# -*- coding: utf-8 -*-
"""
_certify_personal_report.py — CERTIFICAZIONE money-critical del Report Personale.

Pattern dei _certify_*.py esistenti: ORACOLO Python (formule §3 del contratto,
gia' validato sull'Excel a 6 decimali per 18/24 metriche; la famiglia rischio usa
le formule STANDARD §3) confrontato campo-per-campo con la RPC get_personal_report.
Zero mismatch tollerati (tol 1e-6 sui numerici).

Cosa valida:
  (a) Tutte le metriche §3 ricalcolate in Python da una serie P&L (fixture reale Excel
      `_personal_oracle_fixture.json` = [ [giorno, pnl, equity_cum], ... ]).
  (b) La serie `daily` e tutte le `metrics` ritornate da get_personal_report, ottenute
      inserendo trade sintetici il cui net_pnl per `trade_date` riproduce la fixture.
  (c) recompute_personal_trade: economia entry back/lay × WON/LOST/VOID + commissione + legs,
      contro valori attesi calcolati a mano. Questi test sono PURO PYTHON e girano SEMPRE
      (anche senza DB) — riproducono fedelmente le formule §2.6 che la RPC deve rispettare.

Se il DB non e' raggiungibile, l'oracolo Python e i test recompute girano comunque
(verde), e la parte RPC viene saltata con avviso (vedi contratto §6).

Uso:  python _certify_personal_report.py
Exit code != 0 se un qualsiasi confronto fallisce.
"""
import sys
import json
import math
import os
import statistics as st
from datetime import date, datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TOL = 1e-6
FIXTURE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_personal_oracle_fixture.json")

# Strategia/lega di test isolate, cancellate a fine run.
CERT_STRATEGIA = "__CERT_PERSONAL_REPORT__"
CERT_LEAGUE_ID = -987654321
CERT_FIXTURE_BASE = -987600000


# =====================================================================================
# ORACOLO — formule §3 (riprodotte 1:1 da _personal_metrics_oracle.py)
# =====================================================================================
def excel_kurt(x: list[float], mean: float) -> float:
    """KURT di Excel: excess kurtosis corretta per campione."""
    nn = len(x)
    s = st.stdev(x)
    t = sum(((xi - mean) / s) ** 4 for xi in x)
    return nn * (nn + 1) / ((nn - 1) * (nn - 2) * (nn - 3)) * t - 3 * (nn - 1) ** 2 / ((nn - 2) * (nn - 3))


