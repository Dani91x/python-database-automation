"""adattatore_comando.py - ``RichiestaOrdine`` <-> le forme di oggi del comando ordine (W1-C1).

Scopo
-----
Tradurre, senza cambiare nulla, fra il tipo del contratto (``contratto.RichiestaOrdine``)
e le TRE forme in cui un ordine viaggia oggi:

  1. il COMANDO del canale locale (``/comando/<attore>``): il dizionario che
     ``Betfair/stream/motore_ordini.py`` ``valida_comando`` (righe ~391-475) valida e
     che Safe costruisce con ``safe_strategy/porta_ordini.costruisci_comando``;
  2. la riga della CODA calcio ``betfair_live_order_requests`` (colonne della
     migrazione ``migrations/betfair_live_order_queue.sql`` e successive), letta dal
     worker (``live_order_worker._dispatch`` / ``_do_place``);
  3. il ``payload`` della coda TENNIS ``tennis_live_order_queue`` (stesse chiavi
     ``_LOCAL_ROW_KEYS`` + ``action`` + ``mode``, ``esecutore_tennis._payload_da_riga``),
     letto da ``tennis_live_order_worker.parse_order_payload``.

Riuso, mai copia: la VALIDAZIONE del comando e' quella di oggi (``valida_comando`` e'
chiamata, non riscritta: un comando che oggi e' rifiutato lo e' anche qui, con lo stesso
``Rifiuto``); la lettura del payload tennis e' ``parse_order_payload``; le chiavi della
riga sono ``live_order_worker._LOCAL_ROW_KEYS``. Le importazioni del codice di oggi sono
PIGRE (dentro le funzioni): importare questo modulo non carica il runner.

Entrate e uscite
----------------
* ``comando_da_richiesta(r, extra)`` -> dict del comando (le chiavi di
  ``CHIAVI_COMANDO`` di Safe, piu' ``handicap`` e ``params``);
* ``richiesta_da_comando(attore, sport, d)`` -> ``(RichiestaOrdine | RichiestaComposta,
  ExtraComando)``; solleva ``motore_ordini.Rifiuto`` come oggi;
* ``riga_coda_da_richiesta(r, dettagli)`` / ``richiesta_da_riga_coda(riga, ...)``;
* ``payload_tennis_da_richiesta(r, dettagli)`` / ``richiesta_da_payload_tennis(...)``.

Cosa NON fa: non valida i minimi (``minimi.py``), non controlla freni o modo
(``controlli.py``), non manda nulla (``porta.py``). Le azioni composte di oggi (greenup,
cashout, dutch) NON sono ``RichiestaOrdine`` per contratto ("compositori sopra la
porta"): viaggiano come ``RichiestaComposta``, estensione dichiarata nel referto. La
LIABILITY di un place (coda, mai il comando) e ``min_fill_size``/``order_type`` non hanno
un campo nel contratto: stanno in ``DettagliCoda`` (estensione proposta).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Literal, Mapping, Optional, Tuple, Union, cast

from Betfair.nucleo.comuni import Modo, Sport
from Betfair.nucleo.ordini.contratto import RichiestaOrdine

AzioneComposta = Literal["greenup", "cashout_event", "cashout_all", "dutch"]
AZIONI_COMPOSTE: Tuple[str, ...] = ("greenup", "cashout_event", "cashout_all", "dutch")
#: l'azione della coda che e' un place col place-and-trim (non esiste nel comando: li'
#: lo decide il motore con ``_applica_minimi``)
AZIONE_SUBMIN = "place_submin"
#: chiavi del COMANDO che il protocollo mette solo sul ``place`` (``valida_comando``)
_LATI_COMANDO = {"back": "BACK", "lay": "LAY"}


@dataclass(frozen=True)
class RichiestaComposta:
    """ESTENSIONE PROPOSTA (contratto fisso): le azioni composte di oggi (green-up,
    cash-out di mercato/evento, dutch) che il comando e la coda servono e che per il
    contratto vivono SOPRA la porta. Stessi campi base di ``RichiestaOrdine``."""

    ref: str
    attore: str
    sport: Sport
    modo: Modo
    azione: AzioneComposta
    market_id: str
    selection_id: Optional[int] = None
    handicap: float = 0.0
    creato_ms: int = 0
    origine: Optional[Mapping[str, Any]] = None


Richiesta = Union[RichiestaOrdine, RichiestaComposta]


@dataclass(frozen=True)
class ExtraComando:
    """Cio' che il comando di oggi porta e il contratto no.

    ``max_eta_ms`` None = chiave assente (il motore usa ``MAX_ETA_DEFAULT_MS``);
    ``params`` = i params del bot cosi' come li manda (``reduces_liability`` dentro
    params e' TOLTO dal motore: qui non si conserva, e' del comando)."""

    max_eta_ms: Optional[int] = None
    params: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class DettagliCoda:
    """ESTENSIONE PROPOSTA: le colonne della coda senza campo nel contratto.

    ``azione_coda`` = ``place_submin`` quando la riga chiede il place-and-trim;
    ``liability`` = una banca espressa in responsabilita' (la coda la ammette, il
    comando no); ``params`` = il jsonb della riga, intero."""

    client_ref: Optional[str] = None
    azione_coda: Optional[str] = None
    order_type: str = "LIMIT"
    liability: Optional[float] = None
    min_fill_size: Optional[float] = None
    params: Optional[Mapping[str, Any]] = field(default=None)


# ---------------------------------------------------------------------------
# riuso pigro del codice di oggi
# ---------------------------------------------------------------------------
def _motore() -> Any:
    from Betfair.stream import motore_ordini

    return motore_ordini


def chiavi_riga() -> Tuple[str, ...]:
    """Le chiavi della riga di dispatch di oggi (``live_order_worker._LOCAL_ROW_KEYS``)."""
    from Betfair.stream import live_order_worker

    return tuple(live_order_worker._LOCAL_ROW_KEYS)


def chiavi_coda() -> Tuple[str, ...]:
    """Le colonne d'ingresso di ``betfair_live_order_requests`` (senza stato ed esito)."""
    return ("client_ref", "action", "mode") + chiavi_riga()


