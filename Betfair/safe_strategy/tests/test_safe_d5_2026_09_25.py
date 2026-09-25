# -*- coding: utf-8 -*-
"""D5 - decisioni dell'utente del 25/09 sui dubbi del referto Q1/Q4/Q5 (Safe).

  1. coppe AMMESSE, veto SOLO sulle FINALI (round API-Football; in subordine
     il nome dell'evento Betfair);
  2. Bolivia tolta dal veto;
  3. competizione assente: nessun veto (invariato);
  4. femminile riconosciuto anche dai NOMI SQUADRA;
  5. ESATTO: scontri diretti VERI dal DB (la lista della Dashboard), «tanti
     gol» = 4 o piu' gol (2-2, 3-3, 4-2, 4-1 ...);
  6. ESATTO: forze attacco/difesa della Dashboard dichiarate nella nota;
  7. tennis: «sfavorito estremo» = l'avversario di un favorito pre-partita
     sotto 1,20 (quota back del FAVORITO, non piu' 4,0 sul leader).

I FINTI PARLANO COME IL VERO:
  * le righe di scan vengono da `test_engine.calcio_payload` /
    `tennis_payload` (chiavi di `service.build_rows`) e passano da
    `build_*_ctx_from_scan`;
  * le righe della finestra fixture hanno le colonne di
    `omega_db.fixtures_for_window`; la scheda ha le chiavi della proiezione
    `db._SCHEDA_SELECT`; le voci h2h hanno la forma VERA di API-Football
    (letta dal DB il 25/09, sonda `AUDIT_2026-09-25/sonde/d5_schema_sola_lettura.py`);
  * lo scanner e' `service.Scanner` vero (`hydrate_schede` + `build_rows`).

Il file non stampa nulla di non-ASCII (console Windows cp1252).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from Betfair.safe_strategy import certificazione as CERT
from Betfair.safe_strategy import db as SD
from Betfair.safe_strategy import engine as E
from Betfair.safe_strategy import selezione as SEL
from Betfair.safe_strategy import service as SV
from Betfair.safe_strategy import veto_campionati as V
from Betfair.safe_strategy.tests.test_engine import calcio_payload, check, tennis_payload

PUNTA = {"minute": 70, "sh": 2, "sa": 0, "fav_back": 1.06, "fav_lay": 1.07}


def _ctx(**riga: Any) -> E.FootballMatchCtx:
    over = {k: riga.pop(k) for k in list(riga) if k in (
        "minute", "sh", "sa", "fav_back", "fav_lay")}
    p = calcio_payload(**over)
    p.update(riga)
    return E.build_football_ctx_from_scan("ev1", p, 50, 60)


def _tre(**riga: Any) -> Dict[str, E.VariantEvaluation]:
    par = E.merge_params(None)
    return {
        "base": E.evaluate_base(_ctx(**riga), par["base"]),
        "esatto": E.evaluate_esatto(_ctx(minute=49, **riga), par["esatto"], "home"),
        "punta": E.evaluate_punta(_ctx(**PUNTA, **riga), par["punta"]),
    }


# ===========================================================================
# PUNTO 1 - coppe ammesse, veto SOLO sulle finali
# ===========================================================================
# nomi VERI dei round (DB `matches`, 25/09: d5_round_finali_output.txt)
ROUND_FINALI = ["Final", "Finals", "Grand Final", "Clausura - Final",
                "Clausura - Gran Final", "Promotion Play-offs - Final",
                "Promotion Play-offs - Finals", "Relegation Play-offs - Finals",
                "Championship - Final", "Final - Relegation", "Final - Promotion",
                "Promotion Play-offs - final", "Southern Central Play-offs -  Final",
                "Clausura - Clausura - Final", "Fase Final Filiales � Finals"]
ROUND_NON_FINALI = ["Semi-finals", "Quarter-finals", "Semi-finals\t", "Semi finals",
                    "Semi-Finals", "Quarter-Finals", "Regular Season - 5",
                    "Round of 16", "8th Finals", "1/128-finals", "1/2 Final",
                    "Elimination Finals", "Final Round - 3", "Final Group - 1",
                    "Finals - 11", "Finals - 1", "3rd Place Final", "Final - 3rd place",
                    "Placement matches - Final", "7th Place Final",
                    "Promotion Play-offs - Semi-finals", "Group Stage - 2", "", "   "]


@pytest.mark.parametrize("r", ROUND_FINALI)
def test_d5_p1_round_finale_riconosciuto(r):
    assert V.is_round_finale(r) is True, r


@pytest.mark.parametrize("r", ROUND_NON_FINALI + [None])
def test_d5_p1_round_non_finale_non_scatta(r):
    assert V.is_round_finale(r) is False, r


def test_d5_p1_la_finale_scarta_le_tre_varianti_col_motivo_dichiarato():
    for variante, ev in _tre(fixture_round="Final").items():
        ck = check(ev, "campionato")
        assert ev.state == "no" and ck is not None and ck.ok is False, variante
        assert ck.value == V.MOTIVO_FINALE_ROUND, (variante, ck.value)
        assert [c.id for c in ev.checks if c.ok is False] == ["campionato"], variante


@pytest.mark.parametrize("r", ["Semi-finals", "Quarter-finals", "Regular Season - 5", None])
def test_d5_p1_semifinali_giornate_e_round_assente_passano(r):
    for variante, ev in _tre(fixture_round=r).items():
        assert ev.state == "signal", (variante, r)
        assert check(ev, "campionato").ok is True


@pytest.mark.parametrize("coppa", ["English FA Cup", "Coppa Italia", "UEFA Champions League",
                                   "Copa Libertadores", "DFB Pokal"])
def test_d5_p1_le_coppe_sono_ammesse_fuori_dalla_finale(coppa):
    assert V.voce_vietata(coppa) is None
    for variante, ev in _tre(competition=coppa, fixture_round="Round of 16").items():
        assert ev.state == "signal", (variante, coppa)
        assert check(ev, "campionato").value == coppa
    # ...ma la FINALE di quella coppa no
    assert _tre(competition=coppa, fixture_round="Final")["base"].state == "no"


def test_d5_p1_il_round_vince_sul_nome_evento():
    """Il round c'e' e dice semifinale: il nome evento con «Final» non conta
    (la fonte (b) vale SOLO se il round manca)."""
    ev = _tre(fixture_round="Semi-finals", event_name="Nord FC v Sud FC - Cup Final")
    assert ev["base"].state == "signal"
    ev2 = _tre(fixture_round=None, event_name="Nord FC v Sud FC - Cup Final")
    ck = check(ev2["base"], "campionato")
    assert ev2["base"].state == "no" and ck.value == V.MOTIVO_FINALE_NOME


@pytest.mark.parametrize("nome,atteso", [
    ("Nord FC v Sud FC - Final", True), ("Copa del Rey Final", True),
    ("Cup Semi Final", False), ("Semi-final 1st Leg", False),
    ("Quarter-final", False), ("3rd Place Final", False),
    ("Nord FC v Sud FC", False), ("Finals Series", False), (None, False),
])
def test_d5_p1_nome_evento_in_subordine(nome, atteso):
    assert V.nome_indica_finale(nome) is atteso


def test_d5_p1_finale_anche_con_competizione_assente():
    """Competizione assente (banco, LIMITE 1): nessun veto per il nome che
    manca, MA una finale riconosciuta dal round resta una finale."""
    ev = _tre(competition=None, fixture_round="Final")["base"]
    assert check(ev, "campionato").ok is False
    ev2 = _tre(competition=None, fixture_round="Regular Season - 5")["base"]
    assert check(ev2, "campionato") is None and ev2.state == "signal"


# ===========================================================================
# PUNTO 2 - Bolivia ammessa; PUNTO 3 - competizione assente: nessun check
# ===========================================================================
@pytest.mark.parametrize("nome", ["Bolivian Primera Division", "Bolivia - Division Profesional"])
def test_d5_p2_bolivia_ammessa(nome):
    assert V.voce_vietata(nome) is None
    assert all(ev.state == "signal" for ev in _tre(competition=nome).values())


def test_d5_voci_rimaste_sono_solo_quelle_del_video():
    assert [v.codice for v in V.VOCI] == ["femminile", "amichevoli", "bundesliga_2",
                                         "bundesliga", "eerste_divisie", "eredivisie"]


def test_d5_p3_competizione_assente_nessun_check():
    for ev in _tre(competition=None).values():
        assert ev.state == "signal" and check(ev, "campionato") is None


# ===========================================================================
# PUNTO 4 - femminile anche dai NOMI SQUADRA
# ===========================================================================
@pytest.mark.parametrize("casa,ospite", [
    ("Arsenal (W)", "Chelsea (W)"), ("Arsenal W", "Nord FC"), ("Nord FC", "Chelsea Women"),
    ("Juventus Femminile", "Nord FC"), ("Glasgow City Ladies", "Nord FC"),
    ("Wolfsburg Frauen", "Nord FC"), ("Real Madrid Femenino", "Nord FC"),
    ("Barcelona Femenina", "Nord FC"), ("Nord FC", "Santa Fe W"),
])
def test_d5_p4_squadra_femminile_scarta_anche_in_un_campionato_lecito(casa, ospite):
    for variante, ev in _tre(home=casa, away=ospite, competition="Serie A").items():
        ck = check(ev, "campionato")
        assert ev.state == "no" and ck.ok is False, (variante, casa, ospite)
        assert ck.value == V.MOTIVO_SQUADRA_FEMMINILE


@pytest.mark.parametrize("nome", ["W Connection", "Wolverhampton Wanderers", "Wrexham",
                                  "Swansea", "Nord FC", "Lewes", "Womersley United",
                                  "Frauenfeld", None, ""])
def test_d5_p4_nomi_maschili_non_scattano(nome):
    assert V.squadra_femminile(nome) is False, nome


def test_d5_p4_con_competizione_assente_il_nome_squadra_basta():
    ev = _tre(competition=None, home="Arsenal (W)", away="Chelsea (W)")["base"]
    assert check(ev, "campionato").ok is False


# ===========================================================================
# PUNTI 5 e 6 - la SCHEDA DB: h2h VERI, forze della Dashboard
# ===========================================================================
def _h2h(gh: Optional[int], ga: Optional[int], stato: str = "FT", fid: int = 900,
         ft: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Una voce di `raw_json.response[0].h2h` con la forma VERA di API-Football."""
    return {
        "goals": {"away": ga, "home": gh},
        "score": {"penalty": {"away": None, "home": None},
                  "fulltime": ft if ft is not None else {"away": ga, "home": gh},
                  "halftime": {"away": 0, "home": 0},
                  "extratime": {"away": None, "home": None}},
        "teams": {"away": {"id": 2, "name": "Sud FC", "winner": None},
                  "home": {"id": 1, "name": "Nord FC", "winner": None}},
        "league": {"id": 135, "name": "Serie A", "round": "Regular Season - 5",
                   "season": 2025, "country": "Italy"},
        "fixture": {"id": fid, "date": "2025-09-09T20:00:00+00:00",
                    "status": {"long": "Match Finished", "extra": None, "short": stato,
                               "elapsed": 90}},
    }


