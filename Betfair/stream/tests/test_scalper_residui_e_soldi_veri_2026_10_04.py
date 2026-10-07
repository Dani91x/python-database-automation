"""CERTIFICAZIONE SCALPER CALCIO (04/10) - minimi .it dal modulo condiviso,
residui RICORDATI, freno sui rifiuti di taglia, soldi veri SOLO col pulsante.

Reperto: replay 35797769 [base] KO dal 02/10 (09072ca: banco fedele ai minimi
.it). Le uscite esatte mandavano al place-and-trim resti sotto 0,50 che Betfair
.it rifiuta (K1: il bot seguiva un sostituto inesistente), il residuo si
dimenticava al reset del ciclo (K5, B2), la banca da 0,50 (minimo copiato nello
scalper) veniva rifiutata a ogni giro (1905 rifiuti col primo tentativo).

Decisioni dell'utente (04/10, testuali):
 1. «IL RESIDUO RESTA RICORDATO E LO CHIUDO IO»;
 2. «TUTTI I BOT DEVONO OPERARE IN LIVE SOLO SE CLICCO IL PULSANTE».
Regole sui minimi: banca diretta >= 1,00 al centesimo; punta >= 1,00 a multipli
di 0,50 arrotondata per difetto; fra 0,50 e il minimo place-and-trim; sotto 0,50
niente (residuo).

Bot VERO su Flumine VERO (banco del cantiere S, esecuzione differita di 1 e 4
book) con la regola dell'exchange del banco montata (`minimi_banco`).
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from Betfair.stream import modo_ordini as MO
from Betfair.stream.backtest import minimi_banco as MB
from Betfair.stream.scalper import scalper_bot as SB
from Betfair.stream.scalper import scalper_session as SS
from Betfair.stream.tests import test_cantiere_s_scalper_ko_2026_09_29 as SCT
from Betfair.stream.tests.test_cantiere_s_scalper_ko_2026_09_29 import (  # noqa: F401
    differita,
    esecuzione_differita,
    orologio_mercato,
)


@pytest.fixture
def exchange_it():
    """La regola dell'exchange simulato del banco (minimi .it)."""
    with MB.minimi_it_su_flumine() as registro:
        yield registro


def _k1(b: SCT.Banco, i: int) -> List[str]:
    """K1 del banco: uno slot VIVO non segue mai un ordine fuori dal blotter."""
    slot = b.slot()
    if str(slot.status) not in SCT.CERT.STATI_SLOT_VIVI:
        return []
    noti = {str(o.id) for o in b.market.blotter}
    out = []
    for riga in SCT.CERT.credenze(b.strat):
        if riga["chiave"] != (SCT.MID, SCT.SEL):
            continue
        for o in SCT.CERT.ordini_seguiti(riga):
            if str(o.id) not in noti:
                out.append("book %d K1: segue %s fuori dal blotter" % (i, o.id))
    return out


def _giri(b: SCT.Banco, svuota: Any, n: int) -> List[str]:
    viol: List[str] = []
    for i in range(n):
        svuota()
        b.book()
        viol += _k1(b, i) + SCT.invarianti(b, i)
    return viol


def _righe(b: SCT.Banco, kind: str) -> List[Dict[str, Any]]:
    return [p for k, p in b.righe if k == kind]


# ---------------------------------------------------------------------------
# 1. la spartizione di un'uscita (pura, dal modulo condiviso)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("lato,size,atteso", [
    # 07/10 (ordine dell'utente, chiusure al centesimo): la punta non multipla
    # esce ESATTA, diretta un passo sotto + resto 0,50-0,99 al place-and-trim
    ("BACK", 2.83, (2.0, 0.83, 0.0)),
    ("BACK", 1.0, (1.0, 0.0, 0.0)),
    ("BACK", 0.73, (0.0, 0.73, 0.0)),    # fra 0,50 e 1,00: place-and-trim (minimi_it)
    ("BACK", 7.27, (6.5, 0.77, 0.0)),    # 07/10: esatta (prima 7,00 + 0,27 residuo)
    ("BACK", 0.3, (0.0, 0.0, 0.3)),      # sotto 0,50: niente
    ("LAY", 1.37, (1.37, 0.0, 0.0)),     # banca al centesimo
    ("LAY", 0.73, (0.0, 0.73, 0.0)),     # fra 0,50 e 1,00: place-and-trim
    ("LAY", 0.5, (0.0, 0.5, 0.0)),       # prima: diretta (minimo copiato 0,50)
    ("LAY", 0.3, (0.0, 0.0, 0.3)),
])
def test_spezza_uscita_regole_dell_utente(lato, size, atteso):
    d, t, r = SB.spezza_uscita(lato, 2.2, size)
    assert (d, t, r) == pytest.approx(atteso)
    assert d + t + r == pytest.approx(size)


