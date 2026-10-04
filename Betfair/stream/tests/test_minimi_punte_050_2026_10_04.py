"""04/10/2026 - LA REGOLA DELLE PUNTE (BACK) DI BETFAIR .it NEL MOTORE CONDIVISO E NEL BANCO.

Fatto (Umea FC v Hammarby, LIVE, soldi veri): Mike ha mandato via API una PUNTA Under 4,5
da 7,27 @1,07 per chiudere la copertura: Betfair ha risposto ``INVALID_BET_SIZE``. Il
01/10 ``minimi_it`` aveva tolto il passo di 0,50 delle punte sulla prova di un ordine
messo dall'UTENTE dal sito (Cash Out), non dal bot; il banco simulava la stessa regola
sbagliata e i replay erano verdi.

Regola dell'utente (testuale): «SOTTO 1 EURO si usa place and trim (0.50 il minimo),
SOPRA 1 EURO i MULTIPLI DI 0.50 FUNZIONANO, IN BACK». Arrotondamento: per DIFETTO.

Cosa certifica:
  * ``minimi_it.importo_piazzabile``: la tabella completa (punta, banca, sotto 1,00,
    sotto 0,50, input non validi);
  * ``min_stake_rules`` / ``verdetto_minimi`` / ``build_order``: la punta 7,27 parte
    7,00 col residuo 0,27 DICHIARATO (verdetto, ``BuiltOrder.residuo``, nota); la
    banca invariata al centesimo (6,32 / 5,07 / 6,23);
  * ``trading.submin.pianifica_submin``: il place normale di una punta parte a 7,00;
  * motore del canale VERO: in paper e in live la stessa riga 7,00 mandata, e ogni
    evento al bot porta ``punta_050`` (chiesto, piazzato, residuo);
  * banco (exchange simulato di flumine VERO sulla registrazione 35760084): una punta
    diretta 7,27 e' rifiutata ``INVALID_BET_SIZE``, 7,00 passa; a regola spenta
    (falsificazione) 7,27 si abbina e il controllo ``abbinati_sotto_minimo`` lo trova.

Finti: nessuno nuovo. Motore, canale, client e ordini flumine VERI (fixture ``amb`` di
``test_motore_ordini_2026_09_24``); banco vero (``trasporto_rapido.BancoRapido``).
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from flumine import BaseStrategy

from Betfair.stream import live_order_build as LB
from Betfair.stream.tests.test_motore_ordini_2026_09_24 import (  # noqa: F401 - fixture
    _ack,
    _cmd,
    _manda,
    amb,
)
from Betfair.stream.trading import minimi_it as MI
from Betfair.stream.trading import submin as S

_STRAT = BaseStrategy(market_filter={}, name="punte_050_test")
UNDER = 47973


# ===========================================================================
# 1. la regola UNICA (minimi_it)
# ===========================================================================
@pytest.mark.parametrize("lato,chiesto,via,importo,residuo", [
    ("back", 7.27, MI.VIA_DIRETTA, 7.00, 0.27),       # Umea, 04/10
    ("back", 7.47, MI.VIA_DIRETTA, 7.00, 0.47),
    ("back", 7.50, MI.VIA_DIRETTA, 7.50, 0.00),
    ("back", 1.00, MI.VIA_DIRETTA, 1.00, 0.00),
    ("back", 1.49, MI.VIA_DIRETTA, 1.00, 0.49),
    ("back", 1.50, MI.VIA_DIRETTA, 1.50, 0.00),
    ("back", 12.99, MI.VIA_DIRETTA, 12.50, 0.49),
    ("back", 0.99, MI.VIA_PLACE_AND_TRIM, 0.99, 0.00),
    ("back", 0.50, MI.VIA_PLACE_AND_TRIM, 0.50, 0.00),
    ("back", 0.49, MI.VIA_NESSUNA, 0.00, 0.49),
    ("lay", 6.32, MI.VIA_DIRETTA, 6.32, 0.00),        # banche del bot accettate
    ("lay", 5.07, MI.VIA_DIRETTA, 5.07, 0.00),
    ("lay", 6.23, MI.VIA_DIRETTA, 6.23, 0.00),
    ("lay", 1.00, MI.VIA_DIRETTA, 1.00, 0.00),
    ("lay", 0.60, MI.VIA_PLACE_AND_TRIM, 0.60, 0.00),
    ("lay", 0.43, MI.VIA_NESSUNA, 0.00, 0.43),
])
def test_importo_piazzabile_tabella(lato, chiesto, via, importo, residuo):
    v = MI.importo_piazzabile(lato, chiesto)
    assert (v.via, v.chiesto, v.importo, v.residuo) == (via, chiesto, importo, residuo)
    assert round(v.importo + v.residuo, 2) == chiesto


@pytest.mark.parametrize("cattivo", [None, "x", float("nan"), float("inf"), 0, -1.0])
def test_importo_piazzabile_input_non_validi_nessun_ordine(cattivo):
    v = MI.importo_piazzabile("back", cattivo)
    assert v.via == MI.VIA_NESSUNA and v.importo == 0.0


def test_importo_piazzabile_lato_non_valido_solleva():
    with pytest.raises(ValueError):
        MI.importo_piazzabile("BACKX", 7.27)


def test_punta_diretta_valida_e_costanti():
    assert MI.IT_PASSO_PUNTA_DIRETTA == 0.50 == MI.IT_PASSO_PUNTA_RIPIEGO
    assert MI.IT_MIN_BACK == MI.IT_MIN_LAY == 1.00
    assert MI.punta_diretta_valida(7.00) and MI.punta_diretta_valida(1.50)
    assert not MI.punta_diretta_valida(7.27) and not MI.punta_diretta_valida(0.50)
    # la docstring non porta piu' la prova sbagliata come prova
    assert "Cash Out" in MI.__doc__ and "PERCHE' LA VERSIONE DEL 01/10 ERA SBAGLIATA" in MI.__doc__


# ===========================================================================
# 2. il motore condiviso: verdetto, build_order, submin
# ===========================================================================
def test_min_stake_rules_punta_a_difetto_banca_invariata():
    v = LB.min_stake_rules("it", "back", 1.07, 7.27)
    assert v.valid and v.legalized_size == 7.00 and v.residuo == 0.27
    v2 = LB.min_stake_rules("it", "lay", 1.23, 6.32)
    assert v2.valid and v2.legalized_size == 6.32 and v2.residuo == 0.0
    v3 = LB.min_stake_rules("it", "back", 1.07, 0.80)
    assert not v3.valid and v3.reason.startswith(LB.SOTTO_MINIMO_NON_PIAZZABILE)
    # .com invariato (nessun passo)
    assert LB.min_stake_rules("com", "back", 3.0, 7.27).legalized_size == 7.27


def test_verdetto_diretto_porta_il_residuo():
    v = LB.verdetto_minimi("it", "back", 1.07, 7.27)
    assert v.esito == LB.VERDETTO_DIRETTO and v.size == 7.00 and v.residuo == 0.27
    assert LB.verdetto_minimi("it", "lay", 1.22, 6.23).residuo == 0.0


def _costruisci(side: str, price: float, size: float) -> Any:
    return LB.build_order(SimpleNamespace(market_id="1.1"), strategy=_STRAT,
                          selection_id=UNDER, handicap=0.0, side=side, order_type="LIMIT",
                          price=price, size=size, liability=None, persistence="LAPSE",
                          time_in_force="FILL_OR_KILL", min_fill_size=None, jurisdiction="it",
                          max_stake=None, customer_order_ref="p050", reduces_liability=True)


def test_build_order_punta_7_27_parte_7_00_e_lo_dichiara(caplog):
    b = _costruisci("back", 1.07, 7.27)
    assert b.size == 7.00 and b.order.order_type.size == 7.00 and b.residuo == 0.27
    assert "chiesta 7.27, piazzata 7.00, residuo 0.27 NON piazzato" in b.note
    assert any("residuo 0.27" in r.getMessage() for r in caplog.records)
    banca = _costruisci("lay", 1.23, 6.32)
    assert banca.size == 6.32 and banca.residuo == 0.0 and "residuo" not in banca.note


def test_submin_place_normale_della_punta_a_difetto():
    p = S.pianifica_submin(side="back", target_price=1.07, target_size=7.27, jurisdiction="it")
    assert not p.serve_trucco and p.park_size == 7.00 and p.target_size == 7.27
    assert "residuo 0.27 NON piazzato" in p.motivo
    q = S.pianifica_submin(side="lay", target_price=1.23, target_size=6.32, jurisdiction="it")
    assert q.park_size == 6.32 and "residuo" not in q.motivo


# ===========================================================================
# 3. il motore del canale VERO: paper = live, residuo dichiarato in ogni evento
# ===========================================================================
@pytest.mark.parametrize("mode", ["paper", "live"])
def test_motore_punta_7_27_mandata_7_00_con_punta_050(amb, mode):
    ws = amb.ch.collega("mike")
    _manda(amb, ws, _cmd("mike", 1, mode=mode, selection_id=UNDER, side="BACK", price=1.07,
                         size=7.27, reduces_liability=True))
    assert _ack(amb, ws)["accettato"] is True
    ordine, _ref, client = amb.market.calls[-1]
    assert client is (amb.paper if mode == "paper" else amb.reale)
    assert ordine.side == "BACK" and ordine.order_type.size == 7.00
    ev = amb.ch.per_ws(ws, "order")[-1]["d"]
    assert ev["size"] == 7.00
    assert ev["punta_050"]["chiesto"] == 7.27 and ev["punta_050"]["piazzato"] == 7.00
    assert ev["punta_050"]["residuo"] == 0.27
    # la banca della stessa partita (6,23) parte al centesimo, senza dichiarazione
    _manda(amb, ws, _cmd("mike", 2, mode=mode, selection_id=UNDER, side="LAY", price=1.22,
                         size=6.23, reduces_liability=True))
    assert amb.market.calls[-1][0].order_type.size == 6.23
    assert "punta_050" not in amb.ch.per_ws(ws, "order")[-1]["d"]


def test_motore_punta_multipla_nessuna_dichiarazione(amb):
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd("safe", 1, mode="live", price=2.5, size=5.00))
    assert amb.market.calls[-1][0].order_type.size == 5.00
    assert "punta_050" not in amb.ch.per_ws(ws, "order")[-1]["d"]


def test_coda_del_worker_dichiara_il_residuo_nell_esito(monkeypatch):
    """La strada della CODA (``_do_place``, ``build_order`` vero): la riga della coda
    chiede 7,27; parte 7,00 e l'esito scritto porta ``punta_050`` e la nota."""
    from Betfair.stream import live_order_worker as wk
    from Betfair.stream.tests.test_cashout_pro_2026_09_10 import (
        _STRAT as STRAT_CODA,
    )
    from Betfair.stream.tests.test_cashout_pro_2026_09_10 import _fl, _Market, _runner, _Sb

    monkeypatch.setattr(wk, "_jurisdiction", lambda: "it")
    market = _Market("1.1", runners=[_runner(10, 1.07, 1.08)])
    row = {"id": 404, "market_id": "1.1", "selection_id": 10, "handicap": 0, "side": "back",
           "order_type": "LIMIT", "price": 1.07, "size": 7.27, "action": "place",
           "params": {}}
    sb = _Sb([row])
    wk._do_place(sb, _fl(market), row, "live", STRAT_CODA)
    assert [o.order_type.size for o in market.placed] == [7.00]
    esito = row.get("result") or {}
    assert esito.get("punta_050") == {"chiesto": 7.27, "piazzato": 7.0, "residuo": 0.27}
    assert "residuo 0.27 NON piazzato" in str(esito.get("detail") or esito)


