"""MEDIA UNDER (05/10/2026) - la modalita' nuova dello Scalper calcio.

Spec: ``Betfair/stream/scalper/SPEC_MEDIA_UNDER_2026-10-05.md``. Ogni vettore del
par.4 e' un test; in piu' i casi del par.9 (banca abbinata in parte prima di un
rientro, punta di rientro non abbinata, rientro bloccato dal massimo e dal
rischio massimo, nessun rientro in gioco, banca PERSIST che sopravvive al
fischio e punta LAPSE che cade, nessuna chiusura forzata prima del fischio, mai
due chiusure vive insieme, riavvio a posizione aperta, soldi veri fermati senza
"Ordini reali", l'auto-mode non arma la modalita', modalita' spenta = nessun
effetto).

La strategia gira VERA su Flumine VERO (client paper della sessione) con book
nel formato nativo di Betfair (``banco_media_under.BancoMedia``), l'esecuzione
differita di 1 e 4 book (latenza e coda) e la regola dei minimi .it del banco
montata (``minimi_banco.minimi_it_su_flumine``), come i test dello scalper del
04/10. La sessione e' quella VERA (``scalper_session.run_session``) fino
all'armamento (``replay_registrazioni.arma_e_cattura``: nessun book, nessuna
registrazione). Nessuna registrazione di mercato: i replay li lancia il
coordinatore.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

import pytest

from Betfair.stream.backtest import minimi_banco as MB
from Betfair.stream.scalper import auto_mode as AM
from Betfair.stream.scalper import certificazione as CERT
from Betfair.stream.scalper import media_under_bot as MU
from Betfair.stream.scalper import scalper_session as SS
from Betfair.stream.scalper.tools import replay_registrazioni as R
from Betfair.stream.tennis_live.tests.test_cantiere_t_pro_residuo_2026_09_28 import (  # noqa: F401
    esecuzione_differita,
)
from Betfair.stream.tests.banco_media_under import KO_MS, BancoMedia, giri, params_di_serie

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@pytest.fixture(params=[1, 4])
def differita(request, esecuzione_differita):
    """Esecuzione dei pacchetti di flumine differita di 1 e di 4 book."""
    esecuzione_differita.ritardo = request.param
    return esecuzione_differita


@pytest.fixture
def exchange_it():
    with MB.minimi_it_su_flumine() as registro:
        yield registro


def _posizione_a(b: BancoMedia, svuota: Any) -> List[str]:
    """Riscaldamento (60 s di flusso) e ingresso: punta 10 @1,50 abbinata e
    banca appoggiata."""
    return giri(b, svuota, 70)


def _sali(b: BancoMedia, svuota: Any, quote: List[float], n: int = 12) -> List[str]:
    viol: List[str] = []
    for q in quote:
        b.ladder[b.under] = (q, round(q + 0.01, 2))
        viol += giri(b, svuota, n)
    return viol


def _fino_a(b: BancoMedia, svuota: Any, kind: str, massimo: int = 60) -> List[str]:
    """Un book alla volta finche' la strategia non emette ``kind`` (al massimo
    ``massimo`` book: un evento che non arriva e' un test ROSSO, mai appeso)."""
    viol: List[str] = []
    for _i in range(massimo):
        if b.kinds(kind):
            return viol
        viol += giri(b, svuota, 1)
    assert b.kinds(kind), "nessun %s in %d book" % (kind, massimo)
    return viol


def _punte(b: BancoMedia) -> List[Any]:
    return [o for o in b.ordini() if MU._lato(o) == "BACK"]


def _banche(b: BancoMedia) -> List[Any]:
    return [o for o in b.ordini() if MU._lato(o) == "LAY"]


def _banca_viva(b: BancoMedia) -> Any:
    """07/10 (banca SPOSTATA): la banca viva come (quota, somma dei resti):
    puo' essere piu' ordini (la banca spostata col replace + le integrazioni),
    sempre alla STESSA quota. None senza banche vive."""
    vive = b.vivi("LAY")
    if not vive:
        return None
    quote = {float(o.order_type.price) for o in vive}
    assert len(quote) == 1, "banche vive a quote diverse: %s" % sorted(quote)
    return (quote.pop(), round(sum(float(o.size_remaining) for o in vive), 2))


def _annulli_banca(b: BancoMedia) -> List[Any]:
    """Le banche ANNULLATE dal bot (resto annullato, nessun sostituto di un
    replace nel loro Trade): dal 07/10 la banca si sposta, non si annulla."""
    out = []
    for o in _banche(b):
        tr = list(o.trade.orders)
        if float(getattr(o, "size_cancelled", 0.0) or 0.0) > 0.004 and tr[-1] is o:
            out.append(o)
    return out


# ===========================================================================
# 1. LE FORMULE (spec par.4): ogni vettore e' un test
# ===========================================================================
VETTORE_A = [
    # quota, X esatto, punta, totale, quota media, banca, quota banca, lordo
    (1.52, 10.14, 10.00, 20.00, 1.5100, 20.13, 1.50, 0.1333),
    (1.54, 20.27, 20.00, 40.00, 1.5250, 40.13, 1.52, 0.1316),
    (1.56, 40.41, 40.00, 80.00, 1.5425, 80.13, 1.54, 0.1299),
    (1.58, 80.54, 80.50, 160.50, 1.5613, 160.63, 1.56, 0.1346),
    (1.60, 160.68, 160.50, 321.00, 1.5807, 321.13, 1.58, 0.1329),
]


def test_vettore_a_base_10_a_150_obiettivo_automatico_punte_a_050():
    t = MU.obiettivo_automatico(10.0, 1.50, MU.tick_sotto(1.50, 2))
    assert t == pytest.approx(0.1351, abs=5e-5)
    punte = [(10.0, 1.50)]
    pos = MU.posizione_da_importi(punte)
    assert MU.al_centesimo(MU.banca_esatta(pos, 1.48)) == 10.14
    assert pos.se_perde + MU.banca_esatta(pos, 1.48) == pytest.approx(0.1351, abs=5e-5)
    for q, x_es, punta, tot, media, banca, c, lordo in VETTORE_A:
        assert MU.tick_sotto(q, 2) == c
        x = MU.rientro_esatto(pos, q, c, t)
        assert round(x, 2) == x_es
        assert MU.punta_a_multiplo(x)[0] == punta
        punte.append((punta, q))
        pos = MU.posizione_da_importi(punte)
        assert pos.puntato == pytest.approx(tot)
        assert round(pos.quota_media, 4) == media
        assert MU.al_centesimo(MU.banca_esatta(pos, c)) == banca
        assert pos.se_perde + MU.banca_esatta(pos, c) == pytest.approx(lordo, abs=5e-5)


