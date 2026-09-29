# CANTIERE MIKE-MOTORE - Pacchetto P2: il pre-partita (29/09/2026)

Patch: `AUDIT_2026-09-29/MIKE_P2.patch`, SOPRA P1 (verificato: indice temporaneo = master
`2768f04` + `MIKE_P1.patch`, poi `git apply --check MIKE_P2.patch`: pulita). Nel `MIKE_P1.patch`
e' corretta la riga `working = [` come l'ha integrata il coordinatore. Nessun commit.

## 1. Cosa e' cambiato

| File | + / - |
|---|---|
| `Betfair/mike/engine.py` | +95 / -47 (47 righe tolte = il vecchio blocco "a 10' si ritira la banca, chiusura finale, veto che chiude") |
| `Betfair/mike/certificazione.py` | +40 (controlli D3, B6) |
| test esistenti (4 file) | +120 / -132 |
| `Betfair/mike/tests/test_mike_p2_prepartita_2026_09_29.py` | nuovo, 25 test |

`engine.py`, punto per punto:
- **M2.1 / M2.2** (`_decide_prematch`, ramo `PRE_OPEN` ora `PRE_OPEN` + `HOLD`): al segno
  dei 10 minuti con la posizione aperta NON si ritira la banca, niente chiusura al mercato, il
  veto non chiude piu' (punto "hold" del veto non piu' valutato: non avrebbe effetto). Si va in
  `HOLD`, che ora vuol dire "dopo il segno, posizione aperta, nessun ingresso fino al fischio":
  la banca appoggiata si tiene e, se sparisce (rifiuto, residuo cancellato), si rimette a 2 tick
  sotto sul residuo netto, come in `PRE_OPEN`. Le 5 `return Decision("PRE_OPEN", ...)` del ramo
  diventano `Decision(st, ...)` (per `PRE_OPEN` identiche a prima).
- **M2.4** (nuova `_ultimo_ingresso`, chiamata da `WATCH` dopo il segno): Mike piatto al segno
  -> ultimo ingresso = un ingresso come gli altri (`under_entry`, LAPSE, miglior back, stake),
  passando da `_entry_guard` (tutti e 13 i controlli, con la sola finestra "troppo tardi" tolta
  perche' e' proprio questo segno); all'abbinamento `_after_entry_fill` appoggia subito la banca
  a 2 tick sotto (LAPSE) e al giro dopo si va in `HOLD`. Valutato UNA volta: una gamba nata dopo
  il segno, o un controllo che non passa, portano in `HOLD` (nessun ingresso fino al fischio).
  Prezzi non vivi o mercato sospeso non sono una valutazione: si aspetta (regola del 15/09
  "una sospensione non e' una rinuncia"). Il veto (punto "persist") blocca ancora l'ultimo
  ingresso, con la stessa telemetria `veto_under_calibrata`. `last_entry_persist` resta
  l'interruttore dell'ultimo ingresso (spento a bot fermo o dopo un cash out manuale:
  `WATCH` come oggi, "finestra pre-match chiusa").
  Se la banca si abbina DOPO il segno: giro chiuso restando in `HOLD` (non si rientra).
