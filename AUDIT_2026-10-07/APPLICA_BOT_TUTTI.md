# APPLICA BOT PER TUTTI I BOT + MENU DEI PARAMETRI (07/10/2026)

Delegato del coordinatore, worktree `/home/user/python-database-automation/.claude/worktrees/agent-a782862d3db4df909`
(ramo `worktree-agent-a782862d3db4df909`, base `8226d766`). Lavoro NON committato.

Ordini dell'utente (07/10, testuali): «portare TUTTI I BOT nella sezione "applica bot", cosi' posso testare tutti i
bot e le loro strategie direttamente sui dati registrati reali» e «Organizza meglio il menu' a tendina con le varie
impostazioni dei bot (devo poter modificare i parametri di ognuno cosi' da provare altre varianti SENZA CAMBIARE LA
STRATEGIA)». Avvisi del coordinatore recepiti: `clic_ms` (solo ai bot che lo dichiarano), bool come interruttori,
registrazione tennis 35790089, PAGINA TENNIS SEPARATA (qui solo componenti riusabili con `sport`), design system.

## 0. In una tabella

| bot | sport | cronologia ordini (codice di produzione) | parametri esposti | `dal_ms` (strada) | scenari offerti / scartati | prova prima/dopo IDENTICA (parametri e dal_ms assenti) | test nuovi | falsificazioni |
|---|---|---|---|---|---|---|---|---|
| mike | calcio | SI: 2 ordini su 35797769 (punta 10 @1,46 abbinata, banca 10,14 @1,44 appoggiata -> abbinata) | 41 (whitelist `config.PARAM_SPEC`) | control `stopped` -> `running` + parametri del giro = `service._params_for(.., running=False)` finche' spento | 5 / 21 | SI, `base` 35797769 (vedi par. 3) | 3 dedicati + 1 lungo su registrazione + contratto | 5 rosse |
| omega | calcio | SI (specchio agganciato); 0 ordini sulle 2 registrazioni calcio dell'ambiente (vedi par. 6) | 17 (V4) / 20 (v2), whitelist `omega_config._SPEC` | `omega_control.status` `stopped` -> `running` (letto da `run_once`) | 7 / 13 | SI, `apertura` 35797769 | 2 + contratto | 1 rossa |
| safe_base | calcio | SI (specchio); 0 ordini della sola variante BASE su 35797769 | 14 | control `stopped` -> `running` (`run_once`) | 1 / 22 | SI, `base` 35797769 (le 3 varianti, come la certificazione) | 2 + contratto | 2 rosse |
| safe_esatto | calcio | SI (specchio); vedi par. 6 | 10 | idem | 1 / 22 | (stesso modulo di safe_base) | idem | idem |
| safe_punta | calcio | SI (specchio) | 9 | idem | 1 / 22 | (stesso modulo) | idem | idem |
| scalper_calcio | calcio | SI (gia' dal 06/10, specchio della sessione) | dell'ALTRO delegato (`replay_registrazioni:parametri_modificabili`, non ancora nel mio worktree) | dell'altro delegato | 16 / 13 | non toccato da me | contratto (2 ROSSI finche' non si integra l'altro delegato) | - |
| safe_tennis | tennis | SI (specchio); 0 ordini su 35790089 (anche nel referto di HEAD) | 15 | control `stopped` -> `running` (`run_once`) | 2 / 16 | SI, `base` 35790089 | 1 + contratto | 1 rossa |
| tennis_scalper | tennis | SI: 71 ordini (gate-aperto), 4 con stake 4 acceso a meta' | 11 (istanza vera di `_instantiate_bot`) | il bot NON riceve book prima di `dal_ms` (in produzione nasce all'armamento) | 7 / 10 | SI, `base` e `gate-aperto` 35790089 | 2 su registrazione vera + contratto | 2 rosse |
| tennis_pro | tennis | SI: 5 ordini (gate-aperto) | 9 | idem | 7 / 10 | SI, `base` | contratto | (stesso codice) |
| tennis_flb | tennis | SI: 6 ordini (gate-aperto; `live` = stesse 6 righe con `mode='live'`) | 7 | idem | 7 / 10 | SI, `base` | contratto | (stesso codice) |
| tennis_swing | tennis | SI: 24 ordini (gate-aperto) | 6 | idem | 7 / 10 | SI, `base` e `gate-aperto` | contratto | (stesso codice) |

