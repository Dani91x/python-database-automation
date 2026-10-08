"""SCAVALCO E RIFIUTI COI CODICI DI BETFAIR - due guasti del banco (CANTIERE 9, 08/10).

Specifica: `AUDIT_2026-10-08/SPECIFICHE_CANTIERI_CLOUD_2026-10-08.md`, CANTIERE 9.
Il 07/10 sera (decisioni dell'utente <<1) b>> e <<2) b>>, `BIBBIA_SCALPER_CALCIO.md`
par. 13-bis) lo scalper calcio chiude un residuo d'ingresso abbinato SOTTO il
floor di legge (0,50) con due ordini legali: lo SCAVALCO (`ordine_di_scavalco`:
punta 1,00, o banca al centesimo per una posizione corta) e poi la chiusura al
centesimo; al piu' 3 scavalchi per ciclo; il tetto di perdita conta solo le
perdite VERE (`stats.pnl_residui` a parte) e l'attivita' `loss_cap` scrive le
due cifre. Sulle registrazioni il caso non capita da solo: qui lo si PROVOCA.

IL GUASTO 1 - <<ingresso abbinato in parte>> (`GuastoIngressoParziale`)
  Il PRIMO gruppo di ingressi del bot su ogni selezione (le gambe del maker vive
  insieme: per la credenza VERA del bot sono `ingressi` dello slot) trova il
  mercato SOTTILE: tutte insieme possono abbinare al piu' `TETTO_INGRESSO`
  (0,29, la BACK abbinata del reperto R4 del 07/10). Non e' un fill scritto a
  mano: l'abbinamento resta di flumine (prezzi, istanti, coda, mercato che
  attraversa), il guasto TOGLIE liquidita' (`SimulatedOrder._update_matched`
  avvolto, come `chiusura_parziale._tetta_abbinato`). Quando tutte le gambe del
  gruppo sono morte (il bot le annulla dopo il TTL o lo stop avverso) il guasto
  finisce e il mercato torna quello registrato. Un gruppo morto senza un
  centesimo abbinato non ha avuto effetto: il guasto si RIARMA sul gruppo dopo.

IL GUASTO 2 - <<il finto Betfair rifiuta coi codici veri>> (`RifiutiConCodice`)
  Solo negli scenari `rifiuti-betfair-codici*`, sopra il guasto 1. Il PRIMO
  ordine di ogni tipo riceve la risposta FAILURE col codice vero:
    * scavalco (placeOrders)            -> INVALID_BET_SIZE
    * parcheggio del place-and-trim (placeOrders) -> INVALID_PROFIT_RATIO
    * rimpiazzo del place-and-trim (replaceOrders, parte place) -> BET_TAKEN_OR_LAPSED
  La risposta e' lo stesso oggetto che la simulazione di flumine restituisce per
  i SUOI rifiuti (`SimulatedPlaceResponse(status="FAILURE", error_code=...)`,
  stesse chiavi della `PlaceInstructionReport` vera: `status`, `error_code`,
  `order_status`, `bet_id`, ...), con la size tolta come fa flumine
  (`size_voided` per l'ordine mai nato, `size_lapsed` per BET_TAKEN_OR_LAPSED).
  Il rimpiazzo rifiutato NON resta nel `Trade` (come in produzione:
  `BetfairExecution.execute_replace` crea il sostituto solo su SUCCESS) e
  l'ordine sostituito resta annullato: la `cancel` del replace non si ritira
  (Betfair, replaceOrders: <<the cancellations will not be rolled back>>).

I CONTROLLI (dal MERCATO: ordini del blotter, abbinati veri; la credenza del
bot solo dove il controllo e' <<credenza contro mercato>>; mai la sola confessione):
  SV1  dopo un ingresso abbinato in parte la cui chiusura e' sotto il floor, lo
       scavalco parte entro `LIBRI_SCAVALCO` book del mercato e, abbinato lo
       scavalco e passata la pausa anti-churn che il bot dichiara
       (`flatten_min_interval_ms`), la chiusura parte entro altrettanti book;
  SV2  quando il bot dichiara chiuso il ciclo, la posizione del ciclo e' PIATTA
       (|se vince - se perde| <= 0,02 sugli abbinati veri); solo dopo il
       massimo di scavalchi il resto puo' restare, DICHIARATO dal bot;
  SV3  al piu' `SCAVALCHI_MAX` (3) scavalchi per ciclo;
  SV4  ogni scavalco a mercato ha la sua attivita' `scavalco` (lato, quota,
       importo uguali);
  SV5  ogni `loss_cap` scrive le due cifre (perdite vere e residui esclusi) e
       scatta solo con le perdite vere oltre il tetto;
  RC1  dopo un rifiuto nessuna posizione fantasma: uno slot vivo non poggia
       solo su ordini rifiutati e nessuna sequenza place-and-trim aspetta un
       ordine rifiutato oltre `GIRI_DI_TOLLERANZA` giri;
  RC2  nessun loop: dopo un rifiuto, al piu' `TETTO_ORDINI_DOPO_RIFIUTO`
       ordini nuovi sulla selezione prima che il ciclo si chiuda;
  RC3  ogni rifiuto e' scritto nell'attivita' del bot col suo codice entro
       `GIRI_DI_TOLLERANZA` giri; SOLO per `replaceOrders` (08/10, decisione D-2a
       del coordinatore) vale anche la riga `submin.NOTA_RIMPIAZZO_NON_NATO`: in
       produzione il codice del place rifiutato dentro un replace non arriva al
       bot (flumine `BetfairExecution.execute_replace`, `pass  # todo`);
  RC4  a ciclo chiuso dopo un rifiuto la posizione e' piatta o il residuo e'
       DICHIARATO dal bot (`residuo_ricordato`, `flatten_residual*`).

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import hashlib
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import chiusura_parziale as CP
from . import uscite_manuali as UM
from ..trading.submin import NOTA_RIMPIAZZO_NON_NATO

SCENARIO_INGRESSO = "ingresso-abbinato-in-parte"
SCENARIO_INGRESSO_PAPER = SCENARIO_INGRESSO + "-paper"
SCENARIO_CODICI = "rifiuti-betfair-codici"
SCENARIO_CODICI_PAPER = SCENARIO_CODICI + "-paper"
SCENARI: Tuple[str, ...] = (SCENARIO_INGRESSO, SCENARIO_INGRESSO_PAPER,
                            SCENARIO_CODICI, SCENARIO_CODICI_PAPER)
#: gli scenari in PROVA (client paper): paper = live, stesse azioni e importi
SCENARI_PROVA: Tuple[str, ...] = (SCENARIO_INGRESSO_PAPER, SCENARIO_CODICI_PAPER)
SCENARI_CODICI: Tuple[str, ...] = (SCENARIO_CODICI, SCENARIO_CODICI_PAPER)

#: quanto il primo gruppo di ingressi di una selezione puo' abbinare in tutto:
#: la BACK 0,29 del reperto R4 (07/10, `ordine_di_scavalco`), sotto il floor
TETTO_INGRESSO = 0.29
#: al piu' 3 scavalchi per ciclo: decisione dell'utente del 07/10
#: (`BIBBIA_SCALPER_CALCIO.md` par. 13-bis). Il test di contratto verifica che il
#: bot dichiari lo stesso numero (`_SCAVALCHI_MAX_PER_CICLO`).
SCAVALCHI_MAX = 3
#: piatto: |se vince - se perde| <= 0,02 (il monitor DONE del bot, specifica)
TOLLERANZA_PIATTO = 0.02
#: in quanti book del mercato devono partire lo scavalco e la chiusura (SV1).
#: Il bot decide a ogni book: annullate le gambe, al book dopo apre il flatten e
#: manda lo scavalco; 5 book lasciano margine alla latenza dell'annullo
#: (tolleranza del CONTROLLO, dichiarata; non e' un numero della strategia).
#: Un book = un istante di pubblicazione NUOVO del mercato (il motore riemette
#: lo stesso book a ogni riga del raw: non conta)
LIBRI_SCAVALCO = 5
#: giri (1 s di mercato) di tolleranza per i controlli credenza/mercato
GIRI_DI_TOLLERANZA = CP.GIRI_DI_TOLLERANZA
#: ordini nuovi ammessi sulla selezione dopo un rifiuto (lo stesso tetto del
#: loop di `chiusura_parziale`, misurato sul banco: 32 ordini il 15/09)
TETTO_ORDINI_DOPO_RIFIUTO = CP.TETTO_RIPIAZZAMENTI
#: Betfair lavora al centesimo
EPS = CP.EPS

CODICE_TAGLIA = "INVALID_BET_SIZE"
CODICE_PROFITTO = "INVALID_PROFIT_RATIO"
CODICE_PRESO = "BET_TAKEN_OR_LAPSED"
#: (tipo d'ordine, codice, operazione di Betfair)
PIANO_RIFIUTI: Tuple[Tuple[str, str, str], ...] = (
    ("scavalco", CODICE_TAGLIA, "placeOrders"),
    ("parcheggio", CODICE_PROFITTO, "placeOrders"),
    ("rimpiazzo", CODICE_PRESO, "replaceOrders"),
)
#: le attivita' con cui il bot DICHIARA un residuo che non chiude
ATTIVITA_RESIDUO = ("residuo_ricordato", "flatten_residual", "flatten_residual_forced")

DESCRIZIONE_INGRESSO = (
    "come `base`, ma il PRIMO gruppo di ingressi di ogni selezione trova il mercato "
    "sottile: al piu' %.2f abbinati in tutto (reperto R4), poi il mercato torna "
    "quello registrato. Il bot deve chiudere il residuo sotto 0,50 con lo scavalco "
    "e la chiusura al centesimo, ciclo PIATTO, al piu' %d scavalchi (SV1-SV5)"
    % (TETTO_INGRESSO, SCAVALCHI_MAX))
DESCRIZIONE_CODICI = (
    "come `%s`, e il finto Betfair risponde FAILURE coi codici veri al primo "
    "scavalco (INVALID_BET_SIZE), al primo parcheggio del place-and-trim "
    "(INVALID_PROFIT_RATIO) e al primo rimpiazzo (replaceOrders, "
    "BET_TAKEN_OR_LAPSED): nessuna posizione fantasma, nessun loop, ogni rifiuto "
    "scritto col codice, residuo dichiarato se non chiudibile (RC1-RC4)"
    % SCENARIO_INGRESSO)
DESCRIZIONI: Dict[str, str] = {
    SCENARIO_INGRESSO: DESCRIZIONE_INGRESSO + " - soldi veri simulati",
    SCENARIO_INGRESSO_PAPER: ("come `%s` in PROVA (client paper): stesse azioni e "
                              "stessi importi (paper = live)" % SCENARIO_INGRESSO),
    SCENARIO_CODICI: DESCRIZIONE_CODICI + " - soldi veri simulati",
    SCENARIO_CODICI_PAPER: ("come `%s` in PROVA (client paper): stesse azioni e "
                            "stessi importi (paper = live)" % SCENARIO_CODICI),
}

_REGOLE: Tuple[Tuple[str, str], ...] = (
    ("SV1", "dopo un ingresso abbinato in parte sotto il floor (0,50) lo scavalco "
            "parte entro %d book del mercato e la chiusura al centesimo entro %d book "
            "dopo lo scavalco abbinato e la pausa anti-churn dichiarata dal bot"
            % (LIBRI_SCAVALCO, LIBRI_SCAVALCO)),
    ("SV2", "a ciclo chiuso la posizione del ciclo e' PIATTA (|se vince - se perde| "
            "<= %.2f sugli abbinati veri); un resto solo dopo %d scavalchi e "
            "DICHIARATO dal bot" % (TOLLERANZA_PIATTO, SCAVALCHI_MAX)),
    ("SV3", "al piu' %d scavalchi per ciclo (decisione dell'utente del 07/10)"
            % SCAVALCHI_MAX),
    ("SV4", "ogni scavalco a mercato ha la sua attivita' `scavalco` (lato, quota, "
            "importo)"),
    ("SV5", "ogni `loss_cap` scrive le due cifre (perdite vere, residui esclusi) e "
            "scatta solo con le perdite vere oltre il tetto (decisione 2-b del 07/10)"),
    ("RC1", "dopo un rifiuto di Betfair nessuna posizione fantasma: uno slot vivo "
            "non poggia solo su ordini rifiutati, nessuna sequenza place-and-trim "
            "aspetta un ordine rifiutato oltre %d giri" % GIRI_DI_TOLLERANZA),
    ("RC2", "dopo un rifiuto di Betfair nessun loop: al piu' %d ordini nuovi sulla "
            "selezione prima che il ciclo si chiuda" % TETTO_ORDINI_DOPO_RIFIUTO),
    ("RC3", "ogni rifiuto di Betfair e' scritto nell'attivita' del bot col suo "
            "codice entro %d giri" % GIRI_DI_TOLLERANZA),
    ("RC4", "a ciclo chiuso dopo un rifiuto la posizione e' piatta o il residuo e' "
            "DICHIARATO dal bot"),
)


def elenco_controlli(scenario: Optional[str] = None) -> List[Tuple[str, str]]:
    """(codice, regola) dei controlli che lo scenario sollecita."""
    if scenario is not None and scenario not in SCENARI_CODICI:
        return [r for r in _REGOLE if r[0].startswith("SV")]
    return list(_REGOLE)


def regola(codice: str) -> str:
    return dict(_REGOLE).get(str(codice), "")


# ---------------------------------------------------------------------------
# leggere gli ordini di flumine SEMPRE nello stesso modo (quelli del CP)
# ---------------------------------------------------------------------------
def _f(v: Any) -> Optional[float]:
    return CP._f(v)


def creato_ms(ordine: Any) -> Optional[int]:
    """L'istante di nascita dell'ordine (flumine timbra il `publish_time` del
    book, datetime NAIVE in UTC: si dichiara UTC, come `certificazione`)."""
    creato = getattr(ordine, "date_time_created", None)
    if creato is None or not callable(getattr(creato, "timestamp", None)):
        return None
    try:
        if getattr(creato, "tzinfo", None) is None:
            from datetime import timezone

            creato = creato.replace(tzinfo=timezone.utc)
        return int(creato.timestamp() * 1000)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def chiusura_necessaria(ordini: Sequence[Any]) -> Tuple[Optional[str], float, float]:
    """(lato, importo, differenza) della chiusura che renderebbe piatti gli
    abbinati di ``ordini``, alla quota media d'ingresso: la formula del green-up
    (``|se vince - se perde| / quota``). Lato None = gia' piatta."""
    w, lo = CP.esposizione(ordini)
    d = w - lo
    if abs(d) <= TOLLERANZA_PIATTO + 1e-9:
        return None, 0.0, d
    pesi = [(CP.abbinato(o), CP.prezzo_medio(o)) for o in ordini
            if CP.abbinato(o) > 0 and CP.prezzo_medio(o)]
    tot = sum(m for m, _p in pesi)
    q = (sum(m * p for m, p in pesi) / tot) if tot > 0 else None
    if not q:
        return ("LAY" if d > 0 else "BACK"), 0.0, d
    return ("LAY" if d > 0 else "BACK"), abs(d) / float(q), d


