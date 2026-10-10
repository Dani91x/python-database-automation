"""W1-G2 - decisione 10 dell'utente (10/10/2026): i dati calcolati dal cloud arrivano APPENA il cloud ricalcola.

"Tutta l'app in tempo reale per Betfair; il cloud solo come backup; il resto sul DB locale." Oggi il dossier di
Mike cieco si riprova ogni ``_DOSSIER_RETRY_SEC`` = 300 s (``Betfair/mike/service.py``) e la sentinella delle
tabelle di Omega si rilegge ogni 300 s. Qui si prova che ``cache_cloud.Sorveglianza`` (una chiamata leggera ogni
5 s, la RPC ``nucleo_sentinella_cloud`` della migrazione ``nucleo_sentinella_cloud_2026-10-10.sql``; senza la
migrazione le letture REST di oggi ogni 15 s) porta i cambi entro la latenza dichiarata e non e' MAI piu' lenta
del codice di oggi su nessun caso, con l'orologio finto e le funzioni VERE di Mike come arbitro
(``mike/service.dossier_da_ritentare``, ``_retry_dossier``, ``mike/dossier.build_prematch``, ``mike/db``).

Il cloud e' il PostgREST finto di ``test_g2_cache_cloud.py`` dietro il client supabase VERO (``httpx.MockTransport``),
con in piu' la RPC della migrazione e il trigger della versione rifatti in Python con la stessa semantica
(provata sul PostgreSQL vero in ``test_g2_pg_sentinella.py``). Nessuna rete, nessun DB vero.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx
import pytest
import supabase
from supabase import ClientOptions

os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

import db_client  # noqa: E402
from Betfair.mike import db as mike_db  # noqa: E402
from Betfair.mike import dossier  # noqa: E402
from Betfair.mike import service as mike_service  # noqa: E402
from Betfair.nucleo.dati import cache_cloud as K  # noqa: E402
from Betfair.nucleo.dati.cloud import ClienteCloud  # noqa: E402
from Betfair.nucleo.dati.tests.test_g2_cache_cloud import (CORPO_57014, CORPO_PGRST202, FIXTURE,  # noqa: E402
                                                           TACTICAL_OK, CloudFinto, costruisci_notte)
from Betfair.omega import omega_db, omega_service  # noqa: E402

T0 = 1_760_000_000.0
#: le cinque colonne lette dal dossier: il trigger della migrazione cambia la versione solo se cambia una di queste
COLONNE_DOSSIER = ("tactical_engine_json", "db_json_analisi", "league_id", "home_team_id", "away_team_id")


class CloudSentinella(CloudFinto):
    """Il PostgREST finto con la RPC ``nucleo_sentinella_cloud`` e il trigger ``trg_nucleo_versione_dossier``
    della migrazione (semantica in Python; la prova sul PostgreSQL vero e' in ``test_g2_pg_sentinella.py``)."""

    def __init__(self) -> None:
        super().__init__()
        self.con_rpc = True
        self.sequenza = 0
        self.ora = T0
        self.errore_rpc: Optional[Callable[[httpx.Request], httpx.Response]] = None

    # ------------------------------------------------- scritture del cloud (pg_cron, workflow)
    def scrivi_previsione(self, riga: Dict[str, Any], *, tocca_updated_at: bool = True) -> None:
        """Upsert su ``fixture_predictions`` con il trigger: versione nuova SOLO se cambia il dossier."""
        tab = self.tabelle["fixture_predictions"]
        vecchia = next((r for r in tab if str(r.get("fixture_id")) == str(riga["fixture_id"])), None)
        nuova = {**(vecchia or {}), **riga}
        uguale = vecchia is not None and all(
            json.dumps(vecchia.get(c), sort_keys=True) == json.dumps(nuova.get(c), sort_keys=True)
            for c in COLONNE_DOSSIER)
        if uguale:
            nuova["nucleo_versione"] = vecchia.get("nucleo_versione")
        else:
            self.sequenza += 1
            nuova["nucleo_versione"] = self.sequenza
        if tocca_updated_at:
            nuova["updated_at"] = f"2026-10-10T{int(self.ora) % 86400 // 3600:02d}:{int(self.ora) % 3600 // 60:02d}:" \
                                  f"{int(self.ora) % 60:02d}.{self.sequenza:06d}+00:00"
        if vecchia is None:
            tab.append(nuova)
        else:
            tab[tab.index(vecchia)] = nuova

    def togli_previsione(self, fixture_id: int) -> None:
        self.tabelle["fixture_predictions"] = [r for r in self.tabelle["fixture_predictions"]
                                               if str(r.get("fixture_id")) != str(fixture_id)]

    def ponte(self, tabella: str, event_id: str, fixture_id: Any) -> None:
        tab = self.tabelle[tabella]
        tab[:] = [r for r in tab if r["event_id"] != event_id] + [{"event_id": event_id, "fixture_id": fixture_id}]

    # ------------------------------------------------- RPC della migrazione
    def _rpc(self, nome: str, a: Dict[str, Any]) -> httpx.Response:
        if nome != "nucleo_sentinella_cloud":
            return super()._rpc(nome, a)
        if not self.con_rpc:
            return httpx.Response(404, json=CORPO_PGRST202)
        eventi = list(a.get("p_event_ids") or [])
        if len(eventi) > 500:
            return httpx.Response(400, json={"code": "22023", "details": None, "hint": None,
                                             "message": "nucleo_sentinella_cloud: al massimo 500 eventi per chiamata"})
        omega = None
        if a.get("p_omega", True):
            omega = [json.loads(self._select(t, q).content) for t, q in (
                ("omega_transitions_state", {"select": "updated_at,published_at", "id": "eq.1"}),
                ("omega_ht_ft_transitions", {"select": "built_at", "order": "built_at.desc", "limit": "1"}),
                ("omega_build_jobs", {"select": "job,updated_at", "order": "updated_at.desc", "limit": "1"}))]
        righe = []
        for e in sorted(set(eventi)):
            lf = next((r.get("fixture_id") for r in self.tabelle["live_follow"] if str(r["event_id"]) == e), None)
            oe = next((r.get("fixture_id") for r in self.tabelle["omega_events"] if str(r["event_id"]) == e), None)
            fid = lf if lf is not None else oe                                  # coalesce(live_follow, omega_events)
            prev = [r for r in self.tabelle["fixture_predictions"] if fid is not None
                    and str(r.get("fixture_id")) == str(fid)]
            prev.sort(key=lambda r: (r.get("nucleo_versione") is None, -(r.get("nucleo_versione") or 0)))
            righe.append([e, fid, bool(prev), prev[0].get("nucleo_versione") if prev else None])
        return httpx.Response(200, json={"formato": 1, "omega": omega, "eventi": righe})

    def gestisci(self, req: httpx.Request) -> httpx.Response:
        if self.errore_rpc is not None and req.url.path.endswith("/rpc/nucleo_sentinella_cloud"):
            self.richieste.append((req.method, "/rpc/nucleo_sentinella_cloud", "", None))
            return self.errore_rpc(req)
        return super().gestisci(req)

    def conta_rotte(self, da: int = 0) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for _m, rotta, _q, _c in self.richieste[da:]:
            out[rotta] = out.get(rotta, 0) + 1
        return out


@pytest.fixture
def nuvola(monkeypatch):
    srv = CloudSentinella()

    def crea(_url: str, _key: str, options: Any = None) -> Any:
        return supabase.create_client("https://abc.supabase.co", "x" * 40,
                                      options=ClientOptions(httpx_client=httpx.Client(transport=srv.trasporto())))
    monkeypatch.setattr(db_client, "create_client", crea)
    monkeypatch.setattr(db_client._time, "sleep", lambda _s: None)
    db_client._TLS.client = None            # ripristinato da Betfair/conftest.py
    db_client._STATO_RETE.update({"guasti_di_fila": 0})
    monkeypatch.setattr(omega_service, "_EMPIRICAL_CACHE", {})
    monkeypatch.setattr(omega_service, "_MINUTE_CACHE", {})
    monkeypatch.setattr(dossier, "_EMPIRICAL_CACHE", {})
    monkeypatch.setattr(dossier, "_EMPIRICAL_FAILED", {})
    yield srv
    db_client._STATO_RETE.update({"guasti_di_fila": 0})


def _cliente() -> ClienteCloud:
    return ClienteCloud("bot", dormi=lambda _s: None, casuale=lambda: 0.5)


def _impianto(adesso: List[float], **kw: Any) -> Tuple[K.DossierPrematch, K.SentinellaCloud, K.Sorveglianza]:
    orologio = lambda: adesso[0]  # noqa: E731
    d = K.DossierPrematch(_cliente(), ripiego=mike_db, orologio=orologio)
    s = K.SentinellaCloud(_cliente(), orologio=orologio)
    return d, s, K.Sorveglianza(s, dossier=d, orologio=orologio, **kw)


class _DbConLog:
    """Il ``db`` che Mike passa a ``_retry_dossier``: le letture del dossier (``mike.db`` oggi, il
    ``DossierPrematch`` domani) piu' ``log`` (in Mike e' ``mike.db.log``: qui si registra soltanto)."""

    def __init__(self, base: Any) -> None:
        self._base = base
        self.righe: List[Tuple[Any, ...]] = []

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._base, nome)

    def log(self, *a: Any, **_k: Any) -> None:
        self.righe.append(a)


