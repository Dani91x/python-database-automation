"""Cancellazione fallita: si RITENTA, mai buchi ne' doppioni (25/09/2026).

Ordine dell'utente (testuale): "cancellazione fallita, si riprova, non voglio
buchi nel database o dati doppi".

Prima: delete_existing_standings/injuries/top_scorers/top_assists/top_cards
(standings_backfill.py, injuries_backfill.py, top_scorers_backfill.py,
top_assists_backfill.py, top_cards_backfill.py) inghiottivano l'eccezione
della delete (solo logger.error) e l'orchestratore backfill_*_for_league_season
chiamava insert_rows_* SUBITO DOPO comunque -> se la delete falliva per un
motivo transitorio (es. timeout 57014), l'insert scriveva righe doppie sopra
quelle vecchie mai cancellate.
season_aggregates.esegui_aggregato gia' fermava l'aggregato ('errore', nessun
insert) su delete fallita, ma senza ritentare.

Ora: db_delete_retry.delete_con_ritentativi(azione, ...) ritenta la delete
fino a 3 volte (attese crescenti 2/5/10 s, iniettabili) e, se fallisce anche
l'ultimo tentativo, rilancia l'eccezione. Le delete_existing_* la propagano
(niente piu' try/except silenzioso): l'orchestratore non arriva MAI
all'insert. esegui_aggregato usa lo stesso helper prima di restituire 'errore'.

Sandbox, niente rete/DB vero, niente time.sleep reale (si inietta
db_delete_retry.time.sleep - vedi commento nel modulo sul perche' non si puo'
iniettare via default di parametro).
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

import pytest

os.environ["SUPABASE_URL"] = "http://127.0.0.1:9"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "x"
os.environ["SUPABASE_KEY"] = "x"
os.environ["API_FOOTBALL_KEY"] = "x"

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import db_delete_retry  # noqa: E402
import standings_backfill as stb  # noqa: E402
import injuries_backfill as inb  # noqa: E402
import top_scorers_backfill as tsb  # noqa: E402
import top_assists_backfill as tab  # noqa: E402
import top_cards_backfill as tcb  # noqa: E402
import season_aggregates as sa  # noqa: E402


@pytest.fixture(autouse=True)
def niente_sleep_reale(monkeypatch):
    # db_delete_retry.time e' lo STESSO modulo stdlib `time` di sempre
    # (sys.modules e' un singleton): patchare qui vale ovunque sia importato.
    monkeypatch.setattr(db_delete_retry.time, "sleep", lambda s: None)
    monkeypatch.setattr(tcb.time, "sleep", lambda s: None)  # pausa yellow/red cards


# ---------------------------------------------------------------------------
# finto Supabase: table(nome).delete().eq(...).eq(...).execute() / .insert(righe).execute()
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class _DeleteQuery:
    def __init__(self, sb: "FakeSupabase", tabella: str) -> None:
        self.sb = sb
        self.tabella = tabella

    def eq(self, colonna: str, valore: Any) -> "_DeleteQuery":
        return self

    def execute(self) -> _Resp:
        self.sb.tentativi_delete[self.tabella] += 1
        rimasti = self.sb.fallimenti_delete.get(self.tabella, 0)
        if rimasti > 0:
            self.sb.fallimenti_delete[self.tabella] -= 1
            raise RuntimeError(
                "{'message': 'canceling statement due to statement timeout', 'code': '57014'}"
            )
        return _Resp([])


class _InsertQuery:
    def __init__(self, sb: "FakeSupabase", tabella: str, righe: List[Dict[str, Any]]) -> None:
        self.sb = sb
        self.tabella = tabella
        self.righe = righe

    def execute(self) -> _Resp:
        self.sb.inserite[self.tabella].extend(self.righe)
        return _Resp(self.righe)


class _Tabella:
    def __init__(self, sb: "FakeSupabase", nome: str) -> None:
        self.sb = sb
        self.nome = nome

    def delete(self) -> _DeleteQuery:
        return _DeleteQuery(self.sb, self.nome)

    def insert(self, righe: List[Dict[str, Any]]) -> _InsertQuery:
        return _InsertQuery(self.sb, self.nome, righe)


class FakeSupabase:
    """Chiavi e tipi identici al vero client supabase-py usato dai 5 script."""

    def __init__(self, fallimenti_delete: Optional[Dict[str, int]] = None) -> None:
        self.fallimenti_delete: Dict[str, int] = dict(fallimenti_delete or {})
        self.tentativi_delete: Dict[str, int] = {}
        self.inserite: Dict[str, List[Dict[str, Any]]] = {}

    def table(self, nome: str) -> _Tabella:
        self.tentativi_delete.setdefault(nome, 0)
        self.inserite.setdefault(nome, [])
        return _Tabella(self, nome)


# ---------------------------------------------------------------------------
# db_delete_retry.delete_con_ritentativi - unit
# ---------------------------------------------------------------------------
def test_ritentativi_fallisce_2_volte_poi_riesce(monkeypatch):
    attese: List[float] = []
    monkeypatch.setattr(db_delete_retry.time, "sleep", lambda s: attese.append(s))
    chiamate = {"n": 0}

    def azione() -> None:
        chiamate["n"] += 1
        if chiamate["n"] < 3:
            raise RuntimeError("timeout transitorio")

    db_delete_retry.delete_con_ritentativi(azione, etichetta="t")

    assert chiamate["n"] == 3
    assert attese == [2, 5]  # crescente, nessuna attesa dopo il successo


def test_ritentativi_fallisce_sempre_rilancia_dopo_3_tentativi(monkeypatch):
    attese: List[float] = []
    monkeypatch.setattr(db_delete_retry.time, "sleep", lambda s: attese.append(s))
    chiamate = {"n": 0}

    def azione() -> None:
        chiamate["n"] += 1
        raise RuntimeError("sempre giu'")

    with pytest.raises(RuntimeError, match="sempre giu'"):
        db_delete_retry.delete_con_ritentativi(azione, etichetta="t")

    assert chiamate["n"] == 3
    assert attese == [2, 5]


def test_ritentativi_al_primo_colpo_non_dorme(monkeypatch):
    attese: List[float] = []
    monkeypatch.setattr(db_delete_retry.time, "sleep", lambda s: attese.append(s))
    db_delete_retry.delete_con_ritentativi(lambda: None, etichetta="t")
    assert attese == []


def test_ritentativi_falsificazione_senza_ritentativi_basta_1_fallimento():
    """Falsificazione dell'helper: con tentativi=1 (come 'prima', zero ritentativi)
    una delete che fallisce 2 volte e poi riuscirebbe non ha nessuna altra chance:
    l'eccezione risale subito al primo colpo."""
    chiamate = {"n": 0}

    def azione() -> None:
        chiamate["n"] += 1
        if chiamate["n"] < 3:
            raise RuntimeError("timeout transitorio")

    with pytest.raises(RuntimeError):
        db_delete_retry.delete_con_ritentativi(azione, etichetta="t", tentativi=1)
    assert chiamate["n"] == 1


