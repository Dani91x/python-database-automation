"""
pipeline.py ? Market Intelligence CLI

Punto di ingresso unico per tutte le fasi.

Uso:
    python -m market_intelligence.pipeline --audit
    python -m market_intelligence.pipeline --calibration
    python -m market_intelligence.pipeline --signals
    python -m market_intelligence.pipeline --all
    python -m market_intelligence.pipeline --score 1234567
    python -m market_intelligence.pipeline --score-today
    python -m market_intelligence.pipeline --status
"""
import sys, argparse, json
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from market_intelligence.mi_config import (
    REGISTRY_FILE, CALIBRATION_FILE, SIGNAL_WEIGHTS_FILE
)


# -- Prerequisiti -------------------------------------------------------------

def _require(path: Path, phase_name: str, run_cmd: str):
    if not path.exists():
        print(f"\n  ERRORE: {path.name} non trovato.")
        print(f"  Esegui prima: python -m market_intelligence.pipeline {run_cmd}")
        sys.exit(1)


# -- Comandi -------------------------------------------------------------------

def cmd_audit():
    from market_intelligence.audit import run_audit
    result = run_audit()
    n = len(result.get("qualified_leagues", []))
    print(f"\n  OK Audit completato: {n} leghe qualificate")
    return result


def cmd_calibration():
    _require(REGISTRY_FILE, "calibration", "--audit")
    from market_intelligence.calibration import run_calibration
    result = run_calibration()
    n = len(result.get("leagues", {}))
    print(f"\n  OK Calibrazione completata: {n} leghe + globale")
    return result


def cmd_signals():
    _require(REGISTRY_FILE, "signals", "--audit")
    from market_intelligence.signals import run_signals
    result = run_signals()
    ml_ok = result.get("ml_divergence", {}).get("1x2_H", {}).get("trusted", False)
    xg_ok = result.get("xg_residual", {}).get("trusted", False)
    print(f"\n  OK Segnali validati: ML={('OK' if ml_ok else 'X')}  xG={('OK' if xg_ok else 'X')}")
    return result


def cmd_all():
    """Esegue tutte e tre le fasi in sequenza."""
    print("\n  Esecuzione completa: audit -> calibration -> signals\n")
    cmd_audit()
    print()
    cmd_calibration()
    print()
    cmd_signals()
    print("\n  OK Pipeline completata. Cache pronta.")


def cmd_score(fixture_id: int):
    _require(CALIBRATION_FILE, "score", "--all")
    from market_intelligence.edge_scorer import EdgeScorer
    scorer = EdgeScorer()
    result = scorer.score(fixture_id)
    scorer.print_scorecard(result)
    return result


def cmd_score_today():
    _require(CALIBRATION_FILE, "score-today", "--all")

    from db_client import get_supabase_client
    from market_intelligence.edge_scorer import EdgeScorer, score_fixture_from_row

    sb    = get_supabase_client()
    today    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"\n  Fetching partite per {today}...")
    resp = sb.table("fixture_predictions").select(
        "fixture_id, league_id, league_name, fixture_date, "
        "home_team_name, away_team_name, home_team_id, away_team_id, "
        "raw_json_odds, db_json_analisi, result_status_short"
    ).gte("fixture_date", today).lt("fixture_date", tomorrow).execute()

    fixtures = resp.data or []
    # Tieni solo quelle con quote disponibili
    with_odds = [f for f in fixtures if f.get("raw_json_odds") and
                 isinstance(f.get("raw_json_odds"), dict) and
                 f["raw_json_odds"].get("bookmakers")]
    print(f"  Totale: {len(fixtures)}  |  Con quote: {len(with_odds)}")

    if not with_odds:
        print("  Nessuna partita con quote trovata per oggi.")
        return []

    scorer  = EdgeScorer()
    results = []
    for f in with_odds:
        # Tenta fetch xG (post-match, se disponibile)
        xg = scorer._fetch_xg(f["fixture_id"], f)
        r  = score_fixture_from_row(f, xg)
        results.append(r)

    # Ordina per n_actionable DESC
    results.sort(key=lambda x: -x.get("n_actionable", 0))

    n_act = sum(1 for r in results if r.get("n_actionable", 0) > 0)
    print(f"\n  Partite con segnali azionabili: {n_act} / {len(results)}")

    for r in results:
        if r.get("n_actionable", 0) > 0:
            scorer.print_scorecard(r)

    if n_act == 0:
        print("\n  Nessun segnale azionabile trovato oggi.")

    return results


