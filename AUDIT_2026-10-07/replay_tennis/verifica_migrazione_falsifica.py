"""Falsificazioni della migrazione replay_tennis_2026-10-07.sql sul PostgreSQL usa-e-getta.

Per ogni mutazione: copia mutata della migrazione (in una cartella temporanea,
il file del repo non si tocca), verifica completa, il controllo indicato DEVE
risultare KO.

Uso:  python3 AUDIT_2026-10-07/replay_tennis/verifica_migrazione_falsifica.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
MIG = RADICE / "migrations" / "replay_tennis_2026-10-07.sql"
VERIFICA = Path(__file__).with_name("verifica_migrazione_pg.py")

MUTAZIONI = [
    ("S1 lista senza guardia owner",
     """    v_lim  integer := least(greatest(coalesce(p_limit, 100), 1), 500);
BEGIN
    IF NOT public.tennis_is_owner() THEN
        RAISE EXCEPTION 'accesso negato';
    END IF;""",
     """    v_lim  integer := least(greatest(coalesce(p_limit, 100), 1), 500);
BEGIN""",
     "KO non owner rifiutato: list_replays_tennis"),
    ("S2 nel bucket vince il PRIMO frame (la chiusura sparisce)",
     "ORDER BY s.market_id, floor(extract(epoch FROM s.ts) / v_bucket), s.ts DESC",
     "ORDER BY s.market_id, floor(extract(epoch FROM s.ts) / v_bucket), s.ts",
     "KO get_replay_tennis_frames bucket 10s"),
    ("S3 EXECUTE lasciato a PUBLIC/anon",
     "REVOKE ALL ON FUNCTION public.list_replays_tennis(integer) FROM PUBLIC, anon;", "",
     "KO anon senza EXECUTE"),
    ("S4 RLS spenta sugli snapshot",
     "ALTER TABLE public.tennis_replay_snapshots ENABLE ROW LEVEL SECURITY;", "",
     "KO RLS accesa su tutte le tabelle"),
    ("S5 SELECT diretta concessa ad authenticated",
     "-- ============================================================================\n-- RPC 1:",
     "GRANT SELECT ON TABLE public.tennis_replay_snapshots TO authenticated;\n-- ============================================================================\n-- RPC 1:",
     "KO authenticated non legge tennis_replay_snapshots"),
    ("S6 figli non cancellati con l'evento",
     "event_id    TEXT NOT NULL REFERENCES public.tennis_replay_eventi(event_id) ON DELETE CASCADE,\n    market_id   TEXT NOT NULL,\n    ts ",
     "event_id    TEXT NOT NULL,\n    market_id   TEXT NOT NULL,\n    ts ",
     "KO cancellare l'evento cancella i figli"),
]


def main() -> int:
    testo = MIG.read_text(encoding="utf-8")
    esiti = []
    with tempfile.TemporaryDirectory(prefix="mutsql_") as d:
        for nome, old, new, atteso in MUTAZIONI:
            assert testo.count(old) == 1, f"{nome}: testo da mutare non trovato una volta sola"
            copia = Path(d) / "mig.sql"
            copia.write_text(testo.replace(old, new), encoding="utf-8")
            r = subprocess.run([sys.executable, str(VERIFICA)], capture_output=True, text=True, timeout=600,
                               env={**os.environ, "MIGRAZIONE_SQL": str(copia)})
            rosso = r.returncode != 0 and any(riga.startswith(atteso) for riga in r.stdout.splitlines())
            esiti.append(rosso)
            print(("ROSSO " if rosso else "VERDE!") + f" {nome}  [{atteso}]")
    print(f"\n{sum(esiti)}/{len(esiti)} mutazioni rosse (file del repo mai toccato)")
    return 0 if all(esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