# ---------------------------------------------------------------------------
# 1. il comando del canale
# ---------------------------------------------------------------------------
def comando_da_richiesta(r: Richiesta, extra: Optional[ExtraComando] = None) -> Dict[str, Any]:
    """Il dizionario ``d`` del ``t="comando"`` di oggi per ``r``.

    Stesse chiavi di ``costruisci_comando`` di Safe (``None`` dove l'azione non le usa),
    ``side`` maiuscolo come lo manda Safe, ``strategy_ref`` = attore (l'unico valore che
    ``valida_comando`` ammette). Nessuna validazione qui: la fa ``valida_comando``."""
    ex = extra or ExtraComando()
    d: Dict[str, Any] = {
        "ref": r.ref,
        "attore": r.attore,
        "azione": r.azione,
        "mode": r.modo,
        "market_id": r.market_id,
        "selection_id": r.selection_id,
        "handicap": r.handicap,
        "side": None,
        "price": None,
        "size": None,
        "persistence": None,
        "bet_id": None,
        "size_reduction": None,
        "new_price": None,
        "strategy_ref": r.attore,
        "creato_ms": r.creato_ms,
        "max_eta_ms": ex.max_eta_ms,
        "origine": dict(r.origine) if r.origine is not None else None,
        "time_in_force": None,
        "reduces_liability": False,
        "params": dict(ex.params) if ex.params is not None else None,
    }
    if isinstance(r, RichiestaComposta):
        return d
    if r.azione == "place":
        d["side"] = _LATI_COMANDO.get(r.lato, r.lato) if r.lato is not None else None
        d["price"] = r.prezzo
        d["size"] = r.importo
        d["persistence"] = r.persistenza
        d["time_in_force"] = r.time_in_force
        d["reduces_liability"] = bool(r.riduce_esposizione)
    else:
        d["bet_id"] = r.bet_id
        if r.azione == "cancel":
            d["size_reduction"] = r.riduzione
        else:
            d["new_price"] = r.nuovo_prezzo
    return d


