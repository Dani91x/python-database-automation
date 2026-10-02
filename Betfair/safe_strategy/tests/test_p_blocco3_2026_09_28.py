"""CANTIERE P (28/09/2026) - blocco 3: timeout del DB, R-2 lato Safe, tennis al
minimo su ogni strada.

  5. il profilo bot del timeout PostgREST (5 s / 20 s, ``db_client.usa_timeout_bot``)
     si accende all'avvio di Omega (``omega_service.main``) e dello scanner
     (``safe_strategy/service.py`` ``main``), PRIMA di qualunque lettura;
  6. R-2: il ``cor`` (customerOrderRef di flumine) dell'evento ``order`` si
     salva in ``meta.canale_cor`` alla PRIMA vista; la riconciliazione lo usa
     come ref in piu' (``X.reconcile_decision``, ``certificazione_k.ref_di_riga``,
     ``_cleared_match``); la memoria del canale non lo perde agli eventi dopo;
     senza ``cor`` nulla cambia;
  7. apertura Safe TENNIS sotto il minimo -> AL minimo (BACK 2,00 / LAY 0,50) su
     coda e REST live, chiusure esatte; calcio invariato; senza la funzione di
     D2 comportamento di prima e avviso nel log.
I finti: righe e ordini con le chiavi di ``bot_db``/``omega_market``; il motore
del minimo e' la funzione pura del cantiere D2 riprodotta sul suo contratto
(``place_min_size``) finche' D2 non e' su master. ASCII-only.
"""
# minimi .it definitivi 01/10: punta 1,00 / banca 1,00 / trim >= 0,50 (il 'sotto minimo' dei test e' 0,72/0,70, il minimo 1,00)
from __future__ import annotations

import sys
from datetime import timedelta

import pytest

from Betfair.omega import omega_market as M
from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import certificazione_k as K
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import porta_ordini as PO
from Betfair.safe_strategy.tests.test_bot_service import (
    NOW, FakeDB, FakeMarket, _reset_module_state,
)


class _Basta(Exception):
    pass


@pytest.fixture(autouse=True)
def _pulito():
    _reset_module_state()
    yield
    _reset_module_state()


# ---------------------------------------------------------------------------
# 5. timeout del DB all'avvio di Omega e dello scanner
# ---------------------------------------------------------------------------
def test_omega_main_accende_il_profilo_bot_prima_di_tutto(monkeypatch):
    import db_client
    from Betfair.omega import omega_service as OS

    visto: list = []
    monkeypatch.setattr(db_client, "usa_timeout_bot", lambda: visto.append("timeout") or "T")
    monkeypatch.setattr(OS, "_acquire_single_instance_lock", lambda: object())

    def _canale():
        visto.append("canale")
        raise _Basta()

    monkeypatch.setattr(OS, "_avvia_canale", _canale)
    with pytest.raises(_Basta):
        OS.main()
    assert visto == ["timeout", "canale"]


def test_scanner_main_accende_il_profilo_bot_prima_del_client(monkeypatch):
    import db_client
    from Betfair.safe_strategy import service as SV

    visto: list = []
    monkeypatch.setattr(db_client, "usa_timeout_bot", lambda: visto.append("timeout") or "T")
    monkeypatch.setattr(SV, "acquire_single_instance_lock", lambda *a, **k: object())

    def _client(**kw):
        visto.append("client")
        raise _Basta()

    monkeypatch.setattr(SV, "build_client", _client)
    monkeypatch.setattr(sys, "argv", ["service.py"])
    with pytest.raises(_Basta):
        SV.main()
    assert visto == ["timeout", "client"]


def test_scanner_main_non_muore_se_il_profilo_non_si_applica(monkeypatch):
    import db_client
    from Betfair.safe_strategy import service as SV

    def _rotto():
        raise RuntimeError("env rotto")

    monkeypatch.setattr(db_client, "usa_timeout_bot", _rotto)
    monkeypatch.setattr(SV, "acquire_single_instance_lock", lambda *a, **k: object())
    monkeypatch.setattr(SV, "build_client", lambda **kw: (_ for _ in ()).throw(_Basta()))
    monkeypatch.setattr(sys, "argv", ["service.py"])
    with pytest.raises(_Basta):
        SV.main()