def _last5(subiti_media: str) -> Dict[str, Any]:
    return {"att": "50%", "def": "71%", "form": "73%", "played": 5,
            "goals": {"for": {"total": 7, "average": "1.4"},
                      "against": {"total": 4, "average": subiti_media}}}


def _scheda(fid: int = 555, h2h: Optional[List[Any]] = None, casa: str = "0.8",
            fuori: str = "1.6") -> Dict[str, Any]:
    """Riga della proiezione `db._SCHEDA_SELECT` (stesse chiavi)."""
    return {"fixture_id": fid,
            "h2h": h2h if h2h is not None else [_h2h(2, 2), _h2h(4, 1), _h2h(1, 0),
                                               _h2h(0, 0), _h2h(3, 2)],
            "cmp": {"att": {"away": "55%", "home": "45%"}, "def": {"away": "40%", "home": "60%"},
                    "h2h": {"away": "62%", "home": "38%"}, "form": {"away": "48%", "home": "52%"},
                    "goals": {"away": "75%", "home": "25%"},
                    "total": {"away": "62.8%", "home": "37.2%"},
                    "poisson_distribution": {"away": "75%", "home": "25%"}},
            "last5_home": _last5(casa), "last5_away": _last5(fuori)}


def test_d5_p5_conteggio_4_o_piu_gol_sui_soli_finiti():
    lista = [_h2h(2, 2), _h2h(4, 1), _h2h(4, 2), _h2h(3, 2), _h2h(3, 1),
             _h2h(1, 0), _h2h(2, 1), _h2h(0, 0),
             _h2h(None, None, stato="NS"), _h2h(5, 0, stato="PST"),
             # supplementari: conta il punteggio dei 90' (1-1), non i gol (3-1)
             _h2h(3, 1, stato="AET", ft={"home": 1, "away": 1})]
    assert SEL.conta_scontri_diretti(lista) == {"incontri": 9, "tanti_gol": 5}
    assert SEL.conta_scontri_diretti([]) == {"incontri": 0, "tanti_gol": 0}
    assert SEL.conta_scontri_diretti(None) is None
    # la fixture stessa, se mai comparisse nella lista, non e' uno scontro passato
    assert SEL.conta_scontri_diretti([_h2h(3, 3, fid=555)], escludi_fixture=555) == \
        {"incontri": 0, "tanti_gol": 0}


