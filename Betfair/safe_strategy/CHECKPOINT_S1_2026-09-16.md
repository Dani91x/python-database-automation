# CHECKPOINT S1 — SAFE: cash-out globale, chiusura fuori app, cap solo sull'automatico (16/09/2026)

> Delegato "S1" (Opus 5). Stato: **FATTO** (codice, migrazione, 28 test, 12
> falsificazioni tutte rosse, replay calcio e tennis rifatti di persona).
> Vincoli rispettati: nessuna regola di strategia toccata; niente `git add -A`;
> niente commit; niente avvio app.
> File toccati: `Betfair/safe_strategy/bot_service.py`, `bot_db.py`,
> `tests/test_audit_2026_09_11.py`, `tests/test_bot_service.py` (+ migrazione nuova).
> NON toccati (delegato parallelo S2): `engine.py`, `certificazione.py`, `service.py`,
> `tools/replay_registrazioni.py`, `certificazione_tennis.py`, `replay_tennis.py`.

## 1. Punto 1 — CASH-OUT GLOBALE DI PARTITA — FATTO
- marcatore in `meta.chiuso_dall_utente` delle RIGHE (colonna JSONB gia' esistente:
  nessuna migrazione per il marcatore; sopravvive al riavvio, difetto 19 chiuso).
  `bot_service.py`: `CHIUSO_DALL_UTENTE_KEY`, `marcatore_utente`,
  `evento_chiuso_dall_utente`, `indicizza_chiusure_utente` (ricostruita a ogni ciclo
  da `build_risk_ctx`), `segna_chiuso_dall_utente`, `riprendi_evento`, `e_del_bot`.
- kind `cashout_event` in `process_requests` -> `_request_cashout_event`:
  chiude TUTTE le righe vive dell'evento col percorso VERO (`_request_cashout` ->
  `execution.close_trade`), annulla le riserve con `execution.annulla_su_betfair` e
  RILEGGE per bet_id (`_annulla_riserva`), poi scrive il marcatore di partita.
  `CHIUSURE = ("cashout", "cashout_event")` (corsia preferenziale).
- kind `riprendi_evento` -> `_request_riprendi_evento` (unico modo di spegnerlo).
- letto PRIMA della riserva in `scan_and_place` (skip `partita_chiusa_dall_utente`),
  in `_exit_candidates` (niente uscite) e in `_execute` (collo di bottiglia di OGNI
  piazzamento: segnali, opportunita', anomalie, combo, gambe figlie).
- `cashout` per singola riga: marca la RIGA (orfana -> niente gambe figlie) e, se era
  l'ULTIMA viva del bot sull'evento, accende anche il marcatore di partita.

## 2. Punto 2 — CHIUSURA FUORI DALL'APP — FATTO
- `_sorveglia_posizione_di_conto` in `bot_service.py`, chiamata da `settle_open`
  subito dopo `sync_hedges`. Cadenza dichiarata: `CONTO_EVERY_S = 30 s per mercato`
  + `CONTO_MERCATI_PER_CICLO = 2` (ciclo Safe ~2 s: MAI a ogni giro), solo LIVE,
  solo su righe automatiche vive.
- letture RIUSATE (nessuna risorsa nuova): `omega_market.list_current_orders_account`
  / `list_cleared_orders_account` / `market_profit_and_loss` (gia' aggiunte dal
  delegato Mike) e, nel banco, `MercatoFlumine.list_account_orders` /
  `list_account_cleared_orders` (`stream/backtest/banco_comune.py`, gia' presenti:
  NON ho aggiunto `posizione_di_conto`, riuso quei nomi).
- riconoscimento della SUA posizione per ref (`safe-t{id}` + gambe di chiusura) e per
  size: `_refs_di_safe`, `_netto_su_selezione(solo_refs=...)`, `_posizione_attesa_safe`.
  Tre verdetti: `gambe_non_ritrovate` (riconciliazione, non si spegne niente),
  `ridotta_dall_utente` (si dichiara e si continua a proteggere), `chiusa_dall_utente`.
- `_stato_da_settlement_reale`: P&L dal settlement VERO (`profit`/`bet_outcome` degli
  ordini regolati del conto coi nostri ref) al netto della commissione; se il mercato
  non e' ancora regolato NON si inventa nulla (riga viva ma marcata, chiude
  `settle_open`).

