"""说话人显示名证据裁决的验收与回归测试（card-vta-261015-speaker-evidence）。

覆盖：
- 真实 fixture 形态的验收测试（tests/fixtures/twitter_space_1wxWjlzQVwDJQ/
  为人工编写的合成对话，见该目录 README.md；mock LLM，不打真网）：作者名
  主持 applied、dialog_address+title_credit 双证据带标注复合名、伪造引用
  作废降级、低 confidence 不再拦截。
- input_fingerprint 扩展（title/author/description/rules_version）。
- 裁决规则的确定性分支（description_roster 不独立生效、无佐证标题名拒绝、
  未知证据类型作废）。
- v1（confidence 门控）旧产物缓存重放走旧降级语义；v2 产物缓存重放直接采用。
- gate 修复轮第 3 轮①：复合名三要素语义与网页/导出下游断言。
"""

import json
import inspect
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from video_transcript_api.llm.core.speaker_inferencer import (
    SPEAKER_EVIDENCE_RULES_VERSION,
    SpeakerInferencer,
)

FIXTURE_PATH = (
    Path(__file__).parent.parent
    / "fixtures"
    / "twitter_space_1wxWjlzQVwDJQ"
    / "transcript_funasr.json"
)

# 与合成 fixture 逐字一致（fixture 契约的一部分；合成对应关系见该目录 README.md）。
FIXTURE_TITLE = "夜航电台之青柠专场：独立开发者的播客实验，三十天拉新一万"
FIXTURE_AUTHOR = "林晚风"
FIXTURE_DESCRIPTION = (
    "Twitter Space participated by 星野, 长风万里, 阿澈, 小满, 铁蛋, "
    "数码君日常, 阿凯, 夜行者, 望舒, 青山不改, 路人甲, 拾光者"
)


def _load_fixture_dialogs():
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return [
        {
            "speaker": seg.get("speaker") or "",
            "text": seg.get("text") or "",
            "start_time": seg.get("start_time"),
        }
        for seg in data["segments"]
    ]


def _candidate(name, evidence_type, quote):
    return {"name": name, "evidence_type": evidence_type, "evidence_quote": quote}


def _run_infer_with(candidates, confidence, dialogs=None, speakers=None):
    """以 mock LLM 跑完整 infer 链路（真实 fixture 采样 + 证据裁决）。

    返回 (inferencer, result)，供需要检查 inferencer 内部状态的用例使用。
    """
    dialogs = dialogs if dialogs is not None else _load_fixture_dialogs()
    speakers = speakers if speakers is not None else ["Speaker1", "Speaker2"]
    inferencer = _make_inferencer()
    inferencer.llm_client.call = MagicMock(
        return_value=_mock_llm(
            {
                "speaker_mapping": {
                    "Speaker1": "林晚风",
                    "Speaker2": "柠姐",
                },
                "confidence": confidence,
                "candidates": candidates,
                "reasoning": "mock",
            }
        )
    )
    result = inferencer.infer(
        speakers=speakers,
        dialogs=dialogs,
        title=FIXTURE_TITLE,
        author=FIXTURE_AUTHOR,
        description=FIXTURE_DESCRIPTION,
    )
    return inferencer, result


def _make_inferencer(cached_mapping=None, confidence_threshold=0.6):
    llm_client = MagicMock()
    cache_manager = MagicMock()
    cache_manager.get_speaker_mapping.return_value = cached_mapping
    return SpeakerInferencer(
        llm_client=llm_client,
        cache_manager=cache_manager,
        model="test-model",
        confidence_threshold=confidence_threshold,
    )


def _mock_llm(structured_output):
    response = MagicMock()
    response.structured_output = structured_output
    return response


