"""esecutori/runner.py - ``Esecutore`` sopra il dispatch di OGGI del runner (W1-C1, 09/10/2026).

Scopo
-----
Un wrapper SOTTILE sul percorso che oggi esegue un comando del canale dentro il runner:
``motore_ordini.MotoreOrdini._esegui`` -> ``live_order_worker._dispatch`` (con il ``sb``
differito ``_LocalSb(_SbDifferito())``, il lucchetto ``LUCCHETTO_ORDINI`` e il contesto
sul thread ``_CONTESTO``). Lo STESSO esecutore serve il live (client reale di flumine,
``BetfairExecution``) e il paper (client simulato, ``SimulatedExecution``): il client lo
sceglie ``_dispatch`` dal modo della RIGA (``_client_for_mode``), come oggi. Nessuna riga
del codice di oggi e' copiata o cambiata: si chiamano le sue funzioni.

Entrate: ``RichiestaOrdine`` (place/cancel/replace), il framework flumine e le strategie
per modo (``{"live": ..., "paper": ...}``), un diario opzionale per la riga ``ordine``
(il ``customer_order_ref`` VERO di flumine, scritto SUBITO PRIMA di ``place_order``,
come ``MotoreOrdini._pre_invio``). Uscite: ``EventoOrdine`` (seq 0: lo assegna la porta).

Traduzione dell'esito (fasi del motore -> ``FaseOrdine`` del contratto, la stessa per ogni
esecutore, ``FASE_DA_MOTORE``): l'esito del dispatch diventa la riga dello specchio
(``motore_ordini.riga_specchio_da_esito``) e la fase e' ``motore_ordini.fase_da_riga``.
Un errore del dispatch PRIMA dell'invio (``ValueError`` senza ``post_place:``) e' un
``rifiutato`` con il codice di ``motore_ordini.codice_errore``; un errore DOPO l'invio
(``post_place:``) o qualunque altra eccezione SALE: per la porta e' un esito IGNOTO.

Cosa NON fa: il place-and-trim (``submin_disponibile = False``: la macchina a stati vive
nel motore, ``avanza_submin``), l'equivalente sull'altra selezione, la sorveglianza
``INVALID_BET_SIZE`` e dei riprezzi, lo specchio nel DB (le scritture differite restano in
``ultimo_differito`` per chi le vuole rigiocare: l'ondata 2 le passa allo scrittore
asincrono). Non e' agganciato al runner (ondata 2).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Mapping, Optional

from Betfair.nucleo.ordini.adattatore_comando import comando_da_richiesta
from Betfair.nucleo.ordini.contratto import EventoOrdine, FaseOrdine, RichiestaOrdine

logger = logging.getLogger(__name__)

#: fase del motore (``motore_ordini.FASI``) -> fase del contratto. ``inviato`` (ordine
#: partito, Betfair non ha ancora dato il bet_id) e ``accettato_betfair`` diventano
#: entrambe ``accettato``: le distingue ``bet_id`` (None = in volo). ``errore`` NON e'
#: qui: lo decide ``_fase_errore`` (rifiutato prima dell'invio, ignoto dopo).
FASE_DA_MOTORE: Mapping[str, FaseOrdine] = {
    "inviato": "accettato",
    "accettato_betfair": "accettato",
    "parcheggiato": "parcheggiato",
    "ridotto": "ridotto",
    "abbinato_parziale": "parziale",
    "abbinato": "abbinato",
    "annullato": "annullato",
    "scaduto": "scaduto",
    "rifiutato": "rifiutato",
}
PREFISSO_POST_PLACE = "post_place"


def _f(v: Any) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


class EsecutoreRunner:
    """``Esecutore`` sopra ``live_order_worker._dispatch`` (o l'esecutore dello sport che
    il motore riceve: per il tennis ``esecutore_tennis``)."""

    submin_disponibile = False

    def __init__(self, flumine: Any, strategie: Any, *, low: Any = None,
                 diario: Any = None, orologio_ms: Optional[Callable[[], int]] = None) -> None:
        if low is None:
            from Betfair.stream import live_order_worker as low
        self._low = low
        self._flumine = flumine
        self._strategie = strategie
        self._diario = diario
        self._ora_ms = orologio_ms
        self.ultimo_differito: Any = None

    # ----------------------------------------------------------------- contratto
    def place(self, r: RichiestaOrdine) -> EventoOrdine:
        return self._esegui(r)

    def cancel(self, r: RichiestaOrdine) -> EventoOrdine:
        return self._esegui(r)

    def replace(self, r: RichiestaOrdine) -> EventoOrdine:
        return self._esegui(r)

    # ------------------------------------------------------------------ interno
    def _riga(self, r: RichiestaOrdine) -> Dict[str, Any]:
        """La riga che il motore passa a ``_dispatch``: il piano di ``valida_comando``."""
        from Betfair.stream import motore_ordini as M

        piano = M.valida_comando(r.attore, comando_da_richiesta(r))
        riga = piano["riga"]
        riga["id"] = next(self._low._LOCAL_RID)
        riga["action"] = piano["azione"]
        riga["mode"] = piano["mode"]
        return riga

    def _hook(self, ref: str) -> Callable[..., None]:
        """La riga ``ordine`` del diario SUBITO PRIMA di ogni place (forma di
        ``MotoreOrdini._pre_invio``): lega il ref al customerOrderRef VERO di flumine."""
        def _h(order: Any, market: Any, what: str, info: Optional[Dict[str, Any]]) -> None:
            if self._diario is None:
                return
            rec: Dict[str, Any] = {"tipo": "ordine", "ref": ref, "cosa": what,
                                   "ts_ms": self._ora_ms() if self._ora_ms else None}
            if order is not None:
                ot = getattr(order, "order_type", None)
                rec.update({"cor": getattr(order, "customer_order_ref", None),
                            "market_id": getattr(market, "market_id", None),
                            "selection_id": getattr(order, "selection_id", None),
                            "side": getattr(order, "side", None),
                            "price": getattr(ot, "price", None),
                            "size": getattr(ot, "size", None)})
            else:
                rec.update({"market_id": getattr(market, "market_id", None), **(info or {})})
            self._diario.scrivi(rec)   # se solleva, l'ordine NON parte (come oggi)
        return _h

    def _esegui(self, r: RichiestaOrdine) -> EventoOrdine:
        from Betfair.stream import motore_ordini as M

        low = self._low
        riga = self._riga(r)
        differito = low._SbDifferito()
        lsb = low._LocalSb(differito)
        low._CONTESTO.strategy_ref = r.attore
        low._CONTESTO.pre_invio = self._hook(r.ref)
        errore: Optional[str] = None
        try:
            with low.LUCCHETTO_ORDINI:
                low._dispatch(lsb, self._flumine, riga, r.modo, self._strategie)
        except ValueError as ex:
            testo = str(ex)
            if testo.startswith(PREFISSO_POST_PLACE):
                raise          # l'ordine e' partito: esito IGNOTO per la porta
            errore = testo
        finally:
            low._CONTESTO.strategy_ref = None
            low._CONTESTO.pre_invio = None
        self.ultimo_differito = differito
        if errore is not None:
            return EventoOrdine(ref=r.ref, seq=0, fase="rifiutato", bet_id=None,
                                abbinato=0.0, residuo=0.0, prezzo_medio=None,
                                codice_errore=M.codice_errore(errore), esito_ms=None)
        result = lsb.captured.get("result") or {}
        specchio = M.riga_specchio_da_esito(result, cust_ref=low._cust_ref(riga["id"]),
                                            rid=riga["id"], mode=r.modo, riga=riga)
        fase = FASE_DA_MOTORE.get(M.fase_da_riga(specchio), "accettato")
        if result.get("ok") is False:
            fase = "rifiutato"
        return EventoOrdine(
            ref=r.ref, seq=0, fase=fase, bet_id=specchio.get("bet_id"),
            abbinato=_f(specchio.get("size_matched")),
            residuo=_f(specchio.get("size_remaining")),
            prezzo_medio=(_f(specchio.get("average_price_matched")) or None),
            codice_errore=M.codice_errore(result.get("error")) if result.get("error") else None,
            esito_ms=None)
