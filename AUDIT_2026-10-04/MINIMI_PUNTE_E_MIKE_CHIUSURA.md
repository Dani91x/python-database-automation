# Regola delle PUNTE .it nel motore, nel banco e in Mike (04/10/2026)

Ramo `worktree-agent-a41b5cbcc0dd127df`, base master `65ff19e`. Commit: `787be8d` (regola +
test), `991fbd4` (proposta del residuo: un avviso per episodio), `2067b54` (test libro), piu' questo
referto. Delegato Opus. Nessun ordine vero, nessuna chiamata a Betfair, nessuna scrittura su
DB, `.env` non toccato, app non avviata.

## 0. Verdetto in breve

- La regola dell'utente e' nel codice come UNA definizione (`minimi_it.importo_piazzabile`):
  punta diretta da 1,00 solo a multipli di 0,50 **per difetto**, residuo dichiarato; sotto
  1,00 place-and-trim (finale >= 0,50, invariato); sotto 0,50 niente; banca invariata.
- Mike: OGNI sua punta nasce in `engine._place` e da 1,00 in su esce a multiplo di 0,50 per
  difetto (Umea: 7,27 -> 7,00). Il residuo (sempre < 0,50) lo dichiara `_controllo_di_piatto`,
  UN avviso per episodio, nessun ritento.
- Il banco ora rifiuta `INVALID_BET_SIZE` una punta diretta non multipla (come Betfair) e il
  sostituto respinto di un replace e' simulato come in live (patch K1 applicata).
- Replay Mike 26/26 senza violazioni, ma **con differenze attese** (§5) e uno scenario NE.
- Replay Safe base: **KO di parita'** coda/canale — e' il difetto vero di Safe sulla strada
  REST (punta 2,39 rifiutata come farebbe Betfair). Non corretto (fuori perimetro). Omega OK.

## 1. Cosa ho cambiato (file:riga, ramo)

| File | Dove | Cosa |
|---|---|---|
| `Betfair/stream/trading/minimi_it.py` | docstring :1-36; `IT_PASSO_PUNTA_DIRETTA` :54 (`IT_PASSO_PUNTA_RIPIEGO` alias); `ImportoPiazzabile` + `importo_piazzabile` :93-140; `punta_diretta_valida` :143 | La regola UNICA. Docstring corretta: la "prova" del 7,47 era un ordine dell'utente dal sito (Cash Out), scritto perche' era sbagliata. Nome `IT_PASSO_PUNTA_DIRETTA` = quello che il banco tennis dell'altro delegato legge se esiste. |
| `Betfair/stream/live_order_build.py` | `min_stake_rules` :222-242; `MinStakeVerdict.residuo` :122; `VerdettoMinimi.residuo` :607; verdetto diretto :637-639; equivalente non multiplo scartato :667-671; `build_order` :848-858 e `BuiltOrder.residuo` :138 | .it/back: `legalized_size` = multiplo per difetto, `residuo` dichiarato; `build_order` piazza l'importo a difetto, scrive la dichiarazione nella `note`, logga WARNING. Un EQUIVALENTE punta non multiplo non si usa piu' (non sarebbe equivalente). Banca e .com invariati. |
| `Betfair/stream/motore_ordini.py` | `_applica_minimi` :1318-1331; `_ripristina_minimi` :1392; `extra_fisso` :1459-1466 | Canale: la riga parte a difetto e OGNI evento al bot porta `punta_050` {chiesto, piazzato, residuo, motivo}. Idempotente sull'aggancio. Il ripiego `ripiego_050` dopo un rifiuto vero resta (ora inerte per le punte: partono gia' multiple). |
| `Betfair/stream/live_order_worker.py` | `_do_place` :1497-1502 | Coda: l'esito porta `punta_050` (oltre alla `detail`). |
| `Betfair/stream/trading/submin.py` | import :54; `pianifica_submin` ramo "place normale" :700-717 | Il place normale di una punta .it parte a difetto, residuo nel `motivo`. |
| `Betfair/stream/backtest/minimi_banco.py` | docstring; `punta_fuori_passo` :101, `fuori_listino` :119; uso in `execute_place` e nel controllo; patch K1 :188-256 | Il banco rifiuta `INVALID_BET_SIZE` la punta DIRETTA >= 1,00 non multipla (sostituti e finali del place-and-trim: solo il floor 0,50). Il controllo `abbinati_sotto_minimo` vede anche questa violazione. |
| `Betfair/mike/engine.py` | `punta_a_multiplo` :1861; `_place` :1876; commenti :80-86, :687-692, ripiego :1007-1020; `_proposta_residuo_finale` :3054 | Ogni punta di Mike da 1,00 in su a multiplo per difetto con la nota. La proposta del residuo non decade nei giri d'attesa (vedi §5: 23 avvisi -> 1). |
| `Betfair/mike/certificazione.py` | E2 :516-525; L3 nuovo dopo L2 (:851) | E2 accetta ESATTAMENTE il multiplo per difetto della copertura in punta; **L3** rosso su qualunque punta >= 1,00 non multipla (centesimi interi, indipendente dal motore). |
| `Betfair/mike/COSTITUZIONE_MIKE.md` | §15.5 | Nota: superato per le punte da 1,00 in su. |

