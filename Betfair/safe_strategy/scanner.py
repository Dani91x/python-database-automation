"""scanner.py — logica PURA dello scanner Safe Strategy (testabile senza rete).

Qui vivono le decisioni "di testa": mappatura selezioni, finestre di interesse,
cadenze adattive, congelamento del riferimento pre-KO, firma write-on-change.
Il glue di rete/DB sta in service.py; NESSUNA valutazione di strategia qui
(quella è del motore certificato frontend, lib/safeStrategy.ts).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("safe.scanner")

# finestre di interesse (minuti EFFETTIVI di gioco, come certificato).
# REGOLA (utente, 09/09): il minuto delle strategie calcio è una SOGLIA
# ("dal 48' in poi"), NON un intervallo chiuso — il tetto lo mettono i range
# quote. Quindi anche qui le finestre sono aperte verso la fine partita:
# prima del 40' lo scanner rallenta per non sprecare peso API Betfair, dal 40'
# in poi resta "caldo" fino al fischio finale.
HOT_MINUTE_FROM = 40
# candidati Correct Score: dal 30' in poi (Omega entra dal 30', la Safe
# Strategy R.E. dal 48') con al massimo 3 gol per lato (le scoreline esplicite
# del mercato arrivano a 3-3: oltre, resta solo "Any Other" e nessuno lava).
# Nessun tetto di minuto. Il CS dei candidati va sul POOL STREAM come il
# MATCH_ODDS (quote al secondo) e viene pubblicato COMPLETO (tutte le
# selezioni): è il feed unico anche per Omega (audit 09/09 sera).
CS_MINUTE_FROM = 30
CS_MAX_GOALS_SIDE = 3
# HALF TIME SCORE (Omega v2, gamba 1T): sotto quote dal 15' finché il 1T è in corso
HT_MINUTE_FROM = 15
HT_MINUTE_TO = 45

# ---------------------------------------------------------------- OPPORTUNITA'
# Mercati "a gol" tenuti sotto quote per il motore opportunità
# (opportunity.py): Over/Under di tutte le linee quotate da Betfair, Gol/NoGol e
# 1X2 del primo tempo. Servono SOLO in-play (prima del kickoff il modello non ha
# nulla da dire su tempo/punteggio) e SOLO per le linee ancora INDECISE: una
# linea già superata non è un'opportunità, è aritmetica.
OU_MARKET_TYPES = (
    "OVER_UNDER_05", "OVER_UNDER_15", "OVER_UNDER_25", "OVER_UNDER_35",
    "OVER_UNDER_45", "OVER_UNDER_55", "OVER_UNDER_65", "OVER_UNDER_75",
)
BTTS_MARKET_TYPE = "BOTH_TEAMS_TO_SCORE"
HT_RESULT_MARKET_TYPE = "HALF_TIME"          # 1X2 all'intervallo
OPP_MARKET_TYPES = OU_MARKET_TYPES + (BTTS_MARKET_TYPE, HT_RESULT_MARKET_TYPE)
OPP_MINUTE_FROM = 1
# tetto di eventi con i mercati opportunità sotto quote: 10 mercati per evento
# pesano sul pool stream (180/connessione) e sul poll REST di fallback. I posti
# vanno ai minuti più avanzati (dove le probabilità sono davvero estreme).
OPP_MAX_EVENTS = 20

_OU_LINE_RE = re.compile(r"OVER_UNDER_(\d)(\d)$", re.IGNORECASE)
# cattura pre-KO: da KO-15' fino al kickoff
PRE_KO_WINDOW_SEC = 15 * 60
# ------------------------------------------------------- RAMO PRE-KO O/U (Mike)
# Le DUE linee a gol tenute sotto quote PRIMA del calcio d'inizio per il bot Mike
# (Under 3.5 / Over 4.5): stesso ciclo di vita dei mercati opportunità (catalogo
# per i candidati nuovi, quote dal pool stream con priorità tier 2, REST di
# fallback) ma SENZA requisito di minuto/punteggio. Acceso SOLO se
# ``SAFE_PRE_KO_OU_HOURS`` > 0 (service.py): a 0 nulla cambia nel feed.
PRE_KO_OU_MARKET_TYPES = ("OVER_UNDER_35", "OVER_UNDER_45")
# Le stesse due linee viste dal lato MIKE: finché il bot SEGUE la partita
# devono restare nel feed anche in-play e anche quando una delle due è già
# decisa (audit 11/09 C1/C2): senza la 4.5 non c'è copertura né cash out, e la
# 3.5 potata al 4° gol congelava la card.
MIKE_OU_MARKET_TYPES = PRE_KO_OU_MARKET_TYPES
# Tetto DURO delle partite Mike esenti dal taglio dei mercati a gol.
#
# CERTIFICAZIONE 12/09 (osservata sui dati reali) — era 10, allineato a
# ``max_open_matches``, ma le partite con ESPOSIZIONE sono di piu': restano
# aperte anche dopo il cap (in chiusura, in regolamento, con un residuo), e il
# 12/09 ne sono state contate 26 insieme. Le eccedenti restavano SENZA quote in
# gioco: niente copertura Over 4.5, niente cash out, niente uscita. Tre partite
# reali sono finite cosi' a -10,00 ciascuna, con un buco di SETTE ORE fra
# l'ingresso e il regolamento e l'attivita' "linee assenti dal feed".
#
# Il costo di alzarlo e' trascurabile: ogni partita Mike pesa 2 mercati, quindi
# 40 partite = 80 mercati.
# CORREZIONE 13/09: la capacita' VIVA non e' 2000. 2000 (200 x 10 connessioni) e'
# il massimo teorico di Betfair; la configurazione in uso e' 4 connessioni x 180
# mercati = 720 slot (``stream.py``, nessuna variabile d'ambiente che la alzi).
# Il rischio di NON alzare il tetto e' comunque la perdita piena su una
# posizione aperta — ma dal 13/09 il taglio non e' piu' casuale: le partite
# arrivano ordinate per SOLDI A RISCHIO decrescente (``select_opp_candidates``),
# quindi se il tetto morde restano fuori quelle con meno denaro sopra.
# Override: MIKE_MAX_FOLLOWED (env vuota = default, mai `??`).
def _mike_max_followed() -> int:
    import os

    raw = os.environ.get("MIKE_MAX_FOLLOWED", "").strip() or "40"
    try:
        return max(1, int(float(raw)))
    except ValueError:
        return 40


MIKE_MAX_FOLLOWED = _mike_max_followed()


def prioritize_followed(candidates: List[str], followed: Any = ()) -> List[str]:
    """``candidates`` con le partite di ``followed`` DAVANTI, ordine relativo
    invariato per tutto il resto.

    Serve dove la lista viene TRONCATA (lotto del catalogo mercati): chi resta
    fuori aspetta il giro dopo, e aspettare con una posizione APERTA significa
    restare senza quote, quindi senza copertura, senza cash out e senza uscita.
    Caso vivo del 12/09, riavvio delle 21:43: 11 partite di Mike con posizioni
    aperte sono rimaste ~10 minuti senza nessuna linea O/U nel feed, con 46
    allarmi 'feed_line_missing' critici, perche' l'ordine era solo "minuti piu'
    avanzati" e i soldi a rischio non contavano.
    """
    keep = {str(e) for e in (followed or ())}
    if not keep:
        return list(candidates)
    return sorted(candidates, key=lambda e: str(e) not in keep)


def select_opp_candidates(
    candidates: List[str], *, followed: Any = (), max_events: Optional[int] = None,
    max_followed: Optional[int] = None,
) -> List[str]:
    """Eventi che tengono i mercati a gol sotto quote, con il tetto ``max_events``
    (default ``OPP_MAX_EVENTS``) e l'ESENZIONE delle partite seguite da Mike.

    ``candidates`` arriva GIÀ in ordine di priorità (minuti più avanzati prima).
    Le partite in ``followed`` (quelle di Mike CON esposizione) non vengono
    tagliate: sono posizioni APERTE, restare senza quote significa nessuna
    copertura Over 4.5, nessun cash out e nessuna uscita (audit C1). L'esenzione
    è però limitata a ``max_followed`` partite (default ``MIKE_MAX_FOLLOWED``) e
    il tetto normale continua a valere per tutte le altre: il peso sul pool
    stream cresce solo di quanto Mike sta davvero tradando.
    """
    cap = OPP_MAX_EVENTS if max_events is None else int(max_events)
    cap_f = MIKE_MAX_FOLLOWED if max_followed is None else int(max_followed)
    keep_set = {str(e) for e in (followed or ())}
    # CERT. 13/09 — quando il tetto MORDE, l'ordine che conta e' quello di
    # ``followed`` (le partite arrivano gia' ordinate per SOLDI A RISCHIO
    # decrescente, ``db.list_mike_followed_event_ids``), NON quello dei
    # candidati dello scanner. Prima si scorrevano i ``candidates``, ordinati
    # per "minuti piu' avanzati": il tetto tagliava le partite APPENA INIZIATE,
    # cioe' proprio quelle dove la copertura Over 4.5 serve di piu'.
    # Alzare il numero non basterebbe: sposterebbe il problema piu' in la'.
    in_gioco = {str(e) for e in candidates}
    keep = [str(e) for e in (followed or ()) if str(e) in in_gioco][: max(0, cap_f)]
    kept = set(keep)
    if len(keep_set) > len(keep):
        # una partita con SOLDI A RISCHIO tagliata dal tetto resta senza quote:
        # niente copertura, niente uscita. Non si tace: si grida nel log, cosi'
        # il tetto si alza prima che costi una perdita piena.
        logger.warning(
            "[scanner] %d partite seguite da Mike OLTRE il tetto %d: restano senza "
            "quote in gioco (nessuna copertura ne' uscita). Fuori restano quelle con "
            "MENO denaro sopra (ordine per esposizione), ma il tetto va alzato: "
            "MIKE_MAX_FOLLOWED.",
            len(keep_set) - len(keep), cap_f)
    rest = [e for e in candidates if e not in kept]
    return keep + rest[: max(0, cap)]


def in_pre_ko_ou_window(open_date: Optional[str], now: datetime, hours: float) -> bool:
    """KO fra ``now`` e ``now + hours`` (hours <= 0 = ramo spento)."""
    if hours is None or float(hours) <= 0.0:
        return False
    ko = parse_iso(open_date)
    if ko is None:
        return False
    delta = (ko - now).total_seconds()
    return 0 < delta <= float(hours) * 3600.0


def is_pre_ko_ou_candidate(
    inplay: Optional[bool], mo_status: Optional[str], open_date: Optional[str],
    now: datetime, hours: float,
) -> bool:
    """Evento calcio NON ancora iniziato con KO entro ``hours``: le sue linee
    O/U 3.5 e 4.5 vanno sotto quote (ramo pre-KO Mike)."""
    if inplay or mo_status == "CLOSED":
        return False
    return in_pre_ko_ou_window(open_date, now, hours)

_ANY_OTHER_HOME = re.compile(r"any\s*other.*home", re.IGNORECASE)
_ANY_OTHER_AWAY = re.compile(r"any\s*other.*away", re.IGNORECASE)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def livello_campo(levels: Any, campo: str) -> Any:
    """Un campo del MIGLIOR livello del ladder, in ENTRAMBE le forme in cui gira.

    Betfair manda ``{"price": .., "size": ..}``; betfairlightweight lo
    trasforma in un ``PriceSize`` con gli attributi. Ma ``flumine``, appena
    importato, SOSTITUISCE ``RunnerBookEX`` con la sua versione "pigra"
    (``flumine/patching.py``, da ``flumine/__init__.py:13``), che lascia i
    livelli come DIZIONARI.

    IL 17/09/2026 E' SUCCESSO DAVVERO, ed e' la causa del blackout delle quote
    su tutto il feed: ``safe_strategy/service.py`` caricava l'Atlante Hazard da
    ``Betfair.stream.scalper.theta_bot``, quel package importava ``scalper_bot``
    -> ``from flumine import BaseStrategy``, e da quell'istante il processo del
    feed leggeva ``None`` su OGNI prezzo (misurato: un ladder
    ``{'price': 3.2, 'size': 821.19}`` letto come ``None``), da stream e da
    REST, in silenzio, per ore.
    La causa e' stata tolta alla radice (``Betfair/stream/scalper/hazard_atlas.py``,
    modulo puro, + import pigro nel package). Questa e' la difesa in profondita':
    il giorno che qualcuno reintroduce un import di flumine nel processo del
    feed, i prezzi si leggono lo stesso.
    """
    if not levels:
        return None
    top = levels[0]
    if isinstance(top, dict):
        return top.get(campo)
    return getattr(top, campo, None)


def best_price(levels: Any) -> Optional[float]:
    try:
        v = livello_campo(levels, "price")
        return float(v) if v is not None else None
    except Exception:  # noqa: BLE001 - struttura inattesa = prezzo assente
        return None


def best_size(levels: Any) -> Optional[float]:
    """Importo (EUR) disponibile al MIGLIOR prezzo: è quanto si può abbinare
    SUBITO a quella quota (best offers, livello 0)."""
    try:
        v = livello_campo(levels, "size")
        return round(float(v), 2) if v is not None else None
    except Exception:  # noqa: BLE001
        return None


def price_pair(ex: Any) -> Dict[str, Optional[float]]:
    """Coppia back/lay al miglior prezzo con le size abbinabili, da un runner.ex
    (poll REST o stream, stessa forma betfairlightweight)."""
    atb = getattr(ex, "available_to_back", None) if ex else None
    atl = getattr(ex, "available_to_lay", None) if ex else None
    return {
        "back": best_price(atb),
        "lay": best_price(atl),
        "back_size": best_size(atb),
        "lay_size": best_size(atl),
    }


def _pair_con_prezzo(p: Any) -> bool:
    """Una coppia back/lay porta almeno UN prezzo utilizzabile."""
    if isinstance(p, dict):
        return p.get("back") is not None or p.get("lay") is not None
    return False


def has_any_price(sorgente: Any) -> bool:
    """Almeno UN prezzo (back o lay) su almeno UNA selezione.

    Serve a distinguere un aggiornamento di QUOTE da un book di sola
    DEFINIZIONE: betfairlightweight, quando il messaggio porta solo
    ``marketDefinition`` e nessun ``rc``, crea comunque i runner dalla
    definizione (con selection_id e status) e pubblica il MarketBook con le
    scalette VUOTE (streaming/cache.py:314-351 + streaming/stream.py:211-215).
    Applicarlo come se fosse un prezzo cancella le quote buone: e' successo il
    17/09/2026 alle 12:47:04 UTC su TUTTO il feed (tennis, calcio, mercati a
    gol) ed e' sopravvissuto al riavvio delle 13:13 UTC.

    Accetta le tre forme con cui il prezzo gira nel servizio:
      * un MarketBook (oggetto con ``runners``, stream o REST);
      * il dizionario ``{selection_id: pair}`` di ``_apply_market_book``;
      * la lista di selezioni gia' costruita (``_apply_cs_book``/``_apply_opp_book``).
    """
    if sorgente is None:
        return False
    runners = getattr(sorgente, "runners", None)
    if runners is not None and not isinstance(sorgente, (dict, list, tuple)):
        for r in runners or []:
            if _pair_con_prezzo(price_pair(getattr(r, "ex", None))):
                return True
        return False
    valori = sorgente.values() if isinstance(sorgente, dict) else sorgente
    try:
        iteratore = iter(valori)
    except TypeError:
        return False
    return any(_pair_con_prezzo(v) for v in iteratore)


def selection_sides(runners: List[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    """Mappa home/away/draw → selection_id dal catalogo MATCH_ODDS calcio.

    Regola Betfair: sort_priority 1 = casa, 2 = trasferta, 3 = pareggio.
    Fallback sul nome 'The Draw' se i sort mancano.
    """
    by_sort: Dict[int, int] = {}
    draw_by_name: Optional[int] = None
    for r in runners:
        sid = r.get("selection_id")
        if sid is None:
            continue
        sp = r.get("sort_priority")
        if isinstance(sp, int):
            by_sort[sp] = int(sid)
        name = str(r.get("name") or "").strip().lower()
        if name == "the draw":
            draw_by_name = int(sid)
    return {
        "home": by_sort.get(1),
        "away": by_sort.get(2),
        "draw": by_sort.get(3, draw_by_name),
    }


def tennis_sides(runners: List[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    """p1/p2 → selection_id (sort_priority 1/2) dal catalogo MATCH_ODDS tennis."""
    by_sort: Dict[int, int] = {}
    for r in runners:
        sid = r.get("selection_id")
        sp = r.get("sort_priority")
        if sid is not None and isinstance(sp, int):
            by_sort[sp] = int(sid)
    return {"p1": by_sort.get(1), "p2": by_sort.get(2)}


def split_event_name(event_name: Optional[str]) -> "tuple[Optional[str], Optional[str]]":
    """'Casa v Ospite' → (Casa, Ospite); None se la forma non è riconoscibile."""
    if not event_name:
        return None, None
    for sep in (" v ", " vs ", " @ "):
        if sep in event_name:
            a, b = event_name.split(sep, 1)
            return a.strip() or None, b.strip() or None
    return None, None


def is_hot_minute(minute: Optional[int]) -> bool:
    """Minuto 'caldo' per le strategie calcio: dalla soglia HOT_MINUTE_FROM in poi."""
    return minute is not None and minute >= HOT_MINUTE_FROM


def is_cs_candidate(minute: Optional[int], score_home: Optional[int], score_away: Optional[int]) -> bool:
    """Evento per cui vale la pena tenere sotto quote il Correct Score:
    dal 30' in poi (soglia aperta) con max 3 gol per lato."""
    if minute is None or score_home is None or score_away is None:
        return False
    if minute < CS_MINUTE_FROM:
        return False
    return score_home <= CS_MAX_GOALS_SIDE and score_away <= CS_MAX_GOALS_SIDE


