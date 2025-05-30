import os
import json
import uvicorn
import asyncio
import concurrent.futures
import datetime
import re
import threading
import queue
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

# LLM处理队列，使用线程安全的队列，确保同一视频的校对和总结连续发送
llm_task_queue = queue.Queue(maxsize=100)

# 任务结果存储
task_results = {}

# LLM处理锁，确保同一时间只有一个视频在进行LLM处理和微信发送
llm_processing_lock = threading.Lock()


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
                
                # 提交任务到线程池，但不等待结果
                future = executor.submit(process_transcription, task_id, url)
                
                # 添加回调函数来处理任务完成
                def task_completed(future_result):
                    try:
                        result = future_result.result()
                        task_results[task_id] = result
                        logger.info(f"任务完成: {task_id}")
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
                
                # 添加回调函数
                future.add_done_callback(task_completed)
                
                logger.info(f"任务已提交到线程池: {task_id}, URL: {url}")
                
            except Exception as e:
                logger.exception(f"提交任务到线程池失败: {task_id}, URL: {url}, 错误: {str(e)}")
                
                # 更新任务状态为失败
                task_results[task_id] = {
                    "status": "failed",
                    "message": f"提交任务失败: {str(e)}",
                    "error": str(e)
                }
            finally:
                # 标记任务完成（从队列角度）
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
        
        # ======= 新增：先尝试从URL解析平台和视频ID，然后检查缓存 =======
        platform = None
        video_id = None
        
        # 根据下载器类型识别平台
        downloader_class_name = downloader.__class__.__name__
        if downloader_class_name == "DouyinDownloader":
            platform = "douyin"
            video_id = downloader.extract_video_id(url)
        elif downloader_class_name == "BilibiliDownloader":
            platform = "bilibili"
            video_id = downloader.extract_video_id(url)
        elif downloader_class_name == "XiaohongshuDownloader":
            platform = "xiaohongshu"
            # 小红书链接不再预先解析ID，而是在下载器内部处理
            try:
                video_id = downloader.extract_note_id(url)
            except:
                # 如果提取ID失败，不影响后续流程
                logger.warning(f"预先提取小红书笔记ID失败，将在下载器中处理: {url}")
                video_id = None
        elif downloader_class_name == "YoutubeDownloader":
            platform = "youtube"
            video_id = downloader.extract_video_id(url)
        
        output_dir = config.get("storage", {}).get("output_dir", "./output")
        existing_files = []
        video_title = ""
        author = ""
        
        if video_id and platform:
            logger.info(f"从URL中解析出平台: {platform}，视频ID: {video_id}")
            
            # 检查输出目录中是否存在以平台和视频ID结尾的.txt文件
            if os.path.exists(output_dir):
                for file in os.listdir(output_dir):
                    if file.endswith(".txt") and f"_{platform}_{video_id}" in file:
                        existing_files.append(os.path.join(output_dir, file))
        
        if existing_files:
            # 找到最新的文件
            latest_file = max(existing_files, key=os.path.getmtime)
            logger.info(f"找到已存在的转录文件: {latest_file}，跳过下载和转录步骤")
            
            # 读取文件内容
            with open(latest_file, 'r', encoding='utf-8') as f:
                transcript = f.read().strip()
            
            # 从文件名中提取标题，格式为：yyMMdd-hhmmss_平台_videoid_标题.txt
            base_filename = os.path.basename(latest_file)
            video_title = "已缓存视频"
            try:
                # 提取文件名中的标题部分
                name_parts = base_filename.split('_', 3)  # 最多分割3次，第4部分为标题
                if len(name_parts) >= 4:
                    # 去掉.txt扩展名
                    title_part = name_parts[3]
                    if title_part.endswith('.txt'):
                        title_part = title_part[:-4]
                    video_title = title_part
                    logger.info(f"从缓存文件名中提取到标题: {video_title}")
                else:
                    logger.warning(f"缓存文件名格式不符合预期，无法提取标题: {base_filename}")
            except Exception as e:
                logger.warning(f"从文件名提取标题失败: {str(e)}")
            
            # 设置作者为空字符串
            author = ""
            
            # 通知用户我们使用的是缓存的转录
            wechat_notifier.notify_task_status(
                url, 
                "使用已有转录", 
                title=video_title, 
                author=author, 
                transcript="正在处理已存在的转录文本..."
            )
            
            # 将LLM处理任务加入队列，而不是直接处理
            try:
                llm_task = {
                    "task_id": task_id,
                    "url": url,
                    "video_title": video_title,
                    "author": author,
                    "transcript": transcript
                }
                
                logger.info(f"将LLM任务加入队列: {task_id}, 标题: {video_title}")
                
                # 将LLM任务放入线程安全队列中
                llm_task_queue.put(llm_task)
                
            except Exception as e:
                logger.exception(f"将LLM任务加入队列失败: {str(e)}")
                wechat_notifier.send_text(f"【LLM任务加入队列失败】{str(e)}")
            
            return {
                "status": "success",
                "message": "使用已有转录成功",
                "data": {
                    "video_title": video_title,
                    "author": author,
                    "transcript": transcript,
                    "txt_path": latest_file,
                    "cached": True
                }
            }
        # ======= 缓存检查逻辑结束 =======
        
        # 如果没有找到缓存，则获取完整的视频信息
        logger.info(f"未找到缓存文件，获取视频信息: {url}")
        
        # 小红书链接使用原始URL直接获取视频信息
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
            
            # 保存字幕文件，文件名格式为yyMMdd-hhmmss_平台_videoid_安全标题.txt
            output_dir = config.get("storage", {}).get("output_dir", "./output")
            timestamp_prefix = datetime.datetime.now().strftime("%y%m%d-%H%M%S")
            # 清理文件名中的非法字符
            safe_title = re.sub(r'[\\/*?:"<>|]', "_", video_title)
            # 限制标题长度，防止文件名过长
            safe_title = safe_title[:50] if len(safe_title) > 50 else safe_title
            subtitle_filename = f"{timestamp_prefix}_{video_info.get('platform')}_{video_info.get('video_id')}_{safe_title}.txt"
            subtitle_path = os.path.join(output_dir, subtitle_filename)
            
            os.makedirs(os.path.dirname(subtitle_path), exist_ok=True)
            with open(subtitle_path, "w", encoding="utf-8") as f:
                f.write(subtitle)
            
            # 通知转录完成，包含标题、作者和转录文本
            # wechat_notifier.notify_task_status(
            #     url, 
            #     "转录完成", 
            #     title=video_title, 
            #     author=author, 
            #     transcript=subtitle
            # )
            
            # ======= 新增：将LLM处理任务加入队列 =======
            try:
                llm_task = {
                    "task_id": task_id,
                    "url": url,
                    "video_title": video_title,
                    "author": author,
                    "transcript": subtitle
                }
                
                logger.info(f"将LLM任务加入队列（平台字幕）: {task_id}, 标题: {video_title}")
                
                # 将LLM任务放入线程安全队列中
                llm_task_queue.put(llm_task)
                
            except Exception as e:
                logger.exception(f"将LLM任务加入队列失败（平台字幕）: {str(e)}")
                wechat_notifier.send_text(f"【LLM任务加入队列失败】{str(e)}")
            # ======= END =======
            
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
            
            # 检查是否已通过BBDown下载
            local_file = None
            if video_info.get("downloaded", False) and video_info.get("local_file"):
                # 使用BBDown已下载的文件
                local_file = video_info.get("local_file")
                logger.info(f"使用BBDown已下载的文件: {local_file}")
            else:
                # 常规下载流程
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
                
                # 转录文件名，格式为yyMMdd-hhmmss_平台_videoid
                timestamp_prefix = datetime.datetime.now().strftime("%y%m%d-%H%M%S")
                # 清理文件名中的非法字符
                safe_title = re.sub(r'[\\/*?:"<>|]', "_", video_title)
                # 限制标题长度，防止文件名过长
                safe_title = safe_title[:50] if len(safe_title) > 50 else safe_title
                output_base = f"{timestamp_prefix}_{video_info.get('platform')}_{video_info.get('video_id')}_{safe_title}"
                
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
                
                # ======= 新增：将LLM处理任务加入队列 =======
                try:
                    llm_task = {
                        "task_id": task_id,
                        "url": url,
                        "video_title": video_title,
                        "author": author,
                        "transcript": transcript
                    }
                    
                    logger.info(f"将LLM任务加入队列（常规转录）: {task_id}, 标题: {video_title}")
                    
                    # 将LLM任务放入线程安全队列中
                    llm_task_queue.put(llm_task)
                    
                except Exception as e:
                    logger.exception(f"将LLM任务加入队列失败（常规转录）: {str(e)}")
                    wechat_notifier.send_text(f"【LLM任务加入队列失败】{str(e)}")
                # ======= END =======
                
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