def test_vettore_b_esempio_dell_utente_netto_030_al_centesimo():
    """Senza arrotondamento a 0,50 (al centesimo, come vuole Betfair): rientri
    21,32 / 31,63 / 63,27, totale 126,22, media 1,3935, banca 126,54 @1,39,
    netto 0,30 (l'utente: 21,30 / 31,70 / 63,50)."""
    t = MU.lordo_da_netto(0.30, 0.05)
    punte = [(10.0, 1.35)]
    pos = MU.posizione_da_importi(punte)
    attesi = [(1.37, 21.32), (1.39, 31.63), (1.41, 63.27)]
    for q, x_atteso in attesi:
        x = round(MU.rientro_esatto(pos, q, MU.tick_sotto(q, 2), t), 2)
        assert x == x_atteso
        punte.append((x, q))
        pos = MU.posizione_da_importi(punte)
    assert pos.puntato == pytest.approx(126.22)
    assert round(pos.quota_media, 4) == 1.3935
    banca = MU.al_centesimo(MU.banca_esatta(pos, 1.39))
    assert banca == 126.54
    w, l = MU.profitto_lordo_con_banca(pos, banca, 1.39)
    assert MU.netto_da_lordo(min(w, l), 0.05) == pytest.approx(0.30, abs=0.0021)
    assert MU.netto_da_lordo(MU.banca_esatta(pos, 1.39) + pos.se_perde, 0.05) == \
        pytest.approx(0.30, abs=0.002)


def test_vettore_c_come_b_con_le_punte_a_multipli_di_050():
    """21,00 / 31,50 / 62,50 / 125,50 / 251,00; totale 501,50; banca 501,81 @1,43.
    Netto: se perde 0,2945 (dentro "fra 0,294 e 0,299" della spec), se vince
    0,3009 (sopra 0,299: divergenza scritta nel referto, la formula e' quella
    del par.4)."""
    t = MU.lordo_da_netto(0.30, 0.05)
    punte = [(10.0, 1.35)]
    pos = MU.posizione_da_importi(punte)
    for q, attesa in ((1.37, 21.0), (1.39, 31.5), (1.41, 62.5), (1.43, 125.5),
                      (1.45, 251.0)):
        x = MU.rientro_esatto(pos, q, MU.tick_sotto(q, 2), t)
        assert MU.punta_a_multiplo(x)[0] == attesa
        punte.append((attesa, q))
        pos = MU.posizione_da_importi(punte)
    assert pos.puntato == pytest.approx(501.5)
    banca = MU.al_centesimo(MU.banca_esatta(pos, 1.43))
    assert banca == 501.81
    w, l = MU.profitto_lordo_con_banca(pos, banca, 1.43)
    assert MU.netto_da_lordo(l, 0.05) == pytest.approx(0.2945, abs=1e-4)
    assert MU.netto_da_lordo(w, 0.05) == pytest.approx(0.3009, abs=1e-4)
    assert 0.294 <= MU.netto_da_lordo(min(w, l), 0.05) <= 0.299


def test_vettore_d_segnalazione_in_gioco_esempio_dell_utente():
    """Punta 10 @1,32, quota attuale 1,67, commissione 0: chiudere adesso banca
    7,90 @1,67 -> -2,10; per chiudere a 1,65: pareggio 165,00 (175,00; 1,6500),
    +0,30 189,75 esatti (199,75; 1,6525), +1,00 247,50 (257,50; 1,6564)."""
    pos = MU.posizione_da_importi([(10.0, 1.32)])
    r = MU.riquadro_chiusura(pos, quota_punta=1.67, quota_banca=1.67, tick=2,
                             obiettivi_netti=[0.0, 0.30, 1.00], commissione=0.0)
    assert r["chiudi_adesso"] == {"banca": 7.90, "quota": 1.67, "pnl_lordo": -2.10,
                                  "pnl_netto": -2.10}
    o0, o1, o2 = r["obiettivi"]
    assert (o0["quota_chiusura"], o0["punta"], o0["punta_esatta"],
            o0["rischio_totale_esatto"], o0["quota_media_dopo_esatta"]) == \
        (1.65, 165.0, 165.0, 175.0, 1.65)
    assert (o1["punta"], o1["punta_esatta"], o1["rischio_totale_esatto"],
            o1["quota_media_dopo_esatta"]) == (189.5, 189.75, 199.75, 1.6525)
    # col multiplo di 0,50 (par.6): rischio 199,50, media 1,6525
    assert (o1["rischio_totale"], o1["quota_media_dopo"]) == (199.5, 1.6525)
    assert (o2["punta"], o2["punta_esatta"], o2["rischio_totale_esatto"],
            o2["quota_media_dopo_esatta"]) == (247.5, 247.5, 257.5, 1.6564)
    assert r["fonte"] == MU.FONTE_SOLO_BOT


def test_tick_sulla_scala_vera_di_betfair():
    assert MU.tick_sotto(2.02, 2) == 1.99       # 2,02 -> 2,00 (passo 0,02) -> 1,99
    assert MU.tick_sotto(3.05, 2) == 2.98       # 3,05 -> 3,00 (passo 0,05) -> 2,98
    assert MU.tick_sotto(1.50, 2) == 1.48
    assert MU.tick_sotto(4.10, 1) == 4.0


def test_punta_a_multiplo_per_difetto_dalla_fonte_unica():
    assert MU.punta_a_multiplo(80.54) == (80.5, 80.54)
    assert MU.punta_a_multiplo(10.99) == (10.5, 10.99)
    assert MU.punta_a_multiplo(0.80)[0] == 0.0   # sotto 1,00: non diretta


