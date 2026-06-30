"""Static guard-rail tests for migrations/betfair_live_order_queue.sql.

MONEY-CRITICAL: le RPC live accodano ordini su denaro REALE e leggono lo specchio
ordini/posizioni. Devono essere OWNER-ONLY (stesso regime di security_lockdown.sql).
Questi test NON toccano il DB e NON usano la rete: leggono il file SQL e verificano
che il guard owner-only sia presente in ogni RPC e che il GRANT resti chiuso.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_SQL = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "betfair_live_order_queue.sql"
)

# Le 4 RPC esposte via PostgREST che devono essere protette owner-only.
_GUARDED_RPCS = (
    "request_betfair_live_order",
    "get_betfair_live_order",
    "get_live_orders",
    "get_live_positions",
)

_OWNER_EMAIL = "daniele.ritrovato@gmail.com"


@pytest.fixture(scope="module")
def sql_text() -> str:
    return _SQL.read_text(encoding="utf-8")


def _function_body(sql: str, name: str) -> str:
    """Estrae il blocco di UNA funzione: da 'CREATE OR REPLACE FUNCTION <name>'
    fino al terminatore '$$;' che chiude il corpo."""
    start = sql.index(f"CREATE OR REPLACE FUNCTION public.{name}(")
    end = sql.index("$$;", start)
    return sql[start:end]


def test_owner_guard_helper_exists(sql_text: str) -> None:
    assert "FUNCTION public.betfair_live_is_owner()" in sql_text
    # autorizza service_role (backend/runner) e l'owner via email del lockdown
    helper = _function_body(sql_text, "betfair_live_is_owner")
    assert "service_role" in helper
    assert _OWNER_EMAIL in helper
    assert "auth.jwt()" in helper


def test_helper_not_granted_to_anon_or_public(sql_text: str) -> None:
    assert (
        "REVOKE ALL ON FUNCTION public.betfair_live_is_owner() FROM public, anon;"
        in sql_text
    )


@pytest.mark.parametrize("rpc", _GUARDED_RPCS)
def test_each_rpc_has_owner_guard(sql_text: str, rpc: str) -> None:
    body = _function_body(sql_text, rpc)
    assert "IF NOT public.betfair_live_is_owner() THEN" in body, (
        f"{rpc}: manca il guard owner-only"
    )
    assert "non autorizzato (owner-only)" in body, (
        f"{rpc}: manca il RAISE owner-only"
    )


@pytest.mark.parametrize("rpc", _GUARDED_RPCS)
def test_guard_runs_before_any_work(sql_text: str, rpc: str) -> None:
    """Il guard deve essere la PRIMA cosa nel BEGIN: nessuna query/insert prima
    del controllo di autorizzazione."""
    body = _function_body(sql_text, rpc)
    begin_idx = body.index("BEGIN")
    guard_idx = body.index("IF NOT public.betfair_live_is_owner()")
    between = body[begin_idx:guard_idx].lower()
    for forbidden in ("insert", "select", "update", "delete"):
        assert forbidden not in between, (
            f"{rpc}: '{forbidden}' eseguito prima del guard owner-only"
        )


@pytest.mark.parametrize("rpc", _GUARDED_RPCS)
def test_rpcs_revoked_from_anon(sql_text: str, rpc: str) -> None:
    # anon non deve mai poter eseguire le RPC live (denaro reale).
    assert re.search(
        rf"REVOKE\s+ALL\s+ON\s+FUNCTION\s+public\.{re.escape(rpc)}\(",
        sql_text,
    ), f"{rpc}: manca REVOKE ALL"
    assert re.search(
        rf"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+public\.{re.escape(rpc)}\([^)]*\)\s+TO\s+authenticated,\s*service_role",
        sql_text,
    ), f"{rpc}: GRANT non corretto"


def test_get_betfair_live_order_has_input_sanity_guard(sql_text: str) -> None:
    """fix(b): get_betfair_live_order deve avere un guard di sanità input su p_id
    (NOT NULL / > 0), coerente con i guard p_market_id di get_live_orders/positions.
    Il guard owner-only resta e precede tutto (verificato dagli altri test)."""
    body = _function_body(sql_text, "get_betfair_live_order")
    assert "p_id IS NULL" in body, "manca il guard p_id NULL"
    assert "p_id <= 0" in body, "manca il guard p_id <= 0"
    # il guard input deve venire PRIMA della SELECT sulla riga (no lavoro su input sporco)
    guard_idx = body.index("p_id IS NULL")
    select_idx = body.lower().index("select to_jsonb")
    assert guard_idx < select_idx, "guard p_id deve precedere la SELECT"
    # e DOPO il guard owner-only (autorizzazione sempre per prima)
    owner_idx = body.index("IF NOT public.betfair_live_is_owner()")
    assert owner_idx < guard_idx, "owner-only deve precedere il guard input"


def test_place_requires_size_or_liability(sql_text: str) -> None:
    """fix(cluster4): place/place_submin deve esigere almeno uno tra size e
    liability (back→size, lay→size|liability); senza dimensione l'ordine è
    indeterminato. Il guard sta nel ramo place/place_submin dell'azione."""
    body = _function_body(sql_text, "request_betfair_live_order")
    assert (
        "place/place_submin: size o liability obbligatorio" in body
    ), "manca il guard size-o-liability"
    assert (
        "nullif(p->>'size','') IS NULL AND nullif(p->>'liability','') IS NULL"
        in body
    ), "il guard deve usare nullif su size E liability (AND: serve almeno uno)"


def test_selection_id_guard_uses_nullif(sql_text: str) -> None:
    """fix(cluster4): selection_id deve usare nullif(...,'') IS NULL come gli altri
    campi obbligatori; (p->>'selection_id') IS NULL lascia passare la stringa vuota
    che poi diventa NULL all'INSERT."""
    body = _function_body(sql_text, "request_betfair_live_order")
    assert "nullif(p->>'selection_id','') IS NULL" in body, (
        "selection_id deve essere validato con nullif(...,'') IS NULL"
    )
    assert "(p->>'selection_id') IS NULL" not in body, (
        "rimasto il vecchio guard selection_id che accetta stringa vuota"
    )


def test_client_order_ref_not_null(sql_text: str) -> None:
    """fix(cluster4): betfair_live_orders.client_order_ref deve essere NOT NULL.
    L'indice unique parziale idx_blo_mode_cref (mode, client_order_ref) WHERE
    bet_id IS NULL si appoggia su questa colonna: NULL!=NULL romperebbe l'unicità."""
    # nella DDL della tabella la colonna è dichiarata NOT NULL
    assert re.search(
        r"client_order_ref\s+TEXT\s+NOT\s+NULL",
        sql_text,
    ), "client_order_ref deve essere NOT NULL"


def test_owner_email_matches_lockdown(sql_text: str) -> None:
    """L'email owner qui deve essere la STESSA del trigger block_non_owner_signup."""
    lockdown = (
        _SQL.parent / "security_lockdown.sql"
    ).read_text(encoding="utf-8")
    assert _OWNER_EMAIL in lockdown
    assert _OWNER_EMAIL in sql_text
