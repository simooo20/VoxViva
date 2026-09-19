#!/usr/bin/env python3
"""
genera_social.py - dai confronti pubblicati alle card social, in un CSV.

Legge data/events.json, tiene SOLO i confronti a divergenza alta (quelli che
valgono un post), e per ognuno fa scrivere a Haiku la sintesi in corsivo e i
tre estratti "..." (brevi ma di senso compiuto, ognuno col tono del suo lato).
L'analisi "come cambia il racconto" NON si rigenera: e' gia' in events.json
(campo `nota`), la riusiamo. La fonte esce accanto all'estratto.

Il risultato e' web/social.csv, una riga per card, pronto per il Bulk Create
di Canva: colleghi le colonne ai segnaposto del template e sforni tutte le card.

    python genera_social.py                 # soglia e numero da variabili/default
    python genera_social.py --soglia 0.6 --max 4
    python genera_social.py --secco         # niente riscrittura: estratti = titoli veri

Manopole (anche da Settings > Variables, senza toccare il codice):
    ILVAGLIO_SOGLIA_DIVERGENZA   quanto devono divergere i due lati (default 0.65)
    ILVAGLIO_MAX_SOCIAL          quante card al massimo per giro (default 2)
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path

from scala import coppia_divergente, divergenza
import cluster  # riusa client, chiamata e modello Haiku della pipeline

BASE = Path(__file__).resolve().parent
IN = BASE / "data" / "events.json"
OUT = BASE / "web" / "social.csv"

SOGLIA = float(os.environ.get("ILVAGLIO_SOGLIA_DIVERGENZA", "0.65"))
MAX_CARD = int(os.environ.get("ILVAGLIO_MAX_SOCIAL", "2"))

SCHEMA_SOCIAL = {
    "name": "registra_card",
    "description": "Scrive i testi di una card social a partire da un confronto.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sintesi": {"type": "string",
                        "description": "2-3 frasi brevi separate da ';', ognuna dice cosa sottolinea un lato. Neutra, in terza persona. Nomina le testate."},
            "sx_estratto": {"type": "string",
                            "description": "Estratto social del titolo di SINISTRA: frase secca e d'impatto, max ~12 parole, col tono di quel lato. NON iniziare con puntini di sospensione."},
            "centro_estratto": {"type": "string",
                                "description": "Estratto social del titolo di CENTRO: frase secca, asciutta, max ~12 parole. NON iniziare con puntini di sospensione."},
            "dx_estratto": {"type": "string",
                            "description": "Estratto social del titolo di DESTRA: frase secca e d'impatto, max ~12 parole, col tono di quel lato. NON iniziare con puntini di sospensione."},
            "caption": {"type": "string",
                        "description": "Didascalia del post: 2-3 frasi, neutra, chiude con un gancio che invita a leggere l'analisi. Niente hashtag."},
        },
        "required": ["sintesi", "sx_estratto", "centro_estratto", "dx_estratto", "caption"],
    },
}

PROMPT = """Sei l'editor social di una rassegna stampa che confronta come le testate italiane titolano LA STESSA notizia da sinistra, centro e destra.

Notizia (titolo neutro nostro): {neutro}

I titoli VERI, come pubblicati:
- SINISTRA ({sx_fonte}): {sx_titolo}
- CENTRO ({c_fonte}): {c_titolo}
- DESTRA ({dx_fonte}): {dx_titolo}

