"""test_actions_pipeline_paginazione.py -- i tre step della pipeline analytics che
fallivano ogni giorno in silenzio (57014 / ReadTimeout):

  1) enrich_analytics_snapshots: flush staging a FETTE invece di un UPDATE unico
     per lega  -> stesso stato finale, nessuna lega persa;
  2) build_direzione: lettura di bet_features in KEYSET invece che in OFFSET
     profondo -> stesso insieme di righe, stesso DataFrame;
  3) refresh_analytics_bets: RPC chiamata a finestre di UN giorno -> stesso stato
     finale di una chiamata unica;
  + build_analytics_signals / merge_engine_signals: paginazione con ORDER BY su
     chiave unica invece di OFFSET senza ordine.

I FINTI hanno le IDENTICHE chiavi e tipi del vero:
  - gli errori sono `postgrest.exceptions.APIError` costruiti col dict reale
    {'message','code','hint','details'} (code str per gli errori SQL, int per i
    5xx del gateway, come fa postgrest.exceptions.generate_default_error_message);
  - le righe hanno le colonne reali con i tipi reali (fixture_id/id bigint -> int,
    market/selection text -> str, freq_* numeric -> float, delay_current int,
    kickoff timestamptz -> stringa ISO);
  - la RPC `flush_analytics_snap_staging` e' riprodotta 1:1 dal SQL
    (migrations/analytics_snap_staging.sql): UPDATE scopato alla lega + DELETE
    delle SOLE chiavi della lega, e su statement timeout la transazione non
    lascia traccia;
  - il finto PostgREST riproduce il rischio vero: senza ORDER BY l'ordine di
    ritorno NON e' garantito fra una pagina e l'altra, e FRA PARI (stesso valore
    della colonna di ordinamento) nemmeno con ORDER BY.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_analytics_signals as bas
import build_direzione as bd
import db_client
import enrich_analytics_snapshots as en
import merge_engine_signals as mes
import refresh_analytics_bets as rab

_SNAP_COLS = ("freq_baseline", "freq_current", "freq_deviation",
              "delay_current", "delay_record", "delay_avg")


# ---------------------------------------------------------------- errori veri
def api_error(code, message: str, hint=None, details=None) -> APIError:
    """APIError con le IDENTICHE chiavi del vero."""
    return APIError({"message": message, "code": code, "hint": hint, "details": details})


def err_57014() -> APIError:
    return api_error("57014", "canceling statement due to statement timeout")


def err_503() -> APIError:
    """5xx del gateway: postgrest mette lo STATUS INT in 'code'."""
    return APIError({"message": "JSON could not be generated", "code": 503,
                     "hint": "Refer to full message for details",
                     "details": "b'<html>503 Service Unavailable</html>'"})


def err_23505() -> APIError:
    return api_error("23505", 'duplicate key value violates unique constraint '
                              '"analytics_signals_signal_uid_key"')


def err_504() -> APIError:
    """FORMA REALE (run 35837906029, 23/09, finestre 18/09/20/09/22/09):
    postgrest mette lo STATUS INT in 'code', il messaggio e' quello generico di
    PostgREST quando il gateway non riesce a generare la risposta."""
    return APIError({"message": "JSON could not be generated", "code": 504,
                     "hint": "Refer to full message for details",
                     "details": "b'upstream request timeout'"})


# ------------------------------------------------------------- finto PostgREST
class FakeResp:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Not:
    def __init__(self, q):
        self.q = q

    def is_(self, col, val):
        assert val == "null"
        self.q.filters.append(("notnull", col, None))
        return self.q


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.cols = "*"
        self.filters = []
        self.orders = []
        self._limit = None
        self._range = None
        self._upsert = None
        self._delete = False
        self._count = None
        self.not_ = _Not(self)

    # ---- costruzione query
    def select(self, cols="*", count=None, **kw):
        self.cols = cols
        self._count = count
        return self

    def delete(self, **kw):
        self._delete = True
        return self

    def eq(self, c, v):
        self.filters.append(("eq", c, v)); return self

    def in_(self, c, vals):
        self.filters.append(("in", c, list(vals))); return self

    def gte(self, c, v):
        self.filters.append(("gte", c, v)); return self

    def gt(self, c, v):
        self.filters.append(("gt", c, v)); return self

    def lt(self, c, v):
        self.filters.append(("lt", c, v)); return self

    def order(self, c, desc=False, **kw):
        self.orders.append((c, desc)); return self

    def limit(self, n):
        self._limit = n; return self

    def range(self, a, b):
        self._range = (a, b); return self

    def upsert(self, rows, on_conflict=None, **kw):
        self._upsert = (rows, on_conflict); return self

    # ---- esecuzione
    def _match(self, r) -> bool:
        for kind, c, v in self.filters:
            x = r.get(c)
            if kind == "eq" and x != v:
                return False
            if kind == "in" and x not in v:
                return False
            if kind == "gte" and not (x is not None and x >= v):
                return False
            if kind == "gt" and not (x is not None and x > v):
                return False
            if kind == "lt" and not (x is not None and x < v):
                return False
            if kind == "notnull" and x is None:
                return False
        return True

    def execute(self):
        if self._upsert is not None:
            return self._esegui_upsert()
        if self._delete:
            return self._esegui_delete()
        self.db.n_select += 1
        if self.db.select_hook:
            self.db.select_hook(self)
        rows = [dict(r) for r in self.db.tables.get(self.table, []) if self._match(r)]
        totale = len(rows)
        rows = self.db.ordina(rows, self.orders)
        if self._range is not None:
            rows = rows[self._range[0]:self._range[1] + 1]
        elif self._limit is not None:
            rows = rows[:self._limit]
        if self.db.cap is not None:
            rows = rows[:self.db.cap]
        if self.cols != "*":
            keys = [c.strip() for c in self.cols.split(",")]
            rows = [{k: r.get(k) for k in keys} for r in rows]
        return FakeResp(rows, count=totale if self._count == "exact" else None)

    def _esegui_delete(self):
        """DELETE con i filtri applicati (PostgREST cancella le righe che
        combaciano). Conta le esecuzioni: serve a provare che il delete degli
        stale NON parte se un upsert e' fallito."""
        self.db.n_delete += 1
        if self.db.delete_hook:
            self.db.delete_hook(self.table, self.filters)
        resta, tolte = [], []
        for r in self.db.tables.get(self.table, []):
            (tolte if self._match(r) else resta).append(r)
        self.db.tables[self.table] = resta
        return FakeResp(tolte)

    def _esegui_upsert(self):
        rows, conflict = self._upsert
        self.db.n_upsert += 1
        self.db.upsert_sizes.append(len(rows))
        if self.db.upsert_hook:
            self.db.upsert_hook(self.table, rows)
        keycols = [c.strip() for c in conflict.split(",")]
        viste = set()
        for r in rows:
            k = tuple(r[c] for c in keycols)
            if k in viste:   # come Postgres: ON CONFLICT non puo' toccare 2 volte la stessa riga
                raise api_error("21000", "ON CONFLICT DO UPDATE command cannot affect "
                                         "row a second time")
            viste.add(k)
        dest = self.db.tables.setdefault(self.table, [])
        idx = {tuple(r[c] for c in keycols): r for r in dest}
        for r in rows:
            k = tuple(r[c] for c in keycols)
            if k in idx:
                idx[k].update(r)
            else:
                nuova = dict(r)
                dest.append(nuova)
                idx[k] = nuova
        return FakeResp([dict(r) for r in rows])


