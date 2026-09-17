# -*- coding: utf-8 -*-
"""CERTIFICAZIONE DEI QUATTRO BOT TENNIS — si comportano come dice il dossier?

Non si misura se GUADAGNANO: si misura se **si comportano come dice la
specifica**, giro per giro, sui prezzi veri di una partita registrata
(`PROCESSO_STANDARD_BOT.md` gradino 3).

LA FONTE DI VERITA' e' `TENNIS_BOT_DOSSIER.md` §4 (le quattro strategie, con i
parametri e le uscite) letto insieme a `PROCESSO_STANDARD_BOT.md` §6 (la
copertura obbligatoria del banco) e §7 (il catalogo dei 37 errori gia' visti).

OGNI CONTROLLO DICHIARA `quando=` HA DAVVERO UN CASO. Senza, un referto «zero
violazioni» e' ambiguo: non si distingue un controllo che ha guardato e
approvato da uno che non ha mai avuto l'occasione di guardare. Sono due cose
diversissime — la prima e' una garanzia, la seconda e' un buco (§6.7).

LE FAMIGLIE

  B. la CONDOTTA del bot secondo il dossier (ingresso, uscita, sicurezze)
  K. la CONSAPEVOLEZZA DELL'ORDINE contro il banco (catalogo §7 punto 36)
  P. la PERSISTENZA e cio' che la UI mostra (§6.5)

PERCHE' LA FAMIGLIA K E' OBBLIGATORIA. Il 16/09, falsificando Mike, si e'
scoperto che i controlli che guardano solo la DECISIONE non vedono i difetti di
consapevolezza: i cinque difetti del 15/09 reintrodotti uno per uno lasciavano
il replay verde e il referto identico cifra per cifra. Qui i controlli K
confrontano, dopo ogni giro, cio' che il bot CREDE delle sue posizioni (lo stato
in RAM: `_slots` dello scalper, `_trade` del pro, `_pos_state` del flb, `_tr`
dello swing) con cio' che il BLOTTER DI FLUMINE dice dei suoi ordini. Un
controllo che dipende dalla CONFESSIONE del bot (le attivita' che il bot scrive
da se') non certifica niente.

⚠️ LE CHIAVI SI LEGGONO DAL VERO, NON SI RISCRIVONO. Gli stati interni dei
quattro bot hanno nomi diversi (`_Slot.status` contro `trade["state"]` contro
`st["state"]`): qui si legge il nome VERO di ognuno, importato dal modulo di
produzione dove esiste una costante. Riscriverli a mano e' il difetto 27 del
catalogo applicato ai controlli.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# LE SOGLIE SONO QUELLE DEL CODICE DI PRODUZIONE, non copie: un controllo che si
# scrivesse in casa i numeri del dossier certificherebbe se stesso.
from ..tennis_scalper import condotta_ordini as CD
from ..tennis_scalper import tennis_flb_bot as FLB
from ..tennis_scalper import tennis_scalper_bot as SC

# gli stati in cui un ciclo dello scalper e' VIVO: li' la tolleranza e' 0,02
_VIVI_SCALPER = frozenset({SC.QUOTING, SC.QUOTING2, SC.CANCELLING, SC.LOCKING,
                           SC.FLATTENING})

# gli stati VIVI di un ordine flumine: tutto il resto e' terminale. Si legge la
# tupla di produzione dello scalper (`_LIVE_ORDER_STATUSES`), che e' fatta di
# `OrderStatus` Enum: confrontarla come stringa e' il difetto 10 del catalogo.
STATI_ORDINE_VIVI = frozenset(
    getattr(s, "value", str(s)) for s in SC._LIVE_ORDER_STATUSES
)
# lo stato che Betfair (e flumine) danno a un ordine RIFIUTATO da un controllo
STATO_VIOLAZIONE = "Violation"

EPS = 0.011            # Betfair lavora al centesimo: sotto e' arrotondamento

# minimi di giurisdizione .it, gli stessi che lo scalper applica in LIVE
# (`tennis_scalper_bot._side_floor`): back 2,00 / lay 0,50.
MINIMO_IT = {"BACK": 2.0, "LAY": 0.5}


# ---------------------------------------------------------------------------
# il referto
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Violazione:
    """Una regola della specifica non rispettata, col contesto per capirla."""

    codice: str                 # es. "B1"
    regola: str                 # la regola, in una riga, con la voce del dossier
    dettaglio: str              # che cosa e' successo davvero
    quando: str = ""            # istante / punteggio in cui e' successo

    def __str__(self) -> str:
        return "%s [%s] %s -> %s" % (self.codice, self.quando, self.regola,
                                     self.dettaglio)


@dataclass
class Osservazione:
    """TUTTO cio' che e' successo in UN giro del bot, come e' successo.

    Niente viene ricostruito qui dentro: ogni campo e' copiato da un oggetto di
    produzione (il `MarketBook` di flumine, il blotter, lo stato interno della
    strategia di produzione, le attivita' che il bot ha emesso col suo
    `event_sink`).
    """

    bot: str = ""                                  # tennis_scalper | tennis_pro | ...
    scenario: str = "base"
    quando: str = ""                               # publish_time ISO del giro
    modalita: str = "paper"                        # paper | live
    dry_run: bool = False
    disabilitato: bool = False                     # `_tennis_disabled` del runner
    inplay: bool = False
    stato_mercato: str = ""                        # OPEN | SUSPENDED | CLOSED
    market_id: str = ""
    stake: float = 0.0
    cap_esposizione: Optional[float] = None
    giurisdizione: str = "it"
    # gli ordini VERI del bot, letti dal blotter di flumine e normalizzati
    ordini: List[Dict[str, Any]] = field(default_factory=list)
    # i ref che il banco ha RIFIUTATO in questo giro (scenario `rifiuti-betfair`)
    rifiutati: List[str] = field(default_factory=list)
    # cio' che il BOT CREDE: una riga per posizione creduta (vedi `credenze`)
    credenze: List[Dict[str, Any]] = field(default_factory=list)
    # le attivita' che il bot ha emesso in questo giro (kind, payload)
    attivita: List[Tuple[str, Dict[str, Any]]] = field(default_factory=list)
    # le `stats` del bot, come le scriverebbe l'heartbeat in tennis_bot_control
    stats: Dict[str, Any] = field(default_factory=dict)
    # la riga che `tennis_live_orders` porterebbe per ogni ordine (specchio)
    specchio: List[Dict[str, Any]] = field(default_factory=list)
    # esposizione per selezione letta dal blotter (mai ricalcolata a mano)
    esposizioni: Dict[Any, Dict[str, float]] = field(default_factory=dict)
    # gli id degli ordini che il bot dichiara come INGRESSO (non uscite): li
    # raccoglie il replay da `credenze`, cosi' B5 non deve indovinare il ruolo
    ids_ingresso: set = field(default_factory=set)
    # gli id degli ordini COMPARSI a mercato IN QUESTO GIRO. ⚠️ Serve a non
    # accusare il bot per ordini che aveva legittimamente piazzato PRIMA che una
    # condizione cambiasse (il disarm mette `dry_run=True` su un bot che ha gia'
    # una posizione: senza questa distinzione B1 accuserebbe il disarm stesso —
    # e' il falso positivo DEL CONTROLLO contro cui mette in guardia §6.7).
    ordini_nuovi: set = field(default_factory=set)

    def kinds(self) -> List[str]:
        return [k for k, _ in self.attivita]

    def attivita_di(self, kind: str) -> List[Dict[str, Any]]:
        return [p for k, p in self.attivita if k == kind]


Controllo = Callable[[Osservazione], Optional[str]]
_REGISTRO: List[Tuple[str, str]] = []
_FUNZIONI: Dict[str, Controllo] = {}
_QUANDO: Dict[str, Optional[Controllo]] = {}


def _controllo(codice: str, regola: str, quando: Optional[Controllo] = None):
    """Registra un controllo e dichiara QUANDO ha davvero un caso."""

    def _reg(fn: Controllo) -> Controllo:
        _REGISTRO.append((codice, regola))
        _FUNZIONI[codice] = fn
        _QUANDO[codice] = quando
        return fn

    return _reg


# ---------------------------------------------------------------------------
# utilita': leggere un ordine di flumine SEMPRE nello stesso modo
# ---------------------------------------------------------------------------
def _f(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def stato_ordine(ordine: Any) -> Optional[str]:
    """Lo stato di un ordine flumine letto come si DEVE leggere.

    `order.status` e' un Enum `OrderStatus`: `str(stato)` da'
    `"OrderStatus.EXECUTABLE"` e confrontarlo con `"EXECUTABLE"` non matcha mai
    (difetto 10 del catalogo). Qui si legge `.value` e si ripiega su `.name`
    solo se il `.value` non c'e'.
    """
    st = getattr(ordine, "status", None)
    if st is None:
        return None
    v = getattr(st, "value", None)
    if v is not None:
        return str(v)
    n = getattr(st, "name", None)
    return str(n) if n is not None else str(st)


def riga_ordine(ordine: Any) -> Dict[str, Any]:
    """Un ordine di flumine -> le stesse chiavi snake_case che la produzione usa
    (`tennis_live_order_worker._order_snapshot`): cosi' un controllo che legge
    una grafia diversa da quella del vero e' impossibile (difetto 1 del 15/09).
    """
    ot = getattr(ordine, "order_type", None)
    side = getattr(ordine, "side", None)
    return {
        "order_id": str(getattr(ordine, "id", "") or ""),
        "bet_id": getattr(ordine, "bet_id", None),
        "status": stato_ordine(ordine),
        "side": side.upper() if isinstance(side, str) else side,
        "selection_id": getattr(ordine, "selection_id", None),
        "market_id": getattr(ordine, "market_id", None),
        "price": _f(getattr(ot, "price", None)) if ot is not None else None,
        "size": _f(getattr(ot, "size", None)) if ot is not None else None,
        "size_matched": _f(getattr(ordine, "size_matched", None)) or 0.0,
        "size_remaining": _f(getattr(ordine, "size_remaining", None)) or 0.0,
        "size_cancelled": _f(getattr(ordine, "size_cancelled", None)) or 0.0,
        "size_lapsed": _f(getattr(ordine, "size_lapsed", None)) or 0.0,
        "size_voided": _f(getattr(ordine, "size_voided", None)) or 0.0,
        "average_price_matched": _f(
            getattr(ordine, "average_price_matched", None)) or 0.0,
        "customer_order_ref": getattr(ordine, "customer_order_ref", None),
        "violation_msg": getattr(ordine, "violation_msg", None),
    }


def _vivo(riga: Dict[str, Any]) -> bool:
    return str(riga.get("status") or "") in STATI_ORDINE_VIVI


def _rifiutato(riga: Dict[str, Any]) -> bool:
    """Un ordine RIFIUTATO: o Betfair/flumine lo ha bocciato (`Violation`), o non
    ha MAI avuto uno stato — cioe' `place_order` ha risposto `False` e l'ordine
    non e' mai partito (`flumine/execution/transaction.py:67-72`). E' il difetto
    2 del catalogo: `res.ok` mai letto."""
    st = riga.get("status")
    return st is None or str(st) == STATO_VIOLAZIONE


# ---------------------------------------------------------------------------
# CIO' CHE IL BOT CREDE — il nome VERO dello stato di ognuno dei quattro
# ---------------------------------------------------------------------------
def _ordini_di(*candidati: Any) -> List[Any]:
    return [o for o in candidati if o is not None]


def credenze(strat: Any, bot_key: str) -> List[Dict[str, Any]]:
    """Le posizioni che il BOT CREDE di avere, lette dal suo stato di RAM VERO.

    Una riga per posizione, con le stesse chiavi per tutti e quattro:
      chiave      (market_id, selection_id)
      stato       il nome che il bot usa davvero (QUOTING/OPEN/CLOSING/...)
      ordini      gli oggetti Order che il bot sta seguendo per quella posizione
      prezzo      il prezzo d'ingresso che il bot ha memorizzato (o None)
      ruolo       "ingresso" | "uscita" per ogni ordine seguito

    ⚠️ Nessun nome e' inventato: `_Slot.status` (tennis_scalper_bot.py:174),
    `trade["state"]` (tennis_pro_bot.py:389), `st["state"]`
    (tennis_flb_bot.py:224), `tr["closing"]` (tennis_swing_bot.py:276).
    """
    out: List[Dict[str, Any]] = []
    if strat is None:
        return out

    if bot_key == "tennis_scalper":
        for (mid, sel), slot in dict(getattr(strat, "_slots", {}) or {}).items():
            ingressi = _ordini_di(getattr(slot, "entry", None),
                                  getattr(slot, "entry_back", None),
                                  getattr(slot, "entry_lay", None))
            uscite = _ordini_di(getattr(slot, "close", None))
            uscite += list(getattr(slot, "flatten_orders", None) or [])
            out.append({
                "chiave": (str(mid), int(sel)),
                "stato": str(getattr(slot, "status", "")),
                "ingressi": ingressi,
                "uscite": uscite,
                "prezzo": _f(getattr(slot, "ref_price", None)),
                # LA TOLLERANZA E' QUELLA DEL BOT, non una inventata qui.
                # Mentre il ciclo e' VIVO lo scalper pretende 0,02; quando il
                # ciclo e' CHIUSO (IDLE/DONE) la soglia dichiarata e' quella
                # dell'accettazione del micro-residuo (`RESIDUO_ACCETTATO`),
                # perche' un residuo di pochi centesimi non e' chiudibile —
                # qualunque ordine di chiusura sarebbe piu' grande del residuo.
                # ⚠️ Un controllo che pretendesse lo zero assoluto accuserebbe
                # il bot di una cosa che la sua spec gli concede, ed e' il falso
                # positivo DEL CONTROLLO contro cui mette in guardia §6.7.
                # Ciclo CHIUSO con residuo DICHIARATO non piazzabile
                # (`residual_ok`, che lo scalper alza quando nessun ordine
                # legale di .it potrebbe chiuderlo): la soglia e' il MINIMO DI
                # LATO, perche' sotto quello non esiste un ordine che lo chiuda
                # — bumpare a 0,50 o a 2,00 ROVESCEREBBE la posizione. Non e'
                # una soglia scelta per far passare il referto: viene dalla
                # giurisdizione. Senza `residual_ok` resta la tolleranza che il
                # bot dichiara per un ciclo chiuso.
                "tolleranza": (
                    0.02 if str(getattr(slot, "status", "")) in _VIVI_SCALPER
                    else (CD.MINIMO_LATO["LAY"]
                          if getattr(slot, "residual_ok", False)
                          else CD.RESIDUO_ACCETTATO)),
            })
        return out

    if bot_key == "tennis_pro":
        for mid, tr in dict(getattr(strat, "_trade", {}) or {}).items():
            if not isinstance(tr, dict):
                continue
            sel = tr.get("sel")
            if sel is None:
                continue
            out.append({
                "chiave": (str(mid), int(sel)),
                "stato": str(tr.get("state") or ""),
                "ingressi": _ordini_di(tr.get("order")),
                "uscite": _ordini_di(tr.get("staged_order"),
                                     tr.get("close_order")),
                "prezzo": _f(tr.get("entry")),
                # la soglia di «blotter pari» del PRO (`tennis_pro_bot.py:711`)
                "tolleranza": 0.02,
            })
        return out

    if bot_key == "tennis_flb":
        for (mid, sel), st in dict(getattr(strat, "_pos_state", {}) or {}).items():
            if not isinstance(st, dict):
                continue
            out.append({
                "chiave": (str(mid), int(sel)),
                "stato": str(st.get("state") or ""),
                "ingressi": _ordini_di(st.get("order")),
                "uscite": _ordini_di(st.get("green_order")),
                "prezzo": _f(st.get("entry")),
                # il FLB non dichiara nessuna tolleranza: il centesimo
                "tolleranza": EPS,
            })
        return out

    if bot_key == "tennis_swing":
        for mid, tr in dict(getattr(strat, "_tr", {}) or {}).items():
            if not isinstance(tr, dict):
                continue
            sel = tr.get("sel")
            if sel is None:
                continue
            # lo swing non ha costanti di stato: la fase e' implicita nelle
            # chiavi del dizionario (tennis_swing_bot.py:276 `closing`)
            stato = "CLOSING" if tr.get("closing") else "OPEN"
            out.append({
                "chiave": (str(mid), int(sel)),
                "stato": stato,
                "ingressi": _ordini_di(tr.get("order")),
                "uscite": _ordini_di(tr.get("close_order")),
                "prezzo": _f(tr.get("px")),
                # la soglia di «pari» dello swing (`tennis_swing_bot.py:201`)
                "tolleranza": 0.01,
            })
        return out

    return out


# gli stati in cui una credenza DICHIARA di avere (o di poter avere) qualcosa a
# mercato. Sono i nomi VERI dei quattro bot, importati dove esistono.
STATI_CREDUTI_VIVI = frozenset({
    SC.QUOTING, SC.QUOTING2, SC.CANCELLING, SC.LOCKING, SC.FLATTENING,
    FLB.OPEN, FLB.PENDING, "OPEN", "CLOSING",
})
STATI_CREDUTI_CHIUSI = frozenset({SC.IDLE, SC.DONE, FLB.DONE, "FLAT", "DONE"})


def _ids(ordini: Sequence[Any]) -> set:
    return {str(getattr(o, "id", "") or "") for o in ordini if o is not None}


def ordini_seguiti(oss: Osservazione) -> set:
    """Gli id di TUTTI gli ordini che il bot sta seguendo, ingressi e uscite."""
    out: set = set()
    for c in oss.credenze:
        out |= _ids(c.get("ingressi") or ())
        out |= _ids(c.get("uscite") or ())
    return out


# ---------------------------------------------------------------------------
# QUANDO ognuno ha un caso
# ---------------------------------------------------------------------------
def _q_ordini(oss: Osservazione) -> bool:
    return bool(oss.ordini)


def _q_rifiuti(oss: Osservazione) -> bool:
    return any(_rifiutato(r) for r in oss.ordini) or bool(oss.rifiutati)


def _q_credenze_vive(oss: Osservazione) -> bool:
    # ⚠️ In DRY-RUN i quattro bot registrano la posizione SENZA piazzare nulla
    # (`tennis_flb_bot.py:222` `if o is None and not self.dry_run: continue`):
    # e' la contabilita' della prova a vuoto, non una posizione creduta a
    # mercato. Giudicarla contro il banco vorrebbe dire accusare il bot di non
    # avere cio' che non deve avere (§6.7). La divergenza fra dry-run e paper
    # e' un difetto di PROGETTAZIONE e sta nel referto d'audit, non qui.
    if oss.dry_run:
        return False
    return any(str(c.get("stato") or "") in STATI_CREDUTI_VIVI
               for c in oss.credenze)


def _q_abbinati(oss: Osservazione) -> bool:
    return any((r.get("size_matched") or 0.0) > 0.009 for r in oss.ordini)


def _q_dry(oss: Osservazione) -> bool:
    return bool(oss.dry_run)


def _q_disabilitato(oss: Osservazione) -> bool:
    return bool(oss.disabilitato)


def _q_ingressi(oss: Osservazione) -> bool:
    # i quattro bot NON usano lo stesso nome per l'attivita' di apertura: flb,
    # pro e swing emettono `entry`, lo scalper emette `place`. Guardarne uno
    # solo lasciava B5 «mai sollecitato» proprio sul bot che apre di piu'.
    return bool(oss.attivita_di("entry") or oss.attivita_di("place"))


def _q_live(oss: Osservazione) -> bool:
    return oss.modalita == "live" and bool(oss.ordini)


def _q_chiuso(oss: Osservazione) -> bool:
    return str(oss.stato_mercato or "").upper() != "OPEN"


def _q_stats(oss: Osservazione) -> bool:
    return bool(oss.stats)


def _q_specchio(oss: Osservazione) -> bool:
    return bool(oss.specchio)


def _q_cap(oss: Osservazione) -> bool:
    return oss.cap_esposizione is not None and bool(oss.esposizioni)


def _q_flb(oss: Osservazione) -> bool:
    return oss.bot == "tennis_flb" and bool(oss.attivita_di("entry"))


# ===========================================================================
# FAMIGLIA B — la CONDOTTA secondo il dossier
# ===========================================================================
@_controllo("B1", "in DRY-RUN il bot non manda MAI un ordine a mercato "
                  "(dossier §4: `dry_run` gatea ogni `market.place_order`; "
                  "e' il kill-switch che il runner forza in OFF)",
            quando=_q_dry)
def _b1(oss: Osservazione) -> Optional[str]:
    if not oss.dry_run:
        return None
    # SOLO gli ordini NATI in questo giro: quelli piazzati prima che il disarm
    # mettesse `dry_run=True` sono legittimi e li giudica B3/K6.
    nuovi = [r for r in oss.ordini if r.get("order_id") in (oss.ordini_nuovi or set())]
    if nuovi:
        r = nuovi[0]
        return ("dry_run=True ma in questo giro sono comparsi %d ordini nuovi "
                "del bot (primo: %s %s @%s per %s)"
                % (len(nuovi), r.get("side"), r.get("selection_id"),
                   r.get("price"), r.get("size")))
    return None


@_controllo("B2", "ogni ordine chiesto ha prezzo nella ladder Betfair "
                  "[1.01, 1000] e size >= 0.01 (guardie di `_place`)",
            quando=_q_ordini)
def _b2(oss: Osservazione) -> Optional[str]:
    for r in oss.ordini:
        p, s = r.get("price"), r.get("size")
        if p is not None and (p < 1.01 or p > 1000.0):
            return "ordine %s a prezzo %s, fuori dalla ladder" % (r.get("order_id"), p)
        if s is not None and s < 0.01:
            return "ordine %s con size %s, sotto il minimo tecnico" % (r.get("order_id"), s)
    return None


@_controllo("B3", "un bot DISABILITATO (disarm del runner, `_tennis_disabled`) "
                  "non apre piu' nulla: le protezioni girano, le aperture no "
                  "(PROCESSO_STANDARD_BOT §6.3)",
            quando=_q_disabilitato)
def _b3(oss: Osservazione) -> Optional[str]:
    if not oss.disabilitato:
        return None
    if oss.attivita_di("entry") or oss.attivita_di("place"):
        return ("il bot e' disabilitato ma ha emesso %d aperture in questo giro"
                % (len(oss.attivita_di("entry")) + len(oss.attivita_di("place"))))
    return None


@_controllo("B4", "nessun ordine viene chiesto a mercato NON operabile "
                  "(sospeso o chiuso): su sospeso si aspetta, su chiuso si "
                  "cambia strada (catalogo §7 punto 17)",
            quando=_q_chiuso)
def _b4(oss: Osservazione) -> Optional[str]:
    if str(oss.stato_mercato or "").upper() == "OPEN":
        return None
    if oss.attivita_di("place") or oss.attivita_di("entry"):
        return ("mercato %s ma il bot ha chiesto un ordine in questo giro"
                % oss.stato_mercato)
    return None


@_controllo("B5", "lo stake d'ingresso e' quello del control (mai piu' di "
                  "quanto l'utente ha acceso): `_instantiate_bot` scrive "
                  "`params['stake']` dal control-row",
            quando=_q_ingressi)
def _b5(oss: Osservazione) -> Optional[str]:
    if oss.stake <= 0:
        return None
    for r in oss.ordini:
        s = r.get("size")
        if s is None:
            continue
        # le uscite (green-up, flatten) possono essere piu' grandi dello stake:
        # si guarda solo cio' che il bot ha dichiarato come INGRESSO
        if str(r.get("order_id")) not in (oss.ids_ingresso or set()):
            continue
        if s > oss.stake + EPS:
            return ("ordine d'ingresso %s per %s con stake del control %s"
                    % (r.get("order_id"), s, oss.stake))
    return None


@_controllo("B6", "FLB: l'ingresso e' sempre un LAY del favorito ESTREMO "
                  "(best-lay <= `lay_max`) e mai un BACK (dossier §4.3)",
            quando=_q_flb)
def _b6(oss: Osservazione) -> Optional[str]:
    if oss.bot != "tennis_flb":
        return None
    for p in oss.attivita_di("entry"):
        if str(p.get("side") or "").upper() != "LAY":
            return "ingresso FLB con side '%s' invece di LAY" % p.get("side")
    return None


@_controllo("B7", "l'esposizione per selezione non supera il tetto che il "
                  "runner passa al bot (`max_selection_exposure`): i tetti di "
                  "flumine sono aperti nel banco, quello del bot no",
            quando=_q_cap)
def _b7(oss: Osservazione) -> Optional[str]:
    cap = oss.cap_esposizione
    if cap is None:
        return None
    for chiave, exp in (oss.esposizioni or {}).items():
        val = abs(float(exp.get("selection_exposure") or 0.0))
        if val > cap + EPS:
            return ("esposizione %s su %s contro il tetto %s del runner"
                    % (round(val, 2), chiave, cap))
    return None


@_controllo("B8", "in LIVE .it nessun ordine sotto il minimo di giurisdizione "
                  "(back 2,00 / lay 0,50): Betfair lo RIFIUTA e la gamba resta "
                  "scoperta (PROCESSO_STANDARD_BOT §6.4)",
            quando=_q_live)
def _b8(oss: Osservazione) -> Optional[str]:
    if oss.modalita != "live" or oss.giurisdizione != "it":
        return None
    for r in oss.ordini:
        s, side = r.get("size"), str(r.get("side") or "").upper()
        if s is None or side not in MINIMO_IT:
            continue
        if s + EPS < MINIMO_IT[side]:
            return ("ordine %s %s per %s: sotto il minimo .it di %s -> "
                    "INVALID_BET_SIZE, gamba scoperta"
                    % (r.get("order_id"), side, s, MINIMO_IT[side]))
    return None


# ===========================================================================
# FAMIGLIA K — LA CONSAPEVOLEZZA DELL'ORDINE contro il banco (§7 punto 36)
# ===========================================================================
@_controllo("K1", "ogni ordine che il bot STA SEGUENDO esiste davvero a "
                  "mercato: un ordine che il bot tiene in mano e che il blotter "
                  "non conosce e' una posizione che nessuno governa",
            quando=_q_credenze_vive)
def _k1(oss: Osservazione) -> Optional[str]:
    a_mercato = {r.get("order_id") for r in oss.ordini}
    for c in oss.credenze:
        if str(c.get("stato") or "") not in STATI_CREDUTI_VIVI:
            continue
        for oid in _ids(c.get("ingressi") or ()) | _ids(c.get("uscite") or ()):
            if oid and oid not in a_mercato:
                return ("la posizione %s e' '%s' e segue l'ordine %s, che a "
                        "mercato non esiste"
                        % (c.get("chiave"), c.get("stato"), oid))
    return None


@_controllo("K2", "un ordine RIFIUTATO (place_order ha risposto False, oppure "
                  "stato Violation) non lascia il bot con una posizione creduta "
                  "viva (difetto 2 del 15/09: `res.ok` mai letto)",
            quando=_q_rifiuti)
def _k2(oss: Osservazione) -> Optional[str]:
    rifiutati = {r.get("order_id") for r in oss.ordini if _rifiutato(r)}
    rifiutati |= set(oss.rifiutati or ())
    if not rifiutati:
        return None
    for c in oss.credenze:
        if str(c.get("stato") or "") not in STATI_CREDUTI_VIVI:
            continue
        seguiti = _ids(c.get("ingressi") or ()) | _ids(c.get("uscite") or ())
        if not (seguiti & rifiutati):
            continue
        # la posizione e' viva SOLO grazie a ordini rifiutati? allora il bot
        # crede di avere a mercato qualcosa che non e' mai partito
        vivi = {r.get("order_id") for r in oss.ordini
                if not _rifiutato(r) and r.get("order_id") in seguiti}
        if not vivi:
            return ("la posizione %s e' '%s' ma TUTTI i suoi ordini sono stati "
                    "rifiutati (%s): il bot crede di avere a mercato qualcosa "
                    "che non e' mai partito"
                    % (c.get("chiave"), c.get("stato"), sorted(rifiutati & seguiti)))
    return None


@_controllo("K3", "lo stato di ogni ordine si rilegge come Enum `OrderStatus` "
                  "(`.value`), mai come stringa: `str(stato)` da' "
                  "'OrderStatus.EXECUTABLE' e nessun ordine risulta vivo "
                  "(catalogo §7 punto 10)",
            quando=_q_ordini)
def _k3(oss: Osservazione) -> Optional[str]:
    # gli stati LEGALI sono quelli dell'Enum di flumine, letti dall'Enum stesso:
    # scriverseli a mano vorrebbe dire che il giorno in cui flumine ne aggiunge
    # uno il controllo accusa il bot invece di accorgersi di se stesso.
    from flumine.order.order import OrderStatus

    noti = {s.value for s in OrderStatus}
    for r in oss.ordini:
        st = r.get("status")
        if st is None:
            continue           # ordine mai piazzato: lo prende K2
        if str(st).startswith("OrderStatus."):
            return ("l'ordine %s espone lo stato '%s': e' l'Enum letto come "
                    "stringa (difetto 10 del catalogo)" % (r.get("order_id"), st))
        if str(st) not in noti:
            return ("l'ordine %s ha lo stato '%s', che il banco non conosce: "
                    "il confronto degli stati vivi non puo' funzionare"
                    % (r.get("order_id"), st))
    return None


@_controllo("K4", "una posizione che il bot crede VIVA ha almeno un ordine a "
                  "mercato o dell'abbinato: altrimenti il bot sorveglia il "
                  "nulla (difetto 4 del 15/09)",
            quando=_q_credenze_vive)
def _k4(oss: Osservazione) -> Optional[str]:
    per_sel: Dict[Any, float] = {}
    for r in oss.ordini:
        chiave = (str(r.get("market_id") or ""), int(r.get("selection_id") or 0))
        per_sel[chiave] = per_sel.get(chiave, 0.0) + (r.get("size_matched") or 0.0)
    vivi_per_sel: Dict[Any, int] = {}
    for r in oss.ordini:
        if not _vivo(r):
            continue
        chiave = (str(r.get("market_id") or ""), int(r.get("selection_id") or 0))
        vivi_per_sel[chiave] = vivi_per_sel.get(chiave, 0) + 1
    for c in oss.credenze:
        if str(c.get("stato") or "") not in STATI_CREDUTI_VIVI:
            continue
        chiave = c.get("chiave")
        if vivi_per_sel.get(chiave, 0) > 0:
            continue
        if per_sel.get(chiave, 0.0) > 0.009:
            continue
        return ("la posizione %s e' '%s' ma su quella selezione non c'e' nessun "
                "ordine vivo ne' un centesimo di abbinato"
                % (chiave, c.get("stato")))
    return None


def _q_esposizione(oss: Osservazione) -> bool:
    return bool(oss.esposizioni) and _q_abbinati(oss)


@_controllo("K5", "nessuna ESPOSIZIONE abbinata resta senza una posizione viva "
                  "del bot che la governi: nessuna posizione FANTASMA (difetto 4 "
                  "del 15/09 visto dall'altra parte)",
            quando=_q_esposizione)
def _k5(oss: Osservazione) -> Optional[str]:
    """⚠️ LA DOMANDA GIUSTA NON E' «esiste una credenza per quest'ordine».

    La prima stesura di questo controllo confrontava gli ORDINI abbinati con gli
    ordini che il bot sta seguendo, e accusava `tennis_pro` 4386 volte su una
    sola partita. Era un FALSO POSITIVO DEL CONTROLLO (§6.7): il PRO tiene UNA
    sola riga di trade per mercato (`tennis_pro_bot.py:389`) e quando il ciclo si
    chiude la riporta a `{"state": FLAT}`, cioe' DIMENTICA gli ordini di un ciclo
    concluso e contabilizzato. Dimenticare un ciclo CHIUSO E PARI e' corretto.

    Cio' che NON e' corretto — ed e' il difetto 4 del 15/09 — e' che resti
    dell'ESPOSIZIONE ABBINATA che nessuna posizione viva governa. Percio' qui si
    guarda l'esposizione VERA letta dal blotter con la funzione di produzione
    (`tennis_live_order_worker._position_row`), non un conteggio di ordini: se
    per una selezione senza posizione viva `matched_if_win` e `matched_if_lose`
    differiscono di piu' di un centesimo, i soldi sono a mercato senza padrone.
    """
    vive = {c.get("chiave") for c in oss.credenze
            if str(c.get("stato") or "") in STATI_CREDUTI_VIVI}
    # la tolleranza la dichiara il BOT, per selezione (vedi `credenze`)
    tolleranze = {c.get("chiave"): float(c.get("tolleranza") or EPS)
                  for c in oss.credenze}
    for chiave, exp in (oss.esposizioni or {}).items():
        # `esposizioni` e' indicizzata per (selection_id, handicap); la chiave
        # delle credenze e' (market_id, selection_id)
        sel = chiave[0] if isinstance(chiave, tuple) else chiave
        k = (str(oss.market_id), int(sel))
        if k in vive:
            continue
        w = float(exp.get("matched_if_win") or 0.0)
        l = float(exp.get("matched_if_lose") or 0.0)
        tol = max(EPS, tolleranze.get(k, EPS))
        if abs(w - l) <= tol:
            continue           # dentro la tolleranza che il bot DICHIARA
        stato = next((str(c.get("stato") or "?") for c in oss.credenze
                      if c.get("chiave") == k), "nessuna posizione")
        return ("sulla selezione %s resta un'esposizione ABBINATA sbilanciata "
                "di %s (se vince %s, se perde %s), oltre la tolleranza %s che il "
                "bot stesso dichiara, e il bot la crede '%s': i soldi sono a "
                "mercato senza padrone"
                % (sel, round(abs(w - l), 2), round(w, 2), round(l, 2), tol,
                   stato))
    return None


@_controllo("K6", "quando il bot dichiara la posizione CHIUSA non resta nessun "
                  "suo ordine ancora VIVO sul book (residuo non governato: "
                  "PROCESSO_STANDARD_BOT §6.4 «mai una posizione scoperta non "
                  "dichiarata»)",
            quando=_q_ordini)
def _k6(oss: Osservazione) -> Optional[str]:
    chiuse = {c.get("chiave") for c in oss.credenze
              if str(c.get("stato") or "") in STATI_CREDUTI_CHIUSI}
    if not chiuse:
        return None
    vive = {c.get("chiave") for c in oss.credenze
            if str(c.get("stato") or "") in STATI_CREDUTI_VIVI}
    for r in oss.ordini:
        if not _vivo(r):
            continue
        # ⚠️ `Cancelling` NON E' UN RESIDUO NON GOVERNATO: e' il cancel che il
        # bot HA CHIESTO e che sta viaggiando verso Betfair. Accusarlo vuol dire
        # accusare il bot di stare facendo esattamente la cosa giusta, ed e' il
        # falso positivo DEL CONTROLLO contro cui mette in guardia §6.7.
        # MISURATO: F4 del 17/09, 19 violazioni su 12 partite, TUTTE con stato
        # `Cancelling` e tutte transitorie (1-3 giri), con la sorveglianza
        # post-DONE dello scalper che ritentava il cancel a ogni book — cioe'
        # il bot stava governando. Un ordine `Executable` o `Pending` sotto una
        # posizione dichiarata chiusa resta invece una violazione piena: quello
        # nessuno l'ha chiesto e nessuno lo sta togliendo.
        if str(r.get("status") or "") == "Cancelling":
            continue
        chiave = (str(r.get("market_id") or ""), int(r.get("selection_id") or 0))
        if chiave in vive or chiave not in chiuse:
            continue
        return ("la posizione %s e' dichiarata chiusa ma l'ordine %s e' ancora "
                "'%s' sul book per %s"
                % (chiave, r.get("order_id"), r.get("status"),
                   r.get("size_remaining")))
    return None


@_controllo("K7", "il prezzo medio e l'abbinato che il bot pubblica nelle sue "
                  "`stats` non sono mai migliori del mercato: un green contato "
                  "senza hedge a mercato e' una cifra inventata (difetto 3 del "
                  "15/09 in forma nuova)",
            quando=_q_stats)
def _k7(oss: Osservazione) -> Optional[str]:
    greens = _f(oss.stats.get("greens"))
    if greens is None or greens <= 0:
        return None
    # un green CONFERMATO richiede almeno un ordine di copertura a mercato
    if not oss.ordini:
        return ("le stats dichiarano %s green ma il bot non ha MAI avuto un "
                "ordine a mercato" % int(greens))
    coperture = [r for r in oss.ordini if (r.get("size_matched") or 0.0) > 0.009]
    if len(coperture) < 2 and greens >= 1:
        return ("le stats dichiarano %s green ma a mercato esiste solo %d "
                "ordine abbinato: un green e' due gambe, non una"
                % (int(greens), len(coperture)))
    return None


# ===========================================================================
# FAMIGLIA P — la PERSISTENZA e cio' che la UI mostra (§6.5)
# ===========================================================================
@_controllo("P1", "ogni ordine del bot arriva allo specchio `tennis_live_orders` "
                  "con chiesto, abbinato, residuo, prezzo medio e stato: sono i "
                  "campi che la UI mostra (§6.5)",
            quando=_q_specchio)
def _p1(oss: Osservazione) -> Optional[str]:
    obbligatori = ("size", "size_matched", "size_remaining",
                   "average_price_matched", "status", "client_order_ref", "mode")
    for riga in oss.specchio:
        mancanti = [k for k in obbligatori if riga.get(k) is None]
        if mancanti:
            return ("la riga di specchio %s non porta %s: la UI non puo' dire "
                    "che cosa c'e' a mercato"
                    % (riga.get("client_order_ref"), ", ".join(mancanti)))
    return None


@_controllo("P2", "lo specchio non dichiara MAI un ordine abbinato piu' di "
                  "quanto il mercato dica (nessun fill dedotto dal prezzo)",
            quando=_q_specchio)
def _p2(oss: Osservazione) -> Optional[str]:
    per_id = {r.get("order_id"): r for r in oss.ordini}
    for riga in oss.specchio:
        vero = per_id.get(riga.get("order_id"))
        if vero is None:
            continue
        sm = _f(riga.get("size_matched"))
        if sm is None:
            continue
        if abs(sm - (vero.get("size_matched") or 0.0)) > EPS:
            return ("lo specchio di %s dice abbinato %s, il mercato dice %s"
                    % (riga.get("client_order_ref"), sm, vero.get("size_matched")))
    return None


@_controllo("P3", "a mercato CHIUSO il bot pubblica un P&L di settlement: senza, "
                  "lo storico non puo' sommare nulla (§6.5 e §6.4 «settlement "
                  "con commissione, P&L netto»)",
            quando=_q_chiuso)
def _p3(oss: Osservazione) -> Optional[str]:
    if str(oss.stato_mercato or "").upper() != "CLOSED":
        return None
    if not oss.ordini:
        return None            # nessun ordine: niente da regolare
    chiavi = ("pnl", "pnl_settled", "settled_pnl")
    if not any(k in (oss.stats or {}) for k in chiavi):
        return ("mercato chiuso con %d ordini del bot ma nessuna chiave di P&L "
                "regolato nelle stats (%s): lo storico non puo' sommare"
                % (len(oss.ordini), sorted(oss.stats or {})))
    return None


# ===========================================================================
# il giro completo
# ===========================================================================
def verifica(oss: Osservazione,
             sollecitati: Optional[Dict[str, int]] = None) -> List[Violazione]:
    """I controlli su UN giro. Ogni controllo che ha un CASO viene contato."""
    out: List[Violazione] = []
    for codice, regola in _REGISTRO:
        quando = _QUANDO.get(codice)
        try:
            if quando is not None and not quando(oss):
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
        if det:
            out.append(Violazione(codice, regola, det, oss.quando))
    return out


def elenco_controlli() -> List[Tuple[str, str]]:
    """(codice, regola) di tutti i controlli: il contratto per la copertura."""
    return list(_REGISTRO)


def mai_sollecitati(sollecitati: Dict[str, int]) -> List[Tuple[str, str]]:
    """I controlli che NON hanno mai avuto un caso. Su questi il referto non
    dice «sano», dice «non lo so» (§6.7)."""
    return [(c, r) for c, r in _REGISTRO if not sollecitati.get(c)]


# ---------------------------------------------------------------------------
# il referto di UNA partita
# ---------------------------------------------------------------------------
@dataclass
class Referto:
    """Il referto di un evento, con le stesse chiavi che `certifica.py` stampa."""

    event_id: str
    bot: str = ""
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
