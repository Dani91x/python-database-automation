"""Falsificazione dei test dell'AUTO-FOLLOW (25/09): ogni mutazione rimette un
difetto nel codice di produzione, i test devono diventare ROSSI; il file viene
ripristinato dai BYTE salvati (mai git checkout) e verificato con sha1.

    python AUDIT_2026-09-25/mutazioni_auto_follow.py [--banco]

``--banco`` aggiunge il profilo rapido vero (test_strada_unica, ~20 s) alle
mutazioni marcate. Ambiente: SUPABASE_URL=http://127.0.0.1:9 (sandbox).
"""
import hashlib
import io
import os
import subprocess
import sys

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T_AF = "Betfair/stream/tests/test_auto_follow_2026_09_25.py"
T_BANCO = ("Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py"
           "::test_profilo_rapido_verde_sulla_registrazione_vera")

MUTAZIONI = [
    ("M1 motore: niente aggancio (mercato non seguito eseguito subito)",
     "Betfair/stream/motore_ordini.py",
     "        if not in_fila and ag.servibile(mid):\n            return None\n",
     "        if True:\n            return None\n", True),
    ("M2 servibile anche col book STANTIO",
     "Betfair/stream/auto_follow.py",
     "                if libro is None or id(libro) == prima:\n                    return False\n",
     "                if libro is None:\n                    return False\n", False),
    ("M3 niente fila FIFO per mercato",
     "Betfair/stream/motore_ordini.py",
     "        in_fila = any(p[\"market_id\"] == mid for p in self._in_aggancio.values())\n",
     "        in_fila = False\n", False),
    ("M4 l'aggancio non scade mai (comando parcheggiato per sempre)",
     "Betfair/stream/motore_ordini.py",
     "            elif ora > p[\"scadenza_ms\"]:\n",
     "            elif False:\n", True),
    ("M5 guardie NON rifatte all'esecuzione",
     "Betfair/stream/motore_ordini.py",
     "                    self._controlla(p[\"piano\"], p[\"ricevuto_ms\"])\n",
     "                    pass\n", False),
    ("M6 protezione di chi ha ordini tolta",
     "Betfair/stream/auto_follow.py",
     "            if ha_ordini:\n                out.add(chiave)\n",
     "            if False:\n                out.add(chiave)\n", True),
    ("M7 espulsione senza guardare la priorita'",
     "Betfair/stream/auto_follow.py",
     "                     if k != chiave and k not in protetti and x.priorita <= priorita),\n",
     "                     if k != chiave and k not in protetti),\n", False),
    ("M8 stream_id NON aggiornato dopo la risottoscrizione",
     "Betfair/stream/auto_follow.py",
     "        stream.stream_id = nuovo\n        stream.market_filter = filtro",
     "        stream.stream_id = vecchio\n        stream.market_filter = filtro", False),
    ("M9 riga live_follow scritta sovrascrivendo il follow dell'utente",
     "Betfair/stream/auto_follow.py",
     "            sb.table(\"live_follow\").upsert(riga, on_conflict=\"event_id\",\n"
     "                                            ignore_duplicates=True).execute()\n",
     "            sb.table(\"live_follow\").upsert(riga, on_conflict=\"event_id\").execute()\n",
     False),
    ("M10 righe auto STREAMING trattate come follow manuali (ricostruzione)",
     "Betfair/stream/runner.py",
     "        if (auto is not None and str(f.get(\"status\") or \"\") == \"STREAMING\"\n"
     "                and auto.segue_auto(ev)):\n            continue\n",
     "", False),
    ("M11 feed muto: tolte le candidate",
     "Betfair/stream/auto_follow.py",
     "            return                               # feed muto: non si toglie niente\n",
     "            righe = []\n", False),
    ("M12 runner fermo: nessuna richiesta di aggancio",
     "Betfair/stream/motore_ordini.py",
     "            if (self._aggancio is not None and piano.get(\"azione\") in AZIONI_CON_AGGANCIO\n",
     "            if (False and piano.get(\"azione\") in AZIONI_CON_AGGANCIO\n", False),
    ("M13 cancel aggancia anche lui",
     "Betfair/stream/motore_ordini.py",
     "AZIONI_CON_AGGANCIO = frozenset({\"place\", \"greenup\"})\n",
     "AZIONI_CON_AGGANCIO = frozenset({\"place\", \"greenup\", \"cancel\"})\n", False),
    ("M14 un comando espelle anche i follow manuali",
     "Betfair/stream/auto_follow.py",
     "            self._manuali = {str(e): {str(m) for m in ms} for e, ms in per_evento.items()}\n",
     "            self._manuali = {}\n", True),
    ("M15 comando appena chiesto NON protetto (il suo parcheggio scadrebbe)",
     "Betfair/stream/auto_follow.py",
     "            if v.priorita == PRI_COMANDO and ora - v.ultimo_uso < PROTEZIONE_COMANDO_S:\n",
     "            if False:\n", False),
    ("M16 mercato mai arrivato resta nel tetto per sempre",
     "Betfair/stream/auto_follow.py",
     "                        chiusi.append(mid)       # mai arrivato / tolto da flumine\n",
     "                        pass\n", False),
]


def _sha(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def _pytest(bersagli):
    env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9",
               SUPABASE_SERVICE_ROLE_KEY="x", SUPABASE_KEY="x")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "-x"] + bersagli, cwd=RADICE, env=env, capture_output=True,
                       text=True, timeout=600)
    ultima = [ln for ln in r.stdout.splitlines() if ln.strip()][-1:] or ["?"]
    return r.returncode, ultima[0]


def main() -> int:
    banco = "--banco" in sys.argv
    righe = []
    rc0, ult = _pytest([T_AF])
    righe.append("BASE (senza mutazioni): rc=%d %s" % (rc0, ult))
    ko = 0
    for nome, rel, vecchio, nuovo, usa_banco in MUTAZIONI:
        f = os.path.join(RADICE, rel)
        orig = io.open(f, "rb").read()
        sha0 = _sha(orig)
        testo = orig.decode("utf-8").replace("\r\n", "\n")
        if testo.count(vecchio) != 1:
            righe.append("%s: ANCORA NON TROVATA (%d)" % (nome, testo.count(vecchio)))
            ko += 1
            continue
        mut = testo.replace(vecchio, nuovo)
        if b"\r\n" in orig:
            mut = mut.replace("\n", "\r\n")
        try:
            io.open(f, "wb").write(mut.encode("utf-8"))
            rc, ult = _pytest([T_AF])
            if banco and usa_banco:
                # il profilo rapido VERO da solo (senza -x sui test unitari prima)
                rcb, ultb = _pytest([T_BANCO])
                ult += " | banco: %s %s" % ("ROSSO" if rcb else "VERDE (!!)", ultb)
                rc = rc and rcb
        finally:
            io.open(f, "wb").write(orig)
        ripristino = _sha(io.open(f, "rb").read()) == sha0
        esito = "ROSSO" if rc != 0 else "VERDE (!!)"
        if rc == 0 or not ripristino:
            ko += 1
        righe.append("%s: %s  [%s]  ripristino sha1 %s" % (
            nome, esito, ult, "OK" if ripristino else "FALLITO"))
    rc1, ult1 = _pytest([T_AF])
    righe.append("DOPO (codice ripristinato): rc=%d %s" % (rc1, ult1))
    for r in righe:
        print(r)
    return 1 if (ko or rc0 or rc1) else 0


if __name__ == "__main__":
    sys.exit(main())