class FakeRpc:
    def __init__(self, db, name, params):
        self.db, self.name, self.params = db, name, params

    def execute(self):
        self.db.n_rpc += 1
        self.db.rpc_calls.append((self.name, dict(self.params)))
        return FakeResp(self.db.rpc_impl[self.name](self.db, self.params))


class _Session:
    timeout = None


class _Postgrest:
    def __init__(self):
        self.session = _Session()


class FakeDB:
    """Finto PostgREST: tabelle in memoria, cap del server, ordine dei PARI non
    garantito (come il vero), hook per iniettare errori."""

    def __init__(self, tables=None, cap=None, max_flush=None):
        self.tables = tables or {}
        self.cap = cap                 # PostgREST max-rows (None = nessun cap)
        self.max_flush = max_flush     # righe in staging oltre cui l'UPDATE va in 57014
        self.n_select = self.n_upsert = self.n_rpc = self.n_delete = 0
        self.upsert_sizes = []
        self.rpc_calls = []
        self.select_hook = None
        self.upsert_hook = None
        self.delete_hook = None
        self.rpc_impl = {"flush_analytics_snap_staging": flush_analytics_snap_staging}
        self.postgrest = _Postgrest()

    # il client: table()/rpc() come supabase-py
    def table(self, name):
        return FakeQuery(self, name)

    def rpc(self, name, params):
        return FakeRpc(self, name, params)

    def ordina(self, rows, orders):
        if not orders:
            # nessun ORDER BY -> l'ordine di ritorno NON e' garantito fra le pagine
            if not rows:
                return rows
            k = self.n_select % len(rows)
            return rows[k:] + rows[:k]
        for col, desc in reversed(orders):
            rows.sort(key=lambda r: (r[col] is None, r[col]), reverse=desc)
        cols = [c for c, _ in orders]
        out, i = [], 0
        while i < len(rows):
            j = i
            chiave = tuple(rows[i][c] for c in cols)
            while j < len(rows) and tuple(rows[j][c] for c in cols) == chiave:
                j += 1
            grp = rows[i:j]
            k = self.n_select % len(grp)      # PARI: ordine non garantito
            out.extend(grp[k:] + grp[:k])
            i = j
        return out


def flush_analytics_snap_staging(db: FakeDB, params: dict) -> int:
    """Copia 1:1 di migrations/analytics_snap_staging.sql:58.
    UPDATE analytics_signals ... FROM analytics_snap_staging (scopato alla lega),
    poi DELETE dalla staging delle SOLE chiavi che combaciano con la lega.
    Su statement timeout la transazione e' annullata: niente update, niente delete."""
    lid = params["p_league_id"]
    stg = db.tables.get("analytics_snap_staging", [])
    sig = db.tables.get("analytics_signals", [])
    if db.max_flush is not None and len(stg) > db.max_flush:
        raise err_57014()
    idx = {(s["fixture_id"], s["market"], s["selection"]): s for s in stg}
    updated = 0
    for s in sig:
        if s.get("league_id") != lid:
            continue
        st = idx.get((s["fixture_id"], s["market"], s["selection"]))
        if st is None:
            continue
        for c in _SNAP_COLS:
            s[c] = st[c]
        s["updated_at"] = "2026-09-21T03:30:00+00:00"
        updated += 1
    chiavi_lega = {(s["fixture_id"], s["market"], s["selection"])
                   for s in sig if s.get("league_id") == lid}
    db.tables["analytics_snap_staging"] = [
        st for st in stg
        if (st["fixture_id"], st["market"], st["selection"]) not in chiavi_lega]
    return updated


@pytest.fixture(autouse=True)
def niente_attese(monkeypatch):
    """I backoff non devono rallentare i test (la logica di retry resta quella vera)."""
    for mod in (en, bd, bas, mes, rab):
        monkeypatch.setattr(mod.time, "sleep", lambda *_a, **_k: None, raising=False)


# ============================================================================
# 1) enrich_analytics_snapshots: flush a FETTE
# ============================================================================
MERCATI = [("over_2_5", "Over"), ("over_2_5", "Under"), ("btts", "Yes"), ("btts", "No")]
MOTORI = ("poisson", "ml", "tacticai")


def _dati_lega(league_id: int, n_fixture: int, primo_id: int = 1):
    """analytics_signals reale: UNA riga per (engine, fixture, market, selection).
    Ritorna (righe_signals, righe_staging)."""
    signals, stage, rid = [], [], primo_id
    for i in range(n_fixture):
        fid = 1500000 + i
        for market, selection in MERCATI:
            for eng in MOTORI:
                signals.append({
                    "id": rid, "signal_uid": f"{eng}|{fid}|{market}|{selection}",
                    "engine": eng, "fixture_id": fid, "league_id": league_id,
                    "market": market, "selection": selection,
                    "freq_baseline": None, "freq_current": None, "freq_deviation": None,
                    "delay_current": None, "delay_record": None, "delay_avg": None,
                    "updated_at": None,
                })
                rid += 1
            stage.append({
                "fixture_id": fid, "market": market, "selection": selection,
                "freq_baseline": 0.51, "freq_current": 0.6, "freq_deviation": 0.09,
                "delay_current": 3, "delay_record": 11, "delay_avg": 4.2,
            })
    return signals, stage


def _flush_unico(sb, league_id, stage_rows, counters):
    """IL VECCHIO _flush_staging (pre-fix): upsert a batch di 500 + UN SOLO flush
    per lega. Serve come riferimento di equivalenza e come falsificazione."""
    if not stage_rows:
        return 0
    for i in range(0, len(stage_rows), 500):
        chunk = stage_rows[i:i + 500]
        for attempt in range(3):
            try:
                (sb.table("analytics_snap_staging")
                 .upsert(chunk, on_conflict="fixture_id,market,selection").execute())
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 2:
                    counters["failed"] += len(chunk)
    for attempt in range(3):
        try:
            res = sb.rpc("flush_analytics_snap_staging", {"p_league_id": league_id}).execute()
            return res.data if isinstance(res.data, int) else 0
        except Exception:  # noqa: BLE001
            if attempt == 2:
                counters["failed"] += len(stage_rows)
                return 0
    return 0


def test_flush_a_fette_stato_finale_identico_al_flush_unico():
    """EQUIVALENZA: con DB sano, fette e flush unico lasciano analytics_signals
    IDENTICO (riga per riga) e contano le stesse righe aggiornate."""
    sig_a, stage = _dati_lega(129, 200)
    sig_b, _ = _dati_lega(129, 200)
    db_fette = FakeDB({"analytics_signals": sig_a, "analytics_snap_staging": []})
    db_unico = FakeDB({"analytics_signals": sig_b, "analytics_snap_staging": []})

    c1, c2 = {"failed": 0}, {"failed": 0}
    upd_fette = en._flush_staging(db_fette, 129, stage, c1)
    upd_unico = _flush_unico(db_unico, 129, stage, c2)

    assert c1["failed"] == 0 and c2["failed"] == 0
    assert upd_fette == upd_unico == 200 * len(MERCATI) * len(MOTORI)
    assert db_fette.tables["analytics_signals"] == db_unico.tables["analytics_signals"]
    assert db_fette.tables["analytics_snap_staging"] == []      # staging ripulita
    assert db_fette.n_rpc > 1                                    # davvero a fette


