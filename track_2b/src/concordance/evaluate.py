"""Evaluation on corruption-injected ground truth.

Positives = corrupted articles, negatives = untouched clean controls.
Reported per detector mode:
  precision / recall / F1 / false-positive rate     (article level: was it flagged?)
  typed recall        flagged AND a divergence of the injected type was reported
  attribution         among typed hits, the reported language-at-fault includes the corrupted one
  per-type recall     detect and typed, for each injected divergence type
  cost                tokens per model, calls, escalation rate, 8B-equivalent cost proxy
"""
from __future__ import annotations

import time
from collections import Counter, defaultdict

from .corrupt import INJECT_TYPES, EvalCase
from .detector import Detector

# Cost proxy: price per token scales with parameter count (70B / 8B).
COST_RATIO = 70 / 8


def _safe(n, d):
    return n / d if d else 0.0


def _score_mode(cases: list, results: list) -> dict:
    tp = fp = fn = tn = 0
    s_tp = s_fp = s_fn = s_tn = 0          # strict: only confirmed (or model-only) findings count
    fp_types = Counter()
    typed = attributed = 0
    per_type = defaultdict(lambda: {"n": 0, "detected": 0, "typed": 0})
    rows = []
    for case, res in zip(cases, results):
        pred_types = sorted({d.type for d in res.divergences})
        flagged = res.flagged
        strict = any(d.verdict in (None, "confirmed") for d in res.divergences)
        row = {"case_id": case.case_id, "gold": case.gold, "flagged": flagged,
               "pred_types": pred_types, "max_severity": res.max_severity,
               "llm_status": res.llm_status, "escalated": res.escalated}
        if case.gold:
            t = case.gold["type"]
            per_type[t]["n"] += 1
            if flagged:
                tp += 1
                per_type[t]["detected"] += 1
                hit = [d for d in res.divergences if d.type == t]
                if hit:
                    typed += 1
                    per_type[t]["typed"] += 1
                    if any(case.gold["lang"] in d.languages_at_fault for d in hit):
                        attributed += 1
                row["typed_hit"] = bool(hit)
            else:
                fn += 1
            s_tp += strict
            s_fn += not strict
        else:
            if flagged:
                fp += 1
                fp_types.update({d.type for d in res.divergences})
            else:
                tn += 1
            s_fp += strict
            s_tn += not strict
        rows.append(row)
    prec = _safe(tp, tp + fp)
    rec = _safe(tp, tp + fn)
    return {
        "strict": {"precision": _safe(s_tp, s_tp + s_fp), "recall": _safe(s_tp, s_tp + s_fn),
                   "f1": _safe(2 * _safe(s_tp, s_tp + s_fp) * _safe(s_tp, s_tp + s_fn),
                               _safe(s_tp, s_tp + s_fp) + _safe(s_tp, s_tp + s_fn)),
                   "false_positive_rate": _safe(s_fp, s_fp + s_tn)},
        "false_positives_by_type": dict(fp_types.most_common()),
        "n_positive": tp + fn, "n_negative": fp + tn, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": prec, "recall": rec,
        "f1": _safe(2 * prec * rec, prec + rec),
        "false_positive_rate": _safe(fp, fp + tn),
        "typed_recall": _safe(typed, tp + fn),
        "attribution_accuracy": _safe(attributed, typed),
        "per_type": {t: {**v, "recall": _safe(v["detected"], v["n"]),
                         "typed_recall": _safe(v["typed"], v["n"])}
                     for t, v in per_type.items()},
        "llm_unavailable": sum(1 for r in results if r.llm_status == "unavailable"),
        "parse_errors": sum(1 for r in results if r.llm_status == "parse_error"),
        "escalation_rate": _safe(sum(1 for r in results if r.escalated), len(results)),
        "rows": rows,
    }


def _usage_delta(before: dict, after: dict) -> dict:
    out = {}
    for model, a in after.items():
        b = before.get(model, {})
        out[model] = {k: a[k] - b.get(k, 0) for k in a}
    return out


