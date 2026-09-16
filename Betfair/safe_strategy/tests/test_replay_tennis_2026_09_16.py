# -*- coding: utf-8 -*-
"""C.4 — i controlli di SAFE TENNIS sanno diventare ROSSI, e il doppio del
database parla come il vero.

Tre famiglie:

  1. CONTRATTO — ogni metodo di `DbMemoriaSafe` ha la stessa firma della
     funzione omonima di `Betfair/safe_strategy/bot_db.py` (difetto 27 del
     catalogo: «i finti con chiavi o tipi diversi dal vero certificano il
     difetto»).
  2. FALSIFICAZIONE — per ogni controllo si costruisce il caso in cui la regola
     e' VIOLATA e si pretende il rosso. Un controllo che non sa diventare rosso
     non certifica (PROCESSO_STANDARD_BOT §6.7).
  3. CERTIFICAZIONE (marcata `cert`) — un segmento breve del replay vero sulla
     registrazione di riferimento `35790650`, cosi' che una modifica al bot
     rilanci la certificazione di default.
"""
from __future__ import annotations

import inspect
import os
from datetime import datetime, timezone

import pytest

from Betfair.safe_strategy import bot_db as DB
from Betfair.safe_strategy import bot_service as BS
from Betfair.safe_strategy import certificazione_tennis as CERT
from Betfair.safe_strategy import engine as E
from Betfair.safe_strategy import exits as XE
from Betfair.safe_strategy.tools import replay_tennis as RT

EVENTO = RT.EVENTO_DI_RIFERIMENTO


# ---------------------------------------------------------------------------
# 1. CONTRATTO — il doppio parla come il vero
# ---------------------------------------------------------------------------
def _nomi_parametri(fn) -> list:
    return [p.name for p in inspect.signature(fn).parameters.values()
            if p.name != "self"]


def _accetta_tutto(fn) -> bool:
    tipi = {p.kind for p in inspect.signature(fn).parameters.values()}
    return (inspect.Parameter.VAR_POSITIONAL in tipi
            or inspect.Parameter.VAR_KEYWORD in tipi)


METODI_DEL_BOT = (
    "read_control", "set_control", "log", "insert_trade", "update_trade",
    "delete_trade", "get_trade", "list_trades", "open_trades",
    "closing_trades_for", "trade_by_idempotency_key", "traded_signal_keys",
    "aggregates", "place_attempts", "recent_activity", "pending_requests",
    "proposta_di_chiusura_viva", "scrivi_proposta_di_chiusura", "chiudi_proposta",
    "set_request_status", "fail_stale_processing", "upsert_opportunities",
    "purge_opportunities", "delete_opportunities", "get_event",
    "fixtures_for_window", "fixture_analysis", "fetch_scan_rows",
    "scanner_status", "live_follow_status", "runner_heartbeat",
    "enqueue_live_order", "get_live_order_request", "get_live_order_request_by_ref",
    "revoke_live_order_request", "get_live_order_mirror",
)


def _db() -> RT.DbMemoriaSafe:
    ora = datetime(2026, 7, 7, 13, 0, tzinfo=timezone.utc)
    return RT.DbMemoriaSafe({"status": "running", "mode": "live", "params": {}},
                            orologio=lambda: ora)


def test_db_memoria_ha_tutti_i_metodi_del_vero():
    db = _db()
    mancanti = [n for n in METODI_DEL_BOT if not callable(getattr(db, n, None))]
    assert not mancanti, f"il doppio non risponde a: {mancanti}"


def test_db_memoria_ha_le_firme_del_vero():
    """Stessi NOMI di parametro, nello stesso ordine: un doppio che chiede
    `mode` dove il vero chiede `status` fa passare un test e rompere il live."""
    db = _db()
    diverse = []
    for nome in METODI_DEL_BOT:
        vero = getattr(DB, nome, None)
        finto = getattr(db, nome, None)
        if vero is None or finto is None:
            continue
        if _accetta_tutto(finto):
            continue     # accetta qualunque cosa: non puo' divergere
        attesi, offerti = _nomi_parametri(vero), _nomi_parametri(finto)
        # I PRIMI parametri devono coincidere nome per nome e in ordine. Il
        # doppio puo' averne di piu' IN CODA solo se hanno un default: e' il
        # caso di `log(kind, payload, event_id=None)` del banco comune, che un
        # chiamante scritto sulla firma vera non vede nemmeno. Meno parametri,
        # o gli stessi in ordine diverso, sono invece una firma divergente.
        if offerti[:len(attesi)] != attesi:
            diverse.append((nome, attesi, offerti))
            continue
        senza_default = [p.name for p in
                         list(inspect.signature(finto).parameters.values())[len(attesi):]
                         if p.default is inspect.Parameter.empty]
        if senza_default:
            diverse.append((nome, attesi, offerti))
    assert not diverse, f"firme divergenti dal vero: {diverse}"


def test_insert_trade_torna_id_e_rispetta_l_indice_unico():
    db = _db()
    riga = {"event_id": "1", "signal_key": "k", "origin": "auto", "status": "pending",
            "strategy": "tennis", "mode": "live"}
    tid = db.insert_trade(dict(riga))
    assert isinstance(tid, int) and tid > 0          # il vero torna l'ID, non la riga
    with pytest.raises(RuntimeError):
        db.insert_trade(dict(riga))                  # uq_safe_trades_signal


def test_aggregates_ha_le_chiavi_del_vero():
    db = _db()
    db.insert_trade({"event_id": "1", "signal_key": "k", "origin": "auto",
                     "status": "open", "strategy": "tennis", "mode": "live",
                     "liability": 2.0, "size": 2.0, "price": 1.05, "pnl": 0.0})
    agg = db.aggregates(mode="live")
    assert set(DB._AGG_KEYS).issubset(set(agg)), sorted(set(DB._AGG_KEYS) - set(agg))


