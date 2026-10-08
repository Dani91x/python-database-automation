# -*- coding: utf-8 -*-
"""ordini_esterni_banco - gli scenari del banco con un ORDINE ESTERNO (W3b, 08/10/2026).

Ordine dell'utente (08/10): "quando intervengo io dal sito o dall'app su
un'operazione dei bot, i bot lo sanno e non fanno altro", "nel minor tempo
possibile". Per i bot che sono strategie flumine (oggi: lo scalper calcio) la
fonte LIVE e' lo stream ordini del conto (``tennis_scalper.ordini_esterni``).

LA CATENA DEL BANCO (nessun finto al posto del vero, salvo il DB in memoria):
  * l'ordine esterno e' VERO su flumine (stesso ``market.place_order``, stesso
    matching): BACK 2,00 a 1,01 (taker: abbina subito al miglior prezzo);
  * dal primo book la sessione riceve, a ogni cambio degli ordini di un suo
    mercato, la fotografia del conto come la porterebbe lo stream ordini: cache
    VERA di betfairlightweight (``OrderBookCache``) dagli ordini del mercato
    (``banco_comune.MercatoFlumine.ordini_conto_come_stream``), produttore VERO
    (``esiti_ordini_canale.pubblica_conto_da_evento``), JSON come il canale,
    ``Registro.ricevi_conto`` della sessione (in produzione la chiama
    l'osservatore montato sul flumine della sessione);
  * SECONDO GIRO (08/10, coordinatore): la verifica "del bot / fuori bot" e' la
    regola VERA di W2 (``live_order_worker._proprietari_bot``) sul DB in memoria
    del replay (tabelle dei bot, specchio, coda del runner con filtri veri); il suo
    esito diventa visibile alla sessione solo dopo la latenza delle letture
    (``ConfermaBanco``: n select x ``banco_comune.LATENZA_LETTURA_S``, l'assunzione
    del banco comune) sul tempo di mercato. Deterministico, nessun thread.

Gli scenari (tutti LIVE, come ``base``) e i controlli:
  * ``ordine-esterno`` (dal SITO: nessun riferimento) e ``ordine-esterno-app``
    (terminale manuale dell'app: ``customerStrategyRef='live'``, nessuna riga di
    bot nel DB): sospensione al messaggio, poi verifica "fuori bot" -> stop.
      OE1 gli ordini della SESSIONE, pubblicati per tutta la partita, non sono mai
          presi per ordini dell'utente;
      OE2 l'intervento scatta al primo book dopo che la verifica e' pronta;
          latenza messaggio -> decisione definitiva misurata;
      OE3 dopo la decisione nessun ordine NUOVO della sessione;
      OE4 al primo book dopo la decisione ogni vivo e' gia' in annullo; a fine
          sessione nessun vivo, riga 'stopped' col marcatore, attivita' scritta.
  * ``ordine-esterno-di-un-bot``: lo stesso ordine con ``customerStrategyRef='live'``
    ma la riga della coda del runner dice Omega (``client_ref='omega-t9'``,
    ``params.source='omega'``): e' di un altro bot.
      OE6 nessuno stop; sospensione SOLO finche' la verifica non e' pronta (nessun
          ordine nuovo della sessione accettato su quella selezione nel frattempo),
          poi rilasciata; la sessione finisce come sempre.
  * ``ordine-esterno-db-giu``: ordine dal sito, DB illeggibile (ogni lettura delle
    tabelle della verifica fallisce).
      OE7 nessuno stop e nessun ordine nuovo accettato su quella selezione fino a
          fine sessione (sospesa); attivita' 'ordine_esterno_non_verificabile'.
  * ``ordine-esterno-altro-mercato``: ordine dal sito su un mercato fuori dalla
    sessione.
      OE5 nessun intervento, nessuna sospensione: la sessione lavora come in base.

LIMITI DICHIARATI (stampati nel referto):
  * il quadro del banco e' CONDIVISO: l'ordine dell'utente sta nel blotter del
    quadro, quindi lo specchio e la dichiarazione di fine sessione del servizio
    (che in produzione vedono solo la sessione) lo possono contare;
  * la latenza della lettura DB e' l'ASSUNZIONE del banco comune (120 ms per
    chiamata), non una misura;
  * PROVA (paper): la sessione scalper e' un processo separato dal runner calcio,
    la sua fonte in prova non e' collegata (referto W3b): nessuno scenario paper.

File ASCII-only, commenti in italiano.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

SCENARIO = "ordine-esterno"
SCENARIO_APP = "ordine-esterno-app"
SCENARIO_BOT = "ordine-esterno-di-un-bot"
SCENARIO_DB_GIU = "ordine-esterno-db-giu"
SCENARIO_ALTRO = "ordine-esterno-altro-mercato"
SCENARI: Tuple[str, ...] = (SCENARIO, SCENARIO_APP, SCENARIO_BOT, SCENARIO_DB_GIU,
                            SCENARIO_ALTRO)
#: gli scenari in cui la sessione DEVE fermarsi
SCENARI_STOP = (SCENARIO, SCENARIO_APP)

DESCRIZIONI: Dict[str, str] = {
    SCENARIO: ("a meta' della finestra pre-match (o appena la sessione ha un ordine vivo) "
               "l'UTENTE piazza dal SITO (nessun riferimento) un BACK 2,00 a 1,01 sulla "
               "selezione della sessione; stream ordini e verifica sul DB veri: sospensione "
               "al messaggio, poi stop, annullo dei vivi, nessuna copertura (OE1-OE4)"),
    SCENARIO_APP: ("come `ordine-esterno`, ma dal terminale manuale dell'app "
                   "(customerStrategyRef 'live', nessuna riga di un bot nel DB): stop (OE1-OE4)"),
    SCENARIO_BOT: ("lo stesso ordine con customerStrategyRef 'live' ma la riga della coda "
                   "del runner e' di OMEGA (client_ref 'omega-t9'): nessuno stop, sospensione "
                   "solo per la verifica (OE1, OE6)"),
    SCENARIO_DB_GIU: ("ordine dal sito con il DB illeggibile: la sessione resta SOSPESA su "
                      "quella selezione (nessun ordine nuovo al buio) e lo scrive (OE1, OE7)"),
    SCENARIO_ALTRO: ("ordine dal sito su un mercato della registrazione dove la sessione "
                     "NON opera: nulla cambia (OE1, OE5)"),
}

#: l'ordine dell'utente: il minimo .it del BACK, a 1,01 (abbina subito al
#: miglior prezzo disponibile, come un taker)
SIZE_UTENTE = 2.0
PREZZO_UTENTE = 1.01
REF_UTENTE = "utente-esterno"
#: la riga della coda del runner calcio di un ordine di Omega (chiavi della tabella
#: ``betfair_live_order_requests`` lette da ``live_order_worker._proprietari_bot``)
CLIENT_REF_BOT = "omega-t9"
#: le tabelle che la verifica legge (``_proprietari_bot``)
TABELLE_VERIFICA = ("omega_trades", "safe_strategy_trades", "mike_trades",
                    "betfair_live_orders", "betfair_live_order_requests")

REGOLE: Dict[str, str] = {
    "OE1": ("gli ordini della sessione, che lo stream ordini porta per tutta la partita, "
            "non sono MAI presi per ordini dell'utente"),
    "OE2": ("un ordine dell'utente abbinato sul mercato della sessione ferma la sessione "
            "al primo book dopo che la verifica sul DB e' pronta"),
    "OE3": ("dopo l'intervento dell'utente nessun ordine NUOVO della sessione (nessuna "
            "copertura, nessun rientro, nessun ingresso)"),
    "OE4": ("dopo l'intervento: al primo book ogni ordine vivo della sessione e' gia' "
            "in annullo; a sessione chiusa nessun ordine vivo, riga 'stopped' col "
            "marcatore e attivita' 'intervento_utente'"),
    "OE5": ("un ordine dell'utente su un mercato dove la sessione NON opera non cambia "
            "niente (nessun intervento, nessuna sospensione, sessione fino a fine vita)"),
    "OE6": ("un ordine di un ALTRO BOT dalla coda del runner (stesso ref del terminale "
            "manuale) non ferma la sessione: sospensione solo finche' la verifica non e' "
            "pronta, nessun ordine nuovo accettato nel frattempo su quella selezione"),
    "OE7": ("DB illeggibile: la sessione resta sospesa su quella selezione (nessun "
            "ordine nuovo accettato al buio), non si ferma e lo scrive nell'attivita'"),
}

_CODICI: Dict[str, Tuple[str, ...]] = {
    SCENARIO: ("OE1", "OE2", "OE3", "OE4"), SCENARIO_APP: ("OE1", "OE2", "OE3", "OE4"),
    SCENARIO_BOT: ("OE1", "OE6"), SCENARIO_DB_GIU: ("OE1", "OE7"),
    SCENARIO_ALTRO: ("OE1", "OE5"),
}


def elenco_controlli(scenario: str) -> List[Tuple[str, str]]:
    return [(c, REGOLE[c]) for c in _CODICI.get(scenario, ())]


def strategia_utente() -> Any:
    """La strategia sotto cui stanno gli ordini esterni nel quadro (flumine vuole
    una strategia per ogni ordine): non legge nessun book, nessun tetto."""
    from flumine import BaseStrategy

    class _UtenteBanco(BaseStrategy):
        def check_market_book(self, market: Any, market_book: Any) -> bool:  # noqa: ARG002
            return False

        def process_market_book(self, market: Any, market_book: Any) -> None:  # noqa: ARG002
            return None

    return _UtenteBanco(market_filter=None, name="utente-banco",
                        max_order_exposure=None, max_selection_exposure=None,
                        max_trade_count=int(1e9), max_live_trade_count=int(1e9))


def _vivo(o: Any) -> bool:
    st = getattr(o, "status", None)
    return str(getattr(st, "name", st) or "").upper() in (
        "PENDING", "EXECUTABLE", "UPDATING", "CANCELLING", "REPLACING")


# ---------------------------------------------------------------------------
# la verifica "del bot / fuori bot" del banco
# ---------------------------------------------------------------------------
class ConfermaBanco:
    """Stessa interfaccia di ``ordini_esterni.ConfermaBot`` (``chiedi``, ``esito``,
    ``errore``): legge SUBITO il DB del replay con la regola VERA di W2
    (``live_order_worker._proprietari_bot``) ma l'esito diventa visibile solo dopo
    ``n select x LATENZA_LETTURA_S`` di tempo di mercato. Una lettura per bet_id
    nuovo, cache; dopo un errore si rilegge non prima di ``RIPROVA_DB_S``."""

    def __init__(self, db: Any, adesso_ms: Callable[[], int]) -> None:
        from . import banco_comune as BC
        from ..tennis_scalper import ordini_esterni as OE

        self.db = db
        self._adesso_ms = adesso_ms
        self._ms_lettura = int(round(float(BC.LATENZA_LETTURA_S) * 1000.0))
        self._riprova_ms = int(OE.RIPROVA_DB_S * 1000)
        self._fuori = OE.FUORI_BOT
        # bet_id -> (esito o None, errore o None, pronto_ms)
        self._righe: Dict[str, Tuple[Optional[str], Optional[str], int]] = {}
        self.letture = 0
        self.richieste: List[Dict[str, Any]] = []

    def _letture_db(self) -> int:
        return int(sum((getattr(self.db, "letture", {}) or {}).values()))

    def chiedi(self, bet_ids: Any) -> int:
        from .. import live_order_worker as LOW

        ora = int(self._adesso_ms())
        nuovi = []
        for b in bet_ids:
            b = str(b or "").strip()
            r = self._righe.get(b)
            if not b or (r is not None and (r[0] is not None or ora < r[2] + self._riprova_ms
                                            or ora < r[2])):
                continue
            nuovi.append(b)
        if not nuovi:
            return 0
        n0 = self._letture_db()
        errore = None
        dei_bot: Dict[str, str] = {}
        try:
            dei_bot = dict(LOW._proprietari_bot(self.db.sb, nuovi) or {})
        except Exception as ex:  # noqa: BLE001 - DB illeggibile: nessun esito
            errore = str(ex)[:200] or type(ex).__name__
        n = max(1, self._letture_db() - n0)
        self.letture += n
        pronto = ora + n * self._ms_lettura
        for b in nuovi:
            esito = None if errore else (("bot:%s" % dei_bot[b]) if b in dei_bot
                                         else self._fuori)
            self._righe[b] = (esito, errore, pronto)
        self.richieste.append({"bet_ids": nuovi, "chiesto_ms": ora, "pronto_ms": pronto,
                               "select": n, "errore": errore})
        return len(nuovi)

    def esito(self, bet_id: str) -> Optional[str]:
        r = self._righe.get(str(bet_id))
        if r is None or int(self._adesso_ms()) < r[2]:
            return None
        return r[0]

    def errore(self, bet_id: str) -> Optional[str]:
        r = self._righe.get(str(bet_id))
        if r is None or int(self._adesso_ms()) < r[2]:
            return None
        return r[1]

    def pronto_ms(self, bet_id: str) -> Optional[int]:
        r = self._righe.get(str(bet_id))
        return r[2] if r is not None else None


# ---------------------------------------------------------------------------
# l'iniettore
# ---------------------------------------------------------------------------
class Iniettore:
    """L'ordine esterno e lo stream ordini del conto, nel thread del motore (a
    tempo di mercato), dopo ogni book. Non decide niente per la sessione."""

    def __init__(self, scenario: str, *, quadro: Any, utente: Any, db: Any,
                 strategie: Callable[[], List[Any]],
                 mercati_sessione: Callable[[], Sequence[str]],
                 mercati_raw: Sequence[str], da_ms: Callable[[], Optional[int]],
                 entro_ms: Callable[[], Optional[int]]) -> None:
        if scenario not in SCENARI:
            raise ValueError("scenario %r non e' un ordine esterno" % scenario)
        self.scenario = scenario
        self.quadro = quadro
        self.utente = utente
        self.db = db
        self._strategie = strategie
        self._mercati_sessione = mercati_sessione
        self.mercati_raw = [str(m) for m in mercati_raw]
        self._da_ms = da_ms
        self._entro_ms = entro_ms
        self.ordine_utente: Any = None
        self.piazzato_ms: Optional[int] = None
        self.mercato_utente: Optional[str] = None
        self.selezione_utente: Optional[int] = None
        self.abbinato_ms: Optional[int] = None
        self.pubblicazioni = 0
        self.pubblicazioni_prima = 0
        self._firme: Dict[str, Tuple[Any, ...]] = {}
        self.intervento_ms: Optional[int] = None
        self.ricevuto_ms: Optional[int] = None
        self.primo_book_dopo_ms: Optional[int] = None
        self.ids_alla_decisione: Optional[set] = None
        self.nuovi_dopo: List[str] = []
        self.giri_dopo = 0
        # la sospensione (in verifica): da quando, fino a quando, gli ordini della
        # sessione su quella selezione gia' esistenti, quelli nuovi accettati
        self.sospeso_ms: Optional[int] = None
        self.ripreso_ms: Optional[int] = None
        self.messaggio_ms: Optional[int] = None
        self._ids_alla_sospensione: Optional[set] = None
        self.accettati_sospesi: List[str] = []
        self.giri_sospesi = 0
        self.sorveglianza_vista: Any = None
        self._avvisato = False
        self.note: List[str] = []
        self.violazioni: List[Tuple[str, str, str, str]] = []
        self.sollecitati: Dict[str, int] = {}

    # ------------------------------------------------------------- utilita'
    def _sorveglianza(self) -> Any:
        for s in self._strategie():
            sv = getattr(s, "_ordini_esterni", None)
            if sv is not None:
                self.sorveglianza_vista = sv
                return sv
        return self.sorveglianza_vista

    def _ordini_sessione(self, mid: str) -> List[Any]:
        m = self.quadro.markets.markets.get(str(mid))
        if m is None:
            return []
        out: List[Any] = []
        for s in self._strategie():
            try:
                out.extend(list(m.blotter.strategy_orders(s) or []))
            except Exception:  # noqa: BLE001 - blotter illeggibile: nessun ordine
                continue
        return out

    def _tutti_ordini_sessione(self) -> List[Any]:
        out: List[Any] = []
        for mid in set(self._mercati_sessione()) | ({self.mercato_utente}
                                                    if self.mercato_utente else set()):
            out.extend(self._ordini_sessione(mid))
        return out

    def _sulla_selezione(self) -> List[Any]:
        if self.mercato_utente is None:
            return []
        return [o for o in self._ordini_sessione(self.mercato_utente)
                if int(getattr(o, "selection_id", 0) or 0) == int(self.selezione_utente or 0)]

    def _sollecita(self, codice: str, n: int = 1) -> None:
        self.sollecitati[codice] = self.sollecitati.get(codice, 0) + int(n)

    def _viola(self, codice: str, dettaglio: str, quando: str) -> None:
        self.violazioni.append((codice, REGOLE[codice], dettaglio, quando))

    def _id_utente(self) -> Optional[str]:
        o = self.ordine_utente
        return str(getattr(o, "bet_id", None) or o.id) if o is not None else None

    # ------------------------------------------------ l'ordine esterno
    def _scegli(self, ms: int) -> Optional[Tuple[str, int]]:
        """(mercato, selezione) dell'ordine esterno: la selezione dell'ultimo
        ordine VIVO della sessione (il caso piu' duro, provocato); all'ultimo
        istante utile l'ultimo abbinato o l'ultimo ordine, o il primo mercato del
        catalogo (e' gia' un mercato del bot). ``altro-mercato``: un mercato della
        registrazione fuori dalla sessione."""
        sessione = list(self._mercati_sessione())
        if self.scenario != SCENARIO_ALTRO:
            ordini = [o for mid in sessione for o in self._ordini_sessione(mid)]
            entro = self._entro_ms()
            tardi = entro is not None and ms >= entro
            vivi = [o for o in ordini if _vivo(o)]
            abbinati = [o for o in ordini if float(getattr(o, "size_matched", 0) or 0) > 0]
            scelto = vivi[-1] if vivi else ((abbinati or ordini)[-1] if (ordini and tardi)
                                            else None)
            if scelto is not None:
                return str(scelto.market_id), int(scelto.selection_id)
            if not tardi:
                return None
            candidati = sessione
        else:
            candidati = [mid for mid in self.mercati_raw if mid not in set(sessione)]
        for mid in candidati:
            m = self.quadro.markets.markets.get(mid)
            mb = getattr(m, "market_book", None) if m is not None else None
            if mb is None or str(getattr(mb, "status", "")) != "OPEN":
                continue
            for r in getattr(mb, "runners", None) or []:
                atb = getattr(getattr(r, "ex", None), "available_to_back", None) or []
                if atb:
                    return mid, int(r.selection_id)
        return None

    def _piazza(self, ms: int) -> None:
        da, entro = self._da_ms(), self._entro_ms()
        if da is None:
            return
        if ms < da:
            # prima di meta' finestra solo il caso piu' duro: la sessione ha un
            # ordine VIVO a mercato
            if self.scenario == SCENARIO_ALTRO or not any(
                    _vivo(o) for mid in self._mercati_sessione()
                    for o in self._ordini_sessione(mid)):
                return
        scelta = self._scegli(ms)
        if scelta is None:
            if entro is not None and ms >= entro and not self._avvisato:
                self._avvisato = True
                self.note.append("ordine esterno NON piazzato a %d ms: nessun mercato "
                                 "adatto aperto (si riprova al book dopo)" % ms)
            return
        from flumine.order.ordertype import LimitOrder
        from flumine.order.trade import Trade

        mid, sel = scelta
        market = self.quadro.markets.markets.get(mid)
        if market is None:
            return
        trade = Trade(market_id=mid, selection_id=sel, handicap=0.0, strategy=self.utente)
        ordine = trade.create_order(side="BACK", order_type=LimitOrder(
            price=PREZZO_UTENTE, size=SIZE_UTENTE, persistence_type="LAPSE"))
        ordine.notes["utente"] = True
        self.mercato_utente, self.selezione_utente, self.piazzato_ms = mid, sel, ms
        if market.place_order(ordine) is False:
            self.note.append("ordine esterno RIFIUTATO da flumine a %d ms" % ms)
            return
        self.ordine_utente = ordine
        self.note.append("ORDINE ESTERNO (%s): BACK %.2f a %.2f su %s/%s a %d ms"
                         % (self._chi(), SIZE_UTENTE, PREZZO_UTENTE, mid, sel, ms))

    def _chi(self) -> str:
        return {SCENARIO_APP: "terminale manuale dell'app, ref 'live'",
                SCENARIO_BOT: "OMEGA dalla coda del runner, ref 'live'"}.get(
                    self.scenario, "dal sito, nessun riferimento")

    def _riferimenti(self) -> Tuple[Any, Any]:
        """(rfo, rfs) dell'ordine esterno come li porterebbe lo stream."""
        if self.scenario in (SCENARIO_APP, SCENARIO_BOT):
            # il runner calcio piazza con customerStrategyRef 'live' e il ref di
            # flumine della sua strategia (hash-id): quello dell'utente nel quadro
            return str(self.ordine_utente.customer_order_ref), "live"
        return None, None

    def _riga_di_coda(self) -> None:
        """OMEGA: la riga della coda del runner con il bet_id dell'ordine, come la
        scrive il runner (chiavi lette da ``_proprietari_bot``)."""
        if self.scenario != SCENARIO_BOT or self.ordine_utente is None:
            return
        bid = self._id_utente()
        righe = self.db.tabelle.setdefault("betfair_live_order_requests", [])
        if any(str(r.get("bet_id")) == bid for r in righe):
            return
        righe.append({"bet_id": bid, "client_ref": CLIENT_REF_BOT, "mode": "live",
                      "params": {"source": "omega", "trade_id": 9}})

    # ------------------------------------------------ lo stream ordini
    def _firma(self, mid: str) -> Tuple[Any, ...]:
        ordini = list(self._ordini_sessione(mid))
        if self.ordine_utente is not None and self.mercato_utente == mid:
            ordini.append(self.ordine_utente)
        return tuple(sorted((str(getattr(o, "bet_id", None) or o.id),
                             round(float(getattr(o, "size_matched", 0) or 0), 2),
                             str(getattr(getattr(o, "status", None), "name", "")))
                            for o in ordini))

    def _pubblica(self, mid: str, ms: int) -> int:
        from betfairlightweight.streaming.cache import OrderBookCache

        from .. import esiti_ordini_canale as _EO
        from . import banco_comune as BC

        sv = self._sorveglianza()
        registro = getattr(sv, "registro", None) if sv is not None else None
        if registro is None:
            return 0
        conto = BC.MercatoFlumine(None)
        conto.ordini = {str(o.customer_order_ref): o for o in self._ordini_sessione(mid)}
        if self.ordine_utente is not None and self.mercato_utente == mid:
            conto.ordini_utente = {REF_UTENTE: self.ordine_utente}
            self._riga_di_coda()
        per_sel = conto.ordini_conto_come_stream(mid, int(ms))
        if not per_sel:
            return 0
        id_utente = self._id_utente()
        for uo in per_sel.values():
            for u in uo:
                if id_utente is not None and u.get("id") == id_utente:
                    u["rfo"], u["rfs"] = self._riferimenti()
        cache = OrderBookCache(str(mid), int(ms), False)
        cache.update_cache({"id": str(mid), "orc": [{"id": sid, "uo": uo}
                                                    for sid, uo in per_sel.items()]}, int(ms))
        co = cache.create_resource(0)
        co.client = SimpleNamespace(paper_trade=False)       # il client REALE
        testi: List[str] = []
        _EO.pubblica_conto_da_evento(
            SimpleNamespace(event=[co]),
            lambda t, d: testi.append(json.dumps({"t": t, "d": d}, default=str)),
            adesso_ms=int(ms))
        scattati = 0
        for t in testi:
            msg = json.loads(t)
            scattati += int(registro.ricevi_conto(msg.get("t"), msg.get("d")) or 0)
        self.pubblicazioni += 1
        return scattati

    # ------------------------------------------------------- dopo il book
    def dopo_il_book(self, market_id: str, ms: int) -> None:
        if self.ordine_utente is None and self.piazzato_ms is None:
            self._piazza(ms)
        sv = self._sorveglianza()
        if sv is None:
            return
        registro = getattr(sv, "registro", None)
        if registro is not None and sv.intervento is None and sv.in_verifica():
            # la SVEGLIA di produzione (``conferma_dei_bot``): a lettura del DB
            # fatta un evento nella coda di flumine fa rivedere le verifiche nel
            # thread di flumine, fra un messaggio e l'altro dello stream. Nel banco
            # il primo momento utile e' il passo del motore dopo QUALUNQUE book.
            registro.rivedi()
        self._segui_sospensione(sv, ms)
        if self.intervento_ms is None and sv.intervento is not None:
            self.intervento_ms = int(sv.intervento.get("deciso_ms") or ms)
            self.ricevuto_ms = sv.intervento.get("ricevuto_ms")
            self.ids_alla_decisione = {id(o) for o in self._tutti_ordini_sessione()}
            return
        if self.intervento_ms is not None:
            if self.primo_book_dopo_ms is None and ms > self.intervento_ms:
                self.primo_book_dopo_ms = ms
            self._dopo_la_decisione(ms)
            return
        mid = str(market_id)
        candidati = set(self._mercati_sessione())
        if self.mercato_utente:
            candidati.add(self.mercato_utente)
        if mid not in candidati:
            return
        firma = self._firma(mid)
        if self._firme.get(mid) == firma or not firma:
            return
        self._firme[mid] = firma
        prima = self.ordine_utente is None or float(
            getattr(self.ordine_utente, "size_matched", 0) or 0) <= 0
        if prima:
            self.pubblicazioni_prima += 1
        elif self.abbinato_ms is None:
            self.abbinato_ms = ms
            self.messaggio_ms = ms
        self._pubblica(mid, ms)
        if prima:
            # OE1: con i soli ordini della sessione (e un esterno non abbinato)
            # nessun intervento e nessuna sospensione
            self._sollecita("OE1")
            if sv.intervento is not None or sv.in_verifica():
                self._viola("OE1", "intervento o sospensione senza un ordine esterno "
                                   "abbinato: %s" % (sv.intervento or sv.conti), str(ms))
        self._segui_sospensione(sv, ms)
        if self.intervento_ms is None and sv.intervento is not None:
            self.intervento_ms = int(sv.intervento.get("deciso_ms") or ms)
            self.ricevuto_ms = sv.intervento.get("ricevuto_ms")
            self.ids_alla_decisione = {id(o) for o in self._tutti_ordini_sessione()}

    def _segui_sospensione(self, sv: Any, ms: int) -> None:
        if self.mercato_utente is None:
            return
        sospesa = sv.sospesa(self.mercato_utente, self.selezione_utente)
        if sospesa and self.sospeso_ms is None:
            self.sospeso_ms = ms
            self._ids_alla_sospensione = {id(o) for o in self._sulla_selezione()}
        if self.sospeso_ms is not None and self.ripreso_ms is None and not sospesa:
            self.ripreso_ms = ms
        if sospesa and self._ids_alla_sospensione is not None:
            self.giri_sospesi += 1
            for o in self._sulla_selezione():
                if id(o) in self._ids_alla_sospensione:
                    continue
                self._ids_alla_sospensione.add(id(o))
                st = str(getattr(getattr(o, "status", None), "name", "") or "")
                if st.upper() != "VIOLATION":
                    self.accettati_sospesi.append("%s %s@%s (%s) a %d ms" % (
                        o.side, getattr(o.order_type, "size", "?"),
                        getattr(o.order_type, "price", "?"), st, ms))

    def _dopo_la_decisione(self, ms: int) -> None:
        if self.ids_alla_decisione is None:
            return
        self.giri_dopo += 1
        if self.giri_dopo == 1:
            # OE4 (subito): al PRIMO book dopo la decisione ogni ordine della
            # sessione ancora a mercato e' gia' in annullo (CANCELLING)
            self._sollecita("OE4")
            for o in self._tutti_ordini_sessione():
                st = str(getattr(getattr(o, "status", None), "name", "") or "").upper()
                if st in ("PENDING", "EXECUTABLE", "UPDATING", "REPLACING"):
                    self._viola("OE4", "al primo book dopo l'intervento l'ordine %s (%s) "
                                       "e' ancora vivo e non in annullo"
                                % (getattr(o, "bet_id", None) or o.id, st), str(ms))
        self._sollecita("OE3")
        for o in self._tutti_ordini_sessione():
            if id(o) not in self.ids_alla_decisione:
                rif = "%s %s %s@%s" % (getattr(o, "bet_id", None) or o.id, o.side,
                                       getattr(o.order_type, "size", "?"),
                                       getattr(o.order_type, "price", "?"))
                self.ids_alla_decisione.add(id(o))
                self.nuovi_dopo.append(rif)
                self._viola("OE3", "ordine NUOVO della sessione dopo l'intervento: %s" % rif,
                            str(ms))

    # ------------------------------------------------------------- referto
    def chiudi(self, *, stato_finale: Optional[str], stats_finali: Dict[str, Any],
               attivita: List[Dict[str, Any]], ora_ms: int) -> None:
        from ..tennis_scalper import ordini_esterni as OE

        sv = self.sorveglianza_vista
        kind = OE.KIND
        if sv is None:
            self.note.append("sorveglianza degli ordini esterni ASSENTE nella sessione "
                             "(interruttore spento o prova): scenario NON esercitato")
            return
        conti = dict(getattr(sv, "conti", {}) or {})
        conferma = getattr(sv, "conferma", None)
        richieste = list(getattr(conferma, "richieste", []) or [])
        self.note.append("ORDINI ESTERNI: pubblicazioni del conto %d (di cui %d prima "
                         "dell'abbinato dell'esterno); giudizi %s; verifiche sul DB %s"
                         % (self.pubblicazioni, self.pubblicazioni_prima, conti, richieste))
        if self.sospeso_ms is not None:
            self.note.append("SOSPENSIONE: messaggio a %s ms, sospesa a %s ms (+%s ms), "
                             "ripresa a %s; giri sospesi %d; ordini nuovi della sessione "
                             "accettati sulla selezione sospesa: %s"
                             % (self.messaggio_ms, self.sospeso_ms,
                                (self.sospeso_ms - self.messaggio_ms)
                                if self.messaggio_ms is not None else None,
                                self.ripreso_ms, self.giri_sospesi,
                                self.accettati_sospesi or "nessuno"))
        ev = sv.intervento
        tipi = [str(a.get("kind")) for a in attivita]
        if self.scenario in SCENARI_STOP:
            self._chiudi_stop(sv, ev, conferma, stato_finale, stats_finali, tipi, ora_ms, kind)
        elif self.scenario == SCENARIO_BOT:
            self._sollecita("OE6")
            if self.ordine_utente is None or self.sospeso_ms is None:
                self._viola("OE6", "l'ordine di Omega non e' partito o non e' stato messo in "
                                   "verifica: %s" % "; ".join(self.note), str(ora_ms))
            if ev is not None:
                self._viola("OE6", "la sessione si e' FERMATA per un ordine di un altro bot: "
                                   "%s" % ev, str(ora_ms))
            if self.sospeso_ms is not None and self.ripreso_ms is None:
                self._viola("OE6", "la sospensione non e' mai stata rilasciata", str(ora_ms))
            if self.accettati_sospesi:
                self._viola("OE6", "ordini nuovi accettati sulla selezione sospesa: %s"
                            % self.accettati_sospesi, str(ora_ms))
            if (stats_finali or {}).get(kind) or str(stato_finale or "") == "stopped":
                self._viola("OE6", "riga '%s' con marcatore %s" % (stato_finale,
                                                                   (stats_finali or {}).get(kind)),
                            str(ora_ms))
            verifiche = list(getattr(sv, "verifiche", []) or [])
            if verifiche:
                v = verifiche[-1]
                self.note.append("ORDINE DI UN BOT riconosciuto: motivo %s, messaggio -> "
                                 "ripresa %s ms" % (v.get("motivo"), v.get("latenza_ms")))
            if OE.KIND_DI_UN_BOT not in tipi:
                self._viola("OE6", "attivita' '%s' non scritta" % OE.KIND_DI_UN_BOT,
                            str(ora_ms))
        elif self.scenario == SCENARIO_DB_GIU:
            self._sollecita("OE7")
            if self.ordine_utente is None or self.sospeso_ms is None:
                self._viola("OE7", "l'ordine esterno non e' partito o non e' in verifica: %s"
                            % "; ".join(self.note), str(ora_ms))
            if ev is not None:
                self._viola("OE7", "la sessione si e' fermata senza verifica: %s" % ev,
                            str(ora_ms))
            if self.ripreso_ms is not None:
                self._viola("OE7", "sospensione rilasciata a %d ms con il DB giu'"
                            % self.ripreso_ms, str(ora_ms))
            if self.accettati_sospesi:
                self._viola("OE7", "ordini nuovi accettati al buio sulla selezione sospesa: %s"
                            % self.accettati_sospesi, str(ora_ms))
            if OE.KIND_NON_VERIFICABILE not in tipi:
                self._viola("OE7", "attivita' '%s' non scritta" % OE.KIND_NON_VERIFICABILE,
                            str(ora_ms))
        else:
            utente = int(conti.get("utente", 0) or 0)
            if self.ordine_utente is not None and float(
                    getattr(self.ordine_utente, "size_matched", 0) or 0) > 0 and utente > 0:
                self._sollecita("OE5")
            elif self.ordine_utente is None:
                self.note.append("OE5 NON esercitato: %s" % "; ".join(self.note or ["?"]))
            if ev is not None:
                self._viola("OE5", "intervento scattato per un ordine su un mercato dove "
                                   "la sessione non opera: %s" % ev, str(ora_ms))
            if self.sospeso_ms is not None:
                self._viola("OE5", "sessione sospesa per un ordine su un altro mercato",
                            str(ora_ms))
            if (stats_finali or {}).get(kind):
                self._viola("OE5", "marcatore '%s' nella riga" % kind, str(ora_ms))
        self.note.append("limiti dichiarati: l'ordine esterno sta nel blotter del quadro "
                         "condiviso (specchio e dichiarazione di fine sessione del servizio "
                         "possono contarlo; in produzione vedono solo la sessione); latenza "
                         "di ogni lettura del DB = assunzione del banco comune")

    def _chiudi_stop(self, sv: Any, ev: Any, conferma: Any, stato_finale: Optional[str],
                     stats_finali: Dict[str, Any], tipi: List[str], ora_ms: int,
                     kind: str) -> None:
        self._sollecita("OE2")
        if self.ordine_utente is None:
            self._viola("OE2", "l'ordine esterno non e' partito: %s" % "; ".join(self.note),
                        str(ora_ms))
        elif ev is None:
            self._viola("OE2", "ordine esterno abbinato (%.2f) e la sessione NON si e' "
                               "fermata" % float(getattr(self.ordine_utente, "size_matched", 0)
                                                 or 0), str(ora_ms))
        else:
            lat = ev.get("latenza_ms")
            pronto = (conferma.pronto_ms(str(ev.get("bet_id")))
                      if conferma is not None and hasattr(conferma, "pronto_ms") else None)
            self.note.append(
                "INTERVENTO: dove=%s fonte=%s mercato=%s abbinato %.2f; messaggio a %s ms, "
                "sospensione a %s ms, verifica pronta a %s ms (%s), decisione a %s ms: "
                "LATENZA messaggio -> decisione definitiva %s ms di mercato (primo book "
                "dopo +%s ms); annullo %s"
                % (ev.get("dove"), ev.get("fonte"), ev.get("market_id"),
                   float(ev.get("abbinato_nuovo") or 0), self.ricevuto_ms, self.sospeso_ms,
                   pronto, (ev.get("verifica") or {}).get("esito"), ev.get("deciso_ms"), lat,
                   (self.primo_book_dopo_ms - int(ev.get("deciso_ms")))
                   if self.primo_book_dopo_ms is not None else None, ev.get("annullo")))
            if lat is None or lat < 0:
                self._viola("OE2", "latenza non misurata (%s)" % lat, str(ora_ms))
            if pronto is not None and int(ev.get("deciso_ms")) < pronto:
                self._viola("OE2", "decisione a %s ms PRIMA che la verifica fosse pronta "
                                   "(%s ms): decisione dai soli riferimenti"
                            % (ev.get("deciso_ms"), pronto), str(ora_ms))
            if self.sospeso_ms is None:
                self._viola("OE2", "nessuna sospensione al messaggio (la verifica sul DB "
                                   "non e' passata)", str(ora_ms))
        self._sollecita("OE4")
        vivi = [o for o in self._tutti_ordini_sessione() if _vivo(o)]
        if vivi:
            self._viola("OE4", "%d ordini della sessione ancora vivi a fine sessione"
                        % len(vivi), str(ora_ms))
        if ev is not None:
            if str(stato_finale or "") != "stopped":
                self._viola("OE4", "stato finale '%s' (atteso 'stopped')" % stato_finale,
                            str(ora_ms))
            if not (stats_finali or {}).get(kind):
                self._viola("OE4", "marcatore '%s' assente dalle stats della riga" % kind,
                            str(ora_ms))
            if kind not in tipi:
                self._viola("OE4", "attivita' '%s' non scritta" % kind, str(ora_ms))
        if self.giri_dopo == 0 and ev is not None:
            self.note.append("OE3: nessun book dopo la decisione (sessione chiusa subito)")

    def riepilogo(self) -> str:
        return "ORDINI ESTERNI: " + " | ".join(self.note)
