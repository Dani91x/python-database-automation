"""D1-ter (28/09) - BLOCCO 1 (M3): taker FOK SOTTO IL MINIMO, paper = live.

In LIVE Mike piazza un taker sotto il minimo con ``place_submin_live``
(``fill_or_kill=True`` di default, chiamato da ``execution.place``): il piano lo
decide ``omega_market.piano_submin_live`` e, se la quota NON e' abbinabile
(percorso A) o il piano e' irrealizzabile, il rifiuto e' CERTO e nessun ordine
tocca Betfair. In PAPER sul canale del runner ``execution`` mandava il comando
senza FOK e il motore faceva il place-and-trim a riposo: un ordine che il live
non avrebbe mai avuto.

Test di PARITA': la STESSA richiesta a ``execution.place`` in paper (porta di
Mike VERA, ``VistaMike``, sopra il runner finto col protocollo vero) e in live
(``omega_market.place_submin_live`` VERO, con ``call_mutating`` finto che conta
le chiamate a Betfair e il book letto finto). Si confrontano esito, motivo,
codice e numero di ordini.

Il caso B (quota abbinabile: parcheggio lontano, taglio, rimpiazzo e residuo
RITIRATO) si chiude nella seconda consegna, sopra il motore di D2: il suo test
di parita' e' qui sotto, marcato ``xfail(strict=True)`` finche' non e' fatto.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.mike import porta_ordini as MP
from Betfair.omega import omega_market as OM
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import porta_ordini as SPO


@pytest.fixture(autouse=True)
def _freni_aperti(monkeypatch):
    monkeypatch.setattr(X, "_freno_aperture", lambda: None)
    monkeypatch.setattr(X, "_live_brake", lambda: None)

    def _vietato(*_a, **_k):
        raise AssertionError("accesso al database vero da un test")
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", _vietato)


class _DbFinto:
    """Solo cio' che ``execution`` chiama sulla strada del place."""

    def __init__(self) -> None:
        self.righe: List[tuple] = []
        self.aggiornamenti: List[tuple] = []

    def log(self, kind: str, payload: Dict[str, Any], *a: Any, **k: Any) -> None:
        self.righe.append((kind, dict(payload)))

    def update_trade(self, tid: int, **kw: Any) -> None:
        self.aggiornamenti.append((tid, kw))


def _mercato_live(monkeypatch, best_back, best_lay) -> SimpleNamespace:
    """Il LIVE vero: ``place_submin_live`` di produzione. Il book lo legge da
    Betfair (qui finto, stessi valori dello stream); ogni chiamata mutante a
    Betfair viene contata (e qui non deve mai partire)."""
    chiamate: List[Any] = []
    monkeypatch.setattr(OM, "_submin_best_prices", lambda _m, _s: (best_back, best_lay))

    def _mutante(fn):
        chiamate.append(fn)
        raise AssertionError("chiamata a Betfair su un rifiuto che doveva essere certo")
    monkeypatch.setattr(OM, "call_mutating", _mutante)
    return SimpleNamespace(place_submin_live=OM.place_submin_live,
                           place_order_live=lambda **_k: pytest.fail("place normale"),
                           chiamate=chiamate)


def _richiesta(**kw: Any) -> Dict[str, Any]:
    base = dict(event_id="35760084", market_id="1.259475534", selection_id=1222346,
                best_size=None, ladder=((0.0, 0.0),), client_ref="mike-t2", trade_id=2,
                meta={}, params={"execution_mode": "rest"})
    base.update(kw)
    return base


def _esito(o: X.PlaceOutcome) -> tuple:
    return (o.status, o.fill_note, o.error_code, o.size, o.bet_id, o.size_requested, o.size_remaining)


# (lato, quota, importo, best_back, best_lay, codice atteso in live)
CASI_A = [
    # BACK a quota PIU' ALTA del best back: resta a riposo -> percorso A + FOK
    ("back", 4.0, 1.26, 3.9, 3.95, "SUBMIN_NESSUNA_CONTROPARTE"),
    # LAY a quota PIU' BASSA del best lay: resta a riposo -> percorso A + FOK
    ("lay", 2.5, 0.30, 2.54, 2.6, "SUBMIN_NESSUNA_CONTROPARTE"),
]


@pytest.mark.parametrize("side,prezzo,importo,bb,bl,codice", CASI_A)
def test_parita_taker_fok_sotto_minimo_quota_non_abbinabile(monkeypatch, runner, side, prezzo,
                                                            importo, bb, bl, codice):
    # LIVE: place_submin_live vero, zero chiamate mutanti, rifiuto col codice
    mk = _mercato_live(monkeypatch, bb, bl)
    db_live = _DbFinto()
    live = X.place(db=db_live, market=mk, mode="live", side=side, price=prezzo,
                   size=importo, **_richiesta())
    # PAPER: porta di Mike vera sopra il runner finto, book dello stream
    db_paper = _DbFinto()
    paper = X.place(db=db_paper, market=SimpleNamespace(), mode="paper", side=side,
                    price=prezzo, size=importo, porta=MP.vista(appoggiata=False),
                    best_back=bb, best_lay=bl, **_richiesta())
    assert live.status == "error" and live.error_code == codice
    assert _esito(paper) == _esito(live), "paper diverso dal live sul taker FOK sotto minimo"
    assert live.fill_note == f"live_rifiutato:{codice}"
    # zero ordini in entrambi i mondi
    assert mk.chiamate == []
    assert runner.comandi == [], "in paper e' partito un comando che il live non manda"
    # stessa riga di attivita' (tolto il mode)
    rl = [(k, {**p, "mode": None}) for k, p in db_live.righe if k == "place_rifiutato"]
    rp = [(k, {**p, "mode": None}) for k, p in db_paper.righe if k == "place_rifiutato"]
    assert rl and rl == rp