def cmd_status():
    """Mostra lo stato della cache e un riassunto del registry."""
    print("\n  MARKET INTELLIGENCE ? Status")
    print("  " + "-" * 50)

    for label, path in [
        ("league_registry.json",    REGISTRY_FILE),
        ("calibration_tables.json", CALIBRATION_FILE),
        ("signal_weights.json",     SIGNAL_WEIGHTS_FILE),
    ]:
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                gen = data.get("generated_at", "unknown")[:19]
                size_kb = path.stat().st_size // 1024
                print(f"  OK {label:<30} {gen}  ({size_kb} KB)")
            except Exception:
                print(f"  ? {label:<30} (errore lettura)")
        else:
            print(f"  X {label:<30} MANCANTE ? esegui --all")

    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, encoding="utf-8") as f:
            reg = json.load(f)
        qualified = reg.get("qualified_leagues", [])
        total     = reg.get("total_finished", 0)
        print(f"\n  Partite finite nel DB:    {total}")
        print(f"  Leghe qualificate (>=80):  {len(qualified)}")
        if qualified:
            print(f"\n  {'Lega':<36} {'Odds':>6} {'ML':>6} {'xG':>6}")
            print(f"  {'-'*52}")
            for l in sorted(qualified, key=lambda x: -x["n_with_odds"])[:15]:
                print(f"  {l['league_name']:<36} {l['n_with_odds']:>6} "
                      f"{l['n_with_ml']:>6} {l['n_with_xg']:>6}")
            if len(qualified) > 15:
                print(f"  ... e altre {len(qualified) - 15} leghe")

    if SIGNAL_WEIGHTS_FILE.exists():
        with open(SIGNAL_WEIGHTS_FILE, encoding="utf-8") as f:
            sw = json.load(f)
        ml_w = sw.get("ml_divergence", {}).get("weight", 0)
        xg_w = sw.get("xg_residual", {}).get("weight", 0)
        fb   = sw.get("fallback_mode", False)
        print(f"\n  Pesi segnali: ML={ml_w:.2f}  xG={xg_w:.2f}"
              f"  {'[FALLBACK]' if fb else ''}")


# -- Main ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="market_intelligence",
        description="Market Intelligence Pipeline ? analisi edge su quote + ML + xG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  Prima esecuzione:
    python -m market_intelligence.pipeline --all

  Aggiornamento dopo nuovi dati:
    python -m market_intelligence.pipeline --all

  Scorare una partita specifica:
    python -m market_intelligence.pipeline --score 1234567

  Scorare tutte le partite di oggi:
    python -m market_intelligence.pipeline --score-today

  Verificare stato cache:
    python -m market_intelligence.pipeline --status
        """
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--audit",        action="store_true",  help="Phase 1: audit dati e league registry")
    group.add_argument("--calibration",  action="store_true",  help="Phase 2: tabelle calibrazione")
    group.add_argument("--signals",      action="store_true",  help="Phase 3: validazione segnali ML+xG")
    group.add_argument("--all",          action="store_true",  help="Esegui tutte le fasi (audit+cal+signals)")
    group.add_argument("--score",        type=int, metavar="ID", help="Scorare una partita per fixture_id")
    group.add_argument("--score-today",  action="store_true",  help="Scorare tutte le partite di oggi")
    group.add_argument("--status",       action="store_true",  help="Mostra stato cache e statistiche")

    args = parser.parse_args()

    if args.audit:
        cmd_audit()
    elif args.calibration:
        cmd_calibration()
    elif args.signals:
        cmd_signals()
    elif args.all:
        cmd_all()
    elif args.score:
        cmd_score(args.score)
    elif args.score_today:
        cmd_score_today()
    elif args.status:
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
