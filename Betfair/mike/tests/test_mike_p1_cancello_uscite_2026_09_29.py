"""29/09/2026 - MIKE, PACCHETTO P1: IL CANCELLO DELLE USCITE.

Specifica: ``PIANO_MODIFICHE_MIKE_2026-09-29.md`` (decisioni dell'utente 12, 13,
16, 18, 23; modifiche M1.1, M4.1-M4.5, M8.1, M8.2).

  * TUTTE le uscite che bloccano un PROFITTO partono da sole, con l'interruttore
    ``uscite_automatiche`` su manuale O su automatico: banca di green del
    pre-partita (``under_green``), banca al fischio (``ko_green``), cash out in
    profitto a soglia (5 %), cash out intelligente, banca di green del rientro
    (``reentry_green``).
  * L'uscita IN PERDITA (intervallo / 46'-85', 3-4 gol) resta una PROPOSTA da
    firmare, urgente: e' l'unica famiglia che l'interruttore governa.
  * M4.5: il tetto di perdita della partita (``event_loss_cap_pct``, ramo
    ``loss_cap``) e' tolto: Mike non chiude mai in perdita da solo.
  * M8.1: ogni uscita in perdita chiede la SUA firma. Difetto riprodotto qui
    sotto: una gamba d'uscita gia' esistente nel ciclo (di un'uscita precedente)
    faceva passare una nuova uscita in perdita SENZA firma
    (``_uscita_gia_in_corso``, regola "stesso ruolo nel ciclo").
  * M8.2: partita chiusa = partita ferma (prova di cio' che c'e' gia').

Finti: ``MatchCtx``/``Leg``/``Snapshot``/``Book``/``Decision`` sono le classi VERE
del motore; i parametri passano da ``config.merge_params``; i test chiamano
``engine.decide`` (il cancello e' la sua ultima parola). File ASCII-only.
"""
from __future__ import annotations

import pytest

from Betfair.mike import engine as E
from Betfair.mike.tests.test_mike_engine import (DENTRO_FINESTRA, KO, _live_covered,
                                                 book, fill, params, snap)
from Betfair.mike.tests.test_mike_ko_green_appoggiata_2026_09_16 import (
    PAR as PAR_KO, ctx_in_uscita, snap as snap_ko)


def _manuale(**over):
    return params(uscite_automatiche=False, **over)


def _posti(d):
    return [(a.role, a.side, a.price, a.size) for a in d.actions if a.kind == "place"]


def _entrata_abbinata(p):
    ctx = E.MatchCtx()
    s0 = snap(DENTRO_FINESTRA, u35=book(1.50))
    E.apply_decision(ctx, E.decide(ctx, s0, p), s0.now)
    fill(ctx.legs[0])
    return ctx, snap(DENTRO_FINESTRA + 5, u35=book(1.50))


def _cashout_in_profitto():
    return snap(KO + 30 * 60, u35=book(1.30, bl=1.31, inplay=True),
                o45=book(12.0, bl=12.5, inplay=True), inplay=True, minute=30, goals=0)


def _perdita_ht():
    """2 gol all'intervallo: uscita in perdita tollerata (test_ht_loss_tolerated_exit)."""
    return snap(KO + 46 * 60, u35=book(2.20, bl=2.24, inplay=True),
                o45=book(6.0, bl=6.2, inplay=True), inplay=True, minute=45, goals=2,
                ht_active=True)


def _stessa_decisione_nelle_due_posizioni(ctx_factory, s, **over):
    """La decisione a interruttore MANUALE e' IDENTICA (ordini, stato) a quella
    in AUTOMATICO: la strategia non cambia, cambia solo chi la esegue."""
    ctx_a, pa = ctx_factory()
    ctx_m, pm = ctx_factory()
    pa.update(uscite_automatiche=True, **over)
    pm.update(uscite_automatiche=False, **over)
    da, dm = E.decide(ctx_a, s, pa), E.decide(ctx_m, s, pm)
    assert _posti(dm) == _posti(da) and _posti(da), "l'uscita in profitto non e' partita"
    assert dm.state == da.state
    assert not isinstance(dm.updates.get("uscita_proposta"), dict), "niente proposta"
    return dm


