"""uscite_manuali - gli scenari del banco comune a USCITE MANUALI (CANTIERE N3, 28/09).

Ordine dell'utente (28/09): ogni bot nasce a uscite MANUALI; ogni uscita di
trading (profitto o perdita: target, stop, time-stop, timeout, scratch,
strutturale, scaglione, green) diventa una PROPOSTA coi numeri che l'utente
approva; l'uscita approvata parte sul mercato di ADESSO e solo se la
condizione vale ancora; le PROTEZIONI restano automatiche.

Due scenari, per i bot di flusso (tennis x4, scalper calcio maker+sniper):

  * ``uscite-manuali``: interruttore SPENTO, nessuno firma. Controlli:
      UM1 nessuna uscita di trading ESEGUITA (il cancello non lascia mai
          uscire; l'interruttore del bot resta spento);
      UM2 ogni uscita DECISA dalla strategia ha la sua proposta
          (``uscita_proposta`` alla nascita, con le chiavi comuni);
      UM3 le protezioni restano fuori dal cancello (nessun motivo che non sia
          di trading ci passa) e, dove il bot ha una fine finestra, a fine
          sessione e' piatto o dichiarato (il force-flat e' scattato);
      UM4 una proposta la cui condizione cade SPARISCE
          (``uscita_proposta_decaduta``: ne' proposta ne' firma restano).
  * ``uscite-manuali-firmate``: come sopra, ma il banco FIRMA ogni proposta
    dopo ``FIRMA_DOPO_S`` secondi di tempo di mercato dalla sua nascita, per
    la STESSA via di produzione (la firma ``{chiave: now()}`` in
    ``params.uscite_approvate`` della riga di controllo, come la scrive la RPC;
    il runner/la sessione la rilegge al battito). Controlli in piu':
      UF1 una firma fa partire l'uscita UNA volta sola;
      UF2 l'uscita firmata parte all'importo ESATTO della proposta di adesso
          (somma di abbinato + residuo degli ordini nuovi di quella
          selezione e di quel lato, nei ``FINESTRA_ORDINI_S`` secondi dopo);
      UF3 una firma non esegue mai un'uscita diversa da quella firmata
          (stessa chiave, stesso motivo, stessa selezione, stesso lato, stessa
          proposta: ``decided_at`` uguale a quella vista dall'utente).

L'osservatore NON sostituisce niente: avvolge ``CancelloUscite.lascia_uscire`` e
``CancelloUscite._emit`` (il modulo di produzione) chiamando sempre il vero, e
registra cosa e' successo. File ASCII-only, commenti in italiano.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

SCENARIO_MANUALI = "uscite-manuali"
SCENARIO_FIRMATE = "uscite-manuali-firmate"
SCENARI: Tuple[str, ...] = (SCENARIO_MANUALI, SCENARIO_FIRMATE)

#: dopo quanti secondi di tempo di mercato il banco firma una proposta
#: (DICHIARATO: l'utente che legge la scheda e preme "approva")
FIRMA_DOPO_S = 5.0
#: la finestra, in tempo di mercato, in cui si cercano gli ordini dell'uscita
#: firmata (la chiusura puo' partire al book dopo, o inseguire il prezzo)
FINESTRA_ORDINI_S = 5.0
#: tolleranza sull'importo (centesimo)
TOLLERANZA_IMPORTO = 0.011
#: sotto questa cifra il resto di un'uscita non si piazza per regola GIA'
#: esistente dello scalper tennis (`TennisScalperStrategy._place_exact`,
#: `rest < 0.05` -> `min_bet_skip`). UF2 lo scusa SOLO se il bot stesso lo ha
#: dichiarato (callable `resto_non_piazzabile`), mai per tolleranza.
SOGLIA_RESTO_NON_PIAZZABILE = 0.05


def e_parcheggio(ordine: Any) -> bool:
    """Il gradino 1 del place-and-trim: l'ordine a quota NON abbinabile
    (`trading.submin.initial_place_price`: BACK 1000, LAY 1,01)."""
    from ..trading.submin import initial_place_price

    lato = _lato(getattr(ordine, "side", ""))
    if lato not in ("BACK", "LAY"):
        return False
    try:
        prezzo = float(getattr(getattr(ordine, "order_type", None), "price", 0.0) or 0.0)
    except (TypeError, ValueError):
        return False
    return abs(prezzo - initial_place_price(lato.lower())) < 1e-9

#: i motivi di TRADING che passano dal cancello (l'unione di quelli dei bot:
#: swing target/stop/time, pro scaglione/target/stop/strutturale, flb green,
#: scalper tennis e calcio target/stop/timeout/scratch, sniper
#: target/stop/timeout). Tutto il resto e' una protezione e non ci passa.
MOTIVI_DI_TRADING: Tuple[str, ...] = ("target", "stop", "time", "timeout", "scratch",
                                      "strutturale", "scaglione", "green")

#: le chiavi comuni di ogni proposta (``uscite_proposte.proposta_di`` + cancello)
CHIAVI_PROPOSTA: Tuple[str, ...] = (
    "bot", "motivo", "urgente", "market_id", "selection_id", "lato_ingresso",
    "prezzo", "lato_chiusura", "size_chiusura", "se_chiudi", "se_vince", "se_perde",
    "chiave", "decided_at")

#: i NUMERI che l'utente deve vedere per decidere: presenti E valorizzati
#: (una proposta con `size_chiusura=None` o `se_chiudi=None` non si firma a
#: occhi aperti). `urgente` e' un booleano sempre calcolato: non e' un numero.
CHIAVI_NUMERI_OBBLIGATORI: Tuple[str, ...] = tuple(
    k for k in CHIAVI_PROPOSTA if k != "urgente")


#: i numeri della CHIUSURA: gli unici che possono mancare, e SOLO se la
#: proposta dichiara perche' (`numeri_non_disponibili`: nessun prezzo di
#: chiusura mai visto per quella selezione). 29/09, replay dello scalper tennis.
CHIAVI_NUMERI_CHIUSURA: Tuple[str, ...] = ("prezzo", "lato_chiusura",
                                           "size_chiusura", "se_chiudi")


def difetti_proposta(p: Dict[str, Any]) -> List[str]:
    """Le chiavi obbligatorie assenti o senza valore, una per una (UM2, Z4).
    Unica eccezione: i numeri della chiusura senza valore in una proposta che
    DICHIARA `numeri_non_disponibili` con un motivo (stringa non vuota)."""
    out = ["%s assente" % k for k in CHIAVI_PROPOSTA if k not in p]
    motivo = p.get("numeri_non_disponibili")
    dichiarato = isinstance(motivo, str) and bool(motivo.strip())
    out += ["%s senza valore" % k for k in CHIAVI_NUMERI_OBBLIGATORI
            if k in p and p.get(k) is None
            and not (dichiarato and k in CHIAVI_NUMERI_CHIUSURA)]
    # 29/09 (CANTIERE U): un importo di chiusura a 0,00 (o negativo) NON e' un
    # numero presente: la scheda dice "chiudi 0,00 EUR" e alla firma non parte
    # niente (replay 35794049 del tennis_pro, scenario firmato). Si tratta
    # come un numero mancante, senza eccezioni (nemmeno `numeri_non_disponibili`:
    # quella dichiara un numero ASSENTE, non un numero falso).
    size = p.get("size_chiusura")
    if size is not None:
        try:
            if float(size) <= 0.0:
                out.append("size_chiusura a zero (%r): nessun importo da chiudere"
                           % (size,))
        except (TypeError, ValueError):
            out.append("size_chiusura non numerica (%r)" % (size,))
    return out

DESCRIZIONE_MANUALI = (
    "uscite MANUALI (interruttore spento, il default di produzione dopo ogni "
    "avvio) e nessuna firma: ogni uscita di trading deve restare una PROPOSTA, "
    "le protezioni devono scattare da sole (UM1-UM4)")
DESCRIZIONE_FIRMATE = (
    "uscite MANUALI e il banco FIRMA ogni proposta dopo %d s di mercato, per la "
    "via di produzione (params.uscite_approvate, riletta al battito): l'uscita "
    "firmata parte UNA volta, all'importo esatto, e mai un'uscita diversa "
    "(UM1-UM4, UF1-UF3)" % int(FIRMA_DOPO_S))

_CONTROLLI: List[Tuple[str, str]] = [
    ("UM1", "a uscite manuali nessuna uscita di trading parte senza la firma dell'utente"),
    ("UM2", "ogni uscita decisa dalla strategia diventa una proposta coi numeri"),
    ("UM3", "le protezioni non passano dal cancello e scattano da sole"),
    ("UM4", "una proposta la cui condizione cade sparisce, con la sua firma"),
    ("UF1", "una firma fa partire l'uscita una volta sola"),
    ("UF2", "l'uscita firmata parte all'importo esatto della proposta di adesso"),
    ("UF3", "una firma non esegue mai un'uscita diversa da quella firmata"),
]


def elenco_controlli(scenario: Optional[str] = None) -> List[Tuple[str, str]]:
    if scenario == SCENARIO_MANUALI:
        return [c for c in _CONTROLLI if c[0].startswith("UM")]
    return list(_CONTROLLI)


def regola(codice: str) -> str:
    return dict(_CONTROLLI).get(codice, codice)


def istante_iso(t_s: float) -> str:
    """La firma come la scrive la RPC (``to_jsonb(now())``: ISO con fuso)."""
    return datetime.fromtimestamp(float(t_s), tz=timezone.utc).isoformat()


def _f(v: Any) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _lato(v: Any) -> str:
    s = str(getattr(v, "value", v) or "").upper()
    return s


class Osservatore:
    """Guarda il cancello delle uscite di produzione durante un replay.

    ``strategie()``: le strategie vive (quelle con ``cancello_uscite``).
    ``ordini_di(s)``: gli ordini flumine di una strategia (dal blotter).
    ``firma(chiave, istante_iso)``: scrive la firma per la via di produzione
    (solo nello scenario firmato).
    ``piatto_a_fine()``: None = piatto o dichiarato; stringa = il difetto;
    la funzione assente = il bot non ha una fine finestra (UM3b non si applica).
    """

    def __init__(self, scenario: str, *,
                 strategie: Callable[[], Sequence[Any]],
                 ordini_di: Callable[[Any], Sequence[Any]],
                 firma: Optional[Callable[[str, str], None]] = None,
                 piatto_a_fine: Optional[Callable[[], Optional[str]]] = None,
                 ruolo: Optional[Callable[[Any], Optional[str]]] = None,
                 resto_non_piazzabile: Optional[Callable[[Any, Any, str, float], bool]]
                 = None,
                 soglia_resto: float = SOGLIA_RESTO_NON_PIAZZABILE) -> None:
        self.scenario = scenario
        # 04/10 (decisione dell'utente «il residuo resta ricordato e lo chiudo
        # io», scalper calcio): la soglia sotto cui un resto DICHIARATO dal bot
        # (`min_bet_skip`) non accusa UF2. Di serie 0,05 (tennis invariato); lo
        # scalper calcio passa l'importo finale minimo del place-and-trim (0,50,
        # `minimi_it`): sotto, Betfair .it non accetta nessun ordine. Senza la
        # dichiarazione del bot resta violazione.
        self._soglia_resto = float(soglia_resto)
        self.firmate = scenario == SCENARIO_FIRMATE
        self._strategie = strategie
        self._ordini_di = ordini_di
        self._firma = firma
        self._piatto_a_fine = piatto_a_fine
        # N3 UF2 (29/09): la credenza del bot sul RUOLO di un ordine
        # ("ingresso"/"uscita"/None) e il resto che il bot dichiara non piazzabile
        self._ruolo = ruolo
        self._resto_non_piazzabile = resto_non_piazzabile
        self.ora_ms = 0
        self.violazioni: List[Tuple[str, str, str, str]] = []
        self.sollecitati: Dict[str, int] = {}
        self.decisioni = 0
        self.proposte_nate = 0
        self.decadute = 0
        self.firme_date = 0
        self.eseguite = 0
        self.non_giudicabili: List[str] = []
        self.eventi: List[Tuple[int, str, Dict[str, Any]]] = []
        # (id cancello, chiave) -> la proposta che il banco ha firmato
        self._firmate: Dict[Tuple[int, str], Dict[str, Any]] = {}
        # (id cancello, chiave, firma) gia' eseguite (UF1)
        self._usate: Dict[Tuple[int, str, float], int] = {}
        self._pendenti: List[Dict[str, Any]] = []
        self._cancelli: Dict[int, Any] = {}

    # ---------------------------------------------------------------- utilita'
    def _sollecita(self, codice: str) -> None:
        self.sollecitati[codice] = self.sollecitati.get(codice, 0) + 1

    def _viola(self, codice: str, dettaglio: str) -> None:
        self.violazioni.append((codice, regola(codice), dettaglio,
                                istante_iso(self.ora_ms / 1000.0) if self.ora_ms else ""))

    def _strategia_di(self, canc: Any) -> Optional[Any]:
        for s in self._strategie() or ():
            if getattr(s, "cancello_uscite", None) is canc:
                return s
        return None

    def _ids(self, s: Any) -> set:
        try:
            return {str(getattr(o, "id", "")) for o in (self._ordini_di(s) or ())}
        except Exception:  # noqa: BLE001 - blotter illeggibile: nessun ordine
            return set()

    # ------------------------------------------------------------ l'avvolgere
    @contextmanager
    def attivo(self) -> Iterator["Osservatore"]:
        from .. import uscite_proposte as UP

        classe = UP.CancelloUscite
        vero_lascia = classe.lascia_uscire
        vero_emit = classe._emit
        oss = self

        def _lascia(canc: Any, *, automatiche: bool, chiave: str, now_s: float,
                    proposta: Dict[str, Any]) -> bool:
            with canc._lock:
                viva_prima = dict(canc.proposte.get(chiave) or {})
                firma_prima = canc.approvate.get(chiave)
            ids_prima = None
            if not automatiche and firma_prima is not None:
                s = oss._strategia_di(canc)
                ids_prima = (s, oss._ids(s)) if s is not None else None
            ok = vero_lascia(canc, automatiche=automatiche, chiave=chiave,
                             now_s=now_s, proposta=proposta)
            try:
                oss._dopo_decisione(canc, automatiche, chiave, now_s, proposta or {},
                                    ok, viva_prima, firma_prima, ids_prima)
            except Exception as ex:  # noqa: BLE001 - un controllo rotto E' un referto
                oss._viola("UM1", "osservatore esploso: %s: %s" % (type(ex).__name__, ex))
            return ok

        def _emit(canc: Any, ev: str, **p: Any) -> None:
            try:
                oss._evento(canc, ev, p)
            except Exception as ex:  # noqa: BLE001
                oss._viola("UM4", "osservatore esploso: %s: %s" % (type(ex).__name__, ex))
            vero_emit(canc, ev, **p)

        classe.lascia_uscire = _lascia  # type: ignore[assignment]
        classe._emit = _emit  # type: ignore[assignment]
        try:
            yield self
        finally:
            classe.lascia_uscire = vero_lascia  # type: ignore[assignment]
            classe._emit = vero_emit  # type: ignore[assignment]

    # ------------------------------------------------------------ i controlli
    def _dopo_decisione(self, canc: Any, automatiche: bool, chiave: str, now_s: float,
                        proposta: Dict[str, Any], ok: bool, viva_prima: Dict[str, Any],
                        firma_prima: Optional[float],
                        ids_prima: Optional[Tuple[Any, set]]) -> None:
        self._cancelli[id(canc)] = canc
        self.decisioni += 1
        motivo = str(proposta.get("motivo") or "")
        # UM1 - l'interruttore resta spento e niente parte senza firma
        self._sollecita("UM1")
        if automatiche:
            self._viola("UM1", "cancello chiamato con le uscite AUTOMATICHE in uno "
                               "scenario manuale: %s" % chiave)
        elif ok and (firma_prima is None or not self.firmate):
            self._viola("UM1", "uscita di trading ESEGUITA senza firma: %s (%s)"
                        % (chiave, motivo))
        # UM3a - dal cancello passano solo uscite di trading
        self._sollecita("UM3")
        if motivo not in MOTIVI_DI_TRADING or not chiave.endswith(motivo):
            self._viola("UM3", "motivo %r (chiave %s) non e' un'uscita di trading: una "
                               "protezione non deve passare dal cancello" % (motivo, chiave))
        if not ok:
            # UM2 - la decisione e' una proposta viva, nata con il suo evento
            self._sollecita("UM2")
            with canc._lock:
                viva = dict(canc.proposte.get(chiave) or {})
            mancano = difetti_proposta(viva)
            if not viva:
                self._viola("UM2", "uscita decisa (%s) senza proposta viva" % chiave)
            elif mancano:
                self._viola("UM2", "proposta %s senza i numeri: %s" % (chiave, mancano))
            elif not any(ev == "uscita_proposta" and i == id(canc)
                         and p.get("chiave") == chiave for i, ev, p in self.eventi):
                self._viola("UM2", "proposta %s mai annunciata (uscita_proposta)" % chiave)
            if not viva_prima:
                self.proposte_nate += 1
            return
        if automatiche:
            return
        # l'uscita FIRMATA e' partita
        self.eseguite += 1
        self._sollecita("UF1")
        self._sollecita("UF3")
        vista = self._firmate.get((id(canc), chiave))
        if vista is None or firma_prima is None:
            self._viola("UF3", "eseguita %s: il banco non l'ha firmata" % chiave)
            return
        usata = (id(canc), chiave, float(firma_prima))
        self._usate[usata] = self._usate.get(usata, 0) + 1
        if self._usate[usata] > 1:
            self._viola("UF1", "la firma di %s ha fatto partire l'uscita %d volte"
                        % (chiave, self._usate[usata]))
        diversi = []
        if _f(vista.get("decided_at")) != _f(viva_prima.get("decided_at")):
            diversi.append("proposta nata %s, firmata quella nata %s"
                           % (viva_prima.get("decided_at"), vista.get("decided_at")))
        for k in ("motivo", "selection_id", "lato_chiusura", "market_id"):
            if str(vista.get(k)) != str(proposta.get(k)):
                diversi.append("%s firmato %r, eseguito %r" % (k, vista.get(k), proposta.get(k)))
        if diversi:
            self._viola("UF3", "%s: %s" % (chiave, "; ".join(diversi)))
        if ids_prima is None:
            self.non_giudicabili.append("UF2 %s: strategia non trovata" % chiave)
            return
        # S3 (29/09, reperto scalper 35797769: target firmata 24,42 eseguita
        # esatta, poi SCRATCH firmato 25,00 eseguito 9 s dopo sulla stessa
        # posizione): ogni uscita firmata conta SOLO i propri ordini. La finestra
        # di un'uscita ancora da giudicare si CHIUDE quando si esegue la firma
        # successiva sulla stessa posizione (stesso mercato e selezione): gli
        # ordini nati da li' in poi sono dell'uscita nuova, che ha la sua
        # proposta e il suo giudizio.
        for prec in self._pendenti:
            if (prec.get("fino_ids") is None
                    and str(prec.get("market_id")) == str(proposta.get("market_id"))
                    and str(prec.get("selection_id")) == str(proposta.get("selection_id"))):
                prec["fino_ids"] = set(ids_prima[1])
                prec["superata_da"] = chiave
        self._pendenti.append({
            "strategia": ids_prima[0], "ids_prima": ids_prima[1], "chiave": chiave,
            "market_id": proposta.get("market_id"),
            "selection_id": proposta.get("selection_id"),
            "lato": _lato(proposta.get("lato_chiusura")),
            "size": _f(proposta.get("size_chiusura")), "da_ms": self.ora_ms,
            "fino_ids": None, "superata_da": None})

    def _evento(self, canc: Any, ev: str, p: Dict[str, Any]) -> None:
        self._cancelli[id(canc)] = canc
        self.eventi.append((id(canc), ev, dict(p)))
        if ev == "uscita_proposta_decaduta":
            self.decadute += 1
            self._sollecita("UM4")
            k = str(p.get("chiave") or "")
            with canc._lock:
                resta = k in canc.proposte
                firma = k in canc.approvate
            if resta or firma:
                self._viola("UM4", "proposta %s decaduta ma ancora %s"
                            % (k, "viva" if resta else "firmata"))

    # --------------------------------------------------------------- il giro
    def giro(self, ora_ms: int, *, fine: bool = False) -> None:
        """Una volta per giro del banco (tempo di mercato)."""
        if ora_ms:
            self.ora_ms = int(ora_ms)
        ora_s = self.ora_ms / 1000.0
        # UM4b - nessuna proposta viva di una posizione che il bot non segue piu'
        # (la tiene la strategia viva: le strategie ritirate non contano)
        if self.firmate and self._firma is not None and not fine:
            for s in list(self._strategie() or ()):
                canc = getattr(s, "cancello_uscite", None)
                if canc is None:
                    continue
                self._cancelli[id(canc)] = canc
                for p in canc.vive():
                    k = str(p.get("chiave") or "")
                    nata = _f(p.get("decided_at"))
                    if not k or nata is None or ora_s - nata < FIRMA_DOPO_S:
                        continue
                    gia = self._firmate.get((id(canc), k))
                    if gia is not None and _f(gia.get("decided_at")) == nata:
                        continue
                    self._firmate[(id(canc), k)] = dict(p)
                    self.firme_date += 1
                    self._firma(k, istante_iso(ora_s))
        self._giudica_importi(fine)
        if fine:
            self._fine()

    def _ordini_uscita(self, pend: Dict[str, Any]) -> List[Any]:
        """Gli ordini dell'uscita firmata.

        Finestra: gli ordini NATI nei ``FINESTRA_ORDINI_S`` dopo la firma (gli
        id si congelano alla chiusura della finestra), di quella selezione e di
        quel lato, TOLTI gli ordini che la credenza del bot dice di INGRESSO
        (un nuovo ciclo del maker non e' l'uscita: 29/09, replay dello scalper
        tennis). Piu' i RIMPIAZZI della catena place-and-trim nati dopo (il
        gradino 3 di un parcheggio della finestra: stesso Trade, ordine
        successivo, stesso lato), come li riconosce B8 dopo D2."""
        try:
            ordini = list(self._ordini_di(pend["strategia"]) or ())
        except Exception:  # noqa: BLE001
            ordini = []
        if pend.get("congelati") is None:
            pend["congelati"] = {
                str(getattr(o, "id", "")) for o in ordini
                if str(getattr(o, "id", "")) not in pend["ids_prima"]
                and str(getattr(o, "selection_id", "")) == str(pend["selection_id"])
                and (not pend["lato"] or _lato(getattr(o, "side", "")) == pend["lato"])
                and not self._e_ingresso(o)
                # S3: il RIMPIAZZO di un ordine nato prima della firma (gradino 3
                # della catena di un'uscita precedente) e' di quell'uscita
                and not self._rimpiazzo_di_prima(o, pend["ids_prima"])}
        fino = pend.get("fino_ids")
        # S3: la finestra si chiude alla firma successiva eseguita sulla stessa
        # posizione: gli ordini nati dopo sono dell'uscita successiva
        scelti = [o for o in ordini if str(getattr(o, "id", "")) in pend["congelati"]
                  and (fino is None or str(getattr(o, "id", "")) in fino)]
        for p in list(scelti):
            if not e_parcheggio(p):
                continue
            tr = list(getattr(getattr(p, "trade", None), "orders", None) or [])
            idx = next((i for i, o in enumerate(tr) if o is p), None)
            for o in (tr[idx + 1:] if idx is not None else []):
                if _lato(getattr(o, "side", "")) == _lato(getattr(p, "side", "")) \
                        and all(o is not q for q in scelti):
                    scelti.append(o)
        return scelti

    @staticmethod
    def _rimpiazzo_di_prima(o: Any, ids_prima: set) -> bool:
        """S3: ``o`` e' il rimpiazzo (non il primo ordine del suo Trade) di un
        ordine gia' esistente prima della firma: appartiene alla catena
        place-and-trim di un'uscita precedente, non a questa."""
        tr = list(getattr(getattr(o, "trade", None), "orders", None) or [])
        return bool(tr) and tr[0] is not o and str(getattr(tr[0], "id", "")) in ids_prima

    def _e_ingresso(self, o: Any) -> bool:
        if self._ruolo is None:
            return False
        try:
            return self._ruolo(o) == "ingresso"
        except Exception:  # noqa: BLE001 - credenza illeggibile: si conta
            return False

    def _giudica_importi(self, fine: bool) -> None:
        restano = []
        for pend in self._pendenti:
            if not fine and self.ora_ms - pend["da_ms"] < FINESTRA_ORDINI_S * 1000:
                restano.append(pend)
                continue
            uscita = self._ordini_uscita(pend)
            # la catena place-and-trim ancora in corso (parcheggio vivo a quota
            # NON abbinabile): si giudica quando e' finita (o a fine replay)
            if not fine and any(e_parcheggio(o) and
                                (_f(getattr(o, "size_remaining", 0.0)) or 0.0) > 0
                                for o in uscita):
                restano.append(pend)
                continue
            self._sollecita("UF2")
            # L'IMPORTO FINALE A QUOTA ABBINABILE: abbinato di tutto + residuo
            # vivo dei soli ordini NON di parcheggio (il parcheggio a 1000/1,01
            # non e' un importo d'uscita: e' il gradino 1 del place-and-trim).
            if pend.get("superata_da"):
                # S3: un'uscita SUPERATA da un'altra uscita firmata sulla stessa
                # posizione (lo scratch firmato ritira la close a target firmata:
                # condotta di sempre, anche in automatico) non puo' finire:
                # i suoi ordini sono stati ritirati dall'uscita nuova. Si giudica
                # l'importo che ha PIAZZATO a quota abbinabile (size chiesta
                # degli ordini non di parcheggio, rimpiazzi compresi) piu'
                # l'eventuale abbinato di un parcheggio: la stessa regola
                # dell'importo esatto, contro la SUA proposta.
                eff = round(sum((_f(getattr(o, "size_matched", 0.0)) or 0.0)
                                if e_parcheggio(o) else
                                (_f(getattr(getattr(o, "order_type", None), "size", 0.0))
                                 or 0.0)
                                for o in uscita), 2)
            else:
                eff = round(sum((_f(getattr(o, "size_matched", 0.0)) or 0.0)
                                + (0.0 if e_parcheggio(o) else
                                   (_f(getattr(o, "size_remaining", 0.0)) or 0.0))
                                for o in uscita), 2)
            size = pend["size"]
            if size is None:
                self.non_giudicabili.append("UF2 %s: la proposta non porta size_chiusura"
                                            % pend["chiave"])
                continue
            manca = round(size - eff, 2)
            if abs(eff - size) <= TOLLERANZA_IMPORTO:
                continue
            if 0 < manca < self._soglia_resto and self._resto_dichiarato(
                    pend["strategia"], pend["selection_id"], pend["lato"], manca):
                # il resto che il BOT stesso ha dichiarato non piazzabile (regola
                # gia' esistente dello scalper tennis: resto < 0,05 dopo la parte
                # diretta, `min_bet_skip`): non e' l'incrocio N x D2. Dichiarato.
                self.non_giudicabili.append(
                    "UF2 %s: proposta %.2f, uscita %.2f; resto %.2f dichiarato NON "
                    "piazzabile dal bot (min_bet_skip, regola esistente)"
                    % (pend["chiave"], size, eff, manca))
                continue
            if not uscita:
                self._viola("UF2", "uscita firmata %s partita ma nessun ordine %s sulla "
                                   "selezione %s entro %d s (proposta %.2f)"
                            % (pend["chiave"], pend["lato"], pend["selection_id"],
                               int(FINESTRA_ORDINI_S), size))
                continue
            self._viola("UF2", "uscita firmata %s: proposta %.2f, uscita a quota "
                               "abbinabile %.2f (abbinato + residuo, parcheggi esclusi)"
                        % (pend["chiave"], size, eff))
        self._pendenti = restano

    def _resto_dichiarato(self, s: Any, sel: Any, lato: str, resto: float) -> bool:
        if self._resto_non_piazzabile is None:
            return False
        try:
            return bool(self._resto_non_piazzabile(s, sel, lato, resto))
        except Exception:  # noqa: BLE001
            return False

    def _fine(self) -> None:
        if self._piatto_a_fine is None:
            self.non_giudicabili.append(
                "UM3b: il bot non ha una fine finestra con force-flat (tiene fino a "
                "fine mercato per progetto): le protezioni restano quelle dei suoi "
                "controlli (Chiudi, freno, fine mercato)")
            return
        self._sollecita("UM3")
        difetto = self._piatto_a_fine()
        if difetto:
            self._viola("UM3", "a fine sessione, a uscite manuali: %s" % difetto)

    # ------------------------------------------------------------- referto
    def riepilogo(self) -> str:
        return ("USCITE MANUALI (%s): decisioni %d, proposte nate %d, decadute %d, "
                "firme del banco %d, uscite firmate eseguite %d; non giudicabili: %s"
                % (self.scenario, self.decisioni, self.proposte_nate, self.decadute,
                   self.firme_date, self.eseguite,
                   "; ".join(self.non_giudicabili[:6]) or "nessuna"))
