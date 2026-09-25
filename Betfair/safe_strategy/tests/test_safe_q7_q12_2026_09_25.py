# -*- coding: utf-8 -*-
"""Decisioni dell'utente del 25/09 su SAFE, seconda parte: Q7 (selezione
aggiuntiva ESATTO «dove disponibile»), Q8 (mai un ingresso al minuto di uscita
o dopo), Q9 (un solo ingresso per variante e per partita), Q10 (PUNTA con le
bande pre-partita della BASE), Q12 (tennis: quota pre-partita congelata e
«sfavoriti estremi» esclusi).

I FINTI PARLANO COME IL VERO: il ciclo del bot si prova con `run_once` e i
finti di `test_bot_service` (FakeDB con l'indice unico parziale del DB vero,
`traded_signal_keys` con lo stesso filtro); i contesti passano da
`build_*_ctx_from_scan` con le righe di `service.build_rows`; il congelamento
tennis passa da `service.Scanner._apply_market_book`, la funzione di
produzione.

Il file non stampa nulla di non-ASCII (console Windows cp1252).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import db as SD
from Betfair.safe_strategy import engine as E
from Betfair.safe_strategy import scanner as SCAN
from Betfair.safe_strategy.tests.test_bot_service import (
    NOW, FakeDB, FakeEngine, _auto_trade, _run, _signal, _skips,
)
from Betfair.safe_strategy.tests.test_engine import (
    calcio_payload, check, ctx_of, tennis_payload,
)


# ===========================================================================
# Q8 — mai un ingresso AL minuto di uscita o dopo (BASE 80, ESATTO 72, PUNTA 83)
# ===========================================================================
def _segnale_al(minuto, variant="base", key=None):
    s = _signal(variant=variant, key=key or f"1.1:{variant}:1-0")
    s.minute = minuto
    return s


@pytest.mark.parametrize("variant,uscita", [("base", 80), ("esatto", 72), ("punta", 83)])
def test_q8_al_minuto_di_uscita_nessun_ingresso(variant, uscita):
    S._SKIP_LOG_STATE.clear()
    db = FakeDB()
    res = _run(db, engine=FakeEngine([_segnale_al(uscita, variant)]))
    assert res["placed"] == 0 and db.trades == []
    sk = _skips(db, "minuto_ingresso_oltre_uscita")
    assert len(sk) == 1 and sk[0]["minuto"] == uscita and sk[0]["minuto_uscita"] == uscita


@pytest.mark.parametrize("variant,uscita", [("base", 80), ("esatto", 72), ("punta", 83)])
def test_q8_un_minuto_prima_si_entra(variant, uscita):
    S._SKIP_LOG_STATE.clear()
    db = FakeDB()
    res = _run(db, engine=FakeEngine([_segnale_al(uscita - 1, variant)]))
    assert res["placed"] == 1
    assert not _skips(db, "minuto_ingresso_oltre_uscita")


def test_q8_il_minuto_di_uscita_e_quello_dei_parametri_non_un_numero_fisso():
    S._SKIP_LOG_STATE.clear()
    db = FakeDB(params={"exits": {"base_exit_minute": 70}})
    assert _run(db, engine=FakeEngine([_segnale_al(75)]))["placed"] == 0
    assert _skips(db, "minuto_ingresso_oltre_uscita")[0]["minuto_uscita"] == 70


def test_q8_il_tennis_non_ha_minuto_di_uscita():
    S._SKIP_LOG_STATE.clear()
    db = FakeDB()
    s = _signal(variant="tennis", sport="tennis", key="1.1:tennis:set 1-0")
    s.minute = None
    assert S._minuto_oltre_uscita("tennis", None, S._minuti_di_uscita({})) is None
    assert S._minuto_oltre_uscita("base", None, S._minuti_di_uscita({})) is None


# ===========================================================================
# Q9 — UN SOLO ingresso per variante e per partita
# ===========================================================================
def test_q9_nuovo_punteggio_stessa_variante_nessun_secondo_ingresso():
    """BASE gia' presa all'1-0: al 2-0 nasce la chiave `1.1:base:2-0`, nuova
    per l'idempotenza, ma il bot NON rientra."""
    S._SKIP_LOG_STATE.clear()
    db = FakeDB()
    _auto_trade(db, "base", signal_key="1.1:base:1-0")
    res = _run(db, engine=FakeEngine([_signal(key="1.1:base:2-0")]))
    assert res["placed"] == 0
    assert len([t for t in db.trades if t.get("strategy") == "base"]) == 1
    assert _skips(db, "un_solo_ingresso_per_partita")


