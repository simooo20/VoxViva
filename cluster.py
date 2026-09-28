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
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from scala import allarme, lati_mostrati
from scala import (AGGREGATORE, AREE, BREVI, COLONNA_DI, COLONNE, NOMI,
                   coppia_divergente, estremi, ordina_da_sinistra,
                   riferimento_centro)

import re as _re
import urllib.request
import difflib

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

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
        html = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", "ignore")
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

ROMA = ZoneInfo("Europe/Rome")
from scala import AGENZIE as AGENZIE_CENTRO
import re as _re_sport
RUMORE_SPORT = _re_sport.compile(r"\b(serie a|champions|gol|calciomercato|nations league|formula 1|motogp)\b", _re_sport.I)

# FINESTRA TEMPORALE DEL CONFRONTO (regola di Simone, 26 set 2026): i titoli
# messi a confronto devono essere stati scritti nelle STESSE ore. Se fra il
# titolo di sinistra e quello di destra passano 7 ore, quasi sempre non sono la
# stessa notizia ma due momenti diversi della vicenda (la proposta di accordo e,
# ore dopo, il no di Trump). Ogni gruppo viene quindi ristretto alla finestra di
# FINESTRA_ORE ore che copre meglio sinistra/centro/destra; chi sta fuori esce.
# Si cambia senza toccare il codice con la variabile ILVAGLIO_FINESTRA_ORE.
FINESTRA_ORE = float(os.environ.get("ILVAGLIO_FINESTRA_ORE", "10"))
# Eccezione (Simone, 28/9): un titolo di sinistra o di destra MOLTO carico
# (allarme >= SOGLIA_CARICO: parole cariche, origini/nazionalita'...) resta nel
# confronto anche se scritto fino a FINESTRA_LUNGA ore prima/dopo, perche' e'
# proprio la versione che rende il confronto interessante. Che parli dello
# STESSO fatto lo garantiscono verifica() prima e controlla_trio() dopo.
FINESTRA_LUNGA = float(os.environ.get("ILVAGLIO_FINESTRA_LUNGA", "24"))
SOGLIA_CARICO = 2.5

# Temi che NON si pubblicano (decisione di Simone): lo sport non ha una lettura
# di sinistra/centro/destra. Il filtro in ingest.py toglie gran parte dello
# sport dall'indirizzo e dalle parole; questo e' il secondo filtro, sul tema
# che il modello assegna al gruppo, per quello che sfugge.
TEMI_ESCLUSI = {"sport"}


