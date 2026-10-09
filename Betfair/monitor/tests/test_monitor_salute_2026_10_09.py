"""T0A "Salute" (09/10/2026): interruttore, contatori, scrittore, riga contro la
migrazione. Gli agganci nei file di produzione sono in
``test_monitor_agganci_2026_10_09.py``; il referto in
``test_monitor_referto_2026_10_09.py``.

Ogni test e' stato FALSIFICATO (mutazione -> rosso): numeri nel referto
``ARCHITETTURA_2026-10/tappa0/T0A_SALUTE/REFERTO.md``.
"""
from __future__ import annotations

import ast
import json
import logging
import re
import sys
import types
from pathlib import Path

import pytest

from Betfair.monitor import registro as R
from Betfair.monitor import scrittore as SC
from Betfair.monitor import sonde as M

RADICE = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# interruttore: spento di serie, spento nel banco per costruzione
# ---------------------------------------------------------------------------
def test_di_serie_spento_nessun_thread_nessun_handler(monkeypatch):
    monkeypatch.delenv(M.ENV, raising=False)
    prima = {n: list(logging.getLogger(n).handlers) for n, _c, _l in M._GESTORI}
    assert M.avvia("x", _consenti_in_test=True) is False
    assert M.ATTIVO is False
    assert all(t.name != "monitor-salute" for t in __import__("threading").enumerate())
    assert {n: list(logging.getLogger(n).handlers) for n, _c, _l in M._GESTORI} == prima


@pytest.mark.parametrize("valore", ["0", "", "true", "si", "2", " 1x"])
def test_solo_1_accende(monkeypatch, valore):
    monkeypatch.setenv(M.ENV, valore)
    monkeypatch.setattr(M, "nel_banco", lambda: False)
    assert M.avvia("x", scrittore=False, _consenti_in_test=True) is False
    assert M.ATTIVO is False


def test_nel_banco_spento_per_costruzione(monkeypatch):
    """Con un modulo del banco caricato nel processo il monitor NON si accende,
    nemmeno con l'interruttore a 1 (il banco non chiama mai un main di servizio:
    questo e' il secondo chiavistello)."""
    monkeypatch.setenv(M.ENV, "1")
    monkeypatch.setitem(sys.modules, "Betfair.stream.backtest._sonda_test_t0a",
                        types.ModuleType("Betfair.stream.backtest._sonda_test_t0a"))
    assert M.nel_banco() is True
    assert M.avvia("x", scrittore=False, _consenti_in_test=True) is False
    assert M.ATTIVO is False


def test_nel_banco_falso_senza_moduli_del_banco(monkeypatch):
    finti = {k: v for k, v in sys.modules.items() if not k.startswith("Betfair.stream.backtest")}
    monkeypatch.setattr(sys, "modules", finti)
    assert M.nel_banco() is False


def test_sotto_pytest_non_si_accende_senza_permesso(monkeypatch):
    """Un test che chiama il main VERO di un servizio (es. Mike) con il .env del
    PC a MONITOR_SALUTE=1 non deve far partire scritture nel DB."""
    monkeypatch.setenv(M.ENV, "1")
    monkeypatch.setattr(M, "nel_banco", lambda: False)
    assert M.avvia("x", scrittore=False) is False
    assert M.ATTIVO is False


def test_acceso_e_spento(monitor_acceso):
    assert M.ATTIVO is True
    assert M.stato()["servizio"] == "prova-test"
    M.ferma()
    assert M.ATTIVO is False
    for nome, _c, _l in M._GESTORI:
        assert not any(isinstance(h, M._Gestore) for h in logging.getLogger(nome).handlers)


def test_avvia_solo_dentro_i_main_dei_servizi():
    """Ogni ``_mon.avvia(`` dei file di produzione sta dentro una funzione
    ``main``/``_main`` (mai all'import di un modulo: nessuna regressione
    all'avvio, nessun banco che lo accende importando)."""
    trovati = []
    for p in (RADICE / "Betfair").rglob("*.py"):
        if "/tests/" in p.as_posix() or p.parts[-2] == "monitor":
            continue
        testo = p.read_text(encoding="utf-8")
        if "_mon.avvia(" not in testo:
            continue
        albero = ast.parse(testo)
        for fn in ast.walk(albero):
            if isinstance(fn, ast.FunctionDef):
                for n in ast.walk(fn):
                    if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                            and n.func.attr == "avvia" and getattr(n.func.value, "id", "") == "_mon"):
                        trovati.append((p.relative_to(RADICE).as_posix(), fn.name))
        rel = p.relative_to(RADICE).as_posix()
        assert testo.count("_mon.avvia(") == sum(1 for f, _ in trovati if f == rel), p
    assert trovati, "nessun servizio avvia il monitor"
    assert {fn for _f, fn in trovati} <= {"main", "_main"}, trovati
    servizi = {f for f, _fn in trovati}
    assert servizi == {
        "Betfair/stream/runner.py", "Betfair/stream/tennis_live/tennis_runner.py",
        "Betfair/stream/tennis_live/tennis_bot_service.py", "Betfair/stream/scalper/scalper_service.py",
        "Betfair/stream/scalper/scalper_session.py", "Betfair/safe_strategy/service.py",
        "Betfair/omega/omega_service.py", "Betfair/safe_strategy/bot_service.py", "Betfair/mike/service.py"}