# ---------------------------------------------------------------------------
# 6. R-2: il cor di flumine
# ---------------------------------------------------------------------------
COR = "a1b2c3d4e5f6-1727540000123"


def _riga_live_canale(db, *, mode="live", tid_meta=None):
    tid = db.insert_trade({
        "event_id": "1.1", "market_id": "1.250", "selection_id": 47972, "side": "back",
        "price": 2.5, "size": 4.0, "status": "pending", "mode": mode, "sport": "calcio",
        "placed_at": NOW.isoformat(),
        "meta": {"phase": "canale_wait", "canale_ref": "safe-t1",
                 "canale_inviato_at": NOW.isoformat(), **(tid_meta or {})}})
    return tid


class _PortaFinta:
    """Stessa interfaccia di ``PortaCanale`` per la lettura degli esiti."""

    def __init__(self, eventi):
        self.eventi = eventi

    def esiti(self, ref):
        return self.eventi.get(ref)


def _evento(fase="accettato_betfair", seq=10, cor=COR, mode="live"):
    ev = {"ref": "safe-t1", "fase": fase, "seq": seq, "mode": mode, "bet_id": "B9",
          "size": 4.0, "size_matched": 0.0, "size_remaining": 4.0,
          "average_price_matched": 0.0, "matched_at": None}
    if cor is not None:
        ev["cor"] = cor
    return ev


def test_cor_salvato_alla_prima_vista(monkeypatch):
    db = FakeDB(mode="live")
    tid = _riga_live_canale(db)
    monkeypatch.setattr(PO, "porta_esistente", lambda sport: _PortaFinta({"safe-t1": _evento()}))
    S._risolvi_una_via_canale(db, db.get_trade(tid), now=NOW, os_mod=None)
    assert db.get_trade(tid)["meta"]["canale_cor"] == COR
    # alla seconda vista (stesso cor) nessuna riscrittura del marcatore
    scritture = []
    vero = db.update_trade
    monkeypatch.setattr(db, "update_trade",
                        lambda i, **f: scritture.append(f) or vero(i, **f))
    S._risolvi_una_via_canale(db, db.get_trade(tid), now=NOW, os_mod=None)
    assert not [f for f in scritture if (f.get("meta") or {}).get("canale_cor") and
                "canale_fase" not in (f.get("meta") or {})]


def test_ordine_nuovo_della_stessa_riga_aggiorna_il_cor_e_tiene_lo_storico(monkeypatch):
    """Il place-and-trim RIPIAZZA (nuovo ordine, nuovo customerOrderRef di
    flumine) sulla STESSA riga: il cor corrente si aggiorna, il vecchio resta
    nello storico e la riconciliazione trova l'ordine con l'uno o l'altro."""
    db = FakeDB(mode="live")
    tid = _riga_live_canale(db)
    eventi = {"safe-t1": _evento(seq=10)}
    monkeypatch.setattr(PO, "porta_esistente", lambda sport: _PortaFinta(eventi))
    S._risolvi_una_via_canale(db, db.get_trade(tid), now=NOW, os_mod=None)
    nuovo = "a1b2c3d4e5f6-1727540000999"
    eventi["safe-t1"] = _evento(seq=11, cor=nuovo)
    S._risolvi_una_via_canale(db, db.get_trade(tid), now=NOW, os_mod=None)
    meta = db.get_trade(tid)["meta"]
    assert meta["canale_cor"] == nuovo and meta["canale_cor_storico"] == [COR]
    riga = db.get_trade(tid)
    assert X.cor_di_riga(riga) == [nuovo, COR]
    assert COR in K.ref_di_riga(riga) and nuovo in K.ref_di_riga(riga)
    vecchio = (NOW - timedelta(minutes=10)).isoformat()
    tr = {**riga, "placed_at": vecchio}
    for c in (nuovo, COR):
        d = X.reconcile_decision(tr, [_ordine_betfair(c)], [], NOW.isoformat(), ref="safe-t1")
        assert d["action"] == "confirm", c


def test_evento_senza_cor_non_cambia_nulla(monkeypatch):
    db = FakeDB(mode="live")
    tid = _riga_live_canale(db)
    monkeypatch.setattr(PO, "porta_esistente",
                        lambda sport: _PortaFinta({"safe-t1": _evento(cor=None)}))
    S._risolvi_una_via_canale(db, db.get_trade(tid), now=NOW, os_mod=None)
    assert "canale_cor" not in db.get_trade(tid)["meta"]


