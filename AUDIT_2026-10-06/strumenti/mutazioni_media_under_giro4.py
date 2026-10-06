"""Falsificazione del quarto giro della modalita' <<media under>> (06/10/2026):
nome di strategia per partita, P1 (lo stop lascia la banca), P13 (ripresa dal
conto in soldi veri), il banco del riavvio.

Stessa macchina dei giri precedenti (UNA sostituzione per volta, deve comparire
esattamente una volta; test dei quattro giri; ripristino con
``git checkout -- <file>`` e verifica ``git diff --quiet``).

Uso (dalla radice del repo, albero pulito):
    python AUDIT_2026-10-06/strumenti/mutazioni_media_under_giro4.py [id ...]

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                "AUDIT_2026-10-05", "strumenti"))
import mutazioni_media_under as G1  # noqa: E402

MU = G1.MU
RR = G1.RR
SS = G1.SS
CE = G1.CE

PY = ["python", "-m", "pytest",
      "Betfair/stream/tests/test_scalper_media_under_2026_10_05.py",
      "Betfair/stream/tests/test_scalper_media_under_giro2_2026_10_05.py",
      "Betfair/stream/tests/test_scalper_media_under_giro3_2026_10_06.py",
      "Betfair/stream/tests/test_scalper_media_under_giro4_2026_10_06.py",
      "Betfair/stream/tests/test_scalper_arresto_ordinato_2026_10_02.py",
      "-q", "-p", "no:cacheprovider", "-p", "no:randomly"]

# (id, file, vecchio, nuovo, descrizione)
MUTAZIONI: List[Tuple[str, str, str, str, str]] = [
    # --- A. il nome per partita
    ("J1", SS, '''    return ("%s%s" % (PREFISSI_STRATEGIA[ruolo], str(event_id)))[:15]''',
     '''    return ("%s%s" % (PREFISSI_STRATEGIA[ruolo], ""))[:15]''',
     "il nome della strategia non dipende dalla partita"),
    ("J2", SS, '''            name=nome_strategia("media", ev),''',
     '''            name=None,''',
     "la media under torna al nome della classe"),
    # --- B. P1
    ("J3", MU, '''        b = self._banca
        if b is None or o is not b or _lato(b) != "LAY" or not vivo_o_in_volo(b):
            return False
        if str(getattr(b.order_type, "persistence_type", "") or "") != "PERSIST":
            return False''',
     '''        b = self._banca
        if True:
            return False
        if str(getattr(b.order_type, "persistence_type", "") or "") != "PERSIST":
            return False''',
     "P1 spento: la banca non e' mai da lasciare"),
    ("J4", MU, '''        if self.force_flat:
            # 06/10 (P1): allo stop nessuna punta resta sul book
            self._ritira_la_punta_allo_stop(market)''',
     '''        if False:
            # 06/10 (P1): allo stop nessuna punta resta sul book
            self._ritira_la_punta_allo_stop(market)''',
     "allo stop la punta in corso resta sul book"),
    ("J5", MU, '''        return (c is not None and abs(float(b.order_type.price) - c) < 1e-9
                and abs(resto - al_centesimo(banca_esatta(pos, c))) <= 0.01)''',
     '''        return True''',
     "pronta allo stop anche con la banca che non copre la posizione"),
    ("J6", SS, '''        return [(m, o) for m, o in tutti if not _lascia(o)]''',
     '''        return list(tutti)''',
     "l'annullo all'arresto toglie anche la banca da lasciare"),
    ("J7", SS, '''    propri = [b for b in tutti if b not in lascia]''',
     '''    propri = list(tutti)''',
     "lo sweep del crash annulla anche la banca da lasciare"),
    ("J8", SS, '''    if lascia and not propri:''',
     '''    if False:''',
     "solo la banca nel blotter: lo sweep ripiega sul market-wide"),
    # --- C. P13
    ("J9", MU, '''        if self.stato == RIPRESA:
            # 06/10 (P13): nessun ordine finche' la posizione non e' ricostruita''',
     '''        if False:
            # 06/10 (P13): nessun ordine finche' la posizione non e' ricostruita''',
     "in RIPRESA la modalita' opera (nessun freno: ordini doppi)"),
    ("J10", MU, '''        if mancano:
            if now - float(r["da_ms"]) >= ATTESA_RIPRESA_MS:''',
     '''        if False:
            if now - float(r["da_ms"]) >= ATTESA_RIPRESA_MS:''',
     "la ripresa non aspetta che flumine riadotti gli ordini vivi"),
    ("J11", MU, '''            self._rientri = len(abbinate) - 1''',
     '''            self._rientri = len(abbinate)''',
     "ricostruzione: un rientro in piu'"),
    ("J12", MU, '''            self._ultimo_ingresso = float(abbinate[-1].order_type.price)''',
     '''            self._ultimo_ingresso = float(abbinate[0].order_type.price)''',
     "ricostruzione: ultimo ingresso = il primo"),
    ("J13", MU, '''            if self.par.obiettivo_netto is not None:
                self._t_lordo = lordo_da_netto(self.par.obiettivo_netto, self.par.commissione)
            else:
                c0 = tick_sotto(p0, self.par.tick_chiusura)
                self._t_lordo = obiettivo_automatico(m0, p0, c0) if c0 else None''',
     '''            self._t_lordo = None''',
     "ricostruzione: obiettivo perso"),
    ("J14", MU, '''        self.stats["cicli_chiusi"] = len(chiusi)''',
     '''        self.stats["cicli_chiusi"] = 0''',
     "ricostruzione: cicli chiusi dimenticati"),
    ("J15", MU, '''            if self.stato == MASSIMO:
                self._dichiarati.add("massimo")''',
     '''            if False:
                self._dichiarati.add("massimo")''',
     "ricostruzione al massimo: l'avviso del massimo si ripete"),
    ("J16", MU, '''        self._ripresa = {"righe": righe, "letto": True, "da_ms": None}
        self.stato = RIPRESA''',
     '''        self._ripresa = {"righe": righe, "letto": True, "da_ms": None}
        self.stato = FERMO''',
     "ordini sul conto ma la modalita' parte come nuova"),
    ("J17", MU, '''ATTESA_RIPRESA_MS = 60_000''',
     '''ATTESA_RIPRESA_MS = 10 ** 12''',
     "ripresa senza adozione: mai bloccata (attesa infinita, nessun avviso)"),
    ("J18", SS, '''    for s in list(getattr(framework, "strategies", None) or []):
        extra = getattr(s, "ordini_dal_conto", None)''',
     '''    for s in []:
        extra = getattr(s, "ordini_dal_conto", None)''',
     "l'esposizione della sessione non conta gli ordini letti dal conto"),
    ("J19", SS, '''        if not ordini or not getattr(r, "more_available", False):''',
     '''        if True:''',
     "lettura del conto senza le pagine successive"),
    ("J20", SS, '''            if not session_paper:
                _esito_ripresa = prepara_ripresa_media(trading, media, ev)''',
     '''            if False:
                _esito_ripresa = prepara_ripresa_media(trading, media, ev)''',
     "in soldi veri il conto non si legge all'avvio"),
    # --- D. il banco
    ("J21", RR, '''        for strat in (list(self.medie) or [mu]):''',
     '''        for strat in [mu]:''',
     "i controlli M vedono solo la sessione corrente (doppi dopo un riavvio invisibili)"),
    ("J22", RR, '''                o.trade.strategy = nuova
                bl._strategy_orders[vecchia].remove(o)''',
     '''                continue
                bl._strategy_orders[vecchia].remove(o)''',
     "il banco non simula l'adozione di flumine"),
]


def main(scelte: List[str]) -> int:
    rc, _ = G1._esegui(["git", "diff", "--quiet"])
    if rc != 0:
        print("ALBERO NON PULITO: commit prima della falsificazione")
        return 2
    rc, out = G1._esegui(PY)
    if rc != 0:
        print("SUITE ROSSA SENZA MUTAZIONI: niente da falsificare\n" + out[-2000:])
        return 2
    righe = []
    for mid, f, vecchio, nuovo, descr in MUTAZIONI:
        if scelte and mid not in scelte:
            continue
        testo = open(f, encoding="utf-8").read()
        n = testo.count(vecchio)
        if n != 1:
            righe.append((mid, descr, "MUTAZIONE NON APPLICABILE (%d occorrenze)" % n, []))
            print("%s | %s | non applicabile (%d)" % (mid, descr, n), flush=True)
            continue
        open(f, "w", encoding="utf-8").write(testo.replace(vecchio, nuovo))
        try:
            _rc, out = G1._esegui(PY)
            rossi = G1._rossi_py(out)
            if "collected 0" in out or ("error" in out.lower() and not rossi):
                rossi.append("ERRORE DI RACCOLTA: " + out.strip().splitlines()[-1])
        finally:
            subprocess.run(["git", "checkout", "--", f], check=True)
        rc, _ = G1._esegui(["git", "diff", "--quiet"])
        if rc != 0:
            print("RIPRISTINO FALLITO dopo %s" % mid)
            return 3
        righe.append((mid, descr, "%d rossi" % len(rossi), rossi))
        print("%s | %s | %d rossi" % (mid, descr, len(rossi)), flush=True)
    with open("AUDIT_2026-10-06/strumenti/mutazioni_media_under_giro4_esito.json", "w",
              encoding="utf-8") as fh:
        json.dump([{"id": m, "mutazione": d, "esito": e, "rossi": r}
                   for m, d, e, r in righe], fh, indent=1, ensure_ascii=True)
    sopravvissute = [r for r in righe if not r[2].endswith("rossi") or r[2].startswith("0 ")]
    print()
    print("SOPRAVVISSUTE O NON APPLICABILI: %s"
          % (", ".join(r[0] for r in sopravvissute) or "nessuna"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
