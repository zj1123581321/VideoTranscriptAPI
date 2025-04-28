import os
import re
import json
import requests
from abc import ABC, abstractmethod
from urllib.parse import urlparse, parse_qs
from utils import setup_logger, load_config, ensure_dir

# 创建日志记录器
logger = setup_logger("downloaders")

class BaseDownloader(ABC):
    """
    下载器基类，定义了下载器的通用接口和功能
    """
    def __init__(self):
        """
        初始化下载器
        """
        self.config = load_config()
        self.api_key = self.config.get("tikhub", {}).get("api_key")
        self.temp_dir = self.config.get("storage", {}).get("temp_dir", "./temp")
        ensure_dir(self.temp_dir)
        
    @abstractmethod
    def can_handle(self, url):
        """
        判断是否可以处理该URL
        
        参数:
            url: 视频URL
            
        返回:
            bool: 是否可以处理
        """
        pass
    
    @abstractmethod
    def get_video_info(self, url):
        """
        获取视频信息
        
        参数:
            url: 视频URL
            
        返回:
            dict: 包含视频信息的字典，至少包含以下字段:
                - video_title: 视频标题
                - author: 视频作者
                - download_url: 音视频下载地址（可能是mp3或mp4等）
        """
        pass
    
    @abstractmethod
    def get_subtitle(self, url):
        """
        获取字幕，如果有的话
        
        参数:
            url: 视频URL
            
        返回:
            str: 字幕文本，如果没有则返回None
        """
        pass
    
    def resolve_short_url(self, url):
        """
        解析短链接，获取原始长链接
        
        参数:
            url: 短链接URL
            
        返回:
            str: 原始长链接
        """
        try:
            response = requests.head(url, allow_redirects=True, timeout=10)
            return response.url
        except Exception as e:
            logger.error(f"解析短链接失败: {url}, 错误: {str(e)}")
            return url
    
    def download_file(self, url, filename):
        """
        下载文件到本地
        
        参数:
            url: 文件URL
            filename: 本地文件名
            
        返回:
            str: 本地文件路径，如果下载失败则返回None
        """
        try:
            local_path = os.path.join(self.temp_dir, filename)
            
            # 创建目录（如果不存在）
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()
            
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logger.info(f"文件下载成功: {local_path}")
            return local_path
        except Exception as e:
            logger.error(f"文件下载失败: {url}, 错误: {str(e)}")
            return None
    
    def clean_up(self, file_path):
        """
        清理临时文件
        
        参数:
            file_path: 文件路径
            
        返回:
            bool: 是否成功清理
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"文件已删除: {file_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"删除文件失败: {file_path}, 错误: {str(e)}")
            return False
    
    def make_api_request(self, endpoint, params=None):
        """
        调用TikHub API
        
        参数:
            endpoint: API端点
            params: 请求参数
            
        返回:
            dict: API响应
        """
        if not self.api_key:
            raise ValueError("TikHub API密钥未配置")
        
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        url = f"https://api.tikhub.io{endpoint}"
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"API请求失败: {url}, 错误: {str(e)}")
            raise 