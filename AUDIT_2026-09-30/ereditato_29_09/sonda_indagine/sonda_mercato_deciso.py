"""SONDA di sola lettura (fuori dal codice di produzione, mai da committare):
replay base di Mike 35760084 col punto d'ingresso di produzione, registra ogni
decisione (snap + decisione + telemetria) e l'esito del flusso prezzi."""
import json
import sys
import time

OUT = sys.argv[1]
SCEN = sys.argv[2] if len(sys.argv) > 2 else "base"
EXTRA = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
DATA = "C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/_live_raw"

from Betfair.mike import engine as E
from Betfair.mike import feed as F
from Betfair.mike import service as S
from Betfair.mike.tools import replay_registrazioni as RR
from Betfair.stream.backtest import trasporto as TRA

if EXTRA:
    RR.SCENARI[SCEN] = {**RR.SCENARI.get(SCEN, {}), **EXTRA}

righe = []
flussi = {"ultimo": None}
dbs = []

vero_flusso = F.flusso_esito


def flusso_sorv(row, stato=None, now=None):
    es = vero_flusso(row, stato, now)
    flussi["ultimo"] = {"vivo": es.vivo, "motivo": es.motivo, "mercati": list(es.mercati)}
    return es


F.flusso_esito = flusso_sorv
vero_decide = E.decide


def _bk(b):
    if b is None:
        return None
    return [b.best_back, b.best_lay, b.status]


def decide_sorv(ctx, snap, params):
    d = vero_decide(ctx, snap, params)
    try:
        tele = d.telemetry or {}
        cash = tele.get("cashout") or {}
        righe.append({
            "t": snap.now, "st": ctx.state, "d_st": d.state, "reason": d.reason,
            "min": snap.minute, "gol": snap.goals, "ht": snap.ht_active,
            "ff": snap.feed_fresh, "of": snap.order_fresh, "ms": snap.market_status,
            "fonte": getattr(snap, "fonte_prezzi", None),
            "u35": _bk(snap.books.get((E.MARKET_OU35, E.SEL_UNDER))),
            "o45": _bk(snap.books.get((E.MARKET_OU45, E.SEL_OVER))),
            "u45": _bk(snap.books.get((E.MARKET_OU45, E.SEL_UNDER))),
            "cash": ({k: cash.get(k) for k in ("net", "gross", "base", "complete", "per",
                                              "per_gross", "decided")} if cash else None),
            "loss": tele.get("loss_exit"),
            "prop": ((tele.get("uscita_proposta") or {}).get("bloccabile")
                     if tele.get("uscita_proposta") else None),
            "decad": tele.get("uscita_proposta_decaduta"),
            "flusso": flussi["ultimo"],
            "riga_ou": flussi.get("riga_ou"), "riga_flusso": flussi.get("riga_flusso"),
            "p_tot_model": snap.p_total_model, "p_tot_emp": snap.p_total_emp,
            "p_tot_mkt": snap.p_total_market, "p4m": snap.p4_market,
            "acts": [[a.kind, a.role, a.market, a.selection, a.side, a.price, a.size]
                     for a in d.actions],
            "legs": [[l.role, l.market, l.selection, l.side, l.matched,
                      l.fill_price if l.matched else None, l.archived]
                     for l in ctx.legs if l.matched],
        })
    except Exception as ex:  # noqa
        righe.append({"errore_sonda": repr(ex)})
    return d


E.decide = decide_sorv
vero_run = S._run_event


APPROVA_DAL = sys.argv[4] if len(sys.argv) > 4 else ""
firme = []


def _sec(hms):
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s


def run_sorv(*a, **kw):
    db = kw.get("db")
    row = kw.get("row")
    blk = {}
    for b in (((row or {}).get("payload") or {}).get("ou") or []):
        if isinstance(b, dict) and b.get("line") in (3.5, 4.5):
            sel = b.get("selections") or []
            blk[str(b.get("line"))] = [b.get("status"), b.get("inplay"),
                                       [[s.get("back"), s.get("lay")] for s in sel if isinstance(s, dict)]]
    flussi["riga_ou"] = blk
    flussi["riga_flusso"] = ((row or {}).get("payload") or {}).get("flusso")
    if db is not None and not dbs:
        dbs.append(db)
    # FIRMA DELL'UTENTE simulata con la richiesta VERA di produzione
    # (``_request_approva_uscita``): la prima proposta viva dopo APPROVA_DAL (UTC)
    if APPROVA_DAL and db is not None and not firme:
        now = kw["now"]
        if now.hour * 3600 + now.minute * 60 + now.second >= _sec(APPROVA_DAL):
            ev = kw["ev"]
            ctx = S._ctx_from_row(ev, db)
            prop = ctx.uscita_proposta if isinstance(ctx.uscita_proposta, dict) else None
            if prop is not None:
                eid = str(ev["event_id"])
                res = S._request_approva_uscita(db, ev, db.events, eid,
                                                {"chiave": prop.get("chiave")}, now,
                                                request_id=777)
                firme.append({"at": now.isoformat(), "prop": {k: v for k, v in prop.items()
                                                             if k != "sostanza"},
                              "esito": res})
                kw["ev"] = db.events[eid]
    return vero_run(*a, **kw)


S._run_event = run_sorv

t0 = time.time()
with TRA.contesto("mike", "canale"):
    ref = RR.certifica_scenario("35760084", data_dir=DATA, scenario=SCEN)
print("durata", round(time.time() - t0, 1), "decisioni", ref.decisioni, file=sys.stderr)
att = []
trades = []
if dbs:
    for k, p, e in dbs[0].attivita:
        att.append({"kind": k, "payload": p, "ev": e})
    trades = list(dbs[0].trades)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"righe": righe, "attivita": att, "trades": trades,
               "note": list(ref.note), "motivi": ref.motivi, "firme": firme,
               "violazioni": [str(v) for v in ref.violazioni]}, f, default=str)
print("ok", len(righe), len(att), file=sys.stderr)
