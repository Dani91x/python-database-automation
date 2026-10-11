"""m3_mutazioni.py - la falsificazione di M-3 (registratore del canale e mappa).

Ogni mutazione reintroduce UN difetto (alcuni sono quelli trovati dalla
revisione indipendente dell'11/10) sul codice corretto, lancia i test del
modulo con ``-x`` e deve dare ROSSO. Il file mutato si ripristina SEMPRE
(anche su errore o interruzione) e alla fine si controlla l'impronta di ogni
file toccato contro quella di partenza.

    python ARCHITETTURA_2026-10/mappa/m3_mutazioni.py            (tutte)
    python ARCHITETTURA_2026-10/mappa/m3_mutazioni.py M1,R5      (solo alcune)

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

W = Path(__file__).resolve().parents[2]
LC = "Betfair/stream/local_channel.py"
RG = "Betfair/stream/registratore_canale.py"
MF = "Betfair/stream/mappa_flussi.py"
GZ = "Betfair/stream/gz_tollerante.py"
TR = "Betfair/stream/tests/test_registratore_canale_2026_10_11.py"
TM = "Betfair/stream/tests/test_mappa_flussi_2026_10_11.py"

MUT: List[Tuple[str, str, str, str, str]] = [
    # --- registratore -------------------------------------------------------
    ("M1 aggancio publish senza interruttore", LC,
     "            if _reg.ATTIVO:  # 11/10 (M-3): metadati del giro (thread del loop), mai decide",
     "            if True:  # mutazione", TR),
    ("M2 aggancio respond tolto", LC,
     "        if _reg.ATTIVO:  # 11/10 (M-3): esito del comando, mai decide\n"
     "            _reg.risposta(self, req.ws, text, \"respond\")\n", "", TR),
    ("M3 regola dei saltati sbagliata", RG,
     "            if in_volo.get(w, 0) > massimo:", "            if in_volo.get(w, 0) >= 0:", TR),
    ("M4 coda che ASPETTA", RG,
     "        if (len(_CODA) >= _CONF[\"coda_max\"]\n"
     "                or _CONTI[\"byte_in_coda\"] + peso > _CONF[\"coda_max_byte\"]):\n"
     "            _CONTI[\"scartati_coda\"] += 1\n            return\n",
     "        while len(_CODA) >= _CONF[\"coda_max\"]:\n            time.sleep(0.01)\n", TR),
    ("M5 scarto non contato", RG,
     "            _CONTI[\"scartati_coda\"] += 1\n            return\n", "            return\n", TR),
    ("M6 errore del disco propagato", RG,
     "            except Exception as e:  # noqa: BLE001 - disco pieno, permessi: contato, mai propagato",
     "            except ZeroDivisionError as e:  # noqa: BLE001", TR),
    ("M7 tetto che cancella oggi", RG,
     "if d.is_dir() and _giorno_valido(d.name) and d.name != oggi)",
     "if d.is_dir() and _giorno_valido(d.name))", TR),
    ("M8 campione mai salvato", RG,
     "        tieni = pieno or _CONF[\"campione\"] == 1 or (n % _CONF[\"campione\"] == 1)",
     "        tieni = pieno", TR),
    ("M9 niente mascheratura sul testo", RG,
     "    sospetto = any(s in basso for s in _SPIE)", "    sospetto = False", TR),
    ("M10 niente rotazione", RG,
     "        if oggi != self._giorno:\n            self._ruota(oggi)",
     "        if self._giorno is None:\n            self._ruota(oggi)", TR),
    ("M11 niente sospensione al tetto", RG,
     "        if not dentro and self._sospeso_per != oggi:", "        if False:", TR),
    ("M12 interruttore acceso con qualunque valore", RG,
     "    return (valore_env(ENV, file_env) or \"0\").strip() == \"1\"",
     "    return bool((valore_env(ENV, file_env) or \"\").strip())", TR),
    ("M13 banco non controllato al primo record", RG,
     "        if nel_banco():\n            _spegni_per_banco()\n            return\n", "", TR),
    ("M14 interruttore che costa anche da spento", LC,
     "            if _reg.ATTIVO:  # 11/10 (M-3): metadati del giro (thread del loop), mai decide",
     "            if _reg.ATTIVO or sum(range(3000)) < 0:  # mutazione", TR),
    ("M15 file di ambiente ignorato", RG,
     "    return leggi_file_env(file_env).get(nome, \"\")", "    return \"\"", TR),
    ("M16 composizione dei client mai scritta", RG,
     "        if _FIRME.get(ch.port) != numeri:", "        if False:", TR),
    ("M17 append su file esistente (il difetto dell'11/10)", RG,
     "            return gzip.open(p, \"xb\", compresslevel=6), p",
     "            return gzip.open(d / (base + SUFFISSO_FILE), \"ab\", compresslevel=6), p", TR),
    ("M18 nessuna chiusura all'uscita del processo", RG,
     "                atexit.register(_all_uscita)", "                pass", TR),
    ("M19 fork: il figlio tiene i file del padre", RG,
     "    os.register_at_fork(after_in_child=_nel_figlio)", "    pass", TR),
    ("M20 payload riletti col json (il GIL dell'11/10)", RG,
     "    if ok and verificare:", "    if ok:", TR),
    ("M21 coda senza tetto in byte", RG,
     "                or _CONTI[\"byte_in_coda\"] + peso > _CONF[\"coda_max_byte\"]):",
     "                or False):", TR),
    ("M22 numero del client = id riusabile", RG,
     "        n = _NUMERI.get(ws)\n        if n is None:\n            with _LOCK_CONTI:\n"
     "                n = _NUMERI.get(ws)\n                if n is None:\n"
     "                    n = _NUMERI[ws] = next(_PROSSIMO_CLIENTE)\n        return n",
     "        return id(ws) % 1000003", TR),
    ("M23 lettura non tollerante (gzip.open)", GZ,
     "        uscita, intero, dopo = _membro(dati, inizio, n)",
     "        import gzip as _g\n        yield _g.decompress(dati)\n        return\n"
     "        uscita, intero, dopo = _membro(dati, inizio, n)", TR),
    ("M24 guasto: tutto l'output di zlib (anche quello inventato)", GZ,
     "        uscita, _i, _d = _membro(dati, inizio, limite)",
     "        uscita, _i, _d = _membro(dati, inizio, n)", TR),
    # --- dalla revisione indipendente (sopravvissute al primo giro) -----------
    ("R1 token tolto dalle chiavi sensibili", RG,
     "    \"key\", \"x-authentication\", \"x-application\", \"token\", ",
     "    \"key\", \"x-authentication\", \"x-application\", ", TR),
    ("R3 _ripulisci non entra nelle liste", RG,
     "    if isinstance(obj, list):\n        return [_ripulisci(v, conta) for v in obj]",
     "    if isinstance(obj, list):\n        return obj", TR),
    ("R5 confine dei saltati >= invece di >", RG,
     "            if in_volo.get(w, 0) > massimo:", "            if in_volo.get(w, 0) >= massimo:", TR),
    ("R13 guardia di pytest tolta", RG,
     "        if in_pytest() and not _consenti_in_test:\n            return False\n", "", TR),
    ("R7 giorno UTC al posto del locale", RG,
     "    return datetime.fromtimestamp(time.time() if epoca_s is None else epoca_s).strftime(\"%Y-%m-%d\")",
     "    return time.strftime(\"%Y-%m-%d\", time.gmtime(time.time() if epoca_s is None else epoca_s))",
     TR),
    # --- mappa -----------------------------------------------------------------
    ("MA percentile spostato", MF,
     "    k = max(0, min(len(v) - 1, int(-(-p * len(v) // 100)) - 1))",
     "    k = max(0, min(len(v) - 1, int(p * len(v) // 100)))", TM),
    ("MB esito: ack letto come ok", MF,
     "        ok = bool(ed.get(\"accettato\")) if em.get(\"t\") == \"ack\" else bool(em.get(\"ok\"))",
     "        ok = bool(em.get(\"ok\"))", TM),
    ("MC esito = primo candidato senza il tempo", MF,
     "        esito = next((t for t in cand if id(t) not in usate\n"
     "                      and t.get(\"mono_ns\", 0) >= c.get(\"mono_ns\", 0)), None)",
     "        esito = cand[0] if cand else None", TM),
    ("MD scarti in coda alla sequenza ignorati", MF,
     "        ultimo = max(seq[-1] if seq else 0,\n"
     "                     int((pr[\"stato\"] or {}).get(\"seq_prossimo\") or 1) - 1)",
     "        ultimo = seq[-1] if seq else 0", TM),
    ("ME processi con chiave solo porta", MF,
     "            pr = processi.setdefault((porta, pid, av), {",
     "            pr = processi.setdefault((porta, 0, 0), {", TR),
    ("MF accoppiamento senza il client", MF,
     "            cand = per_id.get(vita + (c.get(\"cliente\"), m.get(\"id\")), [])",
     "            cand = [t for k, v in per_id.items() if k[-1] == m.get(\"id\") for t in v]", TM),
    ("MG composizione: genere perso", MF,
     "            k2 = (str(c[1]), str(c[2] if c[2] is not None else \"-\"))",
     "            k2 = (\"desktop\", \"-\")", TM),
    ("MH cadenza che mescola i processi", MF,
     "                t[\"mono\"].setdefault((pid, av), []).append(r[\"mono_ns\"] / 1e6)",
     "                t[\"mono\"].setdefault(0, []).append(r[\"mono_ns\"] / 1e6)", TR),
    ("MI paper e live sommati", MF,
     "        chiave = (c.get(\"porta\"), str(c.get(\"genere\")), _metodo(c), _modo(c))",
     "        chiave = (c.get(\"porta\"), str(c.get(\"genere\")), _metodo(c), \"-\")", TM),
    ("ML raw senza filtro del giorno", MF,
     "        if not (a <= pt < b):\n            continue\n", "", TM),
    ("MM fonte mancante non detta", MF,
     "        out[\"mancante\"] = \"cartella non indicata (--ordini): i file di M-1 non sono letti\"\n",
     "        out[\"file\"] = []\n", TM),
    ("MN M-1: una sola cartella UTC", MF,
     "    while g <= ultima:", "    while g <= prima:", TM),
    ("MO M-1: righe fuori dal giorno locale contate", MF,
     "            if not (a <= t < b):\n                continue\n            genere = _genere_riga(r)",
     "            genere = _genere_riga(r)", TM),
    ("MP M-1: durata della REST dall'orologio sbagliato", MF,
     "                    v[\"durate\"].append((rep_us - r[\"ep_us\"]) / 1000.0)",
     "                    v[\"durate\"].append((rep_us - r[\"ep_us\"]) / 1.0)", TM),
    ("MQ UI -> REST: anche il paper", MF,
     "        if c.get(\"modo\") != \"live\" or c.get(\"epoca_ms\") is None:",
     "        if c.get(\"epoca_ms\") is None:", TM),
    ("MR lettore di M-1 ignorato anche se c'e'", MF,
     "    if not all(hasattr(m, n) for n in (\"leggi_file\", \"analizza_giorni\", \"formatta\")):",
     "    if True:", TM),
    ("MS M-1: decisioni paper e live sommate", MF,
     "                genere = \"dec:%s\" % (str(r.get(\"mode\") or \"-\").lower())",
     "                genere = \"dec:-\"", TM),
]


def _impronta(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    scelte = set(sys.argv[1].split(",")) if len(sys.argv) > 1 else None
    toccati = {f for _n, f, _a, _b, _t in MUT}
    impronte = {f: _impronta(W / f) for f in toccati}
    esiti = []
    for nome, f, a, b, test in MUT:
        if scelte and nome.split()[0] not in scelte:
            continue
        p = W / f
        orig = p.read_text()
        if orig.count(a) != 1:
            esiti.append((nome, "TESTO NON TROVATO", ""))
            continue
        try:
            p.write_text(orig.replace(a, b))
            r = subprocess.run([sys.executable, "-m", "pytest", test, "-q", "-x",
                                "-p", "no:cacheprovider"], cwd=W, capture_output=True,
                               text=True, timeout=600)
            righe = [x for x in r.stdout.splitlines() if x.strip()]
            esiti.append((nome, "ROSSO" if r.returncode != 0 else "VERDE (!!)",
                          righe[-1] if righe else ""))
        except subprocess.TimeoutExpired:
            esiti.append((nome, "ROSSO (scadenza)", ""))
        finally:
            p.write_text(orig)
    for e in esiti:
        print("%-58s %-17s %s" % e)
    integri = all(_impronta(W / f) == h for f, h in impronte.items())
    print("file ripristinati identici:", integri)
    verdi = [e for e in esiti if not e[1].startswith("ROSSO")]
    return 0 if integri and not verdi else 1


if __name__ == "__main__":
    raise SystemExit(main())
