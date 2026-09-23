"""Test del saldo riletto DOPO UN EVENTO D'ORDINE (23/09, bug: "il saldo non si
aggiorna ne' quando partono gli ordini ne' quando vengono chiusi").

NESSUNA rete, nessun DB: ``db.upsert_live_account`` e ``local_channel.publish``
sono sostituiti da registratori. I finti del conto parlano come il vero:
  * REST JSON-RPC (``omega_market`` -> ``account_rpc``): dict con le chiavi di
    ``getAccountFunds`` (``availableToBetBalance``, ``exposure``, ...);
  * flumine/betfairlightweight (runner): la risorsa VERA ``AccountFunds``.

Garanzie sotto test:
  * un evento d'ordine -> ESATTAMENTE una lettura, una scrittura, una publish;
  * nessun evento -> nessuna chiamata; modulo non attivato -> nessuna chiamata;
  * lettura KO -> mai un'eccezione al chiamante, nessuna scrittura;
  * regolati: la prima lettura semina, un bet_id nuovo -> una lettura;
  * flumine: ordine REALE -> lettura, ordine simulato (paper) -> niente;
  * runner calcio: la lettura su evento riparte l'orologio dei 20 s.
"""
from __future__ import annotations

import ast
import pathlib
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from betfairlightweight.resources.accountresources import AccountFunds
from flumine.events import events as fl_events

import Betfair.stream.reconcile_worker as rw
from Betfair.stream import saldo_evento as se

_RADICE = pathlib.Path(__file__).resolve().parents[3]

# risposta JSON-RPC VERA di AccountAPING/v1.0/getAccountFunds (campo "result")
_FUNDS_REST: Dict[str, Any] = {
    "availableToBetBalance": 812.37,
    "exposure": -41.5,
    "retainedCommission": 0.0,
    "exposureLimit": -10000.0,
    "discountRate": 0.0,
    "pointsBalance": 12,
    "wallet": "UK",
}


class _Registro:
    def __init__(self) -> None:
        self.letture = 0
        self.scritture: List[tuple] = []
        self.istanti: List[Any] = []       # updated_at passato alla scrittura DB
        self.pubblicazioni: List[tuple] = []


@pytest.fixture()
def reg(monkeypatch: pytest.MonkeyPatch) -> _Registro:
    r = _Registro()
    se.azzera()
    from Betfair.stream import db, local_channel

    def scrivi(a: Any, e: Any, **kw: Any) -> None:
        r.scritture.append((a, e))
        r.istanti.append(kw.get("updated_at"))

    monkeypatch.setattr(db, "upsert_live_account", scrivi)
    monkeypatch.setattr(local_channel, "publish", lambda t, p: r.pubblicazioni.append((t, p)))
    yield r
    se.azzera()


def _attiva_con(reg: _Registro, risposta: Any = None, **kw: Any) -> None:
    def get_funds() -> Any:
        reg.letture += 1
        return dict(_FUNDS_REST) if risposta is None else risposta

    se.attiva(get_funds, nome="test", **kw)


# ---------------------------------------------------------------------------
# nucleo
# ---------------------------------------------------------------------------
def test_un_evento_una_lettura_una_scrittura_una_publish(reg: _Registro) -> None:
    _attiva_con(reg)
    se.segnala("ordine")
    se.attendi()
    assert reg.letture == 1
    assert reg.scritture == [(812.37, -41.5)]
    assert len(reg.pubblicazioni) == 1
    topic, payload = reg.pubblicazioni[0]
    assert topic == "account"
    assert payload["available"] == 812.37 and payload["exposure"] == -41.5
    assert isinstance(payload["checked_at"], str) and payload["checked_at"].endswith("+00:00")
    assert payload["fonte"] == "test:ordine"


