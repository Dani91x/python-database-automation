# -*- coding: utf-8 -*-
"""LO SCALPER CALCIO SULLE REGISTRAZIONI VERE - il SERVIZIO di produzione sul banco.

Fa rivivere a `scalper_session.run_session` (il processo che il supervisore
`scalper_service` lancia per OGNI partita armata dalla UI) una partita
registrata, e giudica la CONDOTTA con `Betfair/stream/scalper/certificazione.py`.
Non misura il profitto (`PROCESSO_STANDARD_BOT.md` gradino 3).

LA CATENA, e nessun passo e' saltato o riscritto:

    raw registrato  `_live_raw/<id>/<id>.raw.jsonl` (stream NATIVO Betfair)
      -> flumine    `FlumineSimulation` + `HistoricalStream` del BANCO COMUNE
                    (`banco_comune.MotoreReplay`, UN `SimulatedMiddleware`,
                    tetti di flumine aperti, lapse al fischio e alla
                    sospensione, orologio monotono)
      -> `scalper_session.run_session` VERO: legge il control, costruisce i
         parametri (VALIDATED_PARAMS + whitelist UI + stake), sceglie paper/live
         (client `paper_trade`), crea `ScalperStrategy` e il semaforo di
         rischio, arma lo specchio ordini, fa girare heartbeat, stop da UI,
         kill-switch, cap globale, fine vita (KO+10'), gestione del crash e
         stato finale - TUTTO codice di produzione
      -> `ScalperStrategy` VERA (`check_market_book` / `process_market_book`)
         su ogni book dei mercati che la sessione ha scelto dal catalogo
      -> ordini VERI su flumine (`market.place_order`, LAPSE, pacchetto
         asincrono eseguito da flumine quando il tempo di mercato supera
         `place_latency + betDelay`: e' cosi' anche in produzione, dove il bot
         non si blocca sulla REST)
      -> lo SPECCHIO VERO della sessione (`_make_session_mirror`, cioe'
         `LiveTradingStrategy.process_orders`) alla sua cadenza (1 s di
         mercato): le righe di `betfair_live_orders` si catturano, non si scrivono

I FINTI INIETTATI (e soltanto questi; ognuno con le chiavi del vero):
  * `scalper_session.Db`          -> `_DbFinto`: `scalper_control` con le
                                     colonne e i CHECK di `migrations/scalper_bot.sql`,
                                     `scalper_activity`, `live_alerts`, `live_follow`
  * `auth.build_client`/`keep_alive` -> `_TradingFinto`: il CATALOGO costruito dai
                                     `marketDefinition` del raw (limite 1)
  * `flumine.Flumine` / `clients.BetfairClient` -> `_FrameworkSessione`: il
                                     framework della sessione e' un involucro sul
                                     quadro del banco; il client chiesto dalla
                                     sessione (paper_trade, order_stream,
                                     min_bet_validation) si REGISTRA per la parita'
  * `scalper_session._order_mirror_loop` -> lo stesso `mirror.process_orders`
                                     chiamato dal thread del motore alla stessa
                                     cadenza (1 s), per non leggere il blotter da
                                     due thread
  * `scalper_session.time` e `time.time` -> l'OROLOGIO DI MERCATO (vedi sotto)
  * `scalper_session.KILL_FILE`   -> un file in una cartella temporanea del
                                     replay: MAI il `STOP_SCALPER` della cwd, che
                                     fermerebbe la produzione vera
  * `db_client.get_supabase_client` -> ESPLODE: nessun accesso al DB vero puo'
                                     passare in silenzio
Nessun ordine a Betfair, nessuna scrittura sul DB vero.

L'OROLOGIO. In produzione il thread della sessione dorme `HEARTBEAT_S` (5 s)
fra un giro di sorveglianza e l'altro mentre il thread di flumine riceve lo
stream. Qui i due thread si passano il TURNO (`_Orologio`): il motore avanza
i book finche' il tempo di mercato non raggiunge la sveglia della sessione,
poi si ferma e la sessione fa il suo giro (heartbeat, stop, cap, fine vita)
esattamente a quell'istante di mercato. `time.time` (che lo scalper usa per il
tetto transazioni/ora, il rate dei submin e il dry-run) e' l'orologio di
mercato: in produzione il tempo reale COINCIDE con quello del mercato, nel
replay no.

LIMITI DICHIARATI (stampati nel referto)
  1. IL CATALOGO NON C'E' nel raw: si ricostruisce dai `marketDefinition`
     (tipi di mercato veri, nomi dei runner sintetizzati con la convenzione
     Betfair: MATCH_ODDS 3 = "The Draw"). L'ordinamento `MAXIMUM_TRADED` non si
     riproduce: con 4 tipi di sessione e `max_results=25` entra tutto comunque.
  2. LO SCANNER NON SERVE: lo scalper legge il MarketBook direttamente
     (par.6.2 non applicabile, dichiarato).
  3. PUNTEGGI: la sessione in modalita' maker non legge `live_now`; i watcher
     di intervallo/sniper/theta non sono nel perimetro (sniper e theta sono
     strategie separate, non certificate qui).
  4. I PACCHETTI REPLACE (park-trim-replace dei submin) creano l'ordine nuovo
     dentro flumine: il guasto CP non li colpisce (limite del banco comune).
  5. SETTLEMENT: la sessione finisce a KO+10' (fine vita di produzione) e il
     mercato non chiude prima: `pnl_settled` non si misura (e in produzione e'
     lo stesso).
  6. `FreshDelaySimulatedExecution` (paper) viene installata come in
     produzione ma nel banco non cambia nulla: l'attesa del bet delay la fa
     `_check_pending_packages` PRIMA dell'esecuzione.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import io
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import time as _time_mod
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...backtest import chiusura_parziale as CP
from .. import certificazione as CERT

logger = logging.getLogger(__name__)

# i veri, catturati all'import: l'orologio finto NON deve mai chiamare se stesso
_TIME_VERO = _time_mod.time
_MONOTONIC = _time_mod.monotonic

# oltre questi secondi REALI senza che il turno passi, il banco si dichiara
# bloccato invece di restare appeso
ATTESA_MASSIMA_REALE_S = 300.0

EVENTO_DI_RIFERIMENTO = "35760084"

# i guasti: quanti piazzamenti colpire e di quanto ritardare l'esito
PIAZZAMENTI_RIFIUTATI = 6
PIAZZAMENTI_IGNOTI = 6
RITARDO_ESITO_IGNOTO_S = 20.0
# quanto aspetta il supervisore prima di dichiarare orfana una sessione morta
# (`scalper_service.ORPHAN_HEARTBEAT_S`, letto dal vero) e quanto l'utente
# prima di riarmare
ATTESA_RIARMO_S = 60.0

SCENARI_DESCRITTI: Dict[str, str] = {
    "base": ("come gira in produzione, sul percorso degli ordini VERI: il control "
             "che la UI scrive coi suoi default (maker, stake 25, missione "
             "2-tick accesa) e dry_run=False (LIVE)"),
    "paper": ("lo stesso control con dry_run=True: client flumine paper_trade, "
              "latenza paper, esecuzione a bet delay fresco. Paper = live "
              "(controllo S6)"),
    "senza-missione": ("SOLO la casella 'missione 2-tick' spenta dalla UI "
                       "(one_green_per_phase=False): il bot fa tutti i cicli "
                       "che la strategia gli concede, cosi' i controlli di "
                       "ciclo hanno piu' casi"),
    "bot-fermo": ("a meta' della finestra pre-match l'utente preme STOP "
                  "(`scalper_stop`: running -> stopping): force-flat, attesa "
                  "del flat, stato 'stopped'"),
    "kill-switch": ("a meta' della finestra pre-match compare il file "
                    "STOP_SCALPER (in una cartella del replay, mai quella vera)"),
    "esiti-ignoti": ("i primi %d piazzamenti restano SENZA ESITO per %d s di "
                     "mercato (PENDING, nessun bet_id): la risposta di Betfair "
                     "tarda, come in un timeout" % (PIAZZAMENTI_IGNOTI,
                                                   int(RITARDO_ESITO_IGNOTO_S))),
    "rifiuti-betfair": ("i primi %d piazzamenti sono RIFIUTATI da un trading "
                        "control di flumine (place_order torna False, stato "
                        "Violation): difetto 2 del catalogo" % PIAZZAMENTI_RIFIUTATI),
    "riavvio": ("a meta' della finestra pre-match il PROCESSO della sessione "
                "muore; dopo %d s il supervisore la marca 'error' (orfana), "
                "l'utente la riarma e parte una sessione NUOVA: la posizione "
                "della vecchia deve essere governata o dichiarata (S7)"
                % int(ATTESA_RIARMO_S)),
    CP.SCENARIO: "come `base`, ma " + CP.DESCRIZIONE,
}


# ---------------------------------------------------------------------------
# il control che la UI scrive (`ScalperPanel.tsx` + `lib/scalper.ts`)
# ---------------------------------------------------------------------------
def control_della_ui(event_id: str, scenario: str) -> Dict[str, Any]:
    """La riga `scalper_control` che `scalper_activate` scrive coi DEFAULT della
    UI (`SCALPER_PARAM_DEFAULTS`, mode 'maker', stake 25, missione ON,
    ht/sniper/theta spenti). Le chiavi sono le colonne della migrazione.
    Gli scenari cambiano SOLO numeri che la UI espone."""
    params: Dict[str, Any] = {
        "scalp_ticks": 1, "stop_ticks": 1, "min_flow": 10, "min_size": 300,
        "price_min": 1.5, "price_max": 4.6, "entry_stop_before_s": 420,
        "flatten_before_s": 180, "event_profit_target": 1, "event_loss_cap": 1.5,
        "one_green_per_phase": True, "ht_mode": False, "sniper_mode": False,
        "sniper_stake": 10,
    }
    if scenario == "senza-missione":
        params["one_green_per_phase"] = False
    return {
        "event_id": str(event_id), "status": "requested", "mode": "maker",
        "dry_run": scenario == "paper", "stake": 25, "params": params,
        "bias": None, "bias_meta": None, "stats": None, "error": None,
        "requested_at": None, "started_at": None, "stopped_at": None,
        "heartbeat_at": None, "updated_at": None,
    }


# ---------------------------------------------------------------------------
# la registrazione: catalogo, KO, nomi
# ---------------------------------------------------------------------------
def percorso_raw(data_dir: str, event_id: str) -> str:
    return os.path.join(data_dir, str(event_id), "%s.raw.jsonl" % event_id)


def leggi_definizioni(raw: str) -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    """{market_id: {"market_type", "runners": [(id, sortPriority)]}} e il
    `marketTime` del MATCH_ODDS, dal PRIMO `marketDefinition` di ogni mercato."""
    definizioni: Dict[str, Dict[str, Any]] = {}
    ko: Optional[str] = None
    with io.open(raw, "r", encoding="utf-8") as fh:
        for riga in fh:
            try:
                d = json.loads(riga)
            except ValueError:
                continue
            for mc in d.get("mc") or []:
                md = mc.get("marketDefinition")
                if not md:
                    continue
                mid = str(mc.get("id"))
                if mid not in definizioni:
                    definizioni[mid] = {
                        "market_type": md.get("marketType"),
                        "runners": [(int(r["id"]), r.get("sortPriority"))
                                    for r in (md.get("runners") or []) if r.get("id")],
                    }
                if md.get("marketType") == "MATCH_ODDS" and ko is None:
                    ko = md.get("marketTime")
    return definizioni, ko


def primo_publish_time_ms(raw: str) -> Optional[int]:
    """Il `pt` della prima riga del raw: l'istante in cui la sessione si arma.
    Senza, le scritture fatte PRIMA del primo book (arming, running) avrebbero
    l'ora del PC invece di quella del mercato."""
    with io.open(raw, "r", encoding="utf-8") as fh:
        for riga in fh:
            try:
                pt = json.loads(riga).get("pt")
            except ValueError:
                continue
            if pt is not None:
                return int(pt)
    return None