# ---------------------------------------------------------------------------
# 1. La sentinella: UNA chiamata per giro, ripiego senza la migrazione
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("quanti", [0, 11, 120, 500])
def test_rpc_una_chiamata_per_giro_qualunque_numero_di_eventi(nuvola, quanti):
    eventi = [f"ev{i}" for i in range(1, quanti + 1)]
    s = K.SentinellaCloud(_cliente())
    n = nuvola.conta()
    ist = s.leggi(omega=True, eventi=eventi)
    assert nuvola.conta() - n == 1 and ist.modo == "rpc"
    assert set(ist.impronte or {}) == set(eventi)
    # l'impronta di Omega ha la STESSA forma della sentinella di oggi: cambiare modo non rilegge
    assert ist.omega == K.SorgenteOmega(_cliente()).sentinella()
    assert json.loads(ist.impronte["ev1"])[0] == 101 if quanti else True


def test_oltre_500_eventi_due_chiamate_e_omega_una_volta(nuvola):
    s = K.SentinellaCloud(_cliente())
    eventi = [f"x{i}" for i in range(501)]
    n = nuvola.conta()
    ist = s.leggi(omega=True, eventi=eventi)
    corpi = [r[3] for r in nuvola.richieste[n:]]
    assert len(corpi) == 2 and [c["p_omega"] for c in corpi] == [True, False]
    assert [len(c["p_event_ids"]) for c in corpi] == [500, 1]
    assert len(ist.impronte or {}) == 501 and ist.omega is not None


def test_senza_migrazione_ripiega_sulle_letture_e_riprova_la_rpc(nuvola):
    adesso = [0.0]
    nuvola.con_rpc = False
    s = K.SentinellaCloud(_cliente(), orologio=lambda: adesso[0])
    eventi = ["ev1", "ev2", "ev3", "ev10"]
    n = nuvola.conta()
    ist = s.leggi(omega=True, eventi=eventi)
    rotte = nuvola.conta_rotte(n)
    assert ist.modo == "letture" and s.modo() == "letture"
    # 1 RPC assente + 3 letture della sentinella di Omega + live_follow + omega_events + fixture_predictions
    assert rotte == {"/rpc/nucleo_sentinella_cloud": 1, "/omega_transitions_state": 1, "/omega_ht_ft_transitions": 1,
                     "/omega_build_jobs": 1, "/live_follow": 1, "/omega_events": 1, "/fixture_predictions": 1}
    assert ist.omega == K.SorgenteOmega(_cliente()).sentinella()
    assert set(ist.impronte or {}) == set(eventi)
    adesso[0] = K.RIPROVA_RPC_S - 1
    n = nuvola.conta()
    s.leggi(omega=True, eventi=eventi)
    assert "/rpc/nucleo_sentinella_cloud" not in nuvola.conta_rotte(n) and nuvola.conta() - n == 6
    adesso[0] = K.RIPROVA_RPC_S + 1                                         # 10 minuti: si riprova la RPC
    nuvola.con_rpc = True                                                   # l'utente ha applicato la migrazione
    n = nuvola.conta()
    ist = s.leggi(omega=True, eventi=eventi)
    assert ist.modo == "rpc" and nuvola.conta() - n == 1 and s.modo() == "rpc"


@pytest.mark.parametrize("guasto", ["57014", "503", "rete", "forma", "evento_mancante"])
def test_errore_della_rpc_nessuna_conclusione_e_nessun_cambio_di_modo(nuvola, guasto):
    risposte = {
        "57014": lambda _r: httpx.Response(500, json=CORPO_57014),
        "503": lambda _r: httpx.Response(503, json={"code": "PGRST002", "details": None, "hint": None,
                                                    "message": "schema cache"}),
        "forma": lambda _r: httpx.Response(200, json=[{"eventi": []}]),
        "evento_mancante": lambda _r: httpx.Response(200, json={"formato": 1, "omega": [[], [], []], "eventi": []}),
    }
    if guasto == "rete":
        nuvola.rifiuta_tutto = True
    else:
        nuvola.errore_rpc = risposte[guasto]
    s = K.SentinellaCloud(_cliente())
    ist = s.leggi(omega=True, eventi=["ev1"])
    assert ist == K.Istantanea(None, None, "rpc") and s.modo() == "rpc"
    assert s.statistiche()["errori"] == 1


