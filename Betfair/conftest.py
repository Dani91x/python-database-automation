# -*- coding: utf-8 -*-
"""Marcatori della suite Betfair.

``cert`` — i test che fanno girare il BANCO COMUNE (replay flumine sulle
registrazioni reali) su un campione ridotto, per ogni bot registrato. Stanno
nella suite di default proprio perche' una modifica a un bot deve rilanciare la
sua certificazione senza che nessuno se lo ricordi; per isolarli:

    python -m pytest Betfair/ -q -m cert          # solo la certificazione
    python -m pytest Betfair/ -q -m "not cert"    # tutto il resto
"""
from __future__ import annotations

import sys

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "cert: certificazione sul banco comune (replay flumine su registrazioni reali)",
    )


@pytest.fixture(autouse=True)
def _ripristina_flumine_config():
    """R-4 (25/09, ``AUDIT_2026-09-25/TENNIS_UNIFICAZIONE_E_SAFE_CANALE.md``):
    ``flumine.config`` e' un MODULO, cioe' uno stato GLOBALE DI PROCESSO — non per
    istanza — e diversi punti di produzione ci scrivono direttamente senza mai
    ripristinare (perche' in produzione non serve: un solo bot, una sola modalita',
    per tutta la vita del processo):

        Betfair/stream/tennis_live/tennis_runner.py:159   build_order_client(PAPER)
            imposta ``flumine_config.place_latency = TENNIS_PAPER_LATENCY_MS/1000``
            (default 600 ms).
        Betfair/stream/tennis_live/guardie_tennis.py:178  stessa scrittura, stesso
            campo, dalle guardie a caldo.
        Betfair/stream/runner.py:1537 e :1580              lo stesso per il runner
            calcio (PAPER_SIMULATED_LATENCY_MS).

    Un test che fa girare questo codice di produzione (es.
    ``Betfair/stream/tennis_live/tests/test_tennis_iscrizione_a_caldo_2026_09_25.py``)
    lascia ``place_latency = 0.6`` per TUTTO il processo pytest. Il test successivo
    che si aspetta il default di flumine (0.12) — es.
    ``Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py::
    test_profilo_rapido_verde_sulla_registrazione_vera[omega]``, che passa dal
    profilo rapido del banco comune e confronta i tempi attesi contro
    ``place_latency + betDelay`` — vede una latenza diversa da quella con cui e'
    stato scritto e cade. Da solo e' verde perche' nessuno ha ancora toccato
    ``flumine.config`` in quella sessione.

    Riprodotto a comando (falsificato disattivando questa fixture, vedi
    ``AUDIT_2026-09-25/FIX_R4_STATO_GLOBALE_TEST.md``):

        python -m pytest \
          Betfair/stream/tennis_live/tests/test_tennis_iscrizione_a_caldo_2026_09_25.py \
          "Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py::test_profilo_rapido_verde_sulla_registrazione_vera[omega]" \
          -q -p no:cacheprovider

    Fotografa TUTTI gli attributi pubblici di ``flumine.config`` prima di ogni test
    e li ripristina dopo: nessun test — tennis, calcio o altro — puo' piu' sporcare
    quello che gira dopo di lui nella stessa sessione pytest. Scritture dirette su
    ``flumine.config`` (come quelle sopra) NON passano da ``monkeypatch`` — restano
    finche' qualcosa non le tocca di nuovo — quindi solo uno snapshot/ripristino
    esplicito del modulo le neutralizza."""
    import flumine.config as _fconf

    _prima = {
        _nome: getattr(_fconf, _nome)
        for _nome in vars(_fconf)
        if not _nome.startswith("__")
    }
    yield
    for _nome, _valore in _prima.items():
        setattr(_fconf, _nome, _valore)


@pytest.fixture(autouse=True)
def _kill_switch_del_db_senza_rete(monkeypatch):
    """O1 (24/09): ``controls.motivo_kill_switch`` legge anche
    ``betfair_live_settings`` (RPC, cache 2 s). Nei test la rete non c'e'
    (SUPABASE_URL finto): senza questo ogni apertura REST pagherebbe ~2 s di
    connessione rifiutata. Lo snapshot resta quello "mai letto" ({}), cioe'
    esattamente cio' che il codice vedrebbe con il DB irraggiungibile; chi
    collauda il freno del DB lo imposta da se' (monkeypatch di
    ``get_live_settings`` o della cache). Non importa ``controls`` se nessuno
    l'ha gia' importato: nessun modulo pesante entra per colpa di questo."""
    ctl = sys.modules.get("Betfair.stream.trading.controls")
    if ctl is not None and hasattr(ctl, "_SETTINGS_CACHE"):
        monkeypatch.setitem(ctl._SETTINGS_CACHE, "data", {})
        monkeypatch.setitem(ctl._SETTINGS_CACHE, "ts", float("inf"))
    yield


