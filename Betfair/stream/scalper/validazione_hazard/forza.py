"""forza.py - forza pre-partita (lambda casa/trasferta) SENZA sbirciare il futuro.

"Poisson-Elo" cronologico: per ogni partita, PRIMA di vederla,
    lambda_casa = mu_casa(lega) * A_casa * D_trasf,   lambda_trasf = mu_trasf(lega) * A_trasf * D_casa
poi, visto il risultato, un passo di gradiente sulla log-verosimiglianza di Poisson:
    log A_casa += eta*(gol_casa - lambda_casa);  log D_trasf += eta*(gol_casa - lambda_casa)  (idem trasf.)
mu della lega = media mobile esponenziale dei gol (casa/trasferta) della lega.
A ogni cambio di stagione i log-rating si RIAVVICINANO a 0 (fattore ``rientro``).
Serve a B1/A5 come stand-in dei lambda che Safe ha davvero in live (motore
Poisson di ``fixture_predictions``): sul 2025 si confronta con quelli veri.
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

from Betfair.stream.scalper.validazione_hazard.dati import Partita

MU_INIZIALE = (1.45, 1.15)


def lambda_prepartita(partite: List[Partita], eta: float = 0.05, rientro: float = 0.7,
                      alfa_lega: float = 0.01) -> Dict[int, Tuple[float, float, float]]:
    """{fixture_id: (lambda_casa, lambda_trasf, loglik_poisson_della_partita)}.
    ``partite`` in qualunque ordine: si ordinano per data (poi fixture_id)."""
    att: Dict[int, float] = {}
    dif: Dict[int, float] = {}
    stag: Dict[int, int] = {}
    mu: Dict[int, List[float]] = {}
    out: Dict[int, Tuple[float, float, float]] = {}
    for p in sorted(partite, key=lambda x: (x.date, x.fixture_id)):
        for tid in (p.home_id, p.away_id):
            if tid in stag and stag[tid] != p.season:
                att[tid] = att.get(tid, 0.0) * rientro
                dif[tid] = dif.get(tid, 0.0) * rientro
            stag[tid] = p.season
        m = mu.setdefault(p.league_id, list(MU_INIZIALE))
        lh = m[0] * math.exp(att.get(p.home_id, 0.0) + dif.get(p.away_id, 0.0))
        la = m[1] * math.exp(att.get(p.away_id, 0.0) + dif.get(p.home_id, 0.0))
        gh, ga = p.ft
        ll = (gh * math.log(lh) - lh - math.lgamma(gh + 1)) + (ga * math.log(la) - la - math.lgamma(ga + 1))
        out[p.fixture_id] = (lh, la, ll)
        eh, ea = gh - lh, ga - la
        att[p.home_id] = att.get(p.home_id, 0.0) + eta * eh
        dif[p.away_id] = dif.get(p.away_id, 0.0) + eta * eh
        att[p.away_id] = att.get(p.away_id, 0.0) + eta * ea
        dif[p.home_id] = dif.get(p.home_id, 0.0) + eta * ea
        m[0] += alfa_lega * (gh - m[0])
        m[1] += alfa_lega * (ga - m[1])
    return out
