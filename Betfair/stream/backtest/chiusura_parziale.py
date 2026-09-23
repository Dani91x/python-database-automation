"""LO SCENARIO «chiusura-abbinata-in-parte» — il guasto e i controlli, COMUNI.

Cancello C3 del 18/09 (`CRONOSTORIA.md`): «aggiungere al banco lo scenario
"chiusura abbinata in parte" (oggi non esiste) e falsificarlo». Il fix del 18/09
(`safe_strategy.execution.hedge_state` / `chiusura_abbinata`) conta la copertura
sull'ABBINATO della chiusura e non sul CHIESTO; nessun replay lo aveva mai messo
alla prova, perche' sulle registrazioni una chiusura abbinata in parte non capita
da sola.

IL GUASTO (uno solo, dichiarato, e non tocca ne' la partita ne' la strategia).
La PRIMA gamba di CHIUSURA che un bot piazza su una selezione (green-up,
copertura, uscita, cash-out) trova il mercato SOTTILE: al piu' il 40 % della sua
size puo' essere abbinato. Da li' in poi il mercato torna quello registrato.
Non e' un fill scritto a mano: l'abbinamento resta di flumine (prezzi, istanti,
coda); il guasto TOGLIE liquidita', non ne aggiunge.

  * ordine NON fill-or-kill (appoggiato, `persistenceType` LAPSE): flumine abbina
    come sempre, ma l'abbinato complessivo di QUELL'ordine non supera il tetto
    (`SimulatedOrder._update_matched` avvolto): il 40 % si abbina, il 60 % resta
    VIVO a mercato e muore come muore su Betfair (sospensione, fischio, annullo
    del bot, chiusura del mercato). E' la «chiusura abbinata in parte, residuo a
    mercato».
  * ordine FILL_OR_KILL SENZA `minFillSize` (e' l'istruzione di produzione di
    `omega_market.place_order_live`): per Betfair un FOK senza `minFillSize` si
    abbina PER INTERO O PER NIENTE, e flumine fa lo stesso
    (`simulatedorder.py:118`, `min_fill_size = ... or size`). Con il libro
    assottigliato al 40 % la sola conseguenza FEDELE e' la chiusura UCCISA
    (abbinato 0 su chiesto): un abbinamento parziale di un FOK sarebbe un fill
    che Betfair non darebbe mai, cioe' il difetto 8 del catalogo. Il libro
    assottigliato si passa SOLO a quell'ordine (`SimulatedOrder.place` avvolto),
    tutti gli altri vedono il libro registrato.

CHE COS'E' UNA CHIUSURA. Se il replay sa dire il RUOLO dell'ordine (riga del bot
con `closes_trade_id`, credenza del bot tennis), si usa quello; altrimenti la si
riconosce dal mercato: un ordine che RIDUCE l'esposizione netta del bot su quella
selezione (vincita-se-vince meno vincita-se-perde, sugli ordini ABBINATI).

I CONTROLLI (famiglia CP, citati nel referto; regole qui sotto in `_REGOLE`):
  CP1  consapevolezza della chiusura colpita: la riga/credenza del bot porta
       abbinato, residuo e prezzo medio VERI (quelli di flumine);
  CP2  la copertura dichiarata (``meta.hedged_size`` scritto da
       ``apply_hedge_state``) e' calcolata sull'ABBINATO, mai sul chiesto;
  CP3  una posizione con esposizione residua (o con il residuo della chiusura
       ancora vivo a mercato) non e' mai dichiarata CHIUSA;
  CP4  nessun loop di ripiazzamenti: mai una chiusura nuova mentre un'altra e'
       ancora viva sulla stessa selezione, mai una size che chiede di chiudere
       piu' di quanto resta (sul CHIESTO invece che sull'abbinato), al piu'
       `TETTO_RIPIAZZAMENTI` chiusure dopo quella colpita, mai una
       sovracopertura (la posizione ribaltata dalle chiusure).
I controlli che confrontano la CREDENZA del bot col mercato (CP1-CP3) scattano
solo se la discrepanza DURA `GIRI_DI_TOLLERANZA` giri di fila: fra un
abbinamento e il giro dopo il bot non puo' saperlo, e accusarlo di quello sarebbe
il falso positivo del controllo (catalogo §7.16).

LIMITI DICHIARATI
  * I pacchetti REPLACE di flumine (sostituzione di prezzo in un colpo) creano
    l'ordine nuovo DENTRO `execute_replace`: quell'ordine non passa di qui. Nessun
    bot certificato oggi usa il replace di flumine (Mike, Omega e Safe annullano
    e ripiazzano via REST; i quattro bot tennis piazzano e annullano).
  * Il percorso della CODA (worker ordini con place-and-trim, dove in produzione
    un FOK puo' chiudersi in parte) non e' nel banco: il banco serve la REST.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import math
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

SCENARIO = "chiusura-abbinata-in-parte"

DESCRIZIONE = (
    "la PRIMA chiusura (green-up/copertura/uscita/cash-out) su ogni selezione "
    "trova il mercato sottile: al piu' il 40 % si abbina. Appoggiata: 40 % "
    "abbinato e residuo VIVO a mercato; FOK senza minFillSize: uccisa per intero "
    "(per Betfair un FOK e' tutto o niente). Il bot deve contare la copertura "
    "sull'ABBINATO, non dichiarare chiusa una posizione con residuo, non "
    "ripiazzare in loop (CP1-CP4)")

# quanto della size della chiusura colpita il mercato riesce ad abbinare
FRAZIONE = 0.40
# quante chiusure sono ammesse sulla stessa selezione DOPO quella colpita, prima
# che si parli di loop solo per il NUMERO. Il loop che fa danno (una chiusura
# nuova sopra una viva, una size chiesta sul chiesto invece che sull'abbinato,
# la posizione ribaltata) ha i suoi tre controlli dedicati qui sotto; il tetto
# numerico serve per il loop «a vuoto» che non abbina mai. Prima taratura (3)
# FALSIFICATA dal banco il 23/09: Mike su 35760084 fa, IDENTICO nello scenario
# `base` senza guasto, 4 tentativi FOK dell'uscita in perdita che inseguono il
# prezzo tick per tick (8,8 -> 9,0 -> 9,4 -> 9,6), tutti uccisi senza
# abbinare: un inseguimento onesto, non un loop. Il loop vero del 15/09 ne ha
# piazzati 32. Dieci stanno fra i due con margine da entrambe le parti.
TETTO_RIPIAZZAMENTI = 10
# quanti giri di fila deve durare una discrepanza credenza/mercato per essere
# una violazione (vedi testa del modulo)
GIRI_DI_TOLLERANZA = 3
# Betfair lavora al centesimo: sotto e' arrotondamento
EPS = 0.011

_REGOLE: Tuple[Tuple[str, str], ...] = (
    ("CP1", "chiusura abbinata in parte: la riga (o la credenza) del bot porta "
            "l'abbinato VERO della chiusura - chiesto, abbinato, residuo e prezzo "
            "medio come a mercato (PROCESSO par.6.4 parziali, par.6.5)"),
    ("CP2", "la copertura dichiarata (hedge_state, meta.hedged_size) si conta "
            "sull'ABBINATO della chiusura, mai sul chiesto (fix del 18/09)"),
    ("CP3", "una posizione con esposizione residua o con il residuo della "
            "chiusura ancora vivo a mercato non e' mai dichiarata CHIUSA"),
    ("CP4", "dopo una chiusura abbinata in parte nessun loop: mai una chiusura "
            "nuova con un'altra viva sulla stessa selezione, mai una size che chiede "
            "piu' di quanto resta da chiudere, al piu' %d chiusure dopo, mai "
            "sovracopertura (catalogo par.7.1: 32 ordini veri in loop il 15/09)"
            % TETTO_RIPIAZZAMENTI),
)


def elenco_controlli() -> List[Tuple[str, str]]:
    """(codice, regola) dei controlli dello scenario: il contratto della copertura."""
    return list(_REGOLE)


def regola(codice: str) -> str:
    return dict(_REGOLE).get(str(codice), "")


# ---------------------------------------------------------------------------
# leggere un ordine di flumine SEMPRE nello stesso modo
# ---------------------------------------------------------------------------
def _f(v: Any) -> Optional[float]:
    """float FINITO oppure None (mai nan/inf, mai bool)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def lato(ordine: Any) -> str:
    return str(getattr(ordine, "side", "") or "").upper()


