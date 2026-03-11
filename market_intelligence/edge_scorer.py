"""
edge_scorer.py ? Phase 4: Composite Edge Scorer

Data una partita (per fixture_id o per dict pre-caricato),
restituisce un edge score composito per ogni mercato.

Il punteggio risponde a: "Quanto edge ci aspettiamo, tenendo conto
del bias storico di calibrazione + segnali ML e xG?"

Uso:
    from market_intelligence.edge_scorer import EdgeScorer
    scorer = EdgeScorer()
    result = scorer.score(fixture_id=1234567)
    scorer.print_scorecard(result)
"""
import sys, json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from market_intelligence.mi_config import (
    CACHE_DIR, REGISTRY_FILE, CALIBRATION_FILE, SIGNAL_WEIGHTS_FILE,
    MARKETS, ODDS_BRACKETS, MIN_COMPOSITE_EDGE,
    CACHE_MAX_AGE_HOURS, DEFAULT_WEIGHT_ML_DIV, DEFAULT_WEIGHT_XG,
    XG_MIN_SAMPLE
)


# -- Cache singleton (caricata una sola volta al primo score) --------------

_cache: dict = {}


def _load_cache() -> dict:
    global _cache
    if _cache:
        return _cache

    missing = []
    for label, path in [
        ("registry",     REGISTRY_FILE),
        ("calibration",  CALIBRATION_FILE),
        ("signals",      SIGNAL_WEIGHTS_FILE),
    ]:
        if not path.exists():
            missing.append(f"{label} ({path.name})")

    if missing:
        raise FileNotFoundError(
            f"Cache mancante: {', '.join(missing)}.\n"
            f"Esegui prima: python pipeline.py --all"
        )

    with open(REGISTRY_FILE, encoding="utf-8") as f:
        registry = json.load(f)
    with open(CALIBRATION_FILE, encoding="utf-8") as f:
        calibration = json.load(f)
    with open(SIGNAL_WEIGHTS_FILE, encoding="utf-8") as f:
        signals = json.load(f)

    # Verifica eta cache
    warnings = []
    try:
        gen_at = datetime.fromisoformat(calibration.get("generated_at", ""))
        age_h  = (datetime.now(timezone.utc) - gen_at).total_seconds() / 3600
        if age_h > CACHE_MAX_AGE_HOURS:
            warnings.append(f"cache_stale ({age_h:.0f}h > {CACHE_MAX_AGE_HOURS}h) ? ri-esegui --all")
    except Exception:
        pass

    _cache = {
        "registry":    registry,
        "calibration": calibration,
        "signals":     signals,
        "warnings":    warnings,
        "qualified_ids": {
            str(l["league_id"])
            for l in registry.get("qualified_leagues", [])
        },
    }
    return _cache


def reload_cache():
    """Forza il ricaricamento della cache (utile dopo un --all)."""
    global _cache
    _cache = {}
    return _load_cache()


# -- Helpers ----------------------------------------------------------------

def _parse_bookie_odd(raw_json_odds: dict, market_cfg: dict) -> Optional[float]:
    if not isinstance(raw_json_odds, dict):
        return None
    bookmakers = raw_json_odds.get("bookmakers", [])
    if not bookmakers:
        return None
    for bet in bookmakers[0].get("bets", []):
        if bet.get("name") == market_cfg["bet_name"]:
            for v in bet.get("values", []):
                if v.get("value") == market_cfg["value"]:
                    try:
                        odd = float(v["odd"])
                        return odd if odd > 1.0 else None
                    except (KeyError, ValueError, TypeError):
                        return None
    return None


def _get_ml_prob(db_json_analisi: dict, ml_market: str, ml_key: str) -> Optional[float]:
    if not isinstance(db_json_analisi, dict):
        return None
    markets = db_json_analisi.get("markets") or {}
    sub = markets.get(ml_market) or {}
    val = sub.get(ml_key)
    if val is None:
        return None
    try:
        v = float(val)
        return v / 100.0 if v > 1.0 else v
    except (TypeError, ValueError):
        return None


def _find_bracket_label(odd: float) -> Optional[str]:
    for lo, hi in ODDS_BRACKETS:
        if lo <= odd < hi:
            hi_str = "inf" if hi >= 15.0 else f"{hi:.2f}"
            return f"{lo:.2f}-{hi_str}"
    return None


