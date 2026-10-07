"""MEDIA UNDER - <<ATTIVA ADESSO>> (07/10/2026, ordine dell'utente).

Regola definitiva dell'utente (confermata punto per punto, 07/10):
1. avvio SOLO col clic su <<Attiva adesso>> (pre-match o in gioco): prima punta
   immediata al miglior prezzo, poi gestione della posizione come progettato
   SENZA filtri d'ingresso (restano tetti e protezioni);
2. ciclo chiuso PRE-MATCH (avviato col pulsante): rientra da solo con un nuovo
   ciclo, di serie SENZA filtri (subito al miglior prezzo); con
   ``media_rientro_auto_filtri`` acceso solo quando i filtri lo permettono;
3. ciclo chiuso IN GIOCO: non rientra da solo, ATTESA DEL CLIC;
4. ciclo aperto pre-match e ancora aperto al fischio: in gioco continua a
   gestirlo come progettato; chiuso in gioco -> regola 3;
5. tutto questo SOLO se l'avvio e' stato col pulsante: la modalita' accesa nel
   modo di sempre non cambia in nulla.
In piu' (brief del coordinatore): un clic = UNA sola prima punta, anche dopo un
riavvio; clic a posizione aperta, a mercato sospeso, coi prezzi fermi o scaduto =
rifiutato col motivo e consumato (mai accodato).

Stesso banco dei giri 1-4 (``banco_media_under.BancoMedia``: flumine VERO col
client paper della sessione, strategia VERA, book nativi Betfair, esecuzione
differita di 1 e 4 book, minimi .it del banco). Il comando arriva per la strada
della sessione (``scalper_session.consegna_comando_media``) o, dove si prova solo
la strategia, coi suoi due passi (``ricevi_comando`` + ``rilascia_comando``).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from Betfair.stream.backtest import minimi_banco as MB
from Betfair.stream.scalper import media_under_bot as MU
from Betfair.stream.scalper import scalper_session as SS
from Betfair.stream.tennis_live.tests.test_cantiere_t_pro_residuo_2026_09_28 import (  # noqa: F401
    esecuzione_differita,
)
from Betfair.stream.tests.banco_media_under import KO_MS, BancoMedia, giri


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


def _clic(b: BancoMedia, cid: str, *, inviato_ms: Optional[float] = None,
          vivi: Optional[bool] = None) -> Optional[Dict[str, Any]]:
    """Il clic come lo consegna la sessione: ricevuto (consumato), registrato,
    rilasciato. Si esegue al book successivo."""
    info = b.strat.ricevi_comando(cid, float(b.pt if inviato_ms is None else inviato_ms),
                                  float(b.pt), prezzi_vivi=vivi)
    b.strat.rilascia_comando()
    return info


class _DbRiga:
    """La riga ``scalper_control`` vista da ``consegna_comando_media``: le stesse
    firme di ``scalper_session.Db`` (``set_control`` torna se la scrittura e'
    passata, ``log``)."""

    def __init__(self, scrive: bool = True) -> None:
        self.scrive = scrive
        self.scritture: List[Dict[str, Any]] = []
        self.log_righe: List[Any] = []

    def set_control(self, event_id: str, **fields: Any) -> bool:
        if not self.scrive:
            return False
        self.scritture.append(dict(fields))
        return True

    def log(self, event_id: str, kind: str, payload: Dict[str, Any]) -> None:
        self.log_righe.append((kind, dict(payload)))


def _stats_di(b: BancoMedia):
    return lambda: {"%s%s" % (MU.PREFISSO, k): v for k, v in b.strat.stats.items()}


def _params_col_clic(cid: str, ts_ms: float) -> Dict[str, Any]:
    return {MU.CHIAVE_COMANDO: {"id": cid, "ts": ts_ms}, MU.CHIAVE_A_CLIC: True}


def _chiudi_il_ciclo(b: BancoMedia, svuota: Any) -> List[str]:
    """La quota scende sotto la banca di chiusura e la banca si abbina per
    intero (2 000 EUR scambiati al suo prezzo)."""
    banca = b.vivi("LAY")[0]
    c = float(banca.order_type.price)
    b.ladder[b.under] = (round(c - 0.01, 2), c)
    b.scambia(b.under, c, 2000)
    return giri(b, svuota, 8)


# ===========================================================================
# 1. il clic: prima punta SUBITO, senza filtri
# ===========================================================================
def test_sessione_armata_dal_pulsante_non_entra_da_sola(differita, exchange_it):
    """Sessione "a clic" (armata dal pulsante): coi filtri tutti soddisfatti per
    100 book NON entra da sola; aspetta il clic."""
    b = BancoMedia(media_a_clic=True)
    viol = giri(b, differita, 100)
    assert viol == []
    assert b.ordini() == []
    assert b.strat.stato == MU.ATTESA_CLIC
    assert b.strat.stats["non_ingresso"] == {}


def test_il_clic_punta_subito_al_miglior_prezzo_senza_filtri(differita, exchange_it):
    """Liquidita' 200 (filtro 300), nessun riscaldamento, nessun flusso: il clic
    punta lo stake base al miglior prezzo di punta del book successivo; poi la
    banca di chiusura come progettato."""
    b = BancoMedia(profondita=200.0, media_a_clic=True)
    giri(b, differita, 2, flusso=0.0)
    b.ladder[b.under] = (1.62, 1.63)
    info = _clic(b, "c1")
    assert info is not None and info["esito"] == "ricevuto"
    viol = giri(b, differita, 1, flusso=0.0)
    punte = _punte(b)
    assert [(float(o.order_type.price), float(o.order_type.size)) for o in punte] \
        == [(1.62, 10.0)]
    assert str(punte[0].order_type.persistence_type) == "LAPSE"
    viol += giri(b, differita, 10, flusso=0.0)
    assert viol == [], viol[:3]
    assert [(float(o.order_type.price), float(o.order_type.size)) for o in _banche(b)] \
        == [(1.60, 10.13)]
    com = b.strat.stats["comando"]
    assert (com["id"], com["esito"], com["prezzo"], com["importo"]) == ("c1", "eseguito",
                                                                         1.62, 10.0)
    ingressi = b.kinds("media_ingresso")
    assert len(ingressi) == 1 and ingressi[0]["origine"] == MU.ORIGINE_CLIC
    assert b.strat.stats["origine_ciclo"] == MU.ORIGINE_CLIC


def test_il_clic_punta_anche_dentro_la_finestra_di_stop(differita, exchange_it):
    b = BancoMedia(media_a_clic=True)
    b.pt = KO_MS - 200_000
    giri(b, differita, 3)
    _clic(b, "c1")
    viol = giri(b, differita, 6)
    assert viol == []
    assert [float(o.order_type.size) for o in _punte(b)] == [10.0]
    assert b.strat.stato == MU.IN_POSIZIONE


def test_un_clic_una_sola_prima_punta(differita, exchange_it):
    """Lo stesso id consegnato due volte (lettura ripetuta dei params) = una
    sola punta; un SECONDO clic mentre il primo ciclo e' in posizione =
    rifiutato col motivo, consumato, nessuna punta."""
    b = BancoMedia(media_a_clic=True)
    giri(b, differita, 2)
    _clic(b, "c1")
    assert _clic(b, "c1") is None
    viol = giri(b, differita, 6)
    assert len(_punte(b)) == 1
    info = _clic(b, "c2")
    viol += giri(b, differita, 6)
    assert viol == []
    assert len(_punte(b)) == 1
    assert info is not None
    assert b.strat.stats["comando"]["id"] == "c2"
    assert b.strat.stats["comando"]["esito"] == "rifiutato"
    assert "gia' in posizione" in b.strat.stats["comando"]["motivo"]
    rif = b.kinds("media_comando_rifiutato")
    assert len(rif) == 1 and rif[0]["comando"] == "c2"
    # consumato: non riparte nemmeno a posizione chiusa
    viol += _chiudi_il_ciclo(b, differita)
    assert b.strat.stats["comando"]["id"] == "c2"
    assert len(b.kinds("media_comando_eseguito")) == 1


@pytest.mark.parametrize("stato", [MU.INGRESSO, MU.IN_POSIZIONE, MU.RIENTRO, MU.MASSIMO,
                                   MU.LIVE])
def test_clic_rifiutato_in_uno_stato_di_ciclo_anche_senza_ordini(stato, differita, exchange_it):
    """Difesa in profondita' (verifica del coordinatore): per la via vera questi
    stati hanno SEMPRE una punta o un abbinato nel ciclo (il clic e' gia'
    rifiutato da ``pos.aperta``/``_punta``); se un difetto futuro lasciasse lo
    stato senza ordini, il clic resta rifiutato. Lo stato si forza a mano: e' il
    caso irraggiungibile che il controllo dello stato protegge."""
    b = BancoMedia(media_a_clic=True)
    giri(b, differita, 2)
    b.strat.stato = stato
    _clic(b, "c1")
    giri(b, differita, 4)
    assert _punte(b) == []
    assert b.strat.stats["comando"]["esito"] == "rifiutato"
    assert "gia' in posizione" in b.strat.stats["comando"]["motivo"]


def test_doppio_clic_in_volo_una_sola_punta(differita, exchange_it):
    """Due clic diversi a pochi ms (doppio clic): il secondo arriva con la prima
    punta ancora in volo (PENDING) -> rifiutato."""
    b = BancoMedia(media_a_clic=True)
    giri(b, differita, 2)
    _clic(b, "c1")
    b.book()
    _clic(b, "c2")
    viol = giri(b, differita, 8)
    assert viol == []
    assert len(_punte(b)) == 1
    assert b.strat.stats["comando"]["esito"] == "rifiutato"


def test_clic_a_mercato_sospeso_rifiutato_e_non_accodato(differita, exchange_it):
    b = BancoMedia(media_a_clic=True)
    giri(b, differita, 2)
    b.stato = "SUSPENDED"
    giri(b, differita, 2)
    info = _clic(b, "c1")
    assert info is not None and info["esito"] == "rifiutato"
    assert "sospeso" in info["motivo"]
    b.stato = "OPEN"
    giri(b, differita, 10)
    assert b.ordini() == []
    # sospeso DOPO la consegna: deciso sul book (sospeso) -> rifiutato
    _clic(b, "c2")
    b.stato = "SUSPENDED"
    giri(b, differita, 2)
    b.stato = "OPEN"
    viol = giri(b, differita, 10)
    assert viol == []
    assert b.ordini() == []
    assert b.strat.stats["comando"]["id"] == "c2"
    assert "sospeso" in b.strat.stats["comando"]["motivo"]


def test_clic_coi_prezzi_fermi_rifiutato(differita, exchange_it):
    """La sorveglianza del flusso della sessione dice "non vivo": il clic arriva
    per la strada vera (``consegna_comando_media``) ed e' rifiutato."""
    b = BancoMedia(media_a_clic=True)
    giri(b, differita, 2)
    db = _DbRiga()
    out = SS.consegna_comando_media(db, "35999999", b.strat,
                                    _params_col_clic("c1", b.pt), {"vivo": False},
                                    _stats_di(b), ora_s=b.pt / 1000.0)
    assert out is not None and out["esito"] == "rifiutato"
    assert "prezzi fermi" in out["motivo"]
    giri(b, differita, 10)
    assert b.ordini() == []


