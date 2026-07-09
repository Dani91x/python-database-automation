"""Audit scalper 09/07/2026 — test dei bug trovati nel confronto dossier↔codice.

Bug coperti (tutti money-critical, logica pura, no rete):
  1. _signal: filtro WoM INVERTITO (bloccava la conferma, lasciava passare
     la pressione contraria) — coerenza con micro_price/wom_imbalance.
  2. event_loss_cap / event_profit_target ignorati in mode="reversion"
     (il gate viveva solo nel ramo maker/join).
  3. bias_resolver: con quote di mercato presenti ma prob della direzione
     mancante, il bias veniva ATTIVATO senza verifica dell'edge.
  4. match_runner_roles: nomi con parola condivisa ("Real ...") mappati in
     modo ambiguo/ordine-dipendente.
  5. run_scalper_live: filtro stream in snake_case (= filtro vuoto →
     SUBSCRIPTION_LIMIT, bug gia' visto live 02/07 e fixato solo in session)
     + parsing --param che trasformava "false" in stringa truthy.
  6. scalper_session: min_size 150 nei VALIDATED_PARAMS mentre il valore
     validato in backtest (dossier §6.4) e' 300.
"""
from __future__ import annotations

import pytest

from Betfair.stream.scalper.scalper_bot import ScalperStrategy, _Slot


def _make_strategy(**params):
    return ScalperStrategy(market_filter={}, scalper_params=params)


class _FakeMarket:
    market_id = "1.234"

    def __init__(self):
        self.orders = []

    def place_order(self, order):
        self.orders.append(order)

    def cancel_order(self, order):  # pragma: no cover
        pass


class _FakeRunner:
    selection_id = 42


# ------------------------------------------------- 1. WoM del segnale reversion
def test_signal_back_bloccato_da_pressione_su():
    """Quote SALITE → fade BACK. WoM fortemente POSITIVA (size_back >>
    size_lay = micro-price verso il lay = spinta ANCORA SU) e' CONTRO la
    reversione → il segnale va bloccato."""
    s = _make_strategy(signal_ticks=1, max_signal_ticks=4, wom_block=0.9,
                       signal_window_ms=10_000)
    slot = _Slot()
    slot.history.append((95_000, 2.18))          # ref nella finestra
    assert s._signal(slot, 100_000, 2.22, 1000.0, 10.0) is None


def test_signal_back_permesso_con_wom_a_favore():
    """Stessa salita, ma WoM fortemente NEGATIVA (pressione in GIU', cioe'
    nella direzione della reversione attesa) → il BACK deve passare."""
    s = _make_strategy(signal_ticks=1, max_signal_ticks=4, wom_block=0.9,
                       signal_window_ms=10_000)
    slot = _Slot()
    slot.history.append((95_000, 2.18))
    assert s._signal(slot, 100_000, 2.22, 10.0, 1000.0) == "BACK"


def test_signal_lay_bloccato_da_pressione_giu():
    """Quote SCESE → fade LAY (attesa risalita). WoM fortemente NEGATIVA
    (spinta ancora in giu') e' contro → bloccare."""
    s = _make_strategy(signal_ticks=1, max_signal_ticks=4, wom_block=0.9,
                       signal_window_ms=10_000)
    slot = _Slot()
    slot.history.append((95_000, 2.26))
    assert s._signal(slot, 100_000, 2.22, 10.0, 1000.0) is None


def test_signal_lay_permesso_con_wom_a_favore():
    s = _make_strategy(signal_ticks=1, max_signal_ticks=4, wom_block=0.9,
                       signal_window_ms=10_000)
    slot = _Slot()
    slot.history.append((95_000, 2.26))
    assert s._signal(slot, 100_000, 2.22, 1000.0, 10.0) == "LAY"


# --------------------------------------- 2. loss cap anche in mode="reversion"
def _reversion_ready(s):
    """Slot con segnale reversion valido (BACK) su book 2.20/2.22."""
    slot = _Slot()
    slot.history.append((95_000, 2.18))
    return slot


def test_event_loss_cap_vale_anche_in_reversion():
    s = _make_strategy(mode="reversion", min_size=10.0, event_loss_cap=1.0,
                       signal_ticks=1, max_signal_ticks=4,
                       signal_window_ms=10_000)
    s.stats["pnl_locked"] = -1.5     # oltre il tetto di perdita evento
    slot = _reversion_ready(s)
    market = _FakeMarket()
    s._try_enter(market, None, _FakeRunner(), slot, 100_000,
                 2.20, 2.22, 500.0, 500.0, 2.22)
    assert market.orders == []       # nessun nuovo ingresso
    assert s.force_flat is True      # e chiusura totale richiesta


