"""varianti_bot.py - i pezzi COMUNI di "Applica bot" per tutti i bot (07/10/2026).

Ordine dell'utente (07/10): <<portare TUTTI I BOT nella sezione "applica bot">> e
<<devo poter modificare i parametri di ognuno cosi' da provare altre varianti
SENZA CAMBIARE LA STRATEGIA>>.

Qui vive soltanto cio' che e' uguale per tutti i bot, cosi' che ogni modulo di
replay non ne tenga una copia sua:

* ``voce(...)``: una voce del catalogo dei parametri modificabili, con le chiavi
  del contratto (chiave, etichetta, tipo, default, min, max, passo, unita,
  gruppo, scelte). Il DEFAULT lo passa il modulo del bot, letto dalla STESSA
  fonte che usa il servizio (whitelist del bot, preset del runner, istanza vera):
  qui non si scrive nessun numero di strategia.
* ``valida(catalogo, parametri)``: le sostituzioni chieste, controllate contro il
  catalogo. Chiave sconosciuta, tipo sbagliato o valore fuori dominio ->
  ``ValueError`` col motivo (mai un valore inventato, mai ignorato in silenzio).
* ``SpecchioOrdini``: la cronologia degli ordini del bot nella forma delle righe
  ``betfair_live_orders`` (le costruisce ``LiveTradingStrategy._order_row``, la
  funzione di PRODUZIONE dello specchio, la stessa che usa ``porta_banco``) con
  l'istante ``_ms`` del banco (publish time Betfair del book, lo stesso orologio
  dei frame del Match Replay). Legge gli ordini VERI del flumine simulato del
  banco: nessun numero scritto a mano. Si aggancia al ``MotoreReplay`` dopo ogni
  book passato a flumine (``aggancia``) e non cambia niente di cio' che il bot
  vede o fa: legge soltanto.
* ``Accensione``: l'istante ``dal_ms`` in cui l'utente ACCENDE il bot. Ogni modulo
  la usa sulla STESSA strada della produzione (la riga di controllo passa da
  ``stopped`` a ``running``, oppure il runner arma il bot in quel momento).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

#: i tipi ammessi dal contratto
TIPI = ("int", "float", "bool", "scelta")

#: i gruppi con cui la UI raggruppa i parametri (ordine di presentazione)
GRUPPI = ("Ingresso", "Uscita", "Importi", "Tetti", "Filtri", "Tempi")

#: le chiavi di ogni voce, nell'ordine del contratto
CHIAVI_VOCE = ("chiave", "etichetta", "tipo", "default", "min", "max", "passo",
               "unita", "gruppo", "scelte")


def voce(chiave: str, etichetta: str, tipo: str, default: Any, *,
         gruppo: str, minimo: Optional[float] = None, massimo: Optional[float] = None,
         passo: Optional[float] = None, unita: str = "",
         scelte: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Una voce del catalogo. Solleva ValueError se la voce stessa e' incoerente
    (un catalogo sbagliato non deve arrivare alla UI)."""
    if tipo not in TIPI:
        raise ValueError("tipo %r non ammesso per %s (ammessi: %s)"
                         % (tipo, chiave, ", ".join(TIPI)))
    if gruppo not in GRUPPI:
        raise ValueError("gruppo %r non ammesso per %s (ammessi: %s)"
                         % (gruppo, chiave, ", ".join(GRUPPI)))
    if tipo == "scelta":
        if not scelte:
            raise ValueError("parametro %s di tipo scelta senza scelte" % chiave)
        scelte = [str(s) for s in scelte]
        if str(default) not in scelte:
            raise ValueError("default %r di %s fuori dalle scelte %s" % (default, chiave, scelte))
        default = str(default)
    elif tipo == "bool":
        if not isinstance(default, bool):
            raise ValueError("default %r di %s non e' un bool" % (default, chiave))
    else:
        if isinstance(default, bool) or not isinstance(default, (int, float)):
            raise ValueError("default %r di %s non e' un numero" % (default, chiave))
        default = int(default) if tipo == "int" else float(default)
        if minimo is None or massimo is None or passo is None:
            raise ValueError("parametro numerico %s senza min/max/passo" % chiave)
        if not (minimo <= default <= massimo):
            raise ValueError("default %r di %s fuori da [%s, %s]"
                             % (default, chiave, minimo, massimo))
    return {
        "chiave": str(chiave), "etichetta": str(etichetta), "tipo": tipo,
        "default": default,
        "min": (None if tipo in ("bool", "scelta") else
                (int(minimo) if tipo == "int" else float(minimo))),
        "max": (None if tipo in ("bool", "scelta") else
                (int(massimo) if tipo == "int" else float(massimo))),
        "passo": (None if tipo in ("bool", "scelta") else
                  (int(passo) if tipo == "int" else float(passo))),
        "unita": str(unita or ""), "gruppo": gruppo,
        "scelte": list(scelte) if tipo == "scelta" else None,
    }