def catalogo_dal_raw(definizioni: Dict[str, Dict[str, Any]]) -> List[Any]:
    """Gli oggetti che `list_market_catalogue` restituirebbe (limite 1): gli
    attributi letti da `run_session` sono `market_id`, `runners[].selection_id`,
    `runners[].runner_name`."""
    from ...backtest.sim_strategy import _synth_name

    out = []
    for mid, d in sorted(definizioni.items()):
        runners = [SimpleNamespace(selection_id=sid,
                                   runner_name=_synth_name(d.get("market_type"), sp) or str(sid))
                   for sid, sp in d.get("runners") or []]
        out.append(SimpleNamespace(market_id=mid, market_type=d.get("market_type"),
                                   runners=runners, total_matched=0.0))
    return out


def qualita_registrazione(data_dir: str, event_id: str) -> str:
    try:
        from ...tools.validate_recordings import validate_event

        rep = validate_event(data_dir, str(event_id))
        return "%s %s%%" % (rep.verdict, rep.coverage_pct)
    except Exception as ex:  # noqa: BLE001 - il verdetto e' un di piu'
        return "ignota (%s)" % type(ex).__name__


# ---------------------------------------------------------------------------
# L'OROLOGIO: il turno fra il thread della sessione e quello del motore
# ---------------------------------------------------------------------------
class _ProcessoUcciso(BaseException):
    """Il processo della sessione muore (scenario `riavvio`). BaseException:
    nessun `except Exception` della sessione lo intercetta, come nessun
    `except` sopravvive a un processo ucciso."""


class BancoBloccato(BaseException):
    """Il turno non passa piu': guasto del BANCO. BaseException perche' ne'
    `call_strategy_error_handling` di flumine ne' l'`except Exception` della
    sessione devono poterlo inghiottire: deve diventare un replay esploso."""


class _Orologio:
    """Il tempo e' quello di MERCATO; il turno passa fra chi dorme e chi avanza.

    * il thread di CONTROLLO (la sessione, o il replay che fa da supervisore)
      chiama `sleep(s)`: fissa la sveglia a `ora + s` e cede il turno;
    * il thread del MOTORE chiama `al_book(t)` a ogni book: se la sveglia e'
      raggiunta, cede il turno e aspetta che il controllo si riaddormenti.
    Nessuno dei due lavora mentre l'altro lavora: lo stato della strategia non
    si legge mai mentre flumine lo sta cambiando.
    """

    def __init__(self) -> None:
        self._cv = threading.Condition()
        self.ora_s: Optional[float] = None
        self._sveglia: Optional[float] = None
        self._pendente: Optional[float] = None
        self._turno = "controllo"
        self.motore_finito = False
        self.libero = False            # nessun controllo: il motore corre
        self._uccidi: Optional[BaseException] = None
        # ogni istante di mercato (ms) in cui un book e' arrivato, nell'ORDINE
        # di arrivo: serve a S5 per scomputare i silenzi VERI della
        # registrazione (nessun book, qualunque market) dal ritardo del
        # heartbeat (`buchi`, sotto; difetto 24/09)
        self.libro_ms: List[int] = []

    # ------------------------------------------------------------ lettura
    def time(self) -> float:
        o = self.ora_s
        return float(o) if o is not None else _TIME_VERO()

    def buchi(self, soglia_ms: int = 2000) -> List[Tuple[int, int]]:
        """Coppie (inizio, fine) in cui NESSUN book (di nessun mercato della
        sessione) e' arrivato per almeno `soglia_ms`: il turno non poteva
        passare alla sessione piu' spesso di cosi', in un replay che avanza
        il tempo SOLO ai book (vedi il docstring del modulo, 'L'OROLOGIO')."""
        out: List[Tuple[int, int]] = []
        prima = None
        for ms in self.libro_ms:
            if prima is not None and ms - prima >= soglia_ms:
                out.append((prima, ms))
            prima = ms
        return out

    def ora_ms(self) -> int:
        return int(round(self.time() * 1000.0))

    # ------------------------------------------------------------ controllo
    def uccidi_al_prossimo_sonno(self, ex: BaseException) -> None:
        with self._cv:
            self._uccidi = ex

    def _forse_muori(self) -> None:
        if self._uccidi is not None:
            ex, self._uccidi = self._uccidi, None
            raise ex

    def sleep(self, secondi: float) -> None:
        secondi = max(0.0, float(secondi or 0.0))
        with self._cv:
            self._forse_muori()
            if self.motore_finito:
                if self.ora_s is not None:
                    self.ora_s += secondi
                return
            if self.ora_s is None:
                self._pendente = secondi
                self._sveglia = None
            else:
                self._sveglia = self.ora_s + secondi
            self._turno = "motore"
            self._cv.notify_all()
            limite = _MONOTONIC() + ATTESA_MASSIMA_REALE_S
            while self._turno == "motore" and not self.motore_finito:
                self._cv.wait(0.5)
                if _MONOTONIC() > limite:
                    raise BancoBloccato("il motore non restituisce il turno")
            if self._turno == "motore":
                # il motore e' finito mentre si dormiva: il tempo scorre lo stesso
                if self._sveglia is not None and self.ora_s is not None:
                    self.ora_s = max(self.ora_s, self._sveglia)
                self._turno = "controllo"
            self._forse_muori()

    def libera(self) -> None:
        """Nessuno controlla piu': il motore corre fino in fondo."""
        with self._cv:
            self.libero = True
            self._turno = "motore"
            self._cv.notify_all()

    # ------------------------------------------------------------ motore
    def al_book(self, t_s: float) -> None:
        with self._cv:
            self.libro_ms.append(int(round(t_s * 1000.0)))
            self.ora_s = t_s if self.ora_s is None else max(self.ora_s, t_s)
            if self._pendente is not None:
                self._sveglia = self.ora_s + self._pendente
                self._pendente = None
            limite = _MONOTONIC() + ATTESA_MASSIMA_REALE_S
            while self._turno == "controllo" and not self.libero:
                self._cv.wait(0.5)
                if _MONOTONIC() > limite:
                    raise BancoBloccato("la sessione non restituisce il turno")
            if (not self.libero and self._sveglia is not None
                    and self.ora_s >= self._sveglia):
                self._sveglia = None
                self._turno = "controllo"
                self._cv.notify_all()
                limite = _MONOTONIC() + ATTESA_MASSIMA_REALE_S
                while self._turno == "controllo" and not self.libero:
                    self._cv.wait(0.5)
                    if _MONOTONIC() > limite:
                        raise BancoBloccato("la sessione non restituisce il turno")

    def fine_motore(self) -> None:
        with self._cv:
            self.motore_finito = True
            self._cv.notify_all()


