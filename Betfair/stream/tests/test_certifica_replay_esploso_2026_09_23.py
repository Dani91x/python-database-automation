# -*- coding: utf-8 -*-
"""DIFETTO (23/09): `certifica.py` contava un replay ESPLOSO come «muto».

`_lavora` trasformava l'eccezione di un replay in un `Referto` VUOTO con una
nota: zero decisioni, zero violazioni -> `esito_del_banco` lo metteva fra le
partite «senza decisioni» e l'exit code restava 0. Lo stesso per il replay che
non legge nemmeno un tick (registrazione assente, `--data-dir` sbagliato:
NO_RAW e «OK» falso, lezione del 18/09 in CRONOSTORIA).

Qui si chiama `certifica.main()` PER DAVVERO, col registro vero e con
`_lavora` vero: si cambia solo la funzione di replay della scheda (un replay che
solleva, uno che non legge niente, uno muto ma vivo), e si guardano exit code,
riga ESITO e diario. Referto e Violazione sono quelli VERI del modulo di
controlli di `safe_tennis` (`certificazione_tennis`).
"""
from __future__ import annotations

import dataclasses
import os

from Betfair.safe_strategy.certificazione_tennis import Referto
from Betfair.stream.backtest import certifica
from Betfair.stream.backtest import registro_bot as REG

EVENTO = "999999"


def _replay_che_esplode(event_id, *, data_dir, scenario="base", ogni_ms=0, campioni_diff=0):
    raise RuntimeError("il replay si e' rotto a meta'")


def _replay_senza_registrazione(event_id, *, data_dir, scenario="base", ogni_ms=0,
                                campioni_diff=0):
    # e' ESATTAMENTE cio' che fanno i replay veri quando il raw non c'e'
    r = Referto(event_id=str(event_id))
    r.note.append(f"registrazione assente: {data_dir}/{event_id}/{event_id}.raw.jsonl")
    return r


def _replay_muto_ma_vivo(event_id, *, data_dir, scenario="base", ogni_ms=0,
                         campioni_diff=0):
    # ha letto la partita (tick), il bot non ha mai deciso: e' MUTO, non esploso
    r = Referto(event_id=str(event_id))
    r.tick = 1234
    return r


def _con_replay(monkeypatch, funzione):
    """La scheda VERA di safe_tennis, con la sola funzione di replay cambiata."""
    vera = REG.bot("safe_tennis")
    finta = dataclasses.replace(
        vera, replay=f"{__name__}:{funzione.__name__}")

    def _bot(nome):
        return finta if str(nome) == "safe_tennis" else vera

    monkeypatch.setattr(certifica.REG, "bot", _bot)


def test_un_replay_che_solleva_e_una_violazione_ed_esce_con_1(monkeypatch, capsys, tmp_path):
    _con_replay(monkeypatch, _replay_che_esplode)
    diario = tmp_path / "diario.txt"
    esito = certifica.main(["safe_tennis", EVENTO, "--data-dir", str(tmp_path),
                            "--diario", str(diario), "--worker", "1"])
    out = capsys.readouterr().out
    assert esito == 1, out
    assert "REPLAY ESPLOSI: 1" in out, out
    assert "1 violazioni totali" in out, out
    assert "BANCO-ESPLOSO" in out
    assert "RuntimeError" in out
    testo = diario.read_text(encoding="utf-8")
    assert testo.startswith("KO "), testo
    assert "BANCO-ESPLOSO" in testo


def test_una_registrazione_mai_letta_e_una_violazione_ed_esce_con_1(monkeypatch, capsys,
                                                                     tmp_path):
    _con_replay(monkeypatch, _replay_senza_registrazione)
    esito = certifica.main(["safe_tennis", EVENTO, "--data-dir", str(tmp_path),
                            "--worker", "1"])
    out = capsys.readouterr().out
    assert esito == 1, out
    assert "REPLAY ESPLOSI: 1" in out
    assert "NO_RAW" in out
    assert "0 senza decisioni" in out, "un replay esploso non e' muto"


def test_un_replay_muto_ma_vivo_resta_muto_ed_esce_con_0(monkeypatch, capsys, tmp_path):
    """La correzione non deve accusare chi ha letto la partita e non ha deciso:
    quello e' un bot muto, e resta «senza decisioni» con exit 0."""
    _con_replay(monkeypatch, _replay_muto_ma_vivo)
    esito = certifica.main(["safe_tennis", EVENTO, "--data-dir", str(tmp_path),
                            "--worker", "1"])
    out = capsys.readouterr().out
    assert esito == 0, out
    assert "REPLAY ESPLOSI" not in out
    assert "1 senza decisioni" in out


def test_la_diagnosi_e_la_segnatura_sono_una_volta_sola():
    from Betfair.safe_strategy import certificazione_tennis as CT

    r = Referto(event_id="x")
    r.note.append("replay fallito: KeyError: 'a' (in foo.py:3)")
    assert certifica.diagnosi_esplosione(r).startswith("replay fallito")
    certifica.segna_esplosione(r, CT)
    certifica.segna_esplosione(r, CT)
    assert [v.codice for v in r.violazioni] == [certifica.CODICE_ESPLOSO]
    tot, pulite, mute, codice = certifica.esito_del_banco([r])
    assert (tot, pulite, mute, codice) == (1, 0, 0, 1)
    assert os.path.basename(certifica.__file__) == "certifica.py"
