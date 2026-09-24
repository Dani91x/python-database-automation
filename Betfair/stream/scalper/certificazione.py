# -*- coding: utf-8 -*-
"""CERTIFICAZIONE DELLO SCALPER CALCIO - si comporta come dice la sua bibbia?

Non si misura se GUADAGNA: si misura se **si comporta come e' progettato**,
giro per giro, sui prezzi veri di una partita registrata
(`PROCESSO_STANDARD_BOT.md` gradino 3), con il SERVIZIO DI PRODUZIONE intero
(`scalper_session.run_session`: parametri, client, heartbeat, stop, cap
globale, fine vita, crash) e la strategia vera (`ScalperStrategy`).

LE FONTI DI VERITA': `Betfair/stream/scalper/BIBBIA_SCALPER_CALCIO.md`,
`SCALPER_BOT_DOSSIER.md`, i docstring del servizio (`scalper_session.py`) e la
migrazione `migrations/scalper_bot.sql`, letti insieme a
`PROCESSO_STANDARD_BOT.md` par.6 (copertura) e par.7 (catalogo degli errori).

OGNI CONTROLLO DICHIARA `quando=` HA DAVVERO UN CASO: 'zero violazioni' su un
controllo mai sollecitato non vuol dire 'sano', vuol dire 'non lo so' (par.6.7).

LE FAMIGLIE, e il punto del catalogo par.7 che ognuna difende

  B. CONDOTTA della strategia (bibbia/dossier; par.6.3, par.6.4, par.6.6)
     B1 nessun ingresso quando le aperture sono vietate (par.7.17, par.6.3 bot fermo)
     B2 nessuna posizione aperta al fischio (par.6.4, bibbia 'mai aperte al KO')
     B3 ordini legali per la giurisdizione .it (par.6.4 minimi, par.7.14)
     B4 stake d'ingresso = stake del control (par.6.3 modalita', par.7.24)
     B5 esposizione per selezione dentro il tetto della sessione (par.6.6, par.7.11)
     B6 tetto transazioni/ora sugli ingressi (par.6.6)
  K. CONSAPEVOLEZZA DELL'ORDINE contro il mercato (par.7.36, obbligatoria)
     K1 ordine seguito esiste a mercato (par.7.4, par.7.7)
     K2 rifiuto letto (par.7.2)
     K3 stato come Enum (par.7.10)
     K4 posizione creduta viva ha un ordine vivo o dell'abbinato (par.7.4)
     K5 nessuna esposizione abbinata senza padrone (par.7.4, par.6.4)
     K6 ciclo dichiarato chiuso senza ordini vivi (par.7.7, par.6.4)
     K7 il `locked` contabilizzato = worst-case vero dagli abbinati (par.7.3)
  S. SERVIZIO di sessione (par.6.3, par.6.5)
     S1 scritture di `scalper_control` dentro i CHECK della migrazione (par.7.18)
     S2 stop (UI, kill-switch, fine vita, cap globale) -> force-flat su tutte
        le strategie entro un heartbeat (par.6.3, par.7.34)
     S3 a sessione chiusa nulla di vivo a mercato e posizione piatta (par.6.4)
     S4 stato finale coerente con la causa della fine (bug 3 del 15/07)
     S5 heartbeat e stats scritti alla cadenza del servizio (par.6.5, par.7.20, par.7.23)
     S6 paper = live: stessa strategia, client diverso SOLO per paper_trade
        (par.4, par.7.14, par.7.25, par.7.26)
     S7 dopo un riavvio la posizione della sessione morta e' governata o
        dichiarata (par.6.3 riavvio, par.7.19)
  P. PERSISTENZA e UI (par.6.5)
     P1 lo specchio `betfair_live_orders` porta i campi che la UI mostra
     P2 lo specchio non dichiara piu' abbinato di quanto dica il mercato (par.7.8)

!! LE CHIAVI SI LEGGONO DAL VERO: gli stati dello slot sono le costanti di
`scalper_bot` (IDLE, QUOTING, ...), gli stati ammessi di `scalper_control` sono
quelli del CHECK di `migrations/scalper_bot.sql`, gli stati degli ordini sono
l'Enum `OrderStatus` di flumine letto con `.value` (difetto 10 del catalogo).

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import scalper_bot as SB

# ---------------------------------------------------------------------------
# costanti LETTE dal codice di produzione (mai riscritte)
# ---------------------------------------------------------------------------
STATI_SLOT = frozenset({SB.IDLE, SB.QUOTING, SB.QUOTING2, SB.CANCELLING,
                        SB.LOCKING, SB.FLATTENING, SB.DONE})
STATI_SLOT_VIVI = frozenset({SB.QUOTING, SB.QUOTING2, SB.CANCELLING,
                             SB.LOCKING, SB.FLATTENING})
STATI_SLOT_CHIUSI = frozenset({SB.IDLE, SB.DONE})

# gli stati "vivi" di un ordine per lo scalper (`ScalperStrategy._has_live`):
# EXECUTABLE e PENDING, letti dall'Enum
STATI_ORDINE_VIVI = frozenset(s.value for s in (
    SB.OrderStatus.EXECUTABLE, SB.OrderStatus.PENDING))
STATO_VIOLAZIONE = SB.OrderStatus.VIOLATION.value
STATO_CANCELLING = SB.OrderStatus.CANCELLING.value

# il CHECK della migrazione `migrations/scalper_bot.sql` (tabella scalper_control)
STATI_CONTROL_AMMESSI = frozenset({"requested", "arming", "armed", "running",
                                   "stopping", "stopped", "done", "error"})
MODI_CONTROL_AMMESSI = frozenset({"maker", "bias", "both"})

# minimi di giurisdizione .it: quelli che la strategia applica
# (`ScalperStrategy._side_min`: BACK 2,00 / LAY 0,50) e i PARK legali di
# `_place_exact` (size 2,00 a BACK 1000 / LAY 1.01)
MINIMO_IT = {"BACK": SB.ScalperStrategy._side_min("BACK"),
             "LAY": SB.ScalperStrategy._side_min("LAY")}
PASSO_IT = 0.5
EPS = 0.011
# quanti giri di fila deve durare una discrepanza credenza/mercato prima di
# diventare una violazione: fra un abbinamento (o un rifiuto) e il giro dopo il
# bot non puo' saperlo, accusarlo sarebbe il falso positivo del controllo (par.7.16)
GIRI_DI_TOLLERANZA = 3


# ---------------------------------------------------------------------------
# il referto
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Violazione:
    codice: str
    regola: str
    dettaglio: str
    quando: str = ""

    def __str__(self) -> str:
        return "%s [%s] %s -> %s" % (self.codice, self.quando, self.regola,
                                     self.dettaglio)


@dataclass
class Osservazione:
    """TUTTO cio' che e' successo in UN giro, copiato da oggetti di produzione:
    il blotter di flumine, lo stato in RAM della strategia (`_slots`), le
    attivita' emesse col suo `event_sink`, le righe che il servizio ha scritto
    nel DB finto (colonne vere), le righe dello specchio vero."""

    scenario: str = "base"
    quando: str = ""
    ms: int = 0                                    # orologio di mercato (ms)
    modalita: str = "live"                         # paper | live
    inplay: bool = False
    stato_mercato: str = ""
    ko_ms: Optional[float] = None
    stake: float = 0.0
    cap_esposizione: Optional[float] = None
    # divieti d'ingresso ATTIVI e da quando (ms): nome -> ms d'inizio
    divieti: Dict[str, int] = field(default_factory=dict)
    # gli ordini VERI del bot: tutti quelli dei blotter dei mercati della
    # sessione + quelli che il bot tiene in mano e che il blotter non conosce
    ordini: List[Dict[str, Any]] = field(default_factory=list)
    # cio' che il BOT CREDE, una riga per slot (vedi `credenze`)
    credenze: List[Dict[str, Any]] = field(default_factory=list)
    # id degli ordini comparsi IN QUESTO GIRO
    ordini_nuovi: set = field(default_factory=set)
    # (kind, payload) emessi dal bot in questo giro
    attivita: List[Tuple[str, Dict[str, Any]]] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    specchio: List[Dict[str, Any]] = field(default_factory=list)
    # esposizione abbinata per (market_id, selection_id): (se vince, se perde)
    esposizioni: Dict[Tuple[str, int], Tuple[float, float]] = field(default_factory=dict)
    # parametri della strategia armata (per B6)
    max_txn_hour: int = 0
    # ingressi piazzati nell'ultima ora di MERCATO (per B6)
    ingressi_ultima_ora: int = 0
    # chiusure di ciclo avvenute in questo giro, ognuna con gli ordini dello
    # slot fotografati all'istante (vedi `ChiusuraCiclo`)
    chiusure_ciclo: List[Dict[str, Any]] = field(default_factory=list)
    # ---- servizio
    scritture_control: List[Dict[str, Any]] = field(default_factory=list)
    stop_richiesto_ms: Optional[int] = None        # quando lo stop e' nato
    stop_causa: str = ""
    force_flat: bool = False
    force_flat_ms: Optional[int] = None
    sessione_viva: bool = True
    stato_finale: Optional[str] = None
    fine_sessione: bool = False
    dichiarato_non_flat: bool = False
    heartbeat_ms: List[int] = field(default_factory=list)
    heartbeat_cadenza_s: float = 5.0
    # buchi VERI della registrazione (nessun book di NESSUN mercato della
    # sessione, coppie inizio/fine ms): il replay passa il turno alla
    # sessione SOLO quando un book arriva (`_Orologio.al_book`), quindi un
    # silenzio della registrazione ritarda il heartbeat nel replay anche se
    # in produzione il thread dorme sull'orologio REALE, indipendente dal
    # flusso di flumine (S5 li scomputa, non li ignora: difetto 24/09)
    buchi_registrazione_ms: List[Tuple[int, int]] = field(default_factory=list)
    running_da_ms: Optional[int] = None
    parita: Optional[Dict[str, Any]] = None
    orfani_dopo_riavvio: Optional[List[Dict[str, Any]]] = None
    allarmi: List[Dict[str, Any]] = field(default_factory=list)

    def attivita_di(self, kind: str) -> List[Dict[str, Any]]:
        return [p for k, p in self.attivita if k == kind]


Controllo = Callable[[Osservazione], Optional[str]]
_REGISTRO: List[Tuple[str, str]] = []
_FUNZIONI: Dict[str, Controllo] = {}
_QUANDO: Dict[str, Optional[Controllo]] = {}
# i controlli che accusano solo se la discrepanza DURA (vedi GIRI_DI_TOLLERANZA)
_PERSISTENTI: set = set()


def _controllo(codice: str, regola: str, quando: Optional[Controllo] = None,
               persistente: bool = False):
    def _reg(fn: Controllo) -> Controllo:
        _REGISTRO.append((codice, regola))
        _FUNZIONI[codice] = fn
        _QUANDO[codice] = quando
        if persistente:
            _PERSISTENTI.add(codice)
        return fn

    return _reg


# ---------------------------------------------------------------------------
# leggere un ordine di flumine SEMPRE nello stesso modo
# ---------------------------------------------------------------------------
def _f(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def stato_ordine(ordine: Any) -> Optional[str]:
    """`order.status` e' un Enum: si legge `.value` (difetto 10)."""
    st = getattr(ordine, "status", None)
    if st is None:
        return None
    v = getattr(st, "value", None)
    if v is not None:
        return str(v)
    n = getattr(st, "name", None)
    return str(n) if n is not None else str(st)


