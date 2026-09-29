# -*- coding: utf-8 -*-
"""CANTIERE V2 (29/09) - replay di certificazione VELOCI e lo STANDARD DEI TEMPI.

Ordine dell'utente del 29/09: "voglio i replay estremamente rapidi per ogni
bot, devi renderlo uno standard". Qui si prova lo standard:

   IL BANCO COMUNE (`certifica.py`) stampa il tempo di OGNI scenario (con i
   tick al secondo) su una riga PROPRIA, il tempo TOTALE in coda e, SOLO sopra
   il tetto (10 minuti, `CERTIFICA_TETTO_S`), una riga `LENTO:` con lo scenario
   piu' caro. E' un avviso: esito OK/KO ed exit code NON cambiano, e tolte le
   righe dei tempi il referto e' identico riga per riga.
   Si chiama `certifica.main()` PER DAVVERO, col registro vero e il `_lavora`
   vero; si cambia solo la funzione di replay della scheda (come in
   `test_certifica_replay_esploso_2026_09_23.py`) e l'OROLOGIO (`time` del
   modulo), cosi' le durate sono decise dal test e non dalla macchina.
   Referto e Violazione sono quelli VERI di `certificazione_tennis`.
"""
from __future__ import annotations

import dataclasses

import pytest

from Betfair.safe_strategy.certificazione_tennis import Referto, Violazione
from Betfair.stream.backtest import certifica
from Betfair.stream.backtest import registro_bot as REG

EVENTO = "999999"
SCENARI = "base,paper"


class _Orologio:
    """Il `time` del modulo `certifica`, con un `perf_counter` deciso dal test."""

    def __init__(self) -> None:
        self.adesso = 1000.0

    def perf_counter(self) -> float:
        return self.adesso


_OROLOGIO = _Orologio()
#: quanti secondi "dura" ogni scenario (lo decide il test)
_DURATE = {"base": 100.0, "paper": 120.0}
#: il replay produce violazioni? (per l'esito KO)
_CON_VIOLAZIONE = {"si": False}


def _replay_cronometrato(event_id, *, data_dir, scenario="base", ogni_ms=0,
                         campioni_diff=0):
    _OROLOGIO.adesso += _DURATE.get(scenario, 0.0)
    r = Referto(event_id=str(event_id))
    r.tick = 1200
    r.decisioni = 7
    r.note.append(f"nota fissa dello scenario {scenario}")
    if _CON_VIOLAZIONE["si"]:
        r.violazioni.append(Violazione("K1", "regola di prova", "dettaglio di prova"))
    return r


@pytest.fixture
def banco(monkeypatch):
    vera = REG.bot("safe_tennis")
    finta = dataclasses.replace(vera, replay=f"{__name__}:_replay_cronometrato")

    def _bot(nome):
        return finta if str(nome) == "safe_tennis" else vera

    monkeypatch.setattr(certifica.REG, "bot", _bot)
    monkeypatch.setattr(certifica, "time", _OROLOGIO)
    monkeypatch.delenv(certifica.ENV_TETTO_CERTIFICAZIONE, raising=False)
    _DURATE.clear()
    _DURATE.update({"base": 100.0, "paper": 120.0})
    _CON_VIOLAZIONE["si"] = False
    return monkeypatch


def _certifica(capsys, tmp_path):
    esito = certifica.main(["safe_tennis", EVENTO, "--data-dir", str(tmp_path),
                            "--worker", "1", "--scenari", SCENARI])
    return esito, capsys.readouterr().out


def _righe(out, prefisso):
    return [r for r in out.splitlines() if r.lstrip().startswith(prefisso)]


# ---------------------------------------------------------------------------
# 1. i tempi nel referto
# ---------------------------------------------------------------------------
def test_ogni_scenario_ha_la_sua_riga_del_tempo_con_i_tick_al_secondo(banco, capsys,
                                                                    tmp_path):
    esito, out = _certifica(capsys, tmp_path)
    assert esito == 0, out
    tempi = _righe(out, "tempo:")
    assert len(tempi) == 2, out
    assert "[base]" in tempi[0] and "(100.0 s)" in tempi[0] and "12 tick/s" in tempi[0]
    assert "[paper]" in tempi[1] and "(120.0 s)" in tempi[1] and "10 tick/s" in tempi[1]
    # riga PROPRIA: nient'altro sulla riga del tempo, e la riga del tempo viene
    # DOPO le righe dello scenario (esito, note)
    righe = out.splitlines()
    i_ok = next(i for i, r in enumerate(righe) if "[base]" in r and r.startswith("OK"))
    i_t = righe.index(tempi[0])
    assert i_t > i_ok
    assert "nota fissa dello scenario base" in righe[i_t - 1]
    assert "OK" not in tempi[0] and "nota" not in tempi[0]


def test_il_totale_sta_in_coda_e_sotto_il_tetto_non_ce_lento(banco, capsys, tmp_path):
    esito, out = _certifica(capsys, tmp_path)
    assert esito == 0
    tot = _righe(out, "TEMPO TOTALE:")
    assert len(tot) == 1, out
    assert "(220.0 s)" in tot[0] and "tetto 600 s" in tot[0]
    assert not _righe(out, "LENTO:"), out
    assert "LENTO" not in out
    # in CODA: dopo la copertura dei controlli
    assert out.index("TEMPO TOTALE:") > out.index("COPERTURA DEI CONTROLLI")


