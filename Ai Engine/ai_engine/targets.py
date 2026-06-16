from __future__ import annotations

from typing import Dict

import pandas as pd


def _result_1x2(row: pd.Series) -> str | None:
    gh = row.get("goals_home")
    ga = row.get("goals_away")
    if pd.isna(gh) or pd.isna(ga):
        return None
    if gh > ga:
        return "H"
    if gh < ga:
        return "A"
    return "D"


def _over_under(total_goals: float, line: float) -> str | None:
    if pd.isna(total_goals):
        return None
    return "over" if total_goals > line else "under"


def add_targets_from_matches(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds all available targets from matches table columns.
    Targets are appended as new columns. Does not modify inputs in-place.
    """
    if df.empty:
        return df

    out = df.copy()
    out["goals_home"] = pd.to_numeric(out.get("goals_home"), errors="coerce")
    out["goals_away"] = pd.to_numeric(out.get("goals_away"), errors="coerce")
    out["halftime_home"] = pd.to_numeric(out.get("halftime_home"), errors="coerce")
    out["halftime_away"] = pd.to_numeric(out.get("halftime_away"), errors="coerce")
    out["fulltime_home"] = pd.to_numeric(out.get("fulltime_home"), errors="coerce")
    out["fulltime_away"] = pd.to_numeric(out.get("fulltime_away"), errors="coerce")

    out["target_1x2"] = out.apply(_result_1x2, axis=1)

    out["target_btts"] = (out["goals_home"] > 0) & (out["goals_away"] > 0)

    out["target_total_goals"] = out["goals_home"] + out["goals_away"]

    for line in [0.5, 1.5, 2.5, 3.5, 4.5]:
        out[f"target_over_{str(line).replace('.', '_')}"] = out["target_total_goals"] > line

    out["target_clean_sheet_home"] = out["goals_away"] == 0
    out["target_clean_sheet_away"] = out["goals_home"] == 0

    # Team goals lines
    for line in [0.5, 1.5, 2.5]:
        out[f"target_home_over_{str(line).replace('.', '_')}"] = out["goals_home"] > line
        out[f"target_away_over_{str(line).replace('.', '_')}"] = out["goals_away"] > line

    # HT/FT
    out["target_ht_1x2"] = out.apply(
        lambda r: _result_1x2(pd.Series({"goals_home": r["halftime_home"], "goals_away": r["halftime_away"]})),
        axis=1,
    )
    out["target_ft_1x2"] = out.apply(
        lambda r: _result_1x2(pd.Series({"goals_home": r["fulltime_home"], "goals_away": r["fulltime_away"]})),
        axis=1,
    )
    # HT/FT combined target. Only define it when BOTH half-time and full-time
    # results are available. Previously `fillna("")` turned a missing half into
    # spurious classes like "_", "H_" or "_A" (which are not real outcomes and
    # survive dropna because they are non-null strings), polluting the class
    # distribution and the log-loss/Brier of the HT/FT market. Now we emit None
    # when either half is missing, so dropna(subset=["target_ht_ft"]) removes them.
    _ht_res = out["target_ht_1x2"]
    _ft_res = out["target_ft_1x2"]
    _ht_ft_valid = _ht_res.notna() & _ft_res.notna()
    out["target_ht_ft"] = (_ht_res.fillna("") + "_" + _ft_res.fillna("")).where(_ht_ft_valid, other=None)

    # First Half Over 0.5 (direct boolean target)
    # Use .where() to propagate NaN when halftime data is missing, instead of
    # silently coercing NaN > 0 to False (which creates false negatives).
    # FIX 2026-06-16: label come STRINGA "True"/"False" (NaN se primo-tempo
    # mancante). Motivi: (1) `(bool).where(mask)` produce dtype object (bool+NaN)
    # che il classificatore rifiuta con "Unknown label type" sulle leghe con dati
    # 1T parziali; (2) il serving e money_management cercano la classe ESATTA
    # "True" per questo mercato (HT05, ai_path=(target_ht_over_0_5,"True")). Le
    # stringhe "True"/"False" si addestrano come binario pulito (come target_1x2)
    # e, via str(classes_), restano coerenti con tutti gli altri target binari
    # (bool -> "True"/"False"). Un cast a float darebbe classi "1.0"/"0.0" e il
    # segnale HT05 sparirebbe silenziosamente in scommessa.
    ht_total = out["halftime_home"] + out["halftime_away"]
    out["target_ht_over_0_5"] = (
        (ht_total > 0).map({True: "True", False: "False"}).where(ht_total.notna())
    )

    # Exact score — keep NaN when goals are missing instead of using "-1--1"
    has_goals = out["goals_home"].notna() & out["goals_away"].notna()
    out["target_exact_score"] = (
        out["goals_home"].astype("Int64").astype(str) + "-" + out["goals_away"].astype("Int64").astype(str)
    ).where(has_goals, other=None)

    return out


def add_targets_from_team_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds targets derived from team stats (corners, shots on target).
    Expects columns like home_stats_corner_kicks, away_stats_corner_kicks, etc.
    """
    if df.empty:
        return df

    out = df.copy()
    hc = pd.to_numeric(out.get("home_stats_corner_kicks"), errors="coerce")
    ac = pd.to_numeric(out.get("away_stats_corner_kicks"), errors="coerce")
    out["target_corners_total"] = hc + ac

    hsot = pd.to_numeric(out.get("home_stats_shots_on_goal"), errors="coerce")
    asot = pd.to_numeric(out.get("away_stats_shots_on_goal"), errors="coerce")
    out["target_sot_total"] = hsot + asot

    return out


def add_targets_from_events(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds targets derived from match events (cards, goal timing).
    Expects columns like home_events_yellow_cards, away_events_yellow_cards, etc.
    """
    if df.empty:
        return df

    out = df.copy()
    def _series(col: str) -> pd.Series:
        if col in out.columns:
            return pd.to_numeric(out[col], errors="coerce")
        # index=out.index: evita disallineamento quando la colonna manca (il
        # fallback con RangeIndex di default si misallineerebbe con out filtrato).
        return pd.Series([pd.NA] * len(out), index=out.index)

    hy = _series("home_events_yellow_cards")
    ay = _series("away_events_yellow_cards")
    hr = _series("home_events_red_cards")
    ar = _series("away_events_red_cards")

    out["target_cards_total"] = hy + ay + hr + ar
    out["target_home_cards"] = hy + hr
    out["target_away_cards"] = ay + ar

    # Goal timing — CORRETTO 2026-06-16 (bug di logica trovati in code-review):
    # - target_first_goal_before_30 = il PRIMO gol del match e' prima del 30'.
    #   Usa SOLO min_goal_minute (minuto del primo gol, eventi-gol). RIMOSSO il
    #   fallback su avg_goal_minute: quest'ultimo e' la media di TUTTI gli eventi
    #   (gol+cartellini+sostituzioni), quindi una squadra senza gol ma con un
    #   giallo al 25' veniva etichettata "gol prima del 30'" => label corrotte.
    # - target_goal_in_2h = c'e' stato un gol nel 2T = ULTIMO gol del match >= 46'.
    #   Prima usava il PRIMO gol: una squadra che segna al 30' e al 70' risultava
    #   "nessun gol nel 2T" (primo gol=30 < 46) pur avendo segnato nel 2T.
    #   Serve il MAX del minuto-gol tra le due squadre.
    hgm_min = _series("home_events_min_goal_minute")
    agm_min = _series("away_events_min_goal_minute")
    hgm_max = _series("home_events_max_goal_minute")
    agm_max = _series("away_events_max_goal_minute")
    first_min = pd.concat([hgm_min, agm_min], axis=1).min(axis=1)
    last_min = pd.concat([hgm_max, agm_max], axis=1).max(axis=1)

    # FIX 2026-06-16 (label integrity): le label di timing-gol valgono SOLO se gli
    # eventi-gol del match sono COMPLETI. La tabella `match_events` ha copertura
    # molto variabile per lega (verificato sul DB: fino al ~61% delle partite CON
    # gol e' PRIVA di evento-gol). In quei casi min/max_goal_minute e' NaN e il
    # vecchio `.fillna(False)` etichettava "nessun gol prima del 30'/nel 2T" anche
    # per partite che AVEVANO segnato => label sistematicamente corrotte e modelli
    # con BSS NEGATIVO (peggio del baseline). Regola corretta:
    #   - 0-0 reale (gol totali == 0)            => False (certo: nessun gol).
    #   - gol > 0 ed eventi-gol COMPLETI
    #     (#eventi-gol == #gol reali)            => uso il timing (booleano).
    #   - gol > 0 ma eventi mancanti/parziali    => None => la riga viene scartata
    #     dal dropna(subset=[target]) del trainer (meglio non addestrare che
    #     addestrare su una label inventata).
    ev_goals = _series("home_events_goals").fillna(0) + _series("away_events_goals").fillna(0)
    actual_goals = (
        pd.to_numeric(out.get("goals_home"), errors="coerce")
        + pd.to_numeric(out.get("goals_away"), errors="coerce")
    )
    goalless = actual_goals == 0
    events_complete = actual_goals.notna() & (ev_goals == actual_goals)
    use_timing = events_complete & ~goalless  # gol presenti e tracciati per intero

    # Label come STRINGA "True"/"False" (None se non affidabile), STESSO pattern di
    # target_ht_over_0_5: una colonna object con bool+None fa rifiutare il
    # classificatore con "Unknown label type"; le stringhe si addestrano come
    # binario pulito e, via str(classes_), restano "True"/"False" coerenti col
    # serving (identiche alle vecchie label bool->str, nessun impatto a valle).
    fb30 = (first_min < 30).map({True: "True", False: "False"})
    g2h = (last_min >= 46).map({True: "True", False: "False"})
    fg = pd.Series([None] * len(out), index=out.index, dtype="object")
    g2 = pd.Series([None] * len(out), index=out.index, dtype="object")
    fg[goalless] = "False"
    g2[goalless] = "False"
    fg[use_timing] = fb30[use_timing]
    g2[use_timing] = g2h[use_timing]
    out["target_first_goal_before_30"] = fg
    out["target_goal_in_2h"] = g2

    return out
