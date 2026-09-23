"""d2 (24/09) - `bot_service.svuota_le_cache()`: contratto ed enumerazione.

Stesso schema di
`Betfair/omega/test_omega_consapevolezza_2026_09_16.py:234-297`
(`test_ogni_cache_di_processo_e_nell_elenco_di_svuota_le_cache` +
`test_svuota_le_cache_svuota_davvero`): in PRODUZIONE l'azzeramento resta un
elenco scritto a mano (`bot_service.svuota_le_cache`), mai un `dir()` — una
cancellazione per riflessione butterebbe via anche cio' che non e' una cache
(`_FEED_BLOCK_BY_TYPE`, configurazione statica). Qui, nel TEST, si usa invece
la riflessione apposta per accorgersi che qualcuno ha aggiunto una cache NUOVA
e si e' scordato di metterla nell'elenco esplicito (difetto 37 del catalogo:
la pool di replay non isolava gli scenari, e i controlli di uno scenario
venivano sollecitati meno del dovuto).

Nessuna rete, nessun Supabase, nessun processo. ASCII-only.
"""
from __future__ import annotations

import inspect
import threading

import pytest

from Betfair.safe_strategy import bot_service as S

# Nomi module-level che SEMBRANO una cache di processo (dict/set/list/
# threading.Event) ma non lo sono: configurazione STATICA, mai mutata a
# runtime. Dichiarati uno per uno, non esclusi in silenzio: se uno di questi
# comincia a essere mutato altrove nel modulo e' un reperto da riportare al
# coordinatore, non un motivo per rendere il test piu' permissivo.
_NON_CACHE_DICHIARATE = frozenset({
    "_FEED_BLOCK_BY_TYPE",   # mappa STATICA market_type -> campi bloccati
})


@pytest.fixture(autouse=True)
def _pulizia():
    """Ogni test parte e finisce con le cache di modulo azzerate: usa la
    stessa funzione che sta certificando (come `omega/conftest.py:69`)."""
    S.svuota_le_cache()
    yield
    S.svuota_le_cache()


def _nomi_maiuscoli_di_modulo(mod):
    """I nomi PRIVATI e TUTTO MAIUSCOLO del modulo: la convenzione delle
    costanti e delle cache di processo in `bot_service.py`."""
    for nome in dir(mod):
        if not nome.startswith("_"):
            continue
        corpo = nome[1:]
        if not corpo or corpo != corpo.upper():
            continue
        yield nome


def _stato_cache():
    """{nome: lunghezza|"evento"} per ogni variabile module-level che e'
    DAVVERO una cache di processo (dict/set/list/threading.Event), esclusa
    la configurazione statica dichiarata sopra."""
    fuori = {}
    for nome in _nomi_maiuscoli_di_modulo(S):
        if nome in _NON_CACHE_DICHIARATE:
            continue
        val = getattr(S, nome)
        if isinstance(val, threading.Event):
            fuori[nome] = "evento"
        elif isinstance(val, (dict, set, list)):
            fuori[nome] = len(val)
    return fuori


def test_ogni_cache_di_processo_e_nell_elenco_di_svuota_le_cache():
    """Ogni nome che SEMBRA una cache dev'essere citato in `svuota_le_cache`."""
    sorgente = inspect.getsource(S.svuota_le_cache)
    mancanti = [n for n in _stato_cache() if n not in sorgente]
    assert not mancanti, (
        "cache di processo non azzerate da `svuota_le_cache` (passerebbero da "
        f"uno scenario del banco all'altro): {sorted(mancanti)}")


def test_svuota_le_cache_svuota_davvero():
    """FALSIFICAZIONE: si sporca ogni cache e si pretende che torni allo
    stato INIZIALE - vuoto per le une, le CHIAVI FISSE per le altre: a
    differenza di Omega, non tutte le cache di questo modulo nascono vuote
    (``_APERTE`` e' sempre ``{"n": 0}``, mai ``{}``), quindi il confronto e'
    contro lo stato di partenza catturato, non contro lunghezza zero.

    Chi ha gia' delle chiavi (gruppo CHIAVI FISSE) viene sporcato cambiando
    il VALORE di una chiave ESISTENTE, non aggiungendone una sconosciuta: e'
    il modo in cui il codice di produzione le tocca davvero (nessun punto del
    modulo scrive una chiave che lo schema non dichiara)."""
    iniziali: dict = {}
    sporcate = []
    for nome in _stato_cache():
        val = getattr(S, nome)
        if isinstance(val, threading.Event):
            iniziali[nome] = False
            val.set()
        elif isinstance(val, dict):
            iniziali[nome] = dict(val)
            if val:
                k = next(iter(val))
                val[k] = "__sporcata__"
            else:
                val["__prova__"] = 1
        elif isinstance(val, set):
            iniziali[nome] = set(val)
            val.add("__prova__")
        elif isinstance(val, list):
            iniziali[nome] = list(val)
            val.append("__prova__")
        sporcate.append(nome)
    assert sporcate, "nessuna cache trovata: il test non proverebbe niente"
    S.svuota_le_cache()
    rimaste = []
    for nome in sporcate:
        val = getattr(S, nome)
        attuale = val.is_set() if isinstance(val, threading.Event) else val
        if attuale != iniziali[nome]:
            rimaste.append(nome)
    assert not rimaste, f"cache NON tornate allo stato iniziale: {rimaste}"


