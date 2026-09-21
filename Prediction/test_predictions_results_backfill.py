"""Certificazione di Prediction/predictions_results_backfill.py (21/09/2026).

NESSUNA rete e NESSUN DB: client Supabase FINTO che parla come il vero
(postgrest ``APIError`` con dict {'message','code','hint','details'}, righe con
le colonne e i tipi reali di ``fixture_predictions`` / ``matches``, UPDATE e RPC
update-only che toccano solo le righe esistenti e valorizzano ``evaluated_at``).

Cosa certifica:
  * chunk RPC in statement_timeout (57014) -> dimezzato e recuperato;
  * timeout persistente su UNA fixture -> le altre passano, riepilogo + exit != 0;
  * errore NON transitorio -> nessun retry (non si maschera un difetto logico);
  * RPC che NON conferma le righe (meno righe dei payload, o esito ignoto) ->
    mai data per riuscita: riscrittura riga-per-riga e, se la riga non esiste,
    fixture nei falliti con exit != 0;
  * lettura predictions deterministica (keyset ordinato), a fette adattive, che
    NON si ferma su una pagina corta (server con max-rows) e che riconosce il
    troncamento da --limit;
  * idempotenza: il secondo giro non riscrive nulla;
  * percorso senza errori: stesse identiche scritture del codice PRIMA del fix
    (recuperato con ``git show`` dal commit base fisso ``COMMIT_BASE``, mai da
    HEAD: dopo il commit del fix HEAD sarebbe il codice nuovo e il confronto
    passerebbe a vuoto), campi ``hit_*`` identici riga per riga.
"""
from __future__ import annotations

import copy
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pytest
from postgrest.exceptions import APIError

import Prediction.predictions_results_backfill as mod

REPO_ROOT = Path(__file__).resolve().parent.parent


# =========================================================================
# Finti: stessi errori, stesse chiavi, stessi tipi del vero
# =========================================================================

def _timeout_error() -> APIError:
    # forma identica a quella vista nei log di produzione del 19-21/09
    return APIError(
        {
            "message": "canceling statement due to statement timeout",
            "code": "57014",
            "hint": None,
            "details": None,
        }
    )


def _network_error() -> APIError:
    return APIError(
        {
            "message": "Server disconnected without sending a response",
            "code": "PGRST002",
            "hint": None,
            "details": None,
        }
    )


def _logic_error() -> APIError:
    # errore LOGICO: non si ritenta mai
    return APIError(
        {
            "message": 'null value in column "status" violates not-null constraint',
            "code": "23502",
            "hint": None,
            "details": None,
        }
    )


def _rpc_missing_error() -> APIError:
    return APIError(
        {
            "message": "Could not find the function public.bulk_update_prediction_results(p_rows)",
            "code": "PGRST202",
            "hint": None,
            "details": None,
        }
    )


class _Resp:
    def __init__(self, data: Any) -> None:
        self.data = data


class _SelectQuery:
    """Builder select stile postgrest: memorizza i filtri e li applica sul finto."""

    def __init__(self, sb: "_FakeSupabase", table: str) -> None:
        self.sb = sb
        self.table = table
        self.filters: List[tuple] = []
        self.order_by: Optional[str] = None
        self.limit_n: Optional[int] = None

    def select(self, _cols: str) -> "_SelectQuery":
        return self

    def eq(self, col: str, val: Any) -> "_SelectQuery":
        self.filters.append(("eq", col, val))
        return self

    def gte(self, col: str, val: Any) -> "_SelectQuery":
        self.filters.append(("gte", col, val))
        return self

    def lte(self, col: str, val: Any) -> "_SelectQuery":
        self.filters.append(("lte", col, val))
        return self

    def gt(self, col: str, val: Any) -> "_SelectQuery":
        self.filters.append(("gt", col, val))
        return self

    def is_(self, col: str, val: str) -> "_SelectQuery":
        self.filters.append(("is", col, val))
        return self

    def in_(self, col: str, vals: Sequence[Any]) -> "_SelectQuery":
        self.filters.append(("in", col, list(vals)))
        return self

    def order(self, col: str, desc: bool = False) -> "_SelectQuery":
        self.order_by = f"-{col}" if desc else col
        return self

    def limit(self, n: int) -> "_SelectQuery":
        self.limit_n = n
        return self

    def execute(self) -> _Resp:
        return self.sb._run_select(self)


class _UpdateQuery:
    def __init__(self, sb: "_FakeSupabase", table: str, body: Dict[str, Any]) -> None:
        self.sb = sb
        self.table = table
        self.body = body
        self.fixture_id: Optional[int] = None

    def eq(self, col: str, val: Any) -> "_UpdateQuery":
        assert col == "fixture_id"
        self.fixture_id = int(val)
        return self

    def execute(self) -> _Resp:
        return self.sb._run_update(self)