def run_eval(cfg, llm, cases: list, modes: list, workers: int = 4) -> tuple:
    """Returns (report, results_by_mode). `report` is JSON-serialisable."""
    arts = [c.as_article() for c in cases]
    report = {"n_cases": len(cases), "modes": {}, "types": list(INJECT_TYPES)}
    all_results = {}
    for mode in modes:
        det = Detector(cfg, llm, mode)
        before = llm.snapshot() if llm else {}
        t0 = time.time()
        results = det.analyze_many(arts, workers=workers, label=f"eval:{mode}")
        all_results[mode] = results
        elapsed = time.time() - t0
        usage = _usage_delta(before, llm.snapshot()) if llm else {}
        m = _score_mode(cases, results)
        small = usage.get(cfg.small_model, {})
        large = usage.get(cfg.large_model, {})
        tok_s = small.get("prompt_tokens", 0) + small.get("completion_tokens", 0)
        tok_l = large.get("prompt_tokens", 0) + large.get("completion_tokens", 0)
        m["cost"] = {
            "tokens_small": tok_s, "tokens_large": tok_l,
            "calls_small": small.get("calls", 0), "calls_large": large.get("calls", 0),
            "cost_units_8b_equiv": tok_s + COST_RATIO * tok_l,
            "tokens_per_article": _safe(tok_s + tok_l, len(cases)),
            "wall_seconds_this_run": round(elapsed, 1),
        }
        report["modes"][mode] = m
    return report, all_results


def to_markdown(report: dict) -> str:
    modes = list(report["modes"])
    lines = [f"**Evaluation set:** {report['n_cases']} cases "
             f"({next(iter(report['modes'].values()))['n_positive']} corrupted, "
             f"{next(iter(report['modes'].values()))['n_negative']} clean)\n",
             "| Mode | Precision | Recall | F1 | FPR | Typed recall | Attribution | Escalated | Cost (8B-eq tokens) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for m in modes:
        r = report["modes"][m]
        lines.append(f"| {m} | {r['precision']:.2f} | {r['recall']:.2f} | {r['f1']:.2f} | "
                     f"{r['false_positive_rate']:.2f} | {r['typed_recall']:.2f} | "
                     f"{r['attribution_accuracy']:.2f} | {r['escalation_rate']:.0%} | "
                     f"{r['cost']['cost_units_8b_equiv']:,.0f} |")
    lines += ["", "**Strict operating point** (only findings the 70B confirmed; 'needs a human decision' ones excluded)", "",
              "| Mode | Precision | Recall | F1 | FPR |", "|---|---|---|---|---|"]
    for m in modes:
        s = report["modes"][m]["strict"]
        lines.append(f"| {m} | {s['precision']:.2f} | {s['recall']:.2f} | {s['f1']:.2f} | {s['false_positive_rate']:.2f} |")
    lines += ["", "**Which divergence types raise false alarms on clean articles**", ""]
    for m in modes:
        fpt = report["modes"][m]["false_positives_by_type"]
        lines.append(f"- {m}: " + (", ".join(f"{t}={n}" for t, n in fpt.items()) or "none"))
    lines += ["", "**Recall by injected divergence type**", "",
              "| Type | n | " + " | ".join(modes) + " |", "|---|---|" + "---|" * len(modes)]
    for t in report["types"]:
        n = next((report["modes"][m]["per_type"].get(t, {}).get("n", 0) for m in modes), 0)
        if not n:
            continue
        cells = [f"{report['modes'][m]['per_type'].get(t, {}).get('recall', 0):.2f}" for m in modes]
        lines.append(f"| {t} | {n} | " + " | ".join(cells) + " |")
    unavailable = {m: report["modes"][m]["llm_unavailable"] for m in modes if report["modes"][m]["llm_unavailable"]}
    if unavailable:
        lines += ["", f"> **Warning:** model responses were unavailable for some cases ({unavailable}). "
                      "Run once with `CSCS_API_KEY` set to record them (see README)."]
    return "\n".join(lines)
