"""ATLANTE GLOBALE LEGGERO (09/10/2026, AUDIT_2026-10-09/fallimenti_action/
ATLANTE_GLOBALE_LEGGERO.md). Decisione dell'utente: "sul database dobbiamo
scrivere il piu' leggero possibile; se alcuni dati non servono non c'e' bisogno
di scrivere; nessuna perdita di dati o qualita'".

La riga globale ``hazard_atlas`` porta nel payload SOLO ``meta`` e ``global``
(prima ~24 MB con by_league/by_team/h2h_hint/v4, derivati da
``hazard_atlas_leghe``). Qui si prova:
  1. il payload leggero ha solo le chiavi ammesse e pesa < 1 MB, anche con
     l'atlante grosso (seme v3 vero);
  2. la POST (RPC e ripiego diretto) non contiene MAI h2h_hint/by_team/
     by_league/v4 (byte del corpo VERO, catturati da ``urlopen``);
  3. l'atlante assemblato e il file del modo 'domanda' sono IDENTICI byte per
     byte a prima (sha256 calcolati sul codice di origin/master c4fc5fbf
     PRIMA della modifica): il file che i bot e lo scalper leggono non cambia;
  4. il modo 'scarica' con il payload leggero riassembla dalle righe per lega
     lo STESSO file che scaricava prima (byte identici, stessi stati), con
     paginazione completa e senza toccare il file se le leghe mancano;
  5. 'scarica' = 'domanda': stessi blocchi, meta uguale salvo le chiavi del
     modo;
  6. la migrazione e' idempotente, tiene solo meta/global, nessun DROP/VACUUM.

Stati finti: prodotti dal generatore VERO (``bootstrap`` su un PostgREST
finto con le colonne vere di ``matches``/``match_events``, test del v4
collegato), quindi con le chiavi identiche allo stato vero (cells, teams,
h2h, v4, ...). Le righe di ``hazard_atlas_leghe`` passano per un giro JSON
come la colonna jsonb restituita da PostgREST.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import io
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List

import pytest

from Betfair.stream.scalper import atlante_a_domanda as AD
from Betfair.stream.scalper import genera_atlante as G
from Betfair.stream.scalper import hazard_atlas as HA
from Betfair.stream.scalper import hazard_atlas_sync as SY
from Betfair.stream.tests import test_atlante_v4_collegato_2026_09_25 as TV
from Betfair.stream.tests.test_genera_atlante_2026_09_24 import LettoreFinto, _ev, _match

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
GEN = "2026-10-09T07:25:00+00:00"
WM = 10500510
T_GEN = dt.datetime(2026, 10, 9, 7, 25, tzinfo=dt.timezone.utc).timestamp()
# sha256 misurati sul codice di master c4fc5fbf (checkout principale, PRIMA della
# modifica: stessi stati finti, stesso seme v3, stessa data): vedi referto.
SHA_ASSEMBLA_PRIMA = "31a50deba1deba25e75fabc5da94970cb937c83a7eaef968dabca9508b543661"
SHA_DOMANDA_PRIMA = "a198f49e0111f67bd2b485f73291ea0b2cb49410e18216b7577a89927ed633c2"
VIETATE = ("h2h_hint", "by_team", "by_league", "v4")


def _compatto(obj: Any) -> bytes:
    """Come ``scrivi_json_atomico`` / il vecchio ``sincronizza``."""
    return json.dumps(obj, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def _stati_finti() -> Dict[str, Dict[str, Any]]:
    """Leghe 39/140/835 del test del v4 collegato (squadre 1-2) + lega 61 con
    ESATTAMENTE 3 scontri fra le squadre 3 e 4 (soglia ``MIN_H2H`` sul filo)."""
    st = TV._genera(TV._righe_db(n=600))["stati"]
    db = {"matches": [_match(900 + i, 61, 1, 0, home=3, away=4, season=2025) for i in range(3)],
          "match_events": [_ev(9000 + i, 900 + i, 61, 3, 20 + i, season=2025) for i in range(3)]}
    G.bootstrap(LettoreFinto(db), st, [61], [2025], {}, TV.ADESSO)
    return st


@pytest.fixture(scope="module")
def stati() -> Dict[str, Dict[str, Any]]:
    return _stati_finti()


@pytest.fixture(scope="module")
def seme() -> Dict[str, Any]:
    with open(HA.ATLAS_V3_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _atlante_action(stati: Dict[str, Dict[str, Any]], seme: Dict[str, Any]) -> Dict[str, Any]:
    """L'atlante come lo costruisce ``genera_atlante.main`` nella action: gli stati
    arrivano da ``leggi_stato_db`` in ordine di league_id (``--solo-leghe-in-stato``:
    nessuna lega nuova accodata), e l'ordine decide l'ordine delle chiavi nel file."""
    in_ordine = {k: stati[k] for k in sorted(stati, key=int)}
    atlas = G.assembla(copy.deepcopy(in_ordine), generated_at=GEN, watermark=WM, seme=seme)
    atlas["meta"]["run"] = {"conti": {"incrementale": {"aggiunte": 3}}, "leghe_toccate": [39],
                            "richieste_db": 12, "righe_lette": 3400, "secondi": 41.2}
    return atlas


# ----------------------------------------------------------- 1) payload leggero
def test_payload_leggero_solo_meta_e_global_sotto_1_mb(stati, seme):
    atlas = _atlante_action(stati, seme)
    assert set(atlas) == {"meta", "global", "by_league", "by_team", "h2h_hint", "v4"}
    leggero = G.payload_globale_leggero(atlas)
    assert set(leggero) == {"meta", "global"}
    assert leggero["meta"] == atlas["meta"] and leggero["global"] == atlas["global"]
    # l'atlante del chiamante (file --json, riepilogo) resta intero
    assert set(atlas) == {"meta", "global", "by_league", "by_team", "h2h_hint", "v4"}
    assert len(_compatto(leggero)) < 1_000_000
    assert len(_compatto(atlas)) > 10 * len(_compatto(leggero))


# ----------------------------------------------------------- 2) la POST
class _Risposta:
    def __init__(self, corpo: bytes = b"[]") -> None:
        self._c = corpo

    def __enter__(self) -> "_Risposta":
        return self

    def __exit__(self, *a: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._c


def _cattura(monkeypatch, esiti: List[Any]) -> List[Dict[str, Any]]:
    """urlopen finto: registra i BYTE veri di ogni richiesta; esiti in ordine
    (eccezione da alzare o corpo della 200), l'ultimo si ripete."""
    viste: List[Dict[str, Any]] = []

    def urlopen(req: Any, timeout: float = 0.0) -> Any:
        viste.append({"metodo": req.get_method(), "path": req.full_url.split("/rest/v1/", 1)[1],
                      "dati": req.data})
        e = esiti[min(len(viste) - 1, len(esiti) - 1)]
        if isinstance(e, BaseException):
            raise e
        return _Risposta(e)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return viste