def test_traded_signal_keys_filtra_per_modalita_come_il_vero():
    db = _db()
    db.insert_trade({"event_id": "1", "signal_key": "k", "origin": "auto",
                     "status": "open", "strategy": "tennis", "mode": "paper"})
    assert db.traded_signal_keys(mode="live") == set()
    assert db.traded_signal_keys(mode="paper") == {("1", "k")}


# ---------------------------------------------------------------------------
# 2. FALSIFICAZIONE — ogni controllo sa diventare rosso
# ---------------------------------------------------------------------------
PARAMS = BS.resolve_params({"variants": ["tennis"],
                            "strategy_modes": {"tennis": "live"}})
XP = XE.exit_params(PARAMS)


def _payload(sets=(1, 0), games=(4, 1), inplay=True, competizione="Challenger BO3"):
    return {"event_name": "A v B", "p1": "A", "p2": "B", "inplay": inplay,
            "competition": competizione, "mo_market_id": "1.1", "mo_status": "OPEN",
            "sets": {"p1": sets[0], "p2": sets[1]},
            "games": {"p1": games[0], "p2": games[1]},
            "odds": {"p1": {"back": 1.05, "lay": 1.06, "back_size": 50.0,
                            "lay_size": 50.0, "selection_id": 11},
                     "p2": {"back": 12.0, "lay": 14.0, "back_size": 5.0,
                            "lay_size": 5.0, "selection_id": 22}},
            "odds_ts_ms": 1.0}


def _riga(payload=None, updated_at="2026-07-07T13:00:00+00:00"):
    return {"event_id": EVENTO, "sport": "tennis",
            "payload": payload if payload is not None else _payload(),
            "updated_at": updated_at}


def _trade(**kw):
    """Una riga di `safe_strategy_trades` con le CHIAVI VERE di `_reserve_row`."""
    base = BS._reserve_row(
        event_id=EVENTO, event_name="A v B", sport="tennis", strategy="tennis",
        market_id="1.1", market_type="MATCH_ODDS", selection_id=11,
        selection_name="A", side="back", mode="live", price=1.05, size=2.0,
        liability=2.0, commission=0.05, minute=None,
        score="set 1-0 " + E.MIDDOT + " game 4-1", origin="auto",
        signal_key=EVENTO + ":tennis:set 1-0", meta={"variant": "tennis"})
    base["id"] = kw.pop("id", 1)
    meta = {**base["meta"], **(kw.pop("meta", {}) or {})}
    base.update(kw)
    base["meta"] = meta
    return base


def _ordine(ref="safe-t1", **kw):
    """Un ordine nella forma di `omega_market.list_current_orders` (snake_case)."""
    riga = {"bet_id": "b1", "market_id": "1.1", "selection_id": 11, "side": "back",
            "status": "EXECUTION_COMPLETE", "size_matched": 2.0,
            "avg_price_matched": 1.05, "average_price_matched": 1.05,
            "size_remaining": 0.0, "size_settled": 2.0, "customer_order_ref": ref,
            "size_cancelled": 0.0, "size_lapsed": 0.0, "size_voided": 0.0,
            "price_requested": 1.05, "size_requested": 2.0}
    riga.update(kw)
    return riga


def _osserva(**kw) -> CERT.Osservazione:
    base = dict(now_ts=1783430000.0, quando="prova", scenario="prova",
                stato_bot="running", modo_servizio="live", modo_strategia="live",
                params=PARAMS, xp=XP, row=_riga(), payload=_payload(),
                feed_fresco=True, trades=[], aperture=[], chiusure=[], ordini=[],
                rifiutati=[], attivita=[], proposte=[], errore_servizio="")
    base.update(kw)
    return CERT.Osservazione(**base)


def _codici(oss) -> set:
    sol = {}
    return {v.codice for v in CERT.verifica(oss, sol)}, sol


def _ctx(payload=None, osservato=99.0):
    return E.build_tennis_ctx_from_scan(EVENTO, payload or _payload(), osservato)


def _apertura(trade=None, ordine=None):
    return [{"trade": trade or _trade(status="open"), "ordine": ordine or _ordine()}]


def test_t1_verde_e_rosso():
    ok = _osserva(ctx=_ctx(), aperture=_apertura())
    cod, sol = _codici(ok)
    assert sol.get("T1") == 1 and "T1" not in cod
    ko = _osserva(ctx=_ctx(), aperture=_apertura(trade=_trade(status="open", side="lay")))
    assert "T1" in _codici(ko)[0]
    ko2 = _osserva(ctx=_ctx(),
                   aperture=_apertura(trade=_trade(status="open", price=1.55)))
    assert "T1" in _codici(ko2)[0]


def test_t2_rosso_senza_vantaggio_di_game():
    p = _payload(sets=(1, 0), games=(4, 4))
    ko = _osserva(row=_riga(p), payload=p, ctx=_ctx(p), aperture=_apertura())
    assert "T2" in _codici(ko)[0]


def test_t2_rosso_con_due_set_gia_giocati():
    p = _payload(sets=(2, 1), games=(4, 1))
    ko = _osserva(row=_riga(p), payload=p, ctx=_ctx(p), aperture=_apertura())
    assert "T2" in _codici(ko)[0]


def test_t3_rosso_col_punteggio_non_confermato():
    ko = _osserva(ctx=_ctx(osservato=2.0), aperture=_apertura())
    assert "T3" in _codici(ko)[0]


