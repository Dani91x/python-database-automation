"""CANTIERE U (29/09/2026): proposte d'uscita con importo di chiusura 0,00.

Reperto del replay 35794049 (tennis_pro, scenario `uscite-manuali-firmate`):
dopo il primo trade chiuso resta sulla selezione un residuo di centesimi
(BACK 2,06 @1,06 + LAY 2,00 @1,09: se vince -0,056 / se perde -0,060). I bot
tennis leggono la posizione sommando TUTTI i loro ordini della selezione, e il
trade NUOVO, con l'ingresso ancora in coda, sembrava "abbinato": nascevano
scaglione / target / strutturale con `size_chiusura` 0,00, e la firma chiudeva
il trade nuovo (annullando l'ingresso) senza mandare nessun ordine.

Regole provate qui, tutte dal bot VERO via `process_market_book`:
  * niente di piazzabile da chiudere -> nessuna proposta, nessuna uscita;
  * l'ingresso nuovo non abbinato sopra il residuo si gestisce come tale
    (resta in coda; al timeout si cancella e si sorveglia);
  * con una posizione vera l'importo della proposta e' quello che parte alla
    firma (stessa funzione);
  * il controllo UM2 del banco tratta `size_chiusura` <= 0 come numero mancante.

I finti degli ordini hanno le chiavi e i tipi del `BetfairOrder` di flumine che
i bot leggono (`id`, `selection_id`, `side`, `size_matched`,
`average_price_matched`, `size_remaining`, `status` come Enum `OrderStatus`,
`order_type.price/size`).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from flumine.order.order import OrderStatus
from flumine.utils import price_ticks_away

from Betfair.stream.backtest.uscite_manuali import difetti_proposta
from Betfair.stream.tennis_scalper.tennis_pro_bot import CLOSING, OPEN
from Betfair.stream.tennis_scalper.tennis_scalper_bot import green_piazzabile
from Betfair.stream.tennis_scalper.tennis_score import TennisScore
from Betfair.stream.tennis_scalper.tennis_swing_bot import _tki
from Betfair.stream.tennis_scalper.tests import test_tennis_flb_hybrid as FH
from Betfair.stream.tennis_scalper.tests import test_tennis_pro_staged as PS
from Betfair.stream.tennis_scalper.tests import test_tennis_swing as SW


class _Ordine:
    """Le chiavi del `BetfairOrder` che i bot leggono, coi tipi veri."""

    _n = 0

    def __init__(self, sel, side, size, price, matched, status):
        _Ordine._n += 1
        self.id = "u%d" % _Ordine._n
        self.selection_id = sel
        self.side = side
        self.size_matched = float(matched)
        self.average_price_matched = float(price) if matched else 0.0
        self.size_remaining = float(size) - float(matched) \
            if status in (OrderStatus.EXECUTABLE, OrderStatus.PENDING) else 0.0
        self.status = status
        self.order_type = SimpleNamespace(price=float(price), size=float(size))


def _chiuso(sel, side, size, price):
    return _Ordine(sel, side, size, price, size, OrderStatus.EXECUTION_COMPLETE)


def _in_coda(sel, side, size, price):
    return _Ordine(sel, side, size, price, 0.0, OrderStatus.EXECUTABLE)


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


# ---------------------------------------------------------------- PRO
def _residuo_pro():
    """Il residuo VERO del replay 35794049 (primo trade chiuso)."""
    return [_chiuso(111, "BACK", 2.06, 1.06), _chiuso(111, "LAY", 2.00, 1.09)]


def _pro(auto: bool, *, ingresso, entry_games=(1, 0, 0, 0)):
    s = PS._make(staged=True, staged_frac=0.4)
    s.uscite_automatiche = auto
    s.score = TennisScore(event_id="1", server="home", point_home="15", point_away="0")
    m = PS._Market(PS._Blotter(_residuo_pro() + [ingresso]))
    entry = 1.11
    s._trade["1.1"] = {
        "state": OPEN, "sel": 111, "side": "BACK", "entry": entry,
        "target": price_ticks_away(entry, -5), "stop": price_ticks_away(entry, 3),
        "kind": "break_point", "staged_done": False, "staged_order": None,
        "order": ingresso, "wait": 0, "t_open": 1_000, "entry_games": entry_games}
    return s, m


def _book(back, lay, pt):
    mb = PS._MB([PS._Runner(111, (back, 100), (lay, 100))])
    mb.publish_time_epoch = pt
    return mb


def test_pro_residuo_di_centesimi_e_ingresso_in_coda_nessuna_proposta_a_zero():
    """Il caso del replay: scaglione (2 tick a favore) e strutturale (game
    cambiato) decisi su un residuo che a 1,09 vale 0,0033 EUR di chiusura."""
    ingresso = _in_coda(111, "BACK", 2.0, 1.11)
    s, m = _pro(False, ingresso=ingresso)
    s.process_market_book(m, _book(1.08, 1.09, 2_000))
    zero = [p for p in s.stats.get("uscite_proposte", [])
            if not (p.get("size_chiusura") or 0) > 0]
    assert zero == [], "proposta con importo 0,00: %s" % zero
    assert s.stats.get("uscite_proposte", []) == []
    assert s._trade["1.1"]["state"] == OPEN and m.placed == [] and m.cancelled == []


def test_pro_automatico_il_residuo_non_chiude_il_trade_nuovo():
    """A uscite automatiche la stessa decisione chiudeva il trade nuovo:
    `_finish` annullava l'ingresso in coda e lo scaglione veniva "consumato"
    senza nessun ordine."""
    ingresso = _in_coda(111, "BACK", 2.0, 1.11)
    s, m = _pro(True, ingresso=ingresso)
    s.process_market_book(m, _book(1.08, 1.09, 2_000))
    t = s._trade["1.1"]
    assert t["state"] == OPEN and t["staged_done"] is False
    assert ingresso not in m.cancelled and m.placed == []


def test_pro_ingresso_in_coda_sopra_il_residuo_scade_al_timeout():
    """Senza il riconoscimento dell'ingresso non abbinato, il timeout di 25 s
    non scattava mai (la posizione fantasma lo saltava)."""
    ingresso = _in_coda(111, "BACK", 2.0, 1.11)
    s, m = _pro(False, ingresso=ingresso, entry_games=None)
    s.process_market_book(m, _book(1.11, 1.12, 1_000 + 26_000))
    assert s._trade["1.1"]["state"] == CLOSING
    assert ingresso in m.cancelled


def test_pro_ingresso_morto_sopra_il_residuo_libera_il_game():
    ingresso = _Ordine(111, "BACK", 2.0, 1.11, 0.0, OrderStatus.EXECUTION_COMPLETE)
    s, m = _pro(False, ingresso=ingresso, entry_games=None)
    s.process_market_book(m, _book(1.11, 1.12, 2_000))
    assert s._trade["1.1"]["state"] == "FLAT"


def test_pro_posizione_vera_la_firma_manda_l_importo_della_proposta():
    """Ingresso nuovo ABBINATO sopra il residuo: la proposta porta un importo
    vero, e alla firma `_place` riceve esattamente quel numero."""
    ingresso = _chiuso(111, "BACK", 2.0, 1.11)
    s, m = _pro(False, ingresso=ingresso, entry_games=None)
    s.process_market_book(m, _book(1.08, 1.09, 2_000))
    props = s.stats["uscite_proposte"]
    sc = next(p for p in props if p["motivo"] == "scaglione")
    b, ba, l, la = s._position(m, 111)
    atteso = green_piazzabile(*s._net(b, ba, l, la), 1.09, 0.4)
    assert sc["size_chiusura"] == atteso[1] and sc["size_chiusura"] > 0
    s.cancello_uscite.approva({sc["chiave"]: _iso(2_500)})
    chiamate = []
    vero = s._place

    def spia(market, sel, side, price, size, **kw):
        chiamate.append((side, round(float(size), 2), kw.get("copertura", False)))
        return vero(market, sel, side, price, size, **kw)
    s._place = spia
    s.process_market_book(m, _book(1.08, 1.09, 3_000))
    uscite = [c for c in chiamate if c[2]]
    assert uscite and uscite[0][0] == sc["lato_chiusura"]
    assert uscite[0][1] == sc["size_chiusura"], (uscite, sc)


def test_pro_scaglione_sotto_il_centesimo_non_diventa_proposta():
    """Posizione VERA ma piccola (abbinato 0,01 a 1,11): la chiusura totale vale
    0,01, il 40% dello scaglione 0,004 -> 0,00. Lo scaglione non si propone
    (alla firma non partirebbe niente); le altre uscite restano."""
    s = PS._make(staged=True, staged_frac=0.4)
    s.uscite_automatiche = False
    m = PS._Market(PS._Blotter([_chiuso(111, "BACK", 0.01, 1.11)]))
    entry = 1.11
    s._trade["1.1"] = {
        "state": OPEN, "sel": 111, "side": "BACK", "entry": entry,
        "target": price_ticks_away(entry, -5), "stop": price_ticks_away(entry, 3),
        "kind": "break_point", "staged_done": False, "staged_order": None,
        "order": None, "wait": 0, "t_open": 1_000, "entry_games": None}
    s.process_market_book(m, _book(1.08, 1.09, 2_000))
    assert [p for p in s.stats.get("uscite_proposte", [])
            if p["motivo"] == "scaglione"] == []
    assert all(p["size_chiusura"] > 0 for p in s.stats.get("uscite_proposte", []))


# ---------------------------------------------------------------- SWING
def test_swing_residuo_di_centesimi_nessuna_proposta_a_zero():
    """Residuo: BACK 2,00 @1,50 coperto con LAY 1,85 @1,62 (se vince -0,147 /
    se perde -0,150); trade nuovo con l'ingresso in coda; stop deciso."""
    ingresso = _in_coda(111, "BACK", 2.0, 1.50)
    s = SW._make(uscite_automatiche=False, stop_ticks=2, maker=False, tmax=10_000)
    m = SW._Market(SW._Blotter([_chiuso(111, "BACK", 2.0, 1.50),
                                _chiuso(111, "LAY", 1.85, 1.62), ingresso]))
    s._tr["1.1"] = {"sel": 111, "side": "BACK", "etk": _tki(1.50),
                    "anchor": _tki(1.40), "order": ingresso, "held": 0,
                    "wait": 0, "t0": 1_000}
    s.process_market_book(m, SW._MB([SW._Runner(111, (1.60, 100), (1.62, 100),
                                                 ltp=1.61)], pt=2_000))
    assert s.stats.get("uscite_proposte", []) == []
    assert m.placed == [] and ingresso not in m.cancelled and "1.1" in s._tr


