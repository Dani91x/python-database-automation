"""porta_banco.py - F4: la porta ordini del BANCO passa dal MOTORE VERO del runner.

Strada unica (decisione dell'utente, 24/09): in produzione un bot manda i suoi
ordini al runner con il protocollo «comando ordine» (``/comando/<attore>``) e li
esegue ``motore_ordini.MotoreOrdini`` -> ``live_order_worker._dispatch`` sul
``Market`` di flumine. Nel replay la stessa cosa deve accadere: qui NON c'e' una
copia del motore ne' un piazzamento fatto in casa. ``PortaBanco`` costruisce il
``MotoreOrdini`` di produzione e gli consegna i comandi come farebbe il canale;
il motore esegue il ``_dispatch`` vero sul ``Market`` della ``FlumineSimulation``
del banco (client simulato = modalita' paper).

Contratto con il vivo (inchiodato da ``tests/test_porta_banco_f4_2026_09_24.py``):
  * ``invia(comando)`` ritorna l'ack del motore (stesse chiavi: ref, seq,
    accettato, motivo, ricevuto_ms), con le STESSE regole (dedup per ref, eta',
    parametri, place-and-trim sotto il minimo);
  * gli eventi ``order`` sono quelli del motore: la riga dello specchio
    ``betfair_live_orders`` (costruita da ``LiveTradingStrategy._order_row``,
    la funzione di produzione, piu' ``updated_at``) + ref/seq/fase/esito_ms;
  * ``aggiorna()`` va chiamato a ogni book del replay: legge il blotter (come fa
    lo stream ordini in produzione -> specchio) e fa avanzare il place-and-trim.

Differenze DICHIARATE dal vivo (nel banco non esistono):
  * niente DB: lo scrittore asincrono e' nullo (conta i lavori, non li esegue);
  * il modo di processo e' PAPER per costruzione (solo client simulato), il modo
    effettivo della Control Room e l'eta' dei settings non si applicano;
  * il diario si scrive in una cartella temporanea (o in quella indicata).
"""
from __future__ import annotations

import collections
import tempfile
import time
from types import SimpleNamespace
from typing import Any, Callable, Deque, Dict, List, Optional

from .. import motore_ordini as MO
from ..local_channel import ComandoCanale, LocalRequest


class _ScrittoreNullo:
    """Il banco non ha DB: i lavori si contano e si scartano (il diario resta)."""

    def __init__(self) -> None:
        self.lavori: List[str] = []

    def accoda(self, descrizione: str, _job: Any, tentativi: int = 1) -> bool:  # noqa: ARG002
        self.lavori.append(descrizione)
        return True

    def avvia(self) -> None:
        return None

    def ferma(self, timeout: float = 0.0) -> None:  # noqa: ARG002
        return None

    def svuota(self, timeout: float = 0.0) -> bool:  # noqa: ARG002
        return True


class _CanaleBanco:
    """Il canale in-process: raccoglie cio' che il motore manda all'attore."""

    def __init__(self) -> None:
        self.messaggi: List[Dict[str, Any]] = []
        self._comandi: Deque[ComandoCanale] = collections.deque()
        self._richieste: Deque[LocalRequest] = collections.deque()
        self.su_messaggio: Optional[Callable[[Dict[str, Any]], None]] = None

    # --- interfaccia usata dal motore (stessi nomi di LocalChannel) ---------
    def set_su_comando(self, _cb: Any) -> None:
        return None

    def pop_comandi(self, max_n: int = 50) -> List[ComandoCanale]:
        out = []
        while self._comandi and len(out) < max_n:
            out.append(self._comandi.popleft())
        return out

    def pop_requests(self, max_n: int = 20) -> List[LocalRequest]:
        out = []
        while self._richieste and len(out) < max_n:
            out.append(self._richieste.popleft())
        return out

    def invia(self, _ws: Any, payload: Dict[str, Any]) -> None:
        self._ricevi(payload)

    def invia_attore(self, _attore: str, payload: Dict[str, Any]) -> None:
        self._ricevi(payload)

    def respond(self, *_a: Any, **_k: Any) -> None:
        return None

    def _ricevi(self, payload: Dict[str, Any]) -> None:
        self.messaggi.append(payload)
        if self.su_messaggio is not None:
            self.su_messaggio(payload)


