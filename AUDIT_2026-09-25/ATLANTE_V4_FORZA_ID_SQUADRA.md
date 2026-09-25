# Atlante v4: A* COMPLETO, forza pre-partita dagli id squadra (25/09/2026 notte)

Delegato del coordinatore, worktree `agent-aaa9cdc10faf98440`, base `1ba167e` (rebase su origin/master: gia' allineato).
Nessun commit, nessun push, nessuna scrittura sul DB, nessuna lettura sul DB vero. Non toccati: soglie
(`hazard_warn`/`hazard_drop`), `combine_hazard`, Safe `engine.py`/`exits.py`, `omega_v3.py`, `mike/engine.py`,
le parti approvazioni/proposte di `bot_service.py`, `mike/service.py` (`approva_uscita`), `omega_proposte.py`.

## 0. Sintesi
- **Il v4 collegato passa da A1+A2 ad A\***. La forza pre-partita e' il Poisson-Elo del banco
  (`validazione_hazard/forza.py`), NON i lambda di `fixture_predictions`. Si calcola per lega dallo **stesso storico
  gia' letto** dal generatore e dal motore a domanda. Finisce nel blocco `atlas["v4"]["by_league"][lid]["forza"]`.
  `consulta_atlante_v4` la usa quando riceve `home_id`/`away_id` (id squadra API-Football).
- **Id squadra ai consumatori, zero letture in piu'.**
  - Safe: dalla riga `fixture_predictions` gia' letta (`fixtures_for_window`) quando la fixture e' abbinata; per le
    altre fonti di lambda, dalla stessa finestra **se e' gia' in cache**. Gli id viaggiano in una copia del payload
    che arriva a `_hazard_check`.
  - Mike: dalla stessa riga (stessa richiesta) di `get_fixture_prematch_lambdas`, in piu' due colonne. Finiscono nel
    dossier, e `live_frame` li passa all'atlante.
- **Parita' col banco (A\*)**: lambda max diff **6,35e-8**; p a 2' e 3' max diff **8,04e-8** su **79.068 stati**
  (sonda). Nei test: soglia 1e-6 su 1.800 stati, regolari e recupero 2T.
- **Note**:
  - con la forza: «atlante v4 (A\*), regolare, forza usata: casa 0,88 / trasferta 0,96»;
  - senza: «atlante v4 (A1+A2), regolare, forza non usata: id squadra assenti».

  Soglie e decisioni invariate: stesse regole sul dato nuovo.
- **Test**: 18 nuovi. **Falsificazione 29/29 rosse**; al primo giro erano 27/28, i dettagli sono al §5.
  **Suite dei file toccati: 3.964 passati.**
- **Replay: non cambiano le decisioni.** Le registrazioni non hanno `fixture_predictions`: la finestra di Safe e'
  vuota e il `fixture_id_for_event` di Mike restituisce None. Quindi niente id e forza non usata. Cambiano solo le
  note. Vedi §7.

## 1. Cosa fa ora -> dopo (file:riga)
| dove | prima (`1ba167e`) | dopo |
|---|---|---|
| `atlante_v4.py:82-90` | - | `FORZA_ETA` **0,035** (correzione del coordinatore, par. 9), `FORZA_RIENTRO` 1,0, `FORZA_ALFA_LEGA` 0,01, `FORZA_MU_INIZIALE` = `forza.MU_INIZIALE`, `FORZA_MAX_RITARDO_GIORNI` 60 |
| `atlante_v4.py:184,190` `stato_v4_vuoto`/`forza_vuota` | nessuna forza | lo stato v4 nasce con `forza`: `{mu, squadre{tid:[log_att, log_dif, stagione]}, stagione, n, ultima[data,fid], fuori_ordine, saltate}` |
| `atlante_v4.py:213` `aggiungi_forza` | - | **lo stesso passo** di `lambda_prepartita`: stesse operazioni, stesso ordine. Una partita piu' vecchia dell'ultima applicata viene applicata se il ritardo e' di 60 giorni o meno, altrimenti e' saltata; in entrambi i casi e' contata |
| `atlante_v4.py:261` `applica_coda_forza` | - | applica il lotto in ordine (data AAAA-MM-GG, fixture_id): e' l'ordine del banco, non quello di lettura del DB (per fixture_id) |
| `atlante_v4.py:284` `lambda_da_forza` | - | lambda della **prossima** partita h-a. Una squadra mai vista nella lega ha rating 0, come nel banco, e finisce in `senza_storico` |
| `atlante_v4.py:491-495` `assembla_v4` | - | `by_league[lid]["forza"]` (rating a 7 decimali) e `meta.forza` |
| `atlante_v4.py:660,725-760` `consulta_atlante_v4` | la forza era usata solo con i lambda espliciti (il banco) | nuovi `home_id`/`away_id` -> lambda dal Poisson-Elo della lega. `forza` porta `usata`, `motivo`, `fonte`, `casa`, `trasferta`, `lambda_*`, `senza_storico`. Motivi: «id squadra assenti», «lega non nel v4: forze squadra assenti», «forze squadra della lega non ancora calcolate», «ripiego sul v3». **Gli id sono parametri nominati: non arrivano piu' al ripiego v3** (vedi §6.1) |
| `atlante_v4.py:794,812,827` note | «forza x1.04» / «forza non usata» | `testo_forza`, `etichetta_versione`, e base «storico v4 (A\*)» oppure «storico v4 (A1+A2)» |
| `genera_atlante.py:191-236` `aggiungi_v4` | somma solo celle/recupero | accoda anche `(v4, partita)` per la forza, **solo se** `aggiungi_partita` del v3 l'ha appena contata (stessa idempotenza, nessuna lista in piu'). `applica_coda_forza` |
| `genera_atlante.py:657-697` `_sequenze` | - | coda propria, applicata a fine lotto in `finally` |
| `genera_atlante.py:823-842` `incrementale` | - | **una** coda per tutti i lotti del giro (fixture_id a lotti != date), applicata in `finally` |
| `genera_atlante.py:558` `assembla_blocco_v4` | vista senza forza | + `forza` |
| `atlante_a_domanda.py:84` `_v4_completo`, `:212`, `:247` | adottava/considerava completo ogni stato con `v4` | stato v4 **senza forza** = incompleto, quindi non adottato dal DB e ricalcolato per intero con lo stesso tetto (i rating sono cronologici: non si ricostruiscono a pezzi) |
| `atlante_a_domanda.py:315-391` incrementale | `G.aggiungi_v4(st, m, gg)` | coda del giro e `G.applica_coda_forza` in `finally` |
| `stream/db.py:211-262` `get_fixture_prematch_lambdas` | select di 3 colonne, tupla di 3 | `con_squadre=True`: **stessa riga, stessa richiesta**, piu' `home_team_id,away_team_id` e tupla di 5. Il default e' identico per Omega e runner (select e tupla, provati) |
| `mike/db.py:514-524` `fixture_lambdas` | tupla di 3 | `con_squadre=True` |
| `mike/dossier.py:59,73,85-87` `build_prematch` | dossier senza id | `home_team_id`/`away_team_id` (None se la tupla non li porta) |
| `mike/dossier.py:~330` `live_frame` | passava gia' `home_id=dossier.get("home_team_id")`, che finiva al v3 (sempre None) | stessa riga: ora gli id li consuma il v4 (forza) |
| `safe_strategy/bot_service.py:6549-6590` | `_lambdas_from_fixture` senza id | `**_ids_squadra(fixture)`, `_ids_squadra`, `_ids_squadra_da_finestra` (solo cache, fixture di un'altra lega scartata) |
| `bot_service.py:6645-6649` `resolve_event_lambdas` | - | per le fonti diverse dalla fixture abbinata: id dalla finestra in cache. `league_id` e lambda **invariati** |
| `bot_service.py:6850-6855` `process_opportunities` | `model.evaluate(payload, ...)` | `evaluate(payload_eval, ...)`: una **copia** con gli id. La riga del feed non si tocca. La firma di `evaluate` resta quella del banco (`proposte_modello.ModelloCalcioReplay` non ha `**kw`: un kwarg nuovo avrebbe rotto il replay) |
| `safe_strategy/opportunity.py:688-710` `_hazard_check` | niente id; nota «atlante v4, fase» | `home_id`/`away_id` dal payload; `out["forza"]`; nota con `etichetta_versione` e `testo_forza` |

## 2. Parita' col banco (A\*)
- **Test** `test_parita_lambda_forza_col_proxy_del_banco`. Stesse righe del DB (finto PostgREST, colonne vere,
  `raw_json`): 2 leghe × 16 squadre × 4 stagioni, fixture_id mescolati rispetto alle date. I rating del blocco danno
  per la prossima partita h-a gli stessi lambda di `lambda_prepartita(partite + [nuova])`.
  - Differenza ≤ 1e-6 sul blocco arrotondato.
  - Differenza ≤ 1e-12 sullo stato grezzo.
- **Test** `test_parita_p_astar_col_candidato_validato`. Il riferimento e' A\* = `candidati` ConfA(emivita 3,
  forza=True), addestrato coi lambda del proxy; beta stimato **dal banco** sugli stessi dati e messo nel blocco. Su
  1.800 stati (700 regolari e 200 di recupero 2T per lega) `consulta_atlante_v4(..., home_id, away_id)` e
  `prevedi_a` danno p2 e p3 con differenza ≤ 1e-6.
