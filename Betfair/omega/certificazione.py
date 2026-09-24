"""CERTIFICAZIONE DI OMEGA — rispetta le regole per cui e' stato progettato?

Non si misura se GUADAGNA. Si misura se **si comporta come dice la Costituzione**
(`Betfair/omega/COSTITUZIONE_OMEGA.md`), giro per giro, sui dati veri di una
partita registrata (banco comune, `Betfair/stream/backtest/banco_comune.py`).

COME E' AGGANCIATO. Omega non ha una `decide` unica come Mike: la condotta si
osserva in quattro punti del SERVIZIO VERO, che il replay avvolge senza
cambiarne una riga (`Betfair/omega/tools/replay_registrazioni.py`):

  * `omega_service._model_select`  -> la SELEZIONE di una gamba (o il motivo
    per cui non si entra): famiglia A;
  * `omega_service._size_and_place`-> il target e il dimensionamento: famiglia B/C;
  * `omega_service._greenup_decide`-> la decisione di USCITA: famiglia D;
  * `market.place_order_live` e la riga scritta -> il ciclo di vita
    dell'ordine: famiglia J (i difetti del 15/09) e famiglia F.

Ogni controllo qui sotto CITA la regola della Costituzione che difende e
dichiara `quando=` ha davvero un caso da giudicare: «zero violazioni» su un
controllo mai sollecitato non vuol dire «sano», vuol dire «non lo so», e il
referto lo stampa.

Ogni controllo e' CONSERVATIVO: segnala solo quando la violazione e' CERTA. Se
un dato manca, tace — un falso allarme su decine di migliaia di tick rende il
referto inutile (PROCESSO_STANDARD_BOT §6.7: prima di accusare il bot si
esclude che il falso positivo sia del controllo).

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import omega_engine as E


# ---------------------------------------------------------------------------
# il referto
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Violazione:
    """Una regola della Costituzione non rispettata, col contesto per capirla."""

    codice: str                 # es. "A2"
    regola: str                 # la regola, in una riga
    dettaglio: str              # che cosa e' successo davvero
    stato: str = ""             # la fase del servizio quando e' successo
    minuto: Optional[int] = None
    gol: Optional[str] = None   # "H-A"

    def __str__(self) -> str:
        dove = f"[{self.stato}" + (f" {self.minuto}'" if self.minuto is not None else "")
        dove += (f" {self.gol}" if self.gol else "") + "]"
        return f"{self.codice} {dove} {self.regola} -> {self.dettaglio}"


# ---------------------------------------------------------------------------
# il MOMENTO osservato: i dati VERI che il servizio aveva sotto gli occhi
# ---------------------------------------------------------------------------
@dataclass
class Momento:
    """Un istante del servizio, coi suoi dati veri.

    ``tipo`` dice da quale punto della catena arriva: `selezione` | `sizing` |
    `uscita` | `ordine` | `giro`. I controlli guardano solo i tipi che li
    riguardano (vedi `quando=`), e ogni campo e' quello che il SERVIZIO aveva —
    non una ricostruzione di questo file.
    """

    tipo: str
    now: datetime
    params: Dict[str, Any] = field(default_factory=dict)
    event_id: str = ""
    mode: str = "live"

    # --- selezione (hook su `_model_select`) ---
    leg: Optional[str] = None            # 'ht_cs' | 'ft_cs'
    half: bool = False
    state: Any = None                    # M.LiveState (minuto, punteggio, rossi)
    snapshot: Any = None                 # MarketSnapshot della gamba
    sel: Any = None                      # M.ModelSelection scelta (o None)
    audit: Optional[Dict[str, Any]] = None
    motivo: Optional[str] = None         # il `why` dello skip
    size_needed: Optional[float] = None

    # --- sizing e piazzamento (hook su `_size_and_place`) ---
    target: Optional[float] = None
    goal: Optional[float] = None
    realized: Optional[float] = None
    legs_left: Optional[int] = None
    size: Optional[float] = None
    price: Optional[float] = None
    aggregati: Optional[Dict[str, Any]] = None

    # --- uscita (hook su `_greenup_decide`) ---
    trigger: Optional[str] = None
    p_lose: Optional[float] = None
    p_source: Optional[str] = None
    p_modello: Optional[float] = None    # P del modello prima del tetto di mercato
    p_mercato: Optional[float] = None    # P implicita dal back LIQUIDO
    locked: Optional[float] = None
    hold_profit: Optional[float] = None
    loss_if_lose: Optional[float] = None
    distance: Optional[int] = None
    minute: Optional[int] = None
    azione: Optional[str] = None
    perche: Optional[str] = None
    trade: Optional[Dict[str, Any]] = None
    chiusure: Optional[List[Dict[str, Any]]] = None

    # --- ordine (hook sul mercato) ---
    richiesta: Optional[Dict[str, Any]] = None   # market_id/selection_id/price/size/side/ref
    esito: Any = None                            # PlaceResult vero
    righe_ordine: Optional[List[Dict[str, Any]]] = None  # list_current/cleared_orders

    # --- fine giro (dopo `run_once`) ---
    db: Any = None
    stats: Optional[Dict[str, Any]] = None
    esito_giro: Optional[Dict[str, Any]] = None
    attivita: Optional[List[Tuple[str, Dict[str, Any], Any]]] = None
    feed_eta: Optional[float] = None      # eta' VERA della riga di scan, in s
    status_control: str = ""              # `omega_control.status` di questo giro
    posizioni_aperte: int = 0
    # l'utente ha gia' chiuso a mano TUTTE le gambe di questa partita
    cashout_globale: bool = False
    # 16/09 (R9): l'utente ha chiuso la posizione FUORI dall'app, con un ordine
    # suo su Betfair (nel banco: un ref diverso, stesso matching). Vero dal giro
    # in cui quell'ordine si e' ABBINATO; `giri_da_fuori_app` conta i giri
    # passati da allora — il bot ha diritto a qualche giro (la posizione di
    # conto si rilegge alla cadenza `conto_every_s`), non a tutta la partita.
    chiuso_fuori_app: bool = False
    giri_da_fuori_app: Optional[int] = None

    # --- V3 (16/09 sera): il motore nuovo, dietro `strategy_version` ---
    # QUALE MOTORE ha prodotto questo momento. Serve perche' nello scenario `v3`
    # del replay i due motori guardano lo STESSO book e scrivono due momenti
    # distinti: senza questo campo i controlli del v2 giudicherebbero le
    # decisioni del v3 (e viceversa) usando un vocabolario di motivi che non e'
    # il loro. E' un difetto che il primo replay ha trovato davvero: A1 accusava
    # V3 di un motivo "non dichiarato" ('fuori_finestra') che e' dichiaratissimo
    # — solo, in V3.
    motore: str = "v2"                   # 'v2' | 'v3'
    cand: Any = None                     # omega_v3.CandidatoV3 scelto (o None)
    scartati: Optional[List[Tuple[str, str]]] = None   # (nome, perche') degli scarti
    proposta: Any = None                 # omega_v3.PropostaUscita
    trade_id: Any = None
    decided_at: Optional[str] = None     # istante della DECISIONE (non si rinfresca)
    proposed_at: Optional[str] = None    # ultimo aggiornamento della proposta
    # quello che si sapeva delle proposte vive PRIMA di questo momento:
    # trade_id -> {decided_at, proposed_at, profitto}
    proposte_viste: Optional[Dict[str, Dict[str, Any]]] = None
    # 17/09 — lo STATO della riga in coda al momento dell'osservazione
    # ('proposed' | 'pending' | 'processing' | 'done' | 'rejected' | 'error').
    # Serve a G4: una proposta in perdita deve restare una PROPOSTA, cioe' stare
    # ferma in 'proposed' finche' non la firma un essere umano.
    stato_richiesta: Optional[str] = None
    # 17/09 — le proposte APPROVATE dall'utente, e che fine hanno fatto (G3).
    # Una voce per approvazione: {request_id, trade_id, event_id, status,
    # giri_da_approvazione, eseguita, evento_chiuso_dall_utente, exit_kind}
    approvazioni: Optional[List[Dict[str, Any]]] = None

    # ------------------------------------------------------------ comodita'
    @property
    def punteggio(self) -> Optional[str]:
        st = self.state
        if st is not None and getattr(st, "score_home", None) is not None:
            return f"{st.score_home}-{st.score_away}"
        return None

    @property
    def il_minuto(self) -> Optional[int]:
        if self.minute is not None:
            return int(self.minute)
        st = self.state
        m = getattr(st, "minute", None) if st is not None else None
        return int(m) if m is not None else None


Controllo = Callable[[Momento], Optional[str]]
Quando = Callable[[Momento], bool]

_REGISTRO: List[Tuple[str, str, Controllo, Optional[Quando]]] = []


def _controllo(codice: str, regola: str, quando: Optional[Quando] = None):
    """Registra un controllo e dichiara QUANDO ha davvero un caso.

    Senza `quando` un referto «zero violazioni» e' ambiguo: non si distingue un
    controllo che ha guardato e approvato da uno che non ha mai avuto
    l'occasione di guardare. Sono due cose diversissime — la prima e' una
    garanzia, la seconda e' un buco.
    """
    def _reg(fn: Controllo) -> Controllo:
        _REGISTRO.append((codice, regola, fn, quando))
        return fn
    return _reg


# ---------------------------------------------------------------------------
# utilita' comuni ai controlli
# ---------------------------------------------------------------------------
_CAMEL_VIETATE = ("customerOrderRef", "sizeMatched", "averagePriceMatched",
                  "sizeRemaining", "betId", "marketId", "selectionId",
                  "sizeCancelled", "orderStatus")

# i motivi di skip che il servizio dichiara (uno per ogni ramo di non ingresso).
# Un motivo fuori da questo elenco vuol dire che una gamba e' saltata per una
# ragione che non e' stata scritta da nessuna parte: e' il buco che §14.2
# ("due gambe SEMPRE") vieta.
MOTIVI_DICHIARATI = frozenset({
    "no_model_lambdas", "no_runner_by_model", "no_market", "no_live_state",
    "no_legs_remaining", "target_zero", "insufficient_liquidity",
    "max_open_liability", "market_not_open", "market_suspended",
    "market_closed", "market_inactive",
})

# le fonti ammesse della catena lambda (§14.2): fixture -> lambda persistiti
# sull'evento -> quote 1X2 pre-KO -> trade precedente -> mercato (griglia /
# O-U live). Sono le stringhe VERE che `omega_service._prematch_lambdas`
# (`:591-715`) e `_saved_event_lambdas` (`:566`) mettono in `lambda_source`; una
# fonte fuori elenco significa che il bot ha deciso su numeri che in produzione
# non avrebbe. Il prefisso `saved_stale:` marca un lambda persistito oltre il
# TTL, ed e' una fonte legittima di ULTIMA risorsa (§14.2, audit M-12).
FONTI_LAMBDA = frozenset({"fixture", "pre_ko_odds", "market_grid", "live_ou",
                          "saved"})


def _fonte_ammessa(fonte: str) -> bool:
    nome = str(fonte or "")
    if nome.startswith("saved_stale:"):
        nome = nome.split(":", 1)[1]
    return nome in FONTI_LAMBDA


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _distanza(nome: Optional[str], state: Any) -> Optional[int]:
    """Gol AGGIUNTIVI che servono perche' il risultato bancato si avveri.
    None quando non e' una scoreline o manca lo stato: non si giudica."""
    par = E.parse_scoreline(str(nome or "")) if nome else None
    if par is None or state is None:
        return None
    sh = getattr(state, "score_home", None)
    sa = getattr(state, "score_away", None)
    if sh is None or sa is None:
        return None
    if par[0] < int(sh) or par[1] < int(sa):
        return None                     # gia' impossibile: non e' una distanza
    return (par[0] - int(sh)) + (par[1] - int(sa))


# ===========================================================================
# A. LE DUE GAMBE E LA SELEZIONE (§11, §14.2, §15)
# ===========================================================================
@_controllo("A1", "una gamba che non parte lascia SEMPRE scritto il perche' "
                  "(§14.2: due gambe sempre, il 10/09 la 2T non parti' mai)",
            quando=lambda m: m.tipo == "selezione" and m.sel is None
            and m.motore != "v3")
def _a1(m: Momento) -> Optional[str]:
    motivo = str(m.motivo or "").strip()
    if not motivo:
        return f"gamba '{m.leg}' saltata senza motivo dichiarato"
    if motivo not in MOTIVI_DICHIARATI:
        return (f"gamba '{m.leg}' saltata con un motivo non dichiarato: "
                f"'{motivo}' (dichiarati: {sorted(MOTIVI_DICHIARATI)})")
    return None


@_controllo("A2", "mai il punteggio CORRENTE ne' un risultato piu' vicino di "
                  "`model_min_goal_distance` gol (§11: il bug del v1, -93,87 EUR il 09/09)",
            quando=lambda m: m.tipo == "selezione" and m.sel is not None)
def _a2(m: Momento) -> Optional[str]:
    minimo = int(m.params.get("model_min_goal_distance") or 0)
    if minimo <= 0:
        return None
    d = _distanza(getattr(m.sel, "name", None), m.state)
    if d is None:
        return None                     # aggregato o stato assente: non si giudica
    if d == 0:
        return (f"banca il PUNTEGGIO CORRENTE {getattr(m.sel, 'name', '?')} "
                f"(gamba {m.leg}): e' esattamente il difetto del v1")
    if d < minimo:
        return (f"banca '{getattr(m.sel, 'name', '?')}' a {d} gol dal punteggio "
                f"corrente, col minimo a {minimo} (gamba {m.leg})")
    return None


@_controllo("A3", "P del modello entro `model_p_max_pct` e SOTTO la probabilita' "
                  "implicita del mercato (§11)",
            quando=lambda m: m.tipo == "selezione" and m.sel is not None
            and _num(getattr(m.sel, "p_model", None)) is not None)
def _a3(m: Momento) -> Optional[str]:
    p = _num(getattr(m.sel, "p_model", None))
    tetto = _num(m.params.get("model_p_max_pct"))
    if p is None or tetto is None:
        return None
    if p > tetto / 100.0 + 1e-9:
        return (f"P(modello)={p * 100:.3f}% sopra il tetto {tetto:.2f}% "
                f"su '{getattr(m.sel, 'name', '?')}'")
    prezzo = _num(getattr(m.sel, "price", None))
    if prezzo and prezzo > 1.0 and p >= (1.0 / prezzo) - 1e-9:
        return (f"P(modello)={p * 100:.3f}% NON e' sotto la P implicita "
                f"{(100.0 / prezzo):.3f}% (quota {prezzo}): il mercato non la sovrapprezza")
    return None


