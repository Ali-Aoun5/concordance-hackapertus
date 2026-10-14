"""Prompts. English instructions, trilingual content, strict JSON output.

Design notes (also in the technical report):
  * Triage and verification are separate prompts: the cheap model proposes, the large
    model disposes. The verifier sees the candidates and may refute or add.
  * Quotes must be copied verbatim; the detector checks them against the source text
    (a hallucination guard) and records the result as `grounded`.
  * Two short in-context examples fix the output schema for small models.
"""
from __future__ import annotations

import re

_SENT = re.compile(r"(?<=[.;])(?<!\d\.)\s+(?=[A-ZÀ-ÖØ-Þ«„“])|\n+")
_LANGS = ("de", "fr", "it")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\u00a0", " ").lower()).strip()


def evidence_sentences(texts: dict, spans: dict) -> dict:
    """The sentence of each language that contains the evidence span(s) of a candidate.
    Focusing the verifier on corresponding sentences stops it from skimming a long article."""
    out = {}
    for l in _LANGS:
        sents = [s.strip() for s in _SENT.split(texts.get(l, "")) if s.strip()]
        found = []
        for sp in spans.get(l, []) or []:
            n = _norm(sp)
            for s in sents:
                if n and n in _norm(s) and s not in found:
                    found.append(s)
                    break
        out[l] = " ".join(found[:2])[:420]
    return out


TYPE_QUESTION = {
    "modality": "Compare ONLY the legal force of the verbs in the corresponding sentences: may / must / must not / may only. "
                "Different wording can still mean the same ('dürfen nur' = 'ne peuvent … que' = 'possono … soltanto'), "
                "but 'kann' (may) against 'doit' (must) is a real difference.",
    "number": "Check whether the figures, amounts and deadlines are identical.",
    "unit": "Check whether the unit (days, months, years, francs, percent) is identical.",
    "date": "Check whether the calendar dates are identical.",
    "reference": "Check whether the same provisions (article, paragraph, letter) are cited.",
    "negation": "Check whether one version negates what the others state affirmatively. "
                "('ne … que' means 'only'; 'sans délai' / 'senza indugio' means 'immediately'.)",
    "quantifier": "Check whether all / some / at least / at most / only / latest / earliest mean the same in all versions.",
    "terminology": "Check whether the same legal concept or actor is named in all versions.",
}

SYSTEM = (
    "You are a senior reviewer in the legal-linguistic service of the Swiss Federal Chancellery. "
    "The German, French and Italian versions of Swiss federal law are equally authentic, so any "
    "difference in legal meaning between them is a defect that must be reported. "
    "You compare the three versions of one article and report ONLY differences that change the "
    "legal meaning. Ignore differences of style, word order, punctuation, gender-neutral wording and "
    "ordinary translation choices. Reply with a single JSON object and nothing else."
)

TYPE_HELP = """\
- number: a different number, amount or percentage
- unit: the same number with a different unit (days vs months, francs vs percent)
- date: a different calendar date
- modality: may / must / must not / should differ (kann, muss, darf nicht, soll; peut, doit, ne peut pas; può, deve, non può)
- negation: a negation present in one version and absent in another
- quantifier: all / some / at least / at most / only / latest / earliest differ
- reference: a different article, paragraph, letter or item is cited
- terminology: a different legal concept or actor (employer vs employee, fine vs imprisonment, ...)
- omission: a condition, exception or element that appears in only some versions
- other: any other difference in legal meaning"""

SCHEMA_TRIAGE = """\
Return JSON with exactly this shape:
{"consistent": true or false,
 "divergences": [
   {"type": "<one of the types above>",
    "languages_at_fault": ["de" | "fr" | "it", ...],
    "quotes": {"de": "<words copied exactly from the DE text, or empty>", "fr": "...", "it": "..."},
    "explanation": "<one or two sentences in English>",
    "severity": "low" | "medium" | "high" | "critical"}
 ]}
If the three versions agree in legal meaning return {"consistent": true, "divergences": []}.
"languages_at_fault" lists the version(s) that deviate from the other two; if you cannot tell, list all three."""


def _block(texts: dict) -> str:
    return "\n\n".join(f"[{l.upper()}]\n{texts[l].strip()}" for l in ("de", "fr", "it"))


