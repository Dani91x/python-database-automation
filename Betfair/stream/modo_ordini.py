"""modo_ordini - LA MODALITA' ORDINI (OFF / PAPER / LIVE) SI SCEGLIE DALLA UI.

Ordine dell'utente (24/09): "devo operare dalla UI, non dal codice". Fino a
oggi ``LIVE_ORDER_MODE`` viveva SOLO nel ``.env``: era il gate del trading
manuale dal ladder E il freno di Safe/Mike/Omega sugli ordini reali
(``safe_strategy.execution._live_brake``).

DUE FONTI, UNA REGOLA (fail-closed)

  * ``LIVE_ORDER_MODE`` nel ``.env`` = il TETTO DELL'AMBIENTE. E' anche la
    CAPACITA' del processo: il runner costruisce il client reale solo se il
    tetto e' LIVE (``runner.build_order_client``). La UI non puo' superarlo.
  * ``betfair_live_settings.order_mode`` (riga singleton, la STESSA del
    kill-switch da UI) = la SCELTA dalla Control Room (RPC
    ``set_live_order_mode``).

  modo effettivo = il PIU' RESTRITTIVO dei due (OFF < PAPER < LIVE).
  Riga assente, colonna assente, valore illeggibile o lettura troppo vecchia
  -> OFF. Nessun ripiego "ottimista": ai soldi veri si arriva SCRIVENDOLO
  (regola del 14/09), mai ereditandolo.

LE LETTURE (nessuna lettura DB in piu' per giro)

  * Nel runner il valore arriva GRATIS: il worker della coda legge gia'
    ``get_live_settings`` a ~1 s per il kill-switch (``_refresh_settings``) e
    lo registra qui con ``registra_settings``.
  * Nei processi dei bot (Safe/Mike/Omega) il valore serve SOLO prima di
    un'APERTURA live (``_live_brake``): ``aggiorna_da_db`` rilegge al massimo
    ogni ``ETA_RILETTURA_BOT_S`` secondi, mai a ogni giro.
  * Una lettura vale ``VALIDITA_S`` secondi: oltre, la riga e' "illeggibile"
    e il modo e' OFF finche' non torna una lettura buona.

Questo modulo e' volutamente PICCOLO e senza dipendenze pesanti: lo importano
il runner, il worker, l'esecuzione dei bot e i banchi di replay.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Optional

logger = logging.getLogger(__name__)

#: i tre livelli, dal piu' restrittivo al meno restrittivo
LIVELLI = ("OFF", "PAPER", "LIVE")
_RANGO = {m: i for i, m in enumerate(LIVELLI)}

#: nome della variabile d'ambiente (il tetto)
ENV_MODO = "LIVE_ORDER_MODE"

#: chiavi della riga ``betfair_live_settings`` (contratto con la migrazione
#: ``migrations/live_order_mode_control_2026-09-24.sql``)
COL_MODO = "order_mode"
COL_MODO_AGG_AT = "order_mode_updated_at"
COL_MODO_AGG_DA = "order_mode_updated_by"
COL_KILL = "kill_switch"

#: oltre quanti secondi una lettura del DB non vale piu' (-> OFF)
VALIDITA_S = 30.0
#: ogni quanto, al massimo, un processo di bot rilegge il DB (solo su apertura live)
ETA_RILETTURA_BOT_S = 5.0

# Motivi (contratto con la UI e i log: non cambiarli in silenzio)
MOTIVO_OK = "ok"
MOTIVO_TETTO = "tetto_ambiente"
MOTIVO_DB_ASSENTE = "db_assente"


def normalizza(valore: Any) -> Optional[str]:
    """'live' / ' Paper ' / 'OFF' -> 'LIVE' / 'PAPER' / 'OFF'. Altro -> None."""
    if valore is None:
        return None
    try:
        v = str(valore).strip().upper()
    except Exception:  # noqa: BLE001 - un oggetto strano non e' un modo
        return None
    return v if v in _RANGO else None


def modo_effettivo(env: Any, db: Any) -> str:
    """LA REGOLA, pura: il piu' restrittivo fra tetto dell'ambiente e scelta UI.

    Ognuno dei due illeggibile (assente, vuoto, valore sconosciuto) -> OFF.
    """
    e = normalizza(env)
    d = normalizza(db)
    if e is None or d is None:
        return "OFF"
    return e if _RANGO[e] <= _RANGO[d] else d


def descrivi(env: Any, db: Any) -> Dict[str, Any]:
    """Il modo effettivo con il PERCHE' (per la UI e per i log).

    ``motivo``: ``ok`` (vale la scelta dalla UI), ``tetto_ambiente`` (la UI
    chiede di piu' di quanto l'ambiente consenta: vale il tetto),
    ``db_assente`` (la scelta non e' stata letta: OFF).
    """
    e = normalizza(env) or "OFF"
    d = normalizza(db)
    eff = modo_effettivo(env, db)
    if d is None:
        motivo = MOTIVO_DB_ASSENTE
    elif _RANGO[d] > _RANGO[e]:
        motivo = MOTIVO_TETTO
    else:
        motivo = MOTIVO_OK
    return {"effettivo": eff, "tetto_ambiente": e, "scelto_ui": d, "motivo": motivo}


def modo_ambiente() -> str:
    """Il TETTO: ``LIVE_ORDER_MODE`` riletto a ogni chiamata. Assente/ignoto -> OFF."""
    return normalizza(os.getenv(ENV_MODO, "OFF")) or "OFF"


# ---------------------------------------------------------------------------
# L'ultima lettura della riga di controllo (stato di PROCESSO)
# ---------------------------------------------------------------------------
_LOCK = threading.Lock()
_STATO: Dict[str, Any] = {
    "modo": None,          # normalizzato, None = colonna assente / valore ignoto
    "kill": False,
    "agg_at": None,
    "agg_da": None,
    "letto_mono": None,    # time.monotonic() dell'ultima lettura buona
    "tentato_mono": None,  # ultimo tentativo (anche fallito): cadenza dei bot
    "banco": False,        # True = dichiarato da un banco/test, non scade
    "avvio_atteso": False,  # True = runner appena avviato, riga non ancora riportata a PAPER
}


def _ora() -> float:
    return time.monotonic()


def registra_settings(dati: Any) -> None:
    """Registra una lettura BUONA di ``get_live_settings`` (dict della riga).

    Una riga senza ``order_mode`` (migrazione non applicata) e' una lettura
    buona di un valore ASSENTE: il modo effettivo e' OFF.
    """
    if not isinstance(dati, dict):
        return
    with _LOCK:
        if _STATO["banco"]:
            return  # un banco dichiarato non si fa sovrascrivere da un DB finto
        _STATO["modo"] = normalizza(dati.get(COL_MODO))
        _STATO["kill"] = bool(dati.get(COL_KILL))
        _STATO["agg_at"] = dati.get(COL_MODO_AGG_AT)
        _STATO["agg_da"] = dati.get(COL_MODO_AGG_DA)
        _STATO["letto_mono"] = _ora()


def _fresca() -> bool:
    if _STATO["banco"]:
        return True
    letto = _STATO["letto_mono"]
    return letto is not None and (_ora() - float(letto)) <= VALIDITA_S


def valore_db() -> Optional[str]:
    """La scelta dalla UI, se letta e ancora valida; altrimenti None (-> OFF).

    Nel runner appena avviato (``richiedi_avvio``) vale None finche' la riga non
    e' stata riportata a PAPER per questo avvio (``dichiara_avvio``): la scelta
    di IERI non si eredita nemmeno per un giro."""
    with _LOCK:
        if _STATO["avvio_atteso"] and not _STATO["banco"]:
            return None
        return _STATO["modo"] if _fresca() else None


def kill_switch_db() -> bool:
    """Il kill-switch della riga (da UI). Lettura non valida -> False: in quel
    caso il modo effettivo e' gia' OFF, che ferma ogni apertura."""
    with _LOCK:
        return bool(_STATO["kill"]) if _fresca() else False


def modo_corrente() -> str:
    """Il modo EFFETTIVO di questo processo adesso (tetto x ultima scelta letta)."""
    return modo_effettivo(modo_ambiente(), valore_db())


def stato_corrente() -> Dict[str, Any]:
    """Il modo effettivo con motivo, chi/quando l'ha cambiato ed eta' della lettura."""
    out = descrivi(modo_ambiente(), valore_db())
    with _LOCK:
        letto = _STATO["letto_mono"]
        out["scelto_ui_at"] = _STATO["agg_at"]
        out["scelto_ui_da"] = _STATO["agg_da"]
        out["eta_lettura_s"] = (None if letto is None
                                else round(max(0.0, _ora() - float(letto)), 1))
    return out


def aggiorna_da_db(sb_factory: Optional[Callable[[], Any]] = None,
                   eta_max_s: float = ETA_RILETTURA_BOT_S) -> None:
    """Per i processi dei BOT: rilegge la riga se l'ultimo tentativo ha piu' di
    ``eta_max_s`` secondi. Mai solleva: un errore lascia l'ultima lettura, che
    scade da sola dopo ``VALIDITA_S`` (-> OFF)."""
    with _LOCK:
        if _STATO["banco"]:
            return
        tentato = _STATO["tentato_mono"]
        if tentato is not None and (_ora() - float(tentato)) < float(eta_max_s):
            return
        _STATO["tentato_mono"] = _ora()
    try:
        if sb_factory is None:
            from db_client import get_supabase_client as sb_factory  # type: ignore
        sb = sb_factory()
        res = sb.rpc("get_live_settings", {}).execute()
        dati = getattr(res, "data", None)
    except Exception as ex:  # noqa: BLE001 - DB giu': vale l'ultima lettura, poi OFF
        logger.warning("[modo_ordini] lettura di get_live_settings KO: %s", str(ex)[:160])
        return
    if isinstance(dati, dict):
        registra_settings(dati)
    else:
        logger.warning("[modo_ordini] get_live_settings senza riga: modo ordini OFF")


def azzera() -> None:
    """Dimentica ogni lettura (test, e nuovi processi)."""
    with _LOCK:
        _STATO.update({"modo": None, "kill": False, "agg_at": None, "agg_da": None,
                       "letto_mono": None, "tentato_mono": None, "banco": False,
                       "avvio_atteso": False})


def richiedi_avvio() -> None:
    """Il runner calcio all'avvio: finche' ``dichiara_avvio`` non riesce, la
    scelta dalla UI non vale (modo effettivo OFF per le aperture)."""
    with _LOCK:
        _STATO["avvio_atteso"] = True


def avvio_in_attesa() -> bool:
    with _LOCK:
        return bool(_STATO["avvio_atteso"])


@contextmanager
def dichiara_per_banco(modo: str, kill: bool = False) -> Iterator[None]:
    """SOLO banchi di replay e test: dichiara la scelta "dalla UI" per la durata
    del blocco, senza database (il banco non tocca mai il DB vero).

    Il tetto resta quello dell'ambiente: il banco dichiara ANCHE
    ``LIVE_ORDER_MODE`` (come faceva prima), qui si dichiara solo la riga.
    Nessuna variabile d'ambiente attiva questo percorso: si entra solo da codice.
    """
    with _LOCK:
        prima = dict(_STATO)
        _STATO.update({"modo": normalizza(modo), "kill": bool(kill), "agg_at": None,
                       "agg_da": "banco", "letto_mono": _ora(), "banco": True})
    try:
        yield
    finally:
        with _LOCK:
            _STATO.clear()
            _STATO.update(prima)


# ---------------------------------------------------------------------------
# ALL'AVVIO DELL'APP la scelta torna a PAPER (come Omega/Mike/Safe)
# ---------------------------------------------------------------------------
# Stesso schema di ``avvio_app.ferma_al_nuovo_avvio`` (Omega
# ``omega_service.ferma_al_nuovo_avvio``, Mike ``service.ferma_al_nuovo_avvio``,
# Safe ``bot_service.ferma_al_nuovo_avvio``): a un avvio NUOVO dell'app
# (``APP_BOOT_ID`` diverso o assente) la riga scende a PAPER; a un riavvio da
# watchdog (stesso id) non si tocca niente. Fail-closed coerente: all'avvio si
# SCENDE soltanto - LIVE -> PAPER, PAPER resta PAPER, OFF resta OFF (portare
# OFF a PAPER sarebbe salire, e salire e' un gesto dell'utente).
COL_BOOT_ID = "order_mode_boot_id"
MODO_ALL_AVVIO = "PAPER"


def modo_all_avvio(riga: Any, boot_id: str) -> Optional[str]:
    """Il modo da scrivere a questo avvio, o None se non va toccato (stesso avvio).

    ``riga``: l'ultima lettura di ``get_live_settings`` (dict). Riga non letta
    o senza modo -> PAPER (la colonna nasce 'paper'; scrivere PAPER su un
    valore ignoto non sale mai sopra la prova).
    """
    from . import avvio_app as AA

    r = riga if isinstance(riga, dict) else {}
    if AA.stesso_avvio({AA.CHIAVE_BOOT_ID: r.get(COL_BOOT_ID)}, boot_id):
        return None
    attuale = normalizza(r.get(COL_MODO))
    if attuale is None:
        return MODO_ALL_AVVIO
    return modo_effettivo(attuale, MODO_ALL_AVVIO)


def dichiara_avvio(sb: Any, riga: Any, boot_id: str, tetto: str) -> Dict[str, Any]:
    """Scrive (RPC ``live_order_mode_avvio``) l'id dell'avvio, il TETTO
    dell'ambiente di questo runner e, se e' un avvio nuovo, il modo sceso a PAPER.

    SOLLEVA se la scrittura fallisce: il chiamante (ripresa d'avvio del runner)
    tiene la guardia armata e riprova, e intanto la coda non esegue niente.
    """
    nuovo = modo_all_avvio(riga, boot_id)
    res = sb.rpc("live_order_mode_avvio", {
        "p_boot_id": str(boot_id or ""),
        "p_modo": nuovo.lower() if nuovo else None,
        "p_tetto": (normalizza(tetto) or "OFF").lower(),
    }).execute()
    dati = getattr(res, "data", None)
    if not isinstance(dati, dict):
        raise RuntimeError("live_order_mode_avvio: nessuna riga restituita")
    registra_settings(dati)
    with _LOCK:
        _STATO["avvio_atteso"] = False
    if nuovo is not None:
        prima = normalizza(riga.get(COL_MODO)) if isinstance(riga, dict) else None
        logger.warning("[modo_ordini] avvio nuovo dell'app: modo ordini dalla UI %s -> %s",
                       prima, normalizza(dati.get(COL_MODO)))
    return dati
