"""Caricamento scoreline dal DB (SOLA LETTURA). Non scrive nulla.

Usa la scoreline REGOLAMENTARE a 90' (fulltime_*) con fallback su goals_*;
per i tempi (HT) usa halftime_*. Le partite AET/PEN entrano col risultato a 90'
(i supplementari/rigori sono processi separati e non vanno nel Poisson).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_client import get_supabase_client  # noqa: E402
from .dixon_coles import MatchScoreline  # noqa: E402
from .model import parse_iso  # noqa: E402

PLAYED = ("FT", "AET", "PEN")


def _reg_goals(row: dict) -> Optional[Tuple[int, int]]:
    """Gol regolamentari a 90': fulltime se presente, altrimenti goals."""
    fh, fa = row.get("fulltime_home"), row.get("fulltime_away")
    if fh is not None and fa is not None:
        return int(fh), int(fa)
    gh, ga = row.get("goals_home"), row.get("goals_away")
    if gh is not None and ga is not None:
        return int(gh), int(ga)
    return None


def _ht_goals(row: dict) -> Optional[Tuple[int, int]]:
    hh, ha = row.get("halftime_home"), row.get("halftime_away")
    if hh is not None and ha is not None:
        return int(hh), int(ha)
    return None


def load_league(league_id: int, season_max: Optional[int] = None
                ) -> Tuple[List[MatchScoreline], List[datetime], List[MatchScoreline], List[datetime], dict]:
    """Carica le partite giocate di una lega.

    Ritorna: (ft_matches, ft_dates, ht_matches, ht_dates, team_names)
    - ft_*: scoreline 90' per il modello principale
    - ht_*: scoreline primo tempo per il modello HT (riusa la stessa matematica)
    - team_names: {team_id: nome}
    """
    sb = get_supabase_client()
    rows = sb.table("matches").select(
        "fixture_id,season_year,fixture_date,status_short,"
        "home_team_id,home_team_name,away_team_id,away_team_name,"
        "goals_home,goals_away,halftime_home,halftime_away,"
        "fulltime_home,fulltime_away"
    ).eq("league_id", league_id).execute().data

    ft_m: List[MatchScoreline] = []
    ft_d: List[datetime] = []
    ht_m: List[MatchScoreline] = []
    ht_d: List[datetime] = []
    names: dict = {}

    for r in rows:
        if r["status_short"] not in PLAYED:
            continue
        if season_max is not None and r["season_year"] is not None and r["season_year"] > season_max:
            continue
        if not r["fixture_date"] or not r["home_team_id"] or not r["away_team_id"]:
            continue
        date = parse_iso(r["fixture_date"])
        names[r["home_team_id"]] = r["home_team_name"]
        names[r["away_team_id"]] = r["away_team_name"]

        reg = _reg_goals(r)
        if reg is not None:
            ft_m.append(MatchScoreline(r["home_team_id"], r["away_team_id"], reg[0], reg[1]))
            ft_d.append(date)
        ht = _ht_goals(r)
        if ht is not None:
            ht_m.append(MatchScoreline(r["home_team_id"], r["away_team_id"], ht[0], ht[1]))
            ht_d.append(date)

    return ft_m, ft_d, ht_m, ht_d, names
