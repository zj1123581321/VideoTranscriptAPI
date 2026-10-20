from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "tests/tools/gen_error_code_doc.py"
ERROR_CODE_DOC = ROOT / "docs/guides/api/error-codes.md"


def generated_error_code_doc(*, root: Path = ROOT) -> str:
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--root", str(root)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout


def _generator_source_root(tmp_path: Path, source_text: str) -> Path:
    source_root = tmp_path / "repo"
    locale_source = ROOT / "src/video_transcript_api/i18n/locales"
    locale_target = source_root / "src/video_transcript_api/i18n/locales"
    locale_target.mkdir(parents=True)
    for locale_name in ("zh-CN.json", "en.json"):
        shutil.copyfile(locale_source / locale_name, locale_target / locale_name)
    fake_source = source_root / "src/video_transcript_api/api/error_example.py"
    fake_source.parent.mkdir(parents=True)
    fake_source.write_text(source_text, encoding="utf-8")
    return source_root


def test_error_code_reference_matches_generator_output() -> None:
    current = ERROR_CODE_DOC.read_text(encoding="utf-8")
    expected = generated_error_code_doc()
    if current != expected:
        raise AssertionError("Generated API error-code reference is stale.")


def test_task_failure_section_describes_data_error_as_unstable_text() -> None:
    document = generated_error_code_doc()
    expected_phrases = (
        "`GET /api/task/{task_id}` 响应的 `data.error` 是任务失败时写入的本地化文本，不是 locale key；它可能随服务端语言和失败内容变化，因此不稳定、不可用于客户端分支。表中 key 仅供对照文案，不是 API 返回值。",
        "In `GET /api/task/{task_id}`, `data.error` is the localized text stored when the task fails, not a locale key. It can vary with the server language and failure details, so it is unstable and must not be used for client branching. The keys in this table are for looking up the corresponding text only; they are not API response values.",
    )
    for phrase in expected_phrases:
        if phrase not in document:
            raise AssertionError("Task failure documentation must identify data.error as unstable text.")


def _table_cells(line: str) -> list[str]:
    if not line.startswith("|") or not line.endswith("|"):
        raise AssertionError("Markdown table rows must start and end with a pipe.")
    return re.split(r"(?<!\\)(?:\\\\)*\|", line)[1:-1]


def _assert_generated_tables_are_well_formed(document: str) -> None:
    lines = document.splitlines()
    separator = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|)+$")
    for index, line in enumerate(lines):
        if not separator.match(line):
            continue
        headers = _table_cells(lines[index - 1])
        if index + 1 >= len(lines) or not lines[index + 1].startswith("|"):
            raise AssertionError("Every table separator must be followed by a data row.")
        row_index = index - 1
        while row_index < len(lines) and lines[row_index].startswith("|"):
            cells = _table_cells(lines[row_index])
            if len(cells) != len(headers):
                raise AssertionError("Every table row must match its header column count.")
            row_index += 1


def test_generated_tables_have_adjacent_rows_with_matching_column_counts() -> None:
    _assert_generated_tables_are_well_formed(generated_error_code_doc())


def test_locale_pipes_and_newlines_are_escaped_in_generated_tables(tmp_path: Path) -> None:
    source_root = _generator_source_root(
        tmp_path, 'raise ApiError(400, "invalid_url")\n'
    )
    locale_target = source_root / "src/video_transcript_api/i18n/locales"
    en_path = locale_target / "en.json"
    en_catalog = json.loads(en_path.read_text(encoding="utf-8"))
    en_catalog["error.invalid_url"] = "before | after\ncontinued"
    en_path.write_text(
        json.dumps(en_catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    generated = generated_error_code_doc(root=source_root)
    _assert_generated_tables_are_well_formed(generated)
    if "before \\| after<br>continued" not in generated:
        raise AssertionError("Locale pipes and newlines must be escaped in table cells.")
    if "| `invalid_url` | 400 |" not in generated:
        raise AssertionError("The localized API error row was not generated.")


def _readme_heading_counts(path: Path) -> tuple[int, int]:
    level_two = 0
    level_three = 0
    in_fence = False
    fence_marker = re.compile(r"^\s*(`{3,}|~{3,})")
    heading = re.compile(r"^(##|###)\s+")
    for line in path.read_text(encoding="utf-8").splitlines():
        fence = fence_marker.match(line)
        if fence:
            marker = fence.group(1)
            if not in_fence:
                in_fence = True
                fence_character = marker[0]
            elif marker[0] == fence_character:
                in_fence = False
            continue
        if in_fence:
            continue
        match = heading.match(line)
        if match and match.group(1) == "##":
            level_two += 1
        elif match:
            level_three += 1
    return level_two, level_three


def test_readme_heading_counts_match_outside_code_fences() -> None:
    assert _readme_heading_counts(ROOT / "README.md") == _readme_heading_counts(
        ROOT / "README.en.md"
    )


def test_both_readmes_link_language_config_and_error_code_reference() -> None:
    for readme_name in ("README.md", "README.en.md"):
        content = (ROOT / readme_name).read_text(encoding="utf-8")
        if '"language"' not in content:
            raise AssertionError(f"{readme_name} is missing a language config example.")
        if "docs/guides/api/error-codes.md" not in content:
            raise AssertionError(f"{readme_name} is missing the error-code reference link.")


def test_generator_extracts_keyword_error_code_calls(tmp_path: Path) -> None:
    source_root = _generator_source_root(
        tmp_path, 'raise ApiError(status_code=400, error_code="invalid_url")\n'
    )

    generated = generated_error_code_doc(root=source_root)
    if "| `invalid_url` | 400 |" not in generated:
        raise AssertionError("Generator did not extract keyword-form ApiError arguments.")


def test_generator_rejects_nonliteral_error_codes_with_source_location(tmp_path: Path) -> None:
    source_root = _generator_source_root(
        tmp_path, "raise ApiError(status_code=400, error_code=ERROR_CODE)\n"
    )
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--root", str(source_root)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode == 0:
        raise AssertionError("Generator silently accepted a non-literal error_code.")
    if "error_example.py:1" not in result.stderr:
        raise AssertionError("Generator errors must identify the source file and line.")
    if "error_code must be a string literal" not in result.stderr:
        raise AssertionError("Generator error must explain the non-literal error_code.")


def test_generator_output_changes_when_locale_text_changes(tmp_path: Path) -> None:
    source_root = tmp_path / "repo"
    locale_source = ROOT / "src/video_transcript_api/i18n/locales"
    locale_target = source_root / "src/video_transcript_api/i18n/locales"
    locale_target.mkdir(parents=True)
    for locale_name in ("zh-CN.json", "en.json"):
        shutil.copyfile(locale_source / locale_name, locale_target / locale_name)

    fake_source = source_root / "src/video_transcript_api/api/error_example.py"
    fake_source.parent.mkdir(parents=True)
    fake_source.write_text(
        'raise ApiError(400, "invalid_url")\n', encoding="utf-8"
    )
    en_path = locale_target / "en.json"
    en_catalog = json.loads(en_path.read_text(encoding="utf-8"))
    en_catalog["error.invalid_url"] += " (changed)"
    en_path.write_text(
        json.dumps(en_catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    regenerated = generated_error_code_doc(root=source_root)
    current_doc = ERROR_CODE_DOC.read_text(encoding="utf-8")
    if "(changed)" not in regenerated:
        raise AssertionError("Generator did not read the changed locale entry.")
    if regenerated == current_doc:
        raise AssertionError("Changed locale text did not change generated Markdown.")
