"""T0B punto (4) della migrazione (09/10/2026, decisione U-32): il finto del
database di Omega nel banco ha la FIRMA e il COMPORTAMENTO del vero sugli
aggregati per modalita'.

Reperto (E2 difetto 5; PROCESSO_STANDARD_BOT par. 7 n.21 e n.27):
`DbMemoriaOmega.aggregates(self, day_start=None)` e
`aggregates_coppia(self, day_start=None)` non accettavano `mode`, mentre il
vero e' `omega_db.aggregates(day_start=None, mode=None)` e
`aggregates_coppia(day_start=None, mode=None)`. Il servizio
(`omega_service._con_modalita`) se ne accorgeva per `inspect.signature`, lo
diceva con un CRITICAL "paper e live SOMMATI" e decideva sui numeri di TUTTE le
modalita': il replay certificava una condotta diversa da quella di produzione.

Il confronto qui e' contro il VERO, non contro una copia del vero scritta nel
test: `omega_db.aggregates_coppia` gira davvero, con il client del database
che fallisce (la RPC non c'e') e le righe servite dal suo stesso lettore
`_righe_per_aggregati`, proiettate sulle colonne della sua `select`. E' il
percorso "in casa" che il vero dichiara "stesso risultato" della RPC.
"""
from __future__ import annotations

import inspect
import logging
import re
from datetime import datetime, timedelta, timezone

import pytest

from Betfair.omega import omega_db as DBVERO
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_service as S
from Betfair.omega.tools import replay_registrazioni as RR

ADESSO = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)
IERI = ADESSO - timedelta(days=1)
EVENTO = "35760084"

#: le modalita' che il vero distingue, piu' le forme che il vero normalizza
#: (spazi, maiuscole) e quelle che il vero tratta come "tutte" (None, vuota,
#: sconosciuta): il finto deve rispondere come il vero a OGNUNA
MODI = (None, "", "paper", "live", " LIVE ", "Paper", "sconosciuta")


def _righe():
    """Paper e live mescolati, con i casi che la regola di modalita' del vero
    tratta in modo non ovvio:

    * id 3: chiusura SENZA `mode` di un'apertura LIVE -> vale live
      (`righe_della_modalita`: la chiusura eredita la modalita' dell'apertura);
    * id 5: riga senza `mode` -> vale 'paper' (default NOT NULL del database);
    * id 6: manuale dell'utente in live -> fuori dai numeri del bot (R6);
    * id 7: live aperta ieri -> liability viva, ma fuori dalla giornata.
    """
    oggi = ADESSO.isoformat()
    ieri = IERI.isoformat()
    return [
        {"id": 1, "event_id": EVENTO, "status": "won", "pnl": 5.0, "liability": 50.0,
         "bet_id": "b1", "placed_at": oggi, "settled_at": oggi, "meta": {},
         "mode": "paper", "closes_trade_id": None, "origin": "auto",
         "size": 2.0, "price": 26.0, "commission": None, "phase": "ft_cs", "side": "lay"},
        {"id": 2, "event_id": EVENTO, "status": "hedged", "pnl": None, "liability": 80.0,
         "bet_id": "b2", "placed_at": oggi, "settled_at": None,
         "meta": {"hedged_size": 1.0, "if_win": -12.5},
         "mode": "live", "closes_trade_id": None, "origin": "auto",
         "size": 2.0, "price": 41.0, "commission": None, "phase": "ft_cs", "side": "lay"},
        {"id": 3, "event_id": EVENTO, "status": "lost", "pnl": -3.25, "liability": 0.0,
         "bet_id": "b3", "placed_at": oggi, "settled_at": oggi, "meta": {},
         "mode": None, "closes_trade_id": 2, "origin": "auto",
         "size": 1.0, "price": 30.0, "commission": None, "phase": "ft_cs", "side": "back"},
        {"id": 4, "event_id": "35797769", "status": "lost", "pnl": -40.0, "liability": 40.0,
         "bet_id": "b4", "placed_at": oggi, "settled_at": oggi, "meta": {},
         "mode": "live", "closes_trade_id": None, "origin": "auto",
         "size": 2.0, "price": 21.0, "commission": None, "phase": "ft_cs", "side": "lay"},
        {"id": 5, "event_id": "35797769", "status": "open", "pnl": None, "liability": 33.0,
         "bet_id": "b5", "placed_at": oggi, "settled_at": None, "meta": {},
         "closes_trade_id": None, "origin": "auto",
         "size": 1.5, "price": 23.0, "commission": None, "phase": "ft_cs", "side": "lay"},
        {"id": 6, "event_id": "35800001", "status": "won", "pnl": 7.0, "liability": 20.0,
         "bet_id": "b6", "placed_at": oggi, "settled_at": oggi, "meta": {"manual": True},
         "mode": "live", "closes_trade_id": None, "origin": "manual",
         "size": 1.0, "price": 21.0, "commission": None, "phase": "ft_cs", "side": "lay"},
        {"id": 7, "event_id": "35800002", "status": "open", "pnl": None, "liability": 60.0,
         "bet_id": "b7", "placed_at": ieri, "settled_at": None, "meta": {},
         "mode": "live", "closes_trade_id": None, "origin": "auto",
         "size": 2.0, "price": 31.0, "commission": None, "phase": "ft_cs", "side": "lay"},
    ]


