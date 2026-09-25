"""SPEC §2 «Selezione aggiuntiva» — la voce implementata il 16/09 su ordine
dell'utente: «scontri diretti senza troppi 2-2/3-3, difesa avversaria solida».

Che cosa difendono questi test:
  * il DATO (`selezione.hint`) viene dall'atlante VERO gia' in casa, e i due
    numeri coincidono con un conto fatto a mano sullo stesso file;
  * il FILTRO nel motore vero (`evaluate_esatto`) TACE quando la selezione
    passa e SCATTA quando non passa (i due casi che l'utente ha chiesto);
  * la difesa guardata e' quella AVVERSARIA, non quella della squadra bancata:
    invertire i due lati renderebbe il filtro una moneta;
  * dato assente = «n/d», mai un verdetto: e' la regola di tutto il modulo;
  * spento (default) il filtro non aggiunge niente e non cambia una virgola;
  * il controllo E10 di `certificazione.py` sa diventare ROSSO.

I FINTI PARLANO COME IL VERO: la riga di scan ha le chiavi di
`service.Scanner.build_rows` (`selection_hint` compreso), il contesto lo
costruisce `build_football_ctx_from_scan`, la valutazione e' `evaluate_esatto`.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import inspect
import json
from typing import Any, Dict, Optional

import pytest

from Betfair.safe_strategy import certificazione as CERT
from Betfair.safe_strategy import engine as E
from Betfair.safe_strategy import selezione as SEL
from Betfair.safe_strategy import service as SV
from Betfair.safe_strategy.tests.test_certificazione_c3_2026_09_16 import (
    contesto, payload,
)


# ---------------------------------------------------------------------------
# il DATO: l'atlante vero, letto due volte (dal modulo e a mano)
# ---------------------------------------------------------------------------
def _atlante_a_mano() -> Dict[str, Any]:
    with open(SEL.ATLAS_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_hint_coppia_presente_nellatlante_vero() -> None:
    """Udinese-Venezia sta nell'atlante: i numeri devono coincidere con un
    conto indipendente sullo stesso file."""
    SEL.reset_cache()
    h = SEL.hint("Udinese", "Venezia")
    assert h is not None and h["fonte"] == SEL.FONTE
    atl = _atlante_a_mano()
    idx = {v["team_name"]: k for k, v in atl["by_team"].items()}
    a, b = sorted([int(idx["Udinese"]), int(idx["Venezia"])])
    sc = atl["h2h_hint"][f"{a}-{b}"]["ft_scores_a_b"]
    assert h["h2h_meetings"] == sum(sc.values())
    assert h["h2h_big_draws"] == sc.get("2-2", 0) + sc.get("3-3", 0)
    subiti = sum((atl["by_team"][idx["Udinese"]]
                  ["def_goals_per_match_by_bucket"]).values())
    assert h["conceded"]["home"] == pytest.approx(subiti, abs=1e-4)


def test_hint_coppia_assente_dichiara_il_buco_senza_inventare() -> None:
    """Spagna-Belgio: le due squadre ci sono, lo scontro diretto no (meno di
    tre incontri registrati). Il blocco esce con gli scontri a None: un dato
    assente non diventa uno zero."""
    SEL.reset_cache()
    h = SEL.hint("Spain", "Belgium")
    assert h is not None
    assert h["h2h_meetings"] is None and h["h2h_big_draws"] is None
    assert h["conceded"]["home"] is not None


def test_hint_nomi_sconosciuti_nessun_abbinamento_forzato() -> None:
    SEL.reset_cache()
    assert SEL.hint("Squadra Inventata", "Altra Inventata") is None


def test_lo_scanner_pubblica_il_blocco_nella_riga() -> None:
    """Come per `pressure_index`: il campo deve esistere davvero nel feed,
    altrimenti la parita' fra i due motori e' solo una buona intenzione.
    D5 (25/09): la fonte e' la SCHEDA DB della fixture (`SchedeFixture`),
    non piu' l'atlante per nome (`hint(home, away)` non e' piu' pubblicato)."""
    src = inspect.getsource(SV)
    assert 'payload["selection_hint"] = self.schede.hint(eid)' in src
    assert "_selezione.hint(home, away)" not in src


# ---------------------------------------------------------------------------
# il FILTRO nel motore vero
# ---------------------------------------------------------------------------
def _riga(hint: Optional[Dict[str, Any]], **kw: Any) -> Dict[str, Any]:
    """Riga di scan con il blocco della selezione aggiuntiva."""
    p = payload(**kw)
    p["selection_hint"] = hint
    return p


def _valuta(hint: Optional[Dict[str, Any]], *, acceso: bool = True,
            sub: str = "home", **kw: Any):
    par = dict(E.merge_params(None)["esatto"])
    par["requireSelection"] = acceso
    return E.evaluate_esatto(contesto(_riga(hint, **kw)), par, sub)


def _hint(incontri: Optional[int], alti: Optional[int],
          casa: Optional[float], fuori: Optional[float]) -> Dict[str, Any]:
    # D5 (25/09): la forma della scheda DB (`selezione.hint_da_scheda`):
    # `alti` = scontri diretti con 4+ gol
    return {"fonte": SEL.FONTE_DB, "fixture_id": 1, "h2h_meetings": incontri,
            "h2h_many_goals": alti, "conceded": {"home": casa, "away": fuori},
            "forze": None}


def _ck(ev, cid: str):
    return {c.id: c for c in ev.checks}.get(cid)


def test_spento_non_aggiunge_nessun_check() -> None:
    """Spento dal parametro il filtro non aggiunge niente. Q7 (25/09): prima
    era `test_spento_di_default_...` e pretendeva il default SPENTO; l'utente
    lo ha acceso («dove disponibile»), vedi il test sotto."""
    ev = _valuta(_hint(10, 9, 3.0, 3.0), acceso=False)
    assert _ck(ev, "h2hDifesa") is None
    assert ev.state == "signal"


def test_q7_acceso_di_default() -> None:
    assert E.DEFAULT_PARAMS["esatto"]["requireSelection"] is True
    assert E.merge_params(None)["esatto"]["requireSelection"] is True


def test_acceso_e_selezione_buona_il_filtro_TACE() -> None:
    """Zero 2-2/3-3 in dieci incontri e difesa avversaria da 0,90 gol: il
    filtro passa e il segnale resta."""
    ev = _valuta(_hint(10, 0, 3.0, 0.90), sub="home")
    ck = _ck(ev, "h2hDifesa")
    assert ck is not None and ck.ok is True
    assert ev.state == "signal"


def test_acceso_e_troppi_pareggi_alti_il_filtro_SCATTA() -> None:
    """D5: 7 su 10 partite da 4+ gol = 70 %, oltre il 58 % dichiarato:
    niente segnale."""
    ev = _valuta(_hint(10, 7, 3.0, 0.90))
    ck = _ck(ev, "h2hDifesa")
    assert ck is not None and ck.ok is False
    assert ev.state == "no"


def test_acceso_e_difesa_avversaria_debole_il_filtro_SCATTA() -> None:
    """Scontri diretti puliti ma la difesa che deve reggere subisce 1,80 gol
    a partita: sopra la media dichiarata, niente segnale."""
    ev = _valuta(_hint(10, 0, 3.0, 1.80))
    ck = _ck(ev, "h2hDifesa")
    assert ck is not None and ck.ok is False
    assert ev.state == "no"


def test_la_difesa_guardata_e_quella_AVVERSARIA_non_quella_bancata() -> None:
    """Lo stesso identico dato, i due lati bancabili: bancando la CASA conta
    la difesa di FUORI e viceversa. Se i lati fossero invertiti i due verdetti
    si scambierebbero."""
    h = _hint(10, 0, casa=0.80, fuori=1.90)
    assert _ck(_valuta(h, sub="home"), "h2hDifesa").ok is False   # avversaria = fuori
    assert _ck(_valuta(h, sub="away"), "h2hDifesa").ok is True    # avversaria = casa


def test_q7_dato_del_tutto_assente_non_blocca_e_lo_dichiara() -> None:
    """Q7 (utente 25/09): «dove disponibile». Prima di oggi questo test si
    chiamava `test_dato_assente_non_e_un_verdetto` e pretendeva «n/d» e nessun
    segnale; ora il dato assente NON blocca e il valore lo dice."""
    for h in (None, _hint(None, None, None, None)):
        ev = _valuta(h)
        ck = _ck(ev, "h2hDifesa")
        assert ck is not None and ck.ok is True
        assert ck.value == E.SELEZIONE_DATO_ASSENTE == "dato assente (non blocca)"
        assert ev.state == "signal"


def test_q7_manca_solo_lo_scontro_diretto_si_giudica_la_difesa() -> None:
    """Scontri diretti assenti: si applica la sola difesa avversaria."""
    buona = _ck(_valuta(_hint(None, None, 3.0, 0.90), sub="home"), "h2hDifesa")
    assert buona.ok is True
    assert buona.value == (E.SELEZIONE_H2H_ASSENTE + " " + E.MIDDOT
                           + " difesa avversaria 0,90 gol subiti")
    cattiva = _valuta(_hint(None, None, 3.0, 1.80), sub="home")
    assert _ck(cattiva, "h2hDifesa").ok is False and cattiva.state == "no"


def test_q7_manca_solo_la_difesa_si_giudicano_gli_scontri() -> None:
    """Difesa avversaria assente: si applica il solo scontro diretto."""
    buona = _ck(_valuta(_hint(10, 0, None, None)), "h2hDifesa")
    assert buona.ok is True
    assert buona.value == ("h2h: 10 partite, 0 con " + E.GEQ + "4 gol " + E.MIDDOT
                           + " " + E.SELEZIONE_DIFESA_ASSENTE)
    cattiva = _valuta(_hint(10, 7, None, None))
    assert _ck(cattiva, "h2hDifesa").ok is False and cattiva.state == "no"


def test_q7_zero_incontri_vale_come_dato_assente() -> None:
    """0 incontri non e' un campione: la parte non si giudica (non blocca).
    D5: il valore dice che il DB non ha scontri diretti."""
    ck = _ck(_valuta(_hint(0, 0, 3.0, 0.90)), "h2hDifesa")
    assert ck.ok is True and ck.value.startswith(E.SELEZIONE_H2H_NESSUNO)


def test_i_numeri_della_lettura_dichiarata_sono_quelli_del_referto() -> None:
    """Le due soglie NON sono nella SPEC: sono la lettura dichiarata il 16/09
    e vanno difese da un test, come le bande del manuale (CERT 14/09)."""
    par = E.DEFAULT_PARAMS["esatto"]
    # D5 (25/09): 4+ gol, doppio della norma (29,22% dell'atlante) -> 0,58
    assert par["h2hManyGoalsRateMax"] == 0.58
    assert par["h2hMinMeetings"] == 3
    assert "h2hBigDrawRateMax" not in par
    assert par["oppConcededMax"] == 1.37
    # il bordo: esattamente sulla soglia si passa (banda inclusiva come tutte
    # le altre del motore)
    assert _ck(_valuta(_hint(50, 29, 3.0, 1.37)), "h2hDifesa").ok is True   # 58 % esatto
    assert _ck(_valuta(_hint(50, 30, 3.0, 1.37)), "h2hDifesa").ok is False  # 60 %


def test_merge_params_difende_le_chiavi_nuove() -> None:
    """Un valore malformato dal DB torna al default, come per ogni altra
    chiave (merge difensivo)."""
    m = E.merge_params({"esatto": {"requireSelection": "si", "h2hManyGoalsRateMax": None,
                                   "h2hMinMeetings": "tanti",
                                   "oppConcededMax": "molto"}})["esatto"]
    # Q7 (25/09): il default e' ACCESO, un valore malformato torna li'
    assert m["requireSelection"] is True
    assert m["h2hManyGoalsRateMax"] == 0.58 and m["oppConcededMax"] == 1.37
    assert m["h2hMinMeetings"] == 3
    m2 = E.merge_params({"esatto": {"requireSelection": True,
                                    "h2hManyGoalsRateMax": 0.5,
                                    # D5: la chiave vecchia sul DB e' IGNORATA
                                    "h2hBigDrawRateMax": 0.01}})["esatto"]
    assert m2["requireSelection"] is True and m2["h2hManyGoalsRateMax"] == 0.5
    assert "h2hBigDrawRateMax" not in m2


# ---------------------------------------------------------------------------
# il CONTROLLO E10 sa diventare rosso
# ---------------------------------------------------------------------------
def _oss(ev, par: Dict[str, Any], p: Dict[str, Any]) -> CERT.Valutazione:
    params = {**E.merge_params(None), "esatto": par}
    return CERT.Valutazione(strategia="esatto", ctx=contesto(p), ev=ev,
                            par=par, params=params)


def _codici(oss) -> set:
    return {v.codice for v in CERT.verifica(oss)}


def _sollecitato(oss, codice: str) -> bool:
    sol: Dict[str, int] = {}
    CERT.verifica(oss, sol)
    return bool(sol.get(codice))


def test_e10_tace_quando_il_filtro_gira_davvero() -> None:
    par = dict(E.merge_params(None)["esatto"], requireSelection=True)
    p = _riga(_hint(10, 0, 3.0, 0.90))
    ev = E.evaluate_esatto(contesto(p), par, "home")
    oss = _oss(ev, par, p)
    assert _sollecitato(oss, "E10")
    assert "E10" not in _codici(oss)


def test_e10_scatta_se_il_check_sparisce() -> None:
    """Parametro acceso ma nessun check: e' il difetto che E10 nasce per
    prendere (la voce della SPEC senza nessuno che la guardi)."""
    par = dict(E.merge_params(None)["esatto"], requireSelection=True)
    p = _riga(_hint(10, 0, 3.0, 0.90))
    ev = E.evaluate_esatto(contesto(p), dict(par, requireSelection=False), "home")
    assert "E10" in _codici(_oss(ev, par, p))


def test_e10_scatta_sui_lati_invertiti() -> None:
    """Il difetto piu' insidioso: il filtro guarda la difesa della squadra
    BANCATA invece di quella avversaria. I numeri sono gli stessi, il verdetto
    no: E10 rifa' il conto e se ne accorge."""
    par = dict(E.merge_params(None)["esatto"], requireSelection=True)
    h = _hint(10, 0, casa=0.80, fuori=1.90)
    p = _riga(h)
    ev = E.evaluate_esatto(contesto(p), par, "home")
    # verdetto SBAGLIATO messo a mano al posto di quello vero (lati invertiti)
    storti = tuple(
        E.ConditionCheck(c.id, c.label, c.value, True) if c.id == "h2hDifesa" else c
        for c in ev.checks
    )
    ev_storto = E.VariantEvaluation(
        variant=ev.variant, state=ev.state, checks=storti, headline=ev.headline,
        side=ev.side, selection=ev.selection, entry_odds=ev.entry_odds,
        entry_size=ev.entry_size, market_type=ev.market_type,
        market_id=ev.market_id, selection_id=ev.selection_id, sub_id=ev.sub_id)
    assert "E10" in _codici(_oss(ev_storto, par, p))