class TestRealFixtureEvidenceGate(unittest.TestCase):
    """真实生产 fixture + mock LLM 的四条验收形态（卡面完成条件·行为验收）。"""

    def setUp(self):
        self.dialogs = _load_fixture_dialogs()
        # 生产案例只涉及其中的主对话双方。
        self.speakers = ["Speaker1", "Speaker2"]
        inferencer = _make_inferencer()
        self.sample_groups = inferencer._extract_sample_dialogs(self.dialogs, self.speakers)

    def _prompt_text(self):
        """与 infer() 相同方式组装核对文本（元数据区 + 转录片段区）。"""
        snippets = _make_inferencer()._format_sample_dialogs(self.sample_groups)
        return (
            f"- 标题：{FIXTURE_TITLE}\n"
            f"- 作者：{FIXTURE_AUTHOR}\n"
            f"- 描述：{FIXTURE_DESCRIPTION}\n" + snippets
        )

    def _run_infer(self, candidates, confidence):
        return _run_infer_with(candidates, confidence, self.dialogs, self.speakers)[1]

    def test_host_author_name_applied_not_placeholder(self):
        """验收①：主持人形态——author_host + dialog_address 引用均取自输入
        真实文本 → applied，mapping["Speaker1"] != 说话人1（合成角色：主持人
        =作者林晚风，对话中称「风哥」；对应原生产案例被低置信隐藏的主持人）。"""
        # dialog_address 的 quote 取 Speaker1 真实采样文本的首条（必然逐字
        # 在 prompt 中）；name 是 LLM 对话称呼的声称值，程序只核对 quote 存在性。
        speaker1_sample = self.sample_groups["Speaker1"]["own_samples"][0]
        candidates = {
            "Speaker1": [
                _candidate("林晚风", "author_host", FIXTURE_AUTHOR),
                _candidate("风哥", "dialog_address", speaker1_sample),
            ],
        }
        result = self._run_infer(candidates, confidence={"Speaker1": 0.4, "Speaker2": 0.4})

        prompt_text = self._prompt_text()
        self.assertIn(FIXTURE_AUTHOR, prompt_text)
        self.assertIn(speaker1_sample, prompt_text)
        self.assertNotEqual(result["mapping"]["Speaker1"], "说话人1")
        self.assertTrue(result["meta"]["Speaker1"]["applied"])
        # 双证据 → 带标注复合格式：说话人编号 + 作者关联推测 + 两条来源名
        # （gate 修复轮第 3 轮①：作者名与对话称呼是否同一人属模型推测）。
        self.assertEqual(
            result["mapping"]["Speaker1"],
            "说话人1｜作者关联推测:林晚风｜对话称:风哥",
        )

    def test_soul_lan_composite_display_name(self):
        """验收②：「柠姐/青柠」案例形态——Speaker2 的 dialog_address（柠姐，
        quote 真实在采样覆盖的对话文本中）+ title_credit（青柠，quote 取自
        标题）双候选 → 「说话人2｜标题关联推测:青柠｜对话称:柠姐」。"""
        prompt_text = self._prompt_text()
        # 「柠姐」必须真实被采样覆盖（top2 加额后在本 fixture 上成立），
        # 否则此测试的前提即失效——称呼片段进不了输入正是本卡要修的根因。
        self.assertIn("柠姐", prompt_text)
        candidates = {
            "Speaker2": [
                _candidate("柠姐", "dialog_address", "柠姐"),
                _candidate("青柠", "title_credit", "青柠专场"),
            ],
        }
        result = self._run_infer(candidates, confidence={"Speaker1": 0.0, "Speaker2": 0.0})

        self.assertEqual(
            result["mapping"]["Speaker2"],
            "说话人2｜标题关联推测:青柠｜对话称:柠姐",
        )
        self.assertTrue(result["meta"]["Speaker2"]["applied"])

    def test_forged_quote_rejected_to_placeholder(self):
        """验收③：引用伪造（quote 不在输入中）→ 候选作废、显示「说话人N」，
        meta 保留作废原因 quote_missing。"""
        candidates = {
            "Speaker2": [
                _candidate("某大V", "dialog_address", "这句引用根本不在输入文本中"),
                _candidate("青柠", "title_credit", "不存在的标题片段XYZ"),
            ],
        }
        result = self._run_infer(candidates, confidence={"Speaker1": 0.9, "Speaker2": 0.9})

        self.assertEqual(result["mapping"]["Speaker2"], "说话人2")
        self.assertFalse(result["meta"]["Speaker2"]["applied"])
        self.assertEqual(result["meta"]["Speaker2"]["rejection_reason"], "quote_missing")
        # LLM 原始候选保留在 meta 供审计。
        self.assertEqual(len(result["meta"]["Speaker2"]["candidates"]), 2)
        self.assertEqual(result["meta"]["Speaker2"]["verified_candidates"], [])

    def test_low_confidence_does_not_gate_application(self):
        """验收④：confidence=0.1 但证据核对通过 → 仍 applied（confidence 已
        退出裁决，只入 meta）。"""
        candidates = {
            "Speaker2": [
                _candidate("柠姐", "dialog_address", "柠姐"),
            ],
        }
        result = self._run_infer(candidates, confidence={"Speaker1": 0.0, "Speaker2": 0.1})

        self.assertEqual(result["mapping"]["Speaker2"], "柠姐")
        self.assertTrue(result["meta"]["Speaker2"]["applied"])
        self.assertEqual(result["meta"]["Speaker2"]["confidence"], 0.1)
        # Speaker1 无候选 → 降级；其 confidence 高低不改变结果。
        self.assertEqual(result["mapping"]["Speaker1"], "说话人1")

    def test_whitespace_or_punctuation_quote_rejected(self):
        """审查修复①（correctness-whitespace-evidence-quote）：空白/纯标点
        quote 无实质证据内容——即便逐字存在于输入也按 quote_missing 作废。
        quote 取真实采样区里出现过的单个全角逗号（生产 LLM 摇抄标点的真实
        形态），旧判据会放行导致无实质证据的候选 applied。"""
        quote = "，"
        prompt_text = self._prompt_text()
        # 前提自证：该 quote 确实逐字存在于本轮输入（排除假红）。
        self.assertIn(quote, prompt_text)
        candidates = {
            "Speaker2": [
                _candidate("某大V", "dialog_address", quote),
            ],
        }
        result = self._run_infer(candidates, confidence={"Speaker1": 0.9, "Speaker2": 0.9})

        self.assertEqual(result["mapping"]["Speaker2"], "说话人2")
        self.assertFalse(result["meta"]["Speaker2"]["applied"])
        self.assertEqual(result["meta"]["Speaker2"]["rejection_reason"], "quote_missing")

    def test_cross_section_quote_rejected(self):
        """审查修复②（correctness-speaker-evidence-quote-scope）：quote 只
        出现在另一分区（描述参会名单）却声称 dialog_address → 核对收窄到
        evidence_type 对应分区后作废，堵住「名单里的名字标成对话称呼」的
        绕行路径。"""
        # 望舒只出现在描述参会名单，从不出现在任何发言采样里（前提已探针）。
        prompt_text = self._prompt_text()
        self.assertIn("望舒", prompt_text)
        candidates = {
            "Speaker2": [
                _candidate("望舒", "dialog_address", "望舒"),
            ],
        }
        result = self._run_infer(candidates, confidence={"Speaker1": 0.9, "Speaker2": 0.9})

        self.assertEqual(result["mapping"]["Speaker2"], "说话人2")
        self.assertFalse(result["meta"]["Speaker2"]["applied"])
        self.assertEqual(result["meta"]["Speaker2"]["rejection_reason"], "quote_missing")

    def test_v1_cached_artifact_replays_with_legacy_confidence_semantics(self):
        """验收⑤：v1 旧产物（仅 confidence 无 candidates）读侧兼容不崩，
        走旧降级语义（conf 重判），报告选定「走旧降级语义」选项。"""
        cached_v1 = {
            "mapping": {"Speaker1": "张主持", "Speaker2": "李主讲"},
            "meta": {
                "Speaker1": {"name": "张主持", "confidence": 0.9, "applied": True, "sampled": True},
                "Speaker2": {"name": "李主讲", "confidence": 0.4, "applied": False, "sampled": True},
            },
            "low_confidence": ["Speaker2"],
        }
        inferencer = _make_inferencer(cached_mapping=cached_v1)
        inferencer.llm_client.call = MagicMock(side_effect=AssertionError("must not call LLM"))

        result = inferencer.infer(
            speakers=self.speakers,
            dialogs=self.dialogs,
            title=FIXTURE_TITLE,
            author=FIXTURE_AUTHOR,
            description=FIXTURE_DESCRIPTION,
            platform="p",
            media_id="m",
        )

        inferencer.llm_client.call.assert_not_called()
        self.assertEqual(result["source"], "cache_hit")
        # conf=0.9 >= 0.6 → applied；conf=0.4 < 0.6 → 旧降级语义「说话人N」。
        self.assertEqual(result["mapping"]["Speaker1"], "张主持")
        self.assertEqual(result["mapping"]["Speaker2"], "说话人2")
        self.assertIn("Speaker2", result["low_confidence"])

    def test_v2_cached_artifact_replays_verdict_directly(self):
        """v2 产物缓存命中：证据裁决结论无法离线重核（输入全文不在缓存），
        直接采用缓存 mapping/applied，不发起 LLM 调用。"""
        cached_v2 = {
            "mapping": {
                "Speaker1": "说话人1｜作者关联推测:林晚风｜对话称:风哥",
                "Speaker2": "说话人2｜标题关联推测:青柠｜对话称:柠姐",
            },
            "meta": {
                "Speaker1": {
                    "name": "林晚风",
                    "confidence": 0.42,
                    "applied": True,
                    "sampled": True,
                    "candidates": [],
                    "verified_candidates": [
                        {"name": "林晚风", "evidence_type": "author_host"},
                    ],
                },
                "Speaker2": {
                    "name": "柠姐",
                    "confidence": 0.1,
                    "applied": True,
                    "sampled": True,
                    "candidates": [],
                    "verified_candidates": [
                        {"name": "柠姐", "evidence_type": "dialog_address"},
                    ],
                },
            },
            "low_confidence": [],
        }
        inferencer = _make_inferencer(cached_mapping=cached_v2)
        inferencer.llm_client.call = MagicMock(side_effect=AssertionError("must not call LLM"))

        result = inferencer.infer(
            speakers=self.speakers,
            dialogs=self.dialogs,
            title=FIXTURE_TITLE,
            author=FIXTURE_AUTHOR,
            description=FIXTURE_DESCRIPTION,
            platform="p",
            media_id="m",
        )

        inferencer.llm_client.call.assert_not_called()
        self.assertEqual(result["source"], "cache_hit")
        self.assertEqual(
            result["mapping"]["Speaker2"],
            "说话人2｜标题关联推测:青柠｜对话称:柠姐",
        )
        self.assertTrue(result["meta"]["Speaker2"]["applied"])

    def test_dialog_quote_without_name_rejected(self):
        """gate 修复轮第 4 轮（correctness-dialog-candidate-name-not-bound-to-
        quote）：归属核对只证明 quote 属于该说话人，不证明 quote 支持该姓名。
        quote 真实存在于说话人自身片段但不含候选名 → 候选作废、降级说话人N，
        作废原因记 name_not_in_quote。"""
        quote = "先说结论：三十天拉新一万这件事，没有捷径，全是重复劳动。"
        # 前提自证：quote 真实存在于 Speaker2 自身片段（排除假红——若采样没
        # 覆盖该句，候选会挂在分区核对 quote_missing 而非本判据）。
        inferencer = _make_inferencer()
        sample_groups = inferencer._extract_sample_dialogs(self.dialogs, self.speakers)
        seg2 = inferencer._render_speaker_segment("Speaker2", sample_groups["Speaker2"])
        self.assertIn(quote, seg2)
        self.assertNotIn("某主播", quote)

        candidates = {
            "Speaker2": [_candidate("某主播", "dialog_address", quote)],
        }
        result = self._run_infer(candidates, confidence={"Speaker1": 0.9, "Speaker2": 0.9})

        self.assertEqual(result["mapping"]["Speaker2"], "说话人2")
        self.assertFalse(result["meta"]["Speaker2"]["applied"])
        self.assertEqual(
            result["meta"]["Speaker2"]["rejection_reason"], "name_not_in_quote"
        )

    def test_dialog_quote_containing_name_still_applies(self):
        """第 4 轮对照：quote 含候选名本身（合成 fixture 中「柠姐」在 Speaker2
        片段内的自我介绍句）→ applied 保持，新判据不误伤真证据。"""
        quote = "大家好，我是柠姐，麦能听到了吗？"
        candidates = {
            "Speaker2": [_candidate("柠姐", "dialog_address", quote)],
        }
        result = self._run_infer(candidates, confidence={"Speaker1": 0.9, "Speaker2": 0.9})

        self.assertEqual(result["mapping"]["Speaker2"], "柠姐")
        self.assertTrue(result["meta"]["Speaker2"]["applied"])


