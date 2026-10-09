"""W1-C1 - parita' di ``nucleo/ordini/minimi.py`` con le CINQUE definizioni di oggi.

Per ogni politica, la funzione nuova e quella di oggi (importata come ARBITRO, mai
modificata) ricevono gli stessi ingressi su una griglia ampia di importi (0,00-12,00 al
centesimo, piu' i casi limite), prezzi e lati; il risultato deve essere IDENTICO (stessa
tupla, stessi testi). Lo scalper si confronta con il ``_place`` VERO delle due strategie
(calcio e tennis) su un mercato doppio: si legge la taglia dell'ordine flumine VERO che
``_place`` costruisce.

Le divergenze FRA le definizioni di oggi sono fotografate in fondo
(``test_divergenze_di_oggi_fotografate``): non si sceglie, si dichiara (referto par. 9).
"""
from __future__ import annotations

import math
from typing import Any, List, Optional, Tuple

import pytest

from Betfair.nucleo.ordini import minimi as NM
from Betfair.stream import live_order_build as LB
from Betfair.stream.trading import minimi_it as MI
from Betfair.stream.trading import submin as SM
from Betfair.stream.tennis_scalper import condotta_ordini as CO
from Betfair.stream.scalper import scalper_bot as SB
from Betfair.stream.tennis_scalper import tennis_scalper_bot as TSB

IMPORTI: List[float] = [round(i * 0.01, 2) for i in range(0, 1201)] + [
    0.001, 0.004, 0.0049, 0.005, 0.0051, 0.495, 0.4999, 0.995, 0.999, 1.004, 1.005,
    1.249, 1.25, 1.251, 7.27, 7.275, 12.345, 99.995, 100.0, 999.99, 10000.0,
    -1.0, -0.01, 1e-9]
PREZZI = (1.01, 1.5, 2.0, 3.45, 10.0, 1000.0)
LATI = ("back", "lay", "BACK", "LAY", "Back", "x", "")


def _esito(fn: Any, *a: Any, **k: Any) -> Tuple[str, Any]:
    """(ok, valore) o (eccezione, tipo e testo): anche le eccezioni devono coincidere."""
    try:
        return "ok", fn(*a, **k)
    except Exception as ex:  # noqa: BLE001 - confrontata, non inghiottita
        return "eccezione", (type(ex).__name__, str(ex))


def test_regola_it_e_la_stessa_funzione() -> None:
    # nessuna copia: la regola dei numeri E' quella di minimi_it
    assert NM.importo_piazzabile is MI.importo_piazzabile
    assert NM.IT_MIN_BACK is MI.IT_MIN_BACK and NM.IT_MIN_LAY is MI.IT_MIN_LAY


def test_runner_parita_con_min_stake_rules() -> None:
    n = 0
    for lato in LATI:
        for prezzo in PREZZI:
            for imp in IMPORTI + [float("nan"), float("inf")]:
                vecchio = LB.min_stake_rules(LB.JURISDICTION_IT, lato, prezzo, imp)
                nuovo = NM.verdetto_runner(lato, imp)
                assert (vecchio.valid, vecchio.legalized_size, vecchio.reason,
                        vecchio.residuo) == (nuovo.valid, nuovo.legalized_size,
                                             nuovo.reason, nuovo.residuo), (lato, prezzo, imp)
                n += 1
    assert n > 50_000


@pytest.mark.parametrize("submin", [True, False])
def test_verdetto_porta_parita_con_verdetto_minimi(submin: bool) -> None:
    for lato in LATI:
        for prezzo in PREZZI:
            for imp in IMPORTI + [float("nan"), float("inf")]:
                vecchio = _esito(LB.verdetto_minimi, LB.JURISDICTION_IT, lato, prezzo, imp,
                                 altra_selezione=None, submin_disponibile=submin)
                nuovo = _esito(NM.verdetto_porta, lato, prezzo, imp,
                               submin_disponibile=submin)
                if vecchio[0] == "ok":
                    v = vecchio[1]
                    assert v.equivalente is None and v.altra_selezione is None
                    vecchio = ("ok", (v.esito, v.size, v.motivo, v.residuo))
                if nuovo[0] == "ok":
                    n = nuovo[1]
                    nuovo = ("ok", (n.esito, n.size, n.motivo, n.residuo))
                assert nuovo == vecchio, (lato, prezzo, imp, submin)


def test_porta_al_minimo_parita_con_submin() -> None:
    for lato in LATI:
        for imp in IMPORTI:
            assert _esito(NM.porta_al_minimo, lato, imp) == \
                _esito(SM.porta_al_minimo_apertura, "it", lato, imp), (lato, imp)


