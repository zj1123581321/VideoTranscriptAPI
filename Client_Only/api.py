#!/usr/bin/env python
# coding: utf-8

"""
CapsWriter对外API接口模块
提供简单的接口供外部调用
"""

import os
import asyncio
from pathlib import Path

from .config import Config
from .utils.transcriber import transcribe_file
from .utils.cosmic import Cosmic, console

def initialize(config_path=None):
    """
    初始化CapsWriter客户端
    
    参数:
        config_path: 配置文件路径，如果提供则从配置文件加载配置
        
    返回:
        bool: 初始化是否成功
    """
    try:
        # 加载配置
        if config_path and os.path.exists(config_path):
            if not Config.load_from_file(config_path):
                console.print(f"[yellow]警告: 无法加载配置文件 {config_path}，将使用默认配置")
                
        return True
    except Exception as e:
        console.print(f"[red]初始化失败: {e}")
        return False

def transcribe(file_path):
    """
    转录文件的同步接口
    
    参数:
        file_path: 要转录的文件路径
        
    返回:
        tuple: (bool成功状态, list生成的文件)
    """
    return asyncio.run(_async_transcribe(file_path))
    
async def _async_transcribe(file_path):
    """
    转录文件的异步接口
    
    参数:
        file_path: 要转录的文件路径
        
    返回:
        tuple: (bool成功状态, list生成的文件)
    """
    return await transcribe_file(file_path)

def update_config(config_dict=None, config_path=None):
    """
    更新配置
    
    参数:
        config_dict: 配置字典，直接更新配置类
        config_path: 配置文件路径，从文件加载配置
        
    返回:
        bool: 更新是否成功
    """
    try:
        # 从字典更新
        if config_dict:
            for key, value in config_dict.items():
                if hasattr(Config, key):
                    setattr(Config, key, value)
                    
        # 从文件更新
        if config_path:
            return Config.load_from_file(config_path)
            
        return True
    except Exception as e:
        console.print(f"[red]更新配置失败: {e}")
        return False

def save_config(config_path):
    """
    保存当前配置到文件
    
    参数:
        config_path: 配置文件保存路径
        
    返回:
        bool: 保存是否成功
    """
    return Config.save_to_file(config_path)
    
def get_config():
    """
    获取当前配置
    
    返回:
        dict: 当前配置的字典形式
    """
    config_dict = {}
    for key in dir(Config):
        # 跳过私有属性和方法
        if key.startswith('_') or callable(getattr(Config, key)):
            continue
        config_dict[key] = getattr(Config, key)
    return config_dict 