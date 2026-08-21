# VoxViva

La stessa notizia italiana, dal titolo più a sinistra a quello più a destra.

Scala a cinque posizioni, 35 testate su 44 feed, impaginazione a duello: in cima a ogni
evento il titolo più a sinistra contro il più a destra, con il lancio d'agenzia in mezzo.
Sotto, tutte le testate nelle tre colonne con l'etichetta precisa.

Le agenzie hanno un feed per sezione — ANSA ne ha sette. Il solo `topnews` dava dieci
titoli al giorno e lasciava il centro del duello vuoto per metà delle notizie: ora il
lancio d'agenzia c'è quasi sempre, ed è il riferimento asciutto contro cui si leggono gli
estremi.

---

## Partenza rapida

```powershell
cd ilvaglio-starter\v2
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

python check_feeds.py                      # 1. quali feed sono vivi
$env:ANTHROPIC_API_KEY = "sk-ant-..."      # 2. la chiave, da console.anthropic.com
python run.py                              # 3. tutto in fila
```

Il sito finisce in `web\index.html`. Doppio click e si apre.

Per vedere l'anteprima senza chiave, con i titoli veri del 17 agosto da 17 testate:

```powershell
python build_demo.py
python render.py --demo
```

---

## I file

| file | cosa fa | serve la chiave |
|---|---|---|
| `scala.py` | la scala politica e la logica degli estremi, in un posto solo | no |
| `check_feeds.py` | dice quali feed rispondono, quali sono fermi, quanti articoli hanno | no |
| `ingest.py` | legge i feed → `data/articles.json` | no |
| `cluster.py` | raggruppa, **verifica i gruppi**, scrive l'analisi → `data/events.json` | **sì** |
| `render.py` | genera `web/index.html`, un file solo, zero dipendenze | no |
| `run.py` | lancia ingest → cluster → render | sì |
| `build_demo.py` | ricostruisce l'anteprima con i dati reali già raccolti | no |

```powershell
python run.py --ore 12          # finestra più stretta, eventi più freschi
python cluster.py --no-analisi  # salta l'analisi editoriale, costa meno
python cluster.py --no-verifica # salta il controllo degli intrusi (sconsigliato)
python render.py --max 30       # più eventi in pagina
python check_feeds.py --scrivi  # aggiorna il campo "stato" in sources.json
```

Se vuoi cambiare la scala — aggiungere una casella, spostare le colonne — si tocca solo
`scala.py`. Gli altri file importano da lì.

---

## Perché è fatto così

### Il raggruppamento non usa la somiglianza fra le parole

Era il difetto della v1. Cercare i titoli lessicalmente simili (rapidfuzz, Jaccard) trova
solo gli eventi raccontati con le stesse parole, cioè quelli noiosi. Il senso del sito è
l'opposto. Un esempio vero, del 17 agosto:

> **Left** (sin. radicale): «Tutti al tavolo di Lavitola, **il conto solo a Ranucci**»
> **Nicola Porro** (des. radicale): «Il legale: "**Ranucci potrebbe aver capito**".
> Lavitola vuole trascinare giù Sigfrido?»

Stesso fascicolo, stesso giorno. A sinistra un uomo che paga per tutti, a destra un uomo
che forse sapeva. Nessun algoritmo lessicale li mette nello stesso gruppo: un modello che
capisce di cosa si parla sì.

### Il modello non vede la posizione politica quando raggruppa

Nel primo passaggio `cluster.py` gli passa solo id, titolo, ora e nome della testata.
L'etichetta è nascosta. Se la vedesse potrebbe raggruppare per schieramento invece che per
fatto, e il sito misurerebbe la propria assunzione invece della realtà. Nel secondo
passaggio l'etichetta serve, ma i gruppi sono già chiusi.

### La spina dorsale: Google News decide l'agenda, l'ANSA dà il centro

Non siamo noi a decidere quali sono le notizie principali del giorno. Lo decide un
aggregatore neutrale, **Google News**: la sua lista dei top stories è la spina dorsale del
sito. Divisione dei compiti pulita: *Google News dice QUALI sono le notizie, l'ANSA come
sono titolate al centro*.

Un evento diventa **principale** — e sale in cima, nell'ordine di Google News — solo se
contiene un item della spina dorsale **e** almeno una testata con una linea l'ha coperto.
Gli item Google News stanno in una casella a parte (`AGG`, fuori dalla scala politica): non
compaiono nelle colonne né nel duello, marcano solo che una notizia è in agenda. Se un item
d'agenda non lo riprende nessun giornale, resta da solo e non sale.