class _TempoSessione:
    """Il modulo `time` visto da `scalper_session` (usa solo sleep e time)."""

    def __init__(self, orologio: _Orologio) -> None:
        self._o = orologio

    def sleep(self, s: float) -> None:
        self._o.sleep(s)

    def time(self) -> float:
        return self._o.time()


# ---------------------------------------------------------------------------
# il DATABASE finto della sessione: colonne e CHECK della migrazione
# ---------------------------------------------------------------------------
class _Risposta:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Tabella:
    """Il builder di supabase-py che la sessione usa su `db.sb.table(...)`:
    insert/select/update + eq/in_ + execute."""

    def __init__(self, db: "_DbFinto", nome: str) -> None:
        self._db = db
        self._nome = nome
        self._op: Optional[str] = None
        self._riga: Any = None

    def insert(self, riga: Any) -> "_Tabella":
        self._op, self._riga = "insert", riga
        return self

    def select(self, *_a: Any, **_k: Any) -> "_Tabella":
        self._op = "select"
        return self

    def update(self, riga: Any) -> "_Tabella":
        self._op, self._riga = "update", riga
        return self

    def eq(self, *_a: Any, **_k: Any) -> "_Tabella":
        return self

    def in_(self, *_a: Any, **_k: Any) -> "_Tabella":
        return self

    def execute(self) -> _Risposta:
        if self._op == "insert":
            righe = self._riga if isinstance(self._riga, list) else [self._riga]
            dest = self._db.tabelle.setdefault(self._nome, [])
            for r in righe:
                r = json.loads(json.dumps(r, default=str))
                r["_ms"] = self._db.orologio.ora_ms()
                dest.append(r)
            return _Risposta(righe)
        # `live_now` (watcher di ht/sniper/theta) e `theta_confirm_requests`:
        # nessuna riga, come un evento senza punteggio pubblicato
        return _Risposta([])


class _SbFinto:
    def __init__(self, db: "_DbFinto") -> None:
        self._db = db

    def table(self, nome: str) -> _Tabella:
        return _Tabella(self._db, nome)


