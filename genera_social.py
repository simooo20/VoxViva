#!/usr/bin/env python3
"""
genera_social.py - dai confronti alle card social, pronte da scaricare come PNG.

Legge data/events.json, prende i confronti completi (sinistra, centro, destra),
li ordina per divergenza fra i due lati e per ognuno chiede a Haiku:
  1. i tre titoli parlano DELLO STESSO fatto? Se no, la card si scarta.
  2. titolo neutro, sintesi, tre estratti e didascalia.
Gli estratti sono riscritti in versione social ma SENZA forzare il tono: restano
fedeli a parole e registro del titolo vero.

Esce web/social.html: una pagina con le card gia' impaginate (4:5, 1080x1350),
un bottone "Scarica PNG" per ognuna e la didascalia da copiare. Niente CSV,
niente Canva: apri il file nel browser, scarichi le immagini, pubblichi.

    python genera_social.py                 # soglia e numero da variabili/default
    python genera_social.py --soglia 0.5 --max 4

Manopole (Settings > Variables):
    ILVAGLIO_SOGLIA_DIVERGENZA   divergenza minima fra i due lati (default 0.5)
    ILVAGLIO_MAX_SOCIAL          quante card al massimo (default 4)
"""
import argparse
import html
import json
import os
import re
from pathlib import Path

from scala import coppia_divergente, divergenza

BASE = Path(__file__).resolve().parent
IN = BASE / "data" / "events.json"
OUT = BASE / "web" / "social.html"

SOGLIA = float(os.environ.get("ILVAGLIO_SOGLIA_DIVERGENZA", "0.5"))
MAX_CARD = int(os.environ.get("ILVAGLIO_MAX_SOCIAL", "4"))
TENTATIVI_PER_CARD = 3   # quanti confronti al massimo si esaminano per ogni card voluta

SCHEMA_SOCIAL = {
    "name": "registra_card",
    "description": "Controlla il confronto e scrive i testi della card social.",
    "input_schema": {
        "type": "object",
        "properties": {
            "stesso_fatto": {"type": "boolean",
                             "description": "true SOLO se i tre titoli raccontano lo stesso fatto specifico (stesso episodio, stessa dichiarazione, stesso dato). false se uno parla di un fatto collegato ma diverso, di un altro protagonista o e' un commento generico."},
            "motivo": {"type": "string",
                       "description": "Una frase: perche' e' o non e' lo stesso fatto."},
            "titolo": {"type": "string",
                       "description": "Titolo neutro della card: il fatto nudo, max ~12 parole. Nessun verbo di giudizio (attacca, sfida, scontro, umilia, bufera, choc). Solo cio' che risulta da TUTTI e tre i titoli."},
            "sintesi": {"type": "string",
                        "description": "Due frasi brevi, neutre: cosa mette in primo piano ciascun lato, nominando le testate. Solo punti e virgole, MAI il punto e virgola."},
            "sx_estratto": {"type": "string",
                            "description": "Versione social del titolo di SINISTRA: max ~12 parole, stesse parole chiave e stesso registro del titolo vero. Non aggiungere enfasi."},
            "centro_estratto": {"type": "string",
                                "description": "Versione social del titolo di CENTRO: max ~12 parole, fedele al titolo vero."},
            "dx_estratto": {"type": "string",
                            "description": "Versione social del titolo di DESTRA: max ~12 parole, stesse parole chiave e stesso registro del titolo vero. Non aggiungere enfasi."},
            "caption": {"type": "string",
                        "description": "Didascalia Instagram: 2-3 frasi neutre, chiude invitando a leggere il confronto su voxviva.xyz. Niente hashtag."},
        },
        "required": ["stesso_fatto", "motivo", "titolo", "sintesi",
                     "sx_estratto", "centro_estratto", "dx_estratto", "caption"],
    },
}

