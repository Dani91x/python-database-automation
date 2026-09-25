"""CERTIFICAZIONE DI SAFE TENNIS — rispetta la strategia per cui e' stata scritta?

Non si misura se GUADAGNA: si misura se **si comporta come dice la specifica**,
giro per giro, sui dati veri di una partita registrata.

LA FONTE DI VERITA' e' `SPEC_STRATEGIA_S.md` §3 (TENNIS), letta insieme al
riscontro gia' firmato `Betfair/safe_strategy/RISCONTRO_TENNIS_2026-09-14.md`
(che dichiara quali aggiunte del codice RESTRINGONO la specifica e quali voci
sono eccezioni decise dall'utente) e a `HANDOFF_CONTROL_ROOM.md` §2 (le cinque
operazioni live del 14/09: «le chiusure si abbinano al prezzo ESATTO del
segnale», 0 tick di scostamento).

OGNI CONTROLLO DICHIARA `quando=` HA DAVVERO UN CASO. Senza, un referto «zero
violazioni» e' ambiguo: non si distingue un controllo che ha guardato e
approvato da uno che non ha mai avuto l'occasione di guardare. Sono due cose
diversissime — la prima e' una garanzia, la seconda e' un buco — e finche' si
contano solo le violazioni sembrano identiche
(PROCESSO_STANDARD_BOT.md §6.7).

Le famiglie:

  T. la strategia del manuale (ingresso, uscite, esclusioni, stake)
  J. i cinque difetti di consapevolezza dell'ordine del 15/09 (catalogo §7.1-7)
  C. la consapevolezza dell'ordine C.12a (chiesto / abbinato / residuo / medio)
  S. il servizio (modalita' per strategia, bot fermo, feed stantio)
  A. il giro del servizio
  P. il comportamento nel tempo (i loop non si vedono in un istante)

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# LA SOGLIA E I PARAMETRI SONO QUELLI DEL CODICE DI PRODUZIONE, non copie:
# un controllo che si scrivesse in casa i numeri della spec certificherebbe se
# stesso. `engine.DEFAULT_PARAMS['tennis']` e `exits.DEFAULT_EXIT_PARAMS` sono
# le stesse strutture che il bot fonde con i parametri dell'utente.
from . import bot_service as BS
from . import certificazione_k as K
from . import engine as E
from . import execution as X
from . import exits as XE

# ⚠️ LE CHIAVI SI IMPORTANO DAL VERO, NON SI RISCRIVONO.
# La prima versione di questo file cercava `meta["exit_proposta"]`, ma il
# servizio scrive `meta["exit_proposal"]` (`bot_service.PROPOSTA_KEY`): il
# controllo T7 non vedeva MAI una proposta viva e accusava il bot di non uscire
# proprio nello scenario in cui l'utente aveva chiesto di non farlo uscire. E'
# il difetto 27 del catalogo applicato ai CONTROLLI, ed e' il falso positivo
# contro cui mette in guardia §6.7 del processo.
CHIAVE_PROPOSTA = BS.PROPOSTA_KEY        # "exit_proposal"
CHIAVE_HOLD = BS.HOLD_KEY                # "exit_hold"


# ---------------------------------------------------------------------------
# il referto
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Violazione:
    """Una regola della specifica non rispettata, col contesto per capirla."""

    codice: str                 # es. "T1"
    regola: str                 # la regola, in una riga, con la voce della spec
    dettaglio: str              # che cosa e' successo davvero
    quando: str = ""            # istante / punteggio in cui e' successo

    def __str__(self) -> str:
        return f"{self.codice} [{self.quando}] {self.regola} -> {self.dettaglio}"


@dataclass
class Osservazione:
    """TUTTO cio' che e' successo in UN giro del servizio, come e' successo.

    E' la superficie su cui lavorano i controlli: niente viene ricostruito qui
    dentro: ogni campo e' copiato da un oggetto di produzione (la riga dello
    scanner, il contesto vero di `build_tennis_ctx_from_scan`, la valutazione
    vera di `evaluate_tennis`, le righe del database in memoria, gli ordini
    veri di flumine).
    """

    now_ts: float = 0.0
    quando: str = ""                       # ora + punteggio, per il referto
    scenario: str = "base"
    stato_bot: str = "running"             # `control.status`
    modo_servizio: str = "paper"           # `control.mode`
    modo_strategia: str = "paper"          # `modalita_di_strategia('tennis', ...)`
    params: Dict[str, Any] = field(default_factory=dict)
    xp: Dict[str, Any] = field(default_factory=dict)
    row: Optional[Dict[str, Any]] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    feed_fresco: bool = True
    ctx: Any = None                        # TennisMatchCtx vero
    valutazione: Any = None                # VariantEvaluation vera
    segnali: List[Any] = field(default_factory=list)
    trades: List[Dict[str, Any]] = field(default_factory=list)
    # righe che in QUESTO giro sono nate o hanno cambiato stato
    aperture: List[Dict[str, Any]] = field(default_factory=list)
    chiusure: List[Dict[str, Any]] = field(default_factory=list)
    # ordini VERI di flumine nati in questo giro, nella forma di
    # `omega_market.list_current_orders` (snake_case, mai camelCase)
    ordini: List[Dict[str, Any]] = field(default_factory=list)
    # TUTTI gli ordini ancora VIVI a mercato in questo istante (EXECUTABLE):
    # e' la fotografia di cio' che Betfair ha davvero sul book, non di cio' che
    # il bot crede di avere. Serve al controllo L1.
    ordini_vivi: List[Dict[str, Any]] = field(default_factory=list)
    # ordini il cui `size_cancelled` e' CRESCIUTO in questo giro: e' un annullo
    # avvenuto adesso, e serve a riconoscere la sostituzione cancel+place.
    cancellati: List[Dict[str, Any]] = field(default_factory=list)
    rifiutati: List[Dict[str, Any]] = field(default_factory=list)
    attivita: List[Tuple[str, Dict[str, Any], Any]] = field(default_factory=list)
    proposte: List[Dict[str, Any]] = field(default_factory=list)
    # QUANDO L'UTENTE HA CHIUSO, saputo dal REPLAY e non dal bot: {event_id: ts}.
    # ⚠️ lezione del 16/09 (Esito C.4): un controllo che dipende dalla
    # CONFESSIONE del bot non certifica. Se il bot smettesse di accorgersi della
    # chiusura fatta fuori dall'app, il marcatore `meta.chiuso_dall_utente` non
    # verrebbe scritto e un controllo che guarda solo quello resterebbe zitto:
    # misurato, va a «non lo so» mentre il bot continua a operare.
    chiuso_dall_utente: Dict[str, float] = field(default_factory=dict)
    errore_servizio: str = ""

    # ------------------------------------------------------------ comodita'
    def kinds(self) -> List[str]:
        return [str(k) for k, _p, _e in self.attivita]

    def attivita_di(self, kind: str) -> List[Dict[str, Any]]:
        return [dict(p or {}) for k, p, _e in self.attivita if str(k) == str(kind)]


Controllo = Callable[[Osservazione], Optional[str]]
_REGISTRO: List[Tuple[str, str, Controllo, Optional[Controllo]]] = []


def _controllo(codice: str, regola: str, quando: Optional[Controllo] = None):
    """Registra un controllo e, con `quando`, dichiara QUANDO ha un caso."""

    def _reg(fn: Controllo) -> Controllo:
        _REGISTRO.append((codice, regola, fn, quando))
        return fn

    return _reg


# ---------------------------------------------------------------------------
# utilita' comuni
# ---------------------------------------------------------------------------
def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def _par_tennis(oss: Osservazione) -> Dict[str, Any]:
    """La sezione `tennis` dei parametri REALMENTE in uso in questo giro."""
    p = oss.params.get("tennis") if isinstance(oss.params, dict) else None
    return dict(p) if isinstance(p, dict) else dict(E.DEFAULT_PARAMS["tennis"])


def _soglia_take_profit(oss: Osservazione) -> float:
    v = _num(oss.xp.get("tennis_take_profit_min_odds"))
    return v if v is not None else float(
        XE.DEFAULT_EXIT_PARAMS["tennis_take_profit_min_odds"])


def _e_tennis(tr: Dict[str, Any]) -> bool:
    return str(tr.get("strategy") or "") == "tennis"


def _traccia(tr: Dict[str, Any]) -> Dict[str, Any]:
    t = (tr.get("meta") or {}).get(XE.TRACK_KEY)
    return dict(t) if isinstance(t, dict) else {}


def _aperture_tennis(oss: Osservazione) -> List[Dict[str, Any]]:
    """Le APERTURE di tennis nate in questo giro (mai le gambe di chiusura).

    ⚠️ Le righe con `meta.ingresso_dichiarato` sono ESCLUSE: sono le posizioni
    che il replay apre di propria iniziativa quando su quella registrazione la
    strategia non ha mai le sue condizioni (dichiarazione 3 di
    `tools/replay_tennis.py`). Giudicare l'INGRESSO su una riga che il bot non
    ha deciso vorrebbe dire accusarlo di una scelta del banco. Tutto cio' che
    viene DOPO (uscite, ordini, consapevolezza) resta giudicato.
    """
    return [a for a in oss.aperture
            if _e_tennis(a.get("trade") or {})
            and not (a.get("trade") or {}).get("closes_trade_id")
            and not ((a.get("trade") or {}).get("meta") or {}).get("ingresso_dichiarato")]


def _chiusure_tennis(oss: Osservazione) -> List[Dict[str, Any]]:
    return [c for c in oss.chiusure if _e_tennis(c.get("trade") or {})]


def _posizioni_tennis(oss: Osservazione) -> List[Dict[str, Any]]:
    """Le POSIZIONI di tennis (aperture, non gambe di chiusura) nel database."""
    return [t for t in oss.trades
            if _e_tennis(t) and t.get("closes_trade_id") is None]


def _uscita_chiesta(trade: Dict[str, Any]) -> Dict[str, Any]:
    """`meta.exit_requested` — la REGOLA del manuale che ha deciso l'uscita.

    ⚠️ La gamba di chiusura porta `meta.exit_kind`, che e' il vocabolario della
    UI (`exits.ui_exit_kind`): una chiusura integrale in profitto diventa
    'greenup', e 'mandatory' diventa 'forced'. Per giudicare la REGOLA serve il
    `kind` originale, che il servizio scrive sull'APERTURA
    (`bot_service._persist_exit_request`)."""
    r = (trade.get("meta") or {}).get(XE.REQUEST_KEY)
    return dict(r) if isinstance(r, dict) else {}


def _padre_di(oss: Osservazione, chiusura: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tr = chiusura.get("trade") or {}
    pid = tr.get("closes_trade_id") or (tr.get("meta") or {}).get("closes_trade_id")
    if pid is None:
        return None
    for t in oss.trades:
        if str(t.get("id")) == str(pid):
            return t
    return None


def _check_di(oss: Osservazione, ident: str):
    ev = oss.valutazione
    for c in (getattr(ev, "checks", None) or ()):
        if getattr(c, "id", None) == ident:
            return c
    return None


# ===========================================================================
# T. LA STRATEGIA DEL MANUALE (SPEC_STRATEGIA_S.md §3)
# ===========================================================================
@_controllo("T1", "SPEC §3 tennis: si PUNTA (back) chi sta vincendo, alla quota "
                  "della banda d'ingresso (backMin..backMax)",
            quando=lambda o: bool(_aperture_tennis(o)))
def _t1(oss: Osservazione) -> Optional[str]:
    par = _par_tennis(oss)
    lo, hi = _num(par.get("backMin")), _num(par.get("backMax"))
    for a in _aperture_tennis(oss):
        tr = a["trade"]
        lato = str(tr.get("side") or "").lower()
        if lato != "back":
            return (f"trade {tr.get('id')}: lato '{lato}', ma la specifica per il "
                    f"tennis implementata e' il BACK sul leader "
                    f"(RISCONTRO_TENNIS: 'BACK sul leader')")
        # il prezzo CHIESTO (quello del segnale), non quello abbinato: e' su
        # quello che la banda della spec si pronuncia
        chiesto = _num((tr.get("meta") or {}).get("price_richiesto"))
        if chiesto is None:
            chiesto = _num(((tr.get("meta") or {}).get("esecuzione") or {}).get("price_richiesto"))
        if chiesto is None:
            chiesto = _num(tr.get("price"))
        if chiesto is None:
            return f"trade {tr.get('id')}: aperto senza prezzo leggibile"
        if lo is not None and chiesto < lo - 1e-9:
            return f"trade {tr.get('id')}: back a {chiesto} sotto backMin {lo}"
        if hi is not None and chiesto > hi + 1e-9:
            return f"trade {tr.get('id')}: back a {chiesto} sopra backMax {hi}"
    return None


@_controllo("T2", "SPEC §3 tennis: si entra con 1 set vinto e 2+ game di "
                  "vantaggio nel set in corso, dallo STESSO giocatore",
            quando=lambda o: bool(_aperture_tennis(o)))
def _t2(oss: Osservazione) -> Optional[str]:
    par = _par_tennis(oss)
    sets = (oss.payload or {}).get("sets")
    games = (oss.payload or {}).get("games")
    if not isinstance(sets, dict) or not isinstance(games, dict):
        return ("apertura con set/game assenti dal feed: la specifica chiede "
                "«1 set vinto + 2-3 game di vantaggio», qui il punteggio non c'e'")
    s1, s2 = int(sets.get("p1") or 0), int(sets.get("p2") or 0)
    g1, g2 = int(games.get("p1") or 0), int(games.get("p2") or 0)
    diff = s1 - s2
    if abs(diff) < int(par.get("setsLeadMin") or 1):
        return f"apertura con set {s1}-{s2}: vantaggio di set sotto setsLeadMin"
    leader_p1 = diff > 0
    lead = (g1 - g2) if leader_p1 else (g2 - g1)
    if lead < int(par.get("gamesLeadMin") or 2):
        return (f"apertura con game {g1}-{g2}: il giocatore avanti nei set ha "
                f"{lead} game di vantaggio, sotto gamesLeadMin "
                f"{par.get('gamesLeadMin')}")
    giocati = int(par.get("setsPlayedMax") or 0)
    if giocati > 0 and (s1 + s2) > giocati:
        return (f"apertura con {s1 + s2} set gia' giocati (max {giocati}): il "
                f"vantaggio di UN set deve venire dall'UNICO set giocato")
    return None


@_controllo("T3", "SPEC §3 (aggiunta prudenziale, RISCONTRO): il punteggio deve "
                  "essere STABILE da scoreConfirmSec prima di entrare",
            quando=lambda o: bool(_aperture_tennis(o)))
def _t3(oss: Osservazione) -> Optional[str]:
    par = _par_tennis(oss)
    soglia = _num(par.get("scoreConfirmSec"))
    osservato = _num(getattr(oss.ctx, "score_observed_sec", None))
    if soglia is None:
        return None
    if osservato is None:
        return ("apertura senza sapere da quanto il punteggio e' fermo "
                "(score_observed_sec assente): l'anti-blip non ha potuto dire nulla")
    if osservato < soglia - 1e-9:
        return (f"apertura con punteggio fermo da {osservato:.1f}s, sotto "
                f"scoreConfirmSec {soglia}")
    return None


@_controllo("T4", "SPEC §3 «da evitare»: doppi, Slam maschili (5 set), "
                  "competizioni escluse — nessun ingresso",
            quando=lambda o: bool(_aperture_tennis(o)))
def _t4(oss: Osservazione) -> Optional[str]:
    par = _par_tennis(oss)
    p1 = str(getattr(oss.ctx, "p1", "") or "")
    p2 = str(getattr(oss.ctx, "p2", "") or "")
    if par.get("excludeDoubles") and ("/" in p1 or "/" in p2):
        return f"apertura su un DOPPIO ({p1} / {p2}): la specifica lo esclude"
    comp = getattr(oss.ctx, "competition", None)
    if par.get("excludeBestOf5"):
        if comp is None:
            return ("apertura senza il nome della competizione: il filtro «al "
                    "meglio dei 3 set» non ha potuto pronunciarsi, e la "
                    "specifica chiede di evitare gli Slam maschili")
        sets = (oss.payload or {}).get("sets") or {}
        coppia = (int(sets.get("p1") or 0), int(sets.get("p2") or 0))
        if E.detect_best_of(str(comp), coppia) == 5:
            return f"apertura su un match al meglio dei 5 set ({comp})"
    escluse = [str(k).lower() for k in (par.get("excludeCompetitions") or [])]
    if escluse and comp is not None:
        hit = next((k for k in escluse if k in str(comp).lower()), None)
        if hit:
            return f"apertura su una competizione esclusa ('{hit}' in '{comp}')"
    return None


def _take_profit_chiesti(oss: Osservazione) -> List[Dict[str, Any]]:
    """Le posizioni per cui il servizio ha CHIESTO un take profit."""
    return [t for t in _posizioni_tennis(oss)
            if str(_uscita_chiesta(t).get("kind") or "") == "profit"]


@_controllo("T5", "RISCONTRO_TENNIS: il take profit NON si prende sotto "
                  "tennis_take_profit_min_odds (sotto e' una perdita garantita)",
            quando=lambda o: bool(_take_profit_chiesti(o)))
def _t5(oss: Osservazione) -> Optional[str]:
    soglia = _soglia_take_profit(oss)
    for t in _take_profit_chiesti(oss):
        prezzo = _num((_traccia(t).get("entry_price"))) or _num(t.get("price"))
        if prezzo is None:
            continue
        if prezzo < soglia - 1e-9:
            return (f"take profit chiesto sulla posizione {t.get('id')} aperta a "
                    f"{prezzo}: sotto {soglia} il guadagno massimo e' piu' piccolo "
                    f"dello spread da attraversare (17 su 17 misurate il 13/09)")
    return None


def _sotto_soglia(oss: Osservazione) -> List[Dict[str, Any]]:
    soglia = _soglia_take_profit(oss)
    out = []
    for t in _posizioni_tennis(oss):
        if str(t.get("status") or "") not in ("open", "hedged", "won", "lost", "settled"):
            continue
        prezzo = _num(_traccia(t).get("entry_price")) or _num(t.get("price"))
        if prezzo is not None and prezzo < soglia - 1e-9:
            out.append(t)
    return out


@_controllo("T6", "RISCONTRO_TENNIS: un ingresso a 1,01-1,02 si PORTA A FINE "
                  "PARTITA (nessuna chiusura volontaria)",
            quando=lambda o: bool(_sotto_soglia(o)))
def _t6(oss: Osservazione) -> Optional[str]:
    soglia = _soglia_take_profit(oss)
    for t in _sotto_soglia(oss):
        req = _uscita_chiesta(t)
        kind = str(req.get("kind") or "")
        # perdita, rosso e uscita obbligatoria escono sempre: la soglia di quota
        # vale solo sulle uscite VOLONTARIE
        if kind in ("profit", "time") and req.get("sent"):
            return (f"chiusura volontaria ({kind}) della posizione {t.get('id')} "
                    f"aperta a {_num(t.get('price'))}: sotto {soglia} si porta a "
                    f"fine partita")
    return None


def _obbligo_maturo(oss: Osservazione) -> List[Dict[str, Any]]:
    """Le posizioni per cui la regola dell'uscita OBBLIGATORIA e' matura."""
    out: List[Dict[str, Any]] = []
    for t in oss.trades:
        if not _e_tennis(t) or t.get("closes_trade_id"):
            continue
        if str(t.get("status") or "") != "open":
            continue
        tr = _traccia(t)
        livello = tr.get("set_lead_lost")
        if livello is None:
            livello = bool(tr.get("games_level"))
        if int(tr.get("consecutive_lost") or 0) >= 2 and bool(livello):
            out.append(t)
    return out


@_controllo("T7", "SPEC §3 tennis: due game persi di fila E vantaggio perso nel "
                  "set = uscita OBBLIGATORIA, senza eccezioni",
            quando=lambda o: bool(_obbligo_maturo(o)))
def _t7(oss: Osservazione) -> Optional[str]:
    for t in _obbligo_maturo(oss):
        meta = t.get("meta") or {}
        # trattenuta dalla decisione a modello: sarebbe un'eccezione, e la
        # specifica dice «senza eccezioni»
        if isinstance(meta.get(CHIAVE_HOLD), dict):
            return (f"posizione {t.get('id')}: uscita OBBLIGATORIA matura ma "
                    f"trattenuta da una decisione a modello (exit_hold) — "
                    f"'mandatory' non appartiene a PROFIT_KINDS e non deve "
                    f"passare di li'")
        # trattenuta dal cancelletto di approvazione: e' una scelta DICHIARATA
        # dell'utente (14/09), non un difetto: la si dichiara in T7-APPROVAZIONE
        if isinstance(meta.get(CHIAVE_PROPOSTA), dict):
            continue
        chiesta = str(_uscita_chiesta(t).get("kind") or "")
        if chiesta == "mandatory":
            continue
        # il servizio puo' legittimamente ASPETTARE (feed non fresco, mercato
        # sospeso, prezzi assenti): lo scrive, e allora non e' una rinuncia
        if _traccia(t).get("wait_reason"):
            continue
        return (f"posizione {t.get('id')}: due game persi di fila e vantaggio perso "
                f"nel set, ma l'uscita chiesta e' '{chiesta or 'nessuna'}' invece di "
                f"'mandatory' e non c'e' nessun motivo di attesa dichiarato")
    return None


@_controllo("T7-APPROVAZIONE",
            "CERT. 14/09: col cancelletto acceso anche l'uscita OBBLIGATORIA "
            "resta ferma finche' un essere umano non la promuove (scelta "
            "dichiarata dell'utente, non un difetto)",
            quando=lambda o: bool(o.params.get("tennis_exit_approval"))
            and bool(_obbligo_maturo(o)))
def _t7_appr(oss: Osservazione) -> Optional[str]:
    fermi = [t for t in _obbligo_maturo(oss)
             if isinstance((t.get("meta") or {}).get(CHIAVE_PROPOSTA), dict)]
    if fermi:
        return ("DICHIARATA: uscita obbligatoria in attesa di firma sulle "
                f"posizioni {[t.get('id') for t in fermi]} (tennis_exit_approval "
                "acceso). Il bot fa quello che c'e' scritto.")
    return None


# Gli stati TERMINALI che il bot scrive davvero dopo il settlement
# (`bot_db.py:468,494`): 'won', 'lost', 'void'. Fino al 16/09 questo file
# cercava uno stato 'settled' che il bot non scrive in nessun punto: T8 non
# poteva avere un caso NEMMENO con il settlement funzionante — un controllo che
# non sa diventare rosso non certifica (PROCESSO §7).
STATI_REGOLATI = ("won", "lost", "void")


@_controllo("T8-DICHIARATA",
            "SPEC §3 tennis: «perdite dal 5% fino al 25% del capitale» — voce "
            "DESCRITTIVA, non comparabile a stake fisso (eccezione utente 14/09)",
            quando=lambda o: any(
                _e_tennis(t) and str(t.get("status") or "") in STATI_REGOLATI
                and (_num(t.get("pnl")) or 0.0) < 0
                for t in o.trades))
def _t8(oss: Osservazione) -> Optional[str]:
    """La banda 5-25% della SPEC e' DESCRITTIVA (eccezione dell'utente del
    14/09): con uno stake fisso una posizione che va a settlement perdente
    perde il 100% dello stake, e dirlo a ogni riga renderebbe ROSSA per sempre
    ogni certificazione del tennis su una scelta che l'utente ha gia' preso.
    Quello che qui si difende e' l'invariante che resta vero comunque: **un
    BACK non puo' perdere piu' dello stake**. Se il settlement scrive una
    perdita maggiore, e' il conto a essere sbagliato, ed e' money-critical
    (16/09: prima di questa riscrittura il controllo cercava uno stato
    `settled` che il bot non scrive, quindi non aveva MAI un caso)."""
    fuori: List[str] = []
    for t in oss.trades:
        if not _e_tennis(t) or str(t.get("status") or "") not in STATI_REGOLATI:
            continue
        pnl = _num(t.get("pnl"))
        stake = _num(t.get("size"))
        if pnl is None or stake is None or stake <= 0 or pnl >= 0:
            continue
        perc = abs(pnl) / stake * 100.0
        if str(t.get("side") or "").lower() == "back" and perc > 100.0 + 1e-6:
            fuori.append(f"trade {t.get('id')}: {perc:.1f}% dello stake "
                         f"(pnl {pnl}, stake {stake})")
    if fuori:
        return ("un BACK ha perso PIU' dello stake: impossibile, il conto del "
                "settlement e' sbagliato — " + " | ".join(fuori))
    return None


@_controllo("T9", "HANDOFF_CONTROL_ROOM §2 (certificato il 14/09 dal vivo): la "
                  "chiusura si abbina al PREZZO ESATTO del segnale, 0 tick di "
                  "scostamento sulle uscite non urgenti",
            quando=lambda o: any(
                ((c.get("trade") or {}).get("meta") or {}).get("esecuzione")
                for c in _chiusure_tennis(o)))
def _t9(oss: Osservazione) -> Optional[str]:
    for c in _chiusure_tennis(oss):
        tr = c["trade"]
        meta = tr.get("meta") or {}
        esec = meta.get("esecuzione")
        if not isinstance(esec, dict):
            continue
        scost = _num(esec.get("scorrimento_tick"))
        if scost is None:
            continue
        # i tick CONCESSI li dichiara il codice di produzione, non questo file:
        # `execution.ticks_for_exit` da' 0 alle uscite in profitto/tempo e un
        # tick alle urgenti (perdita, rosso, obbligo), dove il manuale dice
        # «esci subito e accetta». La REGOLA la porta l'apertura, non la gamba.
        padre = _padre_di(oss, c)
        regola = str(_uscita_chiesta(padre or {}).get("kind") or "")
        concessi = X.ticks_for_exit(regola or meta.get("exit_kind"))
        if scost > float(concessi) + 1e-9:
            return (f"chiusura {tr.get('id')} (regola '{regola}', UI "
                    f"'{meta.get('exit_kind')}'): abbinata {scost:+.0f} tick PEGGIO "
                    f"del prezzo chiesto, contro i {concessi} concessi a questo "
                    f"tipo di uscita (convenzione: positivo = peggio del chiesto)")
    return None


@_controllo("T10", "SPEC §3 «da evitare: finali» — Betfair NON pubblica il turno "
                   "per il tennis (399 mercati interrogati, zero con final/semi/"
                   "quarter): dato assente, controllo non esercitabile",
            quando=lambda o: bool(_turno_nel_feed(o)))
def _t10(oss: Osservazione) -> Optional[str]:
    # Se un giorno il turno comparisse nel feed, questo controllo si sveglia da
    # solo. Finche' non c'e', resta fra i MAI SOLLECITATI con la causa scritta:
    # e' un ⊘, non un «sano» (STATO_PRODUZIONE L5 / P6).
    turno = _turno_nel_feed(oss)
    if turno and _aperture_tennis(oss):
        return f"apertura su un turno dichiarato '{turno}': se e' una finale va esclusa"
    return None


def _turno_nel_feed(oss: Osservazione) -> Optional[str]:
    p = oss.payload or {}
    for chiave in ("round", "turno", "stage"):
        v = p.get(chiave)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


@_controllo("T11", "B.5: lo stake dell'ingresso e' quello della STRATEGIA "
                   "(stake.per_strategia['tennis'], poi stake.backSize)",
            quando=lambda o: bool(_aperture_tennis(o)))
def _t11(oss: Osservazione) -> Optional[str]:
    atteso = E.stake_di_strategia(oss.params, "tennis", "back")
    for a in _aperture_tennis(oss):
        tr = a["trade"]
        meta = tr.get("meta") or {}
        chiesto = _num(meta.get("size_richiesta"))
        if chiesto is None:
            chiesto = _num((meta.get("esecuzione") or {}).get("size_richiesta"))
        if chiesto is None:
            chiesto = _num(tr.get("size"))
        # la size puo' essere CAPPATA alla liquidita' (`meta.size_capped_from`):
        # in quel caso il confronto va fatto sul valore prima del cap
        prima = _num(meta.get("size_capped_from"))
        misurato = prima if prima is not None else chiesto
        if misurato is None:
            return f"trade {tr.get('id')}: aperto senza size leggibile"
        if abs(misurato - atteso) > 0.011:
            return (f"trade {tr.get('id')}: stake {misurato} invece di {atteso} "
                    f"(stake_di_strategia per 'tennis')")
    return None


@_controllo("T12", "PROCESSO §6.4: ogni ordine parte FILL_OR_KILL — nessun "
                   "residuo vivo a mercato dopo il piazzamento",
            quando=lambda o: bool(o.ordini))
def _t12(oss: Osservazione) -> Optional[str]:
    for o in oss.ordini:
        stato = str(o.get("status") or "")
        residuo = _num(o.get("size_remaining")) or 0.0
        abbinato = _num(o.get("size_matched")) or 0.0
        if stato == "EXECUTABLE" and residuo > 0.009:
            return (f"ordine {o.get('customer_order_ref')}: ancora EXECUTABLE con "
                    f"residuo {residuo} dopo il piazzamento — un FILL_OR_KILL non "
                    f"lascia niente a mercato (abbinato {abbinato})")
    return None


@_controllo("T13", "PROCESSO §6.4: una gamba a esito IGNOTO si riconcilia per "
                   "bet_id/ref, non si ri-piazza",
            quando=lambda o: any(XE.is_tennis(t) and X.is_reconciling(t)
                                 for t in o.trades))
def _t13(oss: Osservazione) -> Optional[str]:
    # `execution.is_reconciling`: riga 'pending' con
    # `meta.reason == 'place_exception_reconciling'` — la definizione di
    # produzione, non una copia (difetto 27 del catalogo: i finti parlano come
    # il vero, e i CONTROLLI pure).
    in_verifica = [t for t in oss.trades if XE.is_tennis(t) and X.is_reconciling(t)]
    for t in in_verifica:
        gemelli = [x for x in oss.trades
                   if x.get("id") != t.get("id")
                   and str(x.get("signal_key") or "") == str(t.get("signal_key") or "")
                   and str(x.get("event_id") or "") == str(t.get("event_id") or "")
                   and str(x.get("status") or "") in ("pending", "open")]
        if gemelli:
            return (f"trade {t.get('id')} a esito IGNOTO e in piu' {len(gemelli)} "
                    f"riga/e vive sullo stesso segnale: e' il difetto 4 del "
                    f"catalogo (ordine vivo dichiarato mai piazzato)")
    return None


# ===========================================================================
# J. I CINQUE DIFETTI DEL 15/09 (PROCESSO_STANDARD_BOT §7.1-7)
# ===========================================================================
@_controllo("J1", "catalogo §7.1/7.4: mai due gambe di chiusura IN VOLO sulla "
                  "stessa posizione (e' la forma del loop dei 32 green-up)",
            quando=lambda o: any(
                t.get("closes_trade_id") for t in o.trades))
def _j1(oss: Osservazione) -> Optional[str]:
    """⚠️ «IN VOLO», non «esistente». La definizione e' quella di produzione:
    `execution.hedge_state` blocca un nuovo cash-out solo quando esiste una
    chiusura 'pending' (`blocked`, `pending_ids`); le chiusure gia' ABBINATE
    (status 'open') sono legittime e anzi previste — e' il cash-out parziale
    piu' il RESIDUO (§4.2 della Costituzione). La prima versione contava anche
    quelle e accusava il bot di un loop dove c'era una chiusura di residuo:
    falso positivo del controllo, non difetto del bot."""
    vive: Dict[str, int] = {}
    for t in oss.trades:
        padre = t.get("closes_trade_id")
        if padre is None or str(t.get("status") or "") != "pending":
            continue
        k = str(padre)
        vive[k] = vive.get(k, 0) + 1
    doppie = {k: n for k, n in vive.items() if n > 1}
    if doppie:
        return (f"posizioni con piu' di una gamba di chiusura IN VOLO: {doppie}. "
                f"Con soldi veri sono ordini veri ripetuti.")
    return None


@_controllo("J2", "catalogo §7.2: `res.ok` si LEGGE — un place rifiutato o non "
                  "abbinato non diventa mai una posizione aperta",
            # ⚠️ IL CONTROLLO NON PUO' DIPENDERE DALLA CONFESSIONE DEL BOT.
            # La prima versione si sollecitava solo con `place_rifiutato` scritto
            # nell'attivita': togliendo la lettura di `res.ok` sparivano insieme
            # il difetto E il controllo, e il referto restava verde. La verita'
            # sta nell'ORDINE di flumine (cioe' di Betfair), non nel log.
            quando=lambda o: bool(o.rifiutati)
            or bool(o.attivita_di("place_rifiutato"))
            or any(a.get("ordine") for a in (o.aperture + o.chiusure)))
def _j2(oss: Osservazione) -> Optional[str]:
    for a in oss.aperture + oss.chiusure:
        tr = a.get("trade") or {}
        ordine = a.get("ordine")
        if not isinstance(ordine, dict) or str(tr.get("status") or "") != "open":
            continue
        abbinato = _num(ordine.get("size_matched")) or 0.0
        if abbinato <= 0.0:
            return (f"trade {tr.get('id')}: riga 'open' ma l'ordine "
                    f"{ordine.get('customer_order_ref')} risulta abbinato per "
                    f"{abbinato} su Betfair (stato {ordine.get('status')}, "
                    f"annullato {ordine.get('size_cancelled')}): il rifiuto e' "
                    f"stato letto come posizione")
    rifiutati = {str(r.get("ref") or "") for r in oss.rifiutati}
    for a in oss.aperture:
        tr = a["trade"]
        # F1 (25/09): il ref del tennis e' "safe_tennis-t<id>" da oggi, ma le
        # registrazioni piazzate prima del fix portano ancora "safe-t<id>"
        # (identico al calcio): si controllano entrambi, cosi' il replay di
        # una registrazione vecchia non perde questo controllo.
        for ref in (f"safe_tennis-t{tr.get('id')}", f"safe-t{tr.get('id')}"):
            if ref in rifiutati and str(tr.get("status") or "") == "open":
                return (f"trade {tr.get('id')}: l'ordine {ref} e' stato RIFIUTATO dai "
                        f"controlli e la riga risulta 'open'")
    for p in oss.attivita_di("place_rifiutato"):
        tid = p.get("trade_id")
        riga = next((t for t in oss.trades if str(t.get("id")) == str(tid)), None)
        if riga is not None and str(riga.get("status") or "") == "open":
            return (f"trade {tid}: 'place_rifiutato' ({p.get('error_code')}) e riga "
                    f"'open': il rifiuto di Betfair e' stato letto come fill")
    return None


@_controllo("J3", "catalogo §7.3: il prezzo medio si legge da "
                  "`average_price_matched`, non dal prezzo chiesto",
            quando=lambda o: bool([a for a in o.aperture
                                   if (a.get("ordine") or {}).get("size_matched")]))
def _j3(oss: Osservazione) -> Optional[str]:
    for a in oss.aperture + oss.chiusure:
        ordine = a.get("ordine") or {}
        tr = a.get("trade") or {}
        abbinato = _num(ordine.get("size_matched")) or 0.0
        if abbinato <= 0:
            continue
        medio_ordine = _num(ordine.get("average_price_matched"))
        medio_riga = _num(tr.get("price"))
        if medio_ordine is None:
            return (f"trade {tr.get('id')}: ordine abbinato ma senza "
                    f"`average_price_matched` — il prezzo medio verrebbe dal chiesto")
        if medio_riga is not None and abs(medio_riga - medio_ordine) > 0.011:
            return (f"trade {tr.get('id')}: riga a {medio_riga}, ordine abbinato a "
                    f"{medio_ordine}: la riga non racconta l'ordine")
    return None


@_controllo("J4", "catalogo §7.4/7.6: il ref con cui si RILEGGE e' lo stesso del "
                  "piazzamento (`safe_tennis-t<id>` da F1 25/09, `safe-t<id>` legacy "
                  "sulle registrazioni pre-fix), e porta mercato e selezione",
            quando=lambda o: bool(o.ordini))
def _j4(oss: Osservazione) -> Optional[str]:
    for o in oss.ordini:
        ref = str(o.get("customer_order_ref") or "")
        if not ref:
            return f"ordine {o.get('bet_id')} senza customer_order_ref: non e' ritrovabile"
        # F1 (25/09): il tennis scrive "safe_tennis-t<id>" da oggi (il motore
        # del runner rifiuta un comando il cui ref non porta il prefisso
        # dell'attore "safe_tennis-"); "safe-t<id>" resta valido SOLO come
        # forma legacy delle registrazioni piazzate prima del fix.
        if not (ref.startswith("safe_tennis-t") or ref.startswith("safe-t")):
            return (f"ordine {o.get('bet_id')}: ref '{ref}' non e' quello che il bot "
                    f"scrive al piazzamento (`safe_tennis-t<trade_id>`)")
        if not o.get("market_id") or not o.get("selection_id"):
            return (f"ordine {ref}: senza mercato o selezione il confronto per ref "
                    f"collide fra partite (difetto 6 del catalogo)")
    return None


@_controllo("J5", "catalogo §7.7: il `bet_id` si salva SEMPRE, anche quando "
                  "l'ordine non e' abbinato",
            quando=lambda o: bool([a for a in o.aperture
                                   if (a.get("ordine") or {}).get("bet_id")]))
def _j5(oss: Osservazione) -> Optional[str]:
    for a in oss.aperture + oss.chiusure:
        ordine = a.get("ordine") or {}
        tr = a.get("trade") or {}
        if not ordine.get("bet_id"):
            continue
        if str(tr.get("status") or "") in ("pending", "open") and not tr.get("bet_id"):
            return (f"trade {tr.get('id')}: ordine {ordine.get('bet_id')} a mercato ma "
                    f"la riga non porta il bet_id — al giro dopo non si ritrova")
    return None


# ===========================================================================
# L. DUE LAY SULLA STESSA SELEZIONE — regola di PIATTAFORMA dell'utente (16/09)
#
#     «non devono mai esserci 2 lay a mercato sullo stesso mercato/selezione,
#      se si abbinano siamo scoperti»
#
# Nel tennis Safe entra BACK e chiude LAY: due lay vive sulla stessa selezione
# vogliono dire che, se si abbinano entrambe, la posizione si rovescia e la
# seconda lay resta SCOPERTA — con la responsabilita' intera e nessun back a
# coprirla. Non e' un dettaglio contabile: e' la forma esatta con cui il 15/09
# sono usciti 32 green-up veri.
#
# La regola e' SEVERA per ordine dell'utente: basta UN SOLO giro con due lay
# vive o in volo. «In volo» comprende la riga 'pending' (ordine mandato, esito
# non ancora noto) e la riga in riconciliazione, perche' su Betfair quell'ordine
# puo' essere vivissimo — §4.11: «una gamba a esito ignoto conta SEMPRE nel
# rischio, peggior caso: abbinata per intero».
# ===========================================================================
def _lay_in_volo(oss: Osservazione) -> Dict[tuple, List[Dict[str, Any]]]:
    """{(mercato, selezione): righe LAY IN VOLO}. Dalle RIGHE del DB.

    ⚠️ «IN VOLO» = 'pending': ordine mandato e non ancora risolto (coda flumine,
    esito REST ignoto, riconciliazione). Una riga 'open' e' una lay GIA'
    ABBINATA: non e' piu' a mercato e non puo' abbinarsi una seconda volta,
    quindi non e' il rischio che la regola dell'utente descrive («se si
    abbinano siamo scoperti»). Contarla faceva scattare il controllo su ogni
    chiusura di RESIDUO (§4.2), che e' comportamento voluto: falso positivo del
    controllo. Il rischio vero — due lay che possono ancora abbinarsi — lo
    misura questa funzione sulle 'pending' e `_lay_vive_a_mercato` sugli ordini
    EXECUTABLE di Betfair."""
    out: Dict[tuple, List[Dict[str, Any]]] = {}
    for t in oss.trades:
        if str(t.get("side") or "").lower() != "lay":
            continue
        if str(t.get("status") or "") != "pending":
            continue
        chiave = (str(t.get("market_id")), str(t.get("selection_id")))
        out.setdefault(chiave, []).append(t)
    return out


def _lay_vive_a_mercato(oss: Osservazione) -> Dict[tuple, List[Dict[str, Any]]]:
    """{(mercato, selezione): ordini LAY ancora EXECUTABLE su Betfair}."""
    out: Dict[tuple, List[Dict[str, Any]]] = {}
    for o in oss.ordini_vivi:
        if str(o.get("side") or "").lower() != "lay":
            continue
        if str(o.get("status") or "") != "EXECUTABLE":
            continue
        chiave = (str(o.get("market_id")), str(o.get("selection_id")))
        out.setdefault(chiave, []).append(o)
    return out


def _lay_sostituite(oss: Osservazione) -> List[tuple]:
    """Le selezioni su cui in QUESTO giro una lay e' stata annullata e un'altra
    lay e' stata piazzata: la sostituzione cancel+place."""
    annullate = {(str(o.get("market_id")), str(o.get("selection_id")))
                 for o in oss.cancellati
                 if str(o.get("side") or "").lower() == "lay"}
    nuove = {(str(o.get("market_id")), str(o.get("selection_id")))
             for o in oss.ordini if str(o.get("side") or "").lower() == "lay"}
    return sorted(annullate & nuove)