def abbinato(ordine: Any) -> float:
    return float(_f(getattr(ordine, "size_matched", None)) or 0.0)


def prezzo_medio(ordine: Any) -> Optional[float]:
    p = _f(getattr(ordine, "average_price_matched", None))
    return p if p and p > 1.0 else None


def residuo(ordine: Any) -> float:
    return float(_f(getattr(ordine, "size_remaining", None)) or 0.0)


def chiesto(ordine: Any) -> Optional[float]:
    """Il CHIESTO dell'ordine per flumine (``order_type.size``), None se ignoto."""
    return _f(getattr(getattr(ordine, "order_type", None), "size", None))


def _chiesto_non_coerente(creduto: Optional[float], ordine: Any,
                          m: float, rem: float) -> Optional[str]:
    """23/09 (B-3): il chiesto scritto dal bot contro quello di flumine.

    Accettati: ``order_type.size`` (il chiesto piazzato) OPPURE abbinato +
    residuo (il chiesto dopo le riduzioni: il place-and-trim piazza al minimo
    di Betfair e taglia al centesimo, quindi ``order_type.size`` resta il
    piazzato mentre la riga porta il chiesto vero). Non scritto con abbinato o
    residuo a mercato = violazione (assente NON e' zero, catalogo par.7.21)."""
    if creduto is None:
        if m > EPS or rem > EPS:
            return f"chiesto NON scritto (abbinato {m:.2f}, residuo {rem:.2f})"
        return None
    piazzato = chiesto(ordine)
    candidati = [x for x in (piazzato, m + rem if (m > EPS or rem > EPS) else None)
                 if x is not None]
    if not candidati:
        return None
    if all(abs(creduto - x) > EPS for x in candidati):
        vero = piazzato if piazzato is not None else m + rem
        return f"chiesto creduto {creduto:.2f} contro {vero:.2f} di flumine"
    return None