def _get_calibration_correction(calibration: dict, league_id: int,
                                 mkey: str, odd: float) -> tuple[Optional[float], str]:
    """
    Ritorna (correction_factor, source).
    source: "league" | "global" | "none"
    Fallback: global se la lega non ha calibrazione per questa fascia.
    """
    brk = _find_bracket_label(odd)
    if brk is None:
        return None, "none"

    for source_key, source_label in [(f"leagues.{league_id}", "league"), ("global", "global")]:
        if "." in source_key:
            table = calibration.get("leagues", {}).get(str(league_id), {})
        else:
            table = calibration.get("global", {})
        cell = table.get(mkey, {}).get(brk)
        if cell and cell.get("n", 0) >= 5:
            return cell.get("correction_factor", 1.0), source_label

    return None, "none"


def _get_calibration_bias(calibration: dict, league_id: int,
                           mkey: str, odd: float) -> tuple[Optional[float], str]:
    """Ritorna (bias, source) dove bias = real_rate - implied_mean."""
    brk = _find_bracket_label(odd)
    if brk is None:
        return None, "none"

    for source_key, source_label in [("league", str(league_id)), ("global", "global")]:
        if source_key == "league":
            table = calibration.get("leagues", {}).get(str(league_id), {})
        else:
            table = calibration.get("global", {})
        cell = table.get(mkey, {}).get(brk)
        if cell and cell.get("n", 0) >= 5:
            return cell.get("bias", 0.0), source_label

    return None, "none"


def _xg_direction(xg: dict, mkey: str) -> Optional[int]:
    """
    +1 se xG supporta l'outcome del mercato, -1 se lo contraddice, 0 neutro.
    None se xG non disponibile.
    """
    if not xg:
        return None
    home_xg = xg.get("home_xg", 0.0)
    away_xg = xg.get("away_xg", 0.0)
    total   = home_xg + away_xg

    direction_map = {
        "1x2_H":     1 if home_xg > away_xg + 0.3 else (-1 if away_xg > home_xg + 0.3 else 0),
        "1x2_A":     1 if away_xg > home_xg + 0.3 else (-1 if home_xg > away_xg + 0.3 else 0),
        "1x2_D":     1 if abs(home_xg - away_xg) < 0.3 else 0,
        "over_2_5":  1 if total > 2.5 else (-1 if total < 1.8 else 0),
        "under_2_5": 1 if total < 1.8 else (-1 if total > 2.5 else 0),
        "btts_yes":  1 if home_xg >= 0.6 and away_xg >= 0.6 else (-1 if home_xg < 0.4 or away_xg < 0.4 else 0),
        "btts_no":   1 if home_xg < 0.4 or away_xg < 0.4 else (-1 if home_xg >= 0.6 and away_xg >= 0.6 else 0),
    }
    return direction_map.get(mkey, 0)


# -- Core scoring ------------------------------------------------------------