# ---------------------------------------------------------------------------
# 5 script storici: delete fallisce 2 volte poi riesce -> insert UNA volta,
# nessun doppione; delete fallisce sempre -> nessun insert, propaga l'errore.
# ---------------------------------------------------------------------------
CASI = [
    (
        "standings",
        stb,
        "backfill_standings_for_league_season",
        "fetch_standings_from_api",
        "map_standings_response_to_rows",
    ),
    (
        "injuries",
        inb,
        "backfill_injuries_for_league_season",
        "fetch_injuries_from_api",
        "map_injuries_response_to_rows",
    ),
    (
        "top_scorers",
        tsb,
        "backfill_top_scorers_for_league_season",
        "fetch_top_scorers_from_api",
        "map_top_scorers_response_to_rows",
    ),
    (
        "top_assists",
        tab,
        "backfill_top_assists_for_league_season",
        "fetch_top_assists_from_api",
        "map_top_assists_response_to_rows",
    ),
]


def _riga(tabella: str) -> Dict[str, Any]:
    return {"league_id": 135, "season_year": 2026, "team_id": 1, "tabella": tabella}


@pytest.mark.parametrize("tabella,modulo,nome_backfill,nome_fetch,nome_map", CASI)
def test_delete_fallisce_2_volte_poi_riesce_insert_una_volta_no_doppioni(
    monkeypatch, tabella, modulo, nome_backfill, nome_fetch, nome_map
):
    sb = FakeSupabase(fallimenti_delete={tabella: 2})
    monkeypatch.setattr(modulo, "get_supabase", lambda: sb)
    monkeypatch.setattr(modulo, nome_fetch, lambda league_id, season_year: {"response": [{"x": 1}]})
    monkeypatch.setattr(modulo, nome_map, lambda data, league_id, season_year: [_riga(tabella)])

    getattr(modulo, nome_backfill)(135, 2026)  # nessuna eccezione

    assert sb.tentativi_delete[tabella] == 3
    assert sb.inserite[tabella] == [_riga(tabella)]  # UNA volta, niente doppioni


