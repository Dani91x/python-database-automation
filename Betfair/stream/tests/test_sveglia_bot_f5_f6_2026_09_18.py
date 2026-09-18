"""F5/F6 - l'aggancio della sveglia ai TRE servizi: Omega, Mike, ponte tennis.

La domanda a cui rispondono questi test e' una sola, ripetuta per bot:
**a interruttore spento il bot esegue esattamente le istruzioni di oggi?**
Si conta ``time.sleep``/``stop.wait`` chiamata per chiamata, con lo stesso
numero. E, a interruttore acceso: la sveglia fa ripartire il giro, ma mai piu'
spesso della cadenza attiva di oggi - il conto delle letture al minuto.

Nessun database, nessuna rete, nessun processo: si tocca solo il punto della
dormita e il filtro ``interessa``.
"""
from __future__ import annotations

import threading

import pytest

from Betfair.mike import service as MIKE
from Betfair.omega import omega_service as OMEGA
from Betfair.stream import sveglia_canale as SV
from Betfair.stream.tennis_live import tennis_bot_service as TB


class _Orologio:
    def __init__(self, t0: float = 1000.0) -> None:
        self.t = float(t0)
        self.dormite: list[float] = []

    def ora(self) -> float:
        return self.t

    def dormi(self, quanto: float) -> None:
        self.dormite.append(float(quanto))
        self.t += float(quanto)


@pytest.fixture(autouse=True)
def _pulizia():
    """Ogni test parte da un processo appena avviato: la sveglia e' stato di
    processo, e uno scenario non deve poter sporcare quello dopo."""
    yield
    OMEGA._ASCOLTO_SCAN = None
    MIKE._ASCOLTO_SCAN = None
    TB._SVEGLIA_ATTIVA = False
    OMEGA._SVEGLIA.azzera()
    MIKE._SVEGLIA.azzera()
    TB._SVEGLIA.azzera()


# ======================================================= interruttore SPENTO
def test_omega_spento_dorme_con_time_sleep_e_lo_stesso_numero(monkeypatch):
    chiamate: list[float] = []
    monkeypatch.setattr(OMEGA.time, "sleep", lambda s: chiamate.append(s))
    OMEGA._ASCOLTO_SCAN = None
    OMEGA._SVEGLIA.alza("scan")          # anche se qualcuno la alzasse: ignorata
    OMEGA._dormi_o_sveglia(60.0, {"poll_interval_s": 20})
    assert chiamate == [60.0]
    assert OMEGA._SVEGLIA.statistiche()["usate"] == 0


def test_mike_spento_dorme_con_time_sleep_e_lo_stesso_numero(monkeypatch):
    chiamate: list[float] = []
    monkeypatch.setattr(MIKE.time, "sleep", lambda s: chiamate.append(s))
    MIKE._ASCOLTO_SCAN = None
    MIKE._SVEGLIA.alza("scan")
    MIKE._dormi_o_sveglia(30.0, {"decide_min_interval_ms": 500})
    assert chiamate == [30.0]
    assert MIKE._SVEGLIA.statistiche()["usate"] == 0


def test_ponte_tennis_spento_aspetta_con_stop_wait_e_lo_stesso_numero():
    class _Stop:
        def __init__(self) -> None:
            self.attese: list[float] = []

        def wait(self, quanto):
            self.attese.append(quanto)
            return False

        def is_set(self):
            return False

    TB._SVEGLIA_ATTIVA = False
    stop = _Stop()
    TB._dormi_o_sveglia(stop)
    assert stop.attese == [TB.ENSURE_POLL_SEC]


@pytest.mark.parametrize("bot,avvia,spia", [
    ("omega", lambda: OMEGA._avvia_sveglia(), lambda: OMEGA._ASCOLTO_SCAN),
    ("mike", lambda: MIKE._avvia_sveglia(), lambda: MIKE._ASCOLTO_SCAN),
])
def test_a_interruttore_spento_non_parte_nessun_thread_e_nessun_client(
        monkeypatch, bot, avvia, spia):
    """La spia CONTA, non solleva: ``_avvia_sveglia`` inghiotte le eccezioni (e
    deve farlo), quindi un finto esplosivo sarebbe un test che non sa diventare
    rosso - il difetto 29 del catalogo."""
    monkeypatch.delenv(SV.ENV_OMEGA_SVEGLIA, raising=False)
    monkeypatch.delenv(SV.ENV_MIKE_SVEGLIA, raising=False)
    costruiti: list = []

    class _AscoltoFinto:
        def __init__(self, *a, **k):
            costruiti.append(k.get("nome") or "?")
            self.url = "ws://127.0.0.1:47336"

        def avvia(self):
            return True

    monkeypatch.setattr(SV, "AscoltoScan", _AscoltoFinto)
    monkeypatch.setattr(OMEGA._lc, "get_channel", lambda: None)
    monkeypatch.setattr(MIKE._lc, "get_channel", lambda: None)
    avvia()
    assert costruiti == [], f"a interruttore spento e' stato costruito: {costruiti}"
    assert spia() is None


