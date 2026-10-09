"""W1-G2 - il registro delle tabelle del cloud contro il codice VERO di oggi (consegna R23).

La scansione e' quella dell'inventario (``ARCHITETTURA_2026-10/strumenti/inventario/s03_db.py``:
``analizza_py``/``analizza_ts`` sui file tracciati da git, categorie di ``s01_righe``), importata
e non copiata; le liste delle 89 tabelle e delle 6 scritte da RPC vengono dallo strumento
``g_copertura_tabelle.py`` e dalla sua matrice. Le definizioni delle RPC sono lette dalle
migrazioni (corpo ``$$...$$``, chiuso sulle funzioni chiamate).

Il test che conta: ``test_il_registro_copre_il_codice_di_oggi``; i test ``test_falsifica_*``
provano che sa diventare rosso (togliere una riga del registro, un sito dinamico nuovo, una
RPC di lettura che scrive...).
"""
from __future__ import annotations

import ast
import csv
import importlib.util
import re
import sys
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Dict, FrozenSet, List, Set, Tuple

import pytest

from Betfair.nucleo.dati import registro as R
from Betfair.nucleo.dati.contratto import SpecTabella

RADICE = Path(__file__).resolve().parents[4]
INVENTARIO = RADICE / "ARCHITETTURA_2026-10" / "strumenti" / "inventario"
VERIFICA = RADICE / "ARCHITETTURA_2026-10" / "strumenti" / "verifica"
ID = re.compile(r"[a-z_][a-z0-9_]*")
RX_REST = re.compile(r'_req\(\s*"(POST|PATCH|DELETE|PUT)"\s*,\s*f?"([A-Za-z_][A-Za-z0-9_/]*)')
RX_FUNZ = re.compile(r"create\s+(?:or\s+replace\s+)?function\s+(?:public\.)?\"?([a-z_0-9]+)\"?", re.I)
RX_CORPO = re.compile(r"\bas\s+(\$[a-z_]*\$)", re.I)
RX_TAB = re.compile(r"create\s+(?:unlogged\s+)?table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?\"?([a-z_0-9]+)\"?", re.I)
RX_DML = re.compile(r"\b(?:insert\s+into|update|delete\s+from)\s+(?:only\s+)?(?:public\.)?\"?([a-z_][a-z0-9_]*)", re.I)
RX_CHIAMATA = re.compile(r"\b(?:public\.)?([a-z_][a-z0-9_]*)\s*\(", re.I)


def _carica(percorso: Path, nome: str) -> ModuleType:
    """Importa uno strumento dell'inventario dal suo file, senza lasciare il suo
    ``sys.path.insert`` nel processo di pytest."""
    prima = list(sys.path)
    try:
        spec = importlib.util.spec_from_file_location(nome, percorso)
        assert spec is not None and spec.loader is not None
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo
    finally:
        sys.path[:] = prima


@lru_cache(maxsize=1)
def _strumenti() -> Tuple[ModuleType, ModuleType]:
    return _carica(INVENTARIO / "s03_db.py", "g2_s03_db"), _carica(VERIFICA / "g_copertura_tabelle.py", "g2_cop")


# ---------------------------------------------------------------------------
# Scansione del codice di oggi (riuso di s03_db)
# ---------------------------------------------------------------------------
def _chiamate_codice() -> List[tuple]:
    s03, _ = _strumenti()
    c = sys.modules["_comune"]
    categoria = sys.modules["s01_righe"].categoria
    out: List[tuple] = []
    for rel in c.file_tracciati():
        ext = Path(rel).suffix.lower()
        if ext not in (".py", ".ts", ".tsx", ".js") or (ext == ".js" and not rel.startswith("desktop/")):
            continue
        testo = c.leggi_testo(rel)
        if testo is None:
            continue
        cat = categoria(rel)
        if s03.tipo_chiamante(rel, cat) not in ("prod", "frontend"):
            continue
        if ext == ".py":
            s03.analizza_py(rel, testo, cat, out)
            for i, riga in enumerate(testo.splitlines(), 1):
                for m in RX_REST.finditer(riga):
                    out.append((rel, i, "rest_scrive", m.group(2), m.group(1), cat, "py"))
        elif rel.startswith(("frontend/src/", "desktop/")):
            s03.analizza_ts(rel, testo, cat, out)
    return out


