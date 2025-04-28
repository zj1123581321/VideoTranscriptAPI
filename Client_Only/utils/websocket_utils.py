#!/usr/bin/env python
# coding: utf-8

"""
WebSocket连接管理工具
"""
import websockets
import asyncio

from ..config import Config
from .cosmic import Cosmic, console

class ConnectionHandler:
    """连接异常处理类"""
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, e, exc_tb):
        if e is None:
            return True
        if isinstance(e, ConnectionRefusedError):
            console.print("[red]无法连接到服务器，请检查服务器地址和端口是否正确")
            return True
        elif isinstance(e, TimeoutError):
            console.print("[red]连接服务器超时")
            return True
        elif isinstance(e, Exception):
            console.print(f"[red]连接出错: {e}")
            return True
        return False

async def check_websocket() -> bool:
    """
    检查并建立WebSocket连接
    
    返回:
        bool: 连接是否成功
    """
    if Cosmic.websocket and not Cosmic.websocket.closed:
        return True
    
    # 增加重试次数和延迟    
    max_retries = 5  # 增加到5次重试
    retry_delay = 2  # 每次重试间隔2秒
    
    for attempt in range(1, max_retries + 1):
        with ConnectionHandler():
            try:
                server_url = f"ws://{Config.server_addr}:{Config.server_port}"
                Cosmic.log(f"连接到服务器: {server_url} (尝试 {attempt}/{max_retries})")
                
                # 增加连接超时时间到10秒
                Cosmic.websocket = await asyncio.wait_for(
                    websockets.connect(server_url, max_size=None),
                    timeout=10.0
                )
                
                Cosmic.log(f"[green]已连接到服务器: {server_url}")
                return True
            except (ConnectionRefusedError, TimeoutError) as e:
                if attempt < max_retries:
                    Cosmic.log(f"[yellow]连接失败，{retry_delay}秒后重试...")
                    await asyncio.sleep(retry_delay)
                else:
                    Cosmic.log(f"[red]连接服务器失败，已达到最大重试次数 ({max_retries})")
    
    return False

async def close_websocket():
    """关闭WebSocket连接"""
    if Cosmic.websocket and not Cosmic.websocket.closed:
        await Cosmic.websocket.close()
        Cosmic.websocket = None
        Cosmic.log("[yellow]已关闭服务器连接") 