# -*- coding: utf-8 -*-
"""SAFE — LA CONSAPEVOLEZZA DELL'ORDINE, CONTRO IL BANCO (famiglia K).

⚠️ PERCHE' QUESTO MODULO ESISTE. Il 16/09 sera, falsificando Mike, si e'
scoperto (catalogo §7 punto 36) che i cinque difetti del 15/09 REINTRODOTTI UNO
A UNO sul codice di oggi NON facevano diventare rosso il replay: il referto era
identico cifra per cifra. I controlli B/E/P/T/J della Safe guardano la
DECISIONE (valutazione, ordine chiesto, uscita, ciclo); i cinque difetti non
stanno li', stanno nel rapporto fra cio' che il bot CREDE delle sue righe
(`safe_strategy_trades`) e cio' che il MERCATO dice dei suoi ordini.

Questi controlli guardano quel rapporto, ed e' lo stesso identico impianto della
famiglia K di Mike (`Betfair/mike/certificazione.py`): stesso registro, stessa
copertura, stesso principio — un controllo che non si conta non esiste, e un
controllo che dipende dalla CONFESSIONE del bot (un marcatore che il bot scrive
da se') non certifica niente.

Il modulo e' UNO SOLO ed e' importato sia da `certificazione.py` (calcio) sia da
`certificazione_tennis.py`: i due bot sono lo stesso servizio (`bot_service`),
lo stesso `execution.place` e la stessa tabella. Duplicarlo avrebbe voluto dire
due copie che divergono — ed e' il difetto 33 del catalogo.

CHE COSA RICEVE, e da dove viene (niente e' ricostruito qui dentro):

  * ``righe``     : le righe VERE di `safe_strategy_trades` del banco
                    (`DbMemoria.trades`), come le ha scritte il servizio;
  * ``ordini``    : {ref CHIESTO al piazzamento -> riga normalizzata}, cioe'
                    `MercatoFlumine.ordini` passato per `_riga` — le stesse
                    chiavi snake_case che `omega_market.list_current_orders`
                    produce in produzione;
  * ``rifiutati`` : i ref che il banco ha RIFIUTATO (`ok=False`), cioe' lo
                    scenario `rifiuti-betfair`.

I CINQUE DIFETTI DEL 15/09 E CHI LI PRENDE:
  (a) `customer_order_ref` letto come `customerOrderRef`  -> K3
  (b) `res.ok` ignorato in `execution.place`              -> K2
  (c) `avg_price` al posto di `avg_price_matched`         -> K1
  (d) ref di riconciliazione diverso da quello piazzato   -> K3/K4/K7
  (e) `closes_trade_id` non nel meta                      -> K6

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# il registro: (codice, regola). Identico nei due bot, contato nei due referti.
# ---------------------------------------------------------------------------
REGISTRO: List[Tuple[str, str]] = []
_FUNZIONI: Dict[str, Callable] = {}
_QUANDO: Dict[str, Optional[Callable]] = {}


def _controllo(codice: str, regola: str, quando: Optional[Callable] = None):
    """Registra un controllo e dichiara QUANDO ha davvero un caso.

    ⚠️ Senza `quando` un referto «zero violazioni» e' ambiguo: non si
    distingue un controllo che ha guardato e approvato da uno che non ha mai
    avuto l'occasione di guardare. Il 16/09 la prima stesura contava tutti e sei
    i controlli K a ogni giro con un ordine: nello scenario `rifiuti-betfair`,
    dove NON esiste nessun ordine a mercato (sono stati tutti rifiutati), li
    contava tutti a zero e K2 - l'unico che quello scenario esiste per
    sollecitare - risultava «non lo so».
    """
    def _reg(fn: Callable) -> Callable:
        REGISTRO.append((codice, regola))
        _FUNZIONI[codice] = fn
        _QUANDO[codice] = quando
        return fn
    return _reg


# gli stati in cui la riga DICHIARA di avere (o di poter avere) un ordine a
# mercato. 'pending' e' inclusa perche' e' la riserva in volo.
STATI_VIVI = ("open", "hedged", "pending")
# gli stati in cui la riga dichiara un ABBINAMENTO avvenuto: qui i numeri del
# bot e quelli del mercato devono coincidere.
STATI_CONFERMATI = ("open", "hedged", "won", "lost", "void")

EPS = 0.011            # Betfair lavora al centesimo: sotto e' arrotondamento


# ---------------------------------------------------------------------------
# utilita': le due grafie, i ref, l'ordine di una riga
# ---------------------------------------------------------------------------
def _camel(nome: str) -> str:
    pezzi = str(nome).split("_")
    return pezzi[0] + "".join(p.title() for p in pezzi[1:])


def campo_ordine(ordine: Dict[str, Any], nome: str) -> Any:
    """Un campo dell'ordine letto con TUTTE le grafie che Betfair usa.

    E' il difetto 1 del catalogo: `customerOrderRef` scritto e
    `customer_order_ref` letto (o viceversa) sono costati 32 ordini veri in
    loop il 15/09. Qui si cercano entrambe, sempre.
    """
    for chiave in (nome, _camel(nome)):
        v = (ordine or {}).get(chiave)
        if v is not None:
            return v
    return None


def ref_di_riga(riga: Dict[str, Any]) -> set:
    """I `customer_order_ref` con cui QUESTA riga puo' essere stata piazzata.

    Non se ne inventa nessuno: `safe-t{id}` e' quello che costruiscono
    `bot_service._execute` (`client_ref=f"safe-t{trade_id}"`) e
    `execution.close_trade` (`f"{table_prefix}-t{closing_id}"`); il ref della
    CODA flumine vive invece in `meta.flumine_client_ref`. Cercarne una sola e'
    il difetto 4 del 15/09.
    """
    refs: set = set()
    try:
        refs.add("safe-t%d" % int(riga.get("id")))
    except (TypeError, ValueError):
        pass
    meta = riga.get("meta") or {}
    if isinstance(meta, dict):
        for k in ("flumine_client_ref", "client_ref", "customer_order_ref"):
            v = meta.get(k)
            if v:
                refs.add(str(v))
    return refs


def ordine_di_riga(ordini: Dict[str, Any], riga: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """L'ordine del banco che appartiene a questa riga.

    Si cerca come lo cercherebbe Betfair: prima per il ref CHIESTO al
    piazzamento (tutte le grafie possibili), poi per `bet_id` — che e' la
    chiave certa quando il ref si e' perso.
    """
    for ref in ref_di_riga(riga):
        o = ordini.get(ref)
        if o is not None:
            return o
    bet = riga.get("bet_id")
    if bet:
        for o in (ordini or {}).values():
            if str(campo_ordine(o, "bet_id") or "") == str(bet):
                return o
    return None


def _f(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _dal_meta(riga: Dict[str, Any], nome: str) -> Optional[float]:
    meta = riga.get("meta") or {}
    if not isinstance(meta, dict):
        return None
    for dove in (meta, meta.get("fill") or {}, meta.get("betfair") or {}):
        if isinstance(dove, dict):
            v = _f(dove.get(nome))
            if v is not None:
                return v
    return None


def abbinato_creduto(riga: Dict[str, Any]) -> Optional[float]:
    """Quanto la riga dice di avere ABBINATO: colonna, meta, o `size`.

    `size` e' l'abbinato per costruzione — `_reconcile_confirm` e `_execute` lo
    riscrivono con la size davvero abbinata — ma la colonna nuova
    `size_matched` (migrazione `trades_consapevolezza_ordine_2026-09-16.sql`)
    e' quella autorevole quando c'e'.
    """
    v = _f(riga.get("size_matched"))
    if v is None:
        v = _dal_meta(riga, "size_matched")
    if v is None:
        v = _f(riga.get("size"))
    return v


def prezzo_creduto(riga: Dict[str, Any]) -> Optional[float]:
    v = _f(riga.get("avg_price_matched"))
    if v is None:
        v = _dal_meta(riga, "avg_price_matched")
    if v is None:
        v = _f(riga.get("price"))
    return v


def residuo_creduto(riga: Dict[str, Any]) -> Optional[float]:
    v = _f(riga.get("size_remaining"))
    if v is None:
        v = _dal_meta(riga, "size_remaining")
    return v


def _e_paper(riga: Dict[str, Any]) -> bool:
    """Una riga PAPER non ha un ordine a mercato: giudicarla contro il banco
    vorrebbe dire accusare il bot di non avere cio' che non deve avere."""
    return str(riga.get("mode") or "") == "paper"


