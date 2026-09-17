"""SELEZIONE AGGIUNTIVA del RISULTATO ESATTO (SPEC §2) — il DATO, non la regola.

    | Selezione aggiuntiva | scontri diretti senza troppi 2-2/3-3,
    |                      | difesa avversaria solida                  (SPEC §2)

Questo modulo NON decide niente: prepara i due NUMERI che la voce della SPEC
nomina, e li consegna allo scanner perche' li pubblichi nella riga di scan. La
regola (le soglie, il verso) vive nel motore, in UN SOLO posto, e viene letta
identica dal motore Python (il bot) e da quello TypeScript (la pagina) — la
stessa disciplina dell'indice di CONTROLLO del gioco (`pressure.py`): un solo
numero calcolato una volta sola, mai due ricalcoli che possono divergere.

DA DOVE VIENE IL DATO — nessuna risorsa nuova (regola: prima si cerca):
  `Betfair/omega/data/hazard_atlas_v2.json`, lo stesso file che usa gia'
  `omega_advisor.h2h_score_stats` (blocco `h2h_hint`) e che il consulente di
  Omega interroga per le missioni. Si carica con il loader gia' esistente
  (`Betfair/stream/scalper/theta_bot.load_hazard_atlas`). Nessuna lettura DB,
  nessuna chiamata di rete, nessun processo nuovo.

  * `h2h_hint['<idA>-<idB>']['ft_scores_a_b']` — distribuzione dei punteggi
    finali negli scontri diretti (solo coppie con >= 3 incontri: e' il
    contratto del dato, non una soglia nostra). 2-2 e 3-3 sono simmetrici,
    quindi l'orientamento della chiave non conta.
  * `by_team['<id>']['def_goals_per_match_by_bucket']` — gol SUBITI per
    partita spezzati nei 18 bucket da 5': la somma e' la media dei gol subiti
    per partita, cioe' la "solidita' della difesa".

L'ABBINAMENTO E' PER NOME, e questo e' un limite dichiarato: la riga di scan
porta i nomi delle due squadre (dall'evento Betfair e dal punteggio IPS), non
l'id della fixture (`service.py`: «lo scanner non ha il fixture_id»). Si
riusa la ricerca per nome gia' scritta (`theta_bot._find_team`), normalizzata.
Nome che non si trova = dato ASSENTE, mai un abbinamento forzato: meglio un
"non lo so" che una statistica di un'altra squadra.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("safe.selezione")

# lo STESSO file dell'advisor di Omega (che ha il blocco h2h_hint): non se ne
# aggiunge un altro, non se ne copia il contenuto.
ATLAS_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "omega", "data", "hazard_atlas_v2.json"))

# i punteggi che la SPEC chiama per nome: i pareggi "alti". Sono simmetrici,
# quindi valgono in qualunque verso sia orientata la chiave dell'atlante.
PAREGGI_ALTI: Tuple[str, ...] = ("2-2", "3-3")

FONTE = "hazard_atlas_v2"

# cache di processo: l'atlante (4 MB) si legge UNA volta, gli indici si
# costruiscono una volta, e ogni coppia di nomi si risolve una volta sola.
_ATLAS: Optional[Dict[str, Any]] = None
_INDICE_NOMI: Optional[Dict[str, str]] = None
_HINT_CACHE: Dict[Tuple[str, str], Optional[Dict[str, Any]]] = {}
_CACHE_MAX = 512


def reset_cache() -> None:
    """Svuota atlante e cache (test / riavvio logico)."""
    global _ATLAS, _INDICE_NOMI
    _ATLAS = None
    _INDICE_NOMI = None
    _HINT_CACHE.clear()


def _normalizza(nome: Any) -> str:
    """Nome confrontabile: senza accenti, senza punteggiatura, minuscolo."""
    s = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def atlante() -> Dict[str, Any]:
    """L'atlante, caricato una volta sola. {} se manca o e' illeggibile."""
    global _ATLAS
    if _ATLAS is None:
        try:
            from Betfair.stream.scalper.hazard_atlas import load_hazard_atlas

            _ATLAS = load_hazard_atlas(ATLAS_PATH) or {}
        except Exception as ex:  # noqa: BLE001 - l'atlante non deve mai fermare lo scanner
            logger.warning("[safe-selezione] atlante non leggibile: %s", str(ex)[:120])
            _ATLAS = {}
    return _ATLAS


def _indice_nomi() -> Dict[str, str]:
    """nome normalizzato -> id squadra. Un nome ambiguo (due squadre con lo
    stesso nome normalizzato) viene SCARTATO: meglio nessun dato che quello
    della squadra sbagliata."""
    global _INDICE_NOMI
    if _INDICE_NOMI is None:
        idx: Dict[str, str] = {}
        ambigui = set()
        for tid, blocco in (atlante().get("by_team") or {}).items():
            if not isinstance(blocco, dict):
                continue
            chiave = _normalizza(blocco.get("team_name"))
            if not chiave:
                continue
            if chiave in idx and idx[chiave] != str(tid):
                ambigui.add(chiave)
                continue
            idx[chiave] = str(tid)
        for chiave in ambigui:
            idx.pop(chiave, None)
        _INDICE_NOMI = idx
    return _INDICE_NOMI


def team_id(nome: Any) -> Optional[str]:
    """id della squadra nell'atlante, per nome. None = non abbinata."""
    chiave = _normalizza(nome)
    return _indice_nomi().get(chiave) if chiave else None


