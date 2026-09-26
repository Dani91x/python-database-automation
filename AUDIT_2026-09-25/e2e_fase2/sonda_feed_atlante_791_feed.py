"""sonda_feed_atlante_791_feed.py - 7.9.1.A (e2e fase 2, 26/09), SOLA LETTURA.
Confronta, nello stesso istante, cio' che il feed unico PUBBLICA sul canale locale 47336
(lettore scan_calcio/scan_tennis, nessun token) con una lettura INDIPENDENTE del DB
(safe_strategy_scan via PostgREST GET ogni ~8 s) per le stesse partite, e controlla che i prezzi
siano un libro Betfair plausibile (reimplementato qui, nessun import di produzione):
  * stessa riga: per ogni coppia (event_id, updated_at) vista sia sul canale sia sul DB, odds /
    minute / score / odds_ts_ms devono essere IDENTICI (il canale dichiara "riga identica a quella
    del DB", Betfair/safe_strategy/service.py:77-78);
  * eta': ricezione sul canale - updated_at; updated_at - odds_pt_ms (tempo di pubblicazione
    Betfair del prezzo -> scrittura); odds_ts_ms <= updated_at;
  * libro: prezzi sulla scala dei tick Betfair, back < lay per ogni selezione, size > 0,
    somma 1/back >= 0.99 e somma 1/lay <= 1.01 (nessun arbitraggio impossibile sul miglior livello).
NON puo' confrontare col libro Betfair VERO (servono credenziali/sessione: fuori perimetro).
Uso: python sonda_feed_atlante_791_feed.py <minuti>  -> sonda_791_feed_esito.json
"""
import asyncio
import datetime as dt
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonda_feed_atlante_db import get  # noqa: E402

QUI = Path(__file__).resolve().parent
MINUTI = float(sys.argv[1]) if len(sys.argv) > 1 else 20


def ts(s):
    d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).timestamp()


def k_upd(s):
    """updated_at normalizzato: PostgREST toglie gli zeri finali dei microsecondi
    ("45.24813") mentre il canale li scrive ("45.248130"): si confronta l'istante, non il testo."""
    return round(ts(s), 6) if s else None


# scala dei tick Betfair (tabella ufficiale degli incrementi)
_FASCE = [(1.01, 2, 0.01), (2, 3, 0.02), (3, 4, 0.05), (4, 6, 0.1), (6, 10, 0.2), (10, 20, 0.5),
          (20, 30, 1), (30, 50, 2), (50, 100, 5), (100, 1000, 10)]


def sul_tick(p):
    if p is None:
        return True
    for lo, hi, inc in _FASCE:
        if lo - 1e-9 <= p <= hi + 1e-9:
            k = round((p - lo) / inc, 6)
            if abs(k - round(k)) < 1e-6:
                return True
    return False


canale = []          # (ricevuto, sport, event_id, updated_at, payload)


def ascolta(fine):
    import websockets

    async def go():
        while time.time() < fine:
            try:
                async with websockets.connect("ws://127.0.0.1:47336/lettore/scan_calcio,scan_tennis",
                                              max_size=None, open_timeout=5) as ws:
                    while time.time() < fine:
                        try:
                            m = await asyncio.wait_for(ws.recv(), 5)
                        except asyncio.TimeoutError:
                            continue
                        r = time.time()
                        j = json.loads(m)
                        if j.get("t") in ("scan_calcio", "scan_tennis"):
                            d = j["d"]
                            canale.append((r, d.get("sport"), str(d.get("event_id")), d.get("updated_at"),
                                           d.get("payload") or {}))
            except Exception:
                await asyncio.sleep(1)
    asyncio.run(go())


fine = time.time() + MINUTI * 60
th = threading.Thread(target=ascolta, args=(fine,), daemon=True)
th.start()
db = []              # (letto, event_id, updated_at, riga, ms)
SEL = ("event_id,sport,updated_at,odds:payload->odds,minute:payload->minute,sh:payload->score_home,"
       "sa:payload->score_away,sets:payload->sets,games:payload->games,ots:payload->odds_ts_ms,"
       "opt:payload->odds_pt_ms,inplay:payload->inplay,mo:payload->>mo_market_id,mos:payload->>mo_status")
while time.time() < fine:
    st, righe, ms = get(f"safe_strategy_scan?select={SEL}&limit=5000")
    t = time.time()
    if st == 200:
        for r in righe:
            db.append((t, str(r["event_id"]), r["updated_at"], r, ms))
    time.sleep(8)
th.join(10)

# ---------------------------------------------------------------- analisi
idx = {}
for (rcv, sport, ev, upd, p) in canale:
    idx.setdefault((ev, k_upd(upd)), (rcv, sport, p))
coppie = uguali = diverse = 0
esempi_diversi = []
visti = set()
for (t, ev, upd, r, ms) in db:
    if (ev, k_upd(upd)) in visti:
        continue
    visti.add((ev, k_upd(upd)))
    c = idx.get((ev, k_upd(upd)))
    if not c:
        continue
    coppie += 1
    p = c[2]
    campi = {"odds": p.get("odds"), "minute": p.get("minute"), "sh": p.get("score_home"),
             "sa": p.get("score_away"), "sets": p.get("sets"), "games": p.get("games"),
             "ots": p.get("odds_ts_ms"), "opt": p.get("odds_pt_ms")}
    dbc = {k: r.get(k) for k in campi}
    if json.dumps(campi, sort_keys=True) == json.dumps(dbc, sort_keys=True):
        uguali += 1
    else:
        diverse += 1
        if len(esempi_diversi) < 5:
            esempi_diversi.append({"event_id": ev, "updated_at": upd,
                                   "diff": {k: [campi[k], dbc[k]] for k in campi
                                            if json.dumps(campi[k], sort_keys=True) != json.dumps(dbc[k], sort_keys=True)}})
