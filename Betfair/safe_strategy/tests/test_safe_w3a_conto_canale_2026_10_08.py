"""08/10 (W3a) - SAFE SA SUBITO DEGLI ORDINI ESTERNI (canale del conto).

Ordine dell'utente (08/10): «I BOT DEVONO ESSERE AGGIORNATI NEL MINOR TEMPO
POSSIBILE SULLE OPERAZIONI FATTE DA APP O DA SITO [...] QUANDO INTERVENGO IO [...]
I BOT LO SANNO E NON FANNO ALTRO».

Prima: Safe rileggeva la posizione di conto SOLO via REST ogni
``CONTO_EVERY_S`` (30 s) e al piu' 2 mercati per ciclo; in paper non vedeva
niente; una riduzione parziale si dichiarava e basta. Ora, con lo STESSO
meccanismo di Mike e Omega (``esiti_ordini_canale.SorveglianzaConto``):
  1. una fotografia NUOVA dello stream ordini che dice la posizione non piu'
     intera fa rileggere la REST nello STESSO giro (fuori cadenza e fuori dal
     tetto per ciclo), che decide;
  2. la riduzione parziale confermata ferma il bot (marcatore ``verdetto='ridotta'``);
  3. in PAPER decide la fotografia del blotter del runner paper (ordine manuale
     dell'app), riconoscendo gli ordini di Safe per ``bet_id``; senza REST;
  4. paper e live mai mescolati; senza canale identico a prima;
  5. la sveglia del conto alza l'evento del ciclo.

I finti parlano come il vero (fotografia LIVE dalla cache VERA dello stream
ordini e dal produttore VERO; fotografia PAPER dal produttore VERO su ordini con
gli attributi di ``BetfairOrder``; REST = ``MercatoConConto`` del 16/09). Tennis:
nessuna registrazione nel container, la stessa funzione e' provata con una riga
``sport='tennis'`` (ref ``safe_tennis-t<id>``). ASCII-only.
"""
from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.stream import esiti_ordini_canale as EO

from test_bot_service import NOW, FakeDB
from test_chiusura_dell_utente_2026_09_16 import MercatoConConto, _ordine, _riga

MKT = "1.1"
SEL = 7


@pytest.fixture(autouse=True)
def _pulito():
    S._EVENTI_CHIUSI.clear()
    S._CONTO_LETTO_A.clear()
    S._CONTO.installa(None)
    yield
    S._EVENTI_CHIUSI.clear()
    S._CONTO_LETTO_A.clear()
    S._CONTO.installa(None)


def _client() -> EO.ClientEsiti:
    memoria = EO.MemoriaConto()
    S._CONTO.installa(memoria)
    return EO.ClientEsiti(memoria, topic=EO.TOPIC_CONTO_TUTTI, porta_ws=1)


def _uo(bet_id: str, *, side: str, sm: float, rfo: Any) -> Dict[str, Any]:
    return {"id": bet_id, "p": 32.0, "s": sm, "side": side, "status": "EC", "pt": "L",
            "ot": "L", "pd": 1_700_000_000_000, "md": 1_700_000_000_500, "avp": 32.0,
            "sm": sm, "sr": 0.0, "sl": 0.0, "sc": 0.0, "sv": 0.0, "rfo": rfo, "rfs": None}


def _dal_runner(client: EO.ClientEsiti, uo: List[Dict[str, Any]], ms: int) -> None:
    from betfairlightweight.streaming.cache import OrderBookCache

    cache = OrderBookCache(MKT, ms, False)
    cache.update_cache({"id": MKT, "orc": [{"id": SEL, "uo": uo}]}, ms)
    co = cache.create_resource(0)
    co.client = SimpleNamespace(paper_trade=False)
    testi: List[str] = []
    EO.pubblica_conto_da_evento(
        SimpleNamespace(event=[co]),
        lambda t, d: testi.append(json.dumps({"t": t, "d": d}, default=str)), adesso_ms=ms)
    for t in testi:
        assert client.incassa(t) is True


