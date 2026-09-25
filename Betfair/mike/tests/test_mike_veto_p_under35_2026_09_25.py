"""M1 (25/09) -- veto sulla P CALIBRATA dell'Under 3.5 nel passaggio pre-match -> live.

Interruttore ``veto_p_under35_cal`` DEFAULT ACCESO (ordine dell'utente del
25/09 sera: "per TUTTI i bot i valori statistici e gli aiuti di default accesi").
SPENTO ESPLICITO Mike si comporta ESATTAMENTE come prima (all'ultimo ingresso: in
perdita tiene, in profitto chiude e rientra in PERSIST): i test del ramo spento
passano sempre ``veto_p_under35_cal=False`` per esteso.

I finti parlano come il vero: la riga di ``fixture_predictions.db_json_analisi``
ha le chiavi del motore Poisson (``inputs``, ``markets``, ``markets_calibrated``)
e i nodi Over hanno le chiavi ``{"True": p, "False": 1-p}`` (formato verificato
sul DB il 25/09, MISURA_PUNTO8 sez. 4 Q6). Il ciclo del servizio gira con i
finti di ``test_mike_service`` (stesse porte del DB vero).

Misura e soglie: AUDIT_2026-09-25/MISURA_PUNTO8_2026-09-25.md sez. 4.
File ASCII-only.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from Betfair.mike import config as C
from Betfair.mike import dossier as D
from Betfair.mike import engine as E
from Betfair.mike import feed as F
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_engine import KO, _open_prematch, book, conferma_annulli, fill, snap
from Betfair.mike.tests.test_mike_feed import KO_IN_FINESTRA, payload, row
from Betfair.mike.tests.test_mike_service import FakeDB, FakeMarket, legs, run, state

TELE = "veto_under_calibrata"


def _analisi(p_over35_cal=None, p_over35_raw=0.40):
    """db_json_analisi come lo scrive il motore Poisson (chiavi vere)."""
    an = {
        "inputs": {"lambda_home": 1.45, "lambda_away": 1.10, "dc_rho": -0.11},
        "markets": {
            "1x2": {"1": 0.45, "X": 0.27, "2": 0.28},
            "over_2_5": {"True": 0.52, "False": 0.48},
            "over_3_5": {"True": p_over35_raw, "False": round(1.0 - p_over35_raw, 4)},
        },
    }
    if p_over35_cal is not None:
        an["markets_calibrated"] = {
            "1x2": {"1": 0.44, "X": 0.28, "2": 0.28},
            "over_2_5": {"True": 0.50, "False": 0.50},
            "over_3_5": {"True": p_over35_cal, "False": round(1.0 - p_over35_cal, 4)},
        }
    return an


def _p(**over):
    p = C.merge_params(None)
    p.update(over)
    return p


def _snap_p(now, p_cal, **kw):
    """snapshot dei test engine + la P calibrata (come la mette il servizio)."""
    s = snap(now, **kw)
    return replace(s, p_under35_cal=p_cal)


# ============================================================ whitelist
def test_parametri_nella_whitelist_accesi_di_default():
    assert C.PARAM_SPEC["veto_p_under35_cal"] == (True, bool, None, None, None)
    attese = {"130": 0.807, "150": 0.684, "200": 0.514, "250": 0.385, "300": 0.275}
    for k, v in attese.items():
        assert C.PARAM_SPEC[f"veto_p_under35_soglia_{k}"] == (v, float, 0.0, 1.0, None)
    p = C.merge_params(None)
    assert p["veto_p_under35_cal"] is True
    assert C.merge_params({"veto_p_under35_cal": "off"})["veto_p_under35_cal"] is False
    assert C.merge_params({"veto_p_under35_cal": "on"})["veto_p_under35_cal"] is True
    # il motore: chiave assente = default della whitelist (acceso); non booleano = spento
    assert E.veto_u35_acceso({}) is True
    assert E.veto_u35_acceso({"veto_p_under35_cal": False}) is False
    assert E.veto_u35_acceso({"veto_p_under35_cal": "si"}) is False
    assert C.merge_params({"veto_p_under35_soglia_150": 7})["veto_p_under35_soglia_150"] == 1.0


# ============================================================ soglia
@pytest.mark.parametrize("quota,attesa", [
    (1.30, 0.807), (1.50, 0.684), (2.00, 0.514), (2.50, 0.385), (3.00, 0.275),
    (1.75, (0.684 + 0.514) / 2), (2.25, (0.514 + 0.385) / 2),
    (1.40, 0.807 + (0.684 - 0.807) * 0.5), (2.80, 0.385 + (0.275 - 0.385) * 0.6),
    (1.20, 0.807), (3.40, 0.275),          # fuori banda: nodo di estremita'
])
def test_soglia_interpolata_fra_i_nodi(quota, attesa):
    assert E.soglia_veto_under35(quota, _p()) == pytest.approx(attesa, abs=1e-9)


def test_nodi_del_motore_uguali_ai_default_della_whitelist():
    """I default di ripiego del motore (parametri assenti) sono gli STESSI della
    whitelist: una tabella doppia non deve poter divergere in silenzio."""
    for quota, chiave, default in E.VETO_U35_NODI:
        assert C.PARAM_SPEC[chiave][0] == default, chiave
        assert E.soglia_veto_under35(quota, {}) == pytest.approx(default)


def test_soglia_legge_i_parametri_non_le_costanti():
    p = _p(veto_p_under35_soglia_150=0.70, veto_p_under35_soglia_200=0.50)
    assert E.soglia_veto_under35(1.75, p) == pytest.approx(0.60, abs=1e-9)


# ============================================================ HOLD (in perdita)
def _in_perdita(p_cal, **over):
    ctx, p = _open_prematch()
    p.update(over)
    s = _snap_p(KO - 9 * 60, p_cal, u35=book(1.50, bl=1.52))
    d = E.decide(ctx, s, p)
    return ctx, p, s, d


def test_hold_spento_tiene_come_oggi_anche_con_p_bassissima():
    ctx, p, s, d = _in_perdita(0.10, veto_p_under35_cal=False)
    assert d.state == "HOLD" and [a.kind for a in d.actions] == ["cancel"]
    assert TELE not in d.telemetry and "veto_u35" not in d.updates


def test_hold_acceso_p_sotto_soglia_a_quota_150_chiude():
    ctx, p, s, d = _in_perdita(0.60, veto_p_under35_cal=True)
    # giro 1: la green appoggiata si ANNULLA e basta (mai due lay a mercato)
    assert [a.kind for a in d.actions] == ["cancel"] and d.state == "PRE_OPEN"
    assert TELE not in d.telemetry
    E.apply_decision(ctx, d, s.now)
    conferma_annulli(ctx, d)
    d = E.decide(ctx, s, p)
    assert d.state == "PRE_GREEN_PENDING"
    a = d.actions[-1]
    assert (a.role, a.side, a.final, a.price) == ("under_green", "lay", True, 1.52)
    assert a.note == E.VETO_U35_NOTE
    v = d.telemetry[TELE]
    assert v["esito"] == "veto" and v["eseguito"] is True and v["punto"] == "hold"
    assert v["p_under35_cal"] == 0.60 and v["quota"] == 1.50 and v["soglia"] == pytest.approx(0.684)
    assert d.updates["veto_u35"]["esito"] == "veto"
    # la chiusura si abbina: niente ultimo ingresso PERSIST, si va in gioco senza posizione
    E.apply_decision(ctx, d, s.now)
    fill([l for l in ctx.legs if l.role == "under_green" and l.status == "pending"][-1])
    d2 = E.decide(ctx, _snap_p(KO - 8 * 60, 0.60, u35=book(1.44, bl=1.45)), p)
    assert d2.state == "IDLE_LIVE" and d2.actions == []
    assert "non si rientra dopo il veto" in d2.reason


def test_hold_acceso_p_sopra_soglia_a_quota_150_tiene():
    ctx, p, s, d = _in_perdita(0.70, veto_p_under35_cal=True)
    assert d.state == "HOLD" and [a.kind for a in d.actions] == ["cancel"]
    v = d.telemetry[TELE]
    assert v["esito"] == "nessun_veto" and v["eseguito"] is False
    assert v["soglia"] == pytest.approx(0.684) and v["p_under35_cal"] == 0.70
    assert "veto_u35" not in d.updates


def test_hold_coi_parametri_di_default_il_veto_scatta():
    """25/09 sera: coi parametri di DEFAULT (nessuna chiave toccata) il veto e'
    acceso: P 0,60 a quota 1,50 (soglia 0,684) -> la green si annulla per
    chiudere, non si tiene."""
    ctx, p, s, d = _in_perdita(0.60)
    assert p["veto_p_under35_cal"] is True
    assert [a.kind for a in d.actions] == ["cancel"] and d.state == "PRE_OPEN"


def test_hold_acceso_senza_p_calibrata_tiene_e_lo_dichiara():
    ctx, p, s, d = _in_perdita(None, veto_p_under35_cal=True)
    assert d.state == "HOLD"
    v = d.telemetry[TELE]
    assert v["esito"] == "non_valutabile" and v["soglia"] is None
    assert "assente" in v["motivo"]


# ============================================================ PERSIST (in profitto)
def _open_a(prezzo, p):
    ctx = E.MatchCtx()
    s0 = snap(KO - 0.5 * 3600, u35=book(prezzo))
    E.apply_decision(ctx, E.decide(ctx, s0, p), s0.now)
    fill(ctx.legs[0])
    s1 = snap(KO - 0.5 * 3600 + 5, u35=book(prezzo))
    E.apply_decision(ctx, E.decide(ctx, s1, p), s1.now)
    return ctx


def _fino_al_persist(prezzo_in, prezzo_ora, p_cal, **over):
    """Ingresso a prezzo_in, all'ultimo ingresso il mercato e' sceso a
    prezzo_ora (profitto): chiusura finale abbinata, poi la decisione PERSIST."""
    p = _p(stake=20.0, **over)
    ctx = _open_a(prezzo_in, p)
    s = _snap_p(KO - 9 * 60, p_cal, u35=book(prezzo_ora))
    d = E.decide(ctx, s, p)
    E.apply_decision(ctx, d, s.now)
    conferma_annulli(ctx, d)
    d = E.decide(ctx, s, p)
    assert d.state == "PRE_GREEN_PENDING"
    E.apply_decision(ctx, d, s.now)
    g = [l for l in ctx.legs if l.role == "under_green" and l.status == "pending"][-1]
    # abbinata per l'importo ESATTO che pareggia la posizione (la size chiesta e'
    # arrotondata al centesimo e lascerebbe un residuo: non e' lo scenario qui)
    fill(g, size=20.0 * prezzo_in / g.price)
    return E.decide(ctx, _snap_p(KO - 8 * 60, p_cal, u35=book(prezzo_ora)), p)


def test_persist_spento_rientra_come_oggi():
    d = _fino_al_persist(2.60, 2.50, 0.10, veto_p_under35_cal=False)
    assert d.state == "PRE_LAST_ENTRY_PENDING"
    assert (d.actions[0].role, d.actions[0].persistence, d.actions[0].price) == ("under_last", "PERSIST", 2.50)
    assert TELE not in d.telemetry


def test_persist_acceso_quota_250_p_sotto_soglia_non_rientra():
    d = _fino_al_persist(2.60, 2.50, 0.35, veto_p_under35_cal=True)
    assert d.state == "IDLE_LIVE" and d.actions == []
    v = d.telemetry[TELE]
    assert v["esito"] == "veto" and v["punto"] == "persist" and v["quota"] == 2.50
    assert v["soglia"] == pytest.approx(0.385)
    assert d.updates["veto_u35"]["esito"] == "veto" and d.updates["_archive_legs"] is True


def test_persist_acceso_quota_250_p_sopra_soglia_rientra():
    d = _fino_al_persist(2.60, 2.50, 0.40, veto_p_under35_cal=True)
    assert d.state == "PRE_LAST_ENTRY_PENDING" and d.actions[0].role == "under_last"
    assert d.telemetry[TELE]["esito"] == "nessun_veto"


@pytest.mark.parametrize("p_cal,stato", [(0.71, "IDLE_LIVE"), (0.73, "PRE_LAST_ENTRY_PENDING")])
def test_persist_acceso_quota_144_interpola_fra_130_e_150(p_cal, stato):
    # 1,44: soglia 0,807 + (0,684 - 0,807) * 0,7 = 0,7209
    d = _fino_al_persist(1.50, 1.44, p_cal, veto_p_under35_cal=True)
    assert d.state == stato
    assert d.telemetry[TELE]["soglia"] == pytest.approx(0.7209, abs=1e-4)


def test_persist_acceso_senza_p_calibrata_rientra_e_lo_dichiara():
    d = _fino_al_persist(2.60, 2.50, None, veto_p_under35_cal=True)
    assert d.state == "PRE_LAST_ENTRY_PENDING"
    assert d.telemetry[TELE]["esito"] == "non_valutabile"


# ============================================================ dossier -> snapshot
class _DBDossier:
    def __init__(self, an):
        self.an = an

    def fixture_id_for_event(self, event_id):
        return 1_208_021

    def fixture_lambdas(self, fid):
        return (1.45, 1.10, 135)

    def fixture_analysis(self, fid):
        return self.an


def test_dossier_dichiara_la_fonte_e_il_servizio_passa_solo_la_calibrata():
    cal = D.build_prematch("E1", _DBDossier(_analisi(p_over35_cal=0.40)))
    assert cal["p_under35_cal"] == 0.60 and cal["p_under35_fonte"] == "calibrated"
    assert S._p_under35_calibrata(cal) == 0.60
    grezza = D.build_prematch("E1", _DBDossier(_analisi(p_over35_cal=None, p_over35_raw=0.30)))
    # comportamento di sempre: la grezza finisce comunque in p_under35_cal ...
    assert grezza["p_under35_cal"] == 0.70 and grezza["p_under35_fonte"] == "raw"
    # ... ma il veto non la vede
    assert S._p_under35_calibrata(grezza) is None
    # dossier scritto prima del 25/09 (senza fonte): nessuna P per il veto
    assert S._p_under35_calibrata({"p_under35_cal": 0.6, "source": "fixture"}) is None
    assert S._p_under35_calibrata({}) is None


def test_snapshot_porta_la_p_calibrata():
    info = F.event_info("E1", payload())
    s = F.snapshot_from_row(row(payload()), info, now=KO_IN_FINESTRA.timestamp() - 1800,
                            params=C.merge_params(None), scanner_age_s=1.0, p_under35_cal=0.61)
    assert s is not None and s.p_under35_cal == 0.61
    s0 = F.snapshot_from_row(row(payload()), info, now=KO_IN_FINESTRA.timestamp() - 1800,
                             params=C.merge_params(None), scanner_age_s=1.0)
    assert s0.p_under35_cal is None


# ============================================================ ciclo del servizio
class _FakeDBFixture(FakeDB):
    """FakeDB del servizio con una fixture abbinata e la sua analisi."""

    def __init__(self, an, **kw):
        super().__init__(**kw)
        self.an = an

    def fixture_id_for_event(self, event_id):
        return 1_208_021

    def fixture_lambdas(self, fid):
        return (1.45, 1.10, 135)

    def fixture_analysis(self, fid):
        return self.an


def _giro_ultimo_ingresso(params, p_over35_cal):
    db = _FakeDBFixture(_analisi(p_over35_cal=p_over35_cal), params=params)
    mk = FakeMarket()
    t0 = KO_IN_FINESTRA - timedelta(minutes=30)
    run(db, mk, t0, [row(payload(), updated=t0)])
    t1 = t0 + timedelta(seconds=2)
    run(db, mk, t1, [row(payload(), updated=t1)])
    assert state(db) == "PRE_OPEN"
    assert db.events["E1"]["dossier"]["p_under35_fonte"] == "calibrated"
    perdita = payload(u35=(1.54, 1.55, 30.0, 25.0))
    for k in range(3):
        t = KO_IN_FINESTRA - timedelta(minutes=9) + timedelta(seconds=2 * k)
        db.scanner["updated_at"] = t.isoformat()
        run(db, mk, t, [row(perdita, updated=t)])
    return db


def test_servizio_spento_in_perdita_tiene_come_oggi():
    db = _giro_ultimo_ingresso({"stake": 10, "veto_p_under35_cal": False},
                               p_over35_cal=0.45)     # P Under 0,55
    assert state(db) == "HOLD"
    assert TELE not in db.kinds()
    assert db.events["E1"]["ctx"].get("veto_u35") is None


def test_servizio_acceso_in_perdita_p_sotto_soglia_chiude_e_lo_scrive():
    db = _giro_ultimo_ingresso({"stake": 10, "veto_p_under35_cal": True}, p_over35_cal=0.45)
    # giro 1: annullo della green appoggiata; giro 2: lay finale al best, abbinata
    # in paper; giro 3: nessun ultimo ingresso PERSIST -> in gioco senza posizione
    assert state(db) == "IDLE_LIVE"
    chiusure = [l for l in legs(db) if l["role"] == "under_green" and l["final"]]
    assert chiusure and chiusure[-1]["side"] == "lay" and chiusure[-1]["price"] == 1.55
    assert chiusure[-1]["matched"] > 0
    assert not [l for l in legs(db) if l["role"] == "under_last"]
    righe = [pl for k, pl, _ in db.activity if k == TELE]
    assert len(righe) == 1                       # una volta sola
    v = righe[0]
    # quota 1,54: soglia 0,684 + (0,514 - 0,684) * 0,08 = 0,6704
    assert v["esito"] == "veto" and v["p_under35_cal"] == 0.55
    assert v["soglia"] == pytest.approx(0.6704, abs=1e-4) and v["quota"] == 1.54
    assert db.events["E1"]["ctx"]["veto_u35"]["esito"] == "veto"      # persistito


def test_servizio_acceso_in_perdita_p_sopra_soglia_tiene_e_lo_scrive():
    db = _giro_ultimo_ingresso({"stake": 10, "veto_p_under35_cal": True}, p_over35_cal=0.25)
    assert state(db) == "HOLD"
    righe = [pl for k, pl, _ in db.activity if k == TELE]
    assert len(righe) == 1 and righe[0]["esito"] == "nessun_veto" and righe[0]["p_under35_cal"] == 0.75
