# V2 - Verifica indipendente dei reperti Poisson MA2, M1, M3 (09/10/2026)

Verificatore indipendente, sola lettura. Repo a `852b717f` (09/10 13:01). Nessun file di produzione, test, DB o app
toccato; nessun processo lasciato acceso. DB: 2 SELECT leggere (finestre di 1 giorno, LIMIT 1000, colonne minime).
Sonde mie (rieseguibili, leggono solo `lavori/sonde/m_dati.json`): `verifica_coordinatore/v2_indip.py`,
`v2_slope2.py`, `v2_o35.py`. Rilancio: `.venv/Scripts/python.exe -I verifica_coordinatore/<sonda>.py lavori/sonde/m_dati.json`.

## Sintesi

| Reperto | Verdetto | In una riga |
|---|---|---|
| MA2 | **CONFERMATO, ma NON NUOVO** | Il codice non usa quote; RPS +0,0156 riprodotto esattamente; vale anche sull'Over 3.5 di Mike. Gia' scritto in CRONOSTORIA 02/10 h18:05 (`AUDIT_2026-10-02/AUDIT_ML_POISSON.md`, 25.330 partite). |
| M1 | **CONFERMATO, RIDIMENSIONATO nell'impatto, NON NUOVO** | 160/1.519 Poisson e 200/1.510 ML dopo il KO riprodotti; ancora vivo OGGI (22/334). Ma non tocca i bot (la riga non esiste al KO): contamina solo analytics/UI e calibrazione. Gia' noto 02/10 (11 % / 13 %). |
| M3 | **RIDIMENSIONATO (meta' vera, meta' sbagliata)** | Grezzo troppo estremo sui mercati GOL confermato (anzi peggio: pendenza 0,47 su n=1.519); ma "lo scalper usa il grezzo" e' fuori bersaglio: lo scalper usa SOLO l'1X2, dove il grezzo e' quasi calibrato (pendenza H 0,95, A 0,90). Il "calibrato 0,81" di V2 non si riproduce (0,63). |

## MA2 - Il Poisson non usa le quote e perde contro di esse

**(1) Codice.** `Prediction/today_predictions_backfill.py:1589-1590` (riletto):
`lambda_home = max(0.05, league_home_avg * home_attack * away_def)`, idem away. Gli ingressi (:1418-1588) sono solo
medie di lega della stagione (`_build_match_cache`, :1210-1240, tabella `matches`), forma 5/10/15 con shrink k=8 e
blend gol/xG 0,6/0,4. Nessuna quota entra nella funzione `compute_db_json_analisi`. Le quote (`raw_json_odds`) sono
scritte dallo stesso batch ma in un ramo separato. CONFERMATO.