def triage_user(act_title: str, num: str, texts: dict) -> str:
    return (f"Act: {act_title or 'n/a'}\nArticle: {num}\n\n{_block(texts)}\n\n"
            f"Divergence types:\n{TYPE_HELP}\n\n{SCHEMA_TRIAGE}")


# --- two compact few-shot examples (invented text, not from the corpus) -------------
_EX_DIV = {
    "de": "Die Gemeinde zahlt den Beitrag innert 10 Tagen aus.",
    "fr": "La commune verse la contribution dans un délai de 20 jours.",
    "it": "Il comune versa il contributo entro 10 giorni.",
}
_EX_DIV_OUT = ('{"consistent": false, "divergences": [{"type": "number", "languages_at_fault": ["fr"], '
               '"quotes": {"de": "innert 10 Tagen", "fr": "dans un délai de 20 jours", "it": "entro 10 giorni"}, '
               '"explanation": "The French version sets a 20-day deadline while German and Italian set 10 days.", '
               '"severity": "critical"}]}')
_EX_OK = {
    "de": "Die Behörde kann Auskünfte verlangen.",
    "fr": "L’autorité peut exiger des renseignements.",
    "it": "L’autorità può esigere informazioni.",
}
_EX_OK_OUT = '{"consistent": true, "divergences": []}'


def triage_messages(act_title: str, num: str, texts: dict) -> list:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": triage_user("Example act", "Art. 1", _EX_DIV)},
        {"role": "assistant", "content": _EX_DIV_OUT},
        {"role": "user", "content": triage_user("Example act", "Art. 2", _EX_OK)},
        {"role": "assistant", "content": _EX_OK_OUT},
        {"role": "user", "content": triage_user(act_title, num, texts)},
    ]


SCHEMA_VERIFY = """\
Return JSON with exactly this shape:
{"verdicts": [
   {"index": <number of the candidate>,
    "verdict": "confirmed" | "refuted" | "uncertain",
    "reason": "<one or two sentences in English>",
    "severity": "low" | "medium" | "high" | "critical",
    "suggestion": "<a harmonised wording for the version at fault, written in its own language, or null>"}
 ],
 "additional": [ <zero or more divergences not listed above, same shape as in the first-pass analysis:
   {"type", "languages_at_fault", "quotes", "explanation", "severity"}> ]}
Verdict rules:
- confirmed: the legal meaning really differs between the versions.
- refuted: the difference is stylistic, structural, a normal translation convention, or a false alarm of an automatic check.
- uncertain: only a legal expert can decide.
Judge every candidate by comparing the corresponding sentences word for word; do not refute a candidate merely because each version reads plausibly on its own. Quotes in "additional" must be copied exactly from the texts."""


def verify_messages(act_title: str, num: str, texts: dict, candidates: list) -> list:
    lines = []
    for i, c in enumerate(candidates):
        q = "; ".join(f"{l.upper()}: “{s}”" for l, ss in c["spans"].items() for s in ss[:2]) or "n/a"
        origin = "automatic rule-based check" if "rules" in c.get("origins", []) else "first-pass model"
        unit = c.get("unit")
        ev = ({l: (unit.get(l) or "")[:420] for l in _LANGS} if unit
              else evidence_sentences(texts, c["spans"]))
        sent = "\n".join(f"      {l.upper()}: {ev[l]}" for l in _LANGS if ev[l])
        hint = TYPE_QUESTION.get(c["type"], "")
        lines.append(f"[{i}] type={c['type']} | raised by: {origin} | at fault: "
                     f"{', '.join(l.upper() for l in c['languages_at_fault']) or 'unclear'}\n"
                     f"    evidence: {q}\n    claim: {c['explanation']}"
                     + (f"\n    corresponding sentences:\n{sent}" if sent else "")
                     + (f"\n    how to judge: {hint}" if hint else ""))
    user = (f"Act: {act_title or 'n/a'}\nArticle: {num}\n\n{_block(texts)}\n\n"
            "A first-pass analysis flagged the candidate divergences below.\n\n"
            + "\n".join(lines) + f"\n\n{SCHEMA_VERIFY}")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
