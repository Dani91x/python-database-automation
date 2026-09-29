"""CANTIERE N3 (28/09) - il banco dei bot di flusso DICHIARA l'interruttore
delle uscite.

Dopo il cantiere N ogni bot nasce a uscite MANUALI. Gli scenari che
esistevano prima (tennis: base, live, gate-aperto, parziali, ...; scalper
calcio: base, paper, sniper, ...) girano con le uscite AUTOMATICHE accese e
lo scrivono nel referto; gli scenari a uscite manuali sono elencati a parte.

Questi test non lanciano replay: fermano `certifica_scenario` subito dopo
l'istanza VERA del bot (`tennis_runner._instantiate_bot`) o subito dopo il
control della UI (scalper) e leggono cio' che il banco ha scritto.
"""
from __future__ import annotations

import json

import pytest

from Betfair.stream.scalper.tools import replay_registrazioni as RR
from Betfair.stream.tennis_live.tools import replay_bot as RB

BOT_TENNIS = ("tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing")
SCENARI_TENNIS_ESISTENTI = ("base", "gate-aperto", "live", "parziali", "dry-run",
                            "chiudi-ora")


class _Fermati(Exception):
    """Ferma il replay: il resto non serve al test."""


def _raw_tennis(tmp_path, event_id: str = "900001") -> str:
    """Un raw con UN marketDefinition MATCH_ODDS (le chiavi del vero stream
    Betfair: `op`, `pt`, `mc[].id`, `marketDefinition.marketType/runners`)."""
    base = tmp_path / event_id
    base.mkdir()
    riga = {"op": "mcm", "pt": 1751900000000, "mc": [{
        "id": "1.555", "marketDefinition": {
            "marketType": "MATCH_ODDS", "inPlay": False, "status": "OPEN",
            "betDelay": 0, "marketTime": "2026-07-07T12:00:00.000Z",
            "runners": [{"id": 11, "sortPriority": 1, "status": "ACTIVE"},
                        {"id": 22, "sortPriority": 2, "status": "ACTIVE"}]}}]}
    (base / ("%s.raw.jsonl" % event_id)).write_text(json.dumps(riga) + "\n",
                                                    encoding="utf-8")
    return str(tmp_path)


# ---------------------------------------------------------------------------
# tennis
# ---------------------------------------------------------------------------
def test_tennis_scenari_esistenti_tutti_automatici_e_i_manuali_a_parte():
    esistenti = [s for s in RB.SCENARI_DESCRITTI if s not in RB.SCENARI_USCITE_MANUALI]
    assert set(SCENARI_TENNIS_ESISTENTI) <= set(esistenti)
    for s in esistenti:
        assert RB.uscite_automatiche_scenario(s) is True, s
    for s in RB.SCENARI_USCITE_MANUALI:
        assert s in RB.SCENARI_DESCRITTI, s
        assert RB.uscite_automatiche_scenario(s) is False, s


@pytest.mark.parametrize("bot", BOT_TENNIS)
@pytest.mark.parametrize("scenario", SCENARI_TENNIS_ESISTENTI)
def test_tennis_la_riga_porta_le_uscite_accese_e_il_bot_vero_le_legge(
        monkeypatch, tmp_path, bot, scenario):
    import flumine

    from Betfair.stream.tennis_live import tennis_runner as TR

    vero = TR._instantiate_bot
    visto = {}

    def _spia(bot_key, control, *a, **k):
        strat = vero(bot_key, control, *a, **k)
        visto["control"] = dict(control)
        visto["effettive"] = getattr(strat, "uscite_automatiche", None)
        return strat

    class _QuadroFermo:
        def __init__(self, *a, **k):
            raise _Fermati()

    monkeypatch.setattr(TR, "_instantiate_bot", _spia)
    monkeypatch.setattr(flumine, "FlumineSimulation", _QuadroFermo)
    with pytest.raises(_Fermati):
        RB.certifica_scenario("900001", data_dir=_raw_tennis(tmp_path),
                              scenario=scenario, bot=bot)
    assert visto["control"]["uscite_automatiche"] is True
    assert visto["effettive"] is True


