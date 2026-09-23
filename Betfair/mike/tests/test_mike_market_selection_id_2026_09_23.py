"""`market_id`/`selection_id` per riga (23/09) — contratto DB + banco comune.

TASK f (coordinatore, 23/09): la scheda Mike della Control Room deve trovare
la quota viva della selezione giusta per «se chiudo ora», come gia' fanno
Omega/Safe. Il meccanismo condiviso (`chiusuraViva`/`quotaViva`) legge
`market_id`/`selection_id` dalla riga: se la riga non li porta, il frontend
mostra "-" per sempre.

VERIFICA (fatta il 23/09, prima di scrivere una riga di codice): la colonna
esiste sul DB da sempre e `service.py::_trade_row` scrive gia' `market_id`/
`selection_id` in OGNI riga (`git blame`: b3770d5, 11/09/2026) — questo file
lo mette sotto contratto perche' non regredisca, non lo introduce.

Due livelli, come chiesto:
  1. CONTRATTO SUL DB VERO (`Betfair/mike/db.py`): `insert_trade` scrive il
     dict COSI' COM'E' (nessuna lista di colonne che potrebbe perdere i due
     campi); `get_trade`/`open_trades`/`trades_for_event` leggono `select("*")`
     (nessuna proiezione esplicita che potrebbe ometterli). Lettura del
     sorgente, non una chiamata di rete: qui non c'e' un Supabase vero da
     interrogare (regola della sessione: nessuna scrittura sul DB, nessuna
     nuova lettura/RPC).
  2. ROUND-TRIP sul banco comune (`DbMemoria`, la stessa classe di
     `Betfair/stream/backtest/banco_comune.py` che il banco di replay usa:
     NON una classe di laboratorio): `_trade_row` -> `_insert_trade_row` ->
     `open_trades()`/`trades_for_event()` portano i due campi nella riga letta.

Falsificazione (fatta a mano, 23/09, sorgente ripristinato subito dopo,
nessun diff lasciato in giro): con `market_id`/`selection_id` tolti da
`_trade_row` in `service.py`, `test_trade_row_porta_market_id_e_selection_id`
e `test_round_trip_open_trades_porta_i_due_campi` diventano ROSSI (KeyError /
None al posto dei valori attesi). Con `select("*")` sostituito da un elenco
esplicito di colonne senza i due campi in `get_trade`/`open_trades` di
`Betfair/mike/db.py`, `test_get_trade_e_open_trades_leggono_select_star`
diventa ROSSO.

ASCII-only nel codice; commenti in italiano.
"""
from __future__ import annotations

import inspect
import re
from datetime import datetime, timezone

from Betfair.mike import engine as E
from Betfair.mike import feed as F
from Betfair.mike import service as S
from Betfair.mike import db as DB
from Betfair.stream.backtest.banco_comune import DbMemoria

ORA = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)


def info_vera() -> F.EventInfo:
    """`EventInfo` di produzione (non un doppio), stessa forma di
    `test_mike_loop_taker_2026_09_16.py::info_vera`."""
    return F.EventInfo(
        event_id="35999999", event_name="Finto FC v Prova United",
        home="Finto FC", away="Prova United", competition="Test League",
        ko_at=ORA.timestamp() + 3600.0, open_date=None,
        markets={E.MARKET_OU35: "1.900001", E.MARKET_OU45: "1.900002"},
        selections={(E.MARKET_OU35, E.SEL_UNDER): 11111, (E.MARKET_OU35, E.SEL_OVER): 22222,
                    (E.MARKET_OU45, E.SEL_UNDER): 33333, (E.MARKET_OU45, E.SEL_OVER): 44444})


def leg_apertura() -> E.Leg:
    return E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                 side="back", price=1.85, size=10.0, ref="under_entry-0-1", cycle_no=0)


