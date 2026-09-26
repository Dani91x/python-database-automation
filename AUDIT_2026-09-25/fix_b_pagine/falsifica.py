"""Falsificazione: per ogni mutazione (file, testo vecchio, testo nuovo, test) applica la
mutazione, lancia il test (deve diventare ROSSO), ripristina il file dal backup e verifica
l'hash SHA256 byte-identico. Una mutazione alla volta; il ripristino e' in `finally`.
NON interrompere questo script a meta' (lascerebbe una mutazione: vedi memoria 25/09)."""
import hashlib
import os
import shutil
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PY = os.path.join(REPO, '.venv', 'Scripts', 'python.exe')
ENV = dict(os.environ, SUPABASE_URL='http://127.0.0.1:9', SUPABASE_SERVICE_ROLE_KEY='x', SUPABASE_KEY='x')

MUT = [
    ('tactical_engine/serving.py', 'if fh is not None and fa is not None:\r\n            return int(fh), int(fa)',
     'if False:\r\n            return int(fh), int(fa)', 'py', 'tactical_engine/tests/test_serving_esito_reale_2026_09_26.py'),
    ('tactical_engine/serving.py', 'if payload.get("actual") is not None:', 'if False:', 'py',
     'tactical_engine/tests/test_serving_esito_reale_2026_09_26.py'),
    ('merge_engine_signals.py', 'kickoff = (match or {}).get("fixture_date") or es.get("kickoff")',
     'kickoff = es.get("kickoff")', 'py', 'test_merge_engine_signals_kickoff_2026_09_26.py'),
    ('frontend/src/lib/rese.ts', "return s === '' ? DASH : s;", "return s === '' ? '0' : s;", 'vt',
     'src/lib/rese.test.ts'),
    ('frontend/src/lib/rese.ts', "return giorno === oggi ? `${p.hh}:${p.mm}` : `${p.g}/${p.m} ${p.hh}:${p.mm}`;",
     "return `${p.hh}:${p.mm}`;", 'vt', 'src/lib/rese.test.ts'),
    ('frontend/src/lib/direzione.ts', "return { odds: m.odds, fonte: 'book', giudicabile: false };",
     "return { odds: m.odds, fonte: 'book', giudicabile: true };", 'vt',
     'src/components/dashboard/DirezioneDashboard.quota.test.tsx'),
    ('frontend/src/lib/fixtureModels.ts', 'divergente: mg !== null && mg !== classe,', 'divergente: false,', 'vt',
     'src/components/dashboard/MLPanel.verdetto.test.tsx'),
    ('frontend/src/lib/erroreRpc.ts', "tipo: 'timeout',", "tipo: 'errore',", 'vt', 'src/lib/erroreRpc.test.ts'),
    ('frontend/src/pages/Analytics.tsx', ') : !error && result ? (', ') : result || error ? (', 'vt',
     'src/pages/Analytics.errori.test.tsx'),
    ('build_analytics_signals.py', '"kickoff": (match or {}).get("fixture_date") or fp.get("fixture_date"),',
     '"kickoff": fp.get("fixture_date"),', 'py', 'test_build_analytics_signals_kickoff_2026_09_26.py'),
]
# FILTRO=<parte del percorso>: esegue solo le mutazioni di quei file
if os.environ.get('FILTRO'):
    MUT = [m for m in MUT if os.environ['FILTRO'] in m[0]]


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


for rel, old, new, tipo, test in MUT:
    p = os.path.join(REPO, rel)
    b = open(p, 'rb').read()
    if b.count(old.encode()) != 1:
        print(f'SALTATA {rel}: testo non trovato {b.count(old.encode())} volte')
        continue
    h0 = sha(p)
    shutil.copyfile(p, p + '.falsifica_bak')
    try:
        open(p, 'wb').write(b.replace(old.encode(), new.encode()))
        if tipo == 'py':
            r = subprocess.run([PY, '-m', 'pytest', test, '-q', '-p', 'no:cacheprovider'], cwd=REPO, env=ENV,
                               capture_output=True, text=True)
        else:
            r = subprocess.run('npx vitest run ' + test, cwd=os.path.join(REPO, 'frontend'), shell=True,
                               capture_output=True, text=True, encoding='utf-8', errors='replace')
        riga = [l for l in (r.stdout + r.stderr).splitlines() if 'passed' in l or 'failed' in l][-1:]
        print(f"{'ROSSO' if r.returncode else 'VERDE(!)'} {rel} :: {old[:50]!r} -> {riga}")
    finally:
        shutil.copyfile(p + '.falsifica_bak', p)
        os.remove(p + '.falsifica_bak')
        print(f'   ripristino byte-identico: {sha(p) == h0}')
