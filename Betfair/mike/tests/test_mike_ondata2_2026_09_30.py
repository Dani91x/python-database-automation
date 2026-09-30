"""30/09/2026 - Mike, seconda ondata di correzioni (ordini dell'utente del 30/09).

1. Il REGOLAMENTO esegue gli annulli che decide (revisione critica, C1-aggiunta):
   con la partita chiusa (linea in gioco CLOSED, o riga assente oltre la grazia)
   gli ordini ancora vivi si annullano davvero, si seguono finche' non hanno un
   esito letto, e solo dopo si regolano le righe.
2. Al fischio Mike NON annulla la banca pre-partita LAPSE (M2.1 "Mike non la
   ritira"): ne legge l'esito (scaduta / abbinata) e decide da li'.
3. ``reentry_time`` in PROFITTO parte da sola; in perdita resta proposta.
4. Il resto sotto minimo (M3.5) va nel registro ``mike_activity``.
5. Due prove mancanti: M6.2 ramo ABBINATO (B-6) e tetto al prezzo LIMITE (B-10).
6. Righe ``ko_green`` scadute: stessa scrittura della size sui due trasporti.

Finti: ``FakeDB``/``FakeMarket`` di ``test_mike_service`` (le firme di
``mike/db.py``), ``payload``/``row`` di ``test_mike_feed`` (chiavi dello scanner),
runner finto sul protocollo vero (``runner_finto``), gambe serializzate con
``dataclasses.asdict`` come fa ``_row_from_ctx``. ASCII-only.
"""
from __future__ import annotations

import dataclasses
from datetime import timedelta
from typing import Any, Dict, List

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import feed as F
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_feed import KO_IN_FINESTRA, payload, row
from Betfair.mike.tests.test_mike_indagine_mercato_deciso_2026_09_29 import (
    OU35, OU45, SEL_O35, SEL_O45, SEL_U35, SEL_U45, _evento_coperto, _payload)
from Betfair.mike.tests.test_mike_service import NOW, FakeDB, FakeMarket, legs, run, state


# ===========================================================================
# 1) il regolamento esegue gli annulli decisi
# ===========================================================================
def _libri_chiusi_4_gol(mk: FakeMarket) -> None:
    """Partita finita 4-0: Over 3,5 e Under 4,5 vincenti (runner come ``read_book``)."""
    mk.books[OU35] = {"market_id": OU35, "status": "CLOSED", "inplay": True,
                      "runners": [{"selection_id": SEL_U35, "status": "LOSER"},
                                  {"selection_id": SEL_O35, "status": "WINNER"}]}
    mk.books[OU45] = {"market_id": OU45, "status": "CLOSED", "inplay": True,
                      "runners": [{"selection_id": SEL_U45, "status": "WINNER"},
                                  {"selection_id": SEL_O45, "status": "LOSER"}]}


def _copertura_in_volo(db: FakeDB, runner) -> str:
    """Posizione di ``_evento_coperto`` + una banca Under 4,5 di copertura
    APPOGGIATA sul runner (strada vera ``_piazza_resting_paper``), non abbinata.
    Ritorna il ref del comando sul runner."""
    _evento_coperto(db)
    leg = E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_UNDER, side="lay",
                price=4.9, size=3.0, ref="over_cover-0-7", cycle_no=0,
                placed_at=NOW.timestamp() - 30.0)
    info = F.event_info("E1", _payload([]))
    S._piazza_resting_paper(db=db, market=FakeMarket(), info=info, leg=leg,
                            params=C.merge_params(None), minuto=64, score="4-0", chiude=None,
                            motivo=None, ev={"event_id": "E1"}, now=NOW)
    assert leg.status == "pending", "precondizione: la banca e' sul book del runner"
    db.events["E1"]["positions"].append(dataclasses.asdict(leg))
    riga = [t for t in db.trades if t.get("signal_key") == leg.ref][0]
    assert riga["status"] == "pending" and riga["meta"]["canale_ref"]
    return str(riga["meta"]["canale_ref"])


def _annulli_al_runner(runner) -> List[Dict[str, Any]]:
    return [c for c in runner.comandi if c.get("azione") == "cancel"]