**Attenzione, due cose da verificare tu prima di andare in produzione:**

1. *Robots.* Google offre gli RSS come funzione, ma il suo `robots.txt` è restrittivo, e
   questo ambiente di prova lo blocca del tutto (non ho potuto testarlo). Dal tuo PC
   `feedparser` lo legge, ma dato quanto siamo stati attenti sul legale: verifica
   `robots.txt` e i termini di Google News prima di appoggiarci un sito pubblico. Se
   preferisci restare robots-clean, in `sources.json` la **topnews ANSA** ha anch'essa
   `"primaria": true` e fa da spina dorsale alternativa: togli GN e resti pulito.
2. *Formato.* Gli item GN sono «Titolo - Testata» e linkano a un redirect di Google, non
   all'articolo. Servono solo a selezionare l'agenda: i link che il sito mostra al lettore
   restano quelli delle testate originali.

Il filtro `MERCATO` in `ingest.py` scarta comunque i tick di borsa in ingresso (l'ho
scoperto guardando la topnews ANSA delle 8: metà erano «prezzo dell'oro a 4.443 dollari
l'oncia», «euro a 1,1572 dollari», «Tokyo -0,56%»). Colpisce solo la forma-ticker; gli
articoli di economia veri restano. Conteggio a fine run, niente sparizioni silenziose.

Struttura della pagina: **principali** in cima (agenda Google News, in ordine), poi **altri
confronti**. Tutto configurabile col flag `"primaria"`: puoi mettere due aggregatori,
tornare all'ANSA, aggiungere il topnews AGI.

### La regola di pubblicazione: solo con tutte e tre le colonne

Decisione di Simone (18/08): **se una notizia non è coperta da sinistra, centro E destra,
non si pubblica.** Manca un lato → fuori. In `render.py` la funzione `completo()` lo
impone: un evento esce solo se le tre colonne (sinistra = SR/CS, centro = C, destra =
CD/DR) sono tutte piene. Nell'anteprima del 17 agosto passano 8 eventi su 19; gli altri 11
sono scartati perché campionando pochi feed manca spesso un lato. Su un giro vero la quota
di completi è molto più alta, perché il centro (ANSA, 7 sezioni) c'è quasi sempre.

I **punti ciechi** (una sola area copre la notizia) di default non si pubblicano, coerente
con la regola. Restano disponibili come funzione opt-in — `python render.py --punti-ciechi`
— perché mostrare «cosa racconta solo una parte» è di per sé un dato (AllSides ha una
sezione Blindspot). Ma è una scelta, non il default.

### L'impaginazione: tre colonne stile AllSides

Ogni notizia è una **rassegna** a tre colonne — *Dalla Sinistra · Dal Centro · Dalla
Destra* — sul modello del "headline roundup" di AllSides. In ogni colonna un titolo
rappresentativo (il più a sinistra, il centro d'agenzia, il più a destra), la testata e il
**meter L-C-R** a cinque celle che mostra dove sta quella testata sulla scala. Sotto, la
riga «Anche:» con le altre testate della colonna, e la nota «come cambia il titolo». Il
titolo neutro in cima e la sintesi del duello danno il colpo d'occhio.

### Stesso FATTO, non stesso argomento

È l'errore che rovina un sito come questo, e ci siamo già cascati una volta: nella prima
versione dell'anteprima gli Europei di **atletica** a Birmingham e quelli di **nuoto** a
Parigi erano finiti nello stesso confronto. Il duello mostrava un titolo sul nuoto contro
un titolo sull'atletica, e non dimostrava niente.

Tre difese, in ordine di efficacia:

1. **Il modello deve dichiarare il `fatto_specifico`** di ogni gruppo: chi ha fatto cosa,
   dove, quando. Se per far entrare tutti i titoli deve scrivere una frase vaga, il gruppo
   è sbagliato. «Gli Europei di atletica» non è un fatto, è un argomento; «l'Italia chiude
   prima nel medagliere degli Europei di atletica di Birmingham il 16 agosto» sì.
2. **Il prompt porta gli esempi negativi**, non solo quelli positivi: competizioni diverse,
   città diverse, giorni diversi, ruoli invertiti (chi attacca e chi è attaccato) sono
   eventi diversi anche quando l'argomento è lo stesso. E la regola di chiusura: **nel
   dubbio, spacca**. Un evento con un solo titolo è un risultato accettabile.
3. **Un passaggio di verifica separato** rilegge ogni gruppo, confronta ogni titolo col
   `fatto_specifico` dichiarato e caccia gli intrusi, che tornano a essere eventi a sé. È
   una chiamata in più e costa pochi centesimi: è il miglior rapporto qualità-prezzo di
   tutta la pipeline, perché è l'unico controllo che il lettore non può fare al posto tuo.

Il verificatore ha istruzioni esplicite su cosa **non** deve togliere: parole diverse, tono
opposto, numeri diversi, opinione anziché cronaca. Quelle differenze sono il materiale del
sito, non rumore.

Un esempio di quello che la severità produce, sui dati veri del 17 agosto: «Ceuta» in una
giornata genera almeno tre fatti distinti — il Marocco che blocca la frontiera, Sánchez che
convoca sette ministri, un pestaggio a Barcellona che qualcuno collega a Ceuta. Sono tre
eventi. Nel confronto sul primo entrano solo L'Espresso e La Verità, che parlano davvero
della stessa cosa.

### Il modello non riscrive nessun titolo

Restituisce solo id. I titoli veri li rimette Python. Se un titolo compare sul sito è
identico a quello pubblicato. Il modello scrive tre cose sole, tutte marcate come testo
redazionale: il titolo neutro dell'evento, la frase sul duello, la nota «come cambia il
titolo».

### Il centro del duello è un lancio d'agenzia, e se non c'è si dice

Lo slot centrale cerca ANSA o AGI. Se nessuna agenzia ha battuto la notizia, il sito
mette un titolo di centro ma cambia l'etichetta in «versione di centro» invece di
«lancio d'agenzia». Un editoriale del Foglio non è un riferimento neutro e non va
spacciato per tale. Quando manca anche quello, lo slot dice esplicitamente che nessuna
testata di centro ha battuto la notizia — che è a sua volta un'informazione.

---

## METODO — la scala a cinque

| | posizione | cosa ci sta |
|---|---|---|
| `AGG` | aggregatore (fuori scala) | Google News — spina dorsale, sceglie l'agenda |
| `SR` | sinistra radicale | Il Manifesto, Left, Liberazione |
| `CS` | centro-sinistra | Repubblica, Fatto, Domani, Espresso, Unità, Fanpage, Open, HuffPost, Tirreno, Internazionale |
| `C` | centro e agenzie | ANSA, AGI, Corriere, La Stampa, Il Messaggero, Sole 24 Ore, Riformista, Linkiesta, QN, Rai News, Avvenire, **Il Dubbio** |
| `CD` | centro-destra | TGCOM24, Il Foglio, Il Giornale, Il Tempo, Mattino, Panorama, Secolo d'Italia, Gazzetta del Sud, **Italia Oggi** |
| `DR` | destra radicale | La Verità, Nicola Porro, **Libero**, Il Primato Nazionale, La Nuova Bussola |

Revisione del 18/08/2026 con riscontro su **Wikipedia** (*List of newspapers in Italy*):
Libero è salito a destra radicale; aggiunte Il Dubbio (centro, garantista) e Italia Oggi
(centro-destra, economico). Che le collocazioni abbiano una fonte terza documentata è la
difesa migliore della pagina metodo — vedi sotto.

**Cosa dichiarano.** La *linea editoriale prevalente* della testata, non il contenuto del
singolo articolo. Un giornale di sinistra può scrivere un titolo asciutto e uno di destra
un titolo misurato: il sito mostra quel singolo titolo, l'etichetta serve a collocarlo.

**Cosa non sono.** Non un punteggio, non il risultato di un'analisi quantitativa, senza
decimali. Il giorno in cui il sito scrive «Repubblica 7.2 a sinistra» ha perso, perché quel
7.2 non è difendibile.

**La proprietà editoriale è la parte solida.** Ogni testata in `sources.json` ha il campo
`proprieta`. Chi possiede un giornale è un fatto verificabile, l'etichetta politica è
un'interpretazione: pubblicare i due insieme è ciò che rende il metodo discutibile invece
che arbitrario. Alcuni fatti che vale la pena avere in pagina:

- **Il Giornale, Libero e Il Tempo** appartengono tutti e tre alla **famiglia Angelucci**.
  Il Giornale è stato comprato dalla famiglia Berlusconi nel 2023, formando un polo di
  centro-destra; nel 2025 il gruppo Toto ha preso il 40% de Il Tempo. Tre testate della
  colonna destra con un editore unico non sono tre voci indipendenti, ed è esattamente il
  genere di cosa che un lettore vuole sapere.
- **GEDI è stato venduto nel marzo 2026**: Repubblica al gruppo greco **Antenna**
  (famiglia Kyriakou), La Stampa al **gruppo SAE**. Che i due maggiori quotidiani di area
  progressista siano passati di mano nello stesso anno è materiale da pagina metodo.
- **TGCOM24** è MFE-MediaForEurope, cioè la famiglia Berlusconi.
- **Il Sole 24 Ore** è di Confindustria. **AGI** è del gruppo Eni. **Rai News** è servizio
  pubblico, con un consiglio che riflette la maggioranza parlamentare del momento.
- **Panorama e La Verità** hanno lo stesso editore (Belpietro) ma stanno in due caselle
  diverse. Lo stesso vale per **L'Unità e Il Riformista** (Romeo Editore).

### Le etichette, e chi le decide

La scala L/C/R è stata rivista il 18/08/2026 sulla lista di Simone, che ha **risolto** le
due collocazioni prima più contese:

- **La Stampa → centro** (prima la tenevo forzata a centro-destra e me n'ero lamentato nel
  codice). Coerente col fatto che fino al 2026 era GEDI, come Repubblica.
- **Il Foglio → centro-destra** (prima al centro come compromesso). Ora è una scelta
  dichiarata: liberal-conservatore, atlantista.
- **Il Messaggero → centro** (prima centro-destra). Editore Caltagirone.

Restano da spiegare nella pagina metodo un paio di scelte, non contestazioni ma
semplificazioni consapevoli:

1. **TGCOM24 in CD.** Proprietà famiglia Berlusconi (MFE). Attenzione tecnica: gran parte
   del feed è copia dei lanci ANSA quasi alla lettera — due titoli uguali nelle colonne
   centro e destra non sono due conferme indipendenti.
2. **Fanpage in CS.** Registro popolare e digitale, non quotidiano di partito. È il caso che
   dimostra il limite di un asse solo: se un giorno servono due dimensioni (linea politica ×
   registro), nasce da qui.
3. **Il Giorno «a destra» (lista di Simone) ma dentro QN.** Il Giorno fa parte del gruppo
   Monrif/QN ed entra attraverso il feed nazionale `quotidiano.net`, la cui linea condivisa
   è moderata. La classificazione a destra riguarda la testata milanese, non il desk
   nazionale: da chiarire.

**Le affinità di partito** dalla lista di Simone (Il Giornale e Il Tempo → Forza Italia,
Libero → Lega, Fanpage e l'Unità → PD, Il Fatto → M5S) sono in `sources.json` come note.
Attenzione a una cosa: Il Giornale, Il Tempo e Libero sono tutti e tre **della famiglia
Angelucci** oggi, quindi le vecchie etichette di partito (FI, Lega) contano meno della
proprietà comune, che è il fatto più forte da mettere in pagina.

**La fonte delle etichette.** Dalla revisione del 18/08/2026 ogni collocazione ha un
riscontro documentato: la voce Wikipedia *List of newspapers in Italy* e le singole voci
delle testate riportano l'orientamento politico. La pagina metodo dovrebbe dirlo
apertamente e linkare la fonte per ciascuna testata: «non è la nostra opinione, è la
classificazione comunemente documentata; dove ce ne discostiamo, lo scriviamo». È
esattamente ciò che fa AllSides con la sua metodologia pubblica, ed è la differenza fra un
progetto discutibile e uno arbitrario. Il campo `proprieta` (un fatto verificabile) e la
fonte della classificazione, affiancati, reggono qualsiasi contestazione.

Altri due punti da dichiarare, meno contesi ma imperfetti:

- **ANSA e AGI sono agenzie**, non hanno linea editoriale come un quotidiano. Nel sito
  fanno da riferimento asciutto, non da «centro politico»: la colonna si chiama «Centro e
  agenzie» per questo.
- **La Nuova Bussola Quotidiana** è cattolica tradizionalista: si posiziona su temi etici
  più che economici, e l'asse sinistra-destra la incastra male.

### Come costruire la fiducia, in ordine di sforzo

1. Due righe di motivazione pubblica per ogni testata, con la data dell'ultima revisione e
   il gruppo proprietario. Un pomeriggio di lavoro. È la differenza fra un progetto
   discutibile e uno arbitrario.
2. Un bottone «questa etichetta ti sembra sbagliata?» su ogni testata, con il conteggio
   grezzo pubblico e nessun automatismo che cambi l'etichetta.
3. Quando il traffico lo permette: sondaggio cieco sui titoli, come fa AllSides — si mostra
   un articolo senza il nome della testata e si chiede da che parte pende.

### I colori non sono quelli dei partiti

Indaco cupo → indaco chiaro → ardesia → ambra chiara → ambra cupa. In Italia il rosso è
storicamente la sinistra e l'azzurro il centro-destra: l'esatto contrario della convenzione
americana che usa AllSides. Usare colori di partito avrebbe fatto sembrare il sito
schierato prima di leggere una riga.

---

## NOTA LEGALE

**Non è un parere legale.** Prima di pubblicare su un dominio tuo, fallo leggere a un
avvocato che si occupi di diritto d'autore: due ore di consulenza.

- **Solo titoli, sempre con la testata e il link all'originale.** Nessun testo
  dell'articolo, nessun sommario riscritto, nessuna immagine dell'editore.
- **Riferimento normativo:** l'art. 15-bis della legge sul diritto d'autore (introdotto dal
  d.lgs. 177/2021, che recepisce l'art. 15 della direttiva UE 2019/790) riconosce agli
  editori un diritto connesso sull'utilizzo online delle pubblicazioni giornalistiche da
  parte dei prestatori di servizi della società dell'informazione, **escludendo
  espressamente i collegamenti ipertestuali e l'utilizzo di singole parole o di estratti
  molto brevi**. Un titolo con link ricade in quella esclusione secondo la lettura
  prevalente, ma AGCOM ha definito un quadro per le negoziazioni fra editori e piattaforme:
  se il sito cresce, la questione va riaperta.
- **Nessun paywall aggirato.** Si legge solo il feed RSS pubblico.
- **Rispetta `robots.txt`.** Il Messaggero e Il Mattino vietano il percorso del feed:
  restano fuori finché non si trova un feed che l'editore autorizzi. Non è una barriera
  tecnica da superare, è un no.
- **Metti la tua email nella costante `UA`** di `ingest.py` e `check_feeds.py` prima di
  andare in produzione.
- **Una richiesta di rimozione si esegue.** Pagina di contatto visibile, e si toglie la
  testata da `sources.json`.
- **Una passata all'ora** è cortese e sufficiente.

---

## Stato dei feed — controllo del 17/08/2026

Verificato da un datacenter: alcuni editori bloccano gli IP dei server ma rispondono da una
connessione domestica. **Rilancia `check_feeds.py` dal tuo PC** prima di dare per morto un
feed.

### Vivi e confermati (17)

Left `SR` · Open, Fanpage, Domani, L'Espresso `CS` · ANSA, Il Foglio, Il Riformista,
Linkiesta, QN Quotidiano Nazionale `C` · TGCOM24, Il Tempo, Secolo d'Italia, Panorama `CD`
· La Verità, Nicola Porro, Il Primato Nazionale `DR`

Tre url che vale la pena annotare, perché non sono quelli che uno prova per primo:

- **ANSA** ha un feed per sezione, tutti nella forma
  `ansa.it/sito/notizie/SEZIONE/SEZIONE_rss.xml`. Confermati: `topnews`, `cronaca`,
  `mondo`, `politica`, `sport`. In `sources.json` ci sono anche `economia` e `cultura`, da
  verificare. Sono sette righe con la stessa `etichetta` («ANSA»): la deduplica per chiave
  del titolo in `ingest.py` evita di contare due volte lo stesso lancio che compare in
  topnews e nella sezione.
- **Il Foglio** sta su `naxos.ilfoglio.it/api/v5/rss/stories/latest`. L'indirizzo si scopre
  solo dalla loro pagina `/rss/`: nessun pattern standard funziona.
- **Il Tempo** su `iltempo.it/rss.xml`, non su `/rss/home.xml` come nella v1.

Perché le sezioni delle agenzie contano: con il solo `topnews` il centro del duello era
vuoto per metà delle notizie, e su alcune il sito dichiarava un punto cieco che non
esisteva. La violenza sessuale in corso Como del 17 agosto sembrava battuta solo da due
testate di destra; l'ANSA l'aveva battuta, in `cronaca`, con un titolo che identifica
l'accusato come «un uomo conosciuto in discoteca» dove La Verità scrive «un uomo dell'Est
Europa». Senza il feed di sezione quel confronto — che è esattamente il confronto per cui
il sito esiste — andava perso e diventava un falso punto cieco.

### Da sistemare

| testata | problema | cosa fare |
|---|---|---|
| **Il Giornale** `CD` | nessun url funzionante: `/rss.xml`, `/feed/`, `/feed.xml`, `/feed.rss`, `/rss/home.xml`, `/rss/politica.xml` danno tutti 404 | cercare nel sorgente della homepage il tag `application/rss+xml`. Manca una delle testate principali della colonna destra |
| **Libero** `CD` | `/rss.xml` va in timeout dal server, ma non dà 404 | probabilmente l'url è giusto: riprovare da casa |
| **Corriere** `C` | il vecchio `xml2.corriereobjects.it/rss/homepage.xml` risponde ma restituisce articoli di **maggio 2024** | feed congelato da due anni che non dà errore, il caso peggiore. `check_feeds.py` ora lo marca `CONGELATO` |
| **L'Unità** `CS` | risponde, ultimo articolo del **7 luglio 2026** | stesso caso: congelato ma silenzioso |
| **Il Manifesto** `SR` | il feed contiene l'edizione cartacea (cultura, spettacoli) con 1-2 giorni di ritardo; `/sezione/politica/feed` esiste ma è vuoto | serve un feed di cronaca. Senza, la casella `SR` regge su Left da sola |
| **Il Tirreno** `CS` | url da trovare | |
| **Avvenire** `C` | `/rss` restituisce una pagina articolo, non un feed | vale la pena cercarlo: sui migranti e sulla povertà tiene posizioni che non stanno né a destra né a sinistra |
| **Messaggero, Mattino** `CD` | `robots.txt` vieta il percorso | vedi nota legale: si rispetta |
| **Repubblica, La Stampa, Il Fatto, Il Sole, Rai News, HuffPost** | bloccati dalla rete del server | ricontrollare da casa, quasi certamente funzionano |

---

## Cosa manca per essere un sito vero

1. **Il Giornale, Libero, Corriere e Repubblica.** Senza le due testate più lette d'Italia e
   il maggiore quotidiano di centro-destra il confronto è squilibrato: adesso la colonna
   destra è tenuta in piedi da Il Tempo, Secolo, Panorama e La Verità, e quella di sinistra
   da Open, Fanpage e Domani. Sono voci legittime ma non quelle che leggono la maggior parte
   degli italiani.
2. **Un feed di cronaca per Il Manifesto.** La casella della sinistra radicale sta in piedi
   su Left da sola, e Left pubblica pochi pezzi al giorno. Un duello fra estremi in cui
   l'estremo sinistro manca metà dei giorni non funziona.
3. **Un archivio.** Adesso ogni giro sovrascrive tutto. Un file al giorno in
   `data/storico/AAAA-MM-GG.json` costa dieci righe e apre le pagine permanenti per evento,
   che sono quelle che la gente condivide.
4. **La pagina metodo**, quella descritta sopra, con la tabella delle proprietà.
5. **Automatizzare.** Una GitHub Action ogni ora che lancia la pipeline e fa commit di
   `web/index.html` su GitHub Pages: gratis, online, senza server.
6. **Ricontrollo sui gruppi.** Il modello a volte unisce eventi vicini. Una pagina privata
   dove approvi o spezzi i gruppi prima della pubblicazione vale più di qualsiasi ritocco al
   prompt.

---

## Costi

Con 35 testate attive arrivano 250-400 titoli nelle 24 ore. Il raggruppamento è una
chiamata da qualche migliaio di token in ingresso, l'analisi una più piccola. Centesimi per
giro; anche girando ogni ora, pochi euro al mese. La spesa vera è il dominio.

---

## Prima di pubblicare

- [ ] `check_feeds.py` dal tuo PC, e i feed rotti sistemati
- [ ] la tua email nella costante `UA` di `ingest.py` e `check_feeds.py`
- [ ] pagina metodo con le quattro etichette contese messe per prime
- [ ] tabella pubblica testata → area → gruppo proprietario
- [ ] pagina contatti visibile, per le richieste di rimozione
- [ ] letto il punto sull'art. 15-bis con un avvocato
- [ ] guardato [bias-news.com](https://www.bias-news.com/), che fa una cosa simile con 40
      testate: serve a capire dove differenziarsi