@_controllo("L1", "REGOLA DI PIATTAFORMA (utente, 16/09): MAI due lay vive o in "
                  "volo sullo stesso mercato/selezione — se si abbinano "
                  "entrambe la posizione resta SCOPERTA",
            quando=lambda o: bool(_lay_in_volo(o)) or bool(_lay_vive_a_mercato(o))
            or bool(o.cancellati))
def _l1(oss: Osservazione) -> Optional[str]:
    doppie = {k: v for k, v in _lay_in_volo(oss).items() if len(v) > 1}
    if doppie:
        dettaglio = "; ".join(
            f"mercato {k[0]} selezione {k[1]}: righe "
            + ", ".join(f"{t.get('id')}({t.get('status')},"
                        f"{t.get('size')}@{t.get('price')})" for t in v)
            for k, v in doppie.items())
        return (f"DUE O PIU' LAY vive/in volo sulla stessa selezione: {dettaglio}. "
                f"Se si abbinano entrambe la seconda e' scoperta.")
    a_mercato = {k: v for k, v in _lay_vive_a_mercato(oss).items() if len(v) > 1}
    if a_mercato:
        dettaglio = "; ".join(
            f"mercato {k[0]} selezione {k[1]}: ordini "
            + ", ".join(f"{o.get('customer_order_ref')}"
                        f"({o.get('size_remaining')}@{o.get('price_requested')})"
                        for o in v)
            for k, v in a_mercato.items())
        return (f"DUE O PIU' LAY ancora EXECUTABLE su Betfair sulla stessa "
                f"selezione: {dettaglio}")
    return None


