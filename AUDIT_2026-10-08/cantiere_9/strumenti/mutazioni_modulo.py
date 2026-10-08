"""Falsificazione dei test del cantiere 9 su `backtest/scavalco_rifiuti.py`.
Ogni mutazione: sostituzione testuale ESATTA (una sola occorrenza), test, ripristino,
verifica sha256. Lanciato dalla radice del worktree."""
import hashlib
import os
import shutil
import subprocess
import sys

F = "Betfair/stream/backtest/scavalco_rifiuti.py"
T = ["Betfair/stream/tests/test_banco_scavalco_rifiuti_2026_10_08.py"]

M = [
    ("G1 tetto del gruppo tolto", "        tetto = self.tetto\n",
     "        tetto = 1000.0  # MUTAZIONE\n"),
    ("G2 tetto per ordine, non per gruppo",
     "                gia = sum(CP.abbinato(o) for o in g[\"ordini\"])\n",
     "                gia = float(sim.size_matched or 0.0)  # MUTAZIONE\n"),
    ("G3 il guasto non finisce mai", "            g[\"stato\"] = \"finito\"\n",
     "            g[\"stato\"] = \"armato\"  # MUTAZIONE\n"),
    ("G4 nessun riarmo senza effetto",
     "                self.gruppi[k] = {\"chiave\": k, \"ordini\": [], \"stato\": \"armato\"}\n",
     "                g[\"stato\"] = \"finito\"  # MUTAZIONE\n"),
    ("R1 rifiuto senza codice",
     "            return sim._create_place_response(None, status=\"FAILURE\", error_code=cod)\n\n        sim.place = _place\n\n    def _rifiuta_rimpiazzo",
     "            return sim._create_place_response(None, status=\"FAILURE\", error_code=None)  # MUTAZIONE\n\n        sim.place = _place\n\n    def _rifiuta_rimpiazzo"),
    ("R2 importo del rifiutato non tolto", "            sim.size_voided += sim.size_remaining\n",
     "            pass  # MUTAZIONE\n"),
    ("R3 sostituto rifiutato lasciato nel Trade", "                    trade.orders.remove(nuovo)\n",
     "                    pass  # MUTAZIONE\n"),
    ("R4 tutti gli ordini del tipo rifiutati",
     "                        self._usati.add(t)\n", "                        pass  # MUTAZIONE\n"),
    ("C1 SV2 tolleranza larga",
     "            self._soll(\"SV2\")\n            if diff <= TOLLERANZA_PIATTO + 1e-9:\n",
     "            self._soll(\"SV2\")\n            if diff <= 1.0:  # MUTAZIONE\n"),
    ("C2 SV3 un scavalco in piu'", "            if len(c[\"scavalchi\"]) > SCAVALCHI_MAX:\n",
     "            if len(c[\"scavalchi\"]) > SCAVALCHI_MAX + 1:  # MUTAZIONE\n"),
    ("C3 SV4 quota non confrontata",
     "                       and _uguale(p.get(\"price\"), getattr(ot, \"price\", None), 1e-9)\n",
     "                       and _uguale(p.get(\"price\"), getattr(ot, \"price\", None), 0.02)  # MUTAZIONE\n"),
    ("C4 SV2 resto dichiarato scusato prima del massimo",
     "            if len(c[\"scavalchi\"]) >= SCAVALCHI_MAX and dichiarato:\n",
     "            if dichiarato:  # MUTAZIONE\n"),
    ("C5 RC3 codice non cercato",
     "                    and rec[\"codice\"] in _testo(p) for _kind, p, t in att)\n",
     "                    for _kind, p, t in att)  # MUTAZIONE\n"),
    ("C6 RC1 sequenza ferma non vista",
     "            if passo in (\"init\", \"placed\", \"trimmed\") and not CP.vivo(o) and not _in_volo(o):\n",
     "            if False:  # MUTAZIONE\n"),
    ("C7 RC2 tetto del loop alzato",
     "            if rec[\"dopo\"] > TETTO_ORDINI_DOPO_RIFIUTO:\n",
     "            if rec[\"dopo\"] > 1000:  # MUTAZIONE\n"),
    ("C8 RC4 resto non dichiarato scusato",
     "            if abs(w - lo) > TOLLERANZA_PIATTO + 1e-9 and not self._dichiarato(k, rec[\"ms\"]):\n",
     "            if False:  # MUTAZIONE\n"),
    ("C9 SV1 nessun limite di book allo scavalco",
     "        if not c[\"scavalchi\"] and not piatta and nlib - c[\"libro0\"] > LIBRI_SCAVALCO:\n",
     "        if not c[\"scavalchi\"] and not piatta and nlib - c[\"libro0\"] > 10 ** 6:  # MUTAZIONE\n"),
    ("C10 SV5 loss_cap sopra il tetto non visto",
     "            elif cap > 0 and vere > -cap + 0.005:\n",
     "            elif False:  # MUTAZIONE\n"),
    ("C11 SV1 chiusura dopo lo scavalco non attesa",
     "        if not dopo and not piatta and nlib - ultimo[\"libro_pausa\"] > LIBRI_SCAVALCO:\n",
     "        if False:  # MUTAZIONE\n"),
    ("C13 book riemesso contato come nuovo",
     "        if self._ultimo_ms.get(market_id) != pub:\n",
     "        if True:  # MUTAZIONE\n"),
    ("C15 book contati con l'orologio del banco, non col mercato",
     "        pub = int(pubblicato_ms) if pubblicato_ms else self.ms\n",
     "        pub = self.ms  # MUTAZIONE\n"),
    ("C16 il ciclo nuovo non chiude quello sorvegliato",
     "        nati = [t for t, i in self._ingressi.get(k, []) if i not in esclusi\n",
     "        nati = [t for t, i in [] if i not in esclusi  # MUTAZIONE\n"),
    ("C14 SV5 loss_cap senza le due cifre non visto",
     "            if vere is None or res is None:\n",
     "            if False:  # MUTAZIONE\n"),
    ("C12 scavalco non riconosciuto dal mercato",
     "    return (la == \"BACK\" and d > TOLLERANZA_PIATTO) or (la == \"LAY\" and d < -TOLLERANZA_PIATTO)\n",
     "    return False  # MUTAZIONE\n"),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


prima = sha(F)
testo = open(F, encoding="utf-8").read()
copia = F + ".salva_mut"
shutil.copyfile(F, copia)
try:
    for nome, vecchio, nuovo in M:
        n = testo.count(vecchio)
        if n != 1:
            print("MUTAZIONE %s: testo trovato %d volte, NON eseguita" % (nome, n))
            continue
        with open(F, "w", encoding="utf-8") as fh:
            fh.write(testo.replace(vecchio, nuovo))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"] + T,
                           capture_output=True, text=True, timeout=1200)
        righe = [l for l in r.stdout.splitlines() if " passed" in l or " failed" in l]
        print("MUTAZIONE %s: %s" % (nome, righe[-1] if righe else r.stdout[-300:]))
        shutil.copyfile(copia, F)
finally:
    shutil.copyfile(copia, F)
    os.remove(copia)
dopo = sha(F)
print("sha256 %s prima %s dopo %s %s" % (F, prima[:16], dopo[:16],
                                         "IDENTICO" if prima == dopo else "DIVERSO!!"))