def test_q9_anche_dopo_la_chiusura_nessun_rientro():
    S._SKIP_LOG_STATE.clear()
    db = FakeDB()
    _auto_trade(db, "base", signal_key="1.1:base:1-0", status="won")
    assert _run(db, engine=FakeEngine([_signal(key="1.1:base:2-1")]))["placed"] == 0


def test_q9_una_riga_in_errore_non_conta_come_ingresso():
    """Stesso filtro dell'idempotenza: un ordine mai partito non e' un ingresso."""
    S._SKIP_LOG_STATE.clear()
    db = FakeDB()
    _auto_trade(db, "base", signal_key="1.1:base:1-0", status="error")
    assert _run(db, engine=FakeEngine([_signal(key="1.1:base:2-0")]))["placed"] == 1


def test_q9_altra_variante_altra_partita_passano():
    S._SKIP_LOG_STATE.clear()
    db = FakeDB()
    _auto_trade(db, "base", signal_key="1.1:base:1-0")
    res = _run(db, engine=FakeEngine([
        _signal(key="1.1:punta:2-0", variant="punta"),         # altra variante
        _signal(key="2.2:base:1-0", event_id="2.2"),            # altra partita
    ]))
    assert res["placed"] >= 1
    chiavi = {t.get("signal_key") for t in db.trades}
    assert "1.1:punta:2-0" in chiavi
    assert not [p for p in _skips(db, "un_solo_ingresso_per_partita")
                if p.get("signal_key") in ("1.1:punta:2-0", "2.2:base:1-0")]


def test_q9_il_prefisso_non_confonde_eventi_con_id_simili():
    assert S._variante_gia_entrata({("1.1", "1.1:base:1-0")}, "1.1", "base")
    assert not S._variante_gia_entrata({("1.10", "1.10:base:1-0")}, "1.1", "base")
    assert not S._variante_gia_entrata({("1.1", "1.1:basex:1-0")}, "1.1", "base")
    assert not S._variante_gia_entrata(set(), "1.1", "base")


def test_q9_la_chiave_di_idempotenza_resta_quella_di_prima():
    """La guardia si AGGIUNGE: la chiave del segnale (e l'indice unico del DB)
    non cambia forma."""
    assert E.signal_key("ev", "base", None, "1-0") == "ev:base:1-0"
    assert E.signal_key("ev", "esatto", "home", "1-0") == "ev:esatto:home:1-0"


# ===========================================================================
# Q10 — PUNTA con le bande pre-partita della BASE
# ===========================================================================
PUNTA = {"minute": 70, "sh": 2, "sa": 0, "fav_back": 1.06, "fav_lay": 1.07}


def _punta(pre, params=None):
    par = params or E.merge_params(None)
    return E.evaluate_football_all(ctx_of(pre_match=pre, **PUNTA), par)[3]


def test_q10_dentro_le_bande_si_entra():
    ev = _punta({"home": 1.65, "draw": 4.0, "away": 5.5})
    assert ev.variant == "punta" and ev.state == "signal"
    assert check(ev, "favPre").ok is True and check(ev, "dogPre").ok is True


@pytest.mark.parametrize("pre,rosso", [
    ({"home": 1.30, "draw": 5.0, "away": 7.5}, "favPre"),     # favorita troppo forte
    ({"home": 1.95, "draw": 3.4, "away": 4.2}, "favPre"),     # favorita troppo debole
    ({"home": 1.45, "draw": 4.5, "away": 8.5}, "dogPre"),     # sfavorita oltre 8
    ({"home": 1.75, "draw": 3.6, "away": 3.9}, "dogPre"),     # sfavorita sotto 4
])
def test_q10_fuori_banda_niente_punta(pre, rosso):
    ev = _punta(pre)
    assert ev.state == "no"
    assert [c.id for c in ev.checks if c.ok is False] == [rosso]


