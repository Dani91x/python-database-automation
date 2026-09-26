"""Atlante a domanda, reperti del test e2e del 26/09/2026.

O-1: la coda delle leghe nuove era ordinata per il PRIMO calcio d'inizio della
finestra (fino a 36 h indietro): una lega che ha giocato ieri sera passava davanti
a quella in gioco adesso (alle 14:39Z solo 42 leghe in gioco su 157 avevano il v4).
Ora: in gioco adesso -> entro 2 h -> il resto.

O-3: il file live si scriveva 2 volte per ciclo con lo stesso ``generated_at``.
Ora una sola scrittura a fine ciclo.

Finti: quelli di ``test_atlante_a_domanda_2026_09_25`` (DBFinto PostgREST con le
colonne vere di ``fixture_predictions``/``api_coverage_by_season``/``matches``/
``match_events``).
"""
from __future__ import annotations

from typing import Any, Dict, List

from Betfair.stream.scalper import atlante_a_domanda as AD
from Betfair.stream.tests.test_atlante_a_domanda_2026_09_25 import (  # noqa: F401 (cartella = fixture)
    T0, DBFinto, _cov, _db_lega_900, _fp, _leggi, _motore, _storico, cartella,
)


def _tab(leghe_ko: Dict[int, List[float]]) -> Dict[str, List[Dict[str, Any]]]:
    tab: Dict[str, List[Dict[str, Any]]] = {"fixture_predictions": [], "api_coverage_by_season": [],
                                            "matches": [], "match_events": []}
    fid = 7500
    for i, (lid, kos) in enumerate(leghe_ko.items()):
        for ko in kos:
            tab["fixture_predictions"].append(_fp(fid, lid, ko))
            fid += 1
        tab["api_coverage_by_season"].append(_cov(lid, 2025, True))
        st = _storico(lid, [2025], 2, 20000 * (i + 1), 200000 * (i + 1))
        tab["matches"] += st["matches"]
        tab["match_events"] += st["match_events"]
    return tab


def test_fascia_priorita():
    fine = 150 * 60.0
    assert AD.fascia_priorita(T0 - 1800, T0, fine) == 0          # iniziata 30' fa: in gioco
    assert AD.fascia_priorita(T0, T0, fine) == 0                 # calcio d'inizio adesso
    assert AD.fascia_priorita(T0 - fine, T0, fine) == 2          # finita (150')
    assert AD.fascia_priorita(T0 + 3600, T0, fine) == 1          # fra 1 h
    assert AD.fascia_priorita(T0 + 7200, T0, fine) == 1          # fra 2 h esatte
    assert AD.fascia_priorita(T0 + 7201, T0, fine) == 2
    assert AD.fascia_priorita(T0 - 20 * 3600, T0, fine) == 2     # ieri sera


def test_coda_in_gioco_poi_prossime_2h_poi_il_resto(cartella):
    db = DBFinto(_tab({
        910: [T0 - 20 * 3600],              # ha giocato ieri sera (primo ko della finestra)
        911: [T0 + 10 * 3600],              # fra 10 h
        912: [T0 + 3600],                   # fra 1 h
        913: [T0 - 30 * 3600, T0 - 1800],   # ieri E in gioco adesso: conta la fascia migliore
        914: [T0 - 1200],                   # in gioco da 20'
    }))
    ora = [T0]
    m = _motore(db, cartella, ora, tetto_ciclo=1, tetto_ora=40)
    r = m.ciclo()
    # in gioco prima (dentro la fascia chi ha il primo ko prima: 913), poi 914
    assert list(r["preparate"]) == ["913"]
    assert r["in_preparazione"] == ["914", "912", "910", "911"]
    assert _leggi(cartella["live"])["meta"]["leghe_in_preparazione"] == [914, 912, 910, 911]


def test_una_sola_scrittura_del_live_per_ciclo(cartella, monkeypatch):
    scritture: List[str] = []
    vero = AD.G.scrivi_json_atomico

    def conta(path: str, obj: Any) -> None:
        if path == cartella["live"]:
            scritture.append(obj["meta"]["generated_at"])
        vero(path, obj)
    monkeypatch.setattr(AD.G, "scrivi_json_atomico", conta)
    db = DBFinto(_db_lega_900())
    ora = [T0]
    m = _motore(db, cartella, ora)
    r = m.ciclo()
    assert r["preparate"] == {"900": "calcolata"}
    assert len(scritture) == 1                                    # era 2, stesso generated_at
    # ciclo senza novita': nessuna scrittura
    ora[0] = T0 + 600
    m.ciclo()
    assert len(scritture) == 1


def test_leghe_in_preparazione_dichiarate_anche_se_il_calcolo_fallisce(cartella, monkeypatch):
    db = DBFinto(_db_lega_900())
    ora = [T0]
    m = _motore(db, cartella, ora)
    m.ciclo()
    db.tabelle["fixture_predictions"].append(_fp(7999, 920, T0 + 1800))

    def rotta(lid: str, adesso: float) -> str:
        raise RuntimeError("rete giu'")
    monkeypatch.setattr(m, "prepara_lega", rotta)
    ora[0] = T0 + 600
    r = m.ciclo()
    assert r["preparate"]["920"].startswith("errore")
    assert _leggi(cartella["live"])["meta"]["leghe_in_preparazione"] == [920]
