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
RX_DML = re.compile(r"\b(?:insert\s+into|update|delete\s+from|truncate(?:\s+table)?)\s+(?:only\s+)?(?:public\.)?"
                    r"\"?([a-z_][a-z0-9_]*)", re.I)
RX_CRON = re.compile(r"cron\.schedule\s*\((.*?)\)\s*;", re.I | re.S)
RX_YML_RPC = re.compile(r"/rest/v1/rpc/([a-z_][a-z0-9_]*)")
RX_YML_TAB = re.compile(r"/rest/v1/([a-z_][a-z0-9_]*)")
RX_YML_DIN = re.compile(r"/rest/v1/[\"']\s*\+|/rest/v1/\$\{?[A-Za-z_]")
RX_YML_SCRIVE = re.compile(r"-X\s+(POST|PATCH|DELETE|PUT)\b|method\s*=\s*[\"'](POST|PATCH|DELETE|PUT)", re.I)
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
    out.extend(_chiamate_workflow(c))
    return out


def _chiamate_workflow(c: ModuleType) -> List[tuple]:
    """I workflow ``.github/**/*.yml``: RPC e tabelle via REST (curl, urllib); una tabella e'
    scritta se entro 3 righe c'e' ``-X POST|PATCH|DELETE|PUT`` o ``method="POST"...``."""
    out: List[tuple] = []
    for rel in c.file_tracciati():
        if not (rel.startswith(".github/") and rel.endswith((".yml", ".yaml"))):
            continue
        righe = (c.leggi_testo(rel) or "").splitlines()
        for i, riga in enumerate(righe, 1):
            for m in RX_YML_RPC.finditer(riga):
                out.append((rel, i, "rpc", m.group(1), "", "workflow", "yml"))
            if RX_YML_DIN.search(riga):
                out.append((rel, i, "table", "<dinamico:rest>", "?", "workflow", "yml"))
            intorno = "\n".join(righe[max(0, i - 4):i + 3])
            for m in RX_YML_TAB.finditer(riga):
                if m.group(1) != "rpc" and RX_YML_SCRIVE.search(intorno):
                    out.append((rel, i, "rest_scrive", m.group(1), "POST", "workflow", "yml"))
    return out


def _definizioni_sql() -> Tuple[Dict[str, List[str]], Set[str], Dict[str, Set[str]]]:
    """(corpi delle funzioni per nome, tabelle create, DML di OGNI funzione e di ogni cron.schedule)."""
    corpi: Dict[str, List[str]] = {}
    tabelle: Set[str] = set()
    dml: Dict[str, Set[str]] = {}
    for p in sorted(list((RADICE / "migrations").glob("*.sql")) + list((RADICE / "sql").glob("*.sql"))):
        t = p.read_text(encoding="utf-8", errors="replace")
        rel = p.relative_to(RADICE).as_posix()
        tabelle |= {m.group(1).lower() for m in RX_TAB.finditer(t)}
        for m in RX_FUNZ.finditer(t):
            a = RX_CORPO.search(t, m.end())
            if not a:
                continue
            b = t.find(a.group(1), a.end())
            corpo = t[a.end():b if b > 0 else len(t)]
            corpi.setdefault(m.group(1).lower(), []).append(corpo)
            for d in RX_DML.finditer(corpo):
                _aggiungi(dml, d.group(1).lower(), f"{rel}:{m.group(1).lower()}")
        for c in RX_CRON.finditer(t):
            for d in RX_DML.finditer(c.group(1)):
                _aggiungi(dml, d.group(1).lower(), f"{rel}:cron")
    return corpi, tabelle, dml


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
    storage: Dict[Tuple[str, str], Set[int]] = {}
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
        elif tipo == "storage":
            _aggiungi(storage, (rel, nome), riga)
        elif tipo == "rest_dinamico":
            _aggiungi(indeterminati, (rel, "<dinamico:rest>"), riga)
        elif tipo == "rest_scrive":
            if nome.startswith("rpc/"):
                _aggiungi(rpc, nome[4:], f"{rel}:{riga}")
            else:
                _aggiungi(rest, (rel, nome), riga)
    corpi, tabelle_sql, dml_migrazioni = _definizioni_sql()
    universo = tabelle_sql | set(scritture) | set(R.REGISTRO.tabelle())
    nomi_rpc = set(rpc) | set(R.REGISTRO.rpc_scriventi())
    dml = {n: frozenset(_chiusura_dml(n, corpi, universo, set())) for n in nomi_rpc}
    congela = lambda d: {k: frozenset(v) for k, v in d.items()}  # noqa: E731
    return R.Scansione(scritture=congela(scritture), dinamici=congela(dinamici),
                       indeterminati=congela(indeterminati), rpc=congela(rpc), rpc_dinamiche=congela(rpc_din),
                       rest=congela(rest), dml_rpc=dml, rpc_definite=frozenset(corpi),
                       dml_migrazioni=congela(dml_migrazioni), storage=congela(storage))


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
                     "tennis_replay_punteggio", "tennis_replay_snapshots",
                     # revisione del 09/10 (D-1): RPC dei workflow e funzioni SQL / pg_cron
                     "analytics_riepilogo_segnali", "analytics_riepilogo_decisioni", "analytics_riepilogo_meta",
                     "analytics_prob_staging", "omega_ht_ft_transitions_raw", "omega_minute_transitions_raw",
                     "omega_transitions_league_counts", "omega_transitions_ledger", "omega_transitions_runs",
                     "omega_transitions_state", "omega_minute_league_counts", "omega_build_jobs", "lanci_action"}