def vivo(ordine: Any) -> bool:
    """Vivo a mercato: stato (letto come `.value`, catalogo §7.10) fra quelli
    che su Betfair tengono un residuo, e un residuo che c'e'."""
    st = getattr(ordine, "status", None)
    parola = str(getattr(st, "value", st) or "")
    return parola in ("Pending", "Executable", "Cancelling", "Updating",
                      "Replacing") and residuo(ordine) > EPS


def e_dell_utente(ordine: Any) -> bool:
    """Gli ordini dell'UTENTE (`MercatoFlumine.place_order_utente`) non sono del
    bot: non si colpiscono e non contano nella sua posizione."""
    note = getattr(ordine, "notes", None) or {}
    return bool(note.get("utente"))


def esposizione(ordini: Sequence[Any]) -> Tuple[float, float]:
    """(se vince, se perde) degli ordini ABBINATI, lordo di commissione."""
    win = lose = 0.0
    for o in ordini:
        m = abbinato(o)
        p = prezzo_medio(o)
        if m <= 0 or p is None:
            continue
        if lato(o) == "BACK":
            win += m * (p - 1.0)
            lose -= m
        else:
            win -= m * (p - 1.0)
            lose += m
    return win, lose


def direzione(ordini: Sequence[Any]) -> float:
    """> 0 la posizione guadagna se la selezione vince (back netto), < 0 il
    contrario (lay netto), ~0 piatta."""
    w, lo = esposizione(ordini)
    return w - lo


def tolleranza(ordini: Sequence[Any], stake_extra: float = 0.0) -> float:
    """La soglia di «piatto», in soldi: un centesimo di stake (piu' la
    tolleranza che il bot DICHIARA, se ne dichiara una) al prezzo piu' alto fra
    gli ordini della posizione, piu' 5 centesimi. E' l'errore di arrotondamento
    di un green-up al centesimo, non una soglia scelta per far passare."""
    pmax = 1.0
    for o in ordini:
        for p in (prezzo_medio(o), _f(getattr(getattr(o, "order_type", None), "price", None))):
            if p and p > pmax:
                pmax = p
    return 0.05 + (0.01 + max(0.0, float(stake_extra or 0.0))) * pmax


# ---------------------------------------------------------------------------
# il libro assottigliato, solo per l'ordine colpito (FOK)
# ---------------------------------------------------------------------------
class _Vista:
    """Un oggetto di flumine visto com'e', con qualche attributo sostituito."""

    def __init__(self, vero: Any, **sostituti: Any) -> None:
        object.__setattr__(self, "_vero", vero)
        for k, v in sostituti.items():
            object.__setattr__(self, k, v)

    def __getattr__(self, nome: str) -> Any:
        return getattr(object.__getattribute__(self, "_vero"), nome)


def _assottiglia(livelli: Any, tetto: float) -> List[Dict[str, float]]:
    """I livelli del libro troncati a `tetto` di size cumulata (i livelli in
    simulazione sono dict `{"price", "size"}`, catalogo §7.9)."""
    out: List[Dict[str, float]] = []
    resto = round(float(tetto), 2)
    for lv in list(livelli or []):
        if resto <= 0:
            break
        try:
            prezzo = float(lv["price"])
            size = float(lv["size"])
        except (KeyError, TypeError, ValueError):
            continue
        s = round(min(size, resto), 2)
        if s <= 0:
            continue
        out.append({"price": prezzo, "size": s})
        resto = round(resto - s, 2)
    return out


def libro_assottigliato(market_book: Any, selection_id: int, handicap: float,
                        lato_ordine: str, tetto: float) -> Any:
    """Il MarketBook come lo vedrebbe l'ordine colpito: sul lato con cui si
    abbina (BACK contro `available_to_back`, LAY contro `available_to_lay`)
    c'e' al piu' `tetto` di size. Tutto il resto e' il libro registrato."""
    runners = []
    for r in list(getattr(market_book, "runners", []) or []):
        if (int(getattr(r, "selection_id", -1)) == int(selection_id)
                and float(getattr(r, "handicap", 0.0) or 0.0) == float(handicap or 0.0)):
            ex = r.ex
            if lato_ordine == "BACK":
                ex2 = _Vista(ex, available_to_back=_assottiglia(ex.available_to_back, tetto))
            else:
                ex2 = _Vista(ex, available_to_lay=_assottiglia(ex.available_to_lay, tetto))
            runners.append(_Vista(r, ex=ex2))
        else:
            runners.append(r)
    return _Vista(market_book, runners=runners)


def _tetto(size: float, frazione: float) -> float:
    return max(0.01, math.floor(float(size) * float(frazione) * 100.0 + 1e-9) / 100.0)


def _e_fok(instruction: Any) -> bool:
    try:
        lim = (instruction or {}).get("limitOrder") or {}
        return str(lim.get("timeInForce") or "") == "FILL_OR_KILL" and not lim.get("minFillSize")
    except AttributeError:
        return False


_RE_ID_RIGA = re.compile(r"-[tm](\d+)$")