@_controllo("L2", "REGOLA DI PIATTAFORMA (utente, 16/09): una lay non si "
                  "SOSTITUISCE con cancel+place nello stesso giro — fra "
                  "l'annullo e il nuovo ordine l'esito del primo non e' certo",
            quando=lambda o: bool(o.cancellati))
def _l2(oss: Osservazione) -> Optional[str]:
    sostituite = _lay_sostituite(oss)
    if sostituite:
        return (f"lay annullata e ri-piazzata nello STESSO giro su "
                f"{sostituite}: finche' l'annullo non e' confermato da Betfair "
                f"le due lay possono convivere a mercato. REPERTO da portare "
                f"all'utente: non si corregge qui (e' strategia/esecuzione).")
    return None


@_controllo("S4", "16/09 (consegna S1): dopo una chiusura DELL'UTENTE (cash-out "
                  "globale o chiusura fatta fuori dall'app) il bot non apre, non "
                  "copre e non esce piu' su quella partita",
            quando=lambda o: bool(_righe_chiuse_dall_utente(o))
            or bool(o.chiuso_dall_utente))
def _s4(oss: Osservazione) -> Optional[str]:
    """Il gemello tennis di T14 (calcio). Il marcatore lo scrive il SERVIZIO
    (`bot_service.segna_chiuso_dall_utente` -> `meta.chiuso_dall_utente`), sia
    quando l'utente preme cash-out sia quando la chiusura la fa FUORI dall'app
    e il bot se ne accorge dalla posizione di CONTO: da li' in poi, su quella
    partita, non deve fare altro. Una chiusura PARZIALE non mette il marcatore
    (il bot deve continuare a proteggere il resto): quel caso qui non entra."""
    chiuse = {int(t.get("id") or 0) for t in _righe_chiuse_dall_utente(oss)}
    eventi = {str(t.get("event_id") or "") for t in _righe_chiuse_dall_utente(oss)}
    # ...e cio' che il REPLAY sa di suo, che non dipende dal bot
    eventi |= {str(e) for e in (oss.chiuso_dall_utente or {})}
    if oss.chiuso_dall_utente and not chiuse:
        # il bot non ha (ancora) scritto il marcatore: le posizioni vive
        # sull'evento chiuso dall'utente sono quelle da non toccare piu'
        chiuse = {int(t.get("id") or 0) for t in _posizioni_tennis(oss)
                  if str(t.get("event_id") or "") in eventi}
    for a in _aperture_tennis(oss):
        tr = a.get("trade") or {}
        if str(tr.get("event_id") or "") in eventi:
            return (f"partita chiusa dall'utente, e il bot ha APERTO la riga "
                    f"{tr.get('id')}: doveva capirlo e non fare altro")
    for c in _chiusure_tennis(oss):
        tr = c.get("trade") or {}
        padre = tr.get("closes_trade_id")
        if padre is not None and int(padre) in chiuse:
            return (f"partita chiusa dall'utente, e il bot ha aggiunto la gamba "
                    f"di chiusura {tr.get('id')} sulla posizione {padre}")
    # ORDINI VERI partiti dopo la chiusura dell'utente: e' la prova che non
    # dipende da cio' che il bot scrive di se'.
    # ⚠️ FALSO POSITIVO ESCLUSO (16/09): dentro il giro in cui l'utente chiude,
    # il bot puo' aver gia' mandato il suo ordine PRIMA (il replay chiude alla
    # fine del giro, come nella realta' un ordine dell'utente arriva mentre il
    # bot sta lavorando). Si giudicano i giri SUCCESSIVI, non quello.
    ultimo = max((float(v) for v in (oss.chiuso_dall_utente or {}).values()),
                 default=None)
    if ultimo is not None and float(oss.now_ts or 0.0) > ultimo:
        for o in oss.ordini or []:
            rif = str(o.get("customer_order_ref") or "")
            if rif.startswith("utente"):
                continue                  # l'ordine del trader non e' del bot
            return (f"partita chiusa dall'utente, e il bot ha mandato a Betfair "
                    f"l'ordine {rif or o.get('bet_id')}: doveva capirlo e non "
                    f"fare altro")
    return None