def riga_ordine(ordine: Any, in_blotter: bool = True) -> Dict[str, Any]:
    """Un ordine di flumine -> chiavi snake_case come lo specchio di
    produzione (`LiveTradingStrategy._order_row`): una grafia diversa dal vero
    nei controlli e' impossibile (difetto 1)."""
    ot = getattr(ordine, "order_type", None)
    side = getattr(ordine, "side", None)
    creato = getattr(ordine, "date_time_created", None)
    ms_creato = None
    if creato is not None and callable(getattr(creato, "timestamp", None)):
        try:
            # flumine timbra gli ordini col `publish_time` del book, che e' un
            # datetime NAIVE in UTC: `.timestamp()` lo leggerebbe come ora
            # LOCALE (due ore di errore in estate). Si dichiara UTC, come fa lo
            # scalper per il market_time (`_ko_epoch_ms`).
            if getattr(creato, "tzinfo", None) is None:
                from datetime import timezone as _tz

                creato = creato.replace(tzinfo=_tz.utc)
            ms_creato = int(creato.timestamp() * 1000)
        except (TypeError, ValueError, OSError, OverflowError):
            ms_creato = None
    # un ordine SOSTITUTO (replace di flumine: park-trim-replace dei submin)
    # nasce dentro flumine con la size residua dell'ordine che sostituisce, e
    # Betfair la accetta perche' un replace non e' un piazzamento nuovo. Lo
    # scalper crea un Trade per ogni `_place`: un ordine che non e' il primo
    # del suo Trade e' un sostituto.
    trade = getattr(ordine, "trade", None)
    ordini_trade = list(getattr(trade, "orders", None) or [])
    sostituto = bool(ordini_trade) and ordini_trade[0] is not ordine
    return {
        "order_id": str(getattr(ordine, "id", "") or ""),
        "bet_id": getattr(ordine, "bet_id", None),
        "status": stato_ordine(ordine),
        "side": side.upper() if isinstance(side, str) else side,
        "selection_id": getattr(ordine, "selection_id", None),
        "market_id": getattr(ordine, "market_id", None),
        "price": _f(getattr(ot, "price", None)) if ot is not None else None,
        "size": _f(getattr(ot, "size", None)) if ot is not None else None,
        "persistence": getattr(ot, "persistence_type", None) if ot is not None else None,
        "size_matched": _f(getattr(ordine, "size_matched", None)) or 0.0,
        "size_remaining": _f(getattr(ordine, "size_remaining", None)) or 0.0,
        "average_price_matched": _f(getattr(ordine, "average_price_matched", None)) or 0.0,
        "in_blotter": bool(in_blotter),
        "creato_ms": ms_creato,
        "sostituto": sostituto,
    }


