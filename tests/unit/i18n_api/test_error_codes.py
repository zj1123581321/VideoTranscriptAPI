"""API error payload and localization contract tests."""

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from video_transcript_api.api.context import (
    ApiError,
    install_api_error_handlers,
    localize_task_error,
)
from video_transcript_api.i18n import SUPPORTED_LANGUAGES
from video_transcript_api.utils.logging.logger import load_config

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOCALES_DIR = PROJECT_ROOT / "src" / "video_transcript_api" / "i18n" / "locales"
_CJK = re.compile(r"[\u3400-\u9fff]")


@pytest.fixture
def language_config():
    config = load_config()
    had_key = "language" in config
    previous = config.get("language")

    def set_language(language):
        if language is None:
            config.pop("language", None)
        else:
            config["language"] = language

    try:
        yield set_language
    finally:
        if had_key:
            config["language"] = previous
        else:
            config.pop("language", None)


_STATIC_BASE_DETAILS = [
    ("上传分享不可用", "upload_share_unavailable"),
    ("上传分享不可用或已关闭", "upload_share_closed"),
    ("视频URL不能为空", "invalid_url"),
    ("任务处理已达上限，请稍后重试", "task_capacity_reached"),
    ("service busy or lock unavailable, retry shortly", "service_busy"),
    ("任务队列已满，请稍后重试", "transcription_queue_full"),
    ("LLM 队列已满，请稍后重试", "llm_queue_full"),
    ("无重新校对权限", "recalibration_permission_denied"),
    ("未找到对应的转录数据", "transcript_not_found"),
    ("缓存中没有转录数据，无法重新校对", "recalibration_transcript_missing"),
    ("归属校验暂时不可用，请稍后重试", "ownership_check_unavailable"),
    ("无权对该任务发起重新校对", "recalibration_ownership_denied"),
    ("无重新生成总结权限", "resummary_permission_denied"),
    ("缓存中没有转录数据，无法重新生成总结", "resummary_transcript_missing"),
    ("无权对该任务发起重新生成总结", "resummary_ownership_denied"),
    ("总结已存在，无需重新生成", "summary_already_exists"),
    ("无生成详细笔记权限", "notes_permission_denied"),
    ("无权对该任务生成详细笔记", "notes_ownership_denied"),
    ("缓存中没有转录数据，无法生成详细笔记", "notes_transcript_missing"),
    ("详细笔记依赖已生成的章节层，请先生成章节后再重试", "notes_chapters_required"),
    ("详细笔记正在生成中，请等待当前任务完成", "notes_already_in_progress"),
    ("详细笔记已存在，无需重复生成", "notes_already_exists"),
    ("详细笔记任务状态查询失败，请稍后重试", "notes_status_unavailable"),
    ("无权访问全局总结比例统计", "summary_ratio_permission_denied"),
    ("无法确定调用方身份", "caller_identity_missing"),
    ("source 仅支持 upload 或 url", "invalid_history_source"),
    ("上传历史查询失败", "upload_history_unavailable"),
    ("服务暂时不可用，请稍后重试", "service_unavailable"),
    ("任务不存在或分享已关闭", "task_not_found_or_share_closed"),
    ("任务不存在", "task_not_found"),
    ("无权访问该任务", "task_access_denied"),
    ("上传回执不存在", "upload_receipt_not_found"),
    ("上传记录不存在", "upload_record_not_found"),
    ("尚未正式受理的上传没有分享可关闭", "upload_not_accepted"),
    ("未提供授权令牌", "authorization_token_missing"),
    ("授权令牌格式错误", "authorization_token_malformed"),
    ("授权令牌无效", "authorization_token_invalid"),
]

_DYNAMIC_BASE_DETAILS = [
    ("任务不存在: probe-task", "task_id_not_found"),
    ("获取任务状态失败: probe-error", "task_status_failed"),
    ("提交转录任务失败: probe-error", "transcription_submission_failed"),
    ("创建重新校对任务失败: probe-error", "recalibration_creation_failed"),
    ("重新校对任务转录数据格式化失败: probe-error", "recalibration_formatting_failed"),
    ("重新生成总结任务转录数据格式化失败: probe-error", "resummary_formatting_failed"),
    ("创建重新生成总结任务失败: probe-error", "resummary_creation_failed"),
    ("创建详细笔记任务失败: probe-error", "notes_creation_failed"),
    ("详细笔记任务加入队列失败: probe-error", "notes_queue_failed"),
    ("任务加入队列失败: probe-error", "task_queue_failed"),
    ("获取统计信息失败: probe-error", "audit_stats_failed"),
    ("获取总结比例统计失败: probe-error", "summary_ratio_failed"),
    ("获取调用记录失败: probe-error", "audit_calls_failed"),
    ("上传历史查询失败: probe-error", "upload_history_failed"),
    ("查询失败: probe-error", "audit_query_failed"),
    ("获取摘要失败: probe-error", "summary_fetch_failed"),
    ("获取用户配置失败: probe-error", "user_profile_failed"),
]