def test_d5_p5_p6_hint_dalla_scheda_e_orientamento():
    h = SEL.hint_da_scheda(_scheda())
    assert h == {"fonte": "fixture_predictions.raw_json", "fixture_id": 555,
                 "h2h_meetings": 5, "h2h_many_goals": 3,
                 "conceded": {"home": 0.8, "away": 1.6},
                 "forze": {"att": {"home": 45.0, "away": 55.0},
                           "def": {"home": 60.0, "away": 40.0}}}
    inv = SEL.hint_da_scheda(_scheda(), invertita=True)
    assert inv["conceded"] == {"home": 1.6, "away": 0.8}
    assert inv["forze"]["att"] == {"home": 55.0, "away": 45.0}
    assert SEL.hint_da_scheda(None) is None
    assert SEL.hint_da_scheda({"fixture_id": 1, "h2h": None, "cmp": None,
                               "last5_home": None, "last5_away": None}) is None


def _esatto(hint: Optional[Dict[str, Any]], lato: str = "home", **par: Any):
    p = calcio_payload(minute=49)
    p["selection_hint"] = hint
    params = dict(E.merge_params(None)["esatto"], **par)
    return E.evaluate_esatto(E.build_football_ctx_from_scan("ev1", p, 40, 60), params, lato)


def test_d5_p5_nota_dichiarata_e_verdetto():
    h = SEL.hint_da_scheda(_scheda(h2h=[_h2h(2, 2), _h2h(4, 1), _h2h(1, 0), _h2h(0, 0)]))
    ev = _esatto(h)
    ck = check(ev, "h2hDifesa")
    # 2/4 = 50% <= 58%: passa; difesa avversaria (ospite) 1,6 > 1,37: NON passa
    assert ck.ok is False and ev.state == "no"
    assert ck.value.startswith(f"h2h: 4 partite, 2 con {E.GEQ}4 gol {E.MIDDOT} "
                               "difesa avversaria 1,60 gol subiti")
    # la stessa scheda bancando l'OSPITE: la difesa che conta e' la casa (0,8)
    assert check(_esatto(h, "away"), "h2hDifesa").ok is True


