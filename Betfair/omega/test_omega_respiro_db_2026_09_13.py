"""IL SOFTWARE DEVE LASCIAR RESPIRARE IL DATABASE — OMEGA (COSTITUZIONE §18).

Nessuna rete, nessun DB vero: fake che CONTANO quante volte gli si chiede ogni
cosa. File ASCII-only (console Windows cp1252).

Perche' questi test esistono
----------------------------
Il 13/09 il progetto Supabase e' andato giu' per esaurimento del budget di IO su
disco: HTTP 503 PGRST002 su tutto, una lettura per chiave primaria a 37 secondi,
e per rialzarlo e' servito un restart. Il contributo di Omega, misurato sul log
delle 21:37 con l'app accesa, era di DUE letture al secondo (la riga del feed di
34 partite, piu' lo stato dello scanner) piu' una ventina di select per giro.

La logica di trading era giusta: era il servizio che non ci arrivava piu'. E
Omega bloccata non e' Omega lenta — e' una posizione aperta a quota 75 che resta
senza nessuno che la guarda. Quelli sono soldi veri.

Questi test fissano il comportamento che lo impedisce. Se qualcuno un domani
rimette una lettura dentro il ciclo senza dichiararne la cadenza, qui diventa
rosso.

IL PATTO: le cache non cambiano MAI una decisione di trading. Cambiano solo ogni
quanto si chiede al database una cosa che nel frattempo non e' cambiata. Il test
``test_la_cache_non_falsifica_la_freschezza_delle_quote`` e' quello che tiene in
piedi tutto il resto: la freschezza si giudica sull'``updated_at`` della RIGA,
non su quando l'abbiamo letta.

Nota: il ``conftest.py`` di Omega SPEGNE le cadenze in tutta la suite (quasi
tutti i test simulano piu' cicli nello stesso istante). Qui le riaccendiamo
apposta, una per una.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest

from Betfair.omega import omega_config as C
from Betfair.omega import omega_market as OM
from Betfair.omega import omega_service as S
from Betfair.stream.scores import scan_feed as SF

NOW = datetime(2026, 9, 13, 21, 37, 0, tzinfo=timezone.utc)

# le cadenze "di produzione", quelle che il conftest spegne e che qui vogliamo
CADENZE_VERE = {
    "feed_cache_s": 2.0,
    "scanner_status_cache_s": 10.0,
    "aggregates_cache_s": 20.0,
    "sets_cache_s": 30.0,
    "results_every_s": 60.0,
    "missions_every_s": 5.0,
    "events_refresh_s": 1800.0,
    "idle_stats_s": 60.0,
    "idle_cycle_s": 60.0,
}


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ===========================================================================
# I finti
# ===========================================================================
class DbContatore:
    """Un finto database che conta quante volte gli si chiede ogni cosa."""

    def __init__(self, params: Optional[dict] = None) -> None:
        self.letture: dict[str, int] = {}
        self.params = dict(params or {})
        self.params.setdefault("engine", "legs")
        self.trades: list[dict[str, Any]] = []
        self.missioni: list[dict[str, Any]] = []
        self.gambe_fatte: set = set()
        self.status = "running"

    def _conta(self, nome: str) -> None:
        self.letture[nome] = self.letture.get(nome, 0) + 1

    def totale(self, *nomi: str) -> int:
        return sum(v for k, v in self.letture.items() if k in nomi)

    # -- letture -----------------------------------------------------------
    def read_control(self):
        self._conta("read_control")
        return {"id": 1, "status": self.status, "mode": "paper",
                "daily_goal": 250.0, "params": self.params, "stats": {}}

    def list_trades(self, status=None):
        self._conta("list_trades")
        return [t for t in self.trades if status is None or t.get("status") == status]

    def open_trades(self):
        self._conta("open_trades")
        return [t for t in self.trades if t.get("status") == "open"]

    def hedged_trades(self):
        self._conta("hedged_trades")
        return []

    def closing_trades_for(self, ids):
        self._conta("closing_trades_for")
        return []

    def get_trade(self, trade_id):
        self._conta("get_trade")
        return next((t for t in self.trades if t.get("id") == int(trade_id)), None)

    def positions_for_results(self, since_iso):
        self._conta("positions_for_results")
        return []

    def pending_manual_requests(self):
        self._conta("pending_manual_requests")
        return []

    def active_missions(self):
        self._conta("active_missions")
        return [m for m in self.missioni if m.get("status", "active") == "active"]

    def mission_event_ids(self):
        self._conta("mission_event_ids")
        return {str(m["event_id"]) for m in self.missioni}

    def manual_event_ids(self, since_iso=None):
        self._conta("manual_event_ids")
        return set()

    def traded_event_ids(self):
        self._conta("traded_event_ids")
        return {str(t["event_id"]) for t in self.trades}

    def traded_legs(self, since_iso=None):
        self._conta("traded_legs")
        return set(self.gambe_fatte)

    def failed_legs(self, since_iso=None):
        self._conta("failed_legs")
        return {}

    def aggregates(self, day_start=None):
        self._conta("aggregates")
        return {"realized_today": 0.0, "realized_profit": 0.0, "matches_open": 0,
                "open_liability": 0.0, "matches_traded": 0, "matches_traded_today": 0,
                "events_today": 0, "legs_today": 0, "live_now": 0}

    def trades_for_event(self, event_id):
        self._conta("trades_for_event")
        return [t for t in self.trades if str(t.get("event_id")) == str(event_id)]

    def get_event(self, event_id):
        self._conta("get_event")
        return None

    # -- scritture (MAI in cache) ------------------------------------------
    def set_control(self, **fields):
        self._conta("set_control")
        self.params = self.params

    def log(self, kind, payload=None):
        self._conta("log")

    def update_trade(self, trade_id, **fields):
        self._conta("update_trade")

    def insert_trade(self, trade):
        self._conta("insert_trade")
        return 1

    def update_mission(self, event_id, **fields):
        self._conta("update_mission")

    def replace_events(self, rows):
        self._conta("replace_events")

    def upsert_daily_goal(self, day, goal):
        self._conta("upsert_daily_goal")
        return True


class MarketMuto:
    """Un Betfair che non ha niente da dire: qui misuriamo il DATABASE."""

    def list_today_football_events(self, with_competitions=False):
        return []

    def read_markets(self, markets):
        return {}

    def get_inplay_scores(self, event_ids):
        return {}


def _giro(db: DbContatore, market: Any, quando: datetime) -> dict:
    return S.run_once(market=market, db=db, now=quando)


@pytest.fixture
def acceso(monkeypatch):
    """Un servizio con le cadenze ACCESE (nel resto della suite sono spente)."""
    for k, v in CADENZE_VERE.items():
        monkeypatch.setitem(C.DEFAULTS, k, v)
    S.svuota_le_cache()
    return DbContatore(), MarketMuto()


# ===========================================================================
# IL FEED — la lettura che decide un ORDINE: cache cortissima, freschezza
# giudicata sull'updated_at della riga e MAI su quando l'abbiamo letta
# ===========================================================================
class CacheFinta:
    """Il finto ``ScanRowCache`` dello scanner: conta le select."""

    def __init__(self, righe: Optional[dict] = None) -> None:
        self.righe = dict(righe or {})
        self.select_righe = 0
        self.select_status = 0
        self.ultimi_id: list[str] = []
        self.eta_scanner: Optional[float] = 1.0

    def rows_for(self, event_ids):
        self.select_righe += 1
        self.ultimi_id = list(event_ids)
        return {e: self.righe[e] for e in event_ids if e in self.righe}

    def scanner_age_sec(self):
        self.select_status += 1
        return self.eta_scanner


def _riga(event_id: str, quando: datetime, payload: Optional[dict] = None) -> dict:
    return {"event_id": event_id, "sport": "football",
            "updated_at": _iso(quando),
            "payload": payload if payload is not None else {"inplay": True, "minute": 30}}


@pytest.fixture
def feed(monkeypatch):
    """``_feed_row`` con cadenze vere e un orologio che possiamo far avanzare."""
    for k, v in CADENZE_VERE.items():
        monkeypatch.setitem(C.DEFAULTS, k, v)
    S.svuota_le_cache()
    finta = CacheFinta()
    monkeypatch.setattr(SF, "shared_cache", lambda: finta)
    orologio = {"t": 1000.0}
    monkeypatch.setattr(S, "_mono", lambda: orologio["t"])
    return finta, orologio


class TestFeed:
    def test_dieci_letture_nello_stesso_istante_costano_UNA_select(self, feed):
        finta, _ = feed
        finta.righe["E1"] = _riga("E1", datetime.now(timezone.utc))
        for _ in range(10):
            S._feed_row("E1")
        assert finta.select_righe == 1, (
            "dieci domande alla stessa riga dentro lo stesso ciclo sono dieci "
            "risposte identiche pagate dieci volte")

    def test_passata_la_scadenza_la_riga_si_rilegge(self, feed):
        finta, orologio = feed
        finta.righe["E1"] = _riga("E1", datetime.now(timezone.utc))
        S._feed_row("E1")
        orologio["t"] += 3.0                      # > feed_cache_s (2 s)
        S._feed_row("E1")
        assert finta.select_righe == 2

    def test_la_cache_non_falsifica_la_freschezza_delle_quote(self, feed):
        """IL PUNTO MONEY-CRITICAL.

        La freschezza si giudica sull'``updated_at`` della riga, non su quando
        l'abbiamo letta. Una riga ferma da dieci minuti resta ferma da dieci
        minuti anche se la rileggiamo adesso — altrimenti la cache farebbe
        passare per buone quote vecchie, e su un lay a quota 75 quello e' il
        modo piu' veloce per perdere una liability intera.
        """
        finta, orologio = feed
        vecchia = _riga("E1", datetime.now(timezone.utc) - timedelta(minutes=10))
        finta.righe["E1"] = vecchia
        finta.eta_scanner = 1.0                   # scanner VIVISSIMO: la deroga c'e'
        payload, _upd = S._feed_row("E1", hard_max_age=S.DECISION_MAX_AGE_S)
        assert payload is None, "una riga di dieci minuti fa non decide un ordine"
        # e rileggendola adesso resta esattamente altrettanto vecchia
        orologio["t"] += 5.0
        payload, _upd = S._feed_row("E1", hard_max_age=S.DECISION_MAX_AGE_S)
        assert payload is None

    def test_una_riga_fresca_passa_anche_dalla_cache(self, feed):
        """Il rovescio: la cache non deve nemmeno BUTTARE VIA dati buoni."""
        finta, _ = feed
        finta.righe["E1"] = _riga("E1", datetime.now(timezone.utc))
        payload, _upd = S._feed_row("E1", hard_max_age=S.DECISION_MAX_AGE_S)
        assert isinstance(payload, dict) and payload.get("minute") == 30

    def test_alla_scadenza_si_rileggono_INSIEME_tutte_le_partite_note(self, feed):
        """Lo scanner risponde con UNA select sull'unione degli id: chiedere
        trenta partite costa come chiederne una, chiederle una alla volta costa
        trenta volte. Era esattamente il log delle 21:37 (34 id in URL)."""
        finta, orologio = feed
        for i in range(5):
            eid = "E%d" % i
            finta.righe[eid] = _riga(eid, datetime.now(timezone.utc))
            S._feed_row(eid)
        prima = finta.select_righe
        orologio["t"] += 3.0
        for i in range(5):
            S._feed_row("E%d" % i)
        assert finta.select_righe == prima + 1, "una sola select per tutte e cinque"
        assert set(finta.ultimi_id) == {"E%d" % i for i in range(5)}

    def test_una_partita_dimenticata_esce_dall_insieme_letto(self, feed):
        """Altrimenti l'URL della select crescerebbe per tutta la giornata."""
        finta, orologio = feed
        finta.righe["E1"] = _riga("E1", datetime.now(timezone.utc))
        finta.righe["E2"] = _riga("E2", datetime.now(timezone.utc))
        S._feed_row("E1")
        S._feed_row("E2")
        orologio["t"] += S._FEED_DIMENTICA_DOPO_S + 10.0
        S._feed_row("E2")
        assert "E1" not in finta.ultimi_id

    def test_eta_dello_scanner_letta_una_volta_e_INVECCHIATA(self, feed):
        """Il valore in cache viene invecchiato del tempo passato: quella che ne
        esce e' esattamente l'eta' di quella riga, non un'approssimazione."""
        finta, orologio = feed
        finta.eta_scanner = 4.0
        cache = SF.shared_cache()
        assert S._scanner_eta_cached(cache) == pytest.approx(4.0)
        orologio["t"] += 6.0
        assert S._scanner_eta_cached(cache) == pytest.approx(10.0)
        assert finta.select_status == 1, "una sola lettura di safe_strategy_status"

    def test_oltre_la_scadenza_lo_stato_dello_scanner_si_rilegge(self, feed):
        finta, orologio = feed
        cache = SF.shared_cache()
        S._scanner_eta_cached(cache)
        orologio["t"] += 11.0                     # > scanner_status_cache_s (10 s)
        S._scanner_eta_cached(cache)
        assert finta.select_status == 2


