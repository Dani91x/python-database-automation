"""Verifica in SOLA LETTURA dei payload TacticAI con P(0-0) negativa (25/09/2026).

Nessun accesso al DB: legge un file JSON estratto dal coordinatore con

    select fixture_id, tactical_engine_json from fixture_predictions
    where (tactical_engine_json->'markets'->>'under_0_5')::numeric < 0;

Formati accettati: lista di righe {fixture_id, tactical_engine_json} (il json come
oggetto o come stringa), lista di payload nudi (come li scrive
serving._build_payload), oppure un solo oggetto.

Per ogni payload ricalcola la griglia Dixon-Coles dai valori scritti (lambda_home,
lambda_away arrotondati a 3 decimali, training.rho a 4) e stampa:
  - under_0_5 SCRITTO nel payload e RICOSTRUITO con la formula di prima (controllo
    della diagnosi: se coincidono a meno dell'arrotondamento, il negativo nasce da
    tau(0,0) = 1 - lh*la*rho < 0);
  - lh*la, 1/(lh*la) e il dominio di rho della coppia (Dixon & Coles 1997);
  - under_0_5 DOPO con rho proiettato nel dominio della coppia (margine TAU_MIN) e
    la somma della griglia.
NB: il "dopo" e' una stima LOCALE. Il valore definitivo lo produce il prossimo run del
serving col fit vincolato su tutte le coppie della lega, che puo' dare un rho piu'
basso e forze leggermente diverse.

Con --rifit (SOLO SELECT sul DB, nessuna scrittura) rifa' il fit della lega come il
serving (stesso storico leakage-free, stessa emivita, stesso RIDGE) col modello
corretto e stampa, per la partita del payload: rho del primo stadio (deve coincidere
col training.rho scritto, se lo storico non e' cambiato), rho vincolato, under_0_5
definitivo e lo scarto massimo su tutti i mercati rispetto al payload scritto.

Uso:  python -m tactical_engine.tools.verifica_payload_tacticai payload.json [--rifit]
Esce con 0 se tutte le griglie ricalcolate sono valide, 1 altrimenti.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tactical_engine.dixon_coles import markets_from_matrix, rho_bounds, score_matrix  # noqa: E402
from tactical_engine.model import TAU_MIN, DixonColesModel, parse_iso  # noqa: E402

MAX_GOALS_FT = 10  # = serving: DixonColesModel(max_goals=10) per il tempo pieno


def _payloads(obj: Any) -> List[Dict[str, Any]]:
    righe = obj if isinstance(obj, list) else [obj]
    out: List[Dict[str, Any]] = []
    for r in righe:
        if not isinstance(r, dict):
            raise ValueError(f"riga non valida: {type(r).__name__}")
        p = r.get("tactical_engine_json", r)
        if isinstance(p, str):
            p = json.loads(p)
        if not isinstance(p, dict) or "markets" not in p:
            raise ValueError(f"payload senza 'markets' (fixture_id={r.get('fixture_id')})")
        if p.get("fixture_id") is None and r.get("fixture_id") is not None:
            p = dict(p, fixture_id=r["fixture_id"])
        out.append(p)
    return out


def _scarto_max(prima: Dict[str, Any], dopo: Dict[str, Any]) -> tuple:
    """(nome, prima, dopo, |scarto|) del mercato che si sposta di piu'."""
    k = max((k for k in prima if k in dopo),
            key=lambda k: abs(float(dopo[k]) - float(prima[k])))
    return k, float(prima[k]), float(dopo[k]), abs(float(dopo[k]) - float(prima[k]))


def verifica_payload(p: Dict[str, Any]) -> Dict[str, Any]:
    lh = float(p["lambda_home"])
    la = float(p["lambda_away"])
    rho = float(p["training"]["rho"])
    scritto = p["markets"].get("under_0_5")
    ht = p.get("markets_ht") or {}

    g_prima = score_matrix(lh, la, rho, MAX_GOALS_FT)
    lo, hi = rho_bounds(lh, la, TAU_MIN)
    rho_dopo = min(max(rho, lo), hi)
    g_dopo = score_matrix(lh, la, rho_dopo, MAX_GOALS_FT)
    m_dopo = markets_from_matrix(g_dopo)
    return {
        "fixture_id": p.get("fixture_id"),
        "league_id": p.get("league_id"),
        "lambda_home": lh, "lambda_away": la, "rho": rho,
        "lh_la": lh * la, "inv_lh_la": 1.0 / (lh * la),
        "rho_lo": lo, "rho_hi": hi, "rho_nel_dominio": lo <= rho <= hi,
        "under_0_5_scritto": None if scritto is None else float(scritto),
        "under_0_5_ricostruito": markets_from_matrix(g_prima)["under_0_5"],
        "under_0_5_ht_scritto": ht.get("under_0_5"),
        "rho_dopo": rho_dopo,
        "under_0_5_dopo": m_dopo["under_0_5"],
        "over_0_5_dopo": m_dopo["over_0_5"],
        "mercato_scarto_max": _scarto_max(p["markets"], {k: round(v, 4) for k, v in m_dopo.items()}),
        "somma_griglia_dopo": float(g_dopo.sum()),
        "cella_min_dopo": float(g_dopo.min()),
        "griglia_valida_dopo": bool(float(g_dopo.min()) >= 0.0
                                    and abs(float(g_dopo.sum()) - 1.0) <= 1e-9
                                    and 0.0 <= m_dopo["under_0_5"] <= 1.0),
    }