def test_swing_ingresso_in_coda_sopra_il_residuo_scade_al_timeout():
    ingresso = _in_coda(111, "BACK", 2.0, 1.50)
    s = SW._make(uscite_automatiche=False, stop_ticks=2, maker=False, tmax=10_000)
    m = SW._Market(SW._Blotter([_chiuso(111, "BACK", 2.0, 1.50),
                                _chiuso(111, "LAY", 1.85, 1.62), ingresso]))
    s._tr["1.1"] = {"sel": 111, "side": "BACK", "etk": _tki(1.50),
                    "anchor": _tki(1.40), "order": ingresso, "held": 0,
                    "wait": 0, "t0": 1_000}
    s.process_market_book(m, SW._MB([SW._Runner(111, (1.50, 100), (1.51, 100),
                                                 ltp=1.50)], pt=1_000 + 41_000))
    assert s._tr["1.1"].get("closing") is True and ingresso in m.cancelled


# ---------------------------------------------------------------- FLB
def _flb_residuo(ingresso, auto=False):
    """Modalita' "green": la selezione torna DONE e si ri-arma. Residuo: LAY
    2,00 @1,05 coperto con BACK 1,96 @1,07; ingresso nuovo in coda."""
    from Betfair.stream.tennis_scalper.tennis_flb_bot import TennisFLBStrategy
    s = TennisFLBStrategy(
        market_filter=FH.filters.streaming_market_filter(market_ids=["1.1"]),
        flb_params={"exit_mode": "green", "green_ticks": 2, "lay_max": 1.10,
                    "min_lay_size": 5.0, "dry_run": False, "entry_timeout": 3})
    s.uscite_automatiche = auto
    m = FH._Market()
    m.blotter.orders.extend([_chiuso(111, "LAY", 2.0, 1.05),
                             _chiuso(111, "BACK", 1.96, 1.07), ingresso])
    s._pos_state[("1.1", 111)] = {"state": "OPEN", "entry": 1.05, "order": ingresso,
                                  "wait": 0, "greened": False, "t0": None}
    return s, m


