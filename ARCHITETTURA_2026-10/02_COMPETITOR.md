# 02 - COMPETITOR, LIMITI UFFICIALI BETFAIR, LIBRERIE E TABELLA DI PARITA' (08/10/2026)

Autore: delegato Sonnet (piano di architettura). Data: 08/10/2026. Solo fonti pubbliche; ogni affermazione porta la
sigla della fonte (elenco con URL in fondo, sezione 9). «deduzione:» = mia inferenza, con la sua base. Citazioni del
nostro codice come `file:riga` (righe lette di persona oggi). Numeri nostri: da `07_MISURE_OGGI.md` (altro delegato) salvo
quelli gia' nel repo con fonte (`SCHEMI_BOT/sistema/MISURE_2026-10-02.md`, `ARCHITETTURA_2026-10/strumenti/misure/uscite/`).

## 0. Metodo e limiti della ricerca (cosa e' stato letto davvero)

- **Documentazione Betfair**: il sito Confluence (`betfair-developer-docs.atlassian.net`) e' reso in JavaScript e WebFetch
  restituisce pagine vuote. Ho letto il testo vero delle pagine dall'API pubblica di Confluence
  (`https://betfair-developer-docs.atlassian.net/wiki/rest/api/content/<id>?expand=body.view`, ids in sezione 9) e gli
  articoli del centro assistenza dall'API pubblica Zendesk
  (`https://support.developer.betfair.com/api/v2/help_center/en-us/articles/<id>.json`). Sono le stesse pagine
  `docs.developer.betfair.com` / `support.developer.betfair.com`; le URL citate sono quelle web.
- **Bet Angel**: il manuale ufficiale PDF (copyright 2025, 11.583 righe di testo estratte con `pdftotext -layout`) e' stato
  scaricato e letto; le citazioni `BA-PDF r.N` sono righe del testo estratto (rieseguibile: scaricare il PDF e lanciare
  `pdftotext -layout Bet-angel-user-guide.pdf ba.txt`).
- **Geeks Toy, Cymatic, Fairbot, Gruss**: pagine prodotto e manuali online letti direttamente.
- **Bfexplorer**: `bfexplorer.net` NON e' raggiungibile ne' dal mio PC ne' da WebFetch (connessione rifiutata). Ho solo
  frammenti di motore di ricerca (URL `bfexplorer.net/...` indicizzati) e il README GitHub del BOT SDK: la scheda e' piu'
  magra e lo dichiara. `fairbot.com` con `www.` ha il certificato sbagliato: letto senza `www.`.
- **Traderline**: sito ufficiale e pagine «education» letti; le pagine non dichiarano ne' latenze ne' architettura.
- **Non e' stato misurato niente sui competitor**: tutti i numeri di velocita' sono DICHIARAZIONI dei produttori.
- Nessuna chiamata a Betfair o ad API-Football; nessun codice di produzione eseguito; solo lettura del repo.

---

## 1. Schede competitor

Legenda: «dich.» = dichiarato dal produttore nella fonte citata; «n.d.» = non dichiarato nelle pagine che ho letto (non
vuol dire che non esista).

### 1.1 Bet Angel Professional (Bet Angel Limited, UK)

| Voce | Cosa dice la fonte |
|---|---|
| Prodotto/versione | Guida utente 2025 per Bet Angel Professional (BA-PDF r.1-4); esistono anche Trader, Basic, Betdaq (BA-HOME). Sistema operativo e requisiti hardware: n.d. nel manuale (il testo nomina Windows solo nelle istruzioni su data e ora, r.789; il sito ha anche una pagina `/apple/` che non ho letto, BA-PRO). |
| Architettura desktop | Applicazione desktop unica; **Guardian** e' la finestra multi-mercato (BA-PDF r.1254, 4584). Piu' finestre (ladder, one-click, grafici) staccabili su piu' monitor (BA-PDF r.1285-1286, 2491). Processi interni: n.d. |
| Stream vs polling | Entrambi. Polling di default; **Exchange Streaming** attivabile in Impostazioni > Comunicazioni (BA-PDF r.8908-8916). «Da quando Betfair ha introdotto lo streaming nel 2016 consigliamo di usarlo» (BA-PDF r.4730). |
| Frequenze dichiarate | Polling: minimo **200 ms** (BA-PDF r.2141-2142, 8913, 9954). Streaming: refresh della schermata fino a **20 ms**, «10 volte piu' veloce del polling» (BA-PDF r.9956-9960). Opzione «Refresh every: Update» = aggiorna appena arriva un messaggio; se non arriva nulla in 500 ms rinfresca comunque per tenere vivi grafici e Servants (BA-PDF r.1231-1236, 9965-9966, 11113-11116). Guardian ha un suo refresh indipendente; per l'automazione avanzata consigliato 20 ms (BA-PDF r.2148-2150). |
| Latenze dichiarate | Indicatori di «responsiveness» in ms per prezzi e scommesse; in streaming sostituiti dalla parola «Streaming» (BA-PDF r.9893-9903). Nessun valore ms ordine->risposta dichiarato (n.d.). Home page: «prezzi dieci volte piu' veloci con lo streaming Betfair e la comunicazione specializzata» (BA-HOME). |
| Mercati monitorabili | Guardian: «regole su 50 mercati al secondo a 20 ms» (BA-PDF r.4732-4734, calcolo del produttore). In streaming c'e' «una restrizione a **1000** mercati imposta da Betfair» (BA-PDF r.5281, 10264). **Attenzione**: la documentazione Betfair dice 200 mercati per sottoscrizione «di serie» (sezione 3); la guida di Bet Angel dice 1000. Non e' una contraddizione dimostrata (il limite per app key si alza su richiesta, vedi nota in 3.1), ma la cifra 1000 e' del produttore. |
| Ordini | One-click e **ladder** (BA-PDF indice r.1-100; BA-PRO). Offset a tick o a percentuale (BA-PDF r.1895); **Fill or Kill** = timer SOFTWARE: cancella dopo N secondi (0 s = abbina quanto c'e' ora e cancella il resto) (BA-PDF r.1897-1925); **batch di offset** (offset parziale durante il fill) (BA-PDF r.2151-2162); **stop loss e trailing stop** a tick/% (BA-PDF r.2045-2090), con la nota che gli stop non si portano dal pre-gara all'in-play (BA-PDF r.2051); **greening/hedge/cash-out** (BA-PDF r.1582, 2018-2026); **dutching** avanzato e bookmaking (BA-PDF indice r.87-93); persistenza «At in-play»: cancella (default) / Keep / Take SP (BA-PDF r.1784-1800); **posizione stimata in coda (EPIQ)** (BA-PDF r.9082-9084). |
| Transazioni | Contatore delle transazioni/ora in basso; «il limite orario e' fissato da Betfair, oltre si paga» (BA-PDF r.9905-9913). |
| Grafici | Grafici avanzati in streaming con indicatori (BA-PDF r.1526, indice); colonne/grafici su valori storici memorizzati (BA-PDF r.1697-1717, 2754); 20 liste di storia per selezione (v1.50, BA-PDF r.11120). |
| Automazione | **Automation / Servants** (regole a trigger, centinaia di modelli) (BA-HOME, BA-PRO); **Guardian** esegue le regole su molti mercati; **Excel** (lettura prezzi, scommesse da foglio, trading automatico da foglio) (BA-PDF indice r.116-139); **Bet Angel API**: operazioni JSON chiamabili da un'applicazione sullo stesso PC/rete, su una porta (BA-PDF r.9749-9760, 8550-8555). |
| Registrazione/replay | **Practice mode**: dati veri di mercato, scommesse abbinate LOCALMENTE, simula il cross-matching Betfair, Take-SP e Keep Bets (BA-PDF r.816-830); avvertenza: uso prolungato puo' far sospendere l'account Betfair (BA-PDF r.837). Replay di mercati storici: **non trovato** nel manuale (grep `replay` / `Market Replay`: solo le «liste storiche» dei valori). |
| Storico locale | File di log e diagnostica (BA-PDF r.8556); storico dei valori nelle History List (sopra). Altro n.d. |
| Riconnessione | Il manuale tratta errori di login (BA-PDF r.780-830) e la riconnessione ai dati corse TPD (BA-PDF r.9618-9623); la ripresa dello stream (initialClk/clk) n.d. |
| Risorse | n.d. nel manuale. Consiglia di chiudere programmi in background, rete cablata (BA-PDF r.9916-9930). |
| P&L | Calcolo locale (obbligatorio con lo streaming) (BA-PDF r.8932-8942). |
| Prezzo | Professional: 1 giorno 1,50 GBP; 1 mese 29,99 GBP; 3 mesi 59,99 GBP; 6 mesi 99,99 GBP; 12 mesi 149,99 GBP (BA-BUY). Prova gratuita (BA-HOME). |

### 1.2 Geeks Toy (Talented Mavericks Ltd, UK)

