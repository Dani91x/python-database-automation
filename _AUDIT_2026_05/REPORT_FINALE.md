# Audit + Ricostruzione Matematica del Sistema di Pronostici — Report Finale
**Data:** 2026-05-26
**Vincolo rispettato:** nessuna scrittura/cancellazione sul database. Tutte le query sono `SELECT`/OpenAPI in sola lettura. I dati sono stati copiati in cache locale (`_AUDIT_2026_05/cache/`) per l'analisi.

---

## 1. Struttura del database (Supabase, 26 tabelle)

| Tabella | Righe | Contenuto chiave |
|---|---|---|
| `matches` | ~grande | Risultati partite: goals_home/away, halftime, fixture_date (ts), league_id, season_year, team ids, status_short |
| `match_odds` | ~grande | Quote storiche **football-data.co.uk**: market_key `1`=1X2, `5`=Over/Under 2.5, `8`=BTTS. Book multipli (Pinnacle, Maximum, Average, Bet365…), **apertura E chiusura** (`bookmaker_name` suffisso `_closing`), `snapshot_time` pre-kickoff |
| `match_team_stats` | ~grande | stat_type incl. `expected_goals` (copertura parziale), tiri, corner, falli, cartellini |
| `fixture_predictions` | 80.186 | Hub predizioni: raw_json_odds, model_predictions_json (ML), db_json_analisi (Poisson), result_* |
| `standings` | 84.380 | Classifiche per lega/stagione |
| `model_performance` | 1.025 | **Metriche reali del modello ML per lega/target**: brier, brier_random, **bss**, ece |
| `signal_history` | 3.474 | Segnali generati — **ma result/pnl/clv MAI popolati** (nessun tracking reale); edge dichiarati assurdi (+21% Poisson, +35% ML) |
| `injuries`, `top_*`, `api_*`, viste `v_roi_*` | varie | Supporto. Le viste ROI sono **vuote** |

---

## 2. Difetti di progettazione confermati (perché il sistema "credeva" di avere edge)

1. **Data leakage nella calibrazione** (`update_poisson_calibration.py`, `generate_dynamic_cal.py`): i fattori di correzione sono stimati in-sample su **tutti** i fixture, poi il backtest valuta sugli stessi → ROI gonfiato. Nessun walk-forward.
2. **De-vig forfettario** (`money_management.py: OVERROUND_CORRECTION=0.975`): margine fisso 2.5% invece dell'overround reale per-mercato → edge sovrastimato sui mercati con vig alto.
3. **Overdispersione ignorata**: Poisson semplice; i fattori di calibrazione mostruosi (O25 1.8×, HT05 2.56×) ne sono il sintomo.
4. **Edge illusorio**: i backtest del sistema mostrano "edge medio +10/12%" ma ROI reale **negativo** (−1.5% → −8.9%), gap di ~15-19 punti. Più cresce il campione, più peggiora → nessun edge reale.
5. **Toppe sintomatiche** invece di fix (MARKET_MAP: pareggio min_prob alzato a 0.42, BTTS e HT05 sospesi).

---

## 3. Sistema ricostruito (matematica corretta, zero leak)

Codice in `_AUDIT_2026_05/`:
- **`dc_model.py`** — Dixon-Coles fatto bene: forze attacco/difesa + vantaggio campo via **regressione di Poisson** con **time-decay** (half-life 180gg), correzione τ sulle 4 celle basse, matrice punteggi → mercati.
- **`devig.py`** — de-vig corretto per-mercato (**Shin** + moltiplicativo), non più costante fissa.
- **`backtest.py` / `dump.py`** — **engine point-in-time**: per ogni partita il modello è addestrato SOLO su match con data < kickoff; le probabilità sono **calibrate con isotonic walk-forward** (solo su partite passate già risolte → corregge overdispersione senza leak); le quote sono pre-kickoff. Simula esattamente "una partita oggi".
- **`strategy*.py`** — valutazione strategie con split **DEV (<2020-07) / HOLDOUT (≥2020-07)** e metrica **CLV** (closing line value) come prova-regina dell'edge.

