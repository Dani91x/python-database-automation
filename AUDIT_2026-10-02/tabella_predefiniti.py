"""Reperto 2 (02/10): per OGNI campo numerico di OGNI foglio parametri, che cosa usa il
servizio Python quando la chiave e' ASSENTE dalla riga del DB (cioe' dopo un campo svuotato).

Non e' una lettura a occhio: si chiamano le funzioni VERE del servizio con la riga senza
quella chiave (Safe `bot_service.resolve_params(raw, engine)`, Mike `config.merge_params`,
Omega `omega_config.resolve_params`) e si legge il valore risultante; per i 4 bot tennis
(classi flumine, non istanziabili qui) si legge il `c.get(chiave, default)` del bot e,
per lo scalper, il preset del runner (`tennis_runner._instantiate_bot` fa
`params.setdefault(k, run_tennis_scalper.TENNIS_PARAMS[k])` prima del bot).
Esito per chiave: OK = valore di serie numerico; ERRORE = eccezione; MANCA = il servizio
non conosce la chiave (nessun valore di serie). Stampa tabelle markdown con file:riga.

Uso (radice del worktree): python AUDIT_2026-10-02/tabella_predefiniti.py
"""
import re
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE))
FE = RADICE / 'frontend' / 'src'


def testo(p: Path) -> list[str]:
    return p.read_text(encoding='utf-8').splitlines()


def riga_di(file: Path, *pattern: str, dopo: str | None = None) -> str:
    """file:riga della prima riga che contiene tutti i pattern (dopo l'ancora, se data)"""
    righe = testo(file)
    inizio = 0
    if dopo:
        for i, r in enumerate(righe):
            if dopo in r:
                inizio = i
                break
    for i in range(inizio, len(righe)):
        if all(p in righe[i] for p in pattern):
            return f'{file.relative_to(RADICE).as_posix()}:{i + 1}'
    return f'{file.relative_to(RADICE).as_posix()}:?'


def blocco(righe: list[str], ancora: str) -> list[str]:
    out, dentro = [], False
    for r in righe:
        if ancora in r:
            dentro = True
        if dentro:
            out.append(r)
            if r.strip() == '];':
                break
    return out


# ---------------------------------------------------------------- chiavi dei fogli
def chiavi_safe() -> list[str]:
    righe = testo(FE / 'components/safestrategy/BotParamsSheet.tsx')
    keys: list[str] = []
    for nome in ('BOT_FIELDS', 'RISK_FIELDS', 'OPPS_FIELDS', 'MODEL_STAKE_FIELDS', 'MODEL_EXIT_FIELDS',
                 'EXIT_NUM_FIELDS', 'STRATEGY_FIELDS'):
        for r in blocco(righe, f'const {nome}: Num[] = ['):
            m = re.search(r"\{ key: (?:'([^']+)'|(TETTO_RISCHIO_KEY))", r)
            if m:
                keys.append(m.group(1) or 'risk.max_open_trades')
    return keys


def chiavi_mike() -> list[str]:
    return re.findall(r"\{ key: '([^']+)'[^\n]*kind: 'number'", (FE / 'lib/mike.ts').read_text(encoding='utf-8'))


def chiavi_omega() -> list[str]:
    t = (FE / 'lib/omega.ts').read_text(encoding='utf-8')
    t = t[t.index('export const OMEGA_PARAM_GROUPS'):]
    return re.findall(r"\{ key: '([^']+)'[^\n]*type: 'number'", t)


def chiavi_tennis() -> dict[str, list[str]]:
    t = (FE / 'lib/tennis.ts').read_text(encoding='utf-8')
    t = t[t.index('export const TENNIS_BOT_REGISTRY'):]
    out: dict[str, list[str]] = {}
    for parte in re.split(r"\n    \{\n        key: '", t)[1:]:
        bot = parte.split("'", 1)[0]
        params = parte[parte.index('params: ['):parte.index('defaults:')]
        out[bot] = [m.group(1) for m in re.finditer(r"\{ key: '([^']+)'([^\n]*)", params)
                    if "type: 'select'" not in m.group(2)]
    return out


# ---------------------------------------------------------------- servizi
def leggi(d: dict, path: str):
    for k in path.split('.'):
        d = d[k]
    return d


