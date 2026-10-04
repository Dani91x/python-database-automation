# CERTIFICAZIONE TENNIS PRO e TENNIS SCALPER (04/10/2026)

Ramo `worktree-agent-a1a759f4267f021ea` (da master `e578802`). Commit: `7b6d1a3` (B8 dalla fonte unica,
B10, scenari soldi-veri + SV1, patch K1 preparata), `3f53743` (B8: passo della punta parametrico).
Registrazione 35794049 (COMPLETE 99,1%), `--data-dir C:/Users/Admin/Desktop/tennis_rec/20260707`.
Referti: `AUDIT_2026-10-04/replay/cert_pro_scalper/`. Nessun file del coordinatore toccato
(`minimi_it`, `minimi_banco`, `live_order_build`, `mike/**`, `trading/submin.py`), nessuna strategia toccata.

---

# SECONDA CONSEGNA - decisioni dell'utente applicate (04/10, sera)

Ramo rifuso con master `65ff19e` (`663953f`). Commit: `f4c8176`, `1709c81`, `6e30e44`, `80b061e`, `e3e0ae8`.
Decisione 1 («1) a» + «IL RESIDUO RESTA RICORDATO E LO CHIUDO IO») applicata a pro e scalper. Decisione 2
(«I SOLDI VERI LI ACCENDO SEMPRE E SOLO IO»): **nel ramo NON c'e' nessun riarmo automatico in soldi veri**; la
proposta R1 (§6 sotto) e' RITIRATA, non costruita. Gli scenari `soldi-veri*` provano solo il gesto dell'utente
(riga del bot live + «Ordini reali» LIVE dichiarati), non accendono niente.

## A. Verdetti

| bot | verdetto | perche' |
|---|---|---|
| **tennis_pro** | **CERTIFICATO su 35794049**, 9/9 scenari OK (decisione 1, regola dei minimi di oggi in `minimi_it`) | nessun rifiuto per taglia (prima 221-226), riprende a operare (base 5 ingressi, live 14; prima 1 e 2), residui dichiarati una volta |
| **tennis_scalper** | **CERTIFICATO su 35794049**, 9/9 scenari OK, K1 sparito SENZA la patch del banco | nessun rifiuto per taglia (prima 11), nessuna sequenza sotto 0,50, ciclo chiuso col residuo dichiarato |
| tennis_flb, tennis_swing | invariati (6/6 OK, azioni 1 e 0) | non arrivano a una chiusura su questa partita: la regola nuova di `UsciteEsatte` (niente trim sotto 0,50) vale anche per loro ma **non e' sollecitata** |
| safe_tennis | invariato: 18 OK, parita' coda 1053/2, canale 1054/2 RAGGIUNTA, righe identiche al riferimento | - |

