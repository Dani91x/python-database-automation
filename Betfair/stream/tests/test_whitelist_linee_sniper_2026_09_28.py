"""Linee Under/Over dello SNIPER e whitelist proposta dei mercati (cantiere D2, 28/09).

Reperto del coordinatore: dopo l'integrazione di D2 il registro del banco
(`registro_bot.scalper_calcio.mercati`) elenca OVER_UNDER_85 e la whitelist
proposta (`config_stream.LIVE_MARKET_TYPES_PROPOSTA`) no.

Chi ha ragione lo dice la PRODUZIONE, non il banco:
- `scalper_session.SNIPER_MARKET_TYPES` (dal 10/07, af89a39) sottoscrive
  OU05..OU85 quando lo sniper e' acceso;
- `scalper_session.applica_linea_sniper` a 7 gol totali mette lo sniper sulla
  linea OVER_UNDER_85 (e con `parallel_lines` la usa anche prima).

Quindi la linea 8.5 e' letta davvero da un bot calcio: il registro e' giusto e
la whitelist proposta deve contenerla, altrimenti con la whitelist attiva il
raw del runner non la registra piu' e il banco dello sniper resta cieco oltre
i 7 gol. Questo test ancora la catena produzione -> registro -> whitelist.
"""
from __future__ import annotations

from typing import Any, List

from Betfair.stream import config_stream as CS
from Betfair.stream.backtest.registro_bot import REGISTRO
from Betfair.stream.scalper import scalper_session as SS


class _SniperFinto:
    """Solo i due metodi che `applica_linea_sniper` chiama sul vero
    `SniperStrategy` (stessi nomi e firme) e il suo `parallel_lines`."""

    def __init__(self, parallel_lines: int = 0) -> None:
        self.parallel_lines = parallel_lines
        self.linee: List[str] = []

    def set_line(self, line: Any) -> None:
        self.linee = [] if line in (None, "NONE") else [str(line)]

    def set_lines(self, lines: Any) -> None:
        self.linee = [str(x) for x in lines]


def _linee_usate_in_produzione() -> set:
    usate = set()
    for tot in range(0, 12):
        for par in (0, 1, 2, 3):
            s = _SniperFinto(par)
            SS.applica_linea_sniper(s, {"score_home": tot, "score_away": 0, "minute": 60})
            usate.update(s.linee)
    return usate


def test_lo_sniper_in_produzione_usa_la_linea_8_5():
    s = _SniperFinto(0)
    SS.applica_linea_sniper(s, {"score_home": 4, "score_away": 3, "minute": 80})
    assert s.linee == ["OVER_UNDER_85"]


def test_linee_dello_sniper_sottoscritte_e_nel_registro():
    usate = _linee_usate_in_produzione()
    assert usate <= set(SS.SNIPER_MARKET_TYPES)
    assert usate <= set(REGISTRO["scalper_calcio"].mercati)


def test_whitelist_proposta_contiene_ogni_linea_dello_sniper():
    mancanti = _linee_usate_in_produzione() - CS.LIVE_MARKET_TYPES_PROPOSTA
    assert not mancanti, f"linee dello sniper escluse dalla whitelist proposta: {mancanti}"
