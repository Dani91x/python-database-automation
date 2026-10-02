# MIKE - chiusura integrata (verifica e correzione, 02/10/2026)

Ramo `mike-chiusura` (base `verifica-runner-master` = `e4c93e0`, master `fb890d5` + runner minimi).
Chi riprende parte da `git log mike-chiusura`. Patch: `AUDIT_2026-10-02/MIKE_CHIUSURA_INTEGRATA.patch`
(`git diff verifica-runner-master`, file nuovi inclusi).

STATO AL 14:05: FATTO tutto (fasi 1-4, falsificazione 21 + 22, profilo). Commit `d6b7db4` (fase 1),
`3169c73` (fase 2), `3dcad88` (fase 3), `a4c4850` (falsificazione), questo (referto, replay, patch).

## Fase 1 - patch del delegato applicata e verificata

`git show fb890d5:AUDIT_2026-10-01/MIKE_CHIUSURA_COPERTURA.patch | git apply --3way`: 15 file puliti,
conflitto solo su `Betfair/stream/trading/minimi_it.py` (AA): tenuta la versione del runner; Mike importa
`IT_MIN_BACK`, `IT_MIN_LAY`, `SUBMIN_IMPORTO_FINALE_MIN` da li' (`engine.py:30-31`), nessuna costante
duplicata (le vecchie `IT_BACK_MIN 2.0 / IT_LAY_MIN 0.50` diventano alias della fonte unica).
Mike NON dipende dalla traduzione del runner: costruisce da se' la punta sulla stessa selezione
(`ripiego_chiusura_sotto_minimo` / `puntata_equivalente`) e la manda come ordine diretto >= 1,00; le
chiusure non passano mai dal place-and-trim (`via_ordine` -> `VIA_NON_SI_MANDA` per i ruoli di chiusura
sotto minimo); le aperture 0,50-0,99 vanno al place-and-trim del runner; sotto, rifiuto dichiarato.
`ATTORI_CON_TRADUZIONE` non esiste ancora nel runner: niente da escludere oggi (Mike non lo usa).

### Revisione riga per riga (prima -> dopo)

| file | prima | dopo | conforme |
|---|---|---|---|
| `engine.py` `via_ordine`/`minimo_listino` | nessuna guardia; `size_chiudibile` al centesimo | guardia unica per ruolo e lato | si' |
| `engine.py` `ripiego_chiusura_sotto_minimo` | punta solo se multipla di 0,50 | punta al centesimo; **02/10 decisione 12**: con la copertura-banca SEMPRE la punta Under (stessa selezione), banca Over solo ripiego | corretto da me |
| `engine.py` `cashout_value` | valore della banca impossibile | valore della punta che parte (decisione 14) | si' |
| `engine.py` `_decide_closing` | ritento a ogni giro, FLAT con residuo | `close_retry_s` dall'ultimo ordine, mai lo strumento rifiutato per taglia, FLAT smentito da `_controllo_di_piatto` | si' |
| `engine.py` `_controllo_di_piatto`/`_dichiara_residuo` | - | LIVE_CLOSING «chiusura parziale: residuo scoperto», 1 CRITICAL per episodio, proposta con l'ordine esatto; **02/10 decisione 13**: `reentry_done=True`, `reentry_allowed=False` (mancava: a residuo chiuso dopo si poteva rientrare) | corretto da me |
| `engine.py` `_ordini_che_chiudono` | banca Over proposta per prima | **02/10**: con la copertura-banca prima la punta Under (stessa selezione) | corretto da me |
| `engine.py` `gate_uscite` (M15/R2) | uscita in perdita senza ordini passava senza firma | categoria «chiusura» da stato+motivo | si' (test + mutazione M15 rossa) |
| `service.py` `_registra_avvisi_esecuzione`, `proposta_non_approvabile` | - | CRITICAL + riga `mike_activity`; residuo non approvabile | si' |
| `service.py` `_segui_ordini_paper_su_runner` | motivo `rifiutata dal runner (rifiutato)` senza codice | **02/10**: legge `error_code` dell'evento (correzione del runner punto 2) e lo passa a `_rifiutata` e al freno | corretto da me |
| `certificazione.py` L1/L2 | - | L1 chiusure e banche < 1,00; **02/10**: anche punta d'apertura < 0,50 (con `exact_sizes`) | stretto da me |
| `porta_ordini.py` | non toccato dalla patch | - | - |

Commenti con minimi superati (2,00/0,50) nelle righe nuove corretti (`engine.py`, 4 punti).

