"""CERTIFICAZIONE DI SAFE CALCIO — base, esatto, punta contro `SPEC_STRATEGIA_S.md`.

Non si misura se GUADAGNA. Si misura se **si comporta come dice la specifica**,
valutazione per valutazione, ordine per ordine, uscita per uscita, sui dati veri
delle partite registrate.

DA DOVE VIENE OGNI CONTROLLO. Le righe di questo file sono la trascrizione,
una per una, della tabella di `Betfair/safe_strategy/RISCONTRO_CALCIO_2026-09-14.md`
(voce della specifica -> file:riga -> valore -> verdetto). Ogni controllo:

  * CITA la voce della SPEC che difende (campo `voce`);
  * dichiara `quando=` ha davvero un caso da giudicare, perche' «zero
    violazioni» su un controllo mai sollecitato non vuol dire «sano», vuol dire
    «non lo so» — e il referto lo deve stampare;
  * e' CONSERVATIVO: segnala solo quando la violazione e' certa. Un controllo
    che non sa decidere tace.

LE QUATTRO FAMIGLIE DI OSSERVAZIONE (ognuna e' un momento vero del bot):

  `Valutazione` — il motore ha appena valutato UNA variante su UNA partita
                  (`engine.evaluate_football_all`): ctx vero, VariantEvaluation
                  vera, parametri veri. Qui vivono i controlli d'INGRESSO.
  `Ordine`      — il servizio ha appena mandato un ordine al mercato
                  (`execution.place` -> `MercatoFlumine.place_order_live`).
                  Qui vivono i controlli sul CICLO DI VITA dell'ordine (J*).
  `Uscita`      — il servizio ha appena chiesto a `exits.decide` che cosa fare
                  di una posizione aperta. Qui vivono le uscite della SPEC.
  `Ciclo`       — fine di un `run_once`: lo stato del database in memoria e del
                  mercato. Qui vivono i controlli TRASVERSALI (cap, modalita',
                  freni, consapevolezza dell'ordine C.12a).

FAMIGLIE DI CODICE:

  B*  CALCIO BASE          (SPEC §1)
  E*  CALCIO RIS. ESATTO   (SPEC §2)
  P*  CALCIO PUNTA         (SPEC §4)
  T*  trasversali          (SPEC "differenze chiave" + eccezioni decise)
  J*  i difetti del 15/09  (PROCESSO_STANDARD_BOT §7, punti 1-7)

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import certificazione_k as K
from . import engine as E
from . import exits as XE

# le tre strategie calcio della SPEC: sono queste, e sono TUTTE.
STRATEGIE_CALCIO: Tuple[str, ...] = ("base", "esatto", "punta")

# ---------------------------------------------------------------------------
# I NUMERI DELLA SPEC, scritti qui e non letti dai parametri
# ---------------------------------------------------------------------------
# ⚠️ E' la differenza fra un controllo e uno specchio. Se la banda la si legge
# da `params`, spostarla nel codice (o dal DB) NON produce nessuna violazione:
# il controllo direbbe sempre «conforme», perche' sta confrontando il parametro
# con se stesso. Qui i valori vengono da `SPEC_STRATEGIA_S.md`, trascritti una
# volta, e il controllo confronta IL PARAMETRO IN USO con la SPEC.
# Le eccezioni gia' decise dall'utente (minuti come soglia, stake fisso,
# quota di banca 20-34 del 25/09) sono dichiarate nei singoli controlli.
SPEC_BASE = {
    "minuteMin": 55.0,                       # «dal 55'»
    "scores": ("1-0", "2-1", "2-0"),
    "favPre": (1.40, 1.80),
    "dogPre": (4.0, 8.0),
    # Q1, decisione dell'utente 25/09: la quota di entrata e' la QUOTA DI BANCA
    # della squadra che perde, 20-34 (corso, «4. STRATEGIA/2. Entrata a
    # mercato» @93.0). Sostituisce la «Lettura A» del 14/09 (back live della
    # favorita 1,20-1,34), che non e' piu' un filtro.
    "dogLay": (20.0, 34.0),
    "uscita": (80, 83),                      # «80-83'»
    "assestamento": (20.0, 60.0),            # «attendi 20-60 s»
}
SPEC_ESATTO = {
    "minuteMin": 48.0,                       # «dal 48'»
    "scores": ("0-0", "1-0", "1-1", "2-1"),
    "maxGoalsLaySide": 1.0,                  # «al massimo 1 gol»
    "entry": (30.0, 70.0),
    "uscita": (70, 75),                      # «entro il 70-75'»
}
SPEC_PUNTA = {
    "minuteMin": 66.0,                       # «dal 66'»
    "scores": ("2-0", "3-1", "3-0"),
    "entry": (1.03, 1.10),
    "attesaGol": (3.0, 4.0),                 # «aspetta 3-4' dopo il gol»
    "uscita": (83, 83),                      # «entro l'83'»
}


def _banda_uguale(valore: Any, atteso: Tuple[float, float]) -> bool:
    """Il parametro in uso e' la banda della SPEC (tolleranza di arrotondamento)."""
    lo, hi = valore
    if lo is None or hi is None:
        return False
    return abs(float(lo) - atteso[0]) < 1e-9 and abs(float(hi) - atteso[1]) < 1e-9


# ---------------------------------------------------------------------------
# il referto
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Violazione:
    """Una voce della specifica non rispettata, col contesto per capirla."""

    codice: str                  # es. "B4"
    regola: str                  # la regola, in una riga
    dettaglio: str               # che cosa e' successo davvero
    strategia: str = ""          # base | esatto | punta | (vuoto = trasversale)
    minuto: Optional[int] = None
    punteggio: Optional[str] = None

    def __str__(self) -> str:
        dove = f"[{self.strategia or 'safe'}"
        if self.minuto is not None:
            dove += f" {self.minuto}'"
        if self.punteggio:
            dove += f" {self.punteggio}"
        return f"{self.codice} {dove}] {self.regola} -> {self.dettaglio}"


# ---------------------------------------------------------------------------
# le osservazioni: i momenti VERI del bot a cui i controlli si agganciano
# ---------------------------------------------------------------------------
@dataclass
class Valutazione:
    """Una variante appena valutata dal motore VERO su una partita vera."""

    strategia: str                       # base | esatto | punta
    ctx: Any                             # engine.FootballMatchCtx
    ev: Any                              # engine.VariantEvaluation
    par: Dict[str, Any]                  # params[strategia] (la sezione vera)
    params: Dict[str, Any]               # tutti i parametri risolti
    pre_ko_congelato: Optional[Dict[str, float]] = None   # il primo riferimento visto

    @property
    def check(self) -> Dict[str, Any]:
        return {c.id: c for c in (self.ev.checks or ())}

    @property
    def segnale(self) -> bool:
        return str(self.ev.state) == "signal"

    @property
    def punteggio(self) -> str:
        sh, sa = self.ctx.score_home, self.ctx.score_away
        return f"{'?' if sh is None else sh}-{'?' if sa is None else sa}"


@dataclass
class Ordine:
    """Un ordine appena mandato al mercato dal servizio vero."""

    strategia: str
    riga: Dict[str, Any]                 # la riga safe_strategy_trades
    esito: Any                           # execution.PlaceOutcome
    mode: str                            # la modalita' del SERVIZIO
    params: Dict[str, Any] = field(default_factory=dict)   # i parametri risolti
    stato_betfair: Optional[Dict[str, Any]] = None   # la riga di list_current_orders
    apertura: bool = True                # False = chiusura/cash-out
    origine: str = ""                    # auto | manual
    size_chiesta: float = 0.0            # la size passata a `execution.place`


@dataclass
class Uscita:
    """Una decisione di uscita appena presa su una posizione aperta."""

    strategia: str
    trade: Dict[str, Any]
    tr: Dict[str, Any]                   # il tracker `meta.exit_track`
    decisione: Any                       # exits.ExitDecision | None
    par: Dict[str, Any]                  # la sezione `exits` risolta
    now_ts: float


@dataclass
class Ciclo:
    """Fine di un `run_once`: lo stato di database e mercato."""

    db: Any
    market: Any
    params: Dict[str, Any]
    mode: str
    now_ts: float
    aperture_nel_giro: int = 0
    # dichiarate dal replay: sono CONDIZIONI dello scenario, non deduzioni
    feed_stantio: bool = False
    segnali_di_variante_spenta: int = 0
    # le righe di attivita' scritte dal servizio in QUESTO giro (kind, payload,
    # event_id): servono a vedere una sostituzione `cancel` + `place` fatta
    # dentro lo stesso ciclo, che da fuori sembrerebbe un ordine solo.
    attivita_del_giro: List[Tuple[str, Dict[str, Any], Any]] = field(
        default_factory=list)
    # {event_id: istante} in cui l'UTENTE ha chiuso a mano TUTTE le operazioni
    # della partita (cash-out globale). Da quel momento il bot «lo capisce e
    # NON FA ALTRO» su quella partita (ordine dell'utente, 16/09 h18:20).
    chiuso_dall_utente: Dict[str, float] = field(default_factory=dict)


Osservazione = Any
Controllo = Callable[[Osservazione], Optional[str]]

# (codice, voce della SPEC, regola, tipo di osservazione, funzione, quando)
_REGISTRO: List[Tuple[str, str, str, type, Controllo, Optional[Controllo]]] = []


def _controllo(codice: str, voce: str, regola: str, tipo: type,
               quando: Optional[Controllo] = None):
    """Registra un controllo, e con `quando` dichiara QUANDO ha davvero un caso.

    ⚠️ Senza `quando`, un referto «zero violazioni» e' ambiguo: non si distingue
    un controllo che ha guardato e approvato da uno che non ha mai avuto
    l'occasione di guardare. Sono due cose diversissime — la prima e' una
    garanzia, la seconda e' un buco — e finche' si contano solo le violazioni
    sembrano identiche.
    """
    def _reg(fn: Controllo) -> Controllo:
        _REGISTRO.append((codice, voce, regola, tipo, fn, quando))
        return fn
    return _reg


# ---------------------------------------------------------------------------
# utilita' comuni ai controlli — tutte costruite sulle funzioni VERE del motore
# ---------------------------------------------------------------------------
def _fav(v: Valutazione) -> Optional[str]:
    return E.favorite_side(v.ctx.pre_match)


def _dog(v: Valutazione) -> Optional[str]:
    f = _fav(v)
    return None if f is None else ("away" if f == "home" else "home")


def _leader(v: Valutazione) -> Optional[str]:
    sh, sa = v.ctx.score_home, v.ctx.score_away
    return E.leader_side(sh, sa) if sh is not None and sa is not None else None


def _nome(v: Valutazione, lato: Optional[str]) -> Optional[str]:
    if lato is None:
        return None
    return v.ctx.home if lato == "home" else v.ctx.away


def _manca(v: Valutazione, cid: str) -> bool:
    """Il check con questo id non esiste nella valutazione: la condizione della
    SPEC e' stata TOLTA dal motore, non solo non superata."""
    return cid not in v.check


def _num(x: Any) -> Optional[float]:
    return E.num_or_none(x)


def _valutazione(tipo: str) -> Callable[[Osservazione], bool]:
    return lambda o: isinstance(o, Valutazione) and o.strategia == tipo


def _segnale(tipo: str) -> Callable[[Osservazione], bool]:
    return lambda o: isinstance(o, Valutazione) and o.strategia == tipo and o.segnale


def _uscita(tipo: str) -> Callable[[Osservazione], bool]:
    return lambda o: isinstance(o, Uscita) and o.strategia == tipo


# ===========================================================================
# B. CALCIO BASE — SPEC §1: banca (lay) la squadra che perde, mercato 1X2
# ===========================================================================
@_controllo("B1", "SPEC §1 tabella: Mercato = 1X2",
            "la BASE opera solo sul mercato Match Odds",
            Valutazione, quando=_valutazione("base"))
def _b1(v: Valutazione) -> Optional[str]:
    if str(v.ev.market_type) != "MATCH_ODDS":
        return f"mercato '{v.ev.market_type}' invece di MATCH_ODDS"
    return None


@_controllo("B2", "SPEC §1: BANCA (lay)",
            "la BASE e' una BANCA: il lato e' sempre LAY",
            Valutazione, quando=_valutazione("base"))
def _b2(v: Valutazione) -> Optional[str]:
    if str(v.ev.side or "").upper() != "LAY":
        return f"lato '{v.ev.side}' invece di LAY"
    return None