def _finto(righe=None):
    db = RR.DbMemoriaOmega({"id": 1, "status": "running", "mode": "live",
                            "params": {}, "daily_goal": 250.0, "stats": {}})
    for r in (righe if righe is not None else _righe()):
        db.trades.append(dict(r))
        db._id = max(db._id, int(r.get("id") or 0))
    return db


def _colonne_del_vero():
    """Le colonne che il lettore VERO chiede al database (dalla sua `select`):
    se domani il vero ne legge una in piu', il test la segue da solo."""
    sorgente = inspect.getsource(DBVERO._righe_per_aggregati)
    trovate = re.findall(r'\.select\("([^"]+)"\)', sorgente)
    assert len(trovate) == 1, "la select del lettore vero non si trova piu'"
    return [c.strip() for c in trovate[0].split(",")]


@pytest.fixture
def vero(monkeypatch):
    """Il VERO `omega_db.aggregates_coppia`, con il client del database che
    fallisce (nessuna RPC: il vero ripiega sul calcolo in casa) e le righe
    servite dal suo lettore, con le SOLE colonne della sua select."""
    colonne = _colonne_del_vero()

    def _sb_assente():
        raise RuntimeError("banco: nessun database")

    monkeypatch.setattr(DBVERO, "_sb", _sb_assente)
    monkeypatch.setattr(DBVERO, "_righe_per_aggregati",
                        lambda: [{c: r.get(c) for c in colonne} for r in _righe()])
    return DBVERO


def _tipi(d):
    return {k: type(v).__name__ for k, v in d.items()}


# ===========================================================================
# 1. LA FIRMA
# ===========================================================================
@pytest.mark.parametrize("nome", ["aggregates", "aggregates_coppia"])
def test_la_firma_del_finto_e_quella_del_vero(nome):
    """Nomi, ordine, tipo e default dei parametri identici al vero (senza
    `self`). Sul codice di 0aa76dfa e' ROSSO: al finto manca `mode`."""
    vero = inspect.signature(getattr(DBVERO, nome)).parameters
    finto = dict(inspect.signature(getattr(RR.DbMemoriaOmega, nome)).parameters)
    finto.pop("self")
    assert [(p.name, p.kind, p.default) for p in finto.values()] == \
        [(p.name, p.kind, p.default) for p in vero.values()]


def test_il_servizio_riconosce_il_finto_come_lettore_per_modalita():
    """Lo stesso esame che fa il servizio (`_con_modalita`): il finto deve
    passarlo come lo passa il vero, o il servizio somma paper e live."""
    for fn in (_finto().aggregates, _finto().aggregates_coppia,
               DBVERO.aggregates, DBVERO.aggregates_coppia):
        assert "mode" in inspect.signature(fn).parameters, fn


# ===========================================================================
# 2. IL COMPORTAMENTO: stesso risultato del vero, stesse chiavi, stessi tipi
# ===========================================================================
@pytest.mark.parametrize("modo", MODI)
@pytest.mark.parametrize("giornata", [True, False])
def test_aggregates_coppia_coincide_col_vero(vero, modo, giornata):
    ds = E.day_start_utc(ADESSO) if giornata else None
    atteso = vero.aggregates_coppia(ds, mode=modo)
    avuto = _finto().aggregates_coppia(ds, mode=modo)
    assert isinstance(avuto, tuple) and len(avuto) == 2
    for a, b in zip(avuto, atteso):
        assert a == b
        assert _tipi(a) == _tipi(b)