def test_una_voce_per_tabella_e_spec_del_contratto():
    assert len(R.REGISTRO.tabelle()) == len(set(R.REGISTRO.tabelle())) == 121
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
    # (le tabelle del pg_cron contano come scritte: il DML delle loro funzioni e' nelle migrazioni)
    assert senza == ["bet_features"]


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


# ---------------------------------------------------------------------------
# 5. Revisione del 09/10 (D-1, D-10): workflow, funzioni SQL e pg_cron, Storage, golden
# ---------------------------------------------------------------------------
def test_workflow_e_rpc_notturna_dei_riepiloghi_nella_scansione():
    sc = scansione_di_oggi()
    assert any(c.startswith(".github/workflows/predictions_results_backfill.yml:")
               for c in sc.rpc["refresh_analytics_riepilogo"])
    assert sc.dml_rpc["refresh_analytics_riepilogo"] == {"analytics_riepilogo_segnali", "analytics_riepilogo_decisioni",
                                                         "analytics_riepilogo_meta"}
    for t in ("analytics_riepilogo_segnali", "analytics_riepilogo_decisioni", "analytics_riepilogo_meta"):
        assert "rpc:refresh_analytics_riepilogo" in R.REGISTRO.spec(t).scrittori_oggi


def test_falsifica_rpc_dei_workflow_dichiarata_di_sola_lettura(monkeypatch):
    """La mutazione del revisore: refresh_analytics_riepilogo dichiarata di sola lettura -> rosso."""
    monkeypatch.setattr(R, "RPC_SOLA_LETTURA_DICHIARATE",
                        {**R.RPC_SOLA_LETTURA_DICHIARATE, "refresh_analytics_riepilogo": "mutazione"})
    esito = _verifica(R.REGISTRO.senza(rpc=("refresh_analytics_riepilogo",)))
    assert any(e.startswith("RPC DI LETTURA CHE SCRIVE: refresh_analytics_riepilogo") for e in esito.errori)


@pytest.mark.parametrize("tabella", ["omega_transitions_ledger", "omega_ht_ft_transitions_raw", "lanci_action",
                                     "omega_build_jobs", "analytics_prob_staging"])
def test_falsifica_tabella_scritta_da_funzioni_sql_tolta(tabella):
    esito = _verifica(R.REGISTRO.senza(tabella))
    assert any(e.startswith("TABELLA SCRITTA DA FUNZIONI SQL/PG_CRON E ASSENTE DAL REGISTRO: " + tabella)
               for e in esito.errori), esito.errori


def test_eccezioni_dml_tutte_usate_e_nessuna_registrata():
    sc = scansione_di_oggi()
    assert set(R.ECCEZIONI_DML) <= set(sc.dml_migrazioni), set(R.ECCEZIONI_DML) - set(sc.dml_migrazioni)
    assert not set(R.ECCEZIONI_DML) & set(R.REGISTRO.tabelle())
    finta = replace(sc, dml_migrazioni={**sc.dml_migrazioni, "tabella_del_cron": frozenset({"x.sql:cron"})})
    assert any("tabella_del_cron" in e for e in _verifica(R.REGISTRO, finta).errori)


def test_storage_dichiarato_e_falsificato():
    sc = scansione_di_oggi()
    assert {(s.file, s.nome) for s in R.SITI_STORAGE} == set(sc.storage)
    finta = replace(sc, storage={**sc.storage, ("Betfair/nuovo.py", "<dinamico:b>"): frozenset({3})})
    assert any(e.startswith("STORAGE NON DICHIARATO: Betfair/nuovo.py") for e in _verifica(R.REGISTRO, finta).errori)


