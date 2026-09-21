"""Ritentativi di fine shard in cloud_retrain_shard.py.

Nessun training, nessun DB, nessuna rete: retrain_all_leagues.py e' sostituito da
un finto processo che stampa le STESSE righe del vero (intestazione
"[i/N] League <id>", marcatore di successo "BSS comparison - league <id>:",
"Completato in Ns | K modelli", "[ERROR] league <id>:", riepilogo
"Leghe con errore (n):" e "Stop budget:") e ritorna lo stesso exit code.
Anche l'orologio e il pre-flight sul DB sono iniettati.

Si dimostra che: le leghe fallite vengono ritentate a fine shard; una lega e'
"recuperata" SOLO con prova positiva di completamento (una lega non avviata per
time-budget NON lo e'); l'exit code e' !=0 con elenco e causa se resta qualcosa;
il budget e il tetto assoluto sono rispettati; il DB viene ricontrollato prima di
ogni giro; nel ritentativo non si passa mai --skip-existing.
"""
from __future__ import annotations

import os
import subprocess
import sys
import types
from typing import List, Tuple

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import cloud_retrain_shard as crs  # noqa: E402


# -- righe del vero retrain_all_leagues.py -----------------------------------

def righe_lega_ok(lid: int, idx: int = 1, tot: int = 1, modelli: int = 18) -> List[str]:
    return [
        f"[10:00:00] [{idx}/{tot}] League {lid}",
        f"[10:00:05]   BSS comparison \u2014 league {lid}:",
        "[10:00:05]     Target                         Prima BSS    Dopo BSS",
        f"[10:00:05]   \u2713 Completato in 12.0s | {modelli} modelli",
    ]


def righe_lega_errore(lid: int, idx: int = 1, tot: int = 1) -> List[str]:
    return [
        f"[10:00:00] [{idx}/{tot}] League {lid}",
        f"[10:00:01]   [ERROR] league {lid}: "
        "{'message': 'canceling statement due to statement timeout', 'code': '57014'}",
    ]


def riepilogo(ok: List[int], errori: List[int], stop_budget: int = 0,
              errori_multiriga: bool = False, senza_marcatore_bss: bool = False) -> List[str]:
    """Output completo di retrain_all_leagues.py, nello stesso formato del vero."""
    tot = len(ok) + len(errori) + stop_budget
    righe: List[str] = ["=" * 70, "  RETRAIN ALL LEAGUES - Betfair ML System", "=" * 70]
    i = 0
    for lid in ok:
        i += 1
        if senza_marcatore_bss:
            # la lega e' passata ma il marcatore per-lega non c'e' (formato cambiato)
            righe += [f"[10:00:00] [{i}/{tot}] League {lid}",
                      "[10:00:05]   \u2713 Completato in 12.0s | 18 modelli"]
        else:
            righe += righe_lega_ok(lid, i, tot)
    for lid in errori:
        i += 1
        righe += righe_lega_errore(lid, i, tot)
    righe += [
        "",
        "=" * 70,
        "  RIEPILOGO FINALE",
        "=" * 70,
        f"  Leghe totali:     {tot}",
        f"  \u2713 OK:             {len(ok)}",
        "  \u27f3 Saltate:        0",
        f"  \u23f3 Stop budget:    {stop_budget} (non avviate, riprese al prossimo run)",
        f"  \u2717 Errori:         {len(errori)}",
    ]
    if errori:
        righe.append(f"  Leghe con errore ({len(errori)}):")
        for k, lid in enumerate(errori):
            righe.append(f"    - League {lid}: canceling statement due to statement timeout")
            if errori_multiriga and k == 0:
                righe += [
                    "Traceback (most recent call last):",
                    '  File "retrain_all_leagues.py", line 220, in retrain_league',
                    "ValueError: dataset vuoto",
                ]
    righe.append("  Log salvato in: retrain_log_20260921_100000.txt")
    righe.append("  NOTA: Dopo il retraining, lancia 'aggiorna_report.bat' normalmente.")
    return righe


