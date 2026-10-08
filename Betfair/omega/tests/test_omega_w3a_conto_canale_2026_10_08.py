"""08/10 (W3a) - OMEGA SA SUBITO DEGLI ORDINI ESTERNI (canale del conto).

Ordine dell'utente (08/10): «I BOT DEVONO ESSERE AGGIORNATI NEL MINOR TEMPO
POSSIBILE SULLE OPERAZIONI FATTE DA APP O DA SITO [...] QUANDO INTERVENGO IO [...]
I BOT LO SANNO E NON FANNO ALTRO».

Prima: Omega rileggeva la posizione di conto SOLO via REST ogni
``conto_every_s`` (120 s); in paper non vedeva niente; una riduzione parziale
dall'esterno si dichiarava e basta. Ora, con lo STESSO meccanismo di Mike
(``esiti_ordini_canale.SorveglianzaConto``):
  1. una fotografia NUOVA dello stream ordini (runner LIVE) che dice la
     posizione non piu' intera fa rileggere la REST nello STESSO giro, fuori
     cadenza, e decide la REST (mai il solo canale in live);
  2. la riduzione parziale confermata ferma il bot (``come='ridotta'``);
  3. in PAPER la fotografia del blotter del runner paper decide (ordine
     manuale dell'app), senza REST; paper e live mai mescolati;
  4. la SVEGLIA: la dormita del ciclo si interrompe (pavimento 1 s);
  5. senza canale: identico a prima.

I finti parlano come il vero: la fotografia LIVE esce dalla cache VERA dello
stream ordini (``OrderBookCache``) e dal produttore VERO del runner
(``pubblica_conto_da_evento``), serializzata come ``local_channel`` e incassata
dal client VERO; la REST e' ``MercatoFinto`` del 16/09 (chiavi di
``omega_market._riga_corrente``). ASCII-only.
"""
from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_chiuso_dall_utente_2026_09_16 import (
    ADESSO, MKT, REF_BOT, SEL, DbFinto, MercatoFinto, _lay_del_bot, _params, _riga_rest)
from Betfair.stream import esiti_ordini_canale as EO

BOT_BET = "100000000001"


@pytest.fixture(autouse=True)
def _pulito():
    S.svuota_le_cache()
    S._CONTO.installa(None)
    yield
    S.svuota_le_cache()
    S._CONTO.installa(None)


def _client() -> EO.ClientEsiti:
    memoria = EO.MemoriaConto()
    S._CONTO.installa(memoria)
    return EO.ClientEsiti(memoria, topic=EO.TOPIC_CONTO_TUTTI, porta_ws=1)


def _uo(bet_id: str, *, side: str, sm: float, rfo: Any) -> Dict[str, Any]:
    return {"id": bet_id, "p": 300.0, "s": sm, "side": side, "status": "EC", "pt": "L",
            "ot": "L", "pd": 1_700_000_000_000, "md": 1_700_000_000_500, "avp": 300.0,
            "sm": sm, "sr": 0.0, "sl": 0.0, "sc": 0.0, "sv": 0.0, "rfo": rfo, "rfs": None}


UO_BOT = _uo(BOT_BET, side="L", sm=5.26, rfo=REF_BOT)


def _dal_runner(client: EO.ClientEsiti, uo: List[Dict[str, Any]], ms: int) -> None:
    """Il runner LIVE: stream ordini (cache VERA) -> produttore VERO -> canale."""
    from betfairlightweight.streaming.cache import OrderBookCache

    cache = OrderBookCache(MKT, ms, False)
    cache.update_cache({"id": MKT, "orc": [{"id": SEL, "uo": uo}]}, ms)
    co = cache.create_resource(0)
    co.client = SimpleNamespace(paper_trade=False)
    testi: List[str] = []
    assert EO.pubblica_conto_da_evento(
        SimpleNamespace(event=[co]),
        lambda t, d: testi.append(json.dumps({"t": t, "d": d}, default=str)),
        adesso_ms=ms) == 1
    for t in testi:
        assert client.incassa(t) is True


