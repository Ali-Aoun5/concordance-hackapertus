"""Explain what the cascade misses and what it wrongly flags.

Run after `python -m concordance demo ...`:   python scripts/diagnose.py
Reads out/eval_details.json and out/eval_cases.json. Paste the output to whoever is helping you tune it.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

out = Path(__file__).resolve().parents[1] / "out"
details = json.loads((out / "eval_details.json").read_text(encoding="utf-8"))
cases = {c["case_id"]: c for c in json.loads((out / "eval_cases.json").read_text(encoding="utf-8"))}
mode = sys.argv[1] if len(sys.argv) > 1 else "cascade"
rows = details[mode]


def strict(r):
    return any(d["verdict"] in (None, "confirmed") for d in r["divergences"])


print(f"=== MISSED by {mode} (strict), 2 examples per injected type ===")
shown = defaultdict(int)
for cid, r in rows.items():
    g = r["gold"]
    if not g or strict(r) or shown[g["type"]] >= 2:
        continue
    shown[g["type"]] += 1
    print(f"\n[{cid}] corrupted {g['lang'].upper()}:\n  before: {g['before']}\n  after : {g['after']}")
    for d in r["divergences"] + r["rejected"]:
        if d["type"] == g["type"]:
            print(f"  -> {d['type']} {d.get('verdict') or 'rejected'} | {d['explanation'][:110]}\n     verifier: {d['verdict_reason'][:260]}")
    if not (r["divergences"] or r["rejected"]):
        print("  -> nothing was raised for this case")

print(f"\n=== FALSE ALARMS by {mode} on CLEAN articles (strict) ===")
n = 0
for cid, r in rows.items():
    if r["gold"] or not strict(r):
        continue
    for d in r["divergences"]:
        if d["verdict"] in (None, "confirmed"):
            n += 1
            if n <= 12:
                ev = "; ".join(f"{l.upper()} '{s}'" for l, ss in d["spans"].items() for s in ss[:1])
                print(f"[{cid}] {d['type']} | {d['explanation'][:120]}\n   evidence: {ev[:200]}\n   verifier: {d['verdict_reason'][:200]}")
print(f"\n(total strict false alarms: {n})")