def _valore(v: Dict[str, Any], grezzo: Any) -> Any:
    """Il valore chiesto per la voce ``v``, controllato. ValueError col motivo."""
    k, tipo = v["chiave"], v["tipo"]
    if tipo == "bool":
        if not isinstance(grezzo, bool):
            raise ValueError("parametro %s: atteso vero/falso, arrivato %r" % (k, grezzo))
        return grezzo
    if tipo == "scelta":
        if str(grezzo) not in (v.get("scelte") or []):
            raise ValueError("parametro %s: %r non e' fra le scelte %s"
                             % (k, grezzo, v.get("scelte")))
        return str(grezzo)
    if isinstance(grezzo, bool) or not isinstance(grezzo, (int, float)):
        raise ValueError("parametro %s: atteso un numero, arrivato %r" % (k, grezzo))
    x = float(grezzo)
    if not math.isfinite(x):
        raise ValueError("parametro %s: numero non finito %r" % (k, grezzo))
    if tipo == "int":
        if x != int(x):
            raise ValueError("parametro %s: atteso un intero, arrivato %r" % (k, grezzo))
        x = int(x)
    lo, hi = v.get("min"), v.get("max")
    if (lo is not None and x < lo) or (hi is not None and x > hi):
        raise ValueError("parametro %s: %r fuori dal dominio [%s, %s]" % (k, grezzo, lo, hi))
    return x