def test_t4_rosso_su_doppio_e_su_slam_maschile():
    p = _payload()
    p["p1"], p["p2"] = "A/C", "B/D"
    ko = _osserva(row=_riga(p), payload=p, ctx=_ctx(p), aperture=_apertura())
    assert "T4" in _codici(ko)[0]
    p2 = _payload(competizione="Wimbledon")
    ko2 = _osserva(row=_riga(p2), payload=p2, ctx=_ctx(p2), aperture=_apertura())
    assert "T4" in _codici(ko2)[0]


def test_t5_rosso_sul_take_profit_sotto_soglia():
    t = _trade(status="open", price=1.02,
               meta={XE.REQUEST_KEY: {"kind": "profit", "reason": "leader_vince_il_game",
                                      "sent": True},
                     XE.TRACK_KEY: {"side": "p1", "entry_price": 1.02}})
    ko = _osserva(ctx=_ctx(), trades=[t])
    cod, sol = _codici(ko)
    assert sol.get("T5") == 1 and "T5" in cod
    # sopra la soglia il take profit e' legittimo
    t_ok = _trade(status="open", price=1.06,
                  meta={XE.REQUEST_KEY: {"kind": "profit", "sent": True},
                        XE.TRACK_KEY: {"side": "p1", "entry_price": 1.06}})
    assert "T5" not in _codici(_osserva(ctx=_ctx(), trades=[t_ok]))[0]


def test_t6_rosso_se_un_ingresso_a_1_02_viene_chiuso_volontariamente():
    t = _trade(status="open", price=1.02,
               meta={XE.REQUEST_KEY: {"kind": "time", "sent": True},
                     XE.TRACK_KEY: {"side": "p1", "entry_price": 1.02}})
    assert "T6" in _codici(_osserva(ctx=_ctx(), trades=[t]))[0]
    # un'uscita OBBLIGATORIA a quella quota e' invece dovuta
    t_ok = _trade(status="open", price=1.02,
                  meta={XE.REQUEST_KEY: {"kind": "mandatory", "sent": True},
                        XE.TRACK_KEY: {"side": "p1", "entry_price": 1.02}})
    assert "T6" not in _codici(_osserva(ctx=_ctx(), trades=[t_ok]))[0]


def _traccia_obbligo(**extra):
    base = {"side": "p1", "entry_sets": [1, 0], "entry_games": [4, 1],
            "entry_price": 1.05, "consecutive_lost": 2, "set_lead_lost": True,
            "last_games": [4, 4], "last_sets": [1, 0]}
    base.update(extra)
    return base


def test_t7_rosso_se_l_obbligo_non_produce_una_uscita_mandatory():
    t = _trade(status="open", meta={XE.TRACK_KEY: _traccia_obbligo()})
    cod, sol = _codici(_osserva(ctx=_ctx(), trades=[t]))
    assert sol.get("T7") == 1 and "T7" in cod
    t_ok = _trade(status="open",
                  meta={XE.TRACK_KEY: _traccia_obbligo(),
                        XE.REQUEST_KEY: {"kind": "mandatory", "sent": True}})
    assert "T7" not in _codici(_osserva(ctx=_ctx(), trades=[t_ok]))[0]


def test_t7_rosso_se_l_obbligo_passa_dalla_decisione_a_modello():
    t = _trade(status="open", meta={XE.TRACK_KEY: _traccia_obbligo(),
                                    "exit_hold": {"why": "margine ampio"}})
    assert "T7" in _codici(_osserva(ctx=_ctx(), trades=[t]))[0]


def test_t7_approvazione_e_una_voce_dichiarata_non_una_violazione():
    par = BS.resolve_params({"variants": ["tennis"], "tennis_exit_approval": True,
                             "strategy_modes": {"tennis": "live"}})
    # ⚠️ la CHIAVE e' quella del servizio (`bot_service.PROPOSTA_KEY`), non una
    # riscritta a mano: con "exit_proposta" il controllo non vedeva la proposta
    # e accusava il bot di non uscire proprio dove l'utente vuole che non esca.
    t = _trade(status="open", meta={XE.TRACK_KEY: _traccia_obbligo(),
                                    BS.PROPOSTA_KEY: {"request_id": 1}})
    oss = _osserva(ctx=_ctx(), trades=[t], params=par)
    cod, _ = _codici(oss)
    assert "T7-APPROVAZIONE" in cod and "T7" not in cod
    ref = CERT.Referto(event_id=EVENTO)
    ref.violazioni.extend(CERT.verifica(oss, ref.sollecitati))
    assert ref.pulita, "una voce DICHIARATA non deve sporcare il referto"


def test_t8_dichiarata_misura_la_perdita_fuori_banda():
    # 16/09: gli stati TERMINALI che il bot scrive sono won/lost/void
    # (`bot_db.py:468,494`). Con `settled` — che il bot non scrive in nessun
    # punto — il controllo non aveva MAI un caso: e' il difetto trovato dal
    # replay del 16/09 e questo test lo fissa.
    for stato in ("lost", "void"):
        t = _trade(status=stato, size=2.0, pnl=-1.2)
        _cod, sol = _codici(_osserva(ctx=_ctx(), trades=[t]))
        assert sol.get("T8-DICHIARATA") == 1, stato
    assert "T8-DICHIARATA" not in _codici(
        _osserva(ctx=_ctx(), trades=[_trade(status="settled", size=2.0, pnl=-1.2)]))[0]
    # una perdita pari allo stake e' NORMALE con lo stake fisso (eccezione
    # dell'utente del 14/09): il controllo tace...
    t = _trade(status="lost", size=2.0, pnl=-2.0, side="back")
    assert "T8-DICHIARATA" not in _codici(_osserva(ctx=_ctx(), trades=[t]))[0]
    # ...e parla solo sull'impossibile: un back che perde PIU' dello stake
    t = _trade(status="lost", size=2.0, pnl=-3.0, side="back")
    assert "T8-DICHIARATA" in _codici(_osserva(ctx=_ctx(), trades=[t]))[0]
    t_ok = _trade(status="settled", size=2.0, pnl=-0.21)   # -10,5%: dentro 5-25%
    assert "T8-DICHIARATA" not in _codici(_osserva(ctx=_ctx(), trades=[t_ok]))[0]


