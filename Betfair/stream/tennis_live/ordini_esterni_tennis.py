# -*- coding: utf-8 -*-
"""ordini_esterni_tennis.py - i 4 bot tennis sanno SUBITO degli ordini esterni (W3b, 08/10/2026).

Ordine dell'utente (08/10): "quando intervengo io dal sito o dall'app su
un'operazione dei bot, i bot lo sanno e non fanno altro". Prima di oggi
``tennis_scalper``, ``tennis_pro``, ``tennis_flb`` e ``tennis_swing`` leggevano
l'esposizione SOLO dal blotter della propria strategia: gli ordini manuali del
ladder stanno sotto la capture (``tennis_live_order_worker._capture_strategy``) e
quelli del sito non li vedeva nessuno (``chiusura_manuale.py``, docstring).

La regola e la logica sono quelle comuni (``tennis_scalper.ordini_esterni``); qui
c'e' solo il collegamento al runner tennis:
  * LIVE: lo STESSO osservatore del runner calcio sul flumine del runner tennis
    (stream ordini del conto: nessuna chiamata in piu'), una ``Registro`` per
    framework (``registro_per_framework``), una sorveglianza per bot ospitato;
  * PAPER: gli ordini manuali SIMULATI del ladder di questo stesso processo
    (``session.tracked_orders``, ``mode='paper'``), letti a ogni book del bot
    (``FontePaperManuali``). Paper e live mai mescolati: la sorveglianza ha la
    modalita' con cui il bot ESEGUE (``tennis_live_order_worker._modo_strategia``,
    la regola della UI);
  * SECONDO GIRO (08/10, coordinatore): un ordine di un BOT passato dalla coda del
    runner tennis porta lo stesso ``customerStrategyRef`` del ladder (``tennis``).
    Si riconosce con la regola di W2: in-process dalla riga di coda che il runner
    ha eseguito (``tracked_orders[...]['coda']`` + ``motivo_bot_da_coda``, o
    l'attore del motore), poi sul DB (``live_order_worker._proprietari_bot``) in un
    thread suo, una lettura per bet_id nuovo. Finche' non si sa, il bot e'
    SOSPESO su quella selezione (il controllo di flumine rifiuta ogni suo ordine
    nuovo); di un bot -> riprende; fuori bot -> intervento; DB illeggibile -> resta
    sospeso e lo scrive;
  * l'intervento: nel thread di flumine annullo dei vivi del bot e
    ``_disable_strategy`` (nessuna decisione piu'); il ``bot_control_worker``
    scrive poi la riga 'stopped' col marcatore ``chiusura_manuale`` (il ponte non
    la riarma: ``chiusura_manuale.chiusi_dall_utente``) e le attivita'
    (``concludi_interventi``): niente I/O nel thread di flumine.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..tennis_scalper import ordini_esterni as OE

logger = logging.getLogger(__name__)

#: il valore di ``stats.chiusura_manuale.come`` per un intervento esterno
COME = "intervento_utente"
#: tetto della memoria degli ordini piazzati dal runner (un processo vive giorni)
MAX_ORDINI = 5000


class MemoriaOrdiniRunner:
    """Gli ordini che il runner tennis ha piazzato per la coda DB, il /order del
    desktop o il motore (``session.tracked_orders``), RICORDATI anche dopo che il
    worker toglie i terminali dal tracking. Per ognuno si sa se e' di un BOT con
    la regola di W2: l'attore del motore (``source`` diverso da 'manual') o la riga
    di coda (``motivo_bot_da_coda``: ``client_ref``/``params`` di un bot)."""

    def __init__(self, session: Any) -> None:
        self.session = session
        self._rec: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def aggiorna(self) -> None:
        tracciati = getattr(self.session, "tracked_orders", None) or {}
        with self._lock:
            for ref, rec in list(tracciati.items()):
                if isinstance(rec, dict) and rec.get("order") is not None:
                    self._rec.setdefault(str(ref), rec)
            while len(self._rec) > MAX_ORDINI:
                self._rec.pop(next(iter(self._rec)))

    @staticmethod
    def motivo_bot(rec: Dict[str, Any]) -> Optional[str]:
        from ..trading.esposizione_fuori_bot import motivo_bot_da_coda

        src = str(rec.get("source") or "manual").strip().lower()
        if src != "manual":
            return "attore:%s" % src
        coda = rec.get("coda")
        return motivo_bot_da_coda(coda) if isinstance(coda, dict) else None

    def elenco(self) -> List[Tuple[str, Dict[str, Any]]]:
        self.aggiorna()
        with self._lock:
            return list(self._rec.items())

    def bot_per_bet_id(self, bet_ids: List[str]) -> Dict[str, str]:
        """bet_id -> motivo, per quelli che il runner sa essere di un bot."""
        voluti = {str(b) for b in bet_ids}
        out: Dict[str, str] = {}
        for _ref, rec in self.elenco():
            bid = str(getattr(rec.get("order"), "bet_id", None) or "")
            if bid in voluti:
                m = self.motivo_bot(rec)
                if m:
                    out[bid] = m
        return out


def _memoria(session: Any) -> MemoriaOrdiniRunner:
    mem = getattr(session, "memoria_ordini_runner", None)
    if mem is None:
        mem = MemoriaOrdiniRunner(session)
        try:
            session.memoria_ordini_runner = mem
        except Exception:  # noqa: BLE001 - sessione finta senza slot
            pass
    return mem


def conferma_tennis(session: Any, framework: Any, registro: Any) -> OE.ConfermaBot:
    """La classificazione "del bot / fuori bot" per il runner tennis: prima la
    memoria in-process (riga di coda eseguita da QUESTO runner), poi il DB con la
    regola di W2 (``_proprietari_bot``). Thread suo; a lettura fatta un evento
    nella coda di flumine fa decidere subito."""
    mem = _memoria(session)

    def _leggi(bet_ids: List[str]) -> Dict[str, str]:
        out = mem.bot_per_bet_id(list(bet_ids))
        resto = [b for b in bet_ids if b not in out]
        if resto:
            from .. import live_order_worker as _LOW
            from . import tennis_db

            out.update(_LOW._proprietari_bot(tennis_db.get_tennis_client(), resto))
        return out

    def _sveglia() -> None:
        from flumine.events.events import CustomEvent

        framework.handler_queue.put(CustomEvent(None, lambda _fw, _ev: registro.rivedi()))

    return OE.ConfermaBot(_leggi, sveglia=_sveglia)


def registro_per_framework(framework: Any, mode: str,
                           session: Any = None) -> Optional[OE.Registro]:
    """Il registro del framework appena costruito. LIVE: osservatore montato
    sullo stream ordini del conto, verifica "del bot / fuori bot" sul DB. Con
    ordini abilitati: il controllo di flumine della sospensione. Interruttore
    spento: ``None`` (come prima)."""
    if not OE.acceso():
        return None
    try:
        reg = OE.Registro()
        live = str(mode or "").strip().upper() == "LIVE"
        reg.montato = live and OE.monta_su_flumine(framework, reg)
        reg.prefissi = OE.prefissi_bot()
        reg.conferma = (conferma_tennis(session, framework, reg)
                        if (live and session is not None) else None)
        if session is not None:
            # la coda degli ordini del runner si fotografa PRIMA di giudicare la
            # fotografia dello stream (il worker toglie i terminali dopo)
            reg.prima_di_valutare = _memoria(session).aggiorna
        OE.monta_controllo(framework)
        return reg
    except Exception as ex:  # noqa: BLE001 - senza registro: come prima
        logger.warning("[tennis-esterni] registro NON costruito: %s", str(ex)[:160])
        return None


class FontePaperManuali:
    """Gli ordini simulati del ladder su UN mercato, nella grafia del conto, SENZA
    quelli dei bot (riga di coda o attore: regola di W2, in-process). Ricordati
    anche dopo che il worker li toglie dal tracking (terminali): un ordine
    abbinato e concluso fra due book resta un intervento."""

    def __init__(self, session: Any, market_id: str) -> None:
        self.session = session
        self.market_id = str(market_id)

    def __call__(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for ref, rec in _memoria(self.session).elenco():
            if str(rec.get("mode") or "").lower() != "paper":
                continue
            o = rec.get("order")
            if str(getattr(o, "market_id", "") or "") != self.market_id:
                continue
            if MemoriaOrdiniRunner.motivo_bot(rec):
                continue                      # ordine di un bot: non e' l'utente
            out.append({
                "betId": str(getattr(o, "bet_id", None) or ref),
                "marketId": self.market_id,
                "selectionId": getattr(o, "selection_id", None),
                "side": getattr(o, "side", None),
                "sizeMatched": float(getattr(o, "size_matched", 0.0) or 0.0),
                "averagePriceMatched": getattr(o, "average_price_matched", None),
                "placedDate": getattr(o, "date_time_created", None),
                # il terminale manuale del tennis (coda DB e /order del desktop)
                "customerStrategyRef": OE.RIF_MANUALE_TENNIS,
                "customerOrderRef": str(ref),
            })
        return out


def _ordini_del_bot(framework: Any, bot: Any, market_id: str) -> List[Tuple[Any, Any]]:
    m = framework.markets.markets.get(str(market_id)) if framework is not None else None
    if m is None:
        return []
    try:
        return [(m, o) for o in list(m.blotter.strategy_orders(bot) or [])]
    except Exception:  # noqa: BLE001 - blotter mutato: nessun ordine in questo giro
        return []


def proteggi_bot(session: Any, framework: Any, event_id: str, bot_key: str, bot: Any, *,
                 disabilita: Callable[[Any], None]) -> Optional[OE.Sorveglianza]:
    """La sorveglianza di UN bot ospitato. ``None`` = nessuna fonte (interruttore
    spento, bot in dry-run, modalita' OFF, live senza osservatore): il bot resta
    identico a prima. ``disabilita`` e' ``tennis_runner._disable_strategy``."""
    reg = getattr(session, "ordini_esterni", None)
    if reg is None or bot is None:
        return None
    try:
        if getattr(bot, "dry_run", False):
            return None            # nessun ordine possibile: niente da proteggere
        from .tennis_live_order_worker import _modo_strategia

        modo = _modo_strategia(bot, session)
        mid = str(getattr(bot, "_tennis_scoped_market_id", "") or "")
        if not mid or modo not in ("paper", "live"):
            return None
        if modo == "live" and not getattr(reg, "montato", False):
            return None
        pendenti = _pendenti(session)
        attivita = _attivita_pendenti(session)

        def _al_intervento(evento: Dict[str, Any]) -> None:
            evento["annullo"] = OE.annulla_vivi(_ordini_del_bot(framework, bot, mid))
            disabilita(bot)
            pendenti.append((str(event_id), str(bot_key), id(bot), dict(evento)))
            logger.critical("[tennis-esterni] %s@%s: ordine dell'UTENTE (%s, %s) abbinato "
                            "sul suo mercato: il bot si ferma (annullo dei vivi, nessuna "
                            "copertura)", bot_key, event_id, evento.get("dove"), modo)

        def _evento(kind: str, payload: Dict[str, Any]) -> None:
            attivita.append((str(event_id), str(bot_key), str(kind), dict(payload)))

        sorv = OE.Sorveglianza(
            nome="%s:%s" % (bot_key, event_id), modo=modo,
            rif_manuali=(OE.RIF_MANUALE_TENNIS,),
            prefissi=getattr(reg, "prefissi", None) or OE.prefissi_bot(),
            identita=OE.Identita([bot]),
            bet_ids_propri=lambda: {str(o.bet_id) for _m, o in
                                    _ordini_del_bot(framework, bot, mid)
                                    if getattr(o, "bet_id", None)},
            mercati_del_bot=lambda: {mid},
            al_intervento=_al_intervento, adesso_ms=OE.adesso_ms,
            inizio_ms=OE.adesso_ms(),
            fonte_paper=FontePaperManuali(session, mid) if modo == "paper" else None,
            # live: la verifica sul DB; paper: la fonte in-process e' gia' esatta
            conferma=getattr(reg, "conferma", None) if modo == "live" else None,
            su_evento=_evento)
        if modo == "live":
            reg.aggiungi(sorv)
        OE.proteggi_strategia(bot, sorv)
        return sorv
    except Exception as ex:  # noqa: BLE001 - senza sorveglianza: come prima
        logger.warning("[tennis-esterni] %s@%s: sorveglianza NON montata: %s",
                       bot_key, event_id, str(ex)[:160])
        return None


def _lista_di_sessione(session: Any, nome: str) -> List[Any]:
    lst = getattr(session, nome, None)
    if lst is None:
        lst = []
        try:
            setattr(session, nome, lst)
        except Exception:  # noqa: BLE001 - sessione finta senza slot
            pass
    return lst


def _pendenti(session: Any) -> List[Tuple[str, str, int, Dict[str, Any]]]:
    return _lista_di_sessione(session, "interventi_esterni")


def _attivita_pendenti(session: Any) -> List[Tuple[str, str, str, Dict[str, Any]]]:
    return _lista_di_sessione(session, "attivita_esterni")


def concludi_interventi(session: Any, flumine: Any, *, e_flat: Callable[[Any, Any], bool],
                        db: Any = None) -> List[Tuple[str, str]]:
    """Dal ``bot_control_worker`` (fuori dal thread di flumine): le attivita' della
    verifica (in verifica, di un bot, non verificabile) e, per ogni bot fermato da
    un intervento dell'utente, la riga 'stopped' col marcatore che il ponte legge
    per non riarmarlo e l'attivita'. Ritorna le (partita, bot) fermate."""
    from .. import avvio_app as AA
    from . import chiusura_manuale as CM
    from . import tennis_db

    db = db if db is not None else tennis_db
    att = getattr(session, "attivita_esterni", None) or []
    while att:
        ev, bot_key, kind, payload = att.pop(0)
        try:
            db.write_tennis_bot_activity(ev, bot_key, kind, payload)
        except Exception as ex:  # noqa: BLE001 - best-effort
            logger.warning("[tennis-esterni] attivita' %s %s/%s KO: %s", kind, ev, bot_key, ex)
    pend = getattr(session, "interventi_esterni", None) or []
    fatti: List[Tuple[str, str]] = []
    while pend:
        ev, bot_key, ist, evento = pend.pop(0)
        strat = (getattr(session, "hosted", {}) or {}).get((ev, bot_key))
        try:
            flat = bool(e_flat(flumine, strat)) if strat is not None else False
        except Exception:  # noqa: BLE001 - blotter illeggibile = non pari
            flat = False
        stats = AA.stats_timbrate(getattr(strat, "stats", None), AA.boot_id_ambiente())
        stats[CM.CHIAVE_STATS] = {"come": COME, "dove": evento.get("dove"),
                                  "mode": evento.get("modo"), "flat": flat,
                                  "ts": tennis_db._now_iso()}
        stats[OE.KIND] = {k: evento.get(k) for k in (
            "dove", "modo", "fonte", "market_id", "selection_id", "side", "bet_id",
            "abbinato_nuovo", "latenza_ms")}
        try:
            db.set_tennis_bot_status(ev, bot_key, "stopped", stopped=True, stats=stats)
        except Exception as ex:  # noqa: BLE001 - l'attivita' si scrive comunque
            logger.warning("[tennis-esterni] stato %s/%s KO: %s", ev, bot_key, ex)
        try:
            db.write_tennis_bot_activity(ev, bot_key, OE.KIND, {
                **evento, "flat": flat, "istanza": ist,
                "nota": ("ordine dell'utente abbinato sul mercato del bot: il bot ha "
                         "annullato i suoi ordini vivi e non opera piu' su questa "
                         "partita finche' non lo riarmi" + (
                             "" if flat else " - la sua posizione resta aperta: "
                             "verificala sul ladder"))})
        except Exception as ex:  # noqa: BLE001 - best-effort
            logger.warning("[tennis-esterni] attivita' %s/%s KO: %s", ev, bot_key, ex)
        fatti.append((ev, bot_key))
    return fatti
