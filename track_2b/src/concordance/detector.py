"""Detection pipeline.

Modes (all share one interface so they can be ablated against each other):

  rules    deterministic checks only
  llm8     small model reads all three versions                        (triage)
  llm70    large model reads all three versions                        (brute force)
  cascade  rules + small-model triage propose candidates; the large model
           verifies ONLY articles that have candidates, may refute or add.

The cascade is the production design: cheap recall first, expensive precision only where needed.
"""
from __future__ import annotations

import re
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from . import prompts
from .llm import CacheMiss, LLMClient, LLMError, parse_json
from .models import (DIVERGENCE_TYPES, LANGS, SEV_RANK, AlignedArticle, ArticleResult,
                     Divergence)
from .rules import rule_divergences

MODES = ("rules", "llm8", "llm70", "cascade")

# Types where the deterministic check is reliable on real law (numbers, units, dates,
# cross-references): a single model refutation must not silently delete them.
# Modality, negation, quantifiers and terminology are NOT here: on real Fedlex text the rule
# stage raised false alarms for most clean articles, and the 70B verifier is what removes them.
RULE_TRUSTED = {"number", "unit", "date", "reference"}

_TYPE_ALIASES = {
    "modal": "modality", "modal_verb": "modality", "modal force": "modality",
    "numeric": "number", "amount": "number", "deadline": "number",
    "negated": "negation", "quantity": "quantifier", "cross-reference": "reference",
    "cross_reference": "reference", "citation": "reference", "term": "terminology",
    "missing": "omission", "addition": "omission", "scope": "quantifier",
}


def norm_type(t) -> str:
    t = str(t or "other").strip().lower()
    t = _TYPE_ALIASES.get(t, t)
    return t if t in DIVERGENCE_TYPES else "other"


def norm_sev(s) -> str:
    s = str(s or "medium").strip().lower()
    return s if s in SEV_RANK else "medium"


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\u00a0", " ").strip().lower())


def quote_in_text(quote: str, text: str) -> bool:
    q = _norm_ws(quote).strip("“”\"'«» ")
    if not q:
        return True
    t = _norm_ws(text)
    parts = [p.strip() for p in re.split(r"…|\.\.\.", q) if len(p.strip()) >= 3]
    return all(p in t for p in parts) if parts else True


def _to_divergence(d: dict, texts: dict, source: str, conf: float) -> Optional[Divergence]:
    if not isinstance(d, dict):
        return None
    langs = []
    for l in d.get("languages_at_fault") or []:
        l = str(l).lower().strip()
        if l in LANGS and l not in langs:
            langs.append(l)
    quotes = d.get("quotes") if isinstance(d.get("quotes"), dict) else {}
    spans, checks = {}, []
    for l in LANGS:
        q = str(quotes.get(l) or quotes.get(l.upper()) or "").strip()
        spans[l] = [q] if q else []
        if q:
            checks.append(quote_in_text(q, texts.get(l, "")))
    grounded = all(checks) if checks else None
    return Divergence(
        type=norm_type(d.get("type")), languages_at_fault=langs or list(LANGS), spans=spans,
        explanation=str(d.get("explanation") or "").strip()[:600], severity=norm_sev(d.get("severity")),
        source=source, confidence=conf if grounded is not False else min(conf, 0.35),
        grounded=grounded, origins=[source])


def _absorb(base: Divergence, d: Divergence) -> None:
    for o in d.origins:
        if o not in base.origins:
            base.origins.append(o)
    for l in LANGS:
        for sp in d.spans.get(l, []):
            if sp and sp not in base.spans.setdefault(l, []):
                base.spans[l].append(sp)
    if d.source != "rules" and d.explanation:
        base.explanation = d.explanation
        base.grounded = d.grounded if d.grounded is not None else base.grounded
    base.confidence = min(0.99, max(base.confidence, d.confidence) + 0.1)
    if SEV_RANK[d.severity] > SEV_RANK[base.severity]:
        base.severity = d.severity
    if not set(d.languages_at_fault) >= set(LANGS):
        base.languages_at_fault = list(d.languages_at_fault)


def _unit_key(d: Divergence):
    return tuple(sorted(d.unit.items())) if d.unit else None


def _merge(rule_divs: list, model_divs: list) -> list:
    """Rule candidates stay separate per (type, sentence). A model candidate joins the first
    rule candidate of the same type, otherwise it stands alone."""
    merged: dict = {}
    for d in rule_divs:
        key = (d.type, _unit_key(d))
        if key in merged:
            _absorb(merged[key], d)
        else:
            merged[key] = d
    for d in model_divs:
        base = next((v for (t, _), v in merged.items() if t == d.type), None)
        if base is not None:
            _absorb(base, d)
        else:
            merged[(d.type, ("model", len(merged)))] = d
    return list(merged.values())