def _dt(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None


def _ora_breve(iso):
    """'26/9 09:14' in ora italiana: al modello serve per capire se due titoli
    sono dello stesso momento della notizia o di due momenti diversi."""
    d = _dt(iso)
    if d is None:
        return "?"
    d = d.astimezone(ROMA)
    return "%d/%d %s" % (d.day, d.month, d.strftime("%H:%M"))

# Modalità economica: Haiku costa ~4-5 volte meno di Sonnet. Si puo' cambiare
# senza toccare il codice, con la variabile ILVAGLIO_MODEL nel repo.
MODELLO = os.environ.get("ILVAGLIO_MODEL", "claude-haiku-4-5")

# Il raggruppamento e' il passo difficile: capire che la STESSA notizia e'
# titolata con parole OPPOSTE dagli estremi. E' proprio il titolo urlato di
# SR/DR quello scritto piu' diversamente dal centro neutro, quindi il piu'
# facile da NON riconoscere: e' il caso che regge o affonda il prodotto (far
# uscire la versione piu' urlata). Per questo il raggruppamento sta su Sonnet,
# che lo becca; verifica e analisi restano su Haiku per contenere la spesa.
# Il tetto giornaliero fa comunque da rete. Per tornare al risparmio massimo
# (a costo di qualche merge urlato perso) basta la variabile, senza toccare il
# codice:  ILVAGLIO_MODEL_RAGGRUPPA=claude-haiku-4-5
MODELLO_RAGGRUPPA = os.environ.get("ILVAGLIO_MODEL_RAGGRUPPA", "claude-haiku-4-5")

# --- TETTO DI SPESA GIORNALIERO -------------------------------------------
# Limite in DOLLARI al giorno sulle chiamate API di questo progetto (i prezzi
# API sono in USD: 0.33 USD = circa 0.30 EUR). Superato il tetto, cluster.py
# smette di chiamare il modello: verifica e analisi vengono saltate, e se il
# tetto e' gia' esaurito a inizio giro il giro viene saltato del tutto e resta
# online l'ultima versione pubblicata (nessun sito vuoto).
# Si cambia senza toccare il codice con la variabile ILVAGLIO_TETTO_USD.
TETTO_SPESA_USD = float(os.environ.get("ILVAGLIO_TETTO_USD", "0"))  # 0 = nessun tetto

# Prezzi per milione di token (input, output). Verificati a settembre 2026.
# Se il modello non e' in tabella si usa il prezzo di Sonnet (prudenziale).
PREZZI = {
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5":  (1.0, 5.0),
}
SPESA_FILE = os.environ.get("ILVAGLIO_SPESA_FILE", "web/spesa.json")
SPESA_URL = os.environ.get("ILVAGLIO_SPESA_URL",
                           "https://simooo20.github.io/VoxViva/spesa.json")


class BudgetEsaurito(RuntimeError):
    """Alzata quando la spesa del giorno ha raggiunto il tetto."""


def _prezzo(modello):
    return PREZZI.get(modello, PREZZI["claude-sonnet-4-5"])


def _costo(modello, uso):
    pin, pout = _prezzo(modello)
    return uso.input_tokens / 1e6 * pin + uso.output_tokens / 1e6 * pout


class Budget:
    """Tiene il conto della spesa di OGGI, sommando i giri precedenti.

    Lo stato del giorno vive in web/spesa.json, che viene pubblicato su Pages:
    e' cosi' che un giro legge quanto hanno gia' speso i giri precedenti (il
    runner di GitHub e' effimero e non conserva niente da solo). Se non si
    riesce a leggere lo storico si riparte da zero: il vero paracadute e'
    comunque il limite di spesa mensile impostato nella Console Anthropic.
    """

    def __init__(self, tetto):
        self.tetto = tetto
        self.oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.speso_prima = self._carica()
        self.speso_ora = 0.0

    def _carica(self):
        # prima il file locale (raro: stesso runner), poi quello su Pages
        try:
            d = json.loads(Path(SPESA_FILE).read_text(encoding="utf-8"))
            if d.get("giorno") == self.oggi:
                return float(d.get("usd", 0.0))
        except Exception:
            pass
        try:
            import urllib.request
            url = "%s?v=%d" % (SPESA_URL, int(time.time()))
            with urllib.request.urlopen(url, timeout=10) as r:
                d = json.loads(r.read().decode("utf-8"))
            if d.get("giorno") == self.oggi:
                return float(d.get("usd", 0.0))
        except Exception:
            pass
        return 0.0

    @property
    def totale(self):
        return self.speso_prima + self.speso_ora

    def resta(self):
        return self.tetto - self.totale

    def registra(self, modello, uso):
        self.speso_ora += _costo(modello, uso)
        try:
            Path(SPESA_FILE).parent.mkdir(parents=True, exist_ok=True)
            Path(SPESA_FILE).write_text(
                json.dumps({"giorno": self.oggi, "usd": round(self.totale, 4)},
                           ensure_ascii=False),
                encoding="utf-8")
        except Exception:
            pass


BUDGET = None  # impostato in main(), None = nessun tetto (es. test)
MODO = {"raggruppamento": None}  # "google" o "completo": finisce in events.json


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
                            "description": "Una TUA sintesi neutra dell'evento (fatto, luogo, attori), scritta con parole tue. NON ricopiare nessuno dei titoli del gruppo, e in particolare NON il lancio d'agenzia (ANSA/AGI) del centro: deve essere una formulazione DIVERSA da tutti i titoli presenti, non la stessa frase. Massimo 90 caratteri, nessun aggettivo valutativo, nessuna virgoletta di dichiarazione.",
                        },
                        "fatto_specifico": {
                            "type": "string",
                            "description": "Il fatto singolo e concreto a cui questo gruppo si riferisce, scritto come CHI ha fatto COSA, DOVE e QUANDO. Deve essere abbastanza preciso da poter dire di un titolo qualsiasi se parla di quel fatto o no. 'Gli Europei di atletica' non va bene: e' un argomento. 'L'Italia chiude prima nel medagliere degli Europei di atletica di Birmingham il 16 agosto' va bene.",
                        },
                        "tema": {
                            "type": "string",
                            "enum": ["politica interna", "esteri", "economia", "cronaca", "giustizia", "societa", "immigrazione", "ambiente", "sport", "cultura", "altro"],
                            "description": "'sport' per QUALSIASI notizia che riguarda partite, risultati, squadre, nazionali, atleti o ex atleti (anche se e' cronaca: un ex calciatore ricoverato e' 'sport'). Usa un altro tema solo se la notizia e' diventata politica (soldi pubblici, governo, leggi).",
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

**Il tuo obiettivo.** Questo sito mostra come la STESSA grande notizia del giorno viene titolata da testate di orientamento opposto. Quindi il lavoro più prezioso che puoi fare è: tra tutti questi titoli, TROVARE le notizie principali coperte da più testate — una versione di sinistra, una di centro (spesso un lancio d'agenzia ANSA/AGI), una di destra — e METTERLE INSIEME nello stesso gruppo. Per ogni fatto importante che vedi, cerca attivamente se altre testate lo stanno raccontando con parole diverse, e uniscile. Un titolo di sinistra e uno di destra sullo stesso fatto vanno quasi sempre nello stesso gruppo: è esattamente il confronto che serve. Non lasciare da soli i titoli delle notizie grosse: è probabile che quel fatto sia coperto anche dagli altri lati.

Questo è comunque un lavoro di precisione, e l'errore da evitare è uno: mettere insieme notizie DAVVERO diverse. Il sito confronta come la stessa notizia viene titolata da testate di orientamento opposto. Se nel gruppo entrano due notizie diverse, il confronto non dimostra niente. Ma attenzione: spaccare una grande notizia in tanti frammenti è un errore altrettanto grave, perché così nessun frammento ha le tre voci e la notizia non esce affatto.

**La cosa che DEVI fare bene.** Titoli scritti con parole completamente diverse sono spesso lo stesso fatto, ed è proprio quello che cerco:
- "Fontana chiede la testa di Salvini" / "Fontana: un passo indietro di Salvini? Niente va escluso" → STESSO fatto: la dichiarazione di Fontana sulla guida della Lega.
- "Tutti al tavolo di Lavitola, il conto solo a Ranucci" / "Il legale: Ranucci potrebbe aver capito" → STESSO fatto: l'inchiesta su Ranucci e i suoi rapporti con Lavitola.
Non guardare le parole in comune: guarda di quale fatto si parla.

**La cosa che NON devi fare — unire notizie DAVVERO diverse:**
- "Europei di ATLETICA a Birmingham" con "Europei di NUOTO a Parigi" → competizioni diverse, città diverse, sport diversi. DUE eventi.
- "L'Italia chiude prima nel medagliere" con "Quadarella vince i 400 stile libero" → uno è il bilancio complessivo, l'altro una singola gara. DUE eventi.
- Due sbarchi in due GIORNI diversi, due incidenti stradali in due province, due dichiarazioni dello stesso politico su temi diversi → eventi separati.

**MA l'errore opposto è peggiore: NON spaccare la grande notizia del giorno.** Le notizie importanti si sviluppano su più aspetti, e TUTTI gli aspetti della stessa vicenda di oggi vanno nello STESSO gruppo — è lì che il confronto sinistra/centro/destra vale di più:
- Guerra Russia-Ucraina: i raid della notte, la replica di Putin, la mossa di Macron sui missili, i danni all'economia russa → se sono le notizie di OGGI sullo stesso episodio, è UN solo evento «la giornata di guerra in Ucraina», con le testate che ne sottolineano aspetti diversi. NON tre eventi separati con una voce ciascuno.
- Un terremoto con le scosse, i feriti, i soccorsi → un evento.
- Una manovra economica con le sue singole misure discusse oggi → un evento.
- Un caso di cronaca (un omicidio, un incidente mortale) con l'indagine, le reazioni, i dettagli → un evento.

**Regola pratica:** se Google News lo terrebbe in UN unico blocco di «notizie principali» con più testate sotto, tienilo in un gruppo solo anche tu. Solo un TEMA perenne e generico ("l'immigrazione", "la guerra" in astratto, senza un episodio del giorno) non è un evento.

**STESSO MOMENTO DELLA NOTIZIA — regola dura.** Accanto a ogni titolo c'è data e ora di pubblicazione. I titoli di un gruppo devono raccontare la notizia allo STESSO STADIO: devono dire la stessa cosa sul punto a cui è arrivata la vicenda. Quando una vicenda fa un passo avanti, il passo prima e il passo dopo sono DUE notizie diverse, anche se i protagonisti sono gli stessi:
- «L'Iran presenta una proposta di tregua» (mattina) e «Trump respinge la proposta dell'Iran» (sera) → DUE eventi. Chi legge il primo non sa ancora del no.
- «Indagato il sindaco» e «Arrestato il sindaco»; «Il governo presenta il decreto» e «Il decreto approvato/bocciato»; «Scomparsa una ragazza» e «Ritrovato il corpo» → DUE eventi.
Test: se il titolo A NON contiene ancora il fatto nuovo che è nel titolo B (e B è di diverse ore dopo), non stanno insieme. Titoli pubblicati a molte ore di distanza (più di 4-5) sono quasi sempre momenti diversi della vicenda: uniscili solo se dicono davvero la stessa cosa. Questo vale anche per la grande notizia del giorno: gli aspetti della STESSA fase stanno insieme, le fasi successive no.

**Nel dubbio, UNISCI — poi si controlla.** Un secondo passaggio ricontrollerà ogni gruppo e caccerà i titoli che non c'entrano, quindi un gruppo un po' generoso è sicuro; un gruppo spaccato no. Se lo stesso fatto finisce in due gruppi separati, il confronto fra le testate di orientamento opposto si perde e non lo recupera più nessuno. Perciò, quando due titoli *potrebbero* essere lo stesso singolo fatto, mettili insieme. Resta fermo solo il divieto qui sopra: non unire MAI fatti davvero diversi (evento, luogo, giorno o protagonisti diversi).

**Come ti controlli.** Per ogni gruppo scrivi `fatto_specifico`: la vicenda del giorno a cui si riferisce. Per una notizia grande va bene un fatto_specifico un po' ampio che tenga insieme gli aspetti di oggi (es. «gli sviluppi del 23 agosto della guerra Russia-Ucraina: raid notturni, replica di Putin, missili annunciati da Macron»). Spacca solo se il fatto_specifico diventa un TEMA astratto e senza tempo (es. «la politica migratoria europea») o se dentro finiscono giorni/episodi diversi.

**Commenti ed editoriali.** Un commento, un retroscena o un editoriale va nel gruppo del fatto di cui parla — sono la parte più interessante da confrontare. Ma solo se parla di *quel* fatto: un editoriale sullo stato della sinistra italiana non va nel gruppo di una singola dichiarazione di Schlein.

**I titoli URLATI sono i più preziosi — non lasciarli soli.** Un titolo carico, allarmistico o di parte (toni da scandalo, guerra, catastrofe, «vergogna», maiuscole, punti esclamativi) è di solito la versione estrema di una notizia che il centro racconta in modo asciutto: è ESATTAMENTE il confronto che serve. Proprio perché è scritto con parole diverse e cariche, è il caso più facile da lasciare erroneamente da solo. Quando vedi un titolo urlato, cerca attivamente se un'agenzia o un altro lato racconta lo stesso fatto in tono neutro, e UNISCILI: un titolo di sinistra radicale e uno di destra radicale sullo stesso episodio del giorno vanno sempre nello stesso gruppo, per quanto opposte siano le parole.

Regole formali (IMPORTANTISSIME):
- Riporta SOLO i gruppi con DUE O PIÙ titoli. I titoli che restano da soli NON vanno riportati: ci pensa il programma a tenerli come eventi singoli. Non elencare i singoli, non riempire la risposta ripetendo id già soli. Riporta esclusivamente gli accostamenti che hai trovato: così la risposta resta corta e non viene tagliata a metà.
- Ogni id compare in un solo gruppo.
- Il titolo_neutro lo scrivi tu, asciutto ma con parole TUE. Non ricopiare il titolo di nessuna testata — men che meno quello dell'agenzia/centro — e non usarne le parole cariche: è la riga grande in cima al confronto e deve essere DIVERSA dai titoli mostrati sotto, non la stessa frase del centro.

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

Per ogni gruppo trovi il fatto/vicenda dichiarato e i titoli dentro. Per ogni titolo chiediti: **questo titolo parla della stessa NOTIZIA (la stessa vicenda del giorno), o di una notizia diversa?**

Togli il titolo SOLO se parla di una notizia DAVVERO diversa:
- un altro episodio, un altro giorno, un'altra vicenda (non un aspetto diverso della stessa notizia di oggi)
- un MOMENTO DIVERSO della stessa vicenda: il titolo racconta la notizia prima (o dopo) il fatto nuovo che raccontano gli altri. Es. «L'Iran propone una tregua» in un gruppo dove gli altri dicono «Trump respinge la proposta» → va tolto: chi lo legge non sa ancora del no. Guarda l'ora fra parentesi: titoli di molte ore prima o dopo gli altri sono i primi sospettati.
- una gara / competizione / città chiaramente diversa
- un tema perenne e generico al posto della notizia del giorno

**NON togliere** un titolo perché sottolinea un ASPETTO diverso della stessa grande notizia del giorno. Nella guerra in Ucraina, «i raid di Kiev», «la replica di Putin», «i missili di Macron», «l'economia russa» sono aspetti della STESSA giornata di guerra: restano tutti insieme, non sono intrusi. E non togliere un titolo solo perché è scritto con parole diverse, ha un tono opposto, sceglie numeri diversi, o è un'opinione anziché una cronaca su quella stessa vicenda: quelle differenze sono il materiale del confronto e vanno conservate. Nel dubbio, LASCIA il titolo nel gruppo.

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
                        "titolo": {
                            "type": "string",
                            "description": "La riga grande in cima al confronto: l'ARGOMENTO essenziale ma RICONOSCIBILE, 4-9 parole, massimo 60 caratteri: cosa e' successo + a chi/dove, quanto basta perche' non possa essere 'un fatto qualsiasi'. Buoni: 'Reggio Emilia, aggredisce una donna e investe due persone', 'Espulso il trapper Bratan dopo il blocco della Milano-Meda', 'Tetto ai prezzi dei carburanti di Eni e Ip'. Troppo poveri: 'Aggressione a Reggio Emilia', 'Incidente a Reggio Emilia'. Niente giudizi ne' dettagli secondari: i dettagli li danno i titoli sotto. Deve essere diverso da tutti i titoli mostrati.",
                        },
                        "divergenza": {
                            "type": "string",
                            "enum": ["bassa", "media", "alta"],
                            "description": "bassa = i titoli raccontano il fatto quasi allo stesso modo, nessuna parola carica. media = cambiano enfasi, cosa mettono in prima posizione, cosa omettono. alta = uno dei titoli cambia il protagonista o la colpa, OPPURE introduce un'inquadratura ideologica assente negli altri: dettagli di nazionalita'/origine/religione, un bersaglio politico (governo, opposizione, UE, sindacati), parole cariche di giudizio («terrore», «vergogna», «schiaffo», «regime», «invasione»), un'accusa. Esempio: ANSA «Aggredisce donna e investe due persone» contro Il Giornale «Terrore a Reggio Emilia, 26enne di origini egiziane...» = ALTA. Non livellare verso il basso: descrivi la differenza che c'e' davvero, senza inventarla.",
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
                    "required": ["evento", "titolo", "divergenza", "duello", "nota"],
                },
            }
        },
        "required": ["analisi"],
    },
}

