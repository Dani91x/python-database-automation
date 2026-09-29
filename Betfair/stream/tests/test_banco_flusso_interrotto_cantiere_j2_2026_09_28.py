"""CANTIERE J2 (28/09/2026) - reperto B: il banco comune sa PROVARE il veto.

Prima: ``ScannerReplay.pubblica`` confermava sempre il flusso di tutti i mercati
visti, quindi in replay il flusso restava vivo per sempre e il veto non poteva
scattare. Ora uno scenario puo' dichiarare un BUCO DEI DATI
(``dichiara_buco_flusso(da, a, mercati)``): nella finestra i book di quei
mercati non arrivano allo scanner e la registrazione non li conferma; dopo la
soglia lo scanner VERO dichiara il flusso fermo; al rientro torna vivo.
Senza buchi il banco e' quello di sempre (righe identiche).
Scanner VERO, ``MarketBook`` di betfairlightweight, ``ScannerReplay`` vero.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from Betfair.safe_strategy.tests.test_flusso_interrotto_cantiere_j_2026_09_28 import MO, book
from Betfair.stream import flusso_prezzi as FP
from Betfair.stream.backtest.banco_comune import ScannerReplay


def _banco():
    banco = ScannerReplay(sport="calcio", conflate_ms=0)
    t0 = 1_790_000_000.0
    banco.imposta_ora(t0)
    scan = banco.scan
    scan._mike_followed = lambda *a, **k: []
    scan.sports["calcio"].metas = {"c1": {
        "event_id": "c1", "market_id": "1.200", "event_name": "Roma v Lazio",
        "open_date": (datetime.fromtimestamp(t0, tz=timezone.utc) - timedelta(minutes=20)).isoformat(),
        "competition": None, "runners": [], "sides": {"home": 11, "draw": 22, "away": 33},
    }}
    scan.events["c1"] = {"sport": "calcio", "inplay": True, "mo_status": "OPEN", "minute": 20,
                         "score_home": 0, "score_away": 0}
    scan._rebuild_market_index()
    banco.mercati_visti["1.200"] = "MATCH_ODDS"
    return banco, t0


def _giri(banco, t0, passi=120):
    """Un book ogni 5 s (il mercato si muove: stesso prezzo, stream vivo) e una
    pubblicazione a ogni passo; torna la sequenza di (vivo, motivo)."""
    out = []
    for passo in range(passi):
        banco.imposta_ora(t0 + 5.0 * passo)
        banco.applica_book(book("1.200", MO))
        banco.pubblica()
        blk = banco.riga("c1")["payload"]["flusso"]
        out.append((blk["vivo"], blk["motivo"]))
    return out


def test_senza_buchi_il_banco_e_quello_di_sempre_e_un_buco_fuori_tempo_non_cambia_niente():
    a, t0 = _banco()
    b, _ = _banco()
    b.dichiara_buco_flusso(t0 + 10_000.0, t0 + 20_000.0)        # oltre la registrazione
    sa, sb = _giri(a, t0), _giri(b, t0)
    assert sa == sb and all(v for v, _m in sa)
    assert json.dumps(a.tabella, sort_keys=True, default=str) == \
        json.dumps(b.tabella, sort_keys=True, default=str)
    assert a.righe_scritte == b.righe_scritte and b.book_persi_nel_buco == 0


def test_banco_senza_buchi_righe_identiche_al_banco_di_prima():
    """Reperto 4: SENZA buchi dichiarati il banco scrive le STESSE righe del banco
    di prima (quello di J: la registrazione conferma tutti i mercati visti a ogni
    pubblicazione). Mercato FERMO dopo il primo book: e' il caso in cui la
    conferma conta."""
    def fermo(banco, t0):
        banco.applica_book(book("1.200", MO))
        for passo in range(1, 121):
            banco.imposta_ora(t0 + 5.0 * passo)
            banco.pubblica()
        return json.dumps(banco.tabella, sort_keys=True, default=str), banco.righe_scritte

    nuovo, t0 = _banco()
    prima, _ = _banco()

    def pubblica_di_prima(self=prima):
        self.scan.conferma_flusso(list(self.mercati_visti))
        rows, wanted = self.scan.build_rows(self.adesso())
        for row in rows:
            self.tabella[str(row["event_id"])] = row
            self.righe_scritte += 1
        for eid in [e for e in self.tabella if e not in set(wanted)]:
            self.tabella.pop(eid, None)
        return rows

    prima.pubblica = pubblica_di_prima
    a, b = fermo(nuovo, t0), fermo(prima, t0)
    assert a == b
    assert nuovo.riga("c1")["payload"]["flusso"]["vivo"] is True


def test_buco_dichiarato_il_flusso_diventa_fermo_e_rientra():
    banco, t0 = _banco()
    banco.dichiara_buco_flusso(t0 + 100.0, t0 + 300.0, ["1.200"])
    seq = _giri(banco, t0)
    nel_buco = seq[20:60]                     # 100 s .. 300 s
    assert seq[19][0] is True
    # dopo la soglia in gioco (45 s) il flusso e' fermo per lo scanner vero
    assert any(v is False and m == FP.MOTIVO_INTERROTTO for v, m in nel_buco)
    assert all(v is False for v, _m in seq[30:60])
    assert banco.book_persi_nel_buco == 40
    # al rientro dei book il flusso torna vivo
    assert seq[61][0] is True and seq[-1][0] is True


def test_buco_su_un_altro_mercato_non_tocca_questo():
    banco, t0 = _banco()
    banco.dichiara_buco_flusso(t0 + 100.0, t0 + 300.0, ["1.999"])
    assert all(v for v, _m in _giri(banco, t0))