def tabella_safe() -> list[tuple]:
    from Betfair.safe_strategy import bot_service as bs, engine as en
    S = RADICE / 'Betfair/safe_strategy'
    righe = []
    for k in chiavi_safe():
        try:
            v = leggi(bs.resolve_params({}, engine_mod=en), k)
            esito = 'OK' if isinstance(v, (int, float)) and not isinstance(v, bool) else f'NON NUMERO ({v!r})'
            if k == 'risk.max_open_trades':
                esito = 'OK (None = tetto del bot)' if v is None else esito
        except KeyError:
            v, esito = None, 'MANCA'
        except Exception as ex:  # noqa: BLE001
            v, esito = None, f'ERRORE {ex}'
        if k.startswith('risk.'):
            dove = riga_di(S / 'risk.py', f'"{k[5:]}"', dopo='DEFAULT_RISK_PARAMS')
        elif k.startswith('exits.'):
            dove = riga_di(S / 'exits.py', f'"{k[6:]}"', dopo='DEFAULT_EXIT_PARAMS')
        elif '.' in k:
            sez, chi = k.split('.')
            dove = riga_di(S / 'engine.py', f'd["{sez}"]["{chi}"]')
        else:
            dove = riga_di(S / 'bot_service.py', f'out.get("{k}")')
            if dove.endswith(':?'):
                dove = riga_di(S / 'bot_service.py', f'"{k}"', dopo='DEFAULT_PARAMS')
        righe.append((k, v, dove, esito))
    return righe


def tabella_mike() -> list[tuple]:
    from Betfair.mike import config as mc
    righe = []
    for k in chiavi_mike():
        v = mc.merge_params({}).get(k, None)
        esito = 'OK' if k in mc.PARAM_SPEC and isinstance(v, (int, float)) and not isinstance(v, bool) else 'MANCA'
        righe.append((k, v, riga_di(RADICE / 'Betfair/mike/config.py', f'"{k}": ('), esito))
    return righe


def tabella_omega() -> list[tuple]:
    from Betfair.omega import omega_config as oc
    righe = []
    for k in chiavi_omega():
        v = oc.resolve_params({}).get(k, None)
        esito = 'OK' if k in oc._SPEC and isinstance(v, (int, float)) and not isinstance(v, bool) else 'MANCA'
        righe.append((k, v, riga_di(RADICE / 'Betfair/omega/omega_config.py', f'"{k}": ('), esito))
    return righe


def tabella_tennis() -> list[tuple]:
    T = RADICE / 'Betfair/stream/tennis_scalper'
    file_bot = {'tennis_scalper': 'tennis_scalper_bot.py', 'tennis_pro': 'tennis_pro_bot.py',
                'tennis_flb': 'tennis_flb_bot.py', 'tennis_swing': 'tennis_swing_bot.py'}
    preset_txt = (T / 'run_tennis_scalper.py').read_text(encoding='utf-8')
    preset_txt = preset_txt[preset_txt.index('TENNIS_PARAMS'):]
    preset_txt = preset_txt[:preset_txt.index('\n}')]
    righe = []
    for bot, keys in chiavi_tennis().items():
        src = (T / file_bot[bot]).read_text(encoding='utf-8')
        for k in keys:
            m = re.search(r'c\.get\("' + re.escape(k) + r'",\s*([^)]+)\)', src)
            if bot == 'tennis_scalper':
                p = re.search(r'"' + re.escape(k) + r'":\s*([^,]+),', preset_txt)
                if p:
                    righe.append((f'{bot}.{k}', p.group(1).strip(),
                                  riga_di(T / 'run_tennis_scalper.py', f'"{k}":', dopo='TENNIS_PARAMS')
                                  + ' (preset del runner, setdefault) e ' + riga_di(T / file_bot[bot], f'c.get("{k}"'),
                                  'OK'))
                    continue
            if m:
                righe.append((f'{bot}.{k}', m.group(1).strip(), riga_di(T / file_bot[bot], f'c.get("{k}"'), 'OK'))
            else:
                righe.append((f'{bot}.{k}', None, '-', 'MANCA'))
    return righe


def stampa(titolo: str, righe: list[tuple]) -> int:
    print(f'\n### {titolo} ({len(righe)} campi numerici)\n')
    print('| campo | valore di serie nel Python (chiave assente) | file:riga | esito |')
    print('|---|---|---|---|')
    male = 0
    for k, v, dove, esito in righe:
        print(f'| `{k}` | {v} | `{dove}` | {esito} |')
        if not esito.startswith('OK'):
            male += 1
    return male


if __name__ == '__main__':
    male = 0
    male += stampa('Safe (`bot_service.resolve_params({}, engine)`)', tabella_safe())
    male += stampa('Mike (`Betfair/mike/config.py` `merge_params({})`)', tabella_mike())
    male += stampa('Omega (`Betfair/omega/omega_config.py` `resolve_params({})`)', tabella_omega())
    male += stampa('Bot tennis (`c.get(chiave, default)` del bot; scalper: preset del runner)', tabella_tennis())
    print(f'\nchiavi senza valore di serie numerico: {male}')
    sys.exit(1 if male else 0)