def richiesta_da_comando(attore: str, sport: Sport,
                         d: Mapping[str, Any]) -> Tuple[Richiesta, ExtraComando]:
    """Valida ``d`` con ``valida_comando`` di OGGI e ne ricava la richiesta.

    Solleva ``motore_ordini.Rifiuto`` (stesso codice e dettaglio di oggi) per ogni
    comando che il motore rifiuterebbe. Il ``ref`` non e' validato qui (lo fa la porta,
    come il motore prima di ``valida_comando``)."""
    M = _motore()
    piano = M.valida_comando(attore, dict(d))
    riga = piano["riga"]
    azione = piano["azione"]
    params = d.get("params")
    params_bot = None
    if isinstance(params, dict):
        params_bot = {k: v for k, v in params.items() if k != "reduces_liability"}
    extra = ExtraComando(max_eta_ms=d.get("max_eta_ms"), params=params_bot)
    origine = d.get("origine")
    sel = d.get("selection_id")
    if azione in AZIONI_COMPOSTE:
        comp = RichiestaComposta(
            ref=str(d.get("ref")), attore=attore, sport=sport, modo=piano["mode"],
            azione=cast(AzioneComposta, azione), market_id=str(riga["market_id"]),
            selection_id=riga.get("selection_id") if riga.get("selection_id") is not None
            else (sel if isinstance(sel, int) and not isinstance(sel, bool) else None),
            handicap=float(riga["handicap"]), creato_ms=int(piano["creato_ms"]),
            origine=origine)
        return comp, extra
    if azione == "place":
        selection_id = int(riga["selection_id"])
    else:
        # cancel/replace: il motore non legge la selezione; si conserva quella del
        # comando se intera, altrimenti 0 (il contratto la vuole intera)
        selection_id = sel if isinstance(sel, int) and not isinstance(sel, bool) else 0
    r = RichiestaOrdine(
        ref=str(d.get("ref")), attore=attore, sport=sport, modo=piano["mode"],
        azione=azione, market_id=str(riga["market_id"]), selection_id=selection_id,
        handicap=float(riga["handicap"]),
        lato=riga.get("side"),
        prezzo=riga.get("price"),
        importo=riga.get("size"),
        persistenza=riga.get("persistence") or "LAPSE",
        time_in_force=riga.get("time_in_force"),
        riduce_esposizione=bool(piano["riduce"]),
        bet_id=riga.get("bet_id"),
        riduzione=riga.get("size_reduction"),
        nuovo_prezzo=riga.get("new_price"),
        creato_ms=int(piano["creato_ms"]),
        origine=origine,
    )
    return r, extra


# ---------------------------------------------------------------------------
# 2. la riga della coda calcio (betfair_live_order_requests)
# ---------------------------------------------------------------------------
def riga_coda_da_richiesta(r: Richiesta, dettagli: Optional[DettagliCoda] = None) -> Dict[str, Any]:
    """La riga d'ingresso della coda per ``r`` (tutte le colonne d'ingresso, ``None``
    dove l'azione non le usa). ``client_ref`` = ``dettagli.client_ref`` o il ref."""
    dt = dettagli or DettagliCoda()
    riga: Dict[str, Any] = {k: None for k in chiavi_coda()}
    riga.update({
        "client_ref": dt.client_ref if dt.client_ref is not None else r.ref,
        "action": r.azione,
        "mode": r.modo,
        "market_id": r.market_id,
        "selection_id": r.selection_id,
        "handicap": r.handicap,
        "order_type": dt.order_type,
        "params": dict(dt.params) if dt.params is not None else None,
    })
    if isinstance(r, RichiestaComposta):
        return riga
    if r.azione == "place":
        riga.update({
            "action": dt.azione_coda or "place",
            "side": r.lato, "price": r.prezzo, "size": r.importo,
            "liability": dt.liability, "persistence": r.persistenza,
            "time_in_force": r.time_in_force, "min_fill_size": dt.min_fill_size,
        })
        if r.riduce_esposizione:
            p = dict(riga["params"] or {})
            p["reduces_liability"] = True
            riga["params"] = p
    else:
        # cancel/replace: la riga del motore NON porta la selezione (``valida_comando``
        # la lascia None: ``_do_cancel``/``_do_replace`` lavorano per bet_id); 0 =
        # "non nota" nel contratto, quindi None nella riga
        riga["selection_id"] = r.selection_id if r.selection_id else None
        riga["bet_id"] = r.bet_id
        if r.azione == "cancel":
            riga["size_reduction"] = r.riduzione
        else:
            riga["new_price"] = r.nuovo_prezzo
    return riga


