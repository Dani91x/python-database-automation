"""sonde.py - l'interruttore e gli AGGANCI del modulo "Salute" (T0A, 09/10/2026).

Mandato: ``ARCHITETTURA_2026-10/05_PIANO_DI_MIGRAZIONE.md`` par. 1 T0A (P0210 fase 0).
Contatori IN MEMORIA agganciati ai client DB e Betfair che esistono gia', marche
di tempo additive sui messaggi, una riga ogni 30 s per servizio verso
``monitor_metrics`` scritta da un thread a parte (``scrittore.py``).

INTERRUTTORE ``MONITOR_SALUTE=0|1``, DI SERIE 0. Il monitor e' acceso SOLO se:
  * ``MONITOR_SALUTE=1`` nell'ambiente del processo, E
  * il ``main`` di un servizio ha chiamato ``avvia(<servizio>)``, E
  * nel processo NON e' caricato il banco (``Betfair.stream.backtest*``) e non
    gira pytest (salvo ``_consenti_in_test`` dei test di questo modulo).
Quindi nel banco e' spento PER COSTRUZIONE: il banco non chiama mai un ``main``
di servizio, e anche se lo facesse il controllo sui moduli caricati lo rifiuta.

A monitor spento ogni aggancio e' un ``if _mon.ATTIVO`` falso: nessun campo in
piu', nessuna scrittura, nessun thread, nessun handler di log.

LE MARCHE SONO CAMPI ADDITIVI (``rx`` nel raw, ``ts_pub_ms``/``pt`` nel ladder del
canale, ``emesso_ms`` nei ``params`` della coda, ``ricevuto_ms`` del canale):
nessuno le legge per decidere. Le legge solo la misura (``tempi_ordine.py``
legge ``emesso_ms`` per il tratto ``decisione_ms``, come previsto da F0).

M-2 (11/10/2026, mappatura dei flussi, ``ARCHITETTURA_2026-10/mappa/M2_MISURE.md``):
stesse regole, misure in piu'. ``rx_ms`` nel ladder del canale (arrivo nel processo
del messaggio con quel ``pt``), ``ts`` nella BUSTA dei push del canale (``busta``) e
la sua lettura nei bot (``ricevuto_canale``), il riassunto della pagina (richiesta
``salute`` sul canale gia' aperto: ``misure_pagina``), il clic della pagina
(``emesso_ms`` nell'``order``, letto da ``drenate``), le righe ``tempi_ordine`` per
attore (handler di log), messaggi ``ocm``, stream aperti, connessioni allo Stream
API, peso delle richieste REST, pacchetto -> risposta di placeOrders.

Ogni funzione pubblica e' best-effort: NON solleva MAI verso il chiamante.
ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

from .registro import BORDI_MS, Registro

logger = logging.getLogger(__name__)

ENV = "MONITOR_SALUTE"
ENV_INTERVALLO = "MONITOR_SALUTE_SEC"
INTERVALLO_DEFAULT_S = 30.0

#: True solo dopo un ``avvia`` riuscito (letto dagli agganci come ``_mon.ATTIVO``)
ATTIVO = False

REGISTRO = Registro()

_STATO: Dict[str, Any] = {"servizio": None, "sport": None, "avvio_ms": None,
                          "scrittore": None, "gestori": [], "pid": None}
_LOCK = threading.Lock()
_TLS = threading.local()


# ---------------------------------------------------------------------------
# interruttore
# ---------------------------------------------------------------------------
def interruttore_acceso() -> bool:
    """``MONITOR_SALUTE=1`` nell'ambiente (qualunque altro valore = spento)."""
    return (os.environ.get(ENV) or "0").strip() == "1"


def nel_banco() -> bool:
    """True se nel processo e' caricato il banco di replay."""
    return any(m == "Betfair.stream.backtest" or m.startswith("Betfair.stream.backtest.")
               for m in list(sys.modules))


def in_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ


def intervallo_s() -> float:
    raw = (os.environ.get(ENV_INTERVALLO) or "").strip()
    try:
        v = float(raw) if raw else INTERVALLO_DEFAULT_S
    except ValueError:
        v = INTERVALLO_DEFAULT_S
    return v if v >= 1.0 else INTERVALLO_DEFAULT_S


def avvia(servizio: str, sport: Optional[str] = None, *, scrittore: bool = True,
          _consenti_in_test: bool = False, _invia: Any = None,
          _cartella: Optional[str] = None) -> bool:
    """Accende il monitor per questo processo (una volta). Ritorna True se acceso.

    Da chiamare in testa al ``main`` di un servizio, MAI da un modulo condiviso.
    ``_invia``/``_cartella``/``_consenti_in_test`` servono solo ai test."""
    global ATTIVO  # noqa: PLW0603 - interruttore di processo
    try:
        if not interruttore_acceso():
            return False
        if nel_banco():
            logger.info("[monitor] banco caricato nel processo: monitor spento per costruzione")
            return False
        if in_pytest() and not _consenti_in_test:
            return False
        with _LOCK:
            if ATTIVO:
                return True
            _STATO.update({"servizio": str(servizio)[:80], "sport": sport,
                           "avvio_ms": int(time.time() * 1000), "pid": os.getpid()})
            REGISTRO.azzera_tutto()
            _azzera_stato_m2()
            _installa_gestori_log()
            ATTIVO = True
        if scrittore:
            from .scrittore import Scrittore

            s = Scrittore(servizio=_STATO["servizio"], sport=sport, intervallo=intervallo_s(),
                          invia=_invia, cartella=_cartella)
            _STATO["scrittore"] = s
            s.start()
        logger.info("[monitor] Salute ACCESO per %s (una riga ogni %.0f s)", servizio,
                    intervallo_s())
        return True
    except Exception as e:  # noqa: BLE001 - la misura non ferma mai un servizio
        logger.warning("[monitor] avvio KO (monitor spento): %s", str(e)[:200])
        ATTIVO = False
        return False


