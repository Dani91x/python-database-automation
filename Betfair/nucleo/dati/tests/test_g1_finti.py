"""W1-G1 - i finti del comparto G (archivio e postino) e la prova che parlano come il vero.

I finti NON sono finti del client: il client e' il VERO ``supabase``/``postgrest``/``httpx``
con un ``httpx.MockTransport`` al posto della rete (modello: ``test_catchup_rete_2026_10_08.py``).
Dietro il trasporto ci sono due "database":

* ``PostgrestFinto``: risponde come PostgREST (rotta ``/rest/v1/rpc/<nome>``, corpi d'errore
  ``{code, message, details, hint}``) e applica in Python la STESSA semantica delle RPC della
  migrazione ``architettura_uid_ombra_2026-10-09.sql`` sulle tabelle vere (colonne, CHECK,
  chiavi esterne e indici unici copiati dalle migrazioni del repo, file:riga nei commenti);
* ``PgPonte``: inoltra la chiamata a un PostgreSQL VERO (usa-e-getta, variabile ``G1_PG_PSQL``)
  con la migrazione applicata: e' la prova che il finto e il vero rispondono uguale
  (``test_g1_pg_reale.py``).

``CloudProva`` implementa il protocollo ``Cloud`` sul client vero (come fara' ``cloud.py`` di
W1-G2, che qui non si tocca).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import httpx
import pytest
import supabase
from postgrest.exceptions import APIError
from supabase import ClientOptions

from Betfair.nucleo.dati.contratto import SpecTabella
from Betfair.nucleo.dati.schema_locale import rev_ordinabile

# ---------------------------------------------------------------------------
# registro di prova: forme VERE delle tabelle (le righe del registro sono di W1-G2)
# ---------------------------------------------------------------------------
SPEC: Dict[str, SpecTabella] = {s.nome: s for s in (
    # log con uid (migrations/mike_bot.sql:124-130 + migrazione G1)
    SpecTabella("mike_activity", ("uid",), "ARC", "log", 60.0, False, None, ()),
    SpecTabella("scalper_activity", ("uid",), "ARC", "log", 60.0, False, None, ()),
    SpecTabella("omega_activity", ("uid",), "ARC", "log", 60.0, False, None, ()),
    SpecTabella("safe_strategy_activity", ("uid",), "ARC", "log", 60.0, False, None, ()),
    # journal (migrations/betfair_live_pnl_journal.sql:89): CHECK su mode/origin/side
    SpecTabella("betfair_live_journal", ("uid",), "ARC", "log", 60.0, False, None, ()),
    # live_alerts: CHECK su level e FK su live_follow (migrations/live_alerts.sql:22-30)
    SpecTabella("live_alerts", ("uid",), "ARC", "log", 60.0, False, None, ("live_follow",)),
    # padre di live_alerts (migrations/live_stream.sql:34-46), stato vivo
    SpecTabella("live_follow", ("event_id",), "SV", "stato_vivo", 5.0, True, "updated_at", ()),
    # specchio ordini (migrations/betfair_live_order_queue.sql:116), stato del denaro, versione updated_at
    SpecTabella("betfair_live_orders", ("mode", "client_order_ref"), "SV", "stato_denaro", 5.0, False,
                "updated_at", ()),
    # richieste d'ordine: claim su status (betfair_live_order_queue.sql:35)
    SpecTabella("betfair_live_order_requests", ("client_ref",), "CMD", "stato_denaro", 5.0, False, None, ()),
    # heartbeat coalescente (stato vivo, chiave id)
    SpecTabella("betfair_live_heartbeat", ("id",), "SV", "stato_vivo", 15.0, True, None, ()),
)}


def riga_attivita(i: int, kind: str = "giro", **extra: Any) -> Dict[str, Any]:
    """Una riga di ``mike_activity`` con le colonne VERE (mike/db.py:71-81)."""
    r: Dict[str, Any] = {"kind": kind, "payload": {"i": i, "nota": "prova"}, "event_id": "35760084"}
    r.update(extra)
    return r


def riga_ordine(ref: str, stato: str, updated_at: str, **extra: Any) -> Dict[str, Any]:
    """Una riga di ``betfair_live_orders`` con le colonne VERE (stream/db.py:773-835)."""
    r = {"mode": "paper", "client_order_ref": ref, "market_id": "1.234", "selection_id": 47972, "side": "back",
         "price": 2.0, "size": 2.0, "status": stato, "updated_at": updated_at, "event_id": "35760084"}
    r.update(extra)
    return r


# ---------------------------------------------------------------------------
# PostgREST finto (semantica delle RPC della migrazione G1)
# ---------------------------------------------------------------------------
class ErrorePg(Exception):
    def __init__(self, codice: str, messaggio: str) -> None:
        super().__init__(messaggio)
        self.codice = codice
        self.messaggio = messaggio


@dataclass
class TabellaFinta:
    nome: str
    colonne: Sequence[str]
    uniche: Sequence[Tuple[str, ...]]
    check: Sequence[Tuple[str, Callable[[Mapping[str, Any]], bool]]] = ()
    fk: Mapping[str, Tuple[str, str]] = field(default_factory=dict)
    righe: List[Dict[str, Any]] = field(default_factory=list)
    prossimo_id: int = 1


def _tabelle_vere() -> Dict[str, TabellaFinta]:
    t = [
        TabellaFinta("mike_activity", ("id", "ts", "event_id", "kind", "payload", "uid"), [("id",), ("uid",)]),
        TabellaFinta("scalper_activity", ("id", "event_id", "ts", "kind", "payload", "uid"), [("id",), ("uid",)]),
        TabellaFinta("omega_activity", ("id", "ts", "kind", "payload", "uid"), [("id",), ("uid",)]),
        TabellaFinta("safe_strategy_activity", ("id", "ts", "kind", "payload", "uid"), [("id",), ("uid",)]),
        TabellaFinta("betfair_live_journal", ("id", "ts", "mode", "request_id", "action", "origin", "event_id",
                                              "market_id", "market_name", "selection_id", "side", "price", "size",
                                              "persistence", "bet_id", "minute", "score_home", "score_away", "inplay",
                                              "ltp", "best_back", "best_lay", "book", "signals", "params", "tag",
                                              "note", "uid"), [("id",), ("uid",)],
                     check=[("betfair_live_journal_mode_check", lambda r: r.get("mode") in ("paper", "live")),
                            ("betfair_live_journal_origin_check",
                             lambda r: r.get("origin", "manual") in ("manual", "risk_rule", None))]),
        TabellaFinta("live_alerts", ("id", "level", "code", "message", "event_id", "acknowledged", "created_at", "uid"),
                     [("id",), ("uid",)],
                     check=[("live_alerts_level_check", lambda r: r.get("level") in ("INFO", "WARN", "CRITICAL"))],
                     fk={"event_id": ("live_follow", "event_id")}),
        TabellaFinta("live_follow", ("event_id", "fixture_id", "watchlist_id", "league_name", "home_name", "away_name",
                                     "open_date", "status", "error_detail", "created_at", "updated_at"), [("event_id",)]),
        TabellaFinta("betfair_live_orders", ("id", "bet_id", "client_order_ref", "request_id", "mode", "event_id",
                                             "market_id", "selection_id", "handicap", "side", "order_type", "price",
                                             "size", "size_matched", "size_remaining", "size_cancelled", "size_lapsed",
                                             "size_voided", "average_price_matched", "status", "persistence",
                                             "placed_at", "matched_at", "updated_at"), [("id",), ("mode", "client_order_ref")],
                     check=[("betfair_live_orders_side_check", lambda r: r.get("side") in ("back", "lay"))]),
        TabellaFinta("betfair_live_order_requests", ("id", "client_ref", "action", "mode", "market_id", "selection_id",
                                                     "handicap", "side", "order_type", "price", "size", "status",
                                                     "result", "error", "requested_at", "processed_at"),
                     [("id",), ("client_ref",)]),
        TabellaFinta("betfair_live_heartbeat", ("id", "runner", "ts", "detail"), [("id",)]),
    ]
    tutte = {x.nome: x for x in t}
    for x in t:
        if x.nome in ("mike_activity", "scalper_activity", "live_alerts", "betfair_live_orders"):
            tutte[x.nome + "_ombra"] = TabellaFinta(x.nome + "_ombra", x.colonne, x.uniche, x.check, {})
    return tutte


class PostgrestFinto:
    """Il server dietro il trasporto. ``copione``: azioni da usare una per richiesta
    (``None`` = normale). ``offline``: ogni richiesta solleva ``httpx.ConnectError``."""

    def __init__(self) -> None:
        self.tabelle = _tabelle_vere()
        self.copione: List[Optional[str]] = []
        self.offline = False
        self.richieste: List[Tuple[str, Dict[str, Any]]] = []
        self.senza_rpc = False
        # come public.postino_versioni: json([tabella, chiave, origine]) -> versione piu' alta applicata
        self.versioni: Dict[str, int] = {}

    # -- trasporto ---------------------------------------------------------
    def trasporto(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.gestisci)

    def gestisci(self, req: httpx.Request) -> httpx.Response:
        if self.offline:
            raise httpx.ConnectError("[Errno 111] Connection refused", request=req)
        rotta = req.url.path.replace("/rest/v1", "")
        if b"\\u0000" in (req.content or b""):
            # come PostgreSQL: il jsonb non ammette \u0000 (22P05), TUTTA la chiamata fallisce
            return httpx.Response(400, json={"code": "22P05", "details": "\\u0000 cannot be converted to text.",
                                             "hint": None, "message": "unsupported Unicode escape sequence"})
        corpo = json.loads(req.content or b"null")
        self.richieste.append((rotta, corpo))
        azione = self.copione.pop(0) if self.copione else None
        if azione == "connect":
            raise httpx.ConnectError("[Errno 111] Connection refused", request=req)
        if azione == "goaway":
            raise httpx.RemoteProtocolError("<ConnectionTerminated error_code:0, last_stream_id:19999, "
                                            "additional_data:None>", request=req)
        if azione == "html520":
            return httpx.Response(520, content=b"<!DOCTYPE html><html><head><title>supabase.co | 520: Web server "
                                               b"is returning an unknown error</title></head></html>",
                                  headers={"content-type": "text/html; charset=UTF-8"})
        if azione == "57014":
            return httpx.Response(500, json={"code": "57014", "details": None, "hint": None,
                                             "message": "canceling statement due to statement timeout"})
        if self.senza_rpc or azione == "pgrst202":
            nome = rotta.rsplit("/", 1)[-1]
            return httpx.Response(404, json={"code": "PGRST202", "details": f"Searched for the function public.{nome}",
                                             "hint": None, "message": f"Could not find the function public.{nome} "
                                                                      "in the schema cache"})
        try:
            dati = self.rpc(rotta.rsplit("/", 1)[-1], corpo)
        except ErrorePg as exc:
            return httpx.Response(400, json={"code": exc.codice, "details": None, "hint": None, "message": exc.messaggio})
        if azione == "applica_poi_perdi":
            # la richiesta e' ARRIVATA al DB ed e' stata applicata; la risposta si perde
            raise httpx.RemoteProtocolError("<ConnectionTerminated error_code:0, last_stream_id:19999, "
                                            "additional_data:None>", request=req)
        return httpx.Response(200, json=dati)

    # -- RPC -----------------------------------------------------------------
    def rpc(self, nome: str, a: Dict[str, Any]) -> Any:
        if nome == "postino_consegna":
            return self.consegna(a["p_tabella"], a["p_op"], a["p_conflitto"], a["p_righe"], a.get("p_origine"),
                                 a.get("p_versioni"))
        if nome == "postino_impronte":
            return self.impronte(a)
        if nome == "postino_confronta_ombra":
            return self.confronta_ombra(a)
        raise ErrorePg("PGRST202", f"Could not find the function public.{nome}")

    def consegna(self, tabella: str, op: str, conflitto: List[str], righe: List[Dict[str, Any]],
                 origine: Optional[str] = None, versioni: Optional[List[Optional[int]]] = None) -> List[Dict[str, Any]]:
        if op not in ("insert", "upsert", "patch", "delete"):
            raise ErrorePg("GP001", f"operazione non ammessa: {op}")
        if versioni is not None and len(versioni) != len(righe):
            raise ErrorePg("GP001", "postino_consegna: p_versioni deve essere un array lungo quanto p_righe")
        t = self.tabelle.get(tabella)
        if t is None:
            raise ErrorePg("42P01", f"postino_consegna: tabella public.{tabella} assente")
        if not set(conflitto) <= set(t.colonne):
            raise ErrorePg("42703", f"postino_consegna: {tabella} non ha le colonne di conflitto")
        if op in ("insert", "upsert") and tuple(sorted(conflitto)) not in {tuple(sorted(u)) for u in t.uniche}:
            raise ErrorePg("42P10", f"postino_consegna: nessun indice unico su {tabella}")
        esiti = []
        for i, r in enumerate(righe):
            ver = versioni[i] if versioni is not None and isinstance(versioni[i], int) else None
            try:
                esiti.append({"esito": self._una(t, op, conflitto, r, origine, ver)})
            except ErrorePg as exc:
                esiti.append({"esito": "errore", "codice": exc.codice, "messaggio": exc.messaggio})
        return esiti

    def _una(self, t: TabellaFinta, op: str, conflitto: List[str], r: Dict[str, Any], origine: Optional[str],
             ver: Optional[int]) -> str:
        ignote = sorted(set(r) - set(t.colonne))
        if ignote:
            raise ErrorePg("42703", f"colonne sconosciute in {t.nome}: {ignote}")
        if not set(conflitto) <= set(r):
            raise ErrorePg("22023", f"manca la chiave naturale {conflitto}")
        chiave = tuple(r[c] for c in conflitto)
        # come la RPC: versione LOCALE confrontata SOLO con la stessa origine (postino_versioni)
        guardia = origine is not None and ver is not None and op != "insert"
        kv = json.dumps([t.nome, list(chiave), origine])
        if guardia and kv in self.versioni:
            if self.versioni[kv] > ver:
                return "vecchia"
            if self.versioni[kv] == ver:
                return "ignorata"
        esito = self._scrivi_riga(t, op, conflitto, chiave, r)       # ErrorePg: la versione non resta
        if guardia:
            self.versioni[kv] = max(self.versioni.get(kv, ver), ver)
        return esito

    def _scrivi_riga(self, t: TabellaFinta, op: str, conflitto: List[str], chiave: Tuple[Any, ...],
                     r: Dict[str, Any]) -> str:
        esistente = next((x for x in t.righe if tuple(x.get(c) for c in conflitto) == chiave), None)
        if op == "delete":
            if esistente is None:
                return "ignorata"
            t.righe.remove(esistente)
            return "ok"
        if op == "patch":
            if esistente is None:
                return "ignorata"
            nuova = {**esistente, **r}
            self._vincoli(t, nuova)
            esistente.update(r)
            return "ok"
        if esistente is not None:
            if op == "insert" or set(r) <= set(conflitto):
                return "ignorata"
            nuova = {**esistente, **r}
            self._vincoli(t, nuova)
            esistente.update(r)
            return "ok"
        nuova = {c: None for c in t.colonne}
        if "id" in t.colonne and "id" not in conflitto:
            nuova["id"] = t.prossimo_id
        nuova.update(r)
        self._vincoli(t, nuova)
        for u in t.uniche:
            k = tuple(nuova.get(c) for c in u)
            if None not in k and any(tuple(x.get(c) for c in u) == k for x in t.righe):
                raise ErrorePg("23505", f"duplicate key value violates unique constraint on {u}")
        if "id" in t.colonne and "id" not in conflitto:
            t.prossimo_id += 1
        t.righe.append(nuova)
        return "ok"

    def _vincoli(self, t: TabellaFinta, r: Mapping[str, Any]) -> None:
        for nome, ok in t.check:
            if not ok(r):
                raise ErrorePg("23514", f'new row for relation "{t.nome}" violates check constraint "{nome}"')
        for col, (padre, col_p) in t.fk.items():
            v = r.get(col)
            if v is not None and not any(x.get(col_p) == v for x in self.tabelle[padre].righe):
                raise ErrorePg("23503", f'insert or update on table "{t.nome}" violates foreign key constraint '
                                        f'"{t.nome}_{col}_fkey"')

    def impronte(self, a: Mapping[str, Any]) -> List[List[Any]]:
        t = self.tabelle[a["p_tabella"]]
        chiave, rev, col_t = a["p_chiave"], a.get("p_rev"), a.get("p_colonna_tempo")
        da = rev_ordinabile(a["p_da"]) if a.get("p_da") else None
        fino = rev_ordinabile(a["p_a"]) if a.get("p_a") else None
        cercate = [list(k) for k in (a.get("p_chiavi") or [])]
        out = []
        for r in t.righe:
            k = [r.get(c) for c in chiave]
            nel_tempo = (col_t is not None and da is not None and r.get(col_t) is not None and None not in k
                         and rev_ordinabile(r[col_t]) >= da and (fino is None or rev_ordinabile(r[col_t]) < fino))
            if nel_tempo or k in cercate:
                out.append([k, r.get(rev) if rev else None])
        return out

    def confronta_ombra(self, a: Mapping[str, Any]) -> List[Dict[str, Any]]:
        da, fino = rev_ordinabile(a["p_da"]), rev_ordinabile(a["p_a"])

        def conta(nome: str) -> Dict[Tuple[str, str], int]:
            out: Dict[Tuple[str, str], int] = {}
            for r in self.tabelle[nome].righe:
                v = r.get(a["p_colonna_tempo"])
                if v is None or not (da <= rev_ordinabile(v) < fino):
                    continue
                k = (str(v)[:10], json.dumps([r.get(c) for c in a["p_gruppo"]]))
                out[k] = out.get(k, 0) + 1
            return out

        vera, ombra = conta(a["p_tabella"]), conta(a["p_tabella"] + "_ombra")
        return [{"giorno": k[0], "gruppo": json.loads(k[1]), "vera": vera.get(k, 0), "ombra": ombra.get(k, 0)}
                for k in sorted(set(vera) | set(ombra)) if vera.get(k, 0) != ombra.get(k, 0)]


# ---------------------------------------------------------------------------
# ponte verso un PostgreSQL VERO (facoltativo)
# ---------------------------------------------------------------------------
_SQL_RPC = {
    "postino_consegna": ("public.postino_consegna(p_tabella := a->>'p_tabella', p_op := a->>'p_op', "
                         "p_conflitto := ARRAY(SELECT jsonb_array_elements_text(a->'p_conflitto')), "
                         "p_righe := a->'p_righe', p_origine := a->>'p_origine', p_versioni := a->'p_versioni')"),
    "postino_impronte": ("public.postino_impronte(p_tabella := a->>'p_tabella', "
                         "p_chiave := ARRAY(SELECT jsonb_array_elements_text(a->'p_chiave')), p_rev := a->>'p_rev', "
                         "p_colonna_tempo := a->>'p_colonna_tempo', p_da := (a->>'p_da')::timestamptz, "
                         "p_a := (a->>'p_a')::timestamptz, p_chiavi := coalesce(a->'p_chiavi', '[]'::jsonb))"),
    "postino_confronta_ombra": ("public.postino_confronta_ombra(p_tabella := a->>'p_tabella', "
                                "p_gruppo := ARRAY(SELECT jsonb_array_elements_text(a->'p_gruppo')), "
                                "p_colonna_tempo := a->>'p_colonna_tempo', p_da := (a->>'p_da')::timestamptz, "
                                "p_a := (a->>'p_a')::timestamptz)"),
}


def psql_argomenti() -> Optional[List[str]]:
    """``G1_PG_PSQL="-h /tmp -p 54329 -U postgres"`` per il PostgreSQL usa-e-getta."""
    v = (os.environ.get("G1_PG_PSQL") or "").strip()
    return v.split() if v else None


def psql(sql: str) -> subprocess.CompletedProcess[str]:
    args = psql_argomenti()
    assert args, "G1_PG_PSQL non impostata"
    return subprocess.run(["psql", *args, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose"],
                          input=sql, capture_output=True, text=True, timeout=60)


class PgPonte(PostgrestFinto):
    """Come ``PostgrestFinto`` ma le RPC le esegue il PostgreSQL vero, come ``service_role``."""

    def rpc(self, nome: str, a: Dict[str, Any]) -> Any:
        if nome not in _SQL_RPC:
            raise ErrorePg("PGRST202", f"Could not find the function public.{nome}")
        etichetta = "a" + uuid.uuid4().hex
        sql = (f"SET ROLE service_role;\nSELECT {_SQL_RPC[nome]} FROM (SELECT ${etichetta}${json.dumps(a)}"
               f"${etichetta}$::jsonb AS a) AS x;\n")
        r = psql(sql)
        if r.returncode != 0:
            m = re.search(r"ERROR:\s+([0-9A-Z]{5}):\s*(.*)", r.stderr)
            if m is None:
                raise RuntimeError(f"psql: {r.stderr[:400]}")
            raise ErrorePg(m.group(1), m.group(2).strip())
        return json.loads(r.stdout.strip() or "null")


# ---------------------------------------------------------------------------
# il protocollo Cloud sul client VERO
# ---------------------------------------------------------------------------
class CloudProva:
    """``contratto.Cloud`` sul client supabase VERO (W1-G2 scrivera' quello di produzione)."""

    def __init__(self, server: PostgrestFinto) -> None:
        self.server = server
        self.client = supabase.create_client(
            "https://abc.supabase.co", "x" * 40,
            options=ClientOptions(httpx_client=httpx.Client(transport=server.trasporto())))

    def leggi(self, tabella: str, filtri: Mapping[str, Any], *, cache_s: float = 0.0) -> Sequence[Mapping[str, Any]]:
        q = self.client.table(tabella).select("*")
        for k, v in filtri.items():
            q = q.eq(k, v)
        return q.execute().data

    def rpc(self, nome: str, args: Mapping[str, Any], *, cache_s: float = 0.0) -> Any:
        return self.client.rpc(nome, dict(args)).execute().data


# ---------------------------------------------------------------------------
# prove che i finti parlano come il vero client si aspetta
# ---------------------------------------------------------------------------
def test_client_vero_sul_finto_rpc_ed_errori() -> None:
    srv = PostgrestFinto()
    cloud = CloudProva(srv)
    esiti = cloud.rpc("postino_consegna", {"p_tabella": "mike_activity", "p_op": "insert", "p_conflitto": ["uid"],
                                           "p_righe": [{"uid": "u1", "kind": "k"}], "p_origine": None,
                                           "p_versioni": None})
    assert esiti == [{"esito": "ok"}]
    assert srv.richieste[-1][0] == "/rpc/postino_consegna"
    # tabella assente: APIError VERA costruita da postgrest sul corpo di PostgREST
    with pytest.raises(APIError) as e:
        cloud.rpc("postino_consegna", {"p_tabella": "nessuna", "p_op": "insert", "p_conflitto": ["uid"],
                                       "p_righe": []})
    assert e.value.code == "42P01"
    srv.copione = ["pgrst202"]
    with pytest.raises(APIError) as e2:
        cloud.rpc("postino_consegna", {})
    assert e2.value.code == "PGRST202"
    srv.offline = True
    with pytest.raises(httpx.ConnectError):
        cloud.rpc("postino_consegna", {})


def test_finto_semantica_versione_e_vincoli() -> None:
    """R1 (terza revisione): versione per ORIGINE; la colonna del bot non decide nulla."""
    srv = PostgrestFinto()
    k = ["mode", "client_order_ref"]
    a = srv.consegna("betfair_live_orders", "upsert", k, [
        riga_ordine("r1", "EXECUTABLE", "2026-10-09T10:00:02+00:00"),
        riga_ordine("r1", "PENDING", "2026-10-09T10:00:01+00:00"),           # updated_at piu' vecchio: VINCE
        riga_ordine("r2", "EXECUTABLE", "2026-10-09T10:00:01+00:00", side="BACK")], "A", [5, 6, 7])
    assert [x["esito"] for x in a] == ["ok", "ok", "errore"]
    assert a[2]["codice"] == "23514"
    assert srv.tabelle["betfair_live_orders"].righe[0]["status"] == "PENDING"
    assert srv.tabelle["betfair_live_orders"].righe[0]["updated_at"] == "2026-10-09T10:00:01+00:00"
    # stessa origine, versione piu' vecchia (ritento tardivo): vecchia; stessa versione: ignorata
    b = srv.consegna("betfair_live_orders", "upsert", k, [riga_ordine("r1", "EXECUTABLE", "x"),
                                                          riga_ordine("r1", "EXECUTABLE", "x")], "A", [5, 6])
    assert [x["esito"] for x in b] == ["vecchia", "ignorata"]
    # altra origine, versione piu' bassa: vince l'ultima arrivata (come oggi)
    c = srv.consegna("betfair_live_orders", "upsert", k, [riga_ordine("r1", "CANCELLED", "y")], "B", [1])
    assert c == [{"esito": "ok"}] and srv.tabelle["betfair_live_orders"].righe[0]["status"] == "CANCELLED"
    # la riga rifiutata non lascia la sua versione
    assert json.dumps(["betfair_live_orders", ["paper", "r2"], "A"]) not in srv.versioni
    d = srv.consegna("live_alerts", "insert", ["uid"], [
        {"uid": "x", "level": "INFO", "code": "c", "message": "m", "event_id": "senza_padre"}])
    assert d[0]["codice"] == "23503"
