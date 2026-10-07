# -*- coding: utf-8 -*-
"""Safe ESATTO SOLO NEL SECONDO TEMPO (decisione dell'utente, 07/10/2026).

Reperto D1 (`AUDIT_2026-10-07/CONFORMITA_BOT_CALCIO.md` par. 7): nel RECUPERO
del 1o tempo il feed IPS di Betfair segna il minuto CUMULATO (timeElapsed 46,
47, 48 ... con elapsedRegularTime 45 e matchStatus 'KickOff'), quindi la
soglia "dal 48'" dell'ESATTO valeva anche PRIMA dell'intervallo. Sulla
35797769 (Spagna-Belgio) e' successo dalle 19:46 alle 19:50 sull'1-1: niente
ingresso solo perche' la banca era fuori banda.

Decisione dell'utente (testuale): "No, e' tassativo nel secondo tempo, il primo
tempo va escluso". Regola: fase = 2o TEMPO (dallo stato IPS del feed,
``score_raw.matchStatus``) E minuto >= soglia di sempre (48). Recupero del 1T e
intervallo = MAI. Stato IPS assente = fase ignota = nessun ingresso (n/d).

I finti sono gli stati IPS VERI della 35797769 (`_live_raw/35797769/
35797769.scores.jsonl`, righe 19:49:22, 19:50:45 e 20:10:25) con le stesse
chiavi e gli stessi tipi; il test `test_i_finti_hanno_le_chiavi_del_vero`
lo verifica sulla registrazione quando c'e'.
"""
import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from Betfair.safe_strategy import certificazione as CERT
from Betfair.safe_strategy import engine as eng
from Betfair.safe_strategy import scanner as SC
from Betfair.safe_strategy.tests.test_engine import calcio_payload

_ESATTO = eng.DEFAULT_PARAMS["esatto"]
_REG = Path(__file__).resolve().parents[3] / "_live_raw" / "35797769" / "35797769.scores.jsonl"
# il checkout principale (i worktree dei delegati non hanno le registrazioni)
_REG_PRINCIPALE = Path("/home/user/python-database-automation/_live_raw/35797769/35797769.scores.jsonl")


def _squadra(nome: str, gol: str, ht: str, secondo_tempo: bool, gialli: int,
             corner: int, punti: int) -> Dict[str, Any]:
    blk: Dict[str, Any] = {
        "name": nome, "score": gol, "halfTimeScore": ht, "fullTimeScore": "",
        "penaltiesScore": "", "penaltiesSequence": [], "games": "", "sets": "",
        "numberOfYellowCards": gialli, "numberOfRedCards": 0, "numberOfCards": gialli,
        "numberOfCorners": corner, "numberOfCornersFirstHalf": corner,
        "bookingPoints": punti,
    }
    if secondo_tempo:
        blk["numberOfCornersSecondHalf"] = 0
    return blk


def stato_ips(match_status: str, time_elapsed: int, regular: int,
              added: Optional[int], secondo_tempo: bool = False,
              ht: str = "") -> Dict[str, Any]:
    """Lo stato IPS GREZZO di Betfair (chiavi e tipi della registrazione vera,
    Spagna-Belgio 1-1). ``added`` None = chiave assente, come nel vero."""
    casa = _squadra("Spain", "1", ht, secondo_tempo, 1, 3, 10)
    ospite = _squadra("Belgium", "1", ht, secondo_tempo, 0, 0, 0)
    score: Dict[str, Any] = {"home": casa, "away": ospite,
                             "numberOfYellowCards": 1, "numberOfRedCards": 0,
                             "numberOfCards": 1, "numberOfCorners": 3,
                             "numberOfCornersFirstHalf": 3}
    if secondo_tempo:
        score["numberOfCornersSecondHalf"] = 0
    score["bookingPoints"] = 10
    st: Dict[str, Any] = {"eventTypeId": 1, "eventId": 35797769, "score": score,
                          "timeElapsed": time_elapsed, "elapsedRegularTime": regular}
    if added is not None:
        st["elapsedAddedTime"] = added
    st["timeElapsedSeconds"] = 41
    st["fullTimeElapsed"] = {"hour": 0, "min": 0, "sec": 0}
    st["status"] = match_status
    st["matchStatus"] = match_status
    return st


