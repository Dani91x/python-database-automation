"""M6 - prova di laboratorio §9.3: costo di scrittura e durabilita' di 6 modi di tenere lo stato vivo.
Prototipo usa-e-getta: scrive SOLO in <cartella_tmp> (da passare, es. strumenti/misure/tmp), che il
chiamante cancella alla fine. Nessun codice di produzione, nessuna rete.

Modi:
  mem          solo memoria (lista in RAM)
  log_buf      log append-only, write() senza flush (buffer di Python)
  log_flush    log append-only, write()+flush() (dati al sistema operativo)
  log_fsync    log append-only, write()+flush()+os.fsync() a ogni record (dati sul disco)
  sqlite_normal  SQLite WAL, synchronous=NORMAL, un INSERT + COMMIT per record
  sqlite_full    SQLite WAL, synchronous=FULL,   un INSERT + COMMIT per record
  sqlite_normal_lotti / sqlite_full_lotti  come sopra ma 100 INSERT per COMMIT
Record: JSON di ~300 byte (come un cambio di ladder / una riga di ordine).
Misure per modo e ripetizione: latenza per record (o per commit nei lotti) p50/p95/p99/max in
microsecondi, throughput record/s, CPU del processo / tempo di muro, byte scritti su disco.
Prova di crash: un processo figlio scrive N record, dichiara su stdout «ack k» DOPO ogni scrittura
completata, poi muore con os._exit(1) (nessuna chiusura pulita, come un kill -9). Si rilegge cio'
che resta e si confronta con l'ultimo ack. (Un crash del PROCESSO non e' uno spegnimento del PC: la
cache del sistema operativo sopravvive; per lo spegnimento si cita la documentazione SQLite.)
Uso: python -I m06_lab_persistenza.py <cartella_tmp> [N=3000] [ripetizioni=3]
"""
import os, sys, json, time, sqlite3, subprocess, statistics

TMP = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
REP = int(sys.argv[3]) if len(sys.argv) > 3 else 3
os.makedirs(TMP, exist_ok=True)

PAD = "x" * 150


def rec(i):
    return json.dumps({"i": i, "m": "1.2345678", "t": 1788277576718 + i, "s": 5, "b": [[1.95, 28.9], [1.91, 37.4]],
                       "l": [[1.99, 169.2], [2.0, 3.4]], "p": PAD}, separators=(",", ":"))


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))]


