"""26/09/2026 - SCALPER: auto-mode contro il freno, origine dei follow, force-flat dichiarato.

Reperti del test e2e del 26/09 (AUDIT_2026-09-25/e2e_fase2/ADMIN26_AUTOMODE_SAFE.md par. A):
  1. 09:41:59Z freno tirato; 09:42:42Z l'auto-mode scrive 2 righe NUOVE
     'requested' (``auto_armata``) e ``stats.auto.motivo_blocco`` resta null;
     le partite fermate DAL FRENO finiscono fra le "chiuse a mano" e non si
     riarmano piu' al rilascio;
  2. ``Db.segui`` scriveva ``live_follow`` senza ``origine`` -> default
     'manuale': il follow aperto dall'auto-mode sembrava seguito a mano;
  3. lo stop "posizione NON flat dopo 30s" chiudeva la riga con
     ``error=null``: il residuo (anche il micro-residuo accettato) non era
     dichiarato nella riga.

Tutto SENZA database e SENZA rete; i finti del Db sono quelli del test
dell'auto-mode del 25/09 (stessi metodi e chiavi di ``scalper_service.Db``).
File ASCII-only.
"""
from __future__ import annotations

import inspect
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, List

import pytest

from Betfair.stream import canale_bot as CB
from Betfair.stream.scalper import auto_mode as AM
from Betfair.stream.scalper import scalper_service as SVC
from Betfair.stream.scalper import scalper_session as SS
from Betfair.stream.tests.test_scalper_auto_mode_2026_09_25 import (
    ORA, ORA_EP, DbFinto, _db_vero, _iso, _stato, riga_control, riga_feed, riga_servizio)

FRENO = "db_kill_switch_attivo"


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(AM.ENV_TETTO, raising=False)
    monkeypatch.delenv(CB.ENV_SCALPER, raising=False)
    CB.azzera_statistiche()


def _stats_auto(db: DbFinto) -> dict:
    return db.nomi("set_servizio")[-1][1]["stats"]["auto"]


# ===========================================================================
# 1. il freno: l'auto-mode non arma e lo dice
# ===========================================================================
def test_a_freno_tirato_nessuna_riga_nuova_e_motivo_freno() -> None:
    db = DbFinto(riga_servizio(), [riga_feed("36090936"), riga_feed("36090937")])
    es = SVC.giro_auto(db, _stato(), [], ORA_EP, freno=FRENO)
    assert es["armate"] == []
    assert db.nomi("arma") == [] and db.nomi("segui") == []
    assert [a for a in getattr(db, "attivita", []) if a[1] == "auto_armata"] == []
    auto = _stats_auto(db)
    assert auto["motivo_blocco"].startswith("freno tirato (%s)" % FRENO)
    assert auto["freno"] == FRENO
    assert es["motivo"] == auto["motivo_blocco"]


def test_a_freno_tirato_il_motivo_c_e_anche_con_sessioni_in_piedi() -> None:
    vive = [riga_control("36090788", status="running"),
            riga_control("36090854", status="requested")]
    db = DbFinto(riga_servizio(params={"auto_max_partite": 4}), [riga_feed("1")])
    es = SVC.giro_auto(db, _stato(), vive, ORA_EP, freno=FRENO)
    assert es["armate"] == [] and db.nomi("arma") == []
    assert _stats_auto(db)["motivo_blocco"].startswith("freno tirato")


def test_rilascio_del_freno_arma_al_giro_subito_dopo() -> None:
    st = _stato()
    db = DbFinto(riga_servizio(), [riga_feed("1")])
    SVC.giro_auto(db, st, [], ORA_EP, freno=FRENO)
    assert db.nomi("arma") == []
    # 3 s dopo (un giro del supervisore, non 15): il cambio del freno basta
    es = SVC.giro_auto(db, st, [], ORA_EP + 3, freno=None)
    assert es["armate"] == ["1"]
    auto = _stats_auto(db)
    assert auto["motivo_blocco"] is None and auto["freno"] is None


def test_senza_freno_comportamento_di_prima() -> None:
    db = DbFinto(riga_servizio(), [riga_feed("1")])
    es = SVC.giro_auto(db, _stato(), [], ORA_EP)
    assert es["armate"] == ["1"] and es["motivo"] is None


