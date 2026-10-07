# -*- coding: utf-8 -*-
"""A11 giudica anche la DISTANZA di un aggregato «Any Other» (07/10).

Senza questa estensione `certificazione._distanza` rispondeva None per ogni
nome non numerico e A11 taceva: un ingresso su «Any Other Home Win» a un gol
dal punteggio (3-0 -> 4-0) passava il banco in silenzio (catalogo 36: i
controlli devono vedere la decisione, non fidarsi del bot)."""
from __future__ import annotations

from datetime import datetime, timezone

from Betfair.omega import certificazione as CERT
from Betfair.omega import omega_config as C
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_model as M
from Betfair.omega import omega_v3 as V3

ORA = datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc)
NOMI_CS = [f"{h} - {a}" for h in range(4) for a in range(4)] + [
    "Any Other Home Win", "Any Other Away Win", "Any Other Draw"]


class _Snap:
    """Il book della decisione: `MarketSnapshot.runners` di `ScoreRunner` veri."""

    def __init__(self) -> None:
        self.runners = [E.ScoreRunner(selection_id=i + 1, name=n, lay_price=60.0,
                                      lay_size=10.0) for i, n in enumerate(NOMI_CS)]


def _cand(nome: str):
    p_imp = V3.p_implicita(60.0, 0.05)
    return V3.CandidatoV3(
        selection_id=9063254, name=nome, price=60.0, size=1.0, p_modello=0.012,
        p_fusa=0.012, p_empirica=None, n_empirico=None, p_nostra=0.012,
        p_implicita=p_imp, k_usato=1.11, margine=p_imp / 0.012,
        ev=V3.ev_gamba(0.012, 60.0, 1.0, 0.05), liability=V3.liability(1.0, 60.0),
        motivo="prova")


def _mom(h: int, a: int, nome: str, snapshot=None):
    return CERT.Momento(tipo="selezione", now=ORA, motore="v3", leg="ft_cs",
                        params=C.resolve_params({"strategy_version": 3}),
                        cand=_cand(nome), state=M.LiveState(minute=60, score_home=h,
                                                            score_away=a),
                        snapshot=snapshot)


def _codici(m):
    return {v.codice for v in CERT.verifica(m)}


def test_a11_aggregato_a_un_gol_e_una_violazione():
    assert "A11" in _codici(_mom(3, 0, "Any Other Home Win", _Snap()))


def test_a11_aggregato_gia_vinto_e_una_violazione():
    assert "A11" in _codici(_mom(4, 4, "Any Other Draw", _Snap()))


def test_a11_aggregato_alla_distanza_giusta_tace():
    assert "A11" not in _codici(_mom(2, 2, "Any Other Home Win", _Snap()))


def test_a11_senza_book_non_giudica_l_aggregato():
    assert "A11" not in _codici(_mom(3, 0, "Any Other Home Win", None))
