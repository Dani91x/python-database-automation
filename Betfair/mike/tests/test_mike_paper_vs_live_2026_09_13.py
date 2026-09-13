"""PAPER E SOLDI VERI NON SI TOCCANO MAI. Certificazione del 13/09/2026.

Nessuna rete, nessun DB. File ASCII-only (console Windows cp1252).

Prima di questa suite non esisteva UN SOLO test che dicesse «un trade in paper
non arriva mai a ``place_order_live``» sul percorso di Mike: la certificazione
cross-mode c'era solo per Omega. Eppure Mike e' l'unico dei tre che piazza in
REST diretto, quindi l'unico non coperto dagli interruttori della coda.

Quello che viene certificato qui:
  * l'interruttore fisico ``MIKE_LIVE_ENABLED``, spento di default;
  * che in paper nessuna funzione che tocca Betfair venga mai chiamata;
  * che il rischio, il P&L bloccato e lo stop giornaliero guardino UNA
    modalita' sola;
  * che le partite armate nella modalita' opposta vengano DICHIARATE.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

import pytest

from Betfair.mike import engine as E
from Betfair.mike import service as S


# ---------------------------------------------------------------------------
# L'interruttore fisico
# ---------------------------------------------------------------------------
class TestInterruttoreLive:
    """L'ultima barriera prima di Betfair, e l'unica che non dipende da un
    valore sul database."""

    def test_di_default_e_spento(self, monkeypatch):
        monkeypatch.delenv("MIKE_LIVE_ENABLED", raising=False)
        assert S.mike_live_abilitato() is False

    def test_si_accende_solo_a_mano(self, monkeypatch):
        for acceso in ("1", "true", "yes", "on", "TRUE"):
            monkeypatch.setenv("MIKE_LIVE_ENABLED", acceso)
            assert S.mike_live_abilitato() is True, acceso
        for spento in ("0", "false", "no", "off", "", "   ", "forse"):
            monkeypatch.setenv("MIKE_LIVE_ENABLED", spento)
            assert S.mike_live_abilitato() is False, repr(spento)

    def test_e_riletto_a_ogni_chiamata(self, monkeypatch):
        """Spegnerlo deve avere effetto SUBITO, senza riavviare niente."""
        monkeypatch.setenv("MIKE_LIVE_ENABLED", "1")
        assert S.mike_live_abilitato() is True
        monkeypatch.setenv("MIKE_LIVE_ENABLED", "0")
        assert S.mike_live_abilitato() is False

    def test_col_kill_switch_spento_NESSUN_ordine_reale_parte(self, monkeypatch):
        monkeypatch.setenv("MIKE_LIVE_ENABLED", "0")
        chiamate: List[str] = []

        class FintoOmega:
            CUSTOMER_STRATEGY_REF = "mike"

            @staticmethod
            def place_order_live(**kw):
                chiamate.append("place_order_live")

            @staticmethod
            def place_submin_live(**kw):
                chiamate.append("place_submin_live")

        monkeypatch.setitem(__import__("sys").modules, "Betfair.omega.omega_market", FintoOmega)
        for fn in (S._RealMarket.place_order_live, S._RealMarket.place_submin_live):
            with pytest.raises(S._LiveNonAbilitato) as ex:
                fn(market_id="1.1", selection_id=1, price=2.0, size=1.0, event_id="E1", side="back")
            assert "MIKE_LIVE_ENABLED" in str(ex.value)
        assert chiamate == [], "nessuna chiamata deve arrivare a Betfair"

    def test_l_errore_dice_che_l_ordine_NON_e_partito(self, monkeypatch):
        """La differenza fra «rifiutato dall'exchange» e «mai inviato» e' tutto:
        nel primo caso si riconcilia, nel secondo non c'e' niente da cercare."""
        monkeypatch.setenv("MIKE_LIVE_ENABLED", "0")
        with pytest.raises(S._LiveNonAbilitato) as ex:
            S._pretendi_live_abilitato("prova")
        msg = str(ex.value)
        assert "nessun ordine reale" in msg
        assert ".env" in msg


# ---------------------------------------------------------------------------
# Il rischio e il P&L guardano UNA modalita' sola
# ---------------------------------------------------------------------------
def _evento(event_id: str, mode: str, stake: float, prezzo: float = 1.50,
            state: str = "LIVE_UNCOVERED", chiuso: bool = False,
            placed_at: float = 1_800_000_000.0) -> Dict[str, Any]:
    gambe = [{"role": "under_entry", "market": E.MARKET_OU35, "selection": E.SEL_UNDER,
              "side": "back", "price": prezzo, "size": stake, "matched": stake,
              "avg_price": prezzo, "ref": f"{event_id}-e", "status": "open",
              "placed_at": placed_at}]
    if chiuso:
        gambe.append({"role": "under_green", "market": E.MARKET_OU35, "selection": E.SEL_UNDER,
                      "side": "lay", "price": prezzo - 0.02, "size": stake * 1.014,
                      "matched": stake * 1.014, "avg_price": prezzo - 0.02,
                      "ref": f"{event_id}-g", "status": "open", "placed_at": placed_at})
    return {"event_id": event_id, "mode": mode, "state": state, "positions": gambe}


class TestRischioPerModalita:
    """Il rischio di una partita in paper non e' rischio, e sommarlo a quello
    vero falsa il cap e lo stop giornaliero."""

    def setup_method(self):
        self.tracked = {
            "P1": _evento("P1", "paper", 10.0),
            "P2": _evento("P2", "paper", 20.0),
            "L1": _evento("L1", "live", 30.0),
        }
        self.params = {"commission_pct": 5.0}

    def test_la_liability_conta_solo_la_modalita_chiesta(self):
        solo_paper = S._open_liability(self.tracked, self.params, "paper")
        solo_live = S._open_liability(self.tracked, self.params, "live")
        tutte = S._open_liability(self.tracked, self.params)
        assert solo_paper == pytest.approx(30.0, abs=0.01)      # 10 + 20
        assert solo_live == pytest.approx(30.0, abs=0.01)       # solo la live
        assert tutte == pytest.approx(60.0, abs=0.01)
        assert solo_live != tutte, "senza filtro il rischio vero era gonfiato dal simulato"

    def test_il_bloccato_conta_solo_la_modalita_chiesta(self):
        tracked = {
            "P1": _evento("P1", "paper", 10.0, chiuso=True),
            "L1": _evento("L1", "live", 10.0, chiuso=True),
        }
        paper = S._locked_open_pnl(tracked, self.params, None, "paper")
        live = S._locked_open_pnl(tracked, self.params, None, "live")
        insieme = S._locked_open_pnl(tracked, self.params, None)
        assert paper != 0.0 and live != 0.0
        assert insieme == pytest.approx(paper + live, abs=0.01)
        assert live != insieme, "lo stop del live non deve vedere il bloccato del paper"

    def test_le_partite_della_modalita_opposta_vengono_dichiarate(self):
        """Il caso piu' pericoloso: il toggle dice paper e tre partite spendono."""
        divergenti = S.partite_di_modalita_diversa(self.tracked, "paper")
        assert divergenti == ["L1"]
        assert S.partite_di_modalita_diversa(self.tracked, "live") == ["P1", "P2"]

    def test_una_partita_gia_regolata_non_e_piu_un_allarme(self):
        tracked = dict(self.tracked)
        tracked["L1"] = _evento("L1", "live", 30.0, state="SETTLED")
        assert S.partite_di_modalita_diversa(tracked, "paper") == []

    def test_senza_mode_dichiarato_una_partita_e_paper(self):
        """Default prudente: nel dubbio e' simulata, mai soldi veri."""
        tracked = {"X": {"event_id": "X", "state": "PRE_OPEN", "positions": []}}
        assert S.partite_di_modalita_diversa(tracked, "paper") == []
        assert S.partite_di_modalita_diversa(tracked, "live") == ["X"]


