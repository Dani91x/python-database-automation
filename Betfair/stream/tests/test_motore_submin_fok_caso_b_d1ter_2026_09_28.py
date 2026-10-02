"""D1-ter (28/09) - BLOCCO 4: il FILL_OR_KILL sotto il minimo sul canale fa
la sequenza del LIVE e RITIRA il residuo; un passo fallito non chiude con
``errore`` un ordine vivo.

Live (``omega_market.place_submin_live``, ``fill_or_kill=True``): parcheggio,
taglio, rimpiazzo alla quota target, poi il residuo NON abbinato si ritira («o si
abbina, o non esiste»). Prima il motore RIFIUTAVA il FOK sotto il minimo
(``submin_non_percorribile``) e, senza FOK, lasciava il residuo a riposo.

Ambiente: quello del test del motore (``amb``: canale, motore e ordini flumine
VERI; mercato finto con la borsa: il place assegna il bet_id, il cancel parziale
riduce, il cancel totale completa l'ordine).
"""
# minimi .it definitivi 01/10: punta 1,00 / banca 1,00 / trim >= 0,50 (il 'sotto minimo' dei test place-and-trim e' 0,70 col parcheggio 1,00)
from __future__ import annotations

from typing import Any, List, Optional

from flumine.exceptions import OrderUpdateError

from Betfair.stream.tests.test_motore_ordini_2026_09_24 import (  # noqa: F401
    LOW, _ack, _cmd, _manda, amb)


def _tipi(amb: Any) -> List[tuple]:
    return [(c[0], c[2]) if isinstance(c[0], str) else ("place", None)
            for c in amb.market.calls]


def _fasi(amb: Any, ws: Any) -> list:
    return [m["d"]["fase"] for m in amb.ch.per_ws(ws, "order")]


def _manda_fok(amb: Any, mode: str = "paper") -> Any:
    amb.market.borsa = True
    ws = amb.ch.collega("mike")
    _manda(amb, ws, _cmd("mike", 1, mode=mode, size=0.7, price=3.0,
                         time_in_force="FILL_OR_KILL"))
    assert _ack(amb, ws)["accettato"] is True, "FOK sotto il minimo rifiutato"
    return ws


def _giri(amb: Any, n: int = 6) -> None:
    for _ in range(n):
        amb.motore.avanza_submin()


def test_fok_sotto_minimo_sequenza_del_live_e_residuo_ritirato(amb):
    ws = _manda_fok(amb)
    ordine = amb.market.calls[0][0]
    assert ordine.order_type.size == 1.0 and ordine.order_type.price == 1000.0
    _giri(amb)
    # parcheggio 1,00, taglio a 0,70, rimpiazzo a 3,0, RITIRO del residuo (totale)
    assert _tipi(amb) == [("place", None), ("cancel", 0.3), ("replace", 3.0),
                          ("cancel", None)]
    assert not amb.motore._submin
    assert "errore" not in _fasi(amb, ws)
    assert ordine.status.name == "EXECUTION_COMPLETE"


def test_fok_abbinato_per_intero_nessun_ritiro(amb):
    amb.market.borsa = True
    vero = amb.market.replace_order

    def _replace_e_abbina(order: Any, new_price: float) -> bool:
        ok = vero(order, new_price)
        order.execution_complete()          # abbinato per intero alla quota target
        return ok
    amb.market.replace_order = _replace_e_abbina
    ws = _manda_fok(amb)
    _giri(amb)
    assert _tipi(amb) == [("place", None), ("cancel", 0.3), ("replace", 3.0)]
    assert not amb.motore._submin and "errore" not in _fasi(amb, ws)


def test_senza_fok_il_residuo_resta_come_prima(amb):
    amb.market.borsa = True
    ws = amb.ch.collega("mike")
    _manda(amb, ws, _cmd("mike", 1, size=0.7, price=3.0))
    _giri(amb)
    assert _tipi(amb) == [("place", None), ("cancel", 0.3), ("replace", 3.0)]


def test_ritiro_del_residuo_che_solleva_si_ritenta(amb):
    ws = _manda_fok(amb)
    vero = amb.market.cancel_order
    n = {"totali": 0}

    def _cancel(order: Any, size_reduction: Optional[float] = None) -> bool:
        if size_reduction is None:
            n["totali"] += 1
            if n["totali"] == 1:
                raise OrderUpdateError("stato transitorio")
        return vero(order, size_reduction)
    amb.market.cancel_order = _cancel
    for _ in range(10):    # fino al primo ritiro (KO)
        if n["totali"]:
            break
        amb.motore.avanza_submin()
    assert n["totali"] == 1
    assert amb.motore._submin, "sequenza chiusa con il residuo forse a riposo"
    _giri(amb, 1)
    assert not amb.motore._submin and n["totali"] == 2
    assert "errore" not in _fasi(amb, ws)


def test_passo_fallito_non_chiude_un_ordine_vivo(amb, monkeypatch):
    """Ramo (2): eccezione in ``_advance_submin_row`` -> ritiro pendente,
    terminale ``errore`` solo a ordine morto (prima: subito ``errore``)."""
    amb.market.borsa = True
    ws = amb.ch.collega("mike")
    _manda(amb, ws, _cmd("mike", 1, size=0.7, price=3.0))
    ordine = amb.market.calls[0][0]

    def _esplode(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("rete giu' al passo del taglio")
    monkeypatch.setattr(LOW, "_advance_submin_row", _esplode)
    vero = amb.market.cancel_order

    def _cancel(order: Any, size_reduction: Optional[float] = None) -> bool:
        if not getattr(order, "bet_id", None):
            raise OrderUpdateError("Order does not currently have a betId")
        return vero(order, size_reduction)
    amb.market.cancel_order = _cancel
    bet = ordine.bet_id
    ordine.bet_id = None
    ordine.placing()
    _giri(amb, 3)
    assert "errore" not in _fasi(amb, ws) and amb.motore._submin
    ordine.bet_id = bet
    ordine.executable()
    _giri(amb, 1)
    assert ("cancel", ordine, None) in amb.market.calls
    assert _fasi(amb, ws)[-1] == "errore" and not amb.motore._submin
