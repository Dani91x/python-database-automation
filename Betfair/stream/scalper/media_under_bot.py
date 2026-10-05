"""MEDIA UNDER - modalita' dello Scalper calcio (05/10/2026).

Specifica: ``Betfair/stream/scalper/SPEC_MEDIA_UNDER_2026-10-05.md`` (le frasi
fra virgolette sono dell'utente). Spenta di serie: la accende SOLO l'utente, a
mano, su UNA partita e UN mercato (Under 2,5 oppure Under 3,5). L'auto-mode
non la arma mai (``auto_mode.params_per_sessione`` toglie le chiavi
``media_*`` e la sessione rifiuta una riga d'origine 'auto').

COSA FA (spec par.3)
  1. FERMO -> INGRESSO (solo pre-match): mercato aperto e non in gioco, quota
     di punta dell'Under nell'intervallo, liquidita' sui due best, flusso
     stampato sui due lati, spread entro i tick, fuori dalla finestra di stop
     prima del fischio: PUNTA lo stake base alla miglior quota (LAPSE).
  2. IN POSIZIONE: appena la punta e' abbinata (anche in parte) appoggia la
     BANCA DI CHIUSURA (PERSIST) sulla stessa selezione a
     ``ultimo ingresso - tick di chiusura``, importo che pareggia i due esiti
     sulla posizione VERA. Una sola banca viva per volta.
  3. CHIUSA IN PROFITTO: banca abbinata per intero e posizione pari -> ciclo
     registrato, si torna FERMO (nuovo ciclo con lo stake base).
  4. RIENTRO (solo pre-match): quota di punta salita di almeno ``tick di
     rientro`` sull'ULTIMO ingresso abbinato e rientri sotto il massimo ->
     (a) annulla la banca e aspetta che sia morta, (b) ricalcola sulla
     posizione vera, (c) PUNTA l'importo di rientro (par.4), (d) riappoggia la
     banca a ``quota del rientro - tick``. Mai replaceOrders.
  5. MASSIMO: dopo l'ultimo rientro consentito non punta piu'; la banca resta
     appoggiata (PERSIST); lo dice una volta (attivita' CRITICAL).
  6. LIVE (dal passaggio in gioco): NESSUN ordine, nessun annullo, nessun
     riprezzo. Pubblica il riquadro "chiusura" (par.6) a ogni book.
  7. FINE: posizione pari (in gioco) o mercato regolato.

LIMITI DICHIARATI (spec par.6, par.7, par.11: scritti nel referto
``AUDIT_2026-10-05/SCALPER_MEDIA_UNDER.md``)
  * gli ordini messi a mano: la sessione dello scalper non li vede (flumine
    scarta gli ordini senza il suo ``customer_order_ref``). Dal 05/10 (giro 2,
    proposta P14 approvata dal revisore) in SOLDI VERI e a posizione aperta la
    sessione legge una volta per battito le righe dello specchio
    ``betfair_live_orders`` della selezione scritte a mano (``source`` 'account'
    = dal sito, visto dal ``reconcile_worker``; 'runner' = terminale dell'app):
    entrano SOLO nel riquadro "chiusura" (mai negli ordini o nei cicli della
    modalita'), che scrive la fonte e l'ora del dato. In prova mai; lettura
    fallita -> "solo ordini del bot", detto;
  * riavvio a posizione aperta: la posizione NON e' ricostruibile dagli ordini
    veri da questa sessione (un flumine nuovo non governa gli ordini del
    processo morto; in prova gli ordini simulati sono spariti col processo) ->
    stato BLOCCATA: nessun ordine, avviso CRITICAL (spec par.7: "Se non e'
    ricostruibile: nessun ordine, avviso critico");
  * una banca che servirebbe sotto 1,00 EUR o un rientro sotto 1,00 EUR non
    partono (il place-and-trim non e' costruito per questa modalita'): si
    dichiarano UNA volta.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence, Tuple

from flumine import BaseStrategy
from flumine.order.order import OrderStatus
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade
from flumine.utils import get_nearest_price, get_price, get_size, price_ticks_away

from ..trading.minimi_it import VIA_DIRETTA, importo_piazzabile
from .scalper_bot import CODICE_TAGLIA, ticks_between

logger = logging.getLogger(__name__)
_EPS = 1e-9

# ---------------------------------------------------------------------------
# costanti
# ---------------------------------------------------------------------------
#: l'interruttore della modalita' nei params della riga ``scalper_control``
CHIAVE_MODO = "media_mode"
#: tutte le chiavi della modalita' cominciano cosi' (l'auto-mode le toglie)
PREFISSO = "media_"
#: i soli due mercati ammessi (utente: "solo su questi due mercati")
MERCATI_AMMESSI: Tuple[str, ...] = ("OVER_UNDER_25", "OVER_UNDER_35")

#: i valori di serie della UI (spec par.5). Sono gli STESSI della scheda
#: (``frontend/src/lib/mediaUnder.ts``, ``MEDIA_UNDER_DEFAULTS``): un test di
#: contratto li confronta (catalogo par.7 punto 33). La sessione NON li usa per
#: riempire un parametro mancante: "Un parametro mancante o non valido = la
#: sessione NON parte e dice perche' (mai un valore inventato)".
#: ``media_ttl_punta_ms`` 30 000 = il ``cooldown_ms`` dello scalper (30 s): un
#: numero che il repo ha gia', non uno nuovo (motivo nel referto).
#: ``media_commissione_pct`` 5,0 = la commissione dei vettori del par.4 e il
#: ``DEFAULT_COMMISSION_PCT`` di Safe/Mike: la sessione dello scalper non ne
#: usa una (punto da confermare all'utente, scritto nel referto).
VALORI_DI_SERIE: Dict[str, Any] = {
    "media_mode": False,
    "media_stake": 10.0,
    "media_obiettivo": 0.0,
    "media_tick_chiusura": 2,
    "media_tick_rientro": 2,
    "media_max_rientri": 5,
    "media_rischio_max": 0.0,
    "media_quota_min": 1.20,
    "media_quota_max": 4.00,
    "media_min_size": 300.0,
    "media_min_flow": 10.0,
    "media_max_spread_ticks": 2,
    "media_stop_ingressi_s": 420.0,
    "media_ttl_punta_ms": 30000,
    "media_obiettivi_live": [0.0, 0.30, 1.00],
    "media_commissione_pct": 5.0,
}
#: i parametri che la riga DEVE portare quando la modalita' e' accesa
#: (``media_obiettivo`` puo' mancare: "0 o assente = automatico")
OBBLIGATORI: Tuple[str, ...] = (
    "media_mercato", "media_stake", "media_tick_chiusura", "media_tick_rientro",
    "media_max_rientri", "media_rischio_max", "media_quota_min", "media_quota_max",
    "media_min_size", "media_min_flow", "media_max_spread_ticks",
    "media_stop_ingressi_s", "media_ttl_punta_ms", "media_obiettivi_live",
    "media_commissione_pct",
)
#: tutte le chiavi che la UI puo' scrivere (whitelist della sessione)
CHIAVI_UI: Tuple[str, ...] = ("media_mode", "media_mercato", "media_obiettivo") + tuple(
    k for k in OBBLIGATORI if k != "media_mercato")

# stati del ciclo (spec par.3, macchina a stati)
FERMO = "FERMO"
INGRESSO = "INGRESSO"
IN_POSIZIONE = "IN_POSIZIONE"
RIENTRO = "RIENTRO"
MASSIMO = "MASSIMO"
LIVE = "LIVE"
FINE = "FINE"
BLOCCATA = "BLOCCATA"
STATI: Tuple[str, ...] = (FERMO, INGRESSO, IN_POSIZIONE, RIENTRO, MASSIMO, LIVE,
                          FINE, BLOCCATA)
#: stati con una posizione (o un ingresso) che il riavvio non sa ricostruire
STATI_CON_POSIZIONE = frozenset({INGRESSO, IN_POSIZIONE, RIENTRO, MASSIMO, LIVE})

#: testo della fonte del riquadro (spec par.6: "NON fingere")
FONTE_SOLO_BOT = ("solo ordini del bot: gli ordini messi a mano dal sito o dal "
                  "terminale NON sono visti da questa sessione")

# 05/10 (giro 2, spec GIRO2 par.2.3): gli ordini del CONTO nel riquadro
#: la tabella dello specchio e le colonne lette (migrazione
#: ``betfair_live_order_queue.sql`` par.1.2 + ``source``)
TABELLA_ORDINI_CONTO = "betfair_live_orders"
COLONNE_ORDINI_CONTO = ("bet_id,mode,source,market_id,selection_id,side,price,size,"
                        "size_matched,average_price_matched,status")
#: le ``source`` delle righe messe A MANO: 'account' = ordine visto solo sul
#: conto (dal sito, ``reconcile_worker._account_order_row``), 'runner' =
#: terminale manuale dell'app. Le altre (lo specchio della sessione 'scalper',
#: gli altri bot, 'bot:<ref>') NON sono ordini a mano.
SORGENTI_A_MANO = ("account", "runner")


def righe_a_mano(righe: Sequence[Dict[str, Any]], market_id: Optional[str],
                 selection_id: Optional[int]) -> List[Dict[str, Any]]:
    """Le righe dello specchio messe a mano, in soldi veri, su QUESTA selezione,
    con qualcosa di abbinato."""
    out = []
    for r in righe or []:
        try:
            if str(r.get("mode") or "") != "live":
                continue
            if str(r.get("source") or "").strip().lower() not in SORGENTI_A_MANO:
                continue
            if str(r.get("market_id") or "") != str(market_id or ""):
                continue
            if selection_id is None or int(r.get("selection_id")) != int(selection_id):
                continue
            if float(r.get("size_matched") or 0.0) <= 0.0:
                continue
        except (TypeError, ValueError):
            continue
        out.append(r)
    return out


def posizione_con_righe(pos: "Posizione", righe: Sequence[Dict[str, Any]]) -> "Posizione":
    """La posizione del bot PIU' gli abbinati delle righe a mano (stesse
    formule di ``posizione_da_ordini``, quota = ``average_price_matched``,
    se manca il prezzo chiesto)."""
    w, lo, puntato, prof, bancato = (pos.se_vince, pos.se_perde, pos.puntato,
                                     pos.profitto_punte, pos.bancato)
    for r in righe:
        m = float(r.get("size_matched") or 0.0)
        q = float(r.get("average_price_matched") or 0.0) or float(r.get("price") or 0.0)
        if m <= 0 or q <= 1.0:
            continue
        if str(r.get("side") or "").lower() == "back":
            w += m * (q - 1.0)
            lo -= m
            puntato += m
            prof += m * (q - 1.0)
        else:
            w -= m * (q - 1.0)
            lo += m
            bancato += m
    return Posizione(se_vince=w, se_perde=lo, puntato=puntato, profitto_punte=prof,
                     bancato=bancato)


# ---------------------------------------------------------------------------
# i parametri (spec par.5)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ParametriMedia:
    mercato: str
    stake: float
    obiettivo_netto: Optional[float]      # None = automatico
    tick_chiusura: int
    tick_rientro: int
    max_rientri: int
    rischio_max: float                    # 0 = spento
    quota_min: float
    quota_max: float
    min_size: float
    min_flow: float
    max_spread_ticks: int
    stop_ingressi_s: float
    ttl_punta_ms: int
    obiettivi_live: Tuple[float, ...]
    commissione: float                    # frazione (0,05 = 5 %)


def media_mode_acceso(params: Optional[Dict[str, Any]]) -> bool:
    """La modalita' e' accesa SOLO con ``media_mode`` booleano vero. Assente =
    spenta (spenta di serie: il contrario dello sniper, che e' acceso di serie)."""
    return (params or {}).get(CHIAVE_MODO) is True


def _numero(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x or x in (float("inf"), float("-inf")):
        return None
    return x


def _intero(v: Any) -> Optional[int]:
    x = _numero(v)
    if x is None or abs(x - round(x)) > 1e-9:
        return None
    return int(round(x))


def leggi_parametri(params: Optional[Dict[str, Any]]) -> Tuple[Optional[ParametriMedia], Optional[str]]:
    """(parametri, None) oppure (None, motivo). Nessun valore inventato: un
    parametro obbligatorio mancante o non valido e' un motivo."""
    p = params or {}
    mancanti = [k for k in OBBLIGATORI if k not in p or p.get(k) is None]
    if mancanti:
        return None, "parametri mancanti: %s" % ", ".join(mancanti)
    errori: List[str] = []
    mercato = str(p.get("media_mercato") or "").strip().upper()
    if mercato not in MERCATI_AMMESSI:
        errori.append("media_mercato %r non ammesso (solo %s)"
                      % (p.get("media_mercato"), " o ".join(MERCATI_AMMESSI)))
    stake = _numero(p.get("media_stake"))
    if stake is None:
        errori.append("media_stake non numerico")
    else:
        v = importo_piazzabile("back", stake)
        if v.via != VIA_DIRETTA or v.residuo > 0 or abs(v.importo - stake) > 1e-6:
            errori.append("media_stake %s non piazzabile diretto su .it (punta da 1,00 "
                          "a multipli di 0,50)" % p.get("media_stake"))
    ob = p.get("media_obiettivo")
    obiettivo: Optional[float] = None
    if ob is not None:
        x = _numero(ob)
        if x is None or x < 0:
            errori.append("media_obiettivo %r non valido (0 = automatico, altrimenti "
                          "euro netti positivi)" % ob)
        elif x > 0:
            obiettivo = x
    interi: Dict[str, int] = {}
    for k, minimo in (("media_tick_chiusura", 1), ("media_tick_rientro", 1),
                      ("media_max_rientri", 0), ("media_max_spread_ticks", 0),
                      ("media_ttl_punta_ms", 1)):
        n = _intero(p.get(k))
        if n is None or n < minimo:
            errori.append("%s %r non valido (intero >= %d)" % (k, p.get(k), minimo))
        else:
            interi[k] = n
    numeri: Dict[str, float] = {}
    for k in ("media_rischio_max", "media_min_size", "media_min_flow",
              "media_stop_ingressi_s"):
        x = _numero(p.get(k))
        if x is None or x < 0:
            errori.append("%s %r non valido (numero >= 0)" % (k, p.get(k)))
        else:
            numeri[k] = x
    qmin, qmax = _numero(p.get("media_quota_min")), _numero(p.get("media_quota_max"))
    if qmin is None or qmax is None or qmin < 1.01 or qmax > 1000.0 or qmin >= qmax:
        errori.append("intervallo di quota %r-%r non valido (1,01 <= min < max <= 1000)"
                      % (p.get("media_quota_min"), p.get("media_quota_max")))
    lista = p.get("media_obiettivi_live")
    obiettivi: List[float] = []
    if not isinstance(lista, (list, tuple)):
        errori.append("media_obiettivi_live non e' una lista")
    else:
        for x in lista:
            n = _numero(x)
            if n is None or n < 0:
                errori.append("media_obiettivi_live: valore %r non valido" % (x,))
            else:
                obiettivi.append(n)
    comm = _numero(p.get("media_commissione_pct"))
    if comm is None or comm < 0 or comm >= 100:
        errori.append("media_commissione_pct %r non valido (0-99)"
                      % (p.get("media_commissione_pct"),))
    if errori:
        return None, "; ".join(errori)
    return ParametriMedia(
        mercato=mercato, stake=float(stake), obiettivo_netto=obiettivo,
        tick_chiusura=interi["media_tick_chiusura"],
        tick_rientro=interi["media_tick_rientro"],
        max_rientri=interi["media_max_rientri"],
        rischio_max=numeri["media_rischio_max"],
        quota_min=float(qmin), quota_max=float(qmax),
        min_size=numeri["media_min_size"], min_flow=numeri["media_min_flow"],
        max_spread_ticks=interi["media_max_spread_ticks"],
        stop_ingressi_s=numeri["media_stop_ingressi_s"],
        ttl_punta_ms=interi["media_ttl_punta_ms"],
        obiettivi_live=tuple(obiettivi), commissione=float(comm) / 100.0,
    ), None


def motivo_non_parte(control: Optional[Dict[str, Any]]) -> Optional[str]:
    """Perche' una sessione con la modalita' accesa NON deve partire (None = parte).

    * origine 'auto': "questo bot non sara' automatico, scelgo io le partite";
    * modo diverso da 'maker' (il connettore bias armerebbe altro);
    * insieme a theta o all'intervallo (una sessione media under arma SOLO la
      modalita': scelta dichiarata nel referto);
    * un parametro mancante o non valido."""
    c = control or {}
    params = c.get("params") if isinstance(c.get("params"), dict) else {}
    if str(c.get("origine") or "").strip().lower() == "auto":
        return "media under armata dall'auto-mode: vietato (la partita la sceglie l'utente)"
    if str(c.get("mode") or "maker") != "maker":
        return "media under solo con mode 'maker' (mode %r)" % c.get("mode")
    if params.get("theta_mode") is True or params.get("ht_mode") is True:
        return "media under non si combina con theta o con la gamba intervallo"
    _par, motivo = leggi_parametri(params)
    return motivo


def vita_sessione_s(params: Optional[Dict[str, Any]]) -> int:
    """Secondi di vita dopo il fischio di una sessione media under: fino a fine
    partita, gli STESSI numeri dello sniper/theta (``auto_mode``): in gioco la
    modalita' segnala la chiusura finche' la partita non finisce."""
    from .auto_mode import VITA_SNIPER_THETA_S

    return int(VITA_SNIPER_THETA_S)


def posizione_aperta_nelle_stats(stats: Optional[Dict[str, Any]]) -> Optional[str]:
    """La sessione PRECEDENTE di questa partita ha lasciato una posizione della
    modalita'? Le ``stats`` della riga sopravvivono al riarmo
    (``scalper_activate`` non le azzera). Torna la descrizione o None."""
    s = stats if isinstance(stats, dict) else {}
    stato = str(s.get(PREFISSO + "stato") or "")
    puntato = _numero(s.get(PREFISSO + "totale_puntato")) or 0.0
    if stato in STATI_CON_POSIZIONE and (puntato > 0 or stato == INGRESSO):
        return ("sessione precedente in stato %s con %.2f EUR puntati (banca: %s)"
                % (stato, puntato, s.get(PREFISSO + "banca")))
    return None


# ---------------------------------------------------------------------------
# le FORMULE (spec par.4): pure, ognuna e' un test
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Posizione:
    """La posizione VERA sulla selezione dagli abbinati (punte b@p, banche l@r)."""

    se_vince: float
    se_perde: float
    puntato: float          # somma b
    profitto_punte: float   # somma b(p-1) = P
    bancato: float          # somma l abbinate

    @property
    def quota_media(self) -> Optional[float]:
        return (1.0 + self.profitto_punte / self.puntato) if self.puntato > _EPS else None

    @property
    def aperta(self) -> bool:
        return self.puntato > _EPS or self.bancato > _EPS


def posizione_da_importi(punte: Sequence[Tuple[float, float]],
                         banche: Sequence[Tuple[float, float]] = ()) -> Posizione:
    """se_vince = sum b(p-1) - sum l(r-1); se_perde = sum l - sum b."""
    s = sum(float(b) for b, _p in punte)
    pp = sum(float(b) * (float(p) - 1.0) for b, p in punte)
    lb = sum(float(l) for l, _r in banche)
    lr = sum(float(l) * (float(r) - 1.0) for l, r in banche)
    return Posizione(se_vince=pp - lr, se_perde=lb - s, puntato=s,
                     profitto_punte=pp, bancato=lb)


def _lato(o: Any) -> str:
    s = getattr(o, "side", None)
    return str(getattr(s, "value", s) or "").upper()


def abbinato(o: Any) -> Tuple[float, float]:
    """(importo abbinato, prezzo medio abbinato) coi campi VERI di flumine."""
    try:
        m = float(getattr(o, "size_matched", 0.0) or 0.0)
        p = float(getattr(o, "average_price_matched", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0, 0.0
    if m <= _EPS or p <= 1.0:
        return 0.0, 0.0
    return m, p


def posizione_da_ordini(ordini: Sequence[Any]) -> Posizione:
    """La posizione vera da ordini flumine (stesso oggetto contato una volta)."""
    visti: set = set()
    punte: List[Tuple[float, float]] = []
    banche: List[Tuple[float, float]] = []
    for o in ordini:
        if o is None or id(o) in visti:
            continue
        visti.add(id(o))
        m, p = abbinato(o)
        if m <= 0:
            continue
        (punte if _lato(o) == "BACK" else banche).append((m, p))
    return posizione_da_importi(punte, banche)


def al_centesimo(x: float) -> float:
    """Arrotondamento al centesimo, mezzo centesimo per eccesso (la banca)."""
    try:
        return float(Decimal(repr(float(x))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return 0.0


def banca_esatta(pos: Posizione, c: float) -> float:
    """Banca di chiusura alla quota c: L = (se_vince - se_perde) / c."""
    return (pos.se_vince - pos.se_perde) / float(c)


def profitto_lordo_con_banca(pos: Posizione, l: float, c: float) -> Tuple[float, float]:
    """(se vince, se perde) dopo una banca di ``l`` a ``c`` abbinata."""
    return pos.se_vince - float(l) * (float(c) - 1.0), pos.se_perde + float(l)


def rientro_esatto(pos: Posizione, q: float, c: float, t_lordo: float) -> float:
    """Importo di rientro alla quota q per chiudere a c con profitto lordo T:
    X = (c (T - se_perde) - (se_vince - se_perde)) / (q - c)."""
    return (float(c) * (float(t_lordo) - pos.se_perde)
            - (pos.se_vince - pos.se_perde)) / (float(q) - float(c))


def lordo_da_netto(netto: float, commissione: float) -> float:
    """T lordo = obiettivo netto / (1 - commissione)."""
    return float(netto) / (1.0 - float(commissione))


def netto_da_lordo(lordo: float, commissione: float) -> float:
    """Netto = lordo x (1 - commissione) se positivo, altrimenti il lordo."""
    return float(lordo) * (1.0 - float(commissione)) if lordo > 0 else float(lordo)


def obiettivo_automatico(b0: float, p0: float, c0: float) -> float:
    """"automatico" = il profitto lordo che danno gli N tick sul PRIMO ingresso
    del ciclo (b0 @p0 chiuso a c0): b0 p0 / c0 - b0."""
    return float(b0) * float(p0) / float(c0) - float(b0)


def tick_sotto(prezzo: float, n: int) -> Optional[float]:
    """La quota ``n`` tick SOTTO ``prezzo`` sulla scala vera di Betfair."""
    if prezzo is None or prezzo <= 1.0:
        return None
    p = price_ticks_away(get_nearest_price(float(prezzo)), -int(n))
    return float(p) if p and p > 1.0 else None


def punta_a_multiplo(x: float) -> Tuple[float, float]:
    """(punta piazzabile, importo esatto): la regola dei minimi .it per una
    PUNTA (``minimi_it.importo_piazzabile``: da 1,00 a multipli di 0,50 per
    difetto). 0,0 se non piazzabile diretta."""
    if x is None or x <= 0:
        return 0.0, 0.0
    v = importo_piazzabile("back", x)
    if v.via != VIA_DIRETTA:
        return 0.0, round(float(x), 2)
    return float(v.importo), round(float(x), 2)


def riquadro_chiusura(pos: Posizione, *, quota_punta: Optional[float],
                      quota_banca: Optional[float], tick: int,
                      obiettivi_netti: Sequence[float], commissione: float,
                      banca: Optional[Dict[str, Any]] = None,
                      fonte: str = FONTE_SOLO_BOT) -> Dict[str, Any]:
    """Il riquadro "chiusura" della spec par.6 (puro).

    * ``chiudi_adesso``: banca di L alla quota di banca attuale e il P&L;
    * per ogni obiettivo (euro netti): quanto PUNTARE alla quota di punta
      attuale q per chiudere a c = q - tick (multiplo di 0,50 e importo
      esatto), il rischio totale, la nuova quota media, la banca dopo."""
    out: Dict[str, Any] = {
        "fonte": fonte,
        "posizione": {
            "totale_puntato": round(pos.puntato, 2),
            "quota_media": (round(pos.quota_media, 4) if pos.quota_media else None),
            "banche_abbinate": round(pos.bancato, 2),
            "se_vince": round(pos.se_vince, 2),
            "se_perde": round(pos.se_perde, 2),
        },
        "banca": dict(banca or {"stato": "nessuna"}),
        "commissione": commissione,
        "tick": int(tick),
        "chiudi_adesso": None,
        "obiettivi": [],
    }
    if not pos.aperta:
        return out
    if quota_banca and quota_banca > 1.0:
        l_ora = al_centesimo(banca_esatta(pos, quota_banca))
        w, l = profitto_lordo_con_banca(pos, l_ora, quota_banca)
        lordo = min(w, l)
        out["chiudi_adesso"] = {"banca": l_ora, "quota": float(quota_banca),
                                "pnl_lordo": round(lordo, 2),
                                "pnl_netto": round(netto_da_lordo(lordo, commissione), 2)}
    c = tick_sotto(quota_punta, tick) if quota_punta else None
    if quota_punta and c:
        for ob in obiettivi_netti:
            t = lordo_da_netto(ob, commissione)
            x = rientro_esatto(pos, quota_punta, c, t)
            xr, xe = punta_a_multiplo(x)
            # la posizione dopo la punta, con le banche gia' abbinate
            dopo = Posizione(se_vince=pos.se_vince + xr * (quota_punta - 1.0),
                             se_perde=pos.se_perde - xr,
                             puntato=pos.puntato + xr,
                             profitto_punte=pos.profitto_punte + xr * (quota_punta - 1.0),
                             bancato=pos.bancato)
            l_dopo = al_centesimo(banca_esatta(dopo, c))
            w, l = profitto_lordo_con_banca(dopo, l_dopo, c)
            # le stesse cifre con l'importo ESATTO: l'esempio dell'utente (spec
            # par.4 D: "189,75 (199,75; 1,6525)") le scrive coi numeri esatti, il
            # par.6 col multiplo di 0,50. Si mostrano entrambe (scelta non fatta
            # da me: referto)
            xe_c = max(0.0, round(x, 2))
            esatta = Posizione(se_vince=pos.se_vince + xe_c * (quota_punta - 1.0),
                               se_perde=pos.se_perde - xe_c,
                               puntato=pos.puntato + xe_c,
                               profitto_punte=pos.profitto_punte + xe_c * (quota_punta - 1.0),
                               bancato=pos.bancato)
            out["obiettivi"].append({
                "obiettivo_netto": round(float(ob), 2),
                "quota_punta": float(quota_punta), "quota_chiusura": float(c),
                "punta": xr, "punta_esatta": round(x, 2),
                "rischio_totale": round(dopo.puntato, 2),
                "quota_media_dopo": (round(dopo.quota_media, 4) if dopo.quota_media else None),
                "banca_dopo": l_dopo,
                "profitto_lordo": round(min(w, l), 2),
                "profitto_netto": round(netto_da_lordo(min(w, l), commissione), 2),
                "rischio_totale_esatto": round(esatta.puntato, 2),
                "quota_media_dopo_esatta": (round(esatta.quota_media, 4)
                                            if esatta.quota_media else None),
                "banca_dopo_esatta": al_centesimo(banca_esatta(esatta, c)),
                "piazzabile": xr > 0,
            })
    return out


# ---------------------------------------------------------------------------
# la STRATEGIA
# ---------------------------------------------------------------------------
_VIVI = (OrderStatus.EXECUTABLE, OrderStatus.PENDING, OrderStatus.CANCELLING,
         OrderStatus.UPDATING, OrderStatus.REPLACING)


def vivo_o_in_volo(o: Any) -> bool:
    """L'ordine puo' ancora cambiare la posizione: vivo o con una richiesta in
    volo (PENDING = esito ignoto: mai un ripiazzo sopra)."""
    if o is None:
        return False
    st = getattr(o, "status", None)
    if st is None:
        return True          # creato, non ancora passato da flumine
    if st not in _VIVI:
        return False
    return float(getattr(o, "size_remaining", 0.0) or 0.0) > _EPS


def eseguibile(o: Any) -> bool:
    """Sul book con un residuo (l'unico stato in cui si chiede un annullo)."""
    return (o is not None and getattr(o, "status", None) == OrderStatus.EXECUTABLE
            and float(getattr(o, "size_remaining", 0.0) or 0.0) > _EPS)


def codice_rifiuto(o: Any) -> Optional[str]:
    """Il codice d'errore di placeOrders (stessa lettura di
    ``scalper_bot._codice_rifiuto``); 'VIOLATION' per un controllo di flumine."""
    if getattr(o, "status", None) == OrderStatus.VIOLATION:
        return "VIOLATION"
    resp = getattr(o, "responses", None)
    pr = getattr(resp, "place_response", None) if resp is not None else None
    if pr is None or str(getattr(pr, "status", "") or "") != "FAILURE":
        return None
    codice = getattr(pr, "error_code", None)
    return str(codice) if codice else "FAILURE"


# 05/10 (giro 2): perche' NON si apre, coi codici dei motivi di non ingresso
# che la strategia conta nelle sue stats (``non_ingresso``) e il referto stampa
_APRIRE_FRENO = "freno o stop della sessione"
_APRIRE_FISCHIO = "fischio d'inizio non leggibile"
_APRIRE_FINESTRA = "dentro la finestra di stop prima del fischio"
_APRIRE_RIFIUTO = "attesa dopo un rifiuto di Betfair"
_MOTIVO_DA_APRIRE = {_APRIRE_FRENO: "freno", _APRIRE_FISCHIO: "fischio_ignoto",
                     _APRIRE_FINESTRA: "finestra_fischio", _APRIRE_RIFIUTO: "rifiuto"}
#: i codici dei motivi di non ingresso, con la frase per chi legge il referto
MOTIVI_NON_INGRESSO: Dict[str, str] = {
    "freno": "freno o stop della sessione",
    "fischio_ignoto": "fischio d'inizio non leggibile",
    "finestra_fischio": "dentro la finestra di stop prima del fischio",
    "rifiuto": "attesa dopo un rifiuto di Betfair",
    "prezzi_mancanti": "manca il miglior prezzo di punta o di banca",
    "quota_fuori": "quota fuori dall'intervallo (quota min / max)",
    "liquidita": "liquidita' sotto il minimo al miglior prezzo (min size)",
    "spread": "spread piu' largo del massimo in tick",
    "riscaldamento": "attesa iniziale (riscaldamento del flusso)",
    "flusso": "flusso degli scambi sotto il minimo",
    "punta_non_piazzata": "punta d'ingresso non partita (rifiutata o soldi veri fermi)",
}


class MediaUnderStrategy(BaseStrategy):
    """La modalita' "media under" (vedi il docstring del modulo)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        cfg = dict(kwargs.pop("media_params", {}) or {})
        self.event_sink = kwargs.pop("event_sink", None)
        super().__init__(*args, **kwargs)
        par, motivo = leggi_parametri(cfg)
        if par is None:
            raise ValueError("media under: %s" % motivo)
        self.par: ParametriMedia = par
        # gli stessi parametri in un dizionario semplice: li confronta la parita'
        # paper/live del banco (S6), che legge solo attributi semplici
        self.parametri: Dict[str, Any] = dict(vars(par))
        # flusso: gli stessi concetti (e numeri) dello scalper (VALIDATED_PARAMS)
        self.flow_window_ms: int = int(cfg.get("flow_window_ms", 90000))
        self.warmup_ms: int = int(cfg.get("warmup_ms", 60000))
        # nomi dei runner dal catalogo: (market_id, selection_id) -> nome
        self.runner_names: Dict[Tuple[str, int], str] = dict(cfg.get("runner_names") or {})
        # freno dei soldi veri (sessione live): None = prova
        self.freno_live: Optional[Any] = None
        self._apertura_ferma: Optional[str] = None
        self.force_flat: bool = False
        # riavvio a posizione aperta: non ricostruibile -> BLOCCATA
        self.riavvio: Optional[str] = cfg.get("riavvio_aperto") or None
        self.stato: str = BLOCCATA if self.riavvio else FERMO
        # mercato e selezione (bloccati al primo book del tipo scelto)
        self._mid: Optional[str] = None
        self._sid: Optional[int] = None
        self._ko_ms: Optional[float] = None
        # il ciclo
        self._ordini: List[Any] = []          # TUTTI gli ordini del ciclo corrente
        self._punta: Optional[Any] = None     # punta (ingresso o rientro) in corso
        self._punta_ms: float = 0.0
        self._punta_rientro: bool = False
        self._banca: Optional[Any] = None     # la banca di chiusura (una sola)
        self._ultimo_ingresso: Optional[float] = None
        self._rientri: int = 0
        self._t_lordo: Optional[float] = None
        self._rientri_bloccati: Optional[str] = None
        self._rientro_annullo: bool = False   # RIENTRO, fase (a): banca in annullo
        self._dichiarati: set = set()
        self._rifiuti_visti: set = set()
        self._rifiuti: int = 0
        # freno dopo un rifiuto: le punte e la banca hanno ciascuna il suo (un
        # rifiuto di una punta non tiene la posizione senza banca)
        self._fermo_punte_ms: float = 0.0
        self._fermo_banca_ms: float = 0.0
        self._ora_ms: float = 0.0
        self._sospeso: bool = False
        self._banca_vista: Dict[str, Any] = {}
        self._esito: Optional[Dict[str, Any]] = None
        # flusso stampato (prints) per lato
        self._prev_trd: Dict[float, float] = {}
        self._flow: List[Tuple[float, float, float]] = []
        self._first_seen: Optional[float] = None
        self._last_bb: Optional[float] = None
        self._last_bl: Optional[float] = None
        self.chiusura: Optional[Dict[str, Any]] = None
        # 05/10 (giro 2): l'ultima lettura degli ordini del conto fatta dalla
        # sessione (None = nessuna lettura: in prova, o posizione chiusa)
        self._conto: Optional[Dict[str, Any]] = None
        self.stats: Dict[str, Any] = {
            "stato": self.stato, "mercato": par.mercato, "market_id": None,
            "selection_id": None, "rientri": 0, "max_rientri": par.max_rientri,
            "totale_puntato": 0.0, "quota_media": None, "se_vince": 0.0, "se_perde": 0.0,
            "banca": {"stato": "nessuna"}, "cicli_chiusi": 0, "pnl_chiuso_lordo": 0.0,
            "obiettivo_lordo": None, "rientri_bloccati": None, "ordini": 0,
            "fonte": FONTE_SOLO_BOT, "chiusura": None, "esito_regolato": None,
            "pnl_settled": 0.0, "riavvio": self.riavvio,
            # 05/10 (giro 2): quante volte (book) ogni filtro ha fermato l'ingresso
            "non_ingresso": {},
        }
        self._settled: set = set()

    # ------------------------------------------------------------------ util
    def _emit(self, kind: str, **payload: Any) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(kind, payload)
        except Exception:  # noqa: BLE001 - il sink non rompe mai il bot
            logger.debug("[media] event_sink KO su %s", kind, exc_info=True)

    def _una_volta(self, chiave: str, kind: str, **payload: Any) -> None:
        if chiave in self._dichiarati:
            return
        self._dichiarati.add(chiave)
        self._emit(kind, **payload)

    def _ko_epoch_ms(self, mb: Any) -> Optional[float]:
        if self._ko_ms is not None:
            return self._ko_ms
        md = getattr(mb, "market_definition", None)
        mt = getattr(md, "market_time", None) if md is not None else None
        if callable(getattr(mt, "timestamp", None)):
            try:
                if getattr(mt, "tzinfo", None) is None:
                    mt = mt.replace(tzinfo=_dt.timezone.utc)
                self._ko_ms = float(mt.timestamp()) * 1000.0
            except (TypeError, ValueError, OSError, OverflowError):
                self._ko_ms = None
        return self._ko_ms

    def _e_under(self, mb: Any, sid: int) -> bool:
        """L'Under: per NOME dal catalogo se noto, altrimenti sortPriority 1
        (la convenzione Betfair che usa lo sniper)."""
        nome = self.runner_names.get((str(mb.market_id), int(sid)))
        if nome:
            return str(nome).strip().lower().startswith("under")
        md = getattr(mb, "market_definition", None)
        for rd in (getattr(md, "runners", None) or []):
            if int(getattr(rd, "selection_id", -1)) == int(sid):
                return int(getattr(rd, "sort_priority", 0) or 0) == 1
        return False

    def is_flat(self) -> bool:
        """Nessun ordine vivo e la posizione del ciclo pari (stop della sessione).
        A mercato regolato non c'e' piu' esposizione."""
        if self._esito is not None:
            return True
        if any(vivo_o_in_volo(o) for o in self._ordini):
            return False
        pos = posizione_da_ordini(self._ordini)
        return abs(pos.se_vince - pos.se_perde) <= self._toll_pari()

    def _toll_pari(self) -> float:
        """Pari entro l'arrotondamento al centesimo della banca (c x 0,005)."""
        c = self._quota_chiusura() or 2.0
        return 0.02 + 0.005 * float(c)

    def _quota_chiusura(self) -> Optional[float]:
        if self._ultimo_ingresso is None:
            return None
        return tick_sotto(self._ultimo_ingresso, self.par.tick_chiusura)

    # -------------------------------------------------------------- flumine
    def check_market_book(self, market: Any, market_book: Any) -> bool:
        md = getattr(market_book, "market_definition", None)
        mtype = getattr(md, "market_type", None) or getattr(market, "market_type", None)
        if mtype != self.par.mercato:
            return False
        if self._mid is None:
            self._mid = str(market_book.market_id)
            self.stats["market_id"] = self._mid
        elif str(market_book.market_id) != self._mid:
            self._una_volta("secondo_mercato", "media_secondo_mercato", level="WARN",
                            market_id=str(market_book.market_id),
                            msg="un secondo mercato %s per la stessa partita: ignorato"
                                % mtype)
            return False
        # anche SOSPESO: lo stato si dichiara (nessun ordine); il CHIUSO lo
        # gestisce ``process_closed_market``
        return getattr(market_book, "status", None) in ("OPEN", "SUSPENDED")

    def process_market_book(self, market: Any, market_book: Any) -> None:
        now = getattr(market_book, "publish_time_epoch", None)
        if now is None:
            return
        now = float(now)
        self._ora_ms = now
        runner = None
        for r in getattr(market_book, "runners", None) or []:
            if self._e_under(market_book, int(r.selection_id)):
                runner = r
                break
        if runner is None:
            self._una_volta("senza_under", "media_senza_under", level="CRITICAL",
                            market_id=self._mid, msg="nessuna selezione Under nel book: "
                                                     "nessun ordine")
            return
        if self._sid is None:
            self._sid = int(runner.selection_id)
            self.stats["selection_id"] = self._sid
        ex = getattr(runner, "ex", None)
        bb = get_price(ex.available_to_back, 0) if ex is not None else None
        bl = get_price(ex.available_to_lay, 0) if ex is not None else None
        sb = get_size(ex.available_to_back, 0) if ex is not None else None
        sl = get_size(ex.available_to_lay, 0) if ex is not None else None
        self._aggiorna_flusso(now, ex)
        self._last_bb, self._last_bl = bb, bl
        inplay = bool(getattr(market_book, "inplay", False))
        aperto = (getattr(market_book, "status", None) == "OPEN"
                  and getattr(runner, "status", None) == "ACTIVE")
        self._leggi_rifiuti(now)
        if self.stato == BLOCCATA:
            self._una_volta("bloccata", "media_riavvio_non_ricostruibile", level="CRITICAL",
                            market_id=self._mid, motivo=self.riavvio,
                            msg="riavvio a posizione aperta: la posizione NON e' "
                                "ricostruibile dagli ordini veri da questa sessione. "
                                "Nessun ordine: verificala sul conto e chiudila a mano")
            self._pubblica(None, bb, bl)
            return
        if inplay:
            self._in_live(now, aperto, bb, bl)
            return
        if not aperto:
            if not self._sospeso:
                self._sospeso = True
                self._emit("media_sospeso", market_id=self._mid,
                           msg="mercato sospeso prima del fischio: nessun ordine nuovo")
            self._pubblica(None, bb, bl)
            return
        if self._sospeso:
            self._sospeso = False
            self._emit("media_riaperto", market_id=self._mid, msg="mercato riaperto")
        self._pre_match(market, market_book, now, bb, bl, sb, sl)
        self._pubblica(None, bb, bl)

    # ------------------------------------------------------------ pre-match
    def _puo_aprire(self, now: float) -> Optional[str]:
        """Perche' NON si puo' aprire (ingresso o rientro) adesso, o None."""
        if self.force_flat:
            return _APRIRE_FRENO
        ko = self._ko_ms
        if ko is None:
            return _APRIRE_FISCHIO
        if now >= ko - self.par.stop_ingressi_s * 1000.0:
            return _APRIRE_FINESTRA
        if now < self._fermo_punte_ms:
            return _APRIRE_RIFIUTO
        return None

    def _pre_match(self, market: Any, mb: Any, now: float, bb: Optional[float],
                   bl: Optional[float], sb: Optional[float], sl: Optional[float]) -> None:
        self._ko_epoch_ms(mb)
        # 1. la punta in corso (ingresso o rientro)
        if self._punta is not None:
            p = self._punta
            if vivo_o_in_volo(p):
                if abbinato(p)[0] > 0:
                    # "appena la punta e' abbinata (anche in parte)"
                    self._assicura_banca(market, now, prezzo_ingresso=float(
                        p.order_type.price))
                if (now - self._punta_ms >= self.par.ttl_punta_ms and eseguibile(p)):
                    self._annulla(market, p, "punta non abbinata entro %d ms"
                                  % self.par.ttl_punta_ms)
                return
            self._punta_morta(p)
        # 2. la banca in annullo per un rientro (fase a): l'annullo si chiede
        # appena la banca e' sul book (anche se al momento della decisione era
        # ancora in volo) e si ASPETTA che sia morta
        if self.stato == RIENTRO and self._rientro_annullo:
            if self._banca is not None and vivo_o_in_volo(self._banca):
                if eseguibile(self._banca):
                    self._annulla(market, self._banca, "rientro: la banca si ritira "
                                                       "prima della punta")
                return
            self._rientro_annullo = False
            if self._ciclo_chiuso(now):
                return
            self._banca = None
            self._punta_di_rientro(market, now, bb)
            if self._punta is not None:
                # (d) la banca si riappoggia DOPO la punta di rientro
                return
            if self.stato == RIENTRO:
                self.stato = IN_POSIZIONE
        # 3. ciclo chiuso?
        if self._ciclo_chiuso(now):
            return
        pos = posizione_da_ordini(self._ordini)
        if self.stato == FERMO:
            self._forse_ingresso(market, now, bb, bl, sb, sl)
            return
        if not pos.aperta:
            return
        # 4. la banca di chiusura sulla posizione vera
        self._assicura_banca(market, now, prezzo_ingresso=self._ultimo_ingresso)
        # 5. il rientro
        if self.stato == IN_POSIZIONE:
            self._forse_rientro(market, now, bb, pos)

    def _perche_non_entra(self, now: float, bb: Optional[float], bl: Optional[float],
                          sb: Optional[float], sl: Optional[float]) -> Optional[str]:
        """Il PRIMO filtro che ferma l'ingresso su questo book (codice di
        ``MOTIVI_NON_INGRESSO``), o None se si puo' puntare. Stessi controlli,
        nello stesso ordine, di prima del 05/10 (giro 2): qui si da' solo il nome."""
        aprire = self._puo_aprire(now)
        if aprire:
            return _MOTIVO_DA_APRIRE.get(aprire, "freno")
        if bb is None or bl is None:
            return "prezzi_mancanti"
        if not (self.par.quota_min <= bb <= self.par.quota_max):
            return "quota_fuori"
        if (sb or 0.0) < self.par.min_size or (sl or 0.0) < self.par.min_size:
            return "liquidita"
        st = ticks_between(bb, bl)
        if st is None or st > self.par.max_spread_ticks:
            return "spread"
        if self._first_seen is None or now - self._first_seen < self.warmup_ms:
            return "riscaldamento"
        fb, fl = self._somme_flusso(now)
        if self.par.min_flow > 0 and (fb < self.par.min_flow or fl < self.par.min_flow):
            return "flusso"
        return None

    def _conta_non_ingresso(self, motivo: str) -> None:
        conti = self.stats.setdefault("non_ingresso", {})
        conti[motivo] = int(conti.get(motivo, 0)) + 1

    def _forse_ingresso(self, market: Any, now: float, bb: Optional[float],
                        bl: Optional[float], sb: Optional[float], sl: Optional[float]) -> None:
        motivo = self._perche_non_entra(now, bb, bl, sb, sl)
        if motivo is not None:
            self._conta_non_ingresso(motivo)
            return
        prezzo = float(get_nearest_price(bb))
        o = self._piazza(market, "BACK", prezzo, self.par.stake, apertura=True,
                         persistenza="LAPSE")
        if o is None:
            self._conta_non_ingresso("punta_non_piazzata")
            return
        self._punta, self._punta_ms, self._punta_rientro = o, now, False
        self.stato = INGRESSO
        self._emit("media_ingresso", market_id=self._mid, selection_id=self._sid,
                   prezzo=prezzo, importo=self.par.stake,
                   msg="punta d'ingresso %.2f EUR @%.2f" % (self.par.stake, prezzo))

    def _punta_morta(self, p: Any) -> None:
        """La punta (ingresso o rientro) non puo' piu' cambiare: si contabilizza.
        In gioco (o bloccata) lo stato non cambia: la modalita' ha finito di
        operare."""
        self._punta = None
        fisso = self.stato in (LIVE, FINE, BLOCCATA)
        stato_prima = self.stato
        m, _avg = abbinato(p)
        prezzo = float(p.order_type.price)
        if m > 0:
            self._ultimo_ingresso = prezzo
            if self._punta_rientro:
                self._rientri += 1
            elif self._t_lordo is None:
                c0 = tick_sotto(prezzo, self.par.tick_chiusura)
                if self.par.obiettivo_netto is not None:
                    self._t_lordo = lordo_da_netto(self.par.obiettivo_netto,
                                                   self.par.commissione)
                elif c0:
                    self._t_lordo = obiettivo_automatico(m, prezzo, c0)
            self.stato = IN_POSIZIONE
            self._emit("media_punta_abbinata", market_id=self._mid, selection_id=self._sid,
                       rientro=self._punta_rientro, abbinato=round(m, 2), prezzo=prezzo,
                       rientri=self._rientri, obiettivo_lordo=self._t_lordo,
                       msg="%s abbinata %.2f EUR @%.2f (rientri fatti %d)"
                           % ("punta di rientro" if self._punta_rientro
                              else "punta d'ingresso", m, prezzo, self._rientri))
            if self._rientri >= self.par.max_rientri:
                self.stato = MASSIMO
                self._una_volta("massimo", "media_massimo", level="CRITICAL",
                                market_id=self._mid, rientri=self._rientri,
                                msg="massimo dei rientri raggiunto (%d): nessuna punta "
                                    "in piu', resta appoggiata la banca di chiusura "
                                    "(PERSIST)" % self._rientri)
        else:
            pos = posizione_da_ordini(self._ordini)
            self.stato = IN_POSIZIONE if pos.aperta else FERMO
            self._emit("media_punta_non_abbinata", market_id=self._mid,
                       rientro=self._punta_rientro, prezzo=prezzo,
                       msg="punta non abbinata e morta: si rivaluta dal book corrente")
        if fisso:
            self.stato = stato_prima

    def _forse_rientro(self, market: Any, now: float, bb: Optional[float],
                       pos: Posizione) -> None:
        if self._rientri_bloccati or self._ultimo_ingresso is None or bb is None:
            return
        if self._puo_aprire(now):
            return
        su = ticks_between(self._ultimo_ingresso, bb)
        if su is None or su < self.par.tick_rientro:
            return
        if self._rientri >= self.par.max_rientri:
            return
        piano = self._piano_rientro(pos, bb)
        if piano is None:
            return
        # (a) annulla la banca viva e ASPETTA che sia morta
        self.stato = RIENTRO
        if self._banca is not None and vivo_o_in_volo(self._banca):
            self._rientro_annullo = True
            if eseguibile(self._banca):
                self._annulla(market, self._banca, "rientro: la banca si ritira prima "
                                                   "della punta")
            return
        self._banca = None
        self._punta_di_rientro(market, now, bb)
        if self._punta is None and self.stato == RIENTRO:
            self.stato = IN_POSIZIONE
            # rientro non partito: la banca torna subito sulla posizione
            self._assicura_banca(market, now, prezzo_ingresso=self._ultimo_ingresso)

    def _piano_rientro(self, pos: Posizione, q: float) -> Optional[Tuple[float, float, float]]:
        """(punta, importo esatto, c) del rientro alla quota q, o None se il
        rientro non si fa (bloccato dal rischio massimo o non piazzabile)."""
        q = float(get_nearest_price(q))
        c = tick_sotto(q, self.par.tick_chiusura)
        if c is None or self._t_lordo is None:
            return None
        x = rientro_esatto(pos, q, c, self._t_lordo)
        xr, xe = punta_a_multiplo(x)
        if xr <= 0:
            self._una_volta("rientro_np_%d" % self._rientri, "media_rientro_non_piazzabile",
                            level="CRITICAL", market_id=self._mid, importo_esatto=xe,
                            msg="rientro di %.2f EUR non piazzabile diretto su .it "
                                "(sotto 1,00): nessun rientro" % xe)
            return None
        if self.par.rischio_max > 0 and pos.puntato + xr > self.par.rischio_max + _EPS:
            self._rientri_bloccati = "rischio_max"
            self.stats["rientri_bloccati"] = self._rientri_bloccati
            self._emit("media_rientro_bloccato", level="CRITICAL", market_id=self._mid,
                       motivo="rischio_max", totale_puntato=round(pos.puntato, 2),
                       rientro=xr, rischio_max=self.par.rischio_max,
                       msg="rientro BLOCCATO: %.2f puntati + %.2f di rientro superano il "
                           "rischio massimo %.2f EUR. Nessun altro rientro; la banca "
                           "di chiusura resta appoggiata"
                           % (pos.puntato, xr, self.par.rischio_max))
            return None
        return xr, xe, c

    def _punta_di_rientro(self, market: Any, now: float, bb: Optional[float]) -> None:
        """(b) ricalcolo sulla posizione VERA, (c) la punta di rientro. La
        condizione del rientro si rilegge sul book corrente."""
        if bb is None or self._ultimo_ingresso is None or self._puo_aprire(now):
            return
        su = ticks_between(self._ultimo_ingresso, bb)
        if su is None or su < self.par.tick_rientro or self._rientri >= self.par.max_rientri:
            return
        pos = posizione_da_ordini(self._ordini)
        piano = self._piano_rientro(pos, bb)
        if piano is None:
            return
        xr, xe, c = piano
        q = float(get_nearest_price(bb))
        o = self._piazza(market, "BACK", q, xr, apertura=True, persistenza="LAPSE")
        if o is None:
            return
        self._punta, self._punta_ms, self._punta_rientro = o, now, True
        self._emit("media_rientro", market_id=self._mid, selection_id=self._sid,
                   rientro=self._rientri + 1, prezzo=q, importo=xr, importo_esatto=xe,
                   chiusura=c, totale_puntato=round(pos.puntato, 2),
                   se_vince=round(pos.se_vince, 4), se_perde=round(pos.se_perde, 4),
                   obiettivo_lordo=self._t_lordo,
                   msg="rientro %d: punta %.2f EUR @%.2f (esatto %.2f) per chiudere a %.2f"
                       % (self._rientri + 1, xr, q, xe, c))

    def _assicura_banca(self, market: Any, now: float,
                        prezzo_ingresso: Optional[float]) -> None:
        """Una sola banca di chiusura viva, PERSIST, a ``ingresso - tick``, per
        l'importo che pareggia la posizione VERA (al centesimo). Se l'importo o
        la quota cambiano: annullo, attesa che sia morta, nuova banca."""
        if prezzo_ingresso is None:
            return
        c = tick_sotto(prezzo_ingresso, self.par.tick_chiusura)
        if c is None:
            return
        pos = posizione_da_ordini(self._ordini)
        b = self._banca
        if b is not None:
            if vivo_o_in_volo(b):
                resto = float(getattr(b, "size_remaining", 0.0) or 0.0)
                # la parte gia' abbinata della banca e' nella posizione: il resto
                # deve essere quanto pareggia ancora la posizione
                voluto = al_centesimo(banca_esatta(pos, c))
                if abs(float(b.order_type.price) - c) < 1e-9 and abs(resto - voluto) <= 0.01:
                    return
                if eseguibile(b):
                    self._annulla(market, b, "banca da riallineare: %.2f @%.2f invece di "
                                             "%.2f @%.2f" % (resto, float(b.order_type.price),
                                                             voluto, c))
                return
            self._banca = None
        voluto = al_centesimo(banca_esatta(pos, c))
        if voluto <= 0.0:
            return
        if now < self._fermo_banca_ms:
            return
        v = importo_piazzabile("lay", voluto)
        if v.via != VIA_DIRETTA:
            self._una_volta("banca_np_%s_%s" % (voluto, c), "media_residuo", level="CRITICAL",
                            market_id=self._mid, selection_id=self._sid, importo=voluto,
                            quota=c, msg="banca di chiusura di %.2f EUR @%.2f non "
                                         "piazzabile diretta (sotto 1,00): resta "
                                         "scoperta e DICHIARATA, la chiudi tu" % (voluto, c))
            return
        o = self._piazza(market, "LAY", c, voluto, apertura=False, persistenza="PERSIST")
        if o is None:
            return
        self._banca = o
        self._emit("media_banca", market_id=self._mid, selection_id=self._sid,
                   prezzo=c, importo=voluto, totale_puntato=round(pos.puntato, 2),
                   se_vince=round(pos.se_vince, 4), se_perde=round(pos.se_perde, 4),
                   msg="banca di chiusura %.2f EUR @%.2f (PERSIST)" % (voluto, c))

    def _ciclo_chiuso(self, now: float) -> bool:
        """Banca abbinata e posizione pari, nessun ordine del ciclo vivo."""
        if any(vivo_o_in_volo(o) for o in self._ordini):
            return False
        if not any(_lato(o) == "LAY" and abbinato(o)[0] > 0 for o in self._ordini):
            return False
        pos = posizione_da_ordini(self._ordini)
        if pos.puntato <= _EPS:
            return False
        if abs(pos.se_vince - pos.se_perde) > self._toll_pari():
            return False
        lordo = min(pos.se_vince, pos.se_perde)
        self.stats["cicli_chiusi"] = int(self.stats["cicli_chiusi"]) + 1
        self.stats["pnl_chiuso_lordo"] = round(float(self.stats["pnl_chiuso_lordo"]) + lordo, 4)
        self._emit("media_ciclo_chiuso", market_id=self._mid, selection_id=self._sid,
                   rientri=self._rientri, totale_puntato=round(pos.puntato, 2),
                   profitto_lordo=round(lordo, 4),
                   profitto_netto=round(netto_da_lordo(lordo, self.par.commissione), 4),
                   msg="ciclo chiuso in profitto: lordo %.2f, netto %.2f, rientri %d"
                       % (lordo, netto_da_lordo(lordo, self.par.commissione), self._rientri))
        inplay = self.stato == LIVE
        self._nuovo_ciclo()
        self.stato = FINE if inplay else FERMO
        return True

    def _nuovo_ciclo(self) -> None:
        self._ordini = []
        self._punta = None
        self._banca = None
        self._ultimo_ingresso = None
        self._rientri = 0
        self._t_lordo = None
        self._rientri_bloccati = None
        self._rientro_annullo = False
        self._banca_vista = {}
        self._dichiarati.discard("massimo")
        self.stats["rientri_bloccati"] = None

    # ------------------------------------------------------------------ live
    def _in_live(self, now: float, aperto: bool, bb: Optional[float],
                 bl: Optional[float]) -> None:
        """In gioco: NESSUN ordine, nessun annullo, nessun riprezzo."""
        pos = posizione_da_ordini(self._ordini)
        if self.stato not in (LIVE, FINE):
            if pos.aperta:
                self.stato = LIVE
                self._emit("media_live", level="CRITICAL", market_id=self._mid,
                           totale_puntato=round(pos.puntato, 2),
                           banca=self._descrivi_banca(),
                           msg="partita in gioco con %.2f EUR puntati: la modalita' non "
                               "piazza piu' niente, la banca PERSIST resta dov'e'. "
                               "Gestisci tu la chiusura (riquadro chiusura)" % pos.puntato)
            else:
                self.stato = FINE
                self._emit("media_live", market_id=self._mid, totale_puntato=0.0,
                           msg="partita in gioco senza posizione: nessun ordine")
        if not aperto:
            if not self._sospeso:
                self._sospeso = True
                self._emit("media_sospeso", level="CRITICAL" if pos.aperta else "INFO",
                           market_id=self._mid, banca=self._descrivi_banca(),
                           msg="mercato SOSPESO in gioco (gol o altro): nessun ordine")
        elif self._sospeso:
            self._sospeso = False
            self._emit("media_riaperto", market_id=self._mid, banca=self._descrivi_banca(),
                       msg="mercato riaperto in gioco")
        self._segui_banca_in_live()
        if self.stato == LIVE and self._ciclo_chiuso(now):
            return
        self._pubblica(pos, bb, bl, forza=True)

    def _segui_banca_in_live(self) -> None:
        """Cambi rilevanti della banca in gioco: abbinata (anche in parte),
        caduta (Betfair l'ha annullata: "la banca non e' piu' a mercato")."""
        b = self._banca
        if b is None:
            return
        m, _a = abbinato(b)
        vista = self._banca_vista
        if m > float(vista.get("abbinato", 0.0)) + 0.005:
            self._emit("media_banca_abbinata", level="CRITICAL", market_id=self._mid,
                       abbinato=round(m, 2), importo=float(b.order_type.size),
                       msg="banca di chiusura abbinata %.2f su %.2f"
                           % (m, float(b.order_type.size)))
            vista["abbinato"] = m
        if not vivo_o_in_volo(b) and m + 0.005 < float(b.order_type.size) \
                and not vista.get("caduta"):
            vista["caduta"] = True
            self._emit("media_banca_caduta", level="CRITICAL", market_id=self._mid,
                       abbinato=round(m, 2), importo=float(b.order_type.size),
                       msg="la banca non e' piu' a mercato (annullata da Betfair o "
                           "scaduta): abbinato %.2f su %.2f" % (m, float(b.order_type.size)))

    def _descrivi_banca(self) -> Dict[str, Any]:
        b = self._banca
        if b is None:
            return {"stato": "nessuna", "testo": "nessuna banca appoggiata"}
        m, _a = abbinato(b)
        size = float(b.order_type.size)
        if vivo_o_in_volo(b):
            stato = "viva" if m <= 0 else "abbinata_in_parte"
        elif m + 0.005 >= size:
            stato = "abbinata"
        else:
            stato = "caduta"
        testo = {"viva": "appoggiata, non ancora abbinata",
                 "abbinata_in_parte": "appoggiata, abbinata in parte",
                 "abbinata": "abbinata per intero",
                 "caduta": "la banca non e' piu' a mercato"}[stato]
        return {"stato": stato, "importo": size, "quota": float(b.order_type.price),
                "abbinato": round(m, 2),
                "persistenza": str(getattr(b.order_type, "persistence_type", "") or ""),
                "testo": testo}

    # ------------------------------------------------------------- ordini
    def _piazza(self, market: Any, lato: str, prezzo: float, importo: float, *,
                apertura: bool, persistenza: str) -> Optional[Any]:
        """Un ordine VERO su flumine. Le APERTURE (ingresso, rientro) chiedono il
        freno dei soldi veri; la banca di chiusura parte sempre."""
        if apertura and self.freno_live is not None:
            try:
                motivo = self.freno_live()
            except Exception as ex:  # noqa: BLE001 - non valutabile = fermo
                motivo = "freni_live_non_letti: %s" % str(ex)[:80]
            if motivo:
                if self._apertura_ferma != motivo:
                    self._apertura_ferma = motivo
                    self._emit("apertura_live_fermata", level="CRITICAL",
                               market_id=self._mid, selection_id=self._sid, side=lato,
                               motivo=motivo,
                               msg="soldi veri NON serviti (%s): nessuna apertura; la "
                                   "banca di chiusura parte" % motivo)
                return None
            self._apertura_ferma = None
        importo = round(float(importo), 2)
        if importo <= 0 or prezzo <= 1.0 or self._sid is None or self._mid is None:
            return None
        tr = Trade(market_id=self._mid, selection_id=int(self._sid), handicap=0.0,
                   strategy=self)
        o = tr.create_order(side=lato, order_type=LimitOrder(
            price=float(prezzo), size=importo,
            persistence_type="PERSIST" if persistenza == "PERSIST" else "LAPSE"))
        self.stats["ordini"] = int(self.stats["ordini"]) + 1
        try:
            accettato = market.place_order(o)
        except Exception as ex:  # noqa: BLE001 - esito non leggibile: rifiuto
            logger.warning("[media] place_order KO: %s", ex)
            accettato = False
        if accettato is False or getattr(o, "status", None) == OrderStatus.VIOLATION:
            # catalogo par.7 punto 2: il rifiuto si LEGGE (place_order False,
            # ordine mai nel blotter): nessuna posizione creduta, freno
            self._registra_rifiuto(o, codice_rifiuto(o) or "VIOLATION", self._ora_ms)
            return None
        self._ordini.append(o)
        return o

    def _annulla(self, market: Any, o: Any, motivo: str) -> None:
        try:
            market.cancel_order(o)
        except Exception:  # noqa: BLE001
            logger.debug("[media] annullo KO", exc_info=True)
            return
        self._emit("media_annullo", market_id=self._mid, side=_lato(o),
                   prezzo=float(o.order_type.price),
                   resto=float(getattr(o, "size_remaining", 0.0) or 0.0), motivo=motivo)

    def _leggi_rifiuti(self, now: float) -> None:
        """Un ordine RIFIUTATO da Betfair (esito FAILURE arrivato dopo il
        piazzamento), niente abbinato: ``_registra_rifiuto``."""
        for o in list(self._ordini):
            oid = getattr(o, "id", None) or id(o)
            if oid in self._rifiuti_visti:
                continue
            codice = codice_rifiuto(o)
            if codice is None or abbinato(o)[0] > 0:
                continue
            self._registra_rifiuto(o, codice, now)

    def _registra_rifiuto(self, o: Any, codice: str, now: float) -> None:
        """Nessun ripiazzo prima di 1, 2, 4, 8, 16 poi 30 s di mercato (il freno
        dei rifiuti di taglia dello scalper, ``scalper_bot._leggi_rifiuti_taglia``),
        separato per punte e banca. CRITICAL al primo, WARN ai successivi."""
        oid = getattr(o, "id", None) or id(o)
        if oid in self._rifiuti_visti:
            return
        self._rifiuti_visti.add(oid)
        self._rifiuti += 1
        attesa_s = min(30, 2 ** (self._rifiuti - 1))
        if _lato(o) == "BACK":
            self._fermo_punte_ms = now + attesa_s * 1000.0
        else:
            self._fermo_banca_ms = now + attesa_s * 1000.0
        if o is self._punta:
            self._punta_morta(o)
        if o is self._banca:
            self._banca = None
        self._emit("media_rifiuto", level="CRITICAL" if self._rifiuti == 1 else "WARN",
                   market_id=self._mid, side=_lato(o), codice=codice,
                   prezzo=float(o.order_type.price), importo=float(o.order_type.size),
                   riprovo_fra_s=attesa_s,
                   msg="Betfair ha rifiutato l'ordine (%s%s): nessun ripiazzo prima "
                       "di %d s" % (codice, " = importo" if codice == CODICE_TAGLIA
                                    else "", attesa_s))

    # ------------------------------------------------------------ flusso
    def _aggiorna_flusso(self, now: float, ex: Any) -> None:
        """I prints (delta della ladder ``trd``) per lato, come
        ``scalper_bot._update_flow``: lato punta se al best back precedente o
        sotto, lato banca se al best lay precedente o sopra, dentro lo spread
        meta' e meta'."""
        if ex is None:
            return
        if self._first_seen is None:
            self._first_seen = now
        trd = getattr(ex, "traded_volume", None) or []
        if not self._prev_trd:
            for t in trd:
                p, s = t.get("price"), t.get("size")
                if p is not None and s:
                    self._prev_trd[float(p)] = float(s)
            return
        bb, bl = self._last_bb, self._last_bl
        fb = fl = 0.0
        for t in trd:
            p, s = t.get("price"), t.get("size")
            if p is None or s is None:
                continue
            p = float(p)
            d = float(s) - self._prev_trd.get(p, 0.0)
            if d <= _EPS:
                continue
            self._prev_trd[p] = float(s)
            if bb is not None and p <= bb + _EPS:
                fb += d
            elif bl is not None and p >= bl - _EPS:
                fl += d
            else:
                fb += d / 2.0
                fl += d / 2.0
        if fb > 0 or fl > 0:
            self._flow.append((now, fb, fl))
        orizzonte = now - self.flow_window_ms
        while self._flow and self._flow[0][0] < orizzonte:
            self._flow.pop(0)

    def _somme_flusso(self, now: float) -> Tuple[float, float]:
        orizzonte = now - self.flow_window_ms
        fb = sum(b for t, b, _l in self._flow if t >= orizzonte)
        fl = sum(l for t, _b, l in self._flow if t >= orizzonte)
        return fb, fl

    # ------------------------------------------------------------ stats
    def _pubblica(self, pos: Optional[Posizione], bb: Optional[float],
                  bl: Optional[float], forza: bool = False) -> None:
        if pos is None:
            pos = posizione_da_ordini(self._ordini)
        s = self.stats
        s["stato"] = self.stato
        s["rientri"] = self._rientri
        s["totale_puntato"] = round(pos.puntato, 2)
        s["quota_media"] = round(pos.quota_media, 4) if pos.quota_media else None
        s["se_vince"] = round(pos.se_vince, 2)
        s["se_perde"] = round(pos.se_perde, 2)
        s["banca"] = self._descrivi_banca()
        s["obiettivo_lordo"] = (round(self._t_lordo, 4) if self._t_lordo is not None
                                else None)
        s["riavvio"] = self.riavvio
        if self.stato in (LIVE, MASSIMO) or (forza and self.stato != BLOCCATA):
            # 05/10 (giro 2): gli ordini del conto letti dalla sessione entrano
            # SOLO qui (il riquadro), con la fonte e l'ora del dato
            fonte, pos_r = self._fonte_e_posizione(pos)
            self.chiusura = riquadro_chiusura(
                pos_r, quota_punta=bb, quota_banca=bl, tick=self.par.tick_chiusura,
                obiettivi_netti=self.par.obiettivi_live, commissione=self.par.commissione,
                banca=s["banca"], fonte=fonte)
            s["fonte"] = fonte
        else:
            self.chiusura = None
        s["chiusura"] = self.chiusura

    # ------------------------------------------------- ordini del conto
    def posizione_aperta(self) -> bool:
        """C'e' una posizione del ciclo da chiudere (letta dalla sessione per
        decidere se leggere gli ordini del conto)."""
        if self._esito is not None:
            return False
        try:
            return posizione_da_ordini(list(self._ordini)).aperta
        except Exception:  # noqa: BLE001 - lista che cambia nel thread di flumine
            return False

    def imposta_ordini_conto(self, righe: Optional[Sequence[Dict[str, Any]]], ora: str,
                             errore: Optional[str] = None) -> None:
        """La sessione consegna l'ultima lettura dello specchio (``righe`` None e
        ``ora`` vuota = nessuna lettura). Entra SOLO nel riquadro."""
        if righe is None and errore is None:
            self._conto = None
            return
        self._conto = {"righe": righe_a_mano(righe or [], self._mid, self._sid),
                       "ora": str(ora), "errore": errore}

    def _fonte_e_posizione(self, pos: Posizione) -> Tuple[str, Posizione]:
        c = self._conto
        if c is None:
            return FONTE_SOLO_BOT, pos
        if c.get("errore"):
            return ("%s (lettura degli ordini del conto fallita alle %s: %s)"
                    % (FONTE_SOLO_BOT, c.get("ora"), str(c["errore"])[:80]), pos)
        righe = list(c.get("righe") or [])
        return ("ordini del bot + ordini del conto letti alle %s (%d a mano su questa "
                "selezione)" % (c.get("ora"), len(righe)), posizione_con_righe(pos, righe))

    def process_closed_market(self, market: Any, market_book: Any) -> None:
        """Mercato regolato: l'esito del ciclo dal risultato di Betfair (stato
        WINNER/LOSER della selezione), e in prova il regolato simulato. SOLO il
        mercato della modalita' (flumine chiama anche per gli altri mercati
        della sessione, per esempio il Match Odds)."""
        mid = str(getattr(market_book, "market_id", None)
                  or getattr(market, "market_id", "") or "")
        if self._mid is None or mid != self._mid:
            return
        try:
            orders = market.blotter.strategy_orders(self)
        except Exception:  # noqa: BLE001
            orders = []
        regolato = 0.0
        for o in orders:
            oid = getattr(o, "id", None) or id(o)
            if oid in self._settled:
                continue
            self._settled.add(oid)
            try:
                regolato += float(getattr(getattr(o, "simulated", None), "profit", 0.0) or 0.0)
            except (TypeError, ValueError):
                pass
        if regolato:
            self.stats["pnl_settled"] = round(float(self.stats["pnl_settled"]) + regolato, 4)
        pos = posizione_da_ordini(self._ordini)
        vincente = None
        for r in getattr(market_book, "runners", None) or []:
            if self._sid is not None and int(r.selection_id) == int(self._sid):
                vincente = str(getattr(r, "status", "") or "")
        if pos.aperta and self._esito is None:
            esito = (pos.se_vince if vincente == "WINNER"
                     else pos.se_perde if vincente == "LOSER" else None)
            self._esito = {"stato_selezione": vincente, "lordo": esito}
            self.stats["esito_regolato"] = self._esito
            self._emit("media_esito", level="CRITICAL", market_id=self._mid,
                       stato_selezione=vincente,
                       lordo=(round(esito, 2) if esito is not None else None),
                       msg="mercato regolato: Under %s, esito lordo della posizione "
                           "del bot %s" % (vincente or "?",
                                           "%.2f" % esito if esito is not None else "?"))
        self.stato = FINE
        self.stats["stato"] = FINE
