# E2E FASE 2 — Feed unico e Atlante v4 (§7.1, §7.3, §7.9.1, §7.9.3) + K1 — referto admin-26 (delegato)

26/09/2026. App accesa dalle 08:56:41 UTC. Bot accesi in paper dall'altra sessione: tennis alle ~09:17 UTC,
scalper alle ~09:18 UTC, Mike e Safe prima delle ~09:22 UTC.

Ho lavorato in SOLA LETTURA:
- DB: solo GET PostgREST, con `select` e `limit` espliciti (`sonda_feed_atlante_db.py`);
- canali 47331 e 47336 da lettore;
- file locali dell'atlante letti, mai scritti.

Non ho toccato app, bot, `.env` o git. Nessuna correzione al codice.

**Referto PARZIALE.** Le finestre di osservazione:
- 09:06-10:57 UTC: sonde continue.
- 10:56 UTC: guasto di rete (DNS). Tutte le sonde vanno in `getaddrinfo failed`.
- Dopo il guasto, Claude Code ha fermato i processi in sottofondo per memoria scarsa. Non li ho riavviati.
- 14:39 UTC: un solo passaggio in primo piano, per fotografare lo stato attuale.

Script, tutti in questa cartella, prefisso `sonda_feed_atlante_`: `db`, `71_monitor`, `71_analisi`, `73_stato`,
`791_feed`, `793_ips`, `793_bot`, `793_ricalcolo`, `793_confronto_bot`.

Dati grezzi: `sonda_71_monitor.jsonl`, `sonda_73_stato.jsonl`, `sonda_791_feed_esito.json`, `sonda_793_ips.jsonl`,
`sonda_793_bot_giro1.jsonl`, `sonda_793_bot.jsonl`, `sonda_793_ricalcolo_esito.json`,
`sonda_793_confronto_bot_esito.json`.

Le copie dell'atlante che i bot avevano in ogni momento non sono nel repo: sono nello scratchpad della sessione,
`.../scratchpad/atlanti_m/hazard_atlas_live_m<mtime>.json`.

---

## K1 — size del feed in sterline (priorità del coordinatore)

**Esito: CONFERMATO.**
- Le size, i volumi e il `total_matched` che arrivano dall'Exchange Stream sono in **GBP**.
- Il codice non le converte mai e le usa come euro.
- Nella maggioranza dei punti l'errore è prudente. In **5 punti non lo è** (money-critical, elenco in K1.4).

### K1.1 Codice: da dove vengono le size e se esiste una conversione

**Scanner.** `Betfair/safe_strategy/scanner.py:250-259`
- `price_pair()` copia `best_size(available_to_back/lay)` così com'è in `back_size`/`lay_size`.
- `Betfair/safe_strategy/service.py:835` (`mo_total_matched`) e `:933` e `:979` (`total_matched` dei blocchi)
  fanno lo stesso con i volumi.
- La fonte è lo stream di `Betfair/safe_strategy/stream.py` (conflate 1 s, best offers).

**Stesso campo, due valute.** I mercati che lo stream non copre vengono riempiti dal ripiego REST `poll_books`
(`service.py:1017`), che è in EUR. Finiscono negli **stessi campi** del payload. Lo stesso accade in
`board_worker.py:119` (REST, EUR) contro `:155` (scanner, GBP).

**Runner e bot flumine** (scalper, tennis, paper di flumine): usano lo stesso Market Stream, quindi GBP.

**Nessuna conversione nel repo.** Ho cercato `gbp|currency|currencyCode|sterlin|eur_gbp` in `Betfair/` e in
`desktop/`. Ci sono solo commenti e codice di test o di replay:
- `backtest/banco_comune.py:1055`
- `mike/tools/replay_registrazioni.py:844`
- `reconcile_worker.py:550`

Nel codice di produzione non c'è nessun cambio di valuta.

**flumine.** Il `SimulatedMiddleware` lo ammette nel proprio codice: `flumine/markets/middleware.py:41`,
«todo currency fluctuations…».

### K1.2 Fonte documentale

Fonte: documentazione ufficiale Betfair, Exchange Stream API.

- Risultato di ricerca che rimanda alla pagina Confluence
  <https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687396/Exchange+Stream+API>:
  «Market subscriptions are always in underlying exchange currency - GBP» e «Orders subscriptions are provided in
  the currency of the account that the orders are placed in».
- Il fetch diretto della pagina ha restituito solo la navigazione: la citazione viene dall'estratto indicizzato, non
  dalla pagina letta per intero.
