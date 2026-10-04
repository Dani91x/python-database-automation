"""04/10/2026 (revisione del coordinatore) - il BUCO in_aggancio.

Nel motore del runner il controllo dell'aggancio viene PRIMA di quello del modo:
su un mercato non ancora seguito il comando e' ACCETTATO ``in_aggancio`` e
parcheggiato; il rifiuto ``mode_non_servibile`` arriva DOPO, come evento
``order`` terminale ``rifiutato`` (``motore_ordini.avanza_aggancio`` ->
``_esegui(errore_forzato=...)`` -> ``_estremi_errore``). E' lo scenario reale
dell'incidente (runner tennis in PAPER, partite nuove).

Regole provate qui:
  * un ``pending`` da ack ``in_aggancio`` NON ripristina la catena (il blocco e
    il ``motivo_blocco`` restano), ne' chiude l'episodio del CRITICAL;
  * il rifiuto ASINCRONO per modo/freno e' un blocco di catena come quello
    sincrono: riga 'error', nessun tentativo consumato, STESSO episodio (nessun
    secondo CRITICAL);
  * la catena si ripristina solo con una prova certa: ack SENZA motivo, oppure
    evento non-rifiuto di un ordine mandato DOPO l'inizio del blocco.

Il canale e' la ``PortaCanale`` VERA; il finto motore parla il protocollo
(ack con ``motivo``) e gli eventi nascono da ``motore_ordini.riga_specchio_da_esito``
+ ``_estremi_errore`` (le funzioni VERE del runner) con le chiavi di ``_emetti``.
"""
from __future__ import annotations

import json
import time
from datetime import timedelta

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy import porta_ordini as PO
from Betfair.safe_strategy.tests.test_porta_ordini_f5_2026_09_24 import (
    NOW, TOKEN, FakeDB, FakeMarket, FintoMotore, _attendi,
)
from Betfair.stream import motore_ordini as MO

ERRORE_MODO = str(MO.Rifiuto(MO.M_MODE, "mode 'live' non servibile dal runner in PAPER"))
MOTIVO_AGGANCIO = (f"{MO.M_IN_AGGANCIO}: mercato 1.250 non sottoscritto: aggancio richiesto")


class MotoreAggancio(FintoMotore):
    """Il runner che parcheggia in aggancio: ack ACCETTATO col motivo
    ``in_aggancio``; l'esito arriva dopo con ``rifiuta_parcheggiati``/``esegui``."""

    def __init__(self) -> None:
        super().__init__(attore="safe_tennis")
        self.parcheggiati: list[tuple] = []
        self.ack_motivo: str | None = MOTIVO_AGGANCIO

    def gestisci(self, ws, testo: str) -> None:
        msg = json.loads(testo)
        t, d = msg.get("t"), msg.get("d")
        if t != "comando":
            return super().gestisci(ws, testo)
        assert tuple(d.keys()) == PO.CHIAVI_COMANDO
        MO.valida_comando(self.attore, d)
        self.comandi.append(d)
        with self._lock:
            seq = self._nuovo_seq()
        self._manda(ws, "ack", {"ref": d["ref"], "seq": seq, "accettato": True,
                                "motivo": self.ack_motivo, "ricevuto_ms": 1.0})
        if self.ack_motivo is None:
            self._fine(ws, d)
        else:
            self.parcheggiati.append((ws, d))

    def _evento_esito(self, ws, d, fase: str, errore) -> None:
        riga = {"market_id": d["market_id"], "selection_id": d["selection_id"],
                "side": d["side"].lower(), "price": d["price"], "size": d["size"]}
        ev = MO.riga_specchio_da_esito({"ok": errore is None, "action": "place",
                                        "mode": d["mode"], "error": errore},
                                       cust_ref="awtq1", rid=1, mode=d["mode"], riga=riga)
        with self._lock:
            ev.update({"ref": d["ref"], "seq": self._nuovo_seq(), "fase": fase,
                       "esito_ms": round(time.time() * 1000.0, 1)})
        if errore is not None:
            ev.update(MO._estremi_errore(errore))
        self.eventi.append(ev)
        self._manda(ws, "order", ev)

    def rifiuta_parcheggiati(self, errore: str = ERRORE_MODO) -> None:
        for ws, d in self.parcheggiati:
            self._evento_esito(ws, d, "rifiutato", errore)
        self.parcheggiati.clear()


@pytest.fixture(autouse=True)
def _pulito():
    for c in (S._CATENA, S._PLACE_ATTEMPTS, S._SKIP_LOG_STATE, X._EPISODI_CATENA):
        c.clear()
    yield
    for c in (S._CATENA, S._PLACE_ATTEMPTS, S._SKIP_LOG_STATE, X._EPISODI_CATENA):
        c.clear()


@pytest.fixture
def canale(monkeypatch):
    monkeypatch.setattr(PO, "MAX_ETA_MS", 400)
    motore = MotoreAggancio()
    porta = PO.PortaCanale(porta_ws=47332, attore="safe_tennis", connetti=motore.connetti,
                           token_fn=lambda: TOKEN)
    porta.avvia()
    assert _attendi(porta.disponibile)
    monkeypatch.setattr(PO, "porta_esistente", lambda sport: porta)
    monkeypatch.setattr(S, "_porta_kw", lambda row: {"porta": porta})
    yield porta, motore
    porta.ferma()