@_controllo("B3", "SPEC §1: si banca la squadra che sta PERDENDO",
            "la selezione bancata e' la sfavorita pre-match, e non e' in vantaggio",
            Valutazione, quando=_segnale("base"))
def _b3(v: Valutazione) -> Optional[str]:
    dog, lead = _dog(v), _leader(v)
    atteso = _nome(v, dog)
    if atteso is not None and v.ev.selection is not None and str(v.ev.selection) != str(atteso):
        return f"banca '{v.ev.selection}' ma la sfavorita e' '{atteso}'"
    if dog is not None and lead is not None and lead == dog:
        return f"banca la sfavorita '{atteso}' che pero' e' in VANTAGGIO ({v.punteggio})"
    return None


@_controllo("B4", "SPEC §1: minuto ingresso DAL 55' (soglia, non fascia)",
            "nessun ingresso prima del minuto minimo; sopra la soglia non c'e' tetto",
            Valutazione, quando=_valutazione("base"))
def _b4(v: Valutazione) -> Optional[str]:
    if _manca(v, "minute"):
        return "il check del minuto non esiste piu' nella valutazione"
    soglia = _num(v.par.get("minuteMin"))
    if soglia is None or abs(soglia - SPEC_BASE["minuteMin"]) > 1e-9:
        return (f"soglia del minuto {soglia} invece del {SPEC_BASE['minuteMin']:.0f}' "
                f"della SPEC")
    m = v.ctx.minute
    if v.segnale and soglia is not None and isinstance(m, int) and m < soglia:
        return f"segnale al {m}' con la soglia a {soglia:.0f}'"
    # la soglia e' APERTA: un minuto ALTO non puo' essere il motivo dello scarto
    ck = v.check.get("minute")
    if (ck is not None and ck.ok is False and isinstance(m, int)
            and soglia is not None and m >= soglia):
        return (f"minuto {m}' >= soglia {soglia:.0f}' ma il check e' FALSO: "
                f"la fascia e' stata richiusa (regola trasversale 14/09)")
    return None


@_controllo("B5", "SPEC §1: punteggio 1-0 / 2-1 / 2-0 (orientato sulla favorita)",
            "si entra solo con la favorita avanti e uno dei punteggi ammessi",
            Valutazione, quando=_valutazione("base"))
def _b5(v: Valutazione) -> Optional[str]:
    if _manca(v, "score"):
        return "il check del punteggio non esiste piu' nella valutazione"
    ammessi_ora = tuple(str(x) for x in (v.par.get("scores") or ()))
    if set(ammessi_ora) != set(SPEC_BASE["scores"]):
        return (f"punteggi ammessi {list(ammessi_ora)} invece di "
                f"{list(SPEC_BASE['scores'])} della SPEC")
    if not v.segnale:
        return None
    fav, sh, sa = _fav(v), v.ctx.score_home, v.ctx.score_away
    if fav is None or sh is None or sa is None:
        return None
    g_fav = sh if fav == "home" else sa
    g_dog = sa if fav == "home" else sh
    ammessi = list(v.par.get("scores") or [])
    if not E.score_in_list_oriented(ammessi, g_fav, g_dog):
        return (f"segnale con {g_fav}-{g_dog} (favorita-sfavorita) fuori "
                f"dall'elenco {ammessi}")
    if _leader(v) != fav:
        return f"segnale con la favorita NON in vantaggio ({v.punteggio})"
    return None


@_controllo("B6", "SPEC §1: quota favorita pre-match 1.40-1.80",
            "la favorita pre-KO deve stare nella banda del manuale",
            Valutazione, quando=_valutazione("base"))
def _b6(v: Valutazione) -> Optional[str]:
    if _manca(v, "favPre"):
        return "il check della quota favorita pre-match non esiste piu'"
    if not _banda_uguale((v.par.get("favPreMin"), v.par.get("favPreMax")),
                         SPEC_BASE["favPre"]):
        return (f"banda favorita pre-match [{v.par.get('favPreMin')}, "
                f"{v.par.get('favPreMax')}] invece di {list(SPEC_BASE['favPre'])}")
    if not v.segnale or v.ctx.pre_match is None:
        return None
    fav = _fav(v)
    if fav is None:
        return None
    q = float(v.ctx.pre_match["home"] if fav == "home" else v.ctx.pre_match["away"])
    lo, hi = _num(v.par.get("favPreMin")), _num(v.par.get("favPreMax"))
    if lo is None or hi is None:
        return None
    if not E.in_range(q, lo, hi):
        return f"favorita pre-match {q} fuori da [{lo}, {hi}]"
    return None


@_controllo("B7", "SPEC §1: quota sfavorita pre-match 4-8",
            "la sfavorita pre-KO deve stare nella banda del manuale",
            Valutazione, quando=_valutazione("base"))
def _b7(v: Valutazione) -> Optional[str]:
    if _manca(v, "dogPre"):
        return "il check della quota sfavorita pre-match non esiste piu'"
    if not _banda_uguale((v.par.get("dogPreMin"), v.par.get("dogPreMax")),
                         SPEC_BASE["dogPre"]):
        return (f"banda sfavorita pre-match [{v.par.get('dogPreMin')}, "
                f"{v.par.get('dogPreMax')}] invece di {list(SPEC_BASE['dogPre'])}")
    if not v.segnale or v.ctx.pre_match is None:
        return None
    fav = _fav(v)
    if fav is None:
        return None
    q = float(v.ctx.pre_match["away"] if fav == "home" else v.ctx.pre_match["home"])
    lo, hi = _num(v.par.get("dogPreMin")), _num(v.par.get("dogPreMax"))
    if lo is None or hi is None:
        return None
    if not E.in_range(q, lo, hi):
        return f"sfavorita pre-match {q} fuori da [{lo}, {hi}]"
    return None


@_controllo("B8", "SPEC §1 + decisione dell'utente 25/09 (Q1): quota di entrata "
                  "20-34 = QUOTA DI BANCA della squadra che perde",
            "si entra solo se il lay della sfavorita sta in [20, 34], estremi inclusi",
            Valutazione, quando=_valutazione("base"))
def _b8(v: Valutazione) -> Optional[str]:
    if _manca(v, "dogLay"):
        return "il check della quota di banca della sfavorita non esiste piu'"
    # la banda IN USO confrontata con quella del corso, scritta qui e non letta
    # dai parametri: spostarla nel codice o dal DB deve diventare rosso.
    if not _banda_uguale((v.par.get("dogLayMin"), v.par.get("dogLayMax")),
                         SPEC_BASE["dogLay"]):
        return (f"banda della quota di banca [{v.par.get('dogLayMin')}, "
                f"{v.par.get('dogLayMax')}] invece di {list(SPEC_BASE['dogLay'])}")
    if not v.segnale:
        return None
    lo, hi = SPEC_BASE["dogLay"]
    # il prezzo VERO della riga (il lay della sfavorita) e quello con cui
    # l'ordine partirebbe (`entry_odds`): tutti e due dentro la banda.
    dog = _dog(v)
    coppia = E._side_pair(v.ctx.odds, dog) if dog else None
    q = getattr(coppia, "lay", None) if coppia is not None else None
    if q is not None and not E.in_range(float(q), lo, hi):
        return f"quota di banca della sfavorita {q} fuori da [{lo:g}, {hi:g}]"
    e = _num(v.ev.entry_odds)
    if e is not None and not E.in_range(float(e), lo, hi):
        return f"ingresso a quota di banca {e} fuori da [{lo:g}, {hi:g}]"
    return None


@_controllo("B9", "decisione dell'utente 25/09 (Q1): NESSUN filtro sulla quota "
                  "live della FAVORITA (la «Lettura A» 1,20-1,34 e' tolta)",
            "l'ingresso non dipende dal back live della favorita",
            Valutazione, quando=_valutazione("base"))
def _b9(v: Valutazione) -> Optional[str]:
    # La Lettura A del 14/09 filtrava sul back live della favorita (check
    # `favLive`, parametri `favLiveMin/Max`). Il 25/09 l'utente l'ha sostituita
    # con la banda della quota di banca (B8). Se il filtro ricomparisse — come
    # check o come parametro risolto — la strategia sarebbe stata alterata.
    if "favLive" in v.check:
        ck = v.check["favLive"]
        return ("la valutazione filtra ancora sulla quota live della favorita "
                f"({ck.label} = {ck.value}): tolto dall'utente il 25/09")
    for k in ("favLiveMin", "favLiveMax"):
        if k in (v.par or {}):
            return (f"il parametro '{k}' e' ancora fra quelli risolti della BASE: "
                    f"la Lettura A e' tolta dal 25/09")
    return None


@_controllo("B10", "SPEC §1: la FAVORITA deve avere il controllo del gioco",
            "con requireControl acceso il check di controllo deve esistere ed "
            "essere orientato sulla favorita",
            Valutazione,
            quando=lambda o: (isinstance(o, Valutazione) and o.strategia == "base"
                              and bool(o.par.get("requireControl"))))
def _b10(v: Valutazione) -> Optional[str]:
    # ⊘ NON ESERCITABILE con i default di produzione: `requireControl` nasce
    # SPENTO (engine.py:188) perche' il dato (statistiche IPS corner/cartellini)
    # non ha ancora copertura misurata. Il controllo esiste e sa parlare: senza
    # il parametro acceso non ha mai un caso, ed e' un «non lo so», non un «sano».
    if _manca(v, "control"):
        return "requireControl acceso ma il check 'control' non esiste"
    return None


@_controllo("B11", "PROCESSO §6.2 / CERT 13/09: `pre_ko` CONGELATO al primo "
                   "tick in-play, mai ricavato dalle quote live",
            "il riferimento 1X2 pre-KO non cambia piu' una volta iniziata la partita",
            Valutazione,
            quando=lambda o: (isinstance(o, Valutazione) and o.strategia == "base"
                              and o.ctx.inplay and o.ctx.pre_match is not None
                              and o.pre_ko_congelato is not None))
def _b11(v: Valutazione) -> Optional[str]:
    primo = v.pre_ko_congelato or {}
    ora = v.ctx.pre_match or {}
    for k in ("home", "draw", "away"):
        a, b = _num(primo.get(k)), _num(ora.get(k))
        if a is None or b is None:
            continue
        if abs(a - b) > 1e-9:
            return (f"il riferimento pre-KO e' CAMBIATO in gioco: {k} {a} -> {b} "
                    f"(difetto 19 del catalogo: stato perso o ricalcolato dal live)")
    return None


@_controllo("B12", "SPEC §1 uscita in perdita: la sfavorita PAREGGIA -> "
                   "accetta subito, non aspettare un secondo gol",
            "il pareggio (o il sorpasso) della sfavorita produce un'uscita 'loss' "
            "e nessun'altra decisione la precede",
            Uscita, quando=_uscita("base"))
def _b12(u: Uscita) -> Optional[str]:
    tr = u.tr
    try:
        fav, dog = int(tr["last_" + str(tr["side"])]), int(
            tr["last_" + ("away" if str(tr["side"]) == "home" else "home")])
    except (KeyError, TypeError, ValueError):
        return None
    if fav > dog:
        return None
    d = u.decisione
    if d is None:
        return f"sfavorita a {dog} contro {fav}: nessuna uscita decisa"
    if str(getattr(d, "kind", "")) != "loss":
        return (f"sfavorita a {dog} contro {fav} ma l'uscita e' "
                f"'{getattr(d, 'kind', None)}' ({getattr(d, 'reason', None)}) "
                f"invece di 'loss'")
    return None


@_controllo("B13", "SPEC §1 uscita in profitto: la favorita segna il 2° gol -> cashout",
            "un gol in piu' della favorita produce un'uscita in profitto",
            Uscita, quando=_uscita("base"))
def _b13(u: Uscita) -> Optional[str]:
    tr = u.tr
    lato = str(tr.get("side") or "")
    try:
        fav, fav_e = int(tr["last_" + lato]), int(tr["entry_" + lato])
        altro = "away" if lato == "home" else "home"
        dog, dog_e = int(tr["last_" + altro]), int(tr["entry_" + altro])
    except (KeyError, TypeError, ValueError):
        return None
    if fav <= fav_e or fav <= dog:
        return None            # non e' questo il caso (o vince prima la perdita)
    d = u.decisione
    if d is None or str(getattr(d, "kind", "")) not in ("profit", "loss"):
        return (f"favorita passata da {fav_e} a {fav} gol (sfavorita {dog_e}->{dog}) "
                f"ma la decisione e' {getattr(d, 'kind', None)}")
    return None


