"""flusso_prezzi.py - I PREZZI DI UNA PARTITA SONO VIVI? (cantiere J, 28/09/2026)

Decisione dell'utente (28/09, testuale): "il bot deve sapere se il flusso dati e'
interrotto, non puo' operare a caso solo perche' vede il punteggio". Regola: se i
PREZZI di una partita non sono vivi, nessun bot apre e nessun bot chiude a mercato
su quella partita basandosi su quei prezzi.

Il fatto del 26/09 (``AUDIT_2026-09-25/FIX_C_RESILIENZA_RETE_2026-09-26.md`` par. 7.1):
dalle 10:42 alle 14:47Z lo stream dello scanner era caduto e anche il REST non
rispondeva (sessione scaduta), ma le righe di ``safe_strategy_scan`` venivano
riscritte a ogni cambio di punteggio: ``updated_at`` fresco, quote vecchie di ore.
``odds_ts_ms`` e' l'istante dell'ultimo CAMBIO di prezzo, non dell'ultimo dato
ricevuto, e i veti dei bot guardavano l'eta' della riga e il battito dello
scanner: nessuno dei due dice se i prezzi arrivano ancora.

CHI PRODUCE IL SEGNALE: lo scanner (``safe_strategy/service.py``), l'unico che sa
da quale fonte arriva ogni mercato. Per ogni mercato tiene l'ultima CONFERMA che il
prezzo in mano e' quello corrente:
  * STREAM: un book con prezzi ricevuto sulla connessione ATTUALE (l'immagine
    iniziale o un delta) e, dopo, ogni messaggio della stessa connessione,
    heartbeat compresi. La Exchange Stream API manda solo i CAMBIAMENTI: un
    mercato fermo non manda niente, e la connessione vive lo dice con un
    heartbeat (``ct=HEARTBEAT``) a ogni ``heartbeatMs`` senza dati (noi 5000 ms,
    limiti 500-30000). Un mercato fermo su una connessione viva e' quindi un dato
    VIVO e invariato. Un ``status: 503`` sul messaggio vuol dire, da schema
    ufficiale, "downstream services are experiencing latencies": in quel caso lo
    stream NON conferma niente.
  * REST (ripiego): l'istante della risposta ``listMarketBook`` che conteneva
    quel mercato con prezzi.
  Un mercato e' VIVO se l'ultima conferma ha meno di una soglia che dipende dalla
  cadenza del ripiego REST (sotto), e se l'ultimo book ricevuto aveva prezzi (un
  book vuoto lascia nella riga le quote vecchie: non sono prezzi operabili).
  Documentazione: schema ufficiale ESA
  https://github.com/betfair/stream-api-sample-code/blob/master/ESASwaggerSchema.json
  (``heartbeatMs``, ``conflateMs``, ``ct``, ``pt``, ``clk``, ``status``) e la
  pagina "Exchange Stream API" del portale sviluppatori Betfair
  (https://docs.developer.betfair.com/ -> Exchange Stream API).

DOVE VIAGGIA (nessuna scrittura in piu' a regime):
  * nella RIGA di scan, chiave ``flusso`` (additiva): ``{"vivo", "motivo",
    "dal_ms", "mercati_fermi"}``. Cambia SOLO quando un mercato passa da vivo a
    fermo o viceversa: la riga si riscrive una volta per passaggio, e sul canale
    al millisecondo (47336) la stessa riga esce nello stesso istante;
  * nello STATO dello scanner (``safe_strategy_status``, riga gia' scritta ogni
    10 s), chiave ``flusso``: ``{"calcolato_ms", "eventi_fermi", ...}``. Serve a
    un caso che la riga non puo' coprire: il giro dello scanner BLOCCATO (il
    battito lo scrive un altro thread): ``calcolato_ms`` vecchio = nessun prezzo
    e' confermato.

CHI LO LEGGE: tutti i bot, SOLO attraverso ``valuta`` qui sotto, dentro la loro
funzione di freschezza. Il modulo e' puro: nessun I/O, nessuna dipendenza.

Dato ASSENTE (riga di uno scanner precedente, finto di un test vecchio): il modulo
risponde "non noto" e NON veta; i veti gia' esistenti dei bot restano gli stessi.
Lo scanner nuovo pubblica la chiave su OGNI riga, quindi l'assenza in esercizio
dura al massimo fino al primo giro dopo il riavvio dell'app.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

# chiave nel payload della riga e nello stato dello scanner
CHIAVE = "flusso"

# motivi (valori possibili di ``flusso.motivo`` e di ``Esito.motivo``)
MOTIVO_INTERROTTO = "flusso_interrotto"     # nessuna conferma da oltre la soglia
MOTIVO_MAI_RICEVUTO = "mai_ricevuto"        # nessun book da quando e' rilevante
MOTIVO_SENZA_PREZZI = "senza_prezzi"        # ultimo book senza prezzi (vuoto/sospeso)
MOTIVO_LATENTE = "stream_latente"           # stream con status 503, nessun'altra fonte
MOTIVO_SCANNER_BLOCCATO = "scanner_bloccato"  # giro dello scanner fermo (stato)
MOTIVO_MERCATO_FERMO = "mercato_fermo"      # un mercato usato dalla decisione e' fermo
# riga SENZA la chiave ``flusso`` mentre lo stato dice che lo scanner e' quello
# nuovo (che la scrive su OGNI riga): non e' una riga dello scanner nuovo
MOTIVO_NON_DICHIARATO = "flusso_non_dichiarato"

MOTIVI = (MOTIVO_INTERROTTO, MOTIVO_MAI_RICEVUTO, MOTIVO_SENZA_PREZZI, MOTIVO_LATENTE,
          MOTIVO_SCANNER_BLOCCATO, MOTIVO_MERCATO_FERMO, MOTIVO_NON_DICHIARATO)

# Il giro dello scanner ricalcola il flusso ogni ~0,5-2 s; il suo stato si scrive
# ogni 10 s. Oltre questa eta' del calcolo (misurata dal bot sull'orologio del PC,
# lo stesso dello scanner) nessun prezzo e' da considerare confermato.
STATO_CALCOLO_MAX_S = 45.0

# Soglie dello SCANNER (quanto puo' mancare una conferma prima di dire "fermo").
# Devono stare sopra la cadenza del ripiego REST (``scanner.books_period_*``:
# calcio 10 s dal 40', 20 s in gioco, 60 s prima; tennis 10 s in gioco, 60 s
# prima), altrimenti il ripiego REST - che E' un flusso vivo - farebbe
# lampeggiare il segnale fra un poll e l'altro. Con lo stream vivo la conferma
# arriva almeno ogni heartbeat (5 s).
SOGLIA_INPLAY_S = {"calcio": 45.0, "tennis": 25.0}
SOGLIA_PRE_S = 125.0
# socket dello stream: vivo se l'ultimo messaggio (heartbeat compreso) ha meno di
# tre heartbeat (3 x 5000 ms)
SOCKET_MAX_S = 15.0

_TESTI = {
    MOTIVO_INTERROTTO: "flusso prezzi INTERROTTO: nessun dato ricevuto da oltre la soglia",
    MOTIVO_MAI_RICEVUTO: "prezzi mai ricevuti su questo mercato",
    MOTIVO_SENZA_PREZZI: "ultimo book senza prezzi (mercato vuoto o sospeso)",
    MOTIVO_LATENTE: "stream Betfair in latenza (status 503) e nessun'altra fonte",
    MOTIVO_SCANNER_BLOCCATO: "giro dello scanner fermo: nessun prezzo confermato",
    MOTIVO_MERCATO_FERMO: "un mercato usato dalla decisione ha il flusso fermo",
    MOTIVO_NON_DICHIARATO: ("riga senza il flusso dichiarato mentre lo scanner lo dichiara: "
                            "prezzi non confermati"),
}


@dataclass(frozen=True)
class Esito:
    """Risposta di ``valuta``. ``noto`` e' False quando il dato non c'e' (riga
    di uno scanner precedente): in quel caso ``vivo`` e' True per non cambiare
    la condotta di prima, e chi vuole lo puo' dire."""

    vivo: bool
    motivo: Optional[str] = None
    testo: str = ""
    noto: bool = True
    mercati: tuple = ()

    @property
    def fermo(self) -> bool:
        return not self.vivo


