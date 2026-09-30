# MIKE - seconda ondata sul BOT (30/09/2026, ordini dell'utente del 30/09)

Delegato di costruzione, worktree `agent-a43a3bb23bedf6ad4`. **Non certificato**: lo certifica il
coordinatore (diff, test, replay rieseguiti di persona).

## Base di lavoro (da leggere prima)
- Il worktree era su `fc0428f` (NON conteneva `a7e9f66`): portato a `a7e9f66` (`git reset --hard`
  sul MIO ramo, worktree pulito), poi applicata `BANCO_QUATTRO_DIFETTI.patch` con
  `git apply --3way --ignore-whitespace` (pulita; i file del banco sono in STAGE nel mio indice).
- Le mie modifiche sono NON in stage: `MIKE_BOT_ONDATA_2.patch` = `git diff` (albero contro indice)
  = SOLO le mie modifiche, SENZA la patch del banco (verificato: 0 righe di `banco_comune`,
  `registro_bot`, `trasporto`, `_CACHE_DI_PROCESSO`). Il file di test nuovo e' `git add -N`.
  Ordine di applicazione: `a7e9f66` -> `BANCO_QUATTRO_DIFETTI.patch` -> `MIKE_BOT_ONDATA_2.patch`
  (`git apply --cached --check` sulla base: pulito).
- Nessun commit, nessun replay, nessun `pip/npm install`.

## File toccati
| File | Punto |
|---|---|
| `Betfair/mike/service.py` | 1 (`_esegui_annulli`, ramo del regolamento), 4 (`_registra_resti`), 6 (`_aggiorna_riga_resting`) |
| `Betfair/mike/engine.py` | 2 (fischio), 3 (`uscita_in_perdita`, `_decide_reentry_open`) |
| `Betfair/mike/certificazione.py` | 3, SOLO `_g3` (+ il suo aiuto `_bloccato_uscita_rientro`, usato solo da `_g3`) |
| `frontend/src/lib/mike.ts` | 4 (`MIKE_ACTIVITY_KINDS`, `MIKE_ACTIVITY_EXTRA`, `mikeActivityLine`) |
| `Betfair/mike/tests/test_mike_ondata2_2026_09_30.py` | NUOVO, 19 test (tutti i punti) |
| `Betfair/mike/tests/test_mike_engine.py` | 2 (test esistente aggiornato) |
| `Betfair/mike/tests/test_mike_p2_prepartita_2026_09_29.py` | 2 (test esistente aggiornato) |
| `Betfair/mike/tests/test_mike_resting_live_2026_09_14.py` | 6 (test esistente aggiornato) |
| `Betfair/mike/tests/test_mike_audit_2026_09_11.py` | 4 (elenco dei kind dichiarati) |
| `AUDIT_2026-09-30/falsifica_mike_ondata2.py` + `.out` | script e uscita delle falsificazioni (fuori dalla patch) |

---

