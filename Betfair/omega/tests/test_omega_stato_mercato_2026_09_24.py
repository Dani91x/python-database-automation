# -*- coding: utf-8 -*-
"""D2 (24/09) - OMEGA: lo stato del mercato davanti agli invii che non lo
guardavano (mappa del 24/09).

  * motore v1 (``scan_and_place``): aveva ``snapshot.status`` in mano e non lo
    leggeva -> ``_mercato_in_attesa`` (guardia condivisa, una riga
    ``attesa_riapertura`` per sospensione);
  * cash-out manuale / proposta approvata (``_cashout_prices``, ramo del FEED):
    restituiva i prezzi anche a mercato SOSPESO (quote congelate) -> None, come
    il ramo REST;
  * F3 (25/09, decisione utente (i)) - stato MANCANTE: Omega lo trattava come
    OPEN (fail-open, mai una lettura in piu'). Ora ``_mercato_in_attesa`` fa
    UNA rilettura da Betfair (``rileggi``, in produzione
    ``market.read_market(cs)``) prima di decidere; se resta ignoto anche dopo,
    NON piazza e lo dichiara (``S.KIND_STATO_IGNOTO``).

Il feed ha le chiavi dello scanner (``cs.status``/``cs.inplay``), lo snapshot e'
il ``MarketSnapshot`` VERO di ``omega_market``. ASCII-only nel codice.
"""
from __future__ import annotations

from typing import Any, List

from Betfair.omega import omega_engine as E
from Betfair.omega import omega_market as M
from Betfair.omega import omega_service as S
from Betfair.stream.trading import stato_mercato as SM


def _payload(status: str) -> dict:
    return {
        "event_name": "Nord v Sud", "inplay": True, "minute": 52,
        "score_home": 1, "score_away": 0,
        "cs": {
            "market_id": "1.777", "status": status, "inplay": True, "total_matched": 500.0,
            "selections": [
                {"selection_id": 2, "name": "3 - 0", "back": 90.0, "lay": 110.0,
                 "back_size": 2, "lay_size": 7.5, "runner_status": "ACTIVE"},
            ],
        },
    }


def _trade() -> dict:
    return {"id": 1, "event_id": "ev1", "market_id": "1.777", "selection_id": 2,
            "side": "lay", "status": "open", "mode": "paper", "price": 110.0,
            "size": 3.0, "meta": {}}


class _Rest:
    def __init__(self) -> None:
        self.calls: List[str] = []

    def read_book(self, market_id: Any, _opts: Any) -> dict:
        self.calls.append(str(market_id))
        return {"status": "SUSPENDED", "runners": []}


def _cashout(monkeypatch, status: str):
    monkeypatch.setattr(S, "_feed_row", lambda eid, hard_max_age=None:
                        (_payload(status), "2026-09-24T20:00:00+00:00"))
    rest = _Rest()
    monkeypatch.setattr(M, "read_book", rest.read_book)
    return S._cashout_prices(M, _trade()), rest


def test_cashout_dal_feed_a_mercato_sospeso_non_da_prezzi(monkeypatch):
    prezzi, rest = _cashout(monkeypatch, "SUSPENDED")
    assert prezzi is None
    assert rest.calls == []          # nessuna chiamata in piu': si sa gia' che e' sospeso


def test_cashout_dal_feed_a_mercato_aperto_prezza_come_prima(monkeypatch):
    prezzi, rest = _cashout(monkeypatch, "OPEN")
    assert prezzi is not None and prezzi["lay"] == 110.0 and rest.calls == []


class _Db:
    def __init__(self) -> None:
        self.righe: List[tuple] = []

    def log(self, kind: str, payload: dict) -> None:
        self.righe.append((kind, payload))


def _snap(status: str) -> M.MarketSnapshot:
    return M.MarketSnapshot(status=status, inplay=True,
                            runners=[E.ScoreRunner(selection_id=2, name="3 - 0")],
                            closed=False, winner_selection_id=None, voided=False)


def test_v1_guardia_una_riga_per_sospensione_e_riapertura():
    db = _Db()
    for _ in range(20):
        assert S._mercato_in_attesa(db, "ev1", "1.777", _snap("SUSPENDED"), "v1") is True
    att = [p for k, p in db.righe if k == SM.KIND_ATTESA]
    assert len(att) == 1 and att[0]["motivo"] == "SUSPENDED" and att[0]["aspetta"] is True
    assert S._mercato_in_attesa(db, "ev1", "1.777", _snap("OPEN"), "v1") is False
    assert S._mercato_in_attesa(db, "ev1", "1.777", _snap("SUSPENDED"), "v1") is True
    assert len([k for k, _ in db.righe if k == SM.KIND_ATTESA]) == 2


