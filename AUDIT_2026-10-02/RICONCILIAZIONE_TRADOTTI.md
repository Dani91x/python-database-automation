# RICONCILIAZIONE_TRADOTTI - ordini tradotti dal runner letti giusti da Safe e Omega (02/10/2026)

Correttore: delegato Opus. Ramo locale `riconciliazione-tradotti` (sopra `verifica-runner-master`
`e4c93e0` = master `fb890d5` + runner «minimi .it» con correzioni). Niente commit su master,
niente push, mai `git add -A`. Nessun ordine vero, nessuna scrittura sul DB, nessun processo
lasciato acceso, nessuna suite intera, nessun replay.

STATO AL 02/10 sera (3): D1, D2, D3 riprodotti rossi, corretti, 59 test nuovi verdi;
falsificazione 32/33 rosse al secondo giro (T-f era un mutante equivalente: guardia ridondante
tolta, mutazione sostituita), terzo giro e suite mirate in corso. Vedi §8 per i numeri finali.

Consegna (in questa cartella):
- `RICONCILIAZIONE_TRADOTTI.patch` = `git diff verifica-runner-master` (file nuovi inclusi);
- `falsifica_riconciliazione.py` + `falsifica_riconciliazione_out.txt`;
- questo referto. Commit del ramo: `git log verifica-runner-master..riconciliazione-tradotti`.

## 0. In breve

| difetto | stato | causa (base `e4c93e0`) |
|---|---|---|
| D1 Omega, ripiego live oltre 20 s | **CORRETTO** | `omega_service.py:3131-3171` `_adotta_per_mercato` cerca selezione e lato del CHIESTO; `:3173-3221` `_canale_live_oltre_scadenza` conferma con lo stato per bet_id del VERO; `:3108` `_aggiorna_da_evento` butta la dichiarazione `tradotto` dell'evento |
| D2 Safe, ripiego per bet_id | **CORRETTO** | `bot_service.py:1473-1497` `_reconcile_by_bet_id` (stato del VERO sulla riga); stesse letture in `:1400` annullo, `:1833` completamento consapevolezza, `execution.py:1156` `reconcile_decision` per ref, `omega_service.py:3450` `_mirror_fill` |
| D3 coda e REST di Safe | **CORRETTO per le CHIUSURE di Safe calcio su mercati a due esiti** (aperture: §4.5) | `execution.py:862` rifiuto in casa sotto 0,50; worker senza verdetto dei minimi; REST senza book |

Approccio: **(B)**, una funzione unica di traduzione nel runner usata da TUTTE le vie di lettura,
**nessuna migrazione**. Nessun cambio di strategia (soglie, quote, timing, stake): cambia solo
come si LEGGE l'esito di un ordine e, per D3, quale ordine il runner manda per una chiusura che
prima era rifiutata in casa.

## 1. Approccio scelto: (B), e perche' non (A)

- Lo specchio `betfair_live_orders` NON ha una colonna JSON riusabile (nessun
  `meta`/`extra`/`ref`: `migrations/betfair_live_order_queue.sql:80-104`). La (A) chiedeva una
  migrazione piu' un ripiego per colonne assenti, e NON copriva le letture REST (stato per
  bet_id, ordini correnti e regolati), che non passano dallo specchio. Una sola via corretta
  su cinque non chiude D1 ne' D2.
- La traduzione e' DETERMINISTICA: dato l'ordine chiesto (la riga del bot) l'equivalente e'
  `equivalente_lato_opposto` (altra selezione, lato opposto, quota `q/(q-1)` al tick, size
  `S(q-1)`). Un ordine VERO legato alla riga (bet_id o ref) che sta sull'ALTRA selezione col
  lato OPPOSTO e' per forza il suo tradotto.