@pytest.mark.parametrize("modo", MODI)
def test_aggregates_coincide_col_vero(vero, modo):
    ds = E.day_start_utc(ADESSO)
    atteso = vero.aggregates(ds, mode=modo)
    avuto = _finto().aggregates(ds, mode=modo)
    assert avuto == atteso and _tipi(avuto) == _tipi(atteso)


def test_paper_e_live_non_si_sommano_mai():
    """I numeri, scritti: il confronto col vero non basta se il vero e il finto
    sbagliassero insieme (test che sa diventare rosso, par. 7 n.35)."""
    ds = E.day_start_utc(ADESSO)
    db = _finto()
    tutte_pag, tutte_bot = db.aggregates_coppia(ds)
    live_pag, live_bot = db.aggregates_coppia(ds, mode="live")
    paper_pag, paper_bot = db.aggregates_coppia(ds, mode="paper")
    # paper: id 1 (+5) e id 5 (senza mode = paper, aperta 33)
    assert paper_pag["realized_today"] == 5.0
    assert paper_pag["open_liability"] == 33.0
    assert paper_pag["total_count"] == 2
    # live: id 2 (hedged, residuo 12,5), 3 (chiusura di 2: -3,25), 4 (-40),
    # 6 (manuale +7), 7 (aperta ieri, 60)
    assert live_pag["realized_today"] == round(-3.25 - 40.0 + 7.0, 2)
    assert live_pag["open_liability"] == round(12.5 + 60.0, 2)
    assert live_pag["total_count"] == 5
    # i numeri del BOT live: la manuale (id 6) non c'e'
    assert live_bot["realized_today"] == round(-3.25 - 40.0, 2)
    # "tutte" e' la somma: e' proprio quella che il bot NON deve vedere
    assert tutte_pag["realized_today"] == round(5.0 - 3.25 - 40.0 + 7.0, 2)
    assert tutte_pag["total_count"] == 7
    assert live_pag != tutte_pag and paper_pag != tutte_pag
    assert tutte_bot["realized_today"] != live_bot["realized_today"]
    # la versione a un dizionario e' il primo della coppia, come nel vero
    assert db.aggregates(ds, mode="live") == live_pag


def test_una_modalita_senza_righe_da_zeri_con_le_chiavi_vere(vero):
    """Nessuna riga di quella modalita': zeri con TUTTE le chiavi del vero,
    mai un ripiego a tutta la tabella."""
    solo_paper = [r for r in _righe() if r["id"] in (1, 5)]
    pag, bot = _finto(solo_paper).aggregates_coppia(E.day_start_utc(ADESSO), mode="live")
    vuoto = E.aggregate_trades([], E.day_start_utc(ADESSO))
    assert pag == vuoto and bot == vuoto
    assert set(pag) == set(vero.aggregates(E.day_start_utc(ADESSO), mode="live"))


# ===========================================================================
# 3. ATTRAVERSO IL SERVIZIO VERO: niente CRITICAL, numeri della sola modalita'
# ===========================================================================
@pytest.mark.parametrize("modo", ["paper", "live"])
def test_il_servizio_col_finto_non_somma_e_non_grida(modo, caplog):
    S.svuota_le_cache()
    S._CACHE_AGGREGATI_MODO.clear()
    S._AVVISO_AGGREGATI_SENZA_MODO["dato"] = False
    ds = E.day_start_utc(ADESSO)
    db = _finto()
    with caplog.at_level(logging.CRITICAL, logger="omega.service"):
        pagina, del_bot = S._aggregati_cached(db, ds, 1000.0, forza=True, mode=modo)
    assert not [r for r in caplog.records if "SOMMATI" in r.getMessage()]
    assert S._AVVISO_AGGREGATI_SENZA_MODO["dato"] is False
    assert (pagina, del_bot) == db.aggregates_coppia(ds, mode=modo)
    assert pagina != db.aggregates(ds)
