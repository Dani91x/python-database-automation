"""BOT MAI CIECHI (01/10/2026) - finestre cieche per causa INTERNA chiuse
oltre all'attesa del fischio (``test_attesa_fischio_2026_10_01.py``).

Ordine dell'utente (01/10): «TUTTI I BOT NON DEVONO ESSERE MAI CIECHI PER
NESSUN MOTIVO, a meno che non dipenda da Betfair».

1. Scanner appena ripartito: «non in gioco» senza nessun book e' ignoranza,
   non un fatto -> l'attesa del fischio non si applica (nessuna riga inventata).
2. Pulizia delle righe orfane: mai prima che il giro sappia cosa vuole
   (cataloghi di tutti gli sport + primi book). Prima cancellava le righe delle
   partite in gioco al primo publish dopo un riavvio.
3. Catalogo: un evento IN GIOCO o con ESPOSIZIONE che esce dalla finestra del
   catalogo (orario previsto > 6 h fa) resta finche' il Match Odds non chiude.
4. Safe: lettura del feed FALLITA != nessuna riga (come Mike M8.7).

Finti con le stesse chiavi e gli stessi tipi del vero (copiati dai test
esistenti dello scanner e del bot). File ASCII-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from Betfair.safe_strategy import bot_service as BS
from Betfair.safe_strategy import scanner
from Betfair.safe_strategy import service as S
from Betfair.safe_strategy.tests.test_bot_service import (
    NOW as NOW_BOT, FakeDB, FakeEngine, FakeMarket, _feed_row, _reset_module_state,
)

NOW = datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat()


# ---------------------------------------------------------------- 1. riavvio
def test_visto_false_niente_attesa_del_fischio():
    ko = iso(NOW - timedelta(seconds=1))
    assert scanner.is_monitorable(False, ko, NOW, mo_status=None, esposto=True, visto=False) is False
    assert scanner.is_monitorable(False, ko, NOW, mo_status="OPEN", esposto=True, visto=True) is True


def _meta(eid, mid, ko_dt, nome="A v B"):
    return {"event_id": eid, "market_id": mid, "event_name": nome, "open_date": iso(ko_dt),
            "competition": "Serie A", "runners": [], "sides": {"home": 1, "away": 2, "draw": 3}}


def test_build_rows_a_scanner_ripartito_non_pubblica_una_riga_inventata():
    """Nessun book visto per l'evento (scanner appena ripartito): la riga non
    nasce «non in gioco» sopra una partita che potrebbe essere al 70'."""
    scan = S.Scanner(None, dry=True, use_stream=False)
    scan.sports["calcio"].metas = {"E1": _meta("E1", "1.MO1", NOW - timedelta(minutes=30))}
    scan._rebuild_market_index()
    scan._mike_followed_ids = ["E1"]
    _, wanted = scan.build_rows(NOW)
    assert wanted == []
    # appena arriva il book del Match Odds (non in gioco) l'attesa vale
    scan.events["E1"] = {"sport": "calcio", "inplay": False, "mo_status": "OPEN"}
    _, wanted = scan.build_rows(NOW)
    assert wanted == ["E1"]


# ---------------------------------------------------------------- 2. pulizia orfane
class _DBScan:
    """Le tre funzioni di ``db`` che ``publish`` usa, con le stesse firme."""

    def __init__(self, in_tabella):
        self.in_tabella = list(in_tabella)
        self.cancellate: list = []
        self.scritte: list = []

    def list_scan_event_ids(self):
        return list(self.in_tabella)

    def delete_scan_rows(self, ids):
        self.cancellate.extend(ids)

    def upsert_scan_rows(self, rows):
        self.scritte.extend(r["event_id"] for r in rows)