# ===========================================================================
# 2. I PARAMETRI (spec par.5): mancante o non valido = la sessione non parte
# ===========================================================================
def _control(**params: Any) -> Dict[str, Any]:
    return {"event_id": "1", "status": "requested", "mode": "maker", "dry_run": True,
            "stake": 25, "params": params_di_serie(**params), "origine": "manuale"}


def test_spenta_di_serie_solo_un_vero_la_accende():
    assert MU.media_mode_acceso({}) is False
    assert MU.media_mode_acceso({"media_mode": "true"}) is False
    assert MU.media_mode_acceso({"media_mode": 1}) is False
    assert MU.media_mode_acceso({"media_mode": True}) is True
    assert MU.VALORI_DI_SERIE["media_mode"] is False


def test_i_valori_di_serie_sono_validi_e_l_obiettivo_assente_e_automatico():
    par, motivo = MU.leggi_parametri(params_di_serie())
    assert motivo is None and par.obiettivo_netto is None
    p = params_di_serie()
    p.pop("media_obiettivo")
    par, motivo = MU.leggi_parametri(p)
    assert motivo is None and par.obiettivo_netto is None
    par, _m = MU.leggi_parametri(params_di_serie(media_obiettivo=0.30))
    assert par.obiettivo_netto == 0.30


@pytest.mark.parametrize("chiave", MU.OBBLIGATORI)
def test_un_parametro_mancante_non_fa_partire(chiave):
    c = _control()
    c["params"].pop(chiave)
    motivo = MU.motivo_non_parte(c)
    # il motivo dice che MANCA (non un errore di tipo qualunque)
    assert motivo == "parametri mancanti: %s" % chiave


@pytest.mark.parametrize("chiave,valore", [
    ("media_mercato", "OVER_UNDER_15"), ("media_mercato", "MATCH_ODDS"),
    ("media_stake", 10.30), ("media_stake", 0.5), ("media_tick_chiusura", 0),
    ("media_tick_rientro", 1.5), ("media_max_rientri", -1), ("media_rischio_max", -5),
    ("media_quota_min", 4.5), ("media_ttl_punta_ms", 0), ("media_obiettivi_live", "0"),
    ("media_commissione_pct", 100), ("media_obiettivo", -0.3), ("media_min_size", True),
])
def test_un_parametro_non_valido_non_fa_partire(chiave, valore):
    assert MU.motivo_non_parte(_control(**{chiave: valore}))


def test_origine_auto_theta_e_intervallo_non_fanno_partire():
    c = _control()
    assert MU.motivo_non_parte(c) is None
    assert "auto-mode" in MU.motivo_non_parte(dict(c, origine="auto"))
    assert MU.motivo_non_parte(dict(c, params=dict(c["params"], theta_mode=True)))
    assert MU.motivo_non_parte(dict(c, params=dict(c["params"], ht_mode=True)))
    assert MU.motivo_non_parte(dict(c, mode="bias"))


def test_le_chiavi_della_modalita_sono_nella_whitelist_della_sessione():
    assert set(MU.CHIAVI_UI) <= SS.UI_PARAM_WHITELIST
    assert set(MU.OBBLIGATORI) <= set(MU.CHIAVI_UI)


def test_i_valori_di_serie_sono_quelli_della_scheda():
    """Catalogo par.7 punto 33: nessuna costante duplicata che diverge. Il
    frontend (``MEDIA_UNDER_DEFAULTS``) e il backend dicono gli stessi numeri."""
    ts = open(os.path.join(RADICE, "frontend", "src", "lib", "mediaUnder.ts"),
              encoding="utf-8").read()
    blocco = ts[ts.index("MEDIA_UNDER_DEFAULTS"):]
    blocco = blocco[blocco.index("{") + 1: blocco.index("};")]
    valori: Dict[str, Any] = {}
    for m in re.finditer(r"(media_\w+):\s*(\[[^\]]*\]|[^,\n]+)", blocco):
        valori[m.group(1)] = m.group(2).strip()
    for k, v in MU.VALORI_DI_SERIE.items():
        assert k in valori, k
        letto = valori[k]
        if isinstance(v, bool):
            assert letto == ("true" if v else "false"), k
        elif isinstance(v, list):
            assert json.loads(letto) == pytest.approx(v), k
        else:
            assert float(letto) == pytest.approx(float(v)), k


# ===========================================================================
# 3. LA STRATEGIA su flumine VERO
# ===========================================================================
def test_ingresso_e_banca_persist_sul_mercato_scelto(differita, exchange_it):
    b = BancoMedia()
    viol = _posizione_a(b, differita)
    assert viol == [], viol[:3]
    punte, banche = _punte(b), _banche(b)
    assert [(float(o.order_type.price), float(o.order_type.size)) for o in punte] == [(1.50, 10.0)]
    assert [(float(o.order_type.price), float(o.order_type.size)) for o in banche] == [(1.48, 10.14)]
    assert str(banche[0].order_type.persistence_type) == "PERSIST"
    assert str(punte[0].order_type.persistence_type) == "LAPSE"
    assert all(o.selection_id == b.under and o.market_id == b.mid for o in b.ordini())
    assert b.strat.stato == MU.IN_POSIZIONE
    assert exchange_it.rifiutati == []


def test_niente_ingresso_senza_liquidita_flusso_spread_o_quota(differita):
    for kw, ladder in (({"profondita": 200.0}, None), ({}, (1.50, 1.54)),
                       ({}, (4.20, 4.30)), ({}, (1.15, 1.16))):
        b = BancoMedia(**kw)
        if ladder:
            b.ladder[b.under] = ladder
        giri(b, differita, 80)
        assert b.ordini() == [], (kw, ladder)
    b = BancoMedia()
    giri(b, differita, 80, flusso=0.0)
    assert b.ordini() == []


def test_niente_ingresso_dentro_la_finestra_di_stop_prima_del_fischio(differita):
    b = BancoMedia()
    b.pt = KO_MS - 420_000 - 30_000
    giri(b, differita, 90)
    assert b.ordini() == []


