# -*- coding: utf-8 -*-
"""percorsi - dove stanno i dati della misura punto 8 (sola lettura).

Le registrazioni (`_live_raw/`, `tennis_rec/`) e le cache dello strumento di
validazione di Safe NON sono versionate: vivono nel checkout PRINCIPALE, non
nel worktree. Qui si risale dalla cartella corrente fino a trovarle; ogni
funzione accetta comunque un percorso esplicito (``--live-raw`` ecc.).
"""
from __future__ import annotations

import os
from typing import Optional

RADICE_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
DATI_OMEGA = os.path.join(RADICE_REPO, "Betfair", "omega", "data")
F_M2_CAMPIONE = os.path.join(DATI_OMEGA, "m2_campione_2026-09-17.json.gz")
F_PARAMETRI_V3 = os.path.join(DATI_OMEGA, "parametri_vincenti_2026-09-16.json")
F_INTENSITA = os.path.join(RADICE_REPO, "inplay_intensity_by_league.json")
F_OPP_CAL = os.path.join(RADICE_REPO, "Betfair", "safe_strategy", "data", "opp_calibration.json")


def _risali(nome: str, partenza: Optional[str] = None) -> Optional[str]:
    cur = os.path.abspath(partenza or RADICE_REPO)
    for _ in range(8):
        cand = os.path.join(cur, nome)
        if os.path.isdir(cand):
            return cand
        su = os.path.dirname(cur)
        if su == cur:
            break
        cur = su
    return None


def live_raw(esplicito: Optional[str] = None) -> Optional[str]:
    """La cartella `_live_raw/` (registrazioni calcio): esplicita o risalendo."""
    if esplicito:
        return esplicito
    return _risali("_live_raw")


def cache_opportunita(esplicito: Optional[str] = None) -> Optional[str]:
    """Le cache di `validate_opportunity` (Betfair/safe_strategy/data/cache) del
    checkout principale: create il 10/09, in SOLA LETTURA."""
    if esplicito:
        return esplicito
    base = live_raw()
    if not base:
        return None
    cand = os.path.join(os.path.dirname(base), "Betfair", "safe_strategy", "data", "cache")
    return cand if os.path.isdir(cand) else None


def tennis_rec(esplicito: Optional[str] = None) -> Optional[str]:
    """Le registrazioni tennis (`TENNIS_RECORD_DIR` o ~/Desktop/tennis_rec),
    la stessa radice di `registro_bot._cartella_tennis`."""
    if esplicito:
        return esplicito
    env = os.environ.get("TENNIS_RECORD_DIR")
    if env and os.path.isdir(env):
        return env
    cand = os.path.join(os.path.expanduser("~"), "Desktop", "tennis_rec")
    return cand if os.path.isdir(cand) else None