def _vivo(ordine: Dict[str, Any]) -> bool:
    return str(campo_ordine(ordine, "status") or "").upper() == "EXECUTABLE"


def _e_chiusura(riga: Dict[str, Any]) -> bool:
    meta = riga.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {}
    return riga.get("closes_trade_id") is not None or meta.get("closes_trade_id") is not None


# ------------------------------------------------- QUANDO ha un caso, ognuno
def _q_confermate(righe, ordini, rif) -> bool:
    return bool(ordini) and any(
        not _e_paper(r) and str(r.get("status") or "") in STATI_CONFERMATI
        for r in righe)


def _q_rifiuti(righe, ordini, rif) -> bool:
    return bool(rif)


def _q_ordini(righe, ordini, rif) -> bool:
    return bool(ordini)


def _q_vive(righe, ordini, rif) -> bool:
    return any(not _e_paper(r) and str(r.get("status") or "") in ("open", "hedged")
               for r in righe)


def _q_residuo(righe, ordini, rif) -> bool:
    return bool(ordini) and any(
        not _e_paper(r) and residuo_creduto(r) is not None for r in righe)


def _q_chiusure(righe, ordini, rif) -> bool:
    return any(_e_chiusura(r) for r in righe)


# ===========================================================================
# K1 — l'abbinato e il prezzo medio
# ===========================================================================
@_controllo("K1", "cio' che la RIGA crede (abbinato e prezzo medio) coincide con "
                  "cio' che il MERCATO dice del suo ordine (difetto 3 del 15/09: "
                  "`avg_price` al posto di `avg_price_matched`)",
            quando=_q_confermate)
