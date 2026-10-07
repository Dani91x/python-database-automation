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
     sulla posizione VERA. La somma delle banche vive non supera MAI la
     posizione da coprire (al centesimo).
  3. CHIUSA IN PROFITTO: banca abbinata per intero e posizione pari -> ciclo
     registrato, si torna FERMO (nuovo ciclo con lo stake base).
  4. RIENTRO (solo pre-match): quota di punta salita di almeno ``tick di
     rientro`` sull'ULTIMO ingresso abbinato e rientri sotto il massimo ->
     dal 07/10 (ordine dell'utente: <<la banca deve aspettare che si abbini il
     rientro prima di fare qualsiasi cosa [...] MODIFICARE l'ordine banca e
     spostarlo a seconda dei rientri effettivamente abbinati>>):
     (a) PUNTA subito l'importo di rientro (par.4) con la banca viva INTATTA;
     (b) finche' la punta di rientro e' viva la banca NON si tocca (il resto
     non abbinato della punta si annulla come prima: alla prima parte
     abbinata, giro 3, o allo scadere del TTL);
     (c) a punta TERMINATA con un abbinato, la banca si SPOSTA una volta sulla
     posizione vera: L = banca esatta a ``quota del rientro - tick``; prima
     l'INTEGRAZIONE L - R (R = resto vivo della banca) alla quota nuova, poi
     ``replace_order`` della banca vecchia alla quota nuova (Betfair non
     aumenta l'importo di un ordine). Mai annullo + ripiazzo identico.
     Dettagli: ``_allinea_banche`` e la spec par.3 punto 4 (07/10).
  5. MASSIMO: dopo l'ultimo rientro consentito non punta piu'; la banca resta
     appoggiata (PERSIST); lo dice una volta (attivita' CRITICAL).
  6. LIVE (dal passaggio in gioco): NESSUN ordine, nessun annullo, nessun
     riprezzo. Pubblica il riquadro "chiusura" (par.6) a ogni book.
  7. FINE: posizione pari (in gioco) o mercato regolato.

ATTIVA ADESSO (07/10, ordine dell'utente, spec par.13): col clic sul pulsante la
modalita' PUNTA SUBITO lo stake base al miglior prezzo di punta (pre-match o in
gioco), senza filtri d'ingresso, e gestisce la posizione come progettato senza
filtri (anche dentro la finestra di stop e in gioco; restano tetti e
protezioni). Ciclo chiuso pre-match: rientra da solo (subito, o coi filtri se
``media_rientro_auto_filtri``); ciclo chiuso in gioco: ATTESA_CLIC. Il comando
lo consegna la sessione (``ricevi_comando`` -> registrazione dell'id nella
riga -> ``rilascia_comando``), si esegue al prossimo book, si consuma UNA volta.
Senza clic la modalita' e' quella di sempre, identica.

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
    dichiarano UNA volta. Un'INTEGRAZIONE della banca sotto 1,00 (07/10) si fa
    riducendo prima una banca viva (``cancelOrders`` con ``sizeReduction``)
    cosi' che l'integrazione salga a 1,00 al centesimo; se nessuna banca viva
    regge la riduzione (resterebbe sotto 1,00) l'integrazione si dichiara UNA
    volta e si sposta solo la parte che c'e'.

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
    # 07/10 (ATTIVA ADESSO, regola dell'utente punto 2): i rientri automatici
    # pre-match dopo una chiusura di un ciclo avviato col pulsante entrano
    # SUBITO (False, di serie) o solo coi filtri d'ingresso (True)
    "media_rientro_auto_filtri": False,
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
# 07/10 - <<ATTIVA ADESSO>> (ordine dell'utente del 07/10, spec par.13)
#: il COMANDO del pulsante nei params della riga: {"id": <testo unico del clic>,
#: "ts": <istante del clic, ISO o epoch ms>}. La sessione lo consuma UNA volta
#: (l'id consumato resta nelle stats e sopravvive al riavvio)
CHIAVE_COMANDO = "media_attiva_adesso"
#: la sessione armata DAL PULSANTE (o in attesa del clic): nessun ingresso da
#: sola finche' un clic non avvia il primo ciclo
CHIAVE_A_CLIC = "media_a_clic"
#: l'interruttore dei rientri automatici pre-match coi filtri (vedi sopra)
CHIAVE_RIENTRO_FILTRI = "media_rientro_auto_filtri"
#: un comando piu' vecchio di cosi' (dal clic alla consegna) non si esegue:
#: protezione contro un clic rimasto nei params di una riga riarmata ore dopo
ATTESA_MASSIMA_COMANDO_S = 120.0
#: da dove e' partito un ciclo (attivita' ``media_ingresso`` e stats)
ORIGINE_CLIC = "clic"
ORIGINE_RIENTRO_AUTO = "rientro_automatico"
ORIGINE_FILTRI = "filtri"

#: tutte le chiavi che la UI puo' scrivere (whitelist della sessione)
CHIAVI_UI: Tuple[str, ...] = ("media_mode", "media_mercato", "media_obiettivo") + tuple(
    k for k in OBBLIGATORI if k != "media_mercato") + (
    CHIAVE_RIENTRO_FILTRI, CHIAVE_A_CLIC, CHIAVE_COMANDO)

# stati del ciclo (spec par.3, macchina a stati)
FERMO = "FERMO"
INGRESSO = "INGRESSO"
IN_POSIZIONE = "IN_POSIZIONE"
RIENTRO = "RIENTRO"
MASSIMO = "MASSIMO"
LIVE = "LIVE"
FINE = "FINE"
BLOCCATA = "BLOCCATA"
#: 07/10 (ATTIVA ADESSO): la modalita' aspetta un clic (sessione armata dal
#: pulsante, ciclo chiuso IN GIOCO, prima punta del clic non abbinata)
ATTESA_CLIC = "ATTESA_CLIC"
#: 06/10 (giro 4, P13): in SOLDI VERI, dopo un riavvio, la modalita' aspetta di
#: ritrovare sul conto (e nel blotter di flumine) gli ordini della sessione
#: morta e ricostruisce il ciclo da li': NESSUN ordine finche' non ha finito
RIPRESA = "RIPRESA"
STATI: Tuple[str, ...] = (FERMO, INGRESSO, IN_POSIZIONE, RIENTRO, MASSIMO, LIVE,
                          FINE, BLOCCATA, RIPRESA, ATTESA_CLIC)
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
    # 07/10 (ATTIVA ADESSO): rientri automatici pre-match coi filtri (assente =
    # False: entrano subito al miglior prezzo)
    rientro_auto_filtri: bool = False


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
    # 07/10 (ATTIVA ADESSO): facoltativo (assente = False), ma se c'e' e' un
    # booleano vero e proprio (mai "si'" o 1 interpretati)
    filtri = p.get(CHIAVE_RIENTRO_FILTRI, False)
    if filtri is None:
        filtri = False
    if not isinstance(filtri, bool):
        errori.append("%s %r non valido (true o false)" % (CHIAVE_RIENTRO_FILTRI, filtri))
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
        rientro_auto_filtri=bool(filtri),
    ), None


def leggi_comando(params: Optional[Dict[str, Any]]) -> Optional[Tuple[str, Optional[float]]]:
    """07/10 (ATTIVA ADESSO): il comando del pulsante nei params della riga,
    ``(id, istante del clic in ms epoch o None)``; None se non c'e' o e'
    illeggibile (un comando senza id non si esegue mai)."""
    c = (params or {}).get(CHIAVE_COMANDO)
    if not isinstance(c, dict):
        return None
    cid = str(c.get("id") or "").strip()
    if not cid:
        return None
    ts = c.get("ts")
    ms: Optional[float] = None
    if isinstance(ts, (int, float)) and not isinstance(ts, bool):
        ms = float(ts)
    elif isinstance(ts, str) and ts.strip():
        try:
            d = _dt.datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=_dt.timezone.utc)
            ms = float(d.timestamp()) * 1000.0
        except ValueError:
            ms = None
    return cid, ms


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


def testo_ciclo_chiuso(lordo: float, netto: float, rientri: int) -> str:
    """Il testo dell'attivita' di un ciclo chiuso: profitto o PERDITA, mai
    <<in profitto>> su un lordo negativo (difetto del giro 2)."""
    return ("ciclo chiuso in %s: lordo %.2f, netto %.2f, rientri %d"
            % ("profitto" if lordo >= 0 else "PERDITA", lordo, netto, rientri))


def tick_sotto_la_media(media: Optional[float]) -> Optional[float]:
    """06/10 (giro 3): il tick della scala vera di Betfair STRETTAMENTE sotto la
    quota media (2,2074 -> 2,20; una media esattamente su un tick, 2,20 -> 2,18:
    chiudere sulla media stessa darebbe zero, non profitto)."""
    if media is None or media <= 1.0:
        return None
    p = float(get_nearest_price(float(media)))
    if p >= float(media) - 1e-9:
        p = price_ticks_away(p, -1)
    return float(p) if p and p > 1.0 else None


