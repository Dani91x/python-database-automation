"""FALSIFICAZIONE dei test nuovi di FRONTEND MINORI (02/10/2026).

Per ogni mutazione: copia di sicurezza del file, difetto rimesso, test mirato,
esito atteso (ROSSO = il test vede il difetto; VERDE = controprova), ripristino
dalla copia e verifica byte per byte. Alla fine: `git status --porcelain`
identico a quello di partenza e i test mirati di nuovo verdi.

Uso (dalla radice del worktree, a macchina scarica):
    python AUDIT_2026-10-02/falsifica_frontend_minori.py > AUDIT_2026-10-02/falsifica_frontend_minori_out.txt
Il codice e' solo ASCII: le sequenze guaste si costruiscono dai byte.
"""
import re
import subprocess
import sys
import time
from pathlib import Path

RADICE = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True,
                             text=True, check=True).stdout.strip())
FE = RADICE / 'frontend'
NPX = 'npx.cmd' if sys.platform == 'win32' else 'npx'

# sequenze guaste costruite dai byte (UTF-8 letto come cp1252)
EURO_GUASTO = bytes([0xE2, 0x82, 0xAC]).decode('cp1252')      # "\u00e2\u201a\u00ac"
A_GRAVE_GUASTO = bytes([0xC3]).decode('cp1252') + chr(0xA0)    # "\u00c3" + nbsp
EURO = chr(0x20AC)


def git_status() -> str:
    return subprocess.run(['git', 'status', '--porcelain'], cwd=RADICE, capture_output=True,
                          text=True, check=True).stdout


def git_master(rel: str) -> bytes:
    return subprocess.run(['git', 'show', 'master:' + rel], cwd=RADICE, capture_output=True,
                          check=True).stdout


