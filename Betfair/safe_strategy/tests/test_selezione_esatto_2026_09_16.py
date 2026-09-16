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
    altrimenti la parita' fra i due motori e' solo una buona intenzione."""
    src = inspect.getsource(SV)
    assert 'payload["selection_hint"] = _selezione.hint(home, away)' in src


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
    return {"fonte": SEL.FONTE, "h2h_meetings": incontri, "h2h_big_draws": alti,
            "conceded": {"home": casa, "away": fuori}}


def _ck(ev, cid: str):
    return {c.id: c for c in ev.checks}.get(cid)


def test_spento_di_default_non_aggiunge_nessun_check() -> None:
    """Il default non cambia una virgola del comportamento di prima."""
    assert E.DEFAULT_PARAMS["esatto"]["requireSelection"] is False
    ev = _valuta(_hint(10, 9, 3.0, 3.0), acceso=False)
    assert _ck(ev, "h2hDifesa") is None
    assert ev.state == "signal"


def test_acceso_e_selezione_buona_il_filtro_TACE() -> None:
    """Zero 2-2/3-3 in dieci incontri e difesa avversaria da 0,90 gol: il
    filtro passa e il segnale resta."""
    ev = _valuta(_hint(10, 0, 3.0, 0.90), sub="home")
    ck = _ck(ev, "h2hDifesa")
    assert ck is not None and ck.ok is True
    assert ev.state == "signal"


def test_acceso_e_troppi_pareggi_alti_il_filtro_SCATTA() -> None:
    """3 su 10 = 30 %, oltre il 12 % dichiarato: niente segnale."""
    ev = _valuta(_hint(10, 3, 3.0, 0.90))
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


def test_dato_assente_non_e_un_verdetto() -> None:
    """Nessun blocco, o scontri diretti mancanti: «n/d» e nessun segnale —
    la stessa regola di `control_check` e del resto del motore."""
    for h in (None, _hint(None, None, 0.9, 0.9), _hint(10, 0, None, None)):
        ev = _valuta(h)
        ck = _ck(ev, "h2hDifesa")
        assert ck is not None and ck.ok is None and ck.value == "n/d"
        assert ev.state == "nd"


def test_i_numeri_della_lettura_dichiarata_sono_quelli_del_referto() -> None:
    """Le due soglie NON sono nella SPEC: sono la lettura dichiarata il 16/09
    e vanno difese da un test, come le bande del manuale (CERT 14/09)."""
    par = E.DEFAULT_PARAMS["esatto"]
    assert par["h2hBigDrawRateMax"] == 0.12
    assert par["oppConcededMax"] == 1.37
    # il bordo: esattamente sulla soglia si passa (banda inclusiva come tutte
    # le altre del motore)
    assert _ck(_valuta(_hint(25, 3, 3.0, 1.37)), "h2hDifesa").ok is True   # 12 % esatto
    assert _ck(_valuta(_hint(25, 4, 3.0, 1.37)), "h2hDifesa").ok is False  # 16 %


def test_merge_params_difende_le_chiavi_nuove() -> None:
    """Un valore malformato dal DB torna al default, come per ogni altra
    chiave (merge difensivo)."""
    m = E.merge_params({"esatto": {"requireSelection": "si", "h2hBigDrawRateMax": None,
                                   "oppConcededMax": "molto"}})["esatto"]
    assert m["requireSelection"] is False
    assert m["h2hBigDrawRateMax"] == 0.12 and m["oppConcededMax"] == 1.37
    m2 = E.merge_params({"esatto": {"requireSelection": True,
                                    "h2hBigDrawRateMax": 0.5}})["esatto"]
    assert m2["requireSelection"] is True and m2["h2hBigDrawRateMax"] == 0.5


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


def test_e10_scatta_se_un_dato_assente_diventa_un_verdetto() -> None:
    par = dict(E.merge_params(None)["esatto"], requireSelection=True)
    p = _riga(_hint(None, None, 0.9, 0.9))
    ev = E.evaluate_esatto(contesto(p), par, "home")
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
    di B10 ed E6)."""
    par = dict(E.merge_params(None)["esatto"])
    p = _riga(None)
    ev = E.evaluate_esatto(contesto(p), par, "home")
    assert not _sollecitato(_oss(ev, par, p), "E10")