# ---------------------------------------------------------------------------
# 2. Il dossier: positivo cambiato, negativo che compare, rinnovo, gare, errori
# ---------------------------------------------------------------------------
def test_positivo_cambiato_nel_cloud_arriva_al_giro_dopo(nuvola):
    adesso = [T0]
    d, _s, sorv = _impianto(adesso)
    d.precarica(["ev1", "ev2"])
    assert sorv.giro().cambiati == ("ev1", "ev2")                           # primo giro: impronte registrate
    d.prendi_cambiati(anche_pieni=True)
    assert dossier.build_prematch("ev1", d) == dossier.build_prematch("ev1", mike_db)
    nuvola.scrivi_previsione({**FIXTURE[101], "tactical_engine_json": {"lambda_home": 2.2, "lambda_away": 0.4}})
    adesso[0] += 1.0
    assert dossier.build_prematch("ev1", d) != dossier.build_prematch("ev1", mike_db)   # prima del giro: vecchio
    n = nuvola.conta()
    adesso[0] += K.INTERVALLO_RAPIDO_S - 1.0
    esito = sorv.giro()
    assert esito.cambiati == ("ev1",) and esito.modo == "rpc" and not esito.errore
    rotte = nuvola.conta_rotte(n)
    assert rotte == {"/rpc/nucleo_sentinella_cloud": 1, "/live_follow": 1, "/fixture_predictions": 1}   # SOLO ev1
    prima = d.statistiche()["ripieghi"]
    nuovo = dossier.build_prematch("ev1", d)
    assert nuovo == dossier.build_prematch("ev1", mike_db) and nuovo["lambda_home"] == 2.2
    assert d.statistiche()["ripieghi"] == prima                             # servito dalla memoria
    assert d.prendi_cambiati(anche_pieni=True) == ("ev1",) and d.prendi_cambiati(anche_pieni=True) == ()


def test_riscrittura_identica_non_e_un_cambio(nuvola):
    adesso = [T0]
    d, _s, sorv = _impianto(adesso)
    d.precarica(["ev1"])
    sorv.giro()
    nuvola.scrivi_previsione(dict(FIXTURE[101]))                            # il workflow riscrive uguale
    nuvola.scrivi_previsione({"fixture_id": 101, "status": "ok"})           # colonna fuori dal dossier
    n = nuvola.conta()
    assert sorv.giro().cambiati == () and nuvola.conta() - n == 1


def test_negativo_compare_appena_il_cloud_lo_scrive(nuvola):
    """Evento senza fixture: il cloud scrive il ponte e la previsione; al giro dopo l'evento e' fra i
    cambiati, la memoria e' pronta e il dossier e' identico a quello di mike.db (con i gol attesi)."""
    adesso = [T0]
    d, _s, sorv = _impianto(adesso)
    d.precarica(["ev_nuovo"])
    sorv.giro()
    d.prendi_cambiati(anche_pieni=True)
    assert dossier.build_prematch("ev_nuovo", d)["lambda_home"] is None
    nuvola.scrivi_previsione({**FIXTURE[101], "fixture_id": 301})
    nuvola.ponte("live_follow", "ev_nuovo", 301)
    adesso[0] += K.INTERVALLO_RAPIDO_S
    assert sorv.giro().cambiati == ("ev_nuovo",)
    assert d.prendi_cambiati(anche_pieni=True) == ("ev_nuovo",)
    prima = d.statistiche()["ripieghi"]
    nuovo = dossier.build_prematch("ev_nuovo", d)
    assert nuovo == dossier.build_prematch("ev_nuovo", mike_db) and nuovo["lambda_home"] == TACTICAL_OK["lambda_home"]
    assert d.statistiche()["ripieghi"] == prima


@pytest.mark.parametrize("caso", ["previsione_tolta", "ponte_spostato", "lambda_tolte", "omega_events_dopo"])
def test_ogni_cambio_del_cloud_che_tocca_il_dossier_arriva(nuvola, caso):
    adesso = [T0]
    d, _s, sorv = _impianto(adesso)
    d.precarica(["ev1", "ev2", "ev3"])
    sorv.giro()
    if caso == "previsione_tolta":
        nuvola.togli_previsione(101)
    elif caso == "ponte_spostato":
        nuvola.ponte("live_follow", "ev1", 102)
    elif caso == "lambda_tolte":
        nuvola.scrivi_previsione({**FIXTURE[101], "tactical_engine_json": None, "db_json_analisi": None})
    elif caso == "omega_events_dopo":                                       # ev3: solo omega_events (103 -> 108)
        nuvola.ponte("omega_events", "ev3", 108)
    atteso = "ev3" if caso == "omega_events_dopo" else "ev1"
    adesso[0] += K.INTERVALLO_RAPIDO_S
    assert sorv.giro().cambiati == (atteso,)
    assert dossier.build_prematch(atteso, d) == dossier.build_prematch(atteso, mike_db)


def test_rinnovo_con_la_rpc_e_scadenza_di_300_s_senza(nuvola):
    """Con la RPC (versione garantita dal trigger) la voce resta fresca finche' l'impronta e' la stessa:
    oltre i 300 s nessuna rilettura e nessun ripiego, UNA richiesta per giro. Senza la RPC (letture
    REST, updated_at non garantito) nessun rinnovo: la voce scade a 300 s come oggi (controllo)."""
    for modo in ("rpc", "letture"):
        nuvola.con_rpc = modo == "rpc"
        adesso = [T0]
        d, _s, sorv = _impianto(adesso)
        d.precarica(["ev1"])
        sorv.giro()
        n = nuvola.conta()
        giri = 0
        while adesso[0] < T0 + 1000:
            adesso[0] += sorv.attesa()
            sorv.giro()
            giri += 1
        richieste = nuvola.conta() - n
        prima = d.statistiche()["ripieghi"]
        assert d.fixture_id_for_event("ev1") == 101
        if modo == "rpc":
            assert richieste == giri and d.statistiche()["ripieghi"] == prima      # una per giro, memoria fresca
            assert d.statistiche()["rinnovi"] >= giri
        else:
            assert d.statistiche()["ripieghi"] == prima + 1                        # scaduta: lettura di oggi
            assert d.statistiche()["rinnovi"] == 0


@pytest.mark.parametrize("tabella", ["fixture_predictions", "live_follow"])
def test_gara_lettura_in_volo_non_rimette_il_dossier_vecchio(nuvola, tabella):
    """Il bot precarica ev1 e legge ``tabella``; mentre la risposta (vecchia) e' in volo il cloud ricalcola
    (la previsione, o il ponte) e la sorveglianza rilegge il nuovo; poi arriva la risposta vecchia: NON
    entra in memoria (generazioni per evento e per fixture)."""
    adesso = [T0]
    d, _s, sorv = _impianto(adesso)
    d.precarica(["ev1"])
    sorv.giro()

    class _CloudConGancio:
        def __init__(self, vero: ClienteCloud) -> None:
            self.vero, self.gancio = vero, None

        def leggi(self, nome: str, filtri: Any, *, cache_s: float = 0.0) -> Any:
            righe = self.vero.leggi(nome, filtri, cache_s=cache_s)
            if nome == tabella and self.gancio is not None:
                g, self.gancio = self.gancio, None
                g()
            return righe

        def rpc(self, nome: str, args: Any, *, cache_s: float = 0.0) -> Any:
            return self.vero.rpc(nome, args, cache_s=cache_s)

    lento = _CloudConGancio(_cliente())
    d._cloud = lento                                                         # type: ignore[assignment]

    def nel_mezzo() -> None:
        if tabella == "fixture_predictions":
            nuvola.scrivi_previsione({**FIXTURE[101], "tactical_engine_json": {"lambda_home": 3.3, "lambda_away": 0.3}})
        else:
            nuvola.ponte("live_follow", "ev1", 102)
        adesso[0] += K.INTERVALLO_RAPIDO_S
        assert sorv.giro().cambiati == ("ev1",)

    lento.gancio = nel_mezzo
    d.precarica(["ev1"])                                                     # la lettura vecchia arriva DOPO
    assert d.statistiche()["scartate"] >= 1
    prima = d.statistiche()["ripieghi"]
    assert d.fixture_id_for_event("ev1") == mike_db.fixture_id_for_event("ev1")
    assert dossier.build_prematch("ev1", d) == dossier.build_prematch("ev1", mike_db)
    assert d.statistiche()["ripieghi"] == prima                              # servito dalla memoria, non dal ripiego
    atteso = 3.3 if tabella == "fixture_predictions" else TACTICAL_OK["lambda_home"]
    assert dossier.build_prematch("ev1", d)["lambda_home"] == atteso