def test_clic_scaduto_rifiutato(differita, exchange_it):
    b = BancoMedia(media_a_clic=True)
    giri(b, differita, 2)
    info = _clic(b, "c1", inviato_ms=b.pt - (MU.ATTESA_MASSIMA_COMANDO_S + 1) * 1000)
    assert info["esito"] == "rifiutato" and "scaduto" in info["motivo"]
    giri(b, differita, 10)
    assert b.ordini() == []


def test_il_clic_si_esegue_solo_dopo_la_registrazione_nella_riga(differita, exchange_it):
    """Scrittura della riga fallita = clic NON eseguito (un riavvio non saprebbe
    che e' gia' stato eseguito); scrittura riuscita = eseguito, e la riga porta
    l'id consumato PRIMA della punta."""
    b = BancoMedia(media_a_clic=True)
    giri(b, differita, 2)
    db = _DbRiga(scrive=False)
    out = SS.consegna_comando_media(db, "35999999", b.strat, _params_col_clic("c1", b.pt),
                                    None, _stats_di(b), ora_s=b.pt / 1000.0)
    assert out["esito"] == "rifiutato" and "non registrato" in out["motivo"]
    giri(b, differita, 6)
    assert b.ordini() == []
    db = _DbRiga()
    out = SS.consegna_comando_media(db, "35999999", b.strat, _params_col_clic("c2", b.pt),
                                    None, _stats_di(b), ora_s=b.pt / 1000.0)
    assert out["esito"] == "ricevuto"
    assert db.scritture and db.scritture[0]["stats"]["media_comando"]["id"] == "c2"
    assert b.ordini() == []          # la punta parte al book, non alla consegna
    giri(b, differita, 4)
    assert len(_punte(b)) == 1


