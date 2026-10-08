"""Sezione 7 - cartelle di radice e *.py di radice: classifica VIVA / MORTA / ARCHIVIO con la prova.

Fonti (tutte rieseguibili, nessun codice di produzione eseguito):
  - uscite/s02_moduli.tsv, s02_archi.tsv, s02_esterni.tsv  (grafo import via AST)
  - lanciatori automatici: .github/workflows/*.yml, *.bat, *.ps1 di radice, desktop/*.js,
    Betfair/stream/{avvio_app,watchdog}.py, package.json
  - citazioni in frontend/src (non test)
  - git log (data dell'ultimo commit per percorso)
REGOLA (scritta qui perche' la classifica sia contestabile):
  VIVA      = importata da >= 1 file di PRODUZIONE esterno alla voce, oppure avviata da un lanciatore
              automatico (workflow, .bat/.ps1, desktop/main.js, avvio_app.py) o citata dal frontend/src non test
  ARCHIVIO  = nessuna delle due, ma importata da test/strumenti/audit, oppure script con __main__ lanciabile
              a mano, oppure cartella storica (AUDIT_*, SCHEMI_BOT, _AUDIT_*, docs, registrazioni, migrations, sql)
  MORTA     = nessun importatore di nessun tipo, nessuna citazione, nessun lanciatore, nessun __main__
Uscite: uscite/k03_classifica.tsv, uscite/k03_riepilogo.txt
Uso: python k03_classifica_radice.py
"""
from __future__ import annotations

import collections
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comune as c  # noqa: E402
from s01_righe import categoria  # noqa: E402

STORICHE = re.compile(r"^(AUDIT_|_AUDIT_|SCHEMI_BOT$|ARCHITETTURA_2026-10$|docs$|registrazioni_banco$|\.agent$|\.claude$)")
PROD = {"py_codice_Betfair", "py_codice_radice", "py_codice_cartelle_radice"}
NL = chr(10)


def ultima_data() -> dict[str, str]:
    out = subprocess.run(["git", "log", "--name-only", "--format=@%cs"], cwd=c.RADICE, capture_output=True, check=True).stdout
    d: dict[str, str] = {}
    cur = ""
    for riga in out.decode("utf-8", errors="replace").splitlines():
        if riga.startswith("@"):
            cur = riga[1:]
        elif riga and riga not in d:
            d[riga] = cur
    return d


