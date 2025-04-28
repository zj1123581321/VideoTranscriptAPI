#!/usr/bin/env python
# coding: utf-8

"""
SRT字幕生成工具
"""

import re
import json
from pathlib import Path
from datetime import timedelta

def format_time(seconds):
    """
    将秒数格式化为SRT时间格式 HH:MM:SS,mmm
    
    参数:
        seconds: 秒数
        
    返回:
        str: 格式化的时间字符串
    """
    td = timedelta(seconds=seconds)
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = int(td.microseconds / 1000)
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def generate_srt_from_txt(txt_file):
    """
    从文本文件生成SRT字幕文件
    
    参数:
        txt_file: 文本文件路径
    """
    txt_path = Path(txt_file)
    json_path = txt_path.with_suffix('.json')
    srt_path = txt_path.with_suffix('.srt')
    
    # 检查文件是否存在
    if not txt_path.exists() or not json_path.exists():
        print(f"错误: 找不到所需的文件 {txt_path} 或 {json_path}")
        return
    
    # 读取文本内容
    with open(txt_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    
    # 读取时间戳
    with open(json_path, 'r', encoding='utf-8') as f:
        time_data = json.load(f)
    
    timestamps = time_data.get('timestamps', [])
    tokens = time_data.get('tokens', [])
    
    if not timestamps or not tokens:
        print("错误: JSON文件中没有找到时间戳或标记")
        return
    
    # 生成SRT内容
    srt_lines = []
    index = 1
    
    # 构建字符到时间的映射
    char_times = []
    for token, time in zip(tokens, timestamps):
        char_times.append((token, time))
    
    # 为每行文本生成字幕
    for i, line in enumerate(lines):
        if not line:
            continue
            
        # 查找该行第一个字符的时间和最后一个字符的时间
        start_time = None
        end_time = None
        
        # 在字符时间映射中查找
        line_chars = "".join(line.split())  # 移除空格
        
        # 寻找匹配的起始和结束时间
        for j, (token, time) in enumerate(char_times):
            if token in line_chars[:3]:  # 检查行开头的前几个字符
                start_time = time
                # 寻找结束时间
                for k in range(j, len(char_times)):
                    if char_times[k][0] in line_chars[-3:]:  # 检查行结尾的后几个字符
                        end_time = char_times[k][1] + 1.0  # 延长1秒
                        break
                break
        
        # 如果找不到精确匹配，使用估计值
        if start_time is None:
            if i > 0 and i < len(timestamps):
                start_time = timestamps[i]
            else:
                start_time = 0
        
        if end_time is None:
            end_time = start_time + max(5.0, len(line) * 0.3)  # 简单估计持续时间
        
        # 添加SRT条目
        srt_lines.append(str(index))
        srt_lines.append(f"{format_time(start_time)} --> {format_time(end_time)}")
        srt_lines.append(line)
        srt_lines.append("")  # 空行
        
        index += 1
    
    # 写入SRT文件
    with open(srt_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(srt_lines))
    
    return srt_path 