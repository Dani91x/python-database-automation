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
def _ripristina_ref_di_strategia_omega_market():
    """02/10 (isolamento, ``AUDIT_2026-10-02/TEST_ISOLAMENTO.md``):
    ``omega_market.CUSTOMER_STRATEGY_REF`` e' una costante di MODULO che Mike
    RILEGA a ``"mike"`` scrivendoci sopra direttamente
    (``Betfair/mike/service.py:133``, ``_RealMarket._bind_strategy_ref``,
    chiamata da place/cancel/list_current_orders/list_cleared_orders dello
    sportello di Mike). In produzione Mike e' un processo a se' e non serve
    ripristinarla; in una sessione pytest resta ``"mike"`` per tutti i test
    dopo. Riprodotto: ``Betfair/mike/tests/test_mike_p4_ordini_2026_09_29.py::
    test_rilettura_alla_riapertura_con_lo_sportello_vero`` (e
    ``test_sospensione_e_riapertura_in_live_dice_cancellata_da_betfair``) prima
    di ``Betfair/omega/tests/test_ref_strategia_per_attore_r1_2026_09_24.py::
    test_omega_piazza_con_omega_come_prima`` -> Omega piazza con ``"mike"``.

    Si ripristina dopo ogni test il valore che aveva prima (o, se il modulo e'
    stato importato durante il test, il ref di Omega fissato all'import,
    ``omega_market._REF_OMEGA``). Non importa il modulo se nessuno l'ha gia'
    importato."""
    _nome = "Betfair.omega.omega_market"
    _om = sys.modules.get(_nome)
    _prima = getattr(_om, "CUSTOMER_STRATEGY_REF", None) if _om is not None else None
    yield
    _om = sys.modules.get(_nome)
    if _om is None:
        return
    _valore = _prima if _prima is not None else getattr(_om, "_REF_OMEGA", None)
    if _valore is not None:
        _om.CUSTOMER_STRATEGY_REF = _valore


@pytest.fixture(autouse=True)
def _svuota_cache_lambda_di_omega():
    """02/10 (isolamento 2, ``AUDIT_2026-10-02/TEST_ISOLAMENTO_2.md``):
    ``omega_service._LAMBDA_CACHE`` (``Betfair/omega/omega_service.py:1000``) e'
    la cache di PROCESSO dei lambda pre-match per ``event_id``, riempita da
    ``_prematch_lambdas`` (:1238) e letta per prima (:1143). La usa anche Safe:
    ``safe_strategy/bot_service.resolve_event_lambdas`` (:7220) chiama per primo
    anello la catena di Omega. ``omega_service.svuota_le_cache`` non la svuota e
    nessuna fixture lo faceva a fine test: un test di Omega che risolve i lambda
    di ``"e1"`` (es. ``Betfair/omega/test_omega_greenup_2026_09_10.py::
    test_trigger_gol_esce_dopo_assestamento_e_marca_le_due_righe``) lasciava
    ``"e1"`` in cache, e ``safe_strategy/tests/test_audit_2026_09_11.py::
    test_l14_ttl_della_cache_lambda`` (stesso ``event_id``) trovava i lambda di
    Omega invece di rifare la sua catena: rosso solo dopo quel file.

    Svuotata a fine test se il modulo e' gia' importato (mai importato da qui)."""
    yield
    _os = sys.modules.get("Betfair.omega.omega_service")
    _cache = getattr(_os, "_LAMBDA_CACHE", None) if _os is not None else None
    if isinstance(_cache, dict):
        _cache.clear()


_DB_CLIENT_STATO_DI_IMPORT = {"timeout": None}