def test_evento_dell_altra_modalita_non_lascia_il_suo_cor(monkeypatch):
    db = FakeDB(mode="live")
    tid = _riga_live_canale(db)
    monkeypatch.setattr(PO, "porta_esistente",
                        lambda sport: _PortaFinta({"safe-t1": _evento(mode="paper")}))
    S._risolvi_una_via_canale(db, db.get_trade(tid), now=NOW, os_mod=None)
    assert "canale_cor" not in db.get_trade(tid)["meta"]


def _ordine_betfair(cor, matched=4.0):
    """Riga di ``list_current_orders`` normalizzata da ``omega_market``."""
    return {"bet_id": "B9", "market_id": "1.250", "selection_id": 47972, "side": "back",
            "size_matched": matched, "size_remaining": 0.0, "avg_price_matched": 2.52,
            "customer_order_ref": cor}


def test_reconcile_decision_ritrova_l_ordine_per_cor():
    vecchio = (NOW - timedelta(minutes=10)).isoformat()
    tr = {"id": 1, "market_id": "1.250", "selection_id": 47972, "side": "back",
          "price": 2.5, "placed_at": vecchio, "meta": {"canale_cor": COR}}
    d = X.reconcile_decision(tr, [_ordine_betfair(COR)], [], NOW.isoformat(), ref="safe-t1")
    assert d["action"] == "confirm" and d["size"] == 4.0 and d["bet_id"] == "B9"
    # senza canale_cor: l'ordine (col ref di flumine) NON e' riconosciuto
    senza = {**tr, "meta": {}}
    assert X.reconcile_decision(senza, [_ordine_betfair(COR)], [], NOW.isoformat(),
                                ref="safe-t1")["action"] == "free"
    # un cor di UN'ALTRA riga non conferma mai questa
    altra = {**tr, "meta": {"canale_cor": "zzz-1"}}
    assert X.reconcile_decision(altra, [_ordine_betfair(COR)], [], NOW.isoformat(),
                                ref="safe-t1")["action"] == "free"


def test_refs_di_riconciliazione_senza_cor_invariati():
    assert X.refs_di_riconciliazione({"meta": {}}, "safe-t1") == "safe-t1"
    assert X.refs_di_riconciliazione({}, ["a", "b"]) == ["a", "b"]
    assert X.refs_di_riconciliazione({"meta": {"canale_cor": COR}}, "safe-t1") == ["safe-t1", COR]


def test_ref_di_riga_del_banco_include_il_cor():
    riga = {"id": 1, "sport": "calcio", "meta": {"canale_cor": COR}}
    assert COR in K.ref_di_riga(riga) and "safe-t1" in K.ref_di_riga(riga)


def test_cleared_match_per_cor():
    riga = {"id": 1, "mode": "live", "meta": {"canale_cor": COR}}
    by_bet, by_ref = X._cleared_index([{"customer_order_ref": COR, "profit": 1.2}])
    assert X._cleared_match(riga, by_bet, by_ref, table_prefix="safe")["profit"] == 1.2
    assert X._cleared_match({**riga, "meta": {}}, by_bet, by_ref, table_prefix="safe") is None


def test_la_memoria_del_canale_conserva_il_cor_del_primo_evento():
    mem = PO.MemoriaComandi()
    mem.ricevi_evento({**_evento(fase="inviato", seq=1), "ref": "safe-t1"})
    mem.ricevi_evento({**_evento(fase="accettato_betfair", seq=2, cor=None), "ref": "safe-t1"})
    assert mem.esito("safe-t1")["cor"] == COR
    assert mem.esito("safe-t1")["fase"] == "accettato_betfair"


def test_riga_live_senza_eventi_si_ritrova_su_betfair_per_cor(monkeypatch):
    """Il caso del reperto: riga LIVE mandata sul canale, cor gia' visto, poi
    nessun evento oltre la scadenza -> ``reconcile_pending`` la cerca su
    Betfair e la ritrova col ref di flumine (prima: 'free', riga persa)."""
    db = FakeDB(mode="live")
    vecchio = (NOW - timedelta(minutes=10)).isoformat()
    tid = _riga_live_canale(db, tid_meta={"canale_cor": COR})
    db.update_trade(tid, placed_at=vecchio,
                    meta={**db.get_trade(tid)["meta"], "canale_inviato_at": vecchio})
    monkeypatch.setattr(PO, "porta_esistente", lambda sport: _PortaFinta({}))

    class Mercato(FakeMarket):
        def list_current_orders(self):
            return [_ordine_betfair(COR)]

        def list_cleared_orders(self):
            return []

    S.reconcile_pending(market=Mercato(), db=db, now=NOW)
    t = db.get_trade(tid)
    assert t["status"] == "open" and float(t["size"]) == 4.0