### Patch K1 (sostituto di un replace respinto): APPLICATA
Verificata sul sorgente di flumine 2.x: `BetfairExecution.execute_replace` crea il sostituto
SOLO su `SUCCESS` (su `FAILURE` non fa nulla, il vecchio resta `execution_complete` dal
cancel); `SimulatedExecution.execute_replace` invece aggiunge sempre il sostituto a
`trade.orders` e su FAILURE rimette il vecchio `executable()`. La patch toglie il sostituto
respinto e chiude il vecchio solo quando il rifiuto e' quello del banco: e' il comportamento
live. Test adattato e falsificato (M11).

## 2. Punto 4: la strada REST di Mike dopo una chiusura RIFIUTATA
Verificato con `service.execute_place` VERO, `PlaceResult` VERO, codici INVALID_BET_SIZE,
INSUFFICIENT_FUNDS, ERROR_IN_ORDER, BET_TAKEN_OR_LAPSED (test d): in nessun giro FLAT con la
posizione aperta, tentativi solo ogni `close_retry_s` e al piu' `close_max_attempts`,
`INVALID_BET_SIZE` -> mai lo stesso strumento, un solo `chiusura_parziale` CRITICAL e una sola
riga del servizio. **Nessun buco trovato nel motore** sulla strada REST. Perche' il 04/10 a
Umea l'utente non abbia visto la proposta NON l'ho potuto verificare (vedi §8).
Buco trovato e chiuso invece sulla chiusura manuale/cash out: la proposta del residuo decadeva
nei giri senza prezzi e rinasceva -> un CRITICAL nuovo ogni volta (23 nel banco).

## 3. Test nuovi e falsificazione
- `Betfair/stream/tests/test_minimi_punte_050_2026_10_04.py` (34): tabella della regola,
  input non validi, verdetto, `build_order`, submin, motore VERO paper e live, coda del worker
  (`_do_place` vero), banco VERO sulla registrazione 35760084 (7,27 rifiutata, 7,00 abbinata,
  falsificazione a regola spenta nel corpo).
- `Betfair/mike/tests/test_mike_punte_multiplo_050_2026_10_04.py` (17): `punta_a_multiplo`,
  `_place`, numeri di Umea (piano esatto 7,27 -> ordine 7,00), REST live abbinata (un avviso,
  zero ritenti, decisione 13), REST rifiutata x4 codici, libro intermittente sul cash out, L3.

Mutazioni (script `AUDIT_2026-10-04/strumenti/mutazioni_punte_050.py`; ogni file ripristinato
con `git checkout` dal commit, verificato `git diff --quiet`):