# ===========================================================================
# 4. il banco rifiuta come Betfair (exchange simulato di flumine VERO)
# ===========================================================================
EVENTO = "35760084"


def _cartella_registrazioni() -> str:
    candidati = [os.getenv("LIVE_STREAM_DATA_DIR") or ""]
    radice = Path(__file__).resolve().parents[3]
    candidati += [str(radice / "_live_raw"), str(radice.parents[2] / "_live_raw")]
    for c in candidati:
        if c and os.path.exists(os.path.join(c, EVENTO, "%s.raw.jsonl" % EVENTO)):
            return c
    return ""


@pytest.fixture
def banco():
    if not _cartella_registrazioni():
        pytest.skip("registrazione 35760084 assente su questa macchina")
    from Betfair.stream.backtest import banco_comune as B
    from Betfair.stream.backtest import trasporto_rapido as TRR

    with B.simulazione_flumine():
        b = TRR.BancoRapido("mike", EVENTO, _cartella_registrazioni())
        b.__enter__()
        try:
            assert b.trova_match_odds()
            yield b
        finally:
            b.__exit__(None, None, None)


def _punta(b: Any, size: float, ref: str) -> Any:
    sel, p, _ = b.quota("back")
    return b.mercato_rest.place_order_live(market_id=b.market_id, selection_id=sel, price=p,
                                           size=size, event_id=EVENTO, side="back",
                                           customer_ref=ref)


