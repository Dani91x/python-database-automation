"""MEDIA UNDER, quarto giro (06/10/2026): decisioni dell'utente su P1 e P13.

* P1 (a): lo STOP della sessione lascia appoggiata la banca PERSIST della
  modalita' (la posizione resta protetta e si chiude da sola).
* P13: dopo un crash / una caduta di rete la modalita' in SOLDI VERI riprende
  ESATTAMENTE da dove era, senza errori e senza operazioni doppie, leggendo il
  conto (in prova niente: la persistenza serve in soldi veri).
* In piu' (scelta dell'utente): ogni strategia della sessione ha un nome legato
  alla PARTITA (prima la classe: una sessione in soldi veri riadottava, e
  all'arresto annullava, gli ordini delle sessioni delle altre partite).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from Betfair.stream.backtest import minimi_banco as MB
from Betfair.stream.scalper import media_under_bot as MU
from Betfair.stream.scalper import scalper_session as SS
from Betfair.stream.scalper.tools import replay_registrazioni as R
from Betfair.stream.tennis_live.tests.test_cantiere_t_pro_residuo_2026_09_28 import (  # noqa: F401
    esecuzione_differita,
)
from Betfair.stream.tests.banco_media_under import EVENTO, KO_MS, BancoMedia, giri


@pytest.fixture(params=[1, 4])
def differita(request, esecuzione_differita):
    """Esecuzione dei pacchetti di flumine differita di 1 e di 4 book."""
    esecuzione_differita.ritardo = request.param
    return esecuzione_differita


@pytest.fixture
def exchange_it():
    with MB.minimi_it_su_flumine() as registro:
        yield registro


@pytest.fixture
def soldi_veri_dichiarati():
    from Betfair.stream.backtest.certifica import _freni_da_banco

    with _freni_da_banco():
        yield


def _catalogo():
    defs = {
        "1.300000001": {"market_type": "MATCH_ODDS", "runners": [(11, 1), (12, 2), (58805, 3)]},
        "1.300000025": {"market_type": "OVER_UNDER_25", "runners": [(47972, 1), (47973, 2)]},
        "1.300000035": {"market_type": "OVER_UNDER_35", "runners": [(1222344, 1), (1222345, 2)]},
    }
    follow = {"event_id": EVENTO, "fixture_id": None, "league_id": None,
              "home_name": "A", "away_name": "B", "open_date": "2025-09-29T10:00:00.000Z"}
    return R.catalogo_dal_raw(defs), follow


# ===========================================================================
# A. il nome di ogni strategia e' legato alla partita
# ===========================================================================
def test_nome_strategia_per_partita_e_ruolo():
    assert SS.nome_strategia("maker", "35797769") == "scm35797769"
    assert SS.nome_strategia("sniper", "35797769") == "scn35797769"
    assert SS.nome_strategia("theta", "35797769") == "sct35797769"
    assert SS.nome_strategia("media", "35797769") == "mu35797769"
    # e' anche il customerStrategyRef: al piu' 15 caratteri, diverso per partita
    assert len(SS.nome_strategia("maker", "123456789012345")) == 15
    nomi = {SS.nome_strategia(r, e) for r in SS.PREFISSI_STRATEGIA
            for e in ("35797769", "35760084")}
    assert len(nomi) == 8


@pytest.mark.usefixtures("soldi_veri_dichiarati")
@pytest.mark.parametrize("scenario, ruolo", [("base", "maker"), (R.SCENARIO_MEDIA, "media")])
def test_la_sessione_arma_le_strategie_col_nome_della_partita(scenario, ruolo):
    import hashlib

    cat, follow = _catalogo()
    par, _cli = R.arma_e_cattura(EVENTO, R.control_della_ui(EVENTO, scenario), follow, cat)
    nome = SS.nome_strategia(ruolo, EVENTO)
    assert par["_name"] == nome
    # l'hash con cui flumine riadotta gli ordini dal conto e' quello del nome
    assert par["name_hash"] == hashlib.sha1(nome.encode("utf-8")).hexdigest()[:13]


# ===========================================================================
# B. P1: lo STOP lascia appoggiata la banca PERSIST della modalita'
# ===========================================================================
def _banche(b: BancoMedia) -> List[Any]:
    return [o for o in b.ordini() if MU._lato(o) == "LAY"]


def _punte(b: BancoMedia) -> List[Any]:
    return [o for o in b.ordini() if MU._lato(o) == "BACK"]


class _Tempo:
    """L'orologio e il sonno dell'annullo all'arresto sul banco di prova: ogni
    <<sonno>> fa passare un book (il simulatore esegue gli annulli)."""

    def __init__(self, b: BancoMedia, svuota: Any) -> None:
        self.b, self.svuota, self.t = b, svuota, 0.0

    def ora(self) -> float:
        return self.t

    def dormi(self, s: float) -> None:
        self.t += float(s)
        giri(self.b, self.svuota, 1)


def _db() -> Any:
    ctl = {"event_id": EVENTO, "status": "running", "params": {}}
    return R._DbFinto(R._Orologio(), ctl, {"event_id": EVENTO})


def test_stop_con_la_banca_viva_la_banca_resta(differita, exchange_it):
    b = BancoMedia()
    viol = giri(b, differita, 70)
    banca = b.vivi("LAY")[0]
    b.strat.force_flat = True
    viol += giri(b, differita, 3)
    assert viol == [], viol[:3]
    assert b.strat.pronta_allo_stop() is True
    assert b.strat.banca_da_lasciare(banca) is True
    t = _Tempo(b, differita)
    db = _db()
    esito = SS.chiudi_all_arresto(db, EVENTO, b.fw, None, True, "stop_app", flumine_vivo=True,
                                  timeout_s=5.0, ora=t.ora, dormi=t.dormi,
                                  da_lasciare=b.strat.banca_da_lasciare)
    # (il banco di prova lascia EXECUTABLE la punta gia' abbinata per intero: lo
    # stream simulato degli ordini non gira; il suo annullo non tocca niente)
    assert esito["lasciati"] == 1
    assert esito["vivi_dopo"] == 0
    giri(b, differita, 6)
    assert b.vivi("LAY") == [banca] and MU.vivo_o_in_volo(banca)
    avvisi = db.tabelle.get("live_alerts", [])
    assert any("banca PERSIST di chiusura lasciata appoggiata" in a["message"]
               for a in avvisi), avvisi


def test_stop_senza_la_regola_la_banca_si_annulla(differita, exchange_it):
    """La regola di prima (nessun ``da_lasciare``): la banca viene annullata."""
    b = BancoMedia()
    giri(b, differita, 70)
    banca = b.vivi("LAY")[0]
    b.strat.force_flat = True
    giri(b, differita, 3)
    t = _Tempo(b, differita)
    esito = SS.chiudi_all_arresto(_db(), EVENTO, b.fw, None, True, "stop_app",
                                  flumine_vivo=True, timeout_s=5.0, ora=t.ora,
                                  dormi=t.dormi)
    assert esito["lasciati"] == 0 and esito["annullo_chiesto"] >= 1
    giri(b, differita, 6)
    assert not MU.vivo_o_in_volo(banca)


def test_stop_durante_un_rientro_la_punta_si_ritira_e_la_banca_copre_tutto(differita,
                                                                            exchange_it):
    """Stop con la punta di rientro abbinata in parte (4 su 10): la punta si
    ritira, la banca copre l'INTERA posizione (14 puntati), poi resta."""
    b = BancoMedia()
    giri(b, differita, 70)
    b.taglie[(b.under, 1.52)] = 4.0
    b.ladder[b.under] = (1.52, 1.53)
    for _i in range(30):
        giri(b, differita, 1, flusso=0.0)
        if len(_punte(b)) == 2 and MU.vivo_o_in_volo(_punte(b)[1]):
            break
    b.strat.force_flat = True
    viol = giri(b, differita, 15, flusso=0.0)
    assert viol == [], viol[:3]
    punta = _punte(b)[1]
    assert not MU.vivo_o_in_volo(punta)
    pos = b.posizione()
    vive = b.vivi("LAY")
    assert len(vive) == 1
    c = MU.quota_della_banca(b.strat._ultimo_ingresso, pos, 2)
    assert (float(vive[0].order_type.price), float(vive[0].size_remaining)) == (
        c, MU.al_centesimo(MU.banca_esatta(pos, c)))
    assert b.strat.pronta_allo_stop() is True
    # nessuna punta nuova dopo lo stop
    assert len(_punte(b)) == 2


