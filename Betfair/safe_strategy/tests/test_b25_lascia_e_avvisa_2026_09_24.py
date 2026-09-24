# -*- coding: utf-8 -*-
"""B25 - "LASCIA E AVVISA" sulla gamba MANUALE di una combo incompleta (24/09/2026).

Decisione dell'utente (reperto T13 x2734 del banco, scenario
`combos-automatiche` di Safe): "il bot non deve MAI chiudere le mie gambe (le
righe manuali del trader), ma deve essere informato, come gia' succede, quando
chiudo io tutte le operazioni: in quel caso non deve fare altro su quella
partita."

Fino al 23/09 `_unwind_combo` apriva una chiusura `origin='auto'` (uscita
'forced', "combo incompleta") anche sulla gamba `origin='manual'` di una combo
approvata dal trader. Qui si certifica, sul codice di produzione
(`bot_service.py`, `certificazione.py`):

  1. combo con una gamba FOK uccisa -> NESSUN ordine sulla gamba manuale,
     avviso `combo_incomplete` con le chiavi giuste, riga marcata
     (`meta.combo_lasciata_al_trader`), UNA volta sola nei giri successivi;
  2. gamba manuale in coda che si abbina dopo -> avvisata al fill, mai chiusa;
  3. dopo il cash-out del trader (globale o della sola riga) il bot non fa
     altro su quella partita / quella riga;
  4. PARITA': una gamba del BOT (`origin='auto'`) di combo incompleta si svolge
     esattamente come ieri;
  5. il controllo di banco T13-COMBO: tace sul comportamento giusto e scatta su
     ognuno dei difetti (chiusura del bot, marcatura mancante, avviso mancante,
     avviso ripetuto, uscita del bot sulla riga).

I finti sono quelli di `test_bot_service.py`/`test_audit_2026_09_11.py` (stesse
chiavi di `bot_db` e di `omega_market`). ASCII-only, commenti in italiano.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

import pytest

from Betfair.omega import omega_market as M
from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import certificazione as CERT
from Betfair.safe_strategy.tests.test_audit_2026_09_11 import (_combo, _combo_feed_row,
                                                              _kinds)
from Betfair.safe_strategy.tests.test_bot_service import (NOW, FakeDB, FakeMarket,
                                                          _reset_module_state)


@pytest.fixture(autouse=True)
def _stato_pulito():
    _reset_module_state()
    S._EVENTI_CHIUSI.clear()
    yield
    _reset_module_state()
    S._EVENTI_CHIUSI.clear()


class MercatoMezzo(FakeMarket):
    """La gamba 1X2 (m1) viene UCCISA dal FOK (EXPIRED, niente abbinato), la
    gamba ou25 si abbina tutta: stessa forma di `HalfMarket` del test H-20."""

    def place_order_live(self, **kw):
        if kw["market_id"] == "m1":
            self.placed.append(kw)
            return M.PlaceResult(ok=False, order_status="EXPIRED", bet_id=None,
                                 size_matched=0.0, avg_price_matched=None)
        return super().place_order_live(**kw)


def _combo_rotta(db: FakeDB, mercato: FakeMarket) -> Dict[str, Any]:
    """Una combo APPROVATA dal trader (le gambe nascono origin='manual', come
    le fa `_request_place_combo`) con la seconda gamba uccisa dal FOK."""
    row = _combo_feed_row()
    params = S.resolve_params({"strategy_modes": {"model": "live"}})
    corpi = S._proponi_combo(db=db, payload=row["payload"], event_id="1.1",
                             combos=[_combo()], params=params, mode="live",
                             now=NOW, rows_by_event={"1.1": row})
    assert len(corpi) == 1
    corpo = corpi[0]
    return S._esegui_combo_riservata(
        db=db, market=mercato, event_id="1.1", event_name=corpo.get("event_name"),
        cid=corpo["combo_id"], legs_esecuzione=corpo["legs"], sport="calcio", mode="live",
        commission=0.05, minute=corpo.get("minute"), score=corpo.get("score"),
        rationale=corpo.get("rationale"), params=params, now=NOW,
        rows_by_event={"1.1": row}, risk_ctx=None)


def _gamba_lasciata(db: FakeDB) -> Dict[str, Any]:
    return next(t for t in db.trades if t.get("market_id") == "ou25"
                and not t.get("closes_trade_id"))


def _avvisi(db: FakeDB, tid: Any = None) -> List[Dict[str, Any]]:
    return [p for p in _kinds(db, "combo_incomplete")
            if p.get("lasciata_al_trader") and (tid is None or p.get("trade_id") == tid)]


_USCITE = ("exit", "exit_retry", "exit_hold", "exit_wait", "exit_failed")


# ===========================================================================
# 1. COMBO CON GAMBA FOK UCCISA: LA GAMBA MANUALE RESTA, L'AVVISO C'E'
# ===========================================================================
def test_gamba_fok_uccisa_nessun_ordine_sulla_gamba_manuale():
    db = FakeDB(status="running", mode="live")
    mercato = MercatoMezzo()
    esito = _combo_rotta(db, mercato)
    assert esito["placed"] == 1 and esito["total"] == 2
    # DUE soli ordini a mercato: le due gambe. Nessuna chiusura della manuale.
    assert [o["market_id"] for o in mercato.placed] == ["ou25", "m1"]
    g = _gamba_lasciata(db)
    assert g["origin"] == "manual" and g["status"] == "open"
    assert [t for t in db.trades if t.get("closes_trade_id")] == []
    assert not [p for k, p in db.activity if k in _USCITE and p.get("trade_id") == g["id"]]


def test_avviso_scritto_con_le_chiavi_giuste_e_riga_marcata():
    db = FakeDB(status="running", mode="live")
    _combo_rotta(db, MercatoMezzo())
    g = _gamba_lasciata(db)
    uccisa = next(t for t in db.trades if t.get("market_id") == "m1")
    avvisi = _avvisi(db)
    assert len(avvisi) == 1
    a = avvisi[0]
    # le chiavi che la Control Room legge (`safeActivityLine`): partita,
    # selezione, lato, mercato, size @ prezzo, liability, motivo in chiaro
    for k in ("event_id", "trade_id", "combo_id", "selection_name", "side",
              "market_type", "size", "price", "liability", "mode", "reason",
              "gambe_non_abbinate", "marcata", "critical", "lasciata_al_trader"):
        assert k in a, k
    assert a["event_id"] == "1.1" and a["trade_id"] == g["id"]
    assert a["critical"] is True and a["marcata"] is True and a["mode"] == "live"
    assert a["selection_name"] == "Under 2.5 Goals" and a["side"] == "back"
    assert "lasciata aperta a mercato: decidi tu" in a["reason"]
    assert f"#{uccisa['id']}" in a["reason"] and "Home" in a["reason"]
    assert f"#{g['id']}" in a["reason"]
    assert [x["trade_id"] for x in a["gambe_non_abbinate"]] == [uccisa["id"]]
    # la riga e' marcata nel meta (colonna gia' esistente, sopravvive al riavvio)
    mk = g["meta"][S.COMBO_LASCIATA_KEY]
    assert set(mk) == {"quando", "motivo", "combo_id", "gambe_non_abbinate"}
    assert mk["motivo"] == a["reason"] and mk["quando"] == NOW.isoformat()
    assert g["meta"]["combo_incomplete"] is True
    assert g["meta"][S.COMBO_NON_ABBINATE_KEY][0]["selection_name"] == "Home"


def test_nei_giri_successivi_niente_chiusura_e_nessun_avviso_ripetuto():
    """Il bot continua a GUARDARE la riga (e' fra le posizioni vive di ogni
    giro) ma non la tocca, e non riscrive l'avviso a ogni ciclo."""
    db = FakeDB(status="running", mode="live")
    mercato = MercatoMezzo()
    _combo_rotta(db, mercato)
    g = _gamba_lasciata(db)
    n_ordini = len(mercato.placed)
    for i in range(1, 6):
        db.scan_rows = [_combo_feed_row()]
        at = NOW + timedelta(seconds=2 * i)
        db.scan_rows[0]["updated_at"] = at.isoformat()
        S.run_once(db=db, market=mercato, now=at)
    assert len(mercato.placed) == n_ordini, "il bot ha piazzato un ordine dopo"
    assert db.get_trade(g["id"])["status"] == "open"
    assert [t for t in db.trades if t.get("closes_trade_id")] == []
    assert len(_avvisi(db, g["id"])) == 1
    assert not [p for k, p in db.activity if k in _USCITE and p.get("trade_id") == g["id"]]