## 1. Il regolamento non eseguiva gli annulli (CRITICO, revisione C1-aggiunta)
**Causa.** `service.py` ramo `if closed and ctx.state not in E.TERMINAL_STATES` (ora ~4406-4520):
chiamava `E.decide` -> `Decision("SETTLING", _cancel_live(ctx), ...)` (`engine.py` `_dispatch`,
~2821) e `E.apply_decision`, che per contratto NON tocca le `cancel` ("e' il chiamante a marcare").
Nessuno eseguiva gli annulli; nello stesso giro la seconda `decide` passava a `SETTLED`
(`settle_legs` conta solo l'abbinato) con la gamba ancora `pending` e l'ordine vivo sul book; e il
ramo usciva prima di `_sorveglia_gambe` (niente esiti del runner, niente riconciliazione).
Riprodotto: riga con 4 gol, 3,5 e 4,5 CLOSED, banca Under 4,5 di copertura appoggiata sul runner
-> 0 `cancel` al runner, partita SETTLED con la riga della copertura ancora `pending` (test rosso
sul codice di prima: `kinds = [..., 'settled']`, `runner.comandi` senza cancel).

**Correzione (minima).**
- `_esegui_annulli` (`service.py:4291`): il ciclo degli annulli che stava in `_run_event` estratto
  in una funzione (codice identico; unica differenza `extra.get("deferred") or []` perche' nel ramo
  del regolamento `deferred` puo' mancare). Il giro normale ora chiama la funzione (stessa strada).
- Nel ramo del regolamento:
  a) se ci sono gambe vive o a esito ignoto, a OGNI giro (anche nel throttle) `_sorveglia_senza_dati`
     (esiti del runner, posizione di conto, gambe stantie, riconciliazione, lay appoggiate) -
     la stessa sorveglianza dei giri senza dati (M8.8);
  b) dopo il throttle, `_esegui_annulli(actions=E._cancel_live(ctx))`: sono esattamente gli annulli
     della decisione SETTLING del motore; si ripetono al giro di regolamento successivo se una gamba
     torna viva dalla riconciliazione;
  c) finche' una gamba e' viva o `pending_reconcile` -> stato `SETTLING` ("attesa dell'esito degli
     ordini ancora aperti"), persistenza, uscita: nessuna riga regolata. Questo copre anche i rami
     che prima regolavano SENZA guardare gli esiti ignoti: mercato ANNULLATO (void per mercato),
     ripiego sull'ultimo punteggio dopo 2 h, "P&L indipendente dal risultato".
- Nessuna decisione di strategia cambia: QUANDO annullare lo decide il motore come prima.

**Test** (`test_mike_ondata2_2026_09_30.py`, `run_once` vero, `FakeDB`/`FakeMarket` di
`test_mike_service`, runner finto sul protocollo vero, banca piazzata con `_piazza_resting_paper`):
- `test_c1_linea_in_gioco_chiusa_la_copertura_in_volo_si_annulla_poi_si_regola`: 1 cancel al runner
  col bet_id dell'ordine, gamba `cancelled`, attivita' `cancel`, poi SETTLED e riga non pending;
- `test_c1_riga_assente_oltre_la_grazia_la_copertura_in_volo_si_annulla` (ramo `absent_closed`);
- `test_c1_annullo_senza_esito_il_regolamento_aspetta_e_la_sorveglianza_continua`: annullo non
  confermato -> `pending_reconcile`, SETTLING, riga `pending`; l'esito arriva -> la sorveglianza lo
  legge -> SETTLED;
- `test_c1_mercato_annullato_non_si_regola_con_un_ordine_senza_esito` (ramo void);
- `test_c1_confine_senza_ordini_vivi_il_regolamento_e_quello_di_prima` (confine, verde anche prima).

**Falsificazione:** M1a (annulli del regolamento non eseguiti) ROSSA 4 test; M1b (niente attesa
degli esiti) ROSSA `test_c1_mercato_annullato...`; M1c (niente sorveglianza) ROSSA
`test_c1_annullo_senza_esito...`. Prima della correzione i primi 3 test erano rossi (visto).

## 2. Nessun annullo della banca LAPSE al fischio (decisione dell'utente, M2.1)
**Causa.** `engine.py` `_decide_prematch`, ramo `if snap.inplay:` (~2995-3025): ogni gamba viva
riceveva `cancel` (eccetto `under_last` PERSIST in grazia), quindi anche la banca pre-partita
`under_green`. Origine dei 19 "annullo NON confermato" (M1 della revisione).
**PERSIST o LAPSE?** Verificato: tutte e 4 le `_place("under_green", ...)` (`engine.py` ~3120-3200)
usano il default `persistence="LAPSE"`; il comando paper al runner porta `persistence: LAPSE`
(assertito nel test). Quindi la banca e' LAPSE.
**Correzione.** `engine.py:3015`: al fischio `under_green` NON PERSIST non riceve l'annullo
(`continue`); PERSIST resta annullata come prima. Il resto era gia' pronto: `_decide_ko_green`
(~3435) aspetta l'esito della banca (`is_live or needs_reconcile`), che si LEGGE (live:
`_segui_resting_live`/M6.2 per bet_id; paper: runner). Abbinata -> piatto (`IDLE_LIVE`, giro chiuso);
scaduta -> `LIVE_KO_GREEN` come oggi; parziale -> esposizione dai fill (test esistente
`test_m2_3_banca_abbinata_in_parte_l_uscita_al_fischio_sul_residuo`, invariato e verde).
**Test** (servizio intero, runner): `test_m2_al_fischio_nessun_annullo_della_banca_lapse` (nessun
cancel al runner, nessun `cancel`/`cancel_richiesto`, gamba pending, LIVE_KO_GREEN);
`test_m2_banca_abbinata_letta_dopo_il_fischio_posizione_chiusa` (IDLE_LIVE, esposizione piatta,
nessun ordine nuovo); `test_m2_banca_scaduta_letta_dopo_il_fischio_si_va_al_ko_green`;
`test_m2_confine_banca_persist_si_annulla_ancora` (motore: PERSIST -> cancel, LAPSE -> nessuno).
**Test esistenti aggiornati (giustificazione: la decisione dell'utente del 30/09 cambia proprio
quell'asserzione):**
- `test_mike_engine.py::test_last_entry_in_profit_keeps_the_green_until_ko`: era
  `actions == [("cancel","under_green")]`, ora `actions == []` e banca ancora viva;
- `test_mike_p2_prepartita_2026_09_29.py::test_m2_3_banca_non_abbinata_cancellata_da_betfair_parte_il_flusso_del_gioco`:
  era `_annulli(d) == ["under_green"]`, ora `[]` (il resto del test, attesa dell'esito e ko_green dopo
  lo scaduto, invariato).
**Falsificazione:** M2a (annullo rimesso) ROSSA 6 test (i 2 aggiornati + 4 nuovi); M2b (anche PERSIST
non annullata) ROSSA `test_m2_confine...`.

## 3. Uscita a tempo del rientro in profitto parte da sola (decisione dell'utente)
**Causa.** `engine.py:2598` `uscita_in_perdita`: `reentry_time` sempre "in perdita" -> sempre
proposta. **Correzione.** `_decide_reentry_open` (ramo `reentry_exit_until_min`, ~4395) mette nella
decisione la telemetria `uscita_a_tempo = {bloccato, in_perdita}` con `bloccato = min(expected_if_win,
expected_if_lose)` del piano di chiusura che parte davvero (stesso ordine, stessi prezzi; la
commissione non cambia il segno). `uscita_in_perdita`: `reentry_time` in perdita solo se
`bloccato < 0`; senza il numero resta in perdita (fail-closed). `certificazione.py::_g3`:
`reentry_time` lasciata come proposta e' violazione se la chiusura al miglior prezzo, RICALCOLATA
dal controllo dalle gambe e dal libro (`_bloccato_uscita_rientro`, non dalla telemetria del
motore), bloccherebbe >= 0.
**Test:** `test_m3_reentry_time_in_profitto_parte_da_sola_in_manuale` (manuale = automatico, nessuna
proposta, telemetria con chiavi e tipi); `test_m3_reentry_time_in_perdita_resta_proposta`;
`test_m3_reentry_time_senza_numero_resta_in_perdita`; `test_m3_banco_g3_coerente_con_reentry_time`
(G3 parla sulla proposta in profitto, tace in perdita e sul motore vero nei due casi). Il test
esistente `test_chiusura_a_tempo_del_rientro_resta_governata` (caso in perdita, 1,60 -> 1,72) resta
invariato e verde.
**Falsificazione:** M3a (sempre in perdita) ROSSA 3; M3b (sempre in profitto) ROSSA 2 (compreso il
test esistente); M3c (G3 muto) ROSSA 1.
**ATTENZIONE - G2 NON aggiornato (fuori dal mio perimetro, lo tocca un altro delegato):**
`certificazione.py::_motivo_perdita` (~507) considera ancora `reentry_time` SEMPRE in perdita. Con
uscite manuali, una chiusura a tempo del rientro IN PROFITTO ora parte senza firma e G2 la
segnalerebbe come violazione ("uscita in perdita (reentry_time) partita senza la sua firma"): falso
positivo. Oggi non puo' accadere sul banco (`reentry_exit_until_min` di serie 0 e nessuno scenario lo
cambia: verificato con grep), ma va allineato da chi tocca G2: `reentry_time` e' perdita solo se il
P&L bloccato ricalcolato e' < 0 (si puo' riusare `_bloccato_uscita_rientro`).

