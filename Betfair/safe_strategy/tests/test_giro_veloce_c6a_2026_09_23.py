"""C6 a (23/09) - ``run_once`` diviso in giro LENTO e giro VELOCE.

Che cosa inchioda questo file:
  * interruttore ``SAFE_BOT_GIRO_VELOCE`` assente: nessuna fotografia, client
    del canale senza sveglia del prezzo, attesa di oggi;
  * EQUIVALENZA: il giro lento (``run_once``) fa le STESSE chiamate, nello
    STESSO ordine, con o senza giri veloci intercalati - anche quando il veloce
    anticipa;
  * il giro veloce non tocca ne' il database ne' il mercato: 0 chiamate;
  * che cosa anticipa (uscita dovuta, punteggio cambiato: la corsia calda) e
    che cosa RIMANDA al lento (contesto oltre 5 s, ciclo degradato, uscita gia'
    inviata, riga del canale senza ``odds_ts_ms``, partita che il DB non ha);
  * coalescenza (N sveglie = 1 giro), tetto dei giri veloci al secondo, tetto
    degli anticipi al minuto, una novita' anticipa una volta sola;
  * l'attesa col giro veloce non sbircia la coda piu' spesso di oggi.

I finti sono quelli di ``test_bot_service`` (stesse chiavi di
``safe_strategy_trades``/``safe_strategy_scan``). Nessuna rete, nessun
Supabase, nessun processo. File ASCII-only.
"""
from __future__ import annotations

import inspect
import json
import threading
import time
from datetime import timedelta

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import canale_scan as CS
from Betfair.safe_strategy.tests.test_bot_service import (
    NOW, FakeDB, FakeMarket, _auto_trade, _exit_feed_row, _reset_module_state,
    _tennis_feed_row,
)

ODDS_TS = 1_700_000_000_000
#: il separatore del punteggio tennis di ``_score_of`` (U+00B7), scritto cosi'
#: perche' il file resta ASCII-only
PUNTO = chr(0xB7)


@pytest.fixture(autouse=True)
def _pulizia(monkeypatch):
    monkeypatch.delenv(S.ENV_GIRO_VELOCE, raising=False)
    monkeypatch.delenv(CS.ENV_LEGGE_CANALE, raising=False)
    monkeypatch.delenv(CS.ENV_SVEGLIA, raising=False)
    S.azzera_canale_scan()
    S.azzera_giro_veloce()
    _reset_module_state()
    S._EXIT_WAIT_AT.clear()
    S._LAST_CONTROL.clear()
    yield
    S.azzera_canale_scan()
    S.azzera_giro_veloce()
    _reset_module_state()
    S._EXIT_WAIT_AT.clear()
    S._LAST_CONTROL.clear()


def _accendi(monkeypatch):
    monkeypatch.setenv(S.ENV_GIRO_VELOCE, "1")


def _dal_canale(riga, secondi):
    """La stessa riga come arriva dal canale: piu' recente e con odds_ts_ms."""
    r = json.loads(json.dumps(riga))
    r["updated_at"] = (NOW + timedelta(seconds=secondi)).isoformat()
    r["payload"]["odds_ts_ms"] = ODDS_TS + int(secondi * 1000)
    return r


def _lento(db, riga, at=NOW):
    db.scan_rows = [riga]
    return S.run_once(db=db, market=FakeMarket(), engine=None, now=at)


class Registro:
    """Involucro che REGISTRA ogni chiamata di metodo (nome + argomenti)."""

    def __init__(self, dentro, nome, righe):
        self._dentro, self._nome, self._righe = dentro, nome, righe

    def __getattr__(self, nome):
        attr = getattr(self._dentro, nome)
        if not callable(attr):
            return attr

        def _chiamata(*a, **kw):
            self._righe.append((self._nome, nome,
                                json.dumps([a, kw], default=str, sort_keys=True)))
            return attr(*a, **kw)
        return _chiamata


