"""Mutazioni INDIPENDENTI del coordinatore sulla consegna N (28/09/2026).

Si lancia dalla radice del worktree di verifica (origin/master + patch N).
Per ogni mutazione: copia del file, sostituzione di UNA occorrenza (ancora a
riga singola o doppia, CRLF rispettato), test mirati, ripristino dalla copia,
md5. Non va MAI interrotto: il ripristino e' nel finally.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple

PY = sys.executable
RADICE = Path.cwd()
COPIE = Path(__file__).resolve().parent / "copie_mutazioni"
COPIE.mkdir(exist_ok=True)

T_CANCELLO = [
    "Betfair/stream/tests/test_coordinatore_cancello_uscite_2026_09_28.py",
    "Betfair/stream/tests/test_scalper_uscite_automatiche_2026_09_25.py",
    "Betfair/stream/tests/test_scalper_uscite_manuali_al_riavvio_2026_09_28.py",
    "Betfair/stream/tests/test_uscite_manuali_al_nuovo_avvio_2026_09_28.py",
    "Betfair/stream/tests/test_sniper_uscite_automatiche_2026_09_28.py",
    "Betfair/stream/tests/test_sniper_bot_2026_07_10.py",
    "Betfair/stream/tennis_scalper/tests",
    "Betfair/stream/tennis_live/tests/test_tennis_firme_e_proposte_2026_09_28.py",
    "Betfair/stream/tennis_live/tests/test_tennis_uscite_manuali_al_riavvio_2026_09_28.py",
    "Betfair/stream/tennis_live/tests/test_tennis_auto_mode_2026_09_25.py",
]
T_MIKE = ["Betfair/mike/tests"]
T_OMEGA = ["Betfair/omega"]
T_SAFE = ["Betfair/safe_strategy/tests/test_uscite_manuali_al_riavvio_2026_09_28.py",
          "Betfair/safe_strategy/tests/test_bot_service.py",
          "Betfair/safe_strategy/tests"]
UP = "Betfair/stream/uscite_proposte.py"
ME = "Betfair/mike/engine.py"
AUTO = "automatiche=bool(self.uscite_automatiche)"

# (nome, file, vecchio, nuovo, quale occorrenza (0 = prima), test)
MUTAZIONI: List[Tuple[str, str, str, str, int, List[str]]] = [
    ("N1 cancello: la firma senza proposta viva viene accettata", UP,
     "                if viva is None or (nata is not None and t < nata):",
     "                if False:  # MUTAZIONE", 0, T_CANCELLO),
    ("N2 cancello: la proposta decade ma la firma resta", UP,
     "        firma = self.approvate.pop(k, None)",
     "        firma = None  # MUTAZIONE", 0, T_CANCELLO),
    ("N3 cancello: una firma non scade mai (TTL tolto)", UP,
     "            if firma is not None and now_s - firma <= TTL_APPROVAZIONE_S:",
     "            if firma is not None:  # MUTAZIONE", 0, T_CANCELLO),
    ("N4 cancello: la firma usata resta valida (due uscite con una firma)", UP,
     "                self.approvate.pop(chiave, None)\n                self._consumate[chiave] = firma\n                viva",
     "                viva", 0, T_CANCELLO),
    ("N5 cancello: in manuale esce lo stesso (il cancello dice sempre si')", UP,
     "            if automatiche:",
     "            if True:  # MUTAZIONE", 0, T_CANCELLO),
    ("N6 mike: firma senza proposta esegue", ME,
     "    if firmata is None:\n        # 29/09",
     "    if firmata is None:\n        return True  # MUTAZIONE\n        # 29/09", 0, T_MIKE),
    ("N7 mike: la proposta decade ma la firma resta", ME,
     "    # se la proposta decade, la firma cade con lei\n    if isinstance(ctx.uscita_approvata, dict):",
     "    # se la proposta decade, la firma cade con lei\n    if False and isinstance(ctx.uscita_approvata, dict):  # MUTAZIONE", 0, T_MIKE),
    ("N8 mike: firma su un motivo esegue un altro motivo", ME,
     "    if _approvazione_valida(ctx, chiave, snap.now) and not firma_altra_uscita:",
     "    if _approvazione_valida(ctx, chiave, snap.now):  # MUTAZIONE", 0, T_MIKE),
    ("N9 sniper: sempre automatico (l'interruttore non conta)",
     "Betfair/stream/scalper/sniper_bot.py", AUTO, "automatiche=True", 0, T_CANCELLO),
    ("N10 scalper calcio: sempre automatico",
     "Betfair/stream/scalper/scalper_bot.py", AUTO, "automatiche=True", 0, T_CANCELLO),
    ("N11 tennis pro: sempre automatico",
     "Betfair/stream/tennis_scalper/tennis_pro_bot.py", AUTO, "automatiche=True", 0, T_CANCELLO),
    ("N12 tennis swing: sempre automatico",
     "Betfair/stream/tennis_scalper/tennis_swing_bot.py", AUTO, "automatiche=True", 0, T_CANCELLO),
    ("N13 tennis flb: sempre automatico",
     "Betfair/stream/tennis_scalper/tennis_flb_bot.py", AUTO, "automatiche=True", 0, T_CANCELLO),
    ("N14 scalper tennis: sempre automatico",
     "Betfair/stream/tennis_scalper/tennis_scalper_bot.py", AUTO, "automatiche=True", 0, T_CANCELLO),
    ("N15 riavvio: Mike resta in automatico dopo un avvio nuovo",
     "Betfair/stream/avvio_app.py",
     "        return {**params, \"uscite_automatiche\": False}",
     "        return None  # MUTAZIONE", 0,
     T_CANCELLO[:4] + ["Betfair/mike/tests/test_mike_uscite_manuali_al_riavvio_2026_09_28.py",
                       "Betfair/mike/tests/test_mike_avvio_app_2026_09_16.py"]),
    ("N16 riavvio: Omega resta in automatico dopo un avvio nuovo",
     "Betfair/stream/avvio_app.py",
     "        return {**params, \"uscite_protezione\": \"avvisa_e_proponi\"}",
     "        return None  # MUTAZIONE", 0,
     T_CANCELLO[:4] + ["Betfair/omega/test_omega_uscite_manuali_al_riavvio_2026_09_28.py"]),
    ("N17 riavvio: Safe resta in automatico dopo un avvio nuovo",
     "Betfair/stream/avvio_app.py",
     "        return {**params, \"uscite_automatiche\": nuova, \"tennis_exit_approval\": True}",
     "        return None  # MUTAZIONE", 0,
     T_CANCELLO[:4] + ["Betfair/safe_strategy/tests/test_uscite_manuali_al_riavvio_2026_09_28.py"]),
    ("N18 omega: l'approvazione non ricontrolla la condizione",
     "Betfair/omega/omega_service.py",
     "    return {\"error\": \"condizione_non_piu_valida\",",
     "    return None\n    return {\"error\": \"condizione_non_piu_valida\",", 0, T_OMEGA),
]


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def sostituisci(testo: bytes, vecchio: str, nuovo: str, quale: int) -> bytes:
    crlf = b"\r\n" in testo
    v = vecchio.encode("utf-8")
    n = nuovo.encode("utf-8")
    if crlf:
        v = v.replace(b"\n", b"\r\n")
        n = n.replace(b"\n", b"\r\n")
    pos = -1
    for _ in range(quale + 1):
        pos = testo.find(v, pos + 1)
        if pos < 0:
            raise LookupError("ancora non trovata")
    return testo[:pos] + n + testo[pos + len(v):]


def main() -> int:
    esiti = []
    for nome, rel, vecchio, nuovo, quale, test in MUTAZIONI:
        f = RADICE / rel
        copia = COPIE / (rel.replace("/", "__") + ".orig")
        shutil.copy2(f, copia)
        prima = md5(f)
        esito = "?"
        t0 = time.time()
        try:
            try:
                f.write_bytes(sostituisci(f.read_bytes(), vecchio, nuovo, quale))
            except LookupError:
                esito = "NON APPLICATA (ancora non trovata)"
                continue
            esistenti = [t for t in test if (RADICE / t).exists()]
            try:
                r = subprocess.run(
                    [PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *esistenti],
                    cwd=str(RADICE), capture_output=True, text=True, errors="replace",
                    timeout=420)
            except subprocess.TimeoutExpired:
                esito = "ROSSA PER BLOCCO (test appesi oltre 420 s)"
                continue
            coda = [x for x in r.stdout.strip().splitlines() if x.strip()][-1:] or [""]
            falliti = [x for x in r.stdout.splitlines()
                       if x.startswith("FAILED") or x.startswith("ERROR")]
            if r.returncode == 0:
                esito = "SOPRAVVISSUTA (test verdi) | " + coda[0]
            else:
                esito = "ROSSA | " + (falliti[0][:150] if falliti else coda[0][:150])
        finally:
            shutil.copy2(copia, f)
            dopo = md5(f)
            ok = "ripristino OK" if dopo == prima else "!!! RIPRISTINO FALLITO !!!"
            esiti.append((nome, esito, ok, time.time() - t0))
            print("%-72s -> %s [%s, %.0f s]" % (nome[:72], esito, ok, time.time() - t0),
                  flush=True)
    sopravvissute = [e for e in esiti if e[1].startswith("SOPRAVVISSUTA")]
    non_appl = [e for e in esiti if e[1].startswith("NON APPLICATA")]
    rotti = [e for e in esiti if "FALLITO" in e[2]]
    print("\nTOTALE %d | rosse %d | SOPRAVVISSUTE %d | non applicate %d | ripristini falliti %d" % (
        len(esiti), len(esiti) - len(sopravvissute) - len(non_appl), len(sopravvissute),
        len(non_appl), len(rotti)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