## 4. Il resto sotto minimo nel registro (decisione 26, M3.5; revisione M4)
**Causa.** Le telemetrie `cover_resto_sotto_minimo` (`_copertura_banca` ~3951,
`_riprezzo_copertura_banca` ~4109) e `residuo_non_piazzabile` (`_tele_residuo`, 5 punti) non erano
nella tupla dei kind che il servizio scrive (`service.py` ~4880): restavano in memoria.
**Correzione.** `_registra_resti` (`service.py:4258`), chiamata dopo il ciclo della telemetria
(`:4936`): una riga di `mike_activity` per episodio (firma `kind|ciclo|importo`, ultime 10 in
`ctx.resti_scritti`), con le chiavi della telemetria del motore + `state` + `ciclo` (int).
Non li ho messi nella tupla generica perche' quella scrive a OGNI emissione, senza la regola
"una volta per episodio"; i `db.log("...")` sono letterali cosi' il contratto dei kind li trova.
Dichiarati in `test_l5_tutti_i_kind_di_attivita_sono_dichiarati` e in `mike.ts`:
`MIKE_ACTIVITY_KINDS` + `MIKE_ACTIVITY_EXTRA` (etichette "COPERTURA: RESTO SOTTO IL MINIMO",
"RESTO NON PIAZZABILE") + righe in `mikeActivityLine` (chiavi `resto`, `minimo`, `sbilancio`,
`state`). Il contratto Python backend<->UI (`test_contratto_ogni_kind_di_attivita_del_backend_e_dichiarato_in_ui`) e' verde.
**Test:** `test_m4_resto_sotto_minimo_della_copertura_e_una_riga_del_registro` (`run_once`, due giri,
UNA riga, `resto` 0.33 float, `minimo`, `form`, `state`, `ciclo` int, nessun ordine al runner);
`test_m4_una_riga_per_episodio_e_residuo_non_piazzabile`.
**Falsificazione:** M4a (niente registro) ROSSA; M4b (a ogni emissione) ROSSA.