def _vivo(r: Dict[str, Any]) -> bool:
    return str(r.get("status") or "") in STATI_ORDINE_VIVI \
        and float(r.get("size_remaining") or 0.0) > 1e-9


def _rifiutato(r: Dict[str, Any]) -> bool:
    """Rifiutato: stato `Violation` (un trading control di flumine o Betfair
    lo ha bocciato) oppure mai nel blotter e mai partito."""
    st = r.get("status")
    return str(st) == STATO_VIOLAZIONE or (not r.get("in_blotter") and st is None)


def _ids(ordini: Sequence[Any]) -> set:
    return {str(getattr(o, "id", "") or "") for o in ordini if o is not None}


# ---------------------------------------------------------------------------
# CIO' CHE IL BOT CREDE - lo stato VERO in RAM (`ScalperStrategy._slots`)
# ---------------------------------------------------------------------------
def tolleranza_slot(slot: Any) -> float:
    """La tolleranza che il BOT dichiara per l'esposizione residua di uno slot.

    E' quella del suo monitor DONE (`scalper_bot.py`, ramo C e ramo A):
    0,02 di norma; `max(0.30, residual_accepted + 0.02)` se ha ACCETTATO un
    residuo non piazzabile (`residual_ok`). Pretendere lo zero accuserebbe il
    bot di una cosa che la sua spec gli concede (falso positivo, par.7.16)."""
    if getattr(slot, "residual_ok", False):
        return max(0.30, float(getattr(slot, "residual_accepted", 0.0) or 0.0) + 0.02)
    return 0.02


def credenze(strat: Any) -> List[Dict[str, Any]]:
    """Una riga per slot `(market_id, selection_id)` dello scalper.

    ingressi = entry / entry_back / entry_lay / next_entry
    uscite   = close + flatten_orders (dove `_track` mette OGNI ordine piazzato
               con lo slot: chiusure, scratch, presize, flatten, park submin)
    """
    out: List[Dict[str, Any]] = []
    if strat is None:
        return out
    for (mid, sel), slot in dict(getattr(strat, "_slots", {}) or {}).items():
        ingressi = [o for o in (getattr(slot, "entry", None),
                                getattr(slot, "entry_back", None),
                                getattr(slot, "entry_lay", None),
                                getattr(slot, "next_entry", None)) if o is not None]
        uscite = [o for o in [getattr(slot, "close", None)] if o is not None]
        for o in list(getattr(slot, "flatten_orders", None) or []):
            if o is not None and all(o is not u for u in uscite):
                uscite.append(o)
        for e in list(getattr(slot, "submins", None) or []):
            o = e.get("order") if isinstance(e, dict) else None
            if o is not None and all(o is not u for u in uscite):
                uscite.append(o)
        out.append({
            "chiave": (str(mid), int(sel)),
            "stato": str(getattr(slot, "status", "")),
            "ingressi": ingressi,
            "uscite": uscite,
            "tolleranza": tolleranza_slot(slot),
            "cicli": int(getattr(slot, "cycles", 0) or 0),
            "residual_ok": bool(getattr(slot, "residual_ok", False)),
        })
    return out


def ordini_seguiti(c: Dict[str, Any]) -> List[Any]:
    return list(c.get("ingressi") or []) + list(c.get("uscite") or [])


def messaggio_dichiara_non_flat(msg: Any) -> bool:
    """Il servizio ha DICHIARATO una posizione non piatta? (S3)

    Le dichiarazioni riconosciute: 'posizione NON flat' (stop o fine vita dopo
    30 s; D7 24/09: residuo accettato dal bot e stato finale della sessione) e
    l'allarme del crash ('CRASH thread flumine'). Spostata qui dal banco
    (`tools/replay_registrazioni.py`) il 24/09 SENZA cambiarne la regola, perche'
    il test la possa provare."""
    m = str(msg or "")
    return "NON flat" in m or "CRASH thread flumine" in m


def esposizione(righe: Sequence[Dict[str, Any]]) -> Tuple[float, float]:
    """(se vince, se perde) sugli ABBINATI delle righe, col prezzo medio VERO."""
    w = l = 0.0
    for r in righe:
        m = float(r.get("size_matched") or 0.0)
        p = float(r.get("average_price_matched") or 0.0)
        if m <= 0 or p <= 1.0:
            continue
        if str(r.get("side") or "").upper() == "BACK":
            w += m * (p - 1.0)
            l -= m
        elif str(r.get("side") or "").upper() == "LAY":
            w -= m * (p - 1.0)
            l += m
    return w, l


def worst_case_vero(ordini: Sequence[Any]) -> Optional[float]:
    """Il worst-case (min fra se-vince e se-perde) degli ordini ABBINATI,
    calcolato QUI dai campi veri di flumine (`size_matched`,
    `average_price_matched`), senza passare dal codice del bot. Lo stesso
    oggetto passato due volte conta una volta (come fa il bot)."""
    visti: set = set()
    righe = []
    for o in ordini:
        if o is None or id(o) in visti:
            continue
        visti.add(id(o))
        righe.append(riga_ordine(o))
    if not any(float(r.get("size_matched") or 0.0) > 0 for r in righe):
        return None
    w, l = esposizione(righe)
    return min(w, l)


