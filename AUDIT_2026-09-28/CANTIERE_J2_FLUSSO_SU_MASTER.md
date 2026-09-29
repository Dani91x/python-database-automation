# CANTIERE J2 — FLUSSO DATI INTERROTTO: IL LAVORO DI J SU MASTER, E COMPLETATO (28/09/2026)

Delegato Opus 5.5, worktree `agent-ab0194ff88b5ea082`. Consegna a BLOCCHI (questo file si
aggiorna blocco per blocco). Nessuna scrittura sul DB, nessuna chiamata a Betfair, nessun
processo avviato, nessun push. Commit SOLO locali di lavoro (file elencati uno per uno, hook
non saltati) per potermi riallineare: `505d963` (blocco 1), `b2bdd28` (blocchi 2-4 in corso), merge
`47eb07f` (su `03e484d`) e `55f0522` (su `ef71543`, K2). Nessun conflitto.

## 0. Le due domande dell'utente, in parole semplici (stato di adesso)

**«Il bot sa se il flusso dati e' interrotto?»** Si'.
- Lo scanner (il feed di Safe, Mike e Omega) scrive su ogni partita se i prezzi sono VIVI, per
  mercato; un punteggio che cambia non basta piu' a far sembrare fresco un prezzo fermo.
- Con i prezzi non vivi NESSUN bot apre (Safe, Mike, Omega; paper e live uguali), nemmeno se il
  book REST di Betfair risponde.
- Una CHIUSURA, una COPERTURA o una PROTEZIONE invece prova il ripiego REST che ogni bot gia' ha
  (col suo tetto di chiamate): se Betfair risponde con il mercato aperto chiude su QUEI prezzi e
  lo scrive (`ripiego_rest`); se non risponde aspetta e scrive una riga ROSSA, al piu' una al
  minuto, con la posizione, l'esposizione in euro e da quanti secondi il flusso e' fermo.
- (Blocco 2, in consegna) scalper, sniper, theta e i bot tennis hanno il proprio stream: se tace
  oltre 15 s lo dicono (avviso rosso con la posizione non gestita, stato «flusso interrotto»).

**«Se cade lo stream c'e' il pool di backup? Funziona?»**
- Per lo SCANNER si': un mercato senza prezzi dallo stream da 20 s viene letto via REST ogni
  10-60 s; il 26/09 e' scattato e ha funzionato; tra le 10:42 e le 14:47 no, perche' era morta la
  sessione Betfair (dal 26/09 c'e' il custode che rifa' il login). Oggi, se anche il REST dello
  scanner tace, il segnale dice «fermo» e i bot si comportano come sopra.
- Per i BOT (Safe, Mike, Omega) da oggi si': le chiusure passano al loro REST.
- Per i RUNNER (ladder, regole di rischio) — blocco 3, in consegna: a stream muto le protezioni
  prendono i prezzi dal feed dello scanner (se vivo), nessuna posizione nuova.

---

## BLOCCO 1 — segnale e veto su master + REGOLA UNICA (reperto A)

### 1.1 Riporto del lavoro di J
- Ricavato file per file (differenza fra `2eb3c1d` e i file del worktree di J, in sola lettura) e
  riscritto A MANO con Edit/Write (la copia diretta dei file e' stata NEGATA dal sistema dei
  permessi). Dove master non era cambiato il risultato e' identico a J riga per riga (controllo
  `cantiere_j2/confronta.py`: «UGUALE»). Dove master era cambiato (`mike/service.py`,
  `omega_service.py`, `safe_strategy/bot_service.py`, `exits.py`, `mike.ts`) funzione per funzione
  sul codice nuovo (D1, C, K2).
- Riallineato due volte: su `03e484d` e poi su `ef71543` (K2, ciclo esterno riscritto): merge
  puliti, test e falsificazione rifatti dopo.

