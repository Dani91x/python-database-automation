"""FALSIFICAZIONE della forza pre-partita nel v4 (A* completo, 25/09/2026 notte).

Per ogni rottura: una sostituzione MINIMA nel codice di produzione, pytest sui
test nuovi (devono diventare ROSSI), ripristino DAL TESTO IN MEMORIA (mai git
checkout: incidente del 23/09) con verifica dell'hash. Alla fine la suite
torna verde. Uso (dalla radice del worktree):
    python AUDIT_2026-09-25/sonde/falsificazioni_forza_v4.py
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TEST = ["Betfair/stream/tests/test_atlante_v4_forza_id_squadra_2026_09_25.py"]
SC = "Betfair/stream/scalper/"
V4 = SC + "atlante_v4.py"
GA = SC + "genera_atlante.py"
AD = SC + "atlante_a_domanda.py"
BS = "Betfair/safe_strategy/bot_service.py"
OP = "Betfair/safe_strategy/opportunity.py"
N = "\r\n"

ROTTURE = [
    ("F1 eta del Poisson-Elo diverso dal banco", V4, "FORZA_ETA = 0.035", "FORZA_ETA = 0.02"),
    ("F2 passo: difesa aggiornata con l'errore sbagliato", V4,
     "    sq[a][1] = sq[a][1] + eta * eh", "    sq[a][1] = sq[a][1] + eta * ea"),
    ("F3 mu di lega mai aggiornata", V4, "    m[0] += alfa * (gh - m[0])", "    m[0] += 0.0"),
    ("F4 coda applicata nell'ordine di lettura (fixture_id)", V4,
     '    for v4, p in sorted(coda, key=lambda x: (str(x[1].date or ""), int(x[1].fixture_id))):',
     "    for v4, p in list(coda):"),
    ("F5 incrementale del generatore: ordine per lotto, non per giro", GA,
     "                          coda_forza=coda_forza)", "                          coda_forza=None)"),
    ("F6 aggiungi_v4 non accoda la forza", GA,
     "            coda_forza.append((v4, p))" + N, "            pass" + N),
    ("F7 doppio conteggio della forza", GA,
     "            coda_forza.append((v4, p))" + N,
     "            coda_forza.append((v4, p))" + N + "            coda_forza.append((v4, p))" + N),
    ("F8 consulta ignora gli id squadra", V4,
     "        if not (lambda_home and lambda_away) and home_id is not None and away_id is not None:",
     "        if False:"),
    ("F9 id squadra girati al ripiego v3", V4,
     "                           adesso=adesso, **kw_v3)" + N + "    k_req",
     "                           adesso=adesso, home_id=home_id, away_id=away_id, **kw_v3)" + N + "    k_req"),
    ("F10 rating nel file live a 3 decimali", V4,
     '"squadre": {t: [round(float(v[0]), 7), round(float(v[1]), 7), int(v[2])]',
     '"squadre": {t: [round(float(v[0]), 3), round(float(v[1]), 3), int(v[2])]'),
    ("F11 lambda casa con la difesa sbagliata", V4,
     "    lh = float(mu[0]) * math.exp(ah + da)", "    lh = float(mu[0]) * math.exp(ah + dh)"),
    ("F12 partita vecchia fuori ordine mai saltata", V4,
     "        if ritardo is not None and ritardo > FORZA_MAX_RITARDO_GIORNI:", "        if False:"),
    ("F13 squadra senza storico non dichiarata", V4, "            senza.append(lato)" + N, ""),
    ("F14 nota col punto decimale", V4,
     '    return f"{float(x):.2f}".replace(".", ",")', '    return f"{float(x):.2f}"'),
    ("F15 etichetta A* anche senza forza", V4,
     '    return "atlante v4 (A*)" if ((c or {}).get("forza") or {}).get("usata") else "atlante v4 (A1+A2)"',
     '    return "atlante v4 (A*)"'),
    ("F16 Safe: evaluate riceve il payload senza id", BS,
     '            opps = list(model.evaluate(payload_eval, sport="calcio", lambdas=lambdas,',
     '            opps = list(model.evaluate(payload, sport="calcio", lambdas=lambdas,'),
    ("F17 Safe: la riga del feed viene modificata", BS,
     '            payload_eval = dict(payload, home_team_id=lam["home_team_id"],' + N
     + '                                away_team_id=lam["away_team_id"])',
     '            payload.update(home_team_id=lam["home_team_id"], away_team_id=lam["away_team_id"])' + N
     + "            payload_eval = payload"),
    ("F18 Safe: gli id rileggono la finestra (lettura in piu')", BS,
     '        out.update(_ids_squadra_da_finestra(payload, state, out.get("league_id")))',
     '        out.update(_ids_squadra(_match_fixture(payload, _fixtures_window(db, now, state))))'),
    ("F19 Safe: fixture di un'altra lega accettata", BS,
     '        if league_id is not None and fx.get("league_id") is not None \\',
     '        if False and league_id is not None and fx.get("league_id") is not None \\'),
    ("F20 Safe: _hazard_check non passa gli id", OP,
     '            home_id=payload.get("home_team_id"), away_id=payload.get("away_team_id"),' + N, ""),
    ("F21 Safe: la fixture abbinata non porta gli id", BS, "            **_ids_squadra(fixture)}", "            }"),
    ("F22 Mike: il dossier non salva gli id", "Betfair/mike/dossier.py",
     '                out["home_team_id"] = _id_int(lam[3])', "                pass"),
    ("F23 Mike: fixture_lambdas senza con_squadre", "Betfair/mike/db.py",
     "return _sdb.get_fixture_prematch_lambdas(int(fixture_id), con_squadre=True)",
     "return _sdb.get_fixture_prematch_lambdas(int(fixture_id))"),
    ("F24 stream.db: select di Omega/runner cambiata", "Betfair/stream/db.py",
     "    if con_squadre:" + N + "        colonne +=", "    if True:" + N + "        colonne +="),
    ("F25 motore: v4 senza forza adottato", AD,
     '    return isinstance(v4, dict) and isinstance(v4.get("forza"), dict)', "    return isinstance(v4, dict)"),
    ("F26 motore: incrementale senza applicare la coda", AD,
     "            G.applica_coda_forza(coda_forza)" + N, "            pass" + N),
    ("F27 assembla_v4 senza blocco forza", V4,
     '            "forza": _forza_blocco(stati[lid].get("forza"))}', '            "forza": None}'),
    ("F28 generatore: vista v4 senza forza", GA,
     '"stagioni": stag, "forza": v4.get("forza")}', '"stagioni": stag}'),
    ("F29 generatore: coda persa se un lotto dell'incrementale cade", GA,
     "    finally:     # le partite gia' contate nel v3/v4 entrano anche nei rating" + N
     + "        applica_coda_forza(coda_forza)",
     "    except BaseException:" + N + "        raise" + N + "    else:" + N
     + "        applica_coda_forza(coda_forza)"),
]


def _h(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def pytest_rosso() -> tuple:
    env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x", SUPABASE_KEY="x")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *TEST],
                       cwd=RADICE, capture_output=True, text=True, timeout=900, env=env)
    righe = [x for x in r.stdout.splitlines() if x.strip()]
    fallito = [x for x in righe if x.startswith("FAILED")]
    return r.returncode != 0, (fallito[0] if fallito else (righe[-1] if righe else r.stderr[-200:]))


def main() -> int:
    esiti = []
    for nome, rel, vecchio, nuovo in ROTTURE:
        path = os.path.join(RADICE, rel)
        with open(path, "rb") as fh:
            originale = fh.read()
        testo = originale.decode("utf-8")
        if testo.count(vecchio) != 1:
            esiti.append((nome, "NON APPLICABILE (testo non trovato una volta)", ""))
            print(esiti[-1], flush=True)
            continue
        try:
            with open(path, "wb") as fh:
                fh.write(testo.replace(vecchio, nuovo).encode("utf-8"))
            rosso, coda = pytest_rosso()
        finally:
            with open(path, "wb") as fh:
                fh.write(originale)
        with open(path, "rb") as fh:
            ok = _h(fh.read()) == _h(originale)
        esiti.append((nome, "ROSSA" if rosso else "VERDE (!)", f"{coda} | ripristino {'OK' if ok else 'KO'}"))
        print(esiti[-1], flush=True)
    rosso, coda = pytest_rosso()
    print("\nsuite dopo i ripristini:", "ROSSA (!)" if rosso else "VERDE", coda)
    print(f"rotture rosse: {sum(1 for e in esiti if e[1] == 'ROSSA')}/{len(esiti)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