# ===========================================================================
# GLI AGGREGATI — la RPC che scorre tutta omega_trades
# ===========================================================================
class TestAggregati:
    def test_dieci_giri_in_dieci_secondi_li_calcolano_UNA_volta(self, acceso):
        db, market = acceso
        for i in range(10):
            _giro(db, market, NOW + timedelta(seconds=i))
        assert db.letture.get("aggregates") == 1

    def test_dopo_la_scadenza_si_ricalcolano(self, acceso):
        db, market = acceso
        _giro(db, market, NOW)
        _giro(db, market, NOW + timedelta(seconds=25))
        assert db.letture.get("aggregates") == 2

    def test_dopo_un_SETTLEMENT_si_rifanno_subito(self, acceso, monkeypatch):
        """Stop giornaliero e cap di perdita decidono su questi numeri: se in
        questo giro abbiamo regolato qualcosa, il conto va rifatto ADESSO — non
        fra venti secondi, o il bot continuerebbe ad aprire dopo aver gia' perso
        il massimo."""
        db, market = acceso
        _giro(db, market, NOW)
        letture_prima = db.letture.get("aggregates")
        monkeypatch.setattr(S, "settle_open", lambda **kw: 3)
        _giro(db, market, NOW + timedelta(seconds=1))
        assert db.letture.get("aggregates") == letture_prima + 1