## 3. Punto 3 — CAP SOLO SULL'AUTOMATICO — FATTO
- `build_risk_ctx`: `open` = solo bot (DECIDE), `open_tutte` = tutto (pagina),
  `open_all` = tutto (protezione, invariato). `_risk_gate` usa `open_tutte` solo per
  il cap MORBIDO del manuale. `_risk_commit` conta nei cap solo le righe del bot.
- `bot_db.aggregate_rows` pubblica DUE serie: chiavi complete + chiavi `_auto`
  (`righe_del_bot` = aperture `origin='auto'` + TUTTE le loro gambe di chiusura).
  `_numeri_di_rischio` in `bot_service` legge le `_auto` e ripiega sui completi.
- `origin` assente = del bot (colonna `NOT NULL DEFAULT 'auto'`): prudente.
- stats: `risk.daily_liability` (totale) e `risk.daily_liability_bot`,
  `risk.realized_today_bot`, `risk.cap_solo_automatico`.

## 4. Migrazione (SCRITTA, NON APPLICATA)
`migrations/safe_cash_out_globale_e_cap_automatico_2026-09-16.sql` — indispensabile
perche' `safe_strategy_requests.kind` ha un CHECK `IN ('place','cashout','cancel')`
(difetto 18 del catalogo) e la RPC `safe_request` rifiuta gli altri kind; piu' i
numeri `_auto` nella RPC `get_safe_aggregates`.

