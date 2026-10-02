# RICONCILIAZIONE_TRADOTTI - ordini tradotti dal runner letti giusti da Safe e Omega (02/10/2026)

Correttore: delegato Opus. Ramo locale `riconciliazione-tradotti` (sopra `verifica-runner-master`
`e4c93e0` = master `fb890d5` + runner «minimi .it» con correzioni). Niente commit su master,
niente push, mai `git add -A`. Nessun ordine vero, nessuna scrittura sul DB, nessun processo
lasciato acceso, nessuna suite intera, nessun replay.

STATO AL 02/10 sera (2): D1, D2, D3 riprodotti rossi, corretti, test verdi; falsificazione in
corso; mancano i numeri delle suite mirate, la patch, i numeri finali qui sotto.

Consegna (in questa cartella):
- `RICONCILIAZIONE_TRADOTTI.patch` = `git diff verifica-runner-master` (file nuovi inclusi);
- `falsifica_riconciliazione.py` + `falsifica_riconciliazione_out.txt`;
- questo referto.

## 0. In breve

| difetto | stato | dove (base `e4c93e0`) |
|---|---|---|
| D1 Omega, ripiego live oltre 20 s | **CORRETTO** | `omega_service.py:3131-3171` `_adotta_per_mercato`, `:3173-3221` `_canale_live_oltre_scadenza`, `:3108` `_aggiorna_da_evento` |
| D2 Safe, ripiego per bet_id | **CORRETTO** | `bot_service.py:1473-1497` `_reconcile_by_bet_id` (+ `:1400` annullo, `:1833` completamento, `execution.py:1156` per ref) |
| D3 coda e REST di Safe | **CORRETTO per le CHIUSURE di Safe calcio su mercati a due esiti** | `execution.py:862` rifiuto in casa; worker senza verdetto; REST senza book |

Approccio scelto: **(B)**, una funzione unica di traduzione nel runner, usata da TUTTE le vie di
lettura, **senza migrazione**. Motivo nel §1.

## 1. Approccio: (B) una traduzione unica, nessuna migrazione

- Lo specchio `betfair_live_orders` NON ha una colonna JSON riusabile (`meta`/`extra`/`ref`
  non esistono: `migrations/betfair_live_order_queue.sql:80-104`); la (A) avrebbe chiesto una
  migrazione e un ripiego per le colonne mancanti, e comunque NON avrebbe coperto le letture
  REST (stato per bet_id, ordini correnti/regolati), che non passano dallo specchio.
- La traduzione e' DETERMINISTICA: dato l'ordine chiesto (la riga del bot: selezione, lato,
  quota, size) l'equivalente e' `equivalente_lato_opposto` (altra selezione, lato opposto,
  quota `q/(q-1)` al tick, size `S(q-1)`). Quindi ogni lettura dell'ordine VERO che sta
  sull'ALTRA selezione col lato OPPOSTO, legata alla riga da bet_id o ref, e' un tradotto,
  e si riporta ai termini chiesti con le stesse regole dell'evento del canale.
- Nel runner (`Betfair/stream/live_order_build.py`):
  - `riporta_lettura_tradotta(letto, originale, mandato)`: la traduzione, per ogni grafia
    (evento/specchio `average_price_matched`; REST `avg_price_matched`, `size_settled`,
    `price_requested`, `size_requested`); la riga vera resta in `riga_mandata`;
  - `motore_ordini._riporta_tradotto` ora delega a lei (evento del canale identico: i test
    del runner di oggi restano verdi);
  - `lettura_nei_termini_chiesti(chiesto, letto, tradotto=None)`: riconosce un tradotto
    dalla dichiarazione del runner se il bot l'ha vista, altrimenti DAI DATI; None = la
    lettura si usa com'e' (un ordine non tradotto torna IDENTICO, stesso oggetto);
  - `impronta_equivalente(chiesto, ordine)`: per l'adozione SENZA bet_id, impronta esatta
    (altra selezione, lato opposto, quota e size chieste identiche all'equivalente).
- Nei bot (`Betfair/safe_strategy/execution.py`, usato da Safe e da Omega):
  `nei_termini_della_riga(trade, letto)`, `ricorda_tradotto(meta, letto)` (la dichiarazione
  `{originale, mandato}` resta in `meta.canale_tradotto`), `tradotto_di_riga(trade)`.
- `omega_market.order_state_by_bet_id` porta in piu' l'IDENTITA' dell'ordine letto
  (`selection_id`, `side`, `price_requested`, `size_requested`, da `CurrentOrder`/
  `ClearedOrder`): chiavi aggiunte, nessuna cambiata; il gemello del banco
  (`banco_comune.MercatoFlumine.order_state_by_bet_id`) le porta uguali.

## 2. D1 - Omega

(da completare)

## 3. D2 - Safe

(da completare)

## 4. D3 - coda e REST di Safe

(da completare)
