from concordance.prompts import evidence_sentences, verify_messages

def test_evidence_sentence_is_the_one_with_the_span():
    texts = {"de": "Erster Satz ohne Besonderheit. Die Behörde kann den Beitrag verweigern. Dritter Satz.",
             "fr": "Première phrase. L’autorité doit refuser la contribution. Troisième phrase.",
             "it": "Prima frase. L’autorità può rifiutare il contributo. Terza frase."}
    ev = evidence_sentences(texts, {"de": ["kann"], "fr": ["doit"], "it": ["può"]})
    assert ev["de"].startswith("Die Behörde kann") and "Erster" not in ev["de"]
    assert ev["fr"].startswith("L’autorité doit")

def test_date_with_ordinal_dot_does_not_split_sentence():
    ev = evidence_sentences({"de": "Das Gesetz vom 25. September 2020 tritt in Kraft."}, {"de": ["tritt"]})
    assert ev["de"].startswith("Das Gesetz vom 25. September")

def test_verify_prompt_contains_sentences_and_question():
    texts = {"de": "Die Behörde kann zahlen.", "fr": "L’autorité doit payer.", "it": "L’autorità può pagare."}
    cand = [{"type": "modality", "origins": ["rules"], "languages_at_fault": ["fr"],
             "spans": {"de": ["kann"], "fr": ["doit"], "it": ["può"]}, "explanation": "Modal force differs."}]
    msg = verify_messages("T", "Art. 1", texts, cand)[1]["content"]
    assert "corresponding sentences" in msg and "how to judge" in msg and "L’autorité doit payer." in msg