def _k1(righe, ordini, rifiutati):
    for r in righe:
        if _e_paper(r) or str(r.get("status") or "") not in STATI_CONFERMATI:
            continue
        o = ordine_di_riga(ordini, r)
        if o is None:
            continue
        if _vivo(o):
            continue                 # ancora vivo: il bot legge alla SUA cadenza
        abbinato = _f(campo_ordine(o, "size_matched")) or 0.0
        creduto = abbinato_creduto(r)
        if creduto is not None and abs(creduto - abbinato) > EPS:
            return ("riga #%s (%s): il bot crede %s abbinato, il mercato dice %s "
                    "(ordine %s)" % (r.get("id"), r.get("strategy"),
                                     round(creduto, 2), round(abbinato, 2),
                                     campo_ordine(o, "status")))
        if abbinato > 0.009:
            medio = _f(campo_ordine(o, "avg_price_matched"))
            if medio is None:
                medio = _f(campo_ordine(o, "average_price_matched"))
            atteso = prezzo_creduto(r)
            if medio and atteso is not None and abs(atteso - medio) > EPS:
                return ("riga #%s (%s): prezzo medio %s contro %s dichiarato dal "
                        "mercato (e' il difetto 3 del 15/09: `avg_price` al posto "
                        "di `avg_price_matched`)"
                        % (r.get("id"), r.get("strategy"), atteso, medio))
    return None


# ===========================================================================
# K2 — un ordine RIFIUTATO non lascia mai la riga viva
# ===========================================================================
@_controllo("K2", "una riga il cui ordine Betfair ha RIFIUTATO non resta mai viva "
                  "(difetto 2 del 15/09: `res.ok` mai letto)",
            quando=_q_rifiuti)
def _k2(righe, ordini, rifiutati):
    if not rifiutati:
        return None
    for r in righe:
        if _e_paper(r) or str(r.get("status") or "") not in STATI_VIVI:
            continue
        if not (ref_di_riga(r) & set(rifiutati)):
            continue
        if ordine_di_riga(ordini, r) is None:
            return ("riga #%s (%s): Betfair ha RIFIUTATO l'ordine e nessun ordine "
                    "esiste a mercato, ma la riga e' ancora '%s'"
                    % (r.get("id"), r.get("strategy"), r.get("status")))
    return None


# ===========================================================================
# K3 — il ref piazzato e' il ref riletto, in ENTRAMBE le grafie
# ===========================================================================
@_controllo("K3", "il riferimento con cui il bot ha piazzato si RILEGGE con la "
                  "stessa grafia, e la funzione VERA che riconosce gli ordini "
                  "del bot lo ritrova (difetto 1 del 15/09: `customerOrderRef` "
                  "vs `customer_order_ref`)",
            quando=_q_ordini)
