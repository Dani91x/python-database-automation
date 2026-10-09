"""Tipi comuni a tutti i comparti (04_ARCHITETTURA_OBIETTIVO.md par. 3.1).

Il piano li colloca in ``Betfair/runtime/contratto.py`` (re-esportati dal
nucleo): finche' ``runtime/`` non esiste (tappa T12) vivono qui; quando nascera'
``runtime/`` li re-esportera' da qui, senza copiarli.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Sport = Literal["calcio", "tennis"]
# MAI sommati: chiave di ogni aggregato (PROCESSO_STANDARD_BOT.md par. 7 n.21)
Modo = Literal["paper", "live"]
# di serie e dopo ogni riavvio MANUALE (cond. 4-bis; scheda D par. 4.2)
UsciteModo = Literal["MANUALE", "AUTOMATICO"]


@dataclass(frozen=True)
class Orologio:
    """Un solo orologio (scheda D par. 4.2): nel banco e' il tempo di mercato."""

    mono_ms: int                      # monotono locale
    publish_ms: Optional[int]         # pt Betfair del book che ha svegliato il giro
    rx_ms: Optional[int]              # ricezione locale