def test_d5_p5_troppe_partite_da_tanti_gol_scarta():
    h = SEL.hint_da_scheda(_scheda(h2h=[_h2h(2, 2), _h2h(4, 1), _h2h(4, 2), _h2h(1, 0)],
                                   fuori="0.4"))
    ck = check(_esatto(h), "h2hDifesa")
    assert ck.ok is False and f"3 con {E.GEQ}4 gol" in ck.value


def test_d5_p5_pochi_scontri_non_bloccano_e_lo_dicono():
    h = SEL.hint_da_scheda(_scheda(h2h=[_h2h(3, 3), _h2h(4, 4)], fuori="0.4"))
    ck = check(_esatto(h), "h2hDifesa")
    assert ck.ok is True
    assert f"h2h: 2 partite, 2 con {E.GEQ}4 gol" + E.SELEZIONE_H2H_POCHI in ck.value


def test_d5_p5_nessuno_scontro_nel_db_non_blocca_e_lo_dice():
    h = SEL.hint_da_scheda(_scheda(h2h=[], fuori="0.4"))
    ck = check(_esatto(h), "h2hDifesa")
    assert ck.ok is True and ck.value.startswith(E.SELEZIONE_H2H_NESSUNO)


def test_d5_p6_forze_solo_nota_non_bloccano():
    s = _scheda(h2h=[_h2h(1, 0)] * 4, fuori="0.4")
    s["cmp"]["att"] = {"home": "0%", "away": "100%"}
    ck = check(_esatto(SEL.hint_da_scheda(s)), "h2hDifesa")
    assert ck.ok is True
    assert ck.value.endswith(f"forze att 0-100 {E.MIDDOT} def 60-40")


