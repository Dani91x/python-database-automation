"""Verifica della migrazione replay_tennis_2026-10-07.sql su un PostgreSQL 16 USA-E-GETTA.

NON e' il DB dell'utente: un cluster temporaneo in una cartella temporanea,
avviato e fermato da questo script (ambiente cloud del delegato, 07/10).
Ruoli e funzioni di Supabase che servono alla migrazione sono simulati con la
STESSA forma: ruoli ``anon``/``authenticated``/``service_role``, ``auth.jwt()``
letta da ``request.jwt.claims`` (come PostgREST), ``tennis_is_owner()`` copiata
da ``migrations/tennis_bots.sql``.

Cosa prova (ogni controllo stampa OK/KO, uscita 1 se un KO):
  1. la migrazione si applica DUE volte (idempotente);
  2. crea SOLO oggetti tennis_replay_* e le 3 RPC del tennis;
  3. righe del convertitore sulla registrazione vera 35790089 inserite nelle tabelle;
  4. owner: list/meta/frames rispondono, i frame per bucket sono quelli attesi
     (ultimo frame del bucket per mercato) calcolati in Python sulle stesse righe;
  5. authenticated NON owner: 'accesso negato'; anon: nessun EXECUTE; nessuna
     SELECT diretta sulle tabelle per anon/authenticated.

Uso (root nel container, gira postgres come utente ``postgres``):
    python3 AUDIT_2026-10-07/replay_tennis/verifica_migrazione_pg.py
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))
BIN = Path(os.getenv("PG_BIN", "/usr/lib/postgresql/16/bin"))
OWNER = "daniele.ritrovato@gmail.com"
ESITI: list = []


def controllo(nome: str, ok: bool, dettaglio: str = "") -> None:
    ESITI.append(ok)
    print(("OK " if ok else "KO ") + nome + (f"  [{dettaglio}]" if dettaglio else ""))


def come_postgres(cmd: list, **kw) -> subprocess.CompletedProcess:
    if os.geteuid() == 0:
        cmd = ["runuser", "-u", "postgres", "--"] + cmd
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main() -> int:
    from Betfair.stream.tennis_replay.convertitore import converti_evento
    from Betfair.stream.tennis_replay.tests.dati_tennis import EVENTO_VERO, cartella_vera

    cart = cartella_vera()
    if cart is None:
        print("registrazione vera assente: verifica non eseguibile")
        return 1
    rt = converti_evento([cart / f"{EVENTO_VERO}.raw.jsonl"], [cart / f"{EVENTO_VERO}.score.jsonl"])

    tmp = Path(tempfile.mkdtemp(prefix="pgreplay_"))
    os.chmod(tmp, 0o777)
    dati, sock = tmp / "dati", tmp / "sock"
    sock.mkdir()
    os.chmod(sock, 0o777)
    r = come_postgres([str(BIN / "initdb"), "-D", str(dati), "-U", "postgres", "--auth=trust", "-E", "UTF8"])
    if r.returncode:
        print(r.stderr)
        return 1
    r = come_postgres([str(BIN / "pg_ctl"), "-D", str(dati), "-o", f"-k {sock} -c listen_addresses=''",
                       "-l", str(tmp / "log.txt"), "-w", "start"])
    if r.returncode:
        print(r.stderr, (tmp / "log.txt").read_text())
        return 1
    try:
        def psql(sql: str, ruolo_sql: str = "", stop: bool = True) -> subprocess.CompletedProcess:
            testo = (ruolo_sql + "\n" + sql) if ruolo_sql else sql
            f = tmp / "q.sql"
            f.write_text(testo, encoding="utf-8")
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
        tb = (RADICE / "migrations" / "tennis_bots.sql").read_text(encoding="utf-8")
        m = re.search(r"CREATE OR REPLACE FUNCTION public\.tennis_is_owner\(\).*?GRANT EXECUTE ON FUNCTION public\.tennis_is_owner\(\) TO service_role;", tb, re.S)
        r = psql(base + m.group(0))
        controllo("ambiente Supabase simulato", r.returncode == 0, r.stderr.strip()[:300])

        prima = psql("SELECT string_agg(c.relname, ',' ORDER BY c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public';"
                     "SELECT string_agg(p.proname, ',' ORDER BY p.proname) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public';").stdout.split("\n")
        # MIGRAZIONE_SQL: un'altra copia (falsificazioni: verifica_migrazione_falsifica.py)
        mig = Path(os.getenv("MIGRAZIONE_SQL") or (RADICE / "migrations" / "replay_tennis_2026-10-07.sql")).read_text(encoding="utf-8")
        r1 = psql(mig)
        r2 = psql(mig)
        controllo("migrazione applicata", r1.returncode == 0, r1.stderr.strip()[:400])
        controllo("migrazione riapplicata (idempotente)", r2.returncode == 0, r2.stderr.strip()[:400])
        dopo = psql("SELECT string_agg(c.relname, ',' ORDER BY c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public';"
                    "SELECT string_agg(p.proname, ',' ORDER BY p.proname) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public';").stdout.split("\n")
        nuove_rel = set(dopo[0].split(",")) - set((prima[0] or "").split(","))
        nuove_fun = set(dopo[1].split(",")) - set((prima[1] or "").split(","))
        controllo("solo oggetti tennis_replay_*", all(x.startswith(("tennis_replay_", "idx_tr")) for x in nuove_rel),
                  ",".join(sorted(nuove_rel)))
        controllo("solo le 3 RPC del tennis", nuove_fun == {"list_replays_tennis", "get_replay_tennis_meta", "get_replay_tennis_frames"},
                  ",".join(sorted(nuove_fun)))

        # dati del convertitore (come li scriverebbe il caricamento)
        def jsonl(nome: str, righe: list) -> Path:
            p = tmp / nome
            p.write_text("\n".join(json.dumps(x, ensure_ascii=True) for x in righe) + "\n", encoding="utf-8")
            os.chmod(p, 0o644)
            return p

        ev = dict(rt.evento, n_markets=len(rt.mercati), n_snapshots=len(rt.snapshot), n_score=len(rt.punteggio),
                  ts_min=rt.snapshot[0]["ts"], ts_max=rt.snapshot[-1]["ts"], raw_files=[], diagnostica=rt.diagnostica)
        fe, fm, fs, fp = (jsonl("e.jsonl", [ev]), jsonl("m.jsonl", rt.mercati), jsonl("s.jsonl", rt.snapshot),
                          jsonl("p.jsonl", rt.punteggio))
        carico = f"""
        CREATE TEMP TABLE j (r jsonb);
        COPY j FROM '{fe}' WITH (FORMAT csv, QUOTE e'\\x01', DELIMITER e'\\x02');
        INSERT INTO public.tennis_replay_eventi (event_id, competition_name, player1_name, player2_name, open_date, n_markets,
                                                 n_snapshots, n_score, ts_min, ts_max, fonte, valuta, raw_files, diagnostica)
          SELECT x.event_id, x.competition_name, x.player1_name, x.player2_name, x.open_date, x.n_markets, x.n_snapshots,
                 x.n_score, x.ts_min, x.ts_max, 'import', 'GBP', x.raw_files, x.diagnostica
            FROM j, jsonb_populate_record(NULL::public.tennis_replay_eventi, r) x;
        TRUNCATE j; COPY j FROM '{fm}' WITH (FORMAT csv, QUOTE e'\\x01', DELIMITER e'\\x02');
        INSERT INTO public.tennis_replay_mercati (event_id, market_id, market_type, market_name, sort_priority, selections, bet_delay, settled_ts, n_updates, ts_min, ts_max)
          SELECT x.event_id, x.market_id, x.market_type, x.market_name, x.sort_priority, x.selections, x.bet_delay, x.settled_ts, x.n_updates, x.ts_min, x.ts_max
            FROM j, jsonb_populate_record(NULL::public.tennis_replay_mercati, r) x;
        TRUNCATE j; COPY j FROM '{fs}' WITH (FORMAT csv, QUOTE e'\\x01', DELIMITER e'\\x02');
        INSERT INTO public.tennis_replay_snapshots (event_id, market_id, ts, inplay, status, ladder)
          SELECT x.event_id, x.market_id, x.ts, x.inplay, x.status, x.ladder FROM j, jsonb_populate_record(NULL::public.tennis_replay_snapshots, r) x;
        TRUNCATE j; COPY j FROM '{fp}' WITH (FORMAT csv, QUOTE e'\\x01', DELIMITER e'\\x02');
        INSERT INTO public.tennis_replay_punteggio (event_id, ts, source, score, event_types, point, payload)
          SELECT x.event_id, x.ts, x.source, x.score, ARRAY(SELECT jsonb_array_elements_text(r->'event_types')), x.point, x.payload
            FROM j, jsonb_populate_record(NULL::public.tennis_replay_punteggio, r) x;
        SELECT (SELECT count(*) FROM public.tennis_replay_snapshots) || ',' || (SELECT count(*) FROM public.tennis_replay_punteggio);
        """
        r = psql(carico)
        controllo("righe del convertitore inserite", r.returncode == 0 and r.stdout.strip() == f"{len(rt.snapshot)},{len(rt.punteggio)}",
                  (r.stdout.strip() + " " + r.stderr.strip())[:300])

        da_owner = f"SET ROLE authenticated; SET request.jwt.claims = '{{\"role\":\"authenticated\",\"email\":\"{OWNER}\"}}';"
        r = psql("SELECT public.list_replays_tennis(10);", da_owner)
        lista = json.loads(r.stdout.strip() or "{}").get("rows", [])
        controllo("list_replays_tennis (owner)", len(lista) == 1 and lista[0]["n_snapshots"] == len(rt.snapshot)
                  and lista[0]["player2_name"] == "Ilia Simakin", r.stderr.strip()[:200])
        r = psql(f"SELECT public.get_replay_tennis_meta('{EVENTO_VERO}');", da_owner)
        meta = json.loads(r.stdout.strip() or "{}")
        controllo("get_replay_tennis_meta (owner)",
                  len(meta.get("markets", [])) == 1 and len(meta.get("score_timeline", [])) == len(rt.punteggio)
                  and meta["markets"][0]["selections"][1]["status"] == "WINNER"
                  and meta["markets"][0]["bet_delay"] == 3 and meta["inplay_from_ts"] is not None
                  and meta["score_timeline"][0]["event_types"] == []
                  and any(p["event_types"] == ["BREAK", "SET_END", "SET_START"] for p in meta["score_timeline"]),
                  r.stderr.strip()[:200])
        for bucket in (1, 2, 10):
            r = psql(f"SELECT public.get_replay_tennis_frames('{EVENTO_VERO}', '{meta['ts_min']}'::timestamptz, "
                     f"'{meta['ts_max']}'::timestamptz + interval '1 second', {bucket}, 10000);", da_owner)
            fr = json.loads(r.stdout.strip() or "{}").get("frames", [])
            attesi = {}
            for s in rt.snapshot:  # ultimo frame di ogni (mercato, bucket)
                t = datetime.fromisoformat(s["ts"]).timestamp()
                attesi[(s["market_id"], math.floor(t / bucket))] = s
            got = sorted((f["ts"], f["status"], json.dumps(f["ladder"], sort_keys=True)) for f in fr)
            exp = sorted((datetime.fromisoformat(s["ts"]).timestamp(), s["status"], json.dumps(s["ladder"], sort_keys=True))
                         for s in attesi.values())
            got_t = [(datetime.fromisoformat(a.replace("Z", "+00:00")).timestamp(), b, c) for a, b, c in got]
            uguali = len(got_t) == len(exp) and all(abs(a[0] - b[0]) < 1e-3 and a[1:] == b[1:] for a, b in zip(sorted(got_t), exp))
            controllo(f"get_replay_tennis_frames bucket {bucket}s = ultimo frame del bucket", uguali and all(f["minute"] is None for f in fr),
                      f"{len(fr)} frame, attesi {len(exp)}")
        r = psql("SELECT public.get_replay_tennis_frames('x', now(), now() - interval '1 second', 10, 100);", da_owner, stop=False)
        controllo("finestra non valida rifiutata", "finestra temporale non valida" in r.stderr, r.stderr.strip()[:200])

        altro = "SET ROLE authenticated; SET request.jwt.claims = '{\"role\":\"authenticated\",\"email\":\"altro@example.com\"}';"
        for q in ("SELECT public.list_replays_tennis(10);", f"SELECT public.get_replay_tennis_meta('{EVENTO_VERO}');",
                  f"SELECT public.get_replay_tennis_frames('{EVENTO_VERO}', now() - interval '1 hour', now(), 10, 100);"):
            r = psql(q, altro, stop=False)
            controllo(f"non owner rifiutato: {q[14:40]}", "accesso negato" in r.stderr, r.stderr.strip()[:120])
        r = psql("SELECT public.list_replays_tennis(10);", "SET ROLE anon;", stop=False)
        controllo("anon senza EXECUTE", "permission denied" in r.stderr, r.stderr.strip()[:120])
        for ruolo in ("anon", "authenticated"):
            for t in ("tennis_replay_eventi", "tennis_replay_mercati", "tennis_replay_snapshots", "tennis_replay_punteggio"):
                r = psql(f"SELECT count(*) FROM public.{t};", f"SET ROLE {ruolo};", stop=False)
                controllo(f"{ruolo} non legge {t}", "permission denied" in r.stderr, r.stderr.strip()[:100])
        r = psql("SELECT bool_and(relrowsecurity) FROM pg_class WHERE relname LIKE 'tennis_replay_%' AND relkind='r';")
        controllo("RLS accesa su tutte le tabelle", r.stdout.strip() == "t")
        r = psql(f"SELECT count(*) FROM public.tennis_replay_snapshots;", "SET ROLE service_role;")
        controllo("service_role legge (backend)", r.returncode == 0 and r.stdout.strip() == str(len(rt.snapshot)), r.stderr.strip()[:120])
        r = psql(f"DELETE FROM public.tennis_replay_eventi WHERE event_id = '{EVENTO_VERO}'; "
                 "SELECT (SELECT count(*) FROM public.tennis_replay_snapshots) + (SELECT count(*) FROM public.tennis_replay_mercati) + (SELECT count(*) FROM public.tennis_replay_punteggio);")
        controllo("cancellare l'evento cancella i figli (ON DELETE CASCADE)", r.stdout.strip() == "0", r.stdout.strip())
    finally:
        come_postgres([str(BIN / "pg_ctl"), "-D", str(dati), "-m", "fast", "-w", "stop"])
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{sum(ESITI)}/{len(ESITI)} controlli OK")
    return 0 if all(ESITI) else 1


if __name__ == "__main__":
    sys.exit(main())