class _FakeTable:
    def __init__(self, sb: "_FakeSupabase", name: str) -> None:
        self.sb = sb
        self.name = name

    def select(self, cols: str) -> _SelectQuery:
        return _SelectQuery(self.sb, self.name).select(cols)

    def update(self, body: Dict[str, Any]) -> _UpdateQuery:
        return _UpdateQuery(self.sb, self.name, body)


class _RpcCall:
    def __init__(self, sb: "_FakeSupabase", name: str, params: Dict[str, Any]) -> None:
        self.sb = sb
        self.name = name
        self.params = params

    def execute(self) -> _Resp:
        return self.sb._run_rpc(self)


class _FakeSupabase:
    """Finto Supabase con la semantica UPDATE-ONLY del vero.

    - UPDATE e RPC scrivono SOLO sulle righe esistenti in fixture_predictions e
      valorizzano i campi del payload (compreso ``evaluated_at``), cosi' il
      secondo giro dello script vede le righe gia' valutate (idempotenza).
    - ``rpc_max_ok``: oltre questa dimensione di payload la RPC va in 57014.
    - ``select_max_ok``: oltre questa dimensione di pagina la select va in 57014.
    - ``select_fail_times``: le prime N select vanno in 57014 (qualsiasi taglia).
    - ``max_rows``: tetto righe del server (tronca la pagina come PostgREST).
    - ``row_always_timeout`` / ``row_flaky`` / ``row_logic_error``: comportamento
      degli UPDATE puntuali.
    - ``rpc_reply``: risposta imposta alla RPC (es. 0, o una lista) SENZA scrivere.
    - ``scramble_unordered``: senza ORDER BY le righe tornano in ordine arbitrario.
    """

    def __init__(
        self,
        preds: List[Dict[str, Any]],
        matches: List[Dict[str, Any]],
        *,
        rpc_max_ok: int = 10 ** 9,
        select_max_ok: int = 10 ** 9,
        select_fail_times: int = 0,
        select_fail_at: Optional[set] = None,
        max_rows: Optional[int] = None,
        row_always_timeout: Optional[set] = None,
        row_flaky: Optional[Dict[int, int]] = None,
        rpc_missing: bool = False,
        rpc_reply: Any = None,
        row_logic_error: Optional[set] = None,
        scramble_unordered: bool = True,
        elimina_alla_prima_rpc: Optional[int] = None,
    ) -> None:
        # copia profonda: ogni finto e' un "DB" indipendente
        self.preds = copy.deepcopy(preds)
        self.matches = copy.deepcopy(matches)
        self._index = {int(r["fixture_id"]): r for r in self.preds}

        self.rpc_max_ok = rpc_max_ok
        self.select_max_ok = select_max_ok
        self.select_fail_times = select_fail_times
        self.select_fail_at = set(select_fail_at or ())  # indici (1-based) di select in 57014
        self.max_rows = max_rows
        self.row_always_timeout = set(row_always_timeout or ())
        self.row_flaky = dict(row_flaky or {})
        self.rpc_missing = rpc_missing
        self.rpc_reply = rpc_reply
        self.row_logic_error = set(row_logic_error or ())
        self.scramble_unordered = scramble_unordered
        self.elimina_alla_prima_rpc = elimina_alla_prima_rpc

        self.written: Dict[int, Dict[str, Any]] = {}
        self.rpc_calls: List[List[int]] = []      # fixture_id per chiamata RPC
        self.update_calls: List[int] = []         # fixture_id per UPDATE puntuale
        self.select_calls: List[Dict[str, Any]] = []

    # -- API stile supabase-py -------------------------------------------
    def table(self, name: str) -> _FakeTable:
        return _FakeTable(self, name)

    def rpc(self, name: str, params: Dict[str, Any]) -> _RpcCall:
        return _RpcCall(self, name, params)

    # -- esecuzione --------------------------------------------------------
    def _rows_for(self, table: str) -> List[Dict[str, Any]]:
        return self.preds if table == "fixture_predictions" else self.matches

    def elimina(self, fixture_id: int) -> None:
        """Toglie la riga da fixture_predictions (delete concorrente)."""
        fx = int(fixture_id)
        self._index.pop(fx, None)
        self.preds = [r for r in self.preds if int(r["fixture_id"]) != fx]

    def _scrivi(self, fx: int, body: Dict[str, Any]) -> bool:
        """UPDATE-only: scrive solo se la riga esiste. True se ha scritto."""
        riga = self._index.get(fx)
        if riga is None:
            return False
        riga.update(body)
        self.written[fx] = dict(body)
        return True

    def _run_select(self, q: _SelectQuery) -> _Resp:
        self.select_calls.append(
            {"table": q.table, "filters": list(q.filters), "order": q.order_by, "limit": q.limit_n}
        )
        if self.select_fail_times > 0:
            self.select_fail_times -= 1
            raise _timeout_error()
        if len(self.select_calls) in self.select_fail_at:
            raise _timeout_error()
        if q.limit_n is not None and q.limit_n > self.select_max_ok:
            raise _timeout_error()

        rows = []
        for r in self._rows_for(q.table):
            ok = True
            for kind, col, val in q.filters:
                v = r.get(col)
                if kind == "eq":
                    ok = v == val
                elif kind == "gte":
                    ok = v is not None and str(v) >= str(val)
                elif kind == "lte":
                    ok = v is not None and str(v) <= str(val)
                elif kind == "gt":
                    ok = v is not None and v > val
                elif kind == "is":
                    ok = v is None if val == "null" else v is not None
                elif kind == "in":
                    ok = v in val
                if not ok:
                    break
            if ok:
                rows.append(dict(r))

        if q.order_by:
            col = q.order_by.lstrip("-")
            rows.sort(key=lambda r: r[col], reverse=q.order_by.startswith("-"))
        elif self.scramble_unordered:
            # senza ORDER BY l'ordine NON e' garantito: il finto lo rende avverso
            rows.sort(key=lambda r: r["fixture_id"], reverse=True)

        if q.limit_n is not None:
            rows = rows[: q.limit_n]
        if self.max_rows is not None:
            rows = rows[: self.max_rows]  # tetto del server (PostgREST max-rows)
        return _Resp(rows)

    def _run_update(self, q: _UpdateQuery) -> _Resp:
        fx = int(q.fixture_id or 0)
        self.update_calls.append(fx)
        if fx in self.row_logic_error:
            raise _logic_error()
        if fx in self.row_always_timeout:
            raise _timeout_error()
        if self.row_flaky.get(fx, 0) > 0:
            self.row_flaky[fx] -= 1
            raise _network_error()
        scritta = self._scrivi(fx, dict(q.body))
        return _Resp([{"fixture_id": fx}] if scritta else [])

    def _run_rpc(self, call: _RpcCall) -> _Resp:
        rows = call.params["p_rows"]
        self.rpc_calls.append([int(r["fixture_id"]) for r in rows])
        if self.elimina_alla_prima_rpc is not None:
            # delete concorrente: la riga c'era alla lettura, non c'e' piu' ora
            self.elimina(self.elimina_alla_prima_rpc)
            self.elimina_alla_prima_rpc = None
        if self.rpc_missing:
            raise _rpc_missing_error()
        if len(rows) > self.rpc_max_ok:
            raise _timeout_error()
        if self.rpc_reply is not None:
            return _Resp(self.rpc_reply)  # risposta imposta: NON scrive nulla
        scritte = 0
        for r in rows:
            fx = int(r["fixture_id"])
            if fx in self.row_always_timeout:
                raise _timeout_error()
            body = {k: v for k, v in r.items() if k != "fixture_id"}
            if self._scrivi(fx, body):
                scritte += 1
        return _Resp(scritte)  # come la RPC vera: ROW_COUNT