def score_fixture_from_row(fixture_row: dict, xg: Optional[dict] = None) -> dict:
    """
    Calcola edge scores per tutti i mercati dato un fixture dict.

    Args:
        fixture_row: dict con i campi di fixture_predictions
        xg:          opzionale {"home_xg": float, "away_xg": float}

    Returns:
        Scorecard strutturata con edge per ogni mercato.
    """
    cache     = _load_cache()
    cal       = cache["calibration"]
    sig       = cache["signals"]
    base_warn = list(cache["warnings"])

    league_id   = fixture_row.get("league_id") or 0
    raw_odds    = fixture_row.get("raw_json_odds") or {}
    db_json     = fixture_row.get("db_json_analisi") or {}

    league_qualified = str(league_id) in cache["qualified_ids"]
    if not league_qualified:
        base_warn.append(f"league_{league_id}_not_qualified_using_global_calibration")

    # Pesi segnali
    ml_sig  = sig.get("ml_divergence", {})
    xg_sig  = sig.get("xg_residual", {})
    w_ml    = ml_sig.get("weight", DEFAULT_WEIGHT_ML_DIV)
    w_xg    = xg_sig.get("weight", DEFAULT_WEIGHT_XG)
    w_total = w_ml + w_xg if (w_ml + w_xg) > 0 else 1.0

    markets_out = {}
    warnings    = list(base_warn)

    for mkey, mcfg in MARKETS.items():
        # 1. Quota bookie
        odd = _parse_bookie_odd(raw_odds, mcfg)
        if odd is None:
            continue

        implied_prob = 1.0 / odd

        # 2. Calibrazione storica
        cal_bias, cal_src = _get_calibration_bias(cal, league_id, mkey, odd)
        cal_corr, _       = _get_calibration_correction(cal, league_id, mkey, odd)
        if cal_src == "none":
            warnings.append(f"no_calibration_{mkey}")
        elif cal_src == "global":
            warnings.append(f"calibration_global_fallback_{mkey}")

        # 3. ML divergence
        ml_prob = _get_ml_prob(db_json, mcfg["ml_market"], mcfg["ml_key"])
        ml_div  = (ml_prob - implied_prob) if ml_prob is not None else None

        # 4. xG signal
        xg_dir = _xg_direction(xg, mkey)
        if xg is None:
            warnings.append(f"xg_unavailable") if f"xg_unavailable" not in warnings else None

        # 5. Composite edge
        # base_edge = bias_calibrazione + contributo ML divergenza (se disponibile)
        components = {}

        if cal_bias is not None:
            components["calibration_bias"] = cal_bias

        if ml_div is not None and w_ml > 0:
            # Scala la divergenza ML per il correction factor di calibrazione
            corr_scaled = ml_div * (cal_corr if cal_corr else 1.0)
            components["ml_divergence"] = corr_scaled

        if xg_dir is not None and w_xg > 0 and xg_sig.get("trusted"):
            # xG contribuisce come boost proporzionale alla forza del segnale storico
            xg_strength = abs(xg_sig.get("spearman_r", 0.1))
            components["xg_signal"] = xg_dir * xg_strength * 0.10  # max +-10% boost

        if not components:
            continue

        # Weighted average dei componenti
        if "calibration_bias" in components and "ml_divergence" in components:
            # Combina calibrazione (peso 0.4) + ML divergenza (peso 0.6)
            edge_raw = 0.4 * components["calibration_bias"] + 0.6 * components["ml_divergence"]
        elif "ml_divergence" in components:
            edge_raw = components["ml_divergence"]
        elif "calibration_bias" in components:
            edge_raw = components["calibration_bias"]
        else:
            edge_raw = 0.0

        # Aggiungi boost xG
        if "xg_signal" in components:
            edge_raw += components["xg_signal"]

        # Stima probabilita "vera" = implied + edge stimato
        true_prob = max(0.01, min(0.99, implied_prob + edge_raw))
        final_edge = true_prob - implied_prob

        # Soglia minima
        if abs(final_edge) < MIN_COMPOSITE_EDGE:
            final_edge = 0.0

        direction = (
            "value"   if final_edge >= MIN_COMPOSITE_EDGE else
            "avoid"   if final_edge <= -MIN_COMPOSITE_EDGE else
            "neutral"
        )

        markets_out[mkey] = {
            "odd":                   round(odd, 3),
            "implied_prob":          round(implied_prob, 4),
            "ml_prob":               round(ml_prob, 4) if ml_prob is not None else None,
            "ml_divergence":         round(ml_div, 4) if ml_div is not None else None,
            "calibration_bias":      round(cal_bias, 4) if cal_bias is not None else None,
            "calibration_source":    cal_src,
            "xg_direction":          xg_dir,
            "true_prob_estimate":    round(true_prob, 4),
            "composite_edge":        round(final_edge, 4),
            "signal_contributions":  {k: round(v, 4) for k, v in components.items()},
            "direction":             direction,
            "actionable":            abs(final_edge) >= MIN_COMPOSITE_EDGE,
        }

    actionable = {k: v for k, v in markets_out.items() if v["actionable"]}

    return {
        "fixture_id":       fixture_row.get("fixture_id"),
        "league_id":        league_id,
        "league_name":      fixture_row.get("league_name", ""),
        "home_team":        fixture_row.get("home_team_name", ""),
        "away_team":        fixture_row.get("away_team_name", ""),
        "fixture_date":     str(fixture_row.get("fixture_date", ""))[:16],
        "league_qualified": league_qualified,
        "scored_at":        datetime.now(timezone.utc).isoformat(),
        "xg_available":     xg is not None,
        "markets":          markets_out,
        "actionable":       actionable,
        "n_actionable":     len(actionable),
        "warnings":         list(set(warnings)),
    }


