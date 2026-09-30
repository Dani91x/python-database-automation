"""25/09/2026 - MIKE: L'INTERRUTTORE "USCITE AUTOMATICHE".

Ordine dell'utente (testuale): «Tutti i bot (in live e in paper) DEVONO AVERE
L'ABILITAZIONE per le uscite automatiche e per l'operativita' totalmente
automatica; se disattivo il pulsante (TUTTO DEVE ESSERE IN UI PER SINGOLO BOT),
le uscite le gestisco io manualmente tramite l'apposita scheda».

Parametro `uscite_automatiche` (mike_control.params, DEFAULT False dal 25/09
sera - ordine dell'utente: «di default tutte le uscite le voglio spente,
decido io se uscire o no, per tutti i bot»; prima del 25/09 sera il default
era True):
  * True  -> ``engine.decide`` identico a prima (parita');
  * False -> l'uscita DISCREZIONALE nuova (green pre-match, uscita al fischio,
    green del re-ingresso, cash out / uscita in perdita a modello) non parte:
    diventa ``ctx.uscita_proposta``; parte solo su approvazione
    (``ctx.uscita_approvata``, richiesta 'approva_uscita') o la chiude l'utente.
    Restano automatici: copertura Over 4.5, cap perdita partita, chiusure gia'
    in corso (riprezzo/residuo), regolamento.

29/09 (piano Mike, pacchetto P1, decisioni 13 e 16 dell'utente): le uscite
che bloccano un PROFITTO (green pre-partita, uscita al fischio, cash out a
soglia e intelligente, green del re-ingresso) partono SEMPRE da sole; resta una
proposta da firmare solo l'uscita che puo' chiudere IN PERDITA. Il cap di
perdita partita non chiude piu' (M4.5). I test della MECCANICA della proposta
(nascita, firma, scadenza, decadenza, riaccensione) usano ora l'uscita in
perdita all'intervallo come veicolo; quelli che dicevano "il green / il cash
out in profitto diventa proposta" dicono ora che parte da solo.

Finti: ``MatchCtx``/``Leg``/``Snapshot``/``Book`` sono le classi VERE del motore
(nessuna copia); i parametri passano da ``config.merge_params`` come in
produzione. File ASCII-only.
"""
from __future__ import annotations

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike.tests.test_mike_engine import (DENTRO_FINESTRA, KO, _live_covered,
                                                 _live_uncovered, book, fill, params,
                                                 snap)
from Betfair.mike.tests.test_mike_ko_green_appoggiata_2026_09_16 import (
    PAR as PAR_KO, ctx_in_uscita, snap as snap_ko)


def _spento(**over):
    return params(uscite_automatiche=False, **over)


def _entrata_abbinata(p):
    ctx = E.MatchCtx()
    s0 = snap(DENTRO_FINESTRA, u35=book(1.50))
    E.apply_decision(ctx, E.decide(ctx, s0, p), s0.now)
    fill(ctx.legs[0])
    return ctx, snap(DENTRO_FINESTRA + 5, u35=book(1.50))


def _cashout_in_profitto():
    return snap(KO + 30 * 60, u35=book(1.30, bl=1.31, inplay=True),
                o45=book(12.0, bl=12.5, inplay=True), inplay=True, minute=30, goals=0)


def _perdita_ht(now=KO + 46 * 60):
    """29/09 (P1): 2 gol all'intervallo, uscita in perdita tollerata: e' l'uscita
    che resta una PROPOSTA (vedi test_ht_loss_tolerated_exit)."""
    return snap(now, u35=book(2.20, bl=2.24, inplay=True), o45=book(6.0, bl=6.2, inplay=True),
                inplay=True, minute=45, goals=2, ht_active=True)


def _spento_perdita(**over):
    # finestra dell'uscita in perdita da 2 gol, come in `_live_covered`
    return _spento(ht_loss_goals_min=2, **over)


def _proposta_in_perdita(p):
    """Contesto a posizione coperta con la proposta d'uscita in perdita viva."""
    ctx, _ = _live_covered()
    s = _perdita_ht()
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    assert ctx.uscita_proposta["chiave"] == "chiusura|c0"
    return ctx, s


def _firma(d):
    return (d.state, [(a.kind, a.role, a.side, a.price, a.size) for a in d.actions],
            d.reason, d.updates, d.telemetry)