class Spia:
    """Qualunque accesso a un attributo e' una violazione: conta e solleva."""

    def __init__(self):
        self.accessi = []

    def __getattr__(self, nome):
        self.accessi.append(nome)
        raise AssertionError(f"il giro veloce ha toccato {nome}")


# ---------------------------------------------------------------------------
# 1. Interruttore spento = oggi
# ---------------------------------------------------------------------------
def test_interruttore_assente_nessuna_fotografia(monkeypatch):
    db = FakeDB(status="running")
    _auto_trade(db, "base")
    _lento(db, _exit_feed_row(60, 1, 0))
    assert S._giro_veloce_acceso() is False
    assert S._GIRO_LENTO["now_ts"] is None
    assert S._CORSIA["eventi"] == frozenset()
    assert S.run_giro_veloce(now=NOW)["motivo"] == "nessun_giro_lento"


def test_interruttore_assente_il_client_non_ha_la_sveglia_del_prezzo(monkeypatch):
    monkeypatch.setenv(CS.ENV_LEGGE_CANALE, "1")
    monkeypatch.setattr(CS.ClientScan, "avvia", lambda self: None)
    assert S.avvia_client_scan() is True
    cl = S._CANALE_SCAN["client"]
    assert cl.evento is None and cl.interessa is None
    S.azzera_canale_scan()
    _accendi(monkeypatch)
    assert S.avvia_client_scan() is True
    cl = S._CANALE_SCAN["client"]
    assert cl.evento is S._PREZZO_NUOVO
    assert cl.interessa is S.interessa_al_giro_veloce


# ---------------------------------------------------------------------------
# 2. EQUIVALENZA: il lento fa le stesse cose, veloce o non veloce
# ---------------------------------------------------------------------------
def _reset_tutto():
    S.azzera_giro_veloce()
    S.azzera_canale_scan()
    _reset_module_state()
    S._EXIT_WAIT_AT.clear()
    S._EVENTI_CHIUSI.clear()
    S._CONTO_LETTO_A.clear()
    S._OPPS_STATE.clear()
    S._LAST_CONTROL.clear()
    S._AGG_ULTIMO_BUONO.clear()


def _scenario(db, righe_log, veloce):
    """Uscita base (gol, assestamento, green-up) + tennis (obbligatoria)."""
    _auto_trade(db, "base")
    _auto_trade(db, "tennis", event_id="2.1", market_id="mt", selection_id=11,
                side="back", price=1.3, sport="tennis",
                score_at_entry=f"set 1-0 {PUNTO} game 4-2", minute_at_entry=None,
                signal_key="2.1:tennis:set 1-0")
    rdb = Registro(db, "db", righe_log)
    rmk = Registro(FakeMarket(), "mk", righe_log)
    passi = [(0, (60, 1, 0), (4, 2)), (2, (66, 2, 0), (4, 3)),
             (4, (66, 2, 0), (4, 4)), (35, (66, 2, 0), (5, 4)),
             (37, (80, 3, 0), (5, 5))]
    esiti, anticipi = [], 0
    for sec, (mi, sh, sa), g in passi:
        at = NOW + timedelta(seconds=sec)
        db.scan_rows = [_exit_feed_row(mi, sh, sa, updated_at=at),
                        _tennis_feed_row((1, 0), g, updated_at=at)]
        esiti.append(S.run_once(db=rdb, market=rmk, engine=None, now=at))
        if veloce:
            # righe del canale PIU' NUOVE: prima a punteggio invariato (minuto
            # dopo, stesso game: passa dal tracciamento sulla COPIA e dalla
            # decisione di uscita), poi con novita' vere (gol, game). Il veloce
            # deve anticipare e non deve cambiare niente del lento.
            stesse = {"1.1": _dal_canale(_exit_feed_row(mi + 1, sh, sa), sec + 0.5),
                      "2.1": _dal_canale(_tennis_feed_row((1, 0), g), sec + 0.5)}
            nuove = {"1.1": _dal_canale(_exit_feed_row(mi + 1, sh + 1, sa), sec + 1),
                     "2.1": _dal_canale(_tennis_feed_row((1, 0), (g[0], g[1] + 1)),
                                        sec + 1)}
            for k, fresche in enumerate((stesse, stesse, nuove, nuove)):
                e = S.run_giro_veloce(now=at + timedelta(milliseconds=300 * (k + 1)),
                                      fresche=fresche)
                anticipi += int(bool(e["anticipa"]))
    return esiti, anticipi