# ---------------------------------------------------------------------------
# 7. tennis: apertura sotto il minimo portata AL minimo su ogni strada
# ---------------------------------------------------------------------------
def _porta_al_minimo_d2(jurisdiction, side, size):
    """Contratto di ``submin.porta_al_minimo_apertura`` (cantiere D2)."""
    from Betfair.stream.trading.submin import place_min_size

    s = round(float(size), 2)
    m = round(float(place_min_size(jurisdiction, side)), 2)
    return m if s < m - 1e-9 else s


@pytest.fixture
def con_d2(monkeypatch):
    monkeypatch.setattr(X, "_PORTA_AL_MINIMO", _porta_al_minimo_d2)


class _MercatoConSubmin(FakeMarket):
    def __init__(self):
        super().__init__()
        self.submin = []

    def place_submin_live(self, **kw):
        self.submin.append(kw)
        return M.PlaceResult(ok=True, order_status="EXECUTION_COMPLETE", bet_id="b-sub",
                             size_matched=float(kw["size"]),
                             avg_price_matched=float(kw["price"]))


def _place(db, mk, *, ref, size, side="back", mode="live", meta=None):
    return X.place(db=db, market=mk, mode=mode, event_id="2.1", market_id="mt",
                   selection_id=11, side=side, price=1.3, size=size, best_size=500.0,
                   client_ref=ref, trade_id=int(ref.rsplit("t", 1)[-1]), now=NOW,
                   params={}, meta=meta)


@pytest.fixture
def freni_aperti(monkeypatch):
    monkeypatch.setattr(X, "_live_brake", lambda: None)
    monkeypatch.setattr(X, "_freno_aperture", lambda: None)


def test_tennis_live_rest_back_072_diventa_100(con_d2, freni_aperti):
    db, mk = FakeDB(mode="live"), _MercatoConSubmin()
    db.follow = "NONE"                                  # REST live
    out = _place(db, mk, ref="safe_tennis-t5", size=0.72)
    assert out.status == "open" and mk.submin == []
    assert mk.placed[-1]["size"] == 1.0 and out.size_requested == 1.0


def test_tennis_lay_sotto_050_diventa_100(con_d2, freni_aperti):
    # 01/10/2026: il minimo accettato della banca .it e' 1,00 (costante condivisa
    # IT_LAY_MIN_SIZE): l'apertura tennis si porta AL minimo, cioe' 1,00
    db, mk = FakeDB(mode="live"), _MercatoConSubmin()
    db.follow = "NONE"
    _place(db, mk, ref="safe_tennis-t6", size=0.3, side="lay")
    assert mk.placed[-1]["size"] == 1.0 and mk.submin == []


def test_tennis_paper_coda_al_minimo(con_d2):
    db, mk = FakeDB(), FakeMarket()
    out = _place(db, mk, ref="safe_tennis-t7", size=0.72, mode="paper")
    assert out.status == "pending"
    q = db.queue[-1]
    assert q["action"] == "place" and q["size"] == 1.0 and q["time_in_force"] == "FILL_OR_KILL"
    assert q["client_ref"] == "safe_tennis-t7"


def test_tennis_chiusura_sotto_il_minimo_resta_esatta(con_d2, freni_aperti):
    db, mk = FakeDB(mode="live"), _MercatoConSubmin()
    db.follow = "NONE"
    _place(db, mk, ref="safe_tennis-t8", size=0.72,
           meta={"cashout": True, "closes_trade_id": 1})
    # 01/10/2026: la chiusura resta ESATTA (mai portata al minimo) ma non parte piu'
    # come place diretto sotto il minimo (Betfair la rifiuterebbe): REST place-and-trim
    assert mk.placed == [] and mk.submin[-1]["size"] == 0.72