def test_q10_le_bande_sono_quelle_della_base_non_una_copia():
    """Spostando la banda nella sezione BASE si sposta anche per la PUNTA."""
    par = E.merge_params({"base": {"favPreMin": 1.70}})
    ev = _punta({"home": 1.65, "draw": 4.0, "away": 5.5}, par)
    assert check(ev, "favPre").ok is False
    assert "favPreMin" not in E.DEFAULT_PARAMS["punta"]


def test_q10_bordi_inclusi():
    for pre in ({"home": 1.40, "draw": 4.5, "away": 8.0},
                {"home": 1.80, "draw": 3.6, "away": 4.0}):
        assert _punta(pre).state == "signal", pre


def test_q10_senza_riferimento_pre_partita_n_d():
    ev = _punta(None)
    assert ev.state == "nd"
    assert check(ev, "favPre").ok is None


# ===========================================================================
# Q7 — l'ESATTO con la selezione accesa «dove disponibile»
# ===========================================================================
def _esatto(hint):
    p = calcio_payload(minute=49)
    p["selection_hint"] = hint
    ctx = E.build_football_ctx_from_scan("ev1", p, 40, 60)
    return E.evaluate_football_all(ctx, E.merge_params(None))[1]   # lato casa


def test_q7_default_acceso_riga_senza_dato_entra_e_lo_dice():
    ev = _esatto(None)
    assert ev.state == "signal"
    assert check(ev, "h2hDifesa").value == E.SELEZIONE_DATO_ASSENTE


def test_q7_dato_presente_e_cattivo_scarta_con_valore_e_soglia():
    # D5 (25/09): fonte DB, partite da 4+ gol, soglia 0,58 (7/10 = 0,70)
    ev = _esatto({"fonte": "fixture_predictions.raw_json", "h2h_meetings": 10,
                  "h2h_many_goals": 7, "conceded": {"home": 1.0, "away": 1.0}})
    ck = check(ev, "h2hDifesa")
    assert ev.state == "no" and ck.ok is False
    assert f"h2h: 10 partite, 7 con {E.GEQ}4 gol" in ck.value
    assert "58%" in ck.label and "1,37" in ck.label


# ===========================================================================
# Q12 — tennis: quota pre-partita CONGELATA e sfavoriti estremi esclusi
# ===========================================================================
def test_q12_congelamento_stesso_schema_del_calcio():
    odds = {"p1": {"back": 1.50, "lay": 1.52}, "p2": {"back": 2.70, "lay": 2.76}}
    pre = SCAN.freeze_pre_ko_tennis(None, False, odds, adesso_iso="t0")
    assert pre == {"p1": 1.50, "p2": 2.70, "captured_at": "t0"}
    # prima dell'inizio si aggiorna (closing line)
    odds2 = {"p1": {"back": 1.45}, "p2": {"back": 2.90}}
    assert SCAN.freeze_pre_ko_tennis(pre, False, odds2, "t1")["p1"] == 1.45
    # in gioco si CONGELA: le quote live non entrano mai
    assert SCAN.freeze_pre_ko_tennis(pre, True, {"p1": {"back": 1.05},
                                                 "p2": {"back": 12.0}}, "t2") == pre
    # coppia incompleta: resta il riferimento di prima
    assert SCAN.freeze_pre_ko_tennis(pre, False, {"p1": {"back": 1.4}, "p2": {}}) == pre


def test_q12_lo_scanner_di_produzione_lo_congela_e_lo_pubblica():
    """`service.Scanner._apply_market_book` (la funzione vera) scrive
    `pre_ko` anche per il tennis, e `build_rows` lo mette nella riga."""
    from Betfair.safe_strategy import service as SV
    import inspect
    src = inspect.getsource(SV.Scanner._apply_market_book)
    assert "freeze_pre_ko_tennis" in src
    rows_src = inspect.getsource(SV.Scanner.build_rows)
    assert '"pre_ko": ev.get("pre_ko"),' in rows_src.split("p1, p2 = scanner.split_event_name")[1]


