"""T0C passo 6: IMPRONTA della LOGICA di strategia per ogni bot, sullo stile di
``strumenti/e1/e1_impronta_strategia.py`` (Mike, 386 voci, che resta il suo
riferimento): garanzia meccanica che la migrazione SPOSTA la strategia senza
cambiarla (05 par. 0 regola 4).

Per ogni file di strategia del bot: SHA-1 (12 cifre) dell'AST SENZA docstring,
commenti e numeri di riga di ogni def/class di primo livello, di ogni METODO e
di ogni CAMPO di classe (``Classe.nome``), di ogni assegnazione di primo
livello, e una voce PER CHIAVE dei dizionari di parametri di primo livello il
cui nome contiene DEFAULT/PARAM/SPEC (``TABELLA[chiave]``: default, tipo,
limiti). Per i file del guscio (servizio, sessione, runner) solo i NOMI di
strategia elencati (parametri di produzione e risoluzione dei parametri).

Il confronto e' per (bot, file, nome): ammette che una funzione cambi file
SOLO dentro lo stesso bot se la voce si sposta di file (rosso: va dichiarato e
rigenerato con ``scrivi`` dopo la verifica umana) e fa ROSSO se cambia una
soglia, un default, una condizione, un ramo. Solo lettura statica: nessun
import del codice di produzione. ASCII-only.

Uso (dalla radice del repository):
    python -I ARCHITETTURA_2026-10/strumenti/impronte/impronta_strategia_bot.py scrivi [bot|tutti]
    python -I ARCHITETTURA_2026-10/strumenti/impronte/impronta_strategia_bot.py confronta [bot|tutti]
    ... [--radice DIR] [--cartella DIR_DELLE_TSV]
Exit code di ``confronta``: 0 = nessuna differenza, 1 = differenze (elencate).
"""
import ast
import hashlib
import os
import re
import sys

#: file interi di STRATEGIA per bot (tutto cio' che c'e' dentro e' strategia)
#: e file del GUSCIO da cui si prendono solo i nomi elencati
BOT = {
    "omega": {
        "file": ["Betfair/omega/omega_engine.py", "Betfair/omega/omega_v3.py",
                 "Betfair/omega/omega_model.py", "Betfair/omega/omega_empirical.py",
                 "Betfair/omega/omega_advisor.py", "Betfair/omega/omega_proposte.py",
                 "Betfair/omega/omega_config.py"],
        "nomi": {},
    },
    "safe": {
        "file": ["Betfair/safe_strategy/engine.py", "Betfair/safe_strategy/opportunity.py",
                 "Betfair/safe_strategy/exits.py", "Betfair/safe_strategy/risk.py",
                 "Betfair/safe_strategy/selezione.py", "Betfair/safe_strategy/pressure.py",
                 "Betfair/safe_strategy/combos.py", "Betfair/safe_strategy/calibration.py",
                 "Betfair/safe_strategy/anomaly.py", "Betfair/safe_strategy/tennis_opportunity.py",
                 "Betfair/safe_strategy/veto_campionati.py"],
        "nomi": {"Betfair/safe_strategy/bot_service.py": [
            "DEFAULT_PARAMS", "STRATEGIE_CON_USCITE", "normalize_uscite_automatiche",
            "uscite_automatiche_di", "resolve_params"]},
    },
    "scalper_calcio": {
        "file": ["Betfair/stream/scalper/scalper_bot.py", "Betfair/stream/scalper/sniper_bot.py",
                 "Betfair/stream/scalper/theta_bot.py", "Betfair/stream/scalper/media_under_bot.py",
                 "Betfair/stream/scalper/auto_mode.py", "Betfair/stream/scalper/bias_resolver.py",
                 "Betfair/stream/scalper/risk_semaphore.py", "Betfair/stream/scalper/habitat_scan.py",
                 "Betfair/stream/scalper/hazard_atlas.py"],
        "nomi": {"Betfair/stream/scalper/scalper_session.py": ["VALIDATED_PARAMS",
                                                               "UI_PARAM_WHITELIST"]},
    },
    "tennis": {
        "file": ["Betfair/stream/tennis_scalper/tennis_scalper_bot.py",
                 "Betfair/stream/tennis_scalper/tennis_pro_bot.py",
                 "Betfair/stream/tennis_scalper/tennis_flb_bot.py",
                 "Betfair/stream/tennis_scalper/tennis_swing_bot.py",
                 "Betfair/stream/tennis_scalper/tennis_winprob.py",
                 "Betfair/stream/tennis_scalper/tennis_score.py",
                 "Betfair/stream/tennis_scalper/superficie.py",
                 "Betfair/stream/tennis_scalper/condotta_ordini.py"],
        "nomi": {"Betfair/stream/tennis_scalper/run_tennis_pro.py": ["PRO_PARAMS"],
                 "Betfair/stream/tennis_scalper/run_tennis_scalper.py": ["TENNIS_PARAMS"]},
    },
}