def _definizioni_sql() -> Tuple[Dict[str, List[str]], Set[str]]:
    corpi: Dict[str, List[str]] = {}
    tabelle: Set[str] = set()
    for p in sorted(list((RADICE / "migrations").glob("*.sql")) + list((RADICE / "sql").glob("*.sql"))):
        t = p.read_text(encoding="utf-8", errors="replace")
        tabelle |= {m.group(1).lower() for m in RX_TAB.finditer(t)}
        for m in RX_FUNZ.finditer(t):
            a = RX_CORPO.search(t, m.end())
            if not a:
                continue
            b = t.find(a.group(1), a.end())
            corpi.setdefault(m.group(1).lower(), []).append(t[a.end():b if b > 0 else len(t)])
    return corpi, tabelle


def _chiusura_dml(nome: str, corpi: Dict[str, List[str]], tabelle: Set[str], visti: Set[str]) -> Set[str]:
    """Tabelle toccate da INSERT/UPDATE/DELETE nel corpo della funzione e delle funzioni che chiama."""
    if nome in visti:
        return set()
    visti.add(nome)
    out: Set[str] = set()
    for corpo in corpi.get(nome, []):
        out |= {m.group(1).lower() for m in RX_DML.finditer(corpo)} & tabelle
        for m in RX_CHIAMATA.finditer(corpo):
            n = m.group(1).lower()
            if n in corpi and n != nome:
                out |= _chiusura_dml(n, corpi, tabelle, visti)
    return out


def _aggiungi(d: Dict, k, v) -> None:
    d.setdefault(k, set()).add(v)


@lru_cache(maxsize=1)
def scansione_di_oggi() -> R.Scansione:
    s03, _ = _strumenti()
    scritture: Dict[str, Set[str]] = {}
    dinamici: Dict[Tuple[str, str], Set[int]] = {}
    indeterminati: Dict[Tuple[str, str], Set[int]] = {}
    rpc: Dict[str, Set[str]] = {}
    rpc_din: Dict[Tuple[str, str], Set[int]] = {}
    rest: Dict[Tuple[str, str], Set[int]] = {}
    for rel, riga, tipo, nome, op, _cat, _ling in _chiamate_codice():
        if tipo == "table":
            ops = set(op.split(","))
            if ops & s03.SCRITTURA:
                if ID.fullmatch(nome):
                    _aggiungi(scritture, nome, f"{rel}:{riga}")
                else:
                    _aggiungi(dinamici, (rel, nome), riga)
            elif not ops & s03.OPS:
                _aggiungi(indeterminati, (rel, nome), riga)
        elif tipo in ("rpc", "rest_rpc"):
            if ID.fullmatch(nome):
                _aggiungi(rpc, nome, f"{rel}:{riga}")
            else:
                _aggiungi(rpc_din, (rel, nome), riga)
        elif tipo == "rest_scrive":
            if nome.startswith("rpc/"):
                _aggiungi(rpc, nome[4:], f"{rel}:{riga}")
            else:
                _aggiungi(rest, (rel, nome), riga)
    corpi, tabelle_sql = _definizioni_sql()
    universo = tabelle_sql | set(scritture) | set(R.REGISTRO.tabelle())
    nomi_rpc = set(rpc) | set(R.REGISTRO.rpc_scriventi())
    dml = {n: frozenset(_chiusura_dml(n, corpi, universo, set())) for n in nomi_rpc}
    congela = lambda d: {k: frozenset(v) for k, v in d.items()}  # noqa: E731
    return R.Scansione(scritture=congela(scritture), dinamici=congela(dinamici),
                       indeterminati=congela(indeterminati), rpc=congela(rpc), rpc_dinamiche=congela(rpc_din),
                       rest=congela(rest), dml_rpc=dml, rpc_definite=frozenset(corpi))


def _sola_lettura_strumento() -> FrozenSet[str]:
    return frozenset(_strumenti()[1].RPC_SOLA_LETTURA)


def _verifica(registro: R.RegistroTabelle, scansione: R.Scansione | None = None) -> R.EsitoCopertura:
    return R.verifica_copertura(registro, scansione or scansione_di_oggi(), _sola_lettura_strumento())


