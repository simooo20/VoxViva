#!/usr/bin/env python3
"""
gnews.py - I raggruppamenti di Google News come punto di partenza.

Google News raggruppa gia' le testate per notizia: ogni voce dei suoi feed RSS
contiene, nella description, fino a 5 testate che raccontano lo STESSO fatto
(il "nucleo"). Qui leggiamo le notizie principali e le sezioni Italia, Mondo,
Economia, Politica, e per ognuna teniamo titolo, ora e nucleo.

cluster.py usa queste "storie" come ossatura: Google decide quali sono le
notizie e chi le racconta; il modello deve solo aggiungere i titoli delle
nostre testate che raccontano quel fatto. Se Google non risponde, cluster.py
torna da solo al raggruppamento completo di prima (nessun sito vuoto).

Verificato il 26/9/2026: top 34 notizie, sezioni ~55-65 notizie l'una, 4-5
testate per notizia. La pagina "copertura completa" (/stories/...) NON ha un
feed: non la usiamo.
"""
import difflib
import html
import re
import unicodedata
import urllib.request
from email.utils import parsedate_to_datetime
from datetime import timezone
from urllib.parse import urlparse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
LINGUA = "hl=it&gl=IT&ceid=IT:it"
FEED = [
    ("principali", "https://news.google.com/rss?" + LINGUA),
    ("italia", "https://news.google.com/rss/headlines/section/topic/NATION?" + LINGUA),
    ("politica", "https://news.google.com/rss/headlines/section/topic/POLITICS?" + LINGUA),
    ("mondo", "https://news.google.com/rss/headlines/section/topic/WORLD?" + LINGUA),
    ("economia", "https://news.google.com/rss/headlines/section/topic/BUSINESS?" + LINGUA),
]

# Come Google chiama alcune testate -> la nostra etichetta in sources.json.
# (chiavi gia' normalizzate con norm_nome)
ALIAS = {
    "corrieretorino": "Corriere della Sera", "corrieremilano": "Corriere della Sera",
    "corrieredelveneto": "Corriere della Sera", "corrierefiorentino": "Corriere della Sera",
    "corrieredibologna": "Corriere della Sera", "corrierebari": "Corriere della Sera",
    "corrieredelmezzogiorno": "Corriere della Sera",
    "restodelcarlino": "QN Quotidiano Nazionale", "giorno": "QN Quotidiano Nazionale",
    "quotidianonazionale": "QN Quotidiano Nazionale",
    "la7": "TgLa7", "tgla7": "TgLa7",
    "agenziadire": "Dire",
    "euronews": "Euronews Italia",
    "nuovabussolaquotidiana": "La Nuova Bussola Q.",
    "opinionedelleliberta": "L'Opinione",
}