# --- le letture: una per partita, cache, mai un'eccezione -------------------
T0 = datetime(2026, 9, 25, 18, 0, tzinfo=timezone.utc)


class _Letture:
    """Le tre letture di `SchedeFixture` con le chiavi VERE."""

    def __init__(self, righe_finestra, schede, rounds, esplode=False):
        self.righe_finestra = righe_finestra
        self.schede = schede
        self.rounds = rounds
        self.esplode = esplode
        self.chiamate: List[Any] = []

    def finestra(self, lo, hi):
        self.chiamate.append(("finestra", lo, hi))
        if self.esplode:
            raise RuntimeError("57014 statement timeout")
        return self.righe_finestra

    def leggi_schede(self, ids):
        self.chiamate.append(("schede", list(ids)))
        return {i: self.schede.get(i) for i in ids if i in self.schede}

    def leggi_round(self, ids):
        self.chiamate.append(("round", list(ids)))
        return {i: self.rounds.get(i) for i in ids if i in self.rounds}


def _fixture(fid, casa, ospite, quando=T0):
    # colonne di `omega_db.fixtures_for_window`
    return {"fixture_id": fid, "home_team_name": casa, "away_team_name": ospite,
            "fixture_date": quando.isoformat(), "league_id": 135,
            "home_team_id": fid * 10, "away_team_id": fid * 10 + 1}


class _Orologio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _schede(letture, orologio=None):
    return SEL.SchedeFixture(leggi_finestra=letture.finestra, leggi_schede=letture.leggi_schede,
                             leggi_round=letture.leggi_round, orologio=orologio or _Orologio())


EVENTI = [{"event_id": "e1", "event_name": "Roma v Lazio", "open_date": T0.isoformat()},
          {"event_id": "e2", "event_name": "Inter v Milan", "open_date": T0.isoformat()}]


def test_d5_letture_una_volta_per_partita():
    let = _Letture([_fixture(1, "Roma", "Lazio"), _fixture(2, "Inter", "Milan")],
                   {1: _scheda(1), 2: _scheda(2)}, {1: "Final", 2: "Regular Season - 5"})
    sch = _schede(let)
    assert sch.aggiorna(EVENTI, T0) == 2
    assert [c[0] for c in let.chiamate] == ["finestra", "schede", "round"]
    assert let.chiamate[1][1] == [1, 2]            # UNA query per il blocco
    assert sch.round("e1") == "Final" and sch.round("e2") == "Regular Season - 5"
    assert sch.hint("e1")["fixture_id"] == 1 and sch.hint("e1")["h2h_meetings"] == 5
    # giro dopo: niente di nuovo, NESSUNA lettura
    assert sch.aggiorna(EVENTI, T0) == 0
    assert len(let.chiamate) == 3
    assert sch.hint("sconosciuto") is None and sch.round("sconosciuto") is None


