# P&L REALE DEL CONTO — Mike (30/09/2026)

Ordine dell'utente (30/09): «IL PNL DEVE ESSERE REALE CON TUTTO QUELLO CHE FANNO I BOT E IO
MANUALMENTE! ANCHE SE REGOLO LE LORO OPERAZIONI!!! IL TRADER DEVE SAPERE COSA STA GUARDANDO E
CHE DATI!!! [...] MASSIMA COERENZA». Vincolo aggiunto: «non voglio spammare i server Betfair».

Delegato di costruzione, worktree `agent-a5d9566643a63ed1e`, base master `30917ed`. Niente
commit. Lavoro NON certificato: va riletto e rieseguito dal coordinatore.

Consegna: questo referto + `AUDIT_2026-09-30/PNL_REALE_DEL_CONTO.patch` (25 file, si applica
pulita su `30917ed`: `git apply --cached --check` verde). Nessuna migrazione.

---

## 1. Che cosa leggeva Mike al regolamento (prima) e che cosa legge ora

**Prima (base `30917ed`)**, solo calcolo interno, mai il conto:
- ramo «mercato chiuso» di `_run_event`: `Betfair/mike/service.py:4465` (void per mercato,
  `E.settle_legs_by_market`), `:4504` (P&L indipendente dal punteggio, `E.settle_legs`), `:4548`
  (normale, `E.decide` -> `engine.py:2834` `settle_legs`) -> `_settle_trades` (`:5643`), che
  scrive su ogni riga `pnl` = calcolo interno;
- `list_account_cleared_orders` (`service.py:229`) la usava SOLO la sorveglianza della
  posizione di conto (`_sorveglia_posizione_di_conto`, `:2934`), mai il regolamento;
- gli ordini dell'utente non entravano MAI nel P&L della partita: dopo la chiusura dal sito
  (R3, `chiuso_dall_utente`) Mike avrebbe regolato solo le sue righe 5087/5089/5090.

**Ora (LIVE)**, `service.py` del worktree:
- `:4496` il ramo «mercato chiuso», dopo il blocco «ordini ancora vivi», chiama
  `_leggi_regolato_conto` (`:5742`). Se Betfair non ha ancora regolato TUTTO (ogni scommessa
  abbinata di Mike + la commissione dei mercati con un profit) la partita resta in SETTLING
  (nessun regolamento cieco) e si rilegge a cadenza lenta; se e' pronto, i tre percorsi di
  regolamento passano il conto a `_settle_trades` (`:6001`).
