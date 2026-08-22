#!/usr/bin/env python3
"""
ingest.py - passo 1 di 3.

Legge tutti i feed di sources.json e produce data/articles.json con gli
articoli delle ultime N ore, deduplicati e con un id stabile.

    python ingest.py                # ultime 24 ore
    python ingest.py --ore 12       # finestra piu' stretta
"""
import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import gzip
import urllib.request
import feedparser

from scala import AREE

BASE = Path(__file__).resolve().parent
SOURCES = BASE / "sources.json"
OUT = BASE / "data" / "articles.json"

# Molte testate bloccano gli user-agent "robot" sconosciuti (403 o feed vuoto)
# pur avendo un feed valido e aggiornato. Ci presentiamo come un browser reale,
# come fa qualunque lettore di feed: e' l'uso per cui i feed RSS esistono.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# Non basta lo User-Agent: molti siti dietro filtri anti-bot lasciano passare
# solo richieste con l'intero corredo di header di un browser (lingua, tipi
# accettati, ecc.). Proviamo prima cosi'; se fallisce, feedparser da solo.
_HEADERS_BROWSER = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def scarica_feed(url):
    """Scarica il feed con header da browser vero; ritorna i bytes o None."""
    try:
        req = urllib.request.Request(url, headers=_HEADERS_BROWSER)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
            if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                data = gzip.decompress(data)
            return data
    except Exception:
        return None


def immagine_di(e):
    """URL di un'immagine dall'entry del feed (media, enclosure o <img> nel testo).
    Serve per l'apertura in stile AllSides; stringa vuota se non c'e'."""
    for chiave in ("media_content", "media_thumbnail"):
        for m in (e.get(chiave) or []):
            u = m.get("url") or ""
            if u.startswith("http"):
                return u
    for enc in (e.get("enclosures") or []):
        u = enc.get("href") or enc.get("url") or ""
        tipo = (enc.get("type") or "").lower()
        if u.startswith("http") and ("image" in tipo or u.lower().split("?")[0].endswith(
                (".jpg", ".jpeg", ".png", ".webp", ".gif"))):
            return u
    testo = e.get("summary") or ""
    if not testo and e.get("content"):
        try:
            testo = e["content"][0].get("value", "")
        except Exception:
            testo = ""
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', testo, re.I)
    if m and m.group(1).startswith("http"):
        return m.group(1)
    return ""

# parametri di tracciamento che sporcano gli url e rompono la deduplica
TRACKING = re.compile(r"^(utm_|fbclid|gclid|ref|refresh_ce|__twitter|mc_|igshid|amp)", re.I)

# Rumore di listino: la topnews ANSA alle 8 del mattino e' meta' tick di borsa
# ("prezzo dell'oro a 4.443 dollari l'oncia", "euro a 1,1572 dollari", "Tokyo -0,56%").
# Non sono notizie di cui confrontare l'inquadratura: si scartano. Non tocca gli
# articoli di economia veri, che non hanno questa forma numerica secca.
MERCATO = re.compile(
    r"(prezzo dell'oro|dollari l'oncia|al barile|\bwti\b|\bbrent\b|\bttf\b|"
    r"\bspread\b|piazza affari|\bftse\b|\bnasdaq\b|dow jones|"
    r"^borsa[:,]|^petrolio|^il petrolio|^l'euro|^euro a|^il gas|^oro |"
    r"apertura in (rialzo|ribasso)|chiude in (rialzo|ribasso)|"
    r"aprono? (in )?(rialzo|ribasso|calo)|\bl'oncia\b)",
    re.I,
)


def pulisci_url(url: str) -> str:
    """Toglie i parametri di tracciamento e normalizza l'host, per deduplicare bene."""
    try:
        p = urlparse(url)
        host = p.netloc.lower()
        for pref in ("www.", "m.", "mobile.", "amp."):
            if host.startswith(pref):
                host = host[len(pref):]
        query = "&".join(
            q for q in p.query.split("&")
            if q and not TRACKING.match(q.split("=")[0])
        )
        return urlunparse((p.scheme or "https", host, p.path.rstrip("/"), "", query, ""))
    except Exception:
        return url


