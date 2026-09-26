"""valuta.py - le size dello STREAM Betfair sono in GBP: qui, e SOLO qui, diventano EUR.

K1 (26/09/2026, test e2e FASE 2, `AUDIT_2026-09-25/e2e_fase2/ADMIN26_FEED_ATLANTE.md`):
Betfair Exchange Stream API, "Market subscriptions are always in underlying
exchange currency - GBP". Il conto e' in EUR: gli ordini (REST e flumine) sono in
EUR, le size del libro viste dallo stream erano in GBP e nessuno le convertiva
(misura: size scan / size REST mediana 0,8599 su 94 coppie). Liquidita' e
controparte risultavano sottostimate del ~14 % e in 5 punti l'errore NON era
prudente (chiusure piu' piccole del libro, copertura trattenuta, uscita non
proposta, "approva" disabilitato, pavimento del green-up saltato).

UN SOLO PUNTO DI CONVERSIONE, ALLA FONTE, con UNA sola funzione (`converti_libro`):
  * flumine (runner calcio, runner tennis, sessioni scalper, BANCO di replay):
    `MiddlewareValutaEur`, montato PRIMO fra i middleware (`monta_su_flumine`),
    quindi prima del `SimulatedMiddleware` (paper) e prima di ogni strategia;
  * scanner del feed unico (`Betfair/safe_strategy/stream.py`, betfairlightweight
    diretto): `StreamShard.drain`.
Il REST (`listMarketBook` senza currencyCode = valuta del conto) e' GIA' in EUR e
NON passa mai di qui: nessuna doppia conversione.
Le REGISTRAZIONI raw restano in GBP (dato nativo Betfair): il banco applica la
stessa conversione nello stesso punto (middleware), a cambio FISSO per la
riproducibilita' dei referti.

Il cambio: `listCurrencyRates` (fromCurrency GBP -> rate EUR per 1 GBP), letto
all'avvio e ogni ora, con cache su disco. Regola dell'utente (brief K1): se non
si legge, ultimo cambio noto + alert WARN; se non esiste nessun cambio noto,
`CAMBIO_RIPIEGO` + alert CRITICAL "cambio non letto". Il cambio non fa MAI
cadere un processo.

Il cambio si CONGELA PER MERCATO (il primo visto): il `SimulatedMiddleware`
abbina gli ordini paper sul DELTA del `traded_volume` fra un book e il
successivo; un cambio che si muovesse a meta' mercato creerebbe volume fantasma
(size x delta cambio) a ogni prezzo.

ATTENZIONE: Mai modificare i livelli IN PLACE: con flumine importato
(`flumine/__init__.py`: `RunnerBookEX = EX`) `ex.available_to_back` e' la STESSA
lista di dict della cache di betfairlightweight, e i `RunnerBook` sono condivisi
fra un book e il successivo (`RunnerBookCache.serialise` memorizza la risorsa).
Qui si sostituiscono le liste con liste NUOVE (`_LivelliEur`) e si marca il
runner: la conversione e' idempotente per oggetto.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("valuta")

# EUR/GBP 0,8586 del 23/09/2026 (exchangerates.org.uk, referto K1 sez. K1.3) -> EUR
# per 1 GBP. SOLO ripiego quando nessun cambio e' mai stato letto.
CAMBIO_RIPIEGO: float = round(1.0 / 0.8586, 6)
CAMBIO_RIPIEGO_DATA = "2026-09-23"
RINFRESCO_S: float = 3600.0
# un cambio fuori da questa banda non e' un cambio EUR/GBP: si scarta
_BANDA_PLAUSIBILE = (0.9, 1.6)
VALUTA_CONTO = "EUR"
NOME_FILE_CACHE = "currency_rate.json"
_TETTO_MERCATI = 20000


class _LivelliEur(list):
    """Lista di livelli GIA' convertita in EUR (marcatore per tipo)."""


def _nuovo_livello(liv: Any, r: float) -> Any:
    """Copia del livello con la size in EUR (stessa forma dell'originale)."""
    if isinstance(liv, dict):
        nuovo = dict(liv)
        if nuovo.get("size") is not None:
            nuovo["size"] = round(float(nuovo["size"]) * r, 2)
        return nuovo
    if isinstance(liv, (list, tuple)):
        if len(liv) >= 2 and liv[1] is not None:
            return type(liv)([liv[0], round(float(liv[1]) * r, 2), *liv[2:]])
        return liv
    prezzo = getattr(liv, "price", None)
    size = getattr(liv, "size", None)
    try:
        from betfairlightweight.resources.bettingresources import PriceSize
        return PriceSize(prezzo, round(float(size) * r, 2) if size is not None else size)
    except Exception:  # noqa: BLE001 - forma sconosciuta: copia e sostituisci
        import copy

        nuovo = copy.copy(liv)
        if size is not None:
            nuovo.size = round(float(size) * r, 2)
        return nuovo


def _livelli(livelli: Any, r: float) -> Any:
    if livelli is None or isinstance(livelli, _LivelliEur):
        return livelli
    return _LivelliEur(_nuovo_livello(x, r) for x in livelli)