def test_equivalenza_il_lento_non_cambia_con_giri_veloci_intercalati(monkeypatch):
    _reset_tutto()
    log_a: list = []
    db_a = FakeDB(status="running")
    esiti_a, _ = _scenario(db_a, log_a, veloce=False)

    # le due corse partono dallo STESSO stato di processo (Safe non ha ancora
    # ``svuota_le_cache``: qui si azzerano a mano le cache che il ciclo usa)
    _reset_tutto()
    _accendi(monkeypatch)
    log_b: list = []
    db_b = FakeDB(status="running")
    esiti_b, anticipi = _scenario(db_b, log_b, veloce=True)

    assert anticipi >= 2, "lo scenario deve davvero far anticipare il veloce"

    import re

    def _n(testo):
        # solo gli istanti d'orologio da parete (t4/t5/t6, *_ms) cambiano da
        # una corsa all'altra; tutto il resto deve essere identico
        return re.sub(r'"(t\d_[a-z_]+|[a-z0-9_]*_ms)": -?[0-9.]+', '"\\1": X', testo)

    def _norm(x):
        return _n(json.dumps(x, default=str, sort_keys=True))

    assert [(a, b) for a, b, _ in log_a] == [(a, b) for a, b, _ in log_b], \
        "stesse chiamate, stesso ordine"
    assert [(a, b, _n(c)) for a, b, c in log_a] == [(a, b, _n(c)) for a, b, c in log_b], \
        "stessi argomenti"
    assert _norm(db_a.trades) == _norm(db_b.trades)
    assert _norm(db_a.activity) == _norm(db_b.activity)
    assert _norm(esiti_a) == _norm(esiti_b)
    assert sum(e["exits"] for e in esiti_a) >= 2, "lo scenario deve far uscire davvero"


# ---------------------------------------------------------------------------
# 3. Il veloce non ha db ne' market, e non li tocca
# ---------------------------------------------------------------------------
def test_il_giro_veloce_non_riceve_db_ne_market():
    for fn in (S.run_giro_veloce, S.giro_veloce_se_dovuto, S._novita_per_il_lento):
        nomi = set(inspect.signature(fn).parameters)
        assert not nomi & {"db", "market"}, fn.__name__


def test_il_giro_veloce_fa_zero_chiamate_al_database_e_al_mercato(monkeypatch):
    _accendi(monkeypatch)
    db = FakeDB(status="running")
    _auto_trade(db, "base")
    _lento(db, _exit_feed_row(79, 1, 0))
    spia_db, spia_mk = Spia(), Spia()
    monkeypatch.setattr(S, "_real_db", spia_db)
    monkeypatch.setattr(S, "_real_market", spia_mk)
    fresche = {"1.1": _dal_canale(_exit_feed_row(80, 2, 0), 1)}
    S.segnala_prezzo_nuovo()
    esito = S.giro_veloce_se_dovuto(now=NOW + timedelta(seconds=1), mono=1000.0)
    esito2 = S.run_giro_veloce(now=NOW + timedelta(seconds=1), fresche=fresche)
    assert esito is not None
    assert esito2["anticipa"] is True
    assert spia_db.accessi == [] and spia_mk.accessi == []


