# RG1 al centesimo (30/09): chi sbagliava il regolamento delle sintetiche

Base: master `7547eee` + `BANCO_MIKE_ONDATA_2.patch`, committati SOLO nel worktree
come `45aa807` ("tmp", da non fondere). `BANCO_RG1_CENTESIMI.patch` = `git diff 45aa807 -- Betfair`
(incrementale, `git apply -R --check` verificato). Nessun commit mio.

## La regola di Betfair
`Betfair/Betfair_api_documentation.pdf` pag. 54-55 (`listClearedOrders`): ogni scommessa
porta `profit` e `commission` a DUE decimali; la commissione e' il 5 % del netto vincente del
mercato, al centesimo (0,56 -> 0,03; 2,14 -> 0,11; 2,36 -> 0,12; 2,52 -> 0,13). Quindi:
1. P&L di ogni scommessa al centesimo (10,14 banca a 1,48 persa = -4,8672 -> -4,87);
2. lordo del mercato = somma dei P&L al centesimo;
3. commissione = round(5 % x lordo vincente del mercato, 2);
4. netto del mercato = lordo - commissione addebitata.
Non documentato: come Betfair arrotonda l'esatto mezzo centesimo. Mike e banco usano entrambi
`round` di Python (flumine: `simulatedorder.profit`).

## Causa: sbagliavano ENTRAMBI (sonda `replay/_strumenti/sonda_rg1.py`, `_synth_mike_reingresso`)
| | lordo 3,5 | lordo 4,5 | comm. 3,5 | comm. 4,5 | netto |
|---|---|---|---|---|---|
| Betfair (regola) | 0,13 | 3,32 | 0,01 | 0,17 | **3,27** |
| Mike prima | 0,1328 | 3,334 | 0,0066* | 0,1667* | 3,30 |
| banco prima (`pnl`) | 0,13 | 3,32 | (0,0065+0,166) = 0,1725 -> 0,17 sul totale | | 3,28 |
(*) Mike toglieva `lordo x 5 %` NON arrotondata (`_net`), sul lordo NON arrotondato.
- Mike (`engine.settle_legs_by_market`) sommava i P&L per gamba NON arrotondati (lo scarto piu'
  grande: +0,014 sul 4,5 con sei banche piccole) e toglieva la commissione non addebitata.
- Il banco (`MercatoFlumine.pnl`) arrotondava i P&L per ordine (giusto: flumine) ma la
  commissione solo sul TOTALE (0,1725 -> 0,17), non per mercato (0,01 + 0,17 = 0,18).
- RG1 aveva una tolleranza di 0,02 che nascondeva lo scarto su `_synth_mike_ultimo_ingresso`.

## Correzioni (minime)
- `Betfair/mike/engine.py` `settle_legs_by_market` (solo il regolamento): `pnl = round(pnl, 2)`
  per gamba (una gamba = un ordine, come la scommessa Betfair); netto del mercato =
  `round(lordo - comm_market, 2)` (la commissione che il motore gia' calcolava al centesimo).
  La somma delle righe resta = `settled_pnl` (§4.15 invariato). Decisioni di trading non
  toccate (`_net`, `net_pnl_by_total`, cash out invariati).
- `Betfair/stream/backtest/banco_comune.py`: `MercatoFlumine.pnl_betfair` (regola sopra).
  `pnl` resta com'e' per la nota storica del referto: Omega e Safe non cambiano.
- `Betfair/mike/certificazione.py` `confronta_regolamento`: tolleranza 0,02 -> 0,005 (solo il
  rumore dei float fra due cifre a due decimali: AL CENTESIMO).
- `Betfair/mike/tools/replay_registrazioni.py`: RG1 confronta con `pnl_betfair`; la nota del
  regolamento scrive per riga lordo/bet/mercato, il lordo per mercato e le commissioni.
- Test esistente modificato: `test_mike_engine_cert_2026_09_12::test_fuzz_somma_righe...`,
  confronto del regolamento col MODELLO (`net_pnl_by_total`, senza arrotondamenti): tolleranza
  da 0,02 fissa a `0,005 x gambe + 0,01` (limite matematico degli arrotondamenti ora dovuti;
  il caso che la superava: 4000 casi fuzz, scarto 0,02 con 6 gambe). La parte del test sulla
  somma delle righe = netto e' invariata (1e-4).
- Test nuovo: `Betfair/mike/tests/test_mike_regolamento_centesimi_2026_09_30.py` (5).

## Prove
TDD: `test_regolamento_come_betfair...` ROSSO prima (per_market 0,13/3,17 contro 0,12/3,15),
verde dopo. Falsificazioni (ripristino sha256, `grep MUTAZIONE` = 0):
- per gamba NON arrotondata -> rosso unitario; e sul REPLAY `_synth_mike_reingresso`
  **KO, RG1: "Mike 3.28 contro 3.27"** (`replay/mut_rgbet_reingresso.txt`);
- netto = `_net` (vecchio) -> rosso (`test_netto_del_mercato_uguale_lordo_meno_commissione_addebitata`:
  lordo 0,10, commissione 0,01, il vecchio scriveva 0,10 invece di 0,09);
- banco con commissione non arrotondata per mercato -> rosso (`test_banco_pnl_betfair...`).
Suite: `Betfair/mike` + test del banco dell'ondata 2: **1362 passed**.

## Replay (dopo)
`replay/rg1_sintetiche.txt` (18 s, comando del coordinatore): 5/5 OK, RG1 x5 verde:
reingresso 3,27 = 3,27 (prima 3,30 / 3,28); reingresso_2gol 3,27 = 3,27 (prima 3,30 / 3,28);
prezzo_migliore 3,55 = 3,55; ultimo_ingresso 0,34 = 0,34 (prima 0,35 / 0,34);
ultimo_ingresso_riprova 0,34 = 0,34.
`replay/rg1_base_35760084.txt` (46 s): OK, RG1 x1, Mike -14,17 = banco -14,17 (commissioni 0,00:
mercati in perdita).

## COSA NON HO POTUTO VERIFICARE
- L'arrotondamento di Betfair sull'ESATTO mezzo centesimo (0,0065 -> 0,01?): non documentato;
  Mike e banco usano lo stesso `round`, quindi concordano, ma col conto vero va confermato su un
  `listClearedOrders` reale.
- `--scenari tutti` e i replay Omega/Safe non rilanciati (Omega/Safe: `pnl` non toccato).
- Il P&L scritto da Mike in produzione cambia fino a qualche centesimo per partita (ora come
  Betfair): storico e stop giornaliero leggono il nuovo numero.
