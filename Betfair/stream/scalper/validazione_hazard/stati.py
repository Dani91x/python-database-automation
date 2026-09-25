"""stati.py - dalle partite agli STATI osservabili (partite-minuto), con la verita'.

LA VERITA' (quello che serve al trader): allo stato "t minuti giocati nel tempo
h", y_k = 1 se nel tempo h c'e' almeno un gol nei prossimi k minuti di gioco,
cioe' in posizione p con t < p <= t + k. Le posizioni oltre 45 sono il
RECUPERO (45+e): un gol al 45+2 sta nella finestra di chi guarda al 44', uno
al 46' (secondo tempo) NO (fra i due tempi c'e' l'intervallo). La partita
finisce quando finisce: una finestra che sfora la fine del tempo si tronca da
sola (dopo la fine non ci sono gol).

GLI STATI A RISCHIO (su cui si misura):
  regolari     t = 0..44 in ogni tempo (minuto live 0..89): sempre;
  recupero 2T  j = 0..d2-1 (minuto live 90+j), solo dove d2 e' NOTO (2024+);
  recupero 1T  j = 0..s1_vivo-1 (minuto live 45+j), solo dove un evento NON-gol
               successivo prova che la partita era viva (2024+). Il DB non ha la
               durata del recupero del 1T: e' un campione dichiaratamente parziale.
Ogni stato porta: gol casa/trasferta e rossi casa/trasferta FINO a t compreso
(stessa convenzione dell'atlante: gol con posizione <= t), minuti dall'ultimo
gol, e il minuto che il feed live darebbe.
PURO: numpy, nessuna rete.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

from Betfair.stream.scalper.validazione_hazard.dati import Partita

COLONNE_INT = ("mi", "lega", "stagione", "tempo", "t", "stop", "j", "m_live",
               "gh", "ga", "rh", "ra", "y2", "y3", "g1", "dal_gol")


def _conta(pos: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Quanti eventi (posizioni ordinate) hanno posizione <= t, per ogni t."""
    if pos.size == 0:
        return np.zeros(t.shape, dtype=np.int32)
    return np.searchsorted(pos, t, side="right").astype(np.int32)


def stati_partita(p: Partita, mi: int) -> Dict[str, np.ndarray]:
    """Gli stati a rischio di UNA partita (vedi docstring del modulo)."""
    blocchi: List[Dict[str, np.ndarray]] = []
    gol_prec_h = gol_prec_a = 0
    rossi_prec_h = rossi_prec_a = 0
    ultimo_gol_abs = None          # tempo assoluto (0..90, recupero schiacciato) dell'ultimo gol
    for h in (1, 2):
        gh_pos = np.array(sorted(g[1] for g in p.gol if g[0] == h and g[2] == "h"), dtype=np.int32)
        ga_pos = np.array(sorted(g[1] for g in p.gol if g[0] == h and g[2] == "a"), dtype=np.int32)
        tutti = np.array(sorted(g[1] for g in p.gol if g[0] == h), dtype=np.int32)
        rh_pos = np.array(sorted(r[1] for r in p.rossi if r[0] == h and r[2] == "h"), dtype=np.int32)
        ra_pos = np.array(sorted(r[1] for r in p.rossi if r[0] == h and r[2] == "a"), dtype=np.int32)
        n_rec = (p.s1_vivo if h == 1 else (p.d2 or 0))
        t = np.arange(0, 45 + int(n_rec), dtype=np.int32)
        stop = (t >= 45).astype(np.int32)
        j = np.where(stop == 1, t - 45, 0).astype(np.int32)
        base = 0 if h == 1 else 45
        # minuto del feed live: 0..44 / 45..89, recupero 1T 45+j, recupero 2T 90+j
        m_live = np.where(stop == 1, (45 if h == 1 else 90) + j, base + t).astype(np.int32)
        c_t = _conta(tutti, t)
        y2 = (_conta(tutti, t + 2) - c_t > 0).astype(np.int32)
        y3 = (_conta(tutti, t + 3) - c_t > 0).astype(np.int32)
        g1 = (_conta(tutti, t + 1) - c_t).astype(np.int32)     # gol nel prossimo minuto
        # minuti dall'ultimo gol (tempo assoluto con il recupero schiacciato sul 45/90)
        t_abs = base + np.minimum(t, 45)
        dal = np.full(t.shape, 99, dtype=np.int32)
        if ultimo_gol_abs is not None:
            dal = (t_abs - ultimo_gol_abs).astype(np.int32)
        if tutti.size:
            idx = c_t - 1                  # indice dell'ultimo gol del tempo con pos <= t
            ok = idx >= 0
            g_abs = base + np.minimum(tutti[np.maximum(idx, 0)], 45)
            dal = np.where(ok, t_abs - g_abs, dal).astype(np.int32)
        dal = np.minimum(dal, 99)
        blocchi.append({
            "mi": np.full(t.shape, mi, dtype=np.int32),
            "lega": np.full(t.shape, p.league_id, dtype=np.int32),
            "stagione": np.full(t.shape, p.season, dtype=np.int32),
            "tempo": np.full(t.shape, h, dtype=np.int32),
            "t": t, "stop": stop, "j": j, "m_live": m_live,
            "gh": gol_prec_h + _conta(gh_pos, t), "ga": gol_prec_a + _conta(ga_pos, t),
            "rh": rossi_prec_h + _conta(rh_pos, t), "ra": rossi_prec_a + _conta(ra_pos, t),
            "y2": y2, "y3": y3, "g1": g1, "dal_gol": dal,
        })
        gol_prec_h += int(gh_pos.size)
        gol_prec_a += int(ga_pos.size)
        rossi_prec_h += int(rh_pos.size)
        rossi_prec_a += int(ra_pos.size)
        if tutti.size:
            ultimo_gol_abs = base + min(int(tutti[-1]), 45)
    return {k: np.concatenate([b[k] for b in blocchi]) for k in COLONNE_INT}


def tabella_stati(partite: List[Partita]) -> Dict[str, np.ndarray]:
    """Tutti gli stati di tutte le partite, colonne numpy allineate."""
    parti = [stati_partita(p, i) for i, p in enumerate(partite)]
    return {k: np.concatenate([x[k] for x in parti]) for k in COLONNE_INT}