def _gamba(db: FakeDB, ref: str) -> Dict[str, Any]:
    return [l for l in legs(db) if l["ref"] == ref][0]


def _payload_finita() -> Dict[str, Any]:
    p = _payload([], stato35="CLOSED")
    p["ou"][1]["status"] = "CLOSED"            # anche la linea in gioco (4,5) e' chiusa
    return p


def test_c1_linea_in_gioco_chiusa_la_copertura_in_volo_si_annulla_poi_si_regola(runner):
    db = FakeDB(params={"stake": 10})
    ref = _copertura_in_volo(db, runner)
    mk = FakeMarket()
    _libri_chiusi_4_gol(mk)
    run(db, mk, NOW, [row(_payload_finita())])
    annulli = _annulli_al_runner(runner)
    assert len(annulli) == 1, (runner.comandi, db.kinds())
    assert str(annulli[0]["bet_id"]) == str(runner.ordine(ref)["bet_id"])
    assert _gamba(db, "over_cover-0-7")["status"] == "cancelled"
    assert any(k == "cancel" and p.get("leg") == "over_cover-0-7" for k, p, _e in db.activity)
    # annullo confermato dal runner: la partita si regola nello stesso giro
    assert state(db) == "SETTLED"
    riga = [t for t in db.trades if t.get("signal_key") == "over_cover-0-7"][0]
    assert riga["status"] not in ("pending", "open")


def test_c1_riga_assente_oltre_la_grazia_la_copertura_in_volo_si_annulla(runner):
    """Il ramo ``absent_closed``: la riga manca da >= grazia e i libri non dicono
    ancora il risultato. La gamba viva si annulla lo stesso (decisione SETTLING
    del motore), non resta sul book creduta viva."""
    db = FakeDB(params={"stake": 10})
    _copertura_in_volo(db, runner)
    db.events["E1"]["ctx"]["row_missing_since"] = NOW.timestamp() - S._ROW_MISSING_GRACE_S - 1
    run(db, FakeMarket(), NOW, [])
    assert len(_annulli_al_runner(runner)) == 1, (runner.comandi, db.kinds())
    assert _gamba(db, "over_cover-0-7")["status"] == "cancelled"
    assert state(db) == "SETTLING"


def test_c1_annullo_senza_esito_il_regolamento_aspetta_e_la_sorveglianza_continua(runner):
    """Il runner non conferma l'annullo (evento trattenuto): la gamba va in
    riconciliazione, la partita resta SETTLING (nessuna riga regolata con un
    ordine forse vivo); quando l'esito arriva, la sorveglianza lo legge e la
    partita si regola."""
    db = FakeDB(params={"stake": 10})
    _copertura_in_volo(db, runner)
    mk = FakeMarket()
    _libri_chiusi_4_gol(mk)
    runner.trattieni = True
    run(db, mk, NOW, [row(_payload_finita())])
    assert len(_annulli_al_runner(runner)) == 1
    assert _gamba(db, "over_cover-0-7")["status"] == E.STATUS_RECONCILE
    assert state(db) == "SETTLING"
    riga = [t for t in db.trades if t.get("signal_key") == "over_cover-0-7"][0]
    assert riga["status"] == "pending"
    righe_aperte = [t for t in db.trades if t["status"] in ("open", "pending")]
    assert righe_aperte, "nessuna riga regolata finche' un ordine e' senza esito"
    runner.trattieni = False
    runner.rilascia()
    t = NOW + timedelta(seconds=90)
    run(db, mk, t, [row(_payload_finita(), updated=t)])
    assert _gamba(db, "over_cover-0-7")["status"] == "cancelled", db.kinds()
    assert state(db) == "SETTLED"


