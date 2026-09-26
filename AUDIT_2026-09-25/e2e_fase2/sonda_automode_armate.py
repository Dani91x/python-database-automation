"""sonda_automode_armate.py - E2E FASE 2 (26/09), referto ADMIN26_AUTOMODE_SAFE, voci 7.6/7.7/7.9.6.

SOLA LETTURA (GET PostgREST, select+limit espliciti). Ogni N secondi fotografa NELLO STESSO GIRO:
  - il feed unico calcio e tennis (safe_strategy_scan, STESSA proiezione che leggono lo scalper
    `scalper_service.Db.feed_calcio` e il ponte tennis `tennis_db.list_tennis_feed_rows`)
  - il battito dello scanner (safe_strategy_status id='scanner')
  - scalper_service_control, scalper_control (righe di oggi), live_follow delle partite del feed
  - tennis_bot_service_control, tennis_bot_control (righe di oggi), tennis_live_follow PENDING/STREAMING
  - tennis_live_now delle partite automatiche uscite dal feed
e ricalcola l'insieme ATTESO con le funzioni di PRODUZIONE importate (mai riscritte):
  scalper: Betfair.stream.scalper.auto_mode (partite_dal_feed, ha_ancora_vita, motivo_esclusione,
           scegli_partite, tetto_partite, STATI_CON_PROCESSO, origine_riga, FOLLOW_CHIUSI)
  tennis : Betfair.stream.tennis_live.auto_mode (partite_dal_feed, scegli_partite, tetto_partite,
           origine_follow) + chiusura_manuale.chiusi_dall_utente
Scrive una riga JSONL per giro in automode_safe/armate_<tag>.jsonl con: armate vere, attese, differenze.
Uso: python sonda_automode_armate.py <minuti> [ogni_s]
"""
import json
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sonda_automode_db as DB  # noqa: E402
from Betfair.stream.scalper import auto_mode as SAM  # noqa: E402
from Betfair.stream.tennis_live import auto_mode as TAM  # noqa: E402
from Betfair.stream.tennis_live import chiusura_manuale as CM  # noqa: E402

OUT = Path(__file__).resolve().parent / "automode_safe"
OUT.mkdir(exist_ok=True)
TAG = time.strftime("%Y%m%d_%H%M%S")
f_out = open(OUT / f"armate_{TAG}.jsonl", "a", encoding="utf-8")

CAL_KEYS = SAM.CHIAVI_FEED
TEN_KEYS = ("p1", "p2", "competition", "open_date", "inplay", "mo_market_id", "mo_status")
OGGI = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
ATTIVI_TENNIS = ["requested", "arming", "armed", "running"]


def q(v):
    return urllib.parse.quote(str(v), safe="")


def feed(sport, keys):
    sel = ",".join(["event_id", "sport", "updated_at"] + ["%s:payload->%s" % (k, k) for k in keys])
    rows = DB.get(f"safe_strategy_scan?select={sel}&sport=eq.{sport}&limit=2000")
    return [{"event_id": r.get("event_id"), "sport": r.get("sport"), "updated_at": r.get("updated_at"),
             "payload": {k: r.get(k) for k in keys}} for r in rows]


def in_list(ids):
    return "(" + ",".join(q(i) for i in ids) + ")"


