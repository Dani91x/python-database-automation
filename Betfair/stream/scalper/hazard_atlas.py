"""hazard_atlas.py — ATLANTE HAZARD: caricamento e lookup, PURI.

Perche' questo modulo esiste (INCIDENTE 17/09/2026, causa vera del blackout
delle quote su tutto il feed):

``safe_strategy/service.py``, ``selezione.py`` e ``opportunity.py`` caricano
l'Atlante con un import PIGRO. Finche' viveva in ``theta_bot``, quell'import
tirava dentro ``Betfair.stream.scalper.__init__`` -> ``scalper_bot`` ->
``from flumine import BaseStrategy``. E ``flumine/__init__.py:13`` fa::

    bettingresources.RunnerBookEX = EX     # flumine/patching.py

cioe' SOSTITUISCE, per tutto il processo, la classe che betfairlightweight usa
per il ladder con una che lascia i livelli come DIZIONARI. Da quell'istante
``scanner.best_price`` (``levels[0].price``, dentro un ``except`` che ritorna
None) leggeva ``None`` su OGNI runner, da stream E da REST: il feed scriveva
quote nulle su tutti i mercati mentre Betfair mandava i prezzi (misurato:
``{'price': 3.2, 'size': 821.19}`` letto come ``None``). L'import e' pigro, e
scattava al primo giro che serviva l'Atlante: per questo la mattina - senza
calcio in gioco - il feed stava bene, e per questo il riavvio non risolveva.

Qui dentro NON si importa flumine, e non si deve mai. Il processo del feed
carica l'Atlante da questo modulo; ``theta_bot`` (che flumine lo usa davvero)
riesporta gli stessi nomi, cosi' i chiamanti storici non cambiano.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# percorso di default dell'Atlante Hazard (repo-relative, v1 15/07)
ATLAS_DEFAULT_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "omega", "data",
    "hazard_atlas_v1.json"))


# ---------------------------------------------------------------------------
# ATLANTE HAZARD — lookup PURO (testabile senza file/flumine)
# ---------------------------------------------------------------------------
# 24/09 - UN SOLO atlante per tutti i consumatori (Safe, Omega advisor, Mike,
# theta). Prima: Safe/selezione e Omega leggevano il v2, Mike/theta/scanner il
# v1 (default qui sopra), ognuno con la sua copia caricata una volta e mai piu'
# riletta. Ora c'e' un PERCORSO CORRENTE e una cache condivisa con ricarica
# per mtime:
#   1) ``hazard_atlas_live.json``: l'atlante RIGENERATO in automatico (scritto
#      in modo atomico da ``hazard_atlas_sync`` a partire dal DB, o a mano con
#      ``genera_atlante``). NON committato (.gitignore): e' una cache locale.
#   2) ``hazard_atlas_v2.json``: l'ultimo atlante committato (15/07), ripiego.
# v1 e v2 hanno IDENTICI i blocchi global/by_league/by_team/h2h_hint
# (verificato il 24/09): passare dal v1 al v2 non cambia un numero.
_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "omega", "data"))
ATLAS_V2_PATH = os.path.join(_DATA_DIR, "hazard_atlas_v2.json")
ATLAS_LIVE_PATH = os.path.join(_DATA_DIR, "hazard_atlas_live.json")

# ogni quanto (s) la cache condivisa guarda l'mtime del file: un os.stat, mai
# nel giro caldo piu' di una volta al minuto
MTIME_CHECK_S = 60.0

# oltre questi giorni l'atlante si DICHIARA vecchio nelle note (nessun effetto
# sulle decisioni: e' un'informazione per chi guarda, non una soglia)
ATLAS_STALE_DAYS = 3

_LOCK = threading.Lock()
_CONDIVISO: Dict[str, Any] = {"atlas": None, "path": None, "mtime": None, "check": 0.0}


def percorso_atlante() -> str:
    """Il file dell'atlante CORRENTE: il live se esiste, altrimenti il v2."""
    return ATLAS_LIVE_PATH if os.path.exists(ATLAS_LIVE_PATH) else ATLAS_V2_PATH


def reset_atlante_condiviso() -> None:
    """Svuota la cache condivisa (test / riavvio logico)."""
    with _LOCK:
        _CONDIVISO.update(atlas=None, path=None, mtime=None, check=0.0)