def test_ponte_tennis_spento_non_aggancia_niente(monkeypatch):
    """A interruttore spento il canale non viene nemmeno chiesto.

    La spia NON solleva: ``_avvia_sveglia`` inghiotte ogni eccezione (e deve
    farlo), quindi un finto esplosivo qui sarebbe un test che non sa diventare
    rosso. Si conta invece che cosa e' stato toccato.
    """
    monkeypatch.delenv(SV.ENV_TENNIS_SVEGLIA, raising=False)
    toccato: list[str] = []

    class _CanaleConSveglia:
        def set_sveglia(self, cb):
            toccato.append("set_sveglia")

    def _chiesto():
        toccato.append("get_channel")
        return _CanaleConSveglia()

    monkeypatch.setattr(TB._lc, "get_channel", _chiesto)
    TB._SVEGLIA_ATTIVA = False
    TB._avvia_sveglia()
    assert toccato == [], f"a interruttore spento e' stato toccato: {toccato}"
    assert TB._SVEGLIA_ATTIVA is False
    assert TB.statistiche_sveglia() is None


def test_a_interruttore_spento_lo_stato_non_dichiara_la_sveglia():
    OMEGA._ASCOLTO_SCAN = None
    MIKE._ASCOLTO_SCAN = None
    assert OMEGA.statistiche_sveglia() is None
    assert MIKE.statistiche_sveglia() is None


# ======================================================= interruttore ACCESO
def test_omega_acceso_il_giro_riparte_sulla_sveglia(monkeypatch):
    def _vietato(_s):
        raise AssertionError("col canale acceso la dormita non e' piu' time.sleep")

    monkeypatch.setattr(OMEGA.time, "sleep", _vietato)
    orol = _Orologio()
    OMEGA._SVEGLIA = SV.Sveglia("omega", ora=orol.ora, dormi=orol.dormi)
    OMEGA._ASCOLTO_SCAN = object()       # basta che ci sia: il ramo cambia
    OMEGA._SVEGLIA.alza("scan")
    OMEGA._dormi_o_sveglia(60.0, {"poll_interval_s": 20})
    # e' ripartito a 20 s (il pavimento), non a 60 (la cadenza a vuoto)
    assert orol.dormite == [20.0]
    OMEGA._SVEGLIA = SV.Sveglia("omega")


def test_mike_acceso_il_giro_riparte_sulla_sveglia(monkeypatch):
    def _vietato(_s):
        raise AssertionError("col canale acceso la dormita non e' piu' time.sleep")

    monkeypatch.setattr(MIKE.time, "sleep", _vietato)
    orol = _Orologio()
    MIKE._SVEGLIA = SV.Sveglia("mike", ora=orol.ora, dormi=orol.dormi)
    MIKE._ASCOLTO_SCAN = object()
    MIKE._SVEGLIA.alza("scan")
    MIKE._dormi_o_sveglia(30.0, {"decide_min_interval_ms": 1000})
    assert orol.dormite == [2.0]
    MIKE._SVEGLIA = SV.Sveglia("mike")


def test_ponte_tennis_acceso_riparte_sulla_sveglia():
    orol = _Orologio()
    TB._SVEGLIA = SV.Sveglia("tennis-bot", ora=orol.ora, dormi=orol.dormi)
    TB._SVEGLIA_ATTIVA = True
    assert TB._su_sveglia_dal_canale({"motivo": "comando"}) is True
    TB._dormi_o_sveglia(threading.Event())
    assert orol.dormite == [TB.MINIMO_SVEGLIA_S]
    TB._SVEGLIA = SV.Sveglia("tennis-bot")


# ======================================== il filtro: solo la memoria, mai il DB
def test_omega_si_sveglia_solo_per_gli_eventi_che_ha_gia_in_memoria():
    OMEGA._CACHE_FEED_CHIESTO_A.clear()
    assert OMEGA._evento_seguito("36050104") is False
    OMEGA._CACHE_FEED_CHIESTO_A["36050104"] = 123.0
    assert OMEGA._evento_seguito("36050104") is True
    assert OMEGA._evento_seguito("99999999") is False
    OMEGA._CACHE_FEED_CHIESTO_A.clear()


