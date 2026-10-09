"""W1-C1 - parita' dell'adattatore ``RichiestaOrdine`` <-> comando / coda calcio / coda tennis.

Arbitri (codice di oggi, importato e mai modificato):
  * ``motore_ordini.valida_comando`` - il PIANO che il motore esegue;
  * ``safe_strategy.porta_ordini.costruisci_comando`` - il comando VERO di Safe (produttore);
  * ``safe_strategy.execution.enqueue_place`` - la riga VERA della coda di Safe (produttore);
  * ``esecutore_tennis._payload_da_riga`` + ``tennis_live_order_worker.parse_order_payload``.

Parita' in ANDATA E RITORNO per ogni azione e campo: place (size; liability solo coda),
cancel totale e parziale, replace, greenup e cash-out (``RichiestaComposta``), FOK,
persistenza, handicap, riduzione dell'esposizione, place-and-trim (``place_submin``).
"""
from __future__ import annotations

import itertools
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from Betfair.nucleo.ordini import adattatore_comando as AC
from Betfair.nucleo.ordini.contratto import RichiestaOrdine
from Betfair.stream import motore_ordini as MO

ORA_MS = 1_760_000_000_000


def _place(**k: Any) -> RichiestaOrdine:
    base: Dict[str, Any] = dict(ref="safe-t101", attore="safe", sport="calcio", modo="paper",
                                azione="place", market_id="1.2345", selection_id=47972,
                                lato="back", prezzo=2.5, importo=4.0, creato_ms=ORA_MS)
    base.update(k)
    return RichiestaOrdine(**base)


def _casi() -> List[AC.Richiesta]:
    out: List[AC.Richiesta] = []
    for lato, pers, tif, riduce, hc, modo, origine in itertools.product(
            ("back", "lay"), ("LAPSE", "PERSIST"), (None, "FILL_OR_KILL"), (False, True),
            (0.0, -1.5, 2.25), ("paper", "live"), (None, {"tabella": "safe_strategy_trades", "id": 7})):
        out.append(_place(lato=lato, persistenza=pers, time_in_force=tif,
                          riduce_esposizione=riduce, handicap=hc, modo=modo, origine=origine,
                          importo=0.73 if riduce else 12.37, prezzo=1.01 if hc else 3.45))
    out.append(_place(ref="omega-t9", attore="omega"))
    out.append(_place(ref="mike-t9", attore="mike", sport="calcio"))
    out.append(_place(ref="safe_tennis-t3", attore="safe_tennis", sport="tennis"))
    for rid in (None, 0.5, 2.0):
        out.append(RichiestaOrdine(ref=f"safe-c311-{rid}", attore="safe", sport="calcio",
                                   modo="live", azione="cancel", market_id="1.2345",
                                   selection_id=0, bet_id="312426000123", riduzione=rid,
                                   creato_ms=ORA_MS))
    out.append(RichiestaOrdine(ref="safe-r1", attore="safe", sport="calcio", modo="paper",
                               azione="replace", market_id="1.2345", selection_id=47972,
                               bet_id="312426000124", nuovo_prezzo=2.62, creato_ms=ORA_MS))
    out.append(AC.RichiestaComposta(ref="desktop-g1", attore="desktop", sport="calcio",
                                    modo="paper", azione="greenup", market_id="1.2345",
                                    selection_id=47972, handicap=0.0, creato_ms=ORA_MS))
    for az in ("cashout_event", "cashout_all"):
        out.append(AC.RichiestaComposta(ref=f"desktop-{az}", attore="desktop", sport="calcio",
                                        modo="live", azione=az, market_id="1.2345",
                                        creato_ms=ORA_MS))
    return out


# ---------------------------------------------------------------------------
# 1. il comando del canale
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("extra", [AC.ExtraComando(),
                                   AC.ExtraComando(max_eta_ms=2500, params={"fok_ttl_sec": 3})])
def test_comando_andata_e_ritorno(extra: AC.ExtraComando) -> None:
    casi = _casi()
    assert len(casi) > 200
    for r in casi:
        d = AC.comando_da_richiesta(r, extra)
        r2, ex2 = AC.richiesta_da_comando(r.attore, r.sport, d)
        assert r2 == r, (r, r2)
        assert ex2 == extra