def test_flush_a_fette_salva_la_lega_grande_dove_il_flush_unico_la_perde():
    """IL BUG VERO: la lega grande supera lo statement_timeout in un colpo solo.
    A fette passa tutto; col flush unico la lega resta NON aggiornata."""
    sig_a, stage = _dati_lega(129, 200)       # 800 chiavi, 2400 righe-segnale
    sig_b, _ = _dati_lega(129, 200)
    db_fette = FakeDB({"analytics_signals": sig_a, "analytics_snap_staging": []},
                      max_flush=500)
    db_unico = FakeDB({"analytics_signals": sig_b, "analytics_snap_staging": []},
                      max_flush=500)

    c1, c2 = {"failed": 0}, {"failed": 0}
    upd_fette = en._flush_staging(db_fette, 129, stage, c1)
    upd_unico = _flush_unico(db_unico, 129, stage, c2)

    assert c1["failed"] == 0
    assert upd_fette == 200 * len(MERCATI) * len(MOTORI)
    assert all(s["freq_current"] == 0.6 for s in db_fette.tables["analytics_signals"])
    # vecchio metodo: 57014 -> nessuna riga scritta, tutte contate come perse
    assert upd_unico == 0 and c2["failed"] == len(stage)
    assert all(s["freq_current"] is None for s in db_unico.tables["analytics_signals"])


def test_flush_lega_senza_righe_non_chiama_la_rpc():
    db = FakeDB({"analytics_signals": [], "analytics_snap_staging": []})
    c = {"failed": 0}
    assert en._flush_staging(db, 7, [], c) == 0
    assert db.n_rpc == 0 and c["failed"] == 0


def test_flush_che_non_riesce_conta_le_righe_dimezza_e_abbandona_la_lega():
    """Nessun errore ingoiato: le righe non scritte finiscono nel contatore
    (-> exit != 0) e la fetta si dimezza per le leghe successive."""
    sig, stage = _dati_lega(129, 50)
    db = FakeDB({"analytics_signals": sig, "analytics_snap_staging": []}, max_flush=0)
    c, stato = {"failed": 0}, {"size": en._FLUSH_SLICE}
    upd = en._flush_staging(db, 129, stage, c, stato)
    assert upd == 0
    assert c["failed"] == len(stage)                 # TUTTE le righe della lega
    assert stato["size"] == en._FLUSH_SLICE // 2     # fetta adattiva
    assert all(s["freq_current"] is None for s in db.tables["analytics_signals"])


def test_flush_ritenta_il_transitorio_e_poi_riesce():
    sig, stage = _dati_lega(140, 10)
    db = FakeDB({"analytics_signals": sig, "analytics_snap_staging": []})
    stato = {"n": 0}
    vero = db.rpc_impl["flush_analytics_snap_staging"]

    def instabile(d, p):
        stato["n"] += 1
        if stato["n"] <= 2:
            raise err_503()          # 5xx del gateway: code INT
        return vero(d, p)

    db.rpc_impl["flush_analytics_snap_staging"] = instabile
    c = {"failed": 0}
    upd = en._flush_staging(db, 140, stage, c)
    assert c["failed"] == 0 and upd == 10 * len(MERCATI) * len(MOTORI)
    assert stato["n"] == 3           # due tentativi falliti, il terzo passa


def test_upsert_staging_errore_logico_non_si_ritenta():
    db = FakeDB({"analytics_signals": [], "analytics_snap_staging": []})
    tentativi = {"n": 0}

    def hook(table, rows):
        tentativi["n"] += 1
        raise api_error("23502", 'null value in column "market" violates not-null constraint')

    db.upsert_hook = hook
    c = {"failed": 0}
    assert en._upsert_stage(db, [{"fixture_id": 1, "market": "btts", "selection": "Yes"}], c) is False
    assert tentativi["n"] == 1 and c["failed"] == 1


def test_is_transient_riconosce_le_forme_vere():
    assert en._is_transient(err_57014())
    assert en._is_transient(err_503())                       # code int
    assert en._is_transient(httpx.ReadTimeout("timed out"))
    assert en._is_transient(httpx.ConnectError("boom"))
    assert en._is_transient(api_error("PGRST002", "Could not query the database for the schema cache"))
    assert not en._is_transient(err_23505())
    assert not en._is_transient(api_error("42703", 'column "pippo" does not exist'))


# ============================================================================
# 2) build_direzione: lettura keyset di bet_features
# ============================================================================
MERCATI_BD = [("1x2", "H"), ("1x2", "D"), ("1x2", "A"), ("btts", "Yes"), ("btts", "No")]


def _righe_bet_features(n_fixture: int):
    out = []
    for i in range(n_fixture):
        fid = 1400000 + i
        for market, selection in MERCATI_BD:
            out.append({
                "fixture_id": fid, "league_id": 135 + (i % 3), "market": market,
                "selection": selection, "hit": bool(i % 2),
                "poisson_prob": 0.41, "ml_prob": 0.39, "tacticai_prob": 0.44,
                "settled": True,
            })
    return out


def _vecchio_load(sb, page: int) -> list[dict]:
    """IL VECCHIO load() (pre-fix): OFFSET che avanza di quanto ricevuto."""
    cols = "league_id,market,selection,hit,poisson_prob,ml_prob,tacticai_prob"
    rows, start = [], 0
    while True:
        d = (sb.table("bet_features").select(cols)
             .eq("settled", True).in_("market", bd.CAL_MARKETS)
             .order("fixture_id").range(start, start + page - 1).execute().data)
        rows.extend(d)
        if not d:
            break
        start += len(d)
    return rows


def _conta(righe, chiavi=("fixture_id", "market", "selection")):
    from collections import Counter
    return Counter(tuple(r[k] for k in chiavi) for r in righe)


def test_load_keyset_legge_esattamente_tutte_le_righe(monkeypatch):
    righe = _righe_bet_features(37)
    db = FakeDB({"bet_features": righe})
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: db)
    monkeypatch.setattr(bd, "PAGE", 18)   # NON multiplo del gruppo: i blocchi tagliano i PARI
    monkeypatch.setattr(bd, "PAGE_MIN", 5)

    df = bd.load()
    assert len(df) == len(righe)
    assert list(df.columns) == ["league_id", "market", "selection", "hit",
                                "poisson_prob", "ml_prob", "tacticai_prob"]
    atteso = _conta(righe, ("fixture_id",))
    letto = {}
    for _, r in df.iterrows():
        letto[(r["market"], r["selection"])] = letto.get((r["market"], r["selection"]), 0) + 1
    assert sum(atteso.values()) == len(df)
    assert all(v == 37 for v in letto.values())     # ogni (mercato,selezione) 37 volte


def test_vecchio_offset_perde_o_duplica_righe_con_i_pari(monkeypatch):
    """FALSIFICAZIONE: sullo STESSO finto, il vecchio OFFSET non ritorna l'insieme
    corretto (l'ordine fra righe con lo stesso fixture_id non e' garantito)."""
    righe = _righe_bet_features(37)
    db = FakeDB({"bet_features": righe})
    vecchio = _vecchio_load(db, 18)
    chiavi = ("league_id", "market", "selection", "hit")
    assert (len(vecchio) != len(righe)
            or _conta(vecchio, chiavi) != _conta(righe, chiavi))


