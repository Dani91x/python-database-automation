"""trasporto.py - IL TRASPORTO DELL'ORDINE nel banco: coda di oggi o canale (F4).

Decisione dell'utente (24/09, strada unica): la strada verso gli ordini diventa
il canale di comando del runner. Cambia SOLO il trasporto: la traccia delle
decisioni del bot deve restare identica. Qui il banco sa far girare la STESSA
registrazione, con lo STESSO codice di produzione del bot, nei due trasporti:

* ``coda``   - il trasporto di oggi nel banco: il gate flumine e' chiuso (nel
  replay il runner non esiste) e l'ordine esce da ``place_order_live``, servito
  da ``MercatoFlumine`` sul matching di flumine. E' il riferimento certificato
  (c3j/c3k). Qui si REGISTRA ogni chiamata, niente di piu'.
* ``canale`` - l'interruttore del bot e' ACCESO (``SAFE_ORDINI_VIA_CANALE`` /
  ``OMEGA_ORDINI_VIA_CANALE``): il bot usa la sua porta VERA
  (``PortaCanale`` / ``PortaCanaleOmega``, col suo thread e la sua memoria),
  che parla su un ``WsBanco`` al ``MotoreOrdini`` VERO (``PortaBanco``), che
  esegue il ``_dispatch`` VERO di ``live_order_worker`` sul ``Market`` della
  ``FlumineSimulation`` del banco. Gli esiti tornano dallo specchio del
  blotter (``LiveTradingStrategy._order_row``) come eventi ``order``.

Nessuna classe di laboratorio al posto di quelle di produzione; nessun fill a
mano: gli ordini li abbina flumine, col bet delay che il banco fa scorrere.

L'aggancio e' UNO per tutti i bot: ``MotoreReplay.esegui`` chiama
``su_esegui(self, strategia)`` all'inizio del replay; fuori da ``contesto`` non
fa niente (i replay di sempre restano identici, riga per riga).

DIFFERENZE AMMESSE fra i due trasporti (dichiarate nel rapporto di parita'):
  * i TEMPI: sulla coda di oggi il bot resta FERMO sulla REST per
    ``place_latency + betDelay`` (``MotoreReplay.attendi_esecuzione``) e sa
    l'esito subito; sul canale riceve l'ack e riprende, l'esito arriva dagli
    eventi e la riga si chiude al giro dopo. I giri successivi cadono quindi su
    book diversi: i prezzi possono differire di tick;
  * l'esecuzione di flumine: sulla coda il pacchetto si esegue nell'attesa sul
    primo book utile di QUALUNQUE mercato, sul canale al primo book DI QUEL
    mercato dopo il ritardo (``_check_pending_packages``).
Tutto il resto (quali ordini, lato, prezzo, size, ref, ordine temporale, esito)
deve coincidere: altrimenti la parita' NON e' raggiunta e si dice dove.
"""
from __future__ import annotations

import contextlib
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

TRASPORTI = ("coda", "canale")

#: bot del registro -> (attore del protocollo, interruttore del bot)
ATTORI: Dict[str, tuple] = {
    "safe_base": ("safe", "SAFE_ORDINI_VIA_CANALE"),
    "safe_esatto": ("safe", "SAFE_ORDINI_VIA_CANALE"),
    "safe_punta": ("safe", "SAFE_ORDINI_VIA_CANALE"),
    "omega": ("omega", "OMEGA_ORDINI_VIA_CANALE"),
    # 25/09 (F8): Safe tennis sul canale 47332 del runner TENNIS (motore con
    # l'esecutore tennis, ``porta_banco.PortaBanco(sport="tennis")``)
    "safe_tennis": ("safe_tennis", "SAFE_TENNIS_ORDINI_VIA_CANALE"),
}

#: lo sport del runner di ogni attore (quale motore, quale porta del bot)
SPORT_ATTORE: Dict[str, str] = {"safe": "calcio", "omega": "calcio",
                                "safe_tennis": "tennis"}

#: perche' gli altri bot non hanno ancora il canale (F7/F8 dell'audit)
SENZA_CANALE: Dict[str, str] = {
    "mike": "F7 non fatta: Mike piazza sempre in REST (execute_place, lay appoggiate, "
            "submin sincrono); nessuna porta a comandi nel suo codice",
}