def ruolo_da_righe(righe: Callable[[], Sequence[Dict[str, Any]]]) -> Callable[[Any], Optional[str]]:
    """Il RUOLO di un ordine letto dalla riga del bot che lo ha chiesto.

    Il ref con cui i bot calcio piazzano e' `<bot>-t<id riga>` (Safe
    `safe-t<id>`, Omega `omega-t<id>`, Mike `mike-t<id>`; manuale Omega
    `omega-m<id>`): dalla riga si legge `closes_trade_id` (o il `meta` di
    chiusura). Ref illeggibile o riga assente = None, e il guasto ripiega sul
    mercato. Nessuna chiave inventata: sono le colonne di `safe_strategy_trades`
    / `omega_trades` / `mike_trades`.
    """
    def _ruolo(ordine: Any) -> Optional[str]:
        note = getattr(ordine, "notes", None) or {}
        ref = str(note.get("bot_ref") or getattr(ordine, "customer_order_ref", "") or "")
        m = _RE_ID_RIGA.search(ref)
        if not m:
            return None
        rid = int(m.group(1))
        for r in list(righe() or []):
            try:
                if int(r.get("id")) != rid:
                    continue
            except (TypeError, ValueError):
                continue
            meta = r.get("meta") or {}
            if r.get("closes_trade_id") or meta.get("closes_trade_id") or meta.get("cashout"):
                return "uscita"
            return "ingresso"
        return None
    return _ruolo


