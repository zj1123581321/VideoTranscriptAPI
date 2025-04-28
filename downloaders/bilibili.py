import os
import re
import json
import time
import datetime
from downloaders.base import BaseDownloader
from utils import setup_logger, create_debug_dir

# 创建日志记录器
logger = setup_logger("bilibili_downloader")
# 创建调试目录
DEBUG_DIR = create_debug_dir()

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
    
    def extract_video_id(self, url):
        """
        从URL中提取视频ID的公共方法
        
        参数:
            url: 视频URL
        返回:
            str: 视频ID
        """
        return self._extract_video_id(url)
    
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
            
            logger.info(f"调用TikHub API获取Bilibili视频信息: bv_id={bv_id}")
            response = self.make_api_request(endpoint, params)
            
            # 生成时间戳前缀
            timestamp_prefix = datetime.datetime.now().strftime("%y%m%d-%H%M%S")
            
            # 记录API响应摘要，帮助调试
            if isinstance(response, dict):
                response_code = response.get("code")
                response_msg = response.get("message", "无消息")
                logger.info(f"API响应状态: {response_code}, 消息: {response_msg}")
                
                # 保存完整响应到文件，用于调试
                debug_file = os.path.join(DEBUG_DIR, f"{timestamp_prefix}_debug_bilibili_{bv_id}.json")
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
                error_file = os.path.join(DEBUG_DIR, f"{timestamp_prefix}_error_bilibili_{bv_id}.json")
                with open(error_file, 'w', encoding='utf-8') as f:
                    json.dump(response, f, ensure_ascii=False, indent=2)
                logger.debug(f"错误响应已保存到: {error_file}")
                
                raise ValueError(f"获取Bilibili视频信息失败: {error_msg}")
            
            # 检查data字段
            if not response.get("data") or not isinstance(response.get("data"), dict):
                logger.error("API响应中缺少data字段或格式不正确")
                raise ValueError("API响应数据格式错误，缺少必要字段")
            
            # 提取必要信息
            data = response.get("data", {}).get("data", {})
            
            if not data:
                logger.error("无法获取视频详情数据")
                
                # 保存错误响应到文件
                error_file = os.path.join(DEBUG_DIR, f"{timestamp_prefix}_error_data_bilibili_{bv_id}.json")
                with open(error_file, 'w', encoding='utf-8') as f:
                    json.dump(response, f, ensure_ascii=False, indent=2)
                    
                logger.debug(f"API完整响应: {json.dumps(response, ensure_ascii=False)[:500]}...")
                raise ValueError("获取视频详情失败，API返回数据结构不符合预期")
            
            # 视频标题
            video_title = data.get("title", "")
            if not video_title or video_title.strip() == "":
                video_title = f"bilibili_{bv_id}"
                logger.warning(f"未找到视频标题，使用ID作为标题: {video_title}")
            
            # 视频作者
            author = data.get("owner", {}).get("name", "未知作者")
            
            logger.info(f"获取到视频信息: 标题='{video_title}', 作者='{author}'")
            
            # 获取cid
            cid = data.get("cid")
            if not cid:
                logger.error("无法获取Bilibili视频CID")
                raise ValueError(f"无法获取Bilibili视频CID: {url}")
            
            # 调用API获取视频流地址
            endpoint = f"/api/v1/bilibili/web/fetch_video_playurl"
            params = {"bv_id": bv_id, "cid": cid}
            
            logger.info(f"调用TikHub API获取Bilibili视频播放地址: bv_id={bv_id}, cid={cid}")
            playurl_response = self.make_api_request(endpoint, params)
            
            # 更新时间戳前缀
            timestamp_prefix = datetime.datetime.now().strftime("%y%m%d-%H%M%S")
            
            # 记录API响应摘要
            if isinstance(playurl_response, dict):
                response_code = playurl_response.get("code")
                response_msg = playurl_response.get("message", "无消息")
                logger.info(f"播放地址API响应状态: {response_code}, 消息: {response_msg}")
                
                # 保存完整响应到文件
                debug_file = os.path.join(DEBUG_DIR, f"{timestamp_prefix}_debug_bilibili_playurl_{bv_id}.json")
                with open(debug_file, 'w', encoding='utf-8') as f:
                    json.dump(playurl_response, f, ensure_ascii=False, indent=2)
                logger.debug(f"播放地址API完整响应已保存到: {debug_file}")
            
            # 检查响应格式
            if not isinstance(playurl_response, dict):
                logger.error(f"播放地址API返回格式错误，预期字典，实际: {type(playurl_response)}")
                raise ValueError("播放地址API返回格式错误，无法解析响应")
            
            # 检查响应状态
            if playurl_response.get("code") != 200:
                error_msg = playurl_response.get("message", "未知错误")
                logger.error(f"获取播放地址API返回错误代码: {playurl_response.get('code')}, 错误信息: {error_msg}")
                
                # 保存错误响应到文件
                error_file = os.path.join(DEBUG_DIR, f"{timestamp_prefix}_error_bilibili_playurl_{bv_id}.json")
                with open(error_file, 'w', encoding='utf-8') as f:
                    json.dump(playurl_response, f, ensure_ascii=False, indent=2)
                logger.debug(f"播放地址错误响应已保存到: {error_file}")
                
                raise ValueError(f"获取Bilibili视频播放地址失败: {error_msg}")
            
            # 提取音频下载地址
            playurl_data = playurl_response.get("data", {}).get("data", {})
            
            if not playurl_data:
                logger.error("播放地址API响应中缺少data.data字段")
                
                # 保存错误响应到文件
                error_file = os.path.join(DEBUG_DIR, f"{timestamp_prefix}_error_playurl_data_bilibili_{bv_id}.json")
                with open(error_file, 'w', encoding='utf-8') as f:
                    json.dump(playurl_response, f, ensure_ascii=False, indent=2)
                    
                raise ValueError("播放地址API响应数据格式错误，缺少必要字段")
            
            # 尝试获取音频下载地址
            download_url = None
            file_ext = "mp4"  # 默认扩展名
            
            if playurl_data.get("dash") and playurl_data["dash"].get("audio"):
                audio_list = playurl_data["dash"]["audio"]
                if audio_list and len(audio_list) > 0:
                    download_url = audio_list[0].get("baseUrl")
                    file_ext = "m4s"  # B站音频格式通常为m4s
                    logger.info(f"找到音频下载URL: {download_url[:50]}...")
            
            if not download_url:
                logger.error("无法获取Bilibili视频下载地址")
                
                # 保存错误数据到文件
                error_file = os.path.join(DEBUG_DIR, f"{timestamp_prefix}_error_no_download_url_bilibili_{bv_id}.json")
                with open(error_file, 'w', encoding='utf-8') as f:
                    json.dump(playurl_data, f, ensure_ascii=False, indent=2)
                    
                raise ValueError(f"无法获取Bilibili视频下载地址: {url}")
            
            # 清理文件名中的非法字符
            safe_title = re.sub(r'[\\/*?:"<>|]', "_", video_title)
            filename = f"bilibili_{bv_id}_{int(time.time())}.{file_ext}"
            
            result = {
                "video_id": bv_id,
                "cid": cid,
                "video_title": video_title,
                "author": author,
                "download_url": download_url,
                "filename": filename,
                "platform": "bilibili"
            }
            
            logger.info(f"成功获取Bilibili视频信息: ID={bv_id}, 文件类型={file_ext}")
            return result
                
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
        # 直接返回None，跳过尝试获取字幕步骤
        return None 