@_controllo("B14", "SPEC §1 uscita a tempo: nessun 2° gol ma si arriva all'80-83' "
                   "-> esci comunque",
            "oltre il minuto di uscita la posizione produce una decisione 'time'",
            Uscita, quando=_uscita("base"))
def _b14(u: Uscita) -> Optional[str]:
    m = u.tr.get("minute")
    soglia = int(u.par.get("base_exit_minute") or 80)
    lo, hi = SPEC_BASE["uscita"]
    if not (lo <= soglia <= hi):
        return (f"minuto di uscita {soglia} fuori dalla finestra "
                f"{lo}-{hi} della SPEC")
    if not isinstance(m, int) or m < soglia:
        return None
    if u.decisione is None:
        return f"minuto {m}' >= {soglia} ma nessuna decisione di uscita"
    return None


@_controllo("B15", "SPEC §1: rosso alla FAVORITA -> esci; rosso alla SFAVORITA "
                   "-> neutro",
            "il rosso muove l'uscita solo quando colpisce la squadra protetta",
            Uscita,
            quando=lambda o: (isinstance(o, Uscita) and o.strategia == "base"
                              and (XE._red_to(o.tr, str(o.tr.get("side") or ""))
                                   or XE._red_to(o.tr, "away" if str(o.tr.get("side")) == "home"
                                                 else "home"))))
def _b15(u: Uscita) -> Optional[str]:
    lato = str(u.tr.get("side") or "")
    altro = "away" if lato == "home" else "home"
    rosso_fav = XE._red_to(u.tr, lato)
    rosso_dog = XE._red_to(u.tr, altro)
    d = u.decisione
    motivo = str(getattr(d, "reason", "") or "")
    if rosso_dog and not rosso_fav and motivo.startswith("rosso"):
        return f"rosso alla SFAVORITA ma l'uscita e' '{motivo}': dovrebbe essere neutro"
    if (rosso_fav and bool(u.par.get("red_card_fav_exit", True)) and d is None):
        return "rosso alla FAVORITA e nessuna uscita decisa"
    return None


@_controllo("B16", "SPEC §1: attendi 20-60 s che le quote si stabilizzino",
            "l'uscita innescata da un evento parte dopo il ritardo di assestamento",
            Uscita,
            quando=lambda o: (isinstance(o, Uscita) and o.strategia == "base"
                              and o.decisione is not None
                              and float(getattr(o.decisione, "not_before_ts", 0.0) or 0.0) > 0))
def _b16(u: Uscita) -> Optional[str]:
    ritardo = float(u.par.get("loss_settle_delay_s") or 0.0)
    lo, hi = SPEC_BASE["assestamento"]
    if not (lo <= ritardo <= hi):
        return (f"ritardo di assestamento {ritardo:.0f}s fuori dalla finestra "
                f"{lo:.0f}-{hi:.0f} s della SPEC")
    return None


@_controllo("B17", "SPEC §1 uscita in profitto: il controllo passa alla sfavorita "
                   "-> esci in pari o piccola perdita",
            "con base_control_exit acceso la perdita di controllo produce un'uscita",
            Uscita,
            quando=lambda o: (isinstance(o, Uscita) and o.strategia == "base"
                              and bool(o.par.get("base_control_exit"))))
def _b17(u: Uscita) -> Optional[str]:
    # ⊘ NON ESERCITABILE con i default: `base_control_exit` nasce SPENTA
    # (exits.py:78) perche' dipende dallo stesso dato IPS di B10.
    if XE._controllo_perso(u.tr, u.par) and u.decisione is None:
        return "controllo perso dalla favorita e nessuna uscita decisa"
    return None


# ===========================================================================
# E. CALCIO RISULTATO ESATTO — SPEC §2: banca «Altro risultato Casa/Ospite»
# ===========================================================================
@_controllo("E1", "SPEC §2: LAY su Risultato Esatto, selezione «Altro risultato»",
            "mercato CORRECT_SCORE, lato LAY, selezione Any Other Home/Away Win",
            Valutazione, quando=_valutazione("esatto"))
def _e1(v: Valutazione) -> Optional[str]:
    if str(v.ev.market_type) != "CORRECT_SCORE":
        return f"mercato '{v.ev.market_type}' invece di CORRECT_SCORE"
    if str(v.ev.side or "").upper() != "LAY":
        return f"lato '{v.ev.side}' invece di LAY"
    if v.segnale:
        sid = (v.ctx.any_other_home_selection_id if v.ev.sub_id == "home"
               else v.ctx.any_other_away_selection_id)
        if sid is not None and v.ev.selection_id is not None and int(sid) != int(v.ev.selection_id):
            return (f"segnale sul lato '{v.ev.sub_id}' ma la selezione e' "
                    f"{v.ev.selection_id} invece di {sid} (Any Other)")
    return None


@_controllo("E2", "SPEC §2: minuto ingresso DAL 48' (soglia)",
            "nessun ingresso prima del minuto minimo; sopra la soglia non c'e' tetto",
            Valutazione, quando=_valutazione("esatto"))
def _e2(v: Valutazione) -> Optional[str]:
    if _manca(v, "minute"):
        return "il check del minuto non esiste piu' nella valutazione"
    soglia = _num(v.par.get("minuteMin"))
    if soglia is None or abs(soglia - SPEC_ESATTO["minuteMin"]) > 1e-9:
        return (f"soglia del minuto {soglia} invece del "
                f"{SPEC_ESATTO['minuteMin']:.0f}' della SPEC")
    m = v.ctx.minute
    if v.segnale and soglia is not None and isinstance(m, int) and m < soglia:
        return f"segnale al {m}' con la soglia a {soglia:.0f}'"
    ck = v.check.get("minute")
    if (ck is not None and ck.ok is False and isinstance(m, int)
            and soglia is not None and m >= soglia):
        return f"minuto {m}' >= soglia {soglia:.0f}' ma il check e' FALSO"
    return None


@_controllo("E3", "SPEC §2: punteggio 0-0 / 1-0 / 1-1 / 2-1 (qualsiasi orientamento)",
            "si entra solo con uno dei punteggi ammessi, letti in entrambi i versi",
            Valutazione, quando=_valutazione("esatto"))
def _e3(v: Valutazione) -> Optional[str]:
    if _manca(v, "score"):
        return "il check del punteggio non esiste piu' nella valutazione"
    ammessi_ora = tuple(str(x) for x in (v.par.get("scores") or ()))
    if set(ammessi_ora) != set(SPEC_ESATTO["scores"]):
        return (f"punteggi ammessi {list(ammessi_ora)} invece di "
                f"{list(SPEC_ESATTO['scores'])} della SPEC")
    if not v.segnale:
        return None
    sh, sa = v.ctx.score_home, v.ctx.score_away
    if sh is None or sa is None:
        return None
    ammessi = list(v.par.get("scores") or [])
    if not E.score_in_list_any_order(ammessi, int(sh), int(sa)):
        return f"segnale con {sh}-{sa} fuori dall'elenco {ammessi}"
    return None


@_controllo("E4", "SPEC §2: si banca chi ha segnato AL MASSIMO 1 gol",
            "il lato bancato ha 0 o 1 gol al momento dell'ingresso",
            Valutazione, quando=_segnale("esatto"))
def _e4(v: Valutazione) -> Optional[str]:
    if _manca(v, "sideGoals"):
        return "il check «al massimo 1 gol» non esiste piu' nella valutazione"
    tetto_ora = _num(v.par.get("maxGoalsLaySide"))
    if tetto_ora is None or abs(tetto_ora - SPEC_ESATTO["maxGoalsLaySide"]) > 1e-9:
        return (f"tetto dei gol del lato bancato {tetto_ora} invece di "
                f"{SPEC_ESATTO['maxGoalsLaySide']:.0f} della SPEC")
    if not v.segnale:
        return None
    sh, sa = v.ctx.score_home, v.ctx.score_away
    if sh is None or sa is None:
        return None
    gol = int(sh) if v.ev.sub_id == "home" else int(sa)
    tetto = _num(v.par.get("maxGoalsLaySide"))
    limite = 1 if tetto is None else int(tetto)
    if gol > limite:
        return f"banca il lato '{v.ev.sub_id}' che ha gia' {gol} gol (tetto {limite})"
    return None


@_controllo("E5", "SPEC §2: quota di entrata 30-70",
            "il LAY di «Altro risultato» deve stare nella banda del manuale",
            Valutazione, quando=_valutazione("esatto"))
def _e5(v: Valutazione) -> Optional[str]:
    if _manca(v, "entry"):
        return "il check della quota di entrata non esiste piu' nella valutazione"
    if not _banda_uguale((v.par.get("entryMin"), v.par.get("entryMax")),
                         SPEC_ESATTO["entry"]):
        return (f"banda della quota di entrata [{v.par.get('entryMin')}, "
                f"{v.par.get('entryMax')}] invece di {list(SPEC_ESATTO['entry'])}")
    if not v.segnale:
        return None
    q = _num(v.ev.entry_odds)
    lo, hi = _num(v.par.get("entryMin")), _num(v.par.get("entryMax"))
    if q is None or lo is None or hi is None:
        return None
    if not E.in_range(q, lo, hi):
        return f"quota di entrata {q} fuori da [{lo}, {hi}]"
    return None


@_controllo("E6", "SPEC §2 + «differenze chiave» 1: condizione INVERTITA — la "
                  "squadra BANCATA non deve avere il controllo",
            "con requireControl acceso il check e' sul lato bancato e in verso inverso",
            Valutazione,
            quando=lambda o: (isinstance(o, Valutazione) and o.strategia == "esatto"
                              and bool(o.par.get("requireControl"))))
def _e6(v: Valutazione) -> Optional[str]:
    # ⊘ stessa causa di B10: il dato IPS non e' ancora coperto, il parametro
    # nasce spento e questo controllo non ha mai un caso.
    if _manca(v, "control"):
        return "requireControl acceso ma il check 'control' non esiste"
    return None


@_controllo("E7", "CERT 13/09: UN SOLO lato «Altro risultato» per partita",
            "mai due lay Correct Score vivi sullo stesso evento",
            Ciclo, quando=lambda o: isinstance(o, Ciclo))
def _e7(c: Ciclo) -> Optional[str]:
    vivi: Dict[str, List[Any]] = {}
    for r in c.db.trades:
        if str(r.get("strategy")) != "esatto":
            continue
        if str(r.get("status")) in ("error", "won", "lost", "void"):
            continue
        if r.get("closes_trade_id"):
            continue
        vivi.setdefault(str(r.get("event_id")), []).append(r.get("id"))
    for eid, ids in vivi.items():
        if len(ids) > 1:
            return f"evento {eid}: {len(ids)} lay «Altro risultato» vivi insieme {ids}"
    return None


@_controllo("E8", "SPEC §2 uscita in profitto: esci comunque entro il 70-75'",
            "oltre il minuto di uscita la posizione produce una decisione",
            Uscita, quando=_uscita("esatto"))
def _e8(u: Uscita) -> Optional[str]:
    m = u.tr.get("minute")
    soglia = int(u.par.get("esatto_exit_minute") or 72)
    lo, hi = SPEC_ESATTO["uscita"]
    if not (lo <= soglia <= hi):
        return (f"minuto di uscita {soglia} fuori dalla finestra "
                f"{lo}-{hi} della SPEC")
    if isinstance(m, int) and m >= soglia and u.decisione is None:
        return f"minuto {m}' >= {soglia} ma nessuna decisione di uscita"
    return None


@_controllo("E9", "SPEC §2 uscita in perdita: la squadra BANCATA segna comunque "
                  "-> esci e accetta",
            "il gol del lato bancato produce un'uscita 'loss'; il gol dell'altro no",
            Uscita, quando=_uscita("esatto"))
def _e9(u: Uscita) -> Optional[str]:
    tr = u.tr
    lato = str(tr.get("side") or "")
    altro = "away" if lato == "home" else "home"
    try:
        bancato, bancato_e = int(tr["last_" + lato]), int(tr["entry_" + lato])
        opposto, opposto_e = int(tr["last_" + altro]), int(tr["entry_" + altro])
    except (KeyError, TypeError, ValueError):
        return None
    d = u.decisione
    if bancato > bancato_e:
        if d is None or str(getattr(d, "kind", "")) != "loss":
            return (f"il lato bancato e' passato da {bancato_e} a {bancato} gol "
                    f"ma la decisione e' {getattr(d, 'kind', None)}")
        return None
    if (opposto > opposto_e and d is not None
            and str(getattr(d, "reason", "")) == "lato_bancato_segna"):
        return (f"ha segnato l'ALTRA squadra ({opposto_e}->{opposto}) e l'uscita "
                f"la attribuisce al lato bancato")
    return None