@pytest.mark.parametrize("tabella,modulo,nome_backfill,nome_fetch,nome_map", CASI)
def test_delete_fallisce_sempre_nessun_insert_esito_errore(
    monkeypatch, tabella, modulo, nome_backfill, nome_fetch, nome_map
):
    sb = FakeSupabase(fallimenti_delete={tabella: 99})
    monkeypatch.setattr(modulo, "get_supabase", lambda: sb)
    monkeypatch.setattr(modulo, nome_fetch, lambda league_id, season_year: {"response": [{"x": 1}]})
    monkeypatch.setattr(modulo, nome_map, lambda data, league_id, season_year: [_riga(tabella)])

    with pytest.raises(RuntimeError, match="57014"):
        getattr(modulo, nome_backfill)(135, 2026)

    assert sb.tentativi_delete[tabella] == 3  # 3 tentativi, poi propaga
    assert sb.inserite[tabella] == []  # NESSUN insert


def test_delete_fallisce_2_volte_poi_riesce_top_cards_insert_una_volta(monkeypatch):
    sb = FakeSupabase(fallimenti_delete={"top_cards": 2})
    monkeypatch.setattr(tcb, "get_supabase", lambda: sb)
    monkeypatch.setattr(tcb, "fetch_top_yellow_cards_from_api", lambda l, s: {"response": [{"x": 1}]})
    monkeypatch.setattr(tcb, "fetch_top_red_cards_from_api", lambda l, s: {"response": [{"x": 1}]})
    monkeypatch.setattr(
        tcb, "map_top_cards_response_to_rows",
        lambda data, league_id, season_year, card_type: [{"league_id": 135, "season_year": 2026,
                                                            "card_type": card_type}],
    )

    tcb.backfill_top_cards_for_league_season(135, 2026)

    assert sb.tentativi_delete["top_cards"] == 3
    assert sb.inserite["top_cards"] == [
        {"league_id": 135, "season_year": 2026, "card_type": "yellow"},
        {"league_id": 135, "season_year": 2026, "card_type": "red"},
    ]


def test_delete_fallisce_sempre_top_cards_nessun_insert(monkeypatch):
    sb = FakeSupabase(fallimenti_delete={"top_cards": 99})
    monkeypatch.setattr(tcb, "get_supabase", lambda: sb)
    monkeypatch.setattr(tcb, "fetch_top_yellow_cards_from_api", lambda l, s: {"response": [{"x": 1}]})
    monkeypatch.setattr(tcb, "fetch_top_red_cards_from_api", lambda l, s: {"response": [{"x": 1}]})
    monkeypatch.setattr(
        tcb, "map_top_cards_response_to_rows",
        lambda data, league_id, season_year, card_type: [{"league_id": 135, "season_year": 2026,
                                                            "card_type": card_type}],
    )

    with pytest.raises(RuntimeError, match="57014"):
        tcb.backfill_top_cards_for_league_season(135, 2026)

    assert sb.tentativi_delete["top_cards"] == 3
    assert sb.inserite["top_cards"] == []


