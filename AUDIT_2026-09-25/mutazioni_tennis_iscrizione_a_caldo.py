# -*- coding: utf-8 -*-
"""Falsificazione dei test dell'ISCRIZIONE/ARMAMENTO A CALDO del runner tennis
(25/09): ogni mutazione del codice di produzione DEVE far diventare rosso il
test indicato.

Il file originale si ripristina dai BYTE letti in memoria (mai `git checkout`:
nel worktree di un delegato ha gia' cancellato lavoro, 23/09) e lo sha1 si
verifica dopo ogni mutazione.

Uso (dal worktree, con il sandbox del DB):
  SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x \
    python AUDIT_2026-09-25/mutazioni_tennis_iscrizione_a_caldo.py
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
T = "Betfair/stream/tennis_live/tests/test_tennis_iscrizione_a_caldo_2026_09_25.py"
RUN = "Betfair/stream/tennis_live/tennis_runner.py"
IAC = "Betfair/stream/tennis_live/iscrizione_a_caldo.py"

MUTAZIONI = [
    ("M1 follow_worker senza via a caldo", RUN,
     "    caldo = _caldo_attivo(flumine, session)\n    if caldo is not None:\n"
     "        with session.caldo_lock:\n            _allinea_follow_a_caldo",
     "    caldo = _caldo_attivo(flumine, session)\n    if False:\n"
     "        with session.caldo_lock:\n            _allinea_follow_a_caldo"),
    ("M2 bot_control senza armamento a caldo", RUN,
     "    caldo = _caldo_attivo(flumine, session)\n    da_armare",
     "    caldo = None\n    da_armare"),
    ("M3 filtro dello stream non aggiornato", IAC,
     "    stream.market_filter = filtro            # la riconnessione di flumine lo riusa\n",
     ""),
    ("M4 filtro delle strategie non aggiornato", IAC,
     "            strat.market_filter = filtro\n    return int(nuovo)",
     "            pass\n    return int(nuovo)"),
    ("M5 filtro non canonico (non ordinato)", IAC,
     "streaming_market_filter(market_ids=sorted({str(m) for m in market_ids}))",
     "streaming_market_filter(market_ids=list(dict.fromkeys(str(m) for m in market_ids)))"),
    ("M6 posizioni ignorate", RUN,
     "    if not market_id or flumine is None:\n        return False\n    try:\n"
     "        market = flumine.markets.markets.get(str(market_id))",
     "    return False\n    try:\n"
     "        market = flumine.markets.markets.get(str(market_id))"),
    ("M7 posizioni non ricontrollate nel ciclo di flumine", RUN,
     "usciti = [ev for ev in uscenti if not _evento_con_posizioni(fw, session, ev)]",
     "usciti = list(uscenti)"),
    ("M8 espulsione anche fra pari", IAC,
     "and e.priorita < n.priorita]", "and e.priorita <= n.priorita]"),
    ("M9 manuali espellibili", IAC,
     "        return self.in_uscita or not self.manuale\n", "        return True\n"),
    ("M10 tetto ignorato nel piano", IAC,
     "        if len(occupati) < int(tetto):\n", "        if True:\n"),
    ("M11 grazia d'uscita ignorata", RUN,
     "pronti = {ev for ev, t0 in assenti.items() if ora - t0 >= grazia}",
     "pronti = set(assenti)"),
    ("M12 sottoscrizione vuota permessa", IAC,
     '    if not ids:\n        raise ValueError("sottoscrizione vuota rifiutata")\n', ""),
    ("M13 client paper non passato a caldo", RUN,
     "                client_paper=caldo.client_paper,\n            )\n        except Exception as e:"
     "  # noqa: BLE001\n            logger.warning(\"[tennis-runner] arm a caldo KO",
     "                client_paper=None,\n            )\n        except Exception as e:"
     "  # noqa: BLE001\n            logger.warning(\"[tennis-runner] arm a caldo KO"),
    ("M14 modalita' LIVE a caldo in un runner PAPER", RUN,
     "_make_sink(ev, bot_key), caldo.data_filter, caldo.mode,",
     "_make_sink(ev, bot_key), caldo.data_filter, \"LIVE\","),
    ("M15 guardia d'avvio ignorata a caldo", RUN,
     'if esito.get("entrati") and not _gt.guardia_blocca():',
     'if esito.get("entrati"):'),
    ("M16 stream spurio non tolto", IAC,
     "        for s in nuovi:\n            try:\n                framework.streams._streams.remove(s)\n"
     "            except ValueError:\n                pass\n",
     ""),
    ("M17 bot della partita uscita non disabilitato", RUN,
     "                    _disable_strategy(st)\n                    disarmati.append((e, bk))",
     "                    disarmati.append((e, bk))"),
    ("M18 caldo che chiede anche la ricostruzione", RUN,
     "                _arma_a_caldo(flumine, session, caldo, da_armare)\n        return\n",
     "                _arma_a_caldo(flumine, session, caldo, da_armare)\n"),
    ("M19 build oltre il tetto", RUN,
     "    if len(visti) <= tetto:\n        return follows\n", "    return follows\n"),
    ("M20 tetto ignorato nel ciclo di flumine", RUN,
     "            if len(base) + len(entrano) < tetto:\n", "            if True:\n"),
    ("M21 lavoro annullato eseguito lo stesso", IAC,
     "            if self.annullato:\n                return\n", ""),
    ("M22 data_filter non verificato", IAC,
     "    if strat.market_data_filter != stream.market_data_filter:\n"
     "        raise ValueError(\"market_data_filter del bot diverso da quello dello stream\")\n",
     ""),
]


def sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()  # noqa: S324


def gira() -> int:
    return subprocess.run([sys.executable, "-m", "pytest", T, "-q", "-x",
                           "-p", "no:cacheprovider"], cwd=RADICE,
                          capture_output=True, text=True).returncode


def main() -> int:
    base = gira()
    print("base (codice intatto): %s" % ("VERDE" if base == 0 else "ROSSO"))
    if base != 0:
        return 2
    esiti = []
    for nome, rel, vecchio, nuovo in MUTAZIONI:
        p = RADICE / rel
        originale = p.read_bytes()
        firma = sha1(originale)
        crlf = b"\r\n" in originale
        v = vecchio.replace("\n", "\r\n") if crlf else vecchio
        n = nuovo.replace("\n", "\r\n") if crlf else nuovo
        vb, nb = v.encode("utf-8"), n.encode("utf-8")
        if originale.count(vb) != 1:
            esiti.append((nome, "NON TROVATA (%d)" % originale.count(vb)))
            continue
        try:
            p.write_bytes(originale.replace(vb, nb))
            rc = gira()
        finally:
            p.write_bytes(originale)
        ripristino = "sha1 ok" if sha1(p.read_bytes()) == firma else "SHA1 DIVERSO"
        esiti.append((nome, ("ROSSO (ok)" if rc != 0 else "VERDE = TEST CIECO")
                      + ", " + ripristino))
    for nome, e in esiti:
        print("%-52s %s" % (nome, e))
    dopo = gira()
    print("dopo (codice ripristinato): %s" % ("VERDE" if dopo == 0 else "ROSSO"))
    ok = all(e.startswith("ROSSO (ok), sha1 ok") for _n, e in esiti) and dopo == 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