@_controllo("E10", "SPEC §2 «Selezione aggiuntiva»: scontri diretti senza troppi "
                   "2-2/3-3, difesa avversaria solida",
            "con requireSelection acceso il check esiste, guarda la difesa "
            "dell'AVVERSARIA (non della bancata) e boccia chi sfora",
            Valutazione,
            quando=lambda o: (isinstance(o, Valutazione) and o.strategia == "esatto"
                              and bool(o.par.get("requireSelection"))))
def _e10(v: Valutazione) -> Optional[str]:
    """La voce della SPEC implementata il 16/09 su ordine dell'utente.

    Il controllo NON ricalcola chiamando la funzione del motore (sarebbe una
    tautologia): rifa' il conto a mano dai numeri della riga di scan e
    pretende lo stesso verdetto. Cosi' un'inversione dei due lati — la difesa
    della squadra BANCATA al posto di quella avversaria — diventa rossa.
    Spento il parametro, il controllo non ha casi e il referto dice «non lo
    so» con la causa (stessa disciplina di B10 ed E6).
    """
    ck = v.check.get("h2hDifesa")
    if ck is None:
        return ("requireSelection acceso ma il check «selezione aggiuntiva» "
                "non esiste nella valutazione")
    hint = getattr(v.ctx, "selection_hint", None)
    lato = str(v.ev.sub_id or "")
    if lato not in ("home", "away"):
        return None
    incontri = _num((hint or {}).get("h2h_meetings")) if isinstance(hint, dict) else None
    alti = _num((hint or {}).get("h2h_big_draws")) if isinstance(hint, dict) else None
    subiti_da = (hint or {}).get("conceded") if isinstance(hint, dict) else None
    avversaria = "away" if lato == "home" else "home"
    subiti = _num(subiti_da.get(avversaria)) if isinstance(subiti_da, dict) else None
    rate_max = _num(v.par.get("h2hBigDrawRateMax"))
    conceded_max = _num(v.par.get("oppConcededMax"))
    if rate_max is None or conceded_max is None:
        return "soglie della selezione aggiuntiva assenti dai parametri"
    # Q7 (ordine dell'utente 25/09): «dove disponibile». Ogni parte si
    # giudica per conto suo: col dato si applica la soglia, senza dato NON
    # blocca. Il conto si rifa' qui a mano, parte per parte.
    h2h_ok = (float(alti) / float(incontri) <= rate_max
              if incontri is not None and incontri > 0 and alti is not None else None)
    dif_ok = float(subiti) <= conceded_max if subiti is not None else None
    atteso = h2h_ok is not False and dif_ok is not False
    if ck.ok is None:
        return ("il check della selezione aggiuntiva e' n/d: dal 25/09 un dato "
                "assente NON blocca, deve dirlo e lasciar passare")
    if bool(ck.ok) is not atteso:
        return (f"verdetto {ck.ok} ma dai numeri (scontri {alti}/{incontri} 2-2/3-3 -> "
                f"{h2h_ok}, difesa {avversaria} {subiti} -> {dif_ok}; None = dato "
                f"assente, non blocca) ci si aspetta {atteso}: soglie "
                f"{rate_max} / {conceded_max}")
    if v.segnale and ck.ok is not True:
        return f"segnale con la selezione aggiuntiva non superata (check={ck.ok})"
    return None


# ===========================================================================
# P. CALCIO PUNTA — SPEC §4: punta (back) la favorita avanti di due gol
# ===========================================================================
@_controllo("P1", "SPEC §4: PUNTA (back) sul 1X2, selezione = la favorita in vantaggio",
            "mercato MATCH_ODDS, lato BACK, selezione = favorita che sta vincendo",
            Valutazione, quando=_valutazione("punta"))
def _p1(v: Valutazione) -> Optional[str]:
    if str(v.ev.market_type) != "MATCH_ODDS":
        return f"mercato '{v.ev.market_type}' invece di MATCH_ODDS"
    if str(v.ev.side or "").upper() != "BACK":
        return f"lato '{v.ev.side}' invece di BACK"
    if not v.segnale:
        return None
    fav, lead = _fav(v), _leader(v)
    if fav is not None and lead is not None and lead != fav:
        return f"punta con il leader '{lead}' diverso dalla favorita '{fav}'"
    atteso = _nome(v, lead)
    if atteso is not None and v.ev.selection is not None and str(v.ev.selection) != str(atteso):
        return f"punta '{v.ev.selection}' ma il leader e' '{atteso}'"
    return None


@_controllo("P2", "SPEC §4: minuto ingresso DAL 66' (soglia)",
            "nessun ingresso prima del minuto minimo; sopra la soglia non c'e' tetto",
            Valutazione, quando=_valutazione("punta"))
def _p2(v: Valutazione) -> Optional[str]:
    if _manca(v, "minute"):
        return "il check del minuto non esiste piu' nella valutazione"
    soglia = _num(v.par.get("minuteMin"))
    if soglia is None or abs(soglia - SPEC_PUNTA["minuteMin"]) > 1e-9:
        return (f"soglia del minuto {soglia} invece del "
                f"{SPEC_PUNTA['minuteMin']:.0f}' della SPEC")
    m = v.ctx.minute
    if v.segnale and soglia is not None and isinstance(m, int) and m < soglia:
        return f"segnale al {m}' con la soglia a {soglia:.0f}'"
    ck = v.check.get("minute")
    if (ck is not None and ck.ok is False and isinstance(m, int)
            and soglia is not None and m >= soglia):
        return f"minuto {m}' >= soglia {soglia:.0f}' ma il check e' FALSO"
    return None


@_controllo("P3", "SPEC §4: punteggio 2-0 / 3-1 / 3-0 (orientato sul leader)",
            "si entra solo con due gol di scarto e uno dei punteggi ammessi",
            Valutazione, quando=_valutazione("punta"))
def _p3(v: Valutazione) -> Optional[str]:
    if _manca(v, "score"):
        return "il check del punteggio non esiste piu' nella valutazione"
    ammessi_ora = tuple(str(x) for x in (v.par.get("scores") or ()))
    if set(ammessi_ora) != set(SPEC_PUNTA["scores"]):
        return (f"punteggi ammessi {list(ammessi_ora)} invece di "
                f"{list(SPEC_PUNTA['scores'])} della SPEC")
    if not v.segnale:
        return None
    sh, sa = v.ctx.score_home, v.ctx.score_away
    lead = _leader(v)
    if sh is None or sa is None or lead is None:
        return None
    g_lead = sh if lead == "home" else sa
    g_altro = sa if lead == "home" else sh
    ammessi = list(v.par.get("scores") or [])
    if not E.score_in_list_oriented(ammessi, int(g_lead), int(g_altro)):
        return f"segnale con {g_lead}-{g_altro} (leader) fuori dall'elenco {ammessi}"
    return None


@_controllo("P4", "SPEC §4: quota di entrata 1.03-1.10",
            "il BACK del leader deve stare nella banda del manuale",
            Valutazione, quando=_valutazione("punta"))
def _p4(v: Valutazione) -> Optional[str]:
    if _manca(v, "entry"):
        return "il check della quota di entrata non esiste piu' nella valutazione"
    if not _banda_uguale((v.par.get("entryMin"), v.par.get("entryMax")),
                         SPEC_PUNTA["entry"]):
        return (f"banda della quota di entrata [{v.par.get('entryMin')}, "
                f"{v.par.get('entryMax')}] invece di {list(SPEC_PUNTA['entry'])}")
    if not v.segnale:
        return None
    q = _num(v.ev.entry_odds)
    lo, hi = _num(v.par.get("entryMin")), _num(v.par.get("entryMax"))
    if q is None or lo is None or hi is None:
        return None
    if not E.in_range(q, lo, hi):
        return f"quota di entrata {q} fuori da [{lo}, {hi}]"
    return None


@_controllo("P5", "SPEC §4: aspetta 3-4' dopo il gol",
            "fra il gol e l'ingresso devono passare almeno i minuti della SPEC",
            Valutazione, quando=_valutazione("punta"))
def _p5(v: Valutazione) -> Optional[str]:
    if _manca(v, "settled"):
        return "il check dell'attesa dopo il gol non esiste piu' nella valutazione"
    attesa = _num(v.par.get("minMinutesAfterGoal"))
    lo, hi = SPEC_PUNTA["attesaGol"]
    if attesa is None or not (lo - 1e-9 <= attesa <= hi + 1e-9):
        return (f"attesa dopo il gol {attesa}' fuori dalla finestra "
                f"{lo:.0f}-{hi:.0f}' della SPEC")
    if not v.segnale:
        return None
    da = v.ctx.score_stable_since_minute
    m = v.ctx.minute
    if isinstance(da, int) and isinstance(m, int) and attesa is not None:
        if (m - da) < attesa:
            return f"segnale a {m - da}' dal gol, ne servono {attesa:.0f}"
    return None


@_controllo("P6", "SPEC §4: la favorita deve CONTINUARE A SPINGERE",
            "con requireControl acceso il check di controllo deve esistere",
            Valutazione,
            quando=lambda o: (isinstance(o, Valutazione) and o.strategia == "punta"
                              and bool(o.par.get("requireControl"))))
def _p6(v: Valutazione) -> Optional[str]:
    # ⊘ stessa causa di B10/E6.
    if _manca(v, "control"):
        return "requireControl acceso ma il check 'control' non esiste"
    return None


@_controllo("P7", "SPEC §4 uscita in perdita: QUALSIASI gol subito -> esci "
                  "immediatamente, anche se si sta ancora vincendo",
            "il gol dell'altra squadra produce un'uscita 'loss', prima di ogni altra",
            Uscita, quando=_uscita("punta"))
def _p7(u: Uscita) -> Optional[str]:
    tr = u.tr
    lato = str(tr.get("side") or "")
    altro = "away" if lato == "home" else "home"
    try:
        dog, dog_e = int(tr["last_" + altro]), int(tr["entry_" + altro])
    except (KeyError, TypeError, ValueError):
        return None
    if dog <= dog_e:
        return None
    d = u.decisione
    if d is None:
        return f"gol subito ({dog_e}->{dog}) e nessuna uscita decisa"
    if str(getattr(d, "kind", "")) != "loss":
        return (f"gol subito ({dog_e}->{dog}) ma l'uscita e' "
                f"'{getattr(d, 'kind', None)}' ({getattr(d, 'reason', None)})")
    return None


@_controllo("P8", "SPEC §4 uscita in profitto: arriva il gol successivo -> cashout",
            "un gol in piu' del leader produce un'uscita in profitto",
            Uscita, quando=_uscita("punta"))
def _p8(u: Uscita) -> Optional[str]:
    tr = u.tr
    lato = str(tr.get("side") or "")
    altro = "away" if lato == "home" else "home"
    try:
        fav, fav_e = int(tr["last_" + lato]), int(tr["entry_" + lato])
        dog, dog_e = int(tr["last_" + altro]), int(tr["entry_" + altro])
    except (KeyError, TypeError, ValueError):
        return None
    if fav <= fav_e or dog > dog_e:
        return None
    d = u.decisione
    if d is None or str(getattr(d, "kind", "")) != "profit":
        return (f"leader passato da {fav_e} a {fav} gol senza subire, ma la "
                f"decisione e' {getattr(d, 'kind', None)}")
    return None


@_controllo("P9", "SPEC §4 uscita a tempo: esci comunque entro l'83'",
            "oltre il minuto di uscita la posizione produce una decisione",
            Uscita, quando=_uscita("punta"))
def _p9(u: Uscita) -> Optional[str]:
    soglia = int(u.par.get("punta_exit_minute") or 83)
    lo, hi = SPEC_PUNTA["uscita"]
    if not (lo <= soglia <= hi):
        return f"minuto di uscita {soglia} invece dell'{lo}' della SPEC"
    m = u.tr.get("minute")
    if isinstance(m, int) and m >= soglia and u.decisione is None:
        return f"minuto {m}' >= {soglia} ma nessuna decisione di uscita"
    return None


@_controllo("P10", "SPEC §4: per la PUNTA il rosso NON e' una regola di uscita",
            "nessuna uscita della punta puo' essere motivata dal cartellino rosso",
            Uscita,
            quando=lambda o: (isinstance(o, Uscita) and o.strategia == "punta"
                              and o.decisione is not None))