#: i dizionari di parametri che si improntano anche chiave per chiave
RE_TABELLA = re.compile(r"(DEFAULT|PARAM|SPEC)")


def senza_doc(nodo):
    for n in ast.walk(nodo):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) and n.body:
            f = n.body[0]
            if isinstance(f, ast.Expr) and isinstance(getattr(f, "value", None), ast.Constant) \
                    and isinstance(f.value.value, str):
                n.body = n.body[1:] or [ast.Pass()]
    return nodo


def impronta(nodo):
    return hashlib.sha1(ast.dump(senza_doc(nodo), include_attributes=False).encode("utf-8")).hexdigest()[:12]


def _nome_assegnato(n):
    tgt = n.targets[0] if isinstance(n, ast.Assign) else n.target
    return tgt.id if isinstance(tgt, ast.Name) else None


def _voci_nodo(f, n, solo=None):
    """Le voci di un nodo di primo livello (con i metodi e i campi delle classi)."""
    out = []
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        if solo is not None and n.name not in solo:
            return out
        out.append((f, n.name, impronta(n)))
        if isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append((f, "%s.%s" % (n.name, m.name), impronta(m)))
                elif isinstance(m, (ast.Assign, ast.AnnAssign)):
                    nome = _nome_assegnato(m)
                    if nome:
                        out.append((f, "%s.%s" % (n.name, nome), impronta(m)))
    elif isinstance(n, (ast.Assign, ast.AnnAssign)):
        nome = _nome_assegnato(n)
        if not nome or (solo is not None and nome not in solo):
            return out
        out.append((f, nome, impronta(n)))
        val = n.value
        if RE_TABELLA.search(nome) and isinstance(val, ast.Dict):
            for k, v in zip(val.keys, val.values):
                if isinstance(k, ast.Constant):
                    out.append((f, "%s[%s]" % (nome, k.value), impronta(v)))
    return out


def calcola(bot, radice="."):
    spec = BOT[bot]
    righe = []
    for f in spec["file"]:
        tree = ast.parse(open(os.path.join(radice, f), encoding="utf-8").read())
        for n in tree.body:
            righe.extend(_voci_nodo(f, n))
    for f, nomi in sorted(spec["nomi"].items()):
        tree = ast.parse(open(os.path.join(radice, f), encoding="utf-8").read())
        trovati = set()
        for n in tree.body:
            v = _voci_nodo(f, n, solo=set(nomi))
            righe.extend(v)
            trovati.update(x[1].split(".")[0].split("[")[0] for x in v)
        for nome in nomi:
            if nome not in trovati:
                righe.append((f, nome, "ASSENTE"))
    return righe


def percorso_tsv(cartella, bot):
    return os.path.join(cartella, "impronta_%s.tsv" % bot)


def main(argv):
    args = list(argv[1:])
    radice = "."
    cartella = os.path.dirname(os.path.abspath(__file__))
    if "--radice" in args:
        i = args.index("--radice")
        radice = args[i + 1]
        del args[i:i + 2]
    if "--cartella" in args:
        i = args.index("--cartella")
        cartella = args[i + 1]
        del args[i:i + 2]
    modo = args[0] if args else "confronta"
    quali = args[1] if len(args) > 1 else "tutti"
    bots = sorted(BOT) if quali == "tutti" else [quali]
    rosso = 0
    for bot in bots:
        r = calcola(bot, radice)
        p = percorso_tsv(cartella, bot)
        if modo == "scrivi":
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("\n".join("\t".join(x) for x in r) + "\n")
            print("%s: scritte %d impronte in %s" % (bot, len(r), p))
            continue
        vecchie = {}
        for riga in open(p, encoding="utf-8").read().split("\n"):
            if riga:
                a, b, c = riga.split("\t")
                vecchie[(a, b)] = c
        nuove = {(a, b): c for a, b, c in r}
        diff = sorted(k for k in set(vecchie) | set(nuove) if vecchie.get(k) != nuove.get(k))
        print("%s: %d voci, differenze: %d %s" % (bot, len(nuove), len(diff), diff[:20]))
        rosso += len(diff)
    return 1 if (modo != "scrivi" and rosso) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