def ferma(attesa_s: float = 2.0) -> None:
    """Spegne il monitor (ultima riga best-effort, handler tolti)."""
    global ATTIVO  # noqa: PLW0603
    try:
        s = _STATO.get("scrittore")
        if s is not None:
            s.ferma(attesa_s)
        with _LOCK:
            ATTIVO = False
            _togli_gestori_log()
            _azzera_stato_m2()
            _STATO.update({"scrittore": None, "servizio": None, "sport": None,
                           "avvio_ms": None, "pid": None})
    except Exception:  # noqa: BLE001
        ATTIVO = False


def stato() -> Dict[str, Any]:
    """Chi sono (per lo scrittore e i test)."""
    return {k: v for k, v in _STATO.items() if k not in ("scrittore", "gestori")}


# ---------------------------------------------------------------------------
# primitive (chiamate dagli agganci SOLO dopo ``if _mon.ATTIVO``)
# ---------------------------------------------------------------------------
def ora_ms() -> int:
    return int(time.time() * 1000)


def conta(gruppo: str, chiave: str, n: float = 1) -> None:
    if ATTIVO:
        try:
            REGISTRO.conta(gruppo, chiave, n)
        except Exception:  # noqa: BLE001
            pass


def tratto(nome: str, ms: float) -> None:
    if ATTIVO:
        try:
            REGISTRO.tratto(nome, ms)
        except Exception:  # noqa: BLE001
            pass


def valore(gruppo: str, chiave: str, v: Any) -> None:
    if ATTIVO:
        try:
            REGISTRO.valore(gruppo, chiave, v)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# marche additive
# ---------------------------------------------------------------------------
def ricevuto_ms() -> int:
    """Istante d'arrivo per ``LocalRequest.ricevuto_ms``: 0 a monitor spento."""
    return int(time.time() * 1000) if ATTIVO else 0


def drenate(richieste: Any) -> None:
    """Il worker ha drenato richieste del canale: attesa in coda = ora - ricevuto."""
    if not ATTIVO:
        return
    try:
        adesso = time.time() * 1000.0
        for r in richieste or ():
            REGISTRO.conta("canale_richieste", str(getattr(r, "method", "?"))[:40])
            ric = getattr(r, "ricevuto_ms", 0) or 0
            if ric > 0:
                REGISTRO.tratto("canale_coda_ms", adesso - float(ric))
            _clic_del_desktop(r, float(ric), adesso)
    except Exception:  # noqa: BLE001
        pass


def _clic_del_desktop(r: Any, ric: float, adesso: float) -> None:
    """M-2 (11/10): un ``order`` della pagina che porta ``emesso_ms`` (istante in
    cui la pagina ha deciso di mandare il comando, ``Date.now()`` del renderer:
    stesso orologio di sistema del processo) da' il tratto M2 del CLIC:
    ``clic_canale_ms`` (clic -> arrivo sul canale) e ``clic_presa_ms`` (clic ->
    drenaggio del worker). Paper e live in chiavi separate, mai sommati."""
    if str(getattr(r, "method", "")) != "order":
        return
    p = getattr(r, "params", None)
    em = p.get("emesso_ms") if isinstance(p, dict) else None
    if not _numero_positivo(em):
        return
    modo = _modo(p.get("mode"))
    REGISTRO.conta("ordini_emessi", "desktop")
    if ric > 0:
        REGISTRO.tratto("clic_canale_ms." + modo, ric - float(em))
    REGISTRO.tratto("clic_presa_ms." + modo, adesso - float(em))


def _numero_positivo(v: Any) -> bool:
    return (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            and v > 0)


def _modo(v: Any) -> str:
    """``paper`` | ``live`` | ``?``: la chiave che tiene separate le due modalita'."""
    s = str(v or "").strip().lower()
    return s if s in ("paper", "live") else "?"


