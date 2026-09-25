# -*- coding: utf-8 -*-
"""Decisioni dell'utente del 25/09 su SAFE: Q1 (BASE, quota di banca 20-34),
Q4 (veto dei campionati del corso), Q5 (tennis, quota minima 1,02).

I FINTI PARLANO COME IL VERO: i contesti passano SEMPRE da
`engine.build_football_ctx_from_scan` / `build_tennis_ctx_from_scan` con le
righe di `safe_strategy_scan` costruite dalle fixture gia' in uso
(`test_engine.calcio_payload`, `test_replay_tennis._payload`), che hanno le
chiavi e i tipi di `service.build_rows`. La competizione e' `payload["competition"]`,
la stessa chiave che lo scanner scrive da `listMarketCatalogue`
(`service.py:449`, `competition.name`).

Il file non stampa nulla di non-ASCII (console Windows cp1252).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from Betfair.safe_strategy import engine as E
from Betfair.safe_strategy import veto_campionati as V
from Betfair.safe_strategy.tests.test_engine import calcio_payload, check

PUNTA = {"minute": 70, "sh": 2, "sa": 0, "fav_back": 1.06, "fav_lay": 1.07}


def _ctx(competition, **over):
    p = calcio_payload(**over)
    p["competition"] = competition
    return E.build_football_ctx_from_scan("ev1", p, 50, 60)


def _tre_varianti(competition):
    """Le tre varianti calcio, ognuna su un contesto in cui darebbe SEGNALE."""
    par = E.merge_params(None)
    return {
        "base": E.evaluate_base(_ctx(competition), par["base"]),
        "esatto": E.evaluate_esatto(_ctx(competition, minute=49), par["esatto"], "home"),
        "punta": E.evaluate_punta(_ctx(competition, **PUNTA), par["punta"]),
    }


# ===========================================================================
# Q4 — VETO DEI CAMPIONATI
# ===========================================================================
# nomi come li scrive Betfair (competition.name) + i sinonimi dell'ordine
VIETATI = {
    "femminile": ["Friendlies Women", "Serie A Femminile", "Liga F (W)",
                  "A-League Women", "Frauen Bundesliga", "Liga MX Femenil",
                  "English Womens Super League"],
    "amichevoli": ["Club Friendlies", "International Friendlies", "Friendlies",
                   "Amichevoli Internazionali"],
    "coppe": ["English FA Cup", "DFB Pokal", "KNVB Beker", "Coppa Italia",
              "Copa del Rey", "Coupe de France", "UEFA Champions League",
              "UEFA Europa League", "UEFA Europa Conference League",
              "Copa Libertadores", "English League Cup", "Taca de Portugal",
              "Taça de Portugal", "Italian Supercoppa", "EFL Trophy"],
    "bundesliga_2": ["German Bundesliga 2", "2. Bundesliga", "Bundesliga 2",
                     "German 2. Bundesliga", "Bundesliga II"],
    "bundesliga": ["German Bundesliga", "Bundesliga", "1. Bundesliga"],
    "eerste_divisie": ["Dutch Eerste Divisie", "Eerste Divisie",
                       "Keuken Kampioen Divisie"],
    "eredivisie": ["Dutch Eredivisie", "Eredivisie"],
    "bolivia": ["Bolivian Primera Division", "Bolivia - Division Profesional"],
}

# «Migliori campionati» del corso (2. SELEZIONE PARTITE/3. Migliori campionati
# @11.8-39.9): Serie A, Liga, Premier, Ligue 1 e le loro serie B, Cina,
# Giappone, Brasile, Argentina, i restanti europei. Devono PASSARE tutti.
LECITI = ["Italian Serie A", "Italian Serie B", "Spanish La Liga",
          "Spanish Segunda Division", "English Premier League",
          "English Championship", "French Ligue 1", "French Ligue 2",
          "Chinese Super League", "Japanese J League", "Brazilian Serie A",
          "Argentinian Primera Division", "Finnish Veikkausliiga",
          "Polish Ekstraklasa", "Portuguese Primeira Liga", "Turkish Super Lig",
          # la Bundesliga AUSTRIACA non e' quella del video
          "Austrian Bundesliga",
          # la 3. Liga tedesca non e' nominata: solo la serie A e la serie B
          "German 3. Liga",
          "Serie A", "Serie Z"]


def test_ogni_voce_del_corso_ha_citazione_e_almeno_un_nome_betfair_coperto():
    assert {v.codice for v in V.VOCI} == set(VIETATI)
    for v in V.VOCI:
        assert "Competizioni da evitare @" in v.citazione, v.codice
        assert v.frasi, v.codice


@pytest.mark.parametrize("codice,nome", [(c, n) for c, ns in VIETATI.items() for n in ns])
def test_ogni_voce_scarta_le_tre_varianti_col_motivo_dichiarato(codice, nome):
    voce = V.voce_vietata(nome)
    assert voce is not None and voce.codice == codice, (nome, voce)
    motivo = "veto campionato: " + voce.nome + " (corso)"
    for variante, ev in _tre_varianti(nome).items():
        assert ev.state == "no", (variante, nome)
        ck = check(ev, "campionato")
        assert ck is not None and ck.ok is False, (variante, nome)
        assert ck.value == motivo, (variante, ck.value)
        # e' il veto a respingere, non un altro check
        assert [c.id for c in ev.checks if c.ok is False] == ["campionato"], variante


def test_il_motivo_della_serie_b_tedesca_e_bundesliga_2():
    """Ordine dell'utente: «Bundesliga NO, 2. Bundesliga NO». Il motivo deve
    dire QUALE delle due, non ripiegare sulla prima."""
    ck = check(_tre_varianti("German Bundesliga 2")["base"], "campionato")
    assert ck.value == "veto campionato: Bundesliga 2 (corso)"
    ck = check(_tre_varianti("German Bundesliga")["base"], "campionato")
    assert ck.value == "veto campionato: Bundesliga (corso)"


@pytest.mark.parametrize("nome", LECITI)
def test_i_campionati_leciti_passano_su_tutte_e_tre(nome):
    assert V.voce_vietata(nome) is None, nome
    for variante, ev in _tre_varianti(nome).items():
        assert ev.state == "signal", (variante, nome)
        ck = check(ev, "campionato")
        assert ck is not None and ck.ok is True and ck.value == nome


def test_parole_intere_non_pezzi_di_parola():
    """«cup» vieta «FA Cup» ma non «Cupertino»; «w» non vieta «Wales»."""
    for nome in ("Cupertino League", "Welsh Premier League", "Wales Premier",
                 "Copacabana Cities League", "Pokalino Regional"):
        assert V.voce_vietata(nome) is None, nome


def test_maiuscole_accenti_e_punteggiatura_non_contano():
    for nome in ("GERMAN BUNDESLIGA 2", "german-bundesliga-2", "  2.Bundesliga  ",
                 "Bundesliga\t2"):
        assert V.voce_vietata(nome).codice == "bundesliga_2", nome
    assert V.voce_vietata("Taça da Liga").codice == "coppe"


def test_veto_spento_dai_parametri_nessun_check():
    par = E.merge_params({"base": {"vetoCampionati": False},
                          "esatto": {"vetoCampionati": False},
                          "punta": {"vetoCampionati": False}})
    assert E.evaluate_base(_ctx("German Bundesliga"), par["base"]).state == "signal"
    assert E.evaluate_esatto(_ctx("German Bundesliga", minute=49), par["esatto"],
                             "home").state == "signal"
    assert E.evaluate_punta(_ctx("German Bundesliga", **PUNTA), par["punta"]).state == "signal"
    assert check(E.evaluate_base(_ctx("German Bundesliga"), par["base"]), "campionato") is None


def test_veto_acceso_di_default_anche_senza_migrazione():
    for v in ("base", "esatto", "punta"):
        assert E.DEFAULT_PARAMS[v]["vetoCampionati"] is True
        assert E.merge_params(None)[v]["vetoCampionati"] is True
        # un valore non booleano sul DB non lo spegne
        assert E.merge_params({v: {"vetoCampionati": "no"}})[v]["vetoCampionati"] is True


def test_competizione_assente_veto_non_applicabile_dichiarato():
    """Nome assente -> nessun check (come i cartellini: l'assenza del dato non
    e' la lista nera). E' il caso del banco di replay (LIMITE 1: niente
    catalogo, `competition` None)."""
    for nome in (None, "", "   "):
        evs = _tre_varianti(nome)
        for variante, ev in evs.items():
            assert ev.state == "signal", (variante, nome)
            assert check(ev, "campionato") is None


def test_il_tennis_non_ha_il_veto_del_calcio():
    """Il veto e' per le tre varianti CALCIO: il tennis ha i suoi filtri."""
    from Betfair.safe_strategy.tests.test_engine import tennis_ctx
    ev = E.evaluate_tennis(tennis_ctx(competition="Davis Cup"), E.DEFAULT_PARAMS["tennis"])
    assert check(ev, "campionato") is None


# --- parita' con il gemello TypeScript (la pagina) -------------------------
_TS_VETO = (Path(__file__).resolve().parents[3]
            / "frontend" / "src" / "lib" / "vetoCampionati.ts")


def _ts_voci() -> list:
    src = _TS_VETO.read_text(encoding="utf-8")
    inizio = src.index("export const VOCI_VETO")
    inizio = src.index("[", src.index("=", inizio))
    livello, fine = 0, None
    for i in range(inizio, len(src)):
        if src[i] == "[":
            livello += 1
        elif src[i] == "]":
            livello -= 1
            if livello == 0:
                fine = i + 1
                break
    blocco = src[inizio:fine]
    blocco = re.sub(r"//[^\n]*", "", blocco)
    blocco = re.sub(r"(\b[a-z]+)\s*:", r"'\1':", blocco)
    blocco = re.sub(r",(\s*[}\]])", r"\1", blocco)
    return ast.literal_eval(blocco)


def test_la_lista_del_bot_e_quella_della_pagina_sono_identiche():
    ts = _ts_voci()
    py = [{"codice": v.codice, "nome": v.nome, "frasi": list(v.frasi),
           "escluse": list(v.escluse)} for v in V.VOCI]
    assert [{k: t[k] for k in ("codice", "nome", "frasi", "escluse")} for t in ts] == py


# ===========================================================================
# Q1 — nessun filtro sulla favorita live, banda sulla quota di banca
# ===========================================================================
def test_q1_la_favorita_live_non_decide_piu_in_nessuna_direzione():
    par = E.DEFAULT_PARAMS["base"]
    for fav_back in (1.05, 1.20, 1.34, 1.50, 1.90):
        ev = E.evaluate_base(_ctx("Italian Serie A", fav_back=fav_back,
                                  fav_lay=round(fav_back + 0.02, 2)), par)
        assert ev.state == "signal", fav_back
        assert check(ev, "favLive") is None


def test_q1_il_prezzo_d_ingresso_e_il_lay_della_perdente():
    ev = E.evaluate_base(_ctx("Italian Serie A", dog_back=29.0, dog_lay=30.0),
                         E.DEFAULT_PARAMS["base"])
    assert ev.state == "signal"
    assert ev.side == "LAY" and ev.entry_odds == 30.0 and ev.selection == "Sud FC"


def test_q1_lay_assente_resta_nd_mai_un_ingresso_al_buio():
    ev = E.evaluate_base(_ctx("Italian Serie A", dog_lay=None), E.DEFAULT_PARAMS["base"])
    assert ev.state == "nd" and check(ev, "dogLay").ok is None


# ===========================================================================
# Q5 — tennis, quota minima d'ingresso 1,02
# ===========================================================================
def test_q5_default_backmin_102_anche_senza_migrazione():
    assert E.DEFAULT_PARAMS["tennis"]["backMin"] == 1.02
    assert E.merge_params(None)["tennis"]["backMin"] == 1.02


def test_q5_a_101_non_si_entra_a_102_si():
    from Betfair.safe_strategy.tests.test_engine import tennis_ctx
    par = E.DEFAULT_PARAMS["tennis"]
    assert E.evaluate_tennis(tennis_ctx(p1_back=1.01), par).state == "no"
    assert check(E.evaluate_tennis(tennis_ctx(p1_back=1.01), par), "odds").ok is False
    assert E.evaluate_tennis(tennis_ctx(p1_back=1.02), par).state == "signal"


def _t1(params_tennis):
    from Betfair.safe_strategy import certificazione_tennis as CT
    from Betfair.safe_strategy.tests import test_replay_tennis_2026_09_16 as RTT
    # la sezione `tennis` risolta come la fonde il bot (`merge_params`), poi
    # l'override del caso: e' quella che T1 legge (`_par_tennis`)
    params = {**RTT.PARAMS, "tennis": {**E.merge_params(None)["tennis"], **params_tennis}}
    oss = RTT._osserva(ctx=RTT._ctx(), aperture=RTT._apertura(), params=params)
    sol: dict = {}
    viol = [v for v in CT.verifica(oss, sol) if v.codice == "T1"]
    return viol, sol


def test_q5_banco_t1_verde_con_102():
    viol, sol = _t1({})
    assert sol.get("T1") == 1 and viol == []


@pytest.mark.parametrize("valore", [1.01, 1.019, 1.03, None, "x"])
def test_q5_banco_t1_rosso_se_backmin_non_e_102(valore):
    """T1 non e' piu' uno specchio dei parametri: un backMin diverso da 1,02
    (anche se il prezzo del trade sta dentro la banda) e' rosso."""
    viol, sol = _t1({"backMin": valore})
    assert sol.get("T1") == 1
    assert len(viol) == 1 and "1.02" in viol[0].dettaglio, viol
