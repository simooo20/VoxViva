#!/usr/bin/env python3
"""
cluster.py - passo 2 di 3. Il cuore del progetto.

Prende data/articles.json e raggruppa gli articoli per EVENTO, non per
somiglianza di parole. Il punto: destra e sinistra usano parole diverse per
la stessa notizia, quindi la sovrapposizione lessicale è il segnale peggiore
possibile. Qui il raggruppamento lo fa un modello che capisce di cosa si parla.

Due passaggi:
  1. RAGGRUPPA - il modello vede id, titolo, ora e testata, ma NON vede
     la posizione politica. Così non può raggruppare per schieramento.
     Restituisce solo liste di id più un titolo neutro per l'evento.
  2. ANALIZZA - solo sugli eventi in cui la scala è coperta in due punti
     distanti, il modello vede i titoli con l'etichetta e spiega come cambia
     l'inquadratura fra il più a sinistra e il più a destra.

Il modello non riscrive mai i titoli: ritorna id, e i titoli veri li rimette
Python pescandoli dal json. Così non può inventare niente.

    export ANTHROPIC_API_KEY=sk-ant-...
    python cluster.py
    python cluster.py --no-analisi     # salta il passo 2, costa meno
"""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from scala import (AGGREGATORE, AREE, BREVI, COLONNA_DI, COLONNE, NOMI,
                   estremi, ordina_da_sinistra, riferimento_centro)

import re as _re
import urllib.request

UA = "IlVaglio/1.0 (analisi comparativa di titoli non commerciale; +mailto:tuo@indirizzo.it)"

BASE = Path(__file__).resolve().parent
IN = BASE / "data" / "articles.json"


def leggi_incipit(url, max_chars=700):
    """Scarica l'articolo e ne estrae l'incipit (og:description + primi <p>).

    Serve SOLO per informare l'analisi «come cambia il titolo»: il testo NON
    viene mai pubblicato, sul sito restano titolo e link. Best-effort: se il
    fetch fallisce (paywall, blocco) ritorna stringa vuota e si analizza dal
    solo titolo. Da questo container il fetch diretto e' bloccato; funziona
    dall'hosting vero.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
    except Exception:
        return ""
    testo = ""
    m = _re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:description|description)["\'][^>]+content=["\']([^"\']+)', html, _re.I)
    if m:
        testo = m.group(1).strip()
    for para in _re.findall(r"<p[^>]*>(.*?)</p>", html, _re.I | _re.S):
        t = _re.sub(r"<[^>]+>", " ", para)
        t = _re.sub(r"\s+", " ", t).strip()
        if len(t) > 60:
            testo += " " + t
        if len(testo) > max_chars:
            break
    return _re.sub(r"\s+", " ", testo).strip()[:max_chars]
OUT = BASE / "data" / "events.json"

MODELLO = os.environ.get("ILVAGLIO_MODEL", "claude-sonnet-4-5")

SCHEMA_RAGGRUPPA = {
    "name": "registra_eventi",
    "description": "Registra gli eventi trovati raggruppando i titoli.",
    "input_schema": {
        "type": "object",
        "properties": {
            "eventi": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "titolo_neutro": {
                            "type": "string",
                            "description": "Come descriverebbe l'evento un'agenzia di stampa: fatto, luogo, attori. Massimo 90 caratteri, nessun aggettivo valutativo, nessuna virgoletta di dichiarazione.",
                        },
                        "fatto_specifico": {
                            "type": "string",
                            "description": "Il fatto singolo e concreto a cui questo gruppo si riferisce, scritto come CHI ha fatto COSA, DOVE e QUANDO. Deve essere abbastanza preciso da poter dire di un titolo qualsiasi se parla di quel fatto o no. 'Gli Europei di atletica' non va bene: e' un argomento. 'L'Italia chiude prima nel medagliere degli Europei di atletica di Birmingham il 16 agosto' va bene.",
                        },
                        "tema": {
                            "type": "string",
                            "enum": ["politica interna", "esteri", "economia", "cronaca", "giustizia", "societa", "immigrazione", "ambiente", "sport", "cultura", "altro"],
                        },
                        "ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Gli id degli articoli che parlano di questo stesso evento.",
                        },
                    },
                    "required": ["titolo_neutro", "fatto_specifico", "tema", "ids"],
                },
            }
        },
        "required": ["eventi"],
    },
}

PROMPT_RAGGRUPPA = """Qui sotto ci sono i titoli delle notizie italiane delle ultime {ore} ore, presi dai feed RSS di diverse testate nazionali.