@pytest.mark.parametrize("live", [True, False])
@pytest.mark.parametrize("riduce", [True, False])
def test_size_legale_parita_con_condotta(live: bool, riduce: bool) -> None:
    for lato in LATI:
        for imp in IMPORTI:
            vecchio = _esito(CO.size_legale, imp, lato, live=live, riduce_liability=riduce)
            nuovo = _esito(NM.size_legale_tennis, imp, lato, live=live, riduce=riduce)
            assert vecchio == nuovo, (lato, imp, live, riduce)


def test_diretta_e_spezza_tennis_parita_con_condotta() -> None:
    for lato in LATI:
        for imp in IMPORTI:
            assert NM.diretta_ok_tennis(imp, lato) == CO.diretta_ok(imp, lato), (lato, imp)
            assert _esito(NM.spezza_esatta_tennis, imp, lato) == \
                _esito(CO.spezza_esatta, imp, lato), (lato, imp)


def test_spezza_uscita_parita_con_lo_scalper() -> None:
    for lato in LATI:
        for prezzo in PREZZI:
            for imp in IMPORTI:
                assert _esito(NM.spezza_uscita_scalper, lato, imp) == \
                    _esito(SB.spezza_uscita, lato, prezzo, imp), (lato, prezzo, imp)


def test_soglia_safe_parita_con_min_size_live(monkeypatch: pytest.MonkeyPatch) -> None:
    from Betfair.safe_strategy import execution as EX

    for grezzo in ("", "  ", "0.7", "2", "-3", "abc", "1,5"):
        monkeypatch.setenv("SAFE_MIN_SIZE_LIVE", grezzo)
        for lato in ("back", "lay", "LAY", "x"):
            assert NM.soglia_safe(lato, grezzo) == EX._min_size_live(lato), (grezzo, lato)
    monkeypatch.delenv("SAFE_MIN_SIZE_LIVE", raising=False)
    assert NM.soglia_safe("lay") == EX._min_size_live("lay")


# ---------------------------------------------------------------------------
# lo scalper: il _place VERO delle due strategie, su un mercato doppio
# ---------------------------------------------------------------------------
class _Mercato:
    """Il minimo che ``_place`` legge: ``market_id``, ``place_order`` (bool come flumine),
    ``blotter``. Registra l'ordine flumine VERO che riceve."""

    def __init__(self) -> None:
        self.market_id = "1.234"
        self.blotter: List[Any] = []
        self.ordini: List[Any] = []

    def place_order(self, order: Any, *_a: Any, **_k: Any) -> bool:
        self.ordini.append(order)
        return True


def _strategia(variante: str, *, size_step: float, live_min_bet: float,
               exact_exits: bool) -> Any:
    params = {"size_step": size_step, "live_min_bet": live_min_bet,
              "exact_exits": exact_exits, "dry_run": False, "max_txn_hour": 0}
    if variante == "calcio":
        s = SB.ScalperStrategy(market_filter={}, scalper_params=params)
    else:
        s = TSB.TennisScalperStrategy(market_filter={}, scalper_params=params)
    # i valori della sessione, letti DOPO il costruttore (stesse chiavi dei bot)
    s.size_step, s.live_min_bet, s.exact_exits, s.dry_run = (
        size_step, live_min_bet, exact_exits, False)
    s.max_txn_hour = 0
    s.freno_live = None
    return s


def _taglia_vera(strat: Any, mercato: _Mercato, lato: str, prezzo: float, imp: float,
                 ingresso: bool, con_slot: bool) -> Tuple[str, Optional[float]]:
    prima = len(mercato.ordini)
    esatte: List[float] = []

    def _esatta(_m: Any, _sel: int, _side: str, _p: float, size: float, _slot: Any) -> str:
        esatte.append(size)
        return "esatta"

    strat._place_exact = _esatta  # solo l'istanza del test
    modulo = SB if isinstance(strat, SB.ScalperStrategy) else TSB
    slot = modulo._Slot() if con_slot else None   # lo slot VERO del bot
    out = strat._place(mercato, 11, lato, prezzo, imp, floor_min=ingresso, slot=slot)
    if esatte:
        return "esatta", esatte[0]
    if out is None or len(mercato.ordini) == prima:
        return "nessuno", None
    return "diretto", float(mercato.ordini[-1].order_type.size)