@pytest.mark.parametrize("tabella,modulo,nome_backfill,nome_fetch,nome_map", CASI)
def test_falsificazione_senza_ritentativo_2_fallimenti_bastano_a_bloccare(
    monkeypatch, tabella, modulo, nome_backfill, nome_fetch, nome_map
):
    """Falsificazione: se si toglie il ritentativo (delete_con_ritentativi con
    tentativi=1, come faceva il codice vecchio senza nemmeno il logger.error che
    inghiottiva), UNA delete che fallirebbe solo la prima volta (poi riuscirebbe)
    non arriva mai all'insert -> comportamento diverso da quello certificato sopra
    (insert eseguito). Dimostra che il ritentativo e' cio' che fa la differenza."""
    sb = FakeSupabase(fallimenti_delete={tabella: 1})
    monkeypatch.setattr(modulo, "get_supabase", lambda: sb)
    monkeypatch.setattr(modulo, nome_fetch, lambda league_id, season_year: {"response": [{"x": 1}]})
    monkeypatch.setattr(modulo, nome_map, lambda data, league_id, season_year: [_riga(tabella)])

    # patch mirato: delete_con_ritentativi con un solo tentativo (equivalente a
    # "nessun ritentativo")
    delete_func_module = sys.modules[modulo.__name__]
    monkeypatch.setattr(
        delete_func_module, "delete_con_ritentativi",
        lambda azione, **kw: db_delete_retry.delete_con_ritentativi(azione, **{**kw, "tentativi": 1}),
    )

    with pytest.raises(RuntimeError, match="57014"):
        getattr(modulo, nome_backfill)(135, 2026)
    assert sb.inserite[tabella] == []


# ---------------------------------------------------------------------------
# season_aggregates.esegui_aggregato
# ---------------------------------------------------------------------------
class _ClientRisposta:
    def __init__(self, risposte: Dict[str, Any]) -> None:
        self.risposte = risposte
        self.chiamate: List[str] = []

    def call(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self.chiamate.append(endpoint)
        return self.risposte.get(endpoint, {"response": []})


def _riga_agg() -> Dict[str, Any]:
    return {"league_id": 135, "season_year": 2026, "rank": 1}


def test_aggregati_delete_fallisce_2_volte_poi_riesce_insert_una_volta(monkeypatch):
    sb = FakeSupabase(fallimenti_delete={"standings": 2})
    client = _ClientRisposta({"/standings": {"response": [{"league": {"standings": [[{"rank": 1}]]}}]}})
    monkeypatch.setattr(
        sa, "_mappa", lambda nome: (lambda dati, league_id, season_year, *a: [_riga_agg()])
    )

    esito = sa.esegui_aggregato(sb, client, "standings", 135, 2026)

    assert esito == "righe"
    assert sb.tentativi_delete["standings"] == 3
    assert sb.inserite["standings"] == [_riga_agg()]


def test_aggregati_delete_fallisce_sempre_esito_errore_nessun_insert(monkeypatch):
    sb = FakeSupabase(fallimenti_delete={"standings": 99})
    client = _ClientRisposta({"/standings": {"response": [{"league": {"standings": [[{"rank": 1}]]}}]}})
    monkeypatch.setattr(
        sa, "_mappa", lambda nome: (lambda dati, league_id, season_year, *a: [_riga_agg()])
    )

    esito = sa.esegui_aggregato(sb, client, "standings", 135, 2026)

    assert esito == "errore"
    assert sb.tentativi_delete["standings"] == 3
    assert sb.inserite["standings"] == []


def test_aggregati_delete_ok_insert_fallito_resta_parziale(monkeypatch):
    """Conferma comportamento gia' esistente (da verificare, non da cambiare):
    delete riuscita + insert fallito -> 'parziale', non 'errore' ne' 'righe'."""
    monkeypatch.setattr(
        sa, "_mappa", lambda nome: (lambda dati, league_id, season_year, *a: [_riga_agg()])
    )
    client = _ClientRisposta({"/standings": {"response": [{"league": {"standings": [[{"rank": 1}]]}}]}})

    class _SbInsertRotto(FakeSupabase):
        def table(self, nome):
            t = super().table(nome)

            def insert_rotto(righe):
                raise RuntimeError("insert fallito")

            t.insert = insert_rotto
            return t

    sb_rotto = _SbInsertRotto()
    esito = sa.esegui_aggregato(sb_rotto, client, "standings", 135, 2026)

    assert esito == "parziale"
    assert sb_rotto.tentativi_delete["standings"] == 1  # delete OK al primo colpo
    assert sb_rotto.inserite["standings"] == []
