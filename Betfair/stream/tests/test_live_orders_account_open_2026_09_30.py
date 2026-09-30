"""30/09 - forma della RPC ``get_live_orders_account_open()`` (migrazione
``migrations/live_orders_account_open_2026-09-30.sql``).

Senza DB non si esegue l'SQL: qui si controlla che il FILE di migrazione
produca ESATTAMENTE le chiavi che la UI attende (contratto consegnato alla
sessione UI) e che un risultato nella forma vera le rispetti. Il «finto
risultato» e' la risposta VERA del corpo della funzione eseguito in sola
lettura sul DB il 30/09 (vedi AUDIT_2026-09-30/BACKEND_PER_UI.md).
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pytest

_MIGRAZIONE = (Path(__file__).resolve().parents[3] / "migrations"
               / "live_orders_account_open_2026-09-30.sql")

#: il contratto con la UI: chiave -> tipi JSON ammessi
CONTRATTO_RIGA = {
    "bet_id": (str,),
    "market_id": (str,),
    "selection_id": (int,),
    "event_id": (str, type(None)),
    "event_name": (str, type(None)),
    "market_name": (str, type(None)),
    "selection_name": (str, type(None)),
    "side": (str,),
    "price_matched": (int, float, type(None)),
    "size_matched": (int, float),
    "size_remaining": (int, float),
    "status": (str,),
    "source": (str,),
    "placed_at": (str, type(None)),
}

# risposta VERA (30/09 18:09 UTC, corpo della RPC in sola lettura), 1 riga
RISPOSTA_VERA: Dict[str, Any] = {
    "rows": [{
        "side": "BACK", "bet_id": "445039090782", "source": "account",
        "status": "EXECUTION_COMPLETE", "event_id": "36130526",
        "market_id": "1.263075925", "placed_at": "2026-09-30T13:32:01+00:00",
        "event_name": "FC Vsetin v Bohemians 1905",
        "market_name": "Over/Under 4.5 Goals", "selection_id": 1222347,
        "size_matched": 5.18, "price_matched": 1.44,
        "selection_name": "Under 4.5 Goals", "size_remaining": 0,
    }],
    "letto_at": "2026-09-30T18:09:28.231521+00:00",
}


def _sql() -> str:
    return _MIGRAZIONE.read_text(encoding="utf-8")


def _chiavi_riga_nel_sql(sql: str) -> list:
    """Le chiavi del jsonb_build_object della RIGA (quello dentro jsonb_agg)."""
    i = sql.index("SELECT coalesce(jsonb_agg(jsonb_build_object(")
    j = sql.index(") ORDER BY b.placed_at", i)
    return re.findall(r"^\s*'([a-z_]+)',\s", sql[i:j], flags=re.M)


def verifica_risposta(r: Dict[str, Any]) -> None:
    assert set(r) == {"rows", "letto_at"}
    datetime.fromisoformat(r["letto_at"])
    assert isinstance(r["rows"], list)
    for riga in r["rows"]:
        assert set(riga) == set(CONTRATTO_RIGA), set(riga) ^ set(CONTRATTO_RIGA)
        for k, tipi in CONTRATTO_RIGA.items():
            assert isinstance(riga[k], tipi), (k, riga[k])
        assert riga["side"] in ("BACK", "LAY")
        if riga["placed_at"] is not None:
            datetime.fromisoformat(riga["placed_at"])


def test_sql_produce_esattamente_le_chiavi_del_contratto():
    assert _chiavi_riga_nel_sql(_sql()) == list(CONTRATTO_RIGA)


def test_sql_busta_rows_e_letto_at():
    sql = _sql()
    assert "RETURN jsonb_build_object('rows', v_rows, 'letto_at', now());" in sql
    assert "'side',           upper(b.side)" in sql


def test_sql_sicurezza_e_filtri_fondamentali():
    sql = _sql()
    assert "SECURITY DEFINER" in sql and "SET search_path = public, pg_temp" in sql
    assert "IF NOT public.betfair_live_is_owner() THEN" in sql
    assert "o.mode = 'live'" in sql
    assert "o.source IN ('runner', 'account')" in sql
    for t in ("omega_trades", "safe_strategy_trades", "mike_trades"):
        assert f"FROM public.{t} t" in sql
    assert "FROM public, anon" in sql
    # nessuna scrittura
    for verbo in ("INSERT ", "UPDATE ", "DELETE ", "TRUNCATE "):
        assert verbo not in sql.upper().replace("-- ", "")


def test_risposta_vera_rispetta_il_contratto():
    verifica_risposta(RISPOSTA_VERA)


@pytest.mark.parametrize("guasto", [
    lambda r: r["rows"][0].pop("selection_name"),
    lambda r: r["rows"][0].__setitem__("side", "back"),
    lambda r: r["rows"][0].__setitem__("selection_id", "1222347"),
    lambda r: r.pop("letto_at"),
])
def test_risposta_guasta_rifiutata(guasto):
    import copy
    r = copy.deepcopy(RISPOSTA_VERA)
    guasto(r)
    with pytest.raises((AssertionError, KeyError)):
        verifica_risposta(r)
