"""IL SOFTWARE DEVE LASCIAR RESPIRARE IL DATABASE (COSTITUZIONE §17).

Nessuna rete, nessun DB vero. File ASCII-only (console Windows cp1252).

Perche' questi test esistono
----------------------------
Il 13/09 la pagina mostrava partite ferme «in attesa di inizio» quando il calcio
d'inizio era passato da due ore. La logica era giusta — dando allo stesso engine
lo stesso snapshot decideva correttamente — ma il servizio non ci arrivava piu':
il database non rispondeva.

La causa, misurata: il ciclo girava OGNI SECONDO e a ogni giro rileggeva TUTTE
le partite (``select *`` su 48 ore), TUTTO il feed, ricalcolava gli aggregati
con una RPC che scorre ``mike_trades``, e chiedeva le righe di ordine di OGNI
partita viva. Finito il budget di IO, Supabase strozza l'istanza: una lettura
per chiave primaria e' arrivata a 39 secondi.

Questi test fissano il comportamento che lo impedisce. Se qualcuno un domani
rimette una lettura dentro il ciclo, qui diventa rosso.

Il patto: le cache non cambiano MAI una decisione di trading. Cambiano solo
ogni quanto si chiede al database una cosa che nel frattempo non e' cambiata.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from Betfair.mike import config as C
from Betfair.mike import service as S

NOW = datetime(2026, 9, 13, 18, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class DbContatore:
    """Un finto database che conta quante volte gli si chiede ogni cosa."""

    def __init__(self, params: Dict[str, Any] | None = None) -> None:
        self.letture: Dict[str, int] = {}
        self.params = params or {}
        self.eventi: List[Dict[str, Any]] = []
        self.righe_feed: List[Dict[str, Any]] = []

    def _conta(self, nome: str) -> None:
        self.letture[nome] = self.letture.get(nome, 0) + 1

    # -- letture -----------------------------------------------------------
    def read_control(self):
        self._conta("read_control")
        return {"id": 1, "status": "running", "mode": "paper", "params": self.params}

    def fetch_scan_rows(self):
        self._conta("fetch_scan_rows")
        return list(self.righe_feed)

    def list_events(self, states=None, since_iso=None):
        self._conta("list_events")
        return [dict(e) for e in self.eventi]

    def aggregates(self, *a, **k):
        self._conta("aggregates")
        return {"realized_today": 0.0, "open_count": 0, "open_liability": 0.0}

    def scanner_status(self):
        self._conta("scanner_status")
        return {"updated_at": _iso(NOW), "payload": {}}

    def pending_requests(self):
        self._conta("pending_requests")
        return []

    def open_trades(self):
        self._conta("open_trades")
        return []

    def trades_for_event(self, event_id):
        self._conta("trades_for_event")
        return []

    def fail_stale_processing(self, minuti):
        self._conta("fail_stale_processing")
        return 0

    # -- scritture ---------------------------------------------------------
    def set_control(self, **kw):
        self._conta("set_control")

    def upsert_event(self, row):
        self._conta("upsert_event")

    def log(self, kind, payload=None, event_id=None):
        self._conta("log")

    def insert_trade(self, row):
        self._conta("insert_trade")
        return 1

    def update_trade(self, *a, **k):
        self._conta("update_trade")

    def set_request_status(self, *a, **k):
        self._conta("set_request_status")


def _partita(event_id: str, state: str = "WATCH", inplay: bool = False,
             gambe: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    return {
        "event_id": event_id, "event_name": "Prova %s" % event_id, "state": state,
        "cycle_no": 0, "entry_price_initial": None, "dossier": {}, "mode": "paper",
        "ko_at": _iso(NOW + timedelta(hours=1)), "markets": {}, "positions": gambe or [],
        "live": {"inplay": inplay}, "ctx": {}, "skipped": False, "settled_pnl": None,
    }


@pytest.fixture
def db_con_cache(monkeypatch):
    """Un servizio con le cache ACCESE (nel resto della suite sono spente)."""
    for k, v in (("feed_cache_s", 2.0), ("events_reload_s", 60.0),
                 ("aggregates_cache_s", 20.0), ("reconcile_every_s", 30.0)):
        monkeypatch.setitem(C.DEFAULTS, k, v)
    S.svuota_le_cache()
    db = DbContatore()
    monkeypatch.setattr(S, "_real_db", db, raising=False)
    monkeypatch.setattr(S, "_db", lambda: db, raising=False)
    return db


def _giro(db: DbContatore, quando: datetime) -> Dict[str, Any]:
    return S.run_once(db=db, market=None, now=quando, dry=True)


# ===========================================================================
# IL FEED: una lettura ogni feed_cache_s, non a ogni giro
# ===========================================================================
class TestFeed:
    def test_dieci_giri_in_un_secondo_leggono_il_feed_UNA_volta(self, db_con_cache):
        for i in range(10):
            _giro(db_con_cache, NOW + timedelta(milliseconds=100 * i))
        assert db_con_cache.letture.get("fetch_scan_rows") == 1

    def test_passata_la_scadenza_il_feed_si_rilegge(self, db_con_cache):
        _giro(db_con_cache, NOW)
        _giro(db_con_cache, NOW + timedelta(seconds=3))
        assert db_con_cache.letture.get("fetch_scan_rows") == 2

    def test_la_cache_non_falsifica_la_FRESCHEZZA_delle_quote(self, db_con_cache):
        """Il punto money-critical: la freschezza si giudica sull'``updated_at``
        della riga, non su quando l'abbiamo letta. Una riga vecchia resta vecchia
        anche se la rileggiamo adesso — altrimenti la cache farebbe passare per
        buone quote di dieci minuti fa."""
        from Betfair.mike import feed as F

        riga_vecchia = {"event_id": "E1", "updated_at": _iso(NOW - timedelta(minutes=10)),
                        "payload": {}}
        p = C.merge_params(None)
        assert F.feed_fresh(riga_vecchia, NOW.timestamp(), float(p["feed_max_age_s"]), 1.0) is False


# ===========================================================================
# LE PARTITE: copia in memoria, rilettura periodica
# ===========================================================================
class TestPartite:
    def test_dieci_giri_rileggono_le_partite_UNA_volta(self, db_con_cache):
        db_con_cache.eventi = [_partita("E1"), _partita("E2")]
        for i in range(10):
            _giro(db_con_cache, NOW + timedelta(seconds=i))
        assert db_con_cache.letture.get("list_events") == 1

    def test_dopo_events_reload_s_si_rilegge(self, db_con_cache):
        db_con_cache.eventi = [_partita("E1")]
        _giro(db_con_cache, NOW)
        _giro(db_con_cache, NOW + timedelta(seconds=61))
        assert db_con_cache.letture.get("list_events") == 2

    def test_se_il_database_non_risponde_si_continua_con_la_copia(self, db_con_cache):
        """Una posizione aperta non puo' restare senza nessuno che la guardi
        perche' una select e' andata in timeout."""
        db_con_cache.eventi = [_partita("E1", state="PRE_OPEN")]
        _giro(db_con_cache, NOW)          # prima lettura: ora la copia c'e'

        def esplode(states=None, since_iso=None):
            raise RuntimeError("canceling statement due to statement timeout")

        db_con_cache.list_events = esplode          # type: ignore[assignment]
        res = _giro(db_con_cache, NOW + timedelta(seconds=120))
        assert res.get("skipped") != "events_unreadable", "il ciclo deve continuare"

    def test_senza_copia_e_senza_database_ci_si_ferma_e_lo_si_dice(self, db_con_cache):
        def esplode(states=None, since_iso=None):
            raise RuntimeError("timeout")

        db_con_cache.list_events = esplode          # type: ignore[assignment]
        res = _giro(db_con_cache, NOW)
        assert res.get("skipped") == "events_unreadable"


# ===========================================================================
# GLI AGGREGATI: non sono una decisione al secondo
# ===========================================================================
class TestAggregati:
    def test_dieci_giri_li_calcolano_UNA_volta(self, db_con_cache):
        for i in range(10):
            _giro(db_con_cache, NOW + timedelta(seconds=i))
        assert db_con_cache.letture.get("aggregates") == 1

    def test_dopo_la_scadenza_si_ricalcolano(self, db_con_cache):
        _giro(db_con_cache, NOW)
        _giro(db_con_cache, NOW + timedelta(seconds=25))
        assert db_con_cache.letture.get("aggregates") == 2


# ===========================================================================
# IL RITMO: pieno solo quando qualcosa si muove da solo
# ===========================================================================
class TestRitmo:
    def test_senza_niente_che_si_muove_non_c_e_fretta(self, db_con_cache):
        db_con_cache.eventi = [_partita("E1", state="WATCH")]
        assert _giro(db_con_cache, NOW).get("fretta") is False

    def test_una_partita_IN_GIOCO_richiede_il_ciclo_pieno(self, db_con_cache):
        db_con_cache.eventi = [_partita("E1", state="LIVE_COVERED", inplay=True)]
        assert _giro(db_con_cache, NOW).get("fretta") is True

    def test_un_ordine_VIVO_richiede_il_ciclo_pieno(self, db_con_cache):
        gambe = [{"role": "under_entry", "market": "OU35", "selection": "UNDER",
                  "side": "back", "price": 1.5, "size": 10, "matched": 0,
                  "ref": "r1", "status": "pending", "placed_at": 0}]
        db_con_cache.eventi = [_partita("E1", state="PRE_ENTRY_PENDING", gambe=gambe)]
        assert _giro(db_con_cache, NOW).get("fretta") is True

    def test_un_ordine_a_esito_IGNOTO_richiede_il_ciclo_pieno(self, db_con_cache):
        gambe = [{"role": "under_entry", "market": "OU35", "selection": "UNDER",
                  "side": "back", "price": 1.5, "size": 10, "matched": 0,
                  "ref": "r1", "status": "pending_reconcile", "placed_at": 0}]
        db_con_cache.eventi = [_partita("E1", state="PRE_OPEN", gambe=gambe)]
        assert _giro(db_con_cache, NOW).get("fretta") is True

    def test_una_partita_gia_regolata_non_tiene_sveglio_il_ciclo(self, db_con_cache):
        db_con_cache.eventi = [_partita("E1", state="SETTLED", inplay=True)]
        assert _giro(db_con_cache, NOW).get("fretta") is False


# ===========================================================================
# IL CONTO COMPLESSIVO: quante letture in un minuto di lavoro
# ===========================================================================
def test_un_minuto_di_lavoro_non_deve_costare_sessanta_letture(db_con_cache):
    """La misura che riassume tutto.

    Prima: sessanta giri = sessanta ``list_events`` (``select *`` su 48 ore),
    sessanta letture del feed, sessanta RPC di aggregati, piu' una lettura delle
    righe di ordine per ogni partita viva. Adesso il conto e' a una cifra.
    """
    db_con_cache.eventi = [_partita("E%d" % i) for i in range(5)]
    for i in range(60):
        _giro(db_con_cache, NOW + timedelta(seconds=i))
    assert db_con_cache.letture.get("list_events") == 1
    assert db_con_cache.letture.get("fetch_scan_rows") <= 30
    assert db_con_cache.letture.get("aggregates") <= 3
    totale = sum(v for k, v in db_con_cache.letture.items()
                 if k in ("list_events", "fetch_scan_rows", "aggregates", "trades_for_event"))
    assert totale <= 40, "in un minuto: %s" % db_con_cache.letture


def test_le_cache_si_possono_spegnere_dalla_UI(db_con_cache):
    """Ogni valore e' un parametro: a zero si torna al comportamento di prima,
    senza toccare il codice."""
    db_con_cache.params = {"feed_cache_s": 0, "events_reload_s": 0,
                           "aggregates_cache_s": 0, "reconcile_every_s": 0}
    db_con_cache.eventi = [_partita("E1")]
    for i in range(3):
        _giro(db_con_cache, NOW + timedelta(seconds=i))
    assert db_con_cache.letture.get("list_events") == 3
    assert db_con_cache.letture.get("fetch_scan_rows") == 3