class _DbFinto:
    """`scalper_session.Db` con le firme e i tipi del vero.

    `scalper_control` si comporta come la tabella della migrazione: una
    scrittura che viola un CHECK viene RIFIUTATA (come farebbe Postgres) e il
    vero `set_control` la inghiotte col suo warning; il controllo S1 la vede
    comunque, perche' ogni scrittura TENTATA e' registrata.
    """

    def __init__(self, orologio: _Orologio, control: Dict[str, Any],
                 follow: Dict[str, Any]) -> None:
        self.orologio = orologio
        self.control = dict(control)
        self.follow_row = dict(follow)
        self.scritture: List[Dict[str, Any]] = []
        self.tabelle: Dict[str, List[Dict[str, Any]]] = {}
        self.sb = _SbFinto(self)
        self.stati_visti: List[str] = []

    @staticmethod
    def _viola_check(campi: Dict[str, Any]) -> Optional[str]:
        st = campi.get("status")
        if st is not None and str(st) not in CERT.STATI_CONTROL_AMMESSI:
            return "status"
        mo = campi.get("mode")
        if mo is not None and str(mo) not in CERT.MODI_CONTROL_AMMESSI:
            return "mode"
        return None

    def set_control(self, event_id: str, **fields: Any) -> None:
        from .. import scalper_session as SS

        fields["updated_at"] = SS._now_iso()
        campi = json.loads(json.dumps(fields, default=str))
        rifiuto = self._viola_check(campi)
        self.scritture.append({"ms": self.orologio.ora_ms(), "campi": campi,
                               "rifiutata": rifiuto})
        if rifiuto:
            logger.warning("[replay-scalper] scrittura rifiutata dal CHECK (%s)", rifiuto)
            return
        self.control.update(campi)
        st = campi.get("status")
        if st and st not in self.stati_visti:
            self.stati_visti.append(str(st))

    def control_status(self, event_id: str) -> Optional[str]:
        return self.control.get("status")

    def get_control(self, event_id: str) -> Optional[Dict[str, Any]]:
        return json.loads(json.dumps(self.control, default=str))

    def follow(self, event_id: str) -> Optional[Dict[str, Any]]:
        return dict(self.follow_row)

    def prediction(self, fixture_id: Optional[int]) -> Optional[Dict[str, Any]]:
        return None

    def log(self, event_id: str, kind: str, payload: Dict[str, Any]) -> None:
        self.tabelle.setdefault("scalper_activity", []).append({
            "event_id": event_id, "kind": kind,
            "payload": json.loads(json.dumps(payload, default=str)),
            "_ms": self.orologio.ora_ms()})

    def log_many(self, rows: List[Dict[str, Any]]) -> None:
        for r in rows or []:
            r = json.loads(json.dumps(r, default=str))
            r["_ms"] = self.orologio.ora_ms()
            self.tabelle.setdefault("scalper_activity", []).append(r)

    # --- letture per il referto
    def attivita(self, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        righe = self.tabelle.get("scalper_activity", [])
        return [r for r in righe if kind is None or r.get("kind") == kind]

    def messaggi(self) -> List[str]:
        return [str((r.get("payload") or {}).get("msg") or "")
                for r in self.attivita()]


# ---------------------------------------------------------------------------
# Betfair finto: SOLO il catalogo; ogni altra chiamata si registra
# ---------------------------------------------------------------------------
class _BettingFinto:
    def __init__(self, banco: "_Banco") -> None:
        self._banco = banco
        self.chiamate: List[Tuple[str, Dict[str, Any]]] = []

    def list_market_catalogue(self, filter: Any = None, market_projection: Any = None,
                              sort: Any = None, max_results: Any = None, **_k: Any) -> List[Any]:
        tipi = set((filter or {}).get("marketTypeCodes") or [])
        out = [m for m in self._banco.catalogo if not tipi or m.market_type in tipi]
        out = out[: int(max_results or len(out) or 1)]
        self.chiamate.append(("list_market_catalogue", {"tipi": sorted(tipi),
                                                        "n": len(out)}))
        self._banco.mercati_catalogo = [m.market_id for m in out]
        return out

    def list_market_book(self, market_ids: Any = None, **_k: Any) -> List[Any]:
        self.chiamate.append(("list_market_book", {"market_ids": market_ids}))
        return []

    def _vivi(self, market_id: str) -> List[Any]:
        m = self._banco.quadro.markets.markets.get(str(market_id))
        if m is None:
            return []
        return [o for o in list(m.blotter)
                if getattr(o, "bet_id", None) and CERT._vivo(CERT.riga_ordine(o))]

    def list_current_orders(self, market_ids: Any = None, **_k: Any) -> Any:
        """Gli ordini NON abbinati del conto su quei mercati, come li darebbe
        Betfair (`bet_id` e basta: e' l'unica chiave che `_sweep_cancel` legge)."""
        self.chiamate.append(("list_current_orders", {"market_ids": market_ids}))
        righe = [SimpleNamespace(bet_id=str(o.bet_id))
                 for mid in (market_ids or []) for o in self._vivi(mid)]
        return SimpleNamespace(orders=righe, current_orders=righe)

    def cancel_orders(self, market_id: Any = None, instructions: Any = None, **_k: Any) -> Any:
        """Lo SWEEP REST del crash (`scalper_session._sweep_cancel`): Betfair
        cancella il residuo non abbinato dei bet indicati. Nel simulato si usa
        lo stesso campo con cui il banco comune fa scadere un ordine
        (`SimulatedOrder`: qui `size_cancelled`), cosi' `size_remaining` va a
        zero; senza istruzioni e' market-wide, come su Betfair."""
        self.chiamate.append(("cancel_orders", {"market_id": market_id,
                                                "instructions": instructions}))
        voluti = None
        if instructions:
            voluti = {str(i.get("betId")) for i in instructions if isinstance(i, dict)}
        for o in self._vivi(str(market_id)):
            if voluti is not None and str(o.bet_id) not in voluti:
                continue
            sim = getattr(o, "simulated", None)
            if sim is not None:
                sim.size_cancelled += float(getattr(o, "size_remaining", 0.0) or 0.0)
        return None


class _TradingFinto:
    def __init__(self, banco: "_Banco") -> None:
        self.betting = _BettingFinto(banco)

    def keep_alive(self) -> None:
        return None


class _ClientChiesto:
    """Cio' che la sessione chiede a `clients.BetfairClient(trading, **kw)`: si
    registra (parita' paper/live, S6) e NON diventa mai un client vero."""

    def __init__(self, trading: Any, **kwargs: Any) -> None:
        self.trading = trading
        self.kwargs = dict(kwargs)


# ---------------------------------------------------------------------------
# il FRAMEWORK della sessione: un involucro sul quadro del banco
# ---------------------------------------------------------------------------
class _CodaTerminazione:
    """`framework.handler_queue` visto dalla sessione: la sola cosa che la
    sessione ci mette e' il `TerminationEvent` che ferma flumine."""

    def __init__(self, fw: "_FrameworkSessione") -> None:
        self._fw = fw

    def put(self, evento: Any) -> None:
        self._fw.termina(type(evento).__name__)


class _FrameworkSessione:
    def __init__(self, banco: "_Banco", client: Any) -> None:
        self.__dict__["_banco"] = banco
        self.__dict__["client_chiesto"] = getattr(client, "kwargs", {})
        self.__dict__["handler_queue"] = _CodaTerminazione(self)
        self.__dict__["_running"] = False
        self.__dict__["strategie"] = []
        self.__dict__["_fine"] = threading.Event()
        self.__dict__["causa_fine"] = None
        self.__dict__["_simulated_execution"] = None

    # il quadro del banco E' il mercato: markets, clients, log_control...
    def __getattr__(self, nome: str) -> Any:
        return getattr(self.__dict__["_banco"].quadro, nome)

    @property
    def simulated_execution(self) -> Any:
        return (self.__dict__["_simulated_execution"]
                or self.__dict__["_banco"].quadro.simulated_execution)

    @simulated_execution.setter
    def simulated_execution(self, v: Any) -> None:
        self.__dict__["_simulated_execution"] = v

    def __setattr__(self, nome: str, valore: Any) -> None:
        if nome == "simulated_execution":
            self.__dict__["_simulated_execution"] = valore
            return
        self.__dict__[nome] = valore

    def add_strategy(self, strategia: Any) -> None:
        self.__dict__["_banco"].aggiungi_strategia(self, strategia)

    def run(self) -> None:
        banco = self.__dict__["_banco"]
        self.__dict__["_running"] = True
        banco.avvia_motore()
        while not self.__dict__["_fine"].is_set() and not banco.motore_finito.is_set():
            self.__dict__["_fine"].wait(0.2)

    def termina(self, causa: str) -> None:
        self.__dict__["_running"] = False
        self.__dict__["causa_fine"] = causa
        self.__dict__["_fine"].set()
        self.__dict__["_banco"].sessione_finita(self)


class _ArmamentoCatturato(BaseException):
    """Ferma `run_session` appena la strategia e' armata (solo per la parita')."""

    def __init__(self, strategia: Any, client: Dict[str, Any]) -> None:
        super().__init__("armamento catturato")
        self.strategia = strategia
        self.client = client


# ---------------------------------------------------------------------------
# IL GUASTI iniettati (scenari)
# ---------------------------------------------------------------------------
def _controllo_rifiuti(quadro: Any, quanti: int):
    """Un trading control di flumine che RIFIUTA i primi `quanti` piazzamenti.
    Via di produzione del rifiuto: `_on_error` -> `order.violation(...)`,
    `place_order` torna False (`flumine/execution/transaction.py:67-72`)."""
    from flumine.controls import BaseControl
    from flumine.order.orderpackage import OrderPackageType

    class _Rifiuta(BaseControl):
        NAME = "REPLAY_RIFIUTA_PRIMI"

        def __init__(self, flumine: Any) -> None:
            super().__init__(flumine)
            self.rifiutati: List[str] = []
            # gli OGGETTI rifiutati: dal 24/09 il bot li lascia cadere (legge il
            # False di place_order) e il blotter non li ha mai avuti; K2 li
            # deve vedere lo stesso per giudicare se il bot ci crede ancora
            self.ordini: List[Any] = []

        def _validate(self, order: Any, package_type: Any) -> None:
            if package_type != OrderPackageType.PLACE or len(self.rifiutati) >= quanti:
                return
            self.rifiutati.append(str(getattr(order, "id", "") or ""))
            self.ordini.append(order)
            self._on_error(order, "rifiuto iniettato dal replay")

    return _Rifiuta(quadro)


def _ritarda_esiti(quadro: Any, quanti: int, secondi: float) -> Dict[str, Any]:
    """I primi `quanti` pacchetti PLACE restano senza esito per `secondi` di
    mercato: flumine li esegue solo quando il tempo supera il loro
    `simulated_delay`, cosi' l'ordine resta PENDING e senza bet_id."""
    from flumine.order.orderpackage import OrderPackageType

    stato = {"ritardati": 0}
    originale = quadro.process_order_package

    def _process(pacco: Any) -> None:
        if (getattr(pacco, "package_type", None) == OrderPackageType.PLACE
                and stato["ritardati"] < quanti):
            pacco.simulated_delay = float(pacco.simulated_delay) + float(secondi)
            stato["ritardati"] += 1
        return originale(pacco)

    quadro.process_order_package = _process
    return stato


# ---------------------------------------------------------------------------
# GLI OSSERVATORI: guardano, non decidono
# ---------------------------------------------------------------------------
def installa_osservatori(s: Any, attivita: List[Tuple[str, Dict[str, Any], int]],
                         chiusure: List[Dict[str, Any]],
                         ora_ms: Callable[[], int]) -> None:
    """Due osservatori in SOLA LETTURA sulla strategia di produzione.

    * TEE dell'`event_sink` (e' il punto d'iniezione della telemetria che il
      bot stesso dichiara: 'callable(kind, payload), mai dalla logica'): ogni
      attivita' arriva ANCHE al referto, il sink vero resta collegato;
    * alla chiusura di ogni ciclo (`_on_cycle_closed`, l'unico punto in cui il
      bot contabilizza un `locked`) si fotografano gli ordini dello slot e si
      calcola QUI il worst-case vero dagli abbinati (K7). Poi si chiama il vero.
    """
    vero = getattr(s, "event_sink", None)

    def _tee(kind: str, payload: Dict[str, Any]) -> None:
        attivita.append((str(kind), dict(payload or {}), ora_ms()))
        if vero is not None:
            vero(kind, payload)

    s.event_sink = _tee
    chiudi_vero = s._on_cycle_closed

    def _osserva(slot: Any, locked: float, kind: str = "cycle",
                 now: Optional[int] = None) -> None:
        ordini = [slot.entry, slot.entry_back, slot.entry_lay, slot.close,
                  slot.next_entry] + list(slot.flatten_orders or [])
        chiave = next((k for k, v in s._slots.items() if v is slot), None)
        chiusure.append({
            "chiave": chiave, "kind": kind, "locked": float(locked),
            "worst_case_vero": CERT.worst_case_vero(ordini), "ms": ora_ms()})
        return chiudi_vero(slot, locked, kind=kind, now=now)

    s._on_cycle_closed = _osserva


# ---------------------------------------------------------------------------
# IL BANCO: quadro, motore, ponte, sessioni
# ---------------------------------------------------------------------------
class _Banco:
    def __init__(self, *, event_id: str, raw: str, scenario: str, ogni_ms: int,
                 referto: CERT.Referto, orologio: _Orologio, db: _DbFinto,
                 catalogo: List[Any], ko_ms: Optional[int]) -> None:
        from ...backtest import banco_comune as BC
        from flumine import FlumineSimulation

        self.BC = BC
        self.event_id = str(event_id)
        self.raw = raw
        self.scenario = scenario
        self.cadenza_ms = int(ogni_ms) if ogni_ms else 1000
        self.ref = referto
        self.orologio = orologio
        self.db = db
        self.catalogo = catalogo
        self.ko_ms = ko_ms
        self.mercati_catalogo: List[str] = []
        self.quadro = FlumineSimulation(client=BC.cliente_simulato())
        BC.assicura_middleware_simulato(self.quadro)
        self.motore = BC.MotoreReplay(self.quadro)
        self.motore_finito = threading.Event()
        self._thread_motore: Optional[threading.Thread] = None
        self.errore_motore: Optional[BaseException] = None
        self.ferma = False
        # sessioni: (framework, strategia, mercati)
        self.sessioni: List[Tuple[_FrameworkSessione, Any, Tuple[str, ...]]] = []
        self.sessioni_morte: List[Tuple[_FrameworkSessione, Any]] = []
        self._stream_ids: set = set()
        self.specchi: List[Any] = []
        self.righe_specchio: List[Dict[str, Any]] = []
        self._specchio_da = 0
        self.attivita: List[Tuple[str, Dict[str, Any], int]] = []
        self._attivita_da = 0
        self.chiusure: List[Dict[str, Any]] = []
        self._chiusure_da = 0
        self._scritture_da = 0
        self._ultimo_giro_ms = 0
        self._ultimo_specchio_ms = 0
        self.ordini_visti: set = set()
        self.ingressi_ms: Dict[str, int] = {}
        self.force_flat_ms: Optional[int] = None
        self.missione_ms: Optional[int] = None
        self.in_gioco_ms: Dict[str, int] = {}
        self.stati_visti: List[str] = []
        self.fasi_viste: List[str] = []
        self.memoria = CERT.Memoria()
        # scenario: quando e perche' lo stop
        self.stop_ms: Optional[int] = None
        self.stop_causa = ""
        self.evento_ms: Optional[int] = None
        self.evento_fatto = False
        self.kill_file: Optional[str] = None
        self.sorveglianza_cp: Optional[Any] = None
        self.parita: Optional[Dict[str, Any]] = None
        self._parita_consegnata = False
        self.riavviata = False
        self.orfani_attivi = False
        self.primo_ms: Optional[int] = None
        self.errori_ponte: List[str] = []
        self.ultima_strategia: Any = None
        self.framework_creati: List[_FrameworkSessione] = []
        # il trading control dello scenario 'rifiuti-betfair' (None altrove)
        self.rifiuti: Any = None

    # ------------------------------------------------------------ sessioni
    def strategia_corrente(self) -> Any:
        """La strategia della sessione viva; a sessione chiusa, l'ULTIMA armata
        (serve al giro finale S3/S4, che giudica cio' che ha lasciato)."""
        if self.sessioni:
            return self.sessioni[-1][1]
        return getattr(self, "ultima_strategia", None)

    def aggiungi_strategia(self, fw: _FrameworkSessione, s: Any) -> None:
        # la registrazione al posto dello stream (come il replay tennis)
        s.market_filter = {"markets": [self.raw]}
        installa_osservatori(s, self.attivita, self.chiusure, self.orologio.ora_ms)
        self.quadro.add_strategy(s)
        self._stream_ids |= set(getattr(s, "stream_ids", set()) or set())
        fw.strategie.append(s)
        self.sessioni.append((fw, s, tuple(self.mercati_catalogo)))
        self.ultima_strategia = s

    def sessione_finita(self, fw: _FrameworkSessione) -> None:
        self.sessioni = [x for x in self.sessioni if x[0] is not fw]

    def uccidi_sessione(self, fw: _FrameworkSessione) -> None:
        """Il processo e' morto: flumine non chiama piu' la strategia. Gli
        ordini restano sul mercato (in LIVE restano sull'exchange)."""
        for x in list(self.sessioni):
            if x[0] is fw:
                self.sessioni_morte.append((fw, x[1]))
        self.sessioni = [x for x in self.sessioni if x[0] is not fw]
        fw.__dict__["_running"] = False
        fw.__dict__["causa_fine"] = "processo ucciso"
        fw.__dict__["_fine"].set()

    def registra_specchio(self, mirror: Any) -> None:
        self.specchi.append(mirror)

    # ------------------------------------------------------------ motore
    def avvia_motore(self) -> None:
        if self._thread_motore is not None:
            return
        self._thread_motore = threading.Thread(target=self._gira, daemon=True,
                                               name="replay-scalper-motore")
        self._thread_motore.start()

    def _gira(self) -> None:
        try:
            self.motore.esegui(_Ponte(self))
        except BaseException as ex:  # noqa: BLE001 - un motore che muore E' un referto
            self.errore_motore = ex
        finally:
            self.orologio.fine_motore()
            self.motore_finito.set()

    def ferma_motore(self) -> None:
        self.ferma = True
        self.orologio.libera()
        if self._thread_motore is not None:
            self._thread_motore.join(timeout=ATTESA_MASSIMA_REALE_S)

    # ------------------------------------------------------------ ordini
    def _mercati_sessione(self) -> Tuple[str, ...]:
        if self.sessioni:
            return self.sessioni[-1][2]
        return tuple(self.mercati_catalogo)

    def ordini_di(self, strategie: List[Any]) -> List[Any]:
        out: List[Any] = []
        for mid in self._mercati_sessione():
            m = self.quadro.markets.markets.get(mid)
            if m is None:
                continue
            for s in strategie:
                try:
                    out.extend(list(m.blotter.strategy_orders(s) or []))
                except Exception:  # noqa: BLE001 - blotter illeggibile: nessun ordine
                    continue
        return out

    def righe_correnti(self, s: Any, cred: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        a_mercato = self.ordini_di([s]) if s is not None else []
        ids = {str(getattr(o, "id", "")) for o in a_mercato}
        righe = [CERT.riga_ordine(o, True) for o in a_mercato]
        # gli ordini che il bot tiene in mano e che il mercato NON conosce
        # (rifiutati, mai partiti): e' la parte di verita' che il blotter non ha
        for c in cred:
            for o in CERT.ordini_seguiti(c):
                oid = str(getattr(o, "id", ""))
                if oid and oid not in ids:
                    ids.add(oid)
                    righe.append(CERT.riga_ordine(o, False))
        # i rifiuti iniettati dallo scenario, anche quelli che il bot NON segue
        # piu' (e' la verita' del mercato: K2 li giudica contro le credenze)
        for o in list(getattr(self.rifiuti, "ordini", None) or []):
            oid = str(getattr(o, "id", ""))
            if oid and oid not in ids:
                ids.add(oid)
                righe.append(CERT.riga_ordine(o, False))
        return righe

    @staticmethod
    def esposizioni(righe: List[Dict[str, Any]]) -> Dict[Tuple[str, int], Tuple[float, float]]:
        per: Dict[Tuple[str, int], List[Dict[str, Any]]] = {}
        for r in righe:
            if not r.get("in_blotter"):
                continue
            try:
                k = (str(r.get("market_id") or ""), int(r.get("selection_id") or 0))
            except (TypeError, ValueError):
                continue
            per.setdefault(k, []).append(r)
        return {k: CERT.esposizione(v) for k, v in per.items()}

    # ------------------------------------------------------------ specchio
    def gira_specchio(self, ms: int) -> None:
        if not self.specchi or ms - self._ultimo_specchio_ms < 1000:
            return
        self._ultimo_specchio_ms = ms
        mirror = self.specchi[-1]
        for mid in self._mercati_sessione():
            m = self.quadro.markets.markets.get(mid)
            if m is None:
                continue
            ordini = list(m.blotter)
            if ordini:
                mirror.process_orders(m, ordini)

    # ------------------------------------------------------------ il giro
    def divieti(self, ms: int) -> Dict[str, int]:
        d: Dict[str, int] = {}
        s = self.strategia_corrente()
        if self.force_flat_ms is not None:
            d["force_flat"] = self.force_flat_ms
        if self.missione_ms is not None:
            d["missione_prematch"] = self.missione_ms
        if s is not None and self.ko_ms is not None:
            esb = float(getattr(s, "entry_stop_before_s", 0.0) or 0.0)
            if esb > 0 and ms >= self.ko_ms - int(esb * 1000):
                d["entry_stop_before_s"] = self.ko_ms - int(esb * 1000)
        if s is not None and not getattr(s, "allow_inplay", False):
            for mid, t in self.in_gioco_ms.items():
                d["in_gioco@%s" % mid] = t
        return d

    def osservazione(self, ms: int, quando: str, *, fine: bool = False,
                     stato_mercato: str = "OPEN") -> CERT.Osservazione:
        s = self.strategia_corrente()
        cred = CERT.credenze(s) if s is not None else []
        righe = self.righe_correnti(s, cred)
        tutti = {r.get("order_id") for r in righe}
        nuovi = tutti - self.ordini_visti
        self.ordini_visti |= tutti
        ids_ingresso: set = set()
        for c in cred:
            ids_ingresso |= CERT._ids(c.get("ingressi") or ())
        for r in righe:
            oid = r.get("order_id")
            if oid in ids_ingresso and oid not in self.ingressi_ms:
                self.ingressi_ms[oid] = int(r.get("creato_ms") or ms)
        ora_fa = ms - 3600 * 1000
        # il ritmo delle transazioni conta i PIAZZAMENTI d'ingresso fatti
        ingressi_ora = sum(1 for t in self.ingressi_ms.values() if t >= ora_fa)
        att = [(k, p) for k, p, _t in self.attivita[self._attivita_da:]]
        self._attivita_da = len(self.attivita)
        chiusure = self.chiusure[self._chiusure_da:]
        self._chiusure_da = len(self.chiusure)
        scritture = self.db.scritture[self._scritture_da:]
        self._scritture_da = len(self.db.scritture)
        specchio = self.righe_specchio[self._specchio_da:]
        self._specchio_da = len(self.righe_specchio)
        # il giro NORMALE della sessione CORRENTE: dall'ultimo 'running' allo
        # stop (dopo lo stop il servizio aspetta il flat senza battere)
        running = None
        for w in self.db.scritture:
            if (w.get("campi") or {}).get("status") == "running":
                running = w["ms"]
        battiti = [w["ms"] for w in self.db.scritture
                   if "heartbeat_at" in (w.get("campi") or {})
                   and running is not None and w["ms"] >= running
                   and (self.stop_ms is None or w["ms"] <= self.stop_ms)]
        orfani = None
        if self.orfani_attivi and self.sessioni_morte:
            morti = self.ordini_di([x[1] for x in self.sessioni_morte])
            orfani = [CERT.riga_ordine(o) for o in morti
                      if float(getattr(o, "size_matched", 0.0) or 0.0) > 0.009
                      or CERT._vivo(CERT.riga_ordine(o))]
        parita = None
        if self.parita is not None and not self._parita_consegnata:
            parita = self.parita
            self._parita_consegnata = True
        oss = CERT.Osservazione(
            scenario=self.scenario, quando=quando, ms=ms,
            modalita="paper" if bool(self.db.control.get("dry_run")) else "live",
            inplay=bool(self.in_gioco_ms), stato_mercato=stato_mercato,
            ko_ms=self.ko_ms,
            stake=float(self.db.control.get("stake") or 0.0),
            cap_esposizione=getattr(s, "max_selection_exposure", None) if s is not None else None,
            divieti=self.divieti(ms), ordini=righe, credenze=cred,
            ordini_nuovi=nuovi, attivita=att,
            stats=dict((self.db.control.get("stats") or {})),
            specchio=specchio, esposizioni=self.esposizioni(righe),
            max_txn_hour=int(getattr(s, "max_txn_hour", 0) or 0) if s is not None else 0,
            ingressi_ultima_ora=ingressi_ora, chiusure_ciclo=chiusure,
            scritture_control=scritture,
            stop_richiesto_ms=self.stop_ms, stop_causa=self.stop_causa,
            force_flat=bool(getattr(s, "force_flat", False)) if s is not None else False,
            force_flat_ms=self.force_flat_ms,
            sessione_viva=bool(self.sessioni) and not fine,
            stato_finale=self.db.control.get("status") if fine else None,
            fine_sessione=fine,
            # il servizio DICHIARA una posizione non piatta in due modi: il log
            # 'posizione NON flat dopo 30s' e l'allarme CRITICAL del crash
            # ('VERIFICA il matched residuo sul conto')
            dichiarato_non_flat=fine and (
                any(CERT.messaggio_dichiara_non_flat(m)
                    for m in self.db.messaggi())
                or any(str(a.get("code") or "") == "SCALPER_CRASH"
                       for a in self.db.tabelle.get("live_alerts", []))),
            heartbeat_ms=battiti, running_da_ms=running,
            buchi_registrazione_ms=self.orologio.buchi(),
            parita=parita, orfani_dopo_riavvio=orfani,
            allarmi=list(self.db.tabelle.get("live_alerts", [])),
        )
        # stati e fasi visti (referto par.6.8)
        for c in cred:
            st = "slot:%s" % c.get("stato")
            if st not in self.stati_visti:
                self.stati_visti.append(st)
        for st in self.db.stati_visti:
            k = "sessione:%s" % st
            if k not in self.stati_visti:
                self.stati_visti.append(k)
        fase = ("fine-sessione" if fine else "in-gioco" if self.in_gioco_ms
                else "finestra-flatten" if (s is not None and self.ko_ms is not None
                                            and ms >= self.ko_ms - int(float(getattr(s, "flatten_before_s", 0) or 0) * 1000))
                else "stop-ingressi" if "entry_stop_before_s" in oss.divieti
                else "pre-match")
        if fase not in self.fasi_viste:
            self.fasi_viste.append(fase)
        return oss

    def giro(self, ms: int, quando: str, *, fine: bool = False) -> None:
        if not self.sessioni and not fine:
            return
        oss = self.osservazione(ms, quando, fine=fine)
        self.ref.violazioni.extend(CERT.verifica(oss, self.ref.sollecitati, self.memoria))
        if self.sorveglianza_cp is not None:
            for cod, reg, det in self.sorveglianza_cp.verifica(
                    credenze_cp(oss.credenze, self.strategia_corrente(), self),
                    self.ref.sollecitati):
                self.ref.violazioni.append(CERT.Violazione(cod, reg, det, quando))


def credenze_cp(cred: List[Dict[str, Any]], s: Any, banco: _Banco) -> List[Dict[str, Any]]:
    """Le credenze dello scalper nella forma dei controlli CP (come
    `tennis_live/tools/replay_bot.credenze_cp`): una voce per slot, CHIUSA =
    IDLE/DONE, le chiusure con i numeri VERI dell'ordine (chiavi dello specchio
    di produzione)."""
    def _riga(o: Any) -> Dict[str, Any]:
        r = CERT.riga_ordine(o)
        return {"ordine_id": r["order_id"], "bet_id": r["bet_id"], "size": r["size"],
                "price": r["price"], "status": r["status"],
                "size_matched": r["size_matched"], "size_remaining": r["size_remaining"],
                "avg_price_matched": r["average_price_matched"]}

    out: List[Dict[str, Any]] = []
    for c in cred:
        out.append({
            "id": "%s%s" % (c.get("stato"), c.get("chiave")),
            "chiave": tuple(c.get("chiave") or ()),
            "chiusa": str(c.get("stato") or "") in CERT.STATI_SLOT_CHIUSI,
            "coperto": None, "apertura": None, "ingressi": [],
            "chiusure": [_riga(o) for o in (c.get("uscite") or ())],
            "per_selezione": True,
            "tolleranza": float(c.get("tolleranza") or 0.0),
        })
    return out


class _Ponte:
    """Sta fra `MotoreReplay` e la strategia della sessione, e non decide niente.

    Fa quello che in produzione fa il framework flumine della sessione: passa a
    `ScalperStrategy` i book dei SOLI mercati a cui la sessione si e' abbonata
    (quelli del catalogo), a ogni aggiornamento dello stream. In piu' fa
    scorrere l'orologio (turno con la sessione), fa girare lo specchio alla sua
    cadenza e i controlli alla loro.
    """

    def __init__(self, banco: _Banco) -> None:
        self.b = banco

    @property
    def stream_ids(self) -> Any:
        return self.b._stream_ids

    def process_new_market(self, market: Any, market_book: Any) -> None:
        from flumine import utils as futils

        for _fw, s, mids in list(self.b.sessioni):
            if market.market_id in mids:
                futils.call_strategy_error_handling(s.process_new_market, market, market_book)

    def check_market_book(self, market: Any, market_book: Any) -> bool:
        b = self.b
        ms = int(getattr(market_book, "publish_time_epoch", 0) or 0)
        if b.primo_ms is None:
            b.primo_ms = ms
        b.ref.tick += 1
        b.orologio.al_book(ms / 1000.0)
        if b.ferma:
            b.motore._gen = iter(())
            b.motore._coda.clear()
            return False
        try:
            self._giro_del_book(market, market_book, b.orologio.ora_ms())
        except Exception as ex:  # noqa: BLE001 - flumine lo inghiottirebbe: si CONTA
            import traceback

            b.errori_ponte.append("%s: %s @ %s" % (
                type(ex).__name__, ex,
                traceback.extract_tb(ex.__traceback__)[-1][:2] if ex.__traceback__ else "?"))
        return False

    def _giro_del_book(self, market: Any, market_book: Any, ms: int) -> None:
        from flumine import utils as futils

        b = self.b
        # FINE VITA della sessione maker: KO + 10' (`run_session`, `_life_s`
        # = 600 senza ht/sniper/theta; docstring del modulo: 'o KO+10''). E'
        # il confine che S2 usa per misurare quanto ci mette il force-flat.
        if b.stop_ms is None and b.ko_ms is not None and ms >= b.ko_ms + 600 * 1000 \
                and b.sessioni:
            b.stop_ms, b.stop_causa = b.ko_ms + 600 * 1000, "fine-vita"
        b.evento_scenario(ms)
        mid = str(market.market_id)
        if bool(getattr(market_book, "inplay", False)) and mid not in b.in_gioco_ms \
                and mid in b._mercati_sessione():
            b.in_gioco_ms[mid] = ms
        for _fw, s, mids in list(b.sessioni):
            if mid not in mids:
                continue
            if s.force_flat and b.force_flat_ms is None:
                b.force_flat_ms = ms
            prima = len(b.attivita)
            if futils.call_strategy_error_handling(s.check_market_book, market, market_book):
                futils.call_strategy_error_handling(s.process_market_book, market, market_book)
                b.ref.decisioni += 1
            b.ref.azioni += len(b.attivita) - prima
            st = getattr(s, "stats", {}) or {}
            if (b.missione_ms is None and getattr(s, "one_green_per_phase", False)
                    and not b.in_gioco_ms and float(st.get("greens_prematch", 0) or 0) >= 1):
                b.missione_ms = ms
        if b.sessioni:
            b.gira_specchio(ms)
        if ms - b._ultimo_giro_ms >= b.cadenza_ms:
            b._ultimo_giro_ms = ms
            pt = getattr(market_book, "publish_time", None)
            b.giro(ms, pt.isoformat() if pt is not None else str(ms))


# ---------------------------------------------------------------------------
# gli eventi degli scenari (nel thread del motore, a tempo di mercato)
# ---------------------------------------------------------------------------
def _posizione_aperta(s: Any) -> bool:
    for slot in dict(getattr(s, "_slots", {}) or {}).values():
        if slot.status in CERT.STATI_SLOT_VIVI:
            for o in (slot.entry, slot.entry_back, slot.entry_lay):
                if o is not None and float(getattr(o, "size_matched", 0.0) or 0.0) > 0:
                    return True
    return False


def _evento_scenario(self: _Banco, ms: int) -> None:
    """Stop da UI / kill-switch / morte del processo: a meta' della finestra
    pre-match (dal primo book a KO - entry_stop_before_s), appena il bot ha una
    posizione abbinata aperta, e comunque entro il primo quarto della seconda
    meta' della finestra: il caso va PROVOCATO, non sperato."""
    if self.evento_fatto or self.scenario not in ("bot-fermo", "kill-switch", "riavvio"):
        return
    s = self.strategia_corrente()
    if s is None or self.ko_ms is None or self.primo_ms is None:
        return
    if self.evento_ms is None:
        fine = self.ko_ms - int(float(getattr(s, "entry_stop_before_s", 420.0) or 0) * 1000)
        meta = self.primo_ms + (fine - self.primo_ms) // 2
        self.evento_ms = meta
        self._evento_ultimo = meta + (fine - meta) // 4
    if ms < self.evento_ms:
        return
    if not _posizione_aperta(s) and ms < self._evento_ultimo:
        return
    self.evento_fatto = True
    aperta = _posizione_aperta(s)
    if self.scenario == "bot-fermo":
        # `scalper_stop`: running/arming/armed -> 'stopping'
        if self.db.control.get("status") in ("running", "arming", "armed"):
            self.db.control["status"] = "stopping"
        self.stop_ms, self.stop_causa = ms, "ui"
        self.ref.note.append("STOP dalla UI a %d ms (posizione abbinata aperta: %s)"
                             % (ms, "si'" if aperta else "no"))
    elif self.scenario == "kill-switch":
        with io.open(self.kill_file, "w", encoding="utf-8") as fh:
            fh.write("stop\n")
        self.stop_ms, self.stop_causa = ms, "kill-switch"
        self.ref.note.append("KILL-SWITCH (file nella cartella del replay) a %d ms "
                             "(posizione abbinata aperta: %s)" % (ms, "si'" if aperta else "no"))
    elif self.scenario == "riavvio":
        self.orologio.uccidi_al_prossimo_sonno(_ProcessoUcciso("processo della sessione ucciso"))
        self.ref.note.append("PROCESSO della sessione ucciso a %d ms (posizione "
                             "abbinata aperta: %s)" % (ms, "si'" if aperta else "no"))


_Banco.evento_scenario = _evento_scenario


# ---------------------------------------------------------------------------
# le INIEZIONI, tutte in un posto e tutte rimesse a posto
# ---------------------------------------------------------------------------
def _patch(stack: ExitStack, oggetto: Any, nome: str, valore: Any) -> None:
    vecchio = getattr(oggetto, nome)
    setattr(oggetto, nome, valore)
    stack.callback(setattr, oggetto, nome, vecchio)


@contextmanager
def _iniezioni(banco: _Banco, orologio: _Orologio, kill_file: str):
    import flumine
    import flumine.clients as fclients

    import db_client

    from ... import auth as AUTH
    from ... import db as STREAM_DB
    from .. import scalper_session as SS

    trading = _TradingFinto(banco)
    banco.trading = trading

    def _niente_db(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("REPLAY: accesso al DB VERO vietato (get_supabase_client)")

    def _flumine(client: Any = None, **_k: Any) -> _FrameworkSessione:
        fw = _FrameworkSessione(banco, client)
        banco.framework_creati.append(fw)
        return fw

    def _cattura_ordine(row: Dict[str, Any]) -> None:
        r = dict(row)
        r["_ms"] = orologio.ora_ms()
        banco.righe_specchio.append(r)

    with ExitStack() as st:
        _patch(st, SS, "Db", lambda: banco.db)
        _patch(st, SS, "time", _TempoSessione(orologio))
        _patch(st, SS, "KILL_FILE", kill_file)
        _patch(st, SS, "_order_mirror_loop",
               lambda mirror, framework, stop_flag, tick_s=1.0: banco.registra_specchio(mirror))
        _patch(st, AUTH, "build_client", lambda login=True: trading)
        _patch(st, AUTH, "keep_alive", lambda client: None)
        _patch(st, flumine, "Flumine", _flumine)
        _patch(st, fclients, "BetfairClient", _ClientChiesto)
        _patch(st, db_client, "get_supabase_client", _niente_db)
        _patch(st, STREAM_DB, "upsert_live_order", _cattura_ordine)
        _patch(st, STREAM_DB, "upsert_live_position", lambda row: None)
        _patch(st, STREAM_DB, "upsert_live_settled", lambda row: None)
        _patch(st, STREAM_DB, "find_live_order_ref", lambda mode, bet_id: None)
        _patch(st, _time_mod, "time", orologio.time)
        yield


# ---------------------------------------------------------------------------
# la PARITA' paper/live (S6): la stessa sessione armata nelle due modalita'
# ---------------------------------------------------------------------------
_ESCLUSI_PARITA = {"event_sink", "risk_sem", "market_filter", "_slots",
                   "_settled_by_id", "_ko_ms", "cycle_log", "_txn_ts",
                   "_dry_seen", "stats", "streams", "historic_stream_ids",
                   "_invested", "_markets", "name", "context", "clients",
                   "runner_contexts", "_markets_cache"}


def _parametri(s: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in vars(s).items():
        if k in _ESCLUSI_PARITA:
            continue
        if isinstance(v, (bool, int, float, str, type(None))):
            out[k] = v
        elif isinstance(v, (set, frozenset)):
            out[k] = sorted(str(x) for x in v)
        elif isinstance(v, (list, tuple)):
            try:
                out[k] = json.loads(json.dumps(list(v), default=str))
            except (TypeError, ValueError):
                continue
        elif isinstance(v, dict):
            try:
                out[k] = json.loads(json.dumps(v, default=str, sort_keys=True))
            except (TypeError, ValueError):
                continue
    return out


def arma_e_cattura(event_id: str, control: Dict[str, Any], follow: Dict[str, Any],
                   catalogo: List[Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Fa girare `run_session` VERO fino all'armamento della strategia e la
    cattura (nessun thread parte, nessun book passa). Torna (parametri della
    strategia, kwargs del client chiesto)."""
    from ...backtest import banco_comune as BC
    from .. import scalper_session as SS

    orologio = _Orologio()
    db = _DbFinto(orologio, control, follow)
    ref = CERT.Referto(event_id=str(event_id))
    with BC.simulazione_flumine():
        banco = _Banco(event_id=event_id, raw="", scenario="parita", ogni_ms=0,
                       referto=ref, orologio=orologio, db=db, catalogo=catalogo,
                       ko_ms=None)
        banco.framework_creati = []

        def _cattura(fw: _FrameworkSessione, s: Any) -> None:
            raise _ArmamentoCatturato(s, dict(fw.client_chiesto))

        banco.aggiungi_strategia = _cattura  # type: ignore[assignment]
        tmp = tempfile.mkdtemp(prefix="replay_scalper_parita_")
        try:
            with _iniezioni(banco, orologio, os.path.join(tmp, "STOP_SCALPER")):
                try:
                    SS.run_session(str(event_id))
                except _ArmamentoCatturato as cat:
                    return _parametri(cat.strategia), cat.client
                except SystemExit:
                    pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    raise RuntimeError("la sessione non ha armato nessuna strategia: %s"
                       % db.control.get("error"))


def parita_paper_live(event_id: str, control: Dict[str, Any], follow: Dict[str, Any],
                      catalogo: List[Any]) -> Dict[str, Any]:
    try:
        cp = dict(control, dry_run=True)
        cl = dict(control, dry_run=False)
        par_p, cli_p = arma_e_cattura(event_id, cp, follow, catalogo)
        par_l, cli_l = arma_e_cattura(event_id, cl, follow, catalogo)
    except Exception as ex:  # noqa: BLE001 - una parita' non misurabile E' un referto
        return {"errore": "%s: %s" % (type(ex).__name__, ex)}
    diversi = sorted(k for k in set(par_p) | set(par_l) if par_p.get(k) != par_l.get(k))
    cli_div = sorted(k for k in set(cli_p) | set(cli_l)
                     if k != "paper_trade" and cli_p.get(k) != cli_l.get(k))
    return {"parametri_diversi": [(k, par_p.get(k), par_l.get(k)) for k in diversi],
            "client_diversi": cli_div,
            "paper_trade_paper": cli_p.get("paper_trade"),
            "paper_trade_live": cli_l.get("paper_trade"),
            "n_parametri": len(par_p), "client_paper": cli_p, "client_live": cli_l}


# ---------------------------------------------------------------------------
# IL REPLAY DI UN EVENTO
# ---------------------------------------------------------------------------
def certifica_scenario(event_id: str, *, data_dir: str, scenario: str = "base",
                       ogni_ms: int = 1000, campioni_diff: int = 0) -> CERT.Referto:
    """Un evento, uno scenario, un referto. E' il contratto del banco comune."""
    del campioni_diff          # lo scalper non passa dalla riga di scan
    from ...backtest import banco_comune as BC
    from .. import scalper_session as SS

    ref = CERT.Referto(event_id=str(event_id), scenario=scenario)
    raw = percorso_raw(data_dir, event_id)
    if not os.path.exists(raw):
        ref.note.append("registrazione assente: %s" % raw)
        return ref
    ref.note.append("qualita' registrazione: %s" % qualita_registrazione(data_dir, event_id))
    definizioni, ko_iso = leggi_definizioni(raw)
    catalogo = catalogo_dal_raw(definizioni)
    if not ko_iso:
        ref.note.append("nessun MATCH_ODDS nel raw: la sessione non ha un KO")
        return ref
    from datetime import datetime

    ko_ms = int(datetime.fromisoformat(str(ko_iso).replace("Z", "+00:00")).timestamp() * 1000)
    punteggi = BC.carica_punteggi(data_dir, str(event_id))
    casa, fuori = BC.nomi_dal_punteggio(punteggi)
    follow = {"event_id": str(event_id), "fixture_id": None, "league_id": None,
              "home_name": casa, "away_name": fuori, "open_date": ko_iso}
    control = control_della_ui(event_id, scenario)
    ref.note.append("control della UI: mode=%s dry_run=%s stake=%s params=%s"
                    % (control["mode"], control["dry_run"], control["stake"],
                       sorted(control["params"].items())))
    ref.note.append("limiti dichiarati: catalogo sintetizzato dai marketDefinition; "
                    "scanner non usato (lo scalper legge il book); orologio di "
                    "mercato per `time.time`; settlement non raggiunto (fine vita "
                    "KO+10'); sniper/theta fuori perimetro")

    orologio = _Orologio()
    primo = primo_publish_time_ms(raw)
    if primo is not None:
        # la sessione si arma all'inizio della registrazione, sull'orologio
        # del mercato (le scritture d'avvio portano quell'istante)
        orologio.ora_s = primo / 1000.0
    db = _DbFinto(orologio, control, follow)
    tmp = tempfile.mkdtemp(prefix="replay_scalper_")
    kill_file = os.path.join(tmp, "STOP_SCALPER")
    esiti: Dict[str, Any] = {}
    with BC.simulazione_flumine():
        banco = _Banco(event_id=event_id, raw=raw, scenario=scenario, ogni_ms=ogni_ms,
                       referto=ref, orologio=orologio, db=db, catalogo=catalogo,
                       ko_ms=ko_ms)
        banco.framework_creati = []
        banco.kill_file = kill_file
        if scenario in ("base", "paper"):
            banco.parita = parita_paper_live(event_id, control, follow, catalogo)
            p = banco.parita
            if not p.get("errore"):
                ref.note.append("parita' paper/live: %d parametri della strategia "
                                "confrontati, diversi %d; client paper %s / live %s"
                                % (p.get("n_parametri", 0), len(p.get("parametri_diversi") or []),
                                   p.get("client_paper"), p.get("client_live")))
        rifiuti = None
        ritardi = None
        if scenario == "rifiuti-betfair":
            rifiuti = _controllo_rifiuti(banco.quadro, PIAZZAMENTI_RIFIUTATI)
            banco.quadro.trading_controls.append(rifiuti)
            banco.rifiuti = rifiuti
        if scenario == "esiti-ignoti":
            ritardi = _ritarda_esiti(banco.quadro, PIAZZAMENTI_IGNOTI, RITARDO_ESITO_IGNOTO_S)
        guasto_cp = None
        if scenario == CP.SCENARIO:
            def _ruolo(ordine: Any) -> Optional[str]:
                for c in CERT.credenze(banco.strategia_corrente()):
                    if any(x is ordine for x in (c.get("uscite") or ())):
                        return "uscita"
                    if any(x is ordine for x in (c.get("ingressi") or ())):
                        return "ingresso"
                return None

            guasto_cp = CP.GuastoChiusuraParziale(ruolo=_ruolo)
            banco.motore.guasto_chiusure = guasto_cp
            banco.sorveglianza_cp = CP.Sorveglianza(guasto_cp)
        try:
            with _iniezioni(banco, orologio, kill_file):
                esiti["prima"] = _una_sessione(SS, event_id, banco)
                if scenario == "riavvio" and esiti["prima"] == "ucciso":
                    _riarma(SS, event_id, banco, esiti)
                # l'ULTIMO giro, a sessione chiusa (S3, S4)
                banco.giro(orologio.ora_ms(), "fine sessione", fine=True)
                banco.ferma_motore()
        finally:
            banco.ferma_motore()
            shutil.rmtree(tmp, ignore_errors=True)
        if banco.errore_motore is not None:
            ex = banco.errore_motore
            ref.note.append("replay fallito: %s: %s" % (type(ex).__name__, ex))
    _chiudi_referto(ref, banco, rifiuti, ritardi, guasto_cp, esiti)
    return ref


def _una_sessione(SS: Any, event_id: str, banco: _Banco) -> str:
    """`run_session` VERO nel thread di controllo. Torna come e' finita."""
    try:
        SS.run_session(str(event_id))
    except _ProcessoUcciso:
        fw = banco.sessioni[-1][0] if banco.sessioni else None
        if fw is not None:
            banco.uccidi_sessione(fw)
        return "ucciso"
    except SystemExit:
        banco.ref.note.append("la sessione e' uscita in errore: %s"
                              % (banco.db.control.get("error") or "?"))
        return "errore"
    return "finita"


def _riarma(SS: Any, event_id: str, banco: _Banco, esiti: Dict[str, Any]) -> None:
    """Dopo la morte del processo: il supervisore marca la riga ORFANA dopo
    `ORPHAN_HEARTBEAT_S` (`scalper_service.main`: 'running' senza figlio e
    heartbeat fermo -> 'error'), poi l'utente riarma (`scalper_activate`:
    status 'requested', stessi mode/dry_run/stake/params) e il supervisore
    lancia una sessione NUOVA."""
    from .. import scalper_service as SVC

    orologio = banco.orologio
    orologio.sleep(float(SVC.ORPHAN_HEARTBEAT_S))
    # la riga come la scrive il supervisore (`scalper_service.main`)
    banco.db.set_control(event_id, status="error",
                         error="sessione orfana (processo morto)",
                         stopped_at=SS._now_iso())
    orologio.sleep(ATTESA_RIARMO_S)
    # `scalper_activate` (RPC): la riga torna 'requested' e si azzera il resto
    banco.db.control.update({"status": "requested", "bias": None, "bias_meta": None,
                             "error": None, "started_at": None, "stopped_at": None})
    banco.riavviata = True
    banco.orfani_attivi = True
    banco.ref.note.append("sessione RIARMATA dopo %d s: parte un processo nuovo"
                          % int(float(SVC.ORPHAN_HEARTBEAT_S) + ATTESA_RIARMO_S))
    esiti["seconda"] = _una_sessione(SS, event_id, banco)


def _chiudi_referto(ref: CERT.Referto, banco: _Banco, rifiuti: Any, ritardi: Any,
                    guasto_cp: Any, esiti: Dict[str, Any]) -> None:
    db = banco.db
    msg = db.messaggi()
    if any("kickoff passato" in m for m in msg):
        causa = "fine-vita"
    elif banco.stop_causa:
        causa = banco.stop_causa
    elif any("CRASH" in m for m in msg):
        causa = "crash"
    else:
        causa = ""
    ref.note.append("sessioni: %s; stato finale '%s' (causa della fine: %s)"
                    % (esiti, db.control.get("status"), causa or "?"))
    tutte = [x[1] for x in banco.sessioni_morte]
    tutte += [s for fw in banco.framework_creati for s in fw.strategie]
    viste: List[Any] = []
    for s in tutte:
        if all(s is not v for v in viste):
            viste.append(s)
    ordini = banco.ordini_di(viste)
    ref.ordini_piazzati = len(ordini) + (len(rifiuti.rifiutati) if rifiuti else 0)
    ref.ordini_abbinati = sum(1 for o in ordini
                              if float(getattr(o, "size_matched", 0.0) or 0.0) > 0.009)
    ref.stati_visti = list(banco.stati_visti)
    ref.fasi_viste = list(banco.fasi_viste)
    for k, _p, _t in banco.attivita:
        ref.motivi[k] = ref.motivi.get(k, 0) + 1
    ref.stats_finali = dict(db.control.get("stats") or {})
    mot = banco.motore
    ref.note.append("book in ritardo: %d; lapse al fischio: %d; lapse alla "
                    "sospensione: %d; righe di specchio catturate: %d"
                    % (mot.book_in_ritardo, mot.lapse_al_fischio,
                       mot.lapse_alla_sospensione, len(banco.righe_specchio)))
    ref.note.append("fasi viste: %s" % ", ".join(banco.fasi_viste))
    mai = [s for s in sorted(CERT.STATI_SLOT) if "slot:%s" % s not in banco.stati_visti]
    if mai:
        ref.note.append("stati dello slot MAI visti: %s" % ", ".join(mai))
    if rifiuti is not None:
        ref.note.append("guasto: %d piazzamenti RIFIUTATI dal trading control"
                        % len(rifiuti.rifiutati))
    if ritardi is not None:
        ref.note.append("guasto: %d piazzamenti con esito IGNOTO per %d s"
                        % (ritardi["ritardati"], int(RITARDO_ESITO_IGNOTO_S)))
    if guasto_cp is not None:
        ref.note.append(guasto_cp.riepilogo())
    chiamate = [c for c, _ in getattr(banco, "trading").betting.chiamate
                if c != "list_market_catalogue"]
    if chiamate:
        ref.note.append("chiamate REST della sessione (registrate, mai eseguite): %s"
                        % ", ".join(chiamate))
    if banco.errori_ponte:
        ref.violazioni.append(CERT.Violazione(
            "BANCO-PONTE", "un errore del replay dentro il giro di un book e' un "
            "guasto del banco, mai un OK muto",
            "%d errori, primo: %s" % (len(banco.errori_ponte), banco.errori_ponte[0])))
    if not ref.decisioni:
        ref.note.append("la strategia non ha MAI deciso: il referto dice 'non lo so'")
