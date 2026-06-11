"""
CALIBRAZIONE COMPLETA — Probabilità stimate vs Risultati reali
Analizza lo storico del modello Poisson per identificare bias sistematici.

⚠️ QUESTO SCRIPT È DIAGNOSTICO. NON è la fonte di verità per dynamic_cal.json.
La fonte di verità (SINGLE SOURCE OF TRUTH) per dynamic_cal.json è
``generate_dynamic_cal.py`` (vedi MANUALE_OPERATIVO.md §3 e diagramma architettura):
quello script filtra solo i record del modello ``poisson_xg_hybrid_dc``, applica
empirical-Bayes shrinkage per-lega e produce lo schema consumato da
``money_management.py`` (``by_league`` / ``global`` / ``divergence_stats`` +
``leagues_covered``).

Per evitare due metodologie incompatibili che si sovrascrivono lo stesso file,
questo script scrive la sua tabella dinamica in ``dynamic_cal_diagnostic.json``
(NON sovrascrive ``dynamic_cal.json``).
"""
import sys, os, json, math
sys.path.insert(0, '.')
from db_client import get_supabase_client
from collections import defaultdict

sb = get_supabase_client()

# ======================================================================
# 1. FETCH DATI STORICI
# ======================================================================
print("Fetching dati storici da fixture_predictions...")
all_data = []
page_size = 1000
offset = 0

while True:
    resp = sb.table("fixture_predictions").select(
        "fixture_id, fixture_date, db_json_analisi, ht_predictions, "
        "result_status_short, result_home_goals, result_away_goals, "
        "percent_home, percent_draw, percent_away"
    ).in_("result_status_short", ["FT", "AET", "PEN"]).range(offset, offset + page_size - 1).execute()
    
    batch = resp.data or []
    all_data.extend(batch)
    print(f"  Fetched {len(batch)} records (total: {len(all_data)})")
    if len(batch) < page_size:
        break
    offset += page_size

print(f"\nTotale match finiti: {len(all_data)}")

# Fetch HT data from matches table 
print("Fetching dati halftime da matches...")
fixture_ids = [r["fixture_id"] for r in all_data]
ht_map = {}
for i in range(0, len(fixture_ids), 200):
    chunk = fixture_ids[i:i+200]
    resp = sb.table("matches").select(
        "fixture_id, halftime_home, halftime_away"
    ).in_("fixture_id", chunk).execute()
    for r in (resp.data or []):
        ht_map[r["fixture_id"]] = (r.get("halftime_home"), r.get("halftime_away"))
print(f"  HT data per {len(ht_map)} match")

# Filter only those with analysis
rows = []
for r in all_data:
    analysis = r.get("db_json_analisi")
    if not analysis or not isinstance(analysis, dict):
        continue
    markets = analysis.get("markets")
    if not markets:
        continue
    ht = ht_map.get(r["fixture_id"], (None, None))
    rows.append({
        "fixture_id": r["fixture_id"],
        "date": str(r.get("fixture_date", ""))[:10],
        "markets": markets,
        "gh": int(r["result_home_goals"]) if r.get("result_home_goals") is not None else None,
        "ga": int(r["result_away_goals"]) if r.get("result_away_goals") is not None else None,
        "hth": int(ht[0]) if ht[0] is not None else None,
        "hta": int(ht[1]) if ht[1] is not None else None,
    })

print(f"Match con analisi valida: {len(rows)}")
dates = sorted(set(r["date"] for r in rows))
print(f"Range: {dates[0]} → {dates[-1]} ({len(dates)} giorni)")

# ======================================================================
# 2. CALIBRAZIONE PER MERCATO
# ======================================================================
def get_prob(markets, market_key, sub_key):
    val = (markets.get(market_key) or {}).get(sub_key)
    if val is None:
        return None
    if val > 1:
        val = val / 100.0
    return val