Raggruppa i titoli che parlano dello STESSO SINGOLO FATTO.

Questo è un lavoro di precisione, e l'errore che devi evitare è uno solo: mettere insieme titoli che parlano di cose vicine ma diverse. Il sito confronta come lo stesso fatto viene titolato da testate di orientamento opposto. Se nel gruppo entrano due fatti diversi, il confronto non dimostra niente e il lettore se ne accorge subito.

**La cosa che DEVI fare bene.** Titoli scritti con parole completamente diverse sono spesso lo stesso fatto, ed è proprio quello che cerco:
- "Fontana chiede la testa di Salvini" / "Fontana: un passo indietro di Salvini? Niente va escluso" → STESSO fatto: la dichiarazione di Fontana sulla guida della Lega.
- "Tutti al tavolo di Lavitola, il conto solo a Ranucci" / "Il legale: Ranucci potrebbe aver capito" → STESSO fatto: l'inchiesta su Ranucci e i suoi rapporti con Lavitola.
Non guardare le parole in comune: guarda di quale fatto si parla.

**La cosa che NON devi fare.** Questi sono errori, non raggrupparli:
- "Europei di ATLETICA a Birmingham" con "Europei di NUOTO a Parigi" → competizioni diverse, città diverse, sport diversi. DUE eventi, anche se entrambi parlano di medagliere e di Italia.
- "L'Italia chiude prima nel medagliere" con "Quadarella vince i 400 stile libero" → uno è il bilancio complessivo, l'altro una singola gara. DUE eventi.
- "Attacco ucraino su Belgorod" con "Mosca bombarda Odessa" → cambia chi attacca e chi è attaccato. DUE eventi, anche se è la stessa guerra nella stessa notte.
- "Scade la tregua con l'Iran" con "Il Wsj scrive che l'Iran ha usato la tregua per prepararsi alla guerra" → uno è un fatto in corso, l'altro la ricostruzione di un giornale. DUE eventi.
- Due sbarchi in due giorni diversi, due incidenti stradali in due province, due dichiarazioni dello stesso politico su temi diversi → sempre eventi separati.
- Un ARGOMENTO non è un evento. "La crisi migratoria a Ceuta" è un argomento e in una giornata produce dieci fatti distinti: il Marocco che ferma 294 persone al confine, Sánchez che convoca i ministri, un commento sulla politica europea. Sono tre eventi, non uno.

**Nel dubbio, spacca.** Due gruppi piccoli e giusti valgono più di un gruppo grande e sbagliato. Un evento con un solo titolo è un risultato perfettamente accettabile.

**Come ti controlli.** Per ogni gruppo devi scrivere `fatto_specifico`: chi ha fatto cosa, dove, quando. Poi rileggi ogni titolo del gruppo e chiediti se quel titolo parla di *quel* fatto. Se la risposta è "parla di qualcosa di collegato", il titolo va fuori. Se per far entrare tutti i titoli devi scrivere un fatto_specifico vago, allora il gruppo è sbagliato: spaccalo.

**Commenti ed editoriali.** Un commento, un retroscena o un editoriale va nel gruppo del fatto di cui parla — sono la parte più interessante da confrontare. Ma solo se parla di *quel* fatto: un editoriale sullo stato della sinistra italiana non va nel gruppo di una singola dichiarazione di Schlein.

Regole formali:
- Ogni id deve comparire in esattamente un evento.
- Non scartare niente: i titoli che restano soli diventano eventi con un id.
- Il titolo_neutro lo scrivi tu, asciutto come un lancio d'agenzia. Non copiare il titolo di nessuna testata e non usarne le parole cariche.

