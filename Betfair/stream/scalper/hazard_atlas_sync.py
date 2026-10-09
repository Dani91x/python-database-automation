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
(lo scanner di Safe, ``service.py``). Nessun flumine importato (vedi
incidente 17/09 in hazard_atlas.py).

25/09: DUE modi (``HAZARD_ATLAS_MODO``). 'domanda' (default): questo thread
e' il motore dell'atlante A DOMANDA (``atlante_a_domanda.py``): le leghe
delle partite da osservare si preparano una volta e poi si aggiornano in
modo incrementale, ogni ``HAZARD_ATLAS_CICLO_S`` secondi (default 600).
'scarica': il comportamento del 24/09 descritto sopra, ogni
``HAZARD_ATLAS_SYNC_S`` secondi (default 1800): 1 GET da una riga ogni 30
minuti + 1 download per ogni versione nuova.

09/10/2026 (AUDIT_2026-10-09/fallimenti_action/ATLANTE_GLOBALE_LEGGERO.md): la
action NON scrive piu' nel payload globale by_league/by_team/h2h_hint/v4 (solo
``meta`` e ``global``, ``genera_atlante.payload_globale_leggero``). Il modo
'scarica', trovata una versione nuova con il payload leggero, ASSEMBLA l'atlante
come la action: stati per lega da ``hazard_atlas_leghe`` (stessa select di
``genera_atlante.leggi_stato_db``, a pagine per league_id), ``genera_atlante.assembla``
con il seme v3, la data e la filigrana della versione, e ``meta.run`` della versione.
Con gli stessi stati il file e' identico a quello che scaricava prima. Una versione
vecchia con il payload intero (prima della migrazione) si scrive come prima.

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


def _payload_leggero(atlas: Any) -> bool:
    """09/10: la riga globale scritta dal 09/10 (o svuotata dalla migrazione
    ``hazard_atlas_globale_leggero_2026-10-09.sql``): meta con la data, nessun
    ``by_league`` (i blocchi derivati si assemblano dalle righe per lega)."""
    return (isinstance(atlas, dict) and isinstance(atlas.get("meta"), dict)
            and bool(atlas["meta"].get("generated_at")) and "by_league" not in atlas)


# righe di hazard_atlas_leghe per GET nel modo 'scarica' (~90 KB di stato a riga)
PAGINA_LEGHE = 50


def _assembla_da_leghe(url: str, key: str, get: Callable[..., List[Dict[str, Any]]],
                       meta: Dict[str, Any], pagina: Optional[int] = None
                       ) -> Optional[Dict[str, Any]]:
    """L'atlante della versione ``meta`` riassemblato come la action
    (``genera_atlante.main``): stati di TUTTE le leghe da ``hazard_atlas_leghe``
    (``select=league_id,stato``, ordine per league_id come ``leggi_stato_db``),
    ``assembla`` con il seme v3 se c'e', data e filigrana della versione, poi
    ``meta.run`` della versione. Paginazione a chiave (niente OFFSET). Un errore
    di lettura sale al chiamante (il file che c'e' resta).

    None (file lasciato com'e') se le leghe lette sono meno di quelle che la
    action aveva nello stato (``meta.n_leagues_in_state``) o nessuna: senza
    questo controllo una lettura vuota o monca produrrebbe un atlante fatto
    del solo seme v3, che ``_valido`` accetterebbe."""
    from . import genera_atlante as G
    pagina = int(pagina or PAGINA_LEGHE)
    stati: Dict[str, Dict[str, Any]] = {}
    ultimo: Optional[Any] = None
    while True:
        p = {"select": "league_id,stato", "order": "league_id.asc", "limit": str(pagina)}
        if ultimo is not None:
            p["league_id"] = f"gt.{ultimo}"
        rows = get(url, key, "hazard_atlas_leghe", p, timeout=180.0)
        for r in rows:
            if isinstance(r.get("stato"), dict):
                stati[str(r["league_id"])] = r["stato"]
        if len(rows) < pagina:
            break
        ultimo = rows[-1]["league_id"]
    attese = int(meta.get("n_leagues_in_state") or 0)
    if not stati or len(stati) < attese:
        logger.warning("[atlante-sync] versione %s: lette %d leghe da hazard_atlas_leghe, la "
                       "action ne aveva %d: file lasciato com'e'", meta.get("generated_at"),
                       len(stati), attese)
        return None
    seme = None
    if os.path.exists(HA.ATLAS_V3_PATH):
        with open(HA.ATLAS_V3_PATH, "r", encoding="utf-8") as fh:
            seme = json.load(fh)
    wm = meta.get("watermark_event_id")
    atlas = G.assembla(stati, generated_at=str(meta["generated_at"]),
                       watermark=int(wm) if wm is not None else None, seme=seme)
    if "run" in meta:
        atlas["meta"]["run"] = meta["run"]
    return atlas


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
        if _payload_leggero(atlas):
            # 09/10: payload leggero (solo meta+global) -> si assembla dalle righe per lega
            atlas = _assembla_da_leghe(url, key, get, atlas["meta"])
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