PROMPT_ANALIZZA = """Per ognuno di questi eventi ti do i titoli con cui testate di orientamento diverso lo hanno raccontato. L'etichetta fra parentesi quadre indica la posizione della testata su una scala a cinque: sinistra radicale, centro-sinistra, centro e agenzie, centro-destra, destra radicale.

Per ogni evento produci: quanto diverge l'inquadratura, una frase secca sul duello fra i due estremi, e una nota di tre o quattro frasi che confronta come le diverse testate RACCONTANO la stessa notizia — nel titolo E nel corpo del pezzo (quando c'è l'estratto).

**ANCORAGGIO — la cosa più importante.** Ogni evento ti arriva con TRE titoli marcati «IN COLONNA (sinistra/centro/destra)»: sono gli UNICI tre che il lettore vede a schermo, uno per colonna. La nota si costruisce SU QUESTI TRE. Quando parli di una colonna, il taglio che le attribuisci deve essere quello del suo titolo mostrato: non descrivere «il centro» con un'inquadratura che il titolo di centro mostrato NON ha (se il centro mostrato apre sul risultato A, non scrivere che il centro apre sul risultato B). Puoi — anzi devi — dare la pluralità citando altre testate del gruppo («anche Il Post…», «le altre agenzie…»), ma come contorno: la spina dorsale restano i tre titoli in colonna, e nessuna frase deve contraddire ciò che si vede. Se un titolo mostrato è l'eccezione rispetto al resto del suo lato, dillo esplicitamente invece di ignorarlo.

**Un'idea di lettura, non una lista.** La nota deve dare al lettore UN filo: qual è l'asse su cui i tre titoli divergono (chi mettono al centro, quale risultato scelgono come principale, cosa tacciono) e come ci si muove da un lato all'altro. Non un elenco slegato di scarti: un racconto breve e ordinato di come cambia l'inquadratura passando da sinistra al centro alla destra.

REGOLA D'ORO — devi essere TOTALMENTE IMPARZIALE. La nota «come cambia il racconto» descrive SOLO le differenze oggettive, verificabili nel testo dei titoli e degli estratti. È un referto, non un commento. Vietato:
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

Per la maggior parte degli articoli trovi, oltre al titolo, un ESTRATTO del pezzo (le prime righe). USALO: il confronto non è solo fra i titoli ma fra il RACCONTO — il tono, le parole scelte, cosa il pezzo mette in evidenza e cosa lascia sullo sfondo, come inquadra causa ed effetto. Un titolo può essere asciutto e il pezzo caricato, o viceversa: quando succede, segnalalo. Resta descrittivo e oggettivo, non citare frasi lunghe dell'articolo, riassumi con parole neutre.

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


# --- Batch API: stesso lavoro, meta' del costo ------------------------------
# La Batch API costa il 50% in meno su input e output. Non e' istantanea: si
# invia la richiesta e si aspetta che il batch finisca (di solito pochi minuti).
# La pipeline gira su schedule due volte al giorno, quindi qualche minuto in
# piu' non si nota. Si spegne con ILVAGLIO_BATCH=0 (torna alle chiamate dirette).
USA_BATCH = os.environ.get("ILVAGLIO_BATCH", "1").strip().lower() not in ("0", "false", "no", "")
BATCH_POLL = int(os.environ.get("ILVAGLIO_BATCH_POLL", "20"))         # secondi tra un controllo e l'altro
BATCH_TIMEOUT = int(os.environ.get("ILVAGLIO_BATCH_TIMEOUT", "2400"))  # attesa massima per batch (40 min)


def _invia_sync(client, params):
    return client.messages.create(**params)


def _invia_batch(client, params):
    """Manda una singola richiesta come batch (50% di sconto) e aspetta l'esito."""
    batch = client.messages.batches.create(
        requests=[{"custom_id": "r", "params": params}])
    atteso = 0
    while True:
        stato = client.messages.batches.retrieve(batch.id)
        if stato.processing_status == "ended":
            break
        if atteso >= BATCH_TIMEOUT:
            raise RuntimeError("batch non concluso entro %d s" % BATCH_TIMEOUT)
        time.sleep(BATCH_POLL)
        atteso += BATCH_POLL
    for r in client.messages.batches.results(batch.id):
        res = r.result
        if res.type == "succeeded":
            return res.message
        raise RuntimeError("batch: risultato %s" % res.type)
    raise RuntimeError("batch senza risultati")


def chiama(client, prompt, schema, max_tokens=16000, tentativi=4, modello=None):
    # L'API ogni tanto risponde con un errore momentaneo (sovraccarico, limite,
    # timeout): non deve buttare giu' l'intero giro. Riproviamo qualche volta con
    # attesa crescente prima di arrenderci.
    modello = modello or MODELLO
    # Tetto di spesa: se oggi abbiamo gia' raggiunto il limite, non chiamiamo.
    # Fuori dal ciclo di retry, cosi' non viene scambiato per un errore da riprovare.
    if BUDGET is not None and BUDGET.resta() <= 0:
        raise BudgetEsaurito(
            "tetto giornaliero di %.2f USD raggiunto (spesi %.2f oggi)"
            % (BUDGET.tetto, BUDGET.totale))
    ultimo = None
    params = {
        "model": modello,
        "max_tokens": max_tokens,
        "tools": [schema],
        "tool_choice": {"type": "tool", "name": schema["name"]},
        "messages": [{"role": "user", "content": prompt}],
    }
    for i in range(tentativi):
        try:
            risposta = (_invia_batch if USA_BATCH else _invia_sync)(client, params)
            for blocco in risposta.content:
                if blocco.type == "tool_use":
                    if BUDGET is not None:
                        BUDGET.registra(modello, risposta.usage)
                    return blocco.input, risposta.usage
            raise RuntimeError("Il modello non ha chiamato lo strumento.")
        except Exception as exc:
            ultimo = exc
            if i < tentativi - 1:
                attesa = 5 * (i + 1)
                print("  chiamata al modello fallita (tentativo %d/%d): %s "
                      "— riprovo tra %ds" % (i + 1, tentativi, str(exc)[:120], attesa))
                time.sleep(attesa)
    raise ultimo


def _titolo_copiato(titolo_neutro, titolo_articolo):
    """Vero se titolo_neutro e' (quasi) la copia letterale del titolo di un
    articolo - anche con un suffisso di testata attaccato in coda ("... - Il
    Fatto Quotidiano"). Il divieto di copiare e' nel prompt, ma i modelli
    ogni tanto non lo rispettano: questa e' la rete di sicurezza in Python."""
    a = (titolo_neutro or "").strip().lower()
    b = (titolo_articolo or "").strip().lower()
    if not a or not b:
        return False
    if a == b or a.startswith(b) or b.startswith(a):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() > 0.85


def _correggi_titolo_neutro(ev, contro_membri=None):
    """Se titolo_neutro risulta copiato da uno dei titoli indicati (di solito
    i membri attuali del gruppo, o quelli appena espulsi), lo sostituisce col
    titolo del primo membro RIMASTO - stessa convenzione di fallback gia' in
    uso altrove nel file per gli eventi singoli. Ritorna True se ha corretto."""
    membri = ev.get("articoli") or []
    if not membri:
        return False
    sospetti = contro_membri if contro_membri is not None else membri
    tn = ev.get("titolo_neutro", "")
    if any(_titolo_copiato(tn, a.get("titolo", "")) for a in sospetti):
        ev["titolo_neutro"] = membri[0]["titolo"]
        return True
    return False


