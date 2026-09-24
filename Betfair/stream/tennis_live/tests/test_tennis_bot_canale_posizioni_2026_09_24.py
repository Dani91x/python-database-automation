"""24/09 - I 4 BOT TENNIS IN CONTROL ROOM DAL LORO CANALE (47337) + SVEGLIA ARMATURA.

Decisione dell'utente (24/09): "righe nuove dei bot in Control Room subito, non
al poll dei 30 s; bot tennis dal loro canale".

Che cosa si difende qui:

1. PRODUTTORE (runner, ``tennis_db.upsert_tennis_order``): la riga d'ordine di un
   BOT esce sul topic ``tennis_bot_posizioni`` DOPO la scrittura riuscita, ed e'
   la riga che la upsert ha RESTITUITO (chiavi e tipi identici, con ``id``) +
   la busta; nessuna lettura in piu'; gli ordini manuali non escono su quel
   topic; interruttore spento = niente; DB che rifiuta = niente.
2. L'armatura per partita ha il SUO topic (``tennis_bot_armamento``).
3. INOLTRO nel ponte (``canale_bot_tennis.InoltroPosizioni``): lettore del
   runner (``/lettore/tennis_bot_posizioni`` su 47332) che ripubblica sul canale
   del processo il messaggio IDENTICO; scarta hello, righe manuali, buste
   storte; non solleva mai. Catena completa produttore -> JSON -> inoltro:
   stesso dizionario.
4. SVEGLIA del ``bot_control_worker`` (``CancelloBotControl``): a riposo gira
   ogni 3 s come oggi (stesse letture al minuto); una sveglia lo anticipa con
   pavimento 1 s; una tempesta di sveglie non supera 60 giri/min; interruttore
   ``TENNIS_RUNNER_SVEGLIA_CANALE`` spento = worker identico (cadenza 3 s,
   nessun ascolto).

I finti hanno le chiavi e i tipi della tabella vera ``tennis_live_orders``
(colonne di ``_mirror_order`` + ``id`` + ``updated_at`` + regolamento).
"""
from __future__ import annotations

import inspect
import json
import types

import pytest

from Betfair.stream import canale_bot as CB
from Betfair.stream import sveglia_canale as SV
from Betfair.stream.tennis_live import canale_bot_tennis as CBT
from Betfair.stream.tennis_live import tennis_bot_service as S
from Betfair.stream.tennis_live import tennis_db as TDB
from Betfair.stream.tennis_live import tennis_runner as R


class RispostaFinta:
    def __init__(self, data) -> None:  # noqa: ANN001
        self.data = data


class TabellaFinta:
    def __init__(self, diario, nome, risposte, solleva=False) -> None:  # noqa: ANN001
        self._diario = diario
        self._nome = nome
        self._risposte = risposte
        self._verbo = "select"
        self._solleva = solleva

    def select(self, *a, **k):  # noqa: ANN001, ANN201, ARG002
        self._verbo = "select"
        return self

    def update(self, payload):  # noqa: ANN001, ANN201
        self._verbo = "update"
        self._diario.append(("update", self._nome, payload))
        return self

    def upsert(self, payload, **k):  # noqa: ANN001, ANN201, ARG002
        self._verbo = "upsert"
        self._diario.append(("upsert", self._nome, payload))
        return self

    def eq(self, *a, **k):  # noqa: ANN001, ANN201, ARG002
        return self

    def in_(self, *a, **k):  # noqa: ANN001, ANN201, ARG002
        return self

    def execute(self):  # noqa: ANN201
        self._diario.append(("execute", self._nome, self._verbo))
        if self._solleva:
            raise RuntimeError("violates not-null constraint")
        return self._risposte.get(self._nome, RispostaFinta([]))


class ClientFinto:
    def __init__(self, diario, risposte, solleva=False) -> None:  # noqa: ANN001
        self._diario = diario
        self._risposte = risposte
        self._solleva = solleva

    def table(self, nome):  # noqa: ANN001, ANN201
        return TabellaFinta(self._diario, nome, self._risposte, self._solleva)


class CanaleFinto:
    def __init__(self) -> None:
        self.inviati: list[tuple[str, dict]] = []

    def publish(self, topic, payload):  # noqa: ANN001, ANN201
        self.inviati.append((topic, payload))