## 5. Due prove mancanti (revisione M3)
Il codice era gia' giusto in entrambi i casi: aggiunti SOLO i test.
- **B-6** `test_m5_b6_banca_uscita_dai_correnti_letta_abbinata_per_bet_id`: sportello di PRODUZIONE
  `omega_market.order_state_by_bet_id` su client con le chiavi grezze di Betfair (`ClientBetfair` di
  `test_mike_p4_ordini`), regolato SETTLED 10,14 a 1,47 -> gamba `open`, abbinato e prezzo veri,
  `rilettura_alla_riapertura` esito "abbinato" fonte "fuori_dai_correnti", niente riconciliazione.
  Mutazione M5a (togliere `_ESITO_ABBINATO` dalla tupla, `service.py:2472`) ROSSA.
- **B-10** `test_m5_b10_tetto_per_partita_sul_rischio_al_prezzo_LIMITE`: banca 12,63, miglior 1,18,
  limite 1,20, spazio 2,40: al miglior prezzo ci starebbe (2,27), al limite no (2,53) -> size 12,00;
  confine con spazio 2,60 -> 12,63. Mutazione M5b (rischio e riduzione al miglior prezzo,
  `engine.py:3957-3960`) ROSSA.

## 6. Righe ko_green scadute: parita' coda/canale
**Causa.** `service.py::_aggiorna_riga_resting` scriveva `size = leg.matched` a ogni
aggiornamento, anche 0 o parziale. Sulla strada LIVE/REST (trasporto `coda`) viene chiamata SUBITO
al piazzamento della lay appoggiata (`_piazza_resting_live`, "live_resting_piazzato", matched 0):
la riga passava a `size 0.00` e ci restava allo scaduto (`_chiudi_gamba_scaduta` riscrive `size`
solo se abbinato > 0). Sulla strada paper/runner (`canale`) la riga non si tocca finche' l'ordine non
finisce, e allo scaduto `size` resta il chiesto (10,12). Tutte le altre chiusure di riga del servizio
(`_segui_ordini_paper_su_runner` terminale, `_chiudi_gamba_scaduta`, `_mark_trade_cancelled`,
conferma della riconciliazione) scrivono `size = abbinato` SOLO se abbinato > 0: la convenzione e'
`size` = chiesto finche' non c'e' un abbinato, e l'abbinato vive in `size_matched`
(`migrations/trades_consapevolezza_ordine_2026-09-16.sql`: `size_requested` chiesto, `size_matched`
abbinato). Giusta la riga del canale. Effetto collaterale del difetto: una riga `pending` live
ricostruita in gamba da `_gamba_dalla_riga` nasceva con size 0.
**Correzione.** `_aggiorna_riga_resting` (`service.py:2203-2213`): `size = abbinato` solo quando
l'ordine e' finito abbinato (`leg.status == "open"`); chiesto/abbinato/residuo restano nelle colonne
di consapevolezza (invariate).
**Test:** `test_m6_ko_green_scaduta_stessa_riga_in_live_e_in_paper` (la stessa lay 10,12 @ 1,69:
live piazzata con `_piazza_resting_live`, letta scaduta per bet_id; paper piazzata col runner,
`scadi`: `status/side/price/size` identici, size 10,12, `size_matched` 0, `size_requested` 10,12);
`test_m6_confine_abbinata_per_intero_size_e_l_abbinato`.
**Test esistente aggiornato:** `test_mike_resting_live_2026_09_14.py::test_l_uscita_appoggiata_SENZA_abbinamento_scrive_subito_chiesto_e_residuo`
fissava `size == 0.0` (il difetto): ora `"size" not in` l'aggiornamento (resta il chiesto della
riserva); le altre asserzioni (chiesto 10,14, abbinato 0, residuo 10,14, pending) invariate.
**Falsificazione:** M6 (size = abbinato anche a 0) ROSSA 2 (il nuovo e quello aggiornato).
**Nota:** un ordine live abbinato IN PARTE e ancora vivo ora tiene `size` = chiesto (come in paper);
prima portava il parziale. Il parziale e' in `size_matched`.