def _p10(u: Uscita) -> Optional[str]:
    motivo = str(getattr(u.decisione, "reason", "") or "")
    if motivo.startswith("rosso") or str(getattr(u.decisione, "kind", "")) == "red_card":
        return f"uscita della PUNTA motivata dal rosso ('{motivo}'): non e' nella SPEC"
    return None


# ===========================================================================
# T. TRASVERSALI — le regole che valgono per tutte e tre
# ===========================================================================
@_controllo("T1", "B.5 (16/09): stake PER STRATEGIA, con ripiego per lato",
            "l'importo dell'ordine e' quello dichiarato per quella strategia",
            Ordine,
            quando=lambda o: (isinstance(o, Ordine) and o.apertura
                              and o.origine == "auto"
                              and o.strategia in STRATEGIE_CALCIO))
def _t1(o: Ordine) -> Optional[str]:
    if not o.params:
        return None
    atteso = E.stake_di_strategia(o.params, o.strategia,
                                  str(o.riga.get("side") or ""))
    chiesto = _num(o.riga.get("size"))
    if atteso is None or chiesto is None:
        return None
    # la size puo' essere CAPPATA alla liquidita' (`execution.place`): mai
    # maggiore dello stake dichiarato, mai diversa senza cappatura.
    if chiesto > float(atteso) + 0.005:
        return (f"stake chiesto {chiesto} maggiore di quello dichiarato per "
                f"'{o.strategia}' ({atteso})")
    return None


@_controllo("T2", "PROCESSO §6.4 / CERT 12/09: FILL OR KILL — un parziale e' un ERRORE",
            "nessuna riga 'open' con abbinato minore del chiesto (paper e live)",
            Ordine, quando=lambda o: isinstance(o, Ordine))
def _t2(o: Ordine) -> Optional[str]:
    if str(getattr(o.esito, "status", "")) != "open":
        return None
    # il CHIESTO autoritativo e' quello che Betfair ha ricevuto
    # (`size_requested` della riga d'ordine), non quello che il bot voleva
    # prima della cappatura alla liquidita' (`execution.place` la dichiara in
    # `meta.size_capped_from`, ed e' una riduzione VOLUTA, non un parziale).
    st = o.stato_betfair or {}
    chiesto = _num(st.get("size_requested"))
    abbinato = _num(st.get("size_matched"))
    if chiesto is None:
        chiesto = _num(getattr(o.esito, "size_requested", None))
    if abbinato is None:
        abbinato = _num(getattr(o.esito, "size", None))
    if chiesto is None or abbinato is None:
        return None
    if abbinato + 0.005 < chiesto:
        return (f"riga aperta con abbinato {abbinato} su {chiesto} chiesti a "
                f"Betfair: il FILL OR KILL avrebbe ucciso l'ordine (percorso "
                f"{getattr(o.esito, 'fill_note', None)})")
    return None


@_controllo("T3", "PROCESSO §6.4: la chiusura si manda al BEST OPPOSTO, spinta "
                  "dentro di qualche tick",
            "il piano di chiusura non usa il lato sbagliato del book",
            Ordine, quando=lambda o: isinstance(o, Ordine) and not o.apertura)
def _t3(o: Ordine) -> Optional[str]:
    lato = str(o.riga.get("side") or "").lower()
    prezzo = _num(o.riga.get("price"))
    if lato not in ("back", "lay") or prezzo is None:
        return None
    # una chiusura e' il lato OPPOSTO dell'apertura: se la riga di chiusura ha lo
    # stesso lato del padre, si sta raddoppiando la posizione, non chiudendola.
    padre = o.riga.get("_padre") if isinstance(o.riga.get("_padre"), dict) else None
    if padre is None:
        return None
    if str(padre.get("side") or "").lower() == lato:
        return (f"chiusura sullo STESSO lato dell'apertura ('{lato}'): "
                f"raddoppia invece di chiudere")
    return None


@_controllo("T4", "CERT 13/09 + 12/09: mai chiudere in perdita quando il margine "
                  "e' ampio (decisione a MODELLO)",
            "le uscite in profitto/tempo passano dal modello; quelle in perdita mai",
            Uscita,
            quando=lambda o: (isinstance(o, Uscita) and o.decisione is not None
                              and str(getattr(o.decisione, "kind", "")) in XE.PROFIT_KINDS))
def _t4(u: Uscita) -> Optional[str]:
    soglia = _num(u.par.get("hold_max_risk"))
    if soglia is None or soglia <= 0:
        return ("hold_max_risk spento: una chiusura a tempo con P&L negativo e "
                "rischio quasi nullo non verrebbe piu' trattenuta")
    return None


@_controllo("T5", "Decisione utente 3+4 (16/09): combo «piazza e svolge» UGUALE "
                  "in paper e in live (guardia L4 rimossa)",
            "nessun ramo di combo condizionato alla modalita'",
            Ciclo, quando=lambda o: isinstance(o, Ciclo) and bool(
                o.params.get("auto_trade_combos")))
def _t5(c: Ciclo) -> Optional[str]:
    # ⊘ FUORI PERIMETRO C.3: le combo sono opportunita' a MODELLO, non una delle
    # tre strategie della SPEC. Nel replay il modello non e' montato, quindi
    # questo controllo non ha mai un caso e il referto lo dichiara.
    return None


@_controllo("T6", "PROCESSO §6.3 / manuale: lo stop giornaliero e i tetti fermano "
                  "le APERTURE, mai le uscite",
            "a stop attivo nessuna riga nuova viene aperta, le chiusure continuano",
            Ciclo,
            quando=lambda o: (isinstance(o, Ciclo)
                              and float((o.params.get("risk") or {}).get(
                                  "daily_loss_stop") or o.params.get("daily_loss_stop") or 0.0) < 0))
def _t6(c: Ciclo) -> Optional[str]:
    from . import risk as RK

    try:
        agg = c.db.aggregates(mode=c.mode)
    except Exception:  # noqa: BLE001 - un aggregato illeggibile non e' un difetto del bot
        return None
    attivo = RK.loss_stop_active(agg.get("realized_today", 0.0), c.params)
    if attivo and c.aperture_nel_giro > 0:
        return (f"stop giornaliero attivo (realizzato {agg.get('realized_today')}) "
                f"ma {c.aperture_nel_giro} aperture in questo giro")
    return None


@_controllo("T7", "CERT 13/09: i tetti di rischio a 0 sono SPENTI",
            "un cap a zero non protegge: va detto, non dedotto",
            Ciclo, quando=lambda o: isinstance(o, Ciclo))
def _t7(c: Ciclo) -> Optional[str]:
    # non e' una violazione del bot: e' una DICHIARAZIONE. Il controllo tace e
    # lascia il fatto alle note del referto (il replay lo scrive), ma resta
    # registrato perche' la voce compaia nella copertura.
    return None


@_controllo("T8", "CERT 14/09: MODALITA' PER STRATEGIA (`strategy_modes`)",
            "ogni riga porta la modalita' della SUA strategia, mai quella ereditata",
            Ordine,
            quando=lambda o: (isinstance(o, Ordine) and o.apertura
                              and o.origine == "auto"
                              and o.strategia in STRATEGIE_CALCIO))
def _t8(o: Ordine) -> Optional[str]:
    # ⚠️ SOLO l'automatico: il percorso MANUALE non passa da `strategy_modes`
    # (la modalita' e' quella del payload, validata contro `control.mode` in
    # `_request_place`). Accusarlo qui sarebbe un falso positivo del controllo,
    # non un difetto del bot (PROCESSO §6.7).
    from .bot_service import modalita_di_strategia

    if not o.params:
        return None
    atteso = modalita_di_strategia(o.strategia, o.mode, o.params)
    scritto = str(o.riga.get("mode") or "")
    if scritto and scritto != atteso:
        return (f"riga in modalita' '{scritto}' ma `strategy_modes` dice "
                f"'{atteso}' per '{o.strategia}'")
    return None


@_controllo("T9", "CERT 12/09: nessun ingresso su una riga del feed NON FRESCA",
            "feed vecchio o assente: le aperture si fermano, le uscite no",
            Ciclo,
            quando=lambda o: isinstance(o, Ciclo) and bool(getattr(o, "feed_stantio", False)))
def _t9(c: Ciclo) -> Optional[str]:
    if c.aperture_nel_giro > 0:
        return (f"feed dichiarato stantio ma {c.aperture_nel_giro} aperture "
                f"in questo giro")
    return None


@_controllo("T10", "CERT 15/09: una variante NON ABILITATA si scarta DICENDOLO",
            "lo scarto per variante spenta lascia sempre una riga di attivita'",
            Ciclo, quando=lambda o: isinstance(o, Ciclo) and bool(
                getattr(o, "segnali_di_variante_spenta", 0)))
def _t10(c: Ciclo) -> Optional[str]:
    quanti = int(getattr(c, "segnali_di_variante_spenta", 0) or 0)
    motivi = [p for k, p, _e in getattr(c.db, "attivita", [])
              if k == "skip" and str((p or {}).get("reason")) == "variante_non_abilitata"]
    if quanti and not motivi:
        return f"{quanti} segnali di variante spenta e nessuno scarto dichiarato"
    return None


@_controllo("T11", "PROCESSO §6.4: minimo di giurisdizione .it e place-and-trim",
            "sotto il minimo si usa il place-and-trim, non si rifiuta",
            Ordine,
            quando=lambda o: (isinstance(o, Ordine)
                              and "submin" in str(getattr(o.esito, "fill_note", "") or "")))
def _t11(o: Ordine) -> Optional[str]:
    # ⊘ NON ESERCITABILE SUL BANCO: flumine non ha il minimo di giurisdizione
    # (`MercatoFlumine.place_submin_live` piazza diretto), quindi il percorso
    # place-and-trim non ha nulla da aggirare e non viene mai sollecitato.
    return None



# ---------------------------------------------------------------------------
# LA REGOLA DI PIATTAFORMA DEL 16/09 (ordine dell'utente) + IL MANUALE
# ---------------------------------------------------------------------------
def _e_del_bot(riga: Dict[str, Any]) -> bool:
    """La riga e' un'operazione DEL BOT, non del trader.

    ⚠️ Chiarimento dell'utente del 16/09: «se io in MANUALE faccio altre
    operazioni su quella partita, il bot deve ignorarle e operare per conto suo
    sulle SUE operazioni». Il servizio distingue le proprie righe con
    ``origin='auto'`` — ed e' la stessa chiave con cui le sceglie da solo
    (`bot_service._exit_candidates:2013`, `_traded_keys`, `place_attempts`).
    Un ordine del trader non e' mai una violazione del bot.
    """
    return str(riga.get("origin") or "") == "auto"


def _riga_del_ref(c: "Ciclo", ref: Any) -> Optional[Dict[str, Any]]:
    """Dalla `customer_order_ref` (`safe-t<id>`) alla riga che l'ha piazzata."""
    testo = str(ref or "")
    if "t" not in testo:
        return None
    coda = testo.rsplit("t", 1)[-1]
    if not coda.isdigit():
        return None
    for tr in getattr(c.db, "trades", []) or []:
        if int(tr.get("id") or 0) == int(coda):
            return tr
    return None



# «Non devono mai esserci 2 lay a mercato sullo stesso mercato/selezione: se si
# abbinano siamo scoperti.» Non e' una regola di UNA strategia: BASE ed ESATTO
# bancano, le chiusure di un back bancano, le gambe di combo bancano — e due
# banche vive sulla stessa selezione, se si abbinano tutte e due, raddoppiano la
# responsabilita' contro un incasso che era stato dimensionato per una sola.
# Vale ANCHE per un solo giro, e ANCHE quando la seconda nasce per sostituire la
# prima: finche' il `cancel` non e' stato riletto da Betfair, le lay a mercato
# sono due.
def _e_chiusura_appaiata(c: "Ciclo", tr: Dict[str, Any]) -> bool:
    """La lay `tr` CHIUDE un back del bot sulla stessa selezione?

    Vero solo se: ha `closes_trade_id` in COLONNA, il padre esiste, e' un BACK
    del bot, ed e' sullo STESSO mercato e sulla STESSA selezione. In quel caso
    la responsabilita' della lay e' compensata dal back che chiude: la
    posizione e' piatta. Qualunque dubbio (padre assente, altra selezione,
    altro lato) -> False, cioe' la lay CONTA: il controllo resta severo.
    """
    padre_id = tr.get("closes_trade_id")
    if padre_id is None:
        return False
    try:
        padre_id = int(padre_id)
    except (TypeError, ValueError):
        return False
    for padre in getattr(c.db, "trades", []) or []:
        if int(padre.get("id") or 0) != padre_id:
            continue
        return bool(
            str(padre.get("side") or "").lower() == "back"
            and _e_del_bot(padre)
            and str(padre.get("market_id")) == str(tr.get("market_id"))
            and str(padre.get("selection_id")) == str(tr.get("selection_id"))
        )
    return False


