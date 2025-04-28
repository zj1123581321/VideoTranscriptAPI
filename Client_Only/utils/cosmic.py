#!/usr/bin/env python
# coding: utf-8

"""
全局状态管理
"""
import sys
from pathlib import Path

from rich.console import Console

# 定义日志控制台
console = Console()

class Cosmic:
    """全局状态类"""
    # 网络通信
    websocket = None
    
    # 文件路径
    base_dir = Path(__file__).parent.parent
    
    # 任务信息
    current_task_id = None
    
    # 转录信息
    current_file = None
    
    @classmethod
    def log(cls, message, style=None, end='\n'):
        """记录日志"""
        # 使用相对导入获取Config
        from ..config import Config
        if Config.verbose:
            console.print(message, style=style, end=end) 