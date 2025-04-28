import os
import re
import json
import time
import datetime
import xml.etree.ElementTree as ET
import requests
from downloaders.base import BaseDownloader
from utils import setup_logger, create_debug_dir

# 创建日志记录器
logger = setup_logger("youtube_downloader")
# 创建调试目录
DEBUG_DIR = create_debug_dir()

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
            
            logger.info(f"调用TikHub API获取YouTube视频信息: video_id={video_id}")
            response = self.make_api_request(endpoint, params)
            
            # 生成时间戳前缀
            timestamp_prefix = datetime.datetime.now().strftime("%y%m%d-%H%M%S")
            
            # 记录API响应摘要，帮助调试
            if isinstance(response, dict):
                response_code = response.get("code")
                response_msg = response.get("message", "无消息")
                logger.info(f"API响应状态: {response_code}, 消息: {response_msg}")
                
                # 保存完整响应到文件，用于调试
                debug_file = os.path.join(DEBUG_DIR, f"{timestamp_prefix}_debug_youtube_{video_id}.json")
                with open(debug_file, 'w', encoding='utf-8') as f:
                    json.dump(response, f, ensure_ascii=False, indent=2)
                logger.debug(f"API完整响应已保存到: {debug_file}")
            
            # 检查响应格式并提供详细错误信息
            if not isinstance(response, dict):
                logger.error(f"API返回格式错误，预期字典，实际: {type(response)}")
                raise ValueError("API返回格式错误，无法解析响应")
            
            # TikHub API成功响应时返回code=200
            if response.get("code") != 200:
                error_msg = response.get("message", "未知错误")
                logger.error(f"API返回错误代码: {response.get('code')}, 错误信息: {error_msg}")
                
                # 保存错误响应到文件
                error_file = os.path.join(DEBUG_DIR, f"{timestamp_prefix}_error_youtube_{video_id}.json")
                with open(error_file, 'w', encoding='utf-8') as f:
                    json.dump(response, f, ensure_ascii=False, indent=2)
                logger.debug(f"错误响应已保存到: {error_file}")
                
                raise ValueError(f"获取YouTube视频信息失败: {error_msg}")
            
            # 检查data字段
            if not response.get("data"):
                logger.error("API响应中缺少data字段或格式不正确")
                
                # 保存错误响应到文件
                error_file = os.path.join(DEBUG_DIR, f"{timestamp_prefix}_error_data_youtube_{video_id}.json")
                with open(error_file, 'w', encoding='utf-8') as f:
                    json.dump(response, f, ensure_ascii=False, indent=2)
                
                raise ValueError("API响应数据格式错误，缺少必要字段")
            
            # 提取必要信息
            data = response.get("data", {})
            
            # 视频标题
            video_title = data.get("title", "")
            if not video_title or video_title.strip() == "":
                video_title = f"youtube_{video_id}"
                logger.warning(f"未找到视频标题，使用ID作为标题: {video_title}")
            
            # 视频作者
            author = data.get("channel", {}).get("name", "未知作者")
            
            logger.info(f"获取到视频信息: 标题='{video_title}', 作者='{author}'")
            
            # 尝试获取音频下载地址
            download_url = None
            file_ext = "mp4"  # 默认扩展名
            
            audio_items = data.get("audios", {}).get("items", [])
            
            if audio_items and len(audio_items) > 0:
                download_url = audio_items[0].get("url")
                file_ext = "m4a"  # YouTube音频通常为m4a格式
                logger.info(f"找到音频下载URL: {download_url[:50]}...")
            
            if not download_url:
                logger.error("无法获取YouTube视频音频下载地址")
                
                # 保存错误数据到文件
                error_file = os.path.join(DEBUG_DIR, f"{timestamp_prefix}_error_no_audio_youtube_{video_id}.json")
                with open(error_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                raise ValueError(f"无法获取Youtube视频音频下载地址: {url}")
            
            # 清理文件名中的非法字符
            safe_title = re.sub(r'[\\/*?:"<>|]', "_", video_title)
            filename = f"youtube_{video_id}_{int(time.time())}.{file_ext}"
            
            # 获取字幕信息
            subtitles = data.get("subtitles", {})
            subtitle_info = None
            
            # 检查字幕数据
            if subtitles and subtitles.get("items"):
                subtitle_items = subtitles.get("items", [])
                
                # 优先选择中文字幕，其次是英文字幕
                zh_subtitle = next((item for item in subtitle_items if item.get("code") == "zh"), None)
                en_subtitle = next((item for item in subtitle_items if item.get("code") == "en"), None)
                
                subtitle_info = zh_subtitle or en_subtitle
                
                if subtitle_info:
                    logger.info(f"找到字幕: 语言={subtitle_info.get('code', '未知')}")
            
            result = {
                "video_id": video_id,
                "video_title": video_title,
                "author": author,
                "download_url": download_url,
                "filename": filename,
                "platform": "youtube",
                "subtitle_info": subtitle_info
            }
            
            logger.info(f"成功获取YouTube视频信息: ID={video_id}, 文件类型={file_ext}")
            return result
                
        except Exception as e:
            logger.exception(f"获取YouTube视频信息异常: {str(e)}")
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
            
            logger.info(f"下载YouTube字幕: {subtitle_url[:50]}...")
            response = requests.get(subtitle_url, timeout=30)
            response.raise_for_status()
            
            xml_content = response.text
            
            # 生成时间戳前缀
            timestamp_prefix = datetime.datetime.now().strftime("%y%m%d-%H%M%S")
            
            # 保存字幕XML到文件，用于调试
            video_id = video_info.get("video_id")
            subtitle_file = os.path.join(DEBUG_DIR, f"{timestamp_prefix}_subtitle_youtube_{video_id}.xml")
            with open(subtitle_file, 'w', encoding='utf-8') as f:
                f.write(xml_content)
            logger.debug(f"字幕内容已保存到: {subtitle_file}")
            
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
            
            logger.info(f"成功解析YouTube字幕，共{len(texts)}段")
            return merged_text.strip()
        except Exception as e:
            logger.exception(f"解析Youtube字幕XML异常: {str(e)}")
            return None 