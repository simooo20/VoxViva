#!/usr/bin/env python3
"""
render.py - passo 3 di 3.

Prende data/events.json e sputa web/index.html: un file solo, senza
dipendenze esterne, che puoi aprire col doppio click o buttare su
Netlify / GitHub Pages / Cloudflare Pages così com'è.

Impaginazione: in cima a ogni evento il duello fra il titolo più a sinistra e
il più a destra, con il lancio d'agenzia in mezzo come riferimento. Sotto,
tutte le testate nelle tre colonne, ognuna con la sua etichetta precisa.

    python render.py
    python render.py --max 25 --demo
"""
import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from scala import (AGGREGATORE, AREE, BREVI, COLONNE, INDICE, NOMI,
                   allarme, ordina_da_sinistra, piu_allarmante)

BASE = Path(__file__).resolve().parent
IN = BASE / "data" / "events.json"
OUT = BASE / "web" / "index.html"

# Nomi delle tre colonne del confronto. Cambiali qui per rinominarle ovunque.
# Alternative pronte: ("Dalla sinistra","Dal centro","Dalla destra") oppure
# ("Area progressista","Area moderata","Area conservatrice").
ETICHETTE_COLONNE = ("Dai progressisti", "Dai moderati", "Dai conservatori")

# ---------------------------------------------------------------------------
# INTEGRAZIONI: analytics, pubblicita', contatore. Incolla qui i tuoi ID e si
# accendono da soli. Lasciali vuoti e restano spazi grigi "segnaposto".
# ---------------------------------------------------------------------------
GA_ID = ""            # Google Analytics 4, es. "G-XXXXXXX"  (console analytics.google.com)
ADSENSE_CLIENT = ""   # Google AdSense, es. "ca-pub-1234567890123456"
ADSENSE_SLOTS = {     # gli id degli slot creati in AdSense, uno per posizione
    "leaderboard": "",   # banner largo sotto la testata
    "in_feed": "",       # box fra un confronto e l'altro
    "footer": "",        # banner in fondo
}
CONTATORE = False     # contatore letture IN PAGINA (Simone: no; le stat le vede in GA)
CONSENSO_COOKIE = True  # banner consenso GDPR (obbligatorio con GA/AdSense in UE)


def _ga_head():
    if not GA_ID:
        return ""
    return (
        '<script async src="https://www.googletagmanager.com/gtag/js?id=%s"></script>'
        '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}'
        'gtag(\'js\',new Date());gtag(\'config\',\'%s\');</script>'
    ) % (GA_ID, GA_ID)


def _adsense_head():
    if not ADSENSE_CLIENT:
        return ""
    return ('<script async src="https://pagead2.googlesyndication.com/pagead/js/'
            'adsbygoogle.js?client=%s" crossorigin="anonymous"></script>') % ADSENSE_CLIENT


def slot_ads(posizione):
    """Un blocco pubblicitario, SOLO se AdSense e' configurato. Da spento non
    mostra nulla (pagina pulita); si accende incollando client e slot."""
    slot = ADSENSE_SLOTS.get(posizione, "")
    if not (ADSENSE_CLIENT and slot):
        return ""
    return ('<div class="ad ad-%s"><ins class="adsbygoogle" style="display:block" '
            'data-ad-client="%s" data-ad-slot="%s" data-ad-format="auto" '
            'data-full-width-responsive="true"></ins>'
            '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script></div>'
            ) % (posizione, ADSENSE_CLIENT, slot)


def _banner_consenso():
    """Banner consenso cookie: serve solo se analytics o ads sono attivi."""
    if not (GA_ID or ADSENSE_CLIENT) or not CONSENSO_COOKIE:
        return ""
    return (
        '<div id="cc" style="position:fixed;left:0;right:0;bottom:0;background:#16181d;'
        'color:#fff;padding:14px 18px;font-size:13.5px;z-index:99;display:flex;gap:14px;'
        'align-items:center;justify-content:center;flex-wrap:wrap">'
        'Questo sito usa cookie per statistiche e pubblicit&agrave;. '
        '<button onclick="document.getElementById(\'cc\').remove()" '
        'style="background:#fff;color:#16181d;border:0;border-radius:6px;padding:7px 16px;'
        'font-weight:600;cursor:pointer">Ho capito</button></div>'
    )


ROMA = ZoneInfo("Europe/Rome")
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]

CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --ink:#16181d; --ink-2:#474c57; --ink-3:#787e8c;
  --line:#e3e5ea; --line-2:#eef0f3; --bg:#fbfbfc; --card:#fff;
  /* la scala: indaco cupo -> indaco chiaro -> ardesia -> ambra chiara -> ambra cupa.
     Nessun colore di partito: in Italia rosso e azzurro direbbero l'opposto
     della convenzione americana. */
  --SR:#3535ad; --SR-bg:#eeeefc;
  --CS:#7070d8; --CS-bg:#f3f3fd;
  --C:#5c6877;  --C-bg:#f1f4f7;
  --CD:#bd8420; --CD-bg:#fdf7e9;
  --DR:#8d5308; --DR-bg:#fbf2e6;
  --serif:"Iowan Old Style",Georgia,"Times New Roman",serif;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);
  font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:1200px;margin:0 auto;padding:0 24px}
a{color:inherit;text-decoration:none}

/* ---------- testata ---------- */
header.top{background:var(--card);border-bottom:1px solid var(--line);padding:38px 0 30px}
.brand{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.brand h1{font-family:var(--serif);font-size:40px;line-height:1;margin:0;letter-spacing:-.02em}
.brand .tag{font-size:14px;color:var(--ink-3)}
.claim{font-family:var(--serif);font-size:20px;line-height:1.45;color:var(--ink-2);
  margin:18px 0 0;max-width:64ch}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin-top:26px}
.stat{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px 14px;min-width:92px}
.stat b{display:block;font-size:22px;font-family:var(--serif);line-height:1.1}
.stat span{font-size:11.5px;color:var(--ink-3);text-transform:uppercase;letter-spacing:.06em}

/* legenda della scala */
.scala{display:flex;gap:0;margin-top:24px;border-radius:7px;overflow:hidden;
  border:1px solid var(--line);max-width:760px}
.scala div{flex:1;padding:8px 10px;font-size:10.5px;text-transform:uppercase;
  letter-spacing:.05em;text-align:center;font-weight:700;line-height:1.3}
.scala .s-SR{background:var(--SR-bg);color:var(--SR)}
.scala .s-CS{background:var(--CS-bg);color:var(--CS)}
.scala .s-C{background:var(--C-bg);color:var(--C)}
.scala .s-CD{background:var(--CD-bg);color:var(--CD)}
.scala .s-DR{background:var(--DR-bg);color:var(--DR)}
.scala-nota{font-size:12px;color:var(--ink-3);margin:8px 0 0;max-width:760px}

.avviso{background:#fff8e1;border:1px solid #f0dfa8;border-radius:8px;
  padding:13px 16px;margin:24px 0 0;font-size:13.5px;color:#6b5514}
.avviso b{color:#54430f}

/* ---------- evento ---------- */
main{padding:34px 0 10px}
.sezione-tit{font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-3);
  margin:40px 0 8px;padding-bottom:9px;border-bottom:1px solid var(--line)}
.sezione-tit:first-child{margin-top:0}
.sezione-sub{font-size:13.5px;color:var(--ink-3);margin:0 0 18px;max-width:78ch}
.evento{background:var(--card);border:1px solid var(--line);border-radius:12px;
  margin-bottom:22px;overflow:hidden}
.ev-head{padding:19px 22px 0}
.ev-meta{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:9px}
.tema{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--ink-3);
  border:1px solid var(--line);border-radius:20px;padding:2px 9px;white-space:nowrap}