def check_result(row, market_type):
    gh, ga, hth, hta = row["gh"], row["ga"], row["hth"], row["hta"]
    if gh is None or ga is None:
        return None
    
    if market_type == "home_win": return gh > ga
    if market_type == "draw": return gh == ga
    if market_type == "away_win": return gh < ga
    if market_type == "over15": return (gh + ga) > 1
    if market_type == "under15": return (gh + ga) <= 1
    if market_type == "over25": return (gh + ga) >= 3
    if market_type == "under25": return (gh + ga) < 3
    if market_type == "over35": return (gh + ga) > 3
    if market_type == "under35": return (gh + ga) <= 3
    if market_type == "btts_yes": return gh >= 1 and ga >= 1
    if market_type == "btts_no": return gh == 0 or ga == 0
    if market_type == "ht_over05":
        if hth is None or hta is None: return None
        return (hth + hta) >= 1
    if market_type == "ht_under05":
        if hth is None or hta is None: return None
        return (hth + hta) == 0
    if market_type == "ht_home":
        if hth is None or hta is None: return None
        return hth > hta
    if market_type == "ht_draw":
        if hth is None or hta is None: return None
        return hth == hta
    if market_type == "ht_away":
        if hth is None or hta is None: return None
        return hth < hta
    return None

MARKETS_CONFIG = [
    ("1x2 Home",       "1x2", "H",    "home_win"),
    ("1x2 Draw",       "1x2", "D",    "draw"),
    ("1x2 Away",       "1x2", "A",    "away_win"),
    ("Over 1.5",       "over_1_5", "True", "over15"),
    ("Under 1.5",      "over_1_5", "False", "under15"),
    ("Over 2.5",       "over_2_5", "True", "over25"),
    ("Under 2.5",      "over_2_5", "False", "under25"),
    ("Over 3.5",       "over_3_5", "True", "over35"),
    ("Under 3.5",      "over_3_5", "False", "under35"),
    ("BTTS Sì",        "btts", "True", "btts_yes"),
    ("BTTS No",        "btts", "False", "btts_no"),
    ("1H Over 0.5",    "first_half_over_0_5", "True", "ht_over05"),
    ("1H Under 0.5",   "first_half_over_0_5", "False", "ht_under05"),
    ("HT Casa",        "ht_1x2", "H", "ht_home"),
    ("HT Pareggio",    "ht_1x2", "D", "ht_draw"),
    ("HT Trasferta",   "ht_1x2", "A", "ht_away"),
]

output_lines = []
calibration_data = {}

def out(line=""):
    output_lines.append(line)
    print(line)

out("=" * 80)
out("  CALIBRAZIONE MODELLO — Prob Stimata vs Win Rate Reale")
out("=" * 80)
out(f"\nDataset: {len(rows)} match ({dates[0]} → {dates[-1]})\n")