# ---------------------------------------------------------------------------
# IL GUASTO
# ---------------------------------------------------------------------------
class GuastoChiusuraParziale:
    """Colpisce la PRIMA chiusura di ogni selezione e sorveglia le successive.

    Si aggancia a `MotoreReplay.guasto_chiusure`: il motore gli passa i
    pacchetti PRIMA di eseguirli (`prepara`), e lui avvolge il `place` simulato
    di ogni ordine. La decisione (colpire, contare, violare CP4) si prende
    all'ESECUZIONE, cioe' quando Betfair (dopo latenza e bet delay) vedrebbe
    l'ordine, con la posizione del bot di QUELL'istante.
    """

    def __init__(self, *, frazione: float = FRAZIONE,
                 tetto_ripiazzamenti: int = TETTO_RIPIAZZAMENTI,
                 ruolo: Optional[Callable[[Any], Optional[str]]] = None) -> None:
        self.frazione = float(frazione)
        self.tetto_ripiazzamenti = int(tetto_ripiazzamenti)
        self.ruolo = ruolo
        self.quadro: Any = None
        self.colpiti: List[Dict[str, Any]] = []
        # (market_id, selection_id) -> sorveglianza CP4
        self.per_chiave: Dict[Tuple[str, int], Dict[str, Any]] = {}
        self._avvolti: set = set()
        # violazioni CP4 nate all'esecuzione, in attesa di essere consegnate
        self._da_consegnare: List[Tuple[str, str]] = []
        self.sollecitati: Dict[str, int] = {}
        self.chiusure_viste = 0

    # ------------------------------------------------------------ aggancio
    def prepara(self, quadro: Any, pacchi: Sequence[Any]) -> None:
        from flumine.order.orderpackage import OrderPackageType

        self.quadro = quadro
        for pacco in list(pacchi or []):
            if getattr(pacco, "package_type", None) != OrderPackageType.PLACE:
                continue
            for ordine in list(pacco):
                chiave = str(getattr(ordine, "id", "") or id(ordine))
                if chiave in self._avvolti:
                    continue
                sim = getattr(ordine, "simulated", None)
                if sim is None:
                    continue
                self._avvolti.add(chiave)
                self._avvolgi(ordine, sim)

    def _avvolgi(self, ordine: Any, sim: Any) -> None:
        originale = sim.place
        guasto = self

        def _place(order_package: Any, market_book: Any, instruction: Any,
                   bet_id: Any) -> Any:
            libro = guasto._al_piazzamento(ordine, sim, market_book, instruction)
            return originale(order_package, libro, instruction, bet_id)

        sim.place = _place

    # ------------------------------------------------------------ mercato
    def _mercato(self, market_id: str) -> Any:
        mercati = getattr(getattr(self.quadro, "markets", None), "markets", None) or {}
        return mercati.get(str(market_id))

    def ordini_del_bot(self, market_id: str, selection_id: int,
                       escludi: Any = None) -> List[Any]:
        m = self._mercato(market_id)
        if m is None:
            return []
        out = []
        for o in list(getattr(m, "blotter", None) or []):
            if o is escludi or e_dell_utente(o):
                continue
            try:
                if int(getattr(o, "selection_id", -1)) != int(selection_id):
                    continue
            except (TypeError, ValueError):
                continue
            out.append(o)
        return out

    def tutti_gli_ordini(self) -> List[Any]:
        mercati = getattr(getattr(self.quadro, "markets", None), "markets", None) or {}
        out: List[Any] = []
        for m in list(mercati.values()):
            out.extend(o for o in list(getattr(m, "blotter", None) or [])
                       if not e_dell_utente(o))
        return out

    def mercato_chiuso(self, market_id: str) -> bool:
        m = self._mercato(market_id)
        if m is None:
            return True
        if getattr(m, "closed", False):
            return True
        mb = getattr(m, "market_book", None)
        return str(getattr(mb, "status", "") or "") == "CLOSED"

    # ------------------------------------------------------ all'esecuzione
    def _ruolo_di(self, ordine: Any) -> Optional[str]:
        if self.ruolo is None:
            return None
        try:
            r = self.ruolo(ordine)
        except Exception:  # noqa: BLE001 - un ruolo illeggibile ripiega sul mercato
            return None
        return r if r in ("ingresso", "uscita") else None

    def _al_piazzamento(self, ordine: Any, sim: Any, market_book: Any,
                        instruction: Any) -> Any:
        if e_dell_utente(ordine):
            return market_book
        mid = str(getattr(ordine, "market_id", ""))
        try:
            sel = int(getattr(ordine, "selection_id", 0))
        except (TypeError, ValueError):
            return market_book
        chiave = (mid, sel)
        altri = self.ordini_del_bot(mid, sel, escludi=ordine)
        d = direzione(altri)
        tol = tolleranza(altri + [ordine])
        la = lato(ordine)
        riduce = (la == "BACK" and d < -tol) or (la == "LAY" and d > tol)
        ruolo = self._ruolo_di(ordine)
        chiude = (ruolo == "uscita") if ruolo is not None else riduce
        st = self.per_chiave.get(chiave)

        if not chiude:
            if st is not None and not st["nuovo_ciclo"]:
                # un'APERTURA dopo la chiusura colpita: comincia un ciclo nuovo,
                # la sorveglianza CP4 di questa selezione si ferma qui
                st["nuovo_ciclo"] = True
            return market_book

        self.chiusure_viste += 1
        if (st is not None and not st["nuovo_ciclo"] and not st["fok"]
                and abbinato(st["colpito"]) <= 0 and not vivo(st["colpito"])):
            # LA CHIUSURA COLPITA NON HA MAI TOCCATO IL MERCATO: era appoggiata
            # lontano dal prezzo e il bot l'ha annullata (o e' scaduta) senza un
            # solo abbinamento. Il guasto non ha avuto effetto — e' come se non
            # fosse mai scattato — quindi si RIARMA sulla chiusura successiva
            # della stessa selezione. Il record resta nel referto, marcato.
            for rec in self.colpiti:
                if rec["ordine"] is st["colpito"]:
                    rec["senza_effetto"] = True
            self.per_chiave.pop(chiave, None)
            st = None
        if st is None:
            if abs(d) <= tol:
                # una «chiusura» su una posizione piatta prima di ogni guasto: non
                # c'e' niente da chiudere, non si colpisce (e non e' affare di CP)
                return market_book
            size = float(getattr(getattr(ordine, "order_type", None), "size", 0.0) or 0.0)
            tetto = _tetto(size, self.frazione)
            fok = _e_fok(instruction)
            pt = getattr(market_book, "publish_time", None)
            rec = {"ordine": ordine, "chiave": chiave, "lato": la, "chiesto": size,
                   "prezzo": _f(getattr(getattr(ordine, "order_type", None), "price", None)),
                   "tetto": tetto, "fok": fok, "segno": 1.0 if d > 0 else -1.0,
                   "quando": pt.isoformat() if pt is not None else ""}
            self.colpiti.append(rec)
            self.per_chiave[chiave] = {"colpito": ordine, "dopo": 0, "fok": fok,
                                       "nuovo_ciclo": False, "segno": rec["segno"],
                                       "emesse": set()}
            if fok:
                return libro_assottigliato(market_book, sel,
                                           float(getattr(ordine, "handicap", 0.0) or 0.0),
                                           la, tetto)
            self._tetta_abbinato(sim, tetto)
            return market_book

        if st["nuovo_ciclo"]:
            return market_book
        # CP4: una chiusura DOPO quella colpita, sulla stessa selezione
        self.sollecitati["CP4"] = self.sollecitati.get("CP4", 0) + 1
        st["dopo"] += 1
        ref = self._ref(ordine)
        vive = [o for o in altri if lato(o) == la and vivo(o)]
        if vive:
            self._cp4(st, "viva", (
                f"{chiave}: nuova chiusura {la} {ref} da "
                f"{float(getattr(ordine.order_type, 'size', 0.0) or 0.0):.2f} piazzata "
                f"mentre {len(vive)} chiusura/e sulla stessa selezione e' ancora VIVA "
                f"(residuo {sum(residuo(o) for o in vive):.2f}): rischio sovracopertura"))
        # SOVRA-RICHIESTA: quanto questa chiusura (piu' il residuo delle chiusure
        # ancora vive dallo stesso lato) sposterebbe il netto, se si abbinasse
        # tutta, contro quanto netto c'e' davvero da chiudere. Una lay s@p sposta
        # il netto di s*p (una back di altrettanto): e' la formula del green-up
        # (S*p0 = s*p). Chiedere la size INTERA dopo un parziale e' il loop del
        # 15/09 (32 green-up), anche se oggi l'ordine si uccide da solo.
        # Vale anche su una posizione GIA' PIATTA (da chiudere resta ~0): e' la
        # stessa regola, e non accusa la «polvere» — la chiusura da un
        # centesimo di stake che uno scalper manda per un residuo sotto il
        # centesimo (misurato 23/09 su tennis_scalper 35794049: prima taratura
        # con una regola «piatta» separata, falso positivo del controllo).
        prezzo_o = _f(getattr(getattr(ordine, "order_type", None), "price", None)) or 0.0
        size_o = float(getattr(getattr(ordine, "order_type", None), "size", 0.0) or 0.0)
        capacita = size_o * prezzo_o + sum(residuo(o) * float(
            _f(getattr(getattr(o, "order_type", None), "price", None)) or 0.0) for o in vive)
        if capacita > abs(d) * 1.02 + tol:
            self._cp4(st, "sovrarichiesta", (
                f"{chiave}: chiusura {la} {ref} chiede di spostare il netto di "
                f"{capacita:.2f} (compreso il residuo vivo) quando da chiudere ne "
                f"resta {abs(d):.2f}{' (posizione GIA PIATTA)' if not riduce else ''}: "
                f"size calcolata sul CHIESTO, non sull'abbinato"))
        if st["dopo"] > self.tetto_ripiazzamenti:
            self._cp4(st, "tetto", (
                f"{chiave}: {st['dopo']} chiusure dopo quella abbinata in parte "
                f"(tetto {self.tetto_ripiazzamenti}): loop di ripiazzamenti"))
        return market_book

    @staticmethod
    def _tetta_abbinato(sim: Any, tetto: float) -> None:
        """L'abbinato complessivo di QUESTO ordine non supera `tetto`: flumine
        abbina come sempre (stessi prezzi, stessi istanti, stessa coda), e
        quello che eccede il tetto non viene abbinato. Il residuo resta VIVO."""
        originale = sim._update_matched

        def _upd(dati: List[Any]) -> None:
            gia = float(getattr(sim, "size_matched", 0.0) or 0.0)
            resto = round(float(tetto) - gia, 2)
            if resto <= 0:
                return
            if float(dati[2]) > resto:
                dati = [dati[0], dati[1], resto]
            originale(dati)

        sim._update_matched = _upd

    @staticmethod
    def _ref(ordine: Any) -> str:
        note = getattr(ordine, "notes", None) or {}
        return str(note.get("bot_ref") or getattr(ordine, "bet_id", None)
                   or getattr(ordine, "id", ""))

    def _cp4(self, st: Dict[str, Any], tipo: str, dettaglio: str) -> None:
        if tipo in st["emesse"]:
            return
        st["emesse"].add(tipo)
        self._da_consegnare.append(("CP4", dettaglio))

    # ---------------------------------------------------------- riepilogo
    def riepilogo(self) -> str:
        if not self.colpiti:
            return (f"scenario {SCENARIO}: NESSUNA chiusura colpita (il bot non ha "
                    f"mai chiuso una posizione su questa partita: CP1-CP4 \"non lo so\")")
        parti = []
        for c in self.colpiti:
            o = c["ordine"]
            parti.append(
                f"{c['chiave'][1]} {c['lato']} chiesto {c['chiesto']:.2f} tetto "
                f"{c['tetto']:.2f} -> abbinato {abbinato(o):.2f} residuo "
                f"{residuo(o):.2f} lapsed {float(getattr(o, 'size_lapsed', 0.0) or 0.0):.2f} "
                f"annullato {float(getattr(o, 'size_cancelled', 0.0) or 0.0):.2f}"
                f"{' (FOK: tutto o niente)' if c['fok'] else ''}"
                f"{' [SENZA EFFETTO: mai abbinata, guasto riarmato]' if c.get('senza_effetto') else ''}")
        return (f"scenario {SCENARIO}: {len(self.colpiti)} chiusura/e colpita/e, "
                f"{self.chiusure_viste} chiusure viste: " + "; ".join(parti))


