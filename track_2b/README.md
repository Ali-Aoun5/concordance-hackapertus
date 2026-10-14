# Concordance: cross-lingual consistency auditing for Swiss federal law

> Track 2B (Own Project), Hack Apertus Online. Built on **Apertus v1.5 8B + 70B**.

German, French and Italian versions of Swiss federal law are **equally authentic**. If they
diverge (one says *kann*, another *doit*; one says 30 days, another 60), that is a legal defect.
Today the check is largely manual. Concordance aligns the three versions article by article and
reports divergences in legal meaning, with evidence, severity, a proposed harmonised wording and a
human review workflow.

It is built for pre-publication legislative work, which cannot be sent to a foreign cloud:
it runs **air-gapped** on the 8B/70B models.

## Run it (judges)

Requires Docker only.

```bash
make run          # builds the image, runs with the network DISABLED, replays recorded Apertus answers
```

Then open **`out/review.html`** in a browser. Also written: `out/summary.md`, `out/eval_table.md`,
`out/eval_results.json`, `out/findings.json`.

`make run` uses `docker run --network none`: it proves nothing needs the internet. Every model response
behind the reported numbers is committed in `data/cache/*.jsonl` and replayed deterministically.
No API key is needed.

Fresh model calls (optional): copy `.env.example` to `.env`, set `CSCS_API_KEY`, then `make warm`.

## What it does

1. **Aligns** acts from Fedlex (Akoma Ntoso XML) on language-independent article ids; articles
   missing in a language are recorded as structural divergences.
2. **Rule engine** (no model): numbers (incl. Swiss `200’000` formats and spelled-out numbers), units,
   dates, cross-references, modal force (may / must / must not / need not), negation (ignores
   *ne … que* and *sans délai*), quantifiers, confusable legal concepts (creditor/debtor,
   employer/employee, fine/imprisonment, ...), length-ratio omissions. The odd-one-out language is
   attributed by majority vote.
3. **Apertus 8B triage** reads all three versions and proposes divergences as strict JSON with verbatim quotes.
4. **Apertus 70B verification** runs **only on articles that have candidates**. It confirms, refutes
   or marks uncertain, may add what the earlier stages missed, and proposes a harmonised wording.
5. **Hallucination guard:** every quoted span is checked against the source text; quotes not found
   verbatim are flagged and down-weighted.
6. **Review UI** (single offline HTML file): synoptic three-column view with highlighted spans,
   severity filters, confirm / dismiss / ask-expert decisions, CSV and JSON export, and an audit trail
   of what the verifier refuted.
7. **Evaluation harness:** corruption injection creates labelled data at scale from real articles
   (exact before/after logged); precision / recall / F1 / false-positive rate, per-type recall,
   language attribution, and cost for four modes: `rules`, `llm8`, `llm70`, `cascade`.

## Sovereign deployability

| Target | How |
|---|---|
| Air-gapped | `make run` (no network). Fresh analysis: local vLLM, see `docs/architecture.md` |
| On-premise | Same container plus the two model servers inside the organisation |
| Swiss sovereign cloud | CSCS Alps endpoint (used for development) |

## Commands

```bash
python -m concordance doctor                  # check key, endpoint, model names
python -m concordance ingest --sr 235.1       # fetch an act from Fedlex (or --preset, or --xml-dir)
python -m concordance analyze                 # analyse the corpus, build out/review.html
python -m concordance eval --max-per-type 25  # evaluation on injected ground truth
python -m concordance demo --max-articles 60  # analyse + evaluate + UI (what make run does)
python -m concordance export-hf               # dataset files for Hugging Face
make test                                     # unit tests
```

## Layout

```
src/concordance/   rules.py lexicon.py detector.py prompts.py llm.py corrupt.py evaluate.py
                   fedlex.py report.py export_hf.py cli.py templates/review.html
data/              corpus/ (Fedlex excerpt), cache/ (recorded Apertus responses), demo/ (synthetic)
docs/              architecture.md, figures/
tests/             rules, injection, Akoma Ntoso parsing, cascade logic (with a fake LLM)
technical_report.md
```

## Honest limitations

* Findings are **candidates for human review**, not legal conclusions.
* Injected errors are cleaner than real ones, and the rule engine and the injector share a lexicon, so
  **rule recall on injected data is optimistic**. The LLM stages do not share it; see the report.
* Clean controls may contain real, unknown divergences (counted as false positives).
* Romansh (the fourth language, partly authentic) is not covered.

## License

Code and data produced here: CC-BY-4.0, as required for HackApertus projects. Source texts are Swiss
federal legislation from Fedlex (cite source and date). The synthetic demo corpus is invented (CC0).