| # | Mutazione | Rossi |
|---|---|---|
| M1 | regola unica senza passo | 31 |
| M2 | `min_stake_rules` torna al centesimo | 12 |
| M3 | verdetto senza residuo | 5 |
| M4 | equivalente punta non multiplo ammesso | 3 |
| M5 | `build_order` senza dichiarazione | 3 |
| M6 | motore senza `punta_050` | 4 |
| M7 | `_ripristina_minimi` non toglie `punta_050` | **0 (sopravvissuta)**: innocua, `_applica_minimi` la riscrive o il piano riparte; nessun test la vede |
| M8 | worker senza `punta_050` | 1 |
| M9 | submin place normale al centesimo | 1 |
| M10 | banco senza passo delle punte | 2 |
| M11 | patch K1 spenta | 1 |
| M12 | Mike `_place` senza multiplo | 7 |
| M13 | Mike per ECCESSO | 11 |
| M14 | L3 muto | 1 |
| M15 | controllo di piatto spento | 5 |
| M16 | avviso a ogni giro | 5 |
| M17 | chiusura rifiutata data per chiusa | 5 |
| M18 | proposta del residuo che decade nei giri d'attesa | 1 (alla prima stesura del test 0: test rifatto sul cash out, poi rosso) |

## 4. Suite
- Prima corsa intera (prima di adattare i test vecchi della traduzione/tennis): 39 rossi,
  9790 verdi.
- Corsa FINALE (`python -m pytest Betfair/ -q -p no:cacheprovider`, 354 s):
  **9864 verdi, 16 rossi, 31 skipped, 9 xfailed.** Suite Mike sola: 1596 verdi.

### I 16 rossi rimasti (NON adattati, lasciati rossi apposta)
- 12 in `safe_strategy/tests/test_riconciliazione_tradotti_safe_2026_10_02.py` (`test_d3_*`) e
  3 in `omega/tests/test_riconciliazione_tradotti_omega_2026_10_02.py`
  (`test_d1_caso_completo_nessuna_seconda_chiusura[True|False-banca_tradotta_in_punta]`,
  `test_d1_il_finto_rispetta_gli_attori_con_traduzione[True]`): fanno passare dalle strade di
  Safe/Omega (coda, REST, canale) la banca di Ashdod 0,43 @18 e pretendono che il verdetto
  VERO scelga l'equivalente punta 7,31. Con la regola nuova 7,31 non e' piazzabile e il
  verdetto da' `SOTTO_MINIMO_NON_PIAZZABILE` (0,43 < 0,50). Sono test della macchina della
  traduzione (oggi spenta: `ATTORI_CON_TRADUZIONE` vuoto) nei file di Safe e Omega, con decine
  di numeri derivati (liability 7,31, p&l 0,43/0,44, parziali 3,66/3,65): rinumerarli
  (es. 0,25 @19 -> 4,50) e' lavoro sul dominio Safe/Omega, NON fatto. Decisione del
  coordinatore.
- 1 in `stream/tests/test_banco_ambiente_dichiarato_2026_10_02.py::test_coda_stesso_referto_con_ambiente_principale_e_ambiente_vuoto`:
  attende per Safe `['hedged','open']` sulla coda; ora la seconda riga e' `error` perche' Safe
  sulla strada REST manda una punta 2,39 e il banco la rifiuta come Betfair. E' lo stesso
  difetto vero di Safe del replay (§5), non un test da adattare.

