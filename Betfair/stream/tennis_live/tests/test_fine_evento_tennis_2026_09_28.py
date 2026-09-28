# -*- coding: utf-8 -*-
"""CANTIERE A "FINE EVENTO" (28/09/2026) - tennis.

Ordine dell'utente (testuale): "le partite TERMINATE sia calcio che tennis non
devono piu' essere seguite ovviamente". Il segnale certo e' il CLOSED del
MATCH_ODDS (documentazione Betfair: "CLOSED - The market has been settled and
is no longer available for betting"), che il runner scrive su
``tennis_live_now`` dal 26/09 (R-FA-1, ``0dbc127``). Cosa certifica:
  * PONTE: una partita FINITA seguita A MANO si chiude (righe in chiusura,
    follow CLOSED a righe ferme) e nessun bot vi si arma; una AUTOMATICA si
    chiude anche a scanner fermo (il CLOSED viene dallo stream, non dallo
    scanner); una riga armata su una partita finita SENZA follow attivo va a
    'stopped' (nessun runner la ospita: 'stopping' resterebbe per sempre);
  * PONTE, ensure: una riga armata su una partita finita non riapre il follow;
  * RUNNER, riavvio: partita iniziata e mercato non in catalogo (CLOSED) ->
    follow CLOSED e ``tennis_live_now`` CLOSED, SENZA relogin (prima: un login
    per partita finita e follow ERROR che il ponte ricreava); partita futura
    senza catalogo -> la strada di sempre;
  * DB: ``chiudi_tennis_now`` e' un UPDATE (punteggio conservato), riga minima
    CLOSED solo se non c'era; ``tennis_live_now`` orfane chiuse all'avvio.

Finti: ``_Db`` di ``test_tennis_chiusura_2026_09_26`` (firme e chiavi di
``tennis_db`` e delle tabelle vere). Nessuna rete, nessun DB.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from Betfair.stream.tennis_live import tennis_bot_service as S
from Betfair.stream.tennis_live import tennis_db as TDB
from Betfair.stream.tennis_live import tennis_runner as TR
from Betfair.stream.tennis_live.tests.test_tennis_chiusura_2026_09_26 import (  # noqa: F401
    EV, _Db, _control, _follow, _servizio, orologio)


# ===========================================================================
# 1. PONTE: la partita finita non si segue piu'
# ===========================================================================
def test_ponte_la_seguita_a_mano_FINITA_si_chiude(orologio):
    db = _Db([_servizio()], controls=[_control(EV)], follows=[_follow(EV, "manuale")],
             feed_ev=[], now_status={EV: "CLOSED"}, clock=orologio)
    S.riconcilia_interruttori(db)
    assert db.stati == [(EV, "tennis_flb", "stopping")], \
        "il bot armato a mano su una partita finita va in chiusura"
    assert db.follow_status == [], "il follow si chiude a righe ferme"
    for r in db.controls:
        r["status"] = "stopped"          # il runner: flat verificato
    orologio.t += 15
    S.riconcilia_interruttori(db)
    assert db.follow_status == [(EV, "CLOSED")]
    assert db.armati == [], "mai riarmata"


def test_ponte_non_arma_una_partita_a_mano_finita(orologio):
    db = _Db([_servizio()], controls=[], follows=[_follow(EV, "manuale")],
             feed_ev=[], now_status={EV: "CLOSED"}, clock=orologio)
    S.riconcilia_interruttori(db)
    assert db.armati == []
    assert db.follow_status == [(EV, "CLOSED")], "nessuna riga la occupa: si chiude subito"


def test_ponte_a_mano_viva_si_arma_come_prima(orologio):
    """Il contrario: a mano, mercato OPEN -> armata come sempre."""
    db = _Db([_servizio()], controls=[], follows=[_follow(EV, "manuale")],
             feed_ev=[], now_status={EV: "OPEN"}, clock=orologio)
    S.riconcilia_interruttori(db)
    assert [r["event_id"] for r in db.armati] == [EV] and db.follow_status == []


def test_ponte_finita_si_chiude_anche_a_scanner_fermo(orologio):
    db = _Db([_servizio()], controls=[_control(EV)], follows=[_follow(EV, "auto")],
             feed_ev=[], now_status={EV: "CLOSED"}, clock=orologio)
    db.scanner_vivo = False
    S.riconcilia_interruttori(db)
    assert db.stati == [(EV, "tennis_flb", "stopping")]


def test_ponte_auto_mode_non_arma_una_partita_del_feed_gia_finita(orologio):
    """Il feed puo' portare ancora per un giro una partita appena chiusa
    (scanner che rinfresca ogni pochi secondi): se il runner ha gia' scritto
    CLOSED non si arma."""
    db = _Db([_servizio()], controls=[], follows=[], feed_ev=[EV, "2"],
             now_status={EV: "CLOSED"}, clock=orologio)
    db.follows.append(_follow(EV, "auto"))
    S.riconcilia_interruttori(db)
    assert [r["event_id"] for r in db.armati] == ["2"]


def test_ponte_riga_armata_su_partita_finita_senza_follow_va_a_stopped(orologio):
    db = _Db([_servizio()], controls=[_control(EV)], follows=[],
             feed_ev=[], now_status={EV: "CLOSED"}, clock=orologio)
    S.riconcilia_interruttori(db)
    assert db.stati == [(EV, "tennis_flb", "stopped")], \
        "nessun runner la ospita: 'stopping' resterebbe per sempre"


def test_ponte_bot_spento_riga_su_partita_finita_senza_follow(orologio):
    db = _Db([_servizio(status="stopped")], controls=[_control(EV)], follows=[],
             feed_ev=[], now_status={EV: "CLOSED"}, clock=orologio)
    S.riconcilia_interruttori(db)
    assert db.stati == [(EV, "tennis_flb", "stopped")]


def test_ponte_stato_non_letto_non_chiude_niente(orologio):
    db = _Db([_servizio()], controls=[_control(EV)], follows=[_follow(EV, "manuale")],
             feed_ev=[], now_status={EV: "CLOSED"}, clock=orologio)
    db.list_tennis_now_status = lambda ids: None          # type: ignore[assignment]
    S.riconcilia_interruttori(db)
    assert db.stati == [] and db.follow_status == []


def test_ensure_non_riapre_il_follow_di_una_partita_finita(monkeypatch):
    creati: List[str] = []
    monkeypatch.setattr(TDB, "list_tennis_bot_controls",
                        lambda event_id=None, statuses=None: [_control("F"), _control("V")])
    monkeypatch.setattr(TDB, "list_pending_tennis_follows", lambda: [])
    monkeypatch.setattr(TDB, "list_tennis_now_status",
                        lambda ids: {"F": "CLOSED", "V": "OPEN"})
    monkeypatch.setattr(TDB, "get_tennis_client", lambda: object())
    monkeypatch.setattr(S, "_market_row_for", lambda sb, ev: {
        "event_id": ev, "market_id": "1.%s" % ev, "player1": {"name": "A"},
        "player2": {"name": "B"}, "competition_name": "ATP", "open_date": None})
    monkeypatch.setattr(TDB, "register_tennis_follow",
                        lambda **kw: creati.append(kw["event_id"]))
    assert S.ensure_follows_for_bots() == ["V"]
    assert creati == ["V"]


# ===========================================================================
# 2. RUNNER al riavvio: mercato non in catalogo a partita iniziata = finita
# ===========================================================================
class _Betting:
    """``trading.betting.list_market_catalogue`` di betfairlightweight."""

    def __init__(self, risposte: List[Any]) -> None:
        self.risposte = list(risposte)
        self.chiamate = 0

    def list_market_catalogue(self, **_kw: Any) -> Any:
        self.chiamate += 1
        r = self.risposte.pop(0) if self.risposte else []
        if isinstance(r, Exception):
            raise r
        return r


def _sessione(risposte: List[Any]) -> Any:
    logins: List[int] = []
    trading = SimpleNamespace(betting=_Betting(risposte), login=lambda: logins.append(1))
    sess = TR.TennisLiveSession(trading)
    return sess, logins


def _riga_follow(open_date: Optional[str]) -> Dict[str, Any]:
    f = _follow(EV, "manuale")
    f["open_date"] = open_date
    return f


@pytest.fixture
def scritture(monkeypatch):
    reg: Dict[str, Any] = {"follow": [], "now": [], "alert": [], "soldi": None}
    monkeypatch.setattr(TR.tennis_db, "set_tennis_follow_status",
                        lambda ev, st, err=None: reg["follow"].append((ev, st)))
    monkeypatch.setattr(TR.tennis_db, "chiudi_tennis_now",
                        lambda ev: reg["now"].append(ev) or None)

    def _soldi(ev, market_id=None):
        if isinstance(reg["soldi"], Exception):
            raise reg["soldi"]
        return reg["soldi"]
    monkeypatch.setattr(TR.tennis_db, "soldi_sull_evento_tennis", _soldi)
    import Betfair.stream.db as _DB
    monkeypatch.setattr(_DB, "insert_alert",
                        lambda lv, code, msg, ev=None: reg["alert"].append((lv, code, ev)))
    return reg


def _iso(delta_min: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=delta_min)).isoformat()


def _scorri(sess: Any, secondi: float) -> None:
    st = TR._stato_fine(sess)
    for k in ("vuoto_dal", "trattenute"):
        for ev in list(st[k]):
            st[k][ev] -= secondi


def test_riavvio_partita_finita_ad_app_spenta_follow_closed_senza_relogin(scritture):
    """Guardia di CONFERMA: alla prima lettura vuota niente; alla seconda,
    FINE_CONFERMA_S dopo, follow CLOSED senza relogin. Fra le due nessuna
    chiamata REST (il follow_worker ripassa ogni 20 s)."""
    sess, logins = _sessione([[], [], []])
    f = _riga_follow(_iso(-90))
    assert TR._risolvi_follow(sess, f) is None
    assert scritture["follow"] == [] and scritture["now"] == [], "mai alla prima lettura"
    assert TR._risolvi_follow(sess, f) is None
    assert sess.trading.betting.chiamate == 1, "prima del momento nessuna lettura"
    assert TR.fine_da_rileggere(sess, EV, time.monotonic()) is False
    _scorri(sess, TR.FINE_CONFERMA_S + 1)
    assert TR._risolvi_follow(sess, f) is None
    assert scritture["follow"] == [(EV, "CLOSED")]
    assert scritture["now"] == [EV], "tennis_live_now CLOSED: il ponte non la riapre"
    assert logins == [] and sess.trading.betting.chiamate == 2, "nessun relogin"


def test_riavvio_mercato_tornato_in_catalogo_annulla_la_conferma(scritture):
    mo = SimpleNamespace(market_id="1.%s" % EV, runners=[], event=SimpleNamespace(id=EV),
                         competition=SimpleNamespace(name="ATP"))
    sess, _l = _sessione([[], [mo]])
    f = _riga_follow(_iso(-90))
    assert TR._risolvi_follow(sess, f) is None
    _scorri(sess, TR.FINE_CONFERMA_S + 1)
    meta = TR._risolvi_follow(sess, f)
    assert meta is not None and meta["market_id"] == "1.%s" % EV
    assert TR._stato_fine(sess) == {"vuoto_dal": {}, "trattenute": {}}
    assert scritture["follow"] == []


def test_riavvio_soldi_dentro_la_partita_resta_seguita(scritture):
    sess, _l = _sessione([[], [], [], []])
    f = _riga_follow(_iso(-90))
    scritture["soldi"] = "1 posizioni aperte sulla partita (live)"
    TR._risolvi_follow(sess, f)
    _scorri(sess, TR.FINE_CONFERMA_S + 1)
    TR._risolvi_follow(sess, f)
    assert scritture["follow"] == [] and scritture["now"] == []
    assert scritture["alert"] == [("CRITICAL", "FINE_PARTITA_CON_SOLDI", EV)]
    assert TR._risolvi_follow(sess, f) is None and sess.trading.betting.chiamate == 2, \
        "trattenuta: niente REST prima del ricontrollo"
    scritture["soldi"] = None
    _scorri(sess, TR.FINE_RIVERIFICA_SOLDI_S + 1)
    TR._risolvi_follow(sess, f)
    assert scritture["follow"] == [(EV, "CLOSED")] and len(scritture["alert"]) == 1


def test_riavvio_soldi_non_verificabili_valgono_soldi(scritture):
    sess, _l = _sessione([])
    scritture["soldi"] = RuntimeError("DB KO")
    f = _riga_follow(_iso(-90))
    assert TR._valuta_catalogo_vuoto_tennis(sess, f, 1000.0) == "in_conferma"
    assert TR._valuta_catalogo_vuoto_tennis(sess, f, 1000.0 + TR.FINE_CONFERMA_S) == "trattenuta"
    assert scritture["follow"] == []


def test_follow_worker_freddo_non_ricostruisce_in_conferma(monkeypatch):
    """Senza iscrizione a caldo: la partita in conferma NON chiede una
    ricostruzione a ogni giro del follow_worker."""
    sess, _l = _sessione([])
    TR._stato_fine(sess)["vuoto_dal"][EV] = time.monotonic()
    richieste: List[str] = []
    monkeypatch.setattr(TR.tennis_db, "list_pending_tennis_follows",
                        lambda: [_riga_follow(_iso(-90))])
    monkeypatch.setattr(TR, "_caldo_attivo", lambda fw, s: None)
    monkeypatch.setattr(TR, "_request_restart",
                        lambda fw, s, motivo, forza=True: richieste.append(motivo))
    TR.follow_worker({}, None, sess)
    assert richieste == []
    _scorri(sess, TR.FINE_CONFERMA_S + 1)
    TR.follow_worker({}, None, sess)
    assert len(richieste) == 1


def test_riavvio_partita_futura_senza_catalogo_strada_di_sempre(scritture):
    sess, logins = _sessione([[], []])
    assert TR._risolvi_follow(sess, _riga_follow(_iso(+90))) is None
    assert logins == [1] and scritture["follow"] == [(EV, "ERROR")]
    assert scritture["now"] == []


def test_riavvio_errore_di_sessione_resta_relogin(scritture):
    """Un errore VERO (sessione scaduta) non e' "catalogo vuoto": relogin e
    retry come prima, anche a partita iniziata."""
    sess, logins = _sessione([RuntimeError("INVALID_SESSION_INFORMATION"), []])
    assert TR._risolvi_follow(sess, _riga_follow(_iso(-90))) is None
    assert logins == [1]
    assert scritture["follow"] == [(EV, "ERROR")]


# ===========================================================================
# 3. DB: tennis_live_now chiusa con UPDATE, orfane chiuse all'avvio
# ===========================================================================
from Betfair.stream.tests.test_fine_evento_2026_09_28 import _SbFinto  # noqa: E402


def _now_tennis(ev: str, inplay: bool, status: str) -> Dict[str, Any]:
    """Riga di ``tennis_live_now`` (colonne di tennis_live.sql)."""
    return {"event_id": ev, "inplay": inplay, "status": status,
            "state": {"markets": [], "order_mode": "PAPER"},
            "score": {"sets": [6, 4]}, "points": [], "updated_at": "2026-09-26T09:00:00+00:00"}


def test_chiudi_tennis_now_update_e_riga_minima_solo_se_assente(monkeypatch):
    sb = _SbFinto({"tennis_live_now": [_now_tennis(EV, True, "SUSPENDED")]})
    pubblicati: List[tuple] = []
    monkeypatch.setattr(TDB, "get_tennis_client", lambda: sb)
    import Betfair.stream.local_channel as LC
    monkeypatch.setattr(LC, "publish", lambda t, d: pubblicati.append((t, d)))
    riga = TDB.chiudi_tennis_now(EV)
    assert riga["status"] == "CLOSED" and riga["inplay"] is False
    assert riga["score"] == {"sets": [6, 4]}, "punteggio conservato"
    assert sb.scritture == [("tennis_live_now", "update", [EV])]
    riga2 = TDB.chiudi_tennis_now("NUOVA")
    assert riga2["status"] == "CLOSED" and riga2["state"] == {"markets": []}
    assert sb.scritture[-1] == ("tennis_live_now", "upsert", "NUOVA")
    assert [p[0] for p in pubblicati] == ["now", "now"]


def test_tennis_now_orfane_chiuse_all_avvio(monkeypatch):
    now = [_now_tennis("A", True, "SUSPENDED"), _now_tennis("B", True, "OPEN"),
           _now_tennis("C", False, "CLOSED")]
    follow = [{"event_id": "A", "status": "ERROR"}, {"event_id": "B", "status": "STREAMING"},
              {"event_id": "C", "status": "CLOSED"}]
    sb = _SbFinto({"tennis_live_now": now, "tennis_live_follow": follow})
    monkeypatch.setattr(TDB, "get_tennis_client", lambda: sb)
    now.append(_now_tennis("Z", True, "OPEN"))   # nessun follow letto (FK: impossibile)
    assert TDB.chiudi_tennis_now_orfani() == 1
    assert sb.scritture == [("tennis_live_now", "update", ["A"])]
    assert now[1]["inplay"] is True and now[1]["status"] == "OPEN"
    assert now[3]["status"] == "OPEN", "senza follow terminale letto non si tocca"


def _ordine_t(stato: str) -> Dict[str, Any]:
    """Riga di ``tennis_live_orders`` (chiavi della migrazione tennis_orders.sql)."""
    return {"event_id": EV, "mode": "paper", "market_id": "1.%s" % EV, "status": stato,
            "size_remaining": 2.0}


def _pos_t(win: float, lose: float) -> Dict[str, Any]:
    """Riga di ``tennis_live_positions``."""
    return {"event_id": EV, "mode": "live", "market_id": "1.%s" % EV, "selection_id": 11,
            "handicap": 0, "matched_if_win": win, "matched_if_lose": lose,
            "unmatched_back_exposure": 0.0, "unmatched_lay_exposure": 0.0}


def test_soldi_sull_evento_tennis_fonti_vere(monkeypatch):
    def _db(**tab: Any) -> None:
        base = {"tennis_live_orders": [], "tennis_live_positions": [],
                "tennis_live_order_queue": []}
        base.update(tab)
        sb = _SbFinto(base)
        monkeypatch.setattr(TDB, "get_tennis_client", lambda: sb)
    mid = "1.%s" % EV
    _db()
    assert TDB.soldi_sull_evento_tennis(EV, mid) is None
    _db(tennis_live_orders=[_ordine_t("EXECUTABLE")])
    assert TDB.soldi_sull_evento_tennis(EV, mid) == "1 ordini vivi sulla partita (paper)"
    _db(tennis_live_orders=[_ordine_t("EXECUTION_COMPLETE")])
    assert TDB.soldi_sull_evento_tennis(EV, mid) is None
    _db(tennis_live_positions=[_pos_t(4.0, -2.0)])
    assert TDB.soldi_sull_evento_tennis(EV, mid) == "1 posizioni aperte sulla partita (live)"
    _db(tennis_live_positions=[_pos_t(0.5, 0.5)])
    assert TDB.soldi_sull_evento_tennis(EV, mid) is None
    _db(tennis_live_order_queue=[{"event_id": "q", "id": 1, "status": "pending",
                                  "payload": {"market_id": mid, "side": "BACK"}}])
    assert TDB.soldi_sull_evento_tennis(EV, mid) == "1 comandi in coda sulla partita"
    _db(tennis_live_order_queue=[{"event_id": "q", "id": 1, "status": "pending",
                                  "payload": {"market_id": "1.altro"}}])
    assert TDB.soldi_sull_evento_tennis(EV, mid) is None


# ===========================================================================
# 4. USCITA ORDINATA e ARRESTO dell'app
# ===========================================================================
def test_uscita_ordinata_tennis(monkeypatch):
    stati: List[tuple] = []
    monkeypatch.setattr(TR.tennis_db, "set_tennis_follow_status",
                        lambda ev, st, err=None: stati.append((ev, st)))
    sess = TR.TennisLiveSession(trading=None)
    for ev in ("FIN", "MAN", "AUT", "CMD"):
        sess.market_meta[ev] = {"market_id": "1." + ev}
    sess.now_chiusi.add("FIN")
    sess.ultimi_follows = [_follow("FIN", "manuale"), _follow("MAN", "manuale"),
                           _follow("AUT", "auto")]
    # ricambio del processo (vita massima/stallo): le vive PENDING, auto comprese
    assert TR.chiudi_alla_uscita_tennis(sess) == {"chiusi": ["FIN"],
                                                  "in_attesa": ["AUT", "MAN"]}
    assert ("CMD", "PENDING") not in stati, "partita di un comando: nessuna riga"
    stati.clear()
    sess.arresto_ordinato = True           # spegnimento dell'app
    assert TR.chiudi_alla_uscita_tennis(sess) == {"chiusi": ["AUT", "FIN"],
                                                  "in_attesa": ["MAN"]}
    assert ("MAN", "STREAMING") not in stati


def test_arresto_ordinato_worker_tennis(monkeypatch, tmp_path):
    from Betfair.stream import arresto_ordinato as AO
    monkeypatch.setenv("APP_ARRESTO_DIR", str(tmp_path))
    fermati: List[Any] = []
    monkeypatch.setattr(TR, "_stop_framework", lambda fw: fermati.append(fw))
    sess = TR.TennisLiveSession(trading=None)
    TR.arresto_worker({}, "FW", sess)
    assert fermati == []
    AO.richiedi()
    TR.arresto_worker({}, "FW", sess)
    assert fermati == ["FW"] and sess.shutdown_requested.is_set()
    assert sess.arresto_ordinato is True and sess.planned_restart is False
    import inspect
    src = inspect.getsource(TR.setup_and_run)
    i = src.index("while not interrupted:")
    assert "if _AO.richiesto():" in src[i:i + 500]
    assert "function=arresto_worker" in src
    assert "chiudi_alla_uscita_tennis(session)" in src.split("    finally:")[-1]