def _ordine_paper(bet_id: str, *, side: str, abbinato: float, ref: str) -> Any:
    """Un ordine del blotter paper con gli attributi di ``BetfairOrder``."""
    from flumine.order.order import OrderStatus
    from flumine.order.ordertype import LimitOrder

    return SimpleNamespace(
        bet_id=bet_id, market_id=MKT, selection_id=SEL, handicap=0.0, side=side,
        status=OrderStatus.EXECUTION_COMPLETE,
        order_type=LimitOrder(300.0, abbinato, persistence_type="LAPSE"),
        size_matched=abbinato, size_remaining=0.0, size_cancelled=0.0, size_lapsed=0.0,
        size_voided=0.0, average_price_matched=300.0,
        context={"customer_order_ref": ref}, notes={"customer_order_ref": ref},
        customer_order_ref="hash", responses=SimpleNamespace(date_time_placed=None))


def _dal_runner_paper(client: EO.ClientEsiti, ordini: List[Any], ms: int) -> None:
    testi: List[str] = []
    assert EO.pubblica_conto_paper(MKT, ordini,
                                   lambda t, d: testi.append(json.dumps({"t": t, "d": d})),
                                   adesso_ms=ms)
    for t in testi:
        assert client.incassa(t) is True


def _ms(dt) -> int:
    return int(dt.timestamp() * 1000)


PAR = _params(conto_every_s=120.0)          # la cadenza VERA di produzione


def _giro(db, market, quando) -> int:
    return S.sorveglia_posizione_di_conto(params=PAR, market=market, db=db, now=quando)


# ===========================================================================
# 1. LIVE: il canale sveglia, la REST conferma nello stesso giro
# ===========================================================================
def test_la_chiusura_dal_sito_si_vede_al_primo_giro_dopo_il_canale():
    client = _client()
    db = DbFinto([_lay_del_bot()])
    market = MercatoFinto([_riga_rest(bet_id=BOT_BET, side="LAY", size=5.26, ref=REF_BOT)])
    assert _giro(db, market, ADESSO) == 0                  # REST a cadenza: intera
    assert market.letture == 1
    market.righe.append(_riga_rest(bet_id="900000000002", side="BACK", size=5.26,
                                   ref=None))
    _dal_runner(client, [UO_BOT, _uo("900000000002", side="B", sm=5.26, rfo=None)],
                _ms(ADESSO + timedelta(seconds=0.4)))
    # un secondo dopo: la cadenza (120 s) NON e' passata, il canale la salta
    assert _giro(db, market, ADESSO + timedelta(seconds=1)) == 1
    assert market.letture == 2, "la REST riletta SUBITO, a conferma"
    p = db.payload("chiuso_dall_utente")
    assert p["dove"] == "fuori dall'app (stream ordini)" and p["come"] == "chiusa"
    sel = p["selezioni"][0]
    assert sel["conferma"] == "posizione di conto riletta via REST"
    assert sel["latenza_ms"]["dal_runner"] == 600
    assert db.trades[0]["meta"]["chiuso_dall_utente"]["dove"] == "fuori dall'app (stream ordini)"
    assert "35760084" in db.user_closed_event_ids()


def test_senza_canale_la_stessa_chiusura_aspetta_la_cadenza_come_prima():
    db = DbFinto([_lay_del_bot()])
    market = MercatoFinto([_riga_rest(bet_id=BOT_BET, side="LAY", size=5.26, ref=REF_BOT)])
    assert _giro(db, market, ADESSO) == 0
    market.righe.append(_riga_rest(bet_id="900000000002", side="BACK", size=5.26, ref=None))
    assert _giro(db, market, ADESSO + timedelta(seconds=1)) == 0
    assert market.letture == 1
    assert _giro(db, market, ADESSO + timedelta(seconds=121)) == 1
    assert db.payload("chiuso_dall_utente")["dove"] == "fuori dall'app"