def atlante_condiviso(*, forza: bool = False) -> Dict[str, Any]:
    """L'atlante CORRENTE, UNA istanza per processo, ricaricata se cambia.

    Ogni ``MTIME_CHECK_S`` secondi guarda percorso e mtime: se il file e'
    cambiato (o e' comparso il live) lo rilegge. Un file nuovo illeggibile
    (scrittura a meta', JSON rotto) NON butta quello gia' in memoria: si
    tiene il vecchio e si riprova quando l'mtime cambia di nuovo. {} solo se
    non si e' mai letto niente. Mai eccezioni."""
    with _LOCK:
        adesso = time.monotonic()
        if (not forza and _CONDIVISO["atlas"] is not None
                and adesso - float(_CONDIVISO["check"]) < MTIME_CHECK_S):
            return _CONDIVISO["atlas"]
        _CONDIVISO["check"] = adesso
        path = percorso_atlante()
        try:
            mt: Optional[float] = os.path.getmtime(path)
        except OSError:
            mt = None
        if (_CONDIVISO["atlas"] is not None and path == _CONDIVISO["path"]
                and mt == _CONDIVISO["mtime"]):
            return _CONDIVISO["atlas"]
        try:
            with open(path, "r", encoding="utf-8") as fh:
                nuovo = json.load(fh)
            if not isinstance(nuovo, dict):
                raise ValueError("atlante non e' un oggetto JSON")
        except Exception as ex:  # noqa: BLE001 - l'atlante non ferma mai nessuno
            logger.warning("[hazard-atlas] atlante %s non leggibile: %s",
                           os.path.basename(path), str(ex)[:120])
            if _CONDIVISO["atlas"] is None:
                _CONDIVISO.update(atlas={}, path=path, mtime=mt)
            return _CONDIVISO["atlas"]
        if _CONDIVISO["atlas"] is not None:
            logger.info("[hazard-atlas] atlante ricaricato: %s (%s)",
                        os.path.basename(path), etichetta_atlante(nuovo))
        _CONDIVISO.update(atlas=nuovo, path=path, mtime=mt)
        return nuovo


def load_hazard_atlas(path: Optional[str] = None) -> Dict[str, Any]:
    """Carica l'Atlante Hazard.

    ``path`` esplicito = quel file, letto ora (comportamento storico).
    Senza ``path`` = l'atlante CORRENTE condiviso (``atlante_condiviso``):
    stessa istanza per tutto il processo, ricaricata se il file cambia. Se non
    c'e' nessun file leggibile solleva FileNotFoundError, come prima (i
    chiamanti storici - theta, Mike - trattano l'eccezione come 'atlante
    assente')."""
    if path:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    atlas = atlante_condiviso()
    if not atlas:
        raise FileNotFoundError(f"nessun atlante leggibile in {_DATA_DIR}")
    return atlas


def eta_atlante(atlas: Optional[Dict[str, Any]],
                adesso: Optional[_dt.datetime] = None) -> Dict[str, Any]:
    """Data di generazione, eta' in giorni e partite dell'atlante.

    {'generated_at': datetime|None, 'giorni': float|None, 'n_partite': int|None,
     'vecchio': bool}. Un atlante senza data e' dichiarato vecchio: non si
    presume fresco cio' che non dice quando e' nato."""
    meta = (atlas or {}).get("meta") or {}
    gen = None
    raw = meta.get("generated_at")
    if isinstance(raw, str) and raw:
        try:
            gen = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if gen.tzinfo is None:
                gen = gen.replace(tzinfo=_dt.timezone.utc)
        except ValueError:
            gen = None
    n = meta.get("n_fixtures_used")
    try:
        n = int(n) if n is not None else None
    except (TypeError, ValueError):
        n = None
    if gen is None:
        return {"generated_at": None, "giorni": None, "n_partite": n, "vecchio": True}
    ora = adesso or _dt.datetime.now(_dt.timezone.utc)
    giorni = max(0.0, (ora - gen).total_seconds() / 86400.0)
    return {"generated_at": gen, "giorni": giorni, "n_partite": n,
            "vecchio": giorni > ATLAS_STALE_DAYS}


