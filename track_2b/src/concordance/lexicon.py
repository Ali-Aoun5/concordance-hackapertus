"""Multilingual (DE/FR/IT) lexicon for Swiss legislative drafting.

Everything the deterministic checks know about the three languages lives here,
so it can be reviewed by a legal-linguist without reading any logic.
"""
from __future__ import annotations

import re

U = re.I | re.UNICODE
LANGS = ("de", "fr", "it")

# ---------------------------------------------------------------- numbers & units
# Separators used in Swiss number formatting: apostrophe, right quote, (narrow) nbsp.
NUM_RE = re.compile(
    r"\d{1,3}(?:[’'\u00a0\u202f]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?", U)

NUMWORDS = {
    "de": {"zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8,
           "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12, "dreissig": 30, "dreißig": 30,
           "vierzig": 40, "fünfzig": 50, "sechzig": 60, "neunzig": 90, "hundert": 100},
    "fr": {"deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
           "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "trente": 30, "quarante": 40,
           "cinquante": 50, "soixante": 60, "cent": 100},
    "it": {"due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7, "otto": 8,
           "nove": 9, "dieci": 10, "undici": 11, "dodici": 12, "trenta": 30, "quaranta": 40,
           "cinquanta": 50, "sessanta": 60, "novanta": 90, "cento": 100},
}
ONE_WORDS = {
    "de": {"ein", "eine", "einen", "einem", "einer", "eines"},
    "fr": {"un", "une"},
    "it": {"un", "uno", "una", "un'"},
}

# surface (lowercase) -> canonical unit
UNITS = {
    "de": {
        "tag": "day", "tage": "day", "tagen": "day", "tages": "day",
        "woche": "week", "wochen": "week",
        "monat": "month", "monate": "month", "monaten": "month", "monats": "month",
        "jahr": "year", "jahre": "year", "jahren": "year", "jahres": "year",
        "stunde": "hour", "stunden": "hour",
        "prozent": "percent", "franken": "chf", "fr": "chf", "chf": "chf",
    },
    "fr": {
        "jour": "day", "jours": "day", "semaine": "week", "semaines": "week",
        "mois": "month", "an": "year", "ans": "year", "année": "year", "années": "year",
        "heure": "hour", "heures": "hour",
        "francs": "chf", "franc": "chf", "fr": "chf", "chf": "chf",
    },
    "it": {
        "giorno": "day", "giorni": "day", "settimana": "week", "settimane": "week",
        "mese": "month", "mesi": "month", "anno": "year", "anni": "year",
        "ora": "hour", "ore": "hour",
        "franchi": "chf", "franco": "chf", "fr": "chf", "chf": "chf",
    },
}
# multi-word units: tuple of tokens -> canonical
MULTIWORD_UNITS = {
    "fr": {("pour", "cent"): "percent"},
    "it": {("per", "cento"): "percent"},
    "de": {},
}
TIME_UNITS = {"day", "week", "month", "year", "hour"}
CRITICAL_UNITS = TIME_UNITS | {"percent", "chf"}

# Replacement surfaces used by the corruption injector (plural forms).
UNIT_SWAP = {
    "de": {"day": "Monate", "week": "Monate", "month": "Tage", "year": "Monate",
           "hour": "Tage", "percent": "Franken", "chf": "Prozent"},
    "fr": {"day": "mois", "week": "mois", "month": "jours", "year": "mois",
           "hour": "jours", "percent": "francs", "chf": "%"},
    "it": {"day": "mesi", "week": "mesi", "month": "giorni", "year": "mesi",
           "hour": "giorni", "percent": "franchi", "chf": "%"},
}

