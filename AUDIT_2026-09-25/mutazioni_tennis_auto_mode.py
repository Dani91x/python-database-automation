# -*- coding: utf-8 -*-
"""Falsificazione dei test del TENNIS AUTO-MODE (25/09): ogni mutazione del
codice di produzione DEVE far diventare rosso almeno un test indicato.

Il file originale si ripristina dal CONTENUTO letto in memoria (mai
`git checkout`: nel worktree di un delegato ha gia' cancellato lavoro, 23/09).

Uso (dal worktree, con il sandbox del DB):
  SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x \
    python AUDIT_2026-09-25/mutazioni_tennis_auto_mode.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
T_AUTO = "Betfair/stream/tennis_live/tests/test_tennis_auto_mode_2026_09_25.py"
T_BOT = "Betfair/stream/tennis_scalper/tests/test_uscite_manuali_bot_tennis_2026_09_25.py"

MUTAZIONI = [
    ("tetto ignorato", "Betfair/stream/tennis_live/auto_mode.py",
     "posti = max(0, int(tetto) - len(tengo))", "posti = 10 ** 6", T_AUTO),
    ("auto-mode mai attivo", "Betfair/stream/tennis_live/tennis_bot_service.py",
     "origine_ok = not _origine_assente_ora(ora)", "origine_ok = False", T_AUTO),
    ("done/error riarmabili", "Betfair/stream/tennis_live/tennis_bot_service.py",
     '_STATI_NON_RIARMABILI_AUTO = ("done", "error")', "_STATI_NON_RIARMABILI_AUTO = ()", T_AUTO),
    ("riarmo nella finestra di disarm", "Betfair/stream/tennis_live/tennis_bot_service.py",
     "if ev in seguite_a_mano or (ev, _bot) in in_chiusura:", "if ev in seguite_a_mano:", T_AUTO),
    ("follow chiusi anche se occupati", "Betfair/stream/tennis_live/tennis_bot_service.py",
     "auto_seguite - bersagli - occupati - seguite_a_mano", "auto_seguite - bersagli - seguite_a_mano",
     T_AUTO),
    ("mercato sempre chiuso", "Betfair/stream/tennis_live/tennis_bot_service.py",
     'return m is not None and str(m.get(ev) or "").upper() == "CLOSED"', "return True", T_AUTO),
    ("feed buono anche a scanner fermo", "Betfair/stream/tennis_live/tennis_bot_service.py",
     'esito["vivo"] = eta is not None and eta <= _SCANNER_VIVO_S', 'esito["vivo"] = True', T_AUTO),
    ("il tetto arriva al bot", "Betfair/stream/tennis_live/auto_mode.py",
     "out.pop(CHIAVE_TETTO, None)", "pass", T_AUTO),
    ("uscite propagate sempre", "Betfair/stream/tennis_live/tennis_bot_service.py",
     "if _AM.uscite_automatiche_riga(r) == bool(voluto):\n            continue",
     "if False:\n            continue", T_AUTO),
    ("restart mite che forza", "Betfair/stream/tennis_live/tennis_runner.py",
     "    if not forza:\n        _rinvio_senza_forzare(session, blockers, reason)\n        return False\n",
     "", T_AUTO),
    ("paper manuale azzerato", "Betfair/stream/tennis_live/tennis_runner.py",
     "if grace_expired and not is_live and not manuale:", "if grace_expired and not is_live:", T_AUTO),
    ("follow dal feed forzano", "Betfair/stream/tennis_live/tennis_runner.py",
     'if all(_AM.origine_follow(f) == _AM.ORIGINE_AUTO for f in new):', "if False:", T_AUTO),
    ("scalper manuale", "Betfair/stream/tennis_live/auto_mode.py",
     'BOT_USCITE_SEMPRE_AUTOMATICHE = frozenset({"tennis_scalper"})',
     "BOT_USCITE_SEMPRE_AUTOMATICHE = frozenset()", T_AUTO),
    ("uscite non passate al bot", "Betfair/stream/tennis_live/tennis_runner.py",
     "    strat.uscite_automatiche = _AM.uscite_automatiche_bot(bot_key, control)\n", "", T_AUTO),
    ("disarmo che forza", "Betfair/stream/tennis_live/tennis_runner.py",
     "        if serve_armare:\n", "        if True:\n", T_AUTO),
    ("armo che non forza", "Betfair/stream/tennis_live/tennis_runner.py",
     "                need_restart = True\n                serve_armare = True     # 25/09: c'e' qualcuno da armare\n",
     "                need_restart = True\n", T_AUTO),
    ("follow auto scritto senza origine", "Betfair/stream/tennis_live/tennis_db.py",
     '            raise ColonnaAssente("tennis_live_follow.origine") from e\n',
     '            row.pop("origine", None)\n'
     '            sb.table("tennis_live_follow").upsert(row, on_conflict="event_id").execute()\n'
     '            return\n', T_AUTO),
    ("uscite: niente ripiego senza colonna", "Betfair/stream/tennis_live/tennis_db.py",
     '        if "uscite_automatiche" not in payload \\\n'
     '                or not colonna_assente(e, "uscite_automatiche"):\n',
     '        if True:\n', T_AUTO),
    ("feed letto intero (score_raw)", "Betfair/stream/tennis_live/tennis_db.py",
     '+ ["%s:payload->%s" % (k, k) for k in _CHIAVI_FEED]))',
     '+ ["payload"]))', T_AUTO),
    ("FLB greena a uscite manuali", "Betfair/stream/tennis_scalper/tennis_flb_bot.py",
     "                and self.uscite_automatiche \\\n", "", T_BOT),
    ("swing: cancello anche sullo stop", "Betfair/stream/tennis_scalper/tennis_swing_bot.py",
     "        if hit or adverse or timed_out:",
     "        if not self.uscite_automatiche:\n            adverse = timed_out = False\n"
     "        if hit or adverse or timed_out:", T_BOT),
    ("swing: nessun cancello", "Betfair/stream/tennis_scalper/tennis_swing_bot.py",
     "        if hit and not self.uscite_automatiche:\n            hit = False\n", "", T_BOT),
    ("pro: target senza cancello", "Betfair/stream/tennis_scalper/tennis_pro_bot.py",
     "if auto and favorable and move_t >= target_t:", "if favorable and move_t >= target_t:", T_BOT),
    ("pro: scaglione senza cancello", "Betfair/stream/tennis_scalper/tennis_pro_bot.py",
     "if (auto and self.staged", "if (self.staged", T_BOT),
]


def gira(test: str) -> int:
    return subprocess.run([sys.executable, "-m", "pytest", test, "-q", "-x",
                           "-p", "no:cacheprovider"], cwd=RADICE,
                          capture_output=True, text=True).returncode


def main() -> int:
    esiti = []
    for nome, rel, vecchio, nuovo, test in MUTAZIONI:
        p = RADICE / rel
        originale = p.read_text(encoding="utf-8")
        if originale.count(vecchio) != 1:
            esiti.append((nome, "ANCORA NON TROVATA"))
            continue
        try:
            p.write_text(originale.replace(vecchio, nuovo), encoding="utf-8")
            rc = gira(test)
        finally:
            p.write_text(originale, encoding="utf-8")
        esiti.append((nome, "ROSSO (ok)" if rc != 0 else "VERDE = TEST CIECO"))
    for nome, e in esiti:
        print("%-40s %s" % (nome, e))
    return 0 if all(e == "ROSSO (ok)" for _n, e in esiti) else 1


if __name__ == "__main__":
    raise SystemExit(main())
