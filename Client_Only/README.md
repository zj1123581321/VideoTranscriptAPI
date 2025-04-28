# CapsWriter 离线转录客户端

CapsWriter离线转录客户端模块，提供音频文件转录功能。

## 特性

- 支持多种音频格式转录
- 支持生成多种格式的转录结果（TXT、SRT、LRC、JSON）
- 提供简单易用的API接口
- 支持外部配置文件

## 安装依赖

```bash
pip install -r requirements.txt
```

## 快速开始

### 简单使用

```python
from Client_Only.api import initialize, transcribe

# 初始化
initialize()

# 转录文件
success, files = transcribe("path/to/your/audio.mp3")
if success:
    print(f"转录成功，生成的文件: {files}")
else:
    print("转录失败")
```

### 使用自定义配置

```python
from Client_Only.api import initialize, update_config, transcribe

# 初始化
initialize()

# 更新配置
config = {
    "generate_txt": True,
    "generate_srt": True,
    "server_addr": "your_server_ip",
    "server_port": 6016
}
update_config(config)

# 转录文件
success, files = transcribe("path/to/your/audio.mp3")
```

### 使用配置文件

```python
from Client_Only.api import initialize, transcribe

# 从配置文件初始化
initialize("path/to/your/config.json")

# 转录文件
success, files = transcribe("path/to/your/audio.mp3")
```

## 配置选项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| server_addr | 字符串 | "100.89.110.76" | 服务器地址 |
| server_port | 整数 | 6016 | 服务器端口 |
| file_seg_duration | 整数 | 25 | 转录文件时分段长度（秒） |
| file_seg_overlap | 整数 | 2 | 转录文件时分段重叠（秒） |
| enable_hot_words | 布尔值 | True | 是否启用热词替换 |
| generate_txt | 布尔值 | False | 是否生成纯文本文件 |
| generate_merge_txt | 布尔值 | True | 是否生成合并文本（不分行） |
| generate_srt | 布尔值 | False | 是否生成SRT字幕文件 |
| generate_lrc | 布尔值 | False | 是否生成LRC歌词文件 |
| generate_json | 布尔值 | False | 是否生成JSON详细信息 |
| verbose | 布尔值 | True | 是否显示详细日志 |

## API接口说明

### initialize(config_path=None)

初始化CapsWriter客户端。

- **参数**:
  - config_path: 配置文件路径，如果提供则从配置文件加载配置
- **返回**:
  - bool: 初始化是否成功

### transcribe(file_path)

转录文件的同步接口。

- **参数**:
  - file_path: 要转录的文件路径
- **返回**:
  - tuple: (bool成功状态, list生成的文件)

### update_config(config_dict=None, config_path=None)

更新配置。

- **参数**:
  - config_dict: 配置字典，直接更新配置类
  - config_path: 配置文件路径，从文件加载配置
- **返回**:
  - bool: 更新是否成功

### save_config(config_path)

保存当前配置到文件。

- **参数**:
  - config_path: 配置文件保存路径
- **返回**:
  - bool: 保存是否成功

### get_config()

获取当前配置。

- **返回**:
  - dict: 当前配置的字典形式

## 示例

详见 `example_usage.py` 文件中的使用示例。 