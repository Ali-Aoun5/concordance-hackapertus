import json
from concordance.detector import Detector, quote_in_text
from concordance.llm import LLMClient, LLMResult, CacheMiss, parse_json, make_key
from concordance.models import AlignedArticle

class FakeLLM(LLMClient):
    """Answers triage/verify prompts from canned JSON, counting calls per model."""
    def __init__(self, triage, verify):
        self.triage, self.verify, self.calls = triage, verify, []
        self.counters = {}
    def snapshot(self): return {}
    def chat(self, model, messages, temperature=0.0, max_tokens=1400):
        last = messages[-1]["content"]
        kind = "verify" if "A first-pass analysis flagged" in last else "triage"
        self.calls.append((kind, model))
        out = self.verify if kind == "verify" else self.triage
        return LLMResult(json.dumps(out), 10, 10, False, model, "k")

def art(demo, art_id):
    meta, arts = demo
    return next(a for a in arts if a.art_id == art_id)

def test_parse_json_variants():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure! {"a": [1,2,],}') == {"a": [1, 2]}
    assert parse_json("no json") is None

def test_quote_grounding():
    assert quote_in_text("innert 60 Tagen", "Die Behörde entscheidet innert 60 Tagen nach")
    assert not quote_in_text("innert 90 Tagen", "Die Behörde entscheidet innert 60 Tagen nach")

def test_cache_roundtrip_and_replay_miss(tmp_path):
    msgs = [{"role": "user", "content": "x"}]
    live = LLMClient("http://x", "", "replay", tmp_path)
    try:
        live.chat("m", msgs); assert False
    except CacheMiss:
        pass
    key = make_key("m", msgs, 0.0, 1400)
    (tmp_path / "m.jsonl").write_text(json.dumps({"key": key, "response": "hi", "prompt_tokens": 3, "completion_tokens": 1}) + "\n")
    r = LLMClient("http://x", "", "replay", tmp_path).chat("m", msgs)
    assert r.text == "hi" and r.cached

def test_cascade_confirms_and_skips_clean_articles(demo, cfg):
    triage = {"consistent": True, "divergences": []}
    verify = {"verdicts": [{"index": 0, "verdict": "confirmed", "reason": "FR says must.", "severity": "critical",
                            "suggestion": "L'autorité peut refuser"}], "additional": []}
    llm = FakeLLM(triage, verify)
    det = Detector(cfg, llm, "cascade")
    clean = det.analyze(art(demo, "art_1"))
    assert not clean.flagged and not clean.escalated
    assert [c for c in llm.calls if c[0] == "verify"] == []          # 70B untouched
    bad = det.analyze(art(demo, "art_4"))
    assert bad.escalated and bad.flagged
    d = bad.divergences[0]
    assert d.verdict == "confirmed" and d.suggestion and d.source == "cascade"
    assert ("verify", cfg.large_model) in llm.calls

def test_model_only_candidate_refuted_goes_to_audit_trail(demo, cfg):
    triage = {"consistent": False, "divergences": [{"type": "other", "languages_at_fault": ["it"],
              "quotes": {}, "explanation": "odd", "severity": "low"}]}
    verify = {"verdicts": [{"index": 0, "verdict": "refuted", "reason": "style only"}], "additional": []}
    r = Detector(cfg, FakeLLM(triage, verify), "cascade").analyze(art(demo, "art_1"))
    assert not r.flagged and len(r.rejected) == 1

def test_refuted_reliable_rule_candidate_is_kept_as_uncertain(demo, cfg):
    verify = {"verdicts": [{"index": 0, "verdict": "refuted", "reason": "style only", "severity": "low"}],
              "additional": []}
    r = Detector(cfg, FakeLLM({"consistent": True, "divergences": []}, verify), "cascade").analyze(art(demo, "art_5"))
    assert r.flagged and not r.rejected
    d = r.divergences[0]
    assert d.type == "number" and d.verdict == "uncertain" and "kept for human review" in d.verdict_reason
    assert d.severity == "critical"          # the verifier's "low" must not downgrade a reliable finding

def test_refuted_noisy_rule_candidate_is_dropped(demo, cfg):
    verify = {"verdicts": [{"index": 0, "verdict": "refuted", "reason": "same force"}], "additional": []}
    r = Detector(cfg, FakeLLM({"consistent": True, "divergences": []}, verify), "cascade").analyze(art(demo, "art_4"))
    assert not r.flagged and len(r.rejected) == 1

def test_verifier_can_add_missed_divergence(demo, cfg):
    verify = {"verdicts": [], "additional": [{"type": "omission", "languages_at_fault": ["it"],
              "quotes": {"it": "dal ricevimento della domanda completa"}, "explanation": "x", "severity": "high"}]}
    llm = FakeLLM({"consistent": False, "divergences": [{"type": "other", "languages_at_fault": ["it"],
                   "quotes": {}, "explanation": "odd", "severity": "low"}]}, verify)
    r = Detector(cfg, llm, "cascade").analyze(art(demo, "art_1"))
    assert any(d.type == "omission" and d.verdict == "confirmed" for d in r.divergences)

def test_missing_cache_degrades_to_rules(demo, cfg):
    llm = LLMClient("http://x", "", "replay", cfg.cache_dir)
    r = Detector(cfg, llm, "cascade").analyze(art(demo, "art_5"))
    assert r.flagged and r.llm_status == "unavailable"        # rules still flag it
    r2 = Detector(cfg, llm, "llm8").analyze(art(demo, "art_5"))
    assert not r2.flagged and r2.llm_status == "unavailable"

def test_ungrounded_quote_lowers_confidence(demo, cfg):
    triage = {"consistent": False, "divergences": [{"type": "number", "languages_at_fault": ["it"],
              "quotes": {"it": "entro 99 giorni"}, "explanation": "x", "severity": "high"}]}
    r = Detector(cfg, FakeLLM(triage, {}), "llm8").analyze(art(demo, "art_5"))
    assert r.divergences[0].grounded is False and r.divergences[0].confidence <= 0.35


def test_merge_handles_several_model_only_candidates(demo, cfg):
    """Regression: model-only candidates of types the rules did not raise used to crash _merge."""
    triage = {"consistent": False, "divergences": [
        {"type": "omission", "languages_at_fault": ["it"], "quotes": {}, "explanation": "a", "severity": "low"},
        {"type": "other", "languages_at_fault": ["fr"], "quotes": {}, "explanation": "b", "severity": "low"},
        {"type": "omission", "languages_at_fault": ["de"], "quotes": {}, "explanation": "c", "severity": "low"}]}
    verify = {"verdicts": [], "additional": []}
    r = Detector(cfg, FakeLLM(triage, verify), "cascade").analyze(art(demo, "art_4"))   # art_4 also has a rule candidate
    assert r.escalated and r.llm_status == "ok"
