# App: tabellone senza quote e riga tennis stantia (30/09/2026)

Delegato in worktree `agent-a8d3e9f678195f74e` (HEAD `15f0a33`; il brief diceva
base `55b0ce0`, il worktree e' su `15f0a33`, stesso `board_worker.py` del checkout
principale a meno dei fine riga). App viva: nessun processo avviato o fermato,
nessuna scrittura sul DB, nessun build. Patch: `APP_TABELLONE_E_RIGA_TENNIS.patch`
(la verifica `git apply --check --reverse` passa).

## DIFETTO 1: «Programma di oggi» con le quote su 1 partita su 47

### Causa vera (provata)

`Betfair/stream/board_worker.py:94-98` (HEAD), `_best`:
`return float(levels[0].price) if levels else None` dentro un `try/except -> None`.

Nel processo del runner calcio **flumine e' importato**, e `flumine/__init__.py`
sostituisce per tutto il processo `bettingresources.RunnerBookEX` con la sua classe
"pigra" `flumine.patching.EX`, che lascia i livelli come **dizionari**
`{'price': .., 'size': ..}` e non come `PriceSize`. `levels[0].price` solleva
`AttributeError`, l'`except` la inghiotte e ogni back/lay letto via REST diventa
`None`. Solo la riga coperta dallo scanner (che legge con
`scanner.best_price`, gia' tollerante alle due forme dal 17/09) aveva le quote.
E' lo stesso incidente scritto in `Betfair/safe_strategy/scanner.py:203-222`
(blackout delle quote del 17/09), non ancora corretto nel board.

Ipotesi del brief, tutte FALSE (provate):
- (a) `price_projection` serializzato male: no, `{'priceData': ['EX_BEST_OFFERS'],
  'exBestOffersOverrides': {}, 'virtualise': True, 'rolloverStakes': False}`; la
  risposta grezza (`lightweight=True`) ha `availableToBack/Lay` pieni.
- (b) client `lightweight=True`: no, `status`/`total_matched` erano valorizzati,
  quindi il libro era un oggetto.
- (c) .it vs .com: no, stesso client `build_client` (`locale="italy"`), prezzi pieni.

### Le prove (sola lettura, una sessione Betfair per sonda, poche chiamate)

| sonda | esito |
|---|---|
| `sonda_board_rest.py` (3 mercati, stessa chiamata, senza flumine) | prezzi pieni, `RunnerBookEX` con `PriceSize` |
| `sonda_board_intero.py` (giro intero del board, 47 mercati, senza flumine) | 47 righe, **0** senza quote |
| `sonda_board_canale.py` (push `board` del runner vivo, lettore 47331) | 47 righe, **46** senza quote (ltp presente) |
| `sonda_board_confronto.py` (stesso istante: board del runner + DB + REST) | le 46 non hanno odds nel feed (DB `odds: null`) -> vengono dal REST; il REST diretto ha i prezzi |
| `sonda_board_flumine.py` (giro REST **con `import flumine`**) | `RunnerBookEX in uso: flumine.patching`, livello `[{'price': 5.1, ...}]`, 47 righe, **47 senza quote** |
| `sonda_board_flumine.py senza` (controllo) | 47 righe, 0 senza quote |
| `sonda_board_flumine.py` **dopo la correzione** (flumine importato) | 47 righe, **0 senza quote** |

### Correzione (minima)

`board_worker._best` legge con `Betfair.safe_strategy.scanner.best_price` (modulo
puro, gia' in uso per lo stesso motivo): stessa semantica, tollera oggetto
`PriceSize` e dizionario. Nessun'altra riga cambiata. Vale anche per il board del
runner tennis (`tennis_runner.py:3170`, stesso worker).

### Test e falsificazione

`Betfair/stream/tests/test_board_quote_flumine_2026_09_30.py` (4 test): libri
`MarketBook` VERI di betfairlightweight costruiti dalla risposta grezza catturata
il 30/09; forma "runner" con `flumine.patching.EX` (monkeypatch, originali
ripristinati a fine test), forma `PriceSize`, giro `_poll_books_rest` con client
finto che restituisce `MarketBook` veri, livelli vuoti -> `None`.
- verdi: 4/4 (+ `test_scan_feed_2026_09_09.py`, `safe_strategy/tests/test_scanner.py`: 64 passati);
- **falsificazione** (`falsifica_board.py`, codice vecchio rimesso, ripristino in
  `finally`): **2 rossi** (i due con flumine), 2 verdi (forma PriceSize e vuoti,
  giustamente). File ripristinato byte per byte.

### Cosa deve fare l'utente

**Riavviare l'app** (il runner calcio legge il codice all'avvio). Nessuna migrazione.

## DIFETTO 2: riga «Swing · paper · 14:41 · 36117569 · LAY 1,21 · residuo 2,00»

### Da dove viene

- Fonte: RPC `get_tennis_bot_orders_today`
  (`migrations/tennis_bot_service_control_2026-09-17.sql:171-194`) su
  `tennis_live_orders`, filtro giorno `coalesce(o.placed_at, o.updated_at)` = oggi.
- Vista: `frontend/src/components/controlroom/useControlRoom.ts`, ramo "posizioni
  aperte dei quattro bot tennis" (~riga 2706), filtro `ordineTennisAperto` (riga
  3810) e ora `piazzataAt: o.placed_at ?? o.updated_at` (riga 2729).
