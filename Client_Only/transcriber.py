#!/usr/bin/env python
# coding: utf-8

"""
CapsWriter文件转录模块主入口
提供同步和异步API
"""

import os
import sys
import asyncio
import argparse
from pathlib import Path

from .config import Config
from .utils.cosmic import Cosmic, console
from .utils.transcriber import transcribe_file

def transcribe(file_path, server_addr=None, server_port=None, **kwargs):
    """
    同步API: 转录音视频文件
    
    参数:
        file_path: 要转录的文件路径
        server_addr: 服务器地址，默认使用配置文件中的地址
        server_port: 服务器端口，默认使用配置文件中的端口
        **kwargs: 其他配置选项，可以覆盖配置文件中的设置
        
    返回:
        tuple: (bool成功状态, list生成的文件)
    """
    # 更新配置
    if server_addr or server_port:
        Config.update_server(server_addr, server_port)
    
    # 更新其他配置
    for key, value in kwargs.items():
        if hasattr(Config, key):
            setattr(Config, key, value)
    
    # 运行异步函数
    return asyncio.run(_transcribe(file_path))

async def transcribe_async(file_path, server_addr=None, server_port=None, **kwargs):
    """
    异步API: 转录音视频文件
    
    参数:
        file_path: 要转录的文件路径
        server_addr: 服务器地址，默认使用配置文件中的地址
        server_port: 服务器端口，默认使用配置文件中的端口
        **kwargs: 其他配置选项，可以覆盖配置文件中的设置
        
    返回:
        tuple: (bool成功状态, list生成的文件)
    """
    # 更新配置
    if server_addr or server_port:
        Config.update_server(server_addr, server_port)
    
    # 更新其他配置
    for key, value in kwargs.items():
        if hasattr(Config, key):
            setattr(Config, key, value)
    
    return await _transcribe(file_path)

async def _transcribe(file_path):
    """内部转录函数"""
    return await transcribe_file(file_path)

def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="CapsWriter离线文件转录工具")
    parser.add_argument("file", help="要转录的音视频文件路径")
    
    args = parser.parse_args()
    
    # 使用config.py中的默认配置
    print(f"使用服务器: {Config.server_addr}:{Config.server_port}")
    print(f"输出设置: SRT={Config.generate_srt}, TXT={Config.generate_txt}, JSON={Config.generate_json}")
    
    # 执行转录
    success, files = transcribe(args.file)
    
    if success:
        if files:
            print(f"转录完成！生成了以下文件:")
            for f in files:
                print(f"  - {f}")
        else:
            print("转录完成，但未生成任何文件")
        return 0
    else:
        print("转录失败")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 