def test_stop_non_pronto_finche_la_punta_e_viva(differita, exchange_it):
    b = BancoMedia()
    giri(b, differita, 70)
    b.ladder[b.under] = (1.52, 1.53)
    for _i in range(30):
        giri(b, differita, 1, flusso=0.0)
        if len(_punte(b)) == 2 and MU.vivo_o_in_volo(_punte(b)[1]):
            break
    assert b.strat.pronta_allo_stop() is False


class _BettingCrash:
    """``trading.betting`` con le firme vere usate dallo sweep: risponde a
    ``list_current_orders`` con gli ordini VERI del banco come ``CurrentOrder``
    di betfairlightweight e registra ogni ``cancel_orders``."""

    def __init__(self, b: BancoMedia) -> None:
        self.b = b
        self.annulli: List[Dict[str, Any]] = []

    def list_current_orders(self, market_ids=None, **_kw):
        from betfairlightweight.resources.bettingresources import CurrentOrders

        righe = [_ordine_corrente(o) for o in self.b.ordini()]
        return CurrentOrders(currentOrders=righe, moreAvailable=False)

    def cancel_orders(self, market_id=None, instructions=None, **_kw):
        self.annulli.append({"market_id": market_id, "instructions": instructions})


class _TradingCrash:
    def __init__(self, b: BancoMedia) -> None:
        self.betting = _BettingCrash(b)