# ===========================================================================
# M1.1, M4.1-M4.4: le uscite in PROFITTO partono da sole in manuale
# ===========================================================================
def test_m1_1_green_pre_partita_parte_da_sola_in_manuale():
    p = _manuale(pre_exit_mode="resting", stake=20.0)
    ctx, s = _entrata_abbinata(p)
    d = E.decide(ctx, s, p)
    assert _posti(d) == [("under_green", "lay", pytest.approx(1.48), pytest.approx(20.27, abs=0.01))]
    assert d.state == "PRE_OPEN"
    assert not isinstance(d.updates.get("uscita_proposta"), dict)
    assert "uscita_proposta" not in d.telemetry


def test_m1_1_green_taker_pre_partita_parte_da_sola_in_manuale():
    p = _manuale(pre_exit_mode="taker", stake=20.0)
    ctx, _ = _entrata_abbinata(p)
    E.apply_decision(ctx, E.decide(ctx, snap(DENTRO_FINESTRA + 5, u35=book(1.50)), p),
                     DENTRO_FINESTRA + 5)
    d = E.decide(ctx, snap(DENTRO_FINESTRA + 10, u35=book(1.47, bl=1.48)), p)
    assert d.state == "PRE_GREEN_PENDING"
    assert [r for r, *_ in _posti(d)] == ["under_green"]


def test_m4_2_banca_al_fischio_parte_da_sola_in_manuale():
    p = dict(PAR_KO, uscite_automatiche=False)
    ctx = ctx_in_uscita(live_since=None)
    ctx.ko_goals = 0
    d = E.decide(ctx, snap_ko(KO + 5.0), p)
    assert [r for r, *_ in _posti(d)] == ["ko_green"]
    assert d.state == "LIVE_KO_GREEN"
    assert not isinstance(d.updates.get("uscita_proposta"), dict)


def test_m4_1_cash_out_in_profitto_parte_da_solo_in_manuale():
    d = _stessa_decisione_nelle_due_posizioni(_live_covered, _cashout_in_profitto())
    assert d.state == "LIVE_CLOSING" and d.updates["close_reason"] == "profit"
    assert sorted(r for r, *_ in _posti(d)) == ["over_close", "under_close"]


def test_m4_3_cash_out_intelligente_parte_da_solo_in_manuale():
    s = snap(KO + 30 * 60, u35=book(1.32, bl=1.33, inplay=True),
             o45=book(12.0, bl=12.5, inplay=True), inplay=True, minute=30, goals=0, hazard=0.12)
    d = _stessa_decisione_nelle_due_posizioni(_live_covered, s)
    assert d.reason.startswith("profit smart") and d.updates["close_reason"] == "profit"


def _reentry_abbinato():
    p = params()
    ctx = E.MatchCtx(state="REENTRY_PENDING", entry_price_initial=1.50, reentry_allowed=True)
    ctx.legs.append(fill(E.Leg(role="reentry", market=E.MARKET_OU45, selection=E.SEL_UNDER,
                               side="back", price=1.60, size=10.0, ref="reentry-0-1")))
    return ctx, p


def test_m4_4_green_del_rientro_parte_da_sola_in_manuale():
    s = snap(KO + 30 * 60, u35=book(2.5, inplay=True), o45=book(5.0, inplay=True),
             u45=book(1.60, bs=50, inplay=True), inplay=True, minute=30, goals=1)
    d = _stessa_decisione_nelle_due_posizioni(_reentry_abbinato, s)
    assert d.state == "REENTRY_OPEN" and [r for r, *_ in _posti(d)] == ["reentry_green"]


