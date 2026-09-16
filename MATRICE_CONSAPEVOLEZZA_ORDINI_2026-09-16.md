# MATRICE DELLA CONSAPEVOLEZZA DELL'ORDINE — TUTTI I BOT (C.10)

> **Letto il 16/09/2026 fra le 09:50 e le 10:30 ora locale.** HEAD `dc0cc30`, working tree
> **sporco**: altri delegati stavano modificando in quel momento `Betfair/mike/service.py`,
> `Betfair/mike/tools/{banco,replay_registrazioni}.py`, `Betfair/omega/omega_service.py`,
> `Betfair/safe_strategy/{bot_service,engine,scanner,service}.py`,
> `Betfair/stream/{live_order_worker,runner,trading/submin}.py`,
> `Betfair/stream/{scalper/scalper_service,tennis_live/*}.py`, `desktop/main.js`, `frontend/src/`.
> Ogni `file:riga` vale **per il file di quel momento**: chi rilegge dopo un commit deve ricontrollare.
> **Sola lettura**: nessun file di codice toccato, nessun processo, nessun git.
> Risponde all'ordine dell'utente del 16/09 (memoria `feedback_consapevolezza_ordine_tutti_i_bot`)
> e alla voce **C.10** di `PIANO_CERTIFICAZIONE_DEFINITIVA_2026-09-16.md:276`.
> Riusa la mappa dei percorsi ordine di `PROGETTO_PAPER_VIA_FLUMINE_2026-09-16.md` §1.

---

## 0. IL CONTRATTO DEI DATI — che cosa un bot PUÒ sapere, prima ancora di volerlo

| fonte | campi che offre | `file:riga` |
|---|---|---|
| `PlaceResult` (risposta REST sincrona) | `ok`, `order_status`, `bet_id`, `size_matched`, `avg_price_matched`, `raw` | `Betfair/omega/omega_market.py:512-518` |
| — **NON offre** | **`size_remaining`**, **la size CHIESTA**, il `errorCode` (sepolto in `raw`) | idem |
| `list_current_orders()` (normalizzato snake_case) | `bet_id`, `status`, `size_matched`, `avg_price_matched`, **`size_remaining`**, `customer_order_ref` | `omega_market.py:879-896` |
| `list_cleared_orders()` | `size_settled`, `price`, `profit`, `bet_outcome` | `omega_market.py:899-932` |
| `order_state_by_bet_id()` | `found`, `size_matched`, `avg_price_matched`, `size_remaining` | `omega_market.py:837-876` |
| blotter flumine (`BetfairOrder`) | `size_matched`, `size_remaining`, `average_price_matched`, `status` (Enum!), `bet_id`, `simulated` | libreria |
| specchio DB `betfair_live_orders` | `size`, `size_matched`, `size_remaining`, `size_cancelled/lapsed/voided`, `average_price_matched`, `status`, `placed_at`, `matched_at`, `updated_at` | `migrations/betfair_live_order_queue.sql` |

**Il reperto strutturale.** Le tre tabelle dei bot che leggono lo scanner —
`omega_trades` (`migrations/omega_bot.sql:38-64`), `safe_strategy_trades`
(`migrations/safe_strategy_bot.sql:47-85`), `mike_trades` (`migrations/mike_bot.sql:79-111`) —
**non hanno nessuna colonna** per *abbinato*, *residuo*, *prezzo medio* o *ultimo aggiornamento da
Betfair*. Hanno `price`, `size`, `status`, `bet_id`, `placed_at`, `settled_at`, `meta` JSONB.
Alla conferma, `size` e `price` vengono **sovrascritti** con l'abbinato reale
(Omega `omega_service.py:1439`; Safe `execution.py:426-428` → `bot_service._reconcile_confirm:836`;
Mike `service.py:620`, `:1052`, `:2864`). Conseguenza:

- **il chiesto sparisce**, tranne dove qualcuno lo salva a mano: `meta.requested_size` (Omega,
  `omega_service.py:1505,1565,1629`), `meta.size_capped_from` (Safe/Mike, `execution.py:288`)
  — **ma persistito solo sul ramo coda flumine** (`execution.py:585-592`): su paper e su REST il
  `meta` locale di `place()` viene scartato e **la size chiesta si perde definitivamente** —,
  `meta.price_segnale` (solo le CHIUSURE, `execution.py:1096`). **Mike non lo salva mai.**
- **il residuo non esiste come numero** su nessuna delle tre tabelle (il «residuo» che si legge
  in Omega/Safe è `meta.hedge.residual_size`, cioè il residuo di **copertura**, non il non-abbinato);
- **non c'è un «quando l'ho saputo da Betfair»**: `placed_at` ha `DEFAULT now()` e non viene mai
  aggiornata; `updated_at` non esiste su nessuna delle tre.

I 5 bot che girano **dentro** flumine (scalper/sniper/theta, tennis ×4) hanno invece i campi veri
sull'oggetto ordine e li **scrivono** su `betfair_live_orders`
(`Betfair/stream/engine/live_trading_strategy.py:312-347`) e `tennis_live_orders`
(`Betfair/stream/tennis_live/tennis_live_order_worker.py:254-274,317-341`), dove chiesto,
abbinato, residuo, prezzo medio e stato convivono. **Quella tabella nessuna scheda bot la legge.**

---

## 1. LEGENDA

**Esiti (righe di ogni matrice):** 1 abbinato subito per intero · 2 parziale subito ·
3 appoggiato poi parziale · 4 appoggiato poi intero · 5 mai abbinato, scaduto/sospeso/chiuso ·
6 annullato dal bot · 7 rifiutato da Betfair · 8 esito ignoto (timeout/eccezione) ·
9 abbinato a prezzo migliore del chiesto · 10 mercato annullato/void.