def test_t9_rosso_se_la_chiusura_scorre_il_book():
    padre = _trade(id=1, status="open",
                   meta={XE.REQUEST_KEY: {"kind": "profit", "sent": True}})
    chiusura = _trade(id=2, status="open", side="lay", closes_trade_id=1,
                      meta={"exit_kind": "greenup", "closes_trade_id": 1,
                            "esecuzione": {"scorrimento_tick": 3,
                                           "price_richiesto": 1.04,
                                           "price_medio": 1.07,
                                           "size_richiesta": 2.0,
                                           "size_abbinata": 2.0,
                                           "size_residua": 0.0}})
    oss = _osserva(ctx=_ctx(), trades=[padre, chiusura],
                   chiusure=[{"trade": chiusura, "ordine": _ordine("safe-t2")}])
    cod, sol = _codici(oss)
    assert sol.get("T9") == 1 and "T9" in cod
    chiusura["meta"]["esecuzione"]["scorrimento_tick"] = 0
    assert "T9" not in _codici(_osserva(ctx=_ctx(), trades=[padre, chiusura],
                                        chiusure=[{"trade": chiusura,
                                                   "ordine": _ordine("safe-t2")}]))[0]


def test_t10_resta_non_esercitabile_finche_il_turno_non_c_e():
    cod, sol = _codici(_osserva(ctx=_ctx(), aperture=_apertura()))
    assert sol.get("T10", 0) == 0
    assert "T10" in CERT.CAUSE_NON_ESERCITABILI
    # ...ma si sveglia da solo il giorno in cui Betfair lo pubblicasse
    p = {**_payload(), "round": "Final"}
    cod2, sol2 = _codici(_osserva(row=_riga(p), payload=p, ctx=_ctx(p),
                                  aperture=_apertura()))
    assert sol2.get("T10") == 1 and "T10" in cod2


def test_t11_rosso_con_uno_stake_diverso_da_quello_della_strategia():
    par = BS.resolve_params({"variants": ["tennis"],
                             "strategy_modes": {"tennis": "live"},
                             "stake": {"per_strategia": {"tennis": 3.0}}})
    ko = _osserva(ctx=_ctx(), params=par,
                  aperture=_apertura(trade=_trade(status="open", size=2.0)))
    assert "T11" in _codici(ko)[0]
    ok = _osserva(ctx=_ctx(), params=par,
                  aperture=_apertura(trade=_trade(status="open", size=3.0)))
    assert "T11" not in _codici(ok)[0]


def test_t12_rosso_se_resta_un_residuo_vivo_dopo_il_piazzamento():
    ko = _osserva(ctx=_ctx(), ordini=[_ordine(status="EXECUTABLE", size_matched=1.0,
                                              size_remaining=1.0)])
    assert "T12" in _codici(ko)[0]
    assert "T12" not in _codici(_osserva(ctx=_ctx(), ordini=[_ordine()]))[0]


def test_t13_rosso_se_un_esito_ignoto_viene_ripiazzato():
    ignoto = _trade(id=1, status="pending",
                    meta={"reason": "place_exception_reconciling"})
    gemello = _trade(id=2, status="open")
    ko = _osserva(ctx=_ctx(), trades=[ignoto, gemello])
    cod, sol = _codici(ko)
    assert sol.get("T13") == 1 and "T13" in cod
    assert "T13" not in _codici(_osserva(ctx=_ctx(), trades=[ignoto]))[0]


def test_j1_rosso_con_due_gambe_di_chiusura_in_volo():
    padre = _trade(id=1, status="open")
    c1 = _trade(id=2, status="pending", closes_trade_id=1)
    c2 = _trade(id=3, status="pending", closes_trade_id=1)
    assert "J1" in _codici(_osserva(ctx=_ctx(), trades=[padre, c1, c2]))[0]
    # UNA sola in volo: nessuna violazione
    assert "J1" not in _codici(_osserva(ctx=_ctx(), trades=[padre, c1]))[0]


def test_j1_non_accusa_il_cash_out_parziale_piu_il_residuo():
    """Due chiusure gia' ABBINATE sulla stessa posizione sono il cash-out
    parziale piu' il residuo (§4.2), non un loop: `execution.hedge_state`
    blocca solo sulle 'pending'. Falso positivo trovato sul replay di
    35795560, dove il controllo accusava 713 giri di fila."""
    padre = _trade(id=1, status="open")
    parziale = _trade(id=2, status="open", side="lay", size=2.15, closes_trade_id=1)
    residuo = _trade(id=3, status="open", side="lay", size=0.09, closes_trade_id=1)
    cod, _ = _codici(_osserva(ctx=_ctx(), trades=[padre, parziale, residuo]))
    assert "J1" not in cod and "L1" not in cod


def test_j2_rosso_quando_un_ordine_non_abbinato_diventa_posizione():
    """Il controllo guarda l'ORDINE di Betfair, non la confessione del bot: e'
    la correzione fatta il 16/09 dopo che la falsificazione (`res.ok` tolto) era
    uscita VERDE perche' spariva anche l'attivita' `place_rifiutato`."""
    ko = _osserva(ctx=_ctx(),
                  aperture=_apertura(trade=_trade(status="open"),
                                     ordine=_ordine(size_matched=0.0,
                                                    size_cancelled=2.0)))
    cod, sol = _codici(ko)
    assert sol.get("J2") == 1 and "J2" in cod
    assert "J2" not in _codici(_osserva(ctx=_ctx(), aperture=_apertura()))[0]