def in_pre_ko_window(open_date: Optional[str], now: datetime) -> bool:
    ko = parse_iso(open_date)
    if ko is None:
        return False
    delta = (ko - now).total_seconds()
    return 0 < delta <= PRE_KO_WINDOW_SEC


def is_monitorable(
    inplay: bool, open_date: Optional[str], now: datetime, pre_ko_ou_hours: float = 0.0,
) -> bool:
    """Riga da pubblicare: evento in-play, KO entro la finestra pre-KO, oppure
    (ramo pre-KO O/U acceso) KO entro ``pre_ko_ou_hours``."""
    return (
        inplay
        or in_pre_ko_window(open_date, now)
        or in_pre_ko_ou_window(open_date, now, pre_ko_ou_hours)
    )


# mercati per cui servono QUOTE (stream o REST): in-play, oppure KO entro
# questa finestra (copre la cattura pre-KO da KO-15' con margine), oppure KO
# già passato ma stato ancora ignoto (nessun book visto: probabilmente in-play).
# Tutto il resto del catalogo (KO lontano) non ha bisogno di quote: così lo
# stream (cap 180 mercati) e il poll REST servono solo ciò che conta.
RELEVANT_PRE_KO_SEC = 20 * 60


def is_relevant_market(
    inplay: Optional[bool],
    mo_status: Optional[str],
    open_date: Optional[str],
    now: datetime,
) -> bool:
    """True se il mercato va tenuto sotto quote adesso (vedi RELEVANT_PRE_KO_SEC)."""
    if mo_status == "CLOSED":
        return False
    if inplay:
        return True
    ko = parse_iso(open_date)
    if ko is None:
        return inplay is None  # senza orario: solo finché non sappiamo nulla
    return (ko - now).total_seconds() <= RELEVANT_PRE_KO_SEC


