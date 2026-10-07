"""Esegue in serie le prove di applica_bot.esegui (la funzione del worker) e salva
gli esiti JSON. Argomenti: <radice worktree> <cartella uscita> <nome,...|tutti>."""
import json
import sys
import time

sys.path.insert(0, sys.argv[1])
from Betfair.stream.backtest import applica_bot  # noqa: E402

CALCIO = "/home/user/python-database-automation/_live_raw"
TENNIS = "/home/user/python-database-automation/_live_raw_tennis"
PROVE = {
    "media_clic_69": ({"bot": "scalper_calcio", "scenario": "media-under", "event_id": "35797769",
                       "dal_ms": 1783708200000, "clic_ms": [1783711500000]}, CALCIO),
    "media_clic_multi_69": ({"bot": "scalper_calcio", "scenario": "media-under", "event_id": "35797769",
                             "dal_ms": 1783708200000,
                             "clic_ms": [1783710154616, 1783711534616, 1783713934616]}, CALCIO),
    "media_presto_84": ({"bot": "scalper_calcio", "scenario": "media-under", "event_id": "35760084",
                         "dal_ms": 1782832000000}, CALCIO),
    "media_presto_69": ({"bot": "scalper_calcio", "scenario": "media-under", "event_id": "35797769",
                         "dal_ms": 1783701200000}, CALCIO),
    "tennis_scalper": ({"bot": "tennis_scalper", "scenario": "gate-aperto", "event_id": "35790089"}, TENNIS),
    "safe_tennis": ({"bot": "safe_tennis", "scenario": "base", "event_id": "35790089"}, TENNIS),
    "tennis_swing": ({"bot": "tennis_swing", "scenario": "gate-aperto", "event_id": "35790089"}, TENNIS),
    "mike_69": ({"bot": "mike", "scenario": "base", "event_id": "35797769"}, CALCIO),
    "safe_base_69": ({"bot": "safe_base", "scenario": "base", "event_id": "35797769"}, CALCIO),
    "scalper_base_69": ({"bot": "scalper_calcio", "scenario": "base", "event_id": "35797769"}, CALCIO),
    "omega_apertura_84": ({"bot": "omega", "scenario": "apertura", "event_id": "35760084"}, CALCIO),
}
scelte = list(PROVE) if sys.argv[3] == "tutti" else sys.argv[3].split(",")
for nome in scelte:
    params, cartella = PROVE[nome]
    t = time.time()
    try:
        esito = applica_bot.esegui(params, data_dir=cartella)
    except Exception as ex:  # noqa: BLE001
        print("ERRORE", nome, ex, flush=True)
        continue
    esito["_secondi"] = round(time.time() - t, 1)
    with open("%s/esito_%s.json" % (sys.argv[2], nome), "w") as f:
        json.dump(esito, f, ensure_ascii=True, indent=1, default=str)
    print("ok", nome, "ordini", esito["ordini"], "righe", len(esito["righe"]),
          "s", esito["_secondi"], "banco", esito.get("conto_banco"),
          "dichiarato", esito.get("conto_dichiarato"), "conferme", esito.get("conferme"),
          flush=True)
