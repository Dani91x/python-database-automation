"""Analisi offline (nessuna rete, nessun DB) dei due giri di semantica_A: rapporto delle size
scan/book a prezzo uguale e stato mercato scan vs book."""
import json
import os
import statistics

QUI = os.path.dirname(os.path.abspath(__file__))
for f in ("semantica_A.json", "semantica_A_giro2.json"):
    d = json.load(open(os.path.join(QUI, f), encoding="utf-8"))
    rs = []
    for ist in d["istanti"]:
        for p in ist["partite"]:
            print(f, ist["k"], p["event_id"], "scan_mo_status", p["scan_mo_status"], "book", p["book_status"],
                  "scan_upd", p["scan_updated_at"], "eta", p["eta_scan_s_a_lettura_book"])
            for lato, c in p["confronto_quote"].items():
                s, b = c["scan"], c["book"]
                for side in ("back", "lay"):
                    if s[side] is not None and s[side] == b.get(side) and b.get(side + "_size"):
                        rs.append(s[side + "_size"] / b[side + "_size"])
    rs.sort()
    print(f, "rapporti size scan/book a prezzo uguale: n", len(rs), "mediana", round(statistics.median(rs), 4),
          "fra 0.855 e 0.865:", sum(1 for r in rs if 0.855 <= r <= 0.865))