def test_load_keyset_regge_il_cap_del_server(monkeypatch):
    """Il server puo' restituire meno righe di quante richieste: non si deve
    scambiare una pagina corta per la fine dei dati."""
    righe = _righe_bet_features(25)
    db = FakeDB({"bet_features": righe}, cap=13)
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: db)
    monkeypatch.setattr(bd, "PAGE", 1000)
    df = bd.load()
    assert len(df) == len(righe)


def test_load_una_sola_fixture_riempie_il_blocco(monkeypatch):
    """Caso limite: tutte le righe del blocco hanno lo stesso fixture_id."""
    righe = []
    for k in range(60):
        righe.append({"fixture_id": 1400000, "league_id": 135, "market": "1x2",
                      "selection": f"S{k:02d}", "hit": True, "poisson_prob": 0.4,
                      "ml_prob": 0.4, "tacticai_prob": 0.4, "settled": True})
    righe += _righe_bet_features(3)
    db = FakeDB({"bet_features": righe})
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: db)
    monkeypatch.setattr(bd, "PAGE", 20)
    monkeypatch.setattr(bd, "PAGE_MIN", 5)
    monkeypatch.setattr(bd, "CAL_MARKETS", ["1x2", "btts"])
    df = bd.load()
    assert len(df) == len(righe)


def test_load_dimezza_il_blocco_sul_timeout_e_finisce(monkeypatch):
    """57014 sul blocco grande: si dimezza e si continua, senza perdere righe."""
    righe = _righe_bet_features(20)
    db = FakeDB({"bet_features": righe})
    usati = []

    def hook(q):
        if q.table != "bet_features":
            return
        usati.append(q._limit)
        if q._limit is not None and q._limit > 15:
            raise err_57014()

    db.select_hook = hook
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: db)
    monkeypatch.setattr(bd, "PAGE", 40)
    monkeypatch.setattr(bd, "PAGE_MIN", 10)
    df = bd.load()
    assert len(df) == len(righe)
    assert min(x for x in usati if x is not None) <= 15


def test_load_errore_non_transitorio_esce_subito(monkeypatch):
    db = FakeDB({"bet_features": _righe_bet_features(3)})
    db.select_hook = lambda q: (_ for _ in ()).throw(api_error("42703", 'column "x" does not exist'))
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: db)
    with pytest.raises(RuntimeError, match="bet_features"):
        bd.load()


def test_load_senza_righe_ritorna_dataframe_vuoto(monkeypatch):
    db = FakeDB({"bet_features": []})
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: db)
    assert bd.load().empty


# ============================================================================
# 3) refresh_analytics_bets: finestre di un giorno
# ============================================================================
def test_finestre_coprono_lo_stesso_intervallo_del_wrapper_sql():
    giorno = date(2026, 9, 21)
    win = rab.finestre(giorno, 5)
    assert win[0][0] == giorno - timedelta(days=5)     # (now() utc)::date - p_days
    assert win[-1][1] == giorno + timedelta(days=2)    # (now() utc)::date + 2
    assert len(win) == 7
    for (a, b), (c, _d) in zip(win, win[1:]):
        assert b == c                                   # contigue, senza buchi
        assert (b - a).days == 1                        # e senza sovrapposizioni


def _simula_range(stato, p_from: date, p_to: date) -> int:
    """Semantica di refresh_analytics_bets_range (migrations/analytics_strategy.sql:145):
      - book_odds_cache: delete+insert per fixture_date in [from,to)
      - analytics_bets : delete+insert per i FIXTURE con un segnale con kickoff in
        [from,to); l'insert aggrega TUTTI i segnali del fixture (non solo quelli
        della finestra)."""
    fixture_date = stato["fixture_date"]
    stato["book_odds_cache"] = {
        f: q for f, q in stato["book_odds_cache"].items()
        if not (p_from <= fixture_date[f] < p_to)}
    for f, d in fixture_date.items():
        if p_from <= d < p_to:
            stato["book_odds_cache"][f] = f"quote-{f}"
    fixtures = {s["fixture_id"] for s in stato["signals"]
                if p_from <= s["kickoff"].date() < p_to}
    stato["analytics_bets"] = {f: v for f, v in stato["analytics_bets"].items()
                               if f not in fixtures}
    n = 0
    for f in sorted(fixtures):
        tutti = sorted(s["prob"] for s in stato["signals"] if s["fixture_id"] == f)
        stato["analytics_bets"][f] = tuple(tutti)      # aggregato di TUTTI i segnali
        n += 1
    return n


def _stato_iniziale():
    base = date(2026, 9, 16)
    signals = []
    for i in range(12):
        fid = 1500000 + i
        ko = datetime(base.year, base.month, base.day, 18, 0, tzinfo=timezone.utc) + timedelta(days=i % 7)
        signals.append({"fixture_id": fid, "kickoff": ko, "prob": 0.4 + i / 100})
        signals.append({"fixture_id": fid, "kickoff": ko, "prob": 0.5 + i / 100})
    # fixture con segnali a CAVALLO di due giorni (kickoff incoerenti fra motori)
    ko1 = datetime(2026, 9, 18, 23, 30, tzinfo=timezone.utc)
    signals.append({"fixture_id": 1599999, "kickoff": ko1, "prob": 0.31})
    signals.append({"fixture_id": 1599999, "kickoff": ko1 + timedelta(hours=1), "prob": 0.32})
    fixture_date = {s["fixture_id"]: s["kickoff"].date() for s in signals}
    return {"signals": signals, "fixture_date": fixture_date,
            "book_odds_cache": {}, "analytics_bets": {}}


def test_finestre_giornaliere_danno_lo_stesso_stato_finale_della_chiamata_unica():
    giorno = date(2026, 9, 21)
    unico, fette = _stato_iniziale(), _stato_iniziale()
    _simula_range(unico, giorno - timedelta(days=5), giorno + timedelta(days=2))
    for a, b in rab.finestre(giorno, 5):
        _simula_range(fette, a, b)
    assert fette["analytics_bets"] == unico["analytics_bets"]
    assert fette["book_odds_cache"] == unico["book_odds_cache"]
    # idempotenza: rilanciare le finestre non cambia nulla
    for a, b in rab.finestre(giorno, 5):
        _simula_range(fette, a, b)
    assert fette["analytics_bets"] == unico["analytics_bets"]


def test_rinfresca_finestra_ritenta_il_transitorio_del_server():
    """Gli errori TRANSITORI del server si ritentano (il ReadTimeout del client
    NO: vedi test_refresh_non_ritenta_il_timeout_del_client)."""
    db = FakeDB()
    stato = {"n": 0}

    def impl(d, p):
        stato["n"] += 1
        if stato["n"] == 1:
            raise api_error("PGRST002", "Could not query the database for the schema cache")
        return 77

    db.rpc_impl[rab._RPC] = impl
    ok, n = rab.rinfresca_finestra(db, date(2026, 9, 20), date(2026, 9, 21))
    assert ok and n == 77 and stato["n"] == 2


def test_rinfresca_finestra_non_ritenta_errore_logico():
    db = FakeDB()
    stato = {"n": 0}

    def impl(d, p):
        stato["n"] += 1
        raise api_error("42883", "function public.refresh_analytics_bets_range(unknown) does not exist")

    db.rpc_impl[rab._RPC] = impl
    ok, n = rab.rinfresca_finestra(db, date(2026, 9, 20), date(2026, 9, 21))
    assert ok is False and n == 0 and stato["n"] == 1