def _ordine_paper(bet_id: str, *, side: str, abbinato: float, ref: str) -> Any:
    from flumine.order.order import OrderStatus
    from flumine.order.ordertype import LimitOrder

    return SimpleNamespace(
        bet_id=bet_id, market_id=MKT, selection_id=SEL, handicap=0.0, side=side,
        status=OrderStatus.EXECUTION_COMPLETE,
        order_type=LimitOrder(32.0, abbinato, persistence_type="LAPSE"),
        size_matched=abbinato, size_remaining=0.0, size_cancelled=0.0, size_lapsed=0.0,
        size_voided=0.0, average_price_matched=32.0,
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


def _sorveglia(db, mercato, riga, quando):
    return S._sorveglia_posizione_di_conto(
        db=db, market=mercato, parents=[riga], closings={int(riga["id"]): []},
        now=quando, params={})


def _bet_del_bot(riga: dict) -> str:
    return f"b-safe-t{riga['id']}"


# ===========================================================================
# 1. LIVE: il canale sveglia, la REST conferma nello stesso giro
# ===========================================================================
def test_la_chiusura_dal_sito_si_vede_al_primo_giro_dopo_il_canale():
    client = _client()
    db = FakeDB(mode="live")
    riga = _riga(db)                                  # LAY 2,00 del bot
    mercato = MercatoConConto(vivi=[_ordine(f"safe-t{riga['id']}", "lay", 2.0)])
    assert _sorveglia(db, mercato, riga, NOW) == 0
    assert len(mercato.letture) == 1
    mercato.vivi.append(_ordine("utente-1", "back", 2.0))
    _dal_runner(client, [_uo(_bet_del_bot(riga), side="L", sm=2.0, rfo=f"safe-t{riga['id']}"),
                         _uo("U1", side="B", sm=2.0, rfo=None)],
                _ms(NOW + timedelta(seconds=0.25)))
    # la cadenza (30 s) NON e' passata: il canale la salta
    assert _sorveglia(db, mercato, riga, NOW + timedelta(seconds=1)) == 1
    assert len(mercato.letture) == 2, "la REST riletta SUBITO, a conferma"
    mk = S.evento_chiuso_dall_utente("1.1")
    assert mk["come"] == "fuori_app" and mk["verdetto"] == "chiusa"
    assert mk["dove"] == "fuori dall'app (stream ordini)"
    assert mk["latenza_ms"]["dal_runner"] == 750


def test_senza_canale_la_stessa_chiusura_aspetta_la_cadenza_come_prima():
    db = FakeDB(mode="live")
    riga = _riga(db)
    mercato = MercatoConConto(vivi=[_ordine(f"safe-t{riga['id']}", "lay", 2.0)])
    assert _sorveglia(db, mercato, riga, NOW) == 0
    mercato.vivi.append(_ordine("utente-1", "back", 2.0))
    assert _sorveglia(db, mercato, riga, NOW + timedelta(seconds=1)) == 0
    assert len(mercato.letture) == 1
    assert _sorveglia(db, mercato, riga, NOW + timedelta(seconds=31)) == 1
    assert "dove" not in S.evento_chiuso_dall_utente("1.1")


def test_il_canale_salta_anche_il_tetto_dei_mercati_per_ciclo():
    """Due mercati gia' letti in questo ciclo (tetto 2): senza segnale il terzo
    aspetta il giro dopo; col segnale si legge SUBITO."""
    client = _client()
    db = FakeDB(mode="live")
    altre = [_riga(db, market_id=m, signal_key=f"{m}:k") for m in ("2.1", "2.2")]
    riga = _riga(db)
    mercato = MercatoConConto(vivi=[_ordine(f"safe-t{r['id']}", "lay", 2.0,
                                            market_id=r["market_id"])
                                    for r in altre + [riga]]
                              + [_ordine("utente-1", "back", 2.0)])
    _dal_runner(client, [_uo(_bet_del_bot(riga), side="L", sm=2.0, rfo=f"safe-t{riga['id']}"),
                         _uo("U1", side="B", sm=2.0, rfo=None)], _ms(NOW))
    n = S._sorveglia_posizione_di_conto(
        db=db, market=mercato, parents=altre + [riga],
        closings={int(r["id"]): [] for r in altre + [riga]}, now=NOW, params={})
    assert n == 1 and sorted(mercato.letture) == ["1.1", "2.1", "2.2"]


def test_lo_snap_ripetuto_non_fa_rileggere_la_REST():
    client = _client()
    db = FakeDB(mode="live")
    riga = _riga(db)
    # la back dell'utente chiude una SUA lay di prima: il conto conferma «intera»
    mercato = MercatoConConto(vivi=[_ordine(f"safe-t{riga['id']}", "lay", 2.0),
                                    _ordine("utente-0", "lay", 2.0),
                                    _ordine("utente-1", "back", 2.0)])
    _sorveglia(db, mercato, riga, NOW)
    uo = [_uo(_bet_del_bot(riga), side="L", sm=2.0, rfo=f"safe-t{riga['id']}"),
          _uo("U1", side="B", sm=2.0, rfo=None)]
    _dal_runner(client, uo, _ms(NOW))
    assert _sorveglia(db, mercato, riga, NOW + timedelta(seconds=1)) == 0
    verdetti = [p.get("verdetto") for k, p in db.activity if k == "posizione_di_conto"]
    assert verdetti == ["canale_non_confermato"]
    letture = len(mercato.letture)
    for i in range(3):
        _dal_runner(client, uo, _ms(NOW + timedelta(seconds=3 * (i + 1))))
        _sorveglia(db, mercato, riga, NOW + timedelta(seconds=3 * (i + 1) + 0.5))
    assert len(mercato.letture) == letture, "snap identici: nessuna REST fuori cadenza"


def test_la_riduzione_parziale_dal_sito_ferma_il_bot():
    client = _client()
    db = FakeDB(mode="live")
    riga = _riga(db, size=4.0, liability=124.0)
    mercato = MercatoConConto(vivi=[_ordine(f"safe-t{riga['id']}", "lay", 4.0)])
    _sorveglia(db, mercato, riga, NOW)
    mercato.vivi.append(_ordine("utente-1", "back", 1.0))
    _dal_runner(client, [_uo(_bet_del_bot(riga), side="L", sm=4.0, rfo=f"safe-t{riga['id']}"),
                         _uo("U1", side="B", sm=1.0, rfo=None)], _ms(NOW))
    assert _sorveglia(db, mercato, riga, NOW + timedelta(seconds=1)) == 1
    mk = S.evento_chiuso_dall_utente("1.1")
    assert mk["verdetto"] == "ridotta" and mk["ancora_viva"] == -3.0


# ===========================================================================
# 2. PAPER: il blotter del runner paper decide
# ===========================================================================
def test_in_PAPER_lordine_manuale_dellapp_ferma_safe_senza_REST():
    client = _client()
    db = FakeDB(mode="paper")
    riga = _riga(db, mode="paper", bet_id="P1")
    mercato = MercatoConConto()
    bot = _ordine_paper("P1", side="LAY", abbinato=2.0, ref="awlq1")
    _dal_runner_paper(client, [bot], _ms(NOW))
    assert _sorveglia(db, mercato, riga, NOW) == 0          # intera
    _dal_runner_paper(client, [bot, _ordine_paper("P2", side="BACK", abbinato=2.0,
                                                  ref="awlq2")],
                      _ms(NOW + timedelta(seconds=0.5)))
    assert _sorveglia(db, mercato, riga, NOW + timedelta(seconds=1)) == 1
    assert mercato.letture == [], "in paper nessuna REST"
    mk = S.evento_chiuso_dall_utente("1.1")
    assert mk["come"] == "app_paper" and mk["verdetto"] == "chiusa"
    assert mk["dove"] == "dall'app (ordine manuale sul runner paper)"
    assert mk["latenza_ms"]["dal_runner"] == 500


def test_in_PAPER_tennis_si_riconosce_col_ref_del_tennis():
    client = _client()
    db = FakeDB(mode="paper")
    riga = _riga(db, mode="paper", bet_id="P1", sport="tennis")
    _dal_runner_paper(client, [_ordine_paper("P1", side="LAY", abbinato=2.0, ref="awlq1"),
                               _ordine_paper("P2", side="BACK", abbinato=1.0, ref="awlq2")],
                      _ms(NOW))
    assert _sorveglia(db, MercatoConConto(), riga, NOW) == 1
    assert S.evento_chiuso_dall_utente("1.1")["verdetto"] == "ridotta"


def test_in_PAPER_senza_bet_id_le_gambe_non_si_ritrovano_e_non_si_decide():
    client = _client()
    db = FakeDB(mode="paper")
    riga = _riga(db, mode="paper")                # esito del runner non ancora arrivato
    _dal_runner_paper(client, [_ordine_paper("P1", side="LAY", abbinato=2.0, ref="awlq1"),
                               _ordine_paper("P2", side="BACK", abbinato=2.0, ref="awlq2")],
                      _ms(NOW))
    assert _sorveglia(db, MercatoConConto(), riga, NOW) == 0
    assert S.evento_chiuso_dall_utente("1.1") is None


def test_paper_e_live_non_si_mescolano():
    client = _client()
    db = FakeDB(mode="live")
    riga = _riga(db, bet_id="P1")
    mercato = MercatoConConto(vivi=[_ordine(f"safe-t{riga['id']}", "lay", 2.0)])
    _sorveglia(db, mercato, riga, NOW)
    _dal_runner_paper(client, [_ordine_paper("P1", side="LAY", abbinato=2.0, ref="awlq1"),
                               _ordine_paper("P2", side="BACK", abbinato=2.0, ref="awlq2")],
                      _ms(NOW))
    assert _sorveglia(db, mercato, riga, NOW + timedelta(seconds=1)) == 0
    assert len(mercato.letture) == 1 and S.evento_chiuso_dall_utente("1.1") is None
    # e al contrario: riga PAPER, fotografia LIVE della chiusura
    S._CONTO.installa(None)
    client = _client()
    db2 = FakeDB(mode="paper")
    riga2 = _riga(db2, mode="paper", bet_id="B9")
    _dal_runner(client, [_uo("B9", side="L", sm=2.0, rfo=f"safe-t{riga2['id']}"),
                         _uo("U1", side="B", sm=2.0, rfo=None)], _ms(NOW))
    assert _sorveglia(db2, MercatoConConto(), riga2, NOW + timedelta(seconds=1)) == 0
    assert S.evento_chiuso_dall_utente("1.1") is None


def test_senza_canale_in_PAPER_tutto_come_prima():
    db = FakeDB(mode="paper")
    riga = _riga(db, mode="paper", bet_id="P1")
    mercato = MercatoConConto(vivi=[_ordine(f"safe-t{riga['id']}", "lay", 2.0),
                                    _ordine("utente-1", "back", 2.0)])
    assert _sorveglia(db, mercato, riga, NOW) == 0
    assert mercato.letture == [] and "posizione_di_conto" not in db.kinds()


# ===========================================================================
# 3. LA SVEGLIA DEL GIRO
# ===========================================================================
def test_la_sveglia_del_conto_alza_levento_del_ciclo_solo_sui_mercati_di_safe():
    client = _client()
    db = FakeDB(mode="live")
    riga = _riga(db)
    _sorveglia(db, MercatoConConto(vivi=[_ordine(f"safe-t{riga['id']}", "lay", 2.0)]),
               riga, NOW)
    assert S._MERCATI_CONTO == {MKT}
    S._SVEGLIA.clear()
    _dal_runner(client, [_uo("X", side="L", sm=1.0, rfo=None)], _ms(NOW))
    assert S._SVEGLIA.is_set(), "fotografia nuova su un mercato di Safe"
    S._SVEGLIA.clear()
    S._MERCATI_CONTO.clear()
    _dal_runner(client, [_uo("X", side="L", sm=2.0, rfo=None)], _ms(NOW) + 1)
    assert not S._SVEGLIA.is_set(), "mercato che Safe non difende: nessuna sveglia"


# ===========================================================================
# 4. REPERTO W2 (coordinatore, 08/10): il verdetto in ESPOSIZIONE, non in size
# ===========================================================================
def test_green_up_dellutente_su_un_suo_ordine_non_tocca_safe():
    """Safe lay 2 @32; dal sito l'utente banca 5 @32 e se la copre con una punta
    5,71 @28 (green-up SUO). Netto in size -1,29: prima «ridotta» (stop)."""
    db = FakeDB(mode="live")
    riga = _riga(db)
    mercato = MercatoConConto(vivi=[
        _ordine(f"safe-t{riga['id']}", "lay", 2.0),
        _ordine("utente-1", "lay", 5.0),
        _ordine("utente-2", "back", 5.71, avg_price_matched=28.0)])
    assert _sorveglia(db, mercato, riga, NOW) == 0
    assert S.evento_chiuso_dall_utente("1.1") is None


def test_green_up_estremo_dellutente_non_chiude_safe():
    """Safe lay 2 @32; dal sito banca 10 @5,0 coperta con punta 33,33 @1,50:
    netto in size +21,33, prima «chiusa»."""
    db = FakeDB(mode="live")
    riga = _riga(db)
    mercato = MercatoConConto(vivi=[
        _ordine(f"safe-t{riga['id']}", "lay", 2.0),
        _ordine("utente-1", "lay", 10.0, avg_price_matched=5.0),
        _ordine("utente-2", "back", 33.33, avg_price_matched=1.50)])
    assert _sorveglia(db, mercato, riga, NOW) == 0
    assert S.evento_chiuso_dall_utente("1.1") is None


def test_la_chiusura_vera_a_un_prezzo_diverso_resta_chiusa():
    db = FakeDB(mode="live")
    riga = _riga(db)
    mercato = MercatoConConto(vivi=[
        _ordine(f"safe-t{riga['id']}", "lay", 2.0),
        _ordine("utente-1", "back", 2.0, avg_price_matched=26.0)])
    assert _sorveglia(db, mercato, riga, NOW) == 1
    assert S.evento_chiuso_dall_utente("1.1")["verdetto"] == "chiusa"


# ===========================================================================
# 5. SECONDA TAPPA (coordinatore, 08/10): l'ordine di un ALTRO bot non e'
#    dell'utente; DB illeggibile -> nessun verdetto, nessun ordine nuovo
# ===========================================================================
class DbConProprietari(FakeDB):
    """``FakeDB`` + ``proprietari_bot_conto(bet_ids, modo)`` (firma di ``bot_db``)."""

    def __init__(self, dei_bot: Dict[str, str] = None, *, giu: bool = False) -> None:
        super().__init__(mode="live")
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
    S._CONTO.azzera()
    monkeypatch.setattr(S._CONTO.proprietari, "_riprova_s", 0.0)
    yield
    S._CONTO.azzera()


def test_ordine_di_un_altro_bot_sulla_selezione_non_ferma_safe(_proprietari_subito):
    """Una punta 2 @26 di MIKE (ref ``mike-t5``) sulla selezione della lay di Safe:
    se fosse dell'utente la chiuderebbe. Riconosciuta dai riferimenti: niente."""
    db = DbConProprietari()
    riga = _riga(db)
    mercato = MercatoConConto(vivi=[_ordine(f"safe-t{riga['id']}", "lay", 2.0),
                                    _ordine("mike-t5", "back", 2.0, avg_price_matched=26.0)])
    assert _sorveglia(db, mercato, riga, NOW) == 0
    assert S.evento_chiuso_dall_utente("1.1") is None
    assert db.letture_proprietari == []


def test_un_altra_variante_della_safe_non_e_l_utente(_proprietari_subito):
    db = DbConProprietari()
    riga = _riga(db)
    mercato = MercatoConConto(vivi=[_ordine(f"safe-t{riga['id']}", "lay", 2.0),
                                    _ordine("safe-t999", "back", 2.0, avg_price_matched=26.0)])
    assert _sorveglia(db, mercato, riga, NOW) == 0
    assert S.evento_chiuso_dall_utente("1.1") is None


def test_il_DB_dice_bot_o_utente(_proprietari_subito):
    db = DbConProprietari({"b-awlq1": "coda_source:omega"})
    riga = _riga(db)
    mercato = MercatoConConto(vivi=[_ordine(f"safe-t{riga['id']}", "lay", 2.0),
                                    _ordine("awlq1", "back", 2.0, avg_price_matched=26.0)])
    assert _sorveglia(db, mercato, riga, NOW) == 0
    assert db.letture_proprietari == [(("b-awlq1",), "live")]
    # lo stesso ordine, ma del desktop: utente -> Safe si ferma
    mercato.vivi[1] = _ordine("awlq2", "back", 2.0, avg_price_matched=26.0)
    S._CONTO_LETTO_A.clear()
    assert _sorveglia(db, mercato, riga, NOW + timedelta(seconds=31)) == 1
    assert S.evento_chiuso_dall_utente("1.1")["verdetto"] == "chiusa"


def test_DB_giu_safe_non_decide_e_non_piazza(_proprietari_subito):
    db = DbConProprietari({}, giu=True)
    riga = _riga(db)
    mercato = MercatoConConto(vivi=[_ordine(f"safe-t{riga['id']}", "lay", 2.0),
                                    _ordine("awlq3", "back", 2.0, avg_price_matched=26.0)])
    assert _sorveglia(db, mercato, riga, NOW) == 0
    assert S.evento_chiuso_dall_utente("1.1") is None, "nessun verdetto al buio"
    assert S._CONTO.eventi_in_verifica() == {"1.1"}
    # nessun ordine nuovo del bot sulla partita: il collo di bottiglia di ogni
    # piazzamento (``_execute``) rifiuta SENZA consumare tentativi
    nuova = dict(riga, id=None, status="pending", signal_key="1.1:esatto:altro")
    tid = db.insert_trade(nuova)
    S._PLACE_ATTEMPTS.clear()
    esito = S._execute(db=db, market=mercato, trade_id=tid, row=db.get_trade(tid),
                       params={}, now=NOW, best_size=None, ladder=None)
    assert (esito.status, esito.fill_note) == ("error", "conto_in_verifica")
    assert mercato.placed == []
    chiave = S._place_key("1.1", "1.1:esatto:altro")
    assert int(S._PLACE_ATTEMPTS[chiave]["attempts"]) == 0
    assert S._PLACE_ATTEMPTS[chiave]["final"] is False
    # il DB torna: alla cadenza si sa che e' l'utente -> Safe si ferma
    db.giu = False
    S._CONTO_LETTO_A.clear()
    assert _sorveglia(db, mercato, riga, NOW + timedelta(seconds=31)) == 1
    assert S._CONTO.eventi_in_verifica() == set()


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