### 1.2 Strade coperte in piu' rispetto a J
1. Safe, ordine a mano / proposta APPROVATA (`_request_place`): veto per MERCATO dell'ordine.
2. Safe, approvazione di una COMBO (`_request_place_combo`): una gamba su un mercato fermo = nessuna.
3. Safe, cash-out rifiutato: porta `motivo = flusso_interrotto:<motivo>`.
4. Safe, giro veloce (`_novita_per_il_lento`): col mercato del trade.
5. Omega, proposta di missione (`_cs_suggestion`): blocco del feed fermo non usato.
6. Mike su D1: il veto vale PRIMA dell'invio al runner in paper e per la lay a riposo (prova sul
   `run_once` vero col runner finto).

### 1.3 REGOLA UNICA (reperto A del coordinatore) — uguale per Safe, Mike e Omega, paper e live
Col flusso dello scanner fermo:
| | Safe | Mike | Omega |
|---|---|---|---|
| APERTURA | `scan_and_place`: scartata dal veto PRIMA di ogni lettura REST (anche REST vivo) | engine `_entry_guard` (`order_fresh` falso) + `execute_place` e ramo della lay appoggiata rifiutano i ruoli d'apertura con prezzi `rest_ripiego` (`APERTURE_MIKE` = `OPENING_ROLES` meno `over_cover`) | `_scan_event_legs`: `return` dopo la riga `flusso_interrotto` (prima apriva col book REST quando c'era lo `score_lookup`) |
| CHIUSURA / PROTEZIONE | `_process_exit_one`, `_unwind_combo`, `_close_combo_siblings`: `_prezzi_ripiego_rest` = `prices_for` senza righe del feed, col tetto `rest_gate` (10 s per mercato, 8 per giro); prezzi marcati `fonte: rest_ripiego`; cash-out dell'utente: `_book_prices` come prima | `_run_event`: con una POSIZIONE aperta, `_books_ripiego_rest` (la `market.read_book` gia' usata dal regolamento; tetto 10 s per mercato) → `snapshot_from_row(books_rest=...)` rimette le linee con i prezzi REST (`fonte_prezzi = rest_ripiego`, `feed_fresh` vero, `order_fresh` falso); green-up, chiusure e copertura `over_cover` partono; cash-out dell'utente (`_request_flatten`): REST senza tetto (un clic) | green-up `_greenup_one`: prezzi da `_cashout_prices` (feed → REST) come prima, con un gol o un residuo; ora lo DICE |
| REST vivo | attivita' `ripiego_rest` (fonte `rest_ripiego`), 1/min per posizione | `ripiego_rest`, 1/min per partita; nel cash-out `ripiego_rest` con `azione` | `ripiego_rest`, 1/min per posizione |
| REST muto | `exit_wait` + `flusso_interrotto` CRITICA 1/min: trade, mercato, lato, `esposizione_eur`, `da_secondi` | `flusso_interrotto_senza_rest` CRITICA 1/min: selezioni aperte, `esposizione_eur`, `da_secondi`; cash-out rifiutato `flusso_interrotto` | `flusso_interrotto` CRITICA 1/min: trade, `esposizione_eur`, `da_secondi` |

Modulo comune: `Betfair/stream/flusso_prezzi.py` (`FONTE_RIPIEGO_REST`, `secondi_fermo`, `Promemoria`).
Etichette UI: `tradeStatus.ts` (Safe), `mike.ts`, `omega.ts`.