def test_il_canale_dice_chiusa_ma_il_conto_no_vince_il_conto():
    client = _client()
    db = DbFinto([_lay_del_bot()])
    # sul conto c'e' anche una lay VECCHIA dell'utente (prima dell'iscrizione
    # dello stream): la back dell'utente chiude quella, non la posizione del bot
    market = MercatoFinto([
        _riga_rest(bet_id=BOT_BET, side="LAY", size=5.26, ref=REF_BOT),
        _riga_rest(bet_id="900000000001", side="LAY", size=5.26, ref=None)])
    _giro(db, market, ADESSO)
    market.righe.append(_riga_rest(bet_id="900000000002", side="BACK", size=5.26, ref=None))
    _dal_runner(client, [UO_BOT, _uo("900000000002", side="B", sm=5.26, rfo=None)],
                _ms(ADESSO))
    assert _giro(db, market, ADESSO + timedelta(seconds=1)) == 0
    assert market.letture == 2
    assert "chiuso_dall_utente" not in db.kinds()
    d = db.payload("diagnosi")
    assert d["verdetto"] == "canale_non_confermato"


def test_lo_snap_ripetuto_non_fa_rileggere_la_REST():
    client = _client()
    db = DbFinto([_lay_del_bot()])
    market = MercatoFinto([
        _riga_rest(bet_id=BOT_BET, side="LAY", size=5.26, ref=REF_BOT),
        _riga_rest(bet_id="900000000001", side="LAY", size=5.26, ref=None)])
    _giro(db, market, ADESSO)
    uo = [UO_BOT, _uo("900000000002", side="B", sm=5.26, rfo=None)]
    _dal_runner(client, uo, _ms(ADESSO))
    _giro(db, market, ADESSO + timedelta(seconds=1))
    letture = market.letture
    for i in range(3):
        _dal_runner(client, uo, _ms(ADESSO + timedelta(seconds=3 * (i + 1))))
        _giro(db, market, ADESSO + timedelta(seconds=3 * (i + 1) + 0.5))
    assert market.letture == letture, "snap identici: nessuna REST fuori cadenza"


def test_la_riduzione_parziale_dal_sito_ferma_il_bot():
    client = _client()
    db = DbFinto([_lay_del_bot()])
    market = MercatoFinto([_riga_rest(bet_id=BOT_BET, side="LAY", size=5.26, ref=REF_BOT)])
    _giro(db, market, ADESSO)
    market.righe.append(_riga_rest(bet_id="900000000002", side="BACK", size=2.0, ref=None))
    _dal_runner(client, [UO_BOT, _uo("900000000002", side="B", sm=2.0, rfo=None)],
                _ms(ADESSO))
    assert _giro(db, market, ADESSO + timedelta(seconds=1)) == 1
    p = db.payload("chiuso_dall_utente")
    assert p["come"] == "ridotta"
    assert p["selezioni"][0]["ancora_viva"] == pytest.approx(-3.26, abs=0.01)


# ===========================================================================
# 2. PAPER: il blotter del runner paper decide (ordine manuale dell'app)
# ===========================================================================
def _lay_paper(**kw: Any) -> dict:
    return _lay_del_bot(mode="paper", **kw)


def test_in_PAPER_lordine_manuale_dellapp_ferma_omega_senza_REST():
    client = _client()
    db = DbFinto([_lay_paper()])
    market = MercatoFinto([])
    bot = _ordine_paper(BOT_BET, side="LAY", abbinato=5.26, ref="awlq1")
    _dal_runner_paper(client, [bot], _ms(ADESSO))
    assert _giro(db, market, ADESSO) == 0                 # intera
    _dal_runner_paper(client, [bot, _ordine_paper("P2", side="BACK", abbinato=5.26,
                                                  ref="awlq2")],
                      _ms(ADESSO + timedelta(seconds=0.5)))
    assert _giro(db, market, ADESSO + timedelta(seconds=1)) == 1
    assert market.letture == 0, "in paper nessuna REST"
    p = db.payload("chiuso_dall_utente")
    assert p["dove"] == "dall'app (ordine manuale sul runner paper)" and p["come"] == "chiusa"
    assert p["selezioni"][0]["latenza_ms"]["dal_runner"] == 500
    assert "35760084" in db.user_closed_event_ids()