def test_q12_reidratazione_riconosce_la_coppia_tennis():
    assert SD.is_usable_pre_ko_tennis({"p1": 1.5, "p2": 2.7})
    assert not SD.is_usable_pre_ko_tennis({"p1": 1.5})
    assert not SD.is_usable_pre_ko_tennis({"p1": 1.0, "p2": 2.7})
    assert not SD.is_usable_pre_ko_tennis({"home": 1.5, "draw": 3.0, "away": 5.0})
    from Betfair.safe_strategy import service as SV
    assert SV._pre_ko_usabile({"sport": "tennis", "pre_ko": {"p1": 1.5, "p2": 2.7}})
    assert not SV._pre_ko_usabile({"sport": "calcio", "pre_ko": {"p1": 1.5, "p2": 2.7}})
    assert SV._pre_ko_usabile({"sport": "calcio",
                               "pre_ko": {"home": 1.5, "draw": 3.0, "away": 5.0}})


class _ScanDbFinto:
    """Il modulo `db` dello scanner, con le STESSE funzioni vere di usabilita'
    (`is_usable_pre_ko`, `is_usable_pre_ko_tennis`) e una lettura in memoria."""

    def __init__(self, salvati):
        self.salvati = dict(salvati)
        self.chiamate = []

    def load_scan_pre_ko(self, event_ids):
        self.chiamate.append(list(event_ids))
        return {e: self.salvati.get(e) for e in event_ids}

    is_usable_pre_ko = staticmethod(SD.is_usable_pre_ko)
    is_usable_pre_ko_tennis = staticmethod(SD.is_usable_pre_ko_tennis)


def _scanner(eventi, salvati, monkeypatch):
    from Betfair.safe_strategy import service as SV
    sc = SV.Scanner.__new__(SV.Scanner)          # niente rete: si costruisce a mano
    sc.dry = False
    sc.events = eventi
    sc.pre_ko_tried = set()
    finto = _ScanDbFinto(salvati)
    monkeypatch.setattr(SV, "scan_db", finto)
    return sc, finto


def test_q12_riavvio_a_partita_iniziata_la_coppia_tennis_si_reidrata(monkeypatch):
    eventi = {"t1": {"sport": "tennis", "inplay": True, "pre_ko": None}}
    sc, finto = _scanner(eventi, {"t1": {"p1": 1.5, "p2": 2.7, "captured_at": "x"}},
                         monkeypatch)
    assert sc.hydrate_pre_ko() == 1
    assert eventi["t1"]["pre_ko"]["p1"] == 1.5 and eventi["t1"]["pre_ko"]["rehydrated"]
    assert finto.chiamate == [["t1"]]


def test_q12_una_tripla_calcio_non_diventa_il_riferimento_di_un_tennis(monkeypatch):
    eventi = {"t1": {"sport": "tennis", "inplay": True, "pre_ko": None}}
    sc, _ = _scanner(eventi, {"t1": {"home": 1.5, "draw": 3.0, "away": 5.0}}, monkeypatch)
    assert sc.hydrate_pre_ko() == 0
    assert eventi["t1"]["pre_ko"] is None


def test_q12_la_lettura_dal_db_tiene_la_coppia_tennis(monkeypatch):
    """`db.load_scan_pre_ko` (la funzione vera) con un client finto che
    risponde come PostgREST (`payload->pre_ko` proiettato come `pre_ko`)."""
    righe = [{"event_id": "t1", "pre_ko": {"p1": 1.5, "p2": 2.7}},
             {"event_id": "c1", "pre_ko": {"home": 1.6, "draw": 3.9, "away": 5.2}},
             {"event_id": "x1", "pre_ko": {"p1": 1.5}}]

    class _Q:
        def select(self, *_a):
            return self

        def in_(self, _col, ids):
            self.ids = list(ids)
            return self

        def execute(self):
            return SimpleNamespace(data=[r for r in righe if r["event_id"] in self.ids])

    class _Client:
        def table(self, _nome):
            return _Q()

    monkeypatch.setattr(SD, "get_supabase_client", lambda: _Client())
    out = SD.load_scan_pre_ko(["t1", "c1", "x1"])
    assert out["t1"] == {"p1": 1.5, "p2": 2.7}
    assert out["c1"]["home"] == 1.6
    assert out["x1"] is None


