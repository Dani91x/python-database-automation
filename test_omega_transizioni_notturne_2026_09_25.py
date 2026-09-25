# -*- coding: utf-8 -*-
"""O2 (25/09/2026): transizioni di Omega sempre aggiornate.

Due famiglie di test, nessun DB, nessuna rete:
1. CONTRATTO sul file SQL ``migrations/omega_transitions_catchup_2026-09-25.sql``:
   registro scritto nella stessa funzione e con ON CONFLICT che non ri-somma,
   pg_cron idempotente con guardia, DELETE sulle tabelle dei bot solo nella
   pubblicazione dichiarata, RPC dei bot non ridefinite, vecchi costruttori spenti,
   nessun grant ad anon/authenticated. (L'esecuzione VERA dell'SQL e' nel banco
   ``AUDIT_2026-09-25/O2_banco_pglite_2026-09-25.mjs``: PostgreSQL in wasm con il
   costruttore originale come oracolo.)
2. Lo script di verifica ``Betfair/omega/tools/verifica_transizioni_2026_09_25.py``
   contro un finto Supabase che parla come il vero: table(..).select(cols,
   count=..).eq/lte/order(col, desc=)/range/limit(..).execute() -> .data/.count,
   max 1000 righe per risposta; rpc(nome, params).execute().data con le chiavi
   estratte dal file SQL (se la migrazione rinomina una chiave, il test diventa rosso).
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

import pytest

os.environ["SUPABASE_URL"] = "http://127.0.0.1:9"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "x"
os.environ["SUPABASE_KEY"] = "x"

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from Betfair.omega.tools import verifica_transizioni_2026_09_25 as V  # noqa: E402

SQL_PATH = os.path.join(ROOT, "migrations", "omega_transitions_catchup_2026-09-25.sql")
SQL = open(SQL_PATH, encoding="utf-8").read()


def _senza_commenti(s: str) -> str:
    return "\n".join(l.split("--", 1)[0] if not l.lstrip().startswith("--") else "" for l in s.splitlines())


CODICE = _senza_commenti(SQL)


def _funzione(nome: str) -> str:
    """Corpo (testo) di CREATE OR REPLACE FUNCTION public.<nome>( ... $$;"""
    m = re.search(r"CREATE OR REPLACE FUNCTION public\." + re.escape(nome) + r"\(", CODICE)
    assert m, f"funzione {nome} assente"
    fine = CODICE.index("$$;", CODICE.index("$$", CODICE.index("AS $$", m.start()) + 5))
    return CODICE[m.start():fine]


def _funzioni_con(testo_regex: str) -> List[str]:
    nomi = []
    for m in re.finditer(r"CREATE OR REPLACE FUNCTION public\.(\w+)\(", CODICE):
        corpo = _funzione(m.group(1))
        if re.search(testo_regex, corpo):
            nomi.append(m.group(1))
    return nomi


# ===========================================================================
# 1. CONTRATTO SQL
# ===========================================================================
def test_file_ascii():
    SQL.encode("ascii")


def test_funzioni_presenti():
    for f in ("omega_transitions_step", "omega_transitions_nightly", "omega_transitions_publish",
              "omega_transitions_unpublish", "omega_transitions_ledger_counts",
              "omega_transitions_compare", "omega_transitions_status", "omega_transitions_schedule"):
        _funzione(f)
    assert re.search(r"omega_transitions_nightly\(\s*p_budget_s\s+integer", CODICE)
    assert re.search(r"p_dry_run\s+boolean DEFAULT false", _funzione("omega_transitions_nightly"))


def test_registro_scritto_nel_passo_con_ledger_on_conflict_che_non_risomma():
    passo = _funzione("omega_transitions_step")
    # il registro si scrive nella STESSA funzione dei conteggi
    assert "INSERT INTO public.omega_transitions_ledger" in passo
    assert "INSERT INTO public.omega_minute_transitions_raw" in passo
    assert "INSERT INTO public.omega_ht_ft_transitions_raw" in passo
    assert re.search(r"omega_transitions_ledger AS l.*?ON CONFLICT \(fixture_id\) DO UPDATE", passo, re.S)
    # gia' contata resta contata: coalesce sul valore esistente, mai sovrascritto
    assert "ht_ft_at          = coalesce(l.ht_ft_at, EXCLUDED.ht_ft_at)" in passo
    assert "minute_at         = coalesce(l.minute_at, EXCLUDED.minute_at)" in passo
    # si conta SOLO cio' che il registro non ha: le colonne need_* vengono dal registro
    assert passo.count("LEFT JOIN public.omega_transitions_ledger l ON l.fixture_id = m.fixture_id") == 2
    assert passo.count("(l.ht_ft_at IS NULL) AS need_htft") == 2
    assert "WHERE s.need_htft" in passo and "WHERE f.need_min" in passo
    # il registro riceve TUTTE le partite del lotto: nessun filtro fra il join e l'ON CONFLICT
    coda = passo[passo.index("INSERT INTO public.omega_transitions_ledger AS l"):]
    coda = coda[:coda.index("ON CONFLICT (fixture_id)")]
    assert "FROM pg_temp.omg_fx f" in coda and "WHERE" not in coda
    # stesso lucchetto del giro notturno e della pubblicazione
    assert "pg_advisory_xact_lock(hashtext('omega_transitions'))" in passo


def test_lega_che_supera_la_soglia_copiata_per_intero_dal_grezzo():
    passo = _funzione("omega_transitions_step")
    copia = passo[passo.index("FROM public.omega_minute_transitions_raw r"):]
    assert "JOIN pg_temp.omg_inc i ON i.league_id = r.league_id" in copia
    assert passo.count("AND c.n_minute >= v_min AND c.n_minute - i.d_minute < v_min") == 2


def test_stesse_definizioni_del_costruttore_originale():
    passo = _funzione("omega_transitions_step")
    for frammento in ("m.status_short = 'FT'", "e.event_type = 'Goal'",
                      "coalesce(e.detail, '') <> 'Missed Penalty'", "e.minute BETWEEN 0 AND 90",
                      "generate_series(0, 85, 5)", "s.bucket <= 40",
                      "coalesce(g.gh, 0) = x.fulltime_home", "coalesce(g.ga, 0) = x.fulltime_away"):
        assert frammento in passo, frammento


def test_pubblicato_scritto_come_copia_del_grezzo_non_come_somma():
    passo = _funzione("omega_transitions_step")
    # grezzo: somma; pubblicato: n = n grezzo (EXCLUDED.n), mai n + EXCLUDED.n
    assert passo.count("DO UPDATE SET n = t.n + EXCLUDED.n") == 2
    assert passo.count("DO UPDATE SET n = EXCLUDED.n, built_at = EXCLUDED.built_at") == 3
    assert "public.omega_minute_transitions.n + EXCLUDED.n" not in CODICE
    assert "p.n + EXCLUDED.n" not in CODICE
    assert "WHERE v_published" in passo


def test_delete_sulle_tabelle_dei_bot_solo_nella_pubblicazione_dichiarata():
    for tab in ("omega_minute_transitions", "omega_ht_ft_transitions", "omega_minute_league_counts"):
        dove = _funzioni_con(r"DELETE FROM public\." + tab + r"\s*;")
        assert sorted(dove) == ["omega_transitions_publish", "omega_transitions_unpublish"], (tab, dove)
    # nessun DELETE / TRUNCATE fuori dalle funzioni, e nessun DELETE sul registro o sul grezzo
    fuori_funzioni = re.sub(r"AS \$\$.*?\$\$;", "", CODICE, flags=re.S)
    assert not re.search(r"\b(DELETE FROM|TRUNCATE)\b", fuori_funzioni)
    assert not re.search(r"DELETE FROM public\.omega_(transitions_ledger|minute_transitions_raw|ht_ft_transitions_raw)", CODICE)
    assert "TRUNCATE" not in CODICE


def test_rpc_dei_bot_non_ridefinite():
    assert "FUNCTION public.get_omega_minute_ft" not in CODICE
    assert "FUNCTION public.get_omega_ht_ft" not in CODICE


def test_vecchi_costruttori_spenti():
    for f in ("omega_build_minute_transitions_reset", "omega_build_minute_transitions_step",
              "omega_build_minute_transitions_run", "omega_build_minute_transitions_schedule",
              "omega_build_ht_ft_transitions"):
        corpo = _funzione(f)
        assert "RAISE EXCEPTION 'dismessa il 25/09" in corpo, f
        assert "INSERT" not in corpo and "DELETE" not in corpo, f


def test_pg_cron_idempotente_con_guardia():
    sch = _funzione("omega_transitions_schedule")
    guardia = sch.index("FROM pg_extension WHERE extname = 'pg_cron'")
    unsched = sch.index("PERFORM cron.unschedule('omega_transitions_nightly')")
    sched = sch.index("PERFORM cron.schedule('omega_transitions_nightly', '0 4 * * *'")
    assert guardia < unsched < sched
    assert re.search(r"IF EXISTS \(SELECT 1 FROM cron\.job WHERE jobname = 'omega_transitions_nightly'\) THEN\s+"
                     r"PERFORM cron\.unschedule\('omega_transitions_nightly'\)", sch)
    assert "PERFORM cron.unschedule('omega_minute_build')" in sch
    assert "SET statement_timeout = '20min'; SELECT public.omega_transitions_nightly(600);" in sch
    # la migrazione schedula davvero (una volta, alla fine)
    assert CODICE.count("SELECT public.omega_transitions_schedule(true);") == 1


def test_dry_run_annulla_con_sottotransazione_e_lascia_il_referto():
    nt = _funzione("omega_transitions_nightly")
    assert "RAISE EXCEPTION USING ERRCODE = 'OT001'" in nt
    assert "WHEN SQLSTATE 'OT001' THEN" in nt
    # il referto si scrive DOPO il blocco annullato
    assert nt.index("WHEN SQLSTATE 'OT001'") < nt.index("INSERT INTO public.omega_transitions_runs\n")
    assert "pg_try_advisory_xact_lock(hashtext('omega_transitions'))" in nt


def test_pubblicazione_protetta():
    pub = _funzione("omega_transitions_publish")
    assert "p_confirm IS DISTINCT FROM 'PUBBLICA'" in pub
    assert "v_st.bootstrap_done_at IS NULL AND NOT coalesce(p_force, false)" in pub
    assert "omega_minute_transitions_pre_ledger" in pub


def test_sicurezza_grant():
    assert not re.search(r"GRANT [^;]* TO [^;]*\b(anon|authenticated|public)\b", CODICE)
    for t in ("omega_transitions_ledger", "omega_minute_transitions_raw", "omega_ht_ft_transitions_raw",
              "omega_transitions_league_counts", "omega_transitions_state", "omega_transitions_runs"):
        assert f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY;" in CODICE, t
        assert f"REVOKE ALL ON TABLE public.{t} FROM anon, authenticated;" in CODICE, t
    for m in re.finditer(r"CREATE OR REPLACE FUNCTION public\.(\w+)\(", CODICE):
        corpo = _funzione(m.group(1))
        assert "SECURITY DEFINER SET search_path = public, pg_temp" in corpo, m.group(1)


def _chiavi_jsonb(corpo: str) -> set:
    return set(re.findall(r"'([a-z_0-9]+)',\s", corpo))


def test_chiavi_dello_script_uguali_a_quelle_dell_sql():
    """I finti sotto usano le costanti dello script: qui si prova che sono quelle vere."""
    status = _chiavi_jsonb(_funzione("omega_transitions_status"))
    assert set(V.CHIAVI_STATUS) <= status, set(V.CHIAVI_STATUS) - status
    reg = _chiavi_jsonb(_funzione("omega_transitions_ledger_counts"))
    assert set(V.CHIAVI_REGISTRO) <= reg, set(V.CHIAVI_REGISTRO) - reg
    cmp = _chiavi_jsonb(_funzione("omega_transitions_compare"))
    assert set(V.CHIAVI_CONFRONTO) <= cmp, set(V.CHIAVI_CONFRONTO) - cmp

    def colonne(tab: str) -> set:
        blocco = CODICE[CODICE.index(f"CREATE TABLE IF NOT EXISTS public.{tab} ("):]
        blocco = blocco[:blocco.index(");")]
        return set(re.findall(r"^\s+([a-z_]+)\s+[A-Z]", blocco, re.M))
    assert set(V.COLONNE_STATE) <= colonne("omega_transitions_state")
    assert set(V.COLONNE_RUN) <= colonne("omega_transitions_runs")
    assert {"league_id", "n_minute", "n_ht_ft"} <= colonne("omega_transitions_league_counts")


# ===========================================================================
# 2. SCRIPT DI VERIFICA con finto Supabase
# ===========================================================================
class _Resp:
    def __init__(self, data: Any, count: Optional[int] = None) -> None:
        self.data = data
        self.count = count


class _Q:
    MAX = 1000   # max-rows di PostgREST

    def __init__(self, db: "FintoSB", tabella: str) -> None:
        self.db, self.t = db, tabella
        self.cols: List[str] = []
        self.count: Optional[str] = None
        self.filtri: List = []
        self.ordini: List = []
        self.a: Optional[int] = None
        self.b: Optional[int] = None
        self.lim: Optional[int] = None

    def select(self, cols: str, count: Optional[str] = None) -> "_Q":
        self.cols = [c.strip() for c in cols.split(",")]
        self.count = count
        return self

    def eq(self, c, v):
        self.filtri.append(lambda r: r[c] == v)
        return self

    def lte(self, c, v):
        self.filtri.append(lambda r: r[c] is not None and r[c] <= v)
        return self

    def order(self, c, desc: bool = False):
        self.ordini.append((c, desc))
        return self

    def range(self, a, b):
        self.a, self.b = a, b
        return self

    def limit(self, n):
        self.lim = n
        return self

    def execute(self) -> _Resp:
        self.db.chiamate.append(self.t)
        righe = self.db.tabelle[self.t]
        for c in self.cols:                                   # colonna inesistente = errore, come PostgREST
            if righe and c not in righe[0]:
                raise KeyError(f"column {self.t}.{c} does not exist")
        righe = [r for r in righe if all(f(r) for f in self.filtri)]
        for c, desc in reversed(self.ordini):
            righe = sorted(righe, key=lambda r: (r[c] is None, r[c]), reverse=desc)
        tot = len(righe)
        if self.a is not None:
            righe = righe[self.a:self.b + 1]
        if self.lim is not None:
            righe = righe[:self.lim]
        righe = righe[:self.MAX]
        return _Resp([{c: r[c] for c in self.cols} for r in righe], tot if self.count == "exact" else None)


class _R:
    def __init__(self, dati):
        self.dati = dati

    def execute(self):
        return _Resp(self.dati)


class FintoSB:
    def __init__(self) -> None:
        self.tabelle: Dict[str, List[dict]] = {}
        self.rpcs: Dict[str, Any] = {}
        self.chiamate: List[str] = []
        self.rpc_chiamate: List = []

    def table(self, t):
        return _Q(self, t)

    def rpc(self, nome, params):
        self.rpc_chiamate.append((nome, params))
        dati = self.rpcs[nome]
        return _R(dati(params) if callable(dati) else dati)


OGGI = "2026-09-26T04:00:05+00:00"


def _mondo(leghe: Dict[int, int], soglia: int = 1000, pubblicata: bool = True, righe_ht_per_lega: int = 1) -> FintoSB:
    """Mondo COERENTE: leghe {league_id: partite}, piu' il globale 0.
    Bucket 0 ft: ogni partita in una cella '0-0' -> risultato (ripartite su 3 celle).
    HT-FT: ``righe_ht_per_lega`` celle per lega (per esercitare la paginazione)."""
    sb = FintoSB()
    tot = sum(leghe.values())

    def celle_min(lg, n):
        out = []
        resti = [n - 2 * (n // 3), n // 3, n // 3]
        for k, v in enumerate(resti):
            if v > 0:
                out.append({"league_id": lg, "bucket": 0, "score": "0-0", "target": "ft",
                            "result": f"{k}-0", "n": v, "built_at": OGGI})
        out.append({"league_id": lg, "bucket": 45, "score": "0-0", "target": "ft",
                    "result": "0-0", "n": max(1, n // 2), "built_at": OGGI})
        return out

    def celle_ht(lg, n):
        k = max(1, min(righe_ht_per_lega, n))
        base, resto = divmod(n, k)
        return [{"league_id": lg, "ht": f"{i}-0", "ft": f"{i}-{j}", "n": base + (1 if i * 50 + j < resto else 0),
                 "built_at": OGGI}
                for i in range(k // 50 + 1) for j in range(50) if i * 50 + j < k]

    raw_min, raw_ht = celle_min(0, tot), celle_ht(0, tot)
    for lg, n in leghe.items():
        raw_min += celle_min(lg, n)
        raw_ht += celle_ht(lg, n)
    sb.tabelle[V.T_MIN_RAW] = raw_min
    sb.tabelle[V.T_HT_RAW] = raw_ht
    ammesse = {lg for lg, n in leghe.items() if n >= soglia}
    if pubblicata:
        sb.tabelle[V.T_MIN] = [dict(r) for r in raw_min if r["league_id"] == 0 or r["league_id"] in ammesse]
        sb.tabelle[V.T_HT] = [dict(r) for r in raw_ht]
        sb.tabelle[V.T_LEGHE_PUB] = [{"league_id": lg, "n": n} for lg, n in leghe.items()]
    else:
        sb.tabelle[V.T_MIN] = [{**r, "built_at": "2026-09-11T11:16:00+00:00"} for r in celle_min(0, tot - 5)]
        sb.tabelle[V.T_HT] = [{**r, "built_at": "2026-09-11T09:53:00+00:00"} for r in celle_ht(0, tot - 5)]
        sb.tabelle[V.T_LEGHE_PUB] = [{"league_id": lg, "n": n - 1} for lg, n in leghe.items()]
    sb.tabelle[V.T_CONTATORI] = ([{"league_id": 0, "n_minute": tot, "n_ht_ft": tot, "updated_at": OGGI}]
                                 + [{"league_id": lg, "n_minute": n, "n_ht_ft": n, "updated_at": OGGI}
                                    for lg, n in leghe.items()])
    registro = ([{"league_id": 0, "n_minute": tot, "n_ht_ft": tot, "n_rejected_open": 7}]
                + [{"league_id": lg, "n_minute": n, "n_ht_ft": n, "n_rejected_open": 0}
                   for lg, n in sorted(leghe.items())])
    sb.rpcs["omega_transitions_ledger_counts"] = registro
    run = {"id": 12, "started_at": OGGI, "finished_at": OGGI, "elapsed_s": 4.2, "dry_run": False,
           "status": "ok", "published": pubblicata, "steps": 3, "scanned": 610, "ht_ft_counted": 600,
           "minute_counted": 540, "minute_rejected": 60, "hot_candidates": 610,
           "hot_skipped_no_index": False, "id_cursor_from": 1627000, "id_cursor_to": 1627544,
           "max_id": 1627544, "sweep_from": 0, "sweep_to": 100000, "live_minute_upserts": 3000,
           "live_ht_ft_upserts": 700, "new_leagues": 0, "error": None, "params": {"budget_s": 600}}
    run2 = {**run, "id": 13, "scanned": 0, "ht_ft_counted": 0, "minute_counted": 0, "minute_rejected": 0,
            "live_minute_upserts": 0, "live_ht_ft_upserts": 0}
    sb.rpcs["omega_transitions_status"] = {
        "state": {"id": 1, "id_cursor": 1627544, "sweep_cursor": 100000, "sweep_cycles": 0,
                  "bootstrap_started_at": "2026-09-26T04:00:01+00:00",
                  "bootstrap_done_at": "2026-09-26T04:09:00+00:00",
                  "published_at": "2026-09-26T10:00:00+00:00" if pubblicata else None,
                  "min_league_matches": soglia, "updated_at": OGGI},
        "runs": [run2, run], "pg_cron": True,
        "cron_jobs": [{"jobname": "omega_transitions_nightly", "schedule": "0 4 * * *",
                       "command": "SET statement_timeout = '20min'; SELECT public.omega_transitions_nightly(600);",
                       "active": True}],
        "cron_last_runs": [{"status": "succeeded", "start_time": OGGI, "end_time": OGGI, "return_message": "1 row"}],
        "index_matches_fixture_date": True, "index_match_events_goal": True, "backup_pre_ledger": pubblicata,
        "league_counts_global": {"league_id": 0, "n_minute": tot, "n_ht_ft": tot, "updated_at": OGGI},
        "now": OGGI}
    cmp_vuoto = {k: 0 for k in V.CHIAVI_CONFRONTO}
    sb.rpcs["omega_transitions_compare"] = lambda p: {"mode": p["p_mode"], "min_league_matches": soglia,
                                                      "minute": dict(cmp_vuoto, cells_old=10, cells_new=12),
                                                      "ht_ft": dict(cmp_vuoto)}
    return sb


LEGHE = {39: 5000, 135: 4200, 140: 1000, 207: 999, 333: 12}   # 140 sul bordo della soglia


def _esegui(sb, argv=()) -> str:
    out = io.StringIO()
    assert V.main(list(argv), sb=sb, out=out) == 0
    return out.getvalue()


def test_mondo_coerente_numeri_a_zero():
    sb = _mondo(LEGHE)
    n = V.raccogli(sb)
    assert n["A_grezzo_minuto"]["leghe_diverse"] == []
    assert n["A_pubblicato_minuto"]["leghe_diverse"] == []
    assert n["A_grezzo_ht_ft"]["leghe_diverse"] == []
    assert n["A_pubblicato_ht_ft"]["leghe_diverse"] == []
    assert n["A_grezzo_minuto"]["leghe_confrontate"] == 6                   # 5 leghe + globale
    assert n["A_pubblicato_minuto"]["globale_somma_b0"] == sum(LEGHE.values())
    assert n["B_celle_n_non_positivo"] == {V.T_MIN: 0, V.T_MIN_RAW: 0, V.T_HT: 0, V.T_HT_RAW: 0}
    assert n["C_built_at_max"][V.T_MIN] == OGGI
    d = n["D_leghe"]
    assert (d["pubblicate"], d["ammesse_dal_registro"]) == (3, 3)
    assert d["pubblicate_non_ammesse"] == [] and d["ammesse_non_pubblicate"] == []
    assert (d["min_partite_fra_pubblicate"], d["max_partite_fra_escluse"]) == (1000, 999)
    assert n["E_contatori"] == {"minuto_leghe_diverse": [], "ht_ft_leghe_diverse": [], "pubblicati_leghe_diverse": []}
    assert [g["minute_counted"] for g in n["F_giri"]] == [0, 540]
    testo = _esegui(sb)
    assert "leghe diverse 0" in testo and "B celle con n <= 0 (atteso 0): omega_minute_transitions=0" in testo


def test_somma_sbagliata_di_una_lega_si_vede_col_numero():
    sb = _mondo(LEGHE)
    for r in sb.tabelle[V.T_MIN]:
        if r["league_id"] == 135 and r["bucket"] == 0:
            r["n"] += 1                                                     # doppio conteggio di una partita
            break
    n = V.raccogli(sb)
    assert n["A_pubblicato_minuto"]["leghe_diverse"] == [(135, 4200, 4201)]
    assert n["A_grezzo_minuto"]["leghe_diverse"] == []
    assert "lega 135: atteso 4200 visto 4201" in _esegui(sb)


def test_celle_negative_e_lega_sotto_soglia_pubblicata():
    sb = _mondo(LEGHE)
    sb.tabelle[V.T_HT_RAW][3]["n"] = -2
    sb.tabelle[V.T_MIN].append({"league_id": 333, "bucket": 0, "score": "0-0", "target": "ft",
                                "result": "0-0", "n": 12, "built_at": OGGI})
    n = V.raccogli(sb)
    assert n["B_celle_n_non_positivo"][V.T_HT_RAW] == 1
    assert n["D_leghe"]["pubblicate_non_ammesse"] == [333]
    assert n["D_leghe"]["min_partite_fra_pubblicate"] == 12


def test_contatori_diversi_dal_registro():
    sb = _mondo(LEGHE)
    sb.tabelle[V.T_CONTATORI][2]["n_minute"] -= 3                            # lega 135
    sb.tabelle[V.T_LEGHE_PUB][0]["n"] += 1                                   # lega 39
    n = V.raccogli(sb)
    assert n["E_contatori"]["minuto_leghe_diverse"] == [(135, 4200, 4197)]
    assert n["E_contatori"]["pubblicati_leghe_diverse"] == [(39, 5000, 5001)]


def test_paginazione_oltre_mille_righe():
    """2.600 celle HT-FT pubblicate: senza paginazione le somme sarebbero sbagliate."""
    sb = _mondo({39: 3000, 135: 2000}, righe_ht_per_lega=1300)
    assert len(sb.tabelle[V.T_HT]) > 2 * _Q.MAX
    n = V.raccogli(sb)
    assert n["A_pubblicato_ht_ft"]["leghe_diverse"] == []
    assert n["A_pubblicato_ht_ft"]["globale_somma"] == 5000
    assert sb.chiamate.count(V.T_HT) >= 3


def test_non_pubblicata_i_controlli_sul_pubblicato_non_sono_misurati():
    sb = _mondo(LEGHE, pubblicata=False)
    n = V.raccogli(sb)
    assert n["pubblicata"] is False
    assert n["A_pubblicato_minuto"]["leghe_diverse"] is None
    assert n["E_contatori"]["pubblicati_leghe_diverse"] is None
    assert n["A_grezzo_minuto"]["leghe_diverse"] == []
    assert n["C_built_at_max"][V.T_MIN] == "2026-09-11T11:16:00+00:00"
    assert "non misurato (tabella non pubblicata)" in _esegui(sb)


def test_confronto_chiama_la_rpc_col_modo_e_stampa_le_chiavi():
    sb = _mondo(LEGHE)
    testo = _esegui(sb, ["--confronto", "pre"])
    assert ("omega_transitions_compare", {"p_mode": "pre"}) in sb.rpc_chiamate
    assert "confronto pre (soglia 1000):" in testo and "cells_lower=0" in testo and "cells_new=12" in testo


def test_impronta_secondo_giro_zero_variazioni_poi_una_partita(tmp_path):
    sb = _mondo(LEGHE)
    f = str(tmp_path / "imp.json")
    _esegui(sb, ["--salva-impronta", f])
    testo = _esegui(sb, ["--confronta-impronta", f])
    assert "impronta pub_min_b0: leghe_prima=4, leghe_dopo=4, leghe_cambiate=0, delta_totale=0" in testo
    # una partita in piu' nella lega 39 (grezzo + pubblicato + registro)
    for t in (V.T_MIN, V.T_MIN_RAW):
        for r in sb.tabelle[t]:
            if r["league_id"] in (0, 39) and r["bucket"] == 0 and r["result"] == "0-0":
                r["n"] += 1
    for r in sb.rpcs["omega_transitions_ledger_counts"]:
        if r["league_id"] in (0, 39):
            r["n_minute"] += 1
    testo = _esegui(sb, ["--confronta-impronta", f])
    assert "impronta pub_min_b0: leghe_prima=4, leghe_dopo=4, leghe_cambiate=2, delta_totale=2, delta_negativi=0" in testo
    assert "impronta registro_min: leghe_prima=6, leghe_dopo=6, leghe_cambiate=2, delta_totale=2" in testo
    assert json.load(open(f, encoding="utf-8"))["pub_min_b0"]["39"] == 5000


def test_script_solo_lettura_e_ascii():
    src = open(V.__file__, encoding="utf-8").read()
    src.encode("ascii")
    assert not re.search(r"\)\s*\.(insert|upsert|update|delete)\(", src)   # nessuna scrittura PostgREST
    for vietato in ("omega_transitions_nightly\"", "omega_transitions_publish", "omega_transitions_unpublish",
                    "omega_transitions_schedule"):
        assert vietato not in src, vietato
    sb = _mondo(LEGHE)
    V.raccogli(sb, confronto="post")
    assert {n for n, _ in sb.rpc_chiamate} == {"omega_transitions_status", "omega_transitions_ledger_counts",
                                               "omega_transitions_compare"}