def giro():
    ora = time.time()
    rec = {"ts_utc": datetime.fromtimestamp(ora, tz=timezone.utc).isoformat()}
    fc = feed("calcio", CAL_KEYS)
    ft = feed("tennis", TEN_KEYS)
    hb = DB.get("safe_strategy_status?select=updated_at&id=eq.scanner&limit=1")
    eta = TAM.eta_s(hb[0]["updated_at"], ora) if hb else None
    vivo = eta is not None and eta <= SAM.SCANNER_VIVO_S
    rec["scanner_eta_s"] = None if eta is None else round(eta, 1)
    rec["feed_righe"] = {"calcio": len(fc), "tennis": len(ft)}

    # ---------------- SCALPER ----------------
    serv = (DB.get("scalper_service_control?select=*&id=eq.1&limit=1") or [{}])[0]
    sc_rows = DB.get("scalper_control?select=event_id,status,requested_at,started_at,stopped_at,"
                     "heartbeat_at,dry_run,origine,mode,stake,error,updated_at"
                     f"&updated_at=gte.{OGGI}&limit=500")
    per_ev = {str(r["event_id"]): r for r in sc_rows}
    params = serv.get("params") if isinstance(serv.get("params"), dict) else {}
    tetto = SAM.tetto_partite(params, env={})
    partite = SAM.partite_dal_feed(fc) if vivo else []
    ids_feed = [p["event_id"] for p in partite]
    vive = [p for p in partite if SAM.ha_ancora_vita(p.get("open_date"), params, ora)]
    ids = [p["event_id"] for p in vive]
    fol = {}
    for i in range(0, len(ids), 80):
        blk = ids[i:i + 80]
        for r in DB.get(f"live_follow?select=event_id,status&event_id=in.{in_list(blk)}&limit=200"):
            fol[str(r["event_id"])] = str(r.get("status") or "")
    con_proc = [r for r in sc_rows if str(r.get("status")) in SAM.STATI_CON_PROCESSO]
    auto_proc = [r for r in con_proc if SAM.origine_riga(r) == SAM.ORIGINE_AUTO]
    acceso_dal = serv.get("started_at")

    def escl(ev):
        if str(fol.get(ev) or "").upper() in SAM.FOLLOW_CHIUSI:
            return True
        return SAM.motivo_esclusione(per_ev.get(ev), acceso_dal) is not None

    armabili = [ev for ev in ids if not escl(ev)]
    posti = max(0, tetto - len(con_proc))
    rec["scalper"] = {
        "status": serv.get("status"), "mode": serv.get("mode"), "started_at": acceso_dal,
        "tetto": tetto, "stats_auto": (serv.get("stats") or {}).get("auto"),
        "feed_partite": len(partite), "feed_con_vita": len(ids),
        "ordine_feed_con_vita": ids[:12],
        "con_processo": [(r["event_id"], r["status"], SAM.origine_riga(r), r.get("dry_run")) for r in con_proc],
        "armabili_non_armate": armabili[:12], "posti_liberi": posti,
        "auto_non_nel_feed": [r["event_id"] for r in auto_proc if str(r["event_id"]) not in set(ids_feed)],
        "auto_dry_run_false": [r["event_id"] for r in sc_rows
                               if SAM.origine_riga(r) == "auto" and r.get("dry_run") is not True],
        "auto_oltre_vita": [r["event_id"] for r in auto_proc if str(r["event_id"]) in set(ids_feed)
                            and str(r["event_id"]) not in set(ids)],
        "difetto_posti_con_armabili": bool(serv.get("status") == "running" and posti > 0 and armabili),
        "difetto_oltre_tetto": len(con_proc) > tetto,
        "righe_oggi": [(r["event_id"], r["status"], SAM.origine_riga(r), r.get("requested_at"),
                        r.get("stopped_at")) for r in sc_rows],
    }

    # ---------------- TENNIS ----------------
    svc = DB.get("tennis_bot_service_control?select=bot_key,status,mode,uscite_automatiche,params,stats,"
                 "started_at,heartbeat_at&limit=10")
    tb = DB.get("tennis_bot_control?select=event_id,bot_key,status,mode,dry_run,uscite_automatiche,stats,"
                f"requested_at,started_at,stopped_at,updated_at&updated_at=gte.{OGGI}&limit=1000")
    tf = DB.get("tennis_live_follow?select=event_id,status,origine,market_id,created_at,updated_at"
                "&status=in.(PENDING,STREAMING)&limit=500")
    tf_oggi = DB.get("tennis_live_follow?select=event_id,status,origine,updated_at"
                     f"&origine=eq.auto&updated_at=gte.{OGGI}&limit=500")
    tpart = TAM.partite_dal_feed(ft) if vivo else []
    cand = [p["event_id"] for p in tpart]
    seguite_mano = {str(f["event_id"]) for f in tf if TAM.origine_follow(f) == TAM.ORIGINE_MANUALE}
    auto_seg = {str(f["event_id"]) for f in tf if TAM.origine_follow(f) == TAM.ORIGINE_AUTO}
    occupate = [r for r in tb if r["status"] in ATTIVI_TENNIS + ["stopping"]]
    in_chius = {(str(r["event_id"]), str(r["bot_key"])) for r in occupate if r["status"] == "stopping"}
    fermi = [r for r in tb if r["status"] in ("stopped", "error", "done")]
    chiusi_ut = CM.chiusi_dall_utente(fermi)
    fuori = sorted(e for e in auto_seg if e not in set(cand))
    now_st = {}
    if fuori:
        for r in DB.get(f"tennis_live_now?select=event_id,status&event_id=in.{in_list(fuori)}&limit=200"):
            now_st[str(r["event_id"])] = str(r.get("status") or "")
    rt = {"feed_partite": len(cand), "ordine_feed": cand[:15], "seguite_a_mano": sorted(seguite_mano),
          "follow_auto_attivi": sorted(auto_seg), "auto_fuori_feed_stato_now": now_st,
          "follow_auto_oggi": [(f["event_id"], f["status"]) for f in tf_oggi], "bot": {}}
    for s in svc:
        bot = s["bot_key"]
        t_bot = TAM.tetto_partite(s.get("params"), env={})
        att = {str(r["event_id"]): r for r in tb if r["bot_key"] == bot and r["status"] in ATTIVI_TENNIS}

        def esc(ev, _bot=bot):
            if ev in seguite_mano or (ev, _bot) in in_chius:
                return True
            if (ev, _bot) in chiusi_ut:
                return True
            return any(str(r["bot_key"]) == _bot and str(r["event_id"]) == ev
                       and r["status"] in ("done", "error") for r in fermi)

        gia = [ev for ev in att if ev not in seguite_mano]
        scelta = TAM.scegli_partite(cand, gia, esc, t_bot)
        auto_arm = [ev for ev in att if ev not in seguite_mano]
        rt["bot"][bot] = {
            "status": s["status"], "mode": s["mode"], "uscite_automatiche": s.get("uscite_automatiche"),
            "tetto": t_bot, "stats_auto": (s.get("stats") or {}).get("auto"),
            "motivo_blocco": (s.get("stats") or {}).get("motivo_blocco"),
            "armate_auto": sorted(auto_arm), "armate_a_mano": sorted(e for e in att if e in seguite_mano),
            "tengo": scelta["tengo"], "nuove_attese": scelta["nuove"],
            "auto_fuori_feed": sorted(e for e in auto_arm if e not in set(cand)),
            "righe_live": [(ev, r["status"], r["mode"], r["dry_run"], r.get("uscite_automatiche"))
                           for ev, r in att.items() if r["mode"] != "paper" or r["dry_run"] is not False],
            "difetto_nuove_attese": bool(s["status"] == "running" and scelta["nuove"]),
            "oltre_tetto": len(auto_arm) > t_bot,
            "stopping": sorted(str(r["event_id"]) for r in occupate
                               if r["bot_key"] == bot and r["status"] == "stopping"),
        }
    rec["tennis"] = rt
    return rec


def main(mins, ogni):
    fine = time.time() + mins * 60
    while time.time() < fine:
        t0 = time.time()
        try:
            rec = giro()
        except Exception as e:
            rec = {"ts_utc": datetime.now(timezone.utc).isoformat(), "errore": repr(e)[:400]}
        f_out.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        f_out.flush()
        time.sleep(max(1.0, ogni - (time.time() - t0)))


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 150, float(sys.argv[2]) if len(sys.argv) > 2 else 45)
