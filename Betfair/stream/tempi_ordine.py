"""tempi_ordine.py - F0 "misura" della strada unica (AUDIT_STRADE_ORDINE 24/09, par. 5).

I CINQUE TEMPI di ESECUZIONE_LIVE.md par. 4 (decisione -> scrittura in coda ->
presa del worker -> risposta di Betfair -> abbinamento), misurati su TUTTE le
strade che passano dal runner:

  strada=coda     riga di ``betfair_live_order_requests`` (giro del worker calcio)
  strada=canale   ``/order`` del canale 47331 (``_process_local_requests``, anche
                  quando lo serve il motore ordini)
  strada=comando  ``/comando/<attore>`` del motore ordini (``motore_ordini.py``)
  strada=tennis   runner tennis: canale 47332 (via=canale) e coda
                  ``tennis_live_order_queue`` (via=coda)

SOLO MISURA E LOG. Nessuna logica, nessuna guardia, nessun IO verso DB o Betfair:
il modulo tiene i numeri in RAM e scrive UNA riga di log per ordine::

  tempi_ordine ref=awlq12 strada=coda via=coda azione=place mode=paper ordine=<id>
      decisione_ms=na ricezione_ms=812 presa_ms=143 place_ms=2 risposta_ms=35
      abbinato_ms=1200 interno_ms=145 risposta_bf_ms=2110 abbinato_fonte=betfair
      orologi=ricezione:db/pc,risposta_bf:pc/betfair esito=abbinato rif=<ref>

I TRATTI (ms, ``na`` = istante non disponibile su quella strada):
  decisione_ms   decisione del bot/clic -> invio (scrittura in coda / arrivo sul
                 canale). Serve che il comando porti l'istante di decisione.
  ricezione_ms   invio -> il worker legge la riga / il comando.
  presa_ms       lettura -> inizio ``_dispatch`` (claim, attese, diario...).
  place_ms       inizio ``_dispatch`` -> subito prima di ``market.place_order``.
  risposta_ms    ``place_order`` -> risposta di Betfair registrata da flumine
                 (``order.responses.date_time_placed``, orologio del PC).
  abbinato_ms    risposta -> primo abbinamento: ``matchedDate - placedDate`` di
                 Betfair (stesso orologio) se ci sono; altrimenti prima
                 osservazione di size abbinata nello stream ordini (orologio del PC).
  interno_ms     lettura -> ``place_order`` (monotonic: il numero piu' affidabile).
  risposta_bf_ms ``place_order`` (PC) -> ``placedDate`` di Betfair: OROLOGI DIVERSI.

OROLOGI. Gli intervalli interni al processo usano ``time.monotonic()``. Dove si
confronta un istante del PC con uno di un altro orologio (``requested_at`` del DB,
``placedDate`` di Betfair) il tratto e' elencato in ``orologi=``: l'orologio di
questo PC era indietro di ~2,07 s il 17/09 (servizio Ora di Windows spento,
``Betfair/safe_strategy/LATENZA_TENNIS_2026-09-17.md`` riga 31). Quei tratti hanno
un errore sistematico dello stesso ordine: vanno letti come tali.

MEMORIA. Cache in RAM con TTL (``TTL_S``) e tetto di voci (``MAX_VOCI``): una voce
scaduta o espulsa scrive comunque la sua riga (``esito=scaduto``/``esito=tetto``)
con cio' che ha, e sparisce. Mai crescita illimitata.

INTERRUTTORE. ``LIVE_TEMPI_ORDINE`` (default acceso; ``0`` spegne). I punti di
aggancio nei worker controllano l'interruttore PRIMA di chiamare il modulo: a
interruttore spento il modulo non viene nemmeno chiamato.

Ogni funzione pubblica e' best-effort: non solleva MAI verso il chiamante.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

ENV = "LIVE_TEMPI_ORDINE"
TTL_S = 600.0
MAX_VOCI = 2000
PREFISSO = "tempi_ordine"

# chiavi con cui un comando o una riga di coda possono portare l'istante della
# DECISIONE (epoch ms, epoch s o ISO). Oggi nessun bot le scrive nella coda
# (Omega e Safe mettono solo ``source`` e ``trade_id``): vedi il referto F0.
_CHIAVI_DECISIONE = ("decisione_ms", "emesso_ms", "creato_ms", "decided_at_ms",
                     "decided_at", "decisione_at")

_STATI_TERMINALI = frozenset({"EXECUTION_COMPLETE", "EXPIRED", "LAPSED", "VIOLATION",
                              "VOIDED"})

_lock = threading.RLock()
_voci: Dict[str, Dict[str, Any]] = {}      # chiave richiesta -> voce (ordine d'inserimento)
_ordini: Dict[str, str] = {}               # id ordine flumine -> chiave richiesta
_filo = threading.local()                  # richiesta in esecuzione su QUESTO thread
_uscita: List[str] = []                    # righe pronte, scritte FUORI dal lucchetto


# ---------------------------------------------------------------------------
# interruttore e orologi
# ---------------------------------------------------------------------------
def attivo() -> bool:
    """Interruttore (letto a ogni chiamata: si spegne senza riavvio)."""
    return (os.getenv(ENV) or "1").strip() != "0"


def ora() -> Tuple[float, float]:
    """(monotonic s, orologio da parete del PC in ms)."""
    return time.monotonic(), time.time() * 1000.0


def _ms_da(v: Any) -> Optional[float]:
    """Istante in epoch ms da: numero (ms, o s se < 1e11), ISO, datetime."""
    if v is None or isinstance(v, bool):
        return None
    try:
        if isinstance(v, (int, float)):
            x = float(v)
            if x <= 0:
                return None
            return x * 1000.0 if x < 1e11 else x
        if isinstance(v, datetime):
            dt = v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)
            return dt.timestamp() * 1000.0
        if isinstance(v, str) and v.strip():
            s = v.strip()
            try:
                return _ms_da(float(s))
            except ValueError:
                pass
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return _ms_da(datetime.fromisoformat(s))
    except Exception:  # noqa: BLE001 - istante illeggibile = assente
        return None
    return None


def decisione_da(*fonti: Any) -> Optional[float]:
    """Primo istante di decisione trovato nelle fonti (dict: comando, params)."""
    for f in fonti:
        if not isinstance(f, dict):
            continue
        for k in _CHIAVI_DECISIONE:
            ms = _ms_da(f.get(k))
            if ms is not None:
                return ms
    return None


# ---------------------------------------------------------------------------
# registrazione degli istanti (punti di aggancio)
# ---------------------------------------------------------------------------
def nuovo(chiave: str, strada: str, *, t: Optional[Tuple[float, float]] = None,
          via: Optional[str] = None, azione: Any = None, mode: Any = None,
          rif: Any = None, decisione_ms: Optional[float] = None,
          invio: Any = None, invio_orologio: str = "pc") -> None:
    """Una richiesta e' stata LETTA dal worker (istante ``t`` = ricezione).

    ``invio`` = istante della scrittura in coda / arrivo sul canale (ms o ISO);
    ``invio_orologio`` = di chi e' quell'orologio (``db`` per ``requested_at``)."""
    try:
        mono, wall = t if t is not None else ora()
        voce = {
            "chiave": str(chiave), "strada": str(strada), "via": via or strada,
            "azione": azione, "mode": mode, "rif": rif,
            "decisione_ms": _ms_da(decisione_ms), "invio_ms": _ms_da(invio),
            "invio_orologio": invio_orologio,
            "ricezione_mono": mono, "ricezione_wall": wall,
            "presa_mono": None, "creata_mono": time.monotonic(),
            "ordini": {}, "finita": False, "ok": None, "errore": None,
        }
        with _lock:
            vecchia = _voci.pop(voce["chiave"], None)
            if vecchia is not None:
                _chiudi_voce(vecchia, "sostituita")
            _voci[voce["chiave"]] = voce
            _pulisci()
    except Exception:  # noqa: BLE001 - la misura non ferma mai un ordine
        logger.debug("[tempi] nuovo KO", exc_info=True)
    finally:
        _svuota()


def presa(chiave: str) -> None:
    """Inizio di ``_dispatch``: la richiesta diventa quella corrente del thread."""
    try:
        mono = time.monotonic()
        with _lock:
            voce = _voci.get(str(chiave))
            if voce is not None and voce["presa_mono"] is None:
                voce["presa_mono"] = mono
        _filo.chiave = str(chiave) if voce is not None else None
    except Exception:  # noqa: BLE001
        logger.debug("[tempi] presa KO", exc_info=True)


def place(order: Any, t: Optional[Tuple[float, float]] = None) -> None:
    """Subito prima di ``market.place_order`` (``t`` = istante gia' preso, per il
    place-and-trim in cui l'ordine nasce dentro la chiamata)."""
    try:
        chiave = getattr(_filo, "chiave", None)
        if chiave is None:
            return
        mono, wall = t if t is not None else ora()
        oid = getattr(order, "id", None)
        if oid is None:
            return
        with _lock:
            voce = _voci.get(chiave)
            if voce is None:
                return
            voce["ordini"][str(oid)] = {
                "order": order, "place_mono": mono, "place_wall": wall,
                "risposta_wall": None, "placed_bf": None, "matched_bf": None,
                "abbinato_wall": None, "emesso": False,
            }
            _ordini[str(oid)] = chiave
    except Exception:  # noqa: BLE001
        logger.debug("[tempi] place KO", exc_info=True)


def fine(chiave: str, ok: bool, errore: Any = None) -> None:
    """Il dispatch e' finito. Senza ordini la riga si scrive subito; con ordini
    si aspetta risposta/abbinamento (gli ordini gia' terminali escono ora)."""
    try:
        if getattr(_filo, "chiave", None) == str(chiave):
            _filo.chiave = None
        with _lock:
            voce = _voci.get(str(chiave))
            if voce is None or voce["finita"]:
                return
            voce["finita"] = True
            voce["ok"] = bool(ok)
            voce["errore"] = (str(errore)[:80] if errore else None)
            if not voce["ordini"]:
                _voci.pop(voce["chiave"], None)
                _scrivi(voce, None, "ok" if ok else "errore")
                return
            for oid, o in list(voce["ordini"].items()):
                _osserva_ordine(voce, oid, o)
            _forse_rimuovi(voce)
    except Exception:  # noqa: BLE001
        logger.debug("[tempi] fine KO", exc_info=True)
    finally:
        _svuota()


def osserva(orders: Iterable[Any]) -> None:
    """Dallo stream ordini (``process_orders``) o dal reconcile tennis: per gli
    ordini che conosciamo legge risposta e abbinamento. Costo: un lookup per
    ordine; nessun IO."""
    try:
        if not _ordini:
            return
        for order in orders or ():
            oid = getattr(order, "id", None)
            if oid is None or str(oid) not in _ordini:
                continue
            with _lock:
                chiave = _ordini.get(str(oid))
                voce = _voci.get(chiave) if chiave is not None else None
                if voce is None:
                    _ordini.pop(str(oid), None)
                    continue
                o = voce["ordini"].get(str(oid))
                if o is None:
                    continue
                _osserva_ordine(voce, str(oid), o)
                _forse_rimuovi(voce)
    except Exception:  # noqa: BLE001
        logger.debug("[tempi] osserva KO", exc_info=True)
    finally:
        _svuota()


# ---------------------------------------------------------------------------
# interni
# ---------------------------------------------------------------------------
def _val(obj: Any, attr: str) -> Any:
    try:
        return getattr(obj, attr, None)
    except Exception:  # noqa: BLE001
        return None


def _stato(order: Any) -> Optional[str]:
    st = _val(order, "status")
    if st is None:
        return None
    return str(getattr(st, "name", None) or st)


def _osserva_ordine(voce: Dict[str, Any], oid: str, o: Dict[str, Any]) -> None:
    """Aggiorna gli istanti di UN ordine; scrive la riga al primo abbinamento o
    a stato terminale. Chiamata sotto ``_lock``."""
    if o["emesso"]:
        return
    order = o["order"]
    resp = _val(order, "responses")
    if o["risposta_wall"] is None and resp is not None:
        # istante (PC) in cui flumine ha registrato la risposta di placeOrders
        o["risposta_wall"] = _ms_da(_val(resp, "_date_time_placed"))
    if o["placed_bf"] is None:
        pr = _val(resp, "place_response") if resp is not None else None
        o["placed_bf"] = _ms_da(_val(pr, "placed_date")) if pr is not None else None
    cur = _val(resp, "current_order") if resp is not None else None
    if o["placed_bf"] is None and cur is not None:
        o["placed_bf"] = _ms_da(_val(cur, "placed_date"))
    try:
        abbinata = float(_val(order, "size_matched") or 0.0)
    except (TypeError, ValueError):
        abbinata = 0.0
    if abbinata > 0:
        if cur is not None:
            o["matched_bf"] = _ms_da(_val(cur, "matched_date"))
        o["abbinato_wall"] = ora()[1]
        _emetti_ordine(voce, oid, o, "abbinato")
        return
    stato = _stato(order)
    if stato in _STATI_TERMINALI:
        _emetti_ordine(voce, oid, o, stato.lower())


def _emetti_ordine(voce: Dict[str, Any], oid: str, o: Dict[str, Any], esito: str) -> None:
    o["emesso"] = True
    _ordini.pop(oid, None)
    _scrivi(voce, o, esito, oid=oid)


def _forse_rimuovi(voce: Dict[str, Any]) -> None:
    if voce["finita"] and all(o["emesso"] for o in voce["ordini"].values()):
        _voci.pop(voce["chiave"], None)


def _chiudi_voce(voce: Dict[str, Any], esito: str) -> None:
    """Voce che esce dalla cache (TTL, tetto): scrive cio' che ha."""
    ordini = voce["ordini"]
    if not ordini:
        _scrivi(voce, None, esito)
        return
    for oid, o in ordini.items():
        if not o["emesso"]:
            o["emesso"] = True
            _ordini.pop(oid, None)
            _scrivi(voce, o, esito, oid=oid)


def _pulisci() -> None:
    """TTL e tetto (sotto ``_lock``). Le voci sono in ordine di creazione."""
    adesso = time.monotonic()
    for chiave in list(_voci):
        voce = _voci[chiave]
        if adesso - voce["creata_mono"] <= TTL_S:
            break
        _voci.pop(chiave, None)
        _chiudi_voce(voce, "scaduto")
    while len(_voci) > MAX_VOCI:
        chiave = next(iter(_voci))
        _chiudi_voce(_voci.pop(chiave), "tetto")


def _d(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """b - a in ms (None se manca uno dei due)."""
    if a is None or b is None:
        return None
    return b - a


def tratti(voce: Dict[str, Any], o: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """I numeri di una riga (ms, None = non disponibile) + i tratti a orologi misti."""
    misti: List[str] = []
    ric_wall = voce["ricezione_wall"]
    invio = voce["invio_ms"]
    decisione = voce["decisione_ms"]
    out: Dict[str, Any] = {}
    out["decisione_ms"] = _d(decisione, invio)
    if out["decisione_ms"] is not None and voce["invio_orologio"] != "pc":
        misti.append(f"decisione:pc/{voce['invio_orologio']}")
    out["ricezione_ms"] = _d(invio, ric_wall)
    if out["ricezione_ms"] is not None and voce["invio_orologio"] != "pc":
        misti.append(f"ricezione:{voce['invio_orologio']}/pc")
    presa_mono = voce["presa_mono"]
    out["presa_ms"] = (None if presa_mono is None
                       else (presa_mono - voce["ricezione_mono"]) * 1000.0)
    if o is not None:
        out["place_ms"] = (None if presa_mono is None
                           else (o["place_mono"] - presa_mono) * 1000.0)
        out["interno_ms"] = (o["place_mono"] - voce["ricezione_mono"]) * 1000.0
        out["risposta_ms"] = _d(o["place_wall"], o["risposta_wall"])
        out["risposta_bf_ms"] = _d(o["place_wall"], o["placed_bf"])
        if out["risposta_bf_ms"] is not None:
            misti.append("risposta_bf:pc/betfair")
        if o["matched_bf"] is not None and o["placed_bf"] is not None:
            out["abbinato_ms"] = o["matched_bf"] - o["placed_bf"]
            out["abbinato_fonte"] = "betfair"
        elif o["abbinato_wall"] is not None:
            base = o["risposta_wall"] if o["risposta_wall"] is not None else o["place_wall"]
            out["abbinato_ms"] = o["abbinato_wall"] - base
            out["abbinato_fonte"] = ("osservato" if o["risposta_wall"] is not None
                                     else "osservato_da_place")
        else:
            out["abbinato_ms"] = None
            out["abbinato_fonte"] = None
    else:
        for k in ("place_ms", "interno_ms", "risposta_ms", "risposta_bf_ms", "abbinato_ms",
                  "abbinato_fonte"):
            out[k] = None
    out["orologi"] = ",".join(misti) if misti else None
    return out


_ORDINE_CAMPI = ("decisione_ms", "ricezione_ms", "presa_ms", "place_ms", "risposta_ms",
                 "abbinato_ms", "interno_ms", "risposta_bf_ms", "abbinato_fonte", "orologi")


def _fmt(v: Any) -> str:
    if v is None:
        return "na"
    if isinstance(v, float):
        return str(int(round(v)))
    return str(v).replace(" ", "_")


def riga_log(voce: Dict[str, Any], o: Optional[Dict[str, Any]], esito: str,
             oid: Optional[str] = None) -> str:
    t = tratti(voce, o)
    parti = [PREFISSO, f"ref={_fmt(voce['chiave'])}", f"strada={_fmt(voce['strada'])}",
             f"via={_fmt(voce['via'])}", f"azione={_fmt(voce['azione'])}",
             f"mode={_fmt(voce['mode'])}", f"ordine={_fmt(oid)}"]
    parti += [f"{k}={_fmt(t[k])}" for k in _ORDINE_CAMPI]
    parti.append(f"esito={_fmt(esito)}")
    if voce.get("errore"):
        parti.append(f"errore={_fmt(voce['errore'])}")
    parti.append(f"rif={_fmt(voce['rif'])}")
    return " ".join(parti)


def _scrivi(voce: Dict[str, Any], o: Optional[Dict[str, Any]], esito: str,
            oid: Optional[str] = None) -> None:
    """Prepara la riga (sotto ``_lock``): il log vero lo fa ``_svuota`` dopo,
    fuori dal lucchetto, cosi' nessun thread ordini aspetta l'IO del log."""
    try:
        _uscita.append(riga_log(voce, o, esito, oid))
    except Exception:  # noqa: BLE001
        pass


def _svuota() -> None:
    """Scrive le righe pronte (fuori dal lucchetto). Mai solleva."""
    try:
        if not _uscita:
            return
        with _lock:
            righe = list(_uscita)
            del _uscita[:]
        for r in righe:
            logger.info(r)
    except Exception:  # noqa: BLE001
        pass


def _azzera_per_test() -> None:
    """Svuota la cache (SOLO test)."""
    with _lock:
        _voci.clear()
        _ordini.clear()
        del _uscita[:]
    _filo.chiave = None