def verifica(obj: Any) -> List[Dict[str, Any]]:
    return [verifica_payload(p) for p in _payloads(obj)]


def rifit(obj: Any, sb: Any) -> List[Dict[str, Any]]:
    """Rifit leakage-free della lega di ogni payload, SOLO letture (select)."""
    from datetime import datetime, timezone
    from tactical_engine import serving

    fits: Dict[tuple, tuple] = {}
    out: List[Dict[str, Any]] = []
    for p in _payloads(obj):
        fid = p["fixture_id"]
        righe = (sb.table("fixture_predictions")
                 .select("fixture_id,league_id,fixture_date,home_team_id,away_team_id,"
                         "home_team_name,away_team_name")
                 .eq("fixture_id", fid).execute().data or [])
        if not righe:
            out.append({"fixture_id": fid, "errore": "riga fixture_predictions assente"})
            continue
        r = righe[0]
        d = parse_iso(r["fixture_date"])
        start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)  # = run_for_date
        neutral = bool(p.get("neutral"))
        hl = serving.HALF_LIFE_NEUTRAL if neutral else serving.HALF_LIFE_CLUB
        key = (r["league_id"], start, neutral)
        if key not in fits:
            ft_m, ft_d, _, _ = serving._load_prior(sb, r["league_id"], start, half_life_days=hl)
            m = DixonColesModel(max_goals=10, half_life_days=hl, ridge=serving.RIDGE)
            f = m.fit(ft_m, dates=ft_d, ref_date=start, fit_home_adv=not neutral)
            fits[key] = (m, f)
        m, f = fits[key]
        pr = m.predict(r["home_team_id"], r["away_team_id"], neutral=neutral)
        nuovi = serving._round_markets(pr["markets"])
        sm = _scarto_max(p["markets"], nuovi)
        scarto = sm[3]
        g = pr["grid"]
        out.append({
            "fixture_id": fid, "league_id": r["league_id"],
            "n_matches_scritto": p["training"].get("n_matches"), "n_matches_rifit": f.n_matches,
            "rho_scritto": float(p["training"]["rho"]), "rho_stadio1": f.rho_unconstrained,
            "rho_vincolato": f.rho, "vincolo_attivo": f.rho_constraint_active,
            "lambda_home": pr["lambda_home"], "lambda_away": pr["lambda_away"],
            "under_0_5_scritto": float(p["markets"]["under_0_5"]),
            "under_0_5_rifit": nuovi["under_0_5"], "scarto_max_mercati": scarto,
            "mercato_scarto_max": sm, "converged": f.converged,
            # la riga di oggi puo' avere casa/trasferta diverse da quelle con cui fu
            # scritto il payload (allora il serving leggeva le partite da `matches`)
            "squadre_payload": (p.get("home_name"), p.get("away_name")),
            "squadre_riga": (r.get("home_team_name"), r.get("away_team_name")),
            "squadre_coerenti": (p.get("home_name"), p.get("away_name"))
            == (r.get("home_team_name"), r.get("away_team_name")),
            "lambda_home_scritto": float(p["lambda_home"]), "lambda_away_scritto": float(p["lambda_away"]),
            "x12_scritto": (p["markets"].get("home"), p["markets"].get("draw"), p["markets"].get("away")),
            "x12_rifit": (nuovi["home"], nuovi["draw"], nuovi["away"]),
            "somma_griglia": float(g.sum()),
            "griglia_valida": bool(float(g.min()) >= 0.0 and abs(float(g.sum()) - 1.0) <= 1e-9),
        })
    return out