def test_c1_mercato_annullato_non_si_regola_con_un_ordine_senza_esito(runner):
    """Il ramo del mercato ANNULLATO (void per mercato) regolava le righe senza
    guardare gli esiti ignoti: con la copertura in volo il cui annullo non e'
    confermato, niente regolamento finche' l'esito non e' letto."""
    db = FakeDB(params={"stake": 10})
    _copertura_in_volo(db, runner)
    mk = FakeMarket()
    _libri_chiusi_4_gol(mk)
    mk.books[OU45] = {"market_id": OU45, "status": "VOIDED", "inplay": True, "runners": []}
    runner.trattieni = True
    run(db, mk, NOW, [row(_payload_finita())])
    assert _gamba(db, "over_cover-0-7")["status"] == E.STATUS_RECONCILE
    assert state(db) == "SETTLING", db.kinds()
    assert "settled" not in db.kinds()


def test_c1_confine_senza_ordini_vivi_il_regolamento_e_quello_di_prima(runner):
    """Confine: nessuna gamba viva -> nessun annullo, regolamento nello stesso
    giro come prima della correzione."""
    db = FakeDB(params={"stake": 10})
    _evento_coperto(db)
    mk = FakeMarket()
    _libri_chiusi_4_gol(mk)
    run(db, mk, NOW, [row(_payload_finita())])
    assert _annulli_al_runner(runner) == []
    assert state(db) == "SETTLED"


# ===========================================================================
# 2) al fischio nessun annullo della banca LAPSE: se ne legge l'esito
# ===========================================================================
def _banca_appoggiata(db: FakeDB, mk: FakeMarket, runner) -> str:
    """Ciclo pre-partita vero: ingresso abbinato dal runner e banca Under 3,5
    appoggiata sul runner (LAPSE). Ritorna il ref del comando della banca."""
    run(db, mk, NOW, [row(payload())])
    run(db, mk, NOW + timedelta(seconds=2), [row(payload())])
    banca = [l for l in legs(db) if l["role"] == "under_green"][0]
    assert banca["status"] == "pending" and banca["persistence"] == "LAPSE"
    lay = runner.comandi[-1]
    assert lay["side"] == "LAY" and lay["persistence"] == "LAPSE"
    return str(lay["ref"])


def _fischio_riga(sec: int = 30) -> Dict[str, Any]:
    t = KO_IN_FINESTRA + timedelta(seconds=sec)
    return row(payload(inplay=True, minute=0, sh=0, sa=0), updated=t)


def _banca_leg(db: FakeDB) -> Dict[str, Any]:
    return [l for l in legs(db) if l["role"] == "under_green"][0]


def test_m2_al_fischio_nessun_annullo_della_banca_lapse(runner):
    db, mk = FakeDB(params={"stake": 10}), FakeMarket()
    _banca_appoggiata(db, mk, runner)
    run(db, mk, KO_IN_FINESTRA + timedelta(seconds=30), [_fischio_riga(30)])
    assert _annulli_al_runner(runner) == [], runner.comandi
    assert "cancel" not in db.kinds() and "cancel_richiesto" not in db.kinds()
    assert state(db) == "LIVE_KO_GREEN"
    assert _banca_leg(db)["status"] == "pending", "Mike aspetta di LEGGERE l'esito"


def test_m2_banca_abbinata_letta_dopo_il_fischio_posizione_chiusa(runner):
    db, mk = FakeDB(params={"stake": 10}), FakeMarket()
    ref = _banca_appoggiata(db, mk, runner)
    n_comandi = len(runner.comandi)
    run(db, mk, KO_IN_FINESTRA + timedelta(seconds=30), [_fischio_riga(30)])
    runner.abbina(ref)                               # abbinata al passaggio in gioco
    run(db, mk, KO_IN_FINESTRA + timedelta(seconds=32), [_fischio_riga(32)])
    assert _banca_leg(db)["status"] == "open"
    assert state(db) == "IDLE_LIVE", db.kinds()
    w, l = E.exposure(S._ctx_from_row(db.events["E1"]).legs, E.MARKET_OU35, E.SEL_UNDER)
    assert abs(w - l) < 0.05, "banca abbinata = piatto: nessuna esposizione"
    assert runner.comandi[n_comandi:] == [], "nessun ordine su una posizione chiusa"