def test_ciclo_chiuso_in_profitto_e_ricomincia_con_lo_stake_base(differita, exchange_it):
    b = BancoMedia()
    viol = _posizione_a(b, differita)
    b.ladder[b.under] = (1.47, 1.48)
    b.scambia(b.under, 1.48, 2000)
    viol += giri(b, differita, 8)
    assert viol == [], viol[:3]
    chiusi = b.kinds("media_ciclo_chiuso")
    assert len(chiusi) == 1 and chiusi[0]["profitto_lordo"] == pytest.approx(0.13, abs=0.006)
    assert b.strat.stats["cicli_chiusi"] == 1
    # nuovo primo ingresso con lo stake base
    assert [float(o.order_type.size) for o in _punte(b)] == [10.0, 10.0]


def test_vettore_a_su_flumine_rientri_banche_e_massimo(differita, exchange_it):
    b = BancoMedia()
    viol = _posizione_a(b, differita)
    assert _banca_viva(b) == (1.48, 10.14)
    # 07/10 (banca SPOSTATA): dopo ogni rientro abbinato la banca e' sulla quota
    # nuova per l'importo del vettore A (stessi numeri di prima), fatta dalla
    # banca spostata col replace + l'integrazione; mai annullata e ripiazzata
    for q, attesa in ((1.52, (1.50, 20.13)), (1.54, (1.52, 40.13)), (1.56, (1.54, 80.13)),
                      (1.58, (1.56, 160.63)), (1.60, (1.58, 321.13)), (1.62, (1.58, 321.13)),
                      (1.64, (1.58, 321.13))):
        viol += _sali(b, differita, [q])
        assert _banca_viva(b) == attesa, q
    assert viol == [], viol[:3]
    assert [(float(o.order_type.price), float(o.order_type.size)) for o in _punte(b)] == [
        (1.50, 10.0), (1.52, 10.0), (1.54, 20.0), (1.56, 40.0), (1.58, 80.5), (1.60, 160.5)]
    assert _annulli_banca(b) == []
    integrazioni = [p for p in b.kinds("media_banca") if p.get("integrazione")]
    assert [(p["prezzo"], p["importo"], p["totale"]) for p in integrazioni] == [
        (1.50, 9.99, 20.13), (1.52, 20.00, 40.13), (1.54, 40.00, 80.13),
        (1.56, 80.50, 160.63), (1.58, 160.50, 321.13)]
    assert b.strat.stato == MU.MASSIMO
    massimo = b.kinds("media_massimo")
    assert len(massimo) == 1 and massimo[0]["level"] == "CRITICAL"
    assert b.vivi("BACK") == []
    ch = b.strat.stats["chiusura"]
    assert ch is not None and ch["posizione"]["totale_puntato"] == 321.0


def test_banca_abbinata_in_parte_prima_di_un_rientro(differita, exchange_it):
    """Banca 10,14 @1,48 abbinata 5,00, poi il rientro: X sulla posizione VERA
    (banca abbinata compresa) = 5,14 -> 5,00; banca 10,13 @1,50."""
    b = BancoMedia()
    viol = _posizione_a(b, differita)
    banca = b.vivi("LAY")[0]
    b.scambia(b.under, 1.48, 1010)          # meta' per lato: 500 di coda + 5,00
    viol += giri(b, differita, 2)
    assert float(banca.size_matched) == pytest.approx(5.0)
    viol += _sali(b, differita, [1.52])
    assert viol == [], viol[:3]
    rientro = b.kinds("media_rientro")[0]
    assert (rientro["importo"], rientro["importo_esatto"]) == (5.0, 5.14)
    # 07/10: la banca (resto 5,14) si sposta a 1,50 e l'integrazione 4,99 la
    # porta a 10,13 sulla posizione vera
    assert _banca_viva(b) == (1.50, 10.13)
    assert _annulli_banca(b) == []
    pos = b.posizione()
    assert pos.se_perde + 10.13 == pytest.approx(0.13, abs=0.006)


def test_punta_di_rientro_non_abbinata_si_annulla_e_non_conta(differita, exchange_it):
    b = BancoMedia()
    viol = _posizione_a(b, differita)
    b.ladder[b.under] = (1.52, 1.53)
    viol += _fino_a(b, differita, "media_rientro")   # annullo della banca, poi la punta
    # prima che la punta passi (un book senza esecuzione): il prezzo torna giu',
    # la punta resta appoggiata
    b.ladder[b.under] = (1.51, 1.52)
    b.book(flusso=0.0)
    viol += giri(b, differita, 45, flusso=0.0)
    assert viol == [], viol[:3]
    punta = _punte(b)[-1]
    assert float(punta.order_type.price) == 1.52 and float(punta.size_matched) == 0.0
    assert not MU.vivo_o_in_volo(punta)
    assert b.kinds("media_punta_non_abbinata")
    assert b.strat._rientri == 0
    # la banca torna sulla posizione (10 @1,50 -> 10,14 @1,48)
    vive = b.vivi("LAY")
    assert [(float(o.order_type.price), float(o.size_remaining)) for o in vive] \
        == [(1.48, 10.14)]


def test_rientro_deciso_con_la_banca_ancora_in_volo(differita, exchange_it):
    """La quota sale di 2 tick mentre la banca e' appena partita (PENDING): il
    rientro aspetta che la banca sia sul book (07/10: NON la annulla), punta, e
    a punta abbinata la banca si sposta (mai bloccato per sempre, mai una
    copertura oltre la posizione)."""
    b = BancoMedia()
    viol = giri(b, differita, 61)
    viol += _fino_a(b, differita, "media_banca")
    banca = b.vivi("LAY")[0]
    assert str(banca.status.value) == "Pending"
    b.ladder[b.under] = (1.52, 1.53)
    viol += giri(b, differita, 15)
    assert viol == [], viol[:3]
    assert not MU.vivo_o_in_volo(banca)          # spostata (replace), non annullata
    assert [float(o.order_type.size) for o in _punte(b)] == [10.0, 10.0]
    assert _banca_viva(b) == (1.50, 20.13)
    assert _annulli_banca(b) == []