def norm_nome(s):
    """'la Repubblica' / 'La Repubblica' / 'Il Sole 24 ORE' -> 'repubblica', 'sole24ore'."""
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"^(www\.)", "", s.strip())
    s = re.sub(r"\.(it|com|net|news|online|info|eu)$", "", s)
    s = re.sub(r"^(il|la|lo|l'|l’|i|gli|le)\s+", "", s)
    s = re.sub(r"^l['’]", "", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def dominio(u):
    h = urlparse(u if "//" in (u or "") else "https://" + (u or "")).netloc.lower()
    for p in ("www.", "m.", "amp."):
        if h.startswith(p):
            h = h[len(p):]
    return h


class Testate:
    """Riconosce le testate di Google (per nome o dominio) -> (etichetta, area)."""

    def __init__(self, sources):
        self.per_dom, self.per_nome, self.per_etichetta = {}, {}, {}
        for s in sources:
            area = s.get("area")
            if area in (None, "AGG"):
                continue
            nome = s.get("etichetta") or s["name"]
            v = (nome, area)
            self.per_etichetta.setdefault(nome, v)
            self.per_dom.setdefault(dominio(s["domain"]), v)
            self.per_nome.setdefault(norm_nome(nome), v)
            lab = dominio(s["domain"]).split(".")[0]
            self.per_nome.setdefault(norm_nome(lab), v)
            self.per_nome.setdefault(norm_nome(re.sub(r"^(il|la)(?=.{4,})", "", lab)), v)

    def riconosci(self, nome, url=""):
        # 1) dominio (anche sottodomini: bologna.repubblica.it, tgcom24.mediaset.it)
        for cand in (url, nome if "." in (nome or "") else ""):
            d = dominio(cand) if cand else ""
            if not d:
                continue
            if d in self.per_dom:
                return self.per_dom[d]
            for k, v in self.per_dom.items():
                if d.endswith("." + k):
                    return v
        # 2) alias e nome normalizzato
        n = norm_nome(nome)
        if n in ALIAS:
            return self.per_etichetta.get(ALIAS[n])
        if n == "libero":          # e' il portale libero.it, non Libero Quotidiano
            return None
        return self.per_nome.get(n)


def _scarica(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "ignore")


def _data(s):
    try:
        return parsedate_to_datetime(s).astimezone(timezone.utc)
    except Exception:
        return None


def _via_suffisso(titolo):
    """Google aggiunge ' - Testata' in coda al titolo della voce: lo togliamo."""
    return re.sub(r"\s+-\s+[^-]{2,60}$", "", titolo or "").strip()


def storie(taglio, log=print):
    """Ritorna le storie di Google: [{titolo, sezione, ordine, pubblicato,
    nucleo: [{titolo, fonte_google}]}]. Deduplica le storie ripetute fra le
    sezioni (stesso titolo di testa). Nessuna eccezione verso fuori: se un
    feed non risponde si salta."""
    out, visti = [], set()
    for sezione, url in FEED:
        try:
            xml = _scarica(url)
        except Exception as exc:
            log("  Google News %s: non raggiungibile (%s)" % (sezione, str(exc)[:60]))
            continue
        voci = xml.split("<item>")[1:]
        prese = 0
        for pos, v in enumerate(voci):
            m = re.search(r"<title>(.*?)</title>", v, re.S)
            titolo = _via_suffisso(html.unescape(m.group(1))) if m else ""
            dt = _data((re.search(r"<pubDate>(.*?)</pubDate>", v) or [None, ""])[1])
            if not titolo or dt is None or dt < taglio:
                continue
            desc = html.unescape((re.search(r"<description>(.*?)</description>", v, re.S) or [None, ""])[1])
            nucleo = []
            for link, t, f in re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>(?:&nbsp;|\s|\u00a0)*<font[^>]*>(.*?)</font>', desc, re.S):
                nucleo.append({"titolo": html.unescape(re.sub("<[^>]+>", "", t)).strip(),
                               "fonte_google": html.unescape(f).strip(), "link": link})
            # la voce di testa: e' il primo del nucleo, e l'unico di cui
            # conosciamo l'ora esatta (pubDate) e il dominio (<source url>)
            src = re.search(r'<source url="([^"]*)">(.*?)</source>', v)
            testa = {"titolo": titolo, "fonte_google": html.unescape(src.group(2)) if src else "",
                     "url_fonte": src.group(1) if src else "",
                     "link": (re.search(r"<link>(.*?)</link>", v) or [None, ""])[1].strip()}
            if not nucleo:
                nucleo = [testa]
            else:
                nucleo[0]["url_fonte"] = testa["url_fonte"]
            chiave = re.sub(r"\W+", " ", titolo.lower()).strip()
            if chiave in visti:
                continue
            visti.add(chiave)
            out.append({"titolo": titolo, "sezione": sezione, "ordine": pos,
                        "pubblicato": dt.isoformat(), "nucleo": nucleo})
            prese += 1
        log("  Google News %s: %d notizie" % (sezione, prese))
    return out


def _norm_titolo(t):
    t = unicodedata.normalize("NFKD", (t or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", " ", t).split()


def stesso_titolo(a, b):
    """Lo stesso pezzo visto da Google e dal nostro feed (piccole differenze)."""
    x, y = " ".join(_norm_titolo(a)), " ".join(_norm_titolo(b))
    if not x or not y:
        return False
    if x == y or x.startswith(y[:45]) or y.startswith(x[:45]):
        return True
    return difflib.SequenceMatcher(None, x, y).ratio() >= 0.78
