# REVISIONE FINALE AVVERSARIA (sola lettura, 09/10/2026)

Perimetro: 07, DECISIONI, 05, REFERTO_FIX_DUTCHING, CERTIFICAZIONE_REFERTI; campione di punti di 00-04 e 06.
Metodo: ogni citazione file:riga e CRONOSTORIA.md:riga riaperta alla riga attuale; numeri del REFERTO confrontati con
`lavori/fase2/suite/*.txt` e con `git diff --numstat`; sonde in `lavori/fase2/sonde/rev_cite.py` e `rev_blank.py`
(stampano righe, nessuna scrittura). Nessun DB, nessun git di scrittura, nessun processo terminato.

Esito: nessuna frase FALSA sul fix del dutching (numeri tutti riscontrati). Restano 4 frasi che l'utente leggera' come
fatti e che non sono certificate (nn. 1-4), piu' imprecisioni minori.

## Problemi

### 1. [MEDIO] 07, riga 7-8 e tabella riga 34: «I conti che muovono i soldi dei bot sono giusti (... commissione, puntate ...)»
- Problema: troppo largo. 05 conferma errori di conto nei bot vivi: B35 (cash-out di Mike: la base della commissione
  esclude le gambe archiviate, 0,62 EUR su un utile archiviato di 12,5; consumatori vivi `mike/engine.py:1463, 1786...`),
  B9 (commissione arrotondata in modi diversi, 1 cent), B10 (due regole di pareggio sul tick, 196 punti su 99.900),
  M17 (min_edge/Kelly per euro di stake anche sui lay, `live_engine_pro.py:596-607`). Sono BASSI/strategia, ma non e'
  vero che «tutto torna».
- Prova: 05 righe 48, 82-85, 104; CERT_3 riga B35, CERT_2 righe B9/B10/M17.
- Correzione: «I conti che muovono i soldi dei bot (green-up, profitti e perdite back e lay, scala delle quote) sono giusti
  nelle prove rifatte. Restano incoerenze BASSE e non critiche: commissione del cash-out di Mike senza le gambe
  archiviate (fino a ~0,6 EUR nel caso provato), arrotondamenti diversi al centesimo, due regole di pareggio sul tick,
  min_edge/Kelly sui lay calcolati per euro di stake (strategia, D11). Nessun errore critico.»
  E nella riga 34 della tabella: togliere «commissione» dall'elenco di cio' che «torna» oppure aggiungere «salvo B35, B9».

### 2. [MEDIO] 07, riga 36: «nessun bot controlla quanto e' vecchia la previsione che usa»
- Problema: falso per Omega e non verificato per lo scalper. `Betfair/omega/omega_service.py:1154-1166` marca come
  `saved_stale:<fonte>` un lambda salvato oltre `LAMBDA_CACHE_TTL_S` (CERT_4 3.24 lo conferma «CONFERMATO»). CERT_4 3.2
  conferma solo che nessun bot legge `generated_at`; per lo scalper 05 B6 dice «controllo d'eta' NON verificato».
- Correzione: «Mike e Safe non controllano l'eta' della previsione salvata (nessun bot legge `generated_at`); Omega marca
  come "stantio" un lambda salvato oltre il TTL; per lo scalper calcio il controllo d'eta' non e' verificato.»