def test_m2_banca_scaduta_letta_dopo_il_fischio_si_va_al_ko_green(runner):
    db, mk = FakeDB(params={"stake": 10}), FakeMarket()
    ref = _banca_appoggiata(db, mk, runner)
    run(db, mk, KO_IN_FINESTRA + timedelta(seconds=30), [_fischio_riga(30)])
    runner.scadi(ref)                                # LAPSE di Betfair al passaggio in gioco
    run(db, mk, KO_IN_FINESTRA + timedelta(seconds=32), [_fischio_riga(32)])
    assert _banca_leg(db)["status"] == "cancelled" and float(_banca_leg(db)["matched"]) == 0.0
    assert state(db) == "LIVE_KO_GREEN"
    assert _annulli_al_runner(runner) == []


def test_m2_confine_banca_persist_si_annulla_ancora():
    """Confine (non previsto dal piano): una banca PERSIST al fischio si
    annulla come prima, perche' Betfair non la farebbe scadere."""
    ctx = E.MatchCtx(state="HOLD", legs=[
        E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
              price=1.5, size=20.0, matched=20.0, avg_price=1.5, ref="under_entry-0-1",
              status="open", cycle_no=0),
        E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
              price=1.48, size=20.27, ref="under_green-0-2", status="pending", cycle_no=0,
              persistence="PERSIST")])
    p = C.merge_params(None)
    ko = KO_IN_FINESTRA.timestamp()
    snap = E.Snapshot(now=ko + 30, ko_at=ko, inplay=True, minute=0, goals=0, books={
        (E.MARKET_OU35, E.SEL_UNDER): E.Book(status="OPEN", best_back=1.54, back_size=50.0,
                                             best_lay=1.55, lay_size=50.0, inplay=True)})
    d = E.decide(ctx, snap, p)
    assert [(a.kind, a.role) for a in d.actions] == [("cancel", "under_green")]
    ctx.legs[1].persistence = "LAPSE"
    d2 = E.decide(ctx, snap, p)
    assert [a for a in d2.actions if a.kind == "cancel"] == []


# ===========================================================================
# 3) uscita a tempo del rientro: in profitto parte da sola, in perdita proposta
# ===========================================================================
from Betfair.mike import certificazione as CERT  # noqa: E402
from Betfair.mike.tests.test_mike_engine import KO as KO_E  # noqa: E402
from Betfair.mike.tests.test_mike_engine import book as book_e  # noqa: E402
from Betfair.mike.tests.test_mike_engine import fill as fill_e  # noqa: E402
from Betfair.mike.tests.test_mike_engine import params as params_e  # noqa: E402
from Betfair.mike.tests.test_mike_engine import snap as snap_e  # noqa: E402


def _rientro_aperto(prezzo_ingresso: float = 1.60):
    ctx = E.MatchCtx(state="REENTRY_OPEN", entry_price_initial=1.50, reentry_allowed=True)
    ctx.legs.append(fill_e(E.Leg(role="reentry", market=E.MARKET_OU45, selection=E.SEL_UNDER,
                                 side="back", price=prezzo_ingresso, size=10.0)))
    return ctx


def _al_minuto(bb: float, bl: float):
    return snap_e(KO_E + 81 * 60, u45=book_e(bb, bl=bl, inplay=True), inplay=True, minute=81,
                  goals=1)


def _posti_e(d):
    return [(a.role, a.side, a.price, a.size) for a in d.actions if a.kind == "place"]


def test_m3_reentry_time_in_profitto_parte_da_sola_in_manuale():
    """Ingresso 10 a 1,60, al 81' il libro e' 1,40/1,42: chiudere blocca un
    profitto -> la chiusura parte anche a uscite MANUALI, nessuna proposta, ed
    e' identica a quella in automatico."""
    s = _al_minuto(1.40, 1.42)
    dm = E.decide(_rientro_aperto(), s, params_e(uscite_automatiche=False,
                                                 reentry_exit_until_min=80))
    da = E.decide(_rientro_aperto(), s, params_e(uscite_automatiche=True,
                                                 reentry_exit_until_min=80))
    assert _posti_e(dm) and _posti_e(dm) == _posti_e(da)
    assert dm.state == "REENTRY_GREEN_PENDING" and dm.updates["close_reason"] == "reentry_time"
    assert not isinstance(dm.updates.get("uscita_proposta"), dict)
    t = dm.telemetry["uscita_a_tempo"]
    assert t["bloccato"] > 0 and t["in_perdita"] is False and isinstance(t["bloccato"], float)


