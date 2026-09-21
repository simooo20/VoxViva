#!/usr/bin/env python3
"""
scala.py - la scala politica, in un posto solo.

Tutti gli altri script importano da qui, così cambiare la scala non significa
andare a caccia di stringhe in cinque file.
"""

import os

# Quanto spingere sulla versione "urlata". 1.0 = normale; alza (es. 1.6, 2.0)
# per pescare titoli sempre piu' carichi e sempre piu' verso l'estremo; abbassa
# (es. 0.6) per un confronto piu' sobrio. Si cambia senza toccare il codice con
# la variabile ILVAGLIO_INTENSITA_ALLARME.
INTENSITA_ALLARME = float(os.environ.get("ILVAGLIO_INTENSITA_ALLARME", "1.6"))

# dalla più a sinistra alla più a destra: l'ordine è quello che conta
AREE = ["SR", "CS", "C", "CD", "DR"]

# area speciale per gli aggregatori (Google News): NON sta sulla scala politica.
# Serve solo a marcare che una notizia e' nell'agenda del giorno; questi articoli
# non compaiono nelle colonne ne' nel duello, fanno da spina dorsale e basta.
AGGREGATORE = "AGG"

NOMI = {
    "SR": "sinistra radicale",
    "CS": "centro-sinistra",
    "C": "centro e agenzie",
    "CD": "centro-destra",
    "DR": "destra radicale",
    "AGG": "aggregatore",
}

# forma breve per le etichette accanto ai titoli
BREVI = {
    "SR": "sin. radicale",
    "CS": "centro-sinistra",
    "C": "centro",
    "CD": "centro-destra",
    "DR": "des. radicale",
    "AGG": "aggregatore",
}

# le tre colonne del sito: la scala è a 5, l'impaginazione a 3
COLONNE = [
    ("sinistra", "Sinistra", ["SR", "CS"]),
    ("centro", "Centro e agenzie", ["C"]),
    ("destra", "Destra", ["CD", "DR"]),
]

# a quale colonna appartiene ogni area
COLONNA_DI = {a: chiave for chiave, _, aree in COLONNE for a in aree}

# posizione numerica, serve a trovare gli estremi
INDICE = {a: i for i, a in enumerate(AREE)}


def ordina_da_sinistra(articoli):
    """Ordina gli articoli da sinistra a destra sulla scala."""
    return sorted(articoli, key=lambda a: (INDICE.get(a.get("area"), 99), a.get("pubblicato", "")))


def estremi(articoli):
    """Il titolo più a sinistra e il più a destra fra quelli passati.

    Ritorna (sinistro, destro, distanza) dove distanza è il numero di caselle
    della scala che separa i due. Se c'è un solo lato, ritorna (x, None, 0).
    """
    con_area = [a for a in articoli if a.get("area") in INDICE]
    if not con_area:
        return None, None, 0
    ordinati = ordina_da_sinistra(con_area)
    sinistro, destro = ordinati[0], ordinati[-1]
    distanza = INDICE[destro["area"]] - INDICE[sinistro["area"]]
    if distanza == 0:
        return sinistro, None, 0
    return sinistro, destro, distanza


AGENZIE = ("ansa.it", "agi.it", "adnkronos.com", "italpress.com", "lapresse.it")


# ---------------------------------------------------------------------------
# Punteggio di ALLARME del titolo.
# Serve a scegliere, in ogni colonna, il titolo piu' carico: cosi' il duello
# mette a confronto la versione piu' urlata di sinistra con quella piu' urlata
# di destra, e la differenza si vede. E' un'euristica lessicale — il passo LLM
# in cluster.py puo' raffinarla — ma cattura bene i segnali tipici.
# ---------------------------------------------------------------------------
import re as _re
import unicodedata

