# Il Vaglio — dalla cartella al sito online

Questa guida ti porta dal progetto che hai sul computer a un sito vero,
raggiungibile da chiunque, che si aggiorna da solo ogni 30 minuti. Non serve
saper programmare: si fa tutto dal sito di GitHub, cliccando.

Tempo richiesto: circa mezz'ora la prima volta. Poi non ci torni quasi più.

---

## Come funziona, in due righe

GitHub tiene il codice e, gratis, ospita il sito (si chiama **GitHub Pages**).
Ogni 30 minuti un programmino di GitHub (una **Action**) riaccende la
pipeline: legge i feed dei giornali, raggruppa le notizie con l'intelligenza
artificiale, ricostruisce la pagina e la pubblica. Il visitatore apre il sito
e vede sempre l'ultima versione. Tutto il lavoro avviene sui computer di
GitHub, non sul suo.

Ti servono due cose: un account GitHub (gratuito) e la tua chiave API di
Anthropic (quella che fa funzionare l'intelligenza artificiale).

---

## Passo 1 — Crea il repository

Il "repository" (o "repo") è la cartella del progetto su GitHub.

1. Vai su https://github.com e accedi (o registrati, è gratis).
2. In alto a destra, clicca sul **+** e poi **New repository**.
3. Dai un nome, per esempio `ilvaglio`.
4. Lascialo **Public** (pubblico). È importante: GitHub Pages è gratis solo
   sui repo pubblici. Non è un problema di sicurezza — nel codice non c'è
   niente di segreto, e la chiave API la metteremo a parte, protetta.
5. Non spuntare nessuna casella ("Add README", ecc.): lasciamo la cartella
   vuota, ci mettiamo i nostri file.
6. Clicca **Create repository**.

---

## Passo 2 — Carica i file del progetto

Nella pagina del repo appena creato, cerca il link **"uploading an existing
file"** (oppure il pulsante **Add file → Upload files**).

1. Apri sul tuo computer la cartella del progetto (`ilvaglio`).
2. Selezionane **tutto il contenuto** — i file `.py`, `sources.json`,
   `requirements.txt`, la cartella `web`, la cartella `.github` — e trascinalo
   nella pagina di GitHub.

   Attenzione a due cartelle un po' nascoste ma essenziali:
   - `.github` (contiene la Action che fa girare tutto);
   - `web` (contiene la pagina del sito).

   Se dal Finder/Esplora file non riesci a trascinare le cartelle che iniziano
   con un punto, usa il caricamento tramite Git (in fondo alla guida) oppure
   crea i file a mano con **Add file → Create new file** scrivendo il percorso
   `.github/workflows/aggiorna.yml`.

3. In fondo clicca **Commit changes**.

---

## Passo 3 — Metti al sicuro la chiave API

La chiave API non va mai scritta dentro il codice. GitHub ha una cassaforte
apposta.

1. Nel repo, vai su **Settings** (in alto).
2. Nel menù a sinistra: **Secrets and variables → Actions**.
3. Clicca **New repository secret**.
4. Nel campo **Name** scrivi esattamente:

   ```
   ANTHROPIC_API_KEY
   ```

5. Nel campo **Secret** incolla la tua chiave API di Anthropic (quella che
   inizia con `sk-ant-...`). La trovi nella tua console Anthropic, alla voce
   API Keys.
6. Clicca **Add secret**.

Da questo momento la Action può usare la chiave senza che nessuno la veda: nei
log appare sempre oscurata.

---

## Passo 4 — Accendi il sito (GitHub Pages)

1. Sempre in **Settings**, menù a sinistra: **Pages**.
2. Alla voce **Source** (Sorgente), scegli **GitHub Actions**.

   È tutto. Non serve scegliere un branch: alla pubblicazione ci pensa la
   nostra Action.

---

## Passo 5 — Prima accensione a mano

Non aspettiamo la mezz'ora: lanciamola subito per vedere se tutto gira.

1. Nel repo, vai sulla scheda **Actions** (in alto).
2. Se GitHub chiede di abilitare i workflow, conferma (**I understand my
   workflows, go ahead and enable them**).
3. A sinistra clicca **Aggiorna Il Vaglio**.
4. A destra clicca **Run workflow** → **Run workflow**.

Parte un giro. Dura un paio di minuti (legge i feed, chiama l'AI, costruisce
la pagina, pubblica). Se tutto va bene vedi la spunta verde. Se qualcosa si
ferma, clicca sul giro fallito per leggere dove: quasi sempre è la chiave API
scritta male o mancante.

Finito il primo giro con successo, il sito è online. L'indirizzo è:

```
https://TUONOME.github.io/ilvaglio/
```

(sostituisci `TUONOME` con il tuo nome utente GitHub). Lo trovi anche in
**Settings → Pages**, scritto in alto.

Da qui in poi il sito si riaggiorna da solo ogni 30 minuti. Non devi fare più
niente.

---

## Passo 6 — Il dominio tuo (opzionale ma consigliato)

`tuonome.github.io/ilvaglio` funziona, ma un indirizzo come `ilvaglio.it` è
più serio, più facile da ricordare, e ti servirà se un domani vorrai la
pubblicità (Google AdSense non accetta i sottodomini `.github.io`).

### 6a. Compra il dominio

Si compra da un "registrar". Costano in genere 10–15 € l'anno. Alcuni
affidabili: Namecheap, Porkbun, Cloudflare, GoDaddy, o italiani come Aruba e
Register.it. Cerca il nome che vuoi (`ilvaglio.it`, `ilvaglio.news`…) e
completalo. Non serve comprare hosting, email o extra: solo il dominio.

### 6b. Punta il dominio su GitHub

Nel pannello del registrar cerca la sezione **DNS**. Devi aggiungere questi
record.

Se usi il dominio "nudo" (`ilvaglio.it`), aggiungi **quattro record di tipo A**
che puntano agli indirizzi di GitHub:

```
Tipo   Nome/Host   Valore
A      @           185.199.108.153
A      @           185.199.109.153
A      @           185.199.110.153
A      @           185.199.111.153
```

E, per far funzionare anche la versione con `www`, un record **CNAME**:

```
Tipo    Nome/Host   Valore
CNAME   www         TUONOME.github.io
```

(sempre col tuo nome utente al posto di `TUONOME`, e col punto finale se il
pannello lo richiede).

I cambiamenti DNS possono metterci da qualche minuto a qualche ora a
propagarsi. È normale.

### 6c. Di' a GitHub qual è il dominio

1. Nel repo: **Settings → Pages**.
2. Alla voce **Custom domain** scrivi il tuo dominio (`ilvaglio.it`) e clicca
   **Save**.
3. GitHub fa un controllo. Quando è verde, spunta **Enforce HTTPS** (così il
   sito va in `https://`, col lucchetto). Questa spunta può comparire dopo
   qualche minuto: se all'inizio è grigia, riprova più tardi.

Fatto. Il file `web/CNAME.esempio` che trovi nel progetto è solo un promemoria:
non serve modificarlo, il dominio si imposta qui dai Settings.

---

## Quanto costa

L'hosting su GitHub Pages è **gratis**. La Action è gratis nei limiti
generosi del piano free (i minuti che consuma un giro da due minuti, 48 volte
al giorno, ci stanno comodamente dentro).

L'unica spesa viva è la tua **chiave API di Anthropic**: ogni mezz'ora fa una
manciata di chiamate al modello. Con Claude Sonnet il costo di un singolo giro
è di pochi centesimi; su 48 giri al giorno parliamo dell'ordine di qualche
euro al mese, a seconda di quante notizie ci sono. Puoi tenerlo d'occhio (e
mettere un tetto di spesa) dalla console Anthropic.

