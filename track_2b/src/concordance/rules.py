"""Deterministic cross-lingual checks.

Each check extracts a language-independent *feature set* from the three texts
(numbers, dates, modal force, ...) and flags a divergence when the features
disagree. The odd-one-out language is attributed by majority vote.

These checks are fast, free and explainable. They are also the high-recall /
low-precision first stage of the cascade: the LLM stages exist to confirm or
refute what they raise and to catch what they cannot see (omissions, nuance).
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Hashable, Optional

from . import lexicon as lx
from .models import Divergence, LANGS
from .sentences import align_units

_WORD_TOKEN = re.compile(
    r"\d{1,3}(?:[’'\u00a0\u202f]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?|%|[^\W\d_]+(?:['’][^\W\d_]+)?",
    re.UNICODE)
_FILLERS = {"volle", "vollen", "ganze", "ganzen", "aufeinanderfolgende", "aufeinanderfolgenden",
            "consécutifs", "consécutives", "complets", "complet", "consecutivi", "consecutive",
            "interi", "pieni"}
_CURRENCY_PREFIX = {"fr", "chf", "sfr"}


# ------------------------------------------------------------------ helpers
def _mask(text: str, spans: list) -> str:
    """Blank out spans with spaces, preserving offsets."""
    if not spans:
        return text
    chars = list(text)
    for s, e in spans:
        for i in range(s, e):
            chars[i] = " "
    return "".join(chars)


def _overlap(a, b) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def norm_number(tok: str) -> str:
    t = re.sub(r"[’'\u00a0\u202f]", "", tok).replace(",", ".")
    if "." in t:
        t = t.rstrip("0").rstrip(".")
    return t.lstrip("0") or "0"


# ------------------------------------------------------------------ dates & refs
def extract_dates(text: str, lang: str) -> list:
    """-> [((y, m, d), (start, end))]"""
    out = []
    for m in lx.DATE_RE[lang].finditer(text):
        out.append(((int(m.group(3)), lx.MONTHS[lang][m.group(2).lower()], int(m.group(1))), m.span()))
    for m in lx.NUMERIC_DATE_RE.finditer(text):
        out.append(((int(m.group(3)), int(m.group(2)), int(m.group(1))), m.span()))
    return out


def extract_refs(text: str, lang: str) -> dict:
    """-> {'art': [(key, span)], 'para': [...], 'lit': [...], 'item': [...]}"""
    out = {}
    for cls, rx in lx.REF_RE[lang].items():
        items = []
        pat = r"[a-z]" if cls == "lit" else r"\d+[a-z]*"
        for m in rx.finditer(text):
            for k in re.findall(pat, m.group(1).lower()):
                items.append((k, m.span()))
        out[cls] = items
    return out


def _non_quantity_spans(text: str, lang: str) -> list:
    spans = [sp for _, sp in extract_dates(text, lang)]
    for items in extract_refs(text, lang).values():
        spans.extend(sp for _, sp in items)
    spans.extend(m.span() for m in lx.SOURCE_REF_RE.finditer(text))
    return spans


# ------------------------------------------------------------------ quantities
@dataclass
class Qty:
    value: str
    unit: Optional[str]
    start: int
    end: int                 # end of the numeral/number word
    unit_span: Optional[tuple]
    is_numeral: bool
    soft: bool               # spelled-out number without a unit: only used to cancel numerals
    surface: str


def _find_unit(toks: list, j: int, lang: str):
    units = lx.UNITS[lang]
    multi = lx.MULTIWORD_UNITS[lang]
    k = j
    while k < len(toks) and k < j + 3:
        tok = toks[k][0].lower()
        if k + 1 < len(toks) and (tok, toks[k + 1][0].lower()) in multi:
            return multi[(tok, toks[k + 1][0].lower())], (toks[k][1], toks[k + 1][2])
        if tok == "%":
            return "percent", (toks[k][1], toks[k][2])
        if tok in units:
            return units[tok], (toks[k][1], toks[k][2])
        if tok in _FILLERS:
            k += 1
            continue
        break
    return None, None


def extract_quantities(text: str, lang: str) -> list:
    masked = _mask(text, _non_quantity_spans(text, lang))
    toks = [(m.group(), m.start(), m.end()) for m in _WORD_TOKEN.finditer(masked)]
    out = []
    for i, (tok, s, e) in enumerate(toks):
        low = tok.lower()
        if tok[0].isdigit():
            val, is_num = norm_number(tok), True
        elif low in lx.NUMWORDS[lang]:
            val, is_num = str(lx.NUMWORDS[lang][low]), False
        elif low in lx.ONE_WORDS[lang]:
            val, is_num = "1", False
        else:
            continue
        unit, uspan = _find_unit(toks, i + 1, lang)
        if unit is None and is_num and i > 0:
            ptok, ps, pe = toks[i - 1]
            if ptok.lower() in _CURRENCY_PREFIX and re.fullmatch(r"\.?\s*", masked[pe:s]):
                unit, uspan = "chf", (ps, pe)
        if unit is None and not is_num:
            if low in lx.ONE_WORDS[lang]:
                continue                       # plain article "un/ein": ignore
            out.append(Qty(val, None, s, e, None, False, True, tok))
            continue
        end = max(e, uspan[1]) if uspan and uspan[0] >= e else e
        start = min(s, uspan[0]) if uspan and uspan[0] < s else s
        out.append(Qty(val, unit, s, e, uspan, is_num, False, text[start:end]))
    return out


# ------------------------------------------------------------------ comparison core
def odd_langs(sigs: dict) -> list:
    groups = defaultdict(list)
    for l, s in sigs.items():
        groups[s].append(l)
    if len(groups) <= 1:
        return []
    if len(groups) == 2:
        smallest = min(groups.values(), key=len)
        largest = max(groups.values(), key=len)
        return smallest if len(smallest) < len(largest) else list(sigs)
    return list(sigs)


def _compare(feats: dict, as_set: bool = False):
    """feats: lang -> [(key, surface)]. Returns (odd, spans, diffkeys) or None."""
    counters = {l: Counter(k for k, _ in f) for l, f in feats.items()}
    if as_set:
        counters = {l: Counter(set(c)) for l, c in counters.items()}
    sigs = {l: tuple(sorted(c.items(), key=repr)) for l, c in counters.items()}
    odd = odd_langs(sigs)
    if not odd:
        return None
    allkeys = set().union(*[set(c) for c in counters.values()])
    diffkeys = {k for k in allkeys if len({c.get(k, 0) for c in counters.values()}) > 1}
    spans = {l: _dedupe([s for k, s in feats[l] if k in diffkeys]) for l in feats}
    return odd, spans, diffkeys


def _dedupe(xs):
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _mk(typ, odd, spans, expl, sev, conf) -> Divergence:
    return Divergence(type=typ, languages_at_fault=list(odd), spans=spans, explanation=expl,
                      severity=sev, source="rules", confidence=conf, origins=["rules"])


def _fmt_odd(odd):
    return "/".join(l.upper() for l in odd)


# ------------------------------------------------------------------ checks
def check_numbers_units(texts: dict) -> list:
    qs = {l: extract_quantities(texts[l], l) for l in LANGS}
    soft = {l: {q.value for q in qs[l] if q.soft} for l in LANGS}

    def num_feats(l):
        out = []
        for q in qs[l]:
            if q.soft:
                continue
            if q.unit is None and q.is_numeral:
                if any(q.value in soft[o] for o in LANGS if o != l):
                    continue
            out.append((q.value, q.surface))
        return out

    res = _compare({l: num_feats(l) for l in LANGS})
    if res:
        odd, spans, diffkeys = res
        crit = any(q.unit in lx.CRITICAL_UNITS for l in LANGS for q in qs[l]
                   if not q.soft and q.value in diffkeys)
        return [_mk("number", odd, spans,
                    f"Numbers differ across versions; {_fmt_odd(odd)} deviates.",
                    "critical" if crit else "high", 0.9)]
    unit_feats = {l: [((q.value, q.unit), q.surface) for q in qs[l] if q.unit and not q.soft]
                  for l in LANGS}
    res = _compare(unit_feats)
    if res:
        odd, spans, diffkeys = res
        crit = any(u in lx.TIME_UNITS or u in {"chf", "percent"} for _, u in diffkeys)
        return [_mk("unit", odd, spans,
                    f"Same quantity but different unit; {_fmt_odd(odd)} deviates.",
                    "critical" if crit else "high", 0.85)]
    return []


def check_dates(texts: dict) -> list:
    feats = {l: [(k, texts[l][sp[0]:sp[1]]) for k, sp in extract_dates(texts[l], l)] for l in LANGS}
    res = _compare(feats)
    if not res:
        return []
    odd, spans, _ = res
    return [_mk("date", odd, spans, f"Calendar dates differ; {_fmt_odd(odd)} deviates.", "critical", 0.9)]


def check_references(texts: dict) -> list:
    feats = {}
    for l in LANGS:
        refs = extract_refs(texts[l], l)
        feats[l] = [((cls, k), texts[l][sp[0]:sp[1]]) for cls, items in refs.items() for k, sp in items]
    res = _compare(feats)
    if not res:
        return []
    odd, spans, diffkeys = res
    kinds = sorted({c for c, _ in diffkeys})
    return [_mk("reference", odd, spans,
                f"Cross-references differ ({', '.join(kinds)}); {_fmt_odd(odd)} deviates.", "high", 0.9)]


MODAL_DESC = {"PERM": "permission (may)", "OBLIG": "obligation (must)",
              "PROHIB": "prohibition (must not)", "SOFT": "recommendation (should)",
              "NOT_REQUIRED": "no obligation (need not)"}


def modal_features(text: str, lang: str) -> list:
    consumed, out = [], []
    for cls, rx in lx.MODAL_RE[lang]:
        for m in rx.finditer(text):
            if any(_overlap(m.span(), c) for c in consumed):
                continue
            consumed.append(m.span())
            if lang == "fr" and cls == "PROHIB" and m.group().lower().startswith("ne "):
                rm = lx.FR_RESTRICTIVE.match(text[m.end(): m.end() + 80])
                if rm and not lx.FR_TRUE_NEG.search(rm.group(1)):
                    cls = "PERM"        # "ne peuvent ... que pour" = "may only ... for"
            out.append((cls, m.group()))
    return out


def check_modality(texts: dict) -> list:
    feats = {l: modal_features(texts[l], l) for l in LANGS}
    sets = {l: {c for c, _ in f} for l, f in feats.items()}
    # One-sided modality is ignored: Swiss drafting often uses the indicative present.
    if any(not s for s in sets.values()):
        return []
    res = _compare(feats, as_set=True)
    if not res:
        return []
    odd, spans, diffkeys = res
    others = [l for l in LANGS if l not in odd]
    s_odd = set().union(*[sets[l] for l in odd])
    s_oth = set().union(*[sets[l] for l in others]) if others else set()
    strong = ({"OBLIG"}, {"PERM"})
    critical = (
        ("PROHIB" in s_odd) != ("PROHIB" in s_oth)
        or any((a <= s_odd and b <= s_oth) or (b <= s_odd and a <= s_oth) for a, b in [strong])
    )
    desc = "; ".join(f"{l.upper()}: {', '.join(MODAL_DESC[c] for c in sorted(sets[l]))}" for l in LANGS)
    return [_mk("modality", odd, spans, f"Modal force differs ({desc}).",
                "critical" if critical else "high", 0.7)]


def negation_features(text: str, lang: str) -> list:
    hits = []
    idioms = [m.span() for m in lx.NEG_IDIOM_RE[lang].finditer(text)]
    for m in lx.NEG_RE[lang].finditer(text):
        if any(_overlap(m.span(), sp) for sp in idioms):
            continue
        if lang == "fr" and m.group().lower() in ("ne", "n'", "n’"):
            rm = lx.FR_RESTRICTIVE.match(text[m.end(): m.end() + 80])
            if rm and not lx.FR_TRUE_NEG.search(rm.group(1)):
                continue                         # "ne ... que" = "only", not a negation
        hits.append((m.start(), m.group()))
    out, last = [], -10_000
    for pos, surf in sorted(hits):
        if pos - last > lx.NEG_CLUSTER_CHARS:
            out.append(("NEG", surf))
        last = pos
    return out[:2]


def check_negation(texts: dict) -> list:
    feats = {l: negation_features(texts[l], l) for l in LANGS}
    res = _compare(feats)
    if not res:
        return []
    odd, spans, _ = res
    counts = {l: len(f) for l, f in feats.items()}
    flip = min(counts.values()) == 0
    return [_mk("negation", odd, spans,
                f"Negation count differs ({', '.join(f'{l.upper()}={c}' for l, c in counts.items())}).",
                "critical" if flip else "medium", 0.55)]


def check_quantifiers(texts: dict) -> list:
    feats = {}
    for l in LANGS:
        items = []
        for cls, per in lx.QUANT_RE.items():
            for m in per[l].finditer(texts[l]):
                items.append((cls, m.group()))
        if l == "fr":
            for m in lx.NEG_RE["fr"].finditer(texts[l]):
                if m.group().lower() in ("ne", "n'", "n’"):
                    rm = lx.FR_RESTRICTIVE.match(texts[l][m.end(): m.end() + 80])
                    if rm and not lx.FR_TRUE_NEG.search(rm.group(1)):
                        items.append(("ONLY", texts[l][m.start(): m.end() + rm.end()]))
        feats[l] = items
    res = _compare(feats, as_set=True)
    if not res:
        return []
    odd, spans, diffkeys = res
    sets = {l: {c for c, _ in f} for l, f in feats.items()}
    others = [l for l in LANGS if l not in odd]
    s_odd = set().union(*[sets[l] for l in odd])
    s_oth = set().union(*[sets[l] for l in others]) if others else set()
    opposite = any((a in s_odd and b in s_oth) or (b in s_odd and a in s_oth)
                   for a, b in lx.OPPOSITE_QUANT)
    return [_mk("quantifier", odd, spans,
                f"Quantifying expressions differ ({', '.join(sorted(diffkeys))}).",
                "critical" if opposite else "medium", 0.5)]


def family_features(text: str, lang: str) -> set:
    return {name for name, per in lx.FAMILY_RE.items() if per[lang].search(text)}


def check_terminology(texts: dict) -> list:
    fams = {l: family_features(texts[l], l) for l in LANGS}
    out = []
    for members, sev in lx.CONFUSABLE_GROUPS:
        g = set(members)
        present = {l: frozenset(fams[l] & g) for l in LANGS if fams[l] & g}
        if len(present) < 2 or len(set(present.values())) == 1:
            continue
        odd = odd_langs(present)
        if not odd:
            continue
        spans = {}
        for l in LANGS:
            spans[l] = []
            for name in fams[l] & g:
                if any(name not in present[o] for o in present if o != l) or l in odd:
                    m = lx.FAMILY_RE[name][l].search(texts[l])
                    if m:
                        spans[l].append(m.group())
        desc = ", ".join(f"{l.upper()}: {'/'.join(sorted(s))}" for l, s in present.items())
        out.append(_mk("terminology", odd, spans, f"Different legal concept or actor named ({desc}).",
                       sev, 0.6))
    return out


def check_omission(texts: dict) -> list:
    lens = {l: len(re.sub(r"\s+", " ", texts[l]).strip()) for l in LANGS}
    if min(lens.values()) < 40:
        return []
    med = sorted(lens.values())[1]
    worst = max(LANGS, key=lambda l: abs(lens[l] - med) / max(med, 1))
    ratio = lens[worst] / max(med, 1)
    if 0.55 <= ratio <= 1.8:
        return []
    return [_mk("omission", [worst], {l: [] for l in LANGS},
                f"{worst.upper()} is {ratio:.2f}x the median length; content may be missing or added.",
                "low", 0.3)]


# Lexical checks that are robust on a whole article ...
RELIABLE_CHECKS = (check_numbers_units, check_dates, check_references, check_omission)
# ... and checks that only make sense between CORRESPONDING sentences.
SENTENCE_CHECKS = (check_modality, check_negation, check_quantifiers, check_terminology)


def rule_divergences(texts: dict) -> list:
    if not all(texts.get(l, "").strip() for l in LANGS):
        return []
    out = []
    for chk in RELIABLE_CHECKS:
        out.extend(chk(texts))
    units = align_units(texts)
    if units is None:                          # structures differ: whole-article fallback
        for chk in SENTENCE_CHECKS:
            out.extend(chk(texts))
    else:
        for unit in units:
            for chk in SENTENCE_CHECKS:
                for d in chk(unit):
                    d.unit = dict(unit)
                    out.append(d)
    return out