- **Sonda** `sonde/esempi_note_forza.py`: 3 coppie per lega e tutti gli stati regolari/2T a passo 7. Lambda max diff
  6,35e-8, p max diff 8,04e-8 su 79.068 stati (eta 0,035).
- **Beta in produzione**: `BETA_DEFAULT` (0,612/0,610), stimato dal banco sul DB vero. Invariato.
- **Parametri del Poisson-Elo** (SUPERATO, vedi par. 9: vale eta 0,035): eta 0,015 e rientro 1,0, presi dal referto VALIDAZIONE_HAZARD §2 e §3 («scelte
  congelate»). **Attenzione**: il `risultati_validazione.json` committato dice eta 0,035. Ma e' la corsa di prova
  `--fumo` (1 partita su 10), come mostrano `A_star` = A1 e 7 leghe affidabili su 15. Da confermare col
  coordinatore (§7.2).

## 3. Costi (misurati, `sonde/costo_forza_v4.py` -> `_esito.txt`)
| voce | misura |
|---|---|
| richieste al DB | **invariate**: 30 = 30 nel bootstrap di una lega grande (lettore finto). Safe: 0 in piu' (test: `window_calls == 0` con la catena di Omega). Mike: 0 in piu' (stessa richiesta, 2 colonne intere in piu') |
| CPU della forza | **11,2 µs a partita**, ordinamento compreso: 42,7 ms per 3.800 partite (lega grande, 10 stagioni). Il bootstrap intero (7-10 s) e' dominato da `stati_partita`, e la differenza con/senza forza e' sotto il rumore |
| stato grezzo (jsonb `hazard_atlas_leghe`) | forza **1.283 B** su 12.726 B di stato v4 (20 squadre). Con 30-40 squadre in 10 stagioni, circa 2-2,5 KB (stima) |
| blocco nel file live | **799 B** per lega. Con 20 leghe il file passa da 276.678 a 292.579 B (+5,7%) |
| assemblaggio 20 leghe | 79 -> 101 ms |
| consultazione | 0,064 ms senza id, 0,101 ms con id |
| Safe, abbinamento sulla finestra in cache | una `_match_fixture` in memoria per evento e per TTL della cache lambda (300 s per le fonti deboli, 3.600 s per quelle buone). Non misurato a parte |

## 4. Note a video prima/dopo (`sonde/esempi_note_forza.txt`, dati sintetici, lega 39)
- **Safe 65' 1-1**:
  - prima: «…divergenza 2%; atlante v4 (A1+A2), regolare, forza non usata: id squadra assenti; atlante del 25/09, 1920 partite)», con p_atlas 0,0811;
  - dopo (id 1004-1011): «…divergenza 9%; atlante v4 (A\*), regolare, forza usata: casa 0,88 / trasferta 0,96; atlante del 25/09, 1920 partite)», con p_atlas 0,0765;
  - decisione: nessun drop, penalty 1,0 in entrambi i casi.
