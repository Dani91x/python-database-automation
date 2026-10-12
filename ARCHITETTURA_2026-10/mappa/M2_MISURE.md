# M-2 - Misure della mappatura dei flussi (11/10/2026)

Agente M-2 della mappatura dei flussi reali. Ramo `mappa/m2-misure` da `a3a58ad8` (cima di master), NON pushato.
Mandato: completare le due misure di riferimento della matrice di parita' (`ondata2/MATRICE_PARITA.md` par. 2, ramo
`claude/architettura-tappa0`): **M1** messaggio Betfair -> ladder A SCHERMO (calcio e tennis) e **M2** decisione ->
risposta di `placeOrders` per TUTTI gli attori, piu' le misure utili alla v2 (messaggi mcm/ocm al secondo, stream e
connessioni, latenza del canale locale, peso REST). Entra su master dopo la firma del PC.

## 0. Regole rispettate

- **Stesso interruttore della Salute** (`MONITOR_SALUTE=0|1`, di serie 0; T0A, `Betfair/monitor/COSA_FA.md` par. 6).
  Spento = nessun campo, nessuna scrittura, nessun timer, comportamento identico (provato: test "spento" per ogni
  misura, banco prima/dopo identico, fotografia di parita' invariata). Nel banco e' spento per costruzione (T0A).
- **Solo aggiunte**, zero cambi di comportamento di bot e ordini; nessuna connessione, nessun processo, nessun
  thread nuovo nei servizi Python. La pagina usa il canale locale GIA' aperto col runner (nessuna lettura nuova,
  nessuna scrittura nel DB dalla pagina).
- **Ogni errore delle sonde e' catturato**: funzioni best-effort; in piu' gli handler di log della Salute ora
  catturano anche le eccezioni di `emit` (`logging.Handler.handle` non lo fa: prima un `emit` storto sarebbe
  risalito fino a flumine o al worker ordini) - `sonde.py:723-730`.
- **Paper e live mai sommati** (chiave `.<modo>` in ogni tratto di M2), **calcio e tennis mai mischiati** (la riga di
  `monitor_metrics` porta lo sport del processo; il referto raggruppa per sport).
- **Dominio**: `Betfair/monitor/**`, righe d'aggancio nei servizi, `frontend/src` per la misura a schermo. Il
  percorso dello stream ordini e delle chiamate REST degli ordini (dominio di M-1) NON e' toccato: M2 si legge dalle
  righe `tempi_ordine` che quel percorso scrive gia' (handler di log, zero agganci).

## 1. Le misure nuove: cosa, dove, come si legge

Tutte finiscono nella riga di `monitor_metrics` del processo (ogni 30 s; `metriche.contatori`, `metriche.tratti`,
`metriche.valori`; nessuna colonna nuova, nessuna migrazione), nella copia locale `_logs/monitor/<giorno>/<servizio>.jsonl`,
nella pagina "Salute" (tabella "Tratti misurati": i nomi nuovi hanno la loro spiegazione, `frontend/src/lib/salute.ts`)
e nel referto giornaliero (`python -m Betfair.monitor.referto ...`, sezioni "M1", "M2", "Canale locale, stream e REST").
I tratti sono istogrammi a secchi fissi (`registro.BORDI_MS`): p50/p95/p99 al bordo del secchio, sommabili fra finestre e processi.

### 1.1 M1 - messaggio Betfair -> ladder a schermo (calcio E tennis)

| Tratto (ms) | Tratta di M1 | Orologi | Dove nasce | Processo |
|---|---|---|---|---|
| `feed_rx_pt_ms.<sorgente>` | a. `pt` -> arrivo nel processo | Betfair/PC (contiene lo scarto) | T0A, invariato | runner calcio, runner tennis, scanner |
| `ladder_pub_pt_ms` | `pt` -> ladder pubblicato | Betfair/PC | T0A (calcio); **ora anche tennis** | runner calcio/tennis |
| `ladder_rx_pub_ms` **nuovo** | b. arrivo nel processo -> ladder pubblicato | PC/PC | `sonde.marca_ladder` (`sonde.py:243-280`) con `rx_di_pt` (`:351-381`) | runner calcio/tennis |
| `pagina_canale_ms` **nuovo** | c. ladder pubblicato (`ts_pub_ms`) -> arrivo del push nella pagina | PC/PC (Date.now) | `frontend/src/lib/misuraSchermo.ts::notaArrivoLadder` | pagina -> riga del runner dello sport |
| `pagina_dipinto_ms` **nuovo** | d. arrivo nella pagina -> primo frame dopo il commit della riga | performance.now | `misuraSchermo.ts::segnaDipinto` via `useMisuraDipinto` (useLayoutEffect + requestAnimationFrame) | idem |
| `pagina_pub_dipinto_ms` **nuovo** | pubblicato -> frame | PC/PC | idem | idem |
| `pagina_rx_dipinto_ms` **nuovo** | **M1 sul PC: arrivo nel processo -> frame** (il numero da confrontare con BA, p95 <= 20 ms) | PC/PC | idem | idem |
| `pagina_pt_dipinto_ms` **nuovo** | `pt` di Betfair -> frame | Betfair/PC (contiene lo scarto, U-62) | idem | idem |

Contatori: `ladder.pubblicati_canale` (T0A); `pagina.{push_ladder, dipinti, riassunti_accolti, riassunti_rifiutati}`.