_STATO: Optional[Dict[str, Any]] = None


def attore_di(bot: str) -> Optional[str]:
    voce = ATTORI.get(str(bot))
    return voce[0] if voce else None


@contextlib.contextmanager
def contesto(bot: str, trasporto: str) -> Iterator[Dict[str, Any]]:
    """Per la durata del replay: quale trasporto usa il bot. ``canale`` accende
    l'interruttore del bot (e lo rimette com'era all'uscita)."""
    global _STATO
    trasporto = str(trasporto or "coda")
    if trasporto not in TRASPORTI:
        raise ValueError("trasporto %r: ammessi %s" % (trasporto, ", ".join(TRASPORTI)))
    voce = ATTORI.get(str(bot))
    if trasporto == "canale" and voce is None:
        raise ValueError("il bot %r non ha la porta a comandi: %s" % (
            bot, SENZA_CANALE.get(str(bot), "non registrato per il canale")))
    stato: Dict[str, Any] = {
        "bot": str(bot), "trasporto": trasporto,
        "attore": voce[0] if voce else None,
        "rest": [],           # chiamate al REST del banco (MercatoFlumine)
        "porta_banco": None, "client": None, "strategia": None, "motore": None,
        "durata_s": None,
    }
    env_prima: Optional[str] = None
    nome_env = voce[1] if voce else None
    if trasporto == "canale" and nome_env:
        env_prima = os.environ.get(nome_env)
        os.environ[nome_env] = "1"
    prima = _STATO
    _STATO = stato
    t0 = time.monotonic()
    try:
        yield stato
    finally:
        stato["durata_s"] = round(time.monotonic() - t0, 1)
        _smonta(stato)
        _STATO = prima
        if trasporto == "canale" and nome_env:
            if env_prima is None:
                os.environ.pop(nome_env, None)
            else:
                os.environ[nome_env] = env_prima


def attivo() -> Optional[Dict[str, Any]]:
    return _STATO


# ---------------------------------------------------------------------------
# l'aggancio al replay (chiamato da MotoreReplay.esegui)
# ---------------------------------------------------------------------------
def su_esegui(motore: Any, strategia: Any) -> None:
    """Primo passo di ``MotoreReplay.esegui``: fuori da ``contesto`` e' nullo."""
    st = _STATO
    if st is None or st.get("strategia") is not None:
        return
    st["strategia"] = strategia
    st["motore"] = motore
    mercato = getattr(strategia, "mercato", None)
    if mercato is not None:
        _registra_rest(st, mercato, motore)
    if st["trasporto"] == "canale":
        _monta_canale(st, motore, strategia)


def _ora_mercato(motore: Any) -> Optional[str]:
    ora = getattr(motore, "_ora_mercato", None)
    return ora.isoformat() if isinstance(ora, datetime) else (str(ora) if ora else None)


def _registra_rest(st: Dict[str, Any], mercato: Any, motore: Any) -> None:
    """Registra ogni chiamata al REST del banco (piazzamento e annullo). Sulla
    coda e' la traccia; sul canale DEVE restare vuota, salvo i ripieghi
    dichiarati (D5: chiusure e annulli a canale giu')."""
    # il place-and-trim REST del banco passa da place_order_live: si spia quello
    for nome in ("place_order_live", "cancel_order_live"):
        vero = getattr(mercato, nome, None)
        if not callable(vero):
            continue

        def _spia(*a: Any, _vero: Any = vero, _nome: str = nome, **kw: Any) -> Any:
            t = _ora_mercato(motore)
            out = _vero(*a, **kw)
            if _nome == "cancel_order_live":
                st["rest"].append({"azione": "cancel", "t_mercato": t,
                                   "bet_id": str(kw.get("bet_id") or (a[0] if a else "")),
                                   "market_id": str(kw.get("market_id") or
                                                    (a[1] if len(a) > 1 else "")),
                                   "ok": bool(getattr(out, "ok", False))})
            else:
                st["rest"].append({
                    "azione": "place", "t_mercato": t,
                    "ref": str(kw.get("customer_ref") or "")[:32],
                    "market_id": str(kw.get("market_id")),
                    "selection_id": int(kw.get("selection_id")),
                    "side": str(kw.get("side") or "lay").upper(),
                    "price": round(float(kw.get("price")), 2),
                    "size": round(float(kw.get("size")), 2),
                    "fok": bool(kw.get("fill_or_kill", _nome == "place_order_live")),
                    "ok": bool(getattr(out, "ok", False)),
                    "size_matched": round(float(getattr(out, "size_matched", 0.0) or 0.0), 2),
                })
            return out
        setattr(mercato, nome, _spia)


