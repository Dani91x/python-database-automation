"""Falsificazione W1-C1: ogni mutazione deve far diventare ROSSO almeno un test; poi il file
torna identico (sha256). Uso: python falsifica_c1.py <radice del worktree>."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

RADICE = Path(sys.argv[1])
O = "Betfair/nucleo/ordini/"
T = O + "tests/"

MUTAZIONI = [
    ("M01 dedup tolto", O + "porta.py", "        if prima is not None:\n            self.conti[\"doppioni\"]",
     "        if False:\n            self.conti[\"doppioni\"]", T + "test_c1_porta.py"),
    ("M02 dedup persistente tolto (archivio ignorato)", O + "porta.py",
     "        riga = self._archivio.leggi(TABELLA_REF, {\"ref\": ref})\n        if riga is None:",
     "        riga = None\n        if riga is None:", T + "test_c1_porta.py"),
    ("M03 da_seq tolto (nessuna richiesta al buco)", O + "eventi.py",
     "        if self._sorgente is None or self._riparazione_in_corso:",
     "        if True:", T + "test_c1_porta.py " + T + "test_c1_eventi.py"),
    ("M04 controllo di contiguita' tolto", O + "eventi.py",
     "        if self._sopra:\n            self.buchi += 1\n            return True",
     "        if False:\n            self.buchi += 1\n            return True",
     T + "test_c1_porta.py " + T + "test_c1_eventi.py"),
    ("M05 ok all'esito ignoto", O + "porta.py", "ev = EventoOrdine(ref=r.ref, seq=0, fase=\"ignoto\"",
     "ev = EventoOrdine(ref=r.ref, seq=0, fase=\"accettato\"", T + "test_c1_porta.py"),
    ("M06 ritento di una mutazione", O + "porta.py",
     "        except Exception as ex:  # noqa: BLE001 - esito ignoto, si dice e si riconcilia\n",
     "        except Exception as ex:  # noqa: BLE001 - esito ignoto, si dice e si riconcilia\n"
     "            try:\n                self._esecutore.place(r)\n            except Exception:\n                pass\n",
     T + "test_c1_porta.py " + T + "test_c1_esecutore_runner.py"),
    ("M07 diario write-ahead dopo l'esecutore (inviato non scritto)", O + "porta.py",
     "            self._diario.scrivi({\"tipo\": \"inviato\"", "            (lambda *a, **k: None)({\"tipo\": \"inviato\"",
     T + "test_c1_porta.py"),
    ("M08 modo del servizio al posto della riga", O + "controlli.py",
     "    if r.modo not in servibili(proc):", "    if \"paper\" not in servibili(proc):",
     T + "test_c1_porta.py " + T + "test_c1_controlli.py"),
    ("M09 kill-switch anche sulle chiusure", O + "controlli.py",
     "    if freni.kill_switch() and not chiusura:", "    if freni.kill_switch():",
     T + "test_c1_porta.py " + T + "test_c1_controlli.py"),
    ("M10 tetto con < invece di <=", O + "controlli.py",
     "            if self.totale_ora <= self.tetto:", "            if self.totale_ora < self.tetto:",
     T + "test_c1_controlli.py"),
    ("M11 cancellazione riuscita contata", O + "controlli.py",
     "        elif azione == \"cancel\":\n            if esito == \"fallito\":",
     "        elif azione == \"cancel\":\n            if True:", T + "test_c1_controlli.py"),
    ("M12 contatore per attore invece che per conto", O + "porta.py",
     "        if self._contatore is not None and not self._contatore.consentito():",
     "        if self._contatore is not None and r.attore == \"safe\" and not self._contatore.consentito():",
     T + "test_c1_porta.py"),
    ("M13 seq globale invece che per attore", O + "porta.py",
     "            s = self._seq.get(attore, self._base_seq) + 1\n            self._seq[attore] = s",
     "            s = self._seq.get(\"*\", self._base_seq) + 1\n            self._seq[\"*\"] = s\n            self._seq[attore] = s",
     T + "test_c1_porta.py"),
    ("M14 scalper tennis con il minimo del calcio", O + "minimi.py",
     "MIN_STAKE_SCALPER_TENNIS = 2.0", "MIN_STAKE_SCALPER_TENNIS = 1.0", T + "test_c1_minimi.py"),
    ("M15 punta senza residuo (al centesimo)", O + "minimi.py",
     "        return VerdettoRunner(True, regola.importo, None, residuo=regola.residuo)",
     "        return VerdettoRunner(True, legale, None)", T + "test_c1_minimi.py " + T + "test_c1_porta.py"),
    ("M16 spezza_esatta tennis come lo scalper", O + "minimi.py",
     "        return diretta, round(s - diretta, 2)\n    return 0.0, s",
     "        return diretta, round(s - diretta, 2) if s - diretta >= 0.5 else 0.0\n    return 0.0, s",
     T + "test_c1_minimi.py"),
    ("M17 passo dello scalper per difetto", O + "minimi.py",
     "        size = round(round(size / size_step) * size_step, 2)",
     "        size = round(math.floor(size / size_step) * size_step, 2)", T + "test_c1_minimi.py"),
    ("M18 bump delle uscite tolto", O + "minimi.py",
     "        if size >= SOGLIA_BUMP_SCALPER:", "        if False:", T + "test_c1_minimi.py"),
    ("M19 FOK perso nel comando", O + "adattatore_comando.py",
     "        d[\"time_in_force\"] = r.time_in_force", "        d[\"time_in_force\"] = None",
     T + "test_c1_adattatore_comando.py"),
    ("M20 riduzione creduta dai params della coda", O + "adattatore_comando.py",
     "        riduce = bool(isinstance(params, dict) and params.get(\"reduces_liability\"))",
     "        riduce = False", T + "test_c1_adattatore_comando.py"),
    ("M21 handicap perso nella coda", O + "adattatore_comando.py",
     "        \"handicap\": r.handicap,\n        \"order_type\"", "        \"handicap\": 0.0,\n        \"order_type\"",
     T + "test_c1_adattatore_comando.py"),
    ("M22 esecutore: post_place trattato da rifiuto", O + "esecutori/runner.py",
     "        except ValueError as ex:\n            testo = str(ex)\n            if testo.startswith(PREFISSO_POST_PLACE):",
     "        except Exception as ex:\n            testo = str(ex)\n            if False:",
     T + "test_c1_esecutore_runner.py"),
    ("M23 esecutore: fase sbagliata", O + "esecutori/runner.py",
     "    \"accettato_betfair\": \"accettato\",", "    \"accettato_betfair\": \"abbinato\",",
     T + "test_c1_esecutore_runner.py"),
    ("M24 taglia rifiutata ritentata", O + "porta.py",
     "        if v.esito != \"submin\" and chiave in self._taglie_rifiutate:",
     "        if False:", T + "test_c1_porta.py"),
    ("M25 terminale sovrascritto da non terminale", O + "porta.py",
     "        if prima is not None and prima.fase in FASI_TERMINALI and ev.fase not in FASI_TERMINALI:\n            logger.info",
     "        if False:\n            logger.info", T + "test_c1_porta.py"),
    ("M26 archivio illeggibile = fail-open", O + "porta.py",
     "            return self._rifiuto_non_registrato(\n                ref, f\"{M_ARCHIVIO}: dedup per ref non verificabile",
     "            prima = None\n        if False:\n            return self._rifiuto_non_registrato(\n                ref, f\"{M_ARCHIVIO}: dedup per ref non verificabile",
     T + "test_c1_porta.py"),
    ("M27 invii non serializzati (dedup in corsa fra thread)", O + "porta.py",
     "        with self._lock_invio:\n            ricevuto", "        if True:\n            ricevuto",
     T + "test_c1_porta.py"),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    esiti = []
    for nome, file, vecchio, nuovo, test in MUTAZIONI:
        p = RADICE / file
        originale = p.read_bytes()
        h0 = sha(p)
        testo = originale.decode("ascii")
        assert testo.count(vecchio) == 1, (nome, testo.count(vecchio))
        p.write_bytes(testo.replace(vecchio, nuovo).encode("ascii"))
        try:
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                "-x", *test.split()], cwd=RADICE, capture_output=True,
                               text=True, timeout=900)
            rosso = r.returncode != 0
            coda = [x for x in r.stdout.splitlines() if x.strip()][-1:] if r.stdout else []
        finally:
            p.write_bytes(originale)
        h1 = sha(p)
        esiti.append({"mutazione": nome, "file": file, "rosso": rosso,
                      "riepilogo": coda[0] if coda else "", "sha256": h1,
                      "ripristinato": h0 == h1})
        print(f"{'ROSSO' if rosso else 'VERDE!!'}  {nome}  [{coda[0] if coda else ''}]  "
              f"ripristino {'ok' if h0 == h1 else 'KO'}", flush=True)
    rossi = sum(e["rosso"] for e in esiti)
    print(f"\n{rossi}/{len(esiti)} mutazioni rosse; ripristini ok: "
          f"{sum(e['ripristinato'] for e in esiti)}/{len(esiti)}")
    (Path(__file__).parent / "falsifica_c1.json").write_text(json.dumps(esiti, indent=1))
    return 0 if rossi == len(esiti) else 1


if __name__ == "__main__":
    raise SystemExit(main())