def _righe_chiuse_dall_utente(oss: Osservazione) -> List[Dict[str, Any]]:
    """Le righe con il marcatore `meta.chiuso_dall_utente` scritto dal servizio."""
    fuori: List[Dict[str, Any]] = []
    for t in oss.trades:
        if not _e_tennis(t):
            continue
        if isinstance((t.get("meta") or {}).get(BS.CHIUSO_DALL_UTENTE_KEY), dict):
            fuori.append(t)
    return fuori


# ===========================================================================
# C. CONSAPEVOLEZZA DELL'ORDINE (C.12a)
# ===========================================================================
@_controllo("C1", "C.12a: ogni riga eseguita porta CHIESTO, ABBINATO, RESIDUO e "
                  "PREZZO MEDIO, sia nel meta SIA nelle COLONNE della migrazione "
                  "`trades_consapevolezza_ordine_2026-09-16.sql` (sono le colonne che "
                  "la UI e i controlli K1/K5 leggono davvero, non il meta)",
            quando=lambda o: bool(o.aperture or o.chiusure))
def _c1(oss: Osservazione) -> Optional[str]:
    for a in oss.aperture + oss.chiusure:
        tr = a.get("trade") or {}
        if str(tr.get("status") or "") != "open":
            continue
        esec = (tr.get("meta") or {}).get("esecuzione")
        if not isinstance(esec, dict):
            return (f"trade {tr.get('id')}: riga 'open' senza `meta.esecuzione` — "
                    f"chiesto, abbinato e residuo non sono scritti da nessuna parte")
        mancanti = [k for k in ("size_richiesta", "size_abbinata", "size_residua",
                                "price_medio") if esec.get(k) is None]
        if mancanti:
            return f"trade {tr.get('id')}: `meta.esecuzione` senza {mancanti}"
        # ⚠️ REPERTO 17/09 (trade live #297, tennis, back 1,03 x 3 EUR): il meta
        # aveva GIA' tutti questi numeri quando le COLONNE nuove
        # (`size_requested`, `size_matched`, `avg_price_matched`) erano NULL
        # sulla riga, perche' la conferma dell'apertura usava `db.update_trade`
        # diretto invece di `execution.aggiorna_trade`. Il controllo restava
        # verde perche' guardava SOLO il meta — cio' che il bot si racconta —
        # e non le colonne che UI, K1 e K5 leggono davvero. Un trade con un
        # bet_id vero (ordine REALE piazzato, non una riserva in coda) deve
        # avere anche le colonne valorizzate. `betfair_updated_at` resta fuori
        # da questa lista: il percorso REST la valorizza da `placedDate`
        # dell'exchange, ma non e' dichiarata garantita in ogni risposta.
        if tr.get("bet_id"):
            mancanti_colonna = [c for c in ("size_requested", "size_matched",
                                            "avg_price_matched")
                                if tr.get(c) is None]
            if mancanti_colonna:
                return (f"trade {tr.get('id')} (bet_id {tr.get('bet_id')}): "
                        f"`meta.esecuzione` e' completo ma la COLONNA {mancanti_colonna} "
                        f"e' NULL sulla riga — UI e controlli K1/K5 leggono la colonna, "
                        f"non il meta (reperto 17/09, trade live #297)")
    return None


