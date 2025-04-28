from downloaders.douyin import DouyinDownloader
from downloaders.bilibili import BilibiliDownloader
from downloaders.xiaohongshu import XiaohongshuDownloader
from downloaders.youtube import YoutubeDownloader
from utils import setup_logger

# 创建日志记录器
logger = setup_logger("downloader_factory")

def create_downloader(url):
    """
    根据URL创建对应的下载器
    
    参数:
        url: 视频URL
        
    返回:
        BaseDownloader的子类实例，如果没有匹配的下载器则返回None
    """
    downloaders = [
        DouyinDownloader(),
        BilibiliDownloader(),
        XiaohongshuDownloader(),
        YoutubeDownloader()
    ]
    
    for downloader in downloaders:
        if downloader.can_handle(url):
            logger.info(f"为URL创建下载器: {url}, 类型: {downloader.__class__.__name__}")
            return downloader
    
    logger.error(f"没有找到匹配的下载器: {url}")
    return None 