_PAROLE_ALLARME = {
    # emergenza / catastrofe
    "shock", "choc", "allarme", "emergenza", "caos", "dramma", "tragedia",
    "catastrofe", "disastro", "incubo", "terrore", "panico", "psicosi",
    # violenza / guerra
    "strage", "assalto", "invasione", "guerra", "raid", "bomba", "esplode",
    "esplosione", "killer", "furia", "massacro", "agguato", "blitz", "scontro",
    "rivolta", "assedio", "minaccia", "ultimatum", "sfida",
    # scandalo / morale
    "scandalo", "vergogna", "umilia", "choc", "delirio", "follia", "orrore",
    "bufera", "gogna", "complotto", "inganno", "tradimento", "ricatto",
    "ricatti", "accusa", "affondo", "attacco", "guerra", "sfregio", "veleno",
    "avvelenata", "bufala", "fake",
    # iperboli / denaro
    "faraonici", "faraonico", "clamoroso", "clamorosa", "sconvolgente",
    "sconcertante", "vergognoso", "inaudito", "inaudita", "record", "boom",
    "tracollo", "salasso", "stangata", "terribile", "choc",
    # tono da inchiesta / polemica
    "affondo", "mirino", "cortocircuito", "giallo", "retromarcia", "silenzio",
    "guerra", "resa", "fuga", "svolta",
    # escalation / catastrofismo
    "escalation", "apocalisse", "apocalittico", "tsunami", "valanga", "allerta",
    "allarmante", "paura", "devastante", "spaventoso", "drammatico", "carneficina",
    "offensiva", "controffensiva", "assedio", "insorge", "esplosiva",
    # crolli / soldi
    "crollo", "tracollo", "tonfo", "picchiata", "disfatta", "flop", "batosta",
    "salasso", "stangata", "spread", "default", "fallimento",
    # scontro politico urlato
    "schiaffo", "spallata", "showdown", "rissa", "caccia", "linciaggio",
    "spia", "dossier", "trama", "spartizione", "poltrone", "casta", "regime",
    "deriva", "assurdo", "grottesco", "indecente", "scempio", "sfacelo",
}
_MAIUSC = _re.compile(r"\b[A-ZÀ-Ü]{3,}\b")


def allarme(titolo: str) -> float:
    """Quanto e' 'urlato' un titolo. Piu' alto = piu' allarmistico/caricato."""
    if not titolo:
        return 0.0
    t = titolo.strip()
    low = t.lower()
    parole = _re.findall(r"[a-zà-ù']+", low)
    lex = sum(1 for w in parole if w in _PAROLE_ALLARME)
    esclam = low.count("!") + low.count("?")
    virgolette = t.count("«") + t.count("“") + t.count("\"") + (1 if "'" in t and '"' not in t else 0)
    maiusc = len([m for m in _MAIUSC.findall(t) if len(m) >= 4])   # REPORTOPOLI, SHOCK
    score = 2.0 * lex + 1.0 * esclam + 0.6 * virgolette + 1.5 * maiusc
    return round(INTENSITA_ALLARME * score, 2)


def _carica(a, verso_destra=None):
    """Quanto e' 'forte' un titolo per il suo lato: allarme + spinta all'estremo."""
    al = allarme(a.get("titolo", ""))
    idx = INDICE.get(a.get("area"), 2)
    if verso_destra is True:
        estremo = idx
    elif verso_destra is False:
        estremo = (len(AREE) - 1) - idx
    else:
        estremo = 0
    return al + 0.9 * INTENSITA_ALLARME * estremo


def piu_allarmante(articoli, verso_destra=None):
    """Il titolo piu' carico fra quelli dati. A parita' di allarme, sceglie
    quello piu' verso l'estremo indicato (verso_destra=True -> il piu' a destra,
    False -> il piu' a sinistra, None -> il piu' recente)."""
    if not articoli:
        return None
    return max(articoli, key=lambda a: (_carica(a, verso_destra),
                                        allarme(a.get("titolo", "")),
                                        a.get("pubblicato", "")))


# Quanto conta la DIVERGENZA (angolazioni diverse) rispetto alla sola loudness
# nella scelta della coppia sinistra/destra. Alza per titoli piu' contrapposti.
PESO_DIVERGENZA = float(os.environ.get("ILVAGLIO_PESO_DIVERGENZA", "14"))

_STOP = {"della", "delle", "dello", "degli", "dei", "come", "dopo", "prima",
         "contro", "senza", "sopra", "sotto", "tra", "fra", "per", "con",
         "che", "chi", "cosa", "quando", "dove", "perche", "sono", "essere",
         "anche", "ancora", "mentre", "questo", "questa", "quello", "quella",
         "loro", "nostro", "tutto", "tutti", "tutte", "ogni", "gli", "una",
         "uno", "nel", "nella", "sul", "sulla", "dal", "dalla", "alla", "allo"}


def _parole(titolo):
    tok = _re.findall(r"[a-zà-ù]+", (titolo or "").lower())
    return {t for t in tok if len(t) > 3 and t not in _STOP}