def raggruppa(client, articoli, ore):
    # Non mandare TUTTO al modello in un colpo solo: con molte centinaia di
    # articoli la risposta supera il limite di token e viene tagliata a meta',
    # cosi' il raggruppamento fallisce e ogni articolo resta un evento a se'.
    # Teniamo le notizie in agenda (primaria) e le piu' recenti, fino a un tetto.
    # Ora il modello riporta SOLO i gruppi da 2+ titoli (i singoli li ricrea
    # Python qui sotto): la risposta non cresce più con il numero di articoli,
    # quindi possiamo dargliene molti di più senza rischiare il taglio a metà.
    # Più articoli in ingresso = più probabilità che ogni notizia grossa abbia
    # tutte e tre le colonne (sinistra, centro, destra).
    # I "lati" (sinistra SR/CS e destra CD/DR) sono la merce SCARSA: se un titolo
    # di sinistra o di destra viene buttato via qui, quella notizia non potra' mai
    # avere le tre colonne piene. Il CENTRO invece e' abbondante (ANSA/AGI hanno
    # sette-otto sezioni): e' quello che si puo' tagliare senza danno, perche' il
    # centro non manca quasi mai. Quindi teniamo SEMPRE tutti i lati + l'agenda,
    # e riempiamo il resto del tetto con il centro piu' recente.
    # Tetto alto: teniamo tutti i lati E abbondante centro, cosi' nessuna
    # colonna resta a secco. (Con un tetto basso, tenere tutti i lati finiva
    # per tagliare troppo il centro, che diventava la colonna mancante.)
    # Selezione BILANCIATA: un terzo sinistra, un terzo centro, un terzo destra.
    # Prima era "tutti i lati + riempi col centro": quando i lati sono tanti
    # (es. con Google News) il centro veniva schiacciato fuori dal pool e i
    # confronti a 3 colonne non si formavano. Ora ogni colonna ha la sua quota,
    # gli estremi scarsi (SR/DR) entrano per primi, e il surplus di una colonna
    # corta va alle altre (non si spreca il tetto).
    MAX_ART = 850
    if len(articoli) > MAX_ART:
        prim = [a for a in articoli if a.get("primaria")]
        prim_ids = {id(a) for a in prim}
        resto = [a for a in articoli if id(a) not in prim_ids]

        def _recenti(pool, estremi):
            est = sorted((a for a in pool if a.get("area") in estremi),
                         key=lambda a: a.get("pubblicato", ""), reverse=True)
            mod = sorted((a for a in pool if a.get("area") not in estremi),
                         key=lambda a: a.get("pubblicato", ""), reverse=True)
            return est + mod          # gli estremi (merce scarsa) non li perdiamo

        colonne = [
            _recenti([a for a in resto if a.get("area") in ("SR", "CS")], {"SR"}),
            _recenti([a for a in resto if a.get("area") == "C"], set()),
            _recenti([a for a in resto if a.get("area") in ("CD", "DR")], {"DR"}),
        ]
        budget = MAX_ART - len(prim)
        quote = [0, 0, 0]
        assegnati = 0
        while assegnati < budget and any(quote[i] < len(colonne[i]) for i in range(3)):
            for i in range(3):
                if assegnati >= budget:
                    break
                if quote[i] < len(colonne[i]):
                    quote[i] += 1
                    assegnati += 1

        tenuti = list(prim)
        for c, q in zip(colonne, quote):
            tenuti += c[:q]

        n_c = sum(1 for a in tenuti if a.get("area") == "C")
        n_l = sum(1 for a in tenuti if a.get("area") in ("SR", "CS", "CD", "DR"))
        print("  troppi articoli (%d): raggruppo i %d bilanciati "
              "(%d lati + %d centro + agenda)"
              % (len(articoli), len(tenuti), n_l, n_c))
        articoli = tenuti
    # Al modello NON serve l'id vero (sha1 da 10 caratteri): gli basta
    # un'etichetta corta per indicare i titoli. Usiamo un indice progressivo
    # (1, 2, 3...) e lo ritraduciamo in id vero qui in Python. Cosi' ogni id
    # occupa ~1 token invece di ~5, sia nei titoli in ingresso sia negli "ids"
    # che il modello ci rimanda: e' il passo su Sonnet, quello che pesa di piu'.
    # L'ora e' TORNATA (26 set): senza, il modello univa la proposta di tregua
    # del mattino col «no» di Trump della sera. Costa pochi token, ne vale la pena.
    per_key = {}
    righe = []
    for n, a in enumerate(articoli, 1):
        k = str(n)
        per_key[k] = a
        # la testata serve al modello per capire il registro, la posizione politica NO.
        # L'ora serve: due titoli a 7 ore di distanza sono quasi sempre due
        # momenti diversi della vicenda (proposta vs rifiuto), non la stessa notizia.
        righe.append("%s (%s) [%s] %s" % (k, _ora_breve(a.get("pubblicato", "")), a["fonte"], a["titolo"]))
    prompt = PROMPT_RAGGRUPPA.format(ore=ore, titoli="\n".join(righe))

    dati, uso = chiama(client, prompt, SCHEMA_RAGGRUPPA, max_tokens=16000, modello=MODELLO_RAGGRUPPA)
    print("  passo 1 raggruppamento (%s): %d token in, %d out" % (MODELLO_RAGGRUPPA, uso.input_tokens, uso.output_tokens))
    n_gruppi = len(dati.get("eventi", []))
    print("  gruppi (2+ titoli) proposti dal modello: %d" % n_gruppi)
    if uso.output_tokens >= 15500:
        print("  ATTENZIONE: risposta ancora vicina al limite dei token")

    eventi, usati = [], set()
    for ev in dati.get("eventi", []):
        if not isinstance(ev, dict):
            continue                      # output malformato del modello: lo salto
        ids = ev.get("ids")
        if not isinstance(ids, list):
            continue
        membri = []
        for i in ids:
            k = str(i)
            if k in per_key and k not in usati:
                membri.append(per_key[k])
                usati.add(k)
        if membri:
            nuovo_ev = {
                "titolo_neutro": (ev.get("titolo_neutro") or membri[0]["titolo"]).strip(),
                "fatto_specifico": (ev.get("fatto_specifico") or "").strip(),
                "tema": ev.get("tema", "altro"),
                "articoli": membri,
            }
            # rete di sicurezza: il prompt vieta di ricopiare un titolo, ma capita.
            _correggi_titolo_neutro(nuovo_ev)
            eventi.append(nuovo_ev)

    persi = [per_key[k] for k in per_key if k not in usati]
    if persi:
        print("  %d articoli non assegnati, li tengo come eventi singoli" % len(persi))
        for a in persi:
            eventi.append({"titolo_neutro": a["titolo"], "fatto_specifico": a["titolo"],
                           "tema": "altro", "articoli": [a]})
    return eventi


# --- RAGGRUPPAMENTO DA GOOGLE NEWS ----------------------------------------
# Dal 26/9/2026 il raggruppamento parte dalle storie di Google News (vedi
# gnews.py): Google decide QUALI sono le notizie e chi le racconta (il nucleo);
# il modello deve solo dire, per ogni nostro titolo, se racconta una di quelle
# notizie. E' un lavoro molto piu' facile e preciso che trovare da zero le
# coppie fra 850 titoli. Se le storie mancano (Google non risponde) o la
# chiamata fallisce, si torna a raggruppa() come prima.
MIN_STORIE = 10

SCHEMA_ABBINA = {
    "name": "registra_abbinamenti",
    "description": "Registra, per ogni notizia di Google, quali titoli delle nostre testate raccontano quello stesso fatto.",
    "input_schema": {
        "type": "object",
        "properties": {
            "notizie": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "notizia": {"type": "integer", "description": "Il numero della notizia (N1, N2... -> 1, 2...)."},
                        "tema": {
                            "type": "string",
                            "enum": ["politica interna", "esteri", "economia", "cronaca", "giustizia", "societa", "immigrazione", "ambiente", "sport", "cultura", "altro"],
                            "description": "'sport' per QUALSIASI notizia su partite, risultati, squadre, nazionali, atleti o ex atleti. 'cultura' per spettacolo, musica, premi, cinema, tv, celebrita'.",
                        },
                        "ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "I numeri dei nostri titoli che raccontano LO STESSO fatto allo STESSO stadio. Lista vuota se nessuno.",
                        },
                        "cerca": {
                            "type": "string",
                            "description": "2-4 parole chiave per cercare QUESTA notizia su Google News: nomi propri, luoghi, la parola del fatto (es. 'Bratan Milano-Meda', 'Fairford base Raf arresti'). Niente parole generiche.",
                        },
                    },
                    "required": ["notizia", "tema", "ids", "cerca"],
                },
            }
        },
        "required": ["notizie"],
    },
}

PROMPT_ABBINA = """Qui sotto trovi due elenchi.

1) NOTIZIE: le notizie del giorno come le ha raggruppate Google News. Per ognuna c'è il titolo di testa (con l'ora) e le testate che Google ha messo nello stesso gruppo. Queste notizie sono già decise: NON devi inventarne altre né unirle fra loro.

2) TITOLI: i titoli delle ultime {ore} ore dalle nostre testate, con data e ora.

Il tuo compito: per ogni notizia, indica quali TITOLI raccontano ESATTAMENTE quel fatto. Il sito mette a confronto come testate di orientamento diverso titolano la stessa notizia, quindi l'abbinamento deve essere preciso:

- **Stesso fatto.** Il titolo parla dello stesso episodio, non dello stesso argomento. «Garofano sentito in procura» e «La difesa di Sempio attende le nuove prove» sono entrambi su Garlasco ma sono fatti diversi. «Eni mette un tetto ai prezzi» e «I viaggi in Africa di Meloni con Descalzi» sono fatti diversi.
- **Stesso stadio della vicenda.** Se la notizia è «Trump respinge la proposta dell'Iran», un titolo che racconta ancora solo «l'Iran propone una tregua» (senza il no) NON va abbinato: è il momento prima. Guarda l'ora: titoli di molte ore prima della notizia sono i primi sospettati.
- **Parole diverse vanno bene.** Lo stesso fatto titolato con parole opposte o cariche («Trump gela l'Iran» / «no di Trump alla tregua») VA abbinato: è proprio il confronto che serve. Anche un commento o un retroscena su quel fatto va bene.
- **I titoli carichi e di parte sono i PIU' preziosi.** Il sito vive di confronto: il titolo urlato di un giornale di destra o di sinistra, il commento, l'editoriale, il retroscena polemico sullo STESSO fatto vanno SEMPRE abbinati, anche se usano parole cariche («terrore», «vergogna», «schiaffo»), aggiungono dettagli (nazionalita', colpe, bersagli politici) o sono scritti come opinione. Per ogni notizia cerca attivamente anche le versioni di Il Manifesto, Il Fatto, Domani, Repubblica, Open, HuffPost, Fanpage da un lato e di La Verita', Libero, Il Giornale, Il Tempo, Il Foglio, Secolo d'Italia, Il Primato dall'altro. Ne servono PIU' d'una per lato, se ci sono.
- Ogni titolo va al massimo in UNA notizia. La maggior parte dei titoli non corrisponde a nessuna notizia: è normale, lasciali fuori.

Riporta una voce per OGNI notizia (anche con ids vuoto), con il tema.

NOTIZIE:

{notizie}

TITOLI:

{titoli}

Chiama registra_abbinamenti."""


def _pool_bilanciato(articoli, massimo):
    """Stessa selezione di raggruppa(): un terzo per colonna, estremi per primi."""
    if len(articoli) <= massimo:
        return articoli

    def _recenti(pool, estremi):
        est = sorted((a for a in pool if a.get("area") in estremi),
                     key=lambda a: a.get("pubblicato", ""), reverse=True)
        mod = sorted((a for a in pool if a.get("area") not in estremi),
                     key=lambda a: a.get("pubblicato", ""), reverse=True)
        return est + mod

    colonne = [
        _recenti([a for a in articoli if a.get("area") in ("SR", "CS")], {"SR"}),
        _recenti([a for a in articoli if a.get("area") == "C"], set()),
        _recenti([a for a in articoli if a.get("area") in ("CD", "DR")], {"DR"}),
    ]
    quote, assegnati = [0, 0, 0], 0
    while assegnati < massimo and any(quote[i] < len(colonne[i]) for i in range(3)):
        for i in range(3):
            if assegnati < massimo and quote[i] < len(colonne[i]):
                quote[i] += 1
                assegnati += 1
    tenuti = []
    for c, q in zip(colonne, quote):
        tenuti += c[:q]
    return tenuti


