"""LA CASSETTA D'OMBRA del banco (T0C, 09/10/2026; H par. 4.3, 04 par. 3.8).

Durante UN replay il banco registra una CASSETTA: un registro append-only in
JSON Lines CANONICO (chiavi ordinate, nessuna conversione dei float, un record
per riga, solo ASCII). Ogni record e' una `VoceCassetta`:

    {"chiave": "<compito>|<chiave>", "dati": {...}, "kind": "<kind>", "ms": <int>}

con ``kind`` fra i SEI di 04 par. 3.8:

  * ``decisione`` - dopo ogni book passato al bot (``MotoreReplay.esegui`` ->
    ``process_market_book`` della strategia del bot, che per Safe tennis e'
    ``_Ponte._giro``): cio' che il referto del bot ha imparato in quel giro
    (decisioni, azioni, motivi, controlli sollecitati per codice, violazioni,
    stati nuovi). Il livello "condizione per condizione" (id, ok) arriva col
    contratto D: oggi il banco vede cio' che vedono i controlli;
  * ``ordine`` - ogni istruzione che arriva a flumine (``Transaction.place/
    cancel/replace/update_order``: tutti i bot, qualunque strada), ogni
    chiamata REST del bot al banco (``MercatoFlumine.place_order_live``,
    ``cancel_order_live``, ``place_submin_live``) con la risposta, e ogni riga
    ``betfair_live_orders`` dello specchio (``SpecchioOrdini._riga``);
  * ``fill`` - ogni abbinamento di flumine (``SimulatedOrder._update_matched``,
    stessa forma ``[publish_time_ms, prezzo, size]``; anche i fill del mercato
    che attraversa passano di li');
  * ``conto`` - P&L lordo/netto e commissione (``MercatoFlumine.pnl_betfair``,
    ``pnl``) e riepilogo dei fill (``riepilogo_fill``);
  * ``riga_db`` - le scritture sul DB in memoria (``DbMemoria.insert_trade/
    update_trade/delete_trade/upsert_event/log/set_control`` e le stesse delle
    sottoclassi di Omega e Safe; i finti dello scalper e del tennis);
  * ``referto`` - i numeri del referto di ogni replay (``_lavora``) e, nel
    padre, il testo intero del referto (riga per riga) e il SIGILLO.

INNOCUITA'. Gli agganci sono AVVOLGIMENTI installati SOLO mentre la cassetta e'
accesa (``certifica --cassetta/--ombra/--congela``) e tolti alla fine di ogni
replay (anche su eccezione): a cassetta spenta il codice del banco e dei bot e'
byte per byte quello di prima, nessuna funzione e' sostituita. Gli avvolgimenti
chiamano l'originale con gli stessi argomenti e ne restituiscono il risultato
(o rilanciano la stessa eccezione): non toccano il valore, ne' l'ordine delle
chiamate, ne' il tempo di mercato. La prova e' nel referto T0C (referti
identici esclusi i tempi, con e senza cassetta).

PIU' PROCESSI. Ogni replay (coppia evento x scenario) scrive il SUO segmento in
``$BANCO_CASSETTA_DIR`` (variabile d'ambiente: la eredita il processo figlio,
anche con ``spawn``); il padre li riunisce nell'ordine canonico (etichetta del
compito) con ``assembla``. Il risultato non dipende da ``--worker``.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import contextlib
import dataclasses
import datetime as _dt
import enum
import hashlib
import json
import os
import sys
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

#: i sei livelli della cassetta (04 par. 3.8): nessun altro
KINDS: Tuple[str, ...] = ("decisione", "ordine", "fill", "conto", "riga_db", "referto")

#: la cartella dei segmenti (padre -> figli). Assente = cassetta SPENTA.
ENV_DIR = "BANCO_CASSETTA_DIR"

#: la chiave del sigillo (ultimo record di ogni cassetta)
CHIAVE_SIGILLO = "sigillo"
#: la chiave della testata (primo record di ogni cassetta)
CHIAVE_TESTATA = "testata"
#: la chiave delle righe del testo del referto
CHIAVE_TESTO = "referto|testo"

#: il registratore del replay in corso in QUESTO processo (None = spenta)
ATTIVA: Optional["Registratore"] = None


@dataclasses.dataclass(frozen=True)
class VoceCassetta:
    """Un record della cassetta (04 par. 3.8)."""
    kind: str
    ms: int
    chiave: str
    dati: Mapping[str, Any]


# ---------------------------------------------------------------------------
# la forma CANONICA
# ---------------------------------------------------------------------------
def jsonabile(x: Any, _prof: int = 0) -> Any:
    """Il valore in forma JSON, senza perdere niente di cio' che conta e senza
    mai scrivere un indirizzo di memoria (un ``repr`` di oggetto cambierebbe da
    un giro all'altro e farebbe divergere due replay identici).

    I float restano float (``json`` li scrive col ``repr`` piu' corto che si
    rilegge identico: nessun arrotondamento del confronto)."""
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    if _prof > 24:
        return "<profondo>"
    if isinstance(x, enum.Enum):
        return x.name
    if isinstance(x, (_dt.datetime, _dt.date, _dt.time)):
        return x.isoformat()
    if isinstance(x, _dt.timedelta):
        return x.total_seconds()
    if isinstance(x, Mapping):
        return {str(k): jsonabile(v, _prof + 1) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonabile(v, _prof + 1) for v in x]
    if isinstance(x, (set, frozenset)):
        return sorted((jsonabile(v, _prof + 1) for v in x),
                      key=lambda v: json.dumps(v, sort_keys=True, default=str))
    if isinstance(x, (bytes, bytearray)):
        return bytes(x).hex()
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return {f.name: jsonabile(getattr(x, f.name, None), _prof + 1)
                for f in dataclasses.fields(x)}
    # un oggetto qualunque: il NOME del tipo, mai il suo repr
    return "<%s>" % type(x).__name__


def canonica(voce: Mapping[str, Any]) -> str:
    """Una riga canonica: chiavi ordinate, separatori senza spazi, solo ASCII."""
    return json.dumps(voce, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def record(kind: str, ms: Any, chiave: str, dati: Any) -> Dict[str, Any]:
    """Il record (dizionario) di una voce, validato."""
    if kind not in KINDS:
        raise ValueError("kind fuori dai sei della cassetta: %r" % (kind,))
    try:
        ms_i = int(ms or 0)
    except (TypeError, ValueError):
        ms_i = 0
    return {"kind": kind, "ms": ms_i, "chiave": str(chiave), "dati": jsonabile(dati)}


def leggi_voce(riga: str) -> VoceCassetta:
    d = json.loads(riga)
    return VoceCassetta(kind=d["kind"], ms=int(d["ms"]), chiave=d["chiave"], dati=d["dati"])


# ---------------------------------------------------------------------------
# il REGISTRATORE di un replay
# ---------------------------------------------------------------------------
def _num(x: Any) -> Any:
    return x if isinstance(x, (int, float)) else None


class _Osservato:
    """Un referto del bot sotto osservazione: la sua ultima fotografia."""

    __slots__ = ("r", "firma", "motivi", "sollecitati", "n_viol", "n_stati")

    def __init__(self, r: Any) -> None:
        self.r = r
        self.firma: Any = None
        self.motivi: Dict[str, Any] = {}
        self.sollecitati: Dict[str, Any] = {}
        self.n_viol = 0
        self.n_stati = 0


def _firma_referto(r: Any) -> Tuple[Any, ...]:
    """La firma ECONOMICA di un referto (si calcola a ogni book): se non cambia,
    nel giro non e' successo niente che il referto sappia."""
    soll = getattr(r, "sollecitati", None)
    try:
        tot_soll = sum(int(v or 0) for v in soll.values()) if isinstance(soll, dict) else 0
    except (TypeError, ValueError):
        tot_soll = -1
    motivi = getattr(r, "motivi", None)
    return (getattr(r, "decisioni", None), getattr(r, "azioni", None),
            len(getattr(r, "violazioni", None) or ()),
            len(getattr(r, "stati_visti", None) or ()), tot_soll,
            len(motivi) if isinstance(motivi, dict) else 0,
            getattr(r, "ordini_piazzati", None))


class Registratore:
    """Scrive i record di UN replay (un compito) nel suo segmento."""

    def __init__(self, etichetta: str, percorso: Optional[str]) -> None:
        self.etichetta = str(etichetta)
        self.percorso = percorso
        self._fh = (open(percorso, "w", encoding="ascii", newline="\n")
                    if percorso else None)
        self.righe: List[str] = []          # solo senza file (test)
        self.ora_ms = 0
        self.conta: Dict[str, int] = {k: 0 for k in KINDS}
        self._referti: List[_Osservato] = []
        self.limiti: List[str] = []
        # le toppe del replay (le usa ``DbMemoria.__init__`` avvolto)
        self.toppe: Optional["_Toppe"] = None
        # l'ultima riga scritta per chiave (``SCRITTURE_A_DIFFERENZA``)
        self.ultime_righe: Dict[Tuple[str, str, str], Any] = {}

    # --- scrittura -----------------------------------------------------------
    def voce(self, kind: str, ms: Any, chiave: str, dati: Any) -> None:
        riga = canonica(record(kind, ms, "%s|%s" % (self.etichetta, chiave), dati))
        self.conta[kind] += 1
        if self._fh is not None:
            self._fh.write(riga + "\n")
        else:
            self.righe.append(riga)

    def chiudi(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    # --- decisioni -----------------------------------------------------------
    def osserva_referto(self, r: Any) -> None:
        if not any(o.r is r for o in self._referti):
            self._referti.append(_Osservato(r))

    def dopo_il_giro(self, ms: Optional[int] = None) -> None:
        """Dopo un book passato al bot: per ogni referto osservato, se e'
        cambiato, il record ``decisione`` con la DIFFERENZA."""
        quando = self.ora_ms if ms is None else int(ms)
        for i, o in enumerate(self._referti):
            r = o.r
            f = _firma_referto(r)
            if f == o.firma:
                continue
            prima = o.firma
            o.firma = f
            dati: Dict[str, Any] = {"tick": _num(getattr(r, "tick", None))}
            if prima is not None:
                dati["decisioni"] = (f[0] - prima[0]) if isinstance(f[0], int) and \
                    isinstance(prima[0], int) else f[0]
                dati["azioni"] = (f[1] - prima[1]) if isinstance(f[1], int) and \
                    isinstance(prima[1], int) else f[1]
            else:
                dati["decisioni"] = f[0]
                dati["azioni"] = f[1]
            motivi = getattr(r, "motivi", None)
            if isinstance(motivi, dict):
                dm = {str(k): v for k, v in motivi.items() if o.motivi.get(k) != v}
                if dm:
                    dati["motivi"] = dm
                o.motivi = dict(motivi)
            soll = getattr(r, "sollecitati", None)
            if isinstance(soll, dict):
                ds = {str(k): v for k, v in soll.items() if o.sollecitati.get(k) != v}
                if ds:
                    dati["sollecitati"] = ds
                o.sollecitati = dict(soll)
            viol = list(getattr(r, "violazioni", None) or [])
            if len(viol) > o.n_viol:
                dati["violazioni"] = [[str(getattr(v, "codice", "")),
                                       str(getattr(v, "dettaglio", ""))]
                                      for v in viol[o.n_viol:]]
            o.n_viol = len(viol)
            stati = list(getattr(r, "stati_visti", None) or [])
            if len(stati) > o.n_stati:
                dati["stati_nuovi"] = [str(s) for s in stati[o.n_stati:]]
            o.n_stati = len(stati)
            if f[6] is not None:
                dati["ordini_piazzati"] = f[6]
            self.voce("decisione", quando, "referto%d" % i, dati)

    # --- i numeri del referto di fine replay ----------------------------------
    def voce_referto(self, r: Any) -> None:
        viol = [[str(getattr(v, "codice", "")), str(getattr(v, "regola", "")),
                 str(getattr(v, "dettaglio", ""))]
                for v in list(getattr(r, "violazioni", None) or [])]
        dati = {
            "event_id": str(getattr(r, "event_id", "")),
            "tick": getattr(r, "tick", None),
            "decisioni": getattr(r, "decisioni", None),
            "azioni": getattr(r, "azioni", None),
            "ordini_piazzati": getattr(r, "ordini_piazzati", None),
            "stati_visti": list(getattr(r, "stati_visti", None) or []),
            "motivi": dict(getattr(r, "motivi", None) or {}),
            "sollecitati": dict(getattr(r, "sollecitati", None) or {}),
            "violazioni": viol,
            "note": [str(n) for n in (getattr(r, "note", None) or [])],
            "non_esercitato": list(getattr(r, "non_esercitato", None) or []),
            "non_applicabili": dict(getattr(r, "non_applicabili", None) or {}),
            "non_esercitabili": dict(getattr(r, "non_esercitabili", None) or {}),
            "limiti_della_cassetta": list(self.limiti),
            "conteggi_cassetta": dict(self.conta),
        }
        self.voce("referto", self.ora_ms, "esito", dati)


def registra(kind: str, ms: Any, chiave: str, dati: Any) -> None:
    """L'aggancio da dentro il banco: a cassetta spenta NON fa niente."""
    reg = ATTIVA
    if reg is not None:
        reg.voce(kind, ms, chiave, dati)


def accesa() -> bool:
    """La cassetta e' accesa per questo processo? (variabile d'ambiente)"""
    return bool(os.environ.get(ENV_DIR))


# ---------------------------------------------------------------------------
# GLI AGGANCI (avvolgimenti installati solo a cassetta accesa)
# ---------------------------------------------------------------------------
def _ms_di_datetime(t: Any) -> Optional[int]:
    if t is None:
        return None
    try:
        return int(round(t.timestamp() * 1000.0))
    except Exception:  # noqa: BLE001 - orologio inatteso
        return None


def _ms_del_mercato(mercato_flumine: Any) -> int:
    """L'orologio di mercato del banco (``MotoreReplay._ora_mercato``) visto da
    un ``MercatoFlumine``; senza motore l'ultimo istante noto."""
    motore = getattr(mercato_flumine, "motore", None)
    ms = _ms_di_datetime(getattr(motore, "_ora_mercato", None))
    if ms is None and ATTIVA is not None:
        return ATTIVA.ora_ms
    return int(ms or 0)


def _identita_flumine(ordine: Any) -> Dict[str, Any]:
    ot = getattr(ordine, "order_type", None)
    note = getattr(ordine, "notes", None)
    tr = getattr(ordine, "trade", None)
    st = getattr(ordine, "status", None)
    return {
        "ordine_id": getattr(ordine, "id", None),
        "trade_id": getattr(tr, "id", None),
        "bot_ref": note.get("bot_ref") if isinstance(note, dict) else None,
        "market_id": getattr(ordine, "market_id", None),
        "selection_id": getattr(ordine, "selection_id", None),
        "handicap": getattr(ordine, "handicap", None),
        "side": getattr(ordine, "side", None),
        "tipo": getattr(getattr(ot, "ORDER_TYPE", None), "name", None),
        "prezzo": getattr(ot, "price", None),
        "size": getattr(ot, "size", None),
        "persistenza": getattr(ot, "persistence_type", None),
        "time_in_force": getattr(ot, "time_in_force", None),
        "stato": getattr(st, "name", None) if st is not None else None,
        "bet_id": getattr(ordine, "bet_id", None),
    }


def _ms_transazione(tx: Any) -> int:
    mb = getattr(getattr(tx, "market", None), "market_book", None)
    ms = getattr(mb, "publish_time_epoch", None)
    if isinstance(ms, (int, float)):
        return int(ms)
    return ATTIVA.ora_ms if ATTIVA is not None else 0


class _Toppe:
    """Le sostituzioni di attributi di classe fatte a cassetta accesa, con gli
    originali per rimetterle a posto (in ordine inverso)."""

    def __init__(self) -> None:
        self._fatte: List[Tuple[Any, str, Any, bool]] = []

    def metti(self, cls: Any, nome: str, nuova: Callable[..., Any]) -> None:
        aveva = nome in cls.__dict__
        vecchia = cls.__dict__.get(nome)
        setattr(cls, nome, nuova)
        self._fatte.append((cls, nome, vecchia, aveva))

    def togli(self) -> None:
        while self._fatte:
            cls, nome, vecchia, aveva = self._fatte.pop()
            if aveva:
                setattr(cls, nome, vecchia)
            else:
                try:
                    delattr(cls, nome)
                except AttributeError:  # pragma: no cover - gia' tolta
                    pass


def _avvolgi_rest(nome: str, orig: Callable[..., Any]) -> Callable[..., Any]:
    """``MercatoFlumine.<nome>``: la richiesta del bot e la risposta del banco."""

    def avvolta(self: Any, *a: Any, **k: Any) -> Any:
        reg = ATTIVA
        if reg is None:
            return orig(self, *a, **k)
        ms0 = _ms_del_mercato(self)
        richiesta = {"args": list(a), "kw": dict(k)}
        ref = k.get("customer_ref") if isinstance(k, dict) else None
        if nome == "cancel_order_live":
            ref = a[0] if a else k.get("bet_id")
        chiave = "rest.%s|%s" % (nome, "" if ref is None else str(ref))
        try:
            esito = orig(self, *a, **k)
        except BaseException as ex:
            reg.voce("ordine", ms0, chiave, {
                "richiesta": richiesta, "ms_risposta": _ms_del_mercato(self),
                "eccezione": "%s: %s" % (type(ex).__name__, str(ex)[:300]),
                "error_code": getattr(ex, "error_code", None)})
            raise
        reg.voce("ordine", ms0, chiave, {"richiesta": richiesta, "esito": esito,
                                         "ms_risposta": _ms_del_mercato(self)})
        return esito

    avvolta.__wrapped__ = orig  # type: ignore[attr-defined]
    return avvolta


def _avvolgi_conto(nome: str, orig: Callable[..., Any]) -> Callable[..., Any]:
    def avvolta(self: Any, *a: Any, **k: Any) -> Any:
        esito = orig(self, *a, **k)
        reg = ATTIVA
        if reg is not None:
            reg.voce("conto", _ms_del_mercato(self), nome,
                     {"args": list(a), "kw": dict(k), "esito": esito})
        return esito

    avvolta.__wrapped__ = orig  # type: ignore[attr-defined]
    return avvolta


def _avvolgi_transazione(nome: str, orig: Callable[..., Any]) -> Callable[..., Any]:
    """``flumine Transaction.<nome>``: ogni istruzione che arriva a flumine."""

    def avvolta(self: Any, order: Any, *a: Any, **k: Any) -> Any:
        reg = ATTIVA
        if reg is None:
            return orig(self, order, *a, **k)
        try:
            esito = orig(self, order, *a, **k)
        except BaseException as ex:
            dati = _identita_flumine(order)
            dati.update({"args": list(a), "kw": dict(k),
                         "eccezione": "%s: %s" % (type(ex).__name__, str(ex)[:300])})
            reg.voce("ordine", _ms_transazione(self), "transazione.%s|%s"
                     % (nome, dati.get("bot_ref") or ""), dati)
            raise
        dati = _identita_flumine(order)
        dati.update({"args": list(a), "kw": dict(k), "accettato": esito,
                     "violazione": getattr(order, "violation_msg", None)})
        reg.voce("ordine", _ms_transazione(self), "transazione.%s|%s"
                 % (nome, dati.get("bot_ref") or ""), dati)
        return esito

    avvolta.__wrapped__ = orig  # type: ignore[attr-defined]
    return avvolta


def _avvolgi_fill(orig: Callable[..., Any]) -> Callable[..., Any]:
    """``SimulatedOrder._update_matched``: ogni abbinamento, dopo che e' avvenuto."""

    def avvolta(self: Any, data: Any) -> Any:
        esito = orig(self, data)
        reg = ATTIVA
        if reg is not None:
            ordine = getattr(self, "order", None)
            ident = _identita_flumine(ordine)
            ms = data[0] if isinstance(data, (list, tuple)) and data else None
            reg.voce("fill", ms if isinstance(ms, (int, float)) else reg.ora_ms,
                     "fill|%s" % (ident.get("bot_ref") or ""),
                     {"matched": list(data) if isinstance(data, (list, tuple)) else data,
                      "ordine_id": ident["ordine_id"], "bet_id": ident["bet_id"],
                      "market_id": ident["market_id"], "selection_id": ident["selection_id"],
                      "side": ident["side"], "prezzo_ordine": ident["prezzo"],
                      "size_matched": getattr(self, "size_matched", None),
                      "average_price_matched": getattr(self, "average_price_matched", None)})
        return esito

    avvolta.__wrapped__ = orig  # type: ignore[attr-defined]
    return avvolta


def _avvolgi_specchio(orig: Callable[..., Any]) -> Callable[..., Any]:
    """``SpecchioOrdini._riga``: la riga ``betfair_live_orders`` quando nasce."""

    def avvolta(self: Any, ordine: Any, market: Any, ms: Any) -> Any:
        prima = len(getattr(self, "righe", None) or [])
        esito = orig(self, ordine, market, ms)
        reg = ATTIVA
        righe = getattr(self, "righe", None) or []
        if reg is not None and len(righe) > prima:
            for riga in righe[prima:]:
                reg.voce("ordine", ms, "specchio|%s" % (riga.get("client_order_ref") or ""),
                         {"riga": riga, "sorgente": getattr(self, "sorgente", None)})
        return esito

    avvolta.__wrapped__ = orig  # type: ignore[attr-defined]
    return avvolta


#: un valore tolto dalla riga (nella DIFFERENZA di ``delta``)
TOLTO = "<tolto>"


def delta(prima: Any, dopo: Any) -> Any:
    """La DIFFERENZA fra due valori JSON: per i dizionari solo le chiavi
    cambiate (ricorsiva), con ``TOLTO`` per le chiavi sparite; altrimenti il
    valore nuovo. Due valori uguali danno ``{}``."""
    if isinstance(prima, dict) and isinstance(dopo, dict):
        out: Dict[str, Any] = {}
        for k in dopo:
            if k not in prima:
                out[k] = dopo[k]
            elif prima[k] != dopo[k]:
                out[k] = delta(prima[k], dopo[k])
        for k in prima:
            if k not in dopo:
                out[k] = TOLTO
        return out
    return dopo


#: le scritture "a riga intera" ripetute a OGNI giro (Mike: ``upsert_event``
#: ~7.500 volte su ``base``, 6 KB l'una): la cassetta ne scrive la DIFFERENZA
#: rispetto all'ultima riga scritta per la stessa chiave (colonna per colonna,
#: anche dentro ``ctx``) e l'elenco delle colonne passate. Nessuna chiamata si
#: perde: una riga identica alla precedente e' un record con ``delta`` vuoto.
SCRITTURE_A_DIFFERENZA: Tuple[str, ...] = ("upsert_event",)


def _avvolgi_db(nome: str, orig: Callable[..., Any]) -> Callable[..., Any]:
    """Una scrittura del DB in memoria. E' un attributo di CLASSE: le istanze
    restano quelle di prima (anche per il ``pickle`` verso il processo padre)."""

    def avvolta(self: Any, *a: Any, **k: Any) -> Any:
        reg = ATTIVA
        if reg is None:
            return orig(self, *a, **k)
        # si fotografa PRIMA della chiamata: il metodo puo' arricchire il
        # dizionario che riceve (``updated_at``), e conta cio' che il bot scrive
        if nome in SCRITTURE_A_DIFFERENZA and len(a) == 1 and not k \
                and isinstance(a[0], Mapping):
            riga = jsonabile(dict(a[0]))
            chiave_riga = (type(self).__name__, nome, str(riga.get("event_id")))
            prec = reg.ultime_righe.get(chiave_riga)
            reg.ultime_righe[chiave_riga] = riga
            richiesta = {"tabella": type(self).__name__, "event_id": riga.get("event_id"),
                         "colonne": sorted(riga),
                         "delta": riga if prec is None else delta(prec, riga)}
        else:
            richiesta = {"args": jsonabile(list(a)), "kw": jsonabile(dict(k)),
                         "tabella": type(self).__name__}
        try:
            esito = orig(self, *a, **k)
        except BaseException as ex:
            reg.voce("riga_db", reg.ora_ms, nome, dict(richiesta, eccezione="%s: %s" % (
                type(ex).__name__, str(ex)[:300])))
            raise
        reg.voce("riga_db", reg.ora_ms, nome, dict(richiesta, esito=esito))
        return esito

    avvolta.__wrapped__ = orig  # type: ignore[attr-defined]
    avvolta.__cassetta__ = True  # type: ignore[attr-defined]
    return avvolta


#: le scritture del DB in memoria del banco (e delle sue sottoclassi)
METODI_DB_MEMORIA: Tuple[str, ...] = ("insert_trade", "update_trade", "delete_trade",
                                      "upsert_event", "log", "set_control")

#: i finti DB dei replay che NON derivano da ``DbMemoria`` (modulo, classe,
#: scritture). Si avvolgono solo se il modulo e' gia' importato (lo importa il
#: replay del bot): la cassetta non importa niente di suo.
FINTI_DB_ADATTATORI: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("Betfair.stream.scalper.tools.replay_registrazioni", "_DbFinto",
     ("set_control", "log", "log_many")),
    ("Betfair.stream.tennis_live.tools.replay_bot", "_DbReplay",
     ("write_tennis_order_done", "write_tennis_order_error", "set_tennis_bot_status",
      "write_tennis_bot_activity")),
)


def _avvolgi_init_db(orig: Callable[..., Any]) -> Callable[..., Any]:
    """``DbMemoria.__init__``: alla nascita di un DB in memoria le sue scritture
    si avvolgono nella classe che le DEFINISCE (la prima nella MRO), cosi' le
    sottoclassi (Omega, Safe) che le ridefiniscono senza ``super()`` sono
    osservate lo stesso. Le toppe le toglie il registratore a fine replay."""

    def avvolta(self: Any, *a: Any, **k: Any) -> None:
        orig(self, *a, **k)
        reg = ATTIVA
        if reg is None or reg.toppe is None:
            return
        for nome in METODI_DB_MEMORIA:
            for cls in type(self).__mro__:
                fn = cls.__dict__.get(nome)
                if fn is None:
                    continue
                if callable(fn) and not getattr(fn, "__cassetta__", False):
                    reg.toppe.metti(cls, nome, _avvolgi_db(nome, fn))
                break

    avvolta.__wrapped__ = orig  # type: ignore[attr-defined]
    return avvolta


def _avvolgi_init_referto(orig: Callable[..., Any]) -> Callable[..., Any]:
    def avvolta(self: Any, *a: Any, **k: Any) -> None:
        orig(self, *a, **k)
        reg = ATTIVA
        if reg is not None:
            reg.osserva_referto(self)

    avvolta.__wrapped__ = orig  # type: ignore[attr-defined]
    return avvolta


def _avvolgi_esegui(orig: Callable[..., Any]) -> Callable[..., Any]:
    """``MotoreReplay.esegui``: il ``process_market_book`` della strategia del
    bot si avvolge SULL'ISTANZA per il tempo del replay: prima del giro si
    aggiorna l'orologio della cassetta, dopo si scrivono le decisioni."""

    def avvolta(self: Any, strategia: Any) -> Any:
        reg = ATTIVA
        attributi = getattr(strategia, "__dict__", None)
        if reg is None or not isinstance(attributi, dict):
            if reg is not None:
                reg.limiti.append("decisione: strategia senza __dict__ (%s)"
                                  % type(strategia).__name__)
            return orig(self, strategia)
        # ``check_market_book`` arriva per primo a ogni book (il ponte dello
        # scalper fa li' tutto il suo giro e torna False); se torna vero segue
        # ``process_market_book``. La decisione si legge dopo l'ULTIMO dei due.
        check = getattr(strategia, "check_market_book", None)
        giro = getattr(strategia, "process_market_book", None)
        salvati = {n: (n in attributi, attributi.get(n))
                   for n in ("check_market_book", "process_market_book")}

        def check_market_book(market: Any, market_book: Any) -> Any:
            ms = getattr(market_book, "publish_time_epoch", None)
            if isinstance(ms, (int, float)):
                reg.ora_ms = int(ms)
            esito = check(market, market_book)
            if not esito or giro is None:
                reg.dopo_il_giro()
            return esito

        def process_market_book(market: Any, market_book: Any) -> Any:
            ms = getattr(market_book, "publish_time_epoch", None)
            if isinstance(ms, (int, float)):
                reg.ora_ms = int(ms)
            esito = giro(market, market_book)
            reg.dopo_il_giro()
            return esito

        if callable(check):
            attributi["check_market_book"] = check_market_book
        if callable(giro):
            attributi["process_market_book"] = process_market_book
        try:
            return orig(self, strategia)
        finally:
            for n, (aveva, vecchia) in salvati.items():
                if aveva:
                    attributi[n] = vecchia
                else:
                    attributi.pop(n, None)

    avvolta.__wrapped__ = orig  # type: ignore[attr-defined]
    return avvolta


def installa(toppe: _Toppe, controlli: Any = None) -> List[str]:
    """Installa gli agganci. Torna i limiti (agganci non disponibili)."""
    from flumine.execution.transaction import Transaction
    from flumine.simulation.simulatedorder import SimulatedOrder

    from . import banco_comune as BC
    from . import varianti_bot as VB

    limiti: List[str] = []
    for nome in ("place_order_live", "cancel_order_live", "place_submin_live"):
        toppe.metti(BC.MercatoFlumine, nome, _avvolgi_rest(nome, getattr(BC.MercatoFlumine, nome)))
    for nome in ("pnl_betfair", "pnl", "riepilogo_fill"):
        toppe.metti(BC.MercatoFlumine, nome, _avvolgi_conto(nome, getattr(BC.MercatoFlumine, nome)))
    for nome in ("place_order", "cancel_order", "replace_order", "update_order"):
        toppe.metti(Transaction, nome, _avvolgi_transazione(nome, getattr(Transaction, nome)))
    toppe.metti(SimulatedOrder, "_update_matched", _avvolgi_fill(SimulatedOrder._update_matched))
    toppe.metti(VB.SpecchioOrdini, "_riga", _avvolgi_specchio(VB.SpecchioOrdini._riga))
    toppe.metti(BC.DbMemoria, "__init__", _avvolgi_init_db(BC.DbMemoria.__init__))
    toppe.metti(BC.MotoreReplay, "esegui", _avvolgi_esegui(BC.MotoreReplay.esegui))
    for modulo, classe, metodi in FINTI_DB_ADATTATORI:
        m = sys.modules.get(modulo)
        cls = getattr(m, classe, None) if m is not None else None
        if cls is None:
            continue
        for nome in metodi:
            fn = cls.__dict__.get(nome)
            if callable(fn):
                toppe.metti(cls, nome, _avvolgi_db(nome, fn))
    referto_cls = getattr(controlli, "Referto", None) if controlli is not None else None
    if isinstance(referto_cls, type) and "__init__" in referto_cls.__dict__:
        toppe.metti(referto_cls, "__init__", _avvolgi_init_referto(referto_cls.__init__))
    else:
        limiti.append("decisione: modulo di controlli senza Referto osservabile")
    return limiti


def etichetta_compito(compito: Sequence[Any]) -> str:
    """L'etichetta del replay: ``<evento> [<scenario>]`` e ``<trasporto>``."""
    ev, scenario = compito[1], compito[3]
    tr = compito[6] if len(compito) > 6 else None
    return "%s [%s]%s" % (ev, scenario, (" <%s>" % tr) if tr else "")


def nome_segmento(etichetta: str) -> str:
    return hashlib.sha1(etichetta.encode("utf-8")).hexdigest()[:20] + ".jsonl"  # noqa: S324


@contextlib.contextmanager
def compito(compito_: Sequence[Any], controlli: Any = None,
            cartella: Optional[str] = None) -> Iterator[Optional[Registratore]]:
    """Accende la cassetta per UN replay (un compito di ``certifica._lavora``).
    Senza ``cartella`` (e senza ``$BANCO_CASSETTA_DIR``) non fa NIENTE."""
    global ATTIVA
    dove = cartella or os.environ.get(ENV_DIR)
    if not dove:
        yield None
        return
    etichetta = etichetta_compito(compito_)
    reg = Registratore(etichetta, os.path.join(dove, nome_segmento(etichetta)))
    toppe = _Toppe()
    reg.toppe = toppe
    precedente = ATTIVA
    try:
        reg.voce("referto", 0, "compito", {
            "bot": compito_[0], "evento": compito_[1], "scenario": compito_[3],
            "ogni_ms": compito_[4], "diff": compito_[5],
            "trasporto": compito_[6] if len(compito_) > 6 else None})
        reg.limiti.extend(installa(toppe, controlli))
        ATTIVA = reg
        yield reg
        reg.dopo_il_giro()
    finally:
        ATTIVA = precedente
        toppe.togli()
        reg.chiudi()


# ---------------------------------------------------------------------------
# il padre: RIUNIRE i segmenti, SIGILLARE, VERIFICARE il sigillo
# ---------------------------------------------------------------------------
def _segmenti(cartella: str) -> List[Tuple[str, List[str]]]:
    out: List[Tuple[str, List[str]]] = []
    for nome in sorted(os.listdir(cartella)):
        if not nome.endswith(".jsonl"):
            continue
        with open(os.path.join(cartella, nome), encoding="ascii") as fh:
            righe = [r.rstrip("\n") for r in fh if r.strip()]
        if not righe:
            continue
        etichetta = json.loads(righe[0])["chiave"].split("|", 1)[0]
        out.append((etichetta, righe))
    out.sort(key=lambda x: x[0])
    return out


def sigillo(righe: Sequence[str]) -> str:
    h = hashlib.sha256()
    for r in righe:
        h.update(r.encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def assembla(cartella: str, testata: Mapping[str, Any], testo_referto: str) -> List[str]:
    """La cassetta INTERA: testata, segmenti in ordine canonico, testo del
    referto riga per riga, sigillo (sha256 di tutte le righe precedenti)."""
    righe = [canonica(record("referto", 0, CHIAVE_TESTATA, dict(testata)))]
    for _etichetta, seg in _segmenti(cartella):
        righe.extend(seg)
    for riga in testo_referto.splitlines():
        righe.append(canonica(record("referto", 0, CHIAVE_TESTO, {"riga": riga})))
    righe.append(canonica(record("referto", 0, CHIAVE_SIGILLO,
                                 {"sha256": sigillo(righe), "voci": len(righe)})))
    return righe


def scrivi(percorso: str, righe: Sequence[str]) -> str:
    """Scrive la cassetta (ASCII, fine riga LF). Torna lo sha256 del file.

    Con un nome che finisce in ``.gz`` la scrive compressa e DETERMINISTICA
    (gzip senza data ne' nome dentro: stesso contenuto = stessi byte = stesso
    sha256): e' la forma per le cassette da congelare (lo scalper ne fa ~20 MB
    a scenario in chiaro)."""
    import gzip

    cartella = os.path.dirname(os.path.abspath(percorso))
    os.makedirs(cartella, exist_ok=True)
    dati = "".join(r + "\n" for r in righe).encode("ascii")
    if percorso.endswith(".gz"):
        with open(percorso, "wb") as grezzo:
            with gzip.GzipFile(filename="", mode="wb", fileobj=grezzo, mtime=0,
                               compresslevel=9) as gz:
                gz.write(dati)
    else:
        with open(percorso, "wb") as fh:
            fh.write(dati)
    with open(percorso, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def leggi(percorso: str) -> List[str]:
    import gzip

    with open(percorso, "rb") as fh:
        grezzo = fh.read()
    if grezzo[:2] == b"\x1f\x8b":
        try:
            grezzo = gzip.decompress(grezzo)
        except Exception as ex:  # noqa: BLE001 - zlib.error, OSError, EOFError
            # un .gz rotto non e' una cassetta: il sigillo lo dira'
            return ["<gzip illeggibile: %s>" % type(ex).__name__]
    return [r for r in grezzo.decode("ascii", errors="replace").split("\n") if r]


def verifica_sigillo(righe: Sequence[str]) -> Optional[str]:
    """None se il sigillo torna; altrimenti il motivo."""
    if not righe:
        return "cassetta vuota"
    try:
        ultimo = json.loads(righe[-1])
    except ValueError:
        return "ultima riga illeggibile: sigillo assente o rotto"
    if ultimo.get("chiave") != CHIAVE_SIGILLO or ultimo.get("kind") != "referto":
        return "sigillo assente (ultima riga non e' il sigillo)"
    atteso = (ultimo.get("dati") or {}).get("sha256")
    voci = (ultimo.get("dati") or {}).get("voci")
    calcolato = sigillo(righe[:-1])
    if voci != len(righe) - 1:
        return "sigillo: %s voci dichiarate, %d presenti" % (voci, len(righe) - 1)
    if atteso != calcolato:
        return "sigillo: sha256 dichiarato %s, calcolato %s" % (atteso, calcolato)
    return None
