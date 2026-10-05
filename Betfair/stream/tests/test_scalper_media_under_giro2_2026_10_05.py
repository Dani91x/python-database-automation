"""MEDIA UNDER, secondo giro (05/10/2026): i buchi dei test trovati dal revisore.

Spec: ``Betfair/stream/scalper/SPEC_MEDIA_UNDER_GIRO2_2026-10-05.md`` par.2.1.
Stesso banco dei test del primo giro (``banco_media_under.BancoMedia``: flumine
VERO col client paper della sessione, strategia VERA, book nativi di Betfair,
esecuzione differita di 1 e 4 book, minimi .it del banco).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

from typing import Any, List

import pytest

from Betfair.stream.backtest import minimi_banco as MB
from Betfair.stream.scalper import media_under_bot as MU
from Betfair.stream.tennis_live.tests.test_cantiere_t_pro_residuo_2026_09_28 import (  # noqa: F401
    esecuzione_differita,
)
from Betfair.stream.tests.banco_media_under import BancoMedia, giri


@pytest.fixture(params=[1, 4])
def differita(request, esecuzione_differita):
    """Esecuzione dei pacchetti di flumine differita di 1 e di 4 book."""
    esecuzione_differita.ritardo = request.param
    return esecuzione_differita


@pytest.fixture
def exchange_it():
    with MB.minimi_it_su_flumine() as registro:
        yield registro


def _banche(b: BancoMedia) -> List[Any]:
    return [o for o in b.ordini() if MU._lato(o) == "LAY"]


def _punte(b: BancoMedia) -> List[Any]:
    return [o for o in b.ordini() if MU._lato(o) == "BACK"]


# ===========================================================================
# 2.1 a) quota salita MENO di N tick dall'ultimo ingresso: la banca resta
# ===========================================================================
def test_quota_su_di_meno_di_n_tick_la_banca_resta_ferma(differita, exchange_it):
    """Punta 10 @1,50, banca 10,14 @1,48. La quota sale di UN tick (1,51) e ci
    resta 40 book: nessun annullo, nessun ordine nuovo, sempre la stessa banca
    viva, stato IN_POSIZIONE a ogni book (N tick di rientro = 2)."""
    b = BancoMedia()
    viol = giri(b, differita, 70)
    assert viol == [], viol[:3]
    banca = b.vivi("LAY")[0]
    n_ordini = len(b.ordini())
    annulli = len(b.kinds("media_annullo"))
    b.ladder[b.under] = (1.51, 1.52)
    for i in range(40):
        viol += giri(b, differita, 1)
        assert b.strat.stato == MU.IN_POSIZIONE, (i, b.strat.stato)
        assert b.vivi("LAY") == [banca], i
    assert viol == [], viol[:3]
    assert len(b.kinds("media_annullo")) == annulli
    assert len(b.ordini()) == n_ordini
    assert b.kinds("media_rientro") == []
    assert float(banca.size_remaining) == pytest.approx(10.14)


# ===========================================================================
# 2.1 b) punta abbinata in due tempi: la banca si riallinea alla posizione vera
# ===========================================================================
def test_punta_abbinata_in_due_tempi_la_banca_si_riallinea(differita, exchange_it):
    """Rientro a 1,52 (punta 10,00) con solo 4 sul book a quel prezzo: si
    abbina 4, la banca va sulla posizione di quel momento (10 @1,50 + 4 @1,52).
    Poi gli scambi a 1,52 abbinano il resto: la banca vecchia si annulla, si
    aspetta che sia morta, la nuova e' per la posizione vera (20 puntati). Mai
    due banche vive insieme (invarianti del banco a ogni book)."""
    b = BancoMedia()
    viol = giri(b, differita, 70)
    b.taglie[(b.under, 1.52)] = 4.0
    b.ladder[b.under] = (1.52, 1.53)
    for _i in range(30):
        viol += giri(b, differita, 1, flusso=0.0)
        punte = _punte(b)
        if len(punte) == 2 and float(punte[1].size_matched) > 0 and len(_banche(b)) == 2 \
                and MU.eseguibile(_banche(b)[1]):
            break
    assert viol == [], viol[:3]
    punta = _punte(b)[1]
    assert (float(punta.order_type.price), float(punta.order_type.size)) == (1.52, 10.0)
    assert float(punta.size_matched) == pytest.approx(4.0)
    prima = _banche(b)[1]
    pos_parziale = MU.posizione_da_ordini([o for o in b.ordini() if o is not prima])
    assert float(prima.order_type.price) == 1.50
    assert float(prima.order_type.size) == pytest.approx(
        MU.al_centesimo(MU.banca_esatta(pos_parziale, 1.50)))
    # gli scambi a 1,52 abbinano il resto della punta
    b.scambia(b.under, 1.52, 2000)
    viol += giri(b, differita, 12, flusso=0.0)
    assert viol == [], viol[:3]
    assert float(punta.size_matched) == pytest.approx(10.0)
    assert not MU.vivo_o_in_volo(prima)
    assert float(prima.size_matched) == 0.0
    riallinea = [p for p in b.kinds("media_annullo")
                 if str(p.get("motivo", "")).startswith("banca da riallineare")]
    assert len(riallinea) == 1
    vive = b.vivi("LAY")
    pos = b.posizione()
    assert pos.puntato == pytest.approx(20.0)
    assert [(float(o.order_type.price), float(o.size_remaining)) for o in vive] == [
        (1.50, MU.al_centesimo(MU.banca_esatta(pos, 1.50)))]
    assert float(vive[0].order_type.size) == pytest.approx(20.13)


# ===========================================================================
# 2.2 il referto dei replay della modalita'
# ===========================================================================
from Betfair.stream.scalper import certificazione as CERT  # noqa: E402
from Betfair.stream.scalper.tools import replay_registrazioni as R  # noqa: E402
from Betfair.stream.tests.banco_media_under import (  # noqa: E402
    EVENTO, KO_MS, params_di_serie,
)


@pytest.mark.parametrize("kw, ladder, flusso, inizio, motivo", [
    ({"profondita": 200.0}, None, 20.0, None, "liquidita"),
    ({}, (1.50, 1.54), 20.0, None, "spread"),
    ({}, (4.20, 4.30), 20.0, None, "quota_fuori"),
    ({}, (1.15, 1.16), 20.0, None, "quota_fuori"),
    ({}, None, 0.0, None, "flusso"),
    ({}, None, 20.0, KO_MS - 420_000 - 30_000, "finestra_fischio"),
])
def test_motivi_di_non_ingresso_contati_per_filtro(differita, kw, ladder, flusso, inizio,
                                                   motivo):
    """Ogni filtro che ferma l'ingresso si conta col suo nome (stats
    ``non_ingresso``); il riscaldamento dei primi 60 s si conta a parte."""
    b = BancoMedia(**kw)
    if ladder:
        b.ladder[b.under] = ladder
    if inizio:
        b.pt = inizio
    giri(b, differita, 80, flusso=flusso)
    assert b.ordini() == []
    conti = b.strat.stats["non_ingresso"]
    assert conti.get(motivo, 0) > 0, conti
    # il primo filtro che non passa e' l'UNICO contato per quel book
    assert sum(conti.values()) <= 80
    if motivo in ("flusso",):
        assert conti.get("riscaldamento", 0) > 0, conti


def test_un_ingresso_regolare_conta_solo_il_riscaldamento(differita, exchange_it):
    b = BancoMedia()
    giri(b, differita, 70)
    assert len(_punte(b)) == 1
    assert set(b.strat.stats["non_ingresso"]) == {"riscaldamento"}, b.strat.stats


class _Ora:
    """Le attivita' della strategia col loro istante di MERCATO (come il tee
    del banco, ``_Banco.aggiungi_strategia``) e l'istante dell'ultimo
    abbinamento di ogni ordine (come ``_Banco.controlli_media``)."""

    def __init__(self, b: BancoMedia) -> None:
        self.b = b
        self.eventi: List[Any] = []
        self.abbinato_ms = {}
        self._visto = {}
        vero = b.strat.event_sink
        b.strat.event_sink = lambda k, p: (self.eventi.append((k, dict(p), b.pt)), vero(k, p))

    def giri(self, svuota: Any, n: int, **kw: Any) -> List[str]:
        viol: List[str] = []
        for _i in range(n):
            viol += giri(self.b, svuota, 1, **kw)
            for o in self.b.ordini():
                m = float(o.size_matched or 0.0)
                if m > self._visto.get(str(o.id), 0.0) + 1e-9:
                    self._visto[str(o.id)] = m
                    self.abbinato_ms[str(o.id)] = self.b.pt
        return viol


def _due_cicli(differita: Any) -> "tuple[BancoMedia, _Ora]":
    """Ciclo 1: 10 @1,50, banca 10,14 @1,48 abbinata (chiuso, +0,13). Ciclo 2:
    10 @1,47, rientro a 1,49, banca appoggiata non abbinata (aperto)."""
    b = BancoMedia()
    ora = _Ora(b)
    viol = ora.giri(differita, 70)
    b.ladder[b.under] = (1.47, 1.48)
    b.scambia(b.under, 1.48, 2000)
    viol += ora.giri(differita, 10)
    b.ladder[b.under] = (1.49, 1.50)
    viol += ora.giri(differita, 15)
    assert viol == [], viol[:3]
    return b, ora


def test_riepilogo_per_ciclo_dagli_ordini_veri(differita, exchange_it):
    b, ora = _due_cicli(differita)
    assert len(b.kinds("media_ciclo_chiuso")) == 1 and b.kinds("media_rientro")
    cicli, conto = R.riepilogo_cicli_media(
        b.ordini(), b.nati, ora.abbinato_ms, ora.eventi, ko_ms=KO_MS, in_gioco_ms=None,
        commissione=0.05, stato_runner=None)
    assert len(cicli) == 2
    c1, c2 = cicli
    assert c1["esito"] == "CHIUSO" and c1["lordo"] == pytest.approx(0.13, abs=0.006)
    assert c1["puntato"] == 10.0 and c1["rientri"] == []
    assert (c1["banca"]["importo"], c1["banca"]["quota"], c1["banca"]["abbinato"]) \
        == (10.14, 1.48, 10.14)
    assert "pre-match" in c1["banca"]["dove"]
    assert "ingresso 10.00 @1.50" in c1["riga"]
    rientro = b.kinds("media_rientro")[0]
    assert c2["rientri"] == [{"quota": 1.49, "esatto": rientro["importo_esatto"],
                              "piazzato": rientro["importo"], "abbinato": rientro["importo"]}]
    assert c2["puntato"] == pytest.approx(10.0 + rientro["importo"])
    assert c2["esito"] == "APERTO, esito ignoto" and c2["lordo"] is None
    assert c2["banca"]["abbinato"] == 0.0 and c2["banca"]["dove"] is None
    # il conto: solo il ciclo con esito noto, commissione sul netto vincente
    assert conto["cicli_esito_ignoto"] == 1
    assert (conto["lordo"], conto["commissione"], conto["netto"]) == (0.13, 0.01, 0.13)
    # col libro finale (Under perdente) il ciclo aperto entra nel conto
    _c, conto_l = R.riepilogo_cicli_media(
        b.ordini(), b.nati, ora.abbinato_ms, ora.eventi, ko_ms=KO_MS, in_gioco_ms=None,
        commissione=0.05, stato_runner="LOSER")
    perso = -(10.0 + rientro["importo"])
    assert conto_l["lordo"] == pytest.approx(round(0.1333 + perso, 2), abs=0.006)
    assert conto_l["commissione"] == 0.0 and conto_l["netto"] == conto_l["lordo"]
    assert conto_l["cicli_esito_ignoto"] == 0


def _banco_replay(b: BancoMedia, params: Any) -> "tuple[Any, CERT.Referto]":
    """Il ``_Banco`` VERO del replay sopra il flumine del banco di prova (come
    ``test_il_ponte_del_replay_giudica_la_modalita`` del primo giro)."""
    from Betfair.stream.backtest import banco_comune as BC

    orologio = R._Orologio()
    ctl = {"event_id": EVENTO, "status": "running", "mode": "maker", "dry_run": True,
           "stake": 25, "params": params}
    db = R._DbFinto(orologio, ctl, {"event_id": EVENTO})
    ref = CERT.Referto(event_id=EVENTO, scenario=R.SCENARIO_MEDIA)
    with BC.simulazione_flumine():
        banco = R._Banco(event_id=EVENTO, raw="", scenario=R.SCENARIO_MEDIA, ogni_ms=0,
                         referto=ref, orologio=orologio, db=db, catalogo=[], ko_ms=KO_MS)
    banco.quadro = b.fw
    banco.mercati_catalogo = [b.mid]
    banco.media = b.strat
    banco.medie = [b.strat]
    banco.media_mercato_scelto, banco.media_under = b.mid, b.under
    banco.tipo_mercato = {b.mid: b.mercato}
    return banco, ref


def test_referto_senza_ordini_e_non_esercitato_col_motivo(differita):
    b = BancoMedia(profondita=200.0)
    giri(b, differita, 80)
    banco, ref = _banco_replay(b, params_di_serie())
    R._referto_media(ref, banco)
    assert len(ref.non_esercitato) == 1
    assert "NESSUN ordine" in ref.non_esercitato[0]
    assert "liquidita'" in ref.non_esercitato[0]
    from Betfair.stream.backtest import certifica as CF

    assert CF.segno_referto(ref).strip() == "NE"
    assert any("motivi di non ingresso" in n for n in ref.note)


def test_referto_con_ordini_esercitato_riepilogo_e_netto(differita, exchange_it):
    b = BancoMedia()
    ora = _Ora(b)
    ora.giri(differita, 70)
    b.ladder[b.under] = (1.47, 1.48)
    b.scambia(b.under, 1.48, 2000)
    ora.giri(differita, 10)
    banco, ref = _banco_replay(b, params_di_serie())
    # le attivita' col loro istante (il tee del banco) e gli istanti di nascita
    # e di abbinamento degli ordini come li memorizza il giro del banco (qui dal
    # banco di prova: flumine non simulato timbra gli ordini con l'ora del PC)
    banco.attivita_media = ora.eventi
    banco.media_nati_ms = dict(b.nati)
    banco.media_abbinato_ms = dict(ora.abbinato_ms)
    R._referto_media(ref, banco)
    assert ref.non_esercitato == []
    from Betfair.stream.backtest import certifica as CF

    assert CF.segno_referto(ref).strip() == "OK", [(v.codice, v.dettaglio) for v in ref.violazioni][:3]
    cicli = [n for n in ref.note if n.startswith("MEDIA UNDER ciclo 1:")]
    assert len(cicli) == 1 and "[CHIUSO]" in cicli[0], ref.note
    netto = [n for n in ref.note if "NETTO" in n]
    # il ciclo 2 (nuovo ingresso dopo la chiusura) e' aperto: fuori dal conto, detto
    assert len(netto) == 1 and "NETTO +0.13 EUR + 1 cicli APERTI" in netto[0], netto
    assert ref.stats_finali["media_conto"]["netto"] == 0.13


def test_le_azioni_del_referto_sono_gli_ordini_della_modalita(differita, exchange_it):
    """Il ponte VERO del replay: ogni ordine piazzato dalla modalita' e' una
    azione del referto (prima restava 0: contava solo le attivita' del maker)."""
    b = BancoMedia()
    banco, ref = _banco_replay(b, params_di_serie())
    banco.sessioni.append((None, b.strat, (b.mid,)))
    ponte = R._Ponte(banco)
    for _i in range(70):
        differita()
        b.book(ponte=ponte)
    b.ladder[b.under] = (1.52, 1.53)
    for _i in range(20):
        differita()
        b.book(ponte=ponte)
    assert banco.errori_ponte == []
    n = int(b.strat.stats["ordini"])
    assert n >= 3 and len(b.ordini()) == n
    assert ref.azioni == n
    assert ref.decisioni > 0


# ===========================================================================
# 2.3 gli ordini messi a mano nel riquadro "chiusura" (solo soldi veri)
# ===========================================================================
from Betfair.stream.scalper import scalper_session as SS  # noqa: E402


def _riga_specchio(b: BancoMedia, **kw: Any) -> Any:
    """Una riga di ``betfair_live_orders`` nella forma VERA: quella che scrive
    ``reconcile_worker._account_order_row`` per un ordine visto solo sul conto
    (dal sito), colonne della migrazione ``betfair_live_order_queue.sql``."""
    riga = {
        "bet_id": "381234567890", "client_order_ref": "ext381234567890", "mode": "live",
        "source": "account", "market_id": b.mid, "selection_id": b.under, "handicap": 0.0,
        "side": "back", "order_type": "LIMIT", "price": 1.80, "size": 30.0,
        "size_matched": 30.0, "size_remaining": 0.0, "size_cancelled": 0.0,
        "size_lapsed": 0.0, "size_voided": 0.0, "average_price_matched": 1.80,
        "status": "EXECUTION_COMPLETE", "persistence": "LAPSE",
        "placed_at": "2025-09-29T09:50:00+00:00",
    }
    riga.update(kw)
    return riga


class _TabellaVera:
    """Il builder di supabase-py (select/eq/execute) su righe date, che conta
    le letture e ricorda i filtri chiesti; ``guasto`` = la lettura esplode."""

    def __init__(self, db: "_DbVero", nome: str) -> None:
        self.db, self.nome, self.filtri = db, nome, {}

    def select(self, colonne: str) -> "_TabellaVera":
        self.db.colonne = colonne
        return self

    def eq(self, k: str, v: Any) -> "_TabellaVera":
        self.filtri[k] = v
        return self

    def execute(self) -> Any:
        self.db.letture.append((self.nome, dict(self.filtri)))
        if self.db.guasto:
            raise RuntimeError("timeout PostgREST")
        righe = [r for r in self.db.righe
                 if all(str(r.get(k)) == str(v) for k, v in self.filtri.items())]
        return type("Risposta", (), {"data": righe})()


class _DbVero:
    def __init__(self, righe: List[Any], guasto: bool = False) -> None:
        self.righe, self.guasto = righe, guasto
        self.letture: List[Any] = []
        self.colonne = ""
        self.sb = self

    def table(self, nome: str) -> _TabellaVera:
        return _TabellaVera(self, nome)


def _al_massimo(differita: Any) -> BancoMedia:
    """Punta 10 @1,50 e un rientro: posizione aperta con la banca appoggiata,
    MASSIMO dei rientri (=1) raggiunto: il riquadro e' pubblicato."""
    b = BancoMedia(media_max_rientri=1)
    viol = giri(b, differita, 70)
    b.ladder[b.under] = (1.52, 1.53)
    viol += giri(b, differita, 15)
    assert viol == [] and b.strat.stato == MU.MASSIMO, (viol[:3], b.strat.stato)
    return b


def test_soldi_veri_righe_a_mano_entrano_solo_nel_riquadro(differita, exchange_it):
    b = _al_massimo(differita)
    pos_bot = b.posizione()
    ordini_prima = len(b.ordini())
    db = _DbVero([
        _riga_specchio(b),                                         # a mano dal sito
        _riga_specchio(b, bet_id="2", source="runner", side="lay", price=1.60,
                       size_matched=5.0, average_price_matched=1.60),   # terminale app
        _riga_specchio(b, bet_id="3", source="scalper", size_matched=99.0),  # la sessione
        _riga_specchio(b, bet_id="4", source="mike", size_matched=99.0),     # un altro bot
        _riga_specchio(b, bet_id="5", selection_id=b.over),                  # l'Over
        _riga_specchio(b, bet_id="6", mode="paper"),                         # prova
        _riga_specchio(b, bet_id="7", size_matched=0.0),                     # niente abbinato
    ])
    assert SS.leggi_ordini_conto_media(db, b.strat, session_paper=False) == "letta"
    # UNA lettura, della tabella dello specchio, filtrata su modo/mercato/selezione
    assert len(db.letture) == 1
    nome, filtri = db.letture[0]
    assert nome == "betfair_live_orders"
    assert filtri == {"mode": "live", "market_id": b.mid, "selection_id": b.under}
    assert "size_matched" in db.colonne and "source" in db.colonne
    giri(b, differita, 1)
    ch = b.strat.stats["chiusura"]
    assert ch["fonte"].startswith("ordini del bot + ordini del conto letti alle ")
    assert "(2 a mano su questa selezione)" in ch["fonte"]
    # la posizione del riquadro = bot + 30 @1,80 punta + 5 @1,60 banca
    atteso_w = pos_bot.se_vince + 30 * 0.80 - 5 * 0.60
    atteso_l = pos_bot.se_perde - 30 + 5
    assert ch["posizione"]["se_vince"] == pytest.approx(round(atteso_w, 2))
    assert ch["posizione"]["se_perde"] == pytest.approx(round(atteso_l, 2))
    assert ch["posizione"]["totale_puntato"] == pytest.approx(pos_bot.puntato + 30)
    # MAI negli ordini o nel ciclo della modalita'
    assert len(b.ordini()) == ordini_prima
    assert b.strat.stats["totale_puntato"] == pytest.approx(round(pos_bot.puntato, 2))
    assert b.strat.stats["se_vince"] == pytest.approx(round(pos_bot.se_vince, 2))


def test_in_prova_mai_nessuna_lettura(differita, exchange_it):
    b = _al_massimo(differita)
    db = _DbVero([_riga_specchio(b)])
    assert SS.leggi_ordini_conto_media(db, b.strat, session_paper=True) == "prova"
    assert db.letture == []
    giri(b, differita, 1)
    assert b.strat.stats["chiusura"]["fonte"] == MU.FONTE_SOLO_BOT


def test_lettura_fallita_torna_solo_ordini_del_bot_e_lo_dice(differita, exchange_it):
    b = _al_massimo(differita)
    pos_bot = b.posizione()
    db = _DbVero([_riga_specchio(b)], guasto=True)
    assert SS.leggi_ordini_conto_media(db, b.strat, session_paper=False) == "errore"
    giri(b, differita, 1)
    ch = b.strat.stats["chiusura"]
    assert ch["fonte"].startswith(MU.FONTE_SOLO_BOT)
    assert "lettura degli ordini del conto fallita alle " in ch["fonte"]
    assert "timeout PostgREST" in ch["fonte"]
    assert ch["posizione"]["totale_puntato"] == pytest.approx(pos_bot.puntato)


def test_posizione_chiusa_nessuna_lettura(differita, exchange_it):
    b = BancoMedia()
    giri(b, differita, 30)
    assert b.ordini() == []
    db = _DbVero([_riga_specchio(b)])
    assert SS.leggi_ordini_conto_media(db, b.strat, session_paper=False) == "chiusa"
    assert db.letture == []


def test_la_sessione_legge_una_volta_per_battito():
    """Il ciclo del battito di ``run_session`` chiama la lettura UNA volta,
    accanto alla scrittura del battito (lettura del sorgente: il ciclo vero
    gira solo con la sessione intera, nel replay del banco: controllo M10)."""
    import inspect

    src = inspect.getsource(SS.run_session)
    ciclo = src[src.index("while runner.is_alive():"):]
    ciclo = ciclo[:ciclo.index("db.set_control(ev, heartbeat_at=")]
    assert ciclo.count("leggi_ordini_conto_media(db, media, session_paper)") == 1
    assert src.count("leggi_ordini_conto_media(") == 1


def test_m10_rosso_su_letture_in_prova_o_oltre_i_battiti():
    par, _m = MU.leggi_parametri(params_di_serie())
    for prova, letture, battiti, rosso in ((True, 0, 10, False), (True, 1, 10, True),
                                           (False, 11, 10, False), (False, 12, 10, True)):
        oss = CERT.OsservazioneMedia(params=par, prova=prova, letture_conto=letture,
                                     battiti=battiti)
        sol: dict = {}
        codici = {v.codice for v in CERT.verifica_media(oss, sol)}
        assert ("M10" in codici) is rosso, (prova, letture, battiti, codici)
        assert sol.get("M10") == 1


# ===========================================================================
# 3. gli scenari dichiarati in piu' della modalita'
# ===========================================================================
@pytest.mark.parametrize("nome, diversi, guasto", [
    ("media-under-obiettivo-030", {"media_obiettivo": 0.30}, None),
    ("media-under-rientri-1", {"media_max_rientri": 1}, None),
    ("media-under-rischio-30", {"media_rischio_max": 30.0}, None),
    ("media-under-tick-1", {"media_tick_rientro": 1, "media_tick_chiusura": 1}, None),
    ("media-under-riavvio", {}, "riavvio"),
    ("media-under-rifiuti-betfair", {}, "rifiuti-betfair"),
    ("media-under-esiti-ignoti", {}, "esiti-ignoti"),
    ("media-under-kill-switch", {}, "kill-switch"),
    ("media-under-bot-fermo", {}, "bot-fermo"),
])
def test_scenari_dichiarati_cambiano_solo_la_loro_differenza(nome, diversi, guasto):
    from Betfair.stream.backtest import registro_bot as REG

    base = R.control_della_ui(EVENTO, R.SCENARIO_MEDIA)
    var = R.control_della_ui(EVENTO, nome)
    assert nome in REG.bot("scalper_calcio").elenco_scenari()
    assert R.mercato_media(nome) == "OVER_UNDER_25"
    assert var["dry_run"] is False and var["params"]["media_mode"] is True
    cambiati = {k: v for k, v in var["params"].items() if base["params"].get(k) != v}
    assert cambiati == diversi
    assert {k: v for k, v in var.items() if k != "params"} == \
        {k: v for k, v in base.items() if k != "params"}
    assert R.guasto_dello_scenario(nome) == (guasto or nome)
    par, motivo = MU.leggi_parametri(var["params"])
    assert par is not None, motivo


def test_i_guasti_dello_scalper_restano_i_loro():
    for sc in ("riavvio", "rifiuti-betfair", "esiti-ignoti", "kill-switch", "bot-fermo",
               "base", R.SCENARIO_MEDIA):
        assert R.guasto_dello_scenario(sc) == sc


def test_i_guasti_del_banco_aspettano_la_posizione_della_modalita(differita, exchange_it):
    """``_evento_scenario`` provoca stop/kill-switch/riavvio appena il bot ha una
    posizione abbinata aperta: per la modalita' la legge dalla SUA posizione
    (la modalita' non ha gli slot del maker)."""
    b = BancoMedia()
    giri(b, differita, 30)
    assert R._posizione_aperta(b.strat) is False
    giri(b, differita, 40)
    assert b.posizione().puntato > 0
    assert R._posizione_aperta(b.strat) is True