class Detector:
    def __init__(self, cfg, llm: Optional[LLMClient], mode: str = "cascade"):
        assert mode in MODES, mode
        self.cfg, self.llm, self.mode = cfg, llm, mode

    # ------------------------------------------------------------------ LLM stages
    def _triage(self, art: AlignedArticle, model: str, source: str):
        msgs = prompts.triage_messages(art.act_title, art.num, art.texts)
        try:
            res = self.llm.chat(model, msgs, max_tokens=1200)
        except (CacheMiss, LLMError) as e:
            return [], "unavailable", [{"stage": "triage", "model": model, "error": str(e)[:200]}]
        trace = [{"stage": "triage", "model": model, "key": res.key, "response": res.text,
                  "prompt_tokens": res.prompt_tokens, "completion_tokens": res.completion_tokens,
                  "cached": res.cached}]
        data = parse_json(res.text)
        if not isinstance(data, dict):
            return [], "parse_error", trace
        divs = [x for x in (_to_divergence(d, art.texts, source, 0.6)
                            for d in (data.get("divergences") or [])) if x]
        if data.get("consistent") is False and not divs:
            divs = [Divergence(type="other", languages_at_fault=list(LANGS), spans={l: [] for l in LANGS},
                               explanation="Model reported an inconsistency without detail.",
                               severity="medium", source=source, confidence=0.3, origins=[source])]
        return divs, "ok", trace

    def _verify(self, art: AlignedArticle, cands: list):
        model = self.cfg.large_model
        msgs = prompts.verify_messages(art.act_title, art.num, art.texts, [c.to_dict() for c in cands])
        try:
            res = self.llm.chat(model, msgs, max_tokens=1800)
        except (CacheMiss, LLMError) as e:
            return None, "unavailable", [{"stage": "verify", "model": model, "error": str(e)[:200]}]
        trace = [{"stage": "verify", "model": model, "key": res.key, "response": res.text,
                  "prompt_tokens": res.prompt_tokens, "completion_tokens": res.completion_tokens,
                  "cached": res.cached}]
        data = parse_json(res.text)
        if not isinstance(data, dict):
            return None, "parse_error", trace
        return data, "ok", trace

    # ------------------------------------------------------------------ modes
    def analyze(self, art: AlignedArticle) -> ArticleResult:
        r = ArticleResult(act_id=art.act_id, art_id=art.art_id, num=art.num, texts=art.texts,
                          mode=self.mode, act_title=art.act_title, sources=art.sources)
        if not all(art.texts.get(l, "").strip() for l in LANGS):
            return r
        small, large = self.cfg.small_model, self.cfg.large_model

        if self.mode == "rules":
            r.divergences = rule_divergences(art.texts)
            return r

        if self.mode in ("llm8", "llm70"):
            model, src = (small, "llm8") if self.mode == "llm8" else (large, "llm70")
            divs, status, trace = self._triage(art, model, src)
            r.divergences, r.llm_status, r.trace = divs, status, trace
            return r

        # cascade
        rule_divs = rule_divergences(art.texts)
        tri, status, trace = self._triage(art, small, "llm8")
        r.trace += trace
        cands = _merge(rule_divs, tri)
        r.llm_status = status
        if not cands:
            return r
        r.escalated = True
        data, vstatus, vtrace = self._verify(art, cands)
        r.trace += vtrace
        if data is None:
            r.llm_status = vstatus if status == "ok" else status
            for c in cands:
                c.source = "cascade"
            r.divergences = cands
            return r
        verdicts = {}
        for v in data.get("verdicts") or []:
            if isinstance(v, dict) and isinstance(v.get("index"), int):
                verdicts[v["index"]] = v
        for i, c in enumerate(cands):
            v = verdicts.get(i, {})
            verdict = str(v.get("verdict") or "uncertain").lower()
            verdict = verdict if verdict in ("confirmed", "refuted", "uncertain") else "uncertain"
            reason = str(v.get("reason") or "")[:400]
            overridden = False
            trusted = c.type in RULE_TRUSTED or (c.type == "quantifier" and c.severity == "critical")  # at least vs at most
            if verdict == "refuted" and "rules" in c.origins and trusted:
                overridden = True
                reason = ("The 70B verifier disagreed (" + reason + ") but the deterministic check is "
                          "reliable for this type, so it is kept for human review.")
                verdict = "uncertain"
            c.verdict, c.verdict_reason = verdict, reason
            if v.get("suggestion") and str(v["suggestion"]).lower() != "null" and not overridden:
                c.suggestion = str(v["suggestion"])[:500]
            if v.get("severity") and not overridden:     # a refuted finding's "low" must not downgrade a reliable one
                c.severity = norm_sev(v["severity"])
            c.source = "cascade"
            (r.rejected if verdict == "refuted" else r.divergences).append(c)
        for d in data.get("additional") or []:
            x = _to_divergence(d, art.texts, "llm70", 0.7)
            if x:
                x.verdict, x.source = "confirmed", "cascade"
                x.verdict_reason = "Added by the verifier."
                r.divergences.append(x)
        r.llm_status = "ok"
        return r

    def analyze_many(self, arts: list, workers: int = 4, label: str = "") -> list:
        total = len(arts)
        done = 0

        def run(a):
            nonlocal done
            res = self.analyze(a)
            done += 1
            if total >= 20 and (done % max(total // 10, 1) == 0 or done == total):
                print(f"  [{label or self.mode}] {done}/{total}", file=sys.stderr, flush=True)
            return res

        if self.mode == "rules" or workers <= 1:
            return [run(a) for a in arts]
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(run, arts))