# =========================================================================
# Dati finti: colonne e tipi reali
# =========================================================================

DATE = "2026-09-20"


def _pred(fixture_id: int, winner: Optional[int] = 100, wod: bool = False,
          uo: Optional[str] = "-3.5") -> Dict[str, Any]:
    return {
        "fixture_id": int(fixture_id),
        "fixture_date": f"{DATE}T18:00:00+00:00",
        "status": "ok",
        "winner_team_id": winner,
        "win_or_draw": wod,
        "under_over_line": uo,
        "evaluated_at": None,
    }


def _match(fixture_id: int, gh: int = 2, ga: int = 1, status: str = "FT") -> Dict[str, Any]:
    return {
        "fixture_id": int(fixture_id),
        "status_short": status,
        "goals_home": int(gh),
        "goals_away": int(ga),
        "home_team_id": 100,
        "away_team_id": 200,
    }


# Combinazioni di dati: PRODOTTO CARTESIANO, non cicli modulari.
# (Con i cicli modulari usati prima i pareggi capitavano solo con
# win_or_draw=False: il ramo "pareggio -> hit_win_or_draw=True" non veniva mai
# eseguito e una mutazione di quel ramo NON faceva diventare rosso il test.)
# Tutti i match sono FINISHED: i casi non valutabili sono coperti a parte.
_PUNTEGGI = [(2, 1, "FT"), (0, 0, "FT"), (1, 3, "AET"), (4, 4, "PEN"),
             (0, 2, "FT"), (3, 3, "FT")]
_WINNERS = [100, 200, None]
_WOD = [True, False]
# linee .5 (come dall'endpoint) + linee intere, che mettono alla prova il
# CONFINE di hit_under_over (total esattamente uguale alla linea: 2-1 -> 3).
_LINEE = ["-3.5", "+2.5", None, "+0.5", "-3", "+3"]

_COMBINAZIONI = [
    (punteggio, winner, wod, uo)
    for punteggio in _PUNTEGGI
    for winner in _WINNERS
    for wod in _WOD
    for uo in _LINEE
]