@_controllo("A4", "quota nella banda [price_min, price_max] e liquidita' almeno "
                  "pari alla size che serve (§3.1-3.2)",
            quando=lambda m: m.tipo == "selezione" and m.sel is not None)
def _a4(m: Momento) -> Optional[str]:
    prezzo = _num(getattr(m.sel, "price", None))
    lo, hi = _num(m.params.get("price_min")), _num(m.params.get("price_max"))
    if prezzo is None:
        return f"selezione '{getattr(m.sel, 'name', '?')}' senza prezzo"
    if lo is not None and hi is not None and not (lo - 1e-9 <= prezzo <= hi + 1e-9):
        return f"quota {prezzo} fuori dalla banda [{lo}, {hi}]"
    if abs(prezzo - E.round_to_tick(prezzo)) > 1e-9:
        return f"quota {prezzo}: non e' un tick valido della scala Betfair"
    disponibile = _num(getattr(m.sel, "lay_size_available", None))
    minima = _num(m.params.get("min_lay_liquidity"))
    if disponibile is not None and minima is not None and disponibile + 1e-9 < minima:
        return (f"liquidita' lay {disponibile} sotto il minimo {minima} "
                f"su '{getattr(m.sel, 'name', '?')}'")
    return None


@_controllo("A5", "la catena lambda dichiara la sua FONTE (§14.2: fixture -> "
                  "evento -> pre-KO -> trade precedente -> mercato)",
            quando=lambda m: m.tipo == "selezione" and isinstance(m.audit, dict)
            and m.audit.get("lambda_source") is not None)
def _a5(m: Momento) -> Optional[str]:
    fonte = str((m.audit or {}).get("lambda_source") or "")
    if not _fonte_ammessa(fonte):
        return (f"lambda da una fonte non dichiarata dalla catena: '{fonte}' "
                f"(ammesse: {sorted(FONTI_LAMBDA)}, piu' 'saved_stale:<fonte>')")
    lam = (m.audit or {}).get("lambda_pre")
    if isinstance(lam, (list, tuple)) and len(lam) == 2:
        for x in lam:
            v = _num(x)
            if v is None or v <= 0:
                return f"lambda pre-match non utilizzabile: {lam} (fonte {fonte})"
    return None


@_controllo("A6", "veto HT->FT: col punteggio ancora quello del 45' la P usata e' "
                  "il MASSIMO fra modello e dati storici (§14.2)",
            quando=lambda m: m.tipo == "selezione" and m.sel is not None
            and isinstance(m.audit, dict) and _num((m.audit or {}).get("p_data")) is not None
            and str(m.params.get("model_empirical", "veto")) == "veto")
def _a6(m: Momento) -> Optional[str]:
    p_data = _num((m.audit or {}).get("p_data"))
    p_sel = _num((m.audit or {}).get("p_selected"))
    if p_sel is None:
        p_sel = _num(getattr(m.sel, "p_model", None))
    if p_data is None or p_sel is None:
        return None
    if p_sel + 1e-9 < p_data:
        return (f"P usata {p_sel * 100:.3f}% piu' bassa della P empirica "
                f"{p_data * 100:.3f}%: il veto dei dati non e' stato applicato "
                f"(gamba {m.leg}, '{getattr(m.sel, 'name', '?')}')")
    tetto = _num(m.params.get("model_p_max_pct"))
    if tetto is not None and p_sel > tetto / 100.0 + 1e-9:
        return (f"P usata {p_sel * 100:.3f}% sopra il tetto {tetto:.2f}% ma la "
                f"gamba e' stata comunque aperta")
    return None


@_controllo("A7", "solo scoreline numeriche: gli aggregati restano fuori se "
                  "`include_aggregate` e' falso (§3.3)",
            quando=lambda m: m.tipo == "selezione" and m.sel is not None
            and not bool(m.params.get("include_aggregate")))
def _a7(m: Momento) -> Optional[str]:
    nome = str(getattr(m.sel, "name", "") or "")
    if not E.is_scoreline(nome):
        return f"selezione non numerica '{nome}' con include_aggregate=False"
    return None


# ===========================================================================
# B. OBIETTIVO DI GIORNATA E TARGET PER GAMBA (§2, §14.2)
# ===========================================================================
@_controllo("B1", "target di GAMBA = (G - R) / gambe ancora piazzabili (§14.2)",
            # SOLO il motore di oggi: in V3 la size NON viene dall'obiettivo di
            # giornata (e' lo stake fisso dell'utente, A9) e un «target di gamba»
            # non esiste — la riga ne porta 0,00. Giudicare V3 con la regola del
            # v2 e' lo stesso falso positivo che A1 aveva gia' avuto il 16/09.
            quando=lambda m: m.tipo == "sizing" and m.motore != "v3"
            and m.target is not None
            and m.goal is not None and m.realized is not None and m.legs_left is not None)
def _b1(m: Momento) -> Optional[str]:
    atteso = E.dynamic_target(float(m.goal), float(m.realized), int(m.legs_left))
    if abs(float(m.target) - atteso) > 0.011:
        return (f"target {float(m.target):.2f} invece di {atteso:.2f} "
                f"(G={m.goal}, R={m.realized:.2f}, gambe residue={m.legs_left})")
    if float(m.target) < 0:
        return f"target negativo {m.target}"
    return None


@_controllo("B2", "la barra della giornata e' coerente: target partita = 2 x target "
                  "gamba, avanzamento mai oltre il 100% (§14.1)",
            quando=lambda m: m.tipo == "giro" and isinstance(m.stats, dict)
            and m.stats.get("target_leg") is not None)
def _b2(m: Momento) -> Optional[str]:
    st = m.stats or {}
    tl, tm = _num(st.get("target_leg")), _num(st.get("target_match"))
    if tl is not None and tm is not None and str(m.params.get("engine", "legs")) == "legs":
        if abs(tm - 2.0 * tl) > 0.011:
            return f"target_match {tm} != 2 x target_leg {tl}"
    pct = _num(st.get("goal_pct"))
    # 17/09 sera (replay 35797769 `cashout-globale`, motore v3): dopo una chiusura
    # in PERDITA il realizzato di giornata e' negativo e la barra sta sotto lo
    # zero (-6,6 %): e' un numero onesto, non un fuori scala. Il fuori scala vero
    # e' un pct negativo SENZA una perdita realizzata, o sopra il 100 %.
    realizzato = _num(st.get("realized_effective"))
    if realizzato is None:
        realizzato = _num(st.get("realized_today"))
    in_perdita = realizzato is not None and realizzato < 0
    if pct is not None and ((pct < 0 and not in_perdita) or pct > 100.0 + 1e-9):
        return f"goal_pct fuori scala: {pct}"
    goal = _num(st.get("goal"))
    if goal is not None and goal <= 0:
        return f"obiettivo di giornata non positivo: {goal}"
    eventi = st.get("events_today")
    gambe = st.get("legs_today")
    if isinstance(eventi, int) and isinstance(gambe, int) and eventi > gambe:
        return (f"partite di oggi {eventi} maggiori delle gambe {gambe}: una "
                f"partita conta almeno una gamba (§14.2)")
    return None


@_controllo("B4", "feed STANTIO (riga oltre `DECISION_MAX_AGE_S`): nessuna "
                  "apertura in quel giro; le uscite restano permesse (§18 patto 2)",
            quando=lambda m: m.tipo == "giro" and m.feed_eta is not None
            and float(m.feed_eta) > 25.0 and str(m.status_control) == "running")
def _b4(m: Momento) -> Optional[str]:
    piazzate = int((m.esito_giro or {}).get("placed") or 0)
    if piazzate:
        return (f"{piazzate} aperture con la riga del feed vecchia di "
                f"{float(m.feed_eta):.0f} s: si decide su prezzi fermi")
    return None


@_controllo("B3", "obiettivo raggiunto (R >= G con `stop_on_goal`): nessuna NUOVA "
                  "apertura (§2)",
            quando=lambda m: m.tipo == "giro" and bool(m.params.get("stop_on_goal"))
            and isinstance(m.stats, dict)
            and (_num(m.stats.get("realized_effective")) is not None
                 or _num(m.stats.get("realized_today")) is not None)
            and (_num(m.stats.get("goal")) or 0.0) > 0.0
            and (_num(m.stats.get("realized_effective"))
                 if _num(m.stats.get("realized_effective")) is not None
                 else _num(m.stats.get("realized_today")))
            >= _num(m.stats.get("goal")))
def _b3(m: Momento) -> Optional[str]:
    """Il freno sta a MONTE (`scan_and_place_legs` esce prima di dimensionare),
    quindi il caso si osserva sul GIRO: obiettivo raggiunto e zero aperture."""
    piazzate = int((m.esito_giro or {}).get("placed") or 0)
    if piazzate:
        st = m.stats or {}
        return (f"{piazzate} aperture con R={st.get('realized_effective')} gia' "
                f"oltre l'obiettivo G={st.get('goal')} e stop_on_goal attivo")
    return None


# ===========================================================================
# C. I CAP DI RISCHIO (§7, §19.5)
# ===========================================================================
@_controllo("C1", "`max_liability_per_match`: la liability della gamba non lo "
                  "supera mai (§2, clamp del sizing)",
            quando=lambda m: m.tipo == "ordine" and m.richiesta is not None
            and (_num(m.params.get("max_liability_per_match")) or 0.0) > 0.0
            and str((m.richiesta or {}).get("side", "lay")).lower() == "lay")
def _c1(m: Momento) -> Optional[str]:
    cap = float(m.params.get("max_liability_per_match"))
    r = m.richiesta or {}
    size, prezzo = _num(r.get("size")), _num(r.get("price"))
    if size is None or prezzo is None:
        return None
    liab = E.liability_from_lay(size, prezzo)
    if liab > cap + 0.011:
        return (f"lay da {size} @ {prezzo} = liability {liab:.2f} col tetto a "
                f"{cap:.2f} (ref {r.get('customer_ref')})")
    return None


@_controllo("C2", "`max_open_liability`: non si apre oltre il capitale impegnato "
                  "ammesso, contando le perdite gia' bloccate (§12, review H1)",
            quando=lambda m: m.tipo == "sizing" and m.size is not None
            and (_num(m.params.get("max_open_liability")) or 0.0) > 0.0
            and isinstance(m.aggregati, dict))
def _c2(m: Momento) -> Optional[str]:
    cap = float(m.params.get("max_open_liability"))
    impegnato = E.open_liability_effective(dict(m.aggregati or {}))
    liab = E.liability_from_lay(float(m.size), float(m.price or 0.0))
    if impegnato + liab > cap + 0.011:
        return (f"apertura da {liab:.2f} con {impegnato:.2f} gia' impegnati e il "
                f"tetto a {cap:.2f}")
    return None


@_controllo("C3", "`daily_loss_cap`: sotto il cap si smette di APRIRE (le uscite "
                  "restano, §12)",
            quando=lambda m: m.tipo == "sizing"
            and (_num(m.params.get("daily_loss_cap")) or 0.0) > 0.0
            and m.realized is not None
            and float(m.realized) <= -float(m.params.get("daily_loss_cap")))
def _c3(m: Momento) -> Optional[str]:
    return (f"apertura con R={float(m.realized):.2f} oltre il cap di perdita "
            f"{float(m.params.get('daily_loss_cap')):.2f}")


@_controllo("C4", "a bot FERMO nessuna apertura, ma settlement, green-up, "
                  "riconciliazione e missioni continuano a girare (§12, I3)",
            quando=lambda m: m.tipo == "giro" and str(m.status_control) not in
            ("running", "") and m.esito_giro is not None)
def _c4(m: Momento) -> Optional[str]:
    esito = m.esito_giro or {}
    if int(esito.get("placed") or 0):
        return (f"{esito.get('placed')} aperture con `status`='{m.status_control}': "
                f"fermare il bot toglie le APERTURE")
    # le fasi di protezione devono essere state ESEGUITE, non saltate: il ramo
    # `status != 'running'` di `run_once` ritorna comunque i loro conteggi
    if "settled" not in esito or "greenup" not in esito:
        return (f"giro a bot fermo senza le fasi di protezione nel risultato "
                f"(chiavi: {sorted(esito)}): una posizione aperta resterebbe "
                f"senza nessuno che la guardi")
    return None


# ===========================================================================
# D. LE USCITE — LE CHIUSURE DISTRUGGONO VALORE (§12, §18.1, §19)
# ===========================================================================
@_controllo("D1", "distanza maggiore di `greenup_trigger_distance`: nessuna "
                  "valutazione di uscita (§19.4)",
            quando=lambda m: m.tipo == "uscita" and m.distance is not None
            and int(m.distance) > int(m.params.get("greenup_trigger_distance") or 0)
            and str(m.trigger or "") == "goal")
def _d1(m: Momento) -> Optional[str]:
    return (f"trigger 'goal' con distanza {m.distance} oltre "
            f"{m.params.get('greenup_trigger_distance')}: due gol di vantaggio "
            f"non si valutano nemmeno")


@_controllo("D2", "MAI chiudere sotto l'EV del tenere: si esce solo se il "
                  "bloccato vale almeno EV(tengo) - margine - premio (§18.1, §19.2)",
            quando=lambda m: m.tipo == "uscita" and str(m.azione or "") == "exit"
            and m.locked is not None and float(m.locked) < 0.0
            and m.p_lose is not None and m.hold_profit is not None)
def _d2(m: Momento) -> Optional[str]:
    """Il metro e' RICOSTRUITO dalla Costituzione, non chiamando la funzione del
    bot: un controllo che chiama il codice che deve giudicare non giudica niente.
    """
    p = min(1.0, max(0.0, float(m.p_lose)))
    perdita = max(0.0, float(m.loss_if_lose if m.loss_if_lose is not None else 0.0))
    ev = round((1.0 - p) * float(m.hold_profit) - p * perdita, 2)
    margine = _num(m.params.get("greenup_ev_margin")) or 0.0
    cap = _num(m.params.get("greenup_risk_cap"))
    cap = 1.0 if cap is None else cap
    pct = _num(m.params.get("greenup_risk_premium_pct")) or 0.0
    premio = 0.0
    if p >= cap:
        if pct >= 1.0:
            return None                 # uscita incondizionata dichiarata dai params
        # §19.2: il premio scala con la frazione di GAMBA gia' giocata
        orizzonte = 45.0 if m.half else 90.0
        minuto = m.il_minuto
        quota = 1.0 if minuto is None else min(1.0, max(0.0, float(minuto) / orizzonte))
        premio = round(perdita * pct * quota, 2)
    soglia = round(ev - margine - premio, 2)
    if float(m.locked) + 1e-9 < soglia:
        return (f"esce a {float(m.locked):+.2f} sotto la soglia {soglia:+.2f} "
                f"(EV(tengo)={ev:+.2f}, margine {margine:.2f}, premio {premio:.2f}, "
                f"P(perdita)={p * 100:.1f}%, minuto {m.il_minuto}): "
                f"la chiusura distrugge valore")
    return None