# ---------------------------------------------------------------------------
# QUANDO ognuno ha un caso
# ---------------------------------------------------------------------------
def _q_ordini(o: Osservazione) -> bool:
    return bool(o.ordini)


def _q_nuovi(o: Osservazione) -> bool:
    return bool(o.ordini_nuovi)


def _q_ingressi_nuovi(o: Osservazione) -> bool:
    return bool(_ingressi_nuovi(o))


def _q_divieti(o: Osservazione) -> bool:
    return bool(o.divieti)


def _q_inplay(o: Osservazione) -> bool:
    return bool(o.inplay) and o.sessione_viva


def _q_credenze_vive(o: Osservazione) -> bool:
    return any(str(c.get("stato") or "") in STATI_SLOT_VIVI for c in o.credenze)


def _q_credenze(o: Osservazione) -> bool:
    return bool(o.credenze)


def _q_rifiuti(o: Osservazione) -> bool:
    return any(_rifiutato(r) for r in o.ordini)


def _q_esposizione(o: Osservazione) -> bool:
    return any(abs(w - l) > EPS for w, l in (o.esposizioni or {}).values())


def _q_chiusi_con_ordini(o: Osservazione) -> bool:
    return any(str(c.get("stato") or "") in STATI_SLOT_CHIUSI for c in o.credenze) \
        and bool(o.ordini)


def _q_chiusure_ciclo(o: Osservazione) -> bool:
    return bool(o.chiusure_ciclo)


def _q_cap(o: Osservazione) -> bool:
    return o.cap_esposizione is not None and bool(o.esposizioni)


def _q_txn(o: Osservazione) -> bool:
    return o.max_txn_hour > 0 and bool(_ingressi_nuovi(o))


def _q_control(o: Osservazione) -> bool:
    return bool(o.scritture_control)


def _q_stop(o: Osservazione) -> bool:
    return o.stop_richiesto_ms is not None


def _q_fine(o: Osservazione) -> bool:
    return bool(o.fine_sessione)


def _q_running(o: Osservazione) -> bool:
    return o.running_da_ms is not None and bool(o.heartbeat_ms)


def _q_parita(o: Osservazione) -> bool:
    return o.parita is not None


def _q_riavvio(o: Osservazione) -> bool:
    return o.orfani_dopo_riavvio is not None


def _q_specchio(o: Osservazione) -> bool:
    return bool(o.specchio)


def _ingressi_nuovi(o: Osservazione) -> List[Dict[str, Any]]:
    ids_ingresso: set = set()
    for c in o.credenze:
        ids_ingresso |= _ids(c.get("ingressi") or ())
    return [r for r in o.ordini
            if r.get("order_id") in (o.ordini_nuovi or set())
            and r.get("order_id") in ids_ingresso]


# ===========================================================================
# FAMIGLIA B - la CONDOTTA
# ===========================================================================
@_controllo("B1", "nessun INGRESSO nuovo quando le aperture sono vietate: "
                  "force-flat (stop UI, kill-switch, loss cap, fine vita), "
                  "entro `entry_stop_before_s` dal KO, in gioco con "
                  "`allow_inplay=False` (bibbia; PROCESSO par.6.3 bot fermo)",
            quando=_q_divieti)
def _b1(o: Osservazione) -> Optional[str]:
    for r in _ingressi_nuovi(o):
        creato = r.get("creato_ms")
        if creato is None:
            continue
        for nome, dal in sorted(o.divieti.items()):
            # il divieto 'in gioco' vale per IL SUO mercato: ogni mercato passa
            # in gioco col suo book, e lo scalper guarda l'`inplay` del book
            # che sta processando
            if nome.startswith("in_gioco@") and nome.split("@", 1)[1] != str(r.get("market_id")):
                continue
            # si accusa SOLO un ingresso nato DOPO l'inizio del divieto: uno
            # nato prima e' legittimo (il divieto lo deve far CANCELLARE, e lo
            # giudicano K6/B2), e questo e' l'unico modo di non accusare il bot
            # di una decisione presa quando il divieto non c'era (par.7.16)
            if creato > dal + 1:
                return ("ingresso %s %s %s @%s per %s creato a %d ms, con il "
                        "divieto '%s' attivo da %d ms"
                        % (r.get("order_id"), r.get("side"), r.get("selection_id"),
                           r.get("price"), r.get("size"), creato, nome, dal))
    return None


@_controllo("B2", "al FISCHIO nessuna posizione aperta: dopo il KO ogni "
                  "selezione ha l'esposizione abbinata piatta (entro la "
                  "tolleranza che il bot dichiara) e nessun ingresso vivo "
                  "(`flatten_before_s`, bibbia 'mai posizioni aperte al KO')",
            quando=_q_inplay, persistente=True)
def _b2(o: Osservazione) -> Optional[str]:
    toll = {c.get("chiave"): float(c.get("tolleranza") or 0.02) for c in o.credenze}
    for chiave, (w, l) in sorted((o.esposizioni or {}).items()):
        tol = max(EPS, toll.get(chiave, 0.02))
        if abs(w - l) > tol + EPS:
            return ("in gioco la selezione %s ha un'esposizione abbinata "
                    "sbilanciata di %.2f (se vince %.2f, se perde %.2f), oltre "
                    "la tolleranza %.2f del bot" % (chiave, abs(w - l), w, l, tol))
    ids_ingresso: set = set()
    for c in o.credenze:
        ids_ingresso |= _ids(c.get("ingressi") or ())
    for r in o.ordini:
        if _vivo(r) and r.get("order_id") in ids_ingresso:
            return ("in gioco l'ingresso %s %s @%s e' ancora VIVO per %s"
                    % (r.get("order_id"), r.get("side"), r.get("price"),
                       r.get("size_remaining")))
    return None


def _legale_it(r: Dict[str, Any]) -> Optional[str]:
    size, side, prezzo = r.get("size"), str(r.get("side") or "").upper(), r.get("price")
    if prezzo is not None and (prezzo < 1.01 - 1e-9 or prezzo > 1000.0 + 1e-9):
        return "prezzo %s fuori dalla ladder" % prezzo
    if size is None or side not in MINIMO_IT:
        return None
    if size + 1e-9 < MINIMO_IT[side]:
        return "size %s sotto il minimo .it del lato %s (%s)" % (size, side, MINIMO_IT[side])
    multiplo = size / PASSO_IT
    if abs(multiplo - round(multiplo)) > 1e-6:
        return "size %s non multipla di %.2f (INVALID_BET_SIZE su .it)" % (size, PASSO_IT)
    return None