def test_main_esce_non_zero_se_una_finestra_fallisce(monkeypatch, capsys):
    db = FakeDB()
    chiamate = []

    # STESSA data che usa lo script (UTC): con date.today() il test sarebbe
    # ballerino fra le 22:00 e le 24:00 UTC (fuso locale avanti).
    oggi_utc = datetime.now(timezone.utc).date()
    fallisce = (oggi_utc + timedelta(days=1)).isoformat()

    def impl(d, p):
        chiamate.append(p["p_from"])
        if p["p_from"] == fallisce:      # una finestra non passa MAI (nemmeno ai retry)
            raise err_57014()
        return 5

    db.rpc_impl[rab._RPC] = impl
    monkeypatch.setattr(rab, "get_supabase_client", lambda: db)
    monkeypatch.setattr(rab, "_PAUSA", 0)
    monkeypatch.setattr(sys, "argv", ["refresh_analytics_bets.py", "--days", "0"])
    with pytest.raises(SystemExit) as ex:
        rab.main()
    assert ex.value.code != 0 and "NON rinfrescate" in str(ex.value.code)
    assert len(set(chiamate)) == 2                  # tutte le finestre provate
    assert db.postgrest.session.timeout is not None  # timeout client alzato


def test_main_chiama_una_finestra_per_giorno(monkeypatch):
    db = FakeDB()
    db.rpc_impl[rab._RPC] = lambda d, p: 3
    monkeypatch.setattr(rab, "get_supabase_client", lambda: db)
    monkeypatch.setattr(rab, "_PAUSA", 0)
    monkeypatch.setattr(sys, "argv", ["refresh_analytics_bets.py", "--days", "5"])
    rab.main()
    assert db.n_rpc == 7
    dal = [p["p_from"] for _n, p in db.rpc_calls]
    assert len(set(dal)) == 7


# ============================================================================
# 4) build_analytics_signals / merge_engine_signals: paginazione su chiave unica
# ============================================================================
def _righe_fixture_predictions(n: int):
    return [{"fixture_id": 1600000 + i, "league_id": 135, "league_name": "Serie A",
             "season_year": 2026, "fixture_date": "2026-09-20T18:00:00+00:00",
             "home_team_name": "A", "away_team_name": "B",
             "db_json_analisi": {"markets": {}}, "model_predictions_json": None,
             "tactical_engine_json": None} for i in range(n)]


def _vecchio_fetch_fixtures(sb, page):
    """IL VECCHIO _fetch_fixtures: OFFSET senza ORDER BY, stop a len<page."""
    sel = "fixture_id"
    off, out = 0, []
    while True:
        q = sb.table("fixture_predictions").select(sel).not_.is_("db_json_analisi", "null")
        batch = q.range(off, off + page - 1).execute().data or []
        if not batch:
            break
        out += batch
        if len(batch) < page:
            break
        off += page
    return out


def test_fetch_fixtures_keyset_legge_tutto_anche_col_cap_del_server():
    righe = _righe_fixture_predictions(17)
    db = FakeDB({"fixture_predictions": righe}, cap=4)
    letti = [f["fixture_id"] for b in bas._fetch_fixtures(db, None, None, page=10) for f in b]
    assert sorted(letti) == sorted(r["fixture_id"] for r in righe)
    assert len(letti) == len(set(letti))            # nessun doppione
    # falsificazione: il vecchio si ferma alla prima pagina corta e perde il resto
    db2 = FakeDB({"fixture_predictions": _righe_fixture_predictions(17)}, cap=4)
    assert len(_vecchio_fetch_fixtures(db2, 10)) < 17


def test_fetch_fixtures_keyset_non_dipende_dall_ordine_fisico():
    righe = _righe_fixture_predictions(23)
    db = FakeDB({"fixture_predictions": righe})
    letti = [f["fixture_id"] for b in bas._fetch_fixtures(db, None, None, page=5) for f in b]
    assert letti == sorted(r["fixture_id"] for r in righe)
    # falsificazione: senza ORDER BY il vecchio metodo non ritorna l'insieme giusto
    db2 = FakeDB({"fixture_predictions": _righe_fixture_predictions(23)})
    vecchio = [r["fixture_id"] for r in _vecchio_fetch_fixtures(db2, 5)]
    assert sorted(vecchio) != sorted(letti)


def test_fetch_engine_signals_keyset_su_signal_uid():
    righe = [{"signal_uid": f"poisson|{1600000 + i}|over_2_5|2026-09-20",
              "run_date": "2026-09-20", "fixture_id": 1600000 + i, "engine": "poisson",
              "market": "O25", "status": "PLACED", "prob_calibrated": 0.55,
              "result": "PENDING"} for i in range(21)]
    db = FakeDB({"engine_signals": righe}, cap=6)
    letti = [s["signal_uid"] for b in mes._fetch_engine_signals(db, None, page=10) for s in b]
    assert sorted(letti) == sorted(r["signal_uid"] for r in righe)
    assert len(letti) == len(set(letti))


def test_upsert_non_ritenta_errore_logico_e_conta_le_righe():
    db = FakeDB({"analytics_signals": []})
    tentativi = {"n": 0}

    def hook(table, rows):
        tentativi["n"] += 1
        raise err_23505()

    db.upsert_hook = hook
    c = {"failed_rows": 0}
    righe = [{"signal_uid": "poisson|1|1x2|H", "market": "1x2", "selection": "H"}]
    bas._upsert(db, righe, False, c)
    assert tentativi["n"] == 1 and c["failed_rows"] == 1


def test_upsert_ritenta_il_transitorio():
    db = FakeDB({"analytics_signals": []})
    tentativi = {"n": 0}

    def hook(table, rows):
        tentativi["n"] += 1
        if tentativi["n"] < 3:
            raise err_57014()

    db.upsert_hook = hook
    c = {"failed_rows": 0}
    righe = [{"signal_uid": "poisson|1|1x2|H", "market": "1x2", "selection": "H"}]
    assert bas._upsert(db, righe, False, c) == 1
    assert c["failed_rows"] == 0 and tentativi["n"] == 3


# ============================================================================
# 5) GIRO 2 - letture di enrich (storia partite e target), eventi, scritture
# ============================================================================
def _righe_matches(n: int, league_id: int = 129):
    """Righe reali di `matches` (fixture_id e' UNICO: matches_fixture_unique)."""
    return [{"fixture_id": 1500000 + i, "league_id": league_id,
             "fixture_date": f"2026-{1 + (i % 9):02d}-15T18:00:00+00:00",
             "status_short": "FT", "goals_home": i % 4, "goals_away": (i + 1) % 3,
             "fulltime_home": i % 4, "fulltime_away": (i + 1) % 3,
             "halftime_home": 0, "halftime_away": 1} for i in range(n)]


def _vecchio_leggi_offset(sb, table: str, cols: str, filtri, page: int = 1000):
    """LA VECCHIA lettura (pre-giro-2): OFFSET senza ORDER BY, uscita a pagina
    CORTA, nessun retry. Serve come falsificazione."""
    off, out = 0, []
    while True:
        q = sb.table(table).select(cols)
        for f in filtri:
            q = f(q)
        r = q.range(off, off + page - 1).execute().data
        if not r:
            break
        out += r
        if len(r) < page:
            break
        off += page
    return out