def test_rilettura_fallita_non_registra_e_riprova(nuvola):
    adesso = [T0]
    d, _s, sorv = _impianto(adesso)
    d.precarica(["ev1"])
    sorv.giro()
    d.prendi_cambiati(anche_pieni=True)
    nuvola.scrivi_previsione({**FIXTURE[101], "tactical_engine_json": {"lambda_home": 1.9, "lambda_away": 1.1}})
    nuvola.errori[("GET", "/fixture_predictions")] = lambda _r: httpx.Response(503, json={
        "code": "PGRST002", "details": None, "hint": None, "message": "schema cache"})
    adesso[0] += K.INTERVALLO_RAPIDO_S
    assert sorv.giro().cambiati == ()
    assert d.statistiche()["riletture_fallite"] == 1 and d.prendi_cambiati(anche_pieni=True) == ()
    del nuvola.errori[("GET", "/fixture_predictions")]
    # intanto la voce e' tolta: il dossier va alla lettura di oggi, che e' gia' quella nuova
    assert dossier.build_prematch("ev1", d) == dossier.build_prematch("ev1", mike_db)
    adesso[0] += K.INTERVALLO_RAPIDO_S
    assert sorv.giro().cambiati == ("ev1",) and d.prendi_cambiati(anche_pieni=True) == ("ev1",)


def test_eventi_non_piu_seguiti_si_dimenticano(nuvola):
    adesso = [T0]
    d, _s, sorv = _impianto(adesso)
    d.precarica(["ev1", "ev2", "ev3"])
    sorv.giro()
    d.segui(["ev2"])
    n = nuvola.conta()
    sorv.giro()
    assert nuvola.richieste[n][3]["p_event_ids"] == ["ev2"]
    assert set(d._impronte) == {"ev2"}
    d.segui(["ev1", "ev2"])                                                  # torna seguito: impronta nuova
    assert sorv.giro().cambiati == ("ev1",)


def test_al_cambio_riceve_i_cambiati_e_un_suo_errore_non_ferma(nuvola):
    adesso = [T0]
    ricevuti: List[Tuple[str, ...]] = []

    def ascolta(cambiati: Tuple[str, ...]) -> None:
        ricevuti.append(cambiati)
        raise RuntimeError("chi ascolta si rompe")

    d, _s, sorv = _impianto(adesso, al_cambio=ascolta)
    d.precarica(["ev1"])
    assert sorv.giro().cambiati == ("ev1",)
    nuvola.ponte("live_follow", "ev1", 102)
    adesso[0] += 5
    assert sorv.giro().cambiati == ("ev1",)
    assert ricevuti == [("ev1",), ("ev1",)] and sorv.statistiche()["giri"] == 2


def test_sorveglianza_senza_niente_rifiutata():
    with pytest.raises(ValueError):
        K.Sorveglianza(K.SentinellaCloud(_cliente()))


# ---------------------------------------------------------------------------
# 3. MAI piu' lento del codice di oggi (Mike vero, orologio finto)
# ---------------------------------------------------------------------------
ISTANTI = (0, 1, 4, 5, 6, 149, 299, 300, 301, 450, 599, 600, 601, 899, 900)


def _scrivi_scenario(nuvola: CloudSentinella, scenario: str, *, tocca_updated_at: bool = True) -> None:
    if scenario == "ponte":                       # la fixture viene abbinata all'evento
        nuvola.ponte("live_follow", "evS", 101)
    elif scenario == "previsione":                # il ponte c'e', la previsione arriva dopo
        nuvola.scrivi_previsione({**FIXTURE[101], "fixture_id": 205}, tocca_updated_at=tocca_updated_at)
    elif scenario == "lambda":                    # la riga c'e' senza gol attesi, il ricalcolo li aggiunge
        nuvola.scrivi_previsione({**FIXTURE[104], "fixture_id": 206, "tactical_engine_json": TACTICAL_OK},
                                 tocca_updated_at=tocca_updated_at)
    elif scenario == "ripunta":                   # ponte su una fixture cieca, poi abbinato a una piena
        nuvola.ponte("live_follow", "evS", 101)


def _prepara_scenario(nuvola: CloudSentinella, scenario: str) -> None:
    for tabella in ("live_follow", "omega_events"):
        nuvola.tabelle[tabella] = [r for r in nuvola.tabelle[tabella] if r["event_id"] != "evS"]
    nuvola.togli_previsione(205)
    nuvola.togli_previsione(206)
    if scenario == "previsione":
        nuvola.ponte("live_follow", "evS", 205)
    elif scenario in ("lambda", "ripunta"):
        nuvola.ponte("omega_events", "evS", 206)
        nuvola.scrivi_previsione({**FIXTURE[104], "fixture_id": 206})


def _simula(nuvola: CloudSentinella, w: int, scenario: str, *, nuovo: bool, guasto_da: Optional[int] = None,
            tocca_updated_at: bool = True, orizzonte: int = 1300) -> int:
    """Secondo in cui Mike ha i gol attesi dell'evento ``evS``. Oggi: ``_retry_dossier`` con ``mike.db``.
    Domani (aggancio proposto): lo STESSO ``_retry_dossier`` sul ``DossierPrematch``, piu' due righe: gli
    eventi di ``prendi_cambiati(tracked)`` (solo i ciechi) si riprovano SUBITO (``retry_ts`` azzerato).
    ``guasto_da``: da quel secondo la RPC della sentinella risponde 57014 (guasto DOPO i rinnovi)."""
    _prepara_scenario(nuvola, scenario)
    adesso = [T0]
    sorv = d = None
    if nuovo:
        d, _s, sorv = _impianto(adesso)
        db = _DbConLog(d)
    else:
        db = _DbConLog(mike_db)
    tracked = {"evS": {"state": "WATCH", "dossier": dossier.build_prematch("evS", db)}}
    assert tracked["evS"]["dossier"]["lambda_home"] is None
    if d is not None:
        d.segui(tracked)
    prossimo = 0.0
    for t in range(orizzonte):
        adesso[0] = T0 + t
        nuvola.ora = adesso[0]
        if t == guasto_da:
            nuvola.errore_rpc = lambda _r: httpx.Response(500, json=CORPO_57014)
        if t == w:
            _scrivi_scenario(nuvola, scenario, tocca_updated_at=tocca_updated_at)
        if sorv is not None and d is not None and t >= prossimo:
            sorv.giro()
            prossimo = t + sorv.attesa()
            for ev in d.prendi_cambiati(tracked):
                if ev in tracked and mike_service.dossier_da_ritentare(tracked[ev], adesso[0], ogni=0.0):
                    tracked[ev]["dossier"]["retry_ts"] = 0.0
        mike_service._retry_dossier(db, tracked, adesso[0])
        if tracked["evS"]["dossier"].get("lambda_home"):
            nuvola.errore_rpc = None
            assert tracked["evS"]["dossier"] == dossier.build_prematch("evS", mike_db) | {
                "retry_ts": tracked["evS"]["dossier"]["retry_ts"]}
            return t
    nuvola.errore_rpc = None
    return orizzonte