Dataset: **309.140 predizioni** point-in-time su **12 leghe**, ~62k partite, 2012-2026.

---

## 4. Risultati onesti

### 4a. Il MODELLO non batte il mercato
Backtest leak-free, quote Max, edge≥3%, pooled 12 leghe (HOLDOUT):
- 1X2 e Over/Under: ROI da −2.5% a −5.5%, **CLV ~0 o negativo**.
- Per-lega e per-mercato i segni si **invertono** tra DEV e HOLDOUT → nessun edge robusto.
- **Conclusione**: un Dixon-Coles anche corretto NON ha edge predittivo sulla closing line. Coerente con la letteratura accademica (i mercati sono efficienti). L'edge del sistema originale era puro artefatto di leak+de-vig.

### 4b. Strategia PROFITTEVOLE trovata: line-shopping alla chiusura
Edge reale = **esecuzione del prezzo**, non predizione. Si prende la **miglior quota di chiusura** disponibile quando supera di ≥8% la fair sharp di Pinnacle (de-viggata). Config scelta su DEV, validata su HOLDOUT.

| Periodo | n bet | ROI flat | CLV | maxDD | ROI Kelly¼ |
|---|---|---|---|---|---|
| DEV (2012..2020-06) | 173 | **+12.82%** | +10.89% | −18u | +11.5% |
| **HOLDOUT (2020-07..2025)** | **1.348** | **+8.75%** | **+11.94%** | −23u | **+14.06%** |
| FULL | 1.521 | +9.21% | +11.82% | −23u | +13.80% |

- **Positivo ogni anno**: 2019 +1.4%, 2020 +27%, 2021 +5.3%, 2022 −0.9%, 2023 +20.5%, 2024 +6.4%, 2025 +10.1%.
- **Positivo su tutti i mercati** (HOLDOUT): H +10.3%, D +7.3%, A +2.6%, O25 +10.5%, U25 +12.4%.

### 4c. Prova anti-artefatto (sanity)
Scommettere **indiscriminatamente** (HOLDOUT, no selezione):
- @ Pinnacle_closing: **−4.15%**, @ Average −6.48%, @ Bet365 −6.59%, @ Maximum_closing −0.88%.

Il betting a caso perde il margine; la **selezione** (best price vs fair sharp ≥ soglia) trasforma −0.88% in +8.75%. Quindi: (1) il fair di Pinnacle è ben calibrato (non distorto), (2) l'edge è genuino e viene dallo scegliere gli spot di miglior prezzo.

---

## 5. Caveat di realizzabilità (onestà intellettuale)
- "Maximum_closing" = miglior prezzo tra ~14 book. Per realizzare +8.75% servono: accesso al miglior prezzo (aggregatore/più conti), quote effettivamente giocabili (alcuni "max" sono prezzi soft/stantii poi annullati), book che non limitano i vincenti.
- Il CLV +12% è strutturalmente sano ma in parte ottimistico (include outlier). Una stima realistica più conservativa userebbe il 2°/3° miglior prezzo; il **segno resta positivo** e stabile.
- Su **Betfair exchange** (target del sistema) il concetto "miglior prezzo" si mappa nel prendere le offerte migliori → la strategia è più realizzabile lì che sui book soft.

---

## 6. Raccomandazioni
1. **Abbandonare la pretesa che il modello batta il mercato.** Usarlo al più come uno dei tanti input, mai come fonte di edge.
2. **Riscrivere la calibrazione in walk-forward** (eliminare il leak) e rigenerare ogni metrica/ROI: i numeri storici "positivi" del sistema non sono affidabili.
3. **De-vig reale per-mercato** (Shin/moltiplicativo sulle quote effettive), eliminare `OVERROUND_CORRECTION` fisso.
4. **Spostare il focus sull'esecuzione**: line-shopping / CLV-tracking. Popolare `signal_history.closing_odds` e `clv` per misurare l'edge reale in avanti (il CLV medio è il KPI da massimizzare, non l'"edge" dichiarato).
5. Se si vuole un modello migliore: aggiungere xG/tiri rolling — ma l'aspettativa di battere la closing resta bassa.