def test_riavvio_dopo_un_clic_consumato_nessuna_seconda_punta(differita, exchange_it):
    """La sessione nuova legge l'id consumato dalle stats della riga (che
    sopravvivono al riarmo): lo stesso clic nei params NON si riesegue; la
    sessione resta "a clic"."""
    control = {"params": _params_col_clic("c1", KO_MS - 3_600_000),
               "stats": {"media_comando": {"id": "c1", "esito": "eseguito"},
                         "media_a_clic": True}}
    prec = SS.comando_media_precedente(control)
    assert prec["comando_consumato"] == "c1" and prec[MU.CHIAVE_A_CLIC] is True
    b = BancoMedia(**{k: v for k, v in prec.items()})
    giri(b, differita, 2)
    db = _DbRiga()
    out = SS.consegna_comando_media(db, "35999999", b.strat, control["params"], None,
                                    _stats_di(b), ora_s=b.pt / 1000.0)
    assert out is None
    viol = giri(b, differita, 80)
    assert viol == []
    assert b.ordini() == []
    assert b.strat.stato == MU.ATTESA_CLIC
    assert b.strat.stats["comando"]["id"] == "c1"


# ===========================================================================
# 2. gestione SENZA filtri d'ingresso
# ===========================================================================
def _sali(b: BancoMedia, svuota: Any, quote: List[float], n: int = 12, **kw: Any) -> List[str]:
    viol: List[str] = []
    for q in quote:
        b.ladder[b.under] = (q, round(q + 0.01, 2))
        viol += giri(b, svuota, n, **kw)
    return viol