@_controllo("D3", "in profitto (bloccato >= 0) si esce sempre e subito, a "
                  "qualunque minuto (§19.4)",
            quando=lambda m: m.tipo == "uscita" and m.locked is not None
            and float(m.locked) >= 0.0)
def _d3(m: Momento) -> Optional[str]:
    if str(m.azione or "") != "exit":
        return (f"bloccato {float(m.locked):+.2f} >= 0 ma la decisione e' "
                f"'{m.azione}': un profitto certo si incassa")
    return None


@_controllo("D4", "modello cieco (P non stimabile) e chiusura in perdita: si "
                  "TIENE, mai cristallizzare su un dato che non c'e' (§19.4)",
            quando=lambda m: m.tipo == "uscita" and m.p_lose is None
            and m.locked is not None and float(m.locked) < 0.0)
def _d4(m: Momento) -> Optional[str]:
    if str(m.azione or "") == "exit":
        return (f"esce a {float(m.locked):+.2f} senza P(perdita): non si "
                f"cristallizza una perdita su un dato assente")
    return None


@_controllo("D5", "il tetto di fine gara non alza la P oltre "
                  "`greenup_market_floor_max_ratio` volte il modello: oltre, la "
                  "quota e' rotta, non informazione (§12, trade 84)",
            quando=lambda m: m.tipo == "riserva" and m.p_lose is not None
            and m.p_modello is not None and m.p_mercato is not None
            and (_num(m.params.get("greenup_market_floor_max_ratio")) or 0.0) > 0.0)
def _d5(m: Momento) -> Optional[str]:
    rapporto = float(m.params.get("greenup_market_floor_max_ratio"))
    p_mod, p_mkt, p_fin = float(m.p_modello), float(m.p_mercato), float(m.p_lose)
    if m.distance is not None and int(m.distance) <= 0:
        return None                     # punteggio gia' sul tabellone: tetto sempre valido
    if p_fin <= p_mod + 1e-9:
        return None                     # il tetto non ha alzato niente
    # §12: la tolleranza assoluta (scarti minuscoli) resta lecita
    if p_mkt - p_mod <= 0.05 + 1e-9:
        return None
    if p_fin > p_mod * rapporto + 1e-9:
        return (f"P(perdita) portata a {p_fin * 100:.2f}% dal mercato "
                f"({p_mkt * 100:.2f}%) oltre {rapporto:.1f}x il modello "
                f"({p_mod * 100:.2f}%), fonte '{m.p_source}': tetto non applicato")
    return None


@_controllo("D6", "mai un secondo invio con una chiusura ancora PENDING (§12)",
            quando=lambda m: m.tipo == "uscita" and str(m.azione or "") == "exit"
            and bool(m.chiusure))
def _d6(m: Momento) -> Optional[str]:
    pendenti = [c for c in (m.chiusure or []) if str(c.get("status")) == "pending"]
    if pendenti:
        return (f"nuova uscita mentre {len(pendenti)} chiusure sono ancora "
                f"'pending' (id {[c.get('id') for c in pendenti]})")
    return None


# ===========================================================================
# E. MAI DUE LAY SULLA STESSA SELEZIONE (regola di PIATTAFORMA, ordine
#    dell'utente 16/09: «non devono mai esserci 2 lay a mercato sullo stesso
#    mercato/selezione, se si abbinano siamo scoperti»)
# ===========================================================================
# I `kind` di attivita' che nascono da una DECISIONE dell'automatico. Il
# settlement e la riconciliazione NON sono qui: quelli devono girare anche sulle
# righe manuali (I3, «Betfair e' la verita'»), e fermarli sarebbe un danno.
KIND_DECISIONE_BOT = ("place", "place_parziale", "size_reduced", "greenup",
                      "greenup_hold", "greenup_wait", "greenup_failed",
                      "greenup_blind", "greenup_residual_dropped")


def _e_manuale(riga: Optional[Dict[str, Any]]) -> bool:
    """Una riga dell'UTENTE, non del bot (`omega_trades.origin`)."""
    return str((riga or {}).get("origin") or "auto") == "manual"


def _lay_a_mercato(m: Momento) -> List[Tuple[Tuple[str, int], str, str]]:
    """Ogni lay che in questo istante ESPONE sulla selezione, con la sua identita'.

    Contano TUTTE le gambe, senza distinzione di ruolo: ingresso 1T, ingresso
    2T, green-up, copertura, cash-out. Espongono:
      * gli ordini VIVI su Betfair (`list_current_orders`, EXECUTABLE): possono
        ancora abbinarsi;
      * le righe 'pending' o in riconciliazione: un esito ignoto puo' essere un
        ordine vivo, e §4.11 dice di contarlo nel caso peggiore;
      * le righe 'open'/'hedged': la lay e' GIA' abbinata, e una seconda lay che
        si abbinasse raddoppierebbe la posizione — che e' esattamente il danno
        («se si abbinano siamo scoperti»).

    L'IDENTITA' e' il `customer_order_ref` (`omega-t<id>` per le righe, derivato
    con la funzione vera): serve a non contare due volte lo STESSO ordine, che
    sul book e' vivo e sulla riga e' aperto.

    ⚠️ SOLO LE LAY DEL BOT (ordine dell'utente, 16/09 h18: «il bot gestisce SOLO
    le sue operazioni; quelle manuali sulla stessa partita le ignora»). Una lay
    che l'utente ha piazzato a mano NON e' un ordine del bot e non puo' essere
    contata come un suo duplicato. Il discrimine e' la colonna `origin` della
    riga, non il ref: dal 16/09 (§16 review C1) auto e manuale usano ENTRAMBI
    `omega-t<id>` (`omega_engine.candidate_customer_refs:600`). Un ordine vivo
    il cui ref non si risolve in nessuna riga resta contato come del BOT: e'
    esattamente il difetto 4/6 del 15/09, e nasconderlo sarebbe peggio.
    """
    fuori: List[Tuple[Tuple[str, int], str, str]] = []
    for r in (m.righe_ordine or []):
        if str(r.get("side", "")).lower() != "lay":
            continue
        if str(r.get("status", "")).upper() != "EXECUTABLE":
            continue
        ident = str(r.get("customer_order_ref") or r.get("bet_id") or "?")
        if _e_manuale(_riga_dal_ref(m, ident)):
            continue                    # ordine dell'utente: non e' del bot
        fuori.append(((str(r.get("market_id")), int(r.get("selection_id") or 0)),
                      ident, f"ordine VIVO {ident}"))
    for r in (m.db.trades if m.db is not None else []):
        if str(r.get("side", "")).lower() != "lay" or _e_manuale(r):
            continue
        stato = str(r.get("status"))
        ignoto = bool((r.get("meta") or {}).get("reconciling"))
        if stato not in ("pending", "open", "hedged") and not ignoto:
            continue
        ident = E.customer_ref_for(r.get("id"))
        fuori.append(((str(r.get("market_id")), int(r.get("selection_id") or 0)),
                      ident, f"riga {r.get('id')} {stato}"
                      + (" a esito IGNOTO" if ignoto else "")))
    return fuori


@_controllo("E1", "MAI due lay vive o in volo sullo stesso mercato e selezione: "
                  "se si abbinano entrambe la posizione e' scoperta (regola di "
                  "piattaforma, ordine dell'utente 16/09)",
            quando=lambda m: m.tipo == "giro" and bool(_lay_a_mercato(m)))
def _e1(m: Momento) -> Optional[str]:
    per_selezione: Dict[Tuple[str, int], Dict[str, str]] = {}
    for chiave, ident, origine in _lay_a_mercato(m):
        per_selezione.setdefault(chiave, {})[ident] = origine
    for (mid, sid), voci in per_selezione.items():
        if len(voci) > 1:
            return (f"{len(voci)} lay sulla selezione {sid} del mercato {mid}: "
                    f"{sorted(voci.values())}. Se si abbinano tutte la posizione "
                    f"e' il doppio di quella voluta e la copertura non basta.")
    return None


@_controllo("E2", "una lay non si SOSTITUISCE con cancel + place nello stesso "
                  "giro: fra l'annullo e il nuovo ordine la vecchia puo' "
                  "abbinarsi (regola di piattaforma, 16/09)",
            quando=lambda m: m.tipo == "giro" and any(
                k in ("cancel_richiesto", "cancel_esito")
                for k, _p, _e in (m.attivita or [])))
def _e2(m: Momento) -> Optional[str]:
    """Le attivita' di annullo portano `trade_id` (non mercato e selezione:
    `omega_service._ordine_ancora_vivo:2358`), quindi la selezione si risolve
    dalla riga del database — che e' la stessa cosa, letta dal posto giusto."""
    righe = {int(r.get("id") or 0): r for r in (m.db.trades if m.db is not None else [])}

    def _sel(tid: Any) -> Optional[Tuple[str, int]]:
        r = righe.get(int(tid or 0))
        if r is None or str(r.get("side", "")).lower() != "lay":
            return None
        return (str(r.get("market_id")), int(r.get("selection_id") or 0))

    annullate: Dict[Tuple[str, int], Any] = {}
    for k, p, _e in (m.attivita or []):
        p = p or {}
        chiave = _sel(p.get("trade_id"))
        if chiave is None:
            continue
        if k == "cancel_richiesto":
            annullate[chiave] = p
        elif k in ("place", "place_parziale") and chiave in annullate:
            return (f"lay annullata e ri-piazzata nello stesso giro su "
                    f"{chiave}: fra i due comandi la prima puo' abbinarsi "
                    f"(annullo: {annullate[chiave]})")
    return None


@_controllo("E3", "le operazioni MANUALI dell'utente non entrano nei numeri con "
                  "cui il bot decide, e il bot non decide sulle righe manuali "
                  "(ordine dell'utente 16/09 h18)",
            quando=lambda m: m.tipo == "giro" and m.db is not None
            and any(_e_manuale(r) for r in m.db.trades))
def _e3(m: Momento) -> Optional[str]:
    """DUE cose diverse, e vanno separate.

    (1) I NUMERI. Target di gamba, stop giornaliero, cap di perdita e cap di
        esposizione si calcolano su `omega_db.aggregates` ->
        `omega_engine.aggregate_trades`, che NON filtra per `origin`
        (`omega_engine.py:338`). Se la liability aperta che il bot usa contiene
        anche quella delle righe manuali, le operazioni dell'utente stanno
        muovendo le decisioni del bot.
    (2) LE AZIONI. Il settlement e la riconciliazione devono girare anche sulle
        righe manuali (I3: Betfair e' la verita', e una posizione va regolata
        comunque). Una DECISIONE dell'automatico su una riga manuale, no.
    """
    manuali = [r for r in m.db.trades if _e_manuale(r)]
    esposti = ("open", "pending", "hedged")
    reperti: List[str] = []
    liab_manuale = sum(float(r.get("liability") or 0.0) for r in manuali
                       if str(r.get("status")) in esposti and not r.get("closes_trade_id"))
    st = m.stats or {}
    # DAL 16/09 SONO DUE NUMERI, e devono essere DUE (patch R6):
    #   `open_liability`      = i TOTALI DI PAGINA: tutto quello che c'e' sul
    #                           conto, operazioni dell'utente comprese;
    #   `open_liability_bot`  = quello con cui il BOT DECIDE.
    # Il controllo morde da tutte e due le parti: il bot non deve vedere le
    # manuali, e la pagina non deve NASCONDERLE (un trader che non vede la
    # propria liability e' l'altro modo di sbagliare).
    aperta_pagina = _num(st.get("open_liability"))
    aperta_bot = _num(st.get("open_liability_bot"))
    if liab_manuale > 0.0:
        auto = sum(float(r.get("liability") or 0.0) for r in m.db.trades
                   if not _e_manuale(r) and str(r.get("status")) in esposti
                   and not r.get("closes_trade_id"))
        if aperta_bot is None:
            reperti.append(
                "le stats non dichiarano `open_liability_bot`: non si puo' sapere "
                "su quale liability il bot abbia deciso (patch R6 assente)")
        elif abs(aperta_bot - auto) > 0.011:
            reperti.append(
                f"la liability aperta con cui il bot decide e' {aperta_bot:.2f} ma "
                f"quella delle SUE gambe e' {auto:.2f}: dentro ci sono "
                f"{liab_manuale:.2f} EUR di operazioni MANUALI. Target, cap e "
                f"stop giornaliero si muovono per colpa di ordini che il bot non "
                f"ha fatto (`omega_engine.aggregate_trades:338`, `solo_auto`)")
        if aperta_pagina is not None and abs(aperta_pagina - (auto + liab_manuale)) > 0.011:
            reperti.append(
                f"i totali di PAGINA dicono {aperta_pagina:.2f} ma sul conto ci "
                f"sono {auto + liab_manuale:.2f} EUR ({liab_manuale:.2f} di "
                f"operazioni manuali): la pagina nasconde al trader la sua "
                f"stessa esposizione")
    ids = {int(r.get("id") or 0) for r in manuali}
    decisi = sorted({k for k, p, _e in (m.attivita or [])
                     if k in KIND_DECISIONE_BOT
                     and int((p or {}).get("trade_id") or 0) in ids})
    if decisi:
        reperti.append(
            f"l'automatico ha deciso {decisi} sulle righe MANUALI {sorted(ids)}: "
            f"il green-up gira su TUTTE le aperture lay "
            f"(`omega_service._greenup_candidates:3688` legge `open_trades()` "
            f"senza filtrare `origin`), come prescrive §12 — che pero' ora e' in "
            f"conflitto con l'ordine dell'utente del 16/09 h18")
    return " | ".join(reperti) if reperti else None


@_controllo("E4", "dopo il CASH-OUT GLOBALE dell'utente sulla partita il bot lo "
                  "capisce e NON FA PIU' NIENTE su quella partita (ordine "
                  "dell'utente 16/09 h18)",
            quando=lambda m: m.tipo == "giro" and bool(m.cashout_globale))
