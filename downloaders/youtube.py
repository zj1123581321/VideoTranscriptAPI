import os
import re
import time
import xml.etree.ElementTree as ET
import requests
from downloaders.base import BaseDownloader
from utils import setup_logger

# 创建日志记录器
logger = setup_logger("youtube_downloader")

class YoutubeDownloader(BaseDownloader):
    """
    Youtube视频下载器
    """
    def can_handle(self, url):
        """
        判断是否可以处理该URL
        
        参数:
            url: 视频URL
            
        返回:
            bool: 是否可以处理
        """
        return "youtube.com" in url or "youtu.be" in url
    
    def _extract_video_id(self, url):
        """
        从URL中提取视频ID
        
        参数:
            url: 视频URL
            
        返回:
            str: 视频ID
        """
        # 解析短链接
        if "youtu.be" in url:
            url = self.resolve_short_url(url)
        
        # 从URL中提取视频ID
        if "youtube.com/watch" in url:
            # 形如 https://www.youtube.com/watch?v=VIDEO_ID
            match = re.search(r'v=([^&]+)', url)
            if match:
                return match.group(1)
        elif "youtu.be/" in url:
            # 形如 https://youtu.be/VIDEO_ID
            match = re.search(r'youtu\.be/([^?&]+)', url)
            if match:
                return match.group(1)
        
        logger.error(f"无法从URL中提取Youtube视频ID: {url}")
        raise ValueError(f"无法从URL中提取Youtube视频ID: {url}")
    
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
            video_id = self._extract_video_id(url)
            
            # 调用API获取视频信息
            endpoint = f"/api/v1/youtube/web/get_video_info"
            params = {"video_id": video_id}
            
            response = self.make_api_request(endpoint, params)
            
            # 提取必要信息
            if response.get("status") and response.get("data"):
                data = response["data"]
                
                # 视频标题
                video_title = data.get("title", f"youtube_{video_id}")
                
                # 视频作者
                author = data.get("channel", {}).get("name", "未知作者")
                
                # 尝试获取音频下载地址
                audio_items = data.get("audios", {}).get("items", [])
                
                download_url = None
                if audio_items and len(audio_items) > 0:
                    download_url = audio_items[0].get("url")
                    file_ext = "m4a"  # YouTube音频通常为m4a格式
                
                if not download_url:
                    raise ValueError(f"无法获取Youtube视频音频下载地址: {url}")
                
                # 清理文件名中的非法字符
                safe_title = re.sub(r'[\\/*?:"<>|]', "_", video_title)
                filename = f"youtube_{video_id}_{int(time.time())}.{file_ext}"
                
                # 获取字幕信息
                subtitles = data.get("subtitles", {})
                subtitle_info = None
                
                if subtitles and subtitles.get("status") and subtitles.get("items"):
                    subtitle_items = subtitles["items"]
                    
                    # 优先选择中文字幕，其次是英文字幕
                    zh_subtitle = next((item for item in subtitle_items if item.get("code") == "zh"), None)
                    en_subtitle = next((item for item in subtitle_items if item.get("code") == "en"), None)
                    
                    subtitle_info = zh_subtitle or en_subtitle
                
                return {
                    "video_id": video_id,
                    "video_title": video_title,
                    "author": author,
                    "download_url": download_url,
                    "filename": filename,
                    "platform": "youtube",
                    "subtitle_info": subtitle_info
                }
            else:
                logger.error(f"获取Youtube视频信息失败: {response.get('message', '未知错误')}")
                raise ValueError(f"获取Youtube视频信息失败: {response.get('message', '未知错误')}")
                
        except Exception as e:
            logger.exception(f"获取Youtube视频信息异常: {str(e)}")
            raise
    
    def get_subtitle(self, url):
        """
        获取字幕，Youtube视频可能有字幕
        
        参数:
            url: 视频URL
            
        返回:
            str: 字幕文本，如果有的话
        """
        try:
            video_info = self.get_video_info(url)
            subtitle_info = video_info.get("subtitle_info")
            
            if not subtitle_info or not subtitle_info.get("url"):
                logger.info(f"Youtube视频没有可用字幕: {url}")
                return None
            
            # 下载字幕XML
            subtitle_url = subtitle_info["url"]
            response = requests.get(subtitle_url, timeout=30)
            response.raise_for_status()
            
            xml_content = response.text
            
            # 解析XML字幕
            return self._parse_youtube_subtitle_xml(xml_content)
        except Exception as e:
            logger.exception(f"获取Youtube字幕异常: {str(e)}")
            return None
    
    def _parse_youtube_subtitle_xml(self, xml_content):
        """
        解析YouTube字幕XML
        
        参数:
            xml_content: XML字幕内容
            
        返回:
            str: 解析后的字幕文本
        """
        try:
            root = ET.fromstring(xml_content)
            
            # 提取文本并按时间顺序排序
            texts = []
            for text_element in root.findall(".//text"):
                start = float(text_element.get("start", "0"))
                duration = float(text_element.get("dur", "0"))
                content = text_element.text or ""
                
                texts.append({
                    "start": start,
                    "duration": duration,
                    "content": content.strip()
                })
            
            # 按开始时间排序
            texts.sort(key=lambda x: x["start"])
            
            # 合并字幕文本
            merged_text = ""
            for text in texts:
                if text["content"]:
                    merged_text += text["content"] + " "
            
            return merged_text.strip()
        except Exception as e:
            logger.exception(f"解析Youtube字幕XML异常: {str(e)}")
            return None 