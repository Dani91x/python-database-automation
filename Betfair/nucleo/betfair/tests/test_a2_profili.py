"""W1-A2 - i quattro ``ProfiloFlusso`` (``profili.py``) contro le costanti di OGGI, importate.

Ogni valore del profilo si confronta con la costante o la funzione del codice di
oggi che lo produce (``config_stream``, ``auto_follow.tetto_mercati``,
``GestoreFrammenti.da_ambiente``, ``tennis_runner``, ``iscrizione_a_caldo``,
``safe_strategy/stream``, il filtro di serie di flumine). Le costanti di oggi si
leggono all'IMPORT dall'ambiente: con l'ambiente cambiato il confronto gira in un
processo a parte (``subprocess``), mai ricaricando moduli in questo.

Anche il profilo del ladder (``ladder.profilo_ladder``) e' confrontato qui con
``config_stream``/``tennis_runner``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Dict

import pytest

from Betfair.nucleo.betfair import profili as P
from Betfair.nucleo.betfair.tests.test_a2_finti import radice_repo

#: lo script che, nell'ambiente dato, stampa i valori di OGGI e quelli nuovi
_SCRIPT = r'''
import json
from betfairlightweight.filters import streaming_market_data_filter
from flumine.strategy.strategy import DEFAULT_MARKET_DATA_FILTER
from Betfair.stream import config_stream as CS
from Betfair.stream import auto_follow as AF
from Betfair.stream import frammenti_mercato as FR
from Betfair.stream import runner as R
from Betfair.stream.tennis_live import tennis_runner as T
from Betfair.stream.tennis_live import iscrizione_a_caldo as IAC
from Betfair.safe_strategy import stream as SS
from Betfair.nucleo.betfair import profili as P
from Betfair.nucleo.betfair import ladder as L

class StreamSpia:
    def subscribe_to_markets(self, **kw):
        self.kw = kw
        return 1

spia = StreamSpia()
SS.StreamShard(None, 0)._subscribe(spia, ["1.1"])
pool = SS.MarketStreamPool(None)
g = FR.GestoreFrammenti.da_ambiente()
oggi = {
  "runner_calcio": {"campi": list(CS.STREAM_FIELDS), "ladder_levels": CS.LADDER_DEPTH,
      "conflate_ms": CS.STREAM_CONFLATE_MS or None, "heartbeat_ms": None,
      "mercati_per_connessione": AF.tetto_mercati(), "connessioni_max": g.max_conn,
      "riserva_connessioni": g.riserva,
      "filtro": streaming_market_data_filter(fields=list(CS.STREAM_FIELDS), ladder_levels=CS.LADDER_DEPTH)},
  "runner_tennis": {"campi": list(T.STREAM_FIELDS), "ladder_levels": T.LADDER_DEPTH,
      "conflate_ms": None, "heartbeat_ms": None,
      "mercati_per_connessione": IAC.tetto_mercati(), "connessioni_max": 1,
      "riserva_connessioni": 0,
      "filtro": streaming_market_data_filter(fields=list(T.STREAM_FIELDS), ladder_levels=T.LADDER_DEPTH)},
  "scansione": {"campi": spia.kw["market_data_filter"]["fields"],
      "ladder_levels": spia.kw["market_data_filter"]["ladderLevels"],
      "conflate_ms": spia.kw["conflate_ms"], "heartbeat_ms": spia.kw["heartbeat_ms"],
      "mercati_per_connessione": pool.per_conn, "connessioni_max": pool.max_conns,
      "riserva_connessioni": 0, "filtro": spia.kw["market_data_filter"]},
  "scalper_partita": {"campi": DEFAULT_MARKET_DATA_FILTER["fields"], "ladder_levels": 0,
      "conflate_ms": None, "heartbeat_ms": None,
      "mercati_per_connessione": 200, "connessioni_max": 1, "riserva_connessioni": 0,
      "filtro": DEFAULT_MARKET_DATA_FILTER},
}
nuovi = {}
for nome, p in P.tutti().items():
    nuovi[nome] = {"campi": list(p.campi), "ladder_levels": p.ladder_levels,
        "conflate_ms": p.conflate_ms, "heartbeat_ms": p.heartbeat_ms,
        "mercati_per_connessione": p.mercati_per_connessione,
        "connessioni_max": p.connessioni_max, "riserva_connessioni": p.riserva_connessioni,
        "filtro": P.filtro_dati(p)}
lad_oggi = {"calcio": [CS.LADDER_DEPTH, CS.LADDER_MAX_LEVELS, CS.LADDER_WOM_LEVELS, CS.LADDER_PUBLISH_SEC,
                       R.LADDER_MAX_LEVELS, R.LADDER_WOM_LEVELS],
            "tennis": [T.LADDER_DEPTH, T.LADDER_MAX_LEVELS, T.LADDER_WOM_LEVELS, T.LADDER_PUBLISH_SEC,
                       T.LADDER_MAX_LEVELS, T.LADDER_WOM_LEVELS]}
lad_nuovi = {}
for sport in ("calcio", "tennis"):
    q = L.profilo_ladder(sport)
    lad_nuovi[sport] = [q.profondita, q.livelli_max, q.livelli_wom, q.db_sec, q.livelli_max, q.livelli_wom]
print("ESITO" + json.dumps({"oggi": oggi, "nuovi": nuovi, "lad_oggi": lad_oggi, "lad_nuovi": lad_nuovi}))
'''

AMBIENTI = {
    "di_serie": {},
    "cambiato": {
        "LIVE_LADDER_DEPTH": "5", "LIVE_STREAM_CONFLATE_MS": "50", "LIVE_HARD_MARKET_CAP": "150",
        "RUNNER_CALCIO_STREAM_CONNS": "2", "RUNNER_CALCIO_STREAM_RISERVA": "3",
        "TENNIS_LADDER_DEPTH": "3", "TENNIS_TETTO_MERCATI": "99.7",
        "SAFE_STRATEGY_STREAM_CONNS": "6", "SAFE_STRATEGY_STREAM_MARKETS_PER_CONN": "500",
        "LIVE_LADDER_MAX_LEVELS": "4", "LIVE_LADDER_WOM_LEVELS": "2", "LIVE_LADDER_PUBLISH_SEC": "1.5",
        "TENNIS_LADDER_WOM_LEVELS": "5", "TENNIS_LADDER_PUBLISH_SEC": "3",
    },
    "fuori_limiti": {
        "AUTO_FOLLOW_TETTO_MERCATI": "250", "RUNNER_CALCIO_STREAM_CONNS": "12",
        "RUNNER_CALCIO_STREAM_RISERVA": "-3", "TENNIS_TETTO_MERCATI": "abc",
        "SAFE_STRATEGY_STREAM_CONNS": "abc", "SAFE_STRATEGY_STREAM_MARKETS_PER_CONN": "0",
    },
}


def _esegui(ambiente: Dict[str, str]) -> Dict[str, Any]:
    env = {k: v for k, v in os.environ.items()
           if not any(k.startswith(p) for p in ("LIVE_", "TENNIS_", "RUNNER_CALCIO_",
                                                 "SAFE_STRATEGY_", "AUTO_FOLLOW_"))}
    env.update(ambiente)
    esito = subprocess.run([sys.executable, "-c", _SCRIPT], capture_output=True, text=True,
                           timeout=180, cwd=radice_repo(), env=env)
    assert esito.returncode == 0, esito.stderr[-3000:]
    riga = [r for r in esito.stdout.splitlines() if r.startswith("ESITO")][-1]
    return json.loads(riga[len("ESITO"):])


@pytest.mark.parametrize("nome_amb", sorted(AMBIENTI))
def test_profili_uguali_ai_valori_di_oggi(nome_amb):
    d = _esegui(AMBIENTI[nome_amb])
    assert d["nuovi"] == d["oggi"]
    assert d["lad_nuovi"] == d["lad_oggi"]


def test_profili_in_questo_processo_e_riferimenti():
    """Nel processo dei test (ambiente corrente) e con i riferimenti file:riga."""
    from Betfair.safe_strategy import stream as SS
    from Betfair.stream import config_stream as CS
    from Betfair.stream.tennis_live import tennis_runner as T

    p = P.tutti()
    assert set(p) == set(P.NOMI_PROFILI)
    assert p["runner_calcio"].campi == tuple(CS.STREAM_FIELDS)
    assert p["runner_tennis"].campi == tuple(T.STREAM_FIELDS)
    assert (p["scansione"].conflate_ms, p["scansione"].heartbeat_ms) == (SS._CONFLATE_MS, SS._HEARTBEAT_MS)
    assert all(q.mercati_per_connessione <= 200 for n, q in p.items() if n != "scansione")
    assert [q.registra_raw for q in p.values()] == [True, True, False, False]
    with pytest.raises(ValueError):
        P.profilo("nessuno")  # type: ignore[arg-type]
    sorgente = open(P.__file__, encoding="utf-8").read()
    for rif in ("config_stream.py:47", "config_stream.py:87", "runner.py:2960",
                "frammenti_mercato.py:89", "tennis_runner.py:104", "safe_strategy/stream.py:66",
                "safe_strategy/stream.py:67", "safe_strategy/stream.py:275"):
        assert rif in sorgente


def test_valore_illeggibile_solleva_come_oggi():
    """Oggi ``int(os.getenv("LIVE_LADDER_DEPTH"))`` illeggibile fa cadere l'import
    del runner: il profilo solleva allo stesso modo (nessun valore inventato)."""
    with pytest.raises(ValueError):
        P.profilo("runner_calcio", {"LIVE_LADDER_DEPTH": "dieci"})