def divergenza(a, b):
    """0 = titoli con le stesse parole, 1 = nessuna parola in comune.
    Poche parole condivise = angolazioni diverse sullo stesso fatto."""
    pa, pb = _parole(a), _parole(b)
    if not pa or not pb:
        return 1.0
    return 1.0 - len(pa & pb) / len(pa | pb)


def coppia_divergente(sinistra, destra, k=6):
    """Sceglie la COPPIA (sinistra, destra) che stride di piu'. Prima si tengono
    i k titoli piu' carichi per lato (garanzia: entrambi forti), poi fra questi
    si prende la coppia con la MASSIMA divergenza di parole (angolazioni diverse);
    a parita', la piu' carica. Cosi' si massimizza la differenza TRA i due lati,
    non la loudness di ciascuno. Costo zero (niente modello)."""
    if not sinistra or not destra:
        return (piu_allarmante(sinistra, False), piu_allarmante(destra, True))
    sx_cand = sorted(sinistra, key=lambda a: _carica(a, False), reverse=True)[:k]
    dx_cand = sorted(destra, key=lambda a: _carica(a, True), reverse=True)[:k]
    return max(
        ((sx, dx) for sx in sx_cand for dx in dx_cand),
        key=lambda p: (divergenza(p[0].get("titolo", ""), p[1].get("titolo", "")),
                       _carica(p[0], False) + _carica(p[1], True)),
    )


_STOP_TIT = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "del", "dei",
    "della", "delle", "dello", "degli", "a", "al", "ai", "alla", "alle", "da",
    "dal", "in", "nel", "nella", "con", "su", "sul", "per", "tra", "fra", "e",
    "ed", "o", "che", "chi", "non", "si", "ha", "ho", "hai", "come", "piu",
    "meno", "ma", "se", "sono", "dopo", "prima", "ancora", "anche", "cosi",
}


def _parole_tit(titolo):
    """Parole-contenuto di un titolo, per misurare quanto due titoli si somigliano."""
    t = unicodedata.normalize("NFKD", (titolo or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = _re.sub(r"[^a-z0-9 ]", " ", t)
    return {w for w in t.split() if len(w) > 3 and w not in _STOP_TIT}


def _rappresentativita(a, gruppo):
    """Quanto il titolo di `a` somiglia agli ALTRI titoli del gruppo (Jaccard medio).
    Alto = inquadratura tipica del centro; basso = outlier (la mosca bianca)."""
    mie = _parole_tit(a.get("titolo", ""))
    if not mie:
        return 0.0
    punteggi = []
    for b in gruppo:
        if b is a:
            continue
        sue = _parole_tit(b.get("titolo", ""))
        if not sue:
            continue
        unione = mie | sue
        punteggi.append(len(mie & sue) / len(unione) if unione else 0.0)
    return sum(punteggi) / len(punteggi) if punteggi else 0.0


def riferimento_centro(articoli):
    """Il titolo di riferimento in mezzo al duello.

    Si preferisce un lancio d'agenzia (la versione più asciutta). Tra i
    candidati NON si prende il più corto — la brevità premia gli outlier — ma il
    più RAPPRESENTATIVO: quello la cui inquadratura somiglia di più agli altri
    titoli del centro. Così la colonna «Centro» mostra il taglio che il centro,
    in maggioranza, ha dato alla notizia, non l'eccezione capitata a essere
    breve. La rappresentatività si misura su TUTTI i titoli di centro; poi, a
    parità sostanziale, si mostra un'agenzia se c'è (più neutra). Un editoriale
    di centro non è un riferimento neutro e non va spacciato per tale.
    """
    centrali = [a for a in articoli if a.get("area") == "C"]
    if not centrali:
        return None

    if len(centrali) <= 2:                      # troppo pochi per un outlier: resta l'asciutto
        agenzie = [a for a in centrali if a.get("dominio", "") in AGENZIE]
        pool = agenzie or centrali
        scelta = min(pool, key=lambda a: len(a.get("titolo", "")))
        return dict(scelta, agenzia=bool(agenzie))

    rappr = {id(a): _rappresentativita(a, centrali) for a in centrali}
    agenzie = [a for a in centrali if a.get("dominio", "") in AGENZIE]
    if agenzie:
        scelta = max(agenzie, key=lambda a: (rappr[id(a)], -len(a.get("titolo", ""))))
        return dict(scelta, agenzia=True)
    scelta = max(centrali, key=lambda a: (rappr[id(a)], -len(a.get("titolo", ""))))
    return dict(scelta, agenzia=False)
