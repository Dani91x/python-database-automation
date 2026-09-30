"""30/09/2026 - IL "DA N S" DEGLI AVVISI DI FLUSSO FERMO DI MIKE (revisione critica).

Difetto: il testo di ``flusso_interrotto`` (e il ``da_secondi`` di
``flusso_interrotto_senza_rest``) contava da ``flusso.dal_ms``, che lo scanner
(``safe_strategy/service.py::flusso_evento``) aggiorna al passaggio di stato del
MATCH ODDS, non della linea: a partita in corso usciva "da 1628 s" (dal fischio)
su una linea ferma da pochi secondi, e il testo diceva solo un market_id.

Correzione: per le linee di Mike (``feed.mercati_di_mike``: 3,5 e 4,5 ancora in
gioco) il testo dice QUALE linea e' ferma e da quanto e' arrivato il suo ultimo
book (``seen_ms`` del blocco ``ou``, scritto dallo scanner a ogni book ricevuto);
il ``da_secondi`` e' quello della linea. Riga senza ``seen_ms`` (scanner
precedente al 13/09): comportamento di prima.

Finti: ``payload``/``row`` di ``test_mike_feed`` (chiavi e tipi della riga vera
dello scanner) con il blocco ``flusso`` di ``flusso_evento`` e il ``seen_ms``
che lo scanner scrive su ogni blocco ``ou``. ASCII-only.
"""
from __future__ import annotations

from datetime import timedelta

from Betfair.mike import feed as F
from Betfair.mike.tests.test_mike_feed import NOW, payload, row
from Betfair.stream import flusso_prezzi as FP


def _ms(dt) -> int:
    return int(dt.timestamp() * 1000)


def _riga(fermi, *, dal_s=1628.0, seen35_s=36.0, seen45_s=2.0, sh=None, sa=None):
    """Riga in gioco: MATCH ODDS vivo dal fischio (``dal_ms`` 1628 s fa), linee
    di Mike con l'ultimo book ricevuto ``seen*_s`` secondi fa."""
    p = payload(inplay=True, minute=27, sh=sh, sa=sa)
    for blk in p["ou"]:
        age = seen35_s if blk["line"] == 3.5 else seen45_s
        blk["seen_ms"] = _ms(NOW - timedelta(seconds=age))
    p["flusso"] = {"vivo": True, "motivo": None,
                   "dal_ms": _ms(NOW - timedelta(seconds=dal_s)),
                   "mercati_fermi": list(fermi)}
    return row(p)


def _adesso_ms() -> int:
    return _ms(NOW)


def test_testo_dice_quale_linea_e_da_quanto_non_dal_fischio():
    es = F.flusso_esito(_riga(["1.35"]), None, NOW.timestamp())
    assert es.vivo is False and es.motivo == FP.MOTIVO_MERCATO_FERMO
    assert "Under/Over 3,5" in es.testo, es.testo
    assert "1.35" in es.testo
    assert "36 s" in es.testo, es.testo
    assert "1628" not in es.testo, es.testo


def test_due_linee_ferme_ognuna_col_suo_tempo():
    es = F.flusso_esito(_riga(["1.35", "1.45"], seen45_s=80.0), None, NOW.timestamp())
    assert "Under/Over 3,5" in es.testo and "Under/Over 4,5" in es.testo, es.testo
    assert "36 s" in es.testo and "80 s" in es.testo, es.testo
    assert "1628" not in es.testo


def test_da_secondi_della_linea_ferma_non_del_fischio():
    r = _riga(["1.35"])
    assert F.secondi_fermo_mike(r["payload"], None, _adesso_ms()) == 36.0
    # confronto: la misura generica conta dal passaggio del MATCH ODDS
    assert FP.secondi_fermo(r["payload"], None, _adesso_ms()) == 1628.0


def test_linea_decisa_dai_gol_non_conta_ne_nel_testo_ne_nel_tempo():
    # 4 gol: il 3,5 e' deciso (fuori da mercati_di_mike), fermo il 4,5
    r = _riga(["1.35", "1.45"], seen35_s=500.0, seen45_s=12.0, sh=3, sa=1)
    es = F.flusso_esito(r, None, NOW.timestamp())
    assert "Under/Over 4,5" in es.testo and "Under/Over 3,5" not in es.testo, es.testo
    assert F.secondi_fermo_mike(r["payload"], None, _adesso_ms()) == 12.0


def test_giro_dello_scanner_bloccato_conta_dall_ultimo_calcolo():
    r = _riga([])
    stato = {"flusso": {"calcolato_ms": _ms(NOW - timedelta(seconds=90)), "eventi_fermi": {}}}
    assert F.secondi_fermo_mike(r["payload"], stato, _adesso_ms()) == 90.0
    es = F.flusso_esito(r, stato, NOW.timestamp())
    assert es.motivo == FP.MOTIVO_SCANNER_BLOCCATO and "90 s" in es.testo