def modo() -> str:
    """25/09 (ordine dell'utente: atlante LEGGERO e A DOMANDA): 'domanda'
    (default) = il motore ``atlante_a_domanda`` sul PC, guidato dalle partite
    da osservare; 'scarica' = il comportamento del 24/09 (scarica l'ultima
    versione assemblata dalla action)."""
    m = (os.environ.get("HAZARD_ATLAS_MODO") or "").strip().lower() or "domanda"
    return m if m in ("domanda", "scarica") else "domanda"


def _num(nome: str, default: float) -> float:
    try:
        return float((os.environ.get(nome) or "").strip() or default)
    except ValueError:
        return float(default)


def parametri_da_env() -> Dict[str, float]:
    """Parametri del motore a domanda dal .env (vuoto = default)."""
    from . import atlante_a_domanda as AD
    nomi = {"tetto_ciclo": "HAZARD_ATLAS_TETTO_CICLO", "tetto_ora": "HAZARD_ATLAS_TETTO_ORA",
            "pausa_lega_s": "HAZARD_ATLAS_PAUSA_LEGA_S", "stagioni_max": "HAZARD_ATLAS_STAGIONI",
            "giorni_inattiva": "HAZARD_ATLAS_GIORNI_INATTIVA"}
    return {k: _num(env, AD.PARAMETRI_DEFAULT[k]) for k, env in nomi.items()}


def crea_motore(url: str, key: str) -> Any:
    """Il motore a domanda con lettore vero (solo GET, passo gentile) e, se
    ``HAZARD_ATLAS_SCRIVI_DB`` non e' '0', lo scrittore di ``hazard_atlas_leghe``."""
    from . import atlante_a_domanda as AD
    from . import genera_atlante as G
    scrivi = (os.environ.get("HAZARD_ATLAS_SCRIVI_DB") or "").strip() != "0"
    return AD.MotoreAtlante(G.LettoreDB(url, key, pausa=0.2),
                            scrittore=G._Scrittore(url, key) if scrivi else None,
                            parametri=parametri_da_env())


def giro_a_domanda(motore: Any) -> Dict[str, Any]:
    """Un ciclo del motore; mai eccezioni (il file che c'e' resta)."""
    try:
        r = motore.ciclo()
        return {"esito": "ok", **r}
    except Exception as ex:  # noqa: BLE001
        logger.warning("[atlante-sync] ciclo a domanda KO: %s", str(ex)[:160])
        return {"esito": "errore", "errore": str(ex)[:160]}


def avvia_se_abilitato(stop: Optional[threading.Event] = None) -> bool:
    """Accende il ciclo di sync in un thread demone, UNA volta per processo,
    solo se ``HAZARD_ATLAS_SYNC=1``. True se acceso ora o gia' acceso.

    Modo 'domanda' (default dal 25/09): ogni ``HAZARD_ATLAS_CICLO_S`` secondi
    (default 600, minimo 120) un ciclo di ``atlante_a_domanda``. Modo
    'scarica': ogni ``HAZARD_ATLAS_SYNC_S`` (default 1800, minimo 300) il
    controllo della versione sul DB, come il 24/09."""
    if not abilitato():
        return False
    if _STATO["thread"] is not None and _STATO["thread"].is_alive():
        return True
    fermo = stop or threading.Event()
    if modo() == "domanda":
        url = (os.environ.get("SUPABASE_URL") or "").strip()
        key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        if not url or not key:
            logger.warning("[atlante-sync] modo a domanda senza SUPABASE_URL/KEY: spento")
            return False
        passo = max(120.0, _num("HAZARD_ATLAS_CICLO_S", 600.0))
        motore = crea_motore(url, key)

        def _ciclo() -> None:
            while not fermo.is_set():
                _STATO["ultimo"] = giro_a_domanda(motore)
                fermo.wait(passo)
    else:
        passo = max(300.0, _num("HAZARD_ATLAS_SYNC_S", 1800.0))

        def _ciclo() -> None:
            while not fermo.is_set():
                _STATO["ultimo"] = sincronizza()
                fermo.wait(passo)

    t = threading.Thread(target=_ciclo, name="hazard-atlas-sync", daemon=True)
    _STATO["thread"] = t
    t.start()
    logger.info("[atlante-sync] acceso (modo %s): ciclo ogni %.0f s", modo(), passo)
    return True