def test_rientro_bloccato_dal_massimo_zero(differita, exchange_it):
    b = BancoMedia(media_max_rientri=0)
    viol = _posizione_a(b, differita)
    viol += _sali(b, differita, [1.52, 1.54])
    assert viol == []
    assert len(_punte(b)) == 1 and b.strat.stato == MU.MASSIMO
    assert len(b.kinds("media_massimo")) == 1


def test_rientro_bloccato_dal_rischio_massimo_con_la_riga_di_log(differita, exchange_it):
    b = BancoMedia(media_rischio_max=35.0)
    viol = _posizione_a(b, differita)
    viol += _sali(b, differita, [1.52, 1.54, 1.56])
    assert viol == [], viol[:3]
    assert [float(o.order_type.size) for o in _punte(b)] == [10.0, 10.0]
    righe = b.kinds("media_rientro_bloccato")
    assert len(righe) == 1 and righe[0]["motivo"] == "rischio_max"
    assert righe[0]["level"] == "CRITICAL" and righe[0]["rientro"] == 20.0
    assert b.strat.stats["rientri_bloccati"] == "rischio_max"
    assert _banca_viva(b) == (1.50, 20.13)       # la banca resta appoggiata


def test_in_gioco_nessun_ordine_banca_persist_resta_punta_lapse_cade(differita, exchange_it):
    b = BancoMedia()
    viol = _posizione_a(b, differita)
    # una punta di rientro VIVA (non abbinata) al fischio
    b.ladder[b.under] = (1.52, 1.53)
    viol += _fino_a(b, differita, "media_rientro")
    b.ladder[b.under] = (1.51, 1.52)
    b.book(flusso=0.0)
    viol += giri(b, differita, 2, flusso=0.0)
    punta = _punte(b)[-1]
    assert MU.vivo_o_in_volo(punta)
    # niente banca durante la punta di rientro: la si appoggia per vedere il PERSIST
    b2 = BancoMedia()
    viol += _posizione_a(b2, differita)
    banca2 = b2.vivi("LAY")[0]
    n_prima = len(b2.ordini())
    b.pt = b2.pt = KO_MS + 1000
    b.in_gioco()
    b2.in_gioco()
    assert not MU.vivo_o_in_volo(punta) and float(punta.size_matched) == 0.0   # LAPSE caduta
    assert MU.vivo_o_in_volo(banca2)                                           # PERSIST resta
    # in gioco la quota sale: nessun rientro, nessun ordine, nessun annullo
    for bb in (b, b2):
        bb.ladder[bb.under] = (1.70, 1.71)
    n1 = len(b.ordini())
    viol += giri(b, differita, 20) + giri(b2, differita, 20)
    assert viol == [], viol[:3]
    assert len(b.ordini()) == n1 and len(b2.ordini()) == n_prima
    assert MU.vivo_o_in_volo(banca2) and float(banca2.size_cancelled) == 0.0
    assert b2.strat.stato == MU.LIVE
    assert b2.kinds("media_live") and b2.kinds("media_live")[0]["level"] == "CRITICAL"
    ch = b2.strat.stats["chiusura"]
    assert ch["banca"]["stato"] == "viva" and ch["chiudi_adesso"]["quota"] == 1.71
    assert ch["obiettivi"][0]["quota_punta"] == 1.70


def test_in_gioco_banca_abbinata_chiude_il_ciclo_e_finisce(differita, exchange_it):
    b = BancoMedia()
    viol = _posizione_a(b, differita)
    b.pt = KO_MS + 1000
    b.in_gioco()
    viol += giri(b, differita, 2)
    b.ladder[b.under] = (1.46, 1.47)
    b.scambia(b.under, 1.48, 2000)
    viol += giri(b, differita, 5)
    assert viol == []
    assert b.strat.stato == MU.FINE
    assert b.kinds("media_banca_abbinata") and b.kinds("media_ciclo_chiuso")
    assert len(b.ordini()) == 2
    # chiuso in gioco = finito subito: il passaggio in gioco si annuncia UNA volta
    assert len(b.kinds("media_live")) == 1


def test_in_gioco_sospensione_e_banca_caduta_si_dicono(differita, exchange_it):
    b = BancoMedia()
    _posizione_a(b, differita)
    banca = b.vivi("LAY")[0]
    b.pt = KO_MS + 1000
    b.in_gioco()
    giri(b, differita, 2)
    b.stato = "SUSPENDED"
    giri(b, differita, 3)
    # Betfair annulla la banca durante la sospensione (il banco: size_lapsed)
    banca.simulated.size_lapsed += float(banca.size_remaining)
    b.stato = "OPEN"
    giri(b, differita, 3)
    sosp = b.kinds("media_sospeso")
    assert len(sosp) == 1 and sosp[0]["level"] == "CRITICAL"
    assert len(b.kinds("media_riaperto")) == 1
    caduta = b.kinds("media_banca_caduta")
    assert len(caduta) == 1 and "non e' piu' a mercato" in caduta[0]["msg"]
    assert b.strat.stats["banca"]["stato"] == "caduta"
    assert b.strat.stats["chiusura"]["banca"]["testo"] == "la banca non e' piu' a mercato"
    assert len(b.ordini()) == 2           # nessun ordine nuovo


def test_nessuna_chiusura_forzata_prima_del_fischio(differita, exchange_it):
    """La chiusura forzata dello scalper (`flatten_before_s`) non vale: dentro i
    3 minuti prima del fischio la posizione resta con la sua banca, nessun
    ordine di chiusura; dentro la finestra di stop nessun rientro."""
    b = BancoMedia()
    viol = _posizione_a(b, differita)
    n = len(b.ordini())
    b.pt = KO_MS - 170_000
    b.ladder[b.under] = (1.54, 1.55)
    viol += giri(b, differita, 60)
    assert viol == []
    assert len(b.ordini()) == n
    assert len(b.vivi("LAY")) == 1