def db_open(path, sync):
    for suf in ("", "-wal", "-shm"):
        try:
            os.remove(path + suf)
        except OSError:
            pass
    c = sqlite3.connect(path, isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=%s" % sync)
    c.execute("CREATE TABLE t(i INTEGER PRIMARY KEY, j TEXT)")
    return c


def esegui(modo, n):
    """Ritorna (lista latenze s, secondi muro, secondi CPU, byte su disco)."""
    lat = []
    path = os.path.join(TMP, modo + ".dat")
    c0, w0 = time.process_time(), time.perf_counter()
    if modo == "mem":
        buf = []
        for i in range(n):
            t = time.perf_counter(); buf.append(rec(i)); lat.append(time.perf_counter() - t)
        sz = 0
    elif modo.startswith("log_"):
        f = open(path, "w", encoding="ascii", newline="\n")
        for i in range(n):
            r = rec(i) + "\n"
            t = time.perf_counter()
            f.write(r)
            if modo in ("log_flush", "log_fsync"):
                f.flush()
            if modo == "log_fsync":
                os.fsync(f.fileno())
            lat.append(time.perf_counter() - t)
        f.close(); sz = os.path.getsize(path)
    else:
        sync = "NORMAL" if "normal" in modo else "FULL"
        lotti = modo.endswith("lotti")
        c = db_open(path, sync)
        if not lotti:
            for i in range(n):
                r = rec(i)
                t = time.perf_counter()
                c.execute("BEGIN"); c.execute("INSERT INTO t VALUES(?,?)", (i, r)); c.execute("COMMIT")
                lat.append(time.perf_counter() - t)
        else:
            L = 100
            for k in range(0, n, L):
                righe = [(i, rec(i)) for i in range(k, min(n, k + L))]
                t = time.perf_counter()
                c.execute("BEGIN"); c.executemany("INSERT INTO t VALUES(?,?)", righe); c.execute("COMMIT")
                lat.append(time.perf_counter() - t)
        c.close()
        sz = sum(os.path.getsize(path + s) for s in ("", "-wal") if os.path.exists(path + s))
    return lat, time.perf_counter() - w0, time.process_time() - c0, sz


MODI = ["mem", "log_buf", "log_flush", "log_fsync", "sqlite_normal", "sqlite_full", "sqlite_normal_lotti", "sqlite_full_lotti"]
print("# M6 lab persistenza: N=%d record, %d ripetizioni, cartella %s" % (N, REP, os.path.abspath(TMP)))
print("# (nei modi *_lotti la latenza e' per COMMIT da 100 record; throughput sempre in record/s)")
for modo in MODI:
    for r in range(REP):
        n = N
        lat, w, c, sz = esegui(modo, n)
        print("%-20s rep%d  lat us p50=%8.1f p95=%8.1f p99=%9.1f max=%10.1f | %9.0f rec/s | CPU/muro %5.1f%% | disco %.2f MB" % (
            modo, r + 1, pct(lat, .5) * 1e6, pct(lat, .95) * 1e6, pct(lat, .99) * 1e6, max(lat) * 1e6,
            n / w, 100 * c / w, sz / 1048576))
        sys.stdout.flush()

# ---- prova di crash ----
FIGLIO = r'''
import os, sys, json, sqlite3
modo, path, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
def rec(i): return json.dumps({"i": i, "p": "x"*150})
if modo.startswith("sqlite"):
    c = sqlite3.connect(path, isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA synchronous=" + ("NORMAL" if "normal" in modo else "FULL"))
    c.execute("CREATE TABLE t(i INTEGER PRIMARY KEY, j TEXT)")
elif modo != "mem":
    f = open(path, "w", encoding="ascii", newline="\n")
buf = []
for i in range(n):
    r = rec(i)
    if modo == "mem": buf.append(r)
    elif modo.startswith("sqlite"): c.execute("BEGIN"); c.execute("INSERT INTO t VALUES(?,?)", (i, r)); c.execute("COMMIT")
    else:
        f.write(r + "\n")
        if modo in ("log_flush", "log_fsync"): f.flush()
        if modo == "log_fsync": os.fsync(f.fileno())
    sys.stdout.write("ack %d\n" % i); sys.stdout.flush()
os._exit(1)
'''
print("\n# PROVA DI CRASH DEL PROCESSO (os._exit senza chiusura; n=500 record per modo)")
fig = os.path.join(TMP, "figlio.py")
open(fig, "w").write(FIGLIO)
for modo in ["mem", "log_buf", "log_flush", "log_fsync", "sqlite_normal", "sqlite_full"]:
    path = os.path.join(TMP, "crash_" + modo + ".dat")
    for suf in ("", "-wal", "-shm"):
        try:
            os.remove(path + suf)
        except OSError:
            pass
    out = subprocess.run([sys.executable, "-I", fig, modo, path, "500"], capture_output=True, text=True, timeout=120).stdout
    ack = len([l for l in out.splitlines() if l.startswith("ack ")])
    if modo == "mem":
        rec_ = 0
    elif modo.startswith("sqlite"):
        c = sqlite3.connect(path); rec_ = c.execute("SELECT COUNT(*) FROM t").fetchone()[0]; c.close()
    else:
        rec_ = sum(1 for l in open(path, encoding="ascii", errors="replace") if l.endswith("\n") and l.strip().endswith("}"))
    print("%-14s ack=%d recuperati=%d persi=%d" % (modo, ack, rec_, ack - rec_))