# ===========================================================================
# 2. GAMBA MANUALE IN CODA CHE SI ABBINA DOPO (H6)
# ===========================================================================
def _riga_manuale_di_combo(db: FakeDB, **kw) -> int:
    riga = {"event_id": "1.1", "event_name": "Home v Away", "sport": "calcio",
            "strategy": "model", "market_id": "ou25", "market_type": "OVER_UNDER",
            "selection_id": 101, "selection_name": "Under 2.5 Goals", "side": "back",
            "price": 2.0, "size": 5.0, "liability": 5.0, "commission": 0.05,
            "status": "open", "mode": "paper", "origin": "manual",
            "signal_key": "combo:c1:0", "minute_at_entry": 30, "score_at_entry": "0-0",
            "meta": {"combo_id": "c1", "combo_incomplete": True,
                     S.COMBO_NON_ABBINATE_KEY: [{"trade_id": 9, "selection_name": "Home",
                                                 "market_type": "MATCH_ODDS", "side": "back",
                                                 "price": 3.0, "size": 5.0}]}}
    riga.update(kw)
    return db.insert_trade(riga)


def _prezzi_ou25() -> Dict[str, Any]:
    """I prezzi della gamba ou25 come li legge il servizio (`prices_from_row`
    sulla riga del feed), non un dict scritto a mano."""
    p = S.prices_from_row(_combo_feed_row(), market_type="OVER_UNDER",
                          selection_id=101, market_id="ou25")
    assert p and p.get("back")
    return p