# ===========================================================================
# S. IL SERVIZIO
# ===========================================================================
@_controllo("S1", "CERT. 14/09: i soldi veri si raggiungono SOLO scrivendo "
                  "`strategy_modes.tennis='live'`, mai ereditandoli",
            quando=lambda o: True)
def _s1(oss: Osservazione) -> Optional[str]:
    scelto = str((oss.params.get("strategy_modes") or {}).get("tennis") or "").lower()
    atteso = "live" if (oss.modo_servizio == "live" and scelto == "live") else "paper"
    if oss.modo_strategia != atteso:
        return (f"modalita' della strategia 'tennis' = {oss.modo_strategia}, attesa "
                f"{atteso} (servizio {oss.modo_servizio}, strategy_modes.tennis="
                f"{scelto or 'assente'})")
    for a in _aperture_tennis(oss):
        tr = a["trade"]
        if str(tr.get("mode") or "") != oss.modo_strategia:
            return (f"trade {tr.get('id')} aperto in modalita' '{tr.get('mode')}' "
                    f"mentre la strategia e' in '{oss.modo_strategia}'")
    return None


@_controllo("S2", "PROCESSO §6.3 / COSTITUZIONE: fermare toglie le APERTURE, non "
                  "le uscite",
            quando=lambda o: o.stato_bot != "running")
