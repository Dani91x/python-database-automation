# Sonda D-15: memoria del PADRE di certifica durante un replay con --worker N.
# Avvolge `_esegui_compiti`: dopo ogni referto ricevuto misura RSS del padre,
# dimensione del referto serializzato e i suoi attributi piu' pesanti.
# Uso: python sonda_padre.py LOG.tsv <argomenti di certifica>
import os, sys, pickle, time
sys.path.insert(0, os.getcwd())


def main():
    import psutil
    from Betfair.stream.backtest import certifica as C
    log = open(sys.argv[1], "w", encoding="utf-8")
    proc = psutil.Process()
    vero = C._esegui_compiti
    t0 = time.perf_counter()

    def sonda(compiti, processi, picchi, tempi=None):
        n = 0
        for r in vero(compiti, processi, picchi, tempi):
            n += 1
            try:
                tot = len(pickle.dumps(r, protocol=pickle.HIGHEST_PROTOCOL))
            except Exception as ex:  # noqa: BLE001
                tot = -1
            pesi = []
            for k, v in vars(r).items():
                try:
                    pesi.append((len(pickle.dumps(v, protocol=pickle.HIGHEST_PROTOCOL)), k))
                except Exception:  # noqa: BLE001
                    pass
            pesi.sort(reverse=True)
            rss = proc.memory_info().rss / 1048576.0
            log.write("%d\t%.1f\t%s\t%.1f\t%.1f\t%s\n" % (
                n, time.perf_counter() - t0, compiti[n - 1][3], rss, tot / 1048576.0,
                ", ".join("%s=%.1fMB" % (k, s / 1048576.0) for s, k in pesi[:5])))
            log.flush()
            yield r
        log.write("fine\t%.1f\tRSS %.1f MB\n" % (time.perf_counter() - t0,
                                                 proc.memory_info().rss / 1048576.0))
        log.flush()

    import threading
    picco = {"mb": 0.0}
    fermo = threading.Event()

    def campiona():
        while not fermo.is_set():
            picco["mb"] = max(picco["mb"], proc.memory_info().rss / 1048576.0)
            fermo.wait(0.5)

    th = threading.Thread(target=campiona, daemon=True)
    th.start()
    C._esegui_compiti = sonda
    rc = C.main(sys.argv[2:])
    fermo.set()
    log.write("dopo main\tRSS %.1f MB\tpicco %.1f MB\n" % (proc.memory_info().rss / 1048576.0, picco["mb"]))
    log.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
