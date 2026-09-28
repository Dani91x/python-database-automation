"""CANTIERE K2 (28/09, seconda consegna) - test di COMPORTAMENTO dell'arresto
ordinato, non di sorgente.

Il coordinatore ha rilanciato le mie mutazioni sui test della prima consegna
(`test_arresto_ordinato_servizi_bot_2026_09_28.py`): quella su
`Betfair/safe_strategy/service.py` (`if _AO.richiesto():` -> `if False and
_AO.richiesto():`) e' SOPRAVVISSUTA — il test guardava il TESTO del sorgente
(`inspect.getsource`), che contiene ancora la stringa `_AO.richiesto()` anche
dopo la mutazione. Qui si prova il COMPORTAMENTO vero: si chiama il codice
reale (non un suo testo) e si osserva cosa fa.

Per farlo senza avviare i servizi (lock di singola istanza, DB, client
Betfair, canali — troppo pesante e vietato dal brief), il ciclo esterno di
ciascun servizio e' stato estratto in una funzione dedicata, ISOLATA dal
resto (setup pesante non ancora fatto, lavoro del giro iniettato da fuori):

  * `Betfair.omega.omega_service._ciclo_persistente(un_giro, label=...)`
  * `Betfair.mike.service._ciclo_persistente(un_giro, label=..., controlla_arresto=...)`
  * `Betfair.safe_strategy.service._ciclo_persistente(scan)` (e
    `_ciclo_una_volta(scan)` per il singolo giro)
  * `Betfair.safe_strategy.bot_service._ciclo_persistente(un_giro, label=...)`
  * `Betfair.stream.scalper.scalper_service._ciclo_supervisore(deve_fermarsi,
    ferma, un_giro)` e `attendi_e_termina_flat(children, ...)` (gia' gusci
    puri: i pezzi sono iniettati)
  * `Betfair.stream.tennis_live.tennis_bot_service._ensure_loop(stop)` (era
    gia' cosi' dal cantiere che l'ha scritta: nessuna modifica qui)

Ognuna di queste funzioni CONTIENE il vero `while True: if <arresto>: break`
(o l'equivalente): chiamarla per davvero, con un file ARRESTO vero scritto
DOPO l'avvio (mtime valido) o PRIMA (mtime di ieri, un resto di uno
spegnimento precedente), prova il comportamento — non il testo.

SICUREZZA DEI TEST: ogni funzione qui chiamata contiene un VERO `while True`.
Se la produzione fosse rotta (o mutata durante la falsificazione) in modo da
non fermarsi mai, un test ingenuo resterebbe APPESO — non c'e' pytest-timeout
installato (vietato installarlo). Ogni callable iniettato in un ciclo ha
quindi un TETTO di sicurezza: dopo poche chiamate solleva un errore chiaro
invece di girare per sempre. Il tetto e' un dettaglio del test, MAI del
comportamento atteso (che resta l'assert sul numero di chiamate).

I due runner (calcio/tennis, cantiere A) hanno gia' `arresto_worker` come
funzione isolata e testabile (non un ciclo, nessun rischio di appendersi):
qui si aggiunge SOLO il caso "file piu' vecchio dell'avvio NON ferma"
chiamando di nuovo il worker VERO (non solo AO.richiesto() da sola, che la
consegna precedente del cantiere A gia' provava).
"""
from __future__ import annotations

import os
import threading
from typing import Any, Callable, List, Tuple

import pytest

from Betfair.stream import arresto_ordinato as AO

_TETTO_SICUREZZA = 5