def test_calcio_sotto_il_minimo_resta_place_and_trim(con_d2, freni_aperti):
    db, mk = FakeDB(mode="live"), _MercatoConSubmin()
    db.follow = "NONE"
    X.place(db=db, market=mk, mode="live", event_id="1.1", market_id="m1", selection_id=7,
            side="back", price=3.0, size=0.72, best_size=500.0, client_ref="safe-t9",
            trade_id=9, now=NOW, params={})
    assert mk.placed == [] and mk.submin[-1]["size"] == 0.72


def test_tennis_sul_canale_la_size_non_si_tocca_la_porta_al_minimo_il_motore(con_d2):
    """CORREZIONE (28/09 sera): sul CANALE la regola la applica il MOTORE del
    runner e la dichiara nell'evento (``portata_al_minimo``, controllo R8 del
    banco sulla registrazione vera, ``test_motore_ordini_tennis_2026_09_25``).
    Qui il comando deve partire con la size CHIESTA (1,00), non gia' a 2,00."""
    from Betfair.mike.tests.runner_finto import RunnerFinto

    porta = RunnerFinto(attore="safe_tennis")
    db, mk = FakeDB(), FakeMarket()
    tid = db.insert_trade({"event_id": "2.1", "status": "pending", "side": "back",
                           "mode": "paper", "sport": "tennis", "meta": {}})
    out = X.place(db=db, market=mk, mode="paper", event_id="2.1", market_id="1.300",
                  selection_id=11, side="back", price=1.3, size=1.0, best_size=500.0,
                  client_ref=f"safe_tennis-t{tid}", trade_id=tid, now=NOW, params={},
                  porta=porta)
    assert out.status == "pending", out
    assert porta.comandi and porta.comandi[-1]["size"] == 1.0
    assert "portata_al_minimo" not in (db.get_trade(tid)["meta"] or {})


def test_tennis_rest_live_riga_e_attivita_dicono_chiesto_e_piazzato(con_d2, freni_aperti):
    """Stessa apertura (0,70 back) sul REST live: ordine a 1,00, e la riga e
    l'attivita' lo dichiarano con le STESSE chiavi dell'evento del motore."""
    db, mk = FakeDB(mode="live"), _MercatoConSubmin()
    db.follow = "NONE"
    row = {"event_id": "2.1", "event_name": "P1 v P2", "sport": "tennis", "strategy": "tennis",
           "market_id": "mt", "market_type": "MATCH_ODDS", "selection_id": 11, "side": "back",
           "price": 1.3, "size": 0.7, "liability": 0.7, "status": "pending", "mode": "live",
           "commission": 0.05, "origin": "auto", "signal_key": "2.1:tennis:x", "pnl": 0.0,
           "meta": {"phase": "reserved"}}
    tid = db.insert_trade(dict(row))
    riserva = db.get_trade(tid)
    # come in produzione: la riga in mano al servizio e' una COPIA (non la riga del DB)
    out = S._execute(db=db, market=mk, trade_id=tid,
                     row={**riserva, "meta": dict(riserva["meta"])},
                     params=S.resolve_params({"strategy_modes": {"tennis": "live"}}),
                     now=NOW, best_size=500.0, ladder=(), feed_prices=None)
    assert out.status == "open" and mk.placed[-1]["size"] == 1.0
    atteso = {"chiesto": 0.7, "piazzato": 1.0}
    assert db.get_trade(tid)["meta"]["portata_al_minimo"] == atteso
    diag = [p for k, p in db.activity if k == "diagnosi" and p.get("reason") == "portata_al_minimo"]
    assert diag and diag[0]["portata_al_minimo"] == atteso


def test_senza_la_funzione_di_d2_comportamento_di_prima(monkeypatch, freni_aperti, caplog):
    monkeypatch.setattr(X, "_PORTA_AL_MINIMO", None)
    monkeypatch.setitem(X._AVVISO_SENZA_PORTA_AL_MINIMO, "fatto", False)
    db, mk = FakeDB(mode="live"), _MercatoConSubmin()
    db.follow = "NONE"
    with caplog.at_level("WARNING", logger="safe.execution"):
        _place(db, mk, ref="safe_tennis-t10", size=0.72)
    assert mk.submin[-1]["size"] == 0.72 and mk.placed == []
    assert any("porta_al_minimo_apertura non disponibile" in r.getMessage()
               for r in caplog.records)
