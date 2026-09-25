"""SONDA DI LETTURA dei servizi (piano E2E §1.7) - SOLA LETTURA.

Chiama le STESSE funzioni con cui i servizi rileggono il DB a ogni giro, con il
client vero (db_client -> config -> .env del checkout principale), SENZA avviare
nessun servizio: nessun run_once, nessun set_*, nessun log, nessun thread.
Uso:  python sonda.py <nome_file_uscita>   (scrive e2e_fase1/<nome>.json)
"""
import json
import os
import sys
import threading

WT = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-ae6b4a3f84a6ad933"
OUT = os.path.join(WT, "AUDIT_2026-09-25", "e2e_fase1")
sys.path.insert(0, WT)
os.chdir(WT)

thread_prima = threading.active_count()

from Betfair.omega import omega_db, omega_config, omega_proposte  # noqa: E402
from Betfair.mike import db as mike_db, config as mike_config  # noqa: E402
from Betfair.safe_strategy import bot_db as safe_db  # noqa: E402
from Betfair.safe_strategy import bot_service as safe_bs  # noqa: E402
from Betfair.stream.tennis_live import tennis_db, tennis_bot_service  # noqa: E402
from Betfair.stream.scalper import scalper_service  # noqa: E402
from Betfair.stream.trading import controls  # noqa: E402
from Betfair.stream import modo_ordini  # noqa: E402

thread_dopo_import = threading.active_count()


def s_omega():
    c = omega_db.read_control() or {}
    p = omega_config.resolve_params(c.get("params"))
    return {"status": c.get("status"), "mode": c.get("mode"), "daily_goal": c.get("daily_goal"),
            "modo_uscite": omega_proposte.modo_uscite(c.get("params")),
            "min_stake_resolved": p.get("min_stake"), "min_stake_raw": (c.get("params") or {}).get("min_stake")}


def s_mike():
    c = mike_db.read_control() or {}
    p = mike_config.merge_params(c.get("params"))
    return {"status": c.get("status"), "mode": c.get("mode"),
            "uscite_automatiche": p.get("uscite_automatiche"), "stake": p.get("stake")}


def s_safe():
    c = safe_db.read_control() or {}
    mode = str(c.get("mode") or "paper")
    p = safe_bs.resolve_params(c.get("params"))
    return {"status": c.get("status"), "mode": mode, "variants": p.get("variants"),
            "modalita_per_strategia": {s: safe_bs.modalita_di_strategia(s, mode, p) for s in safe_bs._STRATEGIES},
            "uscite_per_strategia": {s: safe_bs.uscite_automatiche_di(p, s) for s in safe_bs.STRATEGIE_CON_USCITE},
            "stake_per_strategia": (p.get("stake") or {}).get("per_strategia"),
            "tennis_exit_approval": p.get("tennis_exit_approval")}


def s_tennis():
    righe = tennis_db.list_tennis_bot_services()
    d = tennis_bot_service.stato_desiderato(righe)
    return {k: {kk: v[kk] for kk in ("acceso", "mode", "stake", "uscite_automatiche")} for k, v in (d or {}).items()}


def s_scalper():
    r = scalper_service.Db().servizio() or {}
    return {"status": r.get("status"), "mode": r.get("mode"), "stake": r.get("stake"),
            "strategia": r.get("strategia"),
            "uscite_automatiche": (r.get("params") or {}).get("uscite_automatiche")}


def s_ordini():
    s = controls.get_live_settings(force=True)
    return {"kill_switch": s.get("kill_switch"), "order_mode": s.get("order_mode"),
            "motivo_kill_switch": controls.motivo_kill_switch(),
            "descrivi": modo_ordini.descrivi(os.getenv("LIVE_ORDER_MODE"), s.get("order_mode"))}


if __name__ == "__main__":
    nome = sys.argv[1]
    quali = sys.argv[2].split(",") if len(sys.argv) > 2 else ["omega", "mike", "safe", "tennis", "scalper", "ordini"]
    fn = {"omega": s_omega, "mike": s_mike, "safe": s_safe, "tennis": s_tennis,
          "scalper": s_scalper, "ordini": s_ordini}
    res = {"thread_prima_import": thread_prima, "thread_dopo_import": thread_dopo_import}
    for q in quali:
        res[q] = fn[q]()
    res["thread_fine"] = threading.active_count()
    with open(os.path.join(OUT, nome + ".json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=str)
    print(json.dumps(res, ensure_ascii=False, default=str))