@pytest.mark.parametrize(("source_detail", "expected_code"), _STATIC_BASE_DETAILS)
def test_static_api_details_match_base_and_have_stable_codes(
    language_config, source_detail, expected_code
):
    language_config("zh-CN")

    error = ApiError(status_code=400, detail=source_detail)

    assert error.detail == source_detail
    assert error.error_code == expected_code


@pytest.mark.parametrize(("source_detail", "expected_code"), _DYNAMIC_BASE_DETAILS)
def test_dynamic_api_details_match_base_and_have_stable_codes(
    language_config, source_detail, expected_code
):
    language_config("zh-CN")

    error = ApiError(status_code=500, detail=source_detail)

    assert error.detail == source_detail
    assert error.error_code == expected_code


@pytest.mark.parametrize(
    ("source_detail", "expected_code"),
    [
        (
            "任务队列已满，请稍后重试；任务状态清理失败，task 可能短暂显示为处理中，系统将自动收敛",
            "transcription_queue_full",
        ),
        (
            "LLM 队列已满，请稍后重试；任务状态清理失败，task 可能短暂显示为处理中，系统将自动收敛",
            "llm_queue_full",
        ),
    ],
)
def test_queue_cleanup_warning_keeps_original_chinese_detail(
    language_config, source_detail, expected_code
):
    language_config("zh-CN")

    error = ApiError(status_code=503, detail=source_detail)

    assert error.detail == source_detail
    assert error.error_code == expected_code


@pytest.mark.parametrize(("source_detail", "expected_code"), _STATIC_BASE_DETAILS + _DYNAMIC_BASE_DETAILS)
def test_api_errors_are_english_without_cjk(language_config, source_detail, expected_code):
    language_config("en")

    error = ApiError(status_code=400, detail=source_detail)

    assert error.error_code == expected_code
    assert isinstance(error.detail, str)
    assert _CJK.search(error.detail) is None


@pytest.mark.parametrize(
    "error_code",
    [
        "upload_acceptance_window_expired",
        "upload_content_type",
        "upload_declared_size",
        "upload_declared_size_mismatch",
        "upload_disabled_or_not_ready",
        "upload_history_unavailable",
        "upload_idempotency",
        "upload_idempotency_key",
        "upload_inflight_limit",
        "upload_metadata",
        "upload_not_accepted",
        "upload_observed_size_limit",
        "upload_queue_full",
        "upload_receiver_limit",
        "upload_receipt_not_found",
        "upload_record_not_found",
        "upload_share_closed",
        "upload_share_unavailable",
        "upload_temp_budget",
    ],
)
def test_upload_error_codes_have_english_details(language_config, error_code):
    language_config("en")
    error = ApiError(status_code=400, detail="source detail", error_code=error_code)

    assert error.error_code == error_code
    assert isinstance(error.detail, str)
    assert _CJK.search(error.detail) is None


def test_error_handler_serializes_error_code_and_preserves_fastapi_422(language_config):
    language_config("en")
    app = FastAPI()
    install_api_error_handlers(app)

    @app.get("/api/rejected")
    async def rejected():
        raise ApiError(status_code=401, detail="授权令牌无效")

    @app.get("/api/validated")
    async def validated(value: int):
        return {"value": value}

    client = TestClient(app)
    error_response = client.get("/api/rejected")
    validation_response = client.get("/api/validated?value=invalid")

    assert error_response.status_code == 401
    assert error_response.json() == {
        "detail": "The authorization token is invalid",
        "error_code": "authorization_token_invalid",
    }
    assert validation_response.status_code == 422
    assert set(validation_response.json()) == {"detail"}