def _monta_canale(st: Dict[str, Any], motore: Any, strategia: Any) -> None:
    from .porta_banco import PortaBanco, TOKEN_BANCO

    modo = "LIVE" if str(getattr(strategia, "mode", "live")) == "live" else "PAPER"
    sport = SPORT_ATTORE.get(str(st["attore"]), "calcio")
    pb = PortaBanco(motore.quadro, strategia, attore=st["attore"], modo_processo=modo,
                    sport=sport)
    pb.orologio_mercato = lambda: _ora_mercato(motore)
    st["porta_banco"] = pb
    if st["attore"] == "omega":
        from ...omega import porta_ordini as OPO

        client = OPO.PortaCanaleOmega(porta_ws=0, attore="omega", sport="calcio",
                                      connetti=pb.connetti, token_fn=lambda: TOKEN_BANCO)
        st["_ripristina"] = ("omega", OPO._PORTA)
        OPO._PORTA = client
    else:
        from ...safe_strategy import porta_ordini as SPO

        client = SPO.PortaCanale(porta_ws=0, attore=st["attore"], sport=sport,
                                 connetti=pb.connetti, token_fn=lambda: TOKEN_BANCO)
        st["_ripristina"] = ("safe:" + sport, SPO._PORTE.get(sport))
        SPO._PORTE[sport] = client
    st["client"] = client
    client.avvia()
    fine = time.monotonic() + 5.0
    while not client.disponibile() and time.monotonic() < fine:
        time.sleep(0.001)
    if not client.disponibile():
        raise RuntimeError("banco: il client vero del canale non si e' collegato al "
                           "WsBanco in 5 s (%s)" % client.ultimo_errore)
    vero = strategia.process_market_book
    st["costo_banco_s"] = 0.0
    st["book"] = 0

    def _process_market_book(market: Any, market_book: Any) -> None:
        # lo stream ordini del runner: a ogni book lo specchio del blotter
        # diventa eventi ``order`` (e il place-and-trim fa un passo); il bot
        # al suo giro trova in memoria cio' che nel vivo sarebbe gia' arrivato
        t0 = time.perf_counter()
        pb.aggiorna()
        _adotta(st, pb, strategia)
        pb.attendi_client()
        st["costo_banco_s"] += time.perf_counter() - t0
        st["book"] += 1
        vero(market, market_book)
    strategia.process_market_book = _process_market_book


def _adotta(st: Dict[str, Any], pb: Any, strategia: Any) -> None:
    """Gli ordini piazzati dal MOTORE esistono sul conto come quelli della REST:
    la vista di conto del banco (``MercatoFlumine.ordini``, da cui leggono
    ``list_current_orders``/``order_state_by_bet_id`` e i controlli di condotta
    K4/K7) li deve vedere. Chiave = il ``customerOrderRef`` VERO che il motore ha
    mandato (``awlq<rid>...``, quello di flumine: su Betfair il ref della riga
    NON viaggia, vedi ``motore_ordini`` estensione 24/09), mai il ref del bot."""
    mercato = getattr(strategia, "mercato", None)
    ordini = getattr(mercato, "ordini", None)
    if not isinstance(ordini, dict):
        return
    while pb.ordini_nuovi:
        o = pb.ordini_nuovi.pop(0)
        cor = str(getattr(o, "customer_order_ref", None) or getattr(o, "id", ""))[:32]
        ordini.setdefault(cor, o)


