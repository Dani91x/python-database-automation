"""MEDIA UNDER, terzo giro (06/10/2026): <<e' sempre la quota media che comanda>>.

Regola dell'utente (sostituisce il punto Q1 del referto del giro 2): la banca di
chiusura si calcola sulla posizione REALE abbinata e va al PIU' BASSO fra
<<ultimo ingresso - N tick>> e <<quota media arrotondata al tick inferiore>>,
cosi' e' sempre in profitto; quando la banca si appoggia ogni resto non
abbinato delle punte si annulla e la banca copre l'intera posizione. Con i
rientri abbinati per intero il comportamento resta quello di prima (vettore A).

Stesso banco dei giri 1 e 2 (``banco_media_under.BancoMedia``: flumine VERO col
client paper della sessione, strategia VERA, book nativi Betfair, esecuzione
differita di 1 e 4 book, minimi .it del banco).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from Betfair.stream.backtest import minimi_banco as MB
from Betfair.stream.scalper import certificazione as CERT
from Betfair.stream.scalper import media_under_bot as MU
from Betfair.stream.tennis_live.tests.test_cantiere_t_pro_residuo_2026_09_28 import (  # noqa: F401
    esecuzione_differita,
)
from Betfair.stream.tests.banco_media_under import KO_MS, BancoMedia, giri, params_di_serie


@pytest.fixture(params=[1, 4])
def differita(request, esecuzione_differita):
    """Esecuzione dei pacchetti di flumine differita di 1 e di 4 book."""
    esecuzione_differita.ritardo = request.param
    return esecuzione_differita


@pytest.fixture
def exchange_it():
    with MB.minimi_it_su_flumine() as registro:
        yield registro


def _punte(b: BancoMedia) -> List[Any]:
    return [o for o in b.ordini() if MU._lato(o) == "BACK"]


def _banche(b: BancoMedia) -> List[Any]:
    return [o for o in b.ordini() if MU._lato(o) == "LAY"]


def _lordo(pos: MU.Posizione, c: float) -> float:
    """Il profitto lordo con la banca al centesimo a ``c`` abbinata per intero."""
    banca = MU.al_centesimo(MU.banca_esatta(pos, c))
    w, l = MU.profitto_lordo_con_banca(pos, banca, c)
    return min(w, l)


# ===========================================================================
# 1. le formule: l'esempio dell'utente e il caso normale
# ===========================================================================
def test_esempio_dell_utente_la_media_comanda():
    """Punte 10 @2,18, 10 @2,20, 20 @2,22 e 2,99 abbinati su 40 @2,24 (rientro
    abbinato in parte): media 2,2074 -> banca sull'intera posizione a 2,20 ->
    +0,14. Prima (ultimo ingresso - 1 tick = 2,22): -0,25."""
    pos = MU.posizione_da_importi([(10, 2.18), (10, 2.20), (20, 2.22), (2.99, 2.24)])
    assert pos.quota_media == pytest.approx(2.2074, abs=1e-4)
    assert MU.tick_sotto_la_media(pos.quota_media) == 2.20
    for n in (1, 2):
        assert MU.quota_della_banca(2.24, pos, n) == 2.20
    assert MU.al_centesimo(MU.banca_esatta(pos, 2.20)) == 43.14
    assert _lordo(pos, 2.20) == pytest.approx(0.14, abs=0.005)
    # la regola di prima: ultimo ingresso - 1 tick, in perdita
    assert MU.tick_sotto(2.24, 1) == 2.22
    assert MU.al_centesimo(MU.banca_esatta(pos, 2.22)) == 42.75
    assert _lordo(pos, 2.22) == pytest.approx(-0.25, abs=0.005)


VETTORE_A = [
    # quota, punta, quota banca (giro 1, spec par.4 A: invariato)
    (1.52, 10.00, 1.50), (1.54, 20.00, 1.52), (1.56, 40.00, 1.54),
    (1.58, 80.50, 1.56), (1.60, 160.50, 1.58),
]


def test_vettore_a_rientri_per_intero_quota_invariata():
    """Coi rientri abbinati per intero la media sta sopra <<ultimo ingresso - N
    tick>>: la banca resta dove era (1,48 / 1,50 / 1,52 / 1,54 / 1,56 / 1,58)."""
    punte = [(10.0, 1.50)]
    pos = MU.posizione_da_importi(punte)
    assert MU.quota_della_banca(1.50, pos, 2) == MU.tick_sotto(1.50, 2) == 1.48
    for q, x, c in VETTORE_A:
        punte.append((x, q))
        pos = MU.posizione_da_importi(punte)
        assert MU.quota_della_banca(q, pos, 2) == MU.tick_sotto(q, 2) == c, (q, pos)
        assert _lordo(pos, c) > 0


def test_media_esattamente_su_un_tick_va_al_tick_sotto():
    """Scelta mia (referto): <<arrotondata al tick inferiore>> = il tick
    STRETTAMENTE sotto la media; 10 @2,18 + 10 @2,22 = media 2,20 esatta ->
    2,18 (chiudere a 2,20 darebbe zero, non profitto)."""
    pos = MU.posizione_da_importi([(10, 2.18), (10, 2.22)])
    assert pos.quota_media == pytest.approx(2.20)
    assert MU.tick_sotto_la_media(pos.quota_media) == 2.18
    assert MU.quota_della_banca(2.22, pos, 1) == 2.18
    assert _lordo(pos, 2.18) > 0
    assert _lordo(pos, 2.20) <= 0.005


# ===========================================================================
# 2. la strategia su flumine VERO
# ===========================================================================
def test_rientro_in_parte_resto_annullato_banca_sotto_la_media_in_profitto(differita,
                                                                           exchange_it):
    """Il caso del replay `media-under-tick-1` (giro 2) sul banco: chiusura a 1
    tick, punta 10 @1,50, rientro a 1,52 con 4 sul book. Si abbina 4: la banca
    si appoggia e il resto si annulla; la media 1,5057 comanda: banca
    a 1,50 (non 1,51) sull'intera posizione; abbinata, il ciclo chiude in
    PROFITTO (prima: 1,51 e -0,04)."""
    b = BancoMedia(media_tick_chiusura=1)
    viol = giri(b, differita, 70)
    b.taglie[(b.under, 1.52)] = 4.0
    b.ladder[b.under] = (1.52, 1.53)
    viol += giri(b, differita, 20, flusso=0.0)
    assert viol == [], viol[:3]
    punta = _punte(b)[1]
    assert float(punta.size_matched) == pytest.approx(4.0)
    assert not MU.vivo_o_in_volo(punta)
    assert float(punta.order_type.price) == 1.52
    assert float(punta.size_cancelled) == pytest.approx(float(punta.order_type.size) - 4.0)
    resti = [p for p in b.kinds("media_annullo") if p.get("side") == "BACK"
             and str(p.get("motivo", "")).startswith("banca appoggiata: il resto")]
    assert len(resti) == 1 and resti[0]["prezzo"] == 1.52
    pos = b.posizione()
    assert pos.puntato == pytest.approx(14.0)
    vive = b.vivi("LAY")
    assert [(float(o.order_type.price), float(o.size_remaining)) for o in vive] == [
        (1.50, MU.al_centesimo(MU.banca_esatta(pos, 1.50)))]
    banche = b.kinds("media_banca")
    assert banche[-1]["prezzo"] == 1.50 and banche[-1]["dalla_media"] is True
    assert "sotto la quota media" in banche[-1]["msg"]
    # la quota scende: la banca a 1,50 si abbina e il ciclo chiude in profitto
    b.ladder[b.under] = (1.49, 1.50)
    b.scambia(b.under, 1.50, 3000)
    viol += giri(b, differita, 10)
    assert viol == [], viol[:3]
    chiusi = b.kinds("media_ciclo_chiuso")
    assert len(chiusi) == 1 and chiusi[0]["profitto_lordo"] > 0
    assert chiusi[0]["msg"].startswith("ciclo chiuso in profitto")


def test_rientri_per_intero_banca_dove_era(differita, exchange_it):
    """Vettore A su flumine: con i rientri abbinati per intero nessuna banca
    viene dalla media e nessun resto di punta si annulla."""
    b = BancoMedia()
    viol = giri(b, differita, 70)
    for q in (1.52, 1.54, 1.56):
        b.ladder[b.under] = (q, round(q + 0.01, 2))
        viol += giri(b, differita, 12)
    assert viol == [], viol[:3]
    assert [(float(o.order_type.price), float(o.order_type.size)) for o in _banche(b)] == [
        (1.48, 10.14), (1.50, 20.13), (1.52, 40.13), (1.54, 80.13)]
    assert all(p["dalla_media"] is False for p in b.kinds("media_banca"))
    assert not [p for p in b.kinds("media_annullo") if p.get("side") == "BACK"]


# ===========================================================================
# 3. il controllo del banco M11 (e M6 con la regola nuova)
# ===========================================================================
def _oss(b: BancoMedia, righe: List[Dict[str, Any]] = None, **kw: Any) -> CERT.OsservazioneMedia:
    """L'osservazione del giro del banco dagli ordini VERI (righe di
    ``riga_ordine`` con l'ora di mercato, come il replay)."""
    if righe is None:
        righe = []
        for i, o in enumerate(b.ordini()):
            r = CERT.riga_ordine(o, True)
            r["indice"] = i
            r["creato_ms"] = b.nati[str(o.id)]
            righe.append(r)
    par, _m = MU.leggi_parametri(params_di_serie(b.mercato, **kw.pop("params", {})))
    base = dict(quando="t", ms=b.pt, params=par, mercato_scelto=b.mid,
                tipo_mercato={b.mid: b.mercato}, under=b.under, ordini=righe,
                nuovi=set(), ko_ms=KO_MS)
    base.update(kw)
    return CERT.OsservazioneMedia(**base)


