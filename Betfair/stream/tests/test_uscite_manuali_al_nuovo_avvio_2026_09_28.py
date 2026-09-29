"""CANTIERE N (28/09/2026) - a ogni AVVIO NUOVO dell'app le uscite tornano MANUALI.

Ordine dell'utente (28/09, testuale): "OGNI BOT, PER ORA, DEVE PASSARE DA ME, IO
APPROVO LE USCITE; QUANDO MI FIDERO', LI LASCERO' LAVORARE IN AUTOMATICO". Il
brief: MANUALE e' la posizione di serie "anche dopo ogni riavvio dell'app".

Prima di oggi ``avvio_app.ferma_al_nuovo_avvio`` riportava a ``stopped``/``paper``
ma lasciava l'interruttore delle uscite com'era: un bot messo in AUTOMATICO ieri
sera ripartiva, alla prima accensione di oggi, con le uscite automatiche.

Qui si certifica il MECCANISMO condiviso (``uscite_a_manuali`` e il parametro
``uscite_bot`` di ``ferma_al_nuovo_avvio``). I servizi (Mike, Omega, Safe, scalper,
tennis) hanno i loro test nei rispettivi file ``*_uscite_manuali_al_riavvio``.

Le righe sono costruite dalle COLONNE VERE delle migrazioni (``riga_control``).
File ASCII-only.
"""
from __future__ import annotations

from typing import Any

import pytest

from Betfair.stream import avvio_app as AA
from Betfair.stream.tests.test_avvio_app_2026_09_16 import riga_control

NOW = "2026-09-28T12:00:00+00:00"


class _Scrittore:
    def __init__(self, riga: dict[str, Any]) -> None:
        self.riga = riga
        self.scritture: list[dict[str, Any]] = []
        self.log: list[tuple[str, dict[str, Any]]] = []

    def set_control(self, **campi: Any) -> None:
        self.scritture.append(dict(campi))
        self.riga.update(campi)

    def attivita(self, kind: str, payload: dict[str, Any]) -> None:
        self.log.append((kind, payload))


# ---------------------------------------------------------------------------
# la funzione pura: bot per bot, la chiave VERA che il servizio legge
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bot,params,atteso", [
    ("mike", {"uscite_automatiche": True, "stake": 5},
     {"uscite_automatiche": False, "stake": 5}),
    ("scalper", {"uscite_automatiche": True, "tetto": 3},
     {"uscite_automatiche": False, "tetto": 3}),
    ("omega", {"uscite_protezione": "automatico", "k": 1},
     {"uscite_protezione": "avvisa_e_proponi", "k": 1}),
])
def test_riporta_a_manuali_la_chiave_del_bot(bot, params, atteso):
    nuovi = AA.uscite_a_manuali(bot, params)
    assert nuovi == atteso
    # non muta l'oggetto ricevuto (i params letti dal DB restano quelli)
    assert params != atteso


def test_safe_tutte_le_strategie_e_il_cancelletto_del_tennis():
    params = {"uscite_automatiche": {"base": True, "tennis": True, "esatto": False},
              "tennis_exit_approval": False, "strategy_modes": {"base": "paper"}}
    nuovi = AA.uscite_a_manuali("safe", params)
    assert nuovi["uscite_automatiche"] == {s: False for s in AA.STRATEGIE_SAFE_CON_USCITE}
    assert nuovi["tennis_exit_approval"] is True
    assert nuovi["strategy_modes"] == {"base": "paper"}


def test_le_strategie_di_safe_sono_quelle_del_servizio():
    """Contratto: l'elenco qui (avvio_app non puo' importare Safe) e' lo stesso
    del servizio. Se Safe aggiunge una strategia con uscite, questo diventa rosso."""
    from Betfair.safe_strategy import bot_service as BS
    assert tuple(sorted(AA.STRATEGIE_SAFE_CON_USCITE)) == tuple(sorted(BS.STRATEGIE_CON_USCITE))


@pytest.mark.parametrize("bot,params", [
    ("mike", {"uscite_automatiche": False}),
    ("mike", {"stake": 5}),                      # assente = manuale di serie
    ("omega", {"uscite_protezione": "avvisa_e_proponi"}),
    ("omega", {}),
    ("scalper", {"uscite_automatiche": False}),
    ("safe", {"uscite_automatiche": {s: False for s in ("base", "esatto", "punta", "tennis", "model")},
              "tennis_exit_approval": True}),
    ("safe", {}),
])
def test_gia_manuali_niente_da_scrivere(bot, params):
    assert AA.uscite_a_manuali(bot, params) is None


@pytest.mark.parametrize("bot,params", [
    ("mike", {"uscite_automatiche": "true"}),     # stringa vera = automatiche per _coerce
    ("mike", {"uscite_automatiche": 1}),
    ("safe", {"tennis_exit_approval": False}),    # tennis automatico dal cancelletto storico
    ("omega", {"uscite_protezione": " Automatico "}),
])
def test_ogni_forma_di_automatico_torna_manuale(bot, params):
    assert AA.uscite_a_manuali(bot, params) is not None


