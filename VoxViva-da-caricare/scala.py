#!/usr/bin/env python3
"""
scala.py - la scala politica, in un posto solo.

Tutti gli altri script importano da qui, così cambiare la scala non significa
andare a caccia di stringhe in cinque file.
"""

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
    score = 1.5 * lex + 0.8 * esclam + 0.5 * virgolette + 1.2 * maiusc
    return round(score, 2)


def piu_allarmante(articoli, verso_destra=None):
    """Il titolo piu' carico fra quelli dati. A parita' di allarme, sceglie
    quello piu' verso l'estremo indicato (verso_destra=True -> il piu' a destra,
    False -> il piu' a sinistra, None -> il piu' recente)."""
    if not articoli:
        return None
    def chiave(a):
        al = allarme(a.get("titolo", ""))
        if verso_destra is True:
            spinta = INDICE.get(a.get("area"), 0)
        elif verso_destra is False:
            spinta = -INDICE.get(a.get("area"), 0)
        else:
            spinta = 0
        return (al, spinta, a.get("pubblicato", ""))
    return max(articoli, key=chiave)


def riferimento_centro(articoli):
    """Il titolo di riferimento in mezzo al duello.

    Si preferisce un lancio d'agenzia, che è la versione più asciutta
    disponibile. Se nessuna agenzia ha battuto la notizia si prende un titolo
    di centro, ma va detto al lettore che non è un lancio: sul campo "agenzia"
    il sito cambia l'etichetta della colonna centrale. Un editoriale di centro
    non è un riferimento neutro e non va spacciato per tale.
    """
    centrali = [a for a in articoli if a.get("area") == "C"]
    if not centrali:
        return None
    agenzie = [a for a in centrali if a.get("dominio", "") in AGENZIE]
    if agenzie:
        scelta = min(agenzie, key=lambda a: len(a.get("titolo", "")))
        return dict(scelta, agenzia=True)
    scelta = min(centrali, key=lambda a: len(a.get("titolo", "")))
    return dict(scelta, agenzia=False)