def test_gamba_manuale_in_coda_avvisata_al_fill_e_mai_chiusa():
    db = FakeDB(status="stopped")
    tid = _riga_manuale_di_combo(db)
    n = S.unwind_incomplete_combos(db=db, market=FakeMarket(),
                                   rows_by_event={"1.1": _combo_feed_row()},
                                   params=S.resolve_params({}), now=NOW)
    assert n == 0
    assert [t for t in db.trades if t.get("closes_trade_id") == tid] == []
    assert len(_avvisi(db, tid)) == 1
    assert "#9" in _avvisi(db, tid)[0]["reason"]
    # al giro dopo: gia' marcata, non rientra nemmeno nell'elenco
    assert S.unwind_incomplete_combos(db=db, market=FakeMarket(),
                                      rows_by_event={"1.1": _combo_feed_row()},
                                      params=S.resolve_params({}), now=NOW) == 0
    assert len(_avvisi(db, tid)) == 1


class DbCheRegistra(FakeDB):
    """FakeDB che ricorda le SCRITTURE (`update_trade`) e le letture per id
    (`get_trade`): il finto condivide i dict delle righe, quindi senza questo
    una marcatura fatta solo in memoria sembrerebbe salvata."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.scritture: list = []
        self.letture: list = []

    def update_trade(self, trade_id, **fields):
        self.scritture.append((int(trade_id), dict(fields)))
        super().update_trade(trade_id, **fields)

    def get_trade(self, trade_id):
        self.letture.append(int(trade_id))
        return super().get_trade(trade_id)


def test_la_marcatura_e_SCRITTA_sul_database():
    db = DbCheRegistra(status="stopped")
    tid = _riga_manuale_di_combo(db)
    S.unwind_incomplete_combos(db=db, market=FakeMarket(),
                               rows_by_event={"1.1": _combo_feed_row()},
                               params=S.resolve_params({}), now=NOW)
    scritte = [f["meta"] for i, f in db.scritture if i == tid and "meta" in f]
    assert scritte and isinstance(scritte[-1].get(S.COMBO_LASCIATA_KEY), dict)


def test_avviso_idempotente_anche_chiamato_due_volte_sulla_stessa_riga():
    """La guardia interna di `_lascia_gamba_manuale` (non solo il filtro di
    `unwind_incomplete_combos`): due passaggi, un avviso."""
    db = FakeDB(status="stopped")
    tid = _riga_manuale_di_combo(db)
    for _ in range(2):
        S._close_combo_siblings(db=db, market=FakeMarket(), legs=[db.get_trade(tid)],
                                prices_by_id={tid: _prezzi_ou25()},
                                params=S.resolve_params({}), now=NOW,
                                reason="combo: chiusura solidale della combinazione")
    assert len(_avvisi(db, tid)) == 1


def test_gamba_gia_avvisata_non_viene_nemmeno_riletta():
    """Respiro del DB: una riga manuale gia' marcata esce dall'elenco di
    `unwind_incomplete_combos` prima di qualsiasi lettura per id."""
    db = DbCheRegistra(status="stopped")
    tid = _riga_manuale_di_combo(db)
    S.unwind_incomplete_combos(db=db, market=FakeMarket(),
                               rows_by_event={"1.1": _combo_feed_row()},
                               params=S.resolve_params({}), now=NOW)
    db.letture.clear()
    S.unwind_incomplete_combos(db=db, market=FakeMarket(),
                               rows_by_event={"1.1": _combo_feed_row()},
                               params=S.resolve_params({}), now=NOW)
    assert tid not in db.letture


def test_senza_prezzi_la_gamba_manuale_non_da_exit_failed():
    """Ieri una gamba senza prezzi nel feed dava `exit_failed` critico
    ("combo_incompleta_senza_prezzi"): era il bot che PROVAVA a chiudere. Sulla
    riga del trader non ci prova piu', quindi niente uscita fallita."""
    db = FakeDB(status="stopped")
    tid = _riga_manuale_di_combo(db)
    S.unwind_incomplete_combos(db=db, market=FakeMarket(), rows_by_event={},
                               params=S.resolve_params({}), now=NOW)
    assert not _kinds(db, "exit_failed")
    assert len(_avvisi(db, tid)) == 1