@pytest.mark.parametrize("variante", ["calcio", "tennis"])
def test_taglia_scalper_parita_col_place_vero(variante: str,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    modulo = SB if variante == "calcio" else TSB
    # lo stato del mercato e' fuori dalla taglia: la guardia non blocca qui
    monkeypatch.setattr(modulo, "guardia_flumine", lambda *a, **k: None)
    importi = [round(i * 0.01, 2) for i in range(0, 451)] + [7.27, 7.75, 12.3]
    n = 0
    for size_step in (0.0, 0.5):
        for live_min_bet in (0.0, 2.0):
            for exact_exits in (False, True):
                strat = _strategia(variante, size_step=size_step,
                                   live_min_bet=live_min_bet, exact_exits=exact_exits)
                mercato = _Mercato()
                if variante == "tennis":
                    strat._now_ms = 1_700_000_000_000   # orologio di mercato fisso
                for lato in ("BACK", "LAY"):
                    for ingresso in (True, False):
                        for con_slot in (True, False):
                            for imp in importi:
                                vero = _taglia_vera(strat, mercato, lato, 2.0, imp,
                                                    ingresso, con_slot)
                                nuovo = NM.taglia_scalper(
                                    lato, 2.0, imp, variante=variante, ingresso=ingresso,
                                    uscita_esatta=exact_exits and con_slot,
                                    size_step=size_step, live_min_bet=live_min_bet)
                                assert vero == nuovo, (variante, size_step, live_min_bet,
                                                       exact_exits, lato, ingresso,
                                                       con_slot, imp)
                                n += 1
    assert n > 10_000
    # prezzo non piazzabile: nessun ordine in entrambi
    strat = _strategia(variante, size_step=0.5, live_min_bet=2.0, exact_exits=True)
    if variante == "tennis":
        strat._now_ms = 1_700_000_000_000
    assert _taglia_vera(strat, _Mercato(), "BACK", 1.0, 3.0, True, True) == \
        NM.taglia_scalper("BACK", 1.0, 3.0, variante=variante, ingresso=True,
                          uscita_esatta=True, size_step=0.5, live_min_bet=2.0)


# ---------------------------------------------------------------------------
# la forma uniforme
# ---------------------------------------------------------------------------
def test_taglia_uniforme_coerente_con_le_politiche() -> None:
    for lato in ("back", "lay"):
        for imp in IMPORTI[:1201:7]:
            t = NM.taglia("runner", lato, imp)
            v = NM.verdetto_runner(lato, imp)
            assert t.piazzabile == v.valid
            if v.valid:
                assert (t.diretto, t.residuo) == (v.legalized_size, v.residuo)
            r = NM.taglia("regola_it", lato, imp)
            ip = MI.importo_piazzabile(lato, imp)
            assert r.diretto + r.place_and_trim == ip.importo
            assert math.isclose(r.residuo, ip.residuo, abs_tol=1e-9)
    with pytest.raises(ValueError):
        NM.taglia("inventata", "back", 2.0)


def test_divergenze_di_oggi_fotografate() -> None:
    """Le definizioni di oggi NON coincidono. Si fotografano (referto par. 9): se un
    giorno l'utente sceglie, questo test va aggiornato insieme alla scelta."""
    # (1) ingresso: scalper tennis porta a 2,00 (MIN_STAKE), scalper calcio a 1,00, runner 1,50
    assert NM.taglia_scalper("BACK", 2.0, 1.5, variante="tennis", ingresso=True,
                             uscita_esatta=False, size_step=0.0, live_min_bet=0.0) == ("diretto", 2.0)
    assert NM.taglia_scalper("BACK", 2.0, 1.5, variante="calcio", ingresso=True,
                             uscita_esatta=False, size_step=0.0, live_min_bet=0.0) == ("diretto", 1.5)
    assert NM.verdetto_runner("back", 1.5).legalized_size == 1.5
    # (2) passo 0,50: lo scalper arrotonda al PIU' VICINO (anche in su), il runner per DIFETTO
    assert NM.taglia_scalper("BACK", 2.0, 7.27, variante="calcio", ingresso=True,
                             uscita_esatta=False, size_step=0.5, live_min_bet=2.0) == ("diretto", 7.5)
    assert NM.verdetto_runner("back", 7.27).legalized_size == 7.0
    # (3) divisione di un'uscita di punta 2,80: tennis 2,50 + 0,30 (resto < 0,50!), scalper 2,00 + 0,80
    assert NM.spezza_esatta_tennis(2.80, "BACK") == (2.5, 0.3)
    assert NM.spezza_uscita_scalper("BACK", 2.80) == (2.0, 0.8, 0.0)
    # (4) uscita sotto il minimo: lo scalper (live_min_bet>0, senza via esatta) GONFIA a 1,00,
    #     la copertura tennis la rifiuta (mai gonfiata)
    assert NM.taglia_scalper("LAY", 2.0, 0.6, variante="calcio", ingresso=False,
                             uscita_esatta=False, size_step=0.0, live_min_bet=2.0) == ("diretto", 1.0)
    assert NM.size_legale_tennis(0.6, "LAY", live=True, riduce=True)[0] is None
    # (5) live_min_bet=2,0 e' solo un interruttore: il minimo usato e' quello di minimi_it (1,00)
    assert NM.taglia_scalper("LAY", 2.0, 1.2, variante="calcio", ingresso=False,
                             uscita_esatta=False, size_step=0.0, live_min_bet=2.0) == ("diretto", 1.2)
