import os
import re
import time
from downloaders.base import BaseDownloader
from utils import setup_logger

# 创建日志记录器
logger = setup_logger("bilibili_downloader")

class BilibiliDownloader(BaseDownloader):
    """
    Bilibili视频下载器
    """
    def can_handle(self, url):
        """
        判断是否可以处理该URL
        
        参数:
            url: 视频URL
            
        返回:
            bool: 是否可以处理
        """
        return "bilibili.com" in url or "b23.tv" in url
    
    def _extract_video_id(self, url):
        """
        从URL中提取视频ID (BV号)
        
        参数:
            url: 视频URL
            
        返回:
            str: 视频BV号
        """
        # 解析短链接
        if "b23.tv" in url:
            url = self.resolve_short_url(url)
        
        # 提取BV号
        match = re.search(r'BV(\w+)', url)
        if match:
            return f"BV{match.group(1)}"
        
        logger.error(f"无法从URL中提取Bilibili视频BV号: {url}")
        raise ValueError(f"无法从URL中提取Bilibili视频BV号: {url}")
    
    def get_video_info(self, url):
        """
        获取视频信息
        
        参数:
            url: 视频URL
            
        返回:
            dict: 包含视频信息的字典
        """
        try:
            # 提取视频BV号
            bv_id = self._extract_video_id(url)
            
            # 调用API获取视频信息
            endpoint = f"/api/v1/bilibili/web/fetch_one_video"
            params = {"bv_id": bv_id}
            
            response = self.make_api_request(endpoint, params)
            
            # 提取必要信息
            if response.get("status") and response.get("data"):
                data = response["data"]["data"]
                
                # 视频标题
                video_title = data.get("title", f"bilibili_{bv_id}")
                
                # 视频作者
                author = data.get("owner", {}).get("name", "未知作者")
                
                # 获取cid
                cid = data.get("cid")
                if not cid:
                    raise ValueError(f"无法获取Bilibili视频CID: {url}")
                
                # 调用API获取视频流地址
                endpoint = f"/api/v1/bilibili/web/fetch_video_playurl"
                params = {"bv_id": bv_id, "cid": cid}
                
                playurl_response = self.make_api_request(endpoint, params)
                
                # 提取音频下载地址
                if (playurl_response.get("status") and 
                    playurl_response.get("data") and 
                    playurl_response["data"].get("data") and 
                    playurl_response["data"]["data"].get("dash") and 
                    playurl_response["data"]["data"]["dash"].get("audio")):
                    
                    audio_list = playurl_response["data"]["data"]["dash"]["audio"]
                    if audio_list and len(audio_list) > 0:
                        download_url = audio_list[0].get("baseUrl")
                        file_ext = "m4s"  # B站音频格式通常为m4s
                    else:
                        raise ValueError(f"无法获取Bilibili视频音频地址: {url}")
                else:
                    raise ValueError(f"无法获取Bilibili视频播放地址: {url}")
                
                if not download_url:
                    raise ValueError(f"无法获取Bilibili视频下载地址: {url}")
                
                # 清理文件名中的非法字符
                safe_title = re.sub(r'[\\/*?:"<>|]', "_", video_title)
                filename = f"bilibili_{bv_id}_{int(time.time())}.{file_ext}"
                
                return {
                    "video_id": bv_id,
                    "cid": cid,
                    "video_title": video_title,
                    "author": author,
                    "download_url": download_url,
                    "filename": filename,
                    "platform": "bilibili"
                }
            else:
                logger.error(f"获取Bilibili视频信息失败: {response.get('message', '未知错误')}")
                raise ValueError(f"获取Bilibili视频信息失败: {response.get('message', '未知错误')}")
                
        except Exception as e:
            logger.exception(f"获取Bilibili视频信息异常: {str(e)}")
            raise
    
    def get_subtitle(self, url):
        """
        获取字幕，B站API目前不支持直接获取字幕，返回None
        
        参数:
            url: 视频URL
            
        返回:
            str: 字幕文本，B站API目前返回None
        """
        logger.info(f"Bilibili视频通过API无法获取字幕: {url}")
        return None 