@_controllo("B3", "ogni ordine chiesto e' LEGALE su .it: prezzo nella ladder, "
                  "size multipla di 0,50 e non sotto il minimo del lato "
                  "(BACK 2,00 / LAY 0,50), park compresi. Vale in PAPER e in "
                  "LIVE: stessi parametri (PROCESSO par.6.4 minimi; par.7.14)",
            quando=_q_nuovi)
def _b3(o: Osservazione) -> Optional[str]:
    for r in o.ordini:
        if r.get("order_id") not in (o.ordini_nuovi or set()):
            continue
        if r.get("sostituto"):
            continue          # replace: la size e' quella dell'ordine sostituito
        motivo = _legale_it(r)
        if motivo:
            return ("ordine %s %s %s @%s per %s: %s"
                    % (r.get("order_id"), r.get("side"), r.get("selection_id"),
                       r.get("price"), r.get("size"), motivo))
    return None


@_controllo("B4", "lo stake d'ingresso e' quello del control (mai piu' di "
                  "quanto l'utente ha acceso): `run_session` scrive "
                  "`params['stake']` da `scalper_control.stake`",
            quando=_q_ingressi_nuovi)
def _b4(o: Osservazione) -> Optional[str]:
    if o.stake <= 0:
        return None
    for r in _ingressi_nuovi(o):
        s = r.get("size")
        if s is not None and s > o.stake + EPS:
            return ("ingresso %s per %s con stake del control %s"
                    % (r.get("order_id"), s, o.stake))
    return None


@_controllo("B5", "l'esposizione abbinata per selezione non supera il tetto "
                  "che la sessione passa alla strategia "
                  "(`max_selection_exposure` = stake x (price_max-1) x 2): i "
                  "tetti di flumine sono aperti, quello del bot no (par.6.6)",
            quando=_q_cap)
def _b5(o: Osservazione) -> Optional[str]:
    cap = o.cap_esposizione
    if cap is None:
        return None
    for chiave, (w, l) in sorted((o.esposizioni or {}).items()):
        peggio = -min(w, l)
        if peggio > cap + EPS:
            return ("perdita possibile %.2f su %s contro il tetto %.2f della sessione"
                    % (peggio, chiave, cap))
    return None


@_controllo("B6", "tetto transazioni/ora (`max_txn_hour`): oltre il budget "
                  "nessun NUOVO ingresso (le chiusure passano sempre); l'ora e' "
                  "quella di MERCATO (par.6.6)",
            quando=_q_txn)
def _b6(o: Osservazione) -> Optional[str]:
    if o.max_txn_hour > 0 and o.ingressi_ultima_ora > o.max_txn_hour:
        return ("%d ingressi nell'ultima ora di mercato contro un tetto di %d "
                "transazioni" % (o.ingressi_ultima_ora, o.max_txn_hour))
    return None


# ===========================================================================
# FAMIGLIA K - la CONSAPEVOLEZZA DELL'ORDINE (par.7 punto 36)
# ===========================================================================
@_controllo("K1", "ogni ordine che il bot STA SEGUENDO in una posizione viva "
                  "esiste davvero a mercato (nel blotter): un ordine in mano al "
                  "bot che il mercato non conosce e' una posizione che nessuno "
                  "governa (difetti 4 e 7 del 15/09)",
            quando=_q_credenze_vive, persistente=True)
def _k1(o: Osservazione) -> Optional[str]:
    a_mercato = {r.get("order_id") for r in o.ordini if r.get("in_blotter")}
    for c in o.credenze:
        if str(c.get("stato") or "") not in STATI_SLOT_VIVI:
            continue
        for oid in sorted(_ids(ordini_seguiti(c))):
            if oid and oid not in a_mercato:
                return ("lo slot %s e' '%s' e segue l'ordine %s, che a mercato "
                        "non esiste" % (c.get("chiave"), c.get("stato"), oid))
    return None


@_controllo("K2", "un ordine RIFIUTATO (place_order ha risposto False, stato "
                  "Violation) non lascia il bot con una posizione creduta viva "
                  "che poggia SOLO su ordini rifiutati (difetto 2 del 15/09: "
                  "`res.ok` mai letto)",
            quando=_q_rifiuti, persistente=True)
def _k2(o: Osservazione) -> Optional[str]:
    rifiutati = {r.get("order_id") for r in o.ordini if _rifiutato(r)}
    if not rifiutati:
        return None
    per_id = {r.get("order_id"): r for r in o.ordini}
    for c in o.credenze:
        if str(c.get("stato") or "") not in STATI_SLOT_VIVI:
            continue
        seguiti = _ids(ordini_seguiti(c))
        if not (seguiti & rifiutati):
            continue
        sani = [i for i in seguiti if i not in rifiutati and i in per_id
                and (_vivo(per_id[i]) or float(per_id[i].get("size_matched") or 0) > 0)]
        if not sani:
            return ("lo slot %s e' '%s' ma poggia solo su ordini rifiutati (%s): "
                    "il bot crede di avere a mercato qualcosa che non e' mai partito"
                    % (c.get("chiave"), c.get("stato"), sorted(seguiti & rifiutati)))
    return None


@_controllo("K3", "lo stato di ogni ordine si legge come Enum `OrderStatus` "
                  "(`.value`): `str(stato)` da' 'OrderStatus.EXECUTABLE' e "
                  "nessun ordine risulta vivo (catalogo par.7 punto 10)",
            quando=_q_ordini)
def _k3(o: Osservazione) -> Optional[str]:
    noti = {s.value for s in SB.OrderStatus}
    for r in o.ordini:
        st = r.get("status")
        if st is None:
            continue
        if str(st).startswith("OrderStatus."):
            return ("l'ordine %s espone lo stato '%s': Enum letto come stringa"
                    % (r.get("order_id"), st))
        if str(st) not in noti:
            return ("l'ordine %s ha lo stato '%s', sconosciuto all'Enum di flumine"
                    % (r.get("order_id"), st))
    return None


@_controllo("K4", "uno slot che il bot crede VIVO ha almeno un ordine vivo o "
                  "dell'abbinato sulla sua selezione: altrimenti sorveglia il "
                  "nulla (difetto 4 del 15/09)",
            quando=_q_credenze_vive, persistente=True)