def valida(catalogo: Sequence[Dict[str, Any]],
           parametri: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Le sostituzioni chieste, controllate contro il catalogo dello scenario.
    Torna {chiave: valore} (solo le chiavi chieste). ``None``/vuoto -> {}."""
    if not parametri:
        return {}
    if not isinstance(parametri, dict):
        raise ValueError("parametri: atteso un dizionario, arrivato %r" % type(parametri).__name__)
    per_chiave = {v["chiave"]: v for v in catalogo}
    out: Dict[str, Any] = {}
    ignote = sorted(str(k) for k in parametri if k not in per_chiave)
    if ignote:
        raise ValueError("parametri non modificabili per questo bot/scenario: %s "
                         "(modificabili: %s)" % (", ".join(ignote),
                                                 ", ".join(sorted(per_chiave)) or "nessuno"))
    for k, grezzo in parametri.items():
        out[str(k)] = _valore(per_chiave[k], grezzo)
    return out


def parametri_usati(catalogo: Sequence[Dict[str, Any]],
                    sostituzioni: Dict[str, Any]) -> Dict[str, Any]:
    """Default del catalogo + sostituzioni: cio' che il referto dichiara."""
    out = {v["chiave"]: v["default"] for v in catalogo}
    out.update(sostituzioni or {})
    return out


def applica_annidato(base: Dict[str, Any], chiave: str, valore: Any) -> None:
    """Scrive ``valore`` in ``base`` seguendo il percorso puntato ``a.b.c``
    (sezioni della Safe: ``esatto.minuteMin``, ``exits.base_exit_minute``),
    senza buttare via le altre chiavi della sezione."""
    parti = str(chiave).split(".")
    nodo = base
    for p in parti[:-1]:
        figlio = nodo.get(p)
        if not isinstance(figlio, dict):
            figlio = {}
        else:
            figlio = dict(figlio)
        nodo[p] = figlio
        nodo = figlio
    nodo[parti[-1]] = valore


def leggi_annidato(base: Dict[str, Any], chiave: str) -> Any:
    nodo: Any = base
    for p in str(chiave).split("."):
        if not isinstance(nodo, dict) or p not in nodo:
            return None
        nodo = nodo[p]
    return nodo


# ---------------------------------------------------------------------------
# L'ACCENSIONE (dal_ms)
# ---------------------------------------------------------------------------
class Accensione:
    """L'istante in cui l'utente ACCENDE il bot (``dal_ms``, orologio del banco).

    ``acceso(ms)`` dice se a quell'istante il bot e' gia' acceso; ``scatta(ms)``
    torna True UNA volta sola, al primo istante >= ``dal_ms`` (e' li' che il
    modulo del bot fa il gesto di produzione: riga di controllo a ``running``,
    armamento nel runner). ``None`` = acceso dall'inizio, come oggi."""

    def __init__(self, dal_ms: Optional[int]) -> None:
        if dal_ms is not None:
            if isinstance(dal_ms, bool) or not isinstance(dal_ms, int) or dal_ms < 0:
                raise ValueError("dal_ms: atteso un intero >= 0 (ms del banco), "
                                 "arrivato %r" % (dal_ms,))
        self.dal_ms = dal_ms
        self.scattata_ms: Optional[int] = None

    @property
    def attiva(self) -> bool:
        return self.dal_ms is not None

    def acceso(self, ms: Optional[int]) -> bool:
        return self.dal_ms is None or (ms is not None and int(ms) >= self.dal_ms)

    def scatta(self, ms: Optional[int]) -> bool:
        if self.dal_ms is None or self.scattata_ms is not None:
            return False
        if ms is None or int(ms) < self.dal_ms:
            return False
        self.scattata_ms = int(ms)
        return True


def controlla_dal_ms(dal_ms: Any) -> Optional[int]:
    """``dal_ms`` dalla richiesta: None oppure un intero >= 0. ValueError altrimenti."""
    if dal_ms is None:
        return None
    return Accensione(dal_ms).dal_ms


# ---------------------------------------------------------------------------
# LA CRONOLOGIA DEGLI ORDINI (ordini_specchio)
# ---------------------------------------------------------------------------
_LTS: Any = None


def _classe_specchio() -> Any:
    global _LTS
    if _LTS is None:
        from ..engine.live_trading_strategy import LiveTradingStrategy

        _LTS = LiveTradingStrategy
    return _LTS


def ms_di(adesso: Any) -> Optional[int]:
    """Il publish time (datetime con fuso) in ms; None se non c'e'."""
    if adesso is None:
        return None
    try:
        return int(round(adesso.timestamp() * 1000.0))
    except Exception:  # noqa: BLE001 - orologio inatteso: nessun istante
        return None


def _dell_utente(ordine: Any) -> bool:
    note = getattr(ordine, "notes", None)
    return bool(isinstance(note, dict) and note.get("utente"))


class SpecchioOrdini:
    """Gli ordini del bot come righe ``betfair_live_orders`` + ``_ms``.

    ``sorgente`` = la ``source`` che il motore ordini scrive per l'attore del bot
    (CHECK ``betfair_live_orders_source_check``: 'mike', 'omega', 'safe',
    'safe_tennis', 'tennis_*'). ``modo`` = la modalita' con cui il bot esegue nel
    replay ('live' | 'paper'), costante o funzione dell'ordine. ``includi``
    filtra gli ordini che NON sono del bot (di serie: quelli piazzati dal banco
    per conto dell'utente, nota ``utente``).

    Si scrive una riga quando la FIRMA dell'ordine cambia (la stessa firma di
    ``LiveTradingStrategy.process_orders``: write-on-change come in produzione)."""

    def __init__(self, *, sorgente: str, modo: Any, event_id: Optional[str],
                 includi: Optional[Callable[[Any], bool]] = None) -> None:
        self.sorgente = str(sorgente)
        self._modo = modo
        self.event_id = None if event_id is None else str(event_id)
        self._includi = includi or (lambda o: not _dell_utente(o))
        self.righe: List[Dict[str, Any]] = []
        self._contati: Dict[str, int] = {}
        self._vivi: Dict[str, Any] = {}
        self._firme: Dict[str, Any] = {}
        self._mercati: Dict[str, Any] = {}
        self.ultimo_ms: Optional[int] = None

    def _modo_di(self, ordine: Any) -> str:
        m = self._modo(ordine) if callable(self._modo) else self._modo
        return "live" if str(m or "").lower() == "live" else "paper"

    def _riga(self, ordine: Any, market: Any, ms: int) -> None:
        lts = _classe_specchio()
        finto = SimpleNamespace(mode=self._modo_di(ordine))
        chiave = str(getattr(ordine, "id", id(ordine)))
        firma = lts._order_signature(finto, ordine)
        if self._firme.get(chiave) == firma:
            return
        riga = lts._order_row(finto, ordine,
                              event_id=self.event_id or getattr(market, "event_id", None),
                              market_id=getattr(market, "market_id", None))
        if riga is None or riga.get("status") is None:
            # ``betfair_live_orders.status`` e' NOT NULL: un ordine non ancora
            # materializzato non e' una riga (lo si rilegge al book dopo)
            return
        self._firme[chiave] = firma
        riga["source"] = self.sorgente
        riga["_ms"] = int(ms)
        self.righe.append(riga)

    def osserva_mercato(self, market: Any, ms: Optional[int]) -> None:
        """Dopo un book del mercato: ordini nuovi del suo blotter e quelli vivi."""
        if market is None or ms is None:
            return
        self.ultimo_ms = int(ms)
        mid = str(getattr(market, "market_id", ""))
        blotter = getattr(market, "blotter", None)
        if blotter is None:
            return
        self._mercati[mid] = market
        n = len(blotter)
        if n != self._contati.get(mid):
            self._contati[mid] = n
            for o in blotter:
                k = str(getattr(o, "id", id(o)))
                if k not in self._firme and k not in self._vivi and self._includi(o):
                    self._vivi[k] = (market, o)
        for k, (m, o) in list(self._vivi.items()):
            if str(getattr(m, "market_id", "")) != mid:
                continue
            self._riga(o, m, ms)
            stato = getattr(getattr(o, "status", None), "name", None) or str(
                getattr(o, "status", ""))
            if stato == "EXECUTION_COMPLETE":
                self._vivi.pop(k, None)

    def aggancia(self, motore: Any) -> None:
        """Dopo ogni book che il ``MotoreReplay`` passa a flumine (giro del bot,
        attesa del bet delay, letture): sola lettura, il bot non se ne accorge."""
        originale = motore._a_flumine

        def _a_flumine(market_book: Any):
            out = originale(market_book)
            mercato = out[0] if isinstance(out, tuple) else None
            if mercato is not None:
                self.osserva_mercato(mercato, ms_di(getattr(motore, "_ora_mercato", None)))
            return out

        motore._a_flumine = _a_flumine

    def chiudi(self, mercati: Iterable[Any] = (), ms: Optional[int] = None) -> List[Dict[str, Any]]:
        """L'ultimo giro: lo stato finale di ogni ordine (lapse alla chiusura,
        annulli eseguiti nell'ultima attesa). Torna le righe, in ordine di ``_ms``."""
        quando = ms if ms is not None else self.ultimo_ms
        if quando is not None:
            visti = dict(self._mercati)
            for m in mercati or []:
                if m is not None:
                    visti[str(getattr(m, "market_id", ""))] = m
            for m in visti.values():
                self.osserva_mercato(m, quando)
        self.righe.sort(key=lambda r: int(r["_ms"]))
        return list(self.righe)


def mercati_del_quadro(quadro: Any) -> List[Any]:
    """I mercati di una ``FlumineSimulation`` (per l'ultimo giro dello specchio)."""
    mercati = getattr(getattr(quadro, "markets", None), "markets", None)
    if isinstance(mercati, dict):
        return list(mercati.values())
    return []