def _k3(righe, ordini, rifiutati):
    from . import bot_service as BS

    for ref, o in (ordini or {}).items():
        letto = campo_ordine(o, "customer_order_ref")
        if letto is None:
            return ("l'ordine '%s' esiste a mercato ma il suo riferimento non si "
                    "rilegge in nessuna delle due grafie (chiavi: %s)"
                    % (ref, sorted(o)[:6]))
        if str(letto) != str(ref):
            return "l'ordine '%s' si rilegge col riferimento '%s'" % (ref, letto)
        # LA LETTURA VERA DELLA PRODUZIONE: e' con questa che il bot riconosce
        # la SUA parte dentro la posizione di conto. Se qualcuno le cambiasse
        # la grafia del ref, il bot non si riconoscerebbe piu' e crederebbe che
        # l'utente gli abbia chiuso tutto (o che sia tutto suo).
        abbinato = _f(campo_ordine(o, "size_matched")) or 0.0
        if abbinato <= 0.009:
            continue
        try:
            netto = BS._netto_su_selezione(
                [o], str(campo_ordine(o, "market_id") or ""),
                int(_f(campo_ordine(o, "selection_id")) or 0), {str(ref)})
        except Exception as ex:  # noqa: BLE001
            return ("la lettura di produzione e' esplosa su '%s': %s: %s"
                    % (ref, type(ex).__name__, ex))
        if abs(netto) < 0.005:
            return ("l'ordine '%s' e' abbinato per %s ma "
                    "`bot_service._netto_su_selezione` non lo riconosce come del "
                    "bot: il ref non si rilegge con la grafia con cui e' stato "
                    "piazzato (difetto 1 del 15/09)" % (ref, round(abbinato, 2)))
    return None


# ===========================================================================
# K4 — una riga viva senza ordine a mercato
# ===========================================================================
@_controllo("K4", "una riga 'open' dichiara un ordine che a mercato ESISTE "
                  "(difetto 4 del 15/09: riconciliazione con un ref diverso da "
                  "quello di piazzamento -> ordine vivo dichiarato mai piazzato)",
            quando=_q_vive)
def _k4(righe, ordini, rifiutati):
    for r in righe:
        if _e_paper(r) or str(r.get("status") or "") not in ("open", "hedged"):
            continue
        if ordine_di_riga(ordini, r) is not None:
            continue
        if not r.get("bet_id"):
            # nemmeno un bet_id: la riga non ha MAI avuto un ordine vero
            # (riserva confermata a vuoto). E' il difetto 7 del catalogo.
            return ("riga #%s (%s) e' '%s' e non porta ne' un bet_id ne' un ordine "
                    "a mercato con uno dei suoi ref %s"
                    % (r.get("id"), r.get("strategy"), r.get("status"),
                       sorted(ref_di_riga(r))))
        return ("riga #%s (%s) e' '%s' (bet_id %s) ma a mercato non esiste nessun "
                "ordine ne' col suo ref %s ne' con quel bet_id"
                % (r.get("id"), r.get("strategy"), r.get("status"), r.get("bet_id"),
                   sorted(ref_di_riga(r))))
    return None


# ===========================================================================
# K5 — il residuo dichiarato e' il residuo del mercato
# ===========================================================================
@_controllo("K5", "il RESIDUO che la riga dichiara e' quello che il mercato "
                  "dichiara dell'ordine (C.12a: senza, un parziale sembra un "
                  "ordine intero)",
            quando=_q_residuo)
def _k5(righe, ordini, rifiutati):
    for r in righe:
        if _e_paper(r):
            continue
        dichiarato = residuo_creduto(r)
        if dichiarato is None:
            continue
        o = ordine_di_riga(ordini, r)
        if o is None or _vivo(o):
            continue
        vero = _f(campo_ordine(o, "size_remaining"))
        if vero is None:
            continue
        if abs(dichiarato - vero) > EPS:
            return ("riga #%s (%s): residuo dichiarato %s, il mercato dice %s "
                    "(ordine %s)" % (r.get("id"), r.get("strategy"),
                                     round(dichiarato, 2), round(vero, 2),
                                     campo_ordine(o, "status")))
    return None


# ===========================================================================
# K6 — ogni chiusura dichiara l'apertura che chiude
# ===========================================================================
@_controllo("K6", "ogni gamba di CHIUSURA dichiara l'apertura che chiude in "
                  "COLONNA e nel META (difetto 5 del 15/09: `closes_trade_id` in "
                  "colonna ma letto nel meta -> nessuna chiusura riconosciuta, "
                  "place-and-trim rifiutato in loop e freno live sulle uscite)",
            quando=_q_chiusure)
def _k6(righe, ordini, rifiutati):
    for r in righe:
        meta = r.get("meta") or {}
        if not isinstance(meta, dict):
            meta = {}
        padre = r.get("closes_trade_id")
        if padre is None and meta.get("closes_trade_id") is None:
            continue                     # non e' una chiusura: niente da dire
        if padre is None:
            return ("riga #%s: il meta dichiara di chiudere #%s ma la COLONNA "
                    "`closes_trade_id` e' vuota"
                    % (r.get("id"), meta.get("closes_trade_id")))
        if meta.get("closes_trade_id") is None:
            return ("riga #%s chiude #%s in colonna ma il suo meta non lo dice: chi "
                    "legge il meta (place-and-trim, freno live sulle uscite, UI) "
                    "non la riconosce come chiusura (difetto 5 del 15/09)"
                    % (r.get("id"), padre))
    return None


