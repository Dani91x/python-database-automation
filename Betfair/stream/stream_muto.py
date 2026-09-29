"""stream_muto.py - lo STREAM DI MERCATO di un processo flumine e' vivo? (cantiere J, 28/09/2026)

Per i processi che hanno il PROPRIO stream flumine (runner calcio, runner tennis
con i bot tennis, sessioni scalper con maker/sniper/theta). Lo scanner ha il suo
segnale per mercato (``flusso_prezzi``); qui si misura la connessione di flumine.

Il fatto (verificato sul codice installato, flumine 2.13.11 e betfairlightweight
2.23.2):
  * i bot flumine vengono chiamati SOLO quando arriva un MarketBook: flumine
    non ripete i book vecchi (``streaming_timeout=None`` in tutto il repo), quindi
    a stream muto una posizione aperta NON e' gestita da nessuno finche' non
    arriva il book successivo (force-flat, stop e uscite compresi);
  * la connessione dice di essere viva a ogni messaggio, heartbeat compresi:
    ``BaseStream._update_clk`` (``betfairlightweight/streaming/stream.py:149-155``)
    scrive ``time_updated = utcnow()`` (tz UTC) su SUB_IMAGE, delta e HEARTBEAT;
  * ``listener.status`` e' lo ``status`` dell'ultimo messaggio
    (``streaming/listener.py:135``): 503 = «downstream services are experiencing
    latencies» (schema ESA ufficiale,
    https://github.com/betfair/stream-api-sample-code/blob/master/ESASwaggerSchema.json).
L'HEARTBEAT (J2, reperto 2, letto nel CODICE):
  * scanner: chiede ``heartbeat_ms=5000`` (``safe_strategy/stream.py:65`` e ``:276``);
  * runner calcio, runner tennis, sessioni scalper: flumine NON lo passa
    (``flumine/streams/marketstream.py:36-42``: ``subscribe_to_markets`` senza
    ``heartbeat_ms``; lo stesso la risottoscrizione a caldo
    ``Betfair/stream/sottoscrizione_a_caldo.py:102-104``), quindi
    betfairlightweight manda ``"heartbeatMs": null``
    (``betfairlightweight/streaming/betfairstream.py:109,133``) e decide Betfair;
  * lo schema ESA ufficiale NON dichiara un default: dice che la richiesta sta
    fra 500 e 5000 ms e che il valore VERO viene RIMANDATO sull'immagine
    iniziale (``MarketChangeMessage.heartbeatMs``, «may differ from requested:
    bounds are 500 to 30000»).
Quindi: dove il listener ha letto il valore rimandato da Betfair
(``heartbeat_ms_server``: ``FrammentoListener`` del runner calcio) la soglia e'
3 volte QUEL valore; altrove 3 volte il massimo richiedibile (5000 ms), che e'
anche il valore dello scanner: la soglia piu' stretta possibile fra i valori
ammessi in richiesta (sbaglia solo verso l'allarme, mai verso il silenzio).

CANTIERE J2 (28/09): il runner calcio misura GIA' il battito di ogni sua
connessione (``frammenti_mercato.FrammentoListener.ultimo_msg_mono``, qualunque
messaggio, heartbeat compresi): se il listener lo porta si usa QUELLO (mai due
misure dello stesso fatto). Il runner tennis misura il suo stream nel tee
(``RAW_TEE.last_heartbeat_ms`` / ``last_data_ms``): ``stato_da_battiti``.

Questo modulo NON importa flumine (duck typing sugli oggetti veri) e non fa I/O:
misura (``stato_stream``) e tiene la memoria degli episodi
(``SorvegliaStream``), che dice UNA volta l'inizio e UNA volta la fine.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

#: massimo ``heartbeatMs`` richiedibile (schema ESA, MarketSubscriptionMessage)
HEARTBEAT_MS_MAX_RICHIESTA = 5000
#: quello che chiediamo dove lo chiediamo: lo scanner (``safe_strategy/stream.py``)
try:
    from Betfair.safe_strategy.stream import _HEARTBEAT_MS as HEARTBEAT_MS_SCANNER
except Exception:  # noqa: BLE001 - modulo non importabile: il massimo ammesso
    HEARTBEAT_MS_SCANNER = HEARTBEAT_MS_MAX_RICHIESTA
#: il valore su cui si calcola la soglia quando Betfair non l'ha rimandato
HEARTBEAT_MS_RICHIESTO = min(int(HEARTBEAT_MS_SCANNER), HEARTBEAT_MS_MAX_RICHIESTA)
#: 3 heartbeat senza nessun messaggio = stream muto
BATTITI_PER_SOGLIA = 3
SOGLIA_S = BATTITI_PER_SOGLIA * HEARTBEAT_MS_RICHIESTO / 1000.0
_STATUS_LATENTE = 503


def soglia_per(listener: Any) -> float:
    """3 volte l'heartbeat che Betfair ha RIMANDATO a questa connessione
    (``heartbeat_ms_server``, se il listener l'ha letto), altrimenti SOGLIA_S."""
    hb = getattr(listener, "heartbeat_ms_server", None)
    if isinstance(hb, (int, float)) and not isinstance(hb, bool) and hb > 0:
        return BATTITI_PER_SOGLIA * float(hb) / 1000.0
    return SOGLIA_S
#: una connessione appena aperta che non ha ancora ricevuto niente non e'
#: "interrotta": ha questo tempo per autenticarsi e ricevere l'immagine
GRAZIA_CONNESSIONE_S = 30.0

CODICE_INIZIO = "FLUSSO_INTERROTTO"
CODICE_FINE = "FLUSSO_RIPRESO"
MOTIVO_MAI_CONNESSO = "mai_connesso"
MOTIVO_LATENTE = "stream_latente"
MOTIVO_INTERROTTO = "flusso_interrotto"


def _status_non_ok(st: Any) -> "tuple[bool, Optional[str]]":
    """(non ok, motivo) dallo ``status`` dell'ultimo messaggio dello stream.
    None/200 = aggiornato. 503 = ``stream_latente``; ogni altro valore (anche
    illeggibile) = ``stream_status_<valore>``: il flusso NON e' confermato."""
    if st is None:
        return False, None
    try:
        n = int(st)
    except (TypeError, ValueError):
        return True, f"stream_status_{str(st)[:20]}"
    if n == 200:
        return False, None
    return True, (MOTIVO_LATENTE if n == _STATUS_LATENTE else f"stream_status_{n}")


def _utc(adesso: Optional[datetime]) -> datetime:
    return adesso if adesso is not None else datetime.now(timezone.utc)


def _mercati(stream: Any) -> List[str]:
    mf = getattr(stream, "market_filter", None)
    ids = (mf or {}).get("marketIds") if isinstance(mf, dict) else None
    return [str(m) for m in (ids or [])]


def stream_di_mercato(framework: Any) -> List[Any]:
    """Gli stream di MERCATO (non ordini, non dati) di un framework flumine:
    quelli il cui listener tiene un ``MarketStream`` di betfairlightweight, o
    che non l'hanno ancora (connessione mai riuscita) ma hanno un filtro di
    mercato. Un frammento CHIUSO (``frammenti_mercato``) non conta."""
    out: List[Any] = []
    for s in list(getattr(framework, "streams", None) or []):
        if getattr(s, "chiuso", False):
            continue
        listener = getattr(s, "_listener", None)
        if listener is None:
            continue
        interno = getattr(listener, "stream", None)
        nome = type(interno).__name__ if interno is not None else ""
        if nome == "MarketStream" or (interno is None and getattr(s, "market_filter", None)):
            out.append(s)
    return out


def _eta_messaggio(listener: Any, interno: Any, ora: datetime,
                   adesso_mono: float) -> Optional[float]:
    """Secondi dall'ultimo messaggio della connessione (None = mai ricevuto).
    Il battito del listener del runner calcio (``ultimo_msg_mono``) se c'e',
    altrimenti ``time_updated`` dello stream di betfairlightweight."""
    um = getattr(listener, "ultimo_msg_mono", None)
    if isinstance(um, (int, float)) and not isinstance(um, bool):
        return max(0.0, adesso_mono - float(um)) if um > 0 else None
    agg = getattr(interno, "time_updated", None) if interno is not None else None
    if isinstance(agg, datetime):
        if agg.tzinfo is None:
            agg = agg.replace(tzinfo=timezone.utc)
        return max(0.0, (ora - agg).total_seconds())
    return None


def stato_stream(framework: Any, adesso: Optional[datetime] = None,
                 soglia_s: Optional[float] = None,
                 adesso_mono: Optional[float] = None) -> Dict[str, Any]:
    """{vivo, eta_s, motivo, mercati_fermi, stream: [...]} del framework.
    ``vivo`` = TUTTI gli stream di mercato hanno ricevuto un messaggio da meno di
    ``soglia_s`` e nessuno e' latente. Nessuno stream di mercato = ``vivo`` None
    (non noto). Una connessione aperta da meno di ``GRAZIA_CONNESSIONE_S``
    (``aperto_mono`` del frammento) che non ha ancora ricevuto niente non conta."""
    ora = _utc(adesso)
    mono = time.monotonic() if adesso_mono is None else float(adesso_mono)
    righe: List[Dict[str, Any]] = []
    for s in stream_di_mercato(framework):
        listener = getattr(s, "_listener", None)
        interno = getattr(listener, "stream", None)
        eta = _eta_messaggio(listener, interno, ora, mono)
        aperto = getattr(s, "aperto_mono", None)
        if (eta is None and isinstance(aperto, (int, float))
                and mono - float(aperto) < GRAZIA_CONNESSIONE_S):
            continue                    # connessione nuova: si sta autenticando
        st = getattr(listener, "status", None)
        # J2 (reperto 3): FAIL-CLOSED su ogni ``status`` diverso da null/200 (lo
        # schema ESA dichiara 503; qualunque altro codice non e' «aggiornato»)
        latente, codice = _status_non_ok(st)
        soglia = soglia_s if soglia_s is not None else soglia_per(listener)
        vivo = eta is not None and eta <= soglia and not latente
        motivo = None
        if not vivo:
            motivo = (MOTIVO_MAI_CONNESSO if eta is None else
                      codice if latente else MOTIVO_INTERROTTO)
        righe.append({"stream_id": getattr(s, "stream_id", None),
                      "eta_s": None if eta is None else round(eta, 1),
                      "latente": latente, "vivo": vivo, "motivo": motivo,
                      "mercati": _mercati(s)})
    if not righe:
        return {"vivo": None, "eta_s": None, "motivo": None, "mercati_fermi": [], "stream": []}
    fermi = [r for r in righe if not r["vivo"]]
    eta_max = max((r["eta_s"] for r in righe if r["eta_s"] is not None), default=None)
    return {"vivo": not fermi, "eta_s": eta_max,
            "motivo": fermi[0]["motivo"] if fermi else None,
            "mercati_fermi": sorted({m for r in fermi for m in r["mercati"]}),
            "stream": righe}


def stato_da_battiti(ultimo_heartbeat_ms: Any, ultimo_dato_ms: Any,
                     adesso_ms: Optional[float] = None, soglia_s: float = SOGLIA_S,
                     mercati: Optional[Iterable[Any]] = None,
                     latente: bool = False) -> Dict[str, Any]:
    """Lo stesso verdetto di ``stato_stream`` da due istanti gia' misurati dal
    processo (epoch ms dell'ultimo heartbeat e dell'ultimo dato: il tee del
    runner tennis). ``mercati`` vuoto/None = nessuno stream da sorvegliare."""
    ids = sorted({str(m) for m in (mercati or []) if m})
    if not ids:
        return {"vivo": None, "eta_s": None, "motivo": None, "mercati_fermi": [], "stream": []}
    ora = time.time() * 1000.0 if adesso_ms is None else float(adesso_ms)
    ultimi = [float(x) for x in (ultimo_heartbeat_ms, ultimo_dato_ms)
              if isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0]
    eta = max(0.0, (ora - max(ultimi)) / 1000.0) if ultimi else None
    vivo = eta is not None and eta <= soglia_s and not latente
    motivo = None if vivo else (MOTIVO_MAI_CONNESSO if eta is None else
                                MOTIVO_LATENTE if latente else MOTIVO_INTERROTTO)
    riga = {"stream_id": None, "eta_s": None if eta is None else round(eta, 1),
            "latente": bool(latente), "vivo": vivo, "motivo": motivo, "mercati": ids}
    return {"vivo": vivo, "eta_s": riga["eta_s"], "motivo": motivo,
            "mercati_fermi": [] if vivo else ids, "stream": [riga]}


#: le chiavi del messaggio ``flusso_stream`` sul canale del runner (calcio 47331,
#: tennis 47332), in UN POSTO SOLO: la UI (``runnerCanale.ts``) le legge cosi'
CHIAVI_CANALE = ("ts", "vivo", "interrotto", "motivo", "eta_s", "muto_da_s",
                 "mercati_fermi", "episodi")


def messaggio_canale(dichiarazione: Dict[str, Any],
                     adesso_ms: Optional[float] = None) -> Dict[str, Any]:
    """Il messaggio del topic ``flusso_stream`` dalla ``dichiarazione`` del
    sorvegliante: chiavi fisse ``CHIAVI_CANALE``, ``ts`` in ms epoch del
    produttore."""
    d = dict(dichiarazione or {})
    return {
        "ts": int(time.time() * 1000 if adesso_ms is None else adesso_ms),
        "vivo": d.get("vivo"),
        "interrotto": bool(d.get("interrotto")),
        "motivo": d.get("motivo"),
        "eta_s": d.get("eta_s"),
        "muto_da_s": d.get("muto_da_s"),
        "mercati_fermi": list(d.get("mercati_fermi") or []),
        "episodi": int(d.get("episodi") or 0),
    }


@dataclass
class SorvegliaStream:
    """Memoria degli episodi di stream muto. ``osserva`` restituisce l'avviso da
    scrivere (una volta all'inizio, una alla fine) o None. Pura.

    J2: all'avvio del processo la connessione ha ``GRAZIA_CONNESSIONE_S`` per
    arrivare (``mai_connesso`` prima di allora non e' un episodio)."""

    muto_dal: Optional[float] = None
    episodi: int = 0
    ultimo: Dict[str, Any] = field(default_factory=dict)
    nato_s: Optional[float] = None

    def osserva(self, stato: Dict[str, Any], adesso_s: float,
                posizione: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if self.nato_s is None:
            self.nato_s = adesso_s
        self.ultimo = dict(stato)
        vivo = stato.get("vivo")
        if (vivo is False and self.muto_dal is None
                and stato.get("motivo") == MOTIVO_MAI_CONNESSO
                and adesso_s - self.nato_s < GRAZIA_CONNESSIONE_S):
            return None
        if vivo is False and self.muto_dal is None:
            self.muto_dal = adesso_s
            self.episodi += 1
            aperta = f" POSIZIONE APERTA NON GESTITA: {posizione}." if posizione else ""
            return {"level": "CRITICAL", "code": CODICE_INIZIO,
                    "message": (f"Flusso prezzi INTERROTTO ({stato.get('motivo')}, "
                                f"ultimo messaggio {stato.get('eta_s')} s fa): il bot non "
                                f"riceve prezzi e non puo' aprire ne' chiudere.{aperta} "
                                "Riconnessione automatica in corso.")}
        if vivo is True and self.muto_dal is not None:
            durata = adesso_s - self.muto_dal
            self.muto_dal = None
            return {"level": "INFO", "code": CODICE_FINE,
                    "message": f"Flusso prezzi RIPRESO dopo {durata:.0f} s."}
        return None

    @property
    def interrotto(self) -> bool:
        """C'e' un episodio in corso (dichiarato)."""
        return self.muto_dal is not None

    def dichiarazione(self, adesso_s: float) -> Dict[str, Any]:
        """Per le stats del bot (lette dalla Control Room): chiavi fisse.
        ``interrotto`` = episodio dichiarato in corso (la UI mostra «flusso
        interrotto» finche' e' vero)."""
        return {"vivo": self.ultimo.get("vivo"), "motivo": self.ultimo.get("motivo"),
                "eta_s": self.ultimo.get("eta_s"),
                "interrotto": self.muto_dal is not None,
                "mercati_fermi": list(self.ultimo.get("mercati_fermi") or [])[:50],
                "muto_da_s": (None if self.muto_dal is None
                              else round(adesso_s - self.muto_dal, 1)),
                "episodi": self.episodi}
