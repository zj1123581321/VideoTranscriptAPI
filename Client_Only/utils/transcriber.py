#!/usr/bin/env python
# coding: utf-8

"""
转录核心功能模块
"""

import os
import json
import base64
import time
import asyncio
import re
import uuid
import subprocess
from pathlib import Path

import websockets

from ..config import Config
from .cosmic import Cosmic, console
from .websocket_utils import check_websocket, close_websocket
from .srt_generator import generate_srt_from_txt
from .lrc_generator import generate_lrc_from_json

async def check_file(file_path):
    """
    检查文件是否存在
    
    参数:
        file_path: 文件路径
        
    返回:
        bool: 文件是否存在
    """
    file_path = Path(file_path)
    if not file_path.exists():
        console.print(f"[red]错误: 文件不存在: {file_path}")
        return False
    return True

async def extract_audio(file_path):
    """
    从文件中提取音频数据
    
    参数:
        file_path: 文件路径
        
    返回:
        bytes: 音频数据
        float: 音频时长(秒)
    """
    # 使用ffmpeg提取音频
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", str(file_path),
        "-f", "f32le",  # 32位浮点格式
        "-ac", "1",     # 单声道
        "-ar", "16000", # 16kHz采样率
        "-"
    ]
    
    Cosmic.log(f"正在提取音频...", end='\r')
    
    try:
        process = subprocess.Popen(
            ffmpeg_cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.DEVNULL
        )
        audio_data = process.stdout.read()
        audio_duration = len(audio_data) / 4 / 16000  # 4字节/采样 * 16000采样/秒
        
        Cosmic.log(f"音频提取完成，时长: {audio_duration:.2f}秒")
        return audio_data, audio_duration
    except Exception as e:
        console.print(f"[red]音频提取失败: {e}")
        return None, 0

async def send_audio_data(file_path, audio_data, audio_duration):
    """
    发送音频数据到服务器
    
    参数:
        file_path: 原始文件路径
        audio_data: 音频数据
        audio_duration: 音频时长
        
    返回:
        str: 任务ID
    """
    # 检查连接
    if not await check_websocket():
        console.print("[red]无法连接到服务器，取消转录")
        return None
    
    # 生成任务ID
    task_id = str(uuid.uuid1())
    Cosmic.current_task_id = task_id
    Cosmic.current_file = file_path
    
    Cosmic.log(f"任务ID: {task_id}")
    Cosmic.log(f"处理文件: {file_path}")
    
    # 分段发送音频数据
    offset = 0
    chunk_size = 16000 * 4 * 60  # 每分钟的数据大小
    
    while offset < len(audio_data):
        chunk_end = min(offset + chunk_size, len(audio_data))
        is_final = (chunk_end >= len(audio_data))
        
        # 构建消息
        message = {
            'task_id': task_id,
            'seg_duration': Config.file_seg_duration,
            'seg_overlap': Config.file_seg_overlap,
            'is_final': is_final,
            'time_start': time.time(),
            'time_frame': time.time(),
            'source': 'file',
            'data': base64.b64encode(
                audio_data[offset:chunk_end]
            ).decode('utf-8'),
        }
        
        # 发送消息
        await Cosmic.websocket.send(json.dumps(message))
        
        # 更新进度
        progress = min(chunk_end / 4 / 16000, audio_duration)
        progress_percent = progress / audio_duration * 100
        Cosmic.log(f"发送进度: {progress:.2f}秒 / {audio_duration:.2f}秒 ({progress_percent:.1f}%)", end='\r')
        
        if is_final:
            break
            
        offset = chunk_end
    
    Cosmic.log(f"音频数据发送完成                                       ")
    return task_id

async def receive_results(file_path):
    """
    接收服务器返回的转录结果
    
    参数:
        file_path: 原始文件路径
        
    返回:
        dict: 转录结果
    """
    if not Cosmic.websocket:
        console.print("[red]WebSocket连接已关闭")
        return None
    
    Cosmic.log("等待转录结果...")
    
    # 接收转录结果
    try:
        async for message in Cosmic.websocket:
            try:
                result = json.loads(message)
                
                # 显示进度
                if 'duration' in result:
                    Cosmic.log(f"转录进度: {result['duration']:.2f}秒", end='\r')
                
                # 检查是否为最终结果
                if result.get('is_final', False):
                    Cosmic.log("转录完成！                              ")
                    process_time = result['time_complete'] - result['time_start']
                    rtf = process_time / result['duration']
                    Cosmic.log(f"处理耗时: {process_time:.2f}秒, RTF: {rtf:.3f}")
                    return result
            except json.JSONDecodeError:
                console.print("[yellow]接收到非JSON数据，已忽略")
                continue
    except websockets.ConnectionClosed:
        console.print("[red]WebSocket连接已关闭")
    except Exception as e:
        console.print(f"[red]接收结果时出错: {e}")
    
    return None