# i tre momenti veri della 35797769
RECUPERO_1T_48 = stato_ips("KickOff", 48, 45, 3)                        # 19:49:22
INTERVALLO_50 = stato_ips("FirstHalfEnd", 50, 45, 5, ht="1")            # 19:50:45
SECONDO_TEMPO_48 = stato_ips("SecondHalfKickOff", 48, 48, None,         # 20:10:25
                             secondo_tempo=True, ht="1")


def _payload(stato: Optional[Dict[str, Any]], minute: int = 48) -> Dict[str, Any]:
    """Riga dello scanner (`service.build_rows`) con ``score_raw`` come lo
    scrive lo scanner vero (`scanner.strip_volatile_state`). 1-1, banca
    "Altro risultato Casa" 45 (dentro 30-70): passa tutto tranne la fase."""
    p = calcio_payload(minute=minute, sh=1, sa=1)
    if stato is None:
        p.pop("score_raw", None)
    else:
        p["score_raw"] = SC.strip_volatile_state(copy.deepcopy(stato))
    return p


def _esatto(stato: Optional[Dict[str, Any]], minute: int = 48) -> eng.VariantEvaluation:
    ctx = eng.build_football_ctx_from_scan("35797769", _payload(stato, minute), 46, 120)
    return eng.evaluate_esatto(ctx, _ESATTO, "home")


def _check(ev: eng.VariantEvaluation, cid: str):
    return next((c for c in ev.checks if c.id == cid), None)


# ---------------------------------------------------------------------------
# 1. la regola
# ---------------------------------------------------------------------------
def test_recupero_del_primo_tempo_al_48_non_entra():
    """Il caso vero: 19:49 della 35797769, KickOff, timeElapsed 48. Prima del
    07/10 il motore dava SEGNALE (minuto 48 >= 48)."""
    ev = _esatto(RECUPERO_1T_48, 48)
    assert ev.state == "no", [(c.id, c.value, c.ok) for c in ev.checks]
    ck = _check(ev, "secondHalf")
    assert ck is not None and ck.ok is False
    assert "recupero" in ck.value


def test_intervallo_non_entra():
    """FirstHalfEnd col minuto che continua a contare (50): e' ancora 1T."""
    ev = _esatto(INTERVALLO_50, 50)
    assert ev.state == "no"
    ck = _check(ev, "secondHalf")
    assert ck.ok is False and "intervallo" in ck.value


def test_secondo_tempo_al_48_entra_come_prima():
    ev = _esatto(SECONDO_TEMPO_48, 48)
    assert ev.state == "signal", [(c.id, c.value, c.ok) for c in ev.checks]
    assert _check(ev, "secondHalf").ok is True
    assert ev.entry_odds == 45 and ev.market_type == "CORRECT_SCORE"


def test_secondo_tempo_sotto_soglia_resta_no():
    """La soglia del minuto NON cambia: 2T al 47' resta fuori."""
    ev = _esatto(stato_ips("SecondHalfKickOff", 47, 46, None, secondo_tempo=True, ht="1"), 47)
    assert ev.state == "no"
    assert _check(ev, "minute").ok is False
    assert _check(ev, "secondHalf").ok is True


@pytest.mark.parametrize("minute", [48, 66, 92])
def test_stato_ips_assente_fail_closed(minute):
    """Nessuno stato IPS nella riga: fase ignota, nessun ingresso (n/d),
    nemmeno al 92' (il minuto da solo non certifica la fase)."""
    ev = _esatto(None, minute)
    assert ev.state == "nd"
    ck = _check(ev, "secondHalf")
    assert ck.ok is None and "stato IPS assente" in ck.value
    assert ev.headline is None


def test_stato_ips_vecchio_fail_closed():
    """Stato rimasto 'KickOff' con un minuto da 2T (35833626, misura del 25/09
    in `atlante_v4`): la fonte unica lo dichiara ambiguo -> n/d, nessun ingresso."""
    ev = _esatto(stato_ips("KickOff", 70, 35, None), 70)
    assert ev.state == "nd"
    assert _check(ev, "secondHalf").ok is None