@pytest.fixture
def cartella_arresto(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ARRESTO_DIR", str(tmp_path))
    return tmp_path


def _file_vecchio(tmp_path) -> None:
    """Scrive ARRESTO con mtime di un'ora PRIMA dell'avvio del processo
    (resto di uno spegnimento precedente): non deve contare."""
    p = AO.richiedi()
    vecchio = AO.AVVIO_PROCESSO - 3600
    os.utime(p, (vecchio, vecchio))


def _giro_limitato(cap: int = _TETTO_SICUREZZA) -> Tuple[Callable[[], bool], List[int]]:
    """``un_giro`` iniettabile con un TETTO di sicurezza (solo anti-hang, non
    il comportamento provato): se supera ``cap`` chiamate solleva un errore
    leggibile invece di girare per sempre. Ritorna (funzione, lista delle
    chiamate: ``len(...)`` e' il conteggio vero da controllare nell'assert)."""
    chiamate: List[int] = []

    def _un_giro() -> bool:
        chiamate.append(1)
        if len(chiamate) > cap:
            raise AssertionError(
                f"il ciclo ha superato {cap} giri: NON si e' fermato per "
                "l'arresto ordinato (probabile difetto/mutazione)")
        return True

    return _un_giro, chiamate


# ===========================================================================
# I DUE RUNNER (cantiere A): arresto_worker era GIA' isolata e testata sul
# caso "file fresco". Qui si aggiunge il caso mancante — "file vecchio NON
# ferma" — chiamando di nuovo il worker VERO.
# ===========================================================================
def test_runner_calcio_arresto_worker_ignora_file_vecchio(cartella_arresto, monkeypatch):
    from Betfair.stream import runner as R

    fermati: List[Any] = []
    monkeypatch.setattr(R, "_stop_framework", lambda fw: fermati.append(fw))
    s = R.LiveSession()
    _file_vecchio(cartella_arresto)
    R.arresto_worker({}, "FW", s)
    assert fermati == [] and not s.shutdown_requested.is_set(), \
        "un file piu' vecchio dell'avvio non deve fermare il runner calcio"
    AO.cancella()


def test_runner_tennis_arresto_worker_ignora_file_vecchio(cartella_arresto, monkeypatch):
    from Betfair.stream.tennis_live import tennis_runner as TR

    fermati: List[Any] = []
    monkeypatch.setattr(TR, "_stop_framework", lambda fw: fermati.append(fw))
    s = TR.TennisLiveSession(trading=None)
    _file_vecchio(cartella_arresto)
    TR.arresto_worker({}, "FW", s)
    assert fermati == [] and not s.shutdown_requested.is_set(), \
        "un file piu' vecchio dell'avvio non deve fermare il runner tennis"
    AO.cancella()


# ===========================================================================
# OMEGA
# ===========================================================================
def test_omega_ciclo_esce_entro_un_giro_con_arresto_fresco(cartella_arresto):
    from Betfair.omega import omega_service as S

    un_giro, chiamate = _giro_limitato()
    AO.richiedi()  # fresco: dopo l'avvio del processo
    S._ciclo_persistente(un_giro, label="[omega-test]")
    assert len(chiamate) == 0, "il giro NON deve partire: l'arresto e' controllato PRIMA"
    AO.cancella()


def test_omega_ciclo_NON_esce_con_arresto_vecchio(cartella_arresto):
    from Betfair.omega import omega_service as S

    giri: List[int] = []

    def _un_giro() -> bool:
        giri.append(1)
        return len(giri) < 3  # si ferma da sola dopo 3 giri (mai un test appeso)

    _file_vecchio(cartella_arresto)
    S._ciclo_persistente(_un_giro, label="[omega-test]")
    assert giri == [1, 1, 1], "un file piu' vecchio dell'avvio non deve fermare il ciclo"
    AO.cancella()


# ===========================================================================
# MIKE (con la guardia --once)
# ===========================================================================
def test_mike_ciclo_esce_entro_un_giro_con_arresto_fresco(cartella_arresto):
    from Betfair.mike import service as S

    un_giro, chiamate = _giro_limitato()
    AO.richiedi()
    S._ciclo_persistente(un_giro, label="[mike-test]")
    assert len(chiamate) == 0
    AO.cancella()


def test_mike_ciclo_NON_esce_con_arresto_vecchio(cartella_arresto):
    from Betfair.mike import service as S

    giri: List[int] = []

    def _un_giro() -> bool:
        giri.append(1)
        return len(giri) < 3

    _file_vecchio(cartella_arresto)
    S._ciclo_persistente(_un_giro, label="[mike-test]")
    assert giri == [1, 1, 1]
    AO.cancella()


def test_mike_ciclo_ignora_l_arresto_in_once(cartella_arresto):
    """`controlla_arresto=False`: mai interrompere un `--once` (un giro
    singolo di collaudo, non il servizio lungo)."""
    from Betfair.mike import service as S

    giri: List[int] = []
    AO.richiedi()  # arresto ATTIVO, eppure...

    def _un_giro_once() -> bool:
        giri.append(1)
        return False  # --once: un giro solo, si ferma da sola

    S._ciclo_persistente(_un_giro_once, label="[mike-test]", controlla_arresto=False)
    assert giri == [1], "il --once esegue il suo giro ANCHE con l'arresto attivo"
    AO.cancella()


# ===========================================================================
# SAFE STRATEGY — SCANNER (qui e' nata la mutazione sopravvissuta)
# ===========================================================================
class _ScanFinto:
    """``tick()`` col TETTO di sicurezza anti-hang (vedi ``_giro_limitato``)."""

    def __init__(self, cap: int = _TETTO_SICUREZZA) -> None:
        self.tick_chiamate = 0
        self._cap = cap

    def tick(self) -> None:
        self.tick_chiamate += 1
        if self.tick_chiamate > self._cap:
            raise AssertionError(
                f"scan.tick() chiamato oltre {self._cap} volte: il ciclo NON "
                "si e' fermato per l'arresto ordinato")


def test_safe_scanner_ciclo_esce_entro_un_giro_con_arresto_fresco(cartella_arresto, monkeypatch):
    from Betfair.safe_strategy import service as S

    monkeypatch.setattr(S.time, "sleep", lambda _s: None)  # niente 0.5s vero
    scan = _ScanFinto()
    AO.richiedi()
    S._ciclo_persistente(scan)
    assert scan.tick_chiamate == 0, "scan.tick() non deve MAI partire con l'arresto gia' attivo"
    AO.cancella()


def test_safe_scanner_ciclo_NON_esce_con_arresto_vecchio(cartella_arresto, monkeypatch):
    from Betfair.safe_strategy import service as S

    monkeypatch.setattr(S.time, "sleep", lambda _s: None)
    scan = _ScanFinto()
    _file_vecchio(cartella_arresto)

    # il ciclo persistente e' un `while True` vero: lo si ferma da fuori
    # facendo scattare AO.richiedi() dopo un paio di giri (stesso principio
    # degli altri test: mai un test appeso).
    giri = {"n": 0}
    vero_una_volta = S._ciclo_una_volta

    def _una_volta_poi_arresto(s):
        giri["n"] += 1
        if giri["n"] >= 3:
            AO.richiedi()  # ORA si arma per davvero: il PROSSIMO giro esce
        return vero_una_volta(s)

    monkeypatch.setattr(S, "_ciclo_una_volta", _una_volta_poi_arresto)
    S._ciclo_persistente(scan)
    # giro 1 e 2: file vecchio, tick eseguito; al giro 3 si arma l'arresto
    # PRIMA di richiamare la funzione vera, che quindi si ferma subito (0
    # tick in quel giro): 2 tick totali, non 3.
    assert scan.tick_chiamate == 2, "2 giri col file vecchio, fermato al 3° dal nuovo arresto"
    AO.cancella()


def test_falsificazione_diretta_della_mutazione_del_coordinatore(cartella_arresto, monkeypatch):
    """MUTAZIONE ESATTA segnalata dal coordinatore: `if _AO.richiesto():` ->
    `if False and _AO.richiesto():` in `_ciclo_una_volta`. Qui si applica
    quella stessa mutazione (non al testo: al comportamento, sostituendo la
    funzione con la sua versione mutata) e si prova che il tick parte
    comunque: e' il difetto che il vecchio test (sorgente) non vedeva."""
    from Betfair.safe_strategy import service as S

    monkeypatch.setattr(S.time, "sleep", lambda _s: None)
    scan = _ScanFinto()

    def _ciclo_una_volta_mutato(scan_):
        if False and AO.richiesto():  # noqa: SIM223 - MUTAZIONE riprodotta apposta
            return False
        scan_.tick()
        return True

    monkeypatch.setattr(S, "_ciclo_una_volta", _ciclo_una_volta_mutato)
    AO.richiedi()
    giri = {"n": 0}

    def _ciclo_breve(scan_):
        # il `while True` reale (`_ciclo_persistente`) chiamerebbe la mutata
        # per sempre: qui ci si ferma da soli dopo 3 giri (stesso tetto di
        # sicurezza degli altri test), la prova e' che il tick parte lo
        # stesso nonostante l'arresto attivo.
        while giri["n"] < 3:
            giri["n"] += 1
            if not S._ciclo_una_volta(scan_):
                return

    _ciclo_breve(scan)
    assert scan.tick_chiamate == 3, ("con la mutazione del coordinatore il tick parte "
                                      "SEMPRE, anche con l'arresto attivo")
    AO.cancella()


# ===========================================================================
# SAFE STRATEGY — BOT
# ===========================================================================
def test_safe_bot_ciclo_esce_entro_un_giro_con_arresto_fresco(cartella_arresto):
    from Betfair.safe_strategy import bot_service as S

    un_giro, chiamate = _giro_limitato()
    AO.richiedi()
    S._ciclo_persistente(un_giro, label="[safe.bot-test]")
    assert len(chiamate) == 0
    AO.cancella()


def test_safe_bot_ciclo_NON_esce_con_arresto_vecchio(cartella_arresto):
    from Betfair.safe_strategy import bot_service as S

    giri: List[int] = []

    def _un_giro() -> bool:
        giri.append(1)
        return len(giri) < 3

    _file_vecchio(cartella_arresto)
    S._ciclo_persistente(_un_giro, label="[safe.bot-test]")
    assert giri == [1, 1, 1]
    AO.cancella()


# ===========================================================================
# PONTE TENNIS (--bridge-only): _ensure_loop era GIA' isolata
# ===========================================================================
def _guardia_finta():
    return type("G", (), {"blocca_aperture": False})()


class _CicloNonFermato(BaseException):
    """Anti-hang: NON e' un ``Exception`` apposta, per non essere ingoiata
    dal ``try/except Exception`` che ``_ensure_loop`` mette attorno a
    ``riconcilia_interruttori()`` (e agli altri passi del giro)."""


def test_ponte_tennis_ciclo_esce_entro_un_giro_con_arresto_fresco(cartella_arresto, monkeypatch):
    from Betfair.stream.tennis_live import tennis_bot_service as S

    chiamate: List[str] = []
    stop = threading.Event()

    def _riconcilia_con_tetto():
        chiamate.append("riconcilia")
        if len(chiamate) > _TETTO_SICUREZZA:
            stop.set()
            raise _CicloNonFermato("il ponte non si e' fermato per l'arresto ordinato")

    monkeypatch.setattr(S, "_GUARDIA_AVVIO", _guardia_finta())
    monkeypatch.setattr(S, "ripresa_ponte", lambda: chiamate.append("ripresa"))
    monkeypatch.setattr(S, "ensure_follows_for_bots", lambda: chiamate.append("ensure"))
    monkeypatch.setattr(S, "riconcilia_interruttori", _riconcilia_con_tetto)
    # ENSURE_POLL_SEC (15s) e' un'attesa VERA (stop.wait): fuori gioco nel
    # test, altrimenti anche solo 2-3 giri appenderebbero il test per decine
    # di secondi PRIMA che il tetto di sicurezza scatti.
    monkeypatch.setattr(S, "_dormi_o_sveglia", lambda _stop: None)
    AO.richiedi()
    S._ensure_loop(stop)
    assert chiamate == [], "nessuna chiamata del giro: l'arresto e' controllato PRIMA"
    assert not stop.is_set(), "e' uscito col break, non con stop.set() (nessuna KeyboardInterrupt)"
    AO.cancella()


def test_ponte_tennis_ciclo_NON_esce_con_arresto_vecchio(cartella_arresto, monkeypatch):
    from Betfair.stream.tennis_live import tennis_bot_service as S

    conteggio = {"n": 0}
    stop = threading.Event()
    monkeypatch.setattr(S, "_GUARDIA_AVVIO", _guardia_finta())
    monkeypatch.setattr(S, "ripresa_ponte", lambda: None)
    monkeypatch.setattr(S, "ensure_follows_for_bots", lambda: None)

    def _riconcilia_poi_stop():
        conteggio["n"] += 1
        if conteggio["n"] >= 2:
            stop.set()  # mai un test appeso: si ferma da sola dopo 2 giri

    monkeypatch.setattr(S, "riconcilia_interruttori", _riconcilia_poi_stop)
    # F5/F6: niente attesa vera nel test (vedi il test sopra).
    monkeypatch.setattr(S, "_dormi_o_sveglia", lambda _stop: None)
    _file_vecchio(cartella_arresto)
    S._ensure_loop(stop)
    assert conteggio["n"] == 2, "il ciclo e' proseguito col file vecchio, fermato da stop.set()"
    AO.cancella()


# ===========================================================================
# SCALPER-SERVICE: il guscio (_ciclo_supervisore) con le tre parti iniettate
# ===========================================================================
def test_scalper_ciclo_supervisore_ferma_e_non_esegue_un_giro():
    from Betfair.stream.scalper import scalper_service as S

    chiamate: List[str] = []

    def _un_giro_con_tetto() -> None:
        chiamate.append("giro")
        if chiamate.count("giro") > _TETTO_SICUREZZA:
            raise AssertionError("il supervisore ha eseguito un giro col kill-switch tirato")

    S._ciclo_supervisore(
        deve_fermarsi_kill_switch=lambda: True,
        ferma_per_kill_switch=lambda: chiamate.append("ferma"),
        un_giro=_un_giro_con_tetto,
    )
    assert chiamate == ["ferma"], "col kill-switch tirato: SOLO ferma, MAI un giro"


def test_scalper_ciclo_supervisore_esegue_i_giri_finche_non_si_ferma():
    from Betfair.stream.scalper import scalper_service as S

    giri = {"n": 0}

    def _deve_fermarsi() -> bool:
        return giri["n"] >= 3

    def _un_giro() -> None:
        giri["n"] += 1
        if giri["n"] > _TETTO_SICUREZZA:
            raise AssertionError("il supervisore non si e' mai fermato")

    chiamate: List[str] = []
    S._ciclo_supervisore(
        deve_fermarsi_kill_switch=_deve_fermarsi,
        ferma_per_kill_switch=lambda: chiamate.append("ferma"),
        un_giro=_un_giro,
    )
    assert giri["n"] == 3
    assert chiamate == ["ferma"], "dopo 3 giri il kill-switch scatta e ferma UNA volta sola"


def test_scalper_ferma_per_kill_switch_termina_solo_chi_non_esce_da_solo():
    """``attendi_e_termina_flat`` VERA (la usa il ramo kill-switch di
    ``main()``, non una sua copia): un figlio che esce da solo entro la
    finestra NON viene terminato; uno che resta vivo SI'."""
    from Betfair.stream.scalper import scalper_service as S

    class _PopenFinto:
        def __init__(self, esce_al_giro: int) -> None:
            self._esce_al_giro = esce_al_giro
            self._giro = 0
            self.terminato = False

        def poll(self):
            self._giro += 1
            return 0 if self._giro >= self._esce_al_giro else None

        def terminate(self) -> None:
            self.terminato = True

    buono = _PopenFinto(esce_al_giro=1)       # esce al primo controllo
    testardo = _PopenFinto(esce_al_giro=999)  # non esce mai entro la finestra
    children = {"buono": buono, "testardo": testardo}

    orologio = {"t": 1000.0}
    S.attendi_e_termina_flat(
        children,
        deadline_s=60.0,
        now=lambda: orologio["t"],
        sleep=lambda _s: orologio.__setitem__("t", orologio["t"] + 2.0),
    )

    assert buono.terminato is False, "il figlio uscito da solo NON va terminato"
    assert testardo.terminato is True, "il figlio rimasto vivo va terminato allo scadere"
    assert "buono" not in children and "testardo" in children


def test_scalper_ferma_per_kill_switch_non_termina_nessuno_se_tutti_escono_subito():
    from Betfair.stream.scalper import scalper_service as S

    class _PopenFintoEsceSubito:
        def __init__(self) -> None:
            self.terminato = False

        def poll(self):
            return 0

        def terminate(self) -> None:
            self.terminato = True

    a, b = _PopenFintoEsceSubito(), _PopenFintoEsceSubito()
    children = {"a": a, "b": b}
    sleeps: List[float] = []
    S.attendi_e_termina_flat(children, now=lambda: 1000.0, sleep=sleeps.append)
    assert children == {}
    assert a.terminato is False and b.terminato is False
    # un solo giro di attesa (pop-poi-sleep e' un blocco unico): la prossima
    # verifica del `while children` trova il dict gia' vuoto e si ferma.
    assert len(sleeps) == 1, "un solo giro: erano gia' tutti usciti al primo controllo"
