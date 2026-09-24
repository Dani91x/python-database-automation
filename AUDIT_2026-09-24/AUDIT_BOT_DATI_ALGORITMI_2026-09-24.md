# AUDIT BOT x DATI x ALGORITMI - 24/09/2026

Domanda dell'utente: «I bot che abbiamo costruito utilizzano i dati del database e algoritmi
avanzati per il live? Valuta attentamente se possiamo migliorare le performance dei bot grazie ai
dati in nostro possesso.»

Metodo: audit IN SOLA LETTURA sul worktree allineato a master `20a913a`. Nessuna modifica al
codice, nessun processo del progetto, nessun accesso al DB, nessun `.env`. L'unico codice eseguito
sono stati dei `python -c json.load` per leggere i metadati dei file JSON di dati (nessun modulo del
repo importato).
- Quattro sotto-audit paralleli: Omega; Mike; Safe calcio e tennis; tennis_live, scalper, xhedge e
  feed. Li ho riverificati io a campione sui punti chiave.
- Il grep trasversale sulle tabelle l'ho fatto io.
- I numeri del DB sono quelli letti dal coordinatore il 24/09 alle 12 UTC.
- Dove un numero non l'ho potuto misurare scrivo «NON VERIFICATO» e do la query SQL (§7).

Legenda: **[AVANZATO]** indica un modello probabilistico, un EV o un'ottimizzazione.
**[SOGLIA]** indica una regola fissa su prezzo, minuto o punteggio.

---

## 0. Risposta breve (per il trader)

1. **I dati live sono tutti di Betfair e non da API-Football.**
   - Quote: dallo stream (con ripiego REST).
   - Punteggio, minuto, rossi, corner e gialli: dall'IPS `scoresAndBroadcast` ogni 2 s, scritti
     dallo scanner di Safe in `safe_strategy_scan`.
   - Nessun bot vede tiri, xG, attacchi pericolosi o possesso.
   - API-Football live esiste solo come ripiego del runner calcio (`Betfair/stream/scores/api_football.py:77-86`).
2. **Dei dati di analisi del DB, i bot usano UNA sola tabella: `fixture_predictions`, e in pratica
   ne leggono solo le lambda pre-partita.**
   - Colonne lette: `tactical_engine_json.lambda_*`, poi `db_json_analisi.inputs.lambda_*`.
   - Punto di lettura: `Betfair/stream/db.py:211-252`.
   - Grep su tutto `Betfair/` (test esclusi): **ZERO riferimenti** a `analytics_signals`,
     `poisson_calibration`, `ml_post_calibration`, `direction_pagella`, `engine_signals`,
     `match_odds`, `match_team_stats`, `match_lineups`, `standings` e `injuries`.
   - Le uniche eccezioni sono i tool offline e i job di reportistica: `Betfair/betfair_report_manager.py:239-278`
     sincronizza `engine_signals` e `analytics_signals`, ma nessun bot li consuma.
3. **Il resto dello storico entra per via indiretta, attraverso tabelle e file precalcolati:**
   - `omega_minute_transitions` e `omega_ht_ft_transitions`, costruite da `matches` + `match_events`;
   - l'atlante hazard `hazard_atlas_v1/v2.json`, del 15/07;
   - `inplay_intensity_by_league.json` (29/06), `dc_rho_by_league.json` (15/09, 20 leghe),
     `opp_calibration.json` (10/09, 32 partite).
4. **Gli algoritmi avanzati esistono, ma quasi solo in USCITA e in Omega.**
   - Omega V3 entra con un modello Gamma-Poisson/NegBin fuso col mercato e un veto empirico
     [AVANZATO sotto un cancello a SOGLIA].
   - Mike decide copertura, cash-out e uscita in perdita a EV [AVANZATO], ma entra a SOGLIA.
   - Le quattro strategie di Safe entrano a SOGLIA pura. L'uscita in profitto/a tempo passa da
     un gate a modello Poisson residuo [AVANZATO], che usa probabilita' NON calibrate.
   - I 4 bot tennis e lo scalper sono a SOGLIA o microstruttura. Fanno eccezione il bias
     ML+Poisson del maker e l'hazard di theta.
   - xhedge e' un minimax deterministico, senza probabilita'.
5. **Il fatto misurato che va detto subito.** Il 17/09 M2 ha misurato su 657 partite fuori
   campione che NESSUNA fonte storica del DB (fixture, tattico, API, forza, forma, h2h) migliora
   le lambda rispetto alle quote devigate del mercato con un IC che escluda lo 0.
   - Fonte: `CRONOSTORIA.md:250-255`, `Betfair/omega/M2_DATI_E_PESI_2026-09-17.md`.
   - Come scommesse dirette, i motori del DB hanno ROI storico negativo: Poisson -5,3%, ML -8,0%
     (`Betfair/omega/PROGETTO_OMEGA_V3_2026-09-16.md:104-105`).
   - Conseguenza: «usare piu' DB» NON e' di per se' un miglioramento. Il valore sta in quattro cose:
     - (a) tenere FRESCHE le tabelle empiriche;
     - (b) riempire i buchi quando manca il mercato Betfair (pre-KO assente);
     - (c) calibrare le code e le P d'uscita;
     - (d) usare i dati come VETO e non come segnale.
6. **Due correzioni al brief** (verificate sul codice):
   - `match_odds` sono quote **bookmaker PRE-MATCH di API-Football** (`per_fixture_backfill.py:318-319`
     chiama `/odds`; `DOCUMENTAZIONE_DATABASE.md:25`), non quote Betfair in gioco. **Non servono a
     stimare slippage o liquidita' Betfair per minuto.** Per quello servono le registrazioni
     `_live_raw/` e `betfair_market_odds`.
   - `analytics_signals.freq_*` e `delay_*` sono frequenze e ritardi di **MERCATO per lega**
     (esempio: quante partite di fila senza Over 2.5), non minuti-gol
     (`migrations/analytics_signals.sql:57-63`). Come probabilita' non valgono. Come filtro di
     regime, «molto in ritardo >= 1,6x» e' storicamente la colonna peggiore
     (`PROGETTO_OMEGA_V3_2026-09-16.md:109`).

---

## 1. TABELLA RIASSUNTIVA

