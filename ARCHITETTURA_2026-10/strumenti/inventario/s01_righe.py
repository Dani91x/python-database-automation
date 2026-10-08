"""Sezione 1 - righe per file e per cartella dai file tracciati (git ls-files).

Righe = numero di newline (come `wc -l`). Uscite:
  uscite/s01_righe_per_file.tsv     (una riga per file tracciato: percorso, categoria, righe, byte)
  uscite/s01_riepilogo.txt          (totali per categoria, per cartella di radice, per sottocartella
                                     di Betfair/, file piu' grandi, confronto con il brief)
Uso: python s01_righe.py
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comune as c  # noqa: E402

EXT_FE_SRC = (".ts", ".tsx", ".js", ".jsx", ".css")
CARTELLE_AUDIT = re.compile(r"^(AUDIT_\d{4}-\d\d-\d\d|_AUDIT_\d{4}_\d\d|SCHEMI_BOT|ARCHITETTURA_2026-10)(/|$)")


EXT_BINARIE = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pkl", ".gz", ".zip", ".xlsx", ".woff", ".woff2", ".ttf", ".exe", ".dll", ".mp4", ".webm", ".webp"}
RE_GENERATO = re.compile(r"FILE GENERATO|@generated|[Aa]uto-?generated|DO NOT EDIT")


def e_generato(rel: str) -> bool:
    """File di codice con una dichiarazione di generazione nelle prime 15 righe."""
    if not rel.endswith((".ts", ".tsx", ".js", ".mjs", ".py", ".sql")):
        return False
    if rel.startswith(("AUDIT_", "_AUDIT_", "SCHEMI_BOT/", "ARCHITETTURA_2026-10/")):
        return False
    t = c.leggi_testo(rel)
    if t is None:
        return False
    return bool(RE_GENERATO.search(chr(10).join(t.splitlines()[:15])))


def categoria(rel: str) -> str:
    parti = rel.split("/")
    nome = parti[-1]
    ext = Path(nome).suffix.lower()
    if e_generato(rel):
        return "generati"
    if parti[0] == "frontend":
        if len(parti) > 1 and parti[1] == "src" and ext in EXT_FE_SRC:
            if re.search(r"\.(test|spec)\.", nome) or "test" in parti[2:-1] or "__tests__" in parti[2:-1]:
                return "frontend_test"
            return "frontend_codice"
        if ext in (".md",):
            return "documenti"
        return "frontend_altro"
    if parti[0] == "desktop":
        if ext == ".js":
            return "desktop_test" if ".test." in nome else "desktop_codice"
        return "desktop_altro"
    if ext == ".sql":
        return "sql"
    if ext == ".py":
        if c.e_strumento(rel):
            return "py_strumenti"
        if c.e_test_py(rel):
            return "py_test"
        if CARTELLE_AUDIT.match(rel):
            return "py_script_audit"
        if parti[0] == "Betfair":
            return "py_codice_Betfair"
        if len(parti) == 1:
            return "py_codice_radice"
        return "py_codice_cartelle_radice"
    if ext == ".md":
        return "documenti"
    # sottocategorie del vecchio blocco indistinto "altro"
    if ext in EXT_BINARIE:
        return "altro_binari_pdf_img_pkl"
    if ext in (".json", ".jsonl", ".csv"):
        return "altro_dati_json_csv"
    if ext in (".patch", ".diff"):
        return "altro_patch"
    if ext == ".html":
        return "altro_html"
    if ext in (".txt", ".out", ".err", ".cal_backup"):
        return "altro_txt_log"
    if ext in (".yml", ".yaml", ".toml", ".bat", ".ps1", ".sh", ".cjs", ".mjs", ".js", ".ts", ".tsx", ".mts", ".gitignore", ".npmrc") or ext == "":
        return "altro_script_config"
    return "altro_residuo"


def main() -> int:
    tracciati = c.file_tracciati()
    righe_file: dict[str, tuple[str, int, int]] = {}
    for rel in tracciati:
        d = c.leggi_bytes(rel)
        if d is None:
            righe_file[rel] = (categoria(rel), -1, -1)  # tracciato ma assente dal disco
            continue
        n = -2 if (c.e_binario(d) or Path(rel).suffix.lower() in EXT_BINARIE) else c.righe_wc(d)  # -2 = binario
        righe_file[rel] = (categoria(rel), n, len(d))
    out = ["percorso\tcategoria\trighe\tbyte"]
    for rel in sorted(righe_file):
        cat, n, b = righe_file[rel]
        out.append(f"{rel}\t{cat}\t{n}\t{b}")
    c.scrivi("s01_righe_per_file.tsv", "\n".join(out) + "\n")

    def righe(rel: str) -> int:
        return max(righe_file[rel][1], 0)

    r: list[str] = []
    r.append(f"HEAD {c.git('rev-parse', '--short', 'HEAD').strip()}  file tracciati: {len(tracciati)}")
    assenti = [p for p, v in righe_file.items() if v[1] == -1]
    binari = [p for p, v in righe_file.items() if v[1] == -2]
    r.append(f"tracciati ma assenti dal disco: {len(assenti)}; binari (righe non contate): {len(binari)}")
    mod = [l for l in c.git("status", "--short").splitlines() if not l.startswith("??")]
    r.append(f"file tracciati modificati nel working tree (git status, senza '??'): {len(mod)}")
    for l in mod[:20]:
        r.append("   " + l)
    r.append("")

    # --- per categoria
    r.append("== A. TOTALE PER CATEGORIA ==")
    agg: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    for rel, (cat, n, b) in righe_file.items():
        agg[cat][0] += 1
        agg[cat][1] += max(n, 0)
    r.append(f"{'categoria':<28}{'file':>8}{'righe':>12}")
    for cat, (nf, nr) in sorted(agg.items(), key=lambda x: -x[1][1]):
        r.append(f"{cat:<28}{nf:>8}{nr:>12}")
    r.append(f"{'TOTALE':<28}{sum(v[0] for v in agg.values()):>8}{sum(v[1] for v in agg.values()):>12}")
    r.append("")

    # --- macro-categorie richieste dal compito (codice / test / strumenti / frontend / desktop / SQL / documenti / generati / altro)
    MACRO = {
        "py_codice_Betfair": "1 codice Python produzione (Betfair/)",
        "py_codice_radice": "2 codice Python radice (*.py)",
        "py_codice_cartelle_radice": "3 codice Python altre cartelle di radice",
        "py_test": "4 test Python",
        "py_strumenti": "5 strumenti (tools/ e */tools/)",
        "py_script_audit": "6 script Python nelle cartelle AUDIT/SCHEMI/ARCHITETTURA",
        "frontend_codice": "7 frontend codice (src, ts/tsx/js/css)",
        "frontend_test": "8 frontend test",
        "frontend_altro": "9 frontend altro (config, public, lock, ...)",
        "desktop_codice": "10 desktop codice (js)",
        "desktop_test": "10 desktop test",
        "desktop_altro": "10 desktop altro (package-lock ecc.)",
        "sql": "11 SQL",
        "documenti": "12 documenti (.md)",
        "generati": "13 GENERATI (dichiarati nelle prime 15 righe)",
    }
    r.append("== A2. MACRO-CATEGORIE (compito §1) ==")
    r.append(f"{'macro':<60}{'file':>7}{'righe':>11}")
    macro_agg: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    for cat, (nf, nr) in agg.items():
        m = MACRO.get(cat, "14 ALTRO: " + cat)
        macro_agg[m][0] += nf
        macro_agg[m][1] += nr
    for m, (nf, nr) in sorted(macro_agg.items(), key=lambda x: (int(x[0].split()[0]) if x[0][0].isdigit() else 99, x[0])):
        r.append(f"{m:<60}{nf:>7}{nr:>11}")
    r.append("")
    r.append("== A3. FILE GENERATI (categoria 'generati') ==")
    for rel_, (cat, n, b) in sorted(righe_file.items()):
        if cat == "generati":
            r.append(f"{max(n, 0):>8}  {rel_}")
    r.append("")
    r.append("== A4. COSA CONTIENE IL VECCHIO BLOCCO 'altro' (1,7 M di righe): per cartella di radice e per i 12 file piu grandi di ogni sottocategoria ==")
    for cat in sorted(c_ for c_ in agg if c_.startswith("altro_")):
        r.append(f"-- {cat}: {agg[cat][0]} file, {agg[cat][1]} righe")
        per: dict[str, int] = collections.defaultdict(int)
        for rel_, (cc, n, b) in righe_file.items():
            if cc == cat:
                per[rel_.split("/")[0] if "/" in rel_ else "<radice>"] += max(n, 0)
        r.append("   per cartella: " + ", ".join(f"{k}={v}" for k, v in sorted(per.items(), key=lambda x: -x[1])[:8]))
        for n_, p_ in sorted(((righe(p), p) for p, v in righe_file.items() if v[0] == cat), reverse=True)[:5]:
            r.append(f"   {n_:>8}  {p_}")
    r.append("")

    # --- per cartella di radice (tutte le categorie)
    r.append("== B. PER CARTELLA DI RADICE (tutti i file tracciati) ==")
    top: dict[str, dict[str, list[int]]] = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    for rel, (cat, n, b) in righe_file.items():
        k = rel.split("/")[0] if "/" in rel else "<file di radice>"
        top[k][cat][0] += 1
        top[k][cat][1] += max(n, 0)
    r.append(f"{'cartella':<34}{'file':>7}{'righe':>11}  categorie principali (righe)")
    for k, cats in sorted(top.items(), key=lambda x: -sum(v[1] for v in x[1].values())):
        nf = sum(v[0] for v in cats.values())
        nr = sum(v[1] for v in cats.values())
        dett = ", ".join(f"{cc}={v[1]}" for cc, v in sorted(cats.items(), key=lambda x: -x[1][1])[:4])
        r.append(f"{k:<34}{nf:>7}{nr:>11}  {dett}")
    r.append("")

    # --- Betfair/ per sottocartella, codice/test/strumenti
    r.append("== C. Betfair/ PER SOTTOCARTELLA (solo .py: codice | test | strumenti, righe) ==")
    sub: dict[str, dict[str, list[int]]] = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    for rel, (cat, n, b) in righe_file.items():
        if not rel.startswith("Betfair/") or not rel.endswith(".py"):
            continue
        p = rel.split("/")
        if len(p) <= 2:
            k = "Betfair/*.py (radice del pacchetto)"
        elif len(p) == 3:
            k = "/".join(p[:2])
        else:
            k = "/".join(p[:3]) if p[1] == "stream" else "/".join(p[:2])
        sub[k][cat][0] += 1
        sub[k][cat][1] += max(n, 0)
    r.append(f"{'cartella':<46}{'codice':>9}{'test':>9}{'strum.':>9}{'file cod.':>11}")
    for k, cats in sorted(sub.items(), key=lambda x: -x[1]["py_codice_Betfair"][1]):
        r.append(
            f"{k:<46}{cats['py_codice_Betfair'][1]:>9}{cats['py_test'][1]:>9}{cats['py_strumenti'][1]:>9}"
            f"{cats['py_codice_Betfair'][0]:>11}"
        )
    r.append("")

    # --- file piu' grandi per categoria di codice
    for cat in ("py_codice_Betfair", "py_codice_radice", "frontend_codice", "py_test", "frontend_test", "py_strumenti"):
        r.append(f"== D. 25 FILE PIU GRANDI: {cat} ==")
        lst = sorted(((righe(p), p) for p, v in righe_file.items() if v[0] == cat), reverse=True)[:25]
        for n, p in lst:
            r.append(f"{n:>8}  {p}")
        r.append("")

    # --- frontend/src per cartella (codice | test | generati)
    r.append("== F. frontend/src PER CARTELLA (righe: codice | test | generati; file codice) ==")
    fe: dict[str, dict[str, list[int]]] = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    for rel, (cat, n, b) in righe_file.items():
        if rel.startswith("frontend/src/") and cat in ("frontend_codice", "frontend_test", "generati"):
            p = rel.split("/")
            k = "components/" + p[3] if p[2] == "components" and len(p) > 4 else (p[2] if len(p) > 3 else "(src/*)")
            fe[k][cat][0] += 1
            fe[k][cat][1] += max(n, 0)
    r.append(f"{'cartella':<28}{'codice':>9}{'test':>9}{'generati':>10}{'file cod.':>11}")
    for k, cats in sorted(fe.items(), key=lambda x: -x[1]["frontend_codice"][1] - x[1]["generati"][1]):
        r.append(f"{k:<28}{cats['frontend_codice'][1]:>9}{cats['frontend_test'][1]:>9}{cats['generati'][1]:>10}{cats['frontend_codice'][0]:>11}")
    r.append("")

    # --- confronto con il brief
    r.append("== E. CONFRONTO CON PAR. 1 DEL BRIEF DEL PIANO (valore del brief | valore misurato | esito) ==")

    def somma(pred) -> tuple[int, int]:
        sel = [p for p, v in righe_file.items() if pred(p, v[0])]
        return len(sel), sum(righe(p) for p in sel)

    def conf(etichetta: str, atteso_righe: int, atteso_file: int | None, misurato: tuple[int, int]) -> None:
        nf, nr = misurato
        esito = "UGUALE" if nr == atteso_righe else f"DIVERSO ({nr - atteso_righe:+d})"
        f = "" if atteso_file is None else f"  file brief {atteso_file} | misurati {nf}"
        r.append(f"{etichetta:<52} brief {atteso_righe:>8} | misurato {nr:>8} | {esito}{f}")

    righe_omega_cod = sum(righe(p) for p, v in righe_file.items() if v[0] == "py_codice_Betfair" and p.startswith("Betfair/omega/"))
    cod_betfair_radice = lambda p, cat: cat in ("py_codice_Betfair", "py_codice_radice")
    conf("Backend codice (Betfair/ + radice, no test/tools)", 271857, 256, somma(cod_betfair_radice))
    conf("  Betfair/stream/", 88987, None, somma(lambda p, cat: cat == "py_codice_Betfair" and p.startswith("Betfair/stream/")))
    for sott, v in (("scalper", 21620), ("tennis_live", 11638), ("tennis_scalper", 8943), ("backtest", 13391), ("trading", 4301)):
        conf(f"    stream/{sott}", v, None, somma(lambda p, cat, s=sott: cat == "py_codice_Betfair" and p.startswith(f"Betfair/stream/{s}/")))
    conf("  Betfair/omega/", 37500, None, somma(lambda p, cat: cat == "py_codice_Betfair" and p.startswith("Betfair/omega/")))
    conf("  Betfair/safe_strategy/", 34635, None, somma(lambda p, cat: cat == "py_codice_Betfair" and p.startswith("Betfair/safe_strategy/")))
    conf("  Betfair/mike/", 17755, None, somma(lambda p, cat: cat == "py_codice_Betfair" and p.startswith("Betfair/mike/")))
    conf("  Betfair/*.py (radice del pacchetto)", 7358, None, somma(lambda p, cat: cat == "py_codice_Betfair" and p.count("/") == 1))
    for p, v in (
        ("Betfair/omega/omega_service.py", 8936), ("Betfair/safe_strategy/bot_service.py", 11136),
        ("Betfair/safe_strategy/service.py", 3444), ("Betfair/safe_strategy/execution.py", 3093),
        ("Betfair/safe_strategy/engine.py", 2254), ("Betfair/mike/service.py", 7551), ("Betfair/mike/engine.py", 5359),
        ("Betfair/money_management.py", 3397), ("Betfair/betfair_report_manager.py", 1737),
        ("frontend/src/lib/replayBotCatalogo.ts", 11099), ("frontend/src/components/controlroom/useControlRoom.ts", 4322),
    ):
        if p in righe_file:
            conf(f"    {p}", v, None, (1, righe(p)))
        else:
            r.append(f"    {p}: NON TRACCIATO")
    # Ricostruzione dei numeri del brief: 256 file / 186.235 righe = tutti i .py di Betfair/ fuori da cartelle tests/tools/test
    # (cioe' con i test_*.py sparsi in Betfair/omega e Betfair/*.py contati come codice); 186235 = 88987+37500+34635+17755+7358.
    def fuori_dir_test(p: str) -> bool:
        pp = p.split("/")[:-1]
        return not ("tests" in pp or "tools" in pp or "test" in pp)

    nf_, nr_ = somma(lambda p, cat: p.startswith("Betfair/") and p.endswith(".py") and fuori_dir_test(p))
    r.append(f"RICOSTRUZIONE brief: .py di Betfair/ fuori da dir tests/tools/test: {nf_} file, {nr_} righe (somma componenti del brief 88987+37500+34635+17755+7358 = {88987+37500+34635+17755+7358})")
    nf_, nr_ = somma(lambda p, cat: p.startswith("Betfair/omega/") and p.endswith(".py") and fuori_dir_test(p))
    r.append(f"   di cui Betfair/omega/: {nf_} file, {nr_} righe (codice vero {righe_omega_cod} + test_*.py sparsi in omega/ {nr_ - righe_omega_cod})")
    r.append("   => il totale dichiarato dal brief (271.857) NON e' riproducibile: la somma delle sue componenti e' 186.235")
    conf("Test Python", 163079, None, somma(lambda p, cat: cat == "py_test"))
    conf("Strumenti (tools/, */tools/)", 35486, None, somma(lambda p, cat: cat == "py_strumenti"))
    conf("Frontend src codice", 133686, None, somma(lambda p, cat: cat == "frontend_codice"))
    conf("Frontend test", 73428, None, somma(lambda p, cat: cat == "frontend_test"))
    conf("Desktop (js, tutti)", 1183, None, somma(lambda p, cat: cat in ("desktop_codice", "desktop_test")))
    conf("Desktop (solo codice, senza .test.js)", 1183, None, somma(lambda p, cat: cat == "desktop_codice"))
    conf("SQL (tutti i .sql)", 33835, None, somma(lambda p, cat: cat == "sql"))
    conf("SQL (solo migrations/)", 33835, None, somma(lambda p, cat: cat == "sql" and p.startswith("migrations/")))
    r.append("")
    c.scrivi("s01_riepilogo.txt", "\n".join(r) + "\n")
    print("\n".join(r[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
