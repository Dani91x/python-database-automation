# SCHEDA H - BANCO DI CERTIFICAZIONE E REPLAY

Componente: banco comune `Betfair/stream/backtest/` (punto d'ingresso `python -m Betfair.stream.backtest.certifica <bot> ...`), adattatori di replay per bot, controlli di condotta per bot, «Applica bot» e replay nella UI, worker.
Data: 08/10/2026. Autore: delegato Sonnet 5.5. Commit di partenza: `f26a490e` (HEAD); ultimo commit che ha toccato `banco_comune.py`: `b5547eb8` (regola «mercato che attraversa»).
Perimetro (righe con `wc -l` su file tracciati; strumento per i conteggi dei gemelli: `ARCHITETTURA_2026-10/strumenti/h_gemelli_adattatori.py` e `h_righe_omonime.py`, uscite `_output.txt` accanto):

| Gruppo | File | Righe |
|---|---|---:|
| Banco comune (nucleo e satelliti) | `banco_comune.py` 3.046, `trasporto_rapido.py` 1.778, `proposte_modello.py` 1.393, `certifica.py` 1.084, `chiusura_parziale.py` 994, `applica_bot.py` 892, `porta_banco.py` 834, `trasporto.py` 633, `uscite_manuali.py` 568, `varianti_bot.py` 461, `registro_bot.py` 440, `minimi_banco.py` 282, `__init__.py` 31 | 12.436 |
| Backtest Automatico (percorso diverso dal banco) | `run_backtest.py` 493, `sim_strategy.py` 360, `worker.py` 102 | 955 |
| Strumenti di misura del banco | `Betfair/stream/backtest/tools/misura_punto8/*.py` (12 file) | 3.640 |
| **Totale Python in `Betfair/stream/backtest/`** | `git ls-files` + `wc -l` (il totale 17.537 comprende anche 3 `.md` da 506 righe) | **17.031** |
| Adattatori di replay per bot (6 file) | `Betfair/mike/tools/replay_registrazioni.py` 2.370, `Betfair/omega/tools/replay_registrazioni.py` 2.593, `Betfair/safe_strategy/tools/replay_registrazioni.py` 2.092, `Betfair/safe_strategy/tools/replay_tennis.py` 1.577, `Betfair/stream/scalper/tools/replay_registrazioni.py` 3.803, `Betfair/stream/tennis_live/tools/replay_bot.py` 1.679 | 14.114 |
| Controlli di condotta per bot (7 file) | `mike/certificazione.py` 2.084, `omega/certificazione.py` 2.160, `safe_strategy/certificazione.py` 2.036, `safe_strategy/certificazione_k.py` 533, `safe_strategy/certificazione_tennis.py` 1.217, `stream/scalper/certificazione.py` 2.472, `stream/tennis_live/certificazione_bot.py` 1.189 | 11.691 |
| Test del banco (nome con banco/certifica/trasporto/replay/backtest + «test», `git ls-files Betfair`) | 92 file | 35.661 |
| Replay nella UI (frontend, nome con «replay», non test, non fixture, non snapshot) | `git ls-files frontend/src | grep -i replay`; di cui `replayBotCatalogo.ts` 11.099 GENERATO | 19.226 (8.127 scritti a mano) |
| Test frontend del replay | `*.test.*` con «replay» | 4.093 |
| Fixture frontend del replay (`__fixtures__`) | json di esiti | 20.411 |
| Replay tennis lato Python | `Betfair/stream/tennis_replay/{convertitore 523, importa 165, caricamento 112, __init__ 11}` | 811 |
| Strumenti di prova della barra | `frontend/scripts/verifica_barra_replay.ts` 159, `tools/replay_barra_fixture.py` 455 | 614 |

---------------------------------------------------------------------------------------------------

## 1. OGGI

### 1.1 Che cosa e' il banco (letto dal codice)

La testata di `banco_comune.py:1-60` dichiara la catena: raw registrato (stream NATIVO Betfair) -> `FlumineSimulation` + `HistoricalStream` -> `MarketBook` di betfairlightweight -> scanner VERO (`Scanner._apply_market_book`) -> `build_rows` -> riga in memoria -> feed vero del bot -> servizio vero (`_run_event`/`run_once`) -> ordini veri su flumine (matching con coda, FOK, bet delay). I punteggi arrivano dal sidecar (`.scores.jsonl` / `.score.jsonl`) e passano da `Scanner.apply_score_state` (`banco_comune.py:2758`, `carica_punteggi:2801`). L'orologio dello scanner e' il `publish_time` del tick (`:2604-2618`).

Il banco ha DUE strati con responsabilita' diverse:

1. **Il nucleo comune** (`banco_comune.py`, 3.046 righe): DB in memoria (`DbMemoria:248`), REST simulata con le stesse chiavi del vero (`MercatoFlumine:530`), motore di replay (`MotoreReplay:1968`), scanner di replay (`ScannerReplay:2525`), generatore dei libri (`GeneratoreLibri:1847`), simulazione di flumine con flag rimessi a posto (`simulazione_flumine:1758`).
2. **Un adattatore per bot** (6 file, 14.114 righe) che monta il servizio vero del bot sul nucleo e definisce scenari, guasti iniettati e note del referto; e **un modulo di controlli per bot** (7 file, 11.691 righe) che fa il referto. Il registro (`registro_bot.py:71-110` `BotRegistrato`; voci `:218-420`) lega nome -> funzione di replay -> controlli -> scenari -> catalogo parametri -> spec.

Bot registrati: 11 (`registro_bot.py`, `nome=`): `mike:219`, `omega:244`, `safe_base:256`, `safe_esatto:271`, `safe_punta:286`, `safe_tennis:301`, `scalper_calcio:314`, `tennis_scalper:348`, `tennis_pro:361`, `tennis_flb:374`, `tennis_swing:387`. Sei funzioni di replay distinte servono 11 bot (le tre Safe calcio condividono `Betfair.safe_strategy.tools.replay_registrazioni:certifica_scenario`; i 4 tennis hanno 4 wrapper `certifica_scenario_tennis_*` nello stesso `replay_bot.py`). Il registro dichiara anche i processi NON bot (`NON_BOT`, `:408-420`), fra cui `Betfair.stream.backtest.worker`.

### 1.2 Come il banco entra in flumine (punti di aggancio) e l'impronta della 2.13.11

Versioni installate misurate: flumine 2.13.11, betfairlightweight 2.23.2 (`.venv`, `requirements.txt:28-29`, pin «non negoziabile» `:24`), Python 3.13.3.

- **Costruzioni di `FlumineSimulation(...)` fuori dai test, nel perimetro del banco**: 9 (`git grep -n "FlumineSimulation("`): `banco_comune.py:3023`, `trasporto_rapido.py:172`, `mike/tools/replay_registrazioni.py:1501`, `omega/tools/replay_registrazioni.py:2066`, `safe_strategy/tools/replay_registrazioni.py:1568`, `stream/scalper/tools/replay_registrazioni.py:1789`, `stream/tennis_live/tools/replay_bot.py:1375`, `run_backtest.py:10` e `:405` (il Backtest Automatico, non il banco). Il piano del 02/10 ne contava ~44 in tutto il repo e 38 strategie (`PIANO_OTTIMIZZAZIONE_GLOBALE_2026-10-02.md:78`); il perimetro del banco e' quindi il sottoinsieme sopra.
- **Righe di `import flumine`/`from flumine` nel banco e negli adattatori** (`git grep` sui 6 `tools/` + `backtest/*.py`): **70 righe** in 14 file. `banco_comune.py` ne ha 18 (`:230, 231, 655, 656, 1254, 1255, 1492, 1529, 1578, 1618, 1649, 1678, 1736, 1767, 2149, 2150, 2460, 2936`), `trasporto_rapido.py` 5 (`:146, 1362-1365`), `scalper/tools/replay_registrazioni.py` 9, `tennis_live/tools/replay_bot.py` 4; il resto e' distribuito su `run_backtest.py`, `sim_strategy.py`, `chiusura_parziale.py`, `porta_banco.py`, `minimi_banco.py`, `certifica.py` e sui tre adattatori calcio.
- **API PRIVATE di flumine toccate** (conteggio righe, `grep -c` su `banco_comune.py`): `_piq` 4, `_update_matched` 3, `_process_simulated_orders` 5, `_process_close_market` 10, `SimulatedMiddleware` 8, `SimulatedDateTime` 6, `_orologio_banco` 1 (attributo che il banco aggiunge a `flumine.config`); fuori dal nucleo: `chiusura_parziale.py` 4, `trasporto.py` 2, un'occorrenza in ciascuno dei tre adattatori calcio, 4 in `omega/tools/misura_ingresso_passivo.py`. Totale righe in cui compaiono `_piq|_update_matched|_process_*` nel perimetro: 34 (`git grep -c`).
- **Copie di codice di flumine** (il rischio al cambio di versione): (a) `_chiudi_mercato_senza_resoconti` (`banco_comune.py:1655`) = `BaseFlumine._process_close_market` 2.13.11 (`baseflumine.py:353-414`) meno il blocco dei resoconti vuoti; **impronta** sha256 `43ee8df0...e57c` (`_IMPRONTA_CHIUSURA_FLUMINE:1642`) confrontata con quella della funzione installata (`_impronta_chiusura_flumine:1645`, controllo a `:1739`): se la funzione cambia, il banco usa la VERA senza toccare nulla (commento `:1640-1644`). (b) `GeneratoreLibri` (`:1847`) = `FlumineHistoricalGeneratorStream._read_loop` (`flumine/streams/historicalstream.py:259-275`) con una differenza sola (non ricostruisce i libri che non cambiano). (c) `minimi_banco.py` (`minimi_it_su_flumine`, patch di `SimulatedExecution`, import `:172`). (d) `MotoreReplay._mercato_che_attraversa` (`:2114-2213`): regola nuova che flumine 2.13.11 non ha.
- **Interruttori di modulo** (`banco_comune.py`): `EMISSIONE_VELOCE:1799`, `ATTESA_ESATTA:1805`, `CADENZA_DOPO_LE_CHIAMATE:1812`, `RIUSA_LIBRO_CHIUSO:1818`, `RIUSA_LAPSE:1824`, `ATTRAVERSAMENTO:1830`, `LATENZA_LETTURA_S = 0.120:1844` (ASSUNTA, non misurata: commento `:1832-1843`). Ognuno ha il test di equivalenza lenta/veloce (es. `test_banco_replay_veloce_2026_10_02.py:435`, `test_banco_identita_2026_09_16.py`).
- **Flumine 3** (piano del 02/10, `PIANO_OTTIMIZZAZIONE_GLOBALE_2026-10-02.md:78`): 2.13.11 -> 3.2.6 «blocco a se' DOPO monitoraggio e scanner»; cambia avvio (stream creati a mano), rinomina i parametri della simulazione, richiede betfairlightweight ==2.24.0, porta l'abbinamento passivo dinamico nel simulatore (cambia i numeri dei replay: «distinguere piu' realistico da regressione»). Costo dichiarato: ~44 costruzioni, 38 strategie, **33 punti** in cui il banco entra in flumine (uno verifica l'impronta). Il mio conteggio sul codice di oggi (70 righe di import, 34 righe di API privata, 9 costruzioni) e' compatibile con «33 punti» come numero di luoghi logici, ma non e' lo stesso conteggio e non l'ho riprodotto.

### 1.3 Quanti adattatori per bot e quanto codice gemello

Misure (strumenti `h_gemelli_adattatori.py` e `h_righe_omonime.py`; la somiglianza e' `difflib` sul testo senza commenti/docstring):

| Bot | File di replay | Righe | Controlli | Righe |
|---|---|---:|---|---:|
| Mike | `Betfair/mike/tools/replay_registrazioni.py` | 2.370 | `Betfair/mike/certificazione.py` | 2.084 |
| Omega | `Betfair/omega/tools/replay_registrazioni.py` | 2.593 | `Betfair/omega/certificazione.py` | 2.160 |
| Safe calcio (3 varianti) | `Betfair/safe_strategy/tools/replay_registrazioni.py` | 2.092 | `safe_strategy/certificazione.py` + `certificazione_k.py` | 2.036 + 533 |
| Safe tennis | `Betfair/safe_strategy/tools/replay_tennis.py` | 1.577 | `certificazione_tennis.py` | 1.217 |
| Scalper calcio | `Betfair/stream/scalper/tools/replay_registrazioni.py` | 3.803 | `stream/scalper/certificazione.py` | 2.472 |
| Tennis (4 bot) | `Betfair/stream/tennis_live/tools/replay_bot.py` | 1.679 | `tennis_live/certificazione_bot.py` | 1.189 |

Cioe' **6 adattatori per 11 bot registrati** e 7 moduli di controlli. Le funzioni con lo STESSO NOME in almeno 2 file sono: 21 nei file di replay, 93 nei file di controlli; in tutti e 6 i file di replay c'e' solo `certifica_scenario`; nei controlli `Referto`, `Violazione`, `_controllo`, `elenco_controlli`, `mai_sollecitati`, `verifica` (`h_gemelli_adattatori_output.txt`). Righe dentro funzioni/classi con nome omonimo (`h_righe_omonime_output.txt`): adattatori **5.402 su 14.114 (38,3 %)**, controlli **4.467 su 11.158 (40,0 %)** (il totale dei controlli qui esclude `certificazione_k.py`, 533 righe, che non ha omonimi per costruzione).

ATTENZIONE alla lettura: omonimo non vuol dire identico. I numeri che dicono quanto e' davvero gemello:

| Funzione (stesso ruolo) | Dove (`file:riga`) | Righe | Somiglianza |
|---|---|---:|---|
| `_crea_strategia` (ponte flumine + servizio vero) | `mike/tools/replay_registrazioni.py:485-1283` / `omega/tools/replay_registrazioni.py:1210-1760` / `safe_strategy/tools/replay_registrazioni.py:940-1377` | 799 / 551 / 438 (=1.788) | 0,12-0,18 |
| `_Ponte` | `scalper/tools/replay_registrazioni.py:2797-2924` / `tennis_live/tools/replay_bot.py:597-1083` | 128 / 487 (=615) | 0,04 |
| `_Ponte` del nucleo (usato da `replay_evento`) | `banco_comune.py:2954-3030` | 77 | - |
| `_certifica_evento` | mike `:1347-1889` / omega `:2004-2111` / safe `:1426-1622` | 543 / 108 / 197 (=848) | 0,17-0,43 |
| `certifica_scenario` | mike `:2280-2351`, omega `:2497-2577`, safe `:1994-2042`, safe_tennis `:1400-1411`, scalper `:3166-3400`, tennis `:1225-1517` | 72 / 81 / 49 / 12 / 235 / 293 (=742) | 0,02-0,35 |
| `_componi_note` | omega `:2114-2353` / safe `:1670-1841` | 240 / 172 | 0,10 |
| `parametri_modificabili` | mike `:2235-2246`, omega `:2438-2457`, safe_tennis `:633-647`, scalper `:460-493`, tennis `:1170-1191` | 12-34 | 0,10-0,40 |
| `_applica_parametri` | mike `:2249-2265`, omega `:2460-2480`, safe `:1958-1979`, safe_tennis `:650-666` | 17-22 | 0,11-0,55 |
| `nota_accensione`, `cadenza_ms`, `main`, `_riavvia_processo`, `qualita_registrazione`, `impronta`, `credenze_cp` | vedi `h_gemelli_adattatori_output.txt` | 4-105 ciascuna | 0,00-0,75 |
| `uscite_automatiche_scenario` | scalper `:709-713` / tennis `:128-132` | 5 | **1,00** |
| `_iso` | mike `:331-332` / safe `:1380-1381` | 2 | **1,00** |
| `certifica_evento` (wrapper) | mike `:1339-1344`, omega `:1997-2001`, safe `:1387-1391` | 5-6 | **1,00** fra i tre |
| `Referto` (classe) | mike `certificazione.py:2045-2084`, omega `:1845-1870`, safe_tennis `:1188-1217`, scalper `:1337-1367`, tennis `certificazione_bot.py:1162-1189` | 26-44 | 0,53-0,94 (scalper<->tennis 0,94; mike<->omega 0,93) |
| `Violazione` | mike `certificazione.py:44-57`, omega `:43-56`, scalper `:105-113`, tennis `:81-91` | 9-17 | 0,45-1,00 (scalper<->tennis 1,00) |
| `Osservazione` | safe_tennis `:74-129`, scalper `:117-179`, tennis `:95-167` | 56-73 | 0,12-0,39 |
| regole `_a1.._c1`, `_b1.._b14` | stesse etichette in file diversi | 4-34 | 0,05-0,25 (sono regole di strategie diverse, non copie) |

Somma dei blocchi «stesso ruolo, corpo di bot» negli adattatori (voci della tabella con righe misurate): `_crea_strategia` 1.788 + `_Ponte` 615 + `_certifica_evento` 848 + `certifica_evento` safe_tennis 105 + `certifica_scenario` 742 + `_componi_note` 412 + `parametri_modificabili` 103 + `_applica_parametri` 77 + `nota_accensione` 58 + `cadenza_ms` 35 + `main` 220 + `_riavvia_processo` 79 + `qualita_registrazione` 28 + `impronta` 50 + `credenze_cp` 92 + `uscite_automatiche_scenario` 10 + `_azzera_stato_di_processo` 13 + `cartella_predefinita` 14 = **5.289 righe (37,5 % di 14.114)**. Il codice davvero identico (somiglianza >= 0,9) e' invece piccolo: `Referto`/`Violazione` (alcune decine di righe per file), `uscite_automatiche_scenario`, `_iso`, i tre wrapper `certifica_evento`.

**Difetto strutturale principale (verificato)**: il «ponte» fra raw, flumine e servizio e' scritto una volta nel nucleo (`_replay_evento`, usato SOLO da `safe_tennis`: `replay_tennis.py:589`, e dagli strumenti `omega/tools/misura_ingresso_passivo.py:732,1648,2340`), e **riscritto per bot** in Mike, Omega, Safe calcio, scalper e tennis: ognuno costruisce da se' `ScannerReplay` (`mike:1406`, `omega:2035`, `safe:1473`), `FlumineSimulation(client=cliente_simulato())` (`mike:1501`, `omega:2066`, `safe:1568`), `MotoreReplay(quadro, su_book=...)` (`mike:1518`, `omega:2079`, `safe:1582`) e il proprio `MercatoFlumine(self)` (`mike:595`). La catena che il banco promette «identica per tutti i bot» e' quindi identica solo per costruzione dei suoi pezzi, non per il montaggio: oggi 5 montaggi distinti (calcio x3, scalper, tennis) + 1 nel nucleo + 1 nel trasporto rapido (`trasporto_rapido.py:146-176`).

### 1.4 Scenari per bot (elenco da `SCENARI_DESCRITTI`, `h_scenari_per_bot_output.txt`)

| Bot | Scenari | Dove |
|---|---:|---|
| mike | 26 (+5 sintetiche `tools/synth_mike.py`) | `mike/tools/replay_registrazioni.py:1899` |
| omega | 20 | `omega/tools/replay_registrazioni.py:1085` |
| safe_base / esatto / punta | 18 | `safe_strategy/tools/replay_registrazioni.py:211` |
| safe_tennis | 17 | `safe_strategy/tools/replay_tennis.py:352` |
| scalper_calcio | 20 nominali, 47 replay con le espansioni (`<UM.SCENARIO_MANUALI>`, `<UM.SCENARIO_FIRMATE>`, `<CP.SCENARIO>`, `<**espansione>`) | `scalper/tools/replay_registrazioni.py:767` |
| tennis (4 bot) | 17 | `tennis_live/tools/replay_bot.py:139` |

67 scenari distinti per nome; presenti in tutti i 6 adattatori: `base`, `bot-fermo`, `riavvio`, `rifiuti-betfair`, e `<CP.SCENARIO>` (= `chiusura-abbinata-in-parte`, definito UNA volta in `chiusura_parziale.py`, 994 righe, e riusato). Presenti in 5: `esiti-ignoti`; in 5: `feed-stantio` (assente nello scalper); altri condivisi: `cap-stretto` (mike, omega, safe), `cashout-globale` (mike, omega, safe), `paper` (omega, safe, safe_tennis, scalper), `<UM.*>` (scalper, tennis; `uscite_manuali.py`, 568 righe). Gli scenari del 08/10 del tennis (`gate-aperto`, `dry-run`, `parziali`, `live`, `chiudi-ora`, `soldi-veri*`) e dello scalper (`sniper*`, `media-under*`, `auto-live`, `kill-switch`, `senza-missione`) sono specifici.
Gli scenari applicabili dalla UI sono filtrati da `applica_bot.py:SCENARI_APPLICABILI:67` / `SCENARI_SCARTATI:155` (ogni scarto con il motivo): un TERZO elenco di scenari, oltre a `SCENARI_DESCRITTI` e a `TRASPORTO_OBBLIGATO`.

### 1.5 Tempi di oggi per bot contro l'obiettivo (`PROCESSO_STANDARD_BOT.md` §6.9: 300 s, tetto 600 s; `certifica.py:472-479`)

| Bot | Comando / registrazione | Tempo | Verdetto | Fonte |
|---|---|---:|---|---|
| Mike | `--scenari tutti`, 35760084, 26 replay | **728,4 s** | **oltre il tetto** | `AUDIT_2026-10-02/replay/mike_tutti_MASTER_FINALE.txt:753`; E1 5.2 |
| Omega | `--scenari tutti`, 35760084, 20 replay | 432,7 s (E2 dice 435-458) | sotto il tetto, sopra l'obiettivo | `AUDIT_2026-10-07/omega_apertura_35760084/replay/DOPO_35760084_tutti.txt:557` |
| Omega | `tutti` su 35797769 | 33 min (cantiere 11) | **oltre** | `SPECIFICHE_CANTIERI_CLOUD_2026-10-08.md` cantiere 11, tabella |
| Safe calcio | `tutti`, 22 partite | 254,1 s | dentro | `AUDIT_2026-10-04/replay/safe_base_tutti_PUNTE_MULTIPLE.txt:2254` |
| Safe tennis | `rapidi`, 35795993 | 8,5 s | dentro | E3 |
| Scalper calcio | `tutti`, 35797769, 47 replay | **6.916 s (115 min)** | **violato** | `AUDIT_2026-10-08/banco_attraversa/calcio_prima_tutti.txt`; E4 |
| Scalper calcio | 5 scenari col banco realistico | 370,7 s | oltre l'obiettivo | `calcio_dopo_5.txt:145` |
| Media under (scalper) | 18 scenari, 35797769 | **4.081,6 s (68 min)** | **violato** | `AUDIT_2026-10-07/replay/clic_35797769_r5.txt:505` |
| Media under | 18 scenari, 35760084 | 1.501,2 s | violato | `clic_35760084_r7.txt:488` |
| Tennis pro | `tutti`, 35790089, 17 replay | 18,9 s | dentro | `tennis_dopo.txt:284` |
| Tennis FLB | 6 replay, 35794049 | 15,7 s | dentro | `tennis_flb_35794049_TETTO.txt:122` |
| «Applica bot» | 1 scenario, 1 partita, dal worker | 258-314 s per richiesta | obiettivo cantiere 11: <= 30 s | cantiere 11, tabella |
| Strumento barra | 38 partite | 3,5 min | - | cantiere 11, tabella |

`certifica` stampa gia' i tempi per scenario e la riga `LENTO` (`certifica.py:501-523`, `PREFISSI_RIGHE_TEMPI:479`), e `righe_senza_tempi:525` produce il referto senza le righe dei tempi, che e' il termine del confronto prima/dopo.

### 1.6 Chi avvia il worker; log da 1,1 GB

- `worker.py` (102 righe) consuma `live_backtest_requests` UNA richiesta alla volta: `db.claim_backtest_request()` (`Betfair/stream/db.py:710`) -> `run_backtest(params)` oppure, se `params['tipo']=='applica_bot'`, `applica_bot.esegui(params)` (`worker.py:36-46`) -> `db.write_replay_bot_esito` (`db.py:747`) -> stato `DONE`/`ERROR` (`worker.py:41-58`). Poll di default 5 s (`DEFAULT_POLL_SEC`, `:22`).
- **Chi lo avvia**: il supervisore dell'app desktop, come 9o servizio sotto watchdog (`desktop/main.js:413-470`, riga `:469`; scheda I, I-011 e I-045). Non e' fra i processi attesi (`main.js:279-282`). Se muore a meta' di una richiesta, la riga resta `RUNNING` (scheda I, tabella servizi, riga `backtest-worker`: «nessun codice di recupero in `worker.py:1-102`»).
- **Log**: `_logs/` 1.428,1 MB in 197 file (01/10-08/10); `backtest-worker` 1.138,1 MB = 80 % (scheda I §1.7; `07_MISURE_OGGI.md §5.2`). Causa: `worker.py:87-90` `logging.basicConfig(level=INFO)` + flumine che registra a INFO ogni rimozione di mercato (`.venv/.../flumine/baseflumine.py:230`); il file piu' grande 475.688.289 byte, 4.117.457 righe in 78 min (scheda I §1.7). A riposo il worker interroga la coda ogni ~5,1 s, ~16.900 richieste/giorno al cloud (scheda I, difetto D8).

### 1.7 Replay nella UI (letto dal frontend)

- **Match Replay** `frontend/src/pages/MatchReplay.tsx` 1.280 righe; **Replay Tennis** `pages/TennisReplay.tsx` 811. Componenti `components/replay/`: `ApplicaBotPanel.tsx` 295, `EsitoBotPanel.tsx` 113, `ParametriBotPanel.tsx` 184, `RegistroOperazioniBot.tsx` 238, `TimelineSlider.tsx` 196, `LadderBacktestPanel.tsx` 199, `OpportunitaPanel.tsx` 275, `TradesPanel.tsx` 139, `MarketPanel.tsx` 147.
- Librerie: `lib/replayBot.ts` 299 (RPC `request_backtest` `:228`, `get_replay_bot_esito` `:236`), `replayOperazioni.ts` 978, `replayVerificaBarra.ts` 556, `replayVerificaBarraCalcio.ts` 352, `tennisReplay.ts` 504, `tennisReplayVerificaBarra.ts` 198, `replay-pnl.ts` 241, `replayTimelineEvents.ts` 282, `replayVerificaBarraDb.ts` 154.
- **`frontend/src/lib/replayBotCatalogo.ts` (11.099 righe, GENERATO)**: la testata (righe 1-9) dice «FILE GENERATO - NON MODIFICARE A MANO», origine `Betfair/stream/backtest/applica_bot.py`; si rigenera con `python -m Betfair.stream.backtest.applica_bot --catalogo-ts > frontend/src/lib/replayBotCatalogo.ts` (`applica_bot.py:365 catalogo_ts`, CLI `:875-892`); il test `Betfair/stream/tests/test_applica_bot_tutti_2026_10_07.py` e' rosso se non e' allineato. Contiene, per ogni bot, scenari x parametri con i default (la crescita a 11.099 righe viene dall'espansione scenario x parametro).
- **Replay professionale**: gli «esiti» di riferimento sono i json `frontend/src/lib/__fixtures__/replay_pro/esito_*.json` (9 file; da `esito_tennis_scalper.json` 6.702 righe a `esito_omega_apertura_84.json` 603) e il test `Betfair/stream/tests/test_replay_professionale_2026_10_07.py` (174 righe); schermate in `AUDIT_2026-10-07/replay_pro/`.
- **Strumento della barra**: `frontend/scripts/verifica_barra_replay.ts` (159 righe; `npx vite-node scripts/verifica_barra_replay.ts`, sola lettura, RPC `list_replays`, `get_replay_meta`, `get_replay_frames` a finestre) + verificatori `replayVerificaBarra*.ts`; fixture senza DB: `tools/replay_barra_fixture.py` (455). Referto: `AUDIT_2026-10-07/certificazione_db/verifica_barra_tutte.txt`. Il cantiere 13 (`SPECIFICHE_CANTIERI...:292`) riporta 13 partite su 38 con incoerenze.
- **DB**: tabella `replay_bot_esiti` (`migrations/replay_applica_bot_2026-10-06.sql`, 47 righe), coda `live_backtest_requests` (`migrations/live_backtest.sql`, `live_backtest_rpc.sql`), RPC replay (`live_stream_rpc_get_replay_perf.sql` 141), replay tennis (`replay_tennis_2026-10-07.sql` 387, `replay_tennis_mercati_elenco_2026-10-08.sql` 79). Caricamento tennis: `Betfair/stream/tennis_replay/{convertitore,importa,caricamento}.py` (`importa` «SI LANCIA A MANO», `caricamento` idempotente).
- **Backtest Automatico** (diverso dal banco): `run_backtest.py` (493) + `sim_strategy.py` (360, `SimStrategy` con modalita' `engine`, richiama `Betfair.stream.engine.live_engine_pro.evaluate_event`) esegue una strategia di MOTORE, non il codice dei bot di produzione; e' raggiunto da `worker.py:47` per le richieste senza `tipo=applica_bot`. Non passa dal registro dei bot.

### 1.8 Tabelle del DB, canali, processi, orologi

- Tabelle lette/scritte dal banco in produzione: solo la coda `live_backtest_requests` (claim e stato: `db.py:710-745`), `live_backtest_results` (`write_backtest_results`) e `replay_bot_esiti` (`db.py:747`). `certifica` da riga di comando NON tocca il DB: usa `DbMemoria` (`banco_comune.py:248`) con colonne e CHECK veri (§6.5), e dichiara i suoi limiti.
- Processi: `certifica` apre un processo per coppia evento x scenario, mai oltre `core_fisici-1` (`certifica.py:576 quanti_processi`, `:616 _esegui_compiti`, `--worker`, default 3 su 4 core); `_prepara_figlio:551` azzera le cache di processo da un ELENCO esplicito (catalogo §7 n. 37).
- Orologi: l'orologio del banco e' il `publish_time` (`imposta_ora:2607`); `orologio_monotono:1558` e' lo stato monotono di `SimulatedDateTime`; la latenza di lettura REST e' assunta a 0,120 s (`LATENZA_LETTURA_S:1844`).
- Nessuna chiamata di rete nel percorso del banco (il catalogo dei mercati e' ricostruito dal raw: limite 1 della testata `banco_comune.py:46-60`).

---------------------------------------------------------------------------------------------------

## 2. FUNZIONALITA' (H-001 ... )

Legenda: [UI] visibile nell'interfaccia; [P] parametro editabile (da riga di comando o dalla UI).

### 2.1 Nucleo `banco_comune.py`
- **H-001** `DbMemoria` (`:248-404`): DB in memoria con l'interfaccia del DB vero (control, events, trades, log, richieste, aggregati); `ht_ft_rows:345`, `proprietari_bet:375`; `__getattr__:390` fa fallire a voce alta un metodo non previsto (impedisce il «finto muto»).
- **H-002** Vista del libro come in produzione (`_Livello:406`, `_VistaEx:430`, `_VistaRunner:464`, `_VistaBook:477`, `libro_di_produzione:508`): stessi attributi del libro che legge il bot; `traded_volume` convertito solo se letto.
- **H-003** `MercatoFlumine` (`:530`): REST simulata. `place_order_live:651` (esito vero da oggetti flumine, bet delay), `_attendi_betfair:790`, `cancel_order_live:833`, `place_submin_live:932`, `rifiuto_provocato:622`, `list_current_orders:1024`, `order_state_by_bet_id:1032`, `list_account_cleared_bets:1090`, `list_account_cleared_markets:1145`, `list_account_orders:1176`, `posizione_di_conto:1186`, `ordini_conto_come_stream:1203`, `place_order_utente:1244`, `fills:1279`, `riepilogo_fill:1298`, `fill_attraversati:1311`, `pnl:1322`, `registra_libro_chiuso:1355`, `pnl_betfair:1421`, `read_book:1452`. Per l'utente: il bot vede gli stessi esiti che avrebbe su Betfair.
- **H-004** Cliente e middleware simulati (`assicura_middleware_simulato:1471`, `cliente_simulato:1514`): tetti di flumine aperti (si certificano i limiti del bot).
- **H-005** Orologio monotono e log di flumine silenziato (`orologio_monotono:1558`, `info_flumine_solo_se_loggata:1599`).
- **H-006** Chiusura del mercato senza i resoconti muti, con impronta (`:1642-1760`).
- **H-007** `simulazione_flumine` (`:1758`): accende `flumine.config.simulated`, sovrappone minimi .it (`minimi_banco.py`), chiusura veloce, e RIMETTE i flag (evita il contagio fra test).
- **H-008** `GeneratoreLibri` (`:1847`, `lento:1904`, `veloce:1908`): stessi book senza ricostruire quelli che non cambiano (replay veloce §6.9).
- **H-009** `MotoreReplay` (`:1968`): pompa i book, `_a_flumine:2055`, **mercato che attraversa** `_mercato_che_attraversa:2114` (commit `b5547eb8`, interruttore `ATTRAVERSAMENTO`), LAPSE al fischio `:2215` e alla sospensione `:2238`, `_uccidi_appoggiati:2294`, `attendi_esecuzione:2328` (attesa esatta del bet delay), `consuma_tempo:2407`, `avanza_un_book:2432`, `esegui:2459`.
- **H-010** `ScannerReplay` (`:2525`): scanner vero con orologio = `publish_time`, `registra_mercato:2636`, `applica_book:2706`, `applica_punteggio:2758`, `pubblica:2764`, `dichiara_buco_flusso:2587`/`nel_buco:2596` (flusso interrotto dichiarato), `dichiara_nomi:2622`.
- **H-011** Sidecar dei punteggi (`carica_punteggi:2801`, `nomi_dal_punteggio:2850`) con il ritardo gia' nel dato (testata `:14-31`; `ritardo_punteggi_s` solo per modellare un ritardo in piu').
- **H-012** `replay_evento`/`_replay_evento` (`:2910-3046`): ponte generico (cadenza `ogni_ms`, `strategia_extra`, `su_strategia`, `nomi_extra`, `db`, `veloce`), tetti flumine aperti `:3010-3016`.
- **H-013** Sette interruttori di modulo (`:1799-1844`) con la loro equivalenza testata.
- **H-014** `EsitoReplay` (`:2864`) e `nota_fill_attraversati` (`:2890`): numeri del replay (tick, giri, righe scritte, book in ritardo, lapse, fill attraversati, `senza_futuro`).

### 2.2 Satelliti comuni
- **H-015** `porta_banco.py` (834): la porta ordini del banco passa dal `MotoreOrdini` VERO del runner (`_dispatch`), strada unica del 24/09.
- **H-016** `trasporto.py` (633): trasporto «coda» o «canale» + `confronta` (parita' delle tracce); `trasporto_rapido.py` (1.778): profilo «di minuti» (`--scenari rapidi`, `main_rapidi`, banco rapido `BancoRapido:~172`), 14-18 scenari di trasporto e parita' coda/canale (`--trasporto entrambi`).
- **H-017** `chiusura_parziale.py` (994): scenario `chiusura-abbinata-in-parte` e controlli CP1-CP4 comuni a tutti i bot; avvolge `_update_matched` con un tetto (`:441` usa `OrderPackageType`).
- **H-018** `uscite_manuali.py` (568): scenari a uscite manuali/firmate per i bot di flusso (tennis x4, scalper), controlli UM1-UM4 e UF1-UF3.
- **H-019** `proposte_modello.py` (1.393): proposte di opportunita', anomalie e combo di Safe sul banco (cancello C6).
- **H-020** `minimi_banco.py` (282): rifiuto sotto il minimo come Betfair .it (back 2,00 / lay 0,50, place-and-trim).
- **H-021** `varianti_bot.py` (461): catalogo dei parametri modificabili senza cambiare la strategia (`voce:49`, `valida:121`, `applica_annidato:149`), `Accensione:178` (istante di accensione), `SpecchioOrdini:329` (righe `betfair_live_orders` dagli ordini VERI di flumine, `aggancia:406`, `chiudi:420`), `campi_ordine:249`.
- **H-022** `registro_bot.py` (440): registro dei bot e dei processi non bot; `elenco:422`, `bot:426`, `senza_certificazione:437`; `trasporto_obbligato:140`; `funzione_parametri:125` (ValueError, mai un catalogo inventato).

### 2.3 `certifica.py` (punto d'ingresso unico)
- **H-023** CLI (`main:711`): `bot`, `eventi`, `--elenco`, `--data-dir`, `--ogni-ms` (0 = cadenza del servizio), `--complete`, `--json`, `--scenari` (elenco, `tutti`, `rapidi`), `--diff N`, `--worker`, `--trasporto coda|canale|entrambi`, `--tracce`, `--diario` [P].
- **H-024** Verdetti delle registrazioni COMPLETE/PARTIAL/NO_RAW (`verdetti_registrazioni:194`, `eventi_disponibili:179`).
- **H-025** Impronta di versioni e codice del bot (`impronta:223`: flumine, betfairlightweight, sha1 dei moduli di produzione + controlli; «codice bot <hash> (N file)»).
- **H-026** Isolamento fra scenari (`_prepara_figlio:551`, `_lavora:393`, `_lavora_cronometrato:446`) e parallelismo (`quanti_processi:576`, `_esegui_compiti:616`); freni disattivati (`_freni_da_banco:270`, `cartella_arresto_del_banco:329`, ambiente dichiarato `descrivi_ambiente:385`).
- **H-027** Esito del banco (`esito_del_banco:59`), segno del referto (`segno_referto:113`), diagnosi di esplosione (`:123`, `segna_esplosione:165`, `segna_sotto_minimo:137`).
- **H-028** Tempi e tetto (`tetto_certificazione_s:482`, `riga_tempo_scenario:501`, `righe_finali_tempi:508` con `LENTO`, `picco_memoria_mb:532`, `CERTIFICA_TETTO_S`).
- **H-029** Parita' coda/canale (`_stampa_parita:675`) e elenco dei bot (`_stampa_elenco:655`).
- **H-030** Rifiuto esplicito di un bot senza replay o senza controlli (`certifica.py:~744-760`, messaggi «NON HA ANCORA UN REPLAY SUL BANCO» e «NON HA CONTROLLI DI CONDOTTA»).

### 2.4 `applica_bot.py` e UI [UI]
- **H-031** `esegui` (`:754`): fa girare un bot sulla registrazione con il codice di produzione, parametri e `dal_ms` (accensione) scelti dall'utente; ne esce la cronologia degli ordini [UI: ApplicaBotPanel, EsitoBotPanel] [P].
- **H-032** Catalogo scenari per la UI (`scenari_del_bot:282`, `catalogo_del_bot:319`, `catalogo:358`, `non_classificati:303`), generazione TS (`catalogo_ts:365`) [UI: ParametriBotPanel].
- **H-033** Cartelle delle partite (`cartella_della_partita:391`, tennis `risolvi_cartella_tennis:466` che cerca il Match Odds in tutte le cartelle, `tipi_mercato_del_raw:436`).
- **H-034** Conto della cronologia (`conto_regolato:602`, `conto_flumine:641`, `conto_dichiarato:669`, `cicli_dichiarati:703`, `clic_dichiarati:725`, `conferme:734`, `esiti_dal_raw:541`) [UI: RegistroOperazioniBot, P&L].
- **H-035** `clic_ms` («Attiva adesso» della media under, solo per i bot che lo dichiarano) [UI] [P].
- **H-036** Coda e stato della richiesta: `request_backtest` -> `live_backtest_requests` -> worker -> `replay_bot_esiti` -> `get_replay_bot_esito` (`replayBot.ts:228-236`) [UI].
- **H-037** Pagine Match Replay e Replay Tennis [UI]: timeline, ladder, mercati, trade, opportunita', registro operazioni, P&L (`pages/MatchReplay.tsx`, `pages/TennisReplay.tsx`, `components/replay/*`).
- **H-038** Verifica della coerenza barra/simboli/tabellone per tutte le partite (`verifica_barra_replay.ts`, `replayVerificaBarra*.ts`) [strumento da riga di comando].
- **H-039** Caricamento delle registrazioni tennis su Supabase (`tennis_replay/importa.py`, `caricamento.py`, `convertitore.py`).

### 2.5 Adattatori e controlli per bot
- **H-040** Un adattatore per bot con firma `certifica_scenario(event_id, *, data_dir, scenario='base', ogni_ms, campioni_diff) -> Referto` (contratto del banco, `MODELLO_BOT_NUOVO.md:33`): 6 file / 11 bot (par. 1.3).
- **H-041** Dizionario degli scenari per bot `SCENARI_DESCRITTI` (par. 1.4) [UI: elenco scenari].
- **H-042** Guasti iniettati (esiti ignoti, rifiuti Betfair, feed stantio, riavvio a meta', chiusura abbinata in parte, prezzo migliore, mercato annullato, timeout dopo l'accettazione...) senza cambiare mai partita, prezzi o strategia (`PROCESSO_STANDARD_BOT.md` §6.7).
- **H-043** Catalogo dei parametri modificabili per bot (`parametri_modificabili` x 5 funzioni + 3 varianti Safe `parametri_modificabili_base/esatto/punta`) [P].
- **H-044** Controlli di condotta per bot (49 attivi su Mike, 52 su Omega, 66 su Safe, 22 su scalper e tennis pro, 19 su tennis FLB secondo le schede E1-E5): famiglie K (consapevolezza dell'ordine, catalogo §7 n. 36), J, S, CP, UM/UF, B, R, P, A.
- **H-045** Referto: partite con qualita', tick, decisioni, azioni, violazioni per codice, copertura (`MAI SOLLECITATI: N su M`), stati e fasi visti/non visti, tempi, note di regolamento (P&L del banco con commissione).
- **H-046** Scenario di certificazione con un solo comando, referto riproducibile (impronta + versioni) e confronto senza tempi (`righe_senza_tempi:525`).
- **H-047** Il banco gira nella suite (`pytest -m cert`, §6.8) e i test di contratto rifiutano un bot in produzione non registrato (`test_registro_bot_2026_09_16.py`, 187 righe).

---------------------------------------------------------------------------------------------------

## 3. DIFETTI STRUTTURALI

1. **Il ponte e' copiato per bot** (par. 1.3): `_crea_strategia` x3 = 1.788 righe + `_Ponte` scalper/tennis = 615 righe + `_Ponte` del nucleo 77; somiglianza fra le copie 0,04-0,18 (non sono copie letterali: sono la stessa responsabilita' scritta sei volte in modi diversi). Costo: ogni correzione del banco (es. il commit `b5547eb8` ha toccato `banco_comune.py`, `varianti_bot.py` e due adattatori: `scalper/tools/replay_registrazioni.py` +4, `tennis_live/tools/replay_bot.py` +2) va portata a mano nei file dei bot; un adattatore che dimentica l'aggancio e' un bot certificato su un banco diverso.
2. **Tre elenchi di scenari per lo stesso bot**: `SCENARI_DESCRITTI` (adattatore), `TRASPORTO_OBBLIGATO` (`registro_bot.py:trasporti_scenari`), `SCENARI_APPLICABILI`/`SCENARI_SCARTATI` (`applica_bot.py:67,155`). Il test di contratto li tiene allineati; non e' una fonte unica.
3. **Il banco e' lento dove i bot sono ricchi**: Mike 728,4 s, scalper 6.916 s (47 replay), media under 4.081,6 s, Omega su 35797769 33 min (tabella par. 1.5). Violano §6.9 quattro bot su undici (Mike, scalper, media under, Omega sulla seconda registrazione). Il profilo del punto caldo non e' stato misurato qui (cantiere 11 passo 1).
4. **Il banco dipende da API PRIVATE di flumine e da copie di sue funzioni** (par. 1.2): una sola impronta (`:1642`) protegge una delle 4 copie; le altre (generatore, minimi, attraversamento) non hanno impronta. `_piq` e `_update_matched` sono interni di flumine usati in 7 righe del nucleo.
5. **Parita' mai sollecitata** (par. 5): Mike 6 controlli su 49 e 7 stati su 21 mai visti con UNA sola registrazione COMPLETE; Omega 38 su 52 (tutti, `DOPO_35760084_tutti.txt:518`) e 48 su 52 (solo `base`); Safe 25 su 66 (`safe_base_tutti_PUNTE_MULTIPLE.txt:2228`); scalper 2 su 22; tennis pro 3 su 22. «Zero violazioni» su questi vale «non lo so».
6. **Il finto di Omega con firma diversa dal vero** (E2 difetto 5): `DbMemoriaOmega.aggregates(self, day_start=None)` e `aggregates_coppia(self, day_start=None)` (`omega/tools/replay_registrazioni.py:609,615`) non accettano `mode`, mentre `omega_db.aggregates(day_start=None, mode=None)` (`omega/db.py:777,787`): catalogo §7 n. 27 e n. 21; correggerlo cambia i referti di Omega, quindi va fatto dal banco con referto prima/dopo (E2 §6). Il resto dei finti del banco ha `__getattr__` che fallisce a voce alta (`banco_comune.py:390`).
7. **Il riferimento dello scalper e' in revisione**: con `ATTRAVERSAMENTO` il `base` passa da 44 a 18 azioni, `chiusura-abbinata-in-parte` e' KO (B2, CP4) (`calcio_dopo_5.txt`; cantiere 15). La cartella dei nuovi riferimenti `AUDIT_2026-10-08/riferimenti/` NON esiste ancora (`ls`, 08/10). Nessuna parita' di E4 si firma prima.
8. **Il Backtest Automatico e' un secondo percorso flumine** (`run_backtest.py:405`, `sim_strategy.py:100`) che non passa dal registro dei bot: 853 righe, un secondo punto di aggancio alla libreria.
9. **Worker h24 con log da 1,1 GB e senza recupero** (par. 1.6): `RUNNING` orfano se muore a meta', `INFO` di flumine a ogni mercato rimosso, 16.900 SELECT/giorno a vuoto.
10. **Catalogo TS generato da 11.099 righe nel repo** (`replayBotCatalogo.ts`): cresce con scenari x parametri; e' un artefatto, non codice, ma sta nei diff e nei conteggi (e' il 58 % delle 19.226 righe di frontend con «replay» nel nome: 11.099 / 19.226).
11. **Numeri confrontabili solo a parita' di comando**: `base` Mike 52.082 tick (coda) contro 56.146 (canale) (E1 5.2); `--worker`, `--trasporto`, `--ogni-ms` e la versione del banco cambiano i numeri. Oggi il comando esatto sta nel referto in forma di testo, non in un manifesto verificabile.
12. **Il tempo di mercato delle chiamate di lettura e' ASSUNTO** (120 ms, `:1844`): ogni referto lo eredita; non e' una misura nostra.

---------------------------------------------------------------------------------------------------

## 4. DOMANI

### 4.1 Struttura
Il percorso `Betfair.stream.backtest.certifica` e `applica_bot` restano IDENTICI per l'utente (stessi comandi, stessi flag; si aggiungono solo `--ombra`, `--congela`, `--verifica-congelati`). Dentro:

```
Betfair/stream/backtest/            (stessa cartella: nessun comando cambia)
  nucleo/                          banco_comune.py spezzato per responsabilita' (stessi simboli riesportati)
     mercato.py   DbMemoria, MercatoFlumine
     motore.py    MotoreReplay, GeneratoreLibri, regole di lapse e attraversamento
     scanner.py   ScannerReplay, carica_punteggi
     porta_flumine.py   UNICO modulo che importa flumine (ogni API privata, ogni copia con la sua impronta)
  adattatore.py                    UN adattatore sul contratto D (Plugin: Decisore | OspiteFlumine)
  ombra.py  cassetta.py  congela.py   (parita' automatica: par. 4.3-4.4)
  COSA_FA.md
bots/<nome>/banco.py               solo scenari, guasti specifici, note del referto (~30 righe per bot)
```
`certifica.py`, `registro_bot.py`, `applica_bot.py`, `varianti_bot.py`, `porta_banco.py`, `trasporto*.py`, `chiusura_parziale.py`, `uscite_manuali.py`, `minimi_banco.py` non cambiano di funzione.

### 4.2 Contratto: UN adattatore unico sul contratto D
Si appoggia a `Plugin`/`Decisore`/`OspiteFlumine` di `D_RUNTIME_BOT_CONTRATTO.md §4.2` (`Orologio`, `Libro`, `Quadro`, `Parametri`, `Intento`, `Esito`, `Cadenza`). Il banco aggiunge SOLO il lato scenario:

```python
from dataclasses import dataclass, field
from typing import Literal, Mapping, Protocol, Sequence, Any

Guasto = Literal["esiti_ignoti", "rifiuto_betfair", "feed_stantio", "riavvio", "chiusura_parziale",
                 "prezzo_migliore", "mercato_annullato", "sospensione_lunga", "timeout_dopo_accettazione"]

@dataclass(frozen=True)
class Scenario:                                   # sostituisce SCENARI_DESCRITTI + TRASPORTO_OBBLIGATO + SCENARI_APPLICABILI/SCARTATI
    nome: str; descrizione: str
    parametri: Mapping[str, Any] = field(default_factory=dict)   # solo chiavi del catalogo del Plugin
    guasti: Sequence[Guasto] = ()
    trasporto: Literal["coda", "canale"] | None = None
    in_ui: bool = True; motivo_non_in_ui: str = ""               # ogni scarto col motivo, come oggi

class BancoDelBot(Protocol):
    plugin: "Plugin"                              # il bot (contratto D), invariato
    def scenari(self) -> Sequence[Scenario]: ...
    def controlli(self) -> "ModuloControlli": ...
    def sport(self) -> Literal["calcio", "tennis"]: ...
    def spec(self) -> str: ...                    # percorso della Costituzione/spec

def certifica_scenario(banco: BancoDelBot, event_id: str, *, data_dir: str, scenario: str,
                       ogni_ms: int = 0, cassetta: "Path | None" = None) -> "Referto": ...
```
`Decisore` e `OspiteFlumine` si montano nello STESSO ponte (`adattatore.py`): per `Decisore` il ponte chiama `osserva` alla `Cadenza` del plugin sul tempo di mercato (stessa regola di oggi, `CADENZA_DOPO_LE_CHIAMATE`); per `OspiteFlumine` aggiunge le strategie flumine esistenti al `FlumineSimulation`. Il registro (`registro_bot.py`) deriva da `BancoDelBot`; `catalogo_ts` si deriva dal Plugin (decisione 3).

### 4.3 La modalita' «OMBRA»: stesso input, confronto automatico
Obiettivo: provare che il componente NUOVO (dietro il contratto D) fa esattamente cio' che faceva il VECCHIO sulle stesse registrazioni, con tolleranze ZERO salvo quelle dichiarate.

**Principio**: il banco registra, durante UN replay, una **cassetta** (registro append-only, JSON Lines canonico: chiavi ordinate, nessuna conversione dei float, un record per riga) e `ombra.confronta` confronta due cassette. Il vecchio non va riesumato ad ogni confronto: la cassetta del vecchio si PRODUCE UNA VOLTA PRIMA di toccare il codice e si congela (par. 4.4). Il confronto e' quindi `nuovo (oggi) contro baseline (congelata)`, a costo di un solo replay.

Livelli di confronto (ognuno e' un `kind` della cassetta, agganciato nel banco, non nei bot, cosi' vecchio e nuovo sono osservati dallo stesso occhio):
1. **Decisioni** (`kind='decisione'`): per ogni giro del servizio: `(event_id, publish_ms, indice_giro)`, esito per condizione (`id`, `ok`, `signal/no/nd`), `signal_key`, motivo di non apertura, stato e fase della macchina a stati. Aggancio: dentro `_Ponte._giro` di `_replay_evento` (`banco_comune.py:2954-3030`, chiamata a `servizio(...)`) e nell'equivalente unico del ponte.
2. **Intenti/ordini** (`kind='ordine'`): ogni `place/cancel/replace/close` con istante `ms` (publish time), `market_id`, `selection_id`, `side`, prezzo, importo, `strategy`, `mode`, `ref`. Aggancio: `MercatoFlumine.place_order_live:651`, `cancel_order_live:833`, `place_submin_live:932` (le stesse funzioni che oggi producono `fills()`), e `SpecchioOrdini._riga:359` (righe `betfair_live_orders` per ogni cambio di stato).
3. **Fill ed economia** (`kind='fill'`, `kind='conto'`): `[publish_time_ms, prezzo, size]` di `SimulatedOrder._update_matched` (stessa forma di `H-009`), voce `fill_attraversati`, P&L lordo/netto e commissione (`pnl_betfair:1421`), esposizione e liability sull'abbinato.
4. **Persistenza** (`kind='riga_db'`): `DbMemoria.insert_trade/update_trade/upsert_event/log` (`:287-318`): colonna per colonna; conteggio delle attivita' per `kind`.
5. **Numeri del referto** (`kind='referto'`): tick, decisioni, azioni, book in ritardo, lapse, fill attraversati, controlli sollecitati per codice (`K1 x7067`...), stati e fasi visti/non visti, scenari OK/KO, violazioni per codice; il referto senza le righe dei tempi (`righe_senza_tempi:525`).

**Tolleranze: ZERO.** Interi e stringhe uguali byte per byte; istanti uguali al millisecondo; prezzi e importi uguali nella rappresentazione scritta dal codice (gli arrotondamenti a 2 decimali sono dei bot, non del confronto); ordine delle righe uguale. **Normalizzazioni dichiarate (le sole)**, ciascuna con test di falsificazione e motivo scritto in `TOLLERANZE.md`:
 1. righe dei tempi, tick/s e picco di memoria (`PREFISSI_RIGHE_TEMPI:479` + `picco_memoria_mb:532`);
 2. hash del codice del bot e impronta dei moduli (cambiano per definizione: il referto li dichiara, il confronto li esclude e li stampa);
 3. identificatori derivati dall'orologio di macchina (`created_at`, uuid): sostituiti da un ordinale; `bet_id` e `ref` NON si normalizzano (se non sono deterministici fra due esecuzioni identiche, e' un fatto da capire prima di congelare: par. 4.4 passo 2).
 Qualunque altra differenza e' una `Divergenza(livello, ms, chiave, vecchio, nuovo, regola)` e fa uscire `certifica` con codice != 0.

**Falsificazione obbligatoria dell'ombra** (§6.7 e catalogo n. 35): mutare nel componente nuovo, uno alla volta, (a) una soglia di un tick, (b) un importo di 0,01, (c) un istante di 1 ms, (d) una decisione tolta, (e) una condizione con `ok` invertito, (f) una colonna DB cambiata, (g) un controllo K spento: ognuno DEVE far diventare rosso il livello atteso; e identita' (stesso codice due volte) DEVE dare 0 divergenze. Mutare anche la cassetta congelata (un byte) DEVE far fallire la verifica dell'hash.

**Ombra in produzione (paper)**: la stessa `confronta` si puo' applicare alle cassette scritte da vecchio e nuovo componente in paper sullo stesso periodo; accendere un secondo processo e' una decisione dell'utente (nessun processo nuovo senza permesso): qui e' descritto solo come riuso.

### 4.4 Riferimenti da CONGELARE prima di cominciare (elenco)
Congelare = copiare in `ARCHITETTURA_2026-10/riferimenti_congelati/` (cartella nuova, solo-aggiunta) con un `MANIFEST.json` che porta, per ogni voce: percorso, byte, sha256, comando esatto, commit, versioni. Verifica a ogni tappa: `certifica --verifica-congelati` ricalcola gli hash e fallisce se una voce e' cambiata.

**A. Software e versioni** (misurati oggi): commit del repo `f26a490e` (da sostituire col commit di congelamento); `banco_comune.py` ultimo commit `b5547eb8`, blob `d1887913da35`; flumine **2.13.11**, betfairlightweight **2.23.2**, Python **3.13.3** (`.venv`); `requirements.txt` hash; impronta `_IMPRONTA_CHIUSURA_FLUMINE` = `43ee8df005fd9454e18a7f8f24e66787bf3aa042f6564a64d4f037fc8539e57c` (`banco_comune.py:1642`); `pip freeze` completo (da produrre al congelamento).
**B. Registrazioni** (sha256 misurati oggi con `sha256sum`):

| Partita | File | sha256 |
|---|---|---|
| 35760084 (calcio, COMPLETE) | `registrazioni_banco/35760084/35760084.raw.jsonl.gz` | `6523b03ca307c94e06046dc90c89c2532c8efd77992a60fd2f83702b0879f4fb` |
| | `.scores.jsonl.gz` | `ff334d75ff176e04f1b47db0fd20ec332c9faafc2b90b3d97ce388e1b2a1f8e7` |
| | `.timeline.jsonl` | `31dc7de976327d2896f08e2a764dd5074c2ed1c41efe93518c82a7428d31c8cf` |
| | `_live_raw/35760084/35760084.raw.jsonl` | `8037bac2504ed1ef3c58147bbcd216c5628c36725f81672b03a098b0f96dcda8` |
| | `_live_raw/35760084/35760084.scores.jsonl` | `6910bcab3fbba9840270ac1171891760feb8ba08d56868abc1e09d6df3df998f` |
| 35797769 (calcio) | `registrazioni_banco/35797769/35797769.raw.jsonl.gz` | `5814fcd6391f01edd3feaeda8a260686f00c799d00795d1d420674d3468b902c` |
| | `.scores.jsonl.gz` | `a0348577ffb72728129d76bde47b2040700e0a6ab91e04d72fc63ff5deefe7e6` |
| | `.timeline.jsonl` | `7a92a5c7b0c56a1bcb161520e7ef814e358109595513f9d5c9cba544661a055a` |
| | `_live_raw/35797769/35797769.raw.jsonl` | `c11894abd1a6ead302e622395bb21d76c2f9c4cee31dfbf5ee4c7ad594ba5883` |
| | `_live_raw/35797769/35797769.scores.jsonl` | `28c3de961f2f27164930da494ebca35e533f51c1552c24905a0bc02d65d931c5` |
| 35790089 (tennis, pro/scalper/swing) | `Desktop/tennis_rec/20260707/35790089/35790089.raw.jsonl` | `ffb2a523544e17d55767a67ce8f582a710dd99a1cc2d322a45f045d8b00d942b` |
| | `.score.jsonl` | `99edcc184e68e368035395c41b07c76b321528ab41fdf991a55800e76db38d25` |
| 35794049 (tennis FLB) | `.raw.jsonl` | `3d5ed00f255146a0028b8e726459cfb3ac374c0c9f7cfccc986a4368de4737aa` |
| | `.score.jsonl` | `e0cb019bb816f2027d9a34f16102e3f8e15a728574fea5ee10b084d076f2a56e` |
| 35795993 (tennis, safe_tennis) | `.raw.jsonl` | `35bceb13cd1d393b2d3f8cb7f8c0800ae2bf21123a8b7dd2dd1e0aaa67dadd9b` |
| | `.score.jsonl` | `e9b7c928dae4ad8c882363b62b785328c3d0bfa2a7556b8a9ec9eae86e313e4c` |

Nota: le 22 partite di Safe calcio (`safe_base_tutti_PUNTE_MULTIPLE.txt:2143`) e le altre registrazioni di `_live_raw/` (83 voci, `ls _live_raw | wc -l`) NON hanno qui l'hash: vanno scelte (decisione 5) e calcolate al congelamento; `_live_raw/` e `tennis_rec/` NON sono sotto git (`git ls-files _live_raw` vuoto), quindi la copia con hash e' l'unica garanzia.
**C. Comandi esatti e referti** (con sha256 dei referti esistenti, misurati oggi); ogni comando va scritto per intero nel manifesto con `--worker`, `--trasporto`, `--ogni-ms`:

| Bot | Comando | Referto esistente | sha256 |
|---|---|---|---|
| Mike | `certifica mike 35760084 --scenari tutti` | `AUDIT_2026-10-02/replay/mike_tutti_MASTER_FINALE.txt` | `11f45a309f45cb517386c93dd06e83e1cd526d0a3fe2ec294788a6063fd1a149` |
| Mike (canale) | `certifica mike 35760084 --scenari base --trasporto canale` | `mike_base_riavvio_stantio_MASTER_parita.txt` | `4924927b7ab9c6f842e0b55c69ca56e5a79ccefea9c741aacea87dca91b75a6f` |
| Omega | `certifica omega 35760084 --scenari base` | `omega_base_MASTER_parita.txt` | `7efb782b46c17f65e689e383a6c4e59b01ff5ef915005bd123476daf76116374` |
| Omega | `certifica omega 35760084 --scenari tutti` | `AUDIT_2026-10-07/omega_apertura_35760084/replay/DOPO_35760084_tutti.txt` | `e95996bfa9def89132bc2bf4100159223863c0a2179071753c461e3f96cb8be6` |
| Omega | `certifica omega 35797769 --scenari tutti` | `DOPO_35797769_tutti.txt` | `43f3b8dc6880d0d91fb7cb17b2bb8cbdb3a4a3676478215d2a64f3a2331d9915` |
| Safe | `certifica safe_base ... --scenari tutti` (22 partite) | `AUDIT_2026-10-04/replay/safe_base_tutti_PUNTE_MULTIPLE.txt` | `91f85fbcccf79d4d70a30cb09bb20b64579b99bf8c2fdf0422c4ed61188a5930` |
| Safe | `certifica safe_base 35760084 --scenari rapidi --trasporto entrambi` | `safe_base_rapidi_entrambi_PUNTE_MULTIPLE.txt` | `a862e88f9f0c2595646018d0a7795cdf3f3eb69d7113f44995e9972e11a90e97` |
| Scalper calcio | `certifica scalper_calcio 35797769 --scenari tutti` (prima del 08/10) | `AUDIT_2026-10-08/banco_attraversa/calcio_prima_tutti.txt` | `ab2a493b7e11d5614e8afcf59541f180d922e7f5441674ded0f56604839b4706` |
| Scalper calcio | `certifica scalper_calcio 35797769 --scenari base,paper,chiusura-abbinata-in-parte,rifiuti-betfair,sniper-paper` | `calcio_dopo_5.txt` | `aedce4a721f02b02e58b07f94c08f351884fe440ea11d07558dc54b87d8bec46` |
| Tennis pro | `certifica tennis_pro 35790089 --scenari tutti` | `tennis_dopo.txt` | `b28c45f52252e8d877eb8a812edf429af0af58f286f66b97a86206dfb4269ec1` |
| Tennis FLB | `certifica tennis_flb 35794049 ...` (6 replay) | `AUDIT_2026-10-04/replay/tennis_flb_35794049_TETTO.txt` | `7743dc9638e97e8c08739d57c1e1849a535eff024dc52def85bc8f942959732b` |

**Il vincolo che rende il congelamento valido**: i referti qui sopra hanno DATE e versioni del banco diverse (02/10, 04/10, 07/10, 08/10; solo l'ultimo ha `ATTRAVERSAMENTO`). Un riferimento di parita' vale SOLO se prodotto dal banco in congelamento. Percio': passo 1 = congelare il banco (nessuna modifica a `Betfair/stream/backtest/**` finche' dura la migrazione di un componente, salvo nuova baseline completa); passo 2 = RIPRODURRE ogni baseline con il codice di oggi e la cassetta, ESEGUIRE LA STESSA COSA DUE VOLTE e verificare 0 divergenze (determinismo); solo allora le cassette e i referti entrano nel manifesto. I referti della tabella sono la storia, le cassette del passo 2 sono il riferimento.
Prima di tutto dipendono da due lavori in corso: **cantiere 15** (nuovo riferimento dello scalper col banco realistico; per tutti gli altri bot «stesso controllo» col banco realistico, `SPECIFICHE...:360-394`) e **cantiere 11** (velocita': cambia il banco, referto identico). Il congelamento si fa DOPO di loro.

### 4.5 Stima delle righe (metodo esplicito)

| Voce | Oggi | Domani | Calcolo |
|---|---:|---:|---|
| Nucleo e satelliti del banco | 12.436 | 12.436 | invariato (si spezza `banco_comune.py` per responsabilita', non si riduce) |
| Strumenti `misura_punto8` | 3.640 | 3.640 | invariato |
| Backtest Automatico (`run_backtest`, `sim_strategy`, `worker`) | 955 | 955 | decisione 1 |
| Adattatori (6 file) | 14.114 | 10.655 | 14.114 - 5.289 (blocchi «stesso ruolo», par. 1.3) + 1.500 (adattatore unico: ponte unico ~900, scheletro di `certifica_scenario`/`main`/parametri/nota ~600) + 330 (11 file `bots/<nome>/banco.py` x ~30) |
| Controlli (7 file) | 11.691 | ~11.291 | -400: `Referto` x6 (199 righe), `Violazione` x6 (75), `Osservazione` x3 (192), `Andamento` x3 (45) -> una copia da ~110 (somma ~511 -> 110); le regole (`_a*`, `_b*`...) restano: sono strategia/condotta |
| Parita' (nuovo): `ombra.py` ~450, `cassetta.py` ~250, `congela.py` ~200 | 0 | ~900 | stima per analogia con `certifica.py:impronta` (45 righe), `righe_senza_tempi` (8), `trasporto.confronta` (parte di 633) |
| `porta_flumine.py` (assorbe 70 righe di import e 34 righe di API privata) | 0 | ~250 | stima: 7 API private x ~15 + 4 copie con impronta x ~30 |
| **Totale Python** | **42.836** (= 12.436 + 3.640 + 955 + 14.114 + 11.691) | **~40.127** (= 12.436 + 3.640 + 955 + 10.655 + 11.291 + 900 + 250) | -2.709, -6,3 % |

Il banco e' in gran parte STRATEGIA E CONDOTTA specifica del bot (scenari, guasti, regole dei controlli): le righe non calano molto. Il guadagno e' di altro tipo: un solo ponte (una correzione una volta sola), una sola fonte degli scenari, una sola porta verso flumine (aggiornamento a flumine 3 su un modulo), e la parita' automatica. Test nuovi (non contati sopra): ~600 righe per la falsificazione dell'ombra, il contratto dell'adattatore e il test di determinismo.
Frontend: `replayBotCatalogo.ts` 11.099 righe generate potrebbero sparire dal repo (decisione 3: JSON servito dal registro); le 8.127 righe a mano restano.

### 4.6 «Per sostituire questo componente OGGI tocco ... / DOMANI tocco ...» (criterio §9.1)
- **OGGI**, per sostituire il banco (es. passare a flumine 3 o cambiare il motore di matching): `banco_comune.py` (20 import di flumine, 5 API private), `trasporto_rapido.py`, `chiusura_parziale.py`, `trasporto.py`, `minimi_banco.py`, `porta_banco.py`, i 6 adattatori (ciascuno con il proprio ponte e i propri 3-9 import), `run_backtest.py`, `sim_strategy.py`: **70 righe di import in 14 file**, 9 costruzioni di `FlumineSimulation`, e poi ricertificare 11 bot a mano.
- Per sostituire UN BOT (es. Mike): il suo file di replay (2.370 righe), i suoi controlli (2.084), `registro_bot.py:219-243`, `applica_bot.py:67,155` (scenari applicabili), il catalogo TS (`replayBotCatalogo.ts`), `TRASPORTO_OBBLIGATO`: **5 aree** fuori dalla cartella del bot.
- **DOMANI**: per sostituire il motore: solo `nucleo/porta_flumine.py` (+ le impronte) e i test di contratto del banco; per sostituire un bot: solo `bots/<nome>/` (Plugin + `banco.py` di ~30 righe + controlli) e il suo test di contratto; registro, scenari applicabili, catalogo e pannello UI si derivano dal Plugin.

### 4.7 Cosa e' gia' in una libreria matura e oggi e' riscritto
- **flumine** fornisce `FlumineSimulation`, `HistoricalStream`, `SimulatedMiddleware`, `SimulatedExecution`, matching con coda: il banco li USA (non li riscrive) ma ne riscrive: la pompa dei libri (`GeneratoreLibri:1847` vs `flumine/streams/historicalstream.py:259-275`), la chiusura del mercato (`:1655` vs `baseflumine.py:353-414`), il rifiuto sotto il minimo (`minimi_banco.py` vs `simulatedexecution.py`), la regola di abbinamento al prezzo quando il mercato attraversa (`:2114`; in flumine 3 «abbinamento passivo dinamico», piano 02/10 riga 78: candidata a sostituire la nostra regola, da certificare come «piu' realistico, non regressione»).
- **betfairlightweight**: i `MarketBook` e le risorse sono quelli veri; la costruzione del catalogo dei runner dal raw (`_nome_runner:2502`, limite 1 della testata) e' nostra perche' lo stream non porta i nomi.
- **pytest/difflib**: la cassetta e il confronto si scrivono con la standard library (JSON Lines + confronto per chiave); non si introduce una libreria nuova.

---------------------------------------------------------------------------------------------------

## 5. PARITA'

La parita' del banco e' in due parti: (a) che il banco stesso non cambi mentre si migra (identita' del banco), (b) che ogni componente nuovo dia le stesse cifre (ombra, par. 4.3).

### 5.1 Identita' del banco (da tenere verde)
- Equivalenza via lenta/veloce: `test_banco_identita_2026_09_16.py` (701 righe), `test_banco_replay_veloce_2026_10_02.py` (439), `test_banco_prestazioni_2026_09_30.py` (274), `test_cantiere_v_replay_veloce_2026_09_29.py` (382), `test_cantiere_v2_replay_veloce_2026_09_29.py` (204): ogni interruttore di modulo (`:1799-1844`) ha il suo.
- Regola dell'attraversamento: `test_banco_attraversa_2026_10_08.py` (306), caso vero `35768297` (`AUDIT_2026-10-08/banco_attraversa/caso_vero_*.json`), mutazioni (`mutazioni.txt`).
- Contratto del registro: `test_registro_bot_2026_09_16.py` (187), `test_applica_bot_tutti_2026_10_07.py` (557, incluso l'allineamento del catalogo TS).
- Nucleo: `test_banco_comune_2026_09_16.py` (1.106), `test_strada_unica_banco_2026_09_25.py` (447), `test_minimi_banco_2026_10_02.py` (145).

### 5.2 Parita' per bot (sezione 5 delle schede E1-E5, riassunta)

| Bot | Registrazione | Cosa deve coincidere (riferimento) | Fonte |
|---|---|---|---|
| Mike | 35760084 | 26 coppie evento x scenario, tick/decisioni/azioni per scenario (`base` 52.082/5.246/6; P&L -14,17 in 9 scenari); 5 sintetiche | E1 5.2 |
| Omega | 35760084, 35797769 | `base` 438/0/483.985; `apertura` 467/2/482.034; `tutti` 20/20 OK 0 violazioni | E2 5.2 |
| Safe | 35760084 (decisioni=3512), 22 partite; tennis 35795993 | `22 partite senza violazioni`; `PARITA'` coda/canale | E3 5 |
| Scalper | 35797769 | numeri IN REVISIONE (cantiere 15): `base` 44 -> 18 azioni | E4 5 |
| Tennis pro | 35790089 | `base` 5.216/5.212/0; `gate-aperto` 7 azioni; `bot-fermo` 2.483 decisioni; `rifiuti-betfair` 2; `live` 7 | E5 5 |

### 5.3 Copertura di §6 e §7 per bot (voce x bot). Legenda: ✓ sollecitato/coperto, ⊘ non esercitabile o non sollecitato (con causa), ? non letto/da verificare

| Voce di `PROCESSO_STANDARD_BOT.md` | Mike | Omega | Safe calcio | Safe tennis | Scalper calcio | Tennis (4) |
|---|---|---|---|---|---|---|
| §6.1 dati di mercato | ✓ 35760084 COMPLETE x1 (una sola registrazione completa) | ✓ 2 registrazioni | ✓ 22 partite | ✓ 35795993 | ✓ 35797769 COMPLETE 95,4 % | ✓ 35790089 92,4 % con 5 buchi dichiarati |
| §6.2 scanner e feed veri | ✓ 2.344 righe dallo scanner VERO | ✓ 434 righe | ✓ `feed_stantio` | ✓ `ScannerReplay(nomi_extra)` | **⊘ lo scalper legge il book, non lo scanner** (E4 5; `auto-live` fa il solo giro auto) | ? (E5 non lo dichiara: da verificare) |
| §6.3 servizio intero, cadenza reale | ✓ 14 stati su 21; **⊘ 7 stati mai visti** (`PRE_LAST_ENTRY_PENDING`, `LIVE_SECOND_ENTRY`, `REENTRY_*`, `ERROR`, `SKIPPED`), solo sintetiche | ✓ 438 giri | ✓ `bot_fermo`, `riavvio` | ✓ `riavvio` | ✓ `run_session`; **S7 riavvio ⊘ mai sollecitato nei 5 scenari del 08/10** (KO il 07/10) | ✓ `riavvio`, stati `OPEN,CLOSING` |
| §6.4 ordine: parziali, bet delay, ignoti | ✓ J, K, S, CP, R, KG | ✓ K1-K7, J1-J7; `esiti-ignoti`, `rifiuti-betfair` | ✓ K, `ordini`, `esiti_ignoti`, `due_lay` | ✓ `rifiuti-betfair`, `uscita-ignota` | ✓ ma `chiusura-abbinata-in-parte` **KO** col banco realistico (B2, CP4); **CP2 ⊘ x0** | ✓ `rifiuti-betfair`, `parziali`; **B10 e CP2 ⊘ mai sollecitati sul pro** |
| §6.5 persistenza e UI | ✓ RG1; UI dipende dalle fotografie | ✓ righe `omega_trades`; fotografie | ✓ vitest + fotografie | ✓ | ✓ P1/P2; fotografie ? (non verificato che coprano tutti gli stati) | ✓ `_mirror_order`; 20 fotografie |
| §6.6 concorrenza e limiti | **⊘ parziale: un solo giro per volta** | ✓ `cap-stretto`, `manuale-e-bot` | ✓ `coord_safe_omega` | ? | ✓ S2, `kill-switch` | ? |
| §6.7 scenari e falsificazione | 26 + 5; falsificazione da rifare | 20 + 8 mutazioni (07/10) | `tools/falsifica_*` | ? | mutazioni 25/09 come precedente | ? |
| §6.8 referto riproducibile | ✓ `1fa090ef6631` (9 file) | ✓ `ff8f89cbccdc` (13 file) | ✓ `39b7c22add2c` (19 file) | ? | ✓ `fa6c7016c31e` (12 file) | ✓ `8b0dbb723dd4` (23 file) |
| §6.9 velocita' | **✗ 728,4 s** | ~ 432,7 s (obiettivo 300) | ✓ 254,1 s | ✓ 8,5 s | **✗ 6.916 s** | ✓ 18,9 s |
| Controlli mai sollecitati («non lo so») | **6 su 49** (A2, B6, B7, H1, H2, J5B; E1 D11) | **38 su 52** con `tutti` (`DOPO_35760084_tutti.txt:518`); 48 su 52 con `base` | **25 su 66** (`PUNTE_MULTIPLE.txt:2228`) | ? | **2 su 22** (S7, CP2) | **3 su 22** sul pro (B6, B10, CP2) |
| §7 n. 21 (paper+live sommati) | ⊘ solo fotografia UI | **⊘ NON coperto dal replay** (finto `aggregates` senza `mode`, n. 27) | ✓ `aggregates(mode)` | ? | ✓ S6 | ✓ scenario `soldi-veri-paper` |
| §7 n. 36 (consapevolezza dell'ordine, K) | ✓ K1-K4, CP1-CP4 | ✓ K1-K7 | ✓ `certificazione_k.py` | ✓ | ✓ K1-K7 | ✓ |

Letture: `⊘` con causa viene dalle schede E1-E5 sezione 5 e dai referti citati; `?` = nessuna delle schede ne parla o non l'ho verificato di persona. Il catalogo §7 (35+2 voci) per intero NON e' stato ricontrollato punto per punto qui: E1 lo dice espressamente («va ricontrollata punto per punto in sede di tappa»), E3 pure.

### 5.4 Voci di §6 e §7 che la parita' del banco deve provare per OGNI componente nuovo
- §6.3, §6.4, §6.6, §6.7, §6.8, §6.9 (il banco e' il metro): ogni tappa riproduce cassetta e referto e li confronta numero per numero con il congelato.
- §7 n. 8-16 (simulazione) e n. 31 (copie di laboratorio): il nuovo componente passa dall'adattatore unico e dal ponte comune (non si ammettono classi «lab»).
- §7 n. 27 (finti con chiavi e tipi del vero): test di contratto dell'adattatore che confronta, per ogni finto del banco (`DbMemoria`, `DbMemoriaOmega`), le firme con quelle del vero (cattura il difetto 6 del par. 3).
- §7 n. 35 e n. 37: falsificazione dell'ombra e isolamento dei processi (`_prepara_figlio:551`).

---------------------------------------------------------------------------------------------------

## 6. MIGRAZIONE

Ordine rispetto agli altri componenti: **H va PRIMA di tutti** (e' il metro degli altri). Il banco non si migra: si CONGELA, si arricchisce con la cassetta (comportamento invariato) e poi si usa.

1. **Prerequisiti (altrui)**: cantiere 15 (riferimento scalper col banco realistico, e riga «dove il banco anticipa un fill spiegata» per tutti gli altri bot) e cantiere 11 (velocita', referto identico). Senza di loro i riferimenti cambiano sotto i piedi.
2. **Congelamento del banco**: nessun commit su `Betfair/stream/backtest/**`, sui 6 adattatori e sui 7 moduli di controlli durante la migrazione di un componente, salvo «nuova baseline completa dichiarata».
3. **Cassetta (nel banco, nessun cambio di condotta)**: aggancio ai punti di par. 4.3; prova di innocuita': referto identico, esclusi i tempi (`righe_senza_tempi:525`), su Mike `base`, Omega `base`, Safe `base`, scalper `base`, tennis_pro `tutti`; falsificazione (cassetta spenta -> `confronta` rosso).
4. **Determinismo**: ogni baseline prodotta DUE volte con lo stesso comando: 0 divergenze. Se non e' 0, non si congela: si capisce prima (e' un reperto).
5. **Baseline per ogni bot** con il codice di oggi (non lanciata da me: dichiarare all'utente la durata prima di ogni lancio, §6.9: Mike 728 s, Omega 433 s, Safe 254 s, scalper 6.916 s, tennis 19 s; il blocco in cantiere 11 la abbassa) e congelamento nel manifesto (`MANIFEST.json`: path, byte, sha256, comando, commit, versioni).
6. **`ombra.py` + `TOLLERANZE.md` + falsificazione** (par. 4.3). `certifica <bot> <evento> --ombra <cassetta_congelata>` esce != 0 a divergenza.
7. **`porta_flumine.py`**: spostamento puro degli import e delle API private (70 righe di import, 34 righe di API privata), referto identico per Mike `base`, Omega `base`, Safe `tutti`, scalper 5 scenari, tennis pro `tutti`.
8. **Adattatore unico** (contratto D): pilota = Safe tennis (usa gia' `replay_evento`, `replay_tennis.py:589`, 17 scenari, 8,5 s: il piu' veloce e il piu' vicino al ponte comune); poi tennis (19 s); poi Safe calcio (254 s), Omega (433 s), Mike (728 s), per ultimo lo scalper (6.916 s). Per ognuno: ombra a zero divergenze PRIMA di cancellare il vecchio adattatore.
9. **Taglio**: il vecchio adattatore si cancella solo dopo ombra a zero e firma di chi ha rieseguito il replay di persona (regola 5 dello standard).
10. **Flumine 3**: ULTIMO, dopo la parita' di tutti i componenti, con NUOVO congelamento (le baseline cambiano per costruzione: «abbinamento passivo dinamico»), un solo modulo da toccare (`porta_flumine.py`) e la distinzione scritta «piu' realistico / regressione» per ogni numero cambiato. Interleaving fra migrazione di componente e aggiornamento di libreria e' VIETATO (non si saprebbe chi ha cambiato il numero).

Rischi: (a) baseline non deterministica; (b) banco modificato per errore durante la migrazione (l'hash del manifesto lo scopre); (c) registrazione unica per Mike (D11): l'ombra prova la parita' sulla sola partita, non sulle 7 fasi mai viste: serve piu' di una registrazione o le sintetiche; (d) tempi: l'ombra raddoppia il costo solo se si rilancia il vecchio: con la cassetta congelata costa un replay + il confronto; (e) il manifesto non protegge da una registrazione sostituita fuori dal repo (`_live_raw` non e' sotto git): l'hash sì.
Ritorno indietro: il banco di oggi e' sotto git (commit di congelamento = tag); `--ombra`, `--congela` sono flag in piu': tolti, `certifica` e' quello di prima.

---------------------------------------------------------------------------------------------------

## 7. MISURE

| Grandezza | Oggi (fonte) | Obiettivo dopo | Strumento |
|---|---|---|---|
| Certificazione completa Mike | 728,4 s (26 replay) | <= 300 s, tetto 600 | `certifica` riga `TEMPO TOTALE`; profilo `cProfile` (cantiere 11 passo 1) |
| Omega (`tutti`) | 432,7 s (35760084); 33 min (35797769) | <= 300 s | idem |
| Safe calcio (22 partite) | 254,1 s | invariato | idem |
| Scalper calcio | 6.916 s (47 replay); 4.081,6 s media under (18) | <= 300 s per blocco, tetto 600 | idem; punto caldo: da misurare (S5 x463.834, P1 x360.868 sollecitazioni nel referto del 07/10) |
| Tennis pro / FLB / safe_tennis | 18,9 s / 15,7 s / 8,5 s | invariato | idem |
| «Applica bot» (1 scenario, 1 partita) | 258-314 s | <= 30 s; un clic <= 5 s | `live_backtest_requests` (timestamp created/updated) |
| Righe del banco + adattatori + controlli | 42.836 | ~40.1 mila (stima, par. 4.5) | `git ls-files | xargs wc -l` |
| Righe di import di flumine nel banco e negli adattatori | 70 in 14 file | 1 modulo (`porta_flumine.py`) | `git grep -n "import flumine\|from flumine"` |
| Montaggi del ponte (flumine + scanner + motore) | 7 (mike, omega, safe, scalper, tennis, nucleo, trasporto rapido) | 1 | `git grep -n "FlumineSimulation("` |
| Controlli mai sollecitati | Mike 6/49, Omega 38/52, Safe 25/66, scalper 2/22, tennis pro 3/22 | 0 oppure `⊘` con causa scritta | riga `MAI SOLLECITATI` del referto |
| Log del worker | 1.138,1 MB in 8 giorni (80 % di `_logs/`) | rotazione per dimensione, livello WARNING per flumine | `m05_risorse_disco.py` |
| Richieste a vuoto al cloud dal worker | ~16.900 al giorno | 0 a riposo (avvio a richiesta, decisione 2) | `m04_chiamate_db.py` |
| Divergenze ombra | non esiste | **0** per ogni livello e per ogni bot | `certifica --ombra` |

Numeri che non esistono e lo strumento che li misurerebbe: tempo per punto caldo del banco (cProfile su `certifica mike 35760084 --scenari base --worker 1` e `scalper_calcio ... --scenari base`); latenza di lettura REST vera (`storia_operazioni.py` per le sole letture: oggi assunta, 0,120 s `banco_comune.py:1844`); determinismo del banco (due esecuzioni identiche, par. 6 passo 4).

---------------------------------------------------------------------------------------------------

## DECISIONI PER L'UTENTE

1. **Backtest Automatico** (`run_backtest.py` 493 + `sim_strategy.py` 360, richieste senza `tipo=applica_bot`, `worker.py:47`): non e' codice dei bot di produzione, non passa dal registro. Tenerlo, ritirarlo (-853 righe e un punto di aggancio a flumine) o riportarlo dietro un plugin come gli altri.
2. **Worker del banco**: oggi 9o servizio h24 (`main.js:469`) con 16.900 richieste/giorno a vuoto e 1,1 GB di log. Passare ad avvio a richiesta e a rotazione dei log? (la scheda I propone «lanciato solo quando c'e' una richiesta»; qui non lo decido).
3. **Catalogo TS generato**: tenere `replayBotCatalogo.ts` (11.099 righe nel repo) o servirlo da una RPC/JSON generato al volo dal registro (nessuna riga nel repo, stesso contenuto).
4. **Ordine con flumine 3**: raccomandato DOPO la parita' di tutti i componenti (par. 6 passo 10); alternativa: prima di tutti, con una sola ribaseline iniziale. Non nel mezzo.
5. **Quali registrazioni congelare**: le 5 partite qui (2 calcio, 3 tennis) bastano per il tennis e per Omega/scalper, ma Mike e' certificato su UNA sola partita COMPLETE (E1 D11). Servono altre registrazioni COMPLETE (`_live_raw/` ne ha 83 voci; qualita' da `Betfair/stream/tools/validate_recordings.py`, non eseguito qui) e/o le sintetiche come parte del riferimento.
6. **Tolleranze**: approvare la lista chiusa di 3 normalizzazioni (par. 4.3) come UNICHE ammesse.
7. **Finto di Omega senza `mode`**: correggerlo dal banco (cambia i referti di Omega: «prima/dopo», E2 §6) PRIMA del congelamento, cosi' la baseline di Omega nasce con la firma giusta. Se si congela prima, la baseline porta il difetto.
8. **Assunzione dei 120 ms di lettura REST** (`banco_comune.py:1844`): misurarla (e rifare le baseline) o confermare l'assunzione per tutta la migrazione.

---------------------------------------------------------------------------------------------------

## COSA HO VERIFICATO DI PERSONA / COSA NON HO POTUTO VERIFICARE

Verificato di persona (lettura del codice o esecuzione di strumenti di sola lettura; nessun replay lanciato):
- Righe di tutti i file del perimetro (`git ls-files` + `wc -l`); elenco e righe delle funzioni di `banco_comune.py`, `certifica.py`, `registro_bot.py`, `applica_bot.py`, `varianti_bot.py`; corpo di `_mercato_che_attraversa` (`:2114-2213`), `_replay_evento` (`:2918-3046`), `worker.py` per intero, `certifica.py` (`impronta:223-268`, `main:711-800`, tempi `:472-530`); flag di `certifica` e di `applica_bot`.
- Conteggi `git grep` (costruzioni di `FlumineSimulation(`, righe di import di flumine, API private, `_Ponte`, `MercatoFlumine(`, `MotoreReplay(`, `ScannerReplay(`); output di `h_gemelli_adattatori.py`, `h_scenari_per_bot.py` (riletti) e `h_righe_omonime.py` (nuovo, in `ARCHITETTURA_2026-10/strumenti/`).
- Hash sha256 di 17 file di registrazioni e di 11 referti, `flumine 2.13.11`/`betfairlightweight 2.23.2`/Python 3.13.3 dal `.venv`; i tempi `TEMPO TOTALE` letti nei referti citati (`grep`); le righe `MAI SOLLECITATI` e `ESITO` dei referti citati; esistenza di `AUDIT_2026-10-08/riferimenti/` (assente).
- Testata e generazione di `replayBotCatalogo.ts` (righe 1-9 e `applica_bot.py:365`, `:875-892`).

NON verificato:
- Nessun replay del banco rieseguito (vietato dal brief): i tempi e i numeri di parita' sono quelli dei referti, non rimisurati. In particolare NON ho verificato il determinismo di due esecuzioni identiche.
- Il «33 punti» del piano del 02/10 non e' riprodotto: il mio conteggio (70 righe di import, 34 righe di API privata, 9 costruzioni) e' un'altra misura.
- Il punto caldo dei replay lenti (profilo): non misurato; la tabella dei numeri dell'ombra (par. 4.3) e le stime di righe (par. 4.5) sono PROPOSTE con calcolo, non misure.
- Copertura §6/§7 per bot: la tabella 5.3 riassume le sezioni 5 delle schede E1-E5 e i referti, non e' una rilettura del catalogo §7 punto per punto; le celle `?` sono dove nessuna fonte letta risponde (tennis: scanner, concorrenza, falsificazione; safe_tennis: impronta e concorrenza).
- La riga `certifica.py:~744-760` (messaggi di rifiuto) e le righe di alcune funzioni di `trasporto_rapido.py` (`BancoRapido:~172`) sono approssimate al blocco letto; `main.js:413-470` e `:279-282`, `db.py:710-747`, i dati dei log (1.138,1 MB) provengono dalla scheda I e dalla lettura di `db.py`, non rimisurati.
- `H-044` il numero di controlli attivi per FLB (19) viene da E5, non dal referto; il referto FLB e' stato solo contato per tempo.
- Non ho letto `PIANO_CERTIFICAZIONE_DEFINITIVA_2026-09-16.md` ne' `CRONOSTORIA.md`.