def _k4(o: Osservazione) -> Optional[str]:
    vivi: Dict[Tuple[str, int], int] = {}
    abbinati: Dict[Tuple[str, int], float] = {}
    for r in o.ordini:
        try:
            k = (str(r.get("market_id") or ""), int(r.get("selection_id") or 0))
        except (TypeError, ValueError):
            continue
        if _vivo(r):
            vivi[k] = vivi.get(k, 0) + 1
        abbinati[k] = abbinati.get(k, 0.0) + float(r.get("size_matched") or 0.0)
    for c in o.credenze:
        if str(c.get("stato") or "") not in STATI_SLOT_VIVI:
            continue
        k = c.get("chiave")
        # CANCELLING senza nulla di vivo ne' di abbinato e' esattamente il caso
        # che il bot chiude al giro dopo (`_handle_cancelling` -> _reset): la
        # persistenza lo copre
        if vivi.get(k, 0) > 0 or abbinati.get(k, 0.0) > 0.009:
            continue
        return ("lo slot %s e' '%s' ma su quella selezione non c'e' nessun "
                "ordine vivo ne' un centesimo di abbinato" % (k, c.get("stato")))
    return None


@_controllo("K5", "nessuna ESPOSIZIONE abbinata resta sbilanciata su una "
                  "selezione il cui slot e' dichiarato chiuso (IDLE/DONE), "
                  "oltre la tolleranza che il bot stesso dichiara: nessuna "
                  "posizione fantasma (PROCESSO par.6.4 'mai una posizione "
                  "scoperta non dichiarata')",
            quando=_q_esposizione, persistente=True)
def _k5(o: Osservazione) -> Optional[str]:
    per_chiave = {c.get("chiave"): c for c in o.credenze}
    for chiave, (w, l) in sorted((o.esposizioni or {}).items()):
        c = per_chiave.get(chiave)
        if c is not None and str(c.get("stato") or "") in STATI_SLOT_VIVI:
            continue                 # uno slot vivo la governa
        tol = float((c or {}).get("tolleranza") or 0.02)
        # la tolleranza e' PER CICLO: ogni ciclo chiuso puo' lasciare fino a
        # 0,02 (il monitor DONE del bot); i residui ACCETTATI sono gia' dentro
        # `tolleranza_slot` per il ciclo corrente
        tol_tot = max(EPS, tol + 0.02 * max(0, int((c or {}).get("cicli") or 0)))
        if abs(w - l) <= tol_tot + EPS:
            continue
        return ("la selezione %s ha un'esposizione abbinata sbilanciata di %.2f "
                "(se vince %.2f, se perde %.2f) e il bot la crede '%s': i soldi "
                "sono a mercato senza padrone"
                % (chiave, abs(w - l), w, l, (c or {}).get("stato", "nessuno slot")))
    return None


@_controllo("K6", "quando il bot dichiara uno slot CHIUSO (IDLE/DONE) non resta "
                  "nessun ordine VIVO di quella selezione sul book (un cancel "
                  "in viaggio, `Cancelling`, e' governato e non conta)",
            quando=_q_chiusi_con_ordini, persistente=True)
def _k6(o: Osservazione) -> Optional[str]:
    chiusi = {c.get("chiave") for c in o.credenze
              if str(c.get("stato") or "") in STATI_SLOT_CHIUSI}
    for r in o.ordini:
        if not _vivo(r) or not r.get("in_blotter"):
            continue
        try:
            k = (str(r.get("market_id") or ""), int(r.get("selection_id") or 0))
        except (TypeError, ValueError):
            continue
        if k not in chiusi:
            continue
        return ("lo slot %s e' dichiarato chiuso ma l'ordine %s %s @%s e' ancora "
                "'%s' sul book per %s"
                % (k, r.get("order_id"), r.get("side"), r.get("price"),
                   r.get("status"), r.get("size_remaining")))
    return None


@_controllo("K7", "a ogni ciclo chiuso il `locked` che il bot contabilizza "
                  "(pnl_locked, loss cap, missione) e' il worst-case VERO degli "
                  "ordini abbinati dello slot, letto da `size_matched` e "
                  "`average_price_matched` (difetto 3 del 15/09: prezzo medio "
                  "letto da un campo sbagliato)",
            quando=_q_chiusure_ciclo)
def _k7(o: Osservazione) -> Optional[str]:
    for ch in o.chiusure_ciclo:
        locked = _f(ch.get("locked"))
        vero = _f(ch.get("worst_case_vero"))
        if locked is None or vero is None:
            continue
        # il ramo "scalp" contabilizza `net_lose` con |nw-nl| <= 0,02: il
        # worst-case vero puo' differire al piu' di quei 2 centesimi
        if abs(locked - vero) > 0.02 + EPS:
            return ("ciclo '%s' su %s: il bot contabilizza locked %.4f, gli "
                    "abbinati veri dicono %.4f"
                    % (ch.get("kind"), ch.get("chiave"), locked, vero))
    return None


# ===========================================================================
# FAMIGLIA S - il SERVIZIO di sessione (par.6.3)
# ===========================================================================
@_controllo("S1", "ogni scrittura del servizio su `scalper_control` rispetta i "
                  "CHECK di `migrations/scalper_bot.sql` (status, mode, stake "
                  "2-500): un upsert rifiutato dal DB lascia la UI cieca "
                  "(catalogo par.7 punto 18)",
            quando=_q_control)
def _s1(o: Osservazione) -> Optional[str]:
    for w in o.scritture_control:
        campi = w.get("campi") or {}
        st = campi.get("status")
        if st is not None and str(st) not in STATI_CONTROL_AMMESSI:
            return "status '%s' fuori dal CHECK di scalper_control" % st
        mo = campi.get("mode")
        if mo is not None and str(mo) not in MODI_CONTROL_AMMESSI:
            return "mode '%s' fuori dal CHECK di scalper_control" % mo
        sk = _f(campi.get("stake"))
        if campi.get("stake") is not None and (sk is None or sk < 2 or sk > 500):
            return "stake %s fuori dal CHECK [2,500]" % campi.get("stake")
    return None


@_controllo("S2", "uno STOP (UI 'stopping', kill-switch, fine vita, cap "
                  "globale) arma il force-flat della strategia entro un "
                  "heartbeat del servizio (HEARTBEAT_S + 1 s di mercato): le "
                  "protezioni girano, le aperture no (par.6.3)",
            quando=_q_stop)
def _s2(o: Osservazione) -> Optional[str]:
    if o.stop_richiesto_ms is None:
        return None
    limite = o.stop_richiesto_ms + int((o.heartbeat_cadenza_s + 1.0) * 1000)
    if o.ms <= limite:
        return None
    if not o.force_flat:
        return ("stop '%s' richiesto a %d ms e a %d ms la strategia non ha "
                "ancora il force-flat armato"
                % (o.stop_causa, o.stop_richiesto_ms, o.ms))
    if o.force_flat_ms is not None and o.force_flat_ms > limite:
        return ("stop '%s' richiesto a %d ms, force-flat armato solo a %d ms"
                % (o.stop_causa, o.stop_richiesto_ms, o.force_flat_ms))
    return None


