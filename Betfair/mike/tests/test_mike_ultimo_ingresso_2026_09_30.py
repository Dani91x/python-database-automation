"""30/09/2026 - MIKE, L'ULTIMO INGRESSO SI RITENTA FINO AL FISCHIO.

Decisione dell'utente del 30/09 ("Correggi: riprova fino al fischio").
Prima l'ultimo ingresso (segno dei 10 minuti, solo da piatto) si PERDEVA:
  (a) la banca del giro precedente si abbinava nei 60 s prima del segno: la
      pausa dopo un giro chiuso (``pre_reentry_cooldown_s``) faceva fallire il
      controllo al primo giro dopo il segno e Mike passava in HOLD per sempre;
  (b) un controllo momentaneo (libro assente, spread largo, prezzi non vivi,
      prezzo fuori banda, liquidita' al best) falliva al primo giro dopo il
      segno: stessa rinuncia definitiva.
Ora la pausa e i controlli momentanei sono ATTESA (Mike resta in WATCH e
riprova al giro dopo, fino al fischio); rinuncia definitiva (HOLD) solo per i
controlli di sostanza: massimo cicli, tetto di liability della partita, veto
sulla P calibrata dell'Under 3,5, mercato CHIUSO.
Invariato: al piu' UN ingresso dopo il segno (B6), solo da piatto; la banca
resta fino al fischio; mai chiusura in perdita pre-partita.

Finti: classi VERE del motore (``MatchCtx``/``Leg``/``Snapshot``/``Book``),
parametri da ``config.merge_params`` (via ``test_mike_engine.params``), test da
``engine.decide``. Controlli del banco VERI (``certificazione.verifica``).
File ASCII-only.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from Betfair.mike import certificazione as CERT
from Betfair.mike import engine as E
from Betfair.mike.tests.test_mike_engine import DENTRO_FINESTRA, KO, book, fill, params, snap

ULTIMO = KO - 10 * 60            # il segno dei 10 minuti (pre_last_entry_min di serie)


def _p(**over):
    return params(uscite_automatiche=False, stake=20.0, **over)


def _posti(d):
    return [(a.role, a.side, a.price, a.size, a.persistence) for a in d.actions
            if a.kind == "place"]


def _codici(ctx, s, d, p):
    return [v.codice for v in CERT.verifica(ctx, s, d, p)]


def _aperta(p=None, prezzo=1.50):
    """Ingresso 20 @ prezzo abbinato e banca a 2 tick sotto appoggiata."""
    p = p or _p()
    ctx = E.MatchCtx()
    s0 = snap(DENTRO_FINESTRA, u35=book(prezzo))
    E.apply_decision(ctx, E.decide(ctx, s0, p), s0.now)
    fill(ctx.legs[0])
    s1 = snap(DENTRO_FINESTRA + 5, u35=book(prezzo))
    E.apply_decision(ctx, E.decide(ctx, s1, p), s1.now)
    assert ctx.state == "PRE_OPEN" and ctx.legs[-1].role == "under_green"
    return ctx, p


def _banca_abbinata_a(t, p=None):
    """Un giro aperto; la banca si abbina e Mike lo vede all'istante ``t``."""
    ctx, p = _aperta(p)
    fill([l for l in ctx.legs if l.role == "under_green"][-1])
    s = snap(t, u35=book(1.47))
    d = E.decide(ctx, s, p)
    assert d.state == "WATCH" and d.updates.get("last_green_at") == t
    E.apply_decision(ctx, d, s.now)
    return ctx, p


def _piatto_prima_del_segno(p=None):
    return _banca_abbinata_a(ULTIMO - 5 * 60, p)


def _passo(ctx, t, p, u35=None, **kw):
    """Un giro del motore con i controlli del banco B6/D2/D3/B5 muti."""
    s = snap(t, u35=u35 if u35 is not None else book(1.50), **kw)
    d = E.decide(ctx, s, p)
    assert not {"B5", "B6", "D2", "D3"} & set(_codici(ctx, s, d, p)), d.reason
    E.apply_decision(ctx, d, t)
    return d


