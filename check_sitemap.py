#!/usr/bin/env python3
"""
check_sitemap.py - Le testate bloccate dagli anti-bot sull'RSS si possono
recuperare dalla loro sitemap?

Per ogni dominio la sonda risponde a due domande, le uniche che contano:
  1) la sitemap e' RAGGIUNGIBILE dal runner, o e' bloccata come l'RSS? (HTTP)
  2) contiene il TITOLO (news sitemap con <news:title>), o solo i link?

Scoperta automatica via robots.txt (la riga "Sitemap:"), con qualche URL di
riserva. Legge solo XML pubblici, niente API, niente dipendenze extra.

    python check_sitemap.py                      # domini presi da sources.json
    python check_sitemap.py corriere.it ilgiornale.it adnkronos.com
    python check_sitemap.py --ore 12 corriere.it

NB: va lanciata DOVE gira la pipeline (il runner GitHub, scheda Actions ->
"Run workflow" su un job che la invoca, oppure in locale). Il blocco dipende
dall'IP: il risultato dal tuo PC puo' essere diverso da quello del runner.
"""
import argparse
import gzip
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

BASE = Path(__file__).resolve().parent
UA = ("Mozilla/5.0 (compatible; VoxVivaBot/1.0; +https://simooo20.github.io/VoxViva/)")
RISERVE = ["/sitemap-news.xml", "/news-sitemap.xml", "/sitemap_news.xml",
           "/sitemap.xml", "/sitemap_index.xml"]


def scarica(url, timeout=15):
    """Ritorna (stato, byte) dove stato e' il codice HTTP o una stringa d'errore."""
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/xml,text/xml,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dati = r.read()
            if url.endswith(".gz") or r.headers.get("Content-Encoding") == "gzip":
                try:
                    dati = gzip.decompress(dati)
                except Exception:
                    pass
            return r.status, dati
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except Exception as exc:
        return str(exc)[:60], b""


def locale(tag):
    """Nome del tag senza namespace: '{...}url' -> 'url'."""
    return tag.rsplit("}", 1)[-1].lower()


def sitemap_da_robots(dominio):
    """Legge robots.txt e ritorna (stato_http, [url di sitemap dichiarate])."""
    stato, dati = scarica("https://%s/robots.txt" % dominio)
    urls = []
    if isinstance(stato, int) and stato == 200 and dati:
        for riga in dati.decode("utf-8", "replace").splitlines():
            m = re.match(r"\s*sitemap\s*:\s*(\S+)", riga, re.I)
            if m:
                urls.append(m.group(1).strip())
    return stato, urls


def analizza_sitemap(url, limite_ore, visti=None, profondita=0):
    """Ritorna un dizionario riassuntivo: raggiungibile, tipo, quanti titoli
    recenti, esempi. Segue un livello di sitemap-index."""
    if visti is None:
        visti = set()
    if url in visti or profondita > 2:
        return None
    visti.add(url)
    stato, dati = scarica(url)
    ris = {"url": url, "stato": stato, "titoli_recenti": 0, "voci": 0,
           "news": False, "esempi": []}
    if not (isinstance(stato, int) and stato == 200 and dati):
        return ris
    try:
        radice = ET.fromstring(dati)
    except Exception as exc:
        ris["stato"] = "XML illeggibile: %s" % str(exc)[:40]
        return ris

    tag = locale(radice.tag)
    soglia = datetime.now(timezone.utc) - timedelta(hours=limite_ore)

    if tag == "sitemapindex":
        # indice: scendo nelle sotto-sitemap, dando la precedenza a quelle "news"
        figli = []
        for sm in radice:
            loc = next((c.text for c in sm if locale(c.tag) == "loc" and c.text), None)
            if loc:
                figli.append(loc.strip())
        figli.sort(key=lambda u: (0 if "news" in u.lower() else 1))
        for loc in figli[:4]:
            sub = analizza_sitemap(loc, limite_ore, visti, profondita + 1)
            if sub:
                ris["voci"] += sub["voci"]
                ris["titoli_recenti"] += sub["titoli_recenti"]
                ris["news"] = ris["news"] or sub["news"]
                for e in sub["esempi"]:
                    if len(ris["esempi"]) < 3:
                        ris["esempi"].append(e)
        return ris

    # sitemap normale (urlset): conto le voci e cerco titolo + data
    for u in radice:
        if locale(u.tag) != "url":
            continue
        ris["voci"] += 1
        titolo = data = None
        for c in u.iter():
            lc = locale(c.tag)
            if lc == "title" and c.text:            # <news:title>
                titolo = c.text.strip()
                ris["news"] = True
            elif lc == "publication_date" and c.text:  # <news:publication_date>
                data = c.text.strip()
            elif lc == "lastmod" and c.text and data is None:
                data = c.text.strip()
        recente = True
        if data:
            try:
                d = datetime.fromisoformat(data.replace("Z", "+00:00"))
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                recente = d >= soglia
            except Exception:
                recente = True
        if titolo and recente:
            ris["titoli_recenti"] += 1
            if len(ris["esempi"]) < 3:
                ris["esempi"].append(titolo)
    return ris


