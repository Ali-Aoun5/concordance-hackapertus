# Technical report: Concordance

**Track:** Track 2B: Own Project
**Event:** Online
**Team:** `<<TEAM NAME>>`: Ali Aoun Mehdi
**Demo:** `<<LINK TO 2-MIN VIDEO>>`

> Fill every `<<...>>` from your real run before exporting to PDF (max 6 pages). Delete this note.

## 1. Summary

Swiss federal law exists in German, French and Italian, and all three versions are equally authentic;
a divergence in meaning between them is a legal defect that is today caught mostly by manual review.
Concordance aligns the versions article by article and flags divergences in legal meaning with verbatim
evidence, severity and a proposed harmonised wording. A cascade combines deterministic checks, a cheap
Apertus 8B triage pass and an Apertus 70B verifier that runs only on articles with candidates.
On `<<N>>` corruption-injected test cases the cascade reaches F1 `<<X>>` at `<<Y>>`% of the cost of running the
70B model on everything; on `<<M>>` real articles from `<<K>>` federal acts it surfaced `<<Z>>` candidate
divergences for review. It runs air-gapped.

## 2. Architecture

See `docs/architecture.md` for the diagram. Data flow: Fedlex Akoma Ntoso XML → corpus JSON (articles
aligned by language-independent `eId`) → rule engine and 8B triage in parallel → merged candidates →
70B verifier (only where candidates exist) → quote-grounding check → review UI. A disk cache of
model responses sits between the pipeline and the models, which makes every reported number replayable
without network access. Ingestion is a separate offline step; detection never touches the network.

## 3. Use of Apertus

**Models:** `<<exact ids from `doctor`, e.g. swiss-ai/Apertus-...-8B / -70B>>`.
**How it is used:** inference (triage, verification). Prompts are in `src/concordance/prompts.py`.

* **Triage (8B):** a system prompt framing the model as a Federal Chancellery legal-linguistic reviewer,
  two compact in-context examples (one divergence, one consistent pair), a typed divergence taxonomy and a
  strict JSON schema requiring verbatim quotes. Temperature 0.
* **Verification (70B):** receives the three texts plus numbered candidates (from rules or the 8B model,
  labelled by origin) and returns a verdict per candidate (confirmed / refuted / uncertain), a severity,
  a suggested harmonised wording, and any additional divergence it finds.
* **Why Apertus:** the task needs strong DE/FR/IT legal understanding and must run where legislative drafts
  cannot leave the organisation. Apertus is open, multilingual and deployable on-premise.
* **Serving:** CSCS OpenAI-compatible endpoint during development; local vLLM for on-prem / air-gapped use.
  Other open-weight models were `<<not used / used as ... (describe role)>>`.

## 4. Data

* **Real corpus:** `<<acts and SR numbers>>` from Fedlex (fedlex.admin.ch), consolidated versions in force
  on `<<retrieval date>>`, XML in DE/FR/IT. `<<N>>` aligned articles; `<<U>>` articles present in only some
  languages. Licence: official Swiss legislative texts, re-used with source attribution. `<<state the
  Fedlex terms you verified>>`.
* **Synthetic corpus** (`data/demo/`): invented text for smoke tests, CC0, clearly labelled, with planted errors.
* **Derived evaluation set:** real articles with ONE language version programmatically corrupted
  (number, unit, date, modality, negation, quantifier, cross-reference, terminology) plus untouched controls.
  The exact change is logged per case. Published on Hugging Face: `<<dataset URL>>`.
* No personal data. No human subjects.

## 5. Evaluation

**Protocol.** `<<N>>` cases: `<<P>>` corrupted (≤ `<<k>>` per type), `<<C>>` clean controls; seed 7.
Positives: article flagged. Typed recall: flagged and a divergence of the injected type reported.
Attribution: reported language-at-fault includes the corrupted language. Cost: tokens per model, 70B tokens
weighted 70/8 (a parameter-proportional proxy, not a price).

| Setup | Precision | Recall | F1 | FPR | Typed recall | Sent to 70B | Cost (8B-eq tokens) |
|---|---|---|---|---|---|---|---|
| Rules only (baseline) | `<<>>` | `<<>>` | `<<>>` | `<<>>` | `<<>>` | 0% | 0 |
| Apertus 8B | `<<>>` | `<<>>` | `<<>>` | `<<>>` | `<<>>` | 0% | `<<>>` |
| Apertus 70B (all articles) | `<<>>` | `<<>>` | `<<>>` | `<<>>` | `<<>>` | 100% | `<<>>` |
| **Cascade (ours)** | `<<>>` | `<<>>` | `<<>>` | `<<>>` | `<<>>` | `<<>>` | `<<>>` |

Figures (from `out/figures/`): recall by type, quality per mode, cost versus F1. `<<insert 2 to 3>>`

**Findings to discuss** (write what the data shows): where rules are strong (numbers, dates, references),
where only the LLM sees the problem (omissions, nuance), how the verifier changes precision, how many
8B-flagged candidates the 70B refutes, and the cost saved by escalating only where needed.

**Real-law results.** `<<N>>` candidates across `<<M>>` articles; `<<n>>` examined by `<<who>>`; examples:
`<<one or two concrete findings with quotes>>`. Present these as candidates, not as confirmed errors.

## 6. Limitations

* Findings are decision support for legal reviewers. A finding means the versions appear to differ; whether
  that is a defect is a legal judgement. Stylistic differences between languages can surface as false alarms.
* The injector and the rule engine share a lexicon, so rule recall on injected data is optimistic. The LLM
  stages are independent of it, and the real-law results are the more honest signal.
* Injected errors are cleaner than real ones. Clean controls may hide real divergences (counted as false positives).
* The author does not read all three languages; real-law findings were `<<validated how>>`.
* Romansh is not covered. Only article-level text is compared; tables and annexes are skipped.
* Small-model JSON output can fail; such cases are recorded as `parse_error` and fall back to the rule stage.

## 7. Reproducibility

* **Command:** `make run` (Docker only). Network disabled; replays `data/cache/*.jsonl`.
* **Hardware:** CPU only for replay. Fresh calls need CSCS access (or local GPUs: 8B ≈ one GPU, 70B ≈ four).
* **Determinism:** temperature 0, seed 7 for the injector, responses cached by SHA-256 of
  (model, messages, temperature, max_tokens).
* **Commit:** `<<git commit hash>>`. Tests: `make test` (35 passing).
* Prompt or corpus changes invalidate the cache; re-record with `make warm`.

## 8. Next steps

Scan the full Classified Compilation and publish a divergence atlas by legal domain; amendment mode that checks
whether an amendment changed all three languages equally; terminology-consistency checks across a whole act using
the federal terminology database; Romansh; a fine-tuned small verifier trained on confirmed cases; integration in
a drafting workflow with tracked decisions.

## License

Creative Commons Attribution 4.0 (CC-BY-4.0). All HackApertus projects are open-sourced.

## References

* Fedlex open data and SPARQL endpoint: https://fedlex.data.admin.ch
* Akoma Ntoso (OASIS LegalDocML) 3.0.
* Apertus v1.5 (swiss-ai): https://huggingface.co/swiss-ai
* `<<add any papers you cite, e.g. SwiLTra-Bench; Höfler and Sugisaki on Swiss legislative corpora>>`