@pytest.mark.parametrize("modo", ["rpc", "letture"])
@pytest.mark.parametrize("scenario", ["ponte", "previsione", "lambda", "ripunta"])
def test_mai_piu_lento_di_oggi_e_latenza_dichiarata(nuvola, modo, scenario):
    assert mike_service._DOSSIER_RETRY_SEC == 300.0
    limite = K.INTERVALLO_RAPIDO_S if modo == "rpc" else K.INTERVALLO_LETTURE_S
    for w in ISTANTI:
        nuvola.con_rpc = True
        oggi = _simula(nuvola, w, scenario, nuovo=False)
        nuvola.con_rpc = modo == "rpc"
        domani = _simula(nuvola, w, scenario, nuovo=True)
        assert oggi == math.ceil(w / 300.0) * 300, (w, oggi)                 # il codice di oggi: ogni 300 s
        assert domani <= oggi, (modo, scenario, w, domani, oggi)
        assert domani - w <= limite, (modo, scenario, w, domani)


@pytest.mark.parametrize("guasto", ["sorveglianza_ko", "updated_at_fermo"])
def test_mai_piu_lento_di_oggi_anche_quando_la_sorveglianza_non_vede(nuvola, guasto):
    """La sorveglianza che non risponde (RPC in errore) o che non puo' vedere il cambio (letture REST e
    uno scrittore che non tocca updated_at): Mike riprova ogni 300 s come oggi, mai dopo."""
    for w in (0, 6, 299, 301, 600):
        nuvola.con_rpc = True
        nuvola.errore_rpc = None
        oggi = _simula(nuvola, w, "lambda", nuovo=False)
        if guasto == "sorveglianza_ko":
            nuvola.errore_rpc = lambda _r: httpx.Response(500, json=CORPO_57014)
            domani = _simula(nuvola, w, "lambda", nuovo=True)
        else:
            nuvola.con_rpc = False
            domani = _simula(nuvola, w, "lambda", nuovo=True, tocca_updated_at=False)
        assert domani <= oggi, (guasto, w, domani, oggi)


@pytest.mark.parametrize("scenario", ["ripunta", "lambda", "ponte"])
@pytest.mark.parametrize("guasto_da", [1, 101, 250, 10_000])
def test_guasto_dopo_i_rinnovi_mai_piu_tardi_di_oggi(nuvola, scenario, guasto_da):
    """Revisione D-G (10/10): la sorveglianza RINNOVA le voci a ogni giro, poi la RPC va in errore. Prima
    della correzione il ponte di un dossier cieco restava in memoria fino a 300 s dall'ULTIMA conferma
    (con guasto a 101 s e ripunta a 150 s: oggi 300, domani 600). Ora: solo i positivi in memoria e,
    dopo un giro fallito, ogni voce torna alla scadenza della sua lettura. Griglia del revisore."""
    for w in (150, 7, 299, 301, 450):
        nuvola.con_rpc = True
        oggi = _simula(nuvola, w, scenario, nuovo=False)
        domani = _simula(nuvola, w, scenario, nuovo=True, guasto_da=guasto_da)
        assert domani <= oggi, (scenario, guasto_da, w, domani, oggi)
        if guasto_da > w + K.INTERVALLO_RAPIDO_S:
            assert domani - w <= K.INTERVALLO_RAPIDO_S, (scenario, guasto_da, w, domani)


# ---------------------------------------------------------------------------
# 4. Omega: la ricostruzione vista in 5 s, gli errori al ritmo di oggi
# ---------------------------------------------------------------------------
def _replica_esterna(adesso: List[float]) -> K.ReplicaEmpirica:
    return K.ReplicaEmpirica(K.SorgenteOmega(_cliente()), ripiego_sincrono=False, orologio=lambda: adesso[0],
                             sentinella_esterna=True)


@pytest.mark.parametrize("w", [0, 3, 5, 151, 299, 301])
def test_omega_ricostruzione_vista_in_5_s_non_in_300(nuvola, w):
    adesso = [0.0]
    r = _replica_esterna(adesso)
    sorv = K.Sorveglianza(K.SentinellaCloud(_cliente(), orologio=lambda: adesso[0]), replica=r,
                          orologio=lambda: adesso[0])
    vecchia = K.ReplicaEmpirica(K.SorgenteOmega(_cliente()), ripiego_sincrono=False)   # oggi: ogni 300 s
    sorv.giro()
    r.drena_coda()
    vecchia.controlla_ricostruzione()
    for x in (r, vecchia):
        x.prefetch_lega(39)
    vista = vista_oggi = None
    for t in range(0, 700):
        adesso[0] = float(t)
        if t == w + 1:                                                        # il pg_cron chiude il giro
            nuvola.notte = costruisci_notte(40 + w, "2026-10-11T04:00:00.170000+00:00")
        if t % int(K.INTERVALLO_RAPIDO_S) == 0:
            sorv.giro()
            r.drena_coda()
            if vista is None and r.statistiche()["ricostruzioni"] == 1:
                vista = t
        if t % int(K.INTERVALLO_SORVEGLIANZA_S) == 0 and vista_oggi is None and vecchia.controlla_ricostruzione():
            vista_oggi = t
    assert vista is not None and vista_oggi is not None
    assert vista <= vista_oggi and vista - (w + 1) <= K.INTERVALLO_RAPIDO_S, (w, vista, vista_oggi)
    assert r.ht_ft_transitions(39) == omega_db.ht_ft_transitions(39)
    assert r.minute_transitions(39, 45, "ft") == omega_db.minute_transitions(39, 45, "ft")


def test_omega_valore_uguale_non_si_riconsegna_e_niente_riletture(nuvola):
    adesso = [0.0]
    r = _replica_esterna(adesso)
    sorv = K.Sorveglianza(K.SentinellaCloud(_cliente()), replica=r, orologio=lambda: adesso[0])
    r.prefetch_lega(39)
    notificate = 0
    for t in range(0, 600, 5):
        adesso[0] = float(t)
        notificate += sorv.giro().omega_notificata
        r.drena_coda()
    assert notificate == 1 and r.statistiche()["ricostruzioni"] == 0       # solo la prima (registra)


