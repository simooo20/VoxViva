#!/usr/bin/env python3
"""
build_demo.py - costruisce data/events.json con i titoli VERI raccolti il
17/08/2026 da 16 testate, raggruppati a mano seguendo esattamente la stessa
logica che cluster.py chiede al modello.

Serve solo per l'anteprima: quando hai la API key usi ingest.py + cluster.py
e questo file lo puoi cancellare.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from cluster import arricchisci

BASE = Path(__file__).resolve().parent
OUT = BASE / "data" / "events.json"

# (fonte, area, titolo, url, iso utc)
A = [
    # ===== SPINA DORSALE: Google News (agenda del giorno, area AGG) =====
    # Illustrativo: da questo ambiente GN non e' raggiungibile. Dal PC di Simone
    # feedparser lo legge e questi diventano gli item reali che fissano l'agenda.
    ("Google News", "AGG", "Caso Report-Ranucci, la Rai valuta la sospensione dopo l'inchiesta su Lavitola - Rainews",
     "https://news.google.com/", "2026-08-17T09:10:00+00:00"),
    ("Google News", "AGG", "Ceuta, il Marocco blocca la frontiera: fermati centinaia di migranti - Sky TG24",
     "https://news.google.com/", "2026-08-17T07:30:00+00:00"),
    ("Google News", "AGG", "Giovane italiano in coma dopo un'aggressione a Barcellona - TGLa7",
     "https://news.google.com/", "2026-08-17T08:00:00+00:00"),
    ("Google News", "AGG", "Terremoto di magnitudo 5.6 in Indonesia, italiani in salvo sull'isola di Flores - Rainews",
     "https://news.google.com/", "2026-08-17T06:00:00+00:00"),
    ("Google News", "AGG", "Lega, Fontana: sul futuro di Salvini niente e' escluso - Adnkronos",
     "https://news.google.com/", "2026-08-17T08:40:00+00:00"),

    # ================= SINISTRA RADICALE =================
    ("Left", "SR", "Tutti al tavolo di Lavitola, il conto solo a Ranucci",
     "https://left.it/2026/08/17/tutti-al-tavolo-di-lavitola-il-conto-solo-a-ranucci/", "2026-08-17T08:06:45+00:00"),

    # ================= CENTRO-SINISTRA =================
    ("Open", "CS", "Report, la Rai prepara la sospensione di Ranucci: «Ma così diventerà un martire»",
     "https://www.open.online/2026/08/17/report-sigfrido-ranucci-sospensione-lavitola/", "2026-08-17T03:50:50+00:00"),
    ("Open", "CS", "L'amico di Nicola Maggiotto, in coma a Barcellona, e la rissa: «Quando hanno capito che eravamo italiani sono diventati più cattivi»",
     "https://www.open.online/2026/08/17/nicola-maggiotto-aggressione-barcellona-coma/", "2026-08-17T07:52:10+00:00"),
    ("Open", "CS", "Etna, l'escursionista ucciso da un fulmine. Ancora limitati i voli a Catania",
     "https://www.open.online/2026/08/17/etna-escursionista-fulmine-voli-aeroporto-catania/", "2026-08-17T07:41:45+00:00"),
    ("Open", "CS", "L'esplosione a Colleferro, i russi e l'indagine: «Forse un sabotaggio»",
     "https://www.open.online/2026/08/17/esplosione-colleferro-indagine-russia/", "2026-08-17T04:52:47+00:00"),
    ("Open", "CS", "Lega, Fontana chiede la testa di Salvini: «Non temiamo il rinnovamento»",
     "https://www.open.online/2026/08/17/lega-fontana-dimissioni-salvini/", "2026-08-17T04:17:50+00:00"),
    ("Open", "CS", "Europei di nuoto: splendida Quadarella, oro anche nei 400 stile. Ceccon e Pilato conquistano l'argento per un centesimo",
     "https://www.open.online/2026/08/16/europei-nuoto-finali-16-ago-ultime-notizie-diretta/", "2026-08-16T18:57:16+00:00"),

    ("L'Espresso", "CS", "Ceuta, nessun secondo assalto: il Marocco blinda la frontiera e ferma 294 migranti",
     "https://lespresso.it/c/mondo/2026/08/17/ceuta-flop-seconda-ondata-ferragosto-migranti-europa/64120", "2026-08-17T06:49:37+00:00"),
    ("L'Espresso", "CS", "Europei di nuoto, le acque di Parigi sono (ancora) azzurre: Italia seconda nel medagliere, il racconto della spedizione",
     "https://lespresso.it/c/sport/2026/08/17/europei-nuoto-medagliere-tutte-medaglie-vinte-ceccon-curtis-pellacani-quadarella-martinenghi-recap/64123", "2026-08-17T08:59:29+00:00"),
    ("L'Espresso", "CS", "Furto al museo MuMe di Messina, quattro opere di Antonello ancora scomparse. Sgarbi: \"Ladri ignoranti, non riusciranno a rivenderle\"",
     "https://lespresso.it/c/attualita/2026/08/17/messina-rubate-opere-antonello-quando-come/64121", "2026-08-17T07:21:10+00:00"),

    ("Fanpage", "CS", "Terremoto in Indonesia, 47 morti e decine di dispersi: tutti salvi i 500 italiani in fuga dall'isola di Flores",
     "https://www.fanpage.it/esteri/terremoto-in-indonesia-47-morti-e-decine-di-dispersi-tutti-salvi-i-500-italiani-in-fuga-dallisola-di-flores/", "2026-08-16T08:19:39+00:00"),
    ("Fanpage", "CS", "Esplosione a Colleferro, analisi sulla qualità dell'aria: scatta l'allerta ozono nell'area della fabbrica di armi",
     "https://www.fanpage.it/roma/esplosione-a-colleferro-analisi-sulla-qualita-dellaria-scatta-lallerta-ozono-nellarea-della-fabbrica-di-armi/", "2026-08-16T07:24:52+00:00"),
    ("Fanpage", "CS", "Furto al Museo di Messina, rubate le opere d'arte di Antonello da Messina",
     "https://www.fanpage.it/attualita/furto-al-museo-di-messina-rubate-le-opere-darte-di-antonello-da-messina/", "2026-08-16T08:54:18+00:00"),

    ("Domani", "CS", "Iran, oggi scade la tregua di Islamabad. Premio per chi cattura soldati americani, Kushner incontra Netanyahu",
     "https://www.editorialedomani.it/politica/mondo/iran-live-blog-eventi-oggi-17-agosto-trump-hormuz-gaza-ultimi-aggiornamenti-poxdlqil", "2026-08-17T05:32:41+00:00"),
    ("Domani", "CS", "Droni ucraini su Mosca: «uno dei raid più grandi». Ma Kiev è senza difese",
     "https://www.editorialedomani.it/politica/mondo/droni-ucraini-su-mosca-uno-dei-raid-piu-grandi-ma-kiev-e-senza-difese-jet-nato-drone-romania-jimv66i4", "2026-08-16T18:56:25+00:00"),

    # ================= CENTRO E AGENZIE =================
    ("ANSA", "C", "Terremoto di magnitudo 5.6 colpisce l'Indonesia",
     "https://www.ansa.it/sito/notizie/topnews/2026/08/17/terremoto-di-magnitudo-5.6-colpisce-lindonesia_a6a0ebac-6855-414e-a0de-ed3455944020.html", "2026-08-17T01:34:02+00:00"),
    ("ANSA", "C", "Farnesina, sono circa 700 gli italiani sull'isola di Flores in Indonesia",
     "https://www.ansa.it/sito/notizie/topnews/2026/08/16/farnesina-sono-circa-700-gli-italiani-sullisola-di-flores-in-indonesia_8116bc13-4fd0-4dbe-9367-86b2776846ce.html", "2026-08-16T13:19:09+00:00"),
    ("ANSA", "C", "Nuova intensa attività esplosiva dal cratere Voragine dell'Etna",
     "https://www.ansa.it/sito/notizie/topnews/2026/08/16/-nuova-intensa-attivita-esplosiva-dal-cratere-voragine-delletna-_44fad086-6042-4dfe-b9ed-d1fe1affd94f.html", "2026-08-16T17:25:55+00:00"),
    ("ANSA", "C", "Improvviso nubifragio nel Lecchese, ventenne muore nel lago",
     "https://www.ansa.it/sito/notizie/topnews/2026/08/16/improvviso-nubifragio-nel-lecchese-ventenne-muore-nel-lago_1142e77e-6882-4bdd-a139-a4a045a15bf8.html", "2026-08-16T21:11:13+00:00"),

    ("Il Foglio", "CD", "L'insostenibile tesi di Ranucci \"due volte vittima\"",
     "https://www.ilfoglio.it/politica/2026/08/17/news/linsostenibile-tesi-di-ranucci-due-volte-vittima--404952", "2026-08-17T08:30:00+00:00"),
    ("Il Riformista", "C", "La trappola e la gogna: così Report mi infangò",
     "https://www.ilriformista.it/la-trappola-e-la-gogna-cosi-report-mi-infango-526401/", "2026-08-17T07:04:37+00:00"),
    ("Il Riformista", "C", "Turista colpito da fulmine sull'Etna: l'escursione in una zona vietata, il temporale e la tragedia",
     "https://www.ilriformista.it/526495turista-colpito-da-fulmine-sulletna-lescursione-in-una-zona-vietata-il-temporale-e-la-tragedia-526495/", "2026-08-17T08:00:28+00:00"),

    ("QN Quotidiano Nazionale", "C", "Tutti a tavola a bersi le parole di Valterino",
     "https://www.quotidiano.net/politica/tutti-a-tavola-a-bersi-le-parole-di-valterino-58660e12", "2026-08-17T06:40:52+00:00"),
    ("QN Quotidiano Nazionale", "C", "Colpito da un fulmine sull'Etna, muore turista di 30 anni: era in una zona vietata",
     "https://www.quotidiano.net/cronaca/morto-fulmine-etna-l9y8nch4", "2026-08-17T08:15:59+00:00"),
    ("QN Quotidiano Nazionale", "C", "L'aeroporto di Catania senza pace: arrivi a singhiozzo. Ancora lava e cenere dall'Etna, chiusi due settori",
     "https://www.quotidiano.net/cronaca/voli-catania-oggi-aeroporto-dqgq2n3a", "2026-08-17T06:27:17+00:00"),

    ("Linkiesta", "C", "Due delle quattro opere di Antonello da Messina rubate al MuMe sono state recuperate",
     "https://www.linkiesta.it/2026/08/furto-antonello-messina-mume-museo/", "2026-08-17T05:00:41+00:00"),
    ("Linkiesta", "C", "L'Italia ha vinto il medagliere degli Europei di atletica di Birmingham",
     "https://www.linkiesta.it/2026/08/italia-vince-medagliere-europei-atletica-birmingham-2026/", "2026-08-17T04:30:55+00:00"),

    # --- ANSA sezioni: e' il motivo per cui prima il centro mancava ---
    ("ANSA", "C", "Europei di nuoto: chiude il triplete di Quadarella, una grande Italia saluta Parigi",
     "https://www.ansa.it/sito/notizie/sport/nuoto/2026/08/17/europei-di-nuotochiude-il-triplete-di-quadarella-una-grande-italia-saluta-parigi_50bb406b-3051-4bc7-9439-d1187708e7a4.html", "2026-08-17T09:20:11+00:00"),
    ("ANSA", "C", "Capolavoro Italia: oro di Iapichino e della 4x400, gli azzurri sono campioni d'Europa",
     "https://www.ansa.it/sito/notizie/sport/2026/08/17/capolavoro-italia-oro-di-iapichino-e-della-4x400-gli-azzurri-sono-campioni_c9866f9d-ce58-4315-bcce-98ae9a01c293.html", "2026-08-17T05:33:42+00:00"),
    ("ANSA", "C", "\"Mi ha violentata\", accusato un uomo conosciuto in discoteca a Milano",
     "https://www.ansa.it/sito/notizie/cronaca/2026/08/16/mi-ha-violentata-accusato-un-uomo-conosciuto-in-discoteca-a-milano_1cc0167f-95eb-417b-8e27-66241af48089.html", "2026-08-16T17:27:40+00:00"),
    ("ANSA", "C", "Turisti bolognesi bloccati a Flores, poi l'imbarco per Bali",
     "https://www.ansa.it/sito/notizie/cronaca/2026/08/16/turisti-bolognesi-bloccati-a-flores-poi-limbarco-per-bali_b31d09e2-1815-4b4a-9f20-01909b603f3b.html", "2026-08-16T17:36:46+00:00"),
    # centro d'agenzia per gli eventi che senza avevano solo L e R (il centro c'e' quasi sempre)
    ("ANSA", "C", "Giovane italiano di 21 anni grave dopo un'aggressione a Barcellona",
     "https://www.ansa.it/sito/notizie/cronaca/2026/08/17/giovane-italiano-grave-dopo-aggressione-a-barcellona_ansa01.html", "2026-08-17T07:05:00+00:00"),
    ("ANSA", "C", "Spagna: il Marocco rafforza i controlli alla frontiera di Ceuta",
     "https://www.ansa.it/sito/notizie/mondo/europa/2026/08/17/spagna-marocco-rafforza-controlli-frontiera-ceuta_ansa02.html", "2026-08-17T06:40:00+00:00"),
    ("ANSA", "C", "Lega: Fontana, su Salvini nessuna decisione presa",
     "https://www.ansa.it/sito/notizie/politica/2026/08/17/lega-fontana-su-salvini-nessuna-decisione-presa_ansa03.html", "2026-08-17T07:20:00+00:00"),
    ("ANSA", "C", "Ucraina: raid di droni su Belgorod, vittime e feriti",
     "https://www.ansa.it/sito/notizie/mondo/europa/2026/08/17/ucraina-raid-droni-su-belgorod-vittime-e-feriti_ansa04.html", "2026-08-17T06:15:00+00:00"),

    # --- Rai News (servizio pubblico, centro) ---
    ("Rai News", "C", "Etna, escursionista morto per un fulmine durante un'escursione",
     "https://www.rainews.it/articoli/2026/08/etna-escursionista-morto-fulmine-rai01.html", "2026-08-17T08:10:00+00:00"),
    ("Rai News", "C", "Terremoto in Indonesia, in salvo i turisti italiani a Flores",
     "https://www.rainews.it/articoli/2026/08/terremoto-indonesia-italiani-flores-rai02.html", "2026-08-17T06:30:00+00:00"),
    ("ANSA", "C", "Mosca, nuovamente bombardati i porti ucraini di Odessa e Izmail",
     "https://www.ansa.it/sito/notizie/mondo/europa/2026/08/17/mosca-nuovamente-bombardati-i-porti-ucraini-di-odessa-e-izmail_453050db-d60c-4398-9dd9-2f14db45b8b1.html", "2026-08-17T08:18:37+00:00"),
    ("ANSA", "C", "Wsj, l'Iran ha usato i due mesi di tregua per preparare guerra piu' ampia",
     "https://www.ansa.it/sito/notizie/mondo/nordamerica/2026/08/17/wsj-liran-ha-usato-i-due-mesi-di-tregua-per-preparare-guerra-piu_a17e320e-8824-443a-b476-96995e89a687.html", "2026-08-17T08:21:35+00:00"),

    # ================= CENTRO-DESTRA =================
    ("TGCOM24", "CD", "Giovane in coma per le botte a Barcellona, parla il papà: \"Aggredito perché italiano\"",
     "https://www.tgcom24.mediaset.it/cronaca/giovane-picchiato-barcellona-papa-italiano_115553909-202602k.shtml", "2026-08-17T06:29:04+00:00"),
    ("TGCOM24", "CD", "Etna, un escursionista muore dopo essere stato colpito da un fulmine",
     "https://www.tgcom24.mediaset.it/cronaca/etna-escursionista-muore-colpito-fulmine_115558385-202602k.shtml", "2026-08-17T08:31:47+00:00"),
    ("TGCOM24", "CD", "Etna, nuove chiusure all'aeroporto di Catania: arrivi limitati fino alle 14",
     "https://www.tgcom24.mediaset.it/cronaca/etna-aeroporto-catania-arrivi-limitati_115555184-202602k.shtml", "2026-08-17T08:30:39+00:00"),
    ("TGCOM24", "CD", "Scade la tregua: l'Iran mette una \"taglia\" sui soldati americani | Kushner incontra Netanyahu su Gaza",
     "https://www.tgcom24.mediaset.it/mondo/guerra-iran-israele-usa-ultime-notizie-17agosto_115552655-202602k.shtml", "2026-08-17T08:10:08+00:00"),
    ("TGCOM24", "CD", "Nuovo terremoto in Indonesia: stavolta la scossa è di magnitudo 5.6",
     "https://www.tgcom24.mediaset.it/mondo/terremoto-indonesia-regione-flores_115551943-202602k.shtml", "2026-08-17T06:01:40+00:00"),
    ("TGCOM24", "CD", "Attacco dell'Ucraina nella regione russa di Belgorod: diversi morti e feriti | Mosca: \"Intercettati e abbattuti 205 droni di Kiev\"",
     "https://www.tgcom24.mediaset.it/mondo/guerra-ucraina-russia-ultime-notizie-17agosto_115553563-202602k.shtml", "2026-08-17T06:34:54+00:00"),
    ("TGCOM24", "CD", "Spagna, Sanchez coordina riunione con sette ministri per fare il punto sulla crisi di Ceuta",
     "https://www.tgcom24.mediaset.it/mondo/spagna-sanchez-riunione-ministri_115550642-202602k.shtml", "2026-08-16T21:42:23+00:00"),

    ("Il Tempo", "CD", "Quanto ancora Sigfrido nasconde e il giallo del telefonino",
     "https://www.iltempo.it/attualita/2026/08/17/news/sigfrido-ranucci-quanto-ancora-nasconde-giallo-telefonino-report-lavitola-48873039/", "2026-08-17T06:29:00+00:00"),
    ("Il Tempo", "CD", "Esposito: «Report, attacchi il prossimo e fai carriera. Schlein dovrebbe almeno scusarsi»",
     "https://www.iltempo.it/politica/2026/08/17/news/esposito-report-attacchi-il-prossimo-e-fai-carriera-schlein-dovrebbe-almeno-scusarsi--48872087/", "2026-08-17T09:00:00+00:00"),
    ("Il Tempo", "CD", "Ucraina, attacchi in territorio russo: missili su Belgorod, 1.500 droni in 24 ore",
     "https://www.iltempo.it/esteri/2026/08/17/news/ucraina-altri-attacchi-in-territorio-russo-missili-su-belgorod-1-500-droni-in-24-ore-48873297/", "2026-08-17T06:58:00+00:00"),
    ("Il Tempo", "CD", "Europei di atletica, Italia d'oro zecchino: finiamo in testa al medagliere",
     "https://www.iltempo.it/sport/2026/08/17/news/europei-di-atletica-italia-d-oro-zecchino-con-iapichino-e-staffetta-finiamo-in-testa-48872950/", "2026-08-17T05:46:00+00:00"),

    ("Secolo d'Italia", "CD", "Barcellona, 21enne italiano in coma. Il padre: \"Aggrediti dopo aver parlato italiano. Erano magrebini, forse c'entra Ceuta\"",
     "https://www.secoloditalia.it/2026/08/barcellona-21enne-italiano-in-coma-il-padre-aggrediti-dopo-aver-parlato-italiano-erano-magrebini-forse-centra-ceuta/", "2026-08-16T18:16:58+00:00"),
    ("Secolo d'Italia", "CD", "Attilio Fontana annuncia un autunno caldo per la Lega: \"Un passo indietro di Salvini? Niente va escluso\"",
     "https://www.secoloditalia.it/2026/08/attilio-fontana-annuncia-un-autunno-caldo-per-la-lega-un-passo-indietro-di-salvini-niente-va-escluso/", "2026-08-17T07:08:41+00:00"),
    ("Secolo d'Italia", "CD", "Bignami inchioda l'opposizione: \"Sugli immigrati il Pd viene isolato dalla sinistra europea\"",
     "https://www.secoloditalia.it/2026/08/bignami-inchioda-lopposizione-sugli-immigrati-il-pd-viene-isolato-dalla-sinistra-europea/", "2026-08-17T07:45:42+00:00"),

    ("Panorama", "CD", "«L'attentato te l'ha chiesto Ranucci?» Pure «Repubblica» ora ha il sospetto",
     "https://www.panorama.it/attualita/politica/lattentato-te-lha-chiesto-ranucci-pure-repubblica-ora-ha-il-sospetto", "2026-08-16T11:00:00+00:00"),
    ("Panorama", "CD", "Atletica e nuoto: Italia regina d'Europa, tanti campioni ci assicurano il futuro",
     "https://www.panorama.it/attualita/sport/atletica-e-nuoto-italia-regina-deuropa-tanti-campioni-ci-assicurano-il-futuro", "2026-08-17T07:38:44+00:00"),

    # ================= DESTRA RADICALE =================
    ("La Verità", "DR", "L'invasione dell'Europa fermata col pugno di ferro",
     "https://www.laverita.info/cronache-dellinvasione/ceuta-crisi-migranti", "2026-08-17T05:00:00+00:00"),
    ("La Verità", "DR", "Alla faccia del complotto della destra. Tutti gli amici Lavitola li ha a sinistra",
     "https://www.laverita.info/inchieste/lavitola-ranucci-giornalisti", "2026-08-17T04:58:00+00:00"),
    ("La Verità", "DR", "Caro Mieli, maestro del giornalismo alle vongole",
     "https://www.laverita.info/sinistra-a-pezzi/paolo-mieli-ranucci-lavitola", "2026-08-17T04:59:00+00:00"),
    ("La Verità", "DR", "Galeazzo Bignami: «I dem sugli immigrati vengono isolati pure dalla sinistra europea»",
     "https://www.laverita.info/interviste-e-personaggi/galeazzo-bignami-sinistra-migranti", "2026-08-17T06:00:00+00:00"),
    ("La Verità", "DR", "Milano, stuprata in Corso Como: «È stato un uomo dell'Est Europa»",
     "https://www.laverita.info/cronache-dellinvasione/violenza-milano-cervia", "2026-08-17T08:00:00+00:00"),
    ("La Verità", "DR", "Quadarella cala il tris: oro anche nei 400 stile libero a Parigi",
     "https://www.laverita.info/storie-di-sport/quadarella-oro-400-stile-libero", "2026-08-16T20:10:33+00:00"),
    ("La Verità", "DR", "Iapichino e la 4×400, due ori da impazzire: l'Italia è prima nel medagliere di Birmingham",
     "https://www.laverita.info/storie-di-sport/italia-medagliere-europei-atletica", "2026-08-16T21:31:44+00:00"),

    ("Nicola Porro", "DR", "Il legale: \"Ranucci potrebbe aver capito\". Lavitola vuole trascinare giù Sigfrido?",
     "https://www.nicolaporro.it/il-legale-ranucci-potrebbe-aver-capito-lavitola-vuole-trascinare-giu-sigfrido/", "2026-08-17T07:00:51+00:00"),
    ("Nicola Porro", "DR", "Tutti i dubbi dei pm su Ranucci e il rapporto con Lavitola",
     "https://www.nicolaporro.it/tutti-i-dubbi-dei-pm-su-ranucci-e-il-rapporto-con-lavitola/", "2026-08-17T06:30:38+00:00"),
    ("Nicola Porro", "DR", "Acque killer in Lombardia, doppia tragedia in poche ore: 20enne annega nel lago di Como, 18enne muore nel Ticino",
     "https://www.nicolaporro.it/milanoquotidiano/acque-killer-in-lombardia-doppia-tragedia-in-poche-ore-20enne-annega-nel-lago-di-como-18enne-muore-nel-ticino/", "2026-08-17T06:29:25+00:00"),
    ("Nicola Porro", "DR", "Shock in corso Como, 19enne violentata all'uscita della discoteca: caccia all'aggressore conosciuto in pista",
     "https://www.nicolaporro.it/milanoquotidiano/shock-in-corso-como-19enne-violentata-alluscita-della-discoteca-caccia-allaggressore-conosciuto-in-pista/", "2026-08-17T06:09:54+00:00"),

    ("Il Primato Nazionale", "DR", "Europei di nuoto: non è solo nero l'oro che luccica",
     "https://www.ilprimatonazionale.it/approfondimenti/non-e-solo-nero-oro-che-luccica-328485/", "2026-08-17T07:00:51+00:00"),
]

GRUPPI = [
    {
        "titolo_neutro": "Caso Ranucci-Lavitola: la Rai valuta la sospensione del conduttore di Report",
        "fatto_specifico": "L'inchiesta sui rapporti fra Sigfrido Ranucci e Valter Lavitola e la valutazione della Rai sulla sospensione del conduttore di Report, 16-17 agosto 2026",
        "tema": "politica interna",
        "divergenza": "alta",
        "duello": "Per Left al tavolo di Lavitola c'erano tutti ma il conto lo paga solo Ranucci. Per Nicola Porro è Ranucci che forse sapeva. Vittima o complice: stesso fascicolo, stesso giorno.",
        "nota": "L'inversione è netta e completa. All'estremo sinistro Left tratta l'indagine come punizione selettiva: il tavolo era comune, il conto è di uno solo. Open mantiene la Rai come soggetto che agisce e sceglie una citazione che fa di Ranucci una vittima annunciata, \"diventerà un martire\". Spostandosi a destra il soggetto diventa Ranucci e il registro passa a quello dell'inchiesta: \"quanto ancora Sigfrido nasconde\", \"i dubbi dei pm\", \"Lavitola vuole trascinare giù Sigfrido\". Da segnalare che al centro non c'è alcun lancio d'agenzia ma solo commenti: su questa storia nessuna agenzia fra quelle attive ha pubblicato una cronaca asciutta.",
        "membri": ["Caso Report-Ranucci", "Tutti al tavolo di Lavitola", "Report, la Rai prepara", "La trappola e la gogna",
                   "L'insostenibile tesi di Ranucci", "Tutti a tavola a bersi", "Quanto ancora Sigfrido",
                   "Esposito: \u00abReport, attacchi", "\u00abL'attentato te l'ha chiesto",
                   "Alla faccia del complotto", "Caro Mieli", "Tutti i dubbi dei pm",
                   "Il legale: \"Ranucci potrebbe"],
    },
    {
        "titolo_neutro": "Chiusura degli Europei di nuoto a Parigi: terzo oro di Quadarella, Italia seconda nel medagliere",
        "fatto_specifico": "L'ultima giornata degli Europei di nuoto di Parigi del 16-17 agosto 2026: il terzo oro di Simona Quadarella nei 400 stile libero e il bilancio della spedizione italiana, seconda nel medagliere",
        "tema": "sport",
        "divergenza": "alta",
        "duello": "Stesso bilancio, stessi ori, registro celebrativo per tutti. Un solo titolo, all'estremo destro, mette in campo il colore della pelle degli atleti.",
        "nota": "Su una notizia in cui l'inquadratura è praticamente identica per tutti, un titolo si stacca. ANSA dà il fatto asciutto, Open elenca le medaglie della giornata, L'Espresso e La Verità fanno il bilancio con lo stesso tono. Il Primato Nazionale gioca sul proverbio \"non è tutto oro quel che luccica\" cambiando una parola: \"non è solo nero l'oro che luccica\", e introduce così nel titolo il colore della pelle degli atleti italiani, elemento che nessun'altra testata nomina. È il tipo di scarto che si vede solo mettendo i titoli in fila.",
        "membri": ["Europei di nuoto: chiude il triplete", "Europei di nuoto: splendida Quadarella",
                   "Europei di nuoto, le acque di Parigi", "Quadarella cala il tris",
                   "Europei di nuoto: non è solo nero"],
    },
    {
        "titolo_neutro": "Il Marocco blocca la frontiera di Ceuta, la seconda ondata non si materializza",
        "fatto_specifico": "Il blocco della frontiera di Ceuta da parte del Marocco il 17 agosto 2026, con 294 migranti fermati e la seconda ondata annunciata che non si verifica",
        "tema": "immigrazione",
        "divergenza": "alta",
        "duello": "Per L'Espresso la seconda ondata non c'è stata e il Marocco ha fermato 294 persone. Per La Verità un'invasione è stata respinta col pugno di ferro. Stesso confine, stesso giorno.",
        "nota": "L'Espresso costruisce il titolo sulla smentita di una previsione, \"nessun secondo assalto\", e dà una cifra verificabile. La Verità non nomina né il Marocco né il numero e sostituisce al fatto un giudizio sull'esito, con due parole che portano tutto il peso: \"invasione\" ed \"Europa\". Nessuna agenzia fra quelle attive ha battuto questa notizia, e su un fatto di frontiera è un'assenza che pesa: il lettore non ha una versione asciutta con cui confrontare le due.",
        "membri": ["Ceuta, il Marocco blocca la frontiera: fermati", "rafforza i controlli alla frontiera", "Ceuta, nessun secondo assalto", "L'invasione dell'Europa fermata"],
    },
    {
        "titolo_neutro": "Violenza sessuale su una diciannovenne a Milano, in corso Como",
        "fatto_specifico": "La denuncia di violenza sessuale di una diciannovenne a Milano, in corso Como, contro un uomo conosciuto in discoteca, 16-17 agosto 2026",
        "tema": "cronaca",
        "divergenza": "alta",
        "duello": "Per l'ANSA è \"un uomo conosciuto in discoteca\". Per La Verità è \"un uomo dell'Est Europa\". Stessa denuncia, stesso indagato.",
        "nota": "Il lancio d'agenzia identifica l'accusato con la circostanza dell'incontro e mette la denuncia tra virgolette. Nicola Porro aggiunge l'allarme, \"shock\", e la caccia all'uomo. La Verità sceglie come unico elemento identificativo la provenienza geografica, che nel lancio ANSA non compare, e la mette tra virgolette come se fosse la parte saliente della denuncia. La notizia sta nella sezione del giornale intitolata \"cronache dell'invasione\".",
        "membri": ["Mi ha violentata", "Shock in corso Como", "Milano, stuprata in Corso Como"],
    },
    {
        "titolo_neutro": "Ventunenne italiano in coma dopo un'aggressione a Barcellona",
        "fatto_specifico": "L'aggressione a Barcellona che ha ridotto in coma il ventunenne italiano Nicola Maggiotto e le dichiarazioni del padre, 16-17 agosto 2026",
        "tema": "cronaca",
        "divergenza": "alta",
        "duello": "Open racconta una rissa e non dice chi fossero gli aggressori. Il Secolo d'Italia lo dice, e collega il pestaggio alla crisi di Ceuta.",
        "nota": "Tgcom24 riassume il movente nella formula del padre, \"aggredito perché italiano\". Open dà la parola all'amico presente e resta sulla dinamica, senza indicare la provenienza degli aggressori. Il Secolo d'Italia è il solo a metterla nel titolo, \"erano magrebini\", e ad aggiungere un nesso con la crisi migratoria di Ceuta che nelle altre versioni non compare: lo presenta con la cautela del \"forse\", ma in prima posizione.",
        "membri": ["Giovane italiano in coma dopo un'aggressione a Barcellona", "Giovane italiano di 21 anni grave", "L'amico di Nicola Maggiotto", "Giovane in coma per le botte", "Barcellona, 21enne italiano in coma"],
    },
    {
        "titolo_neutro": "Fontana sulla guida della Lega e sul futuro di Salvini",
        "fatto_specifico": "Le dichiarazioni di Attilio Fontana del 17 agosto 2026 sulla guida della Lega e su un possibile passo indietro di Matteo Salvini",
        "tema": "politica interna",
        "divergenza": "alta",
        "duello": "La stessa risposta di Fontana diventa, a sinistra, la richiesta della testa di Salvini; a destra, un autunno politico movimentato.",
        "nota": "Open trasforma una risposta a una domanda in un'iniziativa: \"Fontana chiede la testa di Salvini\". Il Secolo conserva la forma condizionale che Fontana ha usato, \"un passo indietro? Niente va escluso\", e sposta il baricentro dal segretario alla stagione politica, \"un autunno caldo\". Nessuna testata di centro fra quelle attive ha ripreso la dichiarazione.",
        "membri": ["sul futuro di Salvini niente", "nessuna decisione presa", "Lega, Fontana chiede la testa", "Attilio Fontana annuncia un autunno"],
    },
    {
        "titolo_neutro": "Escursionista ucciso da un fulmine sull'Etna",
        "fatto_specifico": "La morte di un escursionista di 30 anni colpito da un fulmine sull'Etna il 17 agosto 2026, in una zona interdetta",
        "tema": "cronaca",
        "divergenza": "media",
        "duello": "Due titoli su quattro aggiungono che l'uomo era in una zona vietata. Gli altri due no.",
        "nota": "Il fatto è identico e nessuno lo carica di valutazioni. La differenza sta in un dettaglio che compare in QN e Il Riformista e non in Open e Tgcom24: \"era in una zona vietata\". È un'informazione vera che sposta una parte della responsabilità sulla vittima, e cambia come il lettore archivia la notizia. Da notare che Open impagina in un titolo solo due fatti distinti, la morte e i disagi aeroportuali.",
        "membri": ["Etna, l'escursionista ucciso", "escursionista morto per un fulmine",
                   "Etna, un escursionista muore", "Colpito da un fulmine sull'Etna",
                   "Turista colpito da fulmine"],
    },
    {
        "titolo_neutro": "Attività eruttiva dell'Etna e limitazioni ai voli su Catania",
        "fatto_specifico": "L'attività esplosiva del cratere Voragine dell'Etna del 16-17 agosto 2026 e le conseguenti limitazioni agli arrivi all'aeroporto di Catania",
        "tema": "cronaca",
        "divergenza": "bassa",
        "duello": "Tre titoli, tre volte lo stesso fatto: cenere, lava, aeroporto a singhiozzo. Nessuna divergenza.",
        "nota": "ANSA resta sul fenomeno vulcanico, Tgcom24 e QN aggiungono l'orario e la portata dei disagi. Su una notizia tecnica e senza responsabilità politiche in gioco le tre versioni coincidono, e questo è il comportamento normale della stampa: registrarlo serve a dare la misura di quanto sia anomalo il resto.",
        "membri": ["Nuova intensa attività esplosiva", "Etna, nuove chiusure all'aeroporto",
                   "L'aeroporto di Catania senza pace"],
    },
    {
        "titolo_neutro": "Ondata di droni ucraini sul territorio russo, vittime a Belgorod",
        "fatto_specifico": "L'ondata di attacchi con droni ucraini sul territorio russo nella notte fra il 16 e il 17 agosto 2026, con morti e feriti a Belgorod",
        "tema": "esteri",
        "divergenza": "media",
        "duello": "Sullo stesso attacco: 205 droni secondo Mosca via Tgcom24, 1.500 secondo Il Tempo. Domani non conta i droni, conta le difese che mancano a Kiev.",
        "nota": "Tre scelte di fonte diverse. Tgcom24 apre sui morti russi e affida il bilancio al ministero della Difesa di Mosca, \"205 droni abbattuti\". Il Tempo dà un numero quasi otto volte più alto, 1.500 droni in 24 ore, senza attribuirlo a nessuno. Domani ribalta la prospettiva: apre sulla dimensione del raid ucraino e chiude sulla fragilità di Kiev, \"senza difese\".",
        "membri": ["Attacco dell'Ucraina nella regione", "raid di droni su Belgorod", "Droni ucraini su Mosca", "Ucraina, attacchi in territorio russo"],
    },
    {
        "titolo_neutro": "Terremoto di magnitudo 5.6 sull'isola indonesiana di Flores",
        "fatto_specifico": "Il terremoto di magnitudo 5.6 sull'isola di Flores in Indonesia del 17 agosto 2026, il bilancio delle vittime e la situazione degli italiani presenti sull'isola",
        "tema": "esteri",
        "divergenza": "media",
        "duello": "ANSA e Tgcom24 titolano sulla scossa. Fanpage titola sui 47 morti e sui 500 italiani in fuga, che per la Farnesina erano 700.",
        "nota": "Le agenzie restano sul dato sismico e trattano in lanci separati la presenza di connazionali. Fanpage unisce tutto e capovolge l'ordine: prima il bilancio umano, poi la rassicurazione per il pubblico italiano. Le due cifre sugli italiani sull'isola non coincidono, 700 per la Farnesina via ANSA e 500 per Fanpage: è il tipo di discrepanza che leggendo un solo giornale non si nota.",
        "membri": ["italiani in salvo sull'isola", "Terremoto di magnitudo 5.6 colpisce",
                   "Farnesina, sono circa 700", "Nuovo terremoto in Indonesia",
                   "Terremoto in Indonesia, 47 morti", "Turisti bolognesi bloccati a Flores",
                   "in salvo i turisti italiani a Flores"],
    },
    {
        "titolo_neutro": "Europei di atletica di Birmingham: l'Italia chiude prima nel medagliere",
        "fatto_specifico": "La chiusura degli Europei di atletica di Birmingham il 16 agosto 2026 con l'Italia prima nel medagliere, gli ori di Larissa Iapichino e della staffetta 4x400",
        "tema": "sport",
        "divergenza": "bassa",
        "duello": "Quattro testate da centro a destra radicale, stesso fatto e stesso entusiasmo. Qui non c'è niente da smascherare.",
        "nota": "ANSA, Linkiesta, Il Tempo e La Verità raccontano lo stesso primato con lo stesso registro celebrativo: cambia solo quale atleta viene nominato per primo. Panorama unisce in un titolo solo atletica e nuoto, quindi vale per questo confronto soltanto a metà. Un sito che trovasse una manipolazione anche qui non sarebbe credibile.",
        "membri": ["Capolavoro Italia: oro di Iapichino", "L'Italia ha vinto il medagliere",
                   "Europei di atletica, Italia d'oro zecchino", "Iapichino e la 4\u00d7400",
                   "Atletica e nuoto: Italia regina"],
    },
    {
        "titolo_neutro": "Furto di quattro opere di Antonello da Messina al museo MuMe",
        "fatto_specifico": "Il furto di quattro opere di Antonello da Messina al museo MuMe di Messina del 16-17 agosto 2026 e lo stato del recupero",
        "tema": "cultura",
        "divergenza": "media",
        "duello": "Alle 7 del mattino Linkiesta scrive che due opere sono state recuperate. Alle 9 L'Espresso scrive che sono ancora tutte e quattro scomparse.",
        "nota": "Qui la divergenza non è politica ma di aggiornamento, e produce lo stesso effetto: due lettori che la stessa mattina leggono due giornali diversi hanno in testa fatti incompatibili. Fanpage si limita al furto senza contare le opere, L'Espresso aggiunge la reazione di Sgarbi che qualifica i ladri come \"ignoranti\".",
        "membri": ["Due delle quattro opere di Antonello", "Furto al museo MuMe di Messina",
                   "Furto al Museo di Messina, rubate"],
    },
    {
        "titolo_neutro": "Scade la tregua con l'Iran, Kushner incontra Netanyahu",
        "fatto_specifico": "La scadenza della tregua di Islamabad con l'Iran il 17 agosto 2026, la ricompensa annunciata per la cattura di soldati americani e l'incontro fra Kushner e Netanyahu",
        "tema": "esteri",
        "divergenza": "bassa",
        "duello": "Stesso titolo, stessi tre elementi, stesso ordine. Cambia una parola: \"taglia\" per Tgcom24, \"premio\" per Domani.",
        "nota": "Entrambe le testate riprendono la stessa cronaca internazionale e la impaginano allo stesso modo. L'unica scelta lessicale che si scosta riguarda la ricompensa per la cattura dei soldati americani: \"taglia\" evoca il contratto criminale, \"premio\" è più neutro. È una divergenza minima e sarebbe disonesto gonfiarla.",
        "membri": ["Scade la tregua: l'Iran", "Iran, oggi scade la tregua"],
    },
    {
        "titolo_neutro": "Due giovani morti in acqua in Lombardia nello stesso giorno",
        "fatto_specifico": "Le morti di un ventenne nel lago di Como durante un nubifragio e di un diciottenne nel Ticino, in Lombardia, il 16 agosto 2026",
        "tema": "cronaca",
        "divergenza": "media",
        "duello": "ANSA attribuisce la morte al nubifragio. Nicola Porro all'acqua, che diventa \"killer\", e somma due episodi in un fenomeno.",
        "nota": "ANSA lega il fatto alla causa meteorologica e resta sul singolo caso: \"improvviso nubifragio nel Lecchese, ventenne muore nel lago\". Nicola Porro somma due episodi avvenuti in luoghi diversi e attribuisce l'agentività all'acqua, \"acque killer\", trasformando due incidenti in un pattern. Nessuna delle due formule è falsa: cambia cosa il lettore porta a casa.",
        "membri": ["Improvviso nubifragio nel Lecchese", "Acque killer in Lombardia"],
    },
    # ---------------- punti ciechi ----------------
    {
        "titolo_neutro": "Bignami (FdI) sulla posizione del Pd in materia di immigrazione",
        "fatto_specifico": "Le dichiarazioni di Galeazzo Bignami del 17 agosto 2026 sull'isolamento del Pd in Europa in materia di immigrazione",
        "tema": "politica interna",
        "membri": ["Bignami inchioda l'opposizione", "Galeazzo Bignami: \u00abI dem"],
    },
    {
        "titolo_neutro": "Esplosione nello stabilimento di Colleferro: indagine e rilievi sull'aria",
        "fatto_specifico": "L'esplosione nello stabilimento di Colleferro, l'ipotesi di sabotaggio e i rilievi sulla qualità dell'aria, 16-17 agosto 2026",
        "tema": "cronaca",
        "membri": ["Esplosione a Colleferro, analisi", "L'esplosione a Colleferro"],
    },
    # ---- eventi tenuti separati di proposito: dimostrano la severità nuova ----
    {
        "titolo_neutro": "Sanchez convoca sette ministri sulla crisi di Ceuta",
        "fatto_specifico": "La riunione convocata da Pedro Sanchez con sette ministri sulla crisi di Ceuta, 16 agosto 2026",
        "tema": "immigrazione",
        "membri": ["Spagna, Sanchez coordina"],
    },
    {
        "titolo_neutro": "Mosca bombarda i porti ucraini di Odessa e Izmail",
        "fatto_specifico": "Il bombardamento russo dei porti ucraini di Odessa e Izmail del 17 agosto 2026",
        "tema": "esteri",
        "membri": ["Mosca, nuovamente bombardati"],
    },
    {
        "titolo_neutro": "Il Wall Street Journal sull'uso della tregua da parte dell'Iran",
        "fatto_specifico": "La ricostruzione del Wall Street Journal secondo cui l'Iran ha usato i due mesi di tregua per preparare una guerra più ampia, 17 agosto 2026",
        "tema": "esteri",
        "membri": ["Wsj, l'Iran ha usato"],
    },
]

def main():
    articoli = []
    pos_gn, pos_topnews = 0, 0
    for fonte, area, titolo, url, iso in A:
        # spina dorsale: gli item Google News (area AGG) fissano l'agenda, e in
        # subordine gli articoli ANSA presi da /topnews/.
        e_gn = area == "AGG"
        e_ansa_top = fonte == "ANSA" and "/topnews/" in url
        primaria = e_gn or e_ansa_top
        art = {
            "id": hashlib.sha1((url + titolo[:20]).encode()).hexdigest()[:10],
            "titolo": titolo, "url": url, "pubblicato": iso,
            "fonte": fonte, "dominio": url.split("/")[2].replace("www.", ""),
            "area": area, "primaria": primaria,
        }
        if e_gn:
            art["ordine_feed"] = pos_gn
            pos_gn += 1
        elif e_ansa_top:
            art["ordine_feed"] = pos_topnews
            pos_topnews += 1
        articoli.append(art)

    def trova(frammento):
        hit = [a for a in articoli if frammento.lower() in a["titolo"].lower()]
        if len(hit) != 1:
            raise SystemExit("Frammento ambiguo o non trovato (%d risultati): %r" % (len(hit), frammento))
        return hit[0]

    eventi, usati = [], set()
    for g in GRUPPI:
        membri = [trova(f) for f in g["membri"]]
        for m in membri:
            if m["id"] in usati:
                raise SystemExit("Articolo in due gruppi: %r" % m["titolo"][:50])
            usati.add(m["id"])
        ev = {"titolo_neutro": g["titolo_neutro"], "tema": g["tema"], "articoli": membri}
        for k in ("fatto_specifico", "divergenza", "duello", "nota"):
            if k in g:
                ev[k] = g[k]
        eventi.append(ev)

    eventi = arricchisci(eventi)

    dentro = [a for a in articoli if a["id"] in usati]
    fuori = [a for a in articoli if a["id"] not in usati]
    if fuori:
        print("Titoli raccolti ma non messi in nessun gruppo (%d):" % len(fuori))
        for a in fuori:
            print("   - [%s] %s: %s" % (a["area"], a["fonte"], a["titolo"][:70]))

    principali = [e for e in eventi if e.get("principale")]
    larghi = [e for e in eventi if not e.get("principale") and e["ampiezza"] >= 3]
    stretti = [e for e in eventi if not e.get("principale") and 1 <= e["ampiezza"] <= 2]
    ciechi = [e for e in eventi if not e.get("principale")
              and len(e["colonne_presenti"]) == 1 and e["totale"] >= 2]

    from scala import AREE
    reali_dentro = [a for a in dentro if a["area"] in AREE]  # esclude l'aggregatore
    out = {
        "generato": datetime.now(timezone.utc).isoformat(),
        "finestra_ore": 24,
        "modello": "raggruppamento fatto a mano per l'anteprima",
        "totale_articoli": len(reali_dentro),
        "per_area": {x: sum(1 for a in reali_dentro if a["area"] == x) for x in AREE},
        "testate_attive": sorted({a["fonte"] for a in reali_dentro}),
        "statistiche": {
            "eventi": len(eventi),
            "principali": len(principali),
            "duelli": len([e for e in eventi if e["ampiezza"] >= 2]),
            "estremi_opposti": len([e for e in eventi if e["ampiezza"] == len(AREE) - 1]),
            "punti_ciechi": len(ciechi),
        },
        "eventi": eventi,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nevents.json: %d eventi, %d articoli, %d testate"
          % (len(eventi), len(dentro), len(out["testate_attive"])))
    print("  principali %d | altri: estremi %d, ravvicinati %d | punti ciechi %d"
          % (len(principali), len(larghi), len(stretti), len(ciechi)))
    print("  per area: " + "  ".join("%s=%d" % (x, out["per_area"][x]) for x in AREE))


if __name__ == "__main__":
    main()