# ---------------------------------------------------------------------------
# 1. CONTRATTO SUL DB VERO — nessun elenco di colonne che possa perdere i due
#    campi, ne' in scrittura ne' in lettura.
# ---------------------------------------------------------------------------
def test_insert_trade_scrive_il_dict_cosi_com_e() -> None:
    """`insert_trade` deve passare il dict INTERO a Supabase: se un giorno
    qualcuno lo riscrivesse con un elenco esplicito di colonne (com'era per
    `get_mike_state()` prima della v2, vedi `mike_bot_v2.sql`), un campo nuovo
    smetterebbe di arrivare al DB in silenzio."""
    sorgente = inspect.getsource(DB.insert_trade)
    assert re.search(r"\.insert\(\s*trade\s*\)", sorgente), (
        "insert_trade non fa piu' un insert del dict intero: "
        "verificare che market_id/selection_id non vengano persi")


def test_get_trade_e_open_trades_leggono_select_star() -> None:
    """`get_trade`, `open_trades`, `trades_for_event` leggono `select("*")`:
    un elenco esplicito di colonne senza `market_id`/`selection_id` li
    farebbe sparire dalla riga anche se il DB li ha scritti."""
    for fn in (DB.get_trade, DB.open_trades, DB.trades_for_event):
        sorgente = inspect.getsource(fn)
        assert 'select("*")' in sorgente, (
            f"{fn.__name__} non legge piu' select(\"*\"): "
            "verificare che non ometta market_id/selection_id")


# ---------------------------------------------------------------------------
# 2. ROUND-TRIP sul banco comune (DbMemoria, non un doppio di laboratorio):
#    _trade_row -> _insert_trade_row -> lettura della riga.
# ---------------------------------------------------------------------------
def test_trade_row_porta_market_id_e_selection_id() -> None:
    info = info_vera()
    leg = leg_apertura()
    row = S._trade_row(info, leg, "paper", {}, minute=None, score=None)
    assert row["market_id"] == "1.900001"
    assert row["selection_id"] == 11111


def test_round_trip_open_trades_porta_i_due_campi() -> None:
    db = DbMemoria({"status": "running", "mode": "paper", "params": {}})
    info = info_vera()
    leg = leg_apertura()
    row = S._trade_row(info, leg, "paper", {}, minute=12, score="0-0")
    row["status"] = "open"  # una posizione VIVA: deve comparire in open_trades()
    trade_id = S._insert_trade_row(db, row, info.event_id)
    assert trade_id is not None

    aperte = db.open_trades()
    riga = next(r for r in aperte if r["id"] == trade_id)
    assert riga["market_id"] == "1.900001"
    assert riga["selection_id"] == 11111

    per_evento = db.trades_for_event(info.event_id)
    riga2 = next(r for r in per_evento if r["id"] == trade_id)
    assert riga2["market_id"] == "1.900001"
    assert riga2["selection_id"] == 11111


def test_round_trip_su_gamba_over45_selezione_diversa() -> None:
    """Non e' un caso fortunato sulla stessa selezione: OU45/OVER porta un
    market_id e un selection_id DIVERSI, e la riga li deve portare giusti."""
    db = DbMemoria({"status": "running", "mode": "paper", "params": {}})
    info = info_vera()
    leg = E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER,
                side="back", price=2.10, size=5.0, ref="over_cover-0-1", cycle_no=0)
    row = S._trade_row(info, leg, "paper", {}, minute=30, score="1-1")
    row["status"] = "open"
    trade_id = S._insert_trade_row(db, row, info.event_id)

    riga = next(r for r in db.open_trades() if r["id"] == trade_id)
    assert riga["market_id"] == "1.900002"
    assert riga["selection_id"] == 44444


def test_riga_storica_senza_i_due_campi_non_esplode() -> None:
    """Una riga scritta PRIMA dell'11/09 (o da un percorso che non li porta)
    non deve rompere la lettura: `None` e' un valore legittimo, mai un
    KeyError. Il frontend lo mostra come "-", mai un errore o uno zero."""
    db = DbMemoria({"status": "running", "mode": "paper", "params": {}})
    riga_vecchia = {"event_id": "E-STORICO", "status": "open", "side": "back",
                     "price": 1.9, "size": 5.0, "meta": {}}
    trade_id = db.insert_trade(riga_vecchia)
    riga = next(r for r in db.open_trades() if r["id"] == trade_id)
    assert riga.get("market_id") is None
    assert riga.get("selection_id") is None