| Voce | Cosa dice la fonte |
|---|---|
| Architettura | Applicazione Windows (7, 8, 10; CPU 1,6 GHz single core, 1 GB RAM, 20 MB disco) (GT-DL); versione per Betfair, Betdaq, Matchbook (GT-HOME). Dal 2009 (GT-FEAT). |
| Stream vs polling | Il manuale (pagine Introduzione, Ladder, Place Bets, Staking & Tools, API Settings Manager, Market & API Status, ricerca testo `stream`) descrive SOLO polling: gruppi di chiamate (Bets, Prices, Complete Prices, Traded Volume, External Bets, Account Funds), frequenza da **150 ms a 20.000 ms**, «MPC» (chiamate parallele massime, 1-5), «Max Weighted Calls Per Second» 5-20; default 11 chiamate/s (GT-API). Parola `stream` non trovata nelle 11 pagine lette. deduzione: il manuale online e' pre-streaming o non aggiornato; non posso dire se oggi Geeks Toy usi lo Stream API. |
| Latenze dichiarate | «Lightning fast» (GT-HOME) senza numeri. Soglia errore API configurabile 500-2000 ms; da 3 chiamate in ritardo in su «problemi di connessione» (GT-STATUS). |
| Ordini | One-click sul ladder (si clicca sulla quantita' disponibile al prezzo) (GT-LADDER); stake per liquidita' o % del bank; **Fill or Kill** (timer: se non abbinata entro il tempo, cancella anche il residuo) e **Tick Offset** (GT-STAKING); stop loss globale con opzione **Trailing** (1 tick per tick a favore) (GT-STAKING); **OCO** (entry, exit, stop condizionato; exit parziale riduce lo stop) (GT-OCO); persistenza Cancel/Keep/Take SP, anche per ordine da menu destro (GT-LADDER); hedge dell'intero mercato con un clic (GT-STATUS); dutching e bookmaking (GT-FEAT). |
| Ladder/grafici | Ladder verticale con barra dei prezzi 1.01-1000, centratura, **grafici avanzati** «tra i piu' personalizzabili», Market Overview (GT-LADDER, GT-FEAT). |
| Automazione | Audio Alerts Manager, Shortcut Key Manager, Race Time Manager (indice manuale GT-MAN). Motore a regole/Excel: non trovato nelle pagine lette. |
| Practice mode | «Training Mode» completo con denaro finto (GT-FEAT). |
| Multi-mercato | «quanti mercati vuoi» (GT-FEAT); numero massimo n.d. |
| Prezzo | Licenza 3 mesi 20 GBP; 12 mesi 60 GBP; prova 14 giorni; versioni Betdaq/Matchbook gratuite (GT-BUY, GT-HOME). |

### 1.3 Fairbot (Binteko)

| Voce | Cosa dice la fonte |
|---|---|
| Architettura | Applicazione Windows (installer 9,18 MB, v5.14, news 11/08/2026) (FB-DL, FB-HOME). |
| Stream vs polling | Il registro modifiche cita una «**modalita' Stream API**» (v5.1: «risolto un problema che impediva l'apertura dei mercati in Stream API mode») (FB-NEW). Frequenze, conflation, numero mercati: **n.d.**. |
| Ordini | Griglia e **ladder** con profondita' completa, grafico dei prezzi, volume per prezzo, click singolo e drag&drop; **offset** automatico dopo l'abbinamento, **Stop Loss**, **Hedged bets**, **Repeat on Success** (ripete il trade N volte), **Fill or Kill**, **Weight of Money**, **Cash-out** (singolo e mercato, ripartizione libera del profitto), **Dutching e Bookmaking** con profitto per selezione indipendente (FB-HOME). |
| Grafici | Grafico Betfair, grafico proprio, candele, Market Overview, indicatori (Stochastic, RSI, WoM) (FB-HOME). |
| Automazione | «Advanced Automation»: regole di strategia assegnate ai mercati; v5.14 ha l'azione «Set Variable (Selection Expression)» e una lista strategie ricercabile (FB-NEW, FB-HOME). |
| Simulazione | «Simulation/Training Mode»: emula Betfair con scommesse virtuali (FB-HOME). |
| Multi-mercato | Market Watch List aggiorna piu' mercati in parallelo; ricerca per faccette (FB-HOME). |
| Rete | v5.12: risolto lo sfarfallio via Remote Desktop (FB-NEW): il prodotto viene usato anche su desktop remoto. Riconnessione n.d. |
| Prezzo | 12 mesi 85 EUR; 6 mesi 44,99 EUR; 3 mesi 24,99 EUR; 1 mese 9,99 EUR; prova 15 giorni (FB-ORDER, FB-HOME). |

### 1.4 Cymatic Trader (Cymatic Ltd, UK; «Advanced Cymatic Trader»)

| Voce | Cosa dice la fonte |
|---|---|
| Architettura | Applicazione desktop (setup.exe), lingue inglese, portoghese, russo (CY-FEAT). |
| Stream vs polling | **Streaming di default** in tutte le versioni recenti; polling minimo **200 ms** (CY-POLL, CY-APIREF). Conflation impostabile: **0 ms = ogni variazione subito**; consiglia 200-500 ms su PC lenti o fuori dal Regno Unito (CY-STREAM). «Refresh GUI» minimo/massimo: combina gli aggiornamenti nel PC; override automatico che mette in cache i dati se il PC e' ancora occupato col messaggio precedente (CY-STREAM). |
| Latenze dichiarate | Nessun valore assoluto; **API Monitor** mostra durate round-trip, avvisa a schermo e via e-mail, **sospende il trading** se la durata supera una soglia (default 3500 ms in polling, timeout 30.000 ms) (CY-APIREF, CY-FEAT). |
| Ordini | Griglia e ladder one-click, **PIQ** (posizione in coda stimata, «primi a mostrarla»), tasti rapidi da tastiera, **Tick Offset**, **Stop Loss** (trailing incluso), **Fill or Kill**, **Greening/cash-out**, persistenza «At In-Play», Net Stake/Free-Bet (CY-FEAT, indice CY-STREAM). |
| Automazione | Robot di trading integrato nel ladder, **Excel** (prezzi, scommesse da foglio, robot da foglio), Managed Markets (Guardian), Racing Autopilot (CY-FEAT). |
| Grafici | Grafici avanzati con indicatori, trendline magnetiche (CY-FEAT). |
| Practice | Training Mode (CY-FEAT). |
| Altro | Football Odds Predictor (CY-FEAT); Live Video; accounting (storico scommesse/estratti) (CY-FEAT). |
| Prezzo | Annuale 99,99 -> 59,99 GBP; 6 mesi 59,99 -> 35,99; mensile 10,99 -> 6,69; prova 14 giorni (la pagina mostra due cifre per piano, la seconda dopo una freccia: non dichiara quale sia in vigore) (CY-PRICE). |

### 1.5 Bfexplorer (Belo Soft) - scheda magra (sito non raggiungibile)