# ===========================================================================
# K7 — nessun ordine ABBINATO resta senza una riga viva che lo dichiari
# ===========================================================================
def _q_abbinati(righe, ordini, rif) -> bool:
    return any((_f(campo_ordine(o, "size_matched")) or 0.0) > 0.009
               for o in (ordini or {}).values())


@_controllo("K7", "ogni ordine ABBINATO a mercato appartiene a una riga del bot "
                  "che lo dichiara: nessuna posizione FANTASMA (difetto 4 del "
                  "15/09 visto dall'altra parte - riconciliazione con un ref "
                  "diverso da quello di piazzamento -> la riga viene dichiarata "
                  "mai piazzata e i soldi restano a mercato senza padrone)",
            quando=_q_abbinati)
def _k7(righe, ordini, rifiutati):
    """⚠️ E' lo SPECCHIO di K4, e serve perche' K4 da solo non basta.

    K4 guarda la riga e chiede «esiste l'ordine?». Se la riconciliazione
    dichiara la riga MAI PIAZZATA (`free`) o in errore, K4 tace - la riga non e'
    piu' 'open' - ma a mercato restano i soldi abbinati, che nessuna riga
    governa piu'. E' esattamente la seconda meta' del difetto 4 del 15/09: la
    posizione c'e', il bot non lo sa, e al giro dopo ne apre un'altra.
    """
    vive = [r for r in righe if not _e_paper(r)
            and str(r.get("status") or "") in STATI_CONFERMATI]
    for ref, o in (ordini or {}).items():
        abbinato = _f(campo_ordine(o, "size_matched")) or 0.0
        if abbinato <= 0.009:
            continue
        for r in vive:
            if ref in ref_di_riga(r):
                break
            if r.get("bet_id") and str(r["bet_id"]) == str(campo_ordine(o, "bet_id") or ""):
                break
        else:
            padrone = [r for r in righe if ref in ref_di_riga(r)]
            stato = (str(padrone[0].get("status")) if padrone else "nessuna riga")
            return ("l'ordine '%s' e' ABBINATO per %s a mercato ma nessuna riga viva "
                    "del bot lo dichiara (la sua riga e' '%s'): la posizione esiste "
                    "e il bot non la governa piu'"
                    % (ref, round(abbinato, 2), stato))
    return None


# ===========================================================================
# il giro completo
# ===========================================================================
def elenco_controlli() -> List[Tuple[str, str]]:
    """(codice, regola) della famiglia K: il contratto per la copertura."""
    return list(REGISTRO)


def verifica_consapevolezza(righe: Sequence[Dict[str, Any]],
                            ordini: Optional[Dict[str, Any]] = None,
                            rifiutati: Optional[Sequence[str]] = None,
                            sollecitati: Optional[Dict[str, int]] = None
                            ) -> List[Tuple[str, str, str]]:
    """I controlli K su UN giro: la memoria del bot contro il mercato.

    Torna una lista di `(codice, regola, dettaglio)`: la `Violazione` la
    costruisce il chiamante, perche' calcio e tennis hanno due dataclass diverse
    (e diversi campi di contesto) ma la stessa identica regola.

    ⚠️ QUANDO: il giro conta come sollecitazione se c'e' almeno UNA riga viva
    (o confermata) oppure almeno un ordine a mercato. Un giro senza niente non
    e' una garanzia e non deve gonfiare la copertura.
    """
    righe = [r for r in (righe or []) if isinstance(r, dict)]
    ordini = dict(ordini or {})
    rif = {str(x) for x in (rifiutati or ())}
    out: List[Tuple[str, str, str]] = []
    for codice, regola in REGISTRO:
        quando = _QUANDO.get(codice)
        try:
            if quando is not None and not quando(righe, ordini, rif):
                continue          # nessun caso: il controllo non ha niente da dire
        except Exception as ex:  # noqa: BLE001
            out.append(("%s-ERRORE" % codice, regola,
                        "il `quando` e' esploso: %s: %s" % (type(ex).__name__, ex)))
            continue
        if sollecitati is not None:
            sollecitati[codice] = sollecitati.get(codice, 0) + 1
        try:
            det = _FUNZIONI[codice](righe, ordini, rif)
        except Exception as ex:  # noqa: BLE001 - un controllo rotto E' un referto
            out.append(("%s-ERRORE" % codice, regola,
                        "il controllo e' esploso: %s: %s" % (type(ex).__name__, ex)))
            continue
        if det:
            out.append((codice, regola, det))
    return out