def _404() -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://finto/rest/v1/rpc/x", 404, "Not Found", {},
                                  io.BytesIO(b'{"code":"PGRST202","message":"Could not find '
                                             b'the function"}'))


def _controlla_post(dati: bytes, chiave_payload: str, atlas: Dict[str, Any]) -> None:
    for v in VIETATE:
        assert f'"{v}":'.encode() not in dati.replace(b'"v4":{"name"', b"")  # meta.v4 e' un sommario
    corpo = json.loads(dati)
    assert set(corpo[chiave_payload]) == {"meta", "global"}
    assert corpo[chiave_payload]["meta"] == json.loads(_compatto(atlas["meta"]))
    assert len(dati) < 1_000_000


def test_la_post_della_rpc_non_porta_mai_i_blocchi_derivati(monkeypatch, stati, seme):
    atlas = _atlante_action(stati, seme)
    viste = _cattura(monkeypatch, [b"", b"[]"])          # RPC ok, GET potatura vuota
    G._Scrittore("http://finto", "k", attese=(), sleep=lambda s: None).salva_versione(atlas, tieni=7)
    post = [v for v in viste if v["metodo"] == "POST"]
    assert [v["path"] for v in post] == ["rpc/hazard_atlas_salva_versione"]
    _controlla_post(post[0]["dati"], "p_payload", atlas)
    corpo = json.loads(post[0]["dati"])
    assert corpo["p_n_leghe"] == atlas["meta"]["n_leagues"]
    assert corpo["p_n_partite"] == atlas["meta"]["n_fixtures_used"]
    assert corpo["p_watermark_event_id"] == WM and corpo["p_generated_at"] == GEN