def _ordine_corrente(o: Any) -> Dict[str, Any]:
    """Un ordine flumine come riga di ``listCurrentOrders`` (chiavi della API
    Betfair, quelle che betfairlightweight legge)."""
    m = float(o.size_matched or 0.0)
    resto = float(o.size_remaining or 0.0)
    return {
        "betId": str(o.bet_id), "marketId": o.market_id, "selectionId": o.selection_id,
        "handicap": 0.0, "priceSize": {"price": float(o.order_type.price),
                                       "size": float(o.order_type.size)},
        "bspLiability": 0.0, "side": o.side, "orderType": "LIMIT",
        "status": "EXECUTABLE" if MU.vivo_o_in_volo(o) else "EXECUTION_COMPLETE",
        "persistenceType": str(o.order_type.persistence_type),
        "placedDate": "2025-09-29T09:00:00.000Z",
        "averagePriceMatched": float(o.average_price_matched or 0.0),
        "sizeMatched": m, "sizeRemaining": resto, "sizeLapsed": 0.0,
        "sizeCancelled": float(getattr(o, "size_cancelled", 0.0) or 0.0),
        "sizeVoided": 0.0, "regulatorCode": "MR_INT",
        "customerOrderRef": o.customer_order_ref,
        "customerStrategyRef": str(o.trade.strategy)[:15],
    }


def test_crash_di_flumine_in_soldi_veri_lo_sweep_non_tocca_la_banca(differita, exchange_it):
    b = BancoMedia()
    giri(b, differita, 70)
    banca = b.vivi("LAY")[0]
    tr = _TradingCrash(b)
    db = _db()
    SS._handle_flumine_crash(db, EVENTO, tr, [b.mid], False, framework=b.fw,
                             da_lasciare=b.strat.banca_da_lasciare)
    tolti = [i["betId"] for a in tr.betting.annulli for i in (a["instructions"] or [])]
    assert str(banca.bet_id) not in tolti
    # mai il ripiego market-wide (che toglierebbe anche la banca)
    assert all(a["instructions"] for a in tr.betting.annulli)
    righe = db.attivita("error")
    assert righe and righe[-1]["payload"]["sweep"].get("lasciati") == [str(banca.bet_id)]


def test_crash_senza_la_regola_lo_sweep_toglie_la_banca(differita, exchange_it):
    b = BancoMedia()
    giri(b, differita, 70)
    banca = b.vivi("LAY")[0]
    tr = _TradingCrash(b)
    SS._handle_flumine_crash(_db(), EVENTO, tr, [b.mid], False, framework=b.fw)
    tolti = [i["betId"] for a in tr.betting.annulli for i in (a["instructions"] or [])]
    assert str(banca.bet_id) in tolti


# ===========================================================================
# C. P13: la ripresa in soldi veri dal conto, senza errori e senza doppi
# ===========================================================================
NOME = SS.nome_strategia("media", EVENTO)


def _correnti(ordini: List[Any]) -> Any:
    """Gli ordini come risposta VERA di ``listCurrentOrders`` / immagine dello
    stream degli ordini (``CurrentOrders`` di betfairlightweight)."""
    from betfairlightweight.resources.bettingresources import CurrentOrders

    return CurrentOrders(currentOrders=[_ordine_corrente(o) for o in ordini],
                         moreAvailable=False)


