# -*- coding: utf-8 -*-
"""LA SCHEDA DELLE PROPOSTE AL MS: rivalutazione al prezzo, "decido io",
prezzo visto al clic (24/09/2026).

Ordine dell'utente: "Anomalie, opportunita' del modello e in generale TUTTI gli
avvisi che mi arrivano in live DEVONO aggiornarsi in tempo reale nella scheda.
Adesso se il prezzo cambia il sistema non mi fa piazzare (dice che il prezzo e'
cambiato): io voglio quella scheda aggiornata al ms e decido IO se entrare o no.
[...] La scheda delle proposte deve segnalarmi se l'opportunita', in base ai
calcoli e al prezzo attuale, c'e' ancora o no: io decido se approvare o
scartare."

Cosa certifica questo file, sul codice di produzione:
  1. ``valuta_al_prezzo`` applica ESATTAMENTE i criteri del motore che ha
     generato la proposta: parita' accetta/scarta, edge ed EV con
     ``OpportunityModel._try_side``, ``TennisOpportunityModel._try_side`` e
     ``anomaly._Ctx.emit`` (i veri) su una griglia di prezzi/size/probabilita';
  2. il file d'oro condiviso con la porta TypeScript e' quello che produce il
     Python di oggi (``tools/genera_oro_valuta_proposta.py``);
  3. RIVALUTAZIONE lato servizio: una proposta viva che il motore non propone
     piu' resta VIVA, marcata non piu' valida (causa 'prezzo' coi criteri che
     cadono, o 'modello'), coi numeri al prezzo di adesso; torna valida se il
     motore la ripropone; i numeri della NASCITA non si perdono; write-on-change;
  4. APPROVAZIONE: l'ordine parte AL PREZZO VISTO AL CLIC con la tolleranza
     misurata rispetto a QUEL prezzo (mai rispetto al prezzo della proposta); il
     rifiuto riporta i due prezzi; una proposta marcata non piu' valida si
     approva lo stesso (decide l'utente) ed e' un ordine MANUALE;
  5. PARITA' della strategia automatica: il corpo della proposta, tolti i due
     blocchi nuovi (``criteri``, ``valutazione``), e' identico a quello di
     prima; un giro senza opportunita' non scrive niente nella coda.

I finti hanno le IDENTICHE chiavi del vero (riusati da
``test_proposte_opportunita_2026_09_17.py`` e ``test_combos_anomalie_...``).
ASCII-only nel codice, commenti in italiano.
"""
from __future__ import annotations

import itertools
import json
from datetime import datetime, timedelta, timezone

import pytest

from Betfair.safe_strategy import anomaly as AN
from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import opportunity as OPP
from Betfair.safe_strategy import proposte_opportunita as PO
from Betfair.safe_strategy import tennis_opportunity as TO
from Betfair.safe_strategy.tests.test_proposte_opportunita_2026_09_17 import (
    EV, NOW, DbFinto, _ModuloTennisFinto, _opp, _riga_feed,
)
from Betfair.safe_strategy.tools import genera_oro_valuta_proposta as ORO


# ===========================================================================
# 1. PARITA' COI MOTORI VERI
# ===========================================================================
_PREZZI = (1.01, 1.02, 1.04, 1.08, 1.25, 1.6, 2.4, 4.9, 5.0, 5.2, 7.9, 8.1, 20.0)
_SIZE = (0.0, 9.99, 10.0, 19.99, 20.0, 250.0)
_PROB = (0.0, 0.01, 0.05, 0.1, 0.12, 0.5, 0.89, 0.9, 0.95, 0.96, 0.99, 0.999, 1.0)


def _runner(side, prezzo, size):
    return {"back": prezzo if side == "back" else None,
            "lay": prezzo if side == "lay" else None,
            "back_size": size if side == "back" else None,
            "lay_size": size if side == "lay" else None,
            "name": "Sel", "selection_id": 7, "prob_key": None}


