"""arresto_ordinato.py - punto d'ingresso dello SPEGNIMENTO ORDINATO (28/09/2026).

Cantiere A (fine evento), R-28-3: l'app desktop chiude i processi figli con
``taskkill /T /F`` (``desktop/main.js`` ``killChildren``): nessun ``finally``
gira e le righe di follow restano STREAMING senza un processo che le segue.

Questo modulo e' il SEGNALE che ``main.js`` puo' dare PRIMA del taskkill: un
FILE. Scelto al posto di un segnale di sistema perche' su Windows un processo
Python lanciato senza console non riceve CTRL_C/CTRL_BREAK in modo affidabile e
il watchdog in mezzo lo inghiottirebbe; un file lo leggono tutti (runner calcio
e tennis, anche parcheggiati in attesa senza framework) con una stat ogni
secondo, senza porte e senza processi nuovi.

* ``main.js`` scrive ``<cartella>/ARRESTO`` (contenuto libero).
* I runner, entro ~1 s (worker ``arresto_worker`` e cima del ciclo di attesa),
  escono in modo ORDINATO con exit 0: il loro ``finally`` chiude i follow come
  dice la specifica (``AUDIT_2026-09-28/SPEC_SPEGNIMENTO_ORDINATO.md``) e il
  watchdog, su exit 0, NON li rilancia (``watchdog.classify_exit``: 'clean').
* Un file piu' vecchio dell'avvio del processo NON conta (resto di uno
  spegnimento precedente): ``main.js`` lo cancella comunque all'avvio.

Cartella: env ``APP_ARRESTO_DIR`` (vuota = default) oppure
``<LIVE_STREAM_DATA_DIR>/_arresto``. ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import os
import time
from typing import Optional

NOME_FILE = "ARRESTO"

#: epoch dell'import = avvio del processo (il runner importa il modulo all'avvio)
AVVIO_PROCESSO = time.time()


def cartella() -> str:
    raw = os.environ.get("APP_ARRESTO_DIR", "").strip()
    if raw:
        return raw
    from .config_stream import DATA_DIR

    return os.path.join(DATA_DIR, "_arresto")


def percorso() -> str:
    return os.path.join(cartella(), NOME_FILE)


def richiesto(dal: Optional[float] = None) -> bool:
    """True se il file d'arresto esiste ed e' stato scritto DOPO ``dal``
    (default: avvio di questo processo; 2 s di tolleranza sull'orologio del
    filesystem). Mai un'eccezione: nel dubbio False (si continua a lavorare)."""
    try:
        mt = os.path.getmtime(percorso())
    except OSError:
        return False
    rif = AVVIO_PROCESSO if dal is None else float(dal)
    return mt >= rif - 2.0


def richiedi() -> str:
    """Scrive il file d'arresto (lo usa ``main.js``, a mano o i test). Ritorna
    il percorso."""
    os.makedirs(cartella(), exist_ok=True)
    p = percorso()
    with open(p, "w", encoding="ascii") as fh:
        fh.write("arresto ordinato richiesto %.3f\n" % time.time())
    return p


def cancella() -> None:
    """Toglie il file (all'avvio dell'app). Mai un'eccezione."""
    try:
        os.remove(percorso())
    except OSError:
        pass