def _smonta(st: Dict[str, Any]) -> None:
    client = st.get("client")
    if client is not None:
        try:
            client.ferma()
        except Exception:  # noqa: BLE001
            pass
    pb = st.get("porta_banco")
    if pb is not None:
        pb.metti_giu()
    rip = st.pop("_ripristina", None)
    if rip is not None:
        chi, prima = rip
        if chi == "omega":
            from ...omega import porta_ordini as OPO

            OPO._PORTA = prima
        else:
            from ...safe_strategy import porta_ordini as SPO

            sport = chi.split(":", 1)[1] if ":" in chi else "calcio"
            if prima is None:
                SPO._PORTE.pop(sport, None)
            else:
                SPO._PORTE[sport] = prima


# ---------------------------------------------------------------------------
# la traccia e la parita'
# ---------------------------------------------------------------------------
_CHIAVI_RIGA = ("id", "status", "side", "market_id", "selection_id", "price", "size",
                "mode")


def _num(v: Any) -> Optional[float]:
    try:
        return round(float(v), 2) if v is not None else None
    except (TypeError, ValueError):
        return None


def traccia(st: Dict[str, Any]) -> Dict[str, Any]:
    """La traccia del trasporto di un replay: gli ORDINI usciti dal bot (in
    ordine) e le RIGHE del bot a fine partita (l'esito, come lo vede il bot)."""
    ordini: List[Dict[str, Any]] = []
    pb = st.get("porta_banco")
    if st.get("trasporto") == "canale" and pb is not None:
        acks = {}
        for m in pb.canale.messaggi:
            if m.get("t") == "ack":
                d = m.get("d") or {}
                acks.setdefault(str(d.get("ref")), d)
        for c in pb.comandi:
            d = c.get("d") or {}
            if d.get("azione") != "place":
                ordini.append({"azione": str(d.get("azione")), "ref": str(d.get("ref")),
                               "market_id": str(d.get("market_id")),
                               "t_mercato": c.get("t_mercato")})
                continue
            ack = acks.get(str(d.get("ref"))) or {}
            ordini.append({
                "azione": "place", "ref": str(d.get("ref")),
                "market_id": str(d.get("market_id")),
                "selection_id": int(d.get("selection_id")),
                "side": str(d.get("side")).upper(),
                "price": _num(d.get("price")), "size": _num(d.get("size")),
                "fok": d.get("time_in_force") == "FILL_OR_KILL",
                "t_mercato": c.get("t_mercato"),
                "accettato": ack.get("accettato"), "motivo": ack.get("motivo"),
            })
    else:
        for r in st.get("rest") or []:
            if r.get("azione") == "place":
                ordini.append({k: r.get(k) for k in (
                    "azione", "ref", "market_id", "selection_id", "side", "price", "size",
                    "fok", "t_mercato")})
            else:
                ordini.append({"azione": "cancel", "ref": None,
                               "market_id": r.get("market_id"),
                               "t_mercato": r.get("t_mercato")})
    righe: List[Dict[str, Any]] = []
    strategia = st.get("strategia")
    db = getattr(strategia, "db", None)
    for r in list(getattr(db, "trades", []) or []):
        riga = {k: r.get(k) for k in _CHIAVI_RIGA}
        riga["price"] = _num(riga.get("price"))
        riga["size"] = _num(riga.get("size"))
        righe.append(riga)
    rest_sul_canale = ([r for r in st.get("rest") or []]
                       if st.get("trasporto") == "canale" else [])
    out = {"trasporto": st.get("trasporto"), "bot": st.get("bot"),
           "ordini": ordini, "righe": righe, "durata_s": st.get("durata_s"),
           "rest_sul_canale": rest_sul_canale}
    client = st.get("client")
    if client is not None:
        out["client"] = {"da_seq": getattr(client, "richieste_da_seq", None),
                         "buchi": getattr(client.memoria, "buchi", None),
                         "connessioni": getattr(client, "connessioni", None)}
    if pb is not None:
        out["motore"] = dict(pb.motore.conti)
        out["costo_banco_s"] = round(float(st.get("costo_banco_s") or 0.0), 1)
        out["book"] = st.get("book")
    return out