def test_esito_ignoto_mai_un_secondo_ordine(differita, exchange_it):
    b = BancoMedia()
    giri(b, differita, 61)
    differita.ritardo = 10_000            # nessun esito: la punta resta PENDING
    giri(b, differita, 80)
    assert len(b.ordini()) == 1
    assert str(b.ordini()[0].status.value) == "Pending"
    assert b.kinds("media_annullo") == []


def test_rifiuto_freno_mai_un_ripiazzo_a_ogni_giro(differita):
    """Un piazzamento rifiutato (controllo di flumine: place_order False, mai nel
    blotter): nessuna posizione creduta, freno 1-2-4-8 s, CRITICAL al primo."""
    b = BancoMedia()
    controllo = R._controllo_rifiuti(b.fw, 3)
    b.fw.trading_controls.append(controllo)
    giri(b, differita, 55)
    istanti: List[int] = []
    for _i in range(30):
        prima = len(controllo.rifiutati)
        giri(b, differita, 1)
        if len(controllo.rifiutati) > prima:
            istanti.append(b.pt)
    rif = b.kinds("media_rifiuto")
    assert [r["riprovo_fra_s"] for r in rif] == [1, 2, 4]
    assert rif[0]["level"] == "CRITICAL" and rif[1]["level"] == "WARN"
    assert len(controllo.rifiutati) == 3 and len(istanti) == 3
    # i tentativi sono distanziati dal freno (1 s, poi 2 s; senza freno uno a
    # ogni book: 1 s e 1 s)
    assert [istanti[1] - istanti[0], istanti[2] - istanti[1]] == [1000, 2000]
    assert len(_punte(b)) == 1           # solo la quarta e' partita


def test_soldi_veri_fermati_senza_ordini_reali_la_banca_parte(differita, exchange_it):
    b = BancoMedia()
    b.strat.freno_live = lambda: "live_order_mode_non_live:PAPER"
    giri(b, differita, 80)
    assert b.ordini() == []
    crit = b.kinds("apertura_live_fermata")
    assert len(crit) == 1 and crit[0]["level"] == "CRITICAL"
    # a posizione aperta: niente rientro col freno, la banca (chiusura) parte
    b2 = BancoMedia()
    _posizione_a(b2, differita)
    b2.strat.freno_live = lambda: "kill_switch"
    _sali(b2, differita, [1.52])
    assert len(_punte(b2)) == 1
    assert len(b2.vivi("LAY")) == 1
    assert b2.kinds("apertura_live_fermata")


def test_riavvio_a_posizione_aperta_non_ricostruibile_nessun_ordine(differita):
    stats = {"media_stato": MU.MASSIMO, "media_totale_puntato": 321.0,
             "media_banca": {"stato": "viva"}}
    motivo = MU.posizione_aperta_nelle_stats(stats)
    assert motivo and "MASSIMO" in motivo
    for stato, puntato in ((MU.INGRESSO, 0.0), (MU.IN_POSIZIONE, 10.0),
                           (MU.RIENTRO, 20.0), (MU.LIVE, 40.0)):
        assert MU.posizione_aperta_nelle_stats({"media_stato": stato,
                                                "media_totale_puntato": puntato}), stato
    assert MU.posizione_aperta_nelle_stats({"media_stato": MU.FERMO,
                                            "media_totale_puntato": 0.0}) is None
    assert MU.posizione_aperta_nelle_stats({"media_stato": MU.FINE,
                                            "media_totale_puntato": 10.0}) is None
    assert MU.posizione_aperta_nelle_stats({"pnl_locked": 1.0}) is None
    b = BancoMedia(riavvio_aperto=motivo)
    giri(b, differita, 120)
    assert b.ordini() == []
    assert b.strat.stato == MU.BLOCCATA
    righe = b.kinds("media_riavvio_non_ricostruibile")
    assert len(righe) == 1 and righe[0]["level"] == "CRITICAL"
    assert b.strat.stats["chiusura"] is None and b.strat.stats["riavvio"] == motivo


def test_sospeso_prima_del_fischio_nessun_ordine(differita):
    b = BancoMedia()
    giri(b, differita, 30)
    b.stato = "SUSPENDED"
    giri(b, differita, 60)
    assert b.ordini() == []
    assert len(b.kinds("media_sospeso")) == 1


def test_mercato_regolato_esito_dal_risultato(differita, exchange_it):
    b = BancoMedia()
    _posizione_a(b, differita)
    from types import SimpleNamespace

    # flumine chiama anche per gli altri mercati della sessione: il Match Odds
    # chiuso non e' l'esito della modalita'
    mo = SimpleNamespace(market_id="1.300000001",
                         runners=[SimpleNamespace(selection_id=58805, status="WINNER")])
    b.strat.process_closed_market(SimpleNamespace(market_id="1.300000001"), mo)
    assert b.strat.stats["esito_regolato"] is None and b.strat.stato == MU.IN_POSIZIONE
    assert b.strat.is_flat() is False
    libro = SimpleNamespace(market_id=b.mid,
                            runners=[SimpleNamespace(selection_id=b.under, status="WINNER"),
                                     SimpleNamespace(selection_id=b.over, status="LOSER")])
    b.strat.process_closed_market(b.market, libro)
    assert b.strat.stats["esito_regolato"] == {"stato_selezione": "WINNER", "lordo": 5.0}
    assert b.strat.is_flat() is True and b.strat.stato == MU.FINE


# ===========================================================================
# 4. LA SESSIONE VERA (fino all'armamento) e l'AUTO-MODE
# ===========================================================================
EVENTO = "35999999"


def _catalogo():
    defs = {
        "1.300000001": {"market_type": "MATCH_ODDS", "runners": [(11, 1), (12, 2), (58805, 3)]},
        "1.300000025": {"market_type": "OVER_UNDER_25", "runners": [(47972, 1), (47973, 2)]},
        "1.300000035": {"market_type": "OVER_UNDER_35", "runners": [(1222344, 1), (1222345, 2)]},
    }
    follow = {"event_id": EVENTO, "fixture_id": None, "league_id": None,
              "home_name": "A", "away_name": "B", "open_date": "2025-09-29T10:00:00.000Z"}
    return R.catalogo_dal_raw(defs), follow