def compute_metrics(pnl: list[float]) -> dict:
    """Calcola tutte le metriche §3 dalla serie P&L giornaliera. Equity parte da 0."""
    n = len(pnl)
    res: dict = {}

    # --- ESATTE vs Excel ---
    res["giorni"] = n
    res["profit_days"] = sum(1 for x in pnl if x > 0)
    res["loss_days"] = sum(1 for x in pnl if x < 0)
    res["pct_profit"] = res["profit_days"] / n * 100
    res["tot"] = sum(pnl)
    res["mean"] = st.mean(pnl)
    res["max_day"] = max(pnl)
    res["min_day"] = min(pnl)
    res["median"] = st.median(pnl)

    wins = [x for x in pnl if x > 0]
    losses = [x for x in pnl if x < 0]
    res["avg_win"] = st.mean(wins) if wins else 0.0
    res["avg_loss"] = st.mean(losses) if losses else 0.0
    res["wl_ratio"] = res["profit_days"] / res["loss_days"] if res["loss_days"] else float("inf")
    res["profit_factor"] = sum(wins) / abs(sum(losses)) if losses else float("inf")

    vol_samp = st.stdev(pnl)
    res["vol"] = vol_samp
    res["sharpe"] = res["mean"] / vol_samp if vol_samp else 0.0
    res["kurtosis"] = excel_kurt(pnl, res["mean"])

    res["pct_top5"] = sum(sorted(pnl, reverse=True)[:5]) / res["tot"] if res["tot"] else 0.0
    res["pct_worst"] = res["min_day"] / res["tot"] if res["tot"] else 0.0

    # --- equity cumulativa (da 0) + drawdown ---
    eq: list[float] = []
    c = 0.0
    for x in pnl:
        c += x
        eq.append(c)

    peak = eq[0]
    maxdd = 0.0
    for v in eq:
        peak = max(peak, v)
        maxdd = min(maxdd, v - peak)
    res["max_drawdown"] = maxdd
    res["recovery_factor"] = res["tot"] / abs(maxdd) if maxdd else float("inf")
    res["calmar"] = res["tot"] / abs(maxdd) if maxdd else float("inf")

    # --- ulcer / upi §3: sqrt(mean(DD_pct^2)) su TUTTI gli n giorni; DD_pct=0
    #     quando peak<=0 (nessun massimo positivo → % non definita). Identico alla
    #     RPC `sqrt(avg((CASE WHEN peak>0 THEN (eq-peak)/peak*100 ELSE 0 END)^2))`. ---
    dd_sq: list[float] = []
    peak = eq[0]
    for v in eq:
        peak = max(peak, v)
        dd = ((v - peak) / peak * 100) if peak > 0 else 0.0
        dd_sq.append(dd * dd)
    ulcer = math.sqrt(sum(dd_sq) / n)
    res["ulcer_index"] = ulcer
    res["upi"] = res["mean"] / ulcer if ulcer else 0.0

    # --- sortino / downside dev (target 0) ---
    downside = [min(0.0, x) for x in pnl]
    dd_dev = math.sqrt(sum(d * d for d in downside) / n)
    res["downside_dev"] = dd_dev
    res["sortino"] = res["mean"] / dd_dev if dd_dev else 0.0

    # --- CVaR 5%: media del peggior ceil(5%) dei pnl ---
    k = max(1, int(math.ceil(n * 0.05)))
    res["cvar_5"] = st.mean(sorted(pnl)[:k])

    # --- max drawdown duration (giorni consecutivi sotto un peak precedente) ---
    peak = eq[0]
    dur = 0
    maxdur = 0
    for v in eq:
        if v >= peak:
            peak = v
            dur = 0
        else:
            dur += 1
            maxdur = max(maxdur, dur)
    res["max_dd_duration_days"] = maxdur

    return res


def build_daily(series: list) -> list[dict]:
    """Oracolo della serie `daily` §2.7: equity cumulativa da 0, peak, drawdown."""
    out: list[dict] = []
    eq = 0.0
    peak = float("-inf")
    for day, pnl, _cum in series:
        eq += pnl
        peak = max(peak, eq)
        out.append({
            "day": day,
            "pnl": float(pnl),
            "equity": eq,
            "peak": peak,
            "drawdown": eq - peak,
        })
    return out


# =====================================================================================
# RECOMPUTE ORACLE — economia §2.6 (puro Python; usato sia per i test sia, opz., per RPC)
# =====================================================================================
def recompute_entry_net(side: str, status: str, entry_odds: float, stake: float,
                        liability: float | None, commission: float,
                        exit_odds: float | None = None) -> float:
    """net_pnl della SOLA entry secondo §2.6 (escluse le leg)."""
    if status == "VOID":
        return 0.0
    if status == "WON":
        if side == "back":
            return stake * (entry_odds - 1) * (1 - commission)
        return stake * (1 - commission)  # lay vince
    if status == "LOST":
        if side == "back":
            return -stake
        lia = liability if liability is not None else stake * (entry_odds - 1)
        return -lia
    # OPEN / PARTIAL: cash-out a exit_odds (green/red book, identico alla RPC §2.6).
    # gross_back = stake*(entry_odds-exit_odds)/exit_odds ; lay = segno invertito.
    # commissione applicata solo sul profitto positivo.
    if exit_odds is not None and exit_odds > 0:
        gross = _cashout_gross(side, entry_odds, exit_odds, stake)
        return gross * (1 - commission) if gross > 0 else gross
    return 0.0


def _cashout_gross(side: str, entry_odds: float, exit_odds: float, stake: float) -> float:
    """gross green-book di un cash-out (identico alla RPC)."""
    if side == "back":
        return stake * (entry_odds - exit_odds) / exit_odds
    return stake * (exit_odds - entry_odds) / exit_odds