- **Mike 80' 1-0**:
  - prima: «storico v4 (A1+A2) lega 39 (lega, 960 partite) [regolare; forza non usata: id squadra assenti; confidenza media; …]», con hazard_atlas 0,0656;
  - dopo: «storico v4 (A\*) lega 39 … [regolare; forza usata: casa 0,88 / trasferta 0,96; …]», con hazard_atlas 0,0619.
- **Significato di casa/trasferta**: lambda della squadra diviso i gol medi casa/trasferta della lega (mu del
  Poisson-Elo). Una squadra senza storico nella lega (neopromossa) aggiunge «(casa senza storico in lega: neutra)».

## 5. Test e falsificazione
- **Nuovo**: `Betfair/stream/tests/test_atlante_v4_forza_id_squadra_2026_09_25.py`, 18 test. Coprono:
  - parita' dei lambda e di A\*;
  - p che si muove con la forza e p di A1+A2 senza id;
  - i motivi della forza non usata;
  - id mai passati al ripiego v3, su entrambi i rami;
  - incrementale a lotti uguale al bootstrap, idempotente;
  - incrementale che si rompe senza perdere la forza delle partite gia' contate;
  - ordine per data e non per fixture_id;
  - partite fuori ordine: la recente applicata, la vecchia saltata;
  - motore a domanda: incrementale uguale al bootstrap, nessun doppio conteggio;
  - stato v4 senza forza non adottato e ricalcolato;
  - dimensione del blocco;
  - Safe `_hazard_check` con gli id: nota e decisione;
  - Safe: id dalla fixture abbinata nel payload, riga del feed intatta;
  - Safe, catena di Omega: id dalla finestra in cache, zero letture senza cache, scarto della fixture di un'altra lega;
  - `stream.db`: select di default invariata e `con_squadre`;
  - Mike: dossier con gli id, `live_frame` con la forza, tupla vecchia di 3;
  - Mike: il ripiego v3 non usa gli id.
