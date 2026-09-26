"""FIX-C (26/09/2026) - scalper-service e sessioni scalper dopo una caduta di rete.

Reperti (inventario FIX-C, `AUDIT_2026-09-25/FIX_C_RESILIENZA_RETE_2026-09-26.md`):
  * ``scalper_session.run_session``: il keep-alive era ``wait(600)`` +
    ``auth.keep_alive`` (che ingoia l'errore): un keepAlive caduto a rete giu'
    si ritentava dopo 600 s, cioe' sulla scadenza dei 20' della sessione .it, e
    nessuno rifaceva il login (nemmeno il worker di flumine). In LIVE: place,
    cancel, force-flat e la riconnessione degli stream fallivano per sempre;
  * ``scalper_service.ferma_sessioni_al_nuovo_avvio``: una lettura KO all'avvio
    valeva "fatto" e, tornata la rete, le righe 'requested' di un avvio
    precedente diventavano sessioni;
  * ``scalper_service.main``: dopo un riavvio del supervisore (figli non
    registrati) una sessione VIVA con il battito vecchio per la caduta di rete
    veniva messa in 'error' (force-flat) al primo giro.

I finti del client hanno i tipi veri di betfairlightweight (``APIError`` con
``requests.ConnectionError`` a rete giu', ``KeepAliveError`` NO_SESSION).
"""
from __future__ import annotations

import inspect
from typing import List

import requests
from betfairlightweight.exceptions import APIError, KeepAliveError

from Betfair.stream.scalper import scalper_service as SS
from Betfair.stream.scalper import scalper_session as SSN


class Orologio:
    def __init__(self) -> None:
        self.t = 5000.0
        self.giu = False


class TradingFinto:
    """``betfairlightweight.APIClient`` .it: sessione valida 1200 s dall'ultimo
    keepAlive/login riuscito."""

    session_timeout = 20 * 60

    def __init__(self, o: Orologio) -> None:
        self.o = o
        self.session_token = "T1"
        self._rinnovata = o.t
        self.chiamate: List[str] = []

    def valida(self) -> bool:
        return self.o.t - self._rinnovata < self.session_timeout

    def keep_alive(self):
        self.chiamate.append("keep_alive")
        if self.o.giu:
            raise APIError(None, exception=requests.ConnectionError("getaddrinfo failed"))
        if not self.valida():
            raise KeepAliveError({"token": self.session_token, "status": "FAIL",
                                  "error": "NO_SESSION"})
        self._rinnovata = self.o.t

    def login(self):
        self.chiamate.append("login")
        if self.o.giu:
            raise APIError(None, exception=requests.ConnectionError("getaddrinfo failed"))
        self.session_token = "T2"
        self._rinnovata = self.o.t


class StopFinto:
    """``threading.Event`` con il tempo simulato: ``wait`` fa avanzare
    l'orologio e alza lo stop a ``fine``; la rete e' giu' in [giu_da, giu_a)."""

    def __init__(self, o: Orologio, fine: float, giu_da=None, giu_a=None, tr=None) -> None:
        self.o, self.fine, self.giu_da, self.giu_a = o, fine, giu_da, giu_a
        self.tr = tr
        self.cieco = 0.0          # secondi a rete SU con la sessione scaduta

    def wait(self, s: float) -> bool:
        self.o.t += s
        self.o.giu = self.giu_da is not None and self.giu_da <= self.o.t < self.giu_a
        if self.tr is not None and not self.o.giu and not self.tr.valida():
            self.cieco += s
        return self.o.t >= self.fine


def test_sessione_scalper_sopravvive_alla_rete_giu_al_keepalive():
    o = Orologio()
    tr = TradingFinto(o)
    t0 = o.t
    stop = StopFinto(o, fine=t0 + 3 * 3600, giu_da=t0 + 595, giu_a=t0 + 655, tr=tr)
    custode = SSN.mantieni_sessione(tr, stop, ora=lambda: o.t)
    assert stop.cieco == 0.0, f"sessione LIVE scaduta per {stop.cieco:.0f}s a rete su"
    assert tr.valida(), "sessione LIVE dello scalper scaduta dopo la caduta"
    assert custode.fallimenti == 0


def test_sessione_scalper_a_regime_un_keepalive_ogni_600s():
    o = Orologio()
    tr = TradingFinto(o)
    stop = StopFinto(o, fine=o.t + 3 * 3600)
    SSN.mantieni_sessione(tr, stop, ora=lambda: o.t)
    assert tr.chiamate.count("login") == 0
    assert tr.chiamate.count("keep_alive") in (17, 18)      # 3 h / 600 s


def test_sessione_scalper_scaduta_rifa_il_login():
    o = Orologio()
    tr = TradingFinto(o)
    t0 = o.t
    stop = StopFinto(o, fine=t0 + 3 * 3600, giu_da=t0 + 595, giu_a=t0 + 595 + 1800)
    SSN.mantieni_sessione(tr, stop, ora=lambda: o.t)
    assert tr.valida() and "login" in tr.chiamate and tr.session_token == "T2"


# ---------------------------------------------------------------------------
# supervisore: controllo d'avvio ritentato, orfane giudicate solo a DB sano
# ---------------------------------------------------------------------------
class DbKo:
    def controls(self):
        raise requests.ConnectionError("getaddrinfo failed")


class DbVuoto:
    def controls(self):
        return []


def test_controllo_avvio_ko_non_vale_fatto():
    assert SS.controllo_avvio(DbKo(), boot_id="OGGI") is None
    assert SS.controllo_avvio(DbVuoto(), boot_id="OGGI") == []
    # compatibilita': la funzione storica resta una lista
    assert SS.ferma_sessioni_al_nuovo_avvio(DbKo(), boot_id="OGGI") == []


def test_orfane_giudicabili_solo_dopo_un_minuto_di_db_sano():
    assert SS.orfane_giudicabili(None, 1000.0) is False
    assert SS.orfane_giudicabili(1000.0, 1000.0 + SS.ORPHAN_HEARTBEAT_S - 1) is False
    assert SS.orfane_giudicabili(1000.0, 1000.0 + SS.ORPHAN_HEARTBEAT_S) is True


def test_main_usa_il_controllo_ritentato_e_la_grazia():
    """Il loop del supervisore e' infinito: si verifica il cablaggio."""
    src = inspect.getsource(SS.main)
    assert "avvio_concluso = controllo_avvio(db) is not None" in src
    assert "if avvio_concluso and sessione_da_avviare(row, alive, freno):" in src
    assert "giudicabili and _stopping_zombie(row)" in src
    assert 'status in ("running", "arming") and not alive and giudicabili' in src
    assert "db_sano_dal = None" in src
