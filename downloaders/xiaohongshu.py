import os
import re
import json
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
            
            logger.info(f"调用TikHub API获取小红书笔记信息: note_id={note_id}")
            response = self.make_api_request(endpoint, params)
            
            # 记录API响应摘要，帮助调试
            if isinstance(response, dict):
                response_code = response.get("code")
                response_msg = response.get("message", "无消息")
                logger.info(f"API响应状态: {response_code}, 消息: {response_msg}")
                
                # 保存完整响应到文件，用于调试
                debug_file = f"debug_xiaohongshu_{note_id}.json"
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
                raise ValueError(f"获取小红书笔记信息失败: {error_msg}")
            
            # 检查data字段
            if not response.get("data") or not isinstance(response.get("data"), dict):
                logger.error("API响应中缺少data字段或格式不正确")
                raise ValueError("API响应数据格式错误，缺少必要字段")
            
            # 获取笔记详情数据
            data = response.get("data", {})
            note_list = data.get("data", [{}])[0].get("note_list", [{}])[0]
            
            if not note_list:
                logger.error("无法获取笔记详情数据")
                # 记录完整响应以帮助调试
                logger.debug(f"API完整响应: {json.dumps(response, ensure_ascii=False)[:500]}...")
                raise ValueError("获取笔记详情失败，API返回数据结构不符合预期")
            
            # 视频标题
            video_title = note_list.get("title", "")
            if not video_title or video_title.strip() == "":
                video_title = f"xiaohongshu_{note_id}"
                logger.warning(f"未找到视频标题，使用ID作为标题: {video_title}")
            
            # 视频作者
            author = data.get("data", [{}])[0].get("user", {}).get("name", "未知作者")
            
            logger.info(f"获取到视频信息: 标题='{video_title}', 作者='{author}'")
            
            # 视频下载地址
            video_info = note_list.get("video", {})
            download_url = video_info.get("url")
            
            if not download_url:
                # 检查是否是视频笔记
                logger.error(f"小红书笔记可能不是视频类型: {url}")
                raise ValueError(f"小红书笔记可能不是视频类型: {url}")
            
            logger.info(f"找到视频下载URL: {download_url[:50]}...")
            
            # 清理文件名中的非法字符
            safe_title = re.sub(r'[\\/*?:"<>|]', "_", video_title)
            filename = f"xiaohongshu_{note_id}_{int(time.time())}.mp4"
            
            result = {
                "video_id": note_id,
                "video_title": video_title,
                "author": author,
                "download_url": download_url,
                "filename": filename,
                "platform": "xiaohongshu"
            }
            
            logger.info(f"成功获取小红书视频信息: ID={note_id}")
            return result
                
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