Titoli:

{titoli}

Chiama registra_eventi con tutti gli eventi trovati."""

SCHEMA_VERIFICA = {
    "name": "registra_verifica",
    "description": "Registra quali titoli non appartengono al gruppo in cui sono stati messi.",
    "input_schema": {
        "type": "object",
        "properties": {
            "controlli": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "evento": {"type": "integer", "description": "Il numero del gruppo nell'elenco."},
                        "da_togliere": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Gli id dei titoli che NON parlano del fatto specifico dichiarato. Lista vuota se il gruppo è corretto.",
                        },
                        "motivo": {
                            "type": "string",
                            "description": "Se togli qualcosa, una riga sul perché. Stringa vuota se non togli niente.",
                        },
                    },
                    "required": ["evento", "da_togliere", "motivo"],
                },
            }
        },
        "required": ["controlli"],
    },
}

PROMPT_VERIFICA = """Qualcuno ha raggruppato dei titoli di giornale per evento. Il tuo compito è controllare il lavoro e trovare gli intrusi.

Per ogni gruppo trovi il fatto specifico dichiarato e i titoli che sono stati messi dentro. Per ogni titolo chiediti una cosa sola: **questo titolo parla di quel fatto preciso?**

Togli il titolo se:
- parla di un fatto diverso, anche se collegato o dello stesso argomento
- riguarda una gara, una competizione, una città, un giorno o dei protagonisti diversi
- è un commento generico su un tema, non su quel fatto
- ribalta i ruoli (chi attacca e chi è attaccato, chi accusa e chi è accusato)

Non togliere il titolo solo perché è scritto con parole diverse, o perché ha un tono opposto, o perché sceglie numeri diversi, o perché è un'opinione anziché una cronaca. Quelle differenze sono esattamente il materiale che serve al sito: vanno conservate.

Sii severo. Un gruppo con due titoli giusti vale più di un gruppo con quattro titoli di cui uno stonato. Se un gruppo è tutto sbagliato puoi togliere anche tutti i titoli tranne uno.

{gruppi}

Chiama registra_verifica con un controllo per ogni gruppo, anche per quelli che vanno bene."""

SCHEMA_ANALIZZA = {
    "name": "registra_analisi",
    "description": "Registra l'analisi dell'inquadratura per ogni evento.",
    "input_schema": {
        "type": "object",
        "properties": {
            "analisi": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "evento": {"type": "integer", "description": "Il numero dell'evento come indicato nell'elenco."},
                        "divergenza": {
                            "type": "string",
                            "enum": ["bassa", "media", "alta"],
                            "description": "bassa = i titoli raccontano il fatto quasi allo stesso modo. media = cambiano enfasi, cosa mettono in prima posizione, cosa omettono. alta = cambia chi è il protagonista, chi ha la colpa, oppure il fatto stesso sembra un altro.",
                        },
                        "duello": {
                            "type": "string",
                            "description": "Una frase sola, al massimo 30 parole, che mette a fuoco lo scarto fra il titolo più a sinistra e quello più a destra. È la frase che il lettore legge fra le due colonne: deve essere secca e concreta, non un riassunto.",
                        },
                        "nota": {
                            "type": "string",
                            "description": "Due o tre frasi in italiano che spiegano la differenza concreta fra i titoli: quale parola cambia, cosa viene messo davanti, cosa viene taciuto, quale numero viene scelto. Descrittivo, non giudicante: si scrive cosa fanno i titoli, non che una testata è in malafede. Cita le parole tra virgolette.",
                        },
                    },
                    "required": ["evento", "divergenza", "duello", "nota"],
                },
            }
        },
        "required": ["analisi"],
    },
}

PROMPT_ANALIZZA = """Per ognuno di questi eventi ti do i titoli con cui testate di orientamento diverso lo hanno raccontato. L'etichetta fra parentesi quadre indica la posizione della testata su una scala a cinque: sinistra radicale, centro-sinistra, centro e agenzie, centro-destra, destra radicale.