def test_svuota_le_cache_richiama_azzera_canale_scan():
    """d2: le quattro cache F4/F6 del canale locale (_CANALE_SCAN, _SVEGLIA,
    _CONTI_SVEGLIA, _ULTIMO_GIRO) devono tornare come dopo un vero
    `azzera_canale_scan()`, non un doppione della sua logica."""
    S._CANALE_SCAN["avviato"] = True
    S._SVEGLIA.set()
    S._CONTI_SVEGLIA["sveglie"] = 7
    S._ULTIMO_GIRO["mono"] = 123.0
    S.svuota_le_cache()
    assert S._CANALE_SCAN["avviato"] is False
    assert S._SVEGLIA.is_set() is False
    assert S._CONTI_SVEGLIA == {"sveglie": 0, "rifiutate": 0, "installata": False}
    assert S._ULTIMO_GIRO == {"mono": 0.0}


@pytest.mark.xfail(
    strict=True,
    reason="REPERTO (d2, 24/09), NON corretto: fuori dal mio perimetro "
           "append-only. azzera_canale_scan() (bot_service.py:7136, codice "
           "ESISTENTE, non toccato) fa .update({...}) su _CANALE_SCAN, "
           "_CONTI_SVEGLIA e _ULTIMO_GIRO SENZA un .clear() prima: una "
           "chiave che non e' nello schema dichiarato sopravvive a "
           "svuota_le_cache()/azzera_canale_scan(). In produzione non si "
           "vede mai (il modulo scrive solo le chiavi dello schema), ma un "
           "banco di replay che iniettasse per errore una chiave fuori "
           "schema in una di queste tre non la vedrebbe piu' sparire. Il "
           "coordinatore ha chiesto di RIUSARE azzera_canale_scan() com'e', "
           "non di duplicarne/correggerne la logica: questo test documenta "
           "il reperto invece di nasconderlo dietro una falsificazione piu' "
           "permissiva.")
def test_reperto_azzera_canale_scan_non_purga_chiavi_fuori_schema():
    try:
        S._CONTI_SVEGLIA["__chiave_non_nello_schema__"] = 1
        S.svuota_le_cache()
        assert S._CONTI_SVEGLIA == {"sveglie": 0, "rifiutate": 0, "installata": False}
    finally:
        # svuota_le_cache()/azzera_canale_scan() non possono togliere questa
        # chiave (e' il reperto): la si toglie qui a mano, altrimenti
        # sopravvivrebbe a QUALUNQUE azzeramento successivo per il resto
        # della sessione di test (stato di MODULO condiviso).
        S._CONTI_SVEGLIA.pop("__chiave_non_nello_schema__", None)


def test_svuota_le_cache_ripristina_le_chiavi_fisse_senza_keyerror():
    """Le cache a CHIAVI FISSE (lette senza `.get` in giro per il modulo) non
    devono tornare un dict VUOTO: un `.clear()` nudo produrrebbe un
    `KeyError` al giro dopo (`_APERTE["n"]`, `_LOG_MODE["value"]`...)."""
    S._REST_STATE["used"] = 99
    S._APERTE["n"] = 5
    S._BLOCCO["motivo"] = "test"
    S._LOG_MODE["value"] = "x"
    S._CICLO_IN_ERRORE["value"] = True
    S.svuota_le_cache()
    assert S._REST_STATE == {"last": {}, "cycle_ts": 0.0, "used": 0}
    assert S._APERTE == {"n": 0}
    assert S._BLOCCO == {"motivo": None, "tetto": None, "aperte": None}
    assert S._LOG_MODE == {"value": ""}
    assert S._CICLO_IN_ERRORE == {"value": False}