# ===========================================================================
# GLI INSIEMI "che cosa ho gia' fatto io" — li scrive questo stesso processo,
# quindi fra una rilettura e l'altra la copia in memoria E' la verita'
# ===========================================================================
class TestInsiemi:
    def test_dieci_giri_rileggono_le_gambe_fatte_UNA_volta(self, acceso):
        db, market = acceso
        for i in range(10):
            _giro(db, market, NOW + timedelta(seconds=i))
        assert db.letture.get("traded_legs") == 1

    def test_dopo_sets_cache_s_si_rilegge(self, acceso):
        db, market = acceso
        _giro(db, market, NOW)
        _giro(db, market, NOW + timedelta(seconds=31))
        assert db.letture.get("traded_legs") == 2

    def test_la_gamba_appena_piazzata_resta_nella_copia_in_memoria(self):
        """Il bug da NON introdurre: se la cache restituisse una COPIA, la gamba
        aggiunta dallo scan sparirebbe al giro dopo e Omega la ripiazzerebbe —
        un secondo lay sulla stessa partita, soldi veri."""
        S.svuota_le_cache()
        letture = {"n": 0}

        def _leggi():
            letture["n"] += 1
            return {("E1", "ht_cs")}

        primo = S._insieme_cached("traded_legs", 1000.0, 30.0, _leggi)
        primo.add(("E1", "ft_cs"))
        secondo = S._insieme_cached("traded_legs", 1001.0, 30.0, _leggi)
        assert secondo is primo
        assert ("E1", "ft_cs") in secondo
        assert letture["n"] == 1

    def test_se_la_lettura_fallisce_si_continua_con_la_copia(self):
        """Una giornata di trading non si ferma perche' una select e' andata in
        timeout: una posizione aperta non puo' restare senza nessuno che la
        guardi."""
        S.svuota_le_cache()
        stato = {"rompi": False}

        def _leggi():
            if stato["rompi"]:
                raise RuntimeError("canceling statement due to statement timeout")
            return {("E1", "ht_cs")}

        S._insieme_cached("traded_legs", 1000.0, 30.0, _leggi)
        stato["rompi"] = True
        fuori = S._insieme_cached("traded_legs", 2000.0, 30.0, _leggi)
        assert fuori == {("E1", "ht_cs")}

    def test_senza_copia_l_errore_risale_come_prima(self):
        """Nessuna copia = nessuna invenzione: il chiamante decide (ed e' il
        comportamento di prima, heartbeat degradato e giro saltato)."""
        S.svuota_le_cache()

        def _esplode():
            raise RuntimeError("timeout")

        with pytest.raises(RuntimeError):
            S._insieme_cached("traded_legs", 1000.0, 30.0, _esplode)