Per ogni evento produci: quanto diverge l'inquadratura, una frase secca sul duello fra i due estremi, e una nota di due o tre frasi.

REGOLA D'ORO — devi essere TOTALMENTE IMPARZIALE. La nota «come cambia il titolo» descrive SOLO le differenze oggettive, verificabili nel testo dei titoli. È un referto, non un commento. Vietato:
- dire o insinuare che una testata mente, è in malafede, manipola o inganna;
- scrivere quale versione è «giusta» o «più vicina alla verità»;
- aggiungere la tua opinione sul fatto o sui protagonisti;
- usare aggettivi tuoi carichi (scandaloso, vergognoso, allarmante...). Le parole cariche le CITI solo se sono nei titoli, tra virgolette.

Quello che DEVI fare è indicare, con esempi concreti presi dai titoli:
- quale soggetto viene messo per primo, e chi sparisce dalla frase;
- se un'azione è resa in forma attiva o passiva;
- se compaiono dettagli identitari, etnici, di nazionalità o di provenienza in un titolo e non in un altro;
- quali numeri vengono scelti quando ce ne sono di diversi;
- quali parole valutative (citate tra virgolette) prendono il posto della descrizione del fatto;
- cosa viene presentato come causa, e cosa viene taciuto.

Il modello ideale di nota è quello dell'evento dei droni: «L'ANSA titola sul numero lanciato, 620. Il Quotidiano Nazionale riprende la cifra del ministero russo, 205 abbattuti, e mette in evidenza i morti a Belgorod. Il Tempo parla di 1.500 droni in 24 ore. A sinistra Domani non quantifica l'attacco e lo inquadra come segno di debolezza del Cremlino». Puro confronto, zero giudizio.

REGISTRO — scrivi per il LETTORE del sito, non per chi lo costruisce. Terza persona, come la didascalia di un'analisi dei media su un quotidiano. Nomina le testate, non «la sinistra» in astratto quando puoi dire «Il Post» o «Domani». VIETATO nominare il sito, il metodo, «il selettore», «la finestra», «campionato», «in prima pagina», o rivolgerti all'autore. Niente «noi». La nota deve poter stare sotto qualsiasi rassegna stampa seria.

Quando disponibile, per alcuni articoli trovi un ESTRATTO del testo oltre al titolo: usalo per rendere la nota più precisa (un titolo può dire una cosa e il pezzo un'altra), ma sul confronto restano i titoli. Non citare frasi lunghe dell'articolo: riassumi il contenuto con parole neutre.

Equidistanza obbligatoria: se è un giornale di sinistra ad ammorbidire, dillo con lo stesso tono con cui diresti che uno di destra carica, e viceversa. Se la differenza è minima, scrivi che è minima invece di inventarla. Le agenzie sono di solito le più asciutte, ed è utile dirlo.

{eventi}

Chiama registra_analisi con l'analisi di tutti gli eventi."""


def client_anthropic():
    try:
        import anthropic
    except ImportError:
        sys.exit("Manca la libreria. Lancia:  pip install anthropic")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "Manca ANTHROPIC_API_KEY.\n"
            "  Windows PowerShell:  $env:ANTHROPIC_API_KEY = 'sk-ant-...'\n"
            "  Linux/Mac:           export ANTHROPIC_API_KEY=sk-ant-...\n"
            "La chiave si crea su console.anthropic.com."
        )
    return anthropic.Anthropic()


def chiama(client, prompt, schema, max_tokens=16000):
    risposta = client.messages.create(
        model=MODELLO,
        max_tokens=max_tokens,
        tools=[schema],
        tool_choice={"type": "tool", "name": schema["name"]},
        messages=[{"role": "user", "content": prompt}],
    )
    for blocco in risposta.content:
        if blocco.type == "tool_use":
            return blocco.input, risposta.usage
    raise RuntimeError("Il modello non ha chiamato lo strumento.")