@pytest.fixture
def scan_vivo(monkeypatch):
    """Scanner NON dry (il ramo della pulizia vive solo li') con il DB finto."""
    finto = _DBScan(["E_IN", "E_VECCHIA"])
    for nome in ("list_scan_event_ids", "delete_scan_rows", "upsert_scan_rows"):
        monkeypatch.setattr(S.scan_db, nome, getattr(finto, nome))
    scan = S.Scanner(None, dry=False, use_stream=False)
    scan._mike_followed = lambda now_mono=None: []          # type: ignore[method-assign]
    # partita in gioco da 70', scanner appena ripartito: nessun book ancora
    scan.sports["calcio"].metas = {"E_IN": _meta("E_IN", "1.MO1", NOW - timedelta(minutes=70))}
    scan._rebuild_market_index()
    return scan, finto


def test_pulizia_orfane_mai_con_un_catalogo_mancante(scan_vivo):
    scan, finto = scan_vivo
    scan.sports["calcio"].catalogue_ts = 1.0
    scan.sports["tennis"].catalogue_ts = 0.0       # catalogo tennis fallito
    scan.avvio_mono -= 10 * S._ORPHAN_FIRST_GRACE_SEC
    scan.publish(NOW)
    assert finto.cancellate == []


def test_pulizia_orfane_mai_prima_dei_primi_book(scan_vivo):
    scan, finto = scan_vivo
    scan.sports["calcio"].catalogue_ts = 1.0
    scan.sports["tennis"].catalogue_ts = 1.0
    scan.publish(NOW)                               # appena avviato
    assert finto.cancellate == []


def test_pulizia_orfane_a_regime_cancella_le_vere_orfane(scan_vivo):
    scan, finto = scan_vivo
    scan.sports["calcio"].catalogue_ts = 1.0
    scan.sports["tennis"].catalogue_ts = 1.0
    scan.avvio_mono -= S._ORPHAN_FIRST_GRACE_SEC + 1
    scan.events["E_IN"] = {"sport": "calcio", "inplay": True, "mo_status": "OPEN"}
    scan.publish(NOW)
    assert finto.cancellate == ["E_VECCHIA"]        # la partita in gioco resta
    assert finto.scritte == ["E_IN"]


# ---------------------------------------------------------------- 3. catalogo
class _BettingMO:
    def __init__(self):
        self.risposta: list = []
        self.calls = 0

    def list_market_catalogue(self, **kw):
        self.calls += 1
        return list(self.risposta)


def _cat_mo(eid, mid, ko_dt):
    return SimpleNamespace(
        event=SimpleNamespace(id=eid, name="A v B"),
        market_id=mid,
        runners=[SimpleNamespace(selection_id=s, runner_name=n, sort_priority=p)
                 for s, n, p in ((1, "A", 1), (2, "B", 2), (3, "The Draw", 3))],
        market_start_time=ko_dt,
        competition=SimpleNamespace(name="Serie A"),
    )


def test_catalogo_tiene_in_gioco_ed_esposti_fuori_finestra():
    betting = _BettingMO()
    scan = S.Scanner(SimpleNamespace(betting=betting), dry=True, use_stream=False)
    ko = NOW - timedelta(hours=7)                   # oltre _CATALOGUE_PAST_H
    betting.risposta = [_cat_mo("E_IN", "1.1", ko), _cat_mo("E_EXP", "1.2", ko),
                        _cat_mo("E_CHIUSA", "1.3", ko), _cat_mo("E_NULLA", "1.4", ko),
                        _cat_mo("E_ANTICA", "1.5", NOW - timedelta(hours=S._CATALOGUE_KEEP_MAX_H + 1))]
    scan.refresh_catalogue("calcio")
    assert set(scan.sports["calcio"].metas) == {"E_IN", "E_EXP", "E_CHIUSA", "E_NULLA", "E_ANTICA"}
    scan.events.update({
        "E_IN": {"sport": "calcio", "inplay": True, "mo_status": "OPEN"},
        "E_EXP": {"sport": "calcio", "inplay": False, "mo_status": "OPEN"},
        "E_CHIUSA": {"sport": "calcio", "inplay": True, "mo_status": "CLOSED"},
        "E_NULLA": {"sport": "calcio", "inplay": False, "mo_status": "OPEN"},
        "E_ANTICA": {"sport": "calcio", "inplay": True, "mo_status": "OPEN"},
    })
    scan._mike_followed_ids = ["E_EXP"]
    betting.risposta = []                           # tutti fuori dalla finestra
    scan.refresh_catalogue("calcio")
    assert set(scan.sports["calcio"].metas) == {"E_IN", "E_EXP"}
    # l'indice dei mercati li conosce ancora: i loro book si applicano
    assert "1.1" in scan.market_meta and "1.2" in scan.market_meta
    # e restano rilevanti per lo stream (il Match Odds non e' chiuso)
    assert "1.1" in scan.relevant_market_ids("calcio", NOW)
    assert betting.calls == 2                       # nessuna chiamata in piu'