def test_m3_reentry_time_in_perdita_resta_proposta():
    s = _al_minuto(1.70, 1.72)
    d = E.decide(_rientro_aperto(), s, params_e(uscite_automatiche=False,
                                                reentry_exit_until_min=80))
    assert _posti_e(d) == []
    assert d.updates["uscita_proposta"]["close_reason"] == "reentry_time"
    assert d.telemetry["uscita_a_tempo"]["bloccato"] < 0


def test_m3_reentry_time_senza_numero_resta_in_perdita():
    """Fail-closed: una decisione ``reentry_time`` senza il P&L bloccato e'
    trattata come in perdita (proposta)."""
    d = E.Decision("REENTRY_GREEN_PENDING", [], "x", {"close_reason": "reentry_time"})
    assert E.uscita_in_perdita(d) is True
    d.telemetry["uscita_a_tempo"] = {"bloccato": 0.0}
    assert E.uscita_in_perdita(d) is False


def test_m3_banco_g3_coerente_con_reentry_time():
    """G3: una proposta ``reentry_time`` con la chiusura IN PROFITTO al libro e'
    una violazione; in perdita no. Il motore vero non la produce (tace)."""
    p = params_e(uscite_automatiche=False, reentry_exit_until_min=80)
    prop = E.Decision("REENTRY_OPEN", [], "proposta", {"uscita_proposta": {
        "chiave": "rientro|c0", "categoria": "rientro", "close_reason": "reentry_time",
        "motivo": "re-ingresso: chiusura a mercato"}})
    cod = [v.codice for v in CERT.verifica(_rientro_aperto(), _al_minuto(1.40, 1.42), prop, p)]
    assert "G3" in cod
    cod = [v.codice for v in CERT.verifica(_rientro_aperto(), _al_minuto(1.70, 1.72), prop, p)]
    assert "G3" not in cod
    for bb, bl in ((1.40, 1.42), (1.70, 1.72)):
        ctx, s = _rientro_aperto(), _al_minuto(bb, bl)
        d = E.decide(ctx, s, p)
        assert "G3" not in [v.codice for v in CERT.verifica(ctx, s, d, p)], d.reason


# ===========================================================================
# 4) il resto sotto minimo va nel registro (mike_activity)
# ===========================================================================
def _scoperta_con_copertura_quasi_piena() -> Dict[str, Any]:
    """Punta Under 3,5 10,00 a 1,50 e banca Under 4,5 di copertura abbinata
    12,30 su 12,63 (numeri di ``test_mike_p5_copertura_banca``): resta 0,33,
    sotto il minimo di una bancata."""
    ko = NOW - timedelta(minutes=20)
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", entry_price_initial=1.50, legs=[
        E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back",
              price=1.50, size=10.0, matched=10.0, avg_price=1.50, ref="under_entry-0-1",
              status="open", placed_at=ko.timestamp() - 3600),
        E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_UNDER, side="lay",
              price=1.18, size=12.63, matched=12.30, avg_price=1.18, ref="over_cover-0-2",
              status="open", placed_at=ko.timestamp() + 600)])
    return {
        "event_id": "E1", "event_name": "Roma v Lazio", "state": ctx.state, "cycle_no": 0,
        "entry_price_initial": 1.50,
        "markets": {"OU35": {"market_id": "1.35"}, "OU45": {"market_id": "1.45"}},
        "positions": [dataclasses.asdict(l) for l in ctx.legs],
        "dossier": {}, "live": {}, "mode": "paper", "ko_at": ko.isoformat(),
        "ctx": {"seen_inplay": True, "last_goals": 0}}


