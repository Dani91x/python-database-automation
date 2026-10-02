# -*- coding: utf-8 -*-
"""Falsificazione dell'isolamento 2 (02/10): l14, load_dotenv a meta' test,
avviso di processo di Mike.

Lancio (dalla radice del repo, interprete del .venv):

    python AUDIT_2026-10-02/falsifica_test_isolamento_2.py [--ordini]

Ogni mutazione toglie UNA riga della correzione (sostituzione testuale
verificata: deve comparire esattamente una volta), pretende ROSSO sulla
combinazione che falliva, rimette il file (contenuto in memoria, sha256
verificato nel ``finally``) e pretende VERDE. Le sonde del ``.env`` sono un file
di test TEMPORANEO scritto qui e cancellato nel ``finally``: controllano solo se
la variabile e' presente/uguale a "0", MAI il suo valore.

``--ordini``: ``Betfair/safe_strategy/tests`` in ordine inverso e con 3 semi
(plugin ``ordine_test_plugin.py``). Referto: ``falsifica_test_isolamento_2_out.txt``.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
AUDIT = Path(__file__).resolve().parent
OUT = AUDIT / "falsifica_test_isolamento_2_out.txt"

CONFTEST = RADICE / "Betfair/conftest.py"
MIKE = RADICE / "Betfair/mike/tests/test_mike_legge_canale_2026_09_23.py"
CONFTEST_SAFE = RADICE / "Betfair/safe_strategy/tests/conftest.py"
SONDA = RADICE / "Betfair/stream/tests/test_zz_sonda_dotenv_isolamento_2.py"

L14 = ("Betfair/safe_strategy/tests/test_audit_2026_09_11.py"
       "::test_l14_ttl_della_cache_lambda")
GREENUP = "Betfair/omega/test_omega_greenup_2026_09_10.py"
MIKE_REL = "Betfair/mike/tests/test_mike_legge_canale_2026_09_23.py"
SONDA_REL = "Betfair/stream/tests/test_zz_sonda_dotenv_isolamento_2.py"

RIGA_LAMBDA = "        _cache.clear()\n"
RIGA_DOTENV = '    monkeypatch.setattr(_dotenv, "load_dotenv", _solo_con_percorso)\n'
BLOCCO_AGG = ("    _S._AGG_ULTIMO_BUONO.clear()\n    yield\n"
              "    _S._AGG_ULTIMO_BUONO.clear()\n")
AGG_STANTII = ("Betfair/safe_strategy/tests/test_cert_2026_09_13.py"
               "::test_aggregati_stantii_si_riusano_per_poco_invece_di_bloccare")
AGG_ILLEGGIBILI = ("Betfair/safe_strategy/tests/test_cert_2026_09_13.py"
                   "::test_aggregati_illeggibili_bloccano_i_nuovi_ingressi")
RIGA_MIKE = '    _FP._NON_NOTO_AVVISATO.discard("mike")\n'

TESTO_SONDA = '''"""SONDA TEMPORANEA di falsifica_test_isolamento_2.py: cancellata a fine corsa."""
import importlib
import os


def test_sonda_delenv_resta_assente(monkeypatch):
    # come i test "variabile assente": la si toglie, poi un import/reload a
    # meta' test di config_stream (load_dotenv a riga 17)
    from Betfair.stream import config_stream
    monkeypatch.delenv("SAFE_ORDINI_VIA_CANALE", raising=False)
    try:
        importlib.reload(config_stream)
        assert "SAFE_ORDINI_VIA_CANALE" not in os.environ, "riaccesa dal .env"
    finally:
        os.environ.pop("SAFE_ORDINI_VIA_CANALE", None)
        importlib.reload(config_stream)


def test_sonda_percorso_esplicito_usa_la_funzione_vera(tmp_path, monkeypatch):
    # la guardia neutralizza solo la ricerca automatica: un .env FINTO passato
    # col percorso si carica davvero (test_banco_ambiente_dichiarato_2026_10_02)
    from dotenv import load_dotenv
    finto = tmp_path / ".env"
    finto.write_text("ZZ_SONDA_ISOLAMENTO_2=1\\n", encoding="utf-8")
    monkeypatch.delenv("ZZ_SONDA_ISOLAMENTO_2", raising=False)
    load_dotenv(str(finto))
    assert os.environ.get("ZZ_SONDA_ISOLAMENTO_2") == "1"
    monkeypatch.delenv("ZZ_SONDA_ISOLAMENTO_2", raising=False)


def test_sonda_setenv_zero_resta_zero(monkeypatch):
    from Betfair.stream import config_stream
    monkeypatch.setenv("SAFE_ORDINI_VIA_CANALE", "0")
    importlib.reload(config_stream)
    assert os.environ.get("SAFE_ORDINI_VIA_CANALE") == "0"
'''

righe: list[str] = []


def scrivi(s: str) -> None:
    print(s, flush=True)
    righe.append(s)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pytest(*args: str, env_extra: dict | None = None) -> tuple[str, float]:
    env = dict(os.environ)
    env.update(env_extra or {})
    t0 = time.time()
    p = subprocess.run([sys.executable, "-m", "pytest", *args, "-q", "-p", "no:cacheprovider"],
                       cwd=RADICE, capture_output=True, text=True, env=env,
                       encoding="utf-8", errors="replace")
    dt = time.time() - t0
    ultime = [r for r in p.stdout.splitlines() if r.strip()]
    sommario = ultime[-1] if ultime else f"(nessun output, rc={p.returncode})"
    for f in [r for r in p.stdout.splitlines() if r.startswith("FAILED")][:10]:
        scrivi(f"        {f}")
    return sommario, dt


def esito(nome: str, atteso: str, args: tuple[str, ...], env_extra: dict | None = None) -> bool:
    sommario, dt = pytest(*args, env_extra=env_extra)
    rosso = bool(re.search(r"\b\d+ (failed|error)", sommario))
    ottenuto = "ROSSO" if rosso else "VERDE"
    ok = ottenuto == atteso
    scrivi(f"  [{'OK ' if ok else 'KO!'}] {nome}: atteso {atteso}, ottenuto {ottenuto} "
           f"-> {sommario} ({dt:.1f}s)")
    return ok


def muta(p: Path, riga: str, sostituto: str | None = None) -> None:
    testo = p.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in testo else "\n"
    cerca = riga.replace("\n", nl)
    assert testo.count(cerca) == 1, f"testo da mutare non unico in {p}: {riga!r}"
    if sostituto is None:
        rientro = riga[: len(riga) - len(riga.lstrip())]
        sostituto = f"{rientro}pass  # MUTAZIONE\n"
    p.write_bytes(testo.replace(cerca, sostituto.replace("\n", nl)).encode("utf-8"))


def main() -> int:
    ordini = "--ordini" in sys.argv
    orig_c, orig_m = CONFTEST.read_bytes(), MIKE.read_bytes()
    sha_c, sha_m = sha(CONFTEST), sha(MIKE)
    orig_s, sha_s = CONFTEST_SAFE.read_bytes(), sha(CONFTEST_SAFE)
    ok = True
    scrivi(f"falsifica_test_isolamento_2 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    scrivi(f"interprete: {sys.executable}")
    try:
        SONDA.write_text(TESTO_SONDA, encoding="utf-8")
        scrivi("\n== 0) CON LE CORREZIONI")
        ok &= esito("(c) greenup Omega poi l14", "VERDE", (GREENUP, L14))
        ok &= esito("(c) l14 da solo", "VERDE", (L14,))
        ok &= esito("(d) sonde .env (delenv resta assente / '0' resta '0')", "VERDE", (SONDA_REL,))
        ok &= esito("(e) file Mike legge_canale da solo", "VERDE", (MIKE_REL,))
        ok &= esito("(f) aggregati stantii poi illeggibili", "VERDE",
                    (AGG_STANTII, AGG_ILLEGGIBILI))

        scrivi("\n== 1) MUTAZIONE C: niente svuotamento di omega_service._LAMBDA_CACHE")
        muta(CONFTEST, RIGA_LAMBDA)
        ok &= esito("(c) greenup Omega poi l14", "ROSSO", (GREENUP, L14))
        ok &= esito("(c) l14 da solo", "VERDE", (L14,))
        CONFTEST.write_bytes(orig_c)

        scrivi("\n== 2) MUTAZIONE D: load_dotenv di nuovo attivo durante i test")
        muta(CONFTEST, RIGA_DOTENV)
        ok &= esito("(d) sonda delenv: riaccesa dal .env", "ROSSO",
                    (SONDA_REL + "::test_sonda_delenv_resta_assente",))
        ok &= esito("(d) sonda setenv '0': il criterio per sito regge anche senza guardia",
                    "VERDE", (SONDA_REL + "::test_sonda_setenv_zero_resta_zero",))
        CONFTEST.write_bytes(orig_c)

        scrivi("\n== 3) MUTAZIONE E: le due corse di Mike senza azzerare l'avviso di processo")
        muta(MIKE, RIGA_MIKE)
        ok &= esito("(e) file Mike legge_canale da solo", "ROSSO", (MIKE_REL,))
        MIKE.write_bytes(orig_m)

        scrivi("\n== 3b) MUTAZIONE F: _AGG_ULTIMO_BUONO non azzerato fra i test")
        muta(CONFTEST_SAFE, BLOCCO_AGG, "    yield\n")
        ok &= esito("(f) aggregati stantii poi illeggibili", "ROSSO",
                    (AGG_STANTII, AGG_ILLEGGIBILI))
        ok &= esito("(f) illeggibili da solo", "VERDE", (AGG_ILLEGGIBILI,))
        CONFTEST_SAFE.write_bytes(orig_s)

        scrivi("\n== 4) RIPRISTINATO")
        ok &= esito("(c) greenup Omega poi l14", "VERDE", (GREENUP, L14))
        ok &= esito("(d) sonde .env", "VERDE", (SONDA_REL,))
        ok &= esito("(e) file Mike legge_canale da solo", "VERDE", (MIKE_REL,))
        ok &= esito("(f) aggregati stantii poi illeggibili", "VERDE",
                    (AGG_STANTII, AGG_ILLEGGIBILI))
        SONDA.unlink()

        if ordini:
            scrivi("\n== 5) ORDINE: Betfair/safe_strategy/tests, inverso e 3 semi")
            pp = str(AUDIT) + os.pathsep + os.environ.get("PYTHONPATH", "")
            for modo in ("inverso", "casuale:11", "casuale:12", "casuale:13"):
                ok &= esito(f"ORDINE_TEST={modo}", "VERDE",
                            ("Betfair/safe_strategy/tests", "-p", "ordine_test_plugin"),
                            env_extra={"ORDINE_TEST": modo, "PYTHONPATH": pp})
    finally:
        CONFTEST.write_bytes(orig_c)
        MIKE.write_bytes(orig_m)
        CONFTEST_SAFE.write_bytes(orig_s)
        if SONDA.exists():
            SONDA.unlink()
        rip = sha(CONFTEST) == sha_c and sha(MIKE) == sha_m and sha(CONFTEST_SAFE) == sha_s \
            and not SONDA.exists()
        scrivi(f"\nripristino verificato (sha256, sonda cancellata): {rip}")
        ok &= rip
        scrivi(f"ESITO COMPLESSIVO: {'TUTTO COME ATTESO' if ok else 'DIFFORMITA'}")
        OUT.write_text("\n".join(righe) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
