# Safe e Omega: punte a multipli di 0,50 su ogni strada, residuo dichiarato una volta (04/10/2026)

Ramo `worktree-agent-a750be2518f6a7c27`, base master `4dd624a`. Delegato Opus. Nessun ordine
vero, nessuna chiamata a Betfair, nessuna scrittura su DB, `.env` non toccato, app non
avviata, nessun processo nuovo. Interrotto una volta da una caduta di rete: ripreso dallo
stato del worktree (niente perso), commit intermedi da li' in poi.

## 0. Verdetto in breve

- **Safe base**: il difetto e' chiuso. Sulla strada REST la chiusura in punta 2,39 parte 2,00
  (prima: mandata 2,39, rifiutata `INVALID_BET_SIZE`, posizione nuda). Replay rapidi:
  **ESITO OK, PARITA' coda/canale RAGGIUNTA** (era KO). Scenari completi: 22/22 senza
  violazioni, 254 s.
- **Omega**: rapidi OK, parita' raggiunta; scenari completi 20/20 senza violazioni, 162 s,
  referto identico a quello di master (sulla 35760084 Omega non chiude mai in punta: il
  percorso nuovo e' provato dai test, NON dal replay).
- **Safe tennis**: rapidi OK, parita' raggiunta, identico a master (stessi 2 J4C-DICHIARATA
  sul canale di master; 18 scenari di trasporto contro i 14 del referto MASTER_coord: R11*
  del cantiere tennis, gia' su master).
- Il residuo (sempre < 0,50) si dichiara UNA volta (CRITICAL con la proposta), resta scritto
  sull'apertura e nessuna macchina di Safe o Omega lo ritenta: lo chiude l'utente.
- Suite finale: **1 rosso, 9902 verdi** (era 16 rossi): il rosso e' un test del banco FUORI
  perimetro che pretende 'hedged' sopra un residuo vero di 0,39; patch proposta, non applicata (§4).
- Divergenza di strategia scritta e NON decisa: le combo (§6).

## 1. Cosa e' cambiato (file:riga sul ramo)

| File | Dove | Cosa |
|---|---|---|
| `Betfair/omega/omega_market.py` | `PlaceResult.punta_050` :671; `place_order_live` :741-760, :827 | REST diretta: una punta >= 1,00 non multipla parte a DIFETTO (`min_stake_rules` -> `minimi_it.importo_piazzabile`, fonte unica) e il risultato porta `punta_050` = {chiesto, piazzato, residuo, motivo}, le stesse chiavi dell'evento del canale. `size_requested` = importo MANDATO (come le righe di coda e canale). Banca invariata. `place_submin_live` sopra il minimo passa di qui: stessa regola. |
| `Betfair/safe_strategy/execution.py` | `PlaceOutcome.punta_050` :289; `_PREFISSI_PUNTA_050` :1025; `_dichiara_punta_050` :1028; `place` :1061 (rientro col raccoglitore :1114-1125, `_PLACE_VERO` :1513); arrotondamento :1198-1203; lettura del REST :1414-1419 | Safe e Omega passano TUTTI da `place`. La punta si arrotonda UNA volta, PRIMA di scegliere la strada: canale, coda e REST ricevono lo stesso importo; la riga (`meta.punta_050`), l'esito (`PlaceOutcome.punta_050`, con ogni esito) e l'attivita' (`diagnosi`, reason `punta_050`) lo dicono. Solo per i ref `safe-`, `safe_tennis-`, `omega-`: Mike resta com'era (le sue punte nascono gia' multiple in `engine._place`; due test di Mike pretendono il suo canale invariato). Se e' il REST ad arrotondare (altro chiamante), la sua `punta_050` si legge e torna nell'esito. |
| idem | `RESIDUO_KEY`, `ERR_RESIDUO`, `residuo_ricordato`, `_testo_proposta`, `_avviso_residuo`, `_ricorda_residuo`, `_residuo_senza_via` :2289-2380 | Il residuo non piazzabile: CRITICAL UNO per episodio (`_critico_una_volta`, la chiave gia' usata dai rifiuti sotto il minimo: la posizione da chiudere) col testo della proposta ("chiudi tu il residuo: punta 0,39 EUR a 9,20 su ..."); marcatore `meta.residuo_non_piazzabile` sull'apertura, scritto una volta. Kind d'attivita' riusato: `place_parziale` (gia' tradotto dalla UI), `reason=residuo_non_piazzabile`. Nessun kind nuovo (il contratto col frontend non cambia). |
| idem | `close_trade` pre-verifica :2430-2447 | Il RESTO di una chiusura gia' abbinata (`filled_ids` non vuoto) senza nessuna via (sotto 0,50; equivalente non ammesso, `ATTORI_CON_TRADUZIONE` vuoto): nessuna riga di riserva, nessun ordine, `{"error": "residuo_non_piazzabile"}`. La PRIMA chiusura di una posizione non passa di qui (resta com'era: rifiuto certo). |
| idem | `close_trade` dopo l'ordine :2551-2552, :2578-2579, :2599-2617, :2641 | La gamba porta `punta_050` (aperta o in errore); CRITICAL una volta con la proposta (gamba in volo: "se la chiusura in volo si abbina"); a fill CERTO e intero (REST) il residuo e' ricordato subito; l'esito di `close_trade` porta `punta_050`. |
| `Betfair/safe_strategy/bot_service.py` | `_exit_candidates` :4236-4242 | Apertura col residuo ricordato: fuori dalla macchina delle uscite (nessun ritento). |
| idem | combo solidale :4603-4606 | `residuo_non_piazzabile` non e' un secondo CRITICAL. |
| idem | `_send_exit` :5787-5801 | Ramo dedicato: nessun tentativo consumato, `sent`, stato `failed` con `last_error=residuo_non_piazzabile` e nessun `next_retry_at`, nessun `exit_retry`. |
| idem | `_execute` :6140-6143 | Apertura confermata: `meta.punta_050` sulla riga. |
| idem | `_esegui_combo_riservata` :8727-8755 | Una punta della combo arrotondata: CRITICAL una volta (`place_parziale`, reason `combo_punta_050`) con le gambe. Gli importi NON si ricalcolano (§6). |
| `Betfair/omega/omega_service.py` | manuale REST :5724-5735 | La conferma scrive `punta_050` se il REST ha arrotondato l'importo dell'utente (come gia' fa la coda). |
| idem | `_greenup_candidates` :6515-6521 | Residuo ricordato: ne' green-up ne' proposte (stessi candidati) lo ritentano. |
| idem | `_greenup_send` :6964-6975, :7009-7023 | `residuo_non_piazzabile` -> stato `residual_dropped` (meccanismo esistente) senza consumare tentativi; chiusura REST abbinata col residuo gia' ricordato -> `residual_dropped` subito, non "residuo ancora da coprire" (che nessuno coprirebbe). |
| `Betfair/omega/omega_proposte.py` | `_esegui_da_solo` :841-849 | Automatico V3: nessun tentativo, nessun secondo CRITICAL, nessuna proposta di ripiego. |
| `Betfair/order_exec.py` | import :36-44; `place_order` :272-282 | Terminale manuale: punta >= 1,00 non multipla RIFIUTATA prima dell'invio, importo dell'utente intatto: `7,27: la punta va a multipli di 0,50, usa 7,00 o 7,50.` |

### Patch FUORI perimetro (in `AUDIT_2026-10-04/patch/`, NON applicate, `git apply --check` pulito)
1. `banco_place_order_live_punte_050.patch` (`stream/backtest/banco_comune.py`): lo specchio
   del REST nel banco fa come il vero (a difetto, `punta_050`). Non serve ai replay di Safe e
   Omega (arrotondano prima del REST); serve alla fedelta' del banco per un chiamante che
   mandasse al REST una punta non multipla (oggi il banco la rifiuterebbe, il vero no).
2. `test_banco_ambiente_dichiarato_punte_050.patch` (`stream/tests/...2026_10_02.py`): vedi §4.

## 2. I tre punti della regola, strada per strada

| Strada | Prima (master `4dd624a`) | Dopo |
|---|---|---|
| Canale | il motore arrotonda 2,39 -> 2,00 e manda `punta_050` nell'evento; Safe non lo legge (2,00 abbinato visto come parziale) | Safe manda gia' 2,00; la dichiarazione e' nell'esito di `place` e sulla riga (write-ahead del canale) |
| Coda | il worker arrotonda, `punta_050` nell'esito; Safe non lo legge | Safe accoda gia' 2,00 con `meta.punta_050` |
| REST | 2,39 mandata, `INVALID_BET_SIZE`, chiusura nuda | 2,00 mandata (anche `place_order_live` arrotonda per chi non passa da `place`), `punta_050` nell'esito |
| Residuo | `_rifiuto_sotto_050` a ogni giro: una riga 'error' + `place_rifiutato` + `cashout_error` per tentativo, per sempre (CRITICAL una volta) | UN CRITICAL con la proposta, marcatore sull'apertura, nessuna riga, nessun ritento (Safe e Omega) |
| Terminale | 7,27 mandata e rifiutata da Betfair | rifiutata prima, con i due importi validi |

## 3. Test nuovi e falsificazione

- `Betfair/safe_strategy/tests/test_punte_multiple_050_2026_10_04.py` (21): REST vera con
  Betfair finto a livello di rete (`tradotti_comuni.monta_rete`, `PlaceExecutionReport`
  grezzo), tabella della regola (7,27 Umea, 1,49, 2,50, 1,00, banca 2,39), place-and-trim
  sopra il minimo; Safe REST 2,39 -> 2,00 col residuo ricordato e un CRITICAL, secondo
  tentativo senza ordine ne' riga; 10 giri sul residuo = 1 CRITICAL, 0 righe, 0
  `place_rifiutato`; prima chiusura sotto 0,50 invariata; coda (payload della coda) e canale
  (comando VERO di `porta_ordini.costruisci_comando`, `Ack` vero) a 2,00; candidati delle
  uscite di Safe e Omega; terminale (messaggio esatto; 7,50 / 1,00 / banca 7,27 passano);
  combo; giro VERO di Safe (`run_once`, runner paper finto): uscita 9,44 -> 9,00, poi 7 giri
  sul residuo 0,44: 1 gamba, 1 CRITICAL, stato `failed`/`residuo_non_piazzabile`, nessun
  `exit_retry`.
- `Betfair/omega/tests/test_punte_multiple_050_omega_2026_10_04.py` (3, col conftest di
  Omega): green-up paper 34,38 -> 34,00 e residuo 0,38 -> `residual_dropped`, 1 CRITICAL,
  nessuna seconda chiusura; green-up LIVE sulla REST vera -> `residual_dropped` subito;
  automatico V3 senza tentativi ne' CRITICAL.

Mutazioni (`AUDIT_2026-10-04/strumenti/mutazioni_safe_omega_punte_050.py`, ogni file
ripristinato con `git checkout` e verificato `git diff --quiet`; esito completo in
`AUDIT_2026-10-04/mutazioni_safe_omega_punte_050_esito.txt`): **18 su 18 rosse**.

| # | Mutazione | Rossi |
|---|---|---|
| M1 | REST senza arrotondamento | 4 |
| M2 | REST senza dichiarazione | 4 |
| M3 | `place` senza arrotondamento | 5 |
| M4 | esito senza `punta_050` | 5 |
| M5 | `close_trade` senza pre-verifica | 4 |
| M6 | residuo "senza via" sempre falso | 4 |
| M7 | avviso a ogni giro | 4 |
| M8 | residuo mai ricordato | 5 |
| M9 | chiusura abbinata: residuo non ricordato subito | 2 |
| M10 | Safe: candidati non saltano il residuo | 1 |
| M11 | Omega: candidati non saltano il residuo | 1 |
| M12 | Safe `_send_exit` senza ramo | 1 (alla prima stesura 0: test rafforzato, poi rosso) |
| M13 | Omega green-up senza ramo | 1 |
| M14 | terminale: punta non multipla accettata | 1 |
| M15 | terminale: importo cambiato in silenzio | 1 |
| M16 | Omega stato 'pending' invece di 'residual_dropped' | 1 (alla prima stesura 0: aggiunto il test LIVE REST, poi rosso) |
| M17 | Omega automatico senza ramo | 1 |
| M18 | combo arrotondata in silenzio | 1 |

NON coperto da un test che lo falsifica: la riga `punta_050` nel meta della conferma del
manuale REST di Omega (`omega_service.py:5724-5735`, una chiave in piu' nel meta).
Mutazioni rilanciate sul codice FINALE: 18 su 18 rosse, ogni ripristino pulito.

## 4. Suite

`python -m pytest Betfair/ -q -p no:cacheprovider`:
- base del cantiere dei minimi (master): 9864 verdi, 16 rossi.
- prima corsa intera del ramo: **3 rossi, 9900 verdi**, 31 skipped, 9 xfailed (447 s); i due di
  Mike corretti subito (limite ai ref Safe/Omega, `place` resta la funzione vera).
- corsa FINALE (codice del ramo, 357 s): **1 rosso, 9902 verdi, 31 skipped, 9 xfailed**. I 15 rossi della traduzione sono verdi (rinumerati), i 2 di Mike verdi senza toccare Mike.

Il rosso residuo atteso, FUORI perimetro e NON adattato:
`stream/tests/test_banco_ambiente_dichiarato_2026_10_02.py::test_coda_stesso_referto_con_ambiente_principale_e_ambiente_vuoto`.
Era il "sedicesimo rosso" (coda `['hedged','error']`: la punta 2,39 rifiutata). Il motivo del
rosso e' SPARITO (nessun rifiuto, 2 ordini sulla REST, parita' con l'ambiente vuoto, `a == b`
verde); resta l'ultima riga che pretende `['hedged', 'open']`: con la regola dell'utente la
chiusura e' 2,00 e 0,39 @9,2 restano scoperti, quindi l'apertura e' `open` (vero) e mai
`hedged` (sarebbe dichiarare coperto cio' che non lo e'). Non c'e' modo di farlo diventare
verde "per la correzione" senza mentire sul residuo. Patch proposta:
`AUDIT_2026-10-04/patch/test_banco_ambiente_dichiarato_punte_050.patch` (`['open','open']`
col motivo). Decisione del coordinatore.

### Test vecchi toccati (uno per uno, motivo)
Tutti nei file di Safe e Omega; il motivo e' sempre lo stesso: pretendevano una chiusura in
punta NON multipla di 0,50 abbinata per intero (copertura 'hedged'), oggi impossibile. Si sono
RINUMERATI per tenere l'intento (copertura integrale), non si sono cambiate le asserzioni.
1. `safe_strategy/tests/test_bot_service.py::test_exit_base_profit_chiude_dopo_l_assestamento_e_mai_due_volte`: banca 10@8,5 -> 9@8,5 (chiusura 9,44 -> 8,50 esatta).
2. `...::test_uscita_modello_gol_avverso_dopo_l_assestamento`: idem, 9@8,5.
3. `...::test_caso_trade_12_uscita_a_tempo_in_perdita_con_margine_ampio_tiene`: back del passo "il prezzo migliora" 65 -> 80 (punta 1,85 -> 1,50 esatta); greenup ed etichette invariate.
4. `...::test_uscita_a_tempo_in_profitto_esce_sempre`: back 65 -> 80; bloccato 0,15 -> 0,50, testo netto "+0,4" (0,475).
5. `safe_strategy/tests/test_p_nessun_fill_di_casa_2026_09_28.py::test_uscita_paper_senza_runner_resta_da_ritentare_e_poi_esce`: 9@8,5; esposizione 75,00 -> 67,50.
6-11. `omega/test_omega_greenup_2026_09_10.py`: `test_trigger_gol_esce_dopo_assestamento_e_marca_le_due_righe`, `test_p_o1_stato_done_al_fill_e_mai_un_secondo_invio`, `test_p_green_up_paper_senza_runner_non_consuma_e_avvisa`, `test_bot_fermo_gestisce_comunque_le_uscite`: stake 5 -> 4 (punta 34,38 -> 27,50 esatta; bloccato ed EV scalano entrambi: stessa decisione); `test_trigger_gol_tiene_se_p_lose_bassa_poi_esce_oltre_il_cap`: back 5,8 -> 5,5 (50,00 esatta; bloccato -42,4 -> -45,0, numeri dell'EV invariati); `test_trigger_quota_decisione_a_modello_con_riserva_di_mercato`: back 19 -> 22, lay 20 -> 23 (12,50 esatta; p_lose 1/19 -> 1/22).
12-16. `omega/test_omega_audit_2026_09_11.py`: `test_h04_...`, `test_l01_...`, `test_m04_...`, `test_rev_h2_...`, `test_rev_h3_chiusura_in_perdita_e_exit_kind_loss`: stake 5 -> 3,80 (a 7,6 la punta e' 27,50 esatta; prima 36,18 -> 36,00 + 0,18).
17. I 15 rossi della traduzione (12 `safe_strategy/tests/test_riconciliazione_tradotti_safe_2026_10_02.py`, 3 `omega/tests/test_riconciliazione_tradotti_omega_2026_10_02.py`), rinumerati con lo strumento `AUDIT_2026-10-04/strumenti/rinumera_tradotti_punte_050.py` (sostituzioni letterali, diff riletto riga per riga): banca Over 0,43 @18 -> punta Under 7,31 @1,06 diventa 0,25 @19 -> 4,50 @1,06, gli STESSI numeri dei test del runner gia' su master. Derivati: apertura punta 1,00 @7,74 -> @4,75 (0,25 x 19 = 4,75), libro Over 17,5/18 -> 18,5/19, liability 0,25 x 18, P&L banca vinta +0,43 -> +0,25, vincita della punta tradotta 7,31 x 0,06 = 0,44 -> 4,50 x 0,06 = 0,27. UNA asserzione cambiata a mano: il parziale REST (`test_d3_rest_parziale_...`) 3,66/3,65 di 7,31 -> 2,30/2,20 di 4,50 = 0,13/0,12 su 0,25. **Reperto** (fuori perimetro, traduzione oggi spenta): con un parziale a meta' esatta, 2,25/2,25, `riporta_lettura_tradotta` da' 0,12 + 0,12 = 0,24 su 0,25 chiesti (0,125 arrotondato due volte per difetto): abbinato + residuo non tornano al chiesto.

## 5. Replay (punto d'ingresso unico, uno alla volta, ognuno col tetto di 900 s)

Lanciati con `AUDIT_2026-10-04/strumenti/replay_con_tetto.py` (= `timeout 900`), referti in
`AUDIT_2026-10-04/replay/`. "Prima" = gli stessi comandi col codice di master `4dd624a`
(i 6 file sorgente del ramo riportati a master per la sola durata del replay e poi ripristinati
da `git checkout HEAD`).

| Comando | Prima | Dopo | Tempo |
|---|---|---|---|
| `certifica safe_base 35760084 --scenari rapidi --trasporto entrambi --data-dir <MAIN>/_live_raw` | KO, parita' NON raggiunta (`safe_base_rapidi_entrambi_PUNTE_050.txt`: coda `back 2,39 error`, canale `back 2,00 open`) | **OK, parita' RAGGIUNTA**, 18 trasporto KO 0, coda/canale 2 ordini e 2 righe, 0 violazioni (`..._PUNTE_MULTIPLE.txt`) | 67 s |
| `certifica omega 35760084 --scenari rapidi --trasporto entrambi --data-dir ...` | OK, parita' | OK, parita' (identico) | 43 s |
| `certifica safe_tennis 35795993 --scenari rapidi --trasporto entrambi --data-dir Desktop/tennis_rec/20260707` | OK (MASTER_coord) | OK, parita', canale coi 2 J4C-DICHIARATA di master | 11 s |
| `certifica safe_base 35760084 --scenari tutti --data-dir ...` | 22/22 senza violazioni (`safe_base_tutti_PRIMA_4dd624a.txt`) | 22/22 senza violazioni | 254 s |
| `certifica omega 35760084 --scenari tutti --data-dir ...` | 20/20 (`omega_tutti_PRIMA_4dd624a.txt`) | 20/20, identico | 162 s |

Il comando degli "scenari completi" usato e' `--scenari tutti`: in CRONOSTORIA non ho trovato
un referto certificato di Safe base o di Omega con un comando diverso (NON VERIFICATO che sia
quello che intendeva il coordinatore).

### Confronto riga per riga, Safe base `--scenari tutti` (prima -> dopo)
`AUDIT_2026-10-04/replay/confronto_safe_base_tutti.txt` (diff completo) e
`riassunto_safe_base_tutti.txt` (per scenario). 15 scenari identici. Differenze:

| Scenario | Prima | Dopo | Causa |
|---|---|---|---|
| ordini-manuali, bot-fermo, riavvio | righe {open 1, error 1}; 1 `INVALID_BET_SIZE`; NETTO +1,90 | righe {open 2}; 0 rifiuti; 1 `place_parziale` (residuo); NETTO 0,00 | chiusura in punta 2,39 -> 2,00 abbinata; resta 0,39 @9,2 dichiarato |
| due-lay | {open 2, error 1}; +3,80 | {open 3}; +1,90 | idem (2,39 -> 2,00) |
| chiusura-abbinata-in-parte | 1 `INVALID_BET_SIZE` | 0 rifiuti | la chiusura parte 2,00 e il FOK del banco la uccide (scenario), non piu' rifiutata per taglia |
| combos-automatiche | {error 2}: entrambe le punte (6,23 e 3,77) rifiutate per taglia; P&L 0 | {open 1, error 1}: 6,23 -> 6,00 abbinata a 5,7; 3,77 -> 3,50 non abbinata a 9,8 (FOK); combo incompleta, gamba manuale lasciata (B25); NETTO -6,00 | la combo prima non partiva MAI (rifiuto di taglia); ora parte arrotondata |
| combos-gamba-automatica | {error 2}; 0 | {hedged 1, error 1, open 1}: combo incompleta svolta (banca 5,34 @6,4); NETTO -0,66 | idem |

Controlli: **K2** (riga rifiutata da Betfair mai viva) era sollecitato SOLO dai rifiuti di
taglia di Safe (x2745-2783 in 7 scenari) ed e' ora **x0 in tutti i 22 scenari** ("non lo so");
lo scenario `rifiuti-betfair` non lo sollecitava nemmeno prima. E' una perdita di copertura
del banco: K2 ora non vede nessun rifiuto vero su Safe base. **CP1** (chiusura abbinata in
parte) era x0 e ora e' x2746. T2/J1/J2/J3/J6 contano un ordine in piu' dove l'ordine c'e'.

### Residui lasciati, per partita (in euro)
| Replay | Ordine | Residuo NON piazzato |
|---|---|---|
| safe_base 35760084, ordini-manuali / bot-fermo / riavvio / due-lay / rapidi (coda e canale) | chiusura punta 2,39 @9,2 -> 2,00 | **0,39** per scenario (esposizione se vince la selezione: 0,39 x 8,2 = 3,20; se perde -0,39) |
| safe_base 35760084, combos-automatiche e combos-gamba-automatica | apertura combo punta 6,23 @5,7 -> 6,00 | **0,23** (non e' esposizione scoperta: punta piu' piccola) |
| idem | apertura combo punta 3,77 @9,8 -> 3,50 | 0,27 (ordine poi non abbinato) |
| omega 35760084 (tutti) e safe_tennis 35795993 (rapidi) | nessuna punta non multipla | 0 |

## 6. Divergenze di strategia (scritte, NON decise)

1. **Combo / dutch (punto 3 del brief): mi fermo qui.** Gli stake delle gambe vengono dalla
   proposta (`_proponi_combo`, stake pubblicati scalati sul totale); con la punta a difetto le
   proporzioni non sono piu' quelle che bloccano il profitto. Esempio coi numeri del banco
   (combo K: punta 6,23 @5,7 e punta 3,77 @9,8, totale 10,00): se esce la prima 6,23 x 5,7 =
   35,51 di ritorno (+25,51), se esce la seconda 3,77 x 9,8 = 36,95 (+26,95). Arrotondate:
   6,00 x 5,7 = 34,20 (+24,70) e 3,50 x 9,8 = 34,30 (+24,80) su 9,50 puntati: il bloccato
   scende di 0,81 e 2,15 EUR e non e' piu' quello approvato. Tenerlo esatto vuol dire
   ricalcolare gli stake (es. scegliere il totale che rende multiple TUTTE le punte, o
   arrotondare per eccesso una gamba): e' cambiare COME la strategia calcola gli importi.
   NON fatto. Oggi: la combo parte arrotondata e lo si dice con UN CRITICAL (`place_parziale`,
   reason `combo_punta_050`, gambe e residui). Serve la scelta dell'utente.
2. **Safe apertura singola**: con lo stake ridotto alla liquidita' (o qualunque stake non
   multiplo) la punta parte a difetto: posizione piu' piccola di <= 0,49, nessuna esposizione
   scoperta. Dichiarato sulla riga e in `diagnosi`, non CRITICAL. Nessuna divergenza di
   calcolo, ma lo stake reale non e' piu' quello della strategia: lo scrivo.
3. **Il residuo non si ritenta MAI, anche se piu' tardi diventa piazzabile** (decisione
   "LO CHIUDO IO"): il resto di una punta, in stake d'apertura, e' r x p / p'. Se la quota
   scende molto (es. 0,39 a 9,2 = 3,59 di squilibrio; a quota 7 la chiusura sarebbe 0,51)
   diventerebbe piazzabile, ma il bot non lo tocca piu': resta all'utente. Lo scrivo perche'
   e' una scelta, non un caso.
4. **Prima chiusura sotto 0,50** di una posizione intera (nessuna gamba abbinata): lasciata
   COM'ERA (rifiuto certo con una riga 'error' a ogni ritento, CRITICAL una volta). Il brief
   parlava del resto di una chiusura; estendere la regola anche li' e' una decisione.
5. **Omega manuale** (importo dell'utente) sulla strada REST: ora parte a difetto con
   `punta_050` sulla riga, come gia' faceva la coda. Il terminale di `order_exec` invece
   rifiuta (punto 4 del brief). Due comportamenti per due "importi dell'utente": decisione
   dell'utente se il manuale di Omega debba rifiutare come il terminale.
6. **Stato d'uscita di Safe** col residuo: `failed` con `last_error=residuo_non_piazzabile` e
   nessun ritento. La UI (non toccata) lo mostra col codice grezzo e la parola "fallita":
   l'etichetta va decisa (fuori perimetro: `frontend/src/lib/safeActivity.ts`).

## 7. Catalogo §7 e copertura §6 (criteri)

- §7.1/§7.27 chiavi: `punta_050` con le chiavi dell'evento del motore e del worker (test con
  l'insieme esatto); finti a livello di rete coi dizionari grezzi di Betfair.
- §7.2 `res.ok`: il REST rifiutato resta rifiuto (test d'origine invariati); K2 vedi §5.
- §7.28/29/30/35: ogni test nuovo visto rosso (18 mutazioni); due test che passavano a vuoto
  (M12, M16) rafforzati finche' non sono diventati rossi.
- §6 parita' paper/live e coda/canale: replay rapidi OK con parita' su Safe base, Omega,
  Safe tennis.

## 8. NON VERIFICATO (in evidenza)

- **Resa a schermo**: `meta.residuo_non_piazzabile`, `meta.punta_050`, lo stato `failed` di
  Safe e `residual_dropped` di Omega col nuovo motivo, il CRITICAL `place_parziale` con
  `proposta`: UI non avviata, frontend non toccato. Non so come appaiano all'utente.
- **Omega sul replay**: sulla 35760084 Omega non fa mai una chiusura in punta; il percorso nuovo
  di Omega e' provato SOLO dai test (paper col runner finto, LIVE con la REST vera e Betfair
  finto). Nessuna registrazione esercita green-up/proposte con residuo.
- **Safe tennis**: il replay rapido non produce nessuna punta non multipla: il percorso nuovo
  sul tennis non e' esercitato dal banco.
- **K2 non sollecitato** su Safe base dopo la correzione (§5): serve uno scenario del banco che
  provochi un rifiuto vero su Safe (`rifiuti-betfair` oggi non lo fa).
- Il comando degli "scenari completi" (`--scenari tutti`) non l'ho trovato in un referto
  certificato di Safe base / Omega.
- La regola stessa e' quella dell'utente e del cantiere dei minimi: nessun ordine vero di prova.
- `meta.punta_050` sulle righe in volo di coda/canale: scritto dal write-ahead; che sopravviva
  alla risoluzione dell'esito (poll della coda, eventi del canale) l'ho visto sul canale nel
  test, non l'ho seguito su tutte le funzioni di risoluzione.
- La riga del manuale REST di Omega con `punta_050` non ha un test che la falsifichi.