def test_e10_scatta_se_un_dato_assente_blocca() -> None:
    """Q7 (25/09): il rovescio di prima. Prima E10 accusava un dato assente
    trasformato in verdetto; ora accusa un dato assente che BLOCCA (False),
    perche' l'utente ha chiesto «dove disponibile». (Era
    `test_e10_scatta_se_un_dato_assente_diventa_un_verdetto`.)"""
    par = dict(E.merge_params(None)["esatto"], requireSelection=True)
    p = _riga(_hint(None, None, None, None))
    ev = E.evaluate_esatto(contesto(p), par, "home")
    storti = tuple(
        E.ConditionCheck(c.id, c.label, c.value, False) if c.id == "h2hDifesa" else c
        for c in ev.checks
    )
    ev_storto = E.VariantEvaluation(
        variant=ev.variant, state=ev.state, checks=storti, headline=ev.headline,
        side=ev.side, selection=ev.selection, entry_odds=ev.entry_odds,
        entry_size=ev.entry_size, market_type=ev.market_type,
        market_id=ev.market_id, selection_id=ev.selection_id, sub_id=ev.sub_id)
    assert "E10" in _codici(_oss(ev_storto, par, p))


def test_e10_scatta_se_un_dato_assente_torna_n_d() -> None:
    """Q7: il vecchio comportamento (n/d -> nessun segnale) e' ora un difetto.
    Numeri scelti perche' il verdetto atteso sia False (7/10 da 4+ gol): cosi'
    a parlare e' SOLO la regola «n/d non e' ammesso», non il confronto col conto."""
    par = dict(E.merge_params(None)["esatto"], requireSelection=True)
    p = _riga(_hint(10, 7, None, None))
    ev = E.evaluate_esatto(contesto(p), par, "home")
    storti = tuple(
        E.ConditionCheck(c.id, c.label, "n/d", None) if c.id == "h2hDifesa" else c
        for c in ev.checks
    )
    ev_storto = E.VariantEvaluation(
        variant=ev.variant, state="nd", checks=storti, headline=None,
        side=ev.side, selection=ev.selection, entry_odds=ev.entry_odds,
        entry_size=ev.entry_size, market_type=ev.market_type,
        market_id=ev.market_id, selection_id=ev.selection_id, sub_id=ev.sub_id)
    assert "E10" in _codici(_oss(ev_storto, par, p))