def _lay_in_volo(c: "Ciclo") -> Dict[Tuple[str, int], List[str]]:
    """(mercato, selezione) -> le lay che POSSONO ancora abbinarsi adesso.

    Sono tre cose diverse e contano tutte:
      * la riga 'pending', che e' un ordine partito o in volo (anche a esito
        IGNOTO: §4.11 dice che conta SEMPRE nel rischio, peggior caso);
      * l'ordine ancora EXECUTABLE su Betfair (`list_current_orders`), che e'
        la verita' dell'exchange;
      * la riga 'open' il cui ordine ha ancora un residuo vivo.
    Una riga e il suo ordine sono la STESSA lay: si contano per `bet_id` quando
    c'e', per id di riga quando non c'e' ancora.
    """
    vivi: Dict[Tuple[str, int], List[str]] = {}
    visti: Dict[str, Tuple[str, int]] = {}

    def _aggiungi(mid: Any, sid: Any, identita: str, come: str) -> None:
        if not mid or sid is None:
            return
        try:
            chiave = (str(mid), int(sid))
        except (TypeError, ValueError):
            return
        if identita in visti:
            return
        visti[identita] = chiave
        vivi.setdefault(chiave, []).append(come)

    try:
        ordini = list(c.market.list_current_orders() or [])
    except Exception:  # noqa: BLE001 - una lettura KO non e' un difetto del bot
        ordini = []
    vivi_per_bet: Dict[str, Dict[str, Any]] = {}
    for r in ordini:
        if str(r.get("side") or "").lower() != "lay":
            continue
        if str(r.get("status") or "").upper() != "EXECUTABLE":
            continue
        bid = str(r.get("bet_id") or "")
        if not bid:
            continue
        vivi_per_bet[bid] = r
    for tr in getattr(c.db, "trades", []) or []:
        if str(tr.get("side") or "").lower() != "lay":
            continue
        if not _e_del_bot(tr):
            continue        # le operazioni del trader non sono del bot
        stato = str(tr.get("status") or "")
        bid = str(tr.get("bet_id") or "")
        if stato == "pending":
            _aggiungi(tr.get("market_id"), tr.get("selection_id"),
                      bid or f"riga:{tr.get('id')}", f"riga {tr.get('id')} pending")
        elif stato == "open":
            # ⚠️ ANCHE UNA LAY GIA' ABBINATA CONTA. L'ordine dell'utente e'
            # «se si abbinano siamo scoperti»: due lay abbinate sulla stessa
            # selezione SONO il danno, non il rischio. Contarne solo quelle
            # ancora a mercato vorrebbe dire dichiarare sano proprio il caso
            # che la regola vuole impedire — e con il FOK, che abbina o uccide
            # nello stesso giro, sarebbe l'unico caso che capita davvero.
            #
            # ECCEZIONE, 16/09 (trovata dalle registrazioni sintetiche della
            # PUNTA): una lay di CHIUSURA gia' abbinata non e' responsabilita'
            # viva. La PUNTA e il tennis PUNTANO e chiudono BANCANDO la STESSA
            # selezione: due operazioni consecutive nella stessa partita
            # lasciano due righe lay `open`, ognuna appaiata al SUO back sulla
            # stessa selezione e per la stessa size — posizione piatta, non
            # scoperta. Contarle faceva scattare T12 x159 su una condotta
            # corretta: falso positivo del CONTROLLO, non difetto del bot
            # (PROCESSO §6.7). E' la stessa lettura che il gemello del tennis
            # (`certificazione_tennis._lay_in_volo`) aveva gia' scritto per la
            # chiusura del residuo. Resta contata la chiusura con RESIDUO VIVO:
            # quella e' ancora a mercato e puo' abbinarsi.
            if _e_chiusura_appaiata(c, tr) and bid not in vivi_per_bet:
                continue
            come = (f"riga {tr.get('id')} con residuo vivo" if bid in vivi_per_bet
                    else f"riga {tr.get('id')} ABBINATA (responsabilita' viva)")
            _aggiungi(tr.get("market_id"), tr.get("selection_id"),
                      bid or f"riga:{tr.get('id')}", come)
    for bid, r in vivi_per_bet.items():
        riga = _riga_del_ref(c, r.get("customer_order_ref"))
        if riga is None or not _e_del_bot(riga):
            # un ordine che non si riconduce a una riga AUTOMATICA non e' del
            # bot: non lo si accusa (e non lo si nasconde, e' nel referto).
            continue
        _aggiungi(r.get("market_id"), r.get("selection_id"), bid,
                  f"ordine {bid} EXECUTABLE su Betfair")
    return vivi


def _c_ha_lay_vive(o: Any) -> bool:
    return isinstance(o, Ciclo) and bool(_lay_in_volo(o))


@_controllo("T12", "Regola di piattaforma (utente, 16/09): MAI due lay DEL BOT "
                   "sullo stesso mercato e selezione",
            "due lay AUTOMATICHE vive (a mercato, in volo o gia' abbinate) sulla "
            "stessa selezione: la posizione resta scoperta. Le operazioni "
            "manuali del trader non contano: il bot opera sulle SUE",
            Ciclo, quando=_c_ha_lay_vive)
def _t12(c: Ciclo) -> Optional[str]:
    for (mid, sid), quali in sorted(_lay_in_volo(c).items()):
        if len(quali) > 1:
            return (f"{len(quali)} lay vive sul mercato {mid} selezione {sid}: "
                    f"{quali}. Abbinate tutte, la responsabilita' raddoppia "
                    f"contro un incasso dimensionato per una sola: e' la "
                    f"posizione scoperta che la regola del 16/09 vieta.")
    # SOSTITUZIONE nello stesso giro: `cancel` e `place` sulla stessa lay dentro
    # lo stesso ciclo. Finche' Betfair non ha confermato il `cancel` le lay a
    # mercato sono DUE, e il fatto che il bot le consideri una sola non cambia
    # cosa puo' abbinarsi. Si RIPORTA: e' un reperto per l'utente, non una
    # correzione da fare di iniziativa (e' comportamento di strategia).
    annullate: set = set()
    piazzate: set = set()
    per_id = {int(t.get("id") or 0): t for t in (getattr(c.db, "trades", []) or [])}
    for kind, payload, _eid in (c.attivita_del_giro or []):
        tr = per_id.get(int((payload or {}).get("trade_id") or 0))
        if tr is None or str(tr.get("side") or "").lower() != "lay":
            continue
        chiave = (str(tr.get("market_id")), tr.get("selection_id"))
        if str(kind).startswith("cancel"):
            annullate.add(chiave)
        elif str(kind) in ("place", "place_pending", "place_parziale"):
            piazzate.add(chiave)
    doppie = annullate & piazzate
    if doppie:
        return (f"sostituzione di una lay nello STESSO giro su {sorted(doppie)}: "
                f"cancel e place insieme. Finche' il cancel non e' riletto da "
                f"Betfair le lay a mercato sono due (reperto per l'utente).")
    return None




# ---------------------------------------------------------------------------
# T13 — IL MANUALE E IL BOT NON SI TOCCANO (chiarimento dell'utente, 16/09)
# ---------------------------------------------------------------------------
# ⚠️ SOLO i kind che scrive ESCLUSIVAMENTE il percorso automatico
# (`_process_exit_one:2285`, `_send_exit:3433`, `_model_gate:2694`): `cashout`,
# `exit_wait` e `place` li scrive anche `execution.close_trade`, che serve pure
# al bottone del trader — accusarli sarebbe un falso positivo del controllo,
# non un difetto del bot (PROCESSO §6.7). Verificato: il 16/09 la prima stesura
# li conteneva e accusava il trader che chiudeva la PROPRIA riga.
_KIND_CHE_TOCCANO = ("exit", "exit_retry", "exit_hold")


def _manuali_vive(c: "Ciclo") -> List[Dict[str, Any]]:
    return [t for t in (getattr(c.db, "trades", []) or [])
            if str(t.get("origin") or "") == "manual"
            and str(t.get("status") or "") in ("pending", "open", "hedged")]


@_controllo("T13", "Chiarimento dell'utente (16/09): le operazioni MANUALI del "
                   "trader non sono del bot",
            "il bot non chiude, non annulla e non porta a terminale una riga "
            "manuale: opera solo sulle SUE gambe",
            Ciclo, quando=lambda o: isinstance(o, Ciclo) and bool(_manuali_vive(o)))
def _t13(c: Ciclo) -> Optional[str]:
    manuali = {int(t.get("id") or 0) for t in _manuali_vive(c)}
    # 24/09 (estensione B25) - con `combo_gamba_manuale='automatico'` SCRITTO
    # dall'utente, la gamba manuale di una combo incompleta la chiude il bot
    # PER SCELTA SUA: quelle righe escono da T13 (le giudica T13-COMBO).
    if _modo_gamba_manuale(c.params) == "automatico":
        manuali -= {int(t.get("id") or 0) for t in _gambe_manuali_di_combo_incompleta(c)}
    # (a) una gamba di CHIUSURA automatica su un padre manuale: e' il bot che
    #     chiude un'operazione del trader.
    for tr in getattr(c.db, "trades", []) or []:
        padre = tr.get("closes_trade_id")
        if padre is None or int(padre) not in manuali:
            continue
        if str(tr.get("origin") or "") == "auto":
            return (f"il bot ha aperto la gamba di chiusura {tr.get('id')} "
                    f"(origin=auto) sulla riga MANUALE {padre}: le operazioni "
                    f"del trader le chiude il trader")
    # (b) un'attivita' di uscita/annullamento su una riga manuale che NON viene
    #     da una richiesta della UI (il payload del manuale porta origin/mode
    #     della richiesta; l'automatico no).
    for kind, payload, _eid in (c.attivita_del_giro or []):
        if str(kind) not in _KIND_CHE_TOCCANO:
            continue
        tid = (payload or {}).get("trade_id")
        if tid is None or int(tid) not in manuali:
            continue
        return (f"attivita' '{kind}' del percorso automatico sulla riga MANUALE "
                f"{tid}: il bot sta operando su un'operazione del trader")
    return None


# ---------------------------------------------------------------------------
# T13-COMBO - B25 (24/09): "LASCIA E AVVISA" sulla gamba manuale di una combo
# ---------------------------------------------------------------------------
# Decisione dell'utente (reperto T13 x2734 su `combos-automatiche`): "il bot non
# deve MAI chiudere le mie gambe (le righe manuali del trader), ma deve essere
# informato, come gia' succede, quando chiudo io tutte le operazioni".
# Una combo approvata dal trader nasce con TUTTE le gambe `origin='manual'`; se
# una gamba FOK e' uccisa, la gamba abbinata resta sua. Tre cose insieme:
#   (a) nessuna gamba di chiusura `origin='auto'` su quella riga, MAI;
#   (b) la riga e' MARCATA (`meta.combo_lasciata_al_trader`) e l'avviso e'
#       SCRITTO: UNA riga di attivita' `combo_incomplete` con
#       `lasciata_al_trader=True` e il suo `trade_id` (una sola: un avviso
#       ripetuto a ogni giro e' rumore, non informazione);
#   (c) nessuna attivita' del percorso d'uscita del bot su quella riga nel giro.
# Il marcatore si scrive nello STESSO `run_once` in cui la gamba e' vista aperta
# (`_esegui_combo_riservata` all'approvazione, `unwind_incomplete_combos` al
# fill confermato dalla coda, entrambi prima della fine del giro): a fine giro
# una gamba aperta senza marcatore e' un avviso MANCATO, non un avviso in volo.
#
# 24/09 (estensione B25, ordine dell'utente: "devo poter scegliere tramite
# pulsanti"): il parametro `combo_gamba_manuale` decide.
#   - 'avvisa_e_proponi' (default, anche se assente o sconosciuto): (a)-(c) come
#     sopra, piu' (d) al massimo UNA proposta di copertura viva per gamba e
#     (e) nessuna proposta nuova dopo che la prima ha avuto un esito
#     (rifiutata, approvata, decaduta);
#   - 'automatico': la chiusura automatica della gamba manuale e' CONFORME,
#     ma deve portare la scelta dell'utente nel motivo (audit) - una chiusura
#     senza quel motivo e' il bot che chiude di testa sua.
COMBO_LASCIATA_KEY = "combo_lasciata_al_trader"
_KIND_USCITA_DEL_BOT = ("exit", "exit_retry", "exit_hold", "exit_wait", "exit_failed")
_AUDIT_AUTOMATICO = "combo_gamba_manuale=automatico"