def raggruppa_da_google(client, articoli, storie, ore):
    """Eventi costruiti sulle storie di Google. Ritorna None se non si puo'."""
    import hashlib
    import gnews
    fonti = json.loads((BASE / "sources.json").read_text(encoding="utf-8"))["sources"]
    testate = gnews.Testate(fonti)

    # le storie che contano: non sport, con almeno una testata nostra nel nucleo
    # o comunque in agenda (le principali). Ordine: principali, poi sezioni.
    ordine_sez = {"principali": 0, "italia": 1, "politica": 2, "mondo": 3, "economia": 4}
    storie = sorted(storie, key=lambda s: (ordine_sez.get(s["sezione"], 9), s["ordine"]))

    # la stessa notizia compare spesso sia nelle principali sia in una sezione,
    # con un titolo di testa diverso: se due storie condividono un pezzo del
    # nucleo (stessa testata, stesso titolo) sono la stessa, e si tiene la prima
    # (quella delle principali), aggiungendo al nucleo i pezzi nuovi.
    unite, firma_di = [], {}
    for st in storie:
        firme = {(n.get("fonte_google", ""), " ".join(gnews._norm_titolo(n["titolo"]))[:60])
                 for n in st["nucleo"]}
        gia = next((firma_di[f] for f in firme if f in firma_di), None)
        if gia is None:
            gia = dict(st, nucleo=list(st["nucleo"]))
            unite.append(gia)
        else:
            noti = {(n.get("fonte_google", ""), n["titolo"]) for n in gia["nucleo"]}
            gia["nucleo"] += [n for n in st["nucleo"] if (n.get("fonte_google", ""), n["titolo"]) not in noti]
        for f in firme:
            firma_di.setdefault(f, gia)
    if len(unite) < len(storie):
        print("  storie Google unite perche' uguali fra sezioni: %d -> %d" % (len(storie), len(unite)))
    storie = unite

    reali = [a for a in articoli if a.get("area") in AREE]
    per_fonte = {}
    for a in reali:
        per_fonte.setdefault(a["fonte"], []).append(a)

    # 1) il nucleo: i pezzi del gruppo di Google che abbiamo anche noi (stesso
    #    pezzo, stessa testata) entrano subito, con la loro ora vera.
    presi = set()
    eventi = []
    for st in storie:
        membri = []
        for j, n in enumerate(st["nucleo"]):
            chi = testate.riconosci(n.get("fonte_google", ""), n.get("url_fonte", ""))
            if not chi:
                continue
            nome, area = chi
            trovato = next((a for a in per_fonte.get(nome, [])
                            if id(a) not in presi and gnews.stesso_titolo(a["titolo"], n["titolo"])), None)
            if trovato is None and j == 0 and n.get("link"):
                # la voce di testa di Google: ora esatta nota (pubDate), la
                # teniamo anche se il nostro feed non l'aveva (link Google)
                trovato = {
                    "id": hashlib.sha1(n["link"].encode()).hexdigest()[:10],
                    "titolo": n["titolo"], "url": n["link"],
                    "pubblicato": st["pubblicato"], "fonte": nome,
                    "feed": nome + " (google news, nucleo)",
                    "dominio": gnews.dominio(n.get("url_fonte", "")),
                    "area": area, "primaria": False, "ordine_feed": 0, "immagine": None,
                }
            if trovato is not None:
                presi.add(id(trovato))
                membri.append(trovato)
        eventi.append({
            "titolo_neutro": st["titolo"],
            "fatto_specifico": st["titolo"],
            "tema": "altro",
            "articoli": membri,
            "google": {"sezione": st["sezione"], "ordine": st["ordine"],
                       "nucleo": [n.get("fonte_google", "") for n in st["nucleo"]]},
            "ordine_google": st["ordine"] if st["sezione"] == "principali" else None,
        })
    nel_nucleo = sum(len(e["articoli"]) for e in eventi)

    # 2) il modello abbina gli altri nostri titoli alle storie
    liberi = _pool_bilanciato([a for a in reali if id(a) not in presi], 850)
    per_key, righe_t = {}, []
    for n, a in enumerate(liberi, 1):
        per_key[str(n)] = a
        righe_t.append("%d (%s) [%s] %s" % (n, _ora_breve(a.get("pubblicato", "")), a["fonte"], a["titolo"]))
    righe_n = []
    for n, (st, ev) in enumerate(zip(storie, eventi), 1):
        altri = "; ".join("%s: %s" % (x.get("fonte_google", ""), x["titolo"][:90]) for x in st["nucleo"][1:5])
        righe_n.append("N%d (%s) %s%s" % (n, _ora_breve(st["pubblicato"]), st["titolo"],
                                          ("\n     anche: " + altri) if altri else ""))
    prompt = PROMPT_ABBINA.format(ore=ore, notizie="\n".join(righe_n), titoli="\n".join(righe_t))
    dati, uso = chiama(client, prompt, SCHEMA_ABBINA, max_tokens=16000, modello=MODELLO_RAGGRUPPA)
    print("  passo 1 abbinamento a Google (%s): %d token in, %d out"
          % (MODELLO_RAGGRUPPA, uso.input_tokens, uso.output_tokens))

    usati, aggiunti = set(), 0
    for voce in dati.get("notizie", []):
        if not isinstance(voce, dict):
            continue
        n = voce.get("notizia", 0)
        if not isinstance(n, int) or not (1 <= n <= len(eventi)):
            continue
        ev = eventi[n - 1]
        ev["tema"] = voce.get("tema", "altro")
        ev["cerca"] = (voce.get("cerca") or "").strip()
        for k in voce.get("ids") or []:
            k = str(k)
            if k in per_key and k not in usati:
                usati.add(k)
                ev["articoli"].append(per_key[k])
                aggiunti += 1

    eventi = [e for e in eventi if e["articoli"]]
    for e in eventi:
        _correggi_titolo_neutro(e)
    # i titoli non abbinati restano eventi singoli (non si pubblicano)
    for k, a in per_key.items():
        if k not in usati:
            eventi.append({"titolo_neutro": a["titolo"], "fatto_specifico": a["titolo"],
                           "tema": "altro", "articoli": [a]})
    print("  storie Google: %d | titoli dal nucleo: %d | abbinati dal modello: %d"
          % (len(storie), nel_nucleo, aggiunti))
    return eventi


MAX_RICERCHE = int(os.environ.get("ILVAGLIO_MAX_RICERCHE", "45"))


def ricerca_mirata(eventi, articoli):
    """Per ogni notizia candidata cerca su Google News TUTTE le versioni delle
    nostre testate (28/9, caso Bratan: il titolo strillato di Libero non era
    nel feed di Libero, ma la ricerca lo trova, insieme a Secolo, Adnkronos e
    al Fanpage con l'avvocato). I titoli trovati entrano nel gruppo e passano
    poi da verifica(), finestra oraria e controlla_trio() come tutti gli altri.
    Solo HTTP, zero token."""
    import hashlib
    import time as _t
    import gnews
    fonti = json.loads((BASE / "sources.json").read_text(encoding="utf-8"))["sources"]
    testate = gnews.Testate(fonti)
    gia_url = {a.get("url") for a in articoli}
    cand = [ev for ev in eventi if ev.get("cerca") and ev.get("tema") not in TEMI_ESCLUSI
            and len([a for a in ev["articoli"] if a.get("area") in AREE]) >= 2]
    cand.sort(key=lambda ev: (ev.get("ordine_google") is None, ev.get("ordine_google") or 0,
                              -len(ev["articoli"])))
    cand = cand[:MAX_RICERCHE]
    aggiunti = 0
    for ev in cand:
        for r in gnews.cerca(ev["cerca"]):
            chi = testate.riconosci(r["fonte_google"], r["url_fonte"])
            if not chi or r["link"] in gia_url:
                continue
            nome, area = chi
            if any(a["fonte"] == nome and gnews.stesso_titolo(a["titolo"], r["titolo"]) for a in ev["articoli"]):
                continue
            if RUMORE_SPORT.search(r["titolo"]):
                continue
            ev["articoli"].append({
                "id": hashlib.sha1(r["link"].encode()).hexdigest()[:10],
                "titolo": r["titolo"], "url": r["link"], "pubblicato": r["pubblicato"],
                "fonte": nome, "feed": nome + " (google news, ricerca)",
                "dominio": gnews.dominio(r["url_fonte"]), "area": area,
                "primaria": False, "ordine_feed": 0, "immagine": None, "da_ricerca": True,
            })
            gia_url.add(r["link"])
            aggiunti += 1
        _t.sleep(0.4)
    print("  ricerca mirata su Google News: %d notizie, %d titoli nuovi dalle nostre testate"
          % (len(cand), aggiunti))
    return eventi