def _blocchi_create_table() -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for p in sorted((RADICE / "migrations").glob("*.sql")):
        t = p.read_text(encoding="utf-8", errors="replace")
        for m in RX_TAB.finditer(t):
            i, prof = t.find("(", m.end() - 1), 0
            j = i
            while j < len(t):
                prof += {"(": 1, ")": -1}.get(t[j], 0)
                j += 1
                if prof == 0:
                    break
            out.setdefault(m.group(1).lower(), []).append(t[i:j])
    return out


def _ha_updated_at(tabella: str, blocchi: Dict[str, List[str]]) -> bool:
    if any(re.search(r"^\s*updated_at\s", b, re.I | re.M) for b in blocchi.get(tabella, [])):
        return True
    rx = re.compile(rf"alter\s+table\s+(?:if\s+exists\s+)?(?:public\.)?{tabella}\s+add\s+column\s+"
                    rf"(?:if\s+not\s+exists\s+)?updated_at\b", re.I)
    return any(rx.search(p.read_text(encoding="utf-8", errors="replace"))
               for p in (RADICE / "migrations").glob("*.sql"))


def _chiavi_candidate(tabella: str, blocchi: Dict[str, List[str]]) -> Set[FrozenSet[str]]:
    out: Set[FrozenSet[str]] = set()
    for b in blocchi.get(tabella, []):
        for riga in b.splitlines():
            r = riga.split("--")[0]
            m = re.match(r"\s*\(?\s*([a-z_][a-z0-9_]*)\s+[a-z]", r, re.I)
            if m and re.search(r"\b(primary\s+key|unique)\b(?!\s*\()", r, re.I):
                out.add(frozenset({m.group(1).lower()}))
            for g in re.finditer(r"\b(?:primary\s+key|unique)\s*\(([^)]*)\)", r, re.I):
                out.add(frozenset(x.strip().lower() for x in g.group(1).split(",")))
    rx = re.compile(rf"create\s+unique\s+index[^;]*?\bon\s+(?:public\.)?{tabella}\s*(?:using\s+\w+\s*)?"
                    rf"\(([a-z0-9_,\s]+)\)", re.I | re.S)
    for p in (RADICE / "migrations").glob("*.sql"):
        for g in rx.finditer(p.read_text(encoding="utf-8", errors="replace")):
            out.add(frozenset(x.strip().lower() for x in g.group(1).split(",")))
    return out


def test_schema_nel_repo_dichiarato_come_nelle_migrazioni():
    _, tabelle_sql, _ = _definizioni_sql()
    viste = {"bet_features"}
    senza = {t for t in R.REGISTRO.tabelle() if t not in tabelle_sql and t not in viste}
    assert senza == set(R.SENZA_SCHEMA_NEL_REPO)
    for t in R.REGISTRO.tabelle():
        assert R.REGISTRO.voce(t).schema_nel_repo == (t not in senza), t


def test_golden_rev_colonna_dove_la_colonna_esiste():
    blocchi = _blocchi_create_table()
    for v in R.REGISTRO.voci():
        if not v.schema_nel_repo or v.spec.nome == "bet_features":
            assert v.spec.rev_colonna is None, v.spec.nome
            continue
        atteso = "updated_at" if _ha_updated_at(v.spec.nome, blocchi) else None
        assert v.spec.rev_colonna == atteso, (v.spec.nome, v.spec.rev_colonna, atteso)


