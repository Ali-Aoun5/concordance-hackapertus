"""Fedlex ingestion (offline step; the detector itself never touches the network).

Pipeline:  SR number --SPARQL--> XML download URL per language --parse Akoma Ntoso-->
           articles keyed by eId --align across DE/FR/IT--> corpus JSON.

Articles are aligned on their Akoma Ntoso `eId` (e.g. `art_12`), which is structural and
language-independent. Articles present in only some languages are recorded under
`unaligned`: a structural divergence in its own right.

If the SPARQL route fails (the endpoint or schema may change), download the XML of each
language manually from fedlex.admin.ch and use `ingest --xml-dir`.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from .models import LANGS

SPARQL_ENDPOINT = "https://fedlex.data.admin.ch/sparqlendpoint"
LANG_URI = {
    "de": "http://publications.europa.eu/resource/authority/language/DEU",
    "fr": "http://publications.europa.eu/resource/authority/language/FRA",
    "it": "http://publications.europa.eu/resource/authority/language/ITA",
}
# Adapted from a public working query (metaodi/govtech24_kommentator2000, xml_to_json.py).
SPARQL_TEMPLATE = """
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT DISTINCT ?title (str(?daNode) AS ?applicable) ?fileUri WHERE {
  VALUES (?srString) { ("%(sr)s") }
  ?consoAbstract a jolux:ConsolidationAbstract .
  ?consoAbstract jolux:classifiedByTaxonomyEntry/skos:notation ?rsNotation .
  FILTER(str(?rsNotation) = ?srString)
  ?consoAbstract jolux:isRealizedBy ?absExpr .
  ?absExpr jolux:language <%(lang_uri)s> .
  ?absExpr jolux:title ?title .
  ?conso a jolux:Consolidation .
  ?conso jolux:isMemberOf ?consoAbstract .
  ?conso jolux:dateApplicability ?daNode .
  ?conso jolux:isRealizedBy ?consoExpr .
  ?consoExpr jolux:language <%(lang_uri)s> .
  ?consoExpr jolux:isEmbodiedBy ?manifestation .
  ?manifestation jolux:isExemplifiedBy ?fileUri .
  ?manifestation jolux:userFormat/skos:notation "xml"^^<https://fedlex.data.admin.ch/vocabulary/notation-type/uri-suffix> .
}
ORDER BY DESC(?fileUri)
"""

SKIP_TAGS = {"authorialNote", "num", "heading", "subheading"}
BLOCK_TAGS = {"p", "intro", "item", "point", "paragraph", "content", "list", "wrapUp", "blockList"}


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


# ------------------------------------------------------------------ parsing
def _collect_text(el, out: list) -> None:
    if _local(el.tag) in SKIP_TAGS:
        return
    if el.text:
        out.append(el.text)
    for child in el:
        _collect_text(child, out)
        if child.tail:
            out.append(child.tail)
    if _local(el.tag) in BLOCK_TAGS:
        out.append(" ")


def _clean(s: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\s*\n\s*", " ", s)).strip()


def _text_without_notes(el, buf: list) -> None:
    if _local(el.tag) == "authorialNote":
        return
    if el.text:
        buf.append(el.text)
    for c in el:
        _text_without_notes(c, buf)
        if c.tail:
            buf.append(c.tail)


def _first_num(art) -> str:
    for child in art:
        if _local(child.tag) == "num":
            buf: list = []
            _text_without_notes(child, buf)
            return _clean("".join(buf))
    return ""


def _norm_num(num: str) -> str:
    return re.sub(r"[^a-z0-9]", "", num.lower())


def parse_akn(xml_bytes: bytes) -> dict:
    """Parse one Akoma Ntoso act. Returns {'title','articles': OrderedDict[key -> {num,text}]}."""
    root = ET.fromstring(xml_bytes)
    title = ""
    for el in root.iter():
        if _local(el.tag) == "FRBRname" and el.get("value"):
            title = el.get("value")
            break
    articles: "OrderedDict[str, dict]" = OrderedDict()
    for art in root.iter():
        if _local(art.tag) != "article":
            continue
        num = _first_num(art)
        key = art.get("eId") or ("num:" + _norm_num(num))
        paras = [c for c in art if _local(c.tag) == "paragraph"]
        if paras:
            chunks = []
            for p in paras:
                buf: list = []
                _collect_text(p, buf)
                t = _clean("".join(buf))
                if t:
                    chunks.append(t)
            text = "\n".join(chunks)
        else:
            buf = []
            for c in art:
                _collect_text(c, buf)
            text = _clean("".join(buf))
        if key and text and key not in articles:
            articles[key] = {"num": num, "text": text}
    return {"title": title, "articles": articles}


def align_acts(parsed: dict) -> tuple:
    """parsed: lang -> parse_akn() result. Returns (aligned_articles, unaligned)."""
    langs = [l for l in LANGS if l in parsed]
    base = parsed.get("de") or parsed[langs[0]]
    keys_all = list(base["articles"].keys())
    for l in langs:
        for k in parsed[l]["articles"]:
            if k not in keys_all:
                keys_all.append(k)
    aligned, unaligned = [], []
    for k in keys_all:
        present = [l for l in langs if k in parsed[l]["articles"]]
        if len(present) == len(LANGS):
            aligned.append({"art_id": k,
                            "num": parsed["de"]["articles"][k]["num"],
                            "texts": {l: parsed[l]["articles"][k]["text"] for l in LANGS}})
        else:
            unaligned.append({"art_id": k, "present_in": present,
                              "missing_in": [l for l in LANGS if l not in present]})
    return aligned, unaligned


# ------------------------------------------------------------------ network (offline step)
def _session():
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = "concordance-hackapertus/0.1 (research; contact via repo)"
    return s


def resolve_xml_urls(sr: str, today: Optional[dt.date] = None, session=None, debug=False) -> dict:
    """SR number -> {lang: (xml_url, applicable_date, title)} for the latest consolidation in force."""
    session = session or _session()
    today = today or dt.date.today()
    out = {}
    for lang in LANGS:
        q = SPARQL_TEMPLATE % {"sr": sr, "lang_uri": LANG_URI[lang]}
        r = session.get(SPARQL_ENDPOINT, params={"query": q}, timeout=90,
                        headers={"Accept": "application/sparql-results+json"})
        r.raise_for_status()
        rows = r.json()["results"]["bindings"]
        if debug:
            print(f"[{sr}/{lang}] {len(rows)} consolidation files")
        best = None
        for row in rows:
            applicable = row["applicable"]["value"][:10]
            try:
                d = dt.date.fromisoformat(applicable)
            except ValueError:
                continue
            if d <= today and (best is None or d > best[1] or (d == best[1] and row["fileUri"]["value"] > best[0])):
                best = (row["fileUri"]["value"], d, row["title"]["value"])
        if best is None:
            raise RuntimeError(f"No consolidated XML in force found for SR {sr} ({lang}).")
        out[lang] = best
    return out


def fetch_act(sr: str, raw_dir: Optional[Path] = None, session=None, debug=False) -> dict:
    session = session or _session()
    urls = resolve_xml_urls(sr, session=session, debug=debug)
    parsed, sources = {}, {}
    for lang, (url, applicable, title) in urls.items():
        resp = session.get(url, timeout=120)
        resp.raise_for_status()
        if raw_dir:
            raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / f"SR{sr}_{lang}.xml").write_bytes(resp.content)
        p = parse_akn(resp.content)
        p["title"] = title or p["title"]
        p["applicable"] = applicable.isoformat()
        parsed[lang] = p
        sources[lang] = url
    return _assemble(f"SR {sr}", parsed, sources)


def load_xml_dir(xml_dir: Path) -> list:
    """Files named <name>_de.xml / <name>_fr.xml / <name>_it.xml are grouped by <name>."""
    groups: dict = {}
    for f in sorted(Path(xml_dir).glob("*.xml")):
        m = re.match(r"(.+)_(de|fr|it)\.xml$", f.name, re.I)
        if m:
            groups.setdefault(m.group(1), {})[m.group(2).lower()] = f
    acts = []
    for name, files in groups.items():
        if set(files) != set(LANGS):
            print(f"skip {name}: need _de, _fr and _it files (have {sorted(files)})")
            continue
        parsed = {l: parse_akn(files[l].read_bytes()) for l in LANGS}
        acts.append(_assemble(name, parsed, {l: str(files[l].name) for l in LANGS}))
    return acts


def _assemble(act_id: str, parsed: dict, sources: dict) -> dict:
    aligned, unaligned = align_acts(parsed)
    return {
        "act_id": act_id,
        "title": {l: parsed[l]["title"] for l in LANGS},
        "applicable": parsed["de"].get("applicable"),
        "retrieved": dt.date.today().isoformat(),
        "sources": sources,
        "articles": aligned,
        "unaligned": unaligned,
    }


# ------------------------------------------------------------------ corpus I/O
def save_corpus(path: Path, name: str, acts: list, extra_meta: Optional[dict] = None) -> None:
    meta = {"name": name, "synthetic": False, "license_note":
            "Swiss federal law texts from Fedlex (fedlex.admin.ch); re-use per Fedlex terms. Cite source and date.",
            "created": dt.date.today().isoformat()}
    meta.update(extra_meta or {})
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"meta": meta, "acts": acts}, ensure_ascii=False, indent=1),
                          encoding="utf-8")


def load_corpus(path: Path, max_articles_per_act: Optional[int] = None) -> tuple:
    """-> (meta, [AlignedArticle])"""
    from .models import AlignedArticle
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    arts = []
    for act in data["acts"]:
        title = act["title"].get("de", "") if isinstance(act.get("title"), dict) else act.get("title", "")
        rows = act["articles"][:max_articles_per_act] if max_articles_per_act else act["articles"]
        for a in rows:
            arts.append(AlignedArticle(
                act_id=act["act_id"], art_id=a["art_id"], num=a.get("num", ""), texts=a["texts"],
                act_title=title, sources=act.get("sources", {}),
                meta={"applicable": act.get("applicable"), "retrieved": act.get("retrieved")}))
    return data.get("meta", {}), arts
