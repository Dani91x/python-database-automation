"""M5 - dimensione e crescita dei log e delle registrazioni (sola lettura: solo os.stat/os.scandir).
 - log: per servizio (prefisso del file) e per giorno (data nel nome del file di sessione), esclusi/inclusi
   i backtest-worker; byte per ora di sessione (durata = mtime - istante di avvio nel nome file);
 - registrazioni: per evento in `_live_raw`, byte per tipo di file (jsonl snapshot, raw, scores, timeline...).
Uso: python -I m05_risorse_disco.py <cartella_log> <cartella_live_raw>
"""
import sys, os, re, collections, datetime as dt, statistics

LOG, RAW = sys.argv[1], sys.argv[2]
RX = re.compile(r'^(.*)_(\d{4}-\d\d-\d\d)T(\d\d)-(\d\d)-(\d\d)-\d+Z\.log$')
per_serv = collections.defaultdict(lambda: [0, 0, 0.0])    # byte, file, ore
per_giorno = collections.defaultdict(lambda: collections.Counter())
sess_dur = {}
for e in os.scandir(LOG):
    m = RX.match(e.name)
    if not m:
        continue
    serv, d, hh, mm, ss = m.groups()
    st = e.stat()
    t0 = dt.datetime.fromisoformat("%sT%s:%s:%s" % (d, hh, mm, ss)).replace(tzinfo=dt.timezone.utc)
    t1 = dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc)
    ore = max((t1 - t0).total_seconds() / 3600.0, 0.0)
    per_serv[serv][0] += st.st_size
    per_serv[serv][1] += 1
    per_serv[serv][2] += ore
    per_giorno[d][serv] += st.st_size
    per_giorno[d]['_ore_max'] = max(per_giorno[d]['_ore_max'], int(ore * 1000))
print("# LOG per servizio (tutti i file in %s)" % LOG)
tot = sum(v[0] for v in per_serv.values())
for s, (b, n, o) in sorted(per_serv.items(), key=lambda x: -x[1][0]):
    print("  %-22s %9.1f MB  %3d file  %6.1f ore-sessione  %8.2f MB/ora" % (s, b / 1048576, n, o, (b / 1048576) / o if o else 0))
print("  TOTALE %.1f MB" % (tot / 1048576))
print("\n# LOG per giorno (data di avvio sessione, UTC), MB: totale / senza backtest-worker / solo backtest-worker")
for d in sorted(per_giorno):
    c = per_giorno[d]
    bw = c.get('backtest-worker', 0)
    t = sum(v for k, v in c.items() if not k.startswith('_'))
    print("  %s  %8.1f / %8.1f / %8.1f" % (d, t / 1048576, (t - bw) / 1048576, bw / 1048576))
print("\n# REGISTRAZIONI in %s" % RAW)
tipo = collections.Counter()
ev_tot = []
ev_raw = []
for d in os.scandir(RAW):
    if not d.is_dir() or d.name.startswith('_synth'):
        continue
    tot_ev = 0
    for f in os.scandir(d.path):
        if f.is_file():
            n = f.name[len(d.name) + 1:] if f.name.startswith(d.name + '.') else f.name
            sz = f.stat().st_size
            tipo[n] += sz
            tot_ev += sz
            if n == 'raw.jsonl':
                ev_raw.append(sz)
    ev_tot.append(tot_ev)
print("  eventi: %d ; totale %.1f MB" % (len(ev_tot), sum(ev_tot) / 1048576))
for k, v in tipo.most_common():
    print("   %-16s %9.1f MB" % (k, v / 1048576))
q = sorted(ev_tot)
print("  per evento (tutti i file): p50 %.1f MB  p95 %.1f MB  max %.1f MB" % (
    q[len(q) // 2] / 1048576, q[int(len(q) * .95)] / 1048576, q[-1] / 1048576))
r = sorted(ev_raw)
print("  per evento (solo raw.jsonl): n=%d p50 %.1f MB  p95 %.1f MB  max %.1f MB" % (
    len(r), r[len(r) // 2] / 1048576, r[int(len(r) * .95)] / 1048576, r[-1] / 1048576))