# ---------------------------------------------------------------------------
# il parametro
# ---------------------------------------------------------------------------
def test_default_ora_e_manuale():
    """25/09 sera: il default e' cambiato da True a False (ordine dell'utente)."""
    assert C.merge_params(None)["uscite_automatiche"] is False
    assert C.merge_params({"uscite_automatiche": True})["uscite_automatiche"] is True
    assert C.merge_params({"uscite_automatiche": False})["uscite_automatiche"] is False
    assert C.merge_params({"uscite_automatiche": "false"})["uscite_automatiche"] is False
    assert E.uscite_automatiche({}) is False
    assert E.uscite_automatiche({"uscite_automatiche": "boh"}) is False
    assert E.uscite_automatiche({"uscite_automatiche": True}) is True


# ---------------------------------------------------------------------------
# ACCESO = parita' esatta
# ---------------------------------------------------------------------------
def test_acceso_decisione_identica_a_prima_sul_green_pre_match():
    # 25/09 sera: il default e' ora manuale, quindi ENTRAMBI i lati del
    # confronto passano `uscite_automatiche=True` esplicito (prima del 25/09
    # sera p0 lo ereditava dal default, che era True).
    p0 = params(pre_exit_mode="resting", stake=20.0, uscite_automatiche=True)
    p1 = params(pre_exit_mode="resting", stake=20.0, uscite_automatiche=True)
    ctx_a, s = _entrata_abbinata(p0)
    ctx_b, _ = _entrata_abbinata(p1)
    assert _firma(E.decide(ctx_a, s, p0)) == _firma(E.decide(ctx_b, s, p1))


def test_acceso_il_cash_out_parte_come_prima():
    ctx, p = _live_covered()
    p["uscite_automatiche"] = True
    d = E.decide(ctx, _cashout_in_profitto(), p)
    assert d.state == "LIVE_CLOSING"
    assert sorted(a.role for a in d.actions) == ["over_close", "under_close"]
    assert "uscita_proposta" not in d.updates


# ---------------------------------------------------------------------------
# SPENTO = proposta, niente a mercato
# ---------------------------------------------------------------------------
def test_spento_il_green_pre_match_parte_da_solo():
    """29/09 (P1, M1.1): prima era una proposta; ora il green del pre-partita
    parte da solo anche a interruttore spento, identico all'acceso."""
    p = _spento(pre_exit_mode="resting", stake=20.0)
    ctx, s = _entrata_abbinata(p)
    d = E.decide(ctx, s, p)
    rif = E.decide(_entrata_abbinata(p)[0], s, params(pre_exit_mode="resting", stake=20.0))
    assert [(a.role, a.side, a.price, a.size) for a in d.actions] == \
        [(a.role, a.side, a.price, a.size) for a in rif.actions]
    assert d.actions[0].role == "under_green" and d.actions[0].price == pytest.approx(1.48)
    assert d.state == "PRE_OPEN" and d.updates["entry_price_initial"] == 1.50
    assert not isinstance(d.updates.get("uscita_proposta"), dict)
    assert "uscita_proposta" not in d.telemetry


def test_spento_l_uscita_in_perdita_diventa_proposta():
    """La MECCANICA della proposta (ex test sul green pre-partita), sull'uscita
    che resta governata dall'interruttore: l'uscita in perdita."""
    p = _spento_perdita()
    ctx, _ = _live_covered()
    s = _perdita_ht()
    d = E.decide(ctx, s, p)
    assert d.actions == [], "a mercato non va niente"
    # mai in LIVE_CLOSING senza gli ordini di chiusura, niente motivo di chiusura
    assert d.state == "LIVE_COVERED" and "close_reason" not in d.updates
    prop = d.updates["uscita_proposta"]
    assert prop["chiave"] == "chiusura|c0" and prop["categoria"] == "chiusura"
    assert sorted(o["ruolo"] for o in prop["ordini"]) == ["over_close", "under_close"]
    assert all(o["lato"] == "lay" for o in prop["ordini"])
    assert prop["decided_at"] == s.now and prop["urgente"] is True
    assert prop["close_reason"] == "loss_ht"
    assert d.telemetry["uscita_proposta"]["chiave"] == "chiusura|c0"
    nuove = E.apply_decision(ctx, d, s.now)
    assert nuove == [] and ctx.uscita_proposta["chiave"] == "chiusura|c0"
    # giro dopo: la proposta e' la stessa -> nessun log, istante fermo
    d2 = E.decide(ctx, _perdita_ht(s.now + 3), p)
    assert d2.actions == [] and "uscita_proposta" not in d2.telemetry
    assert d2.updates["uscita_proposta"] is ctx.uscita_proposta


