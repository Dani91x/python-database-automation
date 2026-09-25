"""FALSIFICAZIONE dei test D5 (25/09): ogni mutazione del codice di produzione
deve far diventare ROSSO almeno un test. Il file originale si ripristina dal
contenuto in MEMORIA e se ne verifica l'hash (mai `git checkout`).

Uso (dalla radice del worktree, sandbox DB):
  SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x \\
    python AUDIT_2026-09-25/sonde/mutazioni_safe_d5.py
"""
from __future__ import annotations

import hashlib
import subprocess
import sys

PY = sys.executable
T_D5 = "Betfair/safe_strategy/tests/test_safe_d5_2026_09_25.py"
T_Q = "Betfair/safe_strategy/tests/test_safe_q1_q4_q5_2026_09_25.py"
T_SEL = "Betfair/safe_strategy/tests/test_selezione_esatto_2026_09_16.py"
VETO = "Betfair/safe_strategy/veto_campionati.py"
ENG = "Betfair/safe_strategy/engine.py"
SEL = "Betfair/safe_strategy/selezione.py"
SVC = "Betfair/safe_strategy/service.py"
DB = "Betfair/safe_strategy/db.py"
CERT = "Betfair/safe_strategy/certificazione.py"
TS = "frontend/src/lib/vetoCampionati.ts"

MUT = [
    ("P1 'final' tolto dai round finali", VETO,
     'ROUND_FINALE: Tuple[str, ...] = ("final", "finals",',
     'ROUND_FINALE: Tuple[str, ...] = ("finals",', [T_D5]),
    ("P1 il round non si guarda (solo nome)", ENG,
     "    if fixture_round is not None:\n        if _veto.is_round_finale(fixture_round):",
     "    if False:\n        if _veto.is_round_finale(fixture_round):", [T_D5]),
    ("P1 il nome vale anche col round presente", ENG,
     "    elif _veto.nome_indica_finale(event_name):",
     "    if _veto.nome_indica_finale(event_name):", [T_D5]),
    ("P1 piazzamenti contati come finali", VETO,
     "    if any(_contiene(tutto, p) for p in _PAROLE_PIAZZAMENTO):\n        return False",
     "    if False:\n        return False", [T_D5]),
    ("P1 semifinali dal nome contate come finali", VETO,
     "    return not any(p in parole for p in _PAROLE_NON_FINALE)",
     "    return True", [T_D5]),
    ("P1/P3 competizione assente zittisce anche la finale", ENG,
     '    etichetta = "Campionato non vietato dal corso"\n    if competition is not None:',
     '    etichetta = "Campionato non vietato dal corso"\n    if competition is None:\n'
     '        return None\n    if competition is not None:', [T_D5]),
    ("P4 femminile dai nomi squadra spento", ENG,
     "    if _veto.squadra_femminile(home) or _veto.squadra_femminile(away):",
     "    if False:", [T_D5]),
    ("P4 'w' in qualunque posizione", VETO,
     "    if testo.split()[-1] == SUFFISSO_SQUADRA_FEMMINILE:",
     "    if SUFFISSO_SQUADRA_FEMMINILE in testo.split():", [T_D5]),
    ("P5 soglia gol 5 invece di 4", SEL,
     "GOL_TANTI = 4 ", "GOL_TANTI = 5 ", [T_D5]),
    ("P5 partite non finite contate", SEL,
     '        if str(stato.get("short") or "").upper() not in STATI_FINITI:\n            continue',
     "        pass", [T_D5]),
    ("P5 gol dei supplementari al posto dei 90'", SEL,
     '        gh, ga = ft.get("home"), ft.get("away")',
     "        gh, ga = None, None", [T_D5]),
    ("P5 orientamento ignorato", SEL,
     '                int(fid), _orientamento_invertito(str(ev.get("name") or ""), fx))',
     "                int(fid), False)", [T_D5]),
    ("P5 scambio dei lati dimenticato", SEL,
     "    if invertita:\n        sub_casa, sub_ospite = sub_ospite, sub_casa",
     "    if False:\n        sub_casa, sub_ospite = sub_ospite, sub_casa", [T_D5]),
    ("P5 niente cache: rilegge a ogni giro", SEL,
     "                        if eid in vivi and ab[0] not in self._schede})",
     "                        if eid in vivi})", [T_D5]),
    ("P5 nessuna pausa dopo un errore DB", SEL,
     "            self._pausa_fino = self._orologio() + _ERRORE_PAUSA_S",
     "            self._pausa_fino = 0.0", [T_D5]),
    ("P5 lo scanner non pubblica il round", SVC,
     '                    payload["fixture_round"] = self.schede.round(eid)',
     '                    payload["fixture_round"] = None', [T_D5]),
    ("P5 lo scanner legge l'atlante come prima", SVC,
     '                    payload["selection_hint"] = self.schede.hint(eid)',
     '                    payload["selection_hint"] = _selezione.hint(home, away)', [T_D5, T_SEL]),
    ("P5 minimo di scontri ignorato", ENG,
     "            if incontri < min_meetings:", "            if False:", [T_D5]),
    ("P5 chiave vecchia 2-2/3-3 letta", ENG,
     '    tanti = num_or_none(h.get("h2h_many_goals"))',
     '    tanti = num_or_none(h.get("h2h_big_draws"))', [T_D5, T_SEL]),
    ("P5 soglia 0,58 cambiata", ENG,
     '        "h2hManyGoalsRateMax": 0.58,', '        "h2hManyGoalsRateMax": 0.12,', [T_D5, T_SEL]),
    ("P5 E10 senza il minimo di scontri", CERT,
     "              if incontri is not None and incontri >= minimo and incontri > 0",
     "              if incontri is not None and incontri > 0", [T_D5]),
    ("P5 query con tutto raw_json", DB,
     '    "fixture_id,"\n    "h2h:raw_json->response->0->h2h,"',
     '    "fixture_id,raw_json,"\n    "h2h:raw_json->response->0->h2h,"', [T_D5]),
    ("P6 forze non dichiarate", ENG,
     "    if forze is not None:\n        parti.append(forze)",
     "    if False:\n        parti.append(forze)", [T_D5]),
    ("P7 bordo 1,20 incluso", ENG,
     "    if q_fav < fav_super_max and leader != fav:",
     "    if q_fav <= fav_super_max and leader != fav:", [T_D5]),
    ("P7 anche il super favorito escluso", ENG,
     "    if q_fav < fav_super_max and leader != fav:",
     "    if q_fav < fav_super_max:", [T_D5]),
    ("P7 si legge ancora leaderPreMax", ENG,
     '            "favSuperMax": _num(t.get("favSuperMax"), d["tennis"]["favSuperMax"]),',
     '            "favSuperMax": _num(t.get("leaderPreMax"), d["tennis"]["favSuperMax"]),', [T_D5]),
    ("P7 si guarda il leader invece del favorito", ENG,
     "    fav = 1 if q1 < q2 else 2", "    fav = 1 if q1 > q2 else 2", [T_D5]),
    ("P2 Bolivia di nuovo in lista", VETO,
     "    # BOLIVIA: tolta.",
     '    VoceVeto(codice="bolivia", nome="campionato boliviano", citazione="x",\n'
     '             frasi=("bolivian", "bolivia")),\n    # BOLIVIA: tolta.', [T_D5, T_Q]),
    ("P1 coppe di nuovo in lista", VETO,
     "    # COPPE: NON sono una voce.",
     '    VoceVeto(codice="coppe", nome="coppe", citazione="x", frasi=("cup", "coppa")),\n'
     "    # COPPE: NON sono una voce.", [T_D5, T_Q]),
    ("TS lista femminile divergente", TS,
     "    'women', 'womens', 'ladies',", "    'women', 'womens', 'ladies', 'dames',", [T_D5]),
]