def raggruppa(client, articoli, ore):
    # Non mandare TUTTO al modello in un colpo solo: con molte centinaia di
    # articoli la risposta supera il limite di token e viene tagliata a meta',
    # cosi' il raggruppamento fallisce e ogni articolo resta un evento a se'.
    # Teniamo le notizie in agenda (primaria) e le piu' recenti, fino a un tetto.
    MAX_ART = 400
    if len(articoli) > MAX_ART:
        prim = [a for a in articoli if a.get("primaria")]
        resto = [a for a in articoli if not a.get("primaria")]
        resto.sort(key=lambda a: a.get("pubblicato", ""), reverse=True)
        tenuti = prim + resto[: max(0, MAX_ART - len(prim))]
        print("  troppi articoli (%d): raggruppo i %d piu' rilevanti (agenda + recenti)"
              % (len(articoli), len(tenuti)))
        articoli = tenuti
    righe = []
    for a in articoli:
        ora = a["pubblicato"][11:16]
        # la testata serve al modello per capire il registro, la posizione politica NO
        righe.append("%s [%s, %s] %s" % (a["id"], a["fonte"], ora, a["titolo"]))
    prompt = PROMPT_RAGGRUPPA.format(ore=ore, titoli="\n".join(righe))

    dati, uso = chiama(client, prompt, SCHEMA_RAGGRUPPA, max_tokens=16000)
    print("  passo 1 raggruppamento: %d token in, %d out" % (uso.input_tokens, uso.output_tokens))
    if uso.output_tokens >= 15500:
        print("  ATTENZIONE: risposta vicina al limite dei token, riduci ancora MAX_ART")

    per_id = {a["id"]: a for a in articoli}
    eventi, usati = [], set()
    for ev in dati.get("eventi", []):
        membri = []
        for i in ev.get("ids", []):
            if i in per_id and i not in usati:
                membri.append(per_id[i])
                usati.add(i)
        if membri:
            eventi.append({
                "titolo_neutro": ev["titolo_neutro"].strip(),
                "fatto_specifico": (ev.get("fatto_specifico") or "").strip(),
                "tema": ev.get("tema", "altro"),
                "articoli": membri,
            })

    persi = [a for a in articoli if a["id"] not in usati]
    if persi:
        print("  %d articoli non assegnati, li tengo come eventi singoli" % len(persi))
        for a in persi:
            eventi.append({"titolo_neutro": a["titolo"], "fatto_specifico": a["titolo"],
                           "tema": "altro", "articoli": [a]})
    return eventi


def verifica(client, eventi):
    """Passo 1.5: rilegge i gruppi e caccia i titoli che non c'entrano.

    È il passaggio che evita di mettere gli Europei di atletica e quelli di
    nuoto nello stesso confronto. Chi viene cacciato diventa un evento a sé.
    """
    candidati = [(i, ev) for i, ev in enumerate(eventi) if len(ev["articoli"]) >= 2]
    if not candidati:
        return eventi

    blocchi = []
    for n, (_, ev) in enumerate(candidati, 1):
        righe = ["Gruppo %d" % n,
                 "  fatto dichiarato: %s" % (ev.get("fatto_specifico") or ev["titolo_neutro"])]
        for a in ev["articoli"]:
            righe.append('  %s [%s] "%s"' % (a["id"], a["fonte"], a["titolo"]))
        blocchi.append("\n".join(righe))

    dati, uso = chiama(client, PROMPT_VERIFICA.format(gruppi="\n\n".join(blocchi)), SCHEMA_VERIFICA)
    print("  verifica: %d token in, %d out" % (uso.input_tokens, uso.output_tokens))

    espulsi_totali, tocchi = [], 0
    for voce in dati.get("controlli", []):
        n = voce.get("evento", 0)
        da_togliere = set(voce.get("da_togliere") or [])
        if not (1 <= n <= len(candidati)) or not da_togliere:
            continue
        idx, ev = candidati[n - 1]
        restano = [a for a in ev["articoli"] if a["id"] not in da_togliere]
        espulsi = [a for a in ev["articoli"] if a["id"] in da_togliere]
        if not restano:                      # non svuotare mai un gruppo
            restano, espulsi = ev["articoli"][:1], ev["articoli"][1:]
        if not espulsi:
            continue
        eventi[idx]["articoli"] = restano
        eventi[idx]["verificato"] = True
        espulsi_totali.extend(espulsi)
        tocchi += 1
        print("    gruppo %d: fuori %d titoli - %s"
              % (n, len(espulsi), (voce.get("motivo") or "").strip()[:90]))

    for _, ev in candidati:
        ev.setdefault("verificato", True)

    for a in espulsi_totali:
        eventi.append({"titolo_neutro": a["titolo"], "fatto_specifico": a["titolo"],
                       "tema": "altro", "articoli": [a], "riammesso": True})

    if tocchi:
        print("  gruppi corretti: %d, titoli rimessi da soli: %d" % (tocchi, len(espulsi_totali)))
    else:
        print("  nessun intruso trovato")
    return eventi