def test_il_ripiego_diretto_non_porta_mai_i_blocchi_derivati(monkeypatch, stati, seme):
    atlas = _atlante_action(stati, seme)
    viste = _cattura(monkeypatch, [_404(), b"", b"[]"])  # RPC assente -> POST diretta
    G._Scrittore("http://finto", "k", attese=(), sleep=lambda s: None).salva_versione(atlas, tieni=7)
    post = [v for v in viste if v["metodo"] == "POST"]
    assert [v["path"] for v in post] == ["rpc/hazard_atlas_salva_versione", "hazard_atlas"]
    for v in post:
        assert b'"h2h_hint"' not in v["dati"] and b'"by_team"' not in v["dati"]
    _controlla_post(post[1]["dati"], "payload", atlas)


# ----------------------------------------------- 3) file dei bot invariato
def test_assembla_identico_a_prima_byte_per_byte(stati, seme):
    b = _compatto(G.assembla(copy.deepcopy(stati), generated_at=GEN, watermark=WM, seme=seme))
    assert hashlib.sha256(b).hexdigest() == SHA_ASSEMBLA_PRIMA


def _file_domanda(tmp_path, stati) -> bytes:
    m = AD.MotoreAtlante(LettoreFinto({}), path_live=str(tmp_path / "live.json"),
                         path_stato=str(tmp_path / "stato.json"), path_seme=HA.ATLAS_V3_PATH,
                         orologio=lambda: T_GEN)
    m.leghe = copy.deepcopy(stati)
    m._scrivi_live(T_GEN)
    return (tmp_path / "live.json").read_bytes()


def test_file_del_modo_domanda_identico_a_prima_byte_per_byte(tmp_path, stati):
    assert hashlib.sha256(_file_domanda(tmp_path, stati)).hexdigest() == SHA_DOMANDA_PRIMA


# ----------------------------------------------- 4) modo 'scarica'
def _db_finto(versioni: List[Dict[str, Any]], leghe: List[Dict[str, Any]]):
    """PostgREST finto per ``sincronizza``: ``hazard_atlas`` (ultima versione,
    payload per id) e ``hazard_atlas_leghe`` (select/order/limit/gt come il vero;
    stato passato per un giro JSON come una colonna jsonb)."""
    chiamate: List[tuple] = []

    def get(url, key, table, params, timeout=30.0):
        chiamate.append((table, dict(params), timeout))
        if table == "hazard_atlas":
            if "id" in params:
                vid = int(params["id"].split(".")[1])
                return [{"payload": json.loads(json.dumps(v["payload"]))}
                        for v in versioni if v["id"] == vid]
            ult = sorted(versioni, key=lambda v: v["generated_at"], reverse=True)[:1]
            return [{"id": v["id"], "generated_at": v["generated_at"]} for v in ult]
        assert table == "hazard_atlas_leghe"
        assert params["select"] == "league_id,stato"
        col, _, verso = params["order"].partition(".")
        rows = sorted(leghe, key=lambda r: r[col], reverse=verso.startswith("desc"))
        if "league_id" in params:
            op, _, val = params["league_id"].partition(".")
            assert op == "gt"
            rows = [r for r in rows if r["league_id"] > int(val)]
        rows = rows[: int(params["limit"])]
        return [{"league_id": r["league_id"], "stato": json.loads(json.dumps(r["stato"]))}
                for r in rows]
    get.chiamate = chiamate
    return get