def test_m4_resto_sotto_minimo_della_copertura_e_una_riga_del_registro(runner):
    db = FakeDB(params={"stake": 10, "cover_form": E.COVER_LAY_U45,
                        "cover_policy": "immediate"})
    db.events["E1"] = _scoperta_con_copertura_quasi_piena()
    db.trades = [
        {"id": 1, "event_id": "E1", "signal_key": "under_entry-0-1", "status": "open", "pnl": 0},
        {"id": 2, "event_id": "E1", "signal_key": "over_cover-0-2", "status": "open", "pnl": 0},
    ]
    ko = NOW - timedelta(minutes=20)
    p = payload(inplay=True, minute=20, sh=0, sa=0, ko=ko, u45=(1.17, 1.18, 500.0, 500.0))
    run(db, FakeMarket(), NOW, [row(p)])
    t = NOW + timedelta(seconds=3)
    run(db, FakeMarket(), t, [row(p, updated=t)])
    righe = [(pl, e) for k, pl, e in db.activity if k == "cover_resto_sotto_minimo"]
    assert len(righe) == 1, db.kinds()
    pl, eid = righe[0]
    assert eid == "E1" and state(db) == "LIVE_COVERED"
    assert pl["resto"] == 0.33 and isinstance(pl["resto"], float)
    assert pl["minimo"] == E.IT_LAY_MIN and pl["form"] == E.COVER_LAY_U45
    assert pl["state"] == "LIVE_COVERED" and pl["ciclo"] == 0 and isinstance(pl["ciclo"], int)
    assert runner.comandi == [], "nessun secondo ordine per il resto"


def test_m4_una_riga_per_episodio_e_residuo_non_piazzabile():
    """``_registra_resti`` scrive UNA volta per episodio (stessa decisione due
    volte = una riga), e un episodio nuovo (altro importo) ne scrive un'altra.
    Il residuo del 4,5 ha le sue chiavi (``sbilancio``, ``tolleranza``)."""
    db = FakeDB()
    extra: Dict[str, Any] = {}
    ctx = E.MatchCtx(state="LIVE_CLOSING", cycle_no=1)
    r = {"mercato": "OU45", "sbilancio": 0.09, "tolleranza": 0.105, "se_vince_under": 1.0,
         "se_vince_over": 0.91, "nota": "x"}
    d = E.Decision("FLAT", [], "chiuso", telemetry={"residuo_non_piazzabile": r})
    S._registra_resti(db, extra, d, ctx, "E1")
    S._registra_resti(db, extra, d, ctx, "E1")
    righe = [pl for k, pl, _e in db.activity if k == "residuo_non_piazzabile"]
    assert len(righe) == 1
    assert righe[0]["sbilancio"] == 0.09 and righe[0]["state"] == "FLAT" and righe[0]["ciclo"] == 1
    d2 = E.Decision("FLAT", [], "chiuso", telemetry={"residuo_non_piazzabile": {**r, "sbilancio": 0.07}})
    S._registra_resti(db, extra, d2, ctx, "E1")
    assert len([1 for k, _p, _e in db.activity if k == "residuo_non_piazzabile"]) == 2
    # senza telemetria: niente
    S._registra_resti(db, extra, E.Decision("FLAT", [], "x"), ctx, "E1")
    assert len(db.activity) == 2


# ===========================================================================
# 5) due prove mancanti (revisione M3: B-6 e B-10)
# ===========================================================================
def test_m5_b6_banca_uscita_dai_correnti_letta_abbinata_per_bet_id(monkeypatch):
    """M6.2 ramo ABBINATO: la lay appoggiata non e' piu' fra i correnti e
    Betfair (sportello di PRODUZIONE ``omega_market``, client con le chiavi
    grezze) la dice regolata per intero: la gamba e' ABBINATA (posizione), non
    ignota, e niente riconciliazione."""
    from Betfair.mike.tests.test_mike_ko_green_appoggiata_2026_09_16 import (
        DbFinto, gamba_uscita)
    from Betfair.mike.tests.test_mike_ko_green_appoggiata_2026_09_16 import KO as KO_G
    from Betfair.mike.tests.test_mike_p4_ordini_2026_09_29 import (
        ClientBetfair, _collega, regolato)
    monkeypatch.setattr(
        S, "_trade_row_for_leg",
        lambda db, eid, leg, cache=None: {
            "id": 1, "meta": {}, "status": "pending", "bet_id": "B1", "mode": "live",
            "signal_key": leg.ref, "market_id": "1.234", "selection_id": 47999})
    _collega(monkeypatch, ClientBetfair(regolati={"SETTLED": [
        regolato(stato="SETTLED", regolato_eur=10.14, prezzo=1.47)]}))
    leg = gamba_uscita()
    db = DbFinto()
    S._segui_resting_live(db=db, market=S._real_market, leg=leg, extra={},
                          params=C.merge_params({"ko_green_retry_s": 60}),
                          now_ts=KO_G + 10.0, ev={"event_id": "E1"})
    assert leg.status == "open", "abbinata per bet_id: e' una posizione, non ignota"
    assert leg.matched == pytest.approx(10.14) and leg.avg_price == pytest.approx(1.47)
    p = db.payload("rilettura_alla_riapertura")
    assert p["esito"] == "abbinato" and p["fonte"] == "fuori_dai_correnti"
    assert "reconcile_pending" not in db.kinds()
    assert "ordine_scaduto_alla_sospensione" not in db.kinds()