# ===========================================================================
# (a) la pausa dopo un giro chiuso e' ATTESA, non rinuncia
# ===========================================================================
@pytest.mark.parametrize("visto_a", [ULTIMO - 30,        # abbinata 30 s prima del segno
                                     ULTIMO + 5])        # vista al primo giro dopo il segno
def test_a_banca_abbinata_nella_pausa_prima_del_segno_l_ultimo_ingresso_arriva(visto_a):
    ctx, p = _banca_abbinata_a(visto_a)
    pausa = float(p["pre_reentry_cooldown_s"])
    assert pausa == 60.0
    t = max(ULTIMO, visto_a) + 1
    d = _passo(ctx, t, p)
    assert d.state == "WATCH" and _posti(d) == [], "nella pausa si aspetta"
    assert "cooldown" in d.reason
    d = _passo(ctx, visto_a + pausa - 1, p)
    assert d.state == "WATCH" and _posti(d) == []
    d = _passo(ctx, visto_a + pausa, p)
    assert d.state == "PRE_ENTRY_PENDING", "finita la pausa, l'ultimo ingresso parte"
    assert _posti(d) == [("under_entry", "back", 1.50, 20.0, "LAPSE")]
    fill(ctx.legs[-1])
    d = _passo(ctx, visto_a + pausa + 2, p)
    assert _posti(d) == [("under_green", "lay", pytest.approx(1.48),
                          pytest.approx(20.27, abs=0.01), "LAPSE")]
    for t in (KO - 3 * 60, KO - 60, KO - 5):
        d = _passo(ctx, t, p)
        assert d.state == "HOLD" and _posti(d) == [], "un solo ingresso dopo il segno"


# ===========================================================================
# (b) i controlli momentanei sono ATTESA: si riprova a ogni giro
# ===========================================================================
MOMENTANEI = {
    "spread": dict(u35=book(1.50, bl=1.60)),                   # 10 tick
    "libro_assente": dict(u35=None),
    "prezzi_non_vivi": dict(order_fresh=False),
    "sospeso": dict(u35=book(1.50, status="SUSPENDED")),
    "fuori_banda_sopra": dict(u35=book(3.20)),
    "fuori_banda_sotto": dict(u35=book(1.25)),
    "liquidita": dict(u35=book(1.50, bs=5.0)),
}


def _snap_momentaneo(t, caso):
    kw = dict(MOMENTANEI[caso])
    kw.setdefault("u35", book(1.50))
    if kw["u35"] is None:
        del kw["u35"]
    return snap(t, **kw)


@pytest.mark.parametrize("caso", sorted(MOMENTANEI))
def test_b_controllo_momentaneo_al_segno_si_riprova_al_giro_dopo(caso):
    ctx, p = _piatto_prima_del_segno()
    for t in (ULTIMO + 1, ULTIMO + 21, KO - 5 * 60):
        s = _snap_momentaneo(t, caso)
        d = E.decide(ctx, s, p)
        assert d.state == "WATCH" and d.actions == [], (caso, d.reason)
        assert not {"B6"} & set(_codici(ctx, s, d, p))
        E.apply_decision(ctx, d, t)
    d = _passo(ctx, KO - 4 * 60, p)
    assert d.state == "PRE_ENTRY_PENDING", "tornati i controlli, l'ultimo ingresso parte"
    assert _posti(d) == [("under_entry", "back", 1.50, 20.0, "LAPSE")]


def test_b_si_riprova_fino_al_fischio_poi_niente():
    ctx, p = _piatto_prima_del_segno()
    t = ULTIMO + 1
    while t < KO:
        d = _passo(ctx, t, p, u35=book(1.50, bl=1.60))
        assert d.state == "WATCH" and d.actions == []
        t += 20
    d = _passo(ctx, KO + 30, p, u35=book(1.50, inplay=True), inplay=True, minute=0, goals=0)
    assert d.state == "IDLE_LIVE" and d.actions == []