# ===========================================================================
# LE GUARDIE — quello che l'utente si e' preso NON va in cache, mai
# ===========================================================================
class TestGuardie:
    def test_missioni_e_manuali_si_rileggono_a_OGNI_giro(self, acceso):
        """Sono le due letture che impediscono all'automatico di bancare su una
        partita che l'utente si e' appena preso. Le scrive la UI, cioe' un ALTRO
        processo: la copia in memoria non e' la verita', e allargare la finestra
        vuol dire un secondo lay su una partita gia' esposta. Si pagano a ogni
        giro, volentieri."""
        db, market = acceso
        for i in range(5):
            _giro(db, market, NOW + timedelta(seconds=i))
        assert db.letture.get("mission_event_ids") == 5
        assert db.letture.get("manual_event_ids") == 5

    def test_le_partite_gia_bancate_non_vanno_in_cache(self, acceso):
        """Il motore 'single' fa ``traded_ids.add(...)`` su una UNIONE costruita
        nel giro, non sull'insieme originale: con una cache la partita appena
        bancata non risulterebbe bancata al giro dopo, e I1 («un solo lay per
        match») starebbe in piedi solo grazie all'unique del database. Si legge
        a ogni giro — ma UNA volta sola, non due come prima."""
        db, market = acceso
        db.params["engine"] = "single"
        for i in range(3):
            _giro(db, market, NOW + timedelta(seconds=i))
        assert db.letture.get("traded_event_ids") == 3, "una lettura per giro"

    def test_le_righe_dei_trade_non_vanno_mai_in_cache(self, acceso):
        """Fra la fase di settlement e quella di green-up, DENTRO lo stesso
        giro, quelle righe cambiano: una copia vecchia farebbe mandare un ordine
        di chiusura su una posizione appena regolata."""
        db, market = acceso
        _giro(db, market, NOW)
        assert db.letture.get("open_trades", 0) >= 2, (
            "settlement e green-up devono vedere ognuno lo stato VERO del momento")