class TestGateRound2QuoteScope(unittest.TestCase):
    """gate 修复轮第 2 轮：dialog_address 的 quote 核对收窄到该说话人自身的
    采样片段与出场上下文（correctness-speaker-evidence-quote-scope 跨说话人
    借用 + correctness-static-label-evidence-quote 联合兜住）。"""

    def setUp(self):
        self.dialogs = _load_fixture_dialogs()
        self.speakers = ["Speaker1", "Speaker2"]
        inferencer = _make_inferencer()
        self.sample_groups = inferencer._extract_sample_dialogs(self.dialogs, self.speakers)
        self.seg1 = inferencer._render_speaker_segment("Speaker1", self.sample_groups["Speaker1"])
        self.seg2 = inferencer._render_speaker_segment("Speaker2", self.sample_groups["Speaker2"])

    def test_dialog_quote_borrowed_from_other_speaker_rejected(self):
        """跨说话人借用：他人出场上下文里的称呼引用不得作为本说话人的
        dialog_address 证据。fixture 上「柠姐，我邀请你做共同主持人了」只
        出现在 Speaker2 的出场上下文（Speaker1 说出的、归属 Speaker2 的称呼
        证据）；Speaker1 自身片段里虽含「陈柠姐」字样但无此句（前提自证，
        排除假红）。收窄前 quote 对全转录区核对会放行，Speaker1 被误标「柠姐」。"""
        quote = "柠姐，我邀请你做共同主持人了"
        self.assertIn(quote, self.seg2)
        self.assertNotIn(quote, self.seg1)

        candidates = {
            "Speaker1": [_candidate("柠姐", "dialog_address", quote)],
            "Speaker2": [_candidate("柠姐", "dialog_address", quote)],
        }
        _, result = _run_infer_with(candidates, {"Speaker1": 0.9, "Speaker2": 0.9})

        # 跨说话人借用：Speaker1 的候选作废、降级「说话人1」，meta 记 quote_missing。
        self.assertEqual(result["mapping"]["Speaker1"], "说话人1")
        self.assertFalse(result["meta"]["Speaker1"]["applied"])
        self.assertEqual(result["meta"]["Speaker1"]["rejection_reason"], "quote_missing")
        # 正例对照：同一 quote 对归属说话人（出场上下文所在者）核对通过 applied。
        self.assertEqual(result["mapping"]["Speaker2"], "柠姐")
        self.assertTrue(result["meta"]["Speaker2"]["applied"])

    def test_static_evidence_only_never_applies(self):
        """联合兜住：三类静态行证据全部核对通过（quote 逐字存在于对应静态行，
        防幻觉核对保持）、无任何 dialog_address → 永不 applied。静态行核对与
        per-speaker 收窄正交：title_credit/author_host/description_roster 仍按
        静态分区核对，静态证据永远不足以单独支撑显示名（不变式轴表：无佐证的
        标题名不得 applied）。"""
        candidates = {
            "Speaker2": [
                _candidate("青柠", "title_credit", "青柠专场"),
                _candidate("林晚风", "author_host", FIXTURE_AUTHOR),
                _candidate("小满", "description_roster", "小满"),
            ],
        }
        _, result = _run_infer_with(candidates, {"Speaker1": 0.9, "Speaker2": 0.9})

        self.assertEqual(result["mapping"]["Speaker2"], "说话人2")
        self.assertFalse(result["meta"]["Speaker2"]["applied"])
        # 三条静态行 quote 均真实 → 核对全部通过（收窄不波及静态行），
        # 但裁决拒绝：拒绝原因是标题名缺对话佐证。
        self.assertEqual(len(result["meta"]["Speaker2"]["verified_candidates"]), 3)
        self.assertEqual(
            result["meta"]["Speaker2"]["rejection_reason"],
            "title_credit_without_dialog_support",
        )