def _dataset(n: int, first_id: int = 1600000):
    preds, matches = [], []
    for k in range(n):
        fx = first_id + k
        (gh, ga, status), winner, wod, uo = _COMBINAZIONI[k % len(_COMBINAZIONI)]
        preds.append(_pred(fx, winner=winner, wod=wod, uo=uo))
        matches.append(_match(fx, gh=gh, ga=ga, status=status))
    return preds, matches


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Nessuna attesa reale nei test; registra i backoff effettuati."""
    waits: List[int] = []
    monkeypatch.setattr(mod, "_sleep_backoff", lambda attempt: waits.append(attempt))
    return waits


def _install(monkeypatch, sb: _FakeSupabase) -> _FakeSupabase:
    monkeypatch.setattr(mod, "get_supabase_client", lambda: sb)
    return sb


# =========================================================================
# 1) chunk in timeout -> dimezza e recupera TUTTO
# =========================================================================

def test_chunk_in_timeout_dimezza_e_aggiorna_tutte(monkeypatch):
    preds, matches = _dataset(40)
    sb = _install(monkeypatch, _FakeSupabase(preds, matches, rpc_max_ok=10))

    failed = mod.run(DATE, force=False, limit=5000)

    assert failed == 0
    # tutte e 40 aggiornate, nessun buco
    assert sorted(sb.written) == sorted(p["fixture_id"] for p in preds)
    # blocchi PICCOLI (valore fisso, non la costante del modulo: se qualcuno la
    # rialza a 500 questo test deve diventare rosso)
    assert mod.RPC_BULK_CHUNK <= 25
    assert len(sb.rpc_calls[0]) <= 25
    assert max(len(c) for c in sb.rpc_calls[1:]) <= 12
    # nessun fallback riga-per-riga: il bulk ce l'ha fatta da solo
    assert sb.update_calls == []
    scritti = [fx for c in sb.rpc_calls for fx in c if fx in sb.written]
    assert len(set(scritti)) == 40


def test_timeout_persistente_scende_al_riga_per_riga(monkeypatch):
    # nemmeno 5 payload passano: si scende sotto RPC_MIN_CHUNK -> riga-per-riga
    preds, matches = _dataset(12)
    sb = _install(monkeypatch, _FakeSupabase(preds, matches, rpc_max_ok=0))

    failed = mod.run(DATE, force=False, limit=5000)

    assert failed == 0
    assert sorted(sb.written) == sorted(p["fixture_id"] for p in preds)
    assert sorted(sb.update_calls) == sorted(p["fixture_id"] for p in preds)
    # la RPC e' scesa fino a RPC_MIN_CHUNK prima di cedere il passo al riga-per-riga
    assert mod.RPC_MIN_CHUNK in [len(c) for c in sb.rpc_calls]
    assert all(len(c) <= mod.RPC_MIN_CHUNK for c in sb.rpc_calls[2:])
    # nessun tentativo ripetuto con la STESSA dimensione (8 s di DB sprecati)
    assert all(a != b for a, b in zip(sb.rpc_calls, sb.rpc_calls[1:]))


# =========================================================================
# 2) timeout persistente su UNA fixture: le altre passano, exit != 0
# =========================================================================

def test_fixture_irrecuperabile_non_blocca_le_altre_ed_esce_non_zero(monkeypatch, _no_sleep):
    preds, matches = _dataset(12)
    rotta = preds[5]["fixture_id"]
    sb = _install(
        monkeypatch,
        _FakeSupabase(preds, matches, rpc_max_ok=10 ** 9, row_always_timeout={rotta}),
    )

    failed = mod.run(DATE, force=False, limit=5000)

    assert failed == 1
    # tutte le altre 11 sono state aggiornate lo stesso
    assert sorted(sb.written) == sorted(p["fixture_id"] for p in preds if p["fixture_id"] != rotta)
    assert rotta not in sb.written
    # la fixture rotta e' stata ritentata con backoff (non abbandonata al primo colpo)
    assert sb.update_calls.count(rotta) == mod.RETRY_ATTEMPTS
    assert len(_no_sleep) >= mod.RETRY_ATTEMPTS - 1

    # ...e il processo esce con codice != 0
    monkeypatch.setattr(sys, "argv", ["prog", "--date", DATE])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1


def test_riepilogo_elenca_le_fixture_non_aggiornate(monkeypatch, caplog):
    preds, matches = _dataset(6)
    rotta = preds[2]["fixture_id"]
    _install(monkeypatch, _FakeSupabase(preds, matches, rpc_max_ok=10 ** 9,
                                        row_always_timeout={rotta}))
    with caplog.at_level("ERROR"):
        failed = mod.run(DATE, force=False, limit=5000)

    assert failed == 1
    testo = caplog.text
    assert str(rotta) in testo
    assert "57014" in testo  # l'errore vero, non un generico "fallito"
    assert "elenco completo" in testo


def test_elenco_falliti_non_viene_troncato(monkeypatch, caplog):
    """Nel caso peggiore serve l'elenco COMPLETO per il recupero manuale."""
    preds, matches = _dataset(60)
    rotte = {p["fixture_id"] for p in preds}
    _install(monkeypatch, _FakeSupabase(preds, matches, rpc_max_ok=10 ** 9,
                                        row_always_timeout=rotte))
    with caplog.at_level("ERROR"):
        failed = mod.run(DATE, force=False, limit=5000)

    assert failed == 60
    riga = [l for l in caplog.text.splitlines() if "elenco completo" in l][0]
    for fx in rotte:
        assert str(fx) in riga