- Nel runner (`Betfair/stream/live_order_build.py`):
  - `riporta_lettura_tradotta(letto, originale, mandato)`: LA traduzione, per ogni grafia
    (evento/specchio `average_price_matched`; REST `avg_price_matched`, `size_settled`,
    `price_requested`, `size_requested`); la riga vera resta in `riga_mandata`.
    `motore_ordini._riporta_tradotto` ora delega a lei: evento del canale identico (i test
    del runner restano verdi, contratto col motore vero in
    `test_r_contratto_tradotto_del_finto_uguale_al_motore_vero`);
  - `lettura_nei_termini_chiesti(chiesto, letto, tradotto=None)`: con la dichiarazione del
    runner (vista dal bot) usa quella; senza, riconosce DAI DATI (serve selezione e lato
    nella lettura); altrimenti None e la lettura resta IDENTICA (stesso oggetto);
  - `impronta_equivalente(chiesto, ordine)`: per l'adozione SENZA bet_id, impronta esatta;
  - `PARAM_EQUIVALENTE_AMMESSO` (`params.equivalente_ammesso` della riga di coda).
- Nei bot (`Betfair/safe_strategy/execution.py`, usato da Safe e da Omega):
  `nei_termini_della_riga(trade, letto)`, `ricorda_tradotto(meta, letto)` (dichiarazione
  `{originale, mandato}` in `meta.canale_tradotto`), `tradotto_di_riga(trade)` (anche da
  `meta.esecuzione.tradotto` della via REST).
- `omega_market.order_state_by_bet_id` porta in piu' l'IDENTITA' dell'ordine letto
  (`selection_id`, `side`, `price_requested`, `size_requested`, da `CurrentOrder`/
  `ClearedOrder`): solo chiavi aggiunte. Il gemello del banco
  (`banco_comune.MercatoFlumine.order_state_by_bet_id`) porta le stesse (catalogo n. 27).

## 2. D1 - Omega

- **Riproduzione** (`Betfair/omega/tests/test_riconciliazione_tradotti_omega_2026_10_02.py`,
  rossi sulla base):
  - `test_d1_senza_bet_id_la_chiusura_tradotta_abbinata_non_e_fallita`: banca Over 0,43 @18
    sul canale, nessun evento, punta Under 7,31 @1,06 abbinata su Betfair: la base marcava la
    chiusura `error` `flumine_canale_mai_visto_su_betfair`;
  - `test_d1_con_bet_id_lo_stato_rest_si_legge_nei_termini_chiesti`: la base confermava la
    riga Over a 7,31 @1,06;
  - `test_d1_caso_completo_nessuna_seconda_chiusura[con/senza bet_id x banca->punta /
    punta->banca]` (il caso money-critical, integrazione senza rete): cash-out manuale VERO
    di Omega (`_manual_cashout` -> `close_trade` -> porta del canale VERA), finto del motore
    che traduce col verdetto VERO e manda l'evento con `_riporta_tradotto` VERO, poi tace;
    Betfair (funzioni vere di `omega_market` su rete finta) mostra l'equivalente abbinato;
    poll a +25 s e +200 s, `_settle_hedged`, secondo `_manual_cashout`. Sulla base, senza
    bet_id, il secondo cash-out MANDAVA UN SECONDO COMANDO (doppia chiusura, rosso
    `SECONDA CHIUSURA mandata`); con bet_id la riga diceva 7,31 @1,06 (e 2,50 @1,20 nel
    verso punta->banca).
- **Correzione** (`omega_service.py`):
  - `_aggiorna_da_evento` e `_chiudi_da_evento`: la dichiarazione `tradotto` dell'evento resta
    sulla riga (`ricorda_tradotto`);
  - `_adotta_per_mercato`: se nessun ordine sta su selezione/lato chiesti, si adotta SOLO
    l'ordine con l'impronta esatta dell'equivalente (mai uno qualunque dell'altra selezione;
    piu' candidati = indecisa, come prima); `come = mercato_equivalente`;
  - `_canale_live_oltre_scadenza`: lo stato per bet_id si legge nei termini della riga;
  - `_mirror_fill(mirror, req, tr)` e la coda live oltre la deadline: stessa traduzione
    (serve alla coda di Safe, che usa queste funzioni di Omega).
- **Dopo**: chiusura `open` a banca Over 0,43 @18 (riportato: 0,43 @ 1 + 7,31/0,43 = 18,0),
  apertura `hedged`, secondo cash-out rifiutato, UN solo comando.

## 3. D2 - Safe

