"""M1b - come m01_feed_raw.py ma aggregato PER SPORT (eventTypeId del marketDefinition) e con
buchi riferiti al solo tempo IN-PLAY. Sola lettura, a flusso.

Formato: Betfair/stream/raw_listener.py:178-188 (una riga = un `mcm` {op,clk,pt,ct,mc}); `pt` = publish
time di Betfair. L'istante di ricezione locale NON e' nel raw (raw_listener.py:175-176), i battiti
(ct=HEARTBEAT) NON sono scritti (raw_listener.py:158-165): un buco puo' essere mercato fermo, buco dello
stream o registratore spento (sidecar .recmeta.jsonl, raw_listener.py:90-137): per questo si riporta
anche il numero di buchi nel solo in-play, dove un mercato quieto e' raro.
Uso: python -I m01b_feed_per_sport.py <cartella _live_raw>
"""
import sys, os, json, glob, collections, time

RAW = sys.argv[1]


def pct(v, q):
    if not v:
        return float('nan')
    v = sorted(v)
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))]


def riass(v):
    if not v:
        return "n=0"
    return "n=%d p50=%.0f p95=%.0f p99=%.0f max=%.0f ms" % (len(v), pct(v, .5), pct(v, .95), pct(v, .99), max(v))


agg = collections.defaultdict(lambda: dict(
    ev=0, msg=0, byte=0, min_in=0.0, int_in=[], buchi5=0, buchi10=0, buchi30=0, mkt_in=[], bd=collections.Counter()))
files = [f for f in sorted(glob.glob(os.path.join(RAW, '*', '*.raw.jsonl'))) if '_synth' not in f]
t0 = time.time()
for f in files:
    sport = None
    prev = None
    inplay = {}
    last = {}
    a_int, a_mkt = [], []
    b5 = b10 = b30 = 0
    n = 0
    t_in = 0.0
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
            anyin = False
            for ch in m.get('mc') or []:
                mid = ch.get('id')
                md = ch.get('marketDefinition')
                if md:
                    inplay[mid] = bool(md.get('inPlay'))
                    if sport is None:
                        sport = md.get('eventTypeId')
                    if inplay[mid]:
                        agg_bd = md.get('betDelay')
                        agg[sport]['bd'][agg_bd] += 1
                if inplay.get(mid):
                    anyin = True
                    lp = last.get(mid)
                    if lp is not None and pt >= lp:
                        a_mkt.append(pt - lp)
                last[mid] = pt
            if prev is not None and pt >= prev and anyin:
                d = pt - prev
                a_int.append(d)
                t_in += d
                if d > 5000: b5 += 1
                if d > 10000: b10 += 1
                if d > 30000: b30 += 1
            prev = pt
    s = agg[sport]
    s['ev'] += 1; s['msg'] += n; s['byte'] += os.path.getsize(f)
    s['min_in'] += t_in / 60000.0
    s['int_in'] += a_int; s['mkt_in'] += a_mkt
    s['buchi5'] += b5; s['buchi10'] += b10; s['buchi30'] += b30
NOMI = {'1': 'calcio', '2': 'tennis', None: 'sconosciuto'}
print("# M1b feed raw per sport: %d file, lettura %.0f s" % (len(files), time.time() - t0))
for sp, s in sorted(agg.items(), key=lambda x: str(x[0])):
    print("\n## sport %s (%s): eventi %d, messaggi %d, MB raw %.1f, minuti in-play (somma intervalli) %.0f" % (
        sp, NOMI.get(sp, '?'), s['ev'], s['msg'], s['byte'] / 1048576, s['min_in']))
    print("   intervalli fra messaggi in-play : " + riass(s['int_in']))
    print("   intervalli per-mercato in-play  : " + riass(s['mkt_in']))
    print("   buchi in-play >5s/>10s/>30s     : %d/%d/%d" % (s['buchi5'], s['buchi10'], s['buchi30']))
    if s['min_in']:
        print("   buchi in-play >5s per ora in-play: %.2f" % (s['buchi5'] / (s['min_in'] / 60.0)))
    print("   betDelay delle definizioni in-play: %s" % dict(s['bd']))