def test_errore_transitorio_di_rete_viene_recuperato(monkeypatch):
    preds, matches = _dataset(6)
    ballerina = preds[1]["fixture_id"]
    sb = _install(
        monkeypatch,
        _FakeSupabase(preds, matches, rpc_max_ok=0, row_flaky={ballerina: 2}),
    )
    failed = mod.run(DATE, force=False, limit=5000)
    assert failed == 0
    assert sb.update_calls.count(ballerina) == 3  # 2 KO + 1 OK
    assert sorted(sb.written) == sorted(p["fixture_id"] for p in preds)


def test_errore_logico_non_viene_ritentato(monkeypatch, _no_sleep):
    preds, matches = _dataset(4)
    rotta = preds[0]["fixture_id"]
    sb = _install(
        monkeypatch,
        _FakeSupabase(preds, matches, rpc_max_ok=0, row_logic_error={rotta}),
    )
    failed = mod.run(DATE, force=False, limit=5000)
    assert failed == 1
    assert sb.update_calls.count(rotta) == 1   # nessun retry su un 23502
    assert _no_sleep == []


def test_rpc_assente_fallback_integrale(monkeypatch):
    preds, matches = _dataset(8)
    sb = _install(monkeypatch, _FakeSupabase(preds, matches, rpc_missing=True))
    failed = mod.run(DATE, force=False, limit=5000)
    assert failed == 0
    assert sorted(sb.written) == sorted(p["fixture_id"] for p in preds)
    assert len(sb.rpc_calls) == 1  # provata una volta, poi tutto riga-per-riga


# =========================================================================
# 2-bis) la RPC che NON conferma le scritture non e' un successo (A2)
# =========================================================================

def test_rpc_che_risponde_zero_non_viene_data_per_riuscita(monkeypatch):
    """La RPC dice 'ho aggiornato 0 righe' e non scrive: i payload vanno riscritti."""
    preds, matches = _dataset(60)
    sb = _install(monkeypatch, _FakeSupabase(preds, matches, rpc_reply=0))

    failed = mod.run(DATE, force=False, limit=5000)

    # il riga-per-riga ha scritto davvero tutto -> nessun fallimento residuo
    assert failed == 0
    assert sorted(sb.written) == sorted(p["fixture_id"] for p in preds)
    assert sorted(set(sb.update_calls)) == sorted(p["fixture_id"] for p in preds)


def test_rpc_con_esito_ignoto_passa_al_riga_per_riga(monkeypatch):
    """resp.data non e' un intero: esito IGNOTO, mai dato per riuscito."""
    preds, matches = _dataset(10)
    sb = _install(monkeypatch, _FakeSupabase(preds, matches, rpc_reply=[{"x": 1}]))

    failed = mod.run(DATE, force=False, limit=5000)

    assert failed == 0
    assert sorted(sb.written) == sorted(p["fixture_id"] for p in preds)
    assert sorted(set(sb.update_calls)) == sorted(p["fixture_id"] for p in preds)


def test_righe_sparite_finiscono_nei_falliti_con_exit_non_zero(monkeypatch, caplog):
    """La RPC aggiorna meno righe dei payload perche' una riga non esiste piu':
    nemmeno l'UPDATE puntuale puo' scriverla -> fallita, run rosso."""
    preds, matches = _dataset(10)
    sparita = preds[4]["fixture_id"]
    # la riga sparisce da fixture_predictions DOPO la lettura (delete
    # concorrente): il payload esiste, la riga da aggiornare no.
    sb = _FakeSupabase(preds, matches, elimina_alla_prima_rpc=sparita)
    _install(monkeypatch, sb)

    with caplog.at_level("ERROR"):
        failed = mod.run(DATE, force=False, limit=5000)

    assert failed == 1
    assert sparita not in sb.written
    assert sorted(sb.written) == sorted(p["fixture_id"] for p in preds
                                        if p["fixture_id"] != sparita)
    assert str(sparita) in caplog.text
    assert "NON scritto" in caplog.text


# =========================================================================
# 3) letture: deterministiche, a fette, complete
# =========================================================================