def arricchisci(eventi):
    """Calcola aree, estremi, colonne e punti ciechi. Tutto in Python, niente modello."""
    for ev in eventi:
        per_area = {x: [] for x in AREE}
        for a in ev["articoli"]:
            if a.get("area") in per_area:
                per_area[a["area"]].append(a)
        for x in per_area:
            per_area[x].sort(key=lambda a: a["pubblicato"])

        per_colonna = {}
        for chiave, _, aree in COLONNE:
            dentro = [a for x in aree for a in per_area[x]]
            per_colonna[chiave] = ordina_da_sinistra(dentro)

        sinistro, destro, distanza = estremi(ev["articoli"])

        # la spina dorsale: un evento e' "principale" se un aggregatore neutrale
        # (Google News) o la topnews di un'agenzia l'ha messo in agenda (articolo
        # primaria) E almeno una testata con una linea l'ha coperto. Cosi' un item
        # d'agenda che nessun giornale riprende (o un tick di borsa) non sale in cima.
        primari = [a for a in ev["articoli"] if a.get("primaria")]
        reali = [a for a in ev["articoli"] if a.get("area") in AREE]
        ev["principale"] = bool(primari) and len(reali) >= 1 and len(ev["articoli"]) >= 2
        # ordine dell'agenda: comanda l'aggregatore (Google News). Gli eventi in
        # topnews d'agenzia ma non in GN vengono dopo (offset 100).
        agg = [a for a in primari if a.get("area") == AGGREGATORE]
        if agg:
            ev["ordine_agenzia"] = min(a.get("ordine_feed", 999) for a in agg)
        else:
            ev["ordine_agenzia"] = 100 + min((a.get("ordine_feed", 999) for a in primari), default=899)

        ev["per_area"] = per_area
        ev["per_colonna"] = per_colonna
        ev["conteggi"] = {x: len(v) for x, v in per_area.items()}
        ev["aree_presenti"] = [x for x in AREE if per_area[x]]
        ev["colonne_presenti"] = [k for k, v in per_colonna.items() if v]
        ev["colonne_mancanti"] = [k for k, v in per_colonna.items() if not v]
        ev["estremo_sinistro"] = sinistro
        ev["estremo_destro"] = destro
        ev["ampiezza"] = distanza          # quante caselle della scala separano gli estremi
        ev["riferimento"] = riferimento_centro(ev["articoli"])
        ev["totale"] = len(reali)          # conta le testate con una linea, non l'aggregatore
        ev["ultimo"] = max(a["pubblicato"] for a in ev["articoli"])
        ev["testate"] = sorted({a["fonte"] for a in reali})
        ev["in_agenda"] = sorted({a["fonte"] for a in ev["articoli"] if a.get("area") == AGGREGATORE})

    # ordine di default per gli eventi NON principali (quelli principali li
    # ordina render.py per posizione nella topnews). Prima gli estremi piu'
    # distanti, poi i piu' seguiti, poi i piu' recenti.
    eventi.sort(key=lambda e: (e["ampiezza"], len(e["aree_presenti"]), e["totale"], e["ultimo"]),
                reverse=True)
    return eventi