def main() -> int:
    tracciati = c.file_tracciati()
    cat = {p: categoria(p) for p in tracciati}
    date = ultima_data()
    mod = {}
    for r in (c.USCITE / "s02_moduli.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        x = r.split("\t")
        mod[x[0]] = {"modulo": x[1], "cat": x[2], "righe": int(x[3]), "imp_prod": int(x[4]), "imp_test": int(x[5]),
                     "imp_strum": int(x[6]), "imp_audit": int(x[7]), "rif_str": x[9], "main": x[10]}
    archi = [tuple(r.split("\t")) for r in (c.USCITE / "s02_archi.tsv").read_text(encoding="utf-8").splitlines()[1:]]
    esterni = [r.split("\t") for r in (c.USCITE / "s02_esterni.tsv").read_text(encoding="utf-8").splitlines()[1:]]
    lanc_files = [p for p in tracciati if p.startswith(".github/workflows/")
                  or (("/" not in p) and p.endswith((".bat", ".ps1")))
                  or (p.startswith("desktop/") and p.endswith(".js"))
                  or p in ("Betfair/stream/avvio_app.py", "Betfair/stream/watchdog.py", "frontend/package.json", "desktop/package.json")]
    lanc_testi = {p: (c.leggi_testo(p) or "").splitlines() for p in lanc_files}
    fe_testi = {p: (c.leggi_testo(p) or "") for p in tracciati if cat[p] == "frontend_codice"}

    voci: dict[str, list[str]] = collections.defaultdict(list)
    for p in tracciati:
        voci[p.split("/")[0] if "/" in p else p].append(p)

    def nomi(v: str, files: list[str]) -> list[str]:
        if "/" not in v and v.endswith(".py"):
            return [v[:-3]]
        n = {v.replace(" ", "_").lower(), v}
        for f in files:
            parti = f.split("/")
            if len(parti) > 2 and parti[1] not in ("tests", "tools") and any(g.startswith(v + "/" + parti[1] + "/__init__") for g in files):
                n.add(parti[1])
        return sorted(n)

    righe = ["voce\ttipo\tfile\triga_py_prod\triga_py_tutte\tultimo_commit\timp_prod_esterni\timp_da_test\timp_strum_audit\tlanciatori_automatici\tcitata_da_frontend\tclasse\tmotivo"]
    riep = collections.defaultdict(list)
    for v, files in sorted(voci.items()):
        tipo = "cartella" if any("/" in f for f in files) else "file"
        if tipo == "file" and not v.endswith((".py", ".bat", ".ps1")):
            continue
        py = [f for f in files if f.endswith(".py")]
        r_prod = sum(mod[f]["righe"] for f in py if cat[f] in PROD and f in mod)
        r_py = sum(mod[f]["righe"] for f in py if f in mod)
        ultima = max((date.get(f, "") for f in files), default="")
        insieme = set(files)
        imp_prod: set[str] = set()
        imp_alt: set[str] = set()
        nm = nomi(v, files)
        for a, b in archi:
            if b in insieme and a not in insieme:
                (imp_prod if cat.get(a) in PROD else imp_alt).add(a)
        for f, ct, lib, rg in esterni:
            if lib in nm and f not in insieme:
                (imp_prod if cat.get(f) in PROD else imp_alt).add(f)
        n_test = sum(mod[f]["imp_test"] for f in py if f in mod)
        lanc: list[str] = []
        if tipo == "file":
            nome = v[:-3] if v.endswith(".py") else v
            # solo il nome del file (con estensione) o `-m stem`: lo stem nudo (parse, config, logger) darebbe falsi positivi
            rx = re.compile(r"(?<![A-Za-z0-9_./-])" + re.escape(v) + r"(?![A-Za-z0-9_])" + (r"|-m\s+" + re.escape(nome) + r"" if v.endswith(".py") else ""))
        else:
            rx = re.compile(re.escape(v) + r"[/\\ ]|-m\s+" + re.escape(nm[0]) + r"\b")
        for lf, ls in lanc_testi.items():
            if lf in insieme:
                continue
            for i, l in enumerate(ls, 1):
                if l.lstrip().startswith(("#", "//", "REM ")):
                    continue
                if rx.search(l):
                    lanc.append(lf + ":" + str(i))
                    break
        fe = ""
        if v not in ("Betfair", "frontend", "migrations", "desktop", "tools"):
            for f, t in fe_testi.items():
                m = re.search(r"^(?!\s*(//|\*|/\*)).*" + re.escape(v), t, re.M)
                if m:
                    fe = f + ":" + str(t[:m.end()].count(NL) + 1)
                    break
        main_si = any(mod[f]["main"] == "si" for f in py if f in mod)
        if STORICHE.match(v) or v in ("migrations", "sql"):
            cl = "ARCHIVIO"
            mot = "cartella storica o di dati: " + ("SQL applicato dall'utente" if v in ("migrations", "sql") else "audit, schemi, documenti o registrazioni")
        elif v == ".github":
            cl, mot = "VIVA", "10 workflow GitHub Actions: sono i lanciatori cloud dei job di calcolo (vedi sezione 7 del documento)"
        elif v == "Telegram bot":
            cl, mot = "NON_VERIFICABILE", "Edge Functions Supabase in Deno/TypeScript (supabase/functions/telegram-bot, make-daily-post): il codice non e' Python, non e' importato da nulla nel repo; lo stato di deploy e' sul cloud"
        elif v in ("Betfair", "frontend", "desktop"):
            cl, mot = "VIVA", "cuore del prodotto (avviata da desktop/main.js o servita dall'app)"
        elif tipo == "file" and cat.get(v) == "py_test":
            cl, mot = "TEST", "test pytest di radice (non e' codice di produzione)"
        elif imp_prod or lanc:
            cl = "VIVA"
            parti_m = []
            if imp_prod:
                parti_m.append("importata da %d file di produzione esterni (es. %s)" % (len(imp_prod), sorted(imp_prod)[0]))
            if lanc:
                parti_m.append("lanciatore " + lanc[0])
            if fe:
                parti_m.append("citata dal frontend " + fe)
            mot = "; ".join(parti_m)
        elif fe:
            cl = "ARCHIVIO"
            mot = "citata dalla UI come istruzione di lancio manuale: " + fe
        elif imp_alt or n_test or main_si:
            cl = "ARCHIVIO"
            mot = "nessun importatore di produzione ne' lanciatore automatico; importata da test/strumenti/audit (%d file, %d importazioni da test)" % (len(imp_alt), n_test)
            if main_si:
                mot += "; ha __main__ lanciabile a mano"
        elif tipo == "file" and v.endswith((".bat", ".ps1")):
            cl, mot = "ARCHIVIO", "script di lancio manuale (nessun lanciatore automatico lo richiama)"
        else:
            cl, mot = "MORTA", "nessun importatore, nessun lanciatore, nessuna citazione, nessun __main__"
        righe.append("\t".join(map(str, [v, tipo, len(files), r_prod, r_py, ultima, len(imp_prod), n_test, len(imp_alt),
                                         "|".join(lanc[:3]), fe, cl, mot])))
        riep[cl].append((v, r_prod, r_py, ultima, mot))
    c.scrivi("k03_classifica.tsv", NL.join(righe) + NL)
    # tabelle markdown per il documento: cartelle (con codice o rilevanti) e file di radice
    rows = [r.split(chr(9)) for r in righe[1:]]
    md_c = ["| cartella | file | righe py (prod / tutte) | ultimo commit | importata da (file di produzione esterni) | lanciatore automatico | classe | prova |", "|---|---:|---:|---|---:|---|---|---|"]
    md_f = ["| file di radice | righe | ultimo commit | importato da (prod) | lanciatore automatico / citazioni | classe | prova |", "|---|---:|---|---:|---|---|---|"]
    for x in rows:
        v, tipo, nf, rp, rt, ul, ip, itst, ia, lan, fe, cl, mot = x
        if tipo == "cartella":
            md_c.append("| `%s` | %s | %s / %s | %s | %s | %s | **%s** | %s |" % (v, nf, rp, rt, ul, ip, lan.replace("|", ", ") or "-", cl, mot))
        elif v.endswith(".py"):
            md_f.append("| `%s` | %s | %s | %s | %s | **%s** | %s |" % (v, rt, ul, ip, (lan.replace("|", ", ") or "-") + ((" ; UI: " + fe) if fe else ""), cl, mot))
        else:
            md_f.append("| `%s` | - | %s | - | %s | **%s** | %s |" % (v, ul, (lan.replace("|", ", ") or "-") + ((" ; UI: " + fe) if fe else ""), cl, mot))
    c.scrivi("k03_cartelle.md", NL.join(md_c) + NL)
    c.scrivi("k03_file_radice.md", NL.join(md_f) + NL)
    out = []
    for cl in ("VIVA", "ARCHIVIO", "MORTA", "NON_VERIFICABILE", "TEST"):
        lst = riep[cl]
        out.append("== %s: %d voci, %d righe py di produzione, %d righe py totali ==" % (cl, len(lst), sum(x[1] for x in lst), sum(x[2] for x in lst)))
        for v, rp, rt, ul, mot in sorted(lst, key=lambda x: -x[2]):
            out.append("  %-44s prod=%6d py=%6d  %s  %s" % (v, rp, rt, ul, mot[:140]))
        out.append("")
    c.scrivi("k03_riepilogo.txt", NL.join(out) + NL)
    print(NL.join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