### Test vecchi toccati (uno per uno, motivo)
Tutti pretendevano punte al centesimo >= 1,00 o un equivalente-punta non multiplo:
1. `stream/tests/test_runner_minimi_chiusure_2026_10_01.py`: `test_punta_al_centesimo_7_47_accettata` -> riscritto `test_punta_7_47_parte_a_7_00_col_residuo_dichiarato`; `test_numeri_di_oggi_equivalente_e_scarti` (verdetto ora impossibile per 0,43@18, aggiunto 0,25@19 -> 4,50); `test_banca_030_...` (5,10 non multiplo; aggiunto 0,30@21 -> 6,00); `test_motore_banca_043_mandata_come_punta_731...` -> numeri 0,25@19 / 4,50 + test nuovo "7,31 non piu' mandata"; `test_motore_ripiego_050_solo_dopo_invalid_bet_size...` -> riscritto (7,47 parte 7,00 prima dell'invio, nessun ripiego dopo); `test_motore_aggancio_...` -> numeri 0,25@19 + test aggancio `punta_050`; docstring del file.
2. `stream/tests/test_runner_minimi_correzioni_2026_10_02.py`: `_place_tradotto`, p1, p3 (cancel totale/parziale 1,80 -> 2,70; sotto 0,50 con riduzione 0,23; replace 4,00 @1,07), p5 tolleranza, p11 attore nell'insieme: numeri da 0,43@18/7,31 a 0,25@19/4,50 (stessa macchina, punta equivalente multipla).
3. `stream/tests/test_banco_minimi_it_2026_10_02.py::test_replace_con_importo_finale_sotto_0_50_rifiutato`: con K1 il sostituto respinto non sta piu' in `trade.orders`; letto dal registro, asserzioni in piu' (nessun fantasma, vecchio completo).
4. `stream/tests/tradotti_comuni.py::tradotto_di` (aiuto dei test di riconciliazione Safe/Omega/stream): costruisce la dichiarazione con `equivalente_lato_opposto` quando il verdetto vero non sceglie piu' l'equivalente (7,31). Collaudano la RICONCILIAZIONE di un ordine gia' tradotto, non il verdetto. `test_r_contratto_tradotto_del_finto_uguale_al_motore_vero` -> 0,25@19 (motore vero).
5. `stream/tests/test_live_order_build.py`: `test_min_stake_it_back` (1,99/2,3/2,7/4,99/7,47 -> 1,5/2,0/2,5/4,5/7,0); `test_build_back_tiene_il_centesimo` -> `test_build_back_a_multiplo_di_050_per_difetto_col_residuo`.
6. `stream/tests/test_cashout_pro_2026_09_10.py::test_equalize_gamba_su_runner_piatto...`: apertura 6,58 -> 6,50.
7. `stream/tennis_scalper/tests/test_condotta_ordini_2026_09_17.py::test_ingresso_sopra_il_minimo_non_si_gonfia`: BACK 2,30/3,70 -> 2,00/3,50 (tennis: effetto del motore condiviso, il bot NON e' stato toccato).
8. `stream/tennis_live/tests/test_cantiere_d2_minimo_e_specchio_2026_09_28.py::test_chiusura_sotto_il_minimo_non_si_gonfia_mai`: punta 1,20 -> 1,00.
9. Mike: `test_mike_chiusura_copertura_2026_10_01` (6 test: 7,55 -> 7,50; 5,98 -> 5,50; "piatto entro 0,01" sostituito da "residuo dichiarato, LIVE_CLOSING"), `test_mike_chiusura_integrata_2026_10_02` (2), `test_mike_engine` (2: 3,16 -> 3,00; 3,61 -> 3,50), `test_mike_engine_cert_2026_09_12` (2: 2,17 -> 2,00, 2,69 -> 2,50; **invarianti Costituzione 4.3 abbassati della parte non piazzata**, vedi §6), `test_mike_flusso_fischio_2026_09_13` (2: 1,35 -> 1,00, 3,16 -> 3,00), `test_mike_p5_copertura_banca_2026_09_29` (3: 3,16 -> 3,00; 11,88 -> 11,50, due rinominati), `test_mike_banco_ondata2::test_e2_punta_del_motore_vero_tace` (non toccato: corretto il controllo E2).

## 5. Replay (punto d'ingresso unico, uno alla volta)
### Mike: `certifica mike 35760084 --scenari tutti --data-dir <MAIN>/_live_raw`
Referto `AUDIT_2026-10-04/replay/mike_tutti_PUNTE_050_finale.txt`, 449 s (sotto il tetto
600; obiettivo 300 superato come il 02/10). ESITO 26 senza violazioni, 1 NE. L3 sollecitato
41 volte, zitto. Confronto riga per riga (OK/KO/NETTO) con
`mike_tutti_stesso_comando_del_02_10_coord.txt`: 21 scenari identici; differenze:

| Scenario | 02/10 (cert.) | Oggi | Causa |
|---|---|---|---|
| copertura-legacy | NETTO -14,21 | -14,00 | copertura in punta Over 4,21 -> 4,00 (forma spenta in produzione) |
| cashout-dopo-copertura | OK, FLAT, 53027 tick / 5354 dec., -0,68 | **NE**, mai FLAT, 51947 / 5237, -0,81 | la punta Under 4,5 di chiusura parte a multiplo; residuo 0,20-0,53 dichiarato (1 `chiusura_parziale`) e, per decisione 13, LIVE_CLOSING fino al regolamento: il controllo R2 ("dopo il cash out non apre") non ha piu' un giro da guardare -> NON ESERCITATO |
| firma-dopo-gol-decisivo | FLAT, 52170 / 5267, -2,05 | niente FLAT, 52027 / 5232, -2,75 | stessa causa: residuo della punta di chiusura |
| firma-...-senza-chiusura | FLAT, -2,05 | niente FLAT, -2,75 | idem |
| uscite-in-perdita-firmate | -2,01 | -2,27 | idem |
| uscite-automatiche | -2,11 | -2,43 | idem |

Prima del fix di `_proposta_residuo_finale` lo stesso replay dava 23 `chiusura_parziale` nel
cash out (referto `mike_tutti_PUNTE_050.txt`, tenuto per il confronto); ora 1.

### Omega: `certifica omega 35760084 --scenari rapidi --trasporto entrambi` (53 s)
`omega_rapidi_entrambi_PUNTE_050.txt`: ESITO OK, parita' RAGGIUNTA, KO 0. Unica differenza
col referto di A-D: 18 scenari di trasporto invece di 17 (R11d del cantiere tennis, gia' su
master).

### Safe base: `certifica safe_base 35760084 --scenari rapidi --trasporto entrambi` (62 s)
`safe_base_rapidi_entrambi_PUNTE_050.txt`: **ESITO KO, PARITA' NON RAGGIUNTA**. Riga 2:
coda = `back 2,39 @9,2 status error`, canale = `back 2,00 status open`. La coda e' la strada
REST diretta (`omega_market.place_order_live`, non toccata): manda 2,39 e il banco la rifiuta
come Betfair. Il canale arrotonda a 2,00 (il bot riceve `punta_050` ma non lo legge). E' il
difetto di Safe del censimento (§7, rischio 1), NON corretto. Anche qui 18 scenari invece di 17.

## 6. Divergenze dalla strategia (scritte, non decise da me)
1. **Mike, decisione 13 + residuo per costruzione.** Ogni chiusura in punta non multipla lascia
   ora un residuo < 0,50 -> LIVE_CLOSING fino al regolamento, **niente rientro**. Prima la
   chiusura era al centesimo e il rientro restava possibile. La decisione 1(a) del 04/10 sera
   ("residuo sotto 0,50: dichiaralo una volta e riprendi a operare") va in senso opposto per
   gli altri bot: per Mike resta la 13. Serve la scelta dell'utente.
2. **Copertura in punta Over 4,5 (forma `back_over45`, spenta)**: a difetto protegge meno
   (es. 2,17 -> 2,00 toglie 1,13 EUR al netto con 5+ gol; invariante 4.3 non piu' esatto).
3. **Cash out mostrato vs eseguito**: `cashout_value` e la proposta calcolano sul piano esatto
   (7,27); l'ordine parte 7,00. La cifra "bloccabile" e' quindi ottimista del residuo.
4. **Proposta all'utente**: indica l'ordine ESATTO (es. punta 7,27); se l'utente lo mette via
   "Chiudi" di Mike parte comunque a 7,00.

## 7. Censimento degli altri bot (SOLA LETTURA, nessuna modifica)
| Bot | file:riga | Importo | Strada | Effetto |
|---|---|---|---|---|
| Safe apertura | `safe_strategy/execution.py:1087-1089` (`bot_service.py:6090`; combo/dutch :8583/8588) | stake ridotto alla liquidita' | canale / coda / REST :1320 | canale e coda: a difetto, `punta_050` non letto da Safe (vede 7,00 abbinato come parziale); combo: profitto bloccato rotto. REST: **rifiutata INVALID_BET_SIZE** |
| Safe chiusure | `execution.py:2323` (`bot_service.py:3624/4587/5719`) | hedge calcolato | canale / coda / REST (+ `place_submin_live` >= minimo -> `place_order_live`) | canale/coda: chiusura incompleta <= 0,49 poi `_rifiuto_sotto_050` a ogni ciclo; REST: **chiusura rifiutata, posizione nuda** |
| Omega aperture | `omega_service.py:2772/2813/2847` | banca | coda / REST | nessun effetto |
| Omega chiusure | `omega_service.py:6032, 6915`; `omega_proposte.py:816` | punta di copertura calcolata | canale / coda / REST | come Safe chiusure |
| Omega manuale | `omega_service.py:5644` / `:5683` | importo utente | coda / REST | coda a difetto; REST rifiutata se non multipla |
| Scalper calcio | `stream/scalper/scalper_bot.py:2341-2342, 2462, _place_exact 2580` | coperture/flatten | `market.place_order` diretto | non passa da `build_order`: arrotonda al multiplo **piu' vicino** (7,27 -> 7,50, per eccesso), minimo BACK ancora 2,00 |
| Sniper | `stream/scalper/sniper_bot.py:1001-1002, 1027, 1056` | idem | idem | idem scalper |
| tennis_scalper | `tennis_scalper_bot.py:2400-2401, 2507` | coperture | diretto | piu' vicino, minimo 2,00 |
| tennis_pro/flb/swing ingressi | `tennis_pro_bot.py:456`, `tennis_flb_bot.py:210`, `tennis_swing_bot.py:261` -> `condotta_ordini.size_legale` | stake | diretto | a difetto (usano `legalized_size`); residuo ignorato |
| tennis coperture | `tennis_scalper/condotta_ordini.py:111-163, 352-392` | copertura esatta | diretto + place-and-trim proprio | parte diretta gia' multipla; resto < 0,50 in un place-and-trim che non chiama `verifica_importo_finale` |
| tennis_live worker | `tennis_live_order_worker.py:681-685` (place), `:953-957` (green-up) | comandi / hedge | worker tennis | a difetto **senza dichiarazione**; hedge sotto 1,00 -> ValueError |
| worker calcio green-up / cash-out | `live_order_worker.py:2208`, `:2748` | hedge / pareggio | coda | a difetto, solo nella `note` (la `detail` del green-up riporta il P&L atteso sull'importo pieno) |
| Terminale manuale | `order_exec.py:265-271` | importo utente | REST | **rifiutata** se non multipla (usa solo `.valid`) |

Rischio principale: tutte le strade REST dirette (`omega_market.place_order_live`,
`order_exec`) mandano ancora la punta non multipla -> rifiuto certo; per le CHIUSURE di Safe e
Omega significa posizione scoperta. Proposta (non applicata): in `place_order_live` mandare
`_v.legalized_size` e restituire il residuo nel `PlaceResult`, oppure arrotondare nei bot.

## 8. NON VERIFICATO (in evidenza)
- **Umea dal vivo**: non ho letto il DB, quindi non so se il 04/10 la riga `chiusura_parziale`
  (proposta all'utente) sia stata scritta e non mostrata dalla UI, o non sia nata affatto. Il
  motore di oggi, sulla stessa strada REST con i finti veri, la produce (test d).
- La regola stessa non e' provata con ordini del bot sul conto: riposa sulle parole
  dell'utente, sulla documentazione e sulle righe del 04/10 (nessun ordine di prova, per ordine).
- **Scenario del banco "copertura non eseguibile + Under 3,5 in profitto di 2 tick"**: NON
  fattibile nelle regole del banco sulla 35760084: gli scenari cambiano solo parametri/feed,
  e in questa partita dopo il gol al 7' l'Under 3,5 non torna 2 tick sotto l'ingresso mentre
  la copertura e' non eseguibile (referto del 02/10 identico con la condizione gia' attiva). Mi
  sono fermato li'; resta coperta solo dai test unitari del 04/10.
- Resa a schermo di `punta_050` / proposta: non vista (UI non toccata, Safe/Omega non leggono
  il campo).
- Safe tennis, 4 bot tennis, Scalper: nessun replay lanciato da me (fuori perimetro).
- Mutazione M7 sopravvissuta (vedi §3).