- Forum ufficiale per sviluppatori
  (<https://forum.developer.betfair.com/forum/sports-exchange-api/exchange-api/3411-stream-api-questions-contd>):
  «The Exchange Stream API supports GBP currency only». L'amministratore aggiunge che la scelta è definitiva e che
  la conversione spetta al client.

Il REST `listMarketBook` invece risponde nella valuta del conto, qui EUR. Il conto è in EUR: vedi `account`
`available 40.56` sul canale 47331, referto B.

### K1.3 Misura

**Nessun login Betfair nuovo.** Nel sistema non esiste una fonte in EUR con le size del libro già salvata:
- Omega legge il libro CS via REST (`omega_market.read_book` / `read_market`), ma non salva le size da nessuna
  parte: ho controllato `omega_activity` e `omega_trades.meta`.
- Il libro REST del referto B viene da un login PROPRIO della sessione B (`e2e_fase2_z0/semantica_A.py:5,36`).

Quindi **non ho fatto una misura nuova su una fonte EUR indipendente**: per farla servirebbe un login nuovo, oppure
una chiamata anonima all'endpoint pubblico del sito Betfair, che non ho fatto senza permesso.

**Ricalcolo dai dati grezzi di B.** Ho rifatto il calcolo io, con uno script mio (comando in §8), su
`semantica_A.json` + `semantica_A_giro2.json`, prendendo solo le coppie con stesso mercato, stessa selezione, stesso
lato e **stesso prezzo**:
- **94 coppie**.
- Rapporto scan/REST: **mediana 0,8599**, quartili 0,8598-0,8600.
- **69 coppie** nella banda 0,85-0,87: mediana 0,8600, deviazione standard **0,0001**.
- Le altre 25 sono size che il libro ha cambiato fra le due letture.

**Confronto col cambio.** EUR/GBP del 23/09/2026 = **0,8586** (fonte: exchangerates.org.uk, dal risultato di
ricerca). Il rapporto misurato 0,860 è il cambio del giorno (scarto 0,15%, compatibile con il cambio di Betfair o con
il movimento fra il 23 e il 26/09).

Un errore di scala costante con dispersione 1e-4 non è rumore di mercato: è una conversione di valuta.

### K1.4 Dove le size in GBP sono usate come euro

Mappa fatta da un delegato Explore in sola lettura. Le righe dei punti non prudenti le ho rilette io.

Direzione dell'errore: valore GBP = 0,86 × valore EUR, quindi la liquidità risulta **sottostimata del 14%**.

**NON prudenti (money-critical, verificati):**

1. **Chiusure e hedge tagliati alla size GBP.**
   - Dove: `Betfair/safe_strategy/execution.py:660-667`. La riga `if size > avail: size = avail` usa `best_size`
     del feed.
   - Si arriva lì da `close_trade`, `execution.py:1589` → `:1641-1648`.
   - Chi la usa:
     - le uscite Safe (`bot_service.py:3261`, `4010`, `5142`);
     - cash-out, green-up e uscite approvate di Omega (`omega_service.py:5542`, `6405`; `omega_proposte.py:750`);
     - le gambe di chiusura di Mike (`mike/service.py:678/681 → 766`, `best_size=avail_size`).
   - Effetto: quando il libro è il vincolo, la chiusura parte fino al 14% più piccola di quello che il libro
     permetterebbe, e resta **esposizione residua**.
2. **Mike: copertura trattenuta.**
   - Dove: `Betfair/mike/engine.py:3335-3338`.
   - La condizione `bk.back_size + EPS < size` confronta un `back_size` in GBP con una copertura in EUR e produce
     `LIVE_UNCOVERED` «copertura: liquidita».
   - Effetto: l'Over 4.5 aspetta anche quando la liquidità in EUR basterebbe.
3. **Omega: proposta d'uscita soppressa.**
   - Dove: `Betfair/omega/omega_v3.py:834-835`. `attuabile = back_size >= sb`.
   - Il `return … "controparte_insufficiente"` a `:1030` viene PRIMA dei rami `cap` (`:1037`) e `rischio`.
   - Effetto: anche un'uscita per tetto di rischio non viene proposta. L'input viene dal feed (via
     `omega_proposte.py:371 → 408`).
4. **UI: il pulsante Approva di un'uscita si disabilita.**
   - Dove: `frontend/src/lib/controlRoomProposte.ts:224-231` (`abbinabileSufficiente`) e `:324-325`, usati da
     `SchedaChiusura.tsx:131`.
   - Le size vengono dal canale 47331 o dallo scanner, quindi in GBP.
   - Effetto: blocca l'approvazione di una chiusura urgente quando la liquidità in EUR basterebbe.
5. **Omega: pavimento di rischio del green-up.**
   - Dove: `omega_service.py:6103`, dove `quote_p(back, back_size)` con `MARKET_QUOTE_MIN_SIZE` = 2 dà `p_mkt`
     `None`.
   - Effetto: il pavimento a `:6125-6135` salta e la probabilità di rischio è sottostimata. Solo nella fascia stretta
     di `back_size` fra circa £1,72 e £2.
   - Un sesto caso è ambiguo: `omega_model.py:653-663`, `quote_p` nel fit λ di mercato (`:853`, `:920`).

**Prudenti (salta ingressi, stake più piccoli, paper che riempie meno):**
- Safe:
  - `engine.py:2123` → `bot_service.py:6418-6421`;
  - `anomaly.py:243-244`, `323-324`;
  - `combos.py:170`, `415`, `444`, `448`;
  - `opportunity.py:990-994`;
  - `tennis_opportunity.py:421-426`;
  - `proposte_opportunita.py:545-547`;
  - `execution.py:660-667` sulle APERTURE;
  - paper `execution.py:752`, `bot_service.py:5390`.
- Omega: `omega_model.py:521-525`, `1136-1140`; `omega_engine.py:151`; `omega_v3.py:641-642`;
  `omega_service.py:2086-2104` e `2562-2564`.
- Mike: `engine.py:2472-2474`, `2824-2826`, `3161-3163`, `3648`.
- Scalper: `scalper_bot.py:986-989`, `1017`, `1225-1227`; `theta_bot.py:732`, `1026`.
- Tennis: `tennis_scalper_bot.py:1199`, `1202`; `tennis_flb_bot.py:304`, `344`; `tennis_pro_bot.py:481`, `680`;
  `tennis_swing_bot.py:529`.
- Segnali: `live_engine_pro.py:609`, `616-617`.
- flumine: `SimulatedExecution` (paper del runner) abbina ordini in EUR contro un libro in GBP, quindi il paper
  riempie meno del live.

**Solo a video (simbolo € su importi in GBP, circa −14%):**
- `lib/safeStrategy.ts:418-420` («€ abbinabili»);
- `SignalCard.tsx:256`;
- `OpportunityGroup.tsx:225-240`, `278`;
- `SchedaPropostaOpportunita.tsx:138-145` (blocca l'approvazione di un'apertura: prudente);
- `MissionCard.tsx:206`, `376-390`;
- `MikeMatchCard.tsx:295`, `300`, `774`;
- `SchedaPartita.tsx:358-361`;
- `Board.tsx:175` (qui misto REST/stream);
- `TennisMatchesList.tsx:80`, `467`;
- testi `engine.py:1236`, `1325`, `1436`, `1626-1634`.

**Effetto collaterale sul paper.** Il paper è PEGGIORE del live di circa il 14% sui riempimenti vincolati dal
libro. Le statistiche paper sono distorte in modo prudente.

---

## Tabella id → esito

| id | esito | in breve |
|---|---|---|
| 7.1.1 | **PASS** | lo scalper legge `safe_strategy_scan`: 79/81 passi con conteggio identico al mio, 2 differenze spiegate dal ritardo del giro; 7 partite armate, tutte dal feed |
| 7.1.2 | **PASS** sulla fonte · **FAIL candidato R-FA-1** sul rilascio | la fonte è `safe_strategy_scan`: 295/328 identici, 33 differenze di ±1-3 legate al ritardo di lettura. Dalle 09:26 però le partite finite restano armate (vedi R-FA-1) |
| 7.1.3 | **NON CERTIFICATO** | la soglia di 30 s è uguale nei 3 moduli (codice), ma lo scanner non è mai stato vecchio: età massima 15,4 s. Fermarlo non è in sola lettura |
| 7.1.4 | **NON CERTIFICATO (porta spenta)** | il proattivo dell'auto-follow non legge mai il feed: `attori []`, `letto None`, `partite 0` in 91/91 letture dell'hello 47331. Nasce solo con attori `safe`/`omega` sul canale di comando (`auto_follow.py:91`, `862-876`) |
| 7.3.2 | **PASS** (senza log) | il motore a domanda gira: 9→78 leghe v4 su DB, cicli ogni ~10-13 min, tetti 10 leghe a ciclo e 40 l'ora rispettati. Log `[atlante-domanda]` non leggibile (console non salvata, K2 di B) |
| 7.3.3 | **PASS** + osservazioni | `hazard_atlas_leghe` 0 → 78 righe con v4 (14:39 UTC); ordine di preparazione ricalcolato da me = quello del motore. Oss.: le leghe in gioco vengono dopo quelle di ieri (O-1) |
| 7.3.5 | **FAIL** (R-FA-2) | `hazard_versione`, `hazard_fase`, `hazard_recupero_atteso_min` (e `hazard_nota`) **non arrivano mai** in `mike_events.live`: 0/166 frame |
| 7.3.6 | **NON CERTIFICATO** | dipende da 7.3.5 (chiavi assenti); inoltre nessuna partita di Mike in recupero 2T nella finestra |
| 7.9.1.A | **PASS parziale + K1** | canale 47336 = DB su 5.263/5.263 righe, 0 righe perse, libro plausibile su 23.820 righe; prezzi uguali al REST (dati di B); size in GBP (K1). Libro Betfair vero non interrogato da me |
| 7.9.3.B | **PASS** (ricalcolo indipendente) con 2 osservazioni | grezzo→stato identico (4 leghe), stato→blocco entro l'arrotondamento, consultazione 0/204.525 differenze, tempo sugli IPS reali 0/2.993 differenze, valore Mike 162/166 (4 spiegati) |

---

## §7.1 Feed unico

Metodo: `sonda_feed_atlante_71_monitor.py`, un passo ogni 60 s dalle 09:08 alle 10:57 UTC (108 passi), più un passo
alle 14:39. Analisi con `sonda_feed_atlante_71_analisi.py`.

A ogni passo ho ricontato il feed da `safe_strategy_scan` con i filtri dichiarati dai consumatori, **reimplementati
da me**:
- scalper: `mo_market_id`, `mo_status≠CLOSED`, casa e trasferta presenti;
- tennis: `mo_market_id`, `mo_status≠CLOSED`;
- auto-follow: `mo_status≠CLOSED` e almeno un mercato.

Poi ho confrontato i conteggi con la nota del servizio.

### 7.1.1 Scalper

**Conteggio.** `stats.auto.feed` = `{fonte: safe_strategy_scan, letto: true, vivo: true, partite: N, eta_scanner_s}`.
N è uguale al mio in **79/81** passi a scalper acceso. Le 2 differenze:
- 09:57: 12 contro 11;
- 10:00: 4 contro 6.

Cadono proprio mentre le partite giapponesi finivano, con `giro_at` 1-18 s prima della mia lettura.

**Età.** `eta_scanner_s` massima 11,9 s, coerente con il battito dello scanner (10-12 s; massimo che ho osservato
15,4 s).

**Partite armate.** Le sessioni `origine='auto'` sono 7 (vedi la tabella sotto). Tutte erano nel feed al momento
dell'armamento, e nel giusto ordine: in gioco prima, poi orario di inizio, poi `event_id`. Le prime due, 36090788 e
36090854, sono gli `event_id` minori fra le partite in gioco delle 08:00.

**Uscita dal feed.** A fine partita la sessione passa a `stopped` entro 1-2 passi dall'uscita:
- 36090937: fuori feed alle 09:59:04, `stopped` alle 10:00:05;
- 36090941: fuori alle 10:03:09, `stopped` alle 10:05:11.

È coerente con `ASSENZA_FEED_S = 60` (`scalper/auto_mode.py:86`).

**Esito: PASS.**

**Osservazione per il delegato dello scalper, non mia.** 36090936 e 36090937 sono rimaste `requested` dalle 09:43:33
alle 09:57:02 (14 minuti). Le righe `live_follow` create dallo scalper per le sue sessioni automatiche hanno
`origine='manuale'`: 36090788 e 36090854 alle 09:18.

| event_id | armata | fuori dal feed | stopped |
|---|---|---|---|
| 36090788 | 09:18 | 09:57 | ≤09:57 |
| 36090854 | 09:18 | 09:58 | ≤09:58 |
| 36090936 | 09:43 (running 09:57) | 10:00:05 | 10:01:05 |
| 36090937 | 09:43 (running 09:57) | 09:59:04 | 10:00:05 |
| 36090941 | 10:00 | 10:03:09 | 10:05:11 |
| 36111764 / 36111770 | 10:01 / 10:05 | – | in gioco alle 10:40 |

### 7.1.2 Tennis

**Conteggio.** `stats.auto` di ognuno dei 4 bot porta `fonte: safe_strategy_scan`, `feed_letto`, `feed_vivo`,
`feed_partite`, `feed_eta_s`.
- `feed_partite` è uguale al mio conteggio in **295/328** passi-bot.
- Le 33 differenze sono di ±1-3, tutte con `letto_at` da 6 a 15 s prima della mia lettura.

**Armamento.** I 5 follow `origine='auto'` iniziali (09:17) erano tutti nel feed. Alla fine della finestra i follow
armati erano 12, tutti arrivati dal feed.

**Esito sulla fonte unica: PASS.**

**R-FA-1 (FAIL candidato; tocca 7.7.8 e il tetto).** Le partite di tennis finite restano armate per ore e il tetto
viene superato.

Cosa si vede:
- 36118619 è uscita dal feed alle 09:26 UTC. Alle 14:39 UTC:
  - ha ancora le 4 righe `tennis_bot_control` in `running`;
  - il follow è `STREAMING`;
  - `tennis_live_now.status` = `SUSPENDED`, `inplay` = true (letto alle 14:39:47).
- Alle 14:39 ci sono **7 partite fuori feed** in questo stato, per un totale di **28 righe bot `running`**:
  36112100, 36117297, 36117278, 36116525, 36116721, 36116084, 36118619.
- `stats.auto.armate_feed` = **12 con `tetto` = 5**, per tutti e 4 i bot.

La causa nel codice:
- La fermata di una partita automatica uscita dal feed richiede `_mercato_chiuso(ev)`, cioè `CLOSED`
  (`Betfair/stream/tennis_live/tennis_bot_service.py:494-501`, `565-571`).
- `scegli_partite` conta nel tetto solo le armate ANCORA nel feed (`tennis_live/auto_mode.py:190-191`), quindi
  continua ad armare partite nuove.
- Un mercato di tennis finito che resta `SUSPENDED` (in attesa di regolamento) non viene mai rilasciato: la partita
  occupa il runner e il tetto dichiarato diventa di fatto illimitato.

Non corretto. Da portare al delegato di §7.7 e all'utente.

### 7.1.3

La soglia è la stessa di 30 s in tutti e tre i moduli:
- `scalper/auto_mode.py:89` `SCANNER_VIVO_S = 30.0`;
- `tennis_live/tennis_bot_service.py:632` `_SCANNER_VIVO_S = 30.0`;
- `auto_follow.py:459` `SCANNER_VIVO_S = 30.0`.

Dal vivo lo scanner non ha mai superato i 30 s di età (massimo 15,4 s su 108 passi). Provocarlo significa fermare lo
scanner, che non è un'azione di sola lettura.

**NON CERTIFICATO.**

### 7.1.4

L'hello del canale 47331 (`auto_follow`) in **91/91** letture riporta:
- `feed: {letto: null, partite: 0, fonte: db, attori: []}`;
- `mercati_auto 0`.

Il proattivo parte solo con un attore `safe` o `omega` collegato a `/comando/`
(`auto_follow.py:91`, `:862-876`; `runner.py:1693-1706`). Quegli attori ci sono solo con `SAFE_ORDINI_VIA_CANALE` o
`OMEGA_ORDINI_VIA_CANALE` accesi.

Come riferimento, il valore che F avrebbe col mio conteggio (filtro dell'auto-follow): 19 partite alle 09:08, 2 alle
14:39.

**NON CERTIFICATO (porta spenta).** Coincide con K3 del referto B.

---

## §7.3 Atlante v4

### 7.3.2 — il motore a domanda gira (PASS, senza log)

Evidenza da file e DB (`sonda_73_stato.jsonl`, 12 fotografie):

| ora UTC | leghe v4 sul DB | leghe v4 con forza | stato locale | in preparazione | leghe in gioco | … con v4 |
|---|---|---|---|---|---|---|
| 09:06 | 9 | 9 | 9 | 294 | 25 | 0 |
| 09:18 | 19 | 17 | 19 | 284 | 25 | 2 |
| 09:28 | 29 | 25 | 29 | 274 | 25 | 4 |
| 09:38 | 35 | 31 | 35 | 267 | 26 | 4 |
| 10:09 | 46 | 36 | 46 | 256 | 34 | 5 |
| 10:19 | 56 | 41 | 56 | 246 | 32 | 7 |
| 14:39 | 78 | 61 | 75 | 227 | 157 | 42 |

**Cicli** (`generated_at`, poi mtime del file finale): 08:57:01→08:59:28, 09:09:28→09:12:08, 09:22:09→09:25:22,
09:35:24→09:38:21, 09:48:24, 09:58:33, 10:13:17, 10:24:58, 14:38:19.
- Passo di 600 s dopo la fine del ciclo precedente (`hazard_atlas_sync.py:180`).
- Durata del ciclo 2,5-3 min con 10 leghe nuove.
- Tetti rispettati: 10 leghe a ciclo, poi 7, 1, 1 quando si avvicina la soglia di 40 l'ora
  (`calcolate_ts` 13→23→33→39→40, poi 27 quando la finestra mobile si svuota).

**Log non leggibili.** `[atlante-domanda] …` finisce nella console dell'app, che non è salvata (K2 di B). I costi per
lega (richieste e righe) sono solo nel log: **NON misurati**.

**Costi misurati:**
- 23 righe su `hazard_atlas_leghe` pesavano 2,34 MB JSON, media 101 KB. La lega 10 (Friendlies) da sola pesa 633 KB.
- Una GET di tutte le righe impiega 7,6 s: nessuno lo fa in produzione; il motore legge una lega alla volta.

**Scritture sul DB a blocchi**, come da progetto (`atlante_a_domanda.py:477-488`, `scrivi_db_ogni_h=6`):
- le leghe aggiornate dopo il calcolo iniziale restano in `da_scrivere`;
- alle 09:18 erano 11;
- di conseguenza la riga DB di 501 e 536 è indietro rispetto al file locale (vedi 7.9.3 A).

**Oss. O-3: race fra i due file.** Il motore scrive `hazard_atlas_live.json` due volte per ciclo con lo stesso
`generated_at`:
- all'inizio, per dichiarare le leghe «in preparazione» (`:444`);
- alla fine (`:492`).

Il file di stato viene salvato dopo il secondo. In 2 fotografie su 12 (09:59 e 10:25) stato e live erano
disallineati: `coerenza_file_db False`. Nessun effetto sui bot, che leggono solo il live: da sapere per chi
confronta.

### 7.3.3 — righe v4 per lega (PASS)

`hazard_atlas_leghe`: **0 righe** ieri alle 23:00, **78 righe** alle 14:39 UTC, tutte con `stato.v4.affidabile`.
- 61 hanno la forza con `n > 0`.
- Le 17 senza forza sono leghe con tutte le stagioni scartate per copertura eventi: ad esempio 353, 354, 645, 785, …
  con `stagioni_scartate` fra 0 e 0,05.
- Queste 17 non entrano nel blocco pubblicato (`genera_atlante.py:545-563`, «almeno una partita»).

**L'ordine di preparazione ricalcolato da me** è identico all'insieme calcolato dal motore:
- metodo: leghe di `fixture_predictions` in [ora−36 h, ora+36 h], ordinate per primo calcio d'inizio
  (`atlante_a_domanda.py:421-436`);
- prime 10 attese: 501, 243, 906, 1037, 267, 536, 917, 239, 263, 339;
- motore: le stesse 9 calcolate più la 1037 `senza_dati`.

**Oss. O-1 (portare all'utente): la lega che si gioca ORA non ha la precedenza.** Il commento del codice dice «in-play
in testa» (`:428`), ma l'ordinamento è per il PRIMO calcio d'inizio nella finestra, che parte da 36 ore indietro.
- Alle 09:06 le 25 leghe con partite in gioco stavano in media alla **posizione 109 di 304** nella coda; la prima era
  alla 14.
- Alle 10:19 solo 7 leghe su 32 in gioco avevano il v4; alle 14:39, 42 su 157.
- Alle 14:39 `calcolate_ultima_ora` era 0: nessuna lega calcolata nell'ultima ora (guasto di rete fra le ~10:56 e le
  ~14:37).
- Con il tetto di 40 leghe l'ora, una lega di oggi pomeriggio può aspettare ore dietro a leghe che hanno giocato ieri
  sera.
- Nel frattempo i bot usano il ripiego v3, dichiarato, oppure il globale v4.

### 7.3.5 — FAIL (R-FA-2)

**Cosa è osservato.**
- `mike_events.live` in gioco (Liga F 36111764 e 36111770, dalle 10:00 UTC): **166 frame**, di cui **0 con
  `hazard_versione`, `hazard_fase`, `hazard_recupero_atteso_min`, `hazard_nota`**.
- Le uniche chiavi presenti sono `hazard`, `hazard_atlas`, `hazard_model`. Letto anche il frame intero del
  36111764.

**Dove il codice le perde.**
- `Betfair/mike/dossier.py:340-348` le calcola.
- Il frame live costruito in `Betfair/mike/service.py:3795-3820` (`ev["live"] = {...}`) copia solo
  `"hazard": snap.hazard, "hazard_atlas": live.get("hazard_atlas"), "hazard_model": …`.
- Nessuna riga di `service.py` copia `hazard_versione`, `hazard_fase` o `hazard_recupero_atteso_min`: il grep trova
  quelle chiavi solo in `dossier.py`.
- `hazard_nota`, `hazard_n` e `hazard_recupero_atteso_min` sono elencate fra i volatili (`service.py:479-484`), ma
  non vengono mai messe nel frame.

**Conseguenze.**
- La scheda di Mike non può dichiarare «v4» o «v3» né la fase.
- La certificazione 7.3.5 e 7.3.6 non è possibile.
- I test del 25/09 verificano `live_frame` del dossier, non il frame persistito.

**Il VALORE invece è giusto: vedi 7.9.3.**

**Oss. R-FA-3, da portare al delegato di Mike.** Per le due partite di Liga F il dossier ha `league_id`,
`home_team_id` e `away_team_id` tutti `null` (`source: none`), anche se `fixture_predictions` 1573593 ha lega 142 e
id squadra 19896/22018.
- `dossier.py:84-94` valorizza lega e id squadra solo se esistono i λ (`fixture_lambdas`).
- Mike consulta quindi l'atlante sul **globale v4**, senza lega e senza forza.

### 7.3.6 — NON CERTIFICATO

Due motivi:
- le chiavi del frame sono assenti (7.3.5);
- nella finestra nessuna partita di Mike è arrivata al recupero del 2T.

La volatilità è certificabile solo dopo la correzione di R-FA-2.

---

## §7.9.1 — Feed unico: dati veri?

`sonda_feed_atlante_791_feed.py 25`, dalle 09:14 alle 09:39 UTC: 24.156 messaggi dal canale 47336 e 6.720 letture
DB indipendenti (una ogni 8 s), su 40 eventi.

**Stessa riga canale ↔ DB.**
- 5.263 coppie `(event_id, updated_at)` viste da tutte e due le parti: **identiche 5.263/5.263** su quote, minuto,
  punteggio, set, game, `odds_ts_ms` e `odds_pt_ms`.
- Righe DB mai viste sul canale: **0/5.149**.
- Una nota sul metodo: PostgREST toglie gli zeri finali dei microsecondi (`.24813` contro `.248130`). Il confronto va
  fatto sull'istante, non sul testo.

**Età.**

| misura | p50 | p95 | max |
|---|---|---|---|
| ricezione − `updated_at` | 0,073 s | 0,176 s | 1,13 s |
| `updated_at` − `odds_pt_ms` (pubblicazione Betfair → scrittura) | 1,44 s | 10,1 s | 42 s |

`odds_ts_ms` non è mai successivo a `updated_at` (0 casi).

La coda lunga (p95 10 s) è una riga riscritta senza variazioni di prezzo: il libro non si è mosso. Senza il libro
vero non si distingue da un prezzo vecchio.

**Plausibilità del libro, 23.820 righe:**
- 0 prezzi fuori dalla scala dei tick Betfair;
- 0 casi con back ≥ lay;
- 0 size nulle;
- 0 arbitraggi impossibili (somma 1/back < 0,99 o somma 1/lay > 1,01 su mercato OPEN).

**Contro il libro vero.**
- Non l'ho interrogato io: serve una sessione Betfair, fuori perimetro.
- Il canale 47331 non pubblica libri per queste partite: il runner era in attesa, con 0 mercati seguiti alle 09:08.
- Non esistono registrazioni `_live_raw` di oggi (le ultime sono del 24/09).
- I dati REST della sessione B (login proprio), ricalcolati da me, danno: prezzi uguali sul miglior livello salvo
  movimenti di 1-2 tick entro l'età della riga; **size in GBP (K1)**.

**Esito: PASS** su trasporto, età e forma del libro. **KO K1** sull'unità delle size.

---

## §7.9.3 — Atlante v4: ricalcolo indipendente

Script: `sonda_feed_atlante_793_ricalcolo.py 917 501 267 536`, ultima esecuzione alle ~10:30 UTC. Ogni livello è
implementato da me; la produzione è importata solo nel livello C, come termine di confronto.

**A. Dati grezzi → stato.** Ho riletto dal DB `matches` (con `extra` da `raw_json`) e i gol da `match_events`, poi
ho ricostruito da solo gli stati partita-minuto.
- **917** (143 partite, 574 gol): file locale e DB **identici**, per celle n/s2/s3, rec2, durate, `n_fixtures` e gol
  in ogni stagione.
- **267**: identica, su file e su DB.
- **501**: il file locale è identico. Il DB non ha ancora la stagione 2026: 1 partita aggiunta dall'incrementale, che
  il DB riceverà al prossimo blocco di 6 ore (per progetto).
- **536**, stagione 2025: il mio totale è 504 contro 534 della produzione (+30 partite-minuto). **Spiegato e
  riprodotto**: ricalcolando con la regola incrementale («affidabilità dai conteggi CUMULATI della stagione fino a
  questa partita»), il risultato è **identico** (534, differenza massima 0).

**Oss. O-2 (portare all'utente, è di progetto e non un difetto di codice).**
- **Le prime partite di una stagione vengono sempre contate come affidabili.** Lo stato è `quota [1,1]`, `[1,3]`,
  `[1,4]`: sotto i 5 gol di fine tempo la stagione è «presunta affidabile». Nella 536/2025 le prime 5 partite su 6
  sono state contate con gli stati di fine tempo, poi la stagione è diventata NON affidabile (3/6 = 0,5).
- **La decisione non è retroattiva.** L'incrementale mette proprio le distorsioni che il reperto 6 voleva evitare.
- **Stagione scartata ma contata.** La stessa stagione era stata scartata dal bootstrap per copertura eventi 0,556 <
  0,6, eppure l'incrementale ne ha contato le partite dentro la finestra.

**B. Stato → blocco pubblicato** (`hazard_atlas_live.json`, 44 leghe alle ~10:30). Ho rifatto io:
- pesi con emivita 3;
- globale sulle leghe affidabili, con i ripieghi delle celle di recupero vuote;
- shrinkage con K 1500;
- `r_rec2`;
- `pi_durata` con il metodo dei momenti;
- gol medi;
- forza arrotondata a 7 decimali.

Le differenze massime, per voce:

| voce | diff. massima | tolleranza |
|---|---|---|
| p2 | 4,99e-8 | 5e-8 |
| p3 | 5,0e-8 | 5e-8 |
| n | 0,05 (1 decimale) | 0,05 |
| r_rec2 | 5e-8 | 5e-8 |
| pi_durata | 5e-8 | 5e-8 |
| gol_medi | 4,9e-6 (5 decimali) | 5e-6 |
| forza | 0 | – |

Inoltre `stagione_rif` 2028 = 2028 e `k_durata` identico.

**Esito: PASS.** Le tolleranze sono quelle dell'arrotondamento con cui il blocco viene pubblicato
(`atlante_v4._r`).

**Oss.** Le leghe 36, 850 e 637 hanno già una stagione 2027 (stagioni di calendario come «anno di inizio+1»?), quindi
`stagione_rif` = max + 1 = 2028 per TUTTE le leghe. Le stagioni 2025-26 delle altre leghe pesano 0,5^(2/3) anziché
0,5^(1/3).
- È la regola di `genera_atlante.py:562` («riferimento S+1 sull'ultima contata»), unica per tutto l'atlante.
- Il banco di validazione aveva un solo calendario: questa è una deriva dei pesi rispetto al validato.
- Da portare all'utente, non corretta.

**C. Consultazione.**
- Griglia completa:
  - 44 leghe v4, più una lega del v3 fuori dal v4, una lega ignota e `None`;
  - minuti 0-100, gol 0-4, tempo None/1/2, con e senza id squadra.
- Risultato: la mia consultazione contro `consulta_atlante_v4` di produzione dà **0 differenze su 204.525 casi**, su
  versione, fase, p2, p3 (1e-12), recupero atteso e forza usata.
- Ripiego v3 con motivo dichiarato: uguale.
- **Tempo sugli IPS reali**: il mio `mio_tempo` contro `tempo_da_payload` di produzione su **2.993 stati reali**, 0
  differenze. Le fasi viste dal vivo:
  - `KickOff` → tempo 1, fase regolare: 198;
  - `SecondHalfKickOff` → tempo 2, regolare: 2.397;
  - `SecondHalfKickOff` al 90'+ con `elapsedAddedTime` → **recupero_2T**: 351;
  - `Finished` → recupero_2T: 47.
- Il recupero del 1T e l'intervallo (`FirstHalfEnd`) non sono stati campionati: le partite giapponesi erano già nel
  2T quando ho iniziato, quelle di Liga F nel 1T quando si è interrotta la rete.

**D. Contro il bot** (Mike; Safe non ha scritto note con l'atlante nella finestra).
- 166 frame in gioco di Mike ricalcolati con la mia consultazione, con gli STESSI input: lega e id del dossier
  (null), minuto e gol del frame, tempo dall'IPS più vicino.
- L'atlante è la versione che Mike aveva in quel momento: copia salvata al cambio di mtime.
- **`hazard_atlas` uguale sul 4° decimale in 162/166.**
- I 4 diversi (10:15:15, 10:15:16, 10:39:34 ×2) coincidono **esattamente** con la versione PRECEDENTE dell'atlante,
  scritta 5 s prima del frame. È il ritardo di ricarica della cache condivisa (`hazard_atlas.py:69`
  `MTIME_CHECK_S = 60`), dichiarato. Esempio al 38': 0,0842 / 0,0951 contro 0,0848 / 0,0944.
- Versione e fase non sono confrontabili: sono assenti dal frame, R-FA-2.

**Esito 7.9.3.B: PASS** sul valore e sul ricalcolo. Restano fuori versione e fase del frame (R-FA-2), la nota di Safe
(mai emessa) e il recupero del 1T.

---

## Elenco dei FAIL (evidenza + file:riga, nessuna correzione)

- **K1.** Size, volumi e `total_matched` dello stream sono in GBP e vengono usati come EUR, senza conversione.
  - Origine: `safe_strategy/scanner.py:250-259`, `service.py:835,933,979`.
  - Non prudenti: `execution.py:660-667` sulle chiusure, `mike/engine.py:3335-3338`, `omega_v3.py:834-835,1030`,
    `controlRoomProposte.ts:224-231,324-325`, `omega_service.py:6103,6125-6135`.
  - Misura: mediana 0,860 su 94 coppie, cambio 0,8586. Documentazione Betfair: «Market subscriptions are always in …
    GBP».
- **R-FA-1.** Tennis: le partite finite con mercato `SUSPENDED` restano armate per ore; tetto 5, armate 12.
  - `tennis_live/tennis_bot_service.py:494-501,565-571`; `tennis_live/auto_mode.py:190-191`.
  - Evidenza: 7 eventi, 28 righe `running` alle 14:39 UTC.
- **R-FA-2.** Mike: `hazard_versione`, `hazard_fase`, `hazard_recupero_atteso_min` e `hazard_nota` non entrano in
  `mike_events.live`.
  - `mike/service.py:3795-3820` contro `mike/dossier.py:340-348`.
  - Evidenza: 0/166 frame.

## NON CERTIFICATO (motivo)

| id | motivo |
|---|---|
| 7.1.3 | scanner mai più vecchio di 30 s (massimo 15,4 s); provocarlo non è sola lettura |
| 7.1.4 | porta spenta: proattivo inerte senza attori sul canale di comando |
| 7.3.6 | chiavi assenti (R-FA-2) e nessun recupero 2T di Mike osservato |
| costi per lega del motore (richieste, righe) | solo nel log, console non salvata |
| 7.9.1 contro il libro vero | nessuna sessione Betfair mia |
| misura K1 su una fonte EUR indipendente e nuova | richiederebbe un login o una chiamata nuova a Betfair |
| recupero del 1T e intervallo con IPS reale | nessun campione |
| nota di Safe con «atlante v4 / v3» | Safe non ne ha emesse nella finestra (solo proposte `anomaly`) |

## Osservazioni (da portare, nessun FAIL)

- **O-1.** Coda dell'atlante ordinata per il primo calcio d'inizio fra −36 h e +36 h: le leghe in gioco non vanno in
  testa, contrariamente al commento (`atlante_a_domanda.py:428,436`). Alle 14:39, 42 leghe in gioco su 157 avevano il
  v4.
- **O-2.** Affidabilità incrementale non retroattiva e stagioni scartate per copertura ma contate dall'incrementale
  (536/2025).
- **O-3.** Il file live viene scritto 2 volte per ciclo con lo stesso `generated_at`; stato e live sono disallineati
  per qualche minuto.
- **O-4.** `stagione_rif` unica per tutto l'atlante (2028, per via di 3 leghe con una stagione 2027): pesi per età
  spostati per tutte le altre leghe.
- **R-FA-3.** Dossier di Mike senza lega e id squadra quando mancano i λ (`mike/dossier.py:84-94`): atlante sul
  globale, forza non usata.
- **Per il delegato dello scalper:**
  - `live_follow` delle sessioni automatiche dello scalper con `origine='manuale'`;
  - due sessioni rimaste `requested` per 14 minuti.
- `hazard_atlas_leghe.league_name` è NULL (già M5 di B).

## Comandi per rifare le verifiche

Tutti dalla cartella `AUDIT_2026-09-25/e2e_fase2`, con `../../.venv/Scripts/python.exe`.

```
sonda_feed_atlante_73_stato.py
sonda_feed_atlante_71_monitor.py 0
sonda_feed_atlante_71_analisi.py
sonda_feed_atlante_791_feed.py 25
sonda_feed_atlante_793_ips.py <min> 15
sonda_feed_atlante_793_bot.py <min> 20 <dir_copie>
sonda_feed_atlante_793_ricalcolo.py 917 501 267 536
sonda_feed_atlante_793_confronto_bot.py <dir_copie>
```

Nota su `sonda_feed_atlante_73_stato.py`: accoda la fotografia a `sonda_73_stato.jsonl`.

K1, ricalcolo sui dati di B: script in linea che rilegge `../e2e_fase2_z0/semantica_A*.json` e tiene solo le coppie
con prezzo uguale. Righe chiave: `s[side]==b[side]` e `s[side+'_size']/b[side+'_size']`.