- Letture (sportello `_RealMarket`): `list_account_cleared_bets` (`:236`, `listClearedOrders`
  per scommessa, entrambi i mercati in UNA chiamata, normalizzata con
  `omega_market._riga_regolata`) e `list_account_cleared_markets` (`:254`, `groupBy=MARKET`:
  l'unico livello che porta `commission`, come il runner).
- Composizione PURA in `Betfair/mike/regolato_conto.py:114` `componi_regolato`: netto per
  scommessa = `profit` (LORDO, docs Betfair pag. 54: back 2,00 @ 1,28 -> `profit` 0,56 e
  `commission` 0,03 a parte) meno la quota della commissione del SUO mercato, con la STESSA
  funzione del runner (`reconcile_worker.commissioni_per_ordine`, riusata: i numeri per riga
  sono gli stessi che il runner scrive in `pnl_betfair`).
- VINCE BETFAIR: ogni riga di Mike con la sua scommessa regolata prende esito, lordo,
  commissione e netto di Betfair (`pnl`, `pnl_betfair`, `commissione_betfair`,
  `pnl_betfair_settled_at`, `meta.pnl_fonte='betfair'`); il calcolo interno resta in
  `meta.pnl_interno`/`pnl_gross_interno`. Se il P&L di Mike del motore differisce da quello di
  Betfair (o esito/lordo di una riga) -> diario `pnl_differenza_betfair` (critico) coi numeri.
  Una riga di Mike creduta 'error' ma abbinata e regolata da Betfair prende il P&L di Betfair
  (`meta.corretto_da_betfair`), e lo dice il diario.
- `settled_pnl` della partita = P&L del CONTO sui mercati di Mike (Mike + utente); in
  `mike_events.ctx.pnl_conto` la scomposizione: `{fonte:'betfair', conto, mike, utente,
  interno_mike, commissione_mike, commissione_utente, ordini_utente, altri_bot_esclusi,
  netto_altri_bot, senza_bet_id, chiamate_rest, letto_at}`. La somma dei `pnl` delle righe della
  partita (Mike + utente) = `settled_pnl` (H4 conservato).
- Diario `settled`: `pnl` = conto, piu' `pnl_fonte`, `pnl_mike`, `pnl_utente`,
  `pnl_interno_mike`, `ordini_utente`, `altri_bot_esclusi`, `chiamate_rest`.
- **PAPER invariato**: `_leggi_regolato_conto` torna `None` (paper, o nessuna riga live
  abbinata) e il regolamento e' quello interno di sempre, etichettato «simulato».

## 2. La riga «utente» (contratto per il verdetto in tempo reale)

Una riga di `mike_trades` per scommessa Betfair dell'utente sui mercati della partita
(`regolato_conto.riga_utente`, `:311`), stesse chiavi e tipi delle righe vere:

| chiave | valore |
|---|---|
| `signal_key` | `utente-<bet_id>` (una per scommessa; idempotente) |
| `role` | `utente` (colonna senza CHECK) |
| `strategy` | `manual_close` (unico valore del CHECK `mike_trades_strategy_check` per «a mano»: nessuna migrazione) |
| `origin` / `mode` | `manual` / `live` |
| `bet_id`, `side`, `price`, `size`, `size_matched`, `avg_price_matched`, `liability` | dalla scommessa Betfair |
| `market_id`, `market_type`, `selection_id`, `selection_name` | selezione Betfair (nome «Over 3.5 Goals» dalle selezioni della partita) |
| `status`, `pnl`, `pnl_betfair`, `commissione_betfair`, `settled_at` | esito e netto regolati da Betfair |
| `closes_trade_id` | la riga d'APERTURA di Mike sullo stesso mercato (la posizione che l'utente ha regolato): storico, cicli e «posizioni chiuse» la contano DENTRO la posizione, non come ciclo nuovo del bot |
| `meta` | `fonte='utente'`, `pnl_fonte='betfair'` (o `'in_corso'`), `pnl_gross`, `commission_paid`, `customer_order_ref`, `nota` |

Chi e' «utente»: scommessa regolata sui mercati della partita che NON ha una riga di Mike con
quel `bet_id`, NON porta un riferimento di Mike (ref della gamba, `mike-t<id>`) e NON e' di un
altro bot (`db.proprietari_bet`, `db.py:215`: riga LIVE in `omega_trades`/
`safe_strategy_trades`/`betfair_live_orders` con source di un bot; oppure ref `omega-`/`safe-t`/
`sc########`/`sn########`). Sito (`source='account'`) e terminale manuale dell'app
(`source='runner'`) = utente. Verificato in SOLA LETTURA sul DB vero: `proprietari_bet` sui tre
ordini veri dell'utente su Vsetin -> `utente` tutti e tre.

**Per il delegato del canale ordini (topic `conto`)**: `service.scrivi_riga_utente_in_corso`
(`service.py:5866`) scrive/aggiorna la STESSA riga da un ordine del conto ABBINATO (grafia di
`omega_market._riga_corrente`: il messaggio `conto` e' camelCase di `listCurrentOrders`, si
normalizza con quella funzione; passare `strategy_ref` = `customerStrategyRef` se c'e').
Nessuna chiamata a Betfair, idempotente per `signal_key`, `status='open'`, P&L 0,
`meta.pnl_fonte='in_corso'`; il regolamento la ritrova e la aggiorna coi numeri di Betfair
(test `test_riga_utente_in_corso_dal_segnale_e_poi_regolata_senza_doppioni`). NON e' collegata
a nessun punto di chiamata: `_sorveglia_posizione_di_conto` e il canale ordini sono fuori dal
mio perimetro.