**(2) Produzione e consumatori** (git grep su `db_json_analisi|markets_calibrated`):
- Mike: `Betfair/mike/dossier.py:102-103` legge `markets_calibrated` (ripiego al grezzo se assente) -> `p_under35_cal`
  -> veto U3.5 ACCESO di default (`Betfair/mike/config.py:152`, soglie isotoniche :153-157, `engine.py:3530-3600`).
  Nota: il veto NON confronta "P modello > P quota" direttamente: confronta P con una soglia per quota, tarata
  con curva isotonica (P dichiarata -> Under osservato; MISURA_PUNTO8 25/09). La formula del reperto ("modello >
  mercato = valore") e' quindi una semplificazione; il nocciolo resta: se P non aggiunge informazione alle quote,
  il veto filtra con un numero meno informato del prezzo.
- Omega/Safe: lambda da `stream/db.py:240-285` (tattico, poi `db_json_analisi.inputs`); Omega advisor
  `omega_advisor.py`, `omega_db.py:767`; Safe `safe_strategy/opportunity.py:231`.
- Scalper: `Betfair/stream/scalper/bias_resolver.py:87` `markets["1x2"]` GREZZO (solo in modalita' bias/both).
- Foglio: `Betfair/betfair_report_manager.py:612`.
- Batch: `.github/workflows/today_predictions_backfill.yml` (dal 09/10 senza cron, terzo anello della catena pg_cron).

**(3) Misura rieseguita** (`v2_indip.py`, mio codice, stesso `m_dati.json`):
- 1X2 RPS, campione con ML n=1.509: Q 0,2008, Pcal 0,2165, Pgrezzo 0,2168, diff +0,0156 IC95 [+0,0111; +0,0202]
  (bootstrap 2000, seed diverso): IDENTICO a M. Senza filtro ML n=1.518: +0,0160 [+0,0114; +0,0207].
- Controllo di metodo: 1.519 righe, 1.519 fixture_id distinti (nessun duplicato); tutti i timestamp `+00:00`
  (nessun problema UTC/Europe/Rome); quote Sportsbook API-Football, `update` sempre <= `generated_at` (Q_orario,
  ho riletto `q_estrai.py`: stessi filtri). Se mai il confronto e' sfavorevole alle quote (piu' vecchie). Bootstrap iid
  ignora la correlazione per lega/giornata: IC un po' stretti, ma la differenza e' > 6 errori standard.
- **Estensione mia sul mercato che Mike usa davvero** (`v2_o35.py`): Over 3.5, n=1.007, log-loss Q 0,6072,
  Pcal 0,6246, Pgrezzo 0,6356 (= climatologia 0,6354); diff Pcal-Q +0,0174 [+0,0071; +0,0278]; peso ottimo di
  miscela w*=0,0. Solo pre-KO (n=880): +0,0164 [+0,0053; +0,0283], w*=0,0. Riscontro con 02/10: Brier
  `p_under35_cal` 0,219 contro mercato 0,196.

**(4) CRONOSTORIA.** `CRONOSTORIA.md:4888` (02/10 h18:05): "il MERCATO batte ML, Poisson e TacticAI su tutti i 13
bersagli; mescolare ML e quote peggiora le quote (14/15) ... `p_under35_cal` di Mike: Brier 0,219 (... mercato
0,196); il veto Under 3,5 ... il suo valore non e' misurabile ... Nessuna modifica fatta." Proposte di allora
(misurare il veto sulle quote Betfair, pagella contro mercato) NON risultano eseguite (grep "pagella contro",
"veto" dopo il 02/10: nulla). Nessuna decisione dell'utente trovata nella memoria del 09/10.

**Impatto reale.** Nessun ordine sbagliato dimostrato: il veto di Mike agisce solo al passaggio pre-match -> live su
posizioni in perdita; il suo effetto sul P&L e' NON misurato (02/10: ROI non vetate -1,2 % vs vetate -7,4 %, dentro
l'errore +-6,5). Chi lo vede: Mike (veto acceso), Omega/Safe (lambda di ripiego), scalper (bias, non default),
foglio Quant Fund e UI (PoissonPanel). **Verdetto: CONFERMATO; da riclassificare "gia' noto dal 02/10, mai chiuso".**

## M1 - Previsioni "pre-partita" generate dopo il calcio d'inizio

**(1) Codice.** `build_analytics_signals.py:298` `"oos_valid": True` fisso (riletto); `merge_engine_signals.py:203`
idem. Il campo `oos_valid` e' usato SOLO per il ramo ML (`migrations/analytics_strategy.sql:226` `bool_and(s.oos_valid)
filter (where s.engine='ml')`, filtro `p_ml_clean` in `analytics_strategy_rpc.sql:114,217`, checkbox in
`frontend/src/components/dashboard/CreateStrategy.tsx:257` "Richiede segnale ML certificato no-leak"). Nessun filtro
`generated_at < kickoff` in migrations/SQL/py (git grep). Neanche `generate_dynamic_cal.py:122` (calibrazione
settimanale) filtra per orario di generazione. CONFERMATO.

**(2) Produzione.** `build_analytics_signals.py` e `merge_engine_signals.py` girano in
`.github/workflows/predictions_results_backfill.yml:116,128`; `generate_dynamic_cal.py` in
`weekly_poisson_calibration.yml:91`. Consumatori: UI Analytics/Direzione (`DirezioniReport.tsx:8`,
`CreateStrategy.tsx`), tabelle `poisson_calibration` -> `markets_calibrated` -> Mike.

**(3) Misura rieseguita** (`v2_indip.py`): Poisson post-KO 160/1.519 (10,53 %), ML 200/1.510: IDENTICO a M.
Ore UTC del KO dei 160: 00h 42, 01h 44, 02h 16, 03h 7, 04h 3, 05h 11, 06h 5, 07h 5, 08h 27; generati tutti fra 07 e
09 UTC. Fusi: tutto `+00:00`. **Ancora vivo oggi** (mia SELECT del 09/10): righe con `fixture_date` 09/10 = 334,
generate 09:20-09:26 UTC, **22 dopo il KO (6,6 %)**; 08/10: 87 righe, generate 09:08 UTC, 5 post-KO.
- Cosa NON e': un'auto-fuga sulla forma squadra (`_before_date`, :1474-1478, `fixture_date <` stretto). Residuo: le
  medie di lega (`_build_match_cache`) includono ogni partita FT della stagione nota al momento del batch, quindi
  potenzialmente la partita stessa se gia' conclusa e gia' in `matches`: effetto minimo, NON misurato.
- **Bot: non toccati.** Per i post-KO anche `created_at` della riga e' dopo il KO (158/1.519, M par. 3): al momento
  del trading la riga non esiste, quindi Mike non ha P (veto non scatta: "Senza P calibrata ... nessun veto",
  `engine.py:3546`), Omega/Safe non hanno lambda Poisson. Effetto sui soldi = "nessuna previsione", non "previsione
  falsata".
- Nuovo orario: dal 09/10 la catena parte da pg_cron alle 00:12 UTC (workflow, righe 4-16). Con data di default =
  oggi UTC le partite fra 00:00 e la fine del batch resteranno strutturalmente post-KO (nel campione 86/160 avevano
  KO prima delle 02:00 UTC). Riduzione attesa ~meta', NON VERIFICATA (la catena nuova non ha ancora girato:
  oggi il batch ha girato alle 09:20 UTC).

**(4) CRONOSTORIA.** `CRONOSTORIA.md:4888` (02/10): "13 % delle previsioni ML e 11 % Poisson scritte DOPO il
fischio (escluse)"; proposta "congelare le previsioni al fischio (2 gg)": NON eseguita.

**Impatto reale.** Statistiche analytics/Direzione "pre-partita" e checkbox "no-leak" della UI promettono una
pulizia che il dato non ha (~10 % contaminato da previsioni tardive, il filtro e' sempre vero); tabelle di
calibrazione settimanali stimate anche su previsioni tardive (effetto sulla P di Mike NON misurato, plausibilmente
piccolo perche' la forma non vede la partita). Nessun ordine. **Verdetto: CONFERMATO nel fatto, RIDIMENSIONATO
nell'impatto (solo statistiche/UI/calibrazione), gia' noto dal 02/10.**

## M3 - Probabilita' grezze troppo estreme su Over 2.5; "lo scalper usa il grezzo"

**(1) Codice.** :1500-1555 = finestre 5/10/15 pesi 0,5/0,3/0,2, shrink k=8 (riletto). Che sia QUESTA la causa
resta NON provato (anche per l'audit). Il calibratore (`poisson_calibrator.py`) produce `markets_calibrated`.

**(2) Consumatori del GREZZO.** Scalper: `bias_resolver.py:79-90` legge SOLO `markets["1x2"]` (nessun mercato gol).
Foglio/`money_management`: grezzo + calibrazione propria. Mike: calibrato (grezzo solo se manca il calibrato,
`dossier.py:103`).

**(3) Misura rieseguita** (`v2_slope2.py`, regressione logistica esito ~ logit(p), n=1.519, 1 = calibrato):

| mercato | grezzo | calibrato |
|---|---|---|
| Over 2.5 | 0,466 +- 0,080 (con quote O/U n=1.012: 0,418) | 0,627 +- 0,114 (n=1.012: 0,555) |
| Over 3.5 (Mike) | 0,469 +- 0,078 | 0,653 +- 0,109 |
| BTTS | 0,401 +- 0,102 | 0,701 +- 0,177 |
| 1X2 casa | **0,951 +- 0,098** | 0,946 |
| 1X2 ospite | **0,898 +- 0,101** | 0,924 |
| 1X2 pari | 0,773 +- 0,244 | 0,424 +- 0,202 |
| quote O2.5 (riferimento) | 0,816 +- 0,141 | - |

- Troppo estreme sui mercati GOL: CONFERMATO e piu' marcato di quanto scritto (0,47 contro 0,53-0,55: le cifre
  dell'audit vengono da 8 celle con regressione lineare e da 500 righe di un'altra finestra; metodi diversi, stessa
  direzione).
- "Dopo calibrazione 0,81" (V2) NON riprodotto: sul campione intero il calibrato resta 0,63-0,70 (z circa -3 rispetto
  a 1). Quindi anche la P calibrata usata da Mike (Over 3.5: 0,65) e' ancora troppo estrema: le soglie isotoniche
  del veto la ricentrano in parte (sono tarate su P -> esito), effetto residuo NON misurato.
- "Lo scalper usa il grezzo": vero come fatto, sbagliato come collegamento. Lo scalper legge l'1X2, dove il grezzo e'
  quasi calibrato (0,95/0,90) e la calibrazione non cambia nulla in modo misurabile (M: Pcal-Pgrezzo RPS -0,0003
  [-0,0011; +0,0005]). Sul pareggio il calibrato e' anzi peggiore del grezzo (0,42 contro 0,77, IC larghi).

**(4) CRONOSTORIA.** Pendenza/estremita' non trovata (grep "pendenza", "estrem"): reperto nuovo. 02/10 aveva gia'
"il mercato batte il Poisson calibrato" sugli over (tabella AUDIT_ML_POISSON.md:146-150).

**Impatto reale.** Sui mercati gol il grezzo e' pari alla climatologia (O2.5 0,6948 vs 0,6886; O3.5 0,6356 vs 0,6354):
chi legge il grezzo dei gol (foglio, UI PoissonPanel se mostra `markets`) legge rumore; chi legge il calibrato (Mike)
legge un numero migliore ma ancora troppo estremo. Lo scalper NON e' toccato da questo reperto. **Verdetto:
RIDIMENSIONATO: confermato sui mercati gol, da togliere il legame con lo scalper; da correggere la cifra "0,81".**

## Cio' che NON ho potuto verificare
- Effetto in euro del veto U3.5 di Mike (servono le quote Betfair exchange al fischio e gli esiti delle posizioni).
- Se la catena pg_cron delle 00:12 UTC riduca davvero le previsioni post-KO (prima esecuzione non ancora avvenuta).
- Quanto la partita stessa entri nelle medie di lega delle previsioni tardive; quanto la calibrazione settimanale
  cambi escludendo le previsioni post-KO.
- Se la UI (PoissonPanel) mostri `markets` o `markets_calibrated` per gli over (non riletto).
- Correlazione per lega/giornata negli IC (bootstrap iid, come l'audit).