def _righe_leghe(stati: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Come ``_Scrittore.salva_leghe``: lo stato SENZA la lista dei fixture."""
    return [{"league_id": int(l), "stato": {k: v for k, v in s.items() if k != "fixtures"}}
            for l, s in stati.items()]


def _versione_leggera(atlas: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": 14, "generated_at": GEN, "payload": G.payload_globale_leggero(atlas)}


@pytest.fixture()
def cartella(tmp_path, monkeypatch):
    live = tmp_path / "hazard_atlas_live.json"
    monkeypatch.setattr(HA, "ATLAS_LIVE_PATH", str(live))
    monkeypatch.setattr(HA, "MTIME_CHECK_S", 0.0)
    HA.reset_atlante_condiviso()
    yield live
    HA.reset_atlante_condiviso()


def test_scarica_riassembla_lo_stesso_file_di_prima(cartella, stati, seme):
    atlas = _atlante_action(stati, seme)
    prima = _compatto(json.loads(json.dumps(atlas)))      # cio' che scriveva il vecchio scarica
    get = _db_finto([_versione_leggera(atlas)], _righe_leghe(stati))
    r = SY.sincronizza(url="http://x", key="k", path=str(cartella), get=get)
    assert r["esito"] == "aggiornato" and r["generated_at"] == GEN
    assert cartella.read_bytes() == prima
    # i consumatori lo ricaricano come prima
    assert HA.atlante_condiviso()["meta"]["generated_at"] == GEN
    # seconda passata: una sola GET leggera, nessuna lettura delle leghe
    get2 = _db_finto([_versione_leggera(atlas)], _righe_leghe(stati))
    assert SY.sincronizza(url="http://x", key="k", path=str(cartella), get=get2)["esito"] == \
        "gia_aggiornato"
    assert len(get2.chiamate) == 1


def test_scarica_legge_tutte_le_pagine_delle_leghe(cartella, stati, seme, monkeypatch):
    atlas = _atlante_action(stati, seme)
    monkeypatch.setattr(SY, "PAGINA_LEGHE", 1)            # 4 leghe -> 5 GET (l'ultima vuota)
    get = _db_finto([_versione_leggera(atlas)], _righe_leghe(stati))
    r = SY.sincronizza(url="http://x", key="k", path=str(cartella), get=get)
    assert r["esito"] == "aggiornato"
    assert cartella.read_bytes() == _compatto(json.loads(json.dumps(atlas)))
    pagine = [c for c in get.chiamate if c[0] == "hazard_atlas_leghe"]
    assert [p[1].get("league_id") for p in pagine] == [None, "gt.39", "gt.61", "gt.140", "gt.835"]


def test_scarica_senza_leghe_o_monca_non_tocca_il_file(cartella, stati, seme):
    vecchio = b'{"meta":{"generated_at":"2026-10-01T07:00:00+00:00"},"global":{"x":1},' \
              b'"by_league":{"39":{}}}'
    cartella.write_bytes(vecchio)
    atlas = _atlante_action(stati, seme)
    r = SY.sincronizza(url="http://x", key="k", path=str(cartella),
                       get=_db_finto([_versione_leggera(atlas)], []))
    assert r["esito"] == "payload_non_valido"
    assert cartella.read_bytes() == vecchio
    # lettura MONCA (2 leghe su 4 dello stato della action): niente atlante parziale
    monche = _righe_leghe(stati)[:2]
    assert atlas["meta"]["n_leagues_in_state"] == 4
    r = SY.sincronizza(url="http://x", key="k", path=str(cartella),
                       get=_db_finto([_versione_leggera(atlas)], monche))
    assert r["esito"] == "payload_non_valido"
    assert cartella.read_bytes() == vecchio


def test_scarica_uguale_a_domanda(cartella, tmp_path, stati, seme):
    atlas = _atlante_action(stati, seme)
    SY.sincronizza(url="http://x", key="k", path=str(cartella),
                   get=_db_finto([_versione_leggera(atlas)], _righe_leghe(stati)))
    sc = json.loads(cartella.read_bytes())
    do = json.loads(_file_domanda(tmp_path, stati))
    assert set(sc) == set(do)
    for k in sc:
        if k != "meta":
            assert sc[k] == do[k], k
    solo_modo = {"modo", "generator", "leghe_in_preparazione", "leghe_senza_dati", "run",
                 "watermark_event_id"}
    assert {k: v for k, v in sc["meta"].items() if k not in solo_modo} == \
        {k: v for k, v in do["meta"].items() if k not in solo_modo}


# ----------------------------------------------- 6) migrazione
def _sql_senza_commenti() -> str:
    p = os.path.join(ROOT, "migrations", "hazard_atlas_globale_leggero_2026-10-09.sql")
    with open(p, "rb") as fh:
        grezzo = fh.read()
    grezzo.decode("ascii")                                 # ASCII-only
    return "\n".join(r.split("--", 1)[0] for r in grezzo.decode("ascii").splitlines())


def test_migrazione_tiene_solo_meta_e_global_idempotente_senza_drop():
    sql = re.sub(r"\s+", " ", _sql_senza_commenti()).strip().lower()
    assert "update public.hazard_atlas set payload = jsonb_build_object('meta', payload -> 'meta')" in sql
    assert "jsonb_build_object('global', payload -> 'global')" in sql
    assert "where (payload - 'meta' - 'global') <> '{}'::jsonb" in sql
    for v in VIETATE:
        assert f"'{v}'" not in sql
    assert "drop " not in sql and "vacuum" not in sql and "delete" not in sql
    assert "hazard_atlas_leghe" not in sql
    assert sql.startswith("begin;") and sql.endswith("commit;")