def test_rientro_dentro_la_finestra_di_stop_dopo_il_clic(differita, exchange_it):
    """Avviata col pulsante: il rientro (quota +2 tick) si fa anche dentro la
    finestra di stop prima del fischio e senza liquidita'/flusso; nella
    modalita' di sempre lo stesso caso NON rientra (filtri di sempre)."""
    for a_clic in (True, False):
        b = BancoMedia(profondita=200.0, media_a_clic=a_clic,
                       **({} if a_clic else {"media_min_size": 100.0}))
        b.pt = KO_MS - 480_000 - 70_000
        if a_clic:
            giri(b, differita, 2)
            _clic(b, "c1")
            viol = giri(b, differita, 68)
        else:
            viol = giri(b, differita, 70)
        assert [float(o.order_type.size) for o in _punte(b)] == [10.0], a_clic
        b.pt = KO_MS - 400_000
        viol += _sali(b, differita, [1.52], flusso=0.0)
        assert viol == [], viol[:3]
        n = len(_punte(b))
        assert n == (2 if a_clic else 1), (a_clic, n)


def test_in_gioco_gestisce_come_pre_match_dopo_il_clic(differita, exchange_it):
    """Ciclo avviato col pulsante e aperto al fischio (punto 4): in gioco la
    modalita' rientra (quota +2 tick) e SPOSTA la banca come pre-match (07/10:
    la banca spostata col replace + l'integrazione, alla stessa quota)."""
    b = BancoMedia(media_a_clic=True)
    giri(b, differita, 2)
    _clic(b, "c1")
    viol = giri(b, differita, 10)
    b.in_gioco()
    viol += giri(b, differita, 4)
    viol += _sali(b, differita, [1.52])
    assert viol == [], viol[:3]
    assert [(float(o.order_type.price), float(o.order_type.size)) for o in _punte(b)] \
        == [(1.50, 10.0), (1.52, 10.0)]
    vive = b.vivi("LAY")
    assert {float(o.order_type.price) for o in vive} == {1.50}
    assert round(sum(float(o.size_remaining) for o in vive), 2) == 20.13
    assert b.strat.stats["chiusura"] is not None        # riquadro pubblicato
    assert b.kinds("media_live")[0]["a_clic"] is True


def test_in_gioco_mercato_sospeso_nessun_ordine(differita, exchange_it):
    """Gol in gioco: mercato sospeso, la quota salta; nessun ordine finche' e'
    sospeso, poi alla riapertura il rientro scatta come progettato."""
    b = BancoMedia(media_a_clic=True)
    giri(b, differita, 2)
    _clic(b, "c1")
    viol = giri(b, differita, 10)
    b.in_gioco()
    viol += giri(b, differita, 3)
    n = len(b.ordini())
    b.stato = "SUSPENDED"
    b.ladder[b.under] = (1.80, 1.82)
    viol += giri(b, differita, 10)
    assert len(b.ordini()) == n
    assert b.kinds("media_sospeso")
    b.stato = "OPEN"
    viol += giri(b, differita, 12)
    assert viol == [], viol[:3]
    rientri = b.kinds("media_rientro")
    assert len(rientri) == 1 and rientri[0]["prezzo"] == 1.80