def impronta_ordini(ordini: Sequence[Any]) -> Tuple[str, int]:
    """L'impronta degli ordini dello scenario (istante, mercato, selezione,
    lato, quota, chiesto, abbinato, prezzo medio, stato), SENZA id e bet_id:
    paper e live devono dare la STESSA (stesse azioni, stessi importi)."""
    righe = []
    for o in ordini:
        ot = getattr(o, "order_type", None)
        st = getattr(o, "status", None)
        righe.append("%s|%s|%s|%s|%.2f|%.2f|%.2f|%.4f|%s" % (
            creato_ms(o), getattr(o, "market_id", ""), getattr(o, "selection_id", ""),
            getattr(o, "side", ""), float(_f(getattr(ot, "price", None)) or 0.0),
            float(_f(getattr(ot, "size", None)) or 0.0), CP.abbinato(o),
            float(CP.prezzo_medio(o) or 0.0), getattr(st, "value", st)))
    righe.sort()
    return hashlib.sha256("\n".join(righe).encode("ascii", "replace")).hexdigest()[:16], len(righe)


# ---------------------------------------------------------------------------
# IL GUASTO 1: l'ingresso abbinato in parte
# ---------------------------------------------------------------------------
class GuastoIngressoParziale:
    """Il primo gruppo di ingressi di ogni selezione abbina al piu' ``tetto``.

    Si aggancia a `MotoreReplay.guasto_chiusure` (lo stesso aggancio del guasto
    <<chiusura abbinata in parte>>): il motore passa i pacchetti PRIMA di
    eseguirli (`prepara`) e qui si avvolge l'abbinamento degli ingressi."""

    def __init__(self, *, ruolo: Callable[[Any], Optional[str]],
                 tetto: float = TETTO_INGRESSO) -> None:
        self.ruolo = ruolo
        self.tetto = float(tetto)
        self.quadro: Any = None
        # (market_id, selection_id) -> il gruppo corrente
        self.gruppi: Dict[Tuple[str, int], Dict[str, Any]] = {}
        # i gruppi FINITI con effetto (abbinato > 0), in ordine
        self.colpiti: List[Dict[str, Any]] = []
        self.senza_effetto = 0
        self._decisi: set = set()

    @staticmethod
    def chiave(ordine: Any) -> Optional[Tuple[str, int]]:
        try:
            return (str(getattr(ordine, "market_id", "")), int(getattr(ordine, "selection_id", 0)))
        except (TypeError, ValueError):
            return None

    def prepara(self, quadro: Any, pacchi: Sequence[Any]) -> None:
        from flumine.order.orderpackage import OrderPackageType

        self.quadro = quadro
        for pacco in list(pacchi or []):
            if getattr(pacco, "package_type", None) != OrderPackageType.PLACE:
                continue
            for ordine in list(pacco):
                oid = str(getattr(ordine, "id", "") or id(ordine))
                if oid in self._decisi or CP.e_dell_utente(ordine):
                    continue
                try:
                    r = self.ruolo(ordine)
                except Exception:  # noqa: BLE001 - ruolo illeggibile: si riprova
                    r = None
                if r is None:
                    continue          # il bot non lo ha ancora in mano: al giro dopo
                self._decisi.add(oid)
                if r == "ingresso":
                    self._ingresso(ordine)

    def _ingresso(self, ordine: Any) -> None:
        k = self.chiave(ordine)
        sim = getattr(ordine, "simulated", None)
        if k is None or sim is None:
            return
        g = self.gruppi.get(k)
        if g is None:
            g = {"chiave": k, "ordini": [], "stato": "armato"}
            self.gruppi[k] = g
        if g["stato"] != "armato":
            return                    # guasto finito su questa selezione
        g["ordini"].append(ordine)
        if g.get("inizio_ms") is None:
            g["inizio_ms"] = creato_ms(ordine)
        originale = sim._update_matched
        tetto = self.tetto

        def _upd(dati: List[Any]) -> None:
            if g["stato"] == "armato":
                gia = sum(CP.abbinato(o) for o in g["ordini"])
                resto = round(tetto - gia, 2)
                if resto <= 0:
                    return
                if float(dati[2]) > resto:
                    dati = [dati[0], dati[1], resto]
            originale(dati)

        sim._update_matched = _upd

    def aggiorna(self, ms: int) -> List[Dict[str, Any]]:
        """A ogni book: un gruppo con tutte le gambe morte e' FINITO (con
        effetto: torna il record) o si RIARMA (nessun abbinato)."""
        nuovi = []
        for k, g in list(self.gruppi.items()):
            if g["stato"] != "armato" or not g["ordini"]:
                continue
            if any(CP.vivo(o) or _in_volo(o) for o in g["ordini"]):
                continue
            m = round(sum(CP.abbinato(o) for o in g["ordini"]), 2)
            if m <= EPS:
                self.senza_effetto += 1
                self.gruppi[k] = {"chiave": k, "ordini": [], "stato": "armato"}
                continue
            g["stato"] = "finito"
            g["fine_ms"] = int(ms)
            g["abbinato"] = m
            lato, imp, d = chiusura_necessaria(g["ordini"])
            g["chiusura"] = (lato, round(imp, 2), round(d, 4))
            self.colpiti.append(g)
            nuovi.append(g)
        return nuovi


