"""Falsificazione dell'integrazione W1-G1 + W1-C1 (09/10): ogni mutazione deve far diventare
ROSSO almeno un test (con il filtro indicato); poi il file torna identico (sha256).

Uso: ``python falsifica_integrazione.py <radice del worktree> [ID ...]`` (senza ID: tutte).
P* = porta degli ordini (rossi SOLO col filtro ``vero``: l'archivio VERO di W1-G1 li vede);
F* = finto dei test (il contratto finto/vero li vede); D* = dati (solo locali, postino,
client cloud, registro).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

RADICE = Path(sys.argv[1])
SOLO = set(sys.argv[2:])
P = "Betfair/nucleo/ordini/porta.py"
FT = "Betfair/nucleo/ordini/tests/test_c1_porta.py"
A = "Betfair/nucleo/dati/archivio.py"
PO = "Betfair/nucleo/dati/postino.py"
CL = "Betfair/nucleo/dati/cloud.py"
RE = "Betfair/nucleo/dati/registro.py"
T_PORTA = ["Betfair/nucleo/ordini/tests/test_c1_porta.py", "Betfair/nucleo/ordini/tests/test_c1_revisione.py"]
T_CONTR = ["Betfair/nucleo/ordini/tests/test_c1_contratto_archivio.py"]
T_REG = ["Betfair/nucleo/dati/tests/test_g2_registro.py"]

# (id, descrizione, file, vecchio, nuovo, test, filtro -k)
MUTAZIONI = [
    ("P1", "ack non scritto nell'archivio (dedup persistente perso)", P,
     "        self._archivio.scrivi(TABELLA_REF, _ack_in_riga(ack, attore, int(self._ora_ms())))\n",
     "        pass\n", T_PORTA, "vero"),
    ("P2", "dedup che ignora la riga dell'archivio", P,
     "            riga = self._archivio.leggi(TABELLA_REF, {\"ref\": ref})",
     "            riga = None", T_PORTA, "vero"),
    ("P3", "blocco dei seq non prenotato nell'archivio", P,
     "                self._archivio.scrivi(TABELLA_SEQ, {\"chiave\": \"seq\",",
     "                (lambda *a, **k: None)(TABELLA_SEQ, {\"chiave\": \"seq\",", T_PORTA, "vero"),
    ("P4", "blocco dei seq ignorato all'apertura", P,
     "                massimo = max(massimo, int(riga.get(\"fino_a\") or 0))",
     "                massimo = massimo", T_PORTA, "vero"),
    ("P5", "archivio illeggibile: fail-open invece di fail-closed", P,
     "            logger.error(\"[porta] archivio illeggibile, %s RIFIUTATO: %s\", ref, str(ex)[:160])\n"
     "            return self._rifiuto_non_registrato(\n"
     "                ref, f\"{M_ARCHIVIO}: dedup per ref non verificabile ({str(ex)[:120]})\")",
     "            prima = None", T_PORTA, "vero"),
    ("P6", "archivio non scrivibile: l'ordine parte lo stesso", P,
     "                logger.error(\"[porta] archivio NON scrivibile, %s RIFIUTATO: %s\", ref, ex)\n"
     "                return self._rifiuto_dopo_seq(",
     "                logger.error(\"[porta] archivio NON scrivibile, %s RIFIUTATO: %s\", ref, ex)\n"
     "                if False:\n                    return self._rifiuto_dopo_seq(", T_PORTA, "vero"),
    # ------------------------------------------------------------ il finto non diverge dal vero
    ("F1", "finto: transizione su riga assente crea la riga", FT,
     "            if k not in t:\n                return False\n            riga = json.loads(t[k])",
     "            riga = json.loads(t.get(k, '{\"status\": \"\"}'))", T_CONTR, None),
    ("F2", "finto: scrivi sostituisce invece di fondere", FT,
     "            t[k] = _json_vero({**prima, **nuova})", "            t[k] = _json_vero(nuova)", T_CONTR, None),
    ("F3", "finto: una capacita' che il vero non ha", FT,
     "    @property\n    def aperto(self) -> bool:\n        return self._aperto\n\n    def chiudi(self, timeout_s",
     "    @property\n    def aperto(self) -> bool:\n        return self._aperto\n\n"
     "    def elimina(self, tabella: str) -> None:\n        self._righe.pop(tabella, None)\n\n"
     "    def chiudi(self, timeout_s", T_CONTR, None),
    ("F4", "finto: JSON senza default=str (datetime rifiutato)", FT,
     "        nuova = json.loads(_json_vero(dict(riga)))", "        nuova = json.loads(json.dumps(dict(riga)))",
     T_CONTR, None),
    ("F5", "finto: ordine dei controlli di scrivi diverso dal vero", FT,
     "        self._controlla_aperto()\n        spec = self._spec(tabella)\n        k = chiave_canonica(spec, riga)",
     "        spec = self._spec(tabella)\n        self._controlla_aperto()\n        k = chiave_canonica(spec, riga)",
     T_CONTR, None),
    ("F6", "finto: transizione col disco guasto che non aspetta", FT,
     "        while self.guasto_scrittura:                   # sincrona: aspetta il disco",
     "        while False:                                   # sincrona: aspetta il disco", T_CONTR, None),
    # ------------------------------------------------------------ dati: solo locali, mai il cloud
    ("D1", "postino: voce solo locale consegnata", PO,
     "                if v.tabella in TABELLE_SOLO_LOCALI:              # integrazione W1-C1: MAI il cloud",
     "                if False:                                         # integrazione W1-C1: MAI il cloud",
     T_REG, "solo_locale"),
    ("D2", "postino: riconciliazione delle solo locali", PO,
     "            if t in TABELLE_SOLO_LOCALI:\n                continue",
     "            if False:\n                continue", T_REG, "solo_locale"),
    ("D3", "client: postino_consegna senza controllo di p_tabella", CL,
     "        if nome in RPC_CON_TABELLA:\n            self._controlla_tabella_rpc(nome, args)\n", "",
     T_REG, "client_rifiuta"),
    ("D4", "archivio: solo locali in outbox", A,
     "        if tabella in TABELLE_SOLO_LOCALI:\n            return 0", "        if False:\n            return 0",
     T_REG, "solo_locali"),
    ("D5", "archivio: spec che ignora le solo locali", A,
     "        locale = TABELLE_SOLO_LOCALI.get(tabella)\n", "        locale = None\n", T_REG, "solo_locali"),
    ("D6", "archivio: solo locali fra le tabelle da riconciliare", A,
     "(giorno,)) if r[0] not in TABELLE_SOLO_LOCALI)", "(giorno,)))", T_REG, "solo_locali"),
    ("D7", "registro: solo locali nel file vivo (synchronous NORMAL)", RE,
     "    return SpecTabella(nome=nome, chiave_naturale=chiave, natura=\"SV\", regime=\"stato_denaro\",",
     "    return SpecTabella(nome=nome, chiave_naturale=chiave, natura=\"SV\", regime=\"stato_vivo\",",
     T_REG, "solo_locali"),
    ("D8", "registro: postino_versioni tolta (voce intera)", RE,
     None, "", T_REG, None),
    ("D9", "registro: una solo locale anche nel registro del cloud", RE,
     "        if nome in cloud:\n            errori.append", "        if nome in ():\n            errori.append",
     T_REG, "solo_local"),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    esiti = []
    for mid, desc, rel, vecchio, nuovo, test, filtro in MUTAZIONI:
        if SOLO and mid not in SOLO:
            continue
        p = RADICE / rel
        originale = p.read_bytes()
        prima = sha(p)
        testo = originale.decode("utf-8")
        if vecchio is None:                       # D8: la voce _v("postino_versioni", ...) per intero
            inizio = testo.index('    _v("postino_versioni", ')
            vecchio = testo[inizio:testo.index('    _v("lanci_action", ', inizio)]
        assert testo.count(vecchio) == 1, (mid, testo.count(vecchio))
        p.write_text(testo.replace(vecchio, nuovo), encoding="utf-8")
        try:
            cmd = [sys.executable, "-m", "pytest", *test, "-q", "-x", "-p", "no:cacheprovider"]
            if filtro:
                cmd += ["-k", filtro]
            r = subprocess.run(cmd, cwd=RADICE, capture_output=True, text=True, timeout=900)
            righe = [x for x in r.stdout.splitlines() if x.startswith(("FAILED ", "ERROR Betfair/"))]
        finally:
            p.write_bytes(originale)
        dopo = sha(p)
        esito = {"id": mid, "descrizione": desc, "file": rel, "filtro": filtro,
                 "rosso": r.returncode != 0, "primo_rosso": righe[0] if righe else r.stdout.splitlines()[-1:],
                 "sha256_prima": prima, "sha256_dopo": dopo, "ripristinato": prima == dopo}
        esiti.append(esito)
        print(json.dumps(esito, ensure_ascii=True), flush=True)
    rossi = sum(e["rosso"] for e in esiti)
    print(f"ROSSE {rossi}/{len(esiti)}, ripristinati {sum(e['ripristinato'] for e in esiti)}/{len(esiti)}")
    return 0 if rossi == len(esiti) and all(e["ripristinato"] for e in esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
