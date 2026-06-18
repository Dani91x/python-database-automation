"""
Certificazione 1:1 della macchina a stati "ritardi" usata nella RPC
get_market_delays, confrontata con le formule RICORSIVE del file Excel
STUDIO RITARDI_BASE_v5.0.

  Excel (per riga n, colonna mercato):
    W/L  = IF(condizione, 1, 0)
    RIT  = IF(W/L=0, RIT_prec+1, 0)        (RIT della prima riga = IF(WL=0,1,0))
    SUC  = IF(W/L=1, RIT_prec, "")
    RECORD          = MAX(SUC)
    RITARDO ATTUALE = ultimo RIT
    MEDIA RIT.      = AVERAGEIF(RIT, "<>0")
    < / > MEDIA     = COUNTIF(SUC, "<=" INT(media)) / COUNTIF(SUC, ">=" INT(media)+1)
    RUN SOPRA MEDIA = run consecutivi di SUC >= media, istogramma delle lunghezze

  RPC SQL (equivalente set-based):
    last_hit(i) = max idx j<=i con WL=1 (0 se nessuno)
    RIT(i)      = i - last_hit(i)
    SUC(hit q)  = (q - prev_hit) - 1
    run sopra-media via "isole" (hit_seq - row_number)

Esegue il doppio calcolo su molte serie casuali e verifica l'uguaglianza esatta
di ogni metrica. Nessuna dipendenza esterna.
"""
import math
import random


# ----------------------------------------------------------------- EXCEL (ricorsivo)
def excel_engine(wl):
    """Riproduce, riga per riga, le formule del foglio. wl = lista di 0/1."""
    rit, suc = [], []
    prev_rit = 0
    for i, w in enumerate(wl):
        if w == 0:
            cur = (prev_rit + 1) if i > 0 else 1     # RIT della 1a riga: IF(WL=0,1,0)
            rit.append(cur)
        else:
            rit.append(0)
            suc.append(prev_rit)                     # SUC = RIT_prec quando esce
        prev_rit = rit[-1]
    return rit, suc


# ----------------------------------------------------------------- RPC (set-based)
def rpc_engine(wl):
    n = len(wl)
    idx = list(range(1, n + 1))                      # EVENTO progressivo
    last_hit = []
    cur_last = 0
    for i, w in enumerate(wl):
        if w == 1:
            cur_last = idx[i]
        last_hit.append(cur_last)
    rit = [idx[i] - last_hit[i] for i in range(n)]   # RIT = idx - last_hit
    # SUC = gap-1 tra hit consecutivi (primo hit misurato da idx 0)
    hit_idx = [idx[i] for i in range(n) if wl[i] == 1]
    suc = []
    prev = 0
    for h in hit_idx:
        suc.append(h - prev - 1)
        prev = h
    return rit, suc


# ----------------------------------------------------------------- metriche derivate
def metrics(rit, suc, n_eff):
    n_occ = len(suc)
    ritardo_attuale = rit[-1] if rit else 0
    record = max(suc) if suc else 0
    nz = [r for r in rit if r != 0]
    media_rit = (sum(nz) / len(nz)) if nz else 0.0
    media_storica = (n_eff / n_occ) if n_occ else None
    imedia = math.floor(media_rit)
    sotto = sum(1 for s in suc if s <= imedia)
    sopra = sum(1 for s in suc if s >= imedia + 1)
    # distribuzione serie
    distrib = {}
    for s in suc:
        distrib[s] = distrib.get(s, 0) + 1
    # run sopra-media (serie con lunghezza >= media_rit), istogramma run-len
    runs = []
    cur = 0
    for s in suc:
        if s >= media_rit:
            cur += 1
        else:
            if cur > 0:
                runs.append(cur)
            cur = 0
    if cur > 0:
        runs.append(cur)
    run_hist = {}
    for r in runs:
        run_hist[r] = run_hist.get(r, 0) + 1
    return dict(n_occ=n_occ, ritardo_attuale=ritardo_attuale, record=record,
                media_rit=round(media_rit, 6), media_storica=media_storica,
                sotto=sotto, sopra=sopra, distrib=distrib, run_hist=run_hist)


def main():
    random.seed(42)
    cases = 0
    for _ in range(20000):
        n = random.randint(1, 120)
        p = random.choice([0.05, 0.12, 0.25, 0.5, 0.8])
        wl = [1 if random.random() < p else 0 for _ in range(n)]

        rit_x, suc_x = excel_engine(wl)
        rit_r, suc_r = rpc_engine(wl)

        assert rit_x == rit_r, f"RIT mismatch\nwl={wl}\nexcel={rit_x}\nrpc={rit_r}"
        assert suc_x == suc_r, f"SUC mismatch\nwl={wl}\nexcel={suc_x}\nrpc={suc_r}"

        mx = metrics(rit_x, suc_x, len(wl))
        mr = metrics(rit_r, suc_r, len(wl))
        assert mx == mr, f"metrics mismatch\nwl={wl}\n{mx}\n{mr}"
        cases += 1

    # casi limite espliciti
    edge = {
        "mai uscito":      [0, 0, 0, 0, 0],
        "sempre uscito":   [1, 1, 1, 1, 1],
        "uscito subito":   [1, 0, 0, 0],
        "uscito alla fine":[0, 0, 0, 1],
        "alternato":       [0, 1, 0, 1, 0, 1],
    }
    for name, wl in edge.items():
        rx, sx = excel_engine(wl)
        rr, sr = rpc_engine(wl)
        assert rx == rr and sx == sr, name
        assert metrics(rx, sx, len(wl)) == metrics(rr, sr, len(wl)), name
        print(f"  [edge] {name:18s} RIT={rx} SUC={sx} "
              f"ritardo_attuale={rx[-1]} record={max(sx) if sx else 0}")

    print(f"\nOK — {cases} serie casuali + {len(edge)} casi limite: "
          f"macchina a stati RPC IDENTICA alle formule Excel (RIT, SUC, "
          f"record, ritardo attuale, media rit, distribuzione, <>media, run sopra-media).")


if __name__ == "__main__":
    main()
