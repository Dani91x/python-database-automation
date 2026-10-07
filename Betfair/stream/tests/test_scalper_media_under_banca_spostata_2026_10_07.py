"""MEDIA UNDER - la banca si SPOSTA, non si ripiazza (07/10/2026, ordine dell'utente).

Testo dell'utente: <<la banca deve aspettare che si abbini il rientro prima di
fare qualsiasi cosa. Pero' non voglio rischiare doppi ordini di banca, quindi
[...] facciamo in modo di MODIFICARE l'ordine banca e spostarlo a seconda dei
rientri effettivamente abbinati>>; <<voglio una soluzione definitiva per questa
banca>>.

Il difetto (dati veri, richiesta 9a30d0a2, evento 35768297; banco, 35797769): al
rientro la banca si annullava, si aspettava che fosse morta, si puntava, si
riappoggiava; se la quota tornava giu' il rientro non partiva e la banca si
rimetteva IDENTICA in fondo alla coda (ping-pong, ~60 s senza banca).

Strategia IDENTICA (soglie, importi, quote, persistenze, TTL, tetti). Cambia
solo la gestione dell'ordine di banca:
  1. condizione di rientro -> punta SUBITO con la banca viva intatta;
  2. finche' la punta di rientro e' viva la banca non si tocca;
  3. a punta terminata con un abbinato: integrazione L - R alla quota nuova, poi
     replace del resto R alla quota nuova (mai la somma delle banche vive oltre
     L); L - R < 1,00: riduzione + integrazione a 1,00; L - R < 0: riduzione;
     replace fallito nel piazzamento: CRITICAL e si ripiazza subito il mancante;
  4. mai due quote diverse oltre lo spostamento, mai copertura oltre la
     posizione, mai una banca annullata e ripiazzata identica;
  5. banca vecchia abbinata per intero durante il rientro: si annulla subito il
     resto della punta; cio' che ha abbinato e' una posizione nuova;
  6. in gioco (pulsante): stessa gestione, col bet delay; nessun marketVersion.

Flumine VERO, strategia VERA, ordini VERI (``banco_media_under.BancoMedia``),
esecuzione differita di 1 e 4 book, regola dei minimi .it del banco montata.
Le invarianti (``BancoMedia.invarianti``) si leggono a OGNI book dagli ordini del
mercato. ASCII-only; commenti in italiano.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest

from Betfair.stream.backtest import minimi_banco as MB
from Betfair.stream.scalper import certificazione as CERT
from Betfair.stream.scalper import media_under_bot as MU
from Betfair.stream.tennis_live.tests.test_cantiere_t_pro_residuo_2026_09_28 import (  # noqa: F401
    esecuzione_differita,
)
from Betfair.stream.tests.banco_media_under import (
    KO_MS, BancoMedia, giri, params_di_serie, violazioni_banche,
)


@pytest.fixture(params=[1, 4])
def differita(request, esecuzione_differita):
    esecuzione_differita.ritardo = request.param
    return esecuzione_differita


@pytest.fixture
def exchange_it():
    with MB.minimi_it_su_flumine() as registro:
        yield registro


# ---------------------------------------------------------------------------
# aiuti (letture dagli ordini VERI del mercato)
# ---------------------------------------------------------------------------
def _punte(b: BancoMedia) -> List[Any]:
    return [o for o in b.ordini() if MU._lato(o) == "BACK"]


def _banche(b: BancoMedia) -> List[Any]:
    return [o for o in b.ordini() if MU._lato(o) == "LAY"]


def _banca_viva(b: BancoMedia) -> Optional[Tuple[float, float]]:
    vive = b.vivi("LAY")
    if not vive:
        return None
    quote = {float(o.order_type.price) for o in vive}
    assert len(quote) == 1, "banche vive a quote diverse: %s" % sorted(quote)
    return (quote.pop(), round(sum(float(o.size_remaining) for o in vive), 2))


def _toccate(b: BancoMedia, banca: Any) -> Dict[str, Any]:
    """Cosa e' successo a QUELLA banca: annullata (resto annullato), spostata
    (un sostituto nel suo Trade), ridotta (annullato una parte e ancora viva)."""
    tr = list(banca.trade.orders)
    annullato = float(getattr(banca, "size_cancelled", 0.0) or 0.0)
    return {"annullata": annullato > 0.004 and tr[-1] is banca and not MU.vivo_o_in_volo(banca),
            "spostata": tr[-1] is not banca,
            "ridotta": annullato > 0.004 and MU.vivo_o_in_volo(banca)}


def _annulli_banca(b: BancoMedia) -> List[Any]:
    return [o for o in _banche(b) if _toccate(b, o)["annullata"]]


def _in_posizione(b: BancoMedia, differita: Any) -> Tuple[List[str], Any]:
    """Riscaldamento e ingresso: punta 10 @1,50 abbinata, banca 10,14 @1,48."""
    viol = giri(b, differita, 70)
    assert _banca_viva(b) == (1.48, 10.14)
    return viol, b.vivi("LAY")[0]


def _punta_di_rientro_appoggiata(b: BancoMedia, differita: Any,
                                 sotto: Tuple[float, float] = (1.51, 1.52)) -> List[str]:
    """La quota sale di 2 tick (1,52): il bot punta il rientro; PRIMA che la
    punta arrivi al mercato la quota torna sotto, cosi' la punta resta
    appoggiata a 1,52 (si abbina solo col volume scambiato a 1,52)."""
    b.ladder[b.under] = (1.52, 1.53)
    viol: List[str] = []
    n = len(b.kinds("media_rientro"))
    for _i in range(40):
        viol += giri(b, differita, 1)
        if len(b.kinds("media_rientro")) > n:
            break
    assert len(b.kinds("media_rientro")) > n, "rientro mai deciso"
    b.ladder[b.under] = sotto
    b.book(flusso=0.0)                          # un book senza esecuzione
    viol += b.invarianti(-1)
    # la punta arriva al mercato (esecuzione differita) e resta appoggiata
    punta = _punte(b)[-1]
    for _i in range(10):
        if MU.eseguibile(punta):
            break
        viol += giri(b, differita, 1, flusso=0.0)
    assert MU.eseguibile(punta) and float(punta.size_matched) == 0.0
    return viol


# ===========================================================================
# 1. rientro abbinato PER INTERO: integrazione + replace, mai un annullo
# ===========================================================================
def test_rientro_per_intero_la_banca_si_sposta_una_volta(differita, exchange_it):
    b = BancoMedia()
    viol, banca = _in_posizione(b, differita)
    b.ladder[b.under] = (1.52, 1.53)
    while not b.kinds("media_rientro"):
        viol += giri(b, differita, 1)
    # nel book del rientro la banca e' INTATTA (stesso ordine, stessa quota, sul book)
    assert MU.eseguibile(banca) and float(banca.order_type.price) == 1.48
    assert float(banca.size_remaining) == pytest.approx(10.14)
    viol += giri(b, differita, 12)
    assert viol == [], viol[:3]
    assert _banca_viva(b) == (1.50, 20.13)
    # la banca vecchia e' stata SPOSTATA (replace: il sostituto nel suo Trade),
    # non annullata; un'integrazione di 9,99 e il resto 10,14 spostato
    assert _toccate(b, banca)["spostata"] and _annulli_banca(b) == []
    sost = list(banca.trade.orders)[-1]
    assert (float(sost.order_type.price), float(sost.order_type.size)) == (1.50, 10.14)
    assert str(sost.order_type.persistence_type) == "PERSIST"
    integr = [p for p in b.kinds("media_banca") if p.get("integrazione")]
    assert [(p["prezzo"], p["importo"], p["totale"], p["resto_vivo"]) for p in integr] == [
        (1.50, 9.99, 20.13, 10.14)]
    # PRIMA l'integrazione, POI il replace (la parte vecchia resta fino allo spostamento)
    kinds = [k for k, _p in b.righe if k in ("media_banca", "media_banca_sposta")]
    assert kinds[-2:] == ["media_banca", "media_banca_sposta"]
    assert len(b.kinds("media_banca_spostata")) == 1
    assert not [p for p in b.kinds("media_annullo") if p.get("side") == "LAY"]


# ===========================================================================
# 2. rientro abbinato IN PARTE: il resto si annulla, la banca non si tocca
#    finche' la punta e' viva, poi si sposta sulla posizione vera
# ===========================================================================
def test_rientro_in_parte_banca_ferma_poi_spostata(differita, exchange_it):
    b = BancoMedia()
    viol, banca = _in_posizione(b, differita)
    viol += _punta_di_rientro_appoggiata(b, differita)
    punta = _punte(b)[-1]
    b.scambia(b.under, 1.52, 1008)              # 500 di coda per lato + 4,00
    vista_viva = 0
    for _i in range(15):
        viol += giri(b, differita, 1, flusso=0.0)
        if MU.vivo_o_in_volo(punta):
            vista_viva += 1
            # la banca NON si tocca finche' la punta di rientro e' viva
            assert MU.vivo_o_in_volo(banca) and not _toccate(b, banca)["spostata"]
            assert float(banca.order_type.price) == 1.48
            assert float(banca.size_remaining) == pytest.approx(10.14)
            assert len(b.vivi("LAY")) == 1
    assert viol == [], viol[:3]
    assert vista_viva >= 1
    assert float(punta.size_matched) == pytest.approx(4.0)
    assert not MU.vivo_o_in_volo(punta)
    resti = [p for p in b.kinds("media_annullo") if p.get("side") == "BACK"]
    assert [str(p["motivo"])[:25] for p in resti] == ["rientro abbinato in parte"]
    pos = b.posizione()
    c = MU.quota_della_banca(1.52, pos, 2)
    assert _banca_viva(b) == (c, MU.al_centesimo(MU.banca_esatta(pos, c)))
    assert _toccate(b, banca)["spostata"] and _annulli_banca(b) == []
    assert b.strat._rientri == 1


# ===========================================================================
# 3. rientro NON abbinato (TTL): la banca intatta, mai ritoccata
# ===========================================================================
def test_rientro_non_abbinato_banca_mai_ritoccata(differita, exchange_it):
    b = BancoMedia()
    viol, banca = _in_posizione(b, differita)
    n_ordini = len(b.ordini())
    viol += _punta_di_rientro_appoggiata(b, differita)
    punta = _punte(b)[-1]
    for _i in range(45):
        viol += giri(b, differita, 1, flusso=0.0)
        assert b.vivi("LAY") == [banca]
        assert float(banca.order_type.price) == 1.48
        assert float(banca.size_remaining) == pytest.approx(10.14)
    assert viol == [], viol[:3]
    assert not MU.vivo_o_in_volo(punta) and float(punta.size_matched) == 0.0
    assert [str(p["motivo"])[:21] for p in b.kinds("media_annullo")] == ["punta non abbinata en"]
    assert len(b.ordini()) == n_ordini + 1                 # solo la punta
    assert _toccate(b, banca) == {"annullata": False, "spostata": False, "ridotta": False}
    assert b.strat._rientri == 0 and b.strat.stato == MU.IN_POSIZIONE


# ===========================================================================
# 4. RIMBALZO sulla soglia ripetuto 10 volte: zero annulli della banca
# ===========================================================================
def test_rimbalzo_sulla_soglia_dieci_volte_zero_annulli_della_banca(differita, exchange_it):
    """Il ping-pong del 07/10 (richiesta 9a30d0a2): la quota tocca la soglia
    del rientro e torna giu' prima che la punta si abbini, 10 volte di fila.
    La banca resta lo STESSO ordine, sempre sul book alla stessa quota."""
    b = BancoMedia()
    viol, banca = _in_posizione(b, differita)
    for giro in range(10):
        viol += _punta_di_rientro_appoggiata(b, differita, sotto=(1.50, 1.51))
        punta = _punte(b)[-1]
        while MU.vivo_o_in_volo(punta):
            viol += giri(b, differita, 1, flusso=0.0)
            assert b.vivi("LAY") == [banca], giro
        assert float(punta.size_matched) == 0.0
    assert viol == [], viol[:3]
    assert len(_punte(b)) == 11                            # ingresso + 10 rientri falliti
    assert _banche(b) == [banca]
    assert _toccate(b, banca) == {"annullata": False, "spostata": False, "ridotta": False}
    assert not [p for p in b.kinds("media_annullo") if p.get("side") == "LAY"]
    assert b.strat._rientri == 0


# ===========================================================================
# 5. la banca vecchia si abbina per intero DURANTE il rientro
# ===========================================================================
def test_banca_abbinata_durante_il_rientro_punta_ritirata_ciclo_chiuso(differita,
                                                                     exchange_it):
    """La punta di rientro e' appoggiata (zero abbinato) e la quota crolla: la
    banca vecchia 10,14 @1,48 si abbina per intero = ciclo chiuso. Il resto
    della punta si annulla SUBITO (non al TTL) e il ciclo si chiude."""
    b = BancoMedia()
    viol, banca = _in_posizione(b, differita)
    viol += _punta_di_rientro_appoggiata(b, differita)
    punta = _punte(b)[-1]
    viol += giri(b, differita, 3, flusso=0.0)
    assert MU.vivo_o_in_volo(punta)
    b.ladder[b.under] = (1.47, 1.48)
    b.scambia(b.under, 1.48, 2000)
    for _i in range(8):
        viol += giri(b, differita, 1, flusso=0.0)
    assert viol == [], viol[:3]
    assert float(banca.size_matched) == pytest.approx(10.14)
    assert not MU.vivo_o_in_volo(punta) and float(punta.size_matched) == 0.0
    motivi = [str(p["motivo"]) for p in b.kinds("media_annullo") if p.get("side") == "BACK"]
    assert motivi and motivi[0].startswith("la banca si e' abbinata per intero")
    chiusi = b.kinds("media_ciclo_chiuso")
    assert len(chiusi) == 1 and chiusi[0]["profitto_lordo"] > 0
    assert b.strat._rientri == 0


def test_banca_abbinata_durante_il_rientro_con_la_punta_gia_abbinata(differita,
                                                                    exchange_it):
    """Nello STESSO book la punta di rientro abbina 4,00 e la banca vecchia si
    abbina per intero: il resto della punta si annulla subito; i 4,00 abbinati
    sono una posizione NUOVA, gestita come sempre sulla posizione vera (banca a
    quota abbinata - tick, sotto la media se serve)."""
    b = BancoMedia()
    viol, banca = _in_posizione(b, differita)
    viol += _punta_di_rientro_appoggiata(b, differita)
    punta = _punte(b)[-1]
    viol += giri(b, differita, 3, flusso=0.0)
    assert MU.vivo_o_in_volo(punta)
    b.scambia(b.under, 1.52, 1008)              # la punta: 500 di coda + 4,00
    b.scambia(b.under, 1.48, 2000)              # la banca: abbinata per intero
    for _i in range(12):
        viol += giri(b, differita, 1, flusso=0.0)
    assert viol == [], viol[:3]
    assert float(banca.size_matched) == pytest.approx(10.14)
    assert float(punta.size_matched) == pytest.approx(4.0)
    assert not MU.vivo_o_in_volo(punta)
    pos = b.posizione()
    c = MU.quota_della_banca(1.52, pos, 2)
    voluto = MU.al_centesimo(MU.banca_esatta(pos, c))
    assert voluto >= 1.0
    assert _banca_viva(b) == (c, voluto)
    assert b.kinds("media_ciclo_chiuso") == []          # la posizione nuova e' aperta
    assert b.strat._rientri == 1 and b.strat.stato == MU.IN_POSIZIONE


# ===========================================================================
# 6. replace FALLITO nella parte di piazzamento
# ===========================================================================
def test_replace_fallito_nel_piazzamento_si_ripiazza_subito_il_mancante(differita,
                                                                        exchange_it):
    """Betfair: <<the cancellations will not be rolled back>>. Il replace
    annulla la banca vecchia ma il piazzamento alla quota nuova e' rifiutato
    (la forma vera del rifiuto di un replace del banco,
    ``trasporto._sostituzione_fallita``). Il bot lo dice UNA volta (CRITICAL) e
    al book dopo ripiazza SUBITO cio' che manca per arrivare a L, alla quota
    nuova. Mai copertura oltre la posizione, mai una banca identica."""
    from Betfair.stream.backtest import trasporto as TRA

    b = BancoMedia()
    viol, banca = _in_posizione(b, differita)
    b.ladder[b.under] = (1.52, 1.53)
    for _i in range(40):
        if banca.status.value == "Replacing":
            break
        viol += giri(b, differita, 1)
    assert banca.status.value == "Replacing"
    with TRA._sostituzione_fallita(banca, "INVALID_ODDS"):
        for _i in range(differita.ritardo):
            differita()
            b.book()
            viol += b.invarianti(-1)
    viol += giri(b, differita, 10)
    assert viol == [], viol[:3]
    assert not MU.vivo_o_in_volo(banca)
    critici = b.kinds("media_banca_spostamento_fallito")
    assert len(critici) == 1 and critici[0]["level"] == "CRITICAL"
    assert _banca_viva(b) == (1.50, 20.13)
    assert violazioni_banche(b.ordini()) == []


# ===========================================================================
# 7. integrazione SOTTO 1,00 e copertura in eccesso (riduzioni)
# ===========================================================================
def test_integrazione_sotto_un_euro_riduzione_e_integrazione_a_un_euro(differita,
                                                                        exchange_it):
    """Il rientro abbina solo 0,30 @1,52: L = 10,30 @1,50, R = 10,14, L - R =
    0,16 (sotto il minimo .it di una banca). La banca si RIDUCE di 0,84 (9,30)
    e l'integrazione sale a 1,00: totale 10,30 al centesimo, nessuna banca
    annullata, mai oltre la posizione."""
    b = BancoMedia()
    viol, banca = _in_posizione(b, differita)
    viol += _punta_di_rientro_appoggiata(b, differita)
    punta = _punte(b)[-1]
    b.scambia(b.under, 1.52, 1000.6)            # 500 di coda per lato + 0,30
    for _i in range(25):
        viol += giri(b, differita, 1, flusso=0.0)
    assert viol == [], viol[:3]
    assert float(punta.size_matched) == pytest.approx(0.30)
    rid = b.kinds("media_banca_ridotta")
    assert [(p["riduzione"], p["prezzo"]) for p in rid] == [(0.84, 1.48)]
    integr = [p for p in b.kinds("media_banca") if p.get("integrazione")]
    assert [(p["prezzo"], p["importo"]) for p in integr] == [(1.50, 1.00)]
    pos = b.posizione()
    assert _banca_viva(b) == (1.50, MU.al_centesimo(MU.banca_esatta(pos, 1.50))) == (1.50, 10.30)
    assert _annulli_banca(b) == []
    assert b.kinds("media_residuo") == []


def test_copertura_in_eccesso_si_riduce_poi_si_sposta(differita, exchange_it):
    """Il rientro abbina solo 0,10 @1,52: L = 10,10 @1,50 e' MENO del resto
    10,14 (caso anomalo). Prima la riduzione di 0,04, poi il replace: mai, in
    nessun istante, la banca oltre la posizione."""
    b = BancoMedia()
    viol, banca = _in_posizione(b, differita)
    viol += _punta_di_rientro_appoggiata(b, differita)
    b.scambia(b.under, 1.52, 1000.2)            # + 0,10
    for _i in range(25):
        viol += giri(b, differita, 1, flusso=0.0)
    assert viol == [], viol[:3]
    rid = b.kinds("media_banca_ridotta")
    assert [(p["riduzione"], p["prezzo"]) for p in rid] == [(0.04, 1.48)]
    assert [p for p in b.kinds("media_banca") if p.get("integrazione")] == []
    assert _banca_viva(b) == (1.50, 10.10)
    assert _annulli_banca(b) == []


def test_integrazione_sotto_un_euro_senza_banca_riducibile_dichiarata(differita,
                                                                       exchange_it):
    """Stake 1,00: banca 1,01 @1,48. Il rientro abbina 0,30: L - R sotto 1,00 e
    la banca (1,01) non regge una riduzione che la lasci sopra 1,00. La parte
    mancante si DICHIARA una volta (CRITICAL) e si sposta solo la banca che c'e'
    (mai sotto il minimo, mai oltre la posizione)."""
    b = BancoMedia(media_stake=1.0)
    viol = giri(b, differita, 70)
    assert _banca_viva(b) == (1.48, 1.01)
    viol += _punta_di_rientro_appoggiata(b, differita)
    b.scambia(b.under, 1.52, 1000.6)            # + 0,30
    for _i in range(25):
        viol += giri(b, differita, 1, flusso=0.0)
    assert viol == [], viol[:3]
    residui = b.kinds("media_residuo")
    assert len(residui) == 1 and residui[0]["level"] == "CRITICAL"
    assert b.kinds("media_banca_ridotta") == []
    assert _banca_viva(b) == (1.50, 1.01)


# ===========================================================================
# 8. IN GIOCO col bet delay (pulsante: gestione identica al pre-match)
# ===========================================================================
def test_in_gioco_col_bet_delay_lo_spostamento_passa_dal_ritardo(esecuzione_differita,
                                                                 exchange_it, monkeypatch):
    """Ciclo avviato col pulsante, in gioco con betDelay 5 (esecuzione differita
    di 6 book): la punta di rientro parte con la banca intatta; a punta
    abbinata integrazione e replace attraversano il ritardo (la banca vecchia
    resta sul mercato fino allo spostamento); mai oltre la posizione, mai due
    quote sul book; nessun marketVersion (la banca PERSIST resta dopo un gol)."""
    import flumine.execution.simulatedexecution as SE
    from flumine.markets.market import Market

    monkeypatch.setattr(SE.time, "sleep", lambda *_a, **_k: None)
    chiamate: List[Tuple[str, Any]] = []
    vero_place, vero_replace = Market.place_order, Market.replace_order

    def _place(self, order, *a, **k):
        chiamate.append(("place", k.get("market_version")))
        return vero_place(self, order, *a, **k)

    def _replace(self, order, new_price, *a, **k):
        chiamate.append(("replace", k.get("market_version", a[0] if a else None)))
        return vero_replace(self, order, new_price, *a, **k)
    monkeypatch.setattr(Market, "place_order", _place)
    monkeypatch.setattr(Market, "replace_order", _replace)
    differita = esecuzione_differita
    differita.ritardo = 1
    b = BancoMedia(media_a_clic=True)
    giri(b, differita, 2)
    # il clic come lo consegna la sessione: ricevuto, registrato, rilasciato
    b.strat.ricevi_comando("c1", float(b.pt), float(b.pt))
    b.strat.rilascia_comando()
    viol = giri(b, differita, 10)
    assert _banca_viva(b) == (1.48, 10.14)
    banca = b.vivi("LAY")[0]
    b.in_gioco()
    b.bet_delay = 5
    differita.ritardo = 6
    viol += giri(b, differita, 8)
    b.ladder[b.under] = (1.52, 1.53)
    rientro_book = None
    for i in range(40):
        viol += giri(b, differita, 1)
        if rientro_book is None and b.kinds("media_rientro"):
            rientro_book = i
        if rientro_book is not None and MU.vivo_o_in_volo(_punte(b)[-1]):
            assert MU.vivo_o_in_volo(banca) and float(banca.order_type.price) == 1.48
    assert viol == [], viol[:3]
    assert rientro_book is not None
    assert _banca_viva(b) == (1.50, 20.13)
    assert _toccate(b, banca)["spostata"] and _annulli_banca(b) == []
    assert ("replace", None) in chiamate
    assert all(v is None for _k, v in chiamate)


# ===========================================================================
# 9. i controlli del banco della banca spostata (M5, M19, M20, M21) sugli
#    ordini VERI: muti sul bot, rossi sui difetti
# ===========================================================================
def _oss(b: BancoMedia, righe: Optional[List[Dict[str, Any]]] = None,
         **kw: Any) -> CERT.OsservazioneMedia:
    if righe is None:
        righe = []
        for i, o in enumerate(b.ordini()):
            r = CERT.riga_media(o)
            r["indice"] = i
            r["creato_ms"] = b.nati[str(o.id)]
            righe.append(r)
    par, _m = MU.leggi_parametri(params_di_serie(b.mercato, **kw.pop("params", {})))
    base = dict(quando="t", ms=b.pt, params=par, mercato_scelto=b.mid,
                tipo_mercato={b.mid: b.mercato}, under=b.under, ordini=righe,
                nuovi=set(), ko_ms=KO_MS, aperto_ora=True)
    base.update(kw)
    return CERT.OsservazioneMedia(**base)


def _codici(oss: CERT.OsservazioneMedia, sol: Optional[Dict[str, int]] = None,
            memoria: Optional[CERT.Memoria] = None) -> List[str]:
    return [v.codice for v in CERT.verifica_media(oss, sol, memoria)]


def test_controlli_della_banca_muti_sul_bot_e_sollecitati(differita, exchange_it):
    b = BancoMedia()
    _in_posizione(b, differita)
    sol: Dict[str, int] = {}
    memoria = CERT.Memoria()
    for q in (1.52, 1.54):
        b.ladder[b.under] = (q, round(q + 0.01, 2))
        for _i in range(12):
            giri(b, differita, 1)
            assert _codici(_oss(b), sol, memoria) == []
    for c in ("M5", "M6", "M19", "M20"):
        assert sol.get(c), (c, sol)


def test_m5_rosso_sulla_copertura_oltre_la_posizione(differita, exchange_it):
    b = BancoMedia()
    _in_posizione(b, differita)
    b.ladder[b.under] = (1.52, 1.53)
    giri(b, differita, 12)
    oss = _oss(b)
    assert "M5" not in _codici(oss)
    righe = [dict(r) for r in oss.ordini]
    vive = [r for r in righe if r["side"] == "LAY" and CERT._m_vivo(r)]
    vive[0]["size_remaining"] = round(vive[0]["size_remaining"] + 0.05, 2)
    assert "M5" in _codici(_oss(b, righe=righe))


def test_m19_rosso_su_due_quote_fuori_dallo_spostamento(differita, exchange_it):
    b = BancoMedia()
    _in_posizione(b, differita)
    b.ladder[b.under] = (1.52, 1.53)
    giri(b, differita, 12)
    righe = [dict(r) for r in _oss(b).ordini]
    vive = [r for r in righe if r["side"] == "LAY" and CERT._m_vivo(r)]
    assert len(vive) == 2
    vive[0]["price"] = 1.48                      # la banca vecchia mai spostata
    memoria = CERT.Memoria()
    codici: List[str] = []
    for _i in range(3):                          # persistente: rosso se si conferma
        codici += _codici(_oss(b, righe=righe), {}, memoria)
    assert "M19" in codici
    # con lo spostamento in volo (Replacing) non e' un difetto
    vive[0]["status"] = "Replacing"
    memoria = CERT.Memoria()
    codici = []
    for _i in range(3):
        codici += _codici(_oss(b, righe=righe), {}, memoria)
    assert "M19" not in codici
    # ... ma mai con una punta sul mercato
    righe.append(dict(next(r for r in righe if r["side"] == "BACK"), order_id="p9",
                      status="Executable", size_remaining=5.0, size_matched=0.0))
    memoria = CERT.Memoria()
    codici = []
    for _i in range(3):
        codici += _codici(_oss(b, righe=righe), {}, memoria)
    assert "M19" in codici


def test_m20_rosso_sulla_banca_annullata_e_ripiazzata_identica(differita, exchange_it):
    b = BancoMedia()
    _in_posizione(b, differita)
    righe = [dict(r) for r in _oss(b).ordini]
    banca = next(r for r in righe if r["side"] == "LAY")
    assert "M20" not in _codici(_oss(b, righe=righe))
    # il difetto del 07/10: la banca annullata (resto annullato, nessun
    # sostituto) e una banca NUOVA identica dopo di lei
    banca.update(status="Execution complete", size_cancelled=10.14, size_remaining=0.0)
    nuova = dict(banca, order_id="b2", indice=99, creato_ms=banca["creato_ms"] + 5000,
                 status="Executable", size_remaining=10.14, size_cancelled=0.0,
                 bet_id="999")
    assert "M20" in _codici(_oss(b, righe=righe + [nuova]))
    # la stessa coppia ma la nuova e' il SOSTITUTO di un replace: non e' un difetto
    nuova["sostituto"] = True
    banca["sostituito"] = True
    assert "M20" not in _codici(_oss(b, righe=righe + [nuova]))


def test_m21_rosso_sulla_posizione_senza_banca_oltre_la_reazione(differita, exchange_it):
    b = BancoMedia()
    _in_posizione(b, differita)
    oss = _oss(b)
    assert CERT.senza_banca(oss) is False           # la banca c'e'
    righe = [dict(r) for r in oss.ordini]
    banca = next(r for r in righe if r["side"] == "LAY")
    banca.update(status="Execution complete", size_cancelled=10.14, size_remaining=0.0)
    senza = _oss(b, righe=righe)
    assert CERT.senza_banca(senza) is True
    # mercato sospeso, in gioco (modalita' di sempre), dopo lo stop: non conta
    assert CERT.senza_banca(_oss(b, righe=righe, aperto_ora=False)) is False
    assert CERT.senza_banca(_oss(b, righe=righe, in_gioco_ms=b.pt - 1)) is False
    assert CERT.senza_banca(_oss(b, righe=righe, force_flat_ms=b.pt - 1)) is False
    sol: Dict[str, int] = {}
    assert "M21" not in _codici(_oss(b, righe=righe, senza_banca_dal_ms=b.pt - 10_000), sol)
    assert sol.get("M21")
    assert "M21" in _codici(_oss(b, righe=righe, senza_banca_dal_ms=b.pt - 16_000))


def test_m4_giudica_il_rientro_sulla_posizione_della_sua_nascita(differita, exchange_it):
    """Dal 07/10 la banca resta viva durante il rientro e puo' abbinarsi DOPO
    che la punta di rientro e' nata. M4 deve rifare la formula sulla posizione
    che il bot aveva quando ha deciso (la fotografia del banco al book del
    piazzamento, ``_Banco.fotografa_abbinati``), non su quella di adesso:
    senza fotografia il rientro giusto sembra sbagliato (falso positivo)."""
    from types import SimpleNamespace

    from Betfair.stream.scalper.tools import replay_registrazioni as R

    b = BancoMedia()
    _viol, banca = _in_posizione(b, differita)
    foto_banco = SimpleNamespace(media_foto_nascita={})
    b.ladder[b.under] = (1.52, 1.53)
    n = 0
    for _i in range(40):
        giri(b, differita, 1)
        if len(b.ordini()) != n:
            # il ponte del replay: un ordine nuovo della modalita' -> fotografia
            R._Banco.fotografa_abbinati(foto_banco, b.strat, b.market)
            n = len(b.ordini())
        if b.kinds("media_rientro"):
            break
    b.ladder[b.under] = (1.51, 1.52)
    b.book(flusso=0.0)
    for _i in range(6):
        giri(b, differita, 1, flusso=0.0)
    punta = _punte(b)[-1]
    assert MU.eseguibile(punta) and float(punta.size_matched) == 0.0
    # la banca vecchia si abbina in parte DOPO la nascita della punta di rientro
    b.ladder[b.under] = (1.48, 1.49)
    b.scambia(b.under, 1.48, 1010)              # 500 di coda per lato + 5,00
    giri(b, differita, 2, flusso=0.0)
    assert float(banca.size_matched) == pytest.approx(5.0)
    assert MU.vivo_o_in_volo(punta)
    con = _oss(b, abbinati_alla_nascita=foto_banco.media_foto_nascita)
    senza = _oss(b)
    assert "M4" not in _codici(con)
    assert "M4" in _codici(senza)


def test_rientro_dovuto_durante_lo_spostamento_aspetta_la_banca(differita, exchange_it):
    """Il rientro 1 si abbina e la banca comincia a spostarsi; la quota e' gia'
    2 tick sopra il nuovo ultimo ingresso (rientro 2 dovuto). La punta del
    rientro 2 aspetta che lo spostamento sia concluso: mai una punta sul
    mercato con le banche a due quote diverse (M19)."""
    b = BancoMedia()
    viol, _banca = _in_posizione(b, differita)
    b.ladder[b.under] = (1.52, 1.53)
    for _i in range(40):
        viol += giri(b, differita, 1)
        if b.kinds("media_banca_sposta"):
            break
    assert b.kinds("media_banca_sposta")
    b.ladder[b.under] = (1.54, 1.55)
    memoria = CERT.Memoria()
    visti_insieme = 0
    for _i in range(20):
        viol += giri(b, differita, 1)
        punte_vive = b.vivi("BACK")
        quote = {float(o.order_type.price) for o in b.vivi("LAY")}
        if punte_vive:
            assert len(quote) == 1, (quote, [float(o.order_type.price) for o in punte_vive])
            visti_insieme += 1
        assert "M19" not in _codici(_oss(b), {}, memoria)
    assert viol == [], viol[:3]
    assert visti_insieme >= 1
    assert [float(o.order_type.size) for o in _punte(b)] == [10.0, 10.0, 20.0]
    assert _banca_viva(b) == (1.52, 40.13)


def test_m20_non_accusa_il_sostituto_di_un_replace(differita, exchange_it):
    """Una banca annullata e, dopo, il SOSTITUTO di un replace di un'altra
    banca alla stessa quota e con lo stesso importo: non e' un ripiazzo (il
    sostituto nasce dentro Betfair dal resto spostato)."""
    b = BancoMedia()
    _in_posizione(b, differita)
    righe = [dict(r) for r in _oss(b).ordini]
    banca = next(r for r in righe if r["side"] == "LAY")
    banca.update(status="Execution complete", size_cancelled=10.14, size_remaining=0.0)
    sost = dict(banca, order_id="b3", indice=98, creato_ms=banca["creato_ms"] + 5000,
                status="Executable", size_remaining=10.14, size_cancelled=0.0,
                bet_id="998", sostituto=True, sostituito=False)
    assert "M20" not in _codici(_oss(b, righe=righe + [sost]))