MONTHS = {
    "de": {"januar": 1, "februar": 2, "märz": 3, "april": 4, "mai": 5, "juni": 6, "juli": 7,
           "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12},
    "fr": {"janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
           "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11,
           "décembre": 12},
    "it": {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
           "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11,
           "dicembre": 12},
}


def _date_re(lang: str) -> re.Pattern:
    months = "|".join(MONTHS[lang])
    return re.compile(rf"\b(\d{{1,2}})(?:\.|er|°|º)?\s*({months})\s+(\d{{4}})\b", U)


DATE_RE = {l: _date_re(l) for l in LANGS}
NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")

# Source citations that must never be mistaken for quantities.
SOURCE_REF_RE = re.compile(
    r"\b(?:SR|RS)\s*\d+(?:\.\d+)*|\b(?:AS|RO|RU|BBl|FF)\s+\d{4}\s+\d+", U)

# ---------------------------------------------------------------- cross-references
_SEP = {"de": r",|und|bis|–|-|sowie|oder", "fr": r",|et|à|–|-|ainsi que|ou",
        "it": r",|e|a|–|-|nonché|o"}


def _numlist(lang: str) -> str:
    sep = _SEP[lang]
    return rf"\d+[a-z]{{0,10}}(?:\s*(?:{sep})\s*\d+[a-z]{{0,10}})*"


REF_PATTERNS = {
    "de": {
        "art": rf"\b(?:Artikeln|Artikel|Art\.)\s*({_numlist('de')})",
        "para": rf"\b(?:Absätzen|Absätze|Absatz|Abs\.)\s*({_numlist('de')})",
        "lit": r"\b(?:Buchstaben|Buchstabe|Bst\.)\s*([a-z])\b",
        "item": rf"\b(?:Ziffern|Ziffer|Ziff\.)\s*({_numlist('de')})",
    },
    "fr": {
        "art": rf"\b(?:articles|article|art\.)\s*({_numlist('fr')})",
        "para": rf"\b(?:alinéas|alinéa|al\.)\s*({_numlist('fr')})",
        "lit": r"\b(?:lettres|lettre|let\.)\s*([a-z])\b",
        "item": rf"\b(?:chiffres|chiffre|ch\.)\s*({_numlist('fr')})",
    },
    "it": {
        "art": rf"\b(?:articoli|articolo|artt\.|art\.)\s*({_numlist('it')})",
        "para": rf"\b(?:capoversi|capoverso|cpv\.)\s*({_numlist('it')})",
        "lit": r"\b(?:lettere|lettera|lett\.)\s*([a-z])\b",
        "item": rf"\b(?:numeri|numero|n\.)\s*({_numlist('it')})",
    },
}
REF_RE = {l: {k: re.compile(p, U) for k, p in d.items()} for l, d in REF_PATTERNS.items()}

# ---------------------------------------------------------------- modality
# Ordered: earlier classes consume text so later ones cannot double-match.
_GAP = r"(?:[^\s,;:.()]+\s+){0,5}?"
MODAL_PATTERNS = {
    "de": [
        ("NOT_REQUIRED", rf"\b(?:muss|müssen|braucht|brauchen)\s+{_GAP}nicht\b|\b(?:ist|sind)\s+nicht\s+verpflichtet\b"),
        ("PROHIB", rf"\b(?:darf|dürfen|kann|können)\s+{_GAP}(?:nicht|kein\w*)\b|\b(?:ist|sind)\s+verboten\b|\bverboten\b"),
        ("OBLIG", r"\b(?:muss|müssen|musste|müsste)\b|\b(?:ist|sind)\s+(?:\w+\s+){0,3}?verpflichtet\b"),
        ("SOFT", r"\b(?:soll|sollen|sollte|sollten)\b"),
        ("PERM", r"\b(?:kann|können|könnte|könnten|darf|dürfen)\b"),
    ],
    "fr": [
        ("NOT_REQUIRED", r"\bn['’]?(?:est|a)\s+pas\s+(?:tenu|à)\w*|\bne\s+(?:sont|est)\s+pas\s+tenu\w*"),
        ("PROHIB", r"\bne\s+(?:\w+\s+)?(?:doit|doivent|peut|peuvent)\b|\b(?:est|sont)\s+interdit\w*|\binterdit\b"),
        ("OBLIG", r"\b(?:doit|doivent|devra|devront)\b|\b(?:est|sont)\s+tenu\w*|\ba\s+l['’]obligation\b"),
        ("SOFT", r"\b(?:devrait|devraient)\b"),
        ("PERM", r"\b(?:peut|peuvent|pourra|pourront)\b"),
    ],
    "it": [
        ("NOT_REQUIRED", r"\bnon\s+(?:è|sono)\s+tenut\w*"),
        ("PROHIB", r"\bnon\s+(?:\w+\s+)?(?:deve|devono|può|possono)\b|\b(?:è|sono)\s+vietat\w*|\bvietato\b"),
        ("OBLIG", r"\b(?:deve|devono|dovrà|dovranno)\b|\b(?:è|sono)\s+tenut\w*|\bha\s+l['’]obbligo\b"),
        ("SOFT", r"\b(?:dovrebbe|dovrebbero)\b"),
        ("PERM", r"\b(?:può|possono|potrà|potranno)\b"),
    ],
}
MODAL_RE = {l: [(c, re.compile(p, U)) for c, p in lst] for l, lst in MODAL_PATTERNS.items()}

# surface swaps for the corruption injector: (regex, replacement)
MODAL_SWAP = {
    "de": [(r"\bkann\b", "muss"), (r"\bkönnen\b", "müssen"), (r"\bmuss\b", "kann"),
           (r"\bmüssen\b", "können"), (r"\bdarf nicht\b", "muss"), (r"\bdürfen nicht\b", "müssen")],
    "fr": [(r"\bpeut\b", "doit"), (r"\bpeuvent\b", "doivent"), (r"\bdoit\b", "peut"),
           (r"\bdoivent\b", "peuvent")],
    "it": [(r"\bpuò\b", "deve"), (r"\bpossono\b", "devono"), (r"\bdeve\b", "può"),
           (r"\bdevono\b", "possono")],
}

# ---------------------------------------------------------------- negation
NEG_PATTERNS = {
    "de": r"\b(?:nicht|kein\w*|niemals|nie|weder|ohne)\b",
    "fr": r"\bne\b|\bn['’]|\bsans\b|\bnul(?:le)?s?\b",
    "it": r"\bnon\b|\bsenza\b|\bnessun\w*",
}
NEG_RE = {l: re.compile(p, U) for l, p in NEG_PATTERNS.items()}
# "ne ... que" is restrictive, not negative
FR_RESTRICTIVE = re.compile(r"^\s*((?:[^\s,;:.]+\s+){0,4}?)(?:que\b|qu['’])", U)
FR_TRUE_NEG = re.compile(r"\b(?:pas|plus|jamais|point|aucun\w*|rien|guère)\b", U)
NEG_CLUSTER_CHARS = 40
# Lexicalised phrases containing "without" that are not real negations
# (sans délai = unverzüglich = senza indugio).
NEG_IDIOMS = {
    "de": r"\bohne\s+(?:Verzug|Verzögerung|weiteres)\b",
    "fr": r"\bsans\s+(?:délai|retard|autre|plus)\b",
    "it": r"\bsenza\s+(?:indugio|ritardo|altro|ulteriore)\b",
}
NEG_IDIOM_RE = {l: re.compile(p, U) for l, p in NEG_IDIOMS.items()}

NEG_REMOVE = {
    "de": [(r"\s+nicht\b", "")],
    "fr": [(r"\bne\s+(\w+)\s+pas\b", r"\1"), (r"\bn['’](\w+)\s+pas\b", r"\1")],
    "it": [(r"\bnon\s+", "")],
}

# ---------------------------------------------------------------- quantifiers
QUANT_PATTERNS = {
    "ALL": {"de": r"\b(?:alle|allen|aller|alles|sämtliche\w*|jede[rsnm]?)\b",
            "fr": r"\b(?:tous|toutes|tout|toute|chaque)\b",
            "it": r"\b(?:tutt[ie]|tutto|ogni|ciascun\w*)\b"},
    "AT_LEAST": {"de": r"\b(?:mindestens|wenigstens)\b", "fr": r"\bau\s+moins\b",
                 "it": r"\balmeno\b"},
    "AT_MOST": {"de": r"\b(?:höchstens|maximal|längstens)\b",
                "fr": r"\bau\s+plus(?!\s+tard|\s+tôt)\b|\bau\s+maximum\b",
                "it": r"\bal\s+massimo\b|\bal\s+più(?!\s+tardi|\s+presto)\b"},
    "MORE_THAN": {"de": r"\bmehr\s+als\b", "fr": r"\bplus\s+de\b|\bplus\s+que\b",
                  "it": r"\bpiù\s+di\b|\boltre\b"},
    "LESS_THAN": {"de": r"\bweniger\s+als\b", "fr": r"\bmoins\s+de\b|\bmoins\s+que\b",
                  "it": r"\bmeno\s+di\b"},
    "LATEST": {"de": r"\bspätestens\b", "fr": r"\bau\s+plus\s+tard\b",
               "it": r"\bal\s+più\s+tardi\b"},
    "EARLIEST": {"de": r"\bfrühestens\b", "fr": r"\bau\s+plus\s+tôt\b",
                 "it": r"\bnon\s+prima\s+di\b|\bal\s+più\s+presto\b"},
    "ONLY": {"de": r"\b(?:nur|ausschliesslich|ausschliesslich|lediglich)\b",
             "fr": r"\b(?:uniquement|exclusivement|seulement)\b",
             "it": r"\b(?:solo|soltanto|solamente|esclusivamente|unicamente)\b"},
}
QUANT_RE = {c: {l: re.compile(p, U) for l, p in d.items()} for c, d in QUANT_PATTERNS.items()}
OPPOSITE_QUANT = {("AT_LEAST", "AT_MOST"), ("MORE_THAN", "LESS_THAN"),
                  ("LATEST", "EARLIEST")}

QUANT_SWAP = {
    "de": [(r"\balle\b", "einige"), (r"\bmindestens\b", "höchstens"),
           (r"\bhöchstens\b", "mindestens"), (r"\bspätestens\b", "frühestens"),
           (r"\bnur\b", "auch")],
    "fr": [(r"\btous les\b", "certains"), (r"\btoutes les\b", "certaines"),
           (r"\bau moins\b", "au plus"), (r"\bau plus\b(?! tard)", "au moins"),
           (r"\bau plus tard\b", "au plus tôt"), (r"\buniquement\b", "notamment")],
    "it": [(r"\btutti\b", "alcuni"), (r"\btutte\b", "alcune"), (r"\balmeno\b", "al massimo"),
           (r"\bal massimo\b", "almeno"), (r"\bal più tardi\b", "al più presto"),
           (r"\bsolo\b", "anche")],
}

# ---------------------------------------------------------------- terminology families
# Each family: regex per language. Confusable groups are concepts a drafter could
# mix up; a group is only compared when >= 2 languages mention a member of it.
FAMILIES = {
    "authorisation": {"de": r"bewilligung", "fr": r"\bautorisations?\b|\bpermis\b",
                      "it": r"\bautorizzazion\w*|\bpermess[oi]\b"},
    "concession": {"de": r"konzession", "fr": r"\bconcessions?\b",
                   "it": r"\bconcession[ei]\b"},
    "appeal": {"de": r"beschwerde", "fr": r"\brecours\b", "it": r"\bricors[oi]\b"},
    "objection": {"de": r"einsprache|einspruch", "fr": r"\bopposition\b", "it": r"\bopposizione\b"},
    "fine": {"de": r"\bbusse[n]?\b", "fr": r"\bamendes?\b", "it": r"\bmult[ae]\b"},
    "monetary_penalty": {"de": r"geldstrafe", "fr": r"\bpeines?\s+pécuniaires?\b",
                         "it": r"\bpene?\s+pecuniari\w*|\bpena\s+pecuniaria\b"},
    "imprisonment": {"de": r"freiheitsstrafe", "fr": r"\bpeines?\s+privatives?\s+de\s+liberté\b",
                     "it": r"\bpene?\s+detentiv\w*"},
    "federal_court": {"de": r"bundesgericht", "fr": r"\btribunal\s+fédéral\b",
                      "it": r"\btribunale\s+federale\b"},
    "fed_admin_court": {"de": r"bundesverwaltungsgericht",
                        "fr": r"\btribunal\s+administratif\s+fédéral\b",
                        "it": r"\btribunale\s+amministrativo\s+federale\b"},
    "federal_council": {"de": r"bundesrat", "fr": r"\bconseil\s+fédéral\b",
                        "it": r"\bconsiglio\s+federale\b"},
    "federal_assembly": {"de": r"bundesversammlung", "fr": r"\bassemblée\s+fédérale\b",
                         "it": r"\bassemblea\s+federale\b"},
    "confederation": {"de": r"\bbund(?:es)?\b", "fr": r"\bconfédération\b",
                      "it": r"\bconfederazione\b"},
    "canton": {"de": r"kanton", "fr": r"\bcantons?\b|\bcantonal\w*", "it": r"\bcanton[ei]\b|\bcantonal\w*"},
    "municipality": {"de": r"gemeinde", "fr": r"\bcommunes?\b|\bcommunal\w*",
                     "it": r"\bcomun[ei]\b|\bcomunal\w*"},
    "employer": {"de": r"arbeitgeber", "fr": r"\bemployeurs?\b",
                 "it": r"\bdator[ei]\s+di\s+lavoro\b"},
    "employee": {"de": r"arbeitnehmer", "fr": r"\btravailleu(?:r|se)s?\b|\bsalari[ée]\w*",
                 "it": r"\blavorator\w*|\bdipendent\w*"},
    "insurer": {"de": r"versicherer", "fr": r"\bassureurs?\b",
                "it": r"\bassicurator\w*|\bassicuratrice\b"},
    "insured": {"de": r"\bversicherte[nrms]?\b", "fr": r"\bassur[ée]e?s?\b",
                "it": r"\bassicurat[oiae]\b"},
    "creditor": {"de": r"gläubiger", "fr": r"\bcréanc(?:ier|ière)s?\b", "it": r"\bcreditor\w*|\bcreditrice\b"},
    "debtor": {"de": r"schuldner", "fr": r"\bdébiteurs?\b|\bdébitrice\b", "it": r"\bdebitor\w*|\bdebitrice\b"},
    "seller": {"de": r"verkäufer", "fr": r"\bvendeu(?:r|se)s?\b", "it": r"\bvenditor\w*|\bvenditrice\b"},
    "buyer": {"de": r"\bkäufer", "fr": r"\bacheteu(?:r|se)s?\b", "it": r"\bacquirent\w*|\bcompratore\b"},
    "lessor": {"de": r"vermieter", "fr": r"\bbailleu(?:r|resse)s?\b", "it": r"\blocator\w*|\blocatrice\b"},
    "lessee": {"de": r"\bmieter", "fr": r"\blocataires?\b", "it": r"\bconduttor\w*|\binquilin\w*"},
    "plaintiff": {"de": r"\bkläger", "fr": r"\bdemandeu(?:r|se)s?\b|\bdemanderesses?\b",
                  "it": r"\battore\b|\battrice\b|\battori\b"},
    "defendant": {"de": r"\bbeklagte", "fr": r"\bdéfendeu(?:r|se)s?\b|\bdéfenderesses?\b",
                  "it": r"\bconvenut[oai]\b|\bconvenute\b"},
    "natural_person": {"de": r"natürliche\w*\s+person", "fr": r"\bpersonnes?\s+physiques?\b",
                       "it": r"\bperson\w*\s+fisic\w*"},
    "legal_person": {"de": r"juristische\w*\s+person", "fr": r"\bpersonnes?\s+morales?\b",
                     "it": r"\bperson\w*\s+giuridic\w*"},
}
FAMILY_RE = {n: {l: re.compile(p, U) for l, p in d.items()} for n, d in FAMILIES.items()}

# (members, severity-if-mixed-up)
CONFUSABLE_GROUPS = [
    (("creditor", "debtor"), "high"), (("seller", "buyer"), "high"),
    (("lessor", "lessee"), "high"), (("plaintiff", "defendant"), "high"),
    (("insurer", "insured"), "high"), (("employer", "employee"), "high"),
    (("fine", "monetary_penalty", "imprisonment"), "high"),
    (("natural_person", "legal_person"), "high"),
    (("federal_court", "fed_admin_court"), "medium"),
    (("federal_council", "federal_assembly"), "medium"),
    (("confederation", "canton", "municipality"), "medium"),
    (("authorisation", "concession"), "medium"),
    (("appeal", "objection"), "medium"),
]