def _importo(v: Any, r: float) -> Any:
    if v is None:
        return None
    try:
        return round(float(v) * r, 2)
    except (TypeError, ValueError):
        return v


def _alert_db(livello: str, messaggio: str) -> None:
    try:
        from . import db

        db.insert_alert(livello, "CAMBIO_GBP_EUR", messaggio)
    except Exception:  # noqa: BLE001 - alert best-effort
        pass


def percorso_cache_predefinito() -> str:
    from .config_stream import DATA_DIR

    return os.path.join(DATA_DIR, NOME_FILE_CACHE)


class CambioGbpEur:
    """Il cambio EUR per 1 GBP, con fonte dichiarata."""

    def __init__(self, percorso_cache: Optional[str] = None,
                 alert: Optional[Callable[[str, str], None]] = None,
                 fisso: Optional[float] = None) -> None:
        self._percorso = percorso_cache
        self._alert = alert or _alert_db
        self._lock = threading.RLock()
        self._per_mercato: Dict[str, float] = {}
        self._thread: Optional[threading.Thread] = None
        self.letto_at: Optional[float] = None
        self.fisso = fisso is not None
        # la cache su disco si legge al PRIMO uso, non all'import (l'import
        # non deve toccare disco ne' `config_stream`/.env)
        self._caricato = fisso is not None
        if fisso is not None:
            self.rate, self.fonte = float(fisso), "fisso"
        else:
            self.rate, self.fonte = CAMBIO_RIPIEGO, "costante"

    # ------------------------------------------------------------- cache
    def percorso(self) -> str:
        return self._percorso or percorso_cache_predefinito()

    def _assicura_caricato(self) -> None:
        with self._lock:
            if not self._caricato:
                self._caricato = True
                self._carica_cache()

    def _carica_cache(self) -> None:
        try:
            with open(self.percorso(), "r", encoding="utf-8") as fh:
                d = json.load(fh)
            r = float(d["rate"])
            if _BANDA_PLAUSIBILE[0] <= r <= _BANDA_PLAUSIBILE[1]:
                self.rate, self.fonte = r, "cache"
                self.letto_at = float(d.get("letto_at") or 0.0) or None
        except Exception:  # noqa: BLE001 - nessuna cache: resta il ripiego
            pass

    def _scrivi_cache(self) -> None:
        try:
            p = self.percorso()
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            tmp = f"{p}.{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"rate": self.rate, "da": "GBP", "a": VALUTA_CONTO,
                           "letto_at": self.letto_at, "fonte": "listCurrencyRates"}, fh)
            os.replace(tmp, p)
        except Exception as e:  # noqa: BLE001 - la cache non ferma niente
            logger.warning("[valuta] cache cambio non scritta: %s", e)

    # ------------------------------------------------------------- lettura
    @staticmethod
    def _leggi_da_betfair(client: Any) -> float:
        righe = client.account.list_currency_rates(from_currency="GBP")
        for r in righe or []:
            code = r.get("currencyCode") if isinstance(r, dict) else getattr(r, "currency_code", None)
            val = r.get("rate") if isinstance(r, dict) else getattr(r, "rate", None)
            if str(code).upper() == VALUTA_CONTO and val is not None:
                v = float(val)
                if not (_BANDA_PLAUSIBILE[0] <= v <= _BANDA_PLAUSIBILE[1]):
                    raise ValueError(f"cambio GBP->EUR non plausibile: {v}")
                return v
        raise ValueError("listCurrencyRates senza EUR")

    def aggiorna(self, client: Any) -> bool:
        """Rilegge il cambio. Mai un'eccezione: fallisce in alert."""
        if self.fisso:
            return True
        self._assicura_caricato()
        try:
            v = self._leggi_da_betfair(client)
        except Exception as e:  # noqa: BLE001 - regola K1: mai far cadere il processo
            with self._lock:
                if self.fonte in ("betfair", "cache"):
                    self._alert("WARN", (
                        f"cambio GBP->EUR non letto ({type(e).__name__}: {str(e)[:120]}): "
                        f"uso l'ultimo noto {self.rate} ({self.fonte})"))
                else:
                    self._alert("CRITICAL", (
                        f"cambio non letto ({type(e).__name__}: {str(e)[:120]}): nessun "
                        f"cambio noto, uso la costante {self.rate} del {CAMBIO_RIPIEGO_DATA}"))
            logger.warning("[valuta] cambio GBP->EUR non letto: %s", e)
            return False
        with self._lock:
            self.rate, self.fonte, self.letto_at = v, "betfair", time.time()
        self._scrivi_cache()
        logger.info("[valuta] cambio GBP->EUR = %s (listCurrencyRates)", v)
        return True

    def avvia(self, client: Any) -> None:
        """Lettura all'avvio + rinfresco orario in un thread daemon (idempotente)."""
        self.aggiorna(client)
        with self._lock:
            if self._thread is not None or self.fisso:
                return

            def _ciclo() -> None:
                while True:
                    time.sleep(RINFRESCO_S)
                    self.aggiorna(client)

            self._thread = threading.Thread(target=_ciclo, name="cambio-gbp-eur", daemon=True)
            self._thread.start()

    # ------------------------------------------------------------- uso
    def per_mercato(self, market_id: Any) -> float:
        """Cambio CONGELATO per mercato (il primo visto): vedi docstring del modulo."""
        mid = str(market_id)
        self._assicura_caricato()
        with self._lock:
            r = self._per_mercato.get(mid)
            if r is None:
                if len(self._per_mercato) >= _TETTO_MERCATI:
                    self._per_mercato.clear()
                r = self._per_mercato[mid] = self.rate
            return r

    def stato(self) -> Dict[str, Any]:
        self._assicura_caricato()
        return {"rate": self.rate, "fonte": self.fonte, "letto_at": self.letto_at,
                "mercati": len(self._per_mercato)}


