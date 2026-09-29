"""Falsificazione dei test N3: ogni mutazione DEVE far diventare rosso almeno
un test. Il file originale si ripristina byte per byte (anche su errore).

Uso: python AUDIT_2026-09-28/cantiere_n/falsifica_n3.py [punto1|punto2|tutto]
"""
from __future__ import annotations

import subprocess
import sys

TEST = ["Betfair/stream/tests/test_banco_uscite_dichiarate_n3_2026_09_28.py",
        "Betfair/stream/tests/test_banco_scalper_sniper_2026_09_28.py",
        "Betfair/stream/tests/test_banco_uscite_manuali_n3_2026_09_28.py",
        "Betfair/stream/tests/test_firma_scaduta_ttl_n3_2026_09_28.py",
        "Betfair/stream/tests/test_proposta_sempre_coi_numeri_2026_09_29.py"]
TSB = "Betfair/stream/tennis_scalper/tennis_scalper_bot.py"
SCB = "Betfair/stream/scalper/scalper_bot.py"
SNB = "Betfair/stream/scalper/sniper_bot.py"
TB = "Betfair/stream/tennis_live/tools/replay_bot.py"
SC = "Betfair/stream/scalper/tools/replay_registrazioni.py"
UMF = "Betfair/stream/backtest/uscite_manuali.py"
UPF = "Betfair/stream/uscite_proposte.py"

PUNTO1 = [
    ("T1 tennis: riga senza interruttore", TB,
     '    control["uscite_automatiche"] = uscite_automatiche_scenario(scenario)\n',
     '    control["uscite_automatiche_x"] = uscite_automatiche_scenario(scenario)\n'),
    ("T2 tennis: nota non scritta", TB,
     "        ref.note.append(NOTA_USCITE_AUTO)\n", "        pass\n"),
    ("T3 tennis: scenario sempre manuale", TB,
     "    return scenario not in SCENARI_USCITE_MANUALI\n", "    return False\n"),
    ("S1 scalper: params senza interruttore", SC,
     '    params["uscite_automatiche"] = uscite_automatiche_scenario(scenario)\n', ""),
    ("S2 scalper: nota non scritta", SC,
     "        ref.note.append(NOTA_USCITE_AUTO)\n", "        pass\n"),
    ("S3 scalper: scenario sempre manuale", SC,
     "    return scenario not in SCENARI_USCITE_MANUALI\n", "    return False\n"),
]