#: la riga di ``tennis_live_orders`` come la RESTITUISCE la upsert (PostgREST,
#: return=representation): colonne di ``_mirror_order`` + id/updated_at/regolamento
RIGA_ORDINE_BOT = {
    "id": 4812, "mode": "paper", "source": "tennis_scalper",
    "client_order_ref": "tsc-35794049-1", "request_id": None,
    "event_id": "35794049", "market_id": "1.245678901", "selection_id": 10838543,
    "handicap": 0.0, "side": "back", "order_type": "LIMIT", "price": 1.85,
    "size": 2.0, "size_matched": 2.0, "size_remaining": 0.0,
    "size_cancelled": 0.0, "size_lapsed": 0.0, "size_voided": 0.0,
    "average_price_matched": 1.85, "status": "EXECUTION_COMPLETE",
    "bet_id": "345678901234", "persistence": "LAPSE",
    "placed_at": "2026-09-24T14:00:00.123456+00:00",
    "updated_at": "2026-09-24T14:00:01.654321+00:00",
    "pnl": None, "commission": None, "settled_at": None,
    "pnl_betfair": None, "commissione_betfair": None, "pnl_betfair_settled_at": None,
    "matched_at": "2026-09-24T14:00:00.923456+00:00",
}


def _payload_da_mirror(riga: dict) -> dict:
    """Quello che ``_mirror_order`` passa a ``upsert_tennis_order`` (senza id,
    senza updated_at: li mette il database / la funzione)."""
    return {k: v for k, v in riga.items()
            if k not in ("id", "updated_at", "placed_at", "matched_at", "pnl", "commission",
                         "settled_at", "pnl_betfair", "commissione_betfair",
                         "pnl_betfair_settled_at")}


@pytest.fixture
def banco(monkeypatch):
    diario: list = []
    risposte: dict = {}
    canale = CanaleFinto()
    stato = {"solleva": False}
    monkeypatch.setattr(TDB, "get_tennis_client",
                        lambda: ClientFinto(diario, risposte, stato["solleva"]))
    monkeypatch.setattr(CB, "_canale", lambda: canale)
    monkeypatch.setattr(TDB, "_CANALE_ACCESO", True)
    # il push A7 `order` (prima della scrittura) va sul canale del processo: qui
    # nessun canale -> no-op, come in un test senza runner
    CB.azzera_statistiche()
    yield {"diario": diario, "risposte": risposte, "canale": canale, "stato": stato}
    CB.azzera_statistiche()


# ================================================================ 1) produttore
def test_la_riga_dordine_di_un_bot_esce_sul_topic_delle_posizioni(banco):
    banco["risposte"]["tennis_live_orders"] = RispostaFinta([dict(RIGA_ORDINE_BOT)])
    TDB.upsert_tennis_order(_payload_da_mirror(RIGA_ORDINE_BOT))
    assert len(banco["canale"].inviati) == 1
    topic, msg = banco["canale"].inviati[0]
    assert topic == CB.TOPIC["tennis_bot_posizioni"] == "tennis_bot_posizioni"
    # il messaggio E' la riga del database (con `id`) + la busta, nient'altro
    assert set(msg) - set(CB.CHIAVI_META) == set(RIGA_ORDINE_BOT)
    for k, v in RIGA_ORDINE_BOT.items():
        assert msg[k] == v and type(msg[k]) is type(v), k
    assert msg["fonte"] == "canale"
    assert isinstance(msg["_seq"], int) and isinstance(msg["_pubblicato_ms"], int)


def test_nessuna_lettura_in_piu_sul_database(banco):
    banco["risposte"]["tennis_live_orders"] = RispostaFinta([dict(RIGA_ORDINE_BOT)])
    TDB.upsert_tennis_order(_payload_da_mirror(RIGA_ORDINE_BOT))
    verbi = [v for (op, _, v) in banco["diario"] if op == "execute"]
    assert verbi == ["upsert"], "una sola scrittura, nessuna select"


def test_un_ordine_manuale_non_esce_sul_topic_dei_bot(banco):
    manuale = {**RIGA_ORDINE_BOT, "source": "manual"}
    banco["risposte"]["tennis_live_orders"] = RispostaFinta([manuale])
    TDB.upsert_tennis_order(_payload_da_mirror(manuale))
    assert banco["canale"].inviati == []