def _codici(oss: CERT.OsservazioneMedia, sollecitati: Dict[str, int] = None) -> List[str]:
    return [v.codice for v in CERT.verifica_media(oss, sollecitati)]


def test_m11_muto_sul_bot_vero_e_sollecitato(differita, exchange_it):
    b = BancoMedia(media_tick_chiusura=1)
    giri(b, differita, 70)
    b.taglie[(b.under, 1.52)] = 4.0
    b.ladder[b.under] = (1.52, 1.53)
    for _i in range(20):
        giri(b, differita, 1, flusso=0.0)
        sol: Dict[str, int] = {}
        oss = _oss(b, params={"media_tick_chiusura": 1})
        codici = _codici(oss, sol)
        assert "M11" not in codici and "M6" not in codici, codici
    assert sol.get("M11")


def test_m11_rosso_su_banca_non_in_profitto_e_su_resto_vivo(differita, exchange_it):
    b = BancoMedia(media_tick_chiusura=1)
    giri(b, differita, 70)
    b.taglie[(b.under, 1.52)] = 4.0
    b.ladder[b.under] = (1.52, 1.53)
    giri(b, differita, 20, flusso=0.0)
    oss = _oss(b, params={"media_tick_chiusura": 1})
    assert "M11" not in _codici(oss)
    banca = next(r for r in oss.ordini if r["side"].upper() == "LAY" and CERT._m_vivo(r))
    punta = next(r for r in oss.ordini if r["side"].upper() == "BACK"
                 and float(r["price"]) == 1.52)
    # (a) la stessa banca alla regola vecchia (1,51 = ultimo ingresso - 1 tick):
    # sopra la media 1,5057, chiusura in perdita
    righe = [dict(r) for r in oss.ordini]
    next(r for r in righe if r["order_id"] == banca["order_id"])["price"] = 1.51
    assert "M11" in _codici(_oss(b, righe=righe, params={"media_tick_chiusura": 1}))
    # (b) il resto della punta di rientro ancora VIVO sul book accanto alla banca
    righe = [dict(r) for r in oss.ordini]
    r_p = next(r for r in righe if r["order_id"] == punta["order_id"])
    r_p.update({"status": "Executable", "size_remaining": 6.0, "size_cancelled": 0.0})
    assert "M11" in _codici(_oss(b, righe=righe, params={"media_tick_chiusura": 1}))
    # ... ma con l'annullo gia' chiesto (in viaggio) non e' un difetto
    r_p["status"] = "Cancelling"
    assert "M11" not in _codici(_oss(b, righe=righe, params={"media_tick_chiusura": 1}))


