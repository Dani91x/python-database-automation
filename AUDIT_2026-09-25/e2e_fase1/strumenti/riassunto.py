"""Stampa il riassunto di uno o piu' Pxx_esito.json (sola lettura di file locali)."""
import json, os, sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
for nome in sys.argv[1:]:
    e = json.load(open(os.path.join(OUT, nome + "_esito.json"), encoding="utf-8"))
    print("=" * 100)
    print(nome, "ESITO:", e.get("esito"), "|", e["azione"][:160])
    for a in e["asserzioni"]:
        print(("  OK " if a["ok"] else "  KO ") + a["nome"], "|", json.dumps(a["ottenuto"], ensure_ascii=False)[:180],
              "" if a["ok"] else "| ATTESO " + json.dumps(a["atteso"], ensure_ascii=False)[:180])
    print("  RPC:", [(c["rpc"], c["esito"], c.get("errore", "")[:80]) for c in e["rpc"]])
    print("  sveglie:", len(e["sveglie"]), "| rifiuti:", e.get("rifiuti_non_gestiti"), "| bloccate:", e["bloccate"])
    print("  ripristino:", e.get("ripristino"))
    for p in e["passi"]:
        if any(s in p for s in ("TIMEOUT", "preparazione", "rifiut", "title", "a video", "chiavi", "messaggi", "C230",
                                "collaterale", "interrotto", "omegaParamsPatch", "P16a", "P16b")):
            print("  passo:", p[:300])