# ---------------------------------------------------------------------------
# registro
# ---------------------------------------------------------------------------
def test_registro_fotografa_e_azzera():
    r = R.Registro()
    r.conta("db", "GET a")
    r.conta("db", "GET a", 2)
    r.tratto("t", 3.0)
    r.tratto("t", 700.0)
    r.valore("v", "k", 0)
    f = r.fotografa_e_azzera()
    assert f["contatori"] == {"db": {"GET a": 3}}
    assert f["tratti"]["t"]["n"] == 2 and f["tratti"]["t"]["max"] == 700.0
    assert f["tratti"]["t"]["min"] == 3.0
    assert f["valori"] == {"v": {"k": 0}}
    f2 = r.fotografa_e_azzera()
    assert f2["contatori"] == {} and f2["tratti"] == {}
    assert f2["valori"] == {"v": {"k": 0}}          # i valori passano di riga in riga


def test_registro_tetto_delle_chiavi():
    r = R.Registro()
    for i in range(R.MAX_CHIAVI + 50):
        r.conta("g", f"k{i}")
    g = r.fotografa_e_azzera()["contatori"]["g"]
    assert len(g) == R.MAX_CHIAVI + 1
    assert g[R.ALTRO] == 50


def test_secchi_e_quantili():
    h = R.Istogramma()
    for v in [1.0] * 98 + [400.0, 9000.0]:
        h.aggiungi(v)
    s = h.riassunto()
    assert s["p50"] == 1.0
    assert s["p99"] == 500.0                         # bordo del secchio di 400
    assert sum(s["secchi"]) == 100
    oltre = R.Istogramma()
    oltre.aggiungi(70000.0)
    assert oltre.riassunto()["p50"] == 70000.0       # troppo pieno = massimo osservato


def test_somma_dei_riassunti_e_esatta_secchio_per_secchio():
    a, b, tutto = R.Istogramma(), R.Istogramma(), R.Istogramma()
    for v in (0.3, 4.0, 4.5, 120.0):
        a.aggiungi(v)
        tutto.aggiungi(v)
    for v in (1500.0, 2.0):
        b.aggiungi(v)
        tutto.aggiungi(v)
    s = R.somma_riassunti([a.riassunto(), b.riassunto()])
    t = tutto.riassunto()
    assert s["secchi"] == t["secchi"]
    assert (s["n"], s["min"], s["max"], s["p50"], s["p99"]) == (t["n"], t["min"], t["max"], t["p50"], t["p99"])


# ---------------------------------------------------------------------------
# osserva_stream, marche
# ---------------------------------------------------------------------------
def test_osserva_stream_spento_non_conta(monkeypatch):
    monkeypatch.delenv(M.ENV, raising=False)
    M.REGISTRO.azzera_tutto()
    M.osserva_stream("calcio", '{"op":"mcm","pt":1,"mc":[]}')
    assert M.REGISTRO.fotografa_e_azzera()["contatori"] == {}


def test_osserva_stream_mcm_status_e_lo_zero(monitor_acceso):
    import time as _t

    pt = int(_t.time() * 1000) - 250
    M.osserva_stream("scanner", '{"op":"mcm","id":3,"initialClk":"G1xH","clk":"AAAA","pt":%d,"mc":[{"id":"1.1"}]}' % pt)
    M.osserva_stream("scanner", '{"op":"status","id":3,"statusCode":"SUCCESS","connectionClosed":false,'
                                '"connectionsAvailable":0}')
    M.osserva_stream("scanner", '{"op":"status","id":4,"statusCode":"FAILURE","errorCode":'
                                '"MAX_CONNECTION_LIMIT_EXCEEDED","connectionClosed":true}')
    M.osserva_stream("scanner", "non json {")
    M.osserva_stream("scanner", None)
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["contatori"]["stream_msg"] == {"scanner": 1}
    assert f["contatori"]["stream_status"] == {"scanner SUCCESS": 1,
                                               "scanner FAILURE MAX_CONNECTION_LIMIT_EXCEEDED": 1}
    assert f["valori"]["connessioni_disponibili"] == {"scanner": 0}     # lo 0 resta
    t = f["tratti"]["feed_rx_pt_ms.scanner"]
    assert t["n"] == 1 and 240.0 <= t["min"] < 5000.0