def _stampa_rifit(esiti: List[Dict[str, Any]]) -> int:
    print("\nRIFIT (modello corretto, storico letto dal DB in sola lettura)")
    print("fixture_id  lega  n_scr/n_rifit rho_scr  rho_st1  rho_vinc att  lh     la     "
          "u05_scr  u05_rifit scarto_max somma")
    valide = 0
    for e in esiti:
        if "errore" in e:
            print(f"{e['fixture_id']!s:>10}  ERRORE: {e['errore']}")
            continue
        valide += e["griglia_valida"]
        print(f"{e['fixture_id']!s:>10} {e['league_id']!s:>5}  {e['n_matches_scritto']!s:>5}/"
              f"{e['n_matches_rifit']:<5}   {e['rho_scritto']:+.4f} {e['rho_stadio1']:+.4f} "
              f"{e['rho_vincolato']:+.4f} {'SI' if e['vincolo_attivo'] else 'no'}  "
              f"{e['lambda_home']:5.3f}  {e['lambda_away']:5.3f}  {e['under_0_5_scritto']:+.4f}  "
              f"{e['under_0_5_rifit']:+.4f}   {e['scarto_max_mercati']:.4f}     {e['somma_griglia']:.12f}")
        k, a, b, _ = e["mercato_scarto_max"]
        print(f"{'':>12}mercato piu' spostato: {k} {a:.4f} -> {b:.4f} | lambda scritte "
              f"{e['lambda_home_scritto']:.3f}/{e['lambda_away_scritto']:.3f} -> rifit "
              f"{e['lambda_home']:.3f}/{e['lambda_away']:.3f} | 1/X/2 scritto "
              f"{e['x12_scritto'][0]}/{e['x12_scritto'][1]}/{e['x12_scritto'][2]} -> rifit "
              f"{e['x12_rifit'][0]}/{e['x12_rifit'][1]}/{e['x12_rifit'][2]} | converged {e['converged']}")
        if not e["squadre_coerenti"]:
            print(f"{'':>12}ATTENZIONE squadre diverse: payload {e['squadre_payload'][0]} - "
                  f"{e['squadre_payload'][1]} | riga fixture_predictions {e['squadre_riga'][0]} - "
                  f"{e['squadre_riga'][1]}: il confronto non e' fra la stessa partita orientata")
    print(f"griglie valide dopo il rifit: {valide}/{len(esiti)}")
    return 0 if valide == len(esiti) else 1


def _fmt(v: Any) -> str:
    return "-" if v is None else f"{v:+.4f}"


def main(argv: List[str]) -> int:
    con_rifit = "--rifit" in argv
    args = [a for a in argv if a != "--rifit"]
    if len(args) != 1:
        print(__doc__)
        return 2
    with open(args[0], encoding="utf-8") as fh:
        dati = json.load(fh)
    esiti = verifica(dati)
    print("fixture_id  lega   lh     la     rho      lh*la  1/(lh*la) dominio_rho          "
          "u05_scritto u05_ricostr u05_HT  rho_dopo u05_dopo  somma_dopo")
    for e in esiti:
        print(f"{e['fixture_id']!s:>10}  {e['league_id']!s:>5}  {e['lambda_home']:5.3f}  "
              f"{e['lambda_away']:5.3f}  {e['rho']:+.4f}  {e['lh_la']:6.3f} {e['inv_lh_la']:7.4f}   "
              f"[{e['rho_lo']:+.4f},{e['rho_hi']:+.4f}] {'OK ' if e['rho_nel_dominio'] else 'FUORI'} "
              f"{_fmt(e['under_0_5_scritto'])}     {_fmt(e['under_0_5_ricostruito'])}     "
              f"{_fmt(e['under_0_5_ht_scritto'])} {e['rho_dopo']:+.4f}  {e['under_0_5_dopo']:.6f}  "
              f"{e['somma_griglia_dopo']:.12f}")
    for e in esiti:
        k, a, b, d = e["mercato_scarto_max"]
        print(f"{e['fixture_id']!s:>10}  locale: mercato piu' spostato {k} {a:.4f} -> {b:.4f} (|d| {d:.4f})")
    neg_prima = sum(1 for e in esiti if (e["under_0_5_scritto"] or 0.0) < 0)
    fuori = sum(1 for e in esiti if not e["rho_nel_dominio"])
    valide = sum(1 for e in esiti if e["griglia_valida_dopo"])
    print(f"\npayload: {len(esiti)} | under_0_5 scritto < 0: {neg_prima} | rho fuori dal dominio "
          f"della coppia: {fuori} | griglie valide dopo: {valide}/{len(esiti)}")
    rc = 0 if valide == len(esiti) else 1
    if con_rifit:
        from db_client import get_supabase_client
        rc = max(rc, _stampa_rifit(rifit(dati, get_supabase_client())))
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