# ---------------------------------------------------------------------------
# 1. Le 89 dell'inventario e le 6 scritte da RPC sono tutte registrate
# ---------------------------------------------------------------------------
def test_le_89_dell_inventario_e_le_6_da_rpc_sono_registrate():
    _, cop = _strumenti()
    with open(cop.TSV_T, encoding="utf-8") as f:
        righe = list(csv.DictReader(f, delimiter="\t"))
    le_89 = {r["tabella"] for r in righe
             if ID.fullmatch(r["tabella"]) and int(r["n_prod"]) + int(r["n_frontend"]) > 0}
    assert len(le_89) == 89
    assert len(cop.TABELLE_DA_RPC) == 6
    registrate = set(R.REGISTRO.tabelle())
    assert le_89 - registrate == set(), "tabelle delle 89 assenti dal registro"
    assert set(cop.TABELLE_DA_RPC) - registrate == set()
    for t in cop.TABELLE_DA_RPC:
        assert R.REGISTRO.voce(t).origine == "solo_rpc", t
    extra = registrate - le_89 - set(cop.TABELLE_DA_RPC)
    # le voci in piu' sono quelle trovate dalla scansione del 09/10 (dichiarate nel referto)
    assert extra == {"book_odds_cache", "book_odds_cache_fonte", "hazard_atlas", "hazard_atlas_leghe",
                     "live_market_snapshots", "live_score_timeline", "match_lineups", "match_player_stats",
                     "monitor_metrics", "omega_ht_ft_transitions", "omega_minute_transitions",
                     "tennis_replay_punteggio", "tennis_replay_snapshots"}


def test_una_voce_per_tabella_e_spec_del_contratto():
    assert len(R.REGISTRO.tabelle()) == len(set(R.REGISTRO.tabelle())) == 108
    for t in R.REGISTRO.tabelle():
        s = R.REGISTRO.spec(t)
        assert isinstance(s, SpecTabella) and s.nome == t
        assert s.natura in ("SV", "CMD", "ARC", "STA", "CFG")
        assert s.regime in ("stato_denaro", "stato_vivo", "log", "cache", "cloud")
    with pytest.raises(KeyError, match="non registrata"):
        R.REGISTRO.spec("tabella_che_non_esiste")
    assert R.STATO_RITARDI == "proposta, da approvare con U-86"


def test_coerenza_interna_del_registro():
    assert R.controlla_coerenza(R.REGISTRO) == ()


# ---------------------------------------------------------------------------
# 2. Il registro copre il codice di oggi (il test di R23)
# ---------------------------------------------------------------------------
def test_il_registro_copre_il_codice_di_oggi():
    esito = _verifica(R.REGISTRO)
    for a in esito.avvisi:
        print("AVVISO:", a)
    assert esito.errori == (), "\n".join(esito.errori)
    # le voci senza scrittori nel codice sono SOLO quelle dichiarate (segnalate, non errore)
    senza = sorted(a.split(":")[0] for a in esito.avvisi if "nessuno la scrive dal codice" in a)
    assert senza == ["bet_features", "omega_ht_ft_transitions", "omega_minute_transitions"]


def test_scrittori_di_oggi_hanno_file_e_riga_veri():
    """Ogni ``file:riga`` del registro esiste e a quella riga (o nel sito) c'e' la tabella o il nome."""
    for v in R.REGISTRO.voci():
        for s in v.spec.scrittori_oggi:
            if s.startswith("rpc:"):
                assert s[4:] in R.REGISTRO.rpc_scriventi(), s
                continue
            f, riga = s.rsplit(":", 1)
            righe = (RADICE / f).read_text(encoding="utf-8").splitlines()
            assert 1 <= int(riga) <= len(righe), s
            testo = righe[int(riga) - 1]
            assert ("table(" in testo or "_req(" in testo or "from(" in testo), (s, testo)


def test_rpc_registrate_coincidono_con_le_definizioni_sql():
    sc = scansione_di_oggi()
    for nome, r in R.REGISTRO.rpc_scriventi().items():
        assert nome in sc.rpc_definite, f"{nome}: definizione non trovata in migrations/"
        assert set(r.tabelle) == set(sc.dml_rpc[nome]), (nome, r.tabelle, sorted(sc.dml_rpc[nome]))
        f, riga = r.definizione.rsplit(":", 1)
        assert re.search(rf"function\s+(public\.)?{nome}\s*\(",
                         (RADICE / f).read_text(encoding="utf-8").splitlines()[int(riga) - 1], re.I), r


