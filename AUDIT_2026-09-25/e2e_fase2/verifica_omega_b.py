"""verifica_omega_b.py - E2E FASE 2 (26/09), semantica B/C per le decisioni di Omega.

SOLA LETTURA: legge `omega_trades` e `omega_control` con le funzioni di lettura di produzione
(`omega_db.get_trade`, `omega_db.read_control`) e le tabelle storiche con le RPC di lettura
(`get_omega_minute_ft`/`get_omega_ht_ft` via `omega_service._v3_p_empirica`). Nessuna scrittura,
nessun thread, nessun servizio avviato.

RICALCOLO con le funzioni di PRODUZIONE (mai reimplementate):
  * P modello GREZZA  = omega_v3.probabilita_selezioni(...) coi lambda del trade e i parametri del
    banco (omega_proposte.parametri_modello), moltiplicatori rossi di omega_engine;
  * P storica         = omega_service._v3_p_empirica(omega_db, ...)
  * p implicita       = omega_v3.p_implicita(prezzo, commissione)
  * P nostra          = max(P fusa scritta, P storica)   [come omega_v3._seleziona]
  * margine, EV, liability = omega_v3 (p_imp/p_nostra, ev_gamba, liability)
  * CANCELLO (C)      = cfg di omega_config.parametri_v3(params): finestra, fascia p_imp, tetto P,
    k, distanza gol, cap gamba.
  * P fusa: il book intero dell'istante NON e' nel trade; se `p_mercato` e' ricavabile dalla
    registrazione dello scanner (canali/scanner/*.gz, blocco `cs`) si ricalcola con
    omega_v3.fondi_col_mercato, altrimenti si ricava la p_mercato implicita dalla P fusa scritta.
Uso: python verifica_omega_b.py <trade_id> [<trade_id> ...]  (stampa JSON)
"""
import glob, gzip, json, math, os, sys
from datetime import datetime

sys.path.insert(0, os.getcwd())
from Betfair.omega import omega_db, omega_config, omega_v3 as V3, omega_proposte, omega_engine as E  # noqa: E402
from Betfair.omega import omega_model as M  # noqa: E402
from Betfair.omega import omega_service as S  # noqa: E402

REG = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\AUDIT_2026-09-25\e2e_fase2\canali\scanner"


def riga_scanner(event_id, ts_ms):
    """la riga del feed registrata piu' vicina (entro 6 s) all'istante, o None"""
    best = None
    for f in sorted(glob.glob(os.path.join(REG, "*.jsonl.gz"))):
        try:
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                for line in fh:
                    if f'"event_id": "{event_id}"' not in line and f'"event_id": {event_id}' not in line:
                        continue
                    r = json.loads(line)
                    dt = abs(r["ts_ms"] - ts_ms)
                    if best is None or dt < best[0]:
                        best = (dt, r)
        except (OSError, EOFError):
            continue
    return best if best and best[0] <= 6000 else None