def test_book_ignoto_in_paper_non_inventa_rifiuti(runner):
    """Senza book dallo stream il piano e' il percorso B (come il live con book
    ignoto): nessun rifiuto inventato, il comando parte come prima."""
    paper = X.place(db=_DbFinto(), market=SimpleNamespace(), mode="paper", side="back",
                    price=3.9, size=1.26, porta=MP.vista(appoggiata=False), **_richiesta())
    assert paper.status == "pending"
    assert len(runner.comandi) == 1


@pytest.mark.parametrize("porta_nome", ["appoggiata_mike", "safe"])
def test_chi_non_e_un_taker_fok_non_cambia(runner, porta_nome):
    """La lay appoggiata di Mike (``fill_or_kill=False`` in live) e le porte di
    Safe/Omega (canale anche in live, place-and-trim a riposo in entrambi i
    modi) non dichiarano ``submin_fill_or_kill``: il comando parte come prima,
    anche con una quota non abbinabile."""
    if porta_nome == "appoggiata_mike":
        porta = MP.vista(appoggiata=True)
        attesi = 1
    else:
        porta = SimpleNamespace(via_canale=True, attore="mike", disponibile=lambda: True,
                                invia=runner.invia)
        attesi = 1
    assert not getattr(porta, "submin_fill_or_kill", False)
    out = X.place(db=_DbFinto(), market=SimpleNamespace(), mode="paper", side="lay",
                  price=2.5, size=0.30, porta=porta, best_back=2.54, best_lay=2.6,
                  **_richiesta())
    assert out.status == "pending"
    assert len(runner.comandi) == attesi
    assert runner.comandi[-1]["time_in_force"] is None


@pytest.mark.parametrize("side,prezzo,importo", [("back", 3.9, 1.26), ("lay", 2.5, 0.30)])
def test_chiusura_sotto_minimo_resta_all_importo_esatto(runner, side, prezzo, importo):
    """Le CHIUSURE non passano dal piano: importo esatto, nessun rifiuto."""
    out = X.place(db=_DbFinto(), market=SimpleNamespace(), mode="paper", side=side,
                  price=prezzo, size=importo, porta=MP.vista(appoggiata=False),
                  best_back=prezzo - 0.5, best_lay=prezzo + 0.5,
                  **_richiesta(meta={"closes_trade_id": 1}))
    assert out.status == "pending"
    c = runner.comandi[-1]
    assert c["size"] == importo and c["reduces_liability"] is True


def test_mike_paper_passa_il_book_dello_stream_a_execution(monkeypatch, runner):
    """``execute_place`` in paper consegna a ``execution`` il book su cui il
    motore ha deciso (senza, il piano sarebbe «book ignoto» = percorso B)."""
    from Betfair.mike import engine as E
    from Betfair.mike import service as S
    from Betfair.mike.tests.test_mike_d1bis_freno_coperture_runner_2026_09_28 import (
        ORA, _gamba, _params)
    from Betfair.mike.tests.test_mike_loop_taker_2026_09_16 import db_vuoto, info_vera

    monkeypatch.setattr(S, "_freno_aperture_rest", lambda: None)
    visti: List[Dict[str, Any]] = []
    vero = X.place

    def _spia(**kw):
        visti.append(kw)
        return vero(**kw)
    monkeypatch.setattr(X, "place", _spia)
    book = E.Book(status="OPEN", best_back=1.53, back_size=100.0, best_lay=1.55,
                  lay_size=100.0, inplay=True)
    leg = _gamba(1)
    leg.size = 1.26
    ctx = E.MatchCtx(legs=[leg])
    S.execute_place(db=db_vuoto(), market=SimpleNamespace(), info=info_vera(), leg=leg,
                    book=book, mode="paper", params=_params(), now=ORA, dry=False,
                    feed_fresh=True, ctx=ctx)
    assert visti and visti[0]["best_back"] == 1.53 and visti[0]["best_lay"] == 1.55


def test_parita_caso_b_taker_fok_sotto_minimo_quota_abbinabile(runner):
    """Quota ABBINABILE (la copertura aggressiva di Mike, 1,26 @ 3,9 su best back
    3,9): in live percorso B con ``fill_or_kill=True`` (parcheggio lontano,
    taglio, rimpiazzo alla quota target, residuo RITIRATO). Sul canale il
    comando porta lo stesso FOK (scarto (a) del banco: coda fok True, canale
    fok False); la sequenza e il ritiro li fa il motore (test del motore
    ``test_motore_submin_fok_caso_b_d1ter_2026_09_28``)."""
    X.place(db=_DbFinto(), market=SimpleNamespace(), mode="paper", side="back", price=3.9,
            size=1.26, porta=MP.vista(appoggiata=False), best_back=3.9, best_lay=3.95,
            **_richiesta())
    assert runner.comandi and runner.comandi[-1]["time_in_force"] == SPO.FOK
