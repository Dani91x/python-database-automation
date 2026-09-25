# -*- coding: utf-8 -*-
"""FALSIFICAZIONE dei test della misura punto 8.

Per ogni mutazione: copia di sicurezza del file, rottura della metrica, test
mirato che DEVE diventare rosso, ripristino DALLA COPIA (mai `git checkout`:
incidente del 23/09) e verifica dello SHA-256 identico all'originale.

Uso:  python -m Betfair.stream.backtest.tools.misura_punto8.falsifica_misura_punto8
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from typing import List, Tuple

CART = os.path.dirname(os.path.abspath(__file__))
TEST = os.path.join(CART, "test_misura_punto8.py")

# (file, testo originale, testo rotto, test che deve diventare rosso, cosa rompe)
MUTAZIONI: List[Tuple[str, str, str, str, str]] = [
    ("comune.py", "return -math.log(max(EPS, float(p)))", "return 1.0 - float(p)",
     "test_log_loss_e_meno_log_p", "log-loss senza logaritmo"),
    ("comune.py", "idx = rng.integers(0, k, size=(int(giri), k))\n    medie",
     "idx = np.tile(np.arange(k), (int(giri), 1))\n    medie",
     "test_bootstrap_ricampiona_davvero", "IC senza ricampionamento"),
    ("comune.py", "    s, c, ordine = _raggruppa(valori, unita)\n    k = len(ordine)\n    rng = np.random.default_rng(int(seme))\n    idx = rng.integers(0, k, size=(int(giri), k))\n    medie",
     "    s, c, ordine = _raggruppa(valori, list(range(len(valori))))\n    k = len(ordine)\n    rng = np.random.default_rng(int(seme))\n    idx = rng.integers(0, k, size=(int(giri), k))\n    medie",
     "test_bootstrap_a_grappolo_non_a_riga", "bootstrap sulle righe invece che sulle partite"),
    ("comune.py", "        if hi < 0.0:\n            return MIGLIORA", "        if lo < 0.0:\n            return MIGLIORA",
     "test_verdetto", "MIGLIORA con l'IC che contiene lo zero"),
    ("o1_catena_lambda.py", "righe = {int(fid): fp_postgrest} if fp_postgrest else {}", "righe = {}",
     "test_o1_catena_attuale_e_quella_di_produzione", "catena attuale che non vede la fixture"),
    ("o1_catena_lambda.py", '        k = str(r.get("src")) if r.get("src") is not None else "nessun_modello_salvato"\n',
     '        if r.get("src") is None:\n            continue\n        k = str(r.get("src"))\n',
     "test_o1_distribuzione_lambda_source", "eventi senza modello esclusi dal denominatore"),
    ("o5_rossi.py", "rh = max(1e-12, residua * math.exp(-p.beta_squilibrio * d)) * mh",
     "rh = max(1e-12, residua * math.exp(-p.beta_squilibrio * d)) / mh",
     "test_o5_rosso_di_casa_abbassa_i_gol_di_casa", "moltiplicatore del rosso applicato al contrario"),
    ("o5_rossi.py", "bh = (a / lh0 + consumata) / rh", "bh = (a / lh0) / rh",
     "test_o5_moltiplicatore_neutro_e_la_produzione", "posteriore senza l'esposizione consumata"),
    ("o6_coda.py", "    if (gh, ga) in quotate:\n        return 0\n", "",
     "test_o6_esito_aggregati", "aggregato che vince anche su un risultato quotato"),
    ("s2_calibrazione_uscita.py", "while k < n - 1 and giorno(eventi[k]) == giorno(eventi[k - 1]):",
     "while False and giorno(eventi[k]) == giorno(eventi[k - 1]):",
     "test_s2_taglio_mai_nella_stessa_giornata", "taglio dentro la stessa giornata"),
    ("s2_calibrazione_uscita.py", 'prima = [e for e in eventi if (e["data"] or "")[:10] < g]',
     'prima = [e for e in eventi if (e["data"] or "")[:10] <= g]',
     "test_s2_origine_mobile_non_guarda_il_futuro", "tabella stimata anche sul giorno di prova"),
    ("m1_mike.py", '"p_cal": 1.0 - pu,', '"p_cal": pu,',
     "test_m1_affidabilita_su_dati_finti", "P dell'Over presa come P dell'Under"),
    ("x1_bias.py", '.setdefault("targets", {})["target_1x2"] = ml_c',
     '.setdefault("targets", {})["target_1X2"] = ml_c',
     "test_x1_calibra_con_la_pagella_e_chiavi_lette_dal_resolver", "chiave che il resolver non legge"),
    ("estrai_db.py", "        if len(righe) >= tetto:\n            if len(b) == 1:",
     "        if False:\n            if len(b) == 1:",
     "test_estrai_a_blocchi_dimezza_se_pieno", "blocco pieno accettato (troncamento)"),
    ("estrai_db.py",
     "list(filtri) + [lambda q, x=g0: q.gte(col_data, x),\n"
     "                                            lambda q, x=g1: q.lt(col_data, x)],",
     "list(filtri) + [lambda q, x=g0: q.gte(col_data, x)],",
     "test_estrai_per_giorno_legge_tutto_senza_timeout", "finestra senza il limite superiore del giorno"),
    ("estrai_db.py", "out.append((d0.isoformat(), (d0 + timedelta(days=1)).isoformat()))",
     "out.append((d0.isoformat(), (d0 + timedelta(days=2)).isoformat()))",
     "test_estrai_per_giorno_legge_tutto_senza_timeout", "finestre sovrapposte (righe duplicate)"),
    ("estrai_db.py", "            if not e_timeout(ex) or i == TENTATIVI - 1:",
     "            if True:",
     "test_estrai_ritenta_su_57014_con_pagina_dimezzata", "nessun ritentativo sul 57014"),
    ("estrai_db.py", "            pagina = max(1, pagina // 2)\n", "",
     "test_estrai_ritenta_su_57014_con_pagina_dimezzata", "ritentativo senza dimezzare la pagina"),
    ("estrai_db.py", "            if not e_timeout(ex) or timeout_di_fila >= TENTATIVI or len(b) == 1:",
     "            if True:",
     "test_estrai_a_blocchi_dimezza_su_57014", "blocchi senza ritentativo sul 57014"),
    ("estrai_db.py", '"open_date", "event_id", "2026-09-01", a)',
     '"created_at", "event_id", "2026-09-01", a)',
     "test_estrai_o1o6_con_le_colonne_vere", "omega_events filtrata su created_at (inesistente)"),
    ("estrai_db.py", "PAGINA = 1000\n", "PAGINA = 1000\n_SCRIVI = lambda q, r: q.upsert(r)\n",
     "test_estrai_nessuna_scrittura_nel_sorgente", "una scrittura nel file delle estrazioni"),
    ("estrai_db.py", '        i = testo.rfind("\\n[")\n        dati = json.loads(testo[i + 1:])',
     '        dati = []',
     "test_estrai_eventi_da_file", "stdout di certifica non letto"),
    ("o5_rossi.py", 'if tipo == "Goal" and "missed" not in det.lower():', 'if tipo == "Goal":',
     "test_o5_estrazione_finta_con_le_chiavi_di_match_events", "rigore sbagliato contato come gol"),
    ("x1_bias.py", "        if ml[0] == po[0]:\n            conta[\"concordi\"] += 1",
     "        if ml[0] != po[0]:\n            conta[\"concordi\"] += 1",
     "test_x1_concordanza_su_finestra_finta", "concordanza invertita"),
    ("x1_bias.py", "ib = C.bootstrap_media([x[2] - x[1] for x in rr]",
     "ib = C.bootstrap_media([x[1] - x[2] for x in rr]",
     "test_x1_brier_grezza_contro_calibrata", "differenza di Brier al contrario"),
    ("t1_superficie.py", "DB_LEAD_GAMES = 3", "DB_LEAD_GAMES = 2",
     "test_t1_soglie_uguali_al_bot", "soglia diversa da quella del bot"),
]


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _pytest(nome: str) -> int:
    env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x",
               SUPABASE_KEY="x")
    return subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider",
                           "-k", nome], env=env, capture_output=True, text=True,
                          timeout=600).returncode


def main() -> int:
    esiti = []
    for fname, vecchio, nuovo, test, cosa in MUTAZIONI:
        path = os.path.join(CART, fname)
        copia = path + ".falsifica.bak"
        sha0 = _sha(path)
        shutil.copyfile(path, copia)
        try:
            testo = open(path, encoding="utf-8").read()
            if testo.count(vecchio) != 1:
                esiti.append((cosa, "MUTAZIONE NON APPLICABILE", False))
                continue
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(testo.replace(vecchio, nuovo))
            rc = _pytest(test)
            esiti.append((cosa, f"{test}: {'ROSSO' if rc != 0 else 'VERDE (!!)'}", rc != 0))
        finally:
            shutil.copyfile(copia, path)
            os.remove(copia)
            if _sha(path) != sha0:
                print(f"!!! RIPRISTINO FALLITO su {fname}")
                return 2
    rc_tutti = _pytest("")
    for cosa, riga, ok in esiti:
        print(f"[{'OK' if ok else 'KO'}] {cosa:55s} -> {riga}")
    print(f"ripristino: SHA-256 identici su tutti i file; suite dopo il ripristino: "
          f"{'VERDE' if rc_tutti == 0 else 'ROSSA'}")
    return 0 if all(ok for *_x, ok in esiti) and rc_tutti == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
