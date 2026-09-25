"""trasporto_rapido.py - il profilo «di minuti» del trasporto dell'ordine (F4).

Ordine dell'utente (25/09): «voglio test di MINUTI, non di ore; mi vanno bene
anche test molto ridotti». Il replay intero di una partita serve a dire se la
TRACCIA DELLE DECISIONI resta identica cambiando il trasporto (parita', vedi
``trasporto.confronta``); i GUASTI del trasporto invece non hanno bisogno di
una partita intera: bastano un mercato vero, i suoi book veri e il codice vero.

    python -m Betfair.stream.backtest.certifica safe_base 35760084 --scenari rapidi
    python -m Betfair.stream.backtest.certifica omega 35760084 --scenari rapidi \
        --trasporto entrambi

LA CATENA DI OGNI SCENARIO (nessun pezzo sostituito):
    registrazione vera -> FlumineSimulation + MotoreReplay (book veri, bet delay)
    -> funzione di invio VERA del bot (Safe: ``execution.place`` con la porta;
       Omega: ``omega_service._place_via_canale``)
    -> client VERO (``PortaCanale`` / ``PortaCanaleOmega``, col suo thread)
    -> ``WsBanco`` -> ``MotoreOrdini`` VERO -> ``live_order_worker._dispatch``
    -> ``Market`` di flumine (matching, FOK, controlli nativi)
    -> specchio del blotter -> eventi ``order`` -> memoria del client
    -> risoluzione VERA della riga (Safe: ``bot_service._risolvi_una_via_canale``;
       Omega: ``omega_service._risolvi_via_canale``) sul DB in memoria del banco.

GLI SCENARI (ognuno con i suoi controlli; «N/A» detto col motivo):
  R1 accettato        - ordine abbinabile: ack accettato, UN ordine su flumine,
                        evento terminale, riga 'open' con l'abbinato vero;
  R2 freno            - ordine non abbinabile (quota 1,01, FOK): ucciso, riga
                        'error', nessun abbinato; e a mercato SOSPESO (primo
                        book sospeso della registrazione): nessun abbinato;
  R3 parziale         - Safe/Omega live sono FOK: la parte non coperta si
                        uccide tutta (0 abbinato); Omega PAPER (senza FOK):
                        abbinato in parte, riga NON chiusa, numeri sulla riga;
  R4 canale giu'      - regola D5: apertura NON inviata e MAI in REST; chiusura
                        sul REST di oggi (ripiego dichiarato);
  R5 duplicato        - stesso ref due volte: una sola esecuzione;
  R6 comando vecchio  - arrivato oltre ``max_eta_ms``: rifiutato, riga 'error';
  R7 kill-switch      - apertura rifiutata, chiusura (riduzione verificata)
                        eseguita;
  R8 sotto il minimo  - place-and-trim dal canale (Safe; Omega N/A: stake 1 EUR
                        di lay sopra il minimo 0,50);
  R9 sequenza         - nessuna tempesta di ``da_seq`` (reperto del 25/09);
  R10 non seguito     - 25/09 AUTO-FOLLOW: il runner NON segue la partita; il
                        comando e' accettato ``in_aggancio``, il mercato entra
                        nella sottoscrizione (``AutoFollow`` di produzione) e
                        l'ordine parte al primo book: UN ordine, nessun REST;
  R10b tetto pieno    - tetto dei mercati pieno: l'evento automatico meno
                        prioritario e SENZA ordini viene espulso, il comando e'
                        accettato ed eseguito;
  R10c mai espulsi    - tetto pieno di mercati con ORDINI (o seguiti a mano):
                        niente espulso, rifiuto dichiarato ``tetto_mercati_pieno``,
                        nessun ordine;
  R10d mai in silenzio- mercato che non arriva mai (inesistente): dopo
                        ``aggancio_max_ms`` evento terminale ``rifiutato``
                        col motivo ``in_aggancio``, riga error, nessun ordine.
"""
from __future__ import annotations

import io
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import trasporto as TRA

#: lo scenario del bot che PRODUCE ordini sulla registrazione di riferimento
#: (35760084): e' su quello che si misura la parita' coda/canale
SCENARIO_ORDINI = {"safe_base": "ordini-manuali", "safe_esatto": "ordini-manuali",
                   "safe_punta": "ordini-manuali", "omega": "apertura"}

#: quanti book al massimo si leggono per trovare il mercato sospeso (R2b)
MAX_BOOK_SOSPESO = 400000


class _Esito:
    def __init__(self, nome: str) -> None:
        self.nome = nome
        self.controlli: List[Tuple[str, bool, str]] = []
        self.na: Optional[str] = None
        self.durata_s = 0.0
        self.errore: Optional[str] = None

    def controlla(self, desc: str, ok: bool, dettaglio: Any = "") -> bool:
        self.controlli.append((desc, bool(ok), str(dettaglio)[:240]))
        return bool(ok)

    @property
    def ok(self) -> bool:
        return self.errore is None and all(c[1] for c in self.controlli)

    def riga(self) -> str:
        if self.na:
            return "N/A %s (%s)" % (self.nome, self.na)
        segno = "OK " if self.ok else "KO "
        return "%s %s  controlli=%d  %.1f s" % (segno, self.nome, len(self.controlli),
                                               self.durata_s)


