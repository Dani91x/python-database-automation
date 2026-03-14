"""
bss_monitor.py — Monitoraggio degradazione BSS in produzione.

Confronta il Brier proxy calcolato sui segnali ML reali (mm_history.json)
con la soglia minima MIN_BSS_THRESHOLD=0.12.

Uso manuale:
    python -m ai_engine.bss_monitor

Output:
  - Report a terminale
  - Alert nel log se BSS proxy < soglia
  - Suggerimento retraining se necessario

Note:
  Il BSS proxy usa solo la probabilità assegnata alla classe predetta
  (non la distribuzione completa), quindi è una stima conservativa.
  Un BSS proxy < 0.08 indica degradazione seria.
  Un BSS proxy > 0.12 indica modello ancora valido.
"""
from __future__ import annotations
import os, sys, json, math
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HISTORY_FILE = ROOT / "Betfair" / "mm_history.json"
MIN_BSS_THRESHOLD = 0.12    # stesso valore di confidence_gate.py e scan_best_market_ml
ALERT_THRESHOLD   = 0.08    # sotto questa soglia: alert critico
MIN_SAMPLES       = 20      # campione minimo per fidarsi della stima


def load_history() -> list:
    if not HISTORY_FILE.exists():
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_bss_proxy(history: list) -> dict[str, dict]:
    """
    Per ogni mercato ML, calcola:
      - n: scommesse risolte
      - brier: mean squared error tra prob e outcome
      - win_rate: tasso vittoria reale
      - avg_prob: probabilità media prevista
      - calibration_error: |avg_prob - win_rate|  (valore assoluto di bias)
      - bss_proxy: 1 - brier / brier_baseline  (baseline = sempre predire avg_prob)
    """
    by_market: dict[str, dict] = {}

    for day in history:
        for slot in day.get("ml_slots", []):
            result_str = slot.get("result", "PENDING")
            if "VINTO" in result_str:
                outcome = 1
            elif "PERSO" in result_str:
                outcome = 0
            else:
                continue

            prob   = slot.get("prob")
            market = slot.get("market_label", slot.get("market", "unknown"))
            if prob is None:
                continue

            if market not in by_market:
                by_market[market] = {"sq_errors": [], "probs": [], "outcomes": []}

            by_market[market]["sq_errors"].append((prob - outcome) ** 2)
            by_market[market]["probs"].append(prob)
            by_market[market]["outcomes"].append(outcome)

    result = {}
    for market, data in by_market.items():
        n = len(data["sq_errors"])
        if n < MIN_SAMPLES:
            result[market] = {"n": n, "status": "INSUFFICIENT_DATA", "min_samples": MIN_SAMPLES}
            continue

        brier      = sum(data["sq_errors"]) / n
        win_rate   = sum(data["outcomes"]) / n
        avg_prob   = sum(data["probs"]) / n
        cal_error  = abs(avg_prob - win_rate)
        # Baseline Brier = always predict avg_prob → (avg_prob*(1-avg_prob))
        brier_base = avg_prob * (1.0 - avg_prob)
        bss_proxy  = 1.0 - (brier / brier_base) if brier_base > 0 else None

        status = "OK"
        if bss_proxy is None:
            status = "UNKNOWN"
        elif bss_proxy < ALERT_THRESHOLD:
            status = "CRITICAL"
        elif bss_proxy < MIN_BSS_THRESHOLD:
            status = "DEGRADED"

        result[market] = {
            "n":                n,
            "brier":            round(brier, 4),
            "bss_proxy":        round(bss_proxy, 3) if bss_proxy is not None else None,
            "win_rate":         round(win_rate, 3),
            "avg_prob":         round(avg_prob, 3),
            "calibration_error": round(cal_error, 3),
            "status":           status,
        }

    return result


def print_report(metrics: dict[str, dict]):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*64}")
    print(f"  BSS MONITOR — Produzione ML  |  {now}")
    print(f"  Soglia: BSS_proxy >= {MIN_BSS_THRESHOLD}  |  Alert: < {ALERT_THRESHOLD}")
    print(f"{'='*64}")

    if not metrics:
        print("  Nessun dato disponibile (history vuota o nessun ML risolto).")
        return

    print(f"  {'Mercato':<22} {'N':>5}  {'Brier':>7} {'BSSproxy':>9} {'WinRate':>8} {'AvgProb':>8} {'CalErr':>7}  Status")
    print(f"  {'-'*64}")

    alerts = []
    for market, d in sorted(metrics.items(), key=lambda x: (x[1].get("status",""), -x[1].get("n", 0))):
        if d.get("status") == "INSUFFICIENT_DATA":
            print(f"  {market:<22} {d['n']:>5}  {'—':>7} {'—':>9} {'—':>8} {'—':>8} {'—':>7}  ⚠️ dati insuff. (min={d['min_samples']})")
            continue

        bss_s   = f"{d['bss_proxy']:.3f}" if d['bss_proxy'] is not None else "N/A"
        status_icon = {"OK": "✅", "DEGRADED": "⚠️", "CRITICAL": "🚨", "UNKNOWN": "?"}.get(d["status"], "?")
        print(f"  {market:<22} {d['n']:>5}  {d['brier']:>7.4f} {bss_s:>9} "
              f"{d['win_rate']:>7.1%} {d['avg_prob']:>7.1%} {d['calibration_error']:>7.3f}  {status_icon} {d['status']}")

        if d["status"] in ("DEGRADED", "CRITICAL"):
            alerts.append((market, d))

    print(f"\n  {'='*64}")
    if alerts:
        print(f"\n  🚨 DEGRADAZIONE RILEVATA su {len(alerts)} mercati:")
        for market, d in alerts:
            print(f"     {market}: BSS_proxy={d['bss_proxy']} | win_rate={d['win_rate']:.1%} vs avg_prob={d['avg_prob']:.1%}")
        print()
        print("  ACTION: esegui manualmente l'addestramento:")
        print("  > python -m ai_engine.ensemble_trainer")
        print()
        print("  Oppure per singola lega:")
        print("  > python -m ai_engine.ensemble_trainer --league <league_id>")
    else:
        ok_markets = [m for m, d in metrics.items() if d.get("status") == "OK"]
        print(f"\n  ✅ Tutti i mercati nella norma ({len(ok_markets)} validati).")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    history = load_history()
    total_days   = len(history)
    total_ml_bets = sum(len(d.get("ml_slots", [])) for d in history)
    resolved     = sum(
        1 for d in history for s in d.get("ml_slots", [])
        if s.get("result") not in ("PENDING", None, "")
    )
    print(f"\n  Storico: {total_days} giorni | {total_ml_bets} ML bet totali | {resolved} risolti")

    metrics = compute_bss_proxy(history)
    print_report(metrics)