- **Finti con chiavi e tipi veri**: righe `matches` con le colonne vere e `raw_json`; righe fixture con le colonne
  della select di `omega_db.fixtures_for_window`; tupla di `get_fixture_prematch_lambdas`. Il finto `evaluate` ha la
  firma del banco.
- **Test esistenti adattati** (contratto nuovo delle note, dichiarato):
  - `test_atlante_v4_2026_09_25.py:147`: il dict `forza` porta ora `motivo`;
  - `test_atlante_v4_collegato_2026_09_25.py:427`: la nota e' «atlante v4 (A1+A2), <fase>» piu' «forza non usata: id squadra assenti».
- **Falsificazione** (`sonde/falsificazioni_forza_v4.py`). Ripristino dal testo in memoria con verifica dell'hash.
  - **Giro 1: 27/28** (`_esito_giro1.txt`). F9 (id girati al ripiego v3) era **VERDE**, perche' il test copriva solo
    il ramo «blocco v4 assente». Ho aggiunto il ramo «lega non ancora nel v4», e nel giro 2 F9 e' diventato ROSSO.
  - Tra i due giri ho aggiunto il `finally` (la coda si applica anche se un lotto cade), con il suo test e la sua
    rottura F29.
  - **Giro 2: 29/29 rosse; suite verde dopo i ripristini** (`_esito.txt`).
  - Nota su F1 (eta diverso): diventa rosso perche' un test **fissa** eta = 0,015. La parita' da sola non lo
    vedrebbe, perche' banco e produzione leggono la stessa costante.
- **Suite dei file toccati** (sandbox DB, timeout 600): 3.964 passati, 6 saltati, 1 xfail. I file:
  - i 6 test dell'atlante (nuovo, collegato, v4, a domanda, genera, validazione);
  - `Betfair/safe_strategy/tests`, `Betfair/mike/tests`, `Betfair/omega`.

  Piu' `Betfair/stream/tests -k "db or runner or stream"`: 2.127 passati.

## 6. Reperti
1. **Latente in `1ba167e`, chiuso**: Mike `live_frame` passava gia' `home_id=dossier.get("home_team_id")` a
   `consulta_atlante_v4`. Finiva in `**kw_v3`, cioe' al **livello squadre del v3**, che il referto di validazione
   misura come peggiorativo (+0,00120). Era dormiente solo perche' il dossier non aveva gli id. Ora gli id sono
   parametri nominati del v4 e il ripiego v3 resta quello di ieri (test su entrambi i rami).
2. **Forza per lega, non globale**: nel banco `lambda_prepartita` gira su tutte le leghe insieme (una squadra
   promossa porta il suo rating dalla lega di sotto). In produzione il generatore e il motore lavorano per lega:
   una neopromossa parte neutra (rating 0) e la nota lo dice. **L'effetto sulla log-loss non e' misurato**: la cache
   del banco non c'e' piu', e rileggere il DB era fuori brief.
3. **Incrementale fuori ordine**: due partite dello stesso giorno arrivate in giri diversi sono applicate
   nell'ordine d'arrivo, mentre il banco le ordina per fixture_id. Le squadre sono diverse, quindi i rating
   commutano. Resta solo l'effetto sulla media di lega, dell'ordine di alfa² (non misurato). Una stagione vecchia
   acquisita dopo (oltre 60 giorni di ritardo) e' saltata e contata in `saltate`.
4. **Stati v4 scritti tra `1ba167e` e oggi** (senza forza): il motore a domanda li ricalcola per intero quando la
   lega e' osservata, con gli stessi tetti. Il job notturno (`genera_atlante --scrivi-db`) non li completa, e quelle
   leghe restano senza forza: la nota lo dichiara.
5. **Safe, catena di Omega**: se la finestra delle fixture non e' mai stata letta (tutti gli eventi risolti da
   Omega), gli id mancano. Scelta voluta per il vincolo «nessuna lettura in piu'». Alternativa, da decidere: 1
   lettura leggera ogni 10 minuti (`_fixtures_window`).