class _FingerprintAwareCache:
    """按 (platform, media_id, input_fingerprint) 精确模拟真实 CacheManager 的
    指纹敏感命中行为：v2 起 input_fingerprint 是缓存 payload 字段，值变即 miss
    （真实读侧见 CacheManager.get_speaker_mapping 的指纹比对）。"""

    def __init__(self):
        self.store = {}
        self.saved_fingerprints = []

    def get_speaker_mapping(self, platform, media_id, input_fingerprint="", speakers=None):
        return self.store.get((platform, media_id, input_fingerprint))

    def save_speaker_mapping(self, platform, media_id, result, input_fingerprint="", speakers=None, source=""):
        self.saved_fingerprints.append(input_fingerprint)
        self.store[(platform, media_id, input_fingerprint)] = {
            "mapping": dict(result["mapping"]),
            "meta": json.loads(json.dumps(result["meta"])),
            "low_confidence": list(result["low_confidence"]),
        }


class TestMetadataChangeMissesCache(unittest.TestCase):
    """correctness-metadata-fingerprint-order（第 2 轮）：元数据变 → 指纹变 →
    旧映射不命中重算，锁为 spec（实现侧已两次被主审驳回改动，按门禁规则以
    回归测试锁定预期行为：指纹含 title/author/description，元数据变化必须
    触发缓存 miss 与 LLM 重算）。"""

    def _make(self):
        inferencer = _make_inferencer()
        cache = _FingerprintAwareCache()
        inferencer.cache_manager = cache
        calls = {"n": 0}

        def fake_llm_call(**kwargs):
            calls["n"] += 1
            return _mock_llm(
                {
                    "speaker_mapping": {"Speaker1": "林晚风", "Speaker2": "柠姐"},
                    "confidence": {"Speaker1": 0.9, "Speaker2": 0.9},
                    "candidates": {},
                    "reasoning": "mock",
                }
            )

        inferencer.llm_client.call = MagicMock(side_effect=fake_llm_call)
        return inferencer, cache, calls

    def test_metadata_change_misses_cache_and_reinfers(self):
        inferencer, cache, calls = self._make()
        base = dict(
            speakers=["Speaker1", "Speaker2"],
            dialogs=_load_fixture_dialogs(),
            platform="twitter_space",
            media_id="1wxWjlzQVwDJQ",
        )

        r1 = inferencer.infer(title="T1", author="A1", description="D1", **base)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(r1["source"], "llm")

        # 同元数据再次推断：指纹相同 → 缓存命中，不再调 LLM（对照，排除
        # 「永远 miss」的恒真假绿）。
        r2 = inferencer.infer(title="T1", author="A1", description="D1", **base)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(r2["source"], "cache_hit")

        # title 变 → miss 重算
        r3 = inferencer.infer(title="T2", author="A1", description="D1", **base)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(r3["source"], "llm")
        # author 变 → miss 重算
        inferencer.infer(title="T2", author="A2", description="D1", **base)
        self.assertEqual(calls["n"], 3)
        # description 变 → miss 重算
        inferencer.infer(title="T2", author="A2", description="D2", **base)
        self.assertEqual(calls["n"], 4)

        # 四次真实推断的写侧指纹互不相同（元数据组合两两有差异）。
        self.assertEqual(len(set(cache.saved_fingerprints)), 4)