def test_siti_dinamici_coincidono_con_il_codice():
    """Le risoluzioni a mano dei nomi dinamici, provate sulle costanti vere del codice."""
    from Betfair.stream import db as sdb
    from Betfair.stream.tennis_replay import caricamento as car

    pnl = next(s for s in R.SITI_DINAMICI if s.nome == "<dinamico:tabella>")
    assert set(pnl.tabelle) == set(sdb.TABELLE_PNL_BETFAIR)
    blocchi = next(s for s in R.SITI_DINAMICI if s.file == "Betfair/stream/db.py" and s.nome == "<dinamico:table>")
    assert {car.T_SNAPSHOT, car.T_PUNTEGGIO, "live_market_snapshots", "live_score_timeline"} == set(blocchi.tabelle)
    testo_pf = (RADICE / "per_fixture_backfill.py").read_text(encoding="utf-8")
    per_fixture = next(s for s in R.SITI_DINAMICI if s.file == "per_fixture_backfill.py" and s.nome == "<dinamico:table>")
    assert set(per_fixture.tabelle) == set(re.findall(r'^\s*"\w+": \("(match_\w+)"', testo_pf, re.M))
    testo_sa = (RADICE / "season_aggregates.py").read_text(encoding="utf-8")
    aggregati = next(s for s in R.SITI_DINAMICI if s.file == "season_aggregates.py")
    assert set(aggregati.tabelle) == set(re.findall(r'nome == "(\w+)"', testo_sa)) | {"top_cards"}


# ---------------------------------------------------------------------------
# 3. Chiavi naturali e dipendenze contro il codice e le migrazioni
# ---------------------------------------------------------------------------
def _on_conflict_del_codice() -> Dict[str, Set[Tuple[str, ...]]]:
    """tabella -> on_conflict letterali degli upsert del codice di produzione (AST)."""
    s03, _ = _strumenti()
    c = sys.modules["_comune"]
    out: Dict[str, Set[Tuple[str, ...]]] = {}
    for rel in c.file_tracciati():
        if not rel.endswith(".py") or s03.tipo_chiamante(rel, sys.modules["s01_righe"].categoria(rel)) != "prod":
            continue
        testo = c.leggi_testo(rel) or ""
        if "on_conflict" not in testo:
            continue
        try:
            albero = ast.parse(testo)
        except SyntaxError:
            continue
        cost = s03.costanti_modulo(albero)
        for n in ast.walk(albero):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "upsert"):
                continue
            kw = {k.arg: k.value for k in n.keywords}
            oc = kw.get("on_conflict")
            if not (isinstance(oc, ast.Constant) and isinstance(oc.value, str)):
                continue
            ric = n.func.value
            while isinstance(ric, ast.Call) and isinstance(ric.func, ast.Attribute) and ric.func.attr != "table":
                ric = ric.func.value
            if not (isinstance(ric, ast.Call) and isinstance(ric.func, ast.Attribute) and ric.func.attr == "table"):
                continue
            a = ric.args[0] if ric.args else None
            nome = (a.value if isinstance(a, ast.Constant) else cost.get(getattr(a, "id", getattr(a, "attr", ""))))
            if isinstance(nome, str) and ID.fullmatch(nome):
                out.setdefault(nome, set()).add(tuple(x.strip() for x in oc.value.split(",")))
    return out


def test_chiavi_naturali_uguali_agli_on_conflict_del_codice():
    trovati = _on_conflict_del_codice()
    assert len(trovati) >= 25
    for tabella, chiavi in sorted(trovati.items()):
        for k in chiavi:
            assert R.REGISTRO.spec(tabella).chiave_naturale == k, (tabella, k)


def _chiavi_esterne() -> Set[Tuple[str, str]]:
    """(figlia, padre) dalle REFERENCES delle migrazioni (create table e alter table)."""
    out: Set[Tuple[str, str]] = set()
    rx_ref = re.compile(r"references\s+(?:public\.)?([a-z_0-9]+)\s*\(", re.I)
    for p in sorted((RADICE / "migrations").glob("*.sql")):
        testo = p.read_text(encoding="utf-8", errors="replace")
        figlia = None
        for riga in testo.splitlines():
            m = RX_TAB.search(riga) or re.search(r"alter\s+table\s+(?:if\s+exists\s+)?(?:public\.)?([a-z_0-9]+)", riga, re.I)
            if m:
                figlia = m.group(1).lower()
            if riga.strip().startswith("--"):
                continue
            for r in rx_ref.finditer(riga):
                if figlia:
                    out.add((figlia, r.group(1).lower()))
    return out


def test_dipende_da_contiene_le_chiavi_esterne_delle_migrazioni():
    fk = {(f, p) for f, p in _chiavi_esterne() if f in R.REGISTRO.tabelle()}
    assert len(fk) >= 20
    for figlia, padre in sorted(fk):
        assert padre in R.REGISTRO.spec(figlia).dipende_da, (figlia, padre)


# ---------------------------------------------------------------------------
# 4. Falsificazioni: il test sa diventare rosso
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tabella", ["mike_activity", "live_ladder", "betfair_live_orders", "monitor_metrics",
                                     "match_lineups", "hazard_atlas_leghe", "leads", "tennis_replay_snapshots"])