Scrivi i testi per la card (chiama registra_card):
- Gli ESTRATTI sono la versione social del titolo di ogni lato: una frase secca e d'impatto, col TONO di quel lato, di senso compiuto (non tronconi). NON iniziano con puntini di sospensione.
- Non inventare fatti: usa solo cio' che c'e' nel titolo di quel lato.
- La SINTESI dice in modo neutro cosa sottolinea ciascun lato, nominando le testate.
- La CAPTION e' per Instagram: neutra, incuriosisce, chiude invitando a leggere l'analisi. Niente hashtag, niente maiuscole urlate."""


def rappresentanti(ev):
    """Come in render.py: coppia divergente a sx/dx, riferimento neutro al centro."""
    sin = ev["per_colonna"].get("sinistra", [])
    cen = ev["per_colonna"].get("centro", [])
    des = ev["per_colonna"].get("destra", [])
    sx, dx = coppia_divergente(sin, des)
    rif = ev.get("riferimento") or (cen[0] if cen else None)
    return sx, rif, dx


def completo(ev):
    return all(ev["per_colonna"].get(k) for k in ("sinistra", "centro", "destra"))


def _senza_puntini(s):
    """Toglie eventuali puntini di sospensione iniziali dagli estratti."""
    return (s or "").strip().lstrip("….").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--soglia", type=float, default=SOGLIA)
    ap.add_argument("--max", type=int, default=MAX_CARD)
    ap.add_argument("--secco", action="store_true",
                    help="niente riscrittura Haiku: estratti = titoli veri")
    args = ap.parse_args()

    if not IN.exists():
        print("Manca data/events.json: salto la generazione social.")
        return
    dati = json.loads(IN.read_text(encoding="utf-8"))
    eventi = dati["eventi"] if isinstance(dati, dict) else dati

    # candidati: confronti completi, ordinati per divergenza dei due lati scelti
    cand = []
    for ev in eventi:
        if not completo(ev):
            continue
        sx, rif, dx = rappresentanti(ev)
        if not (sx and rif and dx):
            continue
        div = divergenza(sx.get("titolo", ""), dx.get("titolo", ""))
        cand.append((div, ev, sx, rif, dx))
    cand.sort(key=lambda t: t[0], reverse=True)

    scelti = [c for c in cand if c[0] >= args.soglia][:args.max]
    print("Confronti completi: %d | sopra soglia %.2f: %d | genero: %d"
          % (len(cand), args.soglia, sum(1 for c in cand if c[0] >= args.soglia), len(scelti)))

    client = cluster.client_anthropic() if (scelti and not args.secco) else None
    righe = []
    for div, ev, sx, rif, dx in scelti:
        neutro = ev.get("titolo_neutro", "").strip()
        base = {
            "data": (sx.get("pubblicato", "") or "")[:10],
            "titolo_neutro": neutro,
            "sx_fonte": sx.get("fonte", ""),
            "centro_fonte": rif.get("fonte", ""),
            "dx_fonte": dx.get("fonte", ""),
            "analisi": (ev.get("nota") or "").strip(),
            "divergenza": round(div, 2),
        }
        if args.secco:
            base.update({
                "sintesi": "",
                "sx_estratto": sx.get("titolo", ""),
                "centro_estratto": rif.get("titolo", ""),
                "dx_estratto": dx.get("titolo", ""),
                "caption": "",
            })
        else:
            prompt = PROMPT.format(
                neutro=neutro,
                sx_fonte=sx.get("fonte", ""), sx_titolo=sx.get("titolo", ""),
                c_fonte=rif.get("fonte", ""), c_titolo=rif.get("titolo", ""),
                dx_fonte=dx.get("fonte", ""), dx_titolo=dx.get("titolo", ""))
            try:
                dati, uso = cluster.chiama(client, prompt, SCHEMA_SOCIAL,
                                           max_tokens=1200, modello=cluster.MODELLO)
            except Exception as exc:
                print("  card saltata (%s): %s" % (neutro[:40], str(exc)[:80]))
                continue
            base.update({
                "sintesi": (dati.get("sintesi") or "").strip(),
                "sx_estratto": _senza_puntini(dati.get("sx_estratto")),
                "centro_estratto": _senza_puntini(dati.get("centro_estratto")),
                "dx_estratto": _senza_puntini(dati.get("dx_estratto")),
                "caption": (dati.get("caption") or "").strip(),
            })
        righe.append(base)

    campi = ["data", "titolo_neutro", "sintesi",
             "sx_estratto", "sx_fonte", "centro_estratto", "centro_fonte",
             "dx_estratto", "dx_fonte", "analisi", "caption", "divergenza"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campi)
        w.writeheader()
        for r in righe:
            w.writerow(r)
    print("Scritte %d card in %s" % (len(righe), OUT))


if __name__ == "__main__":
    main()