def test_l1_rosso_con_due_lay_in_volo_sulla_stessa_selezione():
    """REGOLA DI PIATTAFORMA dell'utente (16/09): «non devono mai esserci 2 lay
    a mercato sullo stesso mercato/selezione, se si abbinano siamo scoperti»."""
    padre = _trade(id=1, status="open")
    lay1 = _trade(id=2, status="pending", side="lay", closes_trade_id=1)
    lay2 = _trade(id=3, status="pending", side="lay", closes_trade_id=1)
    cod, sol = _codici(_osserva(ctx=_ctx(), trades=[padre, lay1, lay2]))
    assert sol.get("L1") == 1 and "L1" in cod
    # una sola lay in volo: nessuna violazione
    assert "L1" not in _codici(_osserva(ctx=_ctx(), trades=[padre, lay1]))[0]


def test_l1_conta_anche_la_riga_in_riconciliazione():
    """§4.11: una gamba a esito IGNOTO puo' essere vivissima su Betfair — conta
    sempre nel rischio, peggior caso abbinata per intero."""
    padre = _trade(id=1, status="open")
    ignota = _trade(id=2, status="pending", side="lay", closes_trade_id=1,
                    meta={"reason": "place_exception_reconciling"})
    nuova = _trade(id=3, status="pending", side="lay", closes_trade_id=1)
    assert "L1" in _codici(_osserva(ctx=_ctx(), trades=[padre, ignota, nuova]))[0]


def test_l1_rosso_con_due_lay_ancora_executable_su_betfair():
    """La verita' e' il book di Betfair, non cio' che il bot crede di avere."""
    vivi = [_ordine("safe-t2", side="lay", status="EXECUTABLE", size_matched=0.0,
                    size_remaining=2.0),
            _ordine("safe-t3", side="lay", status="EXECUTABLE", size_matched=0.0,
                    size_remaining=2.0, bet_id="b2")]
    cod, sol = _codici(_osserva(ctx=_ctx(), ordini_vivi=vivi))
    assert sol.get("L1") == 1 and "L1" in cod
    # due lay su SELEZIONI diverse non sono un problema
    vivi[1]["selection_id"] = 22
    assert "L1" not in _codici(_osserva(ctx=_ctx(), ordini_vivi=vivi))[0]


def test_l2_rosso_sulla_sostituzione_cancel_piu_place_nello_stesso_giro():
    annullata = _ordine("safe-t2", side="lay", size_cancelled=2.0,
                        status="EXECUTION_COMPLETE", size_matched=0.0)
    nuova = _ordine("safe-t3", side="lay", bet_id="b2")
    cod, sol = _codici(_osserva(ctx=_ctx(), cancellati=[annullata], ordini=[nuova]))
    assert sol.get("L2") == 1 and "L2" in cod
    # annullo senza ri-piazzamento: nessuna violazione
    assert "L2" not in _codici(_osserva(ctx=_ctx(), cancellati=[annullata]))[0]


def test_j3_rosso_senza_average_price_matched():
    ko = _osserva(ctx=_ctx(),
                  aperture=_apertura(ordine=_ordine(average_price_matched=None)))
    assert "J3" in _codici(ko)[0]


def test_j3_rosso_se_la_riga_non_racconta_il_prezzo_dell_ordine():
    ko = _osserva(ctx=_ctx(),
                  aperture=_apertura(trade=_trade(status="open", price=1.05),
                                     ordine=_ordine(average_price_matched=1.02)))
    assert "J3" in _codici(ko)[0]


def test_j4_rosso_con_un_ref_diverso_da_quello_del_piazzamento():
    assert "J4" in _codici(_osserva(ctx=_ctx(),
                                    ordini=[_ordine(ref="omega-t1")]))[0]
    assert "J4" in _codici(_osserva(ctx=_ctx(),
                                    ordini=[_ordine(market_id=None)]))[0]
    assert "J4" not in _codici(_osserva(ctx=_ctx(), ordini=[_ordine()]))[0]


def test_j5_rosso_se_il_bet_id_non_finisce_sulla_riga():
    ko = _osserva(ctx=_ctx(),
                  aperture=_apertura(trade=_trade(status="open", bet_id=None)))
    cod, sol = _codici(ko)
    assert sol.get("J5") == 1 and "J5" in cod
    assert "J5" not in _codici(
        _osserva(ctx=_ctx(), aperture=_apertura(trade=_trade(status="open",
                                                             bet_id="b1"))))[0]


def test_c1_rosso_senza_la_consapevolezza_dell_ordine():
    ko = _osserva(ctx=_ctx(), aperture=_apertura(trade=_trade(status="open")))
    assert "C1" in _codici(ko)[0]
    buono = _trade(status="open", meta={"esecuzione": {
        "size_richiesta": 2.0, "size_abbinata": 2.0, "size_residua": 0.0,
        "price_medio": 1.05, "scorrimento_tick": 0}})
    assert "C1" not in _codici(_osserva(ctx=_ctx(),
                                        aperture=_apertura(trade=buono)))[0]