def test_parita_col_motore_calcio_vero():
    """``OpportunityModel._try_side`` (il vero) contro ``valuta_al_prezzo``:
    stessa decisione su ogni combinazione, stessi edge/EV quando propone.
    Confidenza minima 0 e hazard neutro: sono i due ingredienti che NON
    dipendono dal prezzo (dichiarati nel modulo: li giudica il servizio)."""
    motore = OPP.OpportunityModel({"max_prob_lay": 0.15, "min_confidence": 0.0},
                                  calibration="off")
    criteri = PO.criteri_proposta(motore.params, {"opps_min_edge": 0.0}, stake=5.0)
    spec = {"market_type": "OVER_UNDER_25", "market_name": "Over/Under 2.5",
            "line": 2.5, "market_id": "1.5"}
    hazard = {"drop": False, "penalty": 1.0}
    visti = 0
    for side, q, size, p in itertools.product(("back", "lay"), _PREZZI, _SIZE, _PROB):
        o = motore._try_side(side, _runner(side, q, size), p, None, spec, {}, hazard,
                             None, 60, 1, 0)
        v = PO.valuta_al_prezzo(side=side, prezzo=q, abbinabile=size, p_model=p,
                                criteri=criteri)
        assert (o is not None) == v["valida"], (side, q, size, p, v["motivi"])
        if o is not None:
            visti += 1
            assert o.edge == v["edge"] and o.ev == v["ev"], (side, q, size, p)
    assert visti > 5, "la griglia non esercita nessuna proposta valida"


def test_parita_col_motore_tennis_vero():
    motore = TO.TennisOpportunityModel({"min_confidence": 0.0})
    criteri = PO.criteri_proposta(motore.params, {"opps_min_edge": 0.0}, stake=5.0)
    st = TO._State(sets=(1, 0), games=(3, 1), server="p1", points=(None, None), best_of=3)
    visti = 0
    for side, q, size, p in itertools.product(("back", "lay"), _PREZZI, _SIZE, _PROB):
        o = motore._try_side(side, "p1", _runner(side, q, size), p, p, None, {}, st,
                             {"p1": "Uno", "p2": "Due"}, None, 0.0, False)
        v = PO.valuta_al_prezzo(side=side, prezzo=q, abbinabile=size, p_model=p,
                                criteri=criteri)
        assert (o is not None) == v["valida"], (side, q, size, p, v["motivi"])
        if o is not None:
            visti += 1
            assert o.edge == v["edge"] and o.ev == v["ev"], (side, q, size, p)
    assert visti > 5


def test_parita_con_le_anomalie_vere():
    """``anomaly._Ctx.emit`` (il vero, regola 'decided': la P viene dal
    punteggio, nessun limite del modello) contro ``valuta_al_prezzo`` coi
    parametri fusi ESATTAMENTE come ``detect`` (``_parametri_motore_anomalie``)."""
    prm = S._parametri_motore_anomalie(AN, {})
    criteri = PO.criteri_proposta(prm, {"opps_min_edge": 0.0}, stake=2.0)
    visti = 0
    for side, q, size, p in itertools.product(("back", "lay"), _PREZZI, _SIZE, _PROB):
        ctx = AN._Ctx({"minute": 60, "score_home": 1, "score_away": 0}, {}, prm)
        ctx.emit(rule="decided", market_type="OVER_UNDER_25", market_name="O/U 2.5",
                 line=2.5, market_id="1.5", runner=_runner(side, q, size), side=side,
                 p_model=p, p_implied=None, confidence=0.9, gap=0.0, ref="", why="deciso")
        v = PO.valuta_al_prezzo(side=side, prezzo=q, abbinabile=size, p_model=p,
                                criteri=criteri)
        assert bool(ctx.out) == v["valida"], (side, q, size, p, v["motivi"])
        if ctx.out:
            visti += 1
            assert ctx.out[0]["edge"] == v["edge"] and ctx.out[0]["ev"] == v["ev"]
    assert visti > 5


def test_criteri_letti_dai_parametri_effettivi_del_motore():
    """Il pannello cambia una soglia -> i criteri della proposta la seguono: si
    leggono dai parametri del MOTORE, non da numeri ricopiati."""
    motore = OPP.OpportunityModel({"min_edge": 0.07, "commission_pct": 2.0},
                                  calibration="off")
    c = PO.criteri_proposta(motore.params, {"opps_min_edge": 0.04,
                                            "max_liability_per_trade": 30.0}, stake=5)
    assert c["min_edge"] == 0.07 and c["commission"] == pytest.approx(0.02)
    assert c["opps_min_edge"] == 0.04 and c["max_liability_per_trade"] == 30.0
    assert c["stake"] == 5.0
    assert "min_back_price" not in c, "un criterio che il motore non ha non si inventa"


