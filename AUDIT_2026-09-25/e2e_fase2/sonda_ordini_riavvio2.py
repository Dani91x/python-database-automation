"""sonda_ordini_riavvio2.py - E2E FASE 2, RIAVVIO 2 (porte via canale ACCESE), 26/09. SOLA LETTURA.

Per ogni ordine Omega/Safe/Safe-tennis nato dopo il riavvio 2 ricostruisce:
  comando sul canale (diario del motore _live_raw/_diario_ordini[/tennis]/<giorno>.jsonl, sola lettura:
  inviato/rifiuto -> in_aggancio -> agganciato -> ordine (cor) -> esito) + eta' del comando
  (ts_ms - parametri.creato_ms, soglia max_eta_ms) + riga del bot (meta canale_*, stato, abbinato, medio)
  + specchio betfair_live_orders / tennis_live_orders per customerOrderRef + libro del feed registrato
  (sonda_ordini_ascolto.py) all'istante dell'ordine, delta tick (ticks_between di PRODUZIONE).
Controlli trasversali: ripieghi istantanei (paper_fill_fallback / paper_fill:follow_assente) dopo il riavvio,
righe della coda DB, righe live_follow origine='auto'.
Uso: python sonda_ordini_riavvio2.py [--json out.json]
"""
import sys, json, argparse
from pathlib import Path

QUI = Path(__file__).resolve().parent
RADICE = QUI.parents[1]
sys.path.insert(0, str(QUI))
import sonda_ordini_catena as C  # noqa: E402  (get, libro, intorno, tick, operabile, iso, ms)

DA = "2026-09-26T15:16:04Z"
DIARI = {"calcio": RADICE / "_live_raw" / "_diario_ordini" / "2026-09-26.jsonl",
         "tennis": RADICE / "_live_raw" / "_diario_ordini" / "tennis" / "2026-09-26.jsonl"}