class TestEvidenceGateRules(unittest.TestCase):
    """裁决规则的确定性分支（直接驱动 _verify_candidates/_decide_display_name）。"""

    def test_description_roster_alone_never_applies(self):
        """参会名单核对通过也不得单独 applied（名单≠发言人）。"""
        verified, rejected = SpeakerInferencer._verify_candidates(
            [_candidate("小满", "description_roster", "小满")],
            {"description_roster": "描述：…小满…"},
        )
        self.assertEqual(len(verified), 1)
        name, reason = SpeakerInferencer._decide_display_name(
            verified, "Speaker2", ["Speaker2"]
        )
        self.assertIsNone(name)
        self.assertEqual(reason, "description_roster_not_standalone")

    def test_title_credit_without_dialog_support_rejected(self):
        verified, _ = SpeakerInferencer._verify_candidates(
            [_candidate("青柠", "title_credit", "青柠专场")],
            {"title_credit": "标题：…青柠专场…"},
        )
        name, reason = SpeakerInferencer._decide_display_name(
            verified, "Speaker2", ["Speaker2"]
        )
        self.assertIsNone(name)
        self.assertEqual(reason, "title_credit_without_dialog_support")

    def test_dialog_address_alone_applies_directly(self):
        verified, _ = SpeakerInferencer._verify_candidates(
            [_candidate("柠姐", "dialog_address", "今天是柠姐的专场")],
            {"dialog_address": "…今天是柠姐的专场…"},
        )
        name, reason = SpeakerInferencer._decide_display_name(
            verified, "Speaker2", ["Speaker2"]
        )
        self.assertEqual(name, "柠姐")
        self.assertIsNone(reason)

    def test_composite_format_is_exact(self):
        """title_credit + dialog_address → 带标注复合名（gate 修复轮第 3 轮①：
        三要素缺一不可——说话人编号、「推测」字样、两条来源名）。"""
        verified, _ = SpeakerInferencer._verify_candidates(
            [
                _candidate("青柠", "title_credit", "青柠专场"),
                _candidate("柠姐", "dialog_address", "柠姐"),
            ],
            {"title_credit": "标题：…青柠专场…", "dialog_address": "对话…柠姐…"},
        )
        name, reason = SpeakerInferencer._decide_display_name(
            verified, "Speaker2", ["Speaker2"]
        )
        self.assertIsNone(reason)
        self.assertEqual(name, "说话人2｜标题关联推测:青柠｜对话称:柠姐")

    def test_unknown_evidence_type_rejected(self):
        verified, rejected = SpeakerInferencer._verify_candidates(
            [_candidate("张三", "vibes", "张三")],
            {"dialog_address": "张三"},
        )
        self.assertEqual(verified, [])
        self.assertEqual(rejected, ["unknown_evidence_type"])

    def test_partial_quote_substring_is_enough(self):
        """quote 是输入的逐字子串即可（不要求整行/整段）。"""
        verified, _ = SpeakerInferencer._verify_candidates(
            [_candidate("柠姐", "dialog_address", "柠姐，我邀请你")],
            {"dialog_address": "开场：柠姐，我邀请你做共同主持人了……"},
        )
        self.assertEqual(len(verified), 1)

    def test_whitespace_and_punctuation_only_quotes_all_rejected(self):
        """修复①边界值：纯空白/纯标点（含长度>=2 的多标点串）一律
        quote_missing；带实质字符的才放行。"""
        for quote in ("\u3000\u3000", "\u201c\u201d", "，", "，。", " 。 "):
            verified, rejected = SpeakerInferencer._verify_candidates(
                [_candidate("张三", "dialog_address", quote)],
                {"dialog_address": f"对话{quote}后文"},
            )
            self.assertEqual(verified, [], f"quote={quote!r} should be rejected")
            self.assertEqual(rejected, ["quote_missing"])
        # 对照：去首尾空白后有实质内容的 quote 放行（逐字存在性仍用原文核对）。
        verified, _ = SpeakerInferencer._verify_candidates(
            [_candidate("张三", "dialog_address", " 张三 ")],
            {"dialog_address": "对话 张三 后文"},
        )
        self.assertEqual(len(verified), 1)

    def test_dialog_name_binding_case_insensitive_for_english(self):
        """修复④（第 4 轮）边界：dialog_address 的 quote 必须包含候选名本身，
        英文名忽略大小写（ADRIAN PUNK 支持 Adrian Punk）；不含名的真实
        quote 对该名字无证据力 → name_not_in_quote。"""
        verified, rejected = SpeakerInferencer._verify_candidates(
            [_candidate("Adrian Punk", "dialog_address", "welcome, ADRIAN PUNK speaking")],
            {"dialog_address": "welcome, ADRIAN PUNK speaking"},
        )
        self.assertEqual(len(verified), 1)
        self.assertEqual(rejected, [])

        verified, rejected = SpeakerInferencer._verify_candidates(
            [_candidate("张三", "dialog_address", "今天天气不错")],
            {"dialog_address": "今天天气不错"},
        )
        self.assertEqual(verified, [])
        self.assertEqual(rejected, ["name_not_in_quote"])

    def test_quote_in_wrong_section_rejected(self):
        """修复②边界：quote 只存在于另一分区/分区缺失时，逐字存在也不放行。"""
        verified, rejected = SpeakerInferencer._verify_candidates(
            [_candidate("望舒", "dialog_address", "望舒")],
            {"description_roster": "- 描述：…望舒…"},
        )
        self.assertEqual(verified, [])
        self.assertEqual(rejected, ["quote_missing"])
        # 分区缺失（如空描述不进 prompt）→ fail-closed。
        verified, rejected = SpeakerInferencer._verify_candidates(
            [_candidate("青柠", "title_credit", "青柠专场")],
            {},
        )
        self.assertEqual(verified, [])
        self.assertEqual(rejected, ["quote_missing"])


