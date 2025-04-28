#!/usr/bin/env python
# coding: utf-8

"""
CapsWriter客户端使用示例
"""

import os
from pathlib import Path

# 导入CapsWriter客户端API
from Client_Only.api import initialize, transcribe, update_config, save_config, get_config

def main():
    """
    CapsWriter客户端使用示例
    """
    print("CapsWriter客户端使用示例")
    
    # 获取当前脚本所在目录
    current_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    
    # 配置文件路径
    config_path = current_dir / "my_config.json"
    
    # 1. 初始化客户端
    print("\n1. 初始化客户端")
    if initialize():
        print("初始化成功！")
    else:
        print("初始化失败！")
        return
    
    # 2. 获取当前配置
    print("\n2. 当前配置：")
    current_config = get_config()
    for key, value in current_config.items():
        if not key.startswith("_") and not callable(value):
            print(f"  {key}: {value}")
    
    # 3. 更新配置
    print("\n3. 更新配置")
    new_config = {
        "generate_txt": True,
        "generate_srt": True
    }
    if update_config(new_config):
        print("配置更新成功！")
    else:
        print("配置更新失败！")
    
    # 4. 保存配置到文件
    print("\n4. 保存配置到文件")
    if save_config(config_path):
        print(f"配置已保存到: {config_path}")
    else:
        print("配置保存失败！")
    
    # 5. 转录文件
    print("\n5. 转录文件")
    # 请替换为实际的音频文件路径
    audio_file = "D:/path/to/your/audio_file.mp3"
    print(f"准备转录文件: {audio_file}")
    
    # 检查文件是否存在
    if not os.path.exists(audio_file):
        print(f"文件不存在: {audio_file}")
        print("请修改代码中的音频文件路径后再运行")
    else:
        # 执行转录
        success, generated_files = transcribe(audio_file)
        
        if success:
            print("转录成功！")
            print("生成的文件:")
            for file in generated_files:
                print(f"  - {file}")
        else:
            print("转录失败！")

if __name__ == "__main__":
    main() 