def test_d5_orientamento_invertito_scambia_i_lati():
    let = _Letture([_fixture(1, "Lazio", "Roma")], {1: _scheda(1)}, {1: None})
    sch = _schede(let)
    sch.aggiorna(EVENTI[:1], T0)
    assert sch.hint("e1")["conceded"] == {"home": 1.6, "away": 0.8}
    assert sch.round("e1") is None


def test_d5_non_abbinato_si_riprova_solo_a_finestra_nuova():
    orologio = _Orologio()
    let = _Letture([_fixture(9, "Juventus", "Torino")], {}, {})
    sch = _schede(let, orologio)
    sch.aggiorna(EVENTI[:1], T0)
    sch.aggiorna(EVENTI[:1], T0)
    assert [c[0] for c in let.chiamate] == ["finestra"]
    assert sch.hint("e1") is None
    orologio.t += 601                                # finestra scaduta
    let.righe_finestra = [_fixture(1, "Roma", "Lazio")]
    let.schede = {1: _scheda(1)}
    sch.aggiorna(EVENTI[:1], T0)
    assert sch.hint("e1") is not None


def test_d5_db_che_non_risponde_non_ferma_lo_scanner():
    orologio = _Orologio()
    let = _Letture([], {}, {}, esplode=True)
    sch = _schede(let, orologio)
    assert sch.aggiorna(EVENTI, T0) == 0                   # nessuna eccezione
    assert sch.aggiorna(EVENTI, T0) == 0                   # in pausa: nessuna lettura
    assert len(let.chiamate) == 1
    orologio.t += 61
    sch.aggiorna(EVENTI, T0)
    assert len(let.chiamate) == 2


def test_d5_lo_scanner_vero_pubblica_scheda_e_round():
    """`service.Scanner` vero: `hydrate_schede` (solo nel tick) + `build_rows`."""
    scan = SV.Scanner(api_client=None, dry=True, use_stream=False, canale=False)
    adesso = datetime.now(timezone.utc)
    scan.sports["calcio"].metas = {"c1": {
        "event_id": "c1", "market_id": "1.200", "event_name": "Roma v Lazio",
        "open_date": (adesso - timedelta(minutes=50)).isoformat(),
        "competition": "Coppa Italia", "runners": [],
        "sides": {"home": 11, "draw": 22, "away": 33}}}
    scan.events["c1"] = {"sport": "calcio", "inplay": True, "mo_status": "OPEN"}
    scan._rebuild_market_index()
    let = _Letture([_fixture(1, "Roma", "Lazio", adesso - timedelta(minutes=50))],
                   {1: _scheda(1)}, {1: "Final"})
    scan.schede = _schede(let)
    righe, _ = scan.build_rows(adesso)
    p = righe[0]["payload"]
    assert p["fixture_round"] is None and p["selection_hint"] is None   # prima del tick
    assert let.chiamate == []                                          # build_rows NON legge
    assert scan.hydrate_schede(adesso) == 1
    # la riga CAMBIA (firma nuova) ma il freno per-evento la tratterrebbe:
    # lo si azzera come se fosse passato l'intervallo minimo
    scan.last_pub_mono.clear()
    righe, _ = scan.build_rows(adesso)
    p = righe[0]["payload"]
    assert p["fixture_round"] == "Final"
    assert p["selection_hint"]["h2h_many_goals"] == 3
    # e i due motori leggono la riga: la finale della coppa e' vietata
    ctx = E.build_football_ctx_from_scan("c1", p, None, None)
    assert ctx.fixture_round == "Final"
    assert E.campionato_check(ctx.competition, {"vetoCampionati": True},
                              fixture_round=ctx.fixture_round).ok is False


class _ClientFinto:
    """Il client supabase come lo usa `db.py`: table/select/in_/execute."""

    def __init__(self, data):
        self.data = data
        self.fatto: List[Any] = []

    def table(self, nome):
        self.fatto.append(("table", nome))
        return self

    def select(self, colonne):
        self.fatto.append(("select", colonne))
        return self

    def in_(self, col, valori):
        self.fatto.append(("in_", col, list(valori)))
        return self

    def execute(self):
        from types import SimpleNamespace
        return SimpleNamespace(data=self.data)