PROMPT = """Sei l'editor social di VoxViva, che mette a confronto come le testate italiane titolano la stessa notizia da sinistra, centro e destra.

I titoli VERI, come pubblicati:
- SINISTRA ({sx_fonte}): {sx_titolo}
- CENTRO ({c_fonte}): {c_titolo}
- DESTRA ({dx_fonte}): {dx_titolo}

Chiama registra_card.

PRIMA controlla: i tre titoli parlano dello STESSO fatto specifico? Se uno parla di un fatto collegato ma diverso (un altro protagonista, un altro aspetto che e' di per se' una notizia a parte, un commento generico), rispondi stesso_fatto=false. Nel dubbio, false: una card sbagliata e' peggio di nessuna card.

Poi scrivi i testi:
- TITOLO: il fatto nudo, come lo scriverebbe un'agenzia. Niente verbi di giudizio. Niente che non risulti da tutti e tre i titoli.
- ESTRATTI: accorcia il titolo di ogni lato per un post, SENZA forzare il tono. Tieni le parole chiave e il registro dell'originale: se il titolo e' asciutto resta asciutto, se e' polemico resta polemico quanto l'originale, non di piu'. Non inventare nulla. Niente puntini di sospensione all'inizio.
- SINTESI: due frasi neutre su cosa mette in primo piano ciascun lato, con i nomi delle testate. Mai il punto e virgola.
- CAPTION: neutra, incuriosisce, invita a leggere il confronto su voxviva.xyz. Niente hashtag, niente maiuscole urlate."""


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


def pulito(s):
    """Una riga sola, niente punto e virgola, niente puntini iniziali."""
    s = re.sub(r"\s+", " ", (s or "")).strip()
    s = s.replace(";", ".")
    return s.lstrip("….").strip()


# ---------------------------------------------------------------- pagina HTML

PAGINA = """<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VoxViva — card social</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;500;700&family=Inter:ital,wght@0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<style>
:root{--or:#F25623;--nero:#111;--gr:#6b6b6b;--sf:#ececec}
*{box-sizing:border-box}
body{margin:0;background:var(--sf);font-family:Inter,system-ui,sans-serif;color:var(--nero)}
header.pag{max-width:1100px;margin:0 auto;padding:28px 20px 8px}
header.pag h1{font-family:'Space Grotesk',sans-serif;font-size:26px;margin:0 0 4px}
header.pag p{margin:0;color:var(--gr);font-size:14px}
main{max-width:1100px;margin:0 auto;padding:16px 20px 60px;display:grid;
  grid-template-columns:repeat(auto-fill,minmax(440px,1fr));gap:28px}
.blocco{background:#fff;border-radius:10px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.anteprima{width:432px;height:540px;overflow:hidden;margin:0 auto;border:1px solid #ddd}
.anteprima .card{transform:scale(.4);transform-origin:0 0}
.azioni{display:flex;gap:8px;margin:14px 0 10px;flex-wrap:wrap}
button{font:600 14px Inter,sans-serif;border:0;border-radius:6px;padding:9px 14px;cursor:pointer}
.b1{background:var(--or);color:#fff}.b2{background:#222;color:#fff}
.caption{font-size:14px;line-height:1.45;color:#333;background:#f6f6f6;border-radius:6px;padding:10px 12px;white-space:pre-wrap}
.meta{font-size:12px;color:var(--gr);margin-top:8px}
.vuoto{grid-column:1/-1;text-align:center;color:var(--gr);padding:60px 0}

/* ------- la card vera, 1080x1350 ------- */
.card{width:1080px;height:1350px;position:relative;overflow:hidden;background:#fff;
  font-family:Inter,sans-serif;color:var(--nero);padding:72px 72px 0}
.card .fiamma{position:absolute;left:0;right:0;bottom:0;height:560px;
  background:radial-gradient(ellipse 75% 100% at 50% 100%,rgba(242,86,35,1) 0%,rgba(242,86,35,.7) 30%,rgba(242,86,35,.2) 65%,rgba(242,86,35,0) 100%);}
.card .testa{display:flex;justify-content:space-between;align-items:baseline;position:relative}
.card .marchio{font-family:'Space Grotesk',sans-serif;font-size:54px;letter-spacing:-1.5px}
.card .marchio b{font-weight:700}.card .marchio span{font-weight:300}
.card .data{font-size:24px;color:var(--gr)}
.card .titolo{position:relative;font-family:'Space Grotesk',sans-serif;font-weight:700;color:var(--or);
  font-size:68px;line-height:1.05;letter-spacing:-1.5px;margin:56px 0 0;height:230px;display:flex;align-items:flex-end}
.card .sintesi{position:relative;font-style:italic;font-size:30px;line-height:1.35;color:#444;margin:28px 0 0;height:125px}
.card .colonne{position:relative;display:grid;grid-template-columns:repeat(3,1fr);gap:40px;margin-top:48px}
.card .col h3{margin:0 0 14px;font:600 22px Inter,sans-serif;letter-spacing:3px;text-transform:uppercase;
  padding-bottom:12px;border-bottom:5px solid var(--or)}
.card .fonte{margin:0 0 16px;font-size:24px;color:var(--gr)}
.card .est{font-weight:600;font-size:34px;line-height:1.22;height:330px;overflow:hidden}
.card .piede{position:absolute;left:72px;right:72px;bottom:56px;display:flex;justify-content:space-between;
  font-family:'Space Grotesk',sans-serif;font-size:28px;color:var(--nero);font-weight:500}
</style></head><body>
<header class="pag"><h1>Card social — %(quando)s</h1>
<p>%(n)d card. "Scarica PNG" salva l'immagine 1080&times;1350 pronta per Instagram.</p></header>
<main>%(blocchi)s</main>
<script>
function adatta(el,min){ // rimpicciolisce il testo finche' non entra nel suo box
  var s=parseFloat(getComputedStyle(el).fontSize);
  while((el.scrollHeight>el.clientHeight+1)&&s>min){s-=1;el.style.fontSize=s+'px';}
}
function adattaTutte(){
  document.querySelectorAll('.card').forEach(function(c){
    adatta(c.querySelector('.titolo'),40);adatta(c.querySelector('.sintesi'),22);
    c.querySelectorAll('.est').forEach(function(e){adatta(e,22);});
  });
}
async function scarica(i){
  var orig=document.getElementById('card'+i),box=document.createElement('div');
  box.style.cssText='position:fixed;left:-20000px;top:0';
  var cl=orig.cloneNode(true);cl.style.transform='none';box.appendChild(cl);document.body.appendChild(box);
  var tela=await html2canvas(cl,{width:1080,height:1350,scale:1,backgroundColor:'#ffffff',useCORS:true});
  document.body.removeChild(box);
  var a=document.createElement('a');a.download='voxviva-card-'+(i+1)+'.png';a.href=tela.toDataURL('image/png');a.click();
}
function copia(i,b){
  navigator.clipboard.writeText(document.getElementById('cap'+i).innerText).then(function(){
    b.textContent='Copiata';setTimeout(function(){b.textContent='Copia didascalia';},1500);});
}
(document.fonts?document.fonts.ready:Promise.resolve()).then(adattaTutte);
</script></body></html>"""