def verifica(client, eventi):
    """Passo 1.5: rilegge i gruppi e caccia i titoli che non c'entrano.

    È il passaggio che evita di mettere gli Europei di atletica e quelli di
    nuoto nello stesso confronto. Chi viene cacciato diventa un evento a sé.
    """
    candidati = [(i, ev) for i, ev in enumerate(eventi) if len(ev["articoli"]) >= 2]
    if not candidati:
        return eventi

    # Stesso trucco del raggruppamento: al posto dell'id sha1 diamo al modello
    # una chiave corta ("gruppo-posizione", es. 3-2) e la ritraduciamo. Meno
    # token nei titoli mostrati e negli id che ci rimanda in "da_togliere".
    per_key = {}
    blocchi = []
    for n, (_, ev) in enumerate(candidati, 1):
        righe = ["Gruppo %d" % n,
                 "  fatto dichiarato: %s" % (ev.get("fatto_specifico") or ev["titolo_neutro"])]
        for j, a in enumerate(ev["articoli"], 1):
            k = "%d-%d" % (n, j)
            per_key[k] = a
            righe.append('  %s (%s) [%s] "%s"' % (k, _ora_breve(a.get("pubblicato", "")), a["fonte"], a["titolo"]))
        blocchi.append("\n".join(righe))

    dati, uso = chiama(client, PROMPT_VERIFICA.format(gruppi="\n\n".join(blocchi)), SCHEMA_VERIFICA)
    print("  verifica: %d token in, %d out" % (uso.input_tokens, uso.output_tokens))

    espulsi_totali, tocchi = [], 0
    for voce in dati.get("controlli", []):
        if not isinstance(voce, dict):
            continue
        n = voce.get("evento", 0)
        da_togliere_keys = set(str(x) for x in (voce.get("da_togliere") or []))
        da_togliere = {per_key[k]["id"] for k in da_togliere_keys if k in per_key}
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
        # il titolo_neutro l'ha scritto raggruppa() PRIMA di sapere chi sarebbe
        # stato espulso: se era la copia di un titolo appena cacciato, resta
        # orfano - il lettore leggerebbe in cima la fonte di un articolo che
        # tre righe sotto non compare piu'. Lo si corregge sui membri rimasti.
        if _correggi_titolo_neutro(eventi[idx], contro_membri=espulsi):
            print("    gruppo %d: titolo_neutro era copiato da un titolo espulso, corretto" % n)
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


def _colonna_di(a):
    area = a.get("area")
    for chiave, _, aree in COLONNE:
        if area in aree:
            return chiave
    return None


def stringi_nel_tempo(eventi, finestra_ore=FINESTRA_ORE):
    """Tiene in ogni gruppo solo i titoli scritti nelle STESSE ore.

    Fra tutte le finestre di `finestra_ore` ore si sceglie quella che copre piu'
    colonne (sinistra/centro/destra), poi con piu' testate, poi la piu' recente.
    Chi sta fuori diventa un evento a se': meglio perdere un confronto che
    mostrarne uno fra due momenti diversi della notizia. Tutto in Python, zero
    token, e non si fida del modello: e' la garanzia dura sulla regola delle ore.
    """
    if finestra_ore <= 0:
        return eventi
    larghezza = finestra_ore * 3600
    fuori_tot, toccati = [], 0
    for ev in eventi:
        arts = [a for a in ev["articoli"] if _dt(a.get("pubblicato", ""))]
        if len(arts) < 2:
            continue
        arts.sort(key=lambda a: _dt(a["pubblicato"]))
        ts = [_dt(a["pubblicato"]).timestamp() for a in arts]
        if ts[-1] - ts[0] <= larghezza:
            continue                                  # gia' tutto nelle stesse ore
        migliore, punteggio = None, None
        for i in range(len(arts)):
            dentro = [a for a, t in zip(arts, ts) if ts[i] <= t <= ts[i] + larghezza]
            colonne = {_colonna_di(a) for a in dentro} - {None}
            testate = {a["fonte"] for a in dentro if a.get("area") in AREE}
            # 28/9 (caso Bratan): a parita' di colonne vince la finestra con le
            # versioni PIU' DI PARTE (estremi + titoli carichi), non la piu'
            # recente: prima vinceva domenica mattina e Libero di sabato restava fuori.
            forza = sum(1 for a in dentro if a.get("area") in ("SR", "DR")) \
                + sum(1 for a in dentro if a.get("area") in ("SR", "CS", "CD", "DR")
                      and allarme(a.get("titolo", "")) >= SOGLIA_CARICO)
            p = (len(colonne), forza, len(testate), len(dentro), ts[i])
            if punteggio is None or p > punteggio:
                migliore, punteggio = dentro, p
        tenuti = {id(a) for a in migliore}
        # i titoli di parte molto carichi restano anche se un po' fuori orario
        t_min = min(_dt(a["pubblicato"]).timestamp() for a in migliore)
        t_max = max(_dt(a["pubblicato"]).timestamp() for a in migliore)
        extra = FINESTRA_LUNGA * 3600
        for a in arts:
            if id(a) in tenuti or a.get("area") not in ("SR", "CS", "CD", "DR"):
                continue
            t = _dt(a["pubblicato"]).timestamp()
            if t_max - extra <= t <= t_min + extra and allarme(a.get("titolo", "")) >= SOGLIA_CARICO:
                tenuti.add(id(a))
                a["fuori_orario_carico"] = True
        fuori = [a for a in ev["articoli"] if id(a) not in tenuti]
        if not fuori:
            continue
        ev["articoli"] = [a for a in ev["articoli"] if id(a) in tenuti]
        ev["stretto_nel_tempo"] = True
        _correggi_titolo_neutro(ev, contro_membri=fuori)
        fuori_tot.extend(fuori)
        toccati += 1
    for a in fuori_tot:
        eventi.append({"titolo_neutro": a["titolo"], "fatto_specifico": a["titolo"],
                       "tema": "altro", "articoli": [a], "fuori_finestra": True})
    print("  finestra %.0fh: %d gruppi ristretti, %d titoli fuori orario rimessi da soli"
          % (finestra_ore, toccati, len(fuori_tot)))
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
        if ev.get("ordine_google") is not None:
            # storia delle notizie principali di Google: e' in agenda per definizione
            ev["principale"] = len(reali) >= 2
        # ordine dell'agenda: comanda l'aggregatore (Google News). Gli eventi in
        # topnews d'agenzia ma non in GN vengono dopo (offset 100).
        agg = [a for a in primari if a.get("area") == AGGREGATORE]
        if ev.get("ordine_google") is not None:
            ev["ordine_agenzia"] = ev["ordine_google"]
        elif agg:
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
        scelto_c = (ev.get("scelta") or {}).get("centro")
        if scelto_c:
            a_c = next((a for a in ev["articoli"] if a.get("id") == scelto_c and a.get("area") == "C"), None)
            if a_c is not None:
                ev["riferimento"] = dict(a_c, agenzia=a_c.get("dominio", "") in AGENZIE_CENTRO)
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


SCHEMA_TRIO = {
    "name": "registra_controllo",
    "description": "Per ogni confronto, i titoli che NON raccontano lo stesso fatto.",
    "input_schema": {
        "type": "object",
        "properties": {
            "controlli": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "confronto": {"type": "integer"},
                        "fatto": {"type": "string", "description": "In una riga, il fatto comune che raccontano i titoli giusti."},
                        "fuori": {"type": "array", "items": {"type": "string"},
                                  "description": "Le sigle (es. 3-2) dei titoli che raccontano un ALTRO fatto. Vuota se sono tutti lo stesso fatto."},
                        "motivo": {"type": "string"},
                        "sinistra": {"type": "string", "description": "Sigla del titolo di SINISTRA (tra quelli rimasti) piu' di parte e strillato."},
                        "centro": {"type": "string", "description": "Sigla del titolo di CENTRO (tra quelli rimasti) piu' asciutto e neutro, preferibilmente d'agenzia."},
                        "destra": {"type": "string", "description": "Sigla del titolo di DESTRA (tra quelli rimasti) piu' di parte e strillato."},
                    },
                    "required": ["confronto", "fatto", "fuori", "motivo", "sinistra", "centro", "destra"],
                },
            }
        },
        "required": ["controlli"],
    },
}

PROMPT_TRIO = """Questi sono i confronti che stanno per essere pubblicati. Per ognuno trovi TUTTI i titoli che il lettore vedra' (quelli marcati IN PAGINA sono i tre affiancati, gli altri compaiono come «Anche:»). Il sito afferma che raccontano TUTTI LA STESSA NOTIZIA. Controlla titolo per titolo che sia vero.

Per ogni confronto scrivi il fatto comune e indica in "fuori" le sigle dei titoli che raccontano un FATTO DIVERSO, anche se collegato. Esempi di fatto diverso:
- «L'Idf elimina il terrorista che rapi' Noa Argamani» e «Olmert: Netanyahu sapeva del 7 ottobre» -> stessa vicenda di fondo, fatti DIVERSI: fuori.
- «Garofano sentito in procura» e «La difesa di Sempio attende le prove» -> fatti diversi.
- «Eni mette un tetto ai prezzi» e «I viaggi in Africa di Meloni con Descalzi» -> fatti diversi.
- «L'Iran propone una tregua» e «Trump respinge la proposta» -> momenti diversi: fuori quello che non contiene ancora il fatto nuovo.

NON e' fuori — e anzi e' il titolo piu' prezioso — un titolo che racconta lo STESSO fatto:
- con parole diverse, cariche o di parte, o con dettagli in piu' (origine, colpe, bersagli politici);
- criticandolo o commentandolo (Il Manifesto che critica il tetto ai prezzi Eni il giorno in cui scatta = stesso fatto);
- indicando una causa, una pista o un responsabile (la «pista iraniana» sull'allarme alla base RAF; «colpa di Vannacci» sul calo dell'affluenza = stesso fatto);
- con MENO dettagli degli altri (un titolo che non cita la causa non e' un altro fatto).
E' fuori SOLO se racconta un EVENTO diverso: un'altra dichiarazione di un'altra persona, un altro episodio, un'altra storia (es. il ritratto della contadina che diede l'allarme), un altro momento della vicenda. Nel dubbio, NON togliere.

POI, tra i titoli rimasti, scegli i tre da mettere IN PAGINA (una sigla per colonna; la colonna di ogni titolo e' indicata fra parentesi quadre):
- SINISTRA e DESTRA: il titolo piu' DI PARTE e STRILLATO di quel lato, quello che un lettore di quell'area riconoscerebbe come "suo" e che si allontana di PIU' dal titolo asciutto del centro. In ordine di forza:
  1. una frase secca di un politico o di una parte in causa che prende posizione («Piantedosi: imbarcato sul primo volo», «L'avvocato: vicenda ingigantita», «Meloni: un bel segnale»);
  2. un attacco o un bersaglio politico («la sinistra si indigna», «dalla destra solo gogna»), un'accusa, un'ironia;
  3. parole cariche o dettagli identitari («terrore», «26enne di origini egiziane», «mai piu' in Italia»);
  4. solo dopo, un titolo di cronaca, anche se ben scritto.
  Esempio reale (trapper Bratan): a destra «Bratan blocca la Milano-Meda: espulso. Piantedosi: "Imbarcato sul primo volo"» (Libero) batte «per le autorita' e' un pericolo pubblico» (Il Giornale); a sinistra «L'avvocato: "Vicenda ingigantita, mai vista questa rapidita'"» (Fanpage) batte «espulso dall'Italia dopo 9 giorni» (La Stampa). A parita', preferisci la testata piu' estrema.
- CENTRO: il titolo piu' ASCIUTTO e fattuale, meglio se d'agenzia (ANSA, AGI, LaPresse, Adnkronos, Italpress, Askanews, Dire). Mai un titolo con citazioni sensazionali, virgolette ad effetto o parole cariche, se ce n'e' uno piu' neutro.

{confronti}

Chiama registra_controllo con un controllo per ogni confronto."""


