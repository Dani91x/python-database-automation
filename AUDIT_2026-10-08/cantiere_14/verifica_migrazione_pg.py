"""Cantiere 14 - verifica di migrations/replay_tennis_fonte_nomi_2026-10-08.sql su un PostgreSQL 16 USA-E-GETTA.

NON e' il DB dell'utente: un cluster temporaneo in una cartella temporanea, avviato e fermato da
questo script (stessa tecnica di AUDIT_2026-10-07/replay_tennis/verifica_migrazione_pg.py: ruoli
Supabase simulati con la STESSA forma, ``tennis_is_owner()`` copiata da ``migrations/tennis_bots.sql``).

Cosa prova (ogni controllo stampa OK/KO, uscita 1 se un KO):
  1. le tre migrazioni si applicano in ordine (07/10, elenco 08/10, fonte nomi 08/10), la nuova DUE volte;
  2. list_replays_tennis (owner) porta ``nomi_fonte`` E ``market_types``; get_replay_tennis_meta porta
     ``event.nomi_fonte``; il valore e' quello scritto in ``diagnostica`` dal caricamento;
  3. evento senza ``nomi_fonte`` (caricato prima del cantiere): le chiavi ci sono con valore null;
  4. non owner: 'accesso negato'; anon: nessun EXECUTE;
  5. FALSIFICAZIONI: senza la nuova migrazione la chiave NON c'e' (il controllo 2 sa diventare rosso);
     riapplicando DOPO la sola migrazione dell'elenco la chiave sparisce (la trappola dichiarata nel file).

Uso (root nel container, gira postgres come utente ``postgres``), dalla radice del repo:
    python3 AUDIT_2026-10-08/cantiere_14/verifica_migrazione_pg.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
BIN = Path(os.getenv("PG_BIN", "/usr/lib/postgresql/16/bin"))
OWNER = "daniele.ritrovato@gmail.com"
ESITI: list = []
MIG = RADICE / "migrations"


def controllo(nome: str, ok: bool, dettaglio: str = "") -> None:
    ESITI.append(ok)
    print(("OK " if ok else "KO ") + nome + (f"  [{dettaglio}]" if dettaglio else ""))


def come_postgres(cmd: list, **kw) -> subprocess.CompletedProcess:
    if os.geteuid() == 0:
        cmd = ["runuser", "-u", "postgres", "--"] + cmd
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def nuovo_cluster(tmp: Path, nome: str):
    """Cluster usa-e-getta + ambiente Supabase simulato; ritorna (funzione psql, cartella dati)."""
    dati, sock = tmp / f"dati_{nome}", tmp / f"sock_{nome}"
    sock.mkdir()
    os.chmod(sock, 0o777)
    r = come_postgres([str(BIN / "initdb"), "-D", str(dati), "-U", "postgres", "--auth=trust", "-E", "UTF8"])
    if r.returncode:
        raise RuntimeError(r.stderr)
    r = come_postgres([str(BIN / "pg_ctl"), "-D", str(dati), "-o", f"-k {sock} -c listen_addresses=''",
                       "-l", str(tmp / f"log_{nome}.txt"), "-w", "start"])
    if r.returncode:
        raise RuntimeError(r.stderr)

    def psql(sql: str, ruolo_sql: str = "", stop: bool = True) -> subprocess.CompletedProcess:
        f = tmp / "q.sql"
        f.write_text((ruolo_sql + "\n" + sql) if ruolo_sql else sql, encoding="utf-8")
        os.chmod(f, 0o644)
        return come_postgres([str(BIN / "psql"), "-h", str(sock), "-U", "postgres", "-d", "postgres",
                              "-X", "-q", "-t", "-A", "-v", f"ON_ERROR_STOP={1 if stop else 0}", "-f", str(f)])

    base = """
    CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN BYPASSRLS;
    GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
    CREATE SCHEMA auth; GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
    CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE AS
      $$ SELECT coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb $$;
    GRANT EXECUTE ON FUNCTION auth.jwt() TO anon, authenticated, service_role;
    """
    tb = (MIG / "tennis_bots.sql").read_text(encoding="utf-8")
    m = re.search(r"CREATE OR REPLACE FUNCTION public\.tennis_is_owner\(\).*?GRANT EXECUTE ON FUNCTION public\.tennis_is_owner\(\) TO service_role;", tb, re.S)
    r = psql(base + m.group(0))
    controllo(f"[{nome}] ambiente Supabase simulato", r.returncode == 0, r.stderr.strip()[:300])
    return psql, dati


def ferma(dati: Path) -> None:
    come_postgres([str(BIN / "pg_ctl"), "-D", str(dati), "-m", "fast", "-w", "stop"])


EVENTI = """
INSERT INTO public.tennis_replay_eventi (event_id, competition_name, player1_name, player2_name, n_markets, n_snapshots, n_score, diagnostica)
VALUES ('35790089', 'ATP Prova', 'Marcelo Tomas Barrios V', 'Ilia Simakin', 1, 5, 1,
        '{"righe_raw": 10, "nomi_fonte": {"player1_name": "ips", "player2_name": "marketdef"}}'::jsonb),
       ('35000001', 'ATP Vecchio', 'Uno', 'Due', 1, 5, 1, '{"righe_raw": 10}'::jsonb);
