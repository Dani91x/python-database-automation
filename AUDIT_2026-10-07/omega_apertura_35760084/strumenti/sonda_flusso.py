"""Sonda: avvolge omega_service._flusso_feed e registra i passaggi vivo/fermo col
minuto della riga del feed, poi lancia il punto d'ingresso unico del banco in
processo (--worker 1). Solo lettura: nessun file del repo toccato.
uso (dalla radice dell'albero da provare): python3 sonda_flusso.py <evento> <scenari>"""
import sys, os, collections
sys.path.insert(0, os.getcwd())
from Betfair.omega import omega_service as S
from Betfair.stream import flusso_prezzi as F

orig = S._flusso_feed
passaggi = []
conta = collections.Counter()
ultimo = {}


def sonda(event_id):
    es = orig(event_id)
    try:
        cache = S._scan_feed.shared_cache()
        row = S._feed_riga_cached(cache, str(event_id))
        p = row.get("payload") if isinstance(row, dict) else {}
        p = p or {}
        minuto = p.get("minute")
        blk = p.get(F.CHIAVE)
    except Exception as ex:  # noqa: BLE001
        minuto, blk = None, repr(ex)
    chiave = (bool(es.vivo), es.motivo)
    conta[chiave] += 1
    visti = ultimo.setdefault("_minuti", set())
    if ultimo.get(event_id) != chiave or (minuto in (44, 45, 46, 47, 48, 50, 55, 60, 70, 80) and minuto not in visti):
        visti.add(minuto)
        ultimo[event_id] = chiave
        def _m(k):
            b = p.get(k)
            return (b.get("market_id"), b.get("status"), b.get("inplay")) if isinstance(b, dict) else None
        passaggi.append((event_id, minuto, chiave, getattr(es, "testo", None), blk,
                         "MO=", p.get("mo_market_id"), "CS=", _m("cs"), "HT=", _m("ht"),
                         "inplay=", p.get("inplay"), "status=", p.get("status"), "ht_completo=", {k: v for k, v in (p.get("ht") or {}).items() if k not in ("runners", "selections")}))
    return es


S._flusso_feed = sonda
from Betfair.stream.backtest import certifica as C  # noqa: E402

rc = C.main(["omega", sys.argv[1], "--data-dir", "/home/user/python-database-automation/_live_raw",
             "--scenari", sys.argv[2], "--worker", "1"])
print("\n===== SONDA _flusso_feed =====")
print("conteggi:", dict(conta))
for p in passaggi:
    print("passaggio:", p)
