"""Falsificazione dei test nuovi/aggiornati del cantiere «ko_green 3 minuti» (30/09).

Per ogni mutazione: si scrive nel file la mutazione (marcata MUTAZIONE), si
lanciano i test, si deve vedere ROSSO dove dichiarato, e si RIMETTE il file
com'era (testo originale tenuto in memoria, scritto in un finally). Alla fine:
nessun "MUTAZIONE" nei file, e il chiamante confronta `git diff --stat`.

uso (dalla radice del worktree, ambiente neutro):
    python AUDIT_2026-09-30/ko_green_3_minuti/falsifica_ko_green_3_minuti.py
MAI interrompere a meta'.
"""
from __future__ import annotations

import os
import subprocess
import sys

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENGINE = "Betfair/mike/engine.py"
CERTF = "Betfair/mike/certificazione.py"
REPLAY = "Betfair/mike/tools/replay_registrazioni.py"
NUOVO = "Betfair/mike/tests/test_mike_ko_green_3_minuti_2026_09_30.py"
FISCHIO = ("Betfair/mike/tests/test_mike_flusso_fischio_2026_09_13.py"
           "::test_strada_A_fill_parziale_copre_solo_il_residuo")
APPOGG = "Betfair/mike/tests/test_mike_ko_green_appoggiata_2026_09_16.py"
J5 = [APPOGG + "::test_sostituire_una_lay_viva_emette_SOLO_l_annullamento",
      APPOGG + "::test_con_l_annullamento_FALLITO_nessuna_lay_nuova_e_si_ritenta"]

# (nome, file, vecchio, nuovo, test da lanciare, test che DEVONO diventare rossi)
MUTAZIONI = [
    ("M1 riallineo sul piano che conta il parziale (codice di oggi)", ENGINE,
     "piano_vivo = piano_uscita_ko(ctx, params, Pe,\n"
     "                                     legs=[l for l in ctx.legs if l is not vivo]) or plan",
     "piano_vivo = plan  # MUTAZIONE", [NUOVO],
     ["test_parziale_a_30_secondi_resta_a_mercato",
      "test_parziale_abbinato_a_prezzo_migliore_resta_a_mercato",
      "test_servizio_parziale_al_fischio_resta_fino_allo_scadere"]),
    ("M2 parziale non vivo -> copertura subito (codice di oggi)", ENGINE,
     "            and (not live_open_selections(ctx.legs, snap.goals)\n"
     "                 or finestra_uscita_scaduta(ctx, snap, params)):",
     "            and True:  # MUTAZIONE", [NUOVO],
     ["test_parziale_scaduto_da_betfair_nella_finestra_si_riappoggia_il_residuo"]),
    ("M3 allo scadere nessun annullo", ENGINE,
     "    if finestra_uscita_scaduta(ctx, snap, params):\n        _annulla(uscita)",
     "    if finestra_uscita_scaduta(ctx, snap, params):\n        pass  # MUTAZIONE",
     [NUOVO],
     ["test_parziale_allo_scadere_annulla_il_residuo_e_copre_il_rischio_residuo",
      "test_non_abbinata_allo_scadere_annullo_e_copertura_intera",
      "test_servizio_parziale_al_fischio_resta_fino_allo_scadere"]),
    ("M4 la banca viva non si riallinea mai", ENGINE,
     "        if abs(float(vivo.price) - float(piano_vivo.price)) < 1e-9 and \\",
     "        # MUTAZIONE\n"
     "        if True or abs(float(vivo.price) - float(piano_vivo.price)) < 1e-9 and \\",
     [NUOVO],
     ["test_se_cambia_la_posizione_d_ingresso_la_banca_si_riallinea"]),
    ("M5 la finestra non scade mai", ENGINE,
     "    return float(snap.now) - float(ctx.live_since) >= float(params[\"ko_green_window_s\"])",
     "    return False  # MUTAZIONE", [NUOVO, FISCHIO],
     ["test_parziale_allo_scadere_annulla_il_residuo_e_copre_il_rischio_residuo",
      "test_non_abbinata_allo_scadere_annullo_e_copertura_intera",
      "test_parziale_scaduto_da_betfair_a_finestra_chiusa_si_copre",
      "test_servizio_parziale_al_fischio_resta_fino_allo_scadere",
      "test_strada_A_fill_parziale_copre_solo_il_residuo"]),
    ("M6 gol dopo il fischio ignorato", ENGINE,
     "    if gol_dopo_il_fischio(ctx, snap):\n        _annulla(uscita)",
     "    if False:  # MUTAZIONE\n        _annulla(uscita)", [NUOVO],
     ["test_gol_nella_finestra_con_parziale_strada_c"]),
    ("M7 tutta abbinata non e' FLAT", ENGINE,
     "        if not live_open_selections(ctx.legs, snap.goals):\n            bloccato",
     "        if live_open_selections(ctx.legs, snap.goals):  # MUTAZIONE\n            bloccato",
     [NUOVO], ["test_tutta_abbinata_a_60_secondi_e_flat_subito"]),
    ("M8 copertura sullo stake lordo", ENGINE,
     "    _w, l = exposure(legs, MARKET_OU35, SEL_UNDER)\n"
     "    return round(max(0.0, -float(l)), 2)",
     "    return round(sum(float(x.matched) for x in legs if x.side == 'back' and "
     "x.market == MARKET_OU35), 2)  # MUTAZIONE", [NUOVO, FISCHIO],
     ["test_parziale_allo_scadere_annulla_il_residuo_e_copre_il_rischio_residuo",
      "test_servizio_parziale_al_fischio_resta_fino_allo_scadere",
      "test_strada_A_fill_parziale_copre_solo_il_residuo"]),
    ("M9 due lay nello stesso giro (J5 spento)", ENGINE,
     "    fermate = [(a, g) for a, g in fermate if g is not None]\n    if not fermate:\n"
     "        return d\n    tolte = {id(a) for a, _ in fermate}\n    kept = [a for a in d.actions if id(a) not in tolte]\n"
     "    a0, g0 = fermate[0]\n    come = \"a esito ignoto\" if g0.needs_reconcile else \"ancora viva\"\n"
     "    perche = (f\"lay '",
     "    fermate = []  # MUTAZIONE\n    if not fermate:\n"
     "        return d\n    tolte = {id(a) for a, _ in fermate}\n    kept = [a for a in d.actions if id(a) not in tolte]\n"
     "    a0, g0 = fermate[0]\n    come = \"a esito ignoto\" if g0.needs_reconcile else \"ancora viva\"\n"
     "    perche = (f\"lay '", J5,
     ["test_sostituire_una_lay_viva_emette_SOLO_l_annullamento",
      "test_con_l_annullamento_FALLITO_nessuna_lay_nuova_e_si_ritenta"]),
    ("K1 KG1 cieco", CERTF,
     "def _kg1(ctx, snap, d, params):\n    if ctx.state == \"LIVE_KO_GREEN\":",
     "def _kg1(ctx, snap, d, params):\n    return None  # MUTAZIONE\n    if ctx.state == \"LIVE_KO_GREEN\":",
     [NUOVO],
     ["test_kg1_rosso_sull_annullo_del_parziale_a_29_secondi",
      "test_kg1_rosso_sulla_copertura_dentro_la_finestra",
      "test_kg1_rosso_sulla_copertura_dimensionata_sullo_stake_lordo"]),
    ("K2 KG1 accusa anche il riallineo legittimo", CERTF,
     "        if abs(giusta - float(u.size)) > 0.011 + 0.01 * float(u.size):\n            return None",
     "        pass  # MUTAZIONE", [NUOVO],
     ["test_kg1_tace_allo_scadere_col_gol_e_sul_riallineo"]),
    ("K3 KG1 non guarda l'importo della copertura", CERTF,
     "    if E.cover_form(params) != E.COVER_LAY_U45:\n        return None",
     "    return None  # MUTAZIONE", [NUOVO],
     ["test_kg1_rosso_sulla_copertura_dimensionata_sullo_stake_lordo"]),
    ("P1 il guasto colpisce ogni riga dal ref", REPLAY,
     "                        return _ruolo(r) == \"ko_green\"",
     "                        return True  # MUTAZIONE", [NUOVO],
     ["test_scenario_ko_green_parziale_riconosce_solo_la_banca_al_fischio"]),
    ("P2 sul canale non si guarda l'importo", REPLAY,
     "\n                        and abs(float(r.get(\"size\") or 0.0) - size) < 0.005):",
     "):  # MUTAZIONE", [NUOVO],
     ["test_scenario_ko_green_parziale_riconosce_solo_la_banca_al_fischio"]),
]