def test_mike_si_sveglia_solo_per_gli_eventi_che_ha_gia_in_memoria():
    MIKE._CACHE_EVENTI.clear()
    assert MIKE._evento_seguito("36050104") is False
    MIKE._CACHE_EVENTI["36050104"] = {"event_id": "36050104", "state": "WATCH"}
    assert MIKE._evento_seguito("36050104") is True
    assert MIKE._evento_seguito("99999999") is False
    MIKE._CACHE_EVENTI.clear()


def test_il_filtro_non_tocca_il_database():
    """Se il filtro leggesse dal DB, svegliarsi COSTEREBBE una lettura: sarebbe
    il contrario di questa fase. Qui si sostituisce l'accessore vero con uno che
    esplode, e il filtro deve rispondere lo stesso."""
    class _DBesplosivo:
        def __getattr__(self, nome):
            raise AssertionError(f"il filtro ha letto dal database: {nome}")

    vecchio_o, vecchio_m = OMEGA._real_db, MIKE._real_db
    try:
        OMEGA._real_db = _DBesplosivo()
        MIKE._real_db = _DBesplosivo()
        assert OMEGA._evento_seguito("36050104") is False
        assert MIKE._evento_seguito("36050104") is False
    finally:
        OMEGA._real_db, MIKE._real_db = vecchio_o, vecchio_m


# ====================================== il pavimento = la cadenza attiva di oggi
@pytest.mark.parametrize("params,atteso", [
    ({"poll_interval_s": 20}, 20.0),        # il default dichiarato
    ({}, 20.0),
    (None, 20.0),
    ({"poll_interval_s": 5}, 5.0),          # il minimo di configurazione
    ({"poll_interval_s": 1}, 5.0),          # sotto il minimo: si tiene il minimo
    ({"poll_interval_s": "storto"}, 20.0),
    ({"poll_interval_s": 60}, 60.0),
])
def test_omega_il_pavimento_e_poll_interval_s(params, atteso):
    assert OMEGA._pavimento_sveglia(params) == atteso


@pytest.mark.parametrize("params,atteso", [
    ({"decide_min_interval_ms": 500}, 1.0),   # il default: max(1.0, 0.5*2)
    ({}, 1.0),
    (None, 1.0),
    ({"decide_min_interval_ms": 1000}, 2.0),
    ({"decide_min_interval_ms": 100}, 1.0),   # sotto il pavimento duro di 1 s
    ({"decide_min_interval_ms": "storto"}, 1.0),
])
def test_mike_il_pavimento_e_la_cadenza_attiva(params, atteso):
    assert MIKE._pavimento_sveglia(params) == atteso


def test_il_pavimento_di_mike_e_lo_stesso_numero_che_calcola_il_loop():
    """Non un numero nuovo: la STESSA formula del loop (``service.py``, il punto
    in cui nasce ``interval`` prima di allargarsi a vuoto)."""
    for ms in (100, 500, 1000, 2500, 5000):
        params = {"decide_min_interval_ms": ms}
        interval_del_loop = max(1.0, float(params["decide_min_interval_ms"]) / 1000.0 * 2)
        assert MIKE._pavimento_sveglia(params) == interval_del_loop


# ============================== IL CONTO: le letture al minuto non crescono
@pytest.mark.parametrize("cadenza_attiva,cadenza_vuoto", [(20.0, 60.0), (5.0, 60.0)])
def test_omega_con_sveglie_continue_i_giri_al_minuto_non_superano_quelli_di_oggi(
        cadenza_attiva, cadenza_vuoto):
    orol = _Orologio()
    sveglia = SV.Sveglia("omega", ora=orol.ora, dormi=orol.dormi)
    pavimento = OMEGA._pavimento_sveglia({"poll_interval_s": cadenza_attiva})
    partenza, giri = orol.t, 0
    # tetto = rete contro un ciclo che non avanza (vedi il gemello nel modulo)
    while orol.t - partenza < 60.0 and giri <= 100:
        sveglia.alza("scan")                 # il canale non smette mai
        sveglia.attendi(cadenza_vuoto, pavimento)
        giri += 1
    oggi = int(60.0 / cadenza_attiva)        # i giri che Omega fa oggi da attivo
    assert giri <= oggi, f"{giri} giri/min contro i {oggi} di oggi"


def test_mike_con_sveglie_continue_i_giri_al_minuto_non_superano_quelli_di_oggi():
    orol = _Orologio()
    sveglia = SV.Sveglia("mike", ora=orol.ora, dormi=orol.dormi)
    params = {"decide_min_interval_ms": 500}
    pavimento = MIKE._pavimento_sveglia(params)
    partenza, giri = orol.t, 0
    while orol.t - partenza < 60.0 and giri <= 200:
        sveglia.alza("scan")
        sveglia.attendi(30.0, pavimento)     # 30 s = la dormita a vuoto
        giri += 1
    oggi = int(60.0 / pavimento)             # Mike attivo gira a ``pavimento``
    assert giri <= oggi, f"{giri} giri/min contro i {oggi} di oggi"


