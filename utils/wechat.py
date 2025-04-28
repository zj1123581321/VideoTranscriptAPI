import json
import requests
from utils.logger import setup_logger, load_config

# 创建日志记录器
logger = setup_logger("wechat_notifier")

class WechatNotifier:
    """
    企业微信通知类
    """
    def __init__(self, webhook=None):
        """
        初始化企业微信通知器
        
        参数:
            webhook: 企业微信webhook地址，如果为None则从配置文件加载
        """
        config = load_config()
        self.webhook = webhook or config.get("wechat", {}).get("webhook")
        if not self.webhook:
            logger.warning("企业微信webhook未配置")
    
    def send_text(self, content):
        """
        发送文本消息
        
        参数:
            content: 要发送的文本内容
            
        返回:
            bool: 发送是否成功
        """
        if not self.webhook:
            logger.warning("企业微信webhook未配置，无法发送通知")
            return False
        
        try:
            data = {
                "msgtype": "text",
                "text": {
                    "content": content
                }
            }
            
            response = requests.post(
                self.webhook,
                data=json.dumps(data),
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            
            if response.status_code == 200 and response.json().get("errcode") == 0:
                logger.info(f"企业微信通知发送成功: {content[:50]}...")
                return True
            else:
                logger.error(f"企业微信通知发送失败: {response.text}")
                return False
        except Exception as e:
            logger.exception(f"企业微信通知发送异常: {str(e)}")
            return False

    def notify_task_status(self, url, status, error=None):
        """
        通知任务状态
        
        参数:
            url: 视频URL
            status: 当前状态
            error: 错误信息，如果有的话
            
        返回:
            bool: 发送是否成功
        """
        content = f"视频转录任务状态更新:\n链接: {url}\n状态: {status}"
        if error:
            content += f"\n错误: {error}"
            
        return self.send_text(content)

def wechat_notify(message, webhook=None, config=None):
    """
    发送企业微信通知的简便函数
    
    参数:
        message: 要发送的通知内容
        webhook: 企业微信webhook地址，如果为None则从config或配置文件加载
        config: 配置字典，如果提供则从中获取webhook
        
    返回:
        bool: 发送是否成功
    """
    if config and not webhook:
        webhook = config.get("wechat", {}).get("webhook")
        
    notifier = WechatNotifier(webhook)
    return notifier.send_text(message) 