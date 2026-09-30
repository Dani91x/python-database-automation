"""30/09 - ``get_tennis_bot_daily`` per GIORNO DELLA PARTITA
(``migrations/tennis_bot_daily_giorno_partita_2026-09-30.sql``).

Senza DB non si esegue l'SQL qui (il corpo e' stato eseguito in sola lettura
sul DB vero il 30/09: vedi AUDIT_2026-09-30/BACKEND_PER_UI.md). Il test
blinda il contratto: stessa firma, stesse colonne della definizione
precedente (``pnl_betfair_reale_2026-09-24.sql``), giorno dalla
``open_date`` di ``tennis_live_follow`` con ripiego sul regolamento.
"""
from __future__ import annotations

import re
from pathlib import Path

_MIG = Path(__file__).resolve().parents[3] / "migrations"
_NUOVA = _MIG / "tennis_bot_daily_giorno_partita_2026-09-30.sql"
_VECCHIA = _MIG / "pnl_betfair_reale_2026-09-24.sql"


def _funzione(testo: str) -> str:
    i = testo.index("CREATE OR REPLACE FUNCTION public.get_tennis_bot_daily(")
    return testo[i:testo.index("$$;", i)]


def _colonne(corpo: str) -> list:
    return re.findall(r"\bAS ([a-z_]+)\s*,?\s*$", corpo, flags=re.M)


def test_stessa_firma_e_stesse_colonne_della_definizione_precedente():
    nuova = _funzione(_NUOVA.read_text(encoding="utf-8"))
    vecchia = _funzione(_VECCHIA.read_text(encoding="utf-8"))
    firma = re.compile(r"get_tennis_bot_daily\(\s*p_from date,\s*p_to\s+date,\s*"
                       r"p_mode text,\s*p_bot\s+text DEFAULT NULL\s*\) RETURNS json")
    assert firma.search(nuova) and firma.search(vecchia)
    def _riga(cols: list) -> list:      # da 'giorno' a 'volume' (le colonne del json)
        i = cols.index("bot_key") - 1
        return cols[i:cols.index("volume") + 1]

    assert _riga(_colonne(nuova)) == _riga(_colonne(vecchia))
    assert _riga(_colonne(nuova)) == [
        "giorno", "bot_key", "ordini", "vinti", "persi", "pnl_lordo", "commissione",
        "pnl_netto", "pnl_reale", "pnl_stimato", "stimati", "volume"]
    for guardia in ("tennis_is_owner()", "paper e live non si sommano mai",
                    "o.settled_at IS NOT NULL", "SECURITY DEFINER"):
        assert guardia in nuova


def test_giorno_della_partita_con_ripiego_sul_regolamento():
    nuova = _funzione(_NUOVA.read_text(encoding="utf-8"))
    assert "FROM public.tennis_live_follow f" in nuova
    assert "WHERE f.event_id = o.event_id" in nuova
    assert ("(coalesce(p.open_date, o.settled_at) AT TIME ZONE 'Europe/Rome')::date"
            in nuova)
    assert "g.giorno BETWEEN p_from AND p_to" in nuova
    # il giorno del REGOLAMENTO da solo non decide piu' ne' il gruppo ne' il filtro
    assert "(o.settled_at AT TIME ZONE 'Europe/Rome')::date BETWEEN" not in nuova


def test_grant_invariati():
    t = _NUOVA.read_text(encoding="utf-8")
    assert "FROM public, anon;" in t and "TO authenticated, service_role;" in t