### 3. [MEDIO] 07 riga 42 («la causa (orologio in ritardo) e' stata tolta oggi»), DECISIONI D20, 05 M1, 06 n.22
- Problema: il nesso «cron GitHub in ritardo di 300-370 min -> 10-13% di previsioni scritte dopo il calcio d'inizio» non e'
  scritto in nessuna fonte primaria. CRONOSTORIA.md:5580-5581 documenta solo il ritardo dei cron e 5586-5600 il nuovo
  orologio (la prima notte vera e' il 10/10, riga 5595: non ancora avvenuta); CERT_1 M1 dichiara «contaminazione effettiva
  NON VERIFICATA» e che l'assunto sull'orario `fixture_date` non e' verificato. Il nesso e' un'inferenza di CERT_4 (0.6).
  Dire «causa rimossa» come fatto, quando il primo riscontro e' di domani, e' non certificato.
- Correzione: 07 «la causa probabile (cron GitHub in ritardo di 300-370 min, CRONOSTORIA.md:5580) dovrebbe essere
  stata tolta oggi con l'orologio pg_cron; il primo riscontro e' la notte del 10/10»; D20 «La causa probabile (cron in
  ritardo) dovrebbe essere stata rimossa il 09/10 ...»; 05 M1 «causa probabile rimossa»; 06 n.22 idem («causa
  rimossa» -> «causa probabile rimossa»).

### 4. [MEDIO-BASSO] 07, riga 33: «passa e boccia quasi a caso»
- Problema: non certificato. CERT_1 A3/MA1 misura altro: un modello PERFETTAMENTE calibrato fallisce ECE<=0,10 nel 98% dei
  casi a n=20, 89% a n=40, 54% a n=87; un predittore che dice solo il tasso base 0,74 PASSA il BSS (0,23). Cioe' boccia
  molti modelli buoni e promuove modelli senza informazione: non «a caso».
- Correzione: «... lo confronta con una moneta invece che con la media della lega: un modello che dice solo il tasso
  base puo' passare, e su 90 partite un modello perfetto fallisce il controllo di calibrazione una volta su due.»

### 5. [BASSO] DECISIONI D3: «lo stop di conto oggi e' spento (NULL)»
- Problema: il valore attuale di `daily_loss_limit` nel DB non e' stato letto (CERT_2 M22: «NESSUNA finche' resta NULL»;
  prova = codice: colonna senza DEFAULT, `config_stream.py:325` «runtime, NULL = off»).
- Correzione: «lo stop di conto e' spento di serie (colonna senza default, NULL = off); il valore attuale nel DB non e' stato letto.»

### 6. [BASSO] REFERTO_FIX_DUTCHING riga 7: «nessun bot (Omega, Mike, Safe, tennis) usa il dutching»
- Problema: Safe importa `dutch_back` in `Betfair/safe_strategy/combos.py:43, 527` (proposte COMBO; `auto_trade_combos: False`,
  `bot_service.py:192`). Il fix tocca solo `dutch_variable`, quindi la conclusione regge, la frase no.
  Stesso rischio in 05 A1 («nessun bot lo usa»: «lo» ambiguo).
- Correzione: «nessun bot usa il dutching VARIABLE (l'unico chiamante e' il worker `_do_dutch`, su richiesta manuale); Safe
  usa `dutch_back` solo per proposte COMBO con auto-trade spento.» In 05 A1: «nessun bot usa `dutch_variable`».