- **M2.3** (transizione al fischio e `_decide_ko_green`): al fischio posizione piatta (banca
  abbinata per intero, nessuna lay in volo) -> giro chiuso col suo profitto, `IDLE_LIVE`
  (telemetria `pre_cycle`); in `LIVE_KO_GREEN`, finche' la banca pre-partita e' viva o a
  esito ignoto per Mike, si aspetta di LEGGERNE l'esito ("al fischio: attendo l'esito della
  banca pre-partita ...") prima di qualunque decisione del gioco (A, B, C); letta la banca:
  piatta -> `IDLE_LIVE`; in parte o per niente -> flusso del gioco invariato sulla posizione
  vera (uscita al fischio sull'esposizione netta residua). Al fischio il motore chiede comunque
  l'annullamento della banca (come faceva per ogni ordine vivo): se Betfair l'ha gia' cancellata
  (LAPSE) il servizio lo legge.
- **Verifica del coordinatore sul P1**: test nuovo "una lay in volo su un'ALTRA selezione non
  ferma la chiusura manuale" (mutazione M11 del coordinatore ora ROSSA). Riga `working = [`
  rimessa com'era.

Nessuna firma, nome di stato, ruolo, chiave di parametro o di telemetria cambiati.

## 2. Collegamenti controllati
`HOLD`/`PRE_OPEN`/`PRE_GREEN_PENDING`/`PRE_LAST_ENTRY_PENDING`: service.py:4066 (rientro da
falso regolamento a `PRE_OPEN`: compatibile, al giro dopo il segno va in `HOLD`), frontend
`lib/mike.ts` (etichette stati, invariati), SQL CHECK degli stati (invariati, nessuno nuovo).
`last_entry_persist`: service.py:1275 e 3557 (spento a bot fermo / cash out): rispettato.
`under_last`: frontend (etichette), certificazione B1/F2: non piu' prodotto.
`_entry_guard`: chiamato solo da engine (WATCH e ora `_ultimo_ingresso`, con
`dict(params, pre_last_entry_min=0)`: nessuna firma cambiata).

## 3. Test esistenti aggiornati (decisioni 2, 3, 5, 6, 7 del piano)
| Test | Diceva | Dice ora | Decisione |
|---|---|---|---|
| engine `test_last_entry_in_profit_greens_then_places_persist` -> `..._keeps_the_green_until_ko` | a 10' in profitto: ritiro green, chiusura finale, PERSIST | la green resta, HOLD, nessun `under_last`; al fischio si chiede l'annullamento della green | M2.1, M2.4 |
| engine `test_last_entry_in_loss_holds_into_live` | a 10' la green si annulla | nessuna azione | M2.1 |
| engine `test_last_entry_persist_disabled_goes_idle_live` -> `..._no_last_entry` | chiusura finale + niente PERSIST -> IDLE_LIVE | piatto al segno, interruttore spento: WATCH, nessun ingresso; al fischio IDLE_LIVE | M2.4 |
| engine `test_unmatched_persist_cancelled_after_ko_grace` | PERSIST nato dal flusso | stesso controllo su una partita salvata PRIMA (stato vecchio `PRE_LAST_ENTRY_PENDING`) | stati vecchi |
| engine `test_last_entry_with_partial_green_uses_net_exposure` | green parziale ritirata, chiusura taker sul residuo | green parziale resta; se il residuo sparisce si rimette a 1,48 sul residuo netto | M2.1 |
| service `test_last_entry_cancels_resting_green_in_loss` -> `..._keeps_...` | green cancellata a 10' | green `pending`, nessun `cancel` | M2.1 |
| veto `test_hold_spento_tiene_come_oggi_anche_con_p_bassissima` | HOLD + cancel | HOLD, nessuna azione | M2.1 |
| veto `test_hold_acceso_p_sotto_soglia_a_quota_150_chiude` -> `..._non_chiude_piu` | lay finale di chiusura in perdita | HOLD, nessuna azione, nessun veto registrato | M2.2 |
| veto `test_hold_acceso_p_sopra_soglia_a_quota_150_tiene` | telemetria punto "hold" | nessuna telemetria "hold" | M2.2 |
| veto `test_hold_coi_parametri_di_default_il_veto_scatta` -> `..._non_chiude` | green annullata per chiudere | HOLD, nessuna azione | M2.2 |
| veto `test_hold_acceso_senza_p_calibrata_tiene_e_lo_dichiara` -> `test_hold_acceso_senza_p_calibrata_tiene` | telemetria "non_valutabile" al punto hold | HOLD, nessuna telemetria | M2.2 |
| veto `_fino_al_persist` + 5 test `test_persist_*` | ultimo ingresso `under_last` PERSIST dopo la chiusura finale; veto -> IDLE_LIVE | ultimo ingresso da piatto al segno: `under_entry` LAPSE; veto -> HOLD (stessa telemetria, `eseguito`) | M2.4 |
| veto `test_servizio_acceso_in_perdita_p_sotto_soglia_chiude_e_lo_scrive` -> `..._non_chiude_piu` | chiusura finale in perdita via servizio | HOLD, green `pending`, nessun veto | M2.2 |
| veto `test_servizio_acceso_in_perdita_p_sopra_soglia_tiene_e_lo_scrive` -> `..._tiene` | attivita' punto hold | HOLD, nessuna attivita' hold | M2.2 |
| P1 `test_chiusura_del_veto_pre_partita_resta_governata_in_p1` -> `..._non_parte_mai` | proposta in perdita | nessuna chiusura e nessuna proposta | M2.2 |

## 4. Test nuovi (25) e falsificazione
Banca al segno in profitto/in perdita; veto che non chiude; banca rimessa se manca; banca
abbinata dopo il segno (piatto, niente rientro fino al fischio); ultimo ingresso da piatto con
banca subito; controlli d'ingresso (spread) e valutazione unica; FOK non abbinato non si rifa;
veto blocca/non blocca; interruttore spento; sospeso e prezzi non vivi = attesa; con posizione
nessun ingresso; taker; al fischio banca abbinata per intero / non abbinata (LAPSE letto) / in
parte / scoperta abbinata dopo il fischio / gol con banca da leggere; stati vecchi ripresi senza
ERROR; banco D3, B6; chiusura manuale con lay in volo su un'altra selezione.

`AUDIT_2026-09-29/mike_p2/falsifica_mike_p2.py`: M0 (motore intero del P1) ROSSO 18 test;
M1-M8, M11, M9 (D3 muto), M10 (B6 muto): tutte ROSSE. Ripristino verificato (hash).

Suite: `Betfair/mike` **1075 verdi**; `-k "mike or banco or certifica or uscite"` con
`Betfair/stream/tests`: 1428 verdi, 25 saltati.

## 5. Replay (`AUDIT_2026-09-29/mike_p2/replay_p2_mike_tutti.txt`, comando del brief)
**15/15 OK, 0 violazioni.** Tempi (s | tick/s): base 177,2|317; taker 188,7|297; cap-stretto
180,0|312; bot-fermo 95,4|589; senza-seconda-puntata 134,7|417; feed-stantio 93,9|599;
esiti-ignoti 128,8|436; taker-esiti-ignoti 119,9|469; riavvio 130,3|431; gol-precoce 134,8|417;
cashout-globale 121,7|462; chiuso-fuori-app 137,0|411; copertura-rifiutata 190,4|295;
rifiuti-betfair 170,6|330; chiusura-abbinata-in-parte 174,7|322. Totale 785 s (LENTO, PC
condiviso con l'altro delegato: stessa riserva del P1).
Rispetto al P1: base azioni 7 -> 6 (niente annullo della banca al segno), motivo "in perdita
pre-KO: tengo fino al live" x213 sparito, la banca resta ("posizione aperta, green resting sul
book" x974); "ordini appoggiati uccisi dal passaggio in gioco (LAPSE): 1" (era 0): la banca
pre-partita cancellata da Betfair al fischio, letta dal servizio (`runner_scaduto`). D3
sollecitato 11.728 volte, 0 violazioni. B6 non sollecitato: su questa registrazione al segno
Mike ha sempre la posizione aperta (niente ultimo ingresso) -> provato solo dai test.

## 6. Stati, ruoli, parametri rimasti senza uso (NON cancellati)
- `PRE_LAST_ENTRY_PENDING` e ruolo `under_last`: non piu' prodotti; restano per le partite
  salvate prima (il loro codice, `_late_persist_cancel`, `cancel_unmatched_after_ko_s`, e'
  invariato e provato da `test_unmatched_persist_cancelled_after_ko_grace`).
- `_after_final_green` e green "finale" (`final=True`): non piu' prodotti; `PRE_GREEN_PENDING`
  resta raggiungibile in modo taker (green taker non finale) e dalla chiusura manuale.
- Ramo `if st == "HOLD": return ... "tengo fino al live"` in `_decide_prematch`: ora
  irraggiungibile (HOLD passa dal ramo PRE_OPEN/HOLD); lasciato com'e'.
- `VETO_U35_NOTE`: non piu' usata dal motore (resta come costante; G2 la guarda).
- `last_entry_ticks_above` (default 0): non piu' letto (l'ultimo ingresso e' al miglior back
  come ogni ingresso). Il testo del pannello "Ultimo ingresso in PERSIST" (`lib/mike.ts:459`) e
  le etichette "ULTIMO (PERSIST)" vanno riallineati in UI (pacchetto P6).
- Attivita' `veto_under_calibrata` con `punto: "hold"`: non piu' scritta.

## 7. Cosa NON ho potuto verificare
- Sul replay: l'ultimo ingresso (B6 a zero casi) e la banca abbinata per intero prima del
  fischio (non capitano su 35760084); coperti solo dai test.
- Quanto tempo resta "viva" per Mike la banca pre-partita dopo il fischio in LIVE: dipende dalla
  lettura dell'ordine nel servizio (P4, M6.2). Finche' non la sa, Mike aspetta in
  `LIVE_KO_GREEN` (non copre e non esce): se in live l'esito restasse ignoto a lungo, la
  finestra dei 3 minuti puo' scadere nell'attesa; e' la stessa attesa che il codice di prima
  faceva su una lay a esito ignoto, ma ora capita a OGNI partita portata in gioco.
- Paper/live vero.

## 8. Rischi per le partite gia' in corso all'aggiornamento
- In `PRE_OPEN` dopo il segno (impossibile col codice vecchio) o in `HOLD` (codice vecchio: banca
  gia' ritirata): al primo giro la banca a 2 tick sotto viene RIMESSA fino al fischio (M2.1).
- In `PRE_GREEN_PENDING` con una chiusura "finale" viva (codice vecchio): finisce col percorso
  vecchio (`_after_final_green` -> PERSIST); in manuale una chiusura finale del veto era una
  proposta.
- In `PRE_LAST_ENTRY_PENDING`: invariato fino al fischio.

## 9. Decisioni per l'utente
- L'ultimo ingresso passa da TUTTI i controlli d'ingresso, compresa la pausa di 60 s dopo un
  giro chiuso: se la banca si abbina nei 60 s prima del segno, al segno la pausa blocca l'ultimo
  ingresso (e resta bloccato: si valuta una volta). Letto alla lettera dal piano; da confermare.
- Prezzi non vivi o mercato sospeso al segno: l'ultimo ingresso aspetta che tornino (fino al
  fischio) invece di rinunciare. Da confermare.
