from concordance.fedlex import parse_akn, align_acts

NS = 'xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0"'

def doc(arts, title="T"):
    body = "".join(arts)
    return (f'<akomaNtoso {NS}><act><meta><identification><FRBRWork><FRBRname value="{title}"/></FRBRWork>'
            f'</identification></meta><body>{body}</body></act></akomaNtoso>').encode()

def art(eid, num, *paras):
    ps = "".join(f'<paragraph eId="{eid}/para_{i+1}"><num>{i+1}</num><content><p>{t}</p></content></paragraph>'
                 for i, t in enumerate(paras))
    return f'<article eId="{eid}"><num><b>{num}</b></num><heading>H</heading>{ps}</article>'

def test_parse_skips_numbers_headings_and_notes():
    x = doc([art("art_1", "Art. 1", "Erster Absatz.", "Zweiter Absatz.")])
    p = parse_akn(x)
    a = p["articles"]["art_1"]
    assert a["num"] == "Art. 1"
    assert a["text"] == "Erster Absatz.\nZweiter Absatz."

def test_footnotes_are_ignored():
    x = (f'<akomaNtoso {NS}><act><body><article eId="art_2"><num>Art. 2</num><paragraph eId="p">'
         f'<content><p>Text<authorialNote marker="1"><p>Fussnote</p></authorialNote> weiter.</p></content>'
         f'</paragraph></article></body></act></akomaNtoso>').encode()
    assert parse_akn(x)["articles"]["art_2"]["text"] == "Text weiter."

def test_alignment_and_unaligned():
    de = parse_akn(doc([art("art_1", "Art. 1", "a"), art("art_2", "Art. 2", "b")]))
    fr = parse_akn(doc([art("art_1", "Art. 1", "a"), art("art_2", "Art. 2", "b"), art("art_3", "Art. 3", "c")]))
    it = parse_akn(doc([art("art_1", "Art. 1", "a")]))
    aligned, un = align_acts({"de": de, "fr": fr, "it": it})
    assert [a["art_id"] for a in aligned] == ["art_1"]
    by = {u["art_id"]: u for u in un}
    assert by["art_2"]["missing_in"] == ["it"] and by["art_3"]["missing_in"] == ["de", "it"]


def test_footnote_text_does_not_leak_into_article_label():
    x = (f'<akomaNtoso {NS}><act><body><article eId="art_11a"><num>Art. 11a<authorialNote marker="1">'
         f'<p>Eingefügt durch Anhang Ziff. 3 des BG vom 4. Okt. 1991</p></authorialNote></num>'
         f'<paragraph eId="p"><content><p>Text.</p></content></paragraph></article></body></act></akomaNtoso>').encode()
    assert parse_akn(x)["articles"]["art_11a"]["num"] == "Art. 11a"