def _s2(oss: Osservazione) -> Optional[str]:
    if _aperture_tennis(oss):
        return (f"bot in stato '{oss.stato_bot}' e {len(_aperture_tennis(oss))} "
                f"apertura/e nuove: a bot fermo non si apre niente")
    return None


@_controllo("S3", "12/09: nessun ingresso su una riga del feed NON FRESCA",
            quando=lambda o: not o.feed_fresco)
def _s3(oss: Osservazione) -> Optional[str]:
    if _aperture_tennis(oss):
        return (f"feed non fresco (riga {(oss.row or {}).get('updated_at')}) e "
                f"{len(_aperture_tennis(oss))} apertura/e nuove")
    return None


@_controllo("A1", "il giro del servizio (`run_once`) non deve mai sollevare",
            quando=lambda o: True)
def _a1(oss: Osservazione) -> Optional[str]:
    return oss.errore_servizio or None


# ===========================================================================
# verifica
# ===========================================================================
def verifica(oss: Osservazione,
             sollecitati: Optional[Dict[str, int]] = None) -> List[Violazione]:
    """Tutti i controlli su UN giro. Un controllo che esplode diventa esso
    stesso un referto (`XX-ERRORE`): un controllo rotto e' un'informazione, non
    un motivo per non sapere niente del resto."""
    out: List[Violazione] = []
    for codice, regola, fn, quando in _REGISTRO:
        try:
            if quando is not None and not quando(oss):
                continue
            if sollecitati is not None:
                sollecitati[codice] = sollecitati.get(codice, 0) + 1
            det = fn(oss)
        except Exception as ex:  # noqa: BLE001
            out.append(Violazione(f"{codice}-ERRORE", regola,
                                  f"il controllo e' esploso: {type(ex).__name__}: {ex}",
                                  oss.quando))
            continue
        if det:
            out.append(Violazione(codice, regola, det, oss.quando))
    return out


