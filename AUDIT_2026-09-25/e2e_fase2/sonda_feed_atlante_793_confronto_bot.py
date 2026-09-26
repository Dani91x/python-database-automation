"""sonda_feed_atlante_793_confronto_bot.py - 7.3.5/7.3.6/7.9.3.B: confronta i frame di Mike
(sonda_793_bot.jsonl) con la MIA consultazione (mia_consulta di sonda_feed_atlante_793_ricalcolo.py,
reimplementata) sull'atlante che il bot aveva in quel momento (copia salvata da sonda_793_bot, la piu'
recente con generated_at <= published_at del frame), con gli STESSI input: lega e id squadra del
dossier, minuto e gol del frame, tempo dal campione IPS piu' vicino (sonda_793_ips.jsonl).
Uso: python sonda_feed_atlante_793_confronto_bot.py <dir_copie>
"""
import datetime as dt
import json
import sys
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI))
sys.argv, copie = [sys.argv[0]], Path(sys.argv[1])
import sonda_feed_atlante_793_ricalcolo as R  # noqa: E402


def ts(s):
    d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).timestamp()


atlanti = []
for f in copie.glob("hazard_atlas_live_m*.json"):
    a = json.loads(f.read_text(encoding="utf-8"))
    # vale da quando e' stato SCRITTO (mtime nel nome), non da generated_at (inizio del ciclo)
    atlanti.append((float(f.stem.split("_m", 1)[1]), a))
atlanti.sort(key=lambda x: x[0])
ips = {}
for line in (QUI / "sonda_793_ips.jsonl").read_text(encoding="utf-8").splitlines():
    r = json.loads(line)
    ips.setdefault(str(r["event_id"]), []).append((ts(r["updated_at"]), r))
frames = {}
for line in (QUI / "sonda_793_bot.jsonl").read_text(encoding="utf-8").splitlines():
    for m in json.loads(line).get("mike") or []:
        if m.get("pub"):
            frames[(m["event_id"], m["pub"])] = m
out = {"frame": len(frames), "confrontati": 0, "uguali": 0, "diversi": [], "per_fase": {}, "versioni": {},
       "volatile": [], "senza_atlante_copia": 0}
per_ev = {}
for (ev, pub), m in sorted(frames.items(), key=lambda x: x[0][1]):
    t = ts(pub)
    cand = [a for (g, a) in atlanti if g <= t]
    if not cand:
        out["senza_atlante_copia"] += 1
        continue
    atlas = cand[-1]
    vicini = sorted(ips.get(ev, []), key=lambda x: abs(x[0] - t))
    raw = vicini[0][1].get("score_raw") if vicini and abs(vicini[0][0] - t) < 20 else None
    tempo = R.mio_tempo(raw, m["minute"]) if raw is not None else None
    goals = int(m.get("sh") or 0) + int(m.get("sa") or 0)
    mio = R.mia_consulta(atlas, float(m["minute"]), goals, m.get("lid"), tempo, m.get("hid"), m.get("aid"))
    out["confrontati"] += 1
    key = f"{m.get('hv')}|{m.get('hf')}"
    out["versioni"][key] = out["versioni"].get(key, 0) + 1
    # il VALORE pubblicato (hazard_atlas, 4 decimali) si confronta sempre, anche se le chiavi
    # di versione/fase mancano dal frame (reperto 7.3.5)
    if mio.get("p_3min") is not None and m.get("ha") is not None:
        out.setdefault("valore", {"uguali": 0, "diversi": []})
        if abs(round(mio["p_3min"], 4) - float(m["ha"])) <= 1e-4:
            out["valore"]["uguali"] += 1
        else:
            out["valore"]["diversi"].append([ev, pub, m["minute"], goals, tempo, m["ha"], round(mio["p_3min"], 4)])
    out.setdefault("chiavi_v4_nel_frame", {"presenti": 0, "assenti": 0})
    out["chiavi_v4_nel_frame"]["presenti" if m.get("hv") else "assenti"] += 1
    ok = mio["versione"] == m.get("hv")
    if ok and mio["versione"] == "v4":
        ok = (mio["fase"] == m.get("hf") and m.get("ha") is not None
              and abs(round(mio["p_3min"], 4) - float(m["ha"])) <= 1e-4
              and mio["recupero_atteso_min"] == m.get("hr"))
    if ok:
        out["uguali"] += 1
    elif len(out["diversi"]) < 10:
        out["diversi"].append({"ev": ev, "pub": pub, "minute": m["minute"], "gol": goals, "tempo_mio": tempo,
                               "lid": m.get("lid"), "mike": {k: m.get(k) for k in ("ha", "hv", "hf", "hr", "hn")},
                               "mio": mio})
    per_ev.setdefault(ev, []).append((t, m))
for ev, lst in per_ev.items():
    for (t1, a), (t2, b) in zip(lst, lst[1:]):
        if 50 <= t2 - t1 <= 70 and a.get("hf") == "recupero_2T":
            out["volatile"].append({"ev": ev, "min": [a["minute"], b["minute"]], "hr": [a.get("hr"), b.get("hr")],
                                    "hv": [a.get("hv"), b.get("hv")], "hf": [a.get("hf"), b.get("hf")]})
out["volatile"] = out["volatile"][:10]
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
(QUI / "sonda_793_confronto_bot_esito.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str),
                                                         encoding="utf-8")
