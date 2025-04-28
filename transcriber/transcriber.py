import os
import sys
import json
import shutil
import importlib
import time
from pathlib import Path
from utils import setup_logger, load_config, ensure_dir
from transcriber.srt_converter import SRTConverter

# 添加Client_Only到系统路径
CLIENT_ONLY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Client_Only")
sys.path.append(CLIENT_ONLY_DIR)

# 导入Client_Only模块
import Client_Only.transcriber as client_transcriber
from Client_Only.config import Config as ClientConfig

# 创建日志记录器
logger = setup_logger("transcriber")

class Transcriber:
    """
    音视频转录器，基于CapsWriter-Offline客户端
    """
    def __init__(self, config=None):
        """
        初始化转录器
        
        参数:
            config: 配置信息，如果为None则从配置文件加载
        """
        if config is None:
            config = load_config()
        
        self.config = config
        self.output_dir = config.get("storage", {}).get("output_dir", "./output")
        self.max_retries = config.get("capswriter", {}).get("max_retries", 3)
        self.retry_delay = config.get("capswriter", {}).get("retry_delay", 5)
        
        # 确保输出目录存在
        ensure_dir(self.output_dir)
        
        # 设置Client_Only配置
        self._setup_client_config()
        
    def _setup_client_config(self):
        """
        设置Client_Only的配置
        """
        try:
            # 从项目配置中获取CapsWriter服务器信息
            server_url = self.config.get("capswriter", {}).get("server_url", "ws://localhost:6006")
            
            # 解析服务器地址和端口
            if server_url.startswith("ws://"):
                server_url = server_url[5:]
            
            if ":" in server_url:
                server_addr, server_port = server_url.split(":")
                server_port = int(server_port)
            else:
                server_addr = server_url
                server_port = 6006
                
            # 更新客户端配置
            ClientConfig.server_addr = server_addr
            ClientConfig.server_port = server_port
            
            # 设置输出格式 - 只生成merge.txt文件
            ClientConfig.generate_txt = False
            ClientConfig.generate_merge_txt = True  # 只生成合并文本
            ClientConfig.generate_srt = False
            ClientConfig.generate_lrc = False
            ClientConfig.generate_json = False
            
            logger.info(f"已配置Client_Only，服务器: {server_addr}:{server_port}，仅生成合并文本文件")
        except Exception as e:
            logger.exception(f"设置Client_Only配置失败: {str(e)}")
            raise
    
    def transcribe(self, audio_path, output_base=None):
        """
        转录音频文件
        
        参数:
            audio_path: 音频文件路径
            output_base: 输出文件基础名，如果为None则使用音频文件名
            
        返回:
            dict: 包含转录结果的字典
                - transcript: 纯文本转录结果
                - merge_txt_path: 合并文本文件路径
        """
        try:
            logger.info(f"开始转录音频文件: {audio_path}")
            
            # 如果未指定输出基础名，则使用音频文件名（不含扩展名）
            if output_base is None:
                output_base = os.path.splitext(os.path.basename(audio_path))[0]
            
            # 准备输出文件路径
            output_base_path = os.path.join(self.output_dir, output_base)
            merge_txt_path = f"{output_base_path}.merge.txt"
            final_txt_path = f"{output_base_path}.txt"
            
            # 确保音频文件存在
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"音频文件不存在: {audio_path}")
            
            # 使用Client_Only进行转录，添加重试逻辑
            attempts = 0
            last_error = None
            
            while attempts < self.max_retries:
                attempts += 1
                try:
                    logger.info(f"调用Client_Only转录文件: {audio_path} (尝试 {attempts}/{self.max_retries})")
                    success, generated_files = client_transcriber.transcribe(audio_path)
                    
                    if success:
                        logger.info(f"转录完成，生成文件: {generated_files}")
                        
                        # 准备返回结果
                        result = {
                            "transcript": "",
                            "merge_txt_path": None
                        }
                        
                        # 处理生成的文件
                        for file_path in generated_files:
                            # 将Path对象转换为字符串
                            if isinstance(file_path, Path):
                                file_path_str = str(file_path)
                            else:
                                file_path_str = file_path
                                
                            # 确定目标路径
                            basename = os.path.basename(file_path_str)
                            target_path = os.path.join(self.output_dir, basename)
                            
                            # 只处理merge.txt文件
                            if file_path_str.endswith(".merge.txt"):
                                # 拷贝文件到输出目录（如果不在输出目录中）
                                if os.path.abspath(file_path_str) != os.path.abspath(target_path):
                                    shutil.copy2(file_path_str, target_path)
                                    logger.info(f"合并文本文件已复制到输出目录: {target_path}")
                                
                                result["merge_txt_path"] = target_path
                                
                                # 读取转录文本
                                try:
                                    with open(file_path_str, 'r', encoding='utf-8') as f:
                                        result["transcript"] = f.read().strip()
                                    logger.info(f"已从合并文本文件提取转录文本")
                                except Exception as e:
                                    logger.warning(f"读取转录文本失败: {str(e)}")
                                
                                # 自动重命名为 .txt 作为主输出
                                if os.path.exists(target_path):
                                    try:
                                        shutil.copy2(target_path, final_txt_path)
                                        logger.info(f"主输出文件已重命名为: {final_txt_path}")
                                        result["txt_path"] = final_txt_path
                                        # 删除 .merge.txt 文件
                                        if os.path.exists(target_path):
                                            os.remove(target_path)
                                            logger.info(f"已删除中间文件: {target_path}")
                                    except Exception as e:
                                        logger.warning(f"重命名主输出文件失败: {str(e)}")
                        
                        # 确保找到了merge.txt文件
                        if not result["merge_txt_path"]:
                            logger.warning("未找到合并文本文件，继续重试...")
                            last_error = "未找到合并文本文件"
                            continue
                        
                        return result
                    else:
                        logger.warning(f"转录尝试失败，返回状态: {success}")
                        last_error = "服务器返回失败状态"
                
                except Exception as e:
                    logger.warning(f"转录尝试 {attempts} 失败: {str(e)}")
                    last_error = str(e)
                
                # 如果不是最后一次尝试，等待后重试
                if attempts < self.max_retries:
                    logger.info(f"等待 {self.retry_delay} 秒后重试...")
                    time.sleep(self.retry_delay)
            
            # 达到最大重试次数仍然失败
            error_msg = f"转录文件失败: {audio_path}, 原因: {last_error}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
            
        except Exception as e:
            logger.exception(f"转录音频文件失败: {str(e)}")
            raise