def _tennis(pre_ko, p1_back=1.05, **kw):
    p = tennis_payload(p1_back=p1_back, **kw)
    if pre_ko is not None:
        p["pre_ko"] = pre_ko
    ctx = E.build_tennis_ctx_from_scan("tv1", p, 60)
    return E.evaluate_tennis(ctx, E.merge_params(None)["tennis"])


def test_q12_leader_favorito_o_poco_sfavorito_si_entra():
    for q in (1.30, 2.50, 4.0):
        ev = _tennis({"p1": q, "p2": 2.0})
        assert ev.state == "signal", q
        assert check(ev, "leaderPre").ok is True


def test_q12_leader_sfavorito_estremo_niente_ingresso():
    # D5 (25/09): si guarda il FAVORITO (p2 a 1,15 < 1,20): il leader p1 e'
    # lo sfavorito estremo
    ev = _tennis({"p1": 5.5, "p2": 1.15})
    ck = check(ev, "leaderPre")
    assert ev.state == "no" and ck.ok is False
    assert ck.value == f"favorito pre-match 1,15 {E.RARR} sfavorito estremo: escluso"
    assert [c.id for c in ev.checks if c.ok is False] == ["leaderPre"]


def test_q12_si_guarda_il_giocatore_che_si_punta_non_l_altro():
    """Leader = p2 (1 set a 0 per p2): conta la quota pre-partita di p2."""
    p = tennis_payload(sets={"p1": 0, "p2": 1}, games={"p1": 0, "p2": 3})
    p["odds"]["p2"] = {"back": 1.05, "lay": 1.06, "selection_id": 2}
    p["odds"]["p1"] = {"back": 15.0, "lay": 16.0, "selection_id": 1}
    # D5 (25/09): super favorito p1 (1,15 < 1,20) -> il leader p2 e' lo
    # sfavorito estremo; a lati scambiati il leader E' il super favorito
    p["pre_ko"] = {"p1": 1.15, "p2": 5.00}
    ev = E.evaluate_tennis(E.build_tennis_ctx_from_scan("tv1", p, 60),
                           E.merge_params(None)["tennis"])
    assert check(ev, "leaderPre").ok is False
    p["pre_ko"] = {"p1": 5.00, "p2": 1.15}
    ev2 = E.evaluate_tennis(E.build_tennis_ctx_from_scan("tv1", p, 60),
                            E.merge_params(None)["tennis"])
    assert check(ev2, "leaderPre").ok is True


def test_q12_dato_pre_partita_assente_non_blocca_e_lo_dichiara():
    for pre in (None, {"p1": 1.5}, {"p1": "x", "p2": 2.0}):
        ev = _tennis(pre)
        assert ev.state == "signal", pre
        assert check(ev, "leaderPre").value == E.TENNIS_PRE_ASSENTE


def test_q12_spento_con_zero():
    par = E.merge_params({"tennis": {"favSuperMax": 0}})["tennis"]
    p = tennis_payload(p1_back=1.05)
    p["pre_ko"] = {"p1": 9.0, "p2": 1.05}
    ev = E.evaluate_tennis(E.build_tennis_ctx_from_scan("tv1", p, 60), par)
    assert ev.state == "signal" and check(ev, "leaderPre") is None


def test_q12_vantaggio_di_game_resta_2_per_tutti():
    """Ordine dell'utente: «il corso dice 2-3 game di vantaggio, lasciamo 2»,
    NON 3 per lo sfavorito."""
    assert E.DEFAULT_PARAMS["tennis"]["gamesLeadMin"] == 2
    ev = _tennis({"p1": 3.5, "p2": 1.3}, games={"p1": 2, "p2": 0})
    assert ev.state == "signal"