def test_motivo_blocco_puro_freno_prima_di_tutto() -> None:
    kw = dict(acceso=True, bloccato=False, feed_letto=True, feed_vivo=True, partite_feed=3,
              origine_ok=True, tetto=2, sessioni=2, conflitto=None, armabili=3)
    assert AM.motivo_blocco(**kw) is None
    assert AM.motivo_blocco(**kw, freno=FRENO).startswith("freno tirato (%s)" % FRENO)
    assert AM.motivo_blocco(**{**kw, "acceso": False}, freno=FRENO) is None


def test_il_supervisore_legge_il_freno_prima_del_giro_auto() -> None:
    src = inspect.getsource(SVC.main)
    i_freno = src.index("freno = freno_supervisore()")
    i_giro = src.index("giro_auto(db, stato_auto")
    assert i_freno < i_giro, "il freno va letto PRIMA dell'auto-mode"
    assert "freno=freno" in src[i_giro:i_giro + 120]


# ===========================================================================
# 1bis. fermata DAL FRENO != chiusa a mano
# ===========================================================================
def _dopo_accensione() -> str:
    return _iso(ORA - timedelta(minutes=10))        # accensione = ORA - 1h


@pytest.mark.parametrize("riga,atteso", [
    # automatica fermata dal freno: si riarma
    ({"status": "stopped", "origine": "auto", "requested_at": _iso(ORA - timedelta(minutes=10)),
      "fermata_dal_freno": FRENO}, None),
    ({"status": "stopped", "origine": "auto", "requested_at": _iso(ORA - timedelta(minutes=10)),
      "stats": {"fermata_dal_freno": FRENO, "pnl_locked": 0.1}}, None),
    ({"status": "done", "origine": "auto", "requested_at": _iso(ORA - timedelta(minutes=10)),
      "stats": {"fermata_dal_freno": "file_STOP_SCALPER"}}, "conclusa"),
    # senza marcatore: resta "chiusa a mano" (regola di prima)
    ({"status": "stopped", "origine": "auto", "requested_at": _iso(ORA - timedelta(minutes=10)),
      "fermata_dal_freno": None}, "chiusa a mano"),
    # sessione dell'utente: la riarma l'utente, non l'auto-mode
    ({"status": "stopped", "origine": "manuale",
      "requested_at": _iso(ORA - timedelta(minutes=10)), "fermata_dal_freno": FRENO},
     "chiusa a mano"),
    # in errore resta in errore anche col marcatore
    ({"status": "error", "origine": "auto", "fermata_dal_freno": FRENO}, "in errore"),
])
def test_motivo_esclusione_fermata_dal_freno(riga: dict, atteso: Any) -> None:
    assert AM.motivo_esclusione(riga, _iso(ORA - timedelta(hours=1))) == atteso


def test_al_rilascio_la_partita_fermata_dal_freno_si_riarma() -> None:
    ferma = {**riga_control("36090788", status="stopped", requested_at=_dopo_accensione()),
             "fermata_dal_freno": FRENO}
    db = DbFinto(riga_servizio(), [riga_feed("36090788")], control={"36090788": ferma},
                 follow={"36090788": "STREAMING"})
    es = SVC.giro_auto(db, _stato(), [], ORA_EP, freno=None)
    assert es["armate"] == ["36090788"]
    arma = db.nomi("arma")[0]
    assert arma[3] is ferma                     # update SOLO sulla stessa riga ferma
    assert arma[2]["origine"] == "auto" and arma[2]["dry_run"] is True


def test_query_righe_control_legge_il_marcatore_del_freno() -> None:
    db = _db_vero()
    db.righe_control(["1"])
    sel = [c for c in db.sb.reg if c[0] == "select"][0][1][0]
    assert "fermata_dal_freno:stats->fermata_dal_freno" in sel
    assert sel.startswith("event_id,status,requested_at,dry_run,origine")


def test_la_sessione_non_avviata_col_freno_porta_il_marcatore(monkeypatch) -> None:
    scritte: List[dict] = []
    db = SimpleNamespace(set_control=lambda ev, **c: scritte.append(c),
                         log=lambda *a, **k: None)
    monkeypatch.setattr(SS, "motivo_freno", lambda: FRENO)
    assert SS.non_partire_col_freno(db, "36090936") == FRENO
    assert scritte[0]["status"] == "stopped"
    assert AM.fermata_dal_freno(scritte[0]) == FRENO


