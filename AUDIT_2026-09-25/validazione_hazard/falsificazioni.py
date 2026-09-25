"""FALSIFICAZIONE dei test del banco hazard (25/09/2026).

Per ogni rottura minima: si legge il sorgente IN MEMORIA, si applica la
sostituzione (deve comparire UNA volta), si lancia pytest sul file di test del
banco (sandbox: URL del DB finto), si verifica che diventi ROSSO, si RIPRISTINA
dal testo in memoria (mai git checkout) e si verifica l'hash. Alla fine la
suite deve tornare verde. Esito in ``falsificazioni_esito.txt``.

    python AUDIT_2026-09-25/validazione_hazard/falsificazioni.py
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PKG = os.path.join(RADICE, "Betfair", "stream", "scalper", "validazione_hazard")
TEST = os.path.join("Betfair", "stream", "tests", "test_validazione_hazard_2026_09_25.py")
TEST_V4 = os.path.join("Betfair", "stream", "tests", "test_atlante_v4_2026_09_25.py")
PY = sys.executable

ROTTURE = [
    ("M1 recupero 1T ignorato nella posizione", "dati.py",
     "return (1, mi + (ex if mi == 45 else 0))", "return (1, mi)"),
    ("M2 d2 = solo status.extra (ignora gli eventi oltre)", "dati.py",
     "p.d2 = max(ex, lb2)", "p.d2 = ex"),
    ("M3 s1_vivo conta anche i gol (selezione sull'esito)", "dati.py",
     "elif str(e.get(\"event_type\")) != \"Goal\":", "else:"),
    ("M4 regola di copertura 60% ignorata", "dati.py",
     "if cop < COPERTURA_MIN:", "if cop < 0:"),
    ("M5 autogol mai girati", "dati.py",
     "if sum(1 for x in flip if x[1] == \"h\") != gh:\n            return None\n        out = flip",
     "return None"),
    ("M6 finestra 3' lunga 2'", "stati.py",
     "y3 = (_conta(tutti, t + 3) - c_t > 0)", "y3 = (_conta(tutti, t + 2) - c_t > 0)"),
    ("M7 gol contati con posizione < t (non <=)", "stati.py",
     "return np.searchsorted(pos, t, side=\"right\").astype(np.int32)",
     "return np.searchsorted(pos, t, side=\"left\").astype(np.int32)"),
    ("M8 un minuto di recupero 2T in piu'", "stati.py",
     "n_rec = (p.s1_vivo if h == 1 else (p.d2 or 0))", "n_rec = (p.s1_vivo if h == 1 else (p.d2 or 0) + 1)"),
    ("M9 minuto live del recupero 2T = 90 fisso", "stati.py",
     "m_live = np.where(stop == 1, (45 if h == 1 else 90) + j, base + t)",
     "m_live = np.where(stop == 1, (45 if h == 1 else 90), base + t)"),
    ("M10 AUC senza ranghi medi sui pareggi", "metriche.py",
     "medi = (pos[inizi] + pos[fini - 1]) / 2.0", "medi = pos[inizi]"),
    ("M11 ricampioni non multinomiali", "metriche.py",
     "return rng.multinomial(n_partite, np.full(n_partite, 1.0 / n_partite), size=b).astype(np.float64)",
     "return np.ones((b, n_partite))"),
    ("M12 lettore finto ignora il filtro event_type", "produzione.py",
     "rows = [e for e in rows if str(e.get(\"event_type\")) == tipo]", "rows = rows"),
    ("M13 orizzonti di A0 scambiati", "produzione.py",
     "v = (c2[\"p\"], c3[\"p\"], c3[\"fonte\"])", "v = (c3[\"p\"], c2[\"p\"], c3[\"fonte\"])"),
    ("M14 recupero senza condizionare su partita viva", "candidati.py",
     "vivo = d > j[:, None]", "vivo = d >= 0"),
    ("M15 pesi di stagione col segno sbagliato", "candidati.py",
     "return np.power(0.5, (rif - stagioni).astype(float) / float(emivita))",
     "return np.power(0.5, (stagioni - rif).astype(float) / float(emivita))"),
    ("M16 moltiplicatore hazard lineare in p", "candidati.py",
     "return 1.0 - np.power(1.0 - p, mult)", "return np.clip(p * mult, 0, 1)"),
    ("M17 oracolo con un minuto in meno", "candidati.py",
     "resto = np.minimum(k, np.maximum(d_vero - j, 1))", "resto = np.minimum(k, np.maximum(d_vero - j - 1, 1))"),
    ("M18 media NON condizionata", "candidati.py",
     "atteso = (pi * vivo * (d - j[:, None])).sum(1) / np.maximum(massa, 1e-300)",
     "atteso = (pi * (d - j[:, None])).sum(1)"),
    ("M19 celle del recupero 2T sfalsate", "candidati.py",
     "J_BIN = np.array([0, 1, 2, 3, 4, 5, 6, 6, 7], dtype=np.int32)",
     "J_BIN = np.array([0, 1, 2, 3, 4, 5, 6, 7, 7], dtype=np.int32)"),
    ("M21 blocco recupero: soglia invertita", "dati.py",
     "out[f] = True if t < min_gol else (c / t) >= soglia", "out[f] = True if t < min_gol else (c / t) < soglia"),
    ("M22 blocco con pochi gol: niente ripiego sulla stagione", "dati.py",
     "        if t < min_gol:\n            c, t = stag.get((lid, s), [0, 0])\n", ""),
    ("M20 forza: aggiornamento PRIMA della previsione (sbircia)", "forza.py",
     "        out[p.fixture_id] = (lh, la, ll)\n        eh, ea = gh - lh, ga - la",
     "        eh, ea = gh - lh, ga - la\n        att[p.home_id] = att.get(p.home_id, 0.0) + 5 * eh\n"
     "        lh = m[0] * math.exp(att.get(p.home_id, 0.0) + dif.get(p.away_id, 0.0))\n"
     "        out[p.fixture_id] = (lh, la, ll)"),
]


def _hash(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:12]


def _pytest(file_test) -> int:
    env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x", SUPABASE_KEY="x")
    file_test = [file_test] if isinstance(file_test, str) else list(file_test)
    r = subprocess.run([PY, "-m", "pytest", *file_test, "-q", "-x", "-p", "no:cacheprovider"],
                       cwd=RADICE, env=env, capture_output=True, text=True)
    return r.returncode


def esegui(rotture, cartella, file_test, righe) -> bool:
    tutto_ok = True
    for nome, file_rel, vecchio, nuovo in rotture:
        path = os.path.join(cartella, file_rel)
        with open(path, encoding="utf-8") as fh:
            orig = fh.read()
        h0 = _hash(orig)
        n = orig.count(vecchio)
        if n != 1:
            righe.append(f"{nome}: SOSTITUZIONE NON UNICA ({n} occorrenze) - NON ESEGUITA")
            tutto_ok = False
            continue
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(orig.replace(vecchio, nuovo))
        try:
            rc = _pytest(file_test)
        finally:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(orig)
        with open(path, encoding="utf-8") as fh:
            ripristinato = _hash(fh.read()) == h0
        esito = "ROSSO" if rc != 0 else "VERDE (test NON falsificato!)"
        righe.append(f"{nome} [{file_rel}]: {esito}; ripristino {'OK' if ripristinato else 'FALLITO'} ({h0})")
        print(righe[-1], flush=True)
        tutto_ok = tutto_ok and rc != 0 and ripristinato
    return tutto_ok


def main() -> int:
    righe = []
    ok = esegui(ROTTURE, PKG, TEST, righe)
    extra = os.path.join(os.path.dirname(__file__), "rotture_v4.py")
    if os.path.exists(extra):
        ns: dict = {}
        exec(open(extra, encoding="utf-8").read(), ns)
        ok = esegui(ns["ROTTURE_V4"], os.path.join(RADICE, "Betfair", "stream", "scalper"), TEST_V4, righe) and ok
    rc = _pytest([TEST] + ([TEST_V4] if os.path.exists(os.path.join(RADICE, TEST_V4)) else []))
    righe.append(f"suite dopo i ripristini: {'VERDE' if rc == 0 else 'ROSSA'}")
    print(righe[-1])
    with open(os.path.join(os.path.dirname(__file__), "falsificazioni_esito.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(righe) + "\n")
    return 0 if ok and rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