def test_uscita_in_profitto_fa_decadere_una_proposta_in_perdita_rimasta_viva():
    """Il bot e' informato di ogni stato: la proposta in perdita che non regge
    piu' (la strategia adesso chiude in profitto) sparisce, con la sua firma."""
    ctx, p = _live_covered()
    p["uscite_automatiche"] = False
    d1 = E.decide(ctx, _perdita_ht(), p)
    E.apply_decision(ctx, d1, KO + 46 * 60)
    assert ctx.uscita_proposta["close_reason"].startswith("loss")
    d2 = E.decide(ctx, _cashout_in_profitto(), p)
    assert d2.state == "LIVE_CLOSING" and sorted(r for r, *_ in _posti(d2)) == \
        ["over_close", "under_close"]
    assert d2.updates["uscita_proposta"] is None
    assert d2.telemetry["uscita_proposta_decaduta"]["chiave"] == "chiusura|c0"


# ===========================================================================
# L'uscita in PERDITA resta una proposta da firmare (decisione 16)
# ===========================================================================
def test_uscita_in_perdita_resta_proposta_urgente_in_manuale():
    ctx, p = _live_covered()
    p["uscite_automatiche"] = False
    d = E.decide(ctx, _perdita_ht(), p)
    assert _posti(d) == [] and d.state == "LIVE_COVERED"
    prop = d.updates["uscita_proposta"]
    assert prop["close_reason"] == "loss_ht" and prop["urgente"] is True
    assert prop["chiave"] == "chiusura|c0"


def test_uscita_in_perdita_firmata_parte():
    ctx, p = _live_covered()
    p["uscite_automatiche"] = False
    s = _perdita_ht()
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    ctx.uscita_approvata = {"chiave": ctx.uscita_proposta["chiave"], "at": s.now + 1}
    d = E.decide(ctx, snap(s.now + 2, u35=book(2.20, bl=2.24, inplay=True),
                           o45=book(6.0, bl=6.2, inplay=True), inplay=True, minute=45,
                           goals=2, ht_active=True), p)
    assert d.state == "LIVE_CLOSING" and d.updates["close_reason"] == "loss_ht"
    assert d.updates["uscita_approvata"] is None and d.updates["uscita_proposta"] is None
    assert "uscita_eseguita_su_approvazione" in d.telemetry


def test_chiusura_del_veto_pre_partita_non_parte_mai():
    """La chiusura del veto sull'Under 3,5 (a 10' dal fischio, in perdita) era
    un'uscita IN PERDITA: in P1 restava una proposta; dal pacchetto P2 (M2.2)
    non esiste piu' (nel pre-partita Mike non chiude mai in perdita)."""
    from dataclasses import replace
    from Betfair.mike.tests.test_mike_engine import _open_prematch
    ctx, p = _open_prematch()
    p.update(uscite_automatiche=False, veto_p_under35_cal=True)
    s = replace(snap(KO - 9 * 60, u35=book(1.50, bl=1.52)), p_under35_cal=0.60)
    for _ in range(2):
        d = E.decide(ctx, s, p)
        assert _posti(d) == [] and d.actions == [], "chiusura in perdita nel pre-partita"
        assert not isinstance(d.updates.get("uscita_proposta"), dict)
        assert not {"G2", "G3"} & set(_codici(ctx, s, d, p))
        E.apply_decision(ctx, d, s.now)


def test_chiusura_a_tempo_del_rientro_resta_governata():
    """``reentry_time`` (spenta di serie: ``reentry_exit_until_min`` 0) chiude al
    mercato a un minuto fisso e PUO' chiudere in perdita: resta una proposta."""
    p = _manuale(reentry_exit_until_min=80)
    ctx = E.MatchCtx(state="REENTRY_OPEN", entry_price_initial=1.50, reentry_allowed=True)
    ctx.legs.append(fill(E.Leg(role="reentry", market=E.MARKET_OU45, selection=E.SEL_UNDER,
                               side="back", price=1.60, size=10.0)))
    s = snap(KO + 81 * 60, u45=book(1.70, bl=1.72, inplay=True), inplay=True, minute=81, goals=1)
    d = E.decide(ctx, s, p)
    assert _posti(d) == []
    assert d.updates["uscita_proposta"]["close_reason"] == "reentry_time"


