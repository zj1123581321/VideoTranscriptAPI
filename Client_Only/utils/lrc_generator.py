#!/usr/bin/env python
# coding: utf-8

"""
LRC歌词文件生成工具
"""

import json
import re
from pathlib import Path
from datetime import timedelta

def format_time_lrc(seconds):
    """
    将秒数格式化为LRC时间格式 [mm:ss.xx]
    
    参数:
        seconds: 秒数
        
    返回:
        str: 格式化的时间字符串
    """
    minutes, seconds = divmod(seconds, 60)
    return f"[{int(minutes):02d}:{seconds:.2f}]"

def generate_lrc_from_json(json_file):
    """
    从JSON文件生成LRC歌词文件
    
    参数:
        json_file: JSON文件路径
        
    返回:
        str: 生成的LRC文件路径
    """
    json_path = Path(json_file)
    lrc_path = json_path.with_suffix('.lrc')
    
    # 检查文件是否存在
    if not json_path.exists():
        print(f"错误: 找不到所需的文件 {json_path}")
        return None
    
    # 读取JSON数据
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    timestamps = data.get('timestamps', [])
    tokens = data.get('tokens', [])
    
    if not timestamps or not tokens:
        print("错误: JSON文件中没有找到时间戳或标记")
        return None
    
    # 将标记按时间分段
    # 每隔一定时间(3秒)生成一行歌词
    time_groups = {}
    current_group_time = None
    current_group_text = ""
    group_interval = 3.0  # 每3秒一组
    
    for token, time in zip(tokens, timestamps):
        # 确定当前token所属的时间组
        group_time = int(time / group_interval) * group_interval
        
        if current_group_time is None:
            current_group_time = group_time
            
        if group_time == current_group_time:
            current_group_text += token
        else:
            # 保存当前组并创建新组
            if current_group_text.strip():  # 只保存非空文本
                time_groups[current_group_time] = current_group_text.strip()
            current_group_time = group_time
            current_group_text = token
    
    # 保存最后一组
    if current_group_text.strip():
        time_groups[current_group_time] = current_group_text.strip()
    
    # 生成LRC内容
    lrc_lines = []
    
    # 添加时间轴和文本
    for time, text in sorted(time_groups.items()):
        lrc_lines.append(f"{format_time_lrc(time)}{text}")
    
    # 写入LRC文件
    with open(lrc_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lrc_lines))
    
    return lrc_path 