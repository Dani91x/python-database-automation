"""CANTIERE N (29/09) - la proposta d'uscita porta SEMPRE i numeri.

Reperto del replay (`prova-tutto-2-2026-09-29`, tennis_scalper, scenario
`uscite-manuali`, UM2 x19): la proposta di stop/timeout calcolava i numeri con
`compute_green(...) if px_x else None`; quando nel book di adesso mancava il
lato di chiusura, la proposta nasceva SENZA prezzo, lato, size e "se chiudi":
l'utente vedeva una scheda vuota.

Correzione (nessuna soglia toccata): la proposta usa il prezzo vivo; se manca,
l'ULTIMO prezzo di chiusura visto per quella selezione con la sua eta'
(`prezzo_eta_s`); se non e' mai stato visto lo DICHIARA
(`numeri_non_disponibili`). Appena torna il prezzo vivo la proposta si aggiorna
(stessa chiave, numeri nuovi, nessuna riga di attivita' in piu').

Tutto via `process_market_book` (il percorso vero del bot): scalper tennis,
scalper calcio (maker) e sniper. Finti: quelli delle suite dei bot.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from typing import Any, List, Optional

import pytest

from Betfair.stream.backtest import uscite_manuali as UM
from Betfair.stream.uscite_proposte import (CHIAVE_ETA_PREZZO,
                                            CHIAVE_NUMERI_NON_DISPONIBILI)
from Betfair.stream.tests.test_scalper_presize_2026_07_11 import _FakeMarket, _FakeOrder

T0 = 1_780_000_000_000                    # epoch ms del primo book
KO = dt.datetime(2026, 9, 29, 20, 0, 0)   # KO lontano: nessuna finestra di flatten


def _book(pt: int, back: Optional[float], lay: Optional[float], sel: int) -> Any:
    ex = SimpleNamespace(
        available_to_back=[{"price": back, "size": 500.0}] if back else [],
        available_to_lay=[{"price": lay, "size": 500.0}] if lay else [])
    md = SimpleNamespace(market_type="MATCH_ODDS", market_time=KO,
                         runners=[SimpleNamespace(selection_id=sel, sort_priority=1)])
    return SimpleNamespace(
        market_id="1.234", status="OPEN", inplay=False, publish_time_epoch=pt,
        market_definition=md, total_matched=100000.0,
        runners=[SimpleNamespace(selection_id=sel, status="ACTIVE", ex=ex,
                                 last_price_traded=back or lay, total_matched=1000.0)])


def _proposte(eventi: List[Any]) -> List[dict]:
    return [p for k, p in eventi if k == "uscita_proposta"]


def _viva(s: Any, motivo: str) -> Optional[dict]:
    return next((p for p in s.stats.get("uscite_proposte", []) if p["motivo"] == motivo),
                None)


def _numeri_pieni(p: dict) -> None:
    for k in UM.CHIAVI_NUMERI_CHIUSURA:
        assert p.get(k) is not None, (k, p)
    assert UM.difetti_proposta(p) == []


# ---------------------------------------------------------------- scalper (tennis e calcio)
def _in_locking(tipo: str):
    """Posizione BACK 2,00 @2,22 abbinata, uscite MANUALI, chiusura a target
    proposta (slot in LOCKING senza close): come `_ts` / `_in_stop` delle suite."""
    ev: List[Any] = []
    if tipo == "tennis":
        from Betfair.stream.tennis_scalper.tennis_scalper_bot import (LOCKING,
                                                                     TennisScalperStrategy)
        s = TennisScalperStrategy(market_filter={}, scalper_params={
            "dry_run": False, "stake": 2.0, "stop_ticks": 2},
            event_sink=lambda k, p: ev.append((k, p)))
        s.uscite_automatiche = False
    else:
        from Betfair.stream.scalper.scalper_bot import LOCKING, ScalperStrategy
        s = ScalperStrategy(market_filter={}, scalper_params={
            "dry_run": False, "stake": 2.0, "stop_ticks": 2,
            "uscite_automatiche": False},
            event_sink=lambda k, p: ev.append((k, p)))
    m = _FakeMarket()
    slot = s._slot("1.234", 42)
    slot.entry = _FakeOrder("BACK", price=2.22, size=2.0, size_matched=2.0, avg=2.22)
    slot.entry_side = "BACK"
    s._open_lock(m, slot, T0 - 1_000, slot.entry, 2.22, 2.24)
    assert slot.status == LOCKING and slot.close is None
    return ev, s, m, slot


@pytest.mark.parametrize("tipo", ["tennis", "calcio"])
def test_stop_senza_lato_di_chiusura_mai_visto_lo_dichiara(tipo):
    ev, s, m, slot = _in_locking(tipo)
    # il best back sale a 2,30 (stop a 2 tick) e il lato LAY e' VUOTO
    s.process_market_book(m, _book(T0, 2.30, None, 42))
    p = _viva(s, "stop")
    assert p is not None, s.stats.get("uscite_proposte")
    motivo = p.get(CHIAVE_NUMERI_NON_DISPONIBILI)
    assert isinstance(motivo, str) and "LAY" in motivo
    assert p["prezzo"] is None and p["size_chiusura"] is None
    assert UM.difetti_proposta(p) == [], "dichiarato: UM2 lo accetta"
    assert m.orders == []


@pytest.mark.parametrize("tipo", ["tennis", "calcio"])
def test_stop_senza_lato_usa_l_ultimo_prezzo_visto_e_si_aggiorna_col_vivo(tipo):
    ev, s, m, slot = _in_locking(tipo)
    s.process_market_book(m, _book(T0, 2.22, 2.24, 42))          # lato LAY visto
    assert _viva(s, "stop") is None
    s.process_market_book(m, _book(T0 + 7_000, 2.30, None, 42))  # stop, LAY vuoto
    p = _viva(s, "stop")
    assert p is not None
    _numeri_pieni(p)
    assert p["prezzo"] == 2.24 and p[CHIAVE_ETA_PREZZO] == 7.0
    assert CHIAVE_NUMERI_NON_DISPONIBILI not in p
    nati = len(_proposte(ev))
    # torna il prezzo vivo: stessa chiave, numeri nuovi, nessuna riga in piu'
    s.process_market_book(m, _book(T0 + 8_000, 2.30, 2.32, 42))
    q = _viva(s, "stop")
    assert q["chiave"] == p["chiave"] and q["decided_at"] == p["decided_at"]
    assert q["prezzo"] == 2.32 and CHIAVE_ETA_PREZZO not in q
    _numeri_pieni(q)
    assert q["size_chiusura"] != p["size_chiusura"] or q["se_chiudi"] != p["se_chiudi"]
    assert len(_proposte(ev)) == nati
    assert m.orders == [], "a uscite manuali niente parte"


# ---------------------------------------------------------------- sniper
def test_sniper_timeout_senza_lato_usa_l_ultimo_prezzo_e_si_aggiorna():
    from Betfair.stream.tests.test_sniper_bot_2026_07_10 import _book as sbook
    from Betfair.stream.tests.test_sniper_uscite_automatiche_2026_09_28 import _in_posizione

    s, mkt, pos = _in_posizione(max_pos_s=10)
    s.process_market_book(mkt, sbook(605, bb=3.40, bl=3.45, sb=200))   # lato LAY visto
    assert [p for p in s.stats["uscite_proposte"] if p["motivo"] == "timeout"] == []
    s.process_market_book(mkt, sbook(650, bb=3.40, bl=None, sb=200))  # timeout, LAY vuoto
    p = next(p for p in s.stats["uscite_proposte"] if p["motivo"] == "timeout")
    _numeri_pieni(p)
    assert p["prezzo"] == 3.45 and p[CHIAVE_ETA_PREZZO] == 45.0
    s.process_market_book(mkt, sbook(651, bb=3.40, bl=3.50, sb=200))
    q = next(p for p in s.stats["uscite_proposte"] if p["motivo"] == "timeout")
    assert q["chiave"] == p["chiave"] and q["prezzo"] == 3.50
    assert CHIAVE_ETA_PREZZO not in q
    assert len([1 for k, _p in s._test_events if k == "uscita_proposta"
                and _p["motivo"] == "timeout"]) == 1
    assert pos.flattening is False and mkt.orders == []


def test_sniper_timeout_senza_lato_mai_visto_lo_dichiara():
    from Betfair.stream.tests.test_sniper_bot_2026_07_10 import _book as sbook
    from Betfair.stream.tests.test_sniper_uscite_automatiche_2026_09_28 import _in_posizione

    s, mkt, _pos = _in_posizione(max_pos_s=10)
    s.process_market_book(mkt, sbook(650, bb=3.40, bl=None, sb=200))
    p = next(p for p in s.stats["uscite_proposte"] if p["motivo"] == "timeout")
    assert isinstance(p.get(CHIAVE_NUMERI_NON_DISPONIBILI), str)
    assert UM.difetti_proposta(p) == []


# ---------------------------------------------------------------- UM2
def test_um2_accetta_i_numeri_mancanti_SOLO_se_dichiarati():
    base = dict(UM.CHIAVI_PROPOSTA and {k: 1 for k in UM.CHIAVI_PROPOSTA})
    vuota = dict(base, prezzo=None, lato_chiusura=None, size_chiusura=None, se_chiudi=None)
    assert UM.difetti_proposta(vuota)                            # non dichiarato: rosso
    assert UM.difetti_proposta(dict(vuota, numeri_non_disponibili="")) != []
    assert UM.difetti_proposta(dict(vuota, numeri_non_disponibili=True)) != []
    assert UM.difetti_proposta(dict(vuota, numeri_non_disponibili="mai visto")) == []
    # la dichiarazione NON copre gli altri numeri obbligatori
    assert UM.difetti_proposta(dict(vuota, numeri_non_disponibili="mai visto",
                                    se_vince=None)) == ["se_vince senza valore"]
