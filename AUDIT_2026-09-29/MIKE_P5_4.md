# CANTIERE MIKE-COPERTURA - P5 blocco 4 (+4B): il banco (29/09/2026)

Base: `origin/master` `a742f5e` + `MIKE_P5_3.patch`. Patch: `AUDIT_2026-09-29/MIKE_P5_4.patch`
(39 KB, sopra `MIKE_P5_3.patch`; comprende anche le richieste 4B A e B). Nessun commit.

## 1. Righe toccate
| File | + / - | Cosa |
|---|---|---|
| `Betfair/mike/certificazione.py` | +101 / -5 | E2 ramo banca (VERIFICA l'importo), J5B nuovo, J6 ramo banca, S2 sul libro della copertura (`_sel_copertura`) |
| `Betfair/mike/tools/replay_registrazioni.py` | +60 / -7 | scenari nuovi/ricalibrati, leve (rifiuto delle banche sul 4,5, cash out a partita coperta) |
| `Betfair/mike/engine.py` | +11 | `_decide_flatten`: nessuna chiusura manuale su un mercato non APERTO (reperto, par. 4) |
| `Betfair/stream/backtest/registro_bot.py` | +8 / -1 | impronta di Mike: tutti i moduli di Mike importati dal servizio (4B-B) |
| test nuovi | `test_mike_p5_banco_2026_09_29.py` (13), `test_mike_p5_4b_2026_09_29.py` (12) | |

## 2. Controlli
- **E2** (banca): verifica che l'importo sia QUELLO previsto, residuo dai fill x frazione della
  tranche (`cover_residual_lay`, `frazione_copertura`), al centesimo; piu' piccolo solo se il tetto
  per partita lo tiene fuori (rischio al limite dentro lo spazio). Test: 12,63 giusto (tace, con
  caso), 12,00 / 13,50 / 2,26 sbagliati (parla), 10,00 giusto col tetto 12, sbagliato senza tetto e
  col tetto 20 che non lo tiene fuori. Nel replay: E2 x6 casi, 0 violazioni (12,63 verificato).
  Il ramo della punta resta com'era (anche il difetto noto: legge `commission`/`cover_factor` che non
  esistono, innocuo coi valori di serie: NON corretto per non cambiare il referto della forma di prima).
- **J6** (banca): il residuo e' quello della banca (`cover_residual_lay`), non della punta: il falso
  rosso della sonda del coordinatore ("12.63 Over ... residuo 4.21") sparisce. Test: 12,63 intera tace;
  12,63 con 9,47 gia' abbinati parla ("residuo previsto di 3.16").
- **S2**: il libro e' quello della copertura: ordine proposto, poi copertura sul book, poi la forma
  scelta. Nella forma di prima e' sempre l'Over: `quando` e referto identici.