_LOCK_CONVERSIONE = threading.Lock()


def converti_libro(market_book: Any, cambio: "CambioGbpEur") -> Any:
    """MarketBook dello STREAM (GBP) -> EUR, in place e idempotente. Torna il book.

    Converte: size di `available_to_back/lay`, `traded_volume`, `total_matched`
    del runner e del mercato. Marca il book: ``valuta='EUR'``,
    ``size_gbp_convertite=True``, ``cambio_gbp_eur=<rate>``.
    NON va chiamata sui book REST (gia' in EUR).
    """
    if market_book is None:
        return market_book
    with _LOCK_CONVERSIONE:
        if getattr(market_book, "size_gbp_convertite", False):
            return market_book
        r = cambio.per_mercato(getattr(market_book, "market_id", None))
        for runner in getattr(market_book, "runners", None) or []:
            # il RunnerBook e' condiviso fra book successivi (cache bflw)
            if getattr(runner, "_k1_eur", False) is True:
                continue
            try:
                ex = getattr(runner, "ex", None)
                if ex is not None:
                    ex.available_to_back = _livelli(getattr(ex, "available_to_back", None), r)
                    ex.available_to_lay = _livelli(getattr(ex, "available_to_lay", None), r)
                    ex.traded_volume = _livelli(getattr(ex, "traded_volume", None), r)
                runner.total_matched = _importo(getattr(runner, "total_matched", None), r)
                runner._k1_eur = True
            except Exception as e:  # noqa: BLE001 - un runner strano non ferma il libro
                logger.error("[valuta] runner %s non convertito: %s",
                             getattr(runner, "selection_id", "?"), e)
        try:
            market_book.total_matched = _importo(getattr(market_book, "total_matched", None), r)
            market_book.valuta = VALUTA_CONTO
            market_book.cambio_gbp_eur = r
            market_book.size_gbp_convertite = True
        except Exception as e:  # noqa: BLE001 - mai un'eccezione verso lo stream
            logger.error("[valuta] libro %s non marcato: %s",
                         getattr(market_book, "market_id", "?"), e)
    return market_book


# il cambio del PROCESSO (runner, scanner, sessioni): cache su disco al primo
# uso, Betfair con `CAMBIO.avvia(client)` nel main
CAMBIO = CambioGbpEur()


def cambio_banco() -> "CambioGbpEur":
    """Cambio del BANCO di replay: FISSO (riproducibilita' dei referti).

    Le registrazioni raw non portano il cambio del giorno: si usa
    `CAMBIO_RIPIEGO` (o `BANCO_CAMBIO_EUR_PER_GBP` dall'ambiente).
    """
    raw = (os.getenv("BANCO_CAMBIO_EUR_PER_GBP") or "").strip()
    try:
        v = float(raw) if raw else CAMBIO_RIPIEGO
    except ValueError:
        v = CAMBIO_RIPIEGO
    return CambioGbpEur(fisso=v)


def _classe_middleware() -> Any:
    # import PIGRO: importare flumine nel processo dello scanner cambierebbe la
    # forma dei livelli (dict) per tutto il processo (scanner.livello_campo)
    from flumine.markets.middleware import Middleware

    class MiddlewareValutaEur(Middleware):
        """Converte in EUR il book del mercato PRIMA di ogni altro middleware e
        di ogni strategia (`baseflumine._process_market_books`)."""

        def __init__(self, cambio: "CambioGbpEur") -> None:
            self.cambio = cambio

        def __call__(self, market: Any) -> None:
            converti_libro(getattr(market, "market_book", None), self.cambio)

    return MiddlewareValutaEur


_MW_CLASSE: Any = None


def monta_su_flumine(quadro: Any, cambio: Optional["CambioGbpEur"] = None) -> Any:
    """Monta (idempotente) la conversione come PRIMO middleware del quadro flumine.

    Primo = prima del `SimulatedMiddleware` (che abbina gli ordini paper sul
    libro) e prima delle strategie. Torna il middleware montato.
    """
    global _MW_CLASSE
    if _MW_CLASSE is None:
        _MW_CLASSE = _classe_middleware()
    lista = quadro._market_middleware
    presenti = [m for m in lista if isinstance(m, _MW_CLASSE)]
    mw = presenti[0] if presenti else _MW_CLASSE(cambio or CAMBIO)
    for m in presenti:
        lista.remove(m)
    lista.insert(0, mw)
    return mw