db_distinte = {(ev, k_upd(upd)) for (_, ev, upd, _, _) in db}
t0 = min((x[0] for x in db), default=0) + 15
t1 = max((x[0] for x in db), default=0) - 15
db_centrali = {(ev, k_upd(upd)) for (t, ev, upd, _, _) in db if t0 <= ts(upd) <= t1}
mancanti = []
per_ev = {}
for (rcv, s, ev, upd, p) in canale:
    per_ev.setdefault(ev, []).append((ts(upd), upd, rcv, p))
riga_db = {(ev, k_upd(upd)): r for (_, ev, upd, r, _) in db}
for (ev, upd) in sorted(db_centrali - set(idx)):
    tu = upd
    vicini = sorted(per_ev.get(ev, []), key=lambda x: abs(x[0] - tu))[:2]
    r = riga_db[(ev, upd)]
    stessi = [v[1] for v in per_ev.get(ev, []) if json.dumps(v[3].get("odds"), sort_keys=True)
              == json.dumps(r.get("odds"), sort_keys=True) and v[3].get("minute") == r.get("minute")]
    mancanti.append({"event_id": ev, "updated_at_db": upd,
                     "canale_piu_vicini": [(v[1], round(v[0] - tu, 3)) for v in vicini],
                     "stesso_contenuto_sul_canale_con_updated_at": stessi[:3]})
mancanti = mancanti[:15]
lat_canale = sorted(rcv - ts(upd) for (rcv, s, ev, upd, p) in canale if upd)
lat_pt = sorted(ts(upd) - (p.get("odds_pt_ms") or 0) / 1000 for (rcv, s, ev, upd, p) in canale
                if upd and p.get("odds_pt_ms"))
lat_ts = sorted(ts(upd) - (p.get("odds_ts_ms") or 0) / 1000 for (rcv, s, ev, upd, p) in canale
                if upd and p.get("odds_ts_ms"))
ts_dopo = sum(1 for (rcv, s, ev, upd, p) in canale
              if upd and p.get("odds_ts_ms") and p["odds_ts_ms"] / 1000 > ts(upd) + 0.001)


def pct(a, q):
    return round(a[min(len(a) - 1, int(q * len(a)))], 3) if a else None


fuori_tick = incrociati = size_nulle = arb = 0
controllati = 0
es_libro = []
for (rcv, s, ev, upd, p) in canale:
    o = p.get("odds") or {}
    if not isinstance(o, dict) or not o:
        continue
    controllati += 1
    sb, sl, completo = 0.0, 0.0, True
    for sel, q in o.items():
        if not isinstance(q, dict):
            continue
        b, lay = q.get("back"), q.get("lay")
        for x in (b, lay):
            if x is not None and not sul_tick(float(x)):
                fuori_tick += 1
                if len(es_libro) < 5:
                    es_libro.append(("tick", ev, sel, x))
        if b is not None and lay is not None and float(b) >= float(lay):
            incrociati += 1
            if len(es_libro) < 5:
                es_libro.append(("incrocio", ev, sel, b, lay))
        for x, sz in ((b, q.get("back_size")), (lay, q.get("lay_size"))):
            if x is not None and (sz is None or float(sz) <= 0):
                size_nulle += 1
        if b is None or lay is None:
            completo = False
        else:
            sb += 1 / float(b)
            sl += 1 / float(lay)
    if completo and str(p.get("mo_status") or "OPEN") == "OPEN" and (sb < 0.99 or sl > 1.01):
        arb += 1
        if len(es_libro) < 8:
            es_libro.append(("arb", ev, round(sb, 4), round(sl, 4), upd))
esito = {"finestra_min": MINUTI, "fine_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
         "messaggi_canale": len(canale), "letture_db": len(db), "righe_db_distinte": len(db_distinte),
         "eventi_canale": len({x[2] for x in canale}),
         "stessa_riga": {"coppie": coppie, "identiche": uguali, "diverse": diverse, "esempi": esempi_diversi},
         "righe_db_non_viste_sul_canale": {"n": len(db_centrali - set(idx)), "su": len(db_centrali),
                                           "esempi": mancanti},
         "eta_canale_s": {"p50": pct(lat_canale, .5), "p95": pct(lat_canale, .95), "max": pct(lat_canale, 1)},
         "updated_meno_odds_pt_s": {"min": pct(lat_pt, 0), "p50": pct(lat_pt, .5), "p95": pct(lat_pt, .95),
                                    "max": pct(lat_pt, 1)},
         "updated_meno_odds_ts_s": {"min": pct(lat_ts, 0), "p50": pct(lat_ts, .5), "p95": pct(lat_ts, .95),
                                    "max": pct(lat_ts, 1)},
         "odds_ts_dopo_updated_at": ts_dopo,
         "libro": {"righe": controllati, "prezzi_fuori_tick": fuori_tick, "back_ge_lay": incrociati,
                   "size_nulle": size_nulle, "arbitraggio_impossibile": arb, "esempi": es_libro}}
print(json.dumps(esito, ensure_ascii=False, indent=1, default=str))
(QUI / "sonda_791_feed_esito.json").write_text(json.dumps(esito, ensure_ascii=False, indent=1, default=str),
                                                encoding="utf-8")
