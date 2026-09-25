"""F8 (25/09) - Safe TENNIS sul canale 47332: cio' che la porta e la riga devono
fare perche' l'interruttore ``SAFE_TENNIS_ORDINI_VIA_CANALE`` sia accendibile.

* il ref dell'ANNULLO porta il prefisso dell'attore (``safe_tennis-c<bet>``):
  il motore VERO rifiuta un ref senza ``f"{attore}-"`` (prima ogni annullo di
  Safe tennis sul canale sarebbe stato rifiutato); calcio invariato;
* la riga risolta DAL CANALE porta chiesto/abbinato/residuo/medio
  (``meta.esecuzione`` + colonne), come quella del REST (controllo C1 del
  tennis, visto dal banco sul canale);
* J4 resta rosso per un ref sbagliato; l'ordine nato da un comando (ref di
  flumine su Betfair) e' giudicato da J4C-DICHIARATA (limite del protocollo).

Finti: quelli di ``test_porta_ordini_f5_2026_09_24.py`` (motore finto che valida
con ``valida_comando`` VERA, righe dello specchio dall'encoder VERO) e le righe
di ``test_replay_tennis_2026_09_16.py`` (chiavi di ``_reserve_row``).
"""
from __future__ import annotations

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import certificazione_tennis as CERT
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import porta_ordini as PO
from Betfair.safe_strategy.tests.test_porta_ordini_f5_2026_09_24 import (  # noqa: F401
    NOW,
    _manda_e_risolvi,
    porta_e_motore,
    porta_e_motore_tennis,
    porta_registrata,
    tr_ref,
)
from Betfair.safe_strategy.tests.test_replay_tennis_2026_09_16 import (
    _codici,
    _ctx,
    _ordine,
    _osserva,
    _trade,
)
from Betfair.stream import motore_ordini as MO


# ===========================================================================
# 1. il ref dell'annullo segue l'attore
# ===========================================================================
def test_ref_annullo_col_prefisso_dell_attore():
    assert PO.ref_annullo("123", None) == "safe-c123"                  # calcio invariato
    assert PO.ref_annullo("123", 1.5) == "safe-c123-150"
    assert PO.ref_annullo("123", None, attore="safe_tennis") == "safe_tennis-c123"
    ref = PO.ref_annullo("123456789012", 1.5, attore="safe_tennis")
    assert ref.startswith("safe_tennis-") and len(ref) <= MO.MAX_REF


def test_annullo_safe_tennis_sul_canale_arriva_col_prefisso_giusto(porta_e_motore_tennis):
    porta, motore = porta_e_motore_tennis
    X.annulla_su_betfair(None, bet_id="3000000001", market_id="1.1", porta=porta,
                         mode="paper")
    comandi = [c for c in motore.comandi if c.get("azione") == "cancel"]
    assert comandi, "nessun annullo arrivato al motore"
    assert comandi[-1]["ref"] == "safe_tennis-c3000000001"
    # il motore VERO lo valida col percorso dell'attore
    assert MO.valida_comando("safe_tennis", comandi[-1])["azione"] == "cancel"


# ===========================================================================
# 2. C.12a sulle righe risolte dal canale
# ===========================================================================
def test_riga_risolta_dal_canale_porta_chiesto_abbinato_residuo_medio(porta_registrata):
    porta, motore = porta_registrata
    db, market, tr = _manda_e_risolvi(porta, motore, mode="live", fase_finale="abbinato")
    S.reconcile_pending(market=market, db=db, now=NOW)
    riga = db.get_trade(tr["id"])
    assert riga["status"] == "open"
    esec = riga["meta"]["esecuzione"]
    assert esec["percorso"] == "canale" and esec["canale_ref"] == tr_ref(tr)
    assert esec["size_richiesta"] == 2.0 and esec["size_abbinata"] == 2.0
    assert esec["size_residua"] == 0.0 and esec["price_medio"] == 3.0
    # le COLONNE (quelle che UI e K1/K5 leggono)
    assert riga["size_requested"] == 2.0 and riga["size_matched"] == 2.0
    assert riga["avg_price_matched"] == 3.0


def test_riga_senza_abbinato_resta_error_senza_esecuzione(porta_registrata):
    porta, motore = porta_registrata
    db, market, tr = _manda_e_risolvi(porta, motore, mode="live", fase_finale="annullato")
    S.reconcile_pending(market=market, db=db, now=NOW)
    riga = db.get_trade(tr["id"])
    assert riga["status"] == "error" and "esecuzione" not in riga["meta"]


# ===========================================================================
# 3. J4 e J4C-DICHIARATA
# ===========================================================================
def _riga_canale(**kw):
    return _trade(status="pending", bet_id=None,
                  meta={"canale_ref": "safe_tennis-t1", "phase": "canale_wait"}, **kw)


def test_j4_resta_rosso_per_un_ref_sbagliato_senza_canale():
    cod, _sol = _codici(_osserva(ctx=_ctx(), ordini=[_ordine(ref="36b1eb-1400")]))
    assert "J4" in cod and "J4C-DICHIARATA" not in cod


def test_ordine_del_motore_giudicato_da_j4c_dichiarata():
    oss = _osserva(ctx=_ctx(), trades=[_riga_canale()],
                   ordini=[_ordine(ref="36b1eb45560b0-1400964684")])
    cod, sol = _codici(oss)
    assert "J4" not in cod
    assert "J4C-DICHIARATA" in cod and sol.get("J4C-DICHIARATA") == 1


def test_j4c_per_bet_id_quando_la_riga_lo_conosce():
    # la riga del canale ha un ALTRO bet_id: l'ordine non e' suo -> J4 rosso
    riga = _trade(status="open", bet_id="altro", meta={"canale_ref": "safe_tennis-t1"})
    cod, _sol = _codici(_osserva(ctx=_ctx(), trades=[riga],
                                 ordini=[_ordine(ref="36b1eb-1400", bet_id="b1")]))
    assert "J4" in cod
    riga = _trade(status="open", bet_id="b1", meta={"canale_ref": "safe_tennis-t1"})
    cod, _sol = _codici(_osserva(ctx=_ctx(), trades=[riga],
                                 ordini=[_ordine(ref="36b1eb-1400", bet_id="b1")]))
    assert "J4" not in cod and "J4C-DICHIARATA" in cod


def test_j4c_e_una_dichiarata_non_rompe_l_esito():
    codici = [c for c, _r in CERT.elenco_controlli()]
    assert "J4C-DICHIARATA" in codici and codici.index("J4C-DICHIARATA") > codici.index("J4")