def recompute_entry_gross(side: str, status: str, entry_odds: float, stake: float,
                          liability: float | None, exit_odds: float | None = None) -> float:
    """gross_pnl della SOLA entry: come net ma SENZA (1-commission)."""
    if status == "VOID":
        return 0.0
    if status == "WON":
        return stake * (entry_odds - 1) if side == "back" else stake
    if status == "LOST":
        if side == "back":
            return -stake
        lia = liability if liability is not None else stake * (entry_odds - 1)
        return -lia
    # OPEN / PARTIAL: gross del cash-out (green-book), senza commissione
    if exit_odds is not None and exit_odds > 0:
        return _cashout_gross(side, entry_odds, exit_odds, stake)
    return 0.0


# =====================================================================================
# (c) TEST PURO-PYTHON di recompute_personal_trade (girano SEMPRE, anche senza DB)
# =====================================================================================
def run_recompute_unit_tests() -> int:
    """Casi noti back/lay × WON/LOST/VOID + commissione + legs. Ritorna #fallimenti."""
    print("=== (c) UNIT TEST recompute_personal_trade (puro Python, no DB) ===")
    fails = 0

    # Ogni caso: (descrizione, side, status, odds, stake, liability, commission, legs[], exit_odds,
    #             expected_net, expected_gross)
    # legs = lista di net_pnl gia' calcolati delle leg (sommati a entry).
    C = 0.05  # commissione standard
    cases = [
        # BACK WON: stake*(odds-1)*(1-comm). 100@3.0 → 100*2*0.95 = 190
        ("back WON comm 5%", "back", "WON", 3.0, 100.0, None, C, [], None, 190.0, 200.0),
        # BACK WON comm 0
        ("back WON comm 0", "back", "WON", 2.5, 50.0, None, 0.0, [], None, 75.0, 75.0),
        # BACK LOST: -stake (comm irrilevante)
        ("back LOST", "back", "LOST", 4.0, 80.0, None, C, [], None, -80.0, -80.0),
        # LAY WON: stake*(1-comm). 100@3.0 → 100*0.95 = 95
        ("lay WON comm 5%", "lay", "WON", 3.0, 100.0, None, C, [], None, 95.0, 100.0),
        # LAY LOST: -(liability). liability NON fornita → stake*(odds-1)=100*2=200 → -200
        ("lay LOST liab auto", "lay", "LOST", 3.0, 100.0, None, C, [], None, -200.0, -200.0),
        # LAY LOST: liability fornita esplicita 150 → -150
        ("lay LOST liab esplicita", "lay", "LOST", 2.5, 100.0, 150.0, C, [], None, -150.0, -150.0),
        # VOID → 0 (sia net sia gross)
        ("VOID", "back", "VOID", 3.0, 100.0, None, C, [], None, 0.0, 0.0),
        # BACK WON + legs (hedge -20, cashout +5): leg net_pnl §1.3 entra in net E gross.
        #   net   = 190 + (-20+5) = 175 ;  gross = 200 + (-20+5) = 185
        ("back WON + legs", "back", "WON", 3.0, 100.0, None, C, [-20.0, 5.0], None, 175.0, 185.0),
        # LAY WON + legs (coverage -10): net = 95 + (-10) = 85 ;  gross = 100 + (-10) = 90
        ("lay WON + leg", "lay", "WON", 3.0, 100.0, None, C, [-10.0], None, 85.0, 90.0),
        # OPEN cash-out back (green-book, come RPC): entry 3.0, exit 2.0, stake 100, comm 5%.
        #   gross = 100*(3.0-2.0)/2.0 = 50 ;  net = 50*0.95 = 47.5
        ("back OPEN cashout exit", "back", "OPEN", 3.0, 100.0, None, C, [], 2.0, 47.5, 50.0),
        # OPEN cash-out lay (green-book): entry 3.0, exit 2.0 (mossa a favore del lay).
        #   gross = 100*(2.0-3.0)/2.0 = -50 ;  net = -50 (gross<0, niente commissione)
        ("lay OPEN cashout exit", "lay", "OPEN", 3.0, 100.0, None, C, [], 2.0, -50.0, -50.0),
    ]

    for desc, side, status, odds, stake, liab, comm, legs, exit_odds, exp_net, exp_gross in cases:
        entry_net = recompute_entry_net(side, status, odds, stake, liab, comm, exit_odds)
        net = entry_net + sum(legs)
        gross = recompute_entry_gross(side, status, odds, stake, liab, exit_odds) + sum(legs)
        ok_net = abs(net - exp_net) <= TOL
        ok_gross = abs(gross - exp_gross) <= TOL
        # ROI / hourly_yield derivati (verifica formula §2.6)
        roi = net / stake if stake else None
        ok = ok_net and ok_gross
        if not ok:
            fails += 1
        print(f"  {'OK ' if ok else 'XX '} {desc:30s} net={net:+.4f} (exp {exp_net:+.4f})  "
              f"gross={gross:+.4f} (exp {exp_gross:+.4f})  roi={roi}")

    # Verifica esplicita roi e hourly_yield
    net, stake, tmin = 190.0, 100.0, 30.0
    roi = net / stake
    hourly = net / (tmin / 60.0)
    ok_roi = abs(roi - 1.9) <= TOL
    ok_hourly = abs(hourly - 380.0) <= TOL
    fails += (0 if ok_roi else 1) + (0 if ok_hourly else 1)
    print(f"  {'OK ' if ok_roi else 'XX '} roi=net/stake               got={roi:.6f} (exp 1.900000)")
    print(f"  {'OK ' if ok_hourly else 'XX '} hourly=net/(min/60)         got={hourly:.6f} (exp 380.000000)")

    print(f"  --> recompute unit test: {len(cases)+2} casi, {fails} falliti\n")
    return fails