def domini_da_sources():
    f = BASE / "sources.json"
    if not f.exists():
        return []
    dati = json.loads(f.read_text(encoding="utf-8"))
    fonti = dati.get("fonti") or dati.get("sources") or dati
    domini = []
    for s in (fonti if isinstance(fonti, list) else []):
        url = s.get("url") or s.get("feed") or ""
        m = re.match(r"https?://([^/]+)", url)
        if m:
            d = m.group(1).replace("www.", "")
            if d not in domini:
                domini.append(d)
    return domini


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("domini", nargs="*", help="es. corriere.it ilgiornale.it")
    ap.add_argument("--ore", type=int, default=24, help="finestra per i titoli recenti")
    args = ap.parse_args()

    domini = args.domini or domini_da_sources()
    if not domini:
        sys.exit("Nessun dominio. Passali a mano o metti sources.json accanto allo script.")

    print("Sonda sitemap — finestra %d ore\n" % args.ore + "=" * 60)
    for dom in domini:
        dom = dom.replace("https://", "").replace("http://", "").strip("/")
        stato_r, dichiarate = sitemap_da_robots(dom)
        candidate = dichiarate or ["https://%s%s" % (dom, p) for p in RISERVE]
        migliore = None
        for url in candidate[:6]:
            r = analizza_sitemap(url, args.ore)
            if r and isinstance(r["stato"], int) and r["stato"] == 200:
                migliore = r
                if r["news"] and r["titoli_recenti"]:
                    break            # trovata quella buona: basta
            time.sleep(0.5)

        print("\n%s" % dom)
        print("  robots.txt: %s%s" % (
            stato_r, "" if dichiarate else "  (nessuna sitemap dichiarata, uso le riserve)"))
        if not migliore:
            print("  sitemap: IRRAGGIUNGIBILE (probabile blocco come l'RSS)")
            continue
        if not (isinstance(migliore["stato"], int) and migliore["stato"] == 200):
            print("  sitemap: %s -> %s" % (migliore["url"], migliore["stato"]))
            continue
        if migliore["news"] and migliore["titoli_recenti"]:
            print("  RECUPERABILE: news sitemap con titoli — %d nelle ultime %d h"
                  % (migliore["titoli_recenti"], args.ore))
            for e in migliore["esempi"]:
                print("      · %s" % e[:90])
        elif migliore["voci"]:
            print("  sitemap raggiungibile ma SENZA titoli (%d URL): solo link, "
                  "non serve per l'urlato" % migliore["voci"])
        else:
            print("  sitemap raggiungibile ma vuota/non standard: %s" % migliore["url"])


if __name__ == "__main__":
    main()
