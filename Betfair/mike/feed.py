"""feed — dal payload del FEED UNICO (``safe_strategy_scan``) allo ``Snapshot`` dell'engine.

Logica PURA (testabile senza DB): riceve la riga pubblicata dallo scanner Safe
(ramo pre-KO O/U acceso con ``SAFE_PRE_KO_OU_HOURS``) e ne estrae:
  - ``EventInfo``: nomi, KO, market_id/selection_id delle due linee (risolti PER NOME);
  - ``Snapshot``: book per selezione (best back/lay + size, stato, inplay, betDelay),
    minuto, gol, intervallo, freschezza, P(4) implicita di mercato.

Nessuna chiamata Betfair: Mike legge SOLO il feed (regola dei processi).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from Betfair.stream import flusso_prezzi as _flusso
from Betfair.stream.trading.xhedge import OVER_UNDER, canonical_selection

from . import engine as E

_LINE_TO_MARKET = {3.5: E.MARKET_OU35, 4.5: E.MARKET_OU45}


@dataclass(frozen=True)
class EventInfo:
    event_id: str
    event_name: str
    home: Optional[str]
    away: Optional[str]
    competition: Optional[str]
    ko_at: Optional[float]                      # epoch UTC
    open_date: Optional[str]
    markets: Dict[str, str]                     # {"OU35": market_id, "OU45": market_id}
    selections: Dict[Tuple[str, str], int]     # {(market, UNDER|OVER): selection_id}

    @property
    def complete(self) -> bool:
        return (E.MARKET_OU35 in self.markets and E.MARKET_OU45 in self.markets
                and (E.MARKET_OU35, E.SEL_UNDER) in self.selections
                and (E.MARKET_OU45, E.SEL_OVER) in self.selections)

    def market_id(self, market: str) -> Optional[str]:
        return self.markets.get(market)

    def selection_id(self, market: str, selection: str) -> Optional[int]:
        return self.selections.get((market, selection))

    def selection_name(self, market: str, selection: str) -> str:
        line = E.LINE[market]
        return f"{'Under' if selection == E.SEL_UNDER else 'Over'} {line} Goals"


def parse_iso_epoch(value: Any) -> Optional[float]:
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (TypeError, ValueError):
        return None


def _num(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def blocco_osservato(blk: Dict[str, Any], now: float, max_age_s: float) -> bool:
    """Qualcuno sta ancora guardando questo mercato?

    ``seen_ms`` (13/09) e' il momento dell'ULTIMO BOOK RICEVUTO dallo scanner,
    diverso da ``ts_ms`` che e' l'ultimo CAMBIO DI PREZZO. La distinzione e'
    money-critical: un prezzo fermo da dieci minuti su un mercato che stiamo
    guardando E' il prezzo corrente e ci si opera; lo stesso prezzo su un mercato
    uscito dal feed e' un ricordo, e comprarci sopra una copertura vuol dire
    credere di essere coperti quando non lo si e'.

    Uno scanner vecchio che non scrive ancora ``seen_ms`` non deve far sparire i
    book: in quel caso (campo assente) si risponde "osservato", cioe' il
    comportamento di prima. Il rischio si chiude quando il produttore e'
    aggiornato, non rompendo il bot nel frattempo.
    """
    ms = blk.get("seen_ms")
    if ms is None:
        return True
    try:
        return (now - float(ms) / 1000.0) <= float(max_age_s)
    except (TypeError, ValueError):
        return True


def mercati_fermi(payload: Dict[str, Any]) -> frozenset:
    """CANTIERE J (28/09): i market_id che lo scanner dichiara col flusso prezzi
    fermo (``payload.flusso.mercati_fermi``). Vuoto se la riga non lo dice."""
    blk = _flusso.blocco_riga(payload)
    if blk is None:
        return frozenset()
    return frozenset(str(m) for m in (blk.get("mercati_fermi") or []))


def linea_decisa(market: str, goals: Optional[int]) -> bool:
    """30/09 (mercato deciso): la linea ``market`` e' gia' DECISA dal punteggio
    (gol > linea: Over vinto, Under perso)? Stessa regola di
    ``engine.selection_decided``, non una copia."""
    return E.selection_decided(market, E.SEL_OVER, goals) is not None


def linea_di_riferimento(goals: Optional[int]) -> str:
    """30/09 (mercato deciso): la PRIMA linea di Mike ancora in gioco col
    punteggio ``goals`` (3,5 fino a 3 gol, 4,5 con 4 gol). Con tutte e due
    decise (5+ gol) resta il 3,5: nulla e' piu' gestibile e il regolamento e'
    la strada giusta (regola di prima)."""
    for market in (E.MARKET_OU35, E.MARKET_OU45):
        if not linea_decisa(market, goals):
            return market
    return E.MARKET_OU35


def mercati_di_mike(payload: Dict[str, Any]) -> list:
    """I market_id delle linee di Mike (3.5 e 4.5) presenti nella riga e ANCORA
    IN GIOCO.

    30/09 (mercato deciso, ordine dell'utente): una linea gia' DECISA dal
    punteggio della riga (gol > linea) non serve piu' a nessun ordine (il suo
    esito e' certo, senza prezzo) e Betfair la sospende e la CHIUDE subito: il
    suo flusso "fermo" non deve fermare la partita. Una linea ancora in gioco
    col flusso fermo continua a bloccare (regola del 28/09)."""
    goals = goals_from_payload(payload)
    out = []
    for blk in payload.get("ou") or []:
        if not isinstance(blk, dict) or not blk.get("market_id"):
            continue
        line = _num(blk.get("line"))
        if line is not None and line in _LINE_TO_MARKET:
            if linea_decisa(_LINE_TO_MARKET[line], goals):
                continue
            out.append(str(blk["market_id"]))
    return out


def flusso_esito(row: Dict[str, Any], scanner_stato: Optional[Dict[str, Any]] = None,
                 now: Optional[float] = None) -> "_flusso.Esito":
    """CANTIERE J (28/09): i prezzi delle linee di Mike sono VIVI? (giro dello
    scanner non bloccato + nessuna delle due linee col flusso fermo). Mike non
    decide sul MATCH_ODDS (prima del fischio non e' nemmeno sullo stream)."""
    payload = row.get("payload") if isinstance(row, dict) else None
    if not isinstance(payload, dict):
        return _flusso.NON_NOTO
    adesso_ms = None if now is None else int(float(now) * 1000)
    esito = _flusso.valuta(payload, scanner_stato, None, mercati_di_mike(payload), adesso_ms)
    if esito.vivo or esito.motivo != _flusso.MOTIVO_MERCATO_FERMO:
        return esito
    # 30/09: il testo dice QUALE linea e' ferma e da quanto e' arrivato il suo
    # ultimo book (il "da N s" generico conta dal passaggio del MATCH ODDS)
    testo = testo_flusso_mike(payload, adesso_ms)
    return replace(esito, testo=testo) if testo else esito


# 30/09 (revisione critica): nomi delle linee come li legge il trader
_NOME_LINEA = {E.MARKET_OU35: "Under/Over 3,5", E.MARKET_OU45: "Under/Over 4,5"}


def _adesso_ms(adesso_ms: Optional[int]) -> int:
    return int(adesso_ms) if adesso_ms is not None else int(time.time() * 1000)


def linee_ferme_mike(payload: Dict[str, Any],
                     adesso_ms: Optional[int] = None) -> List[Tuple[str, str, Optional[float]]]:
    """30/09: le linee di Mike ANCORA IN GIOCO (``mercati_di_mike``) che lo
    scanner dichiara col flusso fermo (``flusso.mercati_fermi``), come
    ``(market_id, nome, secondi dall'ultimo book ricevuto)``. I secondi vengono
    da ``seen_ms`` del blocco ``ou`` (l'ultimo book RICEVUTO dallo scanner per
    quella linea); None se la riga non lo porta (scanner precedente al 13/09).
    Stessa regola di ``flusso_esito``, nessuna soglia nuova."""
    fermi = mercati_fermi(payload)
    usati = set(mercati_di_mike(payload))
    adesso = _adesso_ms(adesso_ms)
    fl = payload.get(_flusso.CHIAVE)
    fl_da_ms = fl.get("fermi_da_ms") if isinstance(fl, dict) else None
    out: List[Tuple[str, str, Optional[float]]] = []
    for blk in payload.get("ou") or []:
        if not isinstance(blk, dict):
            continue
        mid = str(blk.get("market_id") or "")
        if not mid or mid not in usati or mid not in fermi:
            continue
        line = _num(blk.get("line"))
        nome = _NOME_LINEA.get(_LINE_TO_MARKET.get(line), mid) if line is not None else mid
        # 30/09: PRIMA ``flusso.fermi_da_ms`` (l'istante VERO dell'ultima
        # conferma con prezzi, scritto dallo scanner quando la linea diventa
        # ferma); ``seen_ms`` solo come ripiego (scanner precedente): e' fuori
        # firma, la riga non si riscrive se cambia solo lui, quindi sovrastima.
        da = _num((fl_da_ms or {}).get(mid))
        seen = da if da is not None and da > 0 else _num(blk.get("seen_ms"))
        eta = round(max(0.0, (adesso - seen) / 1000.0), 1) if seen is not None and seen > 0 else None
        out.append((mid, nome, eta))
    return out


def testo_flusso_mike(payload: Dict[str, Any], adesso_ms: Optional[int] = None) -> Optional[str]:
    """30/09: il testo dell'avviso di flusso fermo delle linee di Mike: quale
    linea e da quanto e' arrivato il suo ultimo book. None se nessuna linea di
    Mike e' ferma o se una non porta ``seen_ms`` (resta il testo di prima)."""
    linee = linee_ferme_mike(payload, adesso_ms)
    if not linee or any(eta is None for _m, _n, eta in linee):
        return None
    parti = [f"{nome} ({mid}) ferma, ultimo book ricevuto {eta:.0f} s fa"
             for mid, nome, eta in linee]
    return "flusso prezzi fermo sulle linee di Mike: " + "; ".join(parti)


def secondi_fermo_mike(payload: Optional[Dict[str, Any]],
                       stato: Optional[Dict[str, Any]] = None,
                       adesso_ms: Optional[int] = None) -> Optional[float]:
    """30/09: da quanti secondi i prezzi delle linee di Mike non arrivano: il
    piu' vecchio fra gli ultimi book delle linee ferme e, col giro dello
    scanner bloccato, l'eta' dell'ultimo calcolo. MAI ``flusso.dal_ms`` (e' il
    passaggio del MATCH ODDS: contava dal fischio). Riga senza ``seen_ms``:
    ``flusso_prezzi.secondi_fermo`` come prima."""
    if not isinstance(payload, dict):
        return _flusso.secondi_fermo(payload, stato, adesso_ms)
    adesso = _adesso_ms(adesso_ms)
    linee = linee_ferme_mike(payload, adesso)
    if any(eta is None for _m, _n, eta in linee):
        return _flusso.secondi_fermo(payload, stato, adesso)
    candidati = [float(eta) for _m, _n, eta in linee if eta is not None]
    if isinstance(stato, dict) and isinstance(stato.get(_flusso.CHIAVE), dict):
        calc = _num(stato[_flusso.CHIAVE].get("calcolato_ms"))
        if calc is not None and calc > 0 and (adesso - calc) / 1000.0 > _flusso.STATO_CALCOLO_MAX_S:
            candidati.append((adesso - calc) / 1000.0)
    return round(max(candidati), 1) if candidati else None


def payload_blocchi_ou(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """{OU35/OU45: blocco} della riga SENZA filtri (per bet_delay e inplay dal
    feed quando i prezzi vengono dal REST)."""
    out: Dict[str, Dict[str, Any]] = {}
    for blk in payload.get("ou") or []:
        if isinstance(blk, dict):
            m = _LINE_TO_MARKET.get(_num(blk.get("line")))
            if m is not None:
                out[m] = blk
    return out


def blocco_da_rest(rest: Optional[Dict[str, Any]],
                   feed_blk: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """CANTIERE J2: un book REST (``omega_market.read_book``: ``status``,
    ``inplay``, ``runners`` con ``back_price``/``lay_price``/``*_size``) nella
    forma del blocco ``ou`` del feed, che ``_book_for`` legge. ``bet_delay``
    dal feed (il REST non lo porta). None se il mercato non e' OPEN o vuoto."""
    if not isinstance(rest, dict) or str(rest.get("status") or "").upper() != "OPEN":
        return None
    sel = []
    for r in rest.get("runners") or []:
        if isinstance(r, dict) and r.get("selection_id") is not None:
            sel.append({"selection_id": int(r["selection_id"]), "back": r.get("back_price"),
                        "back_size": r.get("back_size"), "lay": r.get("lay_price"),
                        "lay_size": r.get("lay_size")})
    if not sel:
        return None
    return {"market_id": rest.get("market_id") or feed_blk.get("market_id"), "status": "OPEN",
            "inplay": bool(rest.get("inplay")), "bet_delay": feed_blk.get("bet_delay"),
            "selections": sel, "fonte": _flusso.FONTE_RIPIEGO_REST}


def ou_blocks(payload: Dict[str, Any], *, now: Optional[float] = None,
              seen_max_s: Optional[float] = None) -> Dict[str, Dict[str, Any]]:
    """{OU35: blocco, OU45: blocco} dalla lista ``ou`` del payload.

    Con ``now`` e ``seen_max_s`` i blocchi NON PIU' OSSERVATI vengono scartati
    come se non ci fossero: Mike sa gia' non fare niente quando un book manca,
    mentre non aveva nessun modo di sospettare di un book presente ma morto.
    """
    out: Dict[str, Dict[str, Any]] = {}
    # CANTIERE J (28/09): con ``now`` (cioe' quando si DECIDE) anche una linea
    # il cui flusso prezzi e' fermo per lo scanner viene scartata come assente:
    # stesso trattamento del blocco non piu' osservato. ``event_info`` (senza
    # ``now``) non filtra: gli id servono per annullare ordini vivi.
    fermi = mercati_fermi(payload) if now is not None else frozenset()
    # 30/09 sera (review incrociata): ``seen_ms`` e' FUORI FIRMA: la riga non si
    # riscrive se cambia solo lui, quindi su una linea col prezzo FERMO (ma
    # osservata, book ogni secondo) ``seen_ms`` invecchia e dopo 90 s la linea
    # spariva come «morta» anche se lo scanner la dichiarava viva. Con il
    # blocco ``flusso`` nella riga (scanner dal 28/09) la vita di una linea la
    # dice LO SCANNER (``mercati_fermi``, fresco a ogni riscrittura, e il
    # tetto assoluto di ``feed_fresh``): il controllo su ``seen_ms`` resta SOLO
    # per le righe di uno scanner precedente, senza ``flusso``.
    scanner_dichiara = isinstance(payload.get(_flusso.CHIAVE), dict)
    for blk in payload.get("ou") or []:
        if not isinstance(blk, dict):
            continue
        if (now is not None and seen_max_s is not None and not scanner_dichiara
                and not blocco_osservato(blk, now, seen_max_s)):
            continue
        if fermi and str(blk.get("market_id") or "") in fermi:
            continue
        line = _num(blk.get("line"))
        market = _LINE_TO_MARKET.get(line) if line is not None else None
        if market is None:
            continue
        out[market] = blk
    return out


def event_info(event_id: str, payload: Dict[str, Any]) -> EventInfo:
    blocks = ou_blocks(payload)
    markets: Dict[str, str] = {}
    sels: Dict[Tuple[str, str], int] = {}
    for market, blk in blocks.items():
        if blk.get("market_id"):
            markets[market] = str(blk["market_id"])
        for i, s in enumerate(blk.get("selections") or []):
            if not isinstance(s, dict) or s.get("selection_id") is None:
                continue
            canon = canonical_selection(OVER_UNDER, s.get("name"), i + 1)
            if canon in (E.SEL_UNDER, E.SEL_OVER):
                sels[(market, canon)] = int(s["selection_id"])
    return EventInfo(
        event_id=str(event_id),
        event_name=str(payload.get("event_name") or ""),
        home=payload.get("home"), away=payload.get("away"),
        competition=payload.get("competition"),
        ko_at=parse_iso_epoch(payload.get("open_date")),
        open_date=payload.get("open_date"),
        markets=markets, selections=sels,
    )


def _book_for(blk: Optional[Dict[str, Any]], selection_id: Optional[int]) -> Optional[E.Book]:
    if not blk or selection_id is None:
        return None
    for s in blk.get("selections") or []:
        if isinstance(s, dict) and s.get("selection_id") is not None and int(s["selection_id"]) == int(selection_id):
            return E.Book(
                best_back=_num(s.get("back")), back_size=float(_num(s.get("back_size")) or 0.0),
                best_lay=_num(s.get("lay")), lay_size=float(_num(s.get("lay_size")) or 0.0),
                status=str(blk.get("status") or "OPEN").upper(),
                inplay=bool(blk.get("inplay")),
                bet_delay=int(_num(blk.get("bet_delay")) or 0),
            )
    return None


def implied_p4(blocks: Dict[str, Dict[str, Any]], info: EventInfo) -> Optional[float]:
    """P(esattamente 4 gol) implicita dai back devig delle due linee: P(O3.5) - P(O4.5)."""
    def p_over(market: str) -> Optional[float]:
        blk = blocks.get(market)
        bo = _book_for(blk, info.selection_id(market, E.SEL_OVER))
        bu = _book_for(blk, info.selection_id(market, E.SEL_UNDER))
        if bo is None or bu is None or not bo.best_back or not bu.best_back:
            return None
        io, iu = 1.0 / bo.best_back, 1.0 / bu.best_back
        return io / (io + iu) if io + iu > 0 else None
    po35, po45 = p_over(E.MARKET_OU35), p_over(E.MARKET_OU45)
    if po35 is None or po45 is None:
        return None
    return round(max(0.0, po35 - po45), 4)


def market_totals(blocks: Dict[str, Dict[str, Any]], info: EventInfo) -> Optional[Dict[int, float]]:
    """Distribuzione dei GOL TOTALI implicita nel MERCATO, in tre classi.

    Il P&L di Mike dipende solo da tre casi: <=3 gol (Under 3.5 vince), 4 gol
    esatti (perdono entrambe le linee), >=5 gol (Over 4.5 vince). Le due linee
    O/U quotate danno esattamente queste tre probabilita', de-viggate:
        P(<=3) = 1 - P(O3.5) · P(4) = P(O3.5) - P(O4.5) · P(>=5) = P(O4.5)
    Si restituisce nella forma attesa da ``hold_expectation`` (chiave = un
    totale rappresentativo della classe: 3, 4, 5).

    CERTIFICAZIONE 12/09 — serve quando il dossier della partita e' vuoto
    (leghe minori senza fixture): senza questa, l'uscita in perdita ricadeva su
    una soglia PERCENTUALE fissa che chiude posizioni ancora favorite. Il
    mercato non e' il modello, ma e' pur sempre il consenso di chi scommette:
    meglio decidere sul suo prezzo che su una percentuale arbitraria.
    """
    def p_over(market: str) -> Optional[float]:
        blk = blocks.get(market)
        bo = _book_for(blk, info.selection_id(market, E.SEL_OVER))
        bu = _book_for(blk, info.selection_id(market, E.SEL_UNDER))
        if bo is None or bu is None or not bo.best_back or not bu.best_back:
            return None
        io_, iu = 1.0 / bo.best_back, 1.0 / bu.best_back
        return io_ / (io_ + iu) if io_ + iu > 0 else None

    po35, po45 = p_over(E.MARKET_OU35), p_over(E.MARKET_OU45)
    if po35 is None or po45 is None:
        return None
    p_le3 = max(0.0, 1.0 - po35)
    p4 = max(0.0, po35 - po45)
    p_ge5 = max(0.0, po45)
    tot = p_le3 + p4 + p_ge5
    if tot <= 0:
        return None
    return {3: round(p_le3 / tot, 6), 4: round(p4 / tot, 6), 5: round(p_ge5 / tot, 6)}


def ht_active_from_payload(payload: Dict[str, Any]) -> bool:
    raw = payload.get("score_raw") or {}
    status = str(raw.get("matchStatus") or raw.get("match_status") or "").lower()
    if not status:
        return False
    return ("half" in status and "end" in status) or status in ("halftime", "half_time", "ht")


def goals_from_payload(payload: Dict[str, Any]) -> Optional[int]:
    h, a = payload.get("score_home"), payload.get("score_away")
    if h is None or a is None:
        return None
    try:
        return int(h) + int(a)
    except (TypeError, ValueError):
        return None


def _hard_max_age() -> float:
    """Tetto assoluto sull'eta' di una riga del feed, condiviso con lo scanner.
    Import PIGRO e guardato: se il modulo non e' importabile si usa il default
    (180 s) invece di far esplodere il ciclo di Mike."""
    try:
        from Betfair.stream.scores import scan_feed as _sf

        return float(_sf.HARD_MAX_AGE_SEC)
    except Exception:  # noqa: BLE001
        return 180.0


def feed_fresh(row: Dict[str, Any], now: float, max_age_s: float, scanner_age_s: Optional[float],
               scanner_alive_max_s: float = 75.0) -> bool:
    """Riga fresca (età ≤ max_age) OPPURE scanner vivo (write-on-change: riga
    immutata = nulla e' cambiato) — stessa regola di scan_feed.fresh_payload.

    CERTIFICAZIONE 12/09 — con un TETTO ASSOLUTO (``scan_feed.HARD_MAX_AGE_SEC``)
    che vale ANCHE a scanner vivo: se il feed di QUESTA partita si ferma (IPS
    muto sul suo chunk, evento uscito dal catalogo) mentre lo scanner continua a
    scrivere le altre, "scanner vivo" non dice piu' nulla su questa riga e Mike
    deciderebbe su un punteggio di ore prima. Stessa falla corretta in
    ``scan_feed.fresh_payload`` (difetto P7 dell'audit del motore condiviso).
    """
    age = None
    ts = parse_iso_epoch(row.get("updated_at"))
    if ts is not None:
        age = now - ts
    if age is not None and age <= max_age_s:
        return True
    if age is not None and age > max(float(max_age_s), _hard_max_age()):
        return False            # oltre il tetto: nessun bypass, mai
    return scanner_age_s is not None and scanner_age_s <= scanner_alive_max_s


def order_fresh(row: Dict[str, Any], now: float, params: Dict[str, Any],
                scanner_age_s: Optional[float]) -> bool:
    """Freschezza per EMETTERE UN ORDINE: piu' stretta di ``feed_fresh``, ma
    stretta sulla cosa GIUSTA.

    MISURA 13/09 ore 21:37 — ``safe_strategy_scan.updated_at`` non dice "quando
    ho guardato": dice "quando e' cambiato qualcosa", perche' lo scanner scrive
    solo cio' che cambia. Su una linea O/U pre-partita che nessuno scambia la
    riga resta ferma per minuti ed e' CORRETTO: quel prezzo E' il prezzo
    corrente. Su 57 righe nessuna era sotto i 24 s — e Mike apre SOLO su quelle
    linee (``is_candidate``: non in gioco, fischio entro
    ``entry_hours_before_ko``). La vecchia soglia di 15 s sull'eta' della riga
    era irraggiungibile per costruzione, e rifiutava ingressi buoni.

    Quindi: prima il tetto assoluto, che non si deroga mai (oltre
    ``HARD_MAX_AGE_SEC`` una riga non e' un prezzo, e' un ricordo). Poi o la riga
    e' davvero recente, oppure il PRODUTTORE ha battuto da poco.

    Perche' due soglie e non una piu' severa per tutti: in live l'ordine parte
    comunque FILL_OR_KILL a prezzo LIMIT, quindi un prezzo mosso non si abbina —
    non si abbina MALE. Il danno vero di un prezzo vecchio e' altrove: nella
    fedelta' del PAPER (fill inventati su un prezzo che non esiste piu', che
    gonfiano un risultato simulato su cui poi si decide di andare in live) e nel
    CASH OUT, dove si attraversa lo spread davvero.
    """
    ts = parse_iso_epoch(row.get("updated_at"))
    age = None if ts is None else now - ts
    if age is None or age > _hard_max_age():
        return False
    if age <= float(params.get("order_max_age_s") or 20.0):
        return True
    return (scanner_age_s is not None
            and scanner_age_s <= float(params.get("order_scanner_max_s") or 30.0))


def snapshot_from_row(row: Dict[str, Any], info: EventInfo, *, now: float, params: Dict[str, Any],
                      scanner_age_s: Optional[float], hazard: Optional[float] = None,
                      p4_model: Optional[float] = None, last_goal_ts: Optional[float] = None,
                      market_status_override: Optional[str] = None,
                      cover_gain_pct: Optional[float] = None, pressure: float = 1.0,
                      model_probs: Optional[Dict[str, float]] = None,
                      p_total_model: Optional[Dict[int, float]] = None,
                      p_total_emp: Optional[Dict[int, float]] = None,
                      p_under35_cal: Optional[float] = None,
                      scanner_stato: Optional[Dict[str, Any]] = None,
                      books_rest: Optional[Dict[str, Dict[str, Any]]] = None) -> Optional[E.Snapshot]:
    payload = row.get("payload") if isinstance(row, dict) else None
    if not isinstance(payload, dict) or info.ko_at is None:
        return None
    # CANTIERE J (28/09): flusso prezzi fermo sulle linee di Mike (o giro dello
    # scanner bloccato) = feed NON fresco per decidere e per ordinare, anche se
    # la riga e' appena stata riscritta per un cambio di punteggio (26/09).
    esito_flusso = flusso_esito(row, scanner_stato, now)
    flusso_vivo = esito_flusso.vivo
    # I book su cui si DECIDE: un blocco non piu' osservato viene scartato come
    # se non ci fosse (vedi ``blocco_osservato``). Mike sa gia' non fare niente
    # quando un book manca; non sapeva sospettare di un book presente ma morto,
    # e ci comprava sopra la copertura credendo di essersi coperto.
    # Attenzione: ``event_info`` NON filtra — i market_id e i selection_id devono
    # restare disponibili anche per un mercato che abbiamo smesso di guardare,
    # altrimenti non potremmo nemmeno ANNULLARE un ordine ancora vivo li' sopra.
    blocks = ou_blocks(payload, now=now,
                       seen_max_s=float(params.get("book_seen_max_s") or 90.0))
    if esito_flusso.motivo == _flusso.MOTIVO_SCANNER_BLOCCATO:
        # giro dello scanner fermo: nessuna linea e' confermata (cantiere J)
        blocks = {}
    # CANTIERE J2 (28/09, regola unica): col flusso fermo le linee lette dal
    # RIPIEGO REST (book vivo, mercato aperto) tornano nella decisione con i
    # prezzi di Betfair adesso. ``order_fresh`` resta FALSO: nessuna apertura.
    rest_usato = False
    if not flusso_vivo and books_rest:
        for mkey, rest in books_rest.items():
            blk = blocco_da_rest(rest, (payload_blocchi_ou(payload).get(mkey) or {}))
            if blk is not None:
                blocks[mkey] = blk
                rest_usato = True
    books: Dict[Tuple[str, str], E.Book] = {}
    for key in ((E.MARKET_OU35, E.SEL_UNDER), (E.MARKET_OU45, E.SEL_OVER), (E.MARKET_OU45, E.SEL_UNDER)):
        bk = _book_for(blocks.get(key[0]), info.selection_id(*key))
        if bk is not None:
            books[key] = bk
    blk35 = blocks.get(E.MARKET_OU35) or {}
    inplay = bool(payload.get("inplay")) or bool(blk35.get("inplay"))
    # 30/09 (mercato deciso): lo stato del mercato si legge dalla prima linea
    # ANCORA IN GIOCO (col 4-0 il 3,5 e' chiuso da Betfair ma il 4,5 e' aperto),
    # non da una linea gia' decisa.
    blk_stato = blocks.get(linea_di_riferimento(goals_from_payload(payload))) or {}
    status = market_status_override or str(blk_stato.get("status") or payload.get("mo_status") or "OPEN").upper()
    return E.Snapshot(
        now=float(now), ko_at=float(info.ko_at), books=books, inplay=inplay,
        minute=payload.get("minute") if isinstance(payload.get("minute"), int) else None,
        goals=goals_from_payload(payload),
        ht_active=ht_active_from_payload(payload),
        feed_fresh=rest_usato or (
            flusso_vivo and feed_fresh(row, now, float(params["feed_max_age_s"]), scanner_age_s,
                                       float(params.get("scanner_alive_max_s") or 75.0))),
        order_fresh=flusso_vivo and order_fresh(row, now, params, scanner_age_s),
        fonte_prezzi=(_flusso.FONTE_RIPIEGO_REST if rest_usato else "feed"),
        hazard=hazard, p4_market=implied_p4(blocks, info), p4_model=p4_model,
        last_goal_ts=last_goal_ts, market_status=status, final_total=None,
        total_matched=_num(blk35.get("total_matched")),   # diagnostica, nessun gate
        cover_gain_pct=cover_gain_pct, pressure=float(pressure or 1.0), model_probs=model_probs,
        p_total_model=p_total_model, p_total_emp=p_total_emp,
        p_total_market=market_totals(blocks, info),
        p_under35_cal=p_under35_cal,
    )


def is_candidate(info: EventInfo, payload: Dict[str, Any], *, now: float, params: Dict[str, Any]) -> bool:
    """Partita da ARMARE ADESSO: entrambe le linee nel feed e KO ancora da venire,
    entro la finestra pre-match. Il filtro per competizione vive nei params.

    L4 — una partita GIA' IN CORSO non viene piu' armata: Mike non entra mai
    in-play da zero (l'unico ingresso live e' il re-ingresso dopo un profitto),
    quindi armarla produceva solo IDLE_LIVE → SETTLED "nessuna operazione" e
    rumore nella lista. Le partite armate pre-KO restano seguite anche in-play
    (vengono da ``mike_events``, non da qui).
    """
    if not info.complete or info.ko_at is None:
        return False
    comp_filter = [s.strip().lower() for s in str(params.get("competition_filter") or "").split(",") if s.strip()]
    if comp_filter and not any(f in str(info.competition or "").lower() for f in comp_filter):
        return False
    if bool(payload.get("inplay")):
        return False
    return 0 < info.ko_at - now <= float(params["entry_hours_before_ko"]) * 3600.0