def test_m6_vuole_la_quota_della_media(differita, exchange_it):
    """M6 con la regola nuova: la banca del bot (1,50, dalla media) e' giusta;
    la stessa banca a 1,51 (la regola vecchia) e' rossa."""
    b = BancoMedia(media_tick_chiusura=1)
    giri(b, differita, 70)
    b.taglie[(b.under, 1.52)] = 4.0
    b.ladder[b.under] = (1.52, 1.53)
    giri(b, differita, 20, flusso=0.0)
    oss = _oss(b, params={"media_tick_chiusura": 1})
    assert "M6" not in _codici(oss)
    righe = [dict(r) for r in oss.ordini]
    banca = next(r for r in righe if r["side"].upper() == "LAY" and CERT._m_vivo(r))
    banca["price"] = 1.51
    memoria = CERT.Memoria()
    codici: List[str] = []
    for _i in range(3):            # M6 e' persistente: rosso se si conferma
        codici += [v.codice for v in CERT.verifica_media(
            _oss(b, righe=righe, params={"media_tick_chiusura": 1}), {}, memoria)]
    assert "M6" in codici


# ===========================================================================
# 4. i due replay dichiarati chiesti dall'utente
# ===========================================================================
@pytest.mark.parametrize("nome, base, diversi, mercato", [
    ("media-under-liquidita-100", "media-under", {"media_min_size": 100.0}, "OVER_UNDER_25"),
    ("media-under-35-liquidita-50", "media-under-35", {"media_min_size": 50.0},
     "OVER_UNDER_35"),
])
def test_scenari_di_liquidita_cambiano_solo_la_liquidita(nome, base, diversi, mercato):
    from Betfair.stream.backtest import registro_bot as REG
    from Betfair.stream.scalper.tools import replay_registrazioni as R

    assert nome in REG.bot("scalper_calcio").elenco_scenari()
    assert R.mercato_media(nome) == mercato
    vb, vn = R.control_della_ui("1", base), R.control_della_ui("1", nome)
    assert {k: v for k, v in vn["params"].items() if vb["params"].get(k) != v} == diversi
    assert {k: v for k, v in vn.items() if k != "params"} == \
        {k: v for k, v in vb.items() if k != "params"}
    assert R.guasto_dello_scenario(nome) == nome