def riepilogo_solo_blocco_errori(errori: List[int], multiriga: bool = True) -> List[str]:
    """Solo il riepilogo finale: niente marcatori "[ERROR] league" in linea.

    Serve a provare il parser del blocco, non quello delle righe per-lega.
    """
    righe = ["  RIEPILOGO FINALE", f"  \u2717 Errori:         {len(errori)}",
             f"  Leghe con errore ({len(errori)}):"]
    for k, lid in enumerate(errori):
        righe.append(f"    - League {lid}: errore di lettura")
        if multiriga and k == 0:
            righe += ["Traceback (most recent call last):",
                      '  File "db_adapter.py", line 200, in _fetch_all',
                      "APIError: Error 57014:", "Message: canceling statement"]
    righe.append("  Log salvato in: retrain_log_20260921_100000.txt")
    return righe


# -- finti: processo, orologio, probe ----------------------------------------

class FintoProcesso:
    def __init__(self, righe: List[str], rc: int) -> None:
        self.stdout = iter([r + "\n" for r in righe])
        self._rc = rc

    def wait(self) -> int:
        return self._rc


class FintoPopen:
    """Sostituisce subprocess.Popen: registra i comandi e recita un copione.

    Ogni voce del copione e' (righe, exit_code) oppure (righe, exit_code, minuti):
    i minuti fanno avanzare l'orologio finto, come farebbe un training vero.
    """

    def __init__(self, copione: List[tuple], orologio: "FintoOrologio") -> None:
        self.copione = list(copione)
        self.orologio = orologio
        self.comandi: List[List[str]] = []

    def __call__(self, cmd, **kwargs):
        self.comandi.append(list(cmd))
        assert kwargs.get("cwd") == crs.ROOT
        if not self.copione:
            raise AssertionError("lanci di training piu' del previsto")
        voce = self.copione.pop(0)
        righe, rc = voce[0], voce[1]
        if len(voce) > 2:
            self.orologio.avanza_min(voce[2])
        return FintoProcesso(righe, rc)


class FintoOrologio:
    def __init__(self) -> None:
        self._t = 1_700_000_000.0

    def time(self) -> float:
        return self._t

    def sleep(self, secondi: float) -> None:
        self._t += secondi

    def avanza_min(self, minuti: float) -> None:
        self._t += minuti * 60.0


def leghe_del_comando(cmd: List[str]) -> List[int]:
    i = cmd.index("--leagues")
    return [int(x) for x in cmd[i + 1].split(",") if x]


def budget_del_comando(cmd: List[str]) -> float:
    i = cmd.index("--time-budget-min")
    return float(cmd[i + 1])


def esegui(monkeypatch, copione, argv_extra=None, probe_lenta: bool = False,
           leagues: str = "71,141,239") -> Tuple[int, FintoPopen]:
    orologio = FintoOrologio()
    finto = FintoPopen(copione, orologio)
    # Si inietta un attributo sul MODULO DI PRODUZIONE: nessun modulo della
    # libreria standard viene mutato.
    monkeypatch.setattr(crs, "subprocess", types.SimpleNamespace(
        Popen=finto, PIPE=subprocess.PIPE, STDOUT=subprocess.STDOUT))
    monkeypatch.setattr(crs, "time", orologio)
    monkeypatch.setattr(crs, "_db_probe_lenta", lambda *a, **k: probe_lenta)
    argv = [
        "cloud_retrain_shard.py",
        "--shard-index", "0",
        "--total-shards", "1",
        "--leagues", leagues,
        "--time-budget-min", "240",
        "--parallel-leagues", "1",
        "--last-n-seasons", "20",
    ] + list(argv_extra or [])
    monkeypatch.setattr(sys, "argv", argv)
    return crs.main(), finto


# -- test --------------------------------------------------------------------

def test_nessun_errore_un_solo_lancio(monkeypatch):
    rc, finto = esegui(monkeypatch, [(riepilogo(ok=[71, 141, 239], errori=[]), 0)])
    assert rc == 0
    assert len(finto.comandi) == 1
    assert leghe_del_comando(finto.comandi[0]) == [71, 141, 239]


