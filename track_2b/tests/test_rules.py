from concordance.rules import rule_divergences, extract_quantities, norm_number

def by_art(demo):
    meta, arts = demo
    return {a.art_id: rule_divergences(a.texts) for a in arts}, meta

def test_planted_divergences_found_with_right_type_and_language(demo):
    res, meta = by_art(demo)
    expect = {"art_4": ("modality", "fr"), "art_5": ("number", "it"), "art_6": ("reference", "fr"),
              "art_8": ("terminology", "fr"), "art_10": ("modality", "it")}
    for art, (typ, lang) in expect.items():
        hits = [d for d in res[art] if d.type == typ]
        assert hits, f"{art}: {typ} not found"
        assert lang in hits[0].languages_at_fault

def test_clean_articles_have_no_false_alarms(demo):
    res, meta = by_art(demo)
    for art in ("art_1", "art_2", "art_3", "art_7", "art_9"):
        assert res[art] == [], (art, [d.explanation for d in res[art]])

def test_number_formats():
    assert norm_number("200’000") == "200000"
    assert norm_number("2,50") == "2.5"
    q = extract_quantities("innerhalb von 30 Tagen", "de")
    assert (q[0].value, q[0].unit) == ("30", "day")
    q = extract_quantities("dans un délai de trente jours", "fr")
    assert (q[0].value, q[0].unit) == ("30", "day")
    q = extract_quantities("Fr. 500", "de")
    assert q[0].unit == "chf"

def test_spelled_number_cancels_bare_numeral():
    t = {"de": "Es sind fünf Mitglieder zu wählen und der Rat tagt öffentlich im Saal.",
         "fr": "Il faut élire 5 membres et le conseil siège publiquement dans la salle.",
         "it": "Si devono eleggere cinque membri e il consiglio siede pubblicamente nella sala."}
    assert [d for d in rule_divergences(t) if d.type == "number"] == []

def test_idiom_sans_delai_not_a_negation():
    t = {"de": "Die Behörde meldet dies unverzüglich der Stelle im Kanton.",
         "fr": "L’autorité l’annonce sans délai au service du canton.",
         "it": "L’autorità lo comunica senza indugio al servizio del cantone."}
    assert [d for d in rule_divergences(t) if d.type == "negation"] == []

def test_ne_que_is_not_negation():
    t = {"de": "Der Beitrag wird nur an Vereine ausgerichtet, die ihren Sitz im Inland haben.",
         "fr": "La contribution n’est accordée qu’aux associations ayant leur siège en Suisse.",
         "it": "Il contributo è concesso solo alle associazioni con sede in Svizzera."}
    assert [d for d in rule_divergences(t) if d.type == "negation"] == []

def test_date_mismatch():
    t = {"de": "Es tritt am 1. Januar 2028 in Kraft und gilt unbefristet für alle Fälle.",
         "fr": "Elle entre en vigueur le 1er janvier 2029 et s’applique sans limite à tous les cas.",
         "it": "Entra in vigore il 1° gennaio 2028 e si applica senza limiti a tutti i casi."}
    d = [x for x in rule_divergences(t) if x.type == "date"]
    assert d and d[0].languages_at_fault == ["fr"]


def test_ne_peuvent_que_is_a_permission_not_a_prohibition():
    t = {"de": "Personendaten dürfen nur zu einem bestimmten und erkennbaren Zweck beschafft werden.",
         "fr": "Les données personnelles ne peuvent être collectées que pour des finalités déterminées et reconnaissables.",
         "it": "I dati personali possono essere raccolti soltanto per uno scopo determinato e riconoscibile."}
    assert [d for d in rule_divergences(t) if d.type == "modality"] == []


def test_swap_hidden_from_article_level_sets_is_caught_per_sentence():
    # DE has both a permission and an obligation, but in the wrong sentences: whole-article
    # sets {PERM, OBLIG} are identical in all languages, so only sentence alignment sees it.
    t = {"de": "Die Behörde muss den Beitrag kürzen. Der Gesuchsteller kann die Kosten tragen.",
         "fr": "L’autorité peut réduire la contribution. Le requérant doit supporter les coûts.",
         "it": "L’autorità può ridurre il contributo. Il richiedente deve sostenere i costi."}
    hits = [d for d in rule_divergences(t) if d.type == "modality"]
    assert hits and all(d.unit for d in hits) and all(d.languages_at_fault == ["de"] for d in hits)

def test_unaligned_structure_falls_back_to_whole_article():
    from concordance.sentences import align_units
    t = {"de": "Ein Satz.\nNoch ein Absatz.", "fr": "Un seul bloc de texte", "it": "Una frase.\nUn altro paragrafo."}
    assert align_units(t) is None

def test_corresponding_sentences_are_not_confused():
    t = {"de": "Personendaten dürfen nur so bearbeitet werden. Die Behörde muss dies prüfen und dokumentieren.",
         "fr": "Les données ne peuvent être traitées que de cette manière. L’autorité doit vérifier et documenter cela.",
         "it": "I dati possono essere trattati soltanto in questo modo. L’autorità deve verificarlo e documentarlo."}
    assert [d for d in rule_divergences(t) if d.type in ("modality", "quantifier")] == []
