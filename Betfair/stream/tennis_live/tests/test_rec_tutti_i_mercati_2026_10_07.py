"""REC su TUTTI i mercati dell'evento (decisione dell'utente del 07/10).

Le partite tennis con la registrazione accesa portano nello stream unico anche
gli altri mercati dell'evento (Set Betting, Set Winner, Total Games, Handicap),
sulla STESSA connessione e nella STESSA sottoscrizione dei bot. Il banco e'
quello dell'iscrizione a caldo (``test_tennis_iscrizione_a_caldo_2026_09_25``):
``Flumine`` VERO, capture e bot VERI, ``BetfairStream`` di betfairlightweight
col socket finto che registra le sottoscrizioni inviate. Il catalogo e' quello
che ``listMarketCatalogue`` restituisce: ``MarketCatalogue`` di betfairlightweight
costruiti dalle chiavi vere della Betting API (marketId, marketName,
description.marketType, runners[selectionId, runnerName, sortPriority]).

Vincoli verificati: i bot ricevono ESATTAMENTE i loro mercati (nessuno tolto,
stesso filtro dello stream, nessuno stream in piu'), le loro posizioni restano
intatte, i Match Odds non escono mai per far posto ai mercati registrati.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List

import pytest
from betfairlightweight.resources.bettingresources import MarketCatalogue

from Betfair.stream.tennis_live import iscrizione_a_caldo as IAC
from Betfair.stream.tennis_live import mercati_registrati as MR
from Betfair.stream.tennis_live import tennis_recorder as TREC
from Betfair.stream.tennis_live import tennis_runner as TR
from Betfair.stream.tennis_live.tests.test_tennis_iscrizione_a_caldo_2026_09_25 import (  # noqa: F401
    Banco, _control, _follow, banchi, db,
)

TIPI = [("SET_BETTING", "Set Betting", ["2 - 0", "2 - 1", "1 - 2", "0 - 2"]),
        ("SET_WINNER", "Set 1 Winner", ["A", "B"]),
        ("TOTAL_GAMES", "Total Games 22.5", ["Under 22.5", "Over 22.5"])]


def _catalogo(ev: str, con_mo: bool = True) -> List[MarketCatalogue]:
    righe = []
    voci = ([("MATCH_ODDS", "Match Odds", ["A", "B"])] if con_mo else []) + TIPI
    for i, (tipo, nome, runner) in enumerate(voci):
        mid = "1.%s" % ev if tipo == "MATCH_ODDS" else "1.%s%d" % (ev, i)
        righe.append(MarketCatalogue(**{
            "marketId": mid, "marketName": nome, "totalMatched": 1234.5,
            "description": {"bettingType": "ODDS", "bspMarket": False, "marketTime": "2026-09-25T10:00:00.000Z",
                            "suspendTime": "2026-09-25T10:00:00.000Z", "turnInPlayEnabled": True,
                            "marketType": tipo, "persistenceEnabled": True, "discountAllowed": True,
                            "marketBaseRate": 5.0, "wallet": "UK wallet"},
            "runners": [{"selectionId": 500 + j, "runnerName": r, "handicap": 0.0, "sortPriority": j + 1}
                        for j, r in enumerate(runner)],
        }))
    return righe


EXTRA_101 = ["1.1011", "1.1012", "1.1013"]


@pytest.fixture
def tee(monkeypatch, tmp_path):
    t = TREC.TennisRawTee()
    t.dir = str(tmp_path)
    monkeypatch.setattr(TR, "sync_record_flags", lambda follows, meta: TREC.sync_record_flags(follows, meta, tee=t))
    return t


def _con_catalogo(b: Banco, chiamate: List[str], rotto: bool = False) -> None:
    def lmc(filter: Dict[str, Any], market_projection: Any = None, sort: Any = None, max_results: Any = None):
        ev = filter["eventIds"][0]
        chiamate.append(ev)
        if rotto:
            raise RuntimeError("TOO_MUCH_DATA")
        return _catalogo(ev)
    b.session.trading.betting.list_market_catalogue = lmc


# ===========================================================================
# funzioni pure
# ===========================================================================
def test_elenco_canonico_match_odds_sempre_poi_i_registrati_sotto_il_tetto():
    metas = {"101": {"market_id": "1.101", MR.CHIAVE: [{"market_id": m} for m in EXTRA_101]},
             "102": {"market_id": "1.102"}}
    assert MR.mercati_da_sottoscrivere(metas, 180) == sorted(["1.101", "1.102"] + EXTRA_101)
    # tetto: i Match Odds non escono mai, i registrati in eccesso restano fuori
    assert MR.mercati_da_sottoscrivere(metas, 3) == ["1.101", "1.1011", "1.102"]
    assert MR.mercati_da_sottoscrivere(metas, 1) == ["1.101", "1.102"]
    # REC spento (chiave assente) o catalogo vuoto: solo i Match Odds
    assert MR.mercati_da_sottoscrivere({"101": {"market_id": "1.101", MR.CHIAVE: []}}, 180) == ["1.101"]
    # nessun doppione se il catalogo ripete il Match Odds
    assert MR.mercati_da_sottoscrivere({"101": {"market_id": "1.101", MR.CHIAVE: [{"market_id": "1.101"}]}}, 180) == ["1.101"]


def test_catalogo_dell_evento_dalla_betting_api_senza_il_match_odds():
    class _Betting:
        def list_market_catalogue(self, filter, market_projection=None, sort=None, max_results=None):
            assert filter["eventIds"] == ["101"] and filter["eventTypeIds"] == ["2"]
            assert set(market_projection) == {"RUNNER_DESCRIPTION", "MARKET_DESCRIPTION"}
            assert max_results == 200
            return _catalogo("101")

    class _Trading:
        betting = _Betting()

    out = MR.catalogo_mercati_evento(_Trading(), "101", "1.101")
    assert [x["market_id"] for x in out] == EXTRA_101
    assert [x["market_type"] for x in out] == ["SET_BETTING", "SET_WINNER", "TOTAL_GAMES"]
    assert out[1]["market_name"] == "Set 1 Winner"
    assert out[0]["selection_names"] == {"500": "2 - 0", "501": "2 - 1", "502": "1 - 2", "503": "0 - 2"}


# ===========================================================================
# REC acceso / spento a partita in corso: stessa connessione, bot intatti
# ===========================================================================
def test_rec_acceso_con_bot_in_posizione_i_mercati_entrano_e_il_bot_non_si_accorge(db, banchi, tee):
    db.controls = [_control("101", "tennis_flb", status="running")]
    b = Banco(db, [_follow("101")])
    banchi.append(b)
    chiamate: List[str] = []
    _con_catalogo(b, chiamate)
    b.book("101")
    ordine = b.posizione("101", "tennis_flb")
    flb = b.session.hosted[("101", "tennis_flb")]
    esp = b.fw.markets.markets["1.101"].blotter.get_exposures(flb, ("1.101", 11, 0.0))
    id_prima = b.stream.stream_id
    inviati_prima = len(b.socket.inviati)

    TR.record_flag_worker({}, b.fw, b.session)          # REC spento: niente
    assert len(b.socket.inviati) == inviati_prima and chiamate == []

    db.follows[0]["record"] = True
    TR.record_flag_worker({}, b.fw, b.session)
    ultimo = b.socket.inviati[-1]
    assert ultimo["op"] == "marketSubscription"
    assert ultimo["marketFilter"]["marketIds"] == sorted(["1.101"] + EXTRA_101)
    assert ultimo["id"] == id_prima + 1 == b.stream.stream_id
    assert len(b.market_stream()) == 1                   # nessuno stream / connessione in piu'
    for s in b.fw.strategies:                            # capture e bot: lo STESSO filtro
        assert s.market_filter == b.stream.market_filter
        assert list(s.stream_ids) == [b.stream.stream_id]
    # il bot e le sue posizioni non sono toccati, il suo mercato c'e' sempre
    assert b.session.hosted[("101", "tennis_flb")] is flb and not getattr(flb, "_tennis_disabled", False)
    assert getattr(flb, "_tennis_scoped_market_id", None) == "1.101"
    blotter = b.fw.markets.markets["1.101"].blotter
    assert ordine.id in [o.id for o in blotter]
    assert blotter.get_exposures(flb, ("1.101", 11, 0.0)) == esp
    # catalogo letto una volta, nomi in sessione, tee instradato su tutti i mercati
    assert chiamate == ["101"]
    assert [x["market_id"] for x in b.session.market_meta["101"][MR.CHIAVE]] == EXTRA_101
    assert all(tee.market_to_event.get(m) == "101" for m in ["1.101"] + EXTRA_101)
    assert tee._meta["101"][MR.CHIAVE][1]["market_name"] == "Set 1 Winner"

    # un secondo giro senza cambi: nessuna risottoscrizione, nessun catalogo
    n = len(b.socket.inviati)
    TR.record_flag_worker({}, b.fw, b.session)
    assert len(b.socket.inviati) == n and chiamate == ["101"]

    # REC spento: i mercati in piu' escono, il Match Odds resta
    db.follows[0]["record"] = False
    TR.record_flag_worker({}, b.fw, b.session)
    assert b.socket.inviati[-1]["marketFilter"]["marketIds"] == ["1.101"]
    assert MR.CHIAVE not in b.session.market_meta["101"]
    assert all(s.market_filter == b.stream.market_filter for s in b.fw.strategies)
    assert b.session.hosted[("101", "tennis_flb")] is flb


def test_book_di_un_mercato_registrato_non_arriva_alla_logica_del_bot(db, banchi, tee):
    db.controls = [_control("101", "tennis_flb", status="running")]
    b = Banco(db, [_follow("101", origine=None)])
    banchi.append(b)
    _con_catalogo(b, [])
    db.follows[0]["record"] = True
    TR.record_flag_worker({}, b.fw, b.session)
    msg = json.loads(json.dumps({"op": "mcm", "id": b.stream.stream_id, "clk": "AAA", "pt": 1758794401000,
                                 "initialClk": "BBB", "ct": "SUB_IMAGE", "mc": []}))
    from Betfair.stream.tennis_live.tests.test_tennis_iscrizione_a_caldo_2026_09_25 import _mcm
    sb = json.loads(_mcm(b.stream.stream_id, "1.1011", "101"))
    sb["mc"][0]["marketDefinition"]["marketType"] = "SET_BETTING"
    msg["mc"] = sb["mc"]
    b.stream._listener.on_data(json.dumps(msg))
    libri = b.stream._output_queue.get_nowait()
    flb = b.session.hosted[("101", "tennis_flb")]
    assert [lb.market_id for lb in libri] == ["1.1011"]
    assert flb.check_market_book(None, libri[0]) is False          # scope del bot
    assert b.cap.latest_for("1.101") == {}                          # il consumer del MO non lo vede
    # il tee lo registra nello STESSO file della partita
    tee.write_message(json.dumps(msg))
    with open(f"{tee.dir}/101/101.raw.jsonl", encoding="utf-8") as fh:
        righe = [json.loads(x) for x in fh if x.strip()]
    assert righe[-1]["mc"][0]["id"] == "1.1011"


def test_tetto_i_match_odds_restano_i_registrati_in_eccesso_fuori(db, banchi, tee, monkeypatch):
    monkeypatch.setenv(IAC.ENV_TETTO, "3")
    b = Banco(db, [_follow("101"), _follow("102")])
    banchi.append(b)
    _con_catalogo(b, [])
    db.follows[0]["record"] = True
    TR.record_flag_worker({}, b.fw, b.session)
    assert b.socket.inviati[-1]["marketFilter"]["marketIds"] == ["1.101", "1.1011", "1.102"]


def test_catalogo_ko_niente_cambia_e_si_riprova_dopo(db, banchi, tee):
    b = Banco(db, [_follow("101")])
    banchi.append(b)
    chiamate: List[str] = []
    _con_catalogo(b, chiamate, rotto=True)
    n = len(b.socket.inviati)
    db.follows[0]["record"] = True
    TR.record_flag_worker({}, b.fw, b.session)
    TR.record_flag_worker({}, b.fw, b.session)            # entro la finestra: niente REST
    assert len(b.socket.inviati) == n and chiamate == ["101"]
    assert MR.CHIAVE not in b.session.market_meta["101"]
    b.session.mercati_rec_ko["101"] = time.monotonic() - TR._MR_RIPROVA_S - 1
    _con_catalogo(b, chiamate)
    TR.record_flag_worker({}, b.fw, b.session)
    assert b.socket.inviati[-1]["marketFilter"]["marketIds"] == sorted(["1.101"] + EXTRA_101)


def test_stream_non_connesso_niente_cambia(db, banchi, tee):
    b = Banco(db, [_follow("101")])
    banchi.append(b)
    _con_catalogo(b, [])
    b.bs._running = False
    n = len(b.socket.inviati)
    db.follows[0]["record"] = True
    assert TR._allinea_mercati_registrati(b.fw, b.session, db.list_pending_tennis_follows()) is None
    assert len(b.socket.inviati) == n
    assert MR.CHIAVE not in b.session.market_meta["101"]


def test_partita_nuova_registrata_entra_coi_suoi_mercati_e_il_bot_resta(db, banchi, tee):
    db.controls = [_control("101", "tennis_flb", status="running")]
    b = Banco(db, [_follow("101")])
    banchi.append(b)
    _con_catalogo(b, [])
    nuova = _follow("102")
    nuova["record"] = True
    db.follows.append(nuova)
    TR.follow_worker({}, b.fw, b.session)
    attesi = sorted(["1.101", "1.102", "1.1021", "1.1022", "1.1023"])
    assert b.socket.inviati[-1]["marketFilter"]["marketIds"] == attesi
    assert all(s.market_filter == b.stream.market_filter for s in b.fw.strategies)
    assert ("101", "tennis_flb") in b.session.hosted


def test_build_i_follow_registrati_portano_i_loro_mercati(db, banchi):
    b = Banco(db, [_follow("101"), _follow("102")])
    banchi.append(b)
    chiamate: List[str] = []
    _con_catalogo(b, chiamate)
    follows = db.list_pending_tennis_follows()
    follows[1]["record"] = True
    TR._mercati_registrati_alla_build(b.session, follows)
    assert chiamate == ["102"]
    assert MR.CHIAVE not in b.session.market_meta["101"]
    assert MR.mercati_da_sottoscrivere(b.session.market_meta, IAC.tetto_mercati()) == sorted(
        ["1.101", "1.102", "1.1021", "1.1022", "1.1023"])


def test_contratto_della_build_un_solo_elenco_per_capture_ordini_e_bot():
    """``setup_and_run`` non e' eseguibile senza Betfair: si legge il sorgente,
    come ``test_fine_evento_tennis_2026_09_28`` e ``test_modo_effettivo_tennis``."""
    import inspect

    src = inspect.getsource(TR.setup_and_run)
    i_cat = src.index("_catalog_follow(session, f)")
    i_rec = src.index("_mercati_registrati_alla_build(session, follows)")
    i_lista = src.index("all_market_ids = _MR.mercati_da_sottoscrivere(session.market_meta, _IAC.tetto_mercati())")
    i_cap = src.index("shared_cap = _make_capture(all_market_ids[0], \"*\", market_ids=all_market_ids)")
    assert i_cat < i_rec < i_lista < i_cap
    assert "capture_degli_ordini(shared_cap, mode, data_filter, all_market_ids)" in src
    assert "data_filter, mode, market_ids=all_market_ids," in src