def controlla_trio(client, eventi, giri=2):
    """Controllo finale su TUTTI i titoli dei confronti che vanno in pagina
    (28/9, caso Israele: Fanpage su Olmert-Netanyahu accanto all'uccisione del
    rapitore di Noa; Simone: «l'attenzione deve essere su tutti gli
    articoli»). Ogni titolo che racconta un altro fatto esce dal gruppo: la
    colonna passa al titolo successivo, o resta vuota e il confronto non esce.
    Il secondo giro ricontrolla i confronti cambiati."""
    def _pieno(ev):
        return all(ev["per_colonna"].get(k) for k in ("sinistra", "centro", "destra"))
    da_controllare = None
    for giro in range(1, giri + 1):
        cand = [ev for ev in eventi if _pieno(ev) and ev.get("tema") not in TEMI_ESCLUSI
                and (da_controllare is None or id(ev) in da_controllare)]
        if not cand:
            return eventi
        per_key, blocchi = {}, []
        for n, ev in enumerate(cand, 1):
            sx, dx = lati_mostrati(ev)
            in_pagina = {id(x): col for x, col in ((sx, "sinistra"), (ev.get("riferimento"), "centro"), (dx, "destra")) if x}
            righe = ["Confronto %d" % n]
            for k, a in enumerate(ordina_da_sinistra([x for x in ev["articoli"] if x.get("area") in AREE]), 1):
                sigla = "%d-%d" % (n, k)
                per_key[sigla] = (ev, a)
                marca = next((c for x, c in in_pagina.items() if x == id(a) or
                              (c == "centro" and ev.get("riferimento", {}).get("id") == a.get("id"))), None)
                righe.append('  %s [%s, %s, %s]%s "%s"' % (sigla, COLONNA_DI.get(a.get("area"), "?"), a["fonte"],
                                                          _ora_breve(a.get("pubblicato", "")),
                                                          " ora in pagina" if marca else "", a["titolo"]))
            blocchi.append("\n".join(righe))
        try:
            dati, uso = chiama(client, PROMPT_TRIO.format(confronti="\n\n".join(blocchi)), SCHEMA_TRIO,
                               modello=MODELLO_RAGGRUPPA)
        except BudgetEsaurito:
            raise
        except Exception as exc:
            print("  controllo finale dei titoli saltato: %s" % str(exc)[:120])
            return eventi
        tolti, cambiati, scelte = 0, set(), 0
        for voce in dati.get("controlli", []):
            if not isinstance(voce, dict):
                continue
            # la scelta dei titoli da mostrare (vale se il titolo resta nel gruppo)
            for col in ("sinistra", "centro", "destra"):
                ev_a = per_key.get(str(voce.get(col) or "").strip())
                if ev_a and COLONNA_DI.get(ev_a[1].get("area")) == col:
                    ev_a[0].setdefault("scelta", {})[col] = ev_a[1].get("id")
                    scelte += 1
            for sigla in voce.get("fuori") or []:
                ev_a = per_key.get(str(sigla).strip())
                if not ev_a:
                    continue
                ev, a = ev_a
                if not any(x is a for x in ev["articoli"]):
                    continue
                ev["articoli"] = [x for x in ev["articoli"] if x is not a]
                eventi.append({"titolo_neutro": a["titolo"], "fatto_specifico": a["titolo"],
                               "tema": "altro", "articoli": [a], "tolto_dal_controllo": True})
                cambiati.add(id(ev))
                tolti += 1
                print("    tolto %s (%s) - %s" % (sigla, a["fonte"], (voce.get("motivo") or "")[:90]))
        print("  controllo finale dei titoli (giro %d): %d confronti, %d titoli tolti, %d titoli scelti per la pagina"
              % (giro, len(cand), tolti, scelte))
        eventi = arricchisci(eventi)       # applica anche la scelta dei titoli da mostrare
        if not tolti:
            return eventi
        da_controllare = cambiati
    return eventi


def decodifica_link(eventi):
    """I titoli arrivati da Google News hanno un link news.google.com: il lettore
    deve finire sul sito del giornale (Simone, 28/9: «clicco HuffPost e mi apre
    Google News»). Si decodificano i link dei titoli MOSTRATI nei confronti a
    tre colonne (quelli cliccabili). Libreria googlenewsdecoder; se fallisce il
    link resta quello di Google, che comunque porta all'articolo."""
    try:
        from googlenewsdecoder import gnewsdecoder
    except Exception as exc:
        print("  decodifica link saltata: %s" % str(exc)[:80])
        return eventi
    def _pieno(ev):
        return all(ev["per_colonna"].get(k) for k in ("sinistra", "centro", "destra"))
    bersagli = []
    for ev in eventi:
        if not _pieno(ev) or ev.get("tema") in TEMI_ESCLUSI:
            continue
        sx, dx = lati_mostrati(ev)
        rif_id = (ev.get("riferimento") or {}).get("id")
        for a in ev["articoli"]:
            if (a is sx or a is dx or a.get("id") == rif_id) and "news.google.com" in (a.get("url") or ""):
                bersagli.append(a)
    if not bersagli:
        return eventi
    ok = 0
    for k in range(0, len(bersagli), 40):
        blocco = bersagli[k:k + 40]
        try:
            res = gnewsdecoder([a["url"] for a in blocco], interval=0.3)
        except Exception as exc:
            print("  decodifica link fallita: %s" % str(exc)[:100])
            break
        for a, r in zip(blocco, res if isinstance(res, list) else [res]):
            if isinstance(r, dict) and r.get("success") and r.get("decoded_url"):
                a["url"] = r["decoded_url"]
                ok += 1
    print("  link Google News convertiti nel link del giornale: %d su %d" % (ok, len(bersagli)))
    return arricchisci(eventi)


def analizza(client, eventi, quanti, ampiezza_minima=2):
    """Divergenza, duello, nota e titolo grande per i confronti PUBBLICABILI.

    Lezione del 27/9: prima si analizzavano i primi 22 eventi ordinati per
    distanza fra gli estremi, e dopo la regola delle 5 ore in cima c'erano
    eventi a DUE colonne (che non si pubblicano): i confronti pubblicati
    uscivano tutti senza divergenza e senza nota. Ora si analizzano SOLO gli
    eventi con tre colonne piene (gli unici che escono), a blocchi da 12, e chi
    resta senza analisi viene riprovato una volta."""
    def _pieno(ev):
        return all(ev["per_colonna"].get(k) for k in ("sinistra", "centro", "destra"))
    idx = [i for i, ev in enumerate(eventi)
           if ev.get("tema") not in TEMI_ESCLUSI and _pieno(ev)]
    idx.sort(key=lambda i: (not eventi[i].get("principale"),
                            eventi[i].get("ordine_agenzia", 999)))
    idx = idx[:max(quanti, 1)]
    if not idx:
        print("  passo 2 saltato: nessun confronto a tre colonne")
        return
    for giro in (1, 2):
        mancano = [i for i in idx if not eventi[i].get("nota")]
        if not mancano:
            break
        if giro == 2:
            print("  analisi: riprovo %d confronti rimasti senza nota" % len(mancano))
        for k in range(0, len(mancano), 12):
            blocco = [(i, eventi[i]) for i in mancano[k:k + 12]]
            try:
                _analizza_blocco(client, eventi, blocco)
            except BudgetEsaurito:
                raise
            except Exception as exc:
                print("  analisi di un blocco fallita: %s" % str(exc)[:150])
    riscrivi_titoli_copiati(client, eventi, idx)
    senza = sum(1 for i in idx if not eventi[i].get("nota"))
    print("  analisi: %d confronti pubblicabili, %d senza nota" % (len(idx), senza))


SCHEMA_TITOLI = {
    "name": "registra_titoli",
    "description": "Registra un titolo neutro nuovo per ogni confronto.",
    "input_schema": {
        "type": "object",
        "properties": {
            "titoli": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "evento": {"type": "integer"},
                        "titolo": {"type": "string"},
                    },
                    "required": ["evento", "titolo"],
                },
            }
        },
        "required": ["titoli"],
    },
}

PROMPT_TITOLI = """Per ogni confronto qui sotto il titolo grande in cima e' risultato IDENTICO (o quasi) al titolo di una delle testate mostrate sotto. Non va bene: il titolo grande deve essere una sintesi NOSTRA, scritta con parole diverse da tutti i titoli.

Per ogni confronto scrivi un titolo nuovo:
- dice l'argomento essenziale ma riconoscibile: 4-9 parole, massimo 60 caratteri, cosa e' successo + a chi/dove (es. "Espulso il trapper Bratan dopo il blocco della Milano-Meda"; NON "Aggressione a Reggio Emilia", troppo generico);
- nessun dettaglio, nessun aggettivo valutativo, nessuna virgoletta;
- NON riusare la frase di nessuno dei titoli (es. "Ubriaco alla guida, travolge un operaio sulla A14" -> "Operaio ucciso sulla A14").

{blocchi}

Chiama registra_titoli."""


def _titolo_copiato_da(ev):
    return any(_titolo_copiato(ev.get("titolo_neutro", ""), a.get("titolo", ""))
               for a in ev["articoli"])