def test_db_e_canale_portano_lo_stesso_istante_della_lettura(reg: _Registro) -> None:
    """F1 revisore A (23/09): ``betfair_live_account.updated_at`` = ``checked_at``
    del canale (istante della LETTURA), non l'istante di scrittura: il frontend
    (saldoDaMostrare) confronta i due come la stessa grandezza."""
    _attiva_con(reg)
    se.segnala("ordine")
    se.attendi()
    assert len(reg.istanti) == 1 and len(reg.pubblicazioni) == 1
    assert reg.istanti[0] == reg.pubblicazioni[0][1]["checked_at"]


class _TabellaFinta:
    """Builder PostgREST minimo: registra il payload dell'upsert."""

    def __init__(self, registro: List[Dict[str, Any]]) -> None:
        self._registro = registro

    def upsert(self, payload: Dict[str, Any], on_conflict: str = "") -> "_TabellaFinta":
        self._registro.append({"payload": dict(payload), "on_conflict": on_conflict})
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=[self._registro[-1]["payload"]])


def test_upsert_live_account_scrive_l_istante_dato_e_di_default_l_ora(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from Betfair.stream import db

    scritte: List[Dict[str, Any]] = []
    client = SimpleNamespace(table=lambda nome: _TabellaFinta(scritte))
    monkeypatch.setattr(db, "get_supabase_client", lambda: client)
    monkeypatch.setattr(db, "_now_iso", lambda: "2026-09-23T10:00:05+00:00")

    db.upsert_live_account(812.37, -41.5, updated_at="2026-09-23T10:00:00.123456+00:00")
    db.upsert_live_account(812.37, -41.5)
    assert [s["payload"] for s in scritte] == [
        {"id": 1, "available": 812.37, "exposure": -41.5,
         "updated_at": "2026-09-23T10:00:00.123456+00:00"},
        {"id": 1, "available": 812.37, "exposure": -41.5,
         "updated_at": "2026-09-23T10:00:05+00:00"},
    ]
    assert all(s["on_conflict"] == "id" for s in scritte)


def test_nessun_evento_nessuna_chiamata(reg: _Registro) -> None:
    _attiva_con(reg)
    se.attendi()
    assert (reg.letture, reg.scritture, reg.pubblicazioni) == (0, [], [])


def test_modulo_non_attivato_segnala_non_fa_nulla(reg: _Registro) -> None:
    se.segnala("ordine")
    se.attendi()
    assert se.attiva_in_questo_processo() is False
    assert (reg.letture, reg.scritture, reg.pubblicazioni) == (0, [], [])


def test_risorsa_vera_betfairlightweight_letta_con_gli_attributi_veri(reg: _Registro) -> None:
    _attiva_con(reg, risposta=AccountFunds(**_FUNDS_REST))
    se.segnala("ordine")
    se.attendi()
    assert reg.scritture == [(812.37, -41.5)]


def test_lettura_ko_mai_eccezione_nessuna_scrittura(reg: _Registro) -> None:
    def rotto() -> Any:
        reg.letture += 1
        raise RuntimeError("rete KO")

    se.attiva(rotto, nome="test")
    se.segnala("ordine")
    se.attendi()
    assert reg.letture == 1
    assert reg.scritture == [] and reg.pubblicazioni == []


def test_risposta_senza_saldo_non_scrive_un_numero_inventato(reg: _Registro) -> None:
    _attiva_con(reg, risposta={"exposure": -1.0})
    se.segnala("ordine")
    se.attendi()
    assert reg.letture == 1 and reg.scritture == [] and reg.pubblicazioni == []


# ---------------------------------------------------------------------------
# regolazioni (REST)
# ---------------------------------------------------------------------------
def test_regolati_la_prima_lettura_semina_poi_un_bet_nuovo_una_lettura(reg: _Registro) -> None:
    _attiva_con(reg)
    assert se.nota_regolati(["1", "2"]) is False       # semina: ieri non e' un evento
    assert se.nota_regolati(["1", "2"]) is False       # stessi: niente
    se.attendi()
    assert reg.letture == 0
    assert se.nota_regolati(["1", "2", "3"]) is True    # regolazione nuova
    se.attendi()
    assert reg.letture == 1 and len(reg.scritture) == 1


# ---------------------------------------------------------------------------
# aggancio REST: omega_market (Omega, Safe, Mike)
# ---------------------------------------------------------------------------
class _ClientFinto:
    def __init__(self, esplodi: Exception | None = None) -> None:
        self.esplodi = esplodi
        self.rpc: List[tuple] = []

    def place_orders(self, *a: Any, **k: Any) -> Dict[str, Any]:
        if self.esplodi is not None:
            raise self.esplodi
        return {"status": "SUCCESS", "instructionReports": [{"status": "SUCCESS", "betId": "9"}]}

    def account_rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self.rpc.append((method, params))
        return dict(_FUNDS_REST)

    def list_cleared_orders(self, **k: Any) -> Dict[str, Any]:
        return {"clearedOrders": list(self.regolati.get(k.get("bet_status"), []))}

    regolati: Dict[str, List[Dict[str, Any]]] = {}


@pytest.fixture()
def client_finto(monkeypatch: pytest.MonkeyPatch) -> _ClientFinto:
    import Betfair.odds_refresh as orf

    c = _ClientFinto()
    monkeypatch.setattr(orf, "get_shared_client", lambda: c)
    monkeypatch.setattr(orf, "reset_shared_client", lambda: None)
    return c


def test_omega_market_ordine_riuscito_una_sola_getaccountfunds(reg: _Registro, client_finto: _ClientFinto) -> None:
    from Betfair.omega import omega_market as om

    om.attiva_saldo_su_evento("omega")
    om.call_mutating(lambda c: c.place_orders("1.1", []))
    se.attendi()
    assert client_finto.rpc == [("AccountAPING/v1.0/getAccountFunds", {})]
    assert reg.scritture == [(812.37, -41.5)]
    assert [t for t, _ in reg.pubblicazioni] == ["account"]


def test_omega_market_ordine_fallito_nessuna_lettura(reg: _Registro, client_finto: _ClientFinto) -> None:
    from Betfair.omega import omega_market as om

    om.attiva_saldo_su_evento("omega")
    client_finto.esplodi = RuntimeError("timeout generico")
    with pytest.raises(RuntimeError):
        om.call_mutating(lambda c: c.place_orders("1.1", []))
    se.attendi()
    assert client_finto.rpc == [] and reg.scritture == []


def test_omega_market_senza_attivazione_nessuna_lettura(reg: _Registro, client_finto: _ClientFinto) -> None:
    from Betfair.omega import omega_market as om

    om.call_mutating(lambda c: c.place_orders("1.1", []))
    se.attendi()
    assert client_finto.rpc == [] and reg.scritture == []


def _regolato(bet_id: str) -> Dict[str, Any]:
    # chiavi VERE di ClearedOrderSummary (JSON-RPC)
    return {"betId": bet_id, "marketId": "1.2", "selectionId": 7, "side": "LAY",
            "sizeSettled": 2.0, "priceMatched": 3.1, "profit": 2.0, "commission": 0.1,
            "betOutcome": "WON", "customerOrderRef": "omega-t1"}


def test_omega_market_regolato_nuovo_una_lettura_vista_parziale_nessuna(
        reg: _Registro, client_finto: _ClientFinto) -> None:
    from Betfair.omega import omega_market as om

    om.attiva_saldo_su_evento("omega")
    _ClientFinto.regolati = {"SETTLED": [_regolato("100")]}
    om.list_cleared_orders()                         # semina
    om.list_cleared_orders()                         # invariato
    _ClientFinto.regolati = {"SETTLED": [_regolato("100"), _regolato("101")]}
    om.list_cleared_orders(market_ids=["1.2"])       # vista PARZIALE: ignorata
    se.attendi()
    assert client_finto.rpc == []
    om.list_cleared_orders()                         # regolazione nuova
    se.attendi()
    assert len(client_finto.rpc) == 1
    _ClientFinto.regolati = {}


# ---------------------------------------------------------------------------
# aggancio flumine (runner calcio / runner tennis)
# ---------------------------------------------------------------------------
def test_flumine_ordine_reale_una_lettura_simulato_nessuna_regolati_una(reg: _Registro) -> None:
    _attiva_con(reg)
    ctl = se.controllo_flumine()
    ctl.process_event(fl_events.OrderEvent(SimpleNamespace(simulated=False)))
    se.attendi()
    assert reg.letture == 1
    ctl.process_event(fl_events.OrderEvent(SimpleNamespace(simulated=True)))
    se.attendi()
    assert reg.letture == 1
    ctl.process_event(fl_events.ClearedOrdersEvent(SimpleNamespace(orders=[])))
    se.attendi()
    assert reg.letture == 2


def test_runner_calcio_lettura_su_evento_riparte_l_orologio_dei_20s(
        reg: _Registro, monkeypatch: pytest.MonkeyPatch) -> None:
    chiamate: List[int] = []

    class _Account:
        def get_account_funds(self) -> AccountFunds:
            chiamate.append(1)
            return AccountFunds(**_FUNDS_REST)

    session = SimpleNamespace(context_api_client=SimpleNamespace(account=_Account()))
    aggiunti: List[Any] = []
    framework = SimpleNamespace(add_logging_control=aggiunti.append)
    monkeypatch.setattr(rw, "_LAST_ACCOUNT_TS", 0.0)
    monkeypatch.setattr(rw, "_LAST_ACCOUNT_SIG", None)
    monkeypatch.setattr(rw, "_run_manual_pnl_if_due", lambda s, force=False: None)
    rw.attiva_saldo_su_evento(framework, session)
    assert len(aggiunti) == 1
    aggiunti[0].process_event(fl_events.OrderEvent(SimpleNamespace(simulated=False)))
    se.attendi()
    assert len(chiamate) == 1
    assert rw._LAST_ACCOUNT_SIG == (812.37, -41.5)
    # il giro periodico subito dopo NON rilegge (orologio ripartito)
    rw.run_account_sync_if_due(session)
    assert len(chiamate) == 1


# ---------------------------------------------------------------------------
# cablaggio: chi accende cosa (AST/testo, i main fanno login reale)
# ---------------------------------------------------------------------------
def _chiama(percorso: str, nome: str) -> bool:
    albero = ast.parse((_RADICE / percorso).read_text(encoding="utf-8"))
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Call):
            f = nodo.func
            if (isinstance(f, ast.Attribute) and f.attr == nome) or (isinstance(f, ast.Name) and f.id == nome):
                return True
    return False


