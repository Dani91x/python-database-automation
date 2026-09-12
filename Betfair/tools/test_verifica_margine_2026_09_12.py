"""Test della logica PURA di ``verifica_margine_2026_09_12``.

Lo strumento decide se il modello di Omega batte il mercato. La cosa che DEVE
fare bene non e' produrre un numero: e' dichiarare quando i dati non bastano.
Il 12/09, su 25 aperture regolate, ZERO avevano perso: in quella situazione il
Brier premia automaticamente chi prevede la probabilita' piu' bassa, e un
"vincitore" sarebbe un artefatto.
"""
from __future__ import annotations

import math

import pytest

from Betfair.tools import verifica_margine_2026_09_12 as M


def _ap(p_model: float, p_mkt: float, esito: float, prezzo: float = 60.0,
        stake: float = 2.0, p_emp: float | None = None) -> M.Apertura:
    return M.Apertura(p_model, p_mkt, p_emp, esito, stake * (prezzo - 1.0), stake, prezzo)


class TestCaricamento:
    """Si contano solo le APERTURE regolate che portano il blocco del modello."""

    class _DB:
        def __init__(self, rows): self.rows = rows
        def table(self, _n): return self
        def select(self, _c): return self
        def in_(self, _c, _v): return self
        def execute(self): return type("R", (), {"data": self.rows})()

    def _carica(self, rows):
        return M.carica(self._DB(rows))

    def test_una_riga_completa_viene_letta(self) -> None:
        dati = self._carica([{
            "id": 1, "price": 60.0, "size": 2.0, "status": "won", "closes_trade_id": None,
            "meta": {"model": {"p_model": 0.008, "p_implied": 0.0167, "empirical": 0.007}},
        }])
        assert len(dati) == 1
        d = dati[0]
        assert d.p_model == 0.008 and d.p_mkt == 0.0167 and d.p_emp == 0.007
        assert d.esito == 0.0 and d.liability == pytest.approx(118.0)

    def test_lay_perso_significa_che_il_bancato_e_uscito(self) -> None:
        dati = self._carica([{
            "id": 1, "price": 60.0, "size": 2.0, "status": "lost", "closes_trade_id": None,
            "meta": {"model": {"p_model": 0.008, "p_implied": 0.0167}},
        }])
        assert dati[0].esito == 1.0

    def test_si_scartano_chiusure_righe_senza_modello_e_prezzi_impossibili(self) -> None:
        base = {"price": 60.0, "size": 2.0, "status": "won",
                "meta": {"model": {"p_model": 0.008, "p_implied": 0.0167}}}
        righe = [
            {**base, "id": 1, "closes_trade_id": 99},                      # e' una chiusura
            {**base, "id": 2, "closes_trade_id": None, "meta": {}},        # niente modello
            {**base, "id": 3, "closes_trade_id": None,
             "meta": {"model": {"p_model": 0.008}}},                       # manca il mercato
            {**base, "id": 4, "closes_trade_id": None, "price": 1.0},      # quota impossibile
            {**base, "id": 5, "closes_trade_id": None, "price": None},     # quota assente
        ]
        assert self._carica(righe) == []


class TestCalibrazioneDichiaraQuandoNonSaRispondere:
    """Il comportamento che conta: con zero eventi NON si nomina un vincitore."""

    def test_senza_eventi_positivi_lo_dice_e_si_ferma(self, capsys) -> None:
        dati = [_ap(0.008, 0.0167, 0.0) for _ in range(25)]
        M.sezione_calibrazione(dati)
        out = capsys.readouterr().out
        assert "NON e' utilizzabile" in out
        # la parola "Brier" compare nella SPIEGAZIONE: quello che non deve
        # comparire e' la classifica, cioe' i punteggi e un vincitore
        assert "log-loss" not in out, "col campione vuoto non si stampa la tabella"
        assert "calibra meglio" not in out, "col campione vuoto non si nomina un vincitore"

    def test_con_eventi_positivi_confronta_e_avvisa_se_sono_pochi(self, capsys) -> None:
        # il modello e' vicino al vero (10%), il mercato lo sovrastima molto (30%)
        dati = [_ap(0.10, 0.30, 1.0) for _ in range(2)]
        dati += [_ap(0.10, 0.30, 0.0) for _ in range(18)]
        M.sezione_calibrazione(dati)
        out = capsys.readouterr().out
        assert "calibra meglio il MODELLO" in out
        assert "ATTENZIONE" in out and "indicativo" in out

    def test_il_brier_premia_chi_ci_prende_non_chi_e_prudente(self) -> None:
        """Guardia sulla metrica: col 20% di eventi il forecaster onesto vince."""
        dati = [_ap(0.20, 0.02, 1.0) for _ in range(20)]
        dati += [_ap(0.20, 0.02, 0.0) for _ in range(80)]
        assert M._brier(dati, "p_model") < M._brier(dati, "p_mkt")
        assert M._logloss(dati, "p_model") < M._logloss(dati, "p_mkt")


class TestScommesseNecessarie:
    def test_nessun_margine_nessun_numero(self) -> None:
        assert M._scommesse_necessarie(0.0, 10.0) is None
        assert M._scommesse_necessarie(-1.0, 10.0) is None

    def test_formula_dell_intervallo_al_95(self) -> None:
        assert M._scommesse_necessarie(1.0, 10.0) == math.ceil((1.96 * 10) ** 2)

    def test_piu_rumore_piu_scommesse_piu_margine_meno_scommesse(self) -> None:
        base = M._scommesse_necessarie(0.5, 10.0)
        assert M._scommesse_necessarie(0.5, 20.0) > base      # varianza doppia
        assert M._scommesse_necessarie(1.0, 10.0) < base      # margine doppio


class TestLaQuotaAltaCostaSoloVarianza:
    """Il punto del terzo blocco: a parita' di margine RELATIVO il valore atteso
    per scommessa non cambia con la quota, ma le scommesse necessarie esplodono."""

    @staticmethod
    def _caso(quota: float, margine_rel: float = 0.315, stake: float = 2.0):
        p_mkt = 1.0 / quota
        p_mod = p_mkt * (1 - margine_rel)
        liab = stake * (quota - 1)
        ev = (1 - p_mod) * stake - p_mod * liab
        sd = math.sqrt(p_mod * (1 - p_mod)) * (liab + stake)
        return ev, M._scommesse_necessarie(ev, sd)

    def test_il_valore_atteso_non_dipende_dalla_quota(self) -> None:
        evs = [self._caso(q)[0] for q in (5, 10, 20, 30, 60, 110)]
        assert max(evs) - min(evs) < 1e-9, "l'EV per scommessa deve restare identico"

    def test_le_scommesse_necessarie_crescono_con_la_quota(self) -> None:
        n = [self._caso(q)[1] for q in (5, 10, 20, 30, 60, 110)]
        assert n == sorted(n), "bancare piu' alto puo' solo richiedere piu' campione"
        assert n[-1] > 10 * n[0], "da quota 5 a 110 il campione cresce di oltre 10 volte"

    def test_bancare_a_dieci_invece_che_a_centodieci_costa_molto_meno_campione(self) -> None:
        _, n10 = self._caso(10)
        _, n110 = self._caso(110)
        assert n110 / n10 > 10