def test_marca_ladder_copia_e_mai_l_originale(monitor_acceso):
    riga = {"event_id": "1", "market_id": "1.2", "ladder": {"updated_ms": 5}}
    copia = M.marca_ladder(riga, {"pt": 1_000})
    assert copia is not riga
    assert set(copia) - set(riga) == {"ts_pub_ms", "pt"}
    assert copia["pt"] == 1_000
    assert set(riga) == {"event_id", "market_id", "ladder"}          # la riga del DB resta pulita
    assert M.marca_ladder(riga, {})["ts_pub_ms"] > 0                  # senza pt: solo ts_pub_ms
    assert "pt" not in M.marca_ladder(riga, {"pt": True})


def test_marche_spente_identita(monkeypatch):
    monkeypatch.delenv(M.ENV, raising=False)
    riga = {"a": 1}
    assert M.marca_ladder(riga, {"pt": 5}) is riga and riga == {"a": 1}
    p = {"source": "omega", "trade_id": 1}
    assert M.marca_emesso(p) is p and p == {"source": "omega", "trade_id": 1}
    assert M.ricevuto_ms() == 0


def test_marca_emesso_acceso(monitor_acceso):
    p = M.marca_emesso({"source": "safe", "trade_id": 3})
    assert isinstance(p["emesso_ms"], int) and p["emesso_ms"] > 1_600_000_000_000
    assert M.REGISTRO.fotografa_e_azzera()["contatori"]["ordini_emessi"] == {"safe": 1}


# ---------------------------------------------------------------------------
# handler di log: Betfair vero e paper MAI sommati
# ---------------------------------------------------------------------------
def test_esecuzione_live_e_paper_separate_transazioni_solo_live(monitor_acceso):
    lv = logging.getLogger("flumine.execution.betfairexecution")
    sim = logging.getLogger("flumine.execution.simulatedexecution")
    vecchi = (lv.level, sim.level)
    lv.setLevel(logging.INFO)
    sim.setLevel(logging.INFO)
    try:
        lv.info("execute_place", extra={"elapsed_time": 0.2, "order_package": {"order_count": 3,
                                                                              "package_type": "Place"}})
        lv.info("execute_replace", extra={"elapsed_time": 0.1, "order_package": {"order_count": 1}})
        lv.info("execute_cancel", extra={"elapsed_time": 0.1, "order_package": {"order_count": 2}})
        lv.error("Execution error", extra={"order_package": {"order_count": 1, "package_type": "Place"}})
        sim.info("execute_place", extra={"elapsed_time": 0.0, "order_package": {"order_count": 5}})
        lv.warning("High latency between current time and OrderPackage creation time, it is likely",
                   extra={"latency": 0.25})
    finally:
        lv.setLevel(vecchi[0])
        sim.setLevel(vecchi[1])
    f = M.REGISTRO.fotografa_e_azzera()
    c = f["contatori"]
    assert c["esecuzione_live"] == {"place": 3, "replace": 1, "cancel": 2}
    assert c["esecuzione_paper"] == {"place": 5}
    assert c["transazioni"] == {"place": 3, "replace": 1, "fallite": 1}   # il paper non e' una transazione
    assert f["tratti"]["betfair_place_ms"]["max"] == 200.0
    assert f["tratti"]["pacchetto_attesa_ms"]["n"] == 1


def test_latenza_flumine_e_stato_dal_log(monitor_acceso):
    logging.getLogger("flumine.baseflumine").warning(
        "High latency between current time and MarketBook publish time", extra={"latency": 3.1})
    li = logging.getLogger("betfairlightweight.streaming.listener")
    vecchio = li.level
    li.setLevel(logging.INFO)
    try:
        li.info("[%s: %s]: %s (%s connections available)", "MarketStream", 7, "SUCCESS", 4)
    finally:
        li.setLevel(vecchio)
    logging.getLogger("qualcosa").error("x")
    f = M.REGISTRO.fotografa_e_azzera()
    assert f["tratti"]["flumine_latenza_alta_ms"]["max"] == 3100.0
    assert f["valori"]["connessioni_disponibili_log"] == {"stream-7": 4}
    assert f["contatori"]["log_errori"] == {"ERROR qualcosa": 1}