def _righe_del_conto(b: BancoMedia) -> List[Dict[str, Any]]:
    """Quello che ``scalper_session.leggi_ordini_media_dal_conto`` consegna."""
    return [MU.riga_dal_conto(o) for o in _correnti(b.ordini()).orders]


def _rinasce(b1: BancoMedia, **params: Any) -> BancoMedia:
    """Il processo NUOVO dopo il crash: flumine nuovo, strategia nuova con lo
    STESSO nome (stessa partita), lo stesso mercato allo stesso istante."""
    b2 = BancoMedia(nome=NOME, **params)
    b2.pt = b1.pt
    b2.ladder = dict(b1.ladder)
    b2.taglie = dict(b1.taglie)
    b2.trd = {k: dict(v) for k, v in b1.trd.items()}
    return b2


def _adotta(b2: BancoMedia, ordini: List[Any]) -> None:
    """L'immagine dello stream degli ordini del conto passa da flumine VERO
    (``BaseFlumine._process_current_orders`` -> ``create_order_from_current``):
    gli ordini col ``name_hash`` della strategia entrano nel suo blotter."""
    from flumine.events.events import CurrentOrdersEvent

    co = _correnti(ordini)
    co.client = b2.client
    b2.fw._process_current_orders(CurrentOrdersEvent([co]))


def _posizione_uguale(a: MU.Posizione, b: MU.Posizione) -> None:
    assert a.puntato == pytest.approx(b.puntato)
    assert a.se_vince == pytest.approx(b.se_vince)
    assert a.se_perde == pytest.approx(b.se_perde)


def test_ripresa_con_la_banca_viva_riprende_esattamente(differita, exchange_it):
    """Crash con 10 @1,50 abbinati e un rientro 10 @1,52 abbinato (banca
    20,13 @1,50 viva). Il processo nuovo legge il conto, riadotta la banca e
    ricostruisce il ciclo: stessi rientri, ultimo ingresso, obiettivo e banca.
    Poi la quota sale di 2 tick: il resumed fa la STESSA mossa del processo
    che non si e' mai fermato (stesso rientro, stessa quota)."""
    b1 = BancoMedia(nome=NOME)
    viol = giri(b1, differita, 70)
    b1.ladder[b1.under] = (1.52, 1.53)
    viol += giri(b1, differita, 15)
    assert viol == [] and b1.strat.stato == MU.IN_POSIZIONE and b1.strat._rientri == 1
    banca1 = b1.vivi("LAY")[0]
    # ---- crash: nasce il processo nuovo
    b2 = _rinasce(b1)
    b2.strat.prepara_ripresa(_righe_del_conto(b1))
    assert b2.strat.stato == MU.RIPRESA
    giri(b2, differita, 3)
    assert b2.strat.stato == MU.RIPRESA and b2.ordini() == []   # nessun ordine
    _adotta(b2, [o for o in b1.ordini() if MU.vivo_o_in_volo(o)])
    giri(b2, differita, 2)
    s1, s2 = b1.strat, b2.strat
    assert s2.stato == MU.IN_POSIZIONE
    assert (s2._rientri, s2._ultimo_ingresso) == (s1._rientri, s1._ultimo_ingresso)
    assert s2._t_lordo == pytest.approx(s1._t_lordo)
    _posizione_uguale(MU.posizione_da_ordini(s2._ordini), b1.posizione())
    assert s2._banca is not None and str(s2._banca.bet_id) == str(banca1.bet_id)
    # nessun ordine nuovo: solo quelli riadottati
    assert [str(o.bet_id) for o in b2.ordini()] == [str(banca1.bet_id)]
    rip = [p for p in b2.kinds("media_ripresa") if p.get("ordini")]
    assert len(rip) == 1 and rip[0]["stato"] == MU.IN_POSIZIONE
    # ---- la quota sale di 2 tick in tutti e due: stessa mossa
    for b in (b1, b2):
        b.ladder[b.under] = (1.54, 1.55)
    n1, n2 = len(b1.ordini()), len(b2.ordini())
    giri(b1, differita, 12)
    giri(b2, differita, 12)
    nuovi1 = [(MU._lato(o), float(o.order_type.price), float(o.order_type.size))
              for o in b1.ordini()[n1:]]
    nuovi2 = [(MU._lato(o), float(o.order_type.price), float(o.order_type.size))
              for o in b2.ordini()[n2:]]
    assert nuovi1 and nuovi1[0] == ("BACK", 1.54, 20.0)
    assert nuovi2[:1] == nuovi1[:1]