def test_event_target_ratchet_vale_anche_in_reversion():
    s = _make_strategy(mode="reversion", min_size=10.0,
                       event_profit_target=1.0, event_target_giveback=0.30,
                       signal_ticks=1, max_signal_ticks=4,
                       signal_window_ms=10_000)
    s.stats["pnl_locked"] = 0.50
    s.stats["pnl_peak"] = 1.20       # target raggiunto, giveback superato
    slot = _reversion_ready(s)
    market = _FakeMarket()
    s._try_enter(market, None, _FakeRunner(), slot, 100_000,
                 2.20, 2.22, 500.0, 500.0, 2.22)
    assert market.orders == []       # cricchetto: profitti protetti


def test_reversion_senza_cap_entra_normalmente():
    """Sanita': senza protezioni evento l'ingresso reversion resta operativo."""
    s = _make_strategy(mode="reversion", min_size=10.0,
                       signal_ticks=1, max_signal_ticks=4,
                       signal_window_ms=10_000)
    slot = _reversion_ready(s)
    market = _FakeMarket()
    s._try_enter(market, None, _FakeRunner(), slot, 100_000,
                 2.20, 2.22, 500.0, 500.0, 2.22)
    assert len(market.orders) == 1
    assert market.orders[0].side == "BACK"


# --------------------------------------------- 3./4. bias_resolver piu' sicuro
NAMES = {30: "Norway", 75104: "Ivory Coast", 58805: "The Draw"}
HOME, AWAY = "Ivory Coast", "Norway"


def _pred(ml, po):
    return {
        "league_id": 365,
        "model_predictions_json": {"targets": {"target_1x2": ml}},
        "db_json_analisi": {"markets": {"1x2": po}},
    }


def test_bias_neutro_se_prob_mercato_della_direzione_manca():
    """market_mid_probs presente ma senza la prob della direzione: l'edge
    NON e' verificabile → niente bias (come nel caso 'quote assenti')."""
    from Betfair.stream.scalper.bias_resolver import resolve_bias

    d = resolve_bias(
        _pred({"H": 0.55, "D": 0.25, "A": 0.20},
              {"H": 0.57, "D": 0.23, "A": 0.20}),
        NAMES, HOME, AWAY,
        {"H": None, "D": 0.28, "A": 0.24},   # prob di H mancante
    )
    assert d.bias == {}
    assert d.consensus is True


def test_mapping_prefer_match_esatto_su_parola_condivisa():
    """'Real Madrid' condivide 'real' con 'Real Sociedad': deve vincere il
    match ESATTO, qualunque sia l'ordine dei runner."""
    from Betfair.stream.scalper.bias_resolver import match_runner_roles

    names = {1: "Real Madrid", 2: "Real Sociedad", 3: "The Draw"}
    roles = match_runner_roles(names, "Real Sociedad", "Real Madrid")
    assert roles == {"H": 2, "A": 1, "D": 3}


def test_mapping_ambiguo_totale_ritorna_none():
    """Runner che matcha ENTRAMBE le squadre allo stesso livello → mapping
    inaffidabile → None (il chiamante resta neutro)."""
    from Betfair.stream.scalper.bias_resolver import match_runner_roles

    names = {1: "United City", 2: "Qualcosa Altro", 3: "The Draw"}
    roles = match_runner_roles(names, "United FC", "City FC")
    assert roles is None


def test_mapping_regressione_caso_reale_invariato():
    from Betfair.stream.scalper.bias_resolver import match_runner_roles

    assert match_runner_roles(NAMES, HOME, AWAY) == {
        "H": 75104, "A": 30, "D": 58805}


# ------------------------------------------------------- 5. run_scalper_live
def test_streaming_filter_in_formato_camel_case():
    """Il filtro passato a flumine live DEVE essere nel formato streaming
    (marketIds): con chiave sconosciuta il filtro e' vuoto e ci si abbona a
    tutto l'exchange (SUBSCRIPTION_LIMIT, visto live 02/07)."""
    from Betfair.stream.scalper.run_scalper_live import _streaming_filter

    f = _streaming_filter(["1.234", "1.235"])
    assert f.get("marketIds") == ["1.234", "1.235"]
    assert "market_ids" not in f


@pytest.mark.parametrize("raw,expected", [
    ("false", False), ("true", True), ("False", False),
    ("300", 300), ("0.5", 0.5), ("-1.5", -1.5), ("join", "join"),
])
def test_parse_param_value(raw, expected):
    from Betfair.stream.scalper.run_scalper_live import _parse_param_value

    assert _parse_param_value(raw) == expected


# --------------------------------------------------------- 6. scalper_session
def test_session_usa_il_min_size_validato_300():
    """Dossier §6.4: min_size 150 → -0.90 €, 300 → +0.77 € (12 match).
    Il default della sessione live deve essere quello VALIDATO (300)."""
    from Betfair.stream.scalper.scalper_session import VALIDATED_PARAMS

    assert VALIDATED_PARAMS["min_size"] == 300.0
