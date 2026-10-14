"""Export the evaluation set in the three-part layout the hackathon asks for.

  evaluation_dataset.jsonl   individual test cases (texts + gold label)
  model_responses.jsonl      what each detector mode answered for every case (incl. raw model output)
  metadata.jsonl             per-case provenance and instance-level licensing

IMPORTANT: copy these into a clone of the HackApertus dataset template
(huggingface.co/datasets/HackApertus/online_hack_template) and complete ITS dataset card;
the README.md written here is only a starting point and may not match the template's fields.
"""
from __future__ import annotations

import json
from pathlib import Path


def _write_jsonl(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def export(out_dir: Path, cases: list, results_by_mode: dict, corpus_meta: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "evaluation_dataset.jsonl", [{
        "case_id": c.case_id, "act_id": c.act_id, "article": c.num, "texts": c.texts,
        "label": "corrupted" if c.gold else "clean",
        "gold_divergence_type": c.gold["type"] if c.gold else None,
        "gold_language_corrupted": c.gold["lang"] if c.gold else None,
    } for c in cases])

    resp = []
    for mode, results in results_by_mode.items():
        for c, r in zip(cases, results):
            resp.append({"case_id": c.case_id, "mode": mode, "flagged": r.flagged,
                         "llm_status": r.llm_status, "escalated": r.escalated,
                         "divergences": [d.to_dict() for d in r.divergences],
                         "refuted_candidates": [d.to_dict() for d in r.rejected],
                         "raw_model_output": r.trace})
    _write_jsonl(out_dir / "model_responses.jsonl", resp)

    synthetic = bool(corpus_meta.get("synthetic"))
    _write_jsonl(out_dir / "metadata.jsonl", [{
        "case_id": c.case_id, "act_id": c.act_id, "article": c.num,
        "source_urls": c.sources, "source_retrieved": corpus_meta.get("created"),
        "source_license": ("CC0-1.0 (synthetic text invented for this project)" if synthetic else
                           "Swiss federal law text (Fedlex). Official legislative texts; re-use with source "
                           "attribution. VERIFY against fedlex.admin.ch terms before publishing."),
        "derivative_license": "CC-BY-4.0",
        "modification": c.gold,           # exact corruption applied (before/after snippet), or null
        "contains_personal_data": False,
    } for c in cases])

    n_bad = sum(1 for c in cases if c.gold)
    (out_dir / "README.md").write_text(f"""---
license: cc-by-4.0
task_categories: [text-classification]
language: [de, fr, it]
pretty_name: Concordance trilingual divergence benchmark
---
# Concordance: trilingual divergence benchmark (DRAFT CARD)

{len(cases)} cases ({n_bad} with one deliberately corrupted language version, {len(cases) - n_bad} clean controls).
Each case is one article of Swiss federal law in German, French and Italian.

**Corpus:** {corpus_meta.get('name')}{' (synthetic, not Swiss law)' if synthetic else ''}.
**Construction:** corruptions (number, unit, date, modality, negation, quantifier, reference, terminology)
are applied programmatically to ONE language; the exact change is in `metadata.jsonl` under `modification`.
**Files:** `evaluation_dataset.jsonl`, `model_responses.jsonl`, `metadata.jsonl`.

**Limitations:** injected errors are cleaner than real ones; clean controls may themselves contain real
(unknown) divergences, which would count as false positives.

TODO before publishing: complete the HackApertus dataset-card template fields; confirm source licensing.
""", encoding="utf-8")
    return out_dir