## 5. Test — FATTI
`Betfair/safe_strategy/tests/test_chiusura_dell_utente_2026_09_16.py`, **28 verdi**
(+ `tests/conftest.py`: la cache di processo si azzera prima di ogni test, come un
servizio appena avviato).
Finti costruiti con le chiavi VERE (`omega_market._riga_corrente`/`_riga_regolata`:
`customer_order_ref`, `size_matched`, `bet_outcome`, `profit`) e percorsi veri
(`_request_cashout` -> `close_trade`, `run_once` intero per la riserva).
Copre: cash-out globale (chiude davvero, marca, niente aperture ne' uscite dopo),
riserva annullata su Betfair e RILETTA, cancel a esito ignoto mai dichiarato
annullato, riga orfana, ultima riga = cash-out globale, «Riprendi», manuale libero,
posizione sparita dal conto, **utente con operazioni SUE sulla stessa selezione**,
copertura parziale, gambe non ritrovate = riconciliazione, paper senza conto,
cadenza 30 s, P&L dal settlement vero, P&L MAI dedotto se il mercato non e'
regolato, 32,80 EUR manuali fuori dai cap, totali di pagina completi.

### Falsificazioni — 12 difetti rimessi, **12 rossi**, file ripristinati e verificati
F1 `_exit_candidates` senza marcatore · F2 `_execute` senza guardia · F3
`scan_and_place` senza guardia · F4 posizione di conto senza `solo_refs` (tutto mio)
· F5 P&L dedotto a mercato non regolato · F6 lettura di conto a ogni giro · F7 cap
di nuovo con le manuali · F8 aggregati `_auto` su tutte le righe · F9 `_risk_commit`
con le manuali · F10 marcatore solo in RAM · F11 uscita del bot approvata scambiata
per chiusura dell'utente · F12 gamba di combo chiusa a partita gia' chiusa.
(F3 e F12 all'inizio NON erano catturate: due test in piu', poi rossi.)

## 6. Suite
`python -m pytest Betfair/safe_strategy Betfair/omega Betfair/stream -q -p no:cacheprovider`
-> **3260 verdi, 0 rossi** (ultima esecuzione). I rossi visti durante il lavoro erano
tutti di delegati paralleli: verificato neutralizzando TUTTE le mie guardie e
rimettendole (gli stessi 3 restavano rossi), e ora li hanno chiusi loro.

## 7. Reperto trovato DAL REPLAY (e corretto)
Il primo giro di `safe_tennis 35792939 --scenari approvata-subito` ha scritto
`chiuso_dall_utente x1`: il cancelletto di approvazione del TENNIS manda una
richiesta `cashout` IDENTICA a quella del bottone «Cash out», ma quella chiusura
l'ha DECISA IL BOT e l'utente ha solo dato l'ok. Marcandola come chiusura
dell'utente il bot si spegneva su una partita che stava gestendo lui.
Correzione: si riconosce dal payload, che porta `exit_kind` (lo scrive
`_proponi_chiusura`); con `exit_kind` presente NESSUN marcatore. Test dedicato.

## 8. Replay — FATTO
Comando (il wrapper `tools/replay_registrazioni.py` passa ancora `safe_calcio`, che
il registro non ha piu': si e' usato il punto d'ingresso unico):
`python -m Betfair.stream.backtest.certifica safe_esatto 35797769 --scenari cashout-globale,manuale-e-bot`

| scenario | prima (C.3, 16/09 h20:30) | dopo |
|---|---|---|
| `cashout-globale` | 3 ordini, **T14 x282 VIOLAZIONI**, gamba automatica 0,04 EUR, `exit_hold` x282 | 2 ordini, **T14 x923 sollecitato, 0 violazioni**, `chiuso_dall_utente` x1, `partita_chiusa_dall_utente` x3, uscite valutate **0**, righe {hedged:1, open:1 (la gamba manuale)} |
| `manuale-e-bot` | 4 ordini, T13 verde | 4 ordini, T13 verde, T14 x0 «non lo so» (nessuna chiusura in questo scenario), 0 violazioni |

Tennis: `certifica safe_tennis 35792939 --scenari approvata-subito` → **0 violazioni**,
attivita' IDENTICA al giro con le guardie nuove spente (baseline misurata di persona
neutralizzando le guardie e rimettendole): `exit_hold x8, place_rifiutato x2,
replay_ingresso_dichiarato x2, place_retry x1, skip x1, place x1, cashout_error x1,
cashout x1`. Unica differenza: 454 tick invece di 463, perche' la lettura della
posizione di conto CONSUMA tempo di mercato — in produzione come nel replay (regola
del tempo, C.0-perf). Dichiarata.

## 9. Cosa serve lato UI (NON ho toccato `frontend/`)
1. bottone «Cash out globale della partita» → `safe_request('cashout_event',
   {"event_id": ...})`;
2. bottone «Riprendi» sulla partita marcata → `safe_request('riprendi_evento',
   {"event_id": ...})`;
3. etichette italiane per i kind nuovi (`chiuso_dall_utente`, `posizione_di_conto`,
   `riprendi_evento`) in `frontend/src/lib/safeActivity.ts`;
4. badge «chiusa da te» sulla partita e sulla riga (da `meta.chiuso_dall_utente`);
5. due numeri nel pannello rischio: `risk.daily_liability` (tutto) e
   `risk.daily_liability_bot` (cap del bot), piu' `risk.cap_solo_automatico`.
Tutte e cinque richiedono la migrazione applicata (punti 1-2) o nulla (3-5).

## 10. Cosa NON e' verificato
- `_sorveglia_posizione_di_conto` non e' mai stata SOLLECITATA da un caso vero nel
  banco: nessuno scenario Safe pianta un ordine dell'utente sul blotter. Il mezzo
  esiste gia' (`banco_comune.MercatoFlumine.place_order_utente`, aggiunto dal delegato
  Mike) ma serve uno scenario `chiusura-fuori-app` in
  `Betfair/safe_strategy/tools/replay_registrazioni.py` (file di un altro delegato).
  Nel replay la funzione gira e TACE: nessun falso positivo, ma nemmeno una conferma.
- `listMarketProfitAndLoss` (`omega_market.market_profit_and_loss`) NON e' usata da
  Safe: la posizione la ricostruiscono gli ordini. Resta come controprova.
- Il banco non porta `bet_outcome`/`profit` negli ordini del conto
  (`banco_comune._riga`): il ramo «P&L dal settlement vero» e' coperto SOLO dai test.
- La RPC `get_safe_aggregates` non torna ancora le chiavi `_auto` (§4): fino ad allora
  i cap giornalieri ripiegano sui numeri completi (piu' alti = piu' prudenti).
- Niente provato contro Betfair vero: nessun `cancel` reale, nessuna lettura di conto
  reale.
