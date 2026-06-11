# Fix motore Poisson — 2026-06-11

Indagine → fix dei punti **1, 2, 3, 4, 8, 9, 11, 15, 19** del report `POISSON_RESEARCH_2026-06-11.md`.
Vincolo: ogni gruppo passato in **code-review** (`everything-claude-code:code-reviewer`) → tutti APPROVED (0 CRITICAL / 0 HIGH). Nessun errore di calcolo introdotto.

File toccati:
- `Prediction/today_predictions_backfill.py` (motore live)
- `generate_dc_rho.py` (NUOVO — estimatore ρ per-lega)
- `dc_rho_by_league.json` (NUOVO — output estimatore, opzionale: fallback a ρ globale)
- `tmp_smoke_poisson_fixes.py` (NUOVO — smoke test offline)

---

## Gruppo A — #1, #2, #3 (coefficienti λ)

**#1 — Cast a float dei gol.** `_to_float()` introdotto; `_build_match_cache` coerce `goals_home/away` (+ halftime) a float prima di sommarli; `_window_stats` ri-guarda i valori. Evita che valori stringa dal driver DB vengano **concatenati** invece che sommati (corromperebbe ogni media gol/λ).

**#2 — Fallback solo-gol quando manca l'xG.** Prima: con xG assente il termine 0.4 collassava a un 1.0 neutro, **smorzando** il segnale dei gol. Ora `_coef()` usa **solo i gol** (eta effettivo = 1.0) quando l'xG non c'è. Telemetria `xg_blend_active` + contatori `home/away_xga_covered` persistiti in `inputs` (interrogabili dal foglio). *Comportamento confermato dall'utente: se l'xG manca, si usano i gol.*

**#3 — xGA derivato (difesa simmetrica).** L'xGA non è nativo → ricavato come **xG dell'avversario nella stessa partita** (`opponent_id` in `team_hist`, `xga_avg`/`xga_blend`). La difesa ora blenda gol+xGA con η=0.6 come l'attacco, normalizzata sui baseline corretti (xGA casa → `league_away_xg_avg`; xGA trasferta → `league_home_xg_avg`). Degrada a soli-gol dove l'xG manca, esattamente come l'attacco. **Zero dati nuovi richiesti.**

## Gruppo B — #11 (ρ Dixon-Coles per-lega)

- `get_league_rho(league_id)`: loader con cache, legge `dc_rho_by_league.json`, **clamp difensivo** a `[DC_RHO_MIN,DC_RHO_MAX]=[-0.25,0.05]`, fallback al ρ globale `-0.13` se file/lega assenti o valore fuori banda. Mai un crash se il file non esiste.
- Lo stesso `rho_league` alimenta **entrambe** le griglie (FT e HT) → coerenza interna. Campo `dc_rho` in output ora riflette il ρ effettivo usato.
- `generate_dc_rho.py`: stima ρ per-lega via **profile-likelihood MLE** (marginali λ = quelli del motore, ρ unico parametro libero). Normalizzatore in forma chiusa `Z = 1 + Σ_{4 celle} pmf_h·pmf_a·(τ−1)`. Shrinkage empirical-Bayes verso `-0.13` (K=300), skip leghe con <300 match, scrittura atomica.
- **Test sintetico**: MLE recupera ρ=-0.16 → -0.137 (n=4000, entro tolleranza) e NLL(MLE) < NLL(indipendenza). ✅

## Gruppo C — #4, #8, #9, #15, #19 (mercato HT + normalizzazione)

**#4 — Shrinkage su `_team_p_goal_1h`.** Prima: frequenza grezza → 0.0/1.0 su pochi dati. Ora shrinkage Beta-Binomiale verso 0.5 (k=5 match); ritorna `(prob, n_valid)`.

**#9 — Componente Poisson HT con correzione DC.** Prima: `1 - exp(-λ_1h)` (versione a indipendenza, ignorava DC → sovrastimava Over 0.5). Ora `p_goal_1h_poisson = 1 - ht_grid[0,0]` (P di ≥1 gol nel 1T presa dalla **stessa griglia HT Dixon-Coles** usata per `ht_1x2`).

**#8 — Blend ibrido pesato per affidabilità.** Prima: media fissa 50/50. Ora `w_freq = n_eff/(n_eff+10)` con `n_eff = (n_home_1h + n_away_1h)/2`. Con pochi dati → si appoggia al Poisson (modello); con dati pieni → w_freq≈0.6. La media (non il min) evita di scartare le osservazioni di una squadra se l'altra è priva di dati HT.

**#15 — Normalizzazione esplicita 1X2 (FT e HT).** H+D+A forzato a sommare 1 esatto sui float interni (le 3 maschere partizionano già la griglia normalizzata). Nessuna deriva 0.9999/1.0001 a valle. (Il JSON memorizza 4 decimali → la somma degli **arrotondati** resta entro ~1e-4, atteso.)

**#19 — Coerenza mercato HT.** Risultante da #4+#8+#9: la componente frequentista è shrinkata, la Poisson è DC-corretta e coerente con `ht_1x2`, il blend è pesato per affidabilità. `details` espone `w_freq`.

---

## Certificazione

| Check | Esito |
|---|---|
| `py_compile` (motore + estimatore) | ✅ PASS |
| Code-review Gruppo A / B / C | ✅ APPROVED (0 CRITICAL, 0 HIGH ciascuno) |
| Smoke test offline (`tmp_smoke_poisson_fixes.py`) — scenario xG pieno + xGA | ✅ PASS (somme=1, prob∈[0,1], monotonia Over, λ>0) |
| Smoke test offline — scenario solo-gol (no xG) | ✅ PASS (`xg_blend_active=False`, fallback corretto) |
| Test sintetico recupero ρ MLE | ✅ PASS |
| **Dry-run su DB reale** (`AGGIORNA --dry-run --limit 40 --force`) | ✅ **0 errori** / 40 fixture, multiple leghe (31 valide, 9 skip dati insufficienti) |

### Resync produzione → foglio (PENDENTE — richiede OK utente)
I fix cambiano gli output: il foglio mostra i numeri vecchi finché non si rigenera. Catena:
1. `python generate_dc_rho.py` → `dc_rho_by_league.json` (per attivare #11)
2. `python AGGIORNA_CAMPO_db_json_analisi.py --force` (⚠️ ~64k righe, irreversibile — consigliato pilota `--league <id>` prima)
3. `python Prediction/backfill_historical_analysis.py`
4. `python generate_dynamic_cal.py`
5. `python master_backtest.py` (ROI più basso/onesto atteso)
6. `python -m market_intelligence.pipeline --all`
7. report giornaliero → foglio coerente.