def marca_ladder(row: Dict[str, Any], book: Any) -> Dict[str, Any]:
    """COPIA della riga del ladder per il CANALE con ``ts_pub_ms`` e ``pt``.

    Mai la riga originale: la stessa riga va anche a ``live_ladder`` (upsert con
    le colonne della tabella) e un campo in piu' romperebbe la scrittura."""
    if not ATTIVO:
        return row
    try:
        ora = time.time() * 1000.0
        ts = int(ora)
        out = dict(row)
        out["ts_pub_ms"] = ts
        pt = book.get("pt") if isinstance(book, dict) else None
        if isinstance(pt, (int, float)) and not isinstance(pt, bool) and pt > 0:
            out["pt"] = int(pt)
            REGISTRO.tratto("ladder_pub_pt_ms", ts - float(pt))
            # M-2 (11/10): ``rx_ms`` = arrivo nel processo del messaggio che ha
            # prodotto questo book (stesso ``pt``): arrivo -> pubblicazione sullo
            # STESSO orologio del PC (tratto b di M1), e la pagina misura
            # ``rx -> pixel`` senza lo scarto con Betfair
            rx = rx_di_pt(pt)
            if rx is not None:
                out["rx_ms"] = int(rx)
                REGISTRO.tratto("ladder_rx_pub_ms", ora - rx)
        REGISTRO.conta("ladder", "pubblicati_canale")
        return out
    except Exception:  # noqa: BLE001
        return row


def marca_emesso(params: Dict[str, Any]) -> Dict[str, Any]:
    """``emesso_ms`` (istante in cui il bot emette il comando) nei ``params`` della
    coda: lo legge ``tempi_ordine`` per ``decisione_ms``. A monitor spento il dict
    torna identico."""
    if ATTIVO and isinstance(params, dict):
        try:
            params["emesso_ms"] = int(time.time() * 1000)
            REGISTRO.conta("ordini_emessi", str(params.get("source") or "?")[:30])
        except Exception:  # noqa: BLE001
            pass
    return params


# ---------------------------------------------------------------------------
# stream Betfair: messaggi, eta' del dato, connectionsAvailable
# ---------------------------------------------------------------------------
_RE_PT = re.compile(r'"pt"\s*:\s*(\d+)')
_RE_OP_STATUS = re.compile(r'"op"\s*:\s*"status"')


def osserva_stream(sorgente: str, raw_data: Any) -> None:
    """Un messaggio grezzo dello stream (dal ``on_data`` del listener).

    mcm: conteggio + ``rx - pt`` (eta' del messaggio all'arrivo, orologio del PC
    contro quello di Betfair: include lo scarto dell'orologio). status: il
    ``connectionsAvailable`` (anche lo 0, che betfairlightweight non salva) e
    l'esito. Lettura della sola testa del messaggio (nessun ``json.loads`` sui
    mcm)."""
    if not ATTIVO or not isinstance(raw_data, str):
        return
    try:
        rx = time.time() * 1000.0
        testa = raw_data[:240]
        if '"mcm"' in testa:
            REGISTRO.conta("stream_msg", sorgente)
            m = _RE_PT.search(testa)
            if m:
                eta = rx - float(m.group(1))
                # il MINIMO di finestra di questo tratto e' il limite superiore
                # dello scarto dell'orologio del PC (scarto + latenza minima)
                REGISTRO.tratto("feed_rx_pt_ms." + sorgente, eta)
                _ricorda_rx(int(m.group(1)), rx)     # M-2: per ``rx_ms`` del ladder
            return
        if '"ocm"' in testa:
            # M-2 (11/10): messaggi dello stream ORDINI (chi aggancia il proprio
            # listener ordini passa di qui; vedi M2_MISURE.md per chi lo fa)
            REGISTRO.conta("stream_ocm", sorgente)
            m = _RE_PT.search(testa)
            if m:
                REGISTRO.tratto("ordini_rx_pt_ms." + sorgente, rx - float(m.group(1)))
            return
        if _RE_OP_STATUS.search(testa):
            _osserva_status(sorgente, raw_data)
            return
        REGISTRO.conta("stream_altri", sorgente)
    except Exception:  # noqa: BLE001 - la misura non rompe mai lo stream
        pass


def _osserva_status(sorgente: str, raw_data: str) -> None:
    import json

    d = json.loads(raw_data)
    esito = str(d.get("statusCode") or "?")
    errore = d.get("errorCode")
    REGISTRO.conta("stream_status", f"{sorgente} {esito}{(' ' + str(errore)) if errore else ''}")
    disp = d.get("connectionsAvailable")
    if isinstance(disp, int) and not isinstance(disp, bool):
        REGISTRO.valore("connessioni_disponibili", sorgente, disp)
        REGISTRO.valore("connessioni_lette_ms", sorgente, int(time.time() * 1000))


# ---------------------------------------------------------------------------
# M-2 (11/10/2026, mappatura dei flussi): misure in piu', stesso interruttore
# ---------------------------------------------------------------------------
#: ``pt`` -> istante d'arrivo (ms, orologio del PC) dei messaggi mcm visti da
#: ``osserva_stream``: lo legge ``marca_ladder`` per ``rx_ms``. Tetto fisso (i
#: ``pt`` piu' vecchi escono per primi): mai crescita senza limite.
RX_PT_MAX = 4096
_RX_PT: "OrderedDict[int, float]" = OrderedDict()
_RX_LOCK = threading.Lock()
#: flumine: stream (tipo -> id) partiti e non ancora fermati, per processo
_STREAM_APERTI: Dict[str, set] = {}