# ---------------------------------------------------------------------------
# La modalita' della PARTITA e' quella che comanda
# ---------------------------------------------------------------------------
class TestModalitaDellaPartita:
    def test_una_partita_live_resta_live_anche_a_control_in_paper(self):
        """Il `mode` si congela all'arming: e' il motivo per cui serve l'allarme.
        Qui si certifica il comportamento, cosi' nessuno lo cambia per sbaglio
        credendo di semplificare."""
        p = S._live_exit_override({"pre_exit_mode": "resting"}, "live")
        assert p["pre_exit_mode"] == "taker", "in live non esiste la lay simulata"
        p2 = S._live_exit_override({"pre_exit_mode": "resting"}, "paper")
        assert p2["pre_exit_mode"] == "resting"

    def test_in_live_una_lay_appoggiata_non_e_mai_simulata(self):
        """Un fill simulato in live e' un profitto che non esiste."""
        lay = E.Leg(role="ko_green", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                    side="lay", price=1.48, size=10.14, ref="k1")
        assert S._is_resting_leg(lay, {"pre_exit_mode": "resting"}) is True
        assert S._is_resting_leg(lay, {"pre_exit_mode": "taker"}) is False


# ---------------------------------------------------------------------------
# L'esecuzione: whitelist e percorsi
# ---------------------------------------------------------------------------
class TestEsecuzione:
    def test_il_mode_e_validato_prima_di_qualunque_rete(self):
        from Betfair.safe_strategy import execution as X

        class MercatoSpia:
            def __init__(self):
                self.chiamate: List[str] = []

            def place_order_live(self, **kw):
                self.chiamate.append("live")

            def place_submin_live(self, **kw):
                self.chiamate.append("submin")

        mk = MercatoSpia()
        for cattivo in ("LIVE", "Paper", "", "prod", None):
            out = X.place(db=None, market=mk, mode=cattivo, event_id="1.1", market_id="m1",
                          selection_id=7, side="back", price=3.0, size=5.0,
                          client_ref="mike-t1", trade_id=1, now=None, params={})
            assert out.status == "error", cattivo
            assert "mode_non_valido" in out.fill_note
        assert mk.chiamate == [], "una modalita' non valida non deve toccare la rete"

    def test_l_azione_accodata_e_su_whitelist(self):
        """Nessuna azione a sorpresa puo' finire sulla coda degli ordini."""
        from Betfair.safe_strategy import execution as X

        class DbSpia:
            def update_trade(self, *a, **k):
                return None

            def enqueue_live_order(self, payload):
                raise AssertionError("non deve arrivare qui")

        for azione in ("cashout_all", "greenup", "cancel", "", "place_tutto"):
            rid = X.enqueue_place(db=DbSpia(), trade_id=1, client_ref="r", event_id="e",
                                  market_id="m", selection_id=1, side="back", price=2.0,
                                  size=1.0, base_meta=None, now=None, mode="paper",
                                  action=azione)
            assert rid is None, azione


def test_il_kill_switch_non_riguarda_il_paper(monkeypatch):
    """La simulazione non passa dalle funzioni che toccano Betfair: spegnere
    l'interruttore non deve impedire di lavorare in paper."""
    monkeypatch.setenv("MIKE_LIVE_ENABLED", "0")
    from Betfair.safe_strategy import execution as X

    class Mercato:
        def place_order_live(self, **kw):
            raise AssertionError("il paper non deve arrivare qui")

    out = X.place(db=None, market=Mercato(), mode="paper", event_id="1.1", market_id="m1",
                  selection_id=7, side="back", price=3.0, size=5.0, best_size=100.0,
                  client_ref="mike-t1", trade_id=1, now=None, params={})
    assert out.status in ("open", "error")
    assert "MIKE_LIVE_ENABLED" not in (out.fill_note or "")