def test_leghe_fallite_ritentate_e_completate(monkeypatch, capsys):
    copione = [
        (riepilogo(ok=[239], errori=[71, 141]), 1),   # primo giro: 2 fallite
        (riepilogo(ok=[71, 141], errori=[]), 0),      # ritentativo: completate
    ]
    rc, finto = esegui(monkeypatch, copione)
    out = capsys.readouterr().out
    assert rc == 0, "completate tutte: l'exit code deve tornare 0"
    assert len(finto.comandi) == 2
    assert leghe_del_comando(finto.comandi[1]) == [71, 141]
    assert "Recuperate al ritentativo 1: [71, 141]" in out


def test_lega_non_avviata_nel_ritentativo_non_e_recuperata(monkeypatch, capsys):
    """rc=0 e nessun errore, ma la lega non e' partita: NON e' un recupero."""
    copione = [
        (riepilogo(ok=[141, 239], errori=[71]), 1),
        (riepilogo(ok=[], errori=[], stop_budget=1), 0),   # 71 mai avviata
        (riepilogo(ok=[], errori=[], stop_budget=1), 0),
    ]
    rc, finto = esegui(monkeypatch, copione)
    out = capsys.readouterr().out
    assert rc == 1, "una lega mai avviata non puo' far uscire lo shard con 0"
    assert "Recuperate" not in out
    assert "NON completate dopo 2 ritentativi" in out
    assert "- League 71: non completata (non avviata o senza modelli)" in out


def test_mix_una_completata_una_no(monkeypatch, capsys):
    copione = [
        (riepilogo(ok=[239], errori=[71, 141]), 1),
        (riepilogo(ok=[71], errori=[], stop_budget=1), 0),  # 71 ok, 141 non avviata
        (riepilogo(ok=[], errori=[], stop_budget=1), 0),
    ]
    rc, _ = esegui(monkeypatch, copione)
    out = capsys.readouterr().out
    assert rc == 1
    assert "Recuperate al ritentativo 1: [71]" in out
    assert "- League 141: non completata (non avviata o senza modelli)" in out
    assert "- League 71:" not in out.split("NON completate")[-1]


def test_lega_sempre_fallita_esce_non_zero_con_causa(monkeypatch, capsys):
    copione = [
        (riepilogo(ok=[141, 239], errori=[71]), 1),
        (riepilogo(ok=[], errori=[71]), 1),
        (riepilogo(ok=[], errori=[71]), 1),
    ]
    rc, finto = esegui(monkeypatch, copione)
    out = capsys.readouterr().out
    assert rc == 1
    assert len(finto.comandi) == 3, "devono esserci 2 giri di ritentativo"
    assert "- League 71: errore nel training" in out


def test_ritentativo_senza_skip_existing(monkeypatch):
    """--skip-existing resta solo al primo giro: nel ritentativo mai."""
    copione = [
        (riepilogo(ok=[141, 239], errori=[71]), 1),
        (riepilogo(ok=[71], errori=[]), 0),
    ]
    rc, finto = esegui(monkeypatch, copione, argv_extra=["--use-planner", "false",
                                                         "--skip-existing", "true",
                                                         "--max-age-days", "7"])
    assert rc == 0
    assert "--skip-existing" in finto.comandi[0]
    assert "--skip-existing" not in finto.comandi[1]
    assert "--max-age-days" not in finto.comandi[1]


def test_ritentativo_dentro_il_budget_residuo(monkeypatch):
    copione = [
        (riepilogo(ok=[141, 239], errori=[71]), 1, 100.0),  # il primo giro dura 100 min
        (riepilogo(ok=[71], errori=[]), 0),
    ]
    rc, finto = esegui(monkeypatch, copione)
    assert rc == 0
    assert budget_del_comando(finto.comandi[0]) == 240.0
    secondo = budget_del_comando(finto.comandi[1])
    assert 130.0 <= secondo <= 140.0, f"budget residuo sbagliato: {secondo}"


def test_budget_esaurito_niente_ritentativo(monkeypatch, capsys):
    copione = [(riepilogo(ok=[141, 239], errori=[71]), 1, 239.5)]
    rc, finto = esegui(monkeypatch, copione)
    out = capsys.readouterr().out
    assert rc == 1
    assert len(finto.comandi) == 1
    assert "Time-budget esaurito" in out
    assert "- League 71: errore nel training" in out