async def save_results(file_path, result):
    """
    保存转录结果
    
    参数:
        file_path: 原始文件路径
        result: 转录结果
        
    返回:
        tuple: 生成的文件列表
    """
    if not result:
        return []
    
    file_path = Path(file_path)
    base_path = file_path.with_suffix("")
    generated_files = []
    
    try:
        # 提取结果数据
        text = result.get('text', '')
        text_split = re.sub('[，。？]', '\n', text)
        timestamps = result.get('timestamps', [])
        tokens = result.get('tokens', [])
        
        # 定义输出文件路径
        json_file = base_path.with_suffix(".json")
        txt_file = base_path.with_suffix(".txt")
        merge_txt_file = base_path.with_suffix(".merge.txt")
        
        # 标记中间文件，在最后可能需要删除
        temp_txt_created = False
        temp_json_created = False
        
        # 保存JSON文件
        if Config.generate_json:
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump({
                    'timestamps': timestamps, 
                    'tokens': tokens
                }, f, ensure_ascii=False)
            generated_files.append(json_file)
            Cosmic.log(f"已生成详细信息文件: {json_file}")
        
        # 保存分行文本文件
        if Config.generate_txt:
            with open(txt_file, "w", encoding="utf-8") as f:
                f.write(text_split)
            generated_files.append(txt_file)
            Cosmic.log(f"已生成文本文件: {txt_file}")
        
        # 保存合并文本文件
        if Config.generate_merge_txt:
            with open(merge_txt_file, "w", encoding="utf-8") as f:
                f.write(text)
            generated_files.append(merge_txt_file)
            Cosmic.log(f"已生成合并文本文件: {merge_txt_file}")
        
        # 生成SRT字幕文件
        if Config.generate_srt:
            # 确保生成txt文件，即使选项关闭了
            if not Config.generate_txt:
                with open(txt_file, "w", encoding="utf-8") as f:
                    f.write(text_split)
                temp_txt_created = True
                
            # 确保生成json文件，即使选项关闭了    
            if not Config.generate_json:
                with open(json_file, "w", encoding="utf-8") as f:
                    json.dump({
                        'timestamps': timestamps, 
                        'tokens': tokens
                    }, f, ensure_ascii=False)
                temp_json_created = True
            
            srt_file = generate_srt_from_txt(txt_file)
            if srt_file:
                generated_files.append(srt_file)
                Cosmic.log(f"已生成字幕文件: {srt_file}")
        
        # 生成LRC歌词文件
        if Config.generate_lrc:
            # 确保生成json文件，用于LRC生成
            need_remove_json = False
            if not Config.generate_json and not temp_json_created:
                with open(json_file, "w", encoding="utf-8") as f:
                    json.dump({
                        'timestamps': timestamps, 
                        'tokens': tokens
                    }, f, ensure_ascii=False)
                need_remove_json = True
            
            lrc_file = generate_lrc_from_json(json_file)
            if lrc_file:
                generated_files.append(lrc_file)
                Cosmic.log(f"已生成LRC歌词文件: {lrc_file}")
            
            # 如果是临时创建的JSON文件，且没有其他功能需要它，则删除
            if need_remove_json and not Config.generate_json:
                os.remove(json_file)
                Cosmic.log(f"已删除临时JSON文件: {json_file}", style="dim")
            
        # 清理临时创建的中间文件
        if temp_txt_created and os.path.exists(txt_file):
            os.remove(txt_file)
            Cosmic.log(f"已删除临时文本文件: {txt_file}", style="dim")
            
        if temp_json_created and os.path.exists(json_file) and not Config.generate_lrc:
            # 只有当不需要生成LRC时才删除JSON文件
            os.remove(json_file)
            Cosmic.log(f"已删除临时JSON文件: {json_file}", style="dim")
        
        # 显示转录结果摘要
        if text:
            preview = text[:100] + "..." if len(text) > 100 else text
            Cosmic.log(f"转录结果预览: [green]{preview}")
        
    except Exception as e:
        console.print(f"[red]保存结果时出错: {e}")
    
    return generated_files

async def transcribe_file(file_path):
    """
    转录文件的主函数
    
    参数:
        file_path: 要转录的文件路径
        
    返回:
        tuple: (bool成功状态, list生成的文件)
    """
    file_path = Path(file_path)
    
    try:
        # 1. 检查文件
        if not await check_file(file_path):
            return False, []
        
        # 2. 提取音频
        audio_data, audio_duration = await extract_audio(file_path)
        if not audio_data:
            return False, []
        
        # 3. 发送音频
        task_id = await send_audio_data(file_path, audio_data, audio_duration)
        if not task_id:
            return False, []
        
        # 4. 接收结果
        result = await receive_results(file_path)
        if not result:
            return False, []
        
        # 5. 保存结果
        generated_files = await save_results(file_path, result)
        
        # 6. 清理
        await close_websocket()
        
        return True, generated_files
        
    except Exception as e:
        console.print(f"[red]转录过程中出错: {e}")
        await close_websocket()
        return False, [] 