### 7. [BASSO] REFERTO_FIX_DUTCHING, numeri e etichette
- Riga 17 `DutchingPanel.test.tsx (+204)`: `git diff --numstat` = +202/-2 (204 e' il totale righe cambiate). Scrivere «+202/-2».
- Riga 59 «2-12 gambe, quote basse 1,01-1,60»: `_gen_cases_coord.py` usa 2, 6, 10, 12 gambe e quote 1,01-1,60 solo nel 40% dei
  prezzi. Scrivere «2/6/10/12 gambe, 40% delle quote tra 1,01 e 1,60 a 2 decimali». (Il numero 11.911 non azionabili e' CORRETTO:
  contato in `suite/_cases.json`.)
- Riga 49 «M5 bottone + guardBeforeSend + opzione tolti insieme: 2 failed»: nel registro `falsifica_ui_coord2.txt` questo e' M5b;
  M5 (bottone + guardBeforeSend) da solo = 1 failed. Rinominare M5b o riportare entrambi.
- `suite/differenziale_coord_seed424242.txt` finisce con un `ENOENT ... _tick_py.json` (la parte griglia dei tick non e' stata
  eseguita nella corsa del coordinatore); il REFERTO non la rivendica, ma il file e' presentato come prova: aggiungere
  «(la griglia dei tick e' del solo delegato: `differenziale_ts_vs_python.txt`)».
- 07 «10 prove su 11»: la nota onesta del REFERTO dice che DUE clausole di `guardBeforeSend` (variable+lay e pesi
  irrealizzabili) non hanno un test rosso da sole; la prova M7 ne copre una sola. Il 07 puo' restare, ma meglio
  «10 prove su 11; le difese doppie dietro il bottone non hanno un test proprio».

### 8. [BASSO] CERTIFICAZIONE_REFERTI riga 12: «17 blocchi di esempi numerici»
- Problema: CERT_5 riga 17 dice «12 blocchi (circa 45 numeri)»; la sua tabella ha 17 righe numerate.
- Correzione: «17 esempi numerici rifatti (CERT_5 li raggruppa in 12 blocchi)».

### 9. [BASSO] Citazioni file:riga sbagliate (le righe sono state aperte)
- 05 M19 e 06 n.30: `theta_mode` citato con `theta_bot.py:546-551`; quelle righe sono `_hazard`/`hazard_lookup`. `theta_mode` e' in
  `scalper_session.py:1560, 1709` (CERT_2 M19). Correzione: «Theta e' opt-in (`theta_mode`, `scalper_session.py:1560,1709`; l'atlante v3
  e' usato in `theta_bot.py:546-551`)».
- 05 B26: `omega_advisor.py:309` e' `_bound(_ANALYSIS_CACHE)`; la memorizzazione di `None` e' alla riga 308. Scrivere `:308`.
- 01 riga 63 e 00 (P-R3 / pesi di forma): `today_predictions_backfill.py:1493` e' una riga vuota; il dizionario `weights` e' a `:1494`
  (1522 `k_shrink` e 1523 `eta_goals` sono giusti). Scrivere `:1494` (l'errore nasce in CERT_4).
- 03 riga 100 e 04 riga 31: `poisson_calibrator.py:84-90`; il blocco `source="none"` -> db/json e' a `:86-92` (come in 05 B7).

### 10. [BASSO] Incoerenza di gravita'/etichetta fra file
- M20: 05 lo mette nella tabella BASSO con verdetto SCELTA DOCUMENTATA; CERTIFICAZIONE sez. 3 dice «NESSUNA (BASSO "1,25 non calibrato")».
  Allineare 05: «SCELTA DOCUMENTATA; gravita' NESSUNA (BASSO solo per il x1,25 non calibrato)».
- 03 righe 110 e 542: «M-leakage temporale MEDIO, GIA' NOTO (CERT_1 M1)». CERT_1 M1 sono le previsioni scritte dopo il calcio d'inizio;
  CRONOSTORIA.md:4888 dice «split temporale corretto, nessuna fuga». Etichettare «previsioni scritte dopo il KO (CERT_1 M1)»
  e togliere «leakage» (la stessa riga 542 ammette «origine del leakage ... non letto»). Il redattore ha seguito CERT_5 riga 173,
  quindi la correzione e' coerente con la fonte ma l'etichetta e' fuorviante.
- 04 riga 54 (FL-15): la cella dice «perdita attesa ~T*(1-1/book)» e poi la sfumatura «danno non provato»; DECISIONI F6 dice
  «probabilmente non abbinato». Premettere «se l'ordine si abbina,» alla perdita attesa.

## Verificato come corretto

- Fix dutching, codice: `live_order_worker.py:2914-2919` (+5 righe, `if side == "lay": raise ValueError`) esatto; `_write_error` alle
  righe 4005 (canale) e 4372 (coda DB) dentro l'`except` di `_dispatch`; `dutching.py` NON modificato (git status pulito);
  `dutching.py:224, 239` `side="back"`.
- `git diff --numstat`: worker +5, test_dutching +32, test_live_order_dutch_cashout +53, DutchingPanel.tsx +146/-13,
  test.tsx +202/-2; `diff_fix_dutching_COORD.patch` = 613 righe; i 6 test Python e i 15 test vitest nuovi (28-13) corrispondono.
- Suite: PRIMA 11477 passed, 11 skipped, 6 xfailed; DOPO 11483 passed, 11 skipped, 6 xfailed (+6); ROSSO 2 failed/24 passed;
  26 passed finale; vitest 13 -> 12 failed/16 passed con codice vecchio -> 28 passed; tsc: i quattro file sono vuoti (0 errori).
- Falsificazione: P1 2 failed/24 passed, P2 1, P3 3, P4 5, M1 1, M2 6, M3 2, M6 1, M7 28 passed (verde) poi rosso con le due clausole;
  7 mutazioni del delegato (4 + 3 nei due file); sha256 ripristinati True. Differenziali: 0/20.000 (seme 20261009) e 0/99.900 ticks,
  748 con round ingenuo, 2 con somma ingenua; 0/20.000 con seme 424242; 11.911 piani non azionabili (contati in `_cases.json`).
  Esempio 40,51/34,18/25,32 -> 40,50/34,00/25,00 presente nei test. `catch (e: any)` a riga 417 preesistente, nessun `any` nel diff.
- CRONOSTORIA.md: 3058 e 3118 (decisioni O1+M1, veto Under calibrata), 4888 («Nessuna modifica fatta», «un solo motore di lambda (3-4 gg)»,
  «misurare il veto ... (1-2 gg)», 13% ML e 11% Poisson dopo il fischio), 4790-4793 e 4947 (minimi 1,00, multipli di 0,50), 5384-5385 (foglio
  non usato dai bot), 5580-5600 (orologio, ordine approvato dall'utente), 5609-5618 (safe_tennis 18/18, `25cab047`; nessun commit
  successivo su `safe_strategy` / `stream/trading` / `live_order_build.py`), 2956 (E34), 3045-3047 (atlante v4 su Safe e Mike).
- Codice, riga per riga: `seriea_model_export.py:401`, `:50`, `:234-236`; `confidence_gate.py:170-215`; `engine.py:1567`; `bot_service.py:5295`
  (`_model_gate`, «Solo per le uscite in PROFITTO»), `:193`; `live_engine_pro.py:596-607` e `:58-72`; `bias_resolver.py:79-92`;
  `COSTITUZIONE_MIKE.md:157-158`; `config_stream.py:325`; `live_order_build.py:99, 875-886`; `serving.py:46,48`; `money_management.py:1333, 2608`;
  `omega_config.py:61-63, 251-253`; `omega_empirical.py:166-176`; `predict_fixture.py:870-909`; `ensemble_trainer.py:866-872`.
- Numeri: A3 (holdout ~90, media ~170, 43% < 60, 89% a n=40), MA2 (+0,0164 [0,0117; 0,0209]), M1 (160/1.519, 200/1.510), calibrazione O2.5
  (16,2% -> 29,6%, n=27) tutti riscontrati in CERT_1/CERT_4; 04 riga 44 (UI vecchia 30,38/50,63/18,99) ricalcolato a mano: esatto.
- Conteggi di CERTIFICAZIONE: 124 correzioni in 00+03 (62+62, `APPLICATE_00_03.md`), 180 in 01/02/04/06, 428 citazioni scansionate con 2 sbagliate,
  campione 40 = 35/4/1, consumatori falsi P-13, P-15, P-23/24/28, 20 gravita' disallineate: tutti coerenti con CERT_5/APPLICATE.
- Coerenza 05 / 07 / DECISIONI / CERTIFICAZIONE: stessi verdetti e stesse gravita' per A1-A4, MA1-MA2, M1, M11-M13, M17, M19, M21-M22, B39;
  rinvii D4/D5/D13/D15/D20/D23/F1-F6 ai reperti giusti; stesso numero di test (11.477 -> 11.483) e stessa nota .it (40,50/34,00/25,00).
- Campione di 15+ punti nelle correzioni «[cert. fase 2]» di 00-04 e 06 contro i registri APPLICATE: P-09 (doppia vita calibratore),
  P-22 (M20), ML-12 (B22), X-01 (B1), TR-19, FE-05 (M18), WF-09, riga 375 (R1-R8), 380, 184 (minimi/tetto), 463, 506, 549, 593 (M21), 605 (A4), 634:
  tutti corrispondono alla fonte CERT indicata, salvo i punti 9-10 sopra.

## Non verificato da questa revisione
- Le righe B1-B38 una per una (solo B7, B26, B35, B39, B9-B11 riletti); i numeri «tutti riprodotti» di CERT_1/2/3 che richiedono DB.
- `tsc` = 0 errori e' dedotto da file di output vuoti (nessun exit code registrato).
- Il percorso `ValueError` -> esito di errore end-to-end (letto, non eseguito, come dichiara il REFERTO).