def test_omega_errori_consegnati_al_ritmo_di_oggi(nuvola):
    """Sentinella illeggibile per 15 minuti: con giri ogni 5 s la replica riceve "non so" al piu' ogni
    300 s, quindi la rilettura forzata (3 errori di fila) arriva a 600 s come oggi, non dopo 10 s."""
    adesso = [0.0]
    r = _replica_esterna(adesso)
    sorv = K.Sorveglianza(K.SentinellaCloud(_cliente()), replica=r, orologio=lambda: adesso[0])
    sorv.giro()
    r.drena_coda()
    r.prefetch_lega(39)
    nuvola.errore_rpc = lambda _r: httpx.Response(500, json=CORPO_57014)
    forzata = None
    for t in range(5, 900, 5):
        adesso[0] = float(t)
        sorv.giro()
        r.drena_coda()
        if forzata is None and r.statistiche()["riletture_forzate"] == 1:
            forzata = t
    assert forzata is not None and 600 <= forzata < 610
    assert r.statistiche()["riletture_forzate"] == 1
    nuvola.errore_rpc = None                                                 # torna: il valore valido passa
    nuvola.notte = costruisci_notte(77, "2026-10-12T04:00:00.170000+00:00")
    adesso[0] = 905.0
    assert sorv.giro().omega_notificata is True
    r.drena_coda()
    assert r.ht_ft_transitions(39) == omega_db.ht_ft_transitions(39)


# ---------------------------------------------------------------------------
# 5. Thread e carico dichiarato
# ---------------------------------------------------------------------------
def test_thread_della_sorveglianza_avvia_e_ferma(nuvola):
    r = K.ReplicaEmpirica(K.SorgenteOmega(_cliente()), ripiego_sincrono=False, sentinella_esterna=True)
    d = K.DossierPrematch(_cliente(), ripiego=mike_db, replica=r)
    sorv = K.Sorveglianza(K.SentinellaCloud(_cliente()), replica=r, dossier=d, intervallo_s=0.02)
    r.richiedi_prefetch(39)
    d.precarica(["ev1"])
    r.avvia()
    sorv.avvia()
    try:
        assert sorv.vivo() and r.vivo()
        fine = time.monotonic() + 10
        while ((r.statistiche()["chiavi"] < K.CHIAVI_PER_LEGA or r.statistiche()["sentinella"] is None
                or d.statistiche()["cambi"] < 1) and time.monotonic() < fine):
            time.sleep(0.02)                                                 # prefetch fatto, impronte registrate
        nuvola.notte = costruisci_notte(91, "2026-10-13T04:00:00.170000+00:00")
        nuvola.scrivi_previsione({**FIXTURE[101], "tactical_engine_json": {"lambda_home": 2.8, "lambda_away": 0.9}})
        while (r.statistiche()["ricostruzioni"] < 1 or d.statistiche()["cambi"] < 2) and time.monotonic() < fine:
            time.sleep(0.02)
        assert r.statistiche()["ricostruzioni"] == 1 and d.statistiche()["cambi"] >= 2
        assert dossier.build_prematch("ev1", d)["lambda_home"] == 2.8
    finally:
        sorv.ferma()
        r.ferma()
    assert not sorv.vivo() and not r.vivo()
    assert r.ht_ft_transitions(39) == omega_db.ht_ft_transitions(39)


@pytest.mark.parametrize("modo,eventi,attese", [("rpc", 60, 12), ("rpc", 500, 12), ("letture", 50, 4 * 6),
                                                ("letture", 60, 4 * 9), ("letture", 500, 4 * 33)])
def test_carico_dichiarato_richieste_al_minuto(nuvola, modo, eventi, attese):
    """Un minuto di sorveglianza (replica + dossier, nessun cambio): richieste contate al trasporto."""
    nuvola.con_rpc = modo == "rpc"
    adesso = [T0]
    elenco = [f"c{i}" for i in range(eventi)]
    for i, ev in enumerate(elenco):
        nuvola.ponte("live_follow", ev, 1000 + i)
        nuvola.scrivi_previsione({**FIXTURE[101], "fixture_id": 1000 + i})
    r = _replica_esterna(adesso)
    d = K.DossierPrematch(_cliente(), ripiego=mike_db, orologio=lambda: adesso[0])
    sorv = K.Sorveglianza(K.SentinellaCloud(_cliente(), orologio=lambda: adesso[0]), replica=r, dossier=d,
                          orologio=lambda: adesso[0])
    d.segui(elenco)
    sorv.giro()                                                              # impronte registrate
    n = nuvola.conta()
    fine = adesso[0] + 60.0
    adesso[0] += sorv.attesa()
    while adesso[0] <= fine:
        sorv.giro()
        adesso[0] += sorv.attesa()
    assert nuvola.conta() - n == attese, nuvola.conta_rotte(n)


# ---------------------------------------------------------------------------
# 6. Revisione indipendente del 10/10 (D-G): rinnovi, backoff, dossier pieni, tetto, thread veri
# ---------------------------------------------------------------------------
def test_giro_fallito_riporta_le_voci_alla_scadenza_della_lettura(nuvola):
    adesso = [T0]
    d, _s, sorv = _impianto(adesso)
    d.precarica(["ev1"])
    sorv.giro()
    letta = d._lette[("e", "ev1")]
    for _ in range(50):                                                      # 250 s di conferme
        adesso[0] += 5
        sorv.giro()
    assert d._ponte["ev1"][0] == adesso[0] and adesso[0] - letta == 250
    nuvola.errore_rpc = lambda _r: httpx.Response(500, json=CORPO_57014)
    adesso[0] += 5
    assert sorv.giro().errore is True
    assert d._ponte["ev1"][0] == letta and d._fixture[101][0] == d._lette[("f", 101)]
    adesso[0] = letta + K.SCADENZA_DOSSIER_S                                  # 300 s dalla LETTURA: scaduta
    prima = d.statistiche()["ripieghi"]
    nuvola.errore_rpc = None
    assert d.fixture_id_for_event("ev1") == 101 and d.statistiche()["ripieghi"] == prima + 1


@pytest.mark.parametrize("precarica_al", [1, 100, 250])
def test_dossier_cieco_mai_in_memoria_anche_senza_sorveglianza(nuvola, precarica_al):
    """Revisione D-G, punto 1: solo i POSITIVI in memoria. Mike prende in carico evS a 0 s (cieco: ponte su
    206 senza gol attesi), il bot precarica a ``precarica_al``, il cloud ripunta evS su 101 a 150 s, nessuna
    sorveglianza. Il ritento di Mike a 300 s deve trovare il ponte NUOVO, come oggi (mai un ponte cieco
    tenuto in memoria fino a 300 s dalla precarica)."""
    _prepara_scenario(nuvola, "ripunta")
    adesso = [T0]
    d = K.DossierPrematch(_cliente(), ripiego=mike_db, orologio=lambda: adesso[0])
    db = _DbConLog(d)
    tracked = {"evS": {"state": "WATCH", "dossier": dossier.build_prematch("evS", db)}}
    risolto = None
    for t in range(0, 700):
        adesso[0] = T0 + t
        if t == precarica_al:
            d.precarica(["evS"])
            assert ("evS" in d._ponte) == (t > 150)                           # cieco: niente in memoria
        if t == 150:
            nuvola.ponte("live_follow", "evS", 101)
        mike_service._retry_dossier(db, tracked, adesso[0])
        if tracked["evS"]["dossier"].get("lambda_home"):
            risolto = t
            break
    assert risolto == 300