### 1.4 Test (worktree riallineato su `ef71543`)
| comando | esito |
|---|---|
| `python -m pytest Betfair/safe_strategy/tests -q -p no:cacheprovider` | **1963 passed**, 3 skipped, 1 xfailed |
| `python -m pytest Betfair/mike/tests -q -p no:cacheprovider` | **974 passed** |
| `python -m pytest Betfair/omega -q -p no:cacheprovider` | **1407 passed**, 3 skipped |
| stream (banco comune, identita', cert, freni, strada unica, punteggi, scan_feed, porta banco, arresto ordinato) | **123 passed**, 25 skipped (prima di K2); dopo K2: `test_arresto_ordinato_comportamento` verde |
| `npx tsc -p tsconfig.app.json --noEmit` | **0 errori** |
| `npx vitest run` (flussoPrezzi, flussoInterrotto, mike, omega, Mike page, tradeStatus, safestrategy, controlRoom, ControlRoom) | **571 passed**, 1 skipped |

Test nuovi: `Betfair/safe_strategy/tests/test_flusso_su_master_cantiere_j2_2026_09_28.py` (16: le
strade 1.2 + regola unica Safe e Omega: chiusura col REST vivo, REST muto con riga critica una
volta, nessuna apertura col REST vivo, sorella di combo col REST, apertura Omega bloccata e
controllo, green-up Omega col REST e col REST muto) e
`Betfair/mike/tests/test_mike_flusso_cantiere_j2_2026_09_28.py` (9, sul `run_once` vero col runner
finto: linee ferme nessun comando; controllo; giro bloccato; lay a riposo col flusso fermo e al
rientro; chiusura col REST vivo = LAY al runner; REST muto = nessun comando e UNA riga critica in
3 giri; nessuna apertura e nessuna lettura REST senza posizione; cash-out dell'utente rifiutato
col REST muto e accettato col REST vivo; `execute_place` rifiuta un'apertura sui prezzi REST).
I finti REST hanno le chiavi di `omega_market.read_book`.

### 1.5 Falsificazione (`AUDIT_2026-09-28/cantiere_j2/falsifica_j2.py`)
50 mutazioni del blocco 1: M1-M30 (J, stringhe ritrovate sul codice di master), N1-N7 (strade
J2), A1-A13 (regola unica). Esito in `cantiere_j2/falsifica_blocco1_esito.txt`.
Ripristino byte-identico (SHA-256 per file, nel `finally`), 0 `MUTAZIONE` nei sorgenti dopo.

### 1.6 Reperto C — Omega legge il flusso da una cache sua
- Stesso DATO: la riga di `safe_strategy_scan` (chiave `flusso`) e la riga di stato
  `safe_strategy_status` (chiave `flusso`), scritte dallo stesso scanner.
- Diverso il CAMMINO: Safe e Mike leggono la riga a ogni giro (canale 47336 o DB) e lo stato con
  `db.scanner_status()` (una SELECT per giro); Omega legge riga e stato da
  `scan_feed.shared_cache()` (canale se vivo, altrimenti DB con cache: righe ogni `feed_cache_s` =
  2 s di serie, max 30; stato col TTL della cache).
- Possono dire cose diverse nello stesso istante? Si', solo come RITARDO: Omega vede il passaggio
  vivo→fermo al piu' dopo `feed_cache_s` (+ il suo giro) col DB, subito col canale (il passaggio e'
  nella firma critica dello scanner e il canale lo spinge nello stesso istante). Un «vivo» falso
  PERMANENTE non puo' nascere: la cache non inventa righe, rilegge. Lo stato vecchio puo' solo
  anticipare un «giro bloccato» (e' il caso prudente). **Non ho scritto un test dedicato a questo
  ritardo**: il TTL della cache e' provato dai test esistenti di `scan_feed`/`omega_respiro_db`.

### 1.7 La patch
`AUDIT_2026-09-28/CANTIERE_J2_blocco1.patch` = `git diff origin/master` (= `ef71543`) dei SOLI file
del blocco 1 + lo script di falsificazione e i suoi esiti (reperto D). Elenco in testa alla patch
(`git apply --stat`).

---

---

## PATCH (in sequenza, sopra `staging-2026-09-28` = `96e6974`; worktree `1c7c156` + non committato)
| ordine | patch | file | contenuto |
|---|---|---|---|
| 1 | `CANTIERE_J2_blocco1.patch` | 34 | segnale, veto, regola unica, falsificatore + esito |
| 2 | `CANTIERE_J2_blocco2.patch` | 12 | stream muto: `stream_muto.py`, `riserva_prezzi.py` (inerte senza il blocco 3), `canale_bot.py` (topic `flusso_stream`), `runner.py`, `scalper_session.py`, `tennis_runner.py`, test, UI scalper/tennis |
| 3 | `CANTIERE_J2_blocco3.patch` | 4 | riserva dei runner: `live_order_worker._best_prices`, `risk_engine_worker`, test |
| 4 | `CANTIERE_J2_blocco4.patch` | 6 | UI: `FlussoStreamBanner`, `flussoStreamRunner.ts`, `LadderView`, `SeguiLive`, `MatchReplay` (spento nel replay) |
| B | `CANTIERE_J2_bancoB.patch` | 4 | buco dei dati nel banco comune (`ScannerReplay.dichiara_buco_flusso`), test, falsificatore aggiornato (M14, K1-K2) |

Merge di staging: conflitti solo sugli import di `scalper_session.py` e `tennis_runner.py` (tenuti
entrambi: `stream_muto` e `uscite_proposte`); `mike/service.py` fuso da solo, tenute le modifiche
D1-bis/D1-ter (`_esito_rifiuto_mercato`, freno in `execute_place`, `best_back`/`best_lay` a `X.place`,
fase `errore`) e le mie.

## BLOCCO 2 — stream muto (scalper, sniper, theta, bot tennis, runner calcio)
- Misura: `stream_muto.stato_stream` (runner calcio: il battito PER CONNESSIONE di
  `FrammentoListener.ultimo_msg_mono`, mai una seconda misura; frammento chiuso escluso; frammento
  appena aperto: 30 s di grazia) e `stato_da_battiti` (runner tennis: `RAW_TEE.last_heartbeat_ms`/
  `last_data_ms`). Soglia 15 s (3 heartbeat da 5 s, da riconfermare sul default ufficiale).
- `SorvegliaStream`: UN avviso CRITICAL per episodio (con la posizione non gestita), INFO al
  rientro; 30 s di grazia all'avvio per «mai connesso».
- Sessione scalper (`sorveglia_flusso_sessione`, a ogni battito da 5 s): `live_alerts`
  (`FLUSSO_INTERROTTO`/`FLUSSO_RIPRESO`), attivita' `flusso_interrotto`/`flusso_ripreso` con
  `posizione_non_gestita`, `stats.flusso` nella riga di controllo; Control Room: la frase della
  sessione comincia con «FLUSSO PREZZI INTERROTTO da N s ... posizione NON gestita».
- Runner calcio (`heartbeat_worker` → `_sorveglia_flusso_runner`, ogni 10 s): `live_alerts`
  `RUNNER_FLUSSO_INTERROTTO` con gli ordini vivi, `session.flusso_runner`, topic `flusso_stream`
  sul 47331.
- Runner tennis (`stall_worker` → `_sorveglia_flusso_tennis`, ogni 10 s): `live_alerts`
  `TENNIS_FLUSSO_INTERROTTO` con i bot non flat, attivita' `flusso_interrotto` di ogni bot ospitato
  (max 40), `stats.flusso` nel battito dei bot, topic `flusso_stream` sul 47332; pannello tennis: kind
  in rosso.
- Test: `test_stream_muto_cantiere_j_2026_09_28.py` (6, J), `test_stream_muto_cablato_cantiere_j2_2026_09_28.py`
  (12), vitest `scalperFlusso.test.ts` (2). Suite collegate: stream 487 (cashout, greenup, live order,
  risk engine, stallo, frammenti, scalper gates, battito), tennis 630: verdi.
- Falsificazione: M31-M33 + B1-B11 = **14/14 ROSSE** (`falsifica_b2_esito.txt`); UI U3 rossa.

## BLOCCO 3 — la riserva dei runner
- `riserva_prezzi.py`: `stream_vivo(market_id)` dalla dichiarazione del battito del runner;
  `prezzi_di_riserva` = miglior livello dalla riga del feed dello scanner (`scan_feed.shared_cache`,
  canale o DB: nessuna chiamata Betfair in piu') SOLO se lo scanner dichiara vivi i prezzi di quel
  mercato; motivo di ogni rinuncia in `ULTIMO_ESITO` e nel log al cambio.
- `live_order_worker._best_prices` passa dalla riserva: green-up, flatten, cash-out, daily stop, dutch e
  regole di rischio del runner, a stream muto, non leggono piu' il book fermo.
- `risk_engine_worker`: stop/take-profit/trailing/bracket a stream muto confrontano con il prezzo di
  CHIUSURA della riserva (lay per un back, back per un lay: prudente) o con niente; stop-entry NON
  scatta (nessuna posizione nuova, resta armato, nota una volta); chase NON ri-prezza.
- LIMITI (non degradati in silenzio): il feed porta SOLO il miglior livello (niente profondita') e
  SOLO MATCH_ODDS, Correct Score, Half Time Score, BTTS, HT result e le linee O/U seguite dallo
  scanner; handicap asiatici e altri mercati: nessuna riserva (`riserva_prezzi.py`
  `prezzi_di_riserva`, motivo «il feed non segue questo mercato»). In PAPER l'ordine di chiusura
  parte coi prezzi della riserva ma il matching simulato di flumine usa il book del runner (fermo):
  vedi «non verificato».
- Bot tennis e sessioni scalper: nessuna riserva di prezzo (i bot flumine agiscono solo su un book
  nuovo; dar loro un book sintetico dal feed vorrebbe dire cambiare il loro motore). Proposta:
  resta l'avviso del blocco 2; eventuale chiusura forzata via REST a stream muto = decisione
  dell'utente.
- Test: `test_riserva_runner_cantiere_j2_2026_09_28.py` (11). Falsificazione R1-R8 **8/8 ROSSE**
  (`falsifica_b3_esito.txt`; R6 era verde al primo giro: il test non dava una riserva viva, corretto).

## BLOCCO 4 — Segui Live e ladder
- `lib/flussoStreamRunner.ts` (lettura pura del topic `flusso_stream`, chiavi di
  `stream_muto.CHIAVI_CANALE`, scade dopo 30 s senza messaggi), `components/live/FlussoStreamBanner.tsx`
  (banner rosso lampeggiante «⚠ FLUSSO INTERROTTO da N s (...): prezzi FERMI»), montato in
  `LadderView` (calcio e tennis, quindi Segui Live, popout, multi-ladder, colonna tennis; spento nel
  replay con `flussoRunner={false}` in `MatchReplay`) e in cima al terminale di `SeguiLive`.
- Test `flussoStreamRunner.test.tsx` (3); U1, U2 rosse; tsc 0; LadderView/GridView/LiveTradingPanel/
  tennis verdi.

## RESTO B — il banco sa provare il veto
- `ScannerReplay.dichiara_buco_flusso(da, a, mercati)`: nel buco i book di quei mercati non arrivano
  allo scanner e la registrazione non li conferma; senza buchi il banco e' byte per byte quello di
  prima (test: tabella e sequenza identiche con un buco fuori tempo).
- Test `test_banco_flusso_interrotto_cantiere_j2_2026_09_28.py` (3); M14, K1, K2 ROSSE.
- **NON fatto**: lo scenario `flusso-interrotto` dentro i tre strumenti di certificazione (Mike,
  Omega, Safe: `tools/replay_registrazioni.py`) con i controlli di condotta (nessuna apertura nella
  finestra, chiusure solo con fonte REST, ripresa senza doppi ordini). Proposta: in ogni
  `certifica_scenario`, con lo scenario scelto, `banco.dichiara_buco_flusso(ko+20', ko+25')` e tre
  controlli K sulle attivita'/ordini del bot nella finestra; il REST del replay deve leggere il book
  della registrazione.

## CORREZIONI (reperti 1-4 del revisore) — `CANTIERE_J2_correzioni.patch` = `git diff prova-tutto-2026-09-28`

**1 (ALTO) — ordini appoggiati a stream muto (regola 11 dell'utente).** Ordini appoggiati che il
runner GOVERNA dopo il piazzamento (`Betfair/stream/risk_engine_worker.py`):
- **chase** (`_handle_chase`, fase tracking): l'ordine inseguito; puo' aprire o chiudere;
- **bracket** (`_handle_bracket`, stato `offset_placed`): il take-profit appoggiato (una chiusura) e
  lo stop che lo sorveglia.
Non governati dopo il piazzamento (la regola si chiude subito, `status=done`): offset semplice
(`_handle_offset`, take-profit PERSIST = chiusura), stop-entry (`_handle_stop_entry`, apertura LAPSE;
a stream muto non scatta affatto). I submin del `live_order_worker` sono della coda, non di una regola.
Regola realizzata (paper e live uguali, e' la stessa coda):
- apertura o chiusura si decide dalla POSIZIONE ABBINATA (`_riduce_rischio`: un back chiude un
  LAY, un lay chiude un BACK; piatta = apertura), letta dal blotter con la strategia vera
  (`_process_rule` ora passa `strategy` al chase);
- stream muto e NESSUN prezzo di riserva: APERTURA → cancel in coda (`risk<id>cf`), regola `done`
  con `ritirato_flusso`, `live_alerts` CRITICAL; al rientro nessun ripiazzamento (la strategia
  ridecide). CHIUSURA → resta, `live_alerts` CRITICAL al piu' 1/min per regola con la posizione
  (se vince / se perde in EUR). Bracket senza riserva: nessuna decisione dello stop al buio, riga
  critica 1/min;
- stream muto CON riserva viva: apertura resta ferma (nessun ri-prezzamento, nessuna posizione
  nuova); chiusura: il chase continua sui prezzi della riserva.
La «D3» citata nel commento era la proposta D3 del referto di J (§8), ora sostituita da questa regola.

**3 (MEDIO) — status e canale.**
- `stream_muto._status_non_ok`: FAIL-CLOSED su ogni `status` diverso da null/200 (503 →
  `stream_latente`, altrimenti `stream_status_<codice>`, anche illeggibile); il motivo va
  nell'avviso e nell'attivita'. Stessa regola nello shard dello scanner
  (`safe_strategy/stream.py` `StreamShard.latente`).
- UI: canale locale del runner giu' = banner ambra «stato dello stream NON NOTO (canale locale del
  runner non raggiungibile)», mai silenzio (`flussoStreamRunner.giudizioConCanale`,
  `FlussoStreamBanner` con `useLocalStatus`). Col canale collegato e nessun messaggio da 30 s il
  runner non ha mercati da sorvegliare (non pubblica): nessun banner.

**2 (MEDIO) — la soglia dal valore vero** (file:riga):
- scanner: `heartbeat_ms=5000` chiesto in `Betfair/safe_strategy/stream.py:65` (`_HEARTBEAT_MS`) e
  passato a `subscribe_to_markets` a `:276`;
- runner calcio, runner tennis, sessioni scalper: flumine NON lo passa
  (`.venv/.../flumine/streams/marketstream.py:36-42`), nemmeno la risottoscrizione a caldo
  (`Betfair/stream/sottoscrizione_a_caldo.py:102-104`): betfairlightweight manda `null`
  (`.venv/.../betfairlightweight/streaming/betfairstream.py:109,133`);
- lo schema ESA ufficiale NON ha un default: la richiesta sta fra 500 e 5000 ms e il valore VERO
  e' rimandato sull'immagine iniziale (`MarketChangeMessage.heartbeatMs`, «may differ from
  requested: bounds are 500 to 30000»), letto dallo schema su GitHub il 28/09;
- quindi: `SOGLIA_S = 3 x HEARTBEAT_MS_RICHIESTO` con `HEARTBEAT_MS_RICHIESTO =
  min(_HEARTBEAT_MS dello scanner, 5000)` importato, non scritto a mano (= 15 s); il runner calcio
  legge il valore RIMANDATO da Betfair (`FrammentoListener.heartbeat_ms_server`, da `"heartbeatMs"`
  del messaggio) e usa 3 volte quello (`stream_muto.soglia_per`). Runner tennis e sessione scalper
  non leggono il valore rimandato (listener di betfairlightweight senza tee di quel campo): 15 s,
  cioe' la soglia piu' stretta fra i valori ammessi in richiesta; se Betfair rimandasse piu' di 5 s
  il difetto sarebbe un falso allarme, mai un silenzio.

**4 (BASSO)** — test `test_banco_senza_buchi_righe_identiche_al_banco_di_prima` (banco nuovo contro
la `pubblica` di J, mercato fermo: tabella e numero di righe identici).

Test: J2 stream + risk engine + frammenti + tennis = 775 passed (1 fallito
`test_motore_ordini_tennis_2026_09_25.py::test_profilo_rapido_safe_tennis_sulla_registrazione_vera`:
**fallisce identico su `prova-tutto-2026-09-28` senza le mie correzioni**, R8 «sotto il minimo», non
mio); Safe 2013 passed; tsc 0; vitest live/tennis/SeguiLive 191 passed.
Falsificazione (`cantiere_j2/falsifica_correzioni_esito.txt`): C1-C9 + M6, M14, M31-M33, K1, K2
tutte ROSSE; R6 sostituita da C1-C4. UI U4 (canale giu' senza banner) rossa.

## Decisioni per l'utente
- **D1 — soglie del segnale** (J): 45 s calcio in gioco, 25 s tennis, 125 s pre-partita; stanno
  sopra la cadenza del ripiego REST dello scanner. Proposta: tenerle.
- **D2 — Omega apriva col proprio book REST col feed fermo**: con la regola unica NON apre piu'.
  E' un cambio di condotta voluto dal coordinatore (una apertura mai col flusso fermo). Proposta:
  confermarlo.
- **D3 — Mike, `over_cover` col ripiego REST**: la copertura Over 4.5 e' per il motore un ruolo
  d'«apertura» (`OPENING_ROLES`), ma riduce il rischio della posizione Under: l'ho trattata come
  COPERTURA (parte col REST vivo). Proposta: confermare.
- **D4 — Omega green-up col flusso fermo**: il REST si legge solo con un rischio reale (gol o
  residuo), come prima; il take-profit «a prezzo» senza gol non si valuta finche' il feed e' fermo.
  Proposta: tenerlo (una lettura REST per ciclo e per trade violerebbe la regola del feed unico).

## Cosa NON ho fatto / NON ho potuto verificare (blocco 1)
- Nessuna caduta di rete VERA: tutto su finti (scanner vero, righe vere, REST finto con le chiavi
  vere di `omega_market.read_book`).
- Il replay del banco NON l'ho rilanciato (lo lancia il coordinatore). Reperto B (scenario
  «flusso-interrotto» nel banco) non ancora fatto: il banco conferma sempre il flusso, quindi oggi
  non puo' provare il veto (va nel prossimo giro).
- Omega: nessun test che misuri il ritardo della cache (1.6).
- Safe: il cash-out dell'UTENTE col flusso fermo usa `_book_prices` (senza tetto, un clic) e non
  scrive la riga `ripiego_rest` (il risultato porta gia' `source: rest`).
- `npm run build` non fatto (si fa all'integrazione).
- Blocchi 2-4: nessuna caduta vera dello stream; heartbeat di default di Betfair (5 s) non
  riconfermato sulla pagina ufficiale; rilevazione nel runner ogni 10 s (quindi fino a ~25 s);
  in PAPER a stream muto il matching simulato di flumine usa il book fermo del runner (paper diverso
  dal live in quella finestra); vitest `Mike.test.tsx` «tetto 500 righe» va in timeout sotto carico
  (verde da solo).
- D2/D3 sono la regola data dal coordinatore: le riporta lui all'utente come cambio di condotta.
- Controlli dal vivo in paper (blocchi 2-4): nessun `FLUSSO_INTERROTTO` in `live_alerts` con la
  rete sana; `stats.flusso.interrotto=false` nelle righe scalper e bot tennis; nessun banner rosso su
  ladder/Segui Live; a una caduta (se capita) banner rosso entro ~25 s e riga `RUNNER_FLUSSO_RIPRESO`
  al rientro.

## Controlli dal vivo in paper (blocco 1)
| controllo | atteso | dove |
|---|---|---|
| righe col flusso | `payload->'flusso'->>'vivo'='true'` sulle partite in gioco | `safe_strategy_scan` |
| stato dello scanner | `payload->'flusso'->>'calcolato_ms'` avanza ogni ~10 s | `safe_strategy_status` id `scanner` |
| nessun veto a vuoto | nessuna `flusso_interrotto` / `ripiego_rest` con lo stream sano | attivita' Safe, Mike, Omega |
| gol = sospensione | per pochi secondi `vivo=false` motivo `senza_prezzi`, poi `true` | righe della partita |
| (se capita) flusso fermo con posizione | `ripiego_rest` (REST vivo) oppure riga rossa 1/min con esposizione | attivita' del bot |