def etichetta_atlante(atlas: Optional[Dict[str, Any]],
                      adesso: Optional[_dt.datetime] = None) -> str:
    """'atlante del GG/MM, n partite' (+ ', VECCHIO: k giorni' se lo e').
    ASCII-only: finisce nelle note mostrate in Control Room."""
    e = eta_atlante(atlas, adesso)
    n = e["n_partite"]
    partite = f"{n} partite" if n is not None else "partite n/d"
    if e["generated_at"] is None:
        return f"atlante senza data, {partite}, VECCHIO: eta' ignota"
    testo = f"atlante del {e['generated_at']:%d/%m}, {partite}"
    if e["vecchio"]:
        testo += f", VECCHIO: {int(e['giorni'])} giorni"
    return testo


def hazard_bucket(minute: float) -> str:
    """Bucket 5' dell'Atlante ('0-5' .. '85-90') dal minuto reale."""
    m = max(0, min(89, int(minute)))
    lo = (m // 5) * 5
    return f"{lo}-{lo + 5}"


def hazard_goals_key(goals: int) -> str:
    """Chiave gol dell'Atlante: '0' | '1' | '2' | '3+'."""
    g = max(0, int(goals))
    return "3+" if g >= 3 else str(g)


def _find_team(by_team: Dict[str, Any], name: Optional[str]) -> Optional[dict]:
    """Cerca la squadra PER NOME (case-insensitive). None = fallback lega."""
    if not name:
        return None
    n = str(name).strip().lower()
    for t in by_team.values():
        if str(t.get("team_name", "")).strip().lower() == n:
            return t
    return None


def hazard_lookup(
    atlas: Optional[Dict[str, Any]],
    minute: float,
    goals: int,
    league_id: Optional[Any] = None,
    home_team: Optional[str] = None,
    away_team: Optional[str] = None,
    horizon: str = "p_goal_next_3min",
) -> Tuple[Optional[float], str]:
    """P(gol nei prossimi 3') per lo stato (minuto, gol) — catena meta.lookup.

    1) SQUADRE: entrambe in by_team + lega in by_league →
       f_att(T,b)=att_rate(T,b)/side_rate(lega,b), f_def analogo;
       M(b)=0.5*[fA_att*fB_def + fB_att*fA_def];
       P = 1 - (1 - P_lega(b,g))^M.
    2) LEGA: by_league[league_id].grid (gia' shrinkata).
    3) GLOBALE: atlas['global'].
    Ritorna (p, fonte) con fonte in {'team','league','global','none'};
    (None, 'none') = semaforo ROSSO (fail-closed).
    """
    if not atlas:
        return None, "none"
    b = hazard_bucket(minute)
    gk = hazard_goals_key(goals)
    by_league = atlas.get("by_league") or {}
    lg = by_league.get(str(league_id)) if league_id is not None else None

    # 1) livello SQUADRE (blend moltiplicativo sull'hazard di lega)
    if lg is not None:
        by_team = atlas.get("by_team") or {}
        ta = _find_team(by_team, home_team)
        tb = _find_team(by_team, away_team)
        cell = ((lg.get("grid") or {}).get(b) or {}).get(gk)
        sr = ((lg.get("meta") or {}).get("side_rate_per_bucket") or {}).get(b)
        if ta and tb and cell and sr:
            p_lega = cell.get(horizon)
            if p_lega is not None:
                try:
                    fa_att = float(ta["att_goals_per_match_by_bucket"].get(b, sr)) / sr
                    fa_def = float(ta["def_goals_per_match_by_bucket"].get(b, sr)) / sr
                    fb_att = float(tb["att_goals_per_match_by_bucket"].get(b, sr)) / sr
                    fb_def = float(tb["def_goals_per_match_by_bucket"].get(b, sr)) / sr
                    mult = 0.5 * (fa_att * fb_def + fb_att * fa_def)
                    p = 1.0 - (1.0 - float(p_lega)) ** max(0.0, mult)
                    return p, "team"
                except (KeyError, TypeError, ValueError, ZeroDivisionError):
                    pass  # fallback dichiarato: lega
        # 2) livello LEGA
        if cell is not None and cell.get(horizon) is not None:
            return float(cell[horizon]), "league"

    # 3) livello GLOBALE
    cell = ((atlas.get("global") or {}).get(b) or {}).get(gk)
    if cell is not None and cell.get(horizon) is not None:
        return float(cell[horizon]), "global"
    return None, "none"
