# -*- coding: utf-8 -*-
"""Safe BASE SOLO NEL SECONDO TEMPO (decisione dell'utente, 07/10/2026 sera).

Testuale: "SAFE BASE SEMPRE E SOLO SECONDO TEMPO". Stessa regola dell'ESATTO
(`test_esatto_secondo_tempo_2026_10_07.py`): fase = 2o tempo dallo stato IPS
(``score_raw``) E minuto >= soglia di sempre (55). Il caso: all'INTERVALLO il
feed tiene 'FirstHalfEnd' ma il minuto continua a contare (misura del 25/09 in
`atlante_v4`: 35674515, 45 -> 56 in 13'); sulla 35797769 lo stato vero
dell'intervallo e' 'FirstHalfEnd' con timeElapsed 45-50 ed elapsedRegularTime
45. Con il minuto a 55-56 la BASE "dal 55'" poteva entrare a partita ferma.

Finti: `test_engine.calcio_payload` (riga dello scanner) con ``score_raw`` dalla
forma vera (`stato_ips_calcio`, chiavi e tipi della registrazione 35797769).
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pytest

from Betfair.safe_strategy import certificazione as CERT
from Betfair.safe_strategy import engine as eng
from Betfair.safe_strategy.tests.test_engine import calcio_payload, stato_ips_calcio

_BASE = eng.DEFAULT_PARAMS["base"]


def _stato(match_status: str, minute: int, regular: int,
           added: Optional[int]) -> Dict[str, Any]:
    """Stato IPS con la forma vera; ``regular``/``added`` come nel feed."""
    st = stato_ips_calcio(match_status, minute, 1, 0)
    st["elapsedRegularTime"] = regular
    st.pop("elapsedAddedTime", None)
    if added is not None:
        st["elapsedAddedTime"] = added
    # stesso ordine di chiavi del vero (added prima di fullTimeElapsed)
    coda = {k: st.pop(k) for k in ("fullTimeElapsed", "status", "matchStatus")}
    st.update(coda)
    return st


# intervallo col minuto che continua a contare (35797769 20:05:56 ha
# 'FirstHalfEnd' 45/45 senza added: stessa forma, minuto 55)
INTERVALLO_55 = _stato("FirstHalfEnd", 55, 45, None)
RECUPERO_1T_55 = _stato("KickOff", 55, 45, 10)
SECONDO_TEMPO_55 = _stato("SecondHalfKickOff", 55, 55, None)


def _payload(stato: Optional[Dict[str, Any]], minute: int = 55) -> Dict[str, Any]:
    """1-0 della favorita (pre 1,65 / 5,5), banca sfavorita 25 (dentro 20-34):
    BASE pronta su ogni altro check."""
    p = calcio_payload(minute=minute, sh=1, sa=0, match_status=None)
    if stato is not None:
        p["score_raw"] = stato
    return p


def _base(stato: Optional[Dict[str, Any]], minute: int = 55) -> eng.VariantEvaluation:
    ctx = eng.build_football_ctx_from_scan("35797769", _payload(stato, minute), 50, 120)
    return eng.evaluate_base(ctx, _BASE)


def _check(ev, cid):
    return next((c for c in ev.checks if c.id == cid), None)


def test_intervallo_al_55_non_entra():
    """Il caso del reperto: 'FirstHalfEnd' col minuto 55. Prima: SEGNALE."""
    ev = _base(INTERVALLO_55, 55)
    assert ev.state == "no", [(c.id, c.value, c.ok) for c in ev.checks]
    ck = _check(ev, "secondHalf")
    assert ck.ok is False and ck.value == "intervallo (FirstHalfEnd)"


def test_intervallo_al_56_non_entra():
    assert _base(_stato("FirstHalfEnd", 56, 45, None), 56).state == "no"


def test_recupero_del_primo_tempo_al_55_non_entra():
    ev = _base(RECUPERO_1T_55, 55)
    assert ev.state == "no"
    assert _check(ev, "secondHalf").value.startswith("recupero del 1")


def test_secondo_tempo_al_55_entra_come_prima():
    ev = _base(SECONDO_TEMPO_55, 55)
    assert ev.state == "signal", [(c.id, c.value, c.ok) for c in ev.checks]
    assert _check(ev, "secondHalf").ok is True
    assert ev.market_type == "MATCH_ODDS" and ev.side == "LAY" and ev.entry_odds == 25


def test_soglia_del_minuto_invariata():
    assert _BASE["minuteMin"] == 55
    ev = _base(_stato("SecondHalfKickOff", 54, 54, None), 54)
    assert ev.state == "no" and _check(ev, "minute").ok is False


@pytest.mark.parametrize("minute", [55, 70, 92])
def test_stato_ips_assente_fail_closed(minute):
    ev = _base(None, minute)
    assert ev.state == "nd"
    assert _check(ev, "secondHalf").value == eng.SECONDO_TEMPO_STATO_ASSENTE
    assert ev.headline is None


def test_check_subito_dopo_il_minuto():
    ids = [c.id for c in _base(SECONDO_TEMPO_55, 55).checks]
    assert ids.index("secondHalf") == ids.index("minute") + 1


def test_la_punta_non_cambia():
    ctx = eng.build_football_ctx_from_scan("35797769", _payload(INTERVALLO_55, 70), 50, 120)
    ev = eng.evaluate_punta(ctx, eng.DEFAULT_PARAMS["punta"], _BASE)
    assert _check(ev, "secondHalf") is None


# ---------------------------------------------------------------------------
# motore intero, attivita', controllo di condotta B18
# ---------------------------------------------------------------------------
def _segnali_base(stato, minute):
    t = {"now": 1_000_000.0}
    se = eng.SafeEngine(clock=lambda: t["now"])
    riga = {"event_id": "35797769", "sport": "calcio", "payload": _payload(stato, minute)}
    se.evaluate([riga])
    t["now"] += 120.0
    return [s for s in se.evaluate([riga]) if ":base:" in str(getattr(s, "key", s))]


def test_safeengine_nessun_segnale_base_allintervallo():
    assert _segnali_base(INTERVALLO_55, 55) == []


def test_safeengine_segnale_base_nel_secondo_tempo():
    assert len(_segnali_base(SECONDO_TEMPO_55, 55)) == 1


def test_safeengine_fase_ignota_base():
    se = eng.SafeEngine(clock=lambda: 1_000_000.0)
    se.evaluate([{"event_id": "35797769", "sport": "calcio", "payload": _payload(None, 60)}])
    voci = se.fase_ignota_events("base")
    assert [(v["event_id"], v["minute"]) for v in voci] == [("35797769", 60)]
    se.evaluate([{"event_id": "35797769", "sport": "calcio", "payload": _payload(None, 50)}])
    assert se.fase_ignota_events("base") == []        # sotto il 55': niente da dire


def test_bot_scrive_base_fase_ignota_solo_con_base_accesa():
    from Betfair.safe_strategy import bot_service as BS

    scritte = []

    class _Motore:
        def fase_ignota_events(self, variante):
            return [{"event_id": "35797769", "event_name": "Nord FC v Sud FC",
                     "minute": 56, "fase": "n/d: stato IPS assente"}] if variante == "base" else []

    orig = BS._log
    BS._log = lambda db, kind, payload: scritte.append((kind, payload))
    ora = datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc)
    try:
        BS._SKIP_LOG_STATE.clear()
        BS._log_base_fase_ignota(None, _Motore(), {"variants": ["base"]}, ora)
        BS._SKIP_LOG_STATE.clear()
        BS._log_base_fase_ignota(None, _Motore(), {"variants": ["esatto"]}, ora)
    finally:
        BS._log = orig
        BS._SKIP_LOG_STATE.clear()
    assert len(scritte) == 1, scritte
    kind, payload = scritte[0]
    assert kind == "skip" and payload["reason"] == "base_fase_ignota"
    assert payload["strategy"] == "base" and payload["signal_key"] == "fase_ignota:base"


def test_esatto_e_base_non_si_alternano_nella_deduplica():
    """Stessa partita, due motivi: chiavi diverse, una riga ciascuno e poi
    silenzio (prima la chiave era la stessa e i motivi si alternavano)."""
    from Betfair.safe_strategy import bot_service as BS

    scritte = []

    class _Motore:
        def esatto_fase_ignota_events(self):
            return [{"event_id": "1", "minute": 60}]

        def fase_ignota_events(self, variante):
            return [{"event_id": "1", "minute": 60}]

    orig = BS._log
    BS._log = lambda db, kind, payload: scritte.append(payload["reason"])
    ora = datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc)
    par = {"variants": ["base", "esatto"], "skip_log_interval_s": 600}
    try:
        BS._SKIP_LOG_STATE.clear()
        for _ in range(3):
            BS._log_esatto_fase_ignota(None, _Motore(), par, ora)
            BS._log_base_fase_ignota(None, _Motore(), par, ora)
    finally:
        BS._log = orig
        BS._SKIP_LOG_STATE.clear()
    assert scritte == ["esatto_fase_ignota", "base_fase_ignota"]


def test_il_giro_del_bot_chiama_la_diagnostica_base_prima_dei_segnali():
    import inspect
    from Betfair.safe_strategy import bot_service as BS
    src = inspect.getsource(BS.scan_and_place)
    assert src.index("_log_base_fase_ignota(db, engine, params, now)") < src.index("if not signals:")


def _valutazione(stato, minute, ev=None):
    ctx = eng.build_football_ctx_from_scan("35797769", _payload(stato, minute), 50, 120)
    ev = ev if ev is not None else eng.evaluate_base(ctx, _BASE)
    return CERT.Valutazione(strategia="base", ctx=ctx, ev=ev, par=dict(_BASE),
                            params=eng.merge_params(None))


def test_b18_tace_sul_motore_corretto():
    for stato, m in ((INTERVALLO_55, 55), (RECUPERO_1T_55, 55), (SECONDO_TEMPO_55, 55), (None, 60)):
        assert "B18" not in {v.codice for v in CERT.verifica(_valutazione(stato, m))}


def test_b18_vede_un_segnale_base_allintervallo():
    ctx = eng.build_football_ctx_from_scan("35797769", _payload(INTERVALLO_55, 55), 50, 120)
    buono = eng.evaluate_base(ctx, _BASE)

    def _storto(checks):
        return eng.VariantEvaluation(
            variant="base", state="signal", checks=checks, headline="BANCA Sud FC",
            side="LAY", selection="Sud FC", entry_odds=25, entry_size=None,
            market_type="MATCH_ODDS", market_id="1.1", selection_id=2)

    viol = [v for v in CERT.verifica(_valutazione(INTERVALLO_55, 55, _storto(buono.checks)))
            if v.codice == "B18"]
    assert viol and "segnale al 55'" in viol[0].dettaglio
    senza = _storto(tuple(c for c in buono.checks if c.id != "secondHalf"))
    viol = [v for v in CERT.verifica(_valutazione(INTERVALLO_55, 55, senza)) if v.codice == "B18"]
    assert viol and "non esiste piu'" in viol[0].dettaglio