def quota_della_banca(ultimo_ingresso: Optional[float], pos: "Posizione",
                      tick: int) -> Optional[float]:
    """06/10 (giro 3), regola dell'utente <<e' sempre la quota media che comanda>>:
    la banca di chiusura va al PIU' BASSO fra <<ultimo ingresso - N tick>> e
    <<quota media arrotondata al tick inferiore>>, sulla posizione REALE
    abbinata: e' sempre in profitto. Con i rientri abbinati per intero la media
    sta sopra <<ultimo ingresso - N tick>> (la formula del rientro chiude in
    profitto proprio li') e la quota resta quella di prima."""
    c = tick_sotto(ultimo_ingresso, tick) if ultimo_ingresso is not None else None
    cm = tick_sotto_la_media(pos.quota_media)
    if cm is not None and (c is None or cm < c - 1e-9):
        return cm
    return c


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
    # 07/10: alla quota minima della scala (1,01) non c'e' una quota di chiusura
    # sotto: nessun obiettivo (prima: divisione per zero a ogni book)
    if quota_punta and c and c < float(quota_punta) - 1e-9:
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


# ---------------------------------------------------------------------------
# 06/10 (giro 4, P13): la RIPRESA in soldi veri dal conto
# ---------------------------------------------------------------------------
#: quanto si aspetta (ms di mercato) che flumine riadotti nel blotter gli ordini
#: VIVI trovati sul conto; oltre: BLOCCATA, avviso, nessun ordine
ATTESA_RIPRESA_MS = 60_000


def riga_dal_conto(o: Any) -> Dict[str, Any]:
    """Un ``CurrentOrder`` di betfairlightweight (``listCurrentOrders``) come
    riga semplice (le chiavi che la ripresa usa)."""
    ps = getattr(o, "price_size", None)
    placed = getattr(o, "placed_date", None)
    try:
        placed_ms = (float(placed.replace(tzinfo=placed.tzinfo or _dt.timezone.utc)
                           .timestamp()) * 1000.0 if placed is not None else None)
    except (AttributeError, TypeError, ValueError, OSError, OverflowError):
        placed_ms = None
    return {
        "bet_id": str(getattr(o, "bet_id", "") or ""),
        "market_id": str(getattr(o, "market_id", "") or ""),
        "selection_id": int(getattr(o, "selection_id", 0) or 0),
        "side": str(getattr(o, "side", "") or "").upper(),
        "price": float(getattr(ps, "price", 0.0) or 0.0) if ps is not None else 0.0,
        "size": float(getattr(ps, "size", 0.0) or 0.0) if ps is not None else 0.0,
        "size_matched": float(getattr(o, "size_matched", 0.0) or 0.0),
        "size_remaining": float(getattr(o, "size_remaining", 0.0) or 0.0),
        "average_price_matched": float(getattr(o, "average_price_matched", 0.0) or 0.0),
        "status": str(getattr(o, "status", "") or ""),
        "persistence": str(getattr(o, "persistence_type", "") or ""),
        "placed_ms": placed_ms,
        "customer_order_ref": str(getattr(o, "customer_order_ref", "") or ""),
    }


class OrdineDelConto:
    """Un ordine CHIUSO (``EXECUTION_COMPLETE``) della sessione morta, letto dal
    conto e non riadottato da flumine: entra nella posizione con le stesse
    letture di un ordine flumine (lato, abbinato, prezzo medio, stato), non si
    annulla e non cambia piu'. Gli ordini VIVI invece si governano solo come
    ordini flumine riadottati (nel blotter)."""

    def __init__(self, riga: Dict[str, Any]) -> None:
        self.riga = dict(riga)
        self.id = "conto-%s" % riga.get("bet_id")
        self.bet_id = str(riga.get("bet_id"))
        self.market_id = str(riga.get("market_id") or "")
        self.selection_id = int(riga.get("selection_id") or 0)
        self.handicap = 0.0
        self.trade = None
        pm = riga.get("placed_ms")
        self.date_time_created = (_dt.datetime.fromtimestamp(float(pm) / 1000.0,
                                                             tz=_dt.timezone.utc)
                                  if pm is not None else None)
        self.side = str(riga.get("side") or "").upper()
        self.status = OrderStatus.EXECUTION_COMPLETE
        self.size_matched = float(riga.get("size_matched") or 0.0)
        self.average_price_matched = float(riga.get("average_price_matched") or 0.0)
        self.size_remaining = 0.0
        self.order_type = LimitOrder(price=float(riga.get("price") or 1.01) or 1.01,
                                     size=float(riga.get("size") or 0.0) or 0.01,
                                     persistence_type=str(riga.get("persistence") or "LAPSE"))
        self.placed_ms = riga.get("placed_ms")


def _ms_creato(o: Any) -> float:
    """L'istante di nascita di un ordine (flumine o del conto), per ordinarli."""
    if isinstance(o, OrdineDelConto):
        return float(o.placed_ms or 0.0)
    d = getattr(o, "date_time_created", None)
    try:
        if d is not None:
            if getattr(d, "tzinfo", None) is None:
                d = d.replace(tzinfo=_dt.timezone.utc)
            return float(d.timestamp()) * 1000.0
    except (AttributeError, TypeError, ValueError, OSError, OverflowError):
        pass
    return 0.0


def cicli_degli_ordini(ordini: Sequence[Any]) -> List[List[Any]]:
    """I cicli dagli ORDINI (in ordine di nascita): un ciclo nuovo comincia con
    una PUNTA piazzata quando il ciclo prima e' morto (nessun ordine vivo), ha
    una banca abbinata ed e' pari entro l'arrotondamento al centesimo della
    banca (la stessa regola di ``certificazione.cicli_media``)."""
    cicli: List[List[Any]] = []
    corrente: List[Any] = []
    for o in sorted(ordini, key=_ms_creato):
        if _lato(o) == "BACK" and corrente and _ciclo_finito(corrente):
            cicli.append(corrente)
            corrente = []
        corrente.append(o)
    if corrente:
        cicli.append(corrente)
    return cicli


def _ciclo_finito(ordini: Sequence[Any]) -> bool:
    if any(vivo_o_in_volo(o) for o in ordini):
        return False
    banche = [o for o in ordini if _lato(o) == "LAY" and abbinato(o)[0] > 0]
    if not banche:
        return False
    pos = posizione_da_ordini(ordini)
    c = max(float(o.order_type.price) for o in banche)
    return pos.puntato > _EPS and abs(pos.se_vince - pos.se_perde) <= 0.02 + 0.005 * c


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