def _azzera_stato_m2() -> None:
    with _RX_LOCK:
        _RX_PT.clear()
    _STREAM_APERTI.clear()


def _ricorda_rx(pt: int, rx: float) -> None:
    """Il PRIMO arrivo di un ``pt`` (due messaggi con lo stesso ``pt``: conta
    il primo, l'istante in cui il dato e' entrato nel processo)."""
    with _RX_LOCK:
        if pt in _RX_PT:
            return
        _RX_PT[pt] = rx
        while len(_RX_PT) > RX_PT_MAX:
            _RX_PT.popitem(last=False)


def rx_di_pt(pt: Any) -> Optional[float]:
    """Arrivo nel processo del messaggio con questo ``pt`` (None se non visto)."""
    try:
        with _RX_LOCK:
            return _RX_PT.get(int(pt))
    except Exception:  # noqa: BLE001
        return None


def busta(topic: str, payload: Any) -> Dict[str, Any]:
    """La busta di un push del canale locale con ``ts`` (ms, istante della
    pubblicazione): campo ADDITIVO della busta, mai del payload. I lettori
    (pagina e bot) ignorano le chiavi che non conoscono; chi misura ricava
    ``ricezione - ts``. Conta anche i push per topic (messaggi/s per processo)."""
    b: Dict[str, Any] = {"t": topic, "d": payload}
    if ATTIVO:
        try:
            b["ts"] = int(time.time() * 1000)
            REGISTRO.conta("canale_pub", str(topic)[:40])
        except Exception:  # noqa: BLE001
            pass
    return b


def ricevuto_canale(msg: Any) -> None:
    """Un lettore (bot) ha ricevuto una busta del canale locale: latenza
    ``pubblicazione -> ricezione`` per topic (stesso orologio del PC)."""
    if not ATTIVO or not isinstance(msg, dict):
        return
    try:
        topic = str(msg.get("t") or "?")[:40]
        REGISTRO.conta("canale_ric", topic)
        ts = msg.get("ts")
        if _numero_positivo(ts):
            REGISTRO.tratto("canale_ricezione_ms." + topic, time.time() * 1000.0 - float(ts))
    except Exception:  # noqa: BLE001
        pass


# --- misure della PAGINA (M1 c-d) -------------------------------------------
#: metodo del canale con cui la pagina manda il suo riassunto (sola misura: mai
#: in coda comandi, nessun token, nessun parametro d'ordine)
METODO_PAGINA = "salute"
VERSIONE_PAGINA = 1
TRATTI_PAGINA = frozenset({
    "pagina_canale_ms",        # ts_pub_ms -> arrivo del push nella pagina
    "pagina_dipinto_ms",       # arrivo nella pagina -> primo frame dopo il commit
    "pagina_rx_dipinto_ms",    # rx_ms (arrivo nel processo) -> frame: M1 sul PC
    "pagina_pt_dipinto_ms",    # pt di Betfair -> frame (orologi diversi)
    "pagina_pub_dipinto_ms",   # ts_pub_ms -> frame
})
CONTATORI_PAGINA = frozenset({"push_ladder", "dipinti", "riassunti"})
#: tetto di misure per riassunto (30 s di pagina con 20 ladder a 10 push/s = 6000)
N_MAX_PAGINA = 100_000


def _riassunto_valido(r: Any) -> tuple:
    """(n, somma, min, max, secchi) di un riassunto della pagina, o ValueError."""
    if not isinstance(r, dict):
        raise ValueError("riassunto non e' un oggetto")
    n = r.get("n")
    secchi = r.get("secchi")
    if not isinstance(n, int) or isinstance(n, bool) or not (0 <= n <= N_MAX_PAGINA):
        raise ValueError("n fuori misura")
    if not isinstance(secchi, list) or len(secchi) != len(BORDI_MS) + 1:
        raise ValueError("secchi di lunghezza diversa dai bordi")
    if any(not isinstance(c, int) or isinstance(c, bool) or c < 0 for c in secchi):
        raise ValueError("secchio non intero")
    if sum(secchi) != n:
        raise ValueError("n diverso dalla somma dei secchi")
    vals = []
    for k in ("somma", "min", "max"):
        v = r.get(k)
        if v is None and (k != "somma" and n == 0):
            vals.append(None)
            continue
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
            raise ValueError(k + " non numerico")
        vals.append(float(v))
    return n, vals[0], vals[1], vals[2], secchi


