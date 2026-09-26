"""Falsificazione K1 (26/09/2026): ogni mutazione rimette il difetto (o una sua
variante) e i test di `test_valuta_k1_2026_09_26.py` devono tornare ROSSI.

Uso (dalla radice del worktree, SENZA timeout: non interrompere mai):
    set SUPABASE_URL=http://127.0.0.1:9 & set SUPABASE_KEY=x & set SUPABASE_SERVICE_ROLE_KEY=x
    python AUDIT_2026-09-26/falsifica_k1.py

Ogni file mutato viene ripristinato dal contenuto originale in memoria e
verificato con sha256 PRIMA della mutazione successiva e alla fine.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

TEST = "Betfair/stream/tests/test_valuta_k1_2026_09_26.py"

MUTAZIONI = [
    ("M1 scanner senza conversione nel drain", "Betfair/safe_strategy/stream.py",
     "                _valuta.converti_libro(b, _valuta.CAMBIO)\n",
     "                pass\n",
     "test_scanner_stream_converte_alla_fonte or test_contratto_ogni_fonte"),
    ("M2 banco senza conversione", "Betfair/stream/backtest/banco_comune.py",
     "    _valuta.monta_su_flumine(quadro, _valuta.cambio_banco())\n",
     "    pass\n",
     "test_parita_runner_banco or test_contratto_il_banco"),
    ("M3 runner calcio senza middleware", "Betfair/stream/runner.py",
     "            _valuta.monta_su_flumine(framework)\n",
     "            pass\n",
     "test_contratto_ogni_fonte"),
    ("M4 runner tennis senza middleware", "Betfair/stream/tennis_live/tennis_runner.py",
     "            _valuta.monta_su_flumine(framework)\n",
     "            pass\n",
     "test_contratto_ogni_fonte"),
    ("M5 sessione scalper senza middleware", "Betfair/stream/scalper/scalper_session.py",
     "        _valuta.monta_su_flumine(framework)\n",
     "        pass\n",
     "test_contratto_ogni_fonte"),
    ("M6 middleware in coda (dopo il SimulatedMiddleware)", "Betfair/stream/valuta.py",
     "    lista.insert(0, mw)\n",
     "    lista.append(mw)\n",
     "test_runner_live_middleware_primo or test_monta_su_flumine or test_parita_runner_banco"),
    ("M7 livelli modificati IN PLACE (cache bflw corrotta)", "Betfair/stream/valuta.py",
     "        nuovo = dict(liv)\n",
     "        nuovo = liv\n",
     "test_la_cache_di_betfairlightweight"),
    ("M8 runner condiviso riconvertito (niente marcatore)", "Betfair/stream/valuta.py",
     "            if getattr(runner, \"_k1_eur\", False) is True:\n                continue\n",
     "            pass\n",
     "test_runner_condiviso"),
    ("M9 lista gia' convertita riconvertita", "Betfair/stream/valuta.py",
     "    if livelli is None or isinstance(livelli, _LivelliEur):\n",
     "    if livelli is None:\n",
     "test_lista_gia_convertita"),
    ("M10 libro gia' convertito riconvertito", "Betfair/stream/valuta.py",
     "        if getattr(market_book, \"size_gbp_convertite\", False):\n            return market_book\n",
     "        pass\n",
     "test_adattatore_idempotente"),
    ("M11 cambio NON congelato per mercato", "Betfair/stream/valuta.py",
     "            r = self._per_mercato.get(mid)\n",
     "            r = None\n",
     "test_cambio_congelato"),
    ("M12 rete giu' con cache -> CRITICAL invece di WARN", "Betfair/stream/valuta.py",
     "                if self.fonte in (\"betfair\", \"cache\"):\n",
     "                if False:\n",
     "test_rete_giu_con_cache"),
    ("M13 cambio implausibile accettato", "Betfair/stream/valuta.py",
     "                if not (_BANDA_PLAUSIBILE[0] <= v <= _BANDA_PLAUSIBILE[1]):\n",
     "                if False:\n",
     "test_cambio_implausibile"),
    ("M14 cache non scritta", "Betfair/stream/valuta.py",
     "        self._scrivi_cache()\n        logger.info",
     "        pass\n        logger.info",
     "test_cambio_letto_da_betfair"),
    ("M15 REST convertito due volte", "Betfair/safe_strategy/service.py",
     "                self._apply_market_book(b)\n",
     "                self._apply_market_book(_valuta.converti_libro(b, _valuta.CAMBIO))\n",
     "test_scanner_rest_non_si_converte"),
    ("M16 total_matched non convertito", "Betfair/stream/valuta.py",
     "        market_book.total_matched = _importo(getattr(market_book, \"total_matched\", None), r)\n",
     "        pass\n",
     "test_adattatore_converte or test_scanner_stream_converte"),
    ("M17 riga del feed senza valuta", "Betfair/safe_strategy/service.py",
     "                        \"valuta\": _valuta.VALUTA_CONTO,\n                        # ts dell'ultimo CAMBIO delle quote 1X2",
     "                        # ts dell'ultimo CAMBIO delle quote 1X2",
     "test_la_riga_del_feed"),
    ("M18 marcatore del recorder tolto", "Betfair/stream/recorder.py",
     "        out[\"valuta\"] = getattr(market_book, \"valuta\", None)\n",
     "        pass\n",
     "test_serialize_book_dichiara"),
    ("M19 cambio del banco non fisso (cache/Betfair)", "Betfair/stream/valuta.py",
     "    return CambioGbpEur(fisso=v)\n",
     "    return CambioGbpEur()\n",
     "test_cambio_del_banco_fisso"),
]


def sha(p: str) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main() -> int:
    py = sys.executable
    originali = {}
    esiti = []
    for nome, file, vecchio, nuovo, filtro in MUTAZIONI:
        if file not in originali:
            originali[file] = (open(file, "rb").read(), sha(file))
        testo = originali[file][0].decode("utf-8")
        if "\r\n" in testo:   # checkout Windows (CRLF)
            vecchio = vecchio.replace("\n", "\r\n")
            nuovo = nuovo.replace("\n", "\r\n")
        if testo.count(vecchio) != 1:
            esiti.append((nome, "MUTAZIONE NON APPLICABILE", testo.count(vecchio)))
            continue
        try:
            open(file, "wb").write(testo.replace(vecchio, nuovo).encode("utf-8"))
            r = subprocess.run([py, "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider",
                                "-k", filtro], capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            ultima = (r.stdout.strip().splitlines() or ["?"])[-1]
            esiti.append((nome, "ROSSO" if r.returncode != 0 else "VERDE (!!)", ultima))
        finally:
            open(file, "wb").write(originali[file][0])
            assert sha(file) == originali[file][1], f"{file} NON ripristinato"
    for file, (_b, h) in originali.items():
        assert sha(file) == h, f"{file} NON ripristinato"
    for e in esiti:
        print(" | ".join(str(x) for x in e))
    print("file ripristinati e verificati (sha256):", len(originali))
    return 0 if all(e[1] == "ROSSO" for e in esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