def test_chiusura_solidale_non_tocca_una_gamba_manuale():
    """`_close_combo_siblings` e' il collo di bottiglia di ogni chiusura di
    gamba di combo: una riga manuale passata li' non si chiude."""
    db = FakeDB(status="stopped")
    tid = _riga_manuale_di_combo(db)
    riga = db.get_trade(tid)
    n = S._close_combo_siblings(db=db, market=FakeMarket(), legs=[riga],
                                prices_by_id={tid: _prezzi_ou25()},
                                params=S.resolve_params({}), now=NOW,
                                reason="combo: chiusura solidale della combinazione")
    assert n == 0
    assert [t for t in db.trades if t.get("closes_trade_id") == tid] == []
    assert len(_avvisi(db, tid)) == 1


# ===========================================================================
# 3. IL TRADER CHIUDE: IL BOT LO CAPISCE E NON FA ALTRO (T14)
# ===========================================================================
def test_cashout_globale_dopo_la_combo_incompleta_il_bot_non_fa_altro():
    db = FakeDB(status="running", mode="live")
    mercato = MercatoMezzo()
    _combo_rotta(db, mercato)
    g = _gamba_lasciata(db)
    res = S._request_cashout_event(db=db, market=mercato,
                                   rows_by_event={"1.1": _combo_feed_row()},
                                   payload={"event_id": "1.1"}, params={}, now=NOW)
    assert res.get("ok") is True and g["id"] in res["chiuse"]
    figlie = [t for t in db.trades if t.get("closes_trade_id") == g["id"]]
    assert len(figlie) == 1 and figlie[0]["origin"] == "manual"
    assert S.evento_chiuso_dall_utente("1.1") is not None
    righe_prima = len(db.trades)
    ordini_prima = len(mercato.placed)
    n_att = len(db.activity)
    for i in range(1, 6):
        at = NOW + timedelta(seconds=2 * i)
        riga = _combo_feed_row()
        riga["updated_at"] = at.isoformat()
        db.scan_rows = [riga]
        S.run_once(db=db, market=mercato, now=at)
    assert len(db.trades) == righe_prima, "il bot ha fatto nascere una riga dopo il cash-out"
    assert len(mercato.placed) == ordini_prima
    nuove = db.activity[n_att:]
    assert not [p for k, p in nuove if k in _USCITE]
    assert not [p for k, p in nuove if k == "combo_incomplete"]