def test_i_minimi_dello_scalper_vengono_dal_modulo_condiviso(monkeypatch):
    """Nessuna copia: cambiando il minimo nel modulo condiviso cambia lo scalper."""
    from Betfair.stream import live_order_build as LOB

    assert SB.ScalperStrategy._side_min("LAY") == LOB.IT_LAY_MIN_SIZE == 1.0
    assert SB.ScalperStrategy._side_min("BACK") == LOB.IT_BACK_MIN_STAKE == 1.0


# ---------------------------------------------------------------------------
# 2. residuo RICORDATO (decisione 1) e mai un ordine fantasma (K1)
# ---------------------------------------------------------------------------
def test_residuo_sotto_050_dichiarato_una_volta_e_ricordato_oltre_il_ciclo(
        differita, orologio_mercato, exchange_it):
    """LAY 0,20 @2,22: chiusura BACK ~0,20, sotto 0,50: nessun ordine, nessuna
    sequenza, UNA riga CRITICAL `residuo_ricordato` con la proposta, il bot
    riprende (ciclo chiuso). Dopo il RESET del ciclo il residuo resta ricordato
    (`residuo_w/l`) e dichiarato: K5/B2 per tutta la vita, mai ritentato."""
    b = SCT._in_flatten("LAY", 2.22, 0.2)
    orologio_mercato["banco"] = b
    viol = _giri(b, differita, 60)
    slot = b.slot()
    assert viol == [], viol[:3]
    assert slot.status in (SB.IDLE, SB.DONE)
    assert _righe(b, "submin_start") == []
    assert [p for p in _righe(b, "place") if p.get("side") == "BACK"] == []
    crit = _righe(b, "residuo_ricordato")
    assert len(crit) == 1, crit
    assert crit[0]["level"] == "CRITICAL" and "SOTTO_MINIMO_NON_PIAZZABILE" in crit[0]["msg"]
    assert "Proposta" in crit[0]["msg"]
    w, l = SCT.esposizione_vera(b.market, b.strat)
    assert abs(w - l) > 0.4                       # il residuo e' a mercato
    assert slot.residuo_w == pytest.approx(w, abs=0.01)
    assert slot.residuo_l == pytest.approx(l, abs=0.01)
    assert exchange_it.rifiutati == []            # nessun tentativo rifiutato


def test_parte_diretta_piu_residuo_il_caso_del_replay(differita, orologio_mercato,
                                                      exchange_it):
    """Selezione 22 del replay: LAY 2,80 @2,22, chiusura BACK ~2,83.
    07/10 (ordine dell'utente: chiusure al centesimo): 2,00 diretti + 0,83 col
    place-and-trim, NESSUN residuo. Prima (04/10): 2,50 diretti + 0,33 residuo
    dichiarato; prima ancora: sequenza per 0,33, rimpiazzo rifiutato, K1."""
    b = SCT._in_flatten("LAY", 2.22, 2.8)
    orologio_mercato["banco"] = b
    viol = _giri(b, differita, 80)
    assert viol == [], viol[:3]
    back = [p for p in _righe(b, "place") if p.get("side") == "BACK"]
    assert back and float(back[0]["size"]) == 2.0
    assert _righe(b, "residuo_ricordato") == []
    assert [r for r in exchange_it.rifiutati if r["tipo"] == MB.SOSTITUZIONE] == []