def _hash(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    rosse = 0
    filtro = sys.argv[1:]            # facoltativo: sottostringhe del nome
    scelte = [m for m in MUT if not filtro or any(f in m[0] for f in filtro)]
    for nome, path, vecchio, nuovo, tests in scelte:
        orig = open(path, "rb").read()
        h0 = _hash(orig)
        testo = orig.decode("utf-8")
        if "\r\n" in testo:          # file con fine riga CRLF
            vecchio, nuovo = vecchio.replace("\n", "\r\n"), nuovo.replace("\n", "\r\n")
        if testo.count(vecchio) != 1:
            print(f"[??] {nome}: frammento trovato {testo.count(vecchio)} volte")
            continue
        try:
            open(path, "wb").write(testo.replace(vecchio, nuovo).encode("utf-8"))
            r = subprocess.run([PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
                                "-m", "not cert", *tests], capture_output=True, text=True)
            rossa = r.returncode != 0
        finally:
            open(path, "wb").write(orig)
            assert _hash(open(path, "rb").read()) == h0, f"RIPRISTINO FALLITO {path}"
        rosse += rossa
        print(f"[{'ROSSA' if rossa else 'VIVA!'}] {nome}")
    print(f"\n{rosse}/{len(scelte)} mutazioni rosse")
    return 0 if rosse == len(scelte) else 1


if __name__ == "__main__":
    sys.exit(main())
