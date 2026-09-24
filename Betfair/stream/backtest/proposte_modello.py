"""IL MODELLO SUL BANCO - proposte di opportunita', anomalie e combo di Safe.

Cancello C6 (e), `CRONOSTORIA.md` righe 1801-1802 e `PIANO_CANALE_LOCALE_AL_MS_
2026-09-18.md` G.8/R12: il replay di Safe chiamava `bot_service.run_once` con
`opp_model=None`, `opp_mod=None` e `extra_mods` tutti a None. Nessuna proposta
(modello, tennis, anomalia, combo -> riga `safe_strategy_requests` 'proposed',
scheda PIAZZA/RIFIUTA in Control Room dal 17-18/09) era MAI passata da un replay.

CHE COSA C'E' QUI (e nient'altro):

  * I FINTI DEL MODELLO, deterministici, con l'interfaccia del vero:
      - `ModelloCalcioReplay` e' una SOTTOCLASSE di
        `safe_strategy.opportunity.OpportunityModel`: `book()` e' quello VERO
        (griglia Poisson/DC sullo stato live), solo `evaluate()` e' sostituito,
        e ritorna `asdict(Opportunity(...))` - il dataclass VERO, quindi chiavi
        e tipi sono quelli del vero per costruzione;
      - `ModelloTennisReplay` e' una sottoclasse di
        `safe_strategy.tennis_opportunity.TennisOpportunityModel`, stesso
        principio (`asdict(TennisOpportunity(...))`);
      - `AnomalieReplay.detect(payload, book, *, params)` e
        `CombosReplay.find_combos(payload, book, *, params)` hanno la firma dei
        veri (`anomaly.detect`, `combos.find_combos`) e ritornano dict con le
        STESSE chiavi e gli stessi tipi di `anomaly._Ctx.emit` e
        `combos._evaluate` (il test di contratto lo verifica contro un'uscita
        VERA dei due moduli).
    Il modulo `opp_mod` passato al servizio e' quello VERO
    (`Betfair.safe_strategy.opportunity`): `resolve_lambdas`, `OpportunityModel`
    per le uscite a modello, tutto di produzione.
    PREZZI e selezioni vengono dalla riga VERA dello scanner (blocco `odds` del
    payload scritto da `Scanner.build_rows` sulla registrazione): il finto
    decide SOLO QUANDO c'e' un'opportunita' (finestre di tempo di mercato,
    `Finestra`), mai il prezzo.

  * IL TRADER DELLA CONTROL ROOM (`TraderProposte`): preme PIAZZA o RIFIUTA
    sulle schede esattamente come le RPC vere
    (`migrations/safe_request_approve_prezzo_visto_2026-09-18.sql`,
    `migrations/safe_strategy_proposed_2026-09-14.sql`): approva solo una riga
    'proposed' (altrimenti `ok=false` e niente cambia), la porta a 'pending' e
    aggiunge al payload `approved_at`, `price_visto_at`, `price_visto` /
    `legs_prices_visti`. Il prezzo visto e' quello che la scheda mostra: il
    prezzo VIVO della selezione sulla riga del feed, oppure la FOTOGRAFIA della
    proposta (scheda non aggiornata) quando lo scenario lo chiede.

  * LE PORTE DEL DATABASE (`ProposteDb`, mixin per i due DB in memoria di Safe):
    `proposte_opportunita`, `trades_pending_o_aperti`,
    `scrivi_proposta_opportunita`, `chiudi_proposta_opportunita`,
    `marca_proposta_opportunita_annotata` con la firma e il tipo di ritorno di
    `bot_db.py`, compreso l'indice unico `uq_safe_requests_proposta_opp_viva`
    (una seconda proposta viva con lo stesso `opp_key` SOLLEVA, come il DB).

  * I CONTROLLI DI CONDOTTA (famiglia PM, `Sorveglianza`), elencati in
    `_REGOLE` qui sotto e contati nel referto da `certifica.py`.

SCENARI (in `SCENARI_DESCRITTI` di Safe calcio e, dove hanno senso, tennis):
  proposta-approvata, proposta-scaduta, proposta-anomalia-effimera,
  combos-automatiche. Anomalie e combo esistono SOLO sul calcio
  (`bot_service.process_anomalies:6969-6978` e `process_opportunities:6116-6153`
  guardano sport='calcio'): sul tennis quei due scenari non esistono.

Negli scenari PREESISTENTI niente di questo e' montato: `run_once` riceve gli
stessi argomenti di prima e i referti non cambiano di una riga.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import math
import re
import types
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

SCENARIO_APPROVATA = "proposta-approvata"
SCENARIO_SCADUTA = "proposta-scaduta"
SCENARIO_ANOMALIA = "proposta-anomalia-effimera"
SCENARIO_COMBOS = "combos-automatiche"
# 24/09 (estensione B25): lo STESSO scenario delle combo col pulsante
# dell'utente su 'automatico' (`combo_gamba_manuale`): la gamba manuale
# lasciata dalla combo incompleta la chiude il bot, come prima di B25.
SCENARIO_COMBOS_AUTO = "combos-gamba-automatica"
SCENARI_COMBO: Tuple[str, ...] = (SCENARIO_COMBOS, SCENARIO_COMBOS_AUTO)
SCENARI_CALCIO: Tuple[str, ...] = (SCENARIO_APPROVATA, SCENARIO_SCADUTA,
                                   SCENARIO_ANOMALIA, SCENARIO_COMBOS,
                                   SCENARIO_COMBOS_AUTO)
SCENARI_TENNIS: Tuple[str, ...] = (SCENARIO_APPROVATA, SCENARIO_SCADUTA)
TUTTI: Tuple[str, ...] = SCENARI_CALCIO

DESCRIZIONI: Dict[str, str] = {
    SCENARIO_APPROVATA: (
        "MODELLO MONTATO (finto deterministico con l'interfaccia del vero, prezzi "
        "dalla riga vera dello scanner): tre proposte; il trader ne approva una "
        "dopo 20 s col prezzo VIVO (ordine al prezzo visto), una col prezzo della "
        "FOTOGRAFIA appena il mercato si muove oltre la tolleranza (rifiuto per "
        "slippage) e una dopo 180 s (proposta piu' vecchia di 120 s). "
        "strategy_modes.model='live' scritto (PM1-PM5, PM7)"),
    SCENARIO_SCADUTA: (
        "MODELLO MONTATO: una proposta mai approvata che DECADE quando "
        "l'opportunita' sparisce (clic dopo la decadenza -> nessun ordine) e una "
        "RIFIUTATA dal trader (RIFIUTA tiene, nessun ordine, nessuna riproposta). "
        "strategy_modes.model NON scritto: proposte in PAPER col servizio in LIVE "
        "(PM1, PM2, PM4, PM5)"),
    SCENARIO_ANOMALIA: (
        "ANOMALIE MONTATE (finto di anomaly.detect): un'anomalia sparisce e la "
        "proposta decade prima del clic (clic a vuoto, nessun ordine); un'altra "
        "sparisce dal rilevamento mentre la scheda e' ancora viva e il trader "
        "preme PIAZZA (PM6: l'anomalia sparita prima del clic non deve dare un "
        "ordine)"),
    SCENARIO_COMBOS: (
        "COMBO MONTATE (finto di combos.find_combos) con auto_trade_combos ACCESO: "
        "dal 18/09 nessuna combo parte senza approvazione anche con l'interruttore "
        "acceso (PM1); il trader approva la proposta con i prezzi visti di ogni "
        "gamba -> tutte le gambe o nessuna, stessi tetti di rischio (PM3, PM8)"),
    SCENARIO_COMBOS_AUTO: (
        "COMBO MONTATE come `combos-automatiche`, con combo_gamba_manuale="
        "'automatico' SCRITTO dall'utente: la gamba MANUALE lasciata da una "
        "combo incompleta la chiude il bot, col motivo che dichiara la scelta "
        "dell'utente (T13-COMBO in modo automatico, PM3, PM8)"),
}

# ---------------------------------------------------------------------------
# i controlli
# ---------------------------------------------------------------------------
_REGOLE: Tuple[Tuple[str, str], ...] = (
    ("PM1", "mai un ordine da una proposta NON approvata: ogni riga strategy='model' "
            "(o con meta.opp_key) nasce da un PIAZZA del trader, mai origin='auto' "
            "(ordine utente 17-18/09, anche con auto_trade_* accesi)"),
    ("PM2", "mai due proposte VIVE identiche (indice unico "
            "uq_safe_requests_proposta_opp_viva) e mai una scrittura di proposta "
            "respinta dal DB"),
    ("PM3", "prezzo visto rispettato: l'ordine parte AL prezzo visto e solo se il "
            "mercato e' entro la tolleranza (SLIPPAGE_PCT_DEFAULT o quella della "
            "scheda); oltre -> rifiuto dichiarato, mai ordine"),
    ("PM4", "proposta scaduta, decaduta o RIFIUTATA = nessun ordine; un clic su una "
            "scheda non piu' viva non cambia niente; RIFIUTA tiene (nessuna "
            "riproposta della stessa chiave)"),
    ("PM5", "parita' paper/live delle proposte: la modalita' della proposta e' "
            "quella SCRITTA (servizio LIVE + strategy_modes.model='live', altrimenti "
            "paper) e la riga nata dall'approvazione ha la modalita' della proposta"),
    ("PM6", "un'anomalia sparita dal rilevamento PRIMA del clic non da' un ordine"),
    ("PM7", "un PIAZZA con clic fresco su una proposta viva non si perde per l'eta' "
            "della PROPOSTA (mai 'richiesta_scaduta' su un'approvazione appena fatta)"),
    ("PM8", "combo: tutte le gambe o nessuna alla riserva, ognuna nel tetto "
            "max_liability_per_trade"),
)


def parametri(scenario: str, par: Dict[str, Any]) -> Dict[str, Any]:
    """I parametri GREZZI del control per uno scenario PM, a partire da quelli
    dello scenario: solo leve che l'utente ha nella Control Room.

      * `strategy_modes.model = 'live'` SCRITTO (approvata, anomalia, combo):
        "i soldi veri si raggiungono solo scrivendolo" - senza, le proposte
        nascono PAPER e l'ordine approvato non passerebbe da flumine;
      * `proposta-scaduta` NON lo scrive: proposte PAPER col servizio LIVE, ed
        e' il caso che PM5 giudica;
      * `combos-automatiche`: `auto_trade_combos = True`.
    Nessuna soglia, stake, tetto o gamba della strategia cambia."""
    out = dict(par)
    if scenario in (SCENARIO_APPROVATA, SCENARIO_ANOMALIA) + SCENARI_COMBO:
        sm = dict(out.get("strategy_modes") or {})
        sm["model"] = "live"
        out["strategy_modes"] = sm
    if scenario in SCENARI_COMBO:
        out["auto_trade_combos"] = True
    if scenario == SCENARIO_COMBOS_AUTO:
        out["combo_gamba_manuale"] = "automatico"
    return out


def azzera_cache_lambda() -> None:
    """`omega_service._LAMBDA_CACHE` e' di PROCESSO (la usa la catena dei lambda
    di Safe): due scenari PM nello stesso processo figlio la condividerebbero."""
    try:
        from Betfair.omega import omega_service as OS
    except Exception:  # noqa: BLE001 - modulo assente: niente da azzerare
        return
    cache = getattr(OS, "_LAMBDA_CACHE", None)
    if isinstance(cache, dict):
        cache.clear()


def elenco_controlli() -> List[Tuple[str, str]]:
    """(codice, regola) dei controlli PM: il contratto della copertura."""
    return list(_REGOLE)


def controlli_per(scenari: Sequence[str]) -> List[Tuple[str, str]]:
    """I controlli PM che gli scenari eseguiti POSSONO sollecitare: PM6 esiste
    solo con le anomalie, PM8 solo con le combo (sul tennis non ci sono, e un
    "non lo so" su un caso impossibile sarebbe rumore, non un'informazione)."""
    scelti = set(scenari)
    fuori = set()
    if SCENARIO_ANOMALIA not in scelti:
        fuori.add("PM6")
    if not scelti & set(SCENARI_COMBO):
        fuori.add("PM8")
    return [(c, r) for c, r in _REGOLE if c not in fuori]


def regola(codice: str) -> str:
    return dict(_REGOLE).get(str(codice), "")


# margine d'errore del modello finto: edge dichiarato sopra `opps_min_edge`
# (0,03 di default) e confidenza sopra `opps_min_confidence` (0,7). Non sono
# soglie della strategia: sono i NUMERI che il finto dichiara, scelti perche'
# la proposta superi le barriere VERE di `_proponi_opps`/`_proponi_combo`.
EDGE_FINTO = 0.06
CONFIDENZA_FINTA = 0.9
# quando il trader, dopo un RIFIUTA, prova comunque a premere PIAZZA
RITARDO_CLIC_DOPO_RIFIUTO_S = 20.0


# ---------------------------------------------------------------------------
# utilita'
# ---------------------------------------------------------------------------
def _num(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _int(v: Any, default: Optional[int] = None) -> Optional[int]:
    x = _num(v)
    return int(x) if x is not None else default


def _ts(v: Any) -> Optional[float]:
    """ISO (con o senza Z) -> epoch secondi; None se illeggibile."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        d = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()


def blocco_odds(payload: Any, chiave: str) -> Optional[Dict[str, Any]]:
    """Il blocco `odds[chiave]` della riga dello scanner (home/draw/away o p1/p2)."""
    odds = payload.get("odds") if isinstance(payload, dict) else None
    blk = odds.get(chiave) if isinstance(odds, dict) else None
    return blk if isinstance(blk, dict) else None


def prezzo_in_riga(riga: Any, selection_id: Any, lato: str) -> Optional[float]:
    """Il prezzo che la SCHEDA mostra adesso per (selezione, lato): letto dal
    blocco `odds` della riga del feed, SENZA passare dalle funzioni del servizio
    (`bot_service.prices_from_row`): e' il termine di paragone dei controlli e
    non deve poter sbagliare insieme al codice che controlla."""
    payload = (riga or {}).get("payload") if isinstance(riga, dict) else None
    odds = payload.get("odds") if isinstance(payload, dict) else None
    if not isinstance(odds, dict) or selection_id is None:
        return None
    for blk in odds.values():
        if not isinstance(blk, dict) or blk.get("selection_id") is None:
            continue
        try:
            if int(blk["selection_id"]) != int(selection_id):
                continue
        except (TypeError, ValueError):
            continue
        p = _num(blk.get(str(lato)))
        return p if p is not None and p > 1.0 else None
    return None


def _nome_selezione(payload: Dict[str, Any], chiave: str) -> str:
    if chiave == "draw":
        return "The Draw"
    return str(payload.get(chiave) or chiave)


def _coda(db: Any) -> List[Dict[str, Any]]:
    """La coda `safe_strategy_requests` del DB in memoria. Si legge da `vars`:
    il `__getattr__` del banco trasformerebbe un nome assente in un metodo
    (e lo registrerebbe fra i `mancanti`)."""
    v = vars(db)
    coda = v.get("requests")
    if coda is None:
        coda = v.get("richieste")
    return coda if isinstance(coda, list) else []


# ---------------------------------------------------------------------------
# il PIANO: quando c'e' un'opportunita' (mai che prezzo ha)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Finestra:
    """Un'opportunita' che il finto dichiara fra `dal_s` e `al_s` secondi di
    MERCATO dal primo istante in gioco con prezzi, e che cosa ne fa il trader.

    azione: 'approva' | 'ignora' | 'niente'
    quando: 'eta'             -> clic quando la proposta ha `dopo_s` secondi
            'deriva'          -> clic col prezzo della FOTOGRAFIA appena il vivo
                                 se ne allontana oltre la tolleranza (o a `dopo_s`)
            'dopo_decadenza'  -> clic appena la proposta e' DECADUTA
            'dopo_sparizione' -> clic appena il finto non la rileva piu' ma la
                                 scheda e' ancora viva
    """

    nome: str
    tipo: str                       # 'model' | 'tennis' | 'anomaly' | 'combo'
    selezioni: Tuple[str, ...]      # chiavi del blocco odds
    lato: str
    dal_s: float
    al_s: float
    azione: str = "niente"
    quando: str = "eta"
    dopo_s: float = 0.0


def finestre_di(scenario: str, sport: str) -> Tuple[Finestra, ...]:
    """Le finestre dello scenario. Stesse regole per calcio e tennis: cambiano
    solo le chiavi delle selezioni (home/draw/away contro p1/p2)."""
    calcio = sport == "calcio"
    a, b, c = (("draw",), ("away",), ("home",)) if calcio else (("p1",), ("p2",), ("p1",))
    tipo = "model" if calcio else "tennis"
    if scenario == SCENARIO_APPROVATA:
        if calcio:
            return (
                Finestra("A", tipo, a, "back", 30, 930, "approva", "eta", 20),
                Finestra("B", tipo, b, "back", 30, 930, "approva", "deriva", 100),
                Finestra("C", tipo, c, "back", 30, 930, "approva", "eta", 180),
            )
        # tennis: due sole selezioni -> A (p1 back, vivo) e C (p2 back, 180 s);
        # la deriva la fa B sul LAY di p1 (lato diverso = chiave diversa)
        return (
            Finestra("A", tipo, ("p1",), "back", 30, 930, "approva", "eta", 20),
            Finestra("B", tipo, ("p1",), "lay", 30, 930, "approva", "deriva", 100),
            Finestra("C", tipo, ("p2",), "back", 30, 930, "approva", "eta", 180),
        )
    if scenario == SCENARIO_SCADUTA:
        return (
            Finestra("D", tipo, a, "back", 30, 150, "approva", "dopo_decadenza", 0),
            Finestra("E", tipo, b, "back", 30, 930, "ignora", "eta", 20),
        )
    if scenario == SCENARIO_ANOMALIA and calcio:
        return (
            Finestra("X", "anomaly", ("home",), "back", 30, 50, "approva",
                     "dopo_decadenza", 0),
            Finestra("Y", "anomaly", ("away",), "back", 200, 215, "approva",
                     "dopo_sparizione", 0),
        )
    if scenario in SCENARI_COMBO and calcio:
        return (Finestra("K", "combo", ("home", "draw", "away"), "back", 30, 930,
                         "approva", "eta", 20),)
    return ()


class Piano:
    """L'orologio del finto: `t0` e' il primo istante in cui un finto viene
    interrogato su una riga IN GIOCO con prezzi; le finestre contano da li'."""

    def __init__(self, finestre: Sequence[Finestra],
                 orologio: Callable[[], float]) -> None:
        self.finestre: Tuple[Finestra, ...] = tuple(finestre)
        self.orologio = orologio
        self.t0: Optional[float] = None
        # nome finestra -> selection_id (tupla per le combo), imparati dalla riga
        self.sid: Dict[str, Tuple[int, ...]] = {}
        # quante volte ogni finestra e' stata EMESSA dal finto
        self.emesse: Counter = Counter()

    def adesso(self) -> float:
        return float(self.orologio())

    def inizia(self, payload: Any) -> None:
        if self.t0 is None and isinstance(payload, dict) and payload.get("inplay") \
                and isinstance(payload.get("odds"), dict):
            self.t0 = self.adesso()

    def attiva(self, f: Finestra, quando: Optional[float] = None) -> bool:
        if self.t0 is None:
            return False
        t = (self.adesso() if quando is None else float(quando)) - self.t0
        return float(f.dal_s) <= t < float(f.al_s)

    def attive(self, tipo: str) -> List[Finestra]:
        return [f for f in self.finestre if f.tipo == tipo and self.attiva(f)]

    def per_nome(self, nome: str) -> Optional[Finestra]:
        return next((f for f in self.finestre if f.nome == nome), None)


def _numeri_di_una_gamba(price: float, lato: str, commissione: float) -> Dict[str, float]:
    """p_model/edge/ev dichiarati dal finto, con le FORMULE del vero
    (`opportunity._try_side`: ev back = p(q-1)(1-c)-(1-p), lay = (1-p)(1-c)-p(q-1))."""
    pi = 1.0 / price
    if lato == "back":
        pm = min(0.999, pi + EDGE_FINTO)
        edge = pm - pi
        ev = pm * (price - 1.0) * (1.0 - commissione) - (1.0 - pm)
    else:
        pm = max(0.001, pi - EDGE_FINTO)
        edge = pi - pm
        ev = (1.0 - pm) * (1.0 - commissione) - pm * (price - 1.0)
    return {"p_model": pm, "p_implied": pi, "edge": edge, "ev": ev}


def _gamba(payload: Dict[str, Any], chiave: str, lato: str) -> Optional[Dict[str, Any]]:
    blk = blocco_odds(payload, chiave)
    if blk is None or blk.get("selection_id") is None:
        return None
    price = _num(blk.get(lato))
    if price is None or price <= 1.0:
        return None
    size = _num(blk.get(f"{lato}_size")) or 0.0
    return {"selection_id": int(blk["selection_id"]), "price": float(price),
            "size": float(size), "nome": _nome_selezione(payload, chiave)}


# ---------------------------------------------------------------------------
# I FINTI
# ---------------------------------------------------------------------------
def _classe_modello_calcio():
    from Betfair.safe_strategy import opportunity as OP

    class ModelloCalcioReplay(OP.OpportunityModel):
        """`OpportunityModel` VERO con `evaluate` deterministico.

        `book()` e' ereditato: anomalie, combo e uscite ricevono la griglia vera.
        `evaluate()` ha la STESSA firma del vero e ritorna `asdict` del dataclass
        VERO `Opportunity`, quindi le chiavi e i tipi non possono divergere."""

        def __init__(self, params: Optional[dict] = None, *, piano: Piano,
                     **kw: Any) -> None:
            kw.setdefault("calibration", "off")
            super().__init__(params, **kw)
            self.piano = piano

        def evaluate(self, payload: dict, *, sport: str,
                     lambdas: Optional[Tuple[float, float]],
                     league_id: Optional[int], now_ts: float,
                     ht_ratio: Optional[Tuple[float, float]] = None,
                     lambda_source: Optional[str] = None) -> List[dict]:
            if sport != "calcio" or not isinstance(payload, dict) \
                    or not payload.get("inplay"):
                return []
            self.piano.inizia(payload)
            comm = float(self.params.get("commission") or 0.05)
            sh = _int(payload.get("score_home"), 0)
            sa = _int(payload.get("score_away"), 0)
            out: List[dict] = []
            for f in self.piano.attive("model"):
                g = _gamba(payload, f.selezioni[0], f.lato)
                if g is None:
                    continue
                self.piano.sid[f.nome] = (g["selection_id"],)
                self.piano.emesse[f.nome] += 1
                n = _numeri_di_una_gamba(g["price"], f.lato, comm)
                o = OP.Opportunity(
                    market_type="MATCH_ODDS", market_name="1X2", line=None,
                    market_id=payload.get("mo_market_id"),
                    selection_id=int(g["selection_id"]), selection_name=g["nome"],
                    side=f.lato, price=round(g["price"], 4),
                    size_available=round(g["size"], 2),
                    p_model=round(n["p_model"], 6), p_implied=round(n["p_implied"], 6),
                    edge=round(n["edge"], 6), ev=round(n["ev"], 6),
                    confidence=round(CONFIDENZA_FINTA, 4),
                    rationale=(f"[BANCO finestra {f.nome}] {g['nome']} {f.lato} "
                               f"@{g['price']:.2f}: opportunita' DICHIARATA dal finto"),
                    minute=_int(payload.get("minute")), score=f"{sh}-{sa}",
                    p_model_raw=round(n["p_model"], 6),
                    calibration={"applied": False, "family": None, "n": 0})
                out.append(asdict(o))
            return out

    return ModelloCalcioReplay


def _classe_modello_tennis(piano: Piano):
    from Betfair.safe_strategy import tennis_opportunity as TO

    class ModelloTennisReplay(TO.TennisOpportunityModel):
        """`TennisOpportunityModel` VERO con `evaluate` deterministico; il
        servizio lo costruisce da solo (`_tennis_model`: `mod.TennisOpportunity
        Model(params)`), quindi il piano e' legato alla classe."""

        PIANO = piano

        def evaluate(self, payload: dict, now_ts: float) -> List[dict]:
            if not isinstance(payload, dict) or not payload.get("inplay"):
                return []
            self.PIANO.inizia(payload)
            comm = float(self.params.get("commission") or 0.05)
            sets = payload.get("sets") if isinstance(payload.get("sets"), dict) else {}
            games = payload.get("games") if isinstance(payload.get("games"), dict) else {}
            score = (f"set {sets.get('p1')}-{sets.get('p2')} - "
                     f"game {games.get('p1')}-{games.get('p2')}")
            out: List[dict] = []
            for f in self.PIANO.attive("tennis"):
                g = _gamba(payload, f.selezioni[0], f.lato)
                if g is None:
                    continue
                self.PIANO.sid[f.nome] = (g["selection_id"],)
                self.PIANO.emesse[f.nome] += 1
                n = _numeri_di_una_gamba(g["price"], f.lato, comm)
                o = TO.TennisOpportunity(
                    market_type="MATCH_ODDS", market_name="Match Odds", line=None,
                    market_id=payload.get("mo_market_id"),
                    selection_id=int(g["selection_id"]), selection_name=g["nome"],
                    side=f.lato, price=round(g["price"], 4),
                    size_available=round(g["size"], 2),
                    p_model=round(n["p_model"], 6), p_implied=round(n["p_implied"], 6),
                    edge=round(n["edge"], 6), ev=round(n["ev"], 6),
                    confidence=round(CONFIDENZA_FINTA, 4),
                    rationale=(f"[BANCO finestra {f.nome}] {g['nome']} {f.lato} "
                               f"@{g['price']:.2f}: opportunita' DICHIARATA dal finto"),
                    minute=None, score=score, kind="tennis",
                    extra={"p_model_raw": round(n["p_model"], 6), "retire_risk": 0.0,
                           "best_of": 3, "server": None, "momentum_against": False,
                           "price_age_s": None})
                out.append(asdict(o))
            return out

    return ModelloTennisReplay


class AnomalieReplay:
    """Finto di `Betfair.safe_strategy.anomaly` (il servizio chiama SOLO
    `detect`). Le chiavi del dict sono quelle di `anomaly._Ctx.emit`."""

    def __init__(self, piano: Piano) -> None:
        self.piano = piano

    def detect(self, payload: dict, book: Dict[str, float], *,
               params: Optional[dict] = None) -> List[dict]:
        if not isinstance(payload, dict) or not payload.get("inplay"):
            return []
        self.piano.inizia(payload)
        comm = _num((params or {}).get("commission_pct"))
        comm = comm / 100.0 if comm is not None else 0.05
        minute = _int(payload.get("minute"), 0)
        score = f"{_int(payload.get('score_home'), 0)}-{_int(payload.get('score_away'), 0)}"
        out: List[dict] = []
        for f in self.piano.attive("anomaly"):
            g = _gamba(payload, f.selezioni[0], f.lato)
            if g is None:
                continue
            self.piano.sid[f.nome] = (g["selection_id"],)
            self.piano.emesse[f.nome] += 1
            n = _numeri_di_una_gamba(g["price"], f.lato, comm)
            out.append({
                "kind": "anomaly", "rule": "banco_finestra",
                "market_type": "MATCH_ODDS", "market_name": "1X2", "line": None,
                "market_id": payload.get("mo_market_id"),
                "selection_id": int(g["selection_id"]),
                "selection_name": g["nome"], "side": f.lato,
                "price": round(g["price"], 4), "size_available": round(g["size"], 2),
                "p_model": round(n["p_model"], 6), "p_implied": round(n["p_implied"], 6),
                "edge": round(n["edge"], 6), "ev": round(n["ev"], 6),
                "confidence": round(CONFIDENZA_FINTA, 4),
                "gap": round(n["edge"], 6), "ref": f"finestra {f.nome}",
                "p_source": "riferimento",
                "rationale": (f"{g['nome']} {f.lato} {g['price']:.2f} [BANCO finestra "
                              f"{f.nome}] sul {score} al {minute}'"),
                "minute": int(minute), "score": score,
            })
        return out


class CombosReplay:
    """Finto di `Betfair.safe_strategy.combos` (il servizio chiama SOLO
    `find_combos`). Le chiavi del dict (e di ogni gamba) sono quelle di
    `combos._evaluate`; gli stake per gamba seguono la regola del vero
    (dutching sul `combo_stake`, `min_total_stake` dal `min_leg_stake`)."""

    def __init__(self, piano: Piano) -> None:
        self.piano = piano
        self._scelte: Dict[str, Tuple[str, ...]] = {}

    def find_combos(self, payload: dict, book: Dict[str, float], *,
                    params: Optional[dict] = None) -> List[dict]:
        from Betfair.safe_strategy import combos as CO

        if not isinstance(payload, dict) or not payload.get("inplay"):
            return []
        self.piano.inizia(payload)
        prm = {**CO.DEFAULT_COMBO_PARAMS, **(params or {})}
        minute = _int(payload.get("minute"), 0)
        score = f"{_int(payload.get('score_home'), 0)}-{_int(payload.get('score_away'), 0)}"
        out: List[dict] = []
        for f in self.piano.attive("combo"):
            # LE DUE GAMBE si scelgono UNA VOLTA, alla prima emissione: le due
            # selezioni a quota piu' alta fra quelle della finestra (le piu'
            # equilibrate, cosi' che la gamba piccola non cada sotto
            # `min_leg_stake` e il vero `_proponi_combo` non la scarti per
            # `combo_totale_sotto_minimo`). Poi restano quelle: una combo e'
            # definita dalle sue gambe (`cid`), non dal prezzo del momento.
            chiavi = self._scelte.get(f.nome)
            if chiavi is None:
                cand = [(k, _gamba(payload, k, f.lato)) for k in f.selezioni]
                cand = [(k, g) for k, g in cand if g is not None]
                if len(cand) < 2:
                    continue
                cand.sort(key=lambda kg: -kg[1]["price"])
                chiavi = tuple(sorted((cand[0][0], cand[1][0]),
                                      key=lambda k: f.selezioni.index(k)))
                self._scelte[f.nome] = chiavi
            gambe = [_gamba(payload, k, f.lato) for k in chiavi]
            if any(g is None for g in gambe) or len(gambe) < 2:
                continue
            self.piano.sid[f.nome] = tuple(int(g["selection_id"]) for g in gambe)
            self.piano.emesse[f.nome] += 1
            inv = [1.0 / g["price"] for g in gambe]
            totale_voluto = float(prm["combo_stake"])
            stakes = [round(i / sum(inv) * totale_voluto, 2) for i in inv]
            totale = round(sum(stakes), 2)
            ratios = [s / totale for s in stakes]
            min_leg = float(prm.get("min_leg_stake") or 0.0)
            min_tot = round(max(max(min_leg / r for r in ratios if r > 0), totale), 2)
            primo = gambe[0]
            out.append({
                "kind": "combo", "combo": "dutch",
                "market_type": "MATCH_ODDS", "market_name": "1X2", "line": None,
                "market_id": payload.get("mo_market_id"),
                "selection_id": int(primo["selection_id"]),
                "selection_name": primo["nome"], "side": f.lato,
                "price": round(primo["price"], 4),
                "size_available": round(primo["size"], 2),
                "p_model": round(1.0 / primo["price"], 6), "p_model_source": "implicita",
                "p_implied": round(1.0 / primo["price"], 6),
                "edge": round(EDGE_FINTO, 6), "ev": round(EDGE_FINTO, 6),
                "confidence": round(CONFIDENZA_FINTA, 4),
                "rationale": (f"[BANCO finestra {f.nome}] combinazione DICHIARATA dal "
                              f"finto sul {score} al {minute}'"),
                "minute": int(minute), "score": score,
                "legs": [{"market_type": "MATCH_ODDS",
                          "market_id": payload.get("mo_market_id"),
                          "selection_id": int(g["selection_id"]),
                          "selection_name": g["nome"], "side": f.lato,
                          "price": round(g["price"], 4),
                          "size_available": round(g["size"], 2),
                          "stake_ratio": round(s / totale, 6), "stake": s}
                         for g, s in zip(gambe, stakes)],
                "locked_profit_per_eur": round(EDGE_FINTO, 6),
                "worst_case_per_eur": round(EDGE_FINTO, 6),
                "worst_case_rounded_per_eur": round(EDGE_FINTO, 6),
                "best_case_per_eur": round(EDGE_FINTO, 6),
                "total_stake": totale,
                "min_leg_stake": round(min_leg, 2),
                "min_total_stake": min_tot,
                "book_supports_min": True,
                "executable_whole": bool(totale + 1e-9 >= min_tot),
            })
        return out


# ---------------------------------------------------------------------------
# LE PORTE DEL DATABASE (mixin per DbSafeMemoria e DbMemoriaSafe)
# ---------------------------------------------------------------------------
class ProposteDb:
    """Le cinque porte di `bot_db.py` che le proposte usano, con la firma e il
    tipo di ritorno del vero. Negli scenari preesistenti il servizio non le
    chiama mai (`process_opportunities` esce prima, a modello assente)."""

    def _prop_iso(self) -> str:
        f = getattr(self, "_ora_iso", None) or getattr(self, "_iso")
        return f()

    def _prop_nuovo_id(self) -> int:
        v = vars(self)
        nome = "_req_id" if "_req_id" in v else "_rid"
        v[nome] = int(v.get(nome) or 0) + 1
        return int(v[nome])

    def proposte_opportunita(self, ore: int = 24, limit: int = 300) -> List[Dict[str, Any]]:
        righe = [dict(r, payload=dict(r.get("payload") or {})) for r in _coda(self)
                 if str(r.get("kind")) == "place"
                 and str(r.get("status")) in ("proposed", "rejected")
                 and isinstance(r.get("payload"), dict) and r["payload"].get("opp_key")]
        righe.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return righe[:int(limit)]

    def trades_pending_o_aperti(self, mode: Optional[str] = None) -> List[Dict[str, Any]]:
        m = str(mode).lower() if mode else None
        return [dict(r) for r in getattr(self, "trades", [])
                if str(r.get("status")) in ("pending", "open")
                and (m is None or str(r.get("mode") or "") == m)]

    def scrivi_proposta_opportunita(self, opp_key: str, payload: Dict[str, Any],
                                    req_id: Optional[int] = None) -> Optional[int]:
        corpo = {**payload, "opp_key": str(opp_key)}
        coda = _coda(self)
        if req_id is not None:
            for r in coda:
                if int(r.get("id") or 0) == int(req_id) and str(r.get("status")) == "proposed":
                    r["payload"] = corpo
                    r["updated_at"] = self._prop_iso()
            return int(req_id)
        # INDICE UNICO `uq_safe_requests_proposta_opp_viva`: come il DB, solleva
        for r in coda:
            if (str(r.get("status")) == "proposed"
                    and str((r.get("payload") or {}).get("opp_key") or "") == str(opp_key)):
                raise RuntimeError("duplicate key value violates unique constraint "
                                   "\"uq_safe_requests_proposta_opp_viva\"")
        rid = self._prop_nuovo_id()
        adesso = self._prop_iso()
        coda.append({"id": rid, "kind": "place", "status": "proposed", "payload": corpo,
                     "created_at": adesso, "updated_at": adesso, "result": None})
        return rid

    def chiudi_proposta_opportunita(self, req_id: int, motivo: str) -> None:
        for r in _coda(self):
            if int(r.get("id") or 0) == int(req_id) and str(r.get("status")) == "proposed":
                r["status"] = "rejected"
                r["result"] = {"decaduta": True, "motivo": str(motivo)[:200]}
                r["updated_at"] = self._prop_iso()

    def marca_proposta_opportunita_annotata(self, req_id: int,
                                            result: Dict[str, Any]) -> None:
        for r in _coda(self):
            if int(r.get("id") or 0) == int(req_id):
                r["result"] = {**(result or {}), "attivita_scritta": True}
                r["updated_at"] = self._prop_iso()


# ---------------------------------------------------------------------------
# LE RPC della Control Room (lato database, come in SQL)
# ---------------------------------------------------------------------------
def _riga_coda(db: Any, req_id: int) -> Optional[Dict[str, Any]]:
    return next((r for r in _coda(db) if int(r.get("id") or 0) == int(req_id)), None)


def rpc_approva(db: Any, req_id: int, adesso: float, *, prezzo: Optional[float] = None,
                prezzi_gambe: Optional[Dict[str, float]] = None,
                slippage_pct: Optional[float] = None) -> Dict[str, Any]:
    """`safe_request_approve(p_id, p_price, p_legs_prices, p_slippage_pct)`."""
    r = _riga_coda(db, req_id)
    if r is None:
        raise RuntimeError(f"richiesta {req_id} inesistente")
    if str(r.get("status")) != "proposed":
        return {"ok": False, "id": int(req_id), "status": r.get("status"),
                "note": "la proposta non e' piu' in attesa di approvazione"}
    d = datetime.fromtimestamp(float(adesso), tz=timezone.utc)
    extra: Dict[str, Any] = {"approved_at": d.strftime("%Y-%m-%dT%H:%M:%SZ")}
    if prezzo is not None or prezzi_gambe is not None:
        extra["price_visto_at"] = d.strftime("%Y-%m-%dT%H:%M:%S.") + \
            f"{int(d.microsecond / 1000):03d}Z"
    if prezzo is not None:
        extra["price_visto"] = float(prezzo)
    if prezzi_gambe is not None:
        extra["legs_prices_visti"] = {str(k): float(v) for k, v in prezzi_gambe.items()}
    if slippage_pct is not None:
        extra["slippage_pct"] = float(slippage_pct)
    r["status"] = "pending"
    r["payload"] = {**(r.get("payload") or {}), **extra}
    r["updated_at"] = _iso(adesso)
    return {"ok": True, "id": int(req_id), "status": "pending"}


def rpc_ignora(db: Any, req_id: int, adesso: float,
               motivo: Optional[str] = None) -> Dict[str, Any]:
    """`safe_request_ignore(p_id, p_reason)`."""
    r = _riga_coda(db, req_id)
    if r is None:
        raise RuntimeError(f"richiesta {req_id} inesistente")
    if str(r.get("status")) != "proposed":
        return {"ok": False, "id": int(req_id), "status": r.get("status"),
                "note": "la proposta non e' piu' in attesa di approvazione"}
    r["status"] = "rejected"
    r["result"] = {**(r.get("result") or {}), "ignorata_dall_utente": True,
                   "motivo": (str(motivo).strip() if motivo and str(motivo).strip()
                              else "nessun motivo indicato")}
    r["updated_at"] = _iso(adesso)
    return {"ok": True, "id": int(req_id), "status": "rejected"}


# ---------------------------------------------------------------------------
# IL TRADER
# ---------------------------------------------------------------------------
@dataclass
class Clic:
    """Un gesto del trader su una scheda, e che cosa ha risposto la RPC."""

    finestra: str
    tipo: str
    azione: str                     # 'approva' | 'ignora'
    req_id: int
    opp_key: str
    quando: float
    esito: Dict[str, Any]
    prezzo_visto: Optional[float] = None
    prezzi_gambe: Optional[Dict[str, float]] = None
    lato: str = ""
    sids: Tuple[int, ...] = ()
    rilevazione_attiva: bool = True    # il finto la rilevava ancora al clic?
    giudicato: bool = False

    @property
    def ok(self) -> bool:
        return bool(self.esito.get("ok"))


class TraderProposte:
    """Il trader della Control Room: una decisione per finestra, prima del giro."""

    def __init__(self, piano: Piano, opps_state: Optional[Dict[str, Any]] = None) -> None:
        self.piano = piano
        # lo stato delle opportunita' del SERVIZIO (in produzione `_OPPS_STATE`):
        # per un'anomalia, "rilevata" vuol dire presente in
        # `opps_state['anomalies']`, cioe' in cio' che il servizio sa, non nel
        # piano del finto (con le quote ferme `detect` non viene richiamato)
        self.opps_state = opps_state if opps_state is not None else {}
        self.clic: List[Clic] = []
        self._fatto: Dict[str, str] = {}          # finestra -> ultimo gesto
        self._foto: Dict[int, Any] = {}            # req_id -> prezzo(i) della fotografia

    def rilevata(self, f: Finestra, adesso: float) -> bool:
        """L'opportunita' della finestra c'e' ancora per il SERVIZIO?"""
        if f.tipo != "anomaly":
            return self.piano.attiva(f, adesso)
        sids = self.piano.sid.get(f.nome) or ()
        for lista in (self.opps_state.get("anomalies") or {}).values():
            for a in lista or []:
                if (isinstance(a, dict) and sids and _int(a.get("selection_id")) == sids[0]
                        and str(a.get("side")) == f.lato):
                    return True
        return False

    def _richiesta_di(self, db: Any, f: Finestra) -> Optional[Dict[str, Any]]:
        """La scheda della finestra: quella VIVA se c'e', altrimenti la prima."""
        trovate = self._richieste_di(db, f)
        viva = next((r for r in trovate if str(r.get("status")) == "proposed"), None)
        return viva if viva is not None else (trovate[0] if trovate else None)

    def _richieste_di(self, db: Any, f: Finestra) -> List[Dict[str, Any]]:
        sids = self.piano.sid.get(f.nome)
        if not sids:
            return []
        out: List[Dict[str, Any]] = []
        for r in _coda(db):
            p = r.get("payload") or {}
            if not p.get("opp_key") or str(r.get("kind")) != "place":
                continue
            if f.tipo == "combo":
                if str(p.get("kind")) != "combo":
                    continue
                legs = [int(l.get("selection_id")) for l in (p.get("legs") or [])
                        if isinstance(l, dict) and l.get("selection_id") is not None]
                if sorted(legs) == sorted(sids):
                    out.append(r)
                continue
            if (str(p.get("kind")) == f.tipo and str(p.get("side")) == f.lato
                    and _int(p.get("selection_id")) == int(sids[0])):
                out.append(r)
        return out

    def agisci(self, db: Any, riga: Optional[Dict[str, Any]], adesso: float) -> None:
        for f in self.piano.finestre:
            if f.azione == "niente":
                continue
            r = self._richiesta_di(db, f)
            if r is None:
                continue
            rid = int(r["id"])
            p = r.get("payload") or {}
            if rid not in self._foto:
                self._foto[rid] = ([l.get("price") for l in (p.get("legs") or [])]
                                   if f.tipo == "combo" else p.get("price"))
            fatto = self._fatto.get(f.nome)
            eta = adesso - float(_ts(r.get("created_at")) or adesso)
            stato = str(r.get("status"))
            if f.azione == "ignora":
                if fatto is None and stato == "proposed" and eta >= f.dopo_s:
                    self._registra(f, r, adesso, "ignora", rpc_ignora(
                        db, rid, adesso, "scheda rifiutata dal trader del banco"))
                    self._fatto[f.nome] = "ignora"
                elif fatto == "ignora" and eta >= f.dopo_s + RITARDO_CLIC_DOPO_RIFIUTO_S:
                    # il trader ci ripensa e preme PIAZZA su una scheda rifiutata
                    self._approva(db, f, r, riga, adesso, "vivo")
                    self._fatto[f.nome] = "approva-dopo-rifiuto"
                continue
            if fatto is not None:
                continue
            if f.quando == "eta":
                if stato == "proposed" and eta >= f.dopo_s:
                    self._approva(db, f, r, riga, adesso, "vivo")
            elif f.quando == "deriva":
                if stato != "proposed":
                    continue
                foto = _num(self._foto.get(rid))
                vivo = prezzo_in_riga(riga, _int(p.get("selection_id")), f.lato)
                from Betfair.safe_strategy import proposte_opportunita as PO

                mosso = (foto is not None and vivo is not None
                         and abs(vivo - foto) / foto * 100.0 > PO.SLIPPAGE_PCT_DEFAULT)
                if mosso or eta >= f.dopo_s:
                    self._approva(db, f, r, riga, adesso, "fotografia")
            elif f.quando == "dopo_decadenza":
                if stato == "rejected" and (r.get("result") or {}).get("decaduta"):
                    self._approva(db, f, r, riga, adesso, "vivo")
            elif f.quando == "dopo_sparizione":
                if stato == "proposed" and not self.rilevata(f, adesso):
                    self._approva(db, f, r, riga, adesso, "vivo")

    def _approva(self, db: Any, f: Finestra, r: Dict[str, Any],
                 riga: Optional[Dict[str, Any]], adesso: float, fonte: str) -> None:
        rid = int(r["id"])
        p = r.get("payload") or {}
        if f.tipo == "combo":
            legs = [l for l in (p.get("legs") or []) if isinstance(l, dict)]
            foto = self._foto.get(rid) or []
            prezzi: Dict[str, float] = {}
            for i, l in enumerate(legs):
                v = (prezzo_in_riga(riga, l.get("selection_id"), str(l.get("side")))
                     if fonte == "vivo" else _num(foto[i] if i < len(foto) else None))
                if v is None:
                    v = _num(l.get("price"))
                if v is not None:
                    prezzi[str(i)] = float(v)
            esito = rpc_approva(db, rid, adesso, prezzi_gambe=prezzi)
            self._registra(f, r, adesso, "approva", esito, prezzi_gambe=prezzi)
        else:
            v = (prezzo_in_riga(riga, _int(p.get("selection_id")), f.lato)
                 if fonte == "vivo" else _num(self._foto.get(rid)))
            if v is None:
                v = _num(p.get("price"))
            esito = rpc_approva(db, rid, adesso, prezzo=v)
            self._registra(f, r, adesso, "approva", esito, prezzo=v)
        self._fatto[f.nome] = self._fatto.get(f.nome) or "approva"

    def _registra(self, f: Finestra, r: Dict[str, Any], adesso: float, azione: str,
                  esito: Dict[str, Any], *, prezzo: Optional[float] = None,
                  prezzi_gambe: Optional[Dict[str, float]] = None) -> None:
        p = r.get("payload") or {}
        self.clic.append(Clic(
            finestra=f.nome, tipo=f.tipo, azione=azione, req_id=int(r["id"]),
            opp_key=str(p.get("opp_key") or ""), quando=float(adesso), esito=dict(esito),
            prezzo_visto=prezzo, prezzi_gambe=prezzi_gambe, lato=f.lato,
            sids=tuple(self.piano.sid.get(f.nome) or ()),
            rilevazione_attiva=self.rilevata(f, adesso)))


# ---------------------------------------------------------------------------
# LA SORVEGLIANZA (controlli PM)
# ---------------------------------------------------------------------------
_RE_ID_RIGA = re.compile(r"-t(\d+)$")


def _sollecita(soll: Optional[Dict[str, int]], cod: str, n: int = 1) -> None:
    if soll is not None and n > 0:
        soll[cod] = int(soll.get(cod, 0)) + int(n)


def _prezzo_chiesto(t: Dict[str, Any], mercato: Any) -> Optional[float]:
    """Il prezzo con cui l'ordine e' stato CHIESTO a mercato: quello dell'ordine
    VERO su flumine (`ref ...-t<id>`) se esiste, altrimenti quello registrato
    dall'esecuzione (`meta.esecuzione.price_richiesto`), altrimenti la riga."""
    tid = int(t.get("id") or 0)
    ordini = getattr(mercato, "ordini", None)
    if isinstance(ordini, dict):
        for ref, o in ordini.items():
            m = _RE_ID_RIGA.search(str(ref))
            if m and int(m.group(1)) == tid:
                ot = getattr(o, "order_type", None)
                v = _num(getattr(ot, "price", None))
                if v is not None:
                    return v
    es = (t.get("meta") or {}).get("esecuzione") if isinstance(t.get("meta"), dict) else None
    v = _num((es or {}).get("price_richiesto")) if isinstance(es, dict) else None
    return v if v is not None else _num(t.get("price"))


def modalita_attesa(control_mode: str, params_grezzi: Dict[str, Any]) -> str:
    """La modalita' di una proposta secondo la REGOLA SCRITTA (17/09), ricalcolata
    qui senza `bot_service.modalita_di_strategia`: servizio LIVE e
    `strategy_modes.model == 'live'` -> live; qualunque altra cosa -> paper."""
    if str(control_mode).lower() != "live":
        return "paper"
    sm = (params_grezzi or {}).get("strategy_modes")
    return "live" if isinstance(sm, dict) and str(sm.get("model") or "").lower() == "live" \
        else "paper"


class Sorveglianza:
    """I controlli PM, a fine giro, sul DB in memoria e sugli ordini di flumine."""

    def __init__(self, trader: TraderProposte) -> None:
        self.trader = trader
        self._trade_visti: set = set()
        self._req_modo_visti: set = set()
        self._req_pm4_visti: set = set()
        self._attivita_lette = 0
        self._gia_dette: set = set()
        self.esiti: Counter = Counter()

    def verifica(self, *, db: Any, mercato: Any, riga: Optional[Dict[str, Any]],
                 sollecitati: Optional[Dict[str, int]]) -> List[Tuple[str, str, str]]:
        out: List[Tuple[str, str, str]] = []

        def viol(cod: str, det: str) -> None:
            # lo STESSO difetto (stesso codice, stesso dettaglio) si dice una
            # volta: una proposta doppia che resta li' non e' un difetto a giro
            if (cod, det) in self._gia_dette:
                return
            self._gia_dette.add((cod, det))
            out.append((cod, regola(cod), det))

        coda = _coda(db)
        trades = list(getattr(db, "trades", []) or [])
        control = dict(getattr(db, "control", {}) or {})
        params_grezzi = control.get("params") if isinstance(control.get("params"), dict) else {}
        control_mode = str(control.get("mode") or "paper")
        clic_ok = [c for c in self.trader.clic if c.azione == "approva" and c.ok]
        chiavi_ok = {c.opp_key for c in clic_ok}

        # PM2 - mai due proposte vive identiche, mai una scrittura respinta
        vive = Counter(str((r.get("payload") or {}).get("opp_key") or "") for r in coda
                       if str(r.get("status")) == "proposed"
                       and (r.get("payload") or {}).get("opp_key"))
        if vive:
            _sollecita(sollecitati, "PM2")
        for k, n in vive.items():
            if n > 1:
                viol("PM2", f"{n} proposte VIVE con lo stesso opp_key {k}")
        att = list(getattr(db, "attivita", []) or [])
        for k, p, _e in att[self._attivita_lette:]:
            if k == "error" and str((p or {}).get("reason") or "") in (
                    "proposta_opportunita_fallita", "proposta_opportunita_aggiorna_fallita"):
                viol("PM2", f"scrittura di proposta respinta dal DB: {p.get('err')}")
        self._attivita_lette = len(att)

        # PM1 - ogni riga di modello nasce da un PIAZZA del trader
        for t in trades:
            tid = int(t.get("id") or 0)
            if tid in self._trade_visti:
                continue
            meta = t.get("meta") if isinstance(t.get("meta"), dict) else {}
            di_modello = (str(t.get("strategy") or "") == "model" or bool(meta.get("opp_key"))
                          or bool(meta.get("da_proposta")))
            if not di_modello or t.get("closes_trade_id") is not None:
                continue
            self._trade_visti.add(tid)
            _sollecita(sollecitati, "PM1")
            chiave = str(meta.get("opp_key") or "")
            if str(t.get("origin") or "") == "auto":
                viol("PM1", f"riga #{tid} di modello con origin='auto' (kind "
                            f"{meta.get('kind')}): partita SENZA approvazione")
            elif not chiave or chiave not in chiavi_ok:
                viol("PM1", f"riga #{tid} di modello senza un PIAZZA del trader "
                            f"(opp_key={chiave or '-'})")

        # PM5 - la modalita' della proposta e' quella scritta
        atteso = modalita_attesa(control_mode, params_grezzi)
        for r in coda:
            p = r.get("payload") or {}
            rid = int(r.get("id") or 0)
            if not p.get("opp_key") or rid in self._req_modo_visti:
                continue
            self._req_modo_visti.add(rid)
            _sollecita(sollecitati, "PM5")
            if str(p.get("mode") or "") != atteso:
                viol("PM5", f"proposta #{rid} in modalita' {p.get('mode')} ma la "
                            f"regola scritta dice {atteso}")

        # le approvazioni ESEGUITE in questo giro: PM3, PM5 (riga), PM6, PM7, PM8
        for c in clic_ok:
            if c.giudicato:
                continue
            r = _riga_coda(db, c.req_id)
            if r is None or str(r.get("status")) in ("pending", "processing"):
                continue
            c.giudicato = True
            res = r.get("result") if isinstance(r.get("result"), dict) else {}
            p = r.get("payload") or {}
            nate = [t for t in trades
                    if str(((t.get("meta") or {}) if isinstance(t.get("meta"), dict)
                            else {}).get("opp_key") or "") == c.opp_key
                    and t.get("closes_trade_id") is None
                    and (_ts(t.get("placed_at")) or c.quando) >= c.quando - 1e-6]
            motivo = str(res.get("reason") or res.get("error") or res.get("rejected") or "")
            self.esiti[f"{c.finestra}:{'ordine' if nate else (motivo or 'nessun_ordine')}"] += 1
            # PM7 - l'approvazione non si perde per l'eta' della PROPOSTA
            _sollecita(sollecitati, "PM7")
            if motivo == "richiesta_scaduta":
                eta_prop = c.quando - float(_ts(r.get("created_at")) or c.quando)
                viol("PM7", f"proposta #{c.req_id} (finestra {c.finestra}) approvata "
                            f"con clic FRESCO ma rifiutata 'richiesta_scaduta' "
                            f"(age_s={res.get('age_s')}: e' l'eta' della PROPOSTA, "
                            f"{eta_prop:.0f} s, non del clic) - bot_service.py:2045")
            # PM5 - la riga nata ha la modalita' della proposta
            for t in nate:
                if str(t.get("mode") or "") != str(p.get("mode") or ""):
                    viol("PM5", f"riga #{t.get('id')} in {t.get('mode')} da una "
                                f"proposta in {p.get('mode')}")
            # PM6 - anomalia sparita prima del clic
            if c.tipo == "anomaly" and not c.rilevazione_attiva:
                _sollecita(sollecitati, "PM6")
                if nate:
                    viol("PM6", f"anomalia (finestra {c.finestra}) SPARITA dal "
                                f"rilevamento prima del clic, eppure {len(nate)} "
                                f"ordine/i: bot_service.py:2262-2286 con price_visto "
                                f"non ricontrolla l'anomalia")
            # PM3 - prezzo visto
            if c.prezzo_visto is not None and c.tipo != "combo":
                _sollecita(sollecitati, "PM3")
                vivo = prezzo_in_riga(riga, c.sids[0] if c.sids else None, c.lato)
                soglia = self._soglia(p)
                fuori = (vivo is None or abs(vivo - c.prezzo_visto) / c.prezzo_visto
                         * 100.0 > soglia)
                if fuori and nate:
                    viol("PM3", f"proposta #{c.req_id}: prezzo visto {c.prezzo_visto} "
                                f"e mercato {vivo} oltre {soglia}% eppure ordine #"
                                f"{nate[0].get('id')}")
                if (not fuori) and motivo == "prezzo_visto_fuori_tolleranza":
                    viol("PM3", f"proposta #{c.req_id}: prezzo visto {c.prezzo_visto} "
                                f"e mercato {vivo} ENTRO {soglia}% ma rifiutata "
                                f"fuori tolleranza")
                for t in nate:
                    chiesto = _prezzo_chiesto(t, mercato)
                    if chiesto is None or abs(chiesto - c.prezzo_visto) > 1e-6:
                        viol("PM3", f"riga #{t.get('id')} chiesta a {chiesto}, il "
                                    f"trader aveva visto {c.prezzo_visto}")
            if c.tipo == "combo":
                self._combo(c, p, res, nate, riga, mercato, params_grezzi,
                            sollecitati, viol)

        # PM4 - scaduta, decaduta, rifiutata, clic a vuoto = nessun ordine
        for c in self.trader.clic:
            if c.ok and c.azione == "approva":
                continue
            chiave = c.opp_key
            if ("clic", c.req_id, c.quando) not in self._req_pm4_visti:
                self._req_pm4_visti.add(("clic", c.req_id, c.quando))
                _sollecita(sollecitati, "PM4")
            if chiave not in chiavi_ok:
                orfane = [t for t in trades if str(((t.get("meta") or {})
                          if isinstance(t.get("meta"), dict) else {}).get("opp_key")
                          or "") == chiave and t.get("closes_trade_id") is None]
                if orfane:
                    viol("PM4", f"{len(orfane)} ordine/i sulla chiave {chiave} senza "
                                f"un PIAZZA riuscito ({c.azione} -> {c.esito})")
        for r in coda:
            p = r.get("payload") or {}
            res = r.get("result") if isinstance(r.get("result"), dict) else {}
            if str(r.get("status")) != "rejected" or not p.get("opp_key"):
                continue
            rid = int(r.get("id") or 0)
            if ("req", rid) not in self._req_pm4_visti:
                self._req_pm4_visti.add(("req", rid))
                _sollecita(sollecitati, "PM4")
            chiave = str(p.get("opp_key"))
            if chiave not in chiavi_ok:
                orfane = [t for t in trades if str(((t.get("meta") or {})
                          if isinstance(t.get("meta"), dict) else {}).get("opp_key")
                          or "") == chiave and t.get("closes_trade_id") is None]
                if orfane:
                    viol("PM4", f"proposta #{rid} {'rifiutata' if res.get('ignorata_dall_utente') else 'decaduta'} "
                                f"ma {len(orfane)} ordine/i sulla sua chiave")
            if res.get("ignorata_dall_utente"):
                # l'istante del RIFIUTA e' quello del clic del trader (la riga
                # si ritocca dopo: `marca_proposta_opportunita_annotata`
                # riscrive `updated_at` nello stesso giro della riproposta)
                t_rif = min([c.quando for c in self.trader.clic
                             if c.azione == "ignora" and c.req_id == rid]
                            or [_ts(r.get("updated_at")) or 0.0])
                riproposte = [x for x in coda if int(x.get("id") or 0) != rid
                              and str((x.get("payload") or {}).get("opp_key") or "") == chiave
                              and (_ts(x.get("created_at")) or 0.0) >= t_rif]
                for x in riproposte:
                    # una violazione per riproposta, non una per giro
                    if ("riproposta", rid, int(x.get("id") or 0)) in self._req_pm4_visti:
                        continue
                    self._req_pm4_visti.add(("riproposta", rid, int(x.get("id") or 0)))
                    viol("PM4", f"proposta #{rid} RIFIUTATA dal trader e riproposta "
                                f"come #{x.get('id')}")
        return out

    @staticmethod
    def _soglia(p: Dict[str, Any]) -> float:
        from Betfair.safe_strategy import proposte_opportunita as PO

        v = _num(p.get("slippage_pct"))
        return v if v is not None and v > 0 else float(PO.SLIPPAGE_PCT_DEFAULT)

    def _combo(self, c: Clic, p: Dict[str, Any], res: Dict[str, Any],
               nate: List[Dict[str, Any]], riga: Optional[Dict[str, Any]], mercato: Any,
               params_grezzi: Dict[str, Any], sollecitati: Optional[Dict[str, int]],
               viol: Callable[[str, str], None]) -> None:
        legs = [l for l in (p.get("legs") or []) if isinstance(l, dict)]
        # PM8 - tutte o nessuna alla riserva, ognuna nel tetto
        _sollecita(sollecitati, "PM8")
        if nate and len(nate) != len(legs):
            viol("PM8", f"combo #{c.req_id}: {len(nate)} gambe riservate su {len(legs)}")
        from Betfair.safe_strategy import bot_service as BS

        cap = _num(BS.resolve_params(params_grezzi).get("max_liability_per_trade")) or 0.0
        for t in nate:
            liab = _num(t.get("liability")) or 0.0
            if cap > 0 and liab > cap + 1e-9:
                viol("PM8", f"gamba #{t.get('id')} con responsabilita' {liab} oltre "
                            f"il tetto {cap}")
        # PM3 - ogni gamba al suo prezzo visto, e solo entro tolleranza
        if not c.prezzi_gambe:
            return
        _sollecita(sollecitati, "PM3")
        soglia = self._soglia(p)
        fuori = False
        for i, l in enumerate(legs):
            pv = _num(c.prezzi_gambe.get(str(i)))
            vivo = prezzo_in_riga(riga, l.get("selection_id"), str(l.get("side")))
            if pv is None or vivo is None or abs(vivo - pv) / pv * 100.0 > soglia:
                fuori = True
        if fuori and nate:
            viol("PM3", f"combo #{c.req_id}: una gamba oltre tolleranza eppure "
                        f"{len(nate)} gambe riservate")
        for t in nate:
            sid = _int(t.get("selection_id"))
            i = next((j for j, l in enumerate(legs) if _int(l.get("selection_id")) == sid), None)
            pv = _num(c.prezzi_gambe.get(str(i))) if i is not None else None
            chiesto = _prezzo_chiesto(t, mercato)
            if pv is None or chiesto is None or abs(chiesto - pv) > 1e-6:
                viol("PM3", f"gamba #{t.get('id')} chiesta a {chiesto}, visto {pv}")


# ---------------------------------------------------------------------------
# IL PACCO per il replay
# ---------------------------------------------------------------------------
class BancoProposte:
    """Tutto cio' che uno scenario PM monta: piano, finti, trader, sorveglianza."""

    def __init__(self, scenario: str, sport: str, orologio: Callable[[], float]) -> None:
        from Betfair.safe_strategy import opportunity as OP

        self.scenario = scenario
        self.sport = sport
        self.piano = Piano(finestre_di(scenario, sport), orologio)
        self.opp_mod = OP                          # il modulo VERO
        self.modello = (_classe_modello_calcio()(None, piano=self.piano)
                        if sport == "calcio" else None)
        self.anomalie = AnomalieReplay(self.piano)
        self.combos = CombosReplay(self.piano)
        self.tennis = (types.SimpleNamespace(
            TennisOpportunityModel=_classe_modello_tennis(self.piano))
            if sport == "tennis" else None)
        # lo stato delle opportunita' vive QUANTO IL PROCESSO (in produzione
        # `_OPPS_STATE`): throttle `opps_interval_s`, hash, cache lambda
        self.opps_state: Dict[str, Any] = {}
        self.trader = TraderProposte(self.piano, self.opps_state)
        self.sorveglianza = Sorveglianza(self.trader)

    def extra_mods(self) -> Dict[str, Any]:
        if self.sport == "calcio":
            return {"anomaly": self.anomalie, "combos": self.combos, "tennis": None}
        return {"anomaly": None, "combos": None, "tennis": self.tennis}

    def riepilogo(self, db: Any) -> List[str]:
        coda = [r for r in _coda(db) if (r.get("payload") or {}).get("opp_key")]
        stati = Counter(str(r.get("status")) for r in coda)
        decadute = sum(1 for r in coda if (r.get("result") or {}).get("decaduta"))
        rifiutate = sum(1 for r in coda if (r.get("result") or {}).get("ignorata_dall_utente"))
        esiti = Counter(str((r.get("result") or {}).get("reason")
                            or (r.get("result") or {}).get("error")
                            or ("ok" if (r.get("result") or {}).get("ok") else ""))
                        for r in coda if str(r.get("status")) in ("done", "error", "rejected")
                        and not (r.get("result") or {}).get("decaduta")
                        and not (r.get("result") or {}).get("ignorata_dall_utente"))
        nate = [t for t in getattr(db, "trades", []) or []
                if isinstance(t.get("meta"), dict) and t["meta"].get("opp_key")]
        righe = [
            f"[PROPOSTE] scenario={self.scenario} sport={self.sport} | t0 del piano="
            f"{_iso(self.piano.t0) if self.piano.t0 else '-'} | emesse dal finto "
            f"{dict(self.piano.emesse)} | richieste di proposta {len(coda)} per stato "
            f"{dict(stati)} (decadute {decadute}, rifiutate dal trader {rifiutate}) | "
            f"esiti delle approvazioni {dict(esiti)} | righe nate da proposta "
            f"{len(nate)} {[(t.get('id'), t.get('status'), t.get('mode'), t.get('price')) for t in nate]}",
            "[PROPOSTE] clic del trader: " + (" | ".join(
                f"{c.finestra}/{c.tipo} {c.azione} #{c.req_id} a t0+"
                f"{(c.quando - (self.piano.t0 or c.quando)):.0f}s visto="
                f"{c.prezzo_visto if c.prezzi_gambe is None else c.prezzi_gambe} "
                f"rilevata={c.rilevazione_attiva} -> ok={c.ok}"
                for c in self.trader.clic) or "nessuno"),
            "[PROPOSTE] esito per finestra: " + (", ".join(
                f"{k} x{n}" for k, n in sorted(self.sorveglianza.esiti.items())) or "-"),
        ]
        mai = [f.nome for f in self.piano.finestre if not self.piano.emesse.get(f.nome)]
        if mai:
            righe.append(f"[PROPOSTE] finestre MAI emesse (nessun prezzo sulla riga "
                         f"nel momento previsto): {mai}")
        return righe
