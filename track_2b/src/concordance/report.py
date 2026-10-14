"""Build the static review UI, figures and a markdown summary into out/."""
from __future__ import annotations

import base64
import json
import re
from collections import Counter
from pathlib import Path

TEMPLATE = Path(__file__).parent / "templates" / "review.html"
PALETTE = {"rules": "#7a8794", "llm8": "#6bb4e6", "llm70": "#0f5c8c", "cascade": "#b8571a"}


def _figures(report: dict, fig_dir: Path) -> dict:
    """Render PNG figures. Returns {name: base64}. Silently skips if matplotlib is missing."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed: skipping figures")
        return {}
    fig_dir.mkdir(parents=True, exist_ok=True)
    modes = list(report["modes"])
    out = {}
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

    # 1. recall by type
    types = [t for t in report["types"]
             if any(report["modes"][m]["per_type"].get(t, {}).get("n") for m in modes)]
    if types:
        fig, ax = plt.subplots(figsize=(9, 3.8))
        w = 0.8 / len(modes)
        for i, m in enumerate(modes):
            vals = [report["modes"][m]["per_type"].get(t, {}).get("recall", 0) for t in types]
            ax.bar([x + i * w for x in range(len(types))], vals, w, label=m,
                   color=PALETTE.get(m, "#999"))
        ax.set_xticks([x + w * (len(modes) - 1) / 2 for x in range(len(types))])
        ax.set_xticklabels(types, rotation=20)
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("Recall")
        ax.set_title("Recall by injected divergence type")
        ax.legend(frameon=False, ncol=len(modes))
        p = fig_dir / "recall_by_type.png"
        fig.tight_layout()
        fig.savefig(p, dpi=160)
        plt.close(fig)
        out["recall_by_type"] = base64.b64encode(p.read_bytes()).decode()

    # 2. precision / recall / FPR
    fig, ax = plt.subplots(figsize=(7, 3.6))
    metrics = [("precision", "Precision"), ("recall", "Recall"), ("false_positive_rate", "False-positive rate")]
    w = 0.8 / len(modes)
    for i, m in enumerate(modes):
        ax.bar([x + i * w for x in range(len(metrics))],
               [report["modes"][m][k] for k, _ in metrics], w, label=m, color=PALETTE.get(m, "#999"))
    ax.set_xticks([x + w * (len(modes) - 1) / 2 for x in range(len(metrics))])
    ax.set_xticklabels([n for _, n in metrics])
    ax.set_ylim(0, 1.05)
    ax.set_title("Detection quality per mode")
    ax.legend(frameon=False, ncol=len(modes))
    p = fig_dir / "quality_by_mode.png"
    fig.tight_layout()
    fig.savefig(p, dpi=160)
    plt.close(fig)
    out["quality_by_mode"] = base64.b64encode(p.read_bytes()).decode()

    # 3. cost vs F1
    fig, ax = plt.subplots(figsize=(6.4, 4))
    for m in modes:
        r = report["modes"][m]
        x = max(r["cost"]["cost_units_8b_equiv"], 1)
        ax.scatter(x, r["f1"], s=90, color=PALETTE.get(m, "#999"), zorder=3)
        ax.annotate(m, (x, r["f1"]), textcoords="offset points", xytext=(8, 6))
    ax.set_xscale("log")
    ax.set_xlabel("Cost (8B-equivalent tokens, log scale; 70B tokens weighted 70/8)")
    ax.set_ylabel("F1")
    ax.set_ylim(0, 1.05)
    ax.grid(alpha=.25)
    ax.set_title("Cost versus accuracy")
    p = fig_dir / "cost_vs_f1.png"
    fig.tight_layout()
    fig.savefig(p, dpi=160)
    plt.close(fig)
    out["cost_vs_f1"] = base64.b64encode(p.read_bytes()).decode()
    return out


_DATA_TAG = re.compile(r"(<script[^>]*\bid=[\"']data[\"'][^>]*>)\s*__DATA__\s*(</script>)", re.I)


def _inject(template: str, blob: str) -> str:
    """Put the JSON into <script id="data">__DATA__</script>. Other occurrences of the
    text __DATA__ (e.g. a 'is the placeholder still there?' check in the page's JS) are left alone."""
    new, n = _DATA_TAG.subn(lambda m: m.group(1) + blob + m.group(2), template, count=1)
    if n == 0:
        raise ValueError('review.html must contain <script id="data" type="application/json">__DATA__</script>')
    return new


def build_report(out_dir: Path, meta: dict, results: list, stats: dict, eval_report: dict | None,
                 fig_dir: Path | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    figures = _figures(eval_report, fig_dir or out_dir / "figures") if eval_report else {}

    flagged = []
    for r in results:
        if not r.flagged:
            continue
        d = r.to_dict()
        d.pop("trace", None)
        flagged.append(d)

    eval_slim = None
    if eval_report:
        eval_slim = json.loads(json.dumps(eval_report))
        for m in eval_slim["modes"].values():
            m.pop("rows", None)

    payload = {"meta": meta, "results": flagged, "stats": stats, "eval": eval_slim, "figures": figures}
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = _inject(TEMPLATE.read_text(encoding="utf-8"), blob)
    path = out_dir / "review.html"
    path.write_text(html, encoding="utf-8")
    return path


def write_summary(out_dir: Path, meta: dict, results: list, stats: dict, eval_md: str | None) -> Path:
    flagged = [r for r in results if r.flagged]
    sev = Counter(r.max_severity for r in flagged)
    types = Counter(d.type for r in flagged for d in r.divergences)
    lines = [f"# Concordance summary: {meta.get('name', 'corpus')}", ""]
    if meta.get("synthetic"):
        lines += ["> Synthetic demonstration corpus. Not Swiss law.", ""]
    lines += [f"- Articles checked: **{stats['n_articles']}**",
              f"- Articles flagged: **{len(flagged)}**",
              f"- Mode: `{stats['mode']}` (LLM mode: `{stats['llm_mode']}`)",
              f"- Severity: " + ", ".join(f"{k}={sev.get(k, 0)}" for k in ("critical", "high", "medium", "low")),
              f"- Types: " + (", ".join(f"{k}={v}" for k, v in types.most_common()) or "none"), ""]
    if stats.get("llm_unavailable"):
        lines += [f"> Model stage unavailable for {stats['llm_unavailable']} articles (no cached response "
                  "and no API key). Results for those articles come from the rule stage only.", ""]
    lines += ["## Findings", ""]
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for r in sorted(flagged, key=lambda x: order.get(x.max_severity, 9)):
        for d in r.divergences:
            ev = "; ".join(f"{l.upper()} “{s}”" for l, ss in d.spans.items() for s in ss[:1])
            lines.append(f"- **{r.act_id} {r.num}** [{d.severity}] {d.type}, at fault: "
                         f"{'/'.join(l.upper() for l in d.languages_at_fault)}. {d.explanation} "
                         f"({ev})" + (f" Verifier: {d.verdict}." if d.verdict else ""))
    if eval_md:
        lines += ["", "## Evaluation", "", eval_md]
    p = out_dir / "summary.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p