def test_d5_le_query_sono_proiezioni_leggere(monkeypatch):
    cl = _ClientFinto([{"fixture_id": 7, "h2h": [], "cmp": None, "last5_home": None,
                        "last5_away": None}])
    monkeypatch.setattr(SD, "get_supabase_client", lambda: cl)
    out = SD.load_schede_fixture([7])
    assert list(out) == [7]
    assert cl.fatto[0] == ("table", "fixture_predictions")
    sel = cl.fatto[1][1]
    assert "raw_json->response->0->h2h" in sel and "raw_json->response->0->comparison" in sel
    assert "raw_json," not in sel and not sel.endswith("raw_json")    # mai tutto raw_json
    assert cl.fatto[2] == ("in_", "fixture_id", [7])
    cl2 = _ClientFinto([{"fixture_id": 7, "round": "Final"}])
    monkeypatch.setattr(SD, "get_supabase_client", lambda: cl2)
    assert SD.load_round_fixture([7]) == {7: "Final"}
    assert cl2.fatto[0] == ("table", "matches")
    assert cl2.fatto[1][1] == "fixture_id,round:raw_json->league->>round"
    assert SD.load_schede_fixture([]) == {} and SD.load_round_fixture([]) == {}


def test_d5_e10_segue_la_regola_nuova():
    """E10 rifa' il conto con le chiavi nuove: 2 scontri (sotto il minimo) con
    2 partite da tanti gol = NON blocca; un motore che bloccasse e' rosso."""
    from Betfair.safe_strategy.tests.test_certificazione_c3_2026_09_16 import contesto, payload
    par = dict(E.merge_params(None)["esatto"], requireSelection=True)
    p = payload()
    p["selection_hint"] = {"fonte": SEL.FONTE_DB, "fixture_id": 1, "h2h_meetings": 2,
                           "h2h_many_goals": 2, "conceded": {"home": None, "away": None},
                           "forze": None}
    ev = E.evaluate_esatto(contesto(p), par, "home")
    assert check(ev, "h2hDifesa").ok is True

    def _oss(e):
        return CERT.Valutazione(strategia="esatto", ctx=contesto(p), ev=e, par=par,
                                params={**E.merge_params(None), "esatto": par})
    assert "E10" not in {v.codice for v in CERT.verifica(_oss(ev))}
    storti = tuple(E.ConditionCheck(c.id, c.label, c.value, False) if c.id == "h2hDifesa"
                   else c for c in ev.checks)
    ev_storto = E.VariantEvaluation(
        variant=ev.variant, state="no", checks=storti, headline=None, side=ev.side,
        selection=ev.selection, entry_odds=ev.entry_odds, entry_size=ev.entry_size,
        market_type=ev.market_type, market_id=ev.market_id,
        selection_id=ev.selection_id, sub_id=ev.sub_id)
    assert "E10" in {v.codice for v in CERT.verifica(_oss(ev_storto))}


# ===========================================================================
# PUNTO 7 - tennis: super favorito < 1,20 -> l'altro e' sfavorito estremo
# ===========================================================================
def _tennis(pre_ko, leader_p2=False, **par):
    if leader_p2:
        p = tennis_payload(sets={"p1": 0, "p2": 1}, games={"p1": 0, "p2": 3})
        p["odds"]["p2"] = {"back": 1.05, "lay": 1.06, "selection_id": 2}
        p["odds"]["p1"] = {"back": 15.0, "lay": 16.0, "selection_id": 1}
    else:
        p = tennis_payload(p1_back=1.05)
    p["pre_ko"] = pre_ko
    params = dict(E.merge_params(None)["tennis"], **par)
    return E.evaluate_tennis(E.build_tennis_ctx_from_scan("tv1", p, 60), params)


def test_d5_p7_default_1_20():
    assert E.DEFAULT_PARAMS["tennis"]["favSuperMax"] == 1.2
    assert "leaderPreMax" not in E.DEFAULT_PARAMS["tennis"]