class TestInputFingerprintExtension(unittest.TestCase):
    """锁定决策 5：指纹纳入 title/author/description/规则版本，唯此一处实现。"""

    DIALOGS = [{"speaker": "Speaker1", "text": "hello", "start_time": 0.0}]
    SPEAKERS = ["Speaker1"]

    def test_signature_has_metadata_keyword_params(self):
        """Accept-Check：签名参数 >= 3（keyword 参数扩展）。"""
        sig = inspect.signature(SpeakerInferencer.input_fingerprint)
        self.assertGreaterEqual(len(sig.parameters), 3)
        for param in ("title", "author", "description", "rules_version"):
            self.assertIn(param, sig.parameters)
            self.assertTrue(sig.parameters[param].kind in (inspect.Parameter.KEYWORD_ONLY,))

    def test_metadata_change_changes_fingerprint(self):
        base = SpeakerInferencer.input_fingerprint(self.SPEAKERS, self.DIALOGS, title="t1")
        self.assertNotEqual(
            base,
            SpeakerInferencer.input_fingerprint(self.SPEAKERS, self.DIALOGS, title="t2"),
        )
        self.assertNotEqual(
            base,
            SpeakerInferencer.input_fingerprint(
                self.SPEAKERS, self.DIALOGS, title="t1", author="someone"
            ),
        )
        self.assertNotEqual(
            base,
            SpeakerInferencer.input_fingerprint(
                self.SPEAKERS, self.DIALOGS, title="t1", description="new desc"
            ),
        )

    def test_rules_version_change_changes_fingerprint(self):
        base = SpeakerInferencer.input_fingerprint(
            self.SPEAKERS, self.DIALOGS, rules_version=SPEAKER_EVIDENCE_RULES_VERSION
        )
        self.assertNotEqual(
            base,
            SpeakerInferencer.input_fingerprint(
                self.SPEAKERS, self.DIALOGS, rules_version=SPEAKER_EVIDENCE_RULES_VERSION + 1
            ),
        )

    def test_fingerprint_is_stable_and_default_compatible(self):
        """同输入指纹稳定；不带 keyword 的旧调用形态等价于显式空元数据。"""
        a = SpeakerInferencer.input_fingerprint(self.SPEAKERS, self.DIALOGS, title="t")
        b = SpeakerInferencer.input_fingerprint(self.SPEAKERS, self.DIALOGS, title="t")
        self.assertEqual(a, b)
        self.assertEqual(
            SpeakerInferencer.input_fingerprint(self.SPEAKERS, self.DIALOGS),
            SpeakerInferencer.input_fingerprint(
                self.SPEAKERS, self.DIALOGS, title="", author="", description=""
            ),
        )


