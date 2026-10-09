# V1 - Verifica indipendente dei reperti ML A2, A3, MA1 (09/10/2026, ore 13:09)

Sola lettura. Repo a `852b717f` (09/10 13:01). Nessuna modifica a codice/test/DB/app, nessun commit, nessun processo lasciato acceso.
Script miei (fuori repo, scratchpad della sessione): `v1_ml_ricalcolo.py` (ricalcolo A2 da `m_dati.json`, nessun DB),
`v1_holdout_registry.py` (4 SELECT su `ai_model_registry`, filtro `target`, LIMIT 1200), `v1_ece.py` (simulazione con la `_ece_score` di produzione),
1 SELECT aggiuntiva (`brier<0.05`, LIMIT 50 per 3 target). Totale 7 SELECT, nessun 57014.

## Sintesi

| reperto | verdetto | gravita' |
|---|---|---|
| A2 ML servito non batte il tasso base su O2.5/BTTS, perde dalle quote su 1X2 | **CONFERMATO** (numeri riprodotti al quarto decimale con codice mio), con una precisazione: "non batte" = **indistinguibile** dal tasso base, non "peggiore" | ALTO come informazione, BASSO sui soldi dei bot |
| A3 gate su ~110 righe di holdout, unica guardia `len<10` | **CONFERMATO, anzi peggio**: holdout misurato ESATTAMENTE dalle celle del registry = mediana 119, ma p25 = 40 e p10 = 17-18; ~24% dei modelli decide su meno di 40 righe | ALTO per la "pagella" ML; BASSO sui soldi dei bot |
| MA1 BSS con baseline uniforme | **CONFERMATO**, con misura reale: over_1_5 696 modelli passano il BSS, 574 di essi (82%) NON battono neppure la frequenza del proprio holdout | MEDIO-ALTO sulla pagella/UI; soldi solo sul foglio Quant Fund |

**Gia' noto**: tutti e tre erano gia' scritti nell'audit del 02/10 (`AUDIT_2026-10-02/AUDIT_ML_POISSON.md` righe 20-25, 67, 110, 312; indicizzato in `CRONOSTORIA.md:4888`: "skill misurata contro la moneta invece che contro la media storica -> il filtro di affidabilità promuove i peggiori; il MERCATO batte ML ... su tutti i 13 bersagli ... Nessuna modifica fatta"). Il difetto del BSS era scritto ancora prima in `Ai Engine/CALIBRATION_RESEARCH.md:35`. Nessuna decisione dell'utente e nessuna correzione trovate dopo il 02/10. L'audit di oggi li RIMISURA in modo indipendente (campione diverso, quote con orario verificato), non li scopre.

## A2 - ML servito vs tasso base e quote

