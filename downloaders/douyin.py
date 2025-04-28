import os
import re
import time
from downloaders.base import BaseDownloader
from utils import setup_logger

# 创建日志记录器
logger = setup_logger("douyin_downloader")

class DouyinDownloader(BaseDownloader):
    """
    抖音视频下载器
    """
    def can_handle(self, url):
        """
        判断是否可以处理该URL
        
        参数:
            url: 视频URL
            
        返回:
            bool: 是否可以处理
        """
        return "douyin.com" in url or "v.douyin.com" in url
    
    def _extract_aweme_id(self, url):
        """
        从URL中提取视频ID
        
        参数:
            url: 视频URL
            
        返回:
            str: 视频ID
        """
        # 解析短链接
        if "v.douyin.com" in url:
            url = self.resolve_short_url(url)
        
        # 提取视频ID
        match = re.search(r'video/(\d+)', url)
        if match:
            return match.group(1)
        
        logger.error(f"无法从URL中提取抖音视频ID: {url}")
        raise ValueError(f"无法从URL中提取抖音视频ID: {url}")
    
    def get_video_info(self, url):
        """
        获取视频信息
        
        参数:
            url: 视频URL
            
        返回:
            dict: 包含视频信息的字典
        """
        try:
            # 提取视频ID
            aweme_id = self._extract_aweme_id(url)
            
            # 调用API获取视频信息
            endpoint = f"/api/v1/douyin/web/fetch_one_video"
            params = {"aweme_id": aweme_id}
            
            response = self.make_api_request(endpoint, params)
            
            # 提取必要信息
            if response.get("status") and response.get("data"):
                data = response["data"]["aweme_detail"]
                
                # 视频标题
                video_title = data.get("item_title", f"douyin_{aweme_id}")
                
                # 视频作者
                author = data.get("author", {}).get("nickname", "未知作者")
                
                # 尝试获取音频下载地址
                download_url = None
                audio_items = data.get("video", {}).get("bit_rate_audio", [])
                
                if audio_items and len(audio_items) > 0:
                    # 优先使用音频文件
                    audio_url = (audio_items[0].get("audio_meta", {})
                                 .get("url_list", {})
                                 .get("main_url"))
                    if audio_url:
                        download_url = audio_url
                        file_ext = "mp3"
                
                if not download_url:
                    # 没有音频文件，尝试使用视频文件
                    video_items = data.get("video", {}).get("bit_rate", [])
                    
                    if video_items and len(video_items) > 0:
                        # 按码率排序，选择码率最低的视频
                        video_items.sort(key=lambda x: x.get("bit_rate", float("inf")))
                        download_url = video_items[0].get("play_addr", {}).get("url_list", [None])[0]
                        file_ext = "mp4"
                
                if not download_url:
                    raise ValueError(f"无法获取抖音视频下载地址: {url}")
                
                # 清理文件名中的非法字符
                safe_title = re.sub(r'[\\/*?:"<>|]', "_", video_title)
                filename = f"douyin_{aweme_id}_{int(time.time())}.{file_ext}"
                
                return {
                    "video_id": aweme_id,
                    "video_title": video_title,
                    "author": author,
                    "download_url": download_url,
                    "filename": filename,
                    "platform": "douyin"
                }
            else:
                logger.error(f"获取抖音视频信息失败: {response.get('message', '未知错误')}")
                raise ValueError(f"获取抖音视频信息失败: {response.get('message', '未知错误')}")
                
        except Exception as e:
            logger.exception(f"获取抖音视频信息异常: {str(e)}")
            raise
    
    def get_subtitle(self, url):
        """
        获取字幕，抖音视频通常没有字幕，返回None
        
        参数:
            url: 视频URL
            
        返回:
            str: 字幕文本，抖音通常返回None
        """
        logger.info(f"抖音视频没有可获取的字幕: {url}")
        return None 