def test_tetto_assoluto_anche_con_budget_illimitato(monkeypatch, capsys):
    """--time-budget-min 0 = illimitato, ma i ritentativi hanno un tetto."""
    copione = [(riepilogo(ok=[141, 239], errori=[71]), 1, 301.0)]
    rc, finto = esegui(monkeypatch, copione, argv_extra=["--time-budget-min", "0"])
    out = capsys.readouterr().out
    assert rc == 1
    assert len(finto.comandi) == 1
    assert "Tetto assoluto" in out


def test_db_lento_niente_ritentativo(monkeypatch, capsys):
    """Pre-flight come quello del workflow: se il DB e' lento non si insiste."""
    copione = [(riepilogo(ok=[141, 239], errori=[71]), 1)]
    rc, finto = esegui(monkeypatch, copione, probe_lenta=True)
    out = capsys.readouterr().out
    assert rc == 1
    assert len(finto.comandi) == 1
    assert "DB non pronto" in out


def test_uscita_sporca_senza_elenco_non_e_successo(monkeypatch):
    """Il figlio muore senza riepilogo: exit code preservato, niente ritentativi."""
    copione = [(["Traceback (most recent call last):", "MemoryError"], 2)]
    rc, finto = esegui(monkeypatch, copione)
    assert rc == 2
    assert len(finto.comandi) == 1


def test_ritentativo_che_muore_senza_elenco_lascia_la_lega_non_completata(monkeypatch, capsys):
    copione = [
        (riepilogo(ok=[141, 239], errori=[71]), 1),
        (["Traceback (most recent call last):", "MemoryError"], 2),
        (["Traceback (most recent call last):", "MemoryError"], 2),
    ]
    rc, _ = esegui(monkeypatch, copione)
    out = capsys.readouterr().out
    assert rc == 1
    assert "- League 71: non completata (non avviata o senza modelli)" in out


def test_errori_su_piu_righe_nel_riepilogo_sono_tutti_riconosciuti(monkeypatch, capsys):
    """Un errore multi-riga non deve far perdere le leghe elencate dopo."""
    copione = [
        (riepilogo_solo_blocco_errori([71, 141, 239]), 1),
        (riepilogo(ok=[71, 141, 239], errori=[]), 0),
    ]
    rc, finto = esegui(monkeypatch, copione)
    out = capsys.readouterr().out
    assert "Leghe fallite al primo giro (3): [71, 141, 239]" in out
    assert leghe_del_comando(finto.comandi[1]) == [71, 141, 239]
    assert rc == 0


def test_una_sola_lega_riconosciuta_anche_senza_marcatore_bss(monkeypatch, capsys):
    """Con una sola lega richiesta basta "Completato ... | K modelli"."""
    copione = [
        (riepilogo(ok=[141, 239], errori=[71]), 1),
        (riepilogo(ok=[71], errori=[], senza_marcatore_bss=True), 0),
    ]
    rc, _ = esegui(monkeypatch, copione)
    out = capsys.readouterr().out
    assert rc == 0
    assert "Recuperate al ritentativo 1: [71]" in out


def test_zero_modelli_non_e_completamento(monkeypatch, capsys):
    """"Completato ... | 0 modelli" senza BSS comparison non e' una prova."""
    copione = [
        (riepilogo(ok=[141, 239], errori=[71]), 1),
        ([
            "[10:00:00] [1/1] League 71",
            "[10:00:05]   [WARN] Nessun modello addestrato per league 71",
            "[10:00:05]   \u2713 Completato in 3.0s | 0 modelli",
            "  RIEPILOGO FINALE",
            "  \u2717 Errori:         0",
            "  Log salvato in: retrain_log.txt",
        ], 0),
        ([
            "[10:00:00] [1/1] League 71",
            "[10:00:05]   \u2713 Completato in 3.0s | 0 modelli",
        ], 0),
    ]
    rc, _ = esegui(monkeypatch, copione)
    out = capsys.readouterr().out
    assert rc == 1
    assert "- League 71: non completata (non avviata o senza modelli)" in out


def test_ritentativi_disattivabili(monkeypatch):
    copione = [(riepilogo(ok=[141, 239], errori=[71]), 1)]
    rc, finto = esegui(monkeypatch, copione, argv_extra=["--retry-failed-rounds", "0"])
    assert rc == 1
    assert len(finto.comandi) == 1