# ===========================================================================
# 2. IL FILE D'ORO CONDIVISO CON LA PORTA TYPESCRIPT
# ===========================================================================
def test_il_file_d_oro_e_quello_del_python_di_oggi():
    salvato = json.loads(ORO.ORO.read_text(encoding="utf-8"))
    assert salvato == json.loads(json.dumps(ORO.calcola())), \
        "valuta_al_prezzo e il file d'oro divergono: rigenerarlo (--scrivi) e ricontrollare il TS"
    codici = {m["codice"] for caso in salvato for m in caso["uscita"]["motivi"]}
    for atteso in ("abbinabile_sotto_minimo", "probabilita_sotto_minimo",
                   "probabilita_sopra_massimo", "quota_sotto_minimo",
                   "quota_sopra_massimo", "edge_sotto_minimo",
                   "edge_sotto_minimo_servizio", "ev_non_positivo",
                   "responsabilita_oltre_tetto", "prezzo_assente",
                   "probabilita_assente", "lato_non_valido"):
        assert atteso in codici, f"il file d'oro non copre {atteso}"
    assert any(c["uscita"]["valida"] for c in salvato)


# ===========================================================================
# 3. RIVALUTAZIONE LATO SERVIZIO
# ===========================================================================
class _TennisVeroNeiParametri:
    """Finto del modello tennis con i PARAMETRI del vero (stesse chiavi):
    ``evaluate`` restituisce le opportunita' scelte dal test."""

    def __init__(self, opps):
        self._opps = list(opps)
        self.params = TO.TennisOpportunityModel({}).params

    def evaluate(self, payload, now_ts):
        return list(self._opps)


def _feed(back_p1=1.30, size=500.0):
    r = _riga_feed()
    r["payload"]["odds"]["p1"]["back"] = back_p1
    r["payload"]["odds"]["p1"]["back_size"] = size
    return r


def _giro(db, opps, riga=None, now=NOW, params=None):
    righe = [riga if riga is not None else _feed()]
    return S.process_opportunities(
        db=db, market=None, rows=righe,
        params={"opps_interval_s": 0.0, "risk": {"model_stake": 5.0},
                "opps_min_edge": 0.03, **(params or {})},
        model=None, opp_mod=None, mode="paper", now=now,
        state={"last_ts": 0.0, "hashes": {}},
        rows_by_event={r["event_id"]: r for r in righe},
        extra={"anomaly": None, "combos": None,
               "tennis": _ModuloTennisFinto(_TennisVeroNeiParametri(opps))},
        scanner_ts=now.timestamp(), scanner_ts_known=True)


def _opp_valida(price=1.30):
    return {**_opp(price=price), "p_model": 0.99, "edge": round(0.99 - 1 / price, 6)}


def test_la_proposta_nasce_con_criteri_e_valutazione_valida():
    db = DbFinto()
    _giro(db, [_opp_valida()])
    c = db.vive()[0]["payload"]
    assert c["criteri"]["min_edge"] == TO.DEFAULT_TENNIS_OPP_PARAMS["min_edge"]
    assert c["criteri"]["opps_min_edge"] == 0.03 and c["criteri"]["stake"] == 5.0
    v = c["valutazione"]
    assert v["valida"] is True and v["causa"] is None and v["motivi"] == []
    assert v["al_prezzo"]["prezzo"] == 1.30 and v["al_prezzo"]["valida"] is True


def test_sparita_col_prezzo_fuori_criterio_resta_viva_causa_prezzo():
    db = DbFinto()
    _giro(db, [_opp_valida()])
    t1 = NOW + timedelta(seconds=10)
    _giro(db, [], riga=_feed(back_p1=1.01), now=t1)
    vive = db.vive()
    assert len(vive) == 1, "la proposta e' stata chiusa d'autorita'"
    v = vive[0]["payload"]["valutazione"]
    assert v["valida"] is False and v["causa"] == "prezzo"
    codici = [m["codice"] for m in v["motivi"]]
    assert "edge_sotto_minimo" in codici and "quota_sotto_minimo" in codici
    assert v["al_prezzo"]["prezzo"] == 1.01
    assert v["valutata_at"] == t1.isoformat() and v["dal"] == t1.isoformat()
    assert "opportunita_decaduta" not in db.kinds()
    att = [p for k, p in db.attivita if k == "opportunita_non_piu_valida"]
    assert att and att[0]["causa"] == "prezzo" and "edge_sotto_minimo" in att[0]["motivi"]