def test_spento_il_cash_out_in_profitto_parte_da_solo():
    """29/09 (P1, M4.1): prima restava fermo e proponeva; ora chiude da solo."""
    ctx, p = _live_covered()
    p["uscite_automatiche"] = False
    d = E.decide(ctx, _cashout_in_profitto(), p)
    assert d.state == "LIVE_CLOSING" and d.updates["close_reason"] == "profit"
    assert sorted(a.role for a in d.actions if a.kind == "place") == ["over_close", "under_close"]
    assert not isinstance(d.updates.get("uscita_proposta"), dict)
    assert d.telemetry["cashout"]["net"] == pytest.approx(1.31, abs=0.05)


def test_spento_la_perdita_a_modello_e_urgente():
    ctx, p = _live_covered()
    p["uscite_automatiche"] = False
    s = snap(KO + 46 * 60, u35=book(2.20, bl=2.24, inplay=True), o45=book(6.0, bl=6.2, inplay=True),
             inplay=True, minute=45, goals=2, ht_active=True)
    d = E.decide(ctx, s, p)
    assert d.actions == [] and d.state == "LIVE_COVERED"
    assert d.updates["uscita_proposta"]["urgente"] is True
    assert d.updates["uscita_proposta"]["close_reason"].startswith("loss")


# ---------------------------------------------------------------------------
# PROTEZIONI: sempre automatiche
# ---------------------------------------------------------------------------
def test_spento_il_cap_perdita_partita_non_chiude_piu():
    """29/09 (P1, M4.5, decisione 18 dell'utente: "toglilo"): prima il cap
    chiudeva da solo anche a interruttore spento; ora non chiude e non propone:
    Mike non chiude mai in perdita da solo."""
    ctx, p = _live_covered()
    p.update(uscite_automatiche=False, event_loss_cap_pct=10.0,
             ht_loss_exit_enabled=False, h2_loss_exit_enabled=False)
    s = snap(KO + 30 * 60, u35=book(3.0, bl=3.1, inplay=True), o45=book(6.0, bl=6.2, inplay=True),
             inplay=True, minute=30, goals=2)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_COVERED" and d.actions == []
    assert d.updates.get("close_reason") != "loss_cap"
    assert not isinstance(d.updates.get("uscita_proposta"), dict)


@pytest.mark.usefixtures("forma_di_prima")
def test_spento_la_copertura_over_45_parte_lo_stesso():
    ctx, p = _live_uncovered()
    p["uscite_automatiche"] = False
    s = snap(KO + 20 * 60, u35=book(1.35, inplay=True), o45=book(9.0, bs=50, inplay=True),
             inplay=True, minute=20, goals=0, hazard=0.05, p4_market=0.12)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_COVER_PENDING"
    assert d.actions[0].role == "over_cover"


def test_spento_una_chiusura_gia_in_corso_si_completa():
    """Il residuo/riprezzo di una chiusura gia' partita non chiede una seconda
    firma: lascerebbe mezza posizione scoperta in attesa di un clic."""
    ctx, p = _live_covered()
    s = _cashout_in_profitto()
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)        # acceso: parte
    assert ctx.state == "LIVE_CLOSING"
    pend = [l for l in ctx.legs if l.status == "pending"]
    fill(pend[0])
    p["uscite_automatiche"] = False                          # spento a meta'
    s2 = snap(s.now + 11, u35=book(1.30, bl=1.32, inplay=True),
              o45=book(12.0, bl=13.0, inplay=True), inplay=True, minute=31, goals=0)
    d = E.decide(ctx, s2, p)
    assert [a.kind for a in d.actions] == ["cancel"] and d.state == "LIVE_CLOSING"


@pytest.mark.parametrize("stato", list(E.STATI_USCITA_IN_CORSO))
def test_uno_stato_di_chiusura_in_corso_basta_da_solo(stato):
    """Anche senza una gamba precedente dello stesso ruolo (es. il residuo
    chiuso su un'altra selezione), in uno stato di chiusura in corso l'uscita
    passa: e' il seguito di un'uscita gia' decisa."""
    ctx = E.MatchCtx(state=stato)
    d = E.Decision(stato, [E.Action(kind="place", role="over_close", market=E.MARKET_OU45,
                                    selection=E.SEL_OVER, side="lay", price=12.5, size=2.0)],
                   "chiusura residuo")
    s = snap(KO + 60, inplay=True, minute=31, goals=0)
    out = E.gate_uscite(ctx, d, s, _spento())
    assert out is d