Guardie (una riga utente non e' mai una gamba di Mike): `_gamba_dalla_riga` (`:5215`) e il
pre-controllo dello specchio `_open_refs_by_event` (`:5187`) la saltano; il regolamento del
motore la ignora (non e' in `per_leg`); negli aggregati e' una CHIUSURA (`closes_trade_id`):
non conta fra le posizioni aperte ne' fra i cicli.

## 3. Chiamate REST a Betfair (vincolo «non spammare»)

| | prima | dopo |
|---|---|---|
| durante la partita | invariato | invariato (nessuna chiamata nuova; ordini utente in corso dal topic `conto`, non da REST) |
| al regolamento, Betfair gia' regolato | `listMarketBook` x2 (per tentativo) | + **2**: `listClearedOrders` SETTLED (i due mercati insieme) + `listClearedOrders groupBy=MARKET`. La VOIDED solo se manca una scommessa di Mike a mercato gia' regolato |
| al regolamento, Betfair non ancora regolato | — | 1 chiamata per tentativo (2 dal 3° tentativo: + VOIDED), tentativi a 1, 2, 4, 8, poi ogni 15 minuti, **tetto 20 tentativi** (~4 h); oltre il tetto: nessuna chiamata, regolamento col calcolo interno dichiarato «stima» (il runner scrivera' comunque `pnl_betfair` sulle righe quando Betfair regola) |
| partita paper | — | 0 |

Misura nel banco (coda, LIVE): `chiamate REST del regolato 2` sia in `base` sia in
`chiuso-fuori-app`. Test: `test_una_lettura_per_partita_due_chiamate_rest` (2 chiamate, nessuna
a partita regolata), `test_attesa_lenta_e_con_tetto_poi_stima_dichiarata` (1+1+2+2 chiamate
con tetto 4, passi >= 60/120/240 s, poi stima dichiarata).

## 4. Etichette prima -> dopo (UNA parola per la stessa cosa: `frontend/src/lib/fontePnl.ts`)

Vocabolario: **conto** = «P&L del conto Betfair (tutte le operazioni: Mike + utente)» (breve
«conto Betfair»); **simulato** = «simulato (runner paper)»; **stima** = «stima del bot (Betfair
non ha ancora regolato)». Fonte di una riga: paper -> simulato; `meta.pnl_fonte='betfair'` o
`pnl_betfair` presente -> conto; altrimenti stima. Partita: `ctx.pnl_conto.fonte`.

**Pagina Mike**
- Scheda partita (`MikeMatchCard.tsx`): «regolato +X» -> «regolato +X · conto Betfair (di cui
  Mike +2,10 € · di cui utente −2,15 €)» (paper: «· simulato»; senza Betfair: «· stima»), titolo
  con la frase intera; «esito +X» -> «esito +X (conto Betfair)»; «partita già chiusa · risultato
  +X» -> «... +X (conto Betfair)».
- KPI «P&L oggi»: sotto il giorno, nuova riga «P&L del conto Betfair (tutte le operazioni:
  Mike + utente) · di cui Mike … · di cui utente …» (paper: «simulato (runner paper)»; se una
  riga di oggi e' ancora calcolo del bot: «stima …»).
- Operazioni della giornata: nota «Una riga per PARTITA col netto …, commissione già tolta.» +
  «P&L: <fonte>.»; tooltip del P&L della riga: «… — in pagina il NETTO · fonte: <fonte>»;
  ruolo della riga utente «Ordine tuo (non del bot)», badge «tuo» (prima «manuale»).
- Attività: `settled` in live -> «totale gol 3 · P&L del conto Betfair (…) −0,05 € · di cui
  Mike +2,10 € · di cui utente −2,15 €» (prima mostrava `net`, il calcolo del bot); quattro kind
  nuovi con etichetta italiana: ATTESA DEL REGOLATO BETFAIR, P&L: IL CALCOLO DEL BOT DIFFERISCE
  DA BETFAIR, ORDINI TUOI NEL CONTO DELLA PARTITA, REGOLATO BETFAIR NON LEGGIBILE: STIMA.
- Storico (tab della pagina, `TradingHistory` via `fonteNota`): «… come in «Posizioni chiuse»»
  + «· P&L: P&L del conto Betfair (…) per le partite regolate dal 30/09/2026; prima: stima»
  (paper: «P&L: simulato (runner paper)»); dettaglio del giorno: la riga utente «TUO (non del
  bot)» (prima «MANUALE»).

**Control Room** (`PosizioniChiuse.tsx`, `DettaglioRigaView.tsx`, `useControlRoom.ts`)
- Fonte della cifra: «Betfair» -> «conto Betfair»; «stimato» -> «stima»; «prova» -> «simulato»;
  «Betfair + stimato» -> «conto Betfair + stima»; titoli dalla stessa frase.
- Testata live: «regolato da Betfair» -> «conto Betfair (regolato)»; «stimato (calcolo del bot,
  Betfair non ha ancora regolato)» -> «stima del bot (Betfair non ha ancora regolato)».
- Dettaglio: «di cui Betfair … e stimato …» -> «di cui conto Betfair … e stima …»; gamba
  `utente` -> «ordine tuo (non del bot)».
- Le pillole di filtro («con stimati» / «solo Betfair») NON cambiate (sono filtri, non fonti).
- **Doppio conteggio evitato**: nella composizione della barra di giornata la voce «Mike»
  prende SOLO gli ordini del bot (le righe `utente` sono escluse): gli ordini dell'utente sono
  gia' nel «Manuale · sito» del conto (il runner li attribuisce all'utente, vedi §5). La
  POSIZIONE chiusa della partita resta intera (Mike + utente).

## 5. File toccati

Nuovi: `Betfair/mike/regolato_conto.py`, `Betfair/mike/tests/test_mike_pnl_reale_del_conto_2026_09_30.py`,
`frontend/src/lib/fontePnl.ts`, `frontend/src/lib/fontePnl.test.ts`,
`frontend/src/components/mike/MikeMatchCard.fontePnl.test.tsx`,
`AUDIT_2026-09-30/falsifica_pnl_reale_conto.py` (+ `.out`),
`AUDIT_2026-09-30/falsifica_pnl_reale_conto_replay.py`, referti replay in
`AUDIT_2026-09-30/replay/mike_{base,chiuso_fuori_app,chiuso_fuori_app_FALSIFICA_M2}_PNL_CONTO.txt`.

Modificati:
- `Betfair/mike/service.py` — sportello (2 letture), ramo di regolamento, `_leggi_regolato_conto`,
  `_applica_conto`, `_settle_trades` (conto), `scrivi_riga_utente_in_corso`, due guardie.
- `Betfair/mike/db.py` — `proprietari_bet` (sola lettura).
- `Betfair/stream/reconcile_worker.py` — `_proprietari`: la riga `role='utente'` di `mike_trades`
  non fa diventare «mike» l'ordine dell'utente (resta manuale sito/app come prima: nessun
  cambio della composizione del conto).
- `Betfair/stream/backtest/banco_comune.py` — `MercatoFlumine.list_account_cleared_bets` /
  `list_account_cleared_markets` (stesse chiavi di produzione, solo mercati regolati nel banco),
  `aliquota_commissione`, `pnl_betfair(con_utente=)`; `DbMemoria.proprietari_bet` (vuoto,
  dichiarato in `senza_dato` solo se chiamato).
- `Betfair/mike/tools/replay_registrazioni.py` — aliquota del banco dal parametro; RG1 in LIVE
  confronta col conto del banco ordini dell'utente compresi (`con_utente`); nota «regolamento
  dal CONTO» (solo quando c'e').
- `Betfair/stream/backtest/registro_bot.py` — `Betfair.mike.regolato_conto` nell'impronta.
- Test adeguati: `test_mike_audit_2026_09_11.py` (4 kind dichiarati), `test_mike_p5_4b_2026_09_29.py`
  (impronta 9 file).
- Frontend: `lib/mike.ts`, `pages/Mike.tsx`, `components/mike/MikeMatchCard.tsx`,
  `components/mike/MikeEventPnlTable.tsx`, `components/trading/TradingHistory.tsx`,
  `components/trading/DayDetail.tsx`, `components/controlroom/PosizioniChiuse.tsx`,
  `components/controlroom/DettaglioRigaView.tsx`, `components/controlroom/useControlRoom.ts`
  (+ test in `useControlRoom.test.tsx`).

## 6. Test

Ambiente NEUTRO (`AUDIT_2026-09-30/ereditato_29_09/scratchpad_admin_e7/replay_mike.sh`, copiato
in `_pnl_scratch/neutro.sh` del worktree).

- `pytest Betfair/mike` -> **1369 passati** (riferimento 1351 + 18 nuovi), 0 rossi, ~60 s;
  con `Betfair/stream/tests/test_reconcile_worker.py test_pnl_betfair_reale_2026_09_24.py
  test_banco_mike_ondata2_2026_09_30.py`: **1447 passati**.
- Nuovi (18), finti con le righe VERE 5087-5090 (lette dal DB in sola lettura) e gli ordini
  VERI dell'utente su Vsetin da `betfair_live_orders` (445039002079 punta Over 3,5 4,34 @ 1,92;
  445039002080 punta Over 3,5 0,09 @ 1,92; 445039090782 punta Under 4,5 5,18 @ 1,44), forma
  `_riga_regolata`/`groupBy=MARKET`; risultato SUPPOSTO (3 gol; 5 gol in un caso a parte):
  solo Mike (cleared = interno, nessuna differenza, +1,87); ordini dell'utente (3 righe utente,
  partita −0,05 = Mike +2,10 + utente −2,15; interno +1,87 -> diario, vince Betfair); 5 gol
  (Mike +1,05 contro interno +0,80, utente −1,11, conto −0,06); regolato non disponibile ->
  SETTLING, nessuna lettura prima del minuto, poi regolato; commissione non letta -> attesa;
  lettura KO -> attesa; paper (nessuna lettura, interno, nessuna riga utente); ordine di un altro
  bot escluso; nessun doppione al secondo regolamento; riga utente mai gamba; riga di Mike
  creduta 'error' regolata da Betfair; runner (`_proprietari`) non attribuisce a Mike; due
  chiamate REST; tetto e stima dichiarata; banco con le chiavi di produzione; riga dal segnale
  in corso poi regolata senza doppioni; segnale che non scrive righe per Mike/altri bot/non
  abbinati/paper.
- Frontend: `npx tsc -p tsconfig.app.json --noEmit` **0 errori**; vitest mirato (22 file: Mike,
  Control Room posizioni chiuse e hook, storico, `mike.test.ts`, nuovi) **381 passati**, 1
  saltato (preesistente).

**Falsificazioni** (`AUDIT_2026-09-30/falsifica_pnl_reale_conto.py`, esito in `.out`): 18
mutazioni, **18 ROSSE**, file ripristinati e verificati byte per byte, `git diff --stat`
identico prima/dopo: M1 vince il calcolo interno; M2 P&L partita solo Mike; M3 utente contato
come Mike; M4 regolamento cieco; M5 conto letto in paper (entrambe le guardie); M6/M6b VOIDED
in piu'; M7 senza tetto; M8 riga utente ricostruita come gamba; M9 runner la attribuisce a Mike;
M10 riga utente non scritta; M11 senza `closes_trade_id`; M12 segnale su ordini di Mike; M13
segnale che duplica; F1 fonte «conto» senza Betfair; F2 diario col calcolo del bot; F3 riga
utente contata anche sotto Mike nella barra; F4 scheda senza fonte. (Nel primo giro M5 e M8
erano VERDI: test a vuoto — difetto 29 del catalogo — corretti: M5 muta entrambe le guardie, il
test di M8 dimostra che la riga ha i dati per diventare gamba.)

**Falsificazione a livello di replay**: M2 sul codice di produzione, `chiuso-fuori-app` sulla
coda -> **KO, RG1 x1** (P&L della partita di Mike −10,00 contro 0,00 del conto del banco);
`AUDIT_2026-09-30/replay/mike_chiuso_fuori_app_FALSIFICA_M2_PNL_CONTO.txt`.

## 7. Replay (uno alla volta, `--worker 0 --data-dir .../_live_raw`, registrazione 35760084)

- `base --trasporto entrambi` (`replay/mike_base_PNL_CONTO.txt`): **2 OK, 0 violazioni**, RG1 x2
  verde, PARITA' coda/canale RAGGIUNTA (ordini 6/6, righe 5/5). Canale (paper): blocco `base
  <canale>` **identico riga per riga** a `mike_tutti_FINALE.txt` (tolta la riga del tempo).
  Coda (LIVE): «regolamento dal CONTO: fonte betfair | conto −14,17 = Mike −14,17 + utente 0,0 |
  calcolo interno −14,17 | chiamate REST 2 | differenze 0».
- `chiuso-fuori-app --trasporto entrambi` (`replay/mike_chiuso_fuori_app_PNL_CONTO.txt`): **2 OK,
  0 violazioni**, RG1 x2. Coda (LIVE): l'utente chiude con ordini VERI su flumine; al regolamento
  «conto 0,00 = Mike −10,00 + utente +10,00 | righe utente 2 [(…002 back lost −3,00), (…003 lay
  won +13,00)] | chiamate REST 2»; RG1 confronta col conto del banco ordini dell'utente compresi
  (+0,00) e l'esito di OGNI riga, utente comprese. Il caso chiesto dal brief e' esercitato.
  Canale: NE (previsto: in paper la posizione di conto non si legge, `TRASPORTO_OBBLIGATO`) e
  PARITA' NON RAGGIUNTA (ordini coda 1 / canale 6: la differenza nasce DURANTE la partita, prima
  del regolamento, perche' il canale non vede la chiusura dell'utente — strutturale, non di
  questo lavoro; exit code 1 per questo).
- Tempi: 136 s e 132 s per coppia (canale ~113 s contro 48,7 s del FINALE). Il codice nuovo non
  gira per giro (paper esce alla prima riga; in live solo al regolamento): la CPU del PC era al
  **100 %** misurata alle 17:04 (altri lavori in corso). Tempi NON confrontabili col FINALE; il
  referto e' identico numero per numero.

## 8. Migrazioni

Nessuna. Le colonne `pnl_betfair`, `commissione_betfair`, `pnl_betfair_settled_at` esistono
gia' su `mike_trades` (`migrations/pnl_betfair_reale_2026-09-24.sql`, verificato leggendo la riga
5087); `role` non ha CHECK; `strategy='manual_close'` e `origin='manual'` sono ammessi. Le RPC
(`get_mike_aggregates`, `get_mike_daily`, `get_mike_day_trades`, posizioni chiuse) sommano `pnl`
delle righe regolate: le righe utente, chiusure della posizione, entrano da sole.

**Reperto del coordinatore (vincolo `betfair_live_orders_source_check`, errore 23514 nel log
del runner)**: verificato. Le righe RIFIUTATE sono gli ordini di **Mike** (445036548091,
445036594830, 445038902107, 445038952708), che `reconcile_worker._account_order_row` scrive con
`source='bot:mike'` (CHECK ammette `runner, account, scalper, omega, safe, mike, …` ma non
`bot:*`). Gli ordini dell'UTENTE dal sito sono entrati regolarmente (`source='account'`, righe
46716, 46717, 46768 lette in sola lettura). Non e' la causa del P&L mancante (Mike non leggeva
il conto al regolamento: e' quello che questo lavoro cambia). **Non ho scritto la migrazione**:
ammettere `bot:*` porterebbe gli ordini di Mike nello specchio del terminale manuale
(`lib/liveOrders.ts`) come ordini «esterni». Proposta (fuori perimetro, runner): in
`_reconcile_orders` non riscrivere nello specchio gli ordini con `customerStrategyRef` di un bot
che ha la sua tabella (mike/omega/safe) — toglie 4 scritture fallite a ogni giro.

## 9. Parita' paper/live

- PAPER: regolamento identico a prima (banco: `base` canale identico al FINALE); fonte
  «simulato»; nessuna riga utente (in paper non esiste un conto).
- LIVE: regolamento dal conto Betfair; stessa macchina a stati (SETTLING/SETTLED), stesse
  righe, stessa H4. La differenza e' la fonte dei numeri, che e' esattamente l'unica ammessa
  (i soldi veri): il paper non ha un conto da leggere.

## 10. Omega e Safe (NON toccati): che cosa leggono oggi al regolamento

- **Omega** (`Betfair/omega/omega_service.py:4738` `settle_open`, `:4873` `_settle_hedged`):
  legge il libro del mercato chiuso (`read_market`/`read_markets`) e calcola il P&L internamente
  (`execution.settle_pair/settle_group`, commissione sul netto di mercato). Mai il cleared, mai
  gli ordini dell'utente. `pnl_betfair` sulle sue righe lo scrive solo il runner.
- **Safe** (`Betfair/safe_strategy/bot_service.py:1866` `_cleared_orders_for_market` ->
  `execution.settle_position`, `execution.py:2143`): legge `list_cleared_orders` filtrato sulle
  SUE righe; se OGNI gamba ha un `profit` regola con quei numeri, altrimenti ripiega SUBITO sul
  calcolo interno (nessuna attesa: puo' regolare «cieco» prima che Betfair abbia regolato).
  **Reperto**: `execution.py:2152` dichiara «Il profit di Betfair e' GIA' netto di commissione»
  e NON toglie la commissione. La documentazione nel repo (`Betfair_api_documentation.pdf` pag.
  54: back 2,00 @ 1,28 WON -> `profit` 0,56 = lordo, `commission` 0,03 a parte) e il runner
  (`reconcile_worker`) dicono il contrario: se Betfair addebita commissione, Safe sovrastima il
  netto di quella commissione. Da verificare su un reperto con commissione > 0,01.
- Cosa servirebbe (stesso principio): lettura del regolato del conto per mercato al regolamento
  (le due funzioni dello sportello di Mike sono generiche), attesa in regolamento finche'
  Betfair non ha regolato (con tetto), netto = lordo − quota della commissione del mercato
  (`commissioni_per_ordine`), righe `utente` per gli ordini dell'utente sui loro mercati, stesse
  etichette (`lib/fontePnl.ts`). Omega: correct score e mezzo tempo, stessa struttura.

## 11. Cosa NON ho fatto / NON ho potuto verificare

- Nessuna chiamata a Betfair: la lettura `groupBy=MARKET` e la forma vera della risposta
  (`profit`, `commission`, `betCount`, `settledDate` per mercato) sono dalla documentazione e dal
  runner (`_fetch_cleared_markets_today`), non da una risposta vista oggi. La lettura per
  scommessa usa il client del repo (`client.list_cleared_orders`, `marketIds` + `betStatus`).
- Il risultato di Vsetin non e' noto (39', 1 gol alle 16:09): i profit nei test sono calcolati a
  mano; i bet dell'utente sono veri, i loro esiti no.
- `scrivi_riga_utente_in_corso` non e' collegata al canale ordini (perimetro dell'altro
  delegato): provata solo in unita'.
- Il ramo «P&L indipendente dal punteggio» col conto (`service.py` dopo `ok0`) non ha un test
  dedicato (richiede libri illeggibili oltre 2 ore e posizione piatta): e' la stessa scrittura
  del ramo normale, provata.
- Il banco non ha un mercato annullato (VOIDED sempre vuota nel banco) ne' scommesse di altri
  bot sui mercati di Mike: quei rami sono provati solo in unita'.
- Tempi del replay non confrontabili (CPU al 100 %).
- Non ho toccato `engine.py` ne' `_sorveglia_posizione_di_conto`/canale ordini (altri delegati).
- `npm run build` non eseguito (divieto); l'app vede le modifiche solo dopo la build.

## 12. Decisioni per l'utente

1. **Stop giornaliero e P&L oggi di Mike comprendono gli ordini tuoi sulle sue partite.** Le
   righe `utente` sono chiusure della posizione di Mike: `realized_today` (che decide lo STOP
   giornaliero) ora e' il P&L del conto di quelle posizioni, non piu' solo quello degli ordini
   del bot. Esempio: Mike +2,10, tu −2,15 per chiudere -> il realizzato di oggi sale di −0,05, non
   di +2,10. Proposta: tenerlo (e' il numero vero della posizione). Alternativa: escludere le
   righe `utente` dagli aggregati dello stop (serve una migrazione di `get_mike_aggregates`),
   con due numeri diversi in pagina.
2. **Ordini di altri bot sui mercati di Mike** (es. lo scalper sulla 3,5): esclusi dal P&L della
   partita (restano nel loro conto) e contati in `ctx.pnl_conto.altri_bot_esclusi`. Proposta:
   tenerlo cosi'.
3. **Oltre il tetto (20 tentativi, ~4 ore) senza regolato di Betfair**: la partita si chiude
   con la stima del bot, dichiarata. Proposta: tenerlo (il runner aggiorna comunque
   `pnl_betfair` quando Betfair regola, e la Control Room lo mostra).

## 13. Da controllare dal vivo (live, dopo build e riavvio fatti dall'utente)

- Alla prossima partita live di Mike finita: in Attivita' `ATTESA DEL REGOLATO BETFAIR` (se
  Betfair tarda) poi `settled` con «P&L del conto Betfair …»; in `mike_events.ctx.pnl_conto`
  `chiamate_rest` = 2 (o poco piu').
- Se l'utente chiude dal sito: righe `mike_trades` con `role='utente'`, `signal_key`
  `utente-<bet>`, `closes_trade_id` = apertura di Mike; somma dei `pnl` della partita =
  `settled_pnl`; scheda «regolato … · conto Betfair (di cui Mike … · di cui utente …)».
- Control Room: la voce «Mike» della barra NON contiene gli ordini dell'utente (sono nel
  «Manuale · sito»); la posizione chiusa della partita si' (Mike + utente).
- Log del runner: le scritture `bot:mike` rifiutate continuano (vedi §8) finche' non si decide.