VIVO = Esito(True, None, "prezzi vivi", True)
NON_NOTO = Esito(True, None, "flusso non dichiarato dalla riga (scanner precedente)", False)


def testo_motivo(motivo: Optional[str]) -> str:
    return _TESTI.get(str(motivo or ""), f"flusso prezzi non vivo ({motivo})")


def _ora_ms() -> int:
    return int(time.time() * 1000)


def blocco_riga(payload: Optional[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    """Il blocco ``flusso`` della riga, o None se la riga non lo porta."""
    if not isinstance(payload, Mapping):
        return None
    blk = payload.get(CHIAVE)
    return blk if isinstance(blk, Mapping) else None


def valuta_riga(payload: Optional[Mapping[str, Any]],
                mercati: Optional[Iterable[Any]] = None,
                adesso_ms: Optional[int] = None) -> Esito:
    """I prezzi della riga sono vivi?

    ``mercati``: i market_id su cui la decisione si basa. None = il MATCH_ODDS
    della partita (``flusso.vivo``). Con un elenco: il MATCH_ODDS conta solo se e'
    nell'elenco, gli altri mercati sono vivi se NON sono in ``mercati_fermi``.
    """
    blk = blocco_riga(payload)
    if blk is None:
        return NON_NOTO
    fermi = {str(m) for m in (blk.get("mercati_fermi") or [])}
    mo = str((payload or {}).get("mo_market_id") or "")
    if mercati is None:
        vivo = blk.get("vivo")
        if vivo is True:
            return VIVO
        motivo = str(blk.get("motivo") or MOTIVO_INTERROTTO)
        return Esito(False, motivo, _con_eta(testo_motivo(motivo), blk, adesso_ms),
                     True, (mo,) if mo else ())
    usati = [str(m) for m in mercati if m is not None and str(m)]
    fermi_usati = [m for m in usati if m in fermi]
    if mo and mo in usati and blk.get("vivo") is not True and mo not in fermi_usati:
        fermi_usati.insert(0, mo)
    if not fermi_usati:
        return VIVO
    motivo = (str(blk.get("motivo") or MOTIVO_INTERROTTO) if mo in fermi_usati
              else MOTIVO_MERCATO_FERMO)
    testo = testo_motivo(motivo) + " (" + ", ".join(fermi_usati[:4]) + ")"
    return Esito(False, motivo, _con_eta(testo, blk, adesso_ms), True, tuple(fermi_usati))


def _con_eta(testo: str, blk: Mapping[str, Any], adesso_ms: Optional[int]) -> str:
    dal = blk.get("dal_ms")
    if isinstance(dal, (int, float)) and dal > 0:
        eta = ((adesso_ms if adesso_ms is not None else _ora_ms()) - int(dal)) / 1000.0
        if eta >= 0:
            return f"{testo}; da {eta:.0f} s"
    return testo


def valuta_stato(stato: Optional[Mapping[str, Any]], event_id: Any = None,
                 adesso_ms: Optional[int] = None) -> Esito:
    """Lo STATO dello scanner conferma i prezzi di questa partita?

    Due verifiche: il calcolo del flusso non e' piu' vecchio di
    ``STATO_CALCOLO_MAX_S`` (giro dello scanner bloccato) e la partita non e'
    fra ``eventi_fermi``. Stato senza la chiave = non noto (nessun veto)."""
    if not isinstance(stato, Mapping):
        return NON_NOTO
    blk = stato.get(CHIAVE)
    if not isinstance(blk, Mapping):
        return NON_NOTO
    calc = blk.get("calcolato_ms")
    adesso = adesso_ms if adesso_ms is not None else _ora_ms()
    if isinstance(calc, (int, float)) and calc > 0:
        eta = (adesso - int(calc)) / 1000.0
        if eta > STATO_CALCOLO_MAX_S:
            return Esito(False, MOTIVO_SCANNER_BLOCCATO,
                         f"{testo_motivo(MOTIVO_SCANNER_BLOCCATO)}; ultimo calcolo {eta:.0f} s fa")
    else:
        return Esito(False, MOTIVO_SCANNER_BLOCCATO, testo_motivo(MOTIVO_SCANNER_BLOCCATO))
    if event_id is not None:
        fermi = blk.get("eventi_fermi")
        if isinstance(fermi, Mapping) and str(event_id) in fermi:
            motivo = str(fermi.get(str(event_id)) or MOTIVO_INTERROTTO)
            return Esito(False, motivo, testo_motivo(motivo) + " (stato dello scanner)")
    return VIVO


def valuta(payload: Optional[Mapping[str, Any]] = None,
           stato: Optional[Mapping[str, Any]] = None,
           event_id: Any = None,
           mercati: Optional[Iterable[Any]] = None,
           adesso_ms: Optional[int] = None) -> Esito:
    """Punto d'ingresso UNICO per i bot: prima lo stato (giro bloccato), poi la
    riga (per mercato). Il primo "fermo" vince. Con ``mercati`` si valuta solo il
    blocco della riga (lo stato conosce l'evento, non il mercato) oltre al giro."""
    if stato is not None:
        es = valuta_stato(stato, None if mercati is not None else event_id, adesso_ms)
        if not es.vivo:
            return es
    if payload is not None:
        if blocco_riga(payload) is None and stato_dichiara_flusso(stato):
            # seconda consegna (28/09): lo scanner NUOVO scrive la chiave su ogni
            # riga; una riga che non la porta non e' sua (residuo, altra fonte):
            # dato assente = NON vivo, mai "non noto"
            return Esito(False, MOTIVO_NON_DICHIARATO, testo_motivo(MOTIVO_NON_DICHIARATO))
        return valuta_riga(payload, mercati, adesso_ms)
    return NON_NOTO


def stato_dichiara_flusso(stato: Optional[Mapping[str, Any]]) -> bool:
    """Lo stato viene dallo scanner NUOVO (porta la chiave ``flusso``)?"""
    return isinstance(stato, Mapping) and isinstance(stato.get(CHIAVE), Mapping)


# Il caso "non noto" VERO: lo stato dello scanner letto NON porta la chiave, cioe'
# gira uno scanner vecchio. Si DICE una volta per processo e per bot (l'avviso lo
# scrive il bot nella SUA attivita', con il suo db: questo modulo resta puro).
_NON_NOTO_AVVISATO: set = set()


def primo_avviso_scanner_vecchio(bot: str, stato: Optional[Mapping[str, Any]]) -> bool:
    """True UNA volta per processo e per ``bot`` quando lo stato dello scanner
    c'e' ma non dichiara il flusso: chi chiama scrive l'avviso visibile."""
    if not isinstance(stato, Mapping) or stato_dichiara_flusso(stato):
        return False
    if bot in _NON_NOTO_AVVISATO:
        return False
    _NON_NOTO_AVVISATO.add(bot)
    return True


TESTO_SCANNER_VECCHIO = ("lo scanner in esercizio NON dichiara il flusso dei prezzi (versione "
                         "precedente al 28/09): il bot non sa se i prezzi sono vivi oltre "
                         "all'eta' della riga. Riavviare l'app per caricare lo scanner nuovo.")


# ---------------------------------------------------------------------------
# CANTIERE J2 (28/09, reperto A del coordinatore): LA REGOLA UNICA per Safe,
# Mike e Omega, paper e live. Col flusso dello scanner fermo:
#   * una APERTURA non parte mai (nemmeno con un book REST vivo);
#   * una CHIUSURA, una COPERTURA di rischio o una PROTEZIONE prova il book dal
#     ripiego REST GIA' esistente del bot (col suo tetto di chiamate); se il
#     REST risponde con un mercato aperto decide su QUEI prezzi e lo scrive
#     nell'attivita' (``fonte = FONTE_RIPIEGO_REST``);
#   * se anche il REST non risponde aspetta e scrive una riga CRITICA al piu'
#     una volta al minuto per posizione (posizione, esposizione in euro, da
#     quanti secondi il flusso e' fermo).
# ---------------------------------------------------------------------------
FONTE_RIPIEGO_REST = "rest_ripiego"
KIND_RIPIEGO_REST = "ripiego_rest"
AVVISO_CRITICO_OGNI_S = 60.0


def secondi_fermo(payload: Optional[Mapping[str, Any]], stato: Optional[Mapping[str, Any]] = None,
                  adesso_ms: Optional[int] = None) -> Optional[float]:
    """Da quanti secondi i prezzi della riga non sono vivi: dal passaggio a
    fermo della riga (``flusso.dal_ms``) o, col giro dello scanner bloccato,
    dall'ultimo calcolo (``stato.flusso.calcolato_ms``). None = non noto."""
    adesso = adesso_ms if adesso_ms is not None else _ora_ms()
    candidati: List[float] = []
    if isinstance(stato, Mapping) and isinstance(stato.get(CHIAVE), Mapping):
        calc = stato[CHIAVE].get("calcolato_ms")
        if isinstance(calc, (int, float)) and calc > 0 and (adesso - calc) / 1000.0 > STATO_CALCOLO_MAX_S:
            candidati.append((adesso - float(calc)) / 1000.0)
    blk = blocco_riga(payload)
    if blk is not None:
        dal = blk.get("dal_ms")
        fermi = blk.get("vivo") is not True or bool(blk.get("mercati_fermi"))
        if fermi and isinstance(dal, (int, float)) and dal > 0:
            candidati.append((adesso - float(dal)) / 1000.0)
    return round(max(candidati), 1) if candidati else None


class Promemoria:
    """Una riga per chiave al piu' ogni ``ogni_s`` (le righe CRITICHE del
    flusso fermo: mai rumore a ogni giro, mai silenzio)."""

    def __init__(self, ogni_s: float = AVVISO_CRITICO_OGNI_S) -> None:
        self.ogni_s = float(ogni_s)
        self._ultimo: Dict[Any, float] = {}

    def dovuto(self, chiave: Any, adesso_s: float) -> bool:
        prec = self._ultimo.get(chiave)
        if prec is not None and adesso_s - prec < self.ogni_s:
            return False
        if len(self._ultimo) > 5000:
            self._ultimo.clear()
        self._ultimo[chiave] = adesso_s
        return True

    def azzera(self) -> None:
        self._ultimo.clear()


def mercati_dal_payload(payload: Optional[Mapping[str, Any]]) -> List[str]:
    """Tutti i market_id dei blocchi della riga (MATCH_ODDS, cs, ht, ou, btts,
    ht_result). Serve allo scanner per sapere su quali mercati dichiarare il
    flusso, e ai bot che vogliono valutare un blocco preciso."""
    out: List[str] = []
    if not isinstance(payload, Mapping):
        return out
    mo = payload.get("mo_market_id")
    if mo:
        out.append(str(mo))
    for key in ("cs", "ht", "btts", "ht_result"):
        b = payload.get(key)
        if isinstance(b, Mapping) and b.get("market_id"):
            out.append(str(b.get("market_id")))
    for b in payload.get("ou") or []:
        if isinstance(b, Mapping) and b.get("market_id"):
            out.append(str(b.get("market_id")))
    visti: Dict[str, None] = {}
    for m in out:
        visti.setdefault(m, None)
    return list(visti)
