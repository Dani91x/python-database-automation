"""Stub OPZIONALE dei dati di servizio per giocatore (degrada da solo).

La v1 del bot e' order-book puro (niente direzione), quindi questo modulo NON e'
richiesto per operare. E' un aggancio per una FASE 2: usare la probabilita' di
punto al servizio come *radar di regime* dell'anti-gap (distinguere il gap finto
dal gap vero), mai per scommettere una direzione.

Comportamento: cerca un CSV locale ``serve_data.csv`` accanto a questo file con
colonne ``name,serve_win_pct``. Se assente o il giocatore non c'e', ritorna
``None`` → il bot resta order-book puro. Per i challenger ITF di oggi ritornera'
``None`` (dati non disponibili), come atteso.
"""

from __future__ import annotations

import csv
import logging
import os
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_CSV = os.path.join(os.path.dirname(__file__), "serve_data.csv")
_cache: Optional[Dict[str, float]] = None


def _norm(name: str) -> str:
    return " ".join(str(name).strip().lower().split())


def _load() -> Dict[str, float]:
    global _cache
    if _cache is not None:
        return _cache
    data: Dict[str, float] = {}
    if os.path.exists(_CSV):
        try:
            with open(_CSV, newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    name = row.get("name")
                    pct = row.get("serve_win_pct")
                    if name and pct not in (None, ""):
                        try:
                            data[_norm(name)] = float(pct)
                        except ValueError:
                            continue
        except OSError as exc:  # noqa: BLE001
            logger.debug("[serve-data] lettura CSV fallita: %s", exc)
    _cache = data
    return data


def get_serve_prob(name: Optional[str]) -> Optional[float]:
    """Probabilita' di punto al servizio (0..1) per un giocatore, o None."""
    if not name:
        return None
    val = _load().get(_norm(name))
    if val is None:
        return None
    return val / 100.0 if val > 1.0 else val


def get_serve_probs(
    name_home: Optional[str], name_away: Optional[str]
) -> Tuple[Optional[float], Optional[float]]:
    """(serve_home, serve_away). None dove il dato non c'e' → order-book puro."""
    ph, pa = get_serve_prob(name_home), get_serve_prob(name_away)
    if ph is None and pa is None:
        logger.info("[serve-data] nessun dato per '%s' / '%s' → order-book puro",
                    name_home, name_away)
    return ph, pa
