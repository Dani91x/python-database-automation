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
# 25/09 - atlante A DOMANDA (hazard_atlas_sync, modo 'domanda'): il SEME e'
# il v3 committato (21 leghe, 2016-2025); lo stato grezzo delle leghe
# calcolate sul PC vive in un file locale NON committato (.gitignore).
ATLAS_V3_PATH = os.path.join(_DATA_DIR, "hazard_atlas_v3.json")
ATLAS_STATO_PATH = os.path.join(_DATA_DIR, "hazard_atlas_stato.json")

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


def _find_team(by_team: Dict[str, Any], name: Optional[str],
               league_id: Optional[Any] = None, team_id: Optional[Any] = None) -> Optional[dict]:
    """La squadra dell'atlante: prima per ID (chiave di ``by_team`` = id
    API-Football), poi PER NOME (case-insensitive). 25/09: con tutte le leghe
    i nomi si ripetono ("Nacional", "Sporting"...): fra piu' squadre con lo
    stesso nome vince quella della lega della partita; se resta ambiguo nessuna
    (fallback dichiarato alla lega, mai la squadra sbagliata). Sul v2 nessun
    nome e' ripetuto (632 squadre, verificato il 25/09): stesso esito di prima.
    None = fallback lega."""
    if team_id is not None:
        try:
            t = by_team.get(str(int(team_id)))
        except (TypeError, ValueError):
            t = None
        if t:
            return t
    if not name:
        return None
    n = str(name).strip().lower()
    trovate = [t for t in by_team.values() if str(t.get("team_name", "")).strip().lower() == n]
    if len(trovate) <= 1:
        return trovate[0] if trovate else None
    if league_id is not None:
        stessa = [t for t in trovate if str(t.get("league_id")) == str(league_id)]
        if len(stessa) == 1:
            return stessa[0]
    return None


# 25/09 - confidenza a video (stesse regole del generatore, qui senza
# importarlo: il modulo resta puro). Per un atlante che non le porta scritte
# (v1/v2) si calcolano da n e K.
_K_DEFAULT = 1500.0
_MIN_LEGA_DEFAULT = 300
_MIN_LEGA_MEDIA = 100
_LIVELLI = {"team": "squadra+lega", "league": "lega", "global": "globale", "none": "nessuno"}


def _conf_cella(n: Any, k: float) -> str:
    try:
        n = max(0, int(n or 0))
    except (TypeError, ValueError):
        n = 0
    w = n / (n + k) if (n + k) > 0 else 0.0
    return "alta" if w >= 0.5 else ("media" if w >= 0.2 else "bassa")


def _conf_lega(n_fixtures: Any, soglia: int) -> str:
    try:
        n = int(n_fixtures or 0)
    except (TypeError, ValueError):
        n = 0
    return "alta" if n >= soglia else ("media" if n >= _MIN_LEGA_MEDIA else "bassa")


_ORDINE_CONF = {"bassa": 0, "media": 1, "alta": 2}


def leghe_in_preparazione(atlas: Optional[Dict[str, Any]]) -> set:
    """Leghe che l'atlante a domanda sta calcolando ora (scritte nel meta del
    file live, cosi' le vede ogni processo che legge l'atlante)."""
    raw = ((atlas or {}).get("meta") or {}).get("leghe_in_preparazione") or []
    return {str(x) for x in raw}