def test_comando_piano_identico_su_comandi_veri_di_safe() -> None:
    """Il comando PRODOTTO da Safe -> richiesta -> comando: ``valida_comando`` da' lo
    STESSO piano (la riga che il motore esegue) cifra per cifra."""
    from Betfair.safe_strategy import porta_ordini as PO

    comandi = []
    for side, pers, tif, riduce in itertools.product(("BACK", "LAY"), (None, "LAPSE", "PERSIST"),
                                                     (None, "FILL_OR_KILL"), (False, True)):
        comandi.append(PO.costruisci_comando(
            ref="safe-t55", attore="safe", azione="place", mode="live", market_id="1.99",
            selection_id=58805, side=side, price=1.87, size=5.13, persistence=pers,
            creato_ms=ORA_MS, origine={"tabella": "safe_strategy_trades", "id": 55},
            time_in_force=tif, reduces_liability=riduce))
    comandi.append(PO.costruisci_comando(ref="safe-c9", attore="safe", azione="cancel",
                                         mode="paper", market_id="1.99", bet_id="321",
                                         size_reduction=0.5, creato_ms=ORA_MS))
    comandi.append(PO.costruisci_comando(ref="safe_tennis-c9", attore="safe_tennis",
                                         azione="cancel", mode="paper", market_id="1.99",
                                         bet_id="321", creato_ms=ORA_MS))
    for d in comandi:
        vecchio = MO.valida_comando(d["attore"], dict(d))
        r, ex = AC.richiesta_da_comando(d["attore"], "calcio", d)
        nuovo = MO.valida_comando(d["attore"], AC.comando_da_richiesta(r, ex))
        assert nuovo == vecchio, d


@pytest.mark.parametrize("modifica", [
    {"side": "SIDEWAYS"}, {"creato_ms": float(ORA_MS)}, {"persistence": "MARKET_ON_CLOSE"},
    {"strategy_ref": "omega"}, {"price": True}, {"size": -1.0}, {"mode": "LIVE"},
    {"time_in_force": "IOC"}, {"azione": "dutch"}, {"attore": "omega"},
    {"reduces_liability": "si"}, {"params": [1]}, {"origine": "riga 7"}, {"max_eta_ms": 0},
])
def test_rifiuti_identici_a_valida_comando(modifica: Dict[str, Any]) -> None:
    d = AC.comando_da_richiesta(_place(), AC.ExtraComando(max_eta_ms=3000))
    d.update(modifica)
    with pytest.raises(MO.Rifiuto) as vecchio:
        MO.valida_comando("safe", dict(d))
    with pytest.raises(MO.Rifiuto) as nuovo:
        AC.richiesta_da_comando("safe", "calcio", d)
    assert (nuovo.value.codice, str(nuovo.value)) == (vecchio.value.codice, str(vecchio.value))


def test_reduces_liability_nei_params_tolto_come_oggi() -> None:
    d = AC.comando_da_richiesta(_place(), AC.ExtraComando(params={"reduces_liability": True,
                                                                  "x": 1}))
    r, ex = AC.richiesta_da_comando("safe", "calcio", d)
    assert r.riduce_esposizione is False            # mai creduto dai params
    assert ex.params == {"x": 1}
    assert MO.valida_comando("safe", dict(d))["riduce"] is False


# ---------------------------------------------------------------------------
# 2. la coda calcio
# ---------------------------------------------------------------------------
def _dettagli_per(r: AC.Richiesta) -> AC.DettagliCoda:
    return AC.DettagliCoda(params={"source": r.attore, "trade_id": 7})


def test_riga_coda_uguale_alla_riga_del_motore() -> None:
    """Il motore esegue una riga con la forma della CODA (docstring di valida_comando):
    la riga di coda dell'adattatore coincide, chiave per chiave, con quella del piano."""
    for r in _casi():
        if isinstance(r, AC.RichiestaComposta):
            continue
        dt = _dettagli_per(r)
        riga = AC.riga_coda_da_richiesta(r, dt)
        piano = MO.valida_comando(r.attore, AC.comando_da_richiesta(
            r, AC.ExtraComando(params=dt.params)))
        for k in AC.chiavi_riga():
            if k == "params":
                continue
            if k == "selection_id" and r.azione != "place" and r.selection_id:
                # la selezione NOTA di un cancel/replace resta nella riga di coda; il
                # motore la lascia None (non la legge): unica differenza, dichiarata
                assert piano["riga"][k] is None
                continue
            assert riga[k] == piano["riga"][k], (k, r)
        p_motore = {k: v for k, v in piano["riga"]["params"].items() if k != "comando"}
        assert (riga["params"] or {}) == p_motore, r
        assert (riga["action"], riga["mode"]) == (piano["azione"], piano["mode"])


def test_coda_andata_e_ritorno_con_liability_e_submin() -> None:
    righe: List[Dict[str, Any]] = []
    for r in _casi():
        righe.append(AC.riga_coda_da_richiesta(r, _dettagli_per(r)))
    # liability (la coda la ammette, il comando no), min_fill_size, place_submin
    lay_liab = AC.riga_coda_da_richiesta(_place(lato="lay", importo=None, time_in_force="FILL_OR_KILL"),
                                         AC.DettagliCoda(liability=6.5, min_fill_size=2.0))
    righe.append(lay_liab)
    righe.append(AC.riga_coda_da_richiesta(
        _place(importo=0.7), AC.DettagliCoda(azione_coda="place_submin",
                                             params={"target_size": 0.7, "source": "safe"})))
    for riga in righe:
        r, dt = AC.richiesta_da_riga_coda(riga, attore="safe", sport="calcio", creato_ms=ORA_MS)
        assert AC.riga_coda_da_richiesta(r, dt) == riga, riga
    assert set(lay_liab) == set(AC.chiavi_coda())
    with pytest.raises(ValueError):
        AC.richiesta_da_riga_coda({"action": "boh"}, attore="safe", sport="calcio")