def test_falsifica_togliere_una_riga_del_registro(tabella):
    esito = _verifica(R.REGISTRO.senza(tabella))
    assert any(e.startswith("TABELLA SCRITTA DAL CODICE E ASSENTE DAL REGISTRO: " + tabella + " ")
               for e in esito.errori), esito.errori


def test_falsifica_togliere_una_tabella_scritta_solo_da_rpc():
    esito = _verifica(R.REGISTRO.senza("book_odds_cache"))
    assert any("refresh_analytics_bets_range" in e and "book_odds_cache" in e for e in esito.errori)


def test_falsifica_togliere_una_rpc_scrivente():
    esito = _verifica(R.REGISTRO.senza(rpc=("mike_activate",)))
    assert any(e.startswith("RPC SCRIVENTE ASSENTE DAL REGISTRO: mike_activate") for e in esito.errori)


def test_falsifica_rpc_di_lettura_che_scrive():
    sc = scansione_di_oggi()
    finta = replace(sc, dml_rpc={**sc.dml_rpc, "get_mike_state": frozenset({"mike_control"})})
    esito = _verifica(R.REGISTRO, finta)
    assert any(e.startswith("RPC DI LETTURA CHE SCRIVE: get_mike_state") for e in esito.errori)


def test_falsifica_rpc_che_scrive_una_tabella_non_dichiarata():
    sc = scansione_di_oggi()
    finta = replace(sc, dml_rpc={**sc.dml_rpc, "mike_stop": frozenset({"mike_control", "mike_trades"})})
    esito = _verifica(R.REGISTRO, finta)
    assert any("mike_stop" in e and "mike_trades" in e for e in esito.errori)


def test_falsifica_file_scrittore_nuovo_e_sito_dinamico_nuovo():
    sc = scansione_di_oggi()
    scritture = dict(sc.scritture)
    scritture["mike_trades"] = scritture["mike_trades"] | {"Betfair/nuovo_file.py:10"}
    dinamici = dict(sc.dinamici)
    dinamici[("Betfair/nuovo_file.py", "<dinamico:x>")] = frozenset({5})
    rest = dict(sc.rest)
    rest[("Betfair/nuovo_file.py", "tabella_rest")] = frozenset({7})
    esito = _verifica(R.REGISTRO, replace(sc, scritture=scritture, dinamici=dinamici, rest=rest))
    assert any(e.startswith("SCRITTORE NON REGISTRATO per mike_trades") for e in esito.errori)
    assert any(e.startswith("NOME DINAMICO NON RISOLTO") and "nuovo_file" in e for e in esito.errori)
    assert any(e.startswith("SCRITTURA REST NON REGISTRATA") for e in esito.errori)


def test_voce_che_nessuno_scrive_piu_segnalata_non_errore_se_dichiarata():
    spec = SpecTabella("tabella_dismessa", ("id",), "STA", "cloud", R.NON_APPLICABILE, False, None, (),
                       (), "nessuno")
    dichiarata = R.VoceRegistro(spec, "EXTRA", "CLOUD", "nuova", (), "dismessa il 09/10 (prova)", "-")
    esito = _verifica(R.RegistroTabelle(list(R.REGISTRO.voci()) + [dichiarata],
                                        R.REGISTRO.rpc_scriventi().values()))
    assert esito.errori == ()
    assert any(a.startswith("tabella_dismessa: nessuno la scrive dal codice") for a in esito.avvisi)
    non_dichiarata = replace(dichiarata, scrittura_fuori_codice=None)
    esito = _verifica(R.RegistroTabelle(list(R.REGISTRO.voci()) + [non_dichiarata],
                                        R.REGISTRO.rpc_scriventi().values()))
    assert any(e.startswith("VOCE SENZA SCRITTORI NON DICHIARATA: tabella_dismessa") for e in esito.errori)


def test_falsifica_scrittore_sparito_e_avviso():
    sc = scansione_di_oggi()
    scritture = dict(sc.scritture)
    scritture["mike_activity"] = frozenset()
    esito = _verifica(R.REGISTRO, replace(sc, scritture=scritture))
    assert any(a.startswith("mike_activity: scrittore registrato che non scrive piu'") for a in esito.avvisi)
    # e senza alcuno scrittore e senza dichiarazione la voce diventa un errore
    assert any(e.startswith("VOCE SENZA SCRITTORI NON DICHIARATA: mike_activity") for e in esito.errori)
