"""hazard_atlas_sync.py - porta l'Atlante Hazard dal DB al file che i bot leggono.

La action notturna rigenera l'atlante (``genera_atlante.py``) e lo scrive nella
tabella ``hazard_atlas``. Qui, SUL PC, un controllo leggero chiede al DB
"qual e' l'ultima versione?" (una riga, due colonne); solo se e' piu' nuova di
quella locale scarica il payload e lo scrive ATOMICO in
``omega/data/hazard_atlas_live.json``. Da li' TUTTI i consumatori (Safe,
Omega advisor, Mike, theta) lo ricaricano da soli per mtime
(``hazard_atlas.atlante_condiviso``): nessun riavvio, nessun processo nuovo.

ACCENSIONE: SPENTO di default. Si accende con ``HAZARD_ATLAS_SYNC=1`` nel
.env; il ciclo gira in un thread demone dentro un processo GIA' esistente
(lo scanner di Safe, ``service.py``), ogni ``HAZARD_ATLAS_SYNC_S`` secondi
(default 1800). Costo: 1 GET da una riga ogni 30 minuti + 1 download da ~4 MB
al giorno. Nessun flumine importato (vedi incidente 17/09 in hazard_atlas.py).

Mai eccezioni verso il chiamante: un guasto qui lascia il file che c'e'.
ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from . import hazard_atlas as HA

logger = logging.getLogger("hazard_atlas_sync")

_STATO: Dict[str, Any] = {"thread": None, "ultimo": None}


def _get(url: str, key: str, table: str, params: Dict[str, str], timeout: float = 30.0
         ) -> List[Dict[str, Any]]:
    q = urllib.parse.urlencode(params, safe="(),.*:!")
    req = urllib.request.Request(f"{url.rstrip('/')}/rest/v1/{table}?{q}", method="GET")
    req.add_header("apikey", key)
    req.add_header("Authorization", "Bearer " + key)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _generated_at_locale(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return str(((json.load(fh) or {}).get("meta") or {}).get("generated_at") or "") or None
    except Exception:  # noqa: BLE001
        return None


def _valido(atlas: Any) -> bool:
    """Un atlante scaricato si scrive SOLO se ha la forma che i consumatori
    leggono: meta.generated_at, global e by_league non vuoti."""
    return (isinstance(atlas, dict) and isinstance(atlas.get("meta"), dict)
            and bool(atlas["meta"].get("generated_at"))
            and isinstance(atlas.get("global"), dict) and bool(atlas["global"])
            and isinstance(atlas.get("by_league"), dict) and bool(atlas["by_league"]))


def sincronizza(*, url: Optional[str] = None, key: Optional[str] = None,
                path: Optional[str] = None,
                get: Optional[Callable[..., List[Dict[str, Any]]]] = None) -> Dict[str, Any]:
    """Un giro di sincronizzazione. {'esito': ..., 'generated_at': ...}.

    esito: 'aggiornato' | 'gia_aggiornato' | 'nessuna_versione' |
           'payload_non_valido' | 'errore' | 'config_mancante'."""
    url = url or (os.environ.get("SUPABASE_URL") or "").strip()
    key = key or (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    path = path or HA.ATLAS_LIVE_PATH
    get = get or _get
    if not url or not key:
        return {"esito": "config_mancante"}
    try:
        ult = get(url, key, "hazard_atlas", {"select": "id,generated_at",
                                             "order": "generated_at.desc", "limit": "1"})
        if not ult:
            return {"esito": "nessuna_versione"}
        remoto = str(ult[0].get("generated_at") or "")
        locale = _generated_at_locale(path)
        if locale and _confronta_date(locale, remoto) >= 0:
            return {"esito": "gia_aggiornato", "generated_at": locale}
        righe = get(url, key, "hazard_atlas", {"select": "payload", "id": f"eq.{int(ult[0]['id'])}"},
                    timeout=180.0)
        atlas = righe[0].get("payload") if righe else None
        if not _valido(atlas):
            logger.warning("[atlante-sync] versione %s non valida: file lasciato com'e'", remoto)
            return {"esito": "payload_non_valido", "generated_at": remoto}
        tmp = f"{path}.tmp{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(atlas, fh, ensure_ascii=True, separators=(",", ":"))
        os.replace(tmp, path)
        logger.info("[atlante-sync] atlante aggiornato: %s", HA.etichetta_atlante(atlas))
        return {"esito": "aggiornato", "generated_at": atlas["meta"]["generated_at"]}
    except Exception as ex:  # noqa: BLE001 - un guasto non tocca il file che c'e'
        logger.warning("[atlante-sync] KO: %s", str(ex)[:160])
        return {"esito": "errore", "errore": str(ex)[:160]}


def _confronta_date(a: str, b: str) -> int:
    """-1 se a < b, 0 se uguali, 1 se a > b (ISO 8601, anche con fuso)."""
    import datetime as dt
    try:
        da = dt.datetime.fromisoformat(a.replace("Z", "+00:00"))
        db = dt.datetime.fromisoformat(b.replace("Z", "+00:00"))
        if da.tzinfo is None:
            da = da.replace(tzinfo=dt.timezone.utc)
        if db.tzinfo is None:
            db = db.replace(tzinfo=dt.timezone.utc)
        return (da > db) - (da < db)
    except ValueError:
        return (a > b) - (a < b)


def abilitato() -> bool:
    return (os.environ.get("HAZARD_ATLAS_SYNC") or "").strip() in ("1", "true", "on", "si")


def avvia_se_abilitato(stop: Optional[threading.Event] = None) -> bool:
    """Accende il ciclo di sync in un thread demone, UNA volta per processo,
    solo se ``HAZARD_ATLAS_SYNC=1``. True se acceso ora o gia' acceso."""
    if not abilitato():
        return False
    if _STATO["thread"] is not None and _STATO["thread"].is_alive():
        return True
    try:
        passo = float((os.environ.get("HAZARD_ATLAS_SYNC_S") or "").strip() or 1800.0)
    except ValueError:
        passo = 1800.0
    passo = max(300.0, passo)
    fermo = stop or threading.Event()

    def _ciclo() -> None:
        while not fermo.is_set():
            _STATO["ultimo"] = sincronizza()
            fermo.wait(passo)

    t = threading.Thread(target=_ciclo, name="hazard-atlas-sync", daemon=True)
    _STATO["thread"] = t
    t.start()
    logger.info("[atlante-sync] acceso: controllo ogni %.0f s", passo)
    return True