def test_ripresa_senza_adozione_nessun_ordine_poi_bloccata(differita, exchange_it):
    """Il conto dice che c'e' una banca viva ma flumine non la riadotta: mai un
    ordine (niente ingresso doppio, anche col mercato buono per entrare), dopo
    l'attesa BLOCCATA con l'avviso."""
    b1 = BancoMedia(nome=NOME)
    giri(b1, differita, 70)
    b2 = _rinasce(b1)
    b2.strat.prepara_ripresa(_righe_del_conto(b1))
    giri(b2, differita, int(MU.ATTESA_RIPRESA_MS / 1000) + 5)
    assert b2.ordini() == []
    assert b2.strat.stato == MU.BLOCCATA
    fallite = b2.kinds("media_ripresa_fallita")
    assert len(fallite) == 1 and fallite[0]["level"] == "CRITICAL"
    giri(b2, differita, 10)
    assert b2.ordini() == []


def test_ripresa_ordini_chiusi_solo_dal_conto(differita, exchange_it):
    """Lo stream riadotta solo gli ordini VIVI: le punte gia' abbinate per
    intero si leggono dal conto (``OrdineDelConto``) e contano nella posizione
    una volta sola, anche se poi lo stream le consegna."""
    b1 = BancoMedia(nome=NOME)
    giri(b1, differita, 70)
    b1.ladder[b1.under] = (1.52, 1.53)
    giri(b1, differita, 15)
    b2 = _rinasce(b1)
    b2.strat.prepara_ripresa(_righe_del_conto(b1))
    _adotta(b2, [o for o in b1.ordini() if MU.vivo_o_in_volo(o)])
    giri(b2, differita, 2)
    conto = [o for o in b2.strat._ordini if isinstance(o, MU.OrdineDelConto)]
    assert len(conto) >= 2           # le due punte abbinate
    _posizione_uguale(MU.posizione_da_ordini(b2.strat._ordini), b1.posizione())


# (un ordine gia' CHIUSO riadottato dallo stream non si prova qui: il flumine di
# prova e' simulato e un ordine riadottato prende i campi del simulatore, che non
# lo ha mai piazzato; in soldi veri flumine legge stato e resto dal conto.
# Referto del giro 4, punto non verificato.)


def test_ripresa_dopo_un_ciclo_chiuso_conta_i_cicli(differita, exchange_it):
    b1 = BancoMedia(nome=NOME)
    giri(b1, differita, 70)
    b1.ladder[b1.under] = (1.47, 1.48)
    b1.scambia(b1.under, 1.48, 2000)
    giri(b1, differita, 10)
    assert b1.strat.stats["cicli_chiusi"] == 1 and b1.strat.stato == MU.IN_POSIZIONE
    b2 = _rinasce(b1)
    b2.strat.prepara_ripresa(_righe_del_conto(b1))
    _adotta(b2, [o for o in b1.ordini() if MU.vivo_o_in_volo(o)])
    giri(b2, differita, 2)
    s1, s2 = b1.strat, b2.strat
    assert s2.stats["cicli_chiusi"] == 1
    assert s2.stats["pnl_chiuso_lordo"] == pytest.approx(s1.stats["pnl_chiuso_lordo"], abs=1e-4)
    assert s2.stato == MU.IN_POSIZIONE and s2._rientri == 0
    _posizione_uguale(MU.posizione_da_ordini(s2._ordini), MU.posizione_da_ordini(s1._ordini))


def test_ripresa_al_massimo_dei_rientri_resta_al_massimo(differita, exchange_it):
    b1 = BancoMedia(nome=NOME, media_max_rientri=1)
    giri(b1, differita, 70)
    b1.ladder[b1.under] = (1.52, 1.53)
    giri(b1, differita, 15)
    assert b1.strat.stato == MU.MASSIMO
    b2 = _rinasce(b1, media_max_rientri=1)
    b2.strat.prepara_ripresa(_righe_del_conto(b1))
    _adotta(b2, [o for o in b1.ordini() if MU.vivo_o_in_volo(o)])
    giri(b2, differita, 2)
    assert b2.strat.stato == MU.MASSIMO
    b2.ladder[b2.under] = (1.56, 1.57)
    n = len(b2.ordini())
    giri(b2, differita, 15)
    assert [o for o in b2.ordini()[n:] if MU._lato(o) == "BACK"] == []
    assert b2.kinds("media_massimo") == []        # gia' detto dal processo morto