def test_fuori_da_uno_stato_di_chiusura_la_stessa_decisione_si_propone():
    # 29/09 (P1): il veicolo e' l'uscita IN PERDITA (``loss_2t``); con motivo
    # "profit" l'uscita ora passa da sola (test_spento_il_cash_out_in_profitto_...)
    ctx = E.MatchCtx(state="LIVE_COVERED")
    d = E.Decision("LIVE_CLOSING", [E.Action(kind="place", role="over_close", market=E.MARKET_OU45,
                                             selection=E.SEL_OVER, side="lay", price=12.5,
                                             size=2.0)],
                   "loss", updates={"close_reason": "loss_2t"})
    out = E.gate_uscite(ctx, d, snap(KO + 60, inplay=True, minute=31, goals=0), _spento())
    assert out.actions == [] and out.state == "LIVE_COVERED"


# ---------------------------------------------------------------------------
# APPROVAZIONE
# ---------------------------------------------------------------------------
def test_approvata_passa_esattamente_la_decisione_della_strategia():
    # 29/09 (P1): veicolo = uscita in perdita (il green pre-partita ora parte da solo)
    p = _spento_perdita()
    ctx, s = _proposta_in_perdita(p)
    ctx.uscita_approvata = {"chiave": "chiusura|c0", "at": s.now + 1,
                            "contesto": {"prezzo_visto": 2.24, "eta_ms": 300, "fonte": "canale"}}
    s2 = _perdita_ht(s.now + 2)
    d = E.decide(ctx, s2, p)
    rif = E.decide(ctx, s2, params(ht_loss_goals_min=2))
    assert [(a.role, a.side, a.price, a.size) for a in d.actions] == \
        [(a.role, a.side, a.price, a.size) for a in rif.actions]
    assert sorted(a.role for a in d.actions if a.kind == "place") == ["over_close", "under_close"]
    assert d.state == "LIVE_CLOSING" and d.updates["close_reason"] == "loss_ht"
    assert d.updates["uscita_approvata"] is None and d.updates["uscita_proposta"] is None
    t = d.telemetry["uscita_eseguita_su_approvazione"]
    assert t["chiave"] == "chiusura|c0" and t["contesto"]["fonte"] == "canale"


def test_approvazione_di_un_altra_chiave_non_sblocca_e_si_cancella():
    p = _spento_perdita()
    ctx, s = _proposta_in_perdita(p)
    ctx.uscita_approvata = {"chiave": "ko_green|c0", "at": s.now}
    d = E.decide(ctx, s, p)
    assert d.actions == [] and d.updates["uscita_approvata"] is None


def test_approvazione_scaduta_non_sblocca():
    p = _spento_perdita()
    ctx, s = _proposta_in_perdita(p)
    ctx.uscita_approvata = {"chiave": "chiusura|c0",
                            "at": s.now - E.APPROVAZIONE_TTL_S - 1}
    d = E.decide(ctx, s, p)
    assert d.actions == [] and "uscita_proposta" in d.updates


# ---------------------------------------------------------------------------
# I TIMER DELLA STRATEGIA NON SI FERMANO
# ---------------------------------------------------------------------------
def test_spento_la_finestra_del_fischio_corre_e_l_uscita_parte_da_sola():
    """29/09 (P1, M4.2): prima l'uscita al fischio era una proposta che poi
    decadeva a finestra scaduta; ora la banca al fischio parte da sola anche a
    interruttore spento, l'orologio della finestra corre come sempre e a
    finestra scaduta la strategia la ritira e passa alla copertura."""
    p = dict(PAR_KO, uscite_automatiche=False)
    ctx = ctx_in_uscita(live_since=None)
    ctx.ko_goals = 0
    s1 = snap_ko(KO + 5.0)
    d1 = E.decide(ctx, s1, p)
    assert [a.role for a in d1.actions if a.kind == "place"] == ["ko_green"]
    assert d1.state == "LIVE_KO_GREEN"
    assert d1.updates["live_since"] == KO + 5.0, "l'orologio della finestra parte lo stesso"
    assert not isinstance(d1.updates.get("uscita_proposta"), dict)
    E.apply_decision(ctx, d1, s1.now)
    # finestra scaduta senza gol: la strategia ritira l'uscita e passa alla copertura
    s2 = snap_ko(KO + 5.0 + float(p["ko_green_window_s"]) + 1, minute=20)
    d2 = E.decide(ctx, s2, p)
    assert d2.state == "LIVE_UNCOVERED"
    assert [a.role for a in d2.actions if a.kind == "cancel"] == ["ko_green"]
    assert not isinstance(d2.updates.get("uscita_proposta"), dict)


