# REPLAY TENNIS — sezione separata, da zero (07/10/2026)

Delegato del coordinatore, worktree `/home/user/python-database-automation/.claude/worktrees/agent-a6ea43b314ba4bc49`
(ramo `worktree-agent-a6ea43b314ba4bc49` su `8226d76`), lavoro NON committato. Ambiente cloud (Python 3.13 di sistema,
node_modules collegato con link simbolico). Ordine dell'utente (07/10): replay del tennis da zero, sezione separata, TUTTE
le funzionalita' del Match Replay, ladder e tutti i mercati, «Applica bot» separato per il tennis; poi: documentarsi sulle
librerie, design system ereditato, nessuna regressione.

Consegna: **blocchi 1, 2 e 3 fatti e verificati; blocco 4 (Applica bot, FASE 2) in attesa del lavoro dell'altro delegato**
(in pagina c'e' la sezione tennis con la struttura pronta e i comandi spenti con la ragione).

---

## 0. Ricerca (librerie installate e documentazione ufficiale)

| fonte | cosa dice | come e' usata |
|---|---|---|
| betfairlightweight 2.23.2, `streaming/betfairstream.py:320-378` (`HistoricalStream`, `HistoricalGeneratorStream`) e `endpoints/streaming.py:53-96` (`create_historical_stream`, `create_historical_generator_stream`: «Uses streaming listener/cache to parse betfair historical data») | il raw registrato si rilegge passando ogni riga a `StreamListener.on_data` | `convertitore.decodifica_raw` fa ESATTAMENTE il ciclo di `_read_loop` (registra lo stream, `on_data` riga per riga) e dopo ogni riga fotografa con `listener.snap(market_ids=<mercati della riga>)` |
| `streaming/listener.py:121-205` (`on_data`, `_on_change_message`: `SUB_IMAGE` -> `on_subscribe`, `RESUB_DELTA`, `UPDATE`) e `streaming/stream.py:175-215` (`MarketStream._process`: `img` o cache assente -> cache nuova) | immagini, ri-sottoscrizioni (i 5 buchi della 35790089) e delta gestiti dalla libreria | nessun parser nostro dello stream |
| `streaming/cache.py:22-90` (`Available`, ordinamento `reverse` per l'atb), `:93-198` (`RunnerBookCache`), `:360` (`create_resource`) | livelli ordinati, "0 vol" tolto, `MarketBook` con `market_definition` (runner `status` WINNER/LOSER, `bet_delay`, `in_play`, `open_date`) | il `MarketBook` va in `recorder.serialize_book` (lo STESSO del calcio); da `market_definition` si prendono tipo mercato, betDelay, sortPriority, esito |
| schema ufficiale dello Stream API `ESASwaggerSchema.json` (https://raw.githubusercontent.com/betfair/stream-api-sample-code/master/ESASwaggerSchema.json) | `img`: «replace existing prices / data with the data supplied: it is not a delta»; `atb/atl/trd`: «PriceVol tuple delta of price changes (0 vol is remove)»; `marketDefinition.status`: INACTIVE/OPEN/SUSPENDED/CLOSED | ORACOLO indipendente scritto nel test con queste regole (confronto frame per frame) |
| flumine 2.13.11 `streams/historicalstream.py:215-275` (`HistoricListener`, `FlumineHistoricalGeneratorStream`) | il lettore storico del banco | SECONDA ricostruzione nel test (frame per frame contro la nostra) |
| flumine docs `docs/quickstart.md` (https://github.com/betcode-org/flumine) — simulazione su file storici, filtro `event_type_ids` | nessuna funzione specifica del tennis: i lettori storici sono per qualunque sport | nessun codice tennis da riusare nelle librerie (grep di «tennis» in flumine/bflw: 0 righe utili; eventTypeId solo come campo) |
| esempio ufficiale `examples/strategies/marketrecorder.py` di flumine | registra le righe `mcm` grezze e salva A PARTE il catalogo del mercato: lo stream non porta i nomi dei runner | conferma che i NOMI vanno presi fuori dal raw (vedi §1.3) |
| betfairlightweight `resources/inplayserviceresources.py` + nostro `tennis_scalper/tennis_score.py::parse_tennis_scores` | il punteggio IPS e' quello del sidecar `.score.jsonl` | riusati `parse_tennis_scores`, `tennis_runner.tennis_score_state`, `tennis_runner.point_event` (stesso contratto `TennisScoreState`/`TennisPointEvent` della UI live) |

Siti `betcode-org.github.io` e `docs.developer.betfair.com` bloccati dal proxy del cloud: letti il codice installato,
il README del repo GitHub e lo schema ufficiale su raw.githubusercontent.

Perche' nessun parser proprio: la decodifica e' della libreria (provata contro flumine e contro l'oracolo dello schema:
5217/5217 libri identici); il record compatto e' `serialize_book` del calcio; la curazione e' quella del calcio
(`curator.curate_records`, estratta da `curate_event` senza cambiarla).

---

## 1. Cosa ho costruito

### 1.1 Dati (blocco 1)
- **Migrazione** `migrations/replay_tennis_2026-10-07.sql` (NON applicata): tabelle `tennis_replay_eventi`,
  `tennis_replay_mercati` (catalogo con selezioni, esito finale WINNER/LOSER, `bet_delay`, `settled_ts`),
  `tennis_replay_snapshots` (frame curati, ladder JSONB come il calcio, GBP storiche), `tennis_replay_punteggio`
  (`TennisScoreState`, `event_types[]`, punto); RPC `list_replays_tennis`, `get_replay_tennis_meta`,
  `get_replay_tennis_frames` (stessa forma di quelle del calcio, `minute` sempre NULL). Sicurezza come i blocchi del 24/09:
  RLS accesa, REVOKE ad anon/authenticated/PUBLIC su tabelle e sequenze, service_role esplicito, RPC SECURITY DEFINER con
  `search_path` fisso e guardia owner `tennis_is_owner()`, EXECUTE solo ad authenticated/service_role; guardia `postgres` e
  prerequisito `tennis_bots.sql` in testa; query di verifica in coda. Differenza voluta dal calcio: nel bucket vince
  l'ULTIMO frame (chiusura/sospensione a fine bucket non sparisce).
- **Convertitore puro** `Betfair/stream/tennis_replay/convertitore.py`: raw (+ sidecar) -> righe. Piu' file della STESSA
  partita (es. cartella MATCH_ODDS e cartella SET_BETTING delle campagne `record_multi`) si fondono in UNA partita.
  Eventi di gioco derivati (`eventi_tennis`): BREAK (game vinto da chi riceveva, mai nel tie-break), SET_END, SET_START,
  TIEBREAK_START, MATCH_END, SALTO (piu' di un game fra due righe = buco: nessun break inventato). Raw senza libri =
  rifiutato (mai un evento vuoto nel DB).
- **Caricamento idempotente** `caricamento.py`: per (evento, mercato) delete+insert (un import col SET_BETTING non cancella
  il MATCH_ODDS di prima), punteggio sostituito solo se portato, conteggi ricalcolati dai mercati nel DB, lock per evento.
  Riusa `db.delete_event_rows` (nuovo argomento facoltativo `market_id`) e `db.insert_rows_resilient`.
- **Import a mano** `python -m Betfair.stream.tennis_replay.importa <cartella> [...] [--evento ID] [--nomi f.json] [--prova]`:
  visita in profondita', unisce la stessa partita da piu' cartelle, nomi da `--nomi` / `_names.json` / `tennis_markets`
  (sola lettura) / IPS; `--prova` = nessun accesso al DB. Provato in `--prova` sulla registrazione vera.
- **Caricamento a fine partita DENTRO il runner tennis** (nessun processo nuovo): in `tennis_recorder.TennisRawTee`, quando
  la marketDefinition del MATCH_ODDS di un evento REGISTRATO diventa CLOSED, un `threading.Timer` (thread daemon dello
  stesso processo) dopo `TENNIS_REPLAY_CARICA_DOPO_S` (60 s) converte e carica; `TENNIS_REPLAY_CARICA=0` lo spegne; errore =
  warning con il comando a mano. `sync_record_flags` passa al tee il catalogo del runner (nomi, torneo).

### 1.2 Pagina «Replay Tennis» (blocchi 2 e 3)
Rotta `/tennis/replay` (entrambi gli alberi di `App.tsx`), voce «Replay tennis» nella sezione Tennis della sidebar del guscio
(accanto a Dashboard tennis / Tennis Terminal) e bottone «Replay» nella `TennisNav` (grafica attuale, guscio spento).
File: `pages/TennisReplay.tsx`, `lib/tennisReplay.ts`, `components/tennis-replay/{TennisReplayList,TennisTimelineSymbols}.tsx` (`TennisApplicaBot.tsx` rimosso in FASE 2, §13).
Design system: stessa struttura e classi del Match Replay e delle pagine tennis (`glass-card`, `ds-v2-*`, `font-display`,
token `primary/secondary`, componenti `ui/*`), tabellone = quello del Tennis Terminal. Le guardie della veste
(`cssGuscio`: sticky marcati, `uiDefault`, `cssVeste`) sono verdi; la fotografia comprende ora anche la pagina nuova.

### 1.3 Cose che il raw NON contiene (dichiarate, mai inventate)
- **Nomi dei runner**: lo stream porta solo `id` e `sortPriority`. Ordine: catalogo del runner (auto) / `--nomi` /
  `_names.json` / `tennis_markets` -> `name` della marketDefinition (file storici) -> per il MATCH_ODDS i nomi IPS per
  sortPriority (p1 = home = sortPriority 1, convenzione di `TennisMatchStats`) -> `#id`. Gli altri mercati senza catalogo
  restano `#id` (Set Betting: i nomi «2 - 0»... vanno dati).
- **Torneo**: solo da DB (`tennis_live_follow`/`tennis_markets`) o dal catalogo del runner.
- **Orologio del punteggio**: le righe IPS hanno l'ora del POLL locale, i book il publish time Betfair (stessa
  approssimazione dichiarata dal banco, `replay_bot.py` «dichiarazione 2»).
- **Valuta**: GBP storiche (nessun marcatore), `tennis_replay_eventi.valuta='GBP'`; il frontend converte alla fonte con
  `CAMBIO_RIPIEGO_GBP_EUR` (stessa regola del calcio).

---

## 2. TABELLA: Match Replay calcio x Replay Tennis (nessuna riga omessa)

| # | funzionalita' del Match Replay | Replay Tennis | come / causa |
|---|---|---|---|
| 1 | elenco partite registrate (RPC propria) | presente | `list_replays_tennis` |
| 2 | raggruppamento per lega -> anno con logo lega | adattata | per torneo -> anno; nessun logo (i tornei non hanno id API-Football: icona trofeo) |
| 3 | stato vuoto «nessun replay» | adattata | dice anche come caricare (importa / automatico) |
| 4 | caricamento a finestre con barra di progresso | presente | `fetchFramesAFinestre` di live.ts (estratta, stessa logica) su `get_replay_tennis_frames` |
| 5 | ripiego su `get_replay` se la migrazione chunked manca | non applicabile | nessuna RPC tennis «vecchia»: messaggio esplicito «applicare replay_tennis_2026-10-07.sql» |
| 6 | conversione size GBP->EUR alla fonte | presente | stessa funzione `convertiFramesEur` |
| 7 | badge Overall Position | presente | P&L realizzato + mercati aperti |
| 8 | End Simulation (reset completo) | presente | |
| 9 | testata partita col punteggio all'istante | adattata | set vinti, riepilogo set, game, punti, tie-break, stato PRE-MATCH/IN GIOCO/SOSPESO/FINE, ora |
| 10 | PlaybackControls (inizio, riavvolgi, passo, play/pausa, avanti, avanti veloce, fine) | presente | componente importato |
| 11 | velocita' x1..x5 | presente | |
| 12 | barra con riempimento e trascinamento | presente | `TimelineSlider` importata |
| 13 | segmenti rossi delle sospensioni | presente | dai frame del MATCH_ODDS (`sospesoPerPasso`) |
| 14 | simboli eventi (gol, cartellini, angoli) con legenda | adattata | inizio set, break, tie-break, fine set, fine partita, buco di registrazione, passaggio in gioco, con legenda (`TennisTimelineSymbols` sopra la barra: `TimelineSlider` e' VIETATA, patch §8) |
| 15 | marker del calcio d'inizio sulla barra | adattata | simbolo «passaggio in gioco» (il marker della barra ha il titolo «Calcio d'inizio»: non usato) |
| 16 | cursore col minuto / PRE | adattata | minuti dall'inizio del gioco registrato, PRE prima; didascalia sotto la barra |
| 17 | cursore iniziale al calcio d'inizio | presente | al passaggio in gioco (flag di mercato) |
| 18 | rombi degli arbitraggi eseguibili | presente | stesso gate `arbExecutableUnderDelay`; sul tennis i rilevatori arb (calcio) non girano -> nessun rombo atteso |
| 19 | menu dei mercati per categoria con conteggio | adattata | Match Odds, Set Betting, Vincente set, Game totali, Handicap, Tie-break, Altri |
| 20 | pannelli mercato (win%, back/lay cliccabili, stake, position, cash out, SOSPESO/CHIUSO) | presente | `MarketPanel` importato, N selezioni |
| 21 | ordini simulati dal motore di matching (taker/maker, coda, LAPSE) | presente | `simulateOrder` |
| 22 | bet-delay in gioco | adattata | betDelay REGISTRATO del mercato (3 s sul MO tennis) invece dei 5/6 s fissi |
| 23 | minimo di stake Betfair | presente | |
| 24 | annulla ordine (resto) / elimina | presente | `TradesPanel` |
| 25 | cash out che blocca il P&L, rifiutato a mercato sospeso non regolato | presente | |
| 26 | esito definitivo dei mercati | adattata | REGOLAMENTO Betfair registrato (runner WINNER a mercato CLOSED) per ogni mercato tennis, non regole di punteggio |
| 27 | pannello dei trade | presente | |
| 28 | nota P&L | adattata | testo con l'esito dal regolamento |
| 29 | Opportunita' (3 fasce) | adattata | girano i rilevatori di microstruttura (flusso, peso del denaro, scalp sullo spread); tier 0 arbitraggi e tier 1 (pareggio, doppia chance, correct score, BTTS, over/under, gol) NON applicabili: la ragione e' scritta a schermo; fasi «Set N» al posto dei tempi; delay del mercato |
| 30 | Validazione su dati reali | presente | stesso report, si mostra se ci sono opportunita' |
| 31 | Ladder TRAINING (LadderView vero, selettore di TUTTI i mercati, Azzera ordini) | presente | `sport="tennis"`, delay del mercato |
| 32 | trade del training con la X | presente | `TrainingTradesPanel` |
| 33 | Applica bot (scelta, Applica, stato, note, ordini del bot sul ladder, BotOrdersPanel) | SI (FASE 2) | `ApplicaBotPanel sport="tennis"` (soli 5 bot tennis), `useApplicaBot`, `EsitoBotPanel`, ordini del bot sul ladder del training (§13) |
| 34 | Backtest del ladder | presente | `LadderBacktestPanel` con delay del mercato |
| 35 | barra di navigazione (Segui Live / Dashboard) | adattata | `TennisNav` della sezione tennis |
| 36 | titolo pagina, footer, card d'errore, scheletri di caricamento | presente | |
| 37 | (in piu') tabellone tennis completo: servizio, set per set, pressione, probabilita' di vittoria, break, punto per punto | presente | `TennisMatchStatsView` estratto da `TennisMatchStats` (stesso DOM), dati all'istante del cursore |

---

## 3. File toccati e nuovi

Nuovi: `Betfair/stream/tennis_replay/{__init__,convertitore,caricamento,importa}.py`,
`Betfair/stream/tennis_replay/tests/{__init__,dati_tennis,test_convertitore_2026_10_07,test_caricamento_importa_2026_10_07,test_fine_partita_runner_2026_10_07}.py`,
`migrations/replay_tennis_2026-10-07.sql`, `frontend/src/pages/TennisReplay.tsx`, `frontend/src/pages/TennisReplay.test.tsx`,
`frontend/src/lib/tennisReplay.ts`, `frontend/src/lib/tennisReplay.test.ts`, `frontend/src/lib/delayMercato.tennisReplay.test.ts`,
`frontend/src/lib/__fixtures__/replay_tennis_35790089.json` (99 KB, uscita del convertitore sulla registrazione vera),
`frontend/src/components/tennis-replay/{TennisReplayList,TennisTimelineSymbols}.tsx`, `frontend/src/lib/tennisReplayVerificaBarra{,.test}.ts` (FASE 2),
`frontend/src/fotografia/snapshot/tennis-replay.{off,off.guscio,v2,v2.guscio}.json`,
`AUDIT_2026-10-07/replay_tennis/{verifica_migrazione_pg,verifica_migrazione_falsifica,falsifica_python,falsifica_frontend,genera_fixture_frontend}.py`, questo referto.

Toccati (motivo; tutte modifiche compatibili, comportamento di prima invariato senza i parametri nuovi):
- `Betfair/stream/curator.py`: estratta `curate_records` da `curate_event` (stessa regola) + argomento `stato_nel_cambio`
  (default False: il calcio non cambia; il tennis lo usa, vedi §6 reperto).
- `Betfair/stream/db.py`: `delete_event_rows(..., market_id=None)`.
- `Betfair/stream/tennis_live/tennis_recorder.py`: aggancio a fine partita (perimetro concesso), `enable(..., meta=None)`.
- `Betfair/stream/tests/test_valuta_k1_2026_09_26.py`: il convertitore registrato fra le fonti esenti (decodifica
  registrazioni GBP per il replay, converte il frontend) — il contratto lo chiede esplicitamente.
- `frontend/src/lib/live.ts`: estratta `fetchFramesAFinestre` (RPC dei frame parametro); `fetchReplayChunked` invariata.
- `frontend/src/lib/trainingLadder.ts` (`delayMsAt?`), `lib/ladderBacktest.ts` (`delayMs` = 5000 di default),
  `components/replay/LadderBacktestPanel.tsx` (`delayMsAt?`; testo d'intestazione ora una sola stringa, stesso testo).
- `frontend/src/components/tennis/TennisMatchStats.tsx`: estratto `TennisMatchStatsView` (stesso DOM dal vivo) + `freschezza`.
- `frontend/src/components/tennis/TennisNav.tsx`: bottone «Replay» (navigazione).
- `frontend/src/App.tsx` (rotte), `components/shell/navigazione.ts` (voce + rotta nel guscio).
- Test esistenti aggiornati per la voce/rotta nuova (DECISIONE dichiarata, solo conteggi/elenchi): `AppShell.test.tsx`
  (23->24 voci, 21->22 rotte, 24->25 `data-nav-legacy`), `fotografia.test.tsx` (pagina nuova + testid in lista bianca).
- Fotografie rigenerate (`FOTOGRAFIA_AGGIORNA=1`), diff riletto: 27 file, **177 righe aggiunte, 0 tolte**; solo la voce
  «Replay tennis» nelle `*.v2.guscio.json` e il bottone «Replay» della TennisNav nelle 3 pagine tennis (`tennis`,
  `tennis-terminal`, `tennis-terminal-match`, off e v2). Match Replay: solo la voce di sidebar del guscio.

NON toccati (vietati): `MatchReplay.tsx`, `replayBot.ts`, `BotOrdersPanel.tsx`, `replayTimelineEvents.ts`, `TimelineSlider.tsx`,
`Betfair/stream/backtest/**`, `Betfair/stream/scalper/**`, `tools/replay_*`.

---

## 4. Test (comandi, numeri)

Python (`python3 -m pytest <file> -q -p no:cacheprovider`):
- `Betfair/stream/tennis_replay` + `tennis_live/tests` + `test_curator`, `test_db_delete_event_rows`, `test_db_insert_resilient`,
  `test_uploader_sweep_2026_07_17`, `test_record_optin_2026_07_17`: **824 passati, 4 saltati, 5 xfailed, 50 s**.
- `Betfair/stream/tests -k "curator or uploader or db_ or record or replay or tennis or recorder"`: 535 passati, 8 saltati
  (prima del ritocco al contratto valuta); contratti che visitano l'albero (`test_valuta_k1`, `test_submin_contratto_chiamanti`,
  `test_contratto_strada_unica`, `test_banco_identita`, `test_motore_ordini`, `test_banco_ambiente_dichiarato`, `test_banco_comune`,
  `test_uscite_proposte_bot_tennis`): verdi dopo la registrazione del convertitore (il contratto valuta era ROSSO: trovato
  e sistemato, §3).
- Convertitore sulla registrazione VERA 35790089: 5217/5217 libri identici a flumine e all'oracolo dello schema; 3355
  snapshot curati; 104 righe di punteggio identiche al sidecar (set, game, punti, servizio, game_sequence); eventi verificati
  a mano sul sidecar (break che chiude il 2o set 7-5; break 2-4, 3-4, 3-5, 4-5 nel 3o; tie-break sul 6-6; fine 6-4 5-7 6-7);
  5 buchi di registrazione (soglia 60 s), quelli dichiarati.
- Migrazione su PostgreSQL 16 USA-E-GETTA (cluster temporaneo in /tmp avviato e fermato dallo script, ruoli e `auth.jwt()`
  di Supabase simulati): `python3 AUDIT_2026-10-07/replay_tennis/verifica_migrazione_pg.py` -> **27/27 OK** (applicata due
  volte, solo oggetti tennis, righe vere inserite, list/meta/frames da owner, frame per bucket 1/2/10 s = ultimo del bucket
  calcolato in Python, non owner rifiutato, anon senza EXECUTE, nessuna SELECT diretta, RLS accesa, CASCADE).

Frontend (dalla cartella `frontend/`):
- `npx tsc -p tsconfig.app.json --noEmit`: **0 errori** (prima e dopo).
- Nuovi: `tennisReplay.test.ts` 21, `delayMercato.tennisReplay.test.ts` 3, `TennisReplay.test.tsx` 7 (pagina con la
  fixture vera: elenco con sole RPC tennis, punteggio al cursore, fine partita, simboli in ordine, nota opportunita',
  Applica bot coi soli bot tennis, backtest a 3 s, tabellone senza «agg. Xs fa»).
- Esistenti rilanciati: `live.valutaReplay`, `trainingLadder`, `trainingLadder.replay`, `ladderBacktest`, `components/replay`,
  `TennisTerminal.test`, `components/shell`, `tennisRegistry`, `replayBot`, `replayTimelineEvents`, `matching`,
  `components/tennis`, `src/fotografia` (4 file, 41 test, 27 pagine), `src/test`, `components/controlroom` insieme ai nuovi:
  **102 file, 1329 test verdi, 0 rossi** (5 min 38 s).

### Falsificazioni (tutte ROSSE)
- Python `falsifica_python.py`: **18/18** (profondita' del libro, fotografia prima della riga, break/tenuta scambiati, SALTO
  tolto, break nel tie-break, chiusura persa dalla curazione, regolamento alla sospensione, doppioni fra file, nomi IPS,
  raw vuoto accettato, delete di tutto l'evento, punteggio cancellato, filtro mercato ignorato, fine partita su qualunque
  mercato, caricamento riprogrammato, interruttore ignorato, catalogo non passato al tee, curatore che ignora lo stato).
  Due erano verdi al primo giro (doppioni, caricamento ripetuto): test rafforzati, poi rosse.
- SQL `verifica_migrazione_falsifica.py`: **6/6** (guardia owner, primo frame del bucket, EXECUTE a PUBLIC, RLS spenta,
  SELECT ad authenticated, niente CASCADE).
- Frontend `falsifica_frontend.py`: **15/15** (esito prima della chiusura, categoria handicap, etichetta break, RPC del calcio
  per i frame e per la lista, delay del mercato ignorato in lib/training/backtest/pannello, punti oltre il cursore,
  sospensione/chiusura, EUR non convertiti, freschezza del live nel replay, bot del calcio nel tennis, passaggio in gioco).
Ogni script ripristina i file byte per byte (sha256 verificato).

---

## 5. Parita' paper/live
Nessun bot, nessun ordine vero, nessuna strategia toccati. Il replay e' una simulazione didattica (come il Match Replay).
Il caricamento automatico gira nel runner tennis sia in paper sia in live in modo identico (dipende solo dalla registrazione
opt-in `record=true`), non tocca ordini ne' stream (best-effort, mai un'eccezione verso il tee).

## 6. Cosa NON ho fatto / NON ho potuto verificare
- **Applica bot FASE 2** (collegamento al banco comune con parametri, scenari, «accendi al cursore», ordini del bot sul
  ladder, `BotOrdersPanel`): aspetta l'integrazione dell'altro delegato.
- **DB vero**: migrazione mai applicata; RPC provate su PostgreSQL usa-e-getta con Supabase simulato, non su PostgREST; il
  caricamento provato con un client Supabase finto (stessa catena di chiamate), non su Supabase.
- **Schermo**: pagina mai vista a occhio (niente app nel cloud); provata dai test della pagina e dalla fotografia.
- **Piu' mercati su dati VERI**: la registrazione vera ha solo il MATCH_ODDS; SET_BETTING/TOTAL_GAMES provati su una partita
  COSTRUITA nel formato vero dello stream (chiavi e tipi presi dalla riga di immagine vera). Una registrazione multi-mercato
  vera (es. `Desktop/tennis_rec/setbetting_20260707`) va importata sul PC dell'utente.
- (SUPERATO il 07/10 sera, §10) ~~Il runner tennis sottoscrive SOLO il MATCH_ODDS~~: ora le partite con REC acceso
  portano tutti i mercati dell'evento.
- Caricamento automatico: se il runner si riavvia nei 60 s dopo la chiusura, il timer si perde -> import a mano.
- (CORRETTO il 07/10 sera, §11) ~~Reperto CALCIO del curatore~~: regola unica per calcio e tennis.

## 7. Decisioni per l'utente
DECISE dall'utente il 07/10 (testuale «1) SI 2) si 3) correggi»): 1 fatta (§10), 2 confermata (acceso di serie), 3 fatta (§11).

1. **Tutti i mercati nelle registrazioni AUTOMATICHE**: oggi il runner tennis registra solo il Match Odds. Proposta: per le
   sole partite con «registra» acceso, aggiungere alla sottoscrizione gli altri mercati dell'evento (piu' dati sullo stream
   del runner; i bot sono gia' limitati al loro mercato da `_scope_to_market`). Fino ad allora: campagne `record_multi` e import.
2. Caricamento automatico a fine partita ACCESO di default (`TENNIS_REPLAY_CARICA=0` per spegnerlo): confermare.
3. Correzione del reperto del curatore anche per il calcio (§6): si/no.

## 8. Patch di TimelineSlider (APPLICATA in FASE 2, vedi §13; testo originale qui sotto)
`components/replay/TimelineSlider.tsx` parametrica per lo sport (cosi' i simboli del tennis starebbero DENTRO la barra e il
titolo del marker non direbbe «Calcio d'inizio»):
```diff
 export interface TimelineSliderProps {
@@
     kickoffPct?: number;   // 0..1 — posizione del calcio d'inizio sulla track (marker)
+    /** icona di un evento per kind (default: quelle del calcio) */
+    iconaEvento?: (kind: string) => React.ReactNode;
+    /** legenda degli eventi (default: quella del calcio) */
+    legenda?: React.ReactNode;
+    /** titolo del marker d'inizio (default «Calcio d'inizio») */
+    titoloInizio?: string;
 }
-export function TimelineSlider({ min, max, value, minute, onChange, suspended, events, arbMarkers, pre, kickoffPct }: TimelineSliderProps) {
+export function TimelineSlider({ min, max, value, minute, onChange, suspended, events, arbMarkers, pre, kickoffPct,
+    iconaEvento, legenda, titoloInizio = "Calcio d'inizio" }: TimelineSliderProps) {
@@
-                        <EventIcon kind={ev.kind} />
+                        {iconaEvento ? iconaEvento(ev.kind) : <EventIcon kind={ev.kind} />}
@@
-                        title="Calcio d'inizio"
+                        title={titoloInizio}
@@
-            {(hasLegend || hasArb) && (
+            {legenda ?? ((hasLegend || hasArb) && (
                 ...
-            )}
+            ))}
```
`MatchReplay.tsx`: potrebbe riusare `fetchFramesAFinestre` (gia' fatto indirettamente da `fetchReplayChunked`), e in
futuro `ultimoAl`/`costruisciTimeline`/`indiceDiPasso` di `lib/tennisReplay.ts` spostate in una lib generica: nessun
cambio fatto (file vietato).

## 9. Da controllare dal vivo (al prossimo avvio)
1. Applicare `migrations/replay_tennis_2026-10-07.sql` (SQL Editor, postgres) e la verifica in coda: tutte 'OK'.
2. `python -m Betfair.stream.tennis_replay.importa C:/Users/Admin/Desktop/tennis_rec --prova` (nessun DB), poi senza
   `--prova`: atteso un riepilogo per partita (mercati, snapshot, punteggi), rilanciandolo stesse cifre.
3. App -> Tennis -> «Replay tennis» (`/tennis/replay`): elenco per torneo, apertura di una partita, punteggio che segue il
   cursore, simboli sulla barra, ladder training sul Match Odds, backtest «bet-delay reale (3s)».
4. Una partita con «registra» acceso: a fine partita nel log del runner tennis «partita X finita: caricamento nel Replay
   Tennis tra 60 s» e poi «[replay-tennis] X caricato»; la partita compare nell'elenco.

## 10. (07/10 sera) REC su TUTTI i mercati dell'evento — decisione dell'utente «1) SI»

### 10.1 Come sottoscrive oggi il runner tennis (letto riga per riga)
- UNA MarketStream per tutto il runner (`tennis_runner.setup_and_run`): la capture condivisa `_make_capture` ha
  `streaming_market_filter(market_ids=<Match Odds di TUTTE le partite seguite>)`, `TennisRecMarketStream` (tee del raw) e il
  `data_filter` unico (`STREAM_FIELDS`, `LADDER_DEPTH`); nessuna conflation impostata. flumine riusa una MarketStream SOLO
  a filtro identico: per questo capture, capture degli ordini live e bot ricevono LO STESSO elenco (`all_market_ids`), e
  la build verifica `bot.stream_ids == cap.stream_ids`.
- Il catalogo (`_resolve_market`, `listMarketCatalogue`) legge SOLO il MATCH_ODDS (`market_type_codes=["MATCH_ODDS"]`):
  `session.market_meta[event] = {market_id, name_to_sel, selection_names, competition_name}`.
- Le partite entrano/escono a framework vivo con la RISOTTOSCRIZIONE A CALDO sulla stessa connessione
  (`iscrizione_a_caldo` + `sottoscrizione_a_caldo.sottoscrivi`: nuovo `marketSubscription`, filtro canonico scritto su
  stream e strategie). Tetto `TENNIS_TETTO_MERCATI` (default 180) sotto il limite Betfair di 200 mercati per connessione.
- I bot sono limitati al LORO mercato (`_scope_to_market`: `check_market_book` falso per ogni altro mercato); ladder, now e
  ordini leggono solo il proprio mercato (`capture.latest_for`).
- Il REC per partita (`tennis_live_follow.record`) e' riletto ogni `RECORD_POLL_SEC` dal `record_flag_worker` ->
  `sync_record_flags` -> tee; il tee scrive i messaggi dei mercati dell'evento (instradamento anche dal `marketDefinition.eventId`).

### 10.2 Quali mercati Betfair offre per il tennis
Non c'e' una lista fissa: i tipi si scoprono con `listMarketTypes`/`listMarketCatalogue` (Betting API, «Betting Type
Definitions» sul portale sviluppatori; la pagina e' bloccata dal proxy del cloud, letta solo la scheda del motore di
ricerca). Nel repo compaiono MATCH_ODDS, SET_BETTING (campagne `record_multi`), SET_WINNER, GAME_HANDICAP (`anteprima/tennisDati.ts`).
Per questo NON si filtra per tipo: si prende TUTTO cio' che il catalogo dell'evento restituisce (max 200 righe).

### 10.3 Cosa ho fatto (STESSA connessione, STESSA sottoscrizione)
- `tennis_live/mercati_registrati.py` (nuovo): `catalogo_mercati_evento` (REST `listMarketCatalogue` per evento, proiezioni
  RUNNER_DESCRIPTION + MARKET_DESCRIPTION, senza il Match Odds) e `mercati_da_sottoscrivere` = l'elenco CANONICO unico:
  sempre TUTTI i Match Odds, poi i mercati delle partite registrate finche' c'e' posto sotto il tetto (i Match Odds non
  escono MAI per i registrati; l'eccesso resta fuori con un warning).
- `tennis_runner.py` (le sole righe della sottoscrizione): build (`_mercati_registrati_alla_build` + `all_market_ids =
  _MR.mercati_da_sottoscrivere(...)`), armamento a caldo (stesso elenco), iscrizione a caldo (le partite nuove con REC portano
  i loro mercati; elenco canonico in `_applica`), `record_flag_worker` -> `_allinea_mercati_registrati` (REC acceso/spento a
  partita in corso: catalogo FUORI dal ciclo di flumine, risottoscrizione DENTRO, sessione aggiornata solo se riuscita;
  catalogo KO = nulla cambia, riprova dopo 60 s; stream non connesso = nulla cambia). Stato di sessione `mercati_rec_ko`.
- `tennis_recorder.py`: il tee instrada anche i mercati in piu' e il caricamento a fine partita usa il loro catalogo (nomi
  dei mercati, es. «Set 1 Winner», e dei runner). Convertitore: `nomi_mercato`. Import a mano: nomi di tutti i mercati da
  `tennis_markets.full_odds` (sola lettura).
- Il registratore scrive tutti i mercati nello stesso `<id>.raw.jsonl`; convertitore e import li portano gia' (provato:
  test `test_tutti_i_mercati_della_partita_registrata_coi_nomi_del_catalogo` e la partita costruita a 3 mercati).

### 10.4 Vincoli del coordinatore: come sono rispettati e cosa NON e' zero
- Nessuna sottoscrizione ne' connessione in piu' (test: un solo MarketStream, stesso `stream_id` per tutte le strategie,
  filtro dei bot == filtro dello stream).
- Nessun mercato tolto ai bot: il loro Match Odds e' sempre nell'elenco (test anche col tetto); posizioni e blotter intatti
  durante l'accensione e lo spegnimento del REC (test con un bot in posizione).
- NON e' zero, lo dichiaro: (a) accendere o spegnere il REC a partita in corso fa una RISOTTOSCRIZIONE (la stessa che oggi
  avviene a ogni partita nuova seguita): Betfair rimanda l'immagine piena di tutti i mercati, i bot ricevono il loro libro
  dalla sottoscrizione nuova; (b) i messaggi dei mercati in piu' passano dallo stesso ciclo di flumine dei bot (mercati
  sottili, ma il lavoro per messaggio esiste: scope del bot, serializzazione della capture, conversione valuta). Evitare
  (b) del tutto richiede una connessione separata: VIETATO dal brief, NON fatto. Va misurato dal vivo (§10.6).

### 10.5 Test e falsificazioni
`tennis_live/tests/test_rec_tutti_i_mercati_2026_10_07.py` (10 test, banco VERO dell'iscrizione a caldo: `Flumine`,
capture e bot veri, `BetfairStream` col socket finto, catalogo con `MarketCatalogue` di betfairlightweight dalle chiavi
vere): REC acceso con bot in posizione, REC spento, nessun cambio = nessuna risottoscrizione, libro di un mercato registrato
che non arriva alla logica del bot ma finisce nel file, tetto, catalogo KO con riprova, stream non connesso, partita nuova
registrata a caldo, build, contratto della build. Falsificazioni R1-R11: tutte ROSSE (`falsifica_python.py`, 31/31 totali).
Suite `tennis_live/tests` intera verde (vedi §12).

**Contratto dell'impronta del banco ROSSO (4 test):** `test_registro_impronta_2026_09_30` chiede che ogni modulo del
pacchetto raggiunto dal runner stia in `registro_bot._MODULI_TENNIS` (file VIETATO, `Betfair/stream/backtest/`). Patch di
una riga pronta: `AUDIT_2026-10-07/patch/registro_bot_mercati_registrati.diff` (`git apply --check` OK; verificata su una
copia del pacchetto: 35/35 verdi). Da applicare all'integrazione. NB: `tennis_runner.py` e' cambiato, quindi l'impronta dei
4 bot tennis cambia: i referti del banco vanno rifatti (le righe toccate non entrano in `_instantiate_bot` ne' nei bot).

### 10.6 Da controllare dal vivo alla prossima partita registrata
1. Log del runner tennis all'accensione del REC: `[tennis-rec] <ev>: N mercati in piu' da registrare` e
   `mercati registrati sulla stessa connessione: accesi [...] (M mercati nello stream)`; nessun `STREAM DUPLICATO`.
2. `<ev>.raw.jsonl`: righe con `marketType` diversi da MATCH_ODDS (SET_BETTING, ...); stesso file.
3. I bot della partita: nessuna interruzione oltre l'immagine della risottoscrizione; latenza del ladder e dei bot uguale a
   prima (confronto con una partita senza REC; `tennis_live_ladder.updated_at`, battito dello stream).
4. Spegnendo il REC: `spenti [...]`, solo i Match Odds nello stream.
5. A fine partita: Replay Tennis con tutti i mercati e i loro nomi del catalogo.

## 11. (07/10 sera) Curatore del CALCIO corretto — decisione dell'utente «3) correggi»
- **Causa** (`Betfair/stream/curator.py`, regola di conservazione): una riga entrava solo se cambiavano i best
  back/lay/ltp o passava la cadenza; la CHIUSURA di un mercato gia' vuoto da sospeso (best invariati) entro 10 s spariva.
  Misura sul calcio vero (ricostruzione del file curato dal raw `_live_raw`, stessa catena del recorder): **35760084: 17
  mercati su 21 finivano SOSPESI invece che CHIUSI; 35797769: 17 su 22**.
- **Correzione** (regola UNICA per calcio e tennis, `curate_records`; tolto l'argomento `stato_nel_cambio`): un cambio di
  `status` o `inplay` rispetto all'ultima riga conservata entra sempre come riga IN PIU', senza toccare firma dei best e
  orologio della cadenza: per costruzione nessuna riga di prima sparisce.
- **TDD**: `Betfair/stream/tests/test_curatore_stato_2026_10_07.py` (4 test; caso vero `dati/curatore_chiusura_35760084.jsonl`
  = ultimi 9 libri del mercato 1.259475526, CLOSED 0,99 s dopo l'ultimo sospeso): ROSSI prima (4/4), VERDI dopo.
  Falsificazioni M18-M20 ROSSE.
- **Prova prima/dopo** (`AUDIT_2026-10-07/replay_tennis/curatore_calcio_prima_dopo.py`, uscita in
  `curatore_calcio_prima_dopo.out.txt`; regola vecchia ricopiata identica):
  - 35797769: 197.229 libri, righe 91.650 -> 91.687, **sparite 0**, in piu' 37, **tutte cambi di stato** (OPEN->SUSPENDED 19,
    SUSPENDED->CLOSED 17, pre->in gioco 1); 20 mercati su 22 con righe in piu'.
  - 35760084: 65.445 libri, righe 34.441 -> 34.674, **sparite 0**, in piu' 233, **tutte cambi di stato** (OPEN->SUSPENDED 125,
    SUSPENDED->OPEN 91, SUSPENDED->CLOSED 17); 21 mercati su 21 con righe in piu'.
  Conteggi per mercato nel file di uscita.
- Effetto: solo i replay caricati DOPO questa modifica (l'uploader ricura dal file a ogni caricamento; i replay gia' nel
  DB restano come sono finche' non si ricaricano). Nessun bot legge il curatore.

## 12. Test rilanciati dopo le sezioni 10-11
- `python3 -m pytest Betfair/stream/tennis_live/tests Betfair/stream/tennis_replay Betfair/stream/tennis_scalper/tests Betfair/stream/tests -k "not velocita_feed"`:
  **4829 passati, 4 falliti, 44 saltati, 5 xfailed, 282 s**. I 4 falliti sono SOLO il contratto dell'impronta
  (`test_registro_impronta_2026_09_30`, uno per bot tennis: modulo nuovo `mercati_registrati` non in `registro_bot`, file
  vietato): patch `AUDIT_2026-10-07/patch/registro_bot_mercati_registrati.diff`, con la patch 35/35 verdi su una copia.
- Falsificazioni Python: **31/31 ROSSE** (M1-M20, R1-R11), file ripristinati (sha256).
- PostgreSQL usa-e-getta: **27/27 OK** dopo la regola unica del curatore (snapshot tennis 3355, invariati).
- Frontend (fixture rigenerata, stesso contenuto): `tennisReplay.test.ts` + `TennisReplay.test.tsx` 28/28 verdi; nessun
  file frontend toccato dalle sezioni 10-11.
- Confronto curatore calcio prima/dopo: §11 (0 righe sparite, solo cambi di stato in piu').

## 13. FASE 2 (07/10 sera): Applica bot tennis, verificatore della barra, barra parametrica
Base: merge di `integrazione-0710-b` (64064f36) sul mio ramo (cc42bfb9), senza conflitti.

**Applica bot tennis** (`pages/TennisReplay.tsx`, vista Ladder TRAINING): il segnaposto `TennisApplicaBot.tsx` e' RIMOSSO;
la pagina usa i componenti comuni dell'altro delegato, come il Match Replay: `ApplicaBotPanel sport="tennis"` (solo i 5 bot
tennis del catalogo: safe_tennis, tennis_scalper, tennis_pro, tennis_flb, tennis_swing; nessun bot calcio), `useApplicaBot`
(richiesta `request_backtest` con `tipo: applica_bot`, `event_id` della partita tennis), `EsitoBotPanel` sotto il ladder e gli
ordini del bot sul ladder del training all'istante del cursore (`conOrdiniDelBot` + `ordiniBotAlMs`, solo import da
`lib/replayBot.ts`). Il backend (`applica_bot.esegui` coi bot tennis) e' dell'altro delegato: non toccato.

**Verificatore della barra tennis** (`lib/tennisReplayVerificaBarra.ts`, nuovo): `verificaBarraTennis(dati, opzioni)`.
- La barra e' costruita con le STESSE funzioni della pagina (`costruisciTimeline`, `inizioInGioco`/`indiceDiPasso`,
  `simboliTennis`, `sospesoPerPasso`) e passata a `verificaBarraGenerica` con `ambito: 'tennis'` (estremi, ordine, simboli
  fuori barra / prima del loro istante / fuori registrazione, inizio del gioco, sospensioni, buchi); il testo «calcio
  d'inizio» dei controlli generici diventa «inizio del gioco».
- Controlli di dominio con oracoli indipendenti dal convertitore: evento di gioco senza simbolo e simbolo senza evento
  (errore), passaggio in gioco (errore), set che scendono, fine set, tie-break e break incoerenti col tabellone e col
  servizio della riga precedente (avviso), salti di piu' game e punteggio assente (nota).
- `CodiceRilievo` (`lib/replayVerificaBarra.ts`): aggiunti SOLO 8 codici `TENNIS_*` all'unione, nient'altro cambia.
- Collegato alla pagina: `<AvvisoCoerenzaBarra replay={perMotore} verifica={verificaTennis} />` sopra i controlli.
- Test `lib/tennisReplayVerificaBarra.test.ts` (17): SCOPRE DA SOLO le fixture `__fixtures__/replay_tennis_*.json` e le
  registrazioni `_live_raw_tennis/<giorno>/<evento>/` risalendo dal frontend (fuori da git: se mancano il controllo e'
  saltato col motivo; qui trovata 35790089, con fixture); 0 incoerenze sulla 35790089; F1-F8 difetti rimessi -> rosso;
  regole su una partita costruita (break, tie-break, salto, punteggio assente).

**TimelineSlider** (patch §8 applicata, file liberato dal coordinatore): props opzionali `iconaEvento`, `legenda`,
`titoloInizio` (default «Calcio d'inizio»); senza props il rendering e' identico (Match Replay invariato, fotografie
invariate: 0 righe cambiate). 2 test nuovi in `TimelineSlider.test.tsx` (default del calcio identico; parametri dello
sport). La pagina tennis ora disegna i simboli DENTRO la barra (`markerTennis`, `iconaTennis`, `LegendaTennis` in
`components/tennis-replay/TennisTimelineSymbols.tsx`; la legenda tiene anche la voce «Arbitraggio» dei rombi verdi), con
la lineetta «Passaggio in gioco» quando la registrazione parte prima del gioco.

**Verifiche (rieseguite)**: tsc 0 errori; vitest per blocchi (l'intera suite in un colpo supera i 10 minuti del comando):
src/lib 151 file / 2635 test; src/components + App 168 / 2130; src/fotografia + shell + pages 28 / 469 (+1 saltato);
anteprima/certification/hooks/test/integrations 2 / 8 (+49 saltati, come prima): tutto verde. Fotografie: nessun file
cambiato. `falsifica_frontend.py`: **20/20 mutazioni rosse** (F12 riscritta sul pannello comune; F16-F20 nuove:
verificatore break, simbolo perso, avviso iniettato visibile nella pagina, titolo d'inizio fisso al calcio, simboli fuori
dalla barra), file ripristinati con sha256.

**NON fatto in FASE 2 (dichiarato)**:
- Banco dei bot tennis sulla 35790089 contro `coord/tennis_base_<bot>.txt`: NON rieseguito per la scadenza (nessun file
  del banco o dei bot e' stato toccato in FASE 2: il diff della FASE 2 e' solo frontend + referto).
- `npm run build` non lanciato (lo fa l'integrazione sul checkout principale).
- L'esito completo dell'Applica bot nella pagina tennis (EsitoBotPanel con un esito DONE vero) e' provato solo dai test
  del componente comune; il test della pagina prova catalogo, richiesta e assenza di RPC del calcio.
- Patch di `registro_bot` (§12/patch) ancora da applicare dal coordinatore: senza, 4 test dell'impronta restano rossi.

## STATO_RIPRESA
- FASE 2 fatta (§13). Resta: banco dei 5 bot tennis sulla 35790089 contro i riferimenti del coordinatore
  (`python3 -m Betfair.stream.backtest.certifica <bot> 35790089 --data-dir _live_raw_tennis/20260707 --scenari tutti
  --worker 1`, togliendo solo tempi e impronta), `npm run build` all'integrazione, patch `registro_bot` del coordinatore.
- Decisioni §7 ancora aperte per l'utente.