def test_m5_b10_tetto_per_partita_sul_rischio_al_prezzo_LIMITE():
    """La banca Under 4,5 (12,63, miglior prezzo 1,18, limite 1,20) con uno
    spazio di 2,40 sotto il tetto: al miglior prezzo rischierebbe 2,27 (ci
    starebbe), al LIMITE 2,53 (no). Il tetto conta il limite: la size scende a
    12,00 (rischio 2,40 al limite)."""
    from Betfair.mike.tests.test_mike_p5_copertura_banca_2026_09_29 import (
        fotografia, params as params_p5, scoperta)
    ctx = scoperta()
    spazio = 2.40
    p = params_p5(max_liability_per_match=E.invested(ctx.legs) + spazio)
    assert E.liability_room(ctx, p) == pytest.approx(spazio)
    d = E.decide(ctx, fotografia(), p)
    [a] = [x for x in d.actions if x.kind == "place"]
    assert (a.role, a.side, a.price) == ("over_cover", "lay", 1.20)
    assert a.size == 12.00
    assert a.size * (a.price - 1.0) <= spazio + 1e-9
    # confine: con spazio sufficiente al limite resta l'importo pieno
    p2 = params_p5(max_liability_per_match=E.invested(ctx.legs) + 2.60)
    [b] = [x for x in E.decide(scoperta(), fotografia(), p2).actions if x.kind == "place"]
    assert b.size == 12.63


# ===========================================================================
# 6) righe ``ko_green`` appoggiate e scadute: stessa scrittura in live e paper
# ===========================================================================
def _uscita_al_fischio() -> E.Leg:
    return E.Leg(role="ko_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                 price=1.69, size=10.12, ref="ko_green-0-4", cycle_no=0,
                 placed_at=NOW.timestamp())


def _riga(db: FakeDB, ref: str) -> Dict[str, Any]:
    return [t for t in db.trades if t.get("signal_key") == ref][-1]


def _riga_live_scaduta(monkeypatch) -> Dict[str, Any]:
    from Betfair.mike.tests.test_mike_ko_green_appoggiata_2026_09_16 import MercatoFinto
    from Betfair.safe_strategy import execution as X
    monkeypatch.setattr(X, "_freno_aperture", lambda: None)
    monkeypatch.setattr(X, "_live_brake", lambda: None)
    monkeypatch.setattr(S, "_freno_aperture_rest", lambda: None)
    monkeypatch.setattr(S, "mike_live_abilitato", lambda: True)
    db = FakeDB(mode="live")
    mk = MercatoFinto()
    leg = _uscita_al_fischio()
    info = F.event_info("E1", payload(inplay=True, minute=1, sh=0, sa=0))
    params = C.merge_params(None)
    S._piazza_resting_live(db=db, market=mk, info=info, leg=leg, mode="live", params=params,
                           minuto=1, score="0-0", chiude=None, motivo=None,
                           ev={"event_id": "E1"})
    assert leg.status == "pending" and _riga(db, leg.ref)["status"] == "pending"
    assert _riga(db, leg.ref)["size"] == pytest.approx(10.12), "pending: size = chiesto"
    # uscita dai correnti, Betfair per bet_id: scaduta senza abbinato (LAPSE)
    mk.per_bet_id["B1"] = {"found": True, "size_matched": 0.0, "avg_price_matched": None,
                           "size_remaining": 0.0, "matched_date": None, "placed_date": None}
    S._segui_resting_live(db=db, market=mk, leg=leg, extra={}, params=params,
                          now_ts=NOW.timestamp() + 60, ev={"event_id": "E1"})
    assert leg.status == "cancelled"
    return _riga(db, leg.ref)