@pytest.fixture
def soldi_veri_dichiarati():
    from Betfair.stream.backtest.certifica import _freni_da_banco

    with _freni_da_banco():
        yield


@pytest.mark.usefixtures("soldi_veri_dichiarati")
def test_la_sessione_arma_solo_la_modalita_e_paper_uguale_live():
    cat, follow = _catalogo()
    # 07/10: gli scenari del pulsante <<Attiva adesso>> (sessione armata dal
    # pulsante: ATTESA_CLIC) hanno il loro test in
    # ``test_replay_scalper_attiva_adesso_2026_10_07.py``
    for sc in [s for s in R.SCENARI_MEDIA if s not in R.SCENARI_MEDIA_CLIC]:
        ctl = R.control_della_ui(EVENTO, sc)
        par, cli = R.arma_e_cattura(EVENTO, ctl, follow, cat)
        assert par["stato"] == MU.FERMO and "flow_window_ms" in par, sc
        # i parametri della modalita' entrano nel confronto paper/live (S6)
        assert par["parametri"]["mercato"] == R.mercato_media(sc), sc
        assert par["parametri"]["stake"] == 10.0
        assert cli["paper_trade"] is (sc == R.SCENARIO_MEDIA_PAPER)
    p = R.parita_paper_live(EVENTO, R.control_della_ui(EVENTO, R.SCENARIO_MEDIA), follow, cat)
    assert not p.get("errore"), p
    assert p["parametri_diversi"] == [] and p["client_diversi"] == []
    assert p["paper_trade_paper"] is True and p["paper_trade_live"] is False


@pytest.mark.usefixtures("soldi_veri_dichiarati")
def test_modalita_spenta_nessun_effetto_la_sessione_arma_il_maker():
    cat, follow = _catalogo()
    par, _cli = R.arma_e_cattura(EVENTO, R.control_della_ui(EVENTO, "base"), follow, cat)
    assert "scalp_ticks" in par and "flow_window_ms" in par and "stato" not in par


def test_la_sessione_non_parte_con_un_parametro_mancante():
    cat, follow = _catalogo()
    ctl = R.control_della_ui(EVENTO, R.SCENARIO_MEDIA_PAPER)
    ctl["params"].pop("media_mercato")
    with pytest.raises(RuntimeError, match="media under non avviata: parametri mancanti"):
        R.arma_e_cattura(EVENTO, ctl, follow, cat)


def test_la_sessione_rifiuta_una_riga_armata_dall_auto_mode():
    cat, follow = _catalogo()
    ctl = dict(R.control_della_ui(EVENTO, R.SCENARIO_MEDIA_PAPER), origine="auto")
    with pytest.raises(RuntimeError, match="auto-mode"):
        R.arma_e_cattura(EVENTO, ctl, follow, cat)


def test_l_auto_mode_non_passa_mai_le_chiavi_della_modalita():
    p = params_di_serie()
    p.update({"auto_max_partite": 2, "sniper_mode": True, "min_size": 300})
    out = AM.params_per_sessione(p)
    assert [k for k in out if k.startswith("media_")] == []
    assert out == {"sniper_mode": True, "min_size": 300}
    # nessun altro valore cambia
    assert AM.params_per_sessione({"min_size": 300, "auto_max_partite": 3}) == {"min_size": 300}


def test_vita_della_sessione_fino_a_fine_partita():
    ctl = R.control_della_ui(EVENTO, R.SCENARIO_MEDIA)
    assert R._vita_da_control(ctl) == AM.VITA_SNIPER_THETA_S
    assert R._vita_da_control(R.control_della_ui(EVENTO, "base")) == AM.VITA_MAKER_S


def test_registrata_nel_banco_e_scenari_riconosciuti():
    from Betfair.stream.backtest import registro_bot as REG

    scheda = REG.bot("scalper_calcio")
    assert "Betfair.stream.scalper.media_under_bot" in scheda.moduli_produzione
    for sc in (R.SCENARIO_MEDIA, R.SCENARIO_MEDIA_PAPER, R.SCENARIO_MEDIA_35):
        assert sc in scheda.elenco_scenari()
    assert R.mercato_media(R.SCENARIO_MEDIA_35) == "OVER_UNDER_35"
    assert R.mercato_media("base") is None
    assert [c for c, _r in CERT.elenco_controlli_media()] == [
        "M1", "M2", "M3", "M4", "M5", "M6", "M11", "M7", "M8", "M9", "M10",
        "M19", "M20", "M21"]   # M10 giro 2, M11 giro 3, M19-M21 banca spostata (07/10)
    # il registro del maker non cambia: la copertura dei 15 scenari resta quella
    assert not any(c.startswith("M") for c, _r in CERT.elenco_controlli())
    assert CERT.ESCLUSI_MEDIA == {"B2", "K5"}


# ===========================================================================
# 5. I CONTROLLI M del banco su ordini VERI (e la loro falsificazione)
# ===========================================================================
def _oss(b: BancoMedia, **kw: Any) -> CERT.OsservazioneMedia:
    righe = []
    for i, o in enumerate(b.ordini()):
        r = CERT.riga_ordine(o, True)
        r["indice"] = i
        r["creato_ms"] = b.nati[str(o.id)]     # l'ora di MERCATO (come il replay)
        righe.append(r)
    par, _m = MU.leggi_parametri(params_di_serie(b.mercato, **kw.pop("params", {})))
    base = dict(quando="t", ms=b.pt, params=par, mercato_scelto=b.mid,
                tipo_mercato={b.mid: b.mercato}, under=b.under, ordini=righe,
                nuovi={r["order_id"] for r in righe}, ko_ms=KO_MS)
    base.update(kw)
    return CERT.OsservazioneMedia(**base)


def _codici(oss: CERT.OsservazioneMedia, sollecitati: Dict[str, int] = None) -> List[str]:
    return [v.codice for v in CERT.verifica_media(oss, sollecitati)]