- La riga (DB, sola lettura, `sonda_riga_tennis.py`): `tennis_live_orders.id = 46018`,
  `source tennis_swing`, `mode paper`, `event_id 36117569`, `market 1.262929640`,
  `side lay`, `price 1.21`, `size 2`, `size_matched 0`, **`size_remaining 2`**,
  **`status VOIDED`**, **`placed_at NULL`**, `settled_at NULL`,
  **`updated_at 2026-09-30T12:41:12Z`** (14:41 locali). Follow 36117569 `CLOSED`
  dal 28/09.

### Perche' porta l'ora 14:41

Non e' il `tennis-bot-service`: e' la **ripresa del runner tennis** all'avvio
(`guardie_tennis.ripresa_all_avvio` -> `tennis_db.chiudi_specchio_paper_orfano`,
`Betfair/stream/tennis_live/tennis_db.py:846-869`). Log `runner-tennis` 14:41:12:
«ripresa riuscita: 0 richieste stantie chiuse, specchio paper orfano chiuso
(**1 ordini**, 15 posizioni)». Quell'unico ordine e' il 46018: l'UPDATE scrive
`status = 'VOIDED', updated_at = now()` ma **lascia `size_remaining = 2`**. Quindi
la ripresa la riga l'ha toccata (il brief supponeva di no); «1 bot orfani marcati
'error'» e' un'altra cosa (`tennis_bot_control`).

### Perche' la Control Room la mostrava

1. `placed_at` nullo (ordine paper) -> la RPC la prende per `updated_at`, che la
   ripresa ha portato a oggi -> la riga entra negli "ordini di oggi".
2. `ordineTennisAperto` (e la gemella `tennisAncoraAMercato` in
   `lib/controlRoom.ts:541`) considerava aperto un ordine con `size_remaining > 0`
   **qualunque fosse lo stato**: un ordine `VOIDED` con residuo 2 era "a mercato".

Altre 34 righe identiche (paper, VOIDED, mai abbinate, residuo > 0) del 26/09
esistono gia' (`sonda_conteggio_migrazione.py`: 35 in tutto, 34 del 26/09 + 1 di
oggi): oggi non si vedono solo perche' la RPC le tiene fuori per giorno; al primo
riavvio che le toccasse riapparirebbero.

### Correzione (minima, nella vista)

`frontend/src/lib/controlRoom.ts`: nuova `residuoTennisSulBook(o)` (esportata) = il
residuo conta solo se lo stato NON e' terminale (`TERMINALI_FLUMINE` di
`lib/esitoAbbinamento.ts`, gli stessi di `esiti_ordini_canale.STATI_TERMINALI`);
usata da `tennisAncoraAMercato` (soldi di partita) e da `ordineTennisAperto`
(posizioni aperte). L'**abbinato** non regolato resta posizione aperta qualunque
sia lo stato (esposizione vera). Nessun import circolare (esitoAbbinamento importa
da controlRoom solo tipi).

