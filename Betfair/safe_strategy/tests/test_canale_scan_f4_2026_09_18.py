"""F4 (18/09) - il bot Safe legge le righe dello scanner dal canale locale.

Che cosa inchioda questo file:
  * con l'interruttore ASSENTE il bot non apre nessun client e legge dal
    database a ogni ciclo, con le STESSE chiamate di oggi (contate);
  * una riga del canale non ha NESSUN privilegio: piu' vecchia del database
    perde, senza ``odds_ts_ms`` perde, stantia si ripiega sul database;
  * il canale non puo' AGGIUNGERE una partita;
  * canale giu' o client che solleva: il ciclo prosegue identico;
  * la sveglia anticipa un giro ma mai sotto i 250 ms;
  * un messaggio di sveglia con dentro campi d'ordine non porta nessun ordine.

I finti hanno le chiavi IDENTICHE alle righe vere di ``safe_strategy_scan``
(``event_id``, ``sport``, ``payload``, ``updated_at``): si parte da
``_feed_row`` del file dei test del bot, che e' lo stesso finto gia' in uso.

Nessuna rete, nessun Supabase, nessun processo. File ASCII-only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from datetime import timedelta

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import canale_scan as CS
from Betfair.safe_strategy import exits as XE
from Betfair.safe_strategy.tests.test_bot_service import (
    NOW, FakeDB, FakeEngine, FakeMarket, _feed_row, _reset_module_state,
)
from Betfair.stream import local_channel as LC


@pytest.fixture(autouse=True)
def _pulizia(monkeypatch):
    """Ogni test parte a interruttori SPENTI e senza stato di modulo."""
    monkeypatch.delenv(CS.ENV_LEGGE_CANALE, raising=False)
    monkeypatch.delenv(CS.ENV_SVEGLIA, raising=False)
    monkeypatch.delenv(CS.ENV_PORTA, raising=False)
    S.azzera_canale_scan()
    _reset_module_state()
    yield
    S.azzera_canale_scan()
    _reset_module_state()


# ---------------------------------------------------------------------------
# Finti: la riga del canale e' la riga del database
# ---------------------------------------------------------------------------
def _riga_canale(event_id="1.1", secondi=0.0, odds_ts_ms=1_700_000_000_000,
                 back=3.0, lay=3.1):
    """La riga come esce dal topic ``scan_calcio``: STESSE chiavi del database.

    L'unica differenza ammessa e' il valore, mai la forma: se questo finto
    divergesse dalla riga vera, certificherebbe un bug (15/09).
    """
    riga = _feed_row(event_id=event_id, back=back, lay=lay,
                     updated_at=NOW + timedelta(seconds=secondi))
    if odds_ts_ms is not None:
        riga["payload"]["odds_ts_ms"] = int(odds_ts_ms)
    return riga


class ContaDB(FakeDB):
    """FakeDB che CONTA le letture del feed: e' la misura del "letture DB"."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.letture_feed = 0

    def fetch_scan_rows(self):
        self.letture_feed += 1
        return list(self.scan_rows)


def _accendi(monkeypatch, cache):
    monkeypatch.setenv(CS.ENV_LEGGE_CANALE, "1")
    S._CANALE_SCAN.update({"cache": cache, "avviato": True, "client": None})


def _giro(db, engine=None, now=NOW):
    return S.run_once(db=db, market=FakeMarket(), engine=engine or FakeEngine(),
                      now=now)