def test_banca_fra_050_e_1_va_al_place_and_trim(differita, orologio_mercato, exchange_it):
    """BACK 0,73 @2,22 aperta: chiusura LAY ~0,74, sotto la banca minima 1,00 e
    sopra 0,50: place-and-trim (nessun residuo dichiarato)."""
    b = SCT._in_flatten("BACK", 2.22, 0.73)
    orologio_mercato["banco"] = b
    viol = _giri(b, differita, 120)
    assert viol == [], viol[:3]
    assert _righe(b, "submin_start"), b.righe[-5:]
    assert _righe(b, "residuo_ricordato") == []
    assert [r for r in exchange_it.rifiutati if r["side"].upper().endswith("LAY")
            and r["tipo"] == MB.DIRETTO] == []


def test_residuo_non_piazzabile_dichiarato_subito_non_dopo_12_tentativi(
        differita, orologio_mercato, exchange_it):
    """Decisione 1: «il bot non prova a chiuderlo da solo a ogni giro». LAY 0,45
    @2,22 (se vince -0,55: oltre il micro-residuo di 0,25): chiusura BACK 0,45,
    tutta residuo. Prima la ULTIMA SPIAGGIA aspettava piu' di 12 tentativi (~20
    book); ora si dichiara e si ricorda al primo giro utile."""
    b = SCT._in_flatten("LAY", 2.22, 0.45)
    orologio_mercato["banco"] = b
    slot = b.slot()
    for i in range(4):
        differita()
        b.book()
    assert len(_righe(b, "residuo_ricordato")) == 1, b.righe[-5:]
    assert slot.flat_tries <= 2
    assert slot.residuo_w == pytest.approx(-0.45 * 1.22, abs=0.01)


def test_banca_piazzabile_esce_al_centesimo_mai_arrotondata(
        differita, orologio_mercato, exchange_it):
    """Condizione 10 (chiusure al centesimo, mai gonfiate): BACK 1,35 @2,22 si
    chiude con una BANCA 1,35 (>= 1,00, al centesimo), non 1,50 (vecchio
    arrotondamento al multiplo di 0,50 delle uscite)."""
    b = SCT._in_flatten("BACK", 2.22, 1.35)
    orologio_mercato["banco"] = b
    differita()
    b.book()
    lay = [p for p in _righe(b, "place") if p.get("side") == "LAY"]
    assert lay and float(lay[0]["size"]) == pytest.approx(1.35), lay


def test_sniper_freno_soldi_veri_sulle_aperture():
    """Lo SNIPER in soldi veri: con il freno condiviso tirato nessuna apertura
    (CRITICAL una volta), le uscite partono."""
    from Betfair.stream.tests import test_sniper_bot_2026_07_10 as TSN

    s = TSN._strategy(exact_exits=True, size_step=0.5, live_min_bet=2.0)
    mkt = TSN._FakeMarket()
    s.freno_live = lambda: "live_order_mode_non_live:PAPER"
    assert s._place(mkt, 1221385, "BACK", 3.4, 10.0, floor=True) is None
    assert s._place(mkt, 1221385, "BACK", 3.4, 10.0, floor=True) is None
    assert mkt.orders == []
    crit = [p for k, p in s._test_events if k == "apertura_live_fermata"]
    assert len(crit) == 1 and crit[0]["level"] == "CRITICAL"
    pos = s._p("1.234", 1221385)
    assert s._place(mkt, 1221385, "LAY", 3.4, 5.0, floor=False, pos=pos) is not None
    s.freno_live = lambda: None
    assert s._place(mkt, 1221385, "BACK", 3.4, 10.0, floor=True) is not None


def test_tolleranza_del_banco_conta_solo_il_residuo_ricordato():
    """K5/B2 (`certificazione.tolleranza_slot`): il residuo RICORDATO dal bot
    entra nella tolleranza al centesimo; senza ricordo resta 0,02."""
    s = SB._Slot()
    assert SCT.CERT.tolleranza_slot(s) == pytest.approx(0.02)
    s.residuo_w, s.residuo_l = -0.244, 0.2
    assert SCT.CERT.tolleranza_slot(s) == pytest.approx(0.02 + 0.444)