def test_clic_in_gioco_nella_modalita_di_sempre(differita, exchange_it):
    """Modalita' accesa nel modo di sempre, in gioco senza posizione (FINE): il
    clic punta subito e da li' la gestione e' quella del pulsante."""
    b = BancoMedia(profondita=200.0)
    giri(b, differita, 3)
    b.in_gioco()
    giri(b, differita, 3)
    assert b.strat.stato == MU.FINE and b.ordini() == []
    _clic(b, "c1")
    viol = giri(b, differita, 10)
    assert viol == []
    assert [float(o.order_type.size) for o in _punte(b)] == [10.0]
    assert b.strat.stato == MU.IN_POSIZIONE and b.strat._clic.a_clic is True


# ===========================================================================
# 3. dopo la chiusura: pre-match rientra da solo, in gioco aspetta il clic
# ===========================================================================
def test_chiuso_pre_match_rientra_subito_senza_filtri(differita, exchange_it):
    b = BancoMedia(profondita=200.0, media_a_clic=True)
    giri(b, differita, 2, flusso=0.0)
    _clic(b, "c1")
    viol = giri(b, differita, 8, flusso=0.0)
    viol += _chiudi_il_ciclo(b, differita)
    assert viol == [], viol[:3]
    assert len(b.kinds("media_ciclo_chiuso")) == 1
    assert len(b.kinds("media_rientro_automatico")) == 1
    punte = _punte(b)
    assert len(punte) == 2 and float(punte[1].order_type.size) == 10.0
    ingressi = b.kinds("media_ingresso")
    assert [i["origine"] for i in ingressi] == [MU.ORIGINE_CLIC, MU.ORIGINE_RIENTRO_AUTO]
    assert len(b.kinds("media_comando_eseguito")) == 1


def test_chiuso_pre_match_coi_filtri_accesi_aspetta_i_filtri(differita, exchange_it):
    """Interruttore acceso: con liquidita' 200 (filtro 300) il nuovo ciclo NON
    parte; con la liquidita' che torna (e il flusso) parte, coi filtri."""
    b = BancoMedia(profondita=200.0, media_a_clic=True, media_rientro_auto_filtri=True)
    giri(b, differita, 2)
    _clic(b, "c1")
    viol = giri(b, differita, 8)
    viol += _chiudi_il_ciclo(b, differita)
    viol += giri(b, differita, 70)
    assert len(_punte(b)) == 1
    assert b.strat.stato == MU.FERMO
    assert b.strat.stats["non_ingresso"].get("liquidita", 0) > 0
    b.profondita = 500.0
    viol += giri(b, differita, 10)
    assert viol == [], viol[:3]
    assert len(_punte(b)) == 2
    assert b.kinds("media_ingresso")[-1]["origine"] == MU.ORIGINE_RIENTRO_AUTO


def test_chiuso_in_gioco_aspetta_il_clic(differita, exchange_it):
    """Ciclo a cavallo del fischio (aperto pre-match, chiuso in gioco): ATTESA
    DEL CLIC, nessun ordine fino al clic; il clic riparte con una prima punta."""
    b = BancoMedia(media_a_clic=True)
    giri(b, differita, 2)
    _clic(b, "c1")
    viol = giri(b, differita, 10)
    b.in_gioco()
    viol += giri(b, differita, 3)
    viol += _chiudi_il_ciclo(b, differita)
    assert len(b.kinds("media_ciclo_chiuso")) == 1
    assert b.strat.stato == MU.ATTESA_CLIC
    assert b.kinds("media_attesa_clic")
    n = len(b.ordini())
    viol += giri(b, differita, 40)
    assert len(b.ordini()) == n
    _clic(b, "c2")
    viol += giri(b, differita, 6)
    assert viol == [], viol[:3]
    assert len(_punte(b)) == 2
    assert b.kinds("media_ingresso")[-1]["origine"] == MU.ORIGINE_CLIC