def test_banco_punta_diretta_7_27_rifiutata_7_00_abbinata(banco, monkeypatch):
    from Betfair.stream.backtest import minimi_banco as MB

    r = _punta(banco, 7.27, "t-727")
    assert r.ok is False and r.error_code == "INVALID_BET_SIZE" and r.size_matched == 0.0
    assert [x["codice"] for x in MB.REGISTRO.rifiutati] == ["INVALID_BET_SIZE"]
    r2 = _punta(banco, 7.00, "t-700")
    assert r2.ok is True and r2.size_matched == 7.00
    assert MB.abbinati_sotto_minimo() == []
    # FALSIFICAZIONE: regola spenta -> 7,27 si abbina e il controllo lo trova
    monkeypatch.setattr(MB, "ATTIVO", False)
    r3 = _punta(banco, 7.27, "t-727b")
    assert r3.ok is True and r3.size_matched == 7.27
    fuori = MB.abbinati_sotto_minimo()
    assert len(fuori) == 1 and fuori[0]["size"] == 7.27


def test_banco_regola_pura_del_passo():
    from Betfair.stream.backtest import minimi_banco as MB

    assert MB.fuori_listino(7.27, MB.DIRETTO, "BACK")
    assert not MB.fuori_listino(7.00, MB.DIRETTO, "BACK")
    assert not MB.fuori_listino(6.23, MB.DIRETTO, "LAY")          # banca al centesimo
    # il sostituto di un replace e il finale del place-and-trim: solo il floor 0,50
    assert not MB.fuori_listino(0.73, MB.SOSTITUZIONE, "BACK")
    assert not MB.fuori_listino(7.27, MB.PLACE_AND_TRIM, "BACK")
    assert MB.fuori_listino(0.43, MB.SOSTITUZIONE, "BACK")