@dataclass
class StatoClic:
    """07/10 (ATTIVA ADESSO): lo stato del pulsante di UNA strategia.

    * ``a_clic``: sessione armata dal pulsante o avviata da un clic;
    * ``consumato``: l'id dell'ultimo comando consumato (anche dalla sessione di
      prima: un riavvio non riesegue lo stesso clic);
    * ``pronto``: comando validato, in attesa che la sessione l'abbia registrato
      nella riga; ``comando``: da eseguire al prossimo book;
    * ``origine``: da dove e' partito il ciclo in corso;
    * ``in_gioco``, ``in_gioco_detto``, ``ultimo_aperto``: l'ultimo book visto."""

    a_clic: bool = False
    consumato: Optional[str] = None
    pronto: Optional[Dict[str, Any]] = None
    comando: Optional[Dict[str, Any]] = None
    origine: Optional[str] = None
    in_gioco: bool = False
    in_gioco_detto: bool = False
    ultimo_aperto: Optional[bool] = None


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
        # 07/10 (ATTIVA ADESSO): la sessione "a clic" (armata dal pulsante o
        # avviata da un clic): nessun primo ingresso da sola; dopo una chiusura
        # pre-match rientra da sola, dopo una chiusura in gioco aspetta il clic.
        # Senza clic (False) la modalita' e' quella di sempre, identica. Tutto lo
        # stato del pulsante sta in UN oggetto (``StatoClic``): la parita'
        # paper/live del banco (S6) confronta i parametri, non lo stato.
        self._clic = StatoClic(
            a_clic=cfg.get(CHIAVE_A_CLIC) is True,
            consumato=(str(cfg.get("comando_consumato"))
                       if cfg.get("comando_consumato") else None))
        self.stato: str = BLOCCATA if self.riavvio else (ATTESA_CLIC if self._clic.a_clic else FERMO)
        # mercato e selezione (bloccati al primo book del tipo scelto)
        self._mid: Optional[str] = None
        self._sid: Optional[int] = None
        self._ko_ms: Optional[float] = None
        # il ciclo
        self._ordini: List[Any] = []          # TUTTI gli ordini del ciclo corrente
        self._punta: Optional[Any] = None     # punta (ingresso o rientro) in corso
        self._punta_ms: float = 0.0
        self._punta_rientro: bool = False
        # 07/10 (banca spostata, ordine dell'utente): le banche di chiusura sono
        # gli ordini LAY di ``self._ordini`` (la banca, le sue integrazioni e i
        # sostituti dei replace). ``_spostamenti``: i replace chiesti e non ancora
        # conclusi (id dell'ordine vecchio -> quota di partenza e d'arrivo);
        # ``_ritoccate``: gli id delle banche che il bot stesso ha annullato,
        # ridotto o spostato (non sono <<cadute>>); ``_scoperto``: l'integrazione
        # sotto il minimo dichiarata e non piazzata (quota, voluto, mancante)
        self._spostamenti: Dict[int, Dict[str, Any]] = {}
        self._ritoccate: set = set()
        self._scoperto: Optional[Tuple[float, float, float]] = None
        self._fermo_sposta_ms: float = 0.0
        self._sposta_falliti: int = 0
        self._ultimo_ingresso: Optional[float] = None
        self._rientri: int = 0
        self._t_lordo: Optional[float] = None
        self._rientri_bloccati: Optional[str] = None
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
        # 06/10 (giro 4, P13): la ripresa dal conto in soldi veri (None = nessuna)
        # e gli ordini CHIUSI letti dal conto (non nel blotter di questo
        # processo): restano per tutta la sessione, l'esposizione li conta
        self._ripresa: Optional[Dict[str, Any]] = None
        self._ordini_conto: List[Any] = []
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
            # 07/10 (ATTIVA ADESSO): l'ultimo comando del pulsante (id, esito,
            # motivo, prezzo, importo), la sessione "a clic", l'origine del
            # ciclo in corso, se la partita e' in gioco
            "comando": (dict(cfg["comando_precedente"])
                        if isinstance(cfg.get("comando_precedente"), dict) else None),
            "a_clic": self._clic.a_clic, "origine_ciclo": None, "in_gioco": False,
            "rientro_auto_filtri": par.rientro_auto_filtri,
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

    # ------------------------------------------------ le banche (07/10)
    def _banche(self) -> List[Any]:
        """Le banche di chiusura del ciclo (in ordine di nascita): la banca, le
        sue integrazioni e i sostituti dei replace."""
        return [o for o in self._ordini if _lato(o) == "LAY"]

    def _banche_vive(self) -> List[Any]:
        return [o for o in self._banche() if vivo_o_in_volo(o)]

    @property
    def _banca(self) -> Optional[Any]:
        """La banca <<di riferimento>> (letture e test di prima del 07/10): la
        piu' recente viva, altrimenti la piu' recente del ciclo."""
        vive = self._banche_vive()
        if vive:
            return vive[-1]
        banche = self._banche()
        return banche[-1] if banche else None

    def _banche_ferme(self) -> bool:
        """Nessuna operazione sulla banca in volo (ogni banca viva e' sul book,
        nessun replace in attesa del sostituto) e tutte alla STESSA quota: lo
        spostamento e' concluso. Solo cosi' parte un rientro (mai due quote
        diverse vive mentre una punta di rientro e' sul mercato)."""
        if self._spostamenti:
            return False
        vive = self._banche_vive()
        if any(not eseguibile(b) for b in vive):
            return False
        return len({round(float(b.order_type.price), 2) for b in vive}) <= 1

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
        # 07/10 (banca spostata): i sostituti dei replace entrano nel ciclo, un
        # replace fallito si dice (prima di ogni decisione, in ogni stato)
        self._segui_spostamenti(market, now)
        # 07/10 (ATTIVA ADESSO): cio' che il clic deve sapere del mercato, e il
        # comando consegnato dalla sessione, deciso su QUESTO book
        self._clic.in_gioco = inplay
        self._clic.ultimo_aperto = aperto
        self.stats["in_gioco"] = inplay
        if self._clic.comando is not None:
            self._esegui_comando(market, market_book, now, inplay, aperto, bb)
        if self.stato == BLOCCATA:
            self._una_volta("bloccata", "media_riavvio_non_ricostruibile", level="CRITICAL",
                            market_id=self._mid, motivo=self.riavvio,
                            msg="riavvio a posizione aperta: la posizione NON e' "
                                "ricostruibile dagli ordini veri da questa sessione. "
                                "Nessun ordine: verificala sul conto e chiudila a mano")
            self._pubblica(None, bb, bl)
            return
        if self.stato == RIPRESA:
            # 06/10 (P13): nessun ordine finche' la posizione non e' ricostruita
            # dagli ordini veri (si decide dal book DOPO, mai in questo)
            self._ko_epoch_ms(market_book)
            self._forse_riprendi(market, now)
            self._pubblica(None, bb, bl)
            return
        if inplay:
            if self._clic.a_clic:
                # 07/10 (ATTIVA ADESSO, punto 4): avviata col pulsante, in gioco
                # gestisce la posizione come pre-match
                self._in_gioco_a_clic(market, market_book, now, aperto, bb, bl, sb, sl)
                return
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

    def _puo_gestire(self, now: float) -> Optional[str]:
        """07/10 (ATTIVA ADESSO, punto 1 della regola dell'utente): la gestione
        di un ciclo avviato col pulsante (rientri) e il rientro automatico
        pre-match senza filtri NON passano dai filtri d'ingresso (quota,
        liquidita', flusso, spread, finestra di stop prima del fischio, fischio
        ignoto): restano solo le protezioni (stop/freno della sessione, attesa
        dopo un rifiuto di Betfair). Mercato aperto e prezzi vivi li decide il
        book (nessun ordine a mercato sospeso, nessun book = nessun ordine)."""
        if self.force_flat:
            return _APRIRE_FRENO
        if now < self._fermo_punte_ms:
            return _APRIRE_RIFIUTO
        return None

    def _filtro_aperture(self, now: float) -> Optional[str]:
        """Il cancello delle punte di RIENTRO: quello di sempre (``_puo_aprire``)
        o, per la sessione avviata col pulsante, le sole protezioni."""
        return self._puo_gestire(now) if self._clic.a_clic else self._puo_aprire(now)

    def _pre_match(self, market: Any, mb: Any, now: float, bb: Optional[float],
                   bl: Optional[float], sb: Optional[float], sl: Optional[float]) -> None:
        self._ko_epoch_ms(mb)
        if self.force_flat:
            # 06/10 (P1): allo stop nessuna punta resta sul book
            self._ritira_la_punta_allo_stop(market)
        # 1. la punta in corso (ingresso o rientro)
        if self._punta is not None:
            p = self._punta
            if vivo_o_in_volo(p):
                if self._punta_rientro:
                    # 07/10 (ordine dell'utente): finche' la punta di RIENTRO e'
                    # viva la banca NON si tocca; si sposta una volta sola quando
                    # la punta e' terminata (``_assicura_banca`` dopo
                    # ``_punta_morta``)
                    self._rientro_in_corso(market, p)
                elif abbinato(p)[0] > 0:
                    # "appena la punta e' abbinata (anche in parte)"
                    self._assicura_banca(market, now, prezzo_ingresso=float(
                        p.order_type.price))
                if (now - self._punta_ms >= self.par.ttl_punta_ms and eseguibile(p)):
                    self._annulla(market, p, "punta non abbinata entro %d ms"
                                  % self.par.ttl_punta_ms)
                return
            self._punta_morta(p)
        # 2. (fino al 06/10: la banca in annullo per un rientro. Dal 07/10 la
        # banca resta viva durante il rientro e si sposta a punta terminata)
        # 3. ciclo chiuso?
        if self._ciclo_chiuso(now):
            return
        pos = posizione_da_ordini(self._ordini)
        if self.stato == FERMO:
            if self._clic.a_clic:
                # 07/10: ciclo chiuso PRE-MATCH di una sessione avviata col
                # pulsante: rientra da solo (subito, o coi filtri se l'utente li
                # ha accesi). In gioco FERMO non esiste: e' ATTESA_CLIC.
                self._rientro_automatico(market, now, bb, bl, sb, sl)
                return
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
                        bl: Optional[float], sb: Optional[float], sl: Optional[float],
                        origine: str = ORIGINE_FILTRI) -> None:
        motivo = self._perche_non_entra(now, bb, bl, sb, sl)
        if motivo is not None:
            self._conta_non_ingresso(motivo)
            return
        if self._punta_d_ingresso(market, now, bb, origine) is None:
            self._conta_non_ingresso("punta_non_piazzata")

    def _punta_d_ingresso(self, market: Any, now: float, bb: Optional[float],
                          origine: str) -> Optional[Any]:
        """La prima punta di un ciclo: lo stake base alla miglior quota di punta
        del book (LAPSE). ``origine``: filtri (la modalita' di sempre), clic
        (<<Attiva adesso>>), rientro automatico pre-match."""
        if bb is None:
            return None
        prezzo = float(get_nearest_price(bb))
        o = self._piazza(market, "BACK", prezzo, self.par.stake, apertura=True,
                         persistenza="LAPSE")
        if o is None:
            return None
        self._punta, self._punta_ms, self._punta_rientro = o, now, False
        self.stato = INGRESSO
        if origine != ORIGINE_FILTRI or self._clic.a_clic:
            self._clic.origine = origine
            self.stats["origine_ciclo"] = origine
        extra: Dict[str, Any] = {}
        if origine != ORIGINE_FILTRI:
            # 07/10: da dove parte il ciclo (il payload della modalita' di sempre
            # resta identico)
            extra["origine"] = origine
            extra["in_gioco"] = self._clic.in_gioco
        self._emit("media_ingresso", market_id=self._mid, selection_id=self._sid,
                   prezzo=prezzo, importo=self.par.stake, **extra,
                   msg="punta d'ingresso %.2f EUR @%.2f%s" % (
                       self.par.stake, prezzo,
                       {ORIGINE_CLIC: " (Attiva adesso)",
                        ORIGINE_RIENTRO_AUTO: " (rientro automatico dopo la chiusura)"}
                       .get(origine, "")))
        return o

    def _rientro_automatico(self, market: Any, now: float, bb: Optional[float],
                            bl: Optional[float], sb: Optional[float],
                            sl: Optional[float]) -> None:
        """07/10 (regola dell'utente, punto 2): ciclo avviato col pulsante e
        chiuso PRE-MATCH -> nuovo ciclo da solo. Di serie SUBITO al miglior
        prezzo (anche dentro la finestra di stop prima del fischio); con
        ``media_rientro_auto_filtri`` acceso solo quando i filtri d'ingresso di
        sempre lo permettono. IN GIOCO mai (punto 3): si aspetta il clic (e' qui,
        in un punto solo, sia per il ciclo chiuso in gioco sia per il ciclo chiuso
        prima del fischio che arriva al fischio senza essere ripartito)."""
        if self._clic.in_gioco:
            self.stato = ATTESA_CLIC
            return
        if self.par.rientro_auto_filtri:
            self._forse_ingresso(market, now, bb, bl, sb, sl, origine=ORIGINE_RIENTRO_AUTO)
            return
        aprire = self._puo_gestire(now)
        if aprire:
            self._conta_non_ingresso(_MOTIVO_DA_APRIRE.get(aprire, "freno"))
            return
        if bb is None:
            self._conta_non_ingresso("prezzi_mancanti")
            return
        if self._punta_d_ingresso(market, now, bb, ORIGINE_RIENTRO_AUTO) is None:
            self._conta_non_ingresso("punta_non_piazzata")

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
            if pos.aperta:
                self.stato = IN_POSIZIONE
            elif self._clic.a_clic and (self._clic.origine == ORIGINE_CLIC or self._clic.in_gioco):
                # 07/10: la prima punta del CLIC non abbinata (o una punta morta
                # in gioco senza posizione): un clic = una sola prima punta, si
                # aspetta il prossimo clic
                self.stato = ATTESA_CLIC
            else:
                self.stato = FERMO
            self._emit("media_punta_non_abbinata", market_id=self._mid,
                       rientro=self._punta_rientro, prezzo=prezzo,
                       msg="punta non abbinata e morta: si rivaluta dal book corrente")
        if fisso:
            self.stato = stato_prima

    def _forse_rientro(self, market: Any, now: float, bb: Optional[float],
                       pos: Posizione) -> None:
        if self._rientri_bloccati or self._ultimo_ingresso is None or bb is None:
            return
        if self._filtro_aperture(now):
            return
        su = ticks_between(self._ultimo_ingresso, bb)
        if su is None or su < self.par.tick_rientro:
            return
        if self._rientri >= self.par.max_rientri:
            return
        # 07/10 (ordine dell'utente): la punta di rientro parte con la banca viva
        # INTATTA (nessun annullo, nessun ripiazzo). Si aspetta solo che uno
        # spostamento della banca gia' chiesto sia concluso: mai due quote
        # diverse vive mentre la punta di rientro e' sul mercato
        if not self._banche_ferme():
            return
        self._punta_di_rientro(market, now, bb)

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
        """Il ricalcolo sulla posizione VERA (la banca abbinata in parte conta) e
        la punta di rientro, con la banca viva intatta. La condizione del
        rientro si rilegge sul book corrente."""
        if bb is None or self._ultimo_ingresso is None or self._filtro_aperture(now):
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
        self.stato = RIENTRO
        self._emit("media_rientro", market_id=self._mid, selection_id=self._sid,
                   rientro=self._rientri + 1, prezzo=q, importo=xr, importo_esatto=xe,
                   chiusura=c, totale_puntato=round(pos.puntato, 2),
                   se_vince=round(pos.se_vince, 4), se_perde=round(pos.se_perde, 4),
                   obiettivo_lordo=self._t_lordo,
                   msg="rientro %d: punta %.2f EUR @%.2f (esatto %.2f) per chiudere a %.2f"
                       % (self._rientri + 1, xr, q, xe, c))

    def _assicura_banca(self, market: Any, now: float,
                        prezzo_ingresso: Optional[float]) -> None:
        """La banca di chiusura, PERSIST, a ``ingresso - tick`` (o sotto la
        media), per l'importo che pareggia la posizione VERA (al centesimo).
        Dal 07/10 la banca si MODIFICA, mai annullo + ripiazzo: vedi
        ``_allinea_banche``."""
        if prezzo_ingresso is None:
            return
        pos = posizione_da_ordini(self._ordini)
        # 06/10 (giro 3): la quota la comanda anche la media della posizione VERA
        c = quota_della_banca(prezzo_ingresso, pos, self.par.tick_chiusura)
        if c is None:
            return
        # 06/10 (giro 3): la banca copre l'INTERA posizione: ogni resto non
        # abbinato delle punte (ingresso o rientro) si annulla
        if pos.puntato > _EPS:
            self._annulla_resti_delle_punte(market)
        voluto = al_centesimo(banca_esatta(pos, c))
        self._allinea_banche(market, now, c, voluto, pos, prezzo_ingresso)

    def _allinea_banche(self, market: Any, now: float, c: float, voluto: float,
                        pos: Posizione, prezzo_ingresso: float) -> None:
        """07/10 - LA BANCA SI SPOSTA, NON SI RIPIAZZA (ordine dell'utente:
        <<non voglio rischiare doppi ordini di banca [...] MODIFICARE l'ordine
        banca e spostarlo a seconda dei rientri effettivamente abbinati>>).

        Porta le banche vive alla quota ``c`` per un resto TOTALE ``voluto``
        (L), un passo per book, senza che in nessun istante la somma dei resti
        vivi superi L (invariante: mai copertura oltre la posizione):

        * un'operazione in volo (banca non ancora sul book, annullo o replace in
          viaggio, sostituto non ancora arrivato) -> si aspetta;
        * R = somma dei resti vivi; D = L - R al centesimo (entro 0,01 = pari,
          la tolleranza di sempre);
        * D < 0 (caso anomalo: la posizione ne vuole meno) -> RIDUZIONE
          (``cancel_order`` con ``size_reduction``; per intero solo una banca
          piu' piccola della riduzione) e si aspetta;
        * D >= 1,00 -> INTEGRAZIONE di D alla quota c (PERSIST) e, nello STESSO
          book, il replace delle banche vive che stanno a un'altra quota
          (Betfair non aumenta l'importo di un ordine: ``replaceOrders`` cambia
          solo il prezzo e porta il resto annullato);
        * 0 < D < 1,00 (sotto il minimo .it di una banca) -> si RIDUCE una banca
          viva di 1,00 - D, cosi' al book dopo l'integrazione vale 1,00 al
          centesimo; se nessuna banca regge la riduzione (resterebbe sotto 1,00)
          la parte mancante si dichiara UNA volta e si sposta solo cio' che c'e';
        * D pari -> solo il replace delle banche a un'altra quota (se c'e').
        Senza banche vive e' il piazzamento di sempre (stesso evento
        ``media_banca``, stesso testo)."""
        vive = self._banche_vive()
        if any(not eseguibile(b) for b in vive) or self._spostamenti:
            # un'operazione in volo: si decide quando e' arrivata
            return
        if not vive:
            self._scoperto = None
            self._banca_nuova(market, now, c, voluto, pos, prezzo_ingresso)
            return
        resto = round(sum(float(getattr(b, "size_remaining", 0.0) or 0.0) for b in vive), 2)
        d = round(voluto - resto, 2)
        if d < -0.01 - 1e-9:
            self._riduci(market, vive, -d, "la posizione vera ne vuole %.2f @%.2f, vive %.2f"
                         % (voluto, c, resto))
            return
        if d > 0.01 + 1e-9:
            if importo_piazzabile("lay", d).via == VIA_DIRETTA:
                if now < self._fermo_banca_ms:
                    return
                o = self._piazza(market, "LAY", c, d, apertura=False, persistenza="PERSIST")
                if o is None:
                    return
                self._scoperto = None
                dalla_media = self._dalla_media(c, pos, prezzo_ingresso)
                self._emit("media_banca", market_id=self._mid, selection_id=self._sid,
                           prezzo=c, importo=d, integrazione=True, totale=voluto,
                           resto_vivo=resto, totale_puntato=round(pos.puntato, 2),
                           se_vince=round(pos.se_vince, 4), se_perde=round(pos.se_perde, 4),
                           quota_media=(round(pos.quota_media, 4) if pos.quota_media else None),
                           dalla_media=dalla_media,
                           msg="banca di chiusura: integrazione %.2f EUR @%.2f (resto vivo "
                               "%.2f, totale %.2f, PERSIST%s)"
                               % (d, c, resto, voluto,
                                  ", sotto la quota media %.4f" % pos.quota_media
                                  if dalla_media else ""))
            else:
                k = round(1.0 - d, 2)
                regge = [b for b in vive
                         if float(getattr(b, "size_remaining", 0.0) or 0.0) - k >= 1.0 - 1e-9]
                if regge:
                    b = max(regge, key=lambda x: float(getattr(x, "size_remaining", 0.0) or 0.0))
                    self._riduci(market, [b], k, "integrazione di %.2f sotto il minimo .it: "
                                                 "la banca si riduce di %.2f e l'integrazione "
                                                 "sale a 1,00" % (d, k))
                    return
                if self._scoperto is None or abs(self._scoperto[2] - d) > 0.005:
                    self._scoperto = (c, voluto, d)
                    self._emit("media_residuo", level="CRITICAL", market_id=self._mid,
                               selection_id=self._sid, importo=d, quota=c,
                               msg="integrazione della banca di %.2f EUR @%.2f non piazzabile "
                                   "(sotto 1,00) e nessuna banca viva riducibile: resta "
                                   "scoperta e DICHIARATA, la chiudi tu" % (d, c))
        self._sposta(market, now, vive, c)

    def _banca_nuova(self, market: Any, now: float, c: float, voluto: float,
                     pos: Posizione, prezzo_ingresso: float) -> None:
        """Nessuna banca viva: la banca di chiusura di sempre (stesso evento e
        stesso testo di prima del 07/10)."""
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
        dalla_media = self._dalla_media(c, pos, prezzo_ingresso)
        self._emit("media_banca", market_id=self._mid, selection_id=self._sid,
                   prezzo=c, importo=voluto, totale_puntato=round(pos.puntato, 2),
                   se_vince=round(pos.se_vince, 4), se_perde=round(pos.se_perde, 4),
                   quota_media=(round(pos.quota_media, 4) if pos.quota_media else None),
                   dalla_media=dalla_media,
                   msg="banca di chiusura %.2f EUR @%.2f (PERSIST%s)"
                       % (voluto, c, ", sotto la quota media %.4f" % pos.quota_media
                          if dalla_media else ""))

    def _dalla_media(self, c: float, pos: Posizione, prezzo_ingresso: float) -> bool:
        return (pos.quota_media is not None
                and c < (tick_sotto(prezzo_ingresso, self.par.tick_chiusura) or c) - 1e-9)

    def _riduci(self, market: Any, vive: Sequence[Any], quanto: float, motivo: str) -> None:
        """Riduce di ``quanto`` i resti delle banche vive (la piu' grande per
        prima): ``cancel_order`` con ``size_reduction`` (Betfair permette di
        RIDURRE un ordine); per intero solo una banca piu' piccola di cio' che
        resta da togliere."""
        resta = round(float(quanto), 2)
        for b in sorted(vive, key=lambda x: -float(getattr(x, "size_remaining", 0.0) or 0.0)):
            if resta < 0.01:
                break
            r = round(float(getattr(b, "size_remaining", 0.0) or 0.0), 2)
            self._ritoccate.add(id(b))
            if resta >= r - 0.005:
                self._annulla(market, b, "banca ridotta per intero: %s" % motivo)
                resta = round(resta - r, 2)
                continue
            try:
                market.cancel_order(b, size_reduction=resta)
            except Exception:  # noqa: BLE001 - riduzione non accettata da flumine
                logger.debug("[media] riduzione KO", exc_info=True)
                return
            self._emit("media_banca_ridotta", market_id=self._mid, selection_id=self._sid,
                       prezzo=float(b.order_type.price), resto=r, riduzione=resta,
                       motivo=motivo,
                       msg="banca %.2f @%.2f ridotta di %.2f (%s)"
                           % (r, float(b.order_type.price), resta, motivo))
            resta = 0.0

    def _sposta(self, market: Any, now: float, vive: Sequence[Any], c: float) -> None:
        """``replace_order`` di ogni banca viva che sta a una quota diversa da
        ``c``: Betfair annulla il resto e lo ripiazza a ``c`` in UNA operazione
        (il resto vecchio resta sul mercato fino allo spostamento). Nessun
        ``market_version``: la banca e' PERSIST e deve restare anche dopo un gol."""
        if now < self._fermo_sposta_ms:
            return
        from flumine.exceptions import OrderUpdateError

        for b in vive:
            da = float(b.order_type.price)
            if abs(da - c) < 1e-9 or not eseguibile(b) or getattr(b, "bet_id", None) is None:
                continue
            resto = float(getattr(b, "size_remaining", 0.0) or 0.0)
            try:
                ok = market.replace_order(b, float(c))
            except OrderUpdateError:
                logger.debug("[media] replace non accettato da flumine", exc_info=True)
                continue
            if ok is False:
                self._spostamento_fallito(b, now, "replace rifiutato dai controlli di flumine")
                continue
            # un replace manda a Betfair un ordine NUOVO (il sostituto): conta fra
            # gli ordini della modalita' (le azioni del referto)
            self.stats["ordini"] = int(self.stats["ordini"]) + 1
            self._ritoccate.add(id(b))
            self._spostamenti[id(b)] = {"ordine": b, "da": da, "a": float(c), "ms": now,
                                        "resto": resto}
            self._emit("media_banca_sposta", market_id=self._mid, selection_id=self._sid,
                       da=da, a=float(c), resto=round(resto, 2),
                       msg="banca %.2f spostata da %.2f a %.2f (replace: stesso resto, "
                           "quota nuova)" % (resto, da, c))

    def _spostamento_fallito(self, b: Any, now: float, motivo: str) -> None:
        """Un replace non riuscito nella parte di ANNULLO (la banca vecchia e'
        ancora viva alla sua quota): si riprova dopo 1, 2, 4, 8, 16 poi 30 s di
        mercato (lo stesso freno dei rifiuti)."""
        self._sposta_falliti += 1
        attesa_s = min(30, 2 ** (self._sposta_falliti - 1))
        self._fermo_sposta_ms = now + attesa_s * 1000.0
        self._emit("media_banca_sposta_fallita", level="WARN", market_id=self._mid,
                   prezzo=float(b.order_type.price), motivo=motivo, riprovo_fra_s=attesa_s,
                   msg="spostamento della banca NON riuscito (%s): la banca resta a %.2f, "
                       "si riprova fra %d s" % (motivo, float(b.order_type.price), attesa_s))

    def _segui_spostamenti(self, market: Any, now: float) -> None:
        """07/10: a ogni book, prima di ogni decisione. Il SOSTITUTO di un
        replace (``Trade.create_order_replacement``: stesso Trade, nel blotter
        solo se Betfair l'ha piazzato) entra negli ordini del ciclo. Un replace
        concluso SENZA sostituto con la banca vecchia annullata = fallito nella
        parte di PIAZZAMENTO (Betfair: <<the cancellations will not be rolled
        back>>): CRITICAL una volta, e l'allineamento ripiazza SUBITO cio' che
        manca alla quota nuova. La banca vecchia di nuovo sul book alla sua
        quota = fallito nella parte di ANNULLO: si riprova col freno."""
        if not self._spostamenti:
            return
        blotter = getattr(market, "blotter", None)
        for k, s in list(self._spostamenti.items()):
            o = s["ordine"]
            tr = getattr(o, "trade", None)
            nuovi = []
            for x in list(getattr(tr, "orders", None) or []):
                if x is o or any(x is y for y in self._ordini):
                    continue
                try:
                    nel_blotter = blotter is not None and getattr(x, "id", None) in blotter
                except Exception:  # noqa: BLE001 - blotter illeggibile: al book dopo
                    nel_blotter = False
                if nel_blotter and _lato(x) == "LAY":
                    nuovi.append(x)
            if nuovi:
                for x in nuovi:
                    self._ordini.append(x)
                    self._emit("media_banca_spostata", market_id=self._mid,
                               selection_id=self._sid, da=s["da"], a=float(x.order_type.price),
                               importo=float(x.order_type.size),
                               msg="banca spostata: %.2f @%.2f (era a %.2f)"
                                   % (float(x.order_type.size), float(x.order_type.price),
                                      s["da"]))
                self._sposta_falliti = 0
                del self._spostamenti[k]
                continue
            if vivo_o_in_volo(o):
                if eseguibile(o) and abs(float(o.order_type.price) - s["da"]) < 1e-9:
                    # di nuovo sul book alla quota vecchia: l'annullo non e' riuscito
                    del self._spostamenti[k]
                    self._spostamento_fallito(o, now, "annullo non riuscito")
                continue
            del self._spostamenti[k]
            m, _p = abbinato(o)
            if m + 0.005 >= float(o.order_type.size):
                # abbinata per intero prima dello spostamento: si ricalcola sulla
                # posizione vera (nessun sostituto serve)
                continue
            self._una_volta("sposta_ko_%s" % id(o), "media_banca_spostamento_fallito",
                            level="CRITICAL", market_id=self._mid, selection_id=self._sid,
                            da=s["da"], a=s["a"], resto=round(s["resto"], 2),
                            msg="spostamento della banca FALLITO nel piazzamento: la banca "
                                "vecchia (%.2f @%.2f) e' annullata e il sostituto a %.2f non "
                                "c'e'. Si ripiazza subito cio' che manca alla posizione"
                                % (s["resto"], s["da"], s["a"]))

    def _rientro_in_corso(self, market: Any, p: Any) -> None:
        """07/10: la punta di RIENTRO e' viva e la banca NON si tocca.

        * la banca si e' abbinata per intero mentre la punta era viva (ciclo
          gia' chiuso dalla banca: nessuna banca viva, la posizione SENZA la
          punta di rientro e' pari) -> si annulla SUBITO il resto della punta;
          cio' che la punta ha gia' abbinato e' una posizione nuova, che la
          modalita' gestisce come sempre sulla posizione vera (banca a quota
          abbinata - tick) quando la punta e' terminata;
        * la punta si e' abbinata in parte -> il resto si annulla (regola del
          giro 3, <<resti non abbinati annullati>>, identica a prima); la banca
          si sposta quando la punta e' terminata."""
        if not eseguibile(p):
            return
        banche = self._banche()
        if (banche and not any(vivo_o_in_volo(b) for b in banche)
                and any(abbinato(b)[0] > 0 for b in banche)):
            pos = posizione_da_ordini([o for o in self._ordini if o is not p])
            if pos.puntato > _EPS and abs(pos.se_vince - pos.se_perde) <= self._toll_pari():
                self._annulla(market, p, "la banca si e' abbinata per intero (ciclo chiuso): "
                                         "il resto della punta di rientro si annulla")
                return
        if abbinato(p)[0] > 0:
            self._annulla(market, p, "rientro abbinato in parte: il resto si annulla, la "
                                     "banca si sposta a punta terminata")

    def _annulla_resti_delle_punte(self, market: Any) -> None:
        """06/10 (giro 3): ogni resto NON abbinato di una punta (ingresso o
        rientro) ancora sul book si annulla quando si appoggia la banca. Si
        annulla solo cio' che e' sul book (``eseguibile``): una punta in volo si
        annulla al book dopo; quella gia' in annullo non si ritocca."""
        for o in list(self._ordini):
            if _lato(o) != "BACK" or not eseguibile(o):
                continue
            if float(getattr(o, "size_remaining", 0.0) or 0.0) <= 0.0:
                continue
            self._annulla(market, o, "banca appoggiata: il resto non abbinato della punta "
                                     "si annulla (la banca copre l'intera posizione)")

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
                   # 05/10 (giro 2): il testo dice se e' profitto o PERDITA (dal 06/10 la
                   # banca sta sotto la quota media e la perdita non dovrebbe piu'
                   # capitare: se capita, si dice)
                   msg=testo_ciclo_chiuso(lordo, netto_da_lordo(lordo, self.par.commissione),
                                          self._rientri))
        inplay = self.stato == LIVE
        self._nuovo_ciclo()
        if self._clic.a_clic:
            # 07/10 (regola dell'utente, punti 2-3): avviata col pulsante. Chiuso
            # PRE-MATCH -> rientra da solo (FERMO = rientro automatico); chiuso
            # IN GIOCO -> aspetta il clic, nessun ordine fino al clic (lo decide
            # ``_rientro_automatico``, al book dopo: in gioco diventa ATTESA_CLIC)
            self.stato = FERMO
            self._emit("media_attesa_clic" if self._clic.in_gioco else "media_rientro_automatico",
                       market_id=self._mid, selection_id=self._sid,
                       profitto_lordo=round(lordo, 4),
                       profitto_netto=round(netto_da_lordo(lordo, self.par.commissione), 4),
                       filtri=self.par.rientro_auto_filtri,
                       msg=("ciclo chiuso in gioco: %+.2f EUR netti. Clicca Attiva adesso "
                            "per ripartire" % netto_da_lordo(lordo, self.par.commissione))
                       if self._clic.in_gioco else
                       ("ciclo chiuso prima del fischio: %+.2f EUR netti. Nuovo ciclo da "
                        "solo, %s" % (netto_da_lordo(lordo, self.par.commissione),
                                      "quando i filtri d'ingresso lo permettono"
                                      if self.par.rientro_auto_filtri
                                      else "subito al miglior prezzo")))
            return True
        self.stato = FINE if inplay else FERMO
        return True

    def _nuovo_ciclo(self) -> None:
        self._ordini = []
        self._punta = None
        self._spostamenti = {}
        self._ritoccate = set()
        self._scoperto = None
        self._ultimo_ingresso = None
        self._rientri = 0
        self._t_lordo = None
        self._rientri_bloccati = None
        self._banca_vista = {}
        self._dichiarati.discard("massimo")
        self.stats["rientri_bloccati"] = None
        self._clic.origine = None
        self.stats["origine_ciclo"] = None

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

    def _in_gioco_a_clic(self, market: Any, mb: Any, now: float, aperto: bool,
                         bb: Optional[float], bl: Optional[float], sb: Optional[float],
                         sl: Optional[float]) -> None:
        """07/10 (ATTIVA ADESSO, punto 4 della regola dell'utente): la sessione
        avviata col pulsante, IN GIOCO, opera come pre-match (banca di chiusura,
        rientri, massimo, rischio massimo) senza i filtri d'ingresso; mercato
        SOSPESO (gol) = nessun ordine finche' non riapre. Un ciclo chiuso in gioco
        NON riparte da solo (ATTESA_CLIC). Il riquadro <<chiusura>> resta
        pubblicato (informativo)."""
        pos = posizione_da_ordini(self._ordini)
        if not self._clic.in_gioco_detto:
            self._clic.in_gioco_detto = True
            self._emit("media_live", level="CRITICAL" if pos.aperta else "INFO",
                       market_id=self._mid, totale_puntato=round(pos.puntato, 2),
                       banca=self._descrivi_banca(), a_clic=True,
                       msg=("partita in gioco con %.2f EUR puntati: la modalita' avviata col "
                            "pulsante continua a gestire la posizione come progettato "
                            "(banca, rientri)" % pos.puntato) if pos.aperta else
                       "partita in gioco senza posizione: si aspetta il clic su Attiva adesso")
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
        if aperto:
            self._pre_match(market, mb, now, bb, bl, sb, sl)
        self._pubblica(None, bb, bl, forza=True)

    # ------------------------------------------------- ATTIVA ADESSO (07/10)
    def comando_consumato(self) -> Optional[str]:
        """L'id dell'ultimo comando del pulsante gia' consumato."""
        return self._clic.consumato

    def ricevi_comando(self, cid: str, inviato_ms: Optional[float], ora_ms: float,
                       prezzi_vivi: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        """La sessione consegna il comando <<Attiva adesso>> (thread della
        sessione). Un id gia' consumato non fa niente (None). Altrimenti il
        comando e' CONSUMATO subito (mai due volte, mai accodato per dopo):
        scaduto o coi prezzi fermi o col mercato sospeso (ultimo book visto) =
        rifiutato col motivo; valido = PRONTO, e diventa eseguibile solo quando la
        sessione l'ha registrato nella riga (``rilascia_comando``). Torna le
        informazioni del comando (per le stats e l'attivita')."""
        cid = str(cid or "").strip()
        if not cid or cid == self._clic.consumato:
            return None
        self._clic.consumato = cid
        info: Dict[str, Any] = {"id": cid, "esito": "ricevuto", "motivo": None,
                                "inviato_ms": inviato_ms, "ricevuto_ms": float(ora_ms),
                                "deciso_ms": None, "prezzo": None, "importo": None,
                                "in_gioco": None}
        self.stats["comando"] = info
        if inviato_ms is not None and float(ora_ms) - float(inviato_ms) > \
                ATTESA_MASSIMA_COMANDO_S * 1000.0:
            self._rifiuta_comando(info, "comando scaduto: cliccato %d s fa (oltre %d s non "
                                        "si esegue)" % ((float(ora_ms) - float(inviato_ms))
                                                        / 1000.0, ATTESA_MASSIMA_COMANDO_S))
        elif prezzi_vivi is False:
            self._rifiuta_comando(info, "prezzi fermi: il flusso dei prezzi della partita e' "
                                        "interrotto, nessun ordine (riprova quando torna)")
        elif self._clic.ultimo_aperto is False:
            self._rifiuta_comando(info, "mercato sospeso: nessun ordine (riprova quando riapre)")
        else:
            self._clic.pronto = info
        return dict(info)

    def rilascia_comando(self) -> bool:
        """La sessione ha registrato il comando nella riga (l'id consumato
        sopravvive a un riavvio): da adesso si esegue al prossimo book."""
        c, self._clic.pronto = self._clic.pronto, None
        if c is None:
            return False
        self._clic.comando = c
        return True

    def annulla_comando(self, motivo: str) -> None:
        """La sessione NON e' riuscita a registrare il comando: non si esegue
        (senza registrazione un riavvio potrebbe rieseguirlo)."""
        c, self._clic.pronto = self._clic.pronto, None
        if c is not None:
            self._rifiuta_comando(c, motivo)

    def _rifiuta_comando(self, info: Dict[str, Any], motivo: str,
                         now: Optional[float] = None) -> None:
        info["esito"] = "rifiutato"
        info["motivo"] = motivo
        info["deciso_ms"] = now
        self.stats["comando"] = info
        self._emit("media_comando_rifiutato", level="WARN", market_id=self._mid,
                   comando=info.get("id"), motivo=motivo,
                   msg="Attiva adesso NON eseguito: %s" % motivo)

    def _motivo_no_comando(self, aperto: bool, bb: Optional[float], now: float,
                           mb: Any) -> Optional[str]:
        """Perche' il clic NON si esegue su questo book (None = si punta). Non
        sono filtri di strategia: solo protezioni e stato."""
        if self.stato == BLOCCATA:
            return ("modalita' bloccata: posizione di una sessione precedente non "
                    "ricostruibile, nessun ordine")
        if self.stato == RIPRESA:
            return "ripresa dal conto in corso: nessun ordine finche' non e' finita"
        if self._esito is not None or getattr(mb, "status", None) == "CLOSED":
            return "mercato chiuso"
        if self.force_flat:
            return "sessione in arresto (stop, freno o fine vita): nessuna apertura"
        pos = posizione_da_ordini(self._ordini)
        if (pos.aperta or self._punta is not None
                or any(vivo_o_in_volo(o) for o in self._ordini)
                or self.stato not in (FERMO, ATTESA_CLIC, FINE)):
            return ("gia' in posizione (stato %s, %.2f EUR puntati): il clic non apre un "
                    "secondo ciclo" % (self.stato, pos.puntato))
        if not aperto:
            return "mercato sospeso: nessun ordine (riprova quando riapre)"
        if bb is None:
            return "nessun prezzo di punta disponibile sull'Under"
        if now < self._fermo_punte_ms:
            return "attesa dopo un rifiuto di Betfair"
        return None

    def _esegui_comando(self, market: Any, mb: Any, now: float, inplay: bool, aperto: bool,
                        bb: Optional[float]) -> None:
        """Il clic su QUESTO book: PUNTA SUBITO lo stake base al miglior prezzo
        di punta, senza i filtri d'ingresso; poi la modalita' gestisce la
        posizione come progettato. Consumato in ogni caso (mai accodato)."""
        info, self._clic.comando = self._clic.comando, None
        if info is None:
            return
        info["in_gioco"] = bool(inplay)
        motivo = self._motivo_no_comando(aperto, bb, now, mb)
        if motivo:
            self._rifiuta_comando(info, motivo, now)
            return
        self._nuovo_ciclo()
        self._clic.a_clic = True
        self.stats["a_clic"] = True
        o = self._punta_d_ingresso(market, now, bb, ORIGINE_CLIC)
        if o is None:
            # freno dei soldi veri o rifiuto: la modalita' e' comunque "a clic"
            self.stato = ATTESA_CLIC
            self._rifiuta_comando(info, "punta non partita (%s)"
                                  % (self._apertura_ferma or "rifiutata da Betfair"), now)
            return
        info.update({"esito": "eseguito", "deciso_ms": now,
                     "prezzo": float(o.order_type.price), "importo": float(o.order_type.size)})
        self.stats["comando"] = info
        self._emit("media_comando_eseguito", level="CRITICAL", market_id=self._mid,
                   selection_id=self._sid, comando=info.get("id"),
                   prezzo=info["prezzo"], importo=info["importo"], in_gioco=bool(inplay),
                   msg="Attiva adesso: punta %.2f EUR @%.2f %s" % (
                       info["importo"], info["prezzo"],
                       "in gioco" if inplay else "prima del fischio"))

    def _segui_banca_in_live(self) -> None:
        """Cambi rilevanti della banca in gioco: abbinata (anche in parte),
        caduta (Betfair l'ha annullata: "la banca non e' piu' a mercato").
        07/10: su TUTTE le banche del ciclo (banca, integrazioni, sostituti);
        caduta = una banca morta con un resto non abbinato che il bot NON ha
        ritoccato (annullo, riduzione o spostamento suoi) e che Betfair aveva
        accettato (un rifiuto si dice gia' come rifiuto)."""
        banche = self._banche()
        if not banche:
            return
        vista = self._banca_vista
        m = sum(abbinato(b)[0] for b in banche)
        if m > float(vista.get("abbinato", 0.0)) + 0.005:
            d = self._descrivi_banca()
            self._emit("media_banca_abbinata", level="CRITICAL", market_id=self._mid,
                       abbinato=round(m, 2), importo=d.get("importo"),
                       msg="banca di chiusura abbinata %.2f (banca appoggiata %.2f @%s)"
                           % (m, float(d.get("importo") or 0.0), d.get("quota")))
            vista["abbinato"] = m
        cadute = vista.setdefault("cadute", set())
        for b in banche:
            mb, _a = abbinato(b)
            if (vivo_o_in_volo(b) or id(b) in self._ritoccate or id(b) in cadute
                    or getattr(b, "bet_id", None) is None
                    or mb + 0.005 >= float(b.order_type.size)):
                continue
            cadute.add(id(b))
            vista["caduta"] = True
            self._emit("media_banca_caduta", level="CRITICAL", market_id=self._mid,
                       abbinato=round(mb, 2), importo=float(b.order_type.size),
                       msg="la banca non e' piu' a mercato (annullata da Betfair o "
                           "scaduta): abbinato %.2f su %.2f" % (mb, float(b.order_type.size)))

    def _descrivi_banca(self) -> Dict[str, Any]:
        """La banca appoggiata per la UI e le stats (stesse chiavi di prima).
        07/10: la banca puo' essere fatta di piu' ordini alla STESSA quota (la
        banca spostata col replace + le integrazioni): importo e abbinato sono
        la somma del gruppo corrente (le banche vive, o quelle all'ultima quota),
        ``ordini`` quanti sono; durante uno spostamento ``quote`` le elenca."""
        banche = self._banche()
        if not banche:
            return {"stato": "nessuna", "testo": "nessuna banca appoggiata"}
        vive = [b for b in banche if vivo_o_in_volo(b)]
        ultima = (vive or banche)[-1]
        q = float(ultima.order_type.price)
        gruppo = vive or [b for b in banche if abs(float(b.order_type.price) - q) < 1e-9]
        size = round(sum(float(b.order_type.size) for b in gruppo), 2)
        m = round(sum(abbinato(b)[0] for b in gruppo), 2)
        if vive:
            stato = "viva" if m <= 0 else "abbinata_in_parte"
        elif m + 0.005 >= size:
            stato = "abbinata"
        elif all(id(b) in self._ritoccate for b in gruppo
                 if abbinato(b)[0] + 0.005 < float(b.order_type.size)):
            return {"stato": "nessuna", "testo": "nessuna banca appoggiata"}
        else:
            stato = "caduta"
        testo = {"viva": "appoggiata, non ancora abbinata",
                 "abbinata_in_parte": "appoggiata, abbinata in parte",
                 "abbinata": "abbinata per intero",
                 "caduta": "la banca non e' piu' a mercato"}[stato]
        quote = sorted({round(float(b.order_type.price), 2) for b in gruppo})
        if len(gruppo) > 1:
            testo += (" (%d ordini alla stessa quota)" % len(gruppo) if len(quote) == 1
                      else " (in spostamento: %s)" % " -> ".join("%.2f" % x for x in quote))
        out = {"stato": stato, "importo": size, "quota": q, "abbinato": m,
               "persistenza": str(getattr(ultima.order_type, "persistence_type", "") or ""),
               "testo": testo, "ordini": len(gruppo)}
        if len(quote) > 1:
            out["quote"] = quote
        return out

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
        if _lato(o) == "LAY":
            # una banca annullata dal bot non e' <<caduta>> (07/10)
            self._ritoccate.add(id(o))
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
        s["a_clic"] = self._clic.a_clic
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

    # ------------------------------------------------- stop (P1, 06/10)
    def banca_da_lasciare(self, o: Any) -> bool:
        """P1 (decisione dell'utente del 06/10): allo STOP della sessione la
        banca di chiusura PERSIST resta appoggiata (la posizione resta protetta
        e si chiude da sola). True per QUELLA banca, viva, con una posizione
        aperta: la sessione non la annulla all'arresto."""
        if self.stato == RIPRESA:
            # durante la ripresa la banca riadottata da flumine non e' ancora
            # "la" banca della modalita': si lascia ogni banca PERSIST viva sua
            tr = getattr(o, "trade", None)
            return (tr is not None and getattr(tr, "strategy", None) is self
                    and _lato(o) == "LAY" and vivo_o_in_volo(o)
                    and str(getattr(o.order_type, "persistence_type", "") or "") == "PERSIST")
        # 07/10: OGNI banca viva del ciclo (la banca, le integrazioni, i
        # sostituti dei replace) e' "la" banca di chiusura
        try:
            ordini = list(self._ordini)
        except Exception:  # noqa: BLE001 - lista che cambia nel thread di flumine
            return False
        if (_lato(o) != "LAY" or not any(o is x for x in ordini) or not vivo_o_in_volo(o)):
            return False
        if str(getattr(o.order_type, "persistence_type", "") or "") != "PERSIST":
            return False
        try:
            return posizione_da_ordini(ordini).aperta
        except Exception:  # noqa: BLE001 - lista che cambia nel thread di flumine
            return False

    def pronta_allo_stop(self) -> bool:
        """Dopo lo STOP (force-flat): nessuna punta viva e, prima del fischio con
        una posizione aperta, la banca viva copre l'intera posizione. La sessione
        aspetta questo (non il piatto: la banca resta per decisione dell'utente)."""
        if self._esito is not None:
            return True
        ordini = list(self._ordini)
        if any(_lato(o) == "BACK" and vivo_o_in_volo(o) for o in ordini):
            return False
        pos = posizione_da_ordini(ordini)
        if abs(pos.se_vince - pos.se_perde) <= self._toll_pari():
            return not any(vivo_o_in_volo(o) for o in ordini)
        if self.stato in (LIVE, FINE, BLOCCATA):
            # in gioco la modalita' non piazza e non riprezza: resta cio' che c'e'
            return True
        # 07/10: le banche vive (anche piu' ordini) tutte sul book alla quota
        # giusta, nessuno spostamento in volo, e la somma dei resti copre la
        # posizione (a meno della parte sotto il minimo DICHIARATA)
        vive = [x for x in ordini if _lato(x) == "LAY" and vivo_o_in_volo(x)]
        if not vive or self._spostamenti or any(not eseguibile(x) for x in vive):
            return False
        c = quota_della_banca(self._ultimo_ingresso, pos, self.par.tick_chiusura)
        if c is None or any(abs(float(x.order_type.price) - c) > 1e-9 for x in vive):
            return False
        resto = sum(float(getattr(x, "size_remaining", 0.0) or 0.0) for x in vive)
        voluto = al_centesimo(banca_esatta(pos, c))
        if abs(resto - voluto) <= 0.01:
            return True
        sc = self._scoperto
        return (sc is not None and abs(sc[0] - c) < 1e-9
                and abs(resto + sc[2] - voluto) <= 0.01)

    def _ritira_la_punta_allo_stop(self, market: Any) -> None:
        """Allo STOP la punta in corso (ingresso o rientro) si ritira subito: la
        banca poi si riallinea sull'intera posizione (``_assicura_banca``)."""
        p = self._punta
        if p is not None and eseguibile(p):
            self._annulla(market, p, "stop della sessione: la punta si ritira, la banca "
                                     "resta appoggiata (decisione dell'utente P1)")

    # ------------------------------------------------- ripresa (P13, 06/10)
    def prepara_ripresa(self, righe: Optional[Sequence[Dict[str, Any]]]) -> None:
        """La sessione in SOLDI VERI ha letto il conto (``listCurrentOrders``
        filtrato sul ``customerStrategyRef`` della modalita' di QUESTA partita):
        se ci sono ordini la modalita' entra in RIPRESA (nessun ordine finche'
        non ha ricostruito il ciclo); senza ordini parte come nuova."""
        righe = [dict(r) for r in (righe or []) if r.get("bet_id")]
        if not righe:
            self._ripresa = None
            if self.stato == RIPRESA:
                self.stato = ATTESA_CLIC if self._clic.a_clic else FERMO
            self._emit("media_ripresa", ordini=0,
                       msg="ripresa: nessun ordine della modalita' sul conto, si parte da "
                           "zero")
            return
        self._ripresa = {"righe": righe, "letto": True, "da_ms": None}
        self.stato = RIPRESA
        self.stats["stato"] = RIPRESA
        self._emit("media_ripresa_avviata", level="CRITICAL", ordini=len(righe),
                   msg="ripresa: %d ordini della modalita' sul conto; nessun ordine nuovo "
                       "finche' la posizione non e' ricostruita" % len(righe))

    def ordini_dal_conto(self) -> List[Any]:
        """Gli ordini della partita letti dal conto alla ripresa e NON presenti
        nel blotter di questo processo (chiusi prima del crash): la sessione li
        conta nell'esposizione (``scalper_session._esposizioni_nette``)."""
        return list(self._ordini_conto)

    def conto_non_letto(self, errore: str) -> None:
        """La lettura del conto e' fallita: RIPRESA senza righe (nessun ordine);
        la sessione riprova al battito."""
        self._ripresa = {"righe": None, "letto": False, "da_ms": None, "errore": str(errore)}
        self.stato = RIPRESA
        self.stats["stato"] = RIPRESA

    def attende_il_conto(self) -> bool:
        """La sessione deve (ri)leggere il conto per la ripresa."""
        r = self._ripresa
        return self.stato == RIPRESA and r is not None and not r.get("letto")

    def _forse_riprendi(self, market: Any, now: float) -> None:
        r = self._ripresa
        if r is None:
            self.stato = ATTESA_CLIC if self._clic.a_clic else FERMO
            return
        if not r.get("letto"):
            self._una_volta("ripresa_conto", "media_ripresa_in_attesa", level="CRITICAL",
                            market_id=self._mid, errore=r.get("errore"),
                            msg="ripresa in soldi veri: il conto non si legge (%s); nessun "
                                "ordine finche' non si legge" % r.get("errore"))
            return
        if r["da_ms"] is None:
            r["da_ms"] = now
        mie = [x for x in r["righe"] if x.get("market_id") == self._mid
               and int(x.get("selection_id") or 0) == int(self._sid or -1)]
        altre = [x for x in r["righe"] if x not in mie]
        if altre:
            self._una_volta("ripresa_altre", "media_ripresa_ordini_estranei", level="CRITICAL",
                            market_id=self._mid, bet_ids=[x.get("bet_id") for x in altre],
                            msg="ripresa: %d ordini della modalita' su un altro mercato o "
                                "selezione: NON governati, verificali sul conto" % len(altre))
        try:
            blotter = [o for o in market.blotter.strategy_orders(self)
                       if int(getattr(o, "selection_id", -1)) == int(self._sid or -1)]
        except Exception:  # noqa: BLE001 - blotter illeggibile: si aspetta
            return
        per_bet = {str(o.bet_id): o for o in blotter if getattr(o, "bet_id", None)}
        mancano = [x["bet_id"] for x in mie
                   if str(x.get("status")) == "EXECUTABLE" and x["bet_id"] not in per_bet]
        if mancano:
            if now - float(r["da_ms"]) >= ATTESA_RIPRESA_MS:
                self._blocca_ripresa("ordini VIVI del conto non ritrovati nel blotter di "
                                     "flumine dopo %d s: %s"
                                     % (ATTESA_RIPRESA_MS // 1000, mancano))
            return
        ordini: List[Any] = []
        visti: set = set()
        conto: List[Any] = []
        for x in mie:
            o = per_bet.get(x["bet_id"])
            if o is None:
                o = OrdineDelConto(x)
                conto.append(o)
            ordini.append(o)
            visti.add(x["bet_id"])
        self._ordini_conto = conto
        for bid, o in per_bet.items():
            if bid not in visti:
                ordini.append(o)
        self._ricostruisci(ordini, now)

    def _blocca_ripresa(self, motivo: str) -> None:
        self._ripresa = None
        self.riavvio = "ripresa non riuscita: %s" % motivo
        self.stato = BLOCCATA
        self.stats["riavvio"] = self.riavvio
        self._emit("media_ripresa_fallita", level="CRITICAL", market_id=self._mid,
                   motivo=motivo,
                   msg="ripresa NON riuscita (%s): nessun ordine, verifica la posizione sul "
                       "conto e chiudila a mano" % motivo)

    def _ricostruisci(self, ordini: Sequence[Any], now: float) -> None:
        """Il ciclo corrente dagli ordini VERI (riadottati da flumine o letti dal
        conto): stessi conti della macchina a stati, nessun ordine."""
        cicli = cicli_degli_ordini(ordini)
        chiusi = list(cicli[:-1])
        ultimo = list(cicli[-1]) if cicli else []
        if ultimo and _ciclo_finito(ultimo):
            chiusi.append(ultimo)
            ultimo = []
        lordo_chiusi = 0.0
        for c in chiusi:
            pc = posizione_da_ordini(c)
            lordo_chiusi += min(pc.se_vince, pc.se_perde)
        punte_vive = [o for o in ultimo if _lato(o) == "BACK" and vivo_o_in_volo(o)]
        # 07/10: piu' banche vive sono normali (la banca spostata col replace +
        # le integrazioni): si riprendono tutte e l'allineamento le porta alla
        # quota giusta senza mai superare la posizione. Due PUNTE vive no.
        if len(punte_vive) > 1:
            self._blocca_ripresa("%d punte vive insieme sul conto" % len(punte_vive))
            return
        self._nuovo_ciclo()
        self.stats["cicli_chiusi"] = len(chiusi)
        self.stats["pnl_chiuso_lordo"] = round(lordo_chiusi, 4)
        self._ordini = list(ultimo)
        abbinate = [o for o in ultimo if _lato(o) == "BACK" and not vivo_o_in_volo(o)
                    and abbinato(o)[0] > 0]
        if abbinate:
            m0, _p = abbinato(abbinate[0])
            p0 = float(abbinate[0].order_type.price)
            if self.par.obiettivo_netto is not None:
                self._t_lordo = lordo_da_netto(self.par.obiettivo_netto, self.par.commissione)
            else:
                c0 = tick_sotto(p0, self.par.tick_chiusura)
                self._t_lordo = obiettivo_automatico(m0, p0, c0) if c0 else None
            self._rientri = len(abbinate) - 1
            self._ultimo_ingresso = float(abbinate[-1].order_type.price)
        if punte_vive:
            self._punta, self._punta_ms = punte_vive[0], now
            self._punta_rientro = bool(abbinate)
        pos = posizione_da_ordini(self._ordini)
        if self._punta is not None:
            self.stato = RIENTRO if self._punta_rientro else INGRESSO
        elif pos.aperta:
            self.stato = MASSIMO if self._rientri >= self.par.max_rientri else IN_POSIZIONE
            if self.stato == MASSIMO:
                self._dichiarati.add("massimo")
        else:
            self._ordini = []
            self._punta = None
            self.stato = ATTESA_CLIC if self._clic.a_clic else FERMO
        self._ripresa = None
        b = self._banca
        self._emit("media_ripresa", level="CRITICAL" if pos.aperta else "INFO",
                   market_id=self._mid, selection_id=self._sid, ordini=len(ordini),
                   cicli_chiusi=len(chiusi), stato=self.stato, rientri=self._rientri,
                   totale_puntato=round(pos.puntato, 2),
                   quota_media=(round(pos.quota_media, 4) if pos.quota_media else None),
                   banca=(None if b is None else {"importo": float(b.order_type.size),
                                                  "quota": float(b.order_type.price),
                                                  "resto": float(getattr(b, "size_remaining", 0.0)
                                                                 or 0.0)}),
                   msg="ripresa dal conto: %s; %d cicli chiusi prima; stato %s, rientri %d, "
                       "puntato %.2f%s%s"
                       % ("posizione aperta" if pos.aperta else "nessuna posizione aperta",
                          len(chiusi), self.stato, self._rientri, pos.puntato,
                          (" a media %.4f" % pos.quota_media) if pos.quota_media else "",
                          (", banca %.2f @%.2f" % (float(b.order_type.size),
                                                   float(b.order_type.price))) if b else ""))

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

    def serve_ordini_conto(self) -> bool:
        """Gli ordini del conto servono solo quando il riquadro "chiusura" e'
        pubblicato (massimo dei rientri o in gioco) con una posizione aperta."""
        return ((self.stato in (LIVE, MASSIMO) or (self._clic.a_clic and self._clic.in_gioco))
                and self.posizione_aperta())

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
