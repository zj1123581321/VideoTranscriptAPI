#!/usr/bin/env python3
"""Generate zh-CN byte baselines from a source tree (usually Base).

Run from the current card worktree, pointing --src at a Base checkout:

  scratch-worktree.sh \"$PWD\" 708352f6c8807eb8d7e605539480107727cb2fe1 -- \\
    python3 tests/tools/generate_zh_cn_baselines.py \\
      --src . --out tests/unit/i18n_web/fixtures/baselines
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

RESULT_CONTEXT = {
    "request": None,
    "view_token": "browser-fixture-view",
    "title": "Fixture Title",
    "author": "Fixture Author",
    "platform": "YouTube",
    "url": "https://www.youtube.com/watch?v=fixture",
    "created_at": "2026-10-08T12:00:00",
    "created_at_display": "2026-10-08 12:00",
    "summary_html": "<p>Summary body.</p>",
    "summary_state": "generated",
    "calibrated_html": (
        '<div class="dialog-container">'
        '<div id="dlg-0" class="dialog-item">'
        '<div class="speaker-header">'
        '<div class="speaker-tag" title="待确认">说话人1'
        '<span class="speaker-status-badge speaker-pending">待确认</span>'
        "</div></div>"
        "<div class=\"dialog-content\"><p>你好，这是第一段。</p></div>"
        "</div></div>"
    ),
    "calibrated_text": "你好，这是第一段。",
    "notes_html": "<p>Notes body.</p>",
    "chapters_data": "[]",
    "use_speaker_recognition": True,
    "stats": {
        "original_length": 12,
        "calibrated_length": 12,
        "summary_length": 13,
        "calibration_status": "full",
    },
    "llm_config": None,
    "share_card": None,
    "og_image_url": None,
    "deep_read_prompt_presets": [],
    "asset_v": "baseline",
    "page_title": "Fixture Title",
    "error_message": "夹具失败状态",
    "message": "夹具失败状态",
    "status": "success",
}


def _read_home_html(views_py: Path) -> str:
    module = ast.parse(views_py.read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_HOME_HTML"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise RuntimeError("_HOME_HTML not found in " + str(views_py))


def _jinja_env(templates_dir: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.globals["asset_v"] = "baseline"
    return env


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, required=True, help="Source repo root (Base)")
    parser.add_argument("--out", type=Path, required=True, help="Fixture output directory")
    args = parser.parse_args()
    src = args.src.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    views_py = src / "src/video_transcript_api/api/routes/views.py"
    templates_dir = src / "src/web/templates"
    (out / "home.html").write_text(_read_home_html(views_py), encoding="utf-8")

    env = _jinja_env(templates_dir)
    pages = {
        "result.html": "transcript.html",
        "processing.html": "processing.html",
        "error.html": "error.html",
        "cleaned.html": "cleaned.html",
    }
    for filename, template_name in pages.items():
        html = env.get_template(template_name).render(**RESULT_CONTEXT)
        (out / filename).write_text(html, encoding="utf-8")

    static_dir = src / "src/web/static"
    snapshots = {}
    for name, rel in (("submit", "index.html"), ("history", "history.html")):
        html = (static_dir / rel).read_text(encoding="utf-8")
        title = ""
        if "<title" in html:
            start = html.find(">", html.find("<title")) + 1
            end = html.find("</title>", start)
            title = html[start:end].strip()
        snapshots[name] = {"title": title}
    (out / "static_titles.json").write_text(
        json.dumps(snapshots, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("wrote", out)


if __name__ == "__main__":
    main()
