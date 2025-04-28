import os
import sys
import json
import subprocess
import tempfile
import shutil
from pathlib import Path
from utils import setup_logger, load_config, ensure_dir
from transcriber.srt_converter import SRTConverter

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
        
        # CapsWriter-Offline路径配置
        self.capswriter_dir = config.get("capswriter", {}).get("path", "./CapsWriter-Offline")
        self.capswriter_url = config.get("capswriter", {}).get("server_url", "ws://localhost:6006")
        
        # 确保输出目录存在
        ensure_dir(self.output_dir)
        
        # 检查CapsWriter-Offline环境
        self._check_capswriter_environment()
    
    def _check_capswriter_environment(self):
        """
        检查CapsWriter-Offline环境是否可用
        """
        try:
            capswriter_dir = Path(self.capswriter_dir)
            
            # 检查关键文件
            core_client = capswriter_dir / "core_client.py"
            client_transcribe = capswriter_dir / "util" / "client_transcribe.py"
            
            if not core_client.exists() or not client_transcribe.exists():
                logger.error(f"CapsWriter-Offline关键文件不存在。请检查路径: {self.capswriter_dir}")
                raise FileNotFoundError(f"CapsWriter-Offline关键文件不存在: {core_client} 或 {client_transcribe}")
            
            logger.info(f"CapsWriter-Offline环境检查通过: {self.capswriter_dir}")
        except Exception as e:
            logger.exception(f"CapsWriter-Offline环境检查失败: {str(e)}")
            raise
    
    def transcribe(self, audio_path, output_base=None):
        """
        转录音频文件
        
        参数:
            audio_path: 音频文件路径
            output_base: 输出文件基础名，如果为None则使用音频文件名
            
        返回:
            dict: 包含转录结果的字典
                - srt_path: SRT格式字幕文件路径
                - lrc_path: LRC格式歌词文件路径
                - json_path: JSON格式转录结果路径
                - transcript: 纯文本转录结果
        """
        try:
            logger.info(f"开始转录音频文件: {audio_path}")
            
            # 如果未指定输出基础名，则使用音频文件名（不含扩展名）
            if output_base is None:
                output_base = os.path.splitext(os.path.basename(audio_path))[0]
            
            # 准备输出文件路径
            output_base_path = os.path.join(self.output_dir, output_base)
            srt_path = f"{output_base_path}.srt"
            lrc_path = f"{output_base_path}.lrc"
            json_path = f"{output_base_path}.json"
            
            # 使用CapsWriter-Offline客户端进行转录
            capswriter_output = self._run_capswriter_client(audio_path)
            
            # 检查CapsWriter输出文件
            capswriter_srt = None
            capswriter_json = None
            
            # 寻找生成的SRT和JSON文件
            for file_path in capswriter_output:
                if file_path.endswith(".srt"):
                    capswriter_srt = file_path
                elif file_path.endswith(".json"):
                    capswriter_json = file_path
            
            # 拷贝SRT文件到输出目录
            if capswriter_srt and os.path.exists(capswriter_srt):
                shutil.copy2(capswriter_srt, srt_path)
                logger.info(f"SRT字幕文件已复制: {srt_path}")
            else:
                logger.error("CapsWriter-Offline未生成SRT文件")
                raise FileNotFoundError("CapsWriter-Offline未生成SRT文件")
            
            # 读取JSON文件内容
            transcript_text = ""
            json_content = {}
            
            if capswriter_json and os.path.exists(capswriter_json):
                try:
                    with open(capswriter_json, 'r', encoding='utf-8') as f:
                        json_content = json.load(f)
                        
                    # 提取转录文本
                    segments = json_content.get("segments", [])
                    for segment in segments:
                        if "text" in segment:
                            transcript_text += segment["text"] + " "
                    
                    # 复制JSON文件到输出目录
                    shutil.copy2(capswriter_json, json_path)
                    logger.info(f"JSON转录结果已复制: {json_path}")
                except Exception as e:
                    logger.exception(f"处理CapsWriter JSON文件失败: {str(e)}")
            
            # 使用SRT转换器生成LRC格式
            converter = SRTConverter(srt_path)
            lrc_content = converter.to_lrc()
            
            # 保存LRC文件
            with open(lrc_path, "w", encoding="utf-8") as lrc_file:
                lrc_file.write(lrc_content)
            
            logger.info(f"LRC歌词文件已保存: {lrc_path}")
            
            return {
                "srt_path": srt_path,
                "lrc_path": lrc_path,
                "json_path": json_path,
                "transcript": transcript_text.strip()
            }
            
        except Exception as e:
            logger.exception(f"转录音频文件失败: {str(e)}")
            raise
    
    def _run_capswriter_client(self, audio_path):
        """
        运行CapsWriter-Offline客户端进行转录
        
        参数:
            audio_path: 音频文件路径
            
        返回:
            list: 生成的输出文件路径列表
        """
        try:
            # 确保音频文件存在
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"音频文件不存在: {audio_path}")
            
            # 转换为绝对路径
            audio_path = os.path.abspath(audio_path)
            
            # 创建临时工作目录
            with tempfile.TemporaryDirectory() as temp_dir:
                # 准备命令
                python_exec = sys.executable
                core_client_path = os.path.join(self.capswriter_dir, "core_client.py")
                
                # 构建命令
                cmd = [
                    python_exec,
                    core_client_path,
                    "-t", "file",           # 文件转录模式
                    "-u", self.capswriter_url,  # 服务器URL
                    "-f", audio_path        # 音频文件路径
                ]
                
                logger.info(f"运行CapsWriter-Offline命令: {' '.join(cmd)}")
                
                # 切换到CapsWriter-Offline目录
                original_dir = os.getcwd()
                os.chdir(self.capswriter_dir)
                
                # 执行命令
                try:
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    
                    stdout, stderr = process.communicate()
                    
                    if process.returncode != 0:
                        logger.error(f"CapsWriter-Offline转录失败: {stderr}")
                        raise RuntimeError(f"CapsWriter-Offline转录失败: {stderr}")
                    
                    logger.info(f"CapsWriter-Offline转录完成，返回码: {process.returncode}")
                    logger.debug(f"CapsWriter输出: {stdout}")
                    
                    # 提取输出文件路径
                    output_files = []
                    
                    # 寻找与音频文件同名的输出文件
                    base_name = os.path.splitext(os.path.basename(audio_path))[0]
                    output_dir = os.path.dirname(audio_path)
                    
                    # 寻找SRT文件
                    srt_file = os.path.join(output_dir, f"{base_name}.srt")
                    if os.path.exists(srt_file):
                        output_files.append(srt_file)
                    
                    # 寻找JSON文件
                    json_file = os.path.join(output_dir, f"{base_name}.json")
                    if os.path.exists(json_file):
                        output_files.append(json_file)
                    
                    # 寻找TXT文件
                    txt_file = os.path.join(output_dir, f"{base_name}.txt")
                    if os.path.exists(txt_file):
                        output_files.append(txt_file)
                    
                    if not output_files:
                        logger.warning("未找到CapsWriter-Offline生成的文件")
                    
                    return output_files
                
                finally:
                    # 切回原始目录
                    os.chdir(original_dir)
        
        except Exception as e:
            logger.exception(f"运行CapsWriter-Offline客户端失败: {str(e)}")
            raise 