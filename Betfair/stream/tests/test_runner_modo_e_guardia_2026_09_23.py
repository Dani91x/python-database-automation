"""23/09 - runner calcio: (5) modalita' ordini non congelata all'import,
(6) guardia d'avvio sul client ordini.

(5) ``setup_and_run`` decideva client ordini e worker dalla COSTANTE
``config_stream.LIVE_ORDER_MODE`` (letta all'import), mentre il worker rilegge
``live_order_mode()`` a ogni giro. Adesso il runner legge ``live_order_mode()``
all'avvio e, a ogni ricostruzione dello stream, se il modo e' SALITO a caldo
(PAPER->LIVE, OFF->PAPER/LIVE) NON costruisce un client nuovo: tiene quello
d'avvio e scrive un errore "serve il riavvio".

(6) La pulizia di ripresa (specchio paper, richieste stantie) era best-effort:
se falliva il runner eseguiva comunque la coda ereditata. Adesso la guardia
d'avvio (``Betfair/stream/avvio_app.Guardia``) resta ARMATA finche' la ripresa
non riesce, e intanto il worker della coda non esegue nulla (riprova la
ripresa ogni 10 s).

Come in ``test_sync_account_worker_wiring.py``, ``setup_and_run`` (login
Betfair reale, stream, while True) si verifica sul CABLAGGIO (AST); i pezzi
nuovi si provano a unita' con ``db`` finto (stesse firme di ``stream/db.py``:
``cleanup_paper_mirror() -> (int, int)``,
``fail_stale_pending_requests(float) -> int``, ``insert_alert(level, code, msg)``).
"""
from __future__ import annotations

import ast
import inspect
import logging

import pytest

from Betfair.stream import avvio_app as AA
from Betfair.stream import runner


# ---------------------------------------------------------------------------
# (5) modalita' ordini
# ---------------------------------------------------------------------------
def _nomi_in_setup_and_run() -> set:
    albero = ast.parse(inspect.getsource(runner.setup_and_run))
    return {n.id for n in ast.walk(albero) if isinstance(n, ast.Name)}


def test_setup_and_run_non_usa_la_costante_congelata():
    nomi = _nomi_in_setup_and_run()
    assert "LIVE_ORDER_MODE" not in nomi, (
        "setup_and_run decide client/worker dalla costante letta all'import")
    assert "_modo_ordini_client" in nomi


def test_modo_invariato_nessun_log(monkeypatch, caplog):
    monkeypatch.setenv("LIVE_ORDER_MODE", "PAPER")
    with caplog.at_level(logging.WARNING, logger=runner.logger.name):
        assert runner._modo_ordini_client("PAPER") == "PAPER"
    assert not caplog.records


@pytest.mark.parametrize("avvio,ora", [("PAPER", "LIVE"), ("OFF", "LIVE"), ("OFF", "PAPER")])
def test_modo_salito_a_caldo_non_costruisce_e_chiede_il_riavvio(monkeypatch, caplog,
                                                                 avvio, ora):
    monkeypatch.setenv("LIVE_ORDER_MODE", ora)
    with caplog.at_level(logging.ERROR, logger=runner.logger.name):
        assert runner._modo_ordini_client(avvio) == avvio      # mai client a caldo
    assert any("riavvio" in r.getMessage() and r.levelno >= logging.ERROR
               for r in caplog.records)


def test_modo_sceso_a_caldo_resta_il_client_d_avvio_con_avviso(monkeypatch, caplog):
    monkeypatch.setenv("LIVE_ORDER_MODE", "PAPER")
    with caplog.at_level(logging.WARNING, logger=runner.logger.name):
        assert runner._modo_ordini_client("LIVE") == "LIVE"
    assert any(r.levelno == logging.WARNING for r in caplog.records)


# ---------------------------------------------------------------------------
# (6) guardia d'avvio sul client ordini
# ---------------------------------------------------------------------------
class _Db:
    def __init__(self, cade=0):
        self.cade, self.pulizie, self.stantie, self.alert = cade, 0, [], []

    def cleanup_paper_mirror(self):
        if self.cade > 0:
            self.cade -= 1
            raise ConnectionError("Server disconnected")
        self.pulizie += 1
        return (0, 0)

    def fail_stale_pending_requests(self, older_than_sec=120.0):
        self.stantie.append(older_than_sec)
        return 1

    def insert_alert(self, level, code, message):
        self.alert.append((level, code, message))


@pytest.fixture()
def guardia(monkeypatch):
    runner._GUARDIA_AVVIO.azzera()
    runner._RIPRESA_STATO["ultimo"] = 0.0
    chiamate = []
    monkeypatch.setattr(runner, "live_order_worker",
                        lambda ctx, fl, session=None, strategy=None: chiamate.append(fl))
    yield chiamate
    runner._GUARDIA_AVVIO.azzera()
    runner._RIPRESA_STATO["ultimo"] = 0.0


def test_la_guardia_e_quella_di_avvio_app():
    assert isinstance(runner._GUARDIA_AVVIO, AA.Guardia)


def test_ripresa_riuscita_disarma_la_guardia(monkeypatch, guardia):
    finto = _Db()
    monkeypatch.setattr(runner, "db", finto)
    runner._GUARDIA_AVVIO.attiva = True
    assert runner._ripresa_all_avvio() is True
    assert runner._GUARDIA_AVVIO.fatto and not runner._GUARDIA_AVVIO.blocca_aperture
    assert finto.stantie == [120.0]                      # soglia invariata
    runner._live_order_worker_guardato({}, "FL")
    assert guardia == ["FL"]


def test_ripresa_fallita_la_coda_resta_ferma_e_riprova(monkeypatch, guardia):
    finto = _Db(cade=1)
    monkeypatch.setattr(runner, "db", finto)
    orologio = [1000.0]
    monkeypatch.setattr(runner.time, "monotonic", lambda: orologio[0])
    runner._GUARDIA_AVVIO.attiva = True
    assert runner._ripresa_all_avvio() is False
    runner._RIPRESA_STATO["ultimo"] = orologio[0]
    assert runner._GUARDIA_AVVIO.blocca_aperture
    runner._live_order_worker_guardato({}, "FL")          # entro 10 s: niente
    assert guardia == [] and finto.pulizie == 0
    orologio[0] += runner._RIPRESA_RIPROVA_S
    runner._live_order_worker_guardato({}, "FL")          # riprova, riesce, esegue
    assert finto.pulizie == 1 and guardia == ["FL"]


def test_guardia_non_attiva_non_blocca(monkeypatch, guardia):
    # un test o un banco che chiama il worker senza avviare il runner
    monkeypatch.setattr(runner, "db", _Db(cade=99))
    runner._live_order_worker_guardato({}, "FL")
    assert guardia == ["FL"]


def _add_worker_function_names(tree) -> list:
    nomi = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "add_worker":
            for a in n.args:
                if isinstance(a, ast.Call):
                    for kw in a.keywords:
                        if kw.arg == "function" and isinstance(kw.value, ast.Name):
                            nomi.append(kw.value.id)
    return nomi


def test_setup_and_run_registra_il_worker_guardato_e_arma_la_guardia():
    src = inspect.getsource(runner.setup_and_run)
    albero = ast.parse(src)
    nomi = _add_worker_function_names(albero)
    assert "_live_order_worker_guardato" in nomi
    assert "live_order_worker" not in nomi, "worker della coda registrato senza guardia"
    assert "_GUARDIA_AVVIO.attiva = True" in src
    assert "_ripresa_all_avvio()" in src