# ===========================================================================
# M4.5: il tetto di perdita della partita e' tolto
# ===========================================================================
@pytest.mark.parametrize("automatiche", [True, False])
def test_m4_5_nessun_tetto_di_perdita_mike_non_chiude_in_perdita_da_solo(automatiche):
    ctx, p = _live_covered()
    p.update(uscite_automatiche=automatiche, event_loss_cap_pct=10.0,
             ht_loss_exit_enabled=False, h2_loss_exit_enabled=False)
    s = snap(KO + 30 * 60, u35=book(3.0, bl=3.1, inplay=True), o45=book(6.0, bl=6.2, inplay=True),
             inplay=True, minute=30, goals=2)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_COVERED" and _posti(d) == []
    assert d.updates.get("close_reason") != "loss_cap"
    assert not isinstance(d.updates.get("uscita_proposta"), dict)


# ===========================================================================
# M8.1: ogni uscita in perdita chiede la SUA firma
# ===========================================================================
def _chiusura_precedente(ctx):
    """Una gamba di chiusura dello stesso ciclo, gia' abbinata: e' il resto di
    un'uscita PRECEDENTE (in profitto partita da sola, o in perdita firmata)."""
    ctx.legs.append(fill(E.Leg(role="under_close", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                               side="lay", price=1.40, size=5.0, ref="under_close-0-9",
                               cycle_no=0)))
    return ctx


def test_m8_1_una_gamba_di_un_uscita_precedente_non_autorizza_un_uscita_in_perdita():
    """DIFETTO D1 riprodotto: prima di P1 questa uscita IN PERDITA partiva
    senza firma perche' nel ciclo esisteva gia' una ``under_close``."""
    ctx_a, pa = _live_covered()
    _chiusura_precedente(ctx_a)
    da = E.decide(ctx_a, _perdita_ht(), pa)          # automatico: la strategia chiude
    assert da.state == "LIVE_CLOSING" and str(da.updates["close_reason"]).startswith("loss")
    ctx, p = _live_covered()
    _chiusura_precedente(ctx)
    p["uscite_automatiche"] = False
    d = E.decide(ctx, _perdita_ht(), p)
    assert _posti(d) == [], "uscita IN PERDITA partita senza la sua firma"
    assert d.state == "LIVE_COVERED"
    assert d.updates["uscita_proposta"]["close_reason"].startswith("loss")


def test_m8_1_la_firma_usata_non_vale_per_la_seconda_uscita_in_perdita():
    ctx, p = _live_covered()
    p["uscite_automatiche"] = False
    s = _perdita_ht()
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    ctx.uscita_approvata = {"chiave": ctx.uscita_proposta["chiave"], "at": s.now + 1}
    d1 = E.decide(ctx, s, p)
    assert d1.state == "LIVE_CLOSING"
    E.apply_decision(ctx, d1, s.now)                 # firma consumata
    assert ctx.uscita_approvata is None
    # la chiusura si abbina in parte, poi la partita torna a posizione coperta
    for l in ctx.legs:
        if l.status == "pending":
            fill(l, size=round(l.size / 2.0, 2))
    ctx.state = "LIVE_COVERED"
    s2 = snap(KO + 60 * 60, u35=book(2.20, bl=2.24, inplay=True),
              o45=book(6.0, bl=6.2, inplay=True), inplay=True, minute=60, goals=2)
    pa = dict(p, uscite_automatiche=True)
    import copy
    da = E.decide(copy.deepcopy(ctx), s2, pa)
    assert da.state == "LIVE_CLOSING" and str(da.updates["close_reason"]).startswith("loss")
    d2 = E.decide(ctx, s2, p)
    assert _posti(d2) == [], "seconda uscita in perdita partita con la firma della prima"
    assert d2.updates["uscita_proposta"]["close_reason"] == "loss_2t"