def consulta_atlante(
    atlas: Optional[Dict[str, Any]],
    minute: float,
    goals: int,
    league_id: Optional[Any] = None,
    *,
    home_id: Optional[Any] = None,
    away_id: Optional[Any] = None,
    home_team: Optional[str] = None,
    away_team: Optional[str] = None,
    horizon: str = "p_goal_next_3min",
    adesso: Optional[_dt.datetime] = None,
) -> Dict[str, Any]:
    """L'atlante per la PARTITA OSSERVATA (lega, squadre, minuto, gol).

    Stessa catena di ``hazard_lookup`` (squadre -> lega -> globale) e stesso
    numero; in piu' DICHIARA come e' nato:
      p            probabilita' (None = nessun dato, fail-closed)
      fonte        'team' | 'league' | 'global' | 'none' (chiave storica)
      livello      'squadra+lega' | 'lega' | 'globale' | 'nessuno'
      n            partite-minuto della cella usata (lega o globale)
      confidenza   'alta' | 'media' | 'bassa' (cella; per la lega il minimo
                   fra cella e lega: pochi dati di lega = bassa)
      lega         {'coperta', 'in_preparazione', 'n_partite', 'confidenza',
                    'nome', 'affidabile', 'da_seme'}
      atlante      etichetta ('atlante del GG/MM, n partite'), eta_giorni
      nota         frase breve ASCII per la Control Room.
    Il livello SQUADRE si usa solo su lega affidabile (>= min_fixtures_league
    partite): i profili squadra sono shrinkati verso il side_rate di una lega
    affidabile, altrimenti il rapporto non avrebbe senso. Mai eccezioni."""
    out: Dict[str, Any] = {"p": None, "fonte": "none", "livello": "nessuno", "n": None,
                           "confidenza": None, "lega": {"coperta": False, "in_preparazione": False,
                                                        "n_partite": None, "confidenza": None,
                                                        "nome": None, "affidabile": False,
                                                        "da_seme": False},
                           "atlante": None, "eta_giorni": None, "nota": "atlante assente"}
    if not atlas:
        return out
    try:
        meta = atlas.get("meta") or {}
        e = eta_atlante(atlas, adesso)
        out["atlante"] = etichetta_atlante(atlas, adesso)
        out["eta_giorni"] = round(e["giorni"], 2) if e["giorni"] is not None else None
        k = float(((meta.get("shrinkage") or {}).get("K_league_fixture_minutes")) or _K_DEFAULT)
        soglia = int(meta.get("min_fixtures_league") or _MIN_LEGA_DEFAULT)
        b = hazard_bucket(minute)
        gk = hazard_goals_key(goals)
        lid = str(league_id) if league_id is not None else None
        lg = (atlas.get("by_league") or {}).get(lid) if lid is not None else None
        lega = out["lega"]
        lega["in_preparazione"] = lid is not None and lid in leghe_in_preparazione(atlas)
        if isinstance(lg, dict):
            lm = lg.get("meta") or {}
            nf = lm.get("n_fixtures")
            if "affidabile" in lm:
                affidabile = bool(lm["affidabile"])
            else:
                # atlante v1/v2 (solo leghe >= soglia) o meta senza conteggio:
                # comportamento storico, il livello squadre resta ammesso
                affidabile = nf is None or _conf_lega(nf, soglia) == "alta"
            lega.update(coperta=True, n_partite=nf, nome=lm.get("league_name"),
                        confidenza=lm.get("confidenza") or (_conf_lega(nf, soglia)
                                                            if nf is not None else None),
                        affidabile=affidabile, da_seme=bool(lm.get("da_seme")))
        p, fonte, cell = None, "none", None
        if isinstance(lg, dict):
            cell = ((lg.get("grid") or {}).get(b) or {}).get(gk)
            sr = ((lg.get("meta") or {}).get("side_rate_per_bucket") or {}).get(b)
            by_team = atlas.get("by_team") or {}
            ta = _find_team(by_team, home_team, league_id, home_id)
            tb = _find_team(by_team, away_team, league_id, away_id)
            if lega["affidabile"] and ta and tb and cell and sr and cell.get(horizon) is not None:
                try:
                    fa_att = float(ta["att_goals_per_match_by_bucket"].get(b, sr)) / sr
                    fa_def = float(ta["def_goals_per_match_by_bucket"].get(b, sr)) / sr
                    fb_att = float(tb["att_goals_per_match_by_bucket"].get(b, sr)) / sr
                    fb_def = float(tb["def_goals_per_match_by_bucket"].get(b, sr)) / sr
                    mult = 0.5 * (fa_att * fb_def + fb_att * fa_def)
                    p = 1.0 - (1.0 - float(cell[horizon])) ** max(0.0, mult)
                    fonte = "team"
                except (KeyError, TypeError, ValueError, ZeroDivisionError, AttributeError):
                    p = None      # fallback dichiarato: lega
            if p is None and cell is not None and cell.get(horizon) is not None:
                p, fonte = float(cell[horizon]), "league"
        if p is None:
            cell = ((atlas.get("global") or {}).get(b) or {}).get(gk)
            if cell is not None and cell.get(horizon) is not None:
                p, fonte = float(cell[horizon]), "global"
            else:
                cell = None
        out.update(p=p, fonte=fonte, livello=_LIVELLI[fonte])
        if cell is not None:
            out["n"] = cell.get("n")
            conf = cell.get("conf") or _conf_cella(cell.get("n"), k)
            if fonte in ("team", "league") and lega["confidenza"] in _ORDINE_CONF:
                conf = min(conf, lega["confidenza"], key=lambda c: _ORDINE_CONF.get(c, 0))
            out["confidenza"] = conf
        out["nota"] = _nota_consulta(out, lid)
    except Exception as ex:  # noqa: BLE001 - l'atlante non ferma mai nessuno
        logger.debug("[hazard-atlas] consulta KO: %s", str(ex)[:120])
        out.update(p=None, fonte="none", livello="nessuno", nota="atlante illeggibile")
    return out


def _nota_consulta(c: Dict[str, Any], lid: Optional[str]) -> str:
    """'storico lega Serie B (lega, n=4210, confidenza media; atlante del ...)'."""
    lega = c["lega"]
    chi = lega.get("nome") or (f"lega {lid}" if lid else "lega n/d")
    if c["fonte"] == "none":
        base = "nessun dato storico per lo stato"
    elif c["fonte"] == "global":
        if lega.get("in_preparazione"):
            base = f"{chi} in preparazione: storico globale"
        elif lid is None:
            base = "lega n/d: storico globale"
        else:
            base = f"lega {lid} senza dati nel DB: storico globale"
    else:
        base = f"storico {chi} ({c['livello']}, {lega.get('n_partite')} partite"
        if lega.get("da_seme"):
            base += ", dal seme"
        base += ")"
    extra = []
    if c.get("n") is not None:
        extra.append(f"n={c['n']}")
    if c.get("confidenza"):
        extra.append(f"confidenza {c['confidenza']}")
    if c.get("atlante"):
        extra.append(c["atlante"])
    return base + (f" [{'; '.join(extra)}]" if extra else "")


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

    1) SQUADRE: entrambe in by_team + lega AFFIDABILE in by_league →
       f_att(T,b)=att_rate(T,b)/side_rate(lega,b), f_def analogo;
       M(b)=0.5*[fA_att*fB_def + fB_att*fA_def];
       P = 1 - (1 - P_lega(b,g))^M.
    2) LEGA: by_league[league_id].grid (gia' shrinkata).
    3) GLOBALE: atlas['global'].
    Ritorna (p, fonte) con fonte in {'team','league','global','none'};
    (None, 'none') = semaforo ROSSO (fail-closed). 25/09: e' la forma corta
    di ``consulta_atlante`` (stesso calcolo, stessi numeri)."""
    c = consulta_atlante(atlas, minute, goals, league_id, home_team=home_team,
                         away_team=away_team, horizon=horizon)
    return c["p"], c["fonte"]
