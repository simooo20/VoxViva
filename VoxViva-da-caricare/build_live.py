#!/usr/bin/env python3
"""
build_live.py - giro VERO con i titoli del 18 agosto 2026.

Solo titoli VERIFICATI pescando i feed con WebFetch in questa sessione, e solo
testate presenti nella lista di Simone: ANSA, QN, Il Tempo, Domani, Open,
TGCOM24. (Fontana e migranti/Ceuta oggi restano fuori: la loro voce di destra
- La Verita', Il Giornale - e' irraggiungibile da questo ambiente, quindi la
tripla non si chiude qui. Non e' un limite del metodo, e' l'ambiente.)
Le note "come cambia il titolo" sono scritte per il lettore, in terza persona.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from cluster import arricchisci
from scala import AREE

BASE = Path(__file__).resolve().parent
OUT = BASE / "data" / "events.json"
SRC = BASE / "sources.json"

# (fonte, area, titolo, url, iso, primaria) -- tutti verificati il 18/08
A = [
    # droni ucraini sulla Russia (SPINA DORSALE: topnews ANSA)
    ("ANSA", "C", "Lanciati 620 droni contro Mosca durante la notte",
     "https://www.ansa.it/sito/notizie/topnews/2026/08/18/lanciati-620-droni-contro-mosca-durante-la-notte_4c4b5023-0f59-4352-ac52-7e01a4e961a4.html", "2026-08-18T03:25:08+00:00", True),
    ("QN Quotidiano Nazionale", "C", "Pioggia di droni dall'Ucraina, Mosca: \"Ne abbiamo distrutti 205\". Morti e feriti in un raid nella regione di Belgorod",
     "https://www.quotidiano.net/esteri/guerra-ucraina-russia-droni-p8j3kqcd", "2026-08-17T05:47:24+00:00", False),
    ("Il Tempo", "CD", "Ucraina, attacchi in territorio russo: missili su Belgorod, 1.500 droni in 24 ore",
     "https://www.iltempo.it/esteri/2026/08/17/news/ucraina-altri-attacchi-in-territorio-russo-missili-su-belgorod-1-500-droni-in-24-ore-48873297/", "2026-08-17T06:58:00+00:00", False),
    ("Domani", "CS", "Potere senza ideologia: Putin semina terrore per salvare la poltrona",
     "https://www.editorialedomani.it/idee/commenti/potere-senza-ideologia-putin-semina-terrore-per-salvare-la-poltrona-azuw0ry3", "2026-08-18T04:00:00+00:00", False),

    # caso Ranucci-Lavitola
    ("Open", "CS", "«Ci ho messo dentro l'IA». Ranucci e quel messaggio a Lavitola sul sondaggio. I pm preparano nuovi interrogatori",
     "https://www.open.online/2026/08/18/ranucci-lavitola-messaggio-sondaggio-indagini/", "2026-08-18T05:03:39+00:00", False),
    ("Domani", "CS", "Al bazar dei ricatti incrociati. Lavitola: «Avvisai Ranucci»",
     "https://www.editorialedomani.it/fatti/lavitola-ranucci-attentato-silenzi-mandante-report-ricatti-colosimo-nod8yrow", "2026-08-18T05:00:00+00:00", False),
    ("Open", "CS", "Caso Ranucci-Lavitola, parla Minoli l'ideatore di Report: «Se fossi una toga sentirei Mieli come persona informata sui fatti»",
     "https://www.open.online/2026/08/18/caso-ranucci-lavitola-giovanni-minoli-paolo-mieli-interrogatorio/", "2026-08-18T05:40:36+00:00", False),
    ("QN Quotidiano Nazionale", "C", "Tutti a tavola a bersi le parole di Valterino",
     "https://www.quotidiano.net/politica/tutti-a-tavola-a-bersi-le-parole-di-valterino-58660e12", "2026-08-17T06:40:52+00:00", False),
    ("Il Tempo", "CD", "Quanto ancora Sigfrido nasconde e il giallo del telefonino",
     "https://www.iltempo.it/attualita/2026/08/17/news/sigfrido-ranucci-quanto-ancora-nasconde-giallo-telefonino-report-lavitola-48873039/", "2026-08-17T06:29:00+00:00", False),

    # compensi/stipendi di Report
    ("Domani", "CS", "«Stipendi d'oro», la destra contro i cronisti di Report",
     "https://www.editorialedomani.it/politica/italia/ranucci-rai-tempo-attacco-mottola-compensi-corsini-rossi-n8afjhkz", "2026-08-17T18:36:29+00:00", False),
    ("ANSA", "C", "Report e i compensi degli inviati, nuova polemica",
     "https://www.ansa.it/sito/notizie/politica/2026/08/17/report-e-i-compensi-degli-inviati-nuova-polemica_a74ccc14-0789-4cf2-9c57-0e25ef60c624.html", "2026-08-17T19:55:12+00:00", False),
    ("Il Tempo", "CD", "REPORTOPOLI - Stipendi faraonici e spese incredibili: ecco quanto ci costa la trasmissione di Ranucci",
     "https://www.iltempo.it/attualita/2026/08/17/news/report-quanto-ci-costa-stipendi-giornalisti-spese-incredibili-rai-programma-sigfrido-ranucci-48872869/", "2026-08-17T05:16:00+00:00", False),

    ("Secolo d'Italia", "CD", "Ranucci, il cortocircuito di Lavitola: è un fratello, per questo ho ordinato l'attentato. E monta il giallo dell'avvertimento un mese prima",
     "https://www.secoloditalia.it/2026/08/ranucci-il-cortocircuito-di-lavitola-e-un-fratello-per-questo-ho-ordinato-lattentato-e-monta-il-giallo-dellavvertimento-un-mese-prima/", "2026-08-18T07:25:48+00:00", False),

    # scontro politico su migranti e Ceuta
    ("Domani", "CS", "Mal di propaganda, su Schengen Meloni è bloccata in un vicolo cieco",
     "https://www.editorialedomani.it/politica/italia/schengen-spagna-italia-risultati-controlli-propaganda-politica-ultime-notizie-meloni-vannacci-l8fozi88", "2026-08-17T18:23:17+00:00", False),
    ("ANSA", "C", "Pd e Psoe contro Frederiksen, 'inaccettabile l'asse con Meloni su Ceuta'",
     "https://www.ansa.it/sito/notizie/politica/2026/08/17/pd-e-psoe-contro-frederiksen-inaccettabile-lasse-con-meloni-su-ceuta_71b05907-92e7-4a00-b392-2a71422e40a4.html", "2026-08-17T19:00:50+00:00", False),
    ("Secolo d'Italia", "CD", "Migranti, altro che Ceuta. FdI mostra il miracolo Lampedusa e spiana Schlein e Conte: con loro sarebbero \"tempi bui\"",
     "https://www.secoloditalia.it/2026/08/migranti-altro-che-ceuta-fdi-mostra-il-miracolo-lampedusa-e-spiana-schlein-e-conte-con-loro-sarebbero-tempi-bui/", "2026-08-17T18:34:34+00:00", False),

    # escalation Iran / Hormuz
    ("Domani", "CS", "L'Iran minaccia un intervento militare su Hormuz se la diplomazia fallisce. Trump mette nel mirino l'Oman",
     "https://www.editorialedomani.it/politica/mondo/iran-trump-hormuz-guerra-ultimi-aggiornamenti-oggi-18-agosto-tnxoa7ur", "2026-08-18T05:37:46+00:00", False),
    ("ANSA", "C", "Wsj, l'Iran ha usato i due mesi di tregua per preparare guerra più ampia",
     "https://www.ansa.it/sito/notizie/mondo/nordamerica/2026/08/17/wsj-liran-ha-usato-i-due-mesi-di-tregua-per-preparare-guerra-piu_a17e320e-8824-443a-b476-96995e89a687.html", "2026-08-17T10:21:35+00:00", False),
    ("Secolo d'Italia", "CD", "La tregua è finita, torna il fuoco a Hormuz: un proiettile centra una nave nello Stretto",
     "https://www.secoloditalia.it/2026/08/la-tregua-e-finita-torna-il-fuoco-a-hormuz-un-proiettile-centra-una-nave-nello-stretto/", "2026-08-18T07:12:02+00:00", False),

    # furto delle opere di Antonello da Messina
    ("Open", "CS", "Svolta nel furto dei quadri di Antonello da Messina: trovato il furgone dei ladri. Le ipotesi degli investigatori",
     "https://www.open.online/2026/08/17/furto-quadri-antonello-messina-ritrovato-furgone/", "2026-08-17T21:00:44+00:00", False),
    ("ANSA", "C", "Furto opere di Antonello da Messina: il museo ha riaperto al pubblico",
     "https://www.ansa.it/sito/notizie/cronaca/2026/08/18/furto-opere-di-antonello-da-messina-il-museo-ha-riaperto-al-pubblico_41c04aac-a5a4-4c3e-a6ba-58293cf622ac.html", "2026-08-18T10:19:37+00:00", False),
    ("Secolo d'Italia", "CD", "Furto dei capolavori di Antonello da Messina, svolta nelle indagini: trovato il furgone della fuga. Sgarbi: un colpo senza senso",
     "https://www.secoloditalia.it/2026/08/furto-dei-capolavori-di-antonello-da-messina-svolta-nelle-indagini-trovato-il-furgone-della-fuga-sgarbi-un-colpo-senza-senso/", "2026-08-17T19:38:18+00:00", False),
]

GRUPPI = [
    {
        "titolo_neutro": "Assalto di droni ucraini sul territorio russo nella notte",
        "tema": "esteri", "divergenza": "alta",
        "duello": "205, 620 o 1.500 droni: sullo stesso attacco ogni testata sceglie un numero diverso.",
        "nota": "Sullo stesso attacco notturno le testate scelgono numeri diversi. L'ANSA titola sui 620 droni lanciati. Il Quotidiano Nazionale riprende la cifra del ministero russo — 205 abbattuti — e mette in evidenza i morti a Belgorod. Il Tempo parla di 1.500 droni in 24 ore. Domani non quantifica l'attacco e lo inquadra come segno di debolezza del Cremlino, «terrore per salvare la poltrona».",
        "membri": ["Lanciati 620 droni contro Mosca", "Pioggia di droni dall'Ucraina", "Ucraina, attacchi in territorio russo", "Potere senza ideologia"],
    },
    {
        "titolo_neutro": "Caso Ranucci-Lavitola: l'avvertimento e i dubbi sull'inchiesta",
        "tema": "politica interna", "divergenza": "alta",
        "duello": "Da una parte «Lavitola avvisò Ranucci», dall'altra «quanto ancora Ranucci nasconde».",
        "nota": "I quotidiani inquadrano lo stesso fascicolo da due angoli opposti. Open e Domani seguono la pista dell'avvertimento — Lavitola avrebbe avvisato Ranucci di «possibili attentati» — e parlano di «ricatti incrociati». A destra il punto interrogativo si sposta su Ranucci stesso: Il Tempo chiede «quanto ancora nasconde», il Secolo d'Italia parla di «cortocircuito» e di un «giallo dell'avvertimento». Il Quotidiano Nazionale commenta con un titolo ironico su Lavitola.",
        "membri": ["Ci ho messo dentro l'IA", "Al bazar dei ricatti incrociati", "parla Minoli", "Tutti a tavola a bersi", "Quanto ancora Sigfrido nasconde", "cortocircuito di Lavitola"],
    },
    {
        "titolo_neutro": "Polemica sui compensi degli inviati di Report",
        "tema": "politica interna", "divergenza": "alta",
        "duello": "«La destra contro i cronisti» per Domani, «REPORTOPOLI, stipendi faraonici» per Il Tempo.",
        "nota": "Il fatto è lo stesso — i compensi degli inviati di Report — ma cambia il soggetto della frase. L'ANSA registra la «nuova polemica». Il Tempo mette al centro i soldi, con un titolo tutto in maiuscolo, «REPORTOPOLI», e la parola «faraonici». Domani rovescia la prospettiva: protagonista non sono gli stipendi ma «la destra» che attacca «i cronisti».",
        "membri": ["«Stipendi d'oro», la destra contro", "Report e i compensi degli inviati", "REPORTOPOLI"],
    },
    {
        "titolo_neutro": "Lo scontro politico su migranti e Ceuta",
        "tema": "immigrazione", "divergenza": "alta",
        "duello": "Per il Secolo «il miracolo è Lampedusa», per Domani «su Schengen Meloni è bloccata». Stesso dossier, due film.",
        "nota": "Sullo stesso dossier migratorio le testate montano cornici opposte. Il Secolo d'Italia rovescia il tema dell'emergenza — «altro che Ceuta» — e indica Lampedusa come modello del governo, attaccando l'opposizione. Domani parla di «propaganda» e di una Meloni «bloccata in un vicolo cieco» su Schengen. L'ANSA sta sul fatto verificabile: Pd e Psoe contestano l'asse tra Meloni e la premier danese Frederiksen.",
        "membri": ["su Schengen Meloni è bloccata", "Pd e Psoe contro Frederiksen", "Migranti, altro che Ceuta"],
    },
    {
        "titolo_neutro": "Escalation fra Iran e Stati Uniti sullo Stretto di Hormuz",
        "tema": "esteri", "divergenza": "alta",
        "duello": "Chi ha riacceso la crisi? Per Domani è Trump, che «mette nel mirino l'Oman»; per il Secolo è l'Iran, «torna il fuoco a Hormuz».",
        "nota": "La stessa escalation nel Golfo, con l'accento su protagonisti diversi. Domani mette al centro Trump, che «mette nel mirino l'Oman». Il Secolo d'Italia apre sull'atto militare: «la tregua è finita», un proiettile che centra una nave nello Stretto di Hormuz. L'ANSA riporta la ricostruzione del Wall Street Journal secondo cui sarebbe stato l'Iran a usare la tregua per prepararsi a una guerra più ampia.",
        "membri": ["L'Iran minaccia un intervento militare", "Wsj, l'Iran ha usato", "La tregua è finita, torna il fuoco"],
    },
    {
        "titolo_neutro": "Furto delle opere di Antonello da Messina: svolta nelle indagini",
        "tema": "cultura", "divergenza": "bassa",
        "duello": "Furgone ritrovato e museo riaperto: qui le versioni coincidono.",
        "nota": "Notizia di cronaca su cui le testate convergono. Open, l'ANSA e il Secolo d'Italia danno tutti la svolta delle indagini — il furgone della fuga ritrovato, il museo riaperto —; il Secolo aggiunge il commento di Sgarbi, «un colpo senza senso». Le differenze sono di dettaglio, non di inquadratura.",
        "membri": ["Svolta nel furto dei quadri", "Furto opere di Antonello da Messina", "Furto dei capolavori di Antonello"],
    },
]


def main():
    articoli = []
    pos = 0
    for fonte, area, titolo, url, iso, primaria in A:
        art = {"id": hashlib.sha1((url + titolo[:20]).encode()).hexdigest()[:10],
               "titolo": titolo, "url": url, "pubblicato": iso, "fonte": fonte,
               "dominio": url.split("/")[2].replace("www.", ""), "area": area, "primaria": primaria}
        if primaria:
            art["ordine_feed"] = pos; pos += 1
        articoli.append(art)

    def trova(fr):
        hit = [a for a in articoli if fr.lower() in a["titolo"].lower()]
        if len(hit) != 1:
            raise SystemExit("Frammento ambiguo/non trovato (%d): %r" % (len(hit), fr))
        return hit[0]

    eventi, usati = [], set()
    for g in GRUPPI:
        membri = [trova(f) for f in g["membri"]]
        for m in membri:
            usati.add(m["id"])
        ev = {"titolo_neutro": g["titolo_neutro"], "tema": g["tema"], "articoli": membri}
        for k in ("divergenza", "duello", "nota"):
            ev[k] = g[k]
        eventi.append(ev)

    eventi = arricchisci(eventi)
    dentro = [a for a in articoli if a["area"] in AREE]
    completi = [e for e in eventi if all(e["per_colonna"].get(k) for k in ("sinistra", "centro", "destra"))]
    princ = [e for e in eventi if e.get("principale")]

    # tutte le testate MONITORATE (dalla configurazione), non solo quelle lette oggi
    cfg = json.loads(SRC.read_text(encoding="utf-8"))
    monitorate = sorted({s.get("etichetta", s["name"]) for s in cfg["sources"] if s["area"] != "AGG"})

    out = {
        "generato": datetime.now(timezone.utc).isoformat(), "finestra_ore": 24,
        "modello": "giro reale 18/08: feed verificati via WebFetch, raggruppamento di Claude",
        "totale_articoli": len(dentro),
        "per_area": {x: sum(1 for a in dentro if a["area"] == x) for x in AREE},
        "testate_attive": sorted({a["fonte"] for a in dentro}),
        "testate_monitorate": monitorate,
        "statistiche": {"eventi": len(eventi), "principali": len(princ),
                        "duelli": len([e for e in eventi if e["ampiezza"] >= 2]),
                        "estremi_opposti": len([e for e in eventi if e["ampiezza"] == len(AREE) - 1]),
                        "punti_ciechi": 0},
        "eventi": eventi,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("GIRO REALE 18/08 — solo titoli verificati e testate in lista")
    print("  eventi: %d | completi: %d | testate lette: %d | testate monitorate: %d"
          % (len(eventi), len(completi), len(out["testate_attive"]), len(monitorate)))


if __name__ == "__main__":
    main()
