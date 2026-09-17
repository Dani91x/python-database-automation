"""omega_market — wrapper Betfair REST per Omega (I/O, non testato in unità).

Riusa la sessione Betfair condivisa (``odds_refresh.get_shared_client``): NON
apre un secondo login. Espone: listing eventi calcio di oggi, risoluzione del
mercato CORRECT_SCORE, lettura del book (→ ScoreRunner), piazzamento LAY reale.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from Betfair.omega import omega_engine as E
from Betfair.omega.omega_config import CUSTOMER_STRATEGY_REF, FOOTBALL_EVENT_TYPE_ID

logger = logging.getLogger("omega.market")


# ---------------------------------------------------------------------------
# Sessione condivisa + retry con re-login (come odds_refresh._with_client)
# ---------------------------------------------------------------------------
def get_client() -> Any:
    from Betfair.odds_refresh import get_shared_client

    return get_shared_client()


def call(fn: Callable[[Any], Any]) -> Any:
    """Esegue ``fn(client)`` con un re-login+retry singolo su errore — SOLO per
    le LETTURE (idempotenti)."""
    from Betfair.odds_refresh import get_shared_client, reset_shared_client

    try:
        return fn(get_shared_client())
    except Exception as ex:  # noqa: BLE001
        logger.warning("[omega] chiamata Betfair fallita, re-login e retry: %s", str(ex)[:160])
        reset_shared_client()
        return fn(get_shared_client())


_SESSION_ERRORS = ("INVALID_SESSION_INFORMATION", "NO_SESSION", "NO_APP_KEY", "INVALID_APP_KEY")


def _is_session_error(ex: Exception) -> bool:
    s = str(ex).upper()
    return any(k in s for k in _SESSION_ERRORS)


def call_mutating(fn: Callable[[Any], Any]) -> Any:
    """Esegue una chiamata che CAMBIA STATO (place/cancel): MAI ritentata su un
    errore generico (un timeout può nascondere un ordine già accettato → doppio
    ordine reale, review H1). Re-login+retry solo se l'exchange dice
    esplicitamente che la sessione non è valida (l'ordine non è stato ricevuto)."""
    from Betfair.odds_refresh import get_shared_client, reset_shared_client

    try:
        return fn(get_shared_client())
    except Exception as ex:  # noqa: BLE001
        if _is_session_error(ex):
            logger.warning("[omega] sessione non valida su chiamata mutante, re-login: %s", str(ex)[:160])
            reset_shared_client()
            return fn(get_shared_client())
        raise


def keep_alive() -> None:
    """Tiene VIVA la sessione condivisa con una chiamata leggera (listEventTypes).

    PROATTIVO (~600s dal loop di servizio, §8): il retry con re-login di
    ``call()`` resta solo rete di sicurezza — il place LIVE non è idempotente
    oltre i 60s di de-dup Betfair, quindi non bisogna MAI arrivare al place con
    la sessione scaduta contando sul retry. Passa da ``call()``: se la sessione
    è già morta, re-login immediato.
    """
    call(lambda c: c.betting_rpc("SportsAPING/v1.0/listEventTypes", {"filter": {}}))


# ---------------------------------------------------------------------------
# Modelli
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EventInfo:
    event_id: str
    name: str
    open_date: Optional[datetime]
    # metadati per la UI (menu Missione): competizione da Betfair, best-effort.
    country_code: Optional[str] = None
    competition_id: Optional[str] = None
    competition_name: Optional[str] = None


@dataclass(frozen=True)
class CorrectScoreMarket:
    market_id: str
    event_id: str
    event_name: str
    market_start_time: Optional[datetime]
    runner_names: dict[int, str]


@dataclass(frozen=True)
class MarketSnapshot:
    status: str            # OPEN | SUSPENDED | CLOSED
    inplay: bool
    runners: list[E.ScoreRunner]
    closed: bool
    winner_selection_id: Optional[int]
    voided: bool
    # C.12a — PERCHE' e' void, detto per nome. Il void di Omega/Safe e' sempre
    # stato DEDOTTO (CLOSED + tutti i runner terminali + nessun WINNER) e non e'
    # mai stato confrontato con lo ``status`` che Betfair dichiara
    # (``VOID``/``VOIDED``), che invece Mike guarda (``service.py:692-711``).
    # Qui il comportamento NON cambia — ``voided`` resta quello che era — ma il
    # motivo smette di essere implicito: ``market_status_void`` quando lo dice
    # Betfair, ``closed_senza_winner`` quando lo abbiamo dedotto noi. La
    # divergenza fra i due e' un reperto per l'utente, non una correzione da
    # fare di iniziativa (le regole di regolamento sono strategia).
    void_reason: Optional[str] = None


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _best_lay(levels: Any) -> tuple[Optional[float], float, tuple[tuple[float, float], ...]]:
    """Ritorna (best_price, best_size, ladder) da availableToLay."""
    if not levels:
        return None, 0.0, ()
    ladder: list[tuple[float, float]] = []
    for l in levels:
        if not isinstance(l, dict) or not l.get("price"):
            continue
        try:
            price, size = float(l["price"]), float(l.get("size") or 0.0)
        except (TypeError, ValueError):
            continue
        # certificazione 12/09: un livello a prezzo non finito o size <= 0 non
        # è liquidità (prima ``l["size"]`` mancante era un KeyError sull'intero
        # book e un NaN passava fino al prezzo dell'ordine)
        if not (math.isfinite(price) and math.isfinite(size)) or price < 1.0 or size <= 0:
            continue
        ladder.append((price, size))
    ladder = tuple(ladder)
    if not ladder:
        return None, 0.0, ()
    best_price, best_size = ladder[0]
    return best_price, best_size, ladder


def _best_back(levels: Any) -> tuple[Optional[float], float]:
    """(best back price, size abbinabile) da availableToBack, con gli STESSI
    filtri del lato lay. Certificazione 12/09: prima si leggeva ``levels[0]``
    senza guardare né la finitezza né la size, e la size del back non finiva
    MAI nello snapshot automatico (``ScoreRunner.back_size`` restava 0,0): il
    ranking per costo di copertura (§15) trattava "size ignota" come "liquidità
    sufficiente" e poteva scegliere un risultato NON copribile."""
    for l in levels or ():
        if not isinstance(l, dict) or not l.get("price"):
            continue
        try:
            price, size = float(l["price"]), float(l.get("size") or 0.0)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(price) and math.isfinite(size)) or price <= 1.0 or size <= 0:
            continue
        return price, size
    return None, 0.0


def _best_back_price(levels: Any) -> Optional[float]:
    """Compatibilità: solo il prezzo (vedi ``_best_back``)."""
    return _best_back(levels)[0]