class EdgeScorer:
    """
    Classe principale per lo scoring. Gestisce il fetch dal DB e la cache.
    """

    def __init__(self):
        _load_cache()  # Pre-carica la cache all'inizializzazione

    def score(self, fixture_id: int) -> dict:
        """Fetch dal DB e score."""
        row = self._fetch_fixture(fixture_id)
        if not row:
            return {"error": f"Fixture {fixture_id} non trovata nel DB"}
        xg = self._fetch_xg(fixture_id, row)
        return score_fixture_from_row(row, xg)

    def score_from_dict(self, fixture_row: dict, xg: Optional[dict] = None) -> dict:
        """Score da un dict gia caricato (evita round-trip DB)."""
        return score_fixture_from_row(fixture_row, xg)

    def _fetch_fixture(self, fixture_id: int) -> Optional[dict]:
        from db_client import get_supabase_client
        sb = get_supabase_client()
        resp = sb.table("fixture_predictions").select(
            "fixture_id, league_id, league_name, fixture_date, "
            "home_team_name, away_team_name, home_team_id, away_team_id, "
            "raw_json_odds, db_json_analisi, result_status_short"
        ).eq("fixture_id", fixture_id).limit(1).execute()
        rows = resp.data or []
        return rows[0] if rows else None

    def _fetch_xg(self, fixture_id: int, fixture_row: dict) -> Optional[dict]:
        """Tenta di caricare xG da match_team_stats."""
        try:
            from db_client import get_supabase_client
            sb = get_supabase_client()
            home_tid = fixture_row.get("home_team_id")
            away_tid = fixture_row.get("away_team_id")
            resp = sb.table("match_team_stats").select(
                "team_id, value_numeric"
            ).eq("fixture_id", fixture_id).eq("stat_type", "Expected Goals").execute()
            result = {}
            for r in (resp.data or []):
                val = r.get("value_numeric")
                if val is None:
                    continue
                if r["team_id"] == home_tid:
                    result["home_xg"] = float(val)
                elif r["team_id"] == away_tid:
                    result["away_xg"] = float(val)
            return result if result else None
        except Exception:
            return None

    def print_scorecard(self, result: dict):
        """Stampa una scorecard formattata a terminale."""
        if "error" in result:
            print(f"\n  Errore: {result['error']}")
            return

        home = result.get("home_team", "?")
        away = result.get("away_team", "?")
        date = result.get("fixture_date", "")
        league = result.get("league_name", "")
        fid = result.get("fixture_id", "?")
        qual_flag = "OK" if result.get("league_qualified") else "~global"
        xg_flag   = "xG:OK" if result.get("xg_available") else "xG:X"

        def _s(t): return str(t).encode('ascii', 'replace').decode('ascii')
        home, away, league = _s(home), _s(away), _s(league)
        print("\n" + "=" * 68)
        print(f"  {home} vs {away}")
        print(f"  {league}  |  {date}  |  ID:{fid}  |  cal:{qual_flag}  {xg_flag}")
        print("=" * 68)
        print(f"  {'Mercato':<12} {'Odd':>5}  {'Implied':>8} {'ML':>7} {'MLdiv':>7} "
              f"{'CalBias':>8} {'Edge':>7}  {'Dir'}")
        print(f"  {'-'*65}")

        for mkey, s in result["markets"].items():
            ml_s    = f"{s['ml_prob']:.1%}"    if s["ml_prob"]    is not None else "  N/A "
            div_s   = f"{s['ml_divergence']:+.1%}" if s["ml_divergence"] is not None else "   N/A"
            bias_s  = f"{s['calibration_bias']:+.1%}" if s["calibration_bias"] is not None else "    N/A"
            edge_s  = f"{s['composite_edge']:+.1%}"
            marker  = " <" if s["actionable"] else ""
            xg_s    = f"xG{s['xg_direction']:+d}" if s["xg_direction"] is not None else ""
            dir_s   = s["direction"] + marker + (f"  {xg_s}" if xg_s else "")
            print(f"  {mkey:<12} {s['odd']:>5.2f}  {s['implied_prob']:>7.1%} "
                  f"{ml_s:>7} {div_s:>7} {bias_s:>8} {edge_s:>7}  {dir_s}")

        if result["actionable"]:
            print(f"\n  -- AZIONABILI ({result['n_actionable']}) --------------------------")
            for mkey, s in sorted(result["actionable"].items(),
                                  key=lambda x: -abs(x[1]["composite_edge"])):
                contr = "  ".join(f"{k}={v:+.3f}" for k, v in s["signal_contributions"].items())
                print(f"  {mkey:<12} edge={s['composite_edge']:+.1%} @ {s['odd']:.2f}  "
                      f"[{contr}]")
        else:
            print(f"\n  Nessun edge azionabile (soglia: +-{MIN_COMPOSITE_EDGE:.0%})")

        if result.get("warnings"):
            # Mostra solo warning rilevanti (non i globali-fallback di routine)
            important = [w for w in result["warnings"] if "stale" in w or "unavailable" in w]
            if important:
                print(f"\n  \!  {' | '.join(important)}")

        print("=" * 68)