# ---------------------------------------------------------------------------
# 3. rifiuto per la TAGLIA: freno, mai un ripiazzo a ogni giro
# ---------------------------------------------------------------------------
def test_chiusura_rifiutata_per_taglia_non_si_ripiazza_a_ogni_giro(
        differita, orologio_mercato, exchange_it, monkeypatch):
    """L'exchange (qui con un minimo della banca alzato a 50) rifiuta la
    chiusura LAY INVALID_BET_SIZE: prima il flatten la ripiazzava ogni 1,5 s
    (replay: 1905 rifiuti); ora 1, 2, 4, 8, 16, 30 s di mercato, una riga
    CRITICAL al primo rifiuto e WARN dopo."""
    monkeypatch.setattr(MB, "IT_MIN_LAY", 50.0)
    b = SCT._in_flatten("BACK", 2.22, 20.0)
    orologio_mercato["banco"] = b
    for _ in range(60):                      # 60 s di mercato
        differita()
        b.book()
    rif = _righe(b, "rifiuto_taglia")
    lay = [p for p in _righe(b, "place") if p.get("side") == "LAY"]
    assert 3 <= len(lay) <= 7, len(lay)      # 1+1+2+4+8+16+30: 6 in 60 s (prima ~35)
    assert rif and rif[0]["level"] == "CRITICAL"
    assert all(r["level"] == "WARN" for r in rif[1:])
    assert len(exchange_it.rifiutati) == len(lay)


# ---------------------------------------------------------------------------
# 4. soldi veri SOLO col pulsante («Ordini reali»)
# ---------------------------------------------------------------------------
def test_freno_soldi_veri_ferma_le_aperture_e_lascia_le_chiusure(
        differita, orologio_mercato):
    """Strategia di una sessione in soldi veri col freno condiviso tirato
    («Ordini reali» in prova): nessuna APERTURA (una riga CRITICAL per
    episodio), le CHIUSURE partono."""
    b = SCT.Banco()
    orologio_mercato["banco"] = b
    b.book()
    b.strat.freno_live = lambda: "live_order_mode_non_live:PAPER"
    a1 = b.strat._place(b.market, SCT.SEL, "BACK", 2.2, 25.0, floor_min=True)
    a2 = b.strat._place(b.market, SCT.SEL, "LAY", 2.22, 25.0, floor_min=True)
    assert a1 is None and a2 is None
    crit = _righe(b, "apertura_live_fermata")
    assert len(crit) == 1 and crit[0]["level"] == "CRITICAL"
    c = b.strat._place(b.market, SCT.SEL, "BACK", 2.2, 5.0, floor_min=False,
                       slot=b.slot())
    assert c is not None                      # la chiusura parte
    b.strat.freno_live = lambda: None         # «Ordini reali» in soldi veri
    assert b.strat._place(b.market, SCT.SEL, "BACK", 2.2, 25.0, floor_min=True) is not None


class _TabellaFinta:
    def __init__(self, db: "_DbSupervisore", nome: str) -> None:
        self.db, self.nome = db, nome

    def insert(self, riga: Dict[str, Any]) -> "_TabellaFinta":
        self.db.tabelle.setdefault(self.nome, []).append(dict(riga))
        return self

    def execute(self) -> Any:
        return None


class _DbSupervisore:
    """Le scritture di `scalper_service.Db` usate da `marca_orfana` (stesse
    firme: `set_control(event_id, **campi)`, `sb.table(nome).insert(riga)`)."""

    def __init__(self) -> None:
        self.controlli: List[Dict[str, Any]] = []
        self.tabelle: Dict[str, List[Dict[str, Any]]] = {}
        self.sb = self

    def table(self, nome: str) -> _TabellaFinta:
        return _TabellaFinta(self, nome)

    def set_control(self, event_id: str, **fields: Any) -> None:
        self.controlli.append({"event_id": event_id, **fields})


