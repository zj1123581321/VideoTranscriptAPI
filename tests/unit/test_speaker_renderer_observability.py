import json
from pathlib import Path

from video_transcript_api.utils.rendering.dialog_renderer import DialogRenderer


def _render(tmp_path, payload):
    cache_dir = tmp_path / "render"
    cache_dir.mkdir()
    (cache_dir / "llm_processed.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return DialogRenderer()._render_from_structured_data(str(cache_dir))


def test_renderer_keeps_dialog_index_anchor_and_renders_segment_metadata(tmp_path):
    html = _render(tmp_path, {
        "dialogs": [{
            "segment_id": "seg_00000001_speaker1", "speaker": "说话人1",
            "speaker_id": "Speaker1", "text": "<safe>", "start_time": "00:00:01",
        }],
        "speaker_mapping": {"Speaker1": "说话人1"},
        "segment_overrides": {"seg_00000001_speaker1": {"name": "<Override>", "status": "suspect"}},
        "speaker_risk_flags": ["low_confidence_cluster_dropped"],
    })
    assert 'id="dlg-0"' in html
    assert 'data-segment-id="seg_00000001_speaker1"' in html
    assert 'data-start-time="00:00:01"' in html
    assert "&lt;Override&gt;" in html
    assert "suspect" in html
    assert "本集说话人区分可能不准" in html


def test_renderer_escapes_segment_metadata_attribute_quotes(tmp_path):
    html = _render(tmp_path, {
        "dialogs": [{
            "segment_id": 'seg-1" data-injected="true&<',
            "speaker": "Alice", "text": "hello",
        }],
    })

    assert 'id="dlg-0"' in html
    assert (
        'data-segment-id="seg-1&quot; data-injected=&quot;true&amp;&lt;"'
        in html
    )
    assert 'data-injected="true&<' not in html


def test_renderer_omits_segment_metadata_without_segment_id(tmp_path):
    html = _render(tmp_path, {
        "dialogs": [{"speaker": "Alice", "text": "hello"}],
    })

    assert 'id="dlg-0"' in html
    assert "data-segment-id" not in html


def test_renderer_preserves_dialog_index_anchors_for_chapter_jump_contract(tmp_path):
    html = _render(tmp_path, {
        "dialogs": [
            {"segment_id": "seg-1", "speaker": "Alice", "text": "one"},
            {"segment_id": "seg-2", "speaker": "Bob", "text": "two"},
        ],
    })

    assert 'id="dlg-0"' in html
    assert 'id="dlg-1"' in html
    assert '<div id="seg-1"' not in html
    assert '<div id="seg-2"' not in html


def test_renderer_supports_confirmed_suspect_and_pending_badges(tmp_path):
    html = _render(tmp_path, {
        "dialogs": [
            {"segment_id": "seg_1", "speaker": "Alice", "speaker_id": "S1", "text": "one"},
            {"segment_id": "seg_2", "speaker": "Bob", "speaker_id": "S2", "text": "two"},
            {"segment_id": "seg_3", "speaker": "说话人3", "speaker_id": "S3", "text": "three"},
        ],
        "segment_overrides": {
            "seg_1": {"name": "Alice Confirmed", "status": "confirmed"},
            "seg_2": {"name": "Bob Suspect", "status": "suspect"},
        },
    })
    assert 'speaker-override-confirmed' in html
    assert 'data-override-status="confirmed"' in html
    assert 'speaker-override-suspect' in html
    assert 'data-override-status="suspect"' in html
    assert 'speaker-pending' in html
    assert '待确认' in html


def test_renderer_tooltip_uses_levels_without_confidence_numbers(tmp_path):
    html = _render(tmp_path, {
        "dialogs": [
            {"segment_id": "seg_1", "speaker": "Alice", "speaker_id": "S1", "text": "one"},
            {"segment_id": "seg_2", "speaker": "Bob", "speaker_id": "S2", "text": "two"},
        ],
        "speaker_inference_meta": {
            "S1": {"confidence": 0.8},
            "S2": {"confidence": 0.7},
        },
    })
    assert 'title="较可靠"' in html
    assert 'title="AI 推断"' in html
    assert '0.8' not in html and '0.7' not in html


def test_renderer_old_artifact_keeps_legacy_anchor_and_plain_speaker(tmp_path):
    html = _render(tmp_path, {
        "dialogs": [{"speaker": "Alice", "text": "hello"}],
        "speaker_mapping": {"S1": "Alice"},
    })
    assert 'id="dlg-0"' in html
    assert "Alice" in html
    assert "speaker-risk-warning" not in html
    assert "speaker-override" not in html
    assert "speaker-pending" not in html


def test_renderer_bad_override_container_falls_back_to_dialog_name(tmp_path):
    html = _render(tmp_path, {
        "dialogs": [{"segment_id": "seg_1", "speaker": "Alice", "text": "hello"}],
        "segment_overrides": [],
    })
    assert "Alice" in html
    assert "dialog-container" in html
