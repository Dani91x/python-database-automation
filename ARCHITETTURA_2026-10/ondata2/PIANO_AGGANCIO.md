# ONDATA 2 - PIANO DI AGGANCIO dei sette comparti (10/10/2026)

Agente del piano di aggancio (Opus 5.5), ramo `ondata2/piano-aggancio` da `d073ddcb`. Lavoro di SOLA LETTURA: nessun file
di produzione toccato, nessun test, nessun replay, nessun processo lanciato. Ogni `file:riga` del codice di oggi e' stato
riletto da me su `d073ddcb` (i file di produzione sono identici a `559a96df`, base dell'ondata 1: `git diff --stat
559a96df d073ddcb` tocca solo test, documenti, frontend del monitor, migrazioni e registrazioni). Dove un referto
dell'ondata 1 cita una riga diversa da quella vera lo scrivo (sezione 11).

Fonti lette per intero: `AVANZAMENTO.md`, `05_PIANO_DI_MIGRAZIONE.md`, `04_ARCHITETTURA_OBIETTIVO.md` (par. 0, 1, 3.2,
3.11, 4.1, 5, 7, 8), `ondata1/DECISIONI_PER_L_UTENTE.md` (le «Risposte dell'utente» sono VINCOLANTI), `ondata1/INTEGRAZIONE.md`,
il par. 8 (e il 9) dei sette `ondata1/W1-*/REFERTO.md`, `PROCESSO_STANDARD_BOT.md` (par. 1-7), `CLAUDE.md`.

Il piano NON si rimette in discussione: questo documento DETTAGLIA le tappe T2, T5, T6, T7, T8, T9, T10, T11, T19 di
`05` (quelle che i sette comparti realizzano), nell'ordine del grafo di `05` par. 3 e del «Traguardo 1» di `AVANZAMENTO.md`.

---------------------------------------------------------------------------------------------------

## 0. In una pagina

1. **Prerequisiti** (non lavoro di questo piano): tappa 0 chiusa (`AVANZAMENTO.md:62-63`: referto 24 h di T0A e
   congelamento di T0C; oggi `ARCHITETTURA_2026-10/riferimenti_congelati/` contiene solo `TOLLERANZE.md`, nessun
   `MANIFEST.json`, quindi nessuna cassetta per `--ombra`) e la matrice di parita' con i competitor (`AVANZAMENTO.md:75-78`).
2. **Ordine di aggancio** (par. 5): Passo 0 (lavori aperti nel nucleo, solo cloud) -> **A1 sessione e REST (T5)** ->
   **A2 ladder a 20 ms (T6)** -> **C1 porta degli ordini (T10)** -> **C2 libro del conto + stream ordini unico (T11)**
   [= Traguardo 1 «operare a mano come i competitor»] -> **G2 client cloud e cache (T2, T7)** -> **G1 archivio e postino
   dei log (T8)** -> **B stato partita (T9)** -> **A2 gestore unico dei flussi (T19, per profilo; lo scanner dopo T17)**.
3. **Architettura dei processi** (par. 3): un processo nuovo, piccolo e SENZA codice di bot, `betfair-nucleo`, tiene
   l'UNICA sessione (custode W1-A1), l'UNICO stream ordini del conto (W1-A2) e, da T19, l'UNICO gestore dei flussi
   (W1-A2, 4 profili). Gli altri processi non fanno login e non aprono connessioni a Betfair: ricevono il token e i
   messaggi grezzi `mcm`/`ocm` su un canale locale 127.0.0.1 SENZA PERDITE (numero di sequenza + immagine piena al buco),
   e li danno a flumine con le classi che flumine gia' prevede (`order_stream_cls`, `stream_class`). Connessioni Betfair
   nel caso peggiore: oggi LIVE 10/10 senza scalper e 18 con 4 sessioni scalper LIVE (oltre il limite); dopo: **9/10**
   senza scalper, **10/10** con qualunque numero di sessioni scalper. Login vivi insieme: oggi fino a **12** sessioni
   (+48 login al giorno del job tennis); dopo **1**. Il processo nuovo richiede il PERMESSO dell'utente (`CLAUDE.md`,
   «Nessun processo ... nuovo senza permesso esplicito»): e' la decisione D-1 di questo piano; l'alternativa senza
   processo nuovo (ospitare tutto nel runner calcio) e' descritta e sconsigliata (par. 3.6).
4. **Ombra**: sul banco (`certifica <bot> <evento> --ombra <cassetta congelata>`) per tutto cio' che tocca la condotta dei
   bot (C1, G2-T7, B, T19); dal vivo sul PC (registro dell'ombra in `_logs/ombra/`, contatori nella «Salute») per cio' che il
   banco non esercita (sessione, stream ordini reale, ladder, postino). Mai una connessione Betfair in piu' per fare l'ombra.
5. **I 5 rischi principali** (par. 8): (R1) il processo `betfair-nucleo` diventa un punto unico di guasto; (R2) il canale
   locale di oggi SCARTA i messaggi per i client lenti (`local_channel.py:663-708`) e non va bene per `mcm`/`ocm`
   differenziali: serve un trasporto nuovo senza perdite, con latenza da misurare; (R3) lo stream ordini sostituito in LIVE
   non e' certificabile sul banco (nessuna registrazione `ocm` nel repo); (R4) la porta degli ordini (C1) e' nel percorso
   dei soldi; (R5) la sessione unica: un relogin cambia il token per TUTTI i processi, e flumine fa un login proprio
   all'avvio del framework (`flumine/baseflumine.py:498`) che va neutralizzato.

---------------------------------------------------------------------------------------------------

## 1. Regole che valgono su ogni aggancio (non si ripetono nei paragrafi)

- **Rami e master** (`AVANZAMENTO.md:11-21`): un ramo per aggancio (`ondata2/<comparto>`) da master aggiornato; il cloud
  costruisce e certifica; il PC rilegge il diff, rilancia test e replay di persona, falsifica e FIRMA; solo dopo la firma e
  col si' esplicito dell'utente l'aggancio entra su master con l'interruttore su `vecchio` (app identica). Poi `ombra` sulle
  giornate vere, poi `nuovo` SOLO su decisione dell'utente. Ritorno: interruttore su `vecchio`.
- **Interruttore**: `ARCH_<COMPARTO>[_<BOT>]=vecchio|ombra|nuovo`, di serie `vecchio`, letto all'avvio del servizio
  (`04:933-938`); scritto nel `.env` della radice (lo legge `load_dotenv` di `Betfair/config.py`, come gli interruttori di
  oggi). Cambiarlo = riavvio dell'app, che fa SOLO l'utente e MAI con posizioni aperte (`05` R13). Un valore illeggibile vale
  `vecchio` con un avviso. Proposta: un solo modulo `Betfair/nucleo/interruttori.py` (nuovo) al posto dei lettori sparsi
  (`nucleo/dati/cloud.py:101` `interruttore_client`, `cache_cloud.py:70` `ENV_PREFETCH`, il `stato_partita/interruttore.py`
  proposto da W1-B).
- **Strategie intoccabili**: nessun aggancio cambia soglie, stake, tetti, gambe, cadenze dei bot, `conflateMs`/`heartbeatMs`
  (U-01, U-02, U-03). Ogni divergenza di condotta trovata in ombra si SCRIVE e si porta all'utente.
- **Paper prima del live**: ogni `nuovo` si accende prima con il runner in PAPER (`LIVE_ORDER_MODE`), e in LIVE solo dopo che
  il paper ha confermato e solo su ordine dell'utente, ricordandogli lo stato di certificazione sul replay (regola 1 dello
  standard, `CLAUDE.md`).
- **Calcio e tennis non si mischiano**: cartelle, diari, archivi, porte, libri del conto e topic restano per sport
  (decisione 7). Il processo `betfair-nucleo` NON contiene logica di sport: solo trasporto e conto (par. 3.2).
- **Criterio di fatto** (`05` par. 0.2): suite Python 0 rossi, vitest 0 rossi, tsc 0 errori; replay dei bot toccati con
  `--ombra` a 0 divergenze (tolleranze: le sole 3 di U-59, `riferimenti_congelati/TOLLERANZE.md`); test nuovi falsificati;
  PSB par. 6/7 sollecitati o ⊘ con causa; firma del PC; riga in `CRONOSTORIA.md`. Metro aggiuntivo dell'ondata 2: la voce
  della matrice di parita' con i competitor «uguale o meglio» del migliore, misurata (`AVANZAMENTO.md:72-78`).
- **Nessun processo nuovo senza permesso**: il solo processo nuovo proposto e' `betfair-nucleo` (D-1). Nessun
  registratore nuovo: il tee raw resta dove e' oggi fino a T19.

---------------------------------------------------------------------------------------------------

## 2. Lo stato di oggi, verificato (chi apre cosa)

### 2.1 I processi avviati dall'app (`desktop/main.js:415-482`)

Ogni servizio e' un watchdog Python (`Betfair.stream.watchdog`) che lancia il figlio: due processi Python per servizio.

| Etichetta (`main.js`) | Riga | Modulo | Betfair |
|---|---|---|---|
| `runner-calcio` | `main.js:419` | `Betfair.stream.runner` (target di serie, `watchdog.py:65`) | login + REST + stream prezzi + stream ordini (LIVE) + motore ordini su 47331 |
| `runner-tennis` | `main.js:420` | `tennis_live.tennis_runner` | login + stream prezzi + stream ordini (LIVE), 4 bot ospiti, 47332 |
| `scalper-service` | `main.js:427` | `scalper.scalper_service` | login (habitat) + fino a 4 sessioni figlie (`scalper_service.py:702-712`, `auto_mode.py:72` `TETTO_MASSIMO = 4`) |
| `tennis-bot-service` | `main.js:437` | `tennis_live.tennis_bot_service --bridge-only` | nessun login (`tennis_bot_service.py:1146`) |
| `safe-strategy-service` | `main.js:443` | `safe_strategy.service` (scanner) | login + fino a 4 stream (`safe_strategy/stream.py:82`), canale 47336 |
| `omega-service` | `main.js:450` | `omega.omega_service` | sessione REST condivisa di processo (ordini LIVE REST) |
| `safe-strategy-bot` | `main.js:456` | `safe_strategy.bot_service` | idem (`bot_service.py:54,138` usa `omega_market`) |
| `mike-service` | `main.js:461` | `mike.service` | idem (`mike/service.py:148-161`) |
| `backtest-worker` | `main.js:469` | `stream.backtest.worker` | nessuno (banco simulato) |
| `tennis-odds` (job, ogni 30 min) | `main.js:475-482` | `betfair_tennis_odds.py` | login a ogni giro |

L'ambiente di tutti i figli e' costruito da `costruisciEnvRunner` (`desktop/ambiente_runner.js:60-84`): passa
`APP_BOOT_ID`, `LOCAL_CHANNEL_TOKEN` (la chiave dei comandi sui canali locali, generata a ogni avvio in `main.js:61`),
`LIVE_LADDER_PUBLISH_SEC=0.3` (scrittura DB del ladder) e le cadenze 0,15 s. Le sessioni scalper figlie ereditano
l'ambiente (`scalper_service.py:705`, nessun `env=`). Lo spegnimento ordinato chiede l'arresto a tutti IN PARALLELO
(`main.js:527-556`, `Promise.all`) con attese per etichetta (`main.js:292-296`: scalper 150 s, Omega e Safe 45 s, gli
altri 25 s), poi `taskkill` (`killChildren`, `main.js:489`).

### 2.2 Login: oggi ogni processo fa il suo (decisione 1 «una sola sessione»)

| Processo | Dove fa login | Note |
|---|---|---|
| runner calcio | `runner.py:2710-2711` (`BetfairClient()` + `login_cert`, la sessione `rest`) e `runner.py:2712` (`build_client(login=True)`) | DUE sessioni; custode `runner.py:1443` (480 s) solo sulla seconda |
| runner tennis | `tennis_runner.py:3195` | custode `tennis_runner.py:1613` |
| scanner | `safe_strategy/service.py:3370` | custode `service.py:555` (900 s) |
| scalper-service | `scalper_service.py:890` (thread habitat) | |
| ogni sessione scalper (fino a 4) | `scalper_session.py:1544` | custode `scalper_session.py:958` (600 s) |
| Omega, Safe bot, Mike | `odds_refresh.py:66-67` (sessione lazy condivisa NEL processo), via `omega_market.py:63-65,71-78,94-102` | relogin su qualunque errore (`odds_refresh.py:78-89`); il «keepAlive» di Omega `omega_market.py:140` chiama `listEventTypes` (reperto W1-A1 par. 9.5) |
| tennis-odds | `betfair_tennis_odds.py:307-308` | 48 login al giorno |
| ogni framework flumine (runner calcio, runner tennis, sessioni scalper) | `flumine/baseflumine.py:498` `self.clients.login()` -> `flumine/clients/betfairclient.py:24-29` `betting_client.login()` | **reperto da verificare sul PC**: i client di `runner.py:2251/2270`, `tennis_runner.py:158/176` e `scalper_session.py:1926` non ridefiniscono `login` (lo fa solo il client paper affiancato, `client_paper_affiancato.py:43-44`): all'avvio del framework c'e' un login IN PIU' sullo stesso `APIClient` |

Fuori dall'app (script lanciati a mano, restano come sono): `run_scalper_live.py:230`, `habitat_scan.py:89`,
`tennis_scalper/{record_multi.py:280, record_tennis.py:41, run_tennis_pro.py:88, run_tennis_scalper.py:219,
backtest_pro.py:81}`, `betfair_report_manager.py:68`, `betfair_full_odds.py:146`, `import_betfair_operations.py:393`.

Totale sessioni vive insieme dall'app, caso peggiore: 2 + 1 + 1 + 1 + 4 + 3 = **12**, piu' il job tennis e i login di
avvio di flumine.

### 2.3 Connessioni Stream: oggi ogni processo apre le sue (decisioni 8 e 13)

| Connessione | Dove | PAPER | LIVE |
|---|---|---:|---:|
| prezzi calcio (frammenti) | `frammenti_mercato.py:89` (`DEFAULT_MAX_CONNESSIONI = 3`), riserva `:91`, classe `FrammentoMarketStream` `:186`, montata in `runner.py:2955-2964` | 1-3 | 1-3 |
| ordini calcio (flumine) | `runner.py:2251-2261` (`order_stream=True, paper_trade=False`); in PAPER `runner.py:2270-2280` apre un `SimulatedOrderStream` (nessuna connessione) | 0 | 1 |
| prezzi tennis | `tennis_runner.py:484-485` (`stream_class=TennisRecMarketStream`, `tennis_recorder.py:464`), una connessione cross-evento | 1 | 1 |
| ordini tennis (flumine) | `tennis_runner.py:158-160` | 0 | 1 |
| scanner | `safe_strategy/stream.py:421` (`create_stream`), pool di `StreamShard` `:492` fino a 4 | 1-4 | 1-4 |
| ogni sessione scalper | `scalper_session.py:1926-1927` (`Flumine` per partita), `_order_client_kwargs` `:927-942` (`order_stream=True`, `paper_trade` = demo) | 1 (prezzi) | 2 (prezzi + ordini) |
| **caso peggiore senza scalper** | | **8** | **10** |
| **con 4 sessioni scalper** | | 12 (oltre: rifiuti) | 18 (oltre) |

Lo stream ordini di flumine NON e' filtrato per strategia (`flumine/streams/orderstream.py:40-49`:
`customer_strategy_refs=None` perche' nessuno imposta `config.customer_strategy_ref`): in LIVE runner calcio, runner
tennis e ogni sessione scalper ricevono TUTTI gli ordini del conto, tre o piu' volte (W1-A2 D1). Il limite di 10
connessioni e' per app key (`frammenti_mercato.py:86`, `safe_strategy/stream.py:77` `BETFAIR_MAX_CONNECTIONS = 10`); solo il
calcio legge `connectionsAvailable` (`frammenti_mercato.py:134-168`).

### 2.4 REST di oggi nel percorso dei prezzi (decisione 8: «la REST solo di riserva»)

| Lettura | Dove | Cadenza / quando |
|---|---|---|
| board calcio e tennis | `board_worker.py:387` `_poll_books_rest` (chiamato `:453`, `:691`); tennis `tennis_runner.py:3431-3434` | ogni `LIVE_BOARD_POLL_SEC` (10 s) |
| scanner, mercati oltre la capacita' degli shard | `safe_strategy/service.py:1672` `poll_books` (chiamato `:3082`, `:3390`, `:3394`) | a ogni giro per i «non coperti» |
| book di Omega e Mike nelle decisioni e uscite | `omega_market.py:571` `read_book`; Omega `omega_service.py:5796,5873,6191,7844`; Mike `mike/service.py:5233-5235`, regolamento `:1323,1354` | a evento |
| quote pre-partita | `odds_refresh.py:137-141` | a richiesta |
| riconciliazione e ripresa | `reconcile_worker.py:1302` (`listCurrentOrders`), `runner.py:2545-2552` (ripresa del motore) | ciclo / avvio |

Le prime due diventano stream con T19 (gestore unico, profili `runner_*` e `scansione`); le letture di Omega e Mike
cambiano l'ingresso dei bot e restano alle tappe dei bot (T12, T15); riconciliazione e ripresa SONO la riserva.

### 2.5 Il canale locale di oggi (`Betfair/stream/local_channel.py`)

WebSocket su 127.0.0.1, un processo = un server per porta (`start_channel` `:762`): 47331 calcio (`runner.py:2732`),
47332 tennis (`tennis_runner.py:3230`), 47333 Mike, 47334 Omega, 47335 Safe, 47336 scanner (`canale_scan.py:69`),
47337 tennis bot, 47338 scalper (`canale_bot.py:135,142`); lock di singola istanza 47311-47319 (47317 libera). Origine e
token di sessione (`:46-72`): i comandi che ESEGUONO passano solo col `LOCAL_CHANNEL_TOKEN`. **Proprieta' decisiva per
l'aggancio**: `publish` (`:663-708`) SALTA il giro verso un client lento (`_MAX_INVII_IN_VOLO = 64`, `:184`; contatori
`saltati`/`saltati_client`): va bene per gli STATI (`ladder`, `scan_*`, `plancia`), non per i flussi differenziali
(`mcm`, `ocm`), che perdono la cache al primo messaggio saltato. Gli esiti degli ordini gia' lo sanno (seq + `da_seq`,
`motore_ordini.py:2280`).

---------------------------------------------------------------------------------------------------

## 3. L'architettura dei processi DOPO l'aggancio (punto 5 del brief)

### 3.1 La scelta: un processo «betfair-nucleo», trasporto senza logica

```
                 Betfair (Stream API + REST .it)
                    |   1 login, <=10 connessioni, tutte qui
             +------+-----------------------------------------------+
             | betfair-nucleo  (NUOVO, ~0 logica di bot)            |
             |  SessioneBetfair (W1-A1)      -> token + generazione |
             |  FlussoOrdiniContoBetfair (W1-A2) -> ocm del conto   |
             |  GestoreFlussi x 4 profili (W1-A2, da T19) -> mcm     |
             |  canale 127.0.0.1:47339 (lock 47317), senza perdite  |
             +--+---------+---------+----------+---------+----------+
                |token    |ocm      |mcm       |mcm      |mcm
       runner-calcio  runner-tennis  sessioni scalper  scanner   omega/mike/safe-bot/tennis-odds
       (flumine,      (flumine,      (flumine,          (stream   (solo token per la REST:
        motore 47331)  motore 47332)  una per partita)   proprio   placeOrders, letture)
                                                         fino a T17)
```

Cosa fa `betfair-nucleo` e NIENTE altro: (a) un login e il keepAlive (custode W1-A1, periodo 480 s = il piu' corto di
oggi, `runner.py:1443`/`tennis_runner.py:1613`; nessun processo vede la sessione meno rinnovata di oggi); (b) distribuisce
token e «generazione» a chi si presenta col `LOCAL_CHANNEL_TOKEN`; fa l'UNICO relogin quando un ospite segnala
`INVALID_SESSION_INFORMATION` (contratto d'uso W1-A1 par. 9.16: generazione catturata, 5 errori = 1 login; freno
`sessione.py:190`, attesa 15/30/60 s anche per `segnala_errore`, decisione 2); (c) apre l'UNICO stream ordini del conto
(W1-A2 `flusso_ordini_conto.py:490`) e ne normalizza i messaggi (`normalizza_ordini`, difetto `rfo`/`rfs` della libreria,
W1-A2 D6) prima di inoltrarli; (d) da T19 tiene i 4 `GestoreFlussi` (`flusso.py:486`, profili `profili.py:114-182`) con il
budget GLOBALE delle 10 connessioni; (e) inoltra i messaggi GREZZI agli abbonati. Non decide, non piazza, non scrive DB,
non converte valute (la conversione GBP->EUR resta dove e' oggi nei consumatori: `runner.py:2993`, `tennis_runner.py:3328`,
`scalper_session.py:1933`, scanner `drain`), non registra il raw (il tee resta nei consumatori fino a T19).

Perche' un processo e non il runner calcio (alternativa B, par. 3.6): il runner calcio ha una vita massima di 18 h e si
ricambia da solo (`runner.py:1257` `LIVE_RUNNER_MAX_HOURS`, `:3264` «ricambio pianificato»): ogni ricambio taglierebbe la
sessione e i flussi del tennis, dello scanner e degli scalper, anche con posizioni aperte, e metterebbe il tennis nel
processo del calcio (calcio e tennis non si mischiano). Perche' non lo scanner: e' il processo con piu' logica condivisa
(Scanner, IPS, `opportunity`) e un suo errore fermerebbe tutto. Un processo SENZA logica di bot e' il piu' stabile.

### 3.2 Come gli altri processi lo usano (le modifiche minime, con le classi che flumine gia' prevede)

1. **Token** - `SessioneOspite` (nuova, `nucleo/betfair/`, implementa `contratto.Sessione` `betfair/contratto.py:36`):
   tiene un `APIClient` costruito con `auth.build_client(login=False)` e ci mette il token con
   `betfairlightweight.baseclient.set_session_token` (`baseclient.py:99`); al cambio di generazione aggiorna il token; su
   `INVALID_SESSION_INFORMATION` chiede il rinnovo all'host invece di fare login. Per flumine: un client che non fa login
   ne' logout ne' keepAlive, sul modello ESISTENTE di `client_paper_affiancato.py:43-55` (stesso motivo: «mai la sessione
   del client proprietario»). Cosi' il login di avvio di flumine (`baseflumine.py:498`) e il relogin del worker
   `keep_alive` (`flumine/worker.py:100-116`) spariscono.
2. **Ordini** - flumine accetta uno stream ordini su misura: `BaseClient(order_stream_cls=...)`
   (`flumine/clients/baseclient.py:35,63`), creato da `Streams.add_client` (`flumine/streams/streams.py:81-89`) al posto
   dell'`OrderStream` che apre la connessione. Una `OrderStreamDaNucleo` (nuova) riceve le righe `ocm` dall'host e le passa
   al listener di flumine (`on_data`): flumine aggiorna blotter e ordini come oggi. Si monta SOLO sul client LIVE:
   `runner.py:2251-2261`, `tennis_runner.py:158-160`, `scalper_session.py:927-942` (`_order_client_kwargs`, ramo
   `session_paper=False`). In PAPER resta il `SimulatedOrderStream` di oggi (nessuna connessione, banco invariato).
   Parita' col filtro: flumine sottoscrive `partition_matched_by_strategy_ref=True, include_overall_position=False`
   (`orderstream.py:47-48`) e usa solo gli `uo`; lo stream del conto li porta identici (da provare, par. 6.4).
3. **Prezzi** (da T19) - flumine accetta una classe di stream per strategia (`BaseStrategy(stream_class=...)`,
   `flumine/strategy/strategy.py:46,77`), gia' usata oggi (`tennis_runner.py:485`, `runner.py:2963`). Una
   `MarketStreamDaNucleo` (sottoclasse di `MarketStream`, come `TennisRecMarketStream`) sostituisce in `run()` il socket
   Betfair con l'abbonamento all'host (profilo + mercati) e passa le righe al SUO `StreamListener`: il parsing, la cache dei
   `MarketBook`, il tee raw e la conversione restano nel consumatore, identici a oggi e identici al banco (che legge lo
   stesso grezzo con `HistoricalStream`). Per lo scanner (non flumine): il listener del pool (`safe_strategy/stream.py:421`)
   legge dall'host invece di `create_stream`.
4. **REST** - Omega, Mike, Safe bot, tennis-odds, scanner: la sessione condivisa di `odds_refresh._get_client`
   (`odds_refresh.py:60-67`) prende il token dalla `SessioneOspite` invece di `login_cert`; le mutazioni restano
   `call_mutating` (un solo ritento su errore di sessione, parita' W1-A1 par. 9.2).

### 3.3 Il trasporto locale (nuovo, NON il `publish` di oggi)

Stesso server WebSocket di `local_channel.py` (bind 127.0.0.1, origine e token `:46-72`), porta 47339, tre percorsi:
`/sessione` (push di token e generazione, richiesta `rinnova(generazione_vista)`), `/ordini` (righe `ocm`), `/flusso/<profilo>`
(abbonamento: insieme di mercati; righe `mcm` FILTRATE ai mercati dell'abbonato, `pt` e `clk` intatti). Regole, diverse dal
`publish` di oggi: ogni riga porta un numero di sequenza per abbonato; nessuna riga si salta: se l'abbonato resta indietro
oltre un tetto (proposta: 10.000 righe o 5 s) l'host lo stacca; al ricollegamento o al primo buco di sequenza l'abbonato
riparte da un'IMMAGINE PIENA, che l'host ottiene RIsottoscrivendo senza `clk` le connessioni di quel profilo (stessa cosa
che succede oggi quando un runner riparte; un profilo ha un consumatore, salvo `scalper_partita` che ne ha uno per partita).
Lo stream ordini oggi in flumine non riprende mai con `clk` (`orderstream.py:40-50`): riprendere da immagine e' la parita'.

### 3.4 Le connessioni Betfair prima e dopo

| Connessione | Oggi PAPER | Oggi LIVE | Dopo T11 (ordini unici) | Dopo T19 (gestore unico) |
|---|---:|---:|---:|---:|
| prezzi calcio | 1-3 | 1-3 | 1-3 (runner) | 1-3 (host, `runner_calcio`, 180/conn) |
| ordini calcio (flumine) | 0 | 1 | 0 | 0 |
| prezzi tennis | 1 | 1 | 1 (runner) | 1 (host, `runner_tennis`) |
| ordini tennis (flumine) | 0 | 1 | 0 | 0 |
| scanner | 1-4 | 1-4 | 1-4 (scanner) | 1-4 (host, `scansione`, dopo T17) |
| sessioni scalper (N <= 4) | N | 2N | N (solo prezzi) | 1 in tutto (host, `scalper_partita`, <= 200 mercati) |
| ordini del conto | 0 | 0 | 1 (host) | 1 (host) |
| **peggiore, N = 0** | **8** | **10** | **9** | **9** |
| **peggiore, N = 4** | 12 | 18 | 13 | **10** |

Capacita' in streaming dopo T19 a profili di oggi: calcio 540 + tennis 180 + scanner 720 + scalper 200 = 1.640 mercati con
10 connessioni (2.000 a 200 per connessione; di piu' solo se Betfair alza il limite, U-04). L'host alloca le connessioni con
una priorita' fissa SOLO quando non bastano (oggi decidono i rifiuti di Betfair, a caso): ordini del conto, mercati con
soldi (`fonti_soldi` del calcio, `runner.py:2916-2954`, `_mercati_con_soldi` `:2927`), tennis, scalper, frammenti calcio in piu', scanner. E' una scelta
tecnica, non di strategia, ma cambia chi resta senza stream quando il budget manca: la porto all'utente (D-4).

### 3.5 I processi: numeri e spegnimento

Oggi: 9 servizi x 2 (watchdog + figlio) = 18 processi Python + job tennis ogni 30 min + fino a 4 sessioni scalper.
Dopo: 20 (+ `betfair-nucleo` e il suo watchdog) + job + sessioni scalper; la riduzione a 8 di `04` par. 5.1 resta a T22
(supervisore) e U-64 (job tennis nel runner o nello scanner). Punti da toccare in `desktop/main.js` (vivo: nessuna
ricompilazione dell'exe): `spawnRunner('betfair-nucleo', ['-m', 'Betfair.stream.watchdog', '--',
'Betfair.nucleo.betfair.servizio'])` PRIMA di `main.js:419`; etichetta in `ARRESTO_ORDINATO_LABELS` (`main.js:279-283`);
in `orderedShutdown` (`main.js:527-556`) l'host si ferma DOPO tutti gli altri (lo scalper chiude le posizioni fino a 150 s e
nel frattempo gli servono token e ordini). Gli ospiti aspettano l'host all'avvio (riprovano come oggi flumine riprova
Betfair) e, se l'host manca da oltre 60 s con il token scaduto, NON fanno login da soli: restano fermi e lo dicono nella
«Salute» (decisione 2: «sempre una sola connessione»); l'unica via di riserva e' l'interruttore su `vecchio`.

### 3.6 L'alternativa senza processo nuovo (B), se l'utente non da' il permesso

Tutto cio' che sta nell'host va nel runner calcio (gia' padrone di 47331 e del topic `conto`, vivo con l'app,
`LIVE_RUNNER_KEEP_ALIVE=1` in `ambiente_runner.js:77`). Costo: (1) ogni ricambio del runner calcio (18 h) e ogni suo crash
fermano sessione e flussi di TUTTI, tennis compreso; (2) il tennis dipende dal processo del calcio; (3) il runner calcio, gia'
il piu' carico, prende il trasporto di tutti. Sconsigliata; resta possibile con lo stesso codice (il modulo dell'host si
monta dentro il runner).

---------------------------------------------------------------------------------------------------

## 4. Strumenti comuni dell'ondata 2

### 4.1 Ombra sul banco (cio' che tocca la condotta dei bot)

Strumenti di T0C: `cassetta.py` (6 livelli: decisione, ordine, fill, conto, riga_db, referto), `ombra.py` (confronto con
tolleranza zero salvo le 3 di U-59), `congela.py` (manifesto, `--verifica-congelati`), punto d'ingresso unico
`python -m Betfair.stream.backtest.certifica <bot> <eventi> --scenari ... [--trasporto coda|canale|entrambi] --ombra
<cassetta congelata>` (`certifica.py:894-948`; esce != 0 a qualunque divergenza). Ogni comparto che la condotta la tocca si
certifica due volte: interruttore `vecchio` (innocuita': 0 divergenze) e `nuovo` (parita': 0 divergenze). Prima di ogni lancio
se ne dichiara la durata (PSB par. 6.9; oggi Mike `tutti` 728 s supera il tetto di 600: lancio dichiarato).

Cosa il banco NON esercita (⊘ con causa in ogni referto): login e sessione (il banco non tocca Betfair), lo stream ordini
reale (il banco usa il `SimulatedOrderStream`; nel repo non c'e' nessuna registrazione `ocm`, W1-A2 D6), il ladder verso la
UI (`ladder_worker` non e' nel banco), `score_worker` e `update_live_now` del runner, le scritture dei moduli DB dei bot
(il banco usa `DbMemoria`/`DbMemoriaOmega`). Per questi valgono i test di parita' dell'ondata 1 e l'ombra dal vivo.

### 4.2 Ombra dal vivo (sul PC, app accesa, giornate vere)

Un registro unico: `_logs/ombra/<comparto>/<AAAA-MM-GG>.jsonl` (una riga per divergenza: istante, chiave, vecchio, nuovo,
regola) e i contatori nella «Salute» (`Betfair/monitor/sonde.py:151` `conta("ombra_<comparto>", ...)`, spenti con
`MONITOR_SALUTE=0`). Referto giornaliero = conteggio per chiave; «uguale o meglio» = 0 divergenze sui campi di identita' e
grandezze di prestazione non peggiori del referto 24 h di T0A (L1-L19 di `04` par. 7). Il numero di giornate lo fissa
l'utente quando accende l'ombra (proposta per comparto nei paragrafi).

---------------------------------------------------------------------------------------------------

## 5. Ordine di aggancio e perche'

| # | Comparto (tappa) | Dipende da | Rischio | Valore per l'utente | Perche' qui |
|---|---|---|---|---|---|
| 0 | Passo 0: lavori aperti nel nucleo (solo cloud, nessun aggancio) | - | nullo | prepara le decisioni 2, 3, 5, 10 | le risposte del 10/10 chiedono modifiche ai comparti prima di agganciarli |
| 1 | W1-A1 sessione e REST (T5) | tappa 0 | medio | una sessione, nessun ban, REST con pesi e tetti | primo del percorso critico (`05` par. 3); base di tutti (token per C1, A2, C2) |
| 2 | W1-A2 ladder (T6) | T5 (grafo; stesso `runner.py`) | basso (solo UI) | ladder a 20 ms come Bet Angel | priorita' dell'utente; nessun bot cambia ingresso |
| 3 | W1-C1 porta (T10) | T5, G1 (archivio, gia' integrato nel nucleo) | alto (soldi) | dedup che sopravvive, minimi unici, rifiuto desktop non multiplo di 0,50 | grafo T5 -> T10 -> T11 |
| 4 | W1-C2 + stream ordini del conto (T11) | T10, A1, host | medio (sola lettura) + alto (sostituzione in LIVE) | TUTTI gli ordini sul ladder con autore, abbinato, prezzo medio, «se vince» | chiude il Traguardo 1 |
| 5 | W1-G2 client cloud e cache (T2, T7) | tappa 0 | basso-medio | dati del cloud aggiornati appena ricalcolati; nessuna RPC nel giro di Omega | T2 precede T8; tocca `mike/service.py` e `omega_service.py` come T10: dopo |
| 6 | W1-G1 archivio e postino dei log (T8) | T2, migrazione `uid` (utente) | medio | nessun log perso, nessuna rete nel percorso | grafo T2 -> T8 |
| 7 | W1-B stato partita (T9) | T5 | basso in ombra, alto in nuovo (ingresso dei bot) | punteggio calcolato una volta, eta' misurata | tocca `runner.py`/`tennis_runner.py` come T5/T6: dopo |
| 8 | W1-A2 gestore dei flussi (T19) | T6, host; scanner dopo T17 | alto (tutti i prezzi) | un gestore, 10 connessioni bastano sempre, REST solo di riserva | per ultimo come nel percorso critico; prima tennis, poi scalper, poi calcio |

Vincolo `05` par. 0 punto 3 («mai due tappe sullo stesso file insieme»): `runner.py` e' toccato da 1, 2, 3, 4, 7, 8;
`omega_service.py` e `mike/service.py` da 1, 3, 5; per questo l'ordine e' una sequenza. In parallelo si puo' lavorare nel
cloud solo sul codice NUOVO del nucleo (Passo 0, host, trasporto), che non tocca file di produzione.

---------------------------------------------------------------------------------------------------

## 6. Comparto per comparto

Formato: (1) punti esatti e modifica minima; (2) ombra; (3) replay del banco; (4) decisioni dell'utente realizzate;
(5) rischi e ritorno; (6) stima e chi fa cosa. Stime: S <= 2 giorni, M 3-5, L 6-10 (lavoro, piu' il calendario dell'ombra).

### 6.0 Passo 0 - lavori aperti nel nucleo (solo cloud, nessun file di produzione)

| Lavoro | Dove (codice nuovo) | Decisione |
|---|---|---|
| «Se vince» su TUTTI i mercati | `nucleo/ordini/pnl_mercato.py:76-86` (`TIPI_UN_VINCITORE`, `TIPI_MERCATO_UN_VINCITORE`, `PREFISSI_...`) e `:196-254` (`_non_supportato`, `calcola`): il numero per selezione si calcola sempre; per i mercati a piu' vincitori o con handicap si marca `per_selezione=True` (non e' un esito unico del mercato) | 5 |
| `segnala_errore` rispetta l'attesa dopo un login fallito | `nucleo/betfair/sessione.py:355-364` (oggi scavalca il backoff, parita' con `auth.py:214-224`) | 2 |
| Desktop: punta non multipla di 0,50 RIFIUTATA | `nucleo/ordini/porta.py` `_valuta` (`:527` del referto) usa `minimi.verdetto_desktop` (`minimi.py:221`) per l'attore `desktop` | 3 |
| Cloud ricalcolato -> app subito | `nucleo/dati/cache_cloud.py:59` `INTERVALLO_SORVEGLIANZA_S = 300` e `:67` `SCADENZA_DOSSIER_S = 300`: sentinella letta ogni 15 s (una riga; ~5.760 letture al giorno per sentinella contro ~1.018.800 richieste al giorno di oggi, `04` L17), rilettura appena cambia; per Mike sentinella su `fixture_predictions.updated_at` delle partite seguite | 10 |
| `SessioneOspite`, client flumine senza login, `OrderStreamDaNucleo`, `MarketStreamDaNucleo`, trasporto senza perdite, modulo dell'host | `nucleo/betfair/` (nuovi) | 1, 8, 13 |
| Interruttori in un modulo | `nucleo/interruttori.py` (nuovo) | - |

Test: ognuno falsificato (mutazione rossa, ripristino con sha256). Il trasporto si prova col server TLS finto di W1-A2
(`test_a2_finti.py`) e col `APIClient` vero: stessa sequenza di `MarketBook`/blotter con il socket diretto e col relay.
**Stima**: L (7-9 giorni, cloud da solo). Nessuna firma del PC necessaria finche' non c'e' aggancio.

### 6.1 W1-A1 - sessione e REST (T5)

**(1) Punti e modifica minima.** Due interruttori, due fasi.

- *Fase a* `ARCH_SESSIONE=vecchio|ombra|nuovo` (custode del nucleo DENTRO ogni processo, un login per processo): ai 12+6
  punti del par. 2.2, al posto di `build_client(login=True)` / `BetfairClient()`+`login_cert`:
  `sess = sessione_del_processo(periodo_keepalive_s=<valore di oggi>)` (`nucleo/betfair/sessione.py:508`), `client =
  sess.client()` (`:277`); il custode di oggi diventa `sess.avvia()` (`:391`) e `alla_sessione_rifatta` (`:386`) richiama
  la ricostruzione dello stream di oggi (`_dopo_relogin`, `runner.py:1448`, W1-A1 par. 8.3). Runner calcio: `runner.py:2710-2712`
  (le DUE sessioni diventano una: la sessione `rest` senza keepAlive sparisce, reperto A §1.7), custode `runner.py:1443`;
  tennis `tennis_runner.py:3195`, `:1613`; scanner `safe_strategy/service.py:3370`, `:555`; scalper
  `scalper_session.py:1544`, `:958`, `scalper_service.py:890`; REST condivisa `odds_refresh.py:60-67` (adattatore sottile con
  l'API di `BetfairClient` sopra `ClienteRestBetfair` `rest.py:195`, con l'obbligo MEDIA-4: `omega_market._segnala_saldo`
  dopo ogni mutazione); tennis-odds `betfair_tennis_odds.py:307-308`. Ripieghi REST con pesi e blocchi di oggi:
  `board_worker.py:387`, `safe_strategy/service.py:1672`, `odds_refresh.py:137-141` (W1-A1 par. 8.2).
- *Fase b* `ARCH_SESSIONE_UNICA=vecchio|ombra|nuovo` (token da `betfair-nucleo`): negli stessi punti `sessione_del_processo`
  restituisce una `SessioneOspite` (par. 3.2.1); i client flumine LIVE/PAPER di `runner.py:2251/2270/2287`,
  `tennis_runner.py:158/176/181`, `scalper_session.py:1926` diventano la sottoclasse senza login (modello
  `client_paper_affiancato.py:43-55`). Host: `spawnRunner` in `main.js` (par. 3.5). Richiede D-1.

**(2) Ombra.** Fase a: nessun login in piu' (decisione 2). La REST nuova gira in parallelo SULLA STESSA sessione per 1 ora
sul PC: `poll_books` dello scanner e il board chiamano vecchia e nuova strada sugli stessi id; criterio: 0 differenze su
best back/lay (prezzo e importo) per mercato e runner; peso raddoppiato ma sotto i limiti. Sessione: si accende `nuovo` UN
processo alla volta (tennis-odds, scanner, scalper-service, Omega, Safe bot, Mike, sessioni scalper, runner tennis, runner
calcio: prima chi non ha soldi, il calcio per ultimo), e la «Salute» confronta col referto 24 h di T0A: login <= oggi,
keepAlive riusciti, 0 `INVALID_SESSION_INFORMATION` sulla REST nuova, nessun `LoginFrenato`, nessun ban; relogin <= 1 ogni
12 h per processo (L18). Mutazioni: nessuna ombra (i soldi non si mandano due volte); conteggio degli invii nella «Salute»
uguale agli ordini registrati. Fase b: l'host fa UN login in piu' e tiene viva la sua sessione per un giorno senza che
nessuno la usi (contatori uguali a sopra); poi `nuovo` processo per processo nello stesso ordine; criterio: login totali
dell'app = 1 (+ relogin al 90% della vita), 0 errori di sessione non risolti entro una generazione.

**(3) Replay.** Il banco non fa login: ⊘ «sessione» con causa. Innocuita' (stessi file modificati nei `main`):
`certifica mike 35760084 --scenari base`, `certifica omega 35760084 --scenari base`, `certifica safe_base 35760084
--scenari rapidi --trasporto entrambi`, `certifica scalper_calcio 35797769 --scenari base`, `certifica tennis_pro 35790089
--scenari base` (registrazioni in `registrazioni_banco/`, ricostruite con `registrazioni_banco/LEGGIMI.md`), ciascuno con
`ARCH_SESSIONE=nuovo` e `--ombra` sulla cassetta congelata: 0 divergenze. Test: `nucleo/betfair/tests/test_a1_*` (222).

**(4) Decisioni.** 1 (una sessione: fase b), 2 (attesa anche su `segnala_errore`; nessun login di riserva negli ospiti).

**(5) Rischi e ritorno.** Relogin che cambia il token sotto una mutazione in volo (un ritento su errore di sessione, parita'
`call_mutating`); il login di avvio di flumine se il client non e' la sottoclasse (prova: contatore dei login della «Salute»
all'avvio = 1); tre politiche di ritento delle mutazioni di oggi (W1-A1 par. 9.1: `order_exec` perde i suoi ritenti, U-14);
`NO_APP_KEY`/`INVALID_APP_KEY` non ritentate dal nuovo (par. 9.3). Ritorno: `ARCH_SESSIONE[_UNICA]=vecchio` + riavvio a bot
flat.

**(6) Stima.** Fase a M (3-4 giorni) + 1 giorno di ombra; fase b M (3 giorni, piu' il Passo 0) + 1 giorno. Cloud: codice,
test, replay calcio. PC: ombra REST 1 h, conteggi della «Salute», replay tennis, firma; utente: permesso D-1, riavvii.

### 6.2 W1-A2 - ladder a ogni cambio, 20 ms (T6)

**(1) Punti e modifica minima.** `ARCH_LADDER=vecchio|ombra|nuovo`.
- Calcio: dopo `session.recorder = recorder` (`runner.py:2977`) si crea `LadderEvento(profilo_ladder("calcio"), meta=...,
  pubblica=..., scrivi_db=..., marca_canale=...)` (`nucleo/betfair/ladder.py:265`, `:95`); `MarketRecorderStrategy.
  process_market_book`/`process_closed_market` (`Betfair/stream/recorder.py:189`, `:209`) chiamano `ladder.consumatore(book)`
  (una riga sotto interruttore); `meta(mid)` dalle mappe della sessione (`session.market_to_event`, `markets_by_event`,
  `selection_names`, esclusi i `finished_events` come `runner.py:711-714`).
- Tennis: `_Capture.process_market_book`/`process_closed_market` (`tennis_runner.py:429`, `:433`), meta da
  `market_meta[ev].market_id`.
- In `nuovo` il `ladder_worker` non si registra: `runner.py:3108-3112`, `tennis_runner.py:3425-3429`; `pubblica=_lc.publish`,
  `scrivi_db=db.upsert_live_ladder` / `tennis_db.upsert_tennis_ladder` sul thread proprio del ladder (il DB esce dal thread
  del worker: oggi `db.upsert_live_ladder`, `db.py:668`, gira nello stesso giro del canale, `runner.py:755`), `marca_canale=_mon.marca_ladder` se `_mon.ATTIVO` (`runner.py:750`).
- Cadenza: `intervallo_min_ms` 20 per mercato (`ladder.py:276,287`). Oggi il canale e' a 200 ms (`config_stream.py:74`
  `LIVE_LADDER_CANALE_MS`, `tennis_runner.py:111`), il DB a 0,3 s dall'app (`ambiente_runner.js:70-71`).

**(2) Ombra.** In `ombra` il `LadderEvento` pubblica su un registratore di firme (non sul canale); il `ladder_worker` resta
il publisher vero. Confronto per mercato della sequenza `status|sha1` (firma `ladder_signature`): criterio 0 firme del nuovo
che il vecchio non abbia per lo stesso book, `updated_ms` crescente, latenza `ts_pub_ms - pt` (marca di T0A,
`sonde.py:198` `marca_ladder`) p50/p99 MINORE di oggi; CPU del processo (psutil di T0A) misurata (W1-A2: +0,15% di un core
con una partita, -7% con dieci, in laboratorio); `saltati_client` del canale (`local_channel.py:652-708`) non peggiore. Una
giornata calcio e una tennis.

**(3) Replay.** Il ladder non e' nel banco (⊘ con causa). Prove: `nucleo/betfair/tests/test_a2_ladder_parita.py` (payload e
firma su 35760084 e 35797769, sequenza del topic calcio e tennis, cadenza 20/200 ms) e `A2_PARITA_COMPLETA=1` (35797769
completa, ~13 min: durata dichiarata); vitest `localTransport.test.ts`, `canaleRunner.test.ts`, `localChannel.test.ts`
verdi senza modifiche.

**(4) Decisioni.** 12 (massima velocita': 20 ms di serie), 10 (tempo reale: il ladder viene dal flusso, il DB a lato).

**(5) Rischi e ritorno.** Piu' messaggi sul canale (tetto 64 in volo): il ladder nuovo ripubblica tutto dopo un salto
(`ladder.py` `RIPARO_MIN_S`); chiusura del mercato diversa fra calcio e tennis riprodotta come oggi (W1-A2 D3). Ritorno:
`ARCH_LADDER=vecchio`.

**(6) Stima.** S-M (2-3 giorni) + 2 giornate di ombra. Cloud: codice e parita'. PC: ombra, prova a schermo, CPU, firma.

### 6.3 W1-C1 - porta degli ordini (T10)

**(1) Punti e modifica minima.** `ARCH_ORDINI_PORTA=vecchio|ombra|nuovo`, PER ATTORE (`safe`, `omega`, `mike`, `desktop`,
`risk`), letto nel motore (il banco lo eredita: `porta_banco.py:446-447` costruisce il `MotoreOrdini` di produzione).
- `motore_ordini.py:974` `_gestisci` -> `PortaLocale.invia` (`nucleo/ordini/porta.py:173`) con `EsecutoreRunner`
  (`esecutori/runner.py:68`, chiama `MotoreOrdini._pre_invio` `motore_ordini.py:1450` e `live_order_worker._dispatch`) e il
  diario del motore; `:1061` `_controlla` -> `controlli.controlla` con `FreniDiOggi`; `:2280` `_rispondi_da_seq` ->
  `PortaLocale.da_seq`; `:2494` `_carica_visti` -> `apri`. Restano al motore: aggancio al volo, place-and-trim,
  equivalente, sorveglianza `INVALID_BET_SIZE`, riprezzi (W1-C1 par. 8.1).
- Costruzione: `runner.py:2555-2564` (`_costruisci_motore`, calcio, diario `DATA_DIR/_diario_ordini`) e
  `esecutore_tennis.py:613-615` (tennis, diario `DATA_DIR/_diario_ordini/tennis`, `tennis_runner.py:2925-2929`; motore spento
  di serie). Archivio della porta: `ArchivioLocale` in `cartella_processo("runner-calcio")` e
  `cartella_processo("runner-tennis")` (`nucleo/dati/percorso.py:86`, base `:64`): DUE cartelle sorelle, mai annidate
  (decisione 7; `ArchivioGiaInUso` impedisce due porte sullo stesso archivio, W1-C1 par. 9.14).
- Lato bot (client): `safe_strategy/porta_ordini.py:541` `PortaCanale` e `:359` `MemoriaComandi` -> `ConsumatoreEventi`
  (`nucleo/ordini/eventi.py`); Omega `omega_service.py:3148` `_porta_ordini`, Mike `mike/service.py:1646` `_porta_paper`
  (aggiungere, non togliere: i test di Safe sostituiscono variabili di modulo).
- Contatore delle transazioni: `ContatoreTransazioni` (`controlli.py:89`) UNO nel processo del runner con il tetto di oggi
  (`config_stream.py:262` `LIVE_TRANSACTION_LIMIT` 1000); il contatore per CONTO fra processi aspetta D-3.

**(2) Ombra.** Dal vivo, in PAPER: il motore esegue come oggi; la porta gira «a secco» sullo stesso comando (valida, dedup,
minimi, freni, tetto: NESSUNA esecuzione) e scrive nel registro dell'ombra il verdetto (accettato/rifiutato, codice, importo
dopo i minimi) per `ref`. Criterio: 0 differenze su N giornate paper con ordini (proposta N = 5; la base reale di ordini e'
piccola, `05` T11), salvo le differenze DICHIARATE e approvate (desktop non multiplo di 0,50 rifiutato, decisione 3;
fail-closed ad archivio giu', W1-C1 par. 9). Sul banco: stessa `RichiestaOrdine` -> stessa sequenza di `EventoOrdine` (fasi
per ref, bet_id simulati, rifiuti con lo stesso codice).

**(3) Replay** (con `ARCH_ORDINI_PORTA=vecchio` e poi `nuovo`, sempre `--ombra` sulla cassetta congelata):
`safe_base 35760084 --scenari rapidi --trasporto entrambi`; `safe_base 35760084 --scenari esiti-ignoti,riavvio,ordini-manuali,due-lay,manuale-e-bot,cashout-globale --trasporto canale`;
`omega 35760084 --scenari tutti --trasporto canale`; `omega 35797769 --scenari tutti` (durata ~1033-1466 s su macchina
condivisa, oltre il tetto: dichiarata, R2 di T0B4); `mike 35760084 --scenari tutti --trasporto canale`; `mike 35777617`,
`35768365`, `35774000 --scenari base`; `safe_tennis 35795993 --scenari tutti` (motore tennis acceso nel banco, trasporto
47332, `trasporto.py:62`). Sul PC anche le 22 partite di Safe (`_live_raw/`, `05` T0C tabella C). Scalper e tennis non
passano dalla porta (U-15): innocuita' `scalper_calcio 35797769 --scenari base`, `tennis_pro 35790089 --scenari base`.

**(4) Decisioni.** 3 (desktop: rifiuto, bot invariati), 7 (cartelle diverse per sport).

**(5) Rischi e ritorno.** Doppio ordine nella finestra di passaggio (dedup per ref che sopravvive: la porta scrive il diario
del motore prima dell'archivio, quindi al ritorno su `vecchio` `_carica_visti` ritrova i ref); porta sincrona e serializzata
come il thread unico del motore (latenza misurata p95 0,96 ms, `ondata1/INTEGRAZIONE.md:25-28`); archivio giu' = rifiuto
(nuovo: va detto all'utente); un'eccezione prima dell'invio diventa esito IGNOTO (piu' rumoroso, direzione sicura).
Ritorno: `ARCH_ORDINI_PORTA_<ATTORE>=vecchio` + riavvio senza ordini vivi.

**(6) Stima.** M-L (4-6 giorni) + 5 giornate paper di ombra. Cloud: codice, banco calcio. PC: `safe_tennis`, 22 partite,
ombra paper, firma. Live: solo su ordine dell'utente.

### 6.4 W1-C2 + stream ordini del conto (T11)

Tre passi, dal piu' sicuro.

**T11a - libro del conto sul ladder, sola lettura, 0 connessioni in piu'.** `ARCH_LIBRO_CONTO=vecchio|ombra|nuovo`.
- Punti: `engine/live_trading_strategy.py:176` (dove si installa `esiti_ordini_canale.osserva_conto_su_flumine(flumine,
  _LC.publish)`, `esiti_ordini_canale.py:815`) e `:214` (gemello paper): la `pubblica` viene avvolta e il topic `conto`
  (`esiti_ordini_canale.py:677`, grafia di `listCurrentOrders`) alimenta `LibroConto.ricevi_live`
  (`nucleo/ordini/libro_conto.py:244`) via `ordine_da_riga_conto`, il topic `conto_paper` (`:691`) `ricevi_prova`. Il topic
  `conto` resta identico (lo leggono Mike e i bot). Un libro per runner: calcio sul 47331, tennis sul 47332 (decisione 7).
- Topic nuovo `libro_conto` (schema W1-C2 par. 8.2: ordini con autore, abbinato, residuo, prezzo medio, comandi; posizione
  con `se_vince` per selezione e per autore; un messaggio per modo, paper e live MAI insieme), coalescenza 20 ms come il ladder.
- UI: `frontend/src/components/live/LadderView.tsx:252-303` (`buildLadder`, oggi `position.matched_if_win` dallo specchio,
  `:288`) dietro un interruttore locale della UI (`ui.libro_conto`, come `lib/uiShell.ts`); contratto TS generato dallo schema
  (PSB par. 7 n.33); `npm run build` lo fa l'utente ad app spenta.
- Comandi dal ladder: `comandi_ammessi` (`libro_conto.py:844`) SOLO su ordini `desktop`/`sito`; sugli ordini dei bot spenti
  finche' l'utente non decide (D-5). Ordine col solo riferimento manuale = «da confermare» (decisione 6, gia' cosi').
- Ombra: libro contro specchio `betfair_live_orders` per `bet_id` (abbinato, prezzo medio, stato) e P&L contro il calcolo del
  frontend di oggi: 0 differenze su 3 giornate; le divergenze di attribuzione D1-D8 di W1-C2 par. 9 restano dichiarate.

**T11b - UN solo stream ordini per l'app (decisione 13).** `ARCH_ORDINI_CONTO=vecchio|ombra|nuovo` (nel referto W1-A2
`spento|ombra|acceso`; uniformato allo schema).
- L'host apre `FlussoOrdiniContoBetfair` (`nucleo/betfair/flusso_ordini_conto.py:490`), filtro e ripresa con `clk`, seme REST
  `listCurrentOrders` dopo una partenza da zero (W1-A2 D7) dato dal libro tramite la REST unica di A1.
- PAPER (`nuovo` di serie per prima cosa): e' l'unico stream ordini reale (oggi in PAPER non ce n'e' nessuno: `runner.py:2270-2280`),
  9/10 nel caso peggiore; il libro vede gli ordini del sito e quelli di Mike live REST anche col runner in PAPER.
- LIVE: lo stream del conto SOSTITUISCE quelli di flumine con `order_stream_cls=OrderStreamDaNucleo` (par. 3.2.2) in
  `tennis_runner.py:158-160` PRIMA (meno ordini), poi `scalper_session.py:927-942` (ramo LIVE), per ultimo `runner.py:2251-2261`.
  Mai aggiunto senza sostituire (decisione 13): in LIVE l'host apre lo stream del conto solo quando il PRIMO processo
  sostituisce il suo (stesso numero di connessioni).
- Ombra LIVE senza connessioni in piu': quando il runner tennis e' sostituito, il runner calcio ha ancora il SUO stream
  flumine, che riceve gli stessi ordini (non filtrato, par. 2.3): si confrontano per `bet_id` gli stati di blotter (calcio,
  vecchio) e del libro dell'host (nuovo); poi, sostituito il calcio, il confronto si fa con `listCurrentOrders` della
  riconciliazione (`reconcile_worker.py:1302`). Criterio: 0 differenze di stato/abbinato/prezzo medio per 5 giornate LIVE
  con ordini (le giornate LIVE le decide l'utente). Flumine nel processo sostituito: stessi `CurrentOrdersEvent`, stesso
  blotter (test sul server TLS finto con la stessa sequenza `ocm` via socket diretto e via host).

**T11c - riconciliatore in ombra.** `ARCH_RICONCILIA=vecchio|ombra`: `reconcile_worker.py:1306-1316` (dopo la lettura dello
specchio, prima di `_reconcile_orders`) e accanto a `riprendi_da_diario` (`motore_ordini.py:2506`): `RiconciliatoreOmbra.giro`
(`nucleo/ordini/riconciliazione.py:192`) sugli STESSI dati gia' letti, referto nel registro dell'ombra. Criterio (W1-C2 par.
8.4): le divergenze dell'ombra che corrispondono alle azioni di R1/R2 coincidono una per una; quelle in piu' sono spiegate.

**(3) Replay.** Il libro e lo stream reale non sono nel banco (⊘: nessuna registrazione `ocm`). Innocuita' con `--ombra`:
`safe_base 35760084 --scenari manuale-e-bot,ordini-manuali --trasporto canale`, `omega 35760084 --scenari base`,
`mike 35760084 --scenari base --trasporto canale`, `scalper_calcio 35797769 --scenari base`, `tennis_pro 35790089 --scenari
tutti`, `safe_tennis 35795993 --scenari tutti` (il banco usa `SimulatedOrderStream`: `order_stream_cls` si monta solo sul
client LIVE reale, quindi il banco DEVE restare identico). Test: `test_c2_*` (265), `test_a2_*` dello stream ordini.

**(4) Decisioni.** 5 (se vince su ogni mercato), 6 (da confermare), 8 e 13 (un solo stream ordini, la REST solo per il seme e
la riconciliazione), 7 (un libro per sport).

**(5) Rischi e ritorno.** Il difetto della libreria sugli `ocm` senza `rfo`/`rfs` (W1-A2 D6) vale anche per flumine di oggi:
l'host inoltra il messaggio GIA' normalizzato (meglio di oggi); da guardare un `ocm` vero del sito nei log del PC prima di
T11b. Una ripresa da immagine dello stream del conto la vedono tutti i processi insieme (come oggi quando flumine riparte).
Ritorno: `ARCH_ORDINI_CONTO=vecchio` riporta `order_stream=True` normale in ogni processo (riavvio a bot flat).

**(6) Stima.** T11a M (3-4 giorni) + 3 giornate; T11b M-L (5-6 giorni, oltre al Passo 0) + 5 giornate LIVE; T11c S-M (2-3
giorni) + N giornate. Cloud: codice, test sul server finto. PC: ombre, build, firma; utente: giornate LIVE.

### 6.5 W1-G2 - client cloud unico, registro, cache degli algoritmi (T2, T7)

**(1) Punti.** T2 `ARCH_DATI_CLIENT=vecchio|nuovo` (`nucleo/dati/cloud.py:60,101`): nei `main` accanto a `usa_timeout_bot()`
- `mike/service.py:7764`, `omega/omega_service.py:9156`, `safe_strategy/bot_service.py:11181`, `safe_strategy/service.py:3366`
- un `ClienteCloud("bot").attiva_profilo()` (`cloud.py:219`); `Betfair/stream/db.py:44` e `tennis_live/tennis_db.py:66`
(`_exec_retry`) passano da `con_ritentativi` SOLO per gli upsert sulla chiave naturale. Registro: gia' nella suite.
T7 `ARCH_PREFETCH_OMEGA` / `ARCH_PREFETCH_MIKE` (`cache_cloud.py:70`): Omega `omega_service.py:1437`, `:1449`, `:1561`, `:1570`
(`_minute_table`/`_empirical_table`) leggono dalla `ReplicaEmpirica` (`cache_cloud.py:149`) in `nuovo`; Mike
`mike/service.py:4486`, `:6967` (`build_prematch`) con `DossierPrematch` (`cache_cloud.py:422`) e `:5439` (`get_empirical`), con
ripiego sincrono SEMPRE acceso per Mike (W1-G2 D6). Sentinella rapida del Passo 0 (decisione 10).

**(2) Ombra.** T7: in `ombra` Omega e Mike chiamano replica e RPC e confrontano riga per riga (`get_omega_ht_ft`,
`get_omega_minute_ft`, dossier): 0 differenze per 3 giornate, salvo la finestra fra ricalcolo del cloud e rilettura della
sentinella (misurata, W1-G2 D5). T2: stessi esiti sulla griglia dei guasti; 0 ritenti di insert/4xx/57014; conteggio delle
richieste per tabella nella «Salute» non maggiore di oggi.

**(3) Replay** con `--ombra`: `omega 35760084 --scenari tutti`, `omega 35797769 --scenari tutti`, `mike 35760084 --scenari
tutti`, `mike 35777617`/`35768365`/`35774000 --scenari base`, col finto alimentato dalla replica e con la prova «rete che
rifiuta tutto» (`05` T7). Innocuita' T2: `safe_base 35760084 --scenari rapidi --trasporto entrambi`.

**(4) Decisioni.** 10 (il cloud solo backup e per cio' che CALCOLA; aggiornamento appena ricalcola), 11 (i due script batch
restano sul client di oggi: `generate_dynamic_cal.py:459`, `load_poisson_calibration_to_db.py:65` non si agganciano).

**(5) Rischi e ritorno.** D1 di W1-G2: oggi `net_retry` ritenta anche 57014 e gli `OSError` nudi nel runner e nel tennis; col
client nuovo no: decisione D-2 prima di `nuovo` sui runner. Ritorno: interruttori.

**(6) Stima.** T2 S-M (2-3 giorni), T7 M (3-4 giorni) + 3 giornate. Cloud: codice, banco calcio. PC: confronto contro le RPC
vere (DB in sola lettura), firma.

### 6.6 W1-G1 - archivio locale e postino dei log (T8)

**(1) Punti.** Prerequisito: la migrazione `migrations/architettura_uid_ombra_2026-10-09.sql` applicata dall'utente (uid e
tabelle `_ombra`). Cartella: `ARCH_ARCHIVIO_DIR` in `desktop/ambiente_runner.js:60-84` (funzione pura, con il suo test) dal
`main.js:365` (`%LOCALAPPDATA%\AlphaScore Trading\archivio`; senza variabile il Python sceglie la stessa, `percorso.py:64`).
Una cartella per processo: `runner-calcio`, `runner-tennis`, `mike`, `omega`, `safe`, `scanner`, `tennis-bot`,
`scalper-<event_id>` (decisione 7). `ARCH_POSTINO_LOG=vecchio|ombra|nuovo` con una facciata `scrivi_log(tabella, riga,
vecchio)` (nuova, `nucleo/dati/facciata.py`) ai punti verificati: `mike/db.py:76`, `omega/omega_db.py:63`,
`safe_strategy/bot_db.py:89`, `tennis_live/tennis_db.py:521`, `stream/db.py:644` (`live_run_log`), `:697` (`live_alerts`),
`:988` (`betfair_live_journal`), `live_order_worker.py:922` (`betfair_live_audit`), `:1071` (`live_alerts`), `:1134`
(`betfair_live_journal`), `motore_ordini.py:2583` (`live_alerts`), `daily_stop_worker.py:391` (`betfair_live_audit`), e gli
scrittori dello scalper elencati da W1-G1 par. 8.2. Fuori da T8: `theta_confirm_requests` (non e' un log, W1-G1 par. 9.2).
Apertura dell'archivio nei `main` accanto alle righe di 6.5; `postino.ferma()` poi `archivio.chiudi()` all'arresto.

**(2) Ombra.** La insert di oggi resta; il postino (`postino.py:221`, `ombra=True`) scrive SOLO su `<tabella>_ombra`;
confronto notturno `confronta_ombra(tabella, ["kind","event_id"], "ts", giorno) == []` per 5 notti; prova sotto carico sul
PC (R08): L2/L6 p99 non peggiori oltre la variabilita' di due giri identici, altrimenti U-82; prova `os._exit` a meta' (0
righe perse).

**(3) Replay.** Il banco usa `DbMemoria` (⊘ per le scritture vere). Innocuita' con `--ombra`: `mike 35760084 --scenari base`,
`omega 35760084 --scenari base`, `safe_base 35760084 --scenari rapidi --trasporto entrambi`, `scalper_calcio 35797769
--scenari base`, `tennis_pro 35790089 --scenari base`. Test `test_g1_*` (136, anche su PostgreSQL vero sul PC).

**(4) Decisioni.** 9 (riga illeggibile messa da parte e ritentata), 10 (il cloud riceve dopo, mai nel percorso), 7.

**(5) Rischi e ritorno.** Istante dei log = istante dell'evento (meglio, ma diverso: da approvare, W1-G1 par. 9.1); i lettori
UI che usano `id` della riga pubblicata (`mike/db.py:77-78`) vanno verificati; `msvcrt.locking` e `%LOCALAPPDATA%` provati
solo sul PC. Ritorno: `ARCH_POSTINO_LOG=vecchio` (la scrittura diretta resta fino a T24).

**(6) Stima.** M (4-5 giorni) + 5 notti. Cloud: codice. PC/utente: migrazione, ombra notturna sul DB, prova di uccisione.

### 6.7 W1-B - stato della partita (T9)

**(1) Punti.** `ARCH_STATO_PARTITA=vecchio|ombra|nuovo`.
- Runner calcio, ombra: `runner.py:350` (`snap = poller.poll(event_id)`): busta dallo stesso `snap` e `stato_da_lettura`;
  confronto prima di `db.update_live_now` (`runner.py:377-382`) su minuto, gol, `inplay` (regola del runner `:361-365`).
- Runner tennis, ombra: `tennis_runner.py:1663` (`parse_tennis_scores`): `stato_tennis_da_grezzo` sullo stesso `raw`, confronto
  di `chiave_tennis` con `ts.key()` e `point_pressure` prima di `tennis_db.upsert_tennis_now` (`:1699`).
- Lettori, ombra: Omega `omega_service.py:9250` (`_build_score_lookup`), Mike `mike/feed.py:493` (`snapshot_from_row`), Safe
  `safe_strategy/engine.py:789` (`_fase_da_scan`): `stato_calcio_da_riga` sulla stessa riga, `in_gioco` contro
  `payload.inplay` (mai contro `live_now`, W1-B div. 9).
- Nuovo, runner calcio: `runner.py:2203-2207` (`ScorePoller`) -> `FonteCircuitoCalcio(FonteIpsRunner(...), ...)` in un
  `ServizioStatoPartita` (`nucleo/stato_partita/servizio.py:304`) per sessione. Lato scanner (`safe_strategy/service.py:1738`
  `poll_scores`, `:1777` `apply_score_state`) PER ULTIMO, dopo T17. Scalper solo con U-11.

**(2) Ombra.** 0 discrepanze su minuto/gol/rossi/fase/tempo e sull'esito del flusso per 5 giornate calcio, poi 3 tennis; eta'
del punteggio riportata; tempi del giro non peggiori.

**(3) Replay.** Parita' per tick gia' provata sui sidecar (35760084, 35797769; test `test_b_*` 224). Per `nuovo` dei lettori:
TUTTI i bot calcio con `--ombra` (`mike 35760084 --scenari tutti`, `omega 35760084/35797769 --scenari tutti`, `safe_base
35760084 --scenari rapidi --trasporto entrambi`, `scalper_calcio 35797769 --scenari base`); tennis `tennis_pro 35790089`,
`tennis_flb 35795993`, `tennis_swing 35794049`, `tennis_scalper 35794049 --scenari tutti` sul PC o nel cloud (ora le
registrazioni sono nel repo).

**(4) Decisioni.** 4 (fase dedotta come Omega, marcata), 10 (stato pubblicato a evento).

**(5) Rischi e ritorno.** Lo scanner serve 4 bot (taglio per ultimo); differenze di oggi fra lettori riprodotte, non scelte
(W1-B par. 9). Ritorno: interruttore.

**(6) Stima.** M (4-5 giorni) + 5+3 giornate. Cloud: calcio. PC: tennis, ombra, firma.

### 6.8 W1-A2 - gestore unico dei flussi (T19)

**(1) Punti.** `ARCH_FLUSSO_<PROFILO>=vecchio|nuovo` (nessuna ombra con due connessioni uguali sul vivo, `05` T19). Ordine:
tennis (1 connessione), scalper (da N a 1), calcio, scanner (dopo T17, decisione U-07 gia' implicita nella risposta 8).
- Tennis: `tennis_runner.py:484-485` `stream_class=TennisRecMarketStream` -> sottoclasse `MarketStreamDaNucleo` con il tee di
  `tennis_recorder.py:464` (il raw si registra come oggi).
- Scalper: le strategie di `scalper_session.py:1650-1830` ricevono `stream_class=MarketStreamDaNucleo` (profilo
  `scalper_partita`); l'host mette i mercati di tutte le partite su UNA connessione.
- Calcio: `runner.py:2963` `stream_class=_FR.FrammentoMarketStream` -> versione da host; `GestoreFrammenti`
  (`frammenti_mercato.py:356`, `manutenzione` `:608`) delega piano e aperture all'host (`GestoreFlussi.imposta_mercati`,
  `flusso.py:547`); `connectionsAvailable` letto UNA volta dall'host.
- Scanner: `safe_strategy/stream.py:421` (`create_stream`) -> listener dall'host; il piano a shard `id mod N` (`:103`) diventa
  quello del gestore (cambia la distribuzione, non i dati: W1-A2 D2, da provare).
- Board e ripiego dello scanner (`board_worker.py:387`, `safe_strategy/service.py:1672`): leggono dai book dell'abbonamento;
  la REST resta SOLO se il mercato non ha stream (budget esaurito o guasto), contata nella «Salute».

**(2) Ombra.** Sul banco: le 40 registrazioni `_live_raw/*` (sul PC) lette dal `GestoreFlussi` via `HistoricalStream` e
passate attraverso il trasporto dell'host danno gli STESSI `MarketBook` campo per campo; scenari di caduta e ripresa
(`resubscribe`, frammento muto > 180 s, relogin con ordini vivi, `status:503`). Dal vivo, «ombra del trasporto» con 0
connessioni in piu': il consumatore, ancora `vecchio`, passa le SUE righe grezze attraverso un host di prova sul loopback in
un listener ombra e confronta le firme dei book e la latenza aggiunta; criterio: 0 differenze, ritardo p99 <= 5 ms (il
loopback di laboratorio fa 0,635 ms p50 / 4,12 ms p99, `04` L4) e nessun messaggio perso. Poi `nuovo` per profilo, prima in
PAPER.

**(3) Replay.** `test_a2_*` (173 + 31 di parita'); `certifica tennis_pro 35790089 --scenari tutti`, `tennis_scalper 35794049
--scenari tutti`, `scalper_calcio 35797769 --scenari base`, `mike/omega/safe_base 35760084` e `omega 35797769` con
`--ombra` (il banco legge il grezzo con `HistoricalStream`: lo stesso ingresso del consumatore nuovo). Per lo scanner, i
replay di T17.

**(4) Decisioni.** 8 (un gestore, la REST solo di riserva), 1 (nessuna connessione apre una sessione propria), 12 (il ladder
riceve ogni book).

**(5) Rischi e ritorno.** Il punto unico di guasto (R1); la latenza aggiunta (R2); `heartbeatMs`/`conflateMs` NON si toccano
(U-01, U-02, U-03); `serialize_book` ha 8 consumatori (uno per uno, `05` T19). Ritorno: `ARCH_FLUSSO_<PROFILO>=vecchio`
(il consumatore riapre la sua connessione come oggi) + riavvio a bot flat.

**(6) Stima.** L (7-9 giorni, `05` T19) piu' il Passo 0. Cloud: codice, banco calcio. PC: 40 registrazioni, tennis, paper,
firma.

---------------------------------------------------------------------------------------------------

## 7. Le decisioni dell'utente e dove si realizzano

| # | Decisione (10/10) | Dove | Comparto / passo |
|---|---|---|---|
| 1 | Una sola sessione per tutta l'app | host + `SessioneOspite` + client flumine senza login; i 12+6 punti del par. 2.2 | A1 fase b (6.1) |
| 2 | Attesa anche su `segnala_errore`, «sempre una sola connessione» | `sessione.py:355-364`; nessun login di riserva negli ospiti (3.5) | Passo 0, A1 |
| 3 | Desktop: punta non multipla di 0,50 rifiutata | `minimi.verdetto_desktop` nella porta per l'attore `desktop` | Passo 0, C1 |
| 4 | Fase dedotta come Omega | gia' in W1-B (`fase_dedotta=True`) | B |
| 5 | «Se vince» su tutti i mercati | `pnl_mercato.py:76-86,196-254`; UI `LadderView.tsx:252-303` | Passo 0, C2 (T11a) |
| 6 | Solo riferimento manuale = da confermare | gia' in W1-C2 (`comandi_ammessi` `libro_conto.py:844`) | C2 |
| 7 | Calcio e tennis su cartelle diverse | `cartella_processo("runner-calcio"/"runner-tennis")`; un libro e un topic per sport; host senza logica di sport | C1, C2, G1 |
| 8 | Stream ovunque, REST solo di riserva, un gestore | host con `GestoreFlussi` x 4; REST del par. 2.4 righe 1-2 sostituite; le altre restano riserva o alle tappe dei bot | T11b, T19 |
| 9 | Riga illeggibile ritentata | gia' in W1-G1 | G1 |
| 10 | Tempo reale per Betfair, cloud backup | ladder dal flusso (T6), stato a evento (T9), postino dopo (T8), sentinella rapida (T7) | A2, B, G1, G2 |
| 11 | Due script batch invariati | nessun aggancio di `generate_dynamic_cal.py`, `load_poisson_calibration_to_db.py` | G2 |
| 12 | Ladder alla massima velocita' (20 ms) | `ladder.py:276,287` (`intervallo_min_ms` 20) | A2 ladder |
| 13 | Un solo flusso ordini | `order_stream_cls=OrderStreamDaNucleo` ai 3 punti; mai aggiunto | T11b |

**Decisioni NUOVE da portare all'utente** (non sono rimesse in discussione: nascono da questo piano):
- **D-1** permesso per il processo `betfair-nucleo` (par. 3), o l'alternativa B (par. 3.6). Serve prima di A1 fase b.
- **D-2** T2: oggi i runner ritentano 57014 e `OSError` nudi (`net_retry`), il client nuovo no (W1-G2 D1). Prima di T2 sui runner.
- **D-3** contatore delle transazioni per CONTO (oggi per processo; valore del tetto, chiusure sempre ammesse?) (W1-C1 par. 9). Prima di C1 `nuovo`.
- **D-4** priorita' delle connessioni quando le 10 non bastano (par. 3.4). Prima di T19.
- **D-5** comandi dal ladder sugli ordini dei bot (oggi spenti) (W1-C2 par. 8.3). Prima di T11a `nuovo`.
- Gia' scritte dai referti e ancora aperte: istante dei log (W1-G1 9.1), conservazione locale e tetto di disco (W1-G1 9.9),
  `cor` in `EventoOrdine` (W1-C1 10b, del coordinatore).

---------------------------------------------------------------------------------------------------

## 8. Rischi

### 8.1 I cinque principali

| # | Rischio | Dove nasce | Mitigazione | Ritorno |
|---|---|---|---|---|
| R1 | `betfair-nucleo` punto unico di guasto: un suo crash ferma prezzi, ordini del conto e rinnovo della sessione per tutti | par. 3 | nessuna logica di bot dentro; watchdog come gli altri; fermato per ULTIMO (`main.js:527-556`); il token resta valido fino a 20 min, gli ordini (REST) continuano; i consumatori riconoscono il flusso muto come oggi (`frammenti_mercato.py:98` `MUTO_S`); aggancio per profilo, il calcio per ultimo | `ARCH_*=vecchio` per comparto: ogni processo torna alle sue connessioni |
| R2 | Trasporto locale con perdite o lento: il `publish` di oggi SALTA i client lenti (`local_channel.py:663-708`) e un `mcm`/`ocm` saltato rompe la cache | 2.5, 3.3 | trasporto nuovo con sequenza per abbonato, distacco oltre un tetto, immagine piena al buco; «ombra del trasporto» dal vivo; ritardo p99 <= 5 ms | interruttore per profilo |
| R3 | Stream ordini sostituito in LIVE senza prova sul banco (nessuna registrazione `ocm`; difetto `rfo`/`rfs` della libreria) | 6.4 | server TLS finto con `APIClient` vero; sostituzione un processo alla volta (tennis prima) con confronto contro lo stream ancora vecchio del calcio; messaggi normalizzati dall'host; un `ocm` vero del sito letto nei log del PC prima | `ARCH_ORDINI_CONTO=vecchio` |
| R4 | Porta degli ordini nel percorso dei soldi: doppio ordine nella finestra di passaggio, fail-closed nuovo, contatore per conto | 6.3 | dedup per ref nel diario del motore (sopravvive al ritorno), ombra a secco in PAPER, replay `--trasporto entrambi`, attore per attore, live solo su ordine | `ARCH_ORDINI_PORTA_<ATTORE>=vecchio` |
| R5 | Sessione unica: un relogin cambia il token per tutti; il login di avvio di flumine (`baseflumine.py:498`) e il relogin del worker `keep_alive` (`flumine/worker.py:116`) aprirebbero sessioni nuove | 6.1 | client flumine senza login (modello `client_paper_affiancato.py:43-55`); un relogin per generazione; contatore dei login = 1 nella «Salute»; un processo alla volta | `ARCH_SESSIONE_UNICA=vecchio` |

### 8.2 Gli altri (per comparto)

- Budget delle connessioni durante i passaggi: mai 11/10 (lo stream del conto in LIVE si apre solo quando il primo processo
  sostituisce il suo; nessuna ombra con connessioni doppie).
- Riavvii: ogni `nuovo`/`vecchio` richiede un riavvio dell'app, che fa l'utente, mai con posizioni (`05` R13).
- Ladder: carico sul canale (64 in volo) e CPU, misurati in ombra.
- G1: GIL sotto carico (R08), Windows non provato nel cloud.
- B: lo scanner serve 4 bot (taglio per ultimo).
- T19: la distribuzione dei mercati dello scanner cambia (`plan_shards` contro il piano a riempimento).

---------------------------------------------------------------------------------------------------

## 9. Stime e chi fa cosa

| Passo | Stima | Cloud da solo | Richiede il PC (app accesa, replay tennis/22 Safe, paper, firma) | Utente |
|---|---|---|---|---|
| Passo 0 | L (7-9 g) | tutto (codice nuovo nel nucleo, test, falsificazione) | - | - |
| A1 fase a (T5) | M (3-4 g) + 1 g | codice, test, replay calcio | ombra REST 1 h, conteggi Salute, replay tennis, firma | si' a master, riavvii |
| A1 fase b | M (3 g) + 1 g | codice, `main.js` (vivo, nessuna ricompilazione) | ombra, conteggio login = 1, firma | **D-1**, riavvii |
| A2 ladder (T6) | S-M (2-3 g) + 2 g | codice, parita' sulle registrazioni | ombra calcio e tennis, schermo, CPU, `npm run build`, firma | si' a master |
| C1 porta (T10) | M-L (4-6 g) + 5 g paper | codice, banco calcio (Safe, Omega, Mike) | `safe_tennis`, 22 partite di Safe, ombra paper, firma | **D-3**, live solo su ordine |
| C2 + ordini (T11 a, b, c) | M + M-L + S-M (10-13 g) + giornate | codice, server finto | ombre (3 g paper, 5 g LIVE), build, firma | **D-5**, giornate LIVE |
| G2 (T2, T7) | S-M + M (5-7 g) + 3 g | codice, banco calcio | confronto contro le RPC vere (DB sola lettura), firma | **D-2** |
| G1 (T8) | M (4-5 g) + 5 notti | codice | migrazione (utente), ombra notturna, `os._exit`, firma | applica la migrazione |
| B (T9) | M (4-5 g) + 8 giornate | codice, calcio | tennis, ombra, firma | - |
| T19 gestore | L (7-9 g) | codice, banco calcio | 40 registrazioni, tennis, paper, firma | **D-4** |
| **Totale** | **~49-64 giorni di lavoro** (somma delle righe) + ombre di calendario | | | |

Il totale e' nell'ordine delle stime di `05` par. 5 per le stesse tappe (T2 2-3, T5 3-4, T6 2-3, T7 3-4, T8 4-5, T9 4-5,
T10 3-4, T11 4-5, T19 7-9 = 32-42 giorni) piu' il Passo 0 e l'host (non previsti da `05`: nascono dalle risposte del 10/10)
e la sostituzione dello stream ordini in LIVE.

---------------------------------------------------------------------------------------------------

## 10. Copertura di PSB par. 6 e 7 (cosa ogni aggancio deve sollecitare)

- 6.1 dati di mercato: T19 (stesso grezzo, `HistoricalStream`), B (punteggi col ritardo di produzione).
- 6.3 servizio intero e cadenza: C1, G2-T7, B (replay con `run_once` dei bot, nessun cambio di cadenza).
- 6.4 ciclo di vita dell'ordine: C1 (dedup, esito ignoto, rifiuti, minimi .it), T11 (stato da Betfair, mai dedotto).
- 6.5 persistenza e UI: G1 (righe vere, `CHECK`), C2 (campi del ladder: chiesto, abbinato, residuo, prezzo medio, stato).
- 6.6 concorrenza e limiti: A1 (login, 3 concorrenti, pesi), T19 (10 connessioni, 200 mercati), C1 (transazioni).
- 6.7 scenari e falsificazione: ogni test nuovo falsificato; `--ombra` falsificata in T0C.
- 6.8/6.9 referto riproducibile e durata dichiarata: ogni `certifica` col comando esatto e la cassetta.
- Catalogo par. 7: n.1-7 (C1, C2: grafie `listCurrentOrders`, `ok` letto, ref di piazzamento), n.10 (`order.status` Enum nel
  libro), n.18 (G1: scrittura fallita mai warning), n.20 (A1: battito vivo non e' sessione utilizzabile), n.21 (paper e live
  mai sommati nel libro e nei P&L), n.27 (finti con chiavi e tipi del vero: server TLS finto + `APIClient` vero), n.33 (UI
  dallo schema), n.35 (nessun test mai visto rosso).

---------------------------------------------------------------------------------------------------

## 11. Cosa ho verificato di persona / cosa NON ho potuto verificare

**Verificato (lettura del codice su `d073ddcb`):** tutti i `file:riga` di questo documento; il modulo di serie del watchdog
(`watchdog.py:65`); che i file di produzione non sono cambiati da `559a96df`; che flumine 2.13.11 accetta
`order_stream_cls` (`flumine/clients/baseclient.py:35,63`, `streams/streams.py:81-89`) e `stream_class`
(`strategy/strategy.py:46,77`); che `betfairlightweight` 2.23.2 ha `set_session_token` (`baseclient.py:99`); che lo stream
ordini di flumine non passa `clk` e chiede `partition_matched_by_strategy_ref=True, include_overall_position=False`
(`orderstream.py:40-50`); che flumine fa `clients.login()` all'avvio (`baseflumine.py:498`); le porte 47317 e 47339 non
usate (`git grep`); che il nucleo non ha oggi un modo di ricevere un token dall'esterno (`nucleo/betfair/sessione.py`: nessun
`set_session_token`) ne' di inoltrare i grezzi ad altri processi (`flusso.py:849-900` consegna `MarketBook` in processo).

**Righe dei referti dell'ondata 1 che NON corrispondono al codice** (vanno usate le mie): W1-B par. 8 cita
`tennis_runner.py:1652` e `:1685` (veri `:1663` `parse_tennis_scores`, `:1699` `upsert_tennis_now`), `omega_service.py:8905`
(vero `:9250` `_build_score_lookup`), `bot_service.py:3214,3409` (righe non pertinenti; il lettore della fase e'
`safe_strategy/engine.py:789`), `mike/feed.py:425-475` (il lettore e' `snapshot_from_row` `:493`); W1-G1 par. 8.2 cita
`mike/service.py:7435`, `omega_service.py:8815`, `bot_service.py:10871`, `service.py:3363` (veri `:7764`, `:9156`, `:11181`,
`:3366`, come W1-G2); `04` e `05` citano `local_channel.py:176` per il tetto dei 64 invii (vero `:184`).

**Reperti nuovi (da guardare sul PC):** (a) il login in piu' di flumine all'avvio di ogni framework (par. 2.2); (b) la
cadenza del ladder che l'app passa al DB e' 0,3 s (`ambiente_runner.js:70-71`), quella del canale resta 200 ms di serie
(`config_stream.py:74`); (c) il diario del motore tennis e' DENTRO quello del calcio (`_diario_ordini/tennis`,
`tennis_runner.py:2925-2929`): non e' un errore, ma per l'archivio nuovo le cartelle sono sorelle; (d) in PAPER con 4
sessioni scalper le connessioni di oggi sono gia' 12 (oltre il limite): chi le perde lo decidono i rifiuti di Betfair.

**NON verificato:** nessun processo, test, replay o app eseguiti (lavoro di sola lettura); nessuna prova contro Betfair
vero: che piu' connessioni TCP con lo STESSO token vadano bene e' dedotto dal codice di oggi (i 3 frammenti del calcio e lo
stream ordini condividono l'`APIClient` di `runner.py:2712`), non provato per processi diversi; la latenza reale del
trasporto locale su Windows (solo il laboratorio di `07` 2b); che lo stream del conto (W1-A2) porti a flumine gli stessi
`uo` del suo stream (filtri diversi, `orderstream.py:47-48`): da provare sul server finto e in ombra; il numero di mercati
per sessione scalper (stimato «pochi»); l'effetto di keepAlive da piu' processi sullo stesso token (atteso nullo); gli hash
delle registrazioni (non ricalcolati); le durate dei replay elencati (prese da `05` e da `AVANZAMENTO.md`, non misurate).
