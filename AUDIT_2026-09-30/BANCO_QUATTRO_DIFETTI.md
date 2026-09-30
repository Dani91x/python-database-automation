# BANCO - QUATTRO DIFETTI (30/09/2026)

Delegato di costruzione, worktree `agent-a7e31a5e958513011` (base `fc0428f`, master).
Ordine dell'utente del 30/09: «oggi voglio fixare ogni cosa, anche sul banco».
Nessuna strategia toccata, nessun commit, nessuna modifica a `Betfair/safe_strategy/service.py`.
Diff completo: `AUDIT_2026-09-30/BANCO_QUATTRO_DIFETTI.patch`. NON dichiaro «certificato».

## File toccati / nuovi

Toccati (4):
- `Betfair/stream/backtest/registro_bot.py` (punto 1)
- `Betfair/mike/service.py` (punto 2, SOLO `_CACHE_DI_PROCESSO` / `azzera_cache_di_processo`)
- `Betfair/stream/backtest/banco_comune.py` (punto 3: leva estratta in `rifiuto_provocato`)
- `Betfair/stream/backtest/trasporto.py` (punto 3: leva sul canale)

Nuovi (4 test):
- `Betfair/stream/tests/test_registro_impronta_2026_09_30.py` (punto 1, 35 test)
- `Betfair/mike/tests/test_mike_banco_memorie_processo_2026_09_30.py` (punto 2, 2 test)
- `Betfair/stream/tests/test_banco_rifiuto_sul_canale_2026_09_30.py` (punto 3, 6 test)
- `Betfair/mike/tests/test_mike_banco_e2_2026_09_30.py` (punto 4, 15 test)

`Betfair/mike/certificazione.py` NON toccato (vedi punto 4: E2 non era largo).

---

## 1. Impronta del referto per tutti i bot

**Causa.** `certifica.py:171` `impronta()` fa lo sha1 dei file di `scheda.moduli_produzione`
+ `scheda.controlli`. In `registro_bot.py` Omega, le quattro Safe e i quattro tennis avevano UN
solo modulo (il servizio), lo scalper calcio tre: cambiando motore, config, porta ordini ecc.
l'impronta restava identica.

**Correzione.** `registro_bot.py`: quattro elenchi (`_MODULI_OMEGA`, `_MODULI_SAFE`,
`_MODULI_SCALPER_CALCIO`, `_MODULI_TENNIS`) = CHIUSURA TRANSITIVA degli import del servizio di
produzione DENTRO il pacchetto del bot (librerie e moduli condivisi di `Betfair/stream/` esclusi):
- Omega (12): `omega_service` + advisor, config, db, empirical, engine, market, model, proposte,
  v3, `porta_ordini`, `tools.misura_k` (importato dal servizio).
- Safe base/esatto/punta/tennis (17, stesso `bot_service`): + anomaly, bot_db, calibration,
  canale_scan, `combos` e `tennis_opportunity` (importati PER NOME da
  `bot_service.OPTIONAL_MODULES`/`importlib`), engine, execution, exits, opportunity,
  porta_ordini, pressure, proposte_opportunita, risk, selezione, veto_campionati. Lo scanner
  `safe_strategy/service.py` NON c'e' (non e' importato dal bot).
- Scalper calcio (10): service, session, scalper_bot + auto_mode, bias_resolver, habitat_scan,
  hazard_atlas, risk_semaphore, sniper_bot, theta_bot.
- Tennis scalper/pro/flb/swing (21, stesso `tennis_runner`): i 12 moduli di `tennis_live` + i 9
  di `tennis_scalper` (le quattro strategie, score, winprob, superficie, condotta_ordini,
  run_tennis_scalper). Scelta dichiarata: i quattro bot girano nello STESSO processo con stato e
  tetti condivisi, quindi ciascuno porta l'intera chiusura del runner (impronta prudente: cambia
  anche se cambia una strategia sorella).