def gol_subiti_per_partita(tid: Optional[str]) -> Optional[float]:
    """Media dei gol SUBITI per partita (somma dei 18 bucket da 5')."""
    if tid is None:
        return None
    blocco = (atlante().get("by_team") or {}).get(str(tid))
    if not isinstance(blocco, dict):
        return None
    bucket = blocco.get("def_goals_per_match_by_bucket")
    if not isinstance(bucket, dict) or not bucket:
        return None
    tot = 0.0
    visti = 0
    for v in bucket.values():
        if isinstance(v, (int, float)):
            tot += float(v)
            visti += 1
    return round(tot, 4) if visti else None


def scontri_diretti(id_a: Optional[str], id_b: Optional[str]) -> Optional[Dict[str, int]]:
    """{'incontri': n, 'pareggi_alti': k} dagli scontri diretti dell'atlante.

    None = la coppia non e' nell'atlante (meno di 3 incontri registrati): il
    dato non c'e', e non si inventa."""
    if id_a is None or id_b is None:
        return None
    try:
        a, b = int(id_a), int(id_b)
    except (TypeError, ValueError):
        return None
    blocco = (atlante().get("h2h_hint") or {}).get(f"{min(a, b)}-{max(a, b)}")
    if not isinstance(blocco, dict):
        return None
    punteggi = blocco.get("ft_scores_a_b")
    if not isinstance(punteggi, dict) or not punteggi:
        return None
    incontri = sum(int(v) for v in punteggi.values() if isinstance(v, (int, float)))
    if incontri <= 0:
        return None
    alti = sum(int(punteggi.get(s, 0) or 0) for s in PAREGGI_ALTI)
    return {"incontri": int(incontri), "pareggi_alti": int(alti)}


def hint(home: Any, away: Any) -> Optional[Dict[str, Any]]:
    """Il blocco `selection_hint` della riga di scan, o None se non c'e' NULLA.

    Forma (chiavi stabili, lette dai due motori):

        {"fonte": "hazard_atlas_v2",
         "h2h_meetings": 14, "h2h_big_draws": 1,        # None se coppia assente
         "conceded": {"home": 1.21, "away": None}}      # gol subiti per partita

    Un campo a None vuol dire DATO ASSENTE: il motore lo dichiara e non lo
    scambia mai per uno zero."""
    chiave = (_normalizza(home), _normalizza(away))
    if not chiave[0] and not chiave[1]:
        return None
    if chiave in _HINT_CACHE:
        return _HINT_CACHE[chiave]
    id_h, id_a = team_id(home), team_id(away)
    h2h = scontri_diretti(id_h, id_a)
    dif_h, dif_a = gol_subiti_per_partita(id_h), gol_subiti_per_partita(id_a)
    out: Optional[Dict[str, Any]]
    if h2h is None and dif_h is None and dif_a is None:
        out = None
    else:
        out = {
            "fonte": FONTE,
            "h2h_meetings": None if h2h is None else h2h["incontri"],
            "h2h_big_draws": None if h2h is None else h2h["pareggi_alti"],
            "conceded": {"home": dif_h, "away": dif_a},
        }
    if len(_HINT_CACHE) > _CACHE_MAX:
        _HINT_CACHE.clear()
    _HINT_CACHE[chiave] = out
    return out
