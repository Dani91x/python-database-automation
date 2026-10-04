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
  R3 parziale         - Safe e Omega sono FOK in live E in paper (Omega paper
                        dal 28/09, cantiere C: prima lavorava il book fino al
                        TTL): la parte non coperta si uccide tutta (0 abbinato),
                        riga 'error', nessun residuo vivo, in entrambe le
                        modalita';
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
  R11 runner in prova - 04/10: bot in LIVE, runner che serve solo la PROVA
                        (``mode_non_servibile``): nessun ordine, e il servizio
                        Safe VERO non brucia i tentativi, dichiara
                        ``motivo_blocco``, UN CRITICAL per episodio;
  R11b Ordini reali   - 04/10: stesso controllo col modo EFFETTIVO su PAPER
                        (funzione vera ``_blocco_apertura_modo``), solo calcio.

25/09 (F8) - SAFE TENNIS (``certifica safe_tennis ... --scenari rapidi``): la
stessa catena sul runner TENNIS. Motore VERO con l'esecutore tennis
(``tennis_live.esecutore_tennis`` -> ``tennis_live_order_worker._dispatch``),
client VERO ``PortaCanale`` con l'attore ``safe_tennis`` e ref
``safe_tennis-t<id>``, risoluzione VERA della riga Safe (strategia ``tennis``).
Stessi scenari, con queste differenze DICHIARATE:
  R8  sotto il minimo - il runner tennis NON ha il place-and-trim: dal 28/09
                        (decisione dell'utente) l'apertura sotto il minimo
                        parte AL minimo (BACK 2,00) come place normale e
                        l'evento lo dichiara (``portata_al_minimo``); prima
                        era rifiutata ``submin_non_percorribile``;
  R10 famiglia        - l'aggancio e' ``AgganciaTennis`` di produzione
                        (priorita' COMANDO del piano ``iscrizione_a_caldo``);
                        al posto della risottoscrizione sulla connessione
                        Betfair il banco usa ``AllineaBancoTennis`` (latenza di
                        un book), come ``SottoscrittoreBanco`` per il calcio.
                        R10b/R10c usano partite «occupanti» con mercati fuori
                        registrazione (una registrazione tennis ha un solo
                        mercato): il piano le vede come partite vere.
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
                   "safe_punta": "ordini-manuali", "omega": "apertura",
                   # 25/09 (F8): su una registrazione tennis la strategia non ha
                   # mai le sue condizioni: l'ingresso dichiarato + le uscite
                   # sono gli unici ordini (``replay_tennis``)
                   "safe_tennis": "posizione-iniettata"}

#: prefisso del ref di riga per attore (il motore pretende ``f"{attore}-"``)
PREFISSI = {"omega": "omega-t", "safe": "safe-t", "safe_tennis": "safe_tennis-t"}

#: 25/09 (F8): nel pre-partita del tennis i book del MATCH_ODDS arrivano anche a
#: decine di secondi l'uno dall'altro: l'ordine agganciato parte al primo book
#: NUOVO e l'esito arriva col book dopo. La finestra di attesa (tempo di MERCATO)
#: degli scenari di aggancio tennis e' quindi piu' larga di quella del calcio.
SECONDI_TENNIS = 600.0

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
    @property
    def sport(self) -> str:
        return TRA.SPORT_ATTORE.get(self.attore, "calcio")

    def monta_porta(self) -> None:
        self.smonta_porta()
        self.pb = self._PortaBanco(self.quadro, self.strat, attore=self.attore,
                                   modo_processo="LIVE", sport=self.sport)
        self.pb.orologio_mercato = lambda: TRA._ora_mercato(self.motore)
        # 30/09 (M1): come ``trasporto._monta_canale``: l'annullo sul canale
        # aspetta il tempo di Betfair sul motore di questo banco
        self.pb.attendi_esecuzione = self.motore.attendi_esecuzione
        if self.attore == "omega":
            from ...omega import porta_ordini as OPO

            self.client = OPO.PortaCanaleOmega(porta_ws=0, attore="omega", sport="calcio",
                                               connetti=self.pb.connetti,
                                               token_fn=lambda: self._TOKEN)
            self._rip = ("omega", OPO._PORTA)
            OPO._PORTA = self.client
        else:
            from ...safe_strategy import porta_ordini as SPO

            self.client = SPO.PortaCanale(porta_ws=0, attore=self.attore, sport=self.sport,
                                          connetti=self.pb.connetti,
                                          token_fn=lambda: self._TOKEN)
            self._rip = ("safe:" + self.sport, SPO._PORTE.get(self.sport))
            SPO._PORTE[self.sport] = self.client
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

                sport = chi.split(":", 1)[1] if ":" in chi else "calcio"
                if prima is None:
                    SPO._PORTE.pop(sport, None)
                else:
                    SPO._PORTE[sport] = prima
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
        # 25/09 (F8): Safe tennis = strategia 'tennis' (``exits.is_tennis``:
        # porta ``tennis``, ref ``safe_tennis-t<id>``); calcio invariato
        self.sport = banco.sport
        self.db = DbSafeMemoria({"id": 1, "status": "running", "mode": "live",
                                 "params": {}, "stats": {}},
                                orologio=lambda: banco.ora().timestamp())

    def riserva(self, *, side: str, price: float, size: float, mode: str = "live",
                closes: Optional[int] = None) -> int:
        riga = {"event_id": self.b.event_id, "market_id": self.b.market_id,
                "selection_id": None, "side": side, "price": price, "size": size,
                "status": "pending", "mode": mode,
                "strategy": "tennis" if self.sport == "tennis" else "base",
                "meta": {"phase": "reserved"}}
        if closes:
            riga["closes_trade_id"] = closes
            riga["meta"]["closes_trade_id"] = closes
        return int(self.db.insert_trade(riga))

    def invia(self, tid: int, *, selection_id: int, side: str, price: float, size: float,
              mode: str = "live", closes: Optional[int] = None, porta: Any = None) -> Any:
        from ...safe_strategy import execution as X
        from ...safe_strategy import porta_ordini as SPO

        self.db.update_trade(tid, selection_id=selection_id)
        meta: Dict[str, Any] = {"closes_trade_id": closes} if closes else {}
        return X.place(db=self.db, market=self.b.mercato_rest, mode=mode,
                       event_id=self.b.event_id, market_id=self.b.market_id,
                       selection_id=selection_id, side=side, price=price, size=size,
                       client_ref=SPO.ref_ordine(tid, sport=self.sport), trade_id=tid,
                       meta=meta,
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
        pref = PREFISSI[attore]
        stato: Dict[str, Any] = {}
        tennis = b.sport == "tennis"
        for nome, fn in (("R1 accettato", _r1), ("R2 freno", _r2),
                         ("R3 parziale", _r3), ("R4 canale giu'", _r4),
                         ("R5 duplicato", _r5), ("R6 comando vecchio", _r6),
                         ("R7 kill-switch", _r7),
                         ("R8 sotto il minimo", _r8_tennis if tennis else _r8),
                         ("R9 sequenza", _r9),
                         ("R10 mercato non seguito", _r10_tennis if tennis else _r10),
                         ("R10b tetto pieno", _r10b_tennis if tennis else _r10b),
                         ("R10c mai espulsi", _r10c_tennis if tennis else _r10c),
                         ("R10d aggancio mai in silenzio",
                          _r10d_tennis if tennis else _r10d),
                         # 04/10 (cantiere tetto tennis): PRIMA di R2b, a mercato
                         # ancora aperto (dopo R2b il MATCH_ODDS tennis non riapre)
                         ("R11d Ordini reali LIVE (tennis)", _r11d),
                         ("R2b mercato sospeso", _r2b),
                         # 04/10: in CODA, gli scenari di prima restano identici
                         ("R11 runner solo prova", _r11),
                         ("R11b Ordini reali in prova", _r11b),
                         ("R11c runner in prova, mercato da agganciare", _r11c)):
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
        e.controlli.append(("PAPER: N/A per Safe (stesso FOK del live, gia' provato)", True, ""))
        return
    # Omega PAPER (cantiere C, 28/09): lo STESSO ordine del live, FOK compreso.
    # Prima qui si pretendeva il parziale (il difetto R8): ora il paper deve
    # uscire identico al live dello stesso scenario.
    tid2 = A.riserva(side="lay", price=prezzo, size=size, mode="paper")
    ref2 = "%s%d" % (pref, tid2)
    A.invia(tid2, selection_id=sel, side="lay", price=prezzo, size=size, mode="paper")
    fase2 = _aspetta_terminale(b, ref2)
    ev2 = b.client.esiti(ref2) or {}
    e.controlla("PAPER FOK oltre la liquidita': ucciso, 0 abbinato (come il live)",
                fase2 in ("annullato", "scaduto")
                and float(ev2.get("size_matched") or 0) == 0
                and float(ev2.get("size_remaining") or 0) == 0,
                (fase2, ev2.get("size_matched"), ev2.get("size_remaining")))
    riga2 = A.risolvi(tid2)
    e.controlla("PAPER riga 'error' (come il live)", riga2.get("status") == "error",
                riga2.get("status"))


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
        e.na = ("Omega: stake fisso 1,00 EUR di LAY, pari al minimo .it 1,00; "
                "omega_service passa sempre sotto_minimo=False")
        return
    sel, prezzo_b, _d = b.quota("back")
    # minimi .it definitivi 01/10: punta 1,00 / banca 1,00 / trim >= 0,50 (sul Match Odds a 3 esiti
    # non c'e' equivalente: 0,70 va al place-and-trim, parcheggio 1,00)
    size = 0.70                                 # BACK sotto il minimo .it (1,00)
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
    e.controlla("ordine a mercato: 0,70 alla quota chiesta (nessun 1,00 a quota vera)",
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
# 25/09 (F8) - gli scenari del runner TENNIS che differiscono dal calcio
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 04/10/2026 - SOLDI VERI COERENTI: la catena che NON serve il live
# ---------------------------------------------------------------------------
# Incidente del 04/10: Safe tennis in «soldi veri», runner tennis in PAPER: 15
# aperture rifiutate (``mode_non_servibile``), tentativi bruciati, motivo_blocco
# null. Qui il bot e' in LIVE e il motore VERO del runner serve solo la prova
# (R11) oppure ha «Ordini reali» su PAPER (R11b, solo calcio: il runner tennis
# non ha un modo effettivo dalla UI). Si controlla la CONDOTTA: rifiuto certo,
# nessun ordine, e per Safe il servizio VERO (``bot_service._place_fail``) che
# non brucia i tentativi, dichiara il blocco e dice il CRITICAL una volta.
N_APERTURE_CATENA = 3


def _condotta_catena(b: BancoRapido, A: Any, pref: str, e: _Esito, motivo_atteso: str,
                     stato: Dict[str, Any]) -> None:
    from ...safe_strategy import bot_service as BS
    from ...safe_strategy import execution as X

    ord0, rest0 = len(b.ordini_del_motore()), _conta_rest(b)
    critici0 = len([p for k, p, _e in A.db.attivita
                    if k == "canale_rifiutato" and p.get("critical")])
    # il rifiuto arriva PRIMA del mercato: selezione di R1, quota qualunque valida
    # (dopo R2b il mercato della registrazione puo' essere sospeso o finito)
    q = b.quota("lay")
    sel = int(stato.get("r1_sel") or (q[0] if q else 0))
    prezzo = float(q[1]) if q else 2.0
    tid = 0
    for i in range(N_APERTURE_CATENA):
        tid = A.riserva(side="lay", price=prezzo, size=2.0)
        ref = "%s%d" % (pref, tid)
        out = A.invia(tid, selection_id=sel, side="lay", price=prezzo, size=2.0)
        ack = _ack_di(b, ref)
        if i == 0:
            e.controlla("APERTURA live rifiutata dal motore col motivo '%s'" % motivo_atteso,
                        ack.get("accettato") is False
                        and str(ack.get("motivo") or "").startswith(motivo_atteso), ack)
            e.controlla("esito certo negativo per il bot", getattr(out, "status", None)
                        == "error", out)
        if A.nome == "safe" and getattr(out, "status", None) == "error":
            riga = A.riga(tid)
            riga.setdefault("signal_key", "rapido:catena")
            BS._place_fail(A.db, tid, riga, out.fill_note, b.ora(), {"place_max_attempts": 3})
    e.controlla("nessun ordine su flumine, nessun REST",
                len(b.ordini_del_motore()) == ord0 and _conta_rest(b) == rest0, "")
    if A.nome != "safe":
        e.controlli.append(("condotta del servizio: N/A per Omega (resta il trasporto; "
                            "la regola di catena di Omega e' un reperto aperto)", True, ""))
        return
    critici = len([p for k, p, _e in A.db.attivita
                   if k == "canale_rifiutato" and p.get("critical")]) - critici0
    e.controlla("UN solo CRITICAL per l'episodio (non uno per tentativo)", critici == 1,
                critici)
    kinds = [k for k, _p, _e in A.db.attivita]
    e.controlla("nessun 'place_exhausted' / 'place_retry' (tentativi non bruciati)",
                "place_exhausted" not in kinds and "place_retry" not in kinds, kinds[-6:])
    st = BS._PLACE_ATTEMPTS.get(BS._place_key(b.event_id, "rapido:catena")) or {}
    e.controlla("budget dei tentativi intatto", int(st.get("attempts") or 0) == 0
                and not st.get("final"), st)
    motivo = BS._motivo_catena()
    e.controlla("motivo_blocco dichiarato per il trader", bool(motivo)
                and "aperture in soldi veri FERME" in str(motivo), motivo)
    e.controlla("altre aperture live ferme fino alla sonda (nessuna raffica)",
                BS._catena_bloccata(b.sport, "live", b.ora().timestamp() + 1) is not None, "")
    e.controlla("la prova non e' toccata (bot indipendenti dalla modalita')",
                BS._catena_bloccata(b.sport, "paper", b.ora().timestamp() + 1) is None, "")
    BS._CATENA.clear()
    BS._PLACE_ATTEMPTS.pop(BS._place_key(b.event_id, "rapido:catena"), None)
    X._EPISODI_CATENA.clear()
    if hasattr(A.db, "_episodi_catena"):
        A.db._episodi_catena.clear()


def _r11(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """R11 - il runner serve SOLO la prova (tetto PAPER), il bot e' in LIVE."""
    motore = b.pb.motore
    prima = motore._modo_processo_forzato
    motore._modo_processo_forzato = "PAPER"
    try:
        _condotta_catena(b, A, pref, e, "mode_non_servibile", stato)
    finally:
        motore._modo_processo_forzato = prima


def _r11c(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """R11c - lo scenario REALE dell'incidente: runner in PAPER, bot in LIVE,
    mercato NON ancora seguito. La prima sonda e' accettata ``in_aggancio`` e
    rifiutata DOPO (evento terminale), le successive (mercato ormai seguito)
    subito. Condotta: un solo CRITICAL nell'episodio, ``motivo_blocco`` mai
    sparito, nessun tentativo consumato, nessuna «catena ripristinata»."""
    from ...safe_strategy import bot_service as BS
    from ...safe_strategy import execution as X

    if A.nome != "safe":
        e.na = "condotta di catena del servizio: solo Safe (Omega: reperto A)"
        return
    motore = b.pb.motore
    prima = motore._modo_processo_forzato
    motore._modo_processo_forzato = "PAPER"
    tennis = b.sport == "tennis"
    # Il rifiuto ASINCRONO esiste SOLO a runner senza framework (fermo, senza
    # partite seguite o in ripartenza: ``_controlla`` parcheggia PRIMA del
    # controllo del modo, motore_ordini.py:1047-1070). E' il runner tennis
    # dell'incidente (in attesa, nessuna partita). Con il framework vivo il
    # controllo del modo viene PRIMA di ``_serve_aggancio`` (:983-984): rifiuto
    # sincrono (R11). Qui: framework tolto per la prima sonda, rimesso dopo.
    if tennis:
        from ..tennis_live import iscrizione_a_caldo as IAC
        b.pb.monta_aggancio_tennis(tetto=IAC.tetto_mercati(),
                                   seguiti={str(b.event_id): b.market_id})
    else:
        _monta_auto(b, mercati_iniziali=[b.market_id])
    fw = motore._flumine
    # la porta del banco al posto di ``_porta_kw`` (interruttore del canale acceso
    # in produzione: ``SAFE_TENNIS_ORDINI_VIA_CANALE=1``/``SAFE_ORDINI_VIA_CANALE=1``)
    porta_kw_vera = BS._porta_kw
    BS._porta_kw = lambda riga: {"porta": b.client}
    ripristini: List[str] = []
    gestore = _ContaLog("catena ripristinata", ripristini)
    import logging as _lg
    _lg.getLogger("safe.bot").addHandler(gestore)
    try:
        ord0, rest0 = len(b.ordini_del_motore()), _conta_rest(b)
        critici0 = len([p for k, p, _e in A.db.attivita
                        if k == "canale_rifiutato" and p.get("critical")])
        q = b.quota("lay")
        sel = int(stato.get("r1_sel") or (q[0] if q else 0))
        prezzo = float(q[1]) if q else 2.0
        motivi: List[Any] = []
        kinds0 = len(A.db.attivita)
        for i in range(N_APERTURE_CATENA):
            # le sonde passano dal SERVIZIO VERO (``bot_service._execute``: e' li'
            # che vivono il ripristino e il ``_place_fail``), come in produzione
            tid = A.riserva(side="lay", price=prezzo, size=2.0)
            A.db.update_trade(tid, selection_id=sel, signal_key="rapido:catena")
            ref = "%s%d" % (pref, tid)
            asincrona = i < 2                   # runner senza framework (partite nuove)
            if asincrona:
                motore._flumine = None
            try:
                out = BS._execute(db=A.db, market=b.mercato_rest, trade_id=tid,
                                  row=A.riga(tid), params={"execution_mode": "rest"},
                                  now=b.ora(), best_size=None, ladder=())
            finally:
                motore._flumine = fw            # il runner riparte con il mercato
            ack = _ack_di(b, ref)
            if asincrona:
                e.controlla("sonda %d: ack ACCETTATO 'in_aggancio' (runner senza partite)"
                            % (i + 1), ack.get("accettato") is True
                            and str(ack.get("motivo") or "").startswith("in_aggancio"), ack)
                e.controlla("sonda %d: un 'pending' in_aggancio non e' una prova"
                            % (i + 1), getattr(out, "status", None) == "pending"
                            and getattr(out, "catena_servita", None) is False, out)
                if i > 0:
                    # il blocco e' gia' in corso: il pending NON lo deve togliere
                    motivi.append(BS._motivo_catena())
                fase = _aspetta_terminale(b, ref, secondi=SECONDI_TENNIS)
                e.controlla("sonda %d: rifiuto ASINCRONO per modo (evento 'rifiutato')"
                            % (i + 1), fase == "rifiutato", fase)
                riga_fine = A.risolvi(tid)
                e.controlla("sonda %d: riga 'error' marcata blocco di catena (nessun no-fill)"
                            % (i + 1), riga_fine.get("status") == "error"
                            and ((riga_fine.get("meta") or {}).get("place") or {})
                            .get("blocco_catena") is True, riga_fine.get("meta"))
            else:
                e.controlla("sonda %d: rifiuto sincrono (mercato ormai seguito)" % (i + 1),
                            getattr(out, "status", None) == "error", out)
            motivi.append(BS._motivo_catena())
        e.controlla("motivo_blocco MAI sparito fra una sonda e l'altra",
                    all(m and "aperture in soldi veri FERME" in str(m) for m in motivi), motivi)
        critici = len([p for k, p, _e in A.db.attivita
                       if k == "canale_rifiutato" and p.get("critical")]) - critici0
        e.controlla("UN solo CRITICAL nell'episodio (asincrono + sincroni)", critici == 1,
                    critici)
        kinds = [k for k, _p, _e in A.db.attivita[kinds0:]]
        e.controlla("nessun 'place_retry'/'place_exhausted'/'flumine_no_fill'",
                    not ({"place_retry", "place_exhausted", "flumine_no_fill"} & set(kinds)),
                    kinds[-8:])
        st = BS._PLACE_ATTEMPTS.get(BS._place_key(b.event_id, "rapido:catena")) or {}
        e.controlla("budget dei tentativi intatto", int(st.get("attempts") or 0) == 0
                    and not st.get("final"), st)
        e.controlla("nessuna «catena ripristinata» nel log", not ripristini, ripristini)
        e.controlla("nessun ordine su flumine, nessun REST",
                    len(b.ordini_del_motore()) == ord0 and _conta_rest(b) == rest0, "")
    finally:
        _lg.getLogger("safe.bot").removeHandler(gestore)
        BS._porta_kw = porta_kw_vera
        motore._modo_processo_forzato = prima
        if tennis:
            b.pb.smonta_aggancio_tennis()
        else:
            b.pb.smonta_auto_follow()
        BS._CATENA.clear()
        BS._PLACE_ATTEMPTS.pop(BS._place_key(b.event_id, "rapido:catena"), None)
        X._EPISODI_CATENA.clear()
        if hasattr(A.db, "_episodi_catena"):
            A.db._episodi_catena.clear()


import logging as _logging


class _ContaLog(_logging.Handler):
    """Handler di logging che raccoglie i messaggi che contengono ``testo``."""

    def __init__(self, testo: str, dove: List[str]) -> None:
        super().__init__(level=0)
        self._testo, self._dove = testo, dove

    def emit(self, record: Any) -> None:
        msg = record.getMessage()
        if self._testo in msg:
            self._dove.append(msg)


def _r11b_tennis(b: BancoRapido, A: Any, pref: str, e: _Esito,
                 stato: Dict[str, Any]) -> None:
    """R11b TENNIS (04/10, cantiere tetto tennis) - tetto del runner tennis LIVE,
    «Ordini reali» in PROVA (lo stesso interruttore del calcio, decisione
    dell'utente): nessun ordine reale da NESSUNA strada. Motore (Safe tennis) con
    la funzione VERA ``esecutore_tennis._blocco_apertura_modo``: condotta di
    catena come R11b del calcio, ma il motivo deve essere «Ordini reali» (non
    l'assenza di un client). Ladder (coda e ``/order`` del worker tennis): stessa
    funzione (``tennis_live_order_worker._blocco_apertura_modo``). Terza rete
    dentro flumine (4 bot e ogni strada): ``ControlloModoOrdiniTennis``. La prova
    e le chiusure passano."""
    from .. import modo_ordini as MOD
    from ..live_order_worker import _CONTESTO
    from ..tennis_live import esecutore_tennis as ET
    from ..tennis_live import guardie_tennis as GT
    from ..tennis_live import tennis_live_order_worker as TW

    motore = b.pb.motore
    prima = motore._blocco_modo
    motore._blocco_modo = ET._blocco_apertura_modo          # la funzione VERA del runner
    acks0 = len(b.pb._ack)
    try:
        with MOD.dichiara_per_banco("PAPER"):
            _condotta_catena(b, A, pref, e, "mode_non_servibile", stato)
            nuovi = list(b.pb._ack.values())[acks0:]
            e.controlla("il rifiuto dice «Ordini reali» (non un client assente)",
                        bool(nuovi) and all("Ordini reali" in str(a.get("motivo") or "")
                                            for a in nuovi if a.get("accettato") is False),
                        [a.get("motivo") for a in nuovi][:2])
            _CONTESTO.modo_processo = "LIVE"                 # tetto LIVE del runner
            try:
                e.controlla("ladder (coda e /order del worker): apertura reale rifiutata",
                            TW._blocco_apertura_modo("live", "place", {}) is not None, "")
                e.controlla("ladder: la prova passa",
                            TW._blocco_apertura_modo("paper", "place", {}) is None, "")
                e.controlla("ladder: chiusure reali servite (green-up, cancel, riduzione)",
                            TW._blocco_apertura_modo("live", "greenup", {}) is None
                            and TW._blocco_apertura_modo("live", "cancel", {}) is None
                            and TW._blocco_apertura_modo(
                                "live", "place", {"reduces_liability": True}) is None, "")
                e.controlla("terza rete (4 bot, ogni strada): ordine reale fermo",
                            GT.motivo_reale_fermo() is not None, "")
                esito = _terza_rete_su_ordine(b, stato.get("r1_sel"))
                e.controlla("terza rete DENTRO flumine: un'apertura sul client live del "
                            "banco e' rifiutata (ControlError)", esito == "rifiutato", esito)
            finally:
                _CONTESTO.modo_processo = None
    finally:
        motore._blocco_modo = prima


def _terza_rete_su_ordine(b: BancoRapido, sel_da_evitare: Any = None) -> str:
    """Il trading control VERO ``ControlloModoOrdiniTennis`` su un'APERTURA
    (BACK 2,00 su una selezione DIVERSA da quella delle posizioni degli scenari
    di prima: alza la perdita worst-case, quindi non e' una chiusura) col client
    LIVE del banco: 'rifiutato' | 'passa' | 'errore: ...'. Solo ``_validate``:
    nessun ordine nasce nel blotter, nessun client e' chiamato."""
    from flumine.controls import ControlError
    from flumine.order.orderpackage import OrderPackageType
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    from ..tennis_live import guardie_tennis as GT

    try:
        sel = None
        for r in list(getattr(b.book, "runners", None) or []):
            if str(r.selection_id) != str(sel_da_evitare):
                sel = int(r.selection_id)
                break
        if sel is None:
            sel = int(b.book.runners[0].selection_id)
        prezzo = 2.0
        o = Trade(b.market_id, sel, 0.0, b.strat).create_order(
            "BACK", LimitOrder(prezzo, 2.0))
        o.update_client(b.pb.cliente_live)
        GT.ControlloModoOrdiniTennis(b.pb.vista)._validate(o, OrderPackageType.PLACE)
        return "passa"
    except ControlError:
        return "rifiutato"
    except Exception as ex:  # noqa: BLE001 - il controllo lo dice, mai un'eccezione
        return "errore: %s" % str(ex)[:120]


def _r11d(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """R11d (04/10) - tetto LIVE + «Ordini reali» LIVE scelto in questo avvio: il
    comando live di Safe tennis passa TUTTE le guardie di modo e va al client
    live del banco (``ClienteLiveBanco``: l'«ordine reale» simulato, nessun
    soldo). Solo tennis: il calcio lo prova R1 (banco LIVE)."""
    if b.sport != "tennis":
        e.na = "solo runner tennis (il calcio: R1 col banco LIVE)"
        return
    from .. import modo_ordini as MOD
    from ..live_order_worker import _CONTESTO
    from ..tennis_live import esecutore_tennis as ET
    from ..tennis_live import guardie_tennis as GT

    motore = b.pb.motore
    prima = motore._blocco_modo
    motore._blocco_modo = ET._blocco_apertura_modo
    try:
        with MOD.dichiara_per_banco("LIVE"):
            q = b.quota("lay")
            sel = int(q[0] if q else (stato.get("r1_sel") or 0))
            prezzo = float(q[1]) if q else 2.0
            ord0 = len(b.ordini_del_motore())
            tid = A.riserva(side="lay", price=prezzo, size=2.0)
            ref = "%s%d" % (pref, tid)
            A.invia(tid, selection_id=sel, side="lay", price=prezzo, size=2.0)
            ack = _ack_di(b, ref)
            e.controlla("comando LIVE accettato dal motore (guardie di modo passate)",
                        ack.get("accettato") is True, ack)
            fase = _aspetta_terminale(b, ref)
            nuovi = b.ordini_del_motore()[ord0:]
            if nuovi:
                cl = getattr(nuovi[-1], "client", None)
                e.controlla("l'ordine e' sul client LIVE del banco (mai sul simulato)",
                            str(getattr(getattr(cl, "VENUE", None), "name", "")) == "BANCO_LIVE",
                            repr(cl))
            else:
                motivo = _motivo_esito_diario(b, ref)
                e.controlla("nessun ordine solo per il mercato (mai per il modo): fase=%s "
                            "book=%s motivo=%s" % (fase, getattr(b.book, "status", None),
                                                   motivo[:120]),
                            "Ordini reali" not in motivo and "mode_non_servibile" not in motivo,
                            (fase, motivo))
            _CONTESTO.modo_processo = "LIVE"
            try:
                e.controlla("terza rete: ordine reale libero con «Ordini reali» LIVE",
                            GT.motivo_reale_fermo() is None, "")
                esito = _terza_rete_su_ordine(b, stato.get("r1_sel"))
                e.controlla("terza rete DENTRO flumine: l'apertura sul client live passa",
                            esito == "passa", esito)
            finally:
                _CONTESTO.modo_processo = None
            A.risolvi(tid)
    finally:
        motore._blocco_modo = prima


def _r11b(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """R11b - «Ordini reali» su PAPER (modo effettivo), tetto LIVE: aperture
    rifiutate, la CHIUSURA della posizione di R5 passa (mai bloccata)."""
    if b.sport == "tennis":
        _r11b_tennis(b, A, pref, e, stato)
        return
    from .. import live_order_worker as LOW
    from .. import modo_ordini as MOD

    motore = b.pb.motore
    prima = motore._blocco_modo
    env_prima = os.environ.get("LIVE_ORDER_MODE")
    os.environ["LIVE_ORDER_MODE"] = "LIVE"
    motore._blocco_modo = LOW._blocco_apertura_modo      # la funzione VERA del runner
    try:
        with MOD.dichiara_per_banco("PAPER"):
            _condotta_catena(b, A, pref, e, "mode_non_servibile", stato)
        # la chiusura a modo effettivo PAPER: la posizione di R5 e' gia' chiusa in
        # R7; la regola (chiusure mai bloccate) e' provata sul motore vero in
        # stream/tests/test_motore_ordini_2026_09_24.py::
        # test_modo_effettivo_dalla_ui_blocca_le_aperture_non_le_chiusure
        e.controlli.append(("chiusura a «Ordini reali» PAPER: coperta dal test del motore "
                            "(posizione di R5 gia' chiusa in R7)", True, ""))
    finally:
        motore._blocco_modo = prima
        if env_prima is None:
            os.environ.pop("LIVE_ORDER_MODE", None)
        else:
            os.environ["LIVE_ORDER_MODE"] = env_prima


def _motivo_esito_diario(b: BancoRapido, ref: str) -> str:
    mot = b.pb.motore
    esiti = [r for r in mot.diario.leggi(mot._giorni_diario())
             if r.get("tipo") == "esito" and r.get("ref") == ref]
    return str((esiti[-1].get("errore") if esiti else "") or "")


def _r8_tennis(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """28/09 - DECISIONE DELL'UTENTE su R-1 ("porta al limite minimo
    accettato"): il runner tennis non ha il place-and-trim e un'apertura sotto
    il minimo NON si rifiuta piu': parte AL minimo (BACK 1,00 dal 01/10) come place
    normale, e l'evento lo DICE (``portata_al_minimo``). Prima: rifiuto
    ``submin_non_percorribile``, nessun ordine."""
    sel, prezzo_b, _d = b.quota("back")
    # minimi .it definitivi 01/10: punta 1,00 / banca 1,00 / trim >= 0,50
    size = 0.70                                 # BACK sotto il minimo .it (1,00)
    tid = A.riserva(side="back", price=prezzo_b, size=size)
    ref = "%s%d" % (pref, tid)
    ord0, rest0 = len(b.ordini_del_motore()), _conta_rest(b)
    A.invia(tid, selection_id=sel, side="back", price=prezzo_b, size=size)
    fase = _aspetta_terminale(b, ref, secondi=5.0)
    motivo = _motivo_esito_diario(b, ref)
    e.controlla("evento terminale NON 'rifiutato' (l'apertura parte)",
                fase is not None and fase != "rifiutato", fase)
    e.controlla("nessun motivo di rifiuto nel diario del runner", motivo == "", motivo[:160])
    eventi = list(b.pb.esiti(ref) or [])
    primo = eventi[0] if eventi else {}
    e.controlla("l'evento DICE che l'importo e' stato portato al minimo",
                primo.get("portata_al_minimo") == {"chiesto": size, "piazzato": 1.0},
                primo.get("portata_al_minimo"))
    nuovi = b.ordini_del_motore()[ord0:]
    e.controlla("UN ordine al minimo (1,00) alla quota chiesta, nessun REST",
                len(nuovi) == 1 and _conta_rest(b) == rest0
                and abs(float(nuovi[0].order_type.size) - 1.0) < 1e-9
                and abs(float(nuovi[0].order_type.price) - prezzo_b) < 1e-6,
                ([(o.order_type.size, o.order_type.price) for o in nuovi],
                 b.rest[rest0:]))
    e.controlla("nessun place-and-trim appeso", not b.pb.motore._submin,
                list(b.pb.motore._submin))
    riga = A.risolvi(tid)
    e.controlla("riga non in errore (esito dall'ordine vero, nessun rifiuto inventato)",
                riga.get("status") != "error", riga.get("status"))
    stato["r8_tennis_portata_al_minimo"] = primo.get("portata_al_minimo")


def _r10_tennis(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """Il runner tennis NON segue la partita: il comando di Safe tennis sul
    MATCH_ODDS vero e' accettato ``in_aggancio``, la partita entra nel piano
    a priorita' COMANDO e l'ordine parte al primo book NUOVO."""
    from ..tennis_live import iscrizione_a_caldo as IAC

    ag = b.pb.monta_aggancio_tennis(tetto=IAC.tetto_mercati(), seguiti={})
    try:
        sel, prezzo, _d = b.quota("lay")
        tid = A.riserva(side="lay", price=prezzo, size=2.0)
        ref = "%s%d" % (pref, tid)
        rest0, ord0 = _conta_rest(b), len(b.ordini_del_motore())
        e.controlla("prima del comando il runner NON segue il mercato",
                    not ag.servibile(b.market_id), dict(b.pb.sessione.market_meta))
        out = A.invia(tid, selection_id=sel, side="lay", price=prezzo, size=2.0)
        ack = _ack_di(b, ref)
        e.controlla("esito dell'invio 'pending' (il bot attende l'esito)",
                    getattr(out, "status", None) == "pending", out)
        e.controlla("ack ACCETTATO con motivo 'in_aggancio' (dichiarato)",
                    ack.get("accettato") is True
                    and str(ack.get("motivo") or "").startswith("in_aggancio"), ack)
        fase = _aspetta_terminale(b, ref, secondi=SECONDI_TENNIS)
        comandi = b.pb.sessione.comandi
        e.controlla("partita nel piano come COMANDO, con l'event_id vero del catalogo",
                    str(b.event_id) in comandi
                    and comandi[str(b.event_id)]["market_id"] == b.market_id,
                    {k: v.get("market_id") for k, v in comandi.items()})
        chiamate = ag.allinea_banco.chiamate
        e.controlla("sottoscrizione (allineamento) col mercato del comando",
                    bool(chiamate) and b.market_id in chiamate[-1], chiamate[-1:])
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
        if fase == "abbinato":
            e.controlla("riga 'open' con l'abbinato del runner",
                        riga.get("status") == "open", riga.get("status"))
        else:
            e.controlla("FOK non abbinato: riga 'error' (esito vero, non un rifiuto del "
                        "runner)", riga.get("status") == "error" and fase != "rifiutato",
                        (riga.get("status"), fase))
        stato["r10_fase"] = fase
        stato["r10_aggancio"] = ag.stato()
    finally:
        b.pb.smonta_aggancio_tennis()


def _r10b_tennis(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """Tetto pieno (1): una partita candidata SENZA posizioni occupa il posto; il
    comando di Safe tennis sul MATCH_ODDS la espelle ed e' eseguito."""
    ag = b.pb.monta_aggancio_tennis(tetto=1, seguiti={"E-candidata": "1.000000001"})
    try:
        tid = A.riserva(side="lay", price=1.01, size=2.0)
        ref = "%s%d" % (pref, tid)
        ord0 = len(b.ordini_del_motore())
        sel, _p, _d = b.quota("lay")
        A.invia(tid, selection_id=sel, side="lay", price=1.01, size=2.0)
        ack = _ack_di(b, ref)
        e.controlla("ack accettato in_aggancio", ack.get("accettato") is True
                    and str(ack.get("motivo") or "").startswith("in_aggancio"), ack)
        fase = _aspetta_terminale(b, ref, secondi=SECONDI_TENNIS)
        meta = b.pb.sessione.market_meta
        e.controlla("la candidata SENZA posizioni e' espulsa, entra la partita del comando",
                    "E-candidata" not in meta and ag.allinea_banco.espulsi == ["E-candidata"]
                    and [v["market_id"] for v in meta.values()] == [b.market_id],
                    (dict(meta), ag.allinea_banco.espulsi))
        sul_cmd = [o for o in b.ordini_del_motore()[ord0:]
                   if str(getattr(o, "market_id", "")) == b.market_id]
        e.controlla("comando eseguito dopo l'espulsione: ordine ed evento terminale",
                    len(sul_cmd) >= 1 and fase is not None, (len(sul_cmd), fase))
        e.controlla("mai piu' partite del tetto",
                    all(len(c) <= 1 for c in ag.allinea_banco.chiamate),
                    ag.allinea_banco.chiamate)
        A.risolvi(tid)
    finally:
        b.pb.smonta_aggancio_tennis()


def _r10c_tennis(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """Tetto pieno (1) di partite NON espellibili: il MATCH_ODDS con gli ordini
    degli scenari precedenti (posizioni), poi una partita seguita A MANO. Niente
    espulso: rifiuto dichiarato ``tetto_mercati_pieno``, nessun ordine."""
    try:
        n_ord = len(list(iter(b.market.blotter)))
    except Exception:  # noqa: BLE001
        n_ord = 0
    if n_ord == 0:
        e.na = "il MATCH_ODDS non ha ordini dagli scenari precedenti"
        return
    sel, prezzo, _d = b.quota("lay")
    for caso, seguiti, manuali, mercato in (
            ("posizioni", {str(b.event_id): b.market_id}, (), "1.000000002"),
            ("manuale", {"E-a-mano": "1.000000001"}, ("E-a-mano",), b.market_id)):
        ag = b.pb.monta_aggancio_tennis(tetto=1, seguiti=seguiti, manuali=manuali)
        try:
            prima = dict(b.pb.sessione.market_meta)
            tid = A.riserva(side="lay", price=1.01, size=2.0)
            ref = "%s%d" % (pref, tid)
            ord0, rest0 = len(b.ordini_del_motore()), _conta_rest(b)
            out = _invia_su(b, A, tid, mercato, sel, 1.01)
            b.pompa(0.5)
            ack = _ack_di(b, ref)
            e.controlla("[%s] rifiuto dichiarato 'tetto_mercati_pieno'" % caso,
                        ack.get("accettato") is False
                        and str(ack.get("motivo") or "").startswith("tetto_mercati_pieno"),
                        ack)
            e.controlla("[%s] niente espulso: le partite seguite sono quelle di prima" % caso,
                        dict(b.pb.sessione.market_meta) == prima
                        and not ag.allinea_banco.espulsi, dict(b.pb.sessione.market_meta))
            e.controlla("[%s] nessun ordine, nessun REST" % caso,
                        len(b.ordini_del_motore()) == ord0 and _conta_rest(b) == rest0,
                        (len(b.ordini_del_motore()) - ord0, b.rest[rest0:]))
            e.controlla("[%s] esito certo negativo per il bot" % caso,
                        getattr(out, "status", None) == "error"
                        and "tetto_mercati_pieno" in str(getattr(out, "fill_note", "")),
                        out)
        finally:
            b.pb.smonta_aggancio_tennis()


def _r10d_tennis(b: BancoRapido, A: Any, pref: str, e: _Esito, stato: Dict[str, Any]) -> None:
    """Il mercato chiesto non esiste (il catalogo non lo risolve): il comando
    accettato ``in_aggancio`` NON scade in silenzio."""
    from ..tennis_live import iscrizione_a_caldo as IAC

    ag = b.pb.monta_aggancio_tennis(tetto=IAC.tetto_mercati(), seguiti={})
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
        motivo = _motivo_esito_diario(b, ref)
        e.controlla("evento terminale 'rifiutato' (mai in silenzio)",
                    ev.get("fase") == "rifiutato", ev.get("fase"))
        e.controlla("esito nel diario del runner col motivo 'in_aggancio'",
                    motivo.startswith("in_aggancio"), motivo[:160])
        e.controlla("catalogo non risolto contato (mercato inesistente)",
                    ag.conti["catalogo_ko"] >= 1, ag.conti)
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
        b.pb.smonta_aggancio_tennis()


# ---------------------------------------------------------------------------
# l'ingresso da certifica
# ---------------------------------------------------------------------------
def main_rapidi(scheda: Any, eventi: List[str], data_dir: str, *, trasporto: Optional[str],
                diario: Optional[str], tracce: Optional[str], lavora: Callable[..., Any],
                freni: Callable[[], Any], intestazione: Optional[str] = None) -> int:
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
    if intestazione:
        # 02/10 (PARITA_SAFE_ENV): l'ambiente DICHIARATO del banco, in testa
        scrivi(intestazione)
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