def misure_pagina(msg_id: Any, p: Any) -> Dict[str, Any]:
    """Il riassunto periodico della pagina (richiesta ``salute`` sul canale gia'
    aperto): validato PER INTERO, poi fuso nel registro di questo processo (la
    riga dice lo sport). Tutto o niente: un pezzo storto rifiuta il riassunto.
    Ritorna la risposta per la pagina. MAI solleva."""
    if not ATTIVO:
        return {"id": msg_id, "ok": False, "e": "monitor spento in questo processo"}
    try:
        if not isinstance(p, dict) or p.get("v") != VERSIONE_PAGINA:
            raise ValueError("versione del riassunto sconosciuta")
        bordi = p.get("bordi")
        if not isinstance(bordi, list) or [float(b) for b in bordi] != [float(b) for b in BORDI_MS]:
            raise ValueError("bordi dei secchi diversi da registro.BORDI_MS")
        tratti = p.get("tratti") or {}
        contatori = p.get("contatori") or {}
        if not isinstance(tratti, dict) or not isinstance(contatori, dict):
            raise ValueError("tratti/contatori non sono oggetti")
        pronti = []
        for nome, r in tratti.items():
            if nome not in TRATTI_PAGINA:
                raise ValueError("tratto non ammesso: %s" % str(nome)[:40])
            pronti.append((nome, _riassunto_valido(r)))
        conti = []
        for k, v in contatori.items():
            if k not in CONTATORI_PAGINA or not isinstance(v, int) or isinstance(v, bool) \
                    or not (0 <= v <= N_MAX_PAGINA):
                raise ValueError("contatore non ammesso: %s" % str(k)[:40])
            conti.append((k, v))
        for nome, (n, somma, mn, mx, secchi) in pronti:
            if n > 0:
                REGISTRO.fondi(nome, n, somma, mn, mx, secchi)
        for k, v in conti:
            REGISTRO.conta("pagina", k, v)
        REGISTRO.conta("pagina", "riassunti_accolti")
        return {"id": msg_id, "ok": True, "d": {"tratti": len(pronti)}}
    except Exception as e:  # noqa: BLE001 - un riassunto storto non tocca il registro
        try:
            REGISTRO.conta("pagina", "riassunti_rifiutati")
        except Exception:  # noqa: BLE001
            pass
        return {"id": msg_id, "ok": False, "e": "riassunto rifiutato: " + str(e)[:160]}


# --- attore di un ordine dal suo riferimento --------------------------------
_RE_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_RE_PREFISSO = re.compile(r"^([a-z]{2,12})-")


def attore_da_rif(rif: Any) -> str:
    """Chi ha deciso l'ordine, dal riferimento che il comando porta:
    UUID (``crypto.randomUUID`` della pagina, canale e coda) = ``desktop``;
    ``mike-``/``omega-``/``safe-``/``risk-``/... = il prefisso; altro = ``altro``."""
    s = str(rif or "").strip().lower()
    if not s or s == "na":
        return "ignoto"
    if _RE_UUID.match(s):
        return "desktop"
    m = _RE_PREFISSO.match(s)
    return m.group(1) if m else "altro"


# --- peso delle richieste REST (Betfair "Market Data Request Limits") --------
#: punti per mercato di ``priceProjection.priceData`` (listMarketBook,
#: listRunnerBook); senza priceData = 2. EX_ALL_OFFERS + EX_TRADED insieme = 17.
PESI_PREZZI = {"SP_AVAILABLE": 3, "SP_TRADED": 7, "EX_BEST_OFFERS": 5, "EX_ALL_OFFERS": 17,
               "EX_TRADED": 17}
PESO_SENZA_PROIEZIONE = 2
#: punti per mercato di ``marketProjection`` (listMarketCatalogue, x maxResults)
PESI_CATALOGO = {"MARKET_DESCRIPTION": 1, "RUNNER_METADATA": 1}
#: punti per mercato di listMarketProfitAndLoss
PESO_PNL = 4
#: oltre questo Betfair rifiuta la richiesta (TOO_MUCH_DATA)
PESO_MAX_RICHIESTA = 200


def peso_richiesta(metodo: str, corpo: Any) -> Optional[float]:
    """Punti di peso di una richiesta JSON-RPC (None = metodo non pesato o corpo
    illeggibile). Pura."""
    if metodo not in ("listMarketBook", "listRunnerBook", "listMarketCatalogue",
                      "listMarketProfitAndLoss"):
        return None
    if isinstance(corpo, bytes):
        corpo = corpo.decode("utf-8", "replace")
    if not isinstance(corpo, str):
        return None
    d = json.loads(corpo)
    if not isinstance(d, dict):
        return None
    par = d.get("params") or {}
    if not isinstance(par, dict):
        return None
    if metodo == "listMarketCatalogue":
        proiezione = par.get("marketProjection") or []
        per = sum(PESI_CATALOGO.get(str(x), 0) for x in proiezione)
        return float(per * int(par.get("maxResults") or 0))
    if metodo == "listMarketProfitAndLoss":
        return float(PESO_PNL * len(par.get("marketIds") or []))
    n = 1 if metodo == "listRunnerBook" else len(par.get("marketIds") or [])
    pp = par.get("priceProjection") or {}
    dati = set(str(x) for x in (pp.get("priceData") or [])) if isinstance(pp, dict) else set()
    if not dati:
        return float(PESO_SENZA_PROIEZIONE * n)
    per = 0.0
    if {"EX_ALL_OFFERS", "EX_TRADED"} <= dati:
        per += 17
        dati = dati - {"EX_ALL_OFFERS", "EX_TRADED"}
    for x in dati:
        w = float(PESI_PREZZI.get(x, 0))
        if x == "EX_BEST_OFFERS":
            ov = pp.get("exBestOffersOverrides") or {}
            prof = ov.get("bestPricesDepth") if isinstance(ov, dict) else None
            if isinstance(prof, int) and prof > 3:
                w = w * prof / 3.0
        per += w
    return round(per * n, 2)