INSERT INTO public.tennis_replay_mercati (event_id, market_id, market_type, market_name, selections)
VALUES ('35790089', '1.1', 'MATCH_ODDS', 'Match Odds', '[{"selection_id": 1, "name": "Marcelo Tomas Barrios V", "name_source": "ips", "sort_priority": 1, "status": "WINNER"}]'::jsonb),
       ('35000001', '1.2', 'SET_BETTING', 'Set Betting', '[]'::jsonb);
"""
DA_OWNER = f"SET ROLE authenticated; SET request.jwt.claims = '{{\"role\":\"authenticated\",\"email\":\"{OWNER}\"}}';"
ALTRO = "SET ROLE authenticated; SET request.jwt.claims = '{\"role\":\"authenticated\",\"email\":\"altro@example.com\"}';"


def lista(psql) -> dict:
    r = psql("SELECT public.list_replays_tennis(10);", DA_OWNER)
    return {x["event_id"]: x for x in json.loads(r.stdout.strip() or "{}").get("rows", [])}


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="pgnomi_"))
    os.chmod(tmp, 0o777)
    cluster = []
    try:
        # ---- cluster A: le tre migrazioni in ordine ------------------------------------------------
        psql, dati = nuovo_cluster(tmp, "A")
        cluster.append(dati)
        for nome in ("replay_tennis_2026-10-07.sql", "replay_tennis_mercati_elenco_2026-10-08.sql"):
            r = psql((MIG / nome).read_text(encoding="utf-8"))
            controllo(f"[A] applicata {nome}", r.returncode == 0, r.stderr.strip()[:300])
        r = psql(EVENTI)
        controllo("[A] eventi di prova inseriti", r.returncode == 0, r.stderr.strip()[:300])
        # FALSIFICAZIONE: PRIMA della nuova migrazione la chiave non c'e' (il controllo sotto sa diventare rosso)
        righe = lista(psql)
        controllo("[A] FALSIFICAZIONE: prima della nuova migrazione 'nomi_fonte' NON c'e'",
                  "nomi_fonte" not in righe["35790089"], str(list(righe["35790089"])))
        nuova = (MIG / "replay_tennis_fonte_nomi_2026-10-08.sql").read_text(encoding="utf-8")
        r1, r2 = psql(nuova), psql(nuova)
        controllo("[A] nuova migrazione applicata", r1.returncode == 0, r1.stderr.strip()[:400])
        controllo("[A] nuova migrazione riapplicata (idempotente)", r2.returncode == 0, r2.stderr.strip()[:400])
        righe = lista(psql)
        controllo("[A] list: nomi_fonte della 35790089 = quello di diagnostica",
                  righe["35790089"].get("nomi_fonte") == {"player1_name": "ips", "player2_name": "marketdef"},
                  str(righe["35790089"].get("nomi_fonte")))
        controllo("[A] list: market_types ancora presente (elenco 08/10 non perso)",
                  righe["35790089"].get("market_types") == ["MATCH_ODDS"] and righe["35000001"].get("market_types") == ["SET_BETTING"],
                  str(righe["35790089"].get("market_types")))
        controllo("[A] list: evento caricato prima (senza nomi_fonte) -> chiave presente, valore null",
                  "nomi_fonte" in righe["35000001"] and righe["35000001"]["nomi_fonte"] is None, str(righe["35000001"]))
        r = psql("SELECT public.get_replay_tennis_meta('35790089');", DA_OWNER)
        meta = json.loads(r.stdout.strip() or "{}")
        controllo("[A] meta: event.nomi_fonte presente; mercati e selezioni intatti",
                  meta["event"]["nomi_fonte"] == {"player1_name": "ips", "player2_name": "marketdef"}
                  and meta["markets"][0]["selections"][0]["name_source"] == "ips"
                  and meta["event"]["valuta"] == "GBP", r.stderr.strip()[:200])
        r = psql("SELECT public.get_replay_tennis_meta('35000001');", DA_OWNER)
        controllo("[A] meta: evento vecchio -> nomi_fonte null",
                  json.loads(r.stdout.strip())["event"]["nomi_fonte"] is None, r.stderr.strip()[:200])
        for q in ("SELECT public.list_replays_tennis(10);", "SELECT public.get_replay_tennis_meta('35790089');"):
            r = psql(q, ALTRO, stop=False)
            controllo(f"[A] non owner rifiutato: {q[14:40]}", "accesso negato" in r.stderr, r.stderr.strip()[:120])
            r = psql(q, "SET ROLE anon;", stop=False)
            controllo(f"[A] anon senza EXECUTE: {q[14:40]}", "permission denied" in r.stderr, r.stderr.strip()[:120])
        # TRAPPOLA dichiarata: riapplicare DOPO la sola migrazione dell'elenco fa sparire la chiave
        r = psql((MIG / "replay_tennis_mercati_elenco_2026-10-08.sql").read_text(encoding="utf-8"))
        righe = lista(psql)
        controllo("[A] FALSIFICAZIONE: riapplicando DOPO la sola migrazione dell'elenco la chiave sparisce (come dichiarato nel file)",
                  r.returncode == 0 and "nomi_fonte" not in righe["35790089"], str(list(righe["35790089"])))
        # e rimettendo la nuova torna
        psql(nuova)
        controllo("[A] riapplicando la nuova la chiave torna", "nomi_fonte" in lista(psql)["35790089"])

        # ---- cluster B: ordine inverso (nuova PRIMA dell'elenco 08/10 non e' possibile: la nuova e' autosufficiente) ----
        psql, dati = nuovo_cluster(tmp, "B")
        cluster.append(dati)
        r = psql((MIG / "replay_tennis_2026-10-07.sql").read_text(encoding="utf-8"))
        r = psql(nuova)
        controllo("[B] la nuova si applica subito dopo la 07/10 (senza l'elenco 08/10)", r.returncode == 0, r.stderr.strip()[:300])
        psql(EVENTI)
        righe = lista(psql)
        controllo("[B] ... e porta gia' nomi_fonte E market_types",
                  righe["35790089"].get("nomi_fonte") == {"player1_name": "ips", "player2_name": "marketdef"}
                  and righe["35790089"].get("market_types") == ["MATCH_ODDS"], str(righe["35790089"]))
    finally:
        for d in cluster:
            ferma(d)
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{sum(ESITI)}/{len(ESITI)} controlli OK")
    return 0 if all(ESITI) else 1


if __name__ == "__main__":
    sys.exit(main())
