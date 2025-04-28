#!/usr/bin/env python
# coding: utf-8

"""
CapsWriter文件转录模块配置
"""

import os
import json
from pathlib import Path

class Config:
    # 服务器连接配置
    server_addr = '100.89.110.76'  # 服务器地址
    server_port = 6016         # 服务器端口
    
    # 转录设置
    file_seg_duration = 25     # 转录文件时分段长度（秒）
    file_seg_overlap = 2       # 转录文件时分段重叠（秒）
    
    # 热词替换功能开关
    enable_hot_words = True    # 是否启用热词替换
    
    # 输出格式选项
    generate_txt = False        # 生成纯文本文件
    generate_merge_txt = True   # 生成合并文本（不分行）
    generate_srt = False        # 生成SRT字幕文件
    generate_lrc = False       # 生成LRC歌词文件
    generate_json = False       # 生成JSON详细信息
    
    # 日志设置
    verbose = True             # 是否显示详细日志
    
    @classmethod
    def update_server(cls, addr=None, port=None):
        """更新服务器连接信息"""
        if addr:
            cls.server_addr = addr
        if port:
            cls.server_port = port
            
    @classmethod
    def load_from_file(cls, config_path):
        """
        从JSON配置文件加载配置
        
        参数:
            config_path: 配置文件路径
            
        返回:
            bool: 是否成功加载
        """
        try:
            if not os.path.exists(config_path):
                return False
                
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                
            # 更新配置项
            for key, value in config_data.items():
                if hasattr(cls, key):
                    setattr(cls, key, value)
                    
            return True
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            return False
            
    @classmethod
    def save_to_file(cls, config_path):
        """
        保存当前配置到JSON文件
        
        参数:
            config_path: 配置文件路径
            
        返回:
            bool: 是否成功保存
        """
        try:
            # 创建配置目录
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            # 获取所有配置项
            config_data = {}
            for key in dir(cls):
                # 跳过私有属性和方法
                if key.startswith('_') or callable(getattr(cls, key)):
                    continue
                config_data[key] = getattr(cls, key)
            
            # 保存到文件
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
                
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False 