def test_m8_1_seguito_di_un_uscita_in_perdita_firmata_non_chiede_altre_firme():
    """Il riprezzo/residuo di un'uscita firmata e' la STESSA uscita: parte
    (stato di chiusura in corso), altrimenti mezza posizione resterebbe
    scoperta in attesa di un clic."""
    ctx, p = _live_covered()
    p["uscite_automatiche"] = False
    ctx.state = "LIVE_CLOSING"
    ctx.close_reason = "loss_ht"
    d = E.Decision("LIVE_CLOSING", [E.Action(kind="place", role="under_close",
                                             market=E.MARKET_OU35, selection=E.SEL_UNDER,
                                             side="lay", price=2.24, size=5.0)],
                   "chiusura residuo", {"attempts": 1})
    out = E.gate_uscite(ctx, d, _perdita_ht(), p)
    assert out is d


# ===========================================================================
# M8.2: una partita chiusa e' chiusa (prova di cio' che c'e' gia')
# ===========================================================================
def _flat_dopo(close_reason, **ctx_over):
    ctx = E.MatchCtx(state="FLAT", entry_price_initial=1.50, close_reason=close_reason,
                     reentry_allowed=(close_reason == "profit"), **ctx_over)
    ctx.legs.append(fill(E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                               side="back", price=1.50, size=10.0)))
    ctx.legs.append(fill(E.Leg(role="under_close", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                               side="lay", price=1.60, size=9.38)))
    return ctx


def _occasione_di_rientro():
    return snap(KO + 30 * 60, u35=book(2.5, inplay=True), o45=book(5.0, inplay=True),
                u45=book(1.70, bs=50, inplay=True), inplay=True, minute=30, goals=1)


@pytest.mark.parametrize("automatiche", [True, False])
def test_m8_2_chiusa_dal_bot_in_perdita_nessun_ordine_dopo(automatiche):
    ctx = _flat_dopo("loss_ht")
    d = E.decide(ctx, _occasione_di_rientro(), params(uscite_automatiche=automatiche))
    assert d.state == "FLAT" and d.actions == []


@pytest.mark.parametrize("automatiche", [True, False])
def test_m8_2_chiusa_dall_utente_nell_app_nessun_ordine_dopo(automatiche):
    ctx = _flat_dopo("profit", no_reentry=True)
    d = E.decide(ctx, _occasione_di_rientro(), params(uscite_automatiche=automatiche))
    assert d.state == "FLAT" and d.actions == []


@pytest.mark.parametrize("automatiche", [True, False])
def test_m8_2_chiusa_fuori_dall_app_nessun_ordine_dopo(automatiche):
    ctx, _ = _live_covered()
    ctx.chiuso_dall_utente = True
    for s in (_cashout_in_profitto(), _perdita_ht()):
        d = E.decide(ctx, s, params(uscite_automatiche=automatiche))
        assert d.actions == [] and d.state == ctx.state


def test_m8_2_dopo_una_chiusura_in_profitto_il_rientro_resta_la_strategia():
    """NON e' un cambio: il rientro dopo una chiusura in profitto e' la strategia
    (piano, punto 6). Solo chiusure in perdita o dell'utente fermano la partita."""
    ctx = _flat_dopo("profit")
    d = E.decide(ctx, _occasione_di_rientro(), params(uscite_automatiche=False))
    assert d.state == "REENTRY_PENDING" and [r for r, *_ in _posti(d)] == ["reentry"]


def test_chiusura_manuale_non_aggiunge_una_lay_a_una_banca_a_esito_ignoto():
    """Reperto del replay P1 (scenario cashout-globale, J5): la banca
    pre-partita ora e' a mercato anche in manuale; se il suo annullamento non e'
    confermato (esito ignoto) la chiusura manuale non aggiunge una seconda lay
    sulla stessa selezione: aspetta l'esito, poi chiude la posizione vera."""
    ctx = E.MatchCtx(state="PRE_OPEN", flatten_pending=True)
    ctx.legs.append(fill(E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                               side="back", price=1.50, size=10.0, ref="under_entry-0-1")))
    green = E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                  price=1.48, size=10.14, ref="under_green-0-2", status=E.STATUS_RECONCILE)
    ctx.legs.append(green)
    s = snap(DENTRO_FINESTRA, u35=book(1.50, bl=1.52))
    d = E.decide(ctx, s, params(uscite_automatiche=False))
    assert _posti(d) == [], "seconda lay sulla stessa selezione con la banca a esito ignoto"
    assert "under_green-0-2" in d.reason
    green.status = "cancelled"                       # riconciliata: mai abbinata
    d2 = E.decide(ctx, s, params(uscite_automatiche=False))
    assert [r for r, *_ in _posti(d2)] == ["manual_close"]