def process_llm_queue():
    """
    处理LLM队列的后台任务（在单独线程中运行）
    确保同一视频的校对和总结文本按顺序连续发送
    """
    logger.info("启动LLM队列处理器")
    
    while True:
        try:
            # 从LLM队列中获取任务（阻塞等待）
            llm_task = llm_task_queue.get()
            
            # 获取锁，确保同一时间只处理一个视频的LLM任务
            with llm_processing_lock:
                task_id = llm_task["task_id"]
                url = llm_task["url"]
                video_title = llm_task["video_title"]
                author = llm_task["author"]
                transcript = llm_task["transcript"]
                
                logger.info(f"开始处理LLM任务: {task_id}, 标题: {video_title}")
                
                try:
                    # 调用大模型API进行校对和总结
                    from utils.llm import call_llm_api
                    from utils.wechat import send_long_text_wechat
                    config_llm = config.get("llm", {})
                    api_key = config_llm.get("api_key")
                    base_url = config_llm.get("base_url")
                    calibrate_model = config_llm.get("calibrate_model")
                    summary_model = config_llm.get("summary_model")
                    
                    calibrate_prompt = (
                        "你将收到一段音频的转录文本。你的任务是对这段文本进行校对,提高其可读性,但不改变原意。 "
                        "请按照以下指示进行校对: "
                        "1. 适当分段,使文本结构更清晰。每个自然段落应该是一个完整的思想单元。 "
                        "2. 修正明显的错别字和语法错误。 "
                        "3. 调整标点符号的使用,确保其正确性和一致性。 "
                        "4. 如有必要,可以轻微调整词序以提高可读性,但不要改变原意。 "
                        "5. 保留原文中的口语化表达和说话者的语气特点。 "
                        "6. 不要添加或删除任何实质性内容。 "
                        "7. 不要解释或评论文本内容。 "
                        "只返回校对后的文本,不要包含任何其他解释或评论。 "
                        "以下是需要校对的转录文本: <transcript>  " + transcript + "  </transcript>"
                    )
                    summary_prompt = (
                        "请以回车换行为分割，逐段地将正文内容，高度归纳提炼总结为凝炼的一句话，需涵盖主要内容，不能丢失关键信息和想表达的核心意思。用中文。然后将归纳总结的，用无序列表，挨个排列出来。\n"
                        + transcript
                    )
                    
                    # 并发调用LLM API
                    result_dict = {}
                    
                    def run_calibrate():
                        max_retries = config_llm.get("max_retries", 2)
                        retry_delay = config_llm.get("retry_delay", 5)
                        result_dict['校对文本'] = call_llm_api(calibrate_model, calibrate_prompt, api_key, base_url, max_retries, retry_delay)
                    
                    def run_summary():
                        max_retries = config_llm.get("max_retries", 2)
                        retry_delay = config_llm.get("retry_delay", 5)
                        result_dict['内容总结'] = call_llm_api(summary_model, summary_prompt, api_key, base_url, max_retries, retry_delay)
                    
                    # 启动并发线程
                    t1 = threading.Thread(target=run_calibrate)
                    t2 = threading.Thread(target=run_summary)
                    t1.start()
                    t2.start()
                    t1.join()
                    t2.join()
                    
                    logger.info(f"LLM API调用完成，开始发送微信通知: {task_id}")
                    
                    # 校对文本分段发送
                    send_long_text_wechat(
                        title=video_title,
                        url=url,
                        text=result_dict['校对文本'],
                        is_summary=False
                    )
                    
                    # 总结文本直接发送
                    send_long_text_wechat(
                        title=video_title,
                        url=url,
                        text=result_dict['内容总结'],
                        is_summary=True
                    )
                    
                    logger.info(f"LLM任务处理完成: {task_id}, 标题: {video_title}")
                    
                except Exception as e:
                    logger.exception(f"LLM任务处理异常: {task_id}, 错误: {str(e)}")
                    wechat_notifier.send_text(f"【LLM API调用异常】{str(e)}")
                finally:
                    # 标记LLM任务完成
                    llm_task_queue.task_done()
        except Exception as e:
            logger.exception(f"LLM队列处理器异常: {str(e)}")
            import time
            time.sleep(1)  # 防止过快重试


@app.on_event("startup")
async def startup_event():
    """服务启动时执行"""
    # 启动任务队列处理器
    asyncio.create_task(process_task_queue())
    
    # 启动LLM队列处理器（在单独线程中运行）
    llm_thread = threading.Thread(target=process_llm_queue, daemon=True)
    llm_thread.start()
    
    logger.info("API服务已启动，转录队列和LLM队列处理器已启动")


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