@pytest.mark.parametrize("percorso", [
    "Betfair/omega/omega_service.py",
    "Betfair/mike/service.py",
    "Betfair/safe_strategy/bot_service.py",
    "Betfair/stream/runner.py",
])
def test_i_processi_che_piazzano_accendono_la_rilettura(percorso: str) -> None:
    assert _chiama(percorso, "attiva_saldo_su_evento"), percorso


def test_runner_tennis_accende_la_rilettura_solo_in_live() -> None:
    testo = (_RADICE / "Betfair/stream/tennis_live/tennis_runner.py").read_text(encoding="utf-8")
    assert 'if str(mode).strip().upper() == "LIVE":\n                _attiva_saldo_su_evento(framework, trading)' \
        in testo.replace("\r\n", "\n")


def test_runner_calcio_accende_la_rilettura_solo_nel_ramo_live() -> None:
    albero = ast.parse((_RADICE / "Betfair/stream/runner.py").read_text(encoding="utf-8"))
    trovati = []
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.If) and "LIVE" in ast.unparse(nodo.test):
            for sotto in ast.walk(nodo):
                if isinstance(sotto, ast.Call) and isinstance(sotto.func, ast.Name) \
                        and sotto.func.id == "attiva_saldo_su_evento":
                    trovati.append(ast.unparse(nodo.test))
    assert trovati, "attiva_saldo_su_evento deve stare dentro un ramo LIVE"