def test_s1_rosso_se_la_modalita_viene_ereditata():
    """Difetto 25 del catalogo: modalita' ereditata dal servizio invece che
    scritta per strategia."""
    par = BS.resolve_params({"variants": ["tennis"]})     # nessuno strategy_modes
    ko = _osserva(ctx=_ctx(), params=par, modo_servizio="live", modo_strategia="live")
    assert "S1" in _codici(ko)[0]
    ok = _osserva(ctx=_ctx(), params=par, modo_servizio="live", modo_strategia="paper")
    assert "S1" not in _codici(ok)[0]


def test_s1_rosso_se_la_riga_nasce_in_una_modalita_diversa():
    ko = _osserva(ctx=_ctx(), modo_strategia="live",
                  aperture=_apertura(trade=_trade(status="open", mode="paper")))
    assert "S1" in _codici(ko)[0]


def test_s2_rosso_se_a_bot_fermo_nasce_un_ingresso():
    ko = _osserva(ctx=_ctx(), stato_bot="stopped", aperture=_apertura())
    cod, sol = _codici(ko)
    assert sol.get("S2") == 1 and "S2" in cod
    assert "S2" not in _codici(_osserva(ctx=_ctx(), stato_bot="stopped"))[0]


def test_s3_rosso_se_si_entra_su_un_feed_non_fresco():
    ko = _osserva(ctx=_ctx(), feed_fresco=False, aperture=_apertura())
    assert "S3" in _codici(ko)[0]


def test_a1_rosso_se_il_servizio_solleva():
    assert "A1" in _codici(_osserva(ctx=_ctx(), errore_servizio="ValueError: x"))[0]


def test_ingresso_dichiarato_non_fa_giudicare_l_ingresso():
    """La posizione aperta DAL REPLAY non deve far scattare i controlli
    sull'ingresso: giudicare una scelta del banco come una scelta del bot e' il
    falso positivo del catalogo §7.16."""
    t = _trade(status="open", side="lay", price=1.99,
               meta={"ingresso_dichiarato": "il replay ha aperto qui"})
    cod, sol = _codici(_osserva(ctx=_ctx(), aperture=[{"trade": t,
                                                       "ordine": _ordine()}]))
    assert sol.get("T1", 0) == 0 and "T1" not in cod
    assert sol.get("T11", 0) == 0


def test_p1_vede_la_stessa_richiesta_ripetuta():
    and_ = CERT.Andamento()
    for _ in range(4):
        CERT.osserva(and_, _osserva(ctx=_ctx(), ordini=[_ordine()]))
    difetti = CERT.difetti_di_progettazione(and_)
    assert [d.codice for d in difetti] == ["P1"]


def test_ogni_controllo_e_registrato_una_volta_sola():
    codici = [c for c, _r in CERT.elenco_controlli()]
    assert len(codici) == len(set(codici))
    assert CERT.mai_sollecitati({}) == CERT.elenco_controlli()


# ---------------------------------------------------------------------------
# 2-bis. IL SIDECAR DEI PUNTEGGI DEL TENNIS SI CHIAMA `.score.jsonl`
# ---------------------------------------------------------------------------
# Difetto 32 del catalogo: «sidecar cercato con il nome sbagliato». Il
# validatore cercava solo `<id>.scores.jsonl` (il nome del CALCIO) e su OGNI
# registrazione tennis dichiarava `scores=NO` con centinaia di record dentro.
def test_il_validatore_trova_il_sidecar_del_tennis(tmp_path):
    from Betfair.stream.tools import validate_recordings as VR

    ev = tmp_path / "111"
    ev.mkdir()
    (ev / "111.raw.jsonl").write_text("", encoding="utf-8")
    (ev / "111.score.jsonl").write_text(
        '{"t": 1.0, "score": {"eventId": 111}}' + os.linesep, encoding="utf-8")
    rep = VR.validate_event(str(tmp_path), "111")
    assert rep.has_scores is True
    # ...e DICE quale ha trovato: «l'ho letto» e «l'ho cercato col nome giusto»
    # sono due fatti diversi
    assert rep.scores_name == "111.score.jsonl"
    assert rep.to_dict()["scores_name"] == "111.score.jsonl"


def test_il_validatore_preferisce_il_nome_del_calcio_quando_ci_sono_entrambi(tmp_path):
    from Betfair.stream.tools import validate_recordings as VR

    ev = tmp_path / "222"
    ev.mkdir()
    (ev / "222.raw.jsonl").write_text("", encoding="utf-8")
    (ev / "222.scores.jsonl").write_text("{}", encoding="utf-8")
    (ev / "222.score.jsonl").write_text("{}", encoding="utf-8")
    assert VR.validate_event(str(tmp_path), "222").scores_name == "222.scores.jsonl"


def test_il_validatore_dichiara_NO_quando_il_sidecar_manca_davvero(tmp_path):
    """FALSIFICAZIONE del controllo: se accettasse qualunque cosa, questo
    resterebbe verde con `has_scores=True` e il test non certificherebbe nulla."""
    from Betfair.stream.tools import validate_recordings as VR

    ev = tmp_path / "333"
    ev.mkdir()
    (ev / "333.raw.jsonl").write_text("", encoding="utf-8")
    (ev / "333.punteggi.jsonl").write_text("{}", encoding="utf-8")
    rep = VR.validate_event(str(tmp_path), "333")
    assert rep.has_scores is False and rep.scores_name == ""