def host_di(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower()
        for pref in ("www.", "m.", "mobile.", "amp."):
            if h.startswith(pref):
                h = h[len(pref):]
        return h
    except Exception:
        return ""


def chiave_titolo(titolo: str) -> str:
    """Firma del titolo per beccare lo stesso pezzo ripubblicato con url diverso."""
    t = unicodedata.normalize("NFKD", titolo.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return " ".join(sorted(t.split()))[:200]


def pulisci_titolo(titolo: str) -> str:
    """Toglie i prefissi editoriali che confondono il raggruppamento.

    ANSA usa '++ ... ++' per le ultim'ora, il Corriere mette occhielli in
    MAIUSCOLO davanti al titolo. Il testo resta quello della testata: si
    rimuove solo la decorazione, non si riscrive niente.
    """
    t = " ".join((titolo or "").split())
    t = re.sub(r"^\+\+\s*|\s*\+\+$", "", t).strip()
    # occhiello tutto maiuscolo di almeno due parole seguito dal titolo vero
    m = re.match(r"^((?:[A-ZÀ-Ü'’\.]{2,}\s+){1,6})(?=[A-ZÀ-Ü][a-zà-ü])", t)
    if m and len(m.group(1)) > 8:
        t = t[m.end():].strip()
    return t


def data_di(entry):
    for key in ("published_parsed", "updated_parsed"):
        tup = entry.get(key)
        if tup:
            try:
                return datetime(*tup[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ore", type=int, default=24, help="finestra temporale in ore (default 24)")
    ap.add_argument("--max-per-feed", type=int, default=40)
    args = ap.parse_args()

    cfg = json.loads(SOURCES.read_text(encoding="utf-8"))
    sources = cfg["sources"]
    taglio = datetime.now(timezone.utc) - timedelta(hours=args.ore)

    articoli = []
    visti_url, visti_titolo = set(), set()
    report = []
    scartati_mercato = 0

    for src in sources:
        nome = src.get("etichetta") or src["name"]   # ANSA cronaca -> "ANSA"
        area, url_feed = src["area"], src.get("rss") or ""
        primaria = bool(src.get("primaria"))         # ANSA topnews -> spina dorsale
        if not url_feed:
            report.append({"fonte": nome, "area": area, "presi": 0, "nota": "nessun feed configurato"})
            continue
        try:
            dati_feed = scarica_feed(url_feed)
            fp = feedparser.parse(dati_feed) if dati_feed else feedparser.parse(url_feed, agent=UA)
        except Exception as exc:
            report.append({"fonte": nome, "area": area, "presi": 0, "nota": "errore: %s" % str(exc)[:80]})
            continue

        presi = 0
        scartati_vecchi = 0
        for pos, e in enumerate((fp.entries or [])[: args.max_per_feed]):
            titolo = pulisci_titolo(e.get("title") or "")
            link = e.get("link") or ""
            if not titolo or not link or len(titolo) < 15:
                continue

            if MERCATO.search(titolo):
                scartati_mercato += 1
                continue

            dt = data_di(e)
            if dt is None:
                continue
            if dt < taglio:
                scartati_vecchi += 1
                continue

            url_norm = pulisci_url(link)
            if url_norm in visti_url:
                continue
            ktit = chiave_titolo(titolo)
            if ktit in visti_titolo:
                continue
            visti_url.add(url_norm)
            visti_titolo.add(ktit)

            articoli.append({
                "id": hashlib.sha1(url_norm.encode()).hexdigest()[:10],
                "titolo": titolo,
                "url": link,
                "pubblicato": dt.isoformat(),
                "fonte": nome,
                "feed": src["name"],            # il feed preciso: "ANSA topnews" vs "ANSA cronaca"
                "dominio": host_di(link) or src["domain"],
                "area": area,
                "primaria": primaria,           # viene da un feed che definisce l'agenda del giorno
                "ordine_feed": pos,             # posizione nel feed = priorita' redazionale dell'agenzia
                "immagine": immagine_di(e),     # per l'apertura stile AllSides
            })
            presi += 1

        nota = ""
        if presi == 0:
            nota = "feed vivo ma niente nelle ultime %dh" % args.ore if fp.entries else "FEED DA CONTROLLARE"
        report.append({"fonte": nome, "area": area, "presi": presi, "nota": nota})

    articoli.sort(key=lambda a: a["pubblicato"], reverse=True)

    conteggi = {x: sum(1 for a in articoli if a["area"] == x) for x in AREE}
    out = {
        "generato": datetime.now(timezone.utc).isoformat(),
        "finestra_ore": args.ore,
        "totale": len(articoli),
        "per_area": conteggi,
        "report_fonti": report,
        "articoli": articoli,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    primari = sum(1 for a in articoli if a.get("primaria"))
    print("Articoli raccolti nelle ultime %dh: %d" % (args.ore, len(articoli)))
    print("  " + "   ".join("%s %d" % (x, conteggi[x]) for x in AREE))
    print("  di cui dalla spina dorsale (topnews agenzia): %d" % primari)
    if scartati_mercato:
        print("  tick di mercato scartati (oro, petrolio, borsa...): %d" % scartati_mercato)
    muti = [r["fonte"] for r in report if r["presi"] == 0]
    if muti:
        print("  fonti a zero: %s" % ", ".join(muti))
        print("  (lancia check_feeds.py per capire quali sono rotte davvero)")
    print("Salvato in %s" % OUT)


if __name__ == "__main__":
    main()
