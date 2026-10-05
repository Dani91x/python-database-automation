"""Falsificazione del secondo giro della modalita' <<media under>> (05/10/2026).

Stessa macchina del primo giro (``mutazioni_media_under.py``: UNA sostituzione di
testo per volta, deve comparire esattamente una volta; test; ripristino con
``git checkout -- <file>`` e verifica ``git diff --quiet``), con le mutazioni
del secondo giro e i test dei due giri.

Uso (dalla radice del repo, albero pulito):
    python AUDIT_2026-10-05/strumenti/mutazioni_media_under_giro2.py [id ...]

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutazioni_media_under as G1  # noqa: E402

MU = G1.MU
RR = G1.RR
SS = G1.SS
CE = G1.CE

PY = ["python", "-m", "pytest",
      "Betfair/stream/tests/test_scalper_media_under_2026_10_05.py",
      "Betfair/stream/tests/test_scalper_media_under_giro2_2026_10_05.py",
      "-q", "-p", "no:cacheprovider", "-p", "no:randomly"]

# (id, file, vecchio, nuovo, descrizione)
MUTAZIONI: List[Tuple[str, str, str, str, str]] = [
    # --- 2.1: le due mutazioni sopravvissute alla verifica del revisore
    ("G1", MU, '''        su = ticks_between(self._ultimo_ingresso, bb)
        if su is None or su < self.par.tick_rientro:
            return''',
     '''        su = ticks_between(self._ultimo_ingresso, bb)
        if su is None or su < 0:
            return''',
     "_forse_rientro decide il rientro anche con la quota salita meno di N tick"),
    ("G2", MU, '''                if abs(float(b.order_type.price) - c) < 1e-9 and abs(resto - voluto) <= 0.01:
                    return''',
     '''                if True:
                    return''',
     "_assicura_banca: la banca viva e' sempre <<giusta>> (mai riallineata)"),
    ("G3", MU, '''                if abs(float(b.order_type.price) - c) < 1e-9 and abs(resto - voluto) <= 0.01:
                    return''',
     '''                if abs(float(b.order_type.price) - c) < 1e-9:
                    return''',
     "_assicura_banca: confronta solo la quota, non l'importo"),
    # --- 2.2: il referto dei replay della modalita'
    ("G4", RR, '''            if media:
                b.ref.azioni += int((getattr(s, "stats", {}) or {}).get("ordini", 0) or 0) \\
                    - prima_m''',
     '''            if False:
                b.ref.azioni += int((getattr(s, "stats", {}) or {}).get("ordini", 0) or 0) \\
                    - prima_m''',
     "le azioni del referto non contano gli ordini della modalita'"),
    ("G5", RR, '''    if not ordini_m:
        # un replay della modalita' senza un solo ordine NON e' un OK''',
     '''    if False:
        # un replay della modalita' senza un solo ordine NON e' un OK''',
     "uno scenario senza ordini della modalita' esce OK invece di NE"),
    ("G6", RR, '''        elif pari and con_abb:
            esito, lordo = "CHIUSO", min(pos.se_vince, pos.se_perde)''',
     '''        elif pari and con_abb:
            esito, lordo = "CHIUSO", max(pos.se_vince, pos.se_perde) + 0.05''',
     "riepilogo: profitto del ciclo chiuso sbagliato"),
    ("G7", RR, '''    comm = max(lordo_tot, 0.0) * float(commissione)''',
     '''    comm = abs(lordo_tot) * float(commissione)''',
     "riepilogo: commissione anche su un lordo negativo"),
    ("G8", RR, '''            e = es[n] if n < len(es) else {}''',
     '''            e = es[n + 1] if n + 1 < len(es) else {}''',
     "riepilogo: importo esatto del rientro preso dal rientro sbagliato"),
    ("G9", RR, '''        i = max([0] + [n for n, t in enumerate(inizi) if t <= nato])''',
     '''        i = 0''',
     "riepilogo: tutti gli ordini in un solo ciclo"),
    ("G10", MU, '''        if (sb or 0.0) < self.par.min_size or (sl or 0.0) < self.par.min_size:
            return "liquidita"''',
     '''        if (sb or 0.0) < self.par.min_size or (sl or 0.0) < self.par.min_size:
            return "spread"''',
     "motivo di non ingresso con il nome sbagliato"),
    ("G11", MU, '''        motivo = self._perche_non_entra(now, bb, bl, sb, sl)
        if motivo is not None:
            self._conta_non_ingresso(motivo)
            return''',
     '''        motivo = self._perche_non_entra(now, bb, bl, sb, sl)
        if motivo is not None:
            return''',
     "motivi di non ingresso mai contati"),
    ("G12", MU, '''        if motivo is not None:
            self._conta_non_ingresso(motivo)
            return
        prezzo''',
     '''        if motivo is not None and motivo != "flusso":
            self._conta_non_ingresso(motivo)
            return
        prezzo''',
     "un filtro (flusso) non piu' bloccante"),
    # --- 2.3: gli ordini del conto nel riquadro
    ("G13", SS, '''    if session_paper:
        return "prova"''',
     '''    if session_paper and False:
        return "prova"''',
     "in prova la lettura degli ordini del conto si fa"),
    ("G14", SS, '''        if not media.posizione_aperta():
            media.imposta_ordini_conto(None, "")
            return "chiusa"''',
     '''        if False:
            media.imposta_ordini_conto(None, "")
            return "chiusa"''',
     "lettura degli ordini del conto anche a posizione chiusa"),
    ("G15", MU, '''SORGENTI_A_MANO = ("account", "runner")''',
     '''SORGENTI_A_MANO = ("account", "runner", "scalper")''',
     "le righe dello specchio della sessione contate come ordini a mano"),
    ("G16", MU, '''            if selection_id is None or int(r.get("selection_id")) != int(selection_id):
                continue''',
     '''            if selection_id is None:
                continue''',
     "righe a mano di altre selezioni (l'Over) nel riquadro"),
    ("G17", MU, '''        if str(r.get("side") or "").lower() == "back":
            w += m * (q - 1.0)''',
     '''        if str(r.get("side") or "").lower() == "lay":
            w += m * (q - 1.0)''',
     "righe a mano: punta e banca scambiate"),
    ("G18", MU, '''            fonte, pos_r = self._fonte_e_posizione(pos)
            self.chiusura = riquadro_chiusura(
                pos_r,''',
     '''            fonte, pos_r = self._fonte_e_posizione(pos)
            self.chiusura = riquadro_chiusura(
                pos,''',
     "riquadro: le righe a mano lette ma non usate"),
    ("G19", MU, '''        if c.get("errore"):
            return ("%s (lettura degli ordini del conto fallita alle %s: %s)"
                    % (FONTE_SOLO_BOT, c.get("ora"), str(c["errore"])[:80]), pos)''',
     '''        if c.get("errore"):
            return FONTE_SOLO_BOT, pos''',
     "lettura fallita non detta nel riquadro"),
    ("G20", MU, '''            fonte, pos_r = self._fonte_e_posizione(pos)''',
     '''            fonte, pos_r = self._fonte_e_posizione(pos)
            s["totale_puntato"] = round(pos_r.puntato, 2)''',
     "le righe a mano entrano nelle stats della modalita' (non solo nel riquadro)"),
    ("G21", CE, '''    if o.prova and o.letture_conto > 0:''',
     '''    if o.prova and o.letture_conto > 1:''',
     "M10 muto su UNA lettura in prova"),
    ("G22", CE, '''    if o.letture_conto > o.battiti + 1:''',
     '''    if o.letture_conto > 2 * o.battiti + 1:''',
     "M10 muto su piu' letture per battito"),
    # --- 3: gli scenari dichiarati
    ("G23", RR, '''        params.update(dict(SCENARI_MEDIA_VARIANTI.get(scenario, ({}, None, ""))[0]))''',
     '''        pass''',
     "le varianti dichiarate non cambiano i parametri"),
    ("G24", RR, '''        return variante[1] or scenario''',
     '''        return scenario''',
     "le varianti di guasto non armano il guasto"),
    ("G25", RR, '''    if callable(getattr(s, "posizione_aperta", None)):
        return bool(s.posizione_aperta())''',
     '''    if False:
        return bool(s.posizione_aperta())''',
     "il guasto non aspetta la posizione aperta della modalita'"),
    # --- difetto trovato dal replay (giro 2): la lettura e il battito
    ("G26", SS, '''        ora = datetime.fromtimestamp(float(time.time())).strftime("%H:%M:%S")''',
     '''        ora = time.strftime("%H:%M:%S", time.localtime(time.time()))''',
     "la lettura torna a usare time.strftime (il difetto trovato dal replay)"),
    ("G27", SS, '''    except Exception as ex:  # noqa: BLE001 - mai rompere il battito: lo dice il riquadro''',
     '''    except ValueError as ex:  # noqa: BLE001 - mai rompere il battito: lo dice il riquadro''',
     "un'eccezione della lettura arriva al ciclo del battito"),
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
    print()
    print("| # | mutazione | test rossi |")
    print("|---|---|---|")
    for mid, descr, esito, rossi in righe:
        nomi = ", ".join(r.split("::")[-1] for r in rossi[:4]) + (" ..." if len(rossi) > 4 else "")
        print("| %s | %s | %s: %s |" % (mid, descr, esito, nomi))
    with open("AUDIT_2026-10-05/strumenti/mutazioni_media_under_giro2_esito.json", "w",
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