def _chiave(o: Dict[str, Any]) -> tuple:
    if o.get("azione") != "place":
        return (o.get("azione"), o.get("market_id"))
    return ("place", o.get("ref"), o.get("market_id"), o.get("selection_id"),
            o.get("side"), o.get("price"), o.get("size"), o.get("fok"))


def _secondi(a: Optional[str], b: Optional[str]) -> Optional[float]:
    try:
        return round((datetime.fromisoformat(str(b)) -
                      datetime.fromisoformat(str(a))).total_seconds(), 1)
    except (TypeError, ValueError):
        return None


def confronta(coda: Dict[str, Any], canale: Dict[str, Any]) -> Dict[str, Any]:
    """Il rapporto di parita' fra le due tracce della STESSA registrazione e
    dello STESSO scenario. ``parita`` True solo se ordini (chiave per chiave,
    nello stesso ordine) ed esiti delle righe coincidono; i tempi si riportano
    (scarto per ordine) e NON rompono la parita'."""
    a = [o for o in coda.get("ordini") or []]
    b = [o for o in canale.get("ordini") or []]
    ka, kb = [_chiave(o) for o in a], [_chiave(o) for o in b]
    primo = None
    for i in range(max(len(ka), len(kb))):
        if i >= len(ka) or i >= len(kb) or ka[i] != kb[i]:
            primo = i
            break
    scarti_t = [s for s in (_secondi(x.get("t_mercato"), y.get("t_mercato"))
                            for x, y in zip(a, b)) if s is not None]
    ra = {r.get("id"): r for r in coda.get("righe") or []}
    rb = {r.get("id"): r for r in canale.get("righe") or []}
    righe_diverse = []
    for rid in sorted(set(ra) | set(rb), key=lambda x: (x is None, x)):
        x, y = ra.get(rid), rb.get(rid)
        if x != y:
            righe_diverse.append({"id": rid, "coda": x, "canale": y})
    ordini_uguali = primo is None
    parita = ordini_uguali and not righe_diverse and not canale.get("rest_sul_canale")
    return {
        "parita": parita,
        "ordini_coda": len(a), "ordini_canale": len(b),
        "ordini_uguali": ordini_uguali,
        "primo_scarto": primo,
        "scarto_coda": (a[primo] if primo is not None and primo < len(a) else None),
        "scarto_canale": (b[primo] if primo is not None and primo < len(b) else None),
        "righe_coda": len(ra), "righe_canale": len(rb),
        "righe_diverse": righe_diverse,
        "rest_sul_canale": len(canale.get("rest_sul_canale") or []),
        "scarto_tempi_s": ({"max": max(scarti_t), "min": min(scarti_t),
                            "n": len(scarti_t)} if scarti_t else None),
        "durata_s": {"coda": coda.get("durata_s"), "canale": canale.get("durata_s")},
        "client": canale.get("client"), "motore": canale.get("motore"),
        "costo_banco_s": canale.get("costo_banco_s"), "book": canale.get("book"),
    }


def descrivi(rapporto: Dict[str, Any]) -> List[str]:
    """Il rapporto in righe leggibili (referto e diario)."""
    r = rapporto
    righe = [
        "PARITA' coda/canale: %s | ordini coda=%d canale=%d | righe coda=%d canale=%d | "
        "REST sul canale=%d" % ("RAGGIUNTA" if r["parita"] else "NON RAGGIUNTA",
                                r["ordini_coda"], r["ordini_canale"], r["righe_coda"],
                                r["righe_canale"], r["rest_sul_canale"]),
        "   tempi (canale - coda, s di mercato): %s | durata replay s: %s" % (
            r["scarto_tempi_s"], r["durata_s"]),
        "   client: %s | motore: %s | costo del banco sul canale: %s s su %s book" % (
            r.get("client"), r.get("motore"), r.get("costo_banco_s"), r.get("book")),
    ]
    if r["primo_scarto"] is not None:
        righe.append("   primo scarto all'ordine #%d: coda=%s | canale=%s" % (
            r["primo_scarto"], r["scarto_coda"], r["scarto_canale"]))
    for d in r["righe_diverse"][:6]:
        righe.append("   riga %s diversa: coda=%s | canale=%s" % (d["id"], d["coda"],
                                                                  d["canale"]))
    return righe
