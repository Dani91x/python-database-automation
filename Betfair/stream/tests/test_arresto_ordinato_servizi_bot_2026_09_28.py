"""CANTIERE K (28/09) - arresto ordinato propagato anche ai SERVIZI dei bot
(non solo ai due runner, gia' del cantiere A): Omega, Mike, Safe scanner,
Safe bot, ponte tennis, scalper-service. Stesso file/modulo condiviso
(Betfair/stream/arresto_ordinato.py), un controllo ADDITIVO nel ciclo
esterno di ciascuno (mai un cambio di logica di trading: nessuna soglia,
stake, tetto, gamba o cancello decisionale toccato).

Ogni servizio e' troppo pesante da avviare per davvero in un test (lock di
singola istanza, canali locali, client Betfair, DB): come per runner.py
(cantiere A, `test_fine_evento_2026_09_28.py::
test_setup_and_run_controlla_l_arresto_in_cima_al_ciclo`), qui si verifica
CHE il controllo esista nel punto giusto del sorgente (`inspect.getsource`,
STESSO metodo del cantiere A) e, dove il pezzo e' isolabile senza avviare il
servizio (scalper-service: la condizione del kill-switch e' una singola
espressione booleana), si esercita per davvero.
"""
from __future__ import annotations

import inspect
import os

from Betfair.stream import arresto_ordinato as AO


def test_omega_controlla_l_arresto_in_cima_al_ciclo():
    from Betfair.omega import omega_service as S
    modulo_src = inspect.getsource(S)
    assert "from Betfair.stream import arresto_ordinato as _AO" in modulo_src
    src = inspect.getsource(S.main)
    i = src.index("while True:")
    finestra = src[i:i + 500]
    assert "_AO.richiesto()" in finestra
    assert "break" in finestra


def test_mike_controlla_l_arresto_in_cima_al_ciclo_e_non_in_once():
    from Betfair.mike import service as S
    modulo_src = inspect.getsource(S)
    assert "from Betfair.stream import arresto_ordinato as _AO" in modulo_src
    src = inspect.getsource(S.main)
    i = src.index("while True:")
    finestra = src[i:i + 500]
    assert "not args.once and _AO.richiesto()" in finestra, "mai interrompere un --once"
    assert "break" in finestra


def test_safe_scanner_controlla_l_arresto_in_cima_al_ciclo():
    from Betfair.safe_strategy import service as S
    modulo_src = inspect.getsource(S)
    assert "from Betfair.stream import arresto_ordinato as _AO" in modulo_src
    src = inspect.getsource(S.main)
    i = src.rindex("while True:")  # l'ultimo: il ciclo persistente, non il --once
    finestra = src[i:i + 500]
    assert "_AO.richiesto()" in finestra
    assert "break" in finestra


def test_safe_bot_controlla_l_arresto_in_cima_al_ciclo():
    from Betfair.safe_strategy import bot_service as S
    modulo_src = inspect.getsource(S)
    assert "from Betfair.stream import arresto_ordinato as _AO" in modulo_src
    src = inspect.getsource(S.main)
    i = src.index("while True:")
    finestra = src[i:i + 500]
    assert "_AO.richiesto()" in finestra
    assert "break" in finestra


def test_ponte_tennis_controlla_l_arresto_in_cima_al_ciclo():
    from Betfair.stream.tennis_live import tennis_bot_service as S
    modulo_src = inspect.getsource(S)
    assert "from .. import arresto_ordinato as _AO" in modulo_src
    src = inspect.getsource(S._ensure_loop)
    i = src.index("while not stop.is_set():")
    finestra = src[i:i + 500]
    assert "_AO.richiesto()" in finestra
    assert "break" in finestra


def test_scalper_kill_switch_reagisce_anche_all_arresto_ordinato(monkeypatch, tmp_path):
    """A differenza degli altri, qui la condizione E' ISOLABILE (non serve
    avviare il servizio): `os.path.isfile(KILL_FILE) or _AO.richiesto()`."""
    from Betfair.stream.scalper import scalper_service as S

    monkeypatch.setenv("APP_ARRESTO_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)  # KILL_FILE e' relativo alla cwd, come nel servizio vero
    assert os.path.isfile(S.KILL_FILE) is False
    assert AO.richiesto() is False
    assert (os.path.isfile(S.KILL_FILE) or AO.richiesto()) is False

    AO.richiedi()
    assert (os.path.isfile(S.KILL_FILE) or AO.richiesto()) is True
    AO.cancella()
    assert (os.path.isfile(S.KILL_FILE) or AO.richiesto()) is False

    # il kill-switch di oggi (STOP_SCALPER) continua a funzionare da solo,
    # senza bisogno del file di arresto: "il kill-switch non va mai scavalcato"
    with open(S.KILL_FILE, "w", encoding="ascii") as fh:
        fh.write("x")
    assert (os.path.isfile(S.KILL_FILE) or AO.richiesto()) is True


def test_scalper_source_usa_entrambe_le_condizioni():
    from Betfair.stream.scalper import scalper_service as S
    modulo_src = inspect.getsource(S)
    assert "from .. import arresto_ordinato as _AO" in modulo_src
    src = inspect.getsource(S.main)
    # main() ha PIU' "while True:" (un retry di login piu' su): quello del
    # supervisore (kill-switch) e' l'ULTIMO, non il primo.
    i = src.rindex("while True:")
    finestra = src[i:i + 700]
    assert "os.path.isfile(KILL_FILE) or _AO.richiesto()" in finestra
