# -*- coding: utf-8 -*-
"""D2 / D7 (decisioni dell'utente del 24/09): STATO DEL MERCATO, FRENO CRESCENTE,
RESIDUO DICHIARATO.

D2: "i bot devono leggere lo STATO DEL MERCATO che Betfair comunica (sospeso/
aperto) invece di ritentare alla cieca; vale per tutti i bot; dove non basta,
freno crescente". D7: "il residuo accettato dallo scalper va DICHIARATO".

I finti parlano come il vero (catalogo par.7 difetti 1 e 27): il ``market_book``
e' il ``MarketBook`` VERO di betfairlightweight costruito dalle chiavi di Betfair
(``status``, ``inplay``, ``betDelay``, ``complete``), la ``marketDefinition`` ha
le chiavi camelCase dello stream, gli ordini del blotter hanno gli attributi di
flumine (``size_matched``, ``average_price_matched``, ``side``).

Ogni test dice la regola E il suo contrario (un test che non sa diventare rosso
non certifica). ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import types
from typing import Any, Dict, List, Optional
from unittest import mock

import pytest
from betfairlightweight.resources import MarketBook

from Betfair.stream.trading import freno_rifiuti as FR
from Betfair.stream.trading import stato_mercato as SM


# ---------------------------------------------------------------------------
# finti con le chiavi del vero
# ---------------------------------------------------------------------------
def _mb(status: str = "OPEN", *, inplay: bool = False, bet_delay: int = 0,
        complete: Optional[bool] = True, market_id: str = "1.1",
        publish_ms: int = 1_000_000) -> MarketBook:
    """Il MarketBook VERO di betfairlightweight, dalle chiavi di Betfair."""
    return MarketBook(marketId=market_id, isMarketDataDelayed=False, status=status,
                      betDelay=bet_delay, bspReconciled=False, complete=complete,
                      inplay=inplay, numberOfWinners=1, numberOfRunners=2,
                      numberOfActiveRunners=2, totalMatched=0.0, totalAvailable=0.0,
                      crossMatching=True, runnersVoidable=False, version=1,
                      runners=[], publishTime=publish_ms)


class _Market:
    """Il minimo di un `flumine.markets.market.Market` che i bot usano:
    `market_id`, `market_book`, `blotter`, `place_order(order, **kw) -> bool`."""

    def __init__(self, status: str = "OPEN", accetta: bool = True, **kw: Any) -> None:
        self.market_id = "1.1"
        self.market_book = _mb(status, **kw)
        self.blotter: List[Any] = []
        self.accetta = accetta
        self.piazzati: List[Any] = []

    def place_order(self, order: Any, **_kw: Any) -> bool:
        self.piazzati.append(order)
        if not self.accetta:
            order.violation_msg = "INVALID_ODDS"
            return False
        self.blotter.append(order)
        return True

    def cancel_order(self, order: Any, size_reduction: Any = None) -> bool:
        return True


class _Sink:
    def __init__(self) -> None:
        self.eventi: List[tuple] = []

    def __call__(self, kind: str, payload: Dict[str, Any]) -> None:
        self.eventi.append((kind, payload))

    def di(self, kind: str) -> List[Dict[str, Any]]:
        return [p for k, p in self.eventi if k == kind]


# ===========================================================================
# 1. la guardia unica
# ===========================================================================
@pytest.mark.parametrize("status,atteso", [
    ("OPEN", (True, "OPEN")),
    ("SUSPENDED", (False, "SUSPENDED")),
    ("CLOSED", (False, "CLOSED")),
    ("INACTIVE", (False, "INACTIVE")),
])
def test_guardia_sugli_stati_di_betfair(status, atteso):
    assert SM.mercato_operabile(SM.stato_da_market_book(_mb(status))) == atteso


def test_definizione_incompleta_non_si_piazza_ma_completa_si():
    assert SM.mercato_operabile(SM.stato_da_market_book(_mb("OPEN", complete=False))) \
        == (False, SM.INCOMPLETO)
    assert SM.mercato_operabile(SM.stato_da_market_book(_mb("OPEN", complete=True)))[0]
    # `complete` assente (None) non e' "incompleto"
    assert SM.mercato_operabile(SM.stato_da_market_book(_mb("OPEN", complete=None)))[0]


def test_stato_ignoto_non_blocca_e_si_dichiara():
    """Senza fonte la guardia non inventa ne' un OPEN ne' un SUSPENDED: dice
    IGNOTO e lascia passare (bloccare = spegnere la strategia)."""
    assert SM.mercato_operabile(None) == (True, SM.IGNOTO)
    assert SM.mercato_operabile(SM.stato_da_market_book(None)) == (True, SM.IGNOTO)
    # un finto generico (MagicMock) NON e' uno stato: ignoto, mai "sospeso"
    assert SM.mercato_operabile(SM.stato_da_market_book(mock.MagicMock())) \
        == (True, SM.IGNOTO)
    assert SM.stato_da_riga_scan({"inplay": True}) is SM.STATO_IGNOTO


def test_le_chiavi_della_market_definition_sono_camelcase():
    """Catalogo par.7 difetto 1: la chiave letta nella grafia sbagliata e' un
    bot cieco. `inPlay`/`betDelay` dello stream, non `inplay`/`bet_delay`."""
    st = SM.stato_da_definizione({"status": "SUSPENDED", "inPlay": True,
                                  "betDelay": 5, "complete": True})
    assert (st.status, st.inplay, st.bet_delay, st.complete) == ("SUSPENDED", True, 5, True)
    sbagliata = SM.stato_da_definizione({"status": "OPEN", "inplay": True, "bet_delay": 5})
    assert sbagliata.inplay is None and sbagliata.bet_delay is None
    # dal MarketBook vero: attributi snake_case
    st2 = SM.stato_da_market_book(_mb("SUSPENDED", inplay=True, bet_delay=5))
    assert (st2.status, st2.inplay, st2.bet_delay) == ("SUSPENDED", True, 5)


def test_sospeso_si_aspetta_chiuso_no():
    """Catalogo par.7 difetto 17: sospeso trattato come chiuso o viceversa."""
    assert SM.da_aspettare(SM.SOSPESO) is True
    assert SM.da_aspettare(SM.CHIUSO) is False


def test_attesa_una_riga_per_sospensione_e_di_nuovo_alla_prossima():
    attese = SM.AttesaRiapertura()
    sosp = SM.stato_da_market_book(_mb("SUSPENDED"))
    aperto = SM.stato_da_market_book(_mb("OPEN"))
    esiti = [SM.guardia(sosp, attese, "1.1") for _ in range(50)]
    assert [e[2] for e in esiti].count(True) == 1          # UNA riga
    assert all(e[0] is False for e in esiti)               # nessun invio
    assert SM.guardia(aperto, attese, "1.1") == (True, "OPEN", False)
    # la sospensione successiva si annuncia di nuovo
    assert SM.guardia(sosp, attese, "1.1")[2] is True
    assert attese.annunci == 2


# ===========================================================================
# 2. il freno crescente condiviso
# ===========================================================================
def test_freno_scalper_1_2_4_8_16_poi_30():
    f = FR.FrenoRifiuti(tetto=None, backoff_s=FR.BACKOFF_SCALPER_S,
                        azzera_al_successo=True)
    attese = [f.registra_rifiuto("1.1", 7, 0.0)[1] for _ in range(8)]
    assert attese == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0]
    # nessun tetto: dopo 100 rifiuti si frena, non si spegne
    for _ in range(100):
        f.registra_rifiuto("1.1", 7, 0.0)
    assert "tetto" not in (f.bloccato("1.1", 7, 1.0) or "")
    assert f.bloccato("1.1", 7, 31.0) is None


def test_freno_scalper_azzerato_al_primo_accettato():
    f = FR.FrenoRifiuti(tetto=None, backoff_s=FR.BACKOFF_SCALPER_S,
                        azzera_al_successo=True)
    for _ in range(4):
        f.registra_rifiuto("1.1", 7, 0.0)
    assert f.bloccato("1.1", 7, 5.0) is not None           # 8 s dopo il 4o
    f.registra_successo("1.1", 7)
    assert f.bloccato("1.1", 7, 5.0) is None
    assert f.registra_rifiuto("1.1", 7, 10.0) == (1, 1.0)  # riparte dal primo passo


def test_freno_tennis_non_azzera_il_conteggio_al_successo():
    """La differenza DICHIARATA fra tennis (17/09) e scalper (24/09)."""
    f = FR.FrenoRifiuti()
    for _ in range(3):
        f.registra_rifiuto("1.1", 7, 0.0)
    f.registra_successo("1.1", 7)
    assert f.registra_rifiuto("1.1", 7, 100.0) == (4, 40.0)


# il comportamento del freno tennis PRIMA dello spostamento (17/09), registrato
# dalla classe originale di `condotta_ordini.py` il 24/09 con lo stesso copione
# di `_copione` qui sotto: la parita' e' cifra per cifra.
_BLK = "freno dopo %d rifiuto/i di Betfair: riprovo fra %d s"
_TETTO = ("tetto rifiuti raggiunto su questa selezione (%d): non apro piu' "
          "finche' la partita non finisce")


def _atteso_tennis() -> List[Any]:
    out: List[Any] = []
    back = [5.0, 10.0, 20.0, 40.0, 60.0]
    for i in range(25):
        n = i + 1
        att = back[min(n, 5) - 1]
        out.append(("rif", [n, att]))
        out.append(("blk", _TETTO % n if n >= 20 else _BLK % (n, att - 1)))
        out.append(("ann", True))
        out.append(("ann2", False))
        if i == 3:
            out.append(("blk_after_ok", None))
    out += [("q", 25), ("other", None), ("badsel", [1, 5.0])]
    out += [("t3", [1, 5.0], None), ("t3", [2, 10.0], None),
            ("t3", [3, 20.0], _TETTO % 3), ("t3", [4, 40.0], _TETTO % 4)]
    out.append(("consts", [5.0, 10.0, 20.0, 40.0, 60.0], 20))
    return out


def _copione(CD: Any) -> List[Any]:
    f = CD.FrenoRifiuti()
    out: List[Any] = []
    t = 1000.0
    for i in range(25):
        out.append(("rif", list(f.registra_rifiuto("1.1", 7, t))))
        out.append(("blk", f.bloccato("1.1", 7, t + 1)))
        out.append(("ann", f.da_annunciare("1.1", 7)))
        out.append(("ann2", f.da_annunciare("1.1", 7)))
        if i == 3:
            f.registra_successo("1.1", 7)
            out.append(("blk_after_ok", f.bloccato("1.1", 7, t + 1)))
        t += 100
    out.append(("q", f.quanti("1.1", 7)))
    out.append(("other", f.bloccato("1.1", 8, t)))
    out.append(("badsel", list(f.registra_rifiuto("1.2", "x", 0.0))))
    f3 = CD.FrenoRifiuti(tetto=3)
    for _ in range(4):
        out.append(("t3", list(f3.registra_rifiuto("m", 1, 0.0)), f3.bloccato("m", 1, 999.0)))
    out.append(("consts", list(CD.BACKOFF_S), CD.TETTO_RIFIUTI))
    return out


def test_parita_tennis_dopo_lo_spostamento():
    from Betfair.stream.tennis_scalper import condotta_ordini as CD

    assert CD.FrenoRifiuti is FR.FrenoRifiuti      # UNA classe, non una copia
    assert _copione(CD) == _atteso_tennis()


# ===========================================================================
# 3. lo scalper calcio: guardia, freno, D7
# ===========================================================================
def _scalper(**params: Any) -> Any:
    from Betfair.stream.scalper.scalper_bot import ScalperStrategy

    sink = _Sink()
    s = ScalperStrategy(market_filter={}, scalper_params=params, event_sink=sink)
    s._ora_mercato_ms = 1_000_000
    return s, sink


def test_scalper_a_mercato_sospeso_non_piazza_e_lo_dice_una_volta():
    s, sink = _scalper()
    m = _Market("SUSPENDED", inplay=True, bet_delay=5)
    for _ in range(30):
        assert s._place(m, 7, "BACK", 2.0, 25.0) is None
        assert s._place(m, 7, "LAY", 2.02, 3.0, floor_min=False) is None
    assert m.piazzati == []                                # nessun ordine costruito
    att = sink.di(SM.KIND_ATTESA)
    assert len(att) == 1 and att[0]["motivo"] == "SUSPENDED" and att[0]["aspetta"]
    assert att[0]["bet_delay"] == 5
    assert sink.di("place_rifiutato") == []                # non e' un rifiuto
    assert s._freno.quanti("1.1", 7) == 0                  # e non frena


def test_scalper_senza_prezzi_nessun_ordine_distinto_da_sospeso(monkeypatch):
    """F3 (25/09) - il 4o stato "senza prezzi" (book vuoto/quote assenti, anche
    a mercato OPEN): ``_try_enter`` e' il gate PRIMA di ``_place``/
    ``guardia_flumine`` — un book senza prezzi non arriva MAI a costruire un
    ordine (``_place`` non accetta ``price=None``: solleverebbe). Distinto da
    "sospeso": qui il mercato e' OPEN, e' la LIQUIDITA' che manca."""
    from Betfair.stream.scalper.scalper_bot import _Slot

    s, sink = _scalper()
    m = _Market("OPEN")
    slot = _Slot()
    runner = types.SimpleNamespace(selection_id=7, total_matched=1000.0)
    # nessun prezzo sul book (best_back/best_lay None): il gate ferma qui,
    # PRIMA di ogni _place/guardia_flumine — nessuna eccezione, nessun ordine.
    s._try_enter(m, m.market_book, runner, slot, 1_000_000,
                best_back=None, best_lay=None, size_back=None, size_lay=None, mp=None)
    assert m.piazzati == []
    # e' un caso DIVERSO da "sospeso": nessuna riga attesa_riapertura (il
    # mercato e' OPEN, non sospeso) ne' place_rifiutato (nessun tentativo)
    assert sink.di(SM.KIND_ATTESA) == []
    assert sink.di("place_rifiutato") == []


