"""Contratto della migrazione `mike_state_arretrati_prova_2026-09-30.sql`.

La UI legge `get_mike_state().arretrati_prova = {day, righe:[...]}`; se la chiave
manca o un campo cambia nome la UI scrive «non letti». Qui si blocca la forma.
"""
from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"
FILE = MIGRATIONS / "mike_state_arretrati_prova_2026-09-30.sql"
CAMPI = ("bot", "mode", "id", "event_id", "event_name", "ko_at", "placed_at",
         "settled_at", "status", "pnl", "closes_trade_id")
CHIAVI_VECCHIE = ("control", "events", "trades", "activity", "aggregates",
                  "requests", "day_start", "day_by")


def _funzione(sql: str) -> str:
    """Corpo della CREATE OR REPLACE FUNCTION get_mike_state (senza commenti di intestazione)."""
    i = sql.index("CREATE OR REPLACE FUNCTION public.get_mike_state()")
    j = sql.index("GRANT EXECUTE ON FUNCTION public.get_mike_state()")
    return sql[i:j]


def _verifica(sql: str) -> list[str]:
    """Elenco dei difetti del contratto (vuoto = ok)."""
    d: list[str] = []
    f = _funzione(sql)
    if "'arretrati_prova'" not in f:
        d.append("manca la chiave arretrati_prova")
    for c in CAMPI:
        if f"'{c}'" not in f:
            d.append(f"manca il campo {c}")
    for k in CHIAVI_VECCHIE:
        if f"'{k}'" not in f:
            d.append(f"chiave preesistente persa: {k}")
    if "'righe'" not in f or "'[]'::jsonb" not in f:
        d.append("righe non garantite come array vuoto")
    if "'day'" not in f:
        d.append("manca day")
    if not re.search(r"mode\s*=\s*'paper'", f):
        d.append("filtro paper assente")
    if "LIMIT 2000" not in f:
        d.append("tetto 2000 assente")
    if "SECURITY DEFINER SET search_path = public, pg_temp" not in f:
        d.append("SECURITY DEFINER / search_path cambiati")
    if "REVOKE ALL    ON FUNCTION public.get_mike_state() FROM public, anon;" not in sql:
        d.append("REVOKE cambiato")
    if "GRANT EXECUTE ON FUNCTION public.get_mike_state() TO authenticated, service_role;" not in sql:
        d.append("GRANT cambiato")
    return d


def test_migrazione_arretrati_prova_contratto():
    assert _verifica(FILE.read_text(encoding="utf-8")) == []


def test_falsificazione_campo_tolto_diventa_rosso():
    sql = FILE.read_text(encoding="utf-8")
    for campo in CAMPI:
        mutato = sql.replace(f"'{campo}',", "'zzz',", 1) if f"'{campo}'," in sql else sql
        assert mutato != sql, campo
        assert any(campo in x for x in _verifica(mutato)), campo
    senza_chiave = sql.replace("'arretrati_prova'", "'altro'")
    assert "manca la chiave arretrati_prova" in _verifica(senza_chiave)
    senza_paper = sql.replace("t.mode = 'paper'", "true")
    assert "filtro paper assente" in _verifica(senza_paper)


def test_solo_ascii():
    FILE.read_text(encoding="utf-8").encode("ascii")