Backend NON toccato: la ripresa fa gia' la cosa giusta (chiude l'ordine morto col
processo); il residuo lasciato a 2 e' un dettaglio di coerenza che la migrazione
facoltativa sotto sistema sui dati. Se si volesse anche nel codice di ripresa, il
suo UPDATE diventerebbe `status='VOIDED', size_remaining=0, updated_at=now()` (ma
PostgREST non puo' copiare `size_remaining` in `size_voided` riga per riga: servirebbe
una RPC). Non fatto: fuori dal minimo, e al prossimo riavvio l'UPDATE di oggi
toccherebbe solo righe paper ancora "vive" (nessuna al momento).

### Test e falsificazione

`useControlRoom.test.tsx`, blocco «30/09» (8 test, riga finta = la 46018 con le
stesse chiavi e valori del DB): VOIDED/LAPSED/CANCELLED/EXPIRED/EXECUTION_COMPLETE
con residuo e mai abbinati -> non compaiono; EXECUTABLE con residuo -> compare;
VOIDED con abbinato 0,5 -> compare; `marcaTennis` non la conta aperta.
- verdi: 8/8; `tsc -p tsconfig.app.json --noEmit`: 0 errori; vitest
  `src/components/controlroom` + `src/lib/controlRoom` + `src/lib/esitoAbbinamento`
  + `src/pages/ControlRoom`: **57 file, 1016 test verdi**.
- **falsificazione** (`falsifica_riga_tennis.py`, tolto il controllo sugli stati
  terminali): **6 rossi** (i "non compare" + marcaTennis), 2 verdi; direzione
  inversa (`falsifica_riga_tennis_inversa.py`, residuo sempre falso): **2 rossi**
  (i "resta"). File ripristinato byte per byte in entrambi i casi.

### Cosa deve fare l'utente

- Correzione della vista: serve `npm run build` in `frontend/` e ricaricare l'app
  (non fatto da me: vietato con l'app viva).
- Per togliere la riga **subito**, senza build: migrazione facoltativa
  `migrations/tennis_paper_voided_residuo_zero_2026-09-30.sql` (solo dati,
  idempotente, commentata, con SELECT di anteprima). Tocca solo righe PAPER dei 4
  bot tennis gia' `VOIDED`, non regolate, mai abbinate, con residuo > 0 (35 righe
  oggi, verificate): `size_voided += size_remaining, size_remaining = 0`. Mai
  righe live, nessuna cancellazione. Rilanciata non trova nulla.

## Cosa NON ho potuto verificare

- Il board del runner **vivo** dopo la correzione: serve il riavvio (l'ho provato
  su un processo mio con `import flumine`, stesso client e stessa chiamata: 47/47).
- La riga tennis sull'app vera dopo build/migrazione: nessun build, nessuna
  migrazione applicata (vincoli).
- Il board tennis (`event_type_id 2`): stessa funzione corretta, non sondato a parte.
- Altri punti del codice che leggono `.price` su libri REST in processi con flumine
  (fuori perimetro; lo scanner e i worker ordini sono gia' tolleranti, vedi
  `live_order_worker.py:1690`, `tennis_live_order_worker.py:704`).
- Suite Python completa e vitest completo non rilanciati (solo i file toccati e i
  vicini, per non caricare il PC con l'app viva).

## File

- modificati: `Betfair/stream/board_worker.py`, `frontend/src/lib/controlRoom.ts`,
  `frontend/src/components/controlroom/useControlRoom.ts`,
  `frontend/src/components/controlroom/useControlRoom.test.tsx`
- nuovi: `Betfair/stream/tests/test_board_quote_flumine_2026_09_30.py`,
  `migrations/tennis_paper_voided_residuo_zero_2026-09-30.sql`
- sonde e falsificazioni (sola lettura / ripristino garantito): `AUDIT_2026-09-30/sonda_*.py`,
  `falsifica_*.py`, `pytest_neutro.sh`, `ascii_mie_aggiunte.py`
- junction create nel worktree: `.venv`, `frontend/node_modules` (da togliere con
  `cmd /c rmdir` prima di `git worktree remove`).
