"""M4 - richieste al DB per servizio e tabella al minuto, dai log dell'app (sola lettura, a flusso).

Riusa il metodo di SCHEMI_BOT/sistema/strumenti/misura_chiamate_db.py (conta le righe
`HTTP Request: <METODO> https://<host>/rest/v1/<tabella>` scritte da httpx), ma su TUTTA la
sessione e non su una finestra: per ogni servizio, richieste totali, durata attiva, media/min,
p50/p95/p99/max dei conteggi al minuto (minuti vuoti inclusi), e le prime tabelle.
httpx NON scrive la durata della richiesta: la latenza HTTP non e' misurabile da questi log.
Uso: python -I m04_chiamate_db.py <cartella_log> <id_sessione> [<id_sessione> ...]
     id_sessione = parte finale del nome file, es. 2026-10-08T06-03-49-625Z
"""
import re, sys, os, collections, glob

D = sys.argv[1]
SESS = sys.argv[2:]
RX = re.compile(r'^(\d{4}-\d\d-\d\d)T(\d\d):(\d\d):(\d\d)\.\d+Z .*HTTP Request: (\w+) https://[^/]+/rest/v1/([^?" ]+)')
RXT = re.compile(r'^(\d{4}-\d\d-\d\d)T(\d\d):(\d\d):(\d\d)\.\d+Z ')


def pct(v, q):
    v = sorted(v)
    if not v:
        return 0
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))]


def minuto(m):
    # indice di minuto assoluto (giorno ISO + ora + minuto): basta per ordinare e contare
    y, mo, d = m.group(1).split('-')
    return (int(y) * 372 + int(mo) * 31 + int(d)) * 1440 + int(m.group(2)) * 60 + int(m.group(3))


for sid in SESS:
    print("\n################ sessione %s" % sid)
    tot_sess = 0
    tot_per_min = collections.Counter()
    for f in sorted(glob.glob(os.path.join(D, '*_%s.log' % sid))):
        name = os.path.basename(f).split('_')[0]
        if name == 'backtest-worker':
            continue
        per_min = collections.Counter()
        per_tab = collections.Counter()
        first = last = None
        n = 0
        with open(f, encoding='utf-8', errors='replace') as fh:
            for line in fh:
                mt = RXT.match(line)
                if mt:
                    mi = minuto(mt)
                    if first is None:
                        first = mi
                    last = mi
                m = RX.match(line)
                if not m:
                    continue
                n += 1
                mi = minuto(m)
                per_min[mi] += 1
                tot_per_min[mi] += 1
                per_tab[m.group(5) + ' ' + m.group(6)] += 1
        tot_sess += n
        if first is None:
            continue
        durata = max(last - first + 1, 1)
        serie = [per_min.get(i, 0) for i in range(first, last + 1)]
        print("\n### %s: richieste %d in %d min (log attivo) -> media %.1f/min | per-minuto p50=%d p95=%d p99=%d max=%d" % (
            name, n, durata, n / durata, pct(serie, .5), pct(serie, .95), pct(serie, .99), max(serie)))
        for k, v in per_tab.most_common(8):
            print("     %6d  %5.1f/min  %s" % (v, v / durata, k))
    if tot_per_min:
        a, b = min(tot_per_min), max(tot_per_min)
        serie = [tot_per_min.get(i, 0) for i in range(a, b + 1)]
        print("\n### TOTALE sessione %s: %d richieste in %d min -> media %.1f/min | per-minuto p50=%d p95=%d p99=%d max=%d" % (
            sid, tot_sess, len(serie), tot_sess / len(serie), pct(serie, .5), pct(serie, .95), pct(serie, .99), max(serie)))