@pytest.mark.parametrize("bot", sorted(CBT.SORGENTI_BOT_TENNIS))
def test_ognuno_dei_quattro_bot_esce(banco, bot):
    riga = {**RIGA_ORDINE_BOT, "source": bot}
    banco["risposte"]["tennis_live_orders"] = RispostaFinta([riga])
    TDB.upsert_tennis_order(_payload_da_mirror(riga))
    assert banco["canale"].inviati[0][1]["source"] == bot


def test_il_mode_e_quello_della_riga(banco):
    riga = {**RIGA_ORDINE_BOT, "mode": "live"}
    banco["risposte"]["tennis_live_orders"] = RispostaFinta([riga])
    TDB.upsert_tennis_order(_payload_da_mirror(riga))
    assert banco["canale"].inviati[0][1]["mode"] == "live"


def test_con_linterruttore_spento_non_esce_niente(banco, monkeypatch):
    monkeypatch.setattr(TDB, "_CANALE_ACCESO", False)
    banco["risposte"]["tennis_live_orders"] = RispostaFinta([dict(RIGA_ORDINE_BOT)])
    TDB.upsert_tennis_order(_payload_da_mirror(RIGA_ORDINE_BOT))
    assert banco["canale"].inviati == []


def test_una_scrittura_rifiutata_non_pubblica(banco):
    banco["stato"]["solleva"] = True
    with pytest.raises(RuntimeError):
        TDB.upsert_tennis_order(_payload_da_mirror(RIGA_ORDINE_BOT))
    assert banco["canale"].inviati == []


def test_le_sorgenti_dei_bot_sono_le_chiavi_del_ponte():
    """Una stringa scritta due volte diverge (difetto 33 del catalogo)."""
    assert CBT.SORGENTI_BOT_TENNIS == frozenset(S._BOT_KEYS)
    assert TDB._SORGENTI_BOT is CBT.SORGENTI_BOT_TENNIS


# ================================================================ 2) armatura
def test_larmatura_ha_il_suo_topic(banco):
    riga = {"id": 3, "event_id": "35794049", "bot_key": "tennis_pro",
            "status": "requested", "mode": "paper"}
    banco["risposte"]["tennis_bot_control"] = RispostaFinta([riga])
    TDB.upsert_tennis_bot_control({"event_id": "35794049", "bot_key": "tennis_pro",
                                   "status": "requested", "mode": "paper"})
    TDB.set_tennis_bot_status("35794049", "tennis_pro", "stopping")
    topic = [t for t, _ in banco["canale"].inviati]
    assert topic == [CB.TOPIC["tennis_bot_armamento"]] * 2
    assert CB.TOPIC["tennis_bot_armamento"] != CB.TOPIC["tennis_bot_posizioni"]


def test_lhello_del_47337_dichiara_i_tre_topic(monkeypatch):
    dichiarati: dict = {}

    class Ch:
        def set_hello(self, **k):  # noqa: ANN003, ANN201
            dichiarati.update(k)

    monkeypatch.setattr(CB, "acceso", lambda nome: True)
    monkeypatch.setattr(S._lc, "start_channel", lambda *a, **k: Ch())
    S._avvia_canale()
    assert dichiarati["topic"] == ["tennis_bot_stato", "tennis_bot_posizioni",
                                   "tennis_bot_armamento"]


# ================================================================ 3) inoltro
def _imbustata(riga: dict, seq: int = 7, ms: int = 1_790_000_000_000) -> dict:
    return {**riga, "fonte": "canale", "_seq": seq, "_pubblicato_ms": ms}


def _inoltro():
    usciti: list = []
    ino = CBT.InoltroPosizioni(porta_ws=47332,
                               pubblica=lambda t, m: usciti.append((t, m)) or True)
    return ino, usciti


def test_linoltro_si_aggancia_come_lettore_del_runner():
    ino, _ = _inoltro()
    assert ino.url == "ws://127.0.0.1:47332/lettore/tennis_bot_posizioni"


def test_linoltro_ripubblica_il_messaggio_identico():
    ino, usciti = _inoltro()
    msg = _imbustata(RIGA_ORDINE_BOT)
    assert ino.inoltra(json.dumps({"t": "tennis_bot_posizioni", "d": msg})) is True
    assert usciti == [("tennis_bot_posizioni", msg)]
    assert ino.statistiche()["inoltrati"] == 1