def _e4(m: Momento) -> Optional[str]:
    """Il vincolo DURO vale sempre: dopo il cash-out dell'utente il bot non apre
    piu' niente su quella partita.

    Il resto dipende da com'e' andato il cash-out. Se la liquidita' ha cappato il
    fill e resta un RESIDUO, la posizione e' ancora aperta e il bot deve
    continuare a proteggerla: fermarlo li' sarebbe il contrario della
    protezione. Solo quando non resta piu' niente di aperto («partita chiusa
    davvero») il bot non deve fare assolutamente altro.
    """
    esito = m.esito_giro or {}
    if int(esito.get("placed") or 0):
        return (f"{esito.get('placed')} nuove gambe dopo che l'utente aveva "
                f"chiuso a mano tutta la partita")
    if int(m.posizioni_aperte or 0) > 0:
        return None                     # residuo dell'utente: la difesa resta
    if int(esito.get("greenup") or 0):
        return (f"{esito.get('greenup')} chiusure automatiche dopo il cash-out "
                f"globale: la posizione era gia' chiusa dall'utente")
    vivi = [o for _chiave, _id, o in _lay_a_mercato(m)
            if "VIVO" in o or "pending" in o]
    if vivi:
        return f"dopo il cash-out globale restano lay del bot a mercato: {vivi}"
    return None


# quanti giri concediamo al bot per ACCORGERSI di una chiusura fatta fuori
# dall'app. La lettura della posizione di conto ha la sua cadenza
# (`conto_every_s`): con la cadenza a zero (lo scenario la mette a zero) un giro
# basterebbe, ma il primo giro dopo l'abbinamento puo' cadere prima che il
# blotter lo registri. Tre e' generoso e resta severo.
GIRI_PER_ACCORGERSI = 3


@_controllo("E5", "una chiusura fatta dall'UTENTE FUORI DALL'APP (un ordine suo "
                  "su Betfair) il bot la VEDE, e da li' in poi non gestisce piu' "
                  "una posizione che non esiste (ordine dell'utente 16/09 sera)",
            quando=lambda m: m.tipo == "giro" and bool(m.chiuso_fuori_app))
def _e5(m: Momento) -> Optional[str]:
    """Il difetto che questo controllo cerca e' quello pericoloso (R9): il bot
    legge solo i PROPRI ordini, quindi non vede la back che l'utente ha piazzato
    dal sito per chiudere; continua a vedere la propria lay abbinata e, al primo
    trigger, ci mette sopra un green-up — un BACK CON SOLDI VERI su una
    posizione che non c'e' piu'.

    Due cose, in ordine:
      1. ACCORGERSENE. Entro `GIRI_PER_ACCORGERSI` giri deve esserci l'attivita'
         `chiuso_dall_utente`, oppure il marcatore sulla riga
         (`meta.chiuso_dall_utente`): senza, il bot sta gestendo al buio.
      2. NON FARCI PIU' NIENTE. Dal momento in cui lo sa: nessuna decisione
         dell'automatico (`KIND_DECISIONE_BOT`) su quelle righe, nessuna nuova
         gamba sulla partita.
    """
    righe = list(m.db.trades if m.db is not None else [])
    marcate = [r for r in righe if (r.get("meta") or {}).get("chiuso_dall_utente")]
    detto = any(k == "chiuso_dall_utente" for k, _p, _e in (m.attivita or []))
    sa = bool(marcate or detto)
    giri = m.giri_da_fuori_app
    if not sa:
        if giri is not None and giri > GIRI_PER_ACCORGERSI:
            return (f"sono passati {giri} giri da quando l'utente ha chiuso la "
                    f"posizione su Betfair e il bot non se n'e' ancora accorto: "
                    f"sta sorvegliando (e potrebbe coprire) una posizione che non "
                    f"esiste piu'")
        return None
    # ⚠️ SOLO I CONTATORI DI QUESTO GIRO (`esito_giro`), mai la lista delle
    # attivita': quella e' CUMULATIVA, e il `place` che ha aperto la posizione
    # sta li' dentro da prima della chiusura. Accusare il bot per un ordine
    # piazzato mezz'ora prima e' il difetto 16 del catalogo — lo stato
    # persistente letto come corrente — e questo controllo ci era cascato.
    esito = m.esito_giro or {}
    if int(esito.get("placed") or 0):
        return (f"{esito.get('placed')} nuove gambe su una partita che l'utente "
                f"ha chiuso fuori dall'app")
    if int(esito.get("greenup") or 0) and marcate:
        return (f"{esito.get('greenup')} chiusure automatiche dopo che l'utente "
                f"aveva gia' chiuso la posizione fuori dall'app: un back con "
                f"soldi veri su una posizione che non esiste "
                f"(righe {sorted(int(r.get('id') or 0) for r in marcate)})")
    # 3. E NON DEVE RESTARE NIENTE DI VIVO. Un ordine del bot ancora appoggiato
    #    su una partita che l'utente ha chiuso, se si abbina, apre una posizione
    #    NUOVA su una partita che non e' piu' del bot: va annullato (la parte
    #    gia' ABBINATA no — quella e' posizione, e la regola il settlement).
    if giri is not None and giri > GIRI_PER_ACCORGERSI:
        vivi = [o for _chiave, _id, o in _lay_a_mercato(m) if "VIVO" in o]
        if vivi:
            return (f"la partita e' chiusa dall'utente e restano ordini del bot a "
                    f"mercato: {vivi}. Se si abbinano, il bot riapre una posizione "
                    f"su una partita che non e' piu' sua")
    return None


# ===========================================================================
# J. IL CICLO DI VITA DELL'ORDINE — i difetti del 15/09 e la consapevolezza
#    (PROCESSO_STANDARD_BOT §7.1-7.7, C.10/C.12a)
# ===========================================================================
def _riga_dal_ref(m: Momento, ref: str) -> Optional[Dict[str, Any]]:
    """La riga `omega_trades` a cui appartiene un `customer_ref`.

    Il ref NON e' scritto sulla riga: Omega lo DERIVA dall'id
    (`omega_engine.customer_ref_for`, §16 review C1), ed e' proprio questa
    derivazione che la riconciliazione usa per ritrovare l'ordine. Qui si fa la
    stessa cosa, con la stessa funzione: se un giorno il ref cambiasse forma,
    questo controllo smetterebbe di trovare la riga e lo direbbe.
    """
    for r in (m.db.trades if m.db is not None else []):
        if E.customer_ref_for(r.get("id")) == str(ref):
            return r
    return None


def _riga_del_piazzamento(m: Momento) -> Optional[Dict[str, Any]]:
    """La riga che il RESERVE-FIRST ha appena scritto per questo ordine, trovata
    senza passare dal ref (mercato, selezione e lato): serve a giudicare il ref
    stesso, che altrimenti sarebbe l'unica chiave e non si potrebbe mettere in
    discussione."""
    r = m.richiesta or {}
    candidate = [t for t in (m.db.trades if m.db is not None else [])
                 if str(t.get("market_id")) == str(r.get("market_id"))
                 and int(t.get("selection_id") or 0) == int(r.get("selection_id") or 0)
                 and str(t.get("side", "")).lower() == str(r.get("side", "")).lower()]
    return candidate[-1] if candidate else None


@_controllo("J1", "`res.ok`: un place NON riuscito non diventa mai una posizione "
                  "aperta (difetto 2 del 15/09)",
            quando=lambda m: m.tipo == "ordine" and m.esito is not None
            and not (bool(getattr(m.esito, "ok", False))
                     and float(getattr(m.esito, "size_matched", 0.0) or 0.0) > 0.0))
def _j1(m: Momento) -> Optional[str]:
    ref = str((m.richiesta or {}).get("customer_ref") or "")
    r = _riga_dal_ref(m, ref)
    if r is not None and str(r.get("status")) in ("open", "hedged"):
        return (f"place non riuscito (ok={getattr(m.esito, 'ok', None)}, "
                f"abbinato={getattr(m.esito, 'size_matched', None)}) ma la riga "
                f"{r.get('id')} risulta '{r.get('status')}'")
    return None


@_controllo("J2", "`avg_price_matched`: il prezzo confermato e' quello ABBINATO, "
                  "non quello chiesto (difetto 3 del 15/09)",
            quando=lambda m: m.tipo == "ordine" and m.esito is not None
            and bool(getattr(m.esito, "ok", False))
            and _num(getattr(m.esito, "avg_price_matched", None)) is not None
            and _num((m.richiesta or {}).get("price")) is not None
            and abs((_num(getattr(m.esito, "avg_price_matched", None)) or 0.0)
                    - (_num((m.richiesta or {}).get("price")) or 0.0)) > 1e-9)
def _j2(m: Momento) -> Optional[str]:
    abbinato = _num(getattr(m.esito, "avg_price_matched", None))
    r = _riga_dal_ref(m, str((m.richiesta or {}).get("customer_ref") or ""))
    if r is None or str(r.get("status")) not in ("open", "hedged"):
        return None
    scritto = _num(r.get("price"))
    if scritto is not None and abs(scritto - float(abbinato)) > 1e-9:
        return (f"riga {r.get('id')}: prezzo scritto {scritto} invece del "
                f"prezzo ABBINATO {abbinato} (chiesto "
                f"{(m.richiesta or {}).get('price')})")
    return None


# GLI STATI TERMINALI di Betfair: l'ordine e' MORTO e a mercato non resta
# niente. E' l'elenco CHIUSO con cui `_j3` riconosce un FOK ucciso a zero;
# scritto QUI e non importato da `omega_service` di proposito — un controllo che
# prendesse l'elenco dal codice che giudica sbaglierebbe insieme a lui.
# Uno stato che non sta qui dentro (o che manca) NON e' terminale: e' AMBIGUO.
STATI_TERMINALI = frozenset({"EXECUTION_COMPLETE", "EXPIRED", "LAPSED",
                             "VIOLATION", "VOIDED", "CANCELLED"})


def _fok_ucciso_a_zero(esito: Any) -> bool:
    """L'ordine e' stato ACCETTATO, non ha abbinato NIENTE ed e' MORTO.

    E' il FOK che Betfair uccide quando la controparte non basta: un `bet_id`
    esiste, ma a mercato non resta nulla e la posizione non e' mai nata. Tutti e
    tre i pezzi vengono dal `PlaceResult` VERO del banco — mai dalle attivita'
    scritte dal bot (§7.36: il bot puo' sbagliarsi anche nel dichiararsi).

    Se lo STATO non e' leggibile, o non e' uno dei terminali dichiarati, questa
    funzione risponde NO: un esito ambiguo e' un rischio, e chi giudica deve
    accusare, non assolvere.
    """
    if esito is None or not bool(getattr(esito, "ok", False)):
        return False
    abbinato = _num(getattr(esito, "size_matched", None))
    if abbinato is None or abbinato > 0.0049:
        return False
    stato = str(getattr(esito, "order_status", "") or "").strip().upper()
    return stato in STATI_TERMINALI


def _e_ref_per_gamba(ref: str) -> bool:
    """True se ``ref`` ha il FORMATO per-gamba ``omega-t<int>`` (§6/§16 review
    C1) — un metro indipendente dal codice (``customer_ref_for`` potrebbe
    cambiare forma, questo controllo no)."""
    resto = ref[len("omega-t"):] if ref.startswith("omega-t") else ""
    return bool(resto) and resto.isdigit()


@_controllo("J3", "il riferimento del piazzamento e' quello PER GAMBA "
                  "(`omega-t<id>`, §16 review C1) e non si ripete",
            quando=lambda m: m.tipo == "ordine" and m.richiesta is not None)
def _j3(m: Momento) -> Optional[str]:
    """DUE metri, e servono entrambi.

    Il primo ri-deriva il ref con `omega_engine.customer_ref_for`, cioe' con la
    STESSA funzione che usa la riconciliazione: prende un ref cablato al punto
    di piazzamento (difetto 4/6 del 15/09). Ma non prende un cambio della
    funzione stessa — li' il controllo e il bot sbaglierebbero insieme.
    Il secondo confronta col FORMATO scritto nella Costituzione (§6, §16
    review C1: `omega-t<id>`, uno per gamba): quello e' un metro indipendente
    dal codice, e prende anche il caso in cui la funzione cambia forma.

    DUE ESCLUSIONI, che sono la stessa cosa vista da due parti: quando la riga
    non c'e' piu' perche' `_leg_certain_failure` l'ha cancellata dopo un esito
    CERTO negativo, non c'e' NIENTE da riconciliare. I due modi in cui Betfair
    dice «niente»: il RIFIUTO (`ok=False`, nessun `bet_id`: l'ordine non e' mai
    esistito) e il FOK UCCISO A ZERO (`ok=True`, il `bet_id` c'e', ma
    `size_matched == 0` e lo stato e' TERMINALE: l'ordine e' esistito per un
    istante e non ha abbinato niente). In nessuno dei due resta una posizione,
    e J3 esiste per garantire che una posizione VIVA sia ritrovabile.

    FALSO POSITIVO DEL CONTROLLO trovato dal replay (17/09, PROCESSO §6.7:
    prima di accusare il bot si esclude che il falso positivo sia del
    controllo): quando ``_leg_certain_failure`` cancella la riserva DOPO un
    rifiuto CERTO di Betfair (``ok=False``, nessun ``bet_id``: nessun ordine
    e' MAI esistito), la riga non c'e' piu' quando questo controllo la cerca
    — ma non c'e' NIENTE da riconciliare, quindi non e' un buco. Qui non si
    accusa SOLO quando ENTRAMBE le condizioni sono vere: (1) il ref e' gia'
    nel formato per-gamba corretto (altrimenti un ref malformato resterebbe
    comunque un problema, anche col rifiuto), e (2) il BANCO STESSO dice che
    l'ordine e' stato rifiutato — ``m.esito``, il ``PlaceResult`` VERO che il
    banco ha osservato, MAI le attivita' scritte dal bot (§7.36: il bot puo'
    sbagliarsi anche nel dichiararsi). Un esito IGNOTO (``m.esito is None``,
    l'eccezione durante il place) NON e' un rifiuto certo: li' si continua ad
    accusare, come oggi — e' esattamente il caso che l'esclusione non deve
    coprire."""
    ref = str((m.richiesta or {}).get("customer_ref") or "")
    if not ref:
        return "ordine piazzato senza customer_ref: non sara' riconciliabile"
    riga = _riga_dal_ref(m, ref) or _riga_del_piazzamento(m)
    if riga is None:
        if str((m.richiesta or {}).get("side", "")).lower() == "lay":
            esito = m.esito
            rifiuto_certo = (esito is not None
                             and not bool(getattr(esito, "ok", False))
                             and not getattr(esito, "bet_id", None))
            # 17/09, SECONDO RAMO: il FOK ucciso a zero. Lo stato terminale lo
            # dice il `PlaceResult` del banco; se non e' leggibile si accusa.
            if _e_ref_per_gamba(ref) and (rifiuto_certo or _fok_ucciso_a_zero(esito)):
                return None
            return (f"ref '{ref}' non riconducibile a nessuna riga con "
                    f"`customer_ref_for`: la riconciliazione non ritroverebbe "
                    f"l'ordine")
    else:
        atteso = f"omega-t{int(riga.get('id') or 0)}"[:32]
        if ref != atteso:
            return (f"ref '{ref}' invece di '{atteso}' (§6/§16: uno per GAMBA, "
                    f"riga {riga.get('id')}): con due gambe per partita il "
                    f"secondo ordine viene rifiutato e la riconciliazione "
                    f"confonde gli ordini")
    visti = (m.richiesta or {}).get("refs_gia_usati") or ()
    if ref in visti:
        return f"ref '{ref}' gia' usato per un altro ordine: la riconciliazione li confonde"
    return None


