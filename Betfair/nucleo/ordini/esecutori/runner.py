"""esecutori/runner.py - ``Esecutore`` sopra il dispatch di OGGI del runner (W1-C1, 09/10/2026).

Scopo
-----
Un wrapper SOTTILE sul percorso che oggi esegue un comando del canale dentro il runner,
``motore_ordini.MotoreOrdini._esegui``: stessa riga (il piano di ``valida_comando``), stesso
contesto sul thread (``MotoreOrdini._imposta_contesto``/``_pulisci_contesto``), stesso hook
del diario prima di ogni ``place_order`` (``MotoreOrdini._pre_invio``, con ``ref_interno``
e la misura della "Salute"), stesso ``sb`` differito (``_LocalSb(_SbDifferito())``), stesso
lucchetto (``LUCCHETTO_ORDINI``), stesso ``_dispatch``. Le funzioni del motore si CHIAMANO
(con un ``self`` minimo che porta solo ``diario``, ``_ora_ms`` e ``_modo_processo_forzato``):
nessuna riga e' copiata. Lo STESSO esecutore serve il live (client reale di flumine) e il
paper (client simulato): il client lo sceglie ``_dispatch`` dal modo della RIGA.

Entrate: ``RichiestaOrdine`` (place/cancel/replace) e i ``params`` del bot (``max_stake``,
``fok_ttl_sec``, ``risk_rule_id``...: arrivano nella riga come oggi dal comando,
``accetta_params = True``); il framework flumine, le strategie per modo, il diario.
Uscite: ``EventoOrdine`` (seq 0: lo assegna la porta).

Traduzione dell'esito (``FASE_DA_MOTORE``): la riga dello specchio
(``motore_ordini.riga_specchio_da_esito``) e ``motore_ordini.fase_da_riga``. Un
``ValueError`` del dispatch e' un rifiuto PRIMA dell'invio (``_place_or_raise`` solleva
``ValueError`` solo se ``place_order`` torna False o il mercato non e' operabile) ->
``rifiutato`` col codice di ``motore_ordini.codice_errore``; un errore DENTRO o DOPO
``place_order`` e' ``RuntimeError("post_place:...")`` e SALE: per la porta e' IGNOTO.
Un dispatch che non lascia l'esito (``_write_done`` mai chiamato) SALE anch'esso.

Differenze dichiarate dal motore: nessun place-and-trim (``submin_disponibile = False``),
nessun equivalente, nessuna sorveglianza ``INVALID_BET_SIZE``/riprezzi (restano al motore);
le scritture DB differite NON sono rigiocate (restano in ``ultimo_differito``: l'ondata 2
le passa allo scrittore asincrono come fa ``MotoreOrdini._esegui``); la riga e' rifatta da
``valida_comando`` (deterministica: la porta ha gia' validato lo stesso comando).
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Callable, Dict, Mapping, Optional

from Betfair.nucleo.ordini.adattatore_comando import ExtraComando, comando_da_richiesta
from Betfair.nucleo.ordini.contratto import EventoOrdine, FaseOrdine, RichiestaOrdine

logger = logging.getLogger(__name__)

#: fase del motore (``motore_ordini.FASI``) -> fase del contratto. ``inviato`` (ordine
#: partito, Betfair non ha ancora dato il bet_id) e ``accettato_betfair`` diventano
#: entrambe ``accettato``: le distingue ``bet_id`` (None = in volo).
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


def _f(v: Any) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


class EsecutoreRunner:
    """``Esecutore`` sopra ``live_order_worker._dispatch`` (o l'esecutore dello sport che
    il motore riceve: per il tennis ``esecutore_tennis``)."""

    submin_disponibile = False
    accetta_params = True

    def __init__(self, flumine: Any, strategie: Any, *, low: Any = None,
                 diario: Any = None, orologio_ms: Optional[Callable[[], int]] = None,
                 modo_processo: Optional[str] = None) -> None:
        from Betfair.stream import motore_ordini as M

        if low is None:
            from Betfair.stream import live_order_worker as low
        self._low = low
        self._flumine = flumine
        self._strategie = strategie
        # il ``self`` minimo dei metodi del motore che si riusano (nessuna copia)
        self._come_motore = SimpleNamespace(diario=diario,
                                            _ora_ms=orologio_ms or M._ora_ms,
                                            _modo_processo_forzato=modo_processo)
        self.ultimo_differito: Any = None

    # ----------------------------------------------------------------- contratto
    def place(self, r: RichiestaOrdine, params: Optional[Mapping[str, Any]] = None) -> EventoOrdine:
        return self._esegui(r, params)

    def cancel(self, r: RichiestaOrdine, params: Optional[Mapping[str, Any]] = None) -> EventoOrdine:
        return self._esegui(r, params)

    def replace(self, r: RichiestaOrdine, params: Optional[Mapping[str, Any]] = None) -> EventoOrdine:
        return self._esegui(r, params)

    # ------------------------------------------------------------------ interno
    def _riga(self, r: RichiestaOrdine, params: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        """La riga che il motore passa a ``_dispatch``: il piano di ``valida_comando``,
        params del bot compresi."""
        from Betfair.stream import motore_ordini as M

        piano = M.valida_comando(r.attore, comando_da_richiesta(
            r, ExtraComando(params=dict(params)) if params else None))
        riga = piano["riga"]
        riga["id"] = next(self._low._LOCAL_RID)
        riga["action"] = piano["azione"]
        riga["mode"] = piano["mode"]
        return riga

    def _esegui(self, r: RichiestaOrdine, params: Optional[Mapping[str, Any]]) -> EventoOrdine:
        from Betfair.stream import motore_ordini as M

        low = self._low
        riga = self._riga(r, params)
        differito = low._SbDifferito()
        lsb = low._LocalSb(differito)
        hook = (M.MotoreOrdini._pre_invio(self._come_motore, r.ref)
                if self._come_motore.diario is not None else None)
        M.MotoreOrdini._imposta_contesto(self._come_motore, r.attore, hook)
        errore: Optional[str] = None
        try:
            with low.LUCCHETTO_ORDINI:
                low._dispatch(lsb, self._flumine, riga, r.modo, self._strategie)
        except ValueError as ex:
            errore = str(ex)          # rifiuto PRIMA dell'invio (vedi docstring)
        finally:
            M.MotoreOrdini._pulisci_contesto()
        self.ultimo_differito = differito
        if errore is not None:
            return EventoOrdine(ref=r.ref, seq=0, fase="rifiutato", bet_id=None,
                                abbinato=0.0, residuo=0.0, prezzo_medio=None,
                                codice_errore=M.codice_errore(errore), esito_ms=None)
        result = lsb.captured.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"dispatch di {r.ref} senza esito: stato dell'ordine ignoto")
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