**Condizione:** quando l'altro delegato porta su master la regola delle punte (passo 0,50 in `minimi_it`/`minimi_banco`)
vanno rifatti merge e replay (ad oggi `minimi_it` dice punta al centesimo; i bot tennis usano gia' il passo 0,50
per le punte d'USCITA con `IT_PASSO_PUNTA_RIPIEGO`).

## B. Bot x scenario: prima (tetto, mattina) / dopo (azioni, esito)

| scenario | pro prima | pro dopo | scalper prima | scalper dopo |
|---|---|---|---|---|
| base | KO B10, 1868 | OK, 37 | OK, 1 | OK, 1 |
| live | KO B8/B10, 1816 | OK, 102 | KO K1, 125 | OK, 248 |
| gate-aperto | KO B10, 1816 | OK, 102 | KO K1, 125 | OK, 248 |
| parziali | KO B10, 1610 | OK, 56 | OK, 1 | OK, 1 |
| uscite-manuali | OK, 61 | OK, 61 | KO K1, 159 | OK, 257 |
| uscite-manuali-firmate | KO B10+UF2, 1820 | OK, 159 | KO K1, 139 | OK, 79 |
| soldi-veri | KO B10, 1816 | OK, 102 (38 ordini sul REALE) | KO K1, 125 | OK, 248 (193 sul REALE) |
| soldi-veri-prova | OK, 32 | OK, 32 (0 reali, 20 aperture fermate) | OK, 80 | OK, 80 (0 reali, 40 fermate) |
| soldi-veri-paper | KO B10, 1816 | OK, 102 (38 SIMULATI) | KO K1, 125 | OK, 248 (193 SIMULATI) |
| 29/09 (riferimento) | 62/130/130/173/61/155 | | 1/309/309/1/114/434 | |

Paper = specchio: `soldi-veri`, `soldi-veri-paper` e `live` hanno le STESSE azioni (pro 102, scalper 248) e lo stesso
numero di ordini, cambia solo il client. Durate: pro 9 scenari 38 s, scalper 102 s, flb 15 s, swing 13 s,
safe_tennis 17 s (tutte sotto 5 min, dentro `timeout 900`).

## C. Residui lasciati per partita (35794049), in EUR

«importo» = l'ordine che chiuderebbe (sotto 0,50, Betfair non lo accetta); «sbilancio» = |se vince - se perde| della
selezione in EUR. Riga `RESIDUI` di ogni scenario nel referto.

| bot / scenario | dichiarati (importo -> sbilancio) | tornati pari | a mercato chiuso |
|---|---|---|---|
| pro base | 0,02 -> 0,02; 0,06 -> 0,06 | 1 | 1 regolato (selezione: se vince -0,14 / se perde -0,02) |
| pro live, gate-aperto, soldi-veri, sv-paper | 0,06 -> 0,06; 0,48 -> 0,51 | 2 | nessuno |
| pro parziali | 0,04; 0,40 -> 0,43; 0,01 x3; 0,02 | 5 | 1 regolato (+0,03 / +0,05) |
| pro uscite-manuali-firmate | 0,06; 0,45 -> 0,49 | 2 | nessuno |
| scalper live, gate-aperto, soldi-veri, sv-paper | 0,05 -> **0,57**; 0,12 -> 0,10 | 0 | 2 regolati (se vince -0,98 / -0,35; se perde -0,41 / -0,17) |
| scalper uscite-manuali-firmate | 0,05 -> 0,50; 0,49 -> 0,54 | 0 | 2 regolati |
| scalper uscite-manuali, base, parziali | nessuno | - | - |

**Da sapere per l'utente:** un importo piccolo puo' valere di piu' in sbilancio a quota alta. Nel giro di mattina
lo scalper aveva un resto da 0,15 a quota 13,5 = **2,00 EUR** di sbilancio (se vince -2,00). Con i numeri della
selezione dichiarati dal bot (correzione `e3e0ae8`) il massimo visto e' 0,57 EUR. La riga CRITICAL riporta sempre «se vince / se perde».

## D. Che cosa e' cambiato (file)

- `tennis_scalper/condotta_ordini.py`:
  - `UsciteEsatte.piazza`: nessun place-and-trim con finale < `SUBMIN_IMPORTO_FINALE_MIN`; il resto e' dichiarato subito.
  - `_passo`: un DONE senza sostituto a mercato diventa ABORTED. E' la difesa nel tennis; la correzione nel nucleo
    e' la patch `AUDIT_2026-10-04/patch/submin_done_solo_con_sostituto_a_mercato.diff` (NON applicata, file tuo).
  - `ResiduiRicordati`: una riga CRITICAL per episodio con la proposta; il residuo resta nelle `stats`
    (`residui_ricordati`) finche' torna pari (<= 0,011) o il mercato si regola; tiene gli importi dell'episodio.
- `tennis_pro_bot.py`:
  - `_residuo_non_piazzabile`: la chiusura richiesta e' < 0,50 e nessuna copertura e' viva -> residuo
    dichiarato, trade FLAT, il bot riprende.
  - `_centesimo_migliora`: un ordine sotto il floor non «migliora».
  - Il micro-residuo < 0,02 resta ricordato (senza riga in piu').
  - A mercato chiuso il residuo e' regolato.
- `tennis_scalper_bot.py`:
  - `_side_min` e `_size_direct_ok` dalla fonte unica: punta >= 1,00 a multipli di 0,50, banca >= 1,00 al
    centesimo (prima 2,00 / 0,50 scritti a mano: la banca diretta da 0,50 Betfair la rifiuta).
  - `_place_exact`: resto < 0,50 = `resto_np`, nessuna sequenza.
  - `_drive_flatten`: il ciclo si chiude col residuo dichiarato (coi numeri della SELEZIONE), PRIMA del ramo
    micro-residuo.
  - La sorveglianza DONE non ri-flattena il residuo ricordato.
  - Il passo 0,50 resta solo per la punta e per gli ingressi; l'uscita in banca esce al centesimo. Senza
    questo, 2,02 diventava 2,00 in silenzio: UF2.
- **Banco**:
  - `certificazione_bot.py`: K5 e RS1, descritti in E.
  - `tools/replay_bot.py`: riga RESIDUI, `soglia_resto` per UF2, hook del residuo.
  - `backtest/uscite_manuali.py`: parametro `soglia_resto` (di serie 0,05, invariato per il calcio).

## E. Controlli del banco adeguati alla decisione 1 (testo prima / dopo)

| controllo | PRIMA | DOPO |
|---|---|---|
| K5 | tolleranza per selezione = quella della credenza del bot (pro FLAT: 0,011) | **max**(credenza, sbilancio del residuo DICHIARATO + 0,011): un euro oltre il dichiarato resta rosso |
| credenza scalper (ciclo chiuso) | `MINIMO_LATO["LAY"]` se `residual_ok`, altrimenti `RESIDUO_ACCETTATO` | la stessa **+ sbilancio del residuo dichiarato** sulla selezione. E' la regola della sorveglianza DONE del bot (`RESIDUO_ACCETTATO + gia`) |
| RS1 (NUOVO) | - | un residuo dichiarato e' davvero NON piazzabile: importo < floor 0,50, con lato e sbilancio. Senza RS1 il bot potrebbe «dichiarare» cio' che deve chiudere |
| UF2 | resto scusato se < 0,05 e dichiarato dal bot | per i bot tennis: < 0,50 (floor, da `minimi_it`) e dichiarato dal bot. L'hook legge anche `residui_ricordati` (stesso lato, importo dell'episodio). Calcio INVARIATO (soglia di serie 0,05) |

## F. Test

- Nuovi: `test_residui_ricordati_2026_10_04.py` (14 test, di cui 5 replay di unita' nel Flumine del runner con
  latenza differita) e +2 in `test_certificazione_pro_scalper_2026_10_04.py` (K5, RS1). Nuovo anche
  `test_banco_uscite_manuali_n3_2026_09_28.py::test_uf2_soglia_del_resto_per_chiamante` (3 casi).
- MODIFICATI, uno per uno. Il motivo comune: chiedevano un place-and-trim sotto 0,50 (regola del 28/09), che
  Betfair rifiuta. Dove serviva il meccanismo, gli importi sono portati in [0,50, 1,00).
  - `test_cantiere_d2_chiusure_esatte::test_annullo_di_una_chiusura_esatta_ferma_la_sequenza`: 1,05 -> 0,75.
  - `test_cantiere_d2_chiusure_esatte::test_anti_cascata_si_azzera_al_primo_successo`: il finto «successo»
    ora porta un ordine vero alla quota voluta (`UsciteEsatte` verifica il sostituto).
  - `test_cantiere_d2_minimo_e_specchio::test_ingresso_flb_sotto_il_minimo_nel_paper_parte_al_minimo`: LAY 0,20
    -> nessun ordine (residuo); il trim provato con LAY 0,60.
  - `test_cantiere_d2_chiusure_via_bot` (`_prepara` con `size_lay`):
    - `test_chiusura_esatta_guidata_dai_book_del_bot`: xfail del reperto 1 TOLTO, LAY 0,60; il parcheggio e'
      `IT_BACK_MIN_STAKE` (1,00, era 2,00).
    - `test_scalper_tennis_chiusura_esatta_guidata_dai_book_del_bot`: 0,60.
    - `test_flb_non_conta_un_verde_su_una_chiusura_abortita_a_meta`: 0,60.
  - `test_cantiere_t_pro_residuo`:
    - `_giri`: tollera il residuo dichiarato.
    - `test_sbilancio_di_centesimi_riducibile_non_si_dichiara_flat`: ora FLAT con `residuo_centesimi` una
      volta, nessun ordine nuovo.
    - `test_chiusura_esatta_in_corso_mai_flat`: LAY 0,60.
  - `test_cantiere_t_scalper_sequenze`:
    - `_giri_con_invariante`: + residuo dichiarato.
    - `test_chiusura_tutta_sotto_il_minimo...`: [1,0, 2,0] -> [0,6]; i casi 1,0 e 2,0 sono ora nei test dei
      residui.
    - `test_chiusura_diretta_piu_resto...`: 3,0, residuo 0,15 dichiarato una volta.
    - `test_rinvio_anti_cascata...`, `test_parcheggio_ritirato...`, `test_sequenza_abortita...`: 1,0 -> 0,6.
- Suite: `tennis_scalper/tests` + `tennis_live/tests` + 6 file del banco: **1180 passed, 5 xfailed** (prima 8: i 3
  xfail del reperto 1 di via_bot ora passano e sono tolti).
- Falsificazione N1-N18 (`AUDIT_2026-10-04/strumenti/falsifica_decisione1_pro_scalper.py`): **18/18 ROSSE**,
  ripristino con `git checkout`, 0 residui. N2 all'inizio restava VERDE: il finto faceva passare il test per
  eccezione. Il test ora usa una strategia flumine vera.

## G. NON verificato (in evidenza)

- **Una sola partita** (35794049, 6 scenari + 3 di soldi veri). Mancano altre registrazioni tennis e il caso di un
  residuo ancora aperto a mercato chiuso con importo grosso.
- **`--data-dir`**: le registrazioni tennis non stanno in `_live_raw` del principale, che e' una cartella del calcio.
  Usata `C:/Users/Admin/Desktop/tennis_rec/20260707` (sola lettura).
- **flb e swing**: la nuova regola di `UsciteEsatte` vale anche per loro, ma su questa partita non chiudono mai.
  Inoltre non hanno il ramo «esci da CLOSING col residuo»: con un residuo sotto 0,50 non mandano piu' ordini
  inutili, ma potrebbero restare nel loro stato di chiusura. Non provato, da affidare.
- **«Lo chiudo io»**: se l'utente chiude il residuo dal Terminale, quell'ordine non e' del bot e il bot non lo vede.
  Il residuo resta segnalato finche' il mercato si regola, o finche' un ciclo del bot lo assorbe (pro).
- Patch per il coordinatore NON applicate e NON provate in suite:
  - `submin_done_solo_con_sostituto_a_mercato.diff` (nucleo condiviso col calcio).
  - `minimi_banco_K1_...diff`: non serve piu' a scalper e pro, che non mandano trim rifiutati; resta corretta per
    la fedelta' del banco.
- Nessun ordine vero; la regola delle punte dell'altro delegato non e' ancora su master: **replay da rifare dopo
  quel merge**.
- K2, B1, B3, B6, B9 restano «mai sollecitati».

---

# PRIMA CONSEGNA (mattina, prima delle decisioni) - storico

## 1. Cause, scenario per scenario (con bisezione)

Bisezione sul codice estratto dei commit (`git archive`, stessi comandi del banco):

| commit | pro base | pro live | scalper live |
|---|---|---|---|
| `3898ce6` (prima di minimi_it) | OK, 62 azioni | OK, 130 | OK, 309 (= 29/09) |
| `9a3bea0` (minimi_it: punta/banca 1,00) | OK, 62 | **KO B8**, 104 | OK, 309 |
| `09072ca` (minimi_banco: l'exchange rifiuta sotto 1,00 diretto / 0,50 nel trim) | OK ma **1868 azioni** | KO B8, 1816 | **KO K1**, 125 |

**C1 - B8 di tennis_pro (`live`): difetto del BANCO, regola dei minimi.** `certificazione_bot.MINIMO_IT` era scritto a
mano `{BACK 2,0, LAY 0,5}`; dal 02/10 il pro parcheggia il place-and-trim a `IT_BACK_MIN_STAKE` = `IT_MIN_BACK` = 1,00
e B8 lo accusava (l'ordine «BACK per 1.0» e' il PARCHEGGIO a quota 1000). Corretto: B8 legge `minimi_it`
(`certificazione_bot.py` MINIMO_IT + `passo_punta_diretta`).

**C2 - il vero difetto di pro (tutti gli scenari con ordini, paper e live): place-and-trim sotto il floor di legge
rimandato in loop.** Dopo il primo trade la chiusura lascia uno sbilancio di 0,02 (LAY, base) / 0,05-0,06 (BACK, live)
EUR. `condotta_ordini.UsciteEsatte.piazza` avvia un place-and-trim con importo finale 0,02-0,06: parcheggio 1,00 a
1000/1,01, taglio, replace -> l'exchange del banco lo rifiuta (finale < 0,50, `SUBMIN_IMPORTO_FINALE_MIN`). `advance_submin`
passa comunque REPRICED -> DONE (non verifica che il sostituto esista), `_fallite` non cresce, l'anti-cascata resta a 30 s:
**~200 sequenze per partita** (base: 197 `uscita_esatta`, 181 `uscita_esatta_attesa` CRITICAL, 470 passi; rifiuti
del banco: LAY 0,02 x220; live BACK 0,06 x207 + 0,05 x19). Il trade resta CLOSING per tutta la partita: **il pro non
fa piu' nessun trade** (1 ingresso contro i molti del 29/09). In base un parcheggio LAY 1,00 @1,01 e' stato ABBINATO
alle 14:40 (ABORT «step1 abbinato alla quota non abbinabile»). Prima del 02/10 il banco accettava il trim a 0,02: per
questo il 29/09 era verde. E' il **reperto 1 di `AUDIT_2026-10-01/RUNNER_MINIMI_CHIUSURE.md` §8** («da decidere con
l'utente»). Nessun controllo lo vedeva: il replay era «OK» (base) con 1868 azioni. Nuovo controllo **B10** (sotto).
Dipende dalla regola dei minimi (floor 0,50 del trim, uguale in tutte le ipotesi) + da una DECISIONE sul residuo.

**C3 - UF2 di pro (`uscite-manuali-firmate`): stessa causa.** Proposta 2,06 -> 2,00 diretti + 0,06 in place-and-trim
(rifiutato): l'uscita firmata esce a 2,00. Sotto l'ipotesi «punta al centesimo» 2,06 sarebbe diretta, ma
`condotta_ordini.diretta_ok` impone il passo 0,50 (`IT_BACK_STEP`).

**C4 - K1 di tennis_scalper (`live`, `gate-aperto`, `uscite-manuali`, `-firmate`): difetto del BANCO (simulazione),
in `minimi_banco.py` (file del coordinatore).** Quando il banco rifiuta il SOSTITUTO di un replace, la simulazione di
flumine lo crea comunque in `trade.orders` (fuori dal blotter) e rimette il vecchio ordine `executable`; flumine LIVE
(`BetfairExecution.execute_replace`, ramo FAILURE `pass`) non crea nessun sostituto e lascia il vecchio
`execution_complete` (Betfair: l'annullo non si ripristina). Lo scalper segue `trade.orders[-1]` -> un fantasma.
Patch pronta, NON applicata: `AUDIT_2026-10-04/patch/minimi_banco_K1_sostituto_respinto_come_live.diff`.
Provata applicandola e togliendola: K1 sparisce in tutti gli scenari, azioni identiche (125/125/159/139).

**C5 - sotto K1, lo stesso C2 nello scalper.** `_place_exact` avvia il place-and-trim per resti 0,05-0,49
(parcheggio 2,00 suo, `_side_min` 2,00/0,50 scritti a mano): rifiutati (LAY 0,45 e 0,46 due volte -> B10 x2). Dopo 5
sequenze `min_bet_skip`; se la perdita del residuo supera 0,25 lo slot resta FLATTENING per tutta la partita: **1 solo
ciclo** contro i 309 eventi del 29/09. Anche qui reperto 1 (decisione dell'utente).

**C6 - `submin.advance_submin` REPRICED -> DONE senza verificare il sostituto** (`trading/submin.py:1138-1143`):
reperto di consapevolezza, in un modulo condiviso col calcio (fuori dal mio perimetro: lo scalper calcio e' in
certificazione da un altro delegato). I bot tennis non ne dipendono per l'esposizione (leggono il blotter), ma il
log dice «a riposo alla target_price» quando non c'e' niente. Proposta: DONE solo se l'ultimo ordine del Trade e' alla
target_price ed e' vivo o abbinato, altrimenti ABORTED «replace fallito». Non applicata.

## 2. Ogni PUNTA che i 4 bot possono mandare (e la banca, dove cambia il rischio)

| bot | ordine | importo | multiplo 0,50? | sotto 2,00? | dopo un rifiuto, in LIVE |
|---|---|---|---|---|---|
| scalper | ingresso BACK (e LAY) | `stake` (>= 2,00) o stake dinamico, `_place(floor_min)` arrotondato al multiplo di `size_step` 0,50 | si' | no | ordine morto: lo slot torna IDLE/CANCELLING, nessuna posizione |
| scalper | chiusura/flatten BACK diretta | `compute_green` -> parte diretta = multiplo 0,50 per difetto se >= 2,00 (`_side_min`) | si' | no | il flatten ritenta ogni `flatten_min_interval_ms` (stessa size): posizione scoperta finche' non passa |
| scalper | parcheggio del trim | 2,00 fisso @1000 / @1,01 | si' | no | sequenza ABORTED, ritenta (max 5 per ciclo) |
| scalper | resto del trim (BACK o LAY) | 0,05-0,49 | no | si' | **rifiutato in OGNI ipotesi (floor 0,50)**; dopo 5 `min_bet_skip`; residuo accettato solo se perdita <= 0,25, altrimenti FLATTENING per sempre |
| scalper | chiusura LAY diretta | >= 0,50 multiplo 0,50 | si' | - | LAY 0,50 rifiutata se la banca minima e' 1,00 (H1/H3): stesso loop del flatten |
| pro / swing | ingresso BACK | `stake` (>= 2,00) legalizzato AL CENTESIMO (`size_legale` -> `min_stake_rules`) | **solo se l'utente sceglie uno stake multiplo** (default 2,00 si') | no | entrata morta -> timeout d'ingresso, nessuna posizione |
| flb | ingresso | sempre LAY `stake` al centesimo | - | - | come sopra |
| pro / flb / swing | copertura BACK diretta | multiplo 0,50 per difetto di `compute_green`, se >= `IT_MIN_BACK` (oggi 1,00) | si' | **si' (1,00 e 1,50)** | la sorveglianza CLOSING ri-copre ogni `close_retry_s` con la stessa size: gamba scoperta, nessun CRITICAL sulla parte diretta |
| pro / flb / swing | parcheggio del trim | `IT_BACK_MIN_STAKE` = 1,00 @1000 / @1,01 | si' | **si'** | sequenza ABORTED, intervallo raddoppiato fino a 300 s, CRITICAL `uscita_esatta_abort` |
| pro / flb / swing | resto del trim | `size - parte diretta` (0,01-0,49 BACK; tutta la LAY < 1,00) | no | si' | **rifiutato in OGNI ipotesi**; oggi falso DONE -> nuova sequenza ogni 30 s (C2), CRITICAL `uscita_esatta_attesa` per finestra |

Verificato sul replay per pro e scalper; per flb/swing dalla lettura del codice (su 35794049 non arrivano a una chiusura:
flb 1 azione, swing 0).

## 3. Regola degli importi: tabella delle ipotesi (NON scelta da me)

Dove il banco tennis decide il minimo: `certificazione_bot.MINIMO_IT` (B8, ora = `minimi_it.IT_MIN_BACK/IT_MIN_LAY`) e
`passo_punta_diretta()` (B8, legge `minimi_it.IT_PASSO_PUNTA_DIRETTA` SE esiste: oggi non esiste = centesimo). Il
rifiuto dell'exchange del banco e' in `minimi_banco.minimo_per` (file del coordinatore). Il trim e' sempre >= 0,50.

| ipotesi | punta diretta | banca | cosa cambiare (solo `minimi_it`, + `minimi_banco` per il passo) | esito atteso del referto pro/scalper |
|---|---|---|---|---|
| H1 = `minimi_it` di oggi | >= 1,00 al centesimo | >= 1,00 | niente | B8 verde (fatto); **B10 rosso** (C2/C5) |
| H2 documentazione | >= 2,00, multipli 0,50 | >= 0,50 (misura 12-13/09) | `IT_MIN_BACK=2.0`, `IT_MIN_LAY=0.5`, `IT_PASSO_PUNTA_DIRETTA=0.5`; `minimi_banco` deve rifiutare la punta non multipla | parcheggi tennis a 2,00 da soli; ingresso pro/swing con stake non multiplo rosso a B8; **B10 rosso** |
| H3 misura del 04/10 | >= 1,00, multipli 0,50 | >= 1,00 | `IT_PASSO_PUNTA_DIRETTA=0.5` (+ `minimi_banco` col passo) | come H1 + B8 rosso se l'utente sceglie uno stake non multiplo; condotta tennis (`diretta_ok`) gia' coerente; LAY 0,50 diretta dello scalper rifiutata |
| H3b | >= 1,00, multipli 0,50 | >= 0,50 | `IT_MIN_LAY=0.5` + passo | come H3, LAY 0,50 dello scalper ok |

In TUTTE le ipotesi il referto di pro e scalper resta rosso per B10 finche' non si decide il reperto 1 (che cosa fa
un bot con un residuo < 0,50: oggi lo rimanda in loop). Il passo: nessuna costante nuova aggiunta da me.

## 4. Correzioni fatte (solo banco; nessuna strategia)

- `certificazione_bot.py`: `MINIMO_IT` da `trading/minimi_it` (prima 2,00/0,50 a mano); testo di B8 coi valori veri;
  `passo_punta_diretta()` parametrico; B10 + `rifiuti_taglia_nuovi` (incrementale, legge
  `minimi_banco.REGISTRO.piazzati` con la regola del banco, solo gli ordini del bot); `client_reale` in `riga_ordine`;
  SV1 + `catena_soldi_veri`.
- `tools/replay_bot.py`: scenari `soldi-veri`, `soldi-veri-prova`, `soldi-veri-paper` (gate di `gate-aperto`, runner
  tetto LIVE, `aggiungi_controlli_ordini` VERI, «Ordini reali» con `modo_ordini.dichiara_per_banco`, bot live instradato
  sul `ClienteLiveBanco` con `instrada_ordini_su_client`, bot paper col client simulato come `client_paper`);
  `modalita_bot_scenario`; il ponte usa la modalita' DEL BOT; letture B10/SV1.
- Test nuovi: `tennis_live/tests/test_certificazione_pro_scalper_2026_10_04.py` (19, di cui 3 replay veri dello scalper,
  ~6 s l'uno). Test MODIFICATO (dichiarato): `test_cantiere_d2_chiusure_esatte_2026_09_28.py::test_b8_sotto_il_minimo...
  [prima3]`, il parcheggio «sotto il minimo» da 1,00 a 0,50 (1,00 e' legale coi minimi del 02/10).
- Suite: `tennis_live` 751+1 passed (1 rosso = il test modificato, ora verde), 8 xfailed; `tennis_scalper/tests` +
  6 file del banco (`test_banco_minimi_it`, `test_minimi_banco`, `test_registro_bot`, uscite N3, chiusura parziale):
  424 passed.

Falsificazione (`AUDIT_2026-10-04/strumenti/falsifica_cert_pro_scalper.py`, ripristino `git checkout`, residui 0):

| mutazione | esito |
|---|---|
| M1 MINIMO_IT riscritto 2,00/0,50 | ROSSO (2) |
| M2 B10 `ripetuto` sempre falso | ROSSO (1); al replay pro live torna **OK** (B10 e' l'unico controllo che vede C2) |
| M3 B10 conta ordini di altri bot | ROSSO (1) |
| M4 SV1 sempre verde | ROSSO (4) |
| M5 `client_reale` invertito | ROSSO (2) |
| M6 bot live non instradato sul client reale | ROSSO (2 replay) |
| M7 terza rete non montata | ROSSO (1 replay) |
| M8 passo della punta ignorato | ROSSO (1) |

## 5. Certificazione (punto d'ingresso unico, uno alla volta)

| bot x scenario | base | live | gate-aperto | parziali | usc-man | usc-man-firm | soldi-veri | sv-prova | sv-paper | 29/09 |
|---|---|---|---|---|---|---|---|---|---|---|
| tennis_pro | KO B10 (1868) | KO B10 (1816) | KO B10 | KO B10 (1610) | OK (61) | KO B10+UF2 | KO B10 (1816) | OK (32) | KO B10 (1816) | 6 OK (62/130/130/173/61/155) |
| tennis_scalper | OK (1) | KO B10+K1 (125) | KO B10+K1 | OK (1) | KO K1 (159) | KO B10+K1 (139) | KO B10+K1 (125) | OK (80) | KO B10+K1 (125) | 6 OK (1/309/309/1/114/434) |
| scalper con patch K1 | OK | KO B10 | KO B10 | OK | OK | KO B10 | KO B10 | OK | KO B10 | - |
| tennis_flb | 6 OK, azioni 1 | | | | | | | | | IDENTICO |
| tennis_swing | 6 OK, azioni 0 | | | | | | | | | IDENTICO |

flb e swing: referto identico riga per riga al `*_TETTO.txt` di oggi tolti tempi/hash, salvo il testo di B8 e due righe
nuove (B10, SV1 «mai sollecitati»). Azioni di pro e scalper identiche al TETTO di oggi in tutti e 6 gli scenari: il banco
nuovo non cambia la condotta, la giudica. safe_tennis `35795993 --scenari rapidi --trasporto entrambi`: 18 OK, parita'
coda 1053/2, canale 1054/2 RAGGIUNTA, righe identiche al riferimento.
Durate: pro 9 scenari 113 s; scalper 9 scenari 44 s (con patch K1 39 s); flb 13 s; swing 11 s; safe_tennis 12 s.

**Soldi veri (punto 5), sul replay del bot vero:** pro soldi-veri 234 ordini tutti sul client REALE, sv-paper 234 tutti
sul SIMULATO con le STESSE 1816 azioni del `live` (paper = specchio); sv-prova 0 ordini reali, 20 aperture fermate da
TENNIS_MODO_ORDINI. Scalper: 31 reali / 31 simulati, azioni 125 = 125; sv-prova 0 reali, 40 fermate. SV1 verde ovunque.

## 6. Reperto R1 (bot gia' acceso in prova passato a soldi veri)

`tennis_bot_service.riconcilia_interruttori` salta le partite gia' armate (`if ev in attive: continue`, e `_escludi` in
auto-mode): la riga per partita resta `mode='paper'` fino alla fine. Il trader vede l'interruttore del bot su «soldi
veri», ma sulle partite gia' armate il bot continua IN PROVA (ordini simulati, P&L di prova) e solo le partite nuove
partono in reale; il tetto partite live non conta quelle in prova, quindi il bot puo' armarne altre in reale accanto.
Proposta minima (non applicata): al cambio di modalita' riscrivere `_riga_armatura` nella modalita' nuova SOLO per le
righe flat; il runner ha gia' il «riarmo» (riga 'requested' con istanza ospitata, `tennis_runner.py:1771-1863`) ma
per pro/flb/swing (senza `force_flat`) disabilita subito anche NON flat: serve quindi un segnale di flat dal battito
del runner prima di riarmare. Fino ad allora: spegnere e riaccendere il bot (gesto sicuro gia' scritto nel TETTO).

## 7. Verdetti

- **tennis_pro: NON CERTIFICATO.** Manca la decisione sul reperto 1 (residuo < 0,50 EUR non chiudibile: oggi loop di
  place-and-trim ogni 30 s, trade CLOSING per sempre, parcheggi che possono abbinarsi). Non e' solo la regola dei
  minimi: in tutte le ipotesi il floor 0,50 resta e B10 resta rosso. Catena soldi veri: verificata.
- **tennis_scalper: NON CERTIFICATO.** K1 = banco (patch pronta in `minimi_banco`, del coordinatore); B10 = reperto 1
  (resti 0,05-0,49, slot FLATTENING per tutta la partita). Catena soldi veri: verificata.
- **tennis_flb, tennis_swing: invariati** rispetto al 29/09 su questa partita, ma usano la stessa `UsciteEsatte` del pro:
  stesso difetto latente appena chiudono con un resto < 0,50 (non sollecitato su 35794049).
- safe_tennis: invariato.

## 8. Decisioni per l'utente (in parole semplici)

1. Un bot tennis che dopo una chiusura resta con pochi centesimi scoperti (meno di 0,50 EUR, che Betfair non accetta):
   (a) dichiara il residuo una volta (CRITICAL + proposta) e riprende a fare trading sulla partita, oppure (b) resta
   fermo su quella partita? Oggi riprova ogni 30 secondi per tutta la partita e non fa piu' trading. Proposta: (a),
   come gia' fa lo scalper col «micro residuo accettato», con il limite di perdita del residuo dichiarato.
2. Il minimo e il passo della punta (tabella §3): decide coordinatore + utente in `minimi_it`; B8 segue da solo.

## 9. Non fatto / non verificato

- Non applicate (file non miei): patch K1 di `minimi_banco`, correzione C6 di `trading/submin.py`, correzione del
  reperto 1 (`UsciteEsatte`, `_place_exact` dello scalper), passo della punta in `minimi_banco`.
- Nessun ordine vero; nessuna misura via API di punta diretta 1,00/1,50.
- flb/swing: comportamento dopo un rifiuto solo da lettura del codice. K2, B1, B3, B6, B9 restano «mai sollecitati».
- Il referto FINALE del pro e' stato girato prima del commit `3f53743` (passo parametrico): con la costante assente
  B8 non cambia (test M8 + test con costante assente).
- R1: analisi da codice, nessun test.
- La UI dei referti stampa in cp1252 i caratteri accentati (solo console; i numeri sono identici).
- Cartella `_lavoro_cert/` (script, estrazioni di bisezione) non committata.
