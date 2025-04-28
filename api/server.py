import os
import json
import uvicorn
import asyncio
import concurrent.futures
from fastapi import FastAPI, HTTPException, Depends, Header, BackgroundTasks, Request
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any

from utils import setup_logger, load_config, WechatNotifier
from downloaders import create_downloader
from transcriber import Transcriber

# 创建日志记录器
logger = setup_logger("api_server")

# 创建API应用
app = FastAPI(
    title="VideoTranscriptAPI",
    description="视频转录API服务",
    version="1.0.0"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 加载配置信息
config = load_config()

# 创建转录任务线程池
max_workers = config.get("concurrent", {}).get("max_workers", 3)
executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)

# 创建企业微信通知器
wechat_notifier = WechatNotifier()

# 任务队列
task_queue = asyncio.Queue(config.get("concurrent", {}).get("queue_size", 10))

# 任务结果存储
task_results = {}


class TranscribeRequest(BaseModel):
    """转录请求数据模型"""
    url: str = Field(..., description="视频URL")


class TranscribeResponse(BaseModel):
    """转录响应数据模型"""
    code: int = Field(200, description="状态码")
    message: str = Field("success", description="状态信息")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")


async def verify_token(authorization: str = Header(None)):
    """验证API令牌"""
    expected_token = config.get("api", {}).get("auth_token")
    
    if not authorization:
        logger.warning("请求未提供Authorization头")
        raise HTTPException(status_code=401, detail="未提供授权令牌")
    
    if not expected_token:
        logger.warning("系统未配置API令牌")
        return
    
    # 检查令牌格式
    token_parts = authorization.split()
    if len(token_parts) != 2 or token_parts[0].lower() != "bearer":
        logger.warning("授权令牌格式错误")
        raise HTTPException(status_code=401, detail="授权令牌格式错误")
    
    token = token_parts[1]
    
    if token != expected_token:
        logger.warning("授权令牌无效")
        raise HTTPException(status_code=401, detail="授权令牌无效")
    
    return token


async def process_task_queue():
    """处理任务队列的后台任务"""
    logger.info("启动任务队列处理器")
    
    while True:
        try:
            # 从队列中获取任务
            task = await task_queue.get()
            task_id = task["id"]
            url = task["url"]
            
            try:
                # 更新任务状态
                task_results[task_id] = {
                    "status": "processing",
                    "message": "正在处理转录任务"
                }
                
                # 提交任务到线程池
                future = executor.submit(process_transcription, task_id, url)
                
                # 等待任务完成
                result = await asyncio.get_event_loop().run_in_executor(
                    None, future.result
                )
                
                # 更新任务结果
                task_results[task_id] = result
            except Exception as e:
                logger.exception(f"任务处理失败: {task_id}, URL: {url}, 错误: {str(e)}")
                
                # 更新任务状态为失败
                task_results[task_id] = {
                    "status": "failed",
                    "message": f"转录任务失败: {str(e)}",
                    "error": str(e)
                }
                
                # 发送错误通知
                wechat_notifier.notify_task_status(url, "转录失败", str(e))
            finally:
                # 标记任务完成
                task_queue.task_done()
        except Exception as e:
            logger.exception(f"任务队列处理器异常: {str(e)}")
            await asyncio.sleep(1)  # 防止过快重试