def test_lettura_predictions_completa_e_ordinata(monkeypatch):
    preds, matches = _dataset(1200)
    sb = _FakeSupabase(preds, matches)
    letti, troncata = mod.fetch_predictions_ok_for_date(sb, DATE, force=False, limit=5000)

    assert troncata is False
    assert [r["fixture_id"] for r in letti] == sorted(p["fixture_id"] for p in preds)
    # ogni pagina chiede un ORDER BY esplicito (senza, l'insieme sarebbe incompleto)
    assert all(c["order"] == "fixture_id" for c in sb.select_calls)
    # e usa il KEYSET (gt sull'ultimo fixture_id della pagina), non l'offset
    gt_usati = [v for c in sb.select_calls for kind, col, v in c["filters"]
                if kind == "gt" and col == "fixture_id"]
    assert gt_usati == [letti[499]["fixture_id"], letti[999]["fixture_id"],
                        letti[1199]["fixture_id"]]


def test_server_che_tronca_le_pagine_non_perde_righe(monkeypatch):
    """max-rows del server piu' basso della pagina chiesta: la lettura non deve
    fermarsi sulla pagina corta (sarebbero righe perse in silenzio)."""
    preds, matches = _dataset(900)
    sb = _FakeSupabase(preds, matches, max_rows=137)
    letti, troncata = mod.fetch_predictions_ok_for_date(sb, DATE, force=False, limit=5000)

    assert troncata is False
    assert [r["fixture_id"] for r in letti] == sorted(p["fixture_id"] for p in preds)
    assert len(letti) == 900


def test_lettura_predictions_dimezza_la_pagina_sul_timeout(monkeypatch):
    preds, matches = _dataset(300)
    sb = _FakeSupabase(preds, matches, select_max_ok=200)
    letti, _ = mod.fetch_predictions_ok_for_date(sb, DATE, force=False, limit=5000)

    assert [r["fixture_id"] for r in letti] == sorted(p["fixture_id"] for p in preds)
    assert sb.select_calls[0]["limit"] == mod.FETCH_PAGE       # primo tentativo grande
    assert sb.select_calls[1]["limit"] == mod.FETCH_PAGE // 2  # poi dimezzato


def test_dimezzamento_basato_sulla_pagina_chiesta(monkeypatch):
    """Il dimezzamento parte da `want` (la pagina DAVVERO chiesta): basarsi sulla
    dimensione nominale farebbe ri-chiedere la stessa pagina, altri 8 s di DB."""
    preds, matches = _dataset(1000)
    # la 2a pagina (quella corta, vicino al tetto) va in timeout
    sb = _FakeSupabase(preds, matches, select_fail_at={2})
    letti, _ = mod.fetch_predictions_ok_for_date(sb, DATE, force=False, limit=600)

    assert len(letti) == 600
    # 500 (piena, ok) -> 100 (corta, KO) -> 50 = meta' di 100.
    # Dimezzando la dimensione nominale (500 -> 250) si sarebbe ri-chiesta la
    # STESSA pagina da 100: altri 8 s di DB per lo stesso identico timeout.
    assert [c["limit"] for c in sb.select_calls[:4]] == [500, 100, 50, 50]


def test_pagina_al_minimo_ritenta_sul_timeout(monkeypatch, _no_sleep):
    """Con la pagina gia' al minimo un 57014 momentaneo non deve abbattere il run."""
    preds, matches = _dataset(30)
    sb = _FakeSupabase(preds, matches, select_fail_times=2)
    letti, _ = mod.fetch_predictions_ok_for_date(
        sb, DATE, force=False, limit=mod.FETCH_MIN_PAGE
    )

    assert [r["fixture_id"] for r in letti] == sorted(p["fixture_id"] for p in preds)
    assert len(_no_sleep) == 2          # due attese, poi la pagina e' passata
    # i tre tentativi chiedono la STESSA pagina minima: nessun dimezzamento
    # inutile sotto il minimo (e nessuna pagina identica ri-chiesta a vuoto)
    assert [c["limit"] for c in sb.select_calls[:3]] == [mod.FETCH_MIN_PAGE] * 3


def test_pagina_al_minimo_si_arrende_dopo_i_tentativi(monkeypatch):
    preds, matches = _dataset(30)
    sb = _FakeSupabase(preds, matches, select_fail_times=99)
    with pytest.raises(APIError):
        mod.fetch_predictions_ok_for_date(sb, DATE, force=False, limit=mod.FETCH_MIN_PAGE)
    assert len(sb.select_calls) == mod.FETCH_MIN_RETRY + 1