.prima{font-size:11px;text-transform:uppercase;letter-spacing:.07em;font-weight:700;
  color:var(--C);background:var(--C-bg);border:1px solid var(--C-line,#cfd7e0);
  border-radius:20px;padding:2px 10px;white-space:nowrap}
.ev-head h2{font-family:var(--serif);font-size:24px;line-height:1.25;margin:0;
  letter-spacing:-.01em;font-weight:600}

.div-badge{display:inline-flex;align-items:center;gap:7px;font-size:11.5px;
  text-transform:uppercase;letter-spacing:.06em;color:var(--ink-2);white-space:nowrap}
.seg{display:inline-flex;gap:2.5px}
.seg i{width:13px;height:5px;border-radius:2px;background:var(--line);display:block}
.seg i.on{background:var(--ink-2)}
.d-alta .seg i.on{background:#9f2f28}
.d-alta{color:#9f2f28}

/* ---------- il duello ---------- */
.duello{margin:18px 22px 4px;border:1px solid var(--line);border-radius:10px;
  background:linear-gradient(180deg,#fcfcfd,transparent);overflow:hidden}
.duello-tit{font-size:10.5px;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-3);
  padding:9px 16px;border-bottom:1px solid var(--line-2);background:var(--bg)}
.duello-griglia{display:grid;grid-template-columns:1fr auto 1fr}
.polo{padding:15px 18px;min-width:0}
.polo-c{padding:15px 20px;background:var(--C-bg);border-left:1px solid var(--line-2);
  border-right:1px solid var(--line-2);max-width:270px}
.polo .et{font-size:10px;text-transform:uppercase;letter-spacing:.09em;font-weight:700;
  margin-bottom:7px;display:block}
.polo-sx .et{color:var(--ink-3)} .polo-dx .et{color:var(--ink-3);text-align:right}
.polo-dx{text-align:right}
.polo .chi{font-size:12.5px;font-weight:600;margin-bottom:2px;display:block}
.polo .area{font-size:10px;text-transform:uppercase;letter-spacing:.06em;display:block;
  margin-bottom:8px}
.polo .testo{font-family:var(--serif);font-size:17px;line-height:1.34;display:block}
.polo-c .testo{font-size:14.5px;color:var(--ink-2)}
.polo-c .chi{color:var(--C)}
.a-SR .chi,.a-SR .area{color:var(--SR)} .a-CS .chi,.a-CS .area{color:var(--CS)}
.a-C .chi,.a-C .area{color:var(--C)}
.a-CD .chi,.a-CD .area{color:var(--CD)} .a-DR .chi,.a-DR .area{color:var(--DR)}
.polo-sx{border-left:3px solid transparent} .polo-dx{border-right:3px solid transparent}
.polo-sx.a-SR{border-left-color:var(--SR)} .polo-sx.a-CS{border-left-color:var(--CS)}
.polo-sx.a-C{border-left-color:var(--C)}
.polo-sx.a-CD{border-left-color:var(--CD)} .polo-sx.a-DR{border-left-color:var(--DR)}
.polo-dx.a-SR{border-right-color:var(--SR)} .polo-dx.a-CS{border-right-color:var(--CS)}
.polo-dx.a-C{border-right-color:var(--C)}
.polo-dx.a-CD{border-right-color:var(--CD)} .polo-dx.a-DR{border-right-color:var(--DR)}
.polo-c-vuoto{padding:15px 18px;background:var(--bg);border-left:1px solid var(--line-2);
  border-right:1px solid var(--line-2);max-width:200px;font-size:12px;color:var(--ink-3);
  font-style:italic;display:flex;align-items:center}
.scarto{padding:10px 18px 13px;border-top:1px solid var(--line-2);background:#fcfcfd;
  font-size:14.5px;color:var(--ink);font-family:var(--serif);text-align:center;
  line-height:1.45}

.nota{margin:16px 22px 4px;font-size:14.5px;color:var(--ink-2);
  border-left:2px solid var(--line);padding-left:13px}
.nota .et{display:block;font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;
  color:var(--ink-3);margin-bottom:3px}

/* ---------- roundup stile AllSides ---------- */
.roundup{background:var(--card);border:1px solid var(--line);border-radius:12px;
  margin-bottom:22px;overflow:hidden;padding:20px 22px 8px}
.ru-head{padding-bottom:14px;border-bottom:1px solid var(--line-2);margin-bottom:16px}
.ru-kicker{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:9px}
.ru-tema{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-3);
  font-weight:700}
.ru-head h2{font-family:var(--serif);font-size:25px;line-height:1.22;margin:0;
  letter-spacing:-.01em;font-weight:600}
.ru-sint{margin:11px 0 0;font-size:15px;line-height:1.5;color:var(--ink-2);font-family:var(--serif)}
.ru-cols{display:grid;grid-template-columns:repeat(3,1fr);gap:0}
.rc{padding:0 20px;border-right:1px solid var(--line-2);min-width:0}
.rc:first-child{padding-left:0} .rc:last-child{padding-right:0;border-right:0}
.rc-lbl{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;
  padding-bottom:8px;margin-bottom:11px;border-bottom:2px solid;display:block}
.rc:nth-child(1) .rc-lbl{color:var(--CS);border-color:var(--CS)}
.rc:nth-child(2) .rc-lbl{color:var(--C);border-color:var(--C)}
.rc:nth-child(3) .rc-lbl{color:var(--CD);border-color:var(--CD)}
.rc-tit{display:block;font-family:var(--serif);font-size:17px;line-height:1.34;color:var(--ink);
  font-weight:600;margin-bottom:10px}
.rc-tit:hover{text-decoration:underline}
.rc-src{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.rc-fonte{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--ink-3);
  font-weight:600}
.rc-altre{font-size:12px;color:var(--ink-3);margin-top:8px;line-height:1.4}
.rc-vuoto{font-size:13px;color:var(--ink-3);font-style:italic;line-height:1.4}
/* meter L-C-R stile AllSides: 5 celle */
.meter{display:inline-flex;gap:2px}
.meter i{width:11px;height:11px;border-radius:2px;background:#e6e8ec;display:block}
.meter i.on.m-SR{background:var(--SR)} .meter i.on.m-CS{background:var(--CS)}
.meter i.on.m-C{background:var(--C)} .meter i.on.m-CD{background:var(--CD)}
.meter i.on.m-DR{background:var(--DR)}

@media(max-width:820px){
  .ru-cols{grid-template-columns:1fr;gap:0}
  .rc{padding:16px 0;border-right:0;border-bottom:1px solid var(--line-2)}
  .rc:last-child{border-bottom:0}
  .ru-head h2{font-size:22px}
}

/* ---------- tutte le testate ---------- */
.tutte-tit{font-size:10.5px;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-3);
  margin:20px 22px 0;padding-top:14px;border-top:1px solid var(--line-2)}
.colonne{display:grid;grid-template-columns:repeat(3,1fr);margin-top:8px}
.col{padding:12px 20px 20px;border-right:1px solid var(--line-2);min-width:0}
.col:last-child{border-right:0}
.col-tit{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
  padding-bottom:7px;margin-bottom:11px;border-bottom:2px solid var(--line)}
.col-sinistra .col-tit{color:var(--CS)} .col-centro .col-tit{color:var(--C)}
.col-destra .col-tit{color:var(--CD)}
.tit{display:block;margin-bottom:13px}
.tit:last-child{margin-bottom:0}
.tit .riga{font-size:11px;color:var(--ink-3);display:block;margin-bottom:2px}
.tit .riga b{font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.tit .riga .pos{font-size:10px;padding:1px 5px;border-radius:3px;margin-left:5px;
  letter-spacing:.04em;text-transform:uppercase}
.pos.p-SR{background:var(--SR-bg);color:var(--SR)} .pos.p-CS{background:var(--CS-bg);color:var(--CS)}
.pos.p-C{background:var(--C-bg);color:var(--C)}
.pos.p-CD{background:var(--CD-bg);color:var(--CD)} .pos.p-DR{background:var(--DR-bg);color:var(--DR)}
.tit .testo{font-family:var(--serif);font-size:15px;line-height:1.36;color:var(--ink);
  border-bottom:1px solid transparent}
.tit:hover .testo{border-bottom-color:var(--ink-3)}
.vuoto{font-size:12.5px;color:var(--ink-3);font-style:italic;padding:2px 0}
.vuoto b{font-style:normal;display:block;font-size:10.5px;text-transform:uppercase;
  letter-spacing:.07em;color:#9f2f28;margin-bottom:3px}

/* ---------- punti ciechi ---------- */
.bs{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:17px 22px;
  margin-bottom:14px;border-left:3px solid var(--line)}
.bs-sinistra{border-left-color:var(--CS)} .bs-centro{border-left-color:var(--C)}
.bs-destra{border-left-color:var(--CD)}
.bs .quale{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;margin-bottom:7px;
  font-weight:700;color:var(--ink-3)}
.bs h3{font-family:var(--serif);font-size:18px;line-height:1.3;margin:0 0 11px;font-weight:600}

/* ---------- fondo ---------- */
footer{background:var(--card);border-top:1px solid var(--line);margin-top:46px;padding:38px 0 52px;
  font-size:13.5px;color:var(--ink-2)}
footer h4{font-size:11.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--ink);
  margin:0 0 9px}
.fcols{display:grid;grid-template-columns:repeat(3,1fr);gap:34px}
footer p{margin:0 0 10px}
footer .fonti{font-size:12.5px;color:var(--ink-3);line-height:1.7}
.legale{margin-top:30px;padding-top:20px;border-top:1px solid var(--line-2);
  font-size:12px;color:var(--ink-3);max-width:82ch}

@media(max-width:900px){
  .duello-griglia{grid-template-columns:1fr}
  .polo-dx{text-align:left;border-right:3px solid transparent;border-left:3px solid transparent}
  .polo-dx .et{text-align:left}
  .polo-dx.a-CD{border-left-color:var(--CD)} .polo-dx.a-DR{border-left-color:var(--DR)}
  .polo-dx.a-C{border-left-color:var(--C)} .polo-dx.a-CS{border-left-color:var(--CS)}
  .polo-c,.polo-c-vuoto{max-width:none;border-left:0;border-right:0;
    border-top:1px solid var(--line-2);border-bottom:1px solid var(--line-2)}
  .colonne{grid-template-columns:1fr}
  .col{border-right:0;border-bottom:1px solid var(--line-2)}
  .col:last-child{border-bottom:0}
  .fcols{grid-template-columns:1fr;gap:24px}
  .brand h1{font-size:32px} .claim{font-size:17px}
  .scala div{font-size:9px;padding:7px 4px}
}
"""

ADESSO = None


def e(t):
    return html.escape(t or "", quote=True)


def ora_it(iso, riferimento=None):
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ROMA)
    except Exception:
        return ""
    oggi = (riferimento or datetime.now(timezone.utc)).astimezone(ROMA).date()
    delta = (oggi - d.date()).days
    if delta == 0:
        return d.strftime("%H:%M")
    if delta == 1:
        return "ieri %s" % d.strftime("%H:%M")
    return "%d/%d, %s" % (d.day, d.month, d.strftime("%H:%M"))


def data_lunga(iso):
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ROMA)
        return "%s %d %s %d, ore %s" % (GIORNI[d.weekday()], d.day, MESI[d.month - 1], d.year,
                                        d.strftime("%H:%M"))
    except Exception:
        return ""


def segmenti(livello):
    n = {"bassa": 1, "media": 2, "alta": 3}.get(livello, 0)
    return "".join('<i class="on"></i>' if i < n else "<i></i>" for i in range(3))


def polo(a, lato, etichetta):
    """Un capo del duello: sinistro, destro o riferimento centrale."""
    classe = {"sx": "polo polo-sx", "dx": "polo polo-dx", "c": "polo polo-c"}[lato]
    # etichetta è testo nostro, non input: passa senza escape così gli accenti restano
    return (
        '<a class="%s a-%s" href="%s" target="_blank" rel="noopener nofollow">'
        '<span class="et">%s</span>'
        '<span class="chi">%s</span>'
        '<span class="area">%s &middot; %s</span>'
        '<span class="testo">%s</span></a>'
    ) % (classe, a["area"], e(a["url"]), etichetta, e(a["fonte"]),
         e(BREVI[a["area"]]), ora_it(a["pubblicato"], ADESSO), e(a["titolo"]))


def meter(area):
    """Il meter L-C-R stile AllSides: 5 celle, accesa quella della testata."""
    celle = "".join(
        '<i class="m-%s%s"></i>' % (x, " on" if x == area else "")
        for x in AREE
    )
    return '<span class="meter">%s</span>' % celle


def rappresentanti(ev):
    """Un titolo per colonna. A sinistra e a destra si sceglie il piu' ALLARMISTICO
    (cosi' il contrasto e' massimo, come chiedeva Simone), a parita' quello piu'
    verso l'estremo. Al centro resta il riferimento neutro d'agenzia."""
    sin = ev["per_colonna"].get("sinistra", [])
    cen = ev["per_colonna"].get("centro", [])
    des = ev["per_colonna"].get("destra", [])
    sx = piu_allarmante(sin, verso_destra=False)      # il piu' urlato a sinistra
    dx = piu_allarmante(des, verso_destra=True)        # il piu' urlato a destra
    rif = ev.get("riferimento") or (cen[0] if cen else None)
    return sx, rif, dx


def colonna_roundup(titolo_col, art, extra):
    if not art:
        return ('<div class="rc"><div class="rc-lbl">%s</div>'
                '<div class="rc-vuoto">Nessuna testata di quest\'area '
                'ha battuto la notizia.</div></div>') % titolo_col
    fonte_extra = ""
    if extra:
        fonte_extra = '<div class="rc-altre">Anche: %s</div>' % e(", ".join(extra))
    return (
        '<div class="rc">'
        '<div class="rc-lbl">%s</div>'
        '<a class="rc-tit" href="%s" target="_blank" rel="noopener nofollow">%s</a>'
        '<div class="rc-src"><span class="rc-fonte">%s</span>%s</div>'
        '%s</div>'
    ) % (titolo_col, e(art["url"]), e(art["titolo"]),
         e(art["fonte"]), meter(art["area"]), fonte_extra)


def altre_di(ev, chiave, rep):
    """Le altre testate della colonna, senza quella già mostrata come titolo."""
    fonti = []
    for a in ev["per_colonna"].get(chiave, []):
        if a["fonte"] != rep["fonte"] and a["fonte"] not in fonti:
            fonti.append(a["fonte"])
    return fonti


def blocco_evento(ev, con_colonne=True):
    sx, rif, dx = rappresentanti(ev)
    p = ['<article class="roundup">', '<div class="ru-head">']

    p.append('<div class="ru-kicker">')
    if ev.get("principale"):
        p.append('<span class="prima">in prima pagina</span> ')
    p.append('<span class="ru-tema">Rassegna &middot; %s</span>' % e(ev.get("tema", "altro")))
    div = ev.get("divergenza")
    if div:
        p.append(' <span class="div-badge d-%s"><span class="seg">%s</span>divergenza %s</span>'
                 % (e(div), segmenti(div), e(div)))
    p.append("</div>")
    p.append("<h2>%s</h2>" % e(ev["titolo_neutro"]))
    if ev.get("duello"):
        p.append('<p class="ru-sint">%s</p>' % e(ev["duello"]))
    p.append("</div>")

    csx, ccen, cdes = ETICHETTE_COLONNE
    p.append('<div class="ru-cols">')
    p.append(colonna_roundup(csx, sx, altre_di(ev, "sinistra", sx) if sx else []))
    p.append(colonna_roundup(ccen, rif, altre_di(ev, "centro", rif) if rif else []))
    p.append(colonna_roundup(cdes, dx, altre_di(ev, "destra", dx) if dx else []))
    p.append("</div>")

    if ev.get("nota"):
        p.append('<p class="nota"><span class="et">come cambia il racconto</span>%s</p>' % e(ev["nota"]))

    p.append("</article>")
    return "\n".join(p)


def blocco_titolo(a):
    return (
        '<a class="tit" href="%s" target="_blank" rel="noopener nofollow">'
        '<span class="riga"><b>%s</b> %s &middot; %s</span>'
        '<span class="testo">%s</span></a>'
    ) % (e(a["url"]), e(a["fonte"]), meter(a["area"]),
         ora_it(a["pubblicato"], ADESSO), e(a["titolo"]))


def blocco_cieco(ev):
    colonna = ev["colonne_presenti"][0]
    nomi = {k: n for k, n, _ in COLONNE}
    mancanti = ", ".join(nomi[m].lower() for m in ev["colonne_mancanti"])
    aree = ", ".join(BREVI[x] for x in ev["aree_presenti"])
    p = ['<div class="bs bs-%s">' % colonna]
    p.append('<div class="quale">Solo %s (%s) &nbsp;&mdash;&nbsp; silenzio da: %s</div>'
             % (e(nomi[colonna].lower()), e(aree), e(mancanti)))
    p.append("<h3>%s</h3>" % e(ev["titolo_neutro"]))
    reali = [a for a in ev["articoli"] if a.get("area") in AREE]
    for a in ordina_da_sinistra(reali)[:4]:
        p.append(blocco_titolo(a))
    p.append("</div>")
    return "\n".join(p)


def main():
    global ADESSO
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=20)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--punti-ciechi", action="store_true", dest="punti_ciechi",
                    help="mostra anche le notizie coperte da un solo lato (default: no)")
    args = ap.parse_args()

    if not IN.exists():
        raise SystemExit("Non trovo %s. Lancia prima ingest.py e cluster.py" % IN)
    d = json.loads(IN.read_text(encoding="utf-8"))
    eventi = d["eventi"]
    st = d.get("statistiche", {})
    try:
        ADESSO = datetime.fromisoformat(d["generato"].replace("Z", "+00:00"))
    except Exception:
        ADESSO = datetime.now(timezone.utc)

    # REGOLA DI PUBBLICAZIONE: si pubblica solo se ci sono tutte e tre le colonne
    # (sinistra, centro, destra). Se manca un lato, la notizia non esce.
    def completo(ev):
        return all(ev["per_colonna"].get(k) for k in ("sinistra", "centro", "destra"))

    completi = [ev for ev in eventi if completo(ev)]
    scartati_incompleti = len(eventi) - len(completi)

    # dentro ai completi: prima l'agenda (spina dorsale) in ordine, poi gli altri
    principali = sorted([ev for ev in completi if ev.get("principale")],
                        key=lambda e: (e.get("ordine_agenzia", 999), -e["ampiezza"]))[: args.max]
    gia = {id(ev) for ev in principali}
    altri = sorted([ev for ev in completi if id(ev) not in gia],
                   key=lambda e: (e["ampiezza"], e["totale"]), reverse=True)[: args.max]

    # punti ciechi: solo se richiesti esplicitamente (--punti-ciechi). Di default,
    # per la regola di Simone, le notizie senza le tre colonne non si pubblicano.
    ciechi = []
    if args.punti_ciechi:
        ciechi = [ev for ev in eventi if not completo(ev)
                  and len(ev["colonne_presenti"]) == 1 and ev["totale"] >= 2][:10]

    corpo = []
    if principali:
        corpo.append('<div class="sezione-tit">Le principali di oggi</div>')
        corpo.append('<p class="sezione-sub">Le notizie in agenda su Google News, nell\'ordine in cui '
                     'le mette &mdash; e come le titola sinistra, centro e destra. &Egrave; l\'agenda '
                     'del giorno, non una nostra scelta. Compaiono solo le notizie coperte da tutte e '
                     'tre le aree.</p>')
        corpo += [blocco_evento(ev) for ev in principali]
    if altri:
        corpo.append(slot_ads("in_feed"))
        corpo.append('<div class="sezione-tit">Altri confronti</div>')
        corpo.append('<p class="sezione-sub">Notizie fuori dall\'agenda del giorno, ma pur sempre '
                     'coperte da sinistra, centro e destra.</p>')
        corpo += [blocco_evento(ev) for ev in altri]
    if ciechi:
        corpo.append('<div class="sezione-tit">Punti ciechi</div>')
        corpo.append('<p class="sezione-sub">Notizie battute da una sola delle tre aree. Non entrano '
                     'nel confronto (manca un lato), ma il silenzio delle altre &egrave; a sua volta '
                     'un dato.</p>')
        corpo += [blocco_cieco(ev) for ev in ciechi]

    stat = [
        (len(principali) + len(altri), "confronti<br>pubblicati"),
        (len(principali), "in prima<br>pagina"),
        (scartati_incompleti, "scartati<br>(manca un lato)"),
        (d.get("totale_articoli", 0), "titoli letti"),
        (len(d.get("testate_attive", [])), "testate"),
    ]
    stat_html = "".join('<div class="stat"><b>%s</b><span>%s</span></div>' % (n, t) for n, t in stat)

    scala_html = "".join('<div class="s-%s">%s</div>' % (x, e(NOMI[x])) for x in AREE)

    avviso = ""
    if args.demo:
        avviso = (
            '<div class="avviso"><b>Anteprima con dati reali ma copertura ridotta.</b> '
            'Titoli autentici da %d testate, %s. La <b>spina dorsale</b> &egrave; Google News: '
            'decide quali sono le principali del giorno, l\'ANSA d&agrave; la versione di centro. '
            'Qui gli item Google News sono illustrativi &mdash; da questa rete GN non &egrave; '
            'raggiungibile &mdash; ma dal tuo PC diventano quelli reali. Mancano ancora Il '
            'Giornale, Repubblica, Corriere, Il Fatto e Il Manifesto (feed rotti o irraggiungibili). '
            'Si pubblicano <b>solo le notizie coperte da tutte e tre le aree</b> (sinistra, centro, '
            'destra): oggi 8 su 19, le altre 11 scartate perch&eacute; manca un lato. '
            'Raggruppamento fatto a mano con la logica di <code>cluster.py</code>.</div>'
            % (len(d.get("testate_attive", [])), data_lunga(d["generato"]))
        )

    doc = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VoxViva &mdash; la stessa notizia, da un estremo all'altro</title>
<meta name="description" content="Come la stessa notizia italiana viene titolata dalla sinistra radicale alla destra radicale. Aggiornato ogni giorno.">
%(ga)s%(adsense)s<style>%(css)s</style>
</head>
<body>

%(leaderboard)s
<header class="top"><div class="wrap">
  <div class="brand">
    <h1>VoxViva</h1>
    <span class="tag">la stessa notizia, da un estremo all'altro</span>
  </div>
  <p class="claim">Quasi nessuno legge gli articoli: si leggono i titoli. Qui ogni notizia
  italiana &egrave; messa accanto a se stessa, dal titolo pi&ugrave; a sinistra a quello pi&ugrave;
  a destra, col lancio d'agenzia in mezzo. Nessun titolo &egrave; riscritto.</p>
  %(stat)s
  <div class="scala">%(scala)s</div>
  <p class="scala-nota">I colori seguono la scala, non i partiti: in Italia rosso e azzurro
  direbbero l'opposto della convenzione americana.</p>
  %(avviso)s
  <p style="margin:22px 0 0;font-size:13px;color:var(--ink-3)">
    Ultimo aggiornamento: %(agg)s &middot; finestra: ultime %(ore)d ore
  </p>
</div></header>

<main><div class="wrap">
%(corpo)s
</div></main>

<footer><div class="wrap">
  <div class="fcols">
    <div>
      <h4>Come funziona</h4>
      <p>Ogni ora leggiamo i feed RSS delle testate monitorate. Un modello linguistico
      raggruppa i titoli che parlano dello stesso fatto &mdash; non per parole in comune,
      ma per contenuto: &egrave; il punto, dato che le parole sono proprio la cosa che cambia.</p>
      <p>Le <b>principali</b> non le scegliamo noi: sono le notizie che l'agenzia ANSA ha
      messo in prima pagina e che almeno un giornale ha ripreso, nell'ordine dell'agenzia.
      Cos&igrave; l'agenda del giorno &egrave; neutrale. Pubblichiamo una notizia solo se
      &egrave; coperta da tutte e tre le aree: sinistra, centro e destra.</p>
      <p>Quando raggruppa, il modello non vede la posizione politica delle testate. E non
      riscrive mai i titoli: restituisce solo dei riferimenti. I titoli che leggi sono quelli
      pubblicati dalle testate, alla lettera. Il titolo neutro dell'evento e la nota
      &laquo;come cambia il racconto&raquo; sono invece testo nostro.</p>
    </div>
    <div>
      <h4>Le etichette</h4>
      <p>Le cinque posizioni descrivono la <em>linea editoriale prevalente</em> di una
      testata, non il contenuto del singolo articolo: un giornale di sinistra pu&ograve;
      scrivere un pezzo asciutto e uno di destra un pezzo misurato.</p>
      <p>Non sono un punteggio e non hanno decimali. Dove la nostra collocazione si discosta
      da quella comunemente accettata, lo dichiariamo nella pagina metodo insieme al gruppo
      editoriale proprietario, che &egrave; invece un fatto verificabile. Se un'etichetta ti
      sembra sbagliata, scrivici.</p>
    </div>
    <div>
      <h4>Testate monitorate</h4>
      <p class="fonti">%(fonti)s</p>
    </div>
  </div>
  <p class="legale">VoxViva riporta i titoli cos&igrave; come pubblicati, con l'indicazione
  della testata e il collegamento all'articolo originale, e non riproduce i testi. Ogni clic
  porta al sito dell'editore. Le testate sono titolari dei diritti sui propri contenuti; per
  richieste di rimozione o segnalazioni: scrivi all'indirizzo di contatto. Progetto
  indipendente, non affiliato ad alcuna testata o partito.</p>
  %(footer_ad)s
</div></footer>
%(consenso)s
</body></html>
""" % {
        "css": CSS,
        "ga": _ga_head(),
        "adsense": _adsense_head(),
        "leaderboard": ('<div class="wrap wrap-ad">%s</div>' % slot_ads("leaderboard")) if slot_ads("leaderboard") else "",
        "footer_ad": slot_ads("footer"),
        "consenso": _banner_consenso(),
        "stat": '<div class="stats">%s</div>' % stat_html,
        "scala": scala_html,
        "avviso": avviso,
        "agg": data_lunga(d["generato"]),
        "ore": d.get("finestra_ore", 24),
        "corpo": "\n".join(corpo) or "<p>Nessun evento da mostrare.</p>",
        "fonti": e(", ".join(d.get("testate_monitorate") or d.get("testate_attive", []))),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    print("Sito generato: %s" % OUT)
    print("  %d confronti pubblicati (%d in prima pagina), %d scartati per lato mancante, %d punti ciechi"
          % (len(principali) + len(altri), len(principali), scartati_incompleti, len(ciechi)))


if __name__ == "__main__":
    main()