def test_scalper_alla_riapertura_rivaluta_e_piazza():
    s, sink = _scalper()
    m = _Market("SUSPENDED")
    assert s._place(m, 7, "BACK", 2.0, 25.0) is None
    m.market_book = _mb("OPEN")
    o = s._place(m, 7, "BACK", 2.0, 25.0)
    assert o is not None and m.piazzati == [o]
    assert len(sink.di(SM.KIND_ATTESA)) == 1


def test_scalper_mercato_chiuso_non_si_aspetta():
    s, sink = _scalper()
    m = _Market("CLOSED")
    assert s._place(m, 7, "BACK", 2.0, 25.0) is None
    att = sink.di(SM.KIND_ATTESA)
    assert att and att[0]["motivo"] == "CLOSED" and att[0]["aspetta"] is False


def test_scalper_rifiuto_arma_il_freno_sugli_ingressi():
    s, sink = _scalper()
    m = _Market("OPEN", accetta=False)
    assert s._place(m, 7, "BACK", 2.0, 25.0) is None       # rifiuto 1: 1 s
    assert len(m.piazzati) == 1
    assert sink.di("place_rifiutato")[0]["riprovo_fra_s"] == 1.0
    # nello stesso secondo di mercato l'ingresso NON riparte
    for _ in range(20):
        assert s._place(m, 7, "LAY", 2.02, 25.0) is None
    assert len(m.piazzati) == 1
    assert len(sink.di("freno_rifiuti")) == 1               # detto una volta
    # le USCITE passano sempre
    s._place(m, 7, "LAY", 2.02, 3.0, floor_min=False)
    assert len(m.piazzati) == 2                             # rifiuto 2: 2 s
    s._ora_mercato_ms += 1_500
    assert s._place(m, 7, "BACK", 2.0, 25.0) is None
    assert len(m.piazzati) == 2                             # 1,5 s < 2 s
    s._ora_mercato_ms += 600
    s._place(m, 7, "BACK", 2.0, 25.0)
    assert len(m.piazzati) == 3                             # 2,1 s: riprova
    assert sink.di("place_rifiutato")[-1]["riprovo_fra_s"] == 4.0