def test_v1_stato_mancante_senza_rilettura_passa_come_prima_del_25_09():
    """F3 (25/09) - se il chiamante NON passa ``rileggi`` (nessun modo di
    rileggere da Betfair) il comportamento resta quello storico: si passa.
    Il chiamante VERO (``scan_and_place``) passa SEMPRE ``rileggi`` da oggi —
    vedi i test sotto per il comportamento in produzione."""
    db = _Db()
    snap = _snap(None)  # type: ignore[arg-type] - il campo che manca nella riga
    assert S._mercato_in_attesa(db, "ev2", "1.777", snap, "v1") is False
    assert db.righe == []


def test_v1_stato_mancante_rilettura_trova_lo_stato_vero(monkeypatch):
    """F3 (25/09, decisione utente (i)) - Omega trattava lo stato mancante come
    OPEN (fail-open storico). Ora rilegge UNA volta da Betfair prima
    dell'ordine: se la rilettura trova un mercato SOSPESO, si comporta come se
    lo stato fosse arrivato sospeso fin da subito (nessun ordine, attesa
    riapertura dichiarata)."""
    db = _Db()
    snap = _snap(None)  # type: ignore[arg-type] - la riga del feed non porta lo status
    chiamate: List[int] = []

    def rileggi():
        chiamate.append(1)
        return _snap("SUSPENDED")

    assert S._mercato_in_attesa(db, "ev2b", "1.777", snap, "v1", rileggi=rileggi) is True
    assert len(chiamate) == 1, "UNA rilettura, non a ogni giro"
    att = [p for k, p in db.righe if k == SM.KIND_ATTESA]
    assert len(att) == 1 and att[0]["motivo"] == "SUSPENDED"


def test_v1_stato_mancante_rilettura_apre_come_sempre(monkeypatch):
    """La rilettura trova un mercato OPEN: si piazza, come se lo stato fosse
    arrivato aperto fin da subito."""
    db = _Db()
    snap = _snap(None)  # type: ignore[arg-type]
    assert S._mercato_in_attesa(db, "ev2c", "1.777", snap, "v1",
                                rileggi=lambda: _snap("OPEN")) is False
    assert db.righe == []


def test_v1_stato_ancora_ignoto_dopo_la_rilettura_non_piazza_e_lo_dichiara(monkeypatch):
    """F3 (25/09) - se anche DOPO la rilettura lo stato resta ignoto (rete
    giu', ``read_market`` torna None), Omega NON piazza e lo dichiara col
    motivo «stato mercato ignoto» (log + attivita' a video), mai un pass
    silenzioso come prima del 25/09."""
    db = _Db()
    snap = _snap(None)  # type: ignore[arg-type]
    assert S._mercato_in_attesa(db, "ev2d", "1.777", snap, "v1",
                                rileggi=lambda: None) is True
    righe = [(k, p) for k, p in db.righe if k == S.KIND_STATO_IGNOTO]
    assert len(righe) == 1
    assert righe[0][1]["motivo"] == "IGNOTO"
    assert righe[0][1]["event_id"] == "ev2d"
    # non e' finita nell'attesa_riapertura (motivo diverso, kind diverso)
    assert not any(k == SM.KIND_ATTESA for k, _ in db.righe)


def test_v1_rilettura_che_solleva_e_gestita_come_ignoto(monkeypatch):
    """La rilettura non deve MAI far esplodere il giro: un'eccezione (rete,
    timeout) e' equivalente a "ancora ignoto", loggata e rifiutata."""
    db = _Db()
    snap = _snap(None)  # type: ignore[arg-type]

    def rileggi_rotta():
        raise RuntimeError("timeout REST")

    assert S._mercato_in_attesa(db, "ev2e", "1.777", snap, "v1",
                                rileggi=rileggi_rotta) is True
    assert any(k == S.KIND_STATO_IGNOTO for k, _ in db.righe)
    assert any(k == "rilettura_stato_mercato_errore" for k, _ in db.righe)


def test_svuota_le_cache_dimentica_le_attese():
    db = _Db()
    S._mercato_in_attesa(db, "ev3", "1.777", _snap("SUSPENDED"), "v1")
    S.svuota_le_cache()
    S._mercato_in_attesa(db, "ev3", "1.777", _snap("SUSPENDED"), "v1")
    assert len(db.righe) == 2