def test_in_PAPER_la_riduzione_parziale_dellapp_ferma_omega():
    client = _client()
    db = DbFinto([_lay_paper()])
    bot = _ordine_paper(BOT_BET, side="LAY", abbinato=5.26, ref="awlq1")
    _dal_runner_paper(client, [bot, _ordine_paper("P2", side="BACK", abbinato=1.0,
                                                  ref="awlq2")], _ms(ADESSO))
    assert _giro(db, MercatoFinto([]), ADESSO) == 1
    assert db.payload("chiuso_dall_utente")["come"] == "ridotta"


def test_paper_e_live_non_si_mescolano():
    client = _client()
    # una riga LIVE: la fotografia PAPER della chiusura non la tocca
    db = DbFinto([_lay_del_bot()])
    market = MercatoFinto([_riga_rest(bet_id=BOT_BET, side="LAY", size=5.26, ref=REF_BOT)])
    _giro(db, market, ADESSO)
    _dal_runner_paper(client, [_ordine_paper(BOT_BET, side="LAY", abbinato=5.26, ref="a1"),
                               _ordine_paper("P2", side="BACK", abbinato=5.26, ref="a2")],
                      _ms(ADESSO))
    assert _giro(db, market, ADESSO + timedelta(seconds=1)) == 0
    assert market.letture == 1 and "chiuso_dall_utente" not in db.kinds()
    # una riga PAPER: la fotografia LIVE della chiusura non la tocca
    S.svuota_le_cache()
    client = _client()
    db2 = DbFinto([_lay_paper()])
    _dal_runner(client, [UO_BOT, _uo("900000000002", side="B", sm=5.26, rfo=None)],
                _ms(ADESSO))
    assert _giro(db2, MercatoFinto([]), ADESSO + timedelta(seconds=1)) == 0
    assert "chiuso_dall_utente" not in db2.kinds()


def test_senza_canale_in_PAPER_tutto_come_prima():
    db = DbFinto([_lay_paper()])
    market = MercatoFinto([_riga_rest(bet_id=BOT_BET, side="LAY", size=5.26, ref=REF_BOT),
                           _riga_rest(bet_id="9", side="BACK", size=5.26, ref=None)])
    assert _giro(db, market, ADESSO) == 0
    assert market.letture == 0 and db.attivita == []


# ===========================================================================
# 3. LA SVEGLIA DEL GIRO
# ===========================================================================
def test_la_sveglia_si_alza_sul_mercato_di_omega_e_interrompe_la_dormita(monkeypatch):
    client = _client()
    db = DbFinto([_lay_del_bot()])
    _giro(db, MercatoFinto([_riga_rest(bet_id=BOT_BET, side="LAY", size=5.26,
                                       ref=REF_BOT)]), ADESSO)
    assert S._MERCATI_CONTO == {MKT}
    S._CONTO.sveglia.clear()
    _dal_runner(client, [UO_BOT], _ms(ADESSO))
    assert S._CONTO.sveglia.is_set()
    # la dormita del ciclo (60 s a vuoto) si interrompe dopo il pavimento (1 s)
    orologio = {"t": 1000.0}
    dormite: List[float] = []

    def _dormi(s: float) -> None:
        dormite.append(s)
        orologio["t"] += s

    monkeypatch.setattr(S.time, "sleep", _dormi)
    monkeypatch.setattr(S.time, "monotonic", lambda: orologio["t"])
    S._dormi_o_sveglia(60.0, PAR)
    assert dormite == [1.0], "svegliato al primo secondo, non dopo 60"