def test_scalper_primo_accettato_azzera_il_freno():
    s, sink = _scalper()
    m = _Market("OPEN", accetta=False)
    for _ in range(3):
        s._place(m, 7, "LAY", 2.02, 3.0, floor_min=False)   # 3 rifiuti -> 4 s
    assert s._freno.bloccato("1.1", 7, s._orologio_s()) is not None
    m.accetta = True
    assert s._place(m, 7, "LAY", 2.02, 3.0, floor_min=False) is not None
    assert s._freno.bloccato("1.1", 7, s._orologio_s()) is None
    assert s._place(m, 7, "BACK", 2.0, 25.0) is not None


def test_scalper_freno_usa_il_tempo_di_mercato_non_il_muro():
    s, _ = _scalper()
    s._ora_mercato_ms = 5_000_000
    assert s._orologio_s() == 5_000.0


def test_d7_messaggio_del_residuo():
    from Betfair.stream.scalper.scalper_bot import _msg_residuo

    assert _msg_residuo(-0.10, 0.05) == \
        "posizione NON flat: residuo accettato 0.15 (se vince -0.10, se perde 0.05)"


@pytest.mark.parametrize("tries,kind", [(0, "flatten_residual"),
                                        (13, "flatten_residual_forced")])
def test_d7_i_due_residui_accettati_si_dichiarano(tries, kind):
    from Betfair.stream.scalper.scalper_bot import FLATTENING, _Slot

    s, sink = _scalper()
    m = _Market("OPEN")
    slot = _Slot()
    slot.status = FLATTENING
    slot.flat_tries = tries
    # residuo: -0.10 se vince, +0.05 se perde (ramo 1); -2,00/+0,05 (ramo 2)
    nw, nl = (-0.10, 0.05) if tries == 0 else (-2.0, 0.05)
    with mock.patch.object(type(s), "_net_position", lambda _s, _sl: (nw, nl)), \
            mock.patch.object(type(s), "_flatten", lambda *a, **k: None):
        s._drive_flatten(m, slot, 2.0, 2.02, now=1_000_000)
    ev = sink.di(kind)
    assert len(ev) == 1
    assert ev[0]["msg"].startswith("posizione NON flat: residuo accettato")
    assert "se vince %.2f, se perde %.2f" % (nw, nl) in ev[0]["msg"]