@pytest.mark.parametrize("bot", BOT_TENNIS)
def test_tennis_referto_dichiara_lo_scenario(monkeypatch, tmp_path, bot):
    """Il bot che non si istanzia chiude il referto: la nota dichiarata deve
    esserci gia' (e' scritta PRIMA dell'istanza)."""
    from Betfair.stream.tennis_live import tennis_runner as TR

    def _rotto(*a, **k):
        raise RuntimeError("istanza rifiutata dal test")

    monkeypatch.setattr(TR, "_instantiate_bot", _rotto)
    ref = RB.certifica_scenario("900001", data_dir=_raw_tennis(tmp_path),
                                scenario="gate-aperto", bot=bot)
    assert RB.NOTA_USCITE_AUTO in ref.note
    assert RB.NOTA_USCITE_AUTO.startswith(
        "SCENARIO DICHIARATO: uscite automatiche accese, e' la condotta certificata")


# ---------------------------------------------------------------------------
# scalper calcio (maker + sniper)
# ---------------------------------------------------------------------------
def test_scalper_scenari_esistenti_tutti_automatici_e_i_manuali_a_parte():
    esistenti = [s for s in RR.SCENARI_DESCRITTI if s not in RR.SCENARI_USCITE_MANUALI]
    assert {"base", "paper", "senza-missione", "sniper", "sniper-paper",
            "sniper-uscite-auto"} <= set(esistenti)
    for s in esistenti:
        c = RR.control_della_ui("1", s)
        assert c["params"]["uscite_automatiche"] is True, s
    for s in RR.SCENARI_USCITE_MANUALI:
        assert s in RR.SCENARI_DESCRITTI, s
        c = RR.control_della_ui("1", s)
        assert c["params"]["uscite_automatiche"] is False, s
        assert c["params"]["sniper_mode"] is True, s


def _raw_calcio(tmp_path, event_id: str = "77") -> str:
    base = tmp_path / event_id
    base.mkdir()
    riga = {"op": "mcm", "pt": 1751900000000, "mc": [{
        "id": "1.9", "marketDefinition": {
            "marketType": "MATCH_ODDS", "inPlay": False, "status": "OPEN",
            "betDelay": 0, "marketTime": "2026-07-07T19:00:00.000Z",
            "runners": [{"id": 1, "sortPriority": 1, "status": "ACTIVE"},
                        {"id": 2, "sortPriority": 2, "status": "ACTIVE"},
                        {"id": 3, "sortPriority": 3, "status": "ACTIVE"}]}}]}
    (base / ("%s.raw.jsonl" % event_id)).write_text(json.dumps(riga) + "\n",
                                                    encoding="utf-8")
    return str(tmp_path)


@pytest.mark.parametrize("scenario", ["base", "paper", "sniper", "sniper-paper"])
def test_scalper_referto_dichiara_lo_scenario(monkeypatch, tmp_path, scenario):
    visto = {}

    def _db_fermo(orologio, control, follow):
        visto["control"] = control
        raise _Fermati()

    monkeypatch.setattr(RR, "_DbFinto", _db_fermo)
    from Betfair.stream.scalper import certificazione as CERT

    creati = []
    vero = CERT.Referto

    def _referto(*a, **k):
        r = vero(*a, **k)
        creati.append(r)
        return r

    monkeypatch.setattr(CERT, "Referto", _referto)
    with pytest.raises(_Fermati):
        RR.certifica_scenario("77", data_dir=_raw_calcio(tmp_path), scenario=scenario)
    assert visto["control"]["params"]["uscite_automatiche"] is True
    assert RR.NOTA_USCITE_AUTO in creati[-1].note
    assert RR.NOTA_USCITE_AUTO.startswith(
        "SCENARIO DICHIARATO: uscite automatiche accese, e' la condotta certificata")