# ---------------------------------------------------------------------------
# client DB (httpx del PostgREST di supabase-py)
# ---------------------------------------------------------------------------
_MARCA_GANCIO = "_monitor_salute"


def _tabella_di(path: str) -> str:
    p = path.split("/rest/v1/", 1)
    if len(p) < 2:
        return path[:40] or "?"
    resto = p[1]
    if resto.startswith("rpc/"):
        return "rpc:" + resto[4:].split("/", 1)[0][:60]
    return resto.split("/", 1)[0].split("?", 1)[0][:60]


def _db_richiesta(request: Any) -> None:
    try:
        _TLS.db_t0 = time.perf_counter()
        _TLS.db_chiave = f"{request.method} {_tabella_di(str(request.url.path))}"
        REGISTRO.conta("db", _TLS.db_chiave)
    except Exception:  # noqa: BLE001
        pass


def _db_risposta(response: Any) -> None:
    try:
        t0 = getattr(_TLS, "db_t0", None)
        if t0 is not None:
            REGISTRO.tratto("db_ms", (time.perf_counter() - t0) * 1000.0)
            _TLS.db_t0 = None
        st = int(getattr(response, "status_code", 0) or 0)
        if st >= 400:
            REGISTRO.conta("db_errori", f"{st} {getattr(_TLS, 'db_chiave', '?')}")
    except Exception:  # noqa: BLE001
        pass


setattr(_db_richiesta, _MARCA_GANCIO, True)
setattr(_db_risposta, _MARCA_GANCIO, True)


def aggancia_client_db(client: Any) -> Any:
    """Conta le richieste PostgREST del client (hook di httpx, come il contatore
    di rinnovo di ``db_client._installa_contatore``). Idempotente. Ritorna il
    client (lo stesso oggetto)."""
    if not ATTIVO or client is None:
        return client
    try:
        hooks = client.postgrest.session.event_hooks
        if any(getattr(f, _MARCA_GANCIO, False) for f in hooks.get("request", [])):
            return client
        hooks["request"].append(_db_richiesta)
        hooks["response"].append(_db_risposta)
    except Exception:  # noqa: BLE001 - client finti o versioni diverse: niente conteggio
        pass
    return client


# ---------------------------------------------------------------------------
# client Betfair (requests.Session dell'APIClient di betfairlightweight)
# ---------------------------------------------------------------------------
_RE_METODO = re.compile(r'"method"\s*:\s*"([^"]+)"')


def _metodo_betfair(resp: Any) -> str:
    req = getattr(resp, "request", None)
    url = str(getattr(req, "url", "") or "")
    if "certlogin" in url:
        return "certlogin"
    if "/api/login" in url:
        return "login"
    if "keepAlive" in url:
        return "keepAlive"
    if "logout" in url:
        return "logout"
    corpo = getattr(req, "body", None)
    if isinstance(corpo, bytes):
        corpo = corpo[:240].decode("ascii", "replace")
    if isinstance(corpo, str):
        m = _RE_METODO.search(corpo[:240])
        if m:
            return m.group(1).rsplit("/", 1)[-1][:40]
    return "altro"


def _bf_risposta(resp: Any, *args: Any, **kwargs: Any) -> None:
    try:
        metodo = _metodo_betfair(resp)
        REGISTRO.conta("betfair_rest", metodo)
        el = getattr(resp, "elapsed", None)
        if el is not None:
            REGISTRO.tratto("rest_ms." + metodo, el.total_seconds() * 1000.0)
        st = int(getattr(resp, "status_code", 0) or 0)
        if st >= 400:
            REGISTRO.conta("betfair_rest_errori", f"{st} {metodo}")
        _pesa_richiesta(metodo, resp)
    except Exception:  # noqa: BLE001
        pass
    return None


def _pesa_richiesta(metodo: str, resp: Any) -> None:
    """M-2 (11/10): il PESO della richiesta (punti Betfair, tetto 200 per
    richiesta) per i metodi di dati di mercato. Somma per metodo + istogramma
    dei punti per richiesta (``rest_peso.<metodo>``, l'unita' e' il punto)."""
    try:
        peso = peso_richiesta(metodo, getattr(getattr(resp, "request", None), "body", None))
    except Exception:  # noqa: BLE001 - corpo illeggibile: nessun peso
        peso = None
    if peso is None:
        return
    REGISTRO.conta("betfair_rest_peso", metodo, peso)
    REGISTRO.tratto("rest_peso." + metodo, peso)
    if peso > PESO_MAX_RICHIESTA:
        REGISTRO.conta("betfair_rest_oltre_peso", metodo)


setattr(_bf_risposta, _MARCA_GANCIO, True)