class TestCompositeNameSemantics(unittest.TestCase):
    """gate 修复轮第 3 轮①：复合显示名语义显式化。

    契约（主脑续修指令锁定）：含 title_credit/author_host 的复合 mapping 值
    三要素缺一不可——原始说话人编号、「推测」字样、两条来源名；标题名与
    对话称呼是否同一人是模型推测，程序只核实引用存在与分区归属，因此
    复合名必须就地自证推测属性，禁止裸标题名/作者名。仅 dialog_address
    的 mapping 值保持对话称呼原文（可证实事实，不标注）。
    """

    def _verified(self, credit_type="title_credit"):
        verified, rejected = SpeakerInferencer._verify_candidates(
            [
                _candidate("青柠" if credit_type == "title_credit" else "林晚风", credit_type, "原文引用"),
                _candidate("柠姐", "dialog_address", "柠姐"),
            ],
            {
                "title_credit": "标题：…青柠专场…原文引用…",
                "author_host": "作者：…林晚风…原文引用…",
                "dialog_address": "对话…柠姐…",
            },
        )
        self.assertEqual(rejected, [])
        self.assertEqual(len(verified), 2)
        return verified

    def test_title_composite_has_speaker_number_and_marker_and_both_names(self):
        name, reason = SpeakerInferencer._decide_display_name(
            self._verified("title_credit"), "Speaker2", ["Speaker1", "Speaker2"]
        )
        self.assertIsNone(reason)
        for element in ("说话人2", "推测", "青柠", "柠姐"):
            self.assertIn(element, name)
        self.assertEqual(name, "说话人2｜标题关联推测:青柠｜对话称:柠姐")

    def test_author_composite_marker(self):
        name, reason = SpeakerInferencer._decide_display_name(
            self._verified("author_host"), "Speaker1", ["Speaker1", "Speaker2"]
        )
        self.assertIsNone(reason)
        for element in ("说话人1", "推测", "林晚风", "柠姐"):
            self.assertIn(element, name)
        self.assertEqual(name, "说话人1｜作者关联推测:林晚风｜对话称:柠姐")

    def test_composite_never_bare_credit_name(self):
        """反例锁定：双证据时绝不允许返回裸标题名/作者名（无标注形态）。"""
        for credit_type in ("title_credit", "author_host"):
            name, _ = SpeakerInferencer._decide_display_name(
                self._verified(credit_type), "Speaker2", ["Speaker2"]
            )
            self.assertIn("推测", name)
            self.assertNotEqual(name, "青柠")
            self.assertNotEqual(name, "林晚风")
            self.assertNotEqual(name, "柠姐")

    def test_non_numeric_label_uses_position_number(self):
        """原始标签无数字时（如 FunASR 通道的「说话人A」），复合名按
        speakers 列表位次编号，与降级占位符同一套编号规则。"""
        verified = self._verified("title_credit")
        name, _ = SpeakerInferencer._decide_display_name(
            verified, "说话人B", ["说话人A", "说话人B"]
        )
        self.assertTrue(name.startswith("说话人2｜"), name)

    def test_wrong_credit_association_still_annotated_end_to_end(self):
        """反例（主脑续修指令①）：真实引用 + 错误关联——dialog_address 真
        （Guest 的对话称呼），title_credit 标给无标题关联的普通说话人。
        程序无法验证语义关联，因此显示名必须带「推测」标注而非裸名。"""
        dialogs = [
            {"speaker": "Speaker1", "text": "欢迎来到今晚的直播", "start_time": 0.0},
            {"speaker": "Speaker2", "text": "大家好我是小张，今天来串门", "start_time": 1.0},
            {"speaker": "Speaker1", "text": "小张请坐", "start_time": 2.0},
        ]
        inferencer = _make_inferencer()
        inferencer.llm_client.call = MagicMock(
            return_value=_mock_llm(
                {
                    "speaker_mapping": {"Speaker1": "小张", "Speaker2": "青柠"},
                    "confidence": {"Speaker1": 0.9, "Speaker2": 0.9},
                    "candidates": {
                        "Speaker2": [
                            _candidate("小张", "dialog_address", "小张"),
                            # 语义错误关联：小张与标题专场毫无关系，但 quote 逐字真实。
                            _candidate("青柠", "title_credit", "青柠专场"),
                        ],
                    },
                    "reasoning": "mock",
                }
            )
        )
        result = inferencer.infer(
            speakers=["Speaker1", "Speaker2"],
            dialogs=dialogs,
            title="青柠专场：夜话电台",
        )

        display = result["mapping"]["Speaker2"]
        # 不允许裸名（无论裸标题名还是裸对话称呼）：推测必须就地可见。
        self.assertNotEqual(display, "小张")
        self.assertNotEqual(display, "青柠")
        for element in ("说话人2", "推测", "青柠", "小张"):
            self.assertIn(element, display)
        self.assertTrue(result["meta"]["Speaker2"]["applied"])