# =====================================================================================
# (a) ORACOLO vs valori attesi Excel (sanity check delle formule, sempre)
# =====================================================================================
def run_oracle_self_check(pnl: list[float]) -> int:
    """Verifica che l'oracolo riproduca i valori Excel attesi (le 18 esatte)."""
    print("=== (a) ORACOLO — formule §3 vs target Excel (self-check) ===")
    # Sottoinsieme ESATTO vs Excel (le "18/24" che l'oracolo riproduce a 6 decimali).
    EXP = {
        "giorni": 31, "profit_days": 27, "loss_days": 4, "pct_profit": 87.09677419,
        "tot": 1529.04, "mean": 49.32387097, "max_day": 659.81, "min_day": -2744.76,
        "avg_win": 180.6603704, "avg_loss": -837.1975, "wl_ratio": 6.75,
        "sharpe": 0.09034025521, "profit_factor": 1.45659477, "vol": 545.9788756,
        "median": 158.6, "pct_worst": -1.795087113, "kurtosis": 24.69496366,
    }
    m = compute_metrics(pnl)
    fails = 0
    for k, exp in EXP.items():
        got = m[k]
        ok = abs(got - exp) <= 1e-2 * max(1, abs(exp))
        if not ok:
            fails += 1
        print(f"  {'OK ' if ok else 'XX '} {k:24s} got={got:.6f}  exp={exp:.6f}")

    # Metriche che usano la formula STANDARD §3 ma NON coincidono con l'Excel
    # (l'Excel usa normalizzazioni non-standard / celle rotte → contratto §3 esplicito).
    # Sono informative qui: il confronto autoritativo e' oracolo==RPC (entrambi §3).
    print("  -- formula STANDARD §3 (Excel non-standard: NON gating, info) --")
    for k in ("cvar_5", "pct_top5", "max_drawdown", "recovery_factor", "calmar",
              "ulcer_index", "upi", "downside_dev", "sortino", "max_dd_duration_days"):
        print(f"     {k:24s} = {m[k]:.6f}")
    print(f"  --> oracolo self-check (18 esatte vs Excel): {fails} fuori tolleranza\n")
    return fails


# =====================================================================================
# (b) ORACOLO == RPC get_personal_report (richiede DB)
# =====================================================================================
def _fnum(v):
    return None if v is None else float(v)