def test_b_ultimo_ingresso_ritentato_non_abbinato_non_si_rifa():
    """B6 intoccabile: dopo UN ingresso nato dopo il segno, nessun altro, anche
    se non si e' abbinato."""
    ctx, p = _piatto_prima_del_segno()
    _passo(ctx, ULTIMO + 1, p, u35=book(1.50, bl=1.60))       # spread: attesa
    d = _passo(ctx, ULTIMO + 21, p)
    assert d.state == "PRE_ENTRY_PENDING"
    ctx.legs[-1].status = "cancelled"                          # FOK non abbinato
    d = _passo(ctx, ULTIMO + 23, p)
    assert d.state == "WATCH" and d.actions == []
    for t in (ULTIMO + 25, ULTIMO + 60, KO - 60):
        d = _passo(ctx, t, p)
        assert _posti(d) == [] and d.state == "HOLD", "un solo ingresso dopo il segno"


# ===========================================================================
# i controlli di SOSTANZA restano rinuncia definitiva
# ===========================================================================
def test_sostanza_max_cicli_rinuncia_definitiva():
    ctx, p = _piatto_prima_del_segno(_p(pre_max_cycles=1))
    d = _passo(ctx, ULTIMO + 1, p)
    assert d.state == "HOLD" and _posti(d) == [] and "max cicli" in d.reason
    d = _passo(ctx, ULTIMO + 30, p)
    assert d.state == "HOLD" and _posti(d) == []


def test_sostanza_tetto_liability_rinuncia_definitiva():
    ctx, p = _piatto_prima_del_segno()
    p = dict(p, max_liability_per_match=10.0)
    d = _passo(ctx, ULTIMO + 1, p)
    assert d.state == "HOLD" and _posti(d) == [] and "cap liability" in d.reason
    d = _passo(ctx, ULTIMO + 30, dict(p, max_liability_per_match=0.0))
    assert d.state == "HOLD" and _posti(d) == []


def test_sostanza_veto_under35_rinuncia_definitiva():
    ctx, p = _piatto_prima_del_segno(_p(veto_p_under35_cal=True))
    s = replace(snap(ULTIMO + 1, u35=book(1.50)), p_under35_cal=0.50)
    d = E.decide(ctx, s, p)
    assert d.state == "HOLD" and _posti(d) == [] and d.updates["veto_u35"]["esito"] == "veto"
    E.apply_decision(ctx, d, s.now)
    s2 = replace(snap(ULTIMO + 30, u35=book(1.50)), p_under35_cal=0.90)
    d2 = E.decide(ctx, s2, p)
    assert d2.state == "HOLD" and _posti(d2) == []


def test_sostanza_mercato_chiuso_non_si_aspetta():
    """Catalogo par. 7 punto 17: su CHIUSO si cambia strada, non si aspetta."""
    ctx, p = _piatto_prima_del_segno()
    d = _passo(ctx, ULTIMO + 1, p, u35=book(1.50, status="CLOSED"))
    assert d.state == "HOLD" and d.actions == []


def test_con_posizione_al_segno_nessun_ingresso_invariato():
    ctx, p = _aperta()
    d = _passo(ctx, ULTIMO + 1, p)
    assert d.state == "HOLD" and _posti(d) == []


def test_b6_confine_gamba_nata_esattamente_al_segno_conta_come_gia_valutato():
    """Confine della guardia B6: un ingresso nato ESATTAMENTE all'istante del
    segno (placed_at == KO - pre_last_entry_min) e' l'ultimo ingresso: se non si
    abbina, nessun altro ingresso fino al fischio."""
    ctx, p = _piatto_prima_del_segno()
    d = _passo(ctx, ULTIMO, p)
    assert d.state == "PRE_ENTRY_PENDING"
    assert ctx.legs[-1].role == "under_entry" and ctx.legs[-1].placed_at == ULTIMO
    ctx.legs[-1].status = "cancelled"                          # FOK non abbinato
    d = _passo(ctx, ULTIMO + 2, p)
    assert d.state == "WATCH" and d.actions == []
    d = _passo(ctx, ULTIMO + 4, p)
    assert _posti(d) == [] and d.state == "HOLD"
    assert "gia' valutato" in d.reason
