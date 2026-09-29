# CANTIERE MIKE-COPERTURA - P5 blocco 2B (correzioni chieste dalla revisione, 29/09/2026)

Base: `08b9c6a` + `MIKE_P2BIS.patch` + `MIKE_P5_2.patch` (tutte e due applicate col `git apply`
semplice, pulite). Patch: `AUDIT_2026-09-29/MIKE_P5_2B.patch` (7 KB), sopra `MIKE_P5_2.patch`.
Nessun commit.

## 1. Cosa cambia
- `Betfair/mike/engine.py`, `_copertura_banca` (+5/-2): la guardia di P2-bis sul punteggio assente,
  identica al ramo della forma di prima: `... and ctx.cover_forced and not dopo_gol and snap.goals
  is not None` e il motivo "copertura: punteggio assente, attendo" quando si aspetta senza gol.
  (`cover_timing` con `goals is None` torna gia' "wait": la guardia impedisce che `cover_forced` la
  scavalchi.)
- nuovo `Betfair/mike/tests/test_mike_p5_2b_2026_09_29.py`, 4 test.

## 2. Test e mutazioni (`AUDIT_2026-09-29/mike_p5/falsifica_mike_p5_2b.py`, esito `..._2b.txt`)
| Test | Mutazione | Esito |
|---|---|---|
| punteggio assente + `cover_forced` + forma banca: nessun ordine, `LIVE_UNCOVERED`, motivo del punteggio assente; con `goals=0` la banca parte (il test non passa a vuoto) | G1: guardia tolta | ROSSO |
| riga del mercato 4,5 con la copertura-banca (chiave Over): `abbinato` 12,63, `abbinato_per_selezione` = {UNDER: {back 0, lay 12,63}} | Q19 del coordinatore | ROSSO |
| domanda (a) | A1: gia' coperto contato senza le banche | ROSSO (4 test) |
| domanda (b) | T1: tolleranza sulla PRIMA chiusura; T2: sulla chiusura a prezzo piu' alto | ROSSO / ROSSO |
Ripristino verificato (hash, nessuna MUTAZIONE). Suite `Betfair/mike` sulla base sopra:
**1187 verdi**, 2 rossi attesi del contratto UI (`cover_form` non ancora in `mike.ts`).

## 3. Risposte
**(a) `cover_matched_value` con la banca Under abbinata in parte** (`engine.py`, `cover_matched_value`
-> `_market_pnl_by_total(active_legs(legs), MARKET_OU45, 5)`; nella somma una gamba `lay` con la
selezione che PERDE vale `+s`, `engine.py` `_market_pnl_by_total`, ramo `else: pnl += ... if win else s`).
Banca Under 4,5 5,00 abbinati a 1,18 (tranche da 9,47): con 5 gol l'Under 4,5 perde, la banca incassa
+5,00; commissione del mercato sul netto positivo -> 5,00 x 0,95 = **4,75** = A. Il resto per la
copertura piena: (1,2 x 10 - 4,75) / 0,95 = **7,63**. Test
`test_cover_matched_value_banca_under_abbinata_in_parte` (valori esatti). Il rischio della parte
abbinata (5 x 0,18) non entra in A: A e' solo cio' che si incassa con 5+ gol, come per la punta Over.

**(b) Tolleranza del piatto nel rientro** (`engine.py`, `tolleranza_piatto_ou45`: `chiusure[-1]`,
ultima gamba di CHIUSURA abbinata del mercato 4,5 in ordine di creazione). Caso del test: copertura
punta Over chiusa a 21, rientro 10 a 1,30, green abbinata in parte 8,61 su 8,67 a 1,50. Sbilancio
0,079 (0,05 di banca a 1,50 da rimettere). L'ultima chiusura abbinata e' la green (1,50): tolleranza
max(0,01; 0,0075) = **0,01**, non 0,105: il mercato NON e' piatto, `open_selections` = [(OU45,
UNDER)] e `_decide_reentry_open` rimette la green del resto (banca 0,06 al prezzo di green 1,28).
Prima che la green si abbini anche solo in parte lo sbilancio e' quello intero del rientro (~13):
lontanissimo da qualunque tolleranza. Le mutazioni T1 e T2 (tolleranza presa dalla chiusura a 21)
fanno diventare rosso il test.

## 4. Non verificato
Replay non rilanciati per 2B (una guardia che scatta solo col punteggio assente e la forma banca,
entrambe assenti dal replay di serie): i numeri del blocco 2 restano validi.