### Verifiche (a)-(h)
* (a) tutte le chiamate di piazzamento (`execute_place` r.5116/5215, `_piazza_resting_paper`,
  `_piazza_resting_live`) nascono da `d.actions` di `E.decide`; ogni ramo di `decide` (flatten C2 e
  dispatch) finisce in `_ultime_guardie` -> `_guardia_minimo_listino`. Nessuna via fuori.
* (b) calcolo Ashdod a mano: posizione banca Under 4,5 6,32 @ 1,23 -> Under: -6,32 x 0,23 = -1,4536;
  Over: +6,32. Chiusura sulla stessa selezione: punta Under 4,5 S x q / p = 7,7736 / 1,03 = 7,547 ->
  **7,55 @ 1,03**; bloccato Under -1,4536 + 7,55 x 0,03 = -1,227, Over 6,32 - 7,55 = -1,23 -> **-1,23**
  (piatto al centesimo). La punta dell'utente 7,47 @ 1,03: -1,23 / -1,15 (sbilancio 0,08). La banca
  0,43 @ 18 (impossibile) avrebbe dato -1,02 / -0,99. Codice: `test_a_la_chiusura_del_45_e_una_puntata_under_7_55_a_1_03`
  (7,55 @ 1,03), `test_b_...` (cash out 0,33 = P&L piatto). Con i libri del 19:07 (Under 1,06) 7,33 @ 1,06.
* (c) dopo INVALID_BET_SIZE / SOTTO_MINIMO mai lo stesso strumento (`chiusura_gia_rifiutata`), ritmo
  `close_retry_s` (`attesa_ritento_chiusura`): test d (21 rifiuti impossibili), M3a/M3b rosse.
* (d) FLAT con esposizione -> LIVE_CLOSING + 1 CRITICAL per episodio + proposta; nessun rientro (mio
  N3 e test `test_decisione_13_*`).
* (e) M15: la correzione regge; il delegato l'ha trovata nel banco; mutazione M15 rossa.
* (f) `SOTTO_MINIMO_NON_PIAZZABILE` sulla strada asincrona: PRIMA no (codice ignorato), ORA si'
  (`service.py`, test `test_codice_del_rifiuto_dal_runner_asincrono_blocca_lo_strumento`, mutazione N9).