def test_cashout_della_sola_gamba_lasciata_il_bot_non_la_tocca_piu():
    db = FakeDB(status="running", mode="live")
    mercato = MercatoMezzo()
    _combo_rotta(db, mercato)
    g = _gamba_lasciata(db)
    res = S._request_cashout(db=db, market=mercato,
                             rows_by_event={"1.1": _combo_feed_row()},
                             payload={"trade_id": g["id"], "fraction": 1.0},
                             params={}, now=NOW)
    assert res.get("ok") is True
    assert S.marcatore_utente(db.get_trade(g["id"])) is not None
    righe_prima = len(db.trades)
    n_att = len(db.activity)
    for i in range(1, 4):
        at = NOW + timedelta(seconds=2 * i)
        riga = _combo_feed_row()
        riga["updated_at"] = at.isoformat()
        db.scan_rows = [riga]
        S.run_once(db=db, market=mercato, now=at)
    assert len(db.trades) == righe_prima
    figlie = [t for t in db.trades if t.get("closes_trade_id") == g["id"]]
    assert [t["origin"] for t in figlie] == ["manual"]
    nuove = db.activity[n_att:]
    assert not [p for k, p in nuove if k in _USCITE and p.get("trade_id") == g["id"]]
    assert not [p for k, p in nuove if k == "combo_incomplete"]


# ===========================================================================
# 4. PARITA': UNA GAMBA DEL BOT SI SVOLGE COME IERI
# ===========================================================================
def test_parita_gamba_automatica_di_combo_incompleta_svolta_come_ieri():
    db = FakeDB(status="stopped")
    tid = _riga_manuale_di_combo(db, origin="auto")
    n = S.unwind_incomplete_combos(db=db, market=FakeMarket(),
                                   rows_by_event={"1.1": _combo_feed_row()},
                                   params=S.resolve_params({}), now=NOW)
    assert n == 1
    figlie = [t for t in db.trades if t.get("closes_trade_id") == tid]
    assert len(figlie) == 1
    assert figlie[0]["origin"] == "auto"
    assert figlie[0]["meta"]["exit_kind"] == "forced"
    assert "combo incompleta" in figlie[0]["meta"]["exit_reason"]
    assert db.get_trade(tid)["status"] == "hedged"
    assert _avvisi(db) == []
    assert S.COMBO_LASCIATA_KEY not in (db.get_trade(tid)["meta"] or {})


def test_parita_chiusura_solidale_di_una_gamba_automatica():
    db = FakeDB(status="stopped")
    tid = _riga_manuale_di_combo(db, origin="auto")
    n = S._close_combo_siblings(db=db, market=FakeMarket(), legs=[db.get_trade(tid)],
                                prices_by_id={tid: _prezzi_ou25()},
                                params=S.resolve_params({}), now=NOW,
                                reason="combo: chiusura solidale della combinazione")
    assert n == 1
    figlie = [t for t in db.trades if t.get("closes_trade_id") == tid]
    assert len(figlie) == 1 and figlie[0]["origin"] == "auto"
    assert _avvisi(db) == []


# ===========================================================================
# 5. IL CONTROLLO DI BANCO T13-COMBO
# ===========================================================================
class _Db:
    """Stessa forma del DB del banco (`replay_registrazioni`): `trades` e
    `attivita` a TRE elementi (kind, payload, event_id)."""

    def __init__(self, trades, attivita=()):
        self.trades = list(trades)
        self.attivita = list(attivita)

    def aggregates(self, mode=None):
        return {}


class _Mercato:
    def list_current_orders(self, strategy_ref=None):
        return []