def test_prima_punta_del_clic_non_abbinata_attesa_del_clic(differita, exchange_it):
    """La punta del clic non si abbina (la quota scappa) e si ritira: un clic =
    una sola prima punta -> ATTESA DEL CLIC, nessuna seconda punta da sola."""
    b = BancoMedia(media_a_clic=True)
    giri(b, differita, 2, flusso=0.0)
    _clic(b, "c1")
    viol = giri(b, differita, 1, flusso=0.0)       # la punta parte a 1,50
    b.ladder[b.under] = (1.49, 1.50)
    b.book(flusso=0.0)                              # la quota scappa prima dell'esecuzione
    viol += giri(b, differita, 50, flusso=0.0)
    assert viol == []
    punte = _punte(b)
    assert len(punte) == 1 and float(punte[0].size_matched) == 0.0
    assert b.strat.stato == MU.ATTESA_CLIC


# ===========================================================================
# 4. la modalita' di sempre NON cambia; paper = live
# ===========================================================================
def test_modalita_di_sempre_in_gioco_nessun_ordine(differita, exchange_it):
    b = BancoMedia()
    viol = giri(b, differita, 70)
    assert len(_punte(b)) == 1
    b.in_gioco()
    n = len(b.ordini())
    viol += _sali(b, differita, [1.52, 1.54])
    assert viol == []
    assert len(b.ordini()) == n
    assert b.strat.stato == MU.LIVE
    assert b.kinds("media_ingresso")[0].get("origine") is None


def test_soldi_veri_fermati_il_clic_non_punta(differita, exchange_it):
    """Paper = live: stessa strada; in soldi veri il freno dei soldi veri vale
    anche per il clic (apertura): rifiutato col motivo, nessuna punta."""
    b = BancoMedia(media_a_clic=True)
    b.strat.freno_live = lambda: "ordini_reali_spenti"
    giri(b, differita, 2)
    _clic(b, "c1")
    giri(b, differita, 6)
    assert b.ordini() == []
    assert b.strat.stats["comando"]["esito"] == "rifiutato"
    assert "ordini_reali_spenti" in b.strat.stats["comando"]["motivo"]
    b2 = BancoMedia(media_a_clic=True)
    b2.strat.freno_live = lambda: None          # soldi veri serviti
    giri(b2, differita, 2)
    _clic(b2, "c1")
    giri(b2, differita, 6)
    assert [float(o.order_type.size) for o in _punte(b2)] == [10.0]


def test_riquadro_alla_quota_minima_nessuna_divisione_per_zero():
    """Visto nel replay (35760084, cicli del pulsante in gioco): miglior punta
    dell'Under a 1,01 -> la chiusura N tick sotto e' ancora 1,01 -> X divideva per
    zero a ogni book (eccezione dentro process_market_book, riquadro mai
    aggiornato). Ora: nessun obiettivo, il resto del riquadro c'e'."""
    pos = MU.posizione_da_importi([(10.0, 1.50)])
    r = MU.riquadro_chiusura(pos, quota_punta=1.01, quota_banca=1.02, tick=2,
                             obiettivi_netti=[0.0, 0.30], commissione=0.05)
    assert r["obiettivi"] == []
    assert r["chiudi_adesso"] is not None
    r2 = MU.riquadro_chiusura(pos, quota_punta=1.05, quota_banca=1.06, tick=2,
                              obiettivi_netti=[0.0], commissione=0.05)
    assert len(r2["obiettivi"]) == 1


def test_parametro_rientro_filtri_valido_solo_booleano():
    from Betfair.stream.tests.banco_media_under import params_di_serie

    par, mot = MU.leggi_parametri(params_di_serie())
    assert mot is None and par.rientro_auto_filtri is False
    par, mot = MU.leggi_parametri(params_di_serie(media_rientro_auto_filtri=True))
    assert par.rientro_auto_filtri is True
    par, mot = MU.leggi_parametri(params_di_serie(media_rientro_auto_filtri="si"))
    assert par is None and MU.CHIAVE_RIENTRO_FILTRI in mot
    assert MU.leggi_comando({MU.CHIAVE_COMANDO: {"id": " x ", "ts": "2026-10-07T10:00:00Z"}}) \
        == ("x", 1791367200000.0)
    assert MU.leggi_comando({MU.CHIAVE_COMANDO: {"ts": 1}}) is None
    assert MU.leggi_comando({MU.CHIAVE_COMANDO: "x"}) is None
    for k in (MU.CHIAVE_COMANDO, MU.CHIAVE_A_CLIC, MU.CHIAVE_RIENTRO_FILTRI):
        assert k in SS.UI_PARAM_WHITELIST