class PortaBanco:
    """Porta ordini del banco = motore ordini di produzione su FlumineSimulation."""

    def __init__(self, framework: Any, strategia: Any, *, attore: str,
                 sport: str = "calcio", cartella_diario: Optional[str] = None,
                 orologio_ms: Optional[Callable[[], int]] = None) -> None:
        self.attore = attore
        self.mode = "paper"
        self.canale = _CanaleBanco()
        self._orologio = orologio_ms or (lambda: int(time.time() * 1000))
        self._cartella = cartella_diario or tempfile.mkdtemp(prefix="diario_banco_")
        self.motore = MO.MotoreOrdini(
            sport, canale=self.canale, diario=MO.Diario(self._cartella),
            scrittore=_ScrittoreNullo(), orologio_ms=self._orologio,
            modo_processo="PAPER", blocco_modo=lambda *_a: None,
            eta_settings=lambda: 0.0)
        self.framework = framework
        self.strategia = strategia
        self.motore.aggancia(framework, {"paper": strategia})
        self._firme: Dict[str, tuple] = {}
        self._ack: Dict[str, Dict[str, Any]] = {}
        self._eventi: Dict[str, List[Dict[str, Any]]] = {}
        self.canale.su_messaggio = self._incassa

    # ------------------------------------------------------------ interfaccia
    def disponibile(self) -> bool:
        return self.motore.agganciato

    def invia(self, comando: Dict[str, Any]) -> Dict[str, Any]:
        """Consegna il comando al motore (come il canale) e torna l'ack."""
        ref = comando.get("ref")
        c = ComandoCanale(ws=self, attore=self.attore, token_ok=True, tipo="comando",
                          d=dict(comando), ricevuto_ms=int(self._orologio()))
        self.motore._gestisci(c)
        self.aggiorna()
        return dict(self._ack.get(str(ref), {}))

    def esiti(self, ref: str) -> List[Dict[str, Any]]:
        return list(self._eventi.get(str(ref), []))

    def aggiorna(self) -> None:
        """A ogni book: specchio dal blotter (come lo stream ordini) e un passo
        del place-and-trim."""
        self._specchio()
        self.motore.avanza_submin()
        self._specchio()

    # ----------------------------------------------------------------- interno
    def _incassa(self, msg: Dict[str, Any]) -> None:
        d = msg.get("d") or {}
        if msg.get("t") == "ack" and d.get("ref"):
            self._ack[str(d["ref"])] = dict(d)
        elif msg.get("t") == "order" and d.get("ref"):
            self._eventi.setdefault(str(d["ref"]), []).append(dict(d))

    def _specchio(self) -> None:
        from ..engine.live_trading_strategy import LiveTradingStrategy

        finto_self = SimpleNamespace(mode=self.mode)
        for market in list(getattr(self.framework, "markets", []) or []):
            blotter = getattr(market, "blotter", None)
            if blotter is None:
                continue
            try:
                ordini = list(blotter.strategy_orders(self.strategia))
            except Exception:  # noqa: BLE001 - blotter inatteso: niente specchio
                continue
            for o in ordini:
                riga = LiveTradingStrategy._order_row(
                    finto_self, o, event_id=getattr(market, "event_id", None),
                    market_id=getattr(market, "market_id", None))
                if riga is None:
                    continue
                firma = LiveTradingStrategy._order_signature(finto_self, o)
                chiave = str(getattr(o, "id", id(o)))
                if self._firme.get(chiave) == firma:
                    continue
                self._firme[chiave] = firma
                riga["updated_at"] = MO._ora_iso()
                self.motore._su_riga_specchio(riga)