PUNTO2 = [
    # il cancello di produzione (la mutazione sopravvissuta del coordinatore)
    ("TTL1 cancello: firma senza scadenza", UPF,
     "if firma is not None and now_s - firma <= TTL_APPROVAZIONE_S:",
     "if firma is not None:"),
    ("TTL2 cancello: limite del TTL escluso", UPF,
     "if firma is not None and now_s - firma <= TTL_APPROVAZIONE_S:",
     "if firma is not None and now_s - firma < TTL_APPROVAZIONE_S:"),
    # i controlli dell'osservatore
    ("UM1a interruttore acceso non visto", UMF,
     "        if automatiche:\n            self._viola(\"UM1\"",
     "        if False:\n            self._viola(\"UM1\""),
    ("UM1b uscita senza firma non vista", UMF,
     "        elif ok and (firma_prima is None or not self.firmate):",
     "        elif False:"),
    ("UM2a decisione senza proposta non vista", UMF,
     "            if not viva:\n", "            if False:\n"),
    ("UM2b proposta senza numeri non vista", UMF,
     "            elif mancano:\n", "            elif False:\n"),
    ("UM3a protezione nel cancello non vista", UMF,
     "        if motivo not in MOTIVI_DI_TRADING or not chiave.endswith(motivo):",
     "        if False:"),
    ("UM3b fine sessione non piatta non vista", UMF,
     "        if difetto:\n", "        if False:\n"),
    ("UM4 proposta decaduta rimasta non vista", UMF,
     "            if resta or firma:\n", "            if False:\n"),
    ("UF0 firma subito (senza attesa di N s)", UMF,
     "if not k or nata is None or ora_s - nata < FIRMA_DOPO_S:",
     "if not k or nata is None:"),
    ("UF1 firma doppia non vista", UMF,
     "        if self._usate[usata] > 1:\n", "        if False:\n"),
    ("UF2a nessun ordine non visto", UMF,
     "            if not uscita:\n                self._viola(",
     "            if False:\n                self._viola("),
    ("UF2b importo sempre giusto", UMF,
     "            if abs(eff - size) <= TOLLERANZA_IMPORTO:\n",
     "            if True:\n"),
    # 29/09 - UF2 e la catena place-and-trim di D2 (replay tennis_pro/scalper)
    ("UF2e parcheggio vivo contato come importo", UMF,
     "                            + (0.0 if e_parcheggio(o) else\n",
     "                            + (0.0 if False else\n"),
    ("UF2f parcheggio abbinato non contato", UMF,
     "            eff = round(sum((_f(getattr(o, \"size_matched\", 0.0)) or 0.0)\n",
     "            eff = round(sum((0.0 if e_parcheggio(o) else "
     "(_f(getattr(o, \"size_matched\", 0.0)) or 0.0))\n"),
    ("UF2g non aspetta la fine della catena", UMF,
     "            if not fine and any(e_parcheggio(o) and\n",
     "            if False and any(e_parcheggio(o) and\n"),
    ("UF2h rimpiazzi della catena ignorati", UMF,
     "                if _lato(getattr(o, \"side\", \"\")) == _lato(getattr(p, \"side\", \"\")) \\\n",
     "                if False and _lato(getattr(o, \"side\", \"\")) == _lato(getattr(p, \"side\", \"\")) \\\n"),
    ("UF2i ingressi del ciclo nuovo contati", UMF,
     "                and not self._e_ingresso(o)}", "}"),
    ("UF2j resto scusato senza dichiarazione", UMF,
     "            if 0 < manca < SOGLIA_RESTO_NON_PIAZZABILE and self._resto_dichiarato(\n",
     "            if 0 < manca < SOGLIA_RESTO_NON_PIAZZABILE or self._resto_dichiarato(\n"),
    ("UF2k resto scusato oltre la soglia", UMF,
     "            if 0 < manca < SOGLIA_RESTO_NON_PIAZZABILE and self._resto_dichiarato(\n",
     "            if 0 < manca and self._resto_dichiarato(\n"),
    ("UF2l quota del parcheggio sbagliata", UMF,
     "    return abs(prezzo - initial_place_price(lato.lower())) < 1e-9\n",
     "    return prezzo > 100.0\n"),
    ("UF2m tennis: memoria del bot non letta", TB,
     "            if (int(k[0]) == int(sel) and str(k[1]).upper() == str(lato).upper()\n",
     "            if (int(k[0]) == int(sel)\n"),
    ("UF2n scalper: resto di un'altra selezione", SC,
     "                if (int(p.get(\"selection_id\")) == int(sel)\n",
     "                if (True\n"),
    ("UF2c ordini di prima contati", UMF,
     'not in pend["ids_prima"]', "not in set()"),
    ("UF2d lato non guardato", UMF,
     '(not pend["lato"] or _lato(getattr(o, "side", "")) == pend["lato"])', "True"),
    ("UF3a proposta diversa non vista", UMF,
     'if _f(vista.get("decided_at")) != _f(viva_prima.get("decided_at")):',
     "if False:"),
    ("UF3b chiavi diverse non viste", UMF,
     'for k in ("motivo", "selection_id", "lato_chiusura", "market_id"):',
     "for k in ():"),
    # il cablaggio dei banchi
    ("W1 tennis: scenari manuali senza gate", TB,
     "            or scenario in UM.SCENARI:\n        # ", "            or False:\n        # "),
    ("W2 tennis: firme non passate al runner", TB,
     '"params": {"uscite_approvate": dict(self.firme)}}', '"params": {}}'),
    ("W3 scalper: sniper spento a uscite manuali", SC,
     "    return scenario in SCENARI_SNIPER or scenario in SCENARI_USCITE_MANUALI\n",
     "    return scenario in SCENARI_SNIPER\n"),
    # Z3 per IDENTITA' (reperto del coordinatore) e Z4 numeri obbligatori
    ("Z3a firma di qualsiasi posizione accettata", SC,
     "            presa = next((c for c in libere if c in cand), None)\n",
     "            presa = libere[0] if libere else None\n"),
    ("Z3b firma usata piu' volte", SC,
     "                libere.remove(presa)\n", "                pass\n"),
    ("Z3c firma dopo il verde accettata", SC,
     "    for n, (k, p) in enumerate(eventi):\n",
     "    for n, (k, p) in enumerate(sorted(eventi, key=lambda e: e[0] != "
     "\"uscita_eseguita_su_approvazione\")):\n"),
    ("Z3d motivo della firma ignorato", SC,
     '            cand = [str(x) + "target" for x in',
     '            cand = [str(x) + m for m in ("target", "stop", "timeout") for x in'),
    ("Z3e il tee non scrive la posizione", SC,
     "                    copia[CHIAVE_PREFISSI_GREEN] = prefissi_del_green(_s)\n",
     "                    pass\n"),
    ("Z3f posizione del verde non letta", SC,
     "        out.append(sn._prefisso_uscite(pos))\n", "        pass\n"),
    ("Z3g conteggio al posto dell'identita' (il vecchio Z3)", SC,
     "            for det in z3_verdi_senza_la_loro_firma(eventi):\n",
     "            for det in ([\"x\"] if sum(k == \"sniper_green\" for k, _p in eventi) > "
     "sum(k == \"uscita_eseguita_su_approvazione\" for k, _p in eventi) else []):\n"),
    ("Z4a numero vuoto accettato", UMF,
     "            if k in p and p.get(k) is None]", "            if False]"),
    ("Z4b chiave assente accettata", UMF,
     '    out = ["%s assente" % k for k in CHIAVI_PROPOSTA if k not in p]',
     "    out = []"),
    ("Z4c Z4 non guarda i difetti", SC,
     "                    if difetti:\n", "                    if False:\n"),
    ("W6 scalper: sniper non piatto non visto", SC,
     '            difetti.append("sniper non piatto")\n', "            pass\n"),
]