### (1) Codice
- Scrittura: `Ai Engine/ai_engine/predict_fixture.py:1051-1089` (`model_predictions_json`, `generated_at` a :1055, `targets` = probabilita' con post-calibrazione, `update` su `fixture_predictions` a :1083-1087). Confermato.

### (2) In produzione e chi lo consuma
- Produzione: `.github/workflows/today_predictions_backfill.yml:65-69` -> `Prediction/today_predictions_backfill.py:2718-2734` (blocco "SECONDO MOTORE: ML ensemble", `serving_batch.run_for_date`) -> `serving_batch.py:32` importa `predict_fixture`. Gira ogni giorno nella catena notturna. Training: `retrain_models.yml:306` (`cloud_retrain_shard.py`) -> `seriea_model_export.py`.
- Lettori di `model_predictions_json` (git grep, test esclusi): UI `frontend/src/components/dashboard/MLPanel.tsx:108`, `frontend/src/lib/fixtureModels.ts:54`; bot Telegram `Telegram bot/supabase/functions/telegram-bot/index.ts:483,743`; RPC Direzione `migrations/get_direction_rpc.sql:61`; `build_analytics_signals.py:157`; `ventaglio_segnali.py:128`; Quant Fund `Betfair/betfair_report_manager.py:63,348` (lanciato a mano da `aggiorna_report.bat:21`); scalper `Betfair/stream/scalper/bias_resolver.py:82` (solo modi `bias`/`both`; default `maker`, `scalper_service.py:496`).
- Omega/Mike/Safe: `git grep model_predictions_json|ensemble_v2` sulle loro cartelle = 0 righe. **I bot a soldi principali NON leggono l'ML.**

### (3) Misura rieseguita con codice mio (`v1_ml_ricalcolo.py` su `lavori/sonde/m_dati.json`, 1519 partite FT 21/09-07/10, bootstrap appaiato 2000)

| mercato (campione) | n | ML | quote molt. | clim. in-sample | clim. fuori campione (giorni precedenti) | ML - clim. in-sample [IC95] | ML - quote [IC95] |
|---|---|---|---|---|---|---|---|
| 1X2 (tutti) | 1509 | 1.0081 | 0.9592 | 1.0463 | - | -0.0382 [-0.057,-0.020] (ML meglio) | **+0.0489 [+0.033,+0.064]** |
| O2.5 (tutti) | 1006 | 0.6905 | 0.6714 | 0.6886 | 0.6940 | +0.0019 [-0.015,+0.019] | **+0.0191 [+0.006,+0.035]** |
| BTTS (tutti) | 1014 | 0.6955 | 0.6790 | 0.6883 | 0.6978 | +0.0073 [-0.010,+0.027] | +0.0165 [+0.0005,+0.035] |
| 1X2 solo ML pre-kickoff | 1309 | 1.0058 | 0.9537 | 1.0464 | - | -0.0405 | **+0.0522 [+0.036,+0.068]** |
| O2.5 pre-kickoff | 845 | 0.6878 | 0.6719 | 0.6890 | 0.6908 | -0.0012 [-0.018,+0.016] | **+0.0159** |
| BTTS pre-kickoff | 850 | 0.7000 | 0.6779 | 0.6889 | 0.6961 | +0.0110 [-0.009,+0.034] | **+0.0220** |

I valori di `M_misure.md` sono riprodotti esattamente (O2.5 0.6905/0.6886, BTTS 0.6955/0.6883, 1X2 1.0081/0.9592; differenze +0.0019 e +0.0072 come in `05`).

### Controlli di metodo
- **Quote prese dopo la previsione?** NO. Rifatto da me su `q_ts.json`: `update` delle quote > `generated_at` ML in **0/1510**; mediana `update` 7,99 h prima del calcio d'inizio; 20/1519 con `update` dopo il kickoff (max ~1 minuto). Il confronto non e' sbilanciato a favore delle quote.
- **Previsioni dopo il calcio d'inizio**: 200/1510 ML (13%) generate dopo il kickoff (gia' scritto da M e dal 02/10). Escluse (righe "pre-kickoff"): conclusioni invariate, il ML peggiora rispetto alle quote.
- **Climatologia in-sample** (tassi del campione stesso) e' ottimistica. Con una climatologia onesta fuori campione (solo giorni precedenti) l'ML risulta marginalmente MEGLIO su O2.5 (-0.0035) e BTTS (-0.0023), sempre non significativo. Quindi la frase corretta e' "**il ML non e' distinguibile dal tasso base** su O2.5/BTTS", non "e' peggiore". Il reperto in `05` dice "differenza non significativa": coerente.
- Unita'/scala: `targets` in 0-1 (verificato sui dati); 1X2 rinormalizzato; Brier binario vs somma-classi distinti (x2). Nessun errore trovato.
- Selezione: O/U e BTTS mancano per ~500 partite (solo partite con quota sul book "Betfair" Sportsbook di API-Football): campione sbilanciato verso leghe maggiori. Finestra di 17 giorni, bootstrap iid (IC un po' stretti).
- Coerenza esterna: l'audit del 02/10 (90 giorni, 25.330 partite, metodo diverso) trova lo stesso esito (BTTS ML 0,2501 vs frequenza 0,2485 peggio; mercato migliore su tutti i bersagli).

### Impatto reale
- Soldi dei bot (Omega/Mike/Safe): **nessuno** (non leggono l'ML). Scalper: solo se l'utente sceglie `bias`/`both`.
- Chi lo vede: la UI (pannello ML, Direzione), il bot Telegram, gli analytics/ventaglio e il foglio Quant Fund. L'utente vede un numero "ML" che su O2.5/BTTS non porta informazione oltre la frequenza media e che su tutti e tre i mercati e' meno informato della quota del bookmaker. Il rischio e' sui consigli e sulle scommesse manuali guidate da quei consigli.

## A3 - Gate su holdout piccoli, unica guardia `len<10`

### (1) Codice (righe attuali)
- `Ai Engine/ai_engine/seriea_model_export.py:234-235`: `temporal_train_val_holdout_split(val_ratio=0.15, holdout_ratio=0.10, purge_days=30)`; `:243` `metrics_split = holdout_split`.
- `:401-405`: unica guardia `if len(metrics_split) < 10: raise ValueError` -> brier/ece = None. **Riga 401 corretta** (`05` giusto; `H_verifica_avversaria.md` cita :437, sbagliato).
- `:111-117` `_brier_score` = somma sulle classi; `:425-427` Brier/ECE su holdout via `predict_ensemble` (prima della post-calibrazione).
- `preprocessing/temporal_split.py:92-118`: holdout = ultimo 10% per data.
- In produzione: `retrain_models.yml:306` -> `cloud_retrain_shard.py` -> `train_and_save_all`. Il Brier finisce nel registry (`:700-704`) e nel pickle (`calibration_metrics`), letto al serving da `predict_fixture.py:836-838`.

### (2) Misura ESATTA dell'holdout (nuova, non fatta dall'audit)
L'audit stimava ~110 righe da `train_rows`. Io ho letto le `calibration_cells` del registry: la somma degli `n` di una classe e' esattamente il numero di righe dell'holdout (`seriea_model_export.py:162-199`).

| target | modelli con celle | holdout mediana | p10 | p25 | p75 | p90 | < 40 righe | Brier NULL (holdout <10) |
|---|---|---|---|---|---|---|---|---|
| target_1x2 | 939 | 119 | 17 | 40 | 232 | 440 | 231 (25%) | 88 |
| target_btts | 938 | 119 | 18 | 40 | 232 | 440 | 230 (25%) | 84 |
| target_over_2_5 | 938 | 119 | 18 | 40 | 232 | 440 | 230 (25%) | 83 |
| target_over_1_5 | 931 | 120 | 18 | 41 | 235 | 440 | 223 (24%) | 78 |

- "~110 righe" e' la mediana giusta come ordine (119), ma nasconde la coda: un quarto dei modelli e' giudicato su 10-40 partite.
- Holdout degeneri nei modelli SERVITI (registry, non solo pkl locali): `target_over_0_5` almeno 50 modelli con Brier < 0,05 (min 0,0001; LIMIT raggiunto), `target_over_1_5` 3 (min 0,0044). Il sotto-reperto "Brier 0,000 passano" e' quindi vero anche in produzione.
- ECE: simulazione mia con la `_ece_score` di produzione, modello binario PERFETTAMENTE calibrato: P(ECE>0,10) = 94% a n=18, 77% a n=40, 60% a n=58, 18% a n=119, 2% a n=232. L'"86% a n=40" di `05` e' il valore 1X2 della sonda B (binario 66% in B, 77% nella mia con altra distribuzione di p): ordine di grandezza confermato.
- Effetto: il gate scarta modelli buoni per caso (ECE) e promuove modelli nulli per caso (Brier), proprio sul quarto dei modelli con holdout piccolo.

### (4) Cronostoria
Noto dal 02/10 (`AUDIT_ML_POISSON.md:21,67`: "holdout mediano ~100 partite: rumore ±0,03-0,06"; `:305` 1.635 righe con Brier NULL). Non corretto.

### Verdetto A3: CONFERMATO (e la coda e' peggiore della mediana dichiarata).

## MA1 - BSS con baseline uniforme

### (1) Codice
- `Ai Engine/ai_engine/confidence_gate.py:40` `MIN_BSS = 0.12`; `:170-237` `gate_calibration_quality`; **`:192`** `brier_random = (n_classes-1)/n_classes`; `:195` `bss = 1 - brier/brier_random`.
- Duplicato al serving: `predict_fixture.py:1031-1048` (stessa formula, produce `targets_not_reliable`).
- Duplicato a soldi: `Betfair/money_management.py:623-655` (BSS >= 0,12 stake pieno, 0,05-0,12 ridotto, < 0,05 blocco), stessa baseline.
- Anche `retrain_all_leagues.py:56,280,599` e `bss_monitor.py:31` usano la stessa soglia/baseline.

### (2) Produzione e consumatori
- `targets_not_reliable` letto da `MLPanel.tsx:108` (UI), `build_analytics_signals.py:157`, `ventaglio_segnali.py:128`. Il ramo a stake e' il Quant Fund (`money_management.py:1058` `scan_best_market_ml`), lanciato da `aggiorna_report.bat` / `betfair_report_manager.py`; CRONOSTORIA 08/10 17:30 (riga 5384): "Quant Fund su Google Sheets (non usato dai bot)". Lo scalper `bias_resolver.py` legge `targets` senza guardare il gate.

### (3) Misura
- Sonda `h_gate.py` rilanciata da me sul gate di produzione: tasso base 0,74 -> Brier 0,385, BSS +0,230, `passed=True`; 0,70/0,30 -> +0,160 True; 0,65 -> +0,090 False; MC holdout 110: passa il 91% a q=0,74. 1X2 climatologia: BSS +0,0285 (sotto soglia: per l'1X2 il gate e' selettivo). Riprodotto.
- **Misura reale nuova sul registry** (BSS contro la frequenza dello stesso holdout, ricavata dalle celle; e' una climatologia "a posteriori", quindi favorevole al modello):

| target | passano BSS_unif >= 0,12 | di cui NON migliori della frequenza dell'holdout | passerebbero BSS_clim >= 0,12 |
|---|---|---|---|
| target_over_1_5 | 696 | **574 (82%)** | 2 |
| target_over_2_5 | 173 | 108 (62%) | 12 |
| target_btts | 46 | 23 (50%) | 4 |
| target_1x2 | 337 | 34 (10%) | 152 |

  Nota: il conteggio considera solo la parte BSS del gate (l'ECE non e' nel registry): e' un limite superiore dei "promossi".
- Coerente con il 02/10 (`AUDIT_ML_POISSON.md:110`: over_0_5 "BSS 0,73 contro la moneta, -0,23 reale").

### (4) Cronostoria
Noto dal 02/10 (CRONOSTORIA.md:4888) e prima in `CALIBRATION_RESEARCH.md:35` ("gate facile; usare la climatologia per-lega"). Non corretto.

### Verdetto MA1: CONFERMATO. Per l'1X2 il gate e' davvero selettivo (10% di falsi promossi); sui binari sbilanciati (over_0_5/1_5) il gate etichetta "affidabile" quasi solo modelli senza skill.
Impatto: l'etichetta di affidabilita' mostrata in UI/analytics e' fuorviante sui mercati over bassi; stake pieno solo nel foglio Quant Fund (che richiede comunque edge > 0 contro la quota). Nessun effetto su Omega/Mike/Safe.

## Discrepanze minori trovate nei referti dell'audit
- `H_verifica_avversaria.md` cita la guardia a `seriea_model_export.py:437` e `MIN_BSS` a `confidence_gate.py:36`: le righe attuali sono **401** e **40** (`05` ha la 401 giusta).
- `05` riga A3: "86% a n=40" senza dire che e' il caso 1X2.
- BTTS ML vs quote: M da' IC [-0,0013,+0,0358] (non significativo), il mio bootstrap [+0,0005,+0,0353]: al limite, conclusione invariata.

## NON VERIFICATO
- Non ho scaricato ne' rieseguito un modello cloud (feature effettive, presenza delle quote come feature).
- Non ho misurato l'ECE dei modelli serviti (non e' nel registry; e' nei pickle): i "promossi" MA1 sono un limite superiore.
- Il campione A2 e' quello estratto dall'audit (`m_dati.json`); non ho rifatto l'estrazione dal DB (ho verificato la coerenza con `q_ts.json`, 0 differenze nei timestamp usati).
- Quante scommesse reali (manuali o Quant Fund) siano state guidate dal ML: non misurato.
- Lo scalper in modo `bias`/`both` acceso oggi: non verificato lo stato dell'app.
