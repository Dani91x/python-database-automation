"""Falsificazione dei test di Q7/Q8/Q9/Q10/Q12 (25/09): ogni mutazione deve
far diventare ROSSO almeno un test; poi il file torna identico (hash).

Ripristino dal CONTENUTO in memoria, mai `git checkout`. Stesso schema di
`mutazioni_safe_q1_q4_q5.py`. Filtro opzionale: primo argomento = pezzo del nome.

Lancio (sandbox): SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x
SUPABASE_KEY=x python AUDIT_2026-09-25/sonde/mutazioni_safe_q7_q12.py [filtro]
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
TEST = [
    "Betfair/safe_strategy/tests/test_safe_q7_q12_2026_09_25.py",
    "Betfair/safe_strategy/tests/test_selezione_esatto_2026_09_16.py",
    "Betfair/safe_strategy/tests/test_certificazione_c3_2026_09_16.py",
    "Betfair/safe_strategy/tests/test_cert_2026_09_13.py",
    "Betfair/stream/tests/test_banco_comune_2026_09_16.py",
]
EN = "Betfair/safe_strategy/engine.py"
BS = "Betfair/safe_strategy/bot_service.py"

MUTAZIONI = [
    # --- Q7
    ("Q7 dato assente torna n/d (blocca)", EN,
     'return ConditionCheck("h2hDifesa", etichetta, SELEZIONE_DATO_ASSENTE, True)',
     'return ConditionCheck("h2hDifesa", etichetta, "n/d", None)'),
    ("Q7 una parte assente blocca", EN,
     "ok = h2h_ok is not False and dif_ok is not False",
     "ok = bool(h2h_ok) and bool(dif_ok)"),
    ("Q7 default spento", EN,
     '"requireSelection": True,', '"requireSelection": False,'),
    ("Q7 difesa della BANCATA", EN,
     'avversaria = "away" if lato_bancato == "home" else "home"\n    subiti = num_or_none(subiti_da.get(avversaria))\n    h2h_ok',
     'avversaria = lato_bancato\n    subiti = num_or_none(subiti_da.get(avversaria))\n    h2h_ok'),
    ("Q7 E10 accetta n/d", "Betfair/safe_strategy/certificazione.py",
     "    if ck.ok is None:\n        return (\"il check della selezione",
     "    if False:\n        return (\"il check della selezione"),
    # --- Q8
    ("Q8 guardia tolta", BS,
     "        if oltre is not None:\n", "        if False:\n"),
    ("Q8 minuto di uscita escluso (>)", BS,
     "return (m, uscita) if m >= uscita else None",
     "return (m, uscita) if m > uscita else None"),
    ("Q8 minuto di uscita fisso 80", BS,
     'return {v: int(xp[f"{v}_exit_minute"]) for v in _VARIANTI_CON_USCITA_A_TEMPO}',
     'return {v: 80 for v in _VARIANTI_CON_USCITA_A_TEMPO}'),
    # --- Q9
    ("Q9 guardia tolta", BS,
     "        if _variante_gia_entrata(traded_s, event_id, variant):\n",
     "        if False:\n"),
    ("Q9 prefisso senza separatore", BS,
     'prefisso = f"{eid}:{variant}:"', 'prefisso = f"{eid}:{variant}"'),
    ("Q9 evento ignorato", BS,
     "if str(ev_id) == eid and str(k).startswith(prefisso):",
     "if str(k).split(':')[1:2] == [variant] or str(k).startswith(prefisso):"),
    # --- Q10
    ("Q10 bande tolte dalla punta", EN,
     "    # Q10 (25/09): bande pre-partita della BASE (stessa funzione, stessi numeri)\n    checks.extend(pre_bands_checks(ctx.pre_match, fav, bande))",
     "    pass"),
    ("Q10 punta ignora i parametri della base", EN,
     'evaluate_punta(ctx, params["punta"], params["base"]),',
     'evaluate_punta(ctx, params["punta"]),'),
    # --- Q12
    ("Q12 in gioco non si congela", "Betfair/safe_strategy/scanner.py",
     "    if inplay:\n        return prev\n    if not odds:\n        return prev\n    coppia = {}",
     "    if not odds:\n        return prev\n    coppia = {}"),
    ("Q12 lo scanner non congela il tennis", "Betfair/safe_strategy/service.py",
     "else scanner.freeze_pre_ko_tennis)", "else (lambda prev, *_a, **_k: prev))"),
    ("Q12 riga tennis senza pre_ko", "Betfair/safe_strategy/service.py",
     '                        "pre_ko": ev.get("pre_ko"),\n                    }\n                sig',
     '                    }\n                sig'),
    ("Q12 lato del leader invertito", EN,
     'q_pre = ctx.pre_match["p1"] if leader == 1 else ctx.pre_match["p2"]',
     'q_pre = ctx.pre_match["p2"] if leader == 1 else ctx.pre_match["p1"]'),
    ("Q12 dato assente blocca", EN,
     'checks.append(ConditionCheck("leaderPre", pre_label, TENNIS_PRE_ASSENTE, True))',
     'checks.append(ConditionCheck("leaderPre", pre_label, TENNIS_PRE_ASSENTE, None))'),
    ("Q12 default spento", EN, '"leaderPreMax": 4.0,', '"leaderPreMax": 0,'),
    ("Q12 la lettura DB scarta la coppia", "Betfair/safe_strategy/db.py",
     "usabile = is_usable_pre_ko(pre) or is_usable_pre_ko_tennis(pre)",
     "usabile = is_usable_pre_ko(pre)"),
    ("Q12 reidratazione solo calcio", "Betfair/safe_strategy/service.py",
     'if ev.get("sport") in ("calcio", "tennis")',
     'if ev.get("sport") == "calcio"'),
    ("Q12 reidratazione senza controllo di forma", "Betfair/safe_strategy/service.py",
     '            if not _pre_ko_usabile({"sport": ev.get("sport"), "pre_ko": pre}):\n                continue\n',
     ''),
]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _pytest() -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "pytest", *TEST, "-q", "-x",
                        "-p", "no:cacheprovider", "-m", "not cert"],
                       cwd=RADICE, capture_output=True, text=True)
    righe = [x for x in r.stdout.splitlines() if x.startswith("FAILED") or " passed" in x
             or " failed" in x]
    return r.returncode, " | ".join(righe[-3:])


def main() -> int:
    esiti = []
    filtro = sys.argv[1] if len(sys.argv) > 1 else ""
    for nome, rel, vecchio, nuovo in MUTAZIONI:
        if filtro and filtro not in nome:
            continue
        f = RADICE / rel
        raw = f.read_bytes()
        prima = _sha(f)
        testo = raw.decode("utf-8")
        crlf = "\r\n" in testo
        norm = testo.replace("\r\n", "\n")
        if norm.count(vecchio) != 1:
            esiti.append((nome, f"MUTAZIONE NON APPLICABILE ({norm.count(vecchio)} occorrenze)", ""))
            continue
        mutato = norm.replace(vecchio, nuovo, 1)
        if crlf:
            mutato = mutato.replace("\n", "\r\n")
        try:
            f.write_bytes(mutato.encode("utf-8"))
            rc, dove = _pytest()
        finally:
            f.write_bytes(raw)
        assert _sha(f) == prima, f"RIPRISTINO FALLITO su {rel}"
        esiti.append((nome, "ROSSO (ok)" if rc != 0 else "VERDE (test NON falsificato!)", dove))
    for nome, esito, dove in esiti:
        print(f"- {nome}: {esito}\n    {dove}")
    return 0 if all(e[1] == "ROSSO (ok)" for e in esiti) else 1


if __name__ == "__main__":
    raise SystemExit(main())
