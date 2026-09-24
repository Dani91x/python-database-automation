# -*- coding: utf-8 -*-
"""CONDOTTA DEGLI ORDINI — le regole che i QUATTRO bot tennis condividono.

⚠️ PERCHE' UN MODULO SOLO. Le stesse tre regole servivano a quattro bot scritti
in momenti diversi. Copiarle quattro volte vuol dire quattro copie che
divergono, ed e' il difetto 33 del catalogo (`PROCESSO_STANDARD_BOT.md` §7:
«costante nel frontend che duplica una scelta del backend»). Qui stanno una
volta sola, con i numeri dichiarati e i motivi misurati.

Le tre regole, e da dove vengono:

1. **LA SIZE LEGALE DI GIURISDIZIONE** (`size_legale`). Su .it Betfair RIFIUTA
   un BACK sotto 2,00 EUR o non multiplo di 0,50, e un LAY sotto 0,50 EUR: la
   gamba non parte e la posizione resta SCOPERTA. Lo scalper aveva gia' la sua
   blindatura (`tennis_scalper_bot.py`, `live_min_bet` / `size_step`); pro, flb
   e swing NON l'avevano (referto d'audit 17/09 §E.3 #11). La regola non la
   riscriviamo: si usa `Betfair.stream.live_order_build.min_stake_rules`, che e'
   gia' la barriera del percorso ordini del tennis
   (`tennis_live_order_worker._do_place`).
   * INGRESSI: sotto il minimo si RIFIUTA (non si gonfia lo stake dell'utente).
   * USCITE / COPERTURE (`riduce_liability=True`): si BUMPA al minimo di lato e
     al multiplo di `IT_BACK_STEP`, perche' una copertura che non parte lascia
     una posizione nuda, che e' il rischio maggiore. E' la stessa scelta gia'
     presa per lo scalper.
   * Fuori dal LIVE non si tocca niente: in simulazione la granularita' .it non
     esiste e arrotondare falserebbe il replay (nota gia' in
     `tennis_runner._instantiate_bot`, che azzera `size_step`/`live_min_bet` in
     PAPER e OFF).

2. **IL FRENO DOPO UN RIFIUTO** (`FrenoRifiuti`). Misurato nel replay del 17/09,
   scenario `rifiuti-betfair` su 35794049: con Betfair che rifiuta ogni
   piazzamento il FLB ha ritentato **8.132 volte** e lo scalper **20.534 volte**
   in UNA partita. In LIVE sono altrettante chiamate REST rifiutate, cioe' il
   rate limit di Betfair. Nessuno dei quattro bot aveva un freno.
   La regola: backoff che raddoppia (5, 10, 20, 40, 60 s di TEMPO DI MERCATO,
   poi fisso a 60) e un tetto di tentativi per (mercato, selezione) per partita,
   oltre il quale su quella selezione non si apre piu' e si scrive il motivo.
   I numeri sono scelti prudenti e DICHIARATI: il primo backoff (5 s) copre il
   betDelay del tennis in gioco (5 s, memoria `project_validazione_certezza`),
   cosi' un rifiuto non si ripresenta prima che l'esito precedente sia noto.
   Il freno NON tocca le USCITE: una copertura deve poter partire sempre (la
   sicurezza vince sui costi, stessa regola del tetto transazioni dello scalper).

3. **LO SBILANCIO DI UNA SELEZIONE** (`sbilancio_selezione`). Il blotter di
   flumine e' l'unica fonte di verita' dell'esposizione, e va letto PER
   SELEZIONE, non per ciclo: il micro-residuo che lo scalper accetta per ogni
   ciclo si ACCUMULA (misurato 0,06 EUR oltre la sua stessa tolleranza di 0,02
   con lo slot gia' tornato IDLE), e lo swing ha abbandonato 7,57 EUR su una
   selezione su cui non aveva piu' nessun trade. Qui si somma cio' che il bot ha
   davvero abbinato su quella selezione e si dice di quanto e' sbilanciato.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, Optional, Tuple

from ..live_order_build import (
    IT_BACK_MIN_STAKE,
    IT_BACK_STEP,
    IT_LAY_MIN_SIZE,
    JURISDICTION_IT,
    min_stake_rules,
)

logger = logging.getLogger(__name__)

_EPS = 1e-9

# il minimo per lato su .it, per il bump delle coperture
MINIMO_LATO = {"BACK": IT_BACK_MIN_STAKE, "LAY": IT_LAY_MIN_SIZE}

# IL RESIDUO CHE IL BOT DICHIARA DI ACCETTARE, in EUR di sbilancio su una
# SELEZIONE. Non e' un numero nuovo: e' la tolleranza che lo scalper applica gia'
# alla sorveglianza post-DONE quando ha accettato un micro-residuo
# (`tennis_scalper_bot.py`: `tol = 0.30 if slot.residual_ok else 0.02`).
# Perche' esiste: un residuo di pochi centesimi NON e' chiudibile — qualunque
# ordine di chiusura sarebbe piu' grande del residuo stesso, e pretendere lo zero
# assoluto produce un loop di flatten (misurato il 17/09: 10.840 tentativi in una
# partita). Sotto questa soglia il residuo si DICHIARA; sopra, si appiattisce.
RESIDUO_ACCETTATO = 0.30

# ---------------------------------------------------------------------------
# 1. la size legale di giurisdizione
# ---------------------------------------------------------------------------
def size_legale(size: float, side: str, *, live: bool, giurisdizione: str = JURISDICTION_IT,
                riduce_liability: bool = False) -> Tuple[Optional[float], Optional[str]]:
    """La size da mandare a Betfair, o `(None, motivo)` se non si puo' mandare.

    Fuori dal LIVE la size non si tocca: in simulazione la granularita' .it non
    esiste e arrotondarla falserebbe il confronto fra replay e paper.
    """
    s = round(max(0.0, float(size or 0.0)), 2)
    if s < 0.01:
        return None, "size %.2f sotto il minimo tecnico di 0,01" % s
    if not live:
        return s, None
    lato = str(side or "").upper()
    if lato not in MINIMO_LATO:
        return None, "side non valido: %r" % side
    if riduce_liability:
        # UNA COPERTURA DEVE PARTIRE. Sotto il minimo di lato si BUMPA (e sul
        # BACK si sale al multiplo di 0,50): un over-hedge di pochi centesimi e'
        # sempre meglio di una gamba scoperta. E' la scelta gia' presa per lo
        # scalper (`live_min_bet` / `size_step`), qui resa comune ai quattro.
        minimo = MINIMO_LATO[lato]
        if s + 1e-9 < minimo:
            s = minimo
        if lato == "BACK":
            # al multiplo di 0,50 PER ECCESSO: verso il basso si tornerebbe
            # sotto la copertura che serve. `- 1e-9` perche' una size gia'
            # multipla (2,50) non deve salire al gradino dopo.
            passi = math.ceil(s / IT_BACK_STEP - 1e-9)
            s = max(minimo, passi * IT_BACK_STEP)
        return round(s, 2), None
    # INGRESSO: non si gonfia lo stake che l'utente ha acceso. Se non e' legale,
    # non si piazza e si dice perche'.
    verdetto = min_stake_rules(giurisdizione, lato.lower(), 0.0, s,
                               reduces_liability=False)
    if not verdetto.valid:
        return None, str(verdetto.reason or "size non legale")
    return round(float(verdetto.legalized_size), 2), None


# ---------------------------------------------------------------------------
# 2. il freno dopo un rifiuto
# ---------------------------------------------------------------------------
# 24/09 (D2): il freno e' stato SPOSTATO nel modulo condiviso
# `Betfair/stream/trading/freno_rifiuti.py` per montarlo anche nello scalper
# calcio. Comportamento INVARIATO per i quattro bot tennis: stessi default
# (5-10-20-40-60 s di tempo di mercato, tetto 20 per mercato e selezione,
# conteggio NON azzerato dal successo). Il test di parita'
# `tests/test_freno_parita_2026_09_24.py` lo prova sul vecchio comportamento.
from ..trading.freno_rifiuti import (  # noqa: E402,F401 - re-export
    BACKOFF_S,
    TETTO_RIFIUTI,
    FrenoRifiuti,
)


# ---------------------------------------------------------------------------
# lo stato di un ordine, letto come si DEVE leggere
# ---------------------------------------------------------------------------
# `OrderStatus` e' un Enum: `str(stato)` da' "OrderStatus.EXECUTABLE" e
# confrontarlo con "EXECUTABLE" non matcha MAI (catalogo §7.10). Si legge
# `.value`, e si ripiega su `.name` solo se il valore non c'e'.
STATI_VIVI = frozenset({"Pending", "Cancelling", "Updating", "Replacing",
                        "Executable"})


def stato_ordine(order: Any) -> Optional[str]:
    st = getattr(order, "status", None)
    if st is None:
        return None
    v = getattr(st, "value", None)
    if v is not None:
        return str(v)
    n = getattr(st, "name", None)
    return str(n) if n is not None else str(st)


def ordine_vivo(order: Any) -> bool:
    """True se l'ordine e' ancora sul book. `None` (mai piazzato) = NON vivo."""
    if order is None:
        return False
    return str(stato_ordine(order) or "") in STATI_VIVI


def ingresso_finito(order: Any) -> bool:
    """L'ingresso e' FINITO: l'ordine esiste, non e' piu' vivo e non ha abbinato
    niente. Succede quando Betfair lo fa scadere alla sospensione (persistenza
    LAPSE: il punto uccide l'appoggiato) o quando lo cancella.

    Serve per NON aspettare il timeout su un ordine che a mercato non esiste
    piu': il bot crederebbe di avere una quota appoggiata che Betfair ha gia'
    ucciso (§6.4, «l'ordine appoggiato scade alla sospensione»).
    """
    if order is None:
        return False
    if ordine_vivo(order):
        return False
    if stato_ordine(order) is None:
        return False            # mai piazzato: lo gestisce il freno dei rifiuti
    return float(getattr(order, "size_matched", 0.0) or 0.0) <= _EPS


# ---------------------------------------------------------------------------
# 3. lo sbilancio di una selezione, dal blotter
# ---------------------------------------------------------------------------
def abbinato_selezione(market: Any, strategia: Any,
                       selection_id: int) -> Tuple[float, float, float, float]:
    """(back, prezzo medio back, lay, prezzo medio lay) della STRATEGIA su UNA
    selezione, letti dal blotter di flumine. Mai numeri ricalcolati a mano.

    ⚠️ Solleva se il blotter non e' leggibile: un'esposizione non letta NON e'
    un'esposizione nulla (difetto 12 del referto d'audit: `orders = []` su
    eccezione faceva dichiarare piatta una posizione aperta).
    """
    b = bw = l = lw = 0.0
    for o in (market.blotter.strategy_orders(strategia) or []):
        if int(getattr(o, "selection_id", 0) or 0) != int(selection_id):
            continue
        sm = float(getattr(o, "size_matched", 0.0) or 0.0)
        ap = float(getattr(o, "average_price_matched", 0.0) or 0.0)
        if sm <= _EPS or ap <= 0:
            continue
        if str(getattr(o, "side", "") or "").upper() == "BACK":
            b += sm
            bw += sm * ap
        else:
            l += sm
            lw += sm * ap
    return b, (bw / b if b else 0.0), l, (lw / l if l else 0.0)


def sbilancio_selezione(market: Any, strategia: Any,
                        selection_id: int) -> Optional[float]:
    """Quanto vale, in EUR, lo sbilancio ABBINATO su una selezione.

    `abs(profitto_se_vince - profitto_se_perde)`: zero = posizione pari, cioe'
    l'esito del mercato non cambia piu' il risultato. `None` = il blotter non e'
    leggibile, e allora NON si conclude niente (fail-safe).
    """
    try:
        b, ba, l, la = abbinato_selezione(market, strategia, selection_id)
    except Exception as ex:  # noqa: BLE001 - blotter illeggibile: non si conclude
        logger.warning("[condotta] blotter illeggibile su sel=%s: %s — "
                       "l'esposizione NON e' dichiarata piatta", selection_id, ex)
        return None
    se_vince = b * (ba - 1.0) - l * (la - 1.0)
    se_perde = l - b
    return abs(se_vince - se_perde)


def ordini_vivi_su(market: Any, strategia: Any, selection_id: int) -> Optional[bool]:
    """Il bot ha ANCORA un ordine vivo sul book, su quella selezione?

    ⚠️ Serve prima di dichiarare chiusa una posizione. `market.cancel_order` e'
    ASINCRONA: l'ordine passa per `Cancelling` prima di morire, e in quella
    finestra puo' ANCORA RIEMPIRSI. Dichiarare «flat» guardando solo l'abbinato
    di adesso significa dimenticare un ordine che fra un tick sara' una
    posizione (misurato il 17/09 sul replay: il PRO andava FLAT con lo sbilancio
    a 0,002 e si ritrovava 3,52 EUR scoperti poco dopo; il FLB dichiarava DONE
    con 2,00 EUR ancora `Cancelling`).

    `None` = il blotter non e' leggibile: non si conclude niente.
    """
    try:
        for o in (market.blotter.strategy_orders(strategia) or []):
            if int(getattr(o, "selection_id", 0) or 0) != int(selection_id):
                continue
            if ordine_vivo(o):
                return True
        return False
    except Exception as ex:  # noqa: BLE001 - illeggibile: non si conclude
        logger.warning("[condotta] blotter illeggibile su sel=%s: %s",
                       selection_id, ex)
        return None


def dichiara_chiusura_mercato(market: Any, strategia: Any, sink: Any,
                              selezioni: Any, bot: str) -> None:
    """LA FASE DI SETTLEMENT, che nessuno dei quattro bot aveva.

    Quando il mercato CHIUDE il bot non riceve piu' book (`check_market_book`
    accetta solo `OPEN`): qualunque posizione ancora creduta aperta resterebbe
    li' per sempre, e il referto la vedrebbe come «il bot sorveglia il nulla»
    (misurato: K4 al settlement su 35795739). Al fischio finale si dichiara che
    cosa c'era aperto, con l'esposizione VERA letta dal blotter, e si chiude la
    memoria: da quel momento la posizione la regola Betfair, non il bot.
    """
    if not selezioni:
        return
    aperte = []
    for sel in list(selezioni):
        sb = sbilancio_selezione(market, strategia, int(sel))
        aperte.append({"selection_id": int(sel),
                       "sbilancio": None if sb is None else round(sb, 3)})
    if sink is None:
        return
    try:
        sink("mercato_chiuso", {
            "bot": bot,
            "market_id": str(getattr(market, "market_id", "") or ""),
            "posizioni_aperte_al_fischio": aperte,
            "note": ("il mercato e' CHIUSO: da qui in poi l'esito lo decide "
                     "Betfair. La memoria del bot su queste selezioni e' stata "
                     "chiusa, il P&L regolato e' in `pnl_settled`."),
        })
    except Exception:  # noqa: BLE001 - la telemetria non rompe il settlement
        pass


def piatta(market: Any, strategia: Any, selection_id: int,
           tolleranza: float) -> bool:
    """True SOLO se lo sbilancio e' dentro la tolleranza DICHIARATA dal bot.
    Blotter illeggibile -> False: mai dichiarare piatta una posizione non vista."""
    sb = sbilancio_selezione(market, strategia, selection_id)
    if sb is None:
        return False
    return sb <= float(tolleranza)