def riscrivi_titoli_copiati(client, eventi, idx):
    """Rete di sicurezza del 28/9: il titolo grande usciva a volte identico al
    lancio ANSA (il modello ricopiava, e il controllo anti-copia teneva il
    vecchio titolo, anch'esso copiato). Qui si chiede una riscrittura mirata,
    fino a due volte, solo per i confronti ancora copiati."""
    for giro in (1, 2):
        copiati = [i for i in idx if _titolo_copiato_da(eventi[i])]
        if not copiati:
            return
        blocchi = []
        for n, i in enumerate(copiati, 1):
            ev = eventi[i]
            righe = ["Confronto %d - titolo grande attuale: %s" % (n, ev["titolo_neutro"])]
            for a in ordina_da_sinistra([x for x in ev["articoli"] if x.get("area") in AREE])[:6]:
                righe.append('  [%s] "%s"' % (a["fonte"], a["titolo"]))
            blocchi.append("\n".join(righe))
        try:
            dati, uso = chiama(client, PROMPT_TITOLI.format(blocchi="\n\n".join(blocchi)), SCHEMA_TITOLI)
        except BudgetEsaurito:
            raise
        except Exception as exc:
            print("  riscrittura titoli fallita: %s" % str(exc)[:120])
            return
        for voce in dati.get("titoli", []):
            if not isinstance(voce, dict):
                continue
            n = voce.get("evento", 0)
            nuovo = (voce.get("titolo") or "").strip()
            if isinstance(n, int) and 1 <= n <= len(copiati) and nuovo:
                ev = eventi[copiati[n - 1]]
                if not any(_titolo_copiato(nuovo, a.get("titolo", "")) for a in ev["articoli"]):
                    ev["titolo_neutro"] = nuovo
        print("  titoli grandi copiati riscritti (giro %d): %d" % (giro, len(copiati)))


def _analizza_blocco(client, eventi, candidati):
    # Leggiamo un pezzo di ogni articolo (og:description + primi paragrafi) per
    # poter confrontare non solo il titolo ma il RACCONTO: tono, parole scelte,
    # cosa mette in evidenza il pezzo. Il testo non viene mai pubblicato, serve
    # solo a informare la nota. Best-effort e con un tetto, per non allungare
    # troppo il giro.
    blocchi = []
    letti = 0
    MAX_LETTURE = 0    # modalità economica "solo titoli": non leggo il corpo degli articoli
                       # (metti 8-10 per riattivare la lettura sui confronti in cima)
    cache_incipit = {}
    for n, (_, ev) in enumerate(candidati, 1):
        # I TRE titoli che finiranno DAVVERO in colonna (gli stessi che sceglie
        # render.py): la nota va costruita su questi, non su un titolo qualunque
        # del mucchio, o descrive una colonna e il sito ne mostra un'altra.
        sx, dx = lati_mostrati(ev)
        rif = ev.get("riferimento")
        mostrati = {}
        for art, col in ((sx, "sinistra"), (rif, "centro"), (dx, "destra")):
            if art:
                mostrati[(art.get("fonte"), art.get("titolo"))] = col
        trio = []
        for art, col in ((sx, "SINISTRA"), (rif, "CENTRO"), (dx, "DESTRA")):
            if art:
                trio.append('  %s -> %s: "%s"' % (col, art.get("fonte"), art.get("titolo")))
        righe = ["Evento %d - %s" % (n, ev["titolo_neutro"])]
        if trio:
            righe.append("  >>> TITOLI MOSTRATI IN COLONNA (su questi va costruita la nota):")
            righe.extend(trio)
            righe.append("  --- tutti i titoli del gruppo (per la pluralità) ---")
        # solo le testate con una linea: l'aggregatore non e' una voce da analizzare
        for a in ordina_da_sinistra([x for x in ev["articoli"] if x.get("area") in AREE]):
            marca = mostrati.get((a["fonte"], a["titolo"]))
            tag = ("  <-- IN COLONNA (%s)" % marca) if marca else ""
            righe.append('  [%s] %s: "%s"%s' % (NOMI[a["area"]], a["fonte"], a["titolo"], tag))
            url = a.get("url")
            if url and letti < MAX_LETTURE:
                if url not in cache_incipit:
                    cache_incipit[url] = leggi_incipit(url)
                    letti += 1
                if cache_incipit[url]:
                    righe.append('       estratto: %s' % cache_incipit[url])
        blocchi.append("\n".join(righe))
    print("  letti %d incipit d'articolo per l'analisi" % letti)

    prompt = PROMPT_ANALIZZA.format(eventi="\n\n".join(blocchi))
    dati, uso = chiama(client, prompt, SCHEMA_ANALIZZA)
    print("  passo 2 analisi: %d token in, %d out" % (uso.input_tokens, uso.output_tokens))

    analisi = dati.get("analisi", [])
    if isinstance(analisi, str):          # a volte il modello rimanda la lista come testo JSON
        try:
            analisi = json.loads(analisi)
        except Exception:
            analisi = []
    for voce in analisi:
        if not isinstance(voce, dict):
            continue                     # risposta malformata del modello (visto il 28/9)
        n = voce.get("evento", 0)
        if 1 <= n <= len(candidati):
            idx = candidati[n - 1][0]
            nuovo = (voce.get("titolo") or "").strip()
            if nuovo and not any(_titolo_copiato(nuovo, a.get("titolo", ""))
                                 for a in eventi[idx]["articoli"]):
                eventi[idx]["titolo_neutro"] = nuovo
            eventi[idx]["divergenza"] = voce.get("divergenza", "media")
            eventi[idx]["duello"] = voce.get("duello", "").strip()
            eventi[idx]["nota"] = voce.get("nota", "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-verifica", action="store_true",
                    help="salta il controllo che caccia gli intrusi dai gruppi (sconsigliato)")
    ap.add_argument("--no-analisi", action="store_true", help="salta il passo 2")
    ap.add_argument("--analizza", type=int, default=40, help="quanti eventi analizzare (serve la divergenza per ordinarli)")
    args = ap.parse_args()

    if not IN.exists():
        sys.exit("Non trovo %s. Lancia prima:  python ingest.py" % IN)
    dati = json.loads(IN.read_text(encoding="utf-8"))
    articoli = dati["articoli"]
    if not articoli:
        sys.exit("Nessun articolo da raggruppare. Controlla i feed con check_feeds.py")

    print("Raggruppo %d articoli da %d testate." % (len(articoli), len({a["fonte"] for a in articoli})))
    client = client_anthropic()

    global BUDGET
    BUDGET = Budget(TETTO_SPESA_USD) if TETTO_SPESA_USD > 0 else None
    if BUDGET is not None:
        if BUDGET.resta() <= 0:
            sys.exit("Tetto di spesa raggiunto: %.2f USD gia' spesi oggi (tetto %.2f). "
                     "Salto il giro; resta online l'ultima versione pubblicata."
                     % (BUDGET.totale, BUDGET.tetto))
        print("Budget di oggi: spesi %.3f USD, tetto %.2f USD." % (BUDGET.totale, BUDGET.tetto))

    storie = dati.get("storie_google") or []
    eventi = None
    if len(storie) >= MIN_STORIE:
        try:
            eventi = raggruppa_da_google(client, articoli, storie, dati.get("finestra_ore", 24))
            MODO["raggruppamento"] = "google"
            try:
                eventi = ricerca_mirata(eventi, articoli)
            except Exception as exc:
                print("  ricerca mirata saltata: %s" % str(exc)[:120])
        except BudgetEsaurito as exc:
            sys.exit("Raggruppamento fermato dal tetto di spesa (%s). "
                     "Salto il giro; resta online l'ultima versione pubblicata." % exc)
        except Exception as exc:
            print("  raggruppamento da Google fallito (%s): uso quello completo" % str(exc)[:150])
            eventi = None
    else:
        print("  storie Google insufficienti (%d): uso il raggruppamento completo" % len(storie))
    try:
        if eventi is None:
            eventi = raggruppa(client, articoli, dati.get("finestra_ore", 24))
            MODO["raggruppamento"] = "completo"
    except BudgetEsaurito as exc:
        sys.exit("Raggruppamento fermato dal tetto di spesa (%s). "
                 "Salto il giro; resta online l'ultima versione pubblicata." % exc)
    if not args.no_verifica:
        try:
            eventi = verifica(client, eventi)
        except BudgetEsaurito as exc:
            print("  verifica saltata: %s" % exc)
        except Exception as exc:
            print("  verifica saltata per un errore momentaneo: %s" % str(exc)[:150])
    eventi = stringi_nel_tempo(eventi)
    esclusi = sum(1 for e in eventi if e.get("tema") in TEMI_ESCLUSI and len(e["articoli"]) >= 2)
    if esclusi:
        print("  gruppi di sport scartati (non si pubblicano): %d" % esclusi)
    eventi = arricchisci(eventi)
    if not args.no_verifica:
        try:
            eventi = controlla_trio(client, eventi)
        except BudgetEsaurito as exc:
            print("  controllo dei tre titoli saltato: %s" % exc)
    if not args.no_analisi:
        try:
            analizza(client, eventi, args.analizza)
        except BudgetEsaurito as exc:
            print("  analisi saltata: %s" % exc)
        except Exception as exc:
            print("  analisi saltata per un errore momentaneo: %s" % str(exc)[:150])

    try:
        eventi = decodifica_link(eventi)
    except Exception as exc:
        print("  decodifica link saltata: %s" % str(exc)[:100])
    principali = [e for e in eventi if e.get("principale")]
    duelli = [e for e in eventi if e["ampiezza"] >= 2]
    estremi_opposti = [e for e in eventi if e["ampiezza"] == len(AREE) - 1]
    ciechi = [e for e in eventi if len(e["colonne_presenti"]) == 1 and e["totale"] >= 2]

    out = {
        "generato": datetime.now(timezone.utc).isoformat(),
        "finestra_ore": dati.get("finestra_ore", 24),
        "modello": MODELLO,
        "modello_raggruppa": MODELLO_RAGGRUPPA,
        "raggruppamento": MODO["raggruppamento"],
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
