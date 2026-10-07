# Estrae dal raw della registrazione il book del CORRECT SCORE a minuti
# campione (minuto e punteggio dal sidecar IPS, source betfair).
import json, math, sys
RAW = "/home/user/python-database-automation/_live_raw"
NOMI_ALTRI = {9063254: "Any Other Home Win", 9063255: "Any Other Away Win",
              9063256: "Any Other Draw"}


def nome(sid):
    if sid in NOMI_ALTRI:
        return NOMI_ALTRI[sid]
    k = int(math.isqrt(sid - 1))
    pos = sid - (k * k + 1)
    if pos <= k:
        return f"{k} - {pos}"
    return f"{2 * k - pos} - {k}"


def estrai(ev, mid, passo=2):
    punteggi = []
    for line in open(f"{RAW}/{ev}/{ev}.scores.jsonl"):
        r = json.loads(line)
        if r.get("source") == "betfair" and r.get("minute") is not None \
                and r.get("score_home") is not None:
            punteggi.append((r["ts_ms"], int(r["minute"]), int(r["score_home"]),
                             int(r["score_away"])))
    voluti = {}
    for ts, m, h, a in punteggi:
        if (1 <= m <= 44 or 46 <= m <= 85) and m % passo == 1 and m not in voluti:
            voluti[m] = (ts, h, a)
    soglie = sorted((ts, m, h, a) for m, (ts, h, a) in voluti.items())
    book = {}
    stati = {}
    out = []
    i = 0
    for line in open(f"{RAW}/{ev}/{ev}.raw.jsonl"):
        d = json.loads(line)
        pt = int(d.get("pt") or 0)
        while i < len(soglie) and pt > soglie[i][0]:
            ts, m, h, a = soglie[i]
            righe = []
            for sid in sorted(book):
                if stati.get(sid, "ACTIVE") != "ACTIVE":
                    continue
                atl = {p: s for p, s in book[sid]["atl"].items() if s > 0}
                atb = {p: s for p, s in book[sid]["atb"].items() if s > 0}
                lp = min(atl) if atl else None
                bp = max(atb) if atb else None
                righe.append([sid, nome(sid), lp, round(atl[lp], 2) if lp else 0.0,
                              bp, round(atb[bp], 2) if bp else 0.0])
            out.append({"event_id": ev, "market_id": mid, "minuto": m,
                        "punteggio": [h, a], "runners": righe})
            i += 1
        for mc in d.get("mc") or []:
            if mc.get("id") != mid:
                continue
            if mc.get("img"):
                book.clear()
            md = mc.get("marketDefinition")
            if md:
                for r in md.get("runners") or []:
                    stati[int(r["id"])] = r.get("status") or "ACTIVE"
            for rc in mc.get("rc") or []:
                sid = int(rc["id"])
                b = book.setdefault(sid, {"atb": {}, "atl": {}})
                for lato in ("atb", "atl"):
                    for p, s in rc.get(lato) or []:
                        b[lato][float(p)] = float(s)
    return out


dati = estrai("35797769", "1.259819681") + estrai("35760084", "1.259475532")
json.dump({"fonte": "_live_raw/<evento>/<evento>.raw.jsonl + .scores.jsonl "
                    "(registrazioni vere; nomi degli aggregati come il catalogo Betfair)",
           "campioni": dati}, open(sys.argv[1], "w"), separators=(",", ":"))
print(len(dati), [(c["event_id"], c["minuto"], c["punteggio"]) for c in dati])
