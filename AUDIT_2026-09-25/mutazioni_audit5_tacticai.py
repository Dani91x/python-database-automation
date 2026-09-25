"""Falsificazione dei test nuovi di tactical_engine/serving.py (AUDIT5, 25/09/2026).

Per ogni mutante: riscrive serving.py con il difetto, lancia i test, RIPRISTINA il
file originale (sempre, anche su errore) e verifica che il file sia tornato identico
byte per byte. Atteso: ogni mutante ROSSO.

Uso (DB sempre sandbox):
  set SUPABASE_URL=http://127.0.0.1:9 & set SUPABASE_SERVICE_ROLE_KEY=x & set SUPABASE_KEY=x
  .venv\\Scripts\\python.exe AUDIT_2026-09-25\\mutazioni_audit5_tacticai.py
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVING = os.path.join(ROOT, "tactical_engine", "serving.py")

MUTANTI = {
    # R1: le partite del giorno tornano a venire da `matches` (il difetto di prima)
    "R1_fonte_matches": ('sb.table("fixture_predictions").select(TODAY_COLS)',
                         'sb.table("matches").select(TODAY_COLS)'),
    # R2: pagina senza ORDER BY (ordine fisico: il cursore keyset salta/duplica righe)
    "R2_senza_order_by": ('batch = q.order("fixture_id").limit(page_size)',
                          'batch = q.limit(page_size)'),
    # R2: uscita su "pagina corta" invece che su pagina vuota (max_rows perde righe)
    "R2_esce_su_pagina_corta": ("        rows.extend(batch)\n        cursore = batch[-1][\"fixture_id\"]\n",
                                "        rows.extend(batch)\n        cursore = batch[-1][\"fixture_id\"]\n"
                                "        if len(batch) < page_size:\n            break\n"),
    # R2: niente ordine cronologico deterministico dello storico
    "R2_senza_sort_cronologico": ('    rows.sort(key=lambda r: (r.get("fixture_date") or "", r.get("fixture_id") or 0))\n', ""),
    # R1: il filtro "non giocata" non si applica piu' (la partita FT verrebbe predetta)
    "R1_senza_filtro_giocate": ('            and r["status_short"] not in PLAYED]', '            ]'),
}


def main() -> int:
    env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x", SUPABASE_KEY="x")
    with open(SERVING, "rb") as f:
        originale = f.read()
    testo = originale.decode("utf-8")
    esiti = {}
    try:
        for nome, (vecchio, nuovo) in MUTANTI.items():
            if vecchio not in testo:
                print(f"{nome}: MUTANTE NON APPLICABILE (testo non trovato)")
                esiti[nome] = "non applicato"
                continue
            with open(SERVING, "wb") as f:
                f.write(testo.replace(vecchio, nuovo, 1).encode("utf-8"))
            # SOLO_TEST=<nome> restringe al singolo test (per vedere rosso ANCHE il test mirato)
            bersaglio = "tactical_engine/tests/test_serving.py"
            if os.environ.get("SOLO_TEST"):
                bersaglio += "::" + os.environ["SOLO_TEST"]
            if os.environ.get("SOLO_MUTANTE") and os.environ["SOLO_MUTANTE"] != nome:
                continue
            r = subprocess.run([sys.executable, "-m", "pytest", bersaglio,
                                "-q", "-p", "no:cacheprovider", "-x", "--tb=line"],
                               cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
            righe = [ln for ln in r.stdout.splitlines() if ln.strip()]
            esiti[nome] = "ROSSO" if r.returncode != 0 else "VERDE (test non falsificato!)"
            print(f"=== {nome}: {esiti[nome]}")
            for ln in righe[-4:]:
                print("    " + ln)
    finally:
        with open(SERVING, "wb") as f:
            f.write(originale)
    with open(SERVING, "rb") as f:
        assert f.read() == originale, "RIPRISTINO FALLITO"
    print("ripristino: serving.py identico all'originale")
    return 0 if all(v == "ROSSO" for v in esiti.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