def test_sparita_col_prezzo_ancora_buono_resta_viva_causa_modello():
    db = DbFinto()
    _giro(db, [_opp_valida()])
    _giro(db, [], riga=_feed(back_p1=1.30), now=NOW + timedelta(seconds=10))
    v = db.vive()[0]["payload"]["valutazione"]
    assert v["valida"] is False and v["causa"] == "modello"
    assert v["motivi"][0]["codice"] == "non_piu_proposta_dal_modello"
    assert "modello tennis" in v["motivi"][0]["testo"]


def test_write_on_change_la_proposta_non_valida_non_si_riscrive_a_ogni_giro():
    db = DbFinto()
    _giro(db, [_opp_valida()])
    _giro(db, [], riga=_feed(back_p1=1.01), now=NOW + timedelta(seconds=10))
    prima = json.dumps(db.vive()[0]["payload"], sort_keys=True)
    _giro(db, [], riga=_feed(back_p1=1.01), now=NOW + timedelta(seconds=20))
    assert json.dumps(db.vive()[0]["payload"], sort_keys=True) == prima
    assert db.kinds().count("opportunita_non_piu_valida") == 1
    # il prezzo si muove ancora: la scheda si aggiorna, l'istante 'dal' resta
    _giro(db, [], riga=_feed(back_p1=1.015), now=NOW + timedelta(seconds=30))
    v = db.vive()[0]["payload"]["valutazione"]
    assert v["al_prezzo"]["prezzo"] == 1.015
    assert v["dal"] == (NOW + timedelta(seconds=10)).isoformat()
    assert db.kinds().count("opportunita_non_piu_valida") == 1


def test_torna_valida_e_conserva_i_numeri_della_nascita():
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    nascita = dict(db.vive()[0]["payload"])
    _giro(db, [], riga=_feed(back_p1=1.01), now=NOW + timedelta(seconds=10))
    t2 = NOW + timedelta(seconds=20)
    _giro(db, [_opp_valida(1.25)], riga=_feed(back_p1=1.25), now=t2)
    vive = db.vive()
    assert len(vive) == 1 and vive[0]["id"] == db.richieste[0]["id"]
    c = vive[0]["payload"]
    assert c["valutazione"]["valida"] is True and c["valutazione"]["dal"] == t2.isoformat()
    assert c["price"] == 1.25, "il prezzo del comando e' quello dell'ultima valutazione"
    assert c["price_at_decision"] == nascita["price_at_decision"] == 1.30
    assert c["decided_at"] == nascita["decided_at"]


def test_la_partita_finita_fa_ancora_decadere():
    """I casi GIA' previsti restano come sono: partita non piu' in gioco."""
    db = DbFinto()
    _giro(db, [_opp_valida()])
    fuori = _feed()
    fuori["event_id"] = "altra"
    _giro(db, [], riga=fuori, now=NOW + timedelta(seconds=10))
    assert db.vive() == []
    d = [p for k, p in db.attivita if k == "opportunita_decaduta"]
    assert d and d[0]["motivo"] == "partita non piu' in gioco"


def test_interruttore_spento_fa_ancora_decadere():
    db = DbFinto()
    _giro(db, [_opp_valida()])
    _giro(db, [], params={"proponi_tennis": False}, now=NOW + timedelta(seconds=10))
    assert db.vive() == []
    d = [p for k, p in db.attivita if k == "opportunita_decaduta"]
    assert d and d[0]["motivo"] == "tipo di proposta disattivato dall'interruttore"


# ===========================================================================
# 4. APPROVAZIONE AL PREZZO VISTO AL CLIC
# ===========================================================================
class _Esito:
    def __init__(self, status, price, size):
        self.status, self.price, self.size = status, price, size
        self.fill_note = ""


def _corpo_approvato(db, prezzo_visto, clic=NOW, extra=None):
    corpo = dict(db.vive()[0]["payload"])
    corpo.update({"approved_at": clic.isoformat(), "price_visto": prezzo_visto,
                  "price_visto_at": clic.isoformat(), **(extra or {})})
    return corpo


@pytest.fixture
def esecuzione(monkeypatch):
    chiamate = []

    def finta(**kw):
        chiamate.append(kw)
        return _Esito(status="open", price=kw["row"]["price"], size=kw["row"]["size"])

    monkeypatch.setattr(S, "_execute", finta)
    return chiamate