---

## Test (ambiente neutro di `replay_mike.sh`, python del `.venv` principale)
- `python -m pytest Betfair/mike -q -p no:cacheprovider -o addopts= -W ignore`:
  **1295 passed** (base con la patch del banco: 1276; +19 nuovi).
- `python -m pytest Betfair/stream/tests -q ...`: **3134 passed, 25 skipped, 0 failed** (211 s;
  uguale al referto del banco).
- Falsificazioni: `AUDIT_2026-09-30/falsifica_mike_ondata2.py` (base verde prima e dopo nello
  stesso script, ripristino dalla copia con sha256, file CRLF gestiti); uscita in
  `falsifica_mike_ondata2.out`: **13 mutazioni, 13 ROSSE**, base 147/147 prima e dopo;
  `grep MUTAZIONE` = 0, `git diff` identico a prima.

## Copertura §6 / catalogo §7
- §6.3 servizio intero (`run_once`) per i punti 1, 2, 4; §6.4 ciclo di vita dell'ordine (annullo,
  esito ignoto, LAPSE al passaggio in gioco, abbinato per bet_id, tetto al limite); §6.5 righe
  (`size`/`size_matched`, kind nuovi con etichetta italiana).
- §7: 1/27 (finti con chiavi vere: `ClientBetfair` camelCase, runner sul protocollo vero, righe
  `mike_trades`), 2 (`res.ok`/esito letto prima di dichiarare annullato), 4/7 (bet_id), 14 (parita'
  paper/live della riga), 17 (chiuso vs sospeso: il regolamento non abbandona gli ordini), 28 (tre
  test esistenti che fissavano il comportamento sbagliato, aggiornati e motivati), 29/30/35 (ogni
  test nuovo visto rosso), 34 (la sorveglianza gira anche nel ramo del regolamento).