# ===========================================================================
# LE FASI CON CADENZA PROPRIA
# ===========================================================================
class TestFasi:
    def test_i_risultati_si_timbrano_al_massimo_ogni_results_every_s(self, acceso):
        db, market = acceso
        for i in range(10):
            _giro(db, market, NOW + timedelta(seconds=i))
        assert db.letture.get("positions_for_results") == 1
        _giro(db, market, NOW + timedelta(seconds=61))
        assert db.letture.get("positions_for_results") == 2

    def test_le_missioni_si_aggiornano_al_massimo_ogni_missions_every_s(self, acceso):
        db, market = acceso
        db.missioni = [{"event_id": "E1", "status": "active", "kickoff": _iso(NOW)}]
        for i in range(5):
            _giro(db, market, NOW + timedelta(seconds=i))
        assert db.letture.get("active_missions") == 1
        _giro(db, market, NOW + timedelta(seconds=6))
        assert db.letture.get("active_missions") == 2

    def test_omega_control_si_legge_UNA_volta_per_giro(self, acceso):
        """Prima erano due: una in ``run_once`` e una in ``process_missions``,
        a un decimo di secondo di distanza, per avere gli stessi identici
        parametri."""
        db, market = acceso
        db.missioni = [{"event_id": "E1", "status": "active", "kickoff": _iso(NOW)}]
        _giro(db, market, NOW)
        assert db.letture.get("read_control") == 1

    def test_il_budget_dei_tentativi_non_si_riscandisce_a_ogni_giro(self, acceso):
        db, market = acceso
        for i in range(10):
            _giro(db, market, NOW + timedelta(seconds=i))
        assert db.letture.get("failed_legs") == 1


# ===========================================================================
# IL RITMO — pieno solo quando qualcosa si muove da solo
# ===========================================================================
class TestRitmo:
    def test_senza_niente_aperto_non_c_e_fretta(self, acceso):
        db, market = acceso
        assert _giro(db, market, NOW).get("fretta") is False

    def test_una_posizione_APERTA_richiede_il_ciclo_pieno(self, acceso, monkeypatch):
        db, market = acceso

        def _agg(day_start=None):
            db._conta("aggregates")
            return {"realized_today": 0.0, "matches_open": 1, "open_liability": 74.0,
                    "live_now": 1, "events_today": 0}

        db.aggregates = _agg                       # type: ignore[assignment]
        assert _giro(db, market, NOW).get("fretta") is True

    def test_una_MISSIONE_attiva_richiede_il_ciclo_pieno(self, acceso):
        """L'utente sta guardando quella partita dalla pagina: i suggerimenti
        non possono arrivargli con un minuto di ritardo."""
        db, market = acceso
        db.missioni = [{"event_id": "E1", "status": "active", "kickoff": _iso(NOW)}]
        assert _giro(db, market, NOW).get("fretta") is True

    def test_a_bot_FERMO_con_una_posizione_aperta_c_e_ancora_fretta(self, acceso):
        """Fermare il bot blocca i NUOVI ingressi, non il green-up di una gamba
        gia' viva: il ritmo deve restare pieno."""
        db, market = acceso
        db.status = "stopped"

        def _agg(day_start=None):
            db._conta("aggregates")
            return {"realized_today": 0.0, "matches_open": 1, "open_liability": 74.0,
                    "live_now": 1}

        db.aggregates = _agg                       # type: ignore[assignment]
        assert _giro(db, market, NOW).get("fretta") is True