def test_approvato_al_prezzo_visto_lontano_dalla_proposta_ma_vicino_al_mercato(esecuzione):
    """Proposta nata a 1,30; l'utente guarda la scheda viva e clicca a 1,50;
    all'esecuzione il mercato e' a 1,51 (0,67 %): l'ordine PARTE a 1,50. Col
    vecchio riferimento (la fotografia a 1,30) sarebbe stato un rifiuto
    "prezzo cambiato" del 16 %."""
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    corpo = _corpo_approvato(db, 1.50)
    out = S._request_place(db=db, market=None, rows_by_event={EV: _feed(back_p1=1.51)},
                           payload=corpo, params={"commission_pct": 5.0}, now=NOW,
                           control_mode="paper")
    assert out.get("ok") is True, out
    assert esecuzione[0]["row"]["price"] == 1.50
    t = db.trades[0]
    assert t["origin"] == "manual" and t["strategy"] == "model"
    assert t["price"] == 1.50


def test_rifiuto_prezzo_mosso_fra_clic_ed_esecuzione_riporta_i_due_prezzi(esecuzione):
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    corpo = _corpo_approvato(db, 1.30)
    out = S._request_place(db=db, market=None, rows_by_event={EV: _feed(back_p1=1.36)},
                           payload=corpo, params={"commission_pct": 5.0}, now=NOW,
                           control_mode="paper")
    assert out["error"] == "prezzo_visto_fuori_tolleranza"
    assert out["price_visto"] == 1.30 and out["price_attuale"] == 1.36
    assert out["soglia_pct"] == PO.SLIPPAGE_PCT_DEFAULT
    assert "1.3" in out["message"] and "1.36" in out["message"]
    assert "rifiutato" in out["message"] and db.trades == [] and esecuzione == []
    # il risultato che finisce sulla riga della coda porta lo stesso motivo
    res = S._request_result(out)
    assert res["message"] == out["message"] and S._request_state(out) == "error"


def test_rifiuto_prezzo_sparito_lo_dice():
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    corpo = _corpo_approvato(db, 1.30)
    senza = _feed()
    senza["payload"]["odds"]["p1"]["back"] = None
    out = S._request_place(db=db, market=None, rows_by_event={EV: senza},
                           payload=corpo, params={"commission_pct": 5.0}, now=NOW,
                           control_mode="paper")
    assert out["error"] == "prezzo_visto_sparito" and out["price_visto"] == 1.30
    assert "1.3" in out["message"] and "non c'era piu'" in out["message"]


def test_la_tolleranza_usa_quella_della_scheda(esecuzione):
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    corpo = _corpo_approvato(db, 1.30, extra={"slippage_pct": 5.0})
    out = S._request_place(db=db, market=None, rows_by_event={EV: _feed(back_p1=1.36)},
                           payload=corpo, params={"commission_pct": 5.0}, now=NOW,
                           control_mode="paper")
    assert out.get("ok") is True, out


def test_una_proposta_non_piu_valida_si_approva_lo_stesso_decide_l_utente(esecuzione):
    """La scheda diceva "fuori criterio": l'utente ha firmato comunque. E' un
    ordine MANUALE (origin 'manual', strategy 'model'), al prezzo visto."""
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    _giro(db, [], riga=_feed(back_p1=1.01), now=NOW + timedelta(seconds=10))
    assert db.vive()[0]["payload"]["valutazione"]["valida"] is False
    clic = NOW + timedelta(seconds=12)
    corpo = _corpo_approvato(db, 1.01, clic=clic)
    out = S._request_place(db=db, market=None, rows_by_event={EV: _feed(back_p1=1.01)},
                           payload=corpo, params={"commission_pct": 5.0}, now=clic,
                           control_mode="paper")
    assert out.get("ok") is True, out
    t = db.trades[0]
    assert t["origin"] == "manual" and t["price"] == 1.01 and t["meta"]["da_proposta"]


def test_clic_troppo_vecchio_resta_rifiutato():
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    corpo = _corpo_approvato(db, 1.30, clic=NOW - timedelta(seconds=60))
    out = S._request_place(db=db, market=None, rows_by_event={EV: _feed()},
                           payload=corpo, params={"commission_pct": 5.0}, now=NOW,
                           control_mode="paper")
    assert out["error"] == "clic_troppo_vecchio"


# ===========================================================================
# 5. PARITA' DELLA STRATEGIA AUTOMATICA
# ===========================================================================
def test_parita_il_corpo_tolti_i_blocchi_nuovi_e_quello_di_prima():
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    c = dict(db.vive()[0]["payload"])
    c.pop("criteri")
    c.pop("valutazione")
    atteso = PO.corpo_proposta(
        event_id=EV, event_name=c["event_name"], sport="tennis", kind="tennis",
        opp={**_opp_valida(1.30), "price": 1.30, "selection_id": 11, "side": "back",
             "market_type": "MATCH_ODDS"},
        stake=5.0, liability=5.0, mode="paper", minute=None, score=c["score"],
        now_iso=NOW.isoformat(), decided_at=NOW.isoformat(),
        feed_updated_at=c["feed_updated_at"], odds_ts_ms=None)
    assert c == {**atteso, "opp_key": c["opp_key"]}