**Verdetti:** ✓ gestito e visibile · ⚠ gestito ma non visibile (o visibile ma non gestito) ·
✗ NON gestito (il bot non sa, o non reagisce come da spec) · ⊘ non applicabile / non provocabile.

**Regola ereditata (vale ovunque, `feedback_consapevolezza_ordine_tutti_i_bot`):** mai «abbinato»
dedotto dal prezzo di mercato senza conferma di Betfair.

---

## 2. OMEGA (lay del punteggio esatto)

**Ordini emessi.** T1 apertura lay REST **FOK** (`omega_service.py:1590-1594` →
`omega_market.py:521`, `timeInForce=FILL_OR_KILL` a `:567`) · T2 apertura in coda flumine **paper**
(`:1541`, quasi-FOK software `paper_fill_ttl_s`) · T3 apertura in coda flumine **live** (`:1576`,
FOK vero `:1808-1811`) · T4 apertura paper legacy su snapshot (`omega_engine.py:280` `paper_fill`) ·
T5 green-up / chiusura / cash-out via `safe_strategy/execution.close_trade:1013` (layer condiviso
con Safe). **Place-and-trim: non usato** (`place_submin_live` esiste ma Omega non lo chiama) → ⊘.
Riconciliazione ogni ciclo, `poll_interval_s` **20 s** (`omega_config.py:35`).

| # | SA — campi e fonte | FA — spec vs codice | UI | ✓ |
|---|---|---|---|---|
| 1 | `res.ok`,`size_matched`,`avg_price_matched`,`order_status`,`bet_id` `:1620-1630`; latenza = REST sincrona | COST_OMEGA:216-233 · `_confirm_open_trade:1424` scrive `status=open`, `price=avg`, `size=matched` | `MatchTradesTable.tsx:316,321` quota + stake unico; **chiesto assente** | ⚠ |
| 2 | T1/T3: **impossibile**, Betfair uccide il residuo (`omega_market.py:557-566`). T2: `size_matched` dallo specchio `:1902-1903` | COST §6-bis:267-272 · TTL scaduto → `cancel` del residuo `:2032` + conferma **solo i € matchati** `:2063-2065` | nessun «chiesto vs abbinato» in nessuna scheda | T1/T3 ⊘ · T2 ⚠ |
| 3 | T2 soltanto (lo specchio aggiorna `size_matched` a ogni tick) | idem riga 2 | idem | T1/T3 ⊘ · T2 ⚠ |
| 4 | T2/T3 dallo specchio, terminale `matched>0` → `_flumine_confirm:1908` | conferma con prezzo medio REALE, `meta.fill='flumine_*'` | idem | ⚠ |
| 5 | `res.ok=False or size_matched<=0` `:1620`; T2 `terminal_lapsed` `:2026-2028`; T3 `live_fok_*` `:2142-2143` | `_leg_certain_failure` → riserva **cancellata** (`db.delete_trade`), gamba ritentabile col budget `LEG_RETRY_MAX` | la riga **sparisce**: resta solo l'attività `no_fill`/`error`. Il trader non vede l'ordine mai nato | ⚠ |
| 6 | solo PAPER: `_flumine_enqueue_cancel:1860`, esito riletto `:2047-2068`. **LIVE: nessun cancel di ordine** — `revoke_live_order_request:2201` revoca la RICHIESTA, non l'ordine | spec tace sull'annullo live | attività `flumine_cancel` | paper ⚠ · live ⊘ |
| 7 | `errorCode` **mai letto per decidere**: `omega_market.py:587-595` lo appiattisce in `ok=False`. `INVALID_PROFIT_RATIO`/`INSUFFICIENT_FUNDS`/`BET_TAKEN_OR_LAPSED` **indistinguibili** | spec tace · il codice consuma un tentativo e riprova identico | badge `ERRORE`; il motivo è `live_not_matched:<order_status>` | ✗ |
| 8 | `omega_market.py:583-585` solleva su `TIMEOUT`; `_place_one:1595-1619` lascia la riga `pending` + `meta.reconciling` | COST §6 · `reconcile_pending:2284` → `reconcile_decision` (`omega_engine.py:642-699`): parziale → `keep`, cleared senza size → `free`, grace `RECON_GRACE_S=120` `:625` | badge **IN VERIFICA SU BETFAIR** (`lib/tradeStatus.ts` `RECONCILING_META`) | ✓ |
| 9 | `avg_price_matched` letto `:1626` e scritto in `price` | corretto · ma il **prezzo chiesto dell'apertura non è conservato** (solo le chiusure hanno `meta.price_segnale`) | nessuno scorrimento visibile sull'apertura | ⚠ |
| 10 | `settle_open:2468` → `E.resolve_settlement` (`omega_engine.py:705-723`): void = `CLOSED` + tutti i runner in `{WINNER,LOSER,REMOVED,REMOVED_VACANT}` + **nessun WINNER** | **non controlla mai `marketStatus IN ('VOID','VOIDED')`** (Mike sì, `service.py:688`): il void è DEDOTTO. Mercato sparito → `_maybe_void_orphan:2399`, paper `void` dopo 48 h, **live mai void automatico** (alert) | stato `VOID` nella tabella | ⚠ |

**Copertura/green-up sul parziale — CORRETTO.** `_greenup_send:3922` → `close_trade:1013` →
`close_plan:953` → `net_exposures:692` → `exposures:673-683`, che legge `trade["size"]` e
`trade["price"]`, cioè l'**abbinato**. Le chiusure già fillate riducono il residuo
(`hedge_state:723-770`); una chiusura `pending` **blocca** un secondo cash-out (`:766`);
residuo non copribile → `_greenup_residual_dropped:3858` con stato dedicato.

---

## 3. SAFE STRATEGY — base · esatto · punta · tennis