# ---------------------------------------------------------------------------
# I CONTROLLI SULLA CREDENZA DEL BOT
# ---------------------------------------------------------------------------
def credenze_da_righe(righe: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Le posizioni che il bot CREDE di avere, lette dalle sue righe.

    Vale per chi scrive le righe con lo schema di `safe_strategy_trades` /
    `omega_trades` (colonne del 16/09: `size_matched`, `size_remaining`,
    `avg_price_matched`, `bet_id`, `closes_trade_id`) e copre la posizione con
    `execution.apply_hedge_state` (apertura 'hedged' = CHIUSA, `meta.hedged_size`
    = copertura dichiarata). Una posizione per apertura.
    """
    righe = list(righe or [])
    out: List[Dict[str, Any]] = []
    for r in righe:
        meta = r.get("meta") or {}
        if r.get("closes_trade_id") or meta.get("closes_trade_id") or meta.get("cashout"):
            continue
        rid = r.get("id")
        chiusure = [c for c in righe
                    if c.get("closes_trade_id") is not None
                    and str(c.get("closes_trade_id")) == str(rid)]
        try:
            chiave = (str(r.get("market_id") or ""), int(r.get("selection_id") or 0))
        except (TypeError, ValueError):
            continue
        out.append({
            "id": f"riga#{rid}",
            "chiave": chiave,
            "chiusa": str(r.get("status") or "") == "hedged",
            "coperto": _f(meta.get("hedged_size")),
            "apertura": {"size": _f(r.get("size")), "price": _f(r.get("price"))},
            "ingressi": [{"bet_id": r.get("bet_id")}],
            "chiusure": [{"bet_id": c.get("bet_id"), "id_riga": c.get("id"),
                          "status": c.get("status"),
                          "size": _f(c.get("size")), "price": _f(c.get("price")),
                          "size_requested": _f(c.get("size_requested")),
                          "size_matched": _f(c.get("size_matched")),
                          "size_remaining": _f(c.get("size_remaining")),
                          "avg_price_matched": _f(c.get("avg_price_matched"))}
                         for c in chiusure],
            "per_selezione": False,
            "tolleranza": 0.0,
        })
    return out


class Sorveglianza:
    """CP1-CP4 a ogni giro del bot, con la regola dei giri di tolleranza.

    `verifica(credute, sollecitati)` torna `[(codice, regola, dettaglio)]`:
    ogni replay lo trasforma nella SUA `Violazione` (stesse prime tre chiavi in
    tutti i moduli di certificazione). Ogni violazione esce UNA volta per
    oggetto (chiusura o posizione): un difetto che dura cento giri non deve
    diventare cento righe.
    """

    def __init__(self, guasto: GuastoChiusuraParziale,
                 giri: int = GIRI_DI_TOLLERANZA) -> None:
        self.g = guasto
        self.giri = int(giri)
        self._conta: Dict[Tuple[str, str], int] = {}
        self._emesse: set = set()

    # ------------------------------------------------------------ utilita'
    def _persiste(self, codice: str, oggetto: str, problema: Optional[str],
                  out: List[Tuple[str, str, str]]) -> None:
        k = (codice, oggetto)
        if not problema:
            self._conta[k] = 0
            return
        self._conta[k] = self._conta.get(k, 0) + 1
        if self._conta[k] >= self.giri and k not in self._emesse:
            self._emesse.add(k)
            out.append((codice, regola(codice),
                        f"{problema} (da {self._conta[k]} giri di fila)"))

    @staticmethod
    def _legato(c: Dict[str, Any], o: Any) -> bool:
        if c.get("ordine") is not None:
            return c.get("ordine") is o
        b = c.get("bet_id")
        if b not in (None, "") and str(b) == str(getattr(o, "bet_id", None) or ""):
            return True
        oid = c.get("ordine_id")
        return oid not in (None, "") and str(oid) == str(getattr(o, "id", ""))

    def _ordine_di(self, c: Dict[str, Any], ordini: Sequence[Any]) -> Optional[Any]:
        for o in ordini:
            if self._legato(c, o):
                return o
        return None

    @staticmethod
    def _sollecita(sollecitati: Optional[Dict[str, int]], codice: str) -> None:
        if sollecitati is not None:
            sollecitati[codice] = sollecitati.get(codice, 0) + 1

    # ------------------------------------------------------------ il giro
    def verifica(self, credute: Sequence[Dict[str, Any]],
                 sollecitati: Optional[Dict[str, int]] = None) -> List[Tuple[str, str, str]]:
        out: List[Tuple[str, str, str]] = []
        # le CP4 nate all'esecuzione (dal mercato, non dalla credenza)
        for codice, det in self.g._da_consegnare:
            out.append((codice, regola(codice), det))
        self.g._da_consegnare = []
        for cod, n in self.g.sollecitati.items():
            if n:
                self._sollecita_n(sollecitati, cod, n)
        self.g.sollecitati = {}
        if not self.g.colpiti:
            return out
        credute = list(credute or [])
        tutti = self.g.tutti_gli_ordini()
        tutte_le_chiusure = [c for b in credute for c in (b.get("chiusure") or [])]

        # ---- CP1: la chiusura colpita, sulla riga del bot ------------------
        for rec in self.g.colpiti:
            o = rec["ordine"]
            if self.g.mercato_chiuso(rec["chiave"][0]):
                continue
            self._sollecita(sollecitati, "CP1")
            m, rem, avg = abbinato(o), (residuo(o) if vivo(o) else 0.0), prezzo_medio(o)
            c = next((x for x in tutte_le_chiusure if self._legato(x, o)), None)
            problema: Optional[str] = None
            if c is None:
                if m > EPS or rem > EPS:
                    problema = (f"chiusura colpita {self.g._ref(o)} (bet {getattr(o, 'bet_id', None)}) "
                                f"abbinata {m:.2f} con residuo {rem:.2f}: NESSUNA riga/credenza "
                                f"del bot la riconosce")
            else:
                cm = _f(c.get("size_matched"))
                cr = _f(c.get("size_remaining"))
                ca = _f(c.get("avg_price_matched"))
                pezzi = []
                if cm is None:
                    # assente NON e' zero (catalogo §7.21), ma una riga che non
                    # scrive lo zero di un ordine mai abbinato non racconta
                    # niente di falso: si pretende il numero quando c'e'
                    if m > EPS or rem > EPS:
                        pezzi.append(f"abbinato NON scritto (mercato {m:.2f}, "
                                     f"residuo {rem:.2f})")
                elif abs(cm - m) > EPS:
                    pezzi.append(f"abbinato creduto {cm:.2f} contro {m:.2f} a mercato")
                # 23/09 (B-3, revisore B): un residuo o un prezzo medio NON
                # scritti mentre a mercato ci sono sono una violazione (prima
                # si confrontavano solo se scritti: falso verde), e il CHIESTO
                # si confronta con quello di flumine.
                if cr is None:
                    if rem > EPS:
                        pezzi.append(f"residuo NON scritto (a mercato {rem:.2f})")
                elif abs(cr - rem) > EPS:
                    pezzi.append(f"residuo creduto {cr:.2f} contro {rem:.2f} a mercato")
                if ca is None:
                    if m > EPS:
                        pezzi.append(f"prezzo medio NON scritto (abbinato {m:.2f}"
                                     + (f" a {avg:.2f})" if avg is not None else ")"))
                elif m > EPS and avg is not None and abs(ca - avg) > 0.011:
                    pezzi.append(f"prezzo medio creduto {ca:.2f} contro {avg:.2f}")
                # il chiesto: ``size_requested`` (la colonna della consapevolezza)
                # se la credenza la porta, altrimenti ``size`` (specchio tennis)
                cs = _f(c.get("size_requested"))
                if cs is None:
                    cs = _f(c.get("size"))
                problema_chiesto = _chiesto_non_coerente(cs, o, m, rem)
                if problema_chiesto:
                    pezzi.append(problema_chiesto)
                if pezzi:
                    problema = f"chiusura colpita {self.g._ref(o)}: " + "; ".join(pezzi)
            self._persiste("CP1", str(getattr(o, "id", "")), problema, out)

        colpite = set(self.g.per_chiave)
        for b in credute:
            chiave = tuple(b.get("chiave") or ())
            if chiave not in colpite or self.g.mercato_chiuso(chiave[0]):
                continue
            chiusure = list(b.get("chiusure") or [])

            # ---- CP2: copertura dichiarata contro abbinato vero ------------
            ap = b.get("apertura") or {}
            p0 = _f(ap.get("price"))
            if b.get("coperto") is not None and p0 and p0 > 1.0 and chiusure:
                legati = [(c, self._ordine_di(c, tutti)) for c in chiusure]
                verificabile = all(o is not None or not (_f(c.get("size_matched")) or 0.0) > EPS
                                   for c, o in legati)
                tocca_colpite = any(o is not None and any(o is r["ordine"] for r in self.g.colpiti)
                                    for _c, o in legati)
                if verificabile and tocca_colpite:
                    self._sollecita(sollecitati, "CP2")
                    vero = 0.0
                    chiesto = 0.0
                    for c, o in legati:
                        chiesto += (float(c.get("size") or 0.0) * float(c.get("price") or 0.0) / p0
                                    if str(c.get("status") or "") not in ("error", "cancelled") else 0.0)
                        if o is not None and abbinato(o) > 0 and prezzo_medio(o):
                            vero += abbinato(o) * float(prezzo_medio(o)) / p0
                    vero = round(vero, 2)
                    dichiarato = float(b["coperto"])
                    problema = None
                    if abs(dichiarato - vero) > 0.02:
                        problema = (f"{b.get('id')} {chiave}: copertura dichiarata "
                                    f"{dichiarato:.2f} contro {vero:.2f} ABBINATA "
                                    f"(sul chiesto sarebbe {chiesto:.2f})")
                    self._persiste("CP2", str(b.get("id")), problema, out)

            # ---- CP3: dichiarata CHIUSA con un residuo ---------------------
            # Il CASO c'e' per ogni posizione su una selezione colpita: la
            # domanda «la dichiari chiusa?» ha una risposta anche quando e' no.
            if b.get("per_selezione"):
                ordini_pos = self.g.ordini_del_bot(chiave[0], chiave[1])
                verificabile = True
            else:
                ordini_pos = []
                verificabile = True
                for c in list(b.get("ingressi") or []) + chiusure:
                    o = self._ordine_di(c, tutti)
                    if o is None:
                        if (_f(c.get("size_matched")) or 0.0) > EPS:
                            verificabile = False
                        continue
                    ordini_pos.append(o)
                if not ordini_pos:
                    verificabile = False
            if verificabile:
                self._sollecita(sollecitati, "CP3")
                d = direzione(ordini_pos)
                tol = tolleranza(ordini_pos, float(b.get("tolleranza") or 0.0))
                vivi = [o for o in ordini_pos
                        if vivo(o) and any(o is r["ordine"] for r in self.g.colpiti)]
                problema = None
                if b.get("chiusa") and (abs(d) > tol or vivi):
                    problema = (f"{b.get('id')} {chiave} dichiarata CHIUSA ma a mercato "
                                f"netto {d:+.2f} (tolleranza {tol:.2f})"
                                + (f", residuo VIVO {sum(residuo(o) for o in vivi):.2f} "
                                   f"sulla chiusura colpita" if vivi else ""))
                self._persiste("CP3", str(b.get("id")), problema, out)

        # ---- CP4 (sovracopertura): le chiusure hanno RIBALTATO la posizione --
        for chiave, st in self.g.per_chiave.items():
            if st["nuovo_ciclo"] or self.g.mercato_chiuso(chiave[0]):
                continue
            self._sollecita(sollecitati, "CP4")
            ordini_k = self.g.ordini_del_bot(chiave[0], chiave[1])
            d = direzione(ordini_k)
            tol = tolleranza(ordini_k)
            problema = None
            if st["segno"] * d < -tol:
                problema = (f"{chiave}: SOVRACOPERTURA, la posizione e' stata ribaltata "
                            f"dalle chiusure (netto {d:+.2f}, tolleranza {tol:.2f})")
            self._persiste("CP4", f"sovra{chiave}", problema, out)
        return out

    @staticmethod
    def _sollecita_n(sollecitati: Optional[Dict[str, int]], codice: str, n: int) -> None:
        if sollecitati is not None:
            sollecitati[codice] = sollecitati.get(codice, 0) + int(n)
