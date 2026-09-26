"""sonda_feed_atlante_793_ricalcolo.py - 7.9.3.B (e2e fase 2, 26/09): RICALCOLO INDIPENDENTE
dell'atlante v4 pubblicato dal motore a domanda. SOLA LETTURA (GET PostgREST, file locali letti).

Tre livelli, ognuno con una implementazione MIA (nessuna funzione di produzione usata per il
ricalcolo; la produzione si importa solo al livello C per il confronto a pari input):
  A. DATI GREZZI -> STATO: per le leghe scelte rileggo dal DB le partite (matches, extra da
     raw_json) e i gol (match_events) dei fixture che lo stato dichiara contati, ricostruisco gli
     stati partita-minuto con la definizione del docstring di validazione_hazard/stati.py
     (y_k = almeno un gol nei prossimi k minuti DELLO STESSO tempo; recupero 2T solo con
     status.extra valido; stagione senza recupero registrato -> solo t<=41 lontano dalla fine)
     e confronto celle (n, s2, s3), rec2 (esposizione, gol), durate, n_fixtures, gol per stagione
     con lo stato v4 del file locale (hazard_atlas_stato.json) e con la riga del DB.
  B. STATO -> BLOCCO PUBBLICATO: dagli stati v4 di TUTTE le leghe (file locale) rifaccio pesi per
     stagione (emivita 3), globale sulle leghe affidabili, shrinkage K=1500, r_rec2, pi_durata col
     metodo dei momenti, gol medi, e confronto col blocco v4 di hazard_atlas_live.json.
  C. CONSULTAZIONE: mia implementazione della consultazione (fase/cella/gol/forza/recupero 2T,
     ripiego v3 con motivo) contro Betfair.stream.scalper.atlante_v4.consulta_atlante_v4 sul file
     live, su una griglia completa (leghe v4 + una fuori v4 + una ignota, minuti 0..100, gol 0..4,
     tempo None/1/2, con e senza id squadra), e mio tempo_da_payload contro quello di produzione
     sugli stati IPS REALI raccolti da sonda_feed_atlante_793_ips.py.
Uso: python sonda_feed_atlante_793_ricalcolo.py <lega> [<lega> ...]  -> sonda_793_ricalcolo_esito.json
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

QUI = Path(__file__).resolve().parent
RADICE = QUI.parents[1]
sys.path.insert(0, str(QUI))
sys.path.insert(0, str(RADICE))
from sonda_feed_atlante_db import get  # noqa: E402

DATA = RADICE / "Betfair" / "omega" / "data"
NT, NG, DMAX = 28, 4, 30
JBIN = [0, 1, 2, 3, 4, 5, 6, 6, 7]
K = 1500.0
EMIVITA = 3.0


def _i(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ A. grezzo -> stato
def mia_pos(minute, extra):
    mi = _i(minute)
    if mi is None:
        return None
    ex = max(0, _i(extra) or 0)
    mi = max(1, mi)
    if mi <= 45:
        return (1, mi + (ex if mi == 45 else 0))
    if mi <= 90:
        return (2, mi - 45 + (ex if mi == 90 else 0))
    return (2, 45 + (mi - 90) + ex)


def mia_partita(m, righe_goal, affidabile):
    """Contributi della partita: celle[tc][gk] -> [n, y2, y3], rec2[gk] -> [esp, gol], durata."""
    gol = [r for r in righe_goal if r.get("event_type") == "Goal" and r.get("detail") != "Missed Penalty"]
    pos = [mia_pos(r.get("minute"), r.get("minute_extra")) for r in gol]
    ex = _i(m.get("extra"))
    d2 = None
    if ex is not None and 0 <= ex <= 30:
        lb2 = 0
        for r in righe_goal:               # tutte le righe Goal (anche rigore sbagliato), come la produzione legge
            p = mia_pos(r.get("minute"), r.get("minute_extra"))
            if p and p[0] == 2 and p[1] > 45:
                lb2 = max(lb2, p[1] - 45)
        d2 = max(ex, lb2)
    celle = np.zeros((NT, NG, 3))
    rec2 = np.zeros((NG, 2))
    ha_rec = False
    prima = 0
    for h in (1, 2):
        ph = sorted(p[1] for p in pos if p and p[0] == h)
        n_rec = 0 if h == 1 else (d2 or 0)
        for t in range(45 + n_rec):
            stop = t >= 45
            if not affidabile and (stop or t > 41):
                continue
            g = prima + sum(1 for x in ph if x <= t)
            gk = min(g, 3)
            y2 = int(any(t < x <= t + 2 for x in ph))
            y3 = int(any(t < x <= t + 3 for x in ph))
            if not stop:
                tc = min(t + (0 if h == 1 else 45), 89) // 5
            else:
                tc = 18 if h == 1 else 19 + JBIN[min(t - 45, 8)]
            celle[tc, gk] += (1, y2, y3)
            if stop and h == 2:
                ha_rec = True
                rec2[gk] += (1, sum(1 for x in ph if t < x <= t + 1))
        prima += len(ph)
    dur = str(min(d2 or 0, DMAX)) if ha_rec else None
    return celle, rec2, dur


def tutte(tab, q, chiave):
    out, off = [], 0
    while True:
        st, righe, _ = get(f"{tab}?{q}&order={chiave}.asc&offset={off}&limit=1000")
        assert st == 200, righe
        out += righe
        if len(righe) < 1000:
            return out
        off += 1000


def livello_a(lid, stato_loc, stato_db):
    v4 = stato_loc["v4"]
    fixtures = set(int(x) for x in stato_loc.get("fixtures") or [])
    stagioni = sorted(int(s) for s in v4["stagioni"])
    matches = tutte("matches", "select=fixture_id,season_year,status_short,goals_home,goals_away,"
                    f"extra:raw_json->fixture->status->extra&league_id=eq.{lid}"
                    f"&season_year=in.({','.join(map(str, stagioni))})", "fixture_id")
    fids = [int(m["fixture_id"]) for m in matches]
    goal = []
    for i in range(0, len(fids), 150):
        goal += tutte("match_events", "select=id,fixture_id,event_type,detail,minute,minute_extra"
                      f"&event_type=eq.Goal&fixture_id=in.({','.join(map(str, fids[i:i + 150]))})", "id")
    per_f = {}
    for g in goal:
        per_f.setdefault(int(g["fixture_id"]), []).append(g)
    # affidabilita' della stagione: quota dei gol al 45'/90' con minute_extra > 0 (>= 0.6) o < 5 gol di fine tempo
    quota = {}
    for m in matches:
        s = int(m["season_year"])
        for g in per_f.get(int(m["fixture_id"]), []):
            if _i(g.get("minute")) in (45, 90):
                q = quota.setdefault(s, [0, 0])
                q[1] += 1
                q[0] += int((_i(g.get("minute_extra")) or 0) > 0)
    aff = {s: (q[1] < 5 or q[0] / q[1] >= 0.6) for s, q in quota.items()}
    mio = {}
    contate_fuori_stato = 0
    for m in matches:
        f = int(m["fixture_id"])
        if f not in fixtures:
            if m.get("status_short") == "FT":
                contate_fuori_stato += 1
            continue
        s = int(m["season_year"])
        a = aff.get(s, True)
        c, r, d = mia_partita(m, per_f.get(f, []), a)
        b = mio.setdefault(str(s), {"n_fixtures": 0, "gol": 0, "celle": np.zeros((NT, NG, 3)),
                                    "rec2": np.zeros((NG, 2)), "durate": {}})
        b["n_fixtures"] += 1
        b["gol"] += (_i(m.get("goals_home")) or 0) + (_i(m.get("goals_away")) or 0)
        b["celle"] += c
        b["rec2"] += r
        if d is not None:
            b["durate"][d] = b["durate"].get(d, 0) + 1
    confronto = {}
    for nome, ref in (("file_locale", v4), ("db", (stato_db or {}).get("v4"))):
        if not isinstance(ref, dict):
            confronto[nome] = "assente"
            continue
        per_s = {}
        for s in sorted(set(mio) | set(ref["stagioni"]), key=int):
            a_ = mio.get(s)
            b_ = ref["stagioni"].get(s)
            if a_ is None or b_ is None:
                per_s[s] = {"solo_mio": b_ is None, "solo_produzione": a_ is None}
                continue
            cp = np.asarray(b_["celle"], dtype=float).reshape(NT, NG, 3)
            rp = np.asarray(b_["rec2"], dtype=float).reshape(NG, 2)
            dp = {str(k): int(v) for k, v in (b_.get("durate") or {}).items()}
            per_s[s] = {"n_fixtures": [a_["n_fixtures"], b_["n_fixtures"]], "gol": [a_["gol"], b_["gol"]],
                        "celle_max_diff": float(np.abs(a_["celle"] - cp).max()),
                        "celle_n_tot": [float(a_["celle"][:, :, 0].sum()), float(cp[:, :, 0].sum())],
                        "rec2_max_diff": float(np.abs(a_["rec2"] - rp).max()),
                        "durate_uguali": a_["durate"] == dp,
                        "affidabile": [aff.get(int(s), True), (ref.get("affidabile") or {}).get(s)]}
        tutto_ok = all(isinstance(v, dict) and v.get("celle_max_diff") == 0 and v.get("rec2_max_diff") == 0
                       and v.get("durate_uguali") and v["n_fixtures"][0] == v["n_fixtures"][1]
                       and v["gol"][0] == v["gol"][1] for v in per_s.values())
        confronto[nome] = {"identico": tutto_ok, "per_stagione": per_s}
    return {"lega": lid, "partite_lette": len(matches), "righe_gol": len(goal),
            "fixture_nello_stato": len(fixtures), "ft_nel_db_non_nello_stato": contate_fuori_stato,
            "scarti_v4": v4.get("scarti"), "confronto": confronto}


# ------------------------------------------------------------------ B. stato -> blocco
def livello_b(stati, pubblicato):
    leghe = sorted(stati, key=int)
    rif = max(int(s) for l in leghe for s in stati[l]["v4"]["stagioni"]) + 1
    L = len(leghe)
    n = np.zeros((L, NT, NG)); s2 = np.zeros((L, NT, NG)); s3 = np.zeros((L, NT, NG))
    E = np.zeros((L, NG)); G = np.zeros((L, NG)); dur = np.zeros((L, DMAX + 1))
    part = np.zeros(L); pw = np.zeros(L); gw = np.zeros(L)
    for i, l in enumerate(leghe):
        for s, b in stati[l]["v4"]["stagioni"].items():
            w = 0.5 ** ((rif - int(s)) / EMIVITA)
            c = np.asarray(b["celle"], float).reshape(NT, NG, 3)
            n[i] += w * c[:, :, 0]; s2[i] += w * c[:, :, 1]; s3[i] += w * c[:, :, 2]
            r = np.asarray(b["rec2"], float).reshape(NG, 2)
            E[i] += w * r[:, 0]; G[i] += w * r[:, 1]
            for d, k in (b.get("durate") or {}).items():
                dur[i, min(int(d), DMAX)] += w * k
            part[i] += b["n_fixtures"]; pw[i] += w * b["n_fixtures"]; gw[i] += w * b["gol"]
    aff = part >= 300
    if not aff.any():
        aff[:] = True
    mie = {}
    for k, S in ((2, s2), (3, s3)):
        nn, ss = n.copy(), S.copy()
        ng, sg = nn[aff].sum(0), ss[aff].sum(0)
        with np.errstate(invalid="ignore", divide="ignore"):
            pg = np.where(ng > 0, sg / np.maximum(ng, 1e-12), np.nan)
        for tcx, rip in [(18, 8)] + [(19 + b, 17) for b in range(8)]:
            vuote = ~np.isfinite(pg[tcx]) | (ng[tcx] <= 0)
            pg[tcx] = np.where(vuote, pg[rip], pg[tcx])
            nn[:, tcx] = np.where(vuote[None, :], nn[:, rip], nn[:, tcx])
            ss[:, tcx] = np.where(vuote[None, :], ss[:, rip], ss[:, tcx])
        pg = np.where(np.isfinite(pg), pg, np.nanmean(pg))
        mie[k] = ((ss + K * pg[None]) / (nn + K), pg, nn)
    Eg, Gg = E[aff].sum(0), G[aff].sum(0)
    rg = np.where(Eg > 0, Gg / np.maximum(Eg, 1e-12), Gg.sum() / max(Eg.sum(), 1e-12))
    r_l = (G + K * rg[None]) / (E + K)
    pool = dur.sum(0); pool = pool / pool.sum()
    dd = np.arange(DMAX + 1)
    med, var, nl = [], [], []
    for i in range(L):
        t = dur[i].sum()
        if t >= 30:
            mu = (dur[i] * dd).sum() / t
            med.append(mu); var.append(((dur[i] * (dd - mu) ** 2).sum() / t) / t); nl.append(t)
    kd = 50.0
    if len(med) >= 3:
        tau2 = float(np.var(med, ddof=1) - np.mean(var))
        kd = float(np.mean(np.array(var) * np.array(nl))) / tau2 if tau2 > 0 else 1e9
    pi = (dur + kd * pool[None]) / (dur.sum(1, keepdims=True) + kd)
    gm = gw / pw
    pub = pubblicato["v4"]
    diff = {"stagione_rif": [rif, pub["meta"]["stagione_rif"]], "k_durata": [kd, pub["meta"]["k_durata"]]}
    mx = {"p2": 0.0, "p3": 0.0, "n": 0.0, "r_rec2": 0.0, "pi_durata": 0.0, "gol_medi": 0.0,
          "glob_p2": 0.0, "glob_p3": 0.0, "glob_r": 0.0}
    for i, l in enumerate(leghe):
        b = pub["by_league"][l]
        mx["p2"] = max(mx["p2"], float(np.abs(mie[2][0][i] - np.asarray(b["p2"])).max()))
        mx["p3"] = max(mx["p3"], float(np.abs(mie[3][0][i] - np.asarray(b["p3"])).max()))
        mx["n"] = max(mx["n"], float(np.abs(mie[3][2][i] - np.asarray(b["n"])).max()))
        mx["r_rec2"] = max(mx["r_rec2"], float(np.abs(r_l[i] - np.asarray(b["r_rec2"])).max()))
        mx["pi_durata"] = max(mx["pi_durata"], float(np.abs(pi[i] - np.asarray(b["pi_durata"])).max()))
        mx["gol_medi"] = max(mx["gol_medi"], abs(gm[i] - b["gol_medi"]))
        if bool(part[i] >= 300) != bool(b["affidabile"]) or int(part[i]) != b["n_fixtures"]:
            diff.setdefault("affidabile_o_n_diversi", []).append(l)
    mx["glob_p2"] = float(np.abs(mie[2][1] - np.asarray(pub["global"]["p2"])).max())
    mx["glob_p3"] = float(np.abs(mie[3][1] - np.asarray(pub["global"]["p3"])).max())
    mx["glob_r"] = float(np.abs(rg - np.asarray(pub["global"]["r_rec2"])).max())
    # forza: il blocco pubblicato deve essere lo stato arrotondato a 7 decimali
    fz_diff = 0.0
    for l in leghe:
        fz = stati[l]["v4"].get("forza") or {}
        fb = pub["by_league"][l].get("forza") or {}
        for t, v in (fz.get("squadre") or {}).items():
            w = fb.get("squadre", {}).get(t)
            if w is None:
                fz_diff = float("inf"); continue
            fz_diff = max(fz_diff, abs(round(v[0], 7) - w[0]), abs(round(v[1], 7) - w[1]))
    diff["max_diff"] = mx
    diff["forza_max_diff"] = fz_diff
    # tolleranze = arrotondamento con cui il blocco e' pubblicato (atlante_v4._r: 7 decimali per
    # p/r/pi, 1 decimale per n, 5 per gol_medi): meta' dell'ultima cifra
    tol = {"p2": 5e-8, "p3": 5e-8, "n": 0.05 + 1e-9, "r_rec2": 5e-8, "pi_durata": 5e-8, "gol_medi": 5e-6,
           "glob_p2": 5e-8, "glob_p3": 5e-8, "glob_r": 5e-8}
    diff["tolleranza"] = tol
    diff["esito"] = (all(mx[k] <= tol[k] for k in mx) and fz_diff <= 5e-8 and rif == pub["meta"]["stagione_rif"]
                     and abs(kd - pub["meta"]["k_durata"]) < 1e-9 and "affidabile_o_n_diversi" not in diff)
    return diff


# ------------------------------------------------------------------ C. consultazione
def mio_tempo(raw, minute):
    m = _i(minute)
    st = ""
    if isinstance(raw, dict):
        st = "".join(ch for ch in str(raw.get("matchStatus") or raw.get("status") or "").lower() if ch.isalpha())
    if st:
        if "secondhalf" in st or "extratime" in st or "penalt" in st:
            return 2
        if "firsthalfend" in st or "halftime" in st:
            return 1
        if ("firsthalf" in st or st == "kickoff") and (m is None or m <= 60):
            return 1
    if isinstance(raw, dict):
        reg = _i(raw.get("elapsedRegularTime"))
        if reg in (45, 90) and raw.get("elapsedAddedTime") is not None and (m is None or m <= reg + 30):
            return 1 if reg == 45 else 2
    if m is None:
        return None
    return 1 if m < 45 else (2 if m >= 90 else None)


def mia_consulta(atlas, minute, goals, lid, tempo=None, home_id=None, away_id=None, k_req=3):
    v4 = atlas.get("v4")
    if not isinstance(v4, dict):
        return {"versione": "v3", "motivo": "blocco v4 assente"}
    meta = v4["meta"]
    solido = bool(meta.get("globale_solido", True))
    l = str(lid) if lid is not None else None
    lg = v4["by_league"].get(l) if l else None
    if atlas.get("global"):
        if isinstance(lg, dict):
            if not (lg.get("affidabile") or solido):
                return {"versione": "v3", "motivo": "lega poca e globale non solido"}
        elif l is not None and l in (atlas.get("by_league") or {}):
            return {"versione": "v3", "motivo": f"lega {l} non ancora nel v4"}
        elif not solido:
            return {"versione": "v3", "motivo": "globale v4 non solido"}
    m = max(0, int(minute))
    if tempo == 1 and m >= 45:
        fase, tc, j = "recupero_1T", 8, m - 45
    elif m >= 90:
        fase, j = "recupero_2T", m - 90
        tc = 19 + JBIN[min(j, 8)]
    else:
        fase, tc, j = "regolare", m // 5, 0
    gk = min(max(0, int(goals)), 3)
    src = lg if isinstance(lg, dict) else v4["global"]
    ref = (lg or {}).get("gol_medi") or v4["global"].get("gol_medi")
    mult, usata = 1.0, False
    fz = (lg or {}).get("forza")
    if home_id is not None and away_id is not None and isinstance(fz, dict):
        sq = fz["squadre"]
        ah, dh = sq.get(str(home_id), [0.0, 0.0])[:2]
        aa, da = sq.get(str(away_id), [0.0, 0.0])[:2]
        lt = fz["mu"][0] * math.exp(ah + da) + fz["mu"][1] * math.exp(aa + dh)
        if ref and lt > 0:
            mult, usata = min(5.0, max(0.2, lt / ref)), True
    out = {"versione": "v4", "fase": fase, "recupero_atteso_min": None}
    for k in (2, 3):
        if fase == "recupero_2T" and meta.get("recupero_2T_noto"):
            r = src["r_rec2"][gk]
            pi = np.asarray(src.get("pi_durata") or v4["global"]["pi_durata"])
            d = np.arange(pi.size)
            vivo = d > j
            massa = (pi * vivo).sum()
            p = 1 - (pi * vivo * np.exp(-r * np.minimum(k, np.maximum(d - j, 0)))).sum() / massa
            out["recupero_atteso_min"] = round(float((pi * vivo * (d - j)).sum() / massa), 2)
        else:
            p = src[f"p{k}"][tc][gk]
        if usata:
            b = float(meta["beta"][str(k)])
            p = 1 - (1 - p) ** (mult ** b)
        out[f"p_{k}min"] = float(p)
    out["forza_usata"] = usata
    return out


def livello_c(atlas, ips_path):
    from Betfair.stream.scalper.atlante_v4 import consulta_atlante_v4, tempo_da_payload
    v4 = atlas["v4"]
    leghe = list(v4["by_league"])
    fuori = next((l for l in atlas.get("by_league", {}) if l not in v4["by_league"]), None)
    casi = diversi = 0
    esempi = []
    for l in leghe + [fuori, "999999", None]:
        fz = (v4["by_league"].get(str(l)) or {}).get("forza") or {}
        sq = list((fz.get("squadre") or {}).keys())
        coppie = [(None, None)] + ([(int(sq[0]), int(sq[1])), (int(sq[-1]), 123456789)] if len(sq) > 1 else [])
        for minute in range(0, 101):
            for goals in range(0, 5):
                for tempo in (None, 1, 2):
                    for (h, a) in coppie:
                        casi += 1
                        mio = mia_consulta(atlas, minute, goals, l, tempo, h, a)
                        pr = consulta_atlante_v4(atlas, minute, goals, l, tempo=tempo, home_id=h, away_id=a)
                        ok = mio["versione"] == pr["versione"]
                        if ok and mio["versione"] == "v4":
                            ok = (mio["fase"] == pr["fase"] and abs(mio["p_2min"] - pr["p_2min"]) < 1e-12
                                  and abs(mio["p_3min"] - pr["p_3min"]) < 1e-12
                                  and mio["recupero_atteso_min"] == pr["recupero_atteso_min"]
                                  and mio["forza_usata"] == bool(pr["forza"]["usata"]))
                        if not ok:
                            diversi += 1
                            if len(esempi) < 8:
                                esempi.append({"lega": l, "min": minute, "gol": goals, "tempo": tempo, "ids": [h, a],
                                               "mio": mio, "prod": {k: pr.get(k) for k in
                                                                    ("versione", "fase", "p_2min", "p_3min",
                                                                     "recupero_atteso_min", "ripiego_v3")}})
    # stati IPS reali
    reali = {"righe": 0, "tempo_diversi": 0, "per_fase": {}, "esempi_diversi": [], "campioni": []}
    if ips_path.exists():
        for line in ips_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("minute") is None:
                continue
            reali["righe"] += 1
            payload = {"score_raw": r.get("score_raw"), "minute": r.get("minute")}
            tp, tm = tempo_da_payload(payload), mio_tempo(r.get("score_raw"), r.get("minute"))
            st = (r.get("ips") or {}).get("matchStatus")
            fase = mia_consulta(atlas, r["minute"], (r.get("sh") or 0) + (r.get("sa") or 0), None, tm).get("fase")
            key = f"{st}|tempo={tm}|fase={fase}"
            reali["per_fase"][key] = reali["per_fase"].get(key, 0) + 1
            if tp != tm:
                reali["tempo_diversi"] += 1
                if len(reali["esempi_diversi"]) < 5:
                    reali["esempi_diversi"].append([r["event_id"], r["minute"], r.get("ips"), tp, tm])
            if (r["minute"] >= 44 or st in ("FirstHalfEnd",)) and len(reali["campioni"]) < 400:
                reali["campioni"].append([r["event_id"], r["updated_at"], r["minute"], r.get("ips"), tm, fase])
    return {"griglia_casi": casi, "griglia_diversi": diversi, "esempi": esempi, "ips_reali": reali}


if __name__ == "__main__":
    import time
    for _ in range(30):     # coppia coerente: il motore scrive i due file in momenti diversi del ciclo
        stato_file = json.loads((DATA / "hazard_atlas_stato.json").read_text(encoding="utf-8"))
        atlas = json.loads((DATA / "hazard_atlas_live.json").read_text(encoding="utf-8"))
        # le leghe con v4 ma SENZA stagioni contate (tutte scartate per copertura eventi) non vanno
        # nel blocco pubblicato: si escludono dal confronto (assembla_blocco_v4 le salta)
        if {l for l, v in stato_file["leghe"].items() if isinstance(v.get("v4"), dict) and v["v4"].get("stagioni")}                 == set(atlas["v4"]["by_league"]):
            break
        time.sleep(20)
    esito = {"atlas_generated_at": atlas["meta"]["generated_at"], "A": [], "B": None, "C": None}
    for lid in sys.argv[1:]:
        st, righe, _ = get(f"hazard_atlas_leghe?select=league_id,stato,fixtures&league_id=eq.{lid}&limit=1")
        sdb = righe[0]["stato"] if st == 200 and righe else None
        esito["A"].append(livello_a(lid, stato_file["leghe"][lid], sdb))
        print("A", lid, json.dumps({k: (v["identico"] if isinstance(v, dict) else v)
                                    for k, v in esito["A"][-1]["confronto"].items()}))
    esito["B"] = livello_b({l: v for l, v in stato_file["leghe"].items()
                            if isinstance(v.get("v4"), dict) and v["v4"].get("stagioni")}, atlas)
    print("B", json.dumps(esito["B"], default=str))
    esito["C"] = livello_c(atlas, QUI / "sonda_793_ips.jsonl")
    print("C", esito["C"]["griglia_casi"], esito["C"]["griglia_diversi"], json.dumps(esito["C"]["ips_reali"]["per_fase"]))
    (QUI / "sonda_793_ricalcolo_esito.json").write_text(json.dumps(esito, ensure_ascii=False, indent=1, default=str),
                                                         encoding="utf-8")