def test_paginazione_che_non_avanza_fallisce_invece_di_ciclare(monkeypatch):
    """Se il keyset non avanzasse (ordinamento/filtro rotti) il ciclo di lettura
    girerebbe per sempre: deve fallire rumorosamente, non piantarsi."""
    preds, matches = _dataset(1200)
    sb = _FakeSupabase(preds, matches)
    vero_select = sb._run_select
    chiamate = {"n": 0}

    def _select_senza_keyset(q: _SelectQuery):
        chiamate["n"] += 1
        # oltre un numero ragionevole di pagine siamo in ciclo infinito
        assert chiamate["n"] <= 20, "ciclo infinito: la paginazione non avanza"
        q.filters = [f for f in q.filters if f[0] != "gt"]
        return vero_select(q)

    sb._run_select = _select_senza_keyset  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="Paginazione predictions bloccata"):
        mod.fetch_predictions_ok_for_date(sb, DATE, force=False, limit=5000)


# ---- tetto --limit (A3) ----------------------------------------------------

def test_tetto_limit_con_altre_righe_da_leggere_esce_non_zero(monkeypatch):
    preds, matches = _dataset(60)
    sb = _install(monkeypatch, _FakeSupabase(preds, matches))

    problemi = mod.run(DATE, force=False, limit=10)

    # le 10 lette sono state comunque elaborate e scritte...
    assert len(sb.written) == 10
    # ...ma le altre 50 non sono state lette: il run NON puo' essere verde
    assert problemi >= 1
    monkeypatch.setattr(sys, "argv", ["prog", "--date", DATE, "--limit", "10"])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1


def test_tetto_limit_esatto_senza_altre_righe_esce_zero(monkeypatch):
    """Nessun falso allarme: le righe sono esattamente `limit` e non c'e' altro."""
    preds, matches = _dataset(10)
    sb = _install(monkeypatch, _FakeSupabase(preds, matches))

    problemi = mod.run(DATE, force=False, limit=10)

    assert problemi == 0
    assert len(sb.written) == 10


def test_limit_non_positivo_viene_rifiutato(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog", "--date", DATE, "--limit", "0"])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2  # errore di argparse, non un run "verde a vuoto"


# ---- matches ---------------------------------------------------------------

def test_lettura_matches_completa_a_blocchi_piccoli(monkeypatch):
    preds, matches = _dataset(450)
    sb = _FakeSupabase(preds, matches)
    mappa = mod.fetch_matches_map(sb, [p["fixture_id"] for p in preds])

    assert sorted(mappa) == sorted(m["fixture_id"] for m in matches)
    # blocchi PICCOLI (erano 200): tetto scritto a mano apposta
    assert mod.MATCHES_CHUNK <= 100
    assert all(len(c["filters"][-1][2]) <= 100
               for c in sb.select_calls if c["table"] == "matches")


def test_lettura_matches_dimezza_il_blocco_sul_timeout(monkeypatch):
    preds, matches = _dataset(200)
    sb = _FakeSupabase(preds, matches)

    # il finto va in timeout sui blocchi > 40 fixture
    vero_select = sb._run_select

    def _select(q):
        for kind, col, vals in q.filters:
            if kind == "in" and len(vals) > 40:
                sb.select_calls.append({"table": q.table, "filters": list(q.filters),
                                        "order": q.order_by, "limit": q.limit_n})
                raise _timeout_error()
        return vero_select(q)

    sb._run_select = _select  # type: ignore[method-assign]
    mappa = mod.fetch_matches_map(sb, [p["fixture_id"] for p in preds])
    assert sorted(mappa) == sorted(m["fixture_id"] for m in matches)


def test_lettura_matches_errore_logico_non_silenziato(monkeypatch):
    preds, matches = _dataset(10)
    sb = _FakeSupabase(preds, matches)

    def _boom(_q):
        raise _logic_error()

    sb._run_select = _boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        mod.fetch_matches_map(sb, [p["fixture_id"] for p in preds])


# =========================================================================
# 4) idempotenza
# =========================================================================

def test_rilancio_dopo_successo_non_riscrive_nulla(monkeypatch):
    preds, matches = _dataset(30)
    sb = _install(monkeypatch, _FakeSupabase(preds, matches))

    assert mod.run(DATE, force=False, limit=5000) == 0
    stato_primo_giro = copy.deepcopy(sb._index)
    scritte_primo_giro = dict(sb.written)
    rpc_primo_giro = len(sb.rpc_calls)

    sb.written.clear()
    assert mod.run(DATE, force=False, limit=5000) == 0

    # secondo giro: nessuna nuova scrittura, stato finale identico
    assert sb.written == {}
    assert len(sb.rpc_calls) == rpc_primo_giro
    assert sb.update_calls == []
    assert sb._index == stato_primo_giro
    assert len(scritte_primo_giro) == 30


# =========================================================================
# 5) equivalenza con il codice ORIGINALE (git show <COMMIT_BASE>:...)
# =========================================================================

# Commit BASE del ramo di fix: l'ultima versione dello script PRIMA di questo
# lavoro. Deve restare fisso: ancorarlo a HEAD non avrebbe senso, perche' una
# volta committato il fix HEAD E' il codice nuovo e il confronto diventerebbe
# nuovo-contro-nuovo, cioe' verde a vuoto.
COMMIT_BASE = "2f1c549"


@pytest.fixture(scope="module")
def modulo_originale(tmp_path_factory):
    """Carica lo script com'era al commit base (prima del fix) per confrontare."""
    try:
        esito = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show",
             f"{COMMIT_BASE}:Prediction/predictions_results_backfill.py"],
            capture_output=True, check=True,
        )
        src = esito.stdout.decode("utf-8")
    except Exception as exc:  # commit/git non disponibili: il confronto non e' eseguibile
        pytest.skip(
            f"impossibile leggere Prediction/predictions_results_backfill.py al commit "
            f"base {COMMIT_BASE} (git show fallito: {exc}): il confronto di equivalenza "
            f"NON e' stato eseguito."
        )

    path = tmp_path_factory.mktemp("orig") / "orig_backfill.py"
    path.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("orig_backfill", path)
    assert spec and spec.loader
    orig = importlib.util.module_from_spec(spec)
    sys.modules["orig_backfill"] = orig
    spec.loader.exec_module(orig)

    # SANITA' DEL RIFERIMENTO: se per sbaglio si confrontasse il codice nuovo
    # con se stesso, il test deve dichiararsi rotto invece di passare a vuoto.
    assert not hasattr(orig, "_recupera_chunk_non_confermato"), (
        f"{COMMIT_BASE} non e' il codice PRIMA del fix: contiene gia' le novita'."
    )
    assert not hasattr(orig, "RPC_MIN_CHUNK"), (
        f"{COMMIT_BASE} non e' il codice PRIMA del fix: contiene gia' RPC_MIN_CHUNK."
    )
    assert orig.RPC_BULK_CHUNK == 500, (
        f"{COMMIT_BASE} non e' il codice PRIMA del fix: RPC_BULK_CHUNK="
        f"{orig.RPC_BULK_CHUNK} invece di 500."
    )
    # ...e il modulo nuovo deve essere davvero un altro: se fossero lo stesso
    # oggetto o la stessa versione, il confronto non proverebbe nulla.
    assert orig is not mod and mod.RPC_BULK_CHUNK != orig.RPC_BULK_CHUNK
    return orig