def test_ponte_tennis_con_sveglie_continue_resta_sotto_il_tetto_dichiarato():
    orol = _Orologio()
    sveglia = SV.Sveglia("tennis-bot", ora=orol.ora, dormi=orol.dormi)
    partenza, giri = orol.t, 0
    while orol.t - partenza < 60.0 and giri <= 200:
        sveglia.alza("comando", minimo_s=TB.MINIMO_SVEGLIA_S)
        sveglia.attendi(TB.ENSURE_POLL_SEC, TB.MINIMO_SVEGLIA_S)
        giri += 1
    assert giri <= int(60.0 / TB.MINIMO_SVEGLIA_S)


# ================================================ la sveglia da UI (F6, lato bot)
@pytest.mark.parametrize("modulo", [OMEGA, MIKE, TB])
def test_il_canale_accetta_solo_il_messaggio_di_sveglia(modulo):
    assert modulo._su_sveglia_dal_canale({"motivo": "approvazione"}) is True
    assert modulo._su_sveglia_dal_canale({"motivo": "comando"}) is True
    for storto in ({"motivo": "place"}, {"action": "place", "price": 3.4},
                   {}, None, "approvazione", [{"motivo": "comando"}]):
        assert modulo._su_sveglia_dal_canale(storto) is False


@pytest.mark.parametrize("modulo", [OMEGA, MIKE, TB])
def test_i_campi_dordine_sul_canale_sono_ignorati(modulo):
    """Il messaggio puo' portare quello che vuole: di li' esce SOLO la sveglia.
    Il comando vero resta la riga sul database."""
    modulo._SVEGLIA.azzera()
    assert modulo._su_sveglia_dal_canale({
        "motivo": "approvazione", "market_id": "1.240985123", "selection_id": 47972,
        "side": "LAY", "price": 3.4, "size": 25.0, "trade_id": 299,
        "client_ref": "omega-t-299", "action": "place", "mode": "live"}) is True
    conti = modulo._SVEGLIA.statistiche()
    assert conti["da_ui"] == 1 and conti["da_scan"] == 0
    # e nello stato non e' finito nessun dato d'ordine
    import json as _json
    testo = _json.dumps(conti)
    for vietato in ("1.240985123", "47972", "LAY", "3.4", "25.0", "live"):
        assert vietato not in testo


def test_la_sveglia_da_ui_e_agganciata_solo_se_il_canale_la_espone(monkeypatch, caplog):
    """``local_channel`` oggi e' di sola lettura e non espone ``set_sveglia``:
    il bot lo dichiara e va avanti, non si rompe."""
    monkeypatch.setenv(SV.ENV_TENNIS_SVEGLIA, "1")

    class _CanaleDiOggi:
        pass

    monkeypatch.setattr(TB._lc, "get_channel", lambda: _CanaleDiOggi())
    TB._SVEGLIA_ATTIVA = False
    TB._avvia_sveglia()
    assert TB._SVEGLIA_ATTIVA is False, "agganciata su un canale che non la espone"


def test_la_sveglia_da_ui_si_aggancia_quando_il_canale_la_espone(monkeypatch):
    monkeypatch.setenv(SV.ENV_TENNIS_SVEGLIA, "1")
    registrate: list = []

    class _CanaleConSveglia:
        def set_sveglia(self, cb):
            registrate.append(cb)

    monkeypatch.setattr(TB._lc, "get_channel", lambda: _CanaleConSveglia())
    TB._SVEGLIA_ATTIVA = False
    TB._avvia_sveglia()
    assert TB._SVEGLIA_ATTIVA is True
    assert registrate and registrate[0] is TB._su_sveglia_dal_canale


# ======================================= la sveglia e' stato di processo (B14)
def test_lo_svuota_le_cache_di_omega_azzera_anche_la_sveglia():
    OMEGA._SVEGLIA.alza("scan")
    OMEGA.svuota_le_cache()
    assert OMEGA._SVEGLIA.statistiche()["sveglie"] == 0


def test_lazzeramento_di_mike_azzera_anche_la_sveglia():
    MIKE._SVEGLIA.alza("scan")
    azzerati = MIKE.azzera_cache_di_processo()
    assert "_SVEGLIA" in azzerati
    assert MIKE._SVEGLIA.statistiche()["sveglie"] == 0