def analizza(client, eventi, quanti, ampiezza_minima=2):
    # analizza gli eventi principali (sempre, sono la cima del sito) piu' quelli
    # con estremi distanti. Cosi' ogni evento in vetta ha la sua nota.
    candidati = [(i, ev) for i, ev in enumerate(eventi)
                 if ev.get("principale") or ev["ampiezza"] >= ampiezza_minima][:quanti]
    if not candidati:
        print("  passo 2 saltato: nessun evento con estremi abbastanza distanti")
        return

    blocchi = []
    for n, (_, ev) in enumerate(candidati, 1):
        righe = ["Evento %d - %s" % (n, ev["titolo_neutro"])]
        # solo le testate con una linea: l'aggregatore non e' una voce da analizzare
        for a in ordina_da_sinistra([x for x in ev["articoli"] if x.get("area") in AREE]):
            righe.append('  [%s] %s: "%s"' % (NOMI[a["area"]], a["fonte"], a["titolo"]))
        blocchi.append("\n".join(righe))

    prompt = PROMPT_ANALIZZA.format(eventi="\n\n".join(blocchi))
    dati, uso = chiama(client, prompt, SCHEMA_ANALIZZA)
    print("  passo 2 analisi: %d token in, %d out" % (uso.input_tokens, uso.output_tokens))

    for voce in dati.get("analisi", []):
        n = voce.get("evento", 0)
        if 1 <= n <= len(candidati):
            idx = candidati[n - 1][0]
            eventi[idx]["divergenza"] = voce.get("divergenza", "media")
            eventi[idx]["duello"] = voce.get("duello", "").strip()
            eventi[idx]["nota"] = voce.get("nota", "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-verifica", action="store_true",
                    help="salta il controllo che caccia gli intrusi dai gruppi (sconsigliato)")
    ap.add_argument("--no-analisi", action="store_true", help="salta il passo 2")
    ap.add_argument("--analizza", type=int, default=14, help="quanti eventi analizzare (default 14)")
    args = ap.parse_args()

    if not IN.exists():
        sys.exit("Non trovo %s. Lancia prima:  python ingest.py" % IN)
    dati = json.loads(IN.read_text(encoding="utf-8"))
    articoli = dati["articoli"]
    if not articoli:
        sys.exit("Nessun articolo da raggruppare. Controlla i feed con check_feeds.py")

    print("Raggruppo %d articoli da %d testate." % (len(articoli), len({a["fonte"] for a in articoli})))
    client = client_anthropic()

    eventi = raggruppa(client, articoli, dati.get("finestra_ore", 24))
    if not args.no_verifica:
        eventi = verifica(client, eventi)
    eventi = arricchisci(eventi)
    if not args.no_analisi:
        analizza(client, eventi, args.analizza)

    principali = [e for e in eventi if e.get("principale")]
    duelli = [e for e in eventi if e["ampiezza"] >= 2]
    estremi_opposti = [e for e in eventi if e["ampiezza"] == len(AREE) - 1]
    ciechi = [e for e in eventi if len(e["colonne_presenti"]) == 1 and e["totale"] >= 2]

    out = {
        "generato": datetime.now(timezone.utc).isoformat(),
        "finestra_ore": dati.get("finestra_ore", 24),
        "modello": MODELLO,
        "totale_articoli": len(articoli),
        "per_area": dati.get("per_area", {}),
        "testate_attive": sorted({a["fonte"] for a in articoli}),
        "statistiche": {
            "eventi": len(eventi),
            "principali": len(principali),
            "duelli": len(duelli),
            "estremi_opposti": len(estremi_opposti),
            "punti_ciechi": len(ciechi),
            "temi": dict(Counter(e["tema"] for e in eventi).most_common()),
        },
        "eventi": eventi,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nEventi trovati: %d" % len(eventi))
    print("  principali (spina dorsale ANSA topnews): %d" % len(principali))
    print("  confrontabili (estremi a 2+ caselle):    %d" % len(duelli))
    print("  da un estremo all'altro della scala:     %d" % len(estremi_opposti))
    print("  punti ciechi (una colonna sola):         %d" % len(ciechi))
    print("Salvato in %s" % OUT)


if __name__ == "__main__":
    main()