# ---------------------------------------------------------------------------
# 4. Che cosa anticipa
# ---------------------------------------------------------------------------
def test_uscita_a_tempo_dovuta_anticipa_e_il_lento_la_invia(monkeypatch):
    _accendi(monkeypatch)
    db = FakeDB(status="stopped")
    tid = _auto_trade(db, "base")
    assert _lento(db, _exit_feed_row(79, 1, 0))["exits"] == 0
    riga = _dal_canale(_exit_feed_row(80, 1, 0), 1)
    e = S.run_giro_veloce(now=NOW + timedelta(seconds=1), fresche={"1.1": riga})
    assert e["anticipa"] is True
    assert e["firme"] and e["firme"][0].startswith(f"u|{tid}|time|")
    # il giro lento con la STESSA riga fa esattamente cio' che il veloce ha
    # previsto: l'uscita la decide e la invia il codice di oggi
    r = _lento(db, riga, at=NOW + timedelta(seconds=1))
    assert r["exits"] == 1


def test_corsia_calda_tennis_game_cambiato_anticipa(monkeypatch):
    _accendi(monkeypatch)
    db = FakeDB(status="running")
    _auto_trade(db, "tennis", event_id="2.1", market_id="mt", selection_id=11,
                side="back", price=1.3, sport="tennis",
                score_at_entry=f"set 1-0 {PUNTO} game 4-2", minute_at_entry=None,
                signal_key="2.1:tennis:set 1-0")
    _lento(db, _tennis_feed_row((1, 0), (4, 2)))
    assert S._CORSIA["eventi"] == frozenset({"2.1"})
    riga = _dal_canale(_tennis_feed_row((1, 0), (4, 3)), 1)
    e = S.run_giro_veloce(now=NOW + timedelta(seconds=1), fresche={"2.1": riga})
    assert e["anticipa"] is True
    assert e["firme"] == [f"p|2.1|set 1-0 {PUNTO} game 4-3"]


def test_gol_su_partita_con_posizione_anticipa(monkeypatch):
    _accendi(monkeypatch)
    db = FakeDB(status="running")
    _auto_trade(db, "base")
    _lento(db, _exit_feed_row(60, 1, 0))
    riga = _dal_canale(_exit_feed_row(61, 2, 0), 1)
    e = S.run_giro_veloce(now=NOW + timedelta(seconds=1), fresche={"1.1": riga})
    assert e["anticipa"] is True and e["firme"] == ["p|1.1|2-0"]


# ---------------------------------------------------------------------------
# 5. Che cosa RIMANDA al lento
# ---------------------------------------------------------------------------
def test_contesto_oltre_5_secondi_non_anticipa(monkeypatch):
    _accendi(monkeypatch)
    db = FakeDB(status="running")
    _auto_trade(db, "base")
    _lento(db, _exit_feed_row(60, 1, 0))
    riga = _dal_canale(_exit_feed_row(61, 2, 0), 1)
    tardi = S.run_giro_veloce(now=NOW + timedelta(seconds=5.1), fresche={"1.1": riga})
    assert tardi["anticipa"] is False and tardi["motivo"] == "contesto_scaduto"
    in_tempo = S.run_giro_veloce(now=NOW + timedelta(seconds=4.9), fresche={"1.1": riga})
    assert in_tempo["anticipa"] is True
    assert CS.MAX_ETA_CONTESTO_S == 5.0


def test_ciclo_degradato_il_veloce_rimanda(monkeypatch):
    _accendi(monkeypatch)
    db = FakeDB(status="running")
    _auto_trade(db, "base")
    _lento(db, _exit_feed_row(60, 1, 0))
    db.read_control = lambda: (_ for _ in ()).throw(RuntimeError("schema cache"))
    _lento(db, _exit_feed_row(60, 1, 0), at=NOW + timedelta(seconds=2))
    riga = _dal_canale(_exit_feed_row(61, 2, 0), 3)
    e = S.run_giro_veloce(now=NOW + timedelta(seconds=3), fresche={"1.1": riga})
    assert e["anticipa"] is False and e["motivo"] == "contesto_non_utilizzabile"