@_controllo("J4", "`closes_trade_id` sta nella COLONNA della riga di chiusura, "
                  "non solo nel meta (difetto 5 del 15/09)",
            quando=lambda m: m.tipo == "giro" and m.db is not None
            and any((r.get("meta") or {}).get("cashout") for r in m.db.trades))
def _j4(m: Momento) -> Optional[str]:
    for r in m.db.trades:
        meta = r.get("meta") or {}
        if not meta.get("cashout"):
            continue
        if r.get("closes_trade_id") in (None, 0, ""):
            return (f"riga di chiusura {r.get('id')} senza `closes_trade_id` in "
                    f"colonna (meta: {meta.get('closes_trade_id')}): nessuna "
                    f"chiusura verrebbe riconosciuta")
    return None


@_controllo("J5", "grafia snake_case ovunque: mai una chiave camelCase nelle "
                  "righe degli ordini o dei trade (difetto 1 del 15/09)",
            quando=lambda m: m.tipo == "giro" and m.db is not None)
def _j5(m: Momento) -> Optional[str]:
    for r in (m.righe_ordine or []):
        cattive = [k for k in r if k in _CAMEL_VIETATE]
        if cattive:
            return f"riga ordine con chiavi camelCase: {cattive}"
    for r in m.db.trades:
        cattive = [k for k in r if k in _CAMEL_VIETATE]
        cattive += [k for k in (r.get("meta") or {}) if k in _CAMEL_VIETATE]
        if cattive:
            return f"riga trade {r.get('id')} con chiavi camelCase: {cattive}"
    return None


@_controllo("J6", "parziale: abbinato sotto il chiesto -> attivita' "
                  "`place_parziale` col residuo (C.10/C.12a)",
            quando=lambda m: m.tipo == "ordine" and m.esito is not None
            and bool(getattr(m.esito, "ok", False))
            and _num(getattr(m.esito, "size_matched", None)) is not None
            and _num((m.richiesta or {}).get("size")) is not None
            # PARZIALE vuol dire che QUALCOSA si e' abbinato (17/09): abbinato
            # ZERO e' un NO-FILL (il FOK ucciso), e li' non c'e' nessun residuo
            # vivo da mostrare al trader — `place_parziale` direbbe una cosa
            # falsa. Il no-fill lo giudicano J1 (mai una posizione aperta da un
            # place non riuscito) e la famiglia K (la riga non resta viva).
            and (_num(getattr(m.esito, "size_matched", None)) or 0.0) > 0.0049
            and (_num(getattr(m.esito, "size_matched", None)) or 0.0) + 0.005
            < (_num((m.richiesta or {}).get("size")) or 0.0))
def _j6(m: Momento) -> Optional[str]:
    kinds = [k for k, _p, _e in (m.attivita or [])]
    if "place_parziale" not in kinds:
        return (f"abbinato {getattr(m.esito, 'size_matched', None)} su "
                f"{(m.richiesta or {}).get('size')} e nessuna attivita' "
                f"'place_parziale': il trader non vede il residuo")
    return None


@_controllo("J7", "un annullo si RILEGGE da Betfair prima di qualunque stato "
                  "terminale (C.12a, `_ordine_ancora_vivo`)",
            quando=lambda m: m.tipo == "giro" and bool(
                [k for k, _p, _e in (m.attivita or []) if k == "cancel_richiesto"]))
def _j7(m: Momento) -> Optional[str]:
    richiesti = [p for k, p, _e in (m.attivita or []) if k == "cancel_richiesto"]
    esiti = [p for k, p, _e in (m.attivita or []) if k == "cancel_esito"]
    if len(esiti) < len(richiesti):
        return (f"{len(richiesti)} annulli richiesti e solo {len(esiti)} esiti "
                f"riletti: un ordine dato per morto puo' essere vivo su Betfair")
    for p in esiti:
        # `omega_service._ordine_ancora_vivo:2365` scrive `esito_ignoto`: un
        # annullo dichiarato CONFERMATO con l'esito ignoto sarebbe un ordine
        # dato per morto senza che Betfair lo abbia detto.
        if p.get("esito_ignoto") and p.get("confermato"):
            return f"annullo dichiarato confermato con esito IGNOTO: {p}"
    return None


# ===========================================================================
# F. SETTLEMENT E RICONCILIAZIONE (§I3, §6)
# ===========================================================================
@_controllo("F1", "settlement: la commissione si applica UNA volta sola, sul "
                  "netto vincente (§6; doppia commissione corretta l'11/09)",
            quando=lambda m: m.tipo == "giro" and m.db is not None
            and any(str(r.get("status")) in ("won", "lost", "void")
                    for r in m.db.trades))
def _f1(m: Momento) -> Optional[str]:
    for r in m.db.trades:
        stato = str(r.get("status"))
        if stato not in ("won", "lost", "void"):
            continue
        if r.get("closes_trade_id"):
            continue                    # la chiusura si nettizza in coppia
        pnl = _num(r.get("pnl"))
        size = _num(r.get("size"))
        prezzo = _num(r.get("price"))
        comm = _num(r.get("commission"))
        if pnl is None or size is None or prezzo is None or comm is None:
            continue
        if (r.get("meta") or {}).get("position_pnl") is not None:
            continue                    # posizione nettizzata: altro metro
        if stato == "won":
            atteso = round(size * (1.0 - comm), 2)
            if abs(pnl - atteso) > max(0.02, abs(atteso) * 0.02):
                return (f"riga {r.get('id')} vinta: pnl {pnl} invece di {atteso} "
                        f"(size {size}, commissione {comm}) — commissione "
                        f"applicata due volte o non applicata")
        elif stato == "lost":
            atteso = round(-E.liability_from_lay(size, prezzo), 2)
            if abs(pnl - atteso) > max(0.02, abs(atteso) * 0.02):
                return (f"riga {r.get('id')} persa: pnl {pnl} invece della "
                        f"liability {atteso} (la perdita non porta commissione)")
    return None


@_controllo("F2", "una riga a esito IGNOTO non viene mai data per non piazzata: "
                  "resta in riconciliazione (§I3, difetto 4 del 15/09)",
            quando=lambda m: m.tipo == "giro" and m.db is not None
            and any((r.get("meta") or {}).get("reconciling") for r in m.db.trades))
def _f2(m: Momento) -> Optional[str]:
    for r in m.db.trades:
        meta = r.get("meta") or {}
        if not meta.get("reconciling"):
            continue
        if meta.get("leg_failed"):
            return (f"riga {r.get('id')} a esito IGNOTO marcata `leg_failed` "
                    f"(gamba ritentabile): un ordine forse vivo su Betfair "
                    f"verrebbe ripiazzato")
        if str(r.get("status")) == "error":
            return (f"riga {r.get('id')} a esito IGNOTO gia' in 'error': "
                    f"l'ordine reale resterebbe non tracciato")
    return None


# ===========================================================================
# V3 (16/09 sera) — LE REGOLE DEL MOTORE NUOVO (`omega_v3.py`).
#
# Valgono SOLO con `strategy_version >= 3`: con il default 2 questi controlli non
# vengono nemmeno sollecitati, e il referto lo dice («mai sollecitato» = non lo
# so, non «sano»). Sono i sette che il progetto V3 chiede al §5.2, piu' i due
# sull'uscita che l'ordine dell'utente del 16/09 sera ha reso necessari.
# ===========================================================================
def _v3_on(m: Momento) -> bool:
    """V3 e' acceso nei parametri (vale per i controlli sulla CONFIGURAZIONE)."""
    return int((m.params or {}).get("strategy_version") or 2) >= 3


def _v3_suo(m: Momento) -> bool:
    """Questo momento e' stato prodotto DAL motore V3 (vale per i controlli sulle
    sue DECISIONI). Un momento del v2 non si giudica col metro del v3."""
    return _v3_on(m) and str(m.motore) == "v3"


# i motivi con cui V3 puo' NON entrare. Uno fuori da questo elenco vuol dire che
# una gamba e' saltata per una ragione che nessuno ha scritto: e' il buco che
# «due gambe su ogni partita» vieta.
MOTIVI_V3 = frozenset({
    "fuori_finestra", "nessun_candidato", "no_model_lambdas", "no_market",
    "no_live_state", "market_not_open", "market_suspended", "market_closed",
    "market_inactive", "gamba_gia_fatta", "cap_partita", "cap_aperto",
    "cap_perdita_giornaliera", "insufficient_liquidity",
})


@_controllo("A8", "V3: su ogni partita seguita o c'e' la gamba, o c'e' un motivo "
                  "DICHIARATO (progetto V3 §5.2; estende A1)",
            quando=lambda m: _v3_suo(m) and m.tipo == "selezione" and m.cand is None)
def _a8(m: Momento) -> Optional[str]:
    motivo = str(m.motivo or "").strip()
    if not motivo:
        return f"gamba '{m.leg}' saltata SENZA motivo dichiarato (V3)"
    if motivo not in MOTIVI_V3:
        return (f"gamba '{m.leg}' saltata con un motivo non dichiarato: '{motivo}' "
                f"(dichiarati: {sorted(MOTIVI_V3)})")
    # se c'erano runner, deve esserci anche l'elenco di CHI e' stato scartato e
    # perche': «nessun candidato» senza la lista non e' una spiegazione
    if motivo == "nessun_candidato" and m.snapshot is not None:
        runners = list(getattr(m.snapshot, "runners", ()) or ())
        if runners and not (m.scartati or ()):
            return (f"gamba '{m.leg}': {len(runners)} runner sul book e nessuno "
                    f"scarto motivato — non si sa perche' non si e' entrati")
    return None


@_controllo("A9", "V3: il lay e' ESATTAMENTE `v3_stake_eur` (1,00 EUR), in paper "
                  "come in live (ordine dell'utente 16/09)",
            quando=lambda m: _v3_suo(m) and m.tipo in ("sizing", "ordine")
            # solo le APERTURE (lay): una CHIUSURA e' un BACK dimensionato dal
            # green-up/cash-out (s*L/B), e giudicarla con lo stake fisso e' un
            # falso positivo (replay 35777617 `cashout-globale`, 17/09 sera)
            and str((m.richiesta or {}).get("side") or "lay").lower() == "lay"
            and (m.size is not None or (m.richiesta or {}).get("size") is not None))
def _a9(m: Momento) -> Optional[str]:
    voluto = _num((m.params or {}).get("v3_stake_eur"))
    if voluto is None:
        return None
    size = _num(m.size if m.size is not None else (m.richiesta or {}).get("size"))
    if size is None:
        return None
    if abs(float(size) - float(voluto)) > 0.005:
        return (f"lay da {size} EUR con lo stake fisso a {voluto} EUR "
                f"(gamba {m.leg}, modo {m.mode})")
    return None


@_controllo("A10", "V3: margine k — `P_nostra * k <= p_implicita`, con k misurato "
                   "per secchio (K_MISURATO_2026-09-16.md; estende A3)",
            quando=lambda m: _v3_suo(m) and m.tipo == "selezione" and m.cand is not None)
def _a10(m: Momento) -> Optional[str]:
    c = m.cand
    p_nostra = _num(getattr(c, "p_nostra", None))
    p_imp = _num(getattr(c, "p_implicita", None))
    k = _num(getattr(c, "k_usato", None))
    if p_nostra is None or p_imp is None or k is None:
        return "candidato V3 senza i numeri del margine (p_nostra / p_implicita / k)"
    minimo = _num((m.params or {}).get("v3_k_minimo")) or 2.0
    if k + 1e-9 < minimo:
        return f"k usato {k:g} sotto il pavimento {minimo:g} su '{getattr(c, 'name', '?')}'"
    if p_nostra * k > p_imp + 1e-12:
        return (f"'{getattr(c, 'name', '?')}' a quota {getattr(c, 'price', '?')}: "
                f"P_nostra {p_nostra * 100:.4f}% x k {k:g} = {p_nostra * k * 100:.4f}% "
                f"oltre la p_implicita {p_imp * 100:.4f}% — margine non rispettato")
    return None


@_controllo("A11", "V3: mai il risultato CORRENTE ne' uno raggiungibile senza "
                   "margine (progetto V3 §5.2; estende A2)",
            quando=lambda m: _v3_suo(m) and m.tipo == "selezione" and m.cand is not None)
