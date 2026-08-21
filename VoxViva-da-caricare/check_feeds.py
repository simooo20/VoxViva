#!/usr/bin/env python3
"""
check_feeds.py - il "dottore dei feed".

Controlla ogni feed in sources.json e dice se e' vivo, se e' fermo da giorni,
e quanti articoli ha nelle ultime 24h. Da lanciare dal TUO pc: alcuni feed
bloccano gli IP dei datacenter ma funzionano da una connessione domestica.

    python check_feeds.py

Aggiorna sources.json col campo "stato" solo se lanci con --scrivi.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser

from scala import AREE, NOMI

BASE = Path(__file__).resolve().parent
SOURCES = BASE / "sources.json"

UA = "IlVaglio/1.0 (aggregatore di titoli non commerciale; +mailto:tuo@indirizzo.it)"


def parse_dt(entry):
    for key in ("published_parsed", "updated_parsed"):
        tup = entry.get(key)
        if tup:
            try:
                return datetime(*tup[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def check(src, timeout=20):
    url = src.get("rss") or ""
    out = {"name": src["name"], "area": src["area"], "url": url}
    if not url:
        out.update(stato="SENZA_URL", dettaglio="nessun feed configurato", n=0, n24=0)
        return out
    try:
        fp = feedparser.parse(url, agent=UA)
    except Exception as exc:
        out.update(stato="ERRORE", dettaglio=str(exc)[:120], n=0, n24=0)
        return out

    status = getattr(fp, "status", None)
    entries = fp.entries or []

    if status and status >= 400:
        out.update(stato="HTTP_%s" % status, dettaglio="il feed risponde errore", n=0, n24=0)
        return out
    if not entries:
        out.update(stato="VUOTO", dettaglio=getattr(fp, "bozo_exception", "nessun item"), n=0, n24=0)
        return out

    now = datetime.now(timezone.utc)
    dates = [d for d in (parse_dt(e) for e in entries) if d]
    n24 = sum(1 for d in dates if d > now - timedelta(hours=24))
    piu_recente = max(dates) if dates else None

    if piu_recente is None:
        out.update(stato="SENZA_DATE", dettaglio="gli item non hanno data leggibile", n=len(entries), n24=0)
    elif piu_recente < now - timedelta(days=7):
        eta = (now - piu_recente).days
        out.update(stato="CONGELATO", dettaglio="ultimo articolo %s giorni fa" % eta, n=len(entries), n24=0)
    elif n24 == 0:
        out.update(stato="LENTO", dettaglio="niente nelle ultime 24h", n=len(entries), n24=0)
    else:
        out.update(stato="OK", dettaglio="", n=len(entries), n24=n24)

    out["ultimo"] = piu_recente.isoformat() if piu_recente else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scrivi", action="store_true", help="aggiorna il campo stato in sources.json")
    args = ap.parse_args()

    cfg = json.loads(SOURCES.read_text(encoding="utf-8"))
    sources = cfg["sources"]

    print("Controllo %d feed. Ci vuole un minuto.\n" % len(sources))
    results = []
    for src in sources:
        r = check(src)
        results.append(r)
        icona = {"OK": "OK  ", "LENTO": "slow", "CONGELATO": "FERMO", "VUOTO": "VUOTO"}.get(r["stato"], "KO  ")
        print("%-3s %-6s %-24s %3d item, %2d nelle 24h  %s"
              % (r["area"], icona, r["name"][:24], r["n"], r["n24"], r["dettaglio"]))

    print()
    for area in AREE:
        etichetta = NOMI[area]
        gruppo = [r for r in results if r["area"] == area]
        vivi = [r for r in gruppo if r["stato"] == "OK"]
        art = sum(r["n24"] for r in vivi)
        print("%-18s %d/%d feed vivi, %d articoli nelle 24h" % (etichetta, len(vivi), len(gruppo), art))

    rotti = [r for r in results if r["stato"] not in ("OK", "LENTO")]
    if rotti:
        print("\nDa sistemare (%d):" % len(rotti))
        for r in rotti:
            print("  %s -> %s (%s)" % (r["name"], r["stato"], r["url"]))
        print("\nPer trovare l'url giusto: apri la homepage della testata e cerca 'RSS' nel footer,")
        print("oppure guarda nel sorgente della pagina il tag <link type=\"application/rss+xml\">.")

    if args.scrivi:
        per_nome = {r["name"]: r for r in results}
        for src in sources:
            r = per_nome.get(src["name"])
            if r:
                src["stato"] = r["stato"].lower()
        SOURCES.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\nsources.json aggiornato.")

    # exit code 1 se un lato dello spettro e' rimasto senza feed vivi
    vuote = [NOMI[a] for a in AREE
             if not any(r["area"] == a and r["stato"] == "OK" for r in results)]
    if vuote:
        print("\nATTENZIONE: nessun feed vivo per: %s." % ", ".join(vuote))
        print("Il confronto fra estremi non funziona se manca un capo della scala.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
