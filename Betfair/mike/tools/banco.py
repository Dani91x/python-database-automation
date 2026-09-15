"""IL BANCO DI PROVA — il database e il mercato che servono a `service.py`.

Serve a far girare Mike **intero** su una registrazione: non solo il cervello
(`engine.decide`) ma anche le MANI, cioe' `service._run_event` — ordini,
riconciliazione, righe, settlement. E' li' che il 15/09 si sono rotte cinque
cose, quindi e' li' che la certificazione deve arrivare.

Due doppi, e nessuno dei due deve MENTIRE:

  * `DbMemoria`   — le tabelle di Mike in memoria. Stessa firma e stessi tipi di
                    ritorno di `Betfair/mike/db.py`: `insert_trade` torna l'ID
                    (`Optional[int]`), non la riga. Un doppio che risponde a
                    domande a cui il vero non risponde e' la causa di tutti i
                    difetti del 15/09.
  * `MercatoFlumine` — gli ordini si piazzano DAVVERO su flumine e il matching
                    (coda compresa) lo fa lui. `place_order_live` restituisce un
                    `PlaceResult` VERO, importato da `omega_market`, non un
                    oggetto inventato: cosi' `ok`, `order_status`, `bet_id`,
                    `size_matched` e `avg_price_matched` sono esattamente i
                    campi che il codice legge in produzione.
                    `list_current_orders` / `list_cleared_orders` restituiscono
                    dizionari con le chiavi **snake_case** identiche a quelle
                    che `omega_market` produce dopo la normalizzazione.

LIMITI DICHIARATI, perche' un banco che non li dichiara e' peggio di nessun banco:

  * il minimo di giurisdizione (.it: BACK 2,00 / LAY 0,50) NON esiste su
    flumine: `place_submin_live` piazza diretto. Quindi il place-and-trim e il
    rifiuto `INVALID_PROFIT_RATIO` del 15/09 sera NON vengono riprodotti qui;
  * nessun errore di rete: gli stati di riconciliazione da esito IGNOTO non
    capitano da soli. Si provocano apposta con `guasti=`;
  * il `bet_delay` in-play non e' simulato.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ...omega.omega_market import PlaceResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# il database, in memoria
# ---------------------------------------------------------------------------
class DbMemoria:
    """Le tabelle di Mike in RAM, con le firme di `Betfair/mike/db.py`."""

    def __init__(self, control: Dict[str, Any]) -> None:
        self.control = dict(control)
        self.trades: List[Dict[str, Any]] = []
        self.events: Dict[str, Dict[str, Any]] = {}
        self.attivita: List[tuple] = []
        self.scan_rows: List[Dict[str, Any]] = []
        self._id = 0
        # i metodi che il servizio ha chiamato e che qui non esistono: si
        # dichiarano nel referto invece di essere ingoiati in silenzio.
        self.mancanti: List[str] = []

    # --- control ---
    def read_control(self) -> Dict[str, Any]:
        return dict(self.control)

    def set_control(self, **campi: Any) -> None:
        self.control.update(campi)

    # --- eventi ---
    def list_events(self, states: Optional[List[str]] = None,
                    since_iso: Optional[str] = None) -> List[Dict[str, Any]]:
        righe = list(self.events.values())
        if states:
            righe = [r for r in righe if str(r.get("state")) in set(states)]
        return righe

    def upsert_event(self, row: Dict[str, Any]) -> None:
        eid = str(row.get("event_id"))
        base = dict(self.events.get(eid) or {})
        base.update(row)
        self.events[eid] = base

    def upsert_events(self, rows: List[Dict[str, Any]]) -> None:
        for r in rows or []:
            self.upsert_event(r)

    # --- trades ---
    def insert_trade(self, trade: Dict[str, Any]) -> Optional[int]:
        # il vero torna l'ID, non la riga: qui uguale.
        self._id += 1
        self.trades.append({**trade, "id": self._id})
        return self._id

    def update_trade(self, trade_id: int, **campi: Any) -> None:
        for r in self.trades:
            if int(r.get("id") or 0) == int(trade_id):
                r.update(campi)
                return

    def trades_for_event(self, event_id: str, **_kw: Any) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.trades if str(r.get("event_id")) == str(event_id)]

    def open_trades(self, *_a: Any, **_k: Any) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.trades
                if str(r.get("status")) in ("open", "hedged", "pending")]

    # --- attivita' ---
    def log(self, kind: str, payload: Optional[Dict[str, Any]] = None,
            event_id: Optional[str] = None) -> None:
        self.attivita.append((str(kind), dict(payload or {}), event_id))

    def kinds(self) -> List[str]:
        return [k for k, _p, _e in self.attivita]

    # --- il resto del ciclo, che qui non ha niente da fare ---
    def fetch_scan_rows(self, *_a: Any, **_k: Any) -> List[Dict[str, Any]]:
        return list(self.scan_rows)

    def scanner_status(self, *_a: Any, **_k: Any) -> Optional[Dict[str, Any]]:
        return None

    def pending_requests(self, *_a: Any, **_k: Any) -> List[Dict[str, Any]]:
        return []

    def set_request_status(self, *_a: Any, **_k: Any) -> None:
        return None

    def fail_stale_processing(self, *_a: Any, **_k: Any) -> None:
        return None

    def aggregates(self, *_a: Any, **_k: Any) -> Dict[str, Any]:
        return {}

    def __getattr__(self, nome: str):
        # un metodo che il servizio chiama e che qui manca NON deve passare
        # inosservato: si registra e si risponde None.
        if nome.startswith("_"):
            raise AttributeError(nome)

        def _ignoto(*_a: Any, **_k: Any):
            if nome not in self.mancanti:
                self.mancanti.append(nome)
            return None
        return _ignoto


# ---------------------------------------------------------------------------
# il mercato: ordini VERI su flumine
# ---------------------------------------------------------------------------
class MercatoFlumine:
    """`place_order_live` e compagnia, serviti dal matching di flumine.

    Il `customer_ref` che il servizio passa viene CONSERVATO e restituito in
    `customer_order_ref` da `list_current_orders`: e' la chiave con cui Mike
    ritrova i suoi ordini, ed e' esattamente quella che il 15/09 veniva scritta
    in un modo e letta in un altro. Qui il giro si chiude davvero.
    """

    def __init__(self, strategia: Any) -> None:
        self.s = strategia
        # l'ultimo book visto per mercato: serve a dare l'esito IMMEDIATO del
        # place, come fa Betfair via REST.
        self.book: Dict[str, Any] = {}
        # customer_ref -> ordine flumine
        self.ordini: Dict[str, Any] = {}
        self.rifiutati: List[Dict[str, Any]] = []
        # guasti da provocare apposta: {"place_exception": N} solleva sui
        # prossimi N piazzamenti, per far nascere gli stati di riconciliazione
        self.guasti: Dict[str, int] = {}

    # ------------------------------------------------------------- place
    def place_order_live(self, *, market_id: str, selection_id: int, price: float,
                         size: float, event_id: str, side: str = "lay",
                         customer_ref: Optional[str] = None,
                         fill_or_kill: bool = True) -> PlaceResult:
        from flumine.order.ordertype import LimitOrder
        from flumine.order.trade import Trade

        if self.guasti.get("place_exception", 0) > 0:
            self.guasti["place_exception"] -= 1
            raise RuntimeError("guasto provocato: esito IGNOTO dal place")

        mercato = self.s.mercati.get(str(market_id))
        if mercato is None:
            return PlaceResult(ok=False, order_status="EXPIRED", bet_id=None,
                               size_matched=0.0, avg_price_matched=None,
                               raw={"motivo": "mercato non in replay"})
        ref = str(customer_ref or f"mike-{event_id}")[:32]
        trade = Trade(market_id=str(market_id), selection_id=int(selection_id),
                      handicap=0.0, strategy=self.s)
        ordine = trade.create_order(
            side="BACK" if str(side).lower() == "back" else "LAY",
            order_type=LimitOrder(price=float(price), size=round(float(size), 2),
                                  persistence_type="LAPSE"),
        )
        # il ref di Mike viaggia nelle note: `customer_order_ref` in flumine e'
        # derivato e in sola lettura, ma cio' che conta e' che il ref che Mike
        # ha CHIESTO torni indietro identico quando rilegge gli ordini.
        ordine.notes["mike_ref"] = ref
        try:
            mercato.place_order(ordine)
        except Exception as ex:  # noqa: BLE001 — rifiuto dichiarato, non eccezione
            self.rifiutati.append({"ref": ref, "err": str(ex)[:160]})
            return PlaceResult(ok=False, order_status="EXPIRED", bet_id=None,
                               size_matched=0.0, avg_price_matched=None,
                               raw={"motivo": str(ex)[:160]})
        self.ordini[ref] = ordine

        # L'ESITO IMMEDIATO — e qui il banco decide, non flumine. Si dichiara.
        #
        # In produzione `place_order_live` e' una REST SINCRONA: Betfair risponde
        # subito dicendo quanto si e' abbinato. Flumine invece esegue a fine
        # giro, quindi `size_matched` letto subito dopo `place_order` e' sempre
        # 0 — e il servizio, che legge `res.size_matched <= 0`, dichiarerebbe
        # 'error' ogni volta (visto: 388 ingressi tutti "non abbinati").
        #
        # Il fill immediato di un TAKER non ha bisogno di nessun modello: o il
        # prezzo chiesto e' ancora sul book o non c'e'. Quello lo si calcola qui.
        # Tutto il resto — ordini che restano a riposo, coda, abbinamenti nei
        # tick successivi — resta a flumine.
        abbinato, medio = self._fill_immediato(market_id, selection_id, side, price, size)
        if fill_or_kill and abbinato <= 0:
            # FILL_OR_KILL: la parte non abbinata subito viene uccisa da
            # Betfair. Senza questo, resterebbe a mercato un ordine vivo che il
            # servizio ha gia' dichiarato morto — una posizione fantasma.
            try:
                ordine.cancel()
            except Exception:  # noqa: BLE001
                pass
            return PlaceResult(ok=True, order_status="EXPIRED", bet_id=str(ordine.id),
                               size_matched=0.0, avg_price_matched=None, raw={})
        return PlaceResult(
            ok=True,
            order_status=("EXECUTION_COMPLETE" if abbinato >= float(size) - 1e-9
                          else "EXECUTABLE"),   # parole di Betfair, non enum flumine
            bet_id=str(getattr(ordine, "bet_id", None) or getattr(ordine, "id", "")),
            size_matched=round(float(abbinato), 2),
            avg_price_matched=medio,
            raw={},
        )

    def _fill_immediato(self, market_id: str, selection_id: int, side: str,
                        price: float, size: float):
        """Quanto si abbina SUBITO al prezzo chiesto, sul book di adesso."""
        from ...stream.backtest.sim_strategy import _offer_price, _offer_size

        mb = self.book.get(str(market_id))
        if mb is None:
            return 0.0, None
        for r in getattr(mb, "runners", None) or []:
            if int(getattr(r, "selection_id", 0) or 0) != int(selection_id):
                continue
            ex = getattr(r, "ex", None)
            livelli = ((getattr(ex, "available_to_back", None) if ex else None) or []
                       if str(side).lower() == "back"
                       else (getattr(ex, "available_to_lay", None) if ex else None) or [])
            if not livelli:
                return 0.0, None
            q, disp = _offer_price(livelli[0]), _offer_size(livelli[0])
            if q is None or disp is None:
                return 0.0, None
            # BACK: si compra se la quota offerta e' almeno quella chiesta.
            # LAY: si banca se la quota chiesta e' almeno quella disponibile.
            ok = (float(q) >= float(price) - 1e-9 if str(side).lower() == "back"
                  else float(q) <= float(price) + 1e-9)
            if not ok:
                return 0.0, None
            return min(float(size), float(disp)), float(q)
        return 0.0, None

    def place_submin_live(self, **kw: Any) -> PlaceResult:
        # LIMITE DICHIARATO: su flumine il minimo di giurisdizione non esiste,
        # quindi qui non c'e' nessun place-and-trim da riprodurre. Un importo
        # sotto il minimo viene piazzato diretto.
        return self.place_order_live(**kw)

    # -------------------------------------------------------- letture
    @staticmethod
    def _stato_betfair(ordine: Any) -> str:
        """Lo stato dell'ordine con le PAROLE DI BETFAIR.

        ⚠️ `order.status` in flumine e' un `Enum`: `str()` restituisce
        "OrderStatus.EXECUTABLE", non "Executable". Confrontarlo cosi' com'e'
        con le parole di Betfair non da' errore — da' sempre falso, e ogni
        ordine risulta NON vivo. E' la terza volta oggi che lo stesso difetto
        (un campo letto in una forma diversa da quella in cui e' scritto) si
        ripresenta, questa volta nel banco di prova: qui produceva 776
        riproposizioni della stessa lay, cioe' un loop finto.
        """
        st = getattr(ordine, "status", None)
        parola = str(getattr(st, "value", st) or "").upper()
        if parola in ("PENDING", "EXECUTABLE"):
            return "EXECUTABLE"
        if parola.startswith("EXECUTION"):
            return "EXECUTION_COMPLETE"
        return parola or "EXPIRED"

    def _vivo(self, ordine: Any) -> bool:
        return self._stato_betfair(ordine) == "EXECUTABLE"

    def _riga(self, ref: str, ordine: Any) -> Dict[str, Any]:
        """Un ordine nella forma che `omega_market` produce dopo la
        normalizzazione: chiavi in snake_case, MAI camelCase."""
        sim = getattr(ordine, "simulated", None)
        return {
            "bet_id": str(getattr(ordine, "bet_id", None) or getattr(ordine, "id", "")),
            "market_id": str(getattr(ordine, "market_id", "")),
            "selection_id": int(getattr(ordine, "selection_id", 0) or 0),
            "side": str(getattr(ordine, "side", "") or "").lower(),
            "status": self._stato_betfair(ordine),
            "size_matched": float(getattr(sim, "size_matched", 0.0) or 0.0),
            "avg_price_matched": getattr(sim, "average_price_matched", None) or None,
            "size_remaining": float(getattr(ordine, "size_remaining", 0.0) or 0.0),
            "size_settled": float(getattr(sim, "size_matched", 0.0) or 0.0),
            "customer_order_ref": ref,
        }

    def list_current_orders(self, strategy_ref: Optional[str] = None) -> List[Dict[str, Any]]:
        return [self._riga(ref, o) for ref, o in self.ordini.items() if self._vivo(o)]

    def list_cleared_orders(self, *_a: Any, **_k: Any) -> List[Dict[str, Any]]:
        return [self._riga(ref, o) for ref, o in self.ordini.items() if not self._vivo(o)]

    def read_book(self, market_id: str, *_a: Any, **_k: Any) -> Optional[Dict[str, Any]]:
        # il book a mercato chiuso serve al regolamento: nel replay lo stato
        # finale arriva dalla registrazione stessa (`process_closed_market`).
        return None