def _riga_paper_scaduta(runner) -> Dict[str, Any]:
    db = FakeDB()
    leg = _uscita_al_fischio()
    info = F.event_info("E1", payload(inplay=True, minute=1, sh=0, sa=0))
    params = C.merge_params(None)
    S._piazza_resting_paper(db=db, market=FakeMarket(), info=info, leg=leg, params=params,
                            minuto=1, score="0-0", chiude=None, motivo=None,
                            ev={"event_id": "E1"}, now=NOW)
    assert leg.status == "pending"
    runner.scadi(str(_riga(db, leg.ref)["meta"]["canale_ref"]))
    S._segui_ordini_paper_su_runner(db=db, ctx=E.MatchCtx(legs=[leg]), ev={"event_id": "E1"},
                                    now_ts=NOW.timestamp() + 60, params=params)
    assert leg.status == "cancelled"
    return _riga(db, leg.ref)


def test_m6_ko_green_scaduta_stessa_riga_in_live_e_in_paper(monkeypatch, runner):
    live = _riga_live_scaduta(monkeypatch)
    paper = _riga_paper_scaduta(runner)
    campi = ("status", "side", "price", "size")
    assert {k: live[k] for k in campi} == {k: paper[k] for k in campi}, (live, paper)
    assert live["size"] == pytest.approx(10.12), "size = CHIESTO su una riga mai abbinata"
    assert live["status"] == "error"
    assert live.get("size_matched") == 0.0 and live.get("size_requested") == pytest.approx(10.12)


def test_m6_confine_abbinata_per_intero_size_e_l_abbinato(monkeypatch):
    """Confine: la lay appoggiata live che si abbina per intero porta ``size`` =
    abbinato (come la riga paper chiusa dal runner con un abbinato)."""
    from Betfair.mike.tests.test_mike_ko_green_appoggiata_2026_09_16 import MercatoFinto
    from Betfair.safe_strategy import execution as X
    monkeypatch.setattr(X, "_freno_aperture", lambda: None)
    monkeypatch.setattr(X, "_live_brake", lambda: None)
    monkeypatch.setattr(S, "_freno_aperture_rest", lambda: None)
    monkeypatch.setattr(S, "mike_live_abilitato", lambda: True)
    db, mk, leg = FakeDB(mode="live"), MercatoFinto(), _uscita_al_fischio()
    info = F.event_info("E1", payload(inplay=True, minute=1, sh=0, sa=0))
    S._piazza_resting_live(db=db, market=mk, info=info, leg=leg, mode="live",
                           params=C.merge_params(None), minuto=1, score="0-0", chiude=None,
                           motivo=None, ev={"event_id": "E1"})
    mk.correnti = [{"bet_id": "B1", "customer_order_ref": f"mike-t{_riga(db, leg.ref)['id']}",
                    "market_id": info.market_id(E.MARKET_OU35),
                    "selection_id": info.selection_id(E.MARKET_OU35, E.SEL_UNDER),
                    "side": "LAY", "status": "EXECUTION_COMPLETE", "size_matched": 10.12,
                    "size_remaining": 0.0, "avg_price_matched": 1.69}]
    S._segui_resting_live(db=db, market=mk, leg=leg, extra={}, params=C.merge_params(None),
                          now_ts=NOW.timestamp() + 60, ev={"event_id": "E1"})
    r = _riga(db, leg.ref)
    assert leg.status == "open" and r["status"] == "open"
    assert r["size"] == pytest.approx(10.12) and r["size_matched"] == pytest.approx(10.12)
