"""Sonda: perche' il modello di Omega scarta i risultati, per tempo (1T = gamba
HT, 2T = gamba FT). Avvolge omega_model.select_by_model SENZA cambiarne l'esito
(chiama l'originale e ne restituisce il risultato) e ricalcola, runner per
runner, il primo filtro che lo esclude, con gli stessi conti della funzione.
uso (dalla radice dell'albero): python3 sonda_modello.py <evento> <scenario>"""
import collections, math, os, sys
sys.path.insert(0, os.getcwd())
from Betfair.omega import omega_model as M
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_service as S

orig = M.select_by_model
per_tempo = collections.defaultdict(collections.Counter)
vicini = {}          # tempo -> miglior (p_sel/p_implied) visto: il piu' vicino a passare
chiamate = collections.Counter()
scelti = []


def sonda(runners, probs, *, state, price_min, price_max, min_liquidity, p_max, size_needed=0.0,
          min_goal_distance=2, calibrator=None, family=M.CALIBRATION_FAMILY_FT, p_data=None,
          tail_factor=1.0, commission=0.0, probs_alt=None, k_se=0.0, liability_cap=0.0, **kw):
    res = orig(runners, probs, state=state, price_min=price_min, price_max=price_max,
               min_liquidity=min_liquidity, p_max=p_max, size_needed=size_needed,
               min_goal_distance=min_goal_distance, calibrator=calibrator, family=family,
               p_data=p_data, tail_factor=tail_factor, commission=commission,
               probs_alt=probs_alt, k_se=k_se, liability_cap=liability_cap, **kw)
    tempo = "1T" if family == M.CALIBRATION_FAMILY_HT else "2T"
    chiamate[tempo] += 1
    c = per_tempo[tempo]
    for r in runners:
        price = getattr(r, "lay_price", None)
        nome = getattr(r, "name", "")
        if price is None or not math.isfinite(float(price)) or price < price_min or price > price_max:
            c["prezzo fuori banda [%s,%s]" % (price_min, price_max)] += 1
            continue
        need = max(float(min_liquidity), E.apply_liability_cap(float(size_needed), float(price), liability_cap))
        lay_size = float(getattr(r, "lay_size", 0.0) or 0.0)
        if not math.isfinite(lay_size) or lay_size < need:
            c["liquidita' lay < %.2f" % need] += 1
            continue
        parsed = E.parse_scoreline(nome or "")
        if parsed is None:
            c["aggregato"] += 1
            continue
        h, a = parsed
        if h < state.score_home or a < state.score_away:
            c["irraggiungibile"] += 1
            continue
        if (h - state.score_home) + (a - state.score_away) < min_goal_distance:
            c["troppo vicino (distanza < %d)" % min_goal_distance] += 1
            continue
        p_raw = probs.get((h, a))
        if p_raw is None:
            c["fuori griglia"] += 1
            continue
        if probs_alt:
            alts = [p_raw] + [d.get((h, a)) for d in probs_alt if isinstance(d, dict)]
            alts = [v for v in alts if v is not None]
            centre, prudent = M.uncertainty_p(alts, k_se=k_se) if k_se > 0 else (p_raw, p_raw)
            p_model = max(M.model_p(centre if k_se > 0 else p_raw, family, state.minute, calibrator,
                                    tail_factor), prudent)
        else:
            p_model = M.model_p(p_raw, family, state.minute, calibrator, tail_factor)
        cc = max(0.0, min(0.5, float(commission)))
        p_impl = (1.0 - cc) / (float(price) - cc)
        p_emp = None
        if p_data is not None:
            try:
                got = p_data(h, a)
                p_emp = float(got) if got is not None and math.isfinite(float(got)) else None
            except Exception:  # noqa: BLE001
                p_emp = None
        p_sel = p_model if p_emp is None else max(p_model, p_emp)
        rapporto = p_sel / p_impl if p_impl > 0 else float("inf")
        prec = vicini.get(tempo)
        if prec is None or rapporto < prec[0]:
            vicini[tempo] = (round(rapporto, 3), nome, float(price), round(p_sel, 5), round(p_impl, 5),
                             state.minute, "%d-%d" % (state.score_home, state.score_away))
        if p_sel > p_max:
            c["P modello > p_max (%.3f)" % p_max] += 1
            continue
        if p_sel >= p_impl:
            c["P modello >= P implicita del mercato"] += 1
            continue
        c["CANDIDATO"] += 1
    if res is not None:
        scelti.append((tempo, state.minute, res.name, res.price))
    return res


M.select_by_model = sonda
from Betfair.stream.backtest import certifica as C  # noqa: E402

C.main(["omega", sys.argv[1], "--data-dir", "/home/user/python-database-automation/_live_raw",
        "--scenari", sys.argv[2], "--worker", "1"])
print("\n===== SONDA MODELLO =====")
for tempo in ("1T", "2T"):
    print(tempo, "valutazioni del modello:", chiamate[tempo])
    for k, v in per_tempo[tempo].most_common():
        print("   ", tempo, k, "x", v)
    print("   ", tempo, "piu' vicino a passare (P_sel/P_impl, nome, quota, P_sel, P_impl, minuto, punteggio):",
          vicini.get(tempo))
print("SCELTI:", scelti)