def _pytest(bersagli):
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf",
           "--no-header"] + list(bersagli)
    p = subprocess.run(cmd, cwd=RADICE, capture_output=True, text=True, timeout=600)
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    esiti = []
    for nome, rel, vecchio, nuovo, bersagli, rossi_attesi in MUTAZIONI:
        path = os.path.join(RADICE, rel)
        with open(path, "r", encoding="utf-8", newline="") as fh:
            originale = fh.read()
        # la copia di lavoro puo' avere CRLF (autocrlf): le ancore si adeguano
        nl = "\r\n" if "\r\n" in originale else "\n"
        vecchio, nuovo = vecchio.replace("\n", nl), nuovo.replace("\n", nl)
        if originale.count(vecchio) != 1:
            esiti.append((nome, "ANCORA NON TROVATA (%d)" % originale.count(vecchio), []))
            continue
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(originale.replace(vecchio, nuovo))
            rc, out = _pytest(bersagli)
        finally:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(originale)
        falliti = [r.split("::")[-1].split(" ")[0] for r in out.splitlines()
                   if r.startswith("FAILED ")]
        mancano = [t for t in rossi_attesi if t not in falliti]
        ok = rc != 0 and not mancano
        esiti.append((nome, "ROSSO come atteso" if ok else "NON ROSSO: mancano %s" % mancano,
                      falliti))
    for nome, esito, falliti in esiti:
        print("%-62s %s | rossi: %s" % (nome, esito, ", ".join(falliti)))
    residui = 0
    for rel in (ENGINE, CERTF, REPLAY):
        with open(os.path.join(RADICE, rel), "r", encoding="utf-8") as fh:
            residui += fh.read().count("MUTAZIONE")
    print("MUTAZIONE rimaste nei file:", residui)
    rc, out = _pytest([NUOVO, FISCHIO] + J5)
    print("dopo il ripristino:", out.strip().splitlines()[-1])
    return 0 if all(e[1] == "ROSSO come atteso" for e in esiti) and residui == 0 and rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
