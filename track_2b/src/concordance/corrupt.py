"""Ground-truth generation by controlled corruption.

Take a real, aligned article, damage ONE language in a way that changes its legal
meaning (a number, a modal verb, a cross-reference, ...), and record exactly what was
done. Untouched articles serve as clean controls. This yields labelled data at scale
without needing a human to find real discrepancies.

Honest limitation: injected errors are cleaner than real ones. They measure whether a
detector can see a divergence of a given kind, not how often real law contains them.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

from . import lexicon as lx
from .models import LANGS, AlignedArticle
from .rules import (extract_dates, extract_quantities, extract_refs, modal_features,
                    negation_features, rule_divergences)

INJECT_TYPES = ("number", "unit", "date", "modality", "negation", "quantifier",
                "reference", "terminology")


@dataclass
class EvalCase:
    case_id: str
    act_id: str
    art_id: str
    num: str
    texts: dict
    act_title: str = ""
    sources: dict = field(default_factory=dict)
    gold: Optional[dict] = None          # None = clean control

    def to_dict(self):
        return asdict(self)

    def as_article(self) -> AlignedArticle:
        return AlignedArticle(act_id=self.act_id, art_id=f"{self.art_id}#{self.case_id}", num=self.num,
                              texts=self.texts, act_title=self.act_title, sources=self.sources)


def _snippet(text: str, a: int, b: int, pad: int = 28) -> str:
    return text[max(0, a - pad): b + pad].replace("\n", " ")


def _keep_case(old: str, new: str) -> str:
    return new[:1].upper() + new[1:] if old[:1].isupper() else new


def _result(text: str, a: int, b: int, repl: str, typ: str, lang: str):
    new = text[:a] + repl + text[b:]
    if new == text:
        return None
    return new, {"type": typ, "lang": lang, "before": _snippet(text, a, b),
                 "after": _snippet(new, a, a + len(repl))}


def _alt_number(v: str) -> str:
    x = float(v)
    if x != int(x):
        return str(x + 1)
    n = int(x)
    alt = n * 2 if n < 50 else max(1, n // 2)
    return str(alt if alt != n else n + 1)


def inject_number(text, lang, rng):
    qs = [q for q in extract_quantities(text, lang) if q.is_numeral and not q.soft]
    if not qs:
        return None
    q = rng.choice(qs)
    return _result(text, q.start, q.end, _alt_number(q.value), "number", lang)


def inject_unit(text, lang, rng):
    qs = [q for q in extract_quantities(text, lang)
          if q.unit and q.unit_span and q.unit in lx.UNIT_SWAP[lang] and not q.soft]
    if not qs:
        return None
    q = rng.choice(qs)
    a, b = q.unit_span
    return _result(text, a, b, lx.UNIT_SWAP[lang][q.unit], "unit", lang)


def inject_date(text, lang, rng):
    ds = [m for m in lx.DATE_RE[lang].finditer(text)]
    if ds:
        m = rng.choice(ds)
        return _result(text, m.start(3), m.end(3), str(int(m.group(3)) + 1), "date", lang)
    ms = list(lx.NUMERIC_DATE_RE.finditer(text))
    if ms:
        m = rng.choice(ms)
        return _result(text, m.start(3), m.end(3), str(int(m.group(3)) + 1), "date", lang)
    return None


def _first_swap(text, lang, table, typ, rng):
    hits = []
    for pat, repl in table[lang]:
        m = re.search(pat, text, lx.U)
        if m:
            hits.append((m, repl))
    if not hits:
        return None
    m, repl = rng.choice(hits)
    return _result(text, m.start(), m.end(), _keep_case(m.group(), m.expand(repl) if "\\" in repl else repl),
                   typ, lang)


def inject_modality(text, lang, rng):
    """Swap a modal verb, keeping only swaps that really change modal force
    (e.g. 'ne peut pas' -> 'ne doit pas' is still a prohibition, so it is rejected)."""
    before = {c for c, _ in modal_features(text, lang)}
    options = []
    for pat, repl in lx.MODAL_SWAP[lang]:
        for m in re.finditer(pat, text, lx.U):
            if m.group()[:1].isupper():
                continue                    # sentence-initial: "Kann weder ... noch ..." is not a rule-level modal
            new = text[:m.start()] + _keep_case(m.group(), repl) + text[m.end():]
            if {c for c, _ in modal_features(new, lang)} != before:
                options.append((m, repl))
    if not options:
        return None
    m, repl = rng.choice(options)
    return _result(text, m.start(), m.end(), _keep_case(m.group(), repl), "modality", lang)


def inject_quantifier(text, lang, rng):
    return _first_swap(text, lang, lx.QUANT_SWAP, "quantifier", rng)


def inject_negation(text, lang, rng):
    if not negation_features(text, lang):
        return None
    for pat, repl in lx.NEG_REMOVE[lang]:
        m = re.search(pat, text, lx.U)
        if m:
            return _result(text, m.start(), m.end(), m.expand(repl), "negation", lang)
    return None


def inject_reference(text, lang, rng):
    rx = lx.REF_RE[lang]["art"]
    ms = list(rx.finditer(text))
    if not ms:
        return None
    m = rng.choice(ms)
    g = m.group(1)
    d = re.search(r"\d+", g)
    if not d:
        return None
    a, b = m.start(1) + d.start(), m.start(1) + d.end()
    return _result(text, a, b, str(int(d.group()) + 1), "reference", lang)


# (source regex, replacement, regex of the target family that must be absent)
TERM_SWAP = {
    "de": [(r"Arbeitgeber", "Arbeitnehmer", r"arbeitnehmer"), (r"Arbeitnehmer", "Arbeitgeber", r"arbeitgeber"),
           (r"Versicherer", "Versicherte", r"versicherte"), (r"Busse", "Freiheitsstrafe", r"freiheitsstrafe"),
           (r"Bewilligung", "Konzession", r"konzession"), (r"Beschwerde", "Einsprache", r"einsprache"),
           (r"Bundesrat", "Bundesversammlung", r"bundesversammlung")],
    "fr": [(r"employeur", "travailleur", r"travailleur"), (r"travailleur", "employeur", r"employeur"),
           (r"assureur", "assuré", r"assuré"), (r"amende", "peine privative de liberté", r"privative"),
           (r"autorisation", "concession", r"concession"), (r"recours", "opposition", r"opposition"),
           (r"Conseil fédéral", "Assemblée fédérale", r"assemblée fédérale")],
    "it": [(r"datore di lavoro", "lavoratore", r"lavorator"), (r"lavoratore", "datore di lavoro", r"datore"),
           (r"assicuratore", "assicurato", r"assicurat[oi]\b"), (r"multa", "pena detentiva", r"detentiv"),
           (r"autorizzazione", "concessione", r"concession"), (r"ricorso", "opposizione", r"opposizione"),
           (r"Consiglio federale", "Assemblea federale", r"assemblea federale")],
}


def inject_terminology(text, lang, rng):
    hits = []
    for src, dst, dst_rx in TERM_SWAP[lang]:
        m = re.search(src, text, lx.U)
        if m and not re.search(dst_rx, text, lx.U):
            hits.append((m, dst))
    if not hits:
        return None
    m, dst = rng.choice(hits)
    return _result(text, m.start(), m.end(), _keep_case(m.group(), dst), "terminology", lang)


INJECTORS = {"number": inject_number, "unit": inject_unit, "date": inject_date,
             "modality": inject_modality, "negation": inject_negation,
             "quantifier": inject_quantifier, "reference": inject_reference,
             "terminology": inject_terminology}


def build_eval_set(arts: list, seed: int = 7, max_per_type: int = 15, types=None,
                   clean_ratio: float = 1.0, exclude_art_ids=()) -> list:
    types = list(types or INJECT_TYPES)
    cases: list = []
    exclude = set(exclude_art_ids)
    pool = [a for a in arts if all(a.texts.get(l, "").strip() for l in LANGS)
            and a.art_id not in exclude]
    originally_clean = [a for a in pool if not rule_divergences(a.texts)]
    for typ in types:
        rng = random.Random(f"{seed}:{typ}")
        order = originally_clean[:]
        rng.shuffle(order)
        n = 0
        for art in order:
            if n >= max_per_type:
                break
            langs = list(LANGS)
            rng.shuffle(langs)
            for lang in langs:
                out = INJECTORS[typ](art.texts[lang], lang, rng)
                if out is None:
                    continue
                new_text, info = out
                texts = dict(art.texts)
                texts[lang] = new_text
                cid = f"{typ}-{n:03d}"
                cases.append(EvalCase(case_id=cid, act_id=art.act_id, art_id=art.art_id, num=art.num,
                                      texts=texts, act_title=art.act_title, sources=art.sources,
                                      gold=info))
                n += 1
                break
    n_clean = min(len(pool), max(1, int(round(len(cases) * clean_ratio))))
    rng = random.Random(f"{seed}:clean")
    for i, art in enumerate(rng.sample(pool, n_clean) if pool else []):
        cases.append(EvalCase(case_id=f"clean-{i:03d}", act_id=art.act_id, art_id=art.art_id, num=art.num,
                              texts=art.texts, act_title=art.act_title, sources=art.sources, gold=None))
    return cases
