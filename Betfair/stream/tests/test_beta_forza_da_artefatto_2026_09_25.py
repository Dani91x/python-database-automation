"""FORZA_ETA / BETA_DEFAULT (atlante_v4.py) devono combaciare con l'artefatto
del banco (AUDIT_2026-09-25/validazione_hazard/risultati_validazione.json),
la stessa fonte citata nel commento sopra le due costanti.

Referto: AUDIT_2026-09-25/LIVE_MARKET_TYPES_E_BETA.md §2. Il valore committato
in precedenza (eta 0,035, beta 0,612/0,610) veniva da un artefatto che era in
realta' l'esito di una corsa --fumo (1 partita su 10: 439 partite) scritta per
errore sul percorso di output di default della corsa COMPLETA: eta e beta sono
accoppiati (beta e' la MLE del moltiplicatore forza CON quell'eta), quindi non
si puo' cambiare l'uno senza l'altro. Questo test legge l'artefatto committato
e falsifica una costante di produzione disallineata da esso.

Falsificazione: con FORZA_ETA=0.035 (il vecchio valore, sbagliato) il test
sull'eta diventa rosso; con BETA_DEFAULT={2:0.612,3:0.610} (i vecchi valori)
il test sul beta diventa rosso.
"""
from __future__ import annotations

import json
import os

from Betfair.stream.scalper import atlante_v4 as V4

_QUI = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_ARTEFATTO = os.path.join(_QUI, "AUDIT_2026-09-25", "validazione_hazard", "risultati_validazione.json")


def _carica_artefatto():
    with open(_ARTEFATTO, encoding="utf-8") as fh:
        return json.load(fh)


def _beta_a5(ris):
    for passo in ris["catena"]:
        if passo["passo"] == "A5":
            assert passo["entra"] is True   # la forza deve vincere in validazione (referto §3)
            beta = passo["esiti"][0]["info"]["beta"]
            return {int(k): float(v) for k, v in beta.items()}
    raise AssertionError("passo A5 non trovato nell'artefatto")


def test_artefatto_esiste_ed_e_la_corsa_completa():
    ris = _carica_artefatto()
    # corsa COMPLETA (non --fumo): stessi n_partite/n_stati del referto
    # VALIDAZIONE_HAZARD.md §3 ("4.396 partite, 420.150 stati")
    assert ris["metriche"]["n_partite"] == 4396
    assert ris["metriche"]["n_stati"] == 420150


def test_forza_eta_allineata_all_artefatto():
    ris = _carica_artefatto()
    scelta = ris["forza"]["scelta"]
    assert V4.FORZA_ETA == scelta["eta"]
    assert V4.FORZA_RIENTRO == scelta["rientro"]


def test_beta_default_allineato_all_artefatto():
    ris = _carica_artefatto()
    beta_banco = _beta_a5(ris)
    for k, v in V4.BETA_DEFAULT.items():
        assert abs(v - beta_banco[k]) < 5e-4, (k, v, beta_banco[k])


def test_falsificazione_eta_vecchia_non_combacia():
    ris = _carica_artefatto()
    scelta = ris["forza"]["scelta"]
    eta_vecchia = 0.035   # valore committato prima della correzione 25/09
    assert eta_vecchia != scelta["eta"]


def test_falsificazione_beta_vecchio_non_combacia():
    ris = _carica_artefatto()
    beta_banco = _beta_a5(ris)
    beta_vecchio = {2: 0.612, 3: 0.610}   # valori committati prima della correzione 25/09
    scarti = [abs(beta_vecchio[k] - beta_banco[k]) for k in beta_vecchio]
    assert max(scarti) > 5e-4
