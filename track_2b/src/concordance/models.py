"""Core data structures. Plain dataclasses, JSON-serialisable via to_dict()."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

LANGS = ("de", "fr", "it")
LANG_NAMES = {"de": "German", "fr": "French", "it": "Italian"}

DIVERGENCE_TYPES = (
    "number", "unit", "date", "modality", "negation", "quantifier",
    "reference", "terminology", "omission", "other",
)
SEVERITIES = ("low", "medium", "high", "critical")
SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}


@dataclass
class AlignedArticle:
    """One article in all three authentic languages."""
    act_id: str
    art_id: str
    num: str
    texts: dict                      # lang -> text
    act_title: str = ""
    sources: dict = field(default_factory=dict)   # lang -> url
    meta: dict = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return f"{self.act_id}::{self.art_id}"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "AlignedArticle":
        return AlignedArticle(
            act_id=d["act_id"], art_id=d["art_id"], num=d.get("num", ""),
            texts=d["texts"], act_title=d.get("act_title", ""),
            sources=d.get("sources", {}), meta=d.get("meta", {}),
        )


@dataclass
class Divergence:
    type: str
    languages_at_fault: list
    spans: dict                      # lang -> list[str] surface strings to highlight
    explanation: str
    severity: str = "medium"
    source: str = "rules"            # rules | llm8 | llm70 | cascade
    confidence: float = 0.5
    verdict: Optional[str] = None    # confirmed | refuted | uncertain | None
    verdict_reason: str = ""
    suggestion: Optional[str] = None
    grounded: Optional[bool] = None  # quotes found verbatim in the source text?
    origins: list = field(default_factory=list)   # which detectors raised it
    unit: Optional[dict] = None      # the corresponding sentences (lang -> text) it was found in

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ArticleResult:
    act_id: str
    art_id: str
    num: str
    texts: dict
    mode: str
    divergences: list = field(default_factory=list)   # list[Divergence]
    rejected: list = field(default_factory=list)      # candidates the verifier refuted
    llm_status: str = "n/a"          # n/a | ok | unavailable | parse_error
    escalated: bool = False          # sent to the large model?
    trace: list = field(default_factory=list)         # raw model I/O for auditing
    act_title: str = ""
    sources: dict = field(default_factory=dict)

    @property
    def flagged(self) -> bool:
        return len(self.divergences) > 0

    @property
    def max_severity(self) -> str:
        if not self.divergences:
            return "none"
        return max((d.severity for d in self.divergences), key=lambda s: SEV_RANK.get(s, 0))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["flagged"] = self.flagged
        d["max_severity"] = self.max_severity
        return d