def aggancia_client_betfair(client: Any) -> Any:
    """Conta le chiamate REST (login, keepAlive, metodi JSON-RPC) della sessione
    HTTP dell'APIClient. Gli ordini di flumine passano da sessioni sue: quelli si
    contano dal log di ``flumine.execution`` (vedi ``_GestoreEsecuzione``)."""
    if not ATTIVO or client is None:
        return client
    try:
        sess = getattr(client, "session", None)
        hooks = getattr(sess, "hooks", None)
        if not isinstance(hooks, dict):
            return client
        lista = hooks.setdefault("response", [])
        if not isinstance(lista, list):
            lista = hooks["response"] = [lista]
        if not any(getattr(f, _MARCA_GANCIO, False) for f in lista):
            lista.append(_bf_risposta)
    except Exception:  # noqa: BLE001
        pass
    return client


# ---------------------------------------------------------------------------
# handler di log (letture di cio' che le librerie GIA' registrano: zero agganci)
# ---------------------------------------------------------------------------
class _Gestore(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - sovrascritto
        pass

    def handle(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        # M-2 (11/10): ``logging.Handler.handle`` NON cattura le eccezioni di
        # ``emit``: senza questo una lettura storta risalirebbe fino a chi ha
        # scritto il log (flumine, il worker ordini). La misura non rompe mai.
        try:
            return bool(super().handle(record))
        except Exception:  # noqa: BLE001
            return False

    def handleError(self, record: logging.LogRecord) -> None:  # noqa: N802
        pass  # la misura non scrive mai tracce d'errore nel log del servizio


class _GestoreLatenzaFlumine(_Gestore):
    """``flumine.baseflumine``: "High latency between current time and
    MarketBook publish time" (> 2 s) con ``extra={"latency": s}``. Oggi il
    formato del log dei runner non stampa ``extra``: il valore andava perso."""

    def emit(self, record: logging.LogRecord) -> None:
        lat = getattr(record, "latency", None)
        if isinstance(lat, (int, float)):
            REGISTRO.tratto("flumine_latenza_alta_ms", float(lat) * 1000.0)


class _GestoreEsecuzione(_Gestore):
    """``flumine.execution``: ``execute_<place|cancel|update|replace>`` con
    ``elapsed_time`` e ``order_package`` (``order_count``). Dal logger si sa se
    e' Betfair vero (``betfairexecution``) o simulato (paper): MAI sommati."""

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.msg if isinstance(record.msg, str) else ""
        live = record.name.endswith("betfairexecution")
        pacchetto = getattr(record, "order_package", None)
        n = 1
        if isinstance(pacchetto, dict):
            try:
                n = int(pacchetto.get("order_count") or 1)
            except (TypeError, ValueError):
                n = 1
        if msg.startswith("execute_"):
            fn = msg[len("execute_"):][:20]
            gruppo = "esecuzione_live" if live else "esecuzione_paper"
            REGISTRO.conta(gruppo, fn, n)
            el = getattr(record, "elapsed_time", None)
            if live and isinstance(el, (int, float)):
                REGISTRO.tratto("betfair_" + fn + "_ms", float(el) * 1000.0)
            if live and fn in ("place", "replace"):
                REGISTRO.conta("transazioni", fn, n)
            if live and fn == "place" and isinstance(pacchetto, dict):
                # M-2 (11/10): pacchetto creato (l'ordine nato nella strategia:
                # scalper, bot tennis, motore del runner) -> risposta di
                # placeOrders registrata, dallo stesso orologio di flumine
                es = pacchetto.get("elapsed_seconds")
                if isinstance(es, (int, float)) and not isinstance(es, bool):
                    REGISTRO.tratto("pacchetto_risposta_ms", float(es) * 1000.0)
        elif msg.startswith("High latency between current time and OrderPackage"):
            lat = getattr(record, "latency", None)
            if isinstance(lat, (int, float)):
                REGISTRO.tratto("pacchetto_attesa_ms", float(lat) * 1000.0)
        elif msg.startswith("Execution error"):
            REGISTRO.conta("esecuzione_errori", "live" if live else "paper", n)
            if live:
                tipo = (pacchetto or {}).get("package_type") if isinstance(pacchetto, dict) else None
                if tipo in ("Place", "Replace"):
                    REGISTRO.conta("transazioni", "fallite", n)


class _GestoreStatoStream(_Gestore):
    """``betfairlightweight.streaming.listener``: "[stream: id]: SUCCESS (N
    connections available)". Ripiego per i processi senza listener nostro
    (sessioni dello scalper): betfairlightweight non salva lo 0, quindi con 0
    qui si legge il valore PRECEDENTE (dichiarato nel referto)."""

    def emit(self, record: logging.LogRecord) -> None:
        a = record.args
        if record.msg == "[%s: %s]: connection_id: %s":
            # M-2 (11/10): una connessione allo Stream API aperta (o riaperta)
            REGISTRO.conta("stream_connessioni", "aperte")
            return
        if not isinstance(a, tuple) or len(a) != 4 or record.msg != "[%s: %s]: %s (%s connections available)":
            return
        REGISTRO.conta("stream_status_log", str(a[2])[:30])
        if isinstance(a[3], int) and not isinstance(a[3], bool):
            REGISTRO.valore("connessioni_disponibili_log", f"stream-{a[1]}", a[3])


class _GestoreAvviiStream(_Gestore):
    """``flumine.streams``: "Starting MarketStream/OrderStream ..." a ogni
    (ri)connessione."""

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.msg if isinstance(record.msg, str) else ""
        if msg.startswith("Starting ") and "Stream" in msg:
            REGISTRO.conta("stream_avvii", msg.split()[1][:30])
            _segna_stream(msg, record.args, aperto=True)
        elif msg.startswith("Stopped ") and "Stream" in msg:
            _segna_stream(msg, record.args, aperto=False)


def _segna_stream(msg: str, args: Any, *, aperto: bool) -> None:
    """M-2 (11/10): stream di flumine APERTI nel processo, per tipo (valore
    ``stream_aperti``): "Starting <Tipo> <id>" li apre, "Stopped <Tipo> <id>" li
    chiude. ``SimulatedOrderStream`` e' simulato (nessuna connessione a Betfair):
    resta nella sua chiave, il referto non lo conta fra le connessioni."""
    tipo = msg.split()[1][:30]
    if not tipo.endswith("Stream"):
        return                      # "Starting output_thread (...)": non e' uno stream
    sid = str(args[0])[:40] if isinstance(args, tuple) and args else "?"
    aperti = _STREAM_APERTI.setdefault(tipo, set())
    if aperto:
        aperti.add(sid)
    else:
        aperti.discard(sid)
        REGISTRO.conta("stream_arresti", tipo)
    REGISTRO.valore("stream_aperti", tipo, len(aperti))


class _GestoreTempiOrdine(_Gestore):
    """M-2 (11/10): ``Betfair.stream.tempi_ordine`` scrive UNA riga per ordine
    (``tempi_ordine ref=... strada=... decisione_ms=... rif=...``, F0): qui la si
    legge e se ne fanno istogrammi per ATTORE (dal ``rif``), strada e modalita'.
    Zero agganci nel percorso degli ordini: si legge cio' che il log dice gia'.

    Tratti (ms, chiave ``<attore>.<strada>.<modo>``): ``decisione_invio_ms``,
    ``invio_presa_ms``, ``presa_place_ms`` (interno), ``place_risposta_ms`` e,
    se ci sono tutti e quattro, ``decisione_risposta_ms`` = la loro somma, cioe'
    decisione -> risposta di placeOrders (gli orologi misti della coda, PC/DB, si
    elidono nella somma). Solo le azioni che PIAZZANO (place*, greenup)."""

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.msg if isinstance(record.msg, str) else ""
        if not msg.startswith("tempi_ordine "):
            return
        campi = dict(p.split("=", 1) for p in msg.split(" ")[1:] if "=" in p)
        azione = campi.get("azione", "")
        if not (azione.startswith("place") or azione == "greenup"):
            REGISTRO.conta("tempi_altre_azioni", azione[:20])
            return
        chiave = "%s.%s.%s" % (attore_da_rif(campi.get("rif")), campi.get("strada", "?")[:12],
                               _modo(campi.get("mode")))
        REGISTRO.conta("ordini_misurati", chiave)
        valori = []
        for campo, nome in _TRATTI_TEMPI:
            v = _ms_del_campo(campi.get(campo))
            if v is not None:
                valori.append(v)
                REGISTRO.tratto(nome + "." + chiave, v)
        if len(valori) == len(_TRATTI_TEMPI):
            REGISTRO.tratto("decisione_risposta_ms." + chiave, sum(valori))


#: campo della riga ``tempi_ordine`` -> tratto della Salute
_TRATTI_TEMPI = (("decisione_ms", "decisione_invio_ms"), ("ricezione_ms", "invio_presa_ms"),
                 ("interno_ms", "presa_place_ms"), ("risposta_ms", "place_risposta_ms"))


def _ms_del_campo(v: Any) -> Optional[float]:
    if v is None or v == "na":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


class _GestoreErrori(_Gestore):
    """Radice: ERROR e CRITICAL per logger (solo il conteggio)."""

    def emit(self, record: logging.LogRecord) -> None:
        REGISTRO.conta("log_errori", f"{record.levelname} {record.name[:60]}")


_GESTORI = (
    ("flumine.baseflumine", _GestoreLatenzaFlumine, logging.WARNING),
    ("flumine.execution", _GestoreEsecuzione, logging.INFO),
    ("betfairlightweight.streaming.listener", _GestoreStatoStream, logging.INFO),
    ("flumine.streams", _GestoreAvviiStream, logging.INFO),
    ("Betfair.stream.tempi_ordine", _GestoreTempiOrdine, logging.INFO),   # M-2 (11/10)
    ("", _GestoreErrori, logging.ERROR),
)


def _installa_gestori_log() -> None:
    """Aggiunge gli handler (nessun livello di logger cambiato: si legge solo
    cio' che il processo registra gia')."""
    _togli_gestori_log()
    for nome, cls, livello in _GESTORI:
        h = cls(level=livello)
        logging.getLogger(nome).addHandler(h)
        _STATO["gestori"].append((nome, h))


def _togli_gestori_log() -> None:
    for nome, h in list(_STATO.get("gestori") or []):
        try:
            logging.getLogger(nome).removeHandler(h)
        except Exception:  # noqa: BLE001
            pass
    _STATO["gestori"] = []