# ===========================================================================
# K. LA CONSAPEVOLEZZA DELL'ORDINE, CONTRO IL MERCATO (16/09 sera)
#
# ⚠️ I controlli T/J/L qui sopra guardano la DECISIONE del giro. I cinque
# difetti del 15/09 non stanno li': stanno nel rapporto fra cio' che le righe di
# `safe_strategy_trades` dicono e cio' che il banco dice degli ordini. La
# famiglia K guarda QUEL rapporto e vive nel modulo condiviso
# `certificazione_k.py`, lo stesso che usa il calcio: il servizio e'
# `bot_service` per tutti e due e il piazzamento e' `execution.place` per tutti
# e due, quindi una seconda copia sarebbe solo una copia che diverge.
# ===========================================================================
def verifica_consapevolezza(righe: List[Dict[str, Any]],
                            ordini: Optional[Dict[str, Any]] = None,
                            rifiutati: Optional[Any] = None,
                            sollecitati: Optional[Dict[str, int]] = None,
                            quando: str = "") -> List[Violazione]:
    """I controlli K su UN giro, nella forma di `Violazione` del tennis."""
    esiti = K.verifica_consapevolezza(righe, ordini, rifiutati, sollecitati)
    return [Violazione(c, r, d, quando) for c, r, d in esiti]


