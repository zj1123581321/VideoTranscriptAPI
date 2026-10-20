"""Guard shared localized error strings across persistence and responses."""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_llm_failure_persists_the_precomputed_localized_message():
    source_path = (
        PROJECT_ROOT
        / "src"
        / "video_transcript_api"
        / "api"
        / "services"
        / "llm_ops.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_handle_llm_task"
    )
    assignments = [
        node
        for node in ast.walk(handler)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "fail_message" for target in node.targets)
    ]
    assert len(assignments) == 1
    assert isinstance(assignments[0].value, ast.Call)
    assert isinstance(assignments[0].value.func, ast.Name)
    assert assignments[0].value.func.id == "t"

    persisted_messages = [
        keyword.value
        for node in ast.walk(handler)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "finalize_terminal_status_and_notify"
        for keyword in node.keywords
        if keyword.arg == "error_message"
        and isinstance(keyword.value, ast.Name)
        and keyword.value.id == "fail_message"
    ]
    assert len(persisted_messages) == 1, "terminal write must reuse the logged localized message"


def test_terminal_write_note_is_localized_by_one_helper():
    from video_transcript_api.api.routes.tasks import _terminal_write_note
    from video_transcript_api.i18n import t

    assert _terminal_write_note(True) == ""
    assert _terminal_write_note(False) == t("error.terminal_write_note")

    source_path = (
        PROJECT_ROOT
        / "src"
        / "video_transcript_api"
        / "api"
        / "routes"
        / "tasks.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    direct_note_translations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "t"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "error.terminal_write_note"
    ]
    assert len(direct_note_translations) == 1
    helper = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_terminal_write_note"
    )
    assert direct_note_translations[0] in ast.walk(helper)