def richiesta_da_riga_coda(riga: Mapping[str, Any], *, attore: str, sport: Sport,
                           creato_ms: int = 0) -> Tuple[Richiesta, DettagliCoda]:
    """La richiesta di una riga della coda, letta come la legge il worker di oggi:
    ``reduces_liability`` = ``params.reduces_liability`` vero (``_do_place``), lato in
    minuscolo (vincolo ``side IN ('back','lay')``), persistenza ``LAPSE`` se assente.
    Solleva ``ValueError`` su un'azione che la coda non conosce."""
    azione = str(riga.get("action") or "")
    params = riga.get("params")
    dettagli = DettagliCoda(
        client_ref=riga.get("client_ref"),
        azione_coda=AZIONE_SUBMIN if azione == AZIONE_SUBMIN else None,
        order_type=str(riga.get("order_type") or "LIMIT"),
        liability=riga.get("liability"),
        min_fill_size=riga.get("min_fill_size"),
        params=dict(params) if isinstance(params, dict) else None,
    )
    ref = str(riga.get("client_ref") or "")
    sel = riga.get("selection_id")
    base = dict(ref=ref, attore=attore, sport=sport, modo=riga.get("mode"),
                market_id=str(riga.get("market_id") or ""),
                handicap=float(riga.get("handicap") or 0.0), creato_ms=int(creato_ms))
    if azione in AZIONI_COMPOSTE:
        return RichiestaComposta(azione=cast(AzioneComposta, azione),
                                 selection_id=int(sel) if sel is not None else None,
                                 **base), dettagli
    if azione in ("place", AZIONE_SUBMIN):
        lato = riga.get("side")
        riduce = bool(isinstance(params, dict) and params.get("reduces_liability"))
        if riduce and isinstance(params, dict):
            # il flag e' un campo del contratto: nei dettagli resta il resto dei params
            resto = {k: v for k, v in params.items() if k != "reduces_liability"}
            dettagli = replace(dettagli, params=resto)
        r = RichiestaOrdine(
            azione="place", selection_id=int(sel) if sel is not None else 0,
            lato=str(lato).lower() if isinstance(lato, str) else lato,
            prezzo=riga.get("price"), importo=riga.get("size"),
            persistenza=riga.get("persistence") or "LAPSE",
            time_in_force=riga.get("time_in_force"), riduce_esposizione=riduce,
            **base)
        return r, dettagli
    if azione in ("cancel", "replace"):
        r = RichiestaOrdine(
            azione=azione, selection_id=int(sel) if sel is not None else 0,
            bet_id=str(riga["bet_id"]) if riga.get("bet_id") is not None else None,
            riduzione=riga.get("size_reduction") if azione == "cancel" else None,
            nuovo_prezzo=riga.get("new_price") if azione == "replace" else None,
            **base)
        return r, dettagli
    raise ValueError(f"azione di coda sconosciuta: {azione!r}")


# ---------------------------------------------------------------------------
# 3. il payload della coda tennis (tennis_live_order_queue)
# ---------------------------------------------------------------------------
def payload_tennis_da_richiesta(r: Richiesta,
                                dettagli: Optional[DettagliCoda] = None) -> Dict[str, Any]:
    """Il ``payload`` jsonb della coda tennis: le chiavi della riga di dispatch +
    ``action`` + ``mode`` (forma di ``esecutore_tennis._payload_da_riga``)."""
    riga = riga_coda_da_richiesta(r, dettagli)
    p = {k: riga.get(k) for k in chiavi_riga()}
    p["action"] = riga["action"]
    p["mode"] = riga["mode"]
    return p


def richiesta_da_payload_tennis(riga_coda: Mapping[str, Any], *, attore: str,
                                creato_ms: int = 0) -> Tuple[Richiesta, DettagliCoda]:
    """La richiesta di una riga della coda tennis, letta con ``parse_order_payload``
    di OGGI (stessi ValueError). ``client_ref`` della riga = ref."""
    from Betfair.stream.tennis_live import tennis_live_order_worker as TW

    cmd = TW.parse_order_payload(dict(riga_coda))
    riga = {k: cmd.get(k) for k in chiavi_coda() if k in cmd}
    riga["client_ref"] = cmd.get("client_ref")
    return richiesta_da_riga_coda(riga, attore=attore, sport="tennis", creato_ms=creato_ms)
