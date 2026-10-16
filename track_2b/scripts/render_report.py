"""Write technical_report.md from scripts/report_template.md using the real results in out/.

    python scripts/render_report.py --team "Ali Aoun Mehdi" --video "https://youtu.be/..." --dataset "https://huggingface.co/datasets/..."

Every number in the report comes from out/eval_results.json and out/findings.json, so the text can
never disagree with what `make run` prints. Run it again after any new evaluation run.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from concordance.cli import resolve_corpus  # noqa: E402

TYPE_ORDER = ["number", "unit", "date", "reference", "negation", "modality", "quantifier", "terminology"]


def f2(x):
    return f"{x:.2f}"


def pct(x):
    return f"{round(100 * x)}%"


def ratio(a, b):
    return a / b if b else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", default="solo")
    ap.add_argument("--video", default="to be added")
    ap.add_argument("--dataset", default="not published")
    ap.add_argument("--out", default=str(ROOT / "technical_report.md"))
    args = ap.parse_args()

    ev = json.loads((ROOT / "out" / "eval_results.json").read_text(encoding="utf-8"))
    fd = json.loads((ROOT / "out" / "findings.json").read_text(encoding="utf-8"))
    M = ev["modes"]
    ru, l8, l70, ca = M["rules"], M["llm8"], M["llm70"], M["cascade"]
    cs = ca["strict"]

    cost = lambda m: m["cost"]["cost_units_8b_equiv"]
    rows = [("Rules only", ru, ru), ("Apertus 8B", l8, l8), ("Apertus 70B on every article", l70, l70),
            ("**Cascade, strict**", ca, cs), ("Cascade, all findings", ca, ca)]
    main_table = ["| Setup | Precision | Recall | F1 | False alarms on clean | Cost |", "|---|---|---|---|---|---|"]
    for i, (name, m, s) in enumerate(rows):
        src = cs if "strict" in name else (ca if "all findings" in name else m)
        main_table.append(f"| {name} | {f2(src['precision'])} | {f2(src['recall'])} | {f2(src['f1'])} | "
                          f"{f2(src['false_positive_rate'])} | {cost(m):,.0f} |")

    types = [t for t in TYPE_ORDER + [t for t in ev["types"] if t not in TYPE_ORDER] if ru["per_type"].get(t, {}).get("n")]
    pt = ["| Type | n | Rules | Apertus 8B | Apertus 70B | Cascade |", "|---|---|---|---|---|---|"]
    for t in types:
        pt.append(f"| {t} | {ru['per_type'][t]['n']} | " + " | ".join(
            f2(M[m]["per_type"].get(t, {}).get("recall", 0)) for m in ("rules", "llm8", "llm70", "cascade")) + " |")

    flagged = [r for r in fd["results"] if r["flagged"]]
    divs = [d for r in flagged for d in r["divergences"]]
    tok = l8["cost"]["tokens_per_article"]
    corpus_meta = json.loads(resolve_corpus(None).read_text(encoding="utf-8")).get("meta", {})
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                cwd=ROOT).stdout.strip() or "unknown"
    except OSError:
        commit = "unknown"

    cost_ratio = ratio(cost(ca), cost(l70))
    dataset_given = args.dataset.strip().lower() not in ("", "not published")
    tokens = {
        "team": args.team, "video": args.video, "dataset": args.dataset, "commit": commit,
        "retrieved": corpus_meta.get("created", "unknown date"),
        "dataset_sentence": (" The test set and model answers are published on Hugging Face (link above) "
                             "under CC-BY-4.0.") if dataset_given else "",
        "n_cases": ev["n_cases"], "n_pos": ru["n_positive"], "n_neg": ru["n_negative"],
        "type_counts": ", ".join(f"{t} {ru['per_type'][t]['n']}" for t in types),
        "cs_p": f2(cs["precision"]), "cs_r": f2(cs["recall"]), "cs_f": f2(cs["f1"]),
        "rules_r": f2(ru["recall"]), "rules_f": f2(ru["f1"]), "rules_fpr_pct": pct(ru["false_positive_rate"]),
        "l70_fpr_pct": pct(l70["false_positive_rate"]), "l70_r_pct": pct(l70["recall"]), "l70_f": f2(l70["f1"]),
        "fpr_cut": round(100 * (ru["false_positive_rate"] - cs["false_positive_rate"]) / ru["false_positive_rate"])
        if ru["false_positive_rate"] else 0,
        "cost_pct": round(100 * cost_ratio), "saving_pct": 100 - round(100 * cost_ratio),
        "esc_pct": round(100 * ca["escalation_rate"]),
        "tok_per_art": f"{int(round(tok / 100) * 100):,}", "m_per_1000": f"{tok * 1000 / 1e6:.1f}",
        "n_real": fd["stats"]["n_articles"], "n_flagged": len(flagged), "n_findings": len(divs),
        "n_uncertain": sum(1 for d in divs if d.get("verdict") == "uncertain"),
        "fp_mod": ca["false_positives_by_type"].get("modality", 0),
        "cas_term": f2(ca["per_type"].get("terminology", {}).get("recall", 0)),
        "cas_quant": f2(ca["per_type"].get("quantifier", {}).get("recall", 0)),
        "main_table": "\n".join(main_table), "per_type_table": "\n".join(pt),
    }
    text = (ROOT / "scripts" / "report_template.md").read_text(encoding="utf-8")
    for k, v in tokens.items():
        text = text.replace("{{" + k + "}}", str(v))
    left = re.findall(r"\{\{\w+\}\}", text)
    if left:
        sys.exit(f"Unfilled tokens: {sorted(set(left))}")
    Path(args.out).write_text(text, encoding="utf-8")
    warn = ca["llm_unavailable"] or l70["llm_unavailable"] or l8["llm_unavailable"]
    print(f"Wrote {args.out}")
    print(f"  cascade strict: precision {cs['precision']:.2f}, recall {cs['recall']:.2f}, F1 {cs['f1']:.2f}, false alarms {cs['false_positive_rate']:.2f}")
    if warn:
        print("  WARNING: some model answers were missing from the cache in that run. Record them first (see instructions).")


if __name__ == "__main__":
    main()