# ---------------------------------------------------------------------------
# scrittore e riga contro la migrazione
# ---------------------------------------------------------------------------
def _colonne_della_migrazione():
    sql = (RADICE / "migrations" / "monitor_metrics_2026-10-09.sql").read_text(encoding="utf-8")
    corpo = sql.split("CREATE TABLE IF NOT EXISTS public.monitor_metrics (", 1)[1].split("\n);", 1)[0]
    colonne = {}
    for riga in corpo.splitlines():
        m = re.match(r"\s+([a-z_]+)\s+([A-Z]+)", riga)
        if m:
            colonne[m.group(1)] = ("NOT NULL" in riga and "DEFAULT" not in riga, m.group(2))
    return colonne


def test_riga_ha_le_colonne_della_tabella_con_i_tipi(monitor_acceso, tmp_path):
    inviate = []
    s = SC.Scrittore(servizio="prova-test", sport="calcio", intervallo=30.0, invia=inviate.append,
                     cartella=str(tmp_path))
    M.conta("db", "GET mike_trades", 4)
    M.conta("betfair_rest", "listMarketBook", 2)
    riga = s.giro()
    col = _colonne_della_migrazione()
    assert set(riga) <= set(col), set(riga) - set(col)
    obbligatorie = {k for k, (nn, _t) in col.items() if nn and k != "id"}
    assert obbligatorie <= set(riga)
    tipi = {"TIMESTAMPTZ": str, "TEXT": str, "INTEGER": int, "NUMERIC": (int, float), "JSONB": dict}
    for k, v in riga.items():
        if v is not None:
            assert isinstance(v, tipi[col[k][1]]), (k, v)
    assert riga["db_richieste"] == 4 and riga["rest_richieste"] == 2
    assert riga["metriche"]["v"] == 1 and "sistema" in riga["metriche"]
    assert inviate == [riga]
    json.dumps(riga)                                       # serializzabile per PostgREST


def test_scrittore_locale_e_db_giu(monitor_acceso, tmp_path, caplog):
    def _rompi(_r):
        raise RuntimeError("relation monitor_metrics does not exist")

    s = SC.Scrittore(servizio="mike-service", sport="calcio", intervallo=30.0, invia=_rompi,
                     cartella=str(tmp_path))
    with caplog.at_level(logging.WARNING, logger=SC.__name__):
        r1 = s.giro()
        r2 = s.giro()
    assert r1 is not None and r2 is not None
    assert s.errori_db == 2 and s.scritte_db == 0
    avvisi = [r for r in caplog.records if "monitor_metrics" in r.getMessage()]
    assert len(avvisi) == 1                                # un avviso ogni 10 minuti, non a raffica
    righe = list(tmp_path.rglob("mike-service.jsonl"))
    assert len(righe) == 1
    lette = [json.loads(x) for x in righe[0].read_text(encoding="ascii").splitlines()]
    assert len(lette) == 2 and lette[0]["servizio"] == "mike-service"
    assert "sistema" in lette[0]["metriche"] and "sistema" not in lette[1]["metriche"]


def test_sistema_ogni_venti_righe(monitor_acceso, tmp_path):
    s = SC.Scrittore(servizio="x", sport=None, intervallo=30.0, invia=lambda r: None, cartella=str(tmp_path))
    con = [("sistema" in s.giro()["metriche"]) for _ in range(SC.OGNI_RIGHE_SISTEMA + 1)]
    assert con[0] and con[SC.OGNI_RIGHE_SISTEMA] and sum(con) == 2


def test_processo_senza_psutil_degrada(monkeypatch):
    from Betfair.monitor import processo as P

    monkeypatch.setattr(P, "_psutil", lambda: None)
    c = P.CampionatoreProcesso()
    sum(i * i for i in range(20000))
    out = c.campiona()
    assert out["psutil"] is False
    assert out["cpu_pct"] is None or out["cpu_pct"] >= 0
    assert out["thread"] >= 1
    assert P.info_sistema()["python"] == sys.version.split()[0]


def test_processo_con_psutil():
    pytest.importorskip("psutil")
    from Betfair.monitor import processo as P

    out = P.CampionatoreProcesso().campiona()
    assert out["psutil"] is True and out["rss_mb"] > 1.0 and out["thread"] >= 1