@pytest.mark.parametrize("grezzo", [
    json.dumps({"t": "hello", "d": {"sport": "tennis"}}),
    json.dumps({"t": "order", "d": _imbustata(RIGA_ORDINE_BOT)}),
    json.dumps({"t": "tennis_bot_posizioni", "d": _imbustata({**RIGA_ORDINE_BOT, "source": "manual"})}),
    json.dumps({"t": "tennis_bot_posizioni", "d": dict(RIGA_ORDINE_BOT)}),       # senza busta
    json.dumps({"t": "tennis_bot_posizioni", "d": {**_imbustata(RIGA_ORDINE_BOT), "fonte": "db"}}),
    json.dumps({"t": "tennis_bot_posizioni", "d": [1, 2]}),
    "{non json",
    b"\xff\xfe",
])
def test_linoltro_scarta_tutto_il_resto(grezzo):
    ino, usciti = _inoltro()
    assert ino.inoltra(grezzo) is False
    assert usciti == []


def test_linoltro_non_solleva_se_il_canale_del_ponte_solleva():
    def _boom(t, m):  # noqa: ANN001, ANN202, ARG001
        raise RuntimeError("canale morto")

    ino = CBT.InoltroPosizioni(porta_ws=47332, pubblica=_boom)
    msg = _imbustata(RIGA_ORDINE_BOT)
    assert ino.inoltra(json.dumps({"t": "tennis_bot_posizioni", "d": msg})) is False
    assert ino.statistiche()["errori"] == 1


def test_catena_completa_produttore_json_inoltro(banco):
    """Dal database del runner al canale del ponte: la riga che esce sul 47337
    e' byte per byte quella che il runner ha pubblicato dopo la scrittura."""
    banco["risposte"]["tennis_live_orders"] = RispostaFinta([dict(RIGA_ORDINE_BOT)])
    TDB.upsert_tennis_order(_payload_da_mirror(RIGA_ORDINE_BOT))
    topic, pubblicato = banco["canale"].inviati[0]
    sul_filo = json.dumps({"t": topic, "d": pubblicato}, default=str)
    ino, usciti = _inoltro()
    assert ino.inoltra(sul_filo) is True
    assert usciti[0][1] == pubblicato


def test_il_giro_del_client_legge_e_inoltra_poi_si_ferma():
    ino, usciti = _inoltro()
    msg = _imbustata(RIGA_ORDINE_BOT)
    coda = [json.dumps({"t": "hello", "d": {}}),
            json.dumps({"t": "tennis_bot_posizioni", "d": msg})]
    aperti: list = []

    class WsFinto:
        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, *a):  # noqa: ANN002, ANN204
            return False

        def recv(self, timeout=None):  # noqa: ANN001, ANN201, ARG002
            if coda:
                return coda.pop(0)
            ino.ferma()
            raise TimeoutError

    def _connetti(url):  # noqa: ANN001, ANN202
        aperti.append(url)
        return WsFinto()

    ino._connetti = _connetti
    ino._gira()
    assert aperti == ["ws://127.0.0.1:47332/lettore/tennis_bot_posizioni"]
    assert usciti == [("tennis_bot_posizioni", msg)]


def test_runner_assente_il_client_riprova_senza_sollevare():
    ino, _ = _inoltro()
    tentativi: list = []

    def _rifiuta(url):  # noqa: ANN001, ANN202
        tentativi.append(url)
        if len(tentativi) >= 2:
            ino.ferma()
        raise ConnectionRefusedError("porta chiusa")

    ino._connetti = _rifiuta
    CBT._ATTESE_S = (0.0,)  # type: ignore[assignment]
    try:
        ino._gira()
    finally:
        CBT._ATTESE_S = (0.5, 1.0, 2.0, 5.0)  # type: ignore[assignment]
    assert len(tentativi) == 2
    assert ino.statistiche()["errori"] == 2


def test_linoltro_parte_solo_con_linterruttore_e_il_canale(monkeypatch):
    CBT._INOLTRO = None
    monkeypatch.delenv(CB.ENV_TENNIS_BOT, raising=False)
    assert CBT.avvia_inoltro_nel_ponte() is None
    monkeypatch.setenv(CB.ENV_TENNIS_BOT, "1")
    monkeypatch.setattr("Betfair.stream.local_channel.get_channel", lambda: None)
    assert CBT.avvia_inoltro_nel_ponte() is None     # nessun 47337: niente inoltro
    assert CBT._INOLTRO is None