# ---- scalper_session: la dichiarazione dello stato finale ----------------
def _ordine(sel: int, side: str, matched: float, avg: float) -> Any:
    """Gli attributi di un ordine flumine che il blotter espone."""
    return types.SimpleNamespace(market_id="1.1", selection_id=sel, side=side,
                                 size_matched=matched, average_price_matched=avg)


def _framework(ordini: List[Any]) -> Any:
    return types.SimpleNamespace(markets=[types.SimpleNamespace(blotter=ordini)])


def test_sessione_piatta_non_dichiara_niente():
    from Betfair.stream.scalper import scalper_session as SS

    fw = _framework([_ordine(7, "BACK", 10.0, 2.0), _ordine(7, "LAY", 10.0, 2.0)])
    assert SS._dichiarazione_non_flat(fw) is None


def test_sessione_non_piatta_dichiara_e_s3_la_vede():
    from Betfair.stream.scalper import certificazione as CERT
    from Betfair.stream.scalper import scalper_session as SS

    fw = _framework([_ordine(7, "BACK", 10.0, 2.0), _ordine(7, "LAY", 9.0, 2.0)])
    msg = SS._dichiarazione_non_flat(fw)
    assert msg is not None and "1.1/7" in msg
    assert "se vince 1.00, se perde -1.00" in msg
    # il banco riconosce la dichiarazione (S3) ...
    assert CERT.messaggio_dichiara_non_flat(msg)
    # ... e S3 passa SOLO con la dichiarazione (falsificazione nel verso opposto)
    base = dict(fine_sessione=True, stato_finale="done",
                esposizioni={("1.1", 7): (1.0, -1.0)})
    s3 = CERT._FUNZIONI["S3"]
    assert s3(CERT.Osservazione(**base)) is not None
    assert s3(CERT.Osservazione(**base, dichiarato_non_flat=True)) is None