# 29/09 - UM2: la proposta porta SEMPRE i numeri (ultimo prezzo visto / dichiarato)
NUMERI = [
    ("N1 memoria del prezzo ignorata", UPF,
     "        visto = self._p.get(chiave)\n", "        visto = None\n"),
    ("N2 eta' del prezzo non dichiarata", UPF,
     "            return visto[0], {CHIAVE_ETA_PREZZO: None if eta is None else round(eta, 1)}\n",
     "            return visto[0], {}\n"),
    ("N3 mai visto non dichiarato", UPF,
     "        return None, {CHIAVE_NUMERI_NON_DISPONIBILI: (\n", "        return None, {\"x\": (\n"),
    ("N4 tennis: lato LAY mai annotato", TSB,
     '            self._ultimi_prezzi.annota((k_sl[0], k_sl[1], "LAY"), best_lay, now)\n',
     "            pass\n"),
    ("N5 calcio: lato LAY mai annotato", SCB,
     '            self._ultimi_prezzi.annota((k_sl[0], k_sl[1], "LAY"), best_lay, now)\n',
     "            pass\n"),
    ("N6 sniper: lato LAY mai annotato", SNB,
     '            self._ultimi_prezzi.annota((mid, int(runner.selection_id), "LAY"), bl, now)\n',
     "            pass\n"),
    ("N7 sniper: proposta non pubblicata a lato vuoto", SNB,
     "                # coi numeri dell'ultimo prezzo visto) arriva SUBITO alla scheda\n"
     "                self._pubblica_proposte()\n",
     "                # coi numeri dell'ultimo prezzo visto) arriva SUBITO alla scheda\n"
     "                pass\n"),
    ("N8 tennis: numeri col solo prezzo vivo (il difetto)", TSB,
     "                g_x = compute_green(nw_x, nl_x, px_p) if px_p else None\n",
     "                g_x = compute_green(nw_x, nl_x, px_x) if px_x else None\n"),
    ("N9 calcio: numeri col solo prezzo vivo (il difetto)", SCB,
     "                g_x = compute_green(nw_x, nl_x, px_p) if px_p else None\n",
     "                g_x = compute_green(nw_x, nl_x, px_x) if px_x else None\n"),
    ("N10 tennis: extra non passato alla proposta", TSB,
     "                se_perde=se_perde, **(extra or {})))\n", "                se_perde=se_perde))\n"),
    ("N11 calcio: extra non passato alla proposta", SCB,
     "                se_perde=se_perde, **(extra or {})))\n", "                se_perde=se_perde))\n"),
    ("N12 UM2: qualsiasi dichiarazione accettata", UMF,
     "    dichiarato = isinstance(motivo, str) and bool(motivo.strip())\n",
     "    dichiarato = motivo is not None\n"),
    ("N13 UM2: la dichiarazione copre tutti i numeri", UMF,
     "            and not (dichiarato and k in CHIAVI_NUMERI_CHIUSURA)]\n",
     "            and not dichiarato]\n"),
]


def main() -> int:
    quali = (sys.argv[1] if len(sys.argv) > 1 else "tutto").lower()
    mutazioni = {"punto1": PUNTO1, "punto2": PUNTO2, "numeri": NUMERI}.get(
        quali, PUNTO1 + PUNTO2 + NUMERI)
    if len(sys.argv) > 2:                  # filtro: solo le mutazioni che iniziano cosi'
        mutazioni = [m for m in mutazioni if m[0].split()[0] in sys.argv[2:]]
    esito = 0
    for nome, f, vecchio, nuovo in mutazioni:
        orig = open(f, "rb").read()
        testo = orig.decode("utf-8")
        if "\r\n" in testo:
            vecchio = vecchio.replace("\n", "\r\n")
            nuovo = nuovo.replace("\n", "\r\n")
        if testo.count(vecchio) != 1:
            print("!! %s: ancora non trovata (%d)" % (nome, testo.count(vecchio)))
            esito = 1
            continue
        try:
            open(f, "wb").write(testo.replace(vecchio, nuovo).encode("utf-8"))
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x",
                                "-p", "no:cacheprovider"] + TEST,
                               capture_output=True, text=True, timeout=900)
            rosso = r.returncode != 0
            print("%s %s" % ("ROSSO" if rosso else "VERDE!!", nome))
            if not rosso:
                esito = 1
        finally:
            open(f, "wb").write(orig)
    return esito


if __name__ == "__main__":
    sys.exit(main())