def test_dossier_cieco_e_il_criterio_di_mike():
    voci = [{}, {"dossier": None}, {"dossier": "x"}, {"dossier": {}}, {"dossier": {"lambda_home": 1.2}},
            {"dossier": {"lambda_home": 1.2, "lambda_away": None}}, {"dossier": {"lambda_home": 0, "lambda_away": 1}},
            {"dossier": {"lambda_home": 1.2, "lambda_away": 0.8}},
            {"dossier": {"lambda_home": 1.2, "lambda_away": 0.8, "retry_ts": 5}}]
    for voce in voci:
        ev = {"state": "WATCH", **voce}
        assert K.dossier_cieco(ev) == mike_service.dossier_da_ritentare(ev, T0, ogni=0.0), voce


def test_prendi_cambiati_di_serie_solo_i_ciechi(nuvola):
    """D10-b nel componente: un dossier PIENO non torna fra i cambiati se non lo si chiede esplicitamente."""
    adesso = [T0]
    d, _s, sorv = _impianto(adesso)
    tracked = {"ev1": {"state": "WATCH", "dossier": dossier.build_prematch("ev1", mike_db)},
               "ev5": {"state": "WATCH", "dossier": dossier.build_prematch("ev5", mike_db)}}
    assert not K.dossier_cieco(tracked["ev1"]) and K.dossier_cieco(tracked["ev5"])
    d.segui(tracked)
    sorv.giro()
    with pytest.raises(ValueError):
        d.prendi_cambiati()
    assert d.prendi_cambiati(tracked) == ("ev5",)
    nuvola.scrivi_previsione({**FIXTURE[101], "tactical_engine_json": {"lambda_home": 2.5, "lambda_away": 0.5}})
    nuvola.scrivi_previsione({**FIXTURE[101], "fixture_id": 105})
    adesso[0] += 5
    assert sorv.giro().cambiati == ("ev1", "ev5")
    assert d.prendi_cambiati(tracked) == ("ev5",)                            # ev1 e' pieno: mai restituito
    nuvola.scrivi_previsione({**FIXTURE[101], "tactical_engine_json": {"lambda_home": 2.6, "lambda_away": 0.5}})
    adesso[0] += 5
    sorv.giro()
    assert d.prendi_cambiati(anche_pieni=True) == ("ev1",)                   # solo se chiesto esplicitamente


def _giro_mike(d: K.DossierPrematch, sorv: K.Sorveglianza, tracked: Dict[str, Any], adesso: List[float],
               db: Any) -> int:
    sorv.giro()
    for ev in d.prendi_cambiati(tracked):
        if mike_service.dossier_da_ritentare(tracked[ev], adesso[0], ogni=0.0):
            tracked[ev]["dossier"]["retry_ts"] = 0.0
    return mike_service._retry_dossier(db, tracked, adesso[0])


def test_dossier_pieno_mai_ricostruito_a_partita_armata(nuvola):
    """Test del revisore: il cloud ricalcola il dossier di una partita gia' armata col dossier pieno; il
    nucleo lo sa (memoria nuova) ma il dossier di Mike resta byte per byte quello della presa in carico."""
    adesso = [T0]
    d, _s, sorv = _impianto(adesso)
    db = _DbConLog(d)
    tracked = {"ev1": {"state": "WATCH", "dossier": dossier.build_prematch("ev1", mike_db)}}
    assert tracked["ev1"]["dossier"]["lambda_home"] == TACTICAL_OK["lambda_home"]
    foto = json.dumps(tracked["ev1"]["dossier"], sort_keys=True)
    d.segui(tracked)
    for i in range(6):
        adesso[0] += 5
        if i in (1, 3):
            nuvola.scrivi_previsione({**FIXTURE[101], "tactical_engine_json": {"lambda_home": 2.0 + i, "lambda_away": 0.5}})
        _giro_mike(d, sorv, tracked, adesso, db)
        assert json.dumps(tracked["ev1"]["dossier"], sort_keys=True) == foto, i
    assert dossier.build_prematch("ev1", d)["lambda_home"] == 5.0
    adesso[0] += 400
    _giro_mike(d, sorv, tracked, adesso, db)
    assert json.dumps(tracked["ev1"]["dossier"], sort_keys=True) == foto


@pytest.mark.parametrize("modo", ["rpc", "letture"])
def test_errori_di_fila_backoff_15_30_60_e_ritorno_a_5(nuvola, modo):
    """RPC (o letture) in errore per 10 minuti: attese 15, 30, 60, 60, ... invece di 5 s; al primo giro
    riuscito si torna alla cadenza. Richieste contate al trasporto."""
    nuvola.con_rpc = modo == "rpc"
    adesso = [T0]
    d, _s, sorv = _impianto(adesso)
    d.precarica(["ev1", "ev2"])
    sorv.giro()
    base = sorv.attesa()
    assert base == (K.INTERVALLO_RAPIDO_S if modo == "rpc" else K.INTERVALLO_LETTURE_S)
    rotta = "/rpc/nucleo_sentinella_cloud" if modo == "rpc" else "/live_follow"
    if modo == "rpc":
        nuvola.errore_rpc = lambda _r: httpx.Response(500, json=CORPO_57014)
    else:
        nuvola.errori[("GET", "/live_follow")] = lambda _r: httpx.Response(500, json=CORPO_57014)
    n = nuvola.conta()
    attese, fine = [], adesso[0] + 600
    while adesso[0] < fine:
        assert sorv.giro().errore is True
        attese.append(sorv.attesa())
        adesso[0] += attese[-1]
    assert attese[:4] == [15.0, 30.0, 60.0, 60.0] and set(attese[3:]) == {60.0}
    giri = len(attese)
    assert giri == 12 and nuvola.conta_rotte(n)[rotta] == giri              # oggi senza backoff: 120 (rpc)
    nuvola.errore_rpc = None
    nuvola.errori.pop(("GET", "/live_follow"), None)
    assert sorv.giro().errore is False and sorv.attesa() == base


