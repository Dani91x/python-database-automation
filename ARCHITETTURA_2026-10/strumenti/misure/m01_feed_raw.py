"""M1 - eta' e regolarita' del feed dalle registrazioni raw dello stream (sola lettura).

Formato (Betfair/stream/raw_listener.py:178-188): una riga = un messaggio `mcm` con
{op, clk, pt, ct, mc:[{id, marketDefinition?, rc?...}]}. `pt` = publish time di Betfair (ms).
NON c'e' l'istante di ricezione locale: il raw non lo registra (raw_listener.py:175-176 scrive solo
op/clk/pt/ct/mc) e i battiti (ct=HEARTBEAT) NON sono scritti (raw_listener.py:158-165).
Quindi qui si misurano: intervallo fra messaggi consecutivi (per file e per mercato) e buchi.
Uso: python -I m01_feed_raw.py <cartella _live_raw> [soglia_s=5]
"""
import sys, os, json, glob, statistics, collections, time

RAW = sys.argv[1]
SOGLIE = (5.0, 10.0, 30.0)


def pct(v, q):
    if not v:
        return float('nan')
    v = sorted(v)
    k = min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))
    return v[k]


def riassumi(v):
    if not v:
        return "n=0"
    return "n=%d p50=%.0f p95=%.0f p99=%.0f max=%.0f ms" % (len(v), pct(v, .5), pct(v, .95), pct(v, .99), max(v))


files = sorted(glob.glob(os.path.join(RAW, '*', '*.raw.jsonl')))
files = [f for f in files if '_synth' not in f]
tot_int_all, tot_int_inplay, tot_mkt_inplay = [], [], []
buchi_all = collections.Counter()
print("# M1 feed raw: %d file" % len(files))
righe_ev = []
t0 = time.time()
for f in files:
    ev = os.path.basename(os.path.dirname(f))
    size = os.path.getsize(f)
    n = 0
    prev_pt = None
    inplay = {}            # market_id -> bool
    last_mkt = {}          # market_id -> pt ultimo cambio
    int_all, int_in, mkt_in = [], [], []
    buchi = collections.Counter()
    buchi_in = collections.Counter()
    max_gap = 0
    max_gap_in = 0
    first_pt = last_pt = None
    bet_delay = collections.Counter()
    ct_cnt = collections.Counter()
    nonmono = 0
    with open(f, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            try:
                m = json.loads(line)
            except ValueError:
                continue
            pt = m.get('pt')
            if not isinstance(pt, (int, float)):
                continue
            n += 1
            ct_cnt[m.get('ct') or '-'] += 1
            if first_pt is None:
                first_pt = pt
            last_pt = pt
            # stato in-play del mercato dai marketDefinition
            any_inplay = False
            for ch in m.get('mc') or []:
                mid = ch.get('id')
                md = ch.get('marketDefinition')
                if md:
                    inplay[mid] = bool(md.get('inPlay'))
                    bd = md.get('betDelay')
                    bet_delay[(md.get('marketType'), bool(md.get('inPlay')), bd)] += 1
                if inplay.get(mid):
                    any_inplay = True
                lp = last_mkt.get(mid)
                if lp is not None and inplay.get(mid) and pt >= lp:
                    mkt_in.append(pt - lp)
                last_mkt[mid] = pt
            if prev_pt is not None:
                d = pt - prev_pt
                if d < 0:
                    nonmono += 1
                else:
                    int_all.append(d)
                    if any_inplay:
                        int_in.append(d)
                    for s in SOGLIE:
                        if d > s * 1000:
                            buchi[s] += 1
                            if any_inplay:
                                buchi_in[s] += 1
                    max_gap = max(max_gap, d)
                    if any_inplay:
                        max_gap_in = max(max_gap_in, d)
            prev_pt = pt
    dur = ((last_pt - first_pt) / 60000.0) if first_pt else 0
    righe_ev.append((ev, size, n, dur))
    tot_int_all += int_all
    tot_int_inplay += int_in
    tot_mkt_inplay += mkt_in
    for s, c in buchi.items():
        buchi_all[('tutti', s)] += c
    for s, c in buchi_in.items():
        buchi_all[('inplay', s)] += c
    print("\n## evento %s  file %.1f MB  messaggi %d  durata %.1f min  msg/s %.2f  non-monotoni %d" % (
        ev, size / 1048576, n, dur, (n / (dur * 60)) if dur else 0, nonmono))
    print("   byte/messaggio %.0f  byte/min %.0f" % (size / max(n, 1), size / max(dur, 1e-9)))
    print("   intervalli fra messaggi (tutti)  : " + riassumi(int_all))
    print("   intervalli fra messaggi (inplay) : " + riassumi(int_in))
    print("   intervalli per-mercato (inplay)  : " + riassumi(mkt_in))
    print("   buchi >5s/>10s/>30s tutti: %d/%d/%d ; in-play: %d/%d/%d ; max buco tutti %.1f s, in-play %.1f s" % (
        buchi[5.0], buchi[10.0], buchi[30.0], buchi_in[5.0], buchi_in[10.0], buchi_in[30.0], max_gap / 1000, max_gap_in / 1000))
    print("   ct: %s" % dict(ct_cnt))
    bd = collections.Counter()
    for (mt, ip, d), c in bet_delay.items():
        bd[(ip, d)] += c
    print("   betDelay osservato (inPlay,betDelay): n_definizioni %s" % dict(bd))

print("\n# TOTALE su %d eventi (tempo di lettura %.0f s)" % (len(files), time.time() - t0))
print("intervalli fra messaggi (tutti)   : " + riassumi(tot_int_all))
print("intervalli fra messaggi (in-play) : " + riassumi(tot_int_inplay))
print("intervalli per-mercato (in-play)  : " + riassumi(tot_mkt_inplay))
for k in sorted(buchi_all):
    print("buchi", k, buchi_all[k])
print("MB totali raw: %.1f  messaggi: %d  minuti: %.0f" % (
    sum(r[1] for r in righe_ev) / 1048576, sum(r[2] for r in righe_ev), sum(r[3] for r in righe_ev)))