class _DbSpia:
    """Il ``db`` che ``enqueue_place`` di Safe usa: registra il payload VERO."""

    def __init__(self) -> None:
        self.payload: Optional[Dict[str, Any]] = None

    def update_trade(self, *_a: Any, **_k: Any) -> None:
        return None

    def enqueue_live_order(self, payload: Dict[str, Any]) -> int:
        self.payload = dict(payload)
        return 4242

    def log(self, *_a: Any, **_k: Any) -> None:
        return None


def _come_la_rpc(p: Dict[str, Any]) -> Dict[str, Any]:
    """La riga che ``request_betfair_live_order`` INSERISCE dal payload
    (``migrations/betfair_live_cashout_v3.sql`` righe ~199-212): handicap 0, order_type
    LIMIT e persistence LAPSE se assenti; il resto cosi' com'e'."""
    riga = {k: p.get(k) for k in AC.chiavi_coda()}
    riga["handicap"] = p.get("handicap") if p.get("handicap") not in (None, "") else 0.0
    riga["order_type"] = p.get("order_type") or "LIMIT"
    riga["persistence"] = p.get("persistence") or "LAPSE"
    return riga


@pytest.mark.parametrize("modo,azione,meta", [
    ("paper", "place", None), ("live", "place", {"closes_trade_id": 3}),
    ("live", "place_submin", None), ("paper", "place_submin", {"cashout": True}),
])
def test_coda_riga_vera_di_safe_andata_e_ritorno(modo: str, azione: str, meta: Any) -> None:
    from Betfair.safe_strategy import execution as EX

    db = _DbSpia()
    rid = EX.enqueue_place(db=db, trade_id=55, client_ref="safe-t55", event_id="E",
                           market_id="1.99", selection_id=58805, side="lay", price=1.87,
                           size=0.73 if azione == "place_submin" else 5.13, base_meta=meta,
                           now=datetime.now(timezone.utc), mode=modo, action=azione)
    assert rid == 4242 and db.payload is not None
    vera = _come_la_rpc(db.payload)
    r, dt = AC.richiesta_da_riga_coda(vera, attore="safe", sport="calcio")
    assert AC.riga_coda_da_richiesta(r, dt) == vera
    assert r.riduce_esposizione is bool(meta)
    assert r.time_in_force == ("FILL_OR_KILL" if azione == "place" else None)
    assert dt.azione_coda == (azione if azione == "place_submin" else None)


# ---------------------------------------------------------------------------
# 3. la coda tennis
# ---------------------------------------------------------------------------
def test_payload_tennis_letto_come_quello_del_motore() -> None:
    from Betfair.stream.tennis_live import esecutore_tennis as ET
    from Betfair.stream.tennis_live import tennis_live_order_worker as TW

    for r in _casi():
        if isinstance(r, AC.RichiestaComposta) and r.azione != "greenup":
            continue
        dt = _dettagli_per(r)
        piano = MO.valida_comando(r.attore, AC.comando_da_richiesta(
            r, AC.ExtraComando(params=dt.params)))
        riga_motore = dict(piano["riga"], action=piano["azione"])
        vecchio = TW.parse_order_payload({"payload": ET._payload_da_riga(riga_motore,
                                                                         piano["mode"])})
        nuovo = TW.parse_order_payload({"payload": AC.payload_tennis_da_richiesta(r, dt)})
        vecchio.pop("params")
        nuovo.pop("params")
        if r.azione in ("cancel", "replace") and r.selection_id:
            assert vecchio["selection_id"] is None   # vedi sopra: il motore non la porta
            nuovo["selection_id"] = None
        assert nuovo == vecchio, r
        # ritorno: la riga di coda tennis (payload + client_ref) torna alla richiesta
        if isinstance(r, RichiestaOrdine):
            riga_coda = {"client_ref": r.ref, "payload": AC.payload_tennis_da_richiesta(r, dt)}
            r2, _dt2 = AC.richiesta_da_payload_tennis(riga_coda, attore=r.attore,
                                                      creato_ms=r.creato_ms)
            atteso = r if r.sport == "tennis" else RichiestaOrdine(**{**r.__dict__,
                                                                      "sport": "tennis",
                                                                      "origine": None})
            assert r2 == RichiestaOrdine(**{**atteso.__dict__, "origine": None}), r