@pytest.fixture(autouse=True)
def _ripristina_stato_di_processo_di_db_client():
    """02/10 (isolamento 4, ``AUDIT_2026-10-02/TEST_ISOLAMENTO_4.md``):
    ``db_client._STATO`` (``db_client.py:33``) e' lo stato di PROCESSO del
    timeout PostgREST; ``usa_timeout_bot`` (``db_client.py:59-67``) ci scrive
    il profilo bot e nessuno lo rimette a ``None``: in produzione e' giusto (lo
    chiama il ``main`` di un bot una volta per processo), in pytest no. Il
    ``main`` VERO di Mike (``Betfair/mike/service.py:7371``) lo chiama, e
    ``Betfair/mike/tests/test_mike_riga_assente_e_arresto_2026_10_02.py::
    test_R1_main_all_arresto_chiama_l_arresto_degli_ordini`` esegue ``S.main()``
    due volte: da li' in poi ``get_supabase_client`` chiamava
    ``create_client(url, key, options=...)`` (``db_client.py:83-84``) e
    ``Betfair/stream/tests/test_net_retry.py::test_db_client_is_per_thread``
    (finto ``create_client(url, key)``) cadeva con ``TypeError: unexpected
    keyword argument 'options'``: rosso solo dopo quel file.

    Fotografa (se il modulo e' gia' importato; mai importato da qui) l'oggetto
    ``_STATO`` col suo contenuto, l'oggetto ``_TLS`` e il contenuto di ``_TLS``
    del thread del test, e li rimette a fine test. Se il modulo e' stato
    importato DURANTE il test, ``_STATO`` torna allo stato di import (``None``)."""
    _mod = sys.modules.get("db_client")
    if _mod is not None:
        _stato = getattr(_mod, "_STATO", None)
        _stato_contenuto = dict(_stato) if isinstance(_stato, dict) else None
        _tls = getattr(_mod, "_TLS", None)
        _tls_contenuto = dict(vars(_tls)) if _tls is not None else None
    yield
    _dopo = sys.modules.get("db_client")
    if _dopo is None:
        return
    if _mod is None or _dopo is not _mod:
        _s = getattr(_dopo, "_STATO", None)
        if isinstance(_s, dict):
            _s.clear()
            _s.update(_DB_CLIENT_STATO_DI_IMPORT)
        return
    if isinstance(_stato, dict):
        _stato.clear()
        _stato.update(_stato_contenuto)
        _mod._STATO = _stato
    if _tls is not None:
        vars(_tls).clear()
        vars(_tls).update(_tls_contenuto)
        _mod._TLS = _tls


@pytest.fixture(autouse=True)
def _nessun_dotenv_a_meta_test(monkeypatch):
    """02/10 (isolamento 2): nessun ``load_dotenv()`` durante un test.

    ``Betfair/stream/config_stream.py:16-17`` (e gli altri moduli che fanno
    ``from dotenv import load_dotenv`` all'import) rileggono il ``.env`` VERO del
    checkout principale la prima volta che vengono importati — o ricaricati con
    ``importlib.reload``. ``load_dotenv`` riempie solo le variabili ASSENTI:
    un test che ha appena fatto ``monkeypatch.delenv(X)`` per provare il
    comportamento "variabile assente" se la vedeva rimettere col valore del
    ``.env`` se quell'import capitava dentro il test (reperto del 02/10 su
    ``test_l4``, vedi ``TEST_ISOLAMENTO.md``). I test che provano proprio
    l'ASSENZA (``..._di_serie_e_spento``, ``valore=None``, default di
    ``LIVE_ORDER_MODE``/``LIVE_LADDER_CANALE_MS``) non possono passare a
    ``setenv``: questa fixture li protegge tutti. Gli import fatti alla RACCOLTA
    (prima delle fixture) restano come sono: il loro effetto e' gia' coperto da
    ``_ambiente_neutro_canali_e_db``."""
    try:
        import dotenv as _dotenv
    except Exception:  # noqa: BLE001 - dotenv assente: niente da neutralizzare
        yield
        return
    _vero = _dotenv.load_dotenv

    def _solo_con_percorso(dotenv_path=None, *a, **k):
        # neutralizzata SOLO la ricerca automatica del .env vero (chiamata senza
        # percorso, come ``config_stream``); un test che passa un .env FINTO
        # col suo percorso (``test_banco_ambiente_dichiarato_2026_10_02.py``)
        # usa la funzione vera, cosi' resta capace di diventare rosso
        if dotenv_path:
            return _vero(dotenv_path, *a, **k)
        return False

    monkeypatch.setattr(_dotenv, "load_dotenv", _solo_con_percorso)
    yield


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