class TestCompositeNameDownstreamSurfaces(unittest.TestCase):
    """gate 修复轮第 3 轮①：复合名是单一事实源——归一化对话（网页渲染、
    导出文本、LLM 后续输入的共同上游）原样携带复合名，渲染层不二次加工。"""

    COMPOSITE = "说话人2｜标题关联推测:青柠｜对话称:柠姐"

    def test_web_html_contains_all_composite_elements(self):
        """网页渲染：结构化数据里 dialogs.speaker 已是复合名，HTML 必须
        同时含「说话人2」「推测」「青柠」「柠姐」四要素（转义不改中文字面）。"""
        import tempfile

        from video_transcript_api.utils.rendering.dialog_renderer import DialogRenderer

        payload = {
            "dialogs": [
                {
                    "segment_id": "seg-1",
                    "speaker": self.COMPOSITE,
                    "speaker_id": "Speaker2",
                    "text": "大家好",
                    "start_time": "00:00:01",
                }
            ],
            "speaker_mapping": {"Speaker2": self.COMPOSITE},
        }
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "render"
            cache_dir.mkdir()
            (cache_dir / "llm_processed.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            html_out = DialogRenderer()._render_from_structured_data(str(cache_dir))

        for element in ("说话人2", "推测", "青柠", "柠姐"):
            self.assertIn(element, html_out)
        # 复合名自带推测标注，不再触发「待确认」badge（全串锚定匹配不命中）。
        self.assertNotIn('data-speaker-status="pending"', html_out)

    def test_normalized_dialogs_carry_composite_verbatim(self):
        """导出/后续输入上游：processor 归一化对话原样携带复合名，
        speaker_id 保留原始标签（映射关系可追溯）。"""
        from video_transcript_api.llm.processors.speaker_aware_processor import (
            SpeakerAwareProcessor,
        )

        processor = SpeakerAwareProcessor.__new__(SpeakerAwareProcessor)
        dialogs = [
            {
                "speaker": "Speaker2",
                "text": "大家好",
                "start_time": "00:00:01",
                "end_time": "00:00:02",
            }
        ]
        normalized = processor._normalize_and_merge_dialogs(
            dialogs, {"Speaker2": self.COMPOSITE}, has_speaker=True
        )
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["speaker"], self.COMPOSITE)
        self.assertEqual(normalized[0]["speaker_id"], "Speaker2")


class TestPlatformSpeakerPriors(unittest.TestCase):
    """gate 修复轮第 5 轮③：平台说话人先验。

    契约：表内平台（twitter_space）在视频信息区追加先验段；表外平台/未传
    platform 与旧输出逐字一致（零变化）；先验段只进 prompt 展示、不进任何
    引用分区（从先验文案摘 quote 会被逐字核对 fail-closed 作废）；规则版本
    随先验上线 bump 3→4。
    """

    def _build(self, platform=""):
        from video_transcript_api.llm.prompts import (
            PLATFORM_SPEAKER_PRIORS,
            build_speaker_inference_user_prompt,
        )

        return build_speaker_inference_user_prompt(
            context_snippets="[Speaker1]：你好",
            original_speakers=["Speaker1"],
            video_title="标题",
            author="作者",
            description="描述",
            platform=platform,
        ), PLATFORM_SPEAKER_PRIORS

    def test_prior_injected_for_known_platform(self):
        prompt, priors = self._build(platform="twitter_space")
        self.assertIn(priors["twitter_space"], prompt)
        # 先验段位置：位于元数据区内（描述行之后、转录片段区之前）。
        self.assertIn(priors["twitter_space"], prompt.split("**转录内容片段**")[0])

    def test_unknown_or_missing_platform_output_unchanged(self):
        """表外平台零变化：不传 platform、传空串、传未知平台三种形态的
        prompt 与旧（无先验）输出逐字一致。"""
        from video_transcript_api.llm.prompts import build_speaker_inference_user_prompt

        legacy = build_speaker_inference_user_prompt(
            context_snippets="[Speaker1]：你好",
            original_speakers=["Speaker1"],
            video_title="标题",
            author="作者",
            description="描述",
        )
        for platform in ("", "youtube", "bilibili"):
            self.assertEqual(
                self._build(platform=platform)[0],
                legacy,
                f"platform={platform!r} 的 prompt 与旧输出不一致",
            )

    def test_prior_never_enters_quote_sections(self):
        """先验段不是证据：不进 build_speaker_quote_sections 任何分区，
        从先验文案摘 quote 会被 fail-closed 作废。"""
        from video_transcript_api.llm.prompts import (
            PLATFORM_SPEAKER_PRIORS,
            build_speaker_quote_sections,
        )

        sections = build_speaker_quote_sections(
            video_title="标题",
            author="作者",
            description="描述",
            context_snippets="[Speaker1]：你好",
        )
        prior = PLATFORM_SPEAKER_PRIORS["twitter_space"]
        for evidence_type, text in sections.items():
            self.assertNotIn(prior, text)
            self.assertNotIn("平台背景", text)

    def test_rules_version_bumped_to_4(self):
        """先验与旁证上线属裁决规则变化：v3→v4，旧缓存经指纹自然失效。"""
        self.assertEqual(SPEAKER_EVIDENCE_RULES_VERSION, 4)


if __name__ == "__main__":
    unittest.main()