def test_scadenza_massima_anche_con_la_rpc(nuvola):
    """Uno scrittore che AGGIRA il trigger (replica, DISABLE TRIGGER, ALTER TYPE) cambia il dossier senza
    versione nuova: la RPC non lo vede. La voce rinnovata non vive oltre SCADENZA_MASSIMA_S dalla lettura:
    allora si rilegge comunque e il dossier torna uguale a mike.db."""
    adesso = [T0]
    d, _s, sorv = _impianto(adesso)
    d.precarica(["ev1"])
    sorv.giro()
    riga = next(r for r in nuvola.tabelle["fixture_predictions"] if r["fixture_id"] == 101)
    riga["tactical_engine_json"] = {"lambda_home": 2.9, "lambda_away": 0.2}    # nessuna versione nuova
    n = nuvola.conta()
    giri = 0
    rilettura = T0 + 3300.0              # 55 minuti (scritti letterali): si rilegge PRIMA della scadenza dura di 60
    while adesso[0] + 5 <= rilettura:
        adesso[0] += 5
        sorv.giro()
        giri += 1
    assert nuvola.conta() - n == giri                                        # solo la RPC: nessuna rilettura
    assert dossier.build_prematch("ev1", d)["lambda_home"] == TACTICAL_OK["lambda_home"]   # vecchio (controllo)
    while adesso[0] < rilettura + 10:
        adesso[0] += 5
        sorv.giro()
    prima = d.statistiche()["ripieghi"]
    assert dossier.build_prematch("ev1", d) == dossier.build_prematch("ev1", mike_db)
    assert dossier.build_prematch("ev1", d)["lambda_home"] == 2.9 and d.statistiche()["ripieghi"] == prima


class _CloudSospeso:
    """Il Cloud vero, ma la lettura di ``tabella`` fatta dal thread "lettore" si FERMA dopo aver ricevuto la
    risposta (vecchia) finche' non e' liberata: un'altra lettura e' davvero in volo in un altro thread."""

    def __init__(self, vero: ClienteCloud, tabella: str) -> None:
        self.vero, self.tabella = vero, tabella
        self.arrivata, self.libera = threading.Event(), threading.Event()
        self.attivo = True

    def leggi(self, nome: str, filtri: Any, *, cache_s: float = 0.0) -> Any:
        righe = self.vero.leggi(nome, filtri, cache_s=cache_s)
        if nome == self.tabella and self.attivo and threading.current_thread().name == "lettore":
            self.attivo = False
            self.arrivata.set()
            assert self.libera.wait(10)
        return righe

    def rpc(self, nome: str, args: Any, *, cache_s: float = 0.0) -> Any:
        return self.vero.rpc(nome, args, cache_s=cache_s)


@pytest.mark.parametrize("tabella", ["fixture_predictions", "live_follow"])
def test_thread_veri_lettura_in_volo_scartata(nuvola, tabella):
    adesso = [T0]
    d, _s, sorv = _impianto(adesso)
    d.precarica(["ev1"])
    sorv.giro()
    sospeso = _CloudSospeso(_cliente(), tabella)
    d._cloud = sospeso                                                       # type: ignore[assignment]
    lettore = threading.Thread(target=lambda: d.precarica(["ev1"]), name="lettore")
    lettore.start()
    try:
        assert sospeso.arrivata.wait(10)
        if tabella == "fixture_predictions":
            nuvola.scrivi_previsione({**FIXTURE[101], "tactical_engine_json": {"lambda_home": 3.3, "lambda_away": 0.3}})
        else:
            nuvola.ponte("live_follow", "ev1", 102)
        adesso[0] += 5
        assert sorv.giro().cambiati == ("ev1",)
    finally:
        sospeso.libera.set()
        lettore.join(10)
    assert not lettore.is_alive()
    assert dossier.build_prematch("ev1", d) == dossier.build_prematch("ev1", mike_db)


def test_thread_veri_scrittori_lettori_e_sorveglianza_convergono(nuvola):
    """Scrittori nel cloud, due precarica e la sorveglianza in thread veri per 2 s: a cloud fermo, dopo tre
    giri, ogni dossier e' identico a mike.db."""
    adesso = [T0]
    blocco = threading.Lock()
    d, _s, sorv = _impianto(adesso)
    nuvola.ponte("live_follow", "evA", 101)
    nuvola.ponte("live_follow", "evB", 102)
    nuvola.scrivi_previsione({**FIXTURE[102], "tactical_engine_json": {"lambda_home": 1.0, "lambda_away": 1.0}})
    d.segui(["evA", "evB"])
    ferma = threading.Event()
    errori: List[BaseException] = []

    def scrittore() -> None:
        i = 0
        while not ferma.is_set():
            i += 1
            with blocco:
                nuvola.scrivi_previsione({**FIXTURE[101], "tactical_engine_json": {"lambda_home": 1 + i / 1000,
                                                                                  "lambda_away": 1.0}})
                if i % 3 == 0:
                    nuvola.ponte("live_follow", "evB", 102 if i % 2 else 101)
            time.sleep(0.001)

    def ripeti(f: Callable[[], Any]) -> Callable[[], None]:
        def corpo() -> None:
            while not ferma.is_set():
                try:
                    f()
                except Exception as ex:  # noqa: BLE001 - raccolto e controllato sotto
                    errori.append(ex)
        return corpo

    def giro() -> None:
        sorv.giro()
        adesso[0] += 1

    fili = [threading.Thread(target=x) for x in (scrittore, ripeti(lambda: d.precarica(["evA", "evB"])),
                                                 ripeti(lambda: d.precarica(["evA", "evB"])), ripeti(giro))]
    for f in fili:
        f.start()
    time.sleep(2.0)
    ferma.set()
    for f in fili:
        f.join(10)
    assert not errori, errori[:2]
    for _ in range(3):
        adesso[0] += 5
        sorv.giro()
    for ev in ("evA", "evB"):
        assert dossier.build_prematch(ev, d) == dossier.build_prematch(ev, mike_db), ev


@pytest.mark.parametrize("modo", ["rpc", "letture"])
def test_parita_su_una_passeggiata_casuale_del_cloud(nuvola, modo):
    """Test del revisore: 60 passi casuali (seme fisso) di scritture nel cloud; a ogni giro il dossier di
    ogni evento e' identico a quello di mike.db."""
    import random
    nuvola.con_rpc = modo == "rpc"
    rnd = random.Random(7)
    adesso = [T0]
    d, _s, sorv = _impianto(adesso)
    eventi = [f"ev{i}" for i in range(1, 12)] + ["ev_nuovo"]
    d.segui(eventi)
    sorv.giro()
    for passo in range(60):
        adesso[0] += sorv.attesa()
        azione = rnd.choice(["prev", "prev_stessa", "ponte", "togli", "niente"])
        fid = rnd.choice([101, 102, 103, 104, 106, 301])
        if azione == "prev":
            nuvola.scrivi_previsione({**FIXTURE.get(fid, FIXTURE[101]), "fixture_id": fid,
                                      "tactical_engine_json": rnd.choice([None, {"lambda_home": rnd.random() + .1,
                                                                                 "lambda_away": rnd.random() + .1}])})
        elif azione == "prev_stessa" and fid in FIXTURE:
            nuvola.scrivi_previsione(dict(FIXTURE[fid]))
        elif azione == "ponte":
            nuvola.ponte(rnd.choice(["live_follow", "omega_events"]), rnd.choice(eventi), rnd.choice([101, 102, 301, None]))
        elif azione == "togli":
            nuvola.togli_previsione(fid)
        sorv.giro()
        for ev in eventi:
            assert dossier.build_prematch(ev, d) == dossier.build_prematch(ev, mike_db), (passo, azione, ev)
