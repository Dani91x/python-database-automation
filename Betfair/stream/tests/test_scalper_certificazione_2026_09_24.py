# -*- coding: utf-8 -*-
"""LO SCALPER CALCIO SUL BANCO (24/09) - registro, adattatore e controlli.

Che cosa si difende:
  1. lo scalper e' REGISTRATO con replay e controlli veri (il registro punta a
     oggetti che esistono) e gli scenari obbligatori ci sono;
  2. l'OROLOGIO del replay passa il turno fra sessione e motore al tempo di
     mercato giusto (la sessione si sveglia ogni HEARTBEAT_S di mercato);
  3. la tabella finta `scalper_control` ha i CHECK della migrazione;
  4. PAPER = LIVE (S6) sul servizio VERO (`run_session` fino all'armamento), e
     la sua falsificazione: una mutazione del servizio che fa divergere paper e
     live deve far diventare S6 ROSSO;
  5. ogni controllo diventa ROSSO su una condotta sbagliata e tace su quella
     giusta, con ordini VERI di flumine e la strategia VERA (`ScalperStrategy`);
  6. K7 (difetto 3 del 15/09: prezzo medio letto da un campo che non esiste)
     diventa rosso con la mutazione REINTRODOTTA nel codice del bot;
  7. lo specchio VERO della sessione produce righe che P1/P2 accettano;
  8. il reperto A (CORRETTO il 24/09 su ordine dell'utente): `_place` legge il
     ritorno di `market.place_order` (difetto 2 del catalogo). Un rifiuto non
     lascia nulla nello slot, scrive `place_rifiutato` col motivo, e K2 resta
     muto pur SOLLECITATO; col difetto reintrodotto K2 torna rosso.

I finti parlano come il vero: gli ordini sono `BetfairOrder` di flumine creati
dal `_place` del bot, le righe hanno le chiavi dello specchio di produzione.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from Betfair.stream.backtest import banco_comune as BC
from Betfair.stream.backtest import registro_bot as REG
from Betfair.stream.scalper import certificazione as CERT
from Betfair.stream.scalper import scalper_bot as SB
from Betfair.stream.scalper import scalper_session as SS
from Betfair.stream.scalper.tools import replay_registrazioni as R

_RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _trova_live_raw() -> str:
    qui = _RADICE
    for _ in range(5):
        cand = os.path.join(qui, "_live_raw")
        if os.path.isdir(cand):
            return cand
        qui = os.path.dirname(qui)
    return os.path.join(_RADICE, "_live_raw")


LIVE_RAW = _trova_live_raw()
EVENTO = "35760084"
_ha_evento = os.path.isfile(os.path.join(LIVE_RAW, EVENTO, EVENTO + ".raw.jsonl"))


# ---------------------------------------------------------------------------
# i finti: parlano come il vero
# ---------------------------------------------------------------------------
class _Blotter:
    def __init__(self) -> None:
        self.ordini: List[Any] = []

    def __iter__(self):
        return iter(list(self.ordini))

    def strategy_orders(self, _s: Any) -> List[Any]:
        return list(self.ordini)


class _Mercato:
    """`flumine.markets.market.Market` visto dal bot: `market_id`,
    `place_order` che ritorna un BOOL, `cancel_order`, `blotter`."""

    market_id = "1.100"
    event_id = "35760084"

    def __init__(self, rifiuta: bool = False) -> None:
        self.blotter = _Blotter()
        self.rifiuta = rifiuta

    def place_order(self, order: Any, *_a: Any, **_k: Any) -> bool:
        if self.rifiuta:
            # `Transaction._validate_controls` -> `order.violation`, False
            order.violation("rifiuto del test")
            return False
        order.executable()
        order.bet_id = str(100 + len(self.blotter.ordini))
        self.blotter.ordini.append(order)
        return True

    def cancel_order(self, order: Any, size_reduction: Optional[float] = None) -> bool:
        return True


def _strategia(**extra: Any) -> Any:
    """La strategia VERA coi parametri che `run_session` le passa
    (VALIDATED_PARAMS + stake + dry_run=False)."""
    params = dict(SS.VALIDATED_PARAMS, stake=25.0, dry_run=False, **extra)
    cap = 25.0 * (params["price_max"] - 1.0) * 2.0
    return SB.ScalperStrategy(market_filter={"markets": ["x"]}, scalper_params=params,
                              max_selection_exposure=cap, max_order_exposure=cap,
                              max_trade_count=int(1e6), max_live_trade_count=int(1e6))


def _abbina(ordine: Any, prezzo: float, size: float) -> None:
    """Un abbinamento come lo registra flumine (`SimulatedOrder._update_matched`)."""
    ordine.simulated._update_matched([0, float(prezzo), float(size)])


@pytest.fixture
def simulato():
    with BC.simulazione_flumine():
        yield


def _oss(**kw: Any) -> CERT.Osservazione:
    base = dict(scenario="test", quando="t", ms=1_000_000, modalita="live")
    base.update(kw)
    return CERT.Osservazione(**base)


def _codici(oss: CERT.Osservazione, giri: int = 1) -> List[str]:
    mem = CERT.Memoria()
    out: List[str] = []
    for _ in range(giri):
        out += [v.codice for v in CERT.verifica(oss, {}, mem)]
    return out


# ===========================================================================
# 1. IL REGISTRO
# ===========================================================================
def test_lo_scalper_e_certificabile_e_le_sue_parti_esistono():
    scheda = REG.bot("scalper_calcio")
    assert scheda.certificabile
    assert callable(scheda.funzione_replay())
    ctl = scheda.modulo_controlli()
    for nome in ("elenco_controlli", "mai_sollecitati", "Referto", "Violazione"):
        assert hasattr(ctl, nome), nome
    scenari = scheda.elenco_scenari()
    for sc in ("base", "paper", "bot-fermo", "kill-switch", "esiti-ignoti",
               "rifiuti-betfair", "riavvio", "chiusura-abbinata-in-parte"):
        assert sc in scenari, sc
    assert os.path.isfile(os.path.join(_RADICE, scheda.spec)), scheda.spec
    assert "Betfair.stream.scalper.scalper_session" in scheda.moduli_produzione
    assert "Betfair.stream.scalper.scalper_bot" in scheda.moduli_produzione


def test_i_controlli_citano_il_catalogo_e_sono_tutti_distinti():
    codici = [c for c, _ in CERT.elenco_controlli()]
    assert len(codici) == len(set(codici))
    for fam in ("B", "K", "S", "P"):
        assert any(c.startswith(fam) for c in codici), fam
    # la famiglia K e' obbligatoria (catalogo par.7 punto 36)
    assert {"K1", "K2", "K3", "K4", "K5", "K6", "K7"} <= set(codici)


# ===========================================================================
# 2. L'OROLOGIO: il turno passa al tempo di MERCATO
# ===========================================================================
def test_la_sessione_si_sveglia_ogni_heartbeat_di_mercato(monkeypatch):
    monkeypatch.setattr(R, "ATTESA_MASSIMA_REALE_S", 20.0)
    o = R._Orologio()
    sveglie: List[float] = []

    def _sessione() -> None:
        for _ in range(4):
            o.sleep(5.0)
            sveglie.append(o.time())
        # la sessione finisce: il replay libera il motore (`ferma_motore`)
        o.libera()

    t = threading.Thread(target=_sessione)
    t.start()
    for s in range(0, 40):
        o.al_book(1000.0 + s)
    o.fine_motore()
    t.join(timeout=10)
    assert sveglie == [1005.0, 1010.0, 1015.0, 1020.0], sveglie


def test_le_scritture_prima_del_primo_book_hanno_l_ora_del_mercato():
    """Le scritture d'avvio (arming, running) avvengono PRIMA del primo book:
    devono portare l'istante di mercato d'inizio registrazione, non l'ora del
    PC (difetto visto nel primo replay del 24/09: S5 mai sollecitato)."""
    o = R._Orologio()
    o.ora_s = 1_700_000_000.0
    db = R._DbFinto(o, R.control_della_ui("1", "base"), {"event_id": "1"})
    db.set_control("1", status="running")
    assert db.scritture[-1]["ms"] == 1_700_000_000_000


@pytest.mark.skipif(not _ha_evento, reason="registrazione 35760084 assente")
def test_il_primo_publish_time_e_quello_della_registrazione():
    pt = R.primo_publish_time_ms(R.percorso_raw(LIVE_RAW, EVENTO))
    quando = datetime.fromtimestamp(pt / 1000.0, tz=timezone.utc)
    assert quando.strftime("%Y-%m-%d %H:%M") == "2026-06-30 15:05"


def test_orologio_buchi_isola_i_silenzi_veri_e_ignora_la_cadenza_normale():
    """Difetto S5 del 24/09 (referto: scalper_calcio 35797769, S5 violato 5764
    volte): il replay avanza il tempo di mercato SOLO quando un book arriva
    (`al_book`), un thread separato in produzione invece dorme sull'orologio
    REALE (docstring del modulo, 'L'OROLOGIO'). Un buco VERO della
    registrazione (nessun book per >= la soglia) va isolato da `buchi()`."""
    # `libera()`: nessun controllo si mette in mezzo, `al_book` non aspetta
    # turno (qui interessa solo la registrazione di `libro_ms`, non il turno)
    o = R._Orologio()
    o.libera()
    for ms in (0, 100, 250, 400):
        o.al_book(ms / 1000.0)
    o.al_book(7400 / 1000.0)   # buco: 7000 ms senza nessun book (> soglia)
    for ms in (7500, 7650):
        o.al_book(ms / 1000.0)
    assert o.buchi() == [(400, 7400)]
    # la cadenza NORMALE dei book (< soglia) non e' un buco
    o2 = R._Orologio()
    o2.libera()
    for ms in (0, 500, 1000, 1500):
        o2.al_book(ms / 1000.0)
    assert o2.buchi() == []
    # due silenzi piu' piccoli della soglia CONSECUTIVI restano due, non si
    # sommano da soli (la soglia si applica al singolo intervallo fra book)
    o3 = R._Orologio()
    o3.libera()
    for ms in (0, 1500, 3000):
        o3.al_book(ms / 1000.0)
    assert o3.buchi() == []


def test_orologio_ucciso_al_prossimo_sonno():
    o = R._Orologio()
    o.al_book  # noqa: B018 - solo per chiarezza: nessun book ancora
    o.fine_motore()
    o.uccidi_al_prossimo_sonno(R._ProcessoUcciso("x"))
    with pytest.raises(R._ProcessoUcciso):
        o.sleep(1.0)


# ===========================================================================
# 3. LA TABELLA FINTA HA I CHECK DELLA MIGRAZIONE
# ===========================================================================
def test_scalper_control_rifiuta_uno_stato_fuori_dal_check_e_s1_lo_vede():
    o = R._Orologio()
    db = R._DbFinto(o, R.control_della_ui("1", "base"), {"event_id": "1"})
    db.set_control("1", status="running")
    db.set_control("1", status="finito")          # non e' nel CHECK
    assert db.control["status"] == "running"      # Postgres l'avrebbe rifiutata
    oss = _oss(scritture_control=db.scritture)
    assert "S1" in _codici(oss)
    oss_ok = _oss(scritture_control=db.scritture[:1])
    assert "S1" not in _codici(oss_ok)


# ===========================================================================
# 4. PAPER = LIVE sul servizio VERO (e la sua falsificazione)
# ===========================================================================
def _catalogo_e_follow():
    raw = R.percorso_raw(LIVE_RAW, EVENTO)
    defs, ko = R.leggi_definizioni(raw)
    follow = {"event_id": EVENTO, "fixture_id": None, "league_id": None,
              "home_name": "A", "away_name": "B", "open_date": ko}
    return R.catalogo_dal_raw(defs), follow


@pytest.mark.skipif(not _ha_evento, reason="registrazione 35760084 assente")
def test_paper_e_live_armano_la_stessa_strategia():
    cat, follow = _catalogo_e_follow()
    p = R.parita_paper_live(EVENTO, R.control_della_ui(EVENTO, "base"), follow, cat)
    assert not p.get("errore"), p
    assert p["n_parametri"] > 50
    assert p["parametri_diversi"] == [] and p["client_diversi"] == []
    assert p["paper_trade_paper"] is True and p["paper_trade_live"] is False
    assert "S6" not in _codici(_oss(parita=p))


@pytest.mark.skipif(not _ha_evento, reason="registrazione 35760084 assente")
def test_s6_diventa_rosso_se_il_paper_arma_una_strategia_diversa(monkeypatch):
    """FALSIFICAZIONE sul servizio: il paper che cambia un parametro (qui il
    tetto transazioni, come un gate 'solo in paper', catalogo par.7.14).
    `run_session` importa `ScalperStrategy` al volo dal modulo del bot: la
    mutazione passa dal modulo, come passerebbe una modifica al codice."""
    originale = SB.ScalperStrategy
    SS_STATO = {"paper": False}

    class _PaperDiverso(originale):
        def __init__(self, *a: Any, **kw: Any) -> None:
            super().__init__(*a, **kw)
            if SS_STATO["paper"]:
                self.max_txn_hour = 0

    monkeypatch.setattr(SB, "ScalperStrategy", _PaperDiverso)
    cat, follow = _catalogo_e_follow()
    ctl = R.control_della_ui(EVENTO, "base")
    SS_STATO["paper"] = True
    par_p, cli_p = R.arma_e_cattura(EVENTO, dict(ctl, dry_run=True), follow, cat)
    SS_STATO["paper"] = False
    par_l, cli_l = R.arma_e_cattura(EVENTO, dict(ctl, dry_run=False), follow, cat)
    diversi = [(k, par_p.get(k), par_l.get(k)) for k in sorted(set(par_p) | set(par_l))
               if par_p.get(k) != par_l.get(k)]
    assert diversi, "la mutazione doveva far divergere i parametri"
    p = {"parametri_diversi": diversi, "client_diversi": [],
         "paper_trade_paper": True, "paper_trade_live": False}
    assert "S6" in _codici(_oss(parita=p))


def test_s6_diventa_rosso_se_il_client_differisce_oltre_paper_trade():
    p = {"parametri_diversi": [], "client_diversi": ["min_bet_validation"],
         "paper_trade_paper": True, "paper_trade_live": False}
    assert "S6" in _codici(_oss(parita=p))
    p2 = {"parametri_diversi": [], "client_diversi": [],
          "paper_trade_paper": False, "paper_trade_live": False}
    assert "S6" in _codici(_oss(parita=p2))


# ===========================================================================
# 5. OGNI CONTROLLO: rosso sulla condotta sbagliata, muto su quella giusta
# ===========================================================================
def _join(s: Any, m: _Mercato, sel: int = 7) -> Any:
    """Un ingresso JOIN vero (`_enter_join`): due gambe da 25 sul touch."""
    slot = s._slot(m.market_id, sel)
    s._enter_join(m, type("R", (), {"selection_id": sel})(), slot, 1_000,
                  2.0, 2.02, 500.0, 500.0, 2.01, 1, 50.0, 50.0)
    return slot


def _difetto_2_reintrodotto(monkeypatch: Any) -> None:
    """La MUTAZIONE del 24/09 rimessa nel CODICE DEL BOT: `_esegui_place` che
    chiama `place_order` e ne IGNORA il ritorno (il `_place` di prima)."""
    def _ignora(market: Any, order: Any) -> Optional[str]:
        market.place_order(order)
        return None

    monkeypatch.setattr(SB.ScalperStrategy, "_esegui_place", staticmethod(_ignora))


def test_k2_rosso_quando_il_bot_crede_a_ordini_rifiutati(simulato, monkeypatch):
    """FALSIFICAZIONE di K2 sul codice del bot: col difetto 2 reintrodotto la
    strategia tiene le gambe rifiutate e si dichiara QUOTING2."""
    _difetto_2_reintrodotto(monkeypatch)
    s = _strategia()
    m = _Mercato(rifiuta=True)
    slot = _join(s, m)
    assert slot.status == SB.QUOTING2
    cred = CERT.credenze(s)
    righe = [CERT.riga_ordine(o, False) for c in cred for o in CERT.ordini_seguiti(c)]
    oss = _oss(credenze=cred, ordini=righe)
    codici = _codici(oss, giri=CERT.GIRI_DI_TOLLERANZA)
    assert "K2" in codici and "K1" in codici


def test_k1_k2_k4_muti_su_ordini_accettati_e_vivi(simulato):
    s = _strategia()
    m = _Mercato()
    slot = _join(s, m)
    assert slot.status == SB.QUOTING2
    cred = CERT.credenze(s)
    righe = [CERT.riga_ordine(o, True) for o in m.blotter.ordini]
    oss = _oss(credenze=cred, ordini=righe)
    codici = _codici(oss, giri=CERT.GIRI_DI_TOLLERANZA + 1)
    for c in ("K1", "K2", "K3", "K4", "K5", "K6"):
        assert c not in codici, (c, codici)


def test_k3_rosso_su_uno_stato_letto_come_stringa():
    r = {"order_id": "o", "status": "OrderStatus.EXECUTABLE", "side": "BACK",
         "selection_id": 7, "market_id": "1.1", "size": 2.0, "price": 2.0,
         "size_matched": 0.0, "size_remaining": 2.0, "average_price_matched": 0.0,
         "in_blotter": True}
    assert "K3" in _codici(_oss(ordini=[r]))
    r2 = dict(r, status=SB.OrderStatus.EXECUTABLE.value)
    assert "K3" not in _codici(_oss(ordini=[r2]))


def test_k4_rosso_su_uno_slot_vivo_senza_nulla_a_mercato(simulato):
    s = _strategia()
    m = _Mercato()
    slot = _join(s, m)
    cred = CERT.credenze(s)
    # a mercato NON c'e' niente di vivo ne' di abbinato su quella selezione
    righe = [dict(CERT.riga_ordine(o, True), status=SB.OrderStatus.EXECUTION_COMPLETE.value,
                  size_remaining=0.0) for o in m.blotter.ordini]
    assert slot.status == SB.QUOTING2
    assert "K4" in _codici(_oss(credenze=cred, ordini=righe), giri=CERT.GIRI_DI_TOLLERANZA)


def test_k5_rosso_su_esposizione_senza_padrone_e_muto_se_pari(simulato):
    s = _strategia()
    m = _Mercato()
    slot = s._slot(m.market_id, 7)
    slot.status = SB.IDLE
    cred = CERT.credenze(s)
    esp = {(m.market_id, 7): (22.5, -25.0)}
    assert "K5" in _codici(_oss(credenze=cred, esposizioni=esp), giri=CERT.GIRI_DI_TOLLERANZA)
    esp_pari = {(m.market_id, 7): (0.51, 0.50)}
    assert "K5" not in _codici(_oss(credenze=cred, esposizioni=esp_pari),
                               giri=CERT.GIRI_DI_TOLLERANZA)


def test_k6_rosso_su_uno_slot_chiuso_con_un_ordine_vivo(simulato):
    s = _strategia()
    m = _Mercato()
    slot = _join(s, m)
    righe = [CERT.riga_ordine(o, True) for o in m.blotter.ordini]
    slot.status = SB.DONE            # il bot dichiara chiuso...
    slot.entry_back = slot.entry_lay = None   # ...e ha dimenticato le gambe vive
    cred = CERT.credenze(s)
    assert "K6" in _codici(_oss(credenze=cred, ordini=righe), giri=CERT.GIRI_DI_TOLLERANZA)


def _ciclo_flatten(s: Any, m: _Mercato) -> Dict[str, Any]:
    """Un ciclo che si chiude davvero nel bot: BACK 10 abbinato a 2,10 (ordine
    a 2,00: prezzo migliore) + LAY di flatten 11,05 abbinato a 1,90. Il bot
    lo chiude in `_drive_flatten` (|nw - nl| <= 0,02) e contabilizza il locked."""
    chiusure: List[Dict[str, Any]] = []
    R.installa_osservatori(s, [], chiusure, lambda: 0)
    slot = s._slot(m.market_id, 7)
    e = s._place(m, 7, "BACK", 2.0, 10.0)
    _abbina(e, 2.10, 10.0)
    f = s._place(m, 7, "LAY", 2.0, 11.05, floor_min=False, slot=slot)
    _abbina(f, 1.90, 11.05)
    slot.entry, slot.entry_side = e, "BACK"
    slot.status = SB.FLATTENING
    s._drive_flatten(m, slot, 1.9, 1.92, 1_000)
    assert slot.status == SB.DONE, "il ciclo doveva chiudersi"
    return chiusure[-1]


def test_k7_muto_sul_bot_vero(simulato):
    s = _strategia(size_step=0.0, live_min_bet=0.0, exact_exits=False)
    ch = _ciclo_flatten(s, _Mercato())
    assert abs(ch["locked"] - ch["worst_case_vero"]) <= 0.021
    assert "K7" not in _codici(_oss(chiusure_ciclo=[ch]))


def test_k7_rosso_col_difetto_3_reintrodotto_nel_bot(simulato, monkeypatch):
    """FALSIFICAZIONE sul CODICE DEL BOT: `_matched_position` che legge il
    prezzo medio da un campo che non esiste (`avg_price_matched`, difetto 3 del
    15/09) con `getattr(..., 0.0)`: gli abbinati spariscono, il bot chiude il
    ciclo a locked 0 e K7 lo vede."""
    vero = SB.ScalperStrategy._matched_position

    def _mutato(*orders: Any):
        class _Vista:
            def __init__(self, o: Any) -> None:
                self._o = o

            def __getattr__(self, n: str) -> Any:
                if n == "average_price_matched":
                    return getattr(self._o, "avg_price_matched", 0.0)
                return getattr(self._o, n)

        return vero(*[(_Vista(o) if o is not None else None) for o in orders])

    monkeypatch.setattr(SB.ScalperStrategy, "_matched_position", staticmethod(_mutato))
    s = _strategia(size_step=0.0, live_min_bet=0.0, exact_exits=False)
    ch = _ciclo_flatten(s, _Mercato())
    assert "K7" in _codici(_oss(chiusure_ciclo=[ch]))


def test_b1_rosso_su_un_ingresso_nato_dopo_il_divieto_e_muto_prima():
    r = {"order_id": "e1", "status": "Executable", "side": "BACK", "selection_id": 7,
         "market_id": "1.1", "size": 25.0, "price": 2.0, "size_matched": 0.0,
         "size_remaining": 25.0, "average_price_matched": 0.0, "in_blotter": True,
         "creato_ms": 2_000}

    class _O:
        id = "e1"

    cred = [{"chiave": ("1.1", 7), "stato": SB.QUOTING, "ingressi": [_O()], "uscite": [],
             "tolleranza": 0.02, "cicli": 0}]
    oss = _oss(ordini=[r], credenze=cred, ordini_nuovi={"e1"},
               divieti={"force_flat": 1_000})
    assert "B1" in _codici(oss)
    oss2 = _oss(ordini=[r], credenze=cred, ordini_nuovi={"e1"},
                divieti={"force_flat": 5_000})
    assert "B1" not in _codici(oss2)
    # il divieto 'in gioco' vale per IL SUO mercato
    oss3 = _oss(ordini=[r], credenze=cred, ordini_nuovi={"e1"},
                divieti={"in_gioco@1.2": 1_000})
    assert "B1" not in _codici(oss3)


def test_b2_rosso_su_posizione_aperta_in_gioco():
    esp = {("1.1", 7): (20.0, -10.0)}
    cred = [{"chiave": ("1.1", 7), "stato": SB.FLATTENING, "ingressi": [], "uscite": [],
             "tolleranza": 0.02, "cicli": 1}]
    oss = _oss(inplay=True, sessione_viva=True, esposizioni=esp, credenze=cred)
    assert "B2" in _codici(oss, giri=CERT.GIRI_DI_TOLLERANZA)
    oss_ok = _oss(inplay=True, sessione_viva=True, esposizioni={("1.1", 7): (0.3, 0.29)},
                  credenze=cred)
    assert "B2" not in _codici(oss_ok, giri=CERT.GIRI_DI_TOLLERANZA)


@pytest.mark.parametrize("size,side,rosso", [
    (2.37, "BACK", True), (1.5, "BACK", True), (0.3, "LAY", True),
    (2.0, "BACK", False), (0.5, "LAY", False), (25.0, "LAY", False)])
def test_b3_legalita_it(size, side, rosso):
    r = {"order_id": "o", "status": "Executable", "side": side, "selection_id": 7,
         "market_id": "1.1", "size": size, "price": 2.0, "in_blotter": True,
         "sostituto": False}
    assert ("B3" in _codici(_oss(ordini=[r], ordini_nuovi={"o"}))) is rosso
    # un SOSTITUTO (replace del park) non e' un piazzamento nuovo
    r2 = dict(r, sostituto=True)
    assert "B3" not in _codici(_oss(ordini=[r2], ordini_nuovi={"o"}))


def test_b4_b5_b6():
    class _O:
        id = "e1"

    cred = [{"chiave": ("1.1", 7), "stato": SB.QUOTING, "ingressi": [_O()], "uscite": [],
             "tolleranza": 0.02, "cicli": 0}]
    r = {"order_id": "e1", "status": "Executable", "side": "BACK", "selection_id": 7,
         "market_id": "1.1", "size": 30.0, "price": 2.0, "in_blotter": True}
    assert "B4" in _codici(_oss(ordini=[r], credenze=cred, ordini_nuovi={"e1"}, stake=25.0))
    assert "B4" not in _codici(_oss(ordini=[dict(r, size=25.0)], credenze=cred,
                                    ordini_nuovi={"e1"}, stake=25.0))
    assert "B5" in _codici(_oss(cap_esposizione=180.0, esposizioni={("1.1", 7): (5.0, -200.0)}))
    assert "B5" not in _codici(_oss(cap_esposizione=180.0,
                                    esposizioni={("1.1", 7): (5.0, -100.0)}))
    assert "B6" in _codici(_oss(ordini=[r], credenze=cred, ordini_nuovi={"e1"},
                                max_txn_hour=300, ingressi_ultima_ora=301))
    assert "B6" not in _codici(_oss(ordini=[r], credenze=cred, ordini_nuovi={"e1"},
                                    max_txn_hour=300, ingressi_ultima_ora=300))


def test_s2_s3_s4_s5_s7():
    # S2: stop senza force-flat dopo un heartbeat e mezzo
    assert "S2" in _codici(_oss(ms=10_000, stop_richiesto_ms=1_000, stop_causa="ui",
                                force_flat=False))
    assert "S2" not in _codici(_oss(ms=10_000, stop_richiesto_ms=1_000, stop_causa="ui",
                                    force_flat=True, force_flat_ms=4_000))
    # S3: sessione chiusa con un ordine vivo e nessuna dichiarazione
    vivo = {"order_id": "o", "status": "Executable", "side": "BACK", "selection_id": 7,
            "market_id": "1.1", "size": 25.0, "price": 2.0, "size_matched": 0.0,
            "size_remaining": 25.0, "average_price_matched": 0.0, "in_blotter": True}
    assert "S3" in _codici(_oss(fine_sessione=True, ordini=[vivo], stato_finale="done"))
    assert "S3" not in _codici(_oss(fine_sessione=True, ordini=[vivo], stato_finale="done",
                                    dichiarato_non_flat=True))
    # S4: fermata dall'utente ma stato 'done'
    assert "S4" in _codici(_oss(fine_sessione=True, stop_causa="ui", stato_finale="done"))
    assert "S4" not in _codici(_oss(fine_sessione=True, stop_causa="ui",
                                    stato_finale="stopped"))
    assert "S4" in _codici(_oss(fine_sessione=True, stop_causa="crash", stato_finale="done"))
    # S5: heartbeat fermo 12 s
    stats = {"orders_placed": 0, "cycles": 0, "pnl_locked": 0.0}
    assert "S5" in _codici(_oss(running_da_ms=0, heartbeat_ms=[5_000, 17_000],
                                ms=18_000, stats=stats))
    assert "S5" not in _codici(_oss(running_da_ms=0, heartbeat_ms=[5_000, 10_000, 15_000],
                                    ms=18_000, stats=stats))
    # S7: orfano del processo morto non seguito ne' dichiarato
    orfano = dict(vivo, order_id="z", size_matched=10.0)
    assert "S7" in _codici(_oss(orfani_dopo_riavvio=[orfano]), giri=CERT.GIRI_DI_TOLLERANZA)
    assert "S7" not in _codici(_oss(orfani_dopo_riavvio=[orfano],
                                    allarmi=[{"message": "posizione ORFANA della sessione"}]),
                               giri=CERT.GIRI_DI_TOLLERANZA)


def test_s5_scomputa_un_buco_vero_della_registrazione_ma_resta_rosso_su_un_ritardo_vero():
    """Difetto dell'ADATTATORE del 24/09 (referto: scalper_calcio 35797769, S5
    violato 5764 volte, esempio 'heartbeat fermo per 7317 ms fra 1783701117089
    e 1783701124406'). Verificato sulla registrazione vera: in
    quell'intervallo ci sono DUE silenzi (3731 ms + 2588 ms = 6319 ms) fra i
    book, nessuno dei due da solo sopra HEARTBEAT_S+1 (6000 ms): il servizio
    ha scritto il heartbeat al PRIMO book utile, come deve fare un replay che
    avanza il tempo SOLO ai book (il servizio VERO dorme su un thread a parte,
    sull'orologio REALE: mai toccato qui). S5 deve tacere quando il buco
    spiega il ritardo, e restare rosso quando non lo spiega (falsificazione:
    il fix non deve rendere S5 cieco a un ritardo vero del servizio)."""
    stats = {"orders_placed": 0, "cycles": 0, "pnl_locked": 0.0}
    a, b = 1_783_701_117_089, 1_783_701_124_406
    assert b - a == 7317
    buchi_veri = [(1_783_701_117_297, 1_783_701_121_028),
                  (1_783_701_121_818, 1_783_701_124_406)]
    oss = _oss(running_da_ms=0, heartbeat_ms=[a, b], ms=b + 1000, stats=stats,
               buchi_registrazione_ms=buchi_veri)
    assert "S5" not in _codici(oss)
    # FALSIFICAZIONE 1: stesso ritardo di 7317 ms ma SENZA alcun buco
    # dichiarato (book fitti, il servizio e' semplicemente stato lento): rosso
    oss_senza_buchi = _oss(running_da_ms=0, heartbeat_ms=[a, b], ms=b + 1000, stats=stats)
    assert "S5" in _codici(oss_senza_buchi)
    # FALSIFICAZIONE 2: un buco troppo piccolo per spiegare tutto il ritardo
    # (800 ms su 7317) resta rosso: non basta CHE ci sia un buco, deve
    # spiegare lo scarto oltre la cadenza
    oss_buco_parziale = _oss(running_da_ms=0, heartbeat_ms=[a, b], ms=b + 1000, stats=stats,
                              buchi_registrazione_ms=[(a + 100, a + 900)])
    assert "S5" in _codici(oss_buco_parziale)


# ===========================================================================
# 7. LO SPECCHIO VERO produce righe che P1/P2 accettano
# ===========================================================================
def test_lo_specchio_vero_della_sessione_passa_p1_p2(simulato, monkeypatch):
    from Betfair.stream import db as STREAM_DB

    righe: List[Dict[str, Any]] = []
    monkeypatch.setattr(STREAM_DB, "upsert_live_order", lambda row: righe.append(dict(row)))
    monkeypatch.setattr(STREAM_DB, "upsert_live_position", lambda row: None)
    monkeypatch.setattr(STREAM_DB, "find_live_order_ref", lambda mode, bet_id: None)
    s = _strategia()
    m = _Mercato()
    _join(s, m)
    _abbina(m.blotter.ordini[0], 2.02, 10.0)
    mirror = SS._make_session_mirror([m.market_id], "live")
    mirror.process_orders(m, list(m.blotter.ordini))
    assert len(righe) == 2
    ordini = [CERT.riga_ordine(o) for o in m.blotter.ordini]
    assert not [c for c in _codici(_oss(specchio=righe, ordini=ordini)) if c.startswith("P")]
    # FALSIFICAZIONE: una riga che dichiara piu' abbinato del mercato, una senza stato
    gonfia = dict(righe[0], size_matched=25.0)
    assert "P2" in _codici(_oss(specchio=[gonfia], ordini=ordini))
    monca = dict(righe[0], status=None)
    assert "P1" in _codici(_oss(specchio=[monca], ordini=ordini))


# ===========================================================================
# 8. IL REPERTO A (corretto il 24/09): `_place` legge il ritorno di `place_order`
# ===========================================================================
def test_place_rifiutato_non_torna_un_ordine(simulato):
    s = _strategia()
    o = s._place(_Mercato(rifiuta=True), 7, "BACK", 2.0, 25.0)
    assert o is None


def _attivita(s: Any) -> List[Any]:
    """Il sink di telemetria come lo collega `run_session`: (kind, payload)."""
    righe: List[Any] = []
    s.event_sink = lambda kind, payload: righe.append((kind, dict(payload)))
    return righe


def _mercato_flumine_che_rifiuta(quanti: int) -> Any:
    """Un `flumine.markets.market.Market` VERO dentro un `FlumineSimulation`
    VERO, col trading control di rifiuto del banco (`_controllo_rifiuti`):
    il rifiuto passa da `Transaction._validate_controls` -> `_on_error` ->
    `order.violation` -> `place_order` torna False, come in produzione."""
    from flumine import FlumineSimulation
    from flumine.markets.market import Market

    quadro = FlumineSimulation(client=BC.cliente_simulato())
    ctl = R._controllo_rifiuti(quadro, quanti)
    # in TESTA: il mercato non e' registrato nel quadro e il MARKET_VALIDATION
    # di flumine lo boccerebbe prima (rifiuto vero anche quello, ma qui si
    # vuole il motivo del banco); nel replay il mercato c'e' e l'ordine e' lo
    # stesso
    quadro.trading_controls.insert(0, ctl)
    return Market(quadro, "1.100", None), ctl


def test_rifiuto_vero_di_flumine_slot_vuoto_attivita_scritta_e_k2_sollecitato_muto(simulato):
    s = _strategia()
    att = _attivita(s)
    m, ctl = _mercato_flumine_che_rifiuta(2)
    slot = _join(s, m)
    # la prima gamba (BACK) e' rifiutata: lo slot NON tiene niente e resta IDLE
    # (il ramo "ordine non partito" gia' esistente in `_enter_join`).
    # D2 (24/09): il rifiuto arma il FRENO dello scalper (1 s di mercato) e la
    # seconda gamba (LAY) della stessa selezione NON parte: prima partiva per
    # essere comunque cancellata (la coppia vuole entrambe le gambe).
    assert len(ctl.ordini) == 1
    assert slot.status == SB.IDLE
    assert slot.entry_back is None and slot.entry_lay is None and slot.entry is None
    assert slot.flatten_orders == []
    assert list(m.blotter) == []
    for o in ctl.ordini:
        assert o.status == SB.OrderStatus.VIOLATION
        assert SB.ScalperStrategy._has_live(o) is False
    # la riga di attivita' col MOTIVO vero del rifiuto, e nessun 'place'
    rif = [p for k, p in att if k == "place_rifiutato"]
    assert len(rif) == 1
    assert {p["side"] for p in rif} == {"BACK"}
    assert rif[0]["riprovo_fra_s"] == 1.0
    freno = [p for k, p in att if k == "freno_rifiuti"]
    assert len(freno) == 1 and freno[0]["side"] == "LAY"
    for p in rif:
        assert "REPLAY_RIFIUTA_PRIMI" in p["motivo"]
        assert p["order_id"] in {str(o.id) for o in ctl.ordini}
    assert not [k for k, _ in att if k == "place"]
    assert s.stats["orders_placed"] == 0
    # K2 SOLLECITATO (a mercato ci sono i rifiuti) e MUTO (il bot non ci crede)
    righe = [CERT.riga_ordine(o, False) for o in ctl.ordini]
    oss = _oss(credenze=CERT.credenze(s), ordini=righe)
    sollecitati: Dict[str, int] = {}
    mem = CERT.Memoria()
    codici: List[str] = []
    for _ in range(CERT.GIRI_DI_TOLLERANZA + 1):
        codici += [v.codice for v in CERT.verifica(oss, sollecitati, mem)]
    assert sollecitati.get("K2"), sollecitati
    assert "K2" not in codici and "K1" not in codici, codici


def test_rifiuto_di_una_sola_gamba_cancella_l_altra_e_lo_slot_resta_idle(simulato):
    """Il ramo ESISTENTE di `_enter_join` (una gamba None -> cancel dell'altra,
    nessuna quota): ora ci si arriva anche col rifiuto. D2 (24/09): si rifiuta
    la SECONDA gamba (col primo rifiutato il freno non farebbe partire la
    seconda, vedi il test sopra)."""
    class _RifiutaIlPrimo(_Mercato):
        def __init__(self) -> None:
            super().__init__()
            self.piazzati = 0
            self.cancellati: List[Any] = []

        def place_order(self, order: Any, *a: Any, **k: Any) -> bool:
            self.piazzati += 1
            self.rifiuta = self.piazzati == 2
            return super().place_order(order, *a, **k)

        def cancel_order(self, order: Any, size_reduction: Optional[float] = None) -> bool:
            self.cancellati.append(order)
            return True

    s = _strategia()
    m = _RifiutaIlPrimo()
    slot = _join(s, m)
    assert slot.status == SB.IDLE
    assert slot.entry_back is None and slot.entry_lay is None
    assert len(m.blotter.ordini) == 1 and m.cancellati == m.blotter.ordini


def test_accettato_parita_con_prima(simulato):
    """Ordine ACCETTATO: stesso oggetto nel blotter, 'place' emesso una volta,
    contatore +1, tracciato nello slot, JOIN in QUOTING2 come prima."""
    s = _strategia()
    att = _attivita(s)
    m = _Mercato()
    slot = s._slot(m.market_id, 7)
    o = s._place(m, 7, "LAY", 2.0, 3.0, floor_min=False, slot=slot)
    assert o is not None and o in m.blotter.ordini
    assert o.status == SB.OrderStatus.EXECUTABLE and SB.ScalperStrategy._has_live(o)
    assert slot.flatten_orders == [o]
    assert [k for k, _ in att] == ["place"]
    assert s.stats["orders_placed"] == 1
    s2 = _strategia()
    slot2 = _join(s2, _Mercato(), sel=8)
    assert slot2.status == SB.QUOTING2
    assert slot2.entry_back is not None and slot2.entry_lay is not None


def test_place_order_che_solleva(simulato):
    """Un'eccezione di `place_order`: se l'ordine NON e' nel blotter e' un
    rifiuto (None + attivita'); se c'e' e' partito e si segue (mai orfani)."""
    class _Solleva(_Mercato):
        def __init__(self, dopo_il_blotter: bool) -> None:
            super().__init__()
            self.dopo = dopo_il_blotter

        def place_order(self, order: Any, *a: Any, **k: Any) -> bool:
            if self.dopo:
                super().place_order(order)
            raise RuntimeError("guasto di rete")

    s = _strategia()
    att = _attivita(s)
    slot = s._slot("1.100", 7)
    s._ora_mercato_ms = 0          # D2 (24/09): il freno conta il tempo di mercato
    assert s._place(_Solleva(False), 7, "BACK", 2.0, 25.0, slot=slot) is None
    assert slot.flatten_orders == []
    rif = [p for k, p in att if k == "place_rifiutato"]
    assert len(rif) == 1 and "guasto di rete" in rif[0]["motivo"]
    m = _Solleva(True)
    s._ora_mercato_ms = 2_000      # oltre il primo passo del freno (1 s)
    o = s._place(m, 7, "BACK", 2.0, 25.0, slot=slot)
    assert o is not None and o in m.blotter.ordini and slot.flatten_orders == [o]


def test_il_banco_vede_i_rifiuti_anche_quando_il_bot_non_li_segue(simulato):
    """Il banco (`_Banco.righe_correnti`) mette fra gli ordini osservati i
    rifiuti iniettati dallo scenario anche se il bot li ha lasciati cadere:
    senza, K2 resterebbe MAI SOLLECITATO proprio in 'rifiuti-betfair'."""
    from types import SimpleNamespace

    s = _strategia()
    m, ctl = _mercato_flumine_che_rifiuta(2)
    _join(s, m)
    finto = SimpleNamespace(ordini_di=lambda _ss: [], rifiuti=ctl)
    righe = R._Banco.righe_correnti(finto, s, CERT.credenze(s))
    # D2 (24/09): col freno la seconda gamba della coppia non parte piu'
    assert len(ctl.ordini) == 1 and len(righe) == 1
    assert sorted(r["order_id"] for r in righe) == sorted(str(o.id) for o in ctl.ordini)
    assert all(CERT._rifiutato(r) for r in righe)
    senza = SimpleNamespace(ordini_di=lambda _ss: [], rifiuti=None)
    assert R._Banco.righe_correnti(senza, s, CERT.credenze(s)) == []