@pytest.mark.parametrize("fav", [1.01, 1.12, 1.19])
def test_d5_p7_leader_sfavorito_estremo_escluso(fav):
    ev = _tennis({"p1": 8.0, "p2": fav})          # p2 super favorito, leader p1
    ck = check(ev, "leaderPre")
    assert ev.state == "no" and ck.ok is False
    assert ck.value == (f"favorito pre-match {E.fmt_odds(fav)} {E.RARR} "
                        "sfavorito estremo: escluso")
    assert [c.id for c in ev.checks if c.ok is False] == ["leaderPre"]


def test_d5_p7_bordo_stretto_1_20_non_e_super_favorito():
    ev = _tennis({"p1": 4.8, "p2": 1.20})
    assert ev.state == "signal" and check(ev, "leaderPre").ok is True


def test_d5_p7_se_si_punta_il_super_favorito_si_entra():
    ev = _tennis({"p1": 1.10, "p2": 8.0})           # leader p1 = il favorito
    ck = check(ev, "leaderPre")
    assert ev.state == "signal" and ck.ok is True and "si punta il favorito" in ck.value
    # stesso schema col leader p2
    assert check(_tennis({"p1": 8.0, "p2": 1.10}, leader_p2=True), "leaderPre").ok is True
    assert check(_tennis({"p1": 1.10, "p2": 8.0}, leader_p2=True), "leaderPre").ok is False


def test_d5_p7_uno_sfavorito_normale_si_puo_puntare():
    """Il corso: «andare su uno sfavorito, si', puo' essere fattibile [...] ma
    non che sia sfavoritissimo». Favorito a 1,50: il leader a 2,60 si punta
    (con la vecchia soglia 4,0 sul leader, anche un leader a 3,90 passava e
    uno a 4,20 no: ora conta SOLO la quota del favorito)."""
    for pre in ({"p1": 2.60, "p2": 1.50}, {"p1": 4.20, "p2": 1.25}):
        ev = _tennis(pre)
        assert ev.state == "signal", pre


def test_d5_p7_quote_pari_nessun_favorito():
    ck = check(_tennis({"p1": 1.90, "p2": 1.90}), "leaderPre")
    assert ck.ok is True and "nessun favorito" in ck.value


def test_d5_p7_spento_e_chiave_vecchia_ignorata():
    ev = _tennis({"p1": 8.0, "p2": 1.05}, favSuperMax=0)
    assert check(ev, "leaderPre") is None
    par = E.merge_params({"tennis": {"leaderPreMax": 1.01}})["tennis"]
    assert "leaderPreMax" not in par and par["favSuperMax"] == 1.2
    assert E.merge_params({"tennis": {"favSuperMax": "x"}})["tennis"]["favSuperMax"] == 1.2


def test_d5_p7_dato_assente_non_blocca():
    ev = _tennis(None)
    assert ev.state == "signal" and check(ev, "leaderPre").value == E.TENNIS_PRE_ASSENTE


# ===========================================================================
# parita' col gemello TS (la pagina): liste nuove identiche
# ===========================================================================
_TS_VETO = (Path(__file__).resolve().parents[3]
            / "frontend" / "src" / "lib" / "vetoCampionati.ts")


def _ts_lista(nome: str) -> List[str]:
    src = _TS_VETO.read_text(encoding="utf-8")
    m = re.search(r"export const " + nome + r"\s*:\s*string\[\]\s*=\s*\[(.*?)\];", src, re.S)
    assert m, nome
    return re.findall(r"'([^']*)'", m.group(1))


def test_d5_liste_nuove_identiche_nel_gemello_ts():
    assert _ts_lista("FRASI_SQUADRA_FEMMINILE") == list(V.FRASI_SQUADRA_FEMMINILE)
    assert _ts_lista("ROUND_FINALE") == list(V.ROUND_FINALE)
    src = _TS_VETO.read_text(encoding="utf-8")
    for motivo in (V.MOTIVO_FINALE_ROUND, V.MOTIVO_FINALE_NOME, V.MOTIVO_SQUADRA_FEMMINILE):
        assert f"'{motivo}'" in src, motivo