@_controllo("S3", "a sessione CHUSA nessun ordine della sessione resta vivo a "
                  "mercato e l'esposizione abbinata e' piatta (tolleranza del "
                  "bot), oppure il servizio lo ha DICHIARATO ('posizione NON "
                  "flat'): in LIVE quegli ordini restano sull'exchange senza "
                  "nessuno che li governi (par.6.4)",
            quando=_q_fine)
def _s3(o: Osservazione) -> Optional[str]:
    if not o.fine_sessione:
        return None
    vivi = [r for r in o.ordini if _vivo(r) and r.get("in_blotter")]
    sbil = [(k, w, l) for k, (w, l) in (o.esposizioni or {}).items()
            if abs(w - l) > 0.30 + EPS]
    if not vivi and not sbil:
        return None
    if o.dichiarato_non_flat:
        return None
    if vivi:
        r = vivi[0]
        return ("sessione chiusa ('%s') con %d ordini vivi a mercato e nessuna "
                "dichiarazione (primo: %s %s @%s per %s)"
                % (o.stato_finale, len(vivi), r.get("order_id"), r.get("side"),
                   r.get("price"), r.get("size_remaining")))
    k, w, l = sbil[0]
    return ("sessione chiusa ('%s') con esposizione sbilanciata su %s (se vince "
            "%.2f, se perde %.2f) e nessuna dichiarazione" % (o.stato_finale, k, w, l))


# causa della fine -> stati finali ammessi (`run_session`, fine del loop)
STATO_FINALE_ATTESO = {
    "ui": {"stopped"},
    "kill-switch": {"done"},
    "fine-vita": {"done"},
    "cap-globale": {"done"},
    "crash": {"error"},
}


@_controllo("S4", "lo stato finale della sessione dice PERCHE' e' finita: "
                  "'stopped' se l'ha fermata l'utente, 'done' a fine vita o "
                  "kill-switch, 'error' se il motore e' morto (mai un 'done' "
                  "silenzioso su un crash: bug 3 del 15/07)",
            quando=_q_fine)
def _s4(o: Osservazione) -> Optional[str]:
    atteso = STATO_FINALE_ATTESO.get(o.stop_causa or "")
    if atteso is None:
        return None
    if str(o.stato_finale or "") not in atteso:
        return ("fine per '%s' ma stato finale '%s' (atteso %s)"
                % (o.stop_causa, o.stato_finale, sorted(atteso)))
    return None


def _sovrapposizione_ms(a: int, b: int, c: int, d: int) -> int:
    """ms in comune fra [a, b) e [c, d)."""
    return max(0, min(b, d) - max(a, c))


def _buco_dentro_ms(buchi: Sequence[Tuple[int, int]], a: int, b: int) -> int:
    """Somma dei ms di [a, b] in cui NESSUN book e' arrivato (silenzio della
    registrazione): il tempo che il replay non poteva far scorrere piu' in
    fretta, qualunque sia la causa del silenzio."""
    return sum(_sovrapposizione_ms(a, b, ga, gb) for ga, gb in buchi)


@_controllo("S5", "mentre la sessione e' 'running' il servizio scrive "
                  "heartbeat_at e stats almeno ogni HEARTBEAT_S (+1 s) di "
                  "mercato EFFETTIVAMENTE trascorso (al netto dei silenzi "
                  "della registrazione, che il replay non puo' scorrere piu' "
                  "in fretta), con le chiavi delle stats della strategia (UI e "
                  "supervisore leggono QUESTE: par.6.5, par.7.20, par.7.23)",
            quando=_q_running)
def _s5(o: Osservazione) -> Optional[str]:
    # si giudica il giro NORMALE della sessione corrente: dopo uno stop il
    # servizio aspetta il flat (fino a 30 s) senza battere, per progetto (il
    # supervisore tollera 60 s: `ORPHAN_HEARTBEAT_S`), e un riavvio fa ripartire
    # il conto (`heartbeat_ms` arriva gia' filtrato dal replay)
    battiti = sorted(o.heartbeat_ms)
    massimo = int((o.heartbeat_cadenza_s + 1.0) * 1000)
    buchi = o.buchi_registrazione_ms or []
    for a, b in zip(battiti, battiti[1:]):
        scarto = (b - a) - _buco_dentro_ms(buchi, a, b)
        if scarto > massimo:
            return ("heartbeat fermo per %d ms di mercato EFFETTIVO (fra %d e "
                    "%d, %d ms sono silenzio della registrazione), la cadenza "
                    "del servizio e' %.0f s"
                    % (scarto, a, b, (b - a) - scarto, o.heartbeat_cadenza_s))
    if (o.sessione_viva and o.stop_richiesto_ms is None and battiti):
        scarto = (o.ms - battiti[-1]) - _buco_dentro_ms(buchi, battiti[-1], o.ms)
        if scarto > massimo:
            return ("ultimo heartbeat %d ms fa di mercato EFFETTIVO, la "
                    "cadenza del servizio e' %.0f s" % (scarto, o.heartbeat_cadenza_s))
    for k in ("orders_placed", "cycles", "pnl_locked"):
        if k not in (o.stats or {}):
            return "le stats scritte non portano la chiave '%s'" % k
    return None


@_controllo("S6", "PAPER = LIVE: armata dallo stesso control, la sessione "
                  "paper e quella live producono la STESSA strategia (parametri "
                  "campo per campo) e un client flumine che differisce SOLO per "
                  "`paper_trade` (par.4; catalogo par.7 punti 14, 25, 26)",
            quando=_q_parita)
def _s6(o: Osservazione) -> Optional[str]:
    p = o.parita or {}
    if p.get("errore"):
        return "parita' non verificabile: %s" % p.get("errore")
    diff = p.get("parametri_diversi") or []
    if diff:
        return "parametri della strategia diversi fra paper e live: %s" % diff[:6]
    cd = p.get("client_diversi") or []
    if cd:
        return "client flumine diverso fra paper e live oltre paper_trade: %s" % cd
    if p.get("paper_trade_paper") is not True or p.get("paper_trade_live") is not False:
        return ("paper_trade non segue dry_run: paper=%s live=%s"
                % (p.get("paper_trade_paper"), p.get("paper_trade_live")))
    return None