BLOCCO = """<section class="blocco">
<div class="anteprima"><div class="card" id="card%(i)d">
  <div class="fiamma"></div>
  <div class="testa"><div class="marchio"><b>vox</b><span>viva</span></div><div class="data">%(data)s</div></div>
  <div class="titolo">%(titolo)s</div>
  <div class="sintesi">%(sintesi)s</div>
  <div class="colonne">
    <div class="col"><h3>Sinistra</h3><div class="fonte">%(sx_fonte)s</div><div class="est">%(sx)s</div></div>
    <div class="col"><h3>Centro</h3><div class="fonte">%(c_fonte)s</div><div class="est">%(c)s</div></div>
    <div class="col"><h3>Destra</h3><div class="fonte">%(dx_fonte)s</div><div class="est">%(dx)s</div></div>
  </div>
  <div class="piede"><span>La stessa notizia. Da un estremo all'altro.</span><span>voxviva.xyz</span></div>
</div></div>
<div class="azioni"><button class="b1" onclick="scarica(%(i)d)">Scarica PNG</button>
<button class="b2" onclick="copia(%(i)d,this)">Copia didascalia</button></div>
<div class="caption" id="cap%(i)d">%(caption)s</div>
<div class="meta">Titoli veri — Sx: %(sx_vero)s · C: %(c_vero)s · Dx: %(dx_vero)s · divergenza %(div).2f</div>
</section>"""

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def data_it(iso):
    try:
        a, m, g = iso[:10].split("-")
        return "%d %s %s" % (int(g), MESI[int(m) - 1], a)
    except Exception:
        return ""


def virgolette(t):
    """L'estratto va fra « »: le virgolette interne diventano “ ” per non annidare."""
    return "«%s»" % t.replace("«", "“").replace("»", "”")