| Bot | Input live (fonte, cadenza) | Tabelle / file di analisi usati DAVVERO | Algoritmo di ingresso | Algoritmo di uscita | Freschezza dei dati di analisi |
|---|---|---|---|---|---|
| **Omega** (V3, `omega_config.py:231`) | `safe_strategy_scan` (minuto, punteggio, rossi, book CS, O/U, pre_ko) con cache 2 s; ciclo 20 s, a vuoto 60 s (`omega_config.py:35,158,220`); canale 47336 opzionale, spento di serie (`omega_service.py:594-600`); ripiego `live_now` e REST | `fixture_predictions` lambda (`omega_service.py:1063-1064`); `omega_events.model`; RPC `get_omega_minute_ft` (veto, `omega_db.py:1016`); RPC `get_omega_ht_ft` (ripiego, `omega_db.py:1003`); `data/parametri_vincenti_2026-09-16.json` (`omega_proposte.py:110-138`). Solo per la UI: `fixture_analysis`, `get_market_frequency`, `hazard_atlas_v2.h2h_hint` | [AVANZATO] Gamma-Poisson -> NegBin residua + profilo Dixon-Robinson + tau DC (`omega_v3.py:179-340`), pool logit col mercato (`omega_v3.py:410-467`), P_nostra = max(fusa, Wilson empirico) (`omega_v3.py:668`), sotto un cancello [SOGLIA]: P <= 2%, p_imp in [1%,2%], margine k >= 1,11, distanza >= 2 gol (`omega_v3.py:653-695`). Stake 1 EUR fisso, FOK | Solo PROPOSTE all'utente (`omega_proposte.py:226-262`) con EV di tenere contro bloccabile (`omega_v3.py:792-918`), su P GREZZA senza fusione (`omega_proposte.py:406-438`) | Transizioni per minuto e HT/FT ferme all'11/09 (M2, da riverificare: Q4); parametri V3 del 16/09 (2.018 partite); lambda da fixture: copertura 28-33% (M2) |
| **Mike** | Righe calcio di `safe_strategy_scan` (O/U 3.5/4.5 pre-KO, punteggio IPS) con cache 4 s (`mike/service.py:4729`, `config.py:303`); ciclo 1 s, a vuoto 5 s (`service.py:4858-4865`); canale 47336 opzionale e spento | `fixture_predictions` lambda (`mike/db.py:514`) e `db_json_analisi` (`inputs.dc_rho`, `markets_calibrated.over_3_5`) (`mike/db.py:527` -> `omega_db.py:754`); RPC `get_omega_ht_ft` -> `p_total_emp` (`dossier.py:148`); `hazard_atlas_v1.json` (`dossier.py:79-88`) | [SOGLIA] candidata se le linee O/U sono nel feed e il KO e' entro 1 h (`feed.py:345-362`); back Under 3.5 a 1,30-3,00, spread <= 6 tick, stake 10 (`engine.py:2235-2278`, `config.py:77,119-124`). **Nessuna P all'ingresso** | [AVANZATO] copertura O4.5 a formula chiusa `1,2*S/((Po-1)(1-c))` (`engine.py:384`) con timing su hazard/P4/cover_gain (`engine.py:1177-1216`); cash-out smart a EV (`engine.py:1040-1097`); uscita in perdita `cv_net >= EV_hold - 10%*P4*base` (`engine.py:1136-1174`) | `p_under35_cal` calcolato e MAI usato (`dossier.py:72`); `p_over45_cal` mai valorizzato (`dossier.py:54`); atlante del 15/07; HT/FT dell'11/09 |
| **Safe calcio** (base / esatto / punta) | Scanner proprio: stream (conflate 1 s) + REST di ripiego, IPS ogni 2 s, timeline ogni 30 s, scrittura con throttle 2,5 s (`safe_strategy/service.py:128-196`); bot ogni 2 s, lettura intera della scan (`bot_service.py:127`, `bot_db.py:889`) | `fixture_predictions` solo come prior lambda di USCITA e delle opportunita' (`bot_service.py:6221`, via `omega_events`); `opp_calibration.json` (solo opportunita', `opportunity.py:859`); `inplay_intensity_by_league.json`; `dc_rho_by_league.json`. `dynamic_cal` SPENTO (`live_engine_pro.py:113`); atlante non collegato (`bot_service.py:3787,8930` -> `opportunity.py:643`) | [SOGLIA] puro: minuto (dal 55', 48', 66'), punteggi, fav pre 1,4-1,8, sfav 4-8, fav live 1,20-1,34 (`engine.py:891-1204`); requireControl spento (`engine.py:902`); stake 2 EUR (`engine.py:270`); gate di rischio (`risk.py:38-45`) | Regole del manuale (`exits.py:879`) + gate a modello sulle uscite in profitto/a tempo: EV_hold = (1-p)*profitto - p*liability (`exits.py:426-510`), p dal book Poisson residuo **non calibrato** (`bot_service.py:3840-3872`) | `opp_calibration` del 10/09 su 32 partite; nel backtest del 10/09 le lambda venivano da fixture 0/38, da default 17/38 |
| **Safe tennis** | Stessa scan (set, game, servizio da `score_raw` IPS, `service.py:60`) | Nessuna tabella; `serve_data.csv` ASSENTE, quindi hold fisso a 0,75 (`tennis_opportunity.py:234-257`) | [SOGLIA] 1 set avanti + >= 2 game, back del leader a 1,01-1,10, conferma 15 s (`engine.py:1229-1376`) | Regole (`exits.py`) + gate a modello di Markov con hold 0,75 (`bot_service.py:4012-4050`) | Nessun dato storico tennis nel DB |
| **Safe opportunita'** (modello, anomalie, combo) | Idem, ogni 10 s (`bot_service.py:153`) | Come sopra; calibrazione `opp_calibration.json` | [AVANZATO] book Poisson/DC residuo, EV = p(q-1)(1-c)-(1-p), confidenza composita (`opportunity.py:66-100,902-960`). **Solo proposte** (`bot_service.py:6440-6447`) | - | Idem |
| **4 bot tennis** (scalper, pro, flb, swing) | Stream flumine in-process (`tennis_runner.py:412-414`); punteggio da scan_feed, poi IPS diretto, ogni 2 s (`tennis_runner.py:83,1131-1158`) | Nessuna. `p_match` Markov calcolato ma solo per la UI (`tennis_runner.py:271-314`) | [SOGLIA] / microstruttura: scalper = mean-reversion su micro-price; pro = setup sul punteggio (3 setup su 6 spenti perche' surface = "grass" di default, `tennis_pro_bot.py:105-108`); flb = lay del favorito <= 1,10; swing = z-MAD + ER + RSI | Tick fissi di target e stop | - |
| **Scalper calcio** (maker / sniper / theta) | Stream flumine MO, OU1.5/2.5/3.5 (+OU 0.5-8.5) (`scalper_session.py:81-86`); punteggio da `live_now` ogni 15 s (`scalper_session.py:889-941`) | `fixture_predictions` (1X2 ML + Poisson) una volta all'armo, solo in modalita' bias (`scalper_session.py:409`, `bias_resolver.py:79-90`); `hazard_atlas_v1.json` solo per theta | Maker [SOGLIA]; bias [AVANZATO-lite]: consenso ML+Poisson con edge 0,02-0,20 (`bias_resolver.py:29-30,193-204`); theta: hazard 3' <= 0,085 (`theta_bot.py:749`); sniper [SOGLIA] | Tick fissi | Atlante del 15/07 (21 leghe, 54.009 partite); P 1X2 grezze non calibrate |
| **xhedge** | Book CS dalla cache del recorder, ordini da `betfair_live_orders`, ogni 5 s (`xhedge_worker.py:56,94`) | Nessuna | Minimax deterministico sul P&L per scoreline, senza P e senza commissione (`trading/xhedge.py:98-208`) | - | - |
| **Feed unico** `scan_feed.py` | E' un LETTORE di `safe_strategy_scan` con TTL 1 s (`scan_feed.py:66,401`); lo scrittore e' `safe_strategy/service.py`. Ramo pre-KO O/U 3.5/4.5 per Mike: `service.py:177,221,705-719` | Nessuna tabella di analisi | - | - | - |

---

## 2. INPUT LIVE (dettaglio per bot)

### 2.1 Scrittore unico: lo scanner di Safe (`Betfair/safe_strategy/service.py`)

**Catalogo e quote**
- Catalogo MATCH_ODDS da -6 h a +14 h, refresh ogni 300 s, massimo 1000 mercati (`service.py:114,144-157`).
- Quote via Exchange Stream (conflate 1 s, `stream.py:22,238`), tetto di 180 mercati in stream, ripiego REST a chunk da 25 (`service.py:139-140,988-995`).
- Un mercato senza prezzo da 20 s torna al REST (`service.py:190`).

**Punteggi e stato di gioco**
- IPS `scoresAndBroadcast` ogni 2 s, a chunk da 50 (`service.py:128,141,1013-1064`); timeline ogni 30 s (`:132`).
- Corner e gialli -> `pressure_index` (`pressure.py:112-140`; scritto a `service.py:1582`).
- **Nessun tiro, xG o attacco pericoloso: l'IPS non li porta.**

**pre_ko e ramo O/U pre-partita**
- `pre_ko`: 1X2 aggiornato da KO-15' e congelato al primo tick in gioco (`service.py:868`).
- Ramo O/U pre-KO per Mike: `SAFE_PRE_KO_OU_HOURS` (`service.py:177,221,705-719`).

**Scrittura**
- Upsert di `safe_strategy_scan` con throttle 2,5 s per evento (`service.py:136`; `safe_strategy/db.py:136,166`).
- Canale WS 47336 solo con `SAFE_SCAN_CANALE` (`service.py:88-113`).

**Latenza reale di un dato**
- Per Omega, Mike e Safe va dall'IPS (+ circa 3 s di ritardo IPS, `scan_feed.py:66`) alla scrittura (2,5 s) e poi alla lettura del bot (Omega: cache 2 s, ciclo 20 s; Mike: 4 s; Safe: 2 s).
- Con i canali spenti di serie, **Omega puo' decidere su uno stato vecchio fino a circa 25 s** (`DECISION_MAX_AGE_S` 25, `omega_service.py:85`).
- Il 23/09 l'utente ha ordinato: «all'avvio tutto passa dai canali al ms, poll DB solo come ripiego». Oggi di serie NON e' cosi' per Omega, Mike e Safe (`OMEGA_LEGGE_CANALE`, `MIKE_LEGGE_CANALE`, `SAFE_BOT_LEGGE_CANALE` spenti di serie).
- Valore effettivo nel `.env`: NON VERIFICATO.

### 2.2 Omega
- `_feed_riga_cached` (`omega_service.py:384`) e `_live_state_for` (`:964-993`).
- Campi usati: minute, score, red, score_raw (gialli), cs, ht, ou, pre_ko.
- Ripiego del punteggio: `live_now` (`omega_db.py:585-600`), IPS REST per le missioni (`omega_market.py:504`).
- Libro di ripiego: REST (`omega_service.py:1595-1611`).
- Cadenze in `omega_config.py:35,158,220`.

### 2.3 Mike
- `fetch_scan_rows` (`mike/db.py:462`), cache 4 s (`config.py:303`).
- O/U estratti da `feed.py:97,120,144`.
- P implicite: `implied_p4` = P(O3.5) - P(O4.5) (`feed.py:159`), `market_totals` (`feed.py:175`).
- Pressione da `pressure_from_payload` (`dossier.py:298-301`).

### 2.4 Safe
- Bot ogni 2 s (`bot_service.py:127`), opportunita' ogni 10 s (`:153`), freschezza obbligatoria all'ingresso (`_row_is_fresh`, circa `bot_service.py:5912`).

### 2.5 4 bot tennis e scalper
- Stream flumine in-process: tennis `tennis_runner.py:412-414`; scalper `scalper_session.py:600-611`.
- Il punteggio dello scalper arriva da `live_now` ogni 15 s, cioe' **piu' lento della scan**
  (`scalper_session.py:889-941`). `live_now` lo scrive il runner calcio ogni 5 s (`runner.py:349,376`; `config_stream.py:32`).
- xhedge: book CS dal recorder ogni 5 s (`xhedge_worker.py:56`; `config_stream.py:289`).

---

## 3. INPUT STORICI E MODELLI: quali tabelle si usano davvero

### 3.1 Mappa tabella -> bot

| Tabella / file | Chi lo legge (file:riga) | Uso | Stato |
|---|---|---|---|
| `fixture_predictions.tactical_engine_json` / `db_json_analisi.inputs.lambda_*` | `stream/db.py:211-252`, chiamato da Omega `omega_service.py:1063`, Mike `mike/db.py:514`, runner `runner.py:455`; Safe legge solo `db_json_analisi.inputs` (`bot_service.py:6221-6240`, **non** il tattico) | Prior lambda pre-partita | Fresca (3.692 righe negli ultimi 7 gg). Copertura lambda 28-33% (M2); tattico 7,7% (`PROGETTO_OMEGA_V3:105`) |
| `fixture_predictions.db_json_analisi` (markets, dc_rho) | Mike `dossier.py:63-72`; advisor di Omega (solo UI) | Mike: rho decisionale; `p_under35_cal` scartato | Idem |
| `fixture_predictions.model_predictions_json` | Scalper `scalper_session.py:409`, `bias_resolver.py:79-90` | Bias 1X2 del maker | Fresca; P grezze |
| `fixture_predictions.raw_json_odds`, `percent_*`, `flat_summary` | **nessun bot** | - | Fresca, inutilizzata |
| `omega_minute_transitions` (RPC `get_omega_minute_ft`) | Omega `omega_db.py:1016`, veto `omega_v3.py:668` | Veto empirico Wilson (K=500, n >= 200) | **Ferma all'11/09** secondo M2 (`CRONOSTORIA.md:254`); decisione utente n. 11 aperta (`CRONOSTORIA.md:277`) |
| `omega_ht_ft_transitions` (RPC `get_omega_ht_ft`) | Omega (ripiego), Mike `dossier.py:148` -> `blend_totals` (`engine.py:1147`) | Distribuzione empirica dei gol totali | Idem |
| `get_market_frequency` (RPC) | Advisor di Omega (UI) | - | - |
| `omega_events.model`, `omega_trades.meta.model` | Omega, Safe | Lambda salvate | - |
| `analytics_signals` | **nessun bot** | - | Fresca (737.702 righe negli ultimi 7 gg) |
| `poisson_calibration` | **nessun bot** (ne esiste una copia statica in `money_management.py:194`, che serve alla reportistica, non ai bot) | - | 21/09 |
| `ml_post_calibration` | **nessun bot** | - | Oggi |
| `direction_pagella` | **nessun bot** | - | Oggi |
| `engine_signals` | **nessun bot** (solo sync in `betfair_report_manager.py:245`) | - | FERMA (kickoff massimo 17/09) |
| `match_odds` | **nessun bot** (offline in Ai Engine) | - | 92,5 M righe; freschezza NON VERIFICATA (Q3) |
| `betfair_market_odds` | Solo tool offline di Omega (`tools/m2_pesi.py:159`) | - | Ferma all'11/09 secondo M2 |
| `match_team_stats`, `match_lineups`, `match_player_stats` | **nessun bot** | - | Vedi nota Q8 sui conteggi |
| `standings`, `injuries` | **nessun bot** | - | VUOTE |
| `hazard_atlas_v1.json` | Mike (`dossier.py:79-88`), theta (`hazard_atlas.py:36-38`) | Hazard 3' | 15/07, 21 leghe |
| `hazard_atlas_v2.json` | Advisor di Omega (UI); `selezione.py:50` (filtro esatto SPENTO, `engine.py:217`) | - | 15/07 |
| `inplay_intensity_by_league.json` | `live_engine.py:62-70` (Safe, ripieghi di Omega e Mike) | Moltiplicatori di stato gara e rossi | Commit del 29/06; in V3 di Omega NON e' collegato (i rossi sono ignorati, `omega_v3.py:266-302`) |
| `dc_rho_by_league.json` | `live_engine_pro.py:37,86` | rho per lega | 15/09, solo 20 leghe (resto -0,13 fisso) |
| `dynamic_cal.json` | `live_engine_pro.py:38` | **SPENTO** (`live_engine_pro.py:113`) | 21/09 |
| `opp_calibration.json` | `opportunity.py:349-362`, applicato solo alle opportunita' (`opportunity.py:859`) | Isotonica | 10/09, 32 partite |
| `data/parametri_vincenti_2026-09-16.json` | `omega_proposte.py:110-138` | Parametri del modello V3 | 16/09, 2.018 partite |
| `data/k_misurato_2026-09-16.json` | Caricato ma passato come `k_tab=None` (`omega_service.py:1470-1481`, scelta dichiarata del 17/09) | Solo referto | - |
| `league_trust_scores.json` | nessuno | - | 30/03 |
| `serve_data.csv` (tennis) | `tennis_opportunity.py:234-242` | Hold per giocatore | **ASSENTE** |

### 3.2 Difetti di collegamento (dati gia' calcolati e poi buttati)
1. **Mike**: `p_under35_cal` (P calibrata dell'Under 3.5 dal Poisson) viene calcolata e poi non la
   legge nessuno (`mike/dossier.py:72`, grep: presente solo in dossier). `p_over45_cal` non viene
   mai valorizzata (`dossier.py:54`). `p4_model` va solo in telemetria.
2. **Safe**: il controincrocio con l'atlante hazard e' scritto (`opportunity.py:630-670`) ma
   `OpportunityModel` viene costruito senza `atlas` (`bot_service.py:3787,8930`). Risultato:
   «atlante assente» sempre, per cui il controllo e' morto in produzione.
3. **Safe**: le P con cui si decide l'USCITA vengono dal `book` grezzo (`bot_service.py:3869-3872`).
   `calibrate` si applica solo alle opportunita' (`opportunity.py:859`).
4. **Safe**: `_lambdas_from_fixture` legge solo `db_json_analisi.inputs`, mentre `stream/db.py:235`
   legge prima `tactical_engine_json`. Le due catene non sono coerenti.
5. **Omega**: in ingresso P_nostra = max(fusa, empirica). In uscita `_p_del_bancato`
   (`omega_proposte.py:406-438`) usa la P grezza del modello: si entra e si esce con due P diverse.
6. **Omega**: la catena delle lambda mette `fixture` PRIMA del mercato (`omega_service.py:1060-1084`).
   M2 ha misurato che invertire l'ordine migliora la gamba HT con IC che esclude 0
   (`CRONOSTORIA.md:252-253`; decisione utente n. 12 aperta, `CRONOSTORIA.md:278`).
7. **Omega**: nel ripiego `pre_ko` il totale gol e' dedotto dal solo 1X2 (`omega_model.py:131-142`,
   `total_goals_from_1x2`), anche se una linea O/U pre-partita e' gia' disponibile in
   `fixture_predictions.raw_json_odds`.
8. **Omega V3** ignora i cartellini rossi (`omega_v3.py:266-302`) anche se il feed li porta
   (`omega_service.py:978-979`) e i coefficienti per lega esistono gia' (`inplay_intensity_by_league.json`).
9. **tennis_pro**: `surface` vale "grass" di default (`tennis_pro_bot.py:105`) e nessun runner la
   passa (grep "surface" in `tennis_live/`: 0 risultati). Quindi `_lay_rev` e' False e 3 setup su 6
   sono spenti di fatto.
10. **tennis**: `p_match` di Markov e' calcolato a ogni tick ma solo per la UI (`tennis_runner.py:314`).

---

## 4. ALGORITMI: che cosa decide davvero

### 4.1 Omega V3 (`strategy_version` 3, `omega_config.py:231`)

**Mercato e gambe**
- Mercato CORRECT_SCORE, due gambe: A dal 1' al 44', B dal 46' all'85' sul minuto reale (`omega_config.py:274-277`).

**Lambda pre-partita (catena, `omega_service.py:1027-1142`)**
1. fixture (tattico, poi Poisson);
2. `omega_events.model`;
3. 1X2 pre_ko;
4. trade precedente;
5. lambda implicite CS/O/U live;
6. O/U live;
7. ripiego scaduto.

**Modello [AVANZATO]**
- Prior Gamma(a = 13,34) sulle lambda; posteriore coi gol visti; predittiva NegBin fino al 94'.
- Profilo Dixon-Robinson exp(c1*u + c2*u^2) con c1 = 0,41; tau DC solo a 0-0; griglia 10x10 (`omega_v3.py:101-340`).
- Fusione: pool logaritmico in logit tra modello e mid devigato del book CS, con peso per fascia
  [<=1%: 1,0; <=2%: 0,65; <=5%: 0,85; <=10%: 0,9; resto 0,6] (`omega_v3.py:410-467`).
- Veto: P_nostra = max(P fusa, limite superiore Wilson empirico) (`omega_v3.py:668`).

**Cancello [SOGLIA]** (`omega_v3.py:653-705`)
- P_nostra <= 2%.
- p_imp = (1-c)/(L-c) in [1%, 2%], cioe' lay circa 47,5-95.
- P_nostra <= p_imp / 1,11.
- Distanza >= 2 gol; liquidita' >= 1 EUR; liability di gamba <= 95.
- Fra i candidati sceglie la P_nostra MINIMA, non l'EV massimo (l'EV di `omega_v3.py:535-541` viene solo registrato).

**Stake e uscita**
- Stake 1 EUR fisso, FOK.
- Uscita: proposte con EV di tenere contro bloccabile netto commissione (`omega_v3.py:792-1067`).

**Contesto misurato** (`CRONOSTORIA.md:230-271`): l'edge di Omega sta nel PREZZO (bias di fascia),
non nel modello. Il market making passivo v4 e' stato fermato dal criterio di arresto
(selezione avversa 1,62 > 1,27).

### 4.2 Mike (dettaglio al §1)

**Ingresso [SOGLIA]** senza nessuna P, anche se il dossier la calcola.

**Uscite [AVANZATO]**
- Uscita in perdita (`engine.py:1136-1174`): chiude se `cv_net >= EV_hold - premio`, con
  EV_hold = somma su t di P(t)*PnL(t) e P = media modello/empirico (senza nessuno dei due, il mercato).
- Premio = 10% x P4 x base (`config.py:254`).
- DIVERGENZA documentale: `COSTITUZIONE_MIKE.md:193` dice 50%, il codice 10% (dal sotto-audit, non
  riverificato da me riga per riga).

### 4.3 Safe (dettaglio al §1)

**Ingresso**: 100% [SOGLIA], come da `SPEC_STRATEGIA_S.md`. Le eccezioni dell'utente sono chiuse:
nessun limite alla quota di banca e stake fisso.

**Condizioni della SPEC non implementate come controllo attivo**
- «La favorita deve avere il controllo del gioco»: `requireControl` e' spento (`engine.py:902`) e il
  segnale disponibile e' solo corner + gialli.
- «Scontri diretti senza troppi 2-2/3-3, difesa avversaria solida» (esatto): `requireSelection`
  e' spento (`engine.py:217`).

Sono i due punti dove i dati storici hanno un aggancio naturale, e restano decisioni dell'utente.

### 4.4 Tennis, scalper, xhedge
Dettaglio al §1. L'unico uso probabilistico e' il bias 1X2 (P grezze) e l'hazard di theta. Il
docstring di theta dichiara «theta classico EV- in tutte le 18 varianti» (`theta_bot.py:9-13`).

---

## 5. MIGLIORAMENTI (con dati gia' in nostro possesso)

Vincoli validi per tutti i punti:
- Le strategie sono intoccabili: ogni punto e' una PROPOSTA che richiede l'ordine dell'utente.
- Regola del 13/09: le letture DB possono solo diminuire. Ogni proposta dichiara il delta di letture.
- Validazione, identica per tutti:
  1. banco comune `python -m Betfair.stream.backtest.certifica <bot> ...` sulle registrazioni
     `_live_raw/`, confronto A/B codice attuale contro variante sugli stessi scenari;
  2. poi, se serve, misura offline fuori campione con IC (split per lega/data, come in M2);
  3. poi paper;
  4. poi live.
- «IC che esclude 0» e' il criterio gia' usato in M2 e M4-M6.

### 5.1 Omega

| # | Miglioramento | Dato | Dove | Rischio | Validazione |
|---|---|---|---|---|---|
| O1 | Invertire la catena delle lambda: mercato (pre_ko) prima di fixture | quote pre_ko del feed | `omega_service.py:1060-1084` | Basso. Zero letture in piu' (anzi meno: la fixture si legge solo se manca il mercato). Gia' misurato in M2 (HT, IC esclude 0) | Banco `certifica omega` A/B, stessi scenari; decisione n. 12 gia' posta all'utente |
| O2 | Ricostruire le transizioni per minuto e HT/FT (ferme all'11/09) + pg_cron alle 04:00 UTC | `matches` + `match_events` | Job `migrations/omega_models_v3.sql:81-256`; consumo `omega_db.py:1016` | Basso (dato piu' fresco, stesso algoritmo); carico DB notturno | Q4 per la freschezza; banco A/B sul veto (conteggio `scartati` per motivo) |
| O3 | Totale gol del ripiego pre_ko dalla linea O/U 2.5 bookmaker invece che dal solo 1X2 | `fixture_predictions.raw_json_odds` (stessa riga gia' letta da `stream/db.py:224`: aggiungere la colonna alla select = 0 richieste in piu') | `omega_model.py:131-142` | Medio: bookmaker != Betfair, margine da devigare | Offline: log-loss dei CS finali contro la catena attuale sulle stesse 657 partite di M2; poi banco |
| O4 | Stessa P in ingresso e in uscita (fusa + empirica anche in `_p_del_bancato`) | nessun dato nuovo | `omega_proposte.py:406-438` | Basso; cambia le proposte d'uscita | Banco: confronto delle proposte generate sugli stessi scenari |
| O5 | Rossi nel V3 (moltiplicatori per lega) | `inplay_intensity_by_league.json` (esistente) o `match_events` (rossi col minuto) | `omega_v3.py:285-331` | Medio: pochi rossi, rischio overfitting per lega -> usare solo il globale | Log-loss fuori campione sui CS delle partite con rosso (campione piccolo: IC largo, dichiararlo) |
| O6 | Calibrazione della coda (M2: usciti/attesi 0,76-0,79 sulla FT) | `betfair_market_odds` + esiti `matches` | `omega_model.load_calibrator` (`omega_model.py:375`, oggi `model_calibration='off'`, `omega_config.py:74`) oppure un fattore prima di `omega_v3.py:668` | Medio-alto: tocca il cuore del cancello | Solo con IC; il banco non basta (pochi esiti) |

### 5.2 Mike

| # | Miglioramento | Dato | Dove | Rischio | Validazione |
|---|---|---|---|---|---|
| M1 | Usare `p_under35_cal` (gia' calcolata) come VETO/EV quando la posizione passa dal pre-match al live (HOLD/PERSIST), cioe' dove Mike prende rischio d'esito vero | `fixture_predictions.db_json_analisi.markets_calibrated.over_3_5` (gia' letta) | Innesto `engine.py:2289-2316`; spostare `build_prematch` prima dell'armamento (`service.py:2672-2677`) | Basso sulle letture (0 in piu', solo anticipate); medio sulla copertura: disponibile solo per il 28-33% delle partite | Banco `certifica mike`: quante HOLD evitate e P&L sugli scenari con gol precoce |
| M2 | Popolare `p_over45_cal` e usarla come terza fonte in `blend_totals` | `markets_calibrated.over_4_5` (formato della chiave NON VERIFICATO: Q6) | `dossier.py:54,69-72`; `engine.py:1147` | Basso | Banco A/B sull'uscita in perdita |
| M3 | Prior di lega della P(4 gol esatti) come pavimento di P4 | RPC `get_market_frequency` (gia' pronta, `omega_db.py:763`) oppure `omega_ht_ft_transitions` | `engine.py:1159` (p4_floor) | Basso; +1 RPC per lega, in cache | Banco |
| M4 | Tarare `pre_green_ticks` e la banda 1,30-3,00 sulla deriva pre-KO dell'Under 3.5 | **registrazioni `_live_raw/` e `betfair_market_odds`**, NON `match_odds` (che sono bookmaker) | `config.py:119-125` | Medio (parametri di strategia) | Misura offline dei fill della lay a -2 tick per banda di prezzo, poi banco |
| M5 | Riallineare la documentazione: premio 50% in `COSTITUZIONE_MIKE.md:193` contro 10% nel codice | - | - | Nullo | Decisione dell'utente su quale sia giusto |

### 5.3 Safe calcio e tennis

| # | Miglioramento | Dato | Dove | Rischio | Validazione |
|---|---|---|---|---|---|
| S1 | Collegare l'atlante al modello (il controllo hazard e' gia' scritto) | `hazard_atlas_v2.json` (file locale) | `bot_service.py:3787,8930` (passare `atlas=`) | Basso: tocca solo confidenza/scarto delle OPPORTUNITA' (proposte), 0 letture DB | Banco: proposte generate e scartate sugli stessi scenari |
| S2 | Calibrare le P d'USCITA (oggi grezze) | `opp_calibration.json` rifatta su PIU' registrazioni (oggi 32 partite del 10/09; le `_live_raw/` sono cresciute), oppure `poisson_calibration` per lega/mercato | `bot_service.py:3869-3872` (applicare `calibrate`) | Medio: una calibrazione su 32 partite puo' peggiorare; `dynamic_cal` e' pre-match e fu spenta apposta (`live_engine_pro.py:110-113`) | Brier/log-loss fuori campione per famiglia e minuto (lo stesso `tools/validate_opportunity.py`), poi banco |
| S3 | Coerenza della catena lambda: `_lambdas_from_fixture` legga anche `tactical_engine_json` come `stream/db.py:235`; misurare la quota di partite su «default» (17/38 nel backtest del 10/09) | `fixture_predictions` (stessa riga) | `bot_service.py:6221-6240`, matcher `:6193` | Basso | Q2 (quota lambda disponibili) + conteggio `source` nelle opportunita' (Q7) |
| S4 | Ripiego di `pre_ko` per Base/Punta (senza pre_ko la favorita non e' definita e la strategia non entra) | 1X2 bookmaker da `fixture_predictions.raw_json_odds` (o `match_odds`) | `engine.py:600,744,925-952` | **Alto**: cambia l'universo d'ingresso di una strategia della SPEC (favorita 1,4-1,8 e sfavorita 4-8 sono prezzi Betfair) | Solo su ordine dell'utente; banco sulle registrazioni senza pre_ko |
| S5 | «Controllo del gioco» (SPEC Base, oggi spento): tarare `controlMin` e i pesi corner/gialli contro l'esito | `match_events` (corner e cartellini col minuto) + esiti | `pressure.py:41-43`, `engine.py:190,902` | Alto (overfitting; segnale povero: niente tiri) | Offline con IC; resta una decisione dell'utente accenderlo |
| S6 | Tennis: hold per giocatore invece di 0,75 fisso | **Nessun dato tennis storico nel DB** (solo tabelle operative) -> non realizzabile coi dati attuali | `tennis_opportunity.py:234-257` | - | - |

### 5.4 4 bot tennis

| # | Miglioramento | Dato | Dove | Rischio | Validazione |
|---|---|---|---|---|---|
| T1 | Passare la superficie reale a tennis_pro (oggi 3 setup su 6 spenti) | `tennis_markets.competition_name` (gia' letto, `tennis_bot_service.py:140-141`) | `tennis_pro_bot.py:105-108` | Medio: accende 3 setup mai certificati | Banco `certifica` per il bot tennis_pro sulle registrazioni tennis, a superficie per superficie |
| T2 | `p_match` (gia' calcolato) come veto su flb e pro (non laiare un favorito <= 1,10 se il Markov lo da' > 1/1,10 + commissione) | nessuno (calcolo gia' presente, `tennis_runner.py:271-314`) | `tennis_flb_bot.py:311`, `tennis_pro_bot.py:441` | Medio: l'hold stimato dai break e' grezzo | Banco A/B |

### 5.5 Scalper calcio e xhedge

| # | Miglioramento | Dato | Dove | Rischio | Validazione |
|---|---|---|---|---|---|
| X1 | Bias del maker su P calibrate e con concordanza misurata | `ml_post_calibration`, `poisson_calibration`, `direction_pagella` (hit-rate per motore x mercato x lega x fascia) | `bias_resolver.py:79-90,193-204` | Medio; +1 lettura all'armo per partita | Banco `scalper_calcio` sulle 2 registrazioni dove entra (35797769, 35777617): troppo poche, quindi serve prima la misura offline della pagella |
| X2 | Rigenerare l'atlante hazard (fermo al 15/07, 21 leghe) su tutte le stagioni | `match_events` | Offline; consumato da `hazard_atlas.py:75`, Mike `dossier.py:79`, theta `theta_bot.py:749` | Basso (stesso algoritmo) | Confronto della curva vecchia contro la nuova sulle leghe comuni; banco su theta e Mike |
| X3 | xhedge pesato con P (EV/CVaR) invece del minimax | griglia CS Poisson (`db_json_analisi`) + punteggio live | `trading/xhedge.py:98-208` | Medio: e' uno strumento manuale | Banco solo dopo la decisione dell'utente |

### 5.6 Ciò che NON conviene fare (misurato o dedotto dai dati)
- Aggiungere `analytics_signals`, `direction_pagella`, team stats o lineups alle lambda di Omega e Mike: M2 ha misurato peso 0 fuori campione (`CRONOSTORIA.md:250-252`).
- Usare `freq_*`/`delay_*` come probabilita': sono ritardi di mercato di lega, al massimo un VETO di regime.
- Agganciare `engine_signals`: e' fermo e storicamente ha ROI negativo come segnale.
- `standings` e `injuries`: vuote.

---

## 6. DATI MANCANTI O ROTTI: cosa perde ogni bot

| Dato | Stato | Chi perde e cosa |
|---|---|---|
| `engine_signals` (fermo, kickoff massimo 17/09) | FERMO | **Nessun bot** lo legge. Perdono le colonne «decisione/piazzamento» di `analytics_signals` (`migrations/analytics_signals.sql:69`) e la UI Direzione/analytics. Impatto sui bot: nullo |
| `standings`, `injuries` | VUOTE | **Nessun bot** le legge oggi. Bloccano pero' ogni feature futura su forma, classifica e assenze (e i job `standings_backfill.py` e `injuries_backfill.py` esistono: perche' sono vuote e' NON VERIFICATO) |
| `poisson_calibration` (ultimo 21/09) | 3 gg | Nessun bot la legge direttamente. La P calibrata che Mike calcola (`markets_calibrated`) viene da `fixture_predictions` e dipende da essa, ma Mike la butta (§3.2.1) |
| `omega_minute_transitions` / `omega_ht_ft_transitions` | Ferme all'11/09 (M2; da riverificare, Q4) | **Omega**: veto empirico su 13 gg di storico in meno (sulle leghe appena ripartite, stagione 26/27, questo pesa). **Mike**: `p_total_emp` dell'uscita in perdita |
| `hazard_atlas_v1/v2.json` | 15/07 | **Mike** (hazard, timing della copertura), **theta**; stagione 26/27 assente |
| `opp_calibration.json` | 10/09, 32 partite | **Safe**: opportunita' (e la calibrazione d'uscita, se la si collega: S2) |
| `betfair_market_odds` (quote Betfair pre-match) | Ferma all'11/09, copertura 3% (M2) | **Omega**: impossibile misurare k e la calibrazione della coda su dati nuovi (decisione utente n. 10: job giornaliero `betfair_full_odds.py`) |
| `dc_rho_by_league.json` | 20 leghe | Tutti i modelli Poisson: rho = -0,13 fisso fuori da quelle 20 (il fit globale da' -0,029: `PROGETTO_OMEGA_V4:402`) |
| `serve_data.csv` | ASSENTE | **Safe tennis**: hold 0,75 per tutti |
| Lambda fixture | 28-33% delle partite (M2) | **Safe** (17/38 su default nel backtest del 10/09), **Mike** (senza dossier: uscita in perdita «a mercato» o a regola fissa) |
| Canali al ms spenti di serie | - | **Omega** decide fino a circa 25 s dopo l'evento; contrasto con l'ordine del 23/09 |

---

## 7. QUERY SQL PER IL COORDINATORE (sola lettura)

Nota: i tipi JSON (json, jsonb o text) non li ho verificati. Se una colonna e' text serve `::jsonb`.

```sql
-- Q1 Copertura delle lambda per le partite delle prossime 48 h (quanto i bot possono usare fixture_predictions)
SELECT count(*) AS fixture,
       count(*) FILTER (WHERE (tactical_engine_json::jsonb ->> 'lambda_home') IS NOT NULL) AS con_tattico,
       count(*) FILTER (WHERE (db_json_analisi::jsonb -> 'inputs' ->> 'lambda_home') IS NOT NULL) AS con_poisson,
       count(*) FILTER (WHERE (db_json_analisi::jsonb -> 'markets_calibrated' -> 'over_3_5') IS NOT NULL) AS con_o35_cal,
       count(*) FILTER (WHERE (db_json_analisi::jsonb -> 'markets_calibrated' -> 'over_4_5') IS NOT NULL) AS con_o45_cal,
       count(*) FILTER (WHERE raw_json_odds IS NOT NULL) AS con_quote_bookmaker
FROM fixture_predictions
WHERE fixture_date >= now() AND fixture_date < now() + interval '48 hours';

-- Q2 Stessa copertura sulle partite su cui i bot hanno operato davvero (omega_events -> fixture)
SELECT count(DISTINCT e.event_id) AS eventi,
       count(DISTINCT e.event_id) FILTER (WHERE (fp.db_json_analisi::jsonb -> 'inputs' ->> 'lambda_home') IS NOT NULL) AS con_lambda
FROM omega_events e LEFT JOIN fixture_predictions fp ON fp.fixture_id = e.fixture_id
WHERE e.created_at > now() - interval '14 days';

-- Q3 Freschezza e copertura di match_odds (quote bookmaker pre-match)
SELECT max(snapshot_time) AS ultimo_snapshot,
       count(DISTINCT fixture_id) FILTER (WHERE snapshot_time > now() - interval '7 days') AS fixture_7gg
FROM match_odds WHERE snapshot_time > now() - interval '30 days';

-- Q4 Freschezza delle tabelle di transizione di Omega (colonna built_at secondo M2: verificare il nome)
SELECT 'minute' t, max(built_at) FROM omega_minute_transitions
UNION ALL SELECT 'ht_ft', max(built_at) FROM omega_ht_ft_transitions
UNION ALL SELECT 'betfair_market_odds', max(run_date)::timestamptz FROM betfair_market_odds;

-- Q5 Calibrazione reale del Poisson sull'Over 3.5 e 4.5 (utile a Mike M1/M2), per decile di prob
--     (i nomi di market e selection vanno verificati con un SELECT DISTINCT prima)
SELECT market, selection, width_bucket(prob, 0, 1, 10) AS decile,
       count(*) n, round(avg(prob)::numeric, 3) p_media, round(avg(hit::int)::numeric, 3) hit_rate
FROM analytics_signals
WHERE engine = 'poisson' AND settled AND market IN ('over_3_5', 'over_4_5')
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;

-- Q6 Formato delle chiavi di markets_calibrated (per M2 di Mike)
SELECT jsonb_object_keys(db_json_analisi::jsonb -> 'markets_calibrated') k, count(*)
FROM fixture_predictions WHERE fixture_date > now() - interval '3 days' GROUP BY 1 ORDER BY 2 DESC;
SELECT db_json_analisi::jsonb -> 'markets_calibrated' -> 'over_4_5'
FROM fixture_predictions WHERE fixture_date > now() - interval '3 days' LIMIT 3;

-- Q7 Da dove vengono le lambda di Safe nelle opportunita' (source dichiarato nel body; chiave da verificare)
SELECT coalesce(payload ->> 'lambda_source', payload -> 'body' ->> 'source') AS fonte, count(*)
FROM safe_strategy_opportunities GROUP BY 1 ORDER BY 2 DESC;

-- Q8 Coerenza dei conteggi (il brief riporta match_team_stats 19.518 e match_player_stats 23.875;
--    DOCUMENTAZIONE_DATABASE.md:26-27 riporta 6,5 M e 5,6 M): tabella potata o conteggio diverso?
SELECT (SELECT count(*) FROM match_team_stats) team_stats,
       (SELECT count(DISTINCT fixture_id) FROM match_team_stats) team_stats_fixture,
       (SELECT count(*) FROM match_player_stats) player_stats;

-- Q9 Hit-rate della pagella per i mercati che i bot trattano (supporto a X1 e al veto)
SELECT engine, market, selection, prob_bucket, n, hit_rate, base_rate
FROM direction_pagella WHERE league_id = 0 AND market IN ('1x2', 'over_2_5', 'over_3_5')
ORDER BY market, selection, engine, prob_bucket;

-- Q10 Ultimo valore scritto dei parametri effettivi dei bot (i default del codice possono essere sovrascritti)
SELECT 'omega' b, params FROM omega_control
UNION ALL SELECT 'mike', params FROM mike_control
UNION ALL SELECT 'safe', params FROM safe_strategy_control;
```

---

## 8. NON VERIFICATO
- Valori nel `.env`: `OMEGA_LEGGE_CANALE`, `MIKE_LEGGE_CANALE`, `SAFE_BOT_LEGGE_CANALE`, `SAFE_SCAN_CANALE`, `SAFE_PRE_KO_OU_HOURS`, `PUNTEGGI_CANALE`.
- Parametri salvati dall'UI in `*_control.params` (Q10): qui sono riportati i DEFAULT del codice.
- Freschezza reale di `omega_minute_transitions`, `omega_ht_ft_transitions`, `betfair_market_odds`
  e `match_odds` (Q3, Q4): «11/09» viene da M2 del 17/09, non rimisurato.
- Copertura reale delle lambda e di `markets_calibrated` sulle partite di oggi (Q1, Q2, Q6).
- Schema reale dei JSON (tipi, chiavi di `markets_calibrated.over_4_5`) e nomi `market`/`selection` in `analytics_signals`.
- Divergenza `COSTITUZIONE_MIKE.md:193` (50%) contro `config.py:254` (10%): riportata dal
  sotto-audit, riga della costituzione non riletta da me.
- Possibile doppio conteggio dei gol visti in Omega V3 quando le lambda vengono da ripieghi gia'
  condizionati allo stato (`omega_v3.py:285-292`): inferenza dalla lettura, non provata.
- Perche' `standings` e `injuries` sono vuote pur avendo job di backfill.
- Conteggi di `match_team_stats`/`match_player_stats` (Q8).
- Nessun replay del banco eseguito: per ordine del 24/09 i replay li lancia solo il coordinatore.