# ---------------------------------------------------------------------------
# 1. Il modulo e' PURO e i topic sono quelli del produttore
# ---------------------------------------------------------------------------
def test_canale_scan_e_un_modulo_puro():
    """Nessun flumine, nemmeno per via transitiva (invariante B1).

    Sottoprocesso VERO: un ``sys.modules`` gia' sporco dagli altri test non
    puo' far passare questo controllo per sbaglio.
    """
    codice = (
        "import sys;"
        "import Betfair.safe_strategy.canale_scan as CS;"
        "sporchi=[m for m in sys.modules if m.split('.')[0] in "
        "('flumine','betfairlightweight','supabase','websockets')];"
        "print('SPORCHI=' + ','.join(sorted(sporchi)));"
        "assert not sporchi, sporchi"
    )
    res = subprocess.run([sys.executable, "-c", codice], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr


def test_i_topic_sono_gli_stessi_del_produttore():
    """Una stringa scritta due volte diverge sempre (catalogo par.7.33)."""
    from Betfair.safe_strategy import service as SV

    assert dict(CS.TOPIC_SCAN) == dict(SV._TOPIC_SCAN)
    assert CS.TOPIC_SCANNER_STATO == SV._TOPIC_SCANNER_STATO
    assert CS.TOPIC_SCAN_NOMI == frozenset(SV._TOPIC_SCAN.values())
    assert CS.PORTA_SCAN == SV._PORTA_CANALE_SCAN
    assert CS.ENV_PORTA == SV._PORTA_CANALE_ENV


@pytest.mark.parametrize("valore", ["", " ", "0", "no", "false", "spento", "2"])
def test_senza_env_scritto_gli_interruttori_sono_spenti(monkeypatch, valore):
    monkeypatch.setenv(CS.ENV_LEGGE_CANALE, valore)
    monkeypatch.setenv(CS.ENV_SVEGLIA, valore)
    assert CS.acceso(CS.ENV_LEGGE_CANALE) is False
    assert CS.acceso(CS.ENV_SVEGLIA) is False


@pytest.mark.parametrize("valore", ["1", "true", "TRUE", "si", "yes"])
def test_con_lenv_scritto_gli_interruttori_sono_accesi(monkeypatch, valore):
    monkeypatch.setenv(CS.ENV_LEGGE_CANALE, valore)
    assert CS.acceso(CS.ENV_LEGGE_CANALE) is True


# ---------------------------------------------------------------------------
# 2. La cache: che cosa entra e che cosa no
# ---------------------------------------------------------------------------
def test_una_riga_senza_payload_non_entra():
    c = CS.CacheScan()
    assert c.aggiorna({"event_id": "1.1", "sport": "calcio",
                       "updated_at": NOW.isoformat()}) is False
    assert c.aggiorna({"sport": "calcio", "payload": {},
                       "updated_at": NOW.isoformat()}) is False
    assert c.aggiorna("non sono una riga") is False
    assert c.stato()["righe"] == 0 and c.stato()["scartate"] == 3


def test_una_riga_senza_updated_at_non_entra():
    """Senza istante non si sa se e' piu' nuova o piu' vecchia: fail-closed."""
    c = CS.CacheScan()
    riga = _riga_canale()
    riga["updated_at"] = "non e' una data"
    assert c.aggiorna(riga) is False


def test_una_riga_piu_vecchia_non_sostituisce_quella_che_c_e():
    c = CS.CacheScan()
    assert c.aggiorna(_riga_canale(secondi=5)) is True
    assert c.aggiorna(_riga_canale(secondi=1)) is False
    assert c.riga("1.1")["updated_at"] == (NOW + timedelta(seconds=5)).isoformat()
    assert c.aggiorna(_riga_canale(secondi=9)) is True
    assert c.riga("1.1")["updated_at"] == (NOW + timedelta(seconds=9)).isoformat()


def test_la_memoria_della_cache_ha_un_tetto():
    c = CS.CacheScan(max_righe=3)
    for i in range(6):
        assert c.aggiorna(_riga_canale(event_id="ev%d" % i)) is True
    assert c.stato()["righe"] == 3 and c.stato()["buttate"] == 3


def test_le_righe_stantie_non_escono_dalla_cache():
    """La soglia e' ``exits.FEED_FRESH_S``, quella che il bot usa gia'."""
    c = CS.CacheScan()
    c.aggiorna(_riga_canale(event_id="fresca", secondi=0))
    c.aggiorna(_riga_canale(event_id="vecchia",
                            secondi=-(XE.FEED_FRESH_S + 5)))
    fuori = c.righe_recenti(XE.FEED_FRESH_S, ora=NOW.timestamp())
    assert set(fuori) == {"fresca"}


# ---------------------------------------------------------------------------
# 3. La precedenza: il canale non ha nessun privilegio
# ---------------------------------------------------------------------------
def test_la_riga_del_canale_piu_vecchia_perde():
    db = _riga_canale(secondi=5)
    canale = _riga_canale(secondi=1)
    assert CS.piu_recente(db, canale) is db


def test_a_parita_di_updated_at_vince_il_db():
    db = _riga_canale(secondi=3)
    canale = _riga_canale(secondi=3, back=9.9)
    assert CS.piu_recente(db, canale) is db


def test_la_riga_del_canale_senza_odds_ts_ms_perde():
    """Invariante B11: senza l'istante del prezzo non entra in decisione."""
    db = _riga_canale(secondi=0)
    canale = _riga_canale(secondi=9, odds_ts_ms=None)
    assert CS.piu_recente(db, canale) is db
    canale["payload"]["odds_ts_ms"] = True        # un booleano non e' un istante
    assert CS.piu_recente(db, canale) is db


def test_la_riga_del_canale_piu_recente_vince():
    db = _riga_canale(secondi=0)
    canale = _riga_canale(secondi=4)
    assert CS.piu_recente(db, canale) is canale


def test_il_canale_non_aggiunge_mai_una_partita():
    """Quali partite esistono lo dice SOLO il database."""
    righe_db = [_riga_canale(event_id="1.1", secondi=0)]
    fresche = {"1.1": _riga_canale(event_id="1.1", secondi=4),
               "9.9": _riga_canale(event_id="9.9", secondi=4)}
    fuori, dal_canale = CS.fondi(righe_db, fresche)
    assert [r["event_id"] for r in fuori] == ["1.1"]
    assert dal_canale == 1


# ---------------------------------------------------------------------------
# 4. Il client: incassa, non solleva, sveglia solo se glielo si chiede
# ---------------------------------------------------------------------------
def test_il_client_ignora_cio_che_non_e_una_riga_di_scan():
    c = CS.CacheScan()
    cl = CS.ClientScan(47336, c)
    assert cl.incassa("{non json") is False
    assert cl.incassa(json.dumps({"t": "hello", "d": {"sport": "safe-scan"}})) is False
    assert cl.incassa(json.dumps({"t": CS.TOPIC_SCANNER_STATO, "d": {}})) is False
    assert cl.incassa(json.dumps({"t": "scan_calcio", "d": _riga_canale()})) is True
    assert c.stato()["righe"] == 1


def test_il_client_non_sveglia_nessuno_senza_interessa():
    ev = threading.Event()
    cl = CS.ClientScan(47336, CS.CacheScan(), evento=ev)
    cl.incassa(json.dumps({"t": "scan_tennis", "d": _riga_canale()}))
    assert ev.is_set() is False and cl.svegliate == 0


def test_il_client_sveglia_solo_gli_eventi_che_interessano():
    ev = threading.Event()
    cl = CS.ClientScan(47336, CS.CacheScan(), evento=ev,
                       interessa=lambda eid: eid == "2.2")
    cl.incassa(json.dumps({"t": "scan_tennis", "d": _riga_canale(event_id="1.1")}))
    assert ev.is_set() is False
    cl.incassa(json.dumps({"t": "scan_tennis", "d": _riga_canale(event_id="2.2")}))
    assert ev.is_set() is True and cl.svegliate == 1


def test_il_client_col_canale_giu_non_solleva_e_si_riaggancia():
    """Porta chiusa: si conta l'errore, si riprova, il bot non se ne accorge."""
    cl = CS.ClientScan(1, CS.CacheScan())          # porta 1: nessuno ascolta
    cl.ATTESE = (0.01,)
    t = threading.Thread(target=cl._gira, daemon=True)
    t.start()
    for _ in range(200):
        if cl.errori:
            break
        time.sleep(0.01)
    cl.ferma()
    t.join(timeout=2.0)
    assert cl.errori >= 1 and cl.ultimo_errore
    assert t.is_alive() is False


# ---------------------------------------------------------------------------
# 5. Il ciclo: interruttore spento = il percorso di oggi, riga per riga
# ---------------------------------------------------------------------------
def test_interruttore_assente_nessun_client_e_lettura_db_a_ogni_ciclo():
    assert S.avvia_client_scan() is False
    assert S._CANALE_SCAN["client"] is None and S._CANALE_SCAN["cache"] is None
    db = ContaDB()
    db.scan_rows = [_feed_row()]
    eng = FakeEngine()
    for i in range(3):
        _giro(db, eng, now=NOW + timedelta(seconds=2 * i))
    assert db.letture_feed == 3
    assert eng.seen_rows == db.scan_rows
    assert db.control["stats"]["fonte_scan"] == "db"


def test_col_canale_acceso_le_letture_del_feed_diminuiscono(monkeypatch):
    """La misura che conta: 3 cicli dentro i 10 s di riallineamento = 1 lettura.

    Oggi sono 30 letture/min (``poll_interval_s``=2); con il canale sano
    diventano 6/min. Le altre letture del ciclo non cambiano perche' il numero
    di cicli al minuto non cambia.
    """
    cache = CS.CacheScan()
    cache.aggiorna(_riga_canale(secondi=1))
    _accendi(monkeypatch, cache)
    db = ContaDB()
    db.scan_rows = [_feed_row()]
    for i in range(3):
        _giro(db, now=NOW + timedelta(seconds=2 * i))
    assert db.letture_feed == 1
    assert S._RISINC_DB_S == 10.0


def test_col_canale_stantio_si_ripiega_sul_database(monkeypatch):
    cache = CS.CacheScan()
    cache.aggiorna(_riga_canale(secondi=-(XE.FEED_FRESH_S + 30)))
    _accendi(monkeypatch, cache)
    db = ContaDB()
    db.scan_rows = [_feed_row()]
    for i in range(3):
        _giro(db, now=NOW + timedelta(seconds=2 * i))
    assert db.letture_feed == 3
    assert db.control["stats"]["fonte_scan"] == "db"


def test_la_riga_del_canale_piu_vecchia_del_db_non_arriva_al_motore(monkeypatch):
    cache = CS.CacheScan()
    cache.aggiorna(_riga_canale(secondi=0, back=9.99))
    _accendi(monkeypatch, cache)
    db = ContaDB()
    db.scan_rows = [_riga_canale(secondi=6, back=3.0)]
    eng = FakeEngine()
    _giro(db, eng, now=NOW + timedelta(seconds=6))
    assert eng.seen_rows[0]["payload"]["odds"]["home"]["back"] == 3.0
    assert db.control["stats"]["fonte_scan"] == "db"


def test_la_riga_del_canale_piu_recente_arriva_al_motore(monkeypatch):
    cache = CS.CacheScan()
    cache.aggiorna(_riga_canale(secondi=6, back=9.99))
    _accendi(monkeypatch, cache)
    db = ContaDB()
    db.scan_rows = [_riga_canale(secondi=0, back=3.0)]
    eng = FakeEngine()
    _giro(db, eng, now=NOW + timedelta(seconds=6))
    assert eng.seen_rows[0]["payload"]["odds"]["home"]["back"] == 9.99
    assert set(eng.seen_rows[0]) == set(db.scan_rows[0])
    assert db.control["stats"]["fonte_scan"] == "canale"


def test_il_client_che_solleva_non_ferma_il_ciclo(monkeypatch):
    """Cache rotta: si legge dal database e si tira avanti."""

    class CacheRotta(CS.CacheScan):
        def righe_recenti(self, max_eta_s=XE.FEED_FRESH_S, ora=None):
            raise RuntimeError("cache rotta")

    _accendi(monkeypatch, CacheRotta())
    db = ContaDB()
    db.scan_rows = [_feed_row()]
    eng = FakeEngine()
    res = _giro(db, eng, now=NOW)
    assert res.get("skipped") is None
    assert db.letture_feed == 1 and eng.seen_rows == db.scan_rows
    assert db.control["stats"]["fonte_scan"] == "db"


# ---------------------------------------------------------------------------
# 6. La sveglia: anticipa un giro, mai una raffica
# ---------------------------------------------------------------------------
def test_la_sveglia_anticipa_il_giro_ma_mai_sotto_i_250_ms():
    ev = threading.Event()
    ev.set()
    S._ULTIMO_GIRO["mono"] = time.monotonic()
    t0 = time.monotonic()
    assert S._attesa_interrompibile(2.0, 0, evento=ev) is True
    passato = time.monotonic() - t0
    assert passato >= S._MIN_GIRO_S * 0.95      # mai un giro a raffica
    assert passato < 1.5                        # e comunque prima dei 2 s
    assert ev.is_set() is False                 # la sveglia si consuma


def test_senza_sveglia_l_attesa_e_quella_di_oggi():
    t0 = time.monotonic()
    assert S._attesa_interrompibile(0.05, 0) is False
    assert 0.03 <= time.monotonic() - t0 < 1.0


def test_la_sveglia_che_arriva_durante_l_attesa_la_interrompe():
    ev = threading.Event()
    S._ULTIMO_GIRO["mono"] = time.monotonic() - 10.0
    threading.Timer(0.05, ev.set).start()
    t0 = time.monotonic()
    assert S._attesa_interrompibile(3.0, 0, evento=ev) is True
    assert time.monotonic() - t0 < 1.5


# ---------------------------------------------------------------------------
# 7. Il messaggio di sveglia: solo una sveglia, mai un ordine
# ---------------------------------------------------------------------------
def _canale_finto():
    """Il canale VERO del bot, non avviato: nessun socket, stesse regole."""
    ch = LC.LocalChannel(47335, "safe", solo_lettura=True)
    ch.risposte = []
    vero_send = ch._send
    ch._send = lambda ws, payload: ch.risposte.append(payload) or vero_send(ws, payload)
    return ch


def test_la_sveglia_alza_l_evento_e_non_porta_nessun_ordine():
    ev = threading.Event()
    ch = _canale_finto()
    conti = {}
    assert CS.installa_sveglia(ch, ev, conti) is True
    ch._on_message(object(), json.dumps({
        "m": "sveglia",
        "p": {"motivo": "approvazione",
              # campi d'ordine messi apposta: NON devono essere letti
              "action": "place", "side": "LAY", "price": 2.0, "size": 100.0,
              "event_id": "1.1", "market_id": "1.99", "selection_id": 7},
    }))
    assert ev.is_set() is True
    assert conti["sveglie"] == 1 and conti["ultimo_motivo"] == "approvazione"
    assert ch.pop_requests() == []              # niente in coda: nessun comando
    # ADATTATO (23/09, d1): prima si sostituiva ``_on_message`` sull'ISTANZA e
    # una sveglia riconosciuta non rispondeva affatto. Da d1 si usa il
    # meccanismo pulito ``set_sveglia``: e' ``LocalChannel._on_message``
    # (local_channel.py:157-169) a rispondere SEMPRE {"ok": cb is not None}
    # per un messaggio "sveglia" - installata la callback, ok e' sempre True,
    # come dichiarato dal checkpoint F5/F6 SS5 ("Risposta attesa: ok: true").
    # Non e' un metodo che porta un ordine: la coda resta vuota, il canale
    # resta di sola lettura.
    assert ch.risposte == [{"id": None, "ok": True}]
    assert ch.solo_lettura is True              # il canale resta di sola lettura


def test_una_sveglia_con_motivo_sconosciuto_e_rifiutata():
    ev = threading.Event()
    ch = _canale_finto()
    conti = {}
    CS.installa_sveglia(ch, ev, conti)
    ch._on_message(object(), json.dumps({"m": "sveglia", "p": {"motivo": "piazza"}}))
    assert ev.is_set() is False and conti["rifiutate"] == 1
    # ADATTATO (23/09, d1): local_channel.py:169 risponde ok=(cb is not None),
    # non ok=(motivo valido): la callback E' installata, quindi il canale
    # risponde ok=True anche per un motivo sconosciuto. Cio' che conta per il
    # bot - l'evento NON si alza, la riga finisce in "rifiutate" - e' identico
    # a prima: il rifiuto avviene dentro il callback di canale_scan, non piu'
    # nella risposta del canale.
    assert ch.risposte and ch.risposte[0]["ok"] is True


def test_un_comando_vero_resta_rifiutato_dal_canale_di_sola_lettura():
    ev = threading.Event()
    ch = _canale_finto()
    CS.installa_sveglia(ch, ev, {})
    ch._on_message(object(), json.dumps({"id": 3, "m": "order",
                                         "p": {"action": "place", "size": 100.0}}))
    assert ev.is_set() is False
    assert ch.pop_requests() == []
    assert ch.risposte and ch.risposte[0]["ok"] is False
    assert "sola lettura" in ch.risposte[0]["e"]


def test_senza_interruttore_la_sveglia_non_si_installa(monkeypatch):
    assert S.installa_sveglia_canale() is False
    assert S._CONTI_SVEGLIA.get("installata") is False


def test_installa_sveglia_non_sostituisce_piu_on_message(monkeypatch):
    """d1 (23/09): il chiamante deve usare ``set_sveglia``, non sostituire
    ``_on_message`` sull'ISTANZA. ``_on_message`` resta quello della CLASSE
    (stesso oggetto funzione di ``LocalChannel``, nessun wrapper agganciato
    sopra), e una sveglia arriva UGUALMENTE al callback registrato."""
    ev = threading.Event()
    ch = _canale_finto()
    conti = {}
    prima = ch._on_message
    assert CS.installa_sveglia(ch, ev, conti) is True
    # _on_message e' ancora il metodo BOUND della classe: nessuna sostituzione
    # sull'istanza. Confronto sul metodo non-bound (__func__) perche' due
    # bound method dello stesso oggetto non sono "is" identici in Python.
    assert ch._on_message.__func__ is LC.LocalChannel._on_message
    assert ch._on_message.__func__ is prima.__func__
    # la sveglia deve comunque arrivare al callback, tramite set_sveglia
    ch._on_message(object(), json.dumps({"m": "sveglia", "p": {"motivo": "comando"}}))
    assert ev.is_set() is True
    assert conti["sveglie"] == 1
