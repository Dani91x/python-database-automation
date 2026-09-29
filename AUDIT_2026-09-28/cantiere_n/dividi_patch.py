"""Divide il lavoro del cantiere N in DUE patch applicabili su origin/master:
  1) blocchi 1-2 (riavvio -> manuale, approvazione che ricontrolla, pulsante
     unico + schede parametri);
  2) blocco 3 (proposta -> firma -> ordine per bot tennis e scalper), da
     applicare DOPO la 1.
Non tocca l'indice ne' il working tree: usa un indice temporaneo e git apply in
una cartella fuori dal repo. Uso: python dividi_patch.py <cartella_temporanea>
"""
import os
import subprocess
import sys

WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(WT, "AUDIT_2026-09-28", "cantiere_n")

BLOCCO3_SOLO = {
    "Betfair/stream/uscite_proposte.py",
    "Betfair/stream/scalper/scalper_bot.py",
    "Betfair/stream/scalper/scalper_session.py",
    "Betfair/stream/tennis_live/tennis_runner.py",
    "Betfair/stream/tennis_live/auto_mode.py",
    "Betfair/stream/tennis_scalper/tennis_swing_bot.py",
    "Betfair/stream/tennis_scalper/tennis_pro_bot.py",
    "Betfair/stream/tennis_scalper/tennis_flb_bot.py",
    "Betfair/stream/tennis_scalper/tennis_scalper_bot.py",
    "Betfair/stream/tennis_scalper/tests/test_tennis_swing.py",
    "Betfair/stream/tennis_scalper/tests/test_uscite_manuali_bot_tennis_2026_09_25.py",
    "Betfair/stream/tennis_scalper/tests/test_uscite_proposte_bot_tennis_2026_09_28.py",
    "Betfair/stream/tennis_live/tests/test_tennis_auto_mode_2026_09_25.py",
    "Betfair/stream/tennis_live/tests/test_tennis_firme_e_proposte_2026_09_28.py",
    "Betfair/stream/tests/test_scalper_uscite_automatiche_2026_09_25.py",
    "migrations/uscite_approva_bot_flusso_2026-09-28.sql",
    "frontend/src/lib/proposteUscite.ts",
    "frontend/src/components/controlroom/ProposteUsciteFlusso.tsx",
    "frontend/src/components/controlroom/ProposteUsciteFlusso.test.tsx",
    "AUDIT_2026-09-28/cantiere_n/patch_tennis_scalper.py",
    "AUDIT_2026-09-28/cantiere_n/falsifica_n.py",
    "AUDIT_2026-09-28/cantiere_n/dividi_patch.py",
    "AUDIT_2026-09-28/cantiere_n/ascii_righe_nuove.py",
    "AUDIT_2026-09-28/cantiere_n/sostituisci_classe.py",
    "AUDIT_2026-09-28/cantiere_n/inserisci_sezioni.py",
    "Betfair/stream/tests/test_coordinatore_cancello_uscite_2026_09_28.py",
    "AUDIT_2026-09-28/CANTIERE_N_PULSANTE_USCITE.md",
}
CONDIVISI = (
    "Betfair/stream/tennis_live/tennis_bot_service.py",
    "frontend/src/components/controlroom/useControlRoom.ts",
    "frontend/src/pages/ControlRoom.tsx",
)
ESCLUSI_PREFISSI = ("AUDIT_2026-09-28/cantiere_n/cantiere_n_",)
# il blocco 3 come commit (prima dei merge): da qui si tolgono i suoi pezzi
# dai file condivisi
B3_DA, B3_A = "4d121b1", "8113f52"


def git(*a: str, env: dict | None = None, inp: bytes | None = None, cwd: str = WT) -> bytes:
    r = subprocess.run(["git", *a], cwd=cwd, env=env, input=inp, capture_output=True)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(a)} -> {r.stderr.decode(errors='replace')}")
    return r.stdout