# ===========================================================================
# IL CONTO COMPLESSIVO: quante letture in un minuto di lavoro
# ===========================================================================
def test_un_minuto_di_lavoro_a_ritmo_aggressivo(acceso):
    """La misura che riassume tutto.

    Dodici giri (``poll_interval_s`` al minimo, 5 s) con una partita in corso.
    Prima: dodici RPC di aggregati, dodici scansioni delle gambe fatte, dodici
    letture del budget dei tentativi, dodici timbrature dei risultati, dodici
    ``omega_control`` in piu' dal loop. Adesso il conto sta in una mano.
    """
    db, market = acceso
    for i in range(12):
        _giro(db, market, NOW + timedelta(seconds=5 * i))
    assert db.letture.get("aggregates") <= 4        # 60 s / aggregates_cache_s
    assert db.letture.get("traded_legs") <= 2       # 60 s / sets_cache_s
    assert db.letture.get("failed_legs") <= 2
    assert db.letture.get("positions_for_results") <= 1
    assert db.letture.get("read_control") == 12     # una per giro, mai due
    periodiche = db.totale("aggregates", "traded_legs", "failed_legs",
                           "positions_for_results", "traded_event_ids")
    assert periodiche <= 10, "in un minuto: %s" % db.letture


def test_le_cadenze_si_possono_spegnere_dai_parametri(acceso):
    """Ogni valore e' un parametro: a zero si torna esattamente al comportamento
    di prima, senza toccare una riga di codice."""
    db, market = acceso
    db.params.update({k: 0 for k in CADENZE_VERE})
    for i in range(3):
        _giro(db, market, NOW + timedelta(seconds=i))
    assert db.letture.get("aggregates") == 6         # due per giro, come prima
    assert db.letture.get("traded_legs") == 3
    assert db.letture.get("positions_for_results") == 3


def test_ogni_cadenza_e_nella_whitelist_con_i_suoi_limiti():
    """Obbligo §18.5: ogni lettura periodica ha il SUO parametro, dichiarato,
    regolabile e con dei limiti. Una select dentro un ciclo senza una cadenza
    dichiarata e' un difetto, non una svista."""
    for nome, atteso in CADENZE_VERE.items():
        assert nome in C._SPEC, "cadenza senza parametro: %s" % nome
        default, cast, lo, hi = C._SPEC[nome]
        assert cast is float
        assert default == atteso, "default cambiato per %s" % nome
        assert lo == 0.0, "%s deve poter essere SPENTO (0)" % nome
        assert hi is not None and hi > default


def test_svuota_le_cache_azzera_davvero_tutto(feed):
    """Serve a forzare un riallineamento immediato: un riavvio, o una modifica
    fatta a mano sul database mentre il servizio gira."""
    finta, _ = feed
    finta.righe["E1"] = _riga("E1", datetime.now(timezone.utc))
    S._feed_row("E1")
    S._scanner_eta_cached(SF.shared_cache())
    S._insieme_cached("traded_legs", 1000.0, 30.0, lambda: {("E1", "ht_cs")})
    S.svuota_le_cache()
    assert not S._CACHE_FEED_RIGHE and not S._CACHE_SCANNER and not S._CACHE_INSIEMI
    assert S._ULTIMI_PARAMS is None
    S._feed_row("E1")
    assert finta.select_righe == 2


def test_il_market_reale_e_quello_vero(acceso):
    """Sanita' del finto: se ``omega_market`` cambiasse nome ai suoi moduli, i
    rami del feed non verrebbero piu' esercitati e questi test misurerebbero
    aria. (Il feed e' attivo SOLO col market reale: vedi ``_feed_state``.)"""
    assert S._real_market is OM