for label, mk, sk, check_type in MARKETS_CONFIG:
    preds = []
    actuals = []
    
    for r in rows:
        p = get_prob(r["markets"], mk, sk)
        if p is None:
            continue
        result = check_result(r, check_type)
        if result is None:
            continue
        preds.append(p)
        actuals.append(1 if result else 0)
    
    if len(preds) < 10:
        out(f"  {label:20s}: DATI INSUFFICIENTI ({len(preds)})")
        continue
    
    avg_p = sum(preds) / len(preds) * 100
    wr = sum(actuals) / len(actuals) * 100
    bias = avg_p - wr
    
    out(f"\n{'─'*70}")
    out(f"  {label:20s} | N={len(preds):5d} | Prob media={avg_p:5.1f}% | WR reale={wr:5.1f}% | BIAS={bias:+5.1f}pp")
    out(f"{'─'*70}")
    
    # Binned calibration (10pp bins)
    bins = defaultdict(lambda: {"preds": [], "actuals": []})
    for p, a in zip(preds, actuals):
        bin_idx = min(int(p * 10), 9)  # 0-9
        bin_label = f"{bin_idx*10}-{bin_idx*10+10}%"
        bins[bin_label]["preds"].append(p)
        bins[bin_label]["actuals"].append(a)
    
    bin_cal = {}
    for bl in sorted(bins.keys()):
        bd = bins[bl]
        if len(bd["preds"]) < 5:
            continue
        bp = sum(bd["preds"]) / len(bd["preds"])
        bwr = sum(bd["actuals"]) / len(bd["actuals"])
        bb = (bp - bwr) * 100
        out(f"    {bl:10s}: N={len(bd['preds']):4d} | Prob avg={bp*100:5.1f}% | WR={bwr*100:5.1f}% | Bias={bb:+5.1f}pp | Corr factor={bwr/bp:.3f}" if bp > 0 else f"    {bl}: N={len(bd['preds'])}")
        bin_cal[bl] = {"n": len(bd["preds"]), "avg_prob": round(bp, 4), "win_rate": round(bwr, 4), "correction": round(bwr/bp, 4) if bp > 0 else 1.0}
    
    calibration_data[label] = {
        "market_key": mk,
        "sub_key": sk,
        "check_type": check_type,
        "total_n": len(preds),
        "avg_prob": round(avg_p / 100, 4),
        "win_rate": round(wr / 100, 4),
        "global_correction": round((wr / 100) / (avg_p / 100), 4) if avg_p > 0 else 1.0,
        "bins": bin_cal
    }

# ======================================================================
# 3. PROFITABILITY SIMULATION 
# ======================================================================
out(f"\n\n{'=' * 80}")
out(f"  BACKTEST — Simulazione con filtri attuali vs corretti")
out(f"{'=' * 80}")

# Simula con probabilità originali (edge >= 5%, prob >= 55%)
def simulate(rows, min_edge, min_prob, correction_factors=None, kelly_frac=0.25, max_stake_pct=0.03, bankroll=1000, commission=0.05):
    pnl = 0
    total_staked = 0
    bets = 0
    wins = 0
    
    for r in rows:
        gh, ga, hth, hta = r["gh"], r["ga"], r["hth"], r["hta"]
        if gh is None or ga is None:
            continue
        
        # Scan best market (come fa il sistema reale)
        best = None
        for label, mk, sk, check_type in MARKETS_CONFIG:
            if check_type in ("under25", "btts_no", "ht_under05"):
                continue  # Mercati inversi: skip se non abilitati
            
            p = get_prob(r["markets"], mk, sk)
            if p is None or p < min_prob:
                continue
            
            # Apply correction if available
            if correction_factors and label in correction_factors:
                p = p * correction_factors[label]
                p = min(p, 0.99)
            
            # Simula la quota come 1/p_fair * (1 + margine_medio Betfair)
            # Usiamo un margine medio Betfair del 5%
            fair_odds = 1.0 / p if p > 0 else 100
            # Quota media Betfair ~= fair_odds * 0.95 (il bookmaker prende margine)
            # Per simulazione: usiamo una stima realistica
            quota = fair_odds * 0.97  # Betfair ha margino basso
            
            odds_net = (quota - 1.0) * (1.0 - commission) + 1.0
            edge = (p * odds_net) - 1.0
            
            if edge < min_edge:
                continue
            
            score = edge * (p ** 0.5)
            if best is None or score > best["score"]:
                best = {"label": label, "prob": p, "odds": quota, "edge": edge, "score": score, "check_type": check_type}
        
        if best is None:
            continue
        
        # Kelly stake
        b = (best["odds"] - 1.0) * (1.0 - commission)
        kelly_full = (b * best["prob"] - (1 - best["prob"])) / b if b > 0 else 0
        if kelly_full <= 0:
            continue
        
        stake = min(bankroll * kelly_full * kelly_frac, bankroll * max_stake_pct)
        stake = max(round(stake, 2), 1.0)
        
        # Risultato
        won = check_result(r, best["check_type"])
        if won is None:
            continue
        
        if won:
            profit = stake * (best["odds"] - 1) * (1.0 - commission)
            pnl += profit
            wins += 1
        else:
            pnl -= stake
        
        total_staked += stake
        bets += 1
    
    return {"bets": bets, "wins": wins, "pnl": round(pnl, 2), "staked": round(total_staked, 2), 
            "wr": round(wins/bets*100, 1) if bets > 0 else 0,
            "yield": round(pnl/total_staked*100, 2) if total_staked > 0 else 0}