@pytest.mark.parametrize("dry_run,modo", [(False, "live"), (True, "paper")])
def test_sessione_orfana_dichiarata_al_trader(dry_run, modo):
    """S7 (scenario `riavvio`): il processo della sessione muore con ordini a
    mercato; un processo nuovo di flumine non li adotta. Il supervisore marca
    la riga 'error' e li DICHIARA con un avviso CRITICAL in `live_alerts`
    (decisione dell'utente: il residuo lo chiude lui)."""
    from Betfair.stream.scalper import scalper_service as SVC

    db = _DbSupervisore()
    SVC.marca_orfana(db, "77", {"dry_run": dry_run})
    assert db.controlli[-1]["status"] == "error"
    assert "orfana" in db.controlli[-1]["error"]
    avvisi = db.tabelle.get("live_alerts") or []
    assert len(avvisi) == 1 and avvisi[0]["level"] == "CRITICAL"
    assert avvisi[0]["code"] == SVC.CODICE_ORFANA and avvisi[0]["event_id"] == "77"
    assert "orfan" in avvisi[0]["message"].lower() and modo in avvisi[0]["message"]
    # il controllo S7 del banco riconosce la dichiarazione
    orf = [{"order_id": "o1", "side": "LAY", "selection_id": 1, "price": 2.0,
            "size_matched": 25.0, "size_remaining": 0.0}]
    oss = SCT.CERT.Osservazione(orfani_dopo_riavvio=orf, credenze=[], allarmi=avvisi)
    assert SCT.CERT._s7(oss) is None
    assert SCT.CERT._s7(SCT.CERT.Osservazione(orfani_dopo_riavvio=orf, credenze=[],
                                              allarmi=[])) is not None


def test_cp1_riconosce_la_chiusura_dalla_riga_di_specchio():
    """CP1 (scenario `chiusura-abbinata-in-parte`): una chiusura colpita che lo
    scalper ha smesso di seguire (ciclo chiuso) resta riconoscibile dalla riga
    di specchio che la UI vede, come per i bot tennis; i NUMERI della riga si
    giudicano (abbinato/residuo/prezzo)."""
    from Betfair.stream.scalper.tools import replay_registrazioni as RR

    riga = {"bet_id": "100000000016", "size": 25.0, "price": 1.82, "status": "EXECUTION_COMPLETE",
            "size_matched": 10.0, "size_remaining": 0.0, "average_price_matched": 1.82,
            "client_order_ref": "x", "mode": "live"}
    out = RR.credenze_cp([], None, None, specchio=[riga])
    assert len(out) == 1 and out[0]["id"] == "specchio" and out[0]["chiave"] == ()
    c = out[0]["chiusure"][0]
    assert c["bet_id"] == "100000000016" and c["size_matched"] == 10.0
    assert c["avg_price_matched"] == 1.82
    assert RR.credenze_cp([], None, None) == []


class _DbSessione:
    """Le due scritture di `scalper_session.Db` usate all'avvio (stesse firme)."""

    def __init__(self) -> None:
        self.controlli: List[Dict[str, Any]] = []
        self.log_righe: List[tuple] = []

    def set_control(self, event_id: str, **fields: Any) -> None:
        self.controlli.append({"event_id": event_id, **fields})

    def log(self, event_id: str, kind: str, payload: Dict[str, Any]) -> None:
        self.log_righe.append((event_id, kind, payload))


@pytest.mark.parametrize("ordini_reali,parte", [("LIVE", True), ("PAPER", False),
                                                ("OFF", False)])
def test_sessione_in_soldi_veri_parte_solo_con_ordini_reali_in_soldi_veri(
        ordini_reali, parte):
    from Betfair.stream.backtest.certifica import _freni_da_banco

    db = _DbSessione()
    with _freni_da_banco(), MO.dichiara_per_banco(ordini_reali, kill=False):
        motivo = SS.non_partire_senza_soldi_veri(db, "77")
    if parte:
        assert motivo is None and db.controlli == []
    else:
        assert motivo == "live_order_mode_non_live:%s" % ordini_reali
        assert db.controlli[-1]["status"] == "stopped"
        assert "soldi veri non serviti" in db.controlli[-1]["error"]
        assert db.log_righe[-1][1] == "critical"


def test_run_session_controlla_i_soldi_veri_prima_del_login():
    """Il cablaggio: in `run_session` il controllo dei soldi veri sta PRIMA del
    login e i freni sono iniettati nelle strategie live (maker e sniper)."""
    import inspect

    src = inspect.getsource(SS.run_session)
    i_ctl = src.index("non_partire_senza_soldi_veri(db, ev)")
    i_login = src.index("trading = build_client(login=True)")
    assert i_ctl < i_login
    assert "strategy.freno_live = freno_soldi_veri" in src
    assert "sniper.freno_live = freno_soldi_veri" in src