Più il dominio, se lo compri: 10–15 € l'anno.

Se un giorno volessi risparmiare, puoi allargare l'intervallo (es. ogni ora
invece di ogni 30 minuti) cambiando una riga nel file
`.github/workflows/aggiorna.yml`: `*/30` diventa `0` (ogni ora esatta).

---

## Due cose da sapere

**I feed dai computer di GitHub.** Alcuni feed che dal tuo ambiente di prova
non si aprivano (Google News, qualche giornale) dai server di GitHub si aprono
senza problemi: hanno internet "vero". Se dopo il primo giro noti che manca
qualche testata, guarda i log della Action: dirà quali feed non ha raggiunto.

**Il contatto nell'User-Agent.** Nel file `ingest.py`, in cima, c'è una riga
con un indirizzo email di esempio (`tuo@indirizzo.it`). È buona educazione da
"robot": alcuni siti vogliono sapere chi li sta leggendo. Puoi metterci un tuo
indirizzo di contatto prima di andare online, ma non è obbligatorio.

---

## Caricare i file con Git (alternativa al trascinamento)

Se il trascinamento delle cartelle `.github` e `web` ti dà problemi, e hai
Git installato, dal terminale nella cartella del progetto:

```
git init
git add .
git commit -m "Il Vaglio"
git branch -M main
git remote add origin https://github.com/TUONOME/ilvaglio.git
git push -u origin main
```

(sostituisci `TUONOME`). Poi prosegui dal Passo 3.