def _flb_book():
    return FH._MB([FH._Runner(111, (1.07, 200), (1.08, 200), ltp=1.07)])


def test_flb_ritorno_sulla_selezione_nessun_green_a_zero():
    ingresso = _in_coda(111, "LAY", 2.0, 1.05)
    s, m = _flb_residuo(ingresso)
    s.process_market_book(m, _flb_book())
    assert s.stats.get("uscite_proposte", []) == []
    assert m.placed == [] and s._pos_state[("1.1", 111)]["greened"] is False


def test_flb_ingresso_in_coda_sopra_il_residuo_scade_al_timeout():
    """In automatico il green sul residuo "consumava" il green (greened=True
    senza ordine); qui l'ingresso nuovo resta tale e scade al timeout."""
    ingresso = _in_coda(111, "LAY", 2.0, 1.05)
    s, m = _flb_residuo(ingresso, auto=True)
    for _ in range(5):
        s.process_market_book(m, _flb_book())
    assert s._pos_state[("1.1", 111)]["state"] == "PENDING"
    assert m.placed == []
    # il residuo non si scambia per un "cancel perso" (riapertura e secondo cancel)
    assert m.cancelled.count(ingresso) == 1, m.cancelled


# ------------------------------------- v2 (revisione del coordinatore, 29/09)
def test_pro_il_lato_del_prezzo_decide_niente_da_chiudere():
    """M12: residuo con sbilancio 0,0052 (BACK 2,00 @1,06 + LAY 2,00 a media
    1,0574) e spread largo (1,01 / 1,10). Per un trade BACK l'uscita e' al
    best-lay: 0,0052/1,10 = 0,0047 -> 0,00, niente da chiudere; al best-back
    sarebbe 0,0052/1,01 = 0,0051 -> 0,01. Con il lato giusto l'ingresso nuovo
    (morto, 0 abbinato) libera il trade; col lato sbagliato il trade resta
    OPEN su una posizione fantasma."""
    ingresso = _Ordine(111, "BACK", 2.0, 1.11, 0.0, OrderStatus.EXECUTION_COMPLETE)
    s = PS._make(staged=True, staged_frac=0.4)
    s.uscite_automatiche = False
    m = PS._Market(PS._Blotter([_chiuso(111, "BACK", 2.0, 1.06),
                                _chiuso(111, "LAY", 2.0, 1.0574), ingresso]))
    entry = 1.11
    s._trade["1.1"] = {
        "state": OPEN, "sel": 111, "side": "BACK", "entry": entry,
        "target": price_ticks_away(entry, -5), "stop": price_ticks_away(entry, 3),
        "kind": "break_point", "staged_done": False, "staged_order": None,
        "order": ingresso, "wait": 0, "t_open": 1_000, "entry_games": None}
    s.process_market_book(m, _book(1.01, 1.10, 2_000))
    assert s._trade["1.1"]["state"] == "FLAT"