def rank_key(inplay: Optional[bool], open_date: Optional[str]) -> "tuple[int, str]":
    """Ordine di priorità per il cap dello stream: in-play prima, poi per KO."""
    return (0 if inplay else 1, str(open_date or ""))


def freeze_pre_ko(
    prev: Optional[Dict[str, Any]],
    inplay: bool,
    odds: Optional[Dict[str, Any]],
    adesso_iso: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Riferimento 1X2 pre-KO: si AGGIORNA solo prima del kickoff (closing line),
    si CONGELA per sempre al primo tick in-play. Mai quote in-play nel riferimento.

    ``adesso_iso`` esiste SOLO per il banco di prova (replay su registrazioni),
    dove "adesso" e' il publish time del tick e non l'orologio del PC. Assente =
    ``now_iso()``, cioe' esattamente il comportamento di produzione.
    """
    if inplay:
        return prev
    if not odds:
        return prev
    triple = {}
    for side in ("home", "draw", "away"):
        pair = odds.get(side) or {}
        back = pair.get("back")
        if not isinstance(back, (int, float)):
            return prev  # riferimento solo se il 1X2 è completo
        triple[side] = float(back)
    return {**triple, "captured_at": adesso_iso or now_iso()}


def books_period_calcio(any_inplay: bool, any_hot: bool) -> float:
    """Cadenza (s) del poll quote MATCH_ODDS calcio: fitta solo quando serve."""
    if any_hot:
        return 10.0
    if any_inplay:
        return 20.0
    return 60.0


def books_period_tennis(any_inplay: bool) -> float:
    return 10.0 if any_inplay else 60.0


# Campi che NON contano per decidere se riscrivere la riga: cambiano di continuo
# e non sono un gate per nessuno.
# CERT. 13/09 — ``total_matched`` (e il gemello del 1X2) si muove a OGNI scambio.
# Tenendolo nella firma, una partita in gioco molto scambiata riscriveva ~12 KB
# di JSONB ogni pochi secondi per un contatore che nessuno usa come condizione:
# Mike lo dichiara "diagnostica, nessun gate", Safe/Omega/frontend lo mostrano e
# basta. La tabella e' TOASTata e pubblicata su realtime, quindi ogni UPDATE
# costa heap + TOAST + indice + WAL + decodifica logica: l'amplificazione e' di
# 3-5 volte. Il valore resta NEL payload (viaggia alla prima riscrittura vera),
# esce solo dalla FIRMA.
# ``seen_ms`` (momento dell'ultimo book ricevuto per quel mercato) cambia a
# ogni poll per costruzione: sta nel payload perche' chi legge deve poter
# distinguere "prezzo fermo" da "mercato non piu' osservato", ma nella firma
# riscriverebbe la riga a ogni giro.
_FUORI_FIRMA = ("total_matched", "mo_total_matched", "seen_ms")


def _senza_campi_rumorosi(value: Any) -> Any:
    """Copia del payload senza i campi che non devono innescare una riscrittura
    (ricorsiva: ``total_matched`` sta anche dentro i blocchi cs/ou/btts)."""
    if isinstance(value, dict):
        return {k: _senza_campi_rumorosi(v) for k, v in value.items()
                if k not in _FUORI_FIRMA}
    if isinstance(value, (list, tuple)):
        return [_senza_campi_rumorosi(v) for v in value]
    return value


def payload_signature(payload: Dict[str, Any]) -> str:
    """Firma stabile del payload per il write-on-change (niente updated_at qui,
    e niente contatori di scambiato: vedi ``_FUORI_FIRMA``)."""
    canon = json.dumps(_senza_campi_rumorosi(payload), sort_keys=True,
                       separators=(",", ":"), default=str)
    return hashlib.md5(canon.encode("utf-8")).hexdigest()


def is_ht_candidate(minute: Optional[int]) -> bool:
    """Evento per cui vale la pena tenere sotto quote il HALF TIME SCORE:
    primo tempo in corso, dal 15' al 45' (poi il mercato si regola)."""
    return minute is not None and HT_MINUTE_FROM <= minute < HT_MINUTE_TO


# campi "critici": un loro cambio va pubblicato SUBITO, saltando il throttle
# per-evento pensato per le sole quote (gol, minuto, rossi, stato mercato,
# in-play, set/game; per il CS lo stato del mercato). Le quote da sole aspettano.
_CRITICAL_CALCIO = ("inplay", "mo_status", "minute", "score_home", "score_away", "red_home", "red_away")
_CRITICAL_TENNIS = ("inplay", "mo_status", "sets", "games")


def _opp_blocks(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """I blocchi opportunità del payload (ou + btts + ht_result), in ordine stabile."""
    out: List[Dict[str, Any]] = [b for b in (payload.get("ou") or []) if isinstance(b, dict)]
    for key in ("btts", "ht_result"):
        b = payload.get(key)
        if isinstance(b, dict):
            out.append(b)
    return out


def critical_signature(sport: str, payload: Dict[str, Any]) -> str:
    keys = _CRITICAL_CALCIO if sport == "calcio" else _CRITICAL_TENNIS
    crit: Dict[str, Any] = {k: payload.get(k) for k in keys}
    if sport == "calcio":
        cs = payload.get("cs") or {}
        crit["cs_status"] = cs.get("status") if isinstance(cs, dict) else None
        ht = payload.get("ht") or {}
        crit["ht_status"] = ht.get("status") if isinstance(ht, dict) else None
        # mercati opportunità: un cambio di STATO (sospensione, chiusura) va
        # pubblicato subito come per CS/HT — le quote da sole aspettano il throttle
        crit["opp_status"] = [
            [b.get("market_id"), b.get("status")]
            for b in _opp_blocks(payload)
        ]
    # lo stato IPS grezzo è il feed dei runner (punti tennis, corner/cartellini
    # calcio): ogni suo cambio va pubblicato subito, come un gol
    crit["score_raw"] = payload.get("score_raw")
    return json.dumps(crit, sort_keys=True, separators=(",", ":"), default=str)


# campi dello stato IPS che cambiano OGNI secondo senza informazione utile
# (il minuto è già in `timeElapsed`): tolti dal payload per non riscrivere la
# riga a ogni poll. I parser dei runner li usano solo come fallback.
_VOLATILE_STATE_KEYS = ("timeElapsedSeconds",)


def strip_volatile_state(state: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Copia dello stato IPS senza i campi al secondo. None resta None."""
    if not isinstance(state, dict):
        return None
    return {k: v for k, v in state.items() if k not in _VOLATILE_STATE_KEYS}


def num_or_none(v: Any) -> Optional[float]:
    """float da un valore numerico, None se assente/malformato."""
    return float(v) if isinstance(v, (int, float)) else None


def publish_time_ms(book: Any) -> Optional[int]:
    """F0 (18/09) - istante in cui BETFAIR ha pubblicato questo book, in ms.

    E' l'unico istante della catena che non viene dal nostro orologio, ed e' per
    questo che va tenuto: ``odds_ts_ms`` dice quando NOI abbiamo lavorato il
    book, non quando il prezzo si e' mosso sul mercato. Fra i due c'e' il
    conflate (1.000 ms) e la cadenza del tick dello scanner, cioe' il salto che
    fino a oggi non si poteva misurare perche' mancava il campo.

    ``publish_time_epoch`` (ms interi, dallo stream: ``MarketBookCache.serialise``
    mette ``publishTime`` e ``MarketBook.__init__`` lo tiene grezzo) ha la
    precedenza su ``publish_time`` (datetime): e' lo stesso numero senza andata
    e ritorno per una data. I book che arrivano dal **poll REST** non hanno ne'
    l'uno ne' l'altro: si torna None - dato assente, mai zero.

    ATTENZIONE: e' l'orologio di BETFAIR. Non si sottrae da uno dei nostri senza
    passare da ``Betfair.stream.orologio`` (l'orologio di questa macchina e'
    indietro di ~2,08 s: misura del 17/09).

    ``bool`` non e' un numero: senza la guardia ``isinstance(True, int)`` e' vero
    in Python e un flag diventerebbe l'istante 1 ms.
    """
    if book is None:
        return None
    epoch = getattr(book, "publish_time_epoch", None)
    if isinstance(epoch, (int, float)) and not isinstance(epoch, bool):
        return int(epoch)
    from Betfair.stream import orologio as _oro

    ms = _oro.ms_da_betfair(getattr(book, "publish_time", None))
    return int(ms) if ms is not None else None


def media_flags(broadcasts: Optional[Dict[str, Any]]) -> Dict[str, Optional[bool]]:
    """Disponibilità media Betfair per l'evento dal blocco `broadcasts` dell'IPS
    scoresAndBroadcast (lo stesso che usa il sito per mostrare/nascondere le
    icone): video live (`isLiveVideoAvailable`) e animazione+statistiche
    (`isDataVisualizationAvailable`). None = dato non esposto, MAI inventato."""
    if not isinstance(broadcasts, dict):
        return {"video": None, "viz": None}

    def flag(key: str) -> Optional[bool]:
        v = broadcasts.get(key)
        return v if isinstance(v, bool) else None

    return {"video": flag("isLiveVideoAvailable"), "viz": flag("isDataVisualizationAvailable")}


def build_market_block(
    market_id: Optional[str],
    status: Optional[str],
    selections: List[Dict[str, Any]],
    inplay: Optional[bool] = None,
    total_matched: Optional[float] = None,
    *,
    market_type: Optional[str] = None,
    line: Optional[float] = None,
    ts_ms: Optional[int] = None,
    bet_delay: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Blocco GENERICO di un mercato nel payload: stato + elenco COMPLETO delle
    selezioni (selection_id, nome, best back/lay con le size abbinabili, stato
    runner). È la forma unica usata da Correct Score (Omega) e dai mercati a gol
    del motore opportunità: un solo builder, un solo formato da leggere.

    ``market_type``/``line``/``ts_ms`` finiscono nel blocco SOLO se valorizzati,
    così il blocco `cs` storico resta byte-identico a prima.
    """
    if market_id is None:
        return None
    full: List[Dict[str, Any]] = []
    for s in selections:
        if s.get("selection_id") is None:
            continue
        full.append({
            "selection_id": int(s["selection_id"]),
            "name": str(s.get("name") or ""),
            "runner_status": s.get("runner_status"),
            "back": s.get("back"), "lay": s.get("lay"),
            "back_size": s.get("back_size"), "lay_size": s.get("lay_size"),
        })
    blk: Dict[str, Any] = {
        "market_id": market_id,
        "status": status,
        "inplay": inplay,
        "total_matched": total_matched,
        "selections": full,
    }
    if market_type is not None:
        blk["market_type"] = market_type
    if line is not None:
        blk["line"] = float(line)
    if ts_ms is not None:
        blk["ts_ms"] = int(ts_ms)
    if bet_delay is not None:
        # betDelay del marketDefinition (0 pre-match, ~5s in-play calcio): serve a
        # chi simula i fill in paper con lo stesso ritardo del live (Mike)
        blk["bet_delay"] = int(bet_delay)
    return blk


def build_cs_block(
    market_id: Optional[str],
    status: Optional[str],
    selections: List[Dict[str, Any]],
    inplay: Optional[bool] = None,
    total_matched: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Blocco Correct Score del payload: le selezioni 'Any Other …' (Safe
    Strategy R.E.) E l'elenco COMPLETO delle selezioni con selection_id, nome,
    best back/lay + size e stato runner — è ciò su cui piazza Omega, che così
    legge il book dal feed (stream) invece di rifare listMarketBook a ogni ciclo."""
    blk = build_market_block(market_id, status, selections, inplay, total_matched)
    if blk is None:
        return None
    any_home = any_away = None
    for s in selections:
        name = str(s.get("name") or "")
        pair = {
            # CERT. 13/09 — il ``selection_id`` VIAGGIA COL PREZZO.
            # Prima il pair portava solo le quote e l'id veniva ri-risolto a
            # valle (``engine._any_other_selection_ids``) ri-scandendo le stesse
            # selezioni con una regola di precedenza OPPOSTA (qui vince l'ULTIMO
            # nome che matcha, la' il PRIMO). Prezzo dell'ordine e selezione su
            # cui si piazza arrivavano quindi da due passaggi indipendenti: se
            # due runner matchassero lo stesso schema si piazzerebbe il prezzo
            # di uno sulla selezione di un altro. Money-critical, e chiuso alla
            # radice tenendoli insieme. Effetto collaterale risolto:
            # ``exits.position_side`` leggeva ``blk.get("selection_id")`` e
            # trovava sempre None — il suo percorso primario era codice morto.
            "selection_id": s.get("selection_id"),
            "back": s.get("back"), "lay": s.get("lay"),
            "back_size": s.get("back_size"), "lay_size": s.get("lay_size"),
        }
        if _ANY_OTHER_HOME.search(name):
            any_home = pair
        elif _ANY_OTHER_AWAY.search(name):
            any_away = pair
    blk["any_other_home"] = any_home
    blk["any_other_away"] = any_away
    return blk


# ------------------------------------------------------- mercati opportunità
def ou_line_from_market_type(market_type: Optional[str]) -> Optional[float]:
    """'OVER_UNDER_25' → 2.5, 'OVER_UNDER_05' → 0.5. None se non è un O/U."""
    if not market_type:
        return None
    m = _OU_LINE_RE.match(str(market_type).strip())
    return float(f"{m.group(1)}.{m.group(2)}") if m else None


def is_opp_candidate(inplay: Optional[bool], minute: Optional[int]) -> bool:
    """Evento per cui tenere sotto quote i mercati a gol del motore opportunità:
    partita IN CORSO dal 1' (prima non c'è nessuno stato live da valutare)."""
    return bool(inplay) and minute is not None and minute >= OPP_MINUTE_FROM


def is_ht_result_candidate(minute: Optional[int]) -> bool:
    """1X2 primo tempo (HALF_TIME): utile solo finché il 1T è in corso."""
    return minute is not None and OPP_MINUTE_FROM <= minute < HT_MINUTE_TO


def is_live_ou_line(line: Optional[float], score_home: Optional[int], score_away: Optional[int]) -> bool:
    """Linea Over/Under ancora INDECISA: i gol già segnati non l'hanno superata.
    Superata = esito certo (Over vinto, Under perso): nessuna opportunità."""
    if line is None or score_home is None or score_away is None:
        return False
    return float(line) > int(score_home) + int(score_away)


def is_live_btts(score_home: Optional[int], score_away: Optional[int]) -> bool:
    """Gol/NoGol ancora indeciso: appena segnano entrambe l'esito è certo."""
    if score_home is None or score_away is None:
        return False
    return not (int(score_home) >= 1 and int(score_away) >= 1)


def opp_rank_key(minute: Optional[int], open_date: Optional[str],
                 mike: bool = False) -> "tuple[float, int, str]":
    """Priorità dei mercati opportunità nel pool stream: SEMPRE dopo i mercati
    core (rank_key restituisce tier 0/1, qui il tier è 2) e, tra loro, prima i
    minuti più avanzati — è lì che le probabilità diventano estreme.

    ``mike=True`` (linea 3.5/4.5 di una partita Mike CON posizione): tier 1.5,
    cioè DOPO i mercati core ma PRIMA di ogni altro mercato opportunità (audit
    H5): restare fuori dal pool per il troncamento degli shard significherebbe
    una posizione aperta senza prezzo, quindi senza copertura né cash out.
    I tier restano numerici e distinti, così l'ordinamento non confronta mai una
    data con un minuto."""
    return (1.5 if mike else 2, -(minute or 0), str(open_date or ""))


def is_opp_market_live(
    market_type: Optional[str],
    line: Optional[float],
    minute: Optional[int],
    score_home: Optional[int],
    score_away: Optional[int],
    pre_ko: bool = False,
    mike: bool = False,
) -> bool:
    """Il mercato opportunità serve ADESSO? (linea indecisa / 1T in corso).

    ``pre_ko=True`` (ramo Mike, evento non iniziato): vive SOLO una delle due
    linee ``PRE_KO_OU_MARKET_TYPES`` — senza punteggio nessuna linea è decisa.

    ``mike=True`` (partita SEGUITA da Mike, stato non terminale): le due linee
    3.5 e 4.5 restano vive anche se già decise (audit C2). Per il motore
    opportunità una linea superata è aritmetica, ma per una POSIZIONE aperta è
    il prezzo con cui si esce: l'Over 4.5 dopo il 4° gol è l'unica gamba
    ancora chiudibile, e senza il suo blocco il cash out risponde
    "feed assente"."""
    mt = (market_type or "").upper()
    if mike and mt in MIKE_OU_MARKET_TYPES:
        return True
    if pre_ko:
        return mt in PRE_KO_OU_MARKET_TYPES
    if mt.startswith("OVER_UNDER"):
        return is_live_ou_line(line, score_home, score_away)
    if mt == BTTS_MARKET_TYPE:
        return is_live_btts(score_home, score_away)
    if mt == HT_RESULT_MARKET_TYPE:
        return is_ht_result_candidate(minute)
    return False


def ou_block_decided(blk: Optional[Dict[str, Any]], score_home: Optional[int],
                     score_away: Optional[int]) -> bool:
    """True se il blocco è una linea Over/Under il cui esito è GIÀ DECISO
    (i gol segnati l'hanno superata). Serve a marcare le linee che restano nel
    feed solo per una posizione Mike: sono prezzi validi per CHIUDERE, non
    opportunità da aprire (audit H6)."""
    if not isinstance(blk, dict):
        return False
    mt = str(blk.get("market_type") or "").upper()
    if not mt.startswith("OVER_UNDER"):
        return False
    line = blk.get("line")
    if line is None:
        return False
    return not is_live_ou_line(float(line), score_home, score_away)


def split_opportunity_blocks(blocks: Optional[Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    """{market_id: blocco} → {'ou': [...ordinati per linea], 'btts': …, 'ht_result': …}
    (le tre chiavi ADDITIVE del payload calcio). Valori None se il mercato non c'è."""
    ou: List[Dict[str, Any]] = []
    btts = ht_result = None
    for blk in (blocks or {}).values():
        if not isinstance(blk, dict):
            continue
        mt = str(blk.get("market_type") or "").upper()
        if mt.startswith("OVER_UNDER"):
            ou.append(blk)
        elif mt == BTTS_MARKET_TYPE:
            btts = blk
        elif mt == HT_RESULT_MARKET_TYPE:
            ht_result = blk
    ou.sort(key=lambda b: b.get("line") or 0.0)
    return {"ou": ou or None, "btts": btts, "ht_result": ht_result}
