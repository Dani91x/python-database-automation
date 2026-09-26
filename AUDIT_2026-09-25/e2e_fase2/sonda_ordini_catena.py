"""sonda_ordini_catena.py - E2E FASE 2 (26/09), referto ADMIN26_ORDINI_SCHEDE. SOLA LETTURA.

Ricostruisce per ogni ordine PAPER di Omega/Safe nato dopo l'accensione la catena
  feed (scanner 47336, registrato da sonda_ordini_ascolto.py) -> condizione del bot (riga/meta)
  -> richiesta (coda DB betfair_live_order_requests / canale / ripiego dichiarato in attivita')
  -> ordine paper (riga) -> esito (size_matched/avg_price_matched) -> push sul canale del bot
con timestamp e latenze, e confronta il prezzo abbinato col libro del feed nello stesso istante
(ultimo record dello scanner ricevuto <= istante della decisione, e il successivo), tolleranza 1 tick,
usando la ladder dei tick di PRODUZIONE (Betfair.stream.trading.risk_engine.ticks_between).
DB: solo GET via sonda_ordini_db.get (select+limit espliciti).
Uso: python sonda_ordini_catena.py [--json out.json]
"""
import sys, json, glob, bisect, argparse
from datetime import datetime, timezone
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI))
sys.path.insert(0, str(QUI.parents[1]))
from sonda_ordini_db import get  # noqa: E402
from Betfair.stream.trading.risk_engine import ticks_between  # noqa: E402  (produzione)
from Betfair.stream.trading.stato_mercato import mercato_operabile, stato_da_riga_scan  # noqa: E402  (produzione)


def operabile(lb):
    """ricalcolo con la guardia UNICA di produzione sullo stato del mercato del feed."""
    if lb is None:
        return None
    return list(mercato_operabile(stato_da_riga_scan({"market_status": lb.get("status")})))

ACCESO = {"omega": "2026-09-26T09:10:26.216Z", "safe": "2026-09-26T09:13:20.500Z"}


def ms(v):
    if v is None:
        return None
    return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp() * 1000.0


def iso(m):
    return None if m is None else datetime.fromtimestamp(m / 1000, timezone.utc).strftime("%H:%M:%S.%f")[:-3] + "Z"


def carica_scan():
    per_ev = {}
    for f in sorted(glob.glob(str(QUI / "canali_ordini" / "scanner_*.jsonl"))):
        for l in open(f, encoding="utf-8"):
            try:
                r = json.loads(l)
            except Exception:
                continue
            if r.get("ev"):
                per_ev.setdefault(str(r["ev"]), []).append(r)
    for v in per_ev.values():
        v.sort(key=lambda r: r["rx_ms"])
    return per_ev


def carica_canale(nome):
    out = []
    for f in sorted(glob.glob(str(QUI / "canali_ordini" / f"{nome}_*.jsonl"))):
        for l in open(f, encoding="utf-8"):
            try:
                out.append(json.loads(l))
            except Exception:
                pass
    return out


def libro(rec, market_id, selection_id):
    """(back, lay, back_size, lay_size, status) della selezione nel record compatto."""
    blocchi = []
    if rec.get("cs"):
        blocchi.append(rec["cs"])
    if rec.get("ht"):
        blocchi.append(rec["ht"])
    for lst in (rec.get("altri") or {}).values():
        for b in lst:
            blocchi.append([b[0], b[3], b[4]])
    for b in blocchi:
        if str(b[0]) == str(market_id):
            for s in b[2]:
                if str(s[0]) == str(selection_id):
                    return {"back": s[3], "lay": s[4], "back_size": s[5], "lay_size": s[6], "status": b[1]}
    if str((rec.get("mo") or [None])[0]) == str(market_id):
        for _k, o in (rec.get("odds") or {}).items():
            if str(o[0]) == str(selection_id):
                return {"back": o[1], "lay": o[2], "back_size": o[3], "lay_size": o[4], "status": rec["mo"][1]}
    return None


def intorno(scan_ev, t_ms):
    """ultimo record con rx_ms <= t e il successivo."""
    if not scan_ev or t_ms is None:
        return None, None
    xs = [r["rx_ms"] for r in scan_ev]
    i = bisect.bisect_right(xs, t_ms)
    prima = scan_ev[i - 1] if i > 0 else None
    dopo = scan_ev[i] if i < len(scan_ev) else None
    return prima, dopo