def test_sotto_soglia_0_30_e_piatta():
    from Betfair.stream.scalper import scalper_session as SS

    # sbilancio 0,20 (< 0,30, la soglia di S3): nessuna dichiarazione
    fw = _framework([_ordine(7, "BACK", 10.0, 2.0), _ordine(7, "LAY", 9.9, 2.0)])
    assert SS._dichiarazione_non_flat(fw) is None


def test_blotter_illeggibile_si_dichiara_non_verificabile():
    from Betfair.stream.scalper import scalper_session as SS

    class _Rotto:
        def __iter__(self):
            raise RuntimeError("blotter mutato")

    fw = types.SimpleNamespace(markets=[types.SimpleNamespace(blotter=_Rotto())])
    msg = SS._dichiarazione_non_flat(fw)
    assert msg is not None and "NON flat" in msg


def test_il_banco_riconosce_ancora_le_dichiarazioni_di_prima():
    from Betfair.stream.scalper import certificazione as CERT

    assert CERT.messaggio_dichiara_non_flat("stop: posizione NON flat dopo 30s")
    assert CERT.messaggio_dichiara_non_flat("CRASH thread flumine: sweep")
    assert not CERT.messaggio_dichiara_non_flat("sessione done")


# ===========================================================================
# 4. i quattro bot tennis: guardia su ogni ordine
# ===========================================================================
def _tennis(nome: str) -> Any:
    from betfairlightweight import filters as FL

    mf = FL.streaming_market_filter(market_ids=["1.1"])
    if nome == "flb":
        from Betfair.stream.tennis_scalper.tennis_flb_bot import TennisFLBStrategy
        return TennisFLBStrategy(market_filter=mf, flb_params={"dry_run": False})
    if nome == "pro":
        from Betfair.stream.tennis_scalper.tennis_pro_bot import TennisProStrategy
        return TennisProStrategy(market_filter=mf, pro_params={"dry_run": False},
                                 name_to_sel={})
    if nome == "swing":
        from Betfair.stream.tennis_scalper.tennis_swing_bot import TennisSwingStrategy
        return TennisSwingStrategy(market_filter=mf, swing_params={"dry_run": False})
    from Betfair.stream.tennis_scalper.tennis_scalper_bot import TennisScalperStrategy
    return TennisScalperStrategy(market_filter=mf, scalper_params={"stake": 2.0})


