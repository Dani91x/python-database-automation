"""api_quota.py - Gestore della quota giornaliera di API-Football (25/09/2026).

Ordine dell'utente: "NON superiamo la quota limite" e "il calcolo dei consumi va
fatto DOPO OGNI LEGA per capire quanto margine abbiamo".

Fonti del contatore del giorno (in quest'ordine):
  1. GET /status di API-Football (accesso diretto v3.football.api-sports.io con
     header x-apisports-key): contatore UFFICIALE `response.requests.current` e
     `response.requests.limit_day`. Da documentazione /status NON consuma quota.
     Chiamata con `requests` diretto (non con APIFootballClient): cosi' non entra
     in api_call_log e non falsa la controprova.
  2. ultimi header `x-ratelimit-requests-limit/remaining` letti dal client
     (solo a lavoro avviato: al primo controllo non ci sono ancora);
  3. controprova/fallback: conteggio di `api_call_log` nel giorno UTC (tutte le
     nostre action scrivono li'), con AVVISO: vede solo le chiamate di questo
     repo e puo' perdere gli ultimi record non ancora scritti.
Se NESSUNA fonte e' leggibile -> QuotaNonLeggibile: non si parte (fail-loud).

Formula:  margine = limit_day - current - riserva
  riserva = API_FOOTBALL_RISERVA_GIORNALIERA (default 3000): chiamate lasciate
  alle action giornaliere (Daily + Today Predictions + Results), p90 misurato
  ~2.700/giorno negli ultimi 9 giorni.
Regola: una lega-stagione parte SOLO se margine >= costo stimato; dopo ogni
lega-stagione si rilegge il contatore.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import requests

API_STATUS_URL = "https://v3.football.api-sports.io/status"
RISERVA_DEFAULT = 3000
LIMITE_DEFAULT = 7500          # piano Pro (usato SOLO se /status non risponde)
FINESTRA_ID_LOG = 20000        # righe di api_call_log esaminate (per PK) per trovare l'inizio del giorno
HEADER_VALIDI_SEC = 15 * 60    # header piu' vecchi di cosi' non valgono come fonte


class QuotaNonLeggibile(RuntimeError):
    """Nessuna fonte del contatore API disponibile: non si parte."""


@dataclass
class StatoQuota:
    current: int
    limit_day: int
    riserva: int
    fonte: str
    avvisi: List[str] = field(default_factory=list)
    controprova_log: Optional[int] = None
    letto_at: str = ""

    @property
    def margine(self) -> int:
        return self.limit_day - self.current - self.riserva

    def riga(self) -> str:
        return (f"contatore API {self.current}/{self.limit_day} (fonte {self.fonte}), "
                f"riserva action {self.riserva}, margine {self.margine}")


def leggi_riserva(env: Optional[Dict[str, str]] = None) -> int:
    env = os.environ if env is None else env
    grezzo = (env.get("API_FOOTBALL_RISERVA_GIORNALIERA") or "").strip()
    if not grezzo:
        return RISERVA_DEFAULT
    try:
        valore = int(grezzo)
    except ValueError as e:
        raise ValueError(f"API_FOOTBALL_RISERVA_GIORNALIERA non intera: {grezzo!r}") from e
    if valore < 0:
        raise ValueError(f"API_FOOTBALL_RISERVA_GIORNALIERA negativa: {valore}")
    return valore


def _limite_env(env: Optional[Dict[str, str]] = None) -> int:
    env = os.environ if env is None else env
    grezzo = (env.get("API_FOOTBALL_LIMITE_GIORNALIERO") or "").strip()
    return int(grezzo) if grezzo else LIMITE_DEFAULT


def leggi_status_api(api_key: Optional[str], http_get: Callable[..., Any] = requests.get,
                     timeout: int = 15) -> Dict[str, int]:
    """GET /status -> {"current": int, "limit_day": int}. Solleva su qualunque problema."""
    if not api_key:
        raise RuntimeError("API_FOOTBALL_KEY assente")
    resp = http_get(API_STATUS_URL, headers={"x-apisports-key": api_key,
                                             "Accept": "application/json"}, timeout=timeout)
    if getattr(resp, "status_code", 0) != 200:
        raise RuntimeError(f"/status HTTP {getattr(resp, 'status_code', '?')}")
    data = resp.json() or {}
    errori = data.get("errors")
    if errori:
        raise RuntimeError(f"/status errors: {errori}")
    richieste = ((data.get("response") or {}) if isinstance(data.get("response"), dict) else {}).get("requests") or {}
    current, limite = richieste.get("current"), richieste.get("limit_day")
    if not isinstance(current, int) or not isinstance(limite, int) or limite <= 0:
        raise RuntimeError(f"/status senza requests.current/limit_day validi: {richieste!r}")
    return {"current": current, "limit_day": limite}


def conta_log_oggi(sb: Any, adesso: Optional[datetime] = None) -> int:
    """Chiamate registrate in api_call_log dal 00:00 UTC di oggi.

    IO minimo su una tabella da ~3M righe senza indice noto su created_at:
    1) max(id) via PK (order desc limit 1);
    2) count esatto su id > max-FINESTRA (range di PK) E created_at >= oggi.
    Il piano Pro ha 7.500 chiamate/giorno: la finestra di 20.000 id copre il
    giorno intero (retry compresi); se la finestra fosse tutta "di oggi" si
    avvisa che il numero e' un minimo.
    """
    try:
        from logger import flush_api_log  # scrive i record ancora in buffer
        flush_api_log()
    except Exception:
        pass
    adesso = adesso or datetime.now(timezone.utc)
    inizio = adesso.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    ultimo = sb.table("api_call_log").select("id").order("id", desc=True).limit(1).execute()
    righe = getattr(ultimo, "data", None) or []
    if not righe:
        return 0
    max_id = int(righe[0]["id"])
    resp = (sb.table("api_call_log").select("id", count="exact")
            .gt("id", max_id - FINESTRA_ID_LOG).gte("created_at", inizio)
            .limit(1).execute())
    n = getattr(resp, "count", None)
    if not isinstance(n, int):
        raise RuntimeError("api_call_log: count non restituito")
    return n


class GestoreQuota:
    """Controllo PRIMA di ogni lega-stagione, ricalcolo DOPO (e ogni tanto durante)."""

    def __init__(self, sb: Any = None, api_key: Optional[str] = None,
                 client: Any = None, riserva: Optional[int] = None,
                 http_get: Callable[..., Any] = requests.get,
                 env: Optional[Dict[str, str]] = None,
                 stampa: Callable[[str], None] = print) -> None:
        self.sb = sb
        self.api_key = api_key
        self.client = client
        self.env = env
        self.riserva = leggi_riserva(env) if riserva is None else riserva
        self.http_get = http_get
        self.stampa = stampa
        self.stato: Optional[StatoQuota] = None
        self._richieste_client_al_ricalcolo = 0
        self._esterne = 0

    def aggiungi_chiamate_esterne(self, n: int) -> None:
        """Chiamate fatte da altri client (fixtures/aggregati) dall'ultimo ricalcolo."""
        self._esterne += int(n)

    # -- lettura ------------------------------------------------------------
    def aggiorna(self) -> StatoQuota:
        avvisi: List[str] = []
        stato: Optional[StatoQuota] = None
        adesso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            st = leggi_status_api(self.api_key, self.http_get)
            stato = StatoQuota(st["current"], st["limit_day"], self.riserva, "/status", avvisi, None, adesso)
        except Exception as e:
            avvisi.append(f"/status non leggibile ({e})")
        if stato is None and self.client is not None:
            rl = getattr(self.client, "ultimo_ratelimit", None)
            if rl and time.time() - float(rl.get("at", 0)) <= HEADER_VALIDI_SEC:
                stato = StatoQuota(int(rl["limit_day"]) - int(rl["remaining"]), int(rl["limit_day"]),
                                   self.riserva, "header x-ratelimit", avvisi, None, adesso)
        # controprova (o fallback) da api_call_log
        n_log: Optional[int] = None
        if self.sb is not None:
            try:
                n_log = conta_log_oggi(self.sb)
            except Exception as e:
                avvisi.append(f"api_call_log non leggibile ({e})")
        if stato is None and n_log is not None:
            avvisi.append("AVVISO: contatore da api_call_log (solo chiamate di questo repo, "
                          "limite da API_FOOTBALL_LIMITE_GIORNALIERO)")
            stato = StatoQuota(n_log, _limite_env(self.env), self.riserva, "api_call_log", avvisi, n_log, adesso)
        if stato is None:
            raise QuotaNonLeggibile("contatore API non leggibile da nessuna fonte: " + "; ".join(avvisi))
        stato.controprova_log = n_log
        if stato.fonte != "api_call_log" and n_log is not None and n_log > stato.current + 50:
            avvisi.append(f"controprova: api_call_log conta {n_log} > contatore {stato.current}")
        for a in avvisi:
            self.stampa(f"[QUOTA] {a}")
        self.stato = stato
        self._richieste_client_al_ricalcolo = self._richieste_client()
        self._esterne = 0
        return stato

    def _richieste_client(self) -> int:
        return int(getattr(self.client, "richieste_http", 0) or 0) if self.client is not None else 0

    # -- decisioni ----------------------------------------------------------
    def margine(self) -> int:
        """Margine stimato ORA: ultimo contatore letto meno le richieste fatte dal
        client da allora (le altre action vengono viste al prossimo ricalcolo)."""
        if self.stato is None:
            self.aggiorna()
        assert self.stato is not None
        return (self.stato.margine - (self._richieste_client() - self._richieste_client_al_ricalcolo)
                - self._esterne)

    def capacita_giornaliera(self) -> int:
        if self.stato is None:
            self.aggiorna()
        assert self.stato is not None
        return self.stato.limit_day - self.riserva

    def copre(self, costo: int) -> bool:
        return self.margine() >= costo