## 7. Non verificato
1. **Nessun ciclo reale** del motore o del generatore sul DB, nessuna lettura del DB. Colonne `home_team_id`/
   `away_team_id` di `fixture_predictions`: esistono gia' nella select di produzione di
   `omega_db.fixtures_for_window` e nei `_CTX_KEYS` di `today_predictions_backfill.py`. Non le ho interrogate.
2. **eta**: CHIUSO dal coordinatore, vale 0,035 dell'artefatto (par. 9).
3. **Guadagno reale di A\* in produzione**: nessuna misura nuova, valgono i numeri del banco (−0,00067 contro −0,00038
   sui regolari).
4. **Replay** (non eseguiti, come da brief; uno per bot, in sequenza):
   ```
   python -m Betfair.stream.backtest.certifica safe_base 35760084 --scenari tutti --worker 1
   python -m Betfair.stream.backtest.certifica safe_esatto 35760084 --scenari tutti --worker 1
   python -m Betfair.stream.backtest.certifica safe_punta 35760084 --scenari tutti --worker 1
   python -m Betfair.stream.backtest.certifica mike 35760084 --scenari tutti --worker 1
   python -m Betfair.stream.backtest.certifica omega 35760084 --scenari tutti --worker 1
   ```
   Atteso: **stesse decisioni e stesso P&L di `1ba167e`**.
   - Nel replay `fixtures_for_window` restituisce [] (`omega/tools/replay_registrazioni.py:640`), quindi Safe non
     ha id.
   - `DbMemoria.__getattr__` restituisce None su `fixture_id_for_event`, quindi Mike non ha id.
   - Forza mai usata: cambiano solo le note («(A1+A2) … forza non usata: id squadra assenti»).
   - Omega non e' toccato.

   **La forza quindi non e' esercitabile dal banco replay**: servirebbe una registrazione con la fixture.
5. Suite intere: non eseguite (brief).

## 8. Consegna
- Patch: `AUDIT_2026-09-25/atlante_v4_forza.patch` (`git diff`, 10 file tracciati).
- File nuovi (non tracciati):
  - `Betfair/stream/tests/test_atlante_v4_forza_id_squadra_2026_09_25.py`;
  - in `AUDIT_2026-09-25/sonde/`: `costo_forza_v4.py` (+`_esito.txt`), `falsificazioni_forza_v4.py`
    (+`_esito.txt`, `_esito_giro1.txt`), `esempi_note_forza.py` (+`.txt`);
  - questo referto.

## 9. Correzione del coordinatore (eta 0,015 -> 0,035)
- **Il coordinatore ha verificato** `validazione_hazard/risultati_validazione.json` (addestra ≤2023, valuta 2024):
  - `forza.scelta` = {eta 0,035, rientro 1,0}, in testa alla griglia (ll −2,93491);
  - vale l'artefatto, non il testo del referto.
- **Modifiche**:
  - `atlante_v4.py:82`: `FORZA_ETA = 0.035`, commento aggiornato;
  - il test fissa 0,035;
  - il lato banco del test chiama `lambda_prepartita(partite, eta=0.035, rientro=1.0, alfa_lega=0.01)` con valori
    **letterali**, non con le costanti di produzione. Cosi' la parita' non e' piu' circolare.
- **Parita'**: lambda max diff 6,35e-8, p max diff 8,04e-8 su 79.068 stati. Test di parita' verdi (≤1e-6).
- **Falsificazione F1** (produzione con eta 0,02, rieseguita a mano con ripristino da copia): **4 test ROSSI**, cioe' le
  due parita' (lambda e p di A\*), i motivi e la costante. Prima, con la costante letta da entrambi i lati,
  diventava rosso solo il test della costante.
  - Il giro completo 29/29 in `_esito.txt` e' stato eseguito con eta 0,015 e non l'ho ripetuto.
  - Le altre 28 rotture non dipendono da eta; la F1 della sonda punta ora a `FORZA_ETA = 0.035`.
- **Suite dei file toccati**: 2.668 passati, 3 saltati, 1 xfail (6 test atlante, `safe_strategy/tests`, `mike/tests`).
- **Costi**: eta non cambia il costo, quindi la sonda non e' stata rieseguita. Note e parita' rigenerate in
  `sonde/esempi_note_forza.txt`.
- **Non verificato**: con quale eta sia stato stimato `BETA_DEFAULT` (0,612/0,610). Non l'ho toccato, come da ordine
  (nessun altro cambiamento).
