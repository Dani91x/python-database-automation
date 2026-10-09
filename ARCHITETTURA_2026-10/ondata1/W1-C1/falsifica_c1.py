"""Falsificazione W1-C1: ogni mutazione deve far diventare ROSSO almeno un test dei
``tests/test_c1_*.py``; poi il file torna identico (sha256).

Uso: ``python falsifica_c1.py <radice del worktree> [ID ...]`` (senza ID: tutte).
M01-M27 = consegna del 09/10; M28-M47 = correzioni dopo la revisione; V* = mutazioni del
revisore indipendente (``rev_w1c1/mut.py``) riportate sul codice corretto.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

RADICE = Path(sys.argv[1])
SOLO = set(sys.argv[2:])
O = "Betfair/nucleo/ordini/"
P, C, E, MI, A, R = (O + "porta.py", O + "controlli.py", O + "eventi.py", O + "minimi.py",
                     O + "adattatore_comando.py", O + "esecutori/runner.py")

MUTAZIONI = [
    # ------------------------------------------------------------ consegna 09/10
    ("M01", "dedup tolto", P, "            prima = self._dedup(ref)\n",
     "            self._dedup(ref)\n            prima = None\n"),
    ("M02", "dedup persistente tolto (archivio e prenotazione ignorati)", P,
     "        riga = self._dall_archivio(ref)\n        if riga is None:\n"
     "            if self._archivio.transizione(TABELLA_REF, {\"ref\": ref}, \"\", self._padrone):",
     "        riga = None\n        if riga is None:\n            if True:"),
    ("M03", "da_seq tolto (nessuna richiesta al buco)", E,
     "        if self._sorgente is None or self._riparazione_in_corso:", "        if True:"),
    ("M04", "controllo di contiguita' tolto", E,
     "        if self._sopra:\n            self.buchi += 1\n            return True",
     "        if False:\n            self.buchi += 1\n            return True"),
    ("M05", "ok all'esito ignoto", P, "ev = EventoOrdine(ref=r.ref, seq=0, fase=\"ignoto\"",
     "ev = EventoOrdine(ref=r.ref, seq=0, fase=\"accettato\""),
    ("M06", "ritento di una mutazione", P,
     "        except Exception as ex:  # noqa: BLE001 - esito ignoto, si dice e si riconcilia\n",
     "        except Exception as ex:  # noqa: BLE001 - esito ignoto, si dice e si riconcilia\n"
     "            try:\n                self._esecutore.place(r)\n            except Exception:\n"
     "                pass\n"),
    ("M07", "diario write-ahead tolto (inviato non scritto)", P,
     "                self._diario.scrivi({\"tipo\": \"inviato\"",
     "                (lambda *a, **k: None)({\"tipo\": \"inviato\""),
    ("M08", "modo del servizio al posto della riga", C, "    if r.modo not in servibili(proc):",
     "    if \"paper\" not in servibili(proc):"),
    ("M09", "kill-switch anche sulle chiusure", C, "    if freni.kill_switch() and not chiusura:",
     "    if freni.kill_switch():"),
    ("M10", "tetto con < invece di <=", C, "            if self.totale_ora <= self.tetto:",
     "            if self.totale_ora < self.tetto:"),
    ("M11", "cancellazione riuscita contata", C,
     "        elif azione == \"cancel\":\n            if esito == \"fallito\":",
     "        elif azione == \"cancel\":\n            if True:"),
    ("M12", "contatore per attore invece che per conto", P,
     "        if contatore is not None and not contatore.consentito():",
     "        if contatore is not None and r.attore == \"safe\" and not contatore.consentito():"),
    ("M13", "seq globale invece che per attore", P,
     "        s = self._seq.get(attore, self._base_seq) + 1\n        self._seq[attore] = s",
     "        s = self._seq.get(\"*\", self._base_seq) + 1\n        self._seq[\"*\"] = s\n"
     "        self._seq[attore] = s"),
    ("M14", "scalper tennis con il minimo del calcio", MI, "MIN_STAKE_SCALPER_TENNIS = 2.0",
     "MIN_STAKE_SCALPER_TENNIS = 1.0"),
    ("M15", "punta senza residuo (al centesimo)", MI,
     "        return VerdettoRunner(True, regola.importo, None, residuo=regola.residuo)",
     "        return VerdettoRunner(True, legale, None)"),
    ("M16", "spezza_esatta tennis come lo scalper", MI,
     "        return diretta, round(s - diretta, 2)\n    return 0.0, s",
     "        return diretta, round(s - diretta, 2) if s - diretta >= 0.5 else 0.0\n"
     "    return 0.0, s"),
    ("M17", "passo dello scalper per difetto", MI,
     "        size = round(round(size / size_step) * size_step, 2)",
     "        size = round(math.floor(size / size_step) * size_step, 2)"),
    ("M18", "bump delle uscite tolto", MI, "        if size >= SOGLIA_BUMP_SCALPER:",
     "        if False:"),
    ("M19", "FOK perso nel comando", A, "        d[\"time_in_force\"] = r.time_in_force",
     "        d[\"time_in_force\"] = None"),
    ("M20", "riduzione creduta dai params della coda", A,
     "        riduce = bool(isinstance(params, dict) and params.get(\"reduces_liability\"))",
     "        riduce = False"),
    ("M21", "handicap perso nella coda", A,
     "        \"handicap\": r.handicap,\n        \"order_type\"",
     "        \"handicap\": 0.0,\n        \"order_type\""),
    ("M22", "esecutore: post_place trattato da rifiuto", R,
     "        except ValueError as ex:\n            errore = str(ex)",
     "        except Exception as ex:\n            errore = str(ex)"),
    ("M23", "esecutore: fase sbagliata", R, "    \"accettato_betfair\": \"accettato\",",
     "    \"accettato_betfair\": \"abbinato\","),
    ("M24", "taglia rifiutata ritentata", P, "        if chiave in self._taglie_rifiutate:",
     "        if False:"),
    ("M25", "terminale sovrascritto", P,
     "    if prima.fase in FASI_TERMINALI:\n        return True",
     "    if False:\n        return True"),
    ("M26", "archivio illeggibile = fail-open", P,
     "            return self._rifiuto_non_registrato(\n"
     "                ref, f\"{M_ARCHIVIO}: dedup per ref non verificabile",
     "            prima = None\n        if False:\n            return self._rifiuto_non_registrato(\n"
     "                ref, f\"{M_ARCHIVIO}: dedup per ref non verificabile"),
    ("M27", "invii non serializzati", P,
     "            with self._lock_invio:\n                return self._invia(r, extra)",
     "            if True:\n                return self._invia(r, extra)"),
    # ------------------------------------------------------------ correzioni dopo la revisione
    ("M28", "il paper usa il contatore del live (tetto)", P,
     "        contatore = self._contatori.get(r.modo)\n        if contatore is not None and not",
     "        contatore = self._contatori.get(\"live\")\n        if contatore is not None and not"),
    ("M29", "il paper contato nel contatore del live", P,
     "        contatore = self._contatori.get(r.modo)\n        if contatore is not None:\n",
     "        contatore = self._contatori.get(\"live\")\n        if contatore is not None:\n"),
    ("M30", "params persi verso il dispatch", R,
     "            r, ExtraComando(params=dict(params)) if params else None))",
     "            r, None))"),
    ("M31", "params accettati da un esecutore che non li serve", P,
     "        if params and not getattr(self._esecutore, \"accetta_params\", False):",
     "        if False:"),
    ("M32", "consegna dentro il lucchetto (deadlock)", P,
     "            if not self._lock_consegna.acquire(blocking=False):",
     "            if not self._lock_consegna.acquire():"),
    ("M33", "prenotazione orfana di questa porta mai ripresa (ack fantasma)", P,
     "        if riga is not None and riga.get(\"stato\") == self._padrone:",
     "        if False:"),
    ("M34", "archivio KO dopo 'inviato' senza riga di chiusura", P,
     "motivo=f\"{M_ARCHIVIO}: {str(ex)[:160]}\"), chiudi_diario=True)",
     "motivo=f\"{M_ARCHIVIO}: {str(ex)[:160]}\"), chiudi_diario=False)"),
    ("M35", "ignoto chiude il ref al riavvio", P,
     "            if st is None or st.fase == \"ignoto\":", "            if st is None:"),
    ("M36", "abbinato che cala accettato", P,
     "    return float(ev.abbinato) < float(prima.abbinato) - _EPS", "    return False"),
    ("M37", "seq assegnato fuori dalla sezione che memorizza", P,
     "        with self._lock:\n            if tipo == \"evento\" and _stantio",
     "        if True:\n            if tipo == \"evento\" and _stantio"),
    ("M38", "dedup non atomico fra due porte", P,
     "            if self._archivio.transizione(TABELLA_REF, {\"ref\": ref}, \"\", self._padrone):",
     "            if True:"),
    ("M39", "tennis non portato al minimo", P,
     "        if r.sport == \"tennis\" and not r.riduce_esposizione:", "        if False:"),
    ("M40", "replace con riduzione che scavalca il kill-switch", C,
     "    riduce = isinstance(r, RichiestaOrdine) and r.azione == \"place\" \\\n",
     "    riduce = isinstance(r, RichiestaOrdine) \\\n"),
    ("M41", "seq indietro dopo il riavvio (blocco ignorato)", P,
     "                massimo = max(massimo, int(riga.get(\"fino_a\") or 0))",
     "                pass"),
    ("M42", "lato maiuscolo nella taglia rifiutata", P,
     "            self._taglie_rifiutate[(rr.modo, str(rr.lato).lower(),",
     "            self._taglie_rifiutate[(rr.modo, str(rr.lato),"),
    ("M43", "contatore che solleva dopo l'invio", P,
     "            except Exception as ex:  # noqa: BLE001 - l'ordine e' partito: l'esito si scrive",
     "            except ZeroDivisionError as ex:  # noqa: BLE001 - l'ordine e' partito: l'esito si scrive"),
    ("M44", "memoria senza limite", P, "    while len(d) > limite:", "    while False:"),
    ("M45", "consumatore: terminale dopo terminale (regola di Safe)", E,
     "if prima is not None and (ev.seq <= prima.seq or terminale(prima)\n",
     "if prima is not None and (ev.seq <= prima.seq or (terminale(prima) and not terminale(ev))\n"),
    ("M46", "politica desktop: punta troncata invece che rifiutata", MI,
     "    if str(lato).upper() == \"BACK\" and float(v.residuo or 0.0) > 0.0:\n        sotto",
     "    if False:\n        sotto"),
    ("M47", "write-ahead non durevole (niente fsync)", P,
     "                                     \"ack\": _ack_in_riga(ack, r.attore, 0)})\n"
     "            except Exception as ex:  # noqa: BLE001 - fail-closed: senza diario niente ordine",
     "                                     \"ack\": _ack_in_riga(ack, r.attore, 0)}, durevole=False)\n"
     "            except Exception as ex:  # noqa: BLE001 - fail-closed: senza diario niente ordine"),
    # ------------------------------------------------------------ mutazioni del revisore
    ("V11", "ignoto contato come transazione", P,
     "        if ev.fase == \"ignoto\":\n            return\n        if ev.fase == \"rifiutato\":",
     "        if False:\n            return\n        if ev.fase == \"rifiutato\":"),
    ("V23", "runner: ok False non diventa rifiutato", R,
     "        if result.get(\"ok\") is False:\n            fase = \"rifiutato\"",
     "        if False:\n            fase = \"rifiutato\""),
    ("V43", "rifiuto locale contato come transazione", P,
     "            if _codice_betfair(ev.codice_errore):", "            if True:"),
    ("V52", "runner: parziale mappato su abbinato", R,
     "    \"abbinato_parziale\": \"parziale\",", "    \"abbinato_parziale\": \"abbinato\","),
    ("V53", "runner: prezzo medio sempre None", R,
     "            prezzo_medio=(_f(specchio.get(\"average_price_matched\")) or None),",
     "            prezzo_medio=None,"),
    ("V54", "runner: abbinato sempre 0", R,
     "            abbinato=_f(specchio.get(\"size_matched\")),", "            abbinato=0.0,"),
    ("V56", "runner: customerStrategyRef non impostato", R,
     "        M.MotoreOrdini._imposta_contesto(self._come_motore, r.attore, hook)",
     "        M.MotoreOrdini._imposta_contesto(self._come_motore, None, hook)"),
    ("V57", "runner: modo della riga sostituito dal live", R,
     "low._dispatch(lsb, self._flumine, riga, r.modo, self._strategie)",
     "low._dispatch(lsb, self._flumine, riga, 'live', self._strategie)"),
    ("V58", "ack accettato non pubblicato", P,
     "            self.conti[\"accettate\"] += 1\n            self._memorizza(r.attore, ack)",
     "            self.conti[\"accettate\"] += 1"),
    ("V59", "notifica: ref sconosciuto accettato", P,
     "                attore = self._attore_di_ref.get(ev.ref)",
     "                attore = self._attore_di_ref.get(ev.ref) or 'safe'"),
    ("V60", "stato: abbinato e residuo scambiati", P,
     "            abbinato=float(ev.abbinato), residuo=float(ev.residuo),",
     "            abbinato=float(ev.residuo), residuo=float(ev.abbinato),"),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    esiti = []
    for ident, nome, file, vecchio, nuovo in MUTAZIONI:
        if SOLO and ident not in SOLO:
            continue
        p = RADICE / file
        originale = p.read_bytes()
        h0 = sha(p)
        testo = originale.decode("ascii")
        assert testo.count(vecchio) == 1, (ident, testo.count(vecchio))
        p.write_bytes(testo.replace(vecchio, nuovo).encode("ascii"))
        try:
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                "-x", O + "tests/"], cwd=RADICE, capture_output=True,
                               text=True, timeout=900)
            rosso = r.returncode != 0
            presa = [x for x in r.stdout.splitlines() if x.startswith("FAILED")][:1]
            coda = [x for x in r.stdout.splitlines() if x.strip()][-1:] if r.stdout else []
        except subprocess.TimeoutExpired:
            rosso, presa, coda = True, ["TIMEOUT (blocco)"], [""]
        finally:
            p.write_bytes(originale)
        h1 = sha(p)
        esiti.append({"id": ident, "mutazione": nome, "file": file, "rosso": rosso,
                      "presa_da": presa[0][7:] if presa else "", "riepilogo": coda[0] if coda else "",
                      "sha256": h1, "ripristinato": h0 == h1})
        print(f"{'ROSSO' if rosso else 'VERDE!!'}  {ident} {nome}  [{presa[0][7:100] if presa else ''}]"
              f"  ripristino {'ok' if h0 == h1 else 'KO'}", flush=True)
    rossi = sum(e["rosso"] for e in esiti)
    print(f"\n{rossi}/{len(esiti)} mutazioni rosse; ripristini ok: "
          f"{sum(e['ripristinato'] for e in esiti)}/{len(esiti)}")
    if not SOLO:
        (Path(__file__).parent / "falsifica_c1.json").write_text(json.dumps(esiti, indent=1))
    return 0 if rossi == len(esiti) else 1


if __name__ == "__main__":
    raise SystemExit(main())