# ---------------------------------------------------------------------------
# LETTO A CALDO
# ---------------------------------------------------------------------------
def test_riaccendere_a_caldo_esegue_e_fa_decadere_la_proposta():
    # 29/09 (P1): veicolo = uscita in perdita (il green pre-partita parte da solo)
    p_off = _spento_perdita()
    ctx, s = _proposta_in_perdita(p_off)
    assert ctx.uscita_proposta is not None
    p_on = params(ht_loss_goals_min=2, uscite_automatiche=True)
    d = E.decide(ctx, _perdita_ht(s.now + 2), p_on)
    assert sorted(a.role for a in d.actions if a.kind == "place") == ["over_close", "under_close"]
    assert d.updates["uscita_proposta"] is None
    assert "automatiche" in d.telemetry["uscita_proposta_decaduta"]["motivo"]


# ===========================================================================
# IL SERVIZIO INTERO (run_once, paper): interruttore letto a caldo, proposta
# persistita nel contesto della partita, approvazione dalla coda richieste.
# Finti: FakeDB/FakeMarket di test_mike_service (stesse chiavi di mike_*:
# events con ctx/positions, requests con id/kind/payload/status/result).
# ===========================================================================
from datetime import timedelta  # noqa: E402

from Betfair.mike.tests.test_mike_service import (NOW, FakeDB, FakeMarket, legs,  # noqa: E402
                                                  payload, row, run, state)


def _green(db):
    return [l for l in legs(db) if l["role"] == "under_green"]


def _chiusure(db):
    return [l for l in legs(db) if l["role"] in ("under_close", "over_close")]


# 29/09 (P1): la MECCANICA della proposta nel servizio si prova sull'uscita in
# PERDITA (2 gol al 60', regola tollerata del 2T): il green pre-partita ora
# parte da solo. Partita seminata a posizione COPERTA, come `_evento_scoperto`
# di test_mike_service (stesse chiavi di mike_events).
_PAR_PERDITA = {"stake": 10, "uscite_automatiche": False, "ht_loss_goals_min": 2,
                # regola fissa (25 %): il modello del servizio qui direbbe "tengo"
                "loss_exit_mode": "fixed"}


def _evento_coperto():
    ko = (NOW - timedelta(minutes=62)).isoformat()
    gamba = {"market": "OU35", "selection": "UNDER", "side": "back", "price": 1.5, "size": 10.0,
             "matched": 10.0, "avg_price": 1.5, "ref": "under_last-1-1", "status": "open",
             "placed_at": 0.0, "persistence": "PERSIST", "cycle_no": 1, "final": False,
             "archived": False, "role": "under_last"}
    cover = dict(gamba, role="over_cover", market="OU45", selection="OVER", price=8.0, size=2.0,
                 matched=2.0, avg_price=8.0, ref="over_cover-1-2", persistence="LAPSE")
    return {"event_id": "E1", "event_name": "Roma v Lazio", "state": "LIVE_COVERED", "cycle_no": 1,
            "entry_price_initial": 1.5,
            "markets": {"OU35": {"market_id": "1.35"}, "OU45": {"market_id": "1.45"}},
            "positions": [gamba, cover], "dossier": {}, "live": {}, "ctx": {}, "mode": "paper",
            "ko_at": ko}


def _payload_perdita():
    return payload(inplay=True, minute=60, sh=1, sa=1, ko=NOW - timedelta(minutes=62),
                   u35=(2.20, 2.24, 50.0, 50.0), o45=(6.0, 6.2, 50.0, 50.0))


def _servizio_con_proposta_in_perdita():
    db = FakeDB(params=dict(_PAR_PERDITA))
    mk = FakeMarket()
    db.events["E1"] = _evento_coperto()
    run(db, mk, NOW, [row(_payload_perdita())])
    prop = db.events["E1"]["ctx"].get("uscita_proposta")
    assert isinstance(prop, dict) and prop["close_reason"] == "loss_2t", db.kinds()
    return db, mk