def _senza_timestamp(body: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in body.items() if k != "evaluated_at"}


def test_campi_hit_identici_a_prima(modulo_originale):
    """La matematica (hit_winner / hit_win_or_draw / hit_under_over) non cambia."""
    preds, matches = _dataset(400)
    for p, m in zip(preds, matches):
        nuovo = mod.evaluate(p, m)
        vecchio = modulo_originale.evaluate(p, m)
        assert (nuovo is None) == (vecchio is None)
        if nuovo is not None:
            assert _senza_timestamp(nuovo) == _senza_timestamp(vecchio)
            assert isinstance(nuovo["evaluated_at"], str)
    # casi limite: match non finito e goals null
    for stato in ("NS", "1H", "PST", "CANC"):
        assert mod.evaluate(preds[0], _match(1, status=stato)) is None
        assert modulo_originale.evaluate(preds[0], _match(1, status=stato)) is None
    senza_gol = {"fixture_id": 1, "status_short": "FT", "goals_home": None,
                 "goals_away": None, "home_team_id": 100, "away_team_id": 200}
    assert mod.evaluate(preds[0], senza_gol) is None
    assert modulo_originale.evaluate(preds[0], senza_gol) is None


def test_percorso_senza_errori_scrive_esattamente_come_prima(monkeypatch, modulo_originale):
    """Stesso insieme di righe e stessi valori scritti: cambia solo il trasporto."""
    preds, matches = _dataset(120)

    sb_new = _install(monkeypatch, _FakeSupabase(preds, matches))
    assert mod.run(DATE, force=False, limit=5000) == 0

    sb_old = _FakeSupabase(preds, matches)
    monkeypatch.setattr(modulo_originale, "get_supabase_client", lambda: sb_old)
    modulo_originale.run(DATE, force=False, limit=5000)

    assert sorted(sb_new.written) == sorted(sb_old.written)
    for fx, body in sb_old.written.items():
        assert _senza_timestamp(sb_new.written[fx]) == _senza_timestamp(body)
        assert isinstance(sb_new.written[fx]["evaluated_at"], str)
    # nessun UPDATE puntuale in piu' rispetto a prima (stesso carico sul DB)
    assert sb_new.update_calls == [] == sb_old.update_calls


def test_missing_match_elencato_non_solo_contato(monkeypatch, caplog):
    preds, matches = _dataset(6)
    orfana = preds[3]["fixture_id"]
    matches = [m for m in matches if m["fixture_id"] != orfana]
    _install(monkeypatch, _FakeSupabase(preds, matches))

    with caplog.at_level("WARNING"):
        failed = mod.run(DATE, force=False, limit=5000)

    assert failed == 0  # missing_match non e' un fallimento di scrittura
    assert "missing_match" in caplog.text
    assert str(orfana) in caplog.text
