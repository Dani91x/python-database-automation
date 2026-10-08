"""Mutazioni D-2: ogni mutazione si applica, si lanciano i test nuovi, si
ripristina dal backup e si verifica lo sha256. Mai interrotto a meta'."""
import hashlib, shutil, subprocess, sys, os

WT = r"C:\Users\Admin\Desktop\PYTHON DATABASE\wt-d2"
PY = os.path.join(WT, ".venv", "Scripts", "python.exe")
TEST = "Betfair/stream/tests/test_submin_rimpiazzo_non_nato_2026_10_08.py"
SM = os.path.join(WT, "Betfair", "stream", "trading", "submin.py")
LOW = os.path.join(WT, "Betfair", "stream", "live_order_worker.py")

def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

MUT = [
    ("M1 REPRICED->DONE come prima (blocco nuovo spento)", SM,
     b"        if state.serve_replace and order is not None:\r\n            ordini = _ordini_della_sequenza(order)",
     b"        if False:\r\n            ordini = _ordini_della_sequenza(order)"),
    ("M2 abort alla PRIMA osservazione (nessuna conferma)", SM,
     b"_GIRI_SOSTITUTO_ASSENTE_MAX = 2", b"_GIRI_SOSTITUTO_ASSENTE_MAX = 1"),
    ("M3 nessuna attesa col replace in volo", SM,
     b'_STATI_IN_VOLO = ("REPLACING",)', b'_STATI_IN_VOLO = ()'),
    ("M4 sostituto senza stato (mai piazzato) contato come nato", SM,
     b"        if _status_name(o) is None:\r\n            continue\r\n        return True",
     b"        if False:\r\n            continue\r\n        return True"),
    ("M5 si guarda solo l'ordine osservato, non il Trade", SM,
     b"    altri = getattr(getattr(order, \"trade\", None), \"orders\", None)",
     b"    altri = None"),
    ("M6 parcheggio vivo NON ritirato all'abort", SM,
     b"                        _require_ops(ops).cancel(market, o, None)\r\n                return _dc_replace(",
     b"                        pass\r\n                return _dc_replace("),
    ("M7 conteggio non azzerato quando il replace torna in volo", SM,
     b"                        if state.giri_senza_sostituto:\r\n                            return _dc_replace(state, giri_senza_sostituto=0)",
     b"                        if False:\r\n                            return _dc_replace(state, giri_senza_sostituto=0)"),
    ("M8 controllo anche sul percorso A (serve_replace ignorato)", SM,
     b"        if state.serve_replace and order is not None:", b"        if order is not None:"),
    ("M9 testo dell'abort diverso", SM,
     b'NOTA_RIMPIAZZO_NON_NATO = ("rimpiazzo NON nato', b'NOTA_RIMPIAZZO_NON_NATO = ("rimpiazzo non nato'),
    ("M10 worker: conteggio NON persistito (to_dict)", LOW,
     b'        "giri_senza_sostituto": int(getattr(state, "giri_senza_sostituto", 0) or 0),\r\n', b""),
    ("M11 worker: conteggio NON riletto (from_dict)", LOW,
     b'        giri_senza_sostituto=int(d.get("giri_senza_sostituto") or 0),\r\n', b""),
    ("M12 DONE anche senza sostituto se l'ordine osservato e' completo", SM,
     b"            if not _sostituto_nato(order, state):", b"            if not _sostituto_nato(order, state) and _status_name(order) != 'EXECUTION_COMPLETE':"),
]

righe = []
for nome, path, a, b in MUT:
    orig = open(path, "rb").read()
    h0 = sha(path)
    bak = path + ".bak_mut"
    shutil.copyfile(path, bak)
    try:
        assert orig.count(a) == 1, (nome, orig.count(a))
        open(path, "wb").write(orig.replace(a, b))
        r = subprocess.run([PY, "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider", "--no-header"],
                           cwd=WT, capture_output=True, text=True)
        ult = [l for l in r.stdout.splitlines() if l.strip()][-1]
        rossi = [l.split(" ")[1] for l in r.stdout.splitlines() if l.startswith("FAILED")]
    finally:
        shutil.copyfile(bak, path)
        os.remove(bak)
    h1 = sha(path)
    righe.append("%s | %s | ripristino %s (%s)" % (nome, ult, "IDENTICO" if h0 == h1 else "DIVERSO!", h1[:16]))
    righe.append("    rossi: " + ", ".join(x.split("::")[-1] for x in rossi))
print("\n".join(righe))