def _in_volo(o: Any) -> bool:
    """Una richiesta in volo (cancel, replace) puo' ancora cambiare l'ordine."""
    st = getattr(o, "status", None)
    return str(getattr(st, "value", st) or "") in ("Pending", "Cancelling", "Updating",
                                                     "Replacing") and CP.residuo(o) > EPS


# ---------------------------------------------------------------------------
# IL GUASTO 2: il finto Betfair coi codici veri
# ---------------------------------------------------------------------------
class RifiutiConCodice:
    """Il PRIMO ordine di ogni tipo del ``piano`` riceve FAILURE col codice vero.

    ``tipo(ordine)`` -> "scavalco" | "parcheggio" | None (classificazione fatta
    dal chiamante con la credenza del bot e il mercato)."""

    def __init__(self, *, tipo: Callable[[Any], Optional[str]],
                 piano: Sequence[Tuple[str, str, str]] = PIANO_RIFIUTI) -> None:
        self.tipo = tipo
        self.piano = {t: (cod, op) for t, cod, op in piano}
        self.fatti: List[Dict[str, Any]] = []
        self._usati: set = set()
        self._visti: set = set()
        self._trade_avvolti: set = set()

    def prepara(self, quadro: Any, pacchi: Sequence[Any]) -> None:
        from flumine.order.orderpackage import OrderPackageType

        for pacco in list(pacchi or []):
            pt = getattr(pacco, "package_type", None)
            if pt == OrderPackageType.PLACE:
                for ordine in list(pacco):
                    oid = str(getattr(ordine, "id", "") or id(ordine))
                    if oid in self._visti or CP.e_dell_utente(ordine):
                        continue
                    try:
                        t = self.tipo(ordine)
                    except Exception:  # noqa: BLE001 - illeggibile: non si colpisce
                        t = None
                    if t is None:
                        continue
                    self._visti.add(oid)
                    if t in self.piano and t not in self._usati and t != "rimpiazzo":
                        self._usati.add(t)
                        self._rifiuta_place(ordine, t)
            elif pt == OrderPackageType.REPLACE and "rimpiazzo" in self.piano \
                    and "rimpiazzo" not in self._usati:
                for ordine in list(pacco):
                    if CP.e_dell_utente(ordine) or not UM.e_parcheggio(ordine):
                        continue
                    self._usati.add("rimpiazzo")
                    self._rifiuta_rimpiazzo(ordine)
                    break

    def _registra(self, ordine: Any, tipo: str, sostituito: Any = None) -> Dict[str, Any]:
        cod, op = self.piano[tipo]
        rec = {"tipo": tipo, "codice": cod, "operazione": op, "ordine": ordine,
               "sostituito": sostituito, "ms": None, "chiave": GuastoIngressoParziale.chiave(
                   sostituito if sostituito is not None else ordine)}
        self.fatti.append(rec)
        return rec

    def _rifiuta_place(self, ordine: Any, tipo: str) -> None:
        sim = getattr(ordine, "simulated", None)
        if sim is None:
            return
        rec = self._registra(ordine, tipo)
        cod = rec["codice"]

        def _place(order_package: Any, market_book: Any, instruction: Any, bet_id: Any) -> Any:
            # la risposta di Betfair, nella forma di flumine: l'ordine non nasce
            # (come `RUNNER_REMOVED`/`ERROR_IN_ORDER` della simulazione) e il
            # BOT la legge da `order.responses.place_response`
            pt = getattr(market_book, "publish_time_epoch", None)
            rec["ms"] = int(pt) if pt is not None else None
            sim.size_voided += sim.size_remaining
            return sim._create_place_response(None, status="FAILURE", error_code=cod)

        sim.place = _place

    def _rifiuta_rimpiazzo(self, ordine: Any) -> None:
        """replaceOrders: la cancel del parcheggio riesce, il place del sostituto
        no (BET_TAKEN_OR_LAPSED). Il sostituto non resta nel Trade (in produzione
        flumine lo crea solo su SUCCESS)."""
        trade = getattr(ordine, "trade", None)
        if trade is None or id(trade) in self._trade_avvolti:
            return
        self._trade_avvolti.add(id(trade))
        rec = self._registra(None, "rimpiazzo", sostituito=ordine)
        cod = rec["codice"]
        originale = trade.create_order_replacement

        def _crea(order: Any, new_price: float, size: float, date_time_created: Any) -> Any:
            nuovo = originale(order, new_price, size, date_time_created)
            if order is not ordine or rec["ordine"] is not None:
                return nuovo
            rec["ordine"] = nuovo
            sim = nuovo.simulated

            def _place(order_package: Any, market_book: Any, instruction: Any,
                       bet_id: Any) -> Any:
                pt = getattr(market_book, "publish_time_epoch", None)
                rec["ms"] = int(pt) if pt is not None else None
                sim.size_lapsed += sim.size_remaining
                try:
                    trade.orders.remove(nuovo)
                except ValueError:
                    pass
                return sim._create_place_response(None, status="FAILURE", error_code=cod)

            sim.place = _place
            return nuovo

        trade.create_order_replacement = _crea

    def tipi_fatti(self) -> List[str]:
        return [r["tipo"] for r in self.fatti if r.get("ms") is not None]