def _a11(m: Momento) -> Optional[str]:
    c = m.cand
    d = _distanza(getattr(c, "name", None), m.state)
    minimo = int((m.params or {}).get("v3_distanza_minima_gol") or 1)
    if d is not None:
        if d == 0:
            return (f"banca il PUNTEGGIO CORRENTE '{getattr(c, 'name', '?')}': "
                    f"e' il difetto del v1, -93,87 EUR il 09/09")
        if d < minimo:
            return (f"banca '{getattr(c, 'name', '?')}' a {d} gol dal punteggio "
                    f"corrente, col minimo a {minimo}")
    tetto = _num((m.params or {}).get("v3_p_max_pct"))
    p_nostra = _num(getattr(c, "p_nostra", None))
    if tetto is not None and p_nostra is not None and p_nostra > tetto / 100.0 + 1e-9:
        return (f"P_nostra {p_nostra * 100:.3f}% sopra il tetto duro {tetto:.2f}% "
                f"su '{getattr(c, 'name', '?')}'")
    # LA FASCIA IN CUI SI OPERA, e sta sulla p_IMPLICITA AL TOCCO (17/09).
    # Il bias e' stato misurato per FASCIA DI p_impl (`tools/k_in_gioco.py`,
    # M4M5M6 §2.3): sotto il pavimento non lo si conosce, sopra il tetto lo si
    # conosce e vale MENO DI UNO (fascia 2-5 %: 0,71, cioe' EV negativo). Una
    # cella fuori fascia non si banca nemmeno col margine migliore del mondo.
    # Il buco l'ha trovato la falsificazione del raccordo: spegnendo la fascia
    # dentro `omega_v3` nessun controllo se ne accorgeva.
    p_impl = _num(getattr(c, "p_implicita", None))
    pavimento = _num((m.params or {}).get("v3_p_min_pct"))
    if pavimento is not None and p_impl is not None \
            and p_impl + 1e-9 < pavimento / 100.0:
        return (f"p_implicita {p_impl * 100:.3f}% SOTTO il pavimento di fascia "
                f"{pavimento:.2f}% su '{getattr(c, 'name', '?')}': li' il bias "
                f"in gioco non e' misurato")
    if tetto is not None and p_impl is not None and tetto > 0 \
            and p_impl > tetto / 100.0 + 1e-9:
        return (f"p_implicita {p_impl * 100:.3f}% SOPRA il tetto di fascia "
                f"{tetto:.2f}% su '{getattr(c, 'name', '?')}': li' il bias "
                f"misurato in gioco e' sotto 1 (EV negativo)")
    return None


@_controllo("A12", "V3: dove il dato storico parla (n >= `v3_empirical_min_n`) la sua "
                   "P e' OBBLIGATORIA — P_nostra = max(modello, storico)",
            quando=lambda m: _v3_suo(m) and m.tipo == "selezione" and m.cand is not None
            and _num(getattr(m.cand, "p_empirica", None)) is not None)
def _a12(m: Momento) -> Optional[str]:
    c = m.cand
    emp = _num(getattr(c, "p_empirica", None))
    n = getattr(c, "n_empirico", None)
    fusa = _num(getattr(c, "p_fusa", None))
    p_nostra = _num(getattr(c, "p_nostra", None))
    minimo = int((m.params or {}).get("v3_empirical_min_n") or 0)
    if n is not None and int(n) < minimo:
        return (f"usata una P storica con n={n} sotto il minimo {minimo} "
                f"su '{getattr(c, 'name', '?')}': il dato non ha diritto di parola")
    if p_nostra is None or fusa is None or emp is None:
        return None
    atteso = max(fusa, emp)
    if abs(p_nostra - atteso) > 1e-9:
        return (f"P_nostra {p_nostra * 100:.4f}% diversa da max(modello "
                f"{fusa * 100:.4f}%, storico {emp * 100:.4f}%): il veto di coda "
                f"non e' stato applicato")
    return None


@_controllo("C5", "V3: nessuna gamba oltre `v3_max_liability_per_leg` (progetto V3 §4.5)",
            quando=lambda m: _v3_suo(m) and m.tipo in ("sizing", "ordine")
            and (_num((m.params or {}).get("v3_max_liability_per_leg")) or 0.0) > 0.0)
def _c5(m: Momento) -> Optional[str]:
    cap = float((m.params or {}).get("v3_max_liability_per_leg"))
    r = m.richiesta or {}
    size = _num(m.size if m.size is not None else r.get("size"))
    prezzo = _num(m.price if m.price is not None else r.get("price"))
    if size is None or prezzo is None:
        return None
    liab = E.liability_from_lay(size, prezzo)
    if liab > cap + 0.011:
        return (f"gamba da {size} @ {prezzo} = liability {liab:.2f} col tetto di "
                f"GAMBA a {cap:.2f}")
    return None


@_controllo("G1", "V3: NESSUNA chiusura automatica — l'uscita e' una proposta che "
                  "approva l'utente (ordine del 16/09; memoria 12/09)",
            quando=lambda m: _v3_on(m) and m.tipo in ("uscita", "ordine", "giro"))
def _g1(m: Momento) -> Optional[str]:
    # (a) il green-up automatico non deve nemmeno essere ACCESO NEI PARAMETRI.
    # Si guardano i parametri GREZZI, non `E.greenup_automatico_attivo`: quella
    # funzione risponde gia' «no» per costruzione quando V3 e' attivo, quindi
    # usarla qui sarebbe un controllo che non puo' diventare rosso — e un
    # controllo cosi' non certifica niente (falsificato: il test lo dimostra).
    p = m.params or {}
    if bool(p.get("greenup_enabled", True)) and \
            str(p.get("greenup_mode") or "auto") == "auto":
        return ("`greenup_mode='auto'` con strategy_version >= 3: qualcuno ha "
                "scavalcato la whitelist (`omega_config.resolve_params` lo porta a "
                "'off'). In V3 non esiste una chiusura che parte da sola")
    if E.greenup_automatico_attivo(p):
        return ("il green-up AUTOMATICO risulta attivo con strategy_version >= 3: "
                "in V3 non esiste una chiusura che parte da sola")
    # (b) nessuna decisione di uscita puo' essere diversa da «tieni»
    if m.tipo == "uscita" and str(m.azione or "").lower() not in ("", "hold", "propose",
                                                                 "proposta"):
        return (f"decisione di uscita '{m.azione}' in V3: l'unica uscita ammessa e' "
                f"la PROPOSTA (perche': {m.perche})")
    # (c) nessun ordine di chiusura (back sulla stessa selezione) puo' partire
    #     senza una decisione UMANA dichiarata nello stesso giro.
    if m.tipo == "ordine":
        r = m.richiesta or {}
        if str(r.get("side") or "").lower() == "back" and not r.get("approvata_dall_utente"):
            firma = _firma_umana(m, r)
            if firma is None:
                return (f"ordine di BACK (= chiusura) partito senza approvazione "
                        f"dell'utente: ref {r.get('customer_ref')}")
    # (d) 24/09 - l'uscita ESEGUITA DAL BOT si guarda anche dal lato
    #     dell'attivita' (vale anche in paper, dove l'ordine non passa dal
    #     mercato del banco): con `uscite_protezione` su 'avvisa_e_proponi' non
    #     deve esistere; su 'automatico' deve dichiarare la scelta dell'utente e
    #     un motivo che la proposta avrebbe avuto.
    if m.tipo == "giro":
        automatico = _uscite_automatiche(m)
        for voce in (m.attivita or ()):
            try:
                kind, payload = str(voce[0]), (voce[1] or {})
            except (TypeError, IndexError):
                continue
            if kind != _ATTIVITA_USCITA_AUTOMATICA or payload.get("esito") != "eseguita":
                continue
            if not automatico:
                return (f"uscita del trade {payload.get('trade_id')} ESEGUITA DAL BOT con "
                        f"uscite_protezione='avvisa_e_proponi': doveva essere una "
                        f"proposta da firmare")
            if payload.get("scelta_utente") != _SCELTA_AUTOMATICO or \
                    str(payload.get("motivo_codice") or "") not in _MOTIVI_DI_USCITA:
                return (f"uscita automatica del trade {payload.get('trade_id')} senza la "
                        f"scelta dell'utente dichiarata o con un motivo che nessuna "
                        f"proposta avrebbe ('{payload.get('motivo_codice')}')")
    return None


# i motivi con cui il produttore delle proposte PROPONE (`omega_proposte.
# MOTIVI_CHE_PROPONGONO`): un'uscita automatica non puo' averne un altro
_MOTIVI_DI_USCITA = ("blocca_il_profitto", "protezione", "cap", "rischio")


# le attivita' con cui il servizio DICHIARA che a chiudere e' stata una persona.
#   `cashout_manual`  — il bottone «Cash out» della scheda: e' un gesto suo;
#   `uscita_approvata` — una proposta del BOT che l'utente ha FIRMATO. Vale solo
#                        con `firmata=True`, cioe' col `approved_at` che scrive
#                        la RPC: senza, quella riga e' arrivata a 'pending' senza
#                        passare dal cancelletto, e non e' una firma.
_ATTIVITA_DI_CHIUSURA_UMANA = ("cashout_manual", "uscita_approvata")

# 24/09 - ORDINE DELL'UTENTE ("QUESTO PER TUTTI I BOT"): con
# `uscite_protezione='automatico'` l'uscita calcolata la ESEGUE il bot e lo
# dichiara con l'attivita' `uscita_automatica` (``omega_proposte._esegui_da_solo``).
# E' conforme SOLO col parametro su 'automatico'; in 'avvisa_e_proponi' (il
# default) vale la regola del 17/09: nessuna chiusura parte da sola.
_ATTIVITA_USCITA_AUTOMATICA = "uscita_automatica"
# anche l'invio FALLITO si dichiara (``closing_trade_id`` se l'ordine e' partito
# prima dell'errore): e' la stessa decisione, con esito diverso
_ATTIVITE_USCITA_AUTOMATICA = (_ATTIVITA_USCITA_AUTOMATICA, "uscita_automatica_fallita")
_SCELTA_AUTOMATICO = "uscite_protezione=automatico"


def _uscite_automatiche(m: "Momento") -> bool:
    """Il parametro dell'utente su 'automatico', letto come lo legge il servizio
    (``omega_proposte.modo_uscite``: fail-closed, solo il valore esatto)."""
    v = str((m.params or {}).get("uscite_protezione") or "").strip().lower()
    return v == "automatico"


def _trade_dal_ref(ref: Any) -> Optional[int]:
    """L'id della riga dal `customerOrderRef` (`omega-t<id>`), o None."""
    testo = str(ref or "")
    pezzo = testo.rsplit("-t", 1)[-1] if "-t" in testo else ""
    pezzo = "".join(c for c in pezzo if c.isdigit())
    return int(pezzo) if pezzo else None