# Scenario A: Parametri attuali
res_a = simulate(rows, min_edge=0.05, min_prob=0.55, kelly_frac=0.25, max_stake_pct=0.03)
out(f"\n  A) Parametri ATTUALI (edge≥5%, prob≥55%, kelly=0.25, maxStake=3%)")
out(f"     Bets: {res_a['bets']} | WR: {res_a['wr']}% | P&L: {res_a['pnl']:+.2f}€ | Yield: {res_a['yield']}%")

# Scenario B: Filtri più severi
res_b = simulate(rows, min_edge=0.10, min_prob=0.60, kelly_frac=0.15, max_stake_pct=0.02)
out(f"\n  B) Filtri SEVERI (edge≥10%, prob≥60%, kelly=0.15, maxStake=2%)")
out(f"     Bets: {res_b['bets']} | WR: {res_b['wr']}% | P&L: {res_b['pnl']:+.2f}€ | Yield: {res_b['yield']}%")

# Scenario C: Con calibrazione applicata + filtri severi
corrections = {label: d["global_correction"] for label, d in calibration_data.items()}
res_c = simulate(rows, min_edge=0.10, min_prob=0.60, kelly_frac=0.15, max_stake_pct=0.02, correction_factors=corrections)
out(f"\n  C) Filtri SEVERI + CALIBRAZIONE (prob corrette)")
out(f"     Bets: {res_c['bets']} | WR: {res_c['wr']}% | P&L: {res_c['pnl']:+.2f}€ | Yield: {res_c['yield']}%")

# Scenario D: Con calibrazione + edge 15%
res_d = simulate(rows, min_edge=0.15, min_prob=0.60, kelly_frac=0.15, max_stake_pct=0.02, correction_factors=corrections)
out(f"\n  D) Filtri ULTRA-SELETTIVI + CALIBRAZIONE (edge≥15%)")
out(f"     Bets: {res_d['bets']} | WR: {res_d['wr']}% | P&L: {res_d['pnl']:+.2f}€ | Yield: {res_d['yield']}%")

# ======================================================================
# 4. SALVA RISULTATI (statica)
# ======================================================================
with open("calibration_results.json", "w", encoding="utf-8") as f:
    json.dump(calibration_data, f, indent=2, ensure_ascii=False)