def test_uscita_gia_inviata_resta_al_lento(monkeypatch):
    _accendi(monkeypatch)
    db = FakeDB(status="stopped")
    # residuo di un'uscita gia' inviata, in cooldown: il lento non lo tocca
    # in questo giro, e il veloce non deve nemmeno provarci
    _auto_trade(db, "base", meta={"exit_requested": {"sent": True, "kind": "time",
                                                     "reason": "minuto_80",
                                                     "last_attempt_ts": NOW.isoformat()},
                                  "residual_size": 3.0})
    _lento(db, _exit_feed_row(79, 1, 0))
    riga = _dal_canale(_exit_feed_row(80, 1, 0), 1)
    e = S.run_giro_veloce(now=NOW + timedelta(seconds=1), fresche={"1.1": riga})
    assert e["anticipa"] is False and e["valutate"] == 1


def test_riga_del_canale_senza_odds_ts_ms_non_e_una_novita(monkeypatch):
    _accendi(monkeypatch)
    db = FakeDB(status="running")
    _auto_trade(db, "base")
    _lento(db, _exit_feed_row(60, 1, 0))
    riga = _dal_canale(_exit_feed_row(61, 2, 0), 1)
    riga["payload"].pop("odds_ts_ms")
    e = S.run_giro_veloce(now=NOW + timedelta(seconds=1), fresche={"1.1": riga})
    assert e["anticipa"] is False and e["valutate"] == 0


def test_il_canale_non_aggiunge_partite_al_veloce(monkeypatch):
    _accendi(monkeypatch)
    db = FakeDB(status="running")
    _auto_trade(db, "base")
    _auto_trade(db, "base", event_id="9.9", signal_key="9.9:base:1-0")
    _lento(db, _exit_feed_row(60, 1, 0))          # il DB elenca SOLO 1.1
    riga = _dal_canale(_exit_feed_row(61, 2, 0, event_id="9.9"), 1)
    e = S.run_giro_veloce(now=NOW + timedelta(seconds=1), fresche={"9.9": riga})
    assert e["anticipa"] is False and e["valutate"] == 0


def test_stessa_riga_gia_vista_dal_lento_non_e_una_novita(monkeypatch):
    _accendi(monkeypatch)
    db = FakeDB(status="running")
    _auto_trade(db, "base")
    riga = _exit_feed_row(60, 1, 0)
    _lento(db, riga)
    e = S.run_giro_veloce(now=NOW + timedelta(seconds=1), fresche={})
    assert e["anticipa"] is False and e["valutate"] == 0


# ---------------------------------------------------------------------------
# 6. Freni: una volta sola, tetto anticipi, coalescenza, tetto giri veloci
# ---------------------------------------------------------------------------
def test_una_novita_anticipa_una_volta_sola(monkeypatch):
    _accendi(monkeypatch)
    db = FakeDB(status="running")
    _auto_trade(db, "base")
    _lento(db, _exit_feed_row(60, 1, 0))
    riga = _dal_canale(_exit_feed_row(61, 2, 0), 1)
    assert S.run_giro_veloce(now=NOW + timedelta(seconds=1),
                             fresche={"1.1": riga})["anticipa"] is True
    seconda = S.run_giro_veloce(now=NOW + timedelta(seconds=1.2), fresche={"1.1": riga})
    assert seconda["anticipa"] is False and seconda["motivo"] == "niente_di_nuovo"


def test_tetto_degli_anticipi_al_minuto(monkeypatch):
    _accendi(monkeypatch)
    db = FakeDB(status="running")
    n = S._ANTICIPI_MAX_AL_MIN + 1
    for i in range(n):
        _auto_trade(db, "base", event_id=f"1.{i}", signal_key=f"1.{i}:base:1-0")
    db.scan_rows = [_exit_feed_row(60, 1, 0, event_id=f"1.{i}") for i in range(n)]
    S.run_once(db=db, market=FakeMarket(), engine=None, now=NOW)
    esiti = []
    for i in range(n):
        riga = _dal_canale(_exit_feed_row(61, 2, 0, event_id=f"1.{i}"), 1)
        esiti.append(S.run_giro_veloce(now=NOW + timedelta(seconds=1),
                                       fresche={f"1.{i}": riga}))
    assert [e["anticipa"] for e in esiti] == [True] * (n - 1) + [False]
    assert esiti[-1]["motivo"] == "tetto_anticipi"
    assert S.stato_giro_veloce()["anticipi_negati"] == 1