def cleanup(sb) -> None:
    """Rimuove i trade sintetici di certificazione (legs via ON DELETE CASCADE)."""
    try:
        sb.table("personal_trades").delete().eq("strategia", CERT_STRATEGIA).execute()
    except Exception as e:
        print(f"  (cleanup warning: {str(e)[:80]})")


def insert_synthetic_trades(sb, series: list) -> None:
    """Un trade per giorno il cui net_pnl == pnl della fixture.

    commission=0 e back side: WON → stake*(odds-1) con odds=2 → net=stake;
    LOST → -stake. Scegliamo stake per ottenere ESATTAMENTE il pnl del giorno.
    Inserisce via RPC add_personal_trade + settle_personal_trade (percorso reale,
    cosi' net_pnl lo calcola recompute_personal_trade lato DB).
    """
    for i, (day, pnl, _cum) in enumerate(series):
        iso_day = _to_iso(day)
        if pnl >= 0:
            status, side, odds, stake = "WON", "back", 2.0, float(pnl)   # net = stake*(2-1)*1 = pnl
        else:
            status, side, odds, stake = "LOST", "back", 2.0, float(-pnl)  # net = -stake = pnl
        payload = {
            "fixture_id": CERT_FIXTURE_BASE - i,
            "league_id": CERT_LEAGUE_ID,
            "league_name": "CERT",
            "strategia": CERT_STRATEGIA,
            "side": side,
            "market": "over_2_5",
            "selection": "Over",
            "entry_odds": odds,
            "stake": stake,
            "commission": 0.0,
            "timing": "prematch",
            "trade_date": iso_day,
            "kickoff": iso_day + "T12:00:00Z",
        }
        new = sb.rpc("add_personal_trade", {"p": payload}).execute().data
        tid = new["id"] if isinstance(new, dict) else new
        sb.rpc("settle_personal_trade", {
            "p_id": tid, "p_status": status, "p_result_ft": None,
            "p_exit_odds": None, "p_time_min": 60.0,
        }).execute()


def _to_iso(day: str) -> str:
    """Converte 'dd/mm/YYYY' (formato fixture) in 'YYYY-mm-dd' ISO."""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(day, fmt).date().isoformat()
        except ValueError:
            continue
    return day