def elenco_controlli() -> List[Tuple[str, str]]:
    """(codice, regola) di tutto cio' che questa certificazione sa verificare.

    Comprende la famiglia K: un controllo che non si conta non esiste."""
    return [(c, r) for c, r, _fn, _q in _REGISTRO] + list(K.REGISTRO)


def mai_sollecitati(sollecitati: Dict[str, int]) -> List[Tuple[str, str]]:
    """I controlli che non hanno MAI avuto un caso da giudicare: non dicono «il
    bot e' sano», dicono «non lo so»."""
    return [(c, r) for c, r in elenco_controlli() if not sollecitati.get(c)]


# cause dichiarate per i controlli che su questo banco NON possono avere un
# caso: si scrivono nel referto invece di essere taciute (PROCESSO §6.8).
CAUSE_NON_ESERCITABILI: Dict[str, str] = {
    "T10": ("Betfair non pubblica il turno per il tennis (399 mercati in 3 giorni, "
            "zero con final/semi/quarter/round/R16/QF/SF): il dato non esiste nel "
            "feed, quindi l'esclusione delle finali non e' esercitabile "
            "(STATO_PRODUZIONE L5/P6, decisione dell'utente sull'euristica)"),
    "L2": ("la sostituzione cancel+place di una lay si solleva solo quando il bot "
           "ANNULLA un ordine gia' vivo al giro prima: nel tennis la chiusura e' "
           "un FILL_OR_KILL che nasce e muore nello stesso giro, quindi su questa "
           "registrazione l'annullo di un ordine appoggiato non capita mai. Si "
           "provoca con un percorso di uscita APPOGGIATO, che il tennis non ha"),
}


# ===========================================================================
# P. IL COMPORTAMENTO NEL TEMPO — i loop non si vedono in un istante
# ===========================================================================
@dataclass
class Andamento:
    """Memoria fra un giro e l'altro, per una partita."""

    ultima_azione: Optional[tuple] = None
    ripetizioni: int = 0
    max_per_ruolo: Dict[str, int] = field(default_factory=dict)
    correnti: Dict[str, int] = field(default_factory=dict)
    azione_per_ruolo: Dict[str, tuple] = field(default_factory=dict)
    ordini_totali: int = 0
    proposte_totali: int = 0


RIPETIZIONI_SOSPETTE = 3


def osserva(and_: Andamento, oss: Osservazione) -> None:
    """Aggiorna l'andamento con gli ordini VERI nati in questo giro."""
    for o in oss.ordini:
        and_.ordini_totali += 1
        ruolo = "chiusura" if o.get("_chiusura") else "apertura"
        firma = (ruolo, str(o.get("market_id")), int(o.get("selection_id") or 0),
                 str(o.get("side")), round(_num(o.get("price_requested")) or 0.0, 2),
                 round(_num(o.get("size_requested")) or 0.0, 2))
        if and_.azione_per_ruolo.get(ruolo) == firma:
            and_.correnti[ruolo] = and_.correnti.get(ruolo, 0) + 1
        else:
            and_.correnti[ruolo] = 1
            and_.azione_per_ruolo[ruolo] = firma
        if and_.correnti[ruolo] > and_.max_per_ruolo.get(ruolo, 0):
            and_.max_per_ruolo[ruolo] = and_.correnti[ruolo]
    and_.proposte_totali += len(oss.proposte)


def difetti_di_progettazione(and_: Andamento) -> List[Violazione]:
    """Il verdetto sul COMPORTAMENTO, a fine partita."""
    out: List[Violazione] = []
    for ruolo, quante in sorted(and_.max_per_ruolo.items(), key=lambda x: -x[1]):
        if quante < RIPETIZIONI_SOSPETTE:
            continue
        firma = and_.azione_per_ruolo.get(ruolo)
        out.append(Violazione(
            "P1", "il bot non deve mandare a mercato la stessa identica richiesta "
                  "all'infinito",
            f"{ruolo}: {firma} ripetuta {quante} volte di fila. E' la forma esatta "
            f"del loop del 15/09 (32 ordini veri)."))
    return out


@dataclass
class Referto:
    """L'esito su UNA partita, nello stesso formato del referto di Mike, cosi'
    che il punto d'ingresso unico (`Betfair/stream/backtest/certifica.py`) possa
    leggerlo senza una seconda implementazione."""

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
        # le voci DICHIARATE non sono violazioni: sono misure che la spec
        # prevede e che vanno lette, non corrette.
        return not [v for v in self.violazioni if not v.codice.endswith("-DICHIARATA")
                    and not v.codice.endswith("-APPROVAZIONE")]

    def per_codice(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for v in self.violazioni:
            out[v.codice] = out.get(v.codice, 0) + 1
        return out