def _riga(db, key="ev1:tennis:back"):
    tid = db.insert_trade({"event_id": "35795993", "sport": "tennis", "market_id": "1.250",
                           "selection_id": 101, "side": "back", "mode": "live",
                           "price": 1.05, "size": 2.0, "status": "pending",
                           "strategy": "tennis", "origin": "auto", "signal_key": key,
                           "meta": {"phase": "reserved"}})
    return tid, db.get_trade(tid)


def _sonda(db, ora, key="ev1:tennis:back"):
    tid, row = _riga(db, key)
    out = S._execute(db=db, market=FakeMarket(), trade_id=tid, row=row, params={},
                     now=ora, best_size=10.0, ladder=())
    return tid, out


def _risolvi(db, tid, ora):
    return S._risolvi_una_via_canale(db, db.get_trade(tid), now=ora, os_mod=S._omega_service())


def _critici(db):
    return [p for k, p in db.activity if k == "canale_rifiutato" and p.get("critical")]


def test_pending_in_aggancio_non_ripristina_ne_chiude_l_episodio(canale):
    porta, motore = canale
    db = FakeDB()
    # blocco in corso (rifiuto sincrono di prima)
    tid0, row0 = _riga(db, "k0")
    X.rifiuto_catena_asincrono(db, attore="safe_tennis", mode="live", trade_id=tid0,
                               ref="r0", errore=ERRORE_MODO, now=NOW)
    S._place_fail_catena(db, tid0, row0, f"canale_rifiutato:{ERRORE_MODO}", NOW, {})
    assert S._motivo_catena() is not None
    tid, out = _sonda(db, NOW + timedelta(seconds=61))
    assert out.status == "pending" and out.catena_servita is False
    assert S._motivo_catena() is not None, "un ack in_aggancio NON e' una prova"
    assert any(k[0] == "safe_tennis" for k in db._episodi_catena), "episodio ancora aperto"


def test_rifiuto_asincrono_dopo_aggancio_e_blocco_di_catena(canale):
    porta, motore = canale
    db = FakeDB()
    ora = NOW
    for i in range(3):        # tre sonde, una al minuto, tutte su mercati da agganciare
        tid, out = _sonda(db, ora, key=f"k{i}")
        assert out.status == "pending"
        motore.rifiuta_parcheggiati()
        assert _attendi(lambda: PO.terminale(porta.esiti(db.get_trade(tid)["meta"]
                                                          ["canale_ref"])))
        assert _risolvi(db, tid, ora) == "risolta"
        riga = db.get_trade(tid)
        assert riga["status"] == "error" and riga["meta"]["place"]["blocco_catena"] is True
        # il motivo non sparisce MAI fra una sonda e l'altra
        assert S._motivo_catena() is not None
        assert "runner tennis gira solo in PAPER" in S._motivo_catena()
        ora = ora + timedelta(seconds=X.CATENA_PROVA_S)
    assert len(_critici(db)) == 1, "un solo CRITICAL nell'episodio"
    kinds = [k for k, _ in db.activity]
    assert "place_retry" not in kinds and "place_exhausted" not in kinds
    assert "flumine_no_fill" not in kinds
    assert all(int(v.get("attempts") or 0) == 0 for v in S._PLACE_ATTEMPTS.values())


def test_ack_senza_motivo_e_prova_certa_e_chiude_il_blocco(canale):
    porta, motore = canale
    db = FakeDB()
    tid0, row0 = _riga(db, "k0")
    S._place_fail_catena(db, tid0, row0, f"canale_rifiutato:{ERRORE_MODO}", NOW, {})
    motore.ack_motivo = None          # il runner serve: ack accettato senza motivo
    _tid, out = _sonda(db, NOW + timedelta(seconds=61))
    assert out.catena_servita is True
    assert S._motivo_catena() is None


def test_evento_di_ordine_arrivato_dopo_aggancio_ripristina(canale):
    porta, motore = canale
    db = FakeDB()
    t_blocco = NOW + timedelta(seconds=5)
    tid0, row0 = _riga(db, "k0")
    S._place_fail_catena(db, tid0, row0, f"canale_rifiutato:{ERRORE_MODO}", t_blocco, {})
    tid, out = _sonda(db, t_blocco + timedelta(seconds=61))
    ws, d = motore.parcheggiati.pop()
    motore._fine(ws, d)               # agganciato e piazzato: accettato_betfair + abbinato
    ref = db.get_trade(tid)["meta"]["canale_ref"]
    assert _attendi(lambda: PO.terminale(porta.esiti(ref)))
    # il marcatore d'invio porta l'ora del giro (``now``) del servizio
    assert S._ts_iso(db.get_trade(tid)["meta"]["canale_inviato_at"]) > t_blocco.timestamp()
    _risolvi(db, tid, t_blocco + timedelta(seconds=62))
    assert S._motivo_catena() is None


