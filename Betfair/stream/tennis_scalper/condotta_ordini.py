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
   * INGRESSI: sotto il minimo accettato da Betfair si PORTA AL MINIMO (BACK
     2,00 EUR, LAY 0,50 EUR) e si piazza. DECISIONE DELL'UTENTE del 28/09
     ("porta al limite minimo accettato"): prima si rifiutava. Sopra il minimo
     il BACK resta arrotondato PER DIFETTO al multiplo di 0,50 (regola .it,
     invariata). Fonte del minimo: documentazione ufficiale Betfair, "Italian
     Exchange Specific Bet Rules" (back >= 200 centesimi a multipli di 50; lay
     con stake del back corrispondente >= 50 centesimi).
   * USCITE / COPERTURE (`riduce_liability=True`): si BUMPA al minimo di lato e
     al multiplo di `IT_BACK_STEP`, perche' una copertura che non parte lascia
     una posizione nuda, che e' il rischio maggiore. E' la stessa scelta gia'
     presa per lo scalper.
   * `live=False` = nessuna regola: resta SOLO per gli strumenti di ricerca
     (backtest di laboratorio con `live_min_bet=0`). In produzione PAPER e LIVE
     passano `live=True` (28/09, paper = specchio del live:
     `tennis_runner._instantiate_bot` da' `live_min_bet`/`size_step` a entrambi).

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
from ..trading.submin import FlumineSubminOps
from ..trading.submin import porta_al_minimo_apertura as _porta_al_minimo

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

    `live=False` (solo strumenti di ricerca): la size non si tocca. PAPER e LIVE
    di produzione passano `live=True` e ricevono la STESSA size.
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
        # 28/09 - REGOLA PERMANENTE DELL'UTENTE: "le chiusure devono sempre
        # essere perfette e spalmare il profitto o la loss su entrambe le
        # selezioni". Prima qui la copertura si GONFIAVA al gradino da 0,50
        # sopra (2,02 -> 2,50): la chiusura non era esatta e la posizione
        # restava sbilanciata dall'altra parte. Ora una copertura esce SEMPRE
        # all'importo esatto al centesimo: diretta se Betfair la accetta cosi'
        # (``diretta_ok``), altrimenti con l'USCITA ESATTA (``UsciteEsatte``:
        # parte diretta + resto col place-and-trim). Qui arriva solo la parte
        # diretta: una size non diretta e' un errore del chiamante, mai gonfiata.
        if diretta_ok(s, lato):
            return s, None
        return None, ("copertura %.2f %s non piazzabile direttamente: va per "
                      "l'uscita esatta (place-and-trim), mai gonfiata" % (s, lato))
    # INGRESSO (28/09, decisione dell'utente): sotto il minimo accettato si
    # PORTA AL MINIMO del lato. Solo verso l'alto e solo fino al minimo: sopra
    # il minimo vale la regola .it di sempre (BACK al multiplo di 0,50 per
    # difetto, dentro `min_stake_rules`).
    s = _porta_al_minimo(giurisdizione, lato.lower(), s)
    verdetto = min_stake_rules(giurisdizione, lato.lower(), 0.0, s,
                               reduces_liability=False)
    if not verdetto.valid:
        return None, str(verdetto.reason or "size non legale")
    return round(float(verdetto.legalized_size), 2), None


def diretta_ok(size: float, side: str) -> bool:
    """La size si piazza DIRETTAMENTE su .it? BACK >= 2,00 e multiplo di 0,50;
    LAY >= 0,50 (per il lay la documentazione non chiede multipli)."""
    s = round(float(size or 0.0), 2)
    lato = str(side or "").upper()
    if lato == "BACK":
        return s + 1e-9 >= IT_BACK_MIN_STAKE and \
            abs(s / IT_BACK_STEP - round(s / IT_BACK_STEP)) < 1e-6
    if lato == "LAY":
        return s + 1e-9 >= IT_LAY_MIN_SIZE
    return False


def spezza_esatta(size: float, side: str) -> Tuple[float, float]:
    """(parte diretta, resto per il place-and-trim) di una chiusura ESATTA.

    LAY >= 0,50 -> tutto diretto. BACK >= 2,00 -> il multiplo di 0,50 per
    difetto diretto, il resto (< 0,50) col place-and-trim. Sotto il minimo del
    lato -> tutto col place-and-trim. La somma e' SEMPRE la size chiesta."""
    s = round(float(size or 0.0), 2)
    lato = str(side or "").upper()
    if diretta_ok(s, lato):
        return s, 0.0
    if lato == "BACK" and s + 1e-9 >= IT_BACK_MIN_STAKE:
        diretta = round(math.floor(s / IT_BACK_STEP + 1e-9) * IT_BACK_STEP, 2)
        return diretta, round(s - diretta, 2)
    return 0.0, s


class OrdineComposto:
    """UNA chiusura esatta vista dal bot come UN ordine (stesse chiavi che i
    bot leggono da un ordine flumine: ``side``, ``selection_id``,
    ``market_id``, ``order_type.price/size``, ``size_matched``,
    ``average_price_matched``, ``size_remaining``, ``status`` Enum, ``bet_id``).

    Dentro: la parte diretta (un ordine vero) e la sequenza place-and-trim del
    resto (gli ordini veri del Trade della sequenza, rimpiazzi compresi). Tutti
    gli ordini sono nel blotter della strategia: l'esposizione la legge sempre
    il blotter, questo oggetto serve solo a sorvegliare la chiusura."""

    def __init__(self, side: str, price: float, size: float, selection_id: int,
                 market_id: str) -> None:
        from types import SimpleNamespace

        self.side = str(side).upper()
        self.selection_id = int(selection_id)
        self.market_id = str(market_id)
        self.order_type = SimpleNamespace(price=float(price), size=round(float(size), 2),
                                          persistence_type="LAPSE")
        self.diretto: Any = None
        self.sequenza: Optional[Dict[str, Any]] = None

    def parti(self) -> list:
        out = []
        if self.diretto is not None:
            out.append(self.diretto)
        seq = self.sequenza
        if seq is not None:
            base = seq.get("order") or getattr(seq.get("ops"), "last_order", None)
            tr = getattr(base, "trade", None) if base is not None else None
            ordini = list(getattr(tr, "orders", None) or []) if tr is not None else []
            for o in (ordini or ([base] if base is not None else [])):
                if all(o is not p for p in out):
                    out.append(o)
        return out

    @property
    def size_matched(self) -> float:
        return round(sum(float(getattr(o, "size_matched", 0.0) or 0.0)
                         for o in self.parti()), 2)

    @property
    def average_price_matched(self) -> float:
        m = w = 0.0
        for o in self.parti():
            sm = float(getattr(o, "size_matched", 0.0) or 0.0)
            ap = float(getattr(o, "average_price_matched", 0.0) or 0.0)
            if sm > 0 and ap > 0:
                m += sm
                w += sm * ap
        return w / m if m else 0.0

    @property
    def size_remaining(self) -> float:
        return round(max(0.0, self.order_type.size - self.size_matched), 2)

    def in_corso(self) -> bool:
        """La sequenza del resto non e' ancora terminale (DONE/ABORTED)."""
        seq = self.sequenza
        if seq is None:
            return False
        return str(getattr(seq["state"].step, "value", seq["state"].step)) not in (
            "done", "aborted")

    @property
    def status(self) -> Any:
        from flumine.order.order import OrderStatus

        if self.in_corso() or any(ordine_vivo(o) for o in self.parti()):
            return OrderStatus.EXECUTABLE
        return OrderStatus.EXECUTION_COMPLETE

    @property
    def completa(self) -> bool:
        """La chiusura e' ABBINATA per intero (abbinato == chiesto al
        centesimo). ATTENZIONE: ``status`` dice solo se a mercato c'e' ancora
        qualcosa di vivo; una sequenza ABORTITA a meta' ha ``status``
        EXECUTION_COMPLETE ma ``completa`` falso e ``size_remaining`` > 0: la
        chiusura NON e' finita. Chi decide "chiusura finita" guarda questo (o
        ``size_remaining``), mai lo stato."""
        return self.size_remaining <= 0.0

    @property
    def bet_id(self) -> Optional[str]:
        for o in self.parti():
            b = getattr(o, "bet_id", None)
            if b:
                return b
        return None


class UsciteEsatte:
    """CHIUSURE A IMPORTO ESATTO per i bot tennis pro/FLB/swing (28/09).

    La STESSA macchina dello scalper tennis (``TennisScalperStrategy.
    _place_exact``/``_drive_submins``) e del worker: ``trading.submin``
    (parcheggio del minimo a quota non abbinabile, riduzione alla size voluta,
    rimpiazzo alla quota vera), con ``FlumineSubminOps`` sul Market che il bot
    riceve (``MercatoConClient`` nel runner LIVE: il client del bot resta il
    suo). Nessuna copia della sequenza. Il bot:
      * chiama ``piazza`` per una copertura NON diretta (``diretta_ok`` falso);
      * chiama ``avanza(market)`` a ogni book, PRIMA delle sue decisioni;
      * annulla con ``annulla(market, ordine)`` (anche un ``OrdineComposto``)."""

    def __init__(self, strategia: Any, emit: Any = None) -> None:
        self._s = strategia
        self._emit = emit
        self._n = 0
        self.attive: list = []          # OrdineComposto con sequenza in corso
        # ANTI-CASCATA (lezione live 02/07: un flatten in trend genero' 2355
        # sequenze in una partita). Base: 30 s fra due sequenze per (mercato,
        # selezione), come `TennisScalperStrategy._SUBMIN_MIN_INTERVAL_MS`,
        # sull'orologio DEL MERCATO del bot (`_orologio_s`: replay = paper =
        # live). 28/09 sera (revisione, regola dell'utente "nessuna gamba resta
        # scoperta per un limite nostro"): la rinuncia NON e' mai definitiva.
        # Dopo ogni sequenza FALLITA l'intervallo raddoppia (30, 60, 120, 240,
        # poi fisso 300 s) e al primo SUCCESSO torna a 30 s. Ogni blocco e ogni
        # fallimento scrivono una riga di attivita' CRITICA con quanto resta
        # scoperto: l'utente puo' chiudere a mano. Solo `UsciteEsatte`: lo
        # scalper tennis ha le sue regole certificate e non si tocca.
        self._avvii: Dict[Tuple[str, int], list] = {}
        self._fallite: Dict[Tuple[str, int], int] = {}
        self._blocco_detto: Dict[Tuple[str, int], float] = {}

    INTERVALLO_S = 30.0
    INTERVALLO_MAX_S = 300.0

    def intervallo_s(self, chiave: Tuple[str, int]) -> float:
        """30 s, poi raddoppia a ogni sequenza fallita consecutiva, tetto 300 s."""
        n = int(self._fallite.get(chiave, 0))
        return min(self.INTERVALLO_MAX_S, self.INTERVALLO_S * (2 ** n))

    def _conta_fallita(self, comp: OrdineComposto, motivo: str) -> None:
        chiave = (comp.market_id, comp.selection_id)
        self._fallite[chiave] = self._fallite.get(chiave, 0) + 1
        self._e("uscita_esatta_abort", level="CRITICAL", sel=comp.selection_id,
                market_id=comp.market_id, motivo=str(motivo)[:200],
                scoperto=comp.size_remaining, lato=comp.side,
                prossima_prova_s=self.intervallo_s(chiave),
                note=("chiusura NON completa: %.2f EUR %s della selezione %s restano "
                      "scoperti; nuovo tentativo fra %.0f s. Puoi chiudere a mano "
                      "dal Terminale." % (comp.size_remaining, comp.side,
                                          comp.selection_id, self.intervallo_s(chiave))))

    def _conta_riuscita(self, comp: OrdineComposto) -> None:
        self._fallite.pop((comp.market_id, comp.selection_id), None)

    def _ora(self) -> float:
        f = getattr(self._s, "_orologio_s", None)
        if callable(f):
            try:
                return float(f())
            except Exception:  # noqa: BLE001
                pass
        import time as _t

        return _t.time()

    def _sequenza_permessa(self, chiave: Tuple[str, int], resto: float, lato: str) -> bool:
        avvii = self._avvii.get(chiave) or []
        if not avvii:
            return True
        attesa = self.intervallo_s(chiave)
        manca = attesa - (self._ora() - avvii[-1])
        if manca <= 0:
            return True
        # BLOCCO: la riga CRITICA si scrive UNA volta per finestra d'attesa
        # (il bot richiama a ogni book: mai una riga per book)
        if self._blocco_detto.get(chiave) != avvii[-1]:
            self._blocco_detto[chiave] = avvii[-1]
            self._e("uscita_esatta_attesa", level="CRITICAL", sel=chiave[1],
                    market_id=chiave[0], scoperto=round(float(resto), 2), lato=lato,
                    attesa_s=round(manca, 1), fallite=int(self._fallite.get(chiave, 0)),
                    note=("%.2f EUR %s della selezione %s restano SCOPERTI per circa "
                          "%.0f s (anti-cascata del place-and-trim). Puoi chiudere a "
                          "mano dal Terminale." % (resto, lato, chiave[1], manca)))
        return False

    def _e(self, kind: str, **p: Any) -> None:
        if callable(self._emit):
            try:
                self._emit(kind, **p)
            except Exception:  # noqa: BLE001 - la telemetria non ferma l'uscita
                pass

    def piazza(self, market: Any, sel: int, side: str, price: float, size: float,
               diretto: Any) -> Optional[OrdineComposto]:
        """La chiusura ESATTA: ``diretto(size)`` piazza la parte diretta col
        ``_place`` del bot (stesse guardie), il resto parte col place-and-trim.
        None = niente e' partito (il bot riprova, come per un rifiuto)."""
        from ..live_order_build import round_to_tick
        from ..trading.submin import SubminState, SubminStep

        parte, resto = spezza_esatta(size, side)
        comp = OrdineComposto(side, price, round(parte + resto, 2), sel,
                              str(getattr(market, "market_id", "") or ""))
        chiave = (comp.market_id, int(sel))
        if resto >= 0.01 and not self._sequenza_permessa(chiave, resto, str(side).upper()):
            resto_bloccato = True
        else:
            resto_bloccato = False
        if parte > 0:
            comp.diretto = diretto(parte)
            if comp.diretto is None:
                return None          # la parte diretta non e' partita: si riprova
        if resto >= 0.01 and not resto_bloccato:
            self._n += 1
            self._avvii.setdefault(chiave, []).append(self._ora())
            ops = _OpsCattura(selection_id=int(sel), handicap=0.0,
                              jurisdiction=JURISDICTION_IT, strategy=self._s)
            state = SubminState(step=SubminStep.INIT, bet_id=None,
                                target_size=round(resto, 2),
                                target_price=round_to_tick(price),
                                placed_size=IT_BACK_MIN_STAKE,   # parcheggio legale .it
                                side=str(side).lower(), note="uscita esatta")
            ref = ("ue%d-%d" % (int(sel) % 10 ** 9, self._n))[:32]
            comp.sequenza = {"state": state, "ops": ops, "order": None, "ref": ref,
                             "market_id": comp.market_id}
            self._e("uscita_esatta", sel=int(sel), side=str(side).upper(),
                    price=float(price), size=round(parte + resto, 2),
                    diretta=parte, place_and_trim=round(resto, 2))
            self.attive.append(comp)
            self._passo(market, comp)       # gradino 1 subito (come lo scalper)
        if comp.diretto is None and comp.sequenza is None:
            return None
        return comp

    def _passo(self, market: Any, comp: OrdineComposto) -> None:
        from ..trading.submin import advance_submin

        seq = comp.sequenza
        if seq is None or not comp.in_corso():
            return
        base = seq.get("order") or getattr(seq["ops"], "last_order", None)
        if base is not None:
            ordini = list(getattr(getattr(base, "trade", None), "orders", None) or [])
            seq["order"] = ordini[-1] if ordini else base
        try:
            nuovo = advance_submin(market, seq["state"], order=seq.get("order"),
                                   jurisdiction=JURISDICTION_IT,
                                   customer_order_ref=seq["ref"], ops=seq["ops"])
        except Exception as ex:  # noqa: BLE001 - sequenza fallita: si DICHIARA
            from dataclasses import replace as _r

            from ..trading.submin import SubminStep

            seq["state"] = _r(seq["state"], step=SubminStep.ABORTED,
                              note="errore: %s" % str(ex)[:160])
            self._conta_fallita(comp, str(ex))
            return
        if seq.get("order") is None and getattr(seq["ops"], "last_order", None) is not None:
            seq["order"] = seq["ops"].last_order
        if nuovo.step is not seq["state"].step:
            self._e("uscita_esatta_passo", sel=comp.selection_id,
                    passo=str(getattr(nuovo.step, "value", nuovo.step)))
        seq["state"] = nuovo
        if nuovo.step is not seq.get("_ultimo_passo"):
            seq["_ultimo_passo"] = nuovo.step
            valore = str(getattr(nuovo.step, "value", ""))
            if valore == "aborted":
                self._conta_fallita(comp, str(nuovo.note))
            elif valore == "done":
                self._conta_riuscita(comp)

    def avanza(self, market: Any) -> None:
        """UN passo per ogni sequenza del mercato (idempotente, come
        ``_drive_submins``). Le terminali escono dall'elenco."""
        mid = str(getattr(market, "market_id", "") or "")
        for comp in list(self.attive):
            if comp.market_id != mid:
                continue
            self._passo(market, comp)
            if not comp.in_corso():
                self.attive.remove(comp)

    def annulla(self, market: Any, ordine: Any) -> None:
        """Annulla un ordine del bot; un ``OrdineComposto`` annulla le sue parti
        vive e chiude la sequenza (ABORTED: mai un rimpiazzo dopo l'annullo)."""
        if ordine is None:
            return
        if not isinstance(ordine, OrdineComposto):
            try:
                market.cancel_order(ordine)
            except Exception:  # noqa: BLE001
                pass
            return
        if ordine.sequenza is not None and ordine.in_corso():
            from dataclasses import replace as _r

            from ..trading.submin import SubminStep

            ordine.sequenza["state"] = _r(ordine.sequenza["state"], step=SubminStep.ABORTED,
                                          note="annullata dal bot")
        for o in ordine.parti():
            if ordine_vivo(o):
                try:
                    market.cancel_order(o)
                except Exception:  # noqa: BLE001
                    pass


class _OpsCattura(FlumineSubminOps):
    """``FlumineSubminOps`` che ricorda l'ordine del parcheggio (come
    ``_CapturingOps`` dello scalper tennis, ma per ISTANZA: due sequenze non
    si rubano l'ordine)."""

    last_order: Any = None

    def place(self, market_: Any, **kw: Any) -> Any:  # noqa: D102
        o = super().place(market_, **kw)
        self.last_order = o
        return o


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


# ---------------------------------------------------------------------------
# 4. "CHIUDI ORA" - l'uscita MANUALE chiesta dall'utente (D3, 24/09)
# ---------------------------------------------------------------------------
# Decisione dell'utente del 24/09: il "Chiudi" della Control Room deve
# funzionare anche per i quattro bot tennis. NON e' una strategia nuova e non
# cambia nessuna condizione d'ingresso o d'uscita: e' un COMANDO che il bot
# esegue con la SUA macchina d'uscita gia' esistente (lo scalper col suo
# `force_flat`, il pro col suo stato CLOSING, lo swing col suo `closing`, il
# FLB con la sua copertura di green), con motivo `manuale`:
#   * annulla gli ordini vivi;
#   * chiude l'ABBINATO (mai il chiesto) al prezzo di mercato;
#   * non rientra su quella partita: da qui il bot non apre piu' niente.
# Il protocollo e' lo stesso per i quattro (una regola, un posto):
#   * il RUNNER alza `uscita_manuale_chiesta` (`chiedi_uscita_manuale`), dal
#     suo thread, e non tocca altro;
#   * il BOT, al primo book utile, decide l'esito UNA volta
#     (`registra_esito_manuale`) e avvia la sua uscita;
#   * il BOT dice quando la sua uscita e' finita (`uscita_manuale_finita()`);
#     la verita' sul flat la dice poi il blotter (`tennis_runner`).
# ANTI DOPPIA USCITA: se il bot stava GIA' uscendo, l'esito e' "gia' in
# uscita" e nessun secondo ordine parte: resta in volo la copertura che c'era.
MOTIVO_USCITA_MANUALE = "manuale"
ESITO_USCITA_AVVIATA = "uscita_avviata"
ESITO_GIA_IN_USCITA = "gia_in_uscita"
ESITO_NESSUNA_POSIZIONE = "nessuna_posizione"
ESITI_USCITA_MANUALE = frozenset({ESITO_USCITA_AVVIATA, ESITO_GIA_IN_USCITA,
                                  ESITO_NESSUNA_POSIZIONE})


def supporta_uscita_manuale(strategia: Any) -> bool:
    """Il bot parla il protocollo del "chiudi ora"? Un bot che non lo parla
    non riceve il comando (il runner rifiuta la richiesta, mai un'alzata di
    flag che nessuno legge)."""
    return (hasattr(strategia, "uscita_manuale_chiesta")
            and hasattr(strategia, "uscita_manuale")
            and callable(getattr(strategia, "uscita_manuale_finita", None)))


def chiedi_uscita_manuale(strategia: Any) -> bool:
    """Il runner chiede l'uscita manuale. True se la chiede ADESSO, False se
    era gia' stata chiesta (idempotente: una seconda richiesta non produce un
    secondo comando)."""
    if bool(getattr(strategia, "uscita_manuale_chiesta", False)):
        return False
    strategia.uscita_manuale_chiesta = True
    return True


def registra_esito_manuale(strategia: Any, esito: str, **dettagli: Any) -> None:
    """Il bot scrive l'esito della richiesta UNA sola volta (il primo vince) e
    lo dice nella sua attivita' (`uscita_manuale`)."""
    if getattr(strategia, "uscita_manuale", None) is not None:
        return
    if esito not in ESITI_USCITA_MANUALE:
        raise ValueError("esito dell'uscita manuale sconosciuto: %s" % esito)
    payload = {"esito": esito, "motivo": MOTIVO_USCITA_MANUALE}
    payload.update(dettagli)
    strategia.uscita_manuale = dict(payload)
    emit = getattr(strategia, "_emit", None)
    if callable(emit):
        try:
            emit("uscita_manuale", **payload)
        except Exception:  # noqa: BLE001 - la telemetria non ferma l'uscita
            logger.debug("[condotta] attivita' uscita manuale KO", exc_info=True)