def test_catalogo_tennis_in_gioco_fuori_finestra_resta():
    betting = _BettingMO()
    scan = S.Scanner(SimpleNamespace(betting=betting), dry=True, use_stream=False)
    betting.risposta = [_cat_mo("T1", "1.9", NOW - timedelta(hours=7))]
    scan.refresh_catalogue("tennis")
    scan.events["T1"] = {"sport": "tennis", "inplay": True, "mo_status": "OPEN"}
    betting.risposta = []
    scan.refresh_catalogue("tennis")
    assert set(scan.sports["tennis"].metas) == {"T1"}


# ---------------------------------------------------------------- 4. Safe, lettura fallita
@pytest.fixture
def _pulito():
    BS.azzera_canale_scan()
    _reset_module_state()
    yield
    BS.azzera_canale_scan()
    _reset_module_state()


class _DBCheCade(FakeDB):
    """FakeDB la cui lettura del feed fallisce come ``bot_db.fetch_scan_rows``
    vero (None, mai eccezione) dal secondo ciclo in poi."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.esiti: list = []

    def fetch_scan_rows(self):
        if self.esiti:
            esito = self.esiti.pop(0)
            return None if esito is None else list(esito)
        return list(self.scan_rows)


def test_safe_lettura_fallita_tiene_l_ultima_lista_buona(_pulito):
    db = _DBCheCade()
    db.scan_rows = [_feed_row()]
    db.esiti = [list(db.scan_rows), None, None, list(db.scan_rows)]
    t = NOW_BOT.timestamp()
    righe1, _ = BS._leggi_righe_scan(db, t)
    righe2, _ = BS._leggi_righe_scan(db, t + 2)
    righe3, _ = BS._leggi_righe_scan(db, t + 4)
    assert righe1 == db.scan_rows
    assert righe2 == db.scan_rows and righe3 == db.scan_rows   # mai []
    errori = [p for k, p in db.activity if k == "error" and p.get("reason") == "feed_failed"]
    assert len(errori) == 1 and errori[0]["critical"] is True  # una volta per episodio
    BS._leggi_righe_scan(db, t + 6)
    riprese = [p for k, p in db.activity if p.get("reason") == "lettura_feed_ripresa"]
    assert len(riprese) == 1 and riprese[0]["secondi_senza_lettura"] == 4.0


def test_safe_lettura_fallita_nel_ciclo_vero_il_motore_vede_ancora_la_partita(_pulito):
    db = _DBCheCade()
    db.scan_rows = [_feed_row()]
    eng = FakeEngine()
    BS.run_once(db=db, market=FakeMarket(), engine=eng, now=NOW_BOT)
    assert eng.seen_rows == db.scan_rows
    db.esiti = [None]
    eng2 = FakeEngine()
    BS.run_once(db=db, market=FakeMarket(), engine=eng2, now=NOW_BOT + timedelta(seconds=2))
    assert eng2.seen_rows == db.scan_rows


def test_bot_db_fetch_scan_rows_torna_none_se_la_lettura_fallisce(monkeypatch):
    from Betfair.safe_strategy import bot_db

    def _rotto():
        raise RuntimeError("rete giu")

    monkeypatch.setattr(bot_db, "_sb", _rotto)
    assert bot_db.fetch_scan_rows() is None