# --- LA FINESTRA ATTESA DIPENDE DALLO SPORT (16/09) -----------------------
# Una partita di tennis non ha una durata attesa: misurarla con i 115 minuti
# del calcio e' misurarla con il metro di un altro sport.
def _raw_tennis(tmp_path, ev, *, primo_ms, ultimo_ms, chiuso, event_type="2"):
    import json as _json

    d = tmp_path / ev
    d.mkdir(exist_ok=True)
    md = {"eventTypeId": event_type, "eventId": ev, "marketType": "MATCH_ODDS",
          "marketTime": "2026-07-07T12:00:00.000Z", "inPlay": True, "status": "OPEN"}
    righe = []
    t = primo_ms
    while t <= ultimo_ms:
        righe.append(_json.dumps({"op": "mcm", "pt": t,
                                  "mc": [{"id": "1.1", "marketDefinition": dict(md)}]}))
        t += 30_000
    if chiuso:
        righe.append(_json.dumps({"op": "mcm", "pt": ultimo_ms,
                                  "mc": [{"id": "1.1",
                                          "marketDefinition": {**md, "status": "CLOSED"}}]}))
    (d / f"{ev}.raw.jsonl").write_text(os.linesep.join(righe), encoding="utf-8")
    return d


def test_una_partita_di_tennis_corta_e_COMPLETE_con_la_finestra_giusta(tmp_path):
    """60 minuti registrati per intero, con il CLOSED: e' COMPLETE. Con la
    finestra del calcio (ko+115m) la stessa registrazione stava sotto al 55 %."""
    from Betfair.stream.tools import validate_recordings as VR

    ko = 1783425600000     # 2026-07-07T12:00:00Z
    d = _raw_tennis(tmp_path, "901", primo_ms=ko, ultimo_ms=ko + 60 * 60_000, chiuso=True)
    (d / "901.score.jsonl").write_text(
        '{"t": %.1f, "score": {}}%s{"t": %.1f, "score": {}}'
        % (ko / 1000.0, os.linesep, (ko + 60 * 60_000) / 1000.0), encoding="utf-8")
    rep = VR.validate_event(str(tmp_path), "901")
    assert rep.sport == "tennis"
    assert rep.finestra == "tennis: primo book -> CLOSED del mercato"
    assert rep.verdict == VR.VERDICT_COMPLETE and rep.coverage_pct == 100.0
    # e la finestra usata finisce nel referto, non solo nella testa di chi guarda
    assert rep.to_dict()["finestra"] == rep.finestra


def test_senza_CLOSED_il_tennis_non_e_mai_COMPLETE(tmp_path):
    from Betfair.stream.tools import validate_recordings as VR

    ko = 1783425600000
    _raw_tennis(tmp_path, "902", primo_ms=ko, ultimo_ms=ko + 60 * 60_000, chiuso=False)
    rep = VR.validate_event(str(tmp_path), "902")
    assert rep.verdict == VR.VERDICT_PARTIAL
    assert any("fine NON confermata" in m for m in rep.reasons)


def test_il_sidecar_smaschera_la_registrazione_cominciata_a_meta(tmp_path):
    """CONTROLLO DI PLAUSIBILITA': dentro la sua finestra la registrazione non
    ha buchi, ma il sidecar dice che la partita e' durata il doppio. Senza
    questo controllo una registrazione cominciata al terzo set si sarebbe
    dichiarata coperta al 100 %."""
    from Betfair.stream.tools import validate_recordings as VR

    ko = 1783425600000
    d = _raw_tennis(tmp_path, "903", primo_ms=ko + 60 * 60_000,
                    ultimo_ms=ko + 120 * 60_000, chiuso=True)
    (d / "903.score.jsonl").write_text(
        '{"t": %.1f, "score": {}}%s{"t": %.1f, "score": {}}'
        % (ko / 1000.0, os.linesep, (ko + 120 * 60_000) / 1000.0), encoding="utf-8")
    rep = VR.validate_event(str(tmp_path), "903")
    assert rep.coverage_pct == 100.0          # dentro la finestra e' piena...
    assert rep.verdict == VR.VERDICT_PARTIAL  # ...ma la partita e' il doppio
    assert any("piu' CORTA della partita" in m for m in rep.reasons)
    assert rep.durata_sidecar_min == 120.0


def test_il_calcio_continua_a_usare_la_sua_finestra(tmp_path):
    """FALSIFICAZIONE al contrario: lo stesso file con `eventTypeId` 1 deve
    tornare alla finestra del calcio. Se la finestra per sport sparisse, questo
    e i tre test qui sopra direbbero la stessa cosa — e non certificherebbero."""
    from Betfair.stream.tools import validate_recordings as VR

    ko = 1783425600000
    _raw_tennis(tmp_path, "904", primo_ms=ko, ultimo_ms=ko + 60 * 60_000,
                chiuso=False, event_type="1")
    rep = VR.validate_event(str(tmp_path), "904")
    assert rep.sport == "calcio"
    assert rep.finestra.startswith("calcio:")
    # 60 minuti su una finestra attesa di 115: poco piu' della meta'
    assert 45.0 < (rep.coverage_pct or 0.0) < 60.0


@pytest.mark.skipif(not os.path.isdir(RT.cartella_predefinita()),
                    reason="registrazioni tennis assenti")
def test_finestra_tennis_sulle_registrazioni_di_riferimento():
    from Betfair.stream.tools import validate_recordings as VR

    for ev in (EVENTO, "35795560"):
        rep = VR.validate_event(RT.cartella_predefinita(), ev)
        assert rep.sport == "tennis"
        assert rep.finestra == "tennis: primo book -> CLOSED del mercato"
        assert rep.durata_sidecar_min and rep.durata_sidecar_min > 60.0


@pytest.mark.skipif(not os.path.isdir(RT.cartella_predefinita()),
                    reason="registrazioni tennis assenti")
def test_il_sidecar_del_tennis_di_riferimento_viene_letto():
    from Betfair.stream.tools import validate_recordings as VR

    rep = VR.validate_event(RT.cartella_predefinita(), EVENTO)
    assert rep.has_scores and rep.scores_name == f"{EVENTO}.score.jsonl"


