"""Traccia ordine per ordine (solo lettura) di uno scenario dello scalper calcio.

Derivato da `AUDIT_2026-10-08/cantiere_15/strumenti/traccia_c15.py`. Uso, dalla
radice del repo:
  python3 AUDIT_2026-10-08/cantiere_9/strumenti/traccia_c9.py <scenario> <market_id> \
      <sel,sel> <out.txt> [evento] [dalle HH:MM:SS] [alle HH:MM:SS]
Lancia il replay vero (`certifica_scenario` sotto i freni del banco) e cattura il
banco alla chiusura del referto: ordini del bot sul mercato (blotter di flumine),
TUTTE le attivita' dello scalper nella finestra oraria, il riepilogo del cantiere 9.
"""
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")
from Betfair.stream.scalper.tools import replay_registrazioni as RR  # noqa: E402

scenario, mid, sels, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
EV = sys.argv[5] if len(sys.argv) > 5 else "35797769"
DALLE = sys.argv[6] if len(sys.argv) > 6 else "00:00:00"
ALLE = sys.argv[7] if len(sys.argv) > 7 else "23:59:59"
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
    ref = RR.certifica_scenario(EV, data_dir=r"C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/_live_raw", scenario=scenario, ogni_ms=0)
banco = catturato["banco"]
righe = []
m = banco.quadro.markets.markets.get(mid)
ordini = list(m.blotter) if m is not None else []
ordini.sort(key=lambda o: (o.date_time_created or datetime.min))
righe.append("ORDINI del blotter su %s (sel %s): %d" % (mid, sorted(sels), len(ordini)))
for o in ordini:
    if int(o.selection_id) not in sels:
        continue
    t = _t(o.date_time_created)
    if not (DALLE <= t[:8] <= ALLE):
        continue
    sim = getattr(o, "simulated", None)
    matched = list(getattr(sim, "matched", []) or [])
    ot = o.order_type
    pr = getattr(getattr(o, "responses", None), "place_response", None)
    righe.append(
        "creato %s id=%s bet=%s sel=%s %s %.2f@%s stato=%s abb=%.2f media=%s rest=%.2f "
        "lapsed=%.2f annull=%.2f void=%.2f fill=%s risposta=%s/%s trade=%d/%d" % (
            t, str(o.id)[-6:], o.bet_id, o.selection_id, o.side, ot.size, ot.price,
            getattr(o.status, "value", o.status), o.size_matched or 0.0,
            o.average_price_matched, o.size_remaining or 0.0, o.size_lapsed or 0.0,
            o.size_cancelled or 0.0, float(getattr(sim, "size_voided", 0.0) or 0.0),
            [(_t(x[0]), x[1], x[2]) for x in matched],
            getattr(pr, "status", None), getattr(pr, "error_code", None),
            o.trade.orders.index(o) + 1 if o in o.trade.orders else 0, len(o.trade.orders)))
righe.append("")
righe.append("ATTIVITA' dello scalper fra %s e %s:" % (DALLE, ALLE))
for k, p, ms in banco.attivita:
    t = _t(ms)
    if DALLE <= t[:8] <= ALLE:
        righe.append("%s %s %s" % (t, k, json.dumps(p, default=str)[:500]))
righe.append("")
righe.append("REFERTO: violazioni %d" % len(ref.violazioni))
for v in ref.violazioni:
    righe.append(str(v.__dict__)[:800])
for n in ref.note:
    if "INGRESSO ABBINATO" in n or "FINTO BETFAIR" in n or "impronta" in n:
        righe.append(n)
open(out, "w", encoding="utf-8").write("\n".join(righe) + "\n")
print("scritto", out, len(righe), "righe")