def _firma_umana(m: Momento, richiesta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """L'attivita' con cui il servizio dichiara CHI ha deciso questa chiusura.

    None = nessuna: l'ordine di back e' partito da solo, ed e' la cosa che in V3
    non deve mai succedere (memoria 12/09: cinque chiusure automatiche, tutte
    sbagliate, -42,39 EUR). Si guardano le attivita' DI QUESTO GIRO, non un flag
    che il codice potrebbe scrivere a comodo: e' la stessa riga che finisce in
    pagina sotto gli occhi del trader.
    """
    tid = _trade_dal_ref(richiesta.get("customer_ref"))
    automatico = _uscite_automatiche(m)
    for voce in (m.attivita or ()):
        try:
            kind, payload = str(voce[0]), (voce[1] or {})
        except (TypeError, IndexError):
            continue
        if kind in _ATTIVITE_USCITA_AUTOMATICA:
            # 24/09 - l'uscita del bot eseguita per SCELTA DELL'UTENTE
            # (`uscite_protezione='automatico'`) e' una decisione dichiarata
            # SOLO se il parametro e' davvero su 'automatico' in questo giro e
            # l'attivita' porta la scelta. In 'avvisa_e_proponi' non conta
            # niente: e' il bot che ha chiuso da solo.
            if not automatico or payload.get("scelta_utente") != _SCELTA_AUTOMATICO:
                continue
        elif kind not in _ATTIVITA_DI_CHIUSURA_UMANA:
            continue
        if kind == "uscita_approvata" and not payload.get("firmata"):
            continue          # promossa a 'pending' senza passare dalla RPC: NON e' una firma
        chiusura = payload.get("closing_trade_id")
        if tid is None or chiusura is None or int(chiusura) == int(tid):
            return {"kind": kind, **payload}
    return None


@_controllo("G2", "V3: la proposta viva porta i numeri della decisione e si "
                  "AGGIORNA senza perdere l'istante della decisione",
            quando=lambda m: _v3_suo(m) and m.tipo == "proposta" and m.proposta is not None)
def _g2(m: Momento) -> Optional[str]:
    p = m.proposta
    for campo in ("profitto_bloccabile", "ev_tenere", "back_price", "back_size",
                  "p_evento", "motivo_codice"):
        if getattr(p, campo, None) is None:
            return f"proposta senza '{campo}': la Control Room non puo' mostrare i numeri"
    if not getattr(p, "proponi", False):
        return None
    motivo = str(getattr(p, "motivo_codice", "") or "")
    bloccabile = _num(getattr(p, "profitto_bloccabile", None))
    if bloccabile is None:
        return "proposta di chiusura senza il numero bloccabile"
    # 17/09 — ORDINE DELL'UTENTE: la scheda vale «sia in profit che in loss».
    # Un bloccabile NEGATIVO e' legittimo quando il motivo lo dichiara
    # (protezione: tenere costa di piu'; cap: un tetto e' scattato; rischio: la
    # P ha superato la soglia). Con `blocca_il_profitto` resta un errore: quel
    # motivo PROMETTE un guadagno, e un guadagno negativo e' una bugia in pagina.
    if float(bloccabile) <= 0 and motivo not in ("protezione", "cap", "rischio"):
        return (f"proposta '{motivo}' con profitto bloccabile non positivo "
                f"({bloccabile:.2f} EUR): quel motivo promette un guadagno")
    # `decided_at` non si rinfresca (altrimenti la latenza misurata e' sempre
    # zero e il numero dice il contrario del vero — cert. Safe 14/09)
    prima = (m.proposte_viste or {}).get(str(m.trade_id))
    if prima and prima.get("decided_at") and m.decided_at and \
            str(prima["decided_at"]) != str(m.decided_at):
        return (f"la proposta del trade {m.trade_id} ha cambiato `decided_at` "
                f"({prima['decided_at']} -> {m.decided_at}): la latenza misurata "
                f"sarebbe sempre ~zero")
    if prima and m.proposed_at and prima.get("proposed_at") == m.proposed_at \
            and prima.get("profitto") != _num(getattr(p, "profitto_bloccabile", None)):
        return (f"il profitto bloccabile del trade {m.trade_id} e' cambiato senza "
                f"che la proposta venisse riscritta: la pagina mostra un numero vecchio")
    return None


# entro quanti GIRI del servizio una proposta firmata deve essere passata a
# mercato. `process_manual` la drena nello stesso giro in cui la trova, quindi
# due giri sono gia' larghi: il terzo vuol dire che nessuno la sta leggendo — ed
# e' esattamente il reperto O-1 (la coda sbagliata).
GIRI_MASSIMI_PER_ESEGUIRE = 2


@_controllo("G3", "una proposta APPROVATA dall'utente viene ESEGUITA dalla coda "
                  "manuale entro pochi giri, e NON marca la partita «chiusa "
                  "dall'utente» (reperti O-1 e O-3, 17/09)",
            quando=lambda m: m.tipo == "giro" and bool(m.approvazioni))
def _g3(m: Momento) -> Optional[str]:
    """I due modi in cui una firma puo' non valere niente.

    (a) LA CODA SBAGLIATA (O-1). La migrazione del 16/09 aveva messo le proposte
        su `omega_requests`, una tabella che il servizio non drena: approvare
        portava la riga da 'proposed' a 'pending' e li' restava per sempre. Il
        trader vedeva «fatto» su una posizione ancora aperta, e se ne sarebbe
        accorto al settlement. Qui si guarda il FATTO: dopo la firma, entro
        ``GIRI_MASSIMI_PER_ESEGUIRE`` giri, la richiesta dev'essere uscita da
        'pending'.
    (b) LA CHIUSURA ATTRIBUITA ALL'UTENTE (O-3). Quella chiusura l'ha DECISA il
        bot; l'utente ha firmato. Marcarla come chiusura sua spegnerebbe il bot
        su una partita che sta gestendo lui — e' il difetto che la Safe ha
        trovato il 16/09 (T14 violato x282).
    """
    for a in (m.approvazioni or ()):
        if not isinstance(a, dict):
            continue
        giri = a.get("giri_da_approvazione")
        stato = str(a.get("status") or "")
        if stato in ("proposed",):
            return (f"la richiesta {a.get('request_id')} risulta APPROVATA ma e' "
                    f"tornata in 'proposed': la firma si e' persa")
        if (not a.get("eseguita") and isinstance(giri, int)
                and giri > GIRI_MASSIMI_PER_ESEGUIRE):
            return (f"la proposta {a.get('request_id')} (trade {a.get('trade_id')}) e' "
                    f"stata approvata {giri} giri fa ed e' ancora '{stato}': il servizio "
                    f"non sta drenando la coda su cui vive la proposta (reperto O-1)")
        if a.get("eseguita") and a.get("evento_chiuso_dall_utente"):
            return (f"la proposta {a.get('request_id')} e' stata eseguita e la partita "
                    f"{a.get('event_id')} risulta «chiusa dall'utente»: quella chiusura "
                    f"l'ha DECISA il bot, l'utente ha solo firmato (reperto O-3)")
        if a.get("eseguita") and str(a.get("exit_kind") or "") == "manual":
            return (f"la proposta {a.get('request_id')} e' stata eseguita con "
                    f"exit_kind='manual': nello storico non si distingue piu' da un "
                    f"cash out premuto a mano, e la latenza della firma non e' piu' "
                    f"misurabile (reperto O-3)")
    return None


@_controllo("G4", "IN PERDITA il bot PROPONE (motivo `protezione`/`cap`/`rischio`) "
                  "e non chiude mai da solo: la riga resta 'proposed' finche' non "
                  "la firma una persona (ordine dell'utente 17/09)",
            quando=lambda m: m.tipo == "proposta" and m.proposta is not None
            and (_num(getattr(m.proposta, "profitto_bloccabile", None)) or 0.0) < 0)
def _g4(m: Momento) -> Optional[str]:
    """La meta' che mancava. Fino al 17/09 `proposta_uscita` usciva SEMPRE da
    `bloccabile_non_positivo` quando chiudere costava: in perdita il bot non
    chiedeva niente e una gamba con la cella che si avvicinava restava muta fino
    al settlement. L'utente lo ha vietato: «la scheda vale sia in profit che in
    loss».

    Due cose insieme, e servono entrambe:
      · la proposta in perdita ESISTE e dichiara perche' (`protezione` / `cap` /
        `rischio`, mai `blocca_il_profitto`: quel motivo promette un guadagno);
      · e resta una PROPOSTA — cioe' la riga in coda e' 'proposed'. Se il bot
        se la promuovesse da solo a 'pending' avrebbe chiuso senza firma, che e'
        esattamente cio' che G1 vieta, dal lato della coda.

    24/09 - IL PARAMETRO DELL'UTENTE `uscite_protezione`. In
    'avvisa_e_proponi' (default) vale tutto quanto sopra. In 'automatico'
    l'uscita la esegue il bot (attivita' `uscita_automatica`, giudicata da G1):
    una proposta in perdita ancora 'proposed' e' ammessa SOLO come ripiego
    dichiarato (tentativi automatici esauriti sulla riga).
    """
    p = m.proposta
    motivo = str(getattr(p, "motivo_codice", "") or "")
    bloccabile = _num(getattr(p, "profitto_bloccabile", None))
    if not getattr(p, "proponi", False):
        # si TIENE con un bloccabile negativo: legittimo solo se tenere vale di
        # piu'. Se tenere vale MENO, il bot sta stando zitto su una perdita che
        # si allarga — ed e' il buco che questo controllo esiste per trovare.
        ev = _num(getattr(p, "ev_tenere", None))
        if ev is not None and bloccabile is not None and ev < bloccabile:
            return (f"bloccabile {bloccabile:.2f} EUR contro un EV di tenere di "
                    f"{ev:.2f} EUR e NESSUNA proposta (motivo '{motivo}'): tenere "
                    f"costa di piu' e il trader non lo sa")
        return None
    if motivo not in ("protezione", "cap", "rischio"):
        return (f"proposta in perdita ({bloccabile:.2f} EUR) col motivo '{motivo}': "
                f"il trader leggerebbe un guadagno dove c'e' una perdita bloccata")
    stato = str(m.stato_richiesta or "")
    if _uscite_automatiche(m) and stato == "proposed":
        # 24/09 - con `uscite_protezione='automatico'` questa uscita la doveva
        # ESEGUIRE il bot. Una proposta in attesa e' legittima solo come
        # ripiego dichiarato: tentativi automatici esauriti
        # (``meta.uscita_automatica.esaurita`` sulla riga).
        riga = None
        getter = getattr(m.db, "get_trade", None)
        if callable(getter) and m.trade_id is not None:
            try:
                riga = getter(int(m.trade_id))
            except Exception:  # noqa: BLE001 - riga illeggibile: non si accusa
                riga = None
        if riga is not None:
            auto = (riga.get("meta") or {}).get("uscita_automatica")
            if not (isinstance(auto, dict) and auto.get("esaurita")):
                return (f"uscite_protezione='automatico' e la proposta in perdita del "
                        f"trade {m.trade_id} e' in scheda invece che eseguita, senza "
                        f"che i tentativi automatici risultino esauriti")
        return None
    if stato and stato != "proposed":
        return (f"la proposta in perdita del trade {m.trade_id} e' in stato '{stato}' "
                f"invece che 'proposed': nessuno l'ha firmata, e sta per partire")
    return None


# ===========================================================================
# il giro completo
# ===========================================================================
def verifica(m: Momento, sollecitati: Optional[Dict[str, int]] = None) -> List[Violazione]:
    """Tutti i controlli su UN momento osservato.

    Un controllo che solleva non ferma gli altri e non ferma la certificazione:
    diventa esso stesso un referto (`XX-ERRORE`), perche' un controllo rotto e'
    un'informazione, non un motivo per non sapere niente del resto.
    """
    out: List[Violazione] = []
    for codice, regola, fn, quando in _REGISTRO:
        try:
            if quando is not None and not quando(m):
                continue
            if sollecitati is not None:
                sollecitati[codice] = sollecitati.get(codice, 0) + 1
            det = fn(m)
        except Exception as ex:  # noqa: BLE001
            out.append(Violazione(f"{codice}-ERRORE", regola,
                                  f"il controllo e' esploso: {type(ex).__name__}: {ex}",
                                  m.tipo, m.il_minuto, m.punteggio))
            continue
        if det:
            out.append(Violazione(codice, regola, det, m.tipo, m.il_minuto, m.punteggio))
    return out


def elenco_controlli() -> List[Tuple[str, str]]:
    """(codice, regola) di tutto cio' che questa certificazione sa verificare —
    i controlli sul MOMENTO (A-G) e quelli sulla CONSAPEVOLEZZA (K).

    La famiglia K vive in un registro separato perche' non guarda un momento ma
    un giro intero; se restasse fuori da qui, il referto non la conterebbe fra i
    controlli e un K mai sollecitato passerebbe per inesistente invece che per
    «non lo so» — che e' esattamente il buco che questa funzione serve a chiudere."""
    return ([(c, r) for c, r, _fn, _q in _REGISTRO]
            + [(c, r) for c, r in _REGISTRO_BANCO])


def mai_sollecitati(sollecitati: Dict[str, int]) -> List[Tuple[str, str]]:
    """I controlli che non hanno MAI avuto un caso da giudicare.

    Sono il buco vero di un referto: non dicono «il bot e' sano», dicono «non lo
    so». Vanno letti come lavoro da fare — uno scenario da provocare — non come
    una garanzia.
    """
    return [(c, r) for c, r in elenco_controlli() if not sollecitati.get(c)]


# ===========================================================================
# P. DIFETTI DI PROGETTAZIONE — non «ha violato una regola», ma «e' fatto in
#    modo che prima o poi la violera'». I controlli A-F guardano UN momento;
#    questi guardano il COMPORTAMENTO nel tempo, che e' dove vivono i loop.
# ===========================================================================
@dataclass
class Andamento:
    """Memoria fra un momento e l'altro, per una partita."""

    # (gamba, mercato, selezione) -> quante volte e' stata proposta
    proposte_per_gamba: Dict[tuple, int] = field(default_factory=dict)
    # la stessa identica richiesta di ordine, di fila
    ultima_richiesta: Optional[tuple] = None
    ripetizioni: int = 0
    max_per_ruolo: Dict[str, int] = field(default_factory=dict)
    ultima_per_ruolo: Dict[str, tuple] = field(default_factory=dict)
    correnti_per_ruolo: Dict[str, int] = field(default_factory=dict)
    # decisioni di uscita, per esito
    uscite: Dict[str, int] = field(default_factory=dict)
    # skip per motivo (il 10/09: 746 `ft_cs no_model_lambdas` in un giorno)
    skip_per_motivo: Dict[str, int] = field(default_factory=dict)


def osserva(and_: Andamento, m: Momento) -> None:
    """Aggiorna l'andamento con quello che il servizio ha appena fatto."""
    if m.tipo == "selezione":
        # V3 non porta una `Selection`, porta il CANDIDATO: leggere `m.sel` per
        # sapere se si e' entrati farebbe contare ogni gamba V3 APERTA come uno
        # skip «senza motivo» (`ft_cs:None`) — che e' il contrario del vero
        # (reperto del raccordo del 17/09, sintetica `_synth_omega_*`).
        scelta = m.cand if str(m.motore) == "v3" else m.sel
        if scelta is None:
            motivo = f"{m.leg}:{m.motivo}"
            and_.skip_per_motivo[motivo] = and_.skip_per_motivo.get(motivo, 0) + 1
        else:
            k = (str(m.leg), str(getattr(scelta, "name", "")), )
            and_.proposte_per_gamba[k] = and_.proposte_per_gamba.get(k, 0) + 1
    elif m.tipo == "uscita":
        chiave = f"{m.trigger}:{m.azione}"
        and_.uscite[chiave] = and_.uscite.get(chiave, 0) + 1
    elif m.tipo == "ordine" and m.richiesta:
        r = m.richiesta
        ruolo = str(r.get("ruolo") or "ordine")
        firma = (ruolo, str(r.get("market_id")), int(r.get("selection_id") or 0),
                 str(r.get("side")), round(float(r.get("price") or 0.0), 2),
                 round(float(r.get("size") or 0.0), 2))
        if firma == and_.ultima_richiesta:
            and_.ripetizioni += 1
        else:
            and_.ultima_richiesta = firma
            and_.ripetizioni = 1
        if and_.ultima_per_ruolo.get(ruolo) == firma:
            and_.correnti_per_ruolo[ruolo] = and_.correnti_per_ruolo.get(ruolo, 0) + 1
        else:
            and_.ultima_per_ruolo[ruolo] = firma
            and_.correnti_per_ruolo[ruolo] = 1
        if and_.correnti_per_ruolo[ruolo] > and_.max_per_ruolo.get(ruolo, 0):
            and_.max_per_ruolo[ruolo] = and_.correnti_per_ruolo[ruolo]


# soglie: sopra queste il comportamento non e' piu' spiegabile come «riprova»
RIPETIZIONI_SOSPETTE = 5        # lo stesso identico ORDINE REALE, di fila
SKIP_SOSPETTI = 200             # lo stesso skip ripetuto (il 10/09: 746)


def difetti_di_progettazione(and_: Andamento, *, ordini_piazzati: int,
                             righe_scritte: int) -> List[Violazione]:
    """Il verdetto sul COMPORTAMENTO, a fine partita."""
    out: List[Violazione] = []
    for ruolo, quante in sorted(and_.max_per_ruolo.items(), key=lambda x: -x[1]):
        if quante < RIPETIZIONI_SOSPETTE:
            continue
        r = and_.ultima_per_ruolo.get(ruolo) or ()
        out.append(Violazione(
            "P1", "non si manda a Betfair la stessa identica richiesta all'infinito",
            f"{ruolo} {r} ripetuto {quante} volte di fila: sono {quante} ordini "
            f"VERI, ed e' la forma esatta del loop del 15/09."))
    for motivo, n in sorted(and_.skip_per_motivo.items(), key=lambda x: -x[1]):
        if n < SKIP_SOSPETTI:
            continue
        out.append(Violazione(
            "P2", "una gamba non puo' saltare per centinaia di cicli con lo stesso "
                  "motivo senza che nessuno se ne accorga (§14.2)",
            f"{motivo} x{n}: il 10/09 erano 746 skip 'ft_cs no_model_lambdas' e "
            f"la seconda gamba non e' MAI partita."))
    return out


@dataclass
class Referto:
    """L'esito su UNA partita. Stessa forma del referto di Mike: il punto
    d'ingresso unico (`Betfair/stream/backtest/certifica.py`) stampa questo."""

    event_id: str
    tick: int = 0
    decisioni: int = 0
    azioni: int = 0
    stati_visti: List[str] = field(default_factory=list)
    motivi: Dict[str, int] = field(default_factory=dict)
    andamento: "Andamento" = field(default_factory=lambda: Andamento())
    ordini_piazzati: int = 0
    righe_scritte: int = 0
    sollecitati: Dict[str, int] = field(default_factory=dict)
    violazioni: List[Violazione] = field(default_factory=list)
    note: List[str] = field(default_factory=list)

    @property
    def pulita(self) -> bool:
        return not self.violazioni

    def per_codice(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for v in self.violazioni:
            out[v.codice] = out.get(v.codice, 0) + 1
        return out


# ===========================================================================
# K. LA CONSAPEVOLEZZA — cio' che il bot CREDE contro cio' che il MERCATO dice
#
# Reperto portato da Mike (catalogo §7, punti 36-37 di `PROCESSO_STANDARD_BOT.md`):
# i controlli che guardano solo la DECISIONE non vedono i cinque difetti del
# 15/09, perche' quei difetti non stanno nella decisione — stanno nel giro dopo,
# quando il bot rilegge l'ordine e non si riconosce. La famiglia K guarda
# esattamente li': DOPO ogni giro si mettono a confronto le righe di
# `omega_trades` con gli ordini veri del banco.
#
# Modello: `Betfair/mike/certificazione.py:779-853`. Le regole sono le stesse
# perche' i difetti sono gli stessi; cambiano i nomi delle cose (Omega ha righe
# `omega_trades` con `bet_id`, `size`, `price`, `meta`, non le `Leg` di Mike).
# ===========================================================================
_REGISTRO_BANCO: List[Tuple[str, str]] = []
_FUNZIONI_BANCO: Dict[str, Callable] = {}


def _controllo_banco(codice: str, regola: str):
    def _reg(fn):
        _REGISTRO_BANCO.append((codice, regola))
        _FUNZIONI_BANCO[codice] = fn
        return fn
    return _reg


def _refs_di_riga(r: Dict[str, Any]) -> set:
    """Le grafie con cui QUESTA riga puo' essere stata piazzata: il ref per
    gamba (`omega-t<id>`) e quelli che il meta ha registrato. Cercarne una sola
    e' come il difetto 1 del 15/09, ma dal lato di chi controlla."""
    fuori = set()
    try:
        fuori.update(str(x) for x in E.candidate_customer_refs(r) if x)
    except Exception:  # noqa: BLE001
        pass
    meta = r.get("meta") or {}
    for chiave in ("customer_ref", "flumine_client_ref", "close_ref"):
        v = meta.get(chiave)
        if v:
            fuori.add(str(v))
    return fuori


def _ordine_di_riga(ordini: Dict[str, Any], r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for ref in _refs_di_riga(r):
        o = (ordini or {}).get(ref)
        if o is not None:
            return o
    bet = r.get("bet_id")
    if bet:
        for o in (ordini or {}).values():
            if str(o.get("bet_id") or "") == str(bet):
                return o
    return None


def _e_viva(r: Dict[str, Any]) -> bool:
    return str(r.get("status") or "") in ("open", "pending", "placed")


# stati in cui la riga DICHIARA di non essere una posizione: li' la colonna
# `size` e' la size CHIESTA, non un abbinamento in cui il bot crede. Accusarla
# vorrebbe dire accusare il bot di aver detto il contrario di quello che ha detto.
# Falso positivo trovato dal banco il 16/09 (scenario `cashout-globale` sulla
# sintetica: 119 violazioni su una riga di chiusura gia' marcata 'error' dopo un
# `place_rifiutato`).
_STATI_NON_POSIZIONE = ("error", "rejected", "cancelled", "voided", "skipped")


@_controllo_banco("K1", "cio' che il bot CREDE di una gamba coincide con cio' che il "
                        "MERCATO dice del suo ordine (abbinato e prezzo medio)")
def _k1(righe, ordini, rifiutati):
    for r in righe or ():
        meta = r.get("meta") or {}
        if meta.get("reconciling"):
            continue                       # esito ignoto: il dubbio e' dichiarato
        if str(r.get("status") or "") in _STATI_NON_POSIZIONE:
            continue                       # il bot ha gia' dichiarato il fallimento
        o = _ordine_di_riga(ordini, r)
        if o is None:
            continue
        if str(o.get("status") or "") == "EXECUTABLE":
            continue                       # ancora vivo: il bot legge alla SUA cadenza
        abbinato = float(o.get("size_matched") or 0.0)
        creduto = float(r.get("size") or 0.0)
        if abs(creduto - abbinato) > 0.011:
            return (f"riga #{r.get('id')}: il bot crede {creduto} abbinato, il mercato "
                    f"dice {round(abbinato, 2)} (ordine {o.get('status')})")
        if abbinato > 0.009:
            medio = o.get("avg_price_matched") or o.get("average_price_matched")
            if medio and abs(float(r.get("price") or 0.0) - float(medio)) > 0.011:
                return (f"riga #{r.get('id')}: prezzo {r.get('price')} contro "
                        f"{medio} dichiarato dal mercato — e' il difetto 3 del 15/09 "
                        f"(`avg_price` al posto di `avg_price_matched`)")
    return None


@_controllo_banco("K2", "una gamba il cui ordine Betfair ha RIFIUTATO non resta mai viva "
                        "(difetto 2 del 15/09: `res.ok` mai letto)")
def _k2(righe, ordini, rifiutati):
    if not rifiutati:
        return None
    for r in righe or ():
        meta = r.get("meta") or {}
        if not (_e_viva(r) or meta.get("reconciling")):
            continue
        if not (_refs_di_riga(r) & set(rifiutati)):
            continue
        if _ordine_di_riga(ordini, r) is None:
            stato = "a esito ignoto" if meta.get("reconciling") else "viva"
            return (f"riga #{r.get('id')}: Betfair ha RIFIUTATO l'ordine e nessun ordine "
                    f"esiste a mercato, ma la riga e' ancora {stato} "
                    f"(status='{r.get('status')}')")
    return None


@_controllo_banco("K3", "il riferimento con cui il bot ha piazzato si RILEGGE con la "
                        "stessa grafia (difetto 1 del 15/09: `customerOrderRef` vs "
                        "`customer_order_ref`)")
def _k3(righe, ordini, rifiutati):
    for ref, o in (ordini or {}).items():
        letto = o.get("customer_order_ref")
        if letto is None:
            return (f"l'ordine '{ref}' esiste a mercato ma il suo riferimento non si "
                    f"rilegge: la chiave `customer_order_ref` non c'e' "
                    f"(chiavi presenti: {sorted(o)[:8]})")
        if str(letto) != str(ref):
            return f"l'ordine '{ref}' si rilegge col riferimento '{letto}'"
    return None


@_controllo_banco("K4", "ogni gamba di CHIUSURA dichiara la riga di apertura che chiude "
                        "(difetto 5 del 15/09: `closes_trade_id` nella COLONNA, non "
                        "solo nel meta)")
def _k4(righe, ordini, rifiutati):
    for r in righe or ():
        if str(r.get("side") or "").lower() != "back":
            continue                       # solo le righe di chiusura vere
        meta = r.get("meta") or {}
        if r.get("closes_trade_id") is None:
            dove = ("nel meta" if meta.get("closes_trade_id") is not None
                    else "da nessuna parte")
            return (f"riga #{r.get('id')} e' una chiusura (back) e `closes_trade_id` "
                    f"sta {dove}, non nella COLONNA")
    return None


@_controllo_banco("K5", "una riga APERTA che dichiara un `bet_id` ha sempre quel "
                        "l'ordine a mercato (nessuna posizione fantasma)")
def _k5(righe, ordini, rifiutati):
    for r in righe or ():
        meta = r.get("meta") or {}
        if str(r.get("status") or "") != "open" or meta.get("reconciling"):
            continue
        # SI ACCUSA SOLO CHI DICHIARA UN `bet_id`. Falso positivo trovato dal
        # banco il 16/09: nello scenario `paper` il fill viene da
        # `omega_engine.paper_fill` (uno snapshot, non un ordine), quindi la riga
        # e' aperta senza `bet_id` e a mercato non c'e' niente — ed e' giusto
        # cosi', e' la divergenza P4 dichiarata. Accusare li' voleva dire
        # accusare il bot di una cosa che il BANCO ha deciso: 242 violazioni
        # false in un giro. Una riga aperta SENZA bet_id in live e' un problema
        # diverso, e lo guarda la famiglia della riconciliazione (F1/F2).
        if not r.get("bet_id"):
            continue
        if _ordine_di_riga(ordini, r) is None:
            return (f"riga #{r.get('id')} risulta APERTA (bet_id {r.get('bet_id')}) ma a "
                    f"mercato non esiste nessun ordine con i suoi riferimenti "
                    f"{sorted(_refs_di_riga(r))[:3]}")
    return None


@_controllo_banco("K6", "il RESIDUO non abbinato e' dichiarato: una riga aperta con "
                        "meno del chiesto lo dice (C.10/C.12a)")
def _k6(righe, ordini, rifiutati):
    for r in righe or ():
        meta = r.get("meta") or {}
        chiesto = meta.get("requested_size")
        if chiesto is None:
            continue
        try:
            manca = float(chiesto) - float(r.get("size") or 0.0)
        except (TypeError, ValueError):
            continue
        if manca <= 0.011:
            continue
        if meta.get("size_remaining") is None and not meta.get("parziale"):
            return (f"riga #{r.get('id')}: chiesti {chiesto}, abbinati {r.get('size')} "
                    f"e il residuo {round(manca, 2)} non e' dichiarato da nessuna parte")
    return None


# colonne della migrazione trades_consapevolezza_ordine_2026-09-16.sql: le
# STESSE cinque di execution.COLONNE_CONSAPEVOLEZZA (safe_strategy/execution.py).
_COLONNE_CONSAPEVOLEZZA = ("size_requested", "size_matched", "size_remaining",
                           "avg_price_matched", "betfair_updated_at")


@_controllo_banco("K7", "il RESIDUO, il CHIESTO e l'ISTANTE di Betfair non "
                        "restano NULL sulla COLONNA quando il meta ha GIA' il "
                        "numero giusto (la scrittura non e' passata da "
                        "X.aggiorna_trade)")
def _k7(righe, ordini, rifiutati):
    """REPERTO 17/09: su Safe (bot_service.py, trade live #297) la conferma di
    apertura chiamava ``db.update_trade`` DIRETTO invece di ``X.aggiorna_trade``:
    ``meta`` portava gia' size_richiesta/size_residua/istante di Betfair
    corretti, ma le colonne dedicate della migrazione
    ``trades_consapevolezza_ordine_2026-09-16.sql`` restavano NULL sulla riga —
    stesso difetto trovato (e corretto) sul percorso flumine di Omega
    (``_mirror_fill``/``_flumine_confirm``, 17/09): il meta aveva gia'
    ``size_remaining``/``betfair_updated_at``, la colonna no.

    Guarda SOLO tre colonne (``size_requested``, ``size_remaining``,
    ``betfair_updated_at``): sono le uniche con un corrispondente INEQUIVOCABILE
    nel meta (``requested_size``/``size_remaining``/``betfair_updated_at``,
    scritti da ``_place_one``/``_flumine_confirm``). ``size_matched`` e
    ``avg_price_matched`` non hanno un meta equivalente distinto (il loro
    corrispondente storico e' ``size``/``price`` della riga stessa, gia'
    incrociati contro il mercato vero da K1): pretenderli qui SENZA un secondo
    numero indipendente con cui confrontarli accuserebbe anche righe scritte
    PRIMA che queste colonne esistessero (falso positivo, stesso genere di
    quelli gia' trovati dal banco il 16/09 su K1/K5 — vedi sopra).

    Si accusa solo quando il meta HA il numero e la colonna no: un meta muto
    (nessun requested_size/size_remaining/betfair_updated_at da nessuna parte,
    come le righe sintetiche pre-migrazione) resta in silenzio — non e' prova
    di niente, e' solo un fixture che non parla di questo.

    Non si accusano le righe 'reconciling' (esito ancora ignoto, dichiarato), ne'
    le righe non ancora confermate (``status`` diverso da 'open'/'hedged': una
    riserva 'pending' porta gia' ``meta.requested_size`` PRIMA che
    ``X.aggiorna_trade`` sia mai stato chiamato — accusarla vorrebbe dire
    accusare una riga che semplicemente non e' ancora arrivata alla conferma),
    ne' le righe senza ``bet_id`` (K5: falso positivo gia' trovato dal banco il
    16/09, il paper storico via ``paper_fill``/snapshot non ha un ordine vero)."""
    _MAPPA = (("size_requested", "requested_size"),
              ("size_remaining", "size_remaining"),
              ("betfair_updated_at", "betfair_updated_at"))
    for r in righe or ():
        meta = r.get("meta") or {}
        if meta.get("reconciling"):
            continue
        if str(r.get("status") or "") not in ("open", "hedged"):
            continue
        if not r.get("bet_id"):
            continue
        mancanti = [colonna for colonna, chiave_meta in _MAPPA
                    if r.get(colonna) is None and meta.get(chiave_meta) is not None]
        if mancanti:
            return (f"riga #{r.get('id')}: il meta ha gia' "
                    f"{[m for _c, m in _MAPPA if meta.get(m) is not None]}, ma la "
                    f"COLONNA resta NULL su {mancanti} (la scrittura non e' "
                    f"passata da X.aggiorna_trade)")
    return None


def verifica_consapevolezza(righe: Optional[List[Dict[str, Any]]],
                            ordini: Optional[Dict[str, Any]],
                            rifiutati: Optional[set] = None,
                            sollecitati: Optional[Dict[str, int]] = None,
                            stato: str = "giro") -> List[Violazione]:
    """I controlli K su UN giro: la memoria del bot contro il mercato.

    Il chiamante e' il replay, subito DOPO il giro del servizio: li' ci sono sia
    le righe di `omega_trades` sia gli ordini veri di flumine. `ordini` e'
    {ref chiesto: riga normalizzata da `MercatoFlumine._riga`}.
    """
    out: List[Violazione] = []
    if not righe and not ordini:
        return out
    rif = set(rifiutati or ())
    for codice, regola in _REGISTRO_BANCO:
        if sollecitati is not None:
            sollecitati[codice] = sollecitati.get(codice, 0) + 1
        try:
            det = _FUNZIONI_BANCO[codice](righe or [], ordini or {}, rif)
        except Exception as ex:  # noqa: BLE001
            out.append(Violazione(f"{codice}-ERRORE", regola,
                                  f"il controllo e' esploso: {type(ex).__name__}: {ex}",
                                  stato))
            continue
        if det:
            out.append(Violazione(codice, regola, det, stato))
    return out


def elenco_controlli_banco() -> List[Tuple[str, str]]:
    """(codice, regola) dei controlli di CONSAPEVOLEZZA (famiglia K)."""
    return list(_REGISTRO_BANCO)
