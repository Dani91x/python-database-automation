"""Falsificazione dei test di test_catchup_rete_2026_10_08.py: ogni mutazione reintroduce un
difetto, i test indicati devono diventare ROSSI; poi ripristino byte per byte."""
import hashlib
import subprocess
import sys

PY = r".venv\Scripts\python.exe"
TEST = "test_catchup_rete_2026_10_08.py"

M = [
    ("M01 5xx non ritentati", "db_client.py",
     '        if c.isdigit() and 500 <= int(c) <= 599:\r\n            return True, "gateway"',
     '        if c.isdigit() and 500 <= int(c) <= 599:\r\n            return True, None  # MUTAZIONE'),
    ("M02 nessun rinnovo del client su connessione terminata", "db_client.py",
     '            if classe == "connessione_terminata":\r\n                rinnova_client()',
     '            if classe == "connessione_terminata":\r\n                pass  # MUTAZIONE'),
    ("M03 per_fixture: client catturato in una variabile di modulo", "per_fixture_backfill.py",
     '    return get_supabase_client()\r\n',
     '    global _supabase  # MUTAZIONE\r\n    if globals().get("_supabase") is None:\r\n        _supabase = get_supabase_client()\r\n    return _supabase\r\n'),
    ("M04 ritentato il solo insert (delete fuori dall'unita')", "per_fixture_backfill.py",
     '        stato["cancellata"] = False\r\n        q = _client_per(get_supabase()).table(table).delete().eq("fixture_id", fixture_id)',
     '        if stato["cancellata"]:  # MUTAZIONE\r\n            return insert_rows(table, rows)\r\n        q = _client_per(get_supabase()).table(table).delete().eq("fixture_id", fixture_id)'),
    ("M05 registro esiti riapplicato alla cieca", "season_gaps.py",
     '        if gia_tentata[0] and campione is not None:',
     '        if False and gia_tentata[0] and campione is not None:  # MUTAZIONE'),
    ("M06 blocco in guasto: GuastoRete risale anche con la lista", "season_gaps.py",
     '                if rinviate_rete is None:\r\n                    raise',
     '                if True:  # MUTAZIONE\r\n                    raise'),
    ("M07 interruttore spento", "db_client.py",
     'INTERRUTTORE_DOPO_GUASTI = 2\r\n', 'INTERRUTTORE_DOPO_GUASTI = 10 ** 6  # MUTAZIONE\r\n'),
    ("M08 per_fixture non si ferma al guasto persistente", "per_fixture_backfill.py",
     '        if fs.get("rinvio_rete"):\r\n            # 08/10',
     '        if False and fs.get("rinvio_rete"):  # MUTAZIONE\r\n            # 08/10'),
    ("M09 referto: guasto di rete mai rosso", "seasons_catchup.py",
     '    return bool(oltre or persistenti)', '    return False  # MUTAZIONE'),
    ("M10 4xx ritentati", "db_client.py",
     '        return True, None                               # 4xx e applicativi: mai',
     '        return True, "gateway"  # MUTAZIONE'),
    ("M11 57014 ritentato come guasto di rete", "db_client.py",
     '            return True, None                           # R-CATCHUP-2, non qui',
     '            return True, "gateway"  # MUTAZIONE'),
    ("M12 proxy: insert ritentato", "db_client.py",
     '        if "insert" in nomi:\r\n            return False',
     '        if "insert" in nomi:\r\n            return True  # MUTAZIONE'),
    ("M13 nessun rinnovo preventivo", "db_client.py",
     '        if not ogni or contatore is None or contatore[0] < ogni:',
     '        if True:  # MUTAZIONE'),
    ("M14 main: GuastoRete non gestito (traceback)", "seasons_catchup.py",
     '    except GuastoRete as e:\r\n        # 08/10: guasto di rete/gateway persistente in una fase',
     '    except ZeroDivisionError as e:  # MUTAZIONE\r\n        # 08/10: guasto di rete/gateway persistente in una fase'),
    ("M15 giorni consecutivi = run consecutive", "season_gaps.py",
     '    if ultimo == oggi:\r\n        return max(1, n)', '    if ultimo == oggi:\r\n        return n + 1  # MUTAZIONE'),
    ("M16 catchup: rinviate non escluse (stato falso scritto)", "seasons_catchup.py",
     '    degradate_set = set(ris.degradate_timeout) | set(rinviate_verifica)',
     '    degradate_set = set(ris.degradate_timeout)  # MUTAZIONE'),
    ("M17 catchup: GuastoRete nel lavoro trattato come errore", "seasons_catchup.py",
     '            if _e_guasto_rete(es):\r\n                _rinvia_per_rete(sb, ris, k, f"lavoro:',
     '            if False and _e_guasto_rete(es):  # MUTAZIONE\r\n                _rinvia_per_rete(sb, ris, k, f"lavoro:'),
    ("M18 nessuna attesa tra i tentativi (backoff tolto)", "db_client.py",
     '            dormi(attesa)\r\n            continue', '            continue  # MUTAZIONE'),
    ("M19 insert_rows inghiotte il guasto di rete (niente unita')", "per_fixture_backfill.py",
     '            if classifica_guasto_rete(e):\r\n                raise\r\n            batch_errors += 1',
     '            if False:  # MUTAZIONE\r\n                raise\r\n            batch_errors += 1'),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    righe = []
    for nome, f, old, new in M:
        orig = open(f, "rb").read()
        h0 = sha(f)
        s = orig.decode("utf-8")
        n = s.count(old)
        if n != 1:
            righe.append(f"{nome}: MUTAZIONE NON APPLICABILE (occorrenze {n})")
            continue
        try:
            open(f, "wb").write(s.replace(old, new).encode("utf-8"))
            r = subprocess.run([PY, "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider", "-x", "--no-header",
                                "-rN"], capture_output=True, text=True, timeout=600)
            coda = [l for l in r.stdout.splitlines() if l.strip()][-1:]
            rossi = [l for l in r.stdout.splitlines() if l.startswith("FAILED") or "Error" in l][:3]
            r2 = subprocess.run([PY, "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider", "--no-header"],
                                capture_output=True, text=True, timeout=600)
            falliti = [l.split("::")[1].split(" ")[0] for l in r2.stdout.splitlines() if l.startswith("FAILED")]
            esito = "ROSSO" if r2.returncode != 0 else "VERDE (!!)"
            righe.append(f"{nome} [{f}]: {esito}; {(coda or [''])[0]}; falliti: {', '.join(falliti) or '-'}")
        finally:
            open(f, "wb").write(orig)
            assert sha(f) == h0, f"ripristino fallito su {f}"
    for r in righe:
        print(r)


if __name__ == "__main__":
    sys.exit(main())