def main(tmp: str) -> int:
    base = git("rev-parse", "origin/master").decode().strip()
    head = git("rev-parse", "HEAD").decode().strip()
    # i file del cantiere = diff fra origin/master e HEAD (HEAD ha gia' dentro master)
    righe = git("diff", "--name-status", base, head).decode().splitlines()
    stato = {}
    for r in righe:
        parti = r.split("\t")
        stato[parti[-1]] = parti[0][0]
    stato = {f: s for f, s in stato.items() if not f.startswith(ESCLUSI_PREFISSI)}
    # i condivisi senza i pezzi del blocco 3
    os.makedirs(tmp, exist_ok=True)
    p3 = os.path.join(tmp, "b3.diff")
    with open(p3, "wb") as fh:
        fh.write(git("diff", B3_DA, B3_A, "--", *CONDIVISI))
    blob12 = {}
    for f in CONDIVISI:
        dst = os.path.join(tmp, "copia", *f.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(git("show", f"{head}:{f}"))
        r = subprocess.run(["git", "apply", "-R", "-C1", f"--include={f}", p3],
                           cwd=os.path.join(tmp, "copia"), capture_output=True)
        if r.returncode != 0 and f.endswith("ControlRoom.tsx"):
            # l'import e' stato fuso a mano con quello di master (conflitto del
            # merge): i due pezzi del blocco 3 si tolgono per testo esatto
            with open(dst, "rb") as fh:
                t = fh.read().decode("utf-8")
            nl = "\r\n" if "\r\n" in t else "\n"
            pezzi = [
                "import { ProposteUsciteFlusso } from '@/components/controlroom/ProposteUsciteFlusso';" + nl,
                ("            {/* 28/09 (CANTIERE N): le uscite da approvare dei bot di flusso" + nl
                 + '                (4 bot tennis, scalper calcio), con i numeri e "approva". Mike,' + nl
                 + "                Omega e Safe hanno le loro schede proposta di sempre. */}" + nl
                 + "            <ProposteUsciteFlusso" + nl
                 + "                proposte={vm.bots.filter((b) => sport == null" + nl
                 + "                    || (sport === 'tennis') === isBotTennis(b.bot))" + nl
                 + "                    .flatMap((b) => b.proposteUscite ?? [])}" + nl
                 + "                nowMs={vm.nowMs}" + nl
                 + "            />" + nl + nl),
            ]
            for pz in pezzi:
                if t.count(pz) != 1:
                    raise SystemExit(f"pezzo del blocco 3 non trovato in {f}: {pz[:60]!r}")
                t = t.replace(pz, "")
            with open(dst, "wb") as fh:
                fh.write(t.encode("utf-8"))
        elif r.returncode != 0:
            raise SystemExit(f"togliere il blocco 3 da {f}: {r.stderr.decode(errors='replace')}")
        with open(dst, "rb") as fh:
            dati = fh.read()
        originale = git("show", f"{head}:{f}")
        # stesse fini riga del file nel repo (git apply fuori dal repo le normalizza)
        if b"\r\n" in originale and b"\r\n" not in dati:
            dati = dati.replace(b"\n", b"\r\n")
        elif b"\r\n" not in originale and b"\r\n" in dati:
            dati = dati.replace(b"\r\n", b"\n")
        blob12[f] = git("hash-object", "-w", "--stdin", inp=dati).decode().strip()
    # albero dei blocchi 1-2: origin/master + i file 1-2 (+ condivisi ripuliti)
    env = dict(os.environ, GIT_INDEX_FILE=os.path.join(tmp, "indice12"))
    git("read-tree", base, env=env)
    for f, s in sorted(stato.items()):
        if f in BLOCCO3_SOLO:
            continue
        if s == "D":
            git("update-index", "--force-remove", f, env=env)
            continue
        if f in blob12:
            sha = blob12[f]
        else:
            sha = git("rev-parse", f"{head}:{f}").decode().strip()
        git("update-index", "--add", "--cacheinfo", f"100644,{sha},{f}", env=env)
    t12 = git("write-tree", env=env).decode().strip()
    # albero finale = HEAD ristretto ai file del cantiere su origin/master
    env2 = dict(os.environ, GIT_INDEX_FILE=os.path.join(tmp, "indice123"))
    git("read-tree", base, env=env2)
    for f, s in sorted(stato.items()):
        if s == "D":
            git("update-index", "--force-remove", f, env=env2)
            continue
        sha = git("rev-parse", f"{head}:{f}").decode().strip()
        git("update-index", "--add", "--cacheinfo", f"100644,{sha},{f}", env=env2)
    t123 = git("write-tree", env=env2).decode().strip()
    with open(os.path.join(OUT, "cantiere_n_blocchi_1_2.patch"), "wb") as fh:
        fh.write(git("diff", "--binary", base, t12))
    with open(os.path.join(OUT, "cantiere_n_blocco_3.patch"), "wb") as fh:
        fh.write(git("diff", "--binary", t12, t123))
    print("base", base, "t12", t12, "t123", t123)
    print("blocchi 1-2:", git("diff", "--stat", base, t12).decode().splitlines()[-1])
    print("blocco 3   :", git("diff", "--stat", t12, t123).decode().splitlines()[-1])
    # controllo: 1 + 2 = tutto il lavoro
    tutto = git("diff", "--stat", base, t123).decode().splitlines()[-1]
    print("tutto      :", tutto)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
