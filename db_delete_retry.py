# db_delete_retry.py - ritentativi per le DELETE che precedono un insert (25/09/2026)
#
# Le tabelle aggregate (standings, injuries, top_scorers, top_assists, top_cards)
# si scrivono con delete(lega, stagione) + insert. Se la delete fallisce e si
# inserisce comunque, la tabella finisce con righe doppie (le vecchie MAI
# cancellate + le nuove). Qui la delete si RITENTA a passo crescente; se
# fallisce anche l'ultimo tentativo si propaga l'errore al chiamante, che non
# deve fare l'insert a valle (niente buchi, niente doppioni - ordine utente).
from __future__ import annotations

import logging
import time
from typing import Callable, Optional, Tuple

logger = logging.getLogger(__name__)

TENTATIVI_DEFAULT = 3
ATTESE_DEFAULT: Tuple[float, ...] = (2, 5, 10)  # secondi, crescente, tra un tentativo e il successivo


def delete_con_ritentativi(
    azione: Callable[[], None],
    *,
    etichetta: str,
    tentativi: int = TENTATIVI_DEFAULT,
    attese: Tuple[float, ...] = ATTESE_DEFAULT,
    dormi: Optional[Callable[[float], None]] = None,
) -> None:
    """
    Esegue `azione` (una DELETE) fino a `tentativi` volte. Tra un tentativo
    fallito e il successivo attende attese[i] secondi (i test iniettano
    `dormi`, oppure patchano db_delete_retry.time.sleep, per non dormire
    davvero: `dormi` e' risolto QUI dentro, a ogni chiamata, non come default
    di parametro, altrimenti un monkeypatch di time.sleep fatto dopo l'import
    di questo modulo non avrebbe alcun effetto). Se fallisce anche l'ultimo
    tentativo, rilancia l'eccezione originale: il chiamante NON deve inserire
    nulla.
    """
    dormi = dormi or time.sleep
    ultimo_errore: Optional[BaseException] = None
    for i in range(tentativi):
        try:
            azione()
            return
        except Exception as e:
            ultimo_errore = e
            logger.error("%s: tentativo %s/%s fallito: %s", etichetta, i + 1, tentativi, e)
            if i < tentativi - 1:
                attesa = attese[i] if i < len(attese) else attese[-1]
                dormi(attesa)

    assert ultimo_errore is not None
    raise ultimo_errore
