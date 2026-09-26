"""sonda_automode_analisi.py - legge automode_safe/armate_*.jsonl (sonda_automode_armate.py) e stampa
la CRONOLOGIA delle voci 7.6 / 7.7 / 7.9.6: per ogni giro le divergenze (armabili non armate con posti
liberi, oltre tetto, dry_run=false su auto, righe tennis non paper/dry_run), e per ogni partita le
transizioni (nel feed / fuori, stato della sessione/righe, follow). Sola lettura di file locali.
Uso: python sonda_automode_analisi.py [file.jsonl]
"""
import glob
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent / "automode_safe"


def main(fn):
    righe = [json.loads(x) for x in open(fn, encoding="utf-8") if x.strip()]
    prec_sc, prec_feed_sc, prec_t, prec_tf = {}, None, {}, {}
    cont = {"giri": 0, "errori": 0}
    div = []
    for r in righe:
        if "errore" in r:
            cont["errori"] += 1
            print(r["ts_utc"][11:19], "ERRORE", r["errore"][:120])
            continue
        cont["giri"] += 1
        ts = r["ts_utc"][11:19]
        s = r["scalper"]
        feed_sc = set(s["ordine_feed_con_vita"])  # prime 12 (solo informativo)
        stato = {e[0]: (e[3], e[2]) for e in s["righe_oggi"]}  # ev -> (requested_at, origine) non usato
        cur = {e[0]: e[1] for e in s["righe_oggi"]}
        for ev, st in cur.items():
            if prec_sc.get(ev) != st:
                print(ts, "SCALPER", ev, prec_sc.get(ev), "->", st, "| con vita:", s["feed_con_vita"],
                      "feed:", s["feed_partite"], "fuori feed:", ev in s["auto_non_nel_feed"])
        prec_sc = cur
        for k in ("difetto_posti_con_armabili", "difetto_oltre_tetto"):
            if s[k]:
                div.append((ts, "scalper", k, s["posti_liberi"], s["armabili_non_armate"][:5]))
        if s["auto_dry_run_false"]:
            div.append((ts, "scalper", "auto_dry_run_false", s["auto_dry_run_false"]))
        if s["mode"] != "paper":
            div.append((ts, "scalper", "mode", s["mode"]))
        if s["auto_oltre_vita"]:
            div.append((ts, "scalper", "auto_oltre_vita (sessione viva su partita oltre la vita)",
                        s["auto_oltre_vita"]))
        t = r["tennis"]
        for ev, st in (t.get("auto_fuori_feed_stato_now") or {}).items():
            if prec_tf.get(("now", ev)) != st:
                print(ts, "TENNIS now", ev, prec_tf.get(("now", ev)), "->", st)
                prec_tf[("now", ev)] = st
        fo = {e[0]: e[1] for e in t.get("follow_auto_oggi") or []}
        for ev, st in fo.items():
            if prec_tf.get(ev) != st:
                print(ts, "TENNIS follow", ev, prec_tf.get(ev), "->", st)
                prec_tf[ev] = st
        for bot, b in t["bot"].items():
            cur_t = set(b["armate_auto"])
            old = prec_t.get(bot, set())
            if cur_t != old:
                print(ts, "TENNIS", bot, "+", sorted(cur_t - old), "-", sorted(old - cur_t),
                      "n=", len(cur_t), "tetto", b["tetto"], "fuori feed:", b["auto_fuori_feed"],
                      "stopping:", b["stopping"])
            prec_t[bot] = cur_t
            if b["oltre_tetto"]:
                div.append((ts, bot, "oltre_tetto", len(cur_t), b["auto_fuori_feed"]))
            if b["difetto_nuove_attese"]:
                div.append((ts, bot, "nuove_attese_non_armate", b["nuove_attese"]))
            if b["righe_live"]:
                div.append((ts, bot, "righe_non_paper_o_dry_run_true", b["righe_live"]))
            if b["mode"] != "paper":
                div.append((ts, bot, "mode", b["mode"]))
    print("\n== giri", cont)
    print("== divergenze (per giro):")
    for d in div:
        print("  ", d)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob(str(DIR / "armate_*.jsonl")))[-1])
