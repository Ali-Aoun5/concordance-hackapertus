"""Generate data/demo/synthetic_corpus.json.

SYNTHETIC: an invented act written for smoke-testing and the demo. It is NOT Swiss
law. Five articles carry deliberately planted divergences (listed under meta.planted)
so the tool has something to find even before real Fedlex data is ingested.
"""
import json
from pathlib import Path

NB = "\u00a0"

ARTICLES = [
    ("art_1", "Art. 1", None,
     "Dieses Gesetz regelt die Gewährung von Beiträgen an Organisationen, die Projekte zur Förderung der Mehrsprachigkeit durchführen.",
     "La présente loi règle l’octroi de contributions aux organisations qui réalisent des projets visant à promouvoir le plurilinguisme.",
     "La presente legge disciplina la concessione di contributi alle organizzazioni che realizzano progetti volti a promuovere il plurilinguismo."),
    ("art_2", "Art. 2", None,
     "Das Gesuch ist spätestens 30 Tage vor Projektbeginn bei der zuständigen Behörde einzureichen. Es muss die Projektbeschreibung und den Finanzierungsplan enthalten.",
     "La demande doit être déposée auprès de l’autorité compétente au plus tard 30 jours avant le début du projet. Elle doit contenir la description du projet et le plan de financement.",
     "La domanda deve essere presentata all’autorità competente al più tardi 30 giorni prima dell’inizio del progetto. Essa deve contenere la descrizione del progetto e il piano di finanziamento."),
    ("art_3", "Art. 3", None,
     "Der Beitrag beträgt höchstens 50 Prozent der anrechenbaren Kosten. Er darf 200’000 Franken pro Projekt nicht übersteigen.",
     f"La contribution s’élève au plus à 50 pour cent des coûts imputables. Elle ne peut pas dépasser 200{NB}000 francs par projet.",
     f"Il contributo ammonta al massimo al 50 per cento dei costi computabili. Non può superare 200{NB}000 franchi per progetto."),
    ("art_4", "Art. 4", "modality",
     "Die Behörde kann den Beitrag verweigern, wenn das Projekt den Zielen dieses Gesetzes nicht entspricht.",
     "L’autorité doit refuser la contribution lorsque le projet ne correspond pas aux buts de la présente loi.",
     "L’autorità può rifiutare il contributo se il progetto non corrisponde agli scopi della presente legge."),
    ("art_5", "Art. 5", "number",
     "Die Behörde entscheidet innert 60 Tagen nach Eingang des vollständigen Gesuchs.",
     "L’autorité statue dans un délai de 60 jours à compter de la réception de la demande complète.",
     "L’autorità decide entro 30 giorni dal ricevimento della domanda completa."),
    ("art_6", "Art. 6", "reference",
     "Wer Beiträge zu Unrecht bezogen hat, muss sie zurückerstatten. Die Rückerstattung richtet sich nach Artikel 7 Absatz 2.",
     "Quiconque a perçu indûment des contributions doit les restituer. La restitution est régie par l’article 8, alinéa 2.",
     "Chi ha percepito indebitamente contributi deve restituirli. La restituzione è disciplinata dall’articolo 7 capoverso 2."),
    ("art_7", "Art. 7", None,
     "Die Behörde verfügt die Rückerstattung. Die Verfügung kann innert 30 Tagen mit Beschwerde angefochten werden. Das Verfahren richtet sich nach dem Verwaltungsverfahrensgesetz.",
     "L’autorité ordonne la restitution par voie de décision. La décision peut faire l’objet d’un recours dans les 30 jours. La procédure est régie par la loi sur la procédure administrative.",
     "L’autorità ordina la restituzione mediante decisione. La decisione può essere impugnata con ricorso entro 30 giorni. La procedura è retta dalla legge sulla procedura amministrativa."),
    ("art_8", "Art. 8", "terminology",
     "Der Arbeitgeber muss der Behörde jede Änderung der Projektleitung unverzüglich melden.",
     "Le travailleur doit annoncer sans délai à l’autorité toute modification de la direction du projet.",
     "Il datore di lavoro deve comunicare senza indugio all’autorità ogni modifica della direzione del progetto."),
    ("art_9", "Art. 9", None,
     "Dieses Gesetz tritt am 1. Januar 2028 in Kraft.",
     "La présente loi entre en vigueur le 1er janvier 2028.",
     "La presente legge entra in vigore il 1° gennaio 2028."),
    ("art_10", "Art. 10", "negation",
     "Beiträge dürfen nicht für Projekte gewährt werden, die bereits begonnen haben.",
     "Les contributions ne peuvent pas être accordées pour des projets déjà commencés.",
     "I contributi possono essere concessi per progetti già iniziati."),
]


def main():
    arts = []
    planted = {}
    for art_id, num, plant, de, fr, it in ARTICLES:
        arts.append({"art_id": art_id, "num": num, "texts": {"de": de, "fr": fr, "it": it}})
        if plant:
            planted[art_id] = plant
    corpus = {
        "meta": {
            "name": "synthetic_demo",
            "synthetic": True,
            "note": "Invented text for smoke tests. Not Swiss law. Do not cite.",
            "license": "CC0-1.0",
            "planted": planted,
        },
        "acts": [{
            "act_id": "SYN-1",
            "title": {"de": "Synthetisches Beispielgesetz", "fr": "Loi synthétique d’exemple",
                      "it": "Legge sintetica d’esempio"},
            "sources": {},
            "articles": arts,
            "unaligned": [],
        }],
    }
    out = Path(__file__).resolve().parents[1] / "data" / "demo" / "synthetic_corpus.json"
    out.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