def _modo_gamba_manuale(params: Any) -> str:
    """Stessa regola di `bot_service.modo_gamba_manuale` (fail-closed)."""
    v = str((params or {}).get("combo_gamba_manuale") or "").strip().lower() \
        if isinstance(params, dict) else ""
    return "automatico" if v == "automatico" else "avvisa_e_proponi"


def _proposte_vive_di(c: "Ciclo", gid: int) -> Optional[int]:
    """Quante proposte di chiusura 'proposed' ci sono per la gamba (None se il
    doppio non tiene la coda delle richieste)."""
    coda = getattr(c.db, "requests", None)
    if coda is None:
        return None
    return sum(1 for r in coda
               if str(r.get("status") or "") == "proposed"
               and str(r.get("kind") or "") == "cashout"
               and str((r.get("payload") or {}).get("trade_id")) == str(gid))


def _gambe_manuali_di_combo_incompleta(c: "Ciclo") -> List[Dict[str, Any]]:
    return [t for t in (getattr(c.db, "trades", []) or [])
            if str(t.get("origin") or "") == "manual"
            and not t.get("closes_trade_id")
            and (t.get("meta") or {}).get("combo_incomplete")
            and str(t.get("status") or "") in ("pending", "open", "hedged")]


@_controllo("T13-COMBO", "Decisione dell'utente B25 (24/09): LASCIA E AVVISA: la "
                         "gamba MANUALE di una combo incompleta non la chiude il bot",
            "gamba manuale lasciata a mercato, marcata e annunciata UNA volta in "
            "attivita'; nessuna chiusura automatica e nessuna uscita del bot su "
            "quella riga, ne' in quel giro ne' dopo",
            Ciclo, quando=lambda o: isinstance(o, Ciclo)
            and bool(_gambe_manuali_di_combo_incompleta(o)))
def _t13_combo(c: Ciclo) -> Optional[str]:
    righe = getattr(c.db, "trades", []) or []
    attivita = getattr(c.db, "attivita", None)
    if _modo_gamba_manuale(c.params) == "automatico":
        for g in _gambe_manuali_di_combo_incompleta(c):
            gid = int(g.get("id") or 0)
            for tr in righe:
                padre = tr.get("closes_trade_id")
                if padre is None or int(padre) != gid or str(tr.get("origin") or "") != "auto":
                    continue
                motivo = str((tr.get("meta") or {}).get("exit_reason") or "")
                if _AUDIT_AUTOMATICO not in motivo:
                    return (f"combo incompleta in 'automatico': la chiusura {tr.get('id')} "
                            f"della gamba MANUALE {gid} non dice che e' una scelta "
                            f"dell'utente (motivo: {motivo[:80]!r})")
        return None
    for g in _gambe_manuali_di_combo_incompleta(c):
        gid = int(g.get("id") or 0)
        # (d)/(e) proposta di copertura: una sola, e mai dopo un esito
        vive = _proposte_vive_di(c, gid)
        if vive is not None and vive > 1:
            return (f"gamba MANUALE {gid}: {vive} proposte di copertura vive: la "
                    f"proposta deve essere una sola")
        cop = ((g.get("meta") or {}).get(COMBO_LASCIATA_KEY) or {})
        cop = cop.get("copertura") if isinstance(cop, dict) else None
        if (isinstance(cop, dict) and cop.get("stato") not in (None, "proposta")
                and vive):
            return (f"gamba MANUALE {gid}: proposta di copertura gia' "
                    f"'{cop.get('stato')}', e ne e' viva un'altra: dopo un esito "
                    f"(rifiuto compreso) non se ne propone piu'")
        # (a) nessuna gamba di chiusura del bot sulla riga del trader
        for tr in righe:
            padre = tr.get("closes_trade_id")
            if padre is not None and int(padre) == gid and str(tr.get("origin") or "") == "auto":
                return (f"combo incompleta: il bot ha chiuso la gamba MANUALE {gid} "
                        f"con la gamba {tr.get('id')} (origin=auto): doveva lasciarla "
                        f"e avvisare (B25)")
        # (c) nessuna uscita del bot su quella riga in questo giro
        for kind, payload, _eid in (c.attivita_del_giro or []):
            tid = (payload or {}).get("trade_id")
            if str(kind) in _KIND_USCITA_DEL_BOT and tid is not None and int(tid) == gid:
                return (f"attivita' '{kind}' del bot sulla gamba MANUALE {gid} di una "
                        f"combo incompleta: la gamba e' del trader (B25)")
        # (b) marcatura e avviso, solo per una gamba ABBINATA (in coda non c'e'
        #     ancora niente da lasciare: l'avviso arriva al fill)
        if str(g.get("status") or "") != "open":
            continue
        if not isinstance((g.get("meta") or {}).get(COMBO_LASCIATA_KEY), dict):
            return (f"gamba MANUALE {gid} di una combo incompleta aperta a mercato "
                    f"senza la marcatura '{COMBO_LASCIATA_KEY}': il trader non e' "
                    f"stato avvisato")
        if attivita is None:
            continue                    # il doppio non tiene l'attivita': non si giudica
        avvisi = [p for k, p, _e in attivita
                  if str(k) == "combo_incomplete" and (p or {}).get("lasciata_al_trader")
                  and (p or {}).get("trade_id") is not None
                  and int((p or {}).get("trade_id")) == gid]
        if not avvisi:
            return (f"gamba MANUALE {gid} marcata ma NESSUNA riga di attivita' "
                    f"'combo_incomplete' con lasciata_al_trader: l'avviso non e' "
                    f"arrivato in Control Room")
        if len(avvisi) > 1 and all((p or {}).get("marcata", True) for p in avvisi):
            return (f"gamba MANUALE {gid}: {len(avvisi)} avvisi 'combo_incomplete' per "
                    f"la stessa riga gia' marcata: l'avviso deve essere uno solo")
    return None




# ---------------------------------------------------------------------------
# T14 — DOPO IL CASH-OUT GLOBALE DELL'UTENTE, IL BOT NON FA ALTRO
# ---------------------------------------------------------------------------
# Ordine dell'utente del 16/09 h18:20: «il bot gestisce le sue operazioni;
# UNICO CASO e' quando io chiudo manualmente TUTTE le operazioni (cash-out
# globale della partita): al successivo controllo lo capisce e NON FA ALTRO».
# Dal giro dopo la chiusura, su quella partita: nessuna apertura nuova, nessuna
# copertura, nessuna uscita, nessuna gamba di combo.
# stessa prudenza di T13: `cashout`/`place` li scrive anche il bottone del
# trader, e dopo un cash-out globale sono proprio le sue richieste a girare.
_KIND_OPERATIVI = ("exit", "exit_retry", "exit_hold")


def _dopo(iso: Any, quando: float) -> bool:
    """La riga e' nata DOPO l'istante dato (entrambi in tempo di mercato)."""
    from datetime import datetime

    try:
        return datetime.fromisoformat(str(iso)).timestamp() > float(quando) + 1e-9
    except (TypeError, ValueError):
        return False


@_controllo("T14", "Ordine dell'utente (16/09 h18:20): dopo il CASH-OUT GLOBALE "
                   "del trader il bot non apre ne' gestisce altro su quella partita",
            "chiuse a mano TUTTE le operazioni della partita, dal giro dopo il "
            "bot non deve aprire, coprire, uscire ne' piazzare gambe di combo",
            Ciclo, quando=lambda o: isinstance(o, Ciclo) and bool(o.chiuso_dall_utente))
def _t14(c: Ciclo) -> Optional[str]:
    for eid, quando in (c.chiuso_dall_utente or {}).items():
        for tr in getattr(c.db, "trades", []) or []:
            if str(tr.get("event_id")) != str(eid):
                continue
            if str(tr.get("origin") or "") != "auto":
                continue
            if _dopo(tr.get("placed_at"), quando):
                return (f"partita {eid} chiusa dall'utente, e il bot ha comunque "
                        f"aperto la riga {tr.get('id')} ({tr.get('strategy')} "
                        f"{tr.get('side')} sel {tr.get('selection_id')}) dopo la "
                        f"chiusura: doveva capirlo e non fare altro")
            # gamba di chiusura AUTOMATICA su un padre che il trader ha GIA'
            # chiuso: non dipende dalla precisione dell'orologio, e' il bot che
            # continua a gestire una posizione che l'utente aveva finito.
            padre = tr.get("closes_trade_id")
            if padre is None:
                continue
            gia_chiuso_dal_trader = any(
                str(x.get("origin") or "") == "manual"
                and x.get("closes_trade_id") is not None
                and int(x["closes_trade_id"]) == int(padre)
                for x in (getattr(c.db, "trades", []) or []))
            if gia_chiuso_dal_trader:
                return (f"partita {eid} chiusa dall'utente: la posizione {padre} "
                        f"era gia' stata chiusa a mano, e il bot ci ha aggiunto "
                        f"la gamba {tr.get('id')} (size {tr.get('size')}). "
                        f"Doveva capirlo e non fare altro.")
        for kind, payload, ev_att in (c.attivita_del_giro or []):
            if str(kind) not in _KIND_OPERATIVI:
                continue
            eid_att = str((payload or {}).get("event_id") or ev_att or "")
            if eid_att and eid_att != str(eid):
                continue
            return (f"partita {eid} chiusa dall'utente, e il bot ha comunque "
                    f"scritto l'attivita' operativa '{kind}' su di essa")
    return None


# ===========================================================================
# J. I DIFETTI DEL 15/09 (PROCESSO_STANDARD_BOT §7, punti 1-7)
#    e la CONSAPEVOLEZZA DELL'ORDINE (C.12a)
# ===========================================================================
@_controllo("J1", "Catalogo §7.1: chiave scritta in una grafia e letta in un'altra",
            "i numeri della riga vengono da Betfair (abbinato, prezzo medio), "
            "non dal chiesto",
            Ordine,
            quando=lambda o: (isinstance(o, Ordine)
                              and str(getattr(o.esito, "status", "")) == "open"
                              and o.stato_betfair is not None))
def _j1(o: Ordine) -> Optional[str]:
    st = o.stato_betfair or {}
    abbinato = _num(st.get("size_matched"))
    scritto = _num(o.riga.get("size"))
    if abbinato is None or scritto is None or abbinato <= 0:
        return None
    if abs(abbinato - scritto) > 0.011:
        return (f"Betfair dichiara abbinato {abbinato}, la riga porta {scritto}: "
                f"il numero letto non e' quello dell'exchange")
    return None


@_controllo("J2", "Catalogo §7.2: `res.ok` mai letto — un rifiuto trattato come "
                  "esecuzione",
            "un place senza abbinamento non produce MAI una riga 'open'",
            Ordine, quando=lambda o: isinstance(o, Ordine))
def _j2(o: Ordine) -> Optional[str]:
    stato = str(getattr(o.esito, "status", ""))
    abbinato = _num(getattr(o.esito, "size", None)) or 0.0
    if stato == "open" and abbinato <= 0:
        return (f"riga 'open' con abbinato {abbinato}: il rifiuto dell'exchange "
                f"e' stato letto come esecuzione ({getattr(o.esito, 'fill_note', None)})")
    return None


@_controllo("J3", "Catalogo §7.3: campo inesistente letto con getattr -> prezzo "
                  "medio uguale al chiesto",
            "il prezzo medio della riga e' quello dichiarato da Betfair",
            Ordine,
            quando=lambda o: (isinstance(o, Ordine)
                              and str(getattr(o.esito, "status", "")) == "open"
                              and o.stato_betfair is not None
                              and _num((o.stato_betfair or {}).get("avg_price_matched")) is not None))
def _j3(o: Ordine) -> Optional[str]:
    medio = _num((o.stato_betfair or {}).get("avg_price_matched"))
    scritto = _num(o.riga.get("price"))
    if medio is None or scritto is None:
        return None
    if abs(medio - scritto) > 1e-6:
        return (f"Betfair dichiara prezzo medio {medio}, la riga porta {scritto}")
    return None


@_controllo("J4", "Catalogo §7.4/§7.6 + C.12a: nessuna riga TERMINALE con un "
                  "ordine ancora VIVO su Betfair",
            "prima di un terminale l'ordine si annulla e si rilegge; il residuo "
            "vivo tiene la riga in riconciliazione",
            Ciclo, quando=lambda o: isinstance(o, Ciclo))