def test_ripresa_conto_vuoto_parte_da_zero(differita, exchange_it):
    b2 = BancoMedia(nome=NOME)
    b2.strat.prepara_ripresa([])
    assert b2.strat.stato == MU.FERMO
    giri(b2, differita, 70)
    assert len(b2.ordini()) == 2          # ingresso + banca, come una sessione nuova


def test_ripresa_conto_non_letto_nessun_ordine_poi_riprova(differita, exchange_it):
    b1 = BancoMedia(nome=NOME)
    giri(b1, differita, 70)
    b2 = _rinasce(b1)

    class _Rotto:
        class betting:  # noqa: N801 - la forma di ``trading.betting``
            @staticmethod
            def list_current_orders(**_kw):
                raise RuntimeError("rete giu'")

    assert SS.prepara_ripresa_media(_Rotto, b2.strat, EVENTO) == "non letto"
    assert b2.strat.attende_il_conto() is True
    giri(b2, differita, 20)
    assert b2.ordini() == [] and b2.strat.stato == MU.RIPRESA
    assert b2.kinds("media_ripresa_in_attesa")

    class _Buono:
        class betting:  # noqa: N801
            @staticmethod
            def list_current_orders(**kw):
                assert kw["customer_strategy_refs"] == [NOME]
                return _correnti(b1.ordini())

    assert SS.prepara_ripresa_media(_Buono, b2.strat, EVENTO) == "letti 2"
    assert b2.strat.attende_il_conto() is False
    _adotta(b2, [o for o in b1.ordini() if MU.vivo_o_in_volo(o)])
    giri(b2, differita, 2)
    assert b2.strat.stato == MU.IN_POSIZIONE


def test_lettura_del_conto_paginata_e_filtrata_sulla_partita():
    from betfairlightweight.resources.bettingresources import CurrentOrders

    pagine = []

    class _Betting:
        @staticmethod
        def list_current_orders(**kw):
            pagine.append(kw)
            riga = {"betId": str(len(pagine)), "marketId": "1.1", "selectionId": 47972,
                    "handicap": 0.0, "priceSize": {"price": 1.5, "size": 10.0},
                    "bspLiability": 0.0, "side": "BACK", "orderType": "LIMIT",
                    "status": "EXECUTION_COMPLETE", "persistenceType": "LAPSE",
                    "placedDate": "2025-09-29T09:00:00.000Z", "averagePriceMatched": 1.5,
                    "sizeMatched": 10.0, "sizeRemaining": 0.0, "sizeLapsed": 0.0,
                    "sizeCancelled": 0.0, "sizeVoided": 0.0,
                    "customerOrderRef": "x-1", "customerStrategyRef": NOME}
            return CurrentOrders(currentOrders=[riga], moreAvailable=len(pagine) < 3)

    class _Trading:
        betting = _Betting

    righe = SS.leggi_ordini_media_dal_conto(_Trading, NOME)
    assert [r["bet_id"] for r in righe] == ["1", "2", "3"]
    assert [p["from_record"] for p in pagine] == [0, 1, 2]
    assert all(p["customer_strategy_refs"] == [NOME] for p in pagine)
    assert righe[0]["side"] == "BACK" and righe[0]["size_matched"] == 10.0


def test_stop_durante_la_ripresa_lascia_la_banca_riadottata(differita, exchange_it):
    b1 = BancoMedia(nome=NOME)
    giri(b1, differita, 70)
    b2 = _rinasce(b1)
    b2.strat.prepara_ripresa(_righe_del_conto(b1))
    # la banca riadottata, la posizione non ancora ricostruita
    _adotta(b2, [o for o in b1.ordini() if MU.vivo_o_in_volo(o)])
    adottata = [o for o in b2.ordini() if MU._lato(o) == "LAY"][0]
    assert b2.strat.stato == MU.RIPRESA
    assert b2.strat.banca_da_lasciare(adottata) is True