def test_fetch_matches_legge_tutta_la_storia_anche_se_il_server_tronca():
    """Una storia partite TRONCATA produrrebbe freq/ritardi FALSI scritti con
    failed=0: qui il server cappa a 500 righe su 2500 partite."""
    righe = _righe_matches(2500)
    db = FakeDB({"matches": righe}, cap=500)
    letti = en._fetch_matches(db, 129)
    assert len(letti) == 2500
    assert len({m["fixture_id"] for m in letti}) == 2500      # nessun doppione
    # falsificazione: il vecchio si fermava alla prima pagina corta -> 500 partite
    db2 = FakeDB({"matches": _righe_matches(2500)}, cap=500)
    vecchio = _vecchio_leggi_offset(
        db2, "matches", en._MATCH_COLS,
        [lambda q: q.eq("league_id", 129), lambda q: q.in_("status_short", ["FT", "AET", "PEN"])])
    assert len(vecchio) == 500


def test_fetch_matches_non_perde_righe_con_ordine_fisico_instabile():
    righe = _righe_matches(120)
    db = FakeDB({"matches": righe})
    letti = en._fetch_matches(db, 129)
    assert [m["fixture_id"] for m in letti] == sorted(r["fixture_id"] for r in righe)
    # falsificazione: senza ORDER BY, con pagine da 50, l'insieme non e' lo stesso
    db2 = FakeDB({"matches": _righe_matches(120)})
    vecchio = _vecchio_leggi_offset(
        db2, "matches", en._MATCH_COLS,
        [lambda q: q.eq("league_id", 129), lambda q: q.in_("status_short", ["FT", "AET", "PEN"])],
        page=50)
    assert sorted(m["fixture_id"] for m in vecchio) != [m["fixture_id"] for m in letti]


def _righe_signals_lega(n_fixture: int, league_id: int = 129):
    out, rid = [], 1
    for i in range(n_fixture):
        fid = 1500000 + i
        for market, selection in MERCATI:
            for eng in MOTORI:
                out.append({"id": rid, "signal_uid": f"{eng}|{fid}|{market}|{selection}",
                            "engine": eng, "fixture_id": fid, "league_id": league_id,
                            "market": market, "selection": selection,
                            # kickoff RELATIVO a oggi (0/1/2 giorni fa): il test chiede
                            # "ultimi 4 giorni" e con date fisse diventava rosso col
                            # passare dei giorni (visto il 23/09).
                            "kickoff": (datetime.now(timezone.utc) - timedelta(days=i % 3))
                                       .strftime("%Y-%m-%dT18:00:00+00:00")})
                rid += 1
    return out


def test_fetch_signal_targets_legge_tutti_i_target_col_server_che_tronca():
    righe = _righe_signals_lega(100)        # 100 x 4 mercati x 3 motori = 1200 righe
    db = FakeDB({"analytics_signals": righe}, cap=500)
    by_ms = en._fetch_signal_targets(db, 129)
    assert sum(len(v) for v in by_ms.values()) == 100 * len(MERCATI)
    # falsificazione: il vecchio si fermava a 500 righe -> target incompleti
    db2 = FakeDB({"analytics_signals": _righe_signals_lega(100)}, cap=500)
    vecchio = _vecchio_leggi_offset(db2, "analytics_signals", "fixture_id,market,selection",
                                    [lambda q: q.eq("league_id", 129)])
    target_vecchi = {(x["market"], x["selection"], x["fixture_id"]) for x in vecchio}
    assert len(target_vecchi) < 100 * len(MERCATI)


def test_recent_targets_legge_tutto_col_server_che_tronca():
    righe = _righe_signals_lega(60)
    db = FakeDB({"analytics_signals": righe}, cap=250)
    out = en._recent_targets(db, 4)
    assert sum(len(v) for v in out.values()) == 60          # tutte le fixture
    assert set(out) == {129}


def test_letture_enrich_errore_non_transitorio_esce():
    db = FakeDB({"matches": _righe_matches(10)})
    db.select_hook = lambda q: (_ for _ in ()).throw(api_error("42703", 'column "x" does not exist'))
    with pytest.raises(RuntimeError, match="matches lega 129"):
        en._fetch_matches(db, 129)


def test_letture_enrich_ritentano_il_transitorio_e_dimezzano():
    righe = _righe_matches(300)
    db = FakeDB({"matches": righe})
    usate = []

    def hook(q):
        if q.table != "matches":
            return
        usate.append(q._range)
        lung = q._range[1] - q._range[0] + 1
        if lung > 500:
            raise err_57014()

    db.select_hook = hook
    letti = en._fetch_matches(db, 129)
    assert len(letti) == 300
    assert min(r[1] - r[0] + 1 for r in usate) <= 500        # pagina dimezzata


def _eventi_gol(fids, per_fixture: int):
    out, rid = [], 1
    for f in fids:
        for k in range(per_fixture):
            out.append({"id": rid, "fixture_id": f, "minute": 10 + k * 5,
                        "detail": "Normal Goal", "comments": None,
                        "event_type": "Goal"})
            rid += 1
    return out


def test_fetch_first_goals_pagina_e_non_perde_i_gol_in_coda():
    """Con 100 fixture x 9 gol = 900 righe e cap del server a 300, il primo gol
    delle fixture in coda spariva: first_goal_minute sbagliato in silenzio."""
    fids = [1600000 + i for i in range(100)]
    eventi = _eventi_gol(fids, 9)
    db = FakeDB({"match_events": eventi}, cap=300)
    out = bas._fetch_first_goals(db, fids)
    assert len(out) == 100                       # TUTTE le fixture hanno il loro gol
    assert set(out.values()) == {10}             # il primo gol e' sempre il minuto 10
    # falsificazione: senza paginazione si fermava alle prime 300 righe
    db2 = FakeDB({"match_events": _eventi_gol(fids, 9)}, cap=300)
    vecchio = _vecchio_leggi_offset(db2, "match_events", "fixture_id,minute,detail,comments",
                                    [lambda q: q.in_("fixture_id", fids),
                                     lambda q: q.eq("event_type", "Goal")])
    assert len({e["fixture_id"] for e in vecchio}) < 100


def test_fetch_first_goals_usa_blocchi_da_100_fixture():
    fids = [1600000 + i for i in range(250)]
    db = FakeDB({"match_events": _eventi_gol(fids, 2)})
    blocchi = []
    db.select_hook = lambda q: blocchi.append([f for f in q.filters if f[0] == "in"][0][2])
    bas._fetch_first_goals(db, fids)
    assert bas._EVENTI_CHUNK == 100
    assert max(len(b) for b in blocchi) <= bas._EVENTI_CHUNK


def _prepara_direzione(monkeypatch, db):
    monkeypatch.setattr(db_client, "get_supabase_client", lambda: db)
    monkeypatch.setattr(bd, "PAGE", 18)
    monkeypatch.setattr(bd, "CAL_MARKETS", ["1x2", "btts"])
    monkeypatch.setattr(bd, "MIN_GLOBAL", 1)
    monkeypatch.setattr(bd, "MIN_LEAGUE", 1)