- **Riproduzione** (`Betfair/safe_strategy/tests/test_riconciliazione_tradotti_safe_2026_10_02.py`):
  - `test_d2_ripiego_per_bet_id_la_riga_resta_nei_termini_chiesti`: la base confermava
    banca Over 7,31 @1,06 (esposizione 0,44 invece di 7,31; apertura non coperta);
  - `test_d2_caso_completo_pnl_della_riga_e_nessuna_seconda_chiusura`: evento accettato
    tradotto (bet_id vero), silenzio, REST oltre i 20 s, apertura `hedged`, secondo
    `close_trade` rifiutato senza ordini, regolamento (vince Under): P&L della chiusura
    +0,43, apertura -1,00. Sulla base la riga Over a 7,31 @1,06 avrebbe dato +7,31.
- **Correzione** (`bot_service.py`): `_reconcile_by_bet_id`, `_annulla_prima_del_terminale`,
  `_completa_consapevolezza_mancante`, il racconto della riga (`ordine` del giro) e
  `execution.reconcile_decision` (correnti e regolati per ref) leggono nei termini della riga;
  gli eventi intermedi e terminali del canale e la conferma per bet_id conservano la
  dichiarazione.
- **P&L al centesimo, detto com'e'**:
  - regolamento dal regolato di Betfair (`_posizione_da_cleared`, per bet_id): il `profit`
    VERO della punta Under (7,31 x 0,06 = 0,4386 -> **0,44**), invariato e giusto
    (`test_d2_pnl_dal_regolato_di_betfair_e_il_vero_al_centesimo`);
  - regolamento calcolato (ripiego quando Betfair non ha ancora il regolato): dalla riga nei
    termini chiesti, **0,43**: prudente di un centesimo per costruzione
    (`riporta_abbinato_all_originale`: la vincita reale e' >= quella riportata). Non l'ho
    cambiato: e' la regola del runner certificata il 01-02/10.

## 4. D3 - coda e REST di Safe

- **Riproduzione** (sulla base): `test_d3_coda_chiusura_043_va_al_runner_con_l_equivalente_ammesso
  [paper/live]` (rifiuto in casa `sotto_minimo_non_piazzabile:0.43`), `test_d3_rest_chiusura_043_...`
  (nessun ordine), `test_d3_tre_vie_stesso_verdetto_stesso_ordine_stessa_riga`.
- **Correzione**:
  - `execution.place`: per le CHIUSURE di Safe calcio (ref `safe-t`) su un tipo di mercato a
    due esiti (`OVER_UNDER_*`, `FIRST_HALF_GOALS_*`, `BOTH_TEAMS_TO_SCORE`, passato da
    `close_trade` dalla riga) sotto 0,50 il rifiuto in casa resta SOLO se l'equivalente non
    e' economicamente possibile (`_equivalente_possibile`); il resto va
    - in CODA come `place_submin` con `params.equivalente_ammesso`: il worker
      (`live_order_worker._traduci_riga_coda`, chiamato da `_dispatch`) applica lo STESSO
      verdetto del canale (`altro_runner_due_esiti` + `verdetto_minimi`): equivalente come
      place diretto FILL_OR_KILL (come la chiusura sul canale), `result` nei termini chiesti
      con `tradotto` e `riga_mandata`; tre esiti -> `SOTTO_MINIMO_NON_PIAZZABILE`, nessun
      ordine; senza il parametro nulla cambia (Omega, Mike, desktop);
    - in REST (runner giu', live): `_equivalente_rest` legge l'altra selezione dal book
      (`omega_market.altra_selezione_due_esiti`, UNA `listMarketBook`, solo sotto il minimo;
      regola pura `altro_esito_dal_book`: due runner ACTIVE, un vincitore), piazza
      l'equivalente FOK col ref della riga, riporta l'esito ai termini chiesti
      (`esecuzione.tradotto`, `percorso=equivalente`); tre esiti / non esaustivo / book
      illeggibile -> il rifiuto certo di prima.
  - Le letture della coda (specchio, stato per bet_id oltre la deadline) e del REST a esito
    ignoto (per ref) leggono nei termini chiesti (§2, §3).
- **Le tre vie, stesso verdetto**: `test_d3_tre_vie_stesso_verdetto_stesso_ordine_stessa_riga`:
  canale, coda (worker vero) e REST (funzioni vere su rete finta) mandano tutti punta Under
  7,31 @1,06 e la riga dice banca Over 0,43 @18.
- **4.5 Cosa resta come prima, deciso e dichiarato**:
  - Risultato Esatto, 1X2, tipo ignoto: rifiuto in casa, mai in coda ne' al book a ogni
    ritento (altrimenti una riga di coda in errore ogni 20 s e un CRITICAL a ogni ritento:
    era la regressione di `test_exit_residuo_sotto_050_coi_minimi_veri_mai_ordini_un_critical`
    al primo giro, corretta col filtro del tipo);
  - APERTURE sotto il minimo su coda e REST: place-and-trim / rifiuto come prima. Sul canale
    la loro traduzione e' SENZA FOK (`_place_via_canale` non mette FOK alle aperture sotto il
    minimo): portarla sul REST lascerebbe un ordine a riposo che nessuno segue. Divergenza
    residua canale/coda/REST per le aperture sotto 0,50: **da decidere dall'utente**;
  - Omega e Mike su coda/REST: come prima (le loro riconciliazioni REST per ref,
    `omega_engine.reconcile_decision` e `mike/service`, non sanno leggere un tradotto).

## 5. Falsificazione

`falsifica_riconciliazione.py`: 33 mutazioni, una per ogni pezzo della correzione (D1-a..f,
D2-a..h, D3-a..m, T-a..f), ognuna rimessa nel file vero, i 3 file di test nuovi lanciati,
rosso preteso, ripristino byte per byte verificato, verde ripreso alla fine. Esito nel
`_out.txt` (§8).

## 6. NON VERIFICATO

- Nessun ordine vero: l'identita' in `order_state_by_bet_id` (`selectionId`, `side`,
  `priceSize`/`priceRequested`) e' letta dalle risposte grezze documentate e dai finti;
  `numberOfWinners` e `status` dei runner nel `listMarketBook` lightweight idem.
- Il worker con un runner flumine VERO (paper o live) che riceve la riga `place_submin` con
  `equivalente_ammesso`: provato con `_dispatch` vero su un mercato flumine finto.
- Ordine di rilascio: se Safe gira col codice nuovo e il runner col vecchio, la chiusura 0,43
  va in coda e il worker vecchio la rifiuta (`verifica_importo_finale`) a ogni ritento: prima
  il runner, poi Safe.
- Suite intera e replay: non lanciati (li fa il coordinatore).

## 7. Reperti (fuori perimetro, NON toccati)

1. **Safe, canale senza NESSUN evento, live (money-critical, preesistente, non solo dei
   tradotti)**: `_MercatoSafe.list_current_orders` filtra `customer_order_ref` per prefisso
   `safe-` (`bot_service.py:90-92`), ma il runner piazza col ref di flumine (`<hash>-<id>`):
   la ricerca per ref (`safe-t<id>` e `meta.canale_cor`, R-2 del 28/09) non trova MAI un
   ordine del canale in produzione. Se nessun evento arriva (porta caduta, memoria persa),
   dopo la grazia la chiusura diventa `reconcile_ordine_assente` mentre l'ordine puo' essere
   abbinato: stesso rischio di doppia chiusura di D1. Omega ha l'adozione per mercato, Safe
   no. Proposta: portare a Safe `_adotta_per_mercato` (con l'impronta dell'equivalente).
2. **Posizione di conto di Safe** (`_sorveglia_posizione_di_conto`): netta per SELEZIONE; una
   chiusura tradotta sta sull'altra selezione. Verdetto prudente (dichiara riconciliazione,
   non spegne niente), ma andrebbe netta per MERCATO sui due esiti.
3. **P&L calcolato prudente di un centesimo** sulle chiusure tradotte (§3); il regolato vero
   e' giusto.
4. **Test di tempo** `test_latenza_logica_comando_place_sotto_20_ms` del motore: rosso una
   volta con la macchina carica (falsificazione in parallelo), come gia' riportato il 02/10.