def test_e10_parte_mancante_ignorata_ma_parte_presente_violata_scatta() -> None:
    """Scontri diretti assenti, difesa avversaria a 1,80: il verdetto giusto e'
    False. Un motore che ignorasse anche la parte presente (True) e' rosso."""
    par = dict(E.merge_params(None)["esatto"], requireSelection=True)
    p = _riga(_hint(None, None, 3.0, 1.80))
    ev = E.evaluate_esatto(contesto(p), par, "home")
    assert _ck(ev, "h2hDifesa").ok is False
    storti = tuple(
        E.ConditionCheck(c.id, c.label, c.value, True) if c.id == "h2hDifesa" else c
        for c in ev.checks
    )
    ev_storto = E.VariantEvaluation(
        variant=ev.variant, state=ev.state, checks=storti, headline=ev.headline,
        side=ev.side, selection=ev.selection, entry_odds=ev.entry_odds,
        entry_size=ev.entry_size, market_type=ev.market_type,
        market_id=ev.market_id, selection_id=ev.selection_id, sub_id=ev.sub_id)
    assert "E10" in _codici(_oss(ev_storto, par, p))


def test_e10_senza_il_parametro_non_ha_casi() -> None:
    """Spento il filtro, E10 non e' «sano»: e' «non lo so» (stessa disciplina
    di B10 ed E6). Q7: il default e' acceso, lo si spegne a mano."""
    par = dict(E.merge_params(None)["esatto"], requireSelection=False)
    p = _riga(None)
    ev = E.evaluate_esatto(contesto(p), par, "home")
    assert not _sollecitato(_oss(ev, par, p), "E10")