def test_bot_sconosciuto_non_tocca_niente():
    assert AA.uscite_a_manuali("chissa", {"uscite_automatiche": True}) is None
    assert AA.uscite_a_manuali("mike", None) is None


# ---------------------------------------------------------------------------
# ferma_al_nuovo_avvio con ``uscite_bot``
# ---------------------------------------------------------------------------
def test_avvio_nuovo_riporta_le_uscite_a_manuali():
    g = AA.Guardia("mike")
    riga = riga_control("mike_control", id=1, status="running", mode="paper",
                        params={"uscite_automatiche": True, "stake": 5},
                        stats={"boot_id": "IERI"})
    w = _Scrittore(riga)
    esito = AA.ferma_al_nuovo_avvio(g, control=riga, set_control=w.set_control,
                                    log=w.attivita, now_iso=NOW, boot_id="OGGI",
                                    uscite_bot="mike")
    assert riga["params"] == {"uscite_automatiche": False, "stake": 5}
    assert esito["uscite_riportate_a_manuali"] is True
    assert w.log and w.log[0][1]["uscite_riportate_a_manuali"] is True


def test_bot_gia_fermo_in_prova_ma_in_automatico_torna_manuale_senza_cartello():
    """Il bot era gia' fermo in prova: non e' stato "fermato all'avvio" (niente
    cartello in Control Room), ma le uscite tornano MANUALI e l'attivita' lo dice."""
    g = AA.Guardia("mike")
    riga = riga_control("mike_control", id=1, status="stopped", mode="paper",
                        params={"uscite_automatiche": True}, stats={"boot_id": "IERI"})
    w = _Scrittore(riga)
    esito = AA.ferma_al_nuovo_avvio(g, control=riga, set_control=w.set_control,
                                    log=w.attivita, now_iso=NOW, boot_id="OGGI",
                                    uscite_bot="mike")
    assert riga["params"]["uscite_automatiche"] is False
    assert esito["azzerato"] is False
    assert "fermato_all_avvio_at" not in riga["stats"]
    assert [k for k, _ in w.log] == [AA.KIND_ATTIVITA]


def test_stesso_avvio_non_tocca_le_uscite():
    """Riavvio dal watchdog (stesso APP_BOOT_ID): l'utente ha scelto AUTOMATICO
    in QUESTO avvio e un crash del processo non glielo toglie."""
    g = AA.Guardia("mike")
    riga = riga_control("mike_control", id=1, status="running", mode="paper",
                        params={"uscite_automatiche": True}, stats={"boot_id": "OGGI"})
    w = _Scrittore(riga)
    assert AA.ferma_al_nuovo_avvio(g, control=riga, set_control=w.set_control,
                                   log=w.attivita, now_iso=NOW, boot_id="OGGI",
                                   uscite_bot="mike") is None
    assert w.scritture == [] and riga["params"]["uscite_automatiche"] is True


def test_safe_si_compone_con_il_reset_delle_modalita():
    """Safe passa gia' ``params_reset`` (strategy_modes a paper): le uscite si
    applicano SOPRA quel risultato, nessuna delle due modifiche si perde."""
    g = AA.Guardia("safe")
    riga = riga_control("safe_strategy_control", id=1, status="running", mode="live",
                        params={"strategy_modes": {"tennis": "live"},
                                "uscite_automatiche": {"tennis": True},
                                "tennis_exit_approval": False},
                        stats={"boot_id": "IERI"})
    w = _Scrittore(riga)

    def _modi(p: Any):
        q = dict(p)
        q["strategy_modes"] = {k: "paper" for k in (p.get("strategy_modes") or {})}
        return q, ["tennis"]

    AA.ferma_al_nuovo_avvio(g, control=riga, set_control=w.set_control, log=w.attivita,
                            now_iso=NOW, boot_id="OGGI", params_reset=_modi,
                            uscite_bot="safe")
    assert riga["params"]["strategy_modes"] == {"tennis": "paper"}
    assert riga["params"]["uscite_automatiche"]["tennis"] is False
    assert riga["params"]["tennis_exit_approval"] is True


def test_senza_uscite_bot_il_comportamento_di_prima():
    """Chi non passa ``uscite_bot`` (codice non ancora aggiornato) non cambia:
    solo stato e modalita', params identici."""
    g = AA.Guardia("x")
    riga = riga_control("mike_control", id=1, status="running", mode="live",
                        params={"uscite_automatiche": True}, stats={"boot_id": "IERI"})
    w = _Scrittore(riga)
    AA.ferma_al_nuovo_avvio(g, control=riga, set_control=w.set_control,
                            log=w.attivita, now_iso=NOW, boot_id="OGGI")
    assert "params" not in w.scritture[0]