# ---------------------------------------------------------------------------
# Listing eventi calcio di oggi (include i match già iniziati)
# ---------------------------------------------------------------------------
def today_window_utc(now: datetime, *, lookback_hours: int = 12) -> tuple[str, str]:
    """(from, to) ISO-Z della finestra "eventi di oggi": da ``now − lookback`` alla
    FINE DELLA GIORNATA OPERATIVA Europe/Rome (§2/§4: "marketStartTime cade
    oggi"). Certificazione 12/09: prima il tetto era 23:59:59 **UTC**, cioè fino
    alle 01:59 di Roma del giorno dopo — due ore di partite di DOMANI entravano
    nell'universo di oggi (gambe residue e target per gamba falsati)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    start = now - timedelta(hours=lookback_hours)
    end = E.day_end_utc(now) - timedelta(seconds=1)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return start.astimezone(timezone.utc).strftime(fmt), end.astimezone(timezone.utc).strftime(fmt)


def list_today_football_events(lookback_hours: int = 12,
                               with_competitions: bool = False) -> list[EventInfo]:
    """Eventi calcio di oggi. ``with_competitions=True`` aggiunge la competizione
    (1 listMarketCatalogue extra per chunk da 100): serve SOLO al refresh della
    cache UI — il loop automatico, che chiama questa funzione a ogni ciclo,
    NON deve pagare la chiamata in più."""
    now = datetime.now(timezone.utc)
    from_date, to_date = today_window_utc(now, lookback_hours=lookback_hours)
    raw = call(lambda c: c.list_events([FOOTBALL_EVENT_TYPE_ID], from_date=from_date, to_date=to_date)) or []
    out: list[EventInfo] = []
    for e in raw:
        ev = e.get("event", {}) or {}
        eid = ev.get("id")
        if not eid:
            continue
        out.append(EventInfo(str(eid), ev.get("name", "") or "", _parse_iso(ev.get("openDate")),
                             country_code=ev.get("countryCode")))
    if with_competitions:
        comps = competitions_by_event([e.event_id for e in out])
        if comps:
            from dataclasses import replace as _dc_replace

            out = [
                _dc_replace(e, competition_id=comps[e.event_id][0], competition_name=comps[e.event_id][1])
                if e.event_id in comps else e
                for e in out
            ]
    return out


def competitions_by_event(event_ids: list[str]) -> dict[str, tuple[Optional[str], Optional[str]]]:
    """event_id -> (competition_id, competition_name) via listMarketCatalogue
    MATCH_ODDS con projection EVENT+COMPETITION (1 chiamata per chunk di 100).
    BEST-EFFORT: su errore torna la mappa parziale (la lista eventi non deve
    mai fallire per colpa dei metadati)."""
    out: dict[str, tuple[Optional[str], Optional[str]]] = {}
    for i in range(0, len(event_ids), 100):
        chunk = event_ids[i:i + 100]
        try:
            cats = call(lambda c: c.list_market_catalogue(
                chunk, ["MATCH_ODDS"], max_results=200,
                market_projection=["EVENT", "COMPETITION"])) or []
        except Exception as ex:  # noqa: BLE001
            logger.warning("[omega] competizioni non lette (chunk %s): %s", i, str(ex)[:160])
            continue
        for mk in cats:
            ev = mk.get("event") or {}
            comp = mk.get("competition") or {}
            eid = ev.get("id")
            if not eid or str(eid) in out:
                continue
            if comp.get("id") is None and not comp.get("name"):
                continue
            out[str(eid)] = (
                str(comp["id"]) if comp.get("id") is not None else None,
                comp.get("name") or None,
            )
    return out


# ---------------------------------------------------------------------------
# Risoluzione mercato CORRECT_SCORE per evento
# ---------------------------------------------------------------------------
def get_correct_score_market(event: EventInfo) -> Optional[CorrectScoreMarket]:
    cats = call(lambda c: c.list_market_catalogue([event.event_id], ["CORRECT_SCORE"], max_results=5)) or []
    for mk in cats:
        mid = mk.get("marketId")
        if not mid:
            continue
        names = {
            int(r["selectionId"]): r.get("runnerName", "?")
            for r in mk.get("runners", [])
            if r.get("selectionId") is not None
        }
        return CorrectScoreMarket(
            market_id=str(mid),
            event_id=event.event_id,
            event_name=(mk.get("event", {}) or {}).get("name") or event.name,
            market_start_time=_parse_iso(mk.get("marketStartTime")),
            runner_names=names,
        )
    return None


# ---------------------------------------------------------------------------
# Lettura book → ScoreRunner + esito settlement
# ---------------------------------------------------------------------------
def read_market(market: CorrectScoreMarket) -> Optional[MarketSnapshot]:
    books = call(lambda c: c.list_market_book([market.market_id])) or []
    if not books:
        return None
    return _snapshot_from_book(market, books[0])


def _snapshot_from_book(market: CorrectScoreMarket, b: dict) -> MarketSnapshot:
    status = b.get("status", "OPEN")
    inplay = bool(b.get("inplay", False))
    closed = status == "CLOSED"
    runners: list[E.ScoreRunner] = []
    winner: Optional[int] = None
    any_winner = False
    runner_statuses: list[Optional[str]] = []
    for r in b.get("runners", []):
        sid = r.get("selectionId")
        if sid is None:
            continue
        sid = int(sid)
        rstatus = r.get("status")
        runner_statuses.append(rstatus)
        if rstatus == "WINNER":
            winner = sid
            any_winner = True
        ex = r.get("ex", {}) or {}
        lay_price, lay_size, ladder = _best_lay(ex.get("availableToLay"))
        back_price, back_size = _best_back(ex.get("availableToBack"))
        runners.append(
            E.ScoreRunner(
                selection_id=sid,
                name=market.runner_names.get(sid, "?"),
                lay_price=lay_price,
                lay_size=lay_size,
                back_price=back_price,
                back_size=back_size,
                lay_ladder=ladder,
            )
        )
    # money-critical: la decisione closed/voided è delegata a E.resolve_settlement
    # (funzione PURA e testata) — vedi omega_engine. Non dedurre mai 'void' dalla
    # sola assenza di WINNER: serve che TUTTI i runner siano terminali.
    closed, voided = E.resolve_settlement(status, runner_statuses, any_winner)
    return MarketSnapshot(
        status=status,
        inplay=inplay,
        runners=runners,
        closed=closed,
        winner_selection_id=winner,
        voided=voided,
        void_reason=void_reason(status, voided),
    )


_STATI_VOID = ("VOID", "VOIDED")


def void_reason(market_status: Optional[str], voided: bool) -> Optional[str]:
    """Il nome del motivo per cui il mercato risulta annullato (C.12a).

    ``market_status_void`` = lo dichiara Betfair con lo ``status`` del mercato;
    ``closed_senza_winner`` = lo abbiamo DEDOTTO (chiuso, runner tutti terminali,
    nessun vincitore). PURA: non cambia nessuna decisione, da' solo un nome a
    una deduzione che finora era anonima.
    """
    if str(market_status or "").upper() in _STATI_VOID:
        return "market_status_void"
    return "closed_senza_winner" if voided else None


def read_markets(markets: list) -> dict:
    """{market_id: MarketSnapshot | None} per una LISTA di mercati in una sola
    ``listMarketBook`` per blocco di 40 (review M6: prima una chiamata REST per
    trade aperto per ciclo). Un mercato assente dalla risposta → None."""
    out: dict = {}
    by_id = {m.market_id: m for m in markets}
    ids = list(by_id)
    for i in range(0, len(ids), 40):
        chunk = ids[i:i + 40]
        try:
            books = call(lambda c, ch=chunk: c.list_market_book(ch)) or []
        except Exception as ex:  # noqa: BLE001 — F7: errore ≠ mercato sparito: il blocco
            # resta FUORI dalla risposta (il chiamante rilegge uno a uno o salta il ciclo)
            logger.warning("[omega] listMarketBook batch KO: %s", str(ex)[:120])
            continue
        seen = set()
        for b in books:
            mid = str(b.get("marketId") or "")
            if mid in by_id:
                out[mid] = _snapshot_from_book(by_id[mid], b)
                seen.add(mid)
        for mid in chunk:
            if mid not in seen:
                out[mid] = None
    return out


# ---------------------------------------------------------------------------
# MISSIONI: mercato per TIPO (HALF_TIME_SCORE / CORRECT_SCORE / OVER_UNDER_X5)
# ---------------------------------------------------------------------------
def get_event_market_by_type(
    event_id: str, event_name: str, market_type: str,
) -> Optional[CorrectScoreMarket]:
    """Risolve il mercato di ``market_type`` per l'evento, con i runner names
    presi DALLO STESSO catalogo (selectionId → runnerName: la coppia id/nome
    non può mai disallinearsi). Ritorna None se il mercato non esiste.
    """
    cats = call(lambda c: c.betting_rpc(
        "SportsAPING/v1.0/listMarketCatalogue",
        {
            "filter": {"eventIds": [event_id], "marketTypeCodes": [market_type]},
            "maxResults": 3,
            "marketProjection": ["MARKET_DESCRIPTION", "RUNNER_DESCRIPTION",
                                 "MARKET_START_TIME", "EVENT"],
        },
    )) or []
    for mk in cats:
        mid = mk.get("marketId")
        # difesa money-critical: accetta SOLO il tipo richiesto (mai un mercato
        # "simile" restituito per errore dal filtro).
        mtype = (mk.get("description", {}) or {}).get("marketType")
        if not mid or mtype != market_type:
            continue
        names = {
            int(r["selectionId"]): r.get("runnerName", "?")
            for r in mk.get("runners", [])
            if r.get("selectionId") is not None
        }
        return CorrectScoreMarket(
            market_id=str(mid),
            event_id=str(event_id),
            event_name=(mk.get("event", {}) or {}).get("name") or event_name,
            market_start_time=_parse_iso(mk.get("marketStartTime")),
            runner_names=names,
        )
    return None


# ---------------------------------------------------------------------------
# MISSIONI: punteggi live BATCH dall'in-play service Betfair (endpoint pubblico,
# GET senza sessione exchange → NESSUN secondo login, coerente con §5).
# Parser riusato da Betfair/stream/scores (lo stesso in produzione nel runner).
# ---------------------------------------------------------------------------
_INPLAY_SCORES_URL = "https://ips.betfair.com/inplayservice/v1.1/scores"


def get_inplay_scores(event_ids: list) -> dict:
    """{event_id: ScoreSnapshot} per gli eventi live. Difensivo: errori → {}."""
    if not event_ids:
        return {}
    import requests

    from Betfair.stream.scores.betfair_inplay import parse_score_dict

    try:
        resp = requests.get(
            _INPLAY_SCORES_URL,
            params={"eventIds": ",".join(str(e) for e in event_ids),
                    "alt": "json", "regionCode": "UK", "locale": "en_GB"},
            headers={"Connection": "keep-alive", "Content-Type": "application/json"},
            timeout=8,
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception as ex:  # noqa: BLE001 — il punteggio non deve mai fermare il bot
        logger.warning("[omega] inplay scores KO: %s", str(ex)[:120])
        return {}
    out: dict = {}
    for item in raw if isinstance(raw, list) else []:
        eid = item.get("eventId")
        if eid is None:
            continue
        try:
            out[str(eid)] = parse_score_dict(str(eid), item)
        except Exception:  # noqa: BLE001 — una riga malformata non blocca le altre
            continue
    return out


# ---------------------------------------------------------------------------
# MANUALE: elenco mercati di un evento + lettura book generico
# ---------------------------------------------------------------------------
def list_event_markets(event_id: str, max_results: int = 30) -> list[dict]:
    """Tutti i mercati di un evento (per il menu Manuale), ordinati per volume."""
    cats = call(lambda c: c.betting_rpc(
        "SportsAPING/v1.0/listMarketCatalogue",
        {
            "filter": {"eventIds": [event_id]},
            "maxResults": max_results,
            "sort": "MAXIMUM_TRADED",
            "marketProjection": ["MARKET_DESCRIPTION", "RUNNER_DESCRIPTION", "MARKET_START_TIME", "EVENT"],
        },
    )) or []
    out: list[dict] = []
    for mk in cats:
        mid = mk.get("marketId")
        if not mid:
            continue
        desc = mk.get("description", {}) or {}
        out.append({
            "market_id": str(mid),
            "market_name": mk.get("marketName"),
            "market_type": desc.get("marketType"),
            "total_matched": mk.get("totalMatched"),
            "event_name": (mk.get("event", {}) or {}).get("name"),
            "runner_names": {
                int(r["selectionId"]): r.get("runnerName", "?")
                for r in mk.get("runners", []) if r.get("selectionId") is not None
            },
        })
    return out


def read_book(market_id: str, runner_names: dict[int, str]) -> Optional[dict]:
    """Snapshot generico di un mercato (lay+back best) per la modalità manuale."""
    books = call(lambda c: c.list_market_book([market_id])) or []
    if not books:
        return None
    b = books[0]
    runners = []
    for r in b.get("runners", []):
        sid = r.get("selectionId")
        if sid is None:
            continue
        sid = int(sid)
        ex = r.get("ex", {}) or {}
        lay_price, lay_size, ladder = _best_lay(ex.get("availableToLay"))
        # certificazione 12/09: prezzo e size del back dallo STESSO livello
        # filtrato (prima il prezzo veniva da levels[0] e la size pure, ma senza
        # il filtro finitezza/size>0: una coppia incoerente finiva nella UI)
        back_price, back_size = _best_back(ex.get("availableToBack"))
        runners.append({
            "selection_id": sid,
            "name": runner_names.get(sid, "?"),
            "status": r.get("status"),
            "lay_price": lay_price,
            "lay_size": lay_size,
            "back_price": back_price,
            "back_size": back_size,
            "lay_ladder": [list(x) for x in ladder],
        })
    return {
        "market_id": str(market_id),
        "status": b.get("status", "OPEN"),
        "inplay": bool(b.get("inplay", False)),
        "runners": runners,
    }


# ---------------------------------------------------------------------------
# Piazzamento LAY reale (LIVE) — soldi veri
# ---------------------------------------------------------------------------
class PlaceRifiutato(RuntimeError):
    """Rifiuto CERTO di Betfair: nessun ordine e' (piu') vivo a mercato.

    C.12a — serve a distinguere il rifiuto dall'esito IGNOTO. Il place-and-trim
    solleva per entrambi i casi: un rifiuto al parcheggio significa che NESSUN
    ordine e' stato creato, mentre un taglio non confermato significa che un
    ordine POTREBBE essere ancora vivo. Chi legge l'eccezione non puo'
    indovinare quale dei due sia, e il chiamante (``execution.place``) lasciava
    la riga 'pending' IN VERIFICA su un ordine che non esiste: il segnale
    restava bloccato e la liability contata piena. Con questa eccezione il
    rifiuto certo diventa una riga 'error' col codice di Betfair, e l'esito
    ignoto resta l'unico caso che va in riconciliazione.
    """

    def __init__(self, messaggio: str, *, error_code: Optional[str] = None,
                 order_status: Optional[str] = None) -> None:
        super().__init__(messaggio)
        self.error_code = error_code
        self.order_status = order_status


@dataclass(frozen=True)
class PlaceResult:
    ok: bool
    order_status: Optional[str]
    bet_id: Optional[str]
    size_matched: float
    avg_price_matched: Optional[float]
    raw: dict = field(default_factory=dict)
    # --- C.12a: CONSAPEVOLEZZA DELL'ORDINE -----------------------------------
    # Prima di oggi il chiamante sapeva solo QUANTO si era abbinato: la size
    # CHIESTA spariva (nessuno la conservava sul percorso REST) e il residuo non
    # esisteva come numero. "Ordine x a prezzo y: quanto e' stato abbinato?" non
    # aveva risposta senza rileggere Betfair. Questi campi hanno tutti un
    # default: nessun chiamante o test esistente cambia.
    #
    # ATTENZIONE alla fonte: ``PlaceInstructionReport`` di Betfair NON contiene
    # ``sizeRemaining`` (lo porta solo ``listCurrentOrders``, vedi
    # ``betfairlightweight/resources/bettingresources.py:664-711`` per
    # ``CurrentOrder`` contro ``:981-1011`` per ``PlaceOrderInstructionReports``).
    # Qui ``size_remaining`` e' quindi il residuo AL MOMENTO DELLA RISPOSTA,
    # calcolato dai due numeri che il report da' davvero: con FILL_OR_KILL vale
    # sempre 0 (Betfair ha ucciso il non abbinato), senza FOK vale
    # chiesto - abbinato. Il residuo di DOPO lo dice solo la riconciliazione.
    size_requested: Optional[float] = None
    price_requested: Optional[float] = None
    size_remaining: Optional[float] = None
    error_code: Optional[str] = None
    size_cancelled: Optional[float] = None
    size_lapsed: Optional[float] = None
    size_voided: Optional[float] = None
    # istante dichiarato da BETFAIR (``placedDate``), non l'ora di questo
    # processo: e' il "quando l'ho saputo" che le tre tabelle non hanno mai avuto.
    betfair_updated_at: Optional[str] = None


@dataclass(frozen=True)
class CancelResult:
    """Esito di ``cancel_order_live``, riletto da Betfair.

    ``ok`` = Betfair ha CONFERMATO l'annullamento (``status='SUCCESS'`` sul
    report e sull'istruzione). ``riletto`` = lo stato dell'ordine dopo
    l'annullamento e' stato davvero riletto: se e' False l'abbinato
    nell'intervallo fra la decisione e l'annullamento resta IGNOTO e il
    chiamante deve andare in riconciliazione, mai dichiarare la riga annullata.
    """

    ok: bool
    status: Optional[str]
    bet_id: Optional[str]
    size_cancelled: float
    error_code: Optional[str] = None
    riletto: bool = False
    size_matched: Optional[float] = None
    avg_price_matched: Optional[float] = None
    size_remaining: Optional[float] = None
    # istante dichiarato da Betfair sull'ordine riletto (matchedDate, o in sua
    # assenza placedDate): il "quando l'ho saputo" che accompagna l'abbinato.
    betfair_updated_at: Optional[str] = None
    raw: dict = field(default_factory=dict)


def place_order_live(
    *, market_id: str, selection_id: int, price: float, size: float, event_id: str,
    side: str = "lay", customer_ref: Optional[str] = None,
    fill_or_kill: bool = True,
) -> PlaceResult:
    """Piazza un ordine REALE (lay/back). customerRef deterministico = de-dup Betfair (I1).

    Certificazione 12/09 (money-critical): prezzo e size sono VALIDATI PRIMA di
    qualunque chiamata di rete. ``round(float(nan), 2)`` è NaN e finiva dritto
    nel ``limitOrder.size``; una size 0/negativa sarebbe un ordine senza senso.
    Si solleva ``ValueError`` senza aver contattato Betfair: nessun ordine reale
    esiste, la riga resta in riconciliazione e si libera dopo il grace.
    """
    side_bf = "BACK" if str(side).lower() == "back" else "LAY"
    try:
        size_f = float(size)
    except (TypeError, ValueError):
        raise ValueError(f"size non numerica: {size!r}") from None
    if not math.isfinite(size_f) or round(size_f, 2) <= 0:
        raise ValueError(f"size non valida per un ordine reale: {size!r}")
    price_tick = E.round_to_tick(float(price))   # solleva su prezzo non finito
    if not (E.MIN_PRICE <= price_tick <= E.MAX_PRICE):
        raise ValueError(f"prezzo fuori scala Betfair: {price!r}")
    customer_ref = (customer_ref or f"omega-{event_id}")[:32]
    instruction = {
        "selectionId": int(selection_id),
        "handicap": 0,
        "side": side_bf,
        "orderType": "LIMIT",
        # customerOrderRef è PERSISTITO sull'ordine e RITORNA in listCurrentOrders/
        # listClearedOrders → è la chiave forte per la riconciliazione (I3).
        "customerOrderRef": customer_ref,
        "limitOrder": {
            "size": round(size_f, 2),
            "price": price_tick,
            "persistenceType": "LAPSE",
            # FILL_OR_KILL = "immediato o annullato": la parte NON matchata subito
            # viene cancellata da Betfair. Senza, un fill parziale lascerebbe un
            # residuo VIVO sul book che, matchando più tardi, sfuggirebbe alla
            # contabilità (la riga è già 'open' con la size congelata → I8 violato).
            # 14/09 — ``fill_or_kill=False`` toglie questa riga e l'ordine RESTA
            # SUL BOOK alla quota chiesta, che e' cio' che la strategia di Mike
            # ha sempre voluto per l'uscita appoggiata (si entra pagando lo
            # spread, si esce facendoselo pagare). Chi lo usa DEVE seguirlo: ha
            # il bet_id e lo riconcilia, altrimenti un ordine vivo che nessuno
            # contabilizza diventa una posizione doppia con soldi veri.
            **({"timeInForce": "FILL_OR_KILL"} if fill_or_kill else {}),
        },
    }
    report = call_mutating(
        lambda c: c.place_orders(
            market_id,
            [instruction],
            customer_ref=customer_ref,
            customer_strategy_ref=CUSTOMER_STRATEGY_REF,
        )
    ) or {}
    reports = report.get("instructionReports") or []
    ir = reports[0] if reports else {}
    # seconda passata F1: 'TIMEOUT' (o nessun report) = esito IGNOTO per la doc
    # Betfair — l'ordine può essere vivo. NON è un rifiuto: si solleva, così la
    # riserva resta 'pending' e la riconciliazione decide contro Betfair.
    if not report or report.get("status") == "TIMEOUT" or ir.get("status") == "TIMEOUT":
        raise RuntimeError(f"placeOrders esito IGNOTO ({report.get('status') if report else 'no_report'}) "
                           f"ref={customer_ref}")
    order_status = ir.get("orderStatus")
    ok = report.get("status") == "SUCCESS" and ir.get("status") == "SUCCESS"
    chiesto = round(size_f, 2)
    abbinato = float(ir.get("sizeMatched") or 0.0)
    return PlaceResult(
        ok=bool(ok),
        order_status=order_status,
        bet_id=ir.get("betId"),
        size_matched=abbinato,
        avg_price_matched=ir.get("averagePriceMatched"),
        raw=report if isinstance(report, dict) else {},
        # C.12a — la size CHIESTA non si perde piu': era l'unico numero che il
        # chiamante non poteva piu' recuperare dopo la conferma (``size`` viene
        # sovrascritta con l'abbinato).
        size_requested=chiesto,
        price_requested=price_tick,
        # con FOK Betfair uccide il non abbinato: residuo 0 per definizione.
        # Senza FOK l'ordine resta sul book: residuo = chiesto - abbinato.
        size_remaining=(0.0 if fill_or_kill else round(max(0.0, chiesto - abbinato), 2)),
        # ``errorCode`` sta sull'istruzione (o sul report): finora era sepolto in
        # ``raw`` e nessuno lo leggeva, quindi INSUFFICIENT_FUNDS e
        # INVALID_PROFIT_RATIO erano indistinguibili da un ``ok=False`` generico.
        error_code=ir.get("errorCode") or report.get("errorCode"),
        betfair_updated_at=ir.get("placedDate"),
    )


# ---------------------------------------------------------------------------
# PLACE-AND-TRIM su REST: QUALSIASI importo, anche 0,05 EUR
# ---------------------------------------------------------------------------
# Betfair rifiuta un place DIRETTO sotto il minimo di giurisdizione (.it BACK
# 2,00 / LAY 0,50), ma NON rifiuta un ordine gia' esistente RIDOTTO sotto quella
# soglia. E' la tecnica che usano Bet Angel, Fairbot e Betting Toolkit:
#
#   1. placeOrders   del MINIMO a una quota NON abbinabile (BACK 1000 / LAY 1.01),
#                    persistenza LAPSE e SENZA fill-or-kill (deve restare a riposo);
#   2. cancelOrders  con ``sizeReduction`` = minimo - importo voluto: resta a
#                    mercato esattamente l'importo voluto, sotto il minimo;
#   3. replaceOrders alla quota reale.
#
# La stessa sequenza esiste gia' come macchina a stati asincrona in
# ``Betfair/stream/trading/submin.py`` per il runner flumine. Questa e' la
# versione REST, sincrona, che non dipende da nessun runner acceso.
#
# GUARDIE money-critical, identiche a quelle della macchina:
#   * se lo step 1 si ABBINA (non deve: la quota non e' abbinabile) -> si ritira
#     tutto e si solleva. Nessun ritento automatico: siamo entrati a mercato in
#     modo non previsto e va guardato a mano.
#   * il passaggio allo step 3 avviene SOLO se Betfair CONFERMA il taglio
#     (``sizeCancelled`` == la riduzione chiesta). Senza questa verifica un
#     replace porterebbe la size PIENA del parcheggio alla quota reale.
#   * qualunque fallimento dopo lo step 1 ritira il residuo prima di propagare:
#     mai un ordine a riposo non tracciato sul conto.

SUBMIN_PARK_PRICE_BACK = 1000.0
SUBMIN_PARK_PRICE_LAY = 1.01
SUBMIN_MIN_BACK = 2.00      # .it
SUBMIN_MIN_LAY = 0.50       # .it
SUBMIN_ABS_MIN = 0.01       # floor assoluto del residuo dopo il taglio


def _submin_cancel(market_id: str, bet_id: str, size_reduction: Optional[float]) -> dict:
    """cancelOrders: parziale con ``size_reduction``, totale con None."""
    instr: dict = {"betId": str(bet_id)}
    if size_reduction is not None:
        instr["sizeReduction"] = round(float(size_reduction), 2)
    return call_mutating(
        lambda c: c.betting_rpc(
            method="SportsAPING/v1.0/cancelOrders",
            params={"marketId": str(market_id), "instructions": [instr]},
        )
    ) or {}


def _submin_ritira(market_id: str, bet_id: Optional[str], obbligatorio: bool = False) -> bool:
    """Ritira il residuo di un ordine. Ritorna True se il ritiro e' RIUSCITO.

    C.12a — il valore di ritorno non c'era e serviva: chi propaga un errore deve
    poter dire se l'ordine e' certamente morto (ritiro riuscito -> rifiuto
    CERTO, riga 'error') oppure se potrebbe essere ancora vivo (ritiro fallito
    -> esito IGNOTO, riconciliazione). Prima i due casi erano indistinguibili e
    finivano entrambi in 'pending'.

    ``obbligatorio=False`` (default): best-effort. Si usa quando si sta gia'
    propagando un errore — il chiamante fallira' comunque e la gamba finira' in
    riconciliazione, quindi un ritiro fallito in piu' non cambia l'esito.

    ``obbligatorio=True``: un fallimento SOLLEVA. Si usa nel fill-or-kill, dove
    il riprezzo e' RIUSCITO e senza ritiro l'ordine resta vivo su Betfair a un
    prezzo REALE. Li' un "non ci sono riuscito" silenzioso vorrebbe dire
    dichiarare annullato un ordine che si abbinera' piu' tardi, e che nessuno
    contabilizzera': posizione doppia con soldi veri (code review 13/09).
    """
    if not bet_id:
        return True
    try:
        _submin_cancel(market_id, bet_id, None)
        return True
    except Exception as ex:  # noqa: BLE001
        logger.critical("[submin] RITIRO FALLITO bet %s su %s: %s — controllare a mano",
                        bet_id, market_id, str(ex)[:160])
        if obbligatorio:
            raise RuntimeError(
                "place-and-trim: riprezzo riuscito ma ritiro del residuo FALLITO "
                "(bet %s su %s): l'ordine puo' essere ancora VIVO, si riconcilia. %s"
                % (bet_id, market_id, str(ex)[:120])) from ex
        return False


def place_submin_live(
    *, market_id: str, selection_id: int, price: float, size: float, event_id: str,
    side: str = "back", customer_ref: Optional[str] = None,
    fill_or_kill: bool = True,
) -> PlaceResult:
    """Piazza un importo SOTTO il minimo di Betfair col place-and-trim (REST).

    ``fill_or_kill`` (default, ed e' il comportamento che serve a Mike): finito
    il riprezzo, la parte NON abbinata viene ritirata subito. Cosi' questa
    funzione si comporta esattamente come il place normale — o si abbina, o non
    esiste — e non lascia mai sul conto un ordine che il bot non sa di avere.

    CERT. 13/09, difetto C-1. Senza questo ritiro il riprezzo lascia un ordine
    LIMITE a riposo alla quota richiesta; il chiamante legge "size_matched = 0",
    lo interpreta come un rifiuto e marca la gamba annullata. L'ordine pero' e'
    VIVO su Betfair: piu' tardi si abbina, nessuno lo contabilizza, e l'engine
    nel frattempo rientra — posizione doppia con soldi veri. Con gli importi
    esatti (default) quasi ogni copertura passa da questa strada.

    Con ``fill_or_kill=False`` l'ordine resta a riposo: usarlo SOLO da un
    chiamante che sa seguirlo (ha il bet_id e lo riconcilia).
    """
    side_l = str(side).lower()
    if side_l not in ("back", "lay"):
        raise ValueError(f"side non valido: {side!r}")
    try:
        target = round(float(size), 2)
    except (TypeError, ValueError):
        raise ValueError(f"size non numerica: {size!r}") from None
    if not math.isfinite(target) or target < SUBMIN_ABS_MIN:
        raise ValueError(f"size non piazzabile nemmeno col place-and-trim: {size!r} "
                         f"(minimo assoluto {SUBMIN_ABS_MIN:.2f})")
    minimo = SUBMIN_MIN_BACK if side_l == "back" else SUBMIN_MIN_LAY
    if target >= minimo - 1e-9:
        # non serve nessun trucco: e' un ordine normale
        return place_order_live(market_id=market_id, selection_id=selection_id, price=price,
                                size=target, event_id=event_id, side=side_l,
                                customer_ref=customer_ref)
    target_tick = E.round_to_tick(float(price))
    if not (E.MIN_PRICE <= target_tick <= E.MAX_PRICE):
        raise ValueError(f"prezzo fuori scala Betfair: {price!r}")
    riduzione = round(minimo - target, 2)
    if riduzione < 0.01:
        raise ValueError(f"riduzione nulla: minimo {minimo} target {target}")
    parcheggio = SUBMIN_PARK_PRICE_BACK if side_l == "back" else SUBMIN_PARK_PRICE_LAY
    ref = (customer_ref or f"submin-{event_id}")[:32]

    # -- step 1: parcheggio del minimo a quota non abbinabile --------------------
    report = call_mutating(
        lambda c: c.place_orders(
            str(market_id),
            [{
                "selectionId": int(selection_id), "handicap": 0,
                "side": "BACK" if side_l == "back" else "LAY",
                "orderType": "LIMIT", "customerOrderRef": ref,
                # NIENTE timeInForce: l'ordine DEVE restare a riposo per poter
                # essere tagliato. Un fill-or-kill lo ucciderebbe subito.
                "limitOrder": {"size": round(minimo, 2), "price": parcheggio,
                               "persistenceType": "LAPSE"},
            }],
            customer_ref=ref,
            customer_strategy_ref=CUSTOMER_STRATEGY_REF,
        )
    ) or {}
    reports = report.get("instructionReports") or []
    ir = reports[0] if reports else {}
    if not report or report.get("status") == "TIMEOUT" or ir.get("status") == "TIMEOUT":
        raise RuntimeError(f"place-and-trim: esito IGNOTO al parcheggio ref={ref}")
    if report.get("status") != "SUCCESS" or ir.get("status") != "SUCCESS":
        # RIFIUTO CERTO: il parcheggio e' il PRIMO passo, nessun ordine e' stato
        # creato. Prima era una RuntimeError come tutte le altre e il chiamante
        # lasciava la riga 'pending' IN VERIFICA su un ordine inesistente.
        codice = ir.get("errorCode") or report.get("errorCode")
        raise PlaceRifiutato(f"place-and-trim: parcheggio rifiutato ({codice})",
                             error_code=str(codice) if codice else None,
                             order_status=ir.get("orderStatus"))
    bet_id = ir.get("betId")
    if not bet_id:
        raise RuntimeError("place-and-trim: parcheggio senza betId")
    abbinato_al_parcheggio = float(ir.get("sizeMatched") or 0.0)
    if abbinato_al_parcheggio > 0:
        # non deve succedere: a 1000 / 1.01 non c'e' controparte. Se succede
        # siamo entrati a mercato in modo NON previsto: stop, niente ritento.
        _submin_ritira(market_id, bet_id)
        raise RuntimeError(f"place-and-trim ABORT: il parcheggio si e' abbinato "
                           f"({abbinato_al_parcheggio:.2f} EUR a {parcheggio}) — "
                           f"riconciliare a mano, bet {bet_id}")

    # -- step 2: taglio fino all'importo voluto ----------------------------------
    try:
        canc = _submin_cancel(market_id, bet_id, riduzione)
    except Exception:
        _submin_ritira(market_id, bet_id)
        raise
    creps = canc.get("instructionReports") or []
    cir = creps[0] if creps else {}
    tagliato = float(cir.get("sizeCancelled") or 0.0)
    if canc.get("status") != "SUCCESS" or cir.get("status") != "SUCCESS" or \
            abs(tagliato - riduzione) > 0.005:
        # money-critical: senza il taglio CONFERMATO da Betfair non si riprezza,
        # altrimenti la size piena del parcheggio finirebbe alla quota reale
        ritirato = _submin_ritira(market_id, bet_id)
        codice = cir.get("errorCode") or canc.get("errorCode")
        msg = (f"place-and-trim: taglio non confermato "
               f"(chiesti {riduzione:.2f}, tagliati {tagliato:.2f})")
        if ritirato:
            # il parcheggio e' stato ritirato: nessun ordine vivo, rifiuto CERTO.
            raise PlaceRifiutato(msg + " — ritirato",
                                 error_code=str(codice) if codice else "TRIM_NON_CONFERMATO")
        # ritiro fallito: l'ordine di parcheggio PUO' essere ancora vivo (a una
        # quota non abbinabile, ma vivo) -> esito IGNOTO, si riconcilia.
        raise RuntimeError(msg + " — RITIRO FALLITO, ordine forse vivo")

    # -- step 3: riprezzo alla quota reale ---------------------------------------
    try:
        rep = call_mutating(
            lambda c: c.betting_rpc(
                method="SportsAPING/v1.0/replaceOrders",
                params={"marketId": str(market_id),
                        "instructions": [{"betId": str(bet_id), "newPrice": target_tick}]},
            )
        ) or {}
    except Exception:
        _submin_ritira(market_id, bet_id)
        raise
    rreps = rep.get("instructionReports") or []
    rir = rreps[0] if rreps else {}
    if rep.get("status") != "SUCCESS" or rir.get("status") != "SUCCESS":
        ritirato = _submin_ritira(market_id, bet_id)
        codice = rir.get("errorCode") or rep.get("errorCode")
        msg = f"place-and-trim: riprezzo rifiutato ({codice})"
        if ritirato:
            # e' il caso reale di INVALID_PROFIT_RATIO sul riprezzo: l'ordine
            # non esiste piu', la riga si chiude in 'error' COL CODICE.
            raise PlaceRifiutato(msg + " — ritirato",
                                 error_code=str(codice) if codice else None)
        raise RuntimeError(msg + " — RITIRO FALLITO, ordine forse vivo")
    pir = rir.get("placeInstructionReport") or {}
    nuovo_bet = pir.get("betId") or bet_id
    matched = round(float(pir.get("sizeMatched") or 0.0), 2)

    # C-1: la parte non abbinata NON resta sul book. O si abbina, o non esiste.
    if fill_or_kill and matched < target - 0.005:
        # OBBLIGATORIO: qui il riprezzo e' andato a buon fine, quindi senza
        # ritiro resta un ordine vivo a un prezzo reale. Se il ritiro fallisce
        # si solleva, la gamba va in riconciliazione e l'ordine viene cercato
        # su Betfair invece di essere dato per annullato.
        _submin_ritira(market_id, nuovo_bet, obbligatorio=True)
        if matched <= 0:
            logger.info("[submin] %s %s %.2f EUR @ %.2f: nessuna controparte, ritirato",
                        side_l, selection_id, target, target_tick)
            return PlaceResult(ok=False, order_status="LAPSED", bet_id=nuovo_bet,
                               size_matched=0.0, avg_price_matched=None,
                               raw=rep if isinstance(rep, dict) else {},
                               size_requested=target, price_requested=target_tick,
                               size_remaining=0.0, size_cancelled=target,
                               error_code=None,
                               betfair_updated_at=pir.get("placedDate"))
        logger.info("[submin] %s %s abbinati %.2f di %.2f EUR @ %.2f, residuo ritirato",
                    side_l, selection_id, matched, target, target_tick)

    logger.info("[submin] %s %s %.2f EUR @ %.2f su %s (bet %s) — place-and-trim completato",
                side_l, selection_id, matched or target, target_tick, market_id, nuovo_bet)
    return PlaceResult(
        ok=True,
        order_status=pir.get("orderStatus") or "EXECUTION_COMPLETE",
        bet_id=nuovo_bet,
        size_matched=matched,
        avg_price_matched=pir.get("averagePriceMatched") or (target_tick if matched > 0 else None),
        raw=rep if isinstance(rep, dict) else {},
        # C.12a — il place-and-trim e' l'UNICO percorso live dove un parziale con
        # ``ok=True`` e' normale (``_submin_ritira`` toglie il residuo): chiesto,
        # abbinato e ritirato devono arrivare al chiamante, altrimenti "abbinati
        # 0,80 dei 2,00 chiesti" resta scritto solo nel log.
        size_requested=target,
        price_requested=target_tick,
        size_remaining=(0.0 if fill_or_kill else round(max(0.0, target - matched), 2)),
        size_cancelled=(round(max(0.0, target - matched), 2) if fill_or_kill else None),
        error_code=None,
        betfair_updated_at=pir.get("placedDate"),
    )

def cancel_order_live(bet_id: str, market_id: str,
                      size_reduction: Optional[float] = None) -> CancelResult:
    """ANNULLA DAVVERO un ordine su Betfair (``cancelOrders``), e rilegge l'esito.

    ⚠️ C.12a — QUESTA FUNZIONE NON ESISTEVA, ed e' il reperto numero 1 della
    matrice della consapevolezza (16/09). Nessuno dei tre bot che passano dal
    REST (Omega, Safe, Mike) sapeva annullare un ordine: i loro «annulla» erano
    CONTABILI — cambiavano lo stato della riga nel database e basta. Lo scenario
    che ne usciva, con soldi veri: una lay da 5 EUR @2,14 appoggiata, il bot
    decide «annulla» e scrive ``cancelled``, su Betfair l'ordine e' VIVO e
    quattro minuti dopo si abbina. Nessuno lo contabilizza, il motore nel
    frattempo rientra: posizione doppia.

    ``size_reduction=None`` annulla TUTTO il residuo; un valore annulla solo
    quella parte (annullo parziale, come ``market.cancel_order(size_reduction=)``
    dei bot dentro flumine).

    L'esito si RILEGGE, non si suppone: Betfair conferma con ``sizeCancelled``
    (``CancelOrderInstructionReports``,
    ``betfairlightweight/resources/bettingresources.py:1049-1071``) e subito
    dopo si chiede lo stato dell'ordine (``order_state_by_bet_id``) perche' fra
    la decisione del bot e l'arrivo dell'annullamento l'ordine PUO' essersi
    abbinato, in tutto o in parte: quella parte e' una posizione reale e non va
    mai dimenticata. Se la rilettura fallisce, ``riletto=False``: il chiamante
    deve andare in riconciliazione, non dichiarare la riga annullata.

    NON solleva su rifiuto (``ok=False`` col ``error_code``, p.es.
    ``BET_TAKEN_OR_LAPSED`` quando l'ordine e' gia' stato preso): solleva solo
    se la rete cade — li' l'esito e' IGNOTO e il chiamante non deve decidere.
    """
    bid = str(bet_id)
    if not bid:
        raise ValueError("cancel_order_live senza bet_id")
    instr: dict = {"betId": bid}
    if size_reduction is not None:
        try:
            rid = round(float(size_reduction), 2)
        except (TypeError, ValueError):
            raise ValueError(f"size_reduction non numerica: {size_reduction!r}") from None
        if not math.isfinite(rid) or rid <= 0:
            raise ValueError(f"size_reduction non valida: {size_reduction!r}")
        instr["sizeReduction"] = rid
    # MAI ritentata su errore generico (``call_mutating``): un annullamento
    # ritentato al buio non fa danni quanto un place, ma un timeout puo'
    # nascondere un annullamento gia' avvenuto e il conteggio di sizeCancelled
    # tornerebbe sbagliato.
    report = call_mutating(
        lambda c: c.betting_rpc(
            method="SportsAPING/v1.0/cancelOrders",
            params={"marketId": str(market_id), "instructions": [instr]},
        )
    ) or {}
    reports = report.get("instructionReports") or []
    cir = reports[0] if reports else {}
    stato = report.get("status")
    if not report or stato == "TIMEOUT" or cir.get("status") == "TIMEOUT":
        # esito IGNOTO: l'ordine puo' essere annullato o no. Si solleva, come fa
        # ``place_order_live``: chi chiama va in riconciliazione.
        raise RuntimeError(f"cancelOrders esito IGNOTO ({stato or 'no_report'}) bet={bid}")
    ok = stato == "SUCCESS" and cir.get("status") == "SUCCESS"
    codice = cir.get("errorCode") or report.get("errorCode")
    tagliato = float(cir.get("sizeCancelled") or 0.0)
    # rilettura: quanto si e' abbinato nel frattempo?
    riletto, matched, medio, residuo = False, None, None, None
    quando: Optional[str] = None
    try:
        stato_ordine = order_state_by_bet_id(bid)
        riletto = True
        if stato_ordine.get("found"):
            matched = float(stato_ordine.get("size_matched") or 0.0)
            medio = stato_ordine.get("avg_price_matched")
            residuo = float(stato_ordine.get("size_remaining") or 0.0)
            quando = stato_ordine.get("matched_date") or stato_ordine.get("placed_date")
        else:
            # Betfair non lo conosce in nessuna lista: mai abbinato.
            matched, medio, residuo = 0.0, None, 0.0
    except Exception as ex:  # noqa: BLE001 — rete KO: l'abbinato resta IGNOTO
        logger.warning("[omega] cancel bet %s: rilettura KO (%s) — esito abbinamento IGNOTO",
                       bid, str(ex)[:120])
    if not ok:
        logger.warning("[omega] cancelOrders NON confermato bet=%s codice=%s", bid, codice)
    return CancelResult(
        ok=bool(ok), status=cir.get("status") or stato, bet_id=bid,
        size_cancelled=tagliato, error_code=str(codice) if codice else None,
        riletto=riletto, size_matched=matched, avg_price_matched=medio,
        size_remaining=residuo, betfair_updated_at=quando,
        raw=report if isinstance(report, dict) else {},
    )


def place_lay_live(
    *, market_id: str, selection_id: int, price: float, size: float, event_id: str,
    customer_ref: Optional[str] = None,
) -> PlaceResult:
    """Wrapper storico: LAY reale (usato dal loop automatico). ``customer_ref``
    PER GAMBA (omega-t<id>, §16): con due gambe per partita il ref per evento
    faceva rifiutare il secondo ordine (DUPLICATE_CUSTOMER_ORDER_REF)."""
    return place_order_live(
        market_id=market_id, selection_id=selection_id, price=price,
        size=size, event_id=event_id, side="lay", customer_ref=customer_ref,
    )


# ---------------------------------------------------------------------------
# RICONCILIAZIONE: stato reale degli ordini Omega su Betfair
# ---------------------------------------------------------------------------
def order_state_by_bet_id(bet_id: str) -> dict:
    """Stato REALE di UN ordine per betId (riconciliazione del percorso LIVE via
    flumine, §6-bis: l'ordine piazzato dal runner NON porta né il customerOrderRef
    ``omega-*`` né la strategy 'omega' — l'unica chiave certa è il betId).

    Ritorna ``{"found": True, "size_matched", "avg_price_matched",
    "size_remaining", "matched_date", "placed_date"}`` oppure
    ``{"found": False}`` se Betfair non lo conosce in nessuna lista. SOLLEVA su
    errori di rete (il chiamante NON deve mai decidere al buio su soldi veri:
    riprova al ciclo dopo).

    C.12a — ``matched_date``/``placed_date`` in snake_case, come li produce
    ``list_current_orders``. Servono perche' questa e' la SOLA strada quando
    l'ordine non compare nella lista del giro (riconciliazione per bet_id del
    percorso flumine): senza, ``betfair_updated_at`` resterebbe vuoto proprio
    nei casi in cui il trader ha piu' bisogno di sapere DA QUANDO quel numero
    e' fermo. Nomi grezzi: ``matchedDate``/``placedDate`` su ``CurrentOrder``
    (``betfairlightweight/resources/bettingresources.py:664-711``),
    ``lastMatchedDate``/``placedDate``/``settledDate`` su ``ClearedOrder``
    (``:790-840``).
    """
    bid = str(bet_id)
    resp = call(lambda c: c.betting_rpc(
        "SportsAPING/v1.0/listCurrentOrders",
        {"betIds": [bid], "orderProjection": "ALL",
         "fromRecord": 0, "recordCount": 100},
    )) or {}
    for o in resp.get("currentOrders", []) or []:
        if str(o.get("betId")) == bid:
            return {
                "found": True,
                "size_matched": float(o.get("sizeMatched") or 0.0),
                "avg_price_matched": o.get("averagePriceMatched"),
                "size_remaining": float(o.get("sizeRemaining") or 0.0),
                "matched_date": o.get("matchedDate"),
                "placed_date": o.get("placedDate"),
            }
    # SETTLED prima (porta i € matchati); poi gli stati "senza fill": un FOK
    # ucciso finisce in CANCELLED/LAPSED con sizeSettled=0.
    for status in ("SETTLED", "VOIDED", "LAPSED", "CANCELLED"):
        resp = call(lambda c, s=status: c.betting_rpc(
            "SportsAPING/v1.0/listClearedOrders",
            {"betStatus": s, "betIds": [bid], "fromRecord": 0, "recordCount": 100},
        )) or {}
        for o in resp.get("clearedOrders", []) or []:
            if str(o.get("betId")) == bid:
                return {
                    "found": True,
                    "size_matched": float(o.get("sizeSettled") or 0.0),
                    "avg_price_matched": o.get("priceMatched"),
                    "size_remaining": 0.0,
                    # su un ordine REGOLATO l'ultimo abbinamento si chiama
                    # ``lastMatchedDate``: stessa cosa, nome diverso.
                    "matched_date": o.get("lastMatchedDate"),
                    "placed_date": o.get("placedDate"),
                    "settled_date": o.get("settledDate"),
                }
    return {"found": False}


def _riga_corrente(o: dict) -> dict:
    """UN ordine corrente, normalizzato. Estratta il 16/09 sera perche' la
    stessa normalizzazione serve anche alla POSIZIONE DI CONTO
    (``list_current_orders_account``): due copie della stessa lettura sono il
    difetto 1 del catalogo in attesa di succedere."""
    sid = o.get("selectionId")
    return {
        "bet_id": o.get("betId"),
        "market_id": str(o["marketId"]) if o.get("marketId") else None,
        "selection_id": int(sid) if sid is not None else None,
        "side": str(o.get("side", "")).lower(),
        "status": o.get("status"),
        "size_matched": float(o.get("sizeMatched") or 0.0),
        "avg_price_matched": o.get("averagePriceMatched"),
        "size_remaining": float(o.get("sizeRemaining") or 0.0),
        "customer_order_ref": o.get("customerOrderRef"),
        # --- C.12a: il resto di cio' che Betfair dice gia' ----------------
        # ``CurrentOrder`` porta questi campi da sempre
        # (``betfairlightweight/resources/bettingresources.py:664-711``) e
        # noi ne buttavamo via meta': senza ``sizeCancelled/Lapsed/Voided``
        # un ordine morto per LAPSE e uno annullato dal bot sono
        # indistinguibili, e senza ``matchedDate`` nessuno sa se "abbinato
        # 5,00" e' di due secondi o di nove minuti fa.
        # Le chiavi di sopra NON cambiano (le legge ``_order_matches`` e
        # tutta la riconciliazione): queste si aggiungono.
        "size_cancelled": float(o.get("sizeCancelled") or 0.0),
        "size_lapsed": float(o.get("sizeLapsed") or 0.0),
        "size_voided": float(o.get("sizeVoided") or 0.0),
        "matched_date": o.get("matchedDate"),
        "placed_date": o.get("placedDate"),
        "price_requested": (o.get("priceSize") or {}).get("price"),
        "size_requested": (o.get("priceSize") or {}).get("size"),
        # stessa cosa di ``avg_price_matched``, con la grafia per esteso di
        # Betfair: un consumatore che cerca l'una o l'altra trova sempre.
        # (15/09: una grafia scritta in un modo e letta in un altro e' costata
        # 32 ordini reali — qui si accettano entrambe per costruzione.)
        "average_price_matched": o.get("averagePriceMatched"),
    }


def list_current_orders(strategy_ref: str = CUSTOMER_STRATEGY_REF) -> list[dict]:
    """Ordini APERTI/matchati DELLA STRATEGIA (normalizzati) per la riconciliazione."""
    resp = call(lambda c: c.list_current_orders(customer_strategy_refs=[strategy_ref])) or {}
    return [_riga_corrente(o) for o in (resp.get("currentOrders", []) or [])]


def list_current_orders_account(market_ids: list, selection_ids: Optional[list] = None) -> list[dict]:
    """LA POSIZIONE DI CONTO, meta' viva: ordini VIVI su questi mercati di
    CHIUNQUE — **senza** filtro di strategia.

    ⚠️ ORDINE DELL'UTENTE, 16/09 sera: «se chiudo io il bot deve saperlo, anche
    fuori dall'app». Un bot che legge solo i propri ordini
    (``customerStrategyRef``) non vede la lay che l'utente ha piazzato dal sito
    Betfair per chiudere la posizione: continua a vedere il proprio back
    abbinato e a gestirlo. La posizione VERA e' quella del CONTO sul mercato, e
    la si ottiene chiedendo ``listCurrentOrders`` con i soli ``marketIds``
    (``betfairlightweight.endpoints.betting.list_current_orders``: i parametri
    sono indipendenti, ``customer_strategy_refs`` si puo' semplicemente
    omettere). ``selection_ids`` non esiste come filtro dell'API: si filtra qui.

    E' una chiamata REST IN PIU': chi la usa la fa alla cadenza del respiro del
    database, mai a ogni giro (§17 della Costituzione di Mike).
    """
    resp = call(lambda c: c.list_current_orders(market_ids=list(market_ids))) or {}
    volute = {int(x) for x in (selection_ids or [])}
    out = [_riga_corrente(o) for o in (resp.get("currentOrders", []) or [])]
    if volute:
        out = [r for r in out if r.get("selection_id") in volute]
    return out


def _riga_regolata(o: dict) -> dict:
    """UN ordine regolato, normalizzato (vedi ``_riga_corrente``).

    ``size_matched`` c'e' ANCHE con la grafia dei correnti: chi somma una
    posizione di conto legge le due liste insieme e non deve conoscere due
    nomi per la stessa cosa (difetto 1 del catalogo del 15/09)."""
    sid = o.get("selectionId")
    regolato = float(o.get("sizeSettled") or 0.0)
    return {
        "bet_id": o.get("betId"),
        "market_id": str(o["marketId"]) if o.get("marketId") else None,
        "selection_id": int(sid) if sid is not None else None,
        "side": str(o.get("side", "")).lower(),
        "size_settled": regolato,
        "size_matched": regolato,
        "size_remaining": 0.0,
        "price": o.get("priceMatched") or o.get("priceRequested"),
        "avg_price_matched": o.get("priceMatched"),
        "profit": float(o.get("profit") or 0.0),
        # I3 (17/09) — Betfair applica gia' la commissione sul ``profit``: non
        # serve a ricalcolare nulla, serve a DICHIARARE nel meta con che
        # numero Betfair ha regolato, per il trader ("dati reali").
        "commission": o.get("commission"),
        "bet_outcome": o.get("betOutcome"),
        "customer_order_ref": o.get("customerOrderRef"),
    }


def list_cleared_orders(
    strategy_ref: str = CUSTOMER_STRATEGY_REF,
    market_ids: Optional[list] = None,
    lookback_hours: int = 72,
) -> list[dict]:
    """Ordini REGOLATI DELLA STRATEGIA (normalizzati). Finestra temporale
    (default 72h) + stati SETTLED **e** VOIDED (un ordine parzialmente matchato
    su un mercato annullato non è SETTLED): così un ordine reale non sfugge
    alla riconciliazione.
    """
    settled_from = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    out: list[dict] = []
    for status in ("SETTLED", "VOIDED"):
        resp = call(
            lambda c, s=status: c.list_cleared_orders(
                bet_status=s, customer_strategy_refs=[strategy_ref],
                market_ids=market_ids, settled_from=settled_from,
            )
        ) or {}
        out.extend(_riga_regolata(o) for o in (resp.get("clearedOrders", []) or []))
    return out


def list_cleared_orders_account(market_ids: list, lookback_hours: int = 72) -> list[dict]:
    """LA POSIZIONE DI CONTO, meta' regolata: ordini REGOLATI su questi mercati
    di CHIUNQUE — **senza** filtro di strategia (vedi
    ``list_current_orders_account``)."""
    settled_from = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    out: list[dict] = []
    for status in ("SETTLED", "VOIDED"):
        resp = call(
            lambda c, s=status: c.list_cleared_orders(
                bet_status=s, market_ids=list(market_ids), settled_from=settled_from,
            )
        ) or {}
        out.extend(_riga_regolata(o) for o in (resp.get("clearedOrders", []) or []))
    return out


def posizione_di_conto(market_id: str, selection_id: Optional[int] = None) -> list[dict]:
    """LA POSIZIONE DI CONTO su un mercato (e, se dato, su UNA selezione):
    ordini VIVI **piu'** REGOLATI di CHIUNQUE, **senza filtro di strategia**.

    ⚠️ ORDINE DELL'UTENTE, 16/09 sera: «se chiudo io, anche fuori dall'app,
    direttamente su Betfair, il bot deve saperlo e NON gestire posizioni che non
    esistono piu'». Un bot che legge solo i propri ordini
    (``customerStrategyRef``) non vede la back che l'utente ha piazzato dal sito
    per chiudere: continua a vedere la propria lay abbinata e a coprirla — un
    green-up su una posizione che non c'e' piu' e' un back con soldi veri.

    UNA funzione sola, con questo nome e questa firma, condivisa da Omega e
    dalla Safe Strategy (accordo fra delegati del 16/09) e rispecchiata dal
    banco di replay (``Betfair/stream/backtest/banco_comune.py``: stesso nome,
    stessa firma, stesse chiavi — un finto che parla una lingua diversa dal vero
    e' il difetto 27 del catalogo).

    Ritorna le righe normalizzate di ``_riga_corrente`` (vive) e ``_riga_regolata``
    (morte): chiavi comuni ``bet_id, market_id, selection_id, side, size_matched,
    size_remaining, avg_price_matched, customer_order_ref``. Le vive portano in
    piu' ``status`` (EXECUTABLE/…); le regolate ``size_settled``, ``profit``,
    ``bet_outcome``.

    COSTA DUE CHIAMATE REST: chi la usa la fa alla CADENZA DICHIARATA del
    respiro (Omega: ``conto_every_s``, default 120 s), mai a ogni giro.
    SOLLEVA su errore di rete: chi decide su soldi veri non decide al buio.
    """
    sel = [int(selection_id)] if selection_id is not None else None
    righe = list(list_current_orders_account([str(market_id)], sel))
    for r in list_cleared_orders_account([str(market_id)]):
        if sel is not None and r.get("selection_id") not in sel:
            continue
        righe.append(r)
    return righe


def market_profit_and_loss(market_ids: list) -> dict:
    """``listMarketProfitAndLoss``: il P&L che Betfair calcola sul CONTO per
    ogni selezione del mercato, comprese le scommesse dell'utente.

    Torna ``{market_id: {selection_id: ifWin}}``. E' la terza lettura possibile
    della posizione di conto (la piu' sintetica) e serve come CONTROPROVA: la
    posizione la si ricostruisce dagli ordini, questa dice se il conto la vede
    allo stesso modo. ``includeSettledBets`` acceso, ``netOfCommission`` spento
    (il lordo: la commissione la applica gia' il bot con la sua aliquota).
    """
    resp = call(lambda c: c.list_market_profit_and_loss(
        market_ids=list(market_ids), include_settled_bets=True,
        net_of_commission=False)) or []
    out: dict = {}
    for m in resp or []:
        mid = str(m.get("marketId") or "")
        if not mid:
            continue
        per_sel: dict = {}
        for r in m.get("profitAndLosses") or []:
            sid = r.get("selectionId")
            if sid is None:
                continue
            per_sel[int(sid)] = float(r.get("ifWin") or 0.0)
        out[mid] = per_sel
    return out
