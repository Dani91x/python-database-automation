"""06/10/2026 - Segui Live: "clicco una partita e non si carica nulla".

1. AGGANCIO A CALDO: con l'auto-follow agganciato, una partita seguita A MANO
   entra nello stream come quelle dei bot (``PianoFollow``: manuali +
   automatiche sulla stessa connessione), SENZA ricostruire il framework e
   quindi senza aspettare il flat (prima: restart rinviato finche' c'erano
   ordini vivi, cioe' per sempre con i bot al lavoro).
2. Il catalogo di una partita senza mercati si ritenta al piu' ogni
   ``MIN_RESUBSCRIBE_INTERVAL_SEC`` (il worker gira ogni 2 s).
3. Il tetto conta i mercati manuali che si SOTTOSCRIVONO (non quelli delle
   partite finite, che restano in ``market_to_event`` per il registratore).
4. ``db.register_follow`` (giro della watchlist) non riporta piu' a PENDING una
   partita manuale gia' STREAMING; una riga dell'auto-follow diventa manuale.

Finti con le chiavi vere: ``listMarketCatalogue`` (marketId, marketName,
description.marketType, runners[selectionId, runnerName, sortPriority]),
l'auto-follow VERO con un sottoscrittore con la firma di
``SottoscrittoreStream.applica``, il blotter di flumine (``live_orders``).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.stream import auto_follow as AF
from Betfair.stream import runner as R
from Betfair.stream.tests.test_auto_follow_2026_09_25 import _SottoscrittoreFinto

EV = "35800001"


def _catalogo(ev: str, n: int = 3) -> List[Dict[str, Any]]:
    """Righe di listMarketCatalogue (chiavi della API Betfair)."""
    tipi = ["MATCH_ODDS", "OVER_UNDER_25", "CORRECT_SCORE", "OVER_UNDER_35", "BOTH_TEAMS_TO_SCORE"]
    out = []
    for i in range(n):
        out.append({
            "marketId": "1.9%s%02d" % (ev[-4:], i),
            "marketName": tipi[i % len(tipi)],
            "description": {"marketType": tipi[i % len(tipi)]},
            "runners": [{"selectionId": 100 + j, "runnerName": "R%d" % j, "sortPriority": j + 1}
                        for j in range(2)],
            "event": {"id": ev},
        })
    return out


class _Rest:
    """``BetfairClient.betting_rpc`` con la firma vera."""

    def __init__(self, cataloghi: Dict[str, List[Dict[str, Any]]]) -> None:
        self.cataloghi = cataloghi
        self.chiamate: List[str] = []

    def betting_rpc(self, metodo: str, params: Dict[str, Any]) -> Any:
        assert metodo == "SportsAPING/v1.0/listMarketCatalogue"
        ev = params["filter"]["eventIds"][0]
        self.chiamate.append(ev)
        return self.cataloghi.get(ev, [])


class _Blotter:
    def __init__(self, n: int) -> None:
        self.live_orders = [object() for _ in range(n)]


@pytest.fixture
def amb(monkeypatch):
    stato: Dict[str, Any] = {"follows": [], "status": [], "upsert": [], "alert": [],
                             "stop": []}
    monkeypatch.setattr(R, "resolve_and_register", lambda rest: None)
    monkeypatch.setattr(R.db, "list_pending_follows", lambda: list(stato["follows"]))
    monkeypatch.setattr(R.db, "upsert_markets", lambda ev, ms: stato["upsert"].append(ev))
    monkeypatch.setattr(R.db, "insert_alert",
                        lambda lvl, code, msg, *a: stato["alert"].append((lvl, code, msg)))
    monkeypatch.setattr(R, "_safe_set_status",
                        lambda ev, st, *a, **k: stato["status"].append((ev, st)))
    monkeypatch.setattr(R, "_stop_framework", lambda fl: stato["stop"].append(fl))
    import Betfair.stream.raw_listener as RL
    monkeypatch.setattr(RL.RAW_STATE, "mark_resubscribe", lambda reason: None)
    session = R.LiveSession()
    session.last_resubscribe_ts = -1e9
    # i bot lavorano: ordini vivi nel blotter (il flat non arriva)
    flumine = SimpleNamespace(markets=[SimpleNamespace(market_id="1.1", blotter=_Blotter(2))])
    return SimpleNamespace(stato=stato, session=session, flumine=flumine)


def _con_auto(monkeypatch, agganciato: bool = True) -> AF.AutoFollow:
    auto = AF.AutoFollow(piano=AF.PianoFollow(180), sottoscrittore=_SottoscrittoreFinto(),
                         min_intervallo_s=0.0)
    if agganciato:
        auto.aggancia(object(), ["1.777"])
    monkeypatch.setitem(R._MOTORE, "auto", auto)
    return auto


def test_partita_manuale_entra_a_caldo_anche_con_ordini_vivi(amb, monkeypatch):
    auto = _con_auto(monkeypatch)
    amb.stato["follows"] = [{"event_id": EV, "status": "PENDING", "fixture_id": None}]
    rest = _Rest({EV: _catalogo(EV)})
    R.subscription_worker({"rest": rest}, amb.flumine, amb.session)
    # nessuna ricostruzione: ne' stop del framework ne' restart richiesto
    assert amb.stato["stop"] == [] and not amb.session.restart_requested.is_set()
    # catalogata, poller pronto (scrivera' il ladder), STREAMING
    assert EV in amb.session.cataloged_events and EV in amb.session.pollers
    assert (EV, "STREAMING") in amb.stato["status"]
    mercati = {m["marketId"] for m in _catalogo(EV)}
    assert set(amb.session.market_to_event) >= mercati
    # i mercati sono nel piano dell'auto-follow e il giro li sottoscrive a caldo
    assert auto.piano.mercati_manuali() >= mercati
    auto.giro()
    assert set(auto.sottoscrittore.chiamate[-1]) >= mercati
    assert any(c == "NEW_MATCHES" and "a caldo" in m for _l, c, m in amb.stato["alert"])


def test_senza_auto_follow_agganciato_resta_la_ricostruzione_di_sempre(amb, monkeypatch):
    _con_auto(monkeypatch, agganciato=False)
    amb.stato["follows"] = [{"event_id": EV, "status": "PENDING", "fixture_id": None}]
    rest = _Rest({EV: _catalogo(EV)})
    R.subscription_worker({"rest": rest}, amb.flumine, amb.session)
    # ordini vivi: restart rinviato (guardia flat), niente catalogo a caldo
    assert amb.stato["stop"] == [] and amb.session.sub_restart_deferred_since is not None
    assert rest.chiamate == [] and EV not in amb.session.cataloged_events


def test_catalogo_senza_mercati_non_si_ritenta_a_ogni_giro(amb, monkeypatch):
    _con_auto(monkeypatch)
    amb.stato["follows"] = [{"event_id": EV, "status": "PENDING", "fixture_id": None,
                             "open_date": "2099-01-01T12:00:00Z"}]
    rest = _Rest({})                              # mercati non ancora pubblicati
    for _ in range(5):
        R.subscription_worker({"rest": rest}, amb.flumine, amb.session)
    assert rest.chiamate == [EV]                  # una volta, non cinque
    # passato l'intervallo si ritenta
    amb.session.catalogo_a_caldo_ts[EV] -= R.MIN_RESUBSCRIBE_INTERVAL_SEC + 1
    rest.cataloghi[EV] = _catalogo(EV)
    R.subscription_worker({"rest": rest}, amb.flumine, amb.session)
    assert rest.chiamate == [EV, EV] and EV in amb.session.cataloged_events


def test_il_tetto_non_conta_le_partite_finite(amb, monkeypatch):
    """Processo lungo: 9 partite finite da 20 mercati restano nel registratore
    (180 mercati in ``market_to_event``) ma non si sottoscrivono piu'. La
    partita nuova entra (prima: REFUSE e PENDING per sempre)."""
    _con_auto(monkeypatch)
    s = amb.session
    for k in range(9):
        ev = "E-finita-%d" % k
        s.finished_events.add(ev)
        for i in range(20):
            s.market_to_event["1.8%d%02d" % (k, i)] = ev
    amb.stato["follows"] = [{"event_id": EV, "status": "PENDING", "fixture_id": None}]
    R.subscription_worker({"rest": _Rest({EV: _catalogo(EV, 5)})}, amb.flumine, s)
    assert EV in s.cataloged_events
    assert not any(c == "MARKET_CAP" for _l, c, _m in amb.stato["alert"])


def test_il_tetto_conta_le_partite_vive(amb, monkeypatch):
    """Il tetto resta vero: 180 mercati di partite VIVE + 5 nuovi = REFUSE."""
    _con_auto(monkeypatch)
    s = amb.session
    for k in range(9):
        ev = "E-viva-%d" % k
        for i in range(20):
            s.market_to_event["1.7%d%02d" % (k, i)] = ev
    amb.stato["follows"] = [{"event_id": EV, "status": "PENDING", "fixture_id": None}]
    R.subscription_worker({"rest": _Rest({EV: _catalogo(EV, 5)})}, amb.flumine, s)
    assert EV not in s.cataloged_events
    assert any(c == "MARKET_CAP" for _l, c, _m in amb.stato["alert"])


# ---------------------------------------------------------------------------
# db.register_follow: lo status di una partita gia' agganciata
# ---------------------------------------------------------------------------
class _Query:
    def __init__(self, sb: "_Sb", tabella: str) -> None:
        self.sb, self.tabella, self._filtri = sb, tabella, {}
        self._upsert = None

    def select(self, _cols: str) -> "_Query":
        return self

    def eq(self, k: str, v: Any) -> "_Query":
        self._filtri[k] = v
        return self

    def limit(self, _n: int) -> "_Query":
        return self

    def upsert(self, row: Dict[str, Any], on_conflict: str = "") -> "_Query":
        self._upsert = dict(row)
        return self

    def execute(self) -> Any:
        if self._upsert is not None:
            self.sb.upsert.append(self._upsert)
            return SimpleNamespace(data=[self._upsert])
        righe = [r for r in self.sb.righe.get(self.tabella, [])
                 if all(r.get(k) == v for k, v in self._filtri.items())]
        return SimpleNamespace(data=righe)


class _Sb:
    def __init__(self, righe: Dict[str, List[Dict[str, Any]]]) -> None:
        self.righe = righe
        self.upsert: List[Dict[str, Any]] = []

    def table(self, nome: str) -> _Query:
        return _Query(self, nome)


def _registra(monkeypatch, esistente: Any) -> Dict[str, Any]:
    from Betfair.stream import db

    sb = _Sb({"live_follow": [esistente] if esistente else []})
    monkeypatch.setattr(db, "get_supabase_client", lambda: sb)
    db.register_follow(event_id=EV, home_name="A", away_name="B",
                       open_date="2026-10-06T18:00:00Z", status="PENDING")
    return sb.upsert[-1]


def test_watchlist_non_riporta_a_pending_una_partita_gia_agganciata(monkeypatch):
    riga = _registra(monkeypatch, {"event_id": EV, "status": "STREAMING", "origine": "manuale"})
    assert riga["status"] == "STREAMING" and "origine" not in riga


def test_watchlist_su_una_riga_dell_auto_follow_la_rende_manuale(monkeypatch):
    riga = _registra(monkeypatch, {"event_id": EV, "status": "STREAMING", "origine": "auto"})
    assert riga["status"] == "PENDING" and riga["origine"] == "manuale"


def test_watchlist_su_riga_nuova_o_chiusa_resta_pending(monkeypatch):
    assert _registra(monkeypatch, None)["status"] == "PENDING"
    assert _registra(monkeypatch, {"event_id": EV, "status": "CLOSED",
                                   "origine": "manuale"})["status"] == "PENDING"