# ---------------------------------------------------------------------------
# il banco rapido: un mercato vero, il motore vero, il client vero
# ---------------------------------------------------------------------------
class BancoRapido:
    def __init__(self, attore: str, event_id: str, data_dir: str) -> None:
        from flumine import BaseStrategy, FlumineSimulation

        from .banco_comune import (MercatoFlumine, MotoreReplay, GeneratoreLibri,
                                   assicura_middleware_simulato, cliente_simulato)
        from .porta_banco import PortaBanco, TOKEN_BANCO

        self.attore = attore
        self.event_id = str(event_id)
        raw = os.path.join(data_dir, str(event_id), "%s.raw.jsonl" % event_id)
        if not os.path.exists(raw):
            raise FileNotFoundError("registrazione assente: %s" % raw)

        class _Muta(BaseStrategy):
            """La strategia flumine sotto cui il motore crea gli ordini: nel
            banco rapido NON decide niente (a decidere e' lo scenario, che
            chiama la funzione d'invio vera del bot)."""

            mercati: Dict[str, Any] = {}

            def check_market_book(self, market: Any, market_book: Any) -> bool:
                return False

        self.strat = _Muta(market_filter={"markets": [raw]}, max_order_exposure=1e9,
                           max_selection_exposure=1e9, max_trade_count=int(1e9),
                           max_live_trade_count=int(1e9))
        self.strat.mercati = {}
        self.quadro = FlumineSimulation(client=cliente_simulato())
        assicura_middleware_simulato(self.quadro)
        self.quadro.add_strategy(self.strat)
        self.motore = MotoreReplay(self.quadro)
        self.mercato_rest = MercatoFlumine(self.strat, self.motore)
        self.strat.mercato = self.mercato_rest
        self.rest: List[Dict[str, Any]] = []
        self._GeneratoreLibri = GeneratoreLibri
        self._PortaBanco = PortaBanco
        self._TOKEN = TOKEN_BANCO
        self.pb: Any = None
        self.client: Any = None
        self.market_id: Optional[str] = None
        self.market: Any = None
        self.book: Any = None
        self._ctx: List[Any] = []

    # ------------------------------------------------------------- ciclo
    def __enter__(self) -> "BancoRapido":
        q = self.quadro
        self._ctx = [q, q.simulated_datetime]
        q.__enter__()
        q.simulated_datetime.__enter__()
        stream = list(q.streams)[0]
        q.simulated_datetime.reset_real_datetime()
        self.motore.generatore = self._GeneratoreLibri(stream)
        self.motore._gen = self.motore.generatore.veloce()
        # spia del REST del banco: nel trasporto canale deve restare muto
        # salvo il ripiego D5 delle chiusure
        st = {"rest": self.rest}
        TRA._registra_rest(st, self.mercato_rest, self.motore)
        return self

    def __exit__(self, *_a: Any) -> None:
        self.smonta_porta()
        try:
            self.quadro.simulated_datetime.__exit__(None, None, None)
        finally:
            self.quadro.__exit__(None, None, None)

    def ora(self) -> datetime:
        o = self.motore._ora_mercato
        return o if isinstance(o, datetime) else datetime.now(timezone.utc)

    def un_book(self) -> Optional[Any]:
        mb = self.motore._prossimo()
        if mb is None:
            return None
        mercato, _nuovo = self.motore._a_flumine(mb)
        if mercato is not None:
            self.strat.mercati[str(mb.market_id)] = mercato
            if str(mb.market_id) == self.market_id:
                self.book = mb
                self.market = mercato
        if self.pb is not None:
            self.pb.aggiorna()
            self.pb.attendi_client()
        return mb

    def pompa(self, secondi: float) -> int:
        """Fa scorrere ``secondi`` di tempo di mercato (book veri)."""
        inizio = self.motore._ora_mercato
        n = 0
        while True:
            mb = self.un_book()
            if mb is None:
                return n
            n += 1
            ora = self.motore._ora_mercato
            if inizio is None:
                inizio = ora
            if (ora - inizio).total_seconds() >= secondi:
                return n

    def trova_match_odds(self, max_book: int = 200000) -> bool:
        """Il primo book di MATCH_ODDS APERTO, prima del fischio, con quote
        vere su entrambi i lati della prima selezione."""
        for _ in range(max_book):
            mb = self.un_book()
            if mb is None:
                return False
            md = getattr(mb, "market_definition", None)
            if md is None or str(getattr(md, "market_type", "")) != "MATCH_ODDS":
                continue
            if mb.status != "OPEN" or bool(getattr(mb, "inplay", False)):
                continue
            if self._lato(mb, "lay") and self._lato(mb, "back"):
                self.market_id = str(mb.market_id)
                self.book = mb
                self.market = self.strat.mercati.get(self.market_id)
                return True
        return False

    @staticmethod
    def _lato(mb: Any, lato: str) -> Optional[Tuple[int, float, float]]:
        for r in getattr(mb, "runners", []) or []:
            ex = getattr(r, "ex", None)
            lv = getattr(ex, "available_to_lay" if lato == "lay" else "available_to_back",
                         None) or []
            if lv:
                p = lv[0]
                prezzo = float(getattr(p, "price", None) or p["price"])
                size = float(getattr(p, "size", None) or p["size"])
                if prezzo > 1.01 and size >= 2.0:
                    return int(r.selection_id), prezzo, size
        return None

    def quota(self, lato: str) -> Optional[Tuple[int, float, float]]:
        return self._lato(self.book, lato) if self.book is not None else None

    # ------------------------------------------------------------- porta
    def monta_porta(self) -> None:
        self.smonta_porta()
        self.pb = self._PortaBanco(self.quadro, self.strat, attore=self.attore,
                                   modo_processo="LIVE")
        self.pb.orologio_mercato = lambda: TRA._ora_mercato(self.motore)
        if self.attore == "omega":
            from ...omega import porta_ordini as OPO

            self.client = OPO.PortaCanaleOmega(porta_ws=0, attore="omega", sport="calcio",
                                               connetti=self.pb.connetti,
                                               token_fn=lambda: self._TOKEN)
            self._rip = ("omega", OPO._PORTA)
            OPO._PORTA = self.client
        else:
            from ...safe_strategy import porta_ordini as SPO

            self.client = SPO.PortaCanale(porta_ws=0, attore="safe", sport="calcio",
                                          connetti=self.pb.connetti,
                                          token_fn=lambda: self._TOKEN)
            self._rip = ("safe", SPO._PORTE.get("calcio"))
            SPO._PORTE["calcio"] = self.client
        self.client.avvia()
        self.attendi(lambda: self.client.disponibile(), 5.0)

    def smonta_porta(self) -> None:
        if self.client is not None:
            try:
                self.client.ferma()
            except Exception:  # noqa: BLE001
                pass
        if self.pb is not None:
            self.pb.metti_giu()
        rip = getattr(self, "_rip", None)
        if rip is not None:
            chi, prima = rip
            if chi == "omega":
                from ...omega import porta_ordini as OPO

                OPO._PORTA = prima
            else:
                from ...safe_strategy import porta_ordini as SPO

                if prima is None:
                    SPO._PORTE.pop("calcio", None)
                else:
                    SPO._PORTE["calcio"] = prima
            self._rip = None
        self.pb = None
        self.client = None

    @staticmethod
    def attendi(pred: Callable[[], Any], timeout_s: float) -> bool:
        fine = time.monotonic() + timeout_s
        while time.monotonic() < fine:
            if pred():
                return True
            time.sleep(0.002)
        return bool(pred())

    def ordini_del_motore(self) -> List[Any]:
        return list(self.pb.ordini_visti.values()) if self.pb is not None else []