# ---------------------------------------------------------------------------
# LA SORVEGLIANZA: guasti + controlli, agganciata al banco dello scalper
# ---------------------------------------------------------------------------
class Sorveglianza:
    """Monta i guasti dello scenario e giudica SV1-SV5 (e RC1-RC4).

    ``strategia()``: la strategia VERA della sessione (credenza: `_slots`);
    ``attivita()``: le attivita' del bot `(kind, payload, ms)` (il tee del banco);
    ``ruolo(ordine)``: "ingresso"/"uscita"/None dalla credenza del bot. Gli
    ordini a mercato si leggono dal blotter del quadro di flumine (quello che il
    motore passa a ``prepara``). Il banco chiama ``al_book`` a ogni book,
    ``giro`` alla cadenza dei controlli, ``riepilogo`` a fine replay."""

    def __init__(self, scenario: str, *, strategia: Callable[[], Any],
                 attivita: Callable[[], Sequence[Tuple[str, Dict[str, Any], int]]],
                 ruolo: Callable[[Any], Optional[str]]) -> None:
        self.scenario = scenario
        self.strategia = strategia
        self.attivita = attivita
        self.ruolo = ruolo
        self.guasto = GuastoIngressoParziale(ruolo=ruolo)
        self.rifiuti: Optional[RifiutiConCodice] = (
            RifiutiConCodice(tipo=self.tipo_ordine) if scenario in SCENARI_CODICI else None)
        self.sollecitati: Dict[str, int] = {}
        self.violazioni: List[Tuple[str, str, str]] = []
        self._emesse: set = set()
        # book del mercato contati per istante di pubblicazione DIVERSO: il motore
        # riemette il book di ogni mercato a ogni riga del raw (stesso istante,
        # nessuna informazione nuova) e il bot non vede niente di nuovo
        self.libri: Dict[str, int] = {}
        self._ultimo_ms: Dict[str, int] = {}
        # (market_id, selection_id) -> [(nato_ms, id)] degli INGRESSI (credenza
        # del bot nell'istante in cui nascono) visti sulle chiavi sorvegliate: il
        # primo ingresso nuovo chiude il ciclo precedente (il bot e' ripartito)
        self._ingressi: Dict[Tuple[str, int], List[Tuple[int, int]]] = {}
        self._classificati: set = set()
        self.cicli: List[Dict[str, Any]] = []
        self.non_esercitato: List[str] = []
        self.loss_cap_visti = 0
        self._att_da = 0
        self._persiste: Dict[str, int] = {}
        self.ms = 0

    # ----------------------------------------------- aggancio al motore
    def prepara(self, quadro: Any, pacchi: Sequence[Any]) -> None:
        self.guasto.prepara(quadro, pacchi)
        if self.rifiuti is not None:
            self.rifiuti.prepara(quadro, pacchi)

    # ------------------------------------------------------- utilita'
    def _soll(self, codice: str, n: int = 1) -> None:
        self.sollecitati[codice] = self.sollecitati.get(codice, 0) + n

    def _viola(self, codice: str, oggetto: str, dettaglio: str) -> None:
        k = (codice, oggetto)
        if k in self._emesse:
            return
        self._emesse.add(k)
        self.violazioni.append((codice, regola(codice), dettaglio))

    def ordini_chiave(self, k: Tuple[str, int], dal_ms: Optional[int] = None) -> List[Any]:
        """Gli ordini del BOT (strategia della sessione) a mercato su una
        selezione, nati da ``dal_ms`` in poi: il blotter del mercato."""
        q = self.guasto.quadro
        mercati = getattr(getattr(q, "markets", None), "markets", None) or {}
        m = mercati.get(str(k[0]))
        if m is None:
            return []
        s = self.strategia()
        out = []
        for o in list(getattr(m, "blotter", None) or []):
            if CP.e_dell_utente(o) or GuastoIngressoParziale.chiave(o) != k:
                continue
            if s is not None and getattr(getattr(o, "trade", None), "strategy", None) is not s:
                continue
            c = creato_ms(o)
            if dal_ms is not None and c is not None and c < dal_ms:
                continue
            out.append(o)
        return out

    def tutti_gli_ordini(self) -> List[Any]:
        q = self.guasto.quadro
        mercati = getattr(getattr(q, "markets", None), "markets", None) or {}
        s = self.strategia()
        out = []
        for m in list(mercati.values()):
            for o in list(getattr(m, "blotter", None) or []):
                if CP.e_dell_utente(o):
                    continue
                if s is not None and getattr(getattr(o, "trade", None), "strategy", None) is not s:
                    continue
                out.append(o)
        return out

    def _credenza(self, k: Tuple[str, int]) -> Optional[Any]:
        s = self.strategia()
        if s is None:
            return None
        return dict(getattr(s, "_slots", {}) or {}).get(k)

    def tipo_ordine(self, ordine: Any) -> Optional[str]:
        """Per il finto Betfair: un ordine d'USCITA del bot (credenza) e' il
        parcheggio di un place-and-trim (`uscite_manuali.e_parcheggio`) o uno
        scavalco (allarga la posizione abbinata della selezione invece di
        ridurla). None = nessuno dei due (o il bot non lo ha ancora in mano)."""
        try:
            r = self.ruolo(ordine)
        except Exception:  # noqa: BLE001
            r = None
        if r != "uscita":
            return None
        if UM.e_parcheggio(ordine):
            return "parcheggio"
        k = GuastoIngressoParziale.chiave(ordine)
        if k is None:
            return None
        if _allarga([o for o in self.ordini_chiave(k) if o is not ordine], ordine):
            return "scavalco"
        return None

    # ------------------------------------------------------- a ogni book
    def al_book(self, market_id: str, ms: int, pubblicato_ms: Optional[int] = None) -> None:
        """``ms``: l'orologio di mercato del banco (avanza coi book di TUTTI i
        mercati); ``pubblicato_ms``: l'istante di pubblicazione del book di QUESTO
        mercato, che conta i book (assente = ``ms``)."""
        self.ms = int(ms)
        pub = int(pubblicato_ms) if pubblicato_ms else self.ms
        if self._ultimo_ms.get(market_id) != pub:
            self._ultimo_ms[market_id] = pub
            self.libri[market_id] = self.libri.get(market_id, 0) + 1
        for g in self.guasto.aggiorna(ms):
            self._nuovo_ciclo(g, market_id)
        self._registra_ingressi(market_id)
        for c in self.cicli:
            if not c["chiuso"] and c["chiave"][0] == market_id:
                self._segui_ciclo(c, market_id)

    def _e_ingresso(self, o: Any) -> bool:
        try:
            return self.ruolo(o) == "ingresso"
        except Exception:  # noqa: BLE001 - credenza illeggibile: non e' un ingresso
            return False

    def _chiavi_aperte(self, market_id: str) -> set:
        k = {c["chiave"] for c in self.cicli if not c["chiuso"] and c["chiave"][0] == market_id}
        if self.rifiuti is not None:
            k |= {r["chiave"] for r in self.rifiuti.fatti
                  if r.get("aperto", True) and r["chiave"] and r["chiave"][0] == market_id}
        return k

    def _registra_ingressi(self, market_id: str) -> None:
        """A ogni book, sulle sole chiavi sorvegliate: ogni ordine NUOVO che il bot
        tiene come INGRESSO (la sua credenza nell'istante in cui nasce)."""
        for k in self._chiavi_aperte(market_id):
            for o in self.ordini_chiave(k):
                if id(o) in self._classificati:
                    continue
                self._classificati.add(id(o))
                if self._e_ingresso(o):
                    self._ingressi.setdefault(k, []).append((creato_ms(o) or self.ms, id(o)))

    def _taglio(self, k: Tuple[str, int], dopo_ms: Optional[int], esclusi: set) -> Optional[int]:
        """L'istante del primo INGRESSO nuovo della chiave nato dopo ``dopo_ms``
        (esclusi gli ordini ``esclusi``): li' il ciclo precedente e' finito."""
        nati = [t for t, i in self._ingressi.get(k, []) if i not in esclusi
                and (dopo_ms is None or t >= dopo_ms)]
        return min(nati) if nati else None

    def _ordini_fino(self, k: Tuple[str, int], dal_ms: Optional[int],
                     taglio: Optional[int], esclusi_taglio: set) -> List[Any]:
        """Gli ordini della chiave nati da ``dal_ms`` e PRIMA del taglio (il primo
        ingresso del ciclo dopo e cio' che nasce con lui non sono di questo ciclo)."""
        out = []
        for o in self.ordini_chiave(k, dal_ms):
            if taglio is not None and id(o) not in esclusi_taglio:
                c = creato_ms(o)
                if c is not None and c >= taglio:
                    continue
            out.append(o)
        return out

    def _nuovo_ciclo(self, g: Dict[str, Any], market_id: str) -> None:
        lato, imp, d = g["chiusura"]
        sotto = lato is not None and imp < _floor() - 1e-9
        c = {"chiave": g["chiave"], "gruppo": g, "inizio_ms": g.get("inizio_ms"),
             "fine_gruppo_ms": g["fine_ms"], "libro0": self.libri.get(market_id, 0),
             "sotto_floor": sotto, "chiusura_ingresso": (lato, imp, d),
             "visti": {id(o) for o in g["ordini"]}, "scavalchi": [], "chiusure": [],
             "chiuso": False, "esito": None}
        self.cicli.append(c)
        if sotto:
            self._soll("SV1")

    def _segui_ciclo(self, c: Dict[str, Any], mid: str) -> None:
        k = c["chiave"]
        nlib = self.libri.get(mid, 0)
        gruppo = {id(o) for o in c["gruppo"]["ordini"]}
        c["taglio"] = self._taglio(k, c["inizio_ms"], gruppo)
        ordini = self._ordini_fino(k, c["inizio_ms"], c["taglio"], gruppo)
        if c["taglio"] is not None:
            return          # il bot e' ripartito: il ciclo si giudica al giro
        for o in ordini:
            if id(o) in c["visti"]:
                continue
            prima = [x for x in ordini if id(x) in c["visti"]]
            c["visti"].add(id(o))
            voce = {"ordine": o, "libro": nlib, "ms": self.ms}
            if _allarga(prima, o) and not UM.e_parcheggio(o):
                c["scavalchi"].append(voce)
            elif abs(CP.direzione(prima)) > TOLLERANZA_PIATTO:
                c["chiusure"].append(voce)
        if not c["sotto_floor"]:
            return
        w, lo = CP.esposizione(ordini)
        piatta = abs(w - lo) <= TOLLERANZA_PIATTO + 1e-9
        # SV1 a) lo scavalco entro LIBRI_SCAVALCO book dalla fine del gruppo
        if not c["scavalchi"] and not piatta and nlib - c["libro0"] > LIBRI_SCAVALCO:
            self._viola("SV1", "scavalco|%s|%s" % (k, c["inizio_ms"]), (
                "%s: ingresso abbinato %.2f (chiusura %s %.2f sotto il floor) e dopo %d "
                "book del mercato nessuno scavalco" % (
                    k, c["gruppo"]["abbinato"], c["chiusura_ingresso"][0],
                    c["chiusura_ingresso"][1], nlib - c["libro0"])))
        if not c["scavalchi"]:
            return
        # SV1 b) la chiusura entro LIBRI_SCAVALCO book dopo lo scavalco abbinato
        # e la pausa anti-churn che il bot dichiara (flatten_min_interval_ms)
        ultimo = c["scavalchi"][-1]
        o = ultimo["ordine"]
        if ultimo.get("dal_ms") is None and not CP.vivo(o) and not _in_volo(o) \
                and CP.abbinato(o) > EPS:
            pausa = int(getattr(self.strategia(), "flatten_min_interval_ms", 0) or 0)
            ultimo["dal_ms"] = self.ms + pausa
        if ultimo.get("dal_ms") is None or self.ms < ultimo["dal_ms"]:
            return
        if ultimo.get("libro_pausa") is None:
            ultimo["libro_pausa"] = nlib
        dopo = [x for x in c["chiusure"] if x["ms"] >= ultimo["ms"]]
        if not dopo and not piatta and nlib - ultimo["libro_pausa"] > LIBRI_SCAVALCO:
            ot = getattr(o, "order_type", None)
            self._viola("SV1", "chiusura|%s|%s" % (k, id(o)), (
                "%s: scavalco %s %.2f @%s abbinato e, passata la pausa del bot, dopo "
                "%d book nessuna chiusura a mercato"
                % (k, CP.lato(o), CP.abbinato(o), _f(getattr(ot, "price", None)),
                   nlib - ultimo["libro_pausa"])))

    # ------------------------------------------------------- al giro
    def giro(self, ms: int, *, fine: bool = False) -> List[Tuple[str, str, str]]:
        if ms:
            self.ms = int(ms)
        self._giudica_cicli(fine)
        self._giudica_attivita(fine)
        if self.rifiuti is not None:
            self._giudica_rifiuti(fine)
        if fine:
            self._fine()
        out, self.violazioni = self.violazioni, []
        return out

    def _dichiarato(self, k: Tuple[str, int], dal_ms: Optional[int]) -> bool:
        """Il bot ha DICHIARATO il residuo della selezione (`residuo_ricordato`,
        la riga CRITICAL che segue ogni `flatten_residual*`) da ``dal_ms``."""
        for kind, p, t in list(self.attivita() or []):
            if kind != "residuo_ricordato":
                continue
            if dal_ms is not None and t is not None and int(t) < int(dal_ms):
                continue
            try:
                if int(p.get("selection_id") or 0) == int(k[1]):
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def _ciclo_chiuso_dal_bot(self, k: Tuple[str, int], ordini: Sequence[Any]) -> bool:
        slot = self._credenza(k)
        stato = str(getattr(slot, "status", "") or "")
        chiuso = slot is None or stato in ("IDLE", "DONE")
        return chiuso and not any(CP.vivo(o) or _in_volo(o) for o in ordini)

    def _giudica_cicli(self, fine: bool) -> None:
        for c in self.cicli:
            if c["chiuso"]:
                continue
            k = c["chiave"]
            gruppo = {id(o) for o in c["gruppo"]["ordini"]}
            c["taglio"] = self._taglio(k, c["inizio_ms"], gruppo)
            ordini = self._ordini_fino(k, c["inizio_ms"], c["taglio"], gruppo)
            # SV3: al piu' SCAVALCHI_MAX scavalchi nel ciclo (dal mercato)
            if c["scavalchi"] and not c.get("sv3"):
                c["sv3"] = True
                self._soll("SV3")
            if len(c["scavalchi"]) > SCAVALCHI_MAX:
                self._viola("SV3", "n|%s|%s" % (k, c["inizio_ms"]), (
                    "%s: %d scavalchi nel ciclo (massimo %d)"
                    % (k, len(c["scavalchi"]), SCAVALCHI_MAX)))
            chiuso_bot = c["taglio"] is not None or self._ciclo_chiuso_dal_bot(k, ordini)
            if not (chiuso_bot or fine):
                continue
            c["chiuso"] = True
            w, lo = CP.esposizione(ordini)
            diff = abs(w - lo)
            c["esito"] = {"se_vince": round(w, 4), "se_perde": round(lo, 4),
                          "differenza": round(diff, 4), "ms": self.ms,
                          "fine_replay": bool(not chiuso_bot)}
            if not c["sotto_floor"]:
                continue
            self._soll("SV2")
            if diff <= TOLLERANZA_PIATTO + 1e-9:
                continue
            dichiarato = self._dichiarato(k, c["fine_gruppo_ms"])
            if len(c["scavalchi"]) >= SCAVALCHI_MAX and dichiarato:
                c["esito"]["dichiarato"] = True
                continue
            self._viola("SV2", "ciclo|%s|%s" % (k, c["inizio_ms"]), (
                "%s: ciclo %s con la posizione NON piatta: se vince %.2f, se perde %.2f "
                "(differenza %.2f); scavalchi %d, residuo %s"
                % (k, "aperto a fine replay" if c["esito"]["fine_replay"]
                   else "dichiarato chiuso dal bot", w, lo, diff, len(c["scavalchi"]),
                   "DICHIARATO" if dichiarato else "NON dichiarato")))

    def _giudica_attivita(self, fine: bool) -> None:
        att = list(self.attivita() or [])
        nuove, self._att_da = att[self._att_da:], len(att)
        s = self.strategia()
        cap = float(getattr(s, "event_loss_cap", 0.0) or 0.0) if s is not None else 0.0
        for kind, p, t in nuove:
            if kind != "loss_cap":
                continue
            # SV5: le due cifre e lo scatto solo sulle perdite vere
            self.loss_cap_visti += 1
            self._soll("SV5")
            vere, res = _f(p.get("locked")), _f(p.get("residui_esclusi"))
            if vere is None or res is None:
                self._viola("SV5", "loss_cap|%s" % t, (
                    "attivita' loss_cap senza le due cifre (perdite vere %r, residui "
                    "esclusi %r)" % (p.get("locked"), p.get("residui_esclusi"))))
            elif cap > 0 and vere > -cap + 0.005:
                self._viola("SV5", "loss_cap_sotto|%s" % t, (
                    "loss_cap scattato con perdite vere %.2f sopra il tetto -%.2f "
                    "(residui esclusi %.2f)" % (vere, cap, res)))
        # SV4: ogni scavalco a mercato ha la SUA attivita' (lato, quota, importo)
        for c in self.cicli:
            for sc in c["scavalchi"]:
                if sc.get("attivita_vista"):
                    continue
                o = sc["ordine"]
                if not sc.get("giri"):
                    self._soll("SV4")
                sc["giri"] = sc.get("giri", 0) + 1
                ot = getattr(o, "order_type", None)
                if any(kind == "scavalco"
                       and str(p.get("side") or "").upper() == CP.lato(o)
                       and _uguale(p.get("price"), getattr(ot, "price", None), 1e-9)
                       and _uguale(p.get("size"), getattr(ot, "size", None), 0.005)
                       and _uguale(p.get("selection_id"), getattr(o, "selection_id", None), 0)
                       for kind, p, _t in att):
                    sc["attivita_vista"] = True
                elif sc["giri"] > GIRI_DI_TOLLERANZA or fine:
                    self._viola("SV4", "scavalco|%s" % id(o), (
                        "%s: scavalco %s %.2f @%s a mercato senza la sua attivita' "
                        "`scavalco`" % (c["chiave"], CP.lato(o),
                                        float(_f(getattr(ot, "size", None)) or 0.0),
                                        _f(getattr(ot, "price", None)))))

    def _giudica_rifiuti(self, fine: bool) -> None:
        att = list(self.attivita() or [])
        for rec in self.rifiuti.fatti:
            if rec.get("ms") is None:
                continue                      # pacchetto non ancora eseguito
            k = rec["chiave"]
            oggetto = "%s|%s" % (rec["tipo"], rec["ms"])
            if rec.get("giri") is None:
                # il ciclo in cui cade il rifiuto: dal primo ordine che lo slot
                # segue in quel momento (credenza), o dal rifiuto stesso
                rec["giri"] = 0
                slot = self._credenza(k)
                seguiti = [x for x in (getattr(slot, "entry", None),
                                       getattr(slot, "entry_back", None),
                                       getattr(slot, "entry_lay", None),
                                       getattr(slot, "close", None),
                                       *list(getattr(slot, "flatten_orders", None) or []))
                           if x is not None] if slot is not None else []
                nati = [creato_ms(x) for x in seguiti if creato_ms(x) is not None]
                rec["ciclo_dal_ms"] = min(nati) if nati else int(rec["ms"])
                rec["ids_prima"] = {id(x) for x in self.ordini_chiave(k)}
                rec["aperto"] = True
                self._soll("RC2")
                self._soll("RC3")
            rec["giri"] += 1
            # RC3: il rifiuto scritto col suo codice
            if not rec.get("scritto"):
                # D-2a (08/10): per replaceOrders il codice non arriva al bot
                # (flumine lo scarta): basta la riga "rimpiazzo NON nato"
                ammessi = [rec["codice"]]
                if rec.get("operazione") == "replaceOrders":
                    ammessi.append(NOTA_RIMPIAZZO_NON_NATO)
                rec["scritto"] = any(
                    t is not None and int(t) >= int(rec["ms"])
                    and any(a in _testo(p) for a in ammessi) for _kind, p, t in att)
                if not rec["scritto"] and (rec["giri"] > GIRI_DI_TOLLERANZA or fine):
                    self._viola("RC3", oggetto, (
                        "%s: rifiuto %s (%s, %s) mai scritto col codice nell'attivita' "
                        "del bot" % (k, rec["codice"], rec["tipo"], rec["operazione"])))
            # RC1: nessuna posizione fantasma sul rifiutato (credenza/mercato)
            self._soll("RC1")
            problema = self._fantasma(rec)
            n = (self._persiste.get(oggetto, 0) + 1) if problema else 0
            self._persiste[oggetto] = n
            if problema and n >= GIRI_DI_TOLLERANZA:
                self._viola("RC1", oggetto, problema)
            if not rec["aperto"]:
                continue
            # RC2: niente loop fino alla chiusura del ciclo (il primo ingresso
            # nuovo dopo il rifiuto apre il ciclo dopo: da li' non si conta)
            taglio = self._taglio(k, int(rec["ms"]), rec["ids_prima"])
            ordini = self._ordini_fino(k, rec["ciclo_dal_ms"], taglio, rec["ids_prima"])
            rec["dopo"] = sum(1 for o in self._ordini_fino(k, None, taglio, rec["ids_prima"])
                              if id(o) not in rec["ids_prima"])
            if rec["dopo"] > TETTO_ORDINI_DOPO_RIFIUTO:
                self._viola("RC2", oggetto, (
                    "%s: %d ordini nuovi dopo il rifiuto %s (tetto %d): loop"
                    % (k, rec["dopo"], rec["codice"], TETTO_ORDINI_DOPO_RIFIUTO)))
            chiuso = taglio is not None or self._ciclo_chiuso_dal_bot(k, ordini)
            if not (chiuso or fine):
                continue
            # RC4: a ciclo chiuso piatta o il residuo DICHIARATO
            rec["aperto"] = False
            self._soll("RC4")
            w, lo = CP.esposizione(ordini)
            rec["esito"] = {"differenza": round(abs(w - lo), 4),
                            "fine_replay": bool(not chiuso)}
            if abs(w - lo) > TOLLERANZA_PIATTO + 1e-9 and not self._dichiarato(k, rec["ms"]):
                self._viola("RC4", oggetto, (
                    "%s: dopo il rifiuto %s il ciclo e' %s con differenza %.2f fra gli "
                    "esiti NON dichiarata" % (k, rec["codice"],
                                              "aperto a fine replay" if not chiuso
                                              else "chiuso", abs(w - lo))))

    def _fantasma(self, rec: Dict[str, Any]) -> Optional[str]:
        """Credenza contro mercato sull'ordine rifiutato (o sostituito)."""
        o = rec["ordine"] if rec["tipo"] != "rimpiazzo" else rec["sostituito"]
        if o is None:
            return None
        slot = self._credenza(rec["chiave"])
        if slot is None:
            return None
        for e in list(getattr(slot, "submins", None) or []):
            if not isinstance(e, dict) or e.get("order") is not o:
                continue
            passo = str(getattr(getattr(e.get("state"), "step", None), "value", "") or "")
            if passo in ("init", "placed", "trimmed") and not CP.vivo(o) and not _in_volo(o):
                return ("%s: la sequenza place-and-trim del bot aspetta l'ordine %s "
                        "(passo %s, rifiutato %s) che a mercato e' morto"
                        % (rec["chiave"], rec["tipo"], passo, rec["codice"]))
        stato = str(getattr(slot, "status", "") or "")
        if stato not in ("QUOTING", "QUOTING2", "CANCELLING", "LOCKING", "FLATTENING"):
            return None
        seguiti = [x for x in (getattr(slot, "entry", None), getattr(slot, "entry_back", None),
                               getattr(slot, "entry_lay", None), getattr(slot, "close", None),
                               getattr(slot, "next_entry", None),
                               *list(getattr(slot, "flatten_orders", None) or []))
                   if x is not None]
        if all(x is not o for x in seguiti):
            return None
        sani = [x for x in seguiti if x is not o and (CP.vivo(x) or CP.abbinato(x) > EPS)]
        if not sani:
            return ("%s: lo slot e' '%s' e poggia solo sull'ordine rifiutato (%s)"
                    % (rec["chiave"], stato, rec["codice"]))
        return None

    def _fine(self) -> None:
        g = self.guasto
        if not g.colpiti:
            self.non_esercitato.append(
                "%s: nessun gruppo d'ingresso abbinato in parte (il guasto non ha mai "
                "avuto effetto: SV1-SV5 'non lo so')" % self.scenario)
        elif not any(c["sotto_floor"] for c in self.cicli):
            self.non_esercitato.append(
                "%s: nessun ingresso abbinato in parte con la chiusura sotto il floor"
                % self.scenario)
        elif not any(c["scavalchi"] for c in self.cicli):
            self.non_esercitato.append("%s: nessuno scavalco a mercato" % self.scenario)
        if self.rifiuti is not None:
            fatti = set(self.rifiuti.tipi_fatti())
            mancano = [t for t, _c, _o in PIANO_RIFIUTI if t not in fatti]
            if mancano:
                self.non_esercitato.append(
                    "%s: rifiuti del piano MAI eseguiti (nessun ordine di quel tipo): %s"
                    % (self.scenario, ", ".join(mancano)))

    # ------------------------------------------------------- referto
    def riepilogo(self) -> List[str]:
        g = self.guasto
        righe = []
        parti = []
        for c in self.cicli:
            e = c.get("esito") or {}
            parti.append(
                "sel %s: ingresso abbinato %.2f su %d gamba/e -> chiusura %s %.2f%s; "
                "scavalchi %d %s; chiusure %d; fine ciclo: differenza %s%s"
                % (c["chiave"][1], c["gruppo"]["abbinato"], len(c["gruppo"]["ordini"]),
                   c["chiusura_ingresso"][0], c["chiusura_ingresso"][1],
                   " (SOTTO il floor)" if c["sotto_floor"] else "",
                   len(c["scavalchi"]),
                   ["%s %.2f @%s abbinato %.2f" % (
                       CP.lato(s["ordine"]),
                       float(_f(getattr(s["ordine"].order_type, "size", None)) or 0.0),
                       _f(getattr(s["ordine"].order_type, "price", None)),
                       CP.abbinato(s["ordine"])) for s in c["scavalchi"]],
                   len(c["chiusure"]),
                   e.get("differenza", "ciclo aperto"),
                   " (residuo DICHIARATO)" if e.get("dichiarato") else ""))
        righe.append("INGRESSO ABBINATO IN PARTE (tetto %.2f): gruppi colpiti %d, senza "
                     "effetto (riarmati) %d; %s"
                     % (g.tetto, len(g.colpiti), g.senza_effetto,
                        "; ".join(parti) or "nessun ciclo"))
        if self.rifiuti is not None:
            fatti = []
            for r in self.rifiuti.fatti:
                o = r["ordine"] if r["tipo"] != "rimpiazzo" else r["sostituito"]
                ot = getattr(o, "order_type", None)
                e = r.get("esito") or {}
                fatti.append("%s %s (%s) su %s %s %.2f @%s%s; ordini dopo %s; fine ciclo "
                             "differenza %s; scritto col codice: %s" % (
                                 r["tipo"], r["codice"], r["operazione"], r["chiave"],
                                 CP.lato(o), float(_f(getattr(ot, "size", None)) or 0.0),
                                 _f(getattr(ot, "price", None)),
                                 "" if r.get("ms") is not None else " [mai eseguito]",
                                 r.get("dopo"), e.get("differenza", "ciclo aperto"),
                                 "si'" if r.get("scritto") else "NO"))
            righe.append("FINTO BETFAIR coi codici veri: %s"
                         % ("; ".join(fatti) or "nessun rifiuto"))
        imp, n = impronta_ordini(self.tutti_gli_ordini())
        righe.append("impronta degli ordini del bot (paper = live): %s su %d ordini"
                     % (imp, n))
        righe.append("loss_cap visti: %d" % self.loss_cap_visti)
        mai = [c for c, _r in elenco_controlli(self.scenario) if not self.sollecitati.get(c)]
        if mai:
            righe.append("controlli del cantiere 9 MAI sollecitati (non lo so): %s"
                         % ", ".join(mai))
        return righe


def _allarga(prima: Sequence[Any], ordine: Any) -> bool:
    """L'ordine va nella STESSA direzione della posizione abbinata degli ordini
    ``prima`` (la allarga): una punta su una posizione gia' lunga, una banca su
    una posizione gia' corta. E' cosi' che uno scavalco si riconosce dal
    mercato (`ordine_di_scavalco`)."""
    d = CP.direzione(prima)
    la = CP.lato(ordine)
    return (la == "BACK" and d > TOLLERANZA_PIATTO) or (la == "LAY" and d < -TOLLERANZA_PIATTO)


def _floor() -> float:
    from ..trading.minimi_it import SUBMIN_IMPORTO_FINALE_MIN

    return float(SUBMIN_IMPORTO_FINALE_MIN)


def _uguale(a: Any, b: Any, tol: float) -> bool:
    x, y = _f(a), _f(b)
    return x is not None and y is not None and abs(x - y) <= tol + 1e-12


def _testo(p: Any) -> str:
    try:
        return " ".join("%s=%s" % (k, v) for k, v in dict(p or {}).items())
    except (TypeError, ValueError):
        return str(p)