# ===========================================================================
# 2. il follow aperto dall'auto-mode e' 'auto'
# ===========================================================================
def test_segui_scrive_origine_auto_senza_sovrascrivere() -> None:
    db = _db_vero()
    db.segui({"event_id": "35", "home": "A", "away": "B", "open_date": "x",
              "competition": "Serie A"})
    ups = [c for c in db.sb.reg if c[0] == "upsert"][0]
    assert ups[1][0]["origine"] == "auto"
    assert ups[2] == {"on_conflict": "event_id", "ignore_duplicates": True}
    # un follow dell'utente gia' presente non si riscrive (nessun update)
    assert [c for c in db.sb.reg if c[0] == "update"] == []


# ===========================================================================
# 3. force-flat "NON flat dopo 30s" dichiarato nella riga
# ===========================================================================
def _ordine(side: str, sm: float, ap: float, st: str = "EXECUTION_COMPLETE") -> Any:
    """Un ordine flumine coi campi veri letti da ``_esposizioni_nette``."""
    return SimpleNamespace(market_id="1.200", selection_id=47972, side=side,
                           size_matched=sm, average_price_matched=ap,
                           status=SimpleNamespace(name=st))


def _fw(*ordini: Any) -> Any:
    return SimpleNamespace(markets=[SimpleNamespace(blotter=list(ordini))])


def test_micro_residuo_accettato_si_dichiara_con_la_sua_entita() -> None:
    # back 10 @2.0 e lay 10.05 @2.0: se vince -0.05, se perde +0.05 -> 0.10
    fw = _fw(_ordine("BACK", 10.0, 2.0), _ordine("LAY", 10.05, 2.0))
    assert SS.residuo_netto(fw) == 0.10
    msg = SS.dichiarazione_stop_non_flat(fw)
    assert msg == ("non_flat_dopo_30s: residuo 0.10 EUR (micro-residuo accettato <= 0.30), "
                   "ordini vivi 0")


def test_residuo_vero_e_ordini_vivi() -> None:
    fw = _fw(_ordine("BACK", 10.0, 2.0), _ordine("LAY", 0.0, 2.0, st="EXECUTABLE"))
    assert SS.dichiarazione_stop_non_flat(fw) == \
        "non_flat_dopo_30s: residuo 20.00 EUR, ordini vivi 1"


def test_blotter_illeggibile_non_e_mai_zero() -> None:
    class _Rotto:
        @property
        def markets(self) -> Any:
            raise RuntimeError("mutato")
    assert SS.residuo_netto(_Rotto()) is None
    assert SS.dichiarazione_stop_non_flat(_Rotto()) == (
        "non_flat_dopo_30s: residuo non leggibile (blotter), ordini vivi non leggibili")


def test_stato_finale_dichiara_non_flat_e_freno() -> None:
    msg = "non_flat_dopo_30s: residuo 0.10 EUR (micro-residuo accettato <= 0.30), ordini vivi 0"
    out = SS.dichiara_stato_finale({"pnl_locked": 0.4}, msg, FRENO)
    assert out == {"pnl_locked": 0.4, "posizione_non_flat": msg, "fermata_dal_freno": FRENO}
    # la dichiarazione D7 (residuo > 0.30) gia' scritta non si sovrascrive
    d7 = {"posizione_non_flat": "posizione NON flat a fine sessione: 1.200/47972 ..."}
    assert SS.dichiara_stato_finale(d7, msg, None)["posizione_non_flat"] == \
        d7["posizione_non_flat"]
    # niente da dichiarare: le stats restano le stesse (stesso oggetto)
    s = {"pnl_locked": 0.0}
    assert SS.dichiara_stato_finale(s, None, None) is s
    assert SS.dichiara_stato_finale(None, None, FRENO) == {"fermata_dal_freno": FRENO}


def test_la_sessione_scrive_error_e_stats_nella_riga_finale() -> None:
    """Il ciclo di ``run_session`` (login + flumine) non si esegue qui: si
    verifica che i due rami 'NON flat dopo 30s' registrino la dichiarazione e
    che la scrittura finale la porti in ``error`` e ``stats`` (il replay del
    banco, ``certifica scalper``, esercita il ciclo vero)."""
    src = inspect.getsource(SS.run_session)
    assert src.count("non_flat_30s = dichiarazione_stop_non_flat(framework)") == 2
    fin = src[src.index("_final_stats = dichiara_stato_finale("):]
    assert "[non_flat_30s] if non_flat_30s else []" in fin
    assert 'error=("; ".join(_errori) or None)' in fin
    assert "fermata_freno = freno" in src