def test_linoltro_vive_solo_nel_ramo_ponte():
    sorgente = inspect.getsource(S._main)
    prima, _, dopo = sorgente.partition("if args.bridge_only:")
    assert "avvia_inoltro_nel_ponte()" in dopo
    assert "avvia_inoltro_nel_ponte()" not in prima
    assert "avvia_inoltro_nel_ponte" not in inspect.getsource(S.run)


def test_il_modulo_del_canale_tennis_e_puro():
    import_ = [r.strip() for r in inspect.getsource(CBT).splitlines()
               if r.strip().startswith(("import ", "from "))]
    for riga in import_:
        for vietato in ("flumine", "betfairlightweight", "supabase", "tennis_db", "websockets"):
            if vietato == "websockets" and riga == "from websockets.sync.client import connect":
                continue          # pigro, dentro _connetti_ws (thread del client)
            assert vietato not in riga, riga


# ================================================================ 4) sveglia
class Orologio:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _giri_in(cancello, orologio, secondi, passo=CBT.PASSO_WORKER_S, sveglie_ogni=None):
    giri = 0
    fine = orologio.t + secondi
    prossima = orologio.t + (sveglie_ogni or 0)
    while orologio.t < fine:
        if sveglie_ogni is not None and orologio.t >= prossima:
            cancello.alza("armamento")
            prossima += sveglie_ogni
        if cancello.deve_girare():
            giri += 1
        orologio.t += passo
    return giri


def test_a_riposo_il_worker_gira_ogni_3_s_come_oggi():
    o = Orologio()
    c = CBT.CancelloBotControl(3.0, ora=o)
    assert _giri_in(c, o, 60.0) == 20        # oggi: 60 / 3 = 20 giri al minuto


def test_una_sveglia_anticipa_il_giro_ma_non_prima_del_pavimento():
    o = Orologio()
    c = CBT.CancelloBotControl(3.0, ora=o)
    assert c.deve_girare() is True           # primo giro
    o.t += 0.5
    c.alza("armamento")
    assert c.deve_girare() is False          # 0,5 s < pavimento 1 s
    o.t += 0.5
    assert c.deve_girare() is True           # 1,0 s: parte, senza aspettare i 3 s
    assert c.statistiche()["giri_per_sveglia"] == 1
    o.t += 1.0
    assert c.deve_girare() is False          # sveglia consumata: si torna a 3 s


def test_una_tempesta_di_sveglie_non_supera_il_pavimento():
    o = Orologio()
    c = CBT.CancelloBotControl(3.0, ora=o)
    assert _giri_in(c, o, 60.0, sveglie_ogni=0.1) <= 60


def test_la_sveglia_passa_dallascolto_del_canale_solo_per_partite_seguite():
    o = Orologio()
    c = CBT.CancelloBotControl(3.0, ora=o)
    ascolto = SV.AscoltoScan(c, lambda ev: ev == "35794049",
                             topic=(CBT.TOPIC_ARMAMENTO,), porta=47337)
    riga = {"id": 3, "event_id": "35794049", "bot_key": "tennis_pro", "status": "requested",
            "fonte": "canale", "_seq": 1, "_pubblicato_ms": 1}
    assert ascolto.tratta(json.dumps({"t": "tennis_bot_stato", "d": riga})) is False
    assert ascolto.tratta(json.dumps({"t": "tennis_bot_armamento",
                                      "d": {**riga, "event_id": "99"}})) is False
    assert c.statistiche()["sveglie"] == 0
    assert ascolto.tratta(json.dumps({"t": "tennis_bot_armamento", "d": riga})) is True
    assert c.statistiche()["sveglie"] == 1


def test_linterruttore_della_sveglia_del_runner_e_spento_di_serie(monkeypatch):
    monkeypatch.delenv(CBT.ENV_SVEGLIA_RUNNER, raising=False)
    assert CBT.sveglia_runner_accesa() is False
    monkeypatch.setenv(CBT.ENV_SVEGLIA_RUNNER, "")
    assert CBT.sveglia_runner_accesa() is False