def _j4(c: Ciclo) -> Optional[str]:
    vivi = {str(r.get("bet_id")): r for r in
            (c.market.list_current_orders() or []) if r.get("bet_id")}
    if not vivi:
        return None
    for tr in c.db.trades:
        stato = str(tr.get("status") or "")
        bid = str(tr.get("bet_id") or "")
        if stato in ("error", "won", "lost", "void") and bid and bid in vivi:
            riga = vivi[bid]
            return (f"trade {tr.get('id')} in stato terminale '{stato}' ma "
                    f"l'ordine {bid} e' ancora EXECUTABLE su Betfair "
                    f"(residuo {riga.get('size_remaining')})")
    return None


@_controllo("J5", "Catalogo §7.5: `closes_trade_id` in COLONNA, non nel meta",
            "ogni gamba di chiusura porta il padre nella colonna che il DB indicizza",
            Ciclo, quando=lambda o: isinstance(o, Ciclo))
def _j5(c: Ciclo) -> Optional[str]:
    for tr in c.db.trades:
        meta = tr.get("meta") if isinstance(tr.get("meta"), dict) else {}
        if meta.get("closes_trade_id") and not tr.get("closes_trade_id"):
            return (f"trade {tr.get('id')}: il padre e' solo nel meta "
                    f"({meta.get('closes_trade_id')}), la colonna e' vuota")
    return None


@_controllo("J6", "Catalogo §7.7: `bet_id` salvato SOLO se abbinato",
            "quando Betfair restituisce un bet_id, la riga lo conserva sempre",
            Ordine,
            quando=lambda o: (isinstance(o, Ordine)
                              and getattr(o.esito, "bet_id", None) is not None))
def _j6(o: Ordine) -> Optional[str]:
    atteso = str(getattr(o.esito, "bet_id", "") or "")
    scritto = str(o.riga.get("bet_id") or "")
    if atteso and not scritto:
        return (f"Betfair ha dato bet_id {atteso} e la riga non lo porta: "
                f"al giro dopo l'ordine non si ritrova")
    return None


@_controllo("J7", "PROCESSO §6.4: mai due ordini vivi per lo stesso segnale",
            "l'idempotenza per (evento, signal_key) non lascia nascere doppioni",
            Ciclo, quando=lambda o: isinstance(o, Ciclo))
def _j7(c: Ciclo) -> Optional[str]:
    visti: Dict[Tuple[str, str, str], List[Any]] = {}
    for r in c.db.trades:
        if r.get("closes_trade_id") or str(r.get("status")) == "error":
            continue
        k = (str(r.get("event_id")), str(r.get("signal_key")), str(r.get("mode")))
        if not k[1] or k[1] == "None":
            continue
        visti.setdefault(k, []).append(r.get("id"))
    for k, ids in visti.items():
        if len(ids) > 1:
            return f"segnale {k} riservato {len(ids)} volte: {ids}"
    return None


# ===========================================================================
# il giro completo
# ===========================================================================
def verifica(oss: Osservazione, sollecitati: Optional[Dict[str, int]] = None,
             per_strategia: Optional[Dict[str, Dict[str, int]]] = None
             ) -> List[Violazione]:
    """Tutti i controlli che RIGUARDANO questa osservazione.

    Un controllo che solleva non ferma gli altri e non ferma la certificazione:
    diventa esso stesso un referto (`XX-ERRORE`), perche' un controllo rotto e'
    un'informazione, non un motivo per non sapere niente del resto.
    """
    out: List[Violazione] = []
    strategia = str(getattr(oss, "strategia", "") or "")
    minuto = None
    punteggio = None
    if isinstance(oss, Valutazione):
        minuto, punteggio = oss.ctx.minute, oss.punteggio
    elif isinstance(oss, Uscita):
        minuto = oss.tr.get("minute") if isinstance(oss.tr.get("minute"), int) else None
    for codice, _voce, regola, tipo, fn, quando in _REGISTRO:
        if not isinstance(oss, tipo):
            continue
        try:
            if quando is not None and not quando(oss):
                continue
            if sollecitati is not None:
                sollecitati[codice] = sollecitati.get(codice, 0) + 1
            if per_strategia is not None and strategia:
                per_strategia.setdefault(strategia, {})
                per_strategia[strategia][codice] = per_strategia[strategia].get(codice, 0) + 1
            det = fn(oss)
        except Exception as ex:  # noqa: BLE001
            out.append(Violazione(f"{codice}-ERRORE", regola,
                                  f"il controllo e' esploso: {type(ex).__name__}: {ex}",
                                  strategia, minuto, punteggio))
            continue
        if det:
            out.append(Violazione(codice, regola, det, strategia, minuto, punteggio))
    return out


# ===========================================================================
# K. LA CONSAPEVOLEZZA DELL'ORDINE, CONTRO IL MERCATO (16/09 sera)
#
# ⚠️ I controlli B/E/P/T/J qui sopra guardano la DECISIONE (valutazione, ordine
# chiesto, uscita, ciclo). I cinque difetti del 15/09 non stanno li': stanno nel
# rapporto fra cio' che le righe di `safe_strategy_trades` dicono e cio' che il
# banco dice degli ordini. La famiglia K guarda QUEL rapporto e vive nel modulo
# condiviso `certificazione_k.py`, identico per calcio e tennis (e' lo stesso
# `bot_service` e lo stesso `execution.place`). Qui si espone soltanto, perche'
# entri nella stessa copertura degli altri: un controllo che non si conta non
# esiste.
# ===========================================================================
VOCE_K = "PROCESSO §7.36"


def verifica_consapevolezza(righe: List[Dict[str, Any]],
                            ordini: Optional[Dict[str, Any]] = None,
                            rifiutati: Optional[Any] = None,
                            sollecitati: Optional[Dict[str, int]] = None,
                            per_strategia: Optional[Dict[str, Dict[str, int]]] = None
                            ) -> List[Violazione]:
    """I controlli K su UN giro, nella forma di `Violazione` del calcio.

    Il chiamante e' il replay (`tools/replay_registrazioni.py`), subito DOPO il
    giro del servizio: li' ci sono insieme le righe del database e gli ORDINI
    VERI di flumine.
    """
    prima = dict(sollecitati or {})
    esiti = K.verifica_consapevolezza(righe, ordini, rifiutati, sollecitati)
    if per_strategia is not None and sollecitati is not None:
        quadro = per_strategia.setdefault("trasversale", {})
        for codice, _r in K.REGISTRO:
            delta = int(sollecitati.get(codice, 0)) - int(prima.get(codice, 0))
            if delta:
                quadro[codice] = quadro.get(codice, 0) + delta
    return [Violazione(c, r, d, "trasversale") for c, r, d in esiti]


def elenco_controlli() -> List[Tuple[str, str]]:
    """(codice, regola) di tutto cio' che questa certificazione sa verificare.

    E' il contratto che `Betfair/stream/backtest/certifica.py` legge per
    stampare la copertura: una riga per controllo, la voce della SPEC in testa.
    Comprende la famiglia K, che non guarda una decisione ma il rapporto fra la
    memoria del bot e il mercato.
    """
    return ([(c, f"[{v}] {r}") for c, v, r, _t, _fn, _q in _REGISTRO]
            + [(c, f"[{VOCE_K}] {r}") for c, r in K.REGISTRO])


def voci_spec() -> List[Tuple[str, str, str, str]]:
    """(codice, strategia, voce della SPEC, regola) — la tabella del referto.

    La strategia si ricava dalla famiglia del codice: B = base, E = esatto,
    P = punta, T/J = trasversali.
    """
    fam = {"B": "base", "E": "esatto", "P": "punta", "T": "trasversale",
           "J": "trasversale", "K": "trasversale"}
    return ([(c, fam.get(c[0], "trasversale"), v, r)
             for c, v, r, _t, _fn, _q in _REGISTRO]
            + [(c, "trasversale", VOCE_K, r) for c, r in K.REGISTRO])


def mai_sollecitati(sollecitati: Dict[str, int]) -> List[Tuple[str, str]]:
    """I controlli che non hanno MAI avuto un caso da giudicare.

    Sono il buco vero di un referto: non dicono «il bot e' sano», dicono «non
    lo so». Vanno letti come lavoro da fare — uno scenario da provocare — non
    come una garanzia.
    """
    return ([(c, f"[{v}] {r}") for c, v, r, _t, _fn, _q in _REGISTRO
             if not sollecitati.get(c)]
            + [(c, f"[{VOCE_K}] {r}") for c, r in K.REGISTRO
               if not sollecitati.get(c)])


# ===========================================================================
# IL REFERTO
# ===========================================================================
@dataclass
class Referto:
    """L'esito su UNA partita. Contratto letto da `certifica.py`."""

    event_id: str
    tick: int = 0
    decisioni: int = 0
    azioni: int = 0
    stati_visti: List[str] = field(default_factory=list)
    motivi: Dict[str, int] = field(default_factory=dict)
    ordini_piazzati: int = 0
    righe_scritte: int = 0
    sollecitati: Dict[str, int] = field(default_factory=dict)
    violazioni: List[Violazione] = field(default_factory=list)
    note: List[str] = field(default_factory=list)

    # --- la parte SPECIFICA di Safe: una colonna per strategia --------------
    # quante volte OGNI strategia e' stata valutata: se una non compare, non e'
    # «sana», e' MUTA — ed e' un reperto da spiegare, non un silenzio.
    valutazioni: Dict[str, int] = field(default_factory=dict)
    # stato aggregato delle valutazioni: signal / nd / no
    stati_valutazione: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # PERCHE' e' stata scartata: id del check -> quante volte l'ha fatta cadere
    scarti: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # copertura per strategia: strategia -> codice -> sollecitazioni
    sollecitati_per_strategia: Dict[str, Dict[str, int]] = field(default_factory=dict)
    segnali: Dict[str, int] = field(default_factory=dict)

    @property
    def pulita(self) -> bool:
        return not self.violazioni

    def per_codice(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for v in self.violazioni:
            out[v.codice] = out.get(v.codice, 0) + 1
        return out

    def violazioni_per_strategia(self) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {}
        for v in self.violazioni:
            s = v.strategia or "trasversale"
            out.setdefault(s, {})
            out[s][v.codice] = out[s].get(v.codice, 0) + 1
        return out


def osserva_valutazione(ref: Referto, v: Valutazione) -> None:
    """Registra CHE COSA ha deciso il motore su quella variante, e perche'.

    «Scartata per X» e' una prova; il silenzio no. Qui si conta lo stato della
    valutazione e, quando non e' un segnale, l'id di OGNI check che l'ha fatta
    cadere: e' il documento che dice se una strategia e' stata davvero valutata.
    """
    s = v.strategia
    ref.valutazioni[s] = ref.valutazioni.get(s, 0) + 1
    stato = str(v.ev.state)
    ref.stati_valutazione.setdefault(s, {})
    ref.stati_valutazione[s][stato] = ref.stati_valutazione[s].get(stato, 0) + 1
    if stato == "signal":
        ref.segnali[s] = ref.segnali.get(s, 0) + 1
        return
    ref.scarti.setdefault(s, {})
    for c in (v.ev.checks or ()):
        if c.ok is False:
            k = f"{c.id}:no"
        elif c.ok is None:
            k = f"{c.id}:nd"
        else:
            continue
        ref.scarti[s][k] = ref.scarti[s].get(k, 0) + 1


def tabella_per_strategia(ref: Referto) -> List[str]:
    """La tabella del referto: voce spec | controllo | sollecitato | violazioni.

    Una riga per controllo e per strategia, senza omissioni: chi non e' stato
    sollecitato compare con «non lo so», non sparisce.
    """
    viol = ref.violazioni_per_strategia()
    righe: List[str] = []
    for strategia in list(STRATEGIE_CALCIO) + ["trasversale"]:
        sol = ref.sollecitati_per_strategia.get(strategia, {})
        righe.append(f"--- {strategia.upper()} ---")
        for cod, fam, voce, _regola in voci_spec():
            if fam != strategia:
                continue
            # un controllo di CICLO (E7, J4, J5, J7...) non ha una strategia
            # nell'osservazione: il suo conteggio e' quello globale.
            n = int(sol.get(cod, 0) or ref.sollecitati.get(cod, 0))
            nv = int((viol.get(strategia) or {}).get(cod, 0))
            verdetto = ("VIOLATO" if nv else ("conforme" if n else "non lo so"))
            righe.append(f"  {cod:4} {voce[:74]:<74} x{n:<6} viol={nv:<3} {verdetto}")
    return righe
