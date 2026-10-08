"""Per ogni fill per attraversamento del referto: il messaggio del raw a quell'istante
(stesso secondo), i livelli di trd che cambiano per la selezione e il delta per livello.
Sola lettura. Uso: python3 raw_verifica_fill.py <raw> "HH:MM:SS mercato sel prezzo_oltre" ...
"""
import json
import sys
import datetime as dt

raw = sys.argv[1]
casi = [x.split() for x in sys.argv[2:]]


def hm(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%H:%M:%S.%f")[:-3]


stato = {}
for i, l in enumerate(open(raw)):
    d = json.loads(l)
    for mc in d.get("mc") or []:
        mid = mc.get("id")
        if mc.get("img"):
            for k in [k for k in stato if k[0] == mid]:
                stato.pop(k)
        for rc in mc.get("rc") or []:
            k = (mid, rc.get("id"))
            st = stato.setdefault(k, {})
            trd = rc.get("trd") or []
            for ora, m, s, p in casi:
                if m == mid and int(s) == rc.get("id") and hm(d["pt"]).startswith(ora) and trd:
                    delta = [(pp, round(v - st.get(pp, 0.0), 2), round(st.get(pp, 0.0), 2))
                             for pp, v in trd]
                    print("%s %s sel %s riga %d: livelli %d, delta %s" % (
                        hm(d["pt"]), mid, s, i, len(trd),
                        [(pp, dl) for pp, dl, _ in delta]))
            for pp, v in trd:
                if v == 0:
                    st.pop(pp, None)
                else:
                    st[pp] = v