# ---------------------------------------------------------------------------
# gli attori: la funzione d'invio e la risoluzione VERE del bot
# ---------------------------------------------------------------------------
class _Safe:
    nome = "safe"

    def __init__(self, banco: BancoRapido) -> None:
        from ...safe_strategy.tools.replay_registrazioni import DbSafeMemoria

        self.b = banco
        self.db = DbSafeMemoria({"id": 1, "status": "running", "mode": "live",
                                 "params": {}, "stats": {}},
                                orologio=lambda: banco.ora().timestamp())

    def riserva(self, *, side: str, price: float, size: float, mode: str = "live",
                closes: Optional[int] = None) -> int:
        riga = {"event_id": self.b.event_id, "market_id": self.b.market_id,
                "selection_id": None, "side": side, "price": price, "size": size,
                "status": "pending", "mode": mode, "strategy": "base",
                "meta": {"phase": "reserved"}}
        if closes:
            riga["closes_trade_id"] = closes
            riga["meta"]["closes_trade_id"] = closes
        return int(self.db.insert_trade(riga))

    def invia(self, tid: int, *, selection_id: int, side: str, price: float, size: float,
              mode: str = "live", closes: Optional[int] = None, porta: Any = None) -> Any:
        from ...safe_strategy import execution as X

        self.db.update_trade(tid, selection_id=selection_id)
        meta: Dict[str, Any] = {"closes_trade_id": closes} if closes else {}
        return X.place(db=self.db, market=self.b.mercato_rest, mode=mode,
                       event_id=self.b.event_id, market_id=self.b.market_id,
                       selection_id=selection_id, side=side, price=price, size=size,
                       client_ref="safe-t%d" % tid, trade_id=tid, meta=meta,
                       now=self.b.ora(), params={"execution_mode": "rest"},
                       porta=(porta if porta is not None else self.b.client))

    def risolvi(self, tid: int) -> Dict[str, Any]:
        from ...safe_strategy import bot_service as BS

        tr = self.riga(tid)
        if tr.get("status") == "pending":
            BS._risolvi_una_via_canale(self.db, tr, now=self.b.ora(),
                                       os_mod=BS._omega_service())
        return self.riga(tid)

    def riga(self, tid: int) -> Dict[str, Any]:
        for r in self.db.trades:
            if int(r.get("id") or 0) == int(tid):
                return dict(r)
        return {}


class _Omega:
    nome = "omega"

    def __init__(self, banco: BancoRapido) -> None:
        from ...omega import omega_config
        from ...omega.tools.replay_registrazioni import DbMemoriaOmega

        self.b = banco
        self.params = omega_config.resolve_params(dict(omega_config.DEFAULTS))
        self.db = DbMemoriaOmega({"id": 1, "status": "running", "mode": "live",
                                  "params": dict(self.params), "daily_goal": 5.0,
                                  "stats": {}})
        self.db.orologio = lambda: banco.ora().isoformat()

    def riserva(self, *, side: str, price: float, size: float, mode: str = "live",
                closes: Optional[int] = None) -> int:
        riga = {"event_id": self.b.event_id, "market_id": self.b.market_id,
                "selection_id": None, "side": side, "price": price, "size": size,
                "status": "pending", "mode": mode, "phase": "rapido",
                "meta": {"phase": "reserved", "requested_size": size}}
        if closes:
            riga["closes_trade_id"] = closes
        return int(self.db.insert_trade(riga))

    def invia(self, tid: int, *, selection_id: int, side: str, price: float, size: float,
              mode: str = "live", closes: Optional[int] = None, porta: Any = None) -> Any:
        from ...omega import omega_service as S
        from ...omega import porta_ordini as OPO
        from ...safe_strategy import execution as X

        self.db.update_trade(tid, selection_id=selection_id)
        p = porta if porta is not None else self.b.client
        if closes:
            # le chiusure di Omega passano da ``X.close_trade`` con la vista
            # FOK + riduzione (``_porta_kw_chiusura``): stesso ``X.place``
            return X.place(db=self.db, market=self.b.mercato_rest, mode=mode,
                           event_id=self.b.event_id, market_id=self.b.market_id,
                           selection_id=selection_id, side=side, price=price, size=size,
                           client_ref=OPO.ref_ordine(tid), trade_id=tid,
                           meta={"closes_trade_id": closes}, now=self.b.ora(),
                           params=dict(self.params),
                           porta=OPO.VistaOmega(p, time_in_force=OPO.FOK, riduce=True))
        return S._place_via_canale(p, db=self.db, trade_id=tid, market_id=self.b.market_id,
                                   selection_id=selection_id, side=side, price=price,
                                   size=size, mode=mode, now=self.b.ora(),
                                   base_meta={"requested_size": size})

    def risolvi(self, tid: int) -> Dict[str, Any]:
        from ...omega import omega_service as S

        tr = self.riga(tid)
        if tr.get("status") == "pending":
            S._risolvi_via_canale(tr, db=self.db, params=self.params,
                                  market=self.b.mercato_rest, now=self.b.ora())
        return self.riga(tid)

    def riga(self, tid: int) -> Dict[str, Any]:
        for r in self.db.trades:
            if int(r.get("id") or 0) == int(tid):
                return dict(r)
        return {}


# ---------------------------------------------------------------------------
# gli scenari
# ---------------------------------------------------------------------------
def _ack_di(b: BancoRapido, ref: str) -> Dict[str, Any]:
    a = b.pb._ack.get(ref) if b.pb is not None else None
    return dict(a or {})


def _fasi(b: BancoRapido, ref: str) -> List[str]:
    return [e.get("fase") for e in (b.pb.esiti(ref) if b.pb is not None else [])]


def _aspetta_terminale(b: BancoRapido, ref: str, secondi: float = 30.0) -> Optional[str]:
    from ...safe_strategy import porta_ordini as SPO

    inizio = b.motore._ora_mercato
    while True:
        ev = b.client.esiti(ref) if b.client is not None else None
        if ev is not None and SPO.terminale(ev):
            return str(ev.get("fase"))
        if b.un_book() is None:
            return None
        if (b.motore._ora_mercato - inizio).total_seconds() > secondi:
            ev = b.client.esiti(ref)
            return str(ev.get("fase")) if ev else None


def esegui_scenari(bot: str, event_id: str, data_dir: str) -> List[_Esito]:
    attore = TRA.attore_di(bot)
    if attore is None:
        raise ValueError("bot %r senza porta a comandi" % bot)
    esiti: List[_Esito] = []
    from .banco_comune import simulazione_flumine

    with simulazione_flumine(), BancoRapido(attore, event_id, data_dir) as b:
        t0 = time.monotonic()
        if not b.trova_match_odds():
            e = _Esito("R0 mercato")
            e.errore = "nessun MATCH_ODDS aperto con quote su entrambi i lati"
            e.controlli.append(("mercato trovato", False, ""))
            return [e]
        b.monta_porta()
        A = _Omega(b) if attore == "omega" else _Safe(b)
        pref = "omega-t" if attore == "omega" else "safe-t"
        stato: Dict[str, Any] = {}
        for nome, fn in (("R1 accettato", _r1), ("R2 freno", _r2),
                         ("R3 parziale", _r3), ("R4 canale giu'", _r4),
                         ("R5 duplicato", _r5), ("R6 comando vecchio", _r6),
                         ("R7 kill-switch", _r7), ("R8 sotto il minimo", _r8),
                         ("R9 sequenza", _r9), ("R10 mercato non seguito", _r10),
                         ("R10b tetto pieno", _r10b), ("R10c mai espulsi", _r10c),
                         ("R10d aggancio mai in silenzio", _r10d),
                         ("R2b mercato sospeso", _r2b)):
            e = _Esito(nome)
            t = time.monotonic()
            try:
                fn(b, A, pref, e, stato)
            except Exception as ex:  # noqa: BLE001 - uno scenario che esplode e' KO
                import traceback

                e.errore = "%s: %s" % (type(ex).__name__, str(ex)[:200])
                e.controlli.append(("scenario eseguito senza eccezioni", False,
                                    traceback.format_exc(limit=3)[-400:]))
            e.durata_s = time.monotonic() - t
            esiti.append(e)
        stato["durata_totale_s"] = time.monotonic() - t0
    return esiti