Stesso codice per le quattro (`execution.py` + `bot_service.py`); il tennis cambia solo
parametri/stake (`migrations/safe_strategy_stake_per_strategia_2026-09-16.sql`) e i mercati.
**Ordini emessi.** T1 taker REST **FOK** (`execution.py:411-417`) · T2 **place-and-trim** submin
(`omega_market.py:672`, tre chiamate REST) · T3 coda flumine (`enqueue_place:556`; FOK in
**entrambe** le modalità `:632`, **ma `place_submin` senza FOK** `:609-616`) · T4 paper fill su
ladder a un livello (`:356`) · T5 chiusura / green-up / cash-out / hedge (`close_trade:1013`).
Riconciliazione ogni ciclo (**2 s**): `poll_flumine:645`, `reconcile_pending:675`,
`_reconcile_by_bet_id:811`, `settle_open:889`. **Le 4 strategie condividono lo stesso percorso
d'ordine**: `strategy` è solo una colonna (`migrations/safe_strategy_bot.sql:52-53`).
`Betfair/order_exec.py` **non** è usato da Safe (appartiene al percorso watchlist).

| # | SA | FA | UI | ✓ |
|---|---|---|---|---|
| 1 | `res.ok`,`size_matched`,`avg_price_matched`,`bet_id` `execution.py:424-431`; + `meta.esecuzione` con `t4/t5/betfair_ms/price_richiesto/price_medio/scorrimento_tick` `:433-441` | COST_SAFE §3-4 · riga `open` con size = matched (`bot_service.py:3407`) | `SafeTradesTable.tsx:529` stake unico; `meta.esecuzione` è letto **solo** dalla Control Room e **solo per i TEMPI** (`lib/controlRoomCatena.ts:94-139`): `price_medio` e `scorrimento_tick` non sono renderizzati da nessun componente | ⚠ |
| 2 | **PAPER**: parziale = **errore** `paper_fok_parziale` `:368-370` (nessuna posizione). **LIVE T1**: ⊘ per FOK. **LIVE T2 (submin): SÌ, caso reale** — `omega_market.py:793-799` ritira il residuo (`_submin_ritira(obbligatorio=True)`) e torna `ok=True` con `matched < target` | il bot accetta `open` con `size=matched` `:427-431`; l'hedge si dimensiona su quella (corretto) | **nessuna riga dice «chiesti 2,00 / abbinati 0,80»**; l'unico posto in tutta la UI con chiesto-vs-abbinato è il tooltip della gamba di CHIUSURA cappata (`SafeTradesTable.tsx:737-739`) | ⚠ |
| 3-4 | Safe **non appoggia mai** su T1/T3 (FOK ovunque). **Due eccezioni**: (a) `place_submin` accodato va **senza FOK** (`execution.py:609-616`) → può restare a riposo; (b) se Betfair mostrasse un parziale con residuo vivo, `reconcile_decision:504` e `_reconcile_by_bet_id:833` tornano **`keep`**: la riga resta `pending` **finché il residuo non muore**, contando nell'esposizione e bloccando il segnale | spec tace su entrambi | il resting non è distinguibile: `SafeTradesTable.tsx:224` chiama `statusMeta(t.status)` **senza** passare `resting`, quindi `RESTING_META` («APPOGGIATA · NON ABBINATA», `lib/tradeStatus.ts:106-111`) **non compare mai nel live** — appare solo nello Storico (`DayDetail.tsx:50`) | T1/T3 ⊘ · submin ✗ |
| 5 | `not res.ok or size_matched<=0` → `live_not_matched:<order_status>` `:424-426`; submin senza controparte → `ok=False, order_status='LAPSED'` (`omega_market.py:800-803`) | riga `status='error'` terminale; budget `place_max_attempts` 3 con backoff 5/15/60/300 s (COST §2:139-149, H-21) | badge `ERRORE` / `USCITA FALLITA` (`SafeTradesTable.tsx:148-228`) | ✓ |
| 6 | **nessun cancel**: Safe non accoda `action='cancel'` e non chiama `cancelOrders` (l'unico `cancelOrders` è **interno** al place-and-trim) | spec tace | — | ⊘ |
| 7 | come Omega: `res.raw` (dove vive `errorCode`) **non è mai ispezionato**. **Aggravante**: un rifiuto del place-and-trim **solleva** (`omega_market.py:742,789`) → cade in `_reconciling:447` e la riga resta **`pending`** anche se il rifiuto è CERTO | spec tace · un rifiuto certo viene trattato come esito ignoto | badge `IN VERIFICA SU BETFAIR` su un ordine che non esiste | ✗ |
| 8 | `_reconciling:447-469` riga `pending` + `meta.reason='place_exception_reconciling'` + attività `place_exception`; l'indice unico parziale `uq_safe_trades_signal` impedisce il ripiazzamento | risolve `reconcile_pending:675` e prima ancora `_reconcile_by_bet_id:811` (chiave più forte), che su `matched=0 & remaining=0` chiude `error` invece di lasciare pending per sempre; `free` su riga in riconciliazione → `_terminal_error`, mai `delete` muto (C-03) | `IN VERIFICA SU BETFAIR` | ✓ |
| 9 | `medio = res.avg_price_matched or price` `:427`; `scorrimento_tick` calcolato `:437` (e `:378` in paper) | corretto | **calcolato e salvato, mai mostrato** | ⚠ |
| 10 | `settle_open:889` → `execution.settle_position:1358`: `snap.voided or winner_selection_id is None` → tutte le gambe `void`, pnl 0. `snap.voided` viene dallo **stesso** `E.resolve_settlement` di Omega (`omega_market.py:318`) → stessa riserva della riga 10 di Omega. Mercato sparito → `_market_missing:996` dopo 3 letture KO | COST §4.3:353 dichiara lo **stato** `void`, non la **regola** di rilevazione | stato `VOID` | ⚠ |

**Copertura/green-up sul parziale — CORRETTO** (stesso layer di Omega). Chiusura parzialmente
abbinata: l'apertura **resta `open`** con `hedged_size`/`residual_size` e passa a `hedged` solo a
residuo < `HEDGE_EPS` (`execution.py:743-749`, `apply_hedge_state:836`); ritentativo su
`residual_retry_s` 20 s × `residual_max_attempts` 15, poi backoff lungo, **mai abbandono**
(COST §3.6:272-274); budget della chiusura intera `exit_max_retries` 3 (`bot_service.py:3164`).
`remaining_liability:783` → **IGNOTO = PIENO**: copertura in volo = rischio pieno.
Una chiusura `pending` **blocca** ogni nuovo cash-out (`execution.py:1046-1048`).

**Dove la spec tace, per Safe.** `SPEC_STRATEGIA_S.md` (183 righe) e `SAFE_STRATEGY_DOSSIER.md`
(342 righe) **non contengono nessuna** delle parole «parziale», «residuo», «abbinato»,
«annullato», «rifiutato», «void»: la fonte di verità strategica **non copre nessuno** dei dieci
esiti. La Costituzione copre §4.2 (copertura parziale), §3.6 (residuo), §2:139-149 (budget dei
rifiuti), §4.3:353 (vocabolario del void); **non dichiara** che il parziale live in APERTURA
viene accettato come posizione (`execution.py:424-431`, deciso solo nei commenti del codice), né
che `size`/`price` vengono sovrascritti con l'abbinato, né il trattamento di `LAPSED`.
⚠️ **Costituzione disallineata**: `COSTITUZIONE_SAFE_STRATEGY.md:367-369` dice ancora «il paper
riempie istantaneamente al best price», mentre dal 12/09 il paper uccide il parziale
(`execution.py:361-370`). E `migrations/safe_strategy_paper_live_2026-09-13.sql` è marcata
🔴 **DA APPLICARE** (`COSTITUZIONE:64`): finché non lo è, `mode` non entra nella chiave di
idempotenza.

---

## 4. MIKE

**Ordini emessi.** Due sole strade verso Betfair: (a) **tutti i taker** via
`execute_place:481` → `execution.place:234` → `place_order_live` FOK **o** `place_submin_live`;
(b) **la lay appoggiata** via `_piazza_resting_live:900` → `place_order_live(fill_or_kill=False)`
`:954-958`. Ruoli: `under_entry`, `under_last` (PERSIST), `under_second`, `reentry`,
`under_green` (resting o taker), `ko_green`, `over_cover`, `under_close`/`over_close`/
`reentry_green`, `manual_close`. `_segui_resting_live:1246` ogni ciclo (~20 s, nessun throttle);
`_reconcile_unknown:2798` con throttle `max(5 s, settle_confirm_s)` per partita.

| # | SA | FA | UI | ✓ |
|---|---|---|---|---|
| 1 | taker: `out.status/size/price/bet_id` `:615-622`. resting: `res.bet_id` `:979` (salvato **sempre**, `:1014-1018`), `size_matched` `:980`, `ok` `:981`, `avg_price_matched` `:1037` | COST §4 inv.1 (`:241-243`): «esposizioni SOLO dai fill, mai dalla size chiesta» — **rispettato**: `ENG.exposure:541-555` somma solo `leg.matched` | `MikeMatchCard.tsx:868` netto abbinato, `:889` **prezzo medio reale** (`lib/mike.ts:1025-1029`) | ✓ |
| 2 | taker paper: parziale **ucciso** (`execution.py:368-370`). taker live: FOK ⊘, **submin sì** → `out.size = matched` `:616`. resting: `size_matched` a ogni giro `:1279` | COST §4 inv.1/3/8 (`:241-253`) · `ENG:1913-1921` «green parziale: residuo aperto» → torna in `PRE_OPEN`; riprezzo del **solo residuo** `ENG:2653-2676` | `MikeMatchCard.tsx:856-878` **residuo separato per direzione** («+X in ingresso sul book», «X di chiusura appoggiata»); `lib/mike.ts:1050-1052` **`SUL BOOK (parziale)`** | ✓ |
| 3 | `_segui_resting_live:1279-1288`: legge `size_matched` e `avg_price_matched`. **NON legge `size_remaining`** (le uniche due occorrenze in `Betfair/mike/` sono un alias `:1087` e una docstring `:1131`): il residuo vivo è **dedotto** da `leg.size - leg.matched` | `leg.status` resta `pending` finché `matched >= leg.size` `:1285`; il residuo si ri-appoggia (`ENG:333,345`) | riquadro «Ordini sul book» `MikeMatchCard.tsx:919-952` con `€ residuo @ quota` e `· abbinati …` | ⚠ |
| 4 | idem, `matched >= leg.size` → `open` `:1285` | corretto | idem | ✓ |
| 5 | l'ordine **sparisce** da `listCurrentOrders`; `_segui_resting_live:1263-1271` non distingue abbinato-del-tutto / annullato / mai arrivato → `pending_reconcile`; `LAPSED` **non è mai confrontato per nome** | COST §5 (`:283`) e §4 inv.11 · `_reconcile_unknown:2798` → `reconcile_decision` (`execution.py:482-522`) decide | badge `IN VERIFICA`; condizioni 16/17 della tabella §15 sono `⊗` (mai osservate) | ⚠ |
| 6 | **✗ NON ESISTE.** `_RealMarket:114-171` non espone `cancel_orders`. Tutti i «cancel» di Mike (`:2446-2454`, `_request_cancel:1399`, `_request_flatten:1470`, `_mark_trade_cancelled:2894`) cambiano **solo** lo stato in DB | COST parla di «annulla ordini», «residuo annullato» (`:138,284,349`) come di un'operazione di rete: **la Costituzione dichiara una cosa che il codice non fa**, e non dichiara la lacuna | il trader vede «annullato» su un ordine che su Betfair è ancora VIVO | ✗ |
| 7 | `place_rifiutato` esiste in **un solo punto**: `:1000-1005`, solo per la lay appoggiata live con `ok=False` e **nessuna traccia**. `ok=False` **con** `bet_id` o `matched>0` → riconciliazione `:981-993`. Sui taker non esiste `place_rifiutato` | COST **tace** su questo caso (fix del 15/09 mai entrato in Costituzione) · la riga viene chiusa apposta «così il motore può riproporre» `:994-996` | `lib/tradeStatus.ts:438` `place_rifiutato → RIFIUTATO DA BETFAIR`; `:437` `place_saltato → DUPLICATO EVITATO` | ⚠ |
| 8 | taker: `_reconciling` → `STATUS_RECONCILE` + attività `reconcile_pending` critica `:629-640`. resting: `:959-968`, riga riservata resta `pending`. `_trade_unknown_outcome:2649` fail-closed, il TTL `_PENDING_STALE_S=120` non la tocca | COST §4 inv.11 (`:263-268`): «mai `cancelled`/`error` per TTL», liability al **peggior caso** | `IN VERIFICA` | ✓ |
| 9 | `avg_price_matched` letto `:1037`,`:1283`; media ponderata in UI | corretto | `MikeMatchCard.tsx:889` prezzo medio | ✓ |
| 10 | `market_voided:692-711`: `status ∈ ('VOID','VOIDED')` **oppure** `CLOSED` senza WINNER con runner in `('REMOVED','REMOVED_VACANT','VOID','VOIDED')`; `INACTIVE` **non** è void. Void **per mercato** (`settle_plan:714-735`) | COST §4 inv.13 · gambe pianificate mai piazzate regolate a zero `:3056-3084` | stato `VOID` | ✓ |

**Il buco che vale soldi — riproposizione senza freno del green-up taker.** In `PRE_OPEN` il ramo
taker (`ENG:1894-1902`) ricalcola lo stesso piano e riemette lo stesso `_place` a ogni ciclo se
l'ordine non si abbina (`ENG:1909-1912`). Su questo ramo **non c'è nessun contatore**:
`close_max_attempts`/`ctx.attempts` proteggono `PRE_GREEN_PENDING` (`ENG:1923-1933`),
`LIVE_CLOSING` (`ENG:2648-2676`), copertura (`ENG:2492-2523`) e re-ingresso (`ENG:2817-2827`),
**non `PRE_OPEN`**. E il freno `_gia_appoggiata:859-897` guarda le righe `status='pending'`: dopo
un `no_fill`/rifiuto la riga è `error`/`cancelled` e il freno si abbassa. È la **quarta**
incarnazione del difetto del 15/09.
**Costituzione disallineata**: `COST:1793,1815` cita `service.py:736` e `:783` per
`_live_exit_override`/`_resting_filled`, che oggi stanno a `:788` e `:1292`, e dichiara
`pre_exit_mode` forzato a `taker` in live mentre dal 14/09 è l'opposto (`:802-813`).

---

## 5. SCALPER CALCIO — scalper · sniper · theta (dentro flumine)

Tutti e tre `market.place_order(LimitOrder(..., persistence_type='LAPSE'|'PERSIST'))`:
`scalper_bot.py:2064-2066`, `sniper_bot.py:772-775`, theta eredita da sniper
(`theta_bot.py:1118,1200` PERSIST pre-match). **`time_in_force`: assente in tutti** → sono
ordini **appoggiati per disegno**, il caso «parziale» è la norma, non l'eccezione.
Consapevolezza per **polling del blotter dentro `process_market_book`** (~50-200 ms):
`scalper_bot.py:575`, `sniper_bot.py:330`, `theta_bot.py:694`. **Nessuno implementa
`process_orders`.** Specchio DB `betfair_live_orders` via `_order_mirror_loop`
(`scalper_session.py:330-353`, tick **1 s**).

| # | SA | FA | UI | ✓ |
|---|---|---|---|---|
| 1 | `order.size_matched` (`scalper_bot.py:1206,1532,1710`), `average_price_matched` `:1209` | `_open_lock:1719-1750` dimensiona l'hedge sul **matched reale** con `floor_min=False` (commento `:1748-1749`: forzare il minimo su un fill parziale creerebbe una posizione direzionale) | `ScalperPanel.tsx:530-545` **solo contatori aggregati** (`Ordini`, `Cicli`, `Catture`): nessuna lista ordini, nessuna size, nessuno stato | ⚠ |
| 2 | idem, a ogni tick | residuo entry **cancellato subito** al primo fill `:1532-1536`; gamba opposta ridotta col **cancel PARZIALE** `market.cancel_order(close, size_reduction=…)` `:1224` (unico `size_reduction` fuori dal worker manuale); micro-residuo ≤ 0,25 € **accettato e contabilizzato** `:1860-1873` (BIBBIA_SCALPER_CALCIO:113,175) | idem | ⚠ |
| 3 | idem | sniper `:436-467`: close morta con matched e `\|nw−nl\| > max(0.02, residual+0.02)` → `sniper_close_partial` WARN + `_begin_flatten`. theta idem su due rami `:904-914`, `:1249-1259` | idem | ⚠ |
| 4 | idem | ciclo chiuso, lock contabilizzato | idem | ⚠ |
| 5 | `_has_live:2269-2277` (`status ∈ {EXECUTABLE,PENDING}` **e** `size_remaining > ε`) — **mai la stringa `LAPSED`**; `_handle_cancelling:1700-1717`; sospensione gol → `risk_semaphore.notice_suspension` `:531-532` | BIBBIA:444-448 «l'ordine LAPSE cade in sospensione (gol) e va ripiazzato» | invisibile | ⚠ |
| 6 | `_cancel_if_live:2284-2290` legge `status` e `size_remaining` prima di `market.cancel_order`; sweep d'emergenza `scalper_session.py:165-200` + alert `live_alerts:286-295` | corretto | invisibile | ⚠ |
| 7 | **✗** `order.violation_reason` **mai letto**; `place_order` **senza `try/except`** (`scalper_bot.py:2066`, `sniper_bot.py:775`): un rifiuto dei trading-control torna `False` in silenzio e l'ordine resta VIOLATION non letto | DOSSIER §7 cita il bug degli «ordini orfani» (`SCALPER_BOT_DOSSIER.md:238-242`) ma non il rifiuto | invisibile | ✗ |
| 8 | in simulazione non esiste; in live l'eccezione non è catturata | spec tace | invisibile | ✗ |
| 9 | `average_price_matched` letto e usato in `_presize_close:1209` per ricalcolare la size ideale | corretto | invisibile | ⚠ |
| 10 | **✗** nessun bot legge `size_voided` né `marketDefinition.status=='VOID'`; `process_closed_market:826` somma solo `order.simulated.profit` | spec tace | invisibile | ✗ |

---

## 6. TENNIS SCALPER

Gemello del calcio (`tennis_scalper_bot.py:2096-2098`, LAPSE, nessun `time_in_force`).
Legge `size_matched` `:841,1291,1569,1742,1989`, `average_price_matched` `:1992`,
`size_remaining` `:2292,2302`, `status` con `_LIVE_ORDER_STATUSES` (**include
PENDING/CANCELLING/UPDATING/REPLACING**, fix audit #5 `:2285-2292`). Specchio
`tennis_live_orders` via `_reconcile_bots` (`tennis_live_order_worker.py:821-863`, 1 Hz).

Verdetti identici a §5 con **tre differenze**:
- riga 2: **`_presize_close` ASSENTE** (nessun `size_reduction`): su fill parziali asimmetrici la
  gamba opposta non viene ridotta come nel calcio → ⚠ più pesante;
- riga 5: **nessun `risk_semaphore`/`notice_suspension`** nel tennis → sospensione non gestita → ✗;
- righe 1-10 UI: `TennisBotPanel.tsx:385-399` mostra **solo tile aggregate**, nessuna vista ordine → ⚠/✗.
- `BIBBIA_SCALPER_TENNIS.md` è **quasi muta**: un solo cenno a `:36` («residuo incondizionato,
  stop parziali»). Nessun § su parziali, residuo, annullamento.

---

## 7. TENNIS PRO · FLB · SWING

`LimitOrder(..., persistence_type='LAPSE')`, nessun `time_in_force`:
`tennis_pro_bot.py:326-329`, `tennis_flb_bot.py:128-129`, `tennis_swing_bot.py:135-136`.
Tutti e tre leggono `size_matched` + `average_price_matched`
(`pro:299-300`, `flb:103-104`, `swing:123-124`) e dimensionano l'uscita sul **matched**
(`pro._close_at:342-359`, `flb._green:141-172`, `swing._close:140-148`). `place_order` in
`try/except` con solo `logger.debug` (`pro:330-332`, `flb:130-132`, `swing:136`).

| # | pro | flb | swing | ✓ |
|---|---|---|---|---|
| 1-2 | hedge su matched; stato CLOSING sorvegliato `:694-745` (hedge non riempito entro `close_retry_s` → cancel + re-hedge) | hedge su matched; residuo entry LAY **cancellato** `:314` | hedge su matched; `closing` esce **solo a posizione flat** (`\|nw−nl\|<0,01`) `:197-224` | ⚠ |
| 3 | **✗ non legge `size_remaining` né `order.status`**: la «pienezza» dell'hedge è dedotta dal netto | **✓** `rem = go.size_remaining` `:273`; ordine morto con residuo → **ripiazza `rem`** `:280-287` (`green_replaced`) | **✗** come pro | pro/swing ✗ · flb ✓ |
| 4 | ok | ok | ok | ⚠ |
| 5 | `entry_timeout:598-610` → cancel | `entry_timeout:252-259`; `_order_alive:171-180` | `:234-241` a 40 s | ⚠ |
| 6 | `_cancel:334-340` | `:133-139` | `:153-156` | ⚠ |
| 7 | `violation_reason` mai letto; errore inghiottito in `debug` | idem | idem | ✗ |
| 8 | spec tace | spec tace | spec tace | ✗ |
| 9 | `average_price_matched` letto | idem | idem | ⚠ |
| 10 | void mai gestito | idem | idem | ✗ |

**UI: nessuna delle tre ha una vista ordine.** Gli ordini si vedono solo aprendo il terminale
ladder dello stesso mercato (`TerminalPositionsRail.tsx`). `TENNIS_BOT_DOSSIER.md` **tace** sui
parziali (unico cenno `:365`, bug aperto `size_matched=0` sul taker in simulazione).

---

## 8. (a) TOP-15 DELLE CELLE ✗/⚠ PER RISCHIO SUI SOLDI

| # | bot · cella | scenario concreto | `file:riga` |
|---:|---|---|---|
| 1 | **Mike · 6 (annullo)** ✗ | ordine 5 € @2,14 lay appoggiato; il bot decide «annulla», scrive `cancelled` in DB — su Betfair l'ordine **è vivo**, si abbina 4′ dopo: posizione reale che nessuno contabilizza, e il motore nel frattempo rientra → posizione doppia | `service.py:114-171` (niente `cancel_orders`), `:2894-2909` |
| 2 | **Mike · green-up taker in `PRE_OPEN`** ✗ | uscita 10 € @1,62 che non si abbina: ogni ciclo il motore riemette lo stesso ordine, senza contatore e senza freno (`_gia_appoggiata` guarda le `pending`, ma la riga è già `error`) | `engine.py:1894-1912`; freno `service.py:859-897` |
| 3 | **Safe · 7 (rifiuto submin)** ✗ | place-and-trim 0,80 € rifiutato al parcheggio → **eccezione** → riga `pending` «IN VERIFICA» su un ordine **che non esiste**: il segnale resta bloccato e la liability è contata piena | `omega_market.py:742,789` → `execution.py:420-421,447` |
| 4 | **tutti · 7 (errorCode)** ✗ | `INSUFFICIENT_FUNDS` e `INVALID_PROFIT_RATIO` arrivano come `ok=False` generico: il bot ritenta identico fino a esaurire il budget invece di fermarsi (fondi) o riprezzare (ratio) | `omega_market.py:587-595`; nessun consumatore |
| 5 | **UI · il dato mancante diventa zero** ✗ | `size_matched ?? 0` → un ordine pieno con esito non ancora scritto compare come **«Non abbinato €0,00»** e `placedOrderState` lo classifica `unmatched`; nel rail del terminale `average_price_matched \|\| price` **sostituisce in silenzio il prezzo medio assente col prezzo chiesto**, e `size_matched.toFixed` è senza guardia | `PlacedOrdersPanel.tsx:38,64`, `lib/betfair.ts:229-232`; `TerminalPositionsRail.tsx:203,230` |
| 6 | **UI · Omega/Safe · resting** ⚠ | un ordine solo **appoggiato** appare nel live come `APERTO` (azzurro), identico a una posizione abbinata; `RESTING_META` esiste ma non viene passata | `SafeTradesTable.tsx:224`, `MatchTradesTable.tsx:102` vs `lib/tradeStatus.ts:99-111` |
| 7 | **Safe · 3-4 (submin accodato)** ✗ | `place_submin` sulla coda va **senza FOK**: un ordine sotto-minimo può restare vivo sul book e abbinarsi più tardi, fuori da ogni riconciliazione del bot | `execution.py:609-616` |
| 8 | **scalper/sniper/theta · 7-8** ✗ | `place_order` senza `try/except`: un rifiuto dei trading-control torna `False`, il bot crede di aver piazzato la gamba di copertura e resta **scoperto** | `scalper_bot.py:2066`, `sniper_bot.py:775` |
| 9 | **tennis pro/swing · 3** ✗ | hedge maker riempito a metà: il bot non legge `size_remaining` né `status` e deduce dal netto — un hedge morto con residuo e un hedge parzialmente vivo gli sembrano uguali | `tennis_pro_bot.py:299-300`, `tennis_swing_bot.py:123-124` |
| 10 | **Omega · 5** ⚠ | ordine mai abbinato: `_leg_certain_failure` **cancella la riga** (`delete_trade`) — il trader non trova traccia dell'ordine tentato se non scorrendo l'attività | `omega_service.py:1621-1624` |
| 11 | **tutti · «ultimo aggiornamento da Betfair»** ✗ | `matched_at`/`updated_at` esistono su `betfair_live_orders` ma **nessun componente li renderizza**: il trader non sa se «abbinato 5,00» è di 2 s o di 9 minuti fa | `lib/liveOrders.ts:93-95`, nessun consumatore |
| 12 | **Safe · 3 (parziale con residuo vivo)** ⚠ | ordine 5 € @2,40, abbinati 2 € e 3 € ancora sul book: `reconcile_decision` torna **`keep`** e la riga resta `pending` **finché il residuo non muore** — esposizione contata, segnale bloccato, nessuna decisione | `execution.py:504`, `bot_service.py:833` |
| 13 | **Safe/Omega/Mike · la size chiesta si perde** ⚠ | sul percorso REST e paper il `meta` locale di `place()` (dove vive `size_capped_from`) **viene scartato**: dopo la conferma nessuno sa più quanto era stato chiesto, e la UI non può mostrare «chiesto vs abbinato» nemmeno volendo | `execution.py:288` vs persistenza solo a `:585-592` |
| 14 | **tennis_scalper · 2** ⚠ | fill parziali asimmetrici sulle due gambe: manca il `_presize_close` con `size_reduction` che il gemello calcio ha → la gamba opposta resta sovradimensionata | `scalper_bot.py:1188-1235` assente in `tennis_scalper_bot.py` |
| 15 | **Mike · 3 (`size_remaining`)** ⚠ | il residuo vivo è **dedotto** da `leg.size − leg.matched`: se un fill arriva fra due letture, o se Betfair riduce l'ordine, il numero è un'ipotesi, non un fatto | `service.py:1279-1288` (le uniche `size_remaining` in `Betfair/mike/` sono `:1087` alias e `:1131` docstring) |

---

## 8. (b) COME SI PROVOCA OGNI CELLA NEL REPLAY FLUMINE

Banco comune: `Betfair/stream/backtest/banco_comune.py` (`MercatoFlumine:306`,
`MotoreReplay:606`); scenari Mike: `Betfair/mike/tools/replay_registrazioni.py:99-141`.

| esito | come si provoca | leva |
|---|---|---|
| 1 intero | registrazione con ladder capiente al best | scenario `base` |
| 2 parziale subito | ordine più grande della size al best: flumine abbina il livello e col **FOK vero** uccide il resto (`simulatedorder.py:126-137,151-175`) | size > `available_to_back/lay` |
| 3 appoggiato poi parziale | `fill_or_kill=False` + `_piq` = coda davanti a noi al piazzamento, consumata dal volume **realmente scambiato** (`simulatedorder.py:230-236`, `:457-496`) | scegliere un prezzo con `_piq` alto e volume scambiato basso nella finestra |
| 4 appoggiato poi intero | stesso prezzo con volume scambiato abbondante | registrazione COMPLETE |
| 5 mai abbinato / sospeso | prezzo fuori dal book, oppure sospensione presa **dal raw** (`marketDefinition.status=SUSPENDED` al gol) | registrazione con gol |
| 6 annullato dal bot | `market.cancel_order(...)` dei bot flumine. **Per Mike/Omega/Safe non è provocabile: il percorso non esiste** (⊘) | — |
| 7 rifiutato da Betfair | **parzialmente ⊘**: flumine rifiuta solo per i propri `trading_controls` (`Transaction.place_order` → `False`, `banco_comune.py:394-405`). **`INVALID_PROFIT_RATIO` e il minimo .it NON sono riprodotti** (`banco_comune.py:57-59`): niente place-and-trim nel banco | `cliente_simulato()` con tetti stretti |
| 8 esito ignoto | `MercatoFlumine.guasti['place_exception'] = N` (`banco_comune.py:357-358`); già cablato in Mike come scenario `esiti-ignoti`, `QUANTI_GUASTI=3` | `replay_registrazioni.py:137-141` |
| 9 prezzo migliore | il book si muove a favore durante `simulated_delay` (`place_latency + betDelay`): il banco **riproduce il bet delay** facendo scorrere il tempo di mercato (`banco_comune.py:418-433`) | registrazione in-play |
| 10 mercato void | **⊘ oggi**: `MercatoFlumine.read_book` torna `None` (`banco_comune.py:511-517`) e lo stato finale arriva da `process_closed_market`. Serve una registrazione che contenga davvero un mercato annullato, oppure un `marketDefinition` sintetico | — |

**Limiti dichiarati del banco che pesano su questa matrice** (`banco_comune.py:37-84`):
nessun minimo di giurisdizione → **place-and-trim non provocabile**; nessun errore di rete se non
iniettato; nessun tetto di scanner; stop giornaliero e tetto partite non mordono (il banco gira su
UN evento); un file raw per volta. **Omega, Safe calcio e Safe tennis non hanno ancora un replay**
(`PIANO_...:§1`): il replay esiste solo per Mike.

---

## 8. (c) I CAMPI MINIMI CHE OGNI RIGA DI TRADE DOVREBBE PORTARE

| campo | oggi ce l'ha | dove manca |
|---|---|---|
| **size chiesta** | `betfair_live_orders.size`, `tennis_live_orders.size` | `omega_trades` (solo `meta.requested_size`), `safe_strategy_trades` (solo `meta.size_capped_from`, e solo se cappata), **`mike_trades` mai** |
| **size abbinata** | `betfair_live_orders.size_matched`, `tennis_live_orders.size_matched` | le tre tabelle dei bot: è la **stessa** colonna `size`, sovrascritta |
| **size residua** | `betfair_live_orders.size_remaining`, `tennis_live_orders.size_remaining` | **tutte e tre** (il `residual_size` di Omega/Safe è il residuo di copertura, non dell'ordine) |
| **prezzo medio abbinato** | `betfair_live_orders.average_price_matched`, `tennis_live_orders.average_price_matched` | le tre: è la **stessa** colonna `price`, sovrascritta. In UI lo mostra **solo Mike** (`lib/mike.ts:1025-1029`) |
| **stato dell'ordine** (parole di Betfair) | `betfair_live_orders.status`, `tennis_live_orders.status` | le tre: `status` è lo stato della **riga** (`pending/open/hedged/...`), non dell'ordine; quello vero vive in `meta.order_status` (Omega) o non esiste |
| **ultimo aggiornamento da Betfair** | `betfair_live_orders.updated_at`/`matched_at` (scritti, **mai renderizzati**) | `tennis_live_orders` (nessun timestamp nel payload); **tutte e tre** le tabelle dei bot |
| size cancelled / lapsed / voided | `betfair_live_orders`, `tennis_live_orders` | le tre |

Fatto bene e da non perdere: `lib/format.ts:44-54` — `fmtMoney(null) → '—'`, con il commento
«mai "0,00 €": un dato assente non è uno zero». La regola c'è; i tre punti che la violano sono ai
numeri 5 e 12 della TOP-15.

---

## 9. NOTE DI METODO

- Tutto quanto sopra è **lettura di codice**, non osservazione: nessuna cella è stata provocata.
  La sezione (b) dice come si provoca; è il lavoro di C.6.
- Dove la spec tace l'ho scritto. **Mike** (`COSTITUZIONE_MIKE.md`): dice bene i parziali
  (§4 inv. 1/3/8, righe 241-253) e l'esito ignoto (§4 inv. 11, righe 263-268), **tace** su
  l'annullo REALE su Betfair (che il codice non sa fare), sull'ordine rifiutato, su un freno alle
  riproposizioni taker e sulle colonne chiesto/abbinato; ed è **disallineata** su
  `pre_exit_mode` (`:1793`). **Safe**: `SPEC_STRATEGIA_S.md` e `SAFE_STRATEGY_DOSSIER.md` non
  contengono nessuna delle parole chiave; la Costituzione tace sul parziale live accettato in
  apertura, sul submin accodato senza FOK e su `LAPSED`, ed è disallineata a `:367-369`.
  **Omega**: `COSTITUZIONE_OMEGA.md` dice bene FOK e TTL (§6, §6-bis), tace su annullo live e
  `errorCode`. **Scalper/tennis**: `BIBBIA_SCALPER_CALCIO.md` è l'unica ricca (`:113,175,444-448,
  668-691`); `BIBBIA_SCALPER_TENNIS.md` ha un solo cenno (`:36`); `TENNIS_BOT_DOSSIER.md` e
  `SCALPER_CALCIO_DOSSIER.md` **taciono del tutto** (zero occorrenze di parziale/residuo/annullo).
- **Nessuna proposta di modifica di strategia**: i reperti sono descrizioni, le decisioni sono
  dell'utente.
