# -*- coding: utf-8 -*-
"""Falsificazione di FIX_TENNIS_CHIUSURA (26/09): ogni mutazione rimette il
bug (o una sua variante) e il test nuovo DEVE tornare rosso. Il file mutato
si ripristina SEMPRE dal testo in memoria e si verifica con sha256.

Uso (dalla radice del worktree/repo):
  SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x \
    .venv/Scripts/python.exe AUDIT_2026-09-26/falsifica_tennis_chiusura.py
Non interrompere lo script (ripristina nel finally).
"""
from __future__ import annotations

import hashlib
import subprocess
import sys

TEST = "Betfair/stream/tennis_live/tests/test_tennis_chiusura_2026_09_26.py"
RUN = "Betfair/stream/tennis_live/tennis_runner.py"
PON = "Betfair/stream/tennis_live/tennis_bot_service.py"
AUTO = "Betfair/stream/tennis_live/auto_mode.py"

MUTAZIONI = [
    ("M1 capture senza process_closed_market", RUN,
     "        def process_closed_market(self, market: Any, market_book: Any) -> None:  # noqa: ARG002",
     "        def _niente_closed(self, market: Any, market_book: Any) -> None:  # noqa: ARG002"),
    ("M2 CLOSED resta in gioco", RUN,
     '''    if str(status).upper() == "CLOSED":
        # 26/09 (R-FA-1): un mercato chiuso non e' in gioco''',
     '''    if False:
        # 26/09 (R-FA-1): un mercato chiuso non e' in gioco'''),
    ("M3 CLOSED riscritto a ogni giro", RUN,
     "            chiusi.add(event_id)    # stato terminale scritto una volta",
     "            pass"),
    ("M4 chiusi svuotati al reset", RUN,
     "        self.follow_assenti_dal.clear()\n        # nuovo framework in arrivo",
     "        self.follow_assenti_dal.clear()\n        self.now_chiusi.clear()\n        # nuovo framework in arrivo"),
    ("M5 ponte solo CLOSED (niente rete)", PON,
     "        return st != \"OPEN\" and dal is not None and (ora - dal) >= _fine_fuori_feed_s()",
     "        return False"),
    ("M6 rete chiude anche a mercato OPEN", PON,
     "        return st != \"OPEN\" and dal is not None and (ora - dal) >= _fine_fuori_feed_s()",
     "        return dal is not None and (ora - dal) >= _fine_fuori_feed_s()"),
    ("M7 rientro nel feed non azzera l'orologio", PON,
     "        if ev in nel_feed or ev not in auto_seguite:\n            _FUORI_FEED_DAL.pop(ev, None)",
     "        if ev not in auto_seguite:\n            _FUORI_FEED_DAL.pop(ev, None)"),
    ("M8 scanner fermo non azzera l'orologio", PON,
     "    if not vivo:\n        _FUORI_FEED_DAL.clear()\n        return",
     "    if not vivo:\n        return"),
    ("M9 tetto senza le vive fuori feed (ponte)", PON,
     "                                            altre_vive=vive_fuori)",
     "                                            altre_vive=0)"),
    ("M10 tetto senza le vive fuori feed (auto_mode)", AUTO,
     "    posti = max(0, int(tetto) - len(tengo) - max(0, int(altre_vive)))",
     "    posti = max(0, int(tetto) - len(tengo))"),
    ("M11 soglia env ignorata", PON,
     '    raw = os.getenv("TENNIS_AUTO_FINE_FUORI_FEED_S", "").strip()',
     '    raw = ""'),
]


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def main() -> int:
    esiti = []
    for nome, path, old, new in MUTAZIONI:
        with open(path, encoding="utf-8", newline="") as fh:
            orig = fh.read()
        sha0 = _sha(orig)
        nl = "\r\n" if "\r\n" in orig else "\n"     # alcuni file sono CRLF
        old, new = old.replace("\n", nl), new.replace("\n", nl)
        if orig.count(old) != 1:
            esiti.append((nome, "ANCORA NON TROVATA"))
            continue
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(orig.replace(old, new))
            r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q",
                                "-p", "no:cacheprovider", "-x"],
                               capture_output=True, text=True)
            coda = (r.stdout.strip().splitlines() or [""])[-1]
            esiti.append((nome, ("ROSSO " if r.returncode != 0 else "VERDE(!) ") + coda))
        finally:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(orig)
            with open(path, encoding="utf-8", newline="") as fh:
                assert _sha(fh.read()) == sha0, "RIPRISTINO FALLITO: " + path
    for nome, e in esiti:
        print("%-48s %s" % (nome, e))
    return 0 if all(e.startswith("ROSSO") for _n, e in esiti) else 1


if __name__ == "__main__":
    raise SystemExit(main())