Come funziona:
1. `osserva_stream` (gia' agganciato da T0A nei listener calcio/tennis/scanner) ricorda per ogni `pt` di un mcm
   l'istante d'arrivo (`_RX_PT`, OrderedDict con tetto `RX_PT_MAX = 4096`, conta il PRIMO arrivo).
2. `marca_ladder` (copia della riga per il CANALE, mai la riga del DB) aggiunge `rx_ms` accanto a `ts_pub_ms`/`pt` e
   misura `ladder_rx_pub_ms`. Il ladder del **tennis** ora passa dalla stessa funzione (`tennis_runner.py:1509-1511`).
3. La pagina (solo con la build a `MONITOR_SALUTE=1`): all'arrivo di un push `ladder` (`localChannel.ts:292`) annota
   arrivo e marche per mercato; il ladder (`LadderView.tsx:1530`) dopo il commit chiede UN frame e lo segna. Un push =
   una misura; due push fusi in un render contano una volta (l'ultimo); al massimo `MAX_ARRIVI = 500` mercati in attesa.
   **Revisione 11/10 (I-1)**: il frame chiude l'arrivo SOLO se la riga dipinta e' quella arrivata (stesso
   `ladder.updated_ms`, che e' identico su canale e DB per lo stesso book) e se l'arrivo ha meno di
   `ETA_MAX_ARRIVO_MS = 2000` ms; gli arrivi piu' vecchi (mercati senza ladder montato) si scartano a ogni arrivo nuovo
   e si contano in `pagina.scartati`. Prima un ladder aperto 40 s dopo l'ultimo push (riga letta dalla cache,
   `localTransport.ts:122`) o una riga dal ripiego DB chiudevano un arrivo vecchio: `pagina_dipinto_ms` = 40000, falso.
   Dopo l'invio del riassunto si azzerano i numeri, non lo sport: un arrivo in volo resta abbinabile (M-3).
4. Ogni 30 s la pagina manda un RIASSUNTO per sport (stessi bordi dei secchi del Python: un test li confronta e il
   Python rifiuta un riassunto con bordi diversi, catalogo PSB par. 7 n.33) come richiesta `salute` sul canale del
   runner gia' aperto (47331 calcio, 47332 tennis). Il runner lo valida PER INTERO (versione, bordi, nomi ammessi,
   `n` = somma dei secchi, numeri finiti, tetto 100.000; **revisione 11/10 (M-1)**: lunghezza dei bordi controllata
   PRIMA di leggerne gli elementi, ogni valore entro `VALORE_MAX_MS = 1e7`, `min <= max`, `n*min <= somma <= n*max`,
   primo e ultimo secchio pieni coerenti con `min` e `max`) e lo fonde nel suo registro (`sonde.misure_pagina`,
   `sonde.py:457-500`; `registro.Registro.fondi`, `registro.py:151-170`): tutto o niente. Mai in coda comandi, nessun
   token, nessun parametro d'ordine. Canale giu': il riassunto si scarta (la misura non aspetta).

Scelta dichiarata (la via piu' semplice fra le due proposte): **riassunto sul canale gia' aperto**, non scrittura in
`monitor_metrics` dalla pagina (la tabella e' owner-only in lettura e scritta dal `service_role`; dalla pagina
servirebbero una policy o una RPC nuove e una scrittura nuova del guscio).

### 1.2 M2 - decisione -> risposta di placeOrders, per TUTTI gli attori

| Attore | Strada di oggi | Istante della decisione | Cosa misura M-2 | Tratti |
|---|---|---|---|---|
| Omega, Safe | coda DB (`betfair_live_order_requests`) | `emesso_ms` nei params (T0A, `marca_emesso`) | righe `tempi_ordine` strada=coda lette per attore | `decisione_invio_ms`, `invio_presa_ms`, `presa_place_ms`, `place_risposta_ms`, `decisione_risposta_ms` `.<attore>.coda.<modo>` |
| Omega, Safe, **Mike** (paper) | `/comando/<attore>` del motore ordini | `creato_ms` del comando (GIA' nel protocollo, chiave obbligatoria; `motore_ordini.py:1040-1042` lo passa a `tempi_ordine`) | righe `tempi_ordine` strada=comando | idem `.<attore>.comando.<modo>` |
| **Clic del desktop** (calcio e tennis) | canale `order` (47331/47332) | **`emesso_ms` nuovo**: `Date.now()` preso PER PRIMO in `localOrderApi.send` (`localTransport.ts:439-442`, campo in `:453`), solo sul canale e solo a monitor acceso | `drenate` (`sonde._clic_del_desktop`, `sonde.py:213-231`): clic -> arrivo sul canale, clic -> presa del worker; e le righe `tempi_ordine` strada=canale/tennis (presa -> place -> risposta) | `clic_canale_ms.<modo>`, `clic_presa_ms.<modo>`; `presa_place_ms`/`place_risposta_ms` `.desktop.canale.<modo>` |
| **Scalper calcio** | in processo (`market.place_order` nella sessione flumine) | creazione del pacchetto di flumine (l'ordine nasce nella strategia, stesso thread) | `elapsed_seconds` del pacchetto nel log `execute_place` di flumine (Betfair vero) | `pacchetto_risposta_ms` nella riga `scalper-sessione-*` (referto: `processo:scalper-sessioni`) |
| **Bot tennis** | in processo (runner tennis) | idem | idem | `pacchetto_risposta_ms` nella riga `runner-tennis` (referto: `processo:runner-tennis`) |

**`pacchetto_risposta_ms` e' una misura per PROCESSO, non per attore** (revisione 11/10, M-5): nel runner tennis
convivono i quattro bot e gli ordini manuali, nel runner calcio il motore esegue gli ordini di tutti; il referto lo
scrive nella colonna attore come `processo:<servizio>` e la spiegazione del tratto lo dice.

**Orologi del clic** (revisione 11/10, M-4): `clic_canale_ms` e `clic_presa_ms` confrontano `Date.now()` della pagina
(Chromium: risoluzione al millisecondo) con `time.time()` di Python nello stesso PC. Su Windows con Python < 3.13
`time.time()` ha risoluzione di circa 15,6 ms (orologio di sistema a scatti); da Python 3.13 usa
`GetSystemTimePreciseAsFileTime` (sotto il microsecondo). `time.time_ns()` ha la stessa risoluzione di
`time.time()` e non aiuterebbe; `perf_counter` non e' confrontabile con un orologio di un altro processo. Quindi:
con Python < 3.13 sul PC i tratti del clic hanno un errore fino a ~16 ms per misura, da leggere come tale (la
versione di Python del servizio e' nella riga `sistema.python` del monitor). I tratti dentro un processo
(`presa_place_ms`, `place_risposta_ms`, `pacchetto_risposta_ms`) non hanno questo limite.
| **Mike** (live) | REST in processo (`omega_market.place_order_live`) | in processo | `rest_ms.placeOrders` (T0A, sessione dell'APIClient) | - |

Perche' `marca_emesso` NON e' stato aggiunto a Mike, scalper e bot tennis: Mike in paper porta gia' l'istante della
decisione (`creato_ms`, e il protocollo del motore rifiuta chiavi non previste: `CHIAVI_COMANDO`); scalper e bot
tennis non hanno una coda ne' dei params - decidono e piazzano nello stesso thread, quindi il loro "decisione ->
invio" e' il calcolo della strategia e il resto e' il pacchetto di flumine, misurato dal log che flumine scrive gia'.

Lettura delle righe `tempi_ordine` (handler `_GestoreTempiOrdine`, `sonde.py:840-886`, logger
`Betfair.stream.tempi_ordine`): attore dal `rif` (`attore_da_rif`: UUID della pagina = `desktop`; revisione 11/10
(M-2): solo i prefissi di `ATTORI_NOTI` = mike, omega, safe, risk, scalper, tennis, desktop, ui, cr, ft diventano chiavi,
ogni altro prefisso = `altro`; le chiavi oltre il tetto `MAX_CHIAVI` del registro non spariscono piu' in silenzio ma si
contano in `contatori.registro_scartati`); solo le azioni che PIAZZANO (`place*`,
`greenup`; le altre si contano in `tempi_altre_azioni`). `decisione_risposta_ms` = somma dei quattro tratti quando ci
sono tutti: sulla coda gli orologi misti PC/DB si elidono nella somma (decisione e risposta sono entrambi del PC).
Contatori: `ordini_misurati.<attore>.<strada>.<modo>`, `ordini_emessi.desktop`.

### 1.3 Altre misure per la v2

| Misura | Dove | Come si legge |
|---|---|---|
| **Messaggi mcm e ocm al secondo per processo** | `osserva_stream` (T0A per mcm; **ocm nuovo**: `stream_ocm.<sorgente>` + tratto `ordini_rx_pt_ms.<sorgente>`, `sonde.py:316-322`) | referto: per servizio e sorgente, messaggi totali e al secondo p50/p95/max (conteggio / `finestra_s` di ogni riga) |
| **Stream aperti per processo** | handler `flumine.streams` ("Starting/Stopped <Tipo>Stream <id>", `_segna_stream`, `sonde.py:822-837`) | `valori.stream_aperti.{MarketStream, OrderStream, SimulatedOrderStream...}` (il simulato NON e' una connessione a Betfair); `stream_arresti` |
| **Connessioni allo Stream API aperte** | handler `betfairlightweight.streaming.listener` ("connection_id", `sonde.py:798-801`) | `stream_connessioni.aperte` (una per (ri)connessione); `connectionsAvailable` resta quello di T0A |
| **Latenza del canale locale (pubblicazione -> ricezione nel bot)** | `ts` nella BUSTA di ogni push (`sonde.busta`, `local_channel.py:702-705`) + lettore dello scanner nei bot (`canale_scan.py:443-444`, `sonde.ricevuto_canale`) | `canale_ricezione_ms.<topic>` nella riga del BOT (Mike, Omega, Safe); `canale_pub.<topic>` (push al secondo per processo), `canale_ric.<topic>` |
| **Richieste REST con il loro peso** | `_bf_risposta` (T0A) + `peso_richiesta` (`sonde.py:521-571`, `_pesa_richiesta` `:676-692`) | `betfair_rest_peso.<metodo>` (punti), istogramma `rest_peso.<metodo>` (PUNTI, non ms), `betfair_rest_oltre_peso` (> 200: Betfair rifiuterebbe) |

Tabella dei pesi usata (documento Betfair "Market Data Request Limits", come lo ricordo: **da verificare sul sito**,
non raggiungibile da qui): listMarketBook/listRunnerBook per mercato: senza priceData 2, SP_AVAILABLE 3, SP_TRADED 7,
EX_BEST_OFFERS 5 (x profondita'/3 oltre 3), EX_ALL_OFFERS 17, EX_TRADED 17, EX_ALL_OFFERS+EX_TRADED insieme 17;
listMarketCatalogue: (MARKET_DESCRIPTION 1 + RUNNER_METADATA 1) x maxResults; listMarketProfitAndLoss 4 per mercato;
tetto 200 punti per richiesta.

## 2. Punti toccati (file:riga sul commit `7b74b7e4`)

Le correzioni della revisione (`2bcad9bc`) toccano solo `Betfair/monitor/` e `frontend/src/lib/misuraSchermo*` /
`salute.ts`: le righe dei file d'aggancio qui sotto restano valide; quelle citate dentro `sonde.py`, `registro.py`
e `referto.py` si spostano di qualche riga (i nomi delle funzioni restano).

Fuori da `Betfair/monitor/` (ognuno dietro `_mon.ATTIVO` o `misuraAccesa()`):

| File | Righe | Cosa | Nota |
|---|---|---|---|
| `Betfair/stream/tennis_live/tennis_runner.py` | 87 (import), 1509-1511 | ladder tennis sul canale con `marca_ladder` | riga del DB `tennis_live_ladder` identica; **cambia l'impronta del codice dei 4 bot tennis**: ricertificazione dal punto d'ingresso unico sul PC (nessuna registrazione tennis qui, par. 4) |
| `Betfair/stream/local_channel.py` | 432-437 | metodo `salute` (riassunto della pagina), solo a monitor acceso; spento = "metodo sconosciuto" come prima | **file condiviso con M-1** (il canale porta anche gli ordini): aggiunta in un punto lontano dal percorso ordini (accanto alla `sveglia`), dichiarata |
| `Betfair/stream/local_channel.py` | 702-705 | `ts` nella busta dei push (`publish`) | riga sostituita: spento = stessa `json.dumps({"t","d"})` |
| `Betfair/safe_strategy/canale_scan.py` | 49 (import), 443-444 | lettore dello scanner nei bot: latenza per topic | modulo resta puro (test di contratto verde); **cambia l'impronta del codice** di safe_base, safe_esatto, safe_punta e safe_tennis: serve la ricertificazione dal punto d'ingresso unico (par. 3 e 4) |
| `frontend/src/lib/localChannel.ts` | 26-27 (import), 292 | arrivo del push `ladder` | |
| `frontend/src/lib/localTransport.ts` | 32 (import), 439-442, 453 | istante del clic nel comando `order` del canale | coda DB (canale giu') invariata |
| `frontend/src/components/live/LadderView.tsx` | 40 (import), 1530 | `useMisuraDipinto(marketId, row)` | nessun DOM nuovo |
| `frontend/src/lib/salute.ts` | 176-193 | spiegazioni dei tratti nuovi (stessi prefissi del referto: test di parita') | |

Dentro `Betfair/monitor/`: `sonde.py` (misure e handler sopra), `registro.py:151-170` (`fondi`), `referto.py:305-420`
(`misure_m2`, `TRATTI_M1/M2`), `:688-704` (`_TRATTI_SPIEGATI`), `:670` (campo `misure_m2`), `:782` e `:825-866`
(`_markdown_m2`), `COSA_FA.md`. Nuovi: `frontend/src/lib/misuraSchermo.ts` (+ test), `Betfair/monitor/tests/test_monitor_m2_misure_2026_10_11.py`.

Lasciato a M-1 (percorso ordini) o al coordinatore, dichiarato (**i primi tre FATTI l'11/10 sul ramo
`mappa/agganci`, par. 7**):
- **ocm** (FATTO, par. 7.1): `osserva_stream` conta gia' gli `ocm` (`stream_ocm`), ma nessun listener dello stream ORDINI lo chiama: serve
  UNA riga `if _mon.ATTIVO: _mon.osserva_stream("ordini-<sport>", raw_data)` nell'`on_data` del listener ordini, che e'
  nel percorso dello stream ordini (dominio M-1). Senza, `stream_ocm` resta vuoto.
- lettore degli **esiti ordini** dei bot (FATTO, par. 7.2) (`esiti_ordini_canale.py`, topic `order`): stessa riga di `canale_scan`
  (`_mon.ricevuto_canale(msg)`) darebbe la latenza "esito -> bot"; non messa perche' e' il percorso degli esiti
  degli ordini. La busta porta gia' `ts`.
- (FATTO, par. 7.3) `tempi_ordine` per la strada `canale` (clic) scrive `decisione_ms=na` perche' non passa `invio`: il tratto del clic
  e' coperto da `clic_canale_ms`/`clic_presa_ms`; se M-1 passasse `invio=req.ricevuto_ms` in `live_order_worker.py:3997`
  il totale `decisione_risposta_ms.desktop.canale.<modo>` comparirebbe da solo.
- Mike live: REST in processo, `rest_ms.placeOrders` di T0A; nessun istante di decisione separato.
- `pacchetto_risposta_ms` solo per il Betfair vero (il paper simulato non scrive `execute_place` con `elapsed_seconds`).

## 3. Prove (rieseguibili)

- `python -m pytest Betfair/monitor -q -p no:cacheprovider`: **145 passati** (60 di T0A + 85 di M-2, revisione
  dell'11/10 compresa).
- Falsificazione (`mutazione -> test -> ripristino con sha256`, script nel referto al coordinatore): **Python 33/34
  rosse, frontend 12/12 rosse**. Due sopravvissute, entrambe EQUIVALENTI e dichiarate:
  - al primo giro "busta con ts anche spento" sul punto d'aggancio in `local_channel.py`: la funzione `busta` ha la
    sua guardia; aggiunto il test diretto della seconda guardia, la mutazione su quella guardia (M4) e' rossa;
  - M30 "min > max accettato": con `min > max` l'intervallo `[n*min, n*max]` e' vuoto, quindi il controllo della
    somma (M31, rosso) rifiuta sempre lo stesso riassunto; il controllo esplicito resta per chiarezza.
- Revisione indipendente dell'11/10: il test del caso I-1 (ladder aperto 40 s dopo l'ultimo push, riga dalla cache)
  e i tre test di M-3/TTL erano ROSSI sul codice di `400558d0` (4 rossi su 22) e sono verdi dopo la correzione.

| # | Mutazione | Esito |
|---|---|---|
| M1 | `pt -> rx` non ricordato | rossa |
| M2 | `rx_ms` scritto sulla riga del DB | rossa |
| M3 | tennis: canale senza marche | rossa |
| M4 | busta con `ts` anche spento (guardia di `busta`) | rossa |
| M5 | metodo `salute` anche a monitor spento | rossa |
| M6 | bordi della pagina non controllati | rossa |
| M7 | riassunto fuso pezzo per pezzo (non tutto o niente) | rossa |
| M8 | clic: paper e live nella stessa chiave | rossa |
| M9 | clic: `emesso_ms` booleano accettato | rossa |
| M10 | lettore dello scanner senza aggancio | rossa |
| M11 | tempi: attore sempre `altro` | rossa |
| M12 | tempi: anche il cancel e' un piazzamento | rossa |
| M13 | tempi: totale senza la risposta | rossa |
| M14 | tempi: modo ignorato (paper e live sommati) | rossa |
| M15 | pacchetto -> risposta anche dal paper | rossa |
| M16 | `output_thread` contato fra gli stream aperti | rossa |
| M17 | `connection_id` non contato | rossa |
| M18 | handler che solleva risale al chiamante | rossa |
| M19 | peso: EX_ALL_OFFERS+EX_TRADED non combinati | rossa |
| M20 | peso: profondita' del best offers ignorata | rossa |
| M21 | referto: modo ignorato (paper e live sommati) | rossa |
| M22 | referto: calcio e tennis mischiati in M1 | rossa |
| M23 | `registro.fondi` senza secchi | rossa |
| M24 | `pt -> rx` senza tetto | rossa |
| M25 | referto: messaggi al secondo sulla finestra sbagliata | rossa |
| F1 | arrivo annotato anche spento | rossa |
| F2 | `emesso_ms` anche spento | rossa |
| F3 | bordi diversi dal Python | rossa |
| F4 | frame chiesto anche spento | rossa |
| F5 | un frame non chiude l'arrivo | rossa |
| F6 | riassunto non azzerato dopo l'invio | rossa |
| F7 | secchio = bisect_right | rossa |
| F8 | riassunto mandato a canale giu' | rossa |
| M26 | (rev T-1) totale con tre tratti su quattro | rossa |
| M27 | (rev T-2) `clic_presa_ms` misurato dall'arrivo invece che dal drenaggio | rossa |
| M28 | (rev M-1) bordi letti prima della lunghezza | rossa |
| M29 | (rev M-1) nessun tetto ai valori | rossa |
| M30 | (rev M-1) min > max accettato | SOPRAVVISSUTA, equivalente (vedi sopra) |
| M31 | (rev M-1) somma fuori da `[n*min, n*max]` | rossa |
| M32 | (rev M-1) secchi incoerenti con min/max | rossa |
| M33 | (rev M-2) attori senza lista nota | rossa |
| M34 | (rev M-2) tratto oltre il tetto scartato in silenzio | rossa |
| F9 | (rev I-1) frame abbinato senza guardare la riga | rossa |
| F10 | (rev I-1) arrivo vecchio misurato al frame | rossa |
| F11 | (rev I-1) arrivi vecchi mai scartati | rossa |
| F12 | (rev M-3) invio che cancella lo sport (arrivo in volo perso) | rossa |

- Banco con il monitor spento, dal punto d'ingresso unico, registrazione `35760084` scompattata da
  `registrazioni_banco/` (poi cancellata): PRIMA = file di `a3a58ad8`, DOPO = `2bcad9bc`.
  `certifica safe_base|safe_esatto|safe_punta 35760084 --scenari rapidi`: per ciascuno **132/132 righe uguali tolti
  i tempi** (`scenari di trasporto: 18, KO 0`, `ESITO: OK`). `certifica mike 35760084 --scenari base` (su `7b74b7e4`)
  identico al referto T0A (`tick= 52082 decisioni= 5246 azioni= 6`, `codice bot 1db476391a03`: i file di Mike non
  sono toccati). **Cambia l'impronta del codice** di safe_base, safe_esatto, safe_punta, safe_tennis (via
  `canale_scan.py`) e dei 4 bot tennis (via `tennis_runner.py`): serve la ricertificazione dal punto d'ingresso unico;
  safe_tennis e i bot tennis non sono rilanciati qui (nessuna registrazione tennis): checklist del PC, par. 4.
- Frontend: `npx tsc -p tsconfig.app.json --noEmit` **0 errori**; `npx vitest run src/fotografia` **4 file, 43 test
  verdi, nessuna fotografia cambiata** (nessun DOM nuovo; misura spenta di serie); vitest dei componenti toccati
  (misuraSchermo, localChannel, localTransport, salute, monitorSalute, Salute, tutta `components/live`,
  MarketWatch.canale, ladderPopout, trainingLadder.replay, SchedaPropostaOpportunita.alms, MissionPanel,
  mikeCanaleLocale, safeStrategyScan.localCanale): **324 verdi** dopo la revisione.
- Suite Python intera (una volta, a fine lavoro, `python -m pytest Betfair/ -q -p no:cacheprovider`):
  **11607 passati, 67 saltati, 6 xfailed, 0 rossi** (464,9 s, su `7b74b7e4`, con la registrazione `35760084`
  scompattata in `_live_raw/`). Dopo la revisione (`2bcad9bc`, registrazione gia' cancellata): **11604 passati,
  87 saltati, 6 xfailed, 0 rossi** (343,0 s); i 20 saltati in piu' sono i test di replay che senza `_live_raw/` si
  saltano da soli (24 SKIPPED in quei 9 file).

## 4. Checklist di firma per il PC (in quest'ordine)

1. Rileggere il diff `a3a58ad8..mappa/m2-misure` (fuori da `Betfair/monitor/` e `frontend/src/lib/misuraSchermo*`
   sono 8 file, tabella par. 2) e rilanciare di persona:
   `python -m pytest Betfair/monitor -q -p no:cacheprovider` (145 verdi) e la suite intera;
   `cd frontend && npx tsc -p tsconfig.app.json --noEmit && npx vitest run src/lib/misuraSchermo.test.ts src/lib/salute.test.ts src/fotografia`.
2. Ricertificazione dal punto d'ingresso unico (cambia l'impronta del codice): `python -m Betfair.stream.backtest.certifica`
   per safe_base, safe_esatto, safe_punta (35760084, `--scenari rapidi`: stessi numeri del par. 3), **safe_tennis** e i
   **4 bot tennis** su una registrazione tennis del PC, prima (`a3a58ad8`) e dopo, a monitor spento, confrontando le
   righe tolti i tempi; `mike 35760084 --scenari base` come controllo.
3. Falsificare almeno due mutazioni a mano (es. M8 e F2) e vederle rosse.
4. Con `MONITOR_SALUTE=1` nel `.env` (gia' previsto da T0A): **`npm run build` in `frontend/` AD APP SPENTA** (vedi
   par. 5), poi l'utente riavvia l'app.
5. Entro 1 minuto, con un ladder calcio e uno tennis aperti: nel file `_logs/monitor/<giorno>/runner-calcio.jsonl`
   (e `runner-tennis.jsonl`) compaiono `ladder_rx_pub_ms` e, dopo 30-60 s, `pagina_*` e `contatori.pagina`; nella
   pagina "Salute" i tratti con la spiegazione. Nei bot (Mike/Omega/Safe) `canale_ricezione_ms.scan_calcio` (solo se
   il loro lettore del canale dello scanner e' acceso).
6. Un ordine paper dal ladder (clic) calcio e uno tennis: `clic_canale_ms.paper`, `clic_presa_ms.paper` nella riga
   del runner dello sport; un ordine paper di Mike/Omega/Safe: `decisione_risposta_ms.<attore>.comando.paper`.
7. Referto del giorno dopo: `python -m Betfair.monitor.referto --giorno <AAAA-MM-GG> --da-db --log-dir _logs --raw-dir _live_raw`
   -> sezioni "M1", "M2", "Canale locale, stream e REST" con p50/p95/p99 per sport, attore, strada e modo.
8. Ritorno: `MONITOR_SALUTE=0` (o riga tolta), `npm run build` ad app spenta, riavvio: nessun campo, nessun timer.

## 5. Dopo aver cambiato il frontend

La misura a schermo si accende SOLO nella build fatta con `MONITOR_SALUTE=1` nel `.env` della radice (lo stesso
interruttore dei servizi, letto da `vite.config.ts` alla build: `lib/monitorSalute.ts`). Dopo il merge, e ogni volta
che si cambia la riga: **`npm run build` in `frontend/` con l'app SPENTA** (l'exe e' un avviatore del `main.js` vivo:
mai ricompilarlo, mai chiudere l'app al posto dell'utente). Senza la build nuova la pagina non misura e non manda
riassunti; i servizi Python misurano comunque la loro parte.

## 6. Cosa non ho potuto verificare

- Nessun numero vero: niente PC, niente app, niente Betfair dal cloud. I tratti sono provati con orologi finti e
  oggetti veri, non misurati sul campo.
- `requestAnimationFrame` in Electron: nei test e' sostituito; l'istante e' l'INIZIO del frame che dipinge la riga
  (prima del paint e della composizione): la misura sottostima il pixel vero di al piu' un frame (~16 ms a 60 Hz).
- Orologio della pagina contro `time.time()` del Python: stessa macchina e stesso orologio di sistema (Date.now); un
  salto dell'Ora di Windows durante la misura sporca i tratti PC/PC di quella finestra (U-62).
- Tabella dei pesi REST di Betfair non riletta sul sito (non raggiungibile da qui).
- Bot tennis e registrazioni tennis: nessuna registrazione tennis disponibile, il banco tennis non e' stato rilanciato.
- Suite `npx vitest run` INTERA non lanciata (macchina condivisa): lanciati tsc, fotografia e i test dei componenti toccati.
- ~~`ocm` e latenza "esito -> bot" restano vuoti finche' M-1 non mette la riga d'aggancio nel suo percorso~~:
  agganci fatti l'11/10 (par. 7); restano non misurati sul campo (nessun PC, nessun Betfair dal cloud).

## 7. Agganci fatti dopo M-1 (11/10/2026, ramo `mappa/agganci` da `mappa/integrazione` `8e768f7f`)

I tre punti di "Lasciato a M-1" del par. 2. Tutti dietro `MONITOR_SALUTE` (`_mon.ATTIVO`): spento = identico a
prima (nessun wrapper, nessun campo, nessun contatore: provato). Righe sul commit del ramo `mappa/agganci`.

### 7.1 `ocm` dello stream ORDINI in "Salute"

| File:riga | Cosa |
|---|---|
| `Betfair/stream/auth.py:73` | `if _ro.attivo() or _mon.ATTIVO: _ro.aggancia_api_client(client)`: l'APIClient si aggancia se ALMENO UNO dei due interruttori e' acceso (prima: solo `REGISTRO_ORDINI`) |
| `Betfair/monitor/registratore_ordini.py:87` | import di `sonde` (il pacchetto resta senza flumine/betfairlightweight al caricamento) |
| `Betfair/monitor/registratore_ordini.py:886-898` | `sorgente_salute()`: `ordini-<sport>` dallo stato in memoria del monitor (`sonde.stato()`, lo sport dato a `avvia`; senza sport il servizio); `None` a monitor spento. Nessuna lettura nuova |
| `Betfair/monitor/registratore_ordini.py:901-943` | `_monta_tee`: il tee scrive su disco SOLO a registratore acceso (`scr = scrittore() if registra else None`, record `sub` solo se `registra`), conta in Salute SOLO a monitor acceso (`_mon.osserva_stream(sorgente, raw_data)`, `:932-936`, errore catturato e loggato `[registro-ordini] ocm non contato in Salute`). L'`on_data` originale e' chiamato una volta e il suo valore torna identico (come M-1) |
| `Betfair/monitor/registratore_ordini.py:985-1009` | `aggancia_api_client`: registratore spento e monitor acceso = si avvolge SOLO `streaming.create_stream` (mai `betting.request`: nessuna registrazione REST, nessuno scrittore, nessun file, nessun thread) |

Cosa si legge (riga del processo, es. `runner-calcio`, `runner-tennis`, `scalper-sessione-*`):
`contatori.stream_ocm.ordini-<sport>`, tratto `ordini_rx_pt_ms.ordini-<sport>` (pt -> ricezione, orologi diversi),
`contatori.stream_status["ordini-<sport> SUCCESS|FAILURE ..."]`, `valori.connessioni_disponibili.ordini-<sport>`
(lo `status` dello stream ordini porta anche `connectionsAvailable`), `contatori.stream_altri.ordini-<sport>`
(`connection`). Calcio e tennis non si mischiano: la sorgente porta lo sport del processo (test
`test_ocm_sport_del_processo_tennis_mai_mischiato`). Il referto li raccoglie gia' (`referto.py`, gruppo `stream_ocm`).

Ordine nei servizi: `_mon.avvia(...)` e' chiamato PRIMA di `build_client` (runner calcio `runner.py:3256` ->
`:2712`, runner tennis `tennis_runner.py:3560` -> `:3198`, sessione scalper `scalper_session.py:2440` -> `:1544`):
alla costruzione del client il monitor e' gia' deciso. Gli stream dei prezzi non sono toccati (il tee si monta solo
su `subscribe_to_orders`).

### 7.2 Latenza esito -> bot (lettore degli esiti ordini dei bot)

| File:riga | Cosa |
|---|---|
| `Betfair/stream/esiti_ordini_canale.py:64` | import di `sonde` (modulo resta PURO: test `test_esiti_ordini_canale_e_un_modulo_puro` verde) |
| `Betfair/stream/esiti_ordini_canale.py:335-336` | `ClientEsiti.incassa`: `if _mon.ATTIVO: _mon.ricevuto_canale(msg, per_modo=True)`, DOPO il filtro dei topic del lettore (hello e altri non contano) e PRIMA della memoria (conta anche una riga poi scartata come vecchia) |
| `Betfair/monitor/sonde.py:400-414` | `ricevuto_canale(msg, *, per_modo=False)`: con `per_modo` la chiave e' `<topic>.<modo>` (`mode` della riga dello specchio, `modo` della fotografia del conto): **paper e live mai sommati**. Senza (`canale_scan`) chiavi di sempre |

Si legge nella riga del BOT (Omega, Safe, Mike): `canale_ricezione_ms.order.paper|live`,
`canale_ricezione_ms.conto.live`, `canale_ricezione_ms.conto_paper.paper`; contatori `canale_ric`. `ts` 0 o
assente (busta di un runner a monitor spento): nessun tratto (`_numero_positivo`).

**Impronta**: `esiti_ordini_canale.py` e' un modulo CONDIVISO di `Betfair/stream/`, NON e' in nessun
`moduli_produzione` del registro del banco (`registro_bot.py`, chiusura degli import DENTRO il pacchetto del bot):
l'impronta `codice_bot` di Mike, Omega, Safe NON cambia (verificato: intersezione vuota per tutti gli 11 bot
registrati). E' pero' codice di produzione dei bot (lettore degli esiti di Omega/Safe, del conto di Mike/Omega/Safe,
montato anche dai replay del banco): va nella checklist del PC come ricertificazione di CONTROLLO (par. 7.4).

### 7.3 `invio` della strada canale (clic del desktop)

| File:riga | Cosa |
|---|---|
| `Betfair/stream/live_order_worker.py:3999-4000` | `_TEMPI.nuovo(..., invio=req.ricevuto_ms)` nella strada canale di `_process_local_requests`. Solo l'argomento di misura: nessun altro cambiamento |

Verificato in `tempi_ordine.py`: `invio` -> `voce["invio_ms"]` (`nuovo`, `_ms_da`), letto SOLO da `tratti`
(`decisione_ms` = invio - decisione, `ricezione_ms` = presa - invio) e dal record `dec` di M-1
(`registratore_ordini.decisione`, campo `invio_ms`): nessuna decisione, nessuna guardia. `_ms_da` tratta `0` e
negativi come ASSENTI (`tempi_ordine.py:107-108`): `req.ricevuto_ms` = 0 a monitor spento -> `decisione_ms=na`,
`ricezione_ms=na` come prima (test `test_clic_spento_identico_a_prima_nessuna_misura`,
`test_clic_acceso_ricevuto_zero_nessuna_misura_falsa`). `ricevuto_ms` e' l'orologio del PC (`invio_orologio="pc"`,
nessun tratto a orologi misti). A monitor acceso compaiono `decisione_invio_ms`, `invio_presa_ms` e il totale
`decisione_risposta_ms.desktop.canale.<modo>`.

Non toccato (dichiarato): la strada canale del TENNIS (`tennis_live_order_worker.py:1799-1802`) ha lo stesso `na`;
quel file e' nella chiusura dei 4 bot tennis (`_MODULI_TENNIS`): metterci `invio=` cambierebbe la loro impronta e
richiederebbe la ricertificazione tennis. Lasciato al coordinatore.

### 7.4 Prove (rieseguibili) e checklist del PC

- Test nuovi: `Betfair/monitor/tests/test_agganci_m1_m2_2026_10_11.py` (21): APIClient VERO da `build_client`,
  `OrderStream.run` VERO di flumine col solo socket finto, listener VERO; `LocalChannel` VERO (`publish`,
  `_on_message`), `ClientEsiti` VERO con righe da `LiveTradingStrategy._order_row` VERA e `payload_conto*` VERI;
  `LocalRequest` VERE, worker VERO, `tempi_ordine` VERO e handler di log VERO della Salute.
- Mutazioni: `python ARCHITETTURA_2026-10/mappa/agganci_mutazioni.py` -> **20/20 ROSSE**, ripristino sha256
  identico (G1-G10 aggancio 1, H1-H6 aggancio 2, K1-K4 aggancio 3). `m1_mutazioni.py` (anchor di M1 aggiornato alla
  riga nuova di `auth.py`): **80/80 ROSSE**.
- `python -m pytest Betfair/monitor -q -p no:cacheprovider`: **277 passati**.
- Test vicini (canale locale, live_order_worker, tempi_ordine F0, motore ordini, esiti canale e purezza,
  canale_scan, conto W3a/W3b, registro e impronta del banco): **522 passati**.
- Suite intera, una volta: `python -m pytest Betfair/ -q -p no:cacheprovider` -> **11736 passati, 87 saltati,
  6 xfailed, 0 rossi** (390 s; senza `_live_raw/`, i test di replay si saltano da soli).

Checklist del PC (in piu' di quella del par. 4):
1. Rileggere il diff `mappa/integrazione..mappa/agganci` (7 file toccati + test + script) e rilanciare i test nuovi
   e `agganci_mutazioni.py` (20 righe ROSSO, uscita 0, `git status` pulito).
2. Ricertificazione di CONTROLLO a monitor spento (l'impronta non cambia, il codice condiviso si'):
   `certifica omega|safe_base|safe_esatto|safe_punta|mike 35760084` prima/dopo, righe uguali tolti i tempi.
3. Con `MONITOR_SALUTE=1` e `REGISTRO_ORDINI` assente: nel `runner-calcio.jsonl` compaiono
   `contatori.stream_ocm.ordini-calcio` (battiti ogni 5 s anche senza ordini) e nessuna cartella `_live_raw\_ordini`;
   nel `runner-tennis.jsonl` `ordini-tennis` (solo con lo stream ordini LIVE aperto: in PAPER flumine usa
   `SimulatedOrderStream` e non c'e' nessun `ocm`).
4. Con `ESITI_ORDINI_CANALE=1` e un ordine paper di Omega/Safe: `canale_ricezione_ms.order.paper` nella riga del bot.
5. Un clic paper dal ladder calcio: `decisione_risposta_ms.desktop.canale.paper` nella riga del runner calcio.