def test_senza_canale_la_dormita_e_quella_di_sempre(monkeypatch):
    orologio = {"t": 1000.0}
    dormite: List[float] = []

    def _dormi(s: float) -> None:
        dormite.append(s)
        orologio["t"] += s

    monkeypatch.setattr(S.time, "sleep", _dormi)
    monkeypatch.setattr(S.time, "monotonic", lambda: orologio["t"])
    S._CONTO.sveglia.set()
    S._dormi_o_sveglia(5.0, PAR)
    assert dormite == [1.0] * 5


# ===========================================================================
# 4. REPERTO W2 (coordinatore, 08/10): il verdetto in ESPOSIZIONE, non in size
# ===========================================================================
def test_green_up_dellutente_su_un_suo_ordine_non_tocca_omega():
    """Omega lay 5,26 @300; dal sito l'utente banca 5 @300 e se la copre con una
    punta 5,36 @280 (green-up SUO). Netto in size -4,90: prima «ridotta» (stop).
    In esposizione la parte dell'utente e' piatta: Omega intera."""
    db = DbFinto([_lay_del_bot()])
    market = MercatoFinto([
        _riga_rest(bet_id=BOT_BET, side="LAY", size=5.26, ref=REF_BOT),
        _riga_rest(bet_id="9001", side="LAY", size=5.0, ref=None, price=300.0),
        _riga_rest(bet_id="9002", side="BACK", size=5.36, ref=None, price=280.0)])
    assert _giro(db, market, ADESSO) == 0
    assert "chiuso_dall_utente" not in db.kinds()


def test_green_up_estremo_dellutente_non_chiude_omega():
    """Omega lay 2 @300; dal sito l'utente banca 10 @5,0 e la copre con una
    punta 33,33 @1,50: netto in size +21,33, prima «chiusa»."""
    db = DbFinto([_lay_del_bot(size=2.0)])
    market = MercatoFinto([
        _riga_rest(bet_id=BOT_BET, side="LAY", size=2.0, ref=REF_BOT),
        _riga_rest(bet_id="9001", side="LAY", size=10.0, ref=None, price=5.0),
        _riga_rest(bet_id="9002", side="BACK", size=33.33, ref=None, price=1.50)])
    assert _giro(db, market, ADESSO) == 0
    assert "chiuso_dall_utente" not in db.kinds()


def test_la_chiusura_vera_a_un_prezzo_diverso_resta_chiusa():
    db = DbFinto([_lay_del_bot()])
    market = MercatoFinto([
        _riga_rest(bet_id=BOT_BET, side="LAY", size=5.26, ref=REF_BOT),
        _riga_rest(bet_id="9001", side="BACK", size=5.26, ref=None, price=250.0)])
    assert _giro(db, market, ADESSO) == 1
    assert db.payload("chiuso_dall_utente")["come"] == "chiusa"


# ===========================================================================
# 5. SECONDA TAPPA (coordinatore, 08/10): l'ordine di un ALTRO bot non e'
#    dell'utente; DB illeggibile -> nessun verdetto, nessun ordine nuovo
# ===========================================================================
class DbConProprietari(DbFinto):
    """``DbFinto`` del 16/09 + ``proprietari_bot_conto(bet_ids, modo)`` (firma di
    ``omega_db``)."""

    def __init__(self, trades: List[dict], dei_bot: Dict[str, str] = None, *,
                 giu: bool = False) -> None:
        super().__init__(trades)
        self.dei_bot = dict(dei_bot or {})
        self.giu = giu
        self.letture_proprietari: List[tuple] = []

    def proprietari_bot_conto(self, bet_ids: List[str], modo: str = "live") -> Dict[str, str]:
        self.letture_proprietari.append((tuple(bet_ids), modo))
        if self.giu:
            raise RuntimeError("DB giu'")
        return {b: m for b, m in self.dei_bot.items() if b in bet_ids}


@pytest.fixture
def _proprietari_subito(monkeypatch):
    monkeypatch.setattr(S._CONTO.proprietari, "_riprova_s", 0.0)


