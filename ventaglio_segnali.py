"""
ventaglio_segnali.py — VENTAGLIO di segnali per partita, ordinato per AFFIDABILITA'
e CONCORDANZA dei 5 motori (dove ogni motore copre il mercato).

I 5 MOTORI e le loro fonti (vedi memory project_calcio_5motori_fusion_backtest_2026-06-19):
  1. POISSON     -> fixture_predictions.db_json_analisi.markets  (1x2, over_x, btts, ht_1x2, first_half_over_0_5)
  2. ML          -> fixture_predictions.model_predictions_json.targets  (gate: targets_not_reliable scarta i non calibrati)
  3. API-Football-> fixture_predictions.flat_summary  (percent_h/d/a, prediction_under_over/advice)
  4. FREQUENZE   -> RPC get_market_delays -> stats.frequency  (base-rate del mercato nella lega)
  5. RITARDI     -> RPC get_market_delays -> rit_vs_media     (regime: caldo<0.8, molto-in-ritardo>=1.6 = filtro EVITA)
     (Frequenze e Ritardi provengono dalla STESSA RPC: e' lo Studio Ritardi/Frequenze certificato.)

SCORING — non e' una probabilita' garantita, e' un INDICE DI FIDUCIA euristico ancorato ai
benchmark di accuratezza DIREZIONALE validati point-in-time su 65k partite:
  HT Over0.5 ~76% | O/U1.5 ~76% | O/U3.5 ~74% | O/U2.5 ~67% | BTTS ~60% | 1X2(concorde) ~57% | HT 1X2 ~52%
Aggiustamenti: convinzione Poisson, n. motori concordi, ML calibrato+concorde, filtro regime (caldo/ritardo).

Uso:  python ventaglio_segnali.py            (le 18 partite Betfair del 2026-06-19)
      python ventaglio_segnali.py 1492915 1553786 ...   (fixture_id specifici)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
H = {"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json"}

# 18 partite Betfair del 2026-06-19 (default)
DEFAULT_FIDS = [
    1529745, 1553788, 1529747, 1495868, 1553787, 1492916, 1492917, 1492915,
    1492717, 1492718, 1492919, 1492918, 1492719, 1492720, 1553786, 1492716,
    1514209, 1499479,
]

# Accuratezza direzionale attesa per mercato quando il segnale e' "AGISCI" (benchmark validati).
MARKET_BASE = {
    "HT Over 0.5": 0.76,
    "O/U 1.5": 0.76,
    "O/U 3.5": 0.74,
    "O/U 2.5": 0.67,
    "BTTS": 0.60,
    "1X2": 0.55,
    "HT 1X2": 0.52,
}


# ------------------------------------------------------------------ HTTP helpers
def _get(path: str):
    req = urllib.request.Request(URL + "/rest/v1/" + path, headers=H)
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())


def _rpc(name: str, payload: dict):
    req = urllib.request.Request(
        URL + "/rest/v1/rpc/" + name, data=json.dumps(payload).encode(), headers=H, method="POST"
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())


# ------------------------------------------------------------------ data model
@dataclass
class Vote:
    engine: str            # "Poisson" | "ML" | "API" | "Freq" | "Ritardi"
    direction: str         # es "OVER", "UNDER", "H", "D", "A", "SI", "NO"
    conviction: float      # prob 0..1 (per Freq = base-rate; per Ritardi = rvm)
    note: str = ""


@dataclass
class Signal:
    market: str
    direction: str
    votes: list[Vote] = field(default_factory=list)
    score: float = 0.0
    tier: str = ""
    concord: int = 0
    n_engines: int = 0
    regime: str = ""       # "caldo" | "neutro" | "ritardo" | ""


# ------------------------------------------------------------------ engine readers
def _argmax_dir(d: dict[str, float], mapping: dict[str, str]) -> tuple[str, float]:
    """Da un dict {classe:prob} ritorna (direzione_normalizzata, prob_max)."""
    k = max(d, key=lambda x: d[x])
    return mapping.get(str(k), str(k)), float(d[k])


def _binary_dir(d: dict, pos="OVER", neg="UNDER") -> tuple[str, float]:
    """Da {'True':p,'False':1-p} ritorna (pos/neg, conv) dove conv = prob del lato scelto."""
    p_true = float(d.get("True", 0.0))
    return (pos, p_true) if p_true >= 0.5 else (neg, 1.0 - p_true)


# mappa mercato-ventaglio -> (chiave Poisson, target ML, tipo)
MARKETS = [
    ("O/U 1.5", "over_1_5", "target_over_1_5", "ou", ("over", "1"), ("under", "2")),
    ("O/U 2.5", "over_2_5", "target_over_2_5", "ou", ("over", "2"), ("under", "3")),
    ("O/U 3.5", "over_3_5", "target_over_3_5", "ou", ("over", "3"), ("under", "4")),
    ("HT Over 0.5", "first_half_over_0_5", "target_ht_over_0_5", "htou", ("ovpt", "0"), None),
    ("BTTS", "btts", "target_btts", "btts", None, None),
    ("1X2", "1x2", "target_1x2", "1x2", None, None),
    ("HT 1X2", "ht_1x2", "target_ht_1x2", "1x2", None, None),
]

ONEX2_MAP = {"H": "H", "D": "D", "A": "A"}
BTTS_MAP = {"True": "SI", "False": "NO"}


def build_signals(fp: dict, delays_cache: dict, league_id: int) -> list[Signal]:
    # Usa le probabilita' Poisson CALIBRATE se presenti (dato migliore, coerente con l'ML
    # che e' gia' calibrato nel DB); fallback al grezzo finche' il backfill non e' passato.
    _dba = fp.get("db_json_analisi") or {}
    pois = _dba.get("markets_calibrated") or _dba.get("markets") or {}
    mpj = fp.get("model_predictions_json") or {}
    targets = mpj.get("targets") or {}
    not_reliable = {t["target"] for t in (mpj.get("targets_not_reliable") or [])}
    fs = fp.get("flat_summary") or {}

    signals: list[Signal] = []
    for label, pkey, mtarget, kind, over_code, under_code in MARKETS:
        votes: list[Vote] = []

        # --- POISSON (motore leader: definisce la direzione di riferimento) ---
        lead_dir = None
        if pkey in pois and isinstance(pois[pkey], dict):
            pm = pois[pkey]
            if kind in ("ou", "htou"):
                d, c = _binary_dir(pm, "OVER", "UNDER")
            elif kind == "btts":
                d, c = _binary_dir(pm, "SI", "NO")
            else:  # 1x2
                d, c = _argmax_dir({k: pm[k] for k in ("H", "D", "A") if k in pm}, ONEX2_MAP)
            lead_dir = d
            votes.append(Vote("Poisson", d, c))

        if lead_dir is None:
            continue  # senza Poisson non emettiamo (no direzione di riferimento)

        # --- ML (solo se calibrato per questo mercato) ---
        if mtarget in targets and mtarget not in not_reliable:
            tm = targets[mtarget]
            if kind in ("ou", "htou"):
                d, c = _binary_dir(tm, "OVER", "UNDER")
            elif kind == "btts":
                d, c = _binary_dir(tm, "SI", "NO")
            else:
                d, c = _argmax_dir({k: tm[k] for k in ("H", "D", "A") if k in tm}, ONEX2_MAP)
            votes.append(Vote("ML", d, c, "calibrato"))
        elif mtarget in not_reliable:
            votes.append(Vote("ML", "-", 0.0, "non affidabile (scartato dal gate)"))

        # --- API-Football ---
        if kind == "1x2" and label == "1X2":
            ph, pd, pa = fs.get("percent_home"), fs.get("percent_draw"), fs.get("percent_away")
            if None not in (ph, pd, pa) and (ph or pd or pa):
                vals = {"H": float(ph), "D": float(pd), "A": float(pa)}
                d = max(vals, key=lambda x: vals[x])
                votes.append(Vote("API", d, vals[d] / 100.0))
        elif label == "O/U 2.5":
            puo = fs.get("prediction_under_over")
            if puo:
                s = str(puo).strip()
                if s.startswith("-") or "under" in s.lower():
                    votes.append(Vote("API", "UNDER", 0.0, str(puo)))
                elif s.startswith("+") or "over" in s.lower():
                    votes.append(Vote("API", "OVER", 0.0, str(puo)))

        # --- FREQUENZE + RITARDI (RPC get_market_delays sul LATO scelto da Poisson) ---
        regime = ""
        code = None
        if kind in ("ou", "htou"):
            code = over_code if lead_dir == "OVER" else under_code
        if code is not None:
            ck = (league_id, code[0], code[1])
            st = delays_cache.get(ck)
            if st is None:
                try:
                    res = _rpc("get_market_delays", {
                        "p_league_id": league_id, "p_market": code[0], "p_target": code[1],
                        "p_mode": "all", "p_last_n": None, "p_season_year": None,
                    })
                    st = (res or {}).get("stats") or {}
                except (urllib.error.HTTPError, urllib.error.URLError, KeyError):
                    st = {}
                delays_cache[ck] = st
            if st:
                freq = st.get("frequency")
                rvm = st.get("rit_vs_media")
                rit = st.get("ritardo_attuale")
                if freq is not None:
                    votes.append(Vote("Freq", lead_dir, float(freq),
                                      f"base-rate lega {float(freq):.0%}"))
                if rvm is not None:
                    if rvm <= 0.8:
                        regime = "caldo"
                    elif rvm >= 1.6:
                        regime = "ritardo"
                    else:
                        regime = "neutro"
                    votes.append(Vote("Ritardi", lead_dir, float(rvm),
                                      f"rvm={rvm:.2f} rit={rit} -> {regime}"))

        # --- concordanza + scoring ---
        directional = [v for v in votes if v.engine in ("Poisson", "ML", "API") and v.direction not in ("-",)]
        concord = sum(1 for v in directional if v.direction == lead_dir)
        n_eng = len(directional)

        base = MARKET_BASE.get(label, 0.55)
        pconv = next((v.conviction for v in votes if v.engine == "Poisson"), 0.5)
        score = base
        # convinzione Poisson
        if pconv >= 0.70:
            score += 0.04
        elif pconv >= 0.65:
            score += 0.02
        elif pconv >= 0.60:
            score += 0.0
        elif pconv >= 0.55:
            score -= 0.03
        else:
            score -= 0.08
        # concordanza (motori extra oltre il leader, max +0.06)
        score += min(max(concord - 1, 0) * 0.025, 0.06)
        # ML calibrato e concorde
        if any(v.engine == "ML" and v.direction == lead_dir and v.note == "calibrato" for v in votes):
            score += 0.03
        # regime
        if regime == "caldo":
            score += 0.03
        elif regime == "ritardo":
            score -= 0.12

        score = max(0.40, min(0.85, score))

        if regime == "ritardo":
            tier = "EVITA (regime girato)"
        elif score >= 0.72:
            tier = "A_MAX"
        elif score >= 0.66:
            tier = "B_ALTA"
        elif score >= 0.60:
            tier = "C_MEDIA"
        elif score >= 0.54:
            tier = "D_DEBOLE"
        else:
            tier = "SCARTA"

        signals.append(Signal(label, lead_dir, votes, score, tier, concord, n_eng, regime))

    signals.sort(key=lambda s: s.score, reverse=True)
    return signals


# ------------------------------------------------------------------ rendering
TIER_ICON = {"A_MAX": "[+++]", "B_ALTA": "[++ ]", "C_MEDIA": "[+  ]", "D_DEBOLE": "[~  ]",
             "SCARTA": "[   ]", "EVITA (regime girato)": "[!!!]"}


def render(fid: int, name: str, signals: list[Signal]) -> str:
    out = [f"\n┌─ {fid}  {name}"]
    for s in signals:
        eng = []
        for v in s.votes:
            if v.engine in ("Poisson", "ML", "API"):
                if v.direction == "-":
                    eng.append(f"{v.engine}✗")
                else:
                    mark = "v" if v.direction == s.direction else "x"
                    eng.append(f"{v.engine}{mark}{v.direction}({v.conviction:.0%})")
            elif v.engine == "Freq":
                eng.append(f"Freq {v.conviction:.0%}")
            elif v.engine == "Ritardi":
                eng.append(f"Rit {v.note.split('->')[-1].strip()}")
        icon = TIER_ICON.get(s.tier, "")
        out.append(
            f"│ {icon} {s.market:12s} {s.direction:5s} "
            f"fid~{s.score:.2f} [{s.tier:8s}] conc {s.concord}/{s.n_engines}  "
            f"| {'  '.join(eng)}"
        )
    out.append("└" + "─" * 60)
    return "\n".join(out)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    fids = [int(x) for x in sys.argv[1:]] or DEFAULT_FIDS
    fid_csv = "in.(" + ",".join(map(str, fids)) + ")"
    fps = _get(
        "fixture_predictions?select=fixture_id,db_json_analisi,model_predictions_json,flat_summary"
        f"&fixture_id={fid_csv}"
    )
    names = _get(
        f"matches?select=fixture_id,home_team_name,away_team_name,league_id,goals_home,goals_away,status_short&fixture_id={fid_csv}"
    )
    name_by = {m["fixture_id"]: m for m in names}
    fp_by = {f["fixture_id"]: f for f in fps}

    delays_cache: dict = {}
    all_signals: list[tuple] = []

    print("=" * 72)
    print("VENTAGLIO SEGNALI 5-MOTORI - ordinato per affidabilita' (indice fiducia)")
    print("Legenda: [+++]alta [+]media [~]debole [!!!]EVITA(regime) | v=concorde x=discorde")
    print("=" * 72)

    for fid in fids:
        fp = fp_by.get(fid)
        m = name_by.get(fid, {})
        nm = f"{m.get('home_team_name','?')} - {m.get('away_team_name','?')}"
        if m.get("status_short") in ("FT", "AET", "PEN"):
            nm += f"  [RIS {m.get('goals_home')}-{m.get('goals_away')}]"
        if not fp:
            print(f"\n┌─ {fid}  {nm}\n│ (nessuna predizione stoccata)\n└" + "─" * 40)
            continue
        league_id = (fp.get("db_json_analisi") or {}).get("league_id") or m.get("league_id")
        sigs = build_signals(fp, delays_cache, league_id)
        print(render(fid, nm, sigs))
        for s in sigs:
            all_signals.append((s.score, fid, nm, s))

    # ---- ventaglio GLOBALE ordinato (top segnali cross-partita) ----
    all_signals.sort(key=lambda x: x[0], reverse=True)
    print("\n" + "=" * 72)
    print("TOP 25 SEGNALI GLOBALI (tutte le partite, ordinati per fiducia)")
    print("=" * 72)
    for score, fid, nm, s in all_signals[:25]:
        if s.tier in ("SCARTA",):
            continue
        print(f"{TIER_ICON.get(s.tier,'')} {s.score:.2f} [{s.tier:18s}] "
              f"{s.market:12s} {s.direction:5s} conc {s.concord}/{s.n_engines}  "
              f"{nm[:38]}")


if __name__ == "__main__":
    main()
