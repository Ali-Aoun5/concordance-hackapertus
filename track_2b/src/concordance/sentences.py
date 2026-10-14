"""Sentence-level alignment of the three language versions.

Swiss federal law is co-drafted, so the three versions of an article almost always have the
same paragraph and sentence structure. Comparing corresponding sentences (instead of whole
articles) is what removes most false alarms and exposes swaps that article-level feature
sets hide. If the structure does not match, callers fall back to the whole article.
"""
from __future__ import annotations

import re

LANGS = ("de", "fr", "it")
# sentence end, not after a digit ("25. September"), followed by a capital letter or opening quote
_SPLIT = re.compile(r"(?<=[.;])(?<!\d\.)\s+(?=[A-ZÀ-ÖØ-Þ«„“])")


def split_paragraphs(text: str) -> list:
    return [p.strip() for p in text.split("\n") if p.strip()]


def split_sentences(text: str) -> list:
    out = []
    for para in split_paragraphs(text):
        out.extend(s.strip() for s in _SPLIT.split(para) if s.strip())
    return out


def _plausible(unit: dict) -> bool:
    lens = [len(v) for v in unit.values()]
    if min(lens) == 0:
        return False
    return min(lens) < 25 or max(lens) <= 2.8 * min(lens)


def align_units(texts: dict):
    """-> list of {lang: sentence} aligned by position, or None if the structures differ."""
    for splitter in (split_sentences, split_paragraphs):
        parts = {l: splitter(texts.get(l, "")) for l in LANGS}
        counts = {len(v) for v in parts.values()}
        if len(counts) != 1 or counts == {0}:
            continue
        units = [{l: parts[l][i] for l in LANGS} for i in range(len(parts["de"]))]
        if all(_plausible(u) for u in units):
            return units
    return None