def vitest(files: list[str], filtro: str | None) -> tuple[int, str]:
    cmd = [NPX, 'vitest', 'run', *files]
    if filtro:
        cmd += ['-t', filtro]
    t0 = time.time()
    r = subprocess.run(cmd, cwd=FE, capture_output=True)
    out = re.sub(r'\x1b\[[0-9;]*m', '', r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace'))
    righe = [x.strip() for x in out.splitlines()
             if re.search(r'^\s*(Test Files|Tests)\s', x) or re.search(r'^\s*(\u00d7|x)\s', x) or ' \u2192 ' in x]
    return r.returncode, f'{time.time() - t0:.0f}s | ' + ' || '.join(righe[:8])


def sostituisci(testo: str, vecchio: str, nuovo: str) -> str:
    n = testo.count(vecchio)
    if n != 1:
        raise SystemExit(f'pattern trovato {n} volte (atteso 1): {vecchio[:80]!r}')
    return testo.replace(vecchio, nuovo)


def nl_di(testo: str) -> str:
    return '\r\n' if '\r\n' in testo else '\n'


# ----------------------------------------------------------------------------
# iniezioni di "carico simulato" (solo nei test, per le prove di 31 e 32)
# ----------------------------------------------------------------------------
def ritarda_sessione(t: str) -> str:
    """supabaseFinto: la sessione arriva dopo 1,5 s (la pagina resta sullo spinner, DOM senza testi)"""
    return sostituisci(
        t,
        'return Promise.resolve({ data: { session: sessioneFinta() }, error: null });',
        'return new Promise((r) => setTimeout(() => r({ data: { session: sessioneFinta() }, error: null }), 1500));',
    )


def ritarda_letture_mw(t: str) -> str:
    """MarketWatch.test: le sei letture finte arrivano tardi e fuori ordine (posizioni ultime, 1,5 s)"""
    nl = nl_di(t)
    ancora = 'const mTPositions = vi.mocked(fetchTennisPositionsAll);'
    codice = nl.join([
        ancora,
        '// CARICO SIMULATO (falsificazione): letture lente e fuori ordine',
        'for (const [m, ms] of [[mFollows, 200], [mNow, 600], [mPositions, 1500], [mTFollows, 300], [mTNow, 700], [mTPositions, 900]] as const) {',
        '    const x = m as unknown as { mockResolvedValue: (v: unknown) => unknown; mockImplementation: (f: () => unknown) => unknown };',
        '    x.mockResolvedValue = (v: unknown) => x.mockImplementation(() => new Promise((r) => setTimeout(() => r(v), ms)));',
        '}',
    ])
    return sostituisci(t, ancora, codice)


# ----------------------------------------------------------------------------
# mutazioni: (id, punto, descrizione, {file: trasformazione}, test, filtro, atteso)
# una trasformazione e' una funzione testo -> testo, oppure 'MASTER' (versione di master)
# ----------------------------------------------------------------------------
SCALPER = 'frontend/src/components/live/ScalperPanel.tsx'
CSS = 'frontend/src/index.css'
CR = 'frontend/src/pages/ControlRoom.tsx'
BPS = 'frontend/src/components/safestrategy/BotParamsSheet.tsx'
FOTO = 'frontend/src/fotografia/fotografia.test.tsx'
FINTO = 'frontend/src/fotografia/supabaseFinto.ts'
MWT = 'frontend/src/pages/MarketWatch.test.tsx'

T_A = (['src/test/codificaSorgenti.test.ts'], None)
T_B = (['src/pages/ControlRoom.test.tsx'], 'FRONTEND MINORI B')
T_C = (['src/fotografia/cssVeste.test.ts'], None)
T_35 = (['src/components/safestrategy/BotParamsSheet.test.tsx'], '35 campo')
T_31 = (['src/fotografia/fotografia.test.tsx'], 'mike:')
T_32 = (['src/pages/MarketWatch.test.tsx'], None)

MUTAZIONI = [
    ('A1', 'A', 'ScalperPanel: rimesso "Stake ' + 'EURO guasto" (riga 311)',
     {SCALPER: lambda t: sostituisci(t, '"text-white/50">Stake ' + EURO + '</span>', '"text-white/50">Stake ' + EURO_GUASTO + '</span>')},
     T_A, 'ROSSO'),
    ('A2', 'A', 'ScalperPanel: rimesso il BOM',
     {SCALPER: lambda t: '\ufeff' + t}, T_A, 'ROSSO'),
    ('A3', 'A', 'direzione nuova: mojibake in un ALTRO sorgente (commento in index.css)',
     {CSS: lambda t: t + '/* attivit' + A_GRAVE_GUASTO + ' */' + nl_di(t)}, T_A, 'ROSSO'),
    ('B1', 'B', 'ControlRoom: tolta l\'etichetta "Parametri comuni di Safe"',
     {CR: lambda t: sostituisci(t, 'triggerLabel="Parametri comuni di Safe"', '')}, T_B, 'ROSSO'),
    ('B2', 'B', 'ControlRoom: tolta l\'etichetta "Parametri strategia"',
     {CR: lambda t: sostituisci(t, 'triggerLabel="Parametri strategia"', '')}, T_B, 'ROSSO'),
    ('B3', 'B', 'BotParamsSheet non passa triggerLabel a ParamsSheetBase',
     {BPS: lambda t: sostituisci(t, 'triggerLabel={triggerLabel}', '')}, T_B, 'ROSSO'),
    ('C1', 'C', 'index.css: tolta la regola .ds-v2-chip--live.bg-red-500',
     {CSS: lambda t: sostituisci(t, '[data-shell="v2"] .ds-v2-chip--live.bg-red-500 {', '[data-shell="v2"] .ds-v2-chip--live-tolta {')}, T_C, 'ROSSO'),
    ('C2', 'C', 'regola presente ma sfondo tinta al 50 % (non pieno)',
     {CSS: lambda t: sostituisci(t, '.ds-v2-chip--live.bg-red-500 { background-color: #dc2626;', '.ds-v2-chip--live.bg-red-500 { background-color: rgb(220 38 38 / 0.5);')}, T_C, 'ROSSO'),
    ('C3', 'C', 'regola presente ma testo rosa chiaro su rosso (contrasto basso)',
     {CSS: lambda t: sostituisci(t, 'border-color: #f87171; color: #ffffff; }', 'border-color: #f87171; color: #fca5a5; }')}, T_C, 'ROSSO'),
    ('C4', 'C', 'direzione nuova: il marcatore LIVE tinta (PannelloBot/FasciaStop) diventa grigio',
     {CSS: lambda t: sostituisci(t, 'border-color: rgb(239 68 68 / 0.5); color: #fca5a5; }', 'border-color: rgb(148 163 184 / 0.5); color: #94a3b8; }')}, T_C, 'ROSSO'),
    ('M1', '35', 'fromValues: tolto il ramo "campo numerico vuoto"',
     {BPS: lambda t: sostituisci(t, "if (CHIAVI_NUMERICHE.has(key) && typeof value === 'string' && value.trim() === '') {", 'if (false) {')}, T_35, 'ROSSO'),
    ('M2', '35', 'fromValues: campo vuoto SALTATO ma chiave del DB conservata (deletePath tolto)',
     {BPS: lambda t: sostituisci(t, 'deletePath(out, key);\r\n            continue;' if '\r\n' in t else 'deletePath(out, key);\n            continue;', 'continue;')}, T_35, 'ROSSO'),
    ('M3', '35', 'CHIAVI_NUMERICHE senza le uscite numeriche (EXIT_NUM_FIELDS)',
     {BPS: lambda t: sostituisci(t, '...MODEL_EXIT_FIELDS, ...EXIT_NUM_FIELDS, ...STRATEGY_FIELDS,', '...MODEL_EXIT_FIELDS, ...STRATEGY_FIELDS,')}, T_35, 'ROSSO'),
    ('F1', '31', 'CARICO SIMULATO (sessione a 1,5 s) con la fotografia di MASTER',
     {FOTO: 'MASTER', FINTO: ritarda_sessione}, T_31, 'ROSSO'),
    ('F1b', '31', 'CARICO SIMULATO (sessione a 1,5 s) con la fotografia CORRETTA (controprova)',
     {FINTO: ritarda_sessione}, T_31, 'VERDE'),
    ('F2', '31', 'fotografia corretta SENZA la condizione "pagina pronta" + carico simulato',
     {FOTO: lambda t: sostituisci(t, 'while (uguali < 5 || scatta(p).pagina.testi.length === 0) {', 'while (uguali < 5) {'),
      FINTO: ritarda_sessione}, T_31, 'ROSSO'),
    ('W1', '32', 'CARICO SIMULATO (letture lente, fuori ordine) con MarketWatch.test di MASTER',
     {MWT: lambda _t: ritarda_letture_mw(git_master('frontend/src/pages/MarketWatch.test.tsx').decode('utf-8'))}, T_32, 'ROSSO'),
    ('W1b', '32', 'CARICO SIMULATO con MarketWatch.test CORRETTO (controprova)',
     {MWT: ritarda_letture_mw}, T_32, 'VERDE'),
    ('W2', '32', 'MarketWatch.test corretto ma "paper e live" senza waitFor + carico simulato',
     {MWT: lambda t: ritarda_letture_mw(sostituisci(t, '        await waitFor(() => {', '        await (async (f: () => void) => f())(() => {'))}, T_32, 'ROSSO'),
]


def main() -> int:
    stato0 = git_status()
    print('git status di partenza:\n' + (stato0 or '(pulito)'))
    esiti = []
    for mid, punto, descr, trasf, (files, filtro), atteso in MUTAZIONI:
        copie = {rel: (RADICE / rel).read_bytes() for rel in trasf}
        try:
            for rel, f in trasf.items():
                p = RADICE / rel
                if f == 'MASTER':
                    p.write_bytes(git_master(rel))
                else:
                    testo = p.read_bytes().decode('utf-8')
                    p.write_bytes(f(testo).encode('utf-8'))
            rc, riass = vitest(files, filtro)
        finally:
            for rel, b in copie.items():
                (RADICE / rel).write_bytes(b)
        for rel, b in copie.items():
            assert (RADICE / rel).read_bytes() == b, f'ripristino fallito: {rel}'
        visto = 'VERDE' if rc == 0 else 'ROSSO'
        ok = visto == atteso
        esiti.append(ok)
        print(f'[{mid}] punto {punto}: {descr}\n    atteso {atteso}, visto {visto} -> {"OK" if ok else "NON OK"}\n    {riass}')
    print('\n--- controprova finale: albero ripristinato, test mirati verdi ---')
    for files, filtro in (T_A, T_B, T_C, T_35, T_32):
        rc, riass = vitest(files, filtro)
        esiti.append(rc == 0)
        print(f'    {" ".join(files)} {filtro or ""}: {"VERDE" if rc == 0 else "ROSSO"} | {riass}')
    stato1 = git_status()
    uguale = stato1 == stato0
    esiti.append(uguale)
    print(f'git status finale identico a quello di partenza: {uguale}')
    print(f'\nESITO: {sum(esiti)}/{len(esiti)} come atteso')
    return 0 if all(esiti) else 1


if __name__ == '__main__':
    sys.exit(main())
