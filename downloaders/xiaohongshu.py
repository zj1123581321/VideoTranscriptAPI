import os
import re
import time
from downloaders.base import BaseDownloader
from utils import setup_logger

# 创建日志记录器
logger = setup_logger("xiaohongshu_downloader")

class XiaohongshuDownloader(BaseDownloader):
    """
    小红书视频下载器
    """
    def can_handle(self, url):
        """
        判断是否可以处理该URL
        
        参数:
            url: 视频URL
            
        返回:
            bool: 是否可以处理
        """
        return "xiaohongshu.com" in url or "xhslink.com" in url
    
    def _extract_note_id(self, url):
        """
        从URL中提取笔记ID
        
        参数:
            url: 视频URL
            
        返回:
            str: 笔记ID
        """
        # 解析短链接
        if "xhslink.com" in url:
            url = self.resolve_short_url(url)
        
        # 提取笔记ID
        match = re.search(r'explore/(\w+)', url)
        if match:
            return match.group(1)
        
        logger.error(f"无法从URL中提取小红书笔记ID: {url}")
        raise ValueError(f"无法从URL中提取小红书笔记ID: {url}")
    
    def get_video_info(self, url):
        """
        获取视频信息
        
        参数:
            url: 视频URL
            
        返回:
            dict: 包含视频信息的字典
        """
        try:
            # 提取笔记ID
            note_id = self._extract_note_id(url)
            
            # 调用API获取视频信息
            endpoint = f"/api/v1/xiaohongshu/web/get_note_info"
            params = {"note_id": note_id}
            
            response = self.make_api_request(endpoint, params)
            
            # 提取必要信息
            if response.get("status") and response.get("data"):
                data = response["data"]["data"][0]
                
                # 视频标题
                note_info = data.get("note_list", [{}])[0]
                video_title = note_info.get("title", f"xiaohongshu_{note_id}")
                
                # 视频作者
                author = data.get("user", {}).get("name", "未知作者")
                
                # 视频下载地址
                video_info = note_info.get("video", {})
                download_url = video_info.get("url")
                
                if not download_url:
                    # 检查是否是视频笔记
                    logger.error(f"小红书笔记可能不是视频类型: {url}")
                    raise ValueError(f"小红书笔记可能不是视频类型: {url}")
                
                # 清理文件名中的非法字符
                safe_title = re.sub(r'[\\/*?:"<>|]', "_", video_title)
                filename = f"xiaohongshu_{note_id}_{int(time.time())}.mp4"
                
                return {
                    "video_id": note_id,
                    "video_title": video_title,
                    "author": author,
                    "download_url": download_url,
                    "filename": filename,
                    "platform": "xiaohongshu"
                }
            else:
                logger.error(f"获取小红书笔记信息失败: {response.get('message', '未知错误')}")
                raise ValueError(f"获取小红书笔记信息失败: {response.get('message', '未知错误')}")
                
        except Exception as e:
            logger.exception(f"获取小红书视频信息异常: {str(e)}")
            raise
    
    def get_subtitle(self, url):
        """
        获取字幕，小红书视频通常没有字幕，返回None
        
        参数:
            url: 视频URL
            
        返回:
            str: 字幕文本，小红书通常返回None
        """
        logger.info(f"小红书视频没有可获取的字幕: {url}")
        return None 