# ---------------------------------------------------------------------------
# 3. CERTIFICAZIONE sul banco — segmento breve, nella suite di default
# ---------------------------------------------------------------------------
def _cartella() -> str:
    return RT.cartella_predefinita()


def _registrazione_presente() -> bool:
    return os.path.exists(os.path.join(_cartella(), EVENTO, f"{EVENTO}.raw.jsonl"))


@pytest.mark.cert
@pytest.mark.skipif(not _registrazione_presente(),
                    reason=f"registrazione {EVENTO} assente")
def test_cert_replay_base_non_apre_e_lo_dichiara():
    """Sulla partita di riferimento la strategia NON ha mai le sue condizioni:
    il referto lo deve dire coi numeri, non tacere."""
    ref = RT.certifica_evento(EVENTO, data_dir=_cartella(), scenario="base",
                              competizione=RT.COMPETIZIONE_DICHIARATA)
    assert ref.decisioni > 500, "il servizio deve aver girato davvero"
    assert ref.ordini_piazzati == 0
    assert ref.pulita, [str(v) for v in ref.violazioni]
    # il motivo del "no" e' misurato, non dedotto
    assert any("games" in m for m in ref.motivi), ref.motivi


@pytest.mark.cert
@pytest.mark.skipif(not _registrazione_presente(),
                    reason=f"registrazione {EVENTO} assente")
def test_cert_replay_uscita_approvata_chiude_al_prezzo_del_segnale():
    """Con la posizione dichiarata e la firma del trader la chiusura parte, e
    si abbina al prezzo ESATTO del segnale (HANDOFF_CONTROL_ROOM §2)."""
    ref = RT.certifica_evento(EVENTO, data_dir=_cartella(),
                              scenario="approvata-subito",
                              competizione=RT.COMPETIZIONE_DICHIARATA)
    assert ref.pulita, [str(v) for v in ref.violazioni]
    assert ref.sollecitati.get("T9", 0) >= 1, "nessuna chiusura da misurare"
    assert ref.sollecitati.get("C1", 0) >= 1
    # 16/09: con il settlement abilitato (`giri_dopo_il_fischio`) la riga non
    # resta 'hedged': arriva allo stato TERMINALE vero del bot.
    assert set(ref.stati_visti) & {"won", "lost", "hedged"}, ref.stati_visti


@pytest.mark.cert
@pytest.mark.skipif(not _registrazione_presente(),
                    reason=f"registrazione {EVENTO} assente")
def test_cert_replay_senza_firma_la_chiusura_resta_ferma():
    ref = RT.certifica_evento(EVENTO, data_dir=_cartella(), scenario="mai-approvata",
                              competizione=RT.COMPETIZIONE_DICHIARATA)
    assert ref.pulita, [str(v) for v in ref.violazioni]
    assert "hedged" not in ref.stati_visti, "senza firma non si chiude niente"


# ---------------------------------------------------------------------------
# 16/09 — IL SETTLEMENT DEL TENNIS ESISTE (e prima non esisteva)
# ---------------------------------------------------------------------------
# Due cause in fila lo impedivano: `MercatoFlumine` senza `read_market` e —
# misurato — il mercato CHIUSO che flumine consegna a `process_closed_market`,
# che il ponte del banco non inoltra: l'ULTIMO giro del servizio avveniva
# sempre a mercato OPEN. Senza settlement nessuna riga arriva a uno stato
# terminale e T8 non ha mai un caso.
_SINTETICA = "_synth_safe_tennis"


def _cartella_sintetica() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))), "_live_raw")


def _sintetica_presente() -> bool:
    return os.path.isfile(os.path.join(_cartella_sintetica(), _SINTETICA,
                                       f"{_SINTETICA}.raw.jsonl"))


@pytest.mark.cert
@pytest.mark.skipif(not _sintetica_presente(),
                    reason="registrazione sintetica assente: "
                           "python -m Betfair.safe_strategy.tools.synth_safe --tennis")
def test_cert_la_sintetica_arriva_al_SETTLEMENT_e_sveglia_t6_e_t8():
    """Registrazione SINTETICA (dichiarata): ingresso a 1,02, crollo, mercato
    CHIUSO con il WINNER dall'altra parte. Deve arrivare a uno stato TERMINALE
    vero del bot (won/lost) e svegliare T6 e T8, che sulla terna reale erano
    due ⊘."""
    ref = RT.certifica_evento(_SINTETICA, data_dir=_cartella_sintetica(),
                              scenario="base",
                              competizione=RT.COMPETIZIONE_DICHIARATA)
    assert ref.pulita, [str(v) for v in ref.violazioni]
    assert set(ref.stati_visti) >= {"won", "lost"}, ref.stati_visti
    assert ref.sollecitati.get("T6", 0) >= 1, "ingresso a 1,02 non riconosciuto"
    assert ref.sollecitati.get("T8-DICHIARATA", 0) >= 1, "nessuna riga regolata"


def test_i_giri_dopo_il_fischio_leggono_l_esito_dal_raw_registrato():
    """L'esito finale NON e' inventato: viene dall'ultimo `marketDefinition`
    della registrazione, che porta i WINNER/LOSER veri."""
    raw = os.path.join(_cartella_sintetica(), _SINTETICA, f"{_SINTETICA}.raw.jsonl")
    if not os.path.isfile(raw):
        pytest.skip("registrazione sintetica assente")
    finali = RT.esito_finale_dal_raw(raw)
    assert finali, "nessuna definizione di mercato letta"
    chiusi = [d for d in finali.values() if d["status"] == "CLOSED"]
    assert chiusi, "la registrazione non arriva a CLOSED"
    assert "WINNER" in set(chiusi[0]["runners"].values())