def test_controlli_m_muti_sul_bot_vero_e_tutti_sollecitati(differita, exchange_it):
    b = BancoMedia()
    _posizione_a(b, differita)
    _sali(b, differita, [1.52, 1.54])
    giri(b, differita, 6)                  # la banca esce dal volo
    sol: Dict[str, int] = {}
    oss = _oss(b, nuovi=set())
    assert _codici(oss, sol) == []
    for c in ("M1", "M2", "M3", "M4", "M5", "M6", "M8"):
        assert sol.get(c), c
    # in gioco, nessun ordine nuovo
    b.pt = KO_MS + 1000
    b.in_gioco()
    giri(b, differita, 5)
    sol2: Dict[str, int] = {}
    assert _codici(_oss(b, nuovi=set(), in_gioco_ms=KO_MS), sol2) == []
    assert sol2.get("M7")


def test_controlli_m_rossi_sui_difetti(differita, exchange_it):
    """Falsificazione dei controlli M sugli ordini VERI: ognuno diventa rosso sul
    difetto che difende."""
    b = BancoMedia()
    _posizione_a(b, differita)
    _sali(b, differita, [1.52, 1.54])
    giri(b, differita, 6)                  # la banca esce dal volo
    # M1: un altro mercato / l'Over
    assert "M1" in _codici(_oss(b, mercato_scelto="1.999"))
    assert "M1" in _codici(_oss(b, under=b.over))
    # M2: massimo 1 con due rientri abbinati; rischio massimo 30 superato
    assert "M2" in _codici(_oss(b, params={"media_max_rientri": 1}))
    assert "M2" in _codici(_oss(b, params={"media_rischio_max": 30.0}))
    # M3: rientro a 2 tick con 3 tick richiesti
    assert "M3" in _codici(_oss(b, params={"media_tick_rientro": 3}))
    # M4: l'obiettivo dichiarato diverso cambia l'importo voluto
    assert "M4" in _codici(_oss(b, params={"media_obiettivo": 5.0}))
    # M6: la banca a 2 tick con 3 tick dichiarati (stessa banca, regola diversa).
    # 06/10 (giro 3): con 1 tick dichiarato la banca a 1,52 e' GIUSTA (la quota
    # media 1,525 comanda: tick sotto la media 1,52 < 1,53), non piu' un difetto
    assert "M6" in _codici(_oss(b, params={"media_tick_chiusura": 3}))
    assert "M6" not in _codici(_oss(b, params={"media_tick_chiusura": 1}))
    # M7: un ordine nato in gioco; un annullo in gioco
    assert "M7" in _codici(_oss(b, in_gioco_ms=KO_MS - 3_700_000))
    assert "M7" in _codici(_oss(b, in_gioco_ms=b.pt - 1, annullati_in_gioco=["x"]))
    # M9: punte nate dentro la finestra di stop (fischio anticipato) o dopo il force-flat
    assert "M9" in _codici(_oss(b, ko_ms=b.pt))
    assert "M9" in _codici(_oss(b, force_flat_ms=KO_MS - 3_700_000))


def test_controlli_m6_importo_e_quota_ognuno_da_solo(differita, exchange_it):
    """M6 guarda DUE cose della banca appoggiata: la quota (ultimo ingresso - tick)
    e il resto (pareggio della posizione vera). Ognuna diventa rossa da sola."""
    b = BancoMedia()
    _posizione_a(b, differita)
    giri(b, differita, 6)
    oss = _oss(b, nuovi=set())
    assert _codici(oss) == []
    banca = next(r for r in oss.ordini if r["side"] == "LAY")
    giusto = dict(banca)
    banca["size_remaining"] = round(banca["size_remaining"] - 0.50, 2)   # importo sbagliato
    assert "M6" in _codici(oss)
    banca.clear()
    banca.update(giusto)
    banca["price"] = 1.49                                                 # quota sbagliata
    assert "M6" in _codici(oss)


def test_controlli_m5_m8_rossi_su_ordini_veri_sbagliati(differita):
    """M5 e M8: due banche vive e una banca LAPSE, piazzate a mano sul flumine
    vero (difetti che la strategia non fa)."""
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    b = BancoMedia()
    giri(b, differita, 2)
    for prezzo in (1.48, 1.47):
        tr = Trade(b.mid, b.under, 0, b.strat)
        o = tr.create_order("LAY", LimitOrder(prezzo, 5.0, persistence_type="LAPSE"))
        b.market.place_order(o)
    differita()
    b.book()
    cod = _codici(_oss(b))
    assert "M5" in cod and "M8" in cod


def test_il_ponte_del_replay_giudica_la_modalita(differita, exchange_it):
    """``_Banco.controlli_media`` (il pezzo del replay) sugli ordini VERI della
    strategia: muto sulla condotta giusta, rosso con un parametro della riga
    diverso da quello eseguito (nessuna registrazione: il quadro e' il flumine
    del banco di prova)."""
    from Betfair.stream.backtest import banco_comune as BC

    b = BancoMedia()
    _posizione_a(b, differita)
    _sali(b, differita, [1.52])
    orologio = R._Orologio()
    for params, rosso in ((params_di_serie(), False),
                          (params_di_serie(media_tick_rientro=4), True)):
        ctl = {"event_id": EVENTO, "status": "running", "mode": "maker", "dry_run": True,
               "stake": 25, "params": params}
        db = R._DbFinto(orologio, ctl, {"event_id": EVENTO})
        ref = CERT.Referto(event_id=EVENTO, scenario=R.SCENARIO_MEDIA)
        with BC.simulazione_flumine():
            banco = R._Banco(event_id=EVENTO, raw="", scenario=R.SCENARIO_MEDIA, ogni_ms=0,
                             referto=ref, orologio=orologio, db=db, catalogo=[],
                             ko_ms=KO_MS)
        banco.quadro = b.fw
        banco.mercati_catalogo = [b.mid]
        banco.media = b.strat
        banco.media_mercato_scelto, banco.media_under = b.mid, b.under
        banco.tipo_mercato = {b.mid: b.mercato}
        # il GIRO del banco (quello che il ponte chiama alla cadenza): i controlli M
        # passano da qui anche senza la sessione del maker
        banco.giro(b.pt, "t")
        codici = {v.codice for v in ref.violazioni}
        assert ("M3" in codici) is rosso, (params, codici)
        assert ref.sollecitati.get("M1")