def test_real_authentication_and_transcription_errors_are_localized(language_config, monkeypatch):
    language_config("en")
    from video_transcript_api.api.routes import tasks
    from video_transcript_api.api.services.transcription import user_manager, verify_token

    authenticated_app = FastAPI()
    install_api_error_handlers(authenticated_app)
    authenticated_app.include_router(tasks.router)
    monkeypatch.setattr(user_manager, "validate_token", lambda token: None)
    auth_response = TestClient(authenticated_app).get(
        "/api/task/private-task",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert auth_response.status_code == 401
    assert auth_response.json() == {
        "detail": "The authorization token is invalid",
        "error_code": "authorization_token_invalid",
    }

    submission_app = FastAPI()
    install_api_error_handlers(submission_app)
    submission_app.include_router(tasks.router)
    submission_app.dependency_overrides[verify_token] = lambda: {
        "user_id": "test-user",
        "api_key": "test-key",
    }
    invalid_url_response = TestClient(submission_app).post(
        "/api/transcribe",
        json={"url": ""},
    )
    assert invalid_url_response.status_code == 400
    assert invalid_url_response.json() == {
        "detail": "The video URL is required",
        "error_code": "invalid_url",
    }


def test_task_failure_reason_is_localized_before_terminal_write(language_config, monkeypatch):
    language_config("en")
    from video_transcript_api.api.services import transcription

    cache_manager = MagicMock()
    cache_manager.update_task_status.return_value = True
    queue = MagicMock()
    queue.put.side_effect = RuntimeError("provider unavailable")
    written = {}

    def capture_terminal_write(*args, **kwargs):
        written.update(kwargs)
        return True

    monkeypatch.setattr(transcription, "cache_manager", cache_manager)
    monkeypatch.setattr(transcription, "llm_task_queue", queue)
    monkeypatch.setattr(
        transcription, "finalize_terminal_status_and_notify", capture_terminal_write
    )
    result = transcription._handoff_to_llm_stage(
        "task-1",
        {"platform": "youtube"},
        calibrating_status_kwargs={},
        task_notifier=object(),
        log_context="unit-test",
        observability={},
    )

    assert result["status"] == "failed"
    assert written["error_message"] == "Task processing failed"
    assert _CJK.search(written["error_message"]) is None


def test_get_task_returns_the_language_localized_failure_reason(language_config, monkeypatch):
    language_config("en")
    from video_transcript_api.api.routes import tasks
    from video_transcript_api.api.services.transcription import verify_token

    source_reason = "LLM处理失败: provider timeout"
    cache_manager = MagicMock()
    cache_manager.get_task_by_id.return_value = {
        "task_id": "task-1",
        "status": "failed",
        "error_message": localize_task_error(source_reason),
        "view_token": "view-1",
    }
    audit_logger = MagicMock()
    monkeypatch.setattr(tasks, "cache_manager", cache_manager)
    monkeypatch.setattr(tasks, "audit_logger", audit_logger)
    monkeypatch.setattr(tasks, "logger", MagicMock())

    app = FastAPI()
    install_api_error_handlers(app)
    app.include_router(tasks.router)
    app.dependency_overrides[verify_token] = lambda: {
        "user_id": "test-user",
        "api_key": "test-key",
    }
    response = TestClient(app).get("/api/task/task-1")

    assert response.status_code == 200
    assert response.json()["data"]["error"] == "Task processing failed"
    assert _CJK.search(response.json()["data"]["error"]) is None


def test_error_catalog_keys_exist_for_each_language():
    catalogs = {
        language: json.loads(
            (LOCALES_DIR / f"{language}.json").read_text(encoding="utf-8")
        )
        for language in SUPPORTED_LANGUAGES
    }
    error_keys = {
        f"error.{code}"
        for _, code in _STATIC_BASE_DETAILS + _DYNAMIC_BASE_DETAILS
    }
    error_keys.update(
        {
            f"error.{code}"
            for code in [
                "upload_acceptance_window_expired",
                "upload_content_type",
                "upload_declared_size",
                "upload_declared_size_mismatch",
                "upload_disabled_or_not_ready",
                "upload_idempotency",
                "upload_idempotency_key",
                "upload_inflight_limit",
                "upload_metadata",
                "upload_observed_size_limit",
                "upload_queue_full",
                "upload_receiver_limit",
                "upload_temp_budget",
            ]
        }
    )
    error_keys.update(
        {
            "error.api_error",
            "error.method_not_allowed",
            "error.resource_not_found",
            "error.task_failed",
            "error.task_failure_reason",
        }
    )
    for language, catalog in catalogs.items():
        catalog_error_keys = {key for key in catalog if key.startswith("error.")}
        assert catalog_error_keys == error_keys
    assert set(catalogs["zh-CN"]) == set(catalogs["en"])
    assert all(not _CJK.search(value) for value in catalogs["en"].values())