def test_la_regola_e_solo_dellesatto():
    """La decisione del 07/10 mattina riguardava l'ESATTO; dal 07/10 sera
    ("SAFE BASE SEMPRE E SOLO SECONDO TEMPO") anche la BASE. La PUNTA no."""
    ctx = eng.build_football_ctx_from_scan("35797769", _payload(RECUPERO_1T_48, 48), 46, 120)
    evs = eng.evaluate_football_all(ctx, eng.DEFAULT_PARAMS)
    per_var = {(e.variant, e.sub_id): e for e in evs}
    assert _check(per_var[("base", None)], "secondHalf") is not None
    assert _check(per_var[("punta", None)], "secondHalf") is None
    assert _check(per_var[("esatto", "home")], "secondHalf") is not None
    assert _check(per_var[("esatto", "away")], "secondHalf") is not None


def test_soglia_del_minuto_invariata():
    assert _ESATTO["minuteMin"] == 48


# ---------------------------------------------------------------------------
# 2. il motore intero (SafeEngine: tracker di stabilita' + candidati)
# ---------------------------------------------------------------------------
def _segnali(stato: Optional[Dict[str, Any]], minute: int):
    t = {"now": 1_000_000.0}
    se = eng.SafeEngine(clock=lambda: t["now"])
    riga = {"event_id": "35797769", "sport": "calcio", "payload": _payload(stato, minute)}
    se.evaluate([riga])
    t["now"] += 120.0                      # punteggio stabile da 120 s (>= 30)
    return [s for s in se.evaluate([riga]) if "esatto" in str(getattr(s, "key", s))]


def test_safeengine_nessun_segnale_nel_recupero_del_primo_tempo():
    assert _segnali(RECUPERO_1T_48, 48) == []


def test_safeengine_segnale_nel_secondo_tempo():
    assert len(_segnali(SECONDO_TEMPO_48, 48)) >= 1


def test_safeengine_fase_ignota_diagnostica_per_lattivita():
    """Fase ignota: il motore la ESPONE (il bot la scrive nell'attivita')."""
    t = {"now": 1_000_000.0}
    se = eng.SafeEngine(clock=lambda: t["now"])
    se.evaluate([{"event_id": "35797769", "sport": "calcio", "payload": _payload(None, 50)}])
    voci = se.esatto_fase_ignota_events()
    assert [v["event_id"] for v in voci] == ["35797769"]
    assert voci[0]["minute"] == 50
    # con lo stato IPS presente non c'e' nulla da dire
    se.evaluate([{"event_id": "35797769", "sport": "calcio",
                  "payload": _payload(SECONDO_TEMPO_48, 48)}])
    assert se.esatto_fase_ignota_events() == []


def test_bot_scrive_il_motivo_nellattivita():
    from Betfair.safe_strategy import bot_service as BS
    from datetime import datetime, timezone

    scritte = []

    class _Motore:
        def esatto_fase_ignota_events(self):
            return [{"event_id": "35797769", "event_name": "Spain v Belgium", "minute": 50}]

    orig = BS._log
    BS._log = lambda db, kind, payload: scritte.append((kind, payload))
    try:
        BS._SKIP_LOG_STATE.clear()
        BS._log_esatto_fase_ignota(None, _Motore(), {"variants": ["esatto"]},
                                   datetime(2026, 7, 10, 19, 50, tzinfo=timezone.utc))
        BS._SKIP_LOG_STATE.clear()
        BS._log_esatto_fase_ignota(None, _Motore(), {"variants": ["base"]},
                                   datetime(2026, 7, 10, 19, 50, tzinfo=timezone.utc))
    finally:
        BS._log = orig
        BS._SKIP_LOG_STATE.clear()
    assert len(scritte) == 1, scritte      # variante ESATTO spenta: niente rumore
    kind, payload = scritte[0]
    assert kind == "skip" and payload["reason"] == "esatto_fase_ignota"
    assert payload["strategy"] == "esatto" and payload["event_id"] == "35797769"