def _ciclo(db, **kw) -> CERT.Ciclo:
    return CERT.Ciclo(db=db, market=_Mercato(), params={}, mode="live", now_ts=0.0, **kw)


def _codici(c) -> set:
    return {v.codice for v in CERT.verifica(c)}


def _sollecitato(c, codice: str) -> bool:
    sol: Dict[str, int] = {}
    CERT.verifica(c, sol)
    return bool(sol.get(codice))


def _dal_servizio(db: FakeDB) -> _Db:
    """Lo stato VERO lasciato dal servizio, nella forma del banco."""
    return _Db(db.trades, [(k, p, p.get("event_id")) for k, p in db.activity])


def test_t13_combo_tace_sul_comportamento_del_servizio():
    db = FakeDB(status="running", mode="live")
    _combo_rotta(db, MercatoMezzo())
    c = _ciclo(_dal_servizio(db))
    assert _sollecitato(c, "T13-COMBO") and _sollecitato(c, "T13")
    assert "T13-COMBO" not in _codici(c) and "T13" not in _codici(c)


def test_t13_combo_senza_gambe_manuali_di_combo_non_ha_un_caso():
    c = _ciclo(_Db([{"id": 1, "origin": "auto", "status": "open", "meta": {}}]))
    assert not _sollecitato(c, "T13-COMBO")


def _lasciata(id_=1, **meta) -> Dict[str, Any]:
    m = {"combo_id": "c1", "combo_incomplete": True,
         S.COMBO_LASCIATA_KEY: {"quando": "x", "motivo": "m", "combo_id": "c1",
                                "gambe_non_abbinate": []}}
    m.update(meta)
    return {"id": id_, "origin": "manual", "status": "open", "event_id": "1",
            "side": "back", "market_id": "ou25", "selection_id": 101, "meta": m}


def _avviso(tid=1, marcata=True):
    return ("combo_incomplete", {"trade_id": tid, "lasciata_al_trader": True,
                                 "marcata": marcata, "event_id": "1"}, "1")


def test_t13_combo_scatta_se_il_bot_chiude_la_gamba_manuale():
    chiusura = {"id": 2, "origin": "auto", "status": "open", "closes_trade_id": 1,
                "side": "lay", "event_id": "1", "meta": {}}
    c = _ciclo(_Db([_lasciata(), chiusura], [_avviso()]))
    assert "T13-COMBO" in _codici(c)


def test_t13_combo_scatta_se_la_riga_non_e_marcata():
    riga = _lasciata()
    del riga["meta"][S.COMBO_LASCIATA_KEY]
    c = _ciclo(_Db([riga], [_avviso()]))
    assert "T13-COMBO" in _codici(c)


def test_t13_combo_scatta_se_l_avviso_non_e_scritto():
    c = _ciclo(_Db([_lasciata()], []))
    assert "T13-COMBO" in _codici(c)


def test_t13_combo_scatta_se_l_avviso_si_ripete():
    c = _ciclo(_Db([_lasciata()], [_avviso(), _avviso()]))
    assert "T13-COMBO" in _codici(c)


def test_t13_combo_un_avviso_ripetuto_per_marcatura_fallita_e_ammesso():
    c = _ciclo(_Db([_lasciata()], [_avviso(marcata=False), _avviso()]))
    assert _sollecitato(c, "T13-COMBO") and "T13-COMBO" not in _codici(c)


def test_t13_combo_scatta_su_un_uscita_del_bot_nella_riga():
    c = _ciclo(_Db([_lasciata()], [_avviso()]),
               attivita_del_giro=[("exit_wait", {"trade_id": 1}, "1")])
    assert "T13-COMBO" in _codici(c)


def test_t13_combo_gamba_in_coda_non_chiede_ancora_l_avviso():
    riga = _lasciata()
    riga["status"] = "pending"
    del riga["meta"][S.COMBO_LASCIATA_KEY]
    c = _ciclo(_Db([riga], []))
    assert _sollecitato(c, "T13-COMBO") and "T13-COMBO" not in _codici(c)
