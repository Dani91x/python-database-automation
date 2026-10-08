"""Traccia ordine per ordine (solo lettura) di uno scenario dello scalper calcio.

Uso: python3 traccia_c15.py <scenario> <market_id> <sel,sel> <out.txt>
Lancia il replay vero (certifica_scenario) e cattura il banco alla chiusura del
referto: elenca gli ordini del bot sul mercato (blotter di flumine) e le righe di
attivita' dello scalper che citano le selezioni.
"""
import sys
import json
from datetime import datetime, timezone

sys.path.insert(0, ".")
from Betfair.stream.scalper.tools import replay_registrazioni as RR  # noqa: E402

scenario, mid, sels, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
EV = sys.argv[5] if len(sys.argv) > 5 else "35797769"
sels = {int(x) for x in sels.split(",")}
catturato = {}
orig = RR._chiudi_referto


def _cattura(ref, banco, *a, **k):
    catturato["banco"] = banco
    return orig(ref, banco, *a, **k)


RR._chiudi_referto = _cattura


def _t(x):
    if x is None:
        return "-"
    if isinstance(x, (int, float)):
        return datetime.fromtimestamp(x / 1000.0, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3]
    try:
        return x.strftime("%H:%M:%S.%f")[:-3]
    except Exception:
        return str(x)


from Betfair.stream.backtest import certifica as CF  # noqa: E402
from Betfair.stream.backtest import minimi_banco as MB  # noqa: E402

MB.REGISTRO.azzera()
with CF._freni_da_banco():
    ref = RR.certifica_scenario(EV, data_dir="_live_raw", scenario=scenario, ogni_ms=0)
banco = catturato["banco"]
righe = []
m = banco.quadro.markets.markets.get(mid)
ordini = list(m.blotter) if m is not None else []
ordini.sort(key=lambda o: (o.date_time_created or datetime.min))
righe.append("ORDINI del blotter su %s (sel %s): %d" % (mid, sorted(sels), len(ordini)))
for o in ordini:
    if int(o.selection_id) not in sels:
        continue
    sim = getattr(o, "simulated", None)
    matched = list(getattr(sim, "matched", []) or [])
    ot = o.order_type
    righe.append(
        "creato %s piazz %s id=%s bet=%s sel=%s %s %.2f@%s pers=%s stato=%s abb=%.2f media=%s "
        "rest=%.2f lapsed=%.2f annull=%.2f fill=%s note=%s compl=%s" % (
            _t(o.date_time_created), _t(getattr(o, "date_time_execution_complete", None)),
            o.id, o.bet_id, o.selection_id, o.side, ot.size, ot.price,
            getattr(ot, "persistence_type", None), getattr(o.status, "value", o.status),
            o.size_matched or 0.0, o.average_price_matched, o.size_remaining or 0.0,
            o.size_lapsed or 0.0, o.size_cancelled or 0.0,
            [(_t(x[0]), x[1], x[2]) for x in matched],
            json.dumps(getattr(o, "notes", None) or {}, default=str)[:200],
            _t(getattr(o, "date_time_execution_complete", None))))
righe.append("")
righe.append("ATTIVITA' dello scalper che cita %s:" % sorted(sels))
for r in banco.db.attivita():
    p = r.get("payload") or {}
    testo = json.dumps(p, default=str)
    if any(str(s) in testo for s in sels) or r.get("kind") in ("flatten_done", "ko", "session"):
        righe.append("%s %s %s" % (_t(r.get("_ms")), r.get("kind"), testo[:600]))
righe.append("")
righe.append("REFERTO: violazioni %d" % len(ref.violazioni))
for v in ref.violazioni:
    righe.append(str(v.__dict__)[:800])
for n in ref.note:
    righe.append("nota: " + str(n)[:1500])
with open(out, "w") as f:
    f.write("\n".join(righe) + "\n")
print("scritto", out, len(righe))