def diario():
    per_ref = {}
    for sport, f in DIARI.items():
        if not f.exists():
            continue
        for l in open(f, encoding="ascii", errors="replace"):
            try:
                r = json.loads(l)
            except Exception:
                continue
            ref = r.get("ref")
            if ref:
                per_ref.setdefault(ref, []).append({**r, "_sport": sport})
    return per_ref


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    D = diario()
    scan = C.carica_scan()
    out = {"trasversali": {}, "ordini": []}
    _, om = C.get("omega_trades?select=*&placed_at=gte.%s&order=id.asc&limit=300" % DA)
    _, sf = C.get("safe_strategy_trades?select=*&placed_at=gte.%s&order=id.asc&limit=300" % DA)
    _, q = C.get("betfair_live_order_requests?select=id,client_ref,action,mode,requested_at,status&requested_at=gte.%s&order=id.asc&limit=300" % DA)
    _, lf = C.get("live_follow?select=event_id,status,origine,created_at,updated_at&origine=eq.auto&order=created_at.asc&limit=500")
    _, oa = C.get("omega_activity?select=id,ts,kind,payload&ts=gte.%s&kind=neq.skip&order=id.asc&limit=3000" % DA)
    _, sa = C.get("safe_strategy_activity?select=id,ts,kind,payload&ts=gte.%s&kind=neq.skip&order=id.asc&limit=3000" % DA)
    fb_o = [x for x in oa if x["kind"] == "paper_fill_fallback"] if isinstance(oa, list) else oa
    fb_s = [r["id"] for r in sf if "follow_assente" in str((r.get("meta") or {}).get("fill"))] if isinstance(sf, list) else sf
    out["trasversali"] = {
        "omega_trades": len(om), "safe_trades": len(sf), "coda_db_righe_dopo_riavvio": q,
        "live_follow_auto": {"totale": len(lf) if isinstance(lf, list) else lf,
                             "per_status": {s: sum(1 for r in lf if r["status"] == s) for s in {r["status"] for r in lf}} if isinstance(lf, list) else None,
                             "prima": lf[0] if isinstance(lf, list) and lf else None},
        "omega_paper_fill_fallback": fb_o, "safe_fill_follow_assente": fb_s,
        "omega_kinds": sorted({x["kind"] for x in oa}) if isinstance(oa, list) else oa,
        "safe_kinds": sorted({x["kind"] for x in sa}) if isinstance(sa, list) else sa,
        "diario_ref": len(D),
    }
    righe = [("omega", r) for r in om] + [("safe", r) for r in sf]
    for bot, r in righe:
        meta = r.get("meta") or {}
        pref = "omega" if bot == "omega" else ("safe_tennis" if r.get("sport") == "tennis" else "safe")
        ref = f"{pref}-t{r['id']}"
        ev = D.get(ref, [])
        inv = next((x for x in ev if x.get("tipo") == "inviato"), None)
        rif = [x for x in ev if x.get("tipo") == "rifiuto"]
        ag = next((x for x in ev if x.get("tipo") == "in_aggancio"), None)
        agd = next((x for x in ev if x.get("tipo") == "agganciato"), None)
        ordn = next((x for x in ev if x.get("tipo") == "ordine"), None)
        esi = [x for x in ev if x.get("tipo") == "esito"]
        par = (inv or {}).get("parametri") or {}
        eta = (inv["ts_ms"] - par["creato_ms"]) if inv and inv.get("ts_ms") and par.get("creato_ms") else None
        mir = None
        if ordn and ordn.get("cor"):
            tab = "tennis_live_orders" if ev and ev[0]["_sport"] == "tennis" else "betfair_live_orders"
            _, mir = C.get(f"{tab}?select=*&client_order_ref=eq.{ordn['cor']}&limit=3")
        t_ord = (ordn or {}).get("ts_ms") or C.ms(r["placed_at"])
        p, _d = C.intorno(scan.get(str(r["event_id"])), t_ord)
        lb = C.libro(p, r["market_id"], r["selection_id"]) if p else None
        pa = r.get("avg_price_matched")
        mm = (mir[0] if isinstance(mir, list) and mir else {}) or {}
        out["ordini"].append({
            "bot": bot, "id": r["id"], "ref": ref, "evento": f'{r["event_id"]} {r.get("event_name")}',
            "strategia": r.get("strategy") or r.get("phase"),
            "selezione": r.get("runner_name") or r.get("selection_name"), "side": r["side"],
            "prezzo_riga": r["price"], "size": r["size"], "status": r["status"],
            "size_matched": r.get("size_matched"), "avg_price_matched": pa, "placed_at": r["placed_at"],
            "meta_canale": {k: meta.get(k) for k in ("canale_ref", "canale_ack_seq", "canale_ack_ms", "canale_fase", "fill")},
            "prezzo_visto": meta.get("prezzo_visto"), "prezzo_segnale": meta.get("prezzo_segnale"),
            "comando": None if not inv else {"ts": C.iso(inv.get("ts_ms")), "attore": inv.get("attore"),
                                             "tif": par.get("time_in_force"), "price": par.get("price"),
                                             "size": par.get("size"), "eta_ms": eta, "max_eta_ms": par.get("max_eta_ms"),
                                             "ack": (inv.get("ack") or {}).get("accettato")},
            "rifiuti": [((x.get("ack") or {}).get("motivo") or "")[:120] for x in rif],
            "in_aggancio": None if not ag else C.iso(ag.get("ts_ms")),
            "agganciato_ms": None if not agd else agd.get("attesa_ms"),
            "ordine": None if not ordn else {"ts": C.iso(ordn["ts_ms"]), "cor": ordn.get("cor"),
                                             "price": ordn.get("price"), "size": ordn.get("size")},
            "esiti_diario": [{"ts": C.iso(x.get("ts_ms")), "ok": x.get("ok"), "err": (x.get("errore") or "")[:120],
                              "status": (x.get("risultato") or {}).get("status"),
                              "matched": (x.get("risultato") or {}).get("size_matched")} for x in esi],
            "specchio": {k: mm.get(k) for k in ("status", "size_matched", "average_price_matched", "size_lapsed",
                                                "size_cancelled", "placed_at", "matched_at", "source")} if mm else mir,
            "ref_coerente": (inv is None) or (inv.get("ref") == ref and meta.get("canale_ref") in (None, ref)),
            "prezzo_size_cmd_uguale_ordine": (None if not (inv and ordn) else
                                              (float(par.get("price")) == float(ordn.get("price"))
                                               and float(par.get("size")) == float(ordn.get("size")))),
            "libro_feed": None if not p else {"rx": C.iso(p["rx_ms"]), "eta_ms": round(t_ord - p["rx_ms"]), "libro": lb},
            "verifica_prezzo": C.verifica_prezzo(r["side"], pa if pa else None, lb),
            "operabile": C.operabile(lb),
        })
    for o in out["ordini"]:
        print(json.dumps(o, ensure_ascii=False, default=str))
    print(json.dumps(out["trasversali"], ensure_ascii=False, default=str)[:3000])
    if a.json:
        Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