def test_swing_dry_run_uscita_sotto_il_centesimo_non_diventa_proposta():
    """M7: `_esce`/`_cancello_lascia` dello swing con una posizione sotto il
    centesimo. Fuori dal dry-run il punto NON e' raggiungibile: il ramo
    `vuota` di `_manage_trade` usa lo stesso prezzo (`px_uscita` = `px`) e la
    stessa `green_piazzabile` senza frazione. In dry-run la posizione e'
    virtuale (stake 2,00 @ prezzo d'ingresso) e il ramo `vuota` e' spento: con
    ingresso 1,01 e uscita a 1000 la chiusura vale 2,02/1000 = 0,002 -> 0,00."""
    s = SW._make(uscite_automatiche=False, stop_ticks=2, maker=False, tmax=10_000,
                 dry_run=True)
    m = SW._Market(SW._Blotter([]))
    s._tr["1.1"] = {"sel": 111, "side": "BACK", "etk": _tki(1.01),
                    "anchor": _tki(1.01), "order": None, "held": 0,
                    "wait": 0, "t0": 1_000, "px": 1.01}
    s.process_market_book(m, SW._MB([SW._Runner(111, (990.0, 100), (1000.0, 100),
                                                 ltp=995.0)], pt=2_000))
    assert s.stats.get("uscite_proposte", []) == [], s.stats.get("uscite_proposte")
    assert m.placed == []