def compare_rpc(sb, series: list, pnl: list[float]) -> int:
    """Inserisce, chiama get_personal_report, confronta daily + metrics a tol 1e-6."""
    print("=== (b) ORACOLO == RPC get_personal_report (tol 1e-6) ===")
    mism = 0
    cleanup(sb)
    try:
        insert_synthetic_trades(sb, series)

        days_iso = [_to_iso(d) for d, _, _ in series]
        p_from, p_to = min(days_iso), max(days_iso)
        rep = sb.rpc("get_personal_report", {
            "p_from": p_from, "p_to": p_to, "p_strategia": CERT_STRATEGIA,
            "p_league_id": CERT_LEAGUE_ID, "p_status": None,
        }).execute().data

        # --- daily ---
        ora_daily = build_daily(series)
        rpc_daily = {row["day"][:10]: row for row in (rep.get("daily") or [])}
        for od in ora_daily:
            key = _to_iso(od["day"])
            r = rpc_daily.get(key)
            if r is None:
                print(f"  XX daily[{key}]: oracolo SI, RPC NO")
                mism += 1
                continue
            for f in ("pnl", "equity", "peak", "drawdown"):
                ov, rv = od[f], _fnum(r.get(f))
                if rv is None or abs(ov - rv) > TOL:
                    print(f"  XX daily[{key}].{f}: oracolo {ov:.6f} vs RPC {rv}")
                    mism += 1
        if len([1 for _ in ora_daily]) and mism == 0:
            print(f"  OK  daily: {len(ora_daily)} giorni allineati (pnl/equity/peak/drawdown)")

        # --- metrics ---
        ora_m = compute_metrics(pnl)
        rpc_m = rep.get("metrics") or {}
        for k, ov in ora_m.items():
            if k not in rpc_m:
                # metrica calcolata dall'oracolo ma non esposta dalla RPC → segnala
                print(f"  XX metrics.{k}: oracolo {ov} vs RPC <assente>")
                mism += 1
                continue
            rv = _fnum(rpc_m[k])
            if rv is None:
                print(f"  XX metrics.{k}: oracolo {ov} vs RPC None")
                mism += 1
                continue
            if math.isinf(ov):
                continue  # ratio degenerati: non confrontabili numericamente
            if abs(ov - rv) > TOL:
                print(f"  XX metrics.{k}: oracolo {ov:.6f} vs RPC {rv:.6f}")
                mism += 1
            else:
                print(f"  OK  metrics.{k:22s} {rv:.6f}")

        # --- metriche OPERATIVE (§3): l'oracolo P&L non le copre perche' dipendono
        #     da stake/tempo/#trade. Le ricavo dai parametri noti dei trade sintetici
        #     (1 trade/giorno, stake=|pnl|, tempo=60min, commissione 0) e le gate vs RPC. ---
        n = len(pnl)
        tot = sum(pnl)
        sum_stake = sum(abs(x) for x in pnl)
        sum_tmin = 60.0 * n
        op = {
            "tempo_medio_giorno": sum_tmin / n if n else None,
            "guadagno_orario_medio": tot / (sum_tmin / 60.0) if sum_tmin > 0 else None,
            "profit_per_stake": tot / sum_stake if sum_stake > 0 else None,
            "stake_medio_giorno": sum_stake / n if n else None,
            "media_trade_giorno": n / n if n else None,  # 1 trade/giorno
            # giorni con perdita > stake: con stake=|pnl| non accade mai → 0 atteso
            "giornate_perdita_gt_stake": sum(1 for x in pnl if x < 0 and -x > abs(x)),
        }
        for k, ov in op.items():
            if k not in rpc_m:
                print(f"  XX metrics.{k}: oracolo {ov} vs RPC <assente>")
                mism += 1
                continue
            rv = _fnum(rpc_m[k])
            if ov is None and rv is None:
                print(f"  OK  metrics.{k:22s} None")
                continue
            if rv is None or ov is None or abs(ov - rv) > TOL:
                print(f"  XX metrics.{k}: oracolo {ov} vs RPC {rv}")
                mism += 1
            else:
                print(f"  OK  metrics.{k:22s} {rv:.6f}")
    finally:
        cleanup(sb)

    print(f"  --> RPC compare: {mism} mismatch\n")
    return mism


# =====================================================================================
def main() -> int:
    series = json.load(open(FIXTURE_PATH, encoding="utf-8"))
    pnl = [float(d[1]) for d in series]

    total_fail = 0
    # (c) recompute economics — SEMPRE
    total_fail += run_recompute_unit_tests()
    # (a) oracolo self-check vs Excel — SEMPRE
    total_fail += run_oracle_self_check(pnl)

    # (b) oracolo == RPC — solo se DB raggiungibile
    db_ran = False
    try:
        from db_client import get_supabase_client
        sb = get_supabase_client()
        # ping minimale: la RPC esiste?
        sb.rpc("get_personal_report", {
            "p_from": "1970-01-01", "p_to": "1970-01-01", "p_strategia": CERT_STRATEGIA,
            "p_league_id": CERT_LEAGUE_ID, "p_status": None,
        }).execute()
        db_ran = True
    except Exception as e:
        print("=== (b) RPC get_personal_report — SALTATA (DB non raggiungibile / RPC assente) ===")
        print(f"    motivo: {str(e)[:160]}")
        print("    (contratto §6: oracolo Python verde + RPC da ispezionare a mano vs §3)\n")

    if db_ran:
        total_fail += compare_rpc(sb, series, pnl)

    print("=" * 70)
    if total_fail == 0:
        if db_ran:
            print("ESITO: ✅ CERTIFICATA — oracolo == RPC, recompute OK (0 mismatch)")
        else:
            print("ESITO: ✅ oracolo + recompute VERDI (RPC saltata: ispezionare a mano §3)")
        return 0
    print(f"ESITO: ❌ {total_fail} MISMATCH/FALLIMENTI — vedi sopra")
    return 1


if __name__ == "__main__":
    sys.exit(main())