def process_transcription(task_id, url):
    """
    处理视频转录
    
    参数:
        task_id: 任务ID
        url: 视频URL
        
    返回:
        dict: 包含转录结果的字典
    """
    try:
        logger.info(f"开始处理转录任务: {task_id}, URL: {url}")
        
        # 通知任务开始
        wechat_notifier.notify_task_status(url, "开始处理")
        
        # 创建下载器
        downloader = create_downloader(url)
        if not downloader:
            error_msg = f"不支持的URL类型: {url}"
            logger.error(error_msg)
            wechat_notifier.notify_task_status(url, "下载失败", error_msg)
            return {
                "status": "failed",
                "message": error_msg
            }
        
        # 获取视频信息
        logger.info(f"获取视频信息: {url}")
        video_info = downloader.get_video_info(url)
        
        # 提取视频标题和作者
        video_title = video_info.get("video_title", "")
        author = video_info.get("author", "")
        
        # 尝试获取字幕 - 只有YouTube等特定平台才需要尝试
        subtitle = None
        if downloader.__class__.__name__ == "YoutubeDownloader":
            logger.info(f"尝试获取字幕: {url}")
            subtitle = downloader.get_subtitle(url)
        
        if subtitle:
            # 如果有字幕，直接使用
            logger.info(f"使用平台提供的字幕: {url}")
            
            # 保存字幕文件
            output_dir = config.get("storage", {}).get("output_dir", "./output")
            subtitle_filename = f"{video_info.get('platform')}_{video_info.get('video_id')}.txt"
            subtitle_path = os.path.join(output_dir, subtitle_filename)
            
            os.makedirs(os.path.dirname(subtitle_path), exist_ok=True)
            with open(subtitle_path, "w", encoding="utf-8") as f:
                f.write(subtitle)
            
            # 通知转录完成，包含标题、作者和转录文本
            wechat_notifier.notify_task_status(
                url, 
                "转录完成", 
                title=video_title, 
                author=author, 
                transcript=subtitle
            )
            
            result = {
                "status": "success",
                "message": "使用平台字幕成功",
                "data": {
                    "video_title": video_title,
                    "author": author,
                    "transcript": subtitle,
                    "subtitle_path": subtitle_path
                }
            }
        else:
            # 没有字幕，需要下载音视频并转录
            logger.info(f"下载视频进行转录: {url}")
            wechat_notifier.notify_task_status(url, "正在下载视频", title=video_title, author=author)
            
            # 下载视频
            download_url = video_info.get("download_url")
            filename = video_info.get("filename")
            
            if not download_url or not filename:
                error_msg = f"无法获取下载信息: {url}"
                logger.error(error_msg)
                wechat_notifier.notify_task_status(url, "下载失败", error_msg, title=video_title, author=author)
                return {
                    "status": "failed",
                    "message": error_msg
                }
            
            # 下载文件
            local_file = downloader.download_file(download_url, filename)
            if not local_file:
                error_msg = f"下载文件失败: {url}"
                logger.error(error_msg)
                wechat_notifier.notify_task_status(url, "下载失败", error_msg, title=video_title, author=author)
                return {
                    "status": "failed",
                    "message": error_msg
                }
            
            try:
                # 开始转录
                logger.info(f"开始转录音视频: {local_file}")
                wechat_notifier.notify_task_status(url, "正在转录音视频", title=video_title, author=author)
                
                # 转录文件名
                output_base = f"{video_info.get('platform')}_{video_info.get('video_id')}"
                
                # 创建转录器并转录
                transcriber = Transcriber()
                transcription_result = transcriber.transcribe(local_file, output_base)
                
                # 获取转录文本
                transcript = transcription_result.get("transcript", "")
                
                # 通知转录完成，包含转录文本预览
                wechat_notifier.notify_task_status(
                    url, 
                    "转录完成", 
                    title=video_title, 
                    author=author, 
                    transcript=transcript
                )
                
                # 返回结果
                result = {
                    "status": "success",
                    "message": "转录成功",
                    "data": {
                        "video_title": video_title,
                        "author": author,
                        "transcript": transcript,
                        "srt_path": transcription_result.get("srt_path", ""),
                        "lrc_path": transcription_result.get("lrc_path", ""),
                        "json_path": transcription_result.get("json_path", "")
                    }
                }
            finally:
                # 清理下载的文件
                logger.info(f"清理下载的文件: {local_file}")
                downloader.clean_up(local_file)
        
        return result
    except Exception as e:
        logger.exception(f"转录处理异常: {str(e)}")
        wechat_notifier.notify_task_status(url, "转录异常", str(e))
        
        return {
            "status": "failed",
            "message": f"转录任务异常: {str(e)}",
            "error": str(e)
        }


@app.on_event("startup")
async def startup_event():
    """服务启动时执行"""
    # 启动任务队列处理器
    asyncio.create_task(process_task_queue())
    logger.info("API服务已启动")


@app.post("/api/transcribe", response_model=TranscribeResponse, dependencies=[Depends(verify_token)])
async def transcribe_video(
    request: TranscribeRequest, 
    background_tasks: BackgroundTasks
):
    """
    转录视频接口
    
    请求参数:
        url: 视频URL
        
    返回:
        TranscribeResponse: 包含转录结果的响应
    """
    url = request.url
    if not url:
        logger.warning("请求未提供视频URL")
        raise HTTPException(status_code=400, detail="视频URL不能为空")
    
    try:
        # 生成任务ID
        task_id = f"task_{len(task_results) + 1}"
        
        # 初始化任务状态
        task_results[task_id] = {
            "status": "queued",
            "message": "任务已加入队列"
        }
        
        # 添加任务到队列
        try:
            task = {"id": task_id, "url": url}
            await task_queue.put(task)
            logger.info(f"任务已加入队列: {task_id}, URL: {url}")
        except asyncio.QueueFull:
            logger.warning(f"任务队列已满，拒绝任务: {url}")
            raise HTTPException(status_code=503, detail="任务队列已满，请稍后重试")
        
        # 返回任务ID
        return TranscribeResponse(
            code=202,
            message="任务已提交",
            data={"task_id": task_id}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"提交转录任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"提交转录任务失败: {str(e)}")


@app.get("/api/task/{task_id}", response_model=TranscribeResponse, dependencies=[Depends(verify_token)])
async def get_task_status(task_id: str):
    """
    获取任务状态接口
    
    请求参数:
        task_id: 任务ID
        
    返回:
        TranscribeResponse: 包含任务状态的响应
    """
    if task_id not in task_results:
        logger.warning(f"任务不存在: {task_id}")
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    
    task_result = task_results[task_id]
    
    # 根据任务状态设置响应码
    code = 200
    if task_result.get("status") == "queued" or task_result.get("status") == "processing":
        code = 202  # 处理中
    elif task_result.get("status") == "failed":
        code = 500  # 失败
    
    return TranscribeResponse(
        code=code,
        message=task_result.get("message", "获取任务状态成功"),
        data=task_result.get("data")
    )


def start_server():
    """启动API服务器"""
    host = config.get("api", {}).get("host", "0.0.0.0")
    port = config.get("api", {}).get("port", 8000)
    
    logger.info(f"启动API服务器: {host}:{port}")
    uvicorn.run(app, host=host, port=port) 