def _flb_ibrido(ingresso, auto):
    """Hybrid, green al 50%: abbinato VERO 0,01 (fill parziale) di un LAY a
    1,05. Green totale a 1,07 = 0,0098 -> 0,01 (il ramo `vuota` NON scatta);
    il green al 50% = 0,0049 -> 0,00: niente da piazzare."""
    from Betfair.stream.tennis_scalper.tennis_flb_bot import TennisFLBStrategy
    s = TennisFLBStrategy(
        market_filter=FH.filters.streaming_market_filter(market_ids=["1.1"]),
        flb_params={"exit_mode": "hybrid", "green_ticks": 2, "green_frac": 0.5,
                    "lay_max": 1.10, "min_lay_size": 5.0, "dry_run": False})
    s.uscite_automatiche = auto
    m = FH._Market()
    m.blotter.orders.append(ingresso)
    s._pos_state[("1.1", 111)] = {"state": "OPEN", "entry": 1.05, "order": ingresso,
                                  "wait": 0, "greened": False, "t0": None}
    return s, m


def test_flb_green_frazionato_sotto_il_centesimo_non_diventa_proposta():
    """M10, uscite manuali."""
    ingresso = _Ordine(111, "LAY", 2.0, 1.05, 0.01, OrderStatus.EXECUTABLE)
    s, m = _flb_ibrido(ingresso, auto=False)
    s.process_market_book(m, _flb_book())
    assert s.stats.get("uscite_proposte", []) == [], s.stats.get("uscite_proposte")
    assert m.placed == []


def test_flb_green_frazionato_sotto_il_centesimo_non_consuma_il_green():
    """M10, uscite automatiche: il green non parte e non si segna fatto."""
    ingresso = _Ordine(111, "LAY", 2.0, 1.05, 0.01, OrderStatus.EXECUTABLE)
    s, m = _flb_ibrido(ingresso, auto=True)
    s.process_market_book(m, _flb_book())
    assert s._pos_state[("1.1", 111)]["greened"] is False and m.placed == []


# ---------------------------------------------------------------- UM2 del banco
@pytest.mark.parametrize("size", [0.0, 0, -0.01])
def test_um2_importo_a_zero_e_numero_mancante(size):
    p = {"bot": "tennis_pro", "motivo": "scaglione", "urgente": False,
         "market_id": "1.1", "selection_id": 111, "lato_ingresso": "BACK",
         "prezzo": 1.09, "lato_chiusura": "LAY", "size_chiusura": size,
         "se_chiudi": -0.023, "se_vince": -0.056, "se_perde": -0.06,
         "chiave": "k", "decided_at": 1.0}
    assert any("size_chiusura" in d for d in difetti_proposta(p))
    p["numeri_non_disponibili"] = "dichiarato"
    assert any("size_chiusura" in d for d in difetti_proposta(p)), \
        "uno zero non e' un numero assente: la dichiarazione non lo scusa"


def test_um2_importo_vero_passa():
    p = {"bot": "tennis_pro", "motivo": "scaglione", "urgente": False,
         "market_id": "1.1", "selection_id": 111, "lato_ingresso": "BACK",
         "prezzo": 1.09, "lato_chiusura": "LAY", "size_chiusura": 0.01,
         "se_chiudi": -0.023, "se_vince": -0.056, "se_perde": -0.06,
         "chiave": "k", "decided_at": 1.0}
    assert difetti_proposta(p) == []


def test_green_piazzabile_e_il_centesimo_di_place():
    assert green_piazzabile(-0.0564, -0.06, 1.09) is None          # 0,0033
    assert green_piazzabile(-0.0564, -0.06, 1.09, 0.4) is None
    g = green_piazzabile(0.6, -1.0, 1.60)                          # 1,00
    assert g is not None and g[0] == "LAY" and g[1] == 1.0
    assert green_piazzabile(0.6, -1.0, None) is None