@pytest.fixture
def runner_pulito(monkeypatch):
    monkeypatch.setattr(R, "_CANCELLO_BOT_CONTROL", None)
    monkeypatch.setitem(R._SESSIONE_ARMAMENTO, "session", None)
    yield


def test_a_interruttore_spento_nessun_ascolto_e_cadenza_di_oggi(monkeypatch, runner_pulito):
    monkeypatch.delenv(CBT.ENV_SVEGLIA_RUNNER, raising=False)
    avviati: list = []
    monkeypatch.setattr(CBT, "avvia_ascolto_armamento",
                        lambda *a, **k: avviati.append(a) or object())
    R._avvia_sveglia_armamento(types.SimpleNamespace(market_meta={}))
    assert avviati == []
    assert R._CANCELLO_BOT_CONTROL is None
    assert R._intervallo_bot_control() == (R.BOT_CONTROL_POLL_SEC or 3.0)


def test_a_interruttore_acceso_il_worker_passa_al_cancello(monkeypatch, runner_pulito):
    monkeypatch.setenv(CBT.ENV_SVEGLIA_RUNNER, "1")
    avviati: list = []
    monkeypatch.setattr(CBT, "avvia_ascolto_armamento",
                        lambda c, f, **k: avviati.append((c, f)) or object())
    sess = types.SimpleNamespace(market_meta={"35794049": {}})
    R._avvia_sveglia_armamento(sess)
    assert len(avviati) == 1
    assert isinstance(R._CANCELLO_BOT_CONTROL, CBT.CancelloBotControl)
    assert R._intervallo_bot_control() == CBT.PASSO_WORKER_S
    filtro = avviati[0][1]
    assert filtro("35794049") is True and filtro("1") is False
    # un secondo avvio (restart del framework) NON apre un secondo ascolto
    R._avvia_sveglia_armamento(sess)
    assert len(avviati) == 1


def test_ascolto_che_non_parte_lascia_il_worker_di_oggi(monkeypatch, runner_pulito):
    monkeypatch.setenv(CBT.ENV_SVEGLIA_RUNNER, "1")
    monkeypatch.setattr(CBT, "avvia_ascolto_armamento", lambda *a, **k: None)
    R._avvia_sveglia_armamento(types.SimpleNamespace(market_meta={}))
    assert R._CANCELLO_BOT_CONTROL is None
    assert R._intervallo_bot_control() == (R.BOT_CONTROL_POLL_SEC or 3.0)


def _sessione_worker():
    return types.SimpleNamespace(market_meta={"35794049": {"market_id": "1.2"}},
                                 hosted={}, stopping_deadline={})


def test_il_cancello_chiuso_non_legge_il_database(monkeypatch, runner_pulito):
    letture: list = []
    monkeypatch.setattr(R, "_desired_controls", lambda ev: letture.append(ev) or {})
    monkeypatch.setattr(R, "_stopping_controls", lambda ev: letture.append(ev) or {})
    monkeypatch.setattr(R._gt, "guardia_blocca", lambda: False)
    o = Orologio()
    c = CBT.CancelloBotControl(3.0, ora=o)
    monkeypatch.setattr(R, "_CANCELLO_BOT_CONTROL", c)
    R.bot_control_worker({}, object(), _sessione_worker())      # primo giro: lavora
    assert len(letture) == 2
    o.t += 0.25
    R.bot_control_worker({}, object(), _sessione_worker())      # 0,25 s dopo: niente
    assert len(letture) == 2
    c.alza("armamento")
    o.t += 0.75
    R.bot_control_worker({}, object(), _sessione_worker())      # sveglia a 1 s: lavora
    assert len(letture) == 4


def test_senza_cancello_il_worker_lavora_a_ogni_chiamata(monkeypatch, runner_pulito):
    letture: list = []
    monkeypatch.setattr(R, "_desired_controls", lambda ev: letture.append(ev) or {})
    monkeypatch.setattr(R, "_stopping_controls", lambda ev: letture.append(ev) or {})
    monkeypatch.setattr(R._gt, "guardia_blocca", lambda: False)
    R.bot_control_worker({}, object(), _sessione_worker())
    R.bot_control_worker({}, object(), _sessione_worker())
    assert len(letture) == 4