## Parita' paper/live
Punto 1 e 2: stessa strada in paper e live (annullo via runner in paper, REST in live; esito letto
da runner / per bet_id). Punto 6 RENDE uguali le righe dei due trasporti. Punto 3: solo motore.

## Divergenze / decisioni per l'utente
- Nessuna decisione di strategia presa da me oltre alle tre dell'utente (punti 2, 3, 4).
- Punto 1: con un ordine a esito ignoto la partita resta SETTLING finche' l'esito non si legge,
  anche oltre le 2 h (`_SETTLE_MAX_WAIT_S` non porta piu' a regolare/ERROR con un ordine forse vivo).
  E' la regola "mai righe regolate su un ordine forse vivo"; se l'utente vuole un tetto di tempo
  anche qui, va deciso (proposta: ERROR con elenco degli ordini non risolti dopo 2 h).
- Punto 3: "profitto" = P&L della sola selezione Under 4,5 chiusa al miglior prezzo (quello che
  l'ordine blocca), non il cash out dell'intera partita. Se l'utente intende l'intera partita, va
  detto.

## COSA NON HO POTUTO VERIFICARE
- **Nessun replay** (vincolo): non so se i 19 "annullo NON confermato" del referto spariscono, ne'
  come cambiano i numeri dei referti (lo scenario del fischio ora non manda l'annullo: attesi
  meno `cancel_richiesto`/`cancel_esito`, J4 e B3 diversi, stati LIVE_KO_GREEN piu' lunghi finche'
  lo scaduto non e' letto). Da confrontare scenario per scenario.
- La parita' coda/canale del punto 6 e' provata con i finti (MercatoFinto con chiavi di
  `omega_market`, runner finto), NON sul banco: il coordinatore deve rilanciare
  `copertura-rifiutata --trasporto entrambi` e vedere le righe 2-4 uguali.
- Punto 1 sul banco: il banco oggi non passa i mercati CLOSED (A6 della revisione): il ramo del
  regolamento con ordini vivi e' provato solo nei test.
- Frontend: `mike.ts` modificato ma **tsc e vitest NON lanciati** (li lancia il coordinatore); il
  contratto Python backend<->UI e' verde.
- G2 (`_motivo_perdita`) non allineato al punto 3 (fuori perimetro): vedi sopra.
- Il comportamento vero di Betfair per una banca LAPSE al passaggio in gioco (scaduta dai correnti
  e letta per bet_id come LAPSED) e' quello gia' assunto da M2.3/M6.2: non verificato su ordini veri.
- Un ordine live abbinato in parte e ancora vivo: `size` ora resta il chiesto; non ho verificato
  a mano che nessuna vista del frontend legga `size` come abbinato su righe `pending` (ho visto che
  il paper faceva gia' cosi').