def test_direzione_upsert_fallito_non_cancella_le_righe_stale(monkeypatch):
    """La pagella non deve mai restare meta' nuova e meta' cancellata: il delete
    delle righe stale avviene SOLO dopo che TUTTI gli upsert sono riusciti."""
    vecchia = [{"engine": "poisson", "market": "1x2", "selection": "H", "league_id": 0,
                "prob_bucket": ".40-.50", "n": 10, "hits": 5, "hit_rate": 0.5,
                "base_rate": 0.5, "generated_at": "2026-09-20T03:30:00+00:00"}]
    db = FakeDB({"bet_features": _righe_bet_features(40), "direction_pagella": vecchia})
    _prepara_direzione(monkeypatch, db)
    db.upsert_hook = lambda table, rows: (_ for _ in ()).throw(err_57014())
    with pytest.raises(RuntimeError, match="upsert direction_pagella"):
        bd.main()
    assert db.tables["direction_pagella"] == vecchia      # pagella intatta
    assert db.n_delete == 0                                # nessun delete eseguito


def test_direzione_upsert_ritenta_il_transitorio_poi_cancella_gli_stale(monkeypatch):
    vecchia = [{"engine": "poisson", "market": "vecchio", "selection": "H", "league_id": 0,
                "prob_bucket": ".40-.50", "n": 10, "hits": 5, "hit_rate": 0.5,
                "base_rate": 0.5, "generated_at": "2026-09-20T03:30:00+00:00"}]
    db = FakeDB({"bet_features": _righe_bet_features(40), "direction_pagella": list(vecchia)})
    _prepara_direzione(monkeypatch, db)
    tent = {"n": 0}

    def hook(table, rows):
        tent["n"] += 1
        if tent["n"] == 1:
            raise err_503()

    db.upsert_hook = hook
    bd.main()
    assert tent["n"] >= 2                                  # ha ritentato
    assert db.n_delete == 1                                # stale rimossi DOPO
    assert all(r["market"] != "vecchio" for r in db.tables["direction_pagella"])
    assert db.tables["direction_pagella"]


def test_merge_codici_non_mappati_fanno_uscire_non_zero(monkeypatch):
    righe = [{"signal_uid": "poisson|1600000|XYZ|2026-09-20", "run_date": "2026-09-20",
              "fixture_id": 1600000, "engine": "poisson", "market": "XYZ",
              "market_label": "?", "status": "PLACED", "prob_calibrated": 0.55,
              "result": "PENDING", "league_id": 135, "league_name": "Serie A",
              "season_year": 2026, "home_team": "A", "away_team": "B",
              "kickoff": "2026-09-20T18:00:00+00:00", "emitted_at": "2026-09-20T09:00:00+00:00",
              "direction": "back"}]
    db = FakeDB({"engine_signals": righe, "analytics_decisions": [], "matches": [],
                 "analytics_signals": []})
    monkeypatch.setattr(mes, "get_supabase_client", lambda: db)
    monkeypatch.setattr(sys, "argv", ["merge_engine_signals.py"])
    with pytest.raises(SystemExit) as ex:
        mes.main()
    assert "XYZ" in str(ex.value.code) and "previsioni perse" in str(ex.value.code)


def test_merge_senza_codici_ignoti_esce_zero(monkeypatch):
    righe = [{"signal_uid": "poisson|1600000|O25|2026-09-20", "run_date": "2026-09-20",
              "fixture_id": 1600000, "engine": "poisson", "market": "O25",
              "market_label": "Over 2.5", "status": "PLACED", "prob_calibrated": 0.55,
              "result": "PENDING", "league_id": 135, "league_name": "Serie A",
              "season_year": 2026, "home_team": "A", "away_team": "B",
              "kickoff": "2026-09-20T18:00:00+00:00", "emitted_at": "2026-09-20T09:00:00+00:00",
              "direction": "back"}]
    db = FakeDB({"engine_signals": righe, "analytics_decisions": [], "matches": [],
                 "analytics_signals": []})
    monkeypatch.setattr(mes, "get_supabase_client", lambda: db)
    monkeypatch.setattr(sys, "argv", ["merge_engine_signals.py"])
    mes.main()          # nessuna SystemExit


def test_refresh_non_ritenta_il_timeout_del_client():
    """Lo statement puo' essere ancora vivo sul server (statement_timeout=0):
    rilanciarlo significa due delete+insert in concorrenza sulle stesse righe."""
    db = FakeDB()
    n = {"c": 0}

    def impl(d, p):
        n["c"] += 1
        raise httpx.ReadTimeout("timed out")

    db.rpc_impl[rab._RPC] = impl
    ok, righe = rab.rinfresca_finestra(db, date(2026, 9, 20), date(2026, 9, 21))
    assert ok is False and righe == 0
    assert n["c"] == 1                      # UNA sola chiamata, nessun retry


def test_refresh_ritenta_gli_altri_transitori():
    db = FakeDB()
    n = {"c": 0}

    def impl(d, p):
        n["c"] += 1
        if n["c"] == 1:
            raise err_503()
        return 42

    db.rpc_impl[rab._RPC] = impl
    ok, righe = rab.rinfresca_finestra(db, date(2026, 9, 20), date(2026, 9, 21))
    assert ok and righe == 42 and n["c"] == 2


def test_refresh_timeout_client_avvisa_di_non_rilanciare(capsys):
    db = FakeDB()
    db.rpc_impl[rab._RPC] = lambda d, p: (_ for _ in ()).throw(httpx.ReadTimeout("t"))
    rab.rinfresca_finestra(db, date(2026, 9, 20), date(2026, 9, 21))
    out = capsys.readouterr().out
    assert "NON ritento" in out and "NON rilanciare a mano subito" in out


def test_refresh_connect_timeout_si_ritenta():
    """La connessione non si e' aperta: lo statement non e' mai partito."""
    db = FakeDB()
    n = {"c": 0}

    def impl(d, p):
        n["c"] += 1
        if n["c"] == 1:
            raise httpx.ConnectTimeout("no connect")
        return 7

    db.rpc_impl[rab._RPC] = impl
    ok, righe = rab.rinfresca_finestra(db, date(2026, 9, 20), date(2026, 9, 21))
    assert ok and righe == 7 and n["c"] == 2


def test_refresh_timeout_client_alzato_a_600s():
    assert rab._HTTP_TIMEOUT >= 600.0


def test_snapshot_non_cambiano_con_l_ordine_di_lettura():
    """EQUIVALENZA dei NUMERI: compute_market_snapshots riordina da se' con
    chrono_key=(fixture_date,fixture_id), quindi l'ORDER BY aggiunto alla lettura
    di `matches` non puo' cambiare nessun freq_*/delay_* scritto."""
    from analytics_market_stats import compute_market_snapshots
    partite = _righe_matches(40)
    mescolate = partite[7:] + partite[:7]
    a = compute_market_snapshots("over_2_5", "Over", partite)
    b = compute_market_snapshots("over_2_5", "Over", mescolate)
    assert a and a == b