def verifica(tid):
    t = omega_db.get_trade(int(tid))
    ctl = omega_db.read_control() or {}
    params = omega_config.resolve_params(ctl.get("params") or {})
    cfg = omega_config.parametri_v3(params)
    a = ((t.get("meta") or {}).get("model") or {})
    out = {"trade_id": tid, "event_id": t["event_id"], "runner": t["runner_name"], "price": float(t["price"]),
           "size": float(t["size"]), "minuto": t["minute_at_entry"], "punteggio": t["score_at_entry"],
           "placed_at": t["placed_at"], "mode": t["mode"], "audit_scritto": a}
    h, aw = (int(x) for x in str(t["score_at_entry"]).split("-"))
    lam = tuple(a.get("lambda_pre") or ())
    par = omega_proposte.parametri_modello()
    if par.modello != cfg["modello"]:
        par = par.con(modello=cfg["modello"])
    mr = a.get("mult_rossi")
    mult = tuple(mr) if mr else V3.MULT_NEUTRO
    nomi = [t["runner_name"]] + [f"{i} - {j}" for i in range(4) for j in range(4)] + [
        "Any Other Home Win", "Any Other Away Win", "Any Other Draw"]
    nomi = list(dict.fromkeys(nomi))
    prob = V3.probabilita_selezioni(periodo=V3.PERIODO_FT, minuto=float(t["minute_at_entry"]), punteggio=(h, aw),
                                    nomi=nomi, p=par, lambdas=(float(lam[0]), float(lam[1])), mult_rossi=mult)
    p_grezza = prob.get(t["runner_name"])
    state = M.LiveState(minute=int(t["minute_at_entry"]), score_home=h, score_away=aw)
    fn = S._v3_p_empirica(omega_db, league_id=a.get("league_id"), state=state, half=False,
                          payload={}, params=params, n_min=int(cfg["empirical_min_n"]))
    emp = fn(t["runner_name"]) if fn else None
    comm = float(cfg["commissione"])
    p_imp = V3.p_implicita(float(t["price"]), comm)
    p_fusa_scritta = float(a.get("p_fusa")) if a.get("p_fusa") is not None else None
    # P fusa dal book registrato (se c'e')
    p_fusa_ric, p_merc = None, None
    ts_ms = int(datetime.fromisoformat(str(t["placed_at"]).replace("Z", "+00:00")).timestamp() * 1000)
    reg = riga_scanner(t["event_id"], ts_ms)
    if reg is not None:
        pay = (reg[1]["d"] or {}).get("payload") or {}
        cs = pay.get("cs") or {}
        from types import SimpleNamespace as NS
        runs = [NS(name=s.get("name"), back_price=s.get("back"), lay_price=s.get("lay"))
                for s in (cs.get("selections") or []) if s.get("runner_status", "ACTIVE") == "ACTIVE"]
        fpm = V3.p_mercato_devigata(runs)
        p_merc_reg = fpm(t["runner_name"]) if fpm else None
        sel = [s for s in (cs.get("selections") or []) if s.get("name") == t["runner_name"]]
        out["scanner_registrato"] = {"dt_ms": reg[0], "minuto": pay.get("minute"),
                                     "punteggio": f"{pay.get('score_home')}-{pay.get('score_away')}",
                                     "runner_nel_book": sel[:1], "p_mercato_devigata": p_merc_reg}
        if p_merc_reg is not None and p_grezza is not None:
            p_fusa_ric = V3.fondi_col_mercato(p_grezza, p_merc_reg, par)
            out["p_fusa_ricalcolata_dal_book_registrato"] = p_fusa_ric
    p_nostra = max(p_fusa_scritta or 0.0, emp[0] if emp else 0.0) if p_fusa_scritta is not None else None
    # p_mercato implicita dalla P fusa scritta (inversione del logit con il peso della fascia)
    if p_fusa_scritta is not None and p_grezza and 0 < p_grezza < 1 and abs(p_fusa_scritta - p_grezza) > 1e-9:
        # w dipende da p_mercato: si cerca il p_mercato che riproduce la P fusa (bisezione in logit)
        lo, hi = 1e-6, 0.5
        for _ in range(200):
            mid = math.sqrt(lo * hi)
            v = V3.fondi_col_mercato(p_grezza, mid, par)
            if (v > p_fusa_scritta):
                hi = mid
            else:
                lo = mid
        p_merc = math.sqrt(lo * hi)
    k = float(cfg["k_minimo"])
    marg = (p_imp / p_nostra) if (p_imp and p_nostra) else None
    ev = V3.ev_gamba(p_nostra, float(t["price"]), float(t["size"]), comm) if p_nostra is not None else None
    liab = V3.liability(float(t["size"]), float(t["price"]))
    lo_m, hi_m = int(cfg["ft_entry_min"]), int(cfg["ft_entry_max"])
    sc = V3.parse_scoreline(t["runner_name"])
    dist = None if sc is None else (sc[0] - h) + (sc[1] - aw)
    cancello = {
        "finestra": [lo_m <= int(t["minute_at_entry"]) <= hi_m, [lo_m, hi_m]],
        "p_imp_in_fascia": [cfg["p_min"] <= p_imp <= cfg["p_max"], [cfg["p_min"], cfg["p_max"]], p_imp],
        "p_nostra_sotto_tetto": [p_nostra is not None and p_nostra <= cfg["p_max"], cfg["p_max"], p_nostra],
        "margine_ge_k": [marg is not None and marg >= k - 1e-9, k, marg],
        "distanza_gol": [dist is None or dist >= int(cfg["distanza_minima_gol"]), int(cfg["distanza_minima_gol"]), dist],
        "liability_le_cap_gamba": [float(cfg["max_liability_per_leg"]) <= 0 or liab <= float(cfg["max_liability_per_leg"]) + 1e-9,
                                   float(cfg["max_liability_per_leg"]), liab],
        "stake": [abs(float(t["size"]) - float(cfg["stake"])) < 1e-9, float(cfg["stake"]), float(t["size"])],
    }

    def eq(x, y, tol):
        return x is not None and y is not None and abs(float(x) - float(y)) <= tol

    confronto = {
        "p_implicita": [p_imp, a.get("p_implied"), eq(p_imp, a.get("p_implied"), 1e-7)],
        "p_empirica": [None if emp is None else emp[0], a.get("p_empirica"),
                       (emp is None and a.get("p_empirica") is None) or (emp is not None and eq(emp[0], a.get("p_empirica"), 1e-7))],
        "n_empirico": [None if emp is None else emp[1], a.get("n_empirico"),
                       (emp is None and a.get("n_empirico") is None) or (emp is not None and emp[1] == a.get("n_empirico"))],
        "p_nostra": [p_nostra, a.get("p_selected"), eq(p_nostra, a.get("p_selected"), 1e-7)],
        "margine": [marg, a.get("margine"), eq(marg, a.get("margine"), 1e-4)],
        "ev": [ev, a.get("ev"), eq(ev, a.get("ev"), 1e-4)],
        "liability": [liab, a.get("liability"), eq(liab, a.get("liability"), 0.005)],
        "p_modello_grezza_vs_scritta": [p_grezza, a.get("p_modello"), eq(p_grezza, a.get("p_modello"), 1e-7)],
        "p_fusa_dal_book_registrato": [p_fusa_ric, p_fusa_scritta,
                                       None if p_fusa_ric is None else eq(p_fusa_ric, p_fusa_scritta, 2e-4)],
    }
    out.update({"cfg_v3": {k2: cfg[k2] for k2 in ("modello", "k_minimo", "p_min", "p_max", "ft_entry_min", "ft_entry_max",
                                                    "max_liability_per_leg", "distanza_minima_gol", "stake", "fusione",
                                                    "rossi", "empirical_min_n")},
                "p_modello_grezza": p_grezza, "p_mercato_implicita_dalla_fusa": p_merc,
                "peso_fusione_modello": (V3.peso_fusione(p_merc, par) if p_merc else None),
                "cancello": cancello, "tutto_il_cancello_vero": all(v[0] for v in cancello.values()),
                "confronto_ricalcolo_vs_scritto": confronto,
                "esito_B": "OK" if all(v[2] for k3, v in confronto.items() if k3 not in ("p_modello_grezza_vs_scritta", "p_fusa_dal_book_registrato")) else "KO"})
    return out


if __name__ == "__main__":
    res = [verifica(x) for x in sys.argv[1:]]
    print(json.dumps(res, indent=1, default=str, ensure_ascii=False))
