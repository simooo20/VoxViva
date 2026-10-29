"""Decide se scrivere sulla segnalazione «Controllo qualita VoxViva» (issue).

Ogni commento sulla segnalazione = una mail a Simone. Regola (29/10/2026):
UNA mail per problema, non una per giro.

- giro fallito (il sito resta fermo): si scrive la prima volta, con le ultime
  righe del log; se i giri dopo falliscono allo stesso modo, silenzio;
- il sito torna ad aggiornarsi dopo un giro fallito: una riga per dirlo;
- allarmi di qualita' (sito aggiornato ma con difetti): si scrive solo quando
  compare un TIPO di allarme mai segnalato dall'ultimo «tutto a posto».

Ogni commento porta delle chiavi nascoste (<!-- chiave: ... -->): il passo del
workflow le rilegge tutte (file indicato da CHIAVI_FILE) e le passa qui.

Input (variabili d'ambiente): ESITO = outcome del passo «Rigenera la pagina»,
GIRO = numero del giro, CHIAVI_FILE = chiavi gia' scritte, in ordine.
Output: il testo del commento su stdout (vuoto = non scrivere niente).
"""
import json
import os
import re
from datetime import datetime, timezone

ESITO = os.environ.get("ESITO", "")
GIRO = os.environ.get("GIRO", "?")


def normalizza(s):
    """Toglie da una riga quello che cambia a ogni giro (numeri, id), cosi'
    lo stesso errore da' sempre la stessa chiave."""
    s = re.sub(r"req_\w+|[0-9a-f]{8,}|\d+", "#", s)
    s = re.sub(r"[<>]", "", s)
    return re.sub(r"\s+", " ", s).strip()[:150]


def chiavi_attive():
    """Chiavi scritte dopo l'ultimo «ok»: quello che e' gia' stato segnalato."""
    try:
        righe = open(os.environ.get("CHIAVI_FILE", "chiavi.txt"), encoding="utf-8").read().splitlines()
    except OSError:
        return set()
    righe = [r.strip() for r in righe if r.strip()]
    if "ok" in righe:
        righe = righe[len(righe) - righe[::-1].index("ok"):]
    return set(righe)


def coda_log(n=30):
    try:
        testo = open("giro.log", encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    testo = re.sub(r"sk-ant-[\w-]+", "sk-ant-***", testo)   # mai una chiave nel commento
    return [r for r in testo.splitlines() if r.strip()][-n:]


def commento(corpo, chiavi):
    ora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    nascoste = "\n".join("<!-- chiave: %s -->" % k for k in chiavi)
    return "%s - giro %s\n\n%s\n\n%s" % (ora, GIRO, corpo, nascoste)


def main():
    gia = chiavi_attive()

    if ESITO == "failure":
        coda = coda_log()
        chiave = "fallito: " + normalizza(coda[-1] if coda else "nessun log")
        if chiave in gia:
            return ""
        corpo = ("**Giro non riuscito: il sito resta fermo all'ultima versione pubblicata.**\n\n"
                 "Ultime righe del log:\n\n```\n%s\n```\n\n"
                 "_Se i prossimi giri falliscono allo stesso modo non arrivano altre mail._"
                 % "\n".join(coda))
        return commento(corpo, [chiave])

    if ESITO != "success":
        return ""

    try:
        allarmi = json.load(open("web/stato.json", encoding="utf-8")).get("allarmi") or []
    except Exception as e:
        allarmi = ["stato.json non leggibile: %s" % e]

    # dopo un giro fallito il sito e' ripartito: si scrive «ok» e si riparte da zero
    ripreso = any(k.startswith("fallito") for k in gia)
    if ripreso:
        gia = set()
    tipi = sorted({"qualita: " + normalizza(a.split(":")[0]) for a in allarmi})
    nuovi = [t for t in tipi if t not in gia]
    elenco = "\n".join("- " + a for a in allarmi)

    if ripreso and allarmi:
        return commento("Il sito si e' aggiornato di nuovo, con questi allarmi di qualita':\n\n"
                        + elenco, ["ok"] + nuovi)
    if ripreso:
        return commento("Il sito si e' aggiornato di nuovo: tutto a posto.", ["ok"])
    if nuovi:
        return commento(elenco, nuovi)
    return ""


if __name__ == "__main__":
    print(main(), end="")