def test_evento_di_un_ordine_mandato_prima_del_blocco_non_ripristina():
    db = FakeDB()
    tid0, row0 = _riga(db, "k0")
    S._place_fail_catena(db, tid0, row0, f"canale_rifiutato:{ERRORE_MODO}", NOW, {})
    assert S._catena_ripristinata(db, "tennis", "live",
                                  inviato_ts=(NOW - timedelta(seconds=30)).timestamp()) is False
    assert S._motivo_catena() is not None
    assert S._catena_ripristinata(db, "tennis", "live",
                                  inviato_ts=(NOW + timedelta(seconds=1)).timestamp()) is True
    assert S._motivo_catena() is None


def _riga_chiusura(db, dove: str):
    """Una CHIUSURA (place che riduce la posizione 7), con ``closes_trade_id`` in
    colonna oppure solo nel ``meta`` (le due grafie vere di Safe)."""
    riga = {"event_id": "35795993", "sport": "tennis", "market_id": "1.250",
            "selection_id": 101, "side": "lay", "mode": "live", "price": 1.10,
            "size": 2.0, "status": "pending", "strategy": "tennis", "origin": "auto",
            "signal_key": "chiusura", "meta": {"phase": "reserved",
                                                "canale_ref": "safe_tennis-t999",
                                                "canale_inviato_at": (NOW + timedelta(seconds=90)).isoformat()}}
    if dove == "colonna":
        riga["closes_trade_id"] = 7
    else:
        riga["meta"]["closes_trade_id"] = 7
    tid = db.insert_trade(riga)
    return tid


class _PortaEventi:
    """Porta con la ``MemoriaComandi`` VERA: l'evento entra dalla busta del runner."""

    attore = "safe_tennis"

    def __init__(self) -> None:
        self.memoria = PO.MemoriaComandi()

    def esiti(self, ref):
        return self.memoria.esito(ref)


def _evento(ref: str, fase: str, errore=None, matched: float = 0.0) -> dict:
    riga = {"market_id": "1.250", "selection_id": 101, "side": "lay", "price": 1.10,
            "size": 2.0}
    ev = MO.riga_specchio_da_esito({"ok": errore is None, "action": "place", "mode": "live",
                                    "error": errore}, cust_ref="awtq9", rid=9, mode="live",
                                   riga=riga)
    ev.update({"ref": ref, "seq": 1, "fase": fase, "esito_ms": 1.0,
               "size_matched": matched, "average_price_matched": 1.10 if matched else 0.0})
    if errore is not None:
        ev.update(MO._estremi_errore(errore))
    return ev


@pytest.mark.parametrize("dove", ["colonna", "meta"])
def test_evento_positivo_di_una_chiusura_non_tocca_il_blocco(monkeypatch, dove):
    db = FakeDB()
    tid0, row0 = _riga(db, "k0")
    X.rifiuto_catena_asincrono(db, attore="safe_tennis", mode="live", trade_id=tid0,
                               ref="r0", errore=ERRORE_MODO, now=NOW)
    S._place_fail_catena(db, tid0, row0, f"canale_rifiutato:{ERRORE_MODO}", NOW, {})
    porta = _PortaEventi()
    monkeypatch.setattr(PO, "porta_esistente", lambda sport: porta)
    tid = _riga_chiusura(db, dove)
    porta.memoria.ricevi_evento(_evento("safe_tennis-t999", "accettato_betfair"))
    S._risolvi_una_via_canale(db, db.get_trade(tid), now=NOW + timedelta(seconds=91),
                              os_mod=None)
    assert S._motivo_catena() is not None, "una chiusura non prova la catena delle aperture"
    assert any(k[0] == "safe_tennis" for k in db._episodi_catena), "episodio ancora aperto"


@pytest.mark.parametrize("dove", ["colonna", "meta"])
def test_rifiuto_terminale_di_una_chiusura_non_registra_un_blocco(monkeypatch, dove):
    db = FakeDB()
    porta = _PortaEventi()
    monkeypatch.setattr(PO, "porta_esistente", lambda sport: porta)
    tid = _riga_chiusura(db, dove)
    porta.memoria.ricevi_evento(_evento("safe_tennis-t999", "rifiutato", errore=ERRORE_MODO))
    S._risolvi_una_via_canale(db, db.get_trade(tid), now=NOW + timedelta(seconds=91),
                              os_mod=None)
    assert S._CATENA == {}, "il rifiuto di una chiusura non e' un blocco delle aperture"
    assert not any(k == "canale_rifiutato" for k, _ in db.activity)
    assert ((db.get_trade(tid).get("meta") or {}).get("place") or {}).get("blocco_catena") is None


def test_rifiuto_asincrono_non_di_catena_resta_come_prima():
    """Aggancio scaduto (``in_aggancio``): NON e' un blocco di catena."""
    db = FakeDB()
    errore = f"{MO.M_IN_AGGANCIO}: mercato 1.9 non sottoscritto entro 300 ms"
    assert X.rifiuto_catena_asincrono(db, attore="safe_tennis", mode="live", trade_id=1,
                                      ref="r", errore=errore, now=NOW) is None
    assert db.activity == []