def test_il_giro_del_bot_chiama_la_diagnostica_prima_dei_segnali():
    """Scritta in ``scan_and_place`` PRIMA dell'uscita su "nessun segnale":
    la fase ignota produce proprio zero segnali ESATTO, dopo sarebbe muta."""
    import inspect
    from Betfair.safe_strategy import bot_service as BS
    src = inspect.getsource(BS.scan_and_place)
    i = src.index("_log_esatto_fase_ignota(db, engine, params, now)")
    assert i < src.index("if not signals:")


# ---------------------------------------------------------------------------
# 3. il controllo di condotta del banco (E11)
# ---------------------------------------------------------------------------
def _valutazione(stato, minute, ev=None):
    ctx = eng.build_football_ctx_from_scan("35797769", _payload(stato, minute), 46, 120)
    ev = ev if ev is not None else eng.evaluate_esatto(ctx, _ESATTO, "home")
    return CERT.Valutazione(strategia="esatto", ctx=ctx, ev=ev, par=dict(_ESATTO),
                            params=eng.merge_params(None))


def test_e11_tace_sul_motore_corretto():
    for stato, m in ((RECUPERO_1T_48, 48), (INTERVALLO_50, 50), (SECONDO_TEMPO_48, 48), (None, 50)):
        assert "E11" not in {v.codice for v in CERT.verifica(_valutazione(stato, m))}


def test_e11_vede_un_segnale_nel_recupero_del_primo_tempo():
    """Il difetto che E11 nasce per prendere: un segnale ESATTO col feed in 1T."""
    ctx = eng.build_football_ctx_from_scan("35797769", _payload(RECUPERO_1T_48, 48), 46, 120)
    buono = eng.evaluate_esatto(ctx, _ESATTO, "home")
    def _storto(checks):
        return eng.VariantEvaluation(
            variant="esatto", sub_id="home", state="signal", checks=checks,
            headline="BANCA Altro risultato Casa (Spain)", side="LAY",
            selection="Altro risultato Casa", entry_odds=45, entry_size=None,
            market_type="CORRECT_SCORE", market_id="1.2", selection_id=11)

    # segnale col check della fase presente (e FALSO): lo prende il ramo "segnale"
    con_check = _storto(buono.checks)
    viol = [v for v in CERT.verifica(_valutazione(RECUPERO_1T_48, 48, con_check))
            if v.codice == "E11"]
    assert viol and "segnale al 48'" in viol[0].dettaglio
    # check della fase tolto dal motore: lo prende il ramo "check sparito"
    senza = _storto(tuple(c for c in buono.checks if c.id != "secondHalf"))
    viol = [v for v in CERT.verifica(_valutazione(RECUPERO_1T_48, 48, senza))
            if v.codice == "E11"]
    assert viol and "non esiste piu'" in viol[0].dettaglio


# ---------------------------------------------------------------------------
# 4. i finti parlano come il vero
# ---------------------------------------------------------------------------
def _righe_vere():
    for p in (_REG, _REG_PRINCIPALE):
        if p.is_file():
            return p
    return None


@pytest.mark.skipif(_righe_vere() is None, reason="registrazione 35797769 assente")
def test_i_finti_hanno_le_chiavi_del_vero():
    vere = {}
    for line in _righe_vere().read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("source") == "betfair" and r["ts"][11:19] in ("19:49:22", "19:50:45", "20:10:25"):
            vere[r["ts"][11:19]] = r["payload"]
    assert set(vere) == {"19:49:22", "19:50:45", "20:10:25"}

    def forma(x):
        if isinstance(x, dict):
            return {k: forma(v) for k, v in x.items()}
        if isinstance(x, list):
            return [forma(v) for v in x]
        return type(x).__name__

    for ora, finto in (("19:49:22", RECUPERO_1T_48), ("19:50:45", INTERVALLO_50),
                       ("20:10:25", SECONDO_TEMPO_48)):
        vero = vere[ora]
        assert forma(finto) == forma(vero), ora
        for k in ("matchStatus", "status", "timeElapsed", "elapsedRegularTime"):
            assert finto[k] == vero[k], (ora, k)
        assert finto.get("elapsedAddedTime") == vero.get("elapsedAddedTime"), ora
