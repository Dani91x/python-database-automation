"""24/09 - LO SCALPER CALCIO IN CONTROL ROOM: contratto della migrazione.

``migrations/scalper_control_room_2026-09-24.sql`` aggiunge due RPC owner-only
(``get_scalper_control_room`` e ``scalper_stop_sessione``) e un indice. Qui si
certifica, SENZA database (il DB vero non si tocca mai):

  (1) sicurezza: SECURITY DEFINER, search_path fisso, controllo owner come
      PRIMA istruzione, REVOKE da public/anon, GRANT ad authenticated e
      service_role; nessuna tabella resa leggibile;
  (2) lo stop: la guardia d'identita' ('richiesta_ambigua' su requested_at o
      modalita' diversi, firma assente, modalita' non dichiarata), le stesse
      transizioni di ``scalper_stop`` (running/arming/armed -> 'stopping',
      requested -> 'stopped'), ogni stato scritto dentro il CHECK di
      ``scalper_control``, e la sessione che davvero reagisce a 'stopping'
      (force-flat) nel codice di produzione;
  (3) quali ordini sono dello scalper: il filtro della lettura prende la riga
      che lo SPECCHIO VERO della sessione scrive (``_make_session_mirror``,
      codice di produzione) e scarta quelle del terminale manuale ('awlq') e
      della riconciliazione del conto ('ext', source 'account'/'bot:').

I finti parlano come il vero: l'ordine finto ha gli attributi di un ordine
flumine (come in ``test_live_trading_strategy.py``).
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

RADICE = Path(__file__).resolve().parents[3]
MIGRAZIONE = RADICE / "migrations" / "scalper_control_room_2026-09-24.sql"
SCALPER_BOT_SQL = RADICE / "migrations" / "scalper_bot.sql"
SESSIONE_PY = RADICE / "Betfair" / "stream" / "scalper" / "scalper_session.py"


def _sql() -> str:
    return MIGRAZIONE.read_text(encoding="utf-8")


def _corpo(nome: str) -> str:
    """Il corpo ($$ ... $$) della funzione ``nome``."""
    s = _sql()
    i = s.index(f"CREATE OR REPLACE FUNCTION public.{nome}(")
    a = s.index("AS $$", i)
    b = s.index("$$;", a + 5)
    return s[i:b]


def _senza_commenti(s: str) -> str:
    return "\n".join(l.split("--", 1)[0] for l in s.splitlines())


def _check_status_scalper_control() -> List[str]:
    s = SCALPER_BOT_SQL.read_text(encoding="utf-8")
    m = re.search(r"CHECK \(status IN \(([^)]*)\)\)", s)
    assert m, "CHECK di scalper_control.status non trovato"
    return re.findall(r"'([a-z_]+)'", m.group(1))


# ---------------------------------------------------------------------------
# (1) sicurezza
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nome,firma", [
    ("get_scalper_control_room", "integer"),
    ("scalper_stop_sessione", "text, timestamptz, text"),
])
def test_rpc_owner_only_definer_search_path_e_grant(nome: str, firma: str) -> None:
    corpo = _corpo(nome)
    assert "SECURITY DEFINER" in corpo
    assert "SET search_path = public, pg_temp" in corpo
    # il controllo owner e' la PRIMA istruzione dopo BEGIN
    dopo_begin = _senza_commenti(corpo.split("BEGIN", 1)[1]).strip()
    assert dopo_begin.startswith("IF NOT public.betfair_live_is_owner() THEN"), dopo_begin[:120]
    s = _sql()
    assert f"REVOKE ALL    ON FUNCTION public.{nome}({firma}) FROM public, anon;" in s
    assert f"GRANT EXECUTE ON FUNCTION public.{nome}({firma}) TO authenticated, service_role;" in s


def test_nessuna_tabella_aperta_e_nessuna_scrittura_nella_lettura() -> None:
    s = _senza_commenti(_sql())
    assert "GRANT SELECT" not in s and "GRANT ALL" not in s
    assert "DISABLE ROW LEVEL SECURITY" not in s
    lettura = _senza_commenti(_corpo("get_scalper_control_room"))
    assert "STABLE" in _corpo("get_scalper_control_room")
    for verbo in ("UPDATE ", "INSERT ", "DELETE "):
        assert verbo not in lettura, verbo


# ---------------------------------------------------------------------------
# (2) lo stop della sessione
# ---------------------------------------------------------------------------
def test_stop_guardia_d_identita() -> None:
    c = _senza_commenti(_corpo("scalper_stop_sessione"))
    # firma assente, modalita' non dichiarata, riga assente, riarmata, altra modalita'
    assert c.count("richiesta_ambigua") >= 5
    assert "IF p_requested_at IS NULL THEN" in c
    assert "v_mode NOT IN ('paper', 'live')" in c
    assert "IF v_row.requested_at <> p_requested_at THEN" in c
    assert "(CASE WHEN v_row.dry_run THEN 'paper' ELSE 'live' END) <> v_mode" in c
    # la riga si blocca prima di confrontarla (niente finestra fra lettura e scrittura)
    assert "FOR UPDATE" in c
    # una sessione ferma non si "ferma" di nuovo
    assert "IF v_row.status NOT IN ('requested', 'arming', 'armed', 'running') THEN" in c


def test_stop_stesse_transizioni_di_scalper_stop_e_dentro_il_check() -> None:
    c = _senza_commenti(_corpo("scalper_stop_sessione"))
    assert ("SET status = CASE WHEN status IN ('running', 'arming', 'armed')\n"
            "                         THEN 'stopping' ELSE 'stopped' END") in c
    vecchio = SCALPER_BOT_SQL.read_text(encoding="utf-8")
    assert ("SET status = CASE WHEN status IN ('running','arming','armed')\n"
            "                         THEN 'stopping' ELSE 'stopped' END") in vecchio
    ammessi = set(_check_status_scalper_control())
    # gli stati SCRITTI: solo nella SET dell'UPDATE (non nei confronti di dry_run)
    aggiornamento = c[c.index("UPDATE public.scalper_control"):]
    scritti = set(re.findall(r"SET status = CASE WHEN .*?THEN '([a-z_]+)' ELSE '([a-z_]+)'",
                             aggiornamento, re.S)[0])
    assert scritti == {"stopping", "stopped"}
    assert scritti <= ammessi, scritti - ammessi


def test_la_sessione_vera_reagisce_a_stopping_con_force_flat() -> None:
    """Il comando e' 'stopping' su scalper_control: il codice di produzione
    della sessione lo legge a ogni battito e fa force-flat + attesa flat."""
    src = SESSIONE_PY.read_text(encoding="utf-8")
    i = src.index('if (status in ("stopping", "stopped", "error")')
    blocco = src[i:i + 900]
    assert "_force_flat_all()" in blocco
    assert "_all_flat(timeout_s=30.0)" in blocco


# ---------------------------------------------------------------------------
# (3) quali ordini sono dello scalper
# ---------------------------------------------------------------------------
def _predicato_sql(riga: Dict[str, Any]) -> bool:
    """Il filtro della lettura, riscritto: si verifica prima che il SQL dica
    ESATTAMENTE queste tre condizioni, poi le si applica alle righe vere."""
    c = _senza_commenti(_corpo("get_scalper_control_room"))
    assert "coalesce(b.source, 'runner') IN ('runner', 'scalper')" in c
    assert "b.client_order_ref NOT LIKE 'awlq%'" in c
    assert "b.client_order_ref NOT LIKE 'ext%'" in c
    src = riga.get("source") or "runner"   # DEFAULT 'runner' della colonna
    ref = str(riga["client_order_ref"])
    return src in ("runner", "scalper") and not ref.startswith("awlq") and not ref.startswith("ext")


def _ordine_flumine(ref: str, **over: Any) -> Any:
    ot = SimpleNamespace(ORDER_TYPE=SimpleNamespace(name="LIMIT"), price=2.0, size=10.0,
                         persistence_type="LAPSE")
    base = dict(
        id="OID-9", bet_id="228000000001", market_id="1.200", selection_id=47972, handicap=0.0,
        side="BACK", status=SimpleNamespace(name="EXECUTABLE"), order_type=ot,
        size_matched=10.0, size_remaining=0.0, size_cancelled=0.0, size_lapsed=0.0,
        size_voided=0.0, average_price_matched=2.0, customer_order_ref=ref,
        responses=SimpleNamespace(date_time_placed="2026-09-24T12:00:00+00:00"),
        date_time_status_update="2026-09-24T12:00:01+00:00",
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_la_riga_dello_specchio_vero_della_sessione_e_presa() -> None:
    from Betfair.stream.scalper.scalper_session import _make_session_mirror

    for modo in ("paper", "live"):
        mirror = _make_session_mirror(["1.200"], modo)
        # flumine: customer_order_ref = name_hash + '-' + id, nessun context/notes
        riga = mirror._order_row(_ordine_flumine("b1946ac92492d-17a2f3"),
                                 event_id="35760084", market_id="1.200")
        assert riga["mode"] == modo
        assert riga["bet_id"] == "228000000001"
        assert riga["event_id"] == "35760084"
        assert "source" not in riga            # vale il DEFAULT 'runner' della colonna
        assert _predicato_sql(riga) is True


def test_terminale_manuale_e_conto_restano_fuori() -> None:
    from Betfair.stream.reconcile_worker import _account_order_row

    # il terminale manuale dell'app: ref `awlq<id>`
    assert _predicato_sql({"client_order_ref": "awlq42", "source": "runner"}) is False
    # un ordine trovato SOLO sul conto (dal sito): ext<bet_id>, source 'account'
    conto = _account_order_row(SimpleNamespace(
        bet_id="99", side="BACK", price_size=SimpleNamespace(price=2.0, size=5.0),
        customer_strategy_ref=None, market_id="1.200", selection_id=1, handicap=0.0,
        order_type="LIMIT", size_matched=0.0, size_remaining=5.0, size_cancelled=0.0,
        size_lapsed=0.0, size_voided=0.0, average_price_matched=0.0, status="EXECUTABLE",
        persistence_type="LAPSE", placed_date=None, matched_date=None,
    ))
    assert conto["source"] == "account" and conto["client_order_ref"].startswith("ext")
    assert _predicato_sql(conto) is False
    # un ordine di un bot visto SOLO sul conto: 'bot:<ref>', di quale bot non si sa
    assert _predicato_sql({"client_order_ref": "ext100", "source": "bot:scalper"}) is False


def test_stop_scrive_solo_scalper_control() -> None:
    c = _senza_commenti(_corpo("scalper_stop_sessione"))
    assert re.findall(r"UPDATE public\.(\w+)", c) == ["scalper_control"]
    assert "INSERT" not in c and "DELETE" not in c
