import re
import os
from utils import setup_logger

# 创建日志记录器
logger = setup_logger("srt_converter")

class SRTConverter:
    """
    SRT格式字幕转换器，支持转换为LRC等格式
    """
    def __init__(self, srt_file):
        """
        初始化SRT转换器
        
        参数:
            srt_file: SRT文件路径
        """
        self.srt_file = srt_file
        self.segments = self._parse_srt()
    
    def _parse_srt(self):
        """
        解析SRT文件
        
        返回:
            list: 字幕片段列表，每个片段包含开始时间、结束时间和文本
        """
        try:
            with open(self.srt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 正则表达式匹配SRT格式的每个片段
            pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n([\s\S]*?)(?=\n\d+\n|$)'
            matches = re.findall(pattern, content)
            
            segments = []
            for match in matches:
                index = int(match[0])
                start_time = match[1]
                end_time = match[2]
                text = match[3].strip()
                
                # 转换时间格式为秒
                start_sec = self._time_to_seconds(start_time)
                end_sec = self._time_to_seconds(end_time)
                
                segments.append({
                    'index': index,
                    'start_time': start_time,
                    'end_time': end_time,
                    'start_sec': start_sec,
                    'end_sec': end_sec,
                    'text': text
                })
            
            return segments
        except Exception as e:
            logger.exception(f"解析SRT文件失败: {str(e)}")
            return []
    
    def _time_to_seconds(self, time_str):
        """
        将SRT时间格式转换为秒数
        
        参数:
            time_str: SRT格式时间字符串 (HH:MM:SS,mmm)
            
        返回:
            float: 秒数
        """
        hours, minutes, seconds = time_str.replace(',', '.').split(':')
        return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    
    def _seconds_to_lrc_time(self, seconds):
        """
        将秒数转换为LRC时间格式 [MM:SS.xx]
        
        参数:
            seconds: 秒数
            
        返回:
            str: LRC格式时间字符串
        """
        minutes = int(seconds // 60)
        seconds = seconds % 60
        return f"[{minutes:02d}:{seconds:06.3f}]".replace('.', ':')
    
    def to_lrc(self):
        """
        将SRT格式转换为LRC格式
        
        返回:
            str: LRC格式字符串
        """
        if not self.segments:
            logger.error(f"没有可用的SRT片段: {self.srt_file}")
            return ""
        
        lrc_lines = []
        
        # 添加LRC文件头信息
        lrc_lines.append("[ti:Transcription]")
        lrc_lines.append("[ar:Whisper]")
        lrc_lines.append(f"[al:{os.path.basename(self.srt_file)}]")
        
        # 添加时间戳和文本
        for segment in self.segments:
            timestamp = self._seconds_to_lrc_time(segment['start_sec'])
            lrc_lines.append(f"{timestamp}{segment['text']}")
        
        return "\n".join(lrc_lines)
    
    def to_text(self):
        """
        将SRT格式转换为纯文本
        
        返回:
            str: 纯文本内容
        """
        if not self.segments:
            logger.error(f"没有可用的SRT片段: {self.srt_file}")
            return ""
        
        text_lines = [segment['text'] for segment in self.segments]
        return "\n".join(text_lines)