def test_riga_senza_seen_ms_comportamento_di_prima():
    r = _riga(["1.35"])
    for blk in r["payload"]["ou"]:
        blk.pop("seen_ms")
    es = F.flusso_esito(r, None, NOW.timestamp())
    assert es.testo == FP.valuta(r["payload"], None, None, F.mercati_di_mike(r["payload"]),
                                 _adesso_ms()).testo
    assert F.secondi_fermo_mike(r["payload"], None, _adesso_ms()) == 1628.0


def test_linee_vive_nessun_cambio():
    es = F.flusso_esito(_riga([]), None, NOW.timestamp())
    assert es.vivo is True and es is FP.VIVO


# ---------------------------------------------------------------------------
# Sul ciclo VERO (``run_once``): le righe di diario che vede il trader
# ---------------------------------------------------------------------------
def test_ciclo_vero_diario_dice_la_linea_e_i_suoi_secondi(runner):
    from Betfair.mike import service as S
    from Betfair.mike.tests.test_mike_flusso_cantiere_j2_2026_09_28 import (
        _posizione_aperta, _scanner_nuovo)
    from Betfair.mike.tests.test_mike_service import run

    db, mk = _posizione_aperta(runner)
    S._FLUSSO_CRITICO.azzera()
    dopo = NOW + timedelta(seconds=40)
    _scanner_nuovo(db, calcolato=dopo)
    p = payload()
    for blk in p["ou"]:
        age = 36.0 if blk["line"] == 3.5 else 20.0
        blk["seen_ms"] = _ms(dopo - timedelta(seconds=age))
    # il MATCH ODDS (mai ricevuto prima del fischio) e' "passato di stato" alla
    # creazione della riga, 1628 s fa: e' il numero che usciva prima
    p["flusso"] = {"vivo": False, "motivo": "mai_ricevuto",
                   "dal_ms": _ms(dopo - timedelta(seconds=1628)),
                   "mercati_fermi": ["1.35", "1.45"]}
    run(db, mk, dopo, [row(p, updated=dopo)])
    avvisi = [q for k, q, _e in db.activity if k == "flusso_interrotto"]
    assert avvisi, db.activity
    assert "Under/Over 3,5 (1.35) ferma, ultimo book ricevuto 36 s fa" in avvisi[-1]["testo"]
    assert "Under/Over 4,5 (1.45) ferma, ultimo book ricevuto 20 s fa" in avvisi[-1]["testo"]
    assert "1628" not in avvisi[-1]["testo"]
    crit = [q for k, q, _e in db.activity if k == "flusso_interrotto_senza_rest"]
    assert len(crit) == 1, db.activity
    assert crit[0]["da_secondi"] == 36.0
    assert "Under/Over 3,5" in crit[0]["testo"]


# ---------------------------------------------------------------------------
# 30/09 sera (review incrociata): ``seen_ms`` e' FUORI FIRMA, la riga non si
# riscrive se cambia solo lui, quindi «ultimo book N s fa» era l'eta' dell'ultima
# riscrittura. Lo scanner ora scrive ``flusso.fermi_da_ms`` (istante vero
# dell'ultima conferma con prezzi, calcolato quando la linea diventa ferma):
# Mike lo legge PRIMA di ``seen_ms``.
# ---------------------------------------------------------------------------
def test_fermi_da_ms_vince_su_seen_ms():
    r = _riga(["1.35"], seen35_s=300.0)  # seen_ms stantio: 300 s
    r["payload"]["flusso"]["fermi_da_ms"] = {"1.35": _ms(NOW - timedelta(seconds=41.0))}
    linee = F.linee_ferme_mike(r["payload"], _adesso_ms())
    assert linee == [("1.35", "Under/Over 3,5", 41.0)]
    es = F.flusso_esito(r, None, NOW.timestamp())
    assert "41 s" in es.testo and "300 s" not in es.testo, es.testo


def test_senza_fermi_da_ms_resta_seen_ms():
    r = _riga(["1.35"], seen35_s=36.0)
    r["payload"]["flusso"]["fermi_da_ms"] = {}  # scanner nuovo, ma senza istante per quella linea
    assert F.linee_ferme_mike(r["payload"], _adesso_ms()) == [("1.35", "Under/Over 3,5", 36.0)]
    r["payload"]["flusso"].pop("fermi_da_ms")  # scanner precedente
    assert F.linee_ferme_mike(r["payload"], _adesso_ms()) == [("1.35", "Under/Over 3,5", 36.0)]