Il registro ha **11** bot (non 13: il brief diceva «verifica gli altri»; verificato con `registro_bot.elenco()`).
Nessun bot e' disattivato per mancanza di cronologia (`applica_bot.SENZA_CRONOLOGIA` vuoto).

## 1. Cosa ho fatto e perche' (contratto comune, alla lettera)

1. **`parametri` e `dal_ms` nella funzione di replay di ogni bot** (keyword, default `None` = referto identico):
   * Mike (`Betfair/mike/tools/replay_registrazioni.py`): `certifica_scenario(..., parametri, dal_ms)`; le sostituzioni
     vanno nei `params` dello scenario, cioe' in `mike_control.params` del `DbMemoria` e in `self.params` del giro
     (come oggi lo scenario); coppie min/max invertite -> `ValueError` (in produzione `merge_params` le riporterebbe
     IN SILENZIO al default). Accensione: control `stopped` fino a `dal_ms`, poi `running`; **reperto**: il replay di
     Mike chiama `service._run_event` direttamente (non `run_once`), quindi lo `status` del control da solo NON fermava
     gli ingressi (prima prova: punta piazzata 1 minuto PRIMA dell'accensione). Correzione: finche' spento i parametri
     del giro sono `service._params_for(params, False, mode)`, la funzione che `run_once` di produzione usa a bot
     fermo (pre-match, re-ingresso e ultimo ingresso spenti, protezioni attive). Da acceso (o senza `dal_ms`) i
     parametri di sempre, riga per riga.
   * Omega: sostituzioni in `omega_control.params` (rilette da `resolve_params` a ogni giro), l'obiettivo in
     `omega_control.daily_goal`; coppie invertite -> `ValueError` (`resolve_params` le scambierebbe in silenzio).
     Accensione: `omega_control.status` `stopped` -> `running`, letto da `run_once`.
   * Safe calcio (tre voci del registro, un modulo): sostituzioni nei params GREZZI del control, nelle SEZIONI della
     Control Room (`esatto.minuteMin`, `exits.esatto_exit_minute`, `stake.laySize`...) con `varianti_bot.applica_annidato`
     (la sezione non si perde: `merge_params` del motore la fonde). Si variano su UNA variante accesa (`strategie`):
     "Applica bot" accende solo quella del bot scelto (`BotRegistrato.argomenti_applica`), come l'interruttore della
     Control Room; la certificazione continua ad accenderle tutte e tre (nessun cambio). Accensione: control
     `stopped` -> `running` (`run_once`).
   * Safe tennis: stesso schema (sezione `tennis`, `exits.tennis_*`).
   * Bot tennis (`replay_bot.py`, quattro voci): sostituzioni nella riga del bot (`params`, `stake`), la stessa che
     `_instantiate_bot` legge in produzione. Accensione: il `_Ponte` non passa book, punteggi ne' worker al bot prima
     di `dal_ms` (in produzione il bot NASCE all'armamento: prima non esiste).
2. **`parametri_modificabili(scenario)`** in ogni modulo (Safe: una per variante; tennis: una per bot). Default letti
   dalla STESSA fonte del servizio: Mike `config.PARAM_SPEC`+scenario, Omega `omega_config._SPEC/DEFAULTS`+scenario,
   Safe `bot_service.resolve_params` dei parametri dello scenario, tennis l'ISTANZA VERA del bot da
   `tennis_runner._instantiate_bot` con la riga dello scenario. Etichette = quelle delle schede di produzione
   (`mike.ts`, `tennis.ts`, Control Room). Fuori dal menu, con la causa scritta nel modulo: cadenze e cache, percorso
   d'esecuzione, ritentativi, parametri dichiarati SENZA EFFETTO, scelte del modello statistico, struttura della
   strategia (`strategy_version`, `engine`, `scores`, `variants`), blindature .it, `dry_run`.
3. **`ordini_specchio` nel referto di ogni bot**: `varianti_bot.SpecchioOrdini` (nuovo) si aggancia al `MotoreReplay`
   dopo OGNI book passato a flumine (giro del bot, attesa del bet delay, letture), legge gli ordini VERI del blotter e
   scrive una riga quando la firma cambia, con `LiveTradingStrategy._order_row` (la funzione di produzione dello
   specchio `betfair_live_orders`, la stessa di `porta_banco._specchio`) + `source` (valori del CHECK della migrazione
   `betfair_live_orders_source_bot_2026-09-26.sql`: mike, omega, safe, safe_tennis, tennis_*) + `_ms` (publish time).
   Esclusi: ordini piazzati dal banco per conto dell'utente (nota `utente`), righe con `status` None (colonna
   `NOT NULL`). Sola lettura: con parametri/dal_ms assenti i referti di certificazione sono identici (par. 3).
4. **Registro** (`registro_bot.py`): campo `parametri` per tutti gli 11 bot (lo scalper punta a
   `Betfair.stream.scalper.tools.replay_registrazioni:parametri_modificabili`, dell'altro delegato),
   `funzione_parametri()` con `ValueError` parlante se il modulo non la espone ancora, campo `argomenti_applica`
   (variante Safe).
5. **`applica_bot.esegui`** riscritto: tutti i bot; scenari = `elenco_scenari()` del registro filtrati da
   `SCENARI_APPLICABILI` (famiglia, modalita' prova/soldi veri simulati, etichetta) e `SCENARI_SCARTATI` (ogni scarto
   col motivo: guasto/trasporto, gesto dell'utente simulato, posizione iniettata, uguale a un altro, tetti di
   certificazione); uno scenario del registro non classificato NON si offre e il test lo nomina. Parametri validati
   prima di partire (e di nuovo nel replay); `dal_ms`, `clic_ms` passati SOLO se la funzione li dichiara nella firma
   (`inspect.signature`), altrimenti `ValueError`. Registrazione assente -> errore prima di partire. Tennis: cerca il
   GIORNO che contiene la partita sotto la radice del recorder. Esito in piu': `sport`, `modalita`,
   `parametri_usati` (serie + sostituzioni), `parametri_cambiati`, `dal_ms`, `accensione` (cosa vede il bot), `clic_ms`.
6. **Catalogo per la UI verificabile**: `python -m Betfair.stream.backtest.applica_bot --catalogo-ts >
   frontend/src/lib/replayBotCatalogo.ts` (GENERATO, 249 KB) + test di contratto che e' ROSSO se il file non e'
   allineato. Scelta motivata: il catalogo dipende solo dal codice (non dal DB), quindi un file versionato e un test
   bastano; la richiesta `catalogo_bot` al worker avrebbe legato la UI al banco acceso anche solo per vedere il menu.
   ATTENZIONE: dopo l'integrazione dell'altro delegato (scalper) il file va RIGENERATO (oggi porta, per lo scalper,
   `errore_parametri` e liste vuote): il test lo segnala.
7. **UI** (componenti riusabili, design system `components/ui/*`):
   * `frontend/src/lib/replayBot.ts`: tipi del catalogo (`CatalogoBot`, `ScenarioBot`, `VoceParametro`), `OpzioniApplica`,
     `payloadApplicaBot` (chiavi opzionali solo se usate: di serie il payload del 06/10), via `SCENARI_BOT` a mano.
   * `frontend/src/lib/applicaBot.ts` (regole pure), `frontend/src/lib/useApplicaBot.ts` (richiesta + rilettura 3 s +
     20 s «banco spento», estratti dal Match Replay).
   * `components/replay/ApplicaBotPanel.tsx`, `ParametriBotPanel.tsx`, `EsitoBotPanel.tsx` (nuovi), `MatchReplay.tsx`
     (solo il riquadro: `sport="calcio"`, minuto di gioco al cursore). `BotOrdersPanel.tsx` non toccato.

## 2. File toccati e nuovi

Modificati: `Betfair/stream/backtest/applica_bot.py`, `Betfair/stream/backtest/registro_bot.py`,
`Betfair/mike/tools/replay_registrazioni.py`, `Betfair/omega/tools/replay_registrazioni.py`,
`Betfair/safe_strategy/tools/replay_registrazioni.py`, `Betfair/safe_strategy/tools/replay_tennis.py`,
`Betfair/stream/tennis_live/tools/replay_bot.py`, `Betfair/stream/tests/test_applica_bot_2026_10_06.py` (2 casi che
asserivano la limitazione di ieri: Mike non applicabile, `SCENARI_VISIVI`), `frontend/src/lib/replayBot.ts`,
`frontend/src/pages/MatchReplay.tsx`.
Nuovi: `Betfair/stream/backtest/varianti_bot.py` (modulo comune: fuori dall'elenco esplicito del perimetro, motivato:
nessuna copia per bot), `Betfair/stream/tests/test_applica_bot_tutti_2026_10_07.py`,
`frontend/src/lib/replayBotCatalogo.ts` (generato), `frontend/src/lib/applicaBot.ts`, `frontend/src/lib/applicaBot.test.ts`,
`frontend/src/lib/useApplicaBot.ts`, `frontend/src/components/replay/ApplicaBotPanel.tsx`,
`frontend/src/components/replay/ApplicaBotPanel.test.tsx`, `frontend/src/components/replay/ParametriBotPanel.tsx`,
`frontend/src/components/replay/EsitoBotPanel.tsx`, questo referto.
NON toccati: `Betfair/stream/scalper/**`, `mediaUnder*`, `replayTimelineEvents.ts`, `TimelineSlider.tsx`, `certifica.py`,
`banco_comune.py`, `worker.py`, `TennisReplay*`. Nessuna migrazione (l'esito viaggia nel JSON gia' esistente).
`frontend/node_modules` = link simbolico al checkout principale (da togliere con `rm frontend/node_modules`, NON ricorsivo).

## 3. Prova prima/dopo (parametri e dal_ms assenti): referti IDENTICI

Metodo: «prima» = `git archive HEAD` (codice + dati di `value_engine` ecc.) in una cartella del scratchpad, «dopo» =
worktree; stesso comando `python -m Betfair.stream.backtest.certifica <bot> <evento> --data-dir ... --worker 1
--scenari <s>`, confronto `diff` tolte le sole righe dei tempi.

| bot | evento | scenario | esito | tempi prima/dopo |
|---|---|---|---|---|
| mike | 35797769 | base | IDENTICO | 141 s / 148 s |
| omega | 35797769 | apertura | IDENTICO | 104 s / 105 s |
| safe_base (3 varianti) | 35797769 | base | IDENTICO | 129 s / 129 s |
| tennis_flb, tennis_scalper, tennis_pro, tennis_swing, safe_tennis | 35790089 | base | IDENTICO (5 su 5) | 4-5 s |
| tennis_scalper, tennis_swing | 35790089 | gate-aperto | IDENTICO | 14/15 s, 8/7 s |

(Il primo «prima» era senza `value_engine/data/goal_time_cdf.json`: unica differenza la riga d'avviso del ripiego; rifatto
con i dati: identico. Lo dico perche' il primo confronto non era valido.) Dopo la correzione dell'accensione di Mike
(par. 1) il referto `mike base 35797769` e' stato rifatto: IDENTICO a HEAD. `omega apertura 35760084`: IDENTICO.

Prove di «Applica bot» (`applica_bot.esegui`, codice di produzione sul banco):

| prova | ordini | osservazione |
|---|---|---|
| mike base 35797769 | 2 | punta 10 @1,46 abbinata (18:00:00,890), banca 10,14 @1,44 PENDING -> EXECUTABLE -> abbinata |
| mike base, `stake` 4 | 2 | stesse quote, importi 4,00 / 4,06 |
| mike base, `dal_ms` 18:01:00,890 | 2 | PRIMA della correzione: punta a 18:00:00,890 (prima dell'accensione: DIFETTO); DOPO: punta a 18:01:03,069 |
| safe_esatto base 35797769 | 1 | banca 2,00 @32 a 20:27:59, abbinata |
| safe_esatto base, `dal_ms` 21:00 | 0 | acceso dopo l'unico ingresso: nessun ordine |
| safe_base base 35797769 | 0 | la sola variante BASE non entra |
| omega v4 / apertura 35760084, v4 35797769 | 0 | vedi par. 6 |
| tennis_scalper gate-aperto 35790089 | 71 (218 righe) | 0 violazioni |
| tennis_scalper gate-aperto, `stake` 4, `dal_ms` +30 min | 4 | primo ordine dopo l'accensione, importo 4,00 |
| tennis_swing / tennis_flb / tennis_pro gate-aperto | 24 / 6 / 5 | 0 violazioni |
| safe_tennis base / paper | 0 / 0 | come il referto di HEAD |

## 4. Test

Python (`python3 -m pytest <file> -q -p no:cacheprovider`):
* `Betfair/stream/tests/test_applica_bot_tutti_2026_10_07.py`: 132 verdi, 1 saltato (prova lunga di Mike, opt-in), **2 ROSSI attesi**:
  `test_ogni_bot_in_produzione_registra_il_catalogo_dei_parametri[scalper_calcio]` e
  `test_la_funzione_di_replay_accetta_parametri_e_dal_ms[scalper_calcio]` (lo scalper e' dell'altro delegato: verdi
  quando il suo `parametri_modificabili` e la sua firma con `parametri`/`dal_ms` sono integrati). Comprende due prove
  sulla registrazione tennis VERA (marcatore `cert`, saltate se assente).
* `test_applica_bot_2026_10_06.py` 9/9; registro, impronta, submin, sniper, mike, omega, safe, proposte, replay
  esploso: 329 verdi 1 saltato; strada unica, replay veloce, banco Mike ondata 2: verdi. Suite intera NON lanciata
  (la lancia il coordinatore).
Frontend (dalla cartella `frontend/`): `npx tsc -p tsconfig.app.json --noEmit` 0 errori; `npx vitest run
src/lib/applicaBot.test.ts src/components/replay/ApplicaBotPanel.test.tsx src/lib/replayBot.test.ts
src/lib/trainingLadder.replay.test.tsx` 30 verdi.

Falsificazioni (script `scratchpad/mut_py.py`, `mut_ts.py`: copia, mutazione, test, ripristino verificato byte per byte):
Python 24 mutazioni, 24 ROSSE (Mike acceso dopo il suo ingresso, prova lunga; specchio: solo primo stato, status None, senza source, ordini dell'utente inclusi [la
prima volta VERDE: il finto dell'utente non era vivo; test corretto, poi ROSSA]; valida senza dominio, chiavi ignote;
accensione sempre accesa; tennis senza cancello d'accensione, stake ignorato; Mike sostituzioni non scritte, coppie
non controllate, dal_ms non passato, default non dallo scenario; Omega obiettivo ignorato; Safe sezione appiattita;
Safe tennis control sempre running; applica senza parametri, senza variante Safe, scenario di guasto offerto; registro
Safe senza variante, bot senza catalogo; cartella tennis senza ricerca del giorno; file TS disallineato).
Frontend 11 mutazioni, 11 ROSSE (sport non filtrato, valori di serie mandati, massimo non controllato, payload con
parametri vuoti, accensione mai mandata, clic a tutti i bot, modalita' ignorata, «cambiato» mai evidenziato, errori che
non bloccano, intestazione senza etichette, minuto dal primo evento).

## 5. Parita' paper/live

Catalogo e parametri identici per «Prova» e «Soldi veri simulati» (stessa funzione, stessa famiglia di scenari; la
modalita' cambia SOLO lo scenario gemello del registro). Prova: `tennis_scalper` `soldi-veri` e `soldi-veri-paper`
danno le STESSE 71 righe d'ordine (`mode` 'live' / 'paper'); `tennis_flb` `live` e `gate-aperto` le stesse 6 righe
(`mode` 'live' / 'paper'). Lo specchio scrive il `mode` di esecuzione del bot nel replay.

## 6. Cosa NON ho fatto / NON ho potuto verificare

* Lo scalper calcio: parametri, `dal_ms`, `clic_ms` sono dell'altro delegato (file vietati); qui solo il riferimento nel
  registro e il passaggio condizionato alla firma. Il catalogo TS va rigenerato dopo l'integrazione.
* Omega: nessun ordine sulle due registrazioni calcio di questo ambiente con gli scenari applicabili (`v4`, `apertura`
  su 35797769 e 35760084): la cronologia di Omega e' provata dal test unitario dello specchio (ordini veri di flumine)
  e dall'identita' dei referti, NON da una partita con ordini Omega. Il 25/09 `omega apertura 35760084` piazzava 1
  ordine (`AUDIT_2026-09-25/strada_unica/rif_omega_apertura_coda_prima.txt`); oggi 0 ordini sia su HEAD sia nel mio
  worktree (referti identici): e' un cambiamento di condotta di Omega fra il 25/09 e oggi, NON indagato (fuori dal
  mio perimetro), lo segnalo.
* Safe: cronologia vista solo per la variante ESATTO (1 ordine); BASE e PUNTA senza ordini su 35797769. La Safe
  tennis non ha ordini sulla registrazione tennis disponibile (anche su HEAD).
* La prova lunga di Mike con `dal_ms` sta nella suite SOLO con `APPLICA_BOT_LUNGHI=1` (~3 min): nella suite di
  default si salta. Esito: VERDE in 146 s; con la mutazione «parametri del giro sempre quelli di sempre» (cioe' il
  codice prima della correzione) ROSSA in 177 s; file ripristinato byte per byte (`cmp`), 0 «MUTAZIONE».
* `clic_ms`: il controllo compare per BOT (firma della funzione di replay), non per scenario; per lo scalper il
  flag e' oggi `false` nel catalogo generato (la funzione dell'altro delegato non e' nel mio worktree): diventa
  `true` rigenerando il catalogo dopo l'integrazione.
* UI mai vista a schermo (nessuna app in questo ambiente); `npm run build` non fatto (lo fa il coordinatore ad app
  chiusa). Il pannello Parametri rende 41 voci per Mike: provato solo nei test di componente.
* `dal_ms` nei bot che girano col servizio (Mike, Omega, Safe): il servizio gira da INIZIO REGISTRAZIONE con il bot
  spento, cioe' come se l'app fosse stata aperta a quell'istante (in produzione il processo del servizio vive dall'avvio
  dell'app): eventi, catalogo, riferimento pre-partita congelato dallo scanner sono quelli che avrebbe. Tennis: il bot
  nasce all'armamento e riparte da zero (riscaldamento, finestre degli indicatori), come in produzione; la
  `process_new_market` (no-op nei quattro bot) e il costruttore restano all'inizio del replay.
* Lo stato «in volo» (PENDING) dei piazzamenti FOK di Mike/Omega/Safe non compare nella cronologia: la REST del banco
  ASPETTA il bet delay dentro la chiamata (come Betfair) e la prima riga e' gia' l'esito. Le banche appoggiate si
  vedono PENDING -> EXECUTABLE -> EXECUTION_COMPLETE.

## 6-bis. Integrazione con lo scalper dell'altro delegato (passi esatti)

1. Fondere prima lo scalper, poi questo lavoro (nessun file in comune: io non tocco `Betfair/stream/scalper/**`).
2. Perche' i 2 rossi [scalper_calcio] diventino verdi, la funzione del registro
   `Betfair.stream.scalper.tools.replay_registrazioni:certifica_scenario` deve accettare `parametri` e `dal_ms` per
   nome con default `None` (e, se vuole i clic, `clic_ms` con default `None`), e il modulo deve esporre
   `parametri_modificabili(scenario)`.
3. Le voci del catalogo dello scalper passano dal test `test_le_voci_del_catalogo_rispettano_il_contratto`: chiavi
   ESATTAMENTE nell'ordine `chiave, etichetta, tipo, default, min, max, passo, unita, gruppo, scelte` (piu' semplice:
   costruirle con `Betfair.stream.backtest.varianti_bot.voce`), `tipo` in int/float/bool/scelta, `gruppo` in
   Ingresso/Uscita/Importi/Tetti/Filtri/Tempi, etichetta ASCII, numeri con min <= default <= max e passo > 0, il
   default riaccettato da `varianti_bot.valida`.
4. Se l'altro delegato ha aggiunto scenari al `SCENARI_DESCRITTI` dello scalper,
   `test_ogni_scenario_del_registro_e_classificato[scalper_calcio]` diventa rosso e li NOMINA: vanno aggiunti in
   `applica_bot.SCENARI_APPLICABILI["scalper_calcio"]` (famiglia, modalita', nota) o in `SCENARI_SCARTATI` col motivo.
5. Rigenerare il catalogo: `python3 -m Betfair.stream.backtest.applica_bot --catalogo-ts >
   frontend/src/lib/replayBotCatalogo.ts` (dalla radice), poi `test_il_file_ts_del_catalogo_e_allineato_al_registro`
   verde e `npx tsc -p tsconfig.app.json --noEmit` 0 errori (il file e' tipizzato con `CatalogoBot`). Con `clic_ms`
   nella firma, `clic_ms: true` per lo scalper e il riquadro mostra «+ clic Attiva adesso al cursore».
6. `npm run build` ad app chiusa (nessuna migrazione).

## 7. Decisioni per l'utente

Nessuna decisione di strategia: nessuna soglia, stake, tetto o gamba di produzione e' cambiata. Da sapere: «di serie» e'
il valore di produzione CON SOPRA lo scenario (es. Omega `apertura` porta la quota di banca massima a 500).

## 8. Da controllare dal vivo al prossimo avvio dell'app

Match Replay -> vista Ladder di una partita registrata: riquadro «Applica bot» -> elenco con i 6 bot calcio (nessun bot
tennis), scenario, «Prova/Soldi veri simulati» solo dove esiste il gemello (Scalper maker, sniper, media under, Omega v2
banda 500), «Parametri» (tendina, gruppi Ingresso/Uscita/Importi/Tetti/Filtri, «di serie: ...» accanto a ogni campo,
«cambiato» sul campo variato, «Ripristina di serie»), casella «accendi il bot all'istante del cursore» con l'ora e il
minuto; Applica -> intestazione del risultato con bot, scenario, parametri cambiati, «acceso dalle ...».

## 9. API dei componenti per la pagina Replay Tennis (altro delegato)

```tsx
import { useApplicaBot } from '@/lib/useApplicaBot';
import { ApplicaBotPanel } from '@/components/replay/ApplicaBotPanel';
import { EsitoBotPanel } from '@/components/replay/EsitoBotPanel';
import { conOrdiniDelBot, ordiniBotAlMs } from '@/lib/replayBot';

const applica = useApplicaBot();            // { richiesta, esito, righe, inCorso, invia(eventId, bot, scenario, opzioni), azzera }
<ApplicaBotPanel
    sport="tennis"                           // 'calcio' | 'tennis': SOLO i bot di quello sport (dal catalogo generato)
    eventId={eventId}                        // partita registrata ('' = pulsante spento)
    cursoreMs={currentMs}                    // istante corrente della barra (ms, orologio dei frame = _ms del banco)
    applica={applica}
    etichettaIstante={ms => '...'}           // facoltativo: es. punteggio/set al cursore
    catalogo={...}                           // facoltativo (test): di serie CATALOGO_BOT
/>
{applica.esito && (
    <EsitoBotPanel esito={applica.esito} nowMs={currentMs}
        nomeMercato={mid => ...} nomeSelezione={(mid, sid) => ...} />
)}
// ladder in sola lettura: conOrdiniDelBot(api, mid => ordiniBotAlMs(applica.righe, currentMs, mid))
```
`ParametriBotPanel` (`voci`, `valori`, `onCambia(chiave, valore|undefined)`, `onRipristina`, `disabilitato?`,
`apertoDiSerie?`) e' usato dentro `ApplicaBotPanel`; si puo' usare da solo. Le partite tennis: `applica_bot.esegui`
cerca il giorno sotto la radice del recorder (`TENNIS_RECORD_DIR`), quindi basta l'`event_id`.