# ===========================================================================
# D. il banco del replay: la lettura del conto e l'adozione al riavvio
# ===========================================================================
def _banco_su(b: BancoMedia, dry_run: bool = False) -> Any:
    from Betfair.stream.backtest import banco_comune as BC
    from Betfair.stream.scalper import certificazione as CERT
    from Betfair.stream.tests.banco_media_under import params_di_serie

    orologio = R._Orologio()
    ctl = {"event_id": EVENTO, "status": "running", "mode": "maker", "dry_run": dry_run,
           "stake": 25, "params": params_di_serie()}
    db = R._DbFinto(orologio, ctl, {"event_id": EVENTO})
    ref = CERT.Referto(event_id=EVENTO, scenario=R.SCENARIO_MEDIA)
    with BC.simulazione_flumine():
        banco = R._Banco(event_id=EVENTO, raw="", scenario=R.SCENARIO_MEDIA, ogni_ms=0,
                         referto=ref, orologio=orologio, db=db, catalogo=[], ko_ms=KO_MS)
    banco.quadro = b.fw
    banco.mercati_catalogo = [b.mid]
    banco.media, banco.medie = b.strat, [b.strat]
    banco.media_mercato_scelto, banco.media_under = b.mid, b.under
    banco.tipo_mercato = {b.mid: b.mercato}
    return banco


def test_il_banco_risponde_al_conto_come_betfair_e_simula_l_adozione(differita, exchange_it):
    from betfairlightweight import filters

    b = BancoMedia(nome=NOME)
    giri(b, differita, 70)
    banco = _banco_su(b)
    betting = R._BettingFinto(banco)
    r = betting.list_current_orders(customer_strategy_refs=[NOME])
    righe = [MU.riga_dal_conto(o) for o in r.orders]
    assert sorted(x["side"] for x in righe) == ["BACK", "LAY"]
    assert {x["status"] for x in righe} == {"EXECUTABLE", "EXECUTION_COMPLETE"}
    assert betting.list_current_orders(customer_strategy_refs=["altra"]).orders == []
    # l'adozione: la banca viva passa alla strategia nuova (stesso nome)
    nuova = MU.MediaUnderStrategy(
        market_filter=filters.streaming_market_filter(market_ids=[b.mid]), name=NOME,
        media_params={**MU.VALORI_DI_SERIE, "media_mode": True,
                      "media_mercato": "OVER_UNDER_25"})
    banca = b.vivi("LAY")[0]
    assert R._adotta_ordini_vivi(b.fw, [b.strat], nuova) == 1
    assert list(b.market.blotter.strategy_orders(nuova)) == [banca]
    assert banca not in list(b.market.blotter.strategy_orders(b.strat))
    assert banca.trade.strategy is nuova
    # una strategia con un altro nome non adotta niente
    altra = MU.MediaUnderStrategy(
        market_filter=filters.streaming_market_filter(market_ids=[b.mid]), name="mu999",
        media_params={**MU.VALORI_DI_SERIE, "media_mode": True,
                      "media_mercato": "OVER_UNDER_25"})
    assert R._adotta_ordini_vivi(b.fw, [nuova], altra) == 0


def test_i_controlli_m_vedono_gli_ordini_di_tutte_le_sessioni(differita, exchange_it):
    """Un ordine DOPPIO dopo un riavvio (la sessione nuova appoggia una seconda
    banca mentre quella della morta e' viva) e' rosso: i controlli M leggono gli
    ordini di TUTTE le sessioni della modalita' della partita."""
    from Betfair.stream.scalper import certificazione as CERT

    b1 = BancoMedia(nome=NOME)
    giri(b1, differita, 70)
    b2 = BancoMedia(nome=NOME)                 # un'altra sessione, stesso mercato
    b2.pt = b1.pt
    giri(b2, differita, 70)                    # entra da capo: punta e banca DOPPIE
    banco = _banco_su(b1)
    # le due sessioni sullo stesso quadro: gli ordini della seconda nel blotter
    for o in b2.ordini():
        o.trade.strategy = b2.strat
        b1.market.blotter[o.id] = o
    banco.medie = [b1.strat, b2.strat]
    banco.media = b2.strat
    banco.giro(b1.pt, "t")
    assert "M5" in {v.codice for v in banco.ref.violazioni}
    # con la sola sessione nuova (la regola di prima) il doppio non si vede
    banco2 = _banco_su(b1)
    banco2.medie, banco2.media = [b2.strat], b2.strat
    banco2.giro(b1.pt, "t")
    assert "M5" not in {v.codice for v in banco2.ref.violazioni}