- **J5B** (nuovo): UNA banca per MERCATO sul 4,5 (stato e decisione, come J5). Nel replay x12 casi.
- Falsificazione (`mike_p5/falsifica_mike_p5_4.py`, esito `..._4.txt`): **7 mutazioni, 7 ROSSE**
  (E2 muto; E2 che accetta una banca ridotta senza tetto che la tenga fuori; J6 col residuo della punta;
  S2 sempre Over; S2 che ignora l'ordine proposto; J5B muto; chiusura manuale a mercato sospeso).

## 3. Scenari (tutti SOLO parametri o leve del banco, mai la partita)
| Scenario | Cosa |
|---|---|
| `copertura-rifiutata` | ricalibrato: forma banca, `cover_rifiuti_max` 1, Betfair rifiuta SEMPRE le banche sul mercato 4,5 (`rifiuta_lato=lay`, `rifiuta_market_id` = 4,5 letto dalla riga) |
| `copertura-rifiutata-legacy` | il vecchio `copertura-rifiutata` sulla forma di prima (stake 3,00, sotto minimo) |
| `copertura-legacy` | `base` con `cover_form=back_over45` (l'interruttore resta certificato) |
| `cashout-dopo-copertura` | forma banca; la richiesta VERA di cash out arriva quando la partita e' `LIVE_COVERED` |
NON aggiunti, con motivo: `cambio-forma-in-corsa` (provato e tolto: la copertura e' FOK, si risolve nel
giro, e il cambio di forma a copertura in volo non ha mai un caso sulla registrazione; il caso vero, una
copertura a esito ignoto di una forma piu' la nuova, e' nei test del blocco 1 con `pending_reconcile`);
`copertura-banca-parziale` (la banca e' FOK, tutto o niente: `execution.py:531`, `time_in_force=FOK`
su ogni place normale; un parziale non esiste, il resto sotto 0,50 e' nei test M3.5).

## 4. Reperto trovato dal banco e corretto (engine, `_decide_flatten`)
Primo giro di `cashout-dopo-copertura`: **KO, C3 x3** "manual_close su un mercato in stato
SUSPENDED". Il cash out dell'utente IN GIOCO piazzava la chiusura anche a mercato sospeso (gol): la
chiusura manuale non guardava lo stato del mercato. Difetto gia' presente anche nella forma di prima
(mai sollecitato: `cashout-globale` scatta in pre-partita). Corretto: con una chiusura su un mercato
non aperto si aspetta la riapertura, stato fermo, nessun ordine. Test + mutazione C7 rossa. Dopo:
`cashout-dopo-copertura` OK su coda e canale.

## 5. Replay (ambiente neutro, `--worker 0`, 35760084)
| Scenario | trasporto | esito | fill | P&L replay | tempo |
|---|---|---|---|---|---|
| base (forma di prima, di serie) | canale | OK | 14,00 [1,71; 4,0] | -14,00 | 90,6 s |
| copertura-legacy | canale | OK | 14,00 [1,71; 4,0] | -14,00 | 93,0 s |
| copertura-rifiutata (banca) | coda | OK, 1 rifiuto, S1 x4520, S3 x4520, S4 x2 | 10,00 [1,71] | -10,00 | - |
| copertura-rifiutata (banca) | canale | OK | 22,63 [1,33; 1,71] | -14,17 | - |
| copertura-rifiutata-legacy | coda / canale | OK / OK | 3,00 / 4,26 | -3,00 / -4,26 | 90,7 s |
| cashout-dopo-copertura (banca) | coda / canale | OK / OK | 36,19 [1,33; 1,71; 1,77; 1,78; 4,3] | -0,61 | 94,1 s |
Referti: `mike_p5/replay_b4_nuovi.txt`, `replay_b4_entrambi.txt`, `replay_b4_rifiutata.txt`.
Tempi: 6 replay in 207 s, 3 scenari x 2 trasporti in 230 s (PC carico). I 3 scenari nuovi aggiungono
circa 3 x 92 s di CPU al giro completo (~90 s col lavoro su 3 processi): il giro di Mike (18 scenari, 506 s
a PC piu' libero) passerebbe a circa 600 s, **al tetto**: LO DICHIARO, va misurato dal coordinatore.
**Reperto del banco (preesistente, non mio):** sul trasporto CANALE la leva del rifiuto
(`MercatoFlumine.place_order_live` di `banco_comune.py:529`) non viene mai usata: il comando va al
motore ordini e a flumine direttamente. Per questo anche il vecchio `copertura-rifiutata` sul canale
non rifiutava niente (riferimento `mike_coperture_P2_P4_2.txt`: canale 4,26 abbinati, nessun rifiuto)
e la "PARITA' coda/canale NON RAGGIUNTA" di quei referti nasce qui. Sul canale S1/S3 non hanno casi.

### Forma banca, numeri per il coordinatore
Ingresso punta Under 3,5 10,00 a 1,71; banca Under 4,5 **12,63** (importo), abbinata a **1,33**
(quota; limite 2 tick sopra il miglior prezzo), **rischio 4,17** (12,63 x 0,33), abbinato 12,63.
| Gol finali | Under 3,5 | Banca Under 4,5 | Totale netto |
|---|---|---|---|
| 0-3 | +7,10 x 0,95 = +6,75 | -4,17 | **+2,58** |
| 4 | -10,00 | -4,17 | **-14,17** (esito della registrazione) |
| 5 o piu' | -10,00 | +12,63 x 0,95 = +12,00 | **+2,00** |
Forma di prima sulla stessa partita: punta Over 4,00 (su 4,21) a 4,0: con 4 gol -14,00.
`cashout-dopo-copertura`: dopo la copertura (12,63 a 1,33) il cash out dell'utente chiude Under 3,5 e
copertura (banche a 1,77/1,78 sul 3,5 e 4,3 sull'Over 4,5 = M3.3); risultato -0,61, J5B mai violato.
`cap-stretto` in forma banca (tetto 12): lo misuro nel blocco 5 (valore di serie banca).

## 6. Impronta del referto (4B-B)
`registro_bot.py`, scheda di Mike: `moduli_produzione` = servizio + `engine`, `config`, `db`,
`dossier`, `feed`, `porta_ordini` (tutti i moduli di `Betfair/mike` che il servizio importa). Gli altri
bot NON toccati. Impronta prima: **`97c18d100ac7 (2 file)`**; dopo: **`556b2199684f (8 file)`** (codice
di questo worktree). Test di contratto: ogni modulo di `Betfair/mike/*.py` importato dal servizio
(letto con `ast`) deve stare nell'elenco; l'impronta cambia se cambia `engine.py` (copia temporanea).
Il test del registro esistente (`test_registro_bot_2026_09_16.py`) resta verde.

## 7. 4B-A: i sei test mancanti (`test_mike_p5_4b_2026_09_29.py`)
`falsifica_mike_p5_4b.py`: N3, N13, N14, N15, N17, N21 del coordinatore e I1 (motore fuori
dall'impronta): **7 su 7 ROSSE**. Codice non cambiato.

## 8. 4B-C: la differenza attesa di `punteggio-ko`
Nel replay completo dopo P2-bis (`9692eb4`) lo scenario `punteggio-ko` cambia rispetto al riferimento
precedente: fill 13,50 invece di 14,00, P&L -13,50 invece di -14,00, proposte di uscita 14/12 invece
di 18/16 (numeri del coordinatore). E' ATTESA: decisione dell'utente **M8.4** (P2-bis) - con il
punteggio ASSENTE `cover_timing` torna "wait" e la copertura ordinata dal flusso (`cover_forced`) non
la scavalca piu' (`engine.py`, guardia `snap.goals is not None`, in tutte e due le forme): per i 5 minuti
senza punteggio la copertura aspetta, e parte dopo a un'altra quota (punta Over 3,50 invece di 4,00:
DEDOTTO dal fill 13,50 = 10,00 + 3,50, non l'ho rieseguito io),
con meno giri in `LIVE_COVERED` e quindi meno proposte di uscita.

## 9. Suite
`Betfair/mike`: **1218 verdi** (anche il contratto pannello/config, ora che `cover_form` e' nel
pannello su master). `Betfair/stream/tests -k "registro or certifica or banco or motore"`: 436 verdi,
25 saltati.

## 10. Non verificato
- Lo scenario di rientro dopo la copertura-banca su una registrazione reale: nessuna delle nostre lo ha
  (la sintetica `_synth_mike_prezzo_migliore` copre copertura + chiusura + rientro: la lancio col blocco
  5, quando la banca e' di serie).
- La parita' coda/canale sugli scenari di rifiuto (leva assente sul canale, par. 5).