@_controllo("S7", "dopo un RIAVVIO della sessione, l'esposizione abbinata e gli "
                  "ordini vivi lasciati dalla sessione morta sono governati "
                  "dalla nuova (una sua credenza li segue) oppure il servizio li "
                  "DICHIARA (allarme): mai una posizione orfana silenziosa "
                  "(PROCESSO par.6.3 riavvio; catalogo par.7 punto 19)",
            quando=_q_riavvio, persistente=True)
def _s7(o: Osservazione) -> Optional[str]:
    orfani = list(o.orfani_dopo_riavvio or [])
    if not orfani:
        return None
    seguiti: set = set()
    for c in o.credenze:
        seguiti |= _ids(ordini_seguiti(c))
    non_governati = [r for r in orfani if r.get("order_id") not in seguiti]
    if not non_governati:
        return None
    dichiarati = any("orfan" in str(a.get("message") or a.get("msg") or "").lower()
                     for a in o.allarmi)
    if dichiarati:
        return None
    r = non_governati[0]
    return ("%d ordini della sessione morta (abbinato o vivo) non governati ne' "
            "dichiarati dalla nuova sessione (primo: %s %s %s @%s abbinato %s, "
            "residuo %s)"
            % (len(non_governati), r.get("order_id"), r.get("side"),
               r.get("selection_id"), r.get("price"), r.get("size_matched"),
               r.get("size_remaining")))


# ===========================================================================
# FAMIGLIA P - la PERSISTENZA e cio' che la UI mostra (par.6.5)
# ===========================================================================
@_controllo("P1", "ogni ordine del bot arriva allo specchio `betfair_live_orders` "
                  "(riga costruita dallo specchio VERO della sessione) con "
                  "chiesto, abbinato, residuo, prezzo medio, stato, ref e "
                  "modalita': sono i campi che la UI mostra (par.6.5)",
            quando=_q_specchio)
def _p1(o: Osservazione) -> Optional[str]:
    obbligatori = ("size", "size_matched", "size_remaining",
                   "average_price_matched", "status", "client_order_ref", "mode")
    for riga in o.specchio:
        mancanti = [k for k in obbligatori if riga.get(k) is None]
        if mancanti:
            return ("la riga di specchio %s non porta %s"
                    % (riga.get("client_order_ref"), ", ".join(mancanti)))
        if str(riga.get("mode") or "") != o.modalita:
            return ("la riga di specchio %s porta mode '%s' in una sessione %s"
                    % (riga.get("client_order_ref"), riga.get("mode"), o.modalita))
    return None


@_controllo("P2", "lo specchio non dichiara MAI un ordine abbinato piu' di "
                  "quanto il mercato dica (nessun fill dedotto: par.7 punto 8)",
            quando=_q_specchio)
def _p2(o: Osservazione) -> Optional[str]:
    per_bet = {str(r.get("bet_id")): r for r in o.ordini if r.get("bet_id")}
    for riga in o.specchio:
        vero = per_bet.get(str(riga.get("bet_id")))
        if vero is None:
            continue
        sm = _f(riga.get("size_matched"))
        if sm is not None and sm > float(vero.get("size_matched") or 0.0) + EPS:
            return ("lo specchio di %s dice abbinato %s, il mercato dice %s"
                    % (riga.get("client_order_ref"), sm, vero.get("size_matched")))
    return None


# ===========================================================================
# il giro completo
# ===========================================================================
class Memoria:
    """La persistenza dei controlli 'persistenti': un controllo accusa solo se
    la stessa discrepanza (stesso testo di dettaglio a meno dei numeri del
    giro) dura GIRI_DI_TOLLERANZA giri di fila."""

    def __init__(self) -> None:
        self._fila: Dict[str, int] = {}

    def conferma(self, codice: str, det: Optional[str]) -> bool:
        if det is None:
            self._fila.pop(codice, None)
            return False
        n = self._fila.get(codice, 0) + 1
        self._fila[codice] = n
        return n == GIRI_DI_TOLLERANZA


def verifica(oss: Osservazione, sollecitati: Optional[Dict[str, int]] = None,
             memoria: Optional[Memoria] = None) -> List[Violazione]:
    out: List[Violazione] = []
    for codice, regola in _REGISTRO:
        quando = _QUANDO.get(codice)
        try:
            if quando is not None and not quando(oss):
                if memoria is not None and codice in _PERSISTENTI:
                    memoria.conferma(codice, None)
                continue
        except Exception as ex:  # noqa: BLE001 - un `quando` rotto E' un referto
            out.append(Violazione("%s-ERRORE" % codice, regola,
                                  "il `quando` e' esploso: %s: %s"
                                  % (type(ex).__name__, ex), oss.quando))
            continue
        if sollecitati is not None:
            sollecitati[codice] = sollecitati.get(codice, 0) + 1
        try:
            det = _FUNZIONI[codice](oss)
        except Exception as ex:  # noqa: BLE001 - un controllo rotto E' un referto
            out.append(Violazione("%s-ERRORE" % codice, regola,
                                  "il controllo e' esploso: %s: %s"
                                  % (type(ex).__name__, ex), oss.quando))
            continue
        if codice in _PERSISTENTI and memoria is not None:
            if memoria.conferma(codice, det):
                out.append(Violazione(codice, regola, det, oss.quando))
            continue
        if det:
            out.append(Violazione(codice, regola, det, oss.quando))
    return out


def elenco_controlli() -> List[Tuple[str, str]]:
    return list(_REGISTRO)


def mai_sollecitati(sollecitati: Dict[str, int]) -> List[Tuple[str, str]]:
    return [(c, r) for c, r in _REGISTRO if not sollecitati.get(c)]


@dataclass
class Referto:
    """Il referto di un evento, con le chiavi che `certifica.py` stampa."""

    event_id: str
    bot: str = "scalper_calcio"
    scenario: str = "base"
    tick: int = 0
    decisioni: int = 0
    azioni: int = 0
    ordini_piazzati: int = 0
    ordini_abbinati: int = 0
    stati_visti: List[str] = field(default_factory=list)
    fasi_viste: List[str] = field(default_factory=list)
    violazioni: List[Violazione] = field(default_factory=list)
    sollecitati: Dict[str, int] = field(default_factory=dict)
    note: List[str] = field(default_factory=list)
    motivi: Dict[str, int] = field(default_factory=dict)
    stats_finali: Dict[str, Any] = field(default_factory=dict)

    @property
    def pulita(self) -> bool:
        return not self.violazioni

    def per_codice(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for v in self.violazioni:
            out[v.codice] = out.get(v.codice, 0) + 1
        return out
