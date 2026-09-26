"""sintesi di un file JSON di verifica_omega_b.py (una riga per trade)"""
import json, sys
for r in json.load(open(sys.argv[1], encoding="utf8")):
    c = r["confronto_ricalcolo_vs_scritto"]
    g = r["cancello"]
    print(r["trade_id"], r["event_id"], r["runner"], r["price"], "min", r["minuto"], r["punteggio"],
          "| B:", r["esito_B"], {k: v[2] for k, v in c.items()},
          "| p_grezza %.6f p_fusa %.6f p_merc_impl %s w %s" % (r["p_modello_grezza"], r["audit_scritto"].get("p_fusa") or -1,
                                                           r["p_mercato_implicita_dalla_fusa"], r["peso_fusione_modello"]),
          "| emp", c["p_empirica"][0], c["n_empirico"][0],
          "| cancello:", r["tutto_il_cancello_vero"], {k: v[0] for k, v in g.items() if not v[0]},
          "| lambda_source", r["audit_scritto"].get("lambda_source"), "| scanner reg:", "scanner_registrato" in r)
