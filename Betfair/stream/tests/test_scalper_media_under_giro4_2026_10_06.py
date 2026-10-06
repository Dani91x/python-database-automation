"""MEDIA UNDER, quarto giro (06/10/2026): decisioni dell'utente su P1 e P13.

* P1 (a): lo STOP della sessione lascia appoggiata la banca PERSIST della
  modalita' (la posizione resta protetta e si chiude da sola).
* P13: dopo un crash / una caduta di rete la modalita' in SOLDI VERI riprende
  ESATTAMENTE da dove era, senza errori e senza operazioni doppie, leggendo il
  conto (in prova niente: la persistenza serve in soldi veri).
* In piu' (scelta dell'utente): ogni strategia della sessione ha un nome legato
  alla PARTITA (prima la classe: una sessione in soldi veri riadottava, e
  all'arresto annullava, gli ordini delle sessioni delle altre partite).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from Betfair.stream.backtest import minimi_banco as MB
from Betfair.stream.scalper import media_under_bot as MU
from Betfair.stream.scalper import scalper_session as SS
from Betfair.stream.scalper.tools import replay_registrazioni as R
from Betfair.stream.tennis_live.tests.test_cantiere_t_pro_residuo_2026_09_28 import (  # noqa: F401
    esecuzione_differita,
)
from Betfair.stream.tests.banco_media_under import EVENTO, KO_MS, BancoMedia, giri


@pytest.fixture(params=[1, 4])
def differita(request, esecuzione_differita):
    """Esecuzione dei pacchetti di flumine differita di 1 e di 4 book."""
    esecuzione_differita.ritardo = request.param
    return esecuzione_differita


@pytest.fixture
def exchange_it():
    with MB.minimi_it_su_flumine() as registro:
        yield registro


@pytest.fixture
def soldi_veri_dichiarati():
    from Betfair.stream.backtest.certifica import _freni_da_banco

    with _freni_da_banco():
        yield


def _catalogo():
    defs = {
        "1.300000001": {"market_type": "MATCH_ODDS", "runners": [(11, 1), (12, 2), (58805, 3)]},
        "1.300000025": {"market_type": "OVER_UNDER_25", "runners": [(47972, 1), (47973, 2)]},
        "1.300000035": {"market_type": "OVER_UNDER_35", "runners": [(1222344, 1), (1222345, 2)]},
    }
    follow = {"event_id": EVENTO, "fixture_id": None, "league_id": None,
              "home_name": "A", "away_name": "B", "open_date": "2025-09-29T10:00:00.000Z"}
    return R.catalogo_dal_raw(defs), follow


# ===========================================================================
# A. il nome di ogni strategia e' legato alla partita
# ===========================================================================
def test_nome_strategia_per_partita_e_ruolo():
    assert SS.nome_strategia("maker", "35797769") == "scm35797769"
    assert SS.nome_strategia("sniper", "35797769") == "scn35797769"
    assert SS.nome_strategia("theta", "35797769") == "sct35797769"
    assert SS.nome_strategia("media", "35797769") == "mu35797769"
    # e' anche il customerStrategyRef: al piu' 15 caratteri, diverso per partita
    assert len(SS.nome_strategia("maker", "123456789012345")) == 15
    nomi = {SS.nome_strategia(r, e) for r in SS.PREFISSI_STRATEGIA
            for e in ("35797769", "35760084")}
    assert len(nomi) == 8


@pytest.mark.usefixtures("soldi_veri_dichiarati")
@pytest.mark.parametrize("scenario, ruolo", [("base", "maker"), (R.SCENARIO_MEDIA, "media")])
def test_la_sessione_arma_le_strategie_col_nome_della_partita(scenario, ruolo):
    import hashlib

    cat, follow = _catalogo()
    par, _cli = R.arma_e_cattura(EVENTO, R.control_della_ui(EVENTO, scenario), follow, cat)
    nome = SS.nome_strategia(ruolo, EVENTO)
    assert par["_name"] == nome
    # l'hash con cui flumine riadotta gli ordini dal conto e' quello del nome
    assert par["name_hash"] == hashlib.sha1(nome.encode("utf-8")).hexdigest()[:13]