def test_servizio_spento_la_green_parte_da_sola_e_nessuna_proposta():
    """29/09 (P1, M1.1): prima a interruttore spento la green non andava a
    mercato e nasceva la proposta; ora la green parte da sola."""
    db = FakeDB(params={"stake": 10, "uscite_automatiche": False})
    mk = FakeMarket()
    run(db, mk, NOW, [row(payload())])
    assert state(db) == "PRE_ENTRY_PENDING"
    run(db, mk, NOW + timedelta(seconds=2), [row(payload())])
    assert state(db) == "PRE_OPEN"
    g = _green(db)
    assert len(g) == 1 and g[0]["price"] == 1.48 and g[0]["status"] == "pending"
    assert "place_resting" in db.kinds() and "uscita_proposta" not in db.kinds()
    assert not isinstance(db.events["E1"]["ctx"].get("uscita_proposta"), dict)


def test_servizio_spento_l_uscita_in_perdita_e_proposta_nel_contesto():
    db, mk = _servizio_con_proposta_in_perdita()
    assert _chiusure(db) == [], "a interruttore spento l'uscita in perdita non va a mercato"
    prop = db.events["E1"]["ctx"]["uscita_proposta"]
    assert prop["chiave"] == "chiusura|c1" and prop["urgente"] is True
    assert db.kinds().count("uscita_proposta") == 1
    # altri giri identici: nessun nuovo log, la proposta resta la stessa
    run(db, mk, NOW + timedelta(seconds=2), [row(_payload_perdita())])
    assert db.kinds().count("uscita_proposta") == 1 and _chiusure(db) == []


def test_servizio_approvazione_dalla_scheda_manda_l_uscita_in_perdita():
    db, mk = _servizio_con_proposta_in_perdita()
    chiave = db.events["E1"]["ctx"]["uscita_proposta"]["chiave"]
    db.requests.append({"id": 7, "kind": "approva_uscita", "status": "pending",
                        "payload": {"event_id": "E1", "chiave": chiave,
                                    "contesto": {"prezzo_visto": 2.24, "eta_ms": 250,
                                                 "fonte": "canale"}}})
    run(db, mk, NOW + timedelta(seconds=2), [row(_payload_perdita())])
    assert db.requests[0]["status"] == "done", db.requests[0]["result"]
    assert sorted(l["role"] for l in _chiusure(db)) == ["over_close", "under_close"]
    assert "uscita_approvata" in db.kinds() and "uscita_eseguita_su_approvazione" in db.kinds()
    assert db.events["E1"]["ctx"]["uscita_proposta"] is None
    assert db.events["E1"]["ctx"]["uscita_approvata"] is None


def test_servizio_approvazione_su_proposta_cambiata_rifiutata():
    db, mk = _servizio_con_proposta_in_perdita()
    db.requests.append({"id": 8, "kind": "approva_uscita", "status": "pending",
                        "payload": {"event_id": "E1", "chiave": "ko_green|c1"}})
    run(db, mk, NOW + timedelta(seconds=2), [row(_payload_perdita())])
    assert db.requests[0]["status"] == "rejected"
    assert db.requests[0]["result"]["code"] == "proposta_cambiata"
    assert _chiusure(db) == []


def test_servizio_riaccendere_a_caldo():
    db, mk = _servizio_con_proposta_in_perdita()
    assert _chiusure(db) == []
    db.control["params"] = {**db.control["params"], "uscite_automatiche": True}
    run(db, mk, NOW + timedelta(seconds=2), [row(_payload_perdita())])
    assert sorted(l["role"] for l in _chiusure(db)) == ["over_close", "under_close"]
    assert "uscita_proposta_decaduta" in db.kinds()
    assert db.events["E1"]["ctx"]["uscita_proposta"] is None


def test_servizio_acceso_parita_col_ciclo_di_sempre():
    """Stesso percorso di test_prematch_cycle_entry_and_green_resting."""
    db = FakeDB(params={"stake": 10, "uscite_automatiche": True})
    mk = FakeMarket()
    run(db, mk, NOW, [row(payload())])
    run(db, mk, NOW + timedelta(seconds=2), [row(payload())])
    g = _green(db)
    assert len(g) == 1 and g[0]["price"] == 1.48 and "place_resting" in db.kinds()
    assert "uscita_proposta" not in db.kinds()