| Voce | Cosa dice la fonte |
|---|---|
| Architettura | Applicazione .NET + **BOT SDK** (librerie .NET: client API Betfair REST e streaming, servizi di dominio, framework per eseguire strategie e monitorare mercati e scommesse; piu' di 30 trigger per bot; esempi C#, F#, VB) (BX-SDK). Tre interfacce utente (ladder, esecuzione bot) (BX-SEARCH). |
| Stream | Tutorial su REST e streaming API; «quando un nuovo mercato entra nell'exchange la sottoscrizione lo riceve automaticamente; unico limite: **200 mercati per sottoscrizione**» (BX-SEARCH, snippet di `bfexplorer.net/Articles/...`). |
| Ordini/bot | Dutching, chiusura posizioni, **essere primi in coda**, tick offset, drip feeding, trailing stop loss, «piu' di dieci altri bot» (BX-SEARCH). |
| Monitoraggio | P&L in tempo reale, chiusura di posizione singola/mercato/tutte (BX-SEARCH). |
| Prezzi (snippet motore di ricerca di `bfexplorer.net/Subscribe`, NON letti sulla pagina) | Community: ladder e 1 mercato con bot; Basic: fino a 3 mercati senza bot; Professional: mercati illimitati e bot. Cifre riportate dal motore: Basic 5 GBP/mese o 50/anno; Professional 30 GBP/mese o 300/anno; sconti per membri attivi della community. Prova 7 giorni (BX-SEARCH). Da verificare sulla pagina viva. |
| Latenze, requisiti, replay, registrazione | **n.d. (non raggiungibile)**. |

### 1.6 Traderline

| Voce | Cosa dice la fonte |
|---|---|
| Cos'e' | «Software di trading professionale per gli exchange sportivi e di previsione, ora gratuito per tutti»; Windows, macOS, iOS; **gratuito, senza abbonamento** (TL-HOME). Dal 2026 supporta anche Polymarket (TL-HOME, TL-SEARCH; deduzione: la versione Betfair e' lo storico, la novita' e' il secondo exchange). |
| Funzioni Betfair | Griglia e ladder, grafici «expert», click singolo, calcolo automatico del rischio, **Cashout Mode** (profitto uguale su tutti gli esiti), **Freebet Mode**, pulsante **Trade** (chiude la posizione), P&L in tempo reale, multi-mercato, calcolatore dutching e hedge (TL-EDU). Stop: la guida «ladder» suggerisce di piazzare in anticipo l'ordine di uscita; **uno stop loss software non e' dichiarato** (TL-EDU, TL-SEARCH). |
| Architettura, stream, latenze, risorse, practice, replay | **n.d.** nelle pagine pubbliche («reserva i dettagli ad altre risorse»). |

### 1.7 Gruss Betting Assistant (Gruss Software, UK) - pertinente per il replay

| Voce | Cosa dice la fonte |
|---|---|
| Funzioni | Click singolo su tutti e 3 i prezzi back/lay, profitto potenziale continuo, cash-out a un clic, dutching, **ladder a profondita' completa**, **tick offset con stop loss «scorrevole»**, aggiornamento prezzi e scommesse da **Excel**, integrazione dati TPD (GR-PAGE). |
| **Market Replay** | «Rigioca mercati storici degli ultimi **5 anni**» (GR-PAGE); e' un'opzione a pagamento (GR-PRICE). E' l'unico competitor in elenco che dichiara un replay di mercato vero. |
| Prezzo | Mensile 6 (9 con Market Replay), annuale 60 (100 con Market Replay); il simbolo di valuta nella pagina e' illeggibile (deduzione: sterline, sito UK) (GR-PRICE). |
| Stream/latenze | n.d. nelle pagine lette (sito con copyright 2013). |

---

## 2. Sintesi comparativa (solo cio' che e' dichiarato)

| Voce | Bet Angel | Geeks Toy | Fairbot | Cymatic | Bfexplorer | Traderline | Gruss |
|---|---|---|---|---|---|---|---|
| Stream API | si' (opzionale) | n.d. (manuale solo polling) | si' («Stream API mode») | si' (default) | si' | n.d. | n.d. |
| Refresh minimo dichiarato | stream 20 ms / «Update»; polling 200 ms | polling 150 ms | n.d. | conflation 0 ms; polling 200 ms | n.d. | n.d. | n.d. |
| Fill or Kill | timer software | timer software | si' | si' | n.d. | n.d. | n.d. |
| Tick offset / offset | si' (+ batch) | si' | si' | si' | si' | n.d. | si' (con stop scorrevole) |
| Stop / trailing | si' | si' | stop si' | si' | trailing si' | n.d. | si' |
| Greening/cash-out | si' | si' (hedge mercato) | si' | si' | chiusura posizioni | si' | si' |
| Dutching | si' | si' | si' | n.d. | si' | calcolatore | si' |
| Persistenza in-play | Keep/Take SP | Keep/Take SP | n.d. | si' | n.d. | n.d. | n.d. |
| Posizione in coda (PIQ) | si' (EPIQ) | n.d. | n.d. | si' | «primi in coda» | n.d. | n.d. |
| Excel | si' | n.d. | n.d. | si' | n.d. | n.d. | si' |
| Regole/bot | Automation, Servants | n.d. | Advanced Automation | robot | BOT SDK, >30 trigger | n.d. | n.d. |
| API locale per codice | si' (JSON, porta locale) | n.d. | n.d. | n.d. | SDK .NET | n.d. | n.d. |
| Practice | si' (matching locale, cross-matching, Take SP) | si' | si' | si' | n.d. | n.d. | n.d. |
| Replay storico | non trovato | n.d. | n.d. | n.d. | n.d. | n.d. | si' (5 anni, a pagamento) |
| Monitor di rete | indicatori di risposta | API status | n.d. | **API Monitor + pausa trading + e-mail** | n.d. | n.d. | n.d. |
| Prezzo | 12,50-29,99 GBP/mese | 20/60 GBP per 3/12 mesi | 85 EUR/anno | 59,99-99,99 GBP/anno (ambiguo) | 0-30 GBP/mese (snippet) | gratis | 6-9 GBP/mese (valuta dedotta) |

Cosa NON dichiara nessun competitor, nelle pagine lette: latenza ordine (decisione -> placeOrders -> risposta) in ms, uso di CPU/RAM
in esercizio (solo Geeks Toy dice i requisiti minimi), ne' la ripresa dello stream con `initialClk`/`clk`. Quindi il confronto
«al millisecondo come i competitor» ha come unico metro pubblico i **20 ms di refresh** (Bet Angel), lo **0 ms di conflation**
(Cymatic) e i **150-200 ms di polling minimo**; tutto il resto del confronto va misurato da noi con la stessa metrica
(misura «messaggio Betfair -> ladder a schermo» e «decisione -> risposta di placeOrders», delegato 07).

---

## 3. Betfair Exchange API - limiti e prestazioni ufficiali

Fonti: sigle B-xx e S-xx della sezione 9 (docs.developer.betfair.com e support.developer.betfair.com).

### 3.1 Exchange Stream API (B-STREAM, S-xx)

| Tema | Valore ufficiale | Fonte |
|---|---|---|
| Endpoint | `stream-api.betfair.com:443` (SSL, JSON delimitato da CRLF); integrazione `stream-api-integration.betfair.com`. Valido anche per l'Italia (stesso endpoint) | B-STREAM «TCP / SSL Connection», B-IT |
| Timeout di connessione | dopo la connessione bisogna inviare un messaggio **entro 15 s** o arriva TIMEOUT | B-STREAM «Avoiding TIMEOUT on connection» |
| Autenticazione | `op=authentication`; la risposta riporta `connectionsAvailable` = «numero di connessioni aggiuntive che puoi aprire» (solo nella risposta di autenticazione) | B-STREAM «Connection / ConnectionMessage» |
| Connessioni per app key/conto | esiste `MAX_CONNECTION_LIMIT_EXCEEDED`; **il numero NON e' scritto** nelle pagine ufficiali che ho letto. Il nostro audit (`AUDIT_2026-09-28/CANTIERE_B_CAPACITA_MERCATI.md:19,426-427,440`) dice 10 di serie e ammette: «Il 10 non e' scritto nelle docs ufficiali». Il commento di `Betfair/safe_strategy/stream.py:3-6` lo attribuisce a una risposta del BDP sul forum del 09/09/2026: NON verificata da me | B-STREAM «ErrorCode»; repo |
| Creare/chiudere connessioni | `TOO_MANY_REQUESTS` anche per «creare/chiudere connessioni troppo spesso» | B-STREAM «errori di autenticazione» |
| Mercati per sottoscrizione | **200 di serie** (`SUBSCRIPTION_LIMIT_EXCEEDED`, unico errore che NON chiude la connessione; tutti gli altri la chiudono); la convalida e' fatta alla sottoscrizione e di nuovo alla ri-sottoscrizione, escludendo i mercati chiusi; i mercati chiusi escono dalla cache con un job ogni **5 min** e vengono marcati per l'eliminazione **1 h** dopo la chiusura | B-STREAM «ErrorCode», S-CLOSED |
| Sottoscrizioni multiple | ogni nuova sottoscrizione SOSTITUISCE la precedente (immagine iniziale nuova), non e' additiva | B-STREAM «Subscription» |
| `conflateMs` | millisecondi; con **Delayed App Key o ritardo sul conto vale 180000** (3 minuti); con la Delayed key lo stream e' conflated «ogni 3 minuti in un solo messaggio» | B-STREAM «Subscription», S-ACCESS |
| `heartbeatMs` | limiti **500-5000 ms** (default 5000); heartbeat = messaggio vuoto `ct=HEARTBEAT` se non c'e' traffico nell'intervallo; sempre con `clk`; mai con dati | B-STREAM, S-HB |
| Salute del flusso | nessun messaggio per **2 x heartbeat** = forse disconnesso; campo `status` null = aggiornato, **503** = latenza di push, «i dati non sono affidabili», il client NON deve disconnettersi, a recupero arrivano gli ultimi dati; per sottoscrizione | B-STREAM «Stream Health», «Stream API Status - latency» |
| `con=true` (conflation) | e' posto se il client legge piu' lentamente della consegna (il socket va svuotato perche' parta il ciclo successivo), se `conflateMs>0`, o se il ciclo di pubblicazione e' lento | B-STREAM «Conflation» |
| Segmentazione | `segmentationEnabled=true`: spezza i messaggi grandi, migliora latenza e tempo al primo/ultimo byte; «i dati segmentati vanno sempre meglio dei non segmentati» | B-STREAM «Performance Considerations» |
| Costo di una sottoscrizione | una sottoscrizione a un solo mercato e una a tutti i mercati hanno la **stessa latenza**; l'immagine iniziale costa piu' degli aggiornamenti; filtrare i campi (`marketDataFilter`) la rende piu' piccola e veloce | B-STREAM «Performance Considerations» |
| Ripresa (`initialClk`/`clk`) | salvare i criteri di sottoscrizione IDENTICI, `initialClk` (di norma solo nell'immagine iniziale) e `clk` (su ogni messaggio non segmentato o `SEG_END`); alla riconnessione si ri-sottoscrive con gli ultimi valori e arriva `ct=RESUB_DELTA`; alcuni mercati con `img=true` (da sostituire per intero); la maggior parte con `con=true`; clock non valido = `INVALID_CLOCK` | B-STREAM «Re-connection», S-RECON |
| Riconnessione | «tenere connessioni lunghe e' incoraggiato» ma «non possiamo garantire che non vengano chiuse»: logica di riconnessione obbligatoria, **con backoff** | B-STREAM, B-BEST |
| Valuta | lo stream supporta **solo GBP** (conversione con `listCurrencyRates`) | B-STREAM «Currency Support» |
| Order Stream | `op=orderSubscription` -> `op=ocm`; filtri `customerStrategyRefs` e `partitionMatchedByStrategyRef` (posizioni per strategia); `includeOverallPosition`; ordini e mercato prodotti da **due sistemi indipendenti: nessuna garanzia sull'ordine di arrivo** fra `ocm` e `mcm` | B-STREAM «OrderSubscription», «ChangeMessage» |
| Accesso | Delayed key: stream disponibile ma conflated 3 min; per dati live serve Live App Key, conto verificato (KYC) e con fondi | S-ACCESS |
| Italia | l'Exchange Stream e' disponibile ai clienti Betfair Italia, stesso endpoint | B-IT |

### 3.2 Richieste REST: limiti e pesi

| Tema | Valore ufficiale | Fonte |
|---|---|---|
| Peso dei dati di mercato | `sum(peso) x numero di market id` **non deve superare 200 punti** per richiesta (errore `TOO_MUCH_DATA`). Pesi `listMarketBook`: senza proiezione 2; `SP_AVAILABLE` 3; `SP_TRADED` 7; `EX_BEST_OFFERS` 5; `EX_ALL_OFFERS` 17; `EX_TRADED` 17; `BEST_OFFERS+TRADED` 20; `ALL_OFFERS+TRADED` 32; con `exBestOffersOverrides` peso x (profondita'/3). `listMarketCatalogue`: `MARKET_DESCRIPTION` 1, `RUNNER_METADATA` 1, altre 0. `listMarketProfitAndLoss` 4 | B-WEIGHT, S-LIMITS |
| Richieste concorrenti | `TOO_MANY_REQUESTS` se ci sono **3** richieste in coda: `listMarketBook` con proiezione ordini/abbinamenti, `listCurrentOrders`, `listMarketProfitAndLoss` si contendono lo stesso tetto, **per conto, non per sessione**; `listClearedOrders` ha un meccanismo separato | B-EXC, S-TMR |
| Istruzioni al secondo | `placeOrders`, `cancelOrders`, `updateOrders`, `replaceOrders`: errore se le istruzioni inviate superano **1000 in un secondo** | B-EXC, S-TMR |
| Istruzioni per `placeOrders` | max **200** (exchange globale), **50** (exchange italiano) per richiesta; una richiesta italiana con back e lay insieme e' RIFIUTATA | B-PLACE, B-IT |
| Istanze per mercato | **non trovato** nella documentazione che ho letto un tetto di «istanze/ordini per mercato» ne' un tetto orario di transazioni in numero. Il tetto «5000 transazioni/ora oltre cui scattano gli addebiti» e' scritto nella documentazione di flumine (`flumine/controls/clientcontrols.py:13-18`, `docs/controls.md`) e nel nostro `Betfair/stream/config_stream.py:256-262`; Bet Angel dice solo «il limite orario e' fissato da Betfair, oltre si paga» (BA-PDF r.9912). La pagina Betfair delle tariffe (`betfair.com/aboutUs/Betfair.Charges`) non e' raggiungibile dal mio PC (bloccata dal filtro ADM) | repo, F-FLUMINE |
| Conteggio transazioni | il costo include scommesse non abbinate, abbinate, cancellate e lapsed; **una cancellazione riuscita non conta** (piazza+cancella = 1); una cancellazione fallita conta | S-TXN |
| Login | richieste di login riuscite max **100 al minuto**, oltre: ban di **20 minuti** per nuovi login (`TEMPORARY_BAN_TOO_MANY_REQUESTS`), le sessioni esistenti restano valide | B-LOGIN |
| HTTP | consigliati `Accept-Encoding: gzip, deflate`, `Connection: keep-alive`; i keep-alive inattivi sono chiusi dai server ogni **3 min**; `Expect: 100-Continue` da NON mandare (errore 417) | B-BEST, B-OPT |
| Usare lo stream | «usare lo Stream API invece del polling dove possibile, in particolare per applicazioni ad alta frequenza»; «preferire lasciare un ordine al suo posto piuttosto che cancellare e ripiazzare: resti in testa alla coda» | B-BEST |
| Stato API | misura latenza ed errori «contro alcune operazioni ogni secondo» e commuta una pagina di stato (`status.developer.betfair.com`) | B-BEST |
| Costi dell'accesso | Delayed key gratuita; **Live App Key: 499 GBP una tantum** (nessuna tassa di attivazione per i conti Betfair Italia) | S-COST, B-IT |

### 3.3 Sessione e keepAlive (anche .it)

| Tema | Valore | Fonte |
|---|---|---|
| Durata sessione | **12 ore** sul .com (esclusi UK e Irlanda); **24 ore** UK e Irlanda; **20 minuti** su exchange Italia e Spagna; la durata non e' estesa dall'attivita' API; configurabile in Account > Preferenze di logout | B-LOGIN «Keep Alive», S-KEEP |
| keepAlive .it | `POST https://identitysso.betfair.it/api/keepAlive` (header `X-Authentication`, `Accept: application/json`); idem logout `identitysso.betfair.it/api/logout`; login non interattivo `identitysso-cert.betfair.it/api/certlogin` | B-LOGIN, B-IT |
| Errori di sessione | gestire `INVALID_SESSION_INFORMATION` ricreando il token | B-BEST, S-SESSERR |
| Heartbeat API (cancella gli ordini se cade la connessione) | `HeartbeatAPING/v1.0/heartbeat(preferredTimeoutSeconds)`; se non arriva un heartbeat entro il tempo, Betfair tenta di cancellare TUTTE le scommesse di tipo LIMIT del cliente su quell'exchange, **senza garanzia**; endpoint dedicato anche per l'Italia (`api.betfair.it/exchange/heartbeat/json-rpc/v1`) | B-HBAPI |

### 3.4 Bet delay, minimi, FILL_OR_KILL, persistenza, riferimenti

| Tema | Valore | Fonte |
|---|---|---|
| Bet delay in-play | di norma **1-12 s**; il valore sta in `betDelay` di `listMarketBook` e nella `MarketDefinition` dello stream | S-DELAY, B-STREAM |
| Modelli di bet delay | `betDelayModels` = `PASSIVE` e/o `DYNAMIC`: negli in-play con `betDelay>0`, un ordine che **non puo' abbinarsi subito** e' accettato senza attendere il delay. Requisiti PASSIVE: solo LIMIT, `persistenceType=LAPSE`, **senza** `timeInForce`, `minFillSize`, `betTargetType`. Disponibile per tennis, basket, freccette e «alcuni mercati di calcio»; si riconosce da `betDelayModels` in `listMarketCatalogue/Book/RunnerBook` | B-STREAM, S-PASSIVE |
| Minimi Italia | puntata back minima **2,00 EUR (200 centesimi)**, incrementi di **0,50 EUR**; un lay deve essere tale che la puntata back corrispondente sia >= **0,50 EUR**; vincita potenziale max **10.000 EUR** (puntata inclusa); minimo per puntata «a payout basso» (1 GBP / 10 GBP di payout) **NON abilitato** su .it, .es, .dk, .se | B-IT, B-PLACE «lower minimum stakes» |
| FILL_OR_KILL | `timeInForce=FILL_OR_KILL` con `minFillSize` opzionale: l'ordine si abbina solo se si abbina almeno `minFillSize` (o tutto); il resto e' cancellato subito. Il prezzo di un FOK e' il limite inferiore del **VWAP** dell'intero volume abbinato (non del singolo frammento) | B-PLACE «Fill or Kill bets» |
| `persistenceType` | `LAPSE` (default), `PERSIST` (resta a mercato in-play), `MARKET_ON_CLOSE` (SP); un LIMIT non abbinato LAPSE decade alla sospensione/in-play | B-PLACE |
| `customerRef` | fino a 32 caratteri, de-duplica rinvii errati in una **finestra di 60 s** | B-PLACE |
| `customerStrategyRef` | fino a **15 caratteri**, ritorna nell'Order Stream; stringa vuota = null | B-PLACE |
| `marketVersion` | se la versione corrente e' piu' alta, l'ordine **decade** | B-PLACE |
| `async` | ordini asincroni: stato `PENDING` senza betId, tracciabili dallo stream con `customerOrderRef` | B-PLACE |
| Fuso/orologio | Betfair raccomanda di sincronizzarsi col tempo del server con i pool NTP europei | B-ADDINFO |
| `PROCESSED_WITH_ERRORS` | se la «Best Execution» e' spenta un `placeOrders` puo' essere parzialmente rifiutato; normalmente e' atomico | B-PLACE |

---

## 4. flumine e betfairlightweight (GitHub, licenza MIT)

Fonti: F-FLUMINE (`betcode-org/flumine`, 249 stelle, ultimo push 01/10/2026), F-BFLW (`betcode-org/betfair`, 515 stelle, v2.24.0,
ultimo push 08/10/2026). Letti README, `docs/*.md` e i sorgenti elencati; le righe sono quelle del file raw del ramo master di oggi.

### 4.1 betfairlightweight (client)

- Wrapper Python «leggero, velocissimo (usa librerie C e Rust)» di tutta l'API Betfair, incluso lo stream (F-BFLW README).
- `streaming/betfairstream.py`: `subscribe_to_markets(..., initial_clk, clk, conflate_ms (bounds 0-120000 nel docstring), heartbeat_ms (500-5000), segmentation_enabled=True)`; `_read_loop`, `_receive_all` con timeout/errori di socket (righe 106-181, 225-305). **Nota**: il docstring dice 0-120000 ms per `conflateMs`, la documentazione Betfair cita 180000 per le chiavi ritardate (3.1): sono due contesti, non un errore dimostrato.
- `streaming/listener.py`: `max_latency=0.5` (avvisa se la latenza supera 0,5 s), `lightweight` (dict invece di oggetti), gestione di `RESUB_DELTA` (righe 12, 97-115, 195).
- `streaming/stream.py`: cache dei book con `MAX_CACHE_AGE = 8 ore` (riga 10), conserva `_initial_clk`/`clk`.
- Endpoint: login (certificato e interattivo), `keep_alive`, tutte le operazioni betting/accounts.

### 4.2 flumine (framework)

| Pezzo | Cosa fa | Fonte |
|---|---|---|
| Ciclo principale | **un solo thread** `__main__` che consuma una coda FIFO di eventi, uno alla volta: `MARKET_CATALOGUE`, `MARKET_BOOK`, `RAW_DATA`, `CURRENT_ORDERS`, `CLEARED_MARKETS`, `CLEARED_ORDERS`, `CLOSE_MARKET`, `CUSTOM_EVENT`, `TERMINATOR` | F-FLUMINE `docs/architecture.md` |
| Stream | stream di mercato condivisi fra strategie (stessi parametri = stesso stream), stream dati (raw, per registrare), stream storico per mercato, **Order Stream** su tutti gli ordini del conto o per `customerStrategyRef` | `docs/advanced.md` |
| Gestisce da solo | riconnessione dello stream, login/logout del client, keep-alive | `docs/architecture.md` |
| Worker in background | `keep_alive` ogni **1200 s** (o `session_timeout/2`), `poll_account_balance` ogni 120 s, `poll_market_catalogue` ogni 60 s, `poll_market_closure` (ordini cancellati/regolati alla chiusura) | `docs/workers.md`; `flumine/worker.py:99-110` |
| Middleware di mercato | analisi/log per mercato prima delle strategie | `docs/architecture.md`, `flumine/markets/middleware.py` |
| Controlli | **client controls**: `MaxTransactionCount` (tetto 5000 transazioni/ora); **trading controls**: `OrderValidation` (taglia/quota, minimi: `tradingcontrols.py:88-112` usa `client.min_bet_size`/`min_bet_payout` da `currency_parameters["GBP"]`), `MarketValidation`, `StrategyExposure`; ordine fuori regole = stato `Violation` | `docs/controls.md`; `flumine/controls/clientcontrols.py:13-18`; `flumine/clients/betfairclient.py:12-14,111-141` |
| Ordini | `LimitOrder(time_in_force, min_fill_size)`, `LimitOnCloseOrder`, `MarketOnCloseOrder`; `Trade`/`OrderPackage`; place/cancel/update/replace con `force=True` per saltare i controlli; `Transaction` per raggruppare | `flumine/order/ordertype.py:27-72`; `docs/controls.md` |
| Simulazione | `FlumineSimulation` con `BetfairHistoricalStream` per mercato; **monkeypatch di `datetime.utcnow`** cosi' `seconds_to_start` e il timer di FOK valgono come in live; ordini simulati: **bet delay** (`simulatedorder.py:128-147`), FOK/`minFillSize` (`:133-161`), persistenza `LAPSE`/`MARKET_ON_CLOSE` (`:60,101`), **posizione in coda** (`:246`), SP, volume scambiato | `docs/architecture.md`; `flumine/simulation/simulatedorder.py` |
| Paper trading | client simulato nello stesso framework con stream reale | README F-FLUMINE; `flumine/clients/simulatedclient.py` |
| Prestazioni | `listener_kwargs` (`seconds_to_start`, `inplay`) limita gli aggiornamenti da elaborare in simulazione; multiprocessing «un processo per core, 8 mercati alla volta»; i file di mercato vanno tenuti in locale | `docs/performance.md` |
| Limiti noti | non conosce le regole **italiane**: nel sorgente dei controlli non c'e' alcun riferimento a `italian`/`.it` (grep `-i "italian\|ITALY"` su `tradingcontrols.py`: nessuna riga); i minimi vengono dalla tabella `currency_parameters` per la valuta del conto (`betfairclient.py:111-141`), che non contiene il passo da 0,50 EUR ne' il minimo del lay del .it. deduzione: i nostri `Betfair/stream/trading/minimi_it.py` e `submin.py` non sono duplicati di flumine ma estensioni necessarie | grep sul sorgente |
| Altro | multi-venue (Betfair, Betdaq, Betconnect; Smarkets, Matchbook, Polymarket, Kalshi in roadmap), Python >= 3.10 | README F-FLUMINE |

### 4.3 Cosa offrono gia' e cosa un'app di trading riscrive spesso

| Cosa un'app riscrive di solito | In flumine/bflw | Da noi |
|---|---|---|
| Client stream + riconnessione con `initialClk`/`clk` | si' (bflw + flumine) | usiamo flumine/bflw; il nostro `frammenti_mercato.py` (665 righe) e `safe_strategy/stream.py` (pool a shard, 2 implementazioni parallele) ricostruiscono parti della connessione: vedi 5.2 |
| keepAlive della sessione | si' (worker ogni 1200 s o `session_timeout/2`) | lo rifacciamo in 3 punti: `Betfair/stream/auth.py:83`, `Betfair/stream/runner.py:1316-1322` (480 s), `Betfair/omega/omega_service.py:8526` (600 s). Nota: 1200 s = la durata della sessione .it (20 min): il default di flumine NON basta da solo, serve `session_timeout/2` (`auth.py:196-200` legge `session_timeout`, default 1200) |
| Cache dei book, ladder in RAM | si' (MarketBook) | si': `recorder.py` tiene la cache; il ladder del frontend e' ricostruito da un payload proprio (`ladder_canale.py`) |
| Controlli pre-ordine, tetto transazioni | si' (`MaxTransactionCount`, `OrderValidation`) | usiamo i nativi (`config_stream.py:262`) + `trading/controls.py` + `limits.py` (nostri) |
| Esecuzione, FOK, persistenza, `customerStrategyRef` | si' (ordini nativi) | `order_exec.py:225-315` e `client.py:334-354` ricostruiscono i parametri JSON a mano fuori da flumine (due vie: `place_order_live` e il motore del runner) |
| Order stream e blotter | si' | usati (`runner.py:2162-2224`) |
| Simulazione/paper, bet delay, coda, FOK | si' (`SimulatedOrder`) | usiamo `SimulatedExecution` per il paper (`client_paper_affiancato.py:1-53`) e un banco proprio (`Betfair/stream/backtest/`) |
| Registratore dati grezzi | si' (esempio `marketrecorder.py`, stream dati) | `recorder.py` (249 righe) + curator: nostro |
| Storico e replay | `BetfairHistoricalStream` | usato dal banco; l'interfaccia di replay (MatchReplay) e' nostra |
| Heartbeat API (cancella a connessione persa) | **non** in flumine nei file letti | non trovata nemmeno da noi (sezione 6, P-09) |

---

## 5. Cosa dice il nostro codice sulle voci Betfair -> ladder -> ordine (fatti letti oggi)

### 5.1 Percorso dei dati

- Runner calcio: `Betfair/stream/runner.py:2858-2864`: sottoscrizione flumine con `market_data_filter` `STREAM_FIELDS` e `ladder_levels=LADDER_DEPTH` (default 10, `config_stream.py:47`), **`conflate_ms=STREAM_CONFLATE_MS or None`** con default **0** (`config_stream.py:87`). Order stream: `ORDER_STREAM_CONFLATE_MS` default 0 (`config_stream.py:235`; usato in `runner.py:2162,2185,2224`).
- Scanner (alimenta Mike/Safe/Omega): `Betfair/safe_strategy/stream.py:65-66` **`_HEARTBEAT_MS = 5000`, `_CONFLATE_MS = 1000`**; sottoscrizione `EX_BEST_OFFERS`+`EX_MARKET_DEF`, `ladder_levels=1` (righe 268-277). Il commento in `Betfair/safe_strategy/scanner.py:655` e `service.py:1487` dice che il salto massimo e' «conflate (1 s) piu' la cadenza del tick». Il banco replica questo conflate (`Betfair/stream/backtest/banco_comune.py:2539-2551`) e nota che il registratore invece scrive a conflate 0 (`recorder.py:127`).
- Capacita': 180 mercati per connessione (< 200), fino a 4 connessioni di default e 10 di tetto (`safe_strategy/stream.py:3-40`); il runner calcio a frammenti (`frammenti_mercato.py:1-40`).
- Ladder al frontend: `Betfair/stream/ladder_canale.py:1-35`: canale locale ogni **`canale_ms` = 200 ms** (default) e scrittura DB ogni **2 s**; il commento cita come metro «Bet Angel/Fairbot (refresh 20-200 ms)». `frontend/src/components/live/LadderView.tsx:15-16` dice che la profondita' arriva dalla tabella realtime `live_ladder` pubblicata dal runner; la corsia locale e' nel trasporto (`lib/localTransport.ts`, citato in `ladder_canale.py:30-33`).
- Ordine: `Betfair/stream/motore_ordini.py:1-40`: strada unica = runner con flumine nello stesso processo; il desktop arriva dal canale locale; thread che dorme su un `Event` (nessun sonno da 1 s); **nessun I/O DB fra ricezione e `_dispatch`**; diario write-ahead `_diario_ordini/<data>.jsonl` con fsync PRIMA della chiamata a Betfair; scrittura DB (audit, specchio) asincrona. Le misure di decisione -> risposta spettano a `07_MISURE_OGGI.md`.

### 5.2 Duplicazioni rispetto a librerie/competitor (alimentano la sezione 4 delle schede A e C)

- Due implementazioni di connessione di mercato a piu' connessioni: `frammenti_mercato.py` (runner) e `safe_strategy/stream.py` (scanner), entrambe con limiti e riconnessione propri.
- Tre keepAlive (`auth.py:83`, `runner.py:1316`, `omega_service.py:8526`).
- Due vie di costruzione ordini (`order_exec.py:225-315` e `live_order_build.py`/`motore_ordini.py`).

---

## 6. TABELLA DI PARITA' (priorita': Betfair -> ladder -> ordine)

Colonne: competitor che la dichiara | c'e' da noi? | misura dichiarata da loro | misura nostra | gap | componente del piano
(A connessione, B punteggi, C ordini, D runtime bot, E strategie, F money mgmt, G dati, H banco/replay, I desktop/processi, J frontend).
«07» = `ARCHITETTURA_2026-10/07_MISURE_OGGI.md` (altro delegato, non ancora presente quando scrivo). «MIS-02/10» = `SCHEMI_BOT/sistema/MISURE_2026-10-02.md`.

### 6.1 Betfair (stream, sessione, limiti)

| # | Funzione competitor | Da noi? (`file:riga` / grep) | Misura dichiarata da loro | Misura nostra | Gap | Dove si chiude |
|---|---|---|---|---|---|---|
| P-01 | Prezzi via Stream API push (Bet Angel, Cymatic, Fairbot «Stream API mode», Bfexplorer) | SI': `runner.py:2858-2864`; scanner `safe_strategy/stream.py:259-277` | BA refresh fino a **20 ms** o «Update» (BA-PDF r.9956-9966); Cymatic conflation **0 ms** (CY-STREAM) | runner: conflate 0 (`config_stream.py:87`); **scanner: conflate 1000 ms** (`safe_strategy/stream.py:66`); registrazioni: p50 fra messaggi 105 ms, p99 1,2-3,2 s (`strumenti/misure/uscite/m01_feed_raw.txt`); latenza vera: 07 | lo **scanner che alimenta Mike/Safe/Omega e' a 1 s**, 50 volte piu' lento del refresh di Bet Angel: e' un'ipotesi di input dei bot, quindi **decisione per l'utente** (non si cambia da soli) | A |
| P-02 | Conflation configurabile a 0 (Cymatic) | SI' nel runner (`config_stream.py:87`, env `LIVE_STREAM_CONFLATE_MS`); NO nello scanner (costante `_CONFLATE_MS=1000`, nessun env) | 0 ms, «alza a 200-500 se il PC e' lento» (CY-STREAM) | vedi P-01 | scanner non configurabile | A |
| P-03 | Ripresa con `initialClk`/`clk` (bflw/flumine; competitor n.d.) | SI' (libreria): `frammenti_mercato.py:49,189`; listener bflw | Betfair: `RESUB_DELTA` invece dell'immagine piena (B-STREAM) | n.d. | nessuno; da provare nel banco (scenario di caduta) | A, H |
| P-04 | Mercati monitorabili | SI': 180/connessione, shard fino a 10 (`safe_strategy/stream.py:3-40`, `frammenti_mercato.py:1-40`) | BA «1000» (BA-PDF r.5281); Bfexplorer/Betfair «200 per sottoscrizione» | in uso: 67 mercati su 2 connessioni il 26/09 (`CANTIERE_B...md:440`) | cifra per app key non verificata nei documenti ufficiali (3.1) | A |
| P-05 | Order Stream / posizioni a push | SI': `runner.py:2162-2224` | BA: scommesse spinte da Betfair (BA-PDF r.2137) | n.d. | nessun gap funzionale | A, C |
| P-06 | Monitor della salute del flusso (503, heartbeat) | SI': `safe_strategy/stream.py:70-75` (503), `flusso_prezzi.py:1-40`, `runner.py:1599-1606`; UI `FlussoStreamBanner.tsx:1-12` | Cymatic API Monitor (soglie, pausa trading, e-mail) (CY-FEAT); Geeks Toy soglia 500-2000 ms (GT-STATUS) | n.d. | da noi manca l'**indicatore numerico di durata round-trip** in UI e la **pausa automatica del trading oltre soglia di latenza** (grep `latenz\|latency\|rtt\|round.?trip` in `frontend/src` fuori da test: solo icone di allarme in `PannelloBot.tsx`) | A, J |
| P-07 | keepAlive e sessione | SI': `auth.py:83`, `runner.py:1316-1322` (480 s), `omega_service.py:8526` (600 s), custode con relogin al 90% (`runner.py:1599-1606`) | .it **20 min** (B-LOGIN); flumine ogni 1200 s | n.d. | 3 implementazioni da unificare | A |
| P-08 | Sincronia dell'orologio col server | PARZIALE per scelta: `Betfair/stream/orologio.py:1-60` **dichiara** lo scarto e rende «non affidabili» i confronti sotto l'incertezza (`SCARTO_MISURATO_MS = 2080.0` misurato il 17/09; env `BETFAIR_SCARTO_OROLOGIO_MS`), ma **non corregge l'orologio** (righe 17-20: «sistemare l'ora e' un'impostazione di sistema, la fa l'utente») | Betfair raccomanda NTP (B-ADDINFO) | PC indietro di **2080 ms** il 17/09 (`orologio.py:6`) e di circa **844 ms** oggi su 3 server NTP (`strumenti/misure/uscite/m00b_ntp_offset.txt`: -826...-846 ms) | ogni latenza calcolata con `publishTime`/`placedDate` e' falsata di 0,8-2 s se non si dichiara lo scarto; l'ora di Windows resta fuori sincronia (decisione dell'utente: impostazione di sistema) | A, H, I |
| P-09 | **Heartbeat API** (auto-cancel ordini) | **NON trovata**: `grep -rn -il "HeartbeatAPING\|exchange/heartbeat" Betfair tools` = nessun file | Betfair: cancella gli ordini LIMIT se manca il battito (B-HBAPI); competitor n.d. | n.d. | stop/offset software-side: «se il processo cade non esistono» (`trading/risk_engine.py:21-23`, `config_stream.py:309-310`) | C, I |
| P-10 | Gestione bet delay (`betDelay`, `betDelayModels`) | PARZIALE: `mike/feed.py:270,347` legge `bet_delay`; `omega/tools/misura_ingresso_passivo.py` misura l'ingresso passivo | Betfair: 1-12 s; PASSIVE per tennis/calcio (S-DELAY, S-PASSIVE); competitor n.d. | betDelay osservato 5 s nelle registrazioni (`m01_feed_raw.txt`) | nessun gap di parita' (i competitor non dichiarano nulla); verificare in C che i requisiti PASSIVE (niente FOK, solo LAPSE) siano rispettati | C, E |
| P-11 | Minimi Italia (2 EUR, passo 0,50, lay con back >= 0,50) | SI': `trading/minimi_it.py:106,143`, `trading/submin.py` | competitor n.d.; flumine non li conosce (4.2) | n.d. | nessuno; e' un vantaggio nostro | C |
| P-12 | `customerStrategyRef` (15 caratteri) e `customerRef` (de-dup 60 s) | SI': `client.py:334-354`; motore con ref e dedup (`motore_ordini.py:20-36`) | Betfair (B-PLACE) | n.d. | nessuno | C |
| P-13 | Contatore transazioni/ora | PARZIALE: tetto in codice `config_stream.py:256-262` (1000/ora); **non trovato in UI** (grep `transazion\|transaction` in `frontend/src`: solo `personalReport.ts:354`) | BA contatore a schermo (BA-PDF r.9905-9913); tetto Betfair 5000/h (flumine) | n.d. | manca la vista a schermo | C, J |
| P-14 | Limiti di richieste/peso (200 punti, 3 concorrenti) | da verificare in A: i poll REST (`odds_http.py`, `riserva_prezzi.py`) | Betfair (3.2) | MIS-02/10 non conta le chiamate a Betfair (solo segni indiretti) | verificare che nessun poll usi `EX_ALL_OFFERS+EX_TRADED` x molti mercati | A |

### 6.2 Ladder, grafici e interfaccia

| # | Funzione competitor | Da noi? | Misura dichiarata da loro | Misura nostra | Gap | Dove |
|---|---|---|---|---|---|---|
| L-01 | Ladder one-click a profondita' completa, LTP, volume per livello | SI': `LadderView.tsx:1-22` (2984 righe), `GridView.tsx` (653), `StandaloneLadder.tsx`, `LadderPopout.tsx` | BA/GT/FB/CY (sezione 1) | n.d. | nessuno funzionale | J |
| L-02 | Cadenza di refresh del ladder | SI': canale locale **200 ms**, DB 2 s (`ladder_canale.py:1-35`) | BA **20 ms** o «Update» (BA-PDF r.9959-9966); Cymatic «0 ms» | 200 ms nominali + 07 per il tempo messaggio->schermo | **10 volte** piu' lento del refresh dichiarato da Bet Angel; il commento nostro cita «20-200 ms» ma il default e' il margine alto | A, J |
| L-03 | Posizione in coda stimata (PIQ/EPIQ) | SI': colonna 8 di `LadderView.tsx:12`; modello di coda nello scalper (`scalper_bot.py:559,1418`) | Cymatic «primi a mostrarla» (CY-FEAT); BA EPIQ (BA-PDF r.9082) | n.d. | nessuno | J |
| L-04 | Weight of Money, profondita' totale | SI': `runner.py:594-639`, `DepthPanel.tsx:2` | Fairbot WoM, indicatori (FB-HOME) | n.d. | nessuno | J |
| L-05 | Grafici avanzati, indicatori tecnici (RSI, Stochastic, candele) | PARZIALE: `SelectionChartPanel.tsx` (357), `MiniPriceChart.tsx`; grep `rsi\|stochastic\|candlestick\|bollinger` in `frontend/src` fuori da test: solo testi di strategia tennis (`lib/tennis.ts:820`) | BA, Cymatic (trendline magnetiche), Fairbot (indicatori) | n.d. | niente indicatori tecnici ne' disegno di trendline sul grafico | J |
| L-06 | Multi-mercato / Guardian / watch list | SI': `MultiLadder.tsx` (197), `MarketWatch.tsx`, `Watchlist.tsx`, `auto_follow.py:1-30` (aggancio al volo dei mercati dei bot) | BA Guardian 50 mercati/s a 20 ms (BA-PDF r.4732) | n.d. | l'auto-follow e' un vantaggio (i bot seguono da soli) | J, A |
| L-07 | Tasti rapidi | SI': `LadderView.tsx:473` (B/L/C/frecce), `lib/workspace.ts:239` `resolveHotkey` | Cymatic «rapid keyboard betting», GT Shortcut Manager | n.d. | nessuno | J |
| L-08 | Allarmi sonori/avvisi | PARZIALE: banner visivi (`LiveAlertBanner.tsx`); grep `new Audio\|beep\|AudioContext\|sound` in `frontend/src` = nessun risultato | GT Audio Alerts Manager (GT-MAN); BA Alerts | n.d. | nessun allarme sonoro | J |
| L-09 | Layout salvabili, piu' monitor | SI': `LadderPopout.tsx` (51), `lib/workspace.ts` | BA undock, Cymatic «layout illimitati» | n.d. | verificare salvataggio layout | J |

### 6.3 Ordini

| # | Funzione competitor | Da noi? | Misura dichiarata | Misura nostra | Gap | Dove |
|---|---|---|---|---|---|---|
| O-01 | One-click: ordine dal ladder fino a Betfair senza rete verso il DB | SI': `motore_ordini.py:1-40` (canale locale, `Event`, diario fsync, scrittura DB asincrona) | nessun competitor dichiara ms ordine->risposta | tempi: 07 | tutti i bot che NON passano dalla «strada unica» (Mike/Omega/Safe/scalper via servizi propri, `mike/porta_ordini.py`, `omega/porta_ordini.py`) hanno ognuno la sua porta | C |
| O-02 | Fill or Kill | SI' nativo (`order_exec.py:225-254`, `timeInForce`) e SOFTWARE a timer (`live_order_worker.py:1480-1543`, `fok_ttl_sec` <= 3600) | BA/GT/CY/FB: timer software (BA-PDF r.1897-1925) | n.d. | nessuno; il FOK nativo e' escluso dai modelli PASSIVE (3.4) | C |
| O-03 | Tick offset / bracket / batch di offset | SI': `trading/risk_engine.py:11-13`, `RiskRulesPanel.tsx` (764); scalper `scalper_bot.py` | BA offset a tick/% e a batch (BA-PDF r.1895, 2151-2162) | n.d. | **offset a batch** (offset parziale) non trovato (grep `batch` nel risk engine) | C |
| O-04 | Stop loss e trailing stop | SI': `risk_engine.py:14-20`, `risk_engine_worker.py:360-370` | BA/GT/CY (BA: gli stop non attraversano il pre-gara->in-play, BA-PDF r.2051) | cadenza del worker `RISK_ENGINE_POLL_SEC=1.0` s (`config_stream.py:311`) | **1 s di cadenza** contro refresh dichiarati da 20 ms: uno stop puo' scattare con 1 s di ritardo; software-side come tutti | C |
| O-05 | Greening / cash-out | SI': `trading/greenup.py:118`, `CashOutButton.tsx` (471), `mike/engine.py:1045` | BA, CY, FB (cash-out avanzato con ripartizione libera) | n.d. | ripartizione libera del profitto fra esiti: non trovata | C, J |
| O-06 | Dutching / bookmaking | SI': `trading/dutching.py:81,147,184`, `DutchingPanel.tsx` (617); bookmaking: non trovato (grep `bookmak`: solo opzioni di `CreateStrategy.tsx:233`) | BA, GT, FB, Gruss | n.d. | bookmaking assente | C, J |
| O-07 | Persistenza in-play (Cancel/Keep/Take SP) | SI': `order_exec.py:88,238`, `LadderView.tsx:187`, `DutchingPanel.tsx:140` | GT, BA, CY | n.d. | nessuno | C, J |
| O-08 | OCO (entry+exit+stop) | EQUIVALENTE funzionale nel risk engine (bracket); non esiste un oggetto «OCO» esplicito (deduzione: `risk_engine.py:11-22` fa offset+stop sullo stesso ingresso) | GT OCO (GT-OCO) | n.d. | verificare il caso parziale (stop che si riduce con l'exit parziale) | C |
| O-09 | Repeat on Success (ripete il trade N volte) | **non trovata** in UI (grep `ripeti\|repeat` in `frontend/src`: solo stili) ne' nel risk engine | Fairbot (FB-HOME) | n.d. | assente (le strategie scalper ripetono per logica propria: fuori perimetro) | C, E |
| O-10 | Sub-minimo / place-and-trim | SI': `trading/submin.py:79-162`, `PLACE_AND_TRIM_INDAGINE_2026-09-17.md` | competitor n.d. (il nostro documento afferma che funziona su BA e Fairbot: fonte interna) | n.d. | nessuno | C |
| O-11 | Passive orders (ingresso senza bet delay) | PARZIALE: misura in `omega/tools/misura_ingresso_passivo.py` | n.d. | n.d. | verificare l'uso reale (S-PASSIVE) | C, E |

### 6.4 Automazione, simulazione, dati, risorse

| # | Funzione competitor | Da noi? | Misura dichiarata | Misura nostra | Gap | Dove |
|---|---|---|---|---|---|---|
| A-01 | Motore di regole editabile dall'utente (BA Automation/Servants, Fairbot Advanced Automation, Bfexplorer >30 trigger, Cymatic robot) | NO come editor generico: i bot sono strategie in codice (Mike, Omega, Safe, scalper) con parametri editabili (`ParamsSheetBase.tsx`) | BA: «centinaia di modelli» (BA-HOME) | n.d. | per scelta (strategie intoccabili): da riportare come decisione, non gap da chiudere | D, E |
| A-02 | Excel (BA, Cymatic, Gruss) | **non trovata** (grep `openpyxl\|xlsx\|excel` in `Betfair/`: solo `safe_strategy/engine.py:212` commento) | prezzi e ordini da foglio | n.d. | assente (nessun requisito dell'utente) | J |
| A-03 | API locale per codice di terzi (Bet Angel API su porta locale) | SI' in forma privata: canale locale `local_channel.py`, `canale_bot.py` | BA API JSON su porta (BA-PDF r.9749) | n.d. | contratto non documentato come API | D, I |
| R-01 | Practice/Training con matching locale | SI': PAPER (`modo_ordini.py:1-30`, `client_paper_affiancato.py:1-53`, esecuzione simulata flumine) | BA: matching locale + cross-matching + Take SP + Keep (BA-PDF r.816-830) | n.d. | nessuno; la nostra regola paper=live e' piu' stretta | C, H |
| R-02 | Replay di mercati storici | SI': banco (`Betfair/stream/backtest/`, `certifica.py`), `MatchReplay.tsx` (1280), `TennisReplay.tsx` (811) | solo Gruss: Market Replay 5 anni, a pagamento (GR-PAGE) | tempo replay: 07 / `PROCESSO_STANDARD_BOT.md` 6.9 (5 min target) | nessuno (e' un nostro punto di forza) | H |
| R-03 | Registrazione locale dei dati grezzi | SI': `recorder.py:1-13` (JSONL per evento «source of truth»), `curator.py` | competitor n.d. | volume: `m05_risorse_disco.txt`; 9,6-25 MB per partita (`m01_feed_raw.txt`) | nessuno | G, H |
| R-04 | Diario degli ordini a prova di crash | SI': `motore_ordini.py:20-30` (JSONL fsync) | competitor n.d. | n.d. | nessuno | C |
| N-01 | Monitor di rete / API | vedi P-06 | Cymatic, Geeks Toy | n.d. | idem | A, J |
| N-02 | Risorse: requisiti dichiarati | n.d. per i bot; Geeks Toy: 1,6 GHz, 1 GB RAM, 20 MB disco (GT-DL) | GT | memoria/CPU in 24 h: 07 / `m05_risorse_disco.txt` | non confrontabile: il nostro e' Electron + Python + cloud, non un unico .exe | I |
| N-03 | **Il DB cloud non e' nel percorso decisionale** (i competitor desktop non hanno DB remoto) | PARZIALE: ordini e ladder si, ma i servizi dei bot leggono/scrivono Supabase nel ciclo: **1.309 chiamate/min totali** il 02/10, runner calcio 552/min, Mike 279/min, Safe bot 269/min (MIS-02/10, riepilogo) | n.d. | idem (fonte: `SCHEMI_BOT/sistema/MISURE_2026-10-02.md`) | tutto cio' che e' nel percorso stream -> cache -> decisione -> ordine deve restare a zero chiamate di rete (§9.3 del brief) | G, D |
| N-04 | Prezzo | n/a | BA 12,50-29,99 GBP/mese; GT 20/60 GBP; FB 85 EUR/anno; CY 59,99-99,99 GBP/anno; TL gratis; Gruss 6-9/mese; Bfexplorer 0-30 GBP/mese (snippet) | costo fisso: Live App Key 499 GBP una tantum (S-COST) | n/a | - |

---

## 7. I gap piu' importanti (ordine di priorita': Betfair -> ladder -> ordine)

1. **Scanner a conflate 1000 ms** (P-01/P-02): il feed che alimenta Mike, Safe e Omega arriva con un salto fino a 1 s (`safe_strategy/stream.py:66`) mentre i competitor dichiarano 20 ms (Bet Angel) o 0 ms (Cymatic) e il nostro runner e' gia' a 0. Cambiarlo cambia l'input dei bot: **decisione per l'utente**, con replay sul banco prima (il banco gia' simula il conflate 1000, `banco_comune.py:2539-2551`). Componente A.
2. **Ladder a 200 ms contro 20 ms** (L-02): default del canale locale `ladder_canale.py`. Componenti A e J. Da misurare «messaggio Betfair -> pixel» (07) prima di fissare l'obiettivo.
3. **Orologio del PC fuori sincronia** (P-08): 2080 ms il 17/09 (`orologio.py:6`), circa 844 ms oggi (`m00b_ntp_offset.txt`); il codice lo dichiara ma non lo corregge, quindi ogni latenza basata su `publishTime` ha un'incertezza di quell'ordine. Betfair raccomanda NTP. Componenti A, H e I (servizio Ora di Windows: impostazione di sistema, la decide l'utente).
4. **Nessun Heartbeat API e stop/offset solo software** (P-09, O-04): se il processo cade, ordini aperti e stop restano scoperti; Betfair offre la cancellazione automatica degli ordini LIMIT (senza garanzia). Componenti C e I. Cambia il comportamento degli ordini: **decisione per l'utente**.
5. **Stop e trailing valutati a 1 s** (O-04, `config_stream.py:311`) contro refresh competitor di 20-200 ms; e **nessun indicatore numerico di latenza ne' pausa automatica per latenza** in UI (P-06, Cymatic). Componenti C e A/J.
6. (minori) contatore transazioni/ora a schermo (P-13), indicatori tecnici sul grafico (L-05), allarmi sonori (L-08), bookmaking (O-06), Repeat on Success (O-09), offset a batch (O-03), ripartizione libera nel cash-out (O-05), Excel (A-02).

Nostri punti di forza senza equivalente pubblico fra i competitor letti: minimi .it e place-and-trim (P-11, O-10), certificazione su replay con codice di produzione (R-02), diario degli ordini con fsync (R-04), auto-follow dei mercati dei bot (L-06), paper = live nello stesso processo (R-01).

---

## 8. Cosa ho verificato di persona / cosa non ho potuto verificare

**Verificato di persona** (letto il testo della fonte o il codice oggi):
- Tutte le pagine Betfair di sezione 3 (testo estratto dalle API pubbliche di Confluence e Zendesk) e i numeri riportati;
- il manuale PDF di Bet Angel (righe citate rilette dal testo estratto);
- le pagine di Geeks Toy, Cymatic, Fairbot, Gruss, Traderline e i file GitHub di flumine e betfairlightweight citati;
- tutti i `file:riga` del repo citati (letti con `sed`/`grep` oggi); gli ultimi grep «non trovata» sono stati lanciati su `Betfair/`, `tools/` e `frontend/src/` (non sull'intera radice, che contiene un log da 3 GB).

**Non trovato / non verificabile**:
- **Numero di connessioni stream per app key**: non scritto nelle pagine ufficiali (3.1); il «10» del nostro audit non e' confermato da fonte ufficiale.
- **Tetto orario di transazioni** e **istanze per mercato** di `placeOrders`: non nelle pagine Betfair raggiungibili; il 5000/ora viene da flumine. La pagina tariffe Betfair non e' raggiungibile dal mio PC.
- **Bfexplorer**: sito non raggiungibile, scheda da snippet e dal README SDK; prezzi da verificare.
- **Geeks Toy e Gruss**: nessuna dichiarazione sullo Stream API nelle pagine lette; il manuale di Geeks Toy potrebbe essere anteriore allo streaming.
- **Fairbot, Traderline**: nessuna latenza ne' frequenza dichiarata.
- **Latenze dei competitor**: nessuna misura indipendente pubblica trovata; solo dichiarazioni (20 ms, 0 ms, 150-200 ms).
- **P-08 (orologio)**: il valore -844 ms viene da `strumenti/misure/uscite/m00b_ntp_offset.txt` (altro delegato), non ripetuto da me; il valore 2080 ms da `orologio.py:6` (misura del 17/09). Perche' lo scarto sia passato da 2080 a circa 844 ms non l'ho verificato.
- Misure nostre di latenza (messaggio -> ladder, decisione -> `placeOrders` -> risposta) e di risorse 24 h: **non fatte qui**, sono nel file 07.

---

## 9. Fonti (URL)

**Betfair, documentazione (id Confluence = pagina `https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/<id>`)**
- B-STREAM Exchange Stream API (id 2687396) https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687396/Exchange+Stream+API
- B-WEIGHT Market Data Request Limits (2687478) https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687478/Market+Data+Request+Limits
- B-PLACE placeOrders (2687496) https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687496/placeOrders
- B-LOGIN Login & Session Management (2687869) https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687869/Login+Session+Management
- B-IT Betting On Italian Exchange (2687808) https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687808/Betting+On+Italian+Exchange
- B-HBAPI Heartbeat API (2687861) https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687861/Heartbeat+API
- B-BEST Best Practice Guide (2687730) https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687730/Best+Practice+Guide
- B-OPT Optimizing API Application Performance (2699882) https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2699882/Optimizing+API+Application+Performance
- B-EXC Betting Exceptions (2687450) https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687450/Betting+Exceptions
- B-ADDINFO Additional Information (2686993) https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2686993/Additional+Information

**Betfair, centro assistenza sviluppatori (`https://support.developer.betfair.com/hc/en-us/articles/<id>`)**
- S-LIMITS 115003864671 What data/request limits exist on the Exchange API?
- S-TMR 360000406111 Why am I receiving the TOO_MANY_REQUESTS error?
- S-HB 360000402611 Market Streaming - How do the Heartbeat and Conflation requests work?
- S-HOW 360000402291 Market & Order Stream API - How does it work?
- S-ACCESS 115003887871 How do I get access to the Stream API?
- S-CLOSED 11741143435932 Are closed markets auto-removed from the Stream API subscription?
- S-RECON 360000391612 Market Streaming - how do I managed re-connections?
- S-DELAY 360002825652 Why do you have a delay on placing bets on a market that is in-play
- S-TXN 20029343399836 Transaction Charge - how are transactions counted?
- S-KEEP 360002773032 How do I keep my API session alive?
- S-PASSIVE 26791968420636 How can I identify markets that accept passive orders via the Betfair API?
- S-COST 115003864531 Are there any costs associated with API access?
- S-SESSERR 11775498092701 Why I am received the error INVALID_SESSION_INFORMATION? (solo titolo, vedi anche B-BEST)

**Librerie**
- F-FLUMINE https://github.com/betcode-org/flumine (README, `docs/architecture.md`, `controls.md`, `workers.md`, `advanced.md`, `performance.md`, `known_issues.md`, `flumine/controls/clientcontrols.py`, `tradingcontrols.py`, `flumine/clients/betfairclient.py`, `flumine/simulation/simulatedorder.py`, `flumine/order/ordertype.py`, `flumine/worker.py`, `flumine/streams/*.py`) - raw: https://raw.githubusercontent.com/betcode-org/flumine/master/<percorso>
- F-BFLW https://github.com/betcode-org/betfair (README, `betfairlightweight/streaming/betfairstream.py`, `listener.py`, `stream.py`, `endpoints/keepalive.py`) - raw: https://raw.githubusercontent.com/betcode-org/betfair/master/<percorso>

**Bet Angel**
- BA-PDF Guida utente PDF (2025) https://www.betangel.com/user-guide-pdf/Bet-angel-user-guide.pdf
- BA-HOME https://www.betangel.com/ ; BA-PRO https://www.betangel.com/bet-angel-professional/ ; BA-BUY https://www.betangel.com/buy/ ; BA-REV https://www.betangel.com/review/ ; indice API https://www.betangel.com/api-guide/

**Geeks Toy**
- GT-HOME https://www.geekstoy.com/ ; GT-FEAT https://www.geekstoy.com/en/features ; GT-DL https://www.geekstoy.com/en/download ; GT-BUY https://www.geekstoy.com/en/buy
- GT-MAN indice https://www.geekstoy.co.uk/UserManuals/english.html ; GT-API https://www.geekstoy.co.uk/UserManuals/EN/API%20Settings%20Manager.html ; GT-STATUS https://www.geekstoy.co.uk/UserManuals/EN/Market%20%26%20API%20Status.html ; GT-LADDER https://www.geekstoy.co.uk/UserManuals/EN/Ladder%20Interface.html ; GT-OCO https://www.geekstoy.co.uk/UserManuals/EN/OCO.html ; GT-STAKING https://www.geekstoy.co.uk/UserManuals/EN/Staking%20%26%20Tools.html ; (lette anche Introduzione, Using the Application, Place Bets, Pending Bets, Unmatched Bets, Multi Market Trading, Main Info Bar, Layout and Settings)

**Fairbot**
- FB-HOME https://fairbot.com/ ; FB-NEW https://fairbot.com/whatsnew ; FB-ORDER https://fairbot.com/order ; FB-DL https://fairbot.com/download

**Cymatic**
- CY-FEAT https://www.cymatic.co.uk/Features.aspx ; CY-PRICE https://www.cymatic.co.uk/Pricing.aspx ; CY-STREAM https://www.cymatic.co.uk/UserManual/Streaming.aspx ; CY-POLL https://www.cymatic.co.uk/UserManual/PollingVersusStreaming.aspx ; CY-APIREF https://www.cymatic.co.uk/UserManual/ApiRefresh.aspx

**Bfexplorer**
- BX-SDK https://github.com/StefanBelo/Bfexplorer-BOT-SDK
- BX-SEARCH risultati di ricerca che indicizzano http://bfexplorer.net/ , http://bfexplorer.net/Products/Bfexplorer , http://bfexplorer.net/Subscribe , http://bfexplorer.net/Articles/Content/204 , http://bfexplorer.net/Articles/Content/388 (snippet, pagine NON lette)

**Traderline**
- TL-HOME https://traderline.com/ ; TL-EDU https://traderline.com/education/new-traderline ; TL-SEARCH https://traderline.com/education/betfair-ladder-trading-guide , https://traderline.com/education/traderline-cashout-freebet-mode-explained , https://traderline.com/about

**Gruss**
- GR-PAGE https://www.gruss-software.co.uk/page/87/Betfair-Betting-Assistant.htm ; GR-PRICE https://www.gruss-software.co.uk/page/82/Pricing.htm ; home https://www.gruss-software.co.uk/

Conteggio: 63 URL distinte elencate sopra (10 Betfair documentazione, 13 centro assistenza di cui 1 solo titolo, 2 librerie, 6 Bet Angel, 10 Geeks Toy, 4 Fairbot, 5 Cymatic, 6 Bfexplorer di cui 5 solo snippet di ricerca non letti, 5 Traderline, 3 Gruss; i file GitHub sono contati sotto il loro repository), piu' 8 pagine del manuale Geeks Toy lette ma non elencate singolarmente.