# ===========================================================================
# IL BANCO: i controlli G2 e G3 (certificazione di Mike)
# ===========================================================================
from Betfair.mike import certificazione as CERT  # noqa: E402


def _codici(ctx, s, d, p):
    return [v.codice for v in CERT.verifica(ctx, s, d, p)]


def test_banco_g2_g3_tacciono_sul_motore_vero():
    ctx, p = _live_covered()
    p["uscite_automatiche"] = False
    for s in (_perdita_ht(), _cashout_in_profitto()):
        d = E.decide(ctx, s, p)
        assert not {"G2", "G3"} & set(_codici(ctx, s, d, p)), d.reason


def test_banco_g2_vede_un_uscita_in_perdita_senza_firma():
    """FALSIFICAZIONE del controllo: la decisione del motore AUTOMATICO (uscita
    in perdita eseguita) giudicata con l'interruttore su manuale e senza firma."""
    ctx, pa = _live_covered()
    d = E.decide(ctx, _perdita_ht(), pa)
    assert _posti(d)
    pm = dict(pa, uscite_automatiche=False)
    assert "G2" in _codici(ctx, _perdita_ht(), d, pm)
    assert "G2" not in _codici(ctx, _perdita_ht(), d, pa)
    # con la SUA firma sulla SUA proposta: tace
    ctx.uscita_proposta = {"chiave": "chiusura|c0", "close_reason": d.updates["close_reason"]}
    # 30/09 (ondata 2 del banco): la firma vale se NON e' scaduta
    # (``APPROVAZIONE_TTL_S``, la stessa regola del cancello). Prima qui c'era
    # ``at: KO``, una firma di 46 minuti prima che il motore rifiuterebbe.
    ctx.uscita_approvata = {"chiave": "chiusura|c0", "at": _perdita_ht().now - 5.0}
    assert "G2" not in _codici(ctx, _perdita_ht(), d, pm)
    # firma su un'altra uscita in perdita: parla
    ctx.uscita_proposta = {"chiave": "chiusura|c0", "close_reason": "loss_2t"}
    assert "G2" in _codici(ctx, _perdita_ht(), d, pm)


def test_banco_g2_vede_il_tetto_di_perdita_in_ogni_posizione():
    ctx, pa = _live_covered()
    d = E.Decision("LIVE_CLOSING", [E.Action(kind="place", role="under_close",
                                             market=E.MARKET_OU35, selection=E.SEL_UNDER,
                                             side="lay", price=3.1, size=5.0)],
                   "cap perdita evento: -3.00", {"close_reason": "loss_cap"})
    assert "G2" in _codici(ctx, _perdita_ht(), d, pa)


def test_banco_g3_vede_un_uscita_in_profitto_lasciata_proposta():
    ctx, p = _live_covered()
    p["uscite_automatiche"] = False
    d = E.Decision("LIVE_COVERED", [], "uscita proposta all'utente (uscite manuali): profit",
                   {"uscita_proposta": {"chiave": "chiusura|c0", "categoria": "chiusura",
                                        "close_reason": "profit", "motivo": "profit: 1.31"}})
    assert "G3" in _codici(ctx, _cashout_in_profitto(), d, p)
    d.updates["uscita_proposta"]["close_reason"] = "loss_ht"
    assert "G3" not in _codici(ctx, _cashout_in_profitto(), d, p)