def _conta_rest(b: BancoRapido) -> int:
    return len(b.rest)


def _r1(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    sel, prezzo, disp = b.quota("lay")
    size = 2.0
    tid = A.riserva(side="lay", price=prezzo, size=size)
    ref = "%s%d" % (pref, tid)
    rest0, ord0 = _conta_rest(b), len(b.ordini_del_motore())
    t = time.perf_counter()
    out = A.invia(tid, selection_id=sel, side="lay", price=prezzo, size=size)
    stato["latenza_invio_ms"] = round((time.perf_counter() - t) * 1000.0, 2)
    e.controlla("esito dell'invio 'pending' (esito dal canale)",
                getattr(out, "status", None) == "pending", out)
    ack = _ack_di(b, ref)
    e.controlla("ack accettato dal motore", ack.get("accettato") is True, ack)
    fase = _aspetta_terminale(b, ref)
    e.controlla("evento terminale arrivato al client", fase is not None, fase)
    e.controlla("UN solo ordine su flumine per il comando",
                len(b.ordini_del_motore()) - ord0 == 1,
                len(b.ordini_del_motore()) - ord0)
    e.controlla("nessuna chiamata REST", _conta_rest(b) == rest0, b.rest[rest0:])
    riga = A.risolvi(tid)
    ev = b.client.esiti(ref) or {}
    stato["r1_tid"], stato["r1_sel"] = tid, sel
    stato["r1_matched"] = float(ev.get("size_matched") or 0.0)
    if fase == "abbinato":
        e.controlla("riga 'open' con l'abbinato del runner",
                    riga.get("status") == "open" and abs(float(riga.get("size") or 0)
                                                         - stato["r1_matched"]) < 0.01,
                    {k: riga.get(k) for k in ("status", "size", "price", "bet_id")})
        e.controlla("bet_id della riga = bet_id dell'evento",
                    str(riga.get("bet_id")) == str(ev.get("bet_id")), riga.get("bet_id"))
    else:
        e.controlla("riga chiusa in 'error' se il FOK non ha abbinato",
                    riga.get("status") == "error", riga.get("status"))


def _r2(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    sel, _prezzo, _disp = b.quota("lay")
    tid = A.riserva(side="lay", price=1.01, size=2.0)
    ref = "%s%d" % (pref, tid)
    A.invia(tid, selection_id=sel, side="lay", price=1.01, size=2.0)
    fase = _aspetta_terminale(b, ref)
    e.controlla("quota non abbinabile: evento terminale senza abbinato",
                fase in ("annullato", "scaduto", "rifiutato"), fase)
    ev = b.client.esiti(ref) or {}
    e.controlla("abbinato 0", float(ev.get("size_matched") or 0.0) == 0.0, ev.get("size_matched"))
    riga = A.risolvi(tid)
    e.controlla("riga in 'error' (nessun fill inventato)", riga.get("status") == "error",
                riga.get("status"))


def _r3(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    sel, prezzo, disp = b.quota("lay")
    size = round(disp * 3 + 50.0, 2)            # piu' di quanto il book copre
    tid = A.riserva(side="lay", price=prezzo, size=size)
    ref = "%s%d" % (pref, tid)
    A.invia(tid, selection_id=sel, side="lay", price=prezzo, size=size)
    fase = _aspetta_terminale(b, ref)
    ev = b.client.esiti(ref) or {}
    e.controlla("LIVE FOK oltre la liquidita': ucciso, 0 abbinato (mai un parziale)",
                fase in ("annullato", "scaduto") and float(ev.get("size_matched") or 0) == 0,
                (fase, ev.get("size_matched")))
    riga = A.risolvi(tid)
    e.controlla("riga 'error'", riga.get("status") == "error", riga.get("status"))
    if A.nome != "omega":
        e.controlli.append(("PAPER senza FOK: N/A per Safe (FOK anche in paper)", True, ""))
        return
    # Omega PAPER: senza FOK l'ordine lavora il book -> parziale
    tid2 = A.riserva(side="lay", price=prezzo, size=size, mode="paper")
    ref2 = "%s%d" % (pref, tid2)
    A.invia(tid2, selection_id=sel, side="lay", price=prezzo, size=size, mode="paper")
    b.pompa(2.0)
    ev2 = b.client.esiti(ref2) or {}
    abb = float(ev2.get("size_matched") or 0.0)
    e.controlla("PAPER senza FOK: abbinato in parte, residuo vivo",
                0 < abb < size and float(ev2.get("size_remaining") or 0) > 0,
                (ev2.get("fase"), abb, ev2.get("size_remaining")))
    e.controlla("evento intermedio (non terminale)", ev2.get("fase") == "abbinato_parziale",
                ev2.get("fase"))
    riga2 = A.risolvi(tid2)
    e.controlla("riga ancora 'pending' con l'abbinato vero sulla riga (C.12a)",
                riga2.get("status") == "pending"
                and abs(float(riga2.get("size_matched") or 0) - abb) < 0.01,
                {k: riga2.get(k) for k in ("status", "size_matched", "size_remaining")})
    # si annulla il residuo per non lasciare un ordine vivo agli scenari dopo
    from ...safe_strategy import execution as X
    from ...omega import porta_ordini as OPO

    X.annulla_su_betfair(None, bet_id=str(ev2.get("bet_id")), market_id=b.market_id,
                         porta=OPO.VistaOmega(b.client), mode="paper")


def _r4(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    b.pb.metti_giu()
    b.attendi(lambda: not b.client.disponibile(), 5.0)
    e.controlla("il client vede il canale giu'", not b.client.disponibile(), "")
    sel, prezzo, _d = b.quota("lay")
    cmd0, rest0 = len(b.pb.comandi), _conta_rest(b)
    tid = A.riserva(side="lay", price=prezzo, size=2.0)
    out = A.invia(tid, selection_id=sel, side="lay", price=prezzo, size=2.0)
    e.controlla("APERTURA a canale giu': NON inviata, errore certo",
                getattr(out, "status", None) == "error"
                and "canale_giu" in str(getattr(out, "fill_note", "")), out)
    e.controlla("APERTURA mai sul REST (D5)", _conta_rest(b) == rest0, b.rest[rest0:])
    e.controlla("nessun comando al motore", len(b.pb.comandi) == cmd0, "")
    # CHIUSURA a canale giu' (della posizione di R1, se abbinata): ripiego REST
    matched = float(stato.get("r1_matched") or 0.0)
    if matched <= 0:
        e.controlli.append(("chiusura a canale giu': N/A (R1 non abbinato)", True, ""))
    else:
        sel_b, prezzo_b, _db = b.quota("back")
        tid_c = A.riserva(side="back", price=prezzo_b, size=matched,
                          closes=stato["r1_tid"])
        out_c = A.invia(tid_c, selection_id=stato["r1_sel"], side="back", price=prezzo_b,
                        size=matched, closes=stato["r1_tid"])
        e.controlla("CHIUSURA a canale giu': sul REST di oggi (D5, ripiego dichiarato)",
                    _conta_rest(b) == rest0 + 1 and len(b.pb.comandi) == cmd0,
                    (out_c, b.rest[rest0:]))
        stato["r1_chiusa"] = True
    b.pb.rialza()
    b.attendi(lambda: b.client.disponibile(), 8.0)
    e.controlla("il client si ricollega da solo", b.client.disponibile(),
                b.client.stato())


def _r5(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    sel, prezzo, _d = b.quota("lay")
    tid = A.riserva(side="lay", price=prezzo, size=2.0)
    ref = "%s%d" % (pref, tid)
    acc0 = b.pb.motore.conti["accettati"]
    ord0 = len(b.ordini_del_motore())
    A.invia(tid, selection_id=sel, side="lay", price=prezzo, size=2.0)
    riga_prima = A.riga(tid)
    A.db.update_trade(tid, meta=dict(riga_prima.get("meta") or {}))
    out2 = A.invia(tid, selection_id=sel, side="lay", price=prezzo, size=2.0)
    ack = _ack_di(b, ref)
    e.controlla("secondo invio: ack 'ref_gia_visto', nessuna seconda esecuzione",
                ack.get("motivo") == "ref_gia_visto"
                and b.pb.motore.conti["accettati"] - acc0 == 1, ack)
    e.controlla("il bot non lo tratta come rifiuto (pending, attende l'esito del primo)",
                getattr(out2, "status", None) == "pending", out2)
    _aspetta_terminale(b, ref)
    e.controlla("UN solo ordine su flumine", len(b.ordini_del_motore()) - ord0 == 1,
                len(b.ordini_del_motore()) - ord0)
    A.risolvi(tid)
    stato["r5_tid"] = tid


def _r6(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    sel, prezzo, _d = b.quota("lay")
    tid = A.riserva(side="lay", price=prezzo, size=2.0)
    ref = "%s%d" % (pref, tid)
    ord0 = len(b.ordini_del_motore())
    b.pb.ritardo_ms = 5000                      # il comando arriva 5 s dopo
    try:
        out = A.invia(tid, selection_id=sel, side="lay", price=prezzo, size=2.0)
    finally:
        b.pb.ritardo_ms = 0
    ack = _ack_di(b, ref)
    e.controlla("rifiutato 'comando_scaduto'",
                ack.get("accettato") is False
                and str(ack.get("motivo") or "").startswith("comando_scaduto"), ack)
    e.controlla("esito certo negativo per il bot", getattr(out, "status", None) == "error",
                out)
    b.pompa(1.0)
    e.controlla("nessun ordine su flumine", len(b.ordini_del_motore()) == ord0, "")


def _r7(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    prima = os.environ.get("LIVE_KILL_SWITCH")
    os.environ["LIVE_KILL_SWITCH"] = "true"
    try:
        sel, prezzo, _d = b.quota("lay")
        tid = A.riserva(side="lay", price=prezzo, size=2.0)
        ref = "%s%d" % (pref, tid)
        ord0 = len(b.ordini_del_motore())
        out = A.invia(tid, selection_id=sel, side="lay", price=prezzo, size=2.0)
        ack = _ack_di(b, ref)
        e.controlla("APERTURA a kill-switch acceso: rifiutata 'kill_switch'",
                    ack.get("accettato") is False
                    and str(ack.get("motivo") or "").startswith("kill_switch"), ack)
        e.controlla("esito certo negativo per il bot", getattr(out, "status", None) == "error",
                    out)
        e.controlla("nessun ordine su flumine", len(b.ordini_del_motore()) == ord0, "")
        # CHIUSURA verificata: la posizione aperta in R5 (lay abbinata)
        r5 = A.riga(int(stato.get("r5_tid") or 0)) if stato.get("r5_tid") else {}
        matched = float(r5.get("size") or 0.0) if r5.get("status") == "open" else 0.0
        if matched <= 0:
            e.controlli.append(("chiusura a kill-switch: N/A (nessuna posizione "
                                "abbinata da chiudere)", True, ""))
            return
        _s, prezzo_b, _db = b.quota("back")
        tid_c = A.riserva(side="back", price=prezzo_b, size=matched,
                          closes=int(stato["r5_tid"]))
        ref_c = "%s%d" % (pref, tid_c)
        A.invia(tid_c, selection_id=int(r5["selection_id"]), side="back", price=prezzo_b,
                size=matched, closes=int(stato["r5_tid"]))
        ack_c = _ack_di(b, ref_c)
        e.controlla("CHIUSURA (riduzione verificata sul blotter) accettata",
                    ack_c.get("accettato") is True, ack_c)
        fase = _aspetta_terminale(b, ref_c)
        e.controlla("la chiusura arriva a un esito", fase is not None, fase)
    finally:
        if prima is None:
            os.environ.pop("LIVE_KILL_SWITCH", None)
        else:
            os.environ["LIVE_KILL_SWITCH"] = prima


def _r8(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    if A.nome == "omega":
        e.na = ("Omega: stake fisso 1,00 EUR di LAY, sopra il minimo .it 0,50; "
                "omega_service passa sempre sotto_minimo=False")
        return
    sel, prezzo_b, _d = b.quota("back")
    size = 1.50                                 # BACK sotto il minimo .it (2,00)
    tid = A.riserva(side="back", price=prezzo_b, size=size)
    ref = "%s%d" % (pref, tid)
    A.invia(tid, selection_id=sel, side="back", price=prezzo_b, size=size)
    ack = _ack_di(b, ref)
    e.controlla("apertura sotto il minimo ACCETTATA dal motore (place-and-trim)",
                ack.get("accettato") is True, ack)
    # la macchina avanza di un passo per book, e ogni passo aspetta che flumine
    # esegua il pacchetto (book successivo DI QUEL mercato): si fa scorrere il
    # tempo di mercato finche' la sequenza non e' chiusa (al massimo 90 s)
    for _ in range(90):
        b.pompa(1.0)
        if not b.pb.motore._submin:
            break
    fasi = _fasi(b, ref)
    e.controlla("fasi della macchina: parcheggiato -> ridotto -> alla quota",
                fasi[:4] == ["inviato", "parcheggiato", "ridotto", "accettato_betfair"],
                fasi)
    e.controlla("sequenza chiusa (nessun place-and-trim appeso)",
                not b.pb.motore._submin, list(b.pb.motore._submin))
    finali = [ev for ev in b.pb.esiti(ref) if ev.get("fase") not in
              ("inviato", "parcheggiato", "ridotto")]
    ultimo = finali[-1] if finali else {}
    e.controlla("ordine a mercato: 1,50 alla quota chiesta (nessun 2,00 a quota vera)",
                abs(float(ultimo.get("size") or 0) - size) < 0.01
                and abs(float(ultimo.get("price") or 0) - prezzo_b) < 1e-6,
                {k: ultimo.get(k) for k in ("fase", "price", "size", "size_matched",
                                            "submin_step")})


def _r9(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    c = b.client
    e.controlla("richieste da_seq <= riconnessioni (nessuna tempesta)",
                c.richieste_da_seq <= max(1, c.connessioni - 1),
                {"da_seq": c.richieste_da_seq, "connessioni": c.connessioni,
                 "buchi": c.memoria.buchi})
    e.controlla("seq contiguo (nessun buco aperto)", not c.memoria._sopra,
                sorted(c.memoria._sopra)[:5])
    stato["client"] = c.stato()


def _monta_auto(b: BancoRapido, *, tetto: Optional[int] = None,
                mercati_iniziali: Any = ()) -> Tuple[Any, Any]:
    """L'``AutoFollow`` di PRODUZIONE sul motore del banco (sottoscrittore del
    banco al posto della connessione Betfair)."""
    from .. import auto_follow as AF
    from .porta_banco import SottoscrittoreBanco

    sott = SottoscrittoreBanco()
    auto = AF.AutoFollow(piano=AF.PianoFollow(tetto if tetto is not None
                                              else AF.tetto_mercati()),
                         sottoscrittore=sott, min_intervallo_s=0.0)
    b.pb.monta_auto_follow(auto, mercati_iniziali)
    return auto, sott


def _altri_mercati(b: BancoRapido, n: int) -> List[Tuple[str, int]]:
    """``n`` mercati VERI della registrazione, APERTI, diversi dal MATCH_ODDS e
    senza ordini, con una selezione vera: (market_id, selection_id)."""
    out: List[Tuple[str, int]] = []
    for mid, m in sorted(b.strat.mercati.items()):
        if mid == b.market_id:
            continue
        mb = getattr(m, "market_book", None)
        if mb is None or mb.status != "OPEN" or not getattr(mb, "runners", None):
            continue
        try:
            if len(list(iter(m.blotter))) > 0:
                continue
        except Exception:  # noqa: BLE001
            continue
        out.append((str(mid), int(mb.runners[0].selection_id)))
        if len(out) >= n:
            break
    return out


def _invia_su(b: BancoRapido, A: Any, tid: int, market_id: str, sel: int,
              prezzo: float) -> Any:
    vero = b.market_id
    b.market_id = market_id
    try:
        return A.invia(tid, selection_id=sel, side="lay", price=prezzo, size=2.0)
    finally:
        b.market_id = vero


def _r10(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """25/09 AUTO-FOLLOW. Il runner NON segue la partita (nessun "Segui live",
    sottoscrizione vuota): il comando del bot sul MATCH_ODDS vero e' accettato
    ``in_aggancio``, il mercato entra nel piano a priorita' comando, la
    sottoscrizione a caldo parte e l'ordine va a flumine al primo book nuovo.
    Prima (24/09): rifiutato "market ... non sottoscritto nel runner"."""
    from .. import auto_follow as AF

    auto, sott = _monta_auto(b)
    try:
        sel, prezzo, _d = b.quota("lay")
        tid = A.riserva(side="lay", price=prezzo, size=2.0)
        ref = "%s%d" % (pref, tid)
        rest0, ord0 = _conta_rest(b), len(b.ordini_del_motore())
        e.controlla("prima del comando il runner NON segue il mercato",
                    not auto.servibile(b.market_id), sorted(auto.piano.mercati()))
        out = A.invia(tid, selection_id=sel, side="lay", price=prezzo, size=2.0)
        ack = _ack_di(b, ref)
        e.controlla("esito dell'invio 'pending' (il bot attende l'esito)",
                    getattr(out, "status", None) == "pending", out)
        e.controlla("ack ACCETTATO con motivo 'in_aggancio' (dichiarato)",
                    ack.get("accettato") is True
                    and str(ack.get("motivo") or "").startswith("in_aggancio"), ack)
        voce = auto.piano.voce(auto.piano.chiave_di(b.market_id) or "")
        e.controlla("mercato nel piano a priorita' COMANDO",
                    voce is not None and voce.priorita == AF.PRI_COMANDO,
                    voce and (voce.chiave, voce.priorita))
        fase = _aspetta_terminale(b, ref)
        e.controlla("sottoscrizione a caldo inviata col mercato del comando",
                    bool(sott.chiamate) and b.market_id in sott.chiamate[-1],
                    sott.chiamate[-1:] if sott.chiamate else None)
        e.controlla("evento terminale arrivato al client", fase is not None, fase)
        e.controlla("UN solo ordine su flumine per il comando",
                    len(b.ordini_del_motore()) - ord0 == 1,
                    len(b.ordini_del_motore()) - ord0)
        e.controlla("nessuna chiamata REST", _conta_rest(b) == rest0, b.rest[rest0:])
        tutte = " ".join(str(x.get("motivo") or x.get("error") or "")
                         for x in (b.pb.esiti(ref) or []))
        e.controlla("mai 'non sottoscritto' negli eventi", "non sottoscritto" not in tutte,
                    tutte[:200])
        riga = A.risolvi(tid)
        ev = b.client.esiti(ref) or {}
        if fase == "abbinato":
            e.controlla("riga 'open' con l'abbinato del runner",
                        riga.get("status") == "open", riga.get("status"))
        else:
            e.controlla("FOK non abbinato: riga 'error' (esito vero di Betfair, non "
                        "un rifiuto del runner)",
                        riga.get("status") == "error" and fase != "rifiutato",
                        (riga.get("status"), fase))
        e.controlla("la voce prende l'event_id vero dal primo book",
                    auto.piano.chiave_di(b.market_id) == str(b.event_id),
                    auto.piano.chiave_di(b.market_id))
        stato["r10_fase"] = fase
        stato["r10_size_matched"] = ev.get("size_matched")
        stato["r10_auto"] = auto.stato()
    finally:
        b.pb.smonta_auto_follow()


def _r10b(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """Tetto pieno: una partita seguita da sola per il feed (priorita'
    candidata, SENZA ordini) occupa il tetto; il comando di un bot su un
    mercato nuovo la espelle ed e' eseguito."""
    from .. import auto_follow as AF

    altri = _altri_mercati(b, 2)
    if len(altri) < 2:
        e.na = "servono 2 mercati aperti senza ordini oltre al MATCH_ODDS"
        return
    (m_cand, _s1), (m_cmd, sel_cmd) = altri
    auto, sott = _monta_auto(b, tetto=1)
    try:
        ok = auto.piano.richiedi("feed-candidata", {m_cand}, priorita=AF.PRI_CANDIDATA,
                                 protetti=set(), puo_espellere=False, ora=time.monotonic())
        auto.giro()
        e.controlla("tetto pieno: 1 mercato candidato seguito su tetto 1",
                    ok.ok and auto.piano.mercati() == {m_cand}, sorted(auto.piano.mercati()))
        tid = A.riserva(side="lay", price=1.01, size=2.0)
        ref = "%s%d" % (pref, tid)
        ord0 = len(b.ordini_del_motore())
        _invia_su(b, A, tid, m_cmd, sel_cmd, 1.01)
        ack = _ack_di(b, ref)
        e.controlla("ack accettato in_aggancio", ack.get("accettato") is True, ack)
        e.controlla("la candidata SENZA ordini e' espulsa, entra il mercato del comando",
                    auto.piano.voce("feed-candidata") is None
                    and auto.piano.mercati() == {m_cmd}
                    and auto.conti["espulsi"] == 1, sorted(auto.piano.mercati()))
        fase = _aspetta_terminale(b, ref)
        # (lo specchio del banco puo' adottare ADESSO un ordine di uno scenario
        # precedente, es. l'ultimo passo del place-and-trim di R8: si contano
        # solo quelli sul mercato del comando)
        sul_cmd = [o for o in b.ordini_del_motore()[ord0:]
                   if str(getattr(o, "market_id", "")) == m_cmd]
        e.controlla("comando eseguito dopo l'espulsione: ordine sul mercato del "
                    "comando ed evento terminale",
                    len(sul_cmd) >= 1 and fase is not None, (len(sul_cmd), fase))
        e.controlla("mai piu' mercati del tetto nella sottoscrizione",
                    all(len(c) <= 1 for c in sott.chiamate), sott.chiamate)
        A.risolvi(tid)
    finally:
        b.pb.smonta_auto_follow()


def _r10c(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """Tetto pieno di mercati NON espellibili: il MATCH_ODDS con gli ordini
    degli scenari precedenti (posizioni/ordini nel blotter), poi un follow
    MANUALE. Niente viene espulso: rifiuto dichiarato, nessun ordine."""
    from .. import auto_follow as AF

    altri = _altri_mercati(b, 2)
    if len(altri) < 2:
        e.na = "servono 2 mercati aperti senza ordini oltre al MATCH_ODDS"
        return
    (m_man, _s0), (m_cmd, sel_cmd) = altri
    try:
        n_ord = len(list(iter(b.market.blotter)))
    except Exception:  # noqa: BLE001
        n_ord = 0
    if n_ord == 0:
        e.na = "il MATCH_ODDS non ha ordini dagli scenari precedenti"
        return
    for caso in ("posizioni", "manuale"):
        auto, _sott = _monta_auto(b, tetto=1)
        try:
            if caso == "posizioni":
                auto.piano.richiedi("evento-con-ordini", {b.market_id},
                                    priorita=AF.PRI_CANDIDATA, protetti=set(),
                                    puo_espellere=False, ora=time.monotonic())
            else:
                auto.imposta_manuali({"evento-manuale": {m_man}})
            prima = set(auto.piano.mercati())
            tid = A.riserva(side="lay", price=1.01, size=2.0)
            ref = "%s%d" % (pref, tid)
            ord0, rest0 = len(b.ordini_del_motore()), _conta_rest(b)
            out = _invia_su(b, A, tid, m_cmd, sel_cmd, 1.01)
            b.pompa(0.5)
            ack = _ack_di(b, ref)
            e.controlla("[%s] rifiuto dichiarato 'tetto_mercati_pieno'" % caso,
                        ack.get("accettato") is False
                        and str(ack.get("motivo") or "").startswith("tetto_mercati_pieno"),
                        ack)
            e.controlla("[%s] niente espulso: il piano e' quello di prima" % caso,
                        auto.piano.mercati() == prima and auto.conti["espulsi"] == 0,
                        sorted(auto.piano.mercati()))
            e.controlla("[%s] nessun ordine, nessun REST" % caso,
                        len(b.ordini_del_motore()) == ord0 and _conta_rest(b) == rest0,
                        (len(b.ordini_del_motore()) - ord0, b.rest[rest0:]))
            e.controlla("[%s] esito certo negativo per il bot (come R6)" % caso,
                        getattr(out, "status", None) == "error"
                        and "tetto_mercati_pieno" in str(getattr(out, "fill_note", "")),
                        out)
        finally:
            b.pb.smonta_auto_follow()


def _r10d(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """Il mercato chiesto non arriva mai (inesistente): il comando accettato
    ``in_aggancio`` NON scade in silenzio. Dopo ``aggancio_max_ms`` evento
    terminale 'rifiutato' col motivo ``in_aggancio``, riga error, nessun
    ordine, nessun REST."""
    auto, _sott = _monta_auto(b)
    prima_max = b.pb.motore.aggancio_max_ms
    b.pb.motore.aggancio_max_ms = 300
    try:
        sel, prezzo, _d = b.quota("lay")
        tid = A.riserva(side="lay", price=prezzo, size=2.0)
        ref = "%s%d" % (pref, tid)
        ord0, rest0 = len(b.ordini_del_motore()), _conta_rest(b)
        _invia_su(b, A, tid, "1.999999999", sel, prezzo)
        ack = _ack_di(b, ref)
        e.controlla("ack accettato in_aggancio", ack.get("accettato") is True
                    and str(ack.get("motivo") or "").startswith("in_aggancio"), ack)
        fine = time.monotonic() + 5.0
        ev: Dict[str, Any] = {}
        while time.monotonic() < fine:
            if b.un_book() is None:
                b.pb.aggiorna()
            ev = b.client.esiti(ref) or {}
            if ev.get("fase") == "rifiutato":
                break
            time.sleep(0.005)
        mot = b.pb.motore
        esiti_diario = [r for r in mot.diario.leggi(mot._giorni_diario())
                        if r.get("tipo") == "esito" and r.get("ref") == ref]
        motivo = str((esiti_diario[-1].get("errore") if esiti_diario else "") or "")
        e.controlla("evento terminale 'rifiutato' (mai in silenzio)",
                    ev.get("fase") == "rifiutato", ev.get("fase"))
        e.controlla("esito nel diario del runner col motivo 'in_aggancio'",
                    motivo.startswith("in_aggancio"), motivo[:160])
        e.controlla("nessun ordine, nessun REST",
                    len(b.ordini_del_motore()) == ord0 and _conta_rest(b) == rest0,
                    (len(b.ordini_del_motore()) - ord0, b.rest[rest0:]))
        e.controlla("nessun comando rimasto parcheggiato", not b.pb.motore._in_aggancio,
                    list(b.pb.motore._in_aggancio))
        riga = A.risolvi(tid)
        e.controlla("riga 'error'", riga.get("status") == "error", riga.get("status"))
        stato["r10d_motivo"] = motivo[:200]
    finally:
        b.pb.motore.aggancio_max_ms = prima_max
        b.pb.smonta_auto_follow()


def _r2b(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """Il PRIMO book SOSPESO del MATCH_ODDS (di solito il fischio d'inizio)."""
    trovato = False
    for _ in range(MAX_BOOK_SOSPESO):
        mb = b.un_book()
        if mb is None:
            break
        if str(mb.market_id) == b.market_id and mb.status == "SUSPENDED":
            trovato = True
            break
    if not trovato:
        e.na = "nessun book sospeso del MATCH_ODDS nella registrazione"
        return
    sel = int(b.book.runners[0].selection_id)
    tid = A.riserva(side="lay", price=3.0, size=2.0)
    ref = "%s%d" % (pref, tid)
    A.invia(tid, selection_id=sel, side="lay", price=3.0, size=2.0)
    fase = _aspetta_terminale(b, ref, secondi=20.0)
    ev = b.client.esiti(ref) or {}
    e.controlla("mercato SOSPESO: nessun abbinato", float(ev.get("size_matched") or 0) == 0,
                (fase, ev.get("size_matched"), ev.get("status")))
    e.controlla("esito terminale negativo", fase in ("rifiutato", "annullato", "scaduto",
                                                     "errore"), fase)
    riga = A.risolvi(tid)
    e.controlla("riga 'error'", riga.get("status") == "error", riga.get("status"))


# ---------------------------------------------------------------------------
# l'ingresso da certifica
# ---------------------------------------------------------------------------
def main_rapidi(scheda: Any, eventi: List[str], data_dir: str, *, trasporto: Optional[str],
                diario: Optional[str], tracce: Optional[str], lavora: Callable[..., Any],
                freni: Callable[[], Any]) -> int:
    bot = scheda.nome
    if TRA.attore_di(bot) is None:
        print("IL BOT '%s' NON HA LA PORTA A COMANDI: %s" % (
            bot, TRA.SENZA_CANALE.get(bot, "non registrato per il canale")))
        return 2
    if not eventi:
        print("nessuna registrazione in %s" % data_dir)
        return 2
    ev = str(eventi[0])
    righe: List[str] = []

    def scrivi(s: str) -> None:
        print(s)
        righe.append(s)

    t0 = time.monotonic()
    scrivi("PROFILO RAPIDO del trasporto - bot %s (attore %s) - registrazione %s" % (
        bot, TRA.attore_di(bot), ev))
    with freni():
        esiti = esegui_scenari(bot, ev, data_dir)
    t_scenari = time.monotonic() - t0
    ko = 0
    for e in esiti:
        scrivi(e.riga())
        for desc, ok, det in e.controlli:
            scrivi("      %s %s%s" % ("ok" if ok else "KO", desc, ("  [%s]" % det) if (det and not ok)
                                  else ""))
        if e.errore:
            scrivi("      ERRORE: %s" % e.errore)
        if not e.ok and not e.na:
            ko += 1
    scrivi("scenari di trasporto: %d, KO %d, durata %.1f s" % (len(esiti), ko, t_scenari))
    parita_ko = 0
    rapporto = None
    if trasporto == "entrambi":
        sc = SCENARIO_ORDINI.get(bot, "base")
        scrivi("PARITA' coda/canale sullo scenario d'ordine '%s' (partita intera, due "
           "replay in sequenza)..." % sc)
        tr_out: Dict[str, Any] = {}
        referti = {}
        for tr in ("coda", "canale"):
            r, _mem = lavora((bot, ev, data_dir, sc, 0, 0, tr))
            referti[tr] = r
            tr_out[tr] = getattr(r, "traccia_trasporto", None)
            scrivi("  %s <%s>: pulita=%s decisioni=%s azioni=%s violazioni=%d" % (
                ev, tr, getattr(r, "pulita", None), getattr(r, "decisioni", None),
                getattr(r, "azioni", None), len(getattr(r, "violazioni", []) or [])))
            for v in (getattr(r, "violazioni", []) or [])[:4]:
                scrivi("      %s: %s" % (v.codice, str(v.dettaglio)[:200]))
        if tr_out.get("coda") is not None and tr_out.get("canale") is not None:
            rapporto = TRA.confronta(tr_out["coda"], tr_out["canale"])
            for riga in TRA.descrivi(rapporto):
                scrivi("  " + riga)
            if not rapporto["parita"]:
                parita_ko = 1
        else:
            scrivi("  traccia mancante: parita' NON verificabile")
            parita_ko = 1
        for tr, r in referti.items():
            if [v for v in (getattr(r, "violazioni", []) or [])
                    if not v.codice.endswith("-DICHIARATA")
                    and not v.codice.endswith("-APPROVAZIONE")]:
                parita_ko = 1
        if tracce:
            with io.open(tracce, "w", encoding="utf-8") as f:
                json.dump({"scenario": sc, "evento": ev, "coda": tr_out.get("coda"),
                           "canale": tr_out.get("canale"), "parita": rapporto},
                          f, indent=1, default=str)
    durata = time.monotonic() - t0
    scrivi("DURATA DEL PROFILO RAPIDO (%s): %.1f s" % (bot, durata))
    esito = 0 if (ko == 0 and parita_ko == 0) else 1
    scrivi("ESITO: %s" % ("OK" if esito == 0 else "KO"))
    if diario:
        with io.open(diario, "a", encoding="utf-8") as f:
            for s in righe:
                f.write(s + chr(10))
    return esito