* (g) L1/L2 del banco: L1 stretto (punta d'apertura < 0,50), falsificato (N10); L2 x797 sollecitato.
* (h) 16 test vecchi cambiati: tutti per premesse smentite (esenzione delle chiusure dai minimi, passo
  0,50, minimi 2,00/0,50, banca 0,01 «partiva»); nessuna condotta indebolita: dove l'importo e' stato
  alzato (es. Over 21 -> 12,5 in `test_mike_p5_compensazione_mercato`) la regola provata resta la stessa.
  Io ne ho cambiati altri 5, motivo nel test: 3 per la decisione 12 (`test_mike_p5_4c` x2,
  `test_mike_p5_banco`), `test_e_banca_di_chiusura_*` (ora decisione 12), `test_mike_service`
  (letture REST 2 -> 4 per il punto 25), `test_chiusura_parziale_2026_09_23` (CP4 sopra il minimo).

### Precisazione dell'utente (12:40): chiusura sulla STESSA selezione

| via di chiusura | selezione dell'ordine | test (profitto e perdita) |
|---|---|---|
| cash out «profit» / «profit smart» / uscita a modello / regola fissa (tutte `_close_actions`) | copertura-banca: punta Under 4,5; 3,5: banca Under 3,5 | `test_chiusure_di_serie_stessa_selezione_copertura_banca[profitto/perdita]`, `test_cash_out_automatico_in_profitto_chiude_sulla_stessa_selezione` |
| forma di prima (punta Over 4,5) | banca Over 4,5 | `test_chiusure_di_serie_stessa_selezione_forma_di_prima[profitto/perdita]` |
| «Chiudi» / cash out manuale (`_decide_flatten`) | stessa selezione, `manual_close` | `test_chiudi_dell_utente_stessa_selezione[profitto/perdita]`, `test_mike_p5_banco::test_chiusura_manuale_in_gioco_*` |
| riprezzo della chiusura (`_decide_closing`) | resta sulla stessa selezione | `test_riprezzo_della_chiusura_resta_sulla_stessa_selezione[profitto/perdita]` |
| green / chiusura del 3,5 | banca Under 3,5 | `test_green_e_chiusura_del_3_5_stessa_selezione` |
| uscite firmate dall'utente | stessa decisione (`gate_uscite` esegue `_close_actions`) | come la prima riga |
| proposta del residuo | prima la stessa selezione | `test_proposta_del_residuo_propone_prima_la_stessa_selezione` |
| ripiego sull'altra selezione | solo se la stessa non ha quota / e' sotto minimo, mai sotto minimo | `test_ripiego_sull_altra_selezione_solo_senza_prezzo_e_mai_sotto_minimo`, `test_e_copertura_banca_con_puntata_sotto_minimo_resta_la_banca` |
| servizio vero | `selection_id` = quella dell'Under 4,5 | `test_il_servizio_manda_la_selection_id_della_posizione` |

Falsificazione «chiusura sull'altra selezione di serie»: N6 e N7 (vedi sotto).

## Fase 2 - banco ottimista
`Betfair/stream/backtest/minimi_banco.py` (nuovo), montato in `simulazione_flumine` per OGNI replay:
l'exchange simulato (`SimulatedExecution.execute_place/execute_replace`) rifiuta `INVALID_BET_SIZE`
gli ordini diretti < 1,00 e i nuovi ordini di replace / place-and-trim < 0,50; mai un abbinato.
`MercatoFlumine.place_order_live` ha la stessa guardia della REST vera (`PlaceRifiutato`
`SOTTO_MINIMO_NON_PIAZZABILE`), `place_submin_live` col floor 0,50 come il vero. Controllo nuovo
`BANCO-SOTTO-MINIMO` (`certifica.segna_sotto_minimo`): legge gli ordini davvero eseguiti, indipendente
dalla regola; nota nel referto solo quando ha un caso (referti senza casi identici riga per riga).
Test: `Betfair/stream/tests/test_banco_minimi_it_2026_10_02.py` (5, ognuno con falsificazione interna).
Sintetica `_synth_mike_ashdod` (`synth_mike.caso_ashdod`, stake di serie: copertura 12,63 @ 1,23; al 28'
Under 4,5 1,03/1,04, Over 26/36 -> banca di chiusura **0,43 @ 36**; con lo stake 5 di quel giorno sarebbe
0,43 @ 18, ma uno scenario nuovo allungherebbe `tutti`). Rigenerare con
`python -m Betfair.mike.tools.synth_mike --caso ashdod --data-dir <_live_raw> --dest-dir <dir>`
(il .raw.jsonl e' in .gitignore: non committato).
* corretto, canale (34,7 s): **OK**, 0 violazioni, punta Under 4,5 **15,08 @ 1,03** (12,63 x 1,23 / 1,03),
  NETTO +0,67, L1 x6, L2 x797 (`replay/mike_synth_ashdod_canale_INTEGRATA.txt`);
* motore e servizio di PRIMA (stesso banco), canale (46,2 s): **KO**, L1 x1 (chiusura sotto minimo
  mandata), RG1 x2 (P&L Mike 0,65 contro banco 0,67) (`replay/mike_synth_ashdod_canale_SENZA_PATCH.txt`);
* reperto trovato: la prima corsa chiudeva a 1,22: il generatore sintetico NON toglie dal libro i
  livelli vecchi (stream a delta senza `[prezzo, 0]`). Corretto solo per `ashdod` (`azzera_livelli`);
  le 5 sintetiche di prima hanno lo stesso difetto (libro ottimista): REPERTO aperto.
* coda (51,3 s): OK ma Mike resta 377 giri «al fischio: attendo l'esito della banca pre-partita» e non
  copre: la sintetica sulla coda (live) non risolve la banca pre-partita LAPSE. NON indagato (Mike gira
  sul canale); REPERTO.
Suite dopo la fase 2: Mike + stream/tests + scalper **4896 verdi, 25 saltati** (411 s).

## Fase 3 - punto 25 e R1
* Punto 25 (`service.py`, costanti `_RIGA_ASSENTE_REST_S = 30`, `_REST_APERTO/_CHIUSO`,
  funzione `_stato_rest_riga_assente`): quando i tetti di sempre direbbero «partita finita» con la riga
  assente, Mike rilegge `market.read_book` (la via del regolamento) delle sue linee: OPEN/SUSPENDED su
  almeno una -> tiene (diario `riga_assente_mercato_aperto`, «riga assente, mercato aperto: tengo», una
  volta per episodio); tutte CLOSED -> annulla e regola come prima; illeggibile -> tetti di sempre
  (600 s di grazia, KO+100' visto in gioco, KO+3 h). Scelta mia, da confermare: il «tetto» per il caso
  illeggibile e' quello di oggi (600 s), non 60 s, per non essere mai piu' aggressivo di prima.
* R1 (`service.py`, `arresto_con_ordini`, `_ARRESTO_TETTO_S = 10`, `_installa_segnali_di_arresto`):
  nel `finally` di `main` (mai in `--once`/`--dry`): annullo degli ordini vivi non abbinati con
  `_mark_trade_cancelled` (runner in paper, Betfair in live: stesso codice), oltre 10 s nessun altro
  annullo + CRITICAL `arresto_ordini_non_annullati`; posizioni abbinate dichiarate
  (`posizione_lasciata_per_arresto`, CRITICAL). Motivo: «stop dall'app», «segnale (...)», «eccezione ...».
  SIGTERM/SIGBREAK -> KeyboardInterrupt. Il tetto di `main.js` (kill forzato a 25 s) NON e' toccato.
* kind nuovi dichiarati in backend (`test_mike_audit_2026_09_11`) e UI (`frontend/src/lib/mike.ts`).
* Test: `Betfair/mike/tests/test_mike_riga_assente_e_arresto_2026_10_02.py` (11). Suite Mike **1539 verdi**.

## Falsificazione
* 21 mutazioni del delegato rilanciate (M9b adattata alla decisione 12): **21/21 rosse**
  (`_tmp_verif`, esito copiato qui sotto). M1 13, M2 45, M3a 2, M3b 4, M4 8, M5 11, M6 2, M7 1, M8 4,
  M9 30, M16 4, M17 3, M18 5, M19 1, M9b 4, M12 15, M14 1, M15 1, M13 1, M10 1, M11 1.
  Esito: `MIKE_CHIUSURA_COPERTURA_falsifica21_rilancio.out`.
* Mie: `MIKE_CHIUSURA_INTEGRATA_falsifica.py` (ripristino da copia + impronte), **22/22 rosse**
  (`.out` + `_R1d.out`: R1d al primo giro aveva il testo sbagliato, rilanciata da sola e rossa).
  Nessuna sopravvissuta.

| mutazione | rossi |
|---|---|
| N1 guardia che lascia passare una banca 0,99 | 23 |
| N2 FLAT con residuo (ogni residuo creduto non chiudibile) | 10 |
| N3 rientro dopo un residuo dichiarato (decisione 13) | 2 |
| N4 equivalente al prezzo sbagliato (lati del libro scambiati) | 20 |
| N5 secondo CRITICAL sulla stessa proposta | 2 |
| N6 chiusura sull'ALTRA selezione di serie (banca Over sopra il minimo) | 8 |
| N7 proposta del residuo: prima l'altra selezione | 1 |
| N8 cash out col valore della banca quando parte la punta | 2 |
| N9 codice del rifiuto ignorato sulla strada asincrona | 2 |
| N10 L1 cieco sulla punta d'apertura < 0,50 | 1 |
| N11 exchange del banco senza regola | 2 |
| N12 replace del banco senza floor 0,50 | 1 |
| N13 REST del banco senza la guardia del vero | 1 |
| N14 BANCO-SOTTO-MINIMO senza violazione | 1 |
| N15 sintetica di Ashdod coi livelli vecchi | 1 |
| P1 riga assente: annullo senza rilettura REST | 5 |
| P2 riga assente: mercato aperto trattato come chiuso | 4 |
| P3 rilettura REST senza ritmo | 1 |
| R1a arresto senza annullo | 3 |
| R1b arresto senza CRITICAL sulle posizioni | 1 |
| R1c arresto senza tetto | 1 |
| R1d `main` senza arresto degli ordini | 1 |

## Fase 4 - replay (uno alla volta, `--data-dir` = `_live_raw` del checkout principale)

| replay | durata (comando / TEMPO TOTALE) | esito | confronto |
|---|---|---|---|
| `35760084 --scenari base,riavvio,feed-stantio --trasporto canale` | 200 s / 163,4 s | 3 OK, 0 violazioni | base e riavvio: **5879 decisioni, 6 azioni, NETTO -14,17, 602 giri senza riga**; feed-stantio 1024 decisioni, 0 azioni, NETTO 0,00: IDENTICO al riferimento di oggi. Unica differenza: letture REST 5 -> 7 (la rilettura del punto 25 quando la riga sparisce a partita finita: Betfair dice CLOSED, si regola come prima) |
| 5 sintetiche `--scenari base --trasporto canale` | 145 s / 97,4 s | 5 OK | NETTO identico al referto del delegato (+3,43, +3,43, +0,51, +0,34, +0,34); decisioni +1 ciascuna (1617 -> 1618 ...): la lettura REST in piu' del punto 25 costa 120 ms di mercato e sposta un giro |
| `35760084 --scenari copertura-rifiutata,copertura-rifiutata-legacy --trasporto entrambi` | 311 s / 275,8 s | 4 OK, parita' coda/canale RAGGIUNTA x2 | NETTO identico (-10,00, -3,00, -10,00, -3,00), ordini 6 / righe 5 identici. Decisioni diverse dal referto del delegato (coda 5353 -> 5367, 5340 -> 5354; canale 5861 -> 5879, 5858 -> 5879): il riferimento del delegato e' su master `ebfab2a` (base allora 620 giri senza riga), la mia base e' master `fb890d5` con scanner mai cieco (base 602): oggi il base fa 5879 come qui. NON verificato riga per riga su master di oggi |
| `_synth_mike_ashdod` (nuova) canale | 35 s | OK | vedi fase 2 (con la patch tolta: KO) |

Durate: sopra l'obiettivo dei tempi del delegato (sintetiche 16 s -> 97 s). Il profilo (sotto) dice che
il tempo in piu' e' l'IMPORT dei moduli in un worktree nuovo, non il banco.

### Profilo (`cProfile`, `certifica mike _synth_mike_reingresso --scenari base --trasporto canale`, 81,8 s)
1. `_io.open_code` 31,9 s su 1620 chiamate (20 ms l'una): lettura dei file .py all'import, worktree
   nuovo senza `__pycache__` / antivirus sui file nuovi (ambiente, non codice);
2. `json.encoder.iterencode` 1,77 s (6684 chiamate: serializzazione delle righe del DB in memoria);
3. `builtins.round` 1,58 s (388.524 chiamate);
4. `engine._market_pnl_by_total` 1,43 s cumulati (178.920 chiamate);
5. `dataclasses._asdict_inner` 1,07 s e `scanner._senza_campi_rumorosi` 1,01 s.
Nessuno corretto (fuori perimetro, punto 5 dell'utente). Il giro del servizio (`_run_event`) vale
16,8 s cumulati su 2219 giri.

## NON VERIFICATO
* frontend (patch del delegato + i 3 kind miei): niente `tsc`/`vitest` (nel worktree non c'e'
  `node_modules` e le junction sono vietate);
* prova dal vivo dei minimi .it via API (punta 1,00 / banca 1,00): solo fonti e la punta 7,47 dell'utente;
* scenari `cashout-dopo-copertura`, `firma-*`, `uscite-*`, `tutti`: cambiano con la decisione 12 e il
  banco nuovo, non lanciati (punto 5 dell'utente, oltre i 10 minuti);
* coda della sintetica di Ashdod (vedi reperto).

## Reperti (per l'utente / il coordinatore)
1. **Sintetiche di prima con libro ottimista**: il generatore (`synth_mike.Costruttore`) non toglie i
   livelli vecchi (`[prezzo, 0]`); i P&L delle 5 sintetiche di prima possono essere migliori del vero.
   Corretto solo per `ashdod` (opzione `azzera_livelli`); estenderlo cambia i loro referti.
2. **Sintetica di Ashdod sulla coda**: Mike in live sul banco non risolve la banca pre-partita LAPSE al
   fischio (377 giri «attendo l'esito»), non copre. Da indagare (Mike gira sul canale).
3. **Decisione 12 applicata solo alla copertura-banca**: nella forma di prima (punta Over 4,5) la
   chiusura resta la banca Over (che e' la stessa selezione). Coerente con la precisazione delle 12:40.
4. **Tetto del punto 25 con REST illeggibile = 600 s** (quello di sempre), non 60 s: da confermare.
5. **R1**: il kill forzato di `main.js` (25 s) non e' allineato al tetto (10 s piu' un annullo da 3 s):
   oggi basta; `TerminateProcess` non e' intercettabile. Safe e Omega: R1 ancora aperto.
6. Il banco rifiuta ora gli ordini sotto minimo per TUTTI i bot (Safe, Omega, scalper, tennis):
   le loro suite sono verdi, ma i loro replay non sono stati rilanciati qui: i P&L con residui sotto
   minimo possono cambiare (in peggio, cioe' veri).
7. Scenari `cashout-dopo-copertura`, `firma-*`, `uscite-*` cambieranno (decisione 12: punta Under al
   posto della banca Over): da rilanciare con `tutti` (punto 5).