def _back_che_chiude(bet_id: str, ref: Any) -> dict:
    """Un BACK 5,26 @250 sulla selezione di Omega: se fosse dell'utente CHIUDEREBBE
    la lay di Omega."""
    return _riga_rest(bet_id=bet_id, side="BACK", size=5.26, ref=ref, price=250.0)


def test_ordine_di_un_altro_bot_sulla_selezione_non_ferma_omega(_proprietari_subito):
    """Ref di un'altra strategia (``safe-t4``): riconosciuto dai riferimenti,
    nessuna lettura del DB, nessun verdetto."""
    db = DbConProprietari([_lay_del_bot()])
    market = MercatoFinto([_riga_rest(bet_id=BOT_BET, side="LAY", size=5.26, ref=REF_BOT),
                           _back_che_chiude("7001", "safe-t4")])
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db,
                                          now=ADESSO) == 0
    assert "chiuso_dall_utente" not in db.kinds()
    assert db.letture_proprietari == []


def test_ordine_di_un_altro_bot_lo_dice_il_DB_manuale_invece_ferma(_proprietari_subito):
    db = DbConProprietari([_lay_del_bot()], {"7002": "tabella:mike_trades"})
    market = MercatoFinto([_riga_rest(bet_id=BOT_BET, side="LAY", size=5.26, ref=REF_BOT),
                           _back_che_chiude("7002", "awlq9")])
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market, db=db,
                                          now=ADESSO) == 0
    assert db.letture_proprietari == [(("7002",), "live")]
    # lo stesso ordine, ma il DB non lo dice di un bot: e' l'utente
    S.svuota_le_cache()
    db2 = DbConProprietari([_lay_del_bot()], {})
    market2 = MercatoFinto([_riga_rest(bet_id=BOT_BET, side="LAY", size=5.26, ref=REF_BOT),
                            _back_che_chiude("7003", "awlq10")])
    assert S.sorveglia_posizione_di_conto(params=_params(), market=market2, db=db2,
                                          now=ADESSO) == 1
    assert db2.payload("chiuso_dall_utente")["come"] == "chiusa"


def test_DB_giu_omega_non_decide_e_non_apre_ne_chiude(_proprietari_subito, monkeypatch):
    db = DbConProprietari([_lay_del_bot()], {}, giu=True)
    market = MercatoFinto([_riga_rest(bet_id=BOT_BET, side="LAY", size=5.26, ref=REF_BOT),
                           _back_che_chiude("7004", "awlq11")])
    assert _giro(db, market, ADESSO) == 0
    assert "chiuso_dall_utente" not in db.kinds(), "nessun verdetto al buio"
    assert S._CONTO.eventi_in_verifica() == {"35760084"}
    d = [p for k, p in db.attivita if k == "diagnosi" and p.get("verdetto") == "in_verifica"]
    assert d and d[0]["ordini_ignoti"] == ["7004"]
    # nessun green-up / proposta sulla partita
    assert S._greenup_candidates(db, set()) == []
    # nessuna apertura sulla partita (lo scan non entra nell'evento)
    entrati: List[str] = []
    monkeypatch.setattr(S, "_scan_event_legs",
                        lambda **kw: (entrati.append(str(kw["ev"].event_id)) or (0, 0)))
    S.scan_and_place_legs(control={"daily_goal": 10.0, "mode": "live"}, params=_params(),
                          events=[SimpleNamespace(event_id="35760084"),
                                  SimpleNamespace(event_id="999")],
                          traded_ids=set(), traded_legs=set(), aggregates={},
                          market=market, db=db, now=ADESSO)
    assert entrati == ["999"]
    # il DB torna: alla rilettura (respiro della verifica, non i 120 s) si sa che
    # e' dell'utente -> Omega si ferma e la verifica finisce
    db.giu = False
    assert _giro(db, market, ADESSO + timedelta(seconds=31)) == 1
    assert S._CONTO.eventi_in_verifica() == set()


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
