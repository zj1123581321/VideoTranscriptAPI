"""性能埋点模块

提供上下文管理器记录各阶段耗时，支持缓存命中/未命中计数和统计汇总。
``track`` 同时是任务阶段进度的唯一发布入口：进入阶段时经注入的
progress sink 持久化"当前阶段 running"，退出时标记 done/failed，
用户新增一个 ``tracker.track(...)`` 阶段无需任何额外代码就会出现在
处理中查看页上。
"""

import datetime
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional
from .logging import setup_logger

logger = setup_logger("perf_tracker")

#: 阶段进度持久化回调的形状：接收进度文档 dict，返回写入是否生效
#: （False 表示任务行不存在或已终态，属预期拒绝）。注入点在持有
#: CacheManager 的业务侧（见 CacheManager.stage_progress_sink）。
ProgressSink = Callable[[Dict[str, Any]], bool]


class PerfTracker:
    """性能追踪器

    使用上下文管理器记录各阶段耗时，线程安全。同一个 ``track`` 边界
    也是阶段进度的唯一发布入口：sink 经 :meth:`attach_progress_sink`
    注入后，进入/退出（或异常退出）阶段都会发布一份进度文档。

    Usage:
        tracker = PerfTracker(task_id="task-001")
        tracker.attach_progress_sink(cache_manager.stage_progress_sink("task-001"))
        with tracker.track("download"):
            download_file(...)
        with tracker.track("transcription"):
            transcribe(...)
        print(tracker.summary())
    """

    def __init__(self, task_id: str = ""):
        """初始化性能追踪器

        Args:
            task_id: 关联的任务 ID（用于日志标识）
        """
        self.task_id = task_id
        self._records: List[Dict] = []
        self._counters: Dict[str, int] = {}
        self._media_duration_s: Optional[float] = None
        self._lock = threading.Lock()
        self._progress_sink: Optional[ProgressSink] = None
        # 当前 running 阶段的发布信息（publish 名 + started_at ISO）；
        # _published_stages 是已退出阶段的有序发布记录。
        self._publishing: Optional[Dict[str, str]] = None
        self._published_stages: List[Dict[str, Any]] = []

    def set_media_duration(self, duration_s: Optional[float]) -> None:
        """记录探测到的媒体时长（秒），随终态快照 observability 落库。

        供偏慢门槛的后续校准使用（261007-notify-slim 卡 2）；None 表示
        未拿到时长，不写入观测。
        """
        with self._lock:
            self._media_duration_s = duration_s

    def attach_progress_sink(self, sink: ProgressSink) -> None:
        """注入阶段进度的持久化回调（唯一写库路径）。

        Args:
            sink: 接收进度文档并写入 task_status.progress 的回调。
                未注入时 track() 只做内存计时，不发布进度（详细笔记等
                独立 progress 契约的流程不注入，维持自身既有写入方）。
        """
        with self._lock:
            self._progress_sink = sink

    @contextmanager
    def track(self, stage: str, *, publish_as: Optional[str] = None):
        """记录指定阶段的耗时，并向 progress sink 发布阶段边界。

        Args:
            stage: 阶段名称（如 "download", "transcription", "llm_processing"）
            publish_as: 进度文档对外展示的阶段名；缺省发布 stage 本身。
                仅当观测口径锁死了内部名、而用户可见阶段需要另一个名字时
                使用（llm_processing 的观测名被终态快照消费方锁死，用户
                可见名为 llm），新代码不要随手加映射。

        Yields:
            None
        """
        start = time.monotonic()
        publish_name = publish_as or stage
        started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._begin_publishing(publish_name, started_at)
        error = None
        try:
            yield
        except Exception as e:
            error = e
            raise
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000
            record = {
                "stage": stage,
                "elapsed_ms": round(elapsed_ms, 2),
                "success": error is None,
            }
            with self._lock:
                self._records.append(record)

            status = "OK" if error is None else f"FAILED: {error}"
            logger.info(
                f"[perf] {self.task_id} | {stage}: {elapsed_ms:.0f}ms ({status})"
            )

            state = "failed" if error is not None else "done"
            self._finish_publishing(publish_name, started_at, elapsed_ms, state)
            if error is not None:
                # 固定字面量 stage_progress_failed：阶段异常退出的可 grep
                # 降级日志（进度是从属元数据，异常本身继续向上传播）。
                logger.error(
                    f"stage_progress_failed: task={self.task_id} "
                    f"stage={publish_name} error={error}"
                )

    def _begin_publishing(self, publish_name: str, started_at: str) -> None:
        """进入阶段：发布 running 文档；发布失败只记降级日志。"""
        with self._lock:
            self._publishing = {
                "stage": publish_name,
                "started_at": started_at,
            }
            document = self._build_progress_document_locked()
        self._publish(document)

    def _finish_publishing(
        self,
        publish_name: str,
        started_at: str,
        elapsed_ms: float,
        state: str,
    ) -> None:
        """退出阶段：记录已完成区间并发布终态文档。"""
        with self._lock:
            self._publishing = None
            self._published_stages.append(
                {
                    "stage": publish_name,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "state": state,
                }
            )
            document = self._build_progress_document_locked()
        self._publish(document)

    def _build_progress_document_locked(self) -> Dict[str, Any]:
        """组装进度文档；调用方必须已持有 self._lock。

        文档形状（契约见 docs/guides/task-observability.md）：
        {"stage", "stage_state", "started_at", "stages": [...]}
        """
        if self._publishing is not None:
            stage = self._publishing["stage"]
            stage_state = "running"
            started_at = self._publishing["started_at"]
        elif self._published_stages:
            last = self._published_stages[-1]
            stage = last["stage"]
            stage_state = last["state"]
            started_at = ""
        else:
            stage = ""
            stage_state = "running"
            started_at = ""
        return {
            "stage": stage,
            "stage_state": stage_state,
            "started_at": started_at,
            "stages": [
                {
                    "stage": record["stage"],
                    "elapsed_ms": record["elapsed_ms"],
                    "state": record["state"],
                }
                for record in self._published_stages
            ],
        }

    def _publish(self, document: Dict[str, Any]) -> bool:
        """把进度文档交给注入的 sink；失败降级为可 grep 日志，不传播。

        进度是从属元数据，绝不参与状态机：写进度失败不得打断转录/LLM
        主流程，固定字面量 stage_progress_failed 供日志检索。
        """
        with self._lock:
            sink = self._progress_sink
        if sink is None:
            return False
        try:
            written = sink(document)
            if not written:
                logger.warning(
                    f"stage progress write rejected (terminal or missing row): "
                    f"task={self.task_id} stage={document.get('stage')}"
                )
            return bool(written)
        except Exception as exc:
            logger.error(
                f"stage_progress_failed: task={self.task_id} "
                f"stage={document.get('stage')} error={exc}"
            )
            return False

    def count(self, name: str, delta: int = 1):
        """递增一个计数器

        Args:
            name: 计数器名称（如 "cache_hit", "cache_miss"）
            delta: 增量
        """
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + delta

    def get_elapsed(self, stage: str) -> Optional[float]:
        """获取指定阶段的耗时（毫秒）

        Args:
            stage: 阶段名称

        Returns:
            float: 耗时（毫秒），未找到返回 None
        """
        with self._lock:
            for record in reversed(self._records):
                if record["stage"] == stage:
                    return record["elapsed_ms"]
        return None

    def summary(self) -> Dict:
        """汇总所有阶段的性能数据

        Returns:
            dict: 性能摘要，包含各阶段耗时和计数器
        """
        with self._lock:
            total_ms = sum(r["elapsed_ms"] for r in self._records)
            stages = {}
            for r in self._records:
                stage = r["stage"]
                if stage not in stages:
                    stages[stage] = {
                        "elapsed_ms": 0,
                        "count": 0,
                        "successes": 0,
                        "failures": 0,
                    }
                stages[stage]["elapsed_ms"] += r["elapsed_ms"]
                stages[stage]["count"] += 1
                if r["success"]:
                    stages[stage]["successes"] += 1
                else:
                    stages[stage]["failures"] += 1

            return {
                "task_id": self.task_id,
                "total_ms": round(total_ms, 2),
                "stages": stages,
                "counters": dict(self._counters),
            }

    def observation(self) -> Dict:
        """Return completed intervals and the cache counters used by reporting."""
        summary = self.summary()
        counters = {
            name: value
            for name, value in summary["counters"].items()
            if name in {"cache_hit", "cache_hit_partial"}
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        }
        observation = {"stages": summary["stages"]}
        with self._lock:
            media_duration_s = self._media_duration_s
        if media_duration_s is not None:
            observation["media_duration_s"] = media_duration_s
        if counters:
            observation["counters"] = counters
        return observation

    def log_summary(self):
        """将性能摘要输出到日志"""
        s = self.summary()
        parts = [f"[perf-summary] {self.task_id} | total: {s['total_ms']:.0f}ms"]
        for stage, data in s["stages"].items():
            parts.append(f"  {stage}: {data['elapsed_ms']:.0f}ms (x{data['count']})")
        for name, value in s["counters"].items():
            parts.append(f"  {name}: {value}")
        logger.info("\n".join(parts))