- Mike invariato (7, chiusura gia' completa).
Nessun effetto sul comportamento: il registro e' letto solo da `certifica` (impronta, `--elenco`)
e dal test di contratto dei runner (`test_registro_bot_2026_09_16`, verde).

**Test** `test_registro_impronta_2026_09_30.py` (stile di `test_mike_p5_4b_2026_09_29.py`, esteso
alla chiusura transitiva con gli import dentro le funzioni e quelli per nome della Safe):
ogni bot del registro ha una riga di servizio; ogni modulo elencato esiste, senza doppioni; la
chiusura ricalcolata dal sorgente sta nel registro; la chiusura della Safe contiene gli opzionali e
non lo scanner; l'impronta conta `len(moduli)+1` file e CAMBIA se cambia l'ultimo modulo non
servizio (copia in cartella temporanea), per tutti gli 11 bot.

**Falsificazione** (script `_tmp_falsifica.sh`: diff salvato, mutazione, test, ripristino, diff
identico, `grep -c MUTAZIONE` = 0, tutte verificate):
| mutazione | esito |
|---|---|
| M1a `tennis_opportunity` tolto dalla Safe | ROSSA 4 (le 4 Safe) |
| M1b `omega_config` tolto | ROSSA 1 (omega) |
| M1c `tennis_winprob` tolto dal tennis | ROSSA 4 (i 4 tennis) |
| M1d `theta_bot` tolto dallo scalper | ROSSA 1 |
| M1e `impronta` legge solo il primo modulo (il difetto di prima, in `certifica.py`) | ROSSA 11 |

§7: 23/35 (impronta = referto rifacibile, §6.8), 29 (test che guardano davvero: soglia minima
della chiusura). §6.8: «hash del codice del bot».

---

## 2. Memorie di processo non azzerate (Mike)

**Causa.** `Betfair/mike/service.py:2764` `_CACHE_DI_PROCESSO` (usata da
`azzera_cache_di_processo`, che il banco chiama all'inizio di OGNI replay:
`mike/tools/replay_registrazioni.py:925`) non conteneva le quattro memorie dei cantieri J/J2
(28/09), che invece `svuota_le_cache` (`service.py:391-394`) azzerava. Meccanismo misurato sul
codice: `_books_ripiego_rest` (`service.py:1223-1226`) tiene per mercato l'ORA DEL GIRO
dell'ultima lettura REST (`_RIPIEGO_REST_ULTIMO[mid] = now_ts`, ora del REPLAY). Il secondo
scenario sulla stessa partita riparte dall'inizio con l'ora di FINE del primo gia' scritta:
`now_ts - prec` e' negativo, quindi `< 10 s` per tutta la partita, e il ripiego non legge MAI
(referti: 150 letture nei primi scenari, 0 negli altri). Stessa natura per `_FLUSSO_CRITICO` /
`_FLUSSO_RIPIEGO` (promemoria per partita con l'ora del giro: righe `ripiego_rest` /
`flusso_interrotto_senza_rest` soppresse) e `_ULTIMO_STATO_SCANNER` (stato dello scanner del
replay precedente).

**Correzione minima** (solo il punto dell'azzeramento, nessun'altra riga del servizio):
`_RIPIEGO_REST_ULTIMO` e `_ULTIMO_STATO_SCANNER` aggiunti a `_CACHE_DI_PROCESSO` (sono dict);
nuovo `_PROMEMORIA_DI_PROCESSO = ("_FLUSSO_CRITICO", "_FLUSSO_RIPIEGO")`, azzerati col loro
`azzera()` in `azzera_cache_di_processo` e riportati nell'elenco degli azzerati. In produzione
`azzera_cache_di_processo` e' chiamata solo dal banco: effetto nullo sul bot vivo.

**Altre memorie dello stesso tipo (ELENCATE, NON corrette: fuori dal minimo richiesto):**
| memoria | dove | azzerata da `azzera_cache_di_processo`? | effetto sul banco |
|---|---|---|---|
| `_ATTESE_RESTING` (`AttesaRiapertura`, per partita/mercato/ruolo) | `service.py:1848` | NO (solo `svuota_le_cache`) | solo la riga `attesa_riapertura` (una per sospensione) puo' mancare nel 2o scenario; nessuna decisione |
| `_CACHE_FEED`, `_CACHE_AGGREGATI` (`_Cache` con ora) | `service.py:361-362` | NO | nessuno oggi: il banco chiama `_run_event`, non `run_once`/`_righe_del_feed`; con ora del replay avrebbero lo stesso difetto se il banco passasse da `run_once` |
| `_SENZA_RUNNER_LOGGATO` | `service.py:1478` | NO | orologio da parete (`time.time()`), solo dedup di una riga di log |
| `_GUARDIA_AVVIO` (`AA.Guardia`) | `service.py:70` | NO | usata da `run_once`/`loop`, non dal banco |
| `flusso_prezzi._NON_NOTO_AVVISATO` (set per bot) | `Betfair/stream/flusso_prezzi.py:248` (condiviso) | NO | l'avviso `flusso_non_dichiarato` esce una volta per PROCESSO: nel 2o scenario non esce |
| `dossier._EMPIRICAL_CACHE` / `_EMPIRICAL_FAILED` | `Betfair/mike/dossier.py:136-137` | NO | tabella HT->FT: nel banco `ht_ft_rows` e' assente (NON ESERCITABILE); `_EMPIRICAL_FAILED` con ora = stesso tipo di difetto se diventasse esercitabile |
| `db._AGG_RPC` / `_TOTALS` | `Betfair/mike/db.py:42-44` | NO | DB vero, il banco usa il DB in memoria |
Proposta: al coordinatore decidere se aggiungere `_ATTESE_RESTING` (gia' in `svuota_le_cache`)
e `_NON_NOTO_AVVISATO` (modulo condiviso) all'azzeramento del banco.

**Test** `test_mike_banco_memorie_processo_2026_09_30.py`: (a) due «partite» identiche nello
STESSO processo sul ciclo vero (`run` di `test_mike_service`: posizione aperta coi prezzi vivi,
poi linee ferme -> ripiego REST), con in mezzo SOLO `azzera_cache_di_processo` come il banco:
stesse letture REST e stesse righe `ripiego_rest` nella seconda; (b) l'azzeramento nomina e svuota
le quattro memorie, e i promemoria tornano «dovuti» a un'ora PRECEDENTE a quella memorizzata.
Finti: `FakeDB`/`FakeMarket`/righe/`_book_rest` dei test esistenti (chiavi vere).

**Falsificazione:** M2a (i due dict tolti dall'elenco) -> ROSSI 2/2; M2b (promemoria non
azzerati) -> ROSSI 2/2 (il primo per le righe `ripiego_rest`). Ripristino verificato.

**Atteso al replay (verifica del coordinatore):** tutti gli scenari di Mike con gli stessi
tick/letture REST dove la sequenza di chiamate e' la stessa; in particolare «chiamate di LETTURA
a Betfair: 150» non piu' 0 negli scenari dopo il terzo. Nel mio unico replay (punto 3, `--worker
0`, coda poi canale nello stesso processo) il canale ha 150 letture e tick 56098 come nel referto
di prima (li' era il primo scenario del canale): coerente, ma NON prova da solo il punto 2.

§7: 37 (pool che non isola i replay: elenco ESPLICITO, nessun `dir()`), 29.

---

## 3. Leva di rifiuto che non passava sul trasporto canale

**Causa.** La leva (`guasti["place_rifiuto"]`, `rifiuta_lato`, `rifiuta_market_id`,
`rifiuta_sotto_minimo`, codici) viveva SOLO dentro `MercatoFlumine.place_order_live`
(`banco_comune.py`, prima alle righe 541-575). Sulla coda l'ordine del bot passa di li'. Sul
canale la strada e': porta VERA del bot (`PortaCanaleMike`) -> `WsBanco` -> `MotoreOrdini` ->
`live_order_worker._dispatch` -> `Market.place_order` di flumine -> `SimulatedExecution`
(`trasporto.py` `_monta_canale`, `porta_banco.py` `PortaBanco`): `place_order_live` non e' mai
chiamata, quindi la leva non scatta mai (referto P5_4C: motore `rifiutati: 0`, copertura abbinata
a 1,33, -14,17 contro -10,00; il delegato P5 l'aveva gia' segnalato in `MIKE_P5_4.md`).

**Correzione (solo banco).**
1. `banco_comune.py:529` nuovo `MercatoFlumine.rifiuto_provocato(market_id, side, size,
   customer_ref)`: la STESSA condizione e lo stesso conteggio di prima (contatore che si consuma,
   -1 che non finisce, riga in `rifiutati`), estratti riga per riga; `place_order_live` la usa
   (`banco_comune.py:570`), esito della coda identico (test dedicato).
2. `trasporto.py` `_monta_rifiuti_canale` (chiamato in `_monta_canale`, riga 215; tolto in
   `_smonta`): sull'esecuzione simulata VERA del replay (`quadro.simulated_execution`)
   - `execute_place`: per ogni ordine nato dal MOTORE (ref interno `awlq`/`awtq` letto come lo
     legge lo specchio, `live_trading_strategy._client_order_ref`) si consulta la leva; se dice
     no, il `simulated.place` di QUELL'ordine torna `FAILURE` col codice (la size esce dal residuo
     come nel `ERROR_IN_ORDER` di flumine), poi `execute_place` di flumine fa
     `execution_complete()`. Nessun abbinato, nessun ordine vivo. Gli ordini della REST del banco
     (ripiego D5) non hanno ref `awlq`: la leva l'hanno gia' attraversata, non si contano due volte.
   - `execute_replace` (per `copertura-rifiutata-legacy`, sotto minimo): sulla coda il banco
     piazza diretto l'importo sotto minimo (`place_submin_live` -> `place_order_live`); sul canale
     il motore fa il place-and-trim VERO (parcheggio 2,00, taglio, REPLACE alla quota voluta).
     L'ordine che corrisponde a quello della coda e' il NUOVO ordine del replace finale: la leva si
     consulta li' con l'importo residuo, SOLO per un replace di una sequenza place-and-trim in corso
     nel motore (`MotoreOrdini._submin`); se dice no, il nuovo ordine torna FAILURE (annullo
     riuscito, piazzamento rifiutato = forma `CANCELLED_NOT_PLACED` di Betfair, la stessa che il
     banco scrive sulla coda). Il resto (macchina place-and-trim, specchio, eventi `order`, esito
     di Mike) e' codice di produzione.
Nessun bot toccato. Senza leva armata nulla cambia (la leva torna None e flumine esegue come prima).

**Test** `test_banco_rifiuto_sul_canale_2026_09_30.py` (oggetti VERI di flumine:
`FlumineSimulation` col client del banco, `SimulatedExecution`, `Trade`/`LimitOrder`/
`BetfairOrderPackage`, `BaseStrategy`; leva VERA `MercatoFlumine`; `config.simulated` vero come in
`FlumineSimulation.__enter__`; unico finto il `market_book` del replace, di cui
`simulated.cancel` legge solo `status`):
1. ordine del motore colpito: FAILURE, 0 abbinato, 0 residuo, EXECUTION_COMPLETE, `rifiutati`;
   `LiveTradingStrategy._order_row` + `motore_ordini.fase_da_riga` = `annullato` (terminale senza
   abbinato: Mike conta il freno, `service.py` ramo runner `annullato`/`rifiutato`);
2. selettivita' e contatore: BACK (lato sbagliato), OU35 (mercato sbagliato), ordine REST, un
   rifiuto che si consuma -> colpito SOLO il primo LAY OU45 del motore;
3. coda identica con la leva estratta (esito, codice, report interno, -1 non consumato);
4. montaggio VERO: `trasporto.contesto("mike","canale")` + `su_esegui` (porta del banco + client
   VERO di Mike collegato) arma la leva; all'uscita `execute_place`/`execute_replace` tornano
   della classe;
5. sotto minimo: replace del place-and-trim -> annullo riuscito (2,00 tolti in tutto), nuovo
   ordine 1,26 a 4,1 rifiutato, fuori dal blotter, `create_order_replacement` ripristinato;
6. replace fuori da una sequenza in corso e replace della REST NON toccati.

**Falsificazione** (tutte con ripristino verificato):
| mutazione | esito |
|---|---|
| M3a `_monta_rifiuti_canale` non chiamato in `_monta_canale` | ROSSA 1/6 |
| M3b la leva consultata ma mai applicata sul place (`if False`) | ROSSE 3/6 |
| M3c filtro dei ref del motore tolto (anche la REST) | ROSSA 1/6 |
| M3d la size non esce dal residuo (ordine rifiutato ma «vivo») | ROSSE 3/6 |
| M3e `_smonta` non ripristina l'esecuzione | ROSSE 3/6 |
| M3f replace colpito anche fuori dal place-and-trim | ROSSA 1/6 |
| M3g replace mai colpito | ROSSE 2/6 |
| M3h il trucco sul `Trade` non si toglie dopo il replace | ROSSA 1/6 |
(tutte rieseguite sul codice finale; ripristino con diff identico e 0 marcatori)

**Replay (UNO, dichiarato: circa 4 minuti, 10:05:12-10:09:11)**, dopo la correzione:
`certifica mike 35760084 --scenari copertura-rifiutata --trasporto entrambi --worker 0`
(referto: `AUDIT_2026-09-30/mike_copertura_rifiutata_dopo_30_09.txt`, codice bot `ed0dd421eab7`,
eseguito PRIMA di aggiungere il ramo `execute_replace`, che su questo scenario non entra: la banca
12,63 e' sopra il minimo e non passa dal place-and-trim; la sola lettura non-REPLACE del codice e'
identica). NON ho lanciato un replay «prima» (il referto del 29/09 fa da prima) ne' lo scenario
`copertura-rifiutata-legacy` (limite del brief: uno scenario). Prima = referto `AUDIT_2026-09-29/replay/mike_coperture_P5_4C.txt`.
| | coda prima | canale prima | coda dopo | canale dopo |
|---|---|---|---|---|
| rifiuti provocati | 1 | 0 | 1 | **1** |
| P&L netto | -10,00 | -14,17 | -10,00 | **-10,00** |
| riga 5 (banca OU45) | error | open 12,63 a 1,33 | error | **error (uguale alla coda)** |
| stati | ... FLAT | senza FLAT | ... FLAT | **... FLAT** |
| tick coda/canale | 53130 / 56098 | | 53130 / 56098 | |
| violazioni | 0 | 0 | 0 | 0 |
| esito parita' | NON RAGGIUNTA | | **NON RAGGIUNTA (righe 2-4)** | |
Tempi: coda 143,2 s, canale 207,3 s (PC carico dalla suite in parallelo; il 29/09 61,5/70,3 s).

**RESIDUO (preesistente, NON del punto 3, NON corretto):** righe 2, 3, 4 (lay 1,69 sull'Under
3,5, `ko_green` appoggiate e scadute, stato `error`): coda `size 0.0`, canale `size 10.12`. Era
gia' nei referti del 29/09 (P4_4_P5_1, P5_3, P5_4C). E' la scrittura della riga di una lay
appoggiata non abbinata: sulla strada REST/coda la `size` finisce a 0 (abbinato), sulla strada
runner/paper resta la size chiesta (`service.py` ramo terminale di `_segui_ordini_paper_su_runner`
~1703 scrive solo `status`). Non ho trovato dove la coda la azzera (tempo); e' codice del bot, e un
altro delegato oggi lavora in `service.py`: lo porto al coordinatore, non l'ho toccato.

§6.7 (rifiuto di Betfair su tutti e due i trasporti), §7: 2 (`res.ok`/rifiuto mai provocato sul
canale), 8 (nessun fill a mano: il rifiuto e' un FAILURE dell'esecuzione di flumine, il resto e'
produzione), 14 (paper specchio: la parita' coda/canale), 27 (oggetti veri), 30.

---

## 4. Due prove mancanti sul controllo E2 (`Betfair/mike/certificazione.py:383-439`)

**T2 (sopravvissuta)** `if liab <= 0` -> `if False`. Perche' sopravviveva: nessun test metteva una
banca di copertura davanti a un Under 3,5 nullo. Con la mutazione E2 PARLA lo stesso, ma dice una
cosa falsa («banca di copertura 12.63 diversa dall'importo previsto 0.0»): il referto deve citare
la causa vera (§6.8). Test `test_E2_banca_senza_under_abbinato_parla_e_dice_perche` in tre forme
reali (nessuna gamba; ingresso chiesto e non abbinato; ingresso abbinato e poi chiuso per intero):
chiede la violazione E2 CON la causa «senza nessun Under abbinato». Mutazione T2 (byte per byte
dello script del coordinatore) -> **ROSSE 3/3**.

**T3 (sopravvissuta) = mutazione EQUIVALENTE, non uccidibile.** `if size < x and spazio !=
float("inf") \` -> `if size < x \`. Senza tetto `E.liability_room` (`engine.py:1974-1981`) vale
`float("inf")`; la clausola successiva `x * (q - 1) > spazio + 0.011` e' allora `> inf`, FALSA per
ogni x finito: il ramo di tolleranza non si apre comunque e la banca piu' piccola resta una
violazione. Con tetto (spazio finito) la clausola tolta e' vera e il codice e' identico. Nessun
input distingue le due versioni: la condizione `spazio != inf` e' ridondante (documenta
l'intenzione). E2 NON e' largo: nessuna correzione. Ho aggiunto
`test_E2_banca_piu_piccola_senza_tetto_e_sempre_un_errore` (12 casi: frazioni 0,25/0,5/0,99 x quote
1,05/1,20/1,50/3,00): verde con T3 (atteso, equivalente) e **ROSSO** con la mutazione SEMANTICA che
T3 voleva provare (T3-bis: «senza tetto la banca piu' piccola si accetta», un `continue` quando
`spazio == inf`): **14 rossi** = tutti i 12 casi nuovi + 2 di `test_mike_p5_banco_2026_09_29`
(`test_E2_banca_sbagliata_parla`, `test_E2_banca_ridotta_dal_tetto_e_giusta`). T3 byte per byte:
28/28 verdi (equivalente, come dimostrato sopra).

§7: 28-30 (test che passa a vuoto / mutazioni non catturate), 16 (il controllo che dice la causa
giusta).

---

## Suite (a pezzi, un processo per cartella, ambiente neutro di `replay_mike.sh`)
Comando: `python -m pytest <cartella> -q -p no:cacheprovider` con le variabili di
`AUDIT_2026-09-30/ereditato_29_09/scratchpad_admin_e7/replay_mike.sh` (script `_tmp_pytest.sh`).

Giro 1 (10:18-10:35, codice intermedio: senza il ramo `execute_replace`):
| pezzo | esito |
|---|---|
| Betfair/mike | 1239 passed |
| Betfair/stream/tests | 3130 passed, 25 skipped, **2 failed** (vedi sotto) |
| Betfair/omega | 1418 passed, 3 skipped |
| Betfair/safe_strategy | 2015 passed, 3 skipped, 1 xfailed |
| Betfair/stream/tennis_live | 649 passed |
| Betfair/stream/tennis_scalper | 272 passed |
| Betfair/tests | 58 passed |
I 2 rossi: (a) `test_submin_contratto_chiamanti_2026_09_17::test_nessun_chiamante_nuovo_non_registrato`:
la docstring del mio `trasporto.py` NOMINAVA `place_submin_live` (il test cerca la parola nei
sorgenti): riformulata la docstring, `trasporto.py` non chiama il place-and-trim; (b)
`test_auto_follow_2026_09_25::test_latenza_logica_aggancio_sotto_i_20_ms` (22,4 ms > 20 ms):
cronometro sotto carico (suite + replay in parallelo), file non toccato; rilanciato da solo: 31/31.

Giro 2 sul codice FINALE (dopo la docstring e il ramo `execute_replace`):
| pezzo | esito |
|---|---|
| Betfair/mike | **1239 passed** (comprese le 17 nuove: 15 E2 + 2 memorie) |
| Betfair/stream/tests | **3134 passed, 25 skipped, 0 failed** (comprese le 41 nuove: 35 impronta + 6 canale) |
| test_auto_follow_2026_09_25.py (da solo) | 31 passed |
Omega, Safe, tennis_live, tennis_scalper, Betfair/tests NON rilanciati sul codice finale: le
modifiche del giro 2 stanno solo in `trasporto.py` (ramo `execute_replace` armato solo sul
trasporto canale del banco, docstring) e nei test nuovi; nessun test di quei pezzi monta il
canale col replace (non verificato a riga di comando: va rilanciato dal coordinatore).

## Parita' paper/live
Nessuna modifica al codice dei bot che giri in produzione: `registro_bot.py` (metadati del banco),
`azzera_cache_di_processo` (chiamata solo dal banco), `banco_comune.py`/`trasporto.py` (solo banco).
Paper e live identici a prima. Il punto 3 RENDE il banco piu' specchio: la stessa leva vale sulla
strada live REST (coda) e sulla strada paper del runner (canale).

## Effetti attesi su altri referti (da verificare al replay del coordinatore)
- Impronta `codice_bot` di TUTTI i bot cambia (piu' file): i referti nuovi non sono confrontabili
  per impronta con quelli vecchi, solo per numeri.
- Omega/Safe/Safe tennis/Mike: gli scenari con leva armata (`rifiuti`, `copertura-rifiutata*`)
  sul trasporto `canale`/`entrambi` ora rifiutano anche sul canale (prima no): referti del canale
  diversi da quelli del 29/09, per costruzione.
- Mike: letture REST e righe del ripiego uguali in tutti gli scenari dello stesso processo.

## Decisioni per l'utente
Nessuna (nessuna strategia toccata).

## COSA NON HO POTUTO VERIFICARE
1. **`copertura-rifiutata-legacy` sul canale end-to-end**: il ramo `execute_replace` (rifiuto del
   replace finale del place-and-trim) e' provato solo con test di unita' su oggetti veri di
   flumine; NON ho lanciato lo scenario (limite del brief: un solo scenario). Non so come la
   macchina place-and-trim del motore (`advance_submin` dopo un replace FAILURE) chiuda la
   sequenza: puo' finire in `annullato` (freno conta) o in `errore` (esito ignoto ->
   riconciliazione di Mike, freno NON conta). In entrambi i casi e' il comportamento di
   produzione davanti a un replace rifiutato, ma la parita' con la coda (-3,00) va misurata dal
   coordinatore.
2. **Parita' coda/canale di `copertura-rifiutata` ancora NON RAGGIUNTA** per le righe 2-4 (size
   0,00 vs 10,12 di tre `ko_green` appoggiate scadute): preesistente, codice del bot, NON
   diagnosticato fino alla riga (vedi punto 3, «RESIDUO»).
3. Il punto 2 al replay completo (`--scenari tutti`): non lanciato (lo fa il coordinatore). Il mio
   test riproduce il riuso su due partite finte sul ciclo vero, non la registrazione.
4. Il replay del punto 3 e' stato eseguito PRIMA del ramo `execute_replace` (codice diverso da
   quello consegnato per quel solo ramo, che su questo scenario non entra).
5. Tempi del replay (143 s coda / 207 s canale) misurati col PC carico dalla suite in parallelo:
   non confrontabili col tetto di §6.9.
6. Omega, Safe, tennis sul codice finale: vedi «Suite», giro 2.
7. La chiusura degli import del punto 1 e' statica (AST): un import fatto con una stringa
   costruita a runtime diversa da `OPTIONAL_MODULES` della Safe non sarebbe visto (cercati
   `import_module`/`__import__` nei cinque pacchetti: solo la Safe, gestita, e un
   `__import__("db_client")` di Omega fuori dal pacchetto).