with open("calibration_report.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))

out(f"\n✅ Salvati: calibration_results.json + calibration_report.txt")


# ======================================================================
# 5. CALIBRAZIONE DINAMICA — Rolling Window per Lega + Globale
#    Genera dynamic_cal.json con:
#    - "by_league": {league_id: {market_cal_key: {bin: correction, ...}}}
#    - "global": {market_cal_key: {bin: correction, ...}}
#    - "divergence_stats": {mean, std, n_samples}
# ======================================================================
import tempfile
from datetime import datetime

out(f"\n\n{'=' * 80}")
out(f"  CALIBRAZIONE DINAMICA — Rolling Window")
out(f"{'=' * 80}")

# --- 5a. Fetch league_id + raw_json_odds per ogni fixture ---
print("\nFetching league_id e raw_json_odds per calibrazione dinamica...")
league_map = {}   # fixture_id -> league_id
odds_map = {}     # fixture_id -> parsed_odds (for divergence stats)
fixture_ids_all = [r["fixture_id"] for r in rows]

for i in range(0, len(fixture_ids_all), 500):
    chunk = fixture_ids_all[i:i+500]
    resp = sb.table("fixture_predictions").select(
        "fixture_id, league_id, raw_json_odds"
    ).in_("fixture_id", chunk).execute()
    for rec in (resp.data or []):
        fid = rec["fixture_id"]
        lid = rec.get("league_id")
        if lid is not None:
            league_map[fid] = int(lid)
        # Parse odds per divergence stats
        raw = rec.get("raw_json_odds")
        if raw and isinstance(raw, dict):
            bookmakers = raw.get("bookmakers", [])
            if bookmakers:
                bets = bookmakers[0].get("bets", [])
                parsed = {}
                for bet in bets:
                    name = bet.get("name", "")
                    vals = {}
                    for v in bet.get("values", []):
                        if v.get("odd"):
                            try:
                                vals[v["value"]] = float(v["odd"])
                            except (ValueError, TypeError):
                                pass
                    if name == "Match Winner":
                        parsed["H"] = vals.get("Home")
                        parsed["D"] = vals.get("Draw")
                        parsed["A"] = vals.get("Away")
                    elif name == "Goals Over/Under":
                        parsed["O25"] = vals.get("Over 2.5")
                        parsed["U25"] = vals.get("Under 2.5")
                    elif name == "Both Teams Score":
                        parsed["BTTS"] = vals.get("Yes")
                        parsed["BTTS_NO"] = vals.get("No")
                    elif name == "Goals Over/Under First Half":
                        parsed["HT05"] = vals.get("Over 0.5")
                        parsed["HT_U05"] = vals.get("Under 0.5")
                if parsed:
                    odds_map[fid] = parsed

print(f"  League IDs mappati: {len(league_map)}")
print(f"  Odds API-Football parsate: {len(odds_map)}")

# Mapping label -> cal_key (come in money_management.py MARKET_MAP)
LABEL_TO_CAL_KEY = {
    "1x2 Home": "H", "1x2 Draw": "D", "1x2 Away": "A",
    "Over 1.5": "O15", "Under 1.5": "U15",
    "Over 2.5": "O25", "Under 2.5": "U25",
    "Over 3.5": "O35", "Under 3.5": "U35",
    "BTTS Sì": "BTTS", "BTTS No": "BTTS_NO",
    "1H Over 0.5": "HT05", "1H Under 0.5": "HT_U05",
    "HT Casa": "HT_H", "HT Pareggio": "HT_D", "HT Trasferta": "HT_A",
}

# Mapping cal_key -> odds_map key (stessa mappatura)
CAL_KEY_TO_ODDS_KEY = {
    "H": "H", "D": "D", "A": "A",
    "O25": "O25", "U25": "U25",
    "BTTS": "BTTS", "BTTS_NO": "BTTS_NO",
    "HT05": "HT05", "HT_U05": "HT_U05",
}


# Empirical-Bayes shrinkage strength: ogni bin per-lega è tirato verso il
# fattore globale con peso n/(n+SHRINK_K). Con SHRINK_K=75 un bin con 75
# campioni pesa 50% reale / 50% globale; 150 campioni → 67% reale. Sceglie un
# valore nel range documentato 50-100 per essere robusto sui bin piccoli senza
# annullare il segnale per-lega sui bin grandi.
SHRINK_K = 75
# Soglia minima alzata da 5 → 20: 5 campioni davano fattori puro rumore.
MIN_PER_BIN = 20


def _enforce_monotonic(market_cal, bin_data):
    """Rende la mappatura calibrata MONOTONA non-decrescente in prob grezza.

    Per ogni bin presente calcola la prob calibrata rappresentativa
    (avg_prob_del_bin * correction) e applica un pooling adjacent-violators
    leggero: se un bin a prob grezza più alta mappa a una prob calibrata più
    bassa di un bin precedente, alza il suo fattore quel tanto che basta a non
    decrescere. Mantiene il formato {bin: correction_factor} esistente.
    """
    bins_sorted = sorted(market_cal.keys())
    prev_calibrated = None
    for bi in bins_sorted:
        avg_p = bin_data[bi]["avg_p"]
        if avg_p <= 0:
            continue
        calibrated = avg_p * market_cal[bi]
        if prev_calibrated is not None and calibrated < prev_calibrated:
            calibrated = prev_calibrated
            market_cal[bi] = round(calibrated / avg_p, 4)
        prev_calibrated = calibrated
    return market_cal


def compute_calibration_bins(subset_rows, markets_config, min_per_bin=MIN_PER_BIN,
                             global_cal=None):
    """Calcola fattori di correzione bin-level per un sottoinsieme di match.

    Se ``global_cal`` è fornito (mappa cal_key->{bin:correction}), ogni fattore
    per-lega viene shrinkato verso il fattore globale con peso n/(n+SHRINK_K)
    (empirical-Bayes). Inoltre la mappatura risultante è resa monotona
    non-decrescente in probabilità grezza.
    """
    cal = {}
    for label, mk, sk, check_type in markets_config:
        cal_key = LABEL_TO_CAL_KEY.get(label, label)
        bin_data = defaultdict(lambda: {"preds": [], "actuals": []})

        for r in subset_rows:
            p = get_prob(r["markets"], mk, sk)
            if p is None:
                continue
            result = check_result(r, check_type)
            if result is None:
                continue
            bin_idx = min(int(p * 10), 9)
            bin_data[bin_idx]["preds"].append(p)
            bin_data[bin_idx]["actuals"].append(1 if result else 0)

        market_cal = {}
        avg_p_by_bin = {}
        for bi in range(10):
            bd = bin_data[bi]
            n = len(bd["preds"])
            if n < min_per_bin:
                continue
            avg_p = sum(bd["preds"]) / n
            wr = sum(bd["actuals"]) / n
            raw_cf = wr / avg_p if avg_p > 0 else 1.0
            # Empirical-Bayes shrinkage verso il fattore globale.
            if global_cal is not None:
                global_cf = (global_cal.get(cal_key, {}) or {}).get(bi, 1.0)
                w = n / (n + SHRINK_K)
                cf = w * raw_cf + (1.0 - w) * global_cf
            else:
                cf = raw_cf
            market_cal[bi] = round(cf, 4)
            avg_p_by_bin[bi] = avg_p

        if market_cal:
            # Monotonicità: usa avg_p per bin appena calcolati.
            _bd = {bi: {"avg_p": avg_p_by_bin[bi]} for bi in market_cal}
            cal[cal_key] = _enforce_monotonic(market_cal, _bd)

    return cal

# --- 5b/5c. Finestre rolling per la calibrazione dinamica diagnostica ---
LEAGUE_WINDOW = 150
GLOBAL_WINDOW = 1000

# Raggruppa match per lega, ordinati per data
from collections import OrderedDict
league_rows = defaultdict(list)
for r in rows:
    lid = league_map.get(r["fixture_id"])
    if lid is not None:
        league_rows[lid].append(r)

# Ordina per data e prendi ultimi N
for lid in league_rows:
    league_rows[lid].sort(key=lambda x: x["date"])

# --- 5c. Calibrazione globale (ultimi 1000 match) — calcolata PRIMA perché
#         serve come target di shrinkage per la calibrazione per-lega. ---
sorted_rows = sorted(rows, key=lambda x: x["date"])
global_window = sorted_rows[-GLOBAL_WINDOW:]
global_cal = compute_calibration_bins(global_window, MARKETS_CONFIG)
out(f"Calibrazione globale: {len(global_cal)} mercati (window={GLOBAL_WINDOW}, match usati={len(global_window)})")

# --- 5b. Calibrazione per lega (empirical-Bayes shrinkage verso il globale) ---
by_league_cal = {}
leagues_covered = 0
for lid, lr in league_rows.items():
    window = lr[-LEAGUE_WINDOW:]  # ultimi 150
    if len(window) < 30:  # serve un minimo per calibrare
        continue
    cal = compute_calibration_bins(window, MARKETS_CONFIG, global_cal=global_cal)
    if cal:
        by_league_cal[str(lid)] = cal
        leagues_covered += 1

out(f"\nCalibrazione per lega: {leagues_covered} leghe coperte "
    f"(window={LEAGUE_WINDOW}, shrink_k={SHRINK_K}, min_per_bin={MIN_PER_BIN})")

# --- 5d. Divergence Stats (per il filtro Z-Score / Hallucination) ---
# Raccoglie le divergenze (prob_model / prob_market) - 1 per tutti i mercati
divergences = []
OVERROUND_CORRECTION = 0.975

for r in rows:
    fid = r["fixture_id"]
    parsed_odds = odds_map.get(fid)
    if not parsed_odds:
        continue

    for label, mk, sk, check_type in MARKETS_CONFIG:
        cal_key = LABEL_TO_CAL_KEY.get(label, label)
        odds_key = CAL_KEY_TO_ODDS_KEY.get(cal_key)
        if not odds_key:
            continue

        p = get_prob(r["markets"], mk, sk)
        if p is None or p < 0.05 or p > 0.95:
            continue

        q = parsed_odds.get(odds_key)
        if q is None or q <= 1.01:
            continue

        prob_market = (1.0 / q) * OVERROUND_CORRECTION
        if prob_market < 0.01:
            continue

        div = (p / prob_market) - 1.0
        divergences.append(div)

# Calcola media e deviazione standard delle divergenze
div_mean = 0.0
div_std = 0.30  # fallback conservativo
n_div = len(divergences)

if n_div >= 50:
    div_mean = sum(divergences) / n_div
    variance = sum((d - div_mean) ** 2 for d in divergences) / (n_div - 1)
    div_std = math.sqrt(variance) if variance > 0 else 0.30
    # Clampa std: minimo 0.10 (troppo aggressivo altrimenti), massimo 0.50
    div_std = max(0.10, min(div_std, 0.50))

out(f"\nDivergence Stats: n={n_div}, mean={div_mean:.4f}, std={div_std:.4f}")

# --- 5e. Assembla e scrivi dynamic_cal_diagnostic.json (ATOMICO) ---
# IMPORTANTE: questo file è DIAGNOSTICO e NON viene caricato da money_management.py.
# La fonte di verità di dynamic_cal.json è generate_dynamic_cal.py. Vedi nota in testa.
dynamic_cal = {
    "by_league": by_league_cal,
    "global": global_cal,
    "divergence_stats": {
        "mean": round(div_mean, 4),
        "std": round(div_std, 4),
        "n_samples": n_div,
    },
    "generated_at": datetime.now().isoformat(),
    "total_matches_used": len(rows),
    "leagues_covered": leagues_covered,
    "league_window": LEAGUE_WINDOW,
    "global_window": GLOBAL_WINDOW,
    "_note": "DIAGNOSTIC ONLY — non caricato in produzione. SoT = generate_dynamic_cal.py",
}

# Scrittura atomica: temp file → os.replace
base_dir = os.path.dirname(os.path.abspath(__file__))
target_path = os.path.join(base_dir, "dynamic_cal_diagnostic.json")
tmp_path = None
try:
    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=base_dir)
    with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
        json.dump(dynamic_cal, tmp_f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, target_path)
    out(f"\n✅ dynamic_cal_diagnostic.json generato ({leagues_covered} leghe, "
        f"{len(global_cal)} mercati globali) — DIAGNOSTICO, non carica in produzione")
except Exception as e:
    out(f"\n❌ Errore scrittura dynamic_cal_diagnostic.json: {e}")
    # Cleanup temp file se esiste
    if tmp_path and os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except OSError:
            pass