def test_parita_un_giro_senza_opportunita_non_scrive_niente():
    db = DbFinto()
    out = _giro(db, [])
    assert out["proposte"] == 0 and db.richieste == [] and db.trades == []
    assert not [k for k in db.kinds() if "opportunita" in k or "proposta" in k]


# ===========================================================================
# 6. (24/09 sera) IL CONTESTO DEL PREZZO VISTO: la scheda non rifiuta piu' il
#    clic; senza prezzo vivo manda l'ULTIMO NOTO col flag. Il servizio decide
#    con la tolleranza, MAI per "assenza" del prezzo vivo a video.
# ===========================================================================
_CTX_ASSENTE = {"eta_ms": 42000, "fonte": "scanner", "prezzo_vivo_assente": True,
                "clic_ms": 1790000000000}


def test_ultimo_noto_col_flag_entro_tolleranza_parte_e_porta_il_contesto(esecuzione):
    """La scheda non aveva un prezzo vivo: ha mandato l'ultimo noto (1,30, di
    42 s prima). Il mercato adesso e' 1,31 (entro il 2 %): l'ordine PARTE al
    prezzo visto, e la riga dice che cosa l'utente ha firmato."""
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    corpo = _corpo_approvato(db, 1.30, extra={"prezzo_visto_ctx": dict(_CTX_ASSENTE)})
    out = S._request_place(db=db, market=None, rows_by_event={EV: _feed(back_p1=1.31)},
                           payload=corpo, params={"commission_pct": 5.0}, now=NOW,
                           control_mode="paper")
    assert out.get("ok") is True, out
    t = db.trades[0]
    assert t["price"] == 1.30 and t["origin"] == "manual"
    assert t["meta"]["prezzo_visto_ctx"] == {"eta_ms": 42000.0, "fonte": "scanner",
                                             "prezzo_vivo_assente": True,
                                             "clic_ms": 1790000000000.0}
    att = [p for k, p in db.attivita if k == "opportunita_piazzata"]
    assert att and att[0]["prezzo_visto_ctx"]["prezzo_vivo_assente"] is True


def test_ultimo_noto_fuori_tolleranza_rifiuto_coi_due_prezzi_e_il_contesto(esecuzione):
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    corpo = _corpo_approvato(db, 1.30, extra={"prezzo_visto_ctx": dict(_CTX_ASSENTE)})
    out = S._request_place(db=db, market=None, rows_by_event={EV: _feed(back_p1=1.40)},
                           payload=corpo, params={"commission_pct": 5.0}, now=NOW,
                           control_mode="paper")
    assert out["error"] == "prezzo_visto_fuori_tolleranza"
    assert out["price_visto"] == 1.30 and out["price_attuale"] == 1.40
    assert out["prezzo_visto_ctx"]["prezzo_vivo_assente"] is True
    assert db.trades == [] and esecuzione == []


def test_senza_contesto_nessun_campo_nuovo(esecuzione):
    """Retrocompatibile: senza la migrazione del 24/09 niente contesto, e la
    riga e l'attivita' restano quelle di ieri."""
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    out = S._request_place(db=db, market=None, rows_by_event={EV: _feed(back_p1=1.31)},
                           payload=_corpo_approvato(db, 1.30),
                           params={"commission_pct": 5.0}, now=NOW, control_mode="paper")
    assert out.get("ok") is True
    assert "prezzo_visto_ctx" not in db.trades[0]["meta"]
    assert "prezzo_visto_ctx" not in [p for k, p in db.attivita if k == "opportunita_piazzata"][0]


def test_contesto_sporco_non_solleva_e_non_inventa():
    assert PO.contesto_prezzo_visto({}) is None
    assert PO.contesto_prezzo_visto({"prezzo_visto_ctx": "x"}) is None
    c = PO.contesto_prezzo_visto({"prezzo_visto_ctx": {
        "eta_ms": float("nan"), "fonte": "inventata", "prezzo_vivo_assente": "si",
        "clic_ms": True}})
    assert c == {"eta_ms": None, "fonte": None, "prezzo_vivo_assente": False, "clic_ms": None}