def test_sopra_il_tetto_la_riga_lento_nomina_lo_scenario_piu_caro(banco, capsys, tmp_path):
    _DURATE.update({"base": 250.0, "paper": 400.0})
    esito, out = _certifica(capsys, tmp_path)
    lento = _righe(out, "LENTO:")
    assert len(lento) == 1, out
    assert "(650.0 s)" in lento[0]
    assert "[paper]" in lento[0] and "(400.0 s)" in lento[0]
    assert "[base]" not in lento[0]
    assert esito == 0, "LENTO e' un avviso: l'exit code resta quello dell'esito"
    assert "2 partite senza violazioni" in out


def test_al_tetto_esatto_non_ce_lento(banco, capsys, tmp_path):
    _DURATE.update({"base": 300.0, "paper": 300.0})
    _esito, out = _certifica(capsys, tmp_path)
    assert not _righe(out, "LENTO:"), out


def test_il_tetto_si_sposta_dalla_variabile_d_ambiente(banco, capsys, tmp_path):
    banco.setenv(certifica.ENV_TETTO_CERTIFICAZIONE, "200")
    _esito, out = _certifica(capsys, tmp_path)
    assert len(_righe(out, "LENTO:")) == 1, out
    assert "tetto 200 s" in _righe(out, "TEMPO TOTALE:")[0]


@pytest.mark.parametrize("grezzo", ["", "abc", "0", "-5"])
def test_un_tetto_illeggibile_vale_il_default(monkeypatch, grezzo):
    monkeypatch.setenv(certifica.ENV_TETTO_CERTIFICAZIONE, grezzo)
    assert certifica.tetto_certificazione_s() == certifica.TETTO_CERTIFICAZIONE_S == 600.0


def test_lento_non_cambia_l_esito_ko_ne_l_exit_code(banco, capsys, tmp_path):
    _CON_VIOLAZIONE["si"] = True
    esito_veloce, out_veloce = _certifica(capsys, tmp_path)
    _DURATE.update({"base": 500.0, "paper": 500.0})
    esito_lento, out_lento = _certifica(capsys, tmp_path)
    assert esito_veloce == esito_lento == 1
    assert "2 violazioni totali" in out_veloce and "2 violazioni totali" in out_lento
    assert _righe(out_lento, "LENTO:") and not _righe(out_veloce, "LENTO:")


def test_tolte_le_righe_dei_tempi_il_referto_e_identico(banco, capsys, tmp_path):
    _esito, veloce = _certifica(capsys, tmp_path)
    _DURATE.update({"base": 700.0, "paper": 9.0})
    _esito, lento = _certifica(capsys, tmp_path)
    assert veloce != lento
    assert certifica.righe_senza_tempi(veloce) == certifica.righe_senza_tempi(lento)
    # e le righe tolte sono SOLO quelle dei tempi (2 scenari + totale [+ LENTO])
    assert len(veloce.splitlines()) - len(certifica.righe_senza_tempi(veloce)) == 3
    assert len(lento.splitlines()) - len(certifica.righe_senza_tempi(lento)) == 4


def test_il_cronometro_viaggia_a_parte_e_lavora_non_cambia_firma(banco):
    """`_lavora` torna ancora (referto, memoria): la usano `trasporto_rapido` e
    i test con ``r, _mem = _lavora(...)``; il tempo lo aggiunge il guscio."""
    compito = ("safe_tennis", EVENTO, "dir", "base", 0, 0)
    fuori = certifica._lavora(compito)
    assert len(fuori) == 2
    r, _mem, secondi = certifica._lavora_cronometrato(compito)
    assert secondi == 100.0
    assert r.tick == 1200


def test_il_comando_stampato_dice_il_trasporto(banco, capsys, tmp_path):
    """Par. 6.8: il referto del 29/09 di Mike (etichette `<canale>`) stampava un
    comando SENZA `--trasporto`: chi lo rifaceva otteneva un altro referto."""
    esito = certifica.main(["safe_tennis", EVENTO, "--data-dir", str(tmp_path),
                            "--worker", "1", "--scenari", "base", "--trasporto", "coda"])
    out = capsys.readouterr().out
    comando = [r for r in out.splitlines() if r.startswith("comando:")]
    assert comando and comando[0].endswith("--scenari base --trasporto coda"), out
    assert esito == 0, out
    certifica.main(["safe_tennis", EVENTO, "--data-dir", str(tmp_path),
                    "--worker", "1", "--scenari", "base"])
    out = capsys.readouterr().out
    comando = [r for r in out.splitlines() if r.startswith("comando:")]
    assert comando[0].endswith("--scenari base"), out


def test_durata_leggibile():
    assert certifica.durata_leggibile(12.34) == "12.3s"
    assert certifica.durata_leggibile(83.4) == "1m23.4s"
    assert certifica.durata_leggibile(1355.8) == "22m35.8s"
    assert certifica.durata_leggibile(-1) == "0.0s"