def test_coalescenza_n_sveglie_un_giro():
    for _ in range(50):
        S.segnala_prezzo_nuovo()
    assert S.giro_veloce_se_dovuto(now=NOW, mono=500.0) is not None
    assert S.giro_veloce_se_dovuto(now=NOW, mono=510.0) is None, "coda vuota"
    st = S.stato_giro_veloce()
    assert st["giri"] == 1 and st["sveglie"] == 50 and st["coalescenti"] == 49


def test_interessa_solo_le_partite_con_posizione(monkeypatch):
    _accendi(monkeypatch)
    db = FakeDB(status="running")
    _auto_trade(db, "base")
    _lento(db, _exit_feed_row(60, 1, 0))
    assert S.interessa_al_giro_veloce("1.1") is True
    assert S.interessa_al_giro_veloce("7.7") is False
    assert S.interessa_al_giro_veloce(None) is False


def test_tetto_dei_giri_veloci_al_secondo():
    giri = 0
    for k in range(101):                  # 1 secondo, una sveglia ogni 10 ms
        S.segnala_prezzo_nuovo()
        if S.giro_veloce_se_dovuto(now=NOW, mono=2000.0 + k * 0.01) is not None:
            giri += 1
    assert giri <= int(S._GIRI_VELOCI_MAX_AL_S) + 1
    assert giri >= int(S._GIRI_VELOCI_MAX_AL_S), "il tetto frena, non spegne"
    assert S.stato_giro_veloce()["fermati_dal_tetto"] > 0


# ---------------------------------------------------------------------------
# 7. L'attesa col giro veloce: anticipa, ma non sbircia piu' di oggi
# ---------------------------------------------------------------------------
class _Coda:
    def __init__(self):
        self.letture = 0

    def pending_requests(self, limit=50):
        self.letture += 1
        return []


def test_attesa_col_veloce_non_sbircia_piu_di_oggi(monkeypatch):
    coda = _Coda()
    monkeypatch.setattr(S, "_real_db", coda)
    monkeypatch.setattr(S, "_MIN_GIRO_S", 0.0)
    fermo = threading.Event()

    def _martella():
        while not fermo.is_set():
            S.segnala_prezzo_nuovo()
            time.sleep(0.005)

    t = threading.Thread(target=_martella, daemon=True)
    t.start()
    try:
        uscita = S._attesa_con_giro_veloce(1.0, aperte=1, evento=None)
    finally:
        fermo.set()
        t.join(timeout=1.0)
    assert uscita is False, "nessuna novita': si dorme fino in fondo"
    assert coda.letture <= int(1.0 / S._SBIRCIATA_S), coda.letture
    assert S.stato_giro_veloce()["giri"] <= int(S._GIRI_VELOCI_MAX_AL_S) + 1


def test_attesa_col_veloce_esce_alla_novita(monkeypatch):
    coda = _Coda()
    monkeypatch.setattr(S, "_real_db", coda)
    monkeypatch.setattr(S, "_MIN_GIRO_S", 0.0)
    monkeypatch.setattr(S, "run_giro_veloce",
                        lambda **kw: {"anticipa": True, "motivo": "novita", "firme": ["x"]})
    S.segnala_prezzo_nuovo()
    t0 = time.monotonic()
    assert S._attesa_con_giro_veloce(2.0, aperte=0, evento=None) is True
    assert time.monotonic() - t0 < 1.0


def test_attesa_col_veloce_la_sveglia_ui_resta_immediata(monkeypatch):
    monkeypatch.setattr(S, "_MIN_GIRO_S", 0.0)
    ui = threading.Event()
    ui.set()
    t0 = time.monotonic()
    assert S._attesa_con_giro_veloce(2.0, aperte=0, evento=ui) is True
    assert time.monotonic() - t0 < 0.2 and not ui.is_set()
