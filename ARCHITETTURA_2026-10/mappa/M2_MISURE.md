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
| `pagina_rx_dipinto_ms` **nuovo** | **M1 sul PC: arrivo nel processo -> frame** (il numero da confrontare con Bet Angel, p95 <= 20 ms) | PC/PC | idem | idem |
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
4. Ogni 30 s la pagina manda un RIASSUNTO per sport (stessi bordi dei secchi del Python: un test li confronta e il
   Python rifiuta un riassunto con bordi diversi, catalogo PSB par. 7 n.33) come richiesta `salute` sul canale del
   runner gia' aperto (47331 calcio, 47332 tennis). Il runner lo valida PER INTERO (versione, bordi, nomi ammessi,
   `n` = somma dei secchi, numeri finiti, tetto 100.000) e lo fonde nel suo registro (`sonde.misure_pagina`,
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
| **Scalper calcio** | in processo (`market.place_order` nella sessione flumine) | creazione del pacchetto di flumine (l'ordine nasce nella strategia, stesso thread) | `elapsed_seconds` del pacchetto nel log `execute_place` di flumine (Betfair vero) | `pacchetto_risposta_ms` nella riga `scalper-sessione-*` (referto: attore `scalper`) |
| **Bot tennis** | in processo (runner tennis) | idem | idem | `pacchetto_risposta_ms` nella riga `runner-tennis` (referto: `tennis-processo`: bot e manuali dello stesso processo) |
| **Mike** (live) | REST in processo (`omega_market.place_order_live`) | in processo | `rest_ms.placeOrders` (T0A, sessione dell'APIClient) | - |

Perche' `marca_emesso` NON e' stato aggiunto a Mike, scalper e bot tennis: Mike in paper porta gia' l'istante della
decisione (`creato_ms`, e il protocollo del motore rifiuta chiavi non previste: `CHIAVI_COMANDO`); scalper e bot
tennis non hanno una coda ne' dei params - decidono e piazzano nello stesso thread, quindi il loro "decisione ->
invio" e' il calcolo della strategia e il resto e' il pacchetto di flumine, misurato dal log che flumine scrive gia'.

Lettura delle righe `tempi_ordine` (handler `_GestoreTempiOrdine`, `sonde.py:840-886`, logger
`Betfair.stream.tempi_ordine`): attore dal `rif` (`attore_da_rif`, `sonde.py:505-516`: UUID della pagina = `desktop`,
`mike-`/`omega-`/`safe-`/`risk-`... = il prefisso, altro = `altro`); solo le azioni che PIAZZANO (`place*`,
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

Fuori da `Betfair/monitor/` (ognuno dietro `_mon.ATTIVO` o `misuraAccesa()`):

| File | Righe | Cosa | Nota |
|---|---|---|---|
| `Betfair/stream/tennis_live/tennis_runner.py` | 87 (import), 1509-1511 | ladder tennis sul canale con `marca_ladder` | riga del DB `tennis_live_ladder` identica |
| `Betfair/stream/local_channel.py` | 432-437 | metodo `salute` (riassunto della pagina), solo a monitor acceso; spento = "metodo sconosciuto" come prima | **file condiviso con M-1** (il canale porta anche gli ordini): aggiunta in un punto lontano dal percorso ordini (accanto alla `sveglia`), dichiarata |
| `Betfair/stream/local_channel.py` | 702-705 | `ts` nella busta dei push (`publish`) | riga sostituita: spento = stessa `json.dumps({"t","d"})` |
| `Betfair/safe_strategy/canale_scan.py` | 49 (import), 443-444 | lettore dello scanner nei bot: latenza per topic | modulo resta puro (test di contratto verde); cambia l'impronta del codice di Safe nel banco (tolleranza U-59), non la strategia |
| `frontend/src/lib/localChannel.ts` | 26-27 (import), 292 | arrivo del push `ladder` | |
| `frontend/src/lib/localTransport.ts` | 32 (import), 439-442, 453 | istante del clic nel comando `order` del canale | coda DB (canale giu') invariata |
| `frontend/src/components/live/LadderView.tsx` | 40 (import), 1530 | `useMisuraDipinto(marketId, row)` | nessun DOM nuovo |
| `frontend/src/lib/salute.ts` | 176-193 | spiegazioni dei tratti nuovi (stessi prefissi del referto: test di parita') | |

Dentro `Betfair/monitor/`: `sonde.py` (misure e handler sopra), `registro.py:151-170` (`fondi`), `referto.py:305-420`
(`misure_m2`, `TRATTI_M1/M2`), `:688-704` (`_TRATTI_SPIEGATI`), `:670` (campo `misure_m2`), `:782` e `:825-866`
(`_markdown_m2`), `COSA_FA.md`. Nuovi: `frontend/src/lib/misuraSchermo.ts` (+ test), `Betfair/monitor/tests/test_monitor_m2_misure_2026_10_11.py`.

Lasciato a M-1 (percorso ordini) o al coordinatore, dichiarato:
- **ocm**: `osserva_stream` conta gia' gli `ocm` (`stream_ocm`), ma nessun listener dello stream ORDINI lo chiama: serve
  UNA riga `if _mon.ATTIVO: _mon.osserva_stream("ordini-<sport>", raw_data)` nell'`on_data` del listener ordini, che e'
  nel percorso dello stream ordini (dominio M-1). Senza, `stream_ocm` resta vuoto.
- lettore degli **esiti ordini** dei bot (`esiti_ordini_canale.py`, topic `order`): stessa riga di `canale_scan`
  (`_mon.ricevuto_canale(msg)`) darebbe la latenza "esito -> bot"; non messa perche' e' il percorso degli esiti
  degli ordini. La busta porta gia' `ts`.
- `tempi_ordine` per la strada `canale` (clic) scrive `decisione_ms=na` perche' non passa `invio`: il tratto del clic
  e' coperto da `clic_canale_ms`/`clic_presa_ms`; se M-1 passasse `invio=req.ricevuto_ms` in `live_order_worker.py:3997`
  il totale `decisione_risposta_ms.desktop.canale.<modo>` comparirebbe da solo.
- Mike live: REST in processo, `rest_ms.placeOrders` di T0A; nessun istante di decisione separato.
- `pacchetto_risposta_ms` solo per il Betfair vero (il paper simulato non scrive `execute_place` con `elapsed_seconds`).

## 3. Prove (rieseguibili)

- `python -m pytest Betfair/monitor -q -p no:cacheprovider`: **126 passati** (60 di T0A + 66 nuovi).
- Falsificazione (`mutazione -> test -> ripristino con sha256`, script nel referto al coordinatore): **Python 25/25
  rosse, frontend 8/8 rosse**. Al primo giro la mutazione "busta con ts anche spento" sul punto d'aggancio in
  `local_channel.py` e' SOPRAVVISSUTA: e' equivalente (la funzione `busta` ha la sua guardia). Aggiunto il test
  diretto della seconda guardia; la mutazione sulla guardia di `busta` e' rossa.

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

- Banco con il monitor spento, PRIMA (`a3a58ad8`) e DOPO (`7b74b7e4`), registrazione `35760084` scompattata da
  `registrazioni_banco/`: `certifica safe_base 35760084 --scenari rapidi` 132/132 righe uguali tolti i tempi
  (`18 scenari, KO 0, ESITO: OK`); `certifica mike 35760084 --scenari base` DOPO identico al referto T0A
  (`tick= 52082 decisioni= 5246 azioni= 6`, `codice bot 1db476391a03`: i file di Mike non sono toccati).
- Frontend: `npx tsc -p tsconfig.app.json --noEmit` **0 errori**; `npx vitest run src/fotografia` **4 file, 43 test
  verdi, nessuna fotografia cambiata** (nessun DOM nuovo; misura spenta di serie); vitest dei componenti toccati
  (misuraSchermo, localChannel, localTransport, salute, Salute, LadderView e i 10 test che rendono LadderView,
  MarketWatch.canale, ladderPopout): **verdi** (125 + 73 test).
- Suite Python intera (una volta, a fine lavoro, `python -m pytest Betfair/ -q -p no:cacheprovider`):
  **11607 passati, 67 saltati, 6 xfailed, 0 rossi** (464,9 s).

## 4. Checklist di firma per il PC (in quest'ordine)

1. Rileggere il diff `a3a58ad8..mappa/m2-misure` (fuori da `Betfair/monitor/` e `frontend/src/lib/misuraSchermo*`
   sono 8 file, tabella par. 2) e rilanciare di persona:
   `python -m pytest Betfair/monitor -q -p no:cacheprovider` (126 verdi) e la suite intera;
   `cd frontend && npx tsc -p tsconfig.app.json --noEmit && npx vitest run src/lib/misuraSchermo.test.ts src/lib/salute.test.ts src/fotografia`.
2. Banco spento identico: `python -m Betfair.stream.backtest.certifica safe_base 35760084 --scenari rapidi` e
   `... mike 35760084 --scenari base` (stessi numeri del par. 3); con una registrazione tennis, uno dei bot tennis
   (tocca `tennis_runner.py`: cambia l'impronta del codice, non la strategia).
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
- `ocm` e latenza "esito -> bot" restano vuoti finche' M-1 non mette la riga d'aggancio nel suo percorso (par. 2).
