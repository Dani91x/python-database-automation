# -*- coding: utf-8 -*-
"""FRENO CRESCENTE DOPO I RIFIUTI - modulo condiviso (decisione D2 del 24/09).

Nato il 17/09 nei quattro bot tennis (``tennis_scalper/condotta_ordini.py``),
spostato qui il 24/09 SENZA cambiarne il comportamento: ``condotta_ordini``
lo re-esporta con gli stessi default (``BACKOFF_S`` 5-10-20-40-60 s e tetto 20
per (mercato, selezione)), e il test di parita' tennis lo prova.

Perche' esiste. Misurato nel replay del 17/09, scenario ``rifiuti-betfair`` su
35794049: con Betfair che rifiuta ogni piazzamento il FLB ha ritentato 8.132
volte e lo scalper tennis 20.534 volte in UNA partita. In LIVE sono altrettante
chiamate rifiutate, cioe' il rate limit di Betfair. D2 (24/09): "dove non basta
[lo stato del mercato], freno crescente".

Il freno vale per i rifiuti RESIDUI: il mercato e' aperto (lo dice la guardia
``stato_mercato.mercato_operabile``) ma Betfair o un trading control dice no
(prezzo non valido, size, errore API). Non cambia soglie ne' prezzi: decide
solo QUANDO si puo' riprovare.

Parametri (tutti DICHIARATI dal chiamante, nessun default nascosto):
  * ``backoff_s``: attese in secondi DI TEMPO DI MERCATO, una per rifiuto
    consecutivo; oltre l'ultima resta l'ultima;
  * ``tetto``: rifiuti per (mercato, selezione) oltre i quali su quella
    selezione non si apre piu' (``None`` = nessun tetto);
  * ``azzera_al_successo``: False (tennis, 17/09) = un piazzamento accettato
    toglie l'attesa ma il conteggio resta (il tetto per partita misura quante
    volte il conto ha detto no); True (scalper calcio, 24/09) = il primo
    accettato azzera anche il conteggio, e il rifiuto dopo riparte dal primo
    passo.

Il tempo e' quello DEL MERCATO (``publish_time``), non quello del muro: e'
l'unico modo perche' replay, paper e live si comportino allo stesso modo.

ASCII-only nel codice; i commenti sono in italiano. Nessun IO.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

# i default del 17/09 (bot tennis): il primo passo copre il betDelay del tennis
# in gioco (5 s), cosi' un rifiuto non si ripresenta prima che l'esito
# precedente sia noto.
BACKOFF_S: Tuple[float, ...] = (5.0, 10.0, 20.0, 40.0, 60.0)
TETTO_RIFIUTI = 20

# lo scalper calcio (24/09, D2): 1, 2, 4, 8, 16 e poi fisso a 30 s, azzerato al
# primo accettato. Nessun tetto: il freno rallenta, non spegne la strategia.
BACKOFF_SCALPER_S: Tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 16.0, 30.0)


class FrenoRifiuti:
    """Quante volte Betfair ci ha detto di no, e quando si puo' riprovare."""

    def __init__(self, tetto: Optional[int] = TETTO_RIFIUTI,
                 backoff_s: Sequence[float] = BACKOFF_S,
                 azzera_al_successo: bool = False) -> None:
        self.tetto = None if tetto is None else int(tetto)
        self.backoff_s = tuple(float(x) for x in backoff_s)
        if not self.backoff_s:
            raise ValueError("backoff_s vuoto: il freno deve dichiarare le attese")
        self.azzera_al_successo = bool(azzera_al_successo)
        self._rifiuti: Dict[Tuple[str, int], int] = {}
        self._riprova_da: Dict[Tuple[str, int], float] = {}
        # per quale conteggio di rifiuti si e' gia' scritto il motivo in
        # attivita': senza questo, un bot che tenta a ogni book scriverebbe
        # DECINE DI MIGLIAIA di righe (misurato: 20.494 righe per 40 rifiuti
        # veri). Il motivo si dice UNA volta per rifiuto, non per tentativo.
        self._annunciato: Dict[Tuple[str, int], int] = {}

    def _k(self, market_id: Any, selection_id: Any) -> Tuple[str, int]:
        try:
            return (str(market_id), int(selection_id))
        except (TypeError, ValueError):
            return (str(market_id), 0)

    def attesa_per(self, n: int) -> float:
        """L'attesa dopo l'n-esimo rifiuto consecutivo (n >= 1)."""
        return self.backoff_s[min(max(int(n), 1), len(self.backoff_s)) - 1]

    def registra_rifiuto(self, market_id: Any, selection_id: Any,
                         adesso_s: float) -> Tuple[int, float]:
        """Un rifiuto in piu'. Torna (quanti, fra quanti secondi si riprova)."""
        k = self._k(market_id, selection_id)
        n = self._rifiuti.get(k, 0) + 1
        self._rifiuti[k] = n
        attesa = self.attesa_per(n)
        self._riprova_da[k] = float(adesso_s) + attesa
        return n, attesa

    def registra_successo(self, market_id: Any, selection_id: Any) -> None:
        """Un piazzamento riuscito toglie l'attesa (e, con ``azzera_al_successo``,
        anche il conteggio)."""
        k = self._k(market_id, selection_id)
        self._riprova_da.pop(k, None)
        if self.azzera_al_successo:
            self._rifiuti.pop(k, None)
            self._annunciato.pop(k, None)

    def bloccato(self, market_id: Any, selection_id: Any,
                 adesso_s: float) -> Optional[str]:
        """``None`` = si puo' provare. Altrimenti il MOTIVO, gia' scritto per la UI."""
        k = self._k(market_id, selection_id)
        n = self._rifiuti.get(k, 0)
        if self.tetto is not None and n >= self.tetto:
            return ("tetto rifiuti raggiunto su questa selezione (%d): non apro "
                    "piu' finche' la partita non finisce" % n)
        fino_a = self._riprova_da.get(k)
        if fino_a is not None and float(adesso_s) < fino_a:
            return ("freno dopo %d rifiuto/i di Betfair: riprovo fra %.0f s"
                    % (n, fino_a - float(adesso_s)))
        return None

    def da_annunciare(self, market_id: Any, selection_id: Any) -> bool:
        """True solo la PRIMA volta che si blocca per questo conteggio di
        rifiuti: il motivo va scritto in attivita' una volta, non a ogni book."""
        k = self._k(market_id, selection_id)
        n = self._rifiuti.get(k, 0)
        if self._annunciato.get(k) == n:
            return False
        self._annunciato[k] = n
        return True

    def quanti(self, market_id: Any, selection_id: Any) -> int:
        return self._rifiuti.get(self._k(market_id, selection_id), 0)