def _piazza_tennis(nome: str, s: Any, m: Any, copertura: bool = False) -> Any:
    if nome == "scalper":
        return s._place(m, 7, "BACK", 2.0, 2.0, floor_min=not copertura)
    return s._place(m, 7, "BACK", 2.0, 2.0, copertura=copertura)


@pytest.mark.parametrize("nome", ["flb", "pro", "swing", "scalper"])
def test_tennis_sospeso_nessun_ordine_una_riga_e_riapertura(nome):
    s = _tennis(nome)
    sink = _Sink()
    s.event_sink = sink
    m = _Market("SUSPENDED", inplay=True, bet_delay=5)
    for cop in (False, True) * 10:
        assert _piazza_tennis(nome, s, m, cop) is None
    assert m.piazzati == []
    assert len(sink.di(SM.KIND_ATTESA)) == 1
    assert s._freno.quanti("1.1", 7) == 0                  # non e' un rifiuto
    m.market_book = _mb("OPEN", inplay=True, bet_delay=5)
    assert _piazza_tennis(nome, s, m) is not None
    assert len(m.piazzati) == 1


# ===========================================================================
# 5. il worker del runner e il place-and-trim
# ===========================================================================
def test_worker_mercato_sospeso_rifiuto_pre_place_senza_diario():
    from Betfair.stream import live_order_worker as LOW

    m = _Market("SUSPENDED")
    diario = []
    with mock.patch.object(LOW, "_chiama_pre_invio",
                           lambda *a, **k: diario.append(a)):
        with pytest.raises(ValueError) as ex:
            LOW._place_or_raise(m, types.SimpleNamespace(violation_msg=None), "place")
    assert "mercato non operabile (SUSPENDED)" in str(ex.value)
    assert "post_place" not in str(ex.value)               # PRE-place: nulla e' partito
    assert m.piazzati == [] and diario == []


def test_worker_mercato_aperto_piazza_come_prima():
    from Betfair.stream import live_order_worker as LOW

    m = _Market("OPEN")
    with mock.patch.object(LOW, "_chiama_pre_invio", lambda *a, **k: None):
        LOW._place_or_raise(m, types.SimpleNamespace(violation_msg=None), "place")
    assert len(m.piazzati) == 1


def test_worker_senza_book_decide_flumine_come_oggi():
    from Betfair.stream import live_order_worker as LOW

    m = _Market("OPEN")
    m.market_book = None
    with mock.patch.object(LOW, "_chiama_pre_invio", lambda *a, **k: None):
        LOW._place_or_raise(m, types.SimpleNamespace(violation_msg=None), "place")
    assert len(m.piazzati) == 1


def test_submin_park_non_parte_a_mercato_sospeso():
    from Betfair.stream.trading.submin import FlumineSubminOps

    s, _ = _scalper()
    ops = FlumineSubminOps(selection_id=7, handicap=0.0, jurisdiction="it", strategy=s)
    m = _Market("SUSPENDED")
    with pytest.raises(ValueError) as ex:
        ops.place(m, side="lay", price=1.01, size=2.0, customer_order_ref="x1")
    assert "mercato non operabile" in str(ex.value) and m.piazzati == []
    m.market_book = _mb("OPEN")
    ops.place(m, side="lay", price=1.01, size=2.0, customer_order_ref="x2")
    assert len(m.piazzati) == 1