def tick(a, b):
    try:
        return ticks_between(float(a), float(b))
    except Exception:
        return None


def verifica_prezzo(side, prezzo_abbinato, lb):
    """Un LAY taker abbina contro il best LAY esposto; un BACK taker contro il best BACK."""
    if lb is None:
        return {"esito": "libro_assente"}
    rif = lb["lay"] if side == "lay" else lb["back"]
    liq = lb["lay_size"] if side == "lay" else lb["back_size"]
    if rif is None or prezzo_abbinato is None:
        return {"esito": "prezzo_assente", "rif": rif}
    d = tick(rif, prezzo_abbinato)
    return {"rif": rif, "liq": liq, "delta_tick": d, "entro_1_tick": (d is not None and abs(d) <= 1),
            "status_mercato": lb["status"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--righe", help="scrive le righe DB grezze (per sonda_ordini_esito_b17.mjs)")
    a = ap.parse_args()
    scan = carica_scan()
    ch = {"omega": carica_canale("omega"), "safe": carica_canale("safe")}
    risultati = []
    _, om = get("omega_trades?select=*&placed_at=gte.%s&order=id.asc&limit=200" % ACCESO["omega"])
    _, sf = get("safe_strategy_trades?select=*&placed_at=gte.%s&order=id.asc&limit=200" % ACCESO["safe"])
    _, q = get("betfair_live_order_requests?select=id,client_ref,action,mode,market_id,selection_id,side,price,size,status,requested_at,processed_at&requested_at=gte.%s&order=id.asc&limit=200" % ACCESO["omega"])
    _, mir = get("betfair_live_orders?select=id,client_order_ref,mode,source,market_id,selection_id,side,price,size,size_matched,average_price_matched,status,placed_at&placed_at=gte.%s&order=id.asc&limit=500" % ACCESO["omega"])
    _, oa = get("omega_activity?select=id,ts,kind,payload&ts=gte.%s&kind=neq.skip&order=id.asc&limit=1000" % ACCESO["omega"])
    _, sa = get("safe_strategy_activity?select=id,ts,kind,payload&ts=gte.%s&kind=neq.skip&order=id.asc&limit=1000" % ACCESO["safe"])
    if a.righe:
        Path(a.righe).write_text(json.dumps({"omega": om, "safe": sf}, default=str), encoding="utf-8")
    print(f"omega_trades={len(om) if isinstance(om, list) else om} safe_trades={len(sf) if isinstance(sf, list) else sf} "
          f"coda_db={len(q) if isinstance(q, list) else q} specchio={len(mir) if isinstance(mir, list) else mir}")
    for bot, righe, att in (("omega", om, oa), ("safe", sf, sa)):
        if not isinstance(righe, list):
            continue
        for r in righe:
            tid = r["id"]
            meta = r.get("meta") or {}
            ev = str(r["event_id"])
            t_row = ms(r["placed_at"])
            a_rel = [x for x in (att if isinstance(att, list) else []) if (x.get("payload") or {}).get("trade_id") == tid]
            tempi = meta.get("tempi") or {}
            t_dec = tempi.get("t3_deciso_ms") or t_row
            t_fill = meta.get("t6_fill_ms") or next((ms(x["ts"]) for x in a_rel if x["kind"] == "place"), None)
            prima, dopo = intorno(scan.get(ev), t_dec)
            lb_p = libro(prima, r["market_id"], r["selection_id"]) if prima else None
            lb_d = libro(dopo, r["market_id"], r["selection_id"]) if dopo else None
            pa = r.get("avg_price_matched")
            # specchio del live: un FOK vero parte DOPO il bet delay; libro a t_fill + bet_delay
            bd = (prima or {}).get("bet_delay") or 0
            dopo_bd, _ = intorno(scan.get(ev), (t_fill or t_dec) + bd * 1000.0)
            lb_bd = libro(dopo_bd, r["market_id"], r["selection_id"]) if dopo_bd else None
            if lb_bd is not None and pa is not None:
                rif_bd = lb_bd["lay"] if r["side"] == "lay" else lb_bd["back"]
                liq_bd = lb_bd["lay_size"] if r["side"] == "lay" else lb_bd["back_size"]
                ok_prezzo = (rif_bd is not None and ((r["side"] == "lay" and rif_bd <= float(r["price"]) + 1e-9)
                                                     or (r["side"] == "back" and rif_bd >= float(r["price"]) - 1e-9)))
                fok_dopo_bd = {"bet_delay_s": bd, "rx": iso(dopo_bd["rx_ms"]), "libro": lb_bd,
                               "fok_avrebbe_abbinato": bool(ok_prezzo and (liq_bd or 0) + 1e-9 >= float(r["size"]))}
            else:
                fok_dopo_bd = {"bet_delay_s": bd, "esito": "libro_assente"}
            push = [m for m in ch[bot] if isinstance(m.get("d"), dict) and m["d"].get("id") == tid
                    and "posizioni" in str(m.get("t", ""))]
            push_open = next((m for m in push if m["d"].get("status") != "pending"), None)
            coda = [x for x in (q if isinstance(q, list) else []) if str(x["market_id"]) == str(r["market_id"])
                    and str(x.get("selection_id")) == str(r["selection_id"])]
            spec = [x for x in (mir if isinstance(mir, list) else []) if str(x["market_id"]) == str(r["market_id"])
                    and str(x.get("selection_id")) == str(r["selection_id"])]
            res = {
                "bot": bot, "trade_id": tid, "event": f'{ev} {r.get("event_name")}',
                "strategia": r.get("strategy") or r.get("phase"),
                "mercato": r["market_id"], "selezione": f'{r["selection_id"]} {r.get("runner_name") or r.get("selection_name")}',
                "side": r["side"], "mode": r["mode"], "status": r["status"], "origin": r.get("origin"),
                "prezzo_riga": r["price"], "size": r["size"], "size_matched": r.get("size_matched"),
                "avg_price_matched": pa, "minuto": r.get("minute_at_entry"), "punteggio": r.get("score_at_entry"),
                "fill_note": meta.get("fill"), "percorso": (meta.get("esecuzione") or {}).get("percorso"),
                "attivita": [(x["ts"], x["kind"], (x.get("payload") or {}).get("reason")) for x in a_rel],
                "coda_db_righe": len(coda), "specchio_righe": len(spec),
                "t": {"t0_quote_betfair": iso(tempi.get("t0_quote_ms")), "t1_feed": iso(tempi.get("t1_feed_ms")),
                      "t2_letto": iso(tempi.get("t2_letto_ms")), "t3_deciso": iso(t_dec),
                      "riga_placed_at": r["placed_at"], "t_fill": iso(t_fill),
                      "push_canale_open": iso(push_open["rx_ms"]) if push_open else None},
                "latenze_ms": {k: tempi.get(k) for k in ("feed_to_bot_ms", "prezzo_to_decisione_ms", "decisione_to_risposta_ms")},
                "scan_prima": None if not prima else {
                    "rx": iso(prima["rx_ms"]), "odds_pt": iso(prima.get("odds_pt_ms")), "odds_ts": iso(prima.get("odds_ts_ms")),
                    "min": prima.get("min"), "sc": prima.get("sc"), "libro": lb_p,
                    "eta_rispetto_decisione_ms": round(t_dec - prima["rx_ms"])},
                "scan_dopo": None if not dopo else {
                    "rx": iso(dopo["rx_ms"]), "min": dopo.get("min"), "sc": dopo.get("sc"), "libro": lb_d,
                    "dopo_decisione_ms": round(dopo["rx_ms"] - t_dec)},
                "verifica_prima": verifica_prezzo(r["side"], pa, lb_p),
                "verifica_dopo": verifica_prezzo(r["side"], pa, lb_d),
                "fok_dopo_bet_delay": fok_dopo_bd,
                "mercato_operabile_alla_decisione": operabile(lb_p),
                "mercato_operabile_dopo_bet_delay": operabile(lb_bd),
                "push_n": len(push),
                "push_canale": [{"rx": iso(m["rx_ms"]), "status": m["d"].get("status"), "size_matched": m["d"].get("size_matched"),
                                 "avg": m["d"].get("avg_price_matched"), "seq": m["d"].get("_seq")} for m in push[:3]],
                "push_uguale_db": ((push_open["d"].get("avg_price_matched") == pa
                                    and push_open["d"].get("size_matched") == r.get("size_matched")) if push_open else None),
            }
            risultati.append(res)
    for x in risultati:
        print(json.dumps(x, ensure_ascii=False, default=str))
    if a.json:
        Path(a.json).write_text(json.dumps(risultati, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
