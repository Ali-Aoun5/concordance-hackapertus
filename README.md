# Concordance: reading Swiss federal law in three languages at once

Track 2B (Own Project), Hack Apertus Online. Solo entry by Ali Aoun Mehdi.
Built on Apertus v1.5 8B and 70B.

Swiss federal law is authentic in German, French and Italian, with no single
original. If one version says an authority *may* act and another says it *must*,
the law says two things. Today this is caught mostly by manual review.
Concordance is a second pair of eyes: it points at where the three versions
appear to disagree. It does not decide which one is right.

## Run it

You need Docker only. No API key, no GPU and no network are needed.

```bash
make run
```

This builds the image and runs it with `--network none`, replaying the recorded
Apertus answers from `data/cache/`. Then open `out/review.html`. Also written:
`out/summary.md`, `out/eval_table.md`, `out/findings.json`.

No `make` (Windows)?
```powershell
docker build -t concordance .
docker run --rm --network none -v "${PWD}\out:/app/out" concordance
```

Results are the same on every run and with any Python hash seed. A fresh
clone gives the table in the report, with no missing model responses.
(An earlier version depended on set ordering; that is fixed on the
`post-deadline-fixes` branch.)

## How it works

1. **Align** the three language versions by article id (Fedlex Akoma Ntoso XML).
2. **Rules** (no model): numbers, units, dates, cross-references, modal verbs,
   negation, quantifiers, legal terms.
3. **Apertus 8B** reads all three versions and proposes divergences as JSON with
   verbatim quotes.
4. **Apertus 70B** confirms or refutes, only on articles that have candidates.
5. **Guards:** quotes are checked against the source text; the 70B cannot
   silently delete a rule finding for a number, unit, date or reference.
6. **Review interface:** one offline HTML file, three columns, confirm/dismiss.

## Results (136 test cases from 3 real federal acts)

| Setup | Precision | Recall | F1 | False alarms on clean |
| --- | --- | --- | --- | --- |
| Rules only | 0.55 | 0.84 | 0.66 | 0.69 |
| Apertus 70B on every article | 0.95 | 0.28 | 0.43 | 0.01 |
| Cascade (confirmed findings only) | 0.84 | 0.69 | 0.76 | 0.13 |

The cascade costs about 69% of running the 70B on everything. Full tables,
per-type recall and failures are in `technical_report.md` and the PDF report.
Dataset: https://huggingface.co/datasets/AliAounMehdi/concordance-trilingual-divergence

## Limits

- Findings are candidates for human review, not legal conclusions.
- The test errors are injected, and the rules and the injector share a word list,
  so rule recall on injected data is optimistic.
- Only three acts were tested. Romansh, tables and annexes are not covered.
- The local-server (air-gapped GPU) path is documented in `docs/architecture.md`
  but I did not run it on local hardware.
- No demo video yet.

## Commands

```bash
make test                       # unit tests
python -m concordance doctor    # check key, endpoint, model names
make warm                       # record fresh answers (needs .env with a key)
```

## Layout

`src/concordance/` code, `data/` corpus and recorded answers, `docs/` notes and
figures, `tests/`, `technical_report.md`.

## Licence

Code: Apache-2.0. Report and dataset: CC-BY-4.0. Source texts are Swiss federal
legislation from Fedlex. The synthetic demo law is invented.
