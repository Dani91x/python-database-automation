"""D1-ter (28/09) - BLOCCO 2 (M2): la fase ``errore`` del runner e' un esito
IGNOTO, mai «annullato» (controllo J4 del banco).

``errore`` = ``post_place:`` o place-and-trim abbandonato dal motore: l'ordine
potrebbe esistere. Prima ``_segui_ordini_paper_su_runner`` chiudeva la gamba
'cancelled' e il motore poteva rientrare con un ordine forse vivo. Ora: gamba
``E.STATUS_RECONCILE``, riga 'pending' marcata ``place_exception_reconciling``
(come il ramo C3 del sincrono), risolta dal primo terminale DEFINITIVO del
runner (stesso ref o stesso bet_id); nessun conteggio del freno delle coperture.

Piu' i due test negativi sul freno (mutazioni del coordinatore sopravvissute a
D1-bis): la fase ``errore`` e la scadenza di una lay APPOGGIATA non fanno
avanzare il conteggio (ne' chiamano il contatore).

Finti: runner finto sul protocollo vero; l'evento ``errore`` e' costruito con
le chiavi di ``motore_ordini.CHIAVI_SPECCHIO`` + ``ref/seq/fase/esito_ms``,
come lo emette ``motore_ordini._chiudi_submin``.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_d1bis_freno_coperture_runner_2026_09_28 import (
    ORA, _attivita, _book, _conteggio, _gamba, _params, _freni_aperti)  # noqa: F401
from Betfair.mike.tests.test_mike_loop_taker_2026_09_16 import EVENTO, db_vuoto, info_vera
from Betfair.stream import motore_ordini as MO


def _evento_errore(runner, ref: str) -> Dict[str, Any]:
    """L'evento terminale ``errore`` del motore (place-and-trim abbandonato):
    riga dello specchio com'e' + fase ``errore``."""
    riga = dict(runner.ordine(ref))
    ev = {**{k: riga.get(k) for k in MO.CHIAVI_SPECCHIO}, "ref": ref,
          "seq": next(runner._seq), "fase": "errore", "esito_ms": 0}
    runner.memoria.ricevi_evento(ev)
    return ev


def _taker_in_volo(runner, db, ctx, leg, par):
    """Il taker parte e resta senza esito (runner trattiene gli eventi)."""
    runner.trattieni = True
    ctx.legs.append(leg)
    out = S.execute_place(db=db, market=SimpleNamespace(), info=info_vera(), leg=leg,
                          book=_book(), mode="paper", params=par, now=ORA, dry=False,
                          feed_fresh=True, ctx=ctx)
    assert out == "pending" and leg.status == "pending"
    ref = runner.comandi[-1]["ref"]
    runner._trattenuti.clear()
    runner.trattieni = False
    # il finto abbina subito i FOK: qui l'ordine e' ancora da eseguire (il
    # place-and-trim del motore non e' arrivato in fondo)
    riga = runner.ordine(ref)
    riga.update({"size_matched": 0.0, "size_remaining": riga["size"],
                 "average_price_matched": 0.0, "status": "EXECUTABLE"})
    return ref


def _riga(db) -> Dict[str, Any]:
    return db.trades_for_event(EVENTO)[-1]


def test_fase_errore_va_in_riconciliazione_non_annullata(runner):
    db = db_vuoto()
    ctx = E.MatchCtx(legs=[])
    par = _params(cover_rifiuti_max=1)
    leg = _gamba(1)
    ref = _taker_in_volo(runner, db, ctx, leg, par)
    _evento_errore(runner, ref)
    S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO},
                                    now_ts=ORA.timestamp() + 5, params=par)
    assert leg.needs_reconcile, f"esito ignoto dato per {leg.status}"
    r = _riga(db)
    assert r["status"] == "pending"
    assert r["meta"]["reason"] == "place_exception_reconciling"
    assert _attivita(db, "reconcile_pending")
    assert _attivita(db, "no_fill") == []
    # (a) il freno delle coperture NON avanza su un esito ignoto
    assert _conteggio(ctx) == 0 and E.copertura_bloccata(ctx) is None
    # riletto al giro dopo: resta in riconciliazione, nessun doppio log
    S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO},
                                    now_ts=ORA.timestamp() + 25, params=par)
    assert leg.needs_reconcile and len(_attivita(db, "reconcile_pending")) == 1


def test_errore_durante_l_attesa_sincrona_ritorna_riconciliazione(runner, monkeypatch):
    db = db_vuoto()
    ctx = E.MatchCtx(legs=[])
    par = _params()
    leg = _gamba(1)
    ctx.legs.append(leg)
    runner.trattieni = True
    vero = S._attendi_terminale

    def _attendi(porta, ref, timeout_s):
        runner._trattenuti.clear()
        runner.trattieni = False
        _evento_errore(runner, ref)
        return vero(porta, ref, 0.0)
    monkeypatch.setattr(S, "_attendi_terminale", _attendi)
    out = S.execute_place(db=db, market=SimpleNamespace(), info=info_vera(), leg=leg,
                          book=_book(), mode="paper", params=par, now=ORA, dry=False,
                          feed_fresh=True, ctx=ctx)
    assert out == "pending_reconcile" and leg.needs_reconcile


@pytest.mark.parametrize("finale,atteso", [("annullato", "cancelled"), ("abbinato", "open")])
def test_si_risolve_col_terminale_definitivo_senza_contare(runner, finale, atteso):
    db = db_vuoto()
    ctx = E.MatchCtx(legs=[])
    par = _params(cover_rifiuti_max=1)
    leg = _gamba(1)
    ref = _taker_in_volo(runner, db, ctx, leg, par)
    _evento_errore(runner, ref)
    S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO},
                                    now_ts=ORA.timestamp() + 5, params=par)
    assert leg.needs_reconcile
    # il runner da' poi il terminale DEFINITIVO dello stesso ordine
    if finale == "annullato":
        runner._annulla(str(runner.ordine(ref)["bet_id"]))
    else:
        runner.abbina(ref)
    S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO},
                                    now_ts=ORA.timestamp() + 10, params=par)
    assert leg.status == atteso
    assert _riga(db)["status"] == ("error" if atteso == "cancelled" else "open")
    # un ordine passato da esito ignoto e poi morto non e' un «no» del mercato
    assert _conteggio(ctx) == 0 and E.copertura_bloccata(ctx) is None


def test_fase_errore_non_chiama_il_contatore_del_freno(runner, monkeypatch):
    chiamate: List[Any] = []
    monkeypatch.setattr(S, "_esito_rifiuto_mercato",
                        lambda *a, **k: chiamate.append((a, k)) or None)
    db = db_vuoto()
    ctx = E.MatchCtx(legs=[])
    par = _params(cover_rifiuti_max=1)
    leg = _gamba(1)
    ref = _taker_in_volo(runner, db, ctx, leg, par)
    _evento_errore(runner, ref)
    S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO},
                                    now_ts=ORA.timestamp() + 5, params=par)
    runner._annulla(str(runner.ordine(ref)["bet_id"]))
    S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO},
                                    now_ts=ORA.timestamp() + 10, params=par)
    assert chiamate == [], "esito ignoto passato al contatore del freno"


def test_scadenza_della_lay_appoggiata_non_chiama_il_contatore(runner, monkeypatch):
    """(b) la lay APPOGGIATA che scade non e' un «no» del mercato a un taker:
    il contatore del freno non viene nemmeno chiamato."""
    chiamate: List[Any] = []
    monkeypatch.setattr(S, "_esito_rifiuto_mercato",
                        lambda *a, **k: chiamate.append((a, k)) or None)
    db = db_vuoto()
    ctx = E.MatchCtx(legs=[])
    par = _params(cover_rifiuti_max=1)
    leg = E.Leg(role="ko_green", market=E.MARKET_OU45, selection=E.SEL_OVER, side="lay",
                price=1.6, size=3.0, ref="ko_green-0-1", cycle_no=0,
                placed_at=ORA.timestamp())
    assert S._is_resting_leg(leg, par)
    ctx.legs.append(leg)
    S._piazza_resting_paper(db=db, market=SimpleNamespace(), info=info_vera(), leg=leg,
                            params=par, minuto=80, score="3-1", chiude=None, motivo=None,
                            ev={"event_id": EVENTO}, now=ORA, ctx=ctx)
    ref = runner.comandi[-1]["ref"]
    assert runner.comandi[-1]["time_in_force"] is None
    runner.scadi(ref)
    S._segui_ordini_paper_su_runner(db=db, ctx=ctx, ev={"event_id": EVENTO},
                                    now_ts=ORA.timestamp() + 5, params=par)
    assert leg.status == "cancelled"
    assert chiamate == [], "scadenza di una lay appoggiata passata al contatore"
    assert _conteggio(ctx) == 0