#: G par. 4.3 (proposta U-86), trascritta a mano famiglia per famiglia: (regime, ritardo s, coalesce, chiave)
GOLDEN_G43: Dict[str, Tuple[str, float, bool, Tuple[str, ...]]] = {
    "betfair_live_order_requests": ("stato_denaro", 5.0, False, ("client_ref",)),
    "betfair_live_orders": ("stato_denaro", 5.0, False, ("mode", "client_order_ref")),
    "betfair_live_positions": ("stato_denaro", 5.0, False, ("mode", "market_id", "selection_id", "handicap")),
    "betfair_live_settled": ("stato_denaro", 5.0, False, ("mode", "market_id")),
    "betfair_live_risk_state": ("stato_denaro", 5.0, False, ("id",)),
    "betfair_live_xhedge": ("stato_denaro", 5.0, False, ("event_id", "mode")),
    "betfair_live_account": ("stato_vivo", 15.0, True, ("id",)),
    "betfair_live_heartbeat": ("stato_vivo", 15.0, True, ("id",)),
    "betfair_live_risk_rules": ("stato_denaro", 5.0, False, ("client_ref",)),
    "betfair_live_settings": ("cache", 1.0, True, ("id",)),
    "betfair_live_journal": ("log", 60.0, False, ()),
    "betfair_live_audit": ("log", 60.0, False, ()),
    "live_alerts": ("log", 60.0, False, ()),
    "live_run_log": ("log", 60.0, False, ("event_id",)),
    "signal_history": ("log", 60.0, False, ("signal_id",)),
    "theta_confirm_requests": ("log", 60.0, False, ()),
    "live_follow": ("stato_vivo", 5.0, False, ("event_id",)),
    "live_now": ("stato_vivo", 2.0, True, ("event_id",)),
    "live_markets": ("stato_vivo", 2.0, True, ("event_id", "market_id")),
    "live_ladder": ("stato_vivo", 2.0, True, ("event_id", "market_id")),
    "live_signals": ("stato_vivo", 2.0, True, ("event_id",)),
    "mike_control": ("cache", 1.0, True, ("id",)),
    "mike_requests": ("cache", 1.0, False, ("id",)),
    "mike_trades": ("stato_denaro", 5.0, False, ("id",)),
    "mike_events": ("stato_vivo", 5.0, False, ("event_id",)),
    "mike_activity": ("log", 60.0, False, ()),
    "omega_control": ("cache", 1.0, True, ("id",)),
    "omega_manual_requests": ("cache", 1.0, False, ("id",)),
    "omega_missions": ("cache", 1.0, False, ("event_id",)),
    "omega_trades": ("stato_denaro", 5.0, False, ("id",)),
    "omega_events": ("stato_vivo", 5.0, False, ("event_id",)),
    "omega_market_snapshot": ("stato_vivo", 5.0, False, ("market_id",)),
    "omega_daily_goal": ("stato_vivo", 5.0, False, ("day",)),
    "omega_activity": ("log", 60.0, False, ()),
    "safe_strategy_control": ("cache", 1.0, True, ("id",)),
    "safe_strategy_requests": ("cache", 1.0, False, ("id",)),
    "safe_strategy_status": ("cache", 1.0, True, ("id",)),
    "safe_strategy_trades": ("stato_denaro", 5.0, False, ("id",)),
    "safe_strategy_opportunities": ("stato_vivo", 5.0, False, ("event_id",)),
    "safe_strategy_scan": ("stato_vivo", 5.0, True, ("event_id",)),
    "safe_strategy_activity": ("log", 60.0, False, ()),
    "scalper_control": ("cache", 3.0, True, ("event_id",)),
    "scalper_service_control": ("cache", 3.0, True, ("id",)),
    "scalper_activity": ("log", 60.0, False, ()),
    "tennis_live_follow": ("stato_vivo", 5.0, False, ("event_id",)),
    "tennis_live_now": ("stato_vivo", 5.0, True, ("event_id",)),
    "tennis_live_ladder": ("stato_vivo", 5.0, True, ("market_id",)),
    "tennis_live_orders": ("stato_denaro", 5.0, False, ("mode", "client_order_ref")),
    "tennis_live_positions": ("stato_denaro", 5.0, False, ("mode", "market_id", "selection_id", "handicap")),
    "tennis_live_order_queue": ("stato_denaro", 5.0, False, ("client_ref",)),
    "tennis_bot_control": ("cache", 1.0, True, ("event_id", "bot_key")),
    "tennis_bot_service_control": ("cache", 1.0, True, ("bot_key",)),
    "tennis_bot_activity": ("log", 60.0, False, ()),
}


def test_golden_regime_ritardo_chiave_di_g_43():
    for t, atteso in GOLDEN_G43.items():
        s = R.REGISTRO.spec(t)
        assert (s.regime, s.ritardo_max_s, s.coalesce, s.chiave_naturale) == atteso, t
    restanti = [v.spec for v in R.REGISTRO.voci() if v.spec.nome not in GOLDEN_G43]
    assert len(restanti) == 68
    for s in restanti:                         # tutte le altre restano nel cloud (G par. 4.3 T14-T17, extra)
        assert (s.regime, s.ritardo_max_s, s.coalesce) == ("cloud", R.NON_APPLICABILE, False), s.nome


def test_golden_chiave_naturale_e_una_chiave_vera_delle_migrazioni():
    blocchi = _blocchi_create_table()
    for v in R.REGISTRO.voci():
        t, k = v.spec.nome, v.spec.chiave_naturale
        if not v.schema_nel_repo or t == "bet_features":
            continue
        candidate = _chiavi_candidate(t, blocchi)
        if k:
            assert frozenset(k) in candidate, (t, k, candidate)
        else:
            # senza chiave: solo tabelle con il solo id seriale (log, archivi) o senza alcuna chiave
            assert candidate <= {frozenset({"id"})}, (t, candidate)