def scrivi_pagina(card, quando=""):
    e = html.escape
    blocchi = []
    for i, c in enumerate(card):
        blocchi.append(BLOCCO % {
            "i": i, "data": e(data_it(c["data"])), "titolo": e(c["titolo"]),
            "sintesi": e(c["sintesi"]),
            "sx": e(virgolette(c["sx_estratto"])), "sx_fonte": e(c["sx_fonte"]),
            "c": e(virgolette(c["centro_estratto"])), "c_fonte": e(c["centro_fonte"]),
            "dx": e(virgolette(c["dx_estratto"])), "dx_fonte": e(c["dx_fonte"]),
            "caption": e(c["caption"]),
            "sx_vero": e(c["sx_vero"]), "c_vero": e(c["c_vero"]), "dx_vero": e(c["dx_vero"]),
            "div": c["divergenza"],
        })
    if not blocchi:
        blocchi.append('<p class="vuoto">Nessun confronto ha passato il controllo in questo giro.</p>')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pagina = (PAGINA.replace("%(quando)s", e(quando))
              .replace("%(n)d", str(len(card)))
              .replace("%(blocchi)s", "\n".join(blocchi)))
    OUT.write_text(pagina, encoding="utf-8")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--soglia", type=float, default=SOGLIA)
    ap.add_argument("--max", type=int, default=MAX_CARD)
    args = ap.parse_args()

    if not IN.exists():
        print("Manca data/events.json: niente card.")
        return
    dati = json.loads(IN.read_text(encoding="utf-8"))
    eventi = dati["eventi"] if isinstance(dati, dict) else dati

    cand = []
    for ev in eventi:
        if not completo(ev):
            continue
        sx, rif, dx = rappresentanti(ev)
        if not (sx and rif and dx):
            continue
        div = divergenza(sx.get("titolo", ""), dx.get("titolo", ""))
        if div >= args.soglia:
            cand.append((div, ev, sx, rif, dx))
    cand.sort(key=lambda t: t[0], reverse=True)
    cand = cand[:args.max * TENTATIVI_PER_CARD]
    print("Confronti da esaminare: %d (soglia %.2f, card volute %d)" % (len(cand), args.soglia, args.max))

    import cluster  # solo qui: serve la chiave API
    client = cluster.client_anthropic() if cand else None
    card = []
    for div, ev, sx, rif, dx in cand:
        if len(card) >= args.max:
            break
        prompt = PROMPT.format(
            sx_fonte=sx.get("fonte", ""), sx_titolo=sx.get("titolo", ""),
            c_fonte=rif.get("fonte", ""), c_titolo=rif.get("titolo", ""),
            dx_fonte=dx.get("fonte", ""), dx_titolo=dx.get("titolo", ""))
        try:
            r, _ = cluster.chiama(client, prompt, SCHEMA_SOCIAL,
                                  max_tokens=1200, modello=cluster.MODELLO)
        except Exception as exc:
            print("  saltata (errore): %s" % str(exc)[:80])
            continue
        if not r.get("stesso_fatto"):
            print("  SCARTATA: %s -> %s" % (ev.get("titolo_neutro", "")[:50], r.get("motivo", "")))
            continue
        print("  ok: %s" % r.get("titolo", ""))
        card.append({
            "data": (rif.get("pubblicato") or sx.get("pubblicato") or "")[:10],
            "titolo": pulito(r.get("titolo")),
            "sintesi": pulito(r.get("sintesi")),
            "sx_estratto": pulito(r.get("sx_estratto")), "sx_fonte": sx.get("fonte", ""),
            "centro_estratto": pulito(r.get("centro_estratto")), "centro_fonte": rif.get("fonte", ""),
            "dx_estratto": pulito(r.get("dx_estratto")), "dx_fonte": dx.get("fonte", ""),
            "caption": (r.get("caption") or "").strip(),
            "sx_vero": sx.get("titolo", ""), "c_vero": rif.get("titolo", ""), "dx_vero": dx.get("titolo", ""),
            "divergenza": div,
        })

    quando = dati.get("generato", "") if isinstance(dati, dict) else ""
    scrivi_pagina(card, data_it(quando) if quando else "")
    print("Scritte %d card in %s" % (len(card), OUT))


if __name__ == "__main__":
    main()