# ============================================================================
# 6) run 35837906029 (23/09): lega 929 in 57014 aveva ucciso l'intero script
#    (enrich_analytics_snapshots), e il 504 del gateway ritentato aveva prodotto
#    23505/55P03 su refresh_analytics_bets. Vedi log righe ~605-671.
# ============================================================================
def test_fetch_signal_targets_dimezza_il_blocco_su_57014_e_legge_la_lega():
    """IL DIFETTO VERO: _PAGE_MIN era 100, IDENTICO al blocco iniziale della
    lettura per lega (_PAGE_LEGA=100): il blocco non si dimezzava MAI davvero,
    5 tentativi sullo STESSO blocco da 100 -> 57014 ripetuto -> RuntimeError.
    Ora la prima lettura (blocco 100) va in 57014, la seconda (dimezzata a 50)
    risponde: la lega si legge lo stesso, senza perdere righe."""
    righe = _righe_signals_lega(30, league_id=929)     # 30 fix x 4 mercati = 120 righe
    db = FakeDB({"analytics_signals": righe})
    usati = []

    def hook(q):
        if q.table != "analytics_signals":
            return
        lung = q._range[1] - q._range[0] + 1
        usati.append(lung)
        if lung >= en._PAGE_LEGA:     # 100: va SEMPRE in 57014 -> deve dimezzare per passare
            raise err_57014()

    db.select_hook = hook
    by_ms = en._fetch_signal_targets(db, 929)
    assert sum(len(v) for v in by_ms.values()) == 30 * len(MERCATI)   # nessuna riga persa
    assert usati[0] == en._PAGE_LEGA == 100      # la prima lettura usa il blocco iniziale
    assert min(usati) < en._PAGE_LEGA            # e si e' DAVVERO dimezzata per riuscire


def test_fetch_signal_targets_57014_persistente_esce_dopo_5_tentativi_al_minimo():
    """Se il 57014 persiste anche al blocco minimo (25), _leggi_pagine esce con
    RuntimeError dopo i 5 tentativi (non resta appesa, non finge un successo)."""
    righe = _righe_signals_lega(10, league_id=929)
    db = FakeDB({"analytics_signals": righe})
    db.select_hook = lambda q: (_ for _ in ()).throw(err_57014()) if q.table == "analytics_signals" else None
    with pytest.raises(RuntimeError, match="analytics_signals lega 929") as ex:
        en._fetch_signal_targets(db, 929)
    assert "5 tentativi" in str(ex.value)
    assert en._is_retry_esauriti(ex.value)      # e' un 57014 esaurito: la lega si puo' saltare


def test_main_lega_57014_persistente_non_ferma_le_altre_leghe(monkeypatch, capsys):
    """IL FIX: prima, una lega in 57014 persistente faceva morire l'INTERO
    script (RuntimeError non gestito, vedi run 35837906029, lega 929: le leghe
    dopo la 929 non venivano mai elaborate). Ora la lega fallita si registra e
    si salta; le ALTRE leghe (qui la 331) vengono elaborate regolarmente e lo
    script esce comunque != 0 col riepilogo."""
    sig_929 = _righe_signals_lega(5, league_id=929)
    sig_331 = _righe_signals_lega(5, league_id=331)
    matches_331 = _righe_matches(5, league_id=331)
    db = FakeDB({"analytics_signals": sig_929 + sig_331, "matches": matches_331,
                 "analytics_snap_staging": []})

    def hook(q):
        if q.table == "analytics_signals" and ("eq", "league_id", 929) in q.filters:
            raise err_57014()          # SEMPRE in 57014 per la lega 929, mai per la 331

    db.select_hook = hook
    monkeypatch.setattr(en, "get_supabase_client", lambda: db)
    monkeypatch.setattr(sys, "argv", ["enrich_analytics_snapshots.py", "--days", "4"])
    with pytest.raises(SystemExit) as ex:
        en.main()
    out = capsys.readouterr().out
    assert "[ERR lega 929]" in out
    assert "929" in str(ex.value.code) and "leghe fallite" in str(ex.value.code)
    # la lega 331 E' STATA elaborata comunque: il flush l'ha davvero toccata
    # (updated_at scritto dalla RPC -- freq_current puo' restare None qui, serve
    # mm10 su >=10 partite precedenti, ma la RIGA e' stata aggiornata lo stesso)
    righe_331 = [s for s in db.tables["analytics_signals"] if s["league_id"] == 331]
    assert righe_331 and any(s.get("updated_at") is not None for s in righe_331)
    # la lega 929 NON e' stata toccata (mai arrivata al flush)
    righe_929 = [s for s in db.tables["analytics_signals"] if s["league_id"] == 929]
    assert all(s.get("updated_at") is None for s in righe_929)


def test_main_errore_logico_in_una_lega_propaga_subito_e_non_salta(monkeypatch):
    """Un errore LOGICO (colonna inesistente, vincolo...) NON e' un DB sotto
    pressione: deve fermare lo script SUBITO, non essere inghiottito come le
    leghe in 57014 persistente (altrimenti un difetto di schema/query
    sparirebbe silenziosamente nel riepilogo delle "leghe fallite")."""
    sig_929 = _righe_signals_lega(5, league_id=929)
    db = FakeDB({"analytics_signals": sig_929, "matches": []})

    def hook(q):
        if q.table == "analytics_signals" and ("eq", "league_id", 929) in q.filters:
            raise api_error("42703", 'column "pippo" does not exist')

    db.select_hook = hook
    monkeypatch.setattr(en, "get_supabase_client", lambda: db)
    monkeypatch.setattr(sys, "argv", ["enrich_analytics_snapshots.py", "--days", "4"])
    with pytest.raises(RuntimeError, match="analytics_signals lega 929"):
        en.main()


def test_timeout_client_riconosce_il_504_del_gateway_dopo_l_invio():
    """IL BUG VERO (run 35837906029): un 504 del gateway ARRIVATO (la richiesta
    e' partita, la risposta no) veniva ritentato come i transitori del server
    -> il secondo tentativo trovava lo statement PRECEDENTE ancora in esecuzione
    (statement_timeout=0 su entrambe le RPC) e sbatteva contro le sue righe
    (23505 duplicate key / 55P03 lock timeout, vedi log 18/09, 20/09, 22/09)."""
    assert rab._timeout_client(err_504())
    assert not rab._is_transient(err_504())
    # il CODE resta autoritativo: un 503 (diverso dal 504 osservato) NON e'
    # trattato come gateway-timeout anche se il messaggio fosse lo stesso
    assert not rab._timeout_client(err_503())
    assert rab._is_transient(err_503())


def test_rinfresca_finestra_504_gateway_nessun_secondo_tentativo(capsys):
    db = FakeDB()
    n = {"c": 0}

    def impl(d, p):
        n["c"] += 1
        raise err_504()

    db.rpc_impl[rab._RPC] = impl
    ok, righe = rab.rinfresca_finestra(db, date(2026, 9, 18), date(2026, 9, 19))
    assert ok is False and righe == 0
    assert n["c"] == 1                          # UNA sola chiamata: nessun retry sul 504
    out = capsys.readouterr().out
    assert "NON ritento" in out and "NON rilanciare a mano subito" in out


def test_rinfresca_finestra_55P03_si_ritenta():
    """55P03 (lock timeout) resta RITENTABILE: e' l'errore che si vede quando la
    finestra precedente e' finita ma ha lasciato un lock, non un 5xx del
    gateway arrivato a meta' di una richiesta ancora in corso."""
    db = FakeDB()
    n = {"c": 0}

    def impl(d, p):
        n["c"] += 1
        if n["c"] == 1:
            raise api_error("55P03", "canceling statement due to lock timeout")
        return 15

    db.rpc_impl[rab._RPC] = impl
    ok, righe = rab.rinfresca_finestra(db, date(2026, 9, 20), date(2026, 9, 21))
    assert ok and righe == 15 and n["c"] == 2