# ---------------------------------------------------------------------------
# CANTIERE M (28/09) — la suite non dipende da cosa c'e' nel .env VERO del PC
# ---------------------------------------------------------------------------
#: i 20 interruttori di produzione che oggi (dal 26/09) il ``.env`` vero del
#: checkout principale accende (``=1``). Stessa lista usata dal cantiere C per
#: falsificare Omega (``AUDIT_2026-09-28/cantiere_c/falsifica_c.py``,
#: ``INTERRUTTORI``). ``load_dotenv()`` in produzione risale le cartelle e
#: trova quel ``.env`` anche da un worktree: senza questa fixture, il
#: verde/rosso della suite dipende da cosa e' scritto li' — reperto del 28/09,
#: vedi ``AUDIT_2026-09-28/CANTIERE_M_TEST_E_AMBIENTE.md``: con gli
#: interruttori accesi 111 test di Omega erano rossi sulla base (tutti e soli
#: dipendenti da ``OMEGA_ORDINI_VIA_CANALE``).
INTERRUTTORI_CANALE = (
    "SAFE_SCAN_CANALE", "MIKE_CANALE_POSIZIONI", "OMEGA_CANALE_POSIZIONI",
    "SAFE_CANALE_POSIZIONI", "TENNIS_BOT_CANALE", "SAFE_BOT_LEGGE_CANALE",
    "SAFE_BOT_SVEGLIA_CANALE", "OMEGA_SVEGLIA_CANALE", "MIKE_SVEGLIA_CANALE",
    "TENNIS_BOT_SVEGLIA_CANALE", "MIKE_LEGGE_CANALE", "OMEGA_LEGGE_CANALE",
    "PUNTEGGI_CANALE", "ESITI_ORDINI_CANALE", "MOTORE_ORDINI_CANALE", "SCALPER_CANALE",
    "SAFE_ORDINI_VIA_CANALE", "OMEGA_ORDINI_VIA_CANALE", "MOTORE_ORDINI_CANALE_TENNIS",
    "SAFE_TENNIS_ORDINI_VIA_CANALE",
)

#: chiavi Supabase finte: STESSA chiave, STESSO valore in ogni test, cosi' un
#: test che se le scambia per errore fallisce in modo riconoscibile (non un
#: 403 casuale contro un progetto vero). Mai una sotto-stringa di una chiave
#: vera: sono lette da chi certifica per riconoscerle a colpo d'occhio.
SUPABASE_URL_FINTO = "https://finto-non-esiste.invalid"
SUPABASE_KEY_FINTA = "finta-chiave-di-test-mai-una-chiave-vera"


@pytest.fixture(autouse=True)
def _ambiente_neutro_canali_e_db(monkeypatch):
    """Ogni test parte da un ambiente NEUTRO e DICHIARATO, qualunque cosa dica
    il ``.env`` vero del PC:

    1) i 20 interruttori dei canali di produzione SPENTI di serie (``=0``: il
       ``VALORI_ACCESI`` di ``Betfair/safe_strategy/porta_ordini.py`` accetta
       solo ``1``/``true``/``si``/``yes``, quindi ``0`` e' spento per
       costruzione). Il test che vuole un interruttore acceso lo accende da
       se' con ``monkeypatch.setenv(nome, "1")`` DOPO questa fixture (l'ultima
       scrittura vince: l'ordine dei fixture autouse non conta, l'ordine di
       ESECUZIONE si', e il corpo del test gira sempre dopo il setup).

    2) le chiavi Supabase finte di serie (``SUPABASE_URL``,
       ``SUPABASE_SERVICE_ROLE_KEY``, ``SUPABASE_KEY``): nessun test puo' piu'
       raggiungere il DB vero per via del ``.env`` risalito da
       ``load_dotenv()``. Non basta l'``env``: ``config.py`` legge
       ``SUPABASE_URL``/``SUPABASE_SERVICE_ROLE_KEY`` all'IMPORT
       (``SUPABASE_URL = os.getenv(...)``) e diversi moduli le importano con
       ``from config import SUPABASE_URL, ...`` — un binding di modulo
       COPIATO all'import, che un ``monkeypatch.setenv`` fatto dopo non
       raggiunge piu' (``db_client.py``, ``api_client.py``,
       ``Betfair/client.py``, ``Betfair/stream/auth.py``,
       ``Betfair/stream/tennis_live/tennis_db.py`` e altri: la lista cresce,
       quindi si ripassano TUTTI i moduli gia' importati, non un elenco fisso
       che invecchia). Per ogni modulo gia' in ``sys.modules`` con questi nomi
       come attributo, si sovrascrive anche l'attributo. I due test che oggi
       usano il DB vero SE raggiungibile (``test_analytics_market_stats.py::
       test_cert_delay_shift_vs_rpc`` e ``test_cert_freq_shift_vs_rpc``, via
       ``_try_db()``) degradano da soli: ``sb is None`` -> ``return`` senza
       asserzioni, restano verdi."""
    for _nome in INTERRUTTORI_CANALE:
        monkeypatch.setenv(_nome, "0")

    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL_FINTO)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_KEY_FINTA)
    monkeypatch.setenv("SUPABASE_KEY", SUPABASE_KEY_FINTA)
    for _modulo in list(sys.modules.values()):
        if _modulo is None:
            continue
        if getattr(_modulo, "SUPABASE_URL", None):
            monkeypatch.setattr(_modulo, "SUPABASE_URL", SUPABASE_URL_FINTO, raising=False)
        for _chiave in ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_KEY"):
            if getattr(_modulo, _chiave, None):
                monkeypatch.setattr(_modulo, _chiave, SUPABASE_KEY_FINTA, raising=False)
    yield
