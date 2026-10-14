"""Command line: python -m concordance <command>."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import ROOT, load_config
from .corrupt import INJECT_TYPES, build_eval_set
from .detector import MODES, Detector
from .evaluate import run_eval, to_markdown
from .fedlex import fetch_act, load_corpus, load_xml_dir, save_corpus
from .llm import LLMClient, LLMError
from .report import build_report, write_summary

PRESET_ACTS = ["235.1", "172.021", "221.229.1"]   # verify these SR numbers on fedlex.admin.ch


def _llm(cfg):
    urls = {cfg.large_model: cfg.large_base_url} if cfg.large_base_url else None
    return LLMClient(cfg.base_url, cfg.api_key, cfg.llm_mode, cfg.cache_dir, model_urls=urls)


def resolve_corpus(arg: str | None) -> Path:
    import os
    if arg:
        return Path(arg)
    env = os.environ.get("CONCORDANCE_CORPUS")
    if env:
        return Path(env)
    found = sorted((ROOT / "data" / "corpus").glob("*.json"))
    if found:
        return found[0]
    return ROOT / "data" / "demo" / "synthetic_corpus.json"


def _banner(cfg, corpus: Path, meta: dict) -> None:
    net = "no network (replay from cache)" if cfg.llm_mode == "replay" else f"LIVE calls to {cfg.base_url}"
    print(f"Concordance {__version__} | LLM mode: {cfg.llm_mode}: {net}")
    print(f"Corpus: {corpus.name}" + ("  [SYNTHETIC demo data, not Swiss law]" if meta.get("synthetic") else ""))
    print(f"Models: small={cfg.small_model}  large={cfg.large_model}")


# ------------------------------------------------------------------ commands
def cmd_models(args, cfg):
    cfg.llm_mode = "live"
    ids = _llm(cfg).list_models()
    print("Models available on the endpoint:")
    for i in ids:
        print("  ", i)
    print("\nPut the exact ids in .env as APERTUS_SMALL_MODEL and APERTUS_LARGE_MODEL.")


def cmd_doctor(args, cfg):
    """Check key, endpoint and model names before spending any budget."""
    cfg.llm_mode = "live"
    key = cfg.api_key
    print(f"Endpoint : {cfg.base_url}")
    print(f"API key  : {'set (' + key[:4] + '…' + key[-2:] + ')' if len(key) > 8 else ('set' if key else 'NOT SET')}")
    print(f"Small    : {cfg.small_model}\nLarge    : {cfg.large_model}")
    llm = _llm(cfg)
    try:
        ids = llm.list_models()
    except Exception as e:
        sys.exit(f"\nCould not list models: {type(e).__name__}: {e}\nCheck CSCS_API_KEY and network.")
    print(f"\n{len(ids)} models on the endpoint:")
    for i in ids:
        print("   ", i)
    ok = True
    for label, model in (("small", cfg.small_model), ("large", cfg.large_model)):
        if model not in ids:
            ok = False
            print(f"\n!! {label} model '{model}' is not in that list. Edit .env "
                  f"(APERTUS_{label.upper()}_MODEL) to one of the ids above.")
            continue
        try:
            r = llm.chat(model, [{"role": "user", "content": "Reply with the single word OK."}], max_tokens=8)
            print(f"\n{label} model answered: {r.text.strip()[:40]!r}  ({r.prompt_tokens}+{r.completion_tokens} tokens)")
        except Exception as e:
            ok = False
            print(f"\n!! {label} model call failed: {e}")
    print("\nAll good." if ok else "\nFix the items marked !! and run doctor again.")


def cmd_ingest(args, cfg):
    acts = []
    if args.xml_dir:
        acts = load_xml_dir(Path(args.xml_dir))
    else:
        srs = args.sr or (PRESET_ACTS if args.preset else [])
        if not srs:
            sys.exit("Give --sr 235.1 (repeatable), --preset, or --xml-dir.")
        for sr in srs:
            print(f"Fetching SR {sr} ...")
            try:
                acts.append(fetch_act(sr, raw_dir=ROOT / "data" / "raw", debug=True))
            except Exception as e:
                print(f"  FAILED: {type(e).__name__}: {str(e)[:260]}\n  Fallback: download the XML per language from fedlex.admin.ch and use --xml-dir.")
    if not acts:
        sys.exit("No acts ingested.")
    for a in acts:
        print(f"  {a['act_id']}: {len(a['articles'])} aligned articles, {len(a['unaligned'])} unaligned")
    out = Path(args.out) if args.out else ROOT / "data" / "corpus" / f"{args.name}.json"
    save_corpus(out, args.name, acts)
    print("Wrote", out)


def cmd_analyze(args, cfg):
    corpus = resolve_corpus(args.corpus)
    meta, arts = load_corpus(corpus, args.max_articles)
    _banner(cfg, corpus, meta)
    llm = None if args.mode == "rules" else _llm(cfg)
    res = Detector(cfg, llm, args.mode).analyze_many(arts, workers=cfg.workers)
    _finish_analysis(cfg, meta, res, args.mode, llm, eval_report=None, eval_md=None)


def _finish_analysis(cfg, meta, results, mode, llm, eval_report, eval_md):
    out = cfg.out_dir
    out.mkdir(parents=True, exist_ok=True)
    stats = {"n_articles": len(results), "mode": mode, "llm_mode": cfg.llm_mode,
             "llm_unavailable": sum(1 for r in results if r.llm_status == "unavailable"),
             "usage": llm.snapshot() if llm else {}}
    (out / "findings.json").write_text(json.dumps(
        {"meta": meta, "stats": stats, "results": [r.to_dict() for r in results]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    html = build_report(out, meta, results, stats, eval_report)
    write_summary(out, meta, results, stats, eval_md)
    flagged = [r for r in results if r.flagged]
    print(f"\nChecked {len(results)} articles, flagged {len(flagged)}.")
    for r in sorted(flagged, key=lambda x: ["critical", "high", "medium", "low"].index(x.max_severity))[:12]:
        print(f"  [{r.max_severity:<8}] {r.act_id} {r.num}: " + ", ".join(sorted({d.type for d in r.divergences})))
    print(f"\nReview UI : {html}\nSummary   : {out / 'summary.md'}\nFindings  : {out / 'findings.json'}")


def _run_eval(args, cfg, arts, meta, llm):
    # Articles with known planted divergences (synthetic corpus) must not serve as clean controls.
    cases = build_eval_set(arts, seed=cfg.seed, max_per_type=args.max_per_type,
                           exclude_art_ids=set((meta or {}).get("planted", {})))
    modes = [m for m in args.modes.split(",") if m]
    bad = [m for m in modes if m not in MODES]
    if bad:
        sys.exit(f"Unknown mode(s): {bad}. Choose from {MODES}")
    print(f"\nEvaluation: {len(cases)} cases, modes={modes}")
    report, by_mode = run_eval(cfg, llm, cases, modes, workers=cfg.workers)
    return cases, report, by_mode


def cmd_eval(args, cfg):
    corpus = resolve_corpus(args.corpus)
    meta, arts = load_corpus(corpus, args.max_articles)
    _banner(cfg, corpus, meta)
    llm = _llm(cfg)
    cases, report, by_mode = _run_eval(args, cfg, arts, meta, llm)
    _save_eval(cfg, cases, report, by_mode, meta)


def _save_eval(cfg, cases, report, by_mode, meta):
    out = cfg.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "eval_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "eval_cases.json").write_text(json.dumps([c.to_dict() for c in cases], ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    details = {}
    for mode, results in by_mode.items():
        details[mode] = {c.case_id: {
            "gold": c.gold, "flagged": r.flagged, "llm_status": r.llm_status,
            "divergences": [{k: d.to_dict()[k] for k in ("type", "severity", "verdict", "verdict_reason", "explanation",
                                                         "spans", "origins", "languages_at_fault")} for d in r.divergences],
            "rejected": [{k: d.to_dict()[k] for k in ("type", "verdict_reason", "explanation", "spans", "origins")}
                         for d in r.rejected]} for c, r in zip(cases, results)}
    (out / "eval_details.json").write_text(json.dumps(details, ensure_ascii=False, indent=1), encoding="utf-8")
    md = to_markdown(report)
    (out / "eval_table.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    return md


def cmd_demo(args, cfg):
    """What `make run` executes: analyse the corpus, evaluate all modes, build the review UI."""
    corpus = resolve_corpus(args.corpus)
    meta, arts = load_corpus(corpus, args.max_articles)
    _banner(cfg, corpus, meta)
    llm = _llm(cfg)
    print("\n[1/2] Analysing corpus with the cascade ...")
    res = Detector(cfg, llm, "cascade").analyze_many(arts, workers=cfg.workers, label="analyze")
    print("[2/2] Evaluating detectors on injected ground truth ...")
    cases, report, by_mode = _run_eval(args, cfg, arts, meta, llm)
    md = _save_eval(cfg, cases, report, by_mode, meta)
    _finish_analysis(cfg, meta, res, "cascade", llm, report, md)
    if cfg.llm_mode == "replay" and any(r.llm_status == "unavailable" for r in res):
        print("\nNOTE: some model responses were not in the cache, so those results come from the rule stage "
              "only. Record them once with:  python -m concordance demo --llm-mode live")


def cmd_export(args, cfg):
    from .export_hf import export
    corpus = resolve_corpus(args.corpus)
    meta, arts = load_corpus(corpus, args.max_articles)
    llm = _llm(cfg)
    cases, report, by_mode = _run_eval(args, cfg, arts, meta, llm)
    path = export(Path(args.out), cases, by_mode, meta)
    print("Exported dataset files to", path)


# ------------------------------------------------------------------ parser
def build_parser():
    p = argparse.ArgumentParser(prog="concordance", description=__doc__)
    p.add_argument("--llm-mode", choices=["auto", "live", "replay"], default=None,
                   help="auto = live if CSCS_API_KEY is set, else replay from cache")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, eval_opts=False):
        sp.add_argument("--corpus", help="corpus JSON (default: data/corpus/*.json, else synthetic demo)")
        sp.add_argument("--max-articles", type=int, default=None, help="cap articles per act")
        if eval_opts:
            sp.add_argument("--modes", default=",".join(MODES))
            sp.add_argument("--max-per-type", type=int, default=12)

    sub.add_parser("models", help="list models on the CSCS endpoint").set_defaults(fn=cmd_models)
    sub.add_parser("doctor", help="check API key, endpoint and model names").set_defaults(fn=cmd_doctor)

    sp = sub.add_parser("ingest", help="fetch acts from Fedlex into a corpus file")
    sp.add_argument("--sr", action="append", help="SR number, e.g. 235.1 (repeatable)")
    sp.add_argument("--preset", action="store_true", help=f"ingest {PRESET_ACTS}")
    sp.add_argument("--xml-dir", help="folder with manually downloaded <name>_de.xml/_fr.xml/_it.xml")
    sp.add_argument("--name", default="fedlex_demo")
    sp.add_argument("--out")
    sp.set_defaults(fn=cmd_ingest)

    sp = sub.add_parser("analyze", help="check a corpus and build the review UI")
    common(sp)
    sp.add_argument("--mode", choices=MODES, default="cascade")
    sp.set_defaults(fn=cmd_analyze)

    sp = sub.add_parser("eval", help="evaluate detector modes on injected ground truth")
    common(sp, True)
    sp.set_defaults(fn=cmd_eval)

    sp = sub.add_parser("demo", help="analyse + evaluate + build UI (what `make run` does)")
    common(sp, True)
    sp.set_defaults(fn=cmd_demo)

    sp = sub.add_parser("export-hf", help="write the 3-part Hugging Face dataset files")
    common(sp, True)
    sp.add_argument("--out", default=str(ROOT / "out" / "hf_dataset"))
    sp.set_defaults(fn=cmd_export)
    return p


def _hoist_llm_mode(argv: list) -> list:
    """Allow `--llm-mode X` anywhere on the command line (argparse wants it before the command)."""
    argv = list(argv)
    for i, a in enumerate(argv):
        if a == "--llm-mode" and i + 1 < len(argv):
            return argv[i:i + 2] + argv[:i] + argv[i + 2:]
        if a.startswith("--llm-mode="):
            return [a] + argv[:i] + argv[i + 1:]
    return argv


def main(argv=None) -> int:
    argv = _hoist_llm_mode(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    cfg = load_config(llm_mode=args.llm_mode)
    try:
        args.fn(args, cfg)
    except LLMError as e:
        sys.exit(f"LLM error: {e}")
    return 0
