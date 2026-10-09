"""Mutazioni di W1-B (comparto B, stato della partita): ogni mutazione deve far
diventare ROSSO almeno un test del comparto.

Uso (dalla radice del repository):
    python ARCHITETTURA_2026-10/ondata1/W1-B/mutazioni.py .

Per ogni mutazione: sha256 del file, sostituzione esatta (UNA sola occorrenza,
altrimenti ERRORE), test indicati (``-m "not cert"``), ripristino dei byte
originali, sha256 ricontrollato. Una riga per mutazione e il totale in coda.
Le prime 29 sono quelle della consegna ``be3cf075`` (adeguate alle righe
cambiate dalle correzioni); poi quelle della prima revisione (``67775f35``) e
della seconda (``e330fdb5``) e della terza (la coda delle consegne).
"""
import hashlib
import os
import subprocess
import sys

R = sys.argv[1] if len(sys.argv) > 1 else "."
B = "Betfair/nucleo/stato_partita/"
T = B + "tests/"
CAL, FRE, SER = T + "test_b_calcolo.py", T + "test_b_freschezza.py", T + "test_b_servizio.py"
ADA, COR, IMP = T + "test_b_adattatori.py", T + "test_b_correzioni.py", T + "test_b_import_innocuo.py"
SEC = T + "test_b_seconda_revisione.py"
TER = T + "test_b_terza_revisione.py"

MUT = [
    # --- consegna be3cf075 -------------------------------------------------
    ("B5-1 riga_s sempre 0", B + "freschezza.py",
     "    return _scan_feed().row_age_sec(dict(riga), adesso_s)", "    return 0.0", [FRE]),
    ("B5-2 ritardo IPS tolto", B + "freschezza.py",
     "    return None if eta is None else eta + ritardo_ips_s()",
     "    return None if eta is None else eta", [FRE]),
    ("B5-3 scanner vivo tolto dalla regola", B + "adattatori/ips.py",
     "payload = _scan_feed().fresh_payload(riga, self.max_age_sec, scanner_age_sec=scanner_s)",
     "payload = _scan_feed().fresh_payload(riga, self.max_age_sec, scanner_age_sec=None)", [ADA]),
    ("B5-4 dato assente = fresco", B + "freschezza.py",
     "    return _scan_feed().row_age_sec(dict(riga), adesso_s)",
     "    eta = _scan_feed().row_age_sec(dict(riga), adesso_s)\n    return 0.0 if eta is None else eta", [FRE]),
    ("stato IPS anche da status", B + "calcolo.py",
     '    return grezzo.get("matchStatus") if isinstance(grezzo, Mapping) else None',
     '    return (grezzo.get("matchStatus") or grezzo.get("status")) if isinstance(grezzo, Mapping) else None',
     [CAL]),
    ("intervallo letto come 2t", B + "calcolo.py",
     '"pre": "pre", "1t": "1t", "ht": "intervallo", "2t": "2t", "finita": "finita",\n}',
     '"pre": "pre", "1t": "1t", "ht": "2t", "2t": "2t", "finita": "finita",\n}', [CAL]),
    ("supplementari non distinti", B + "calcolo.py",
     '            return "supplementari"', '            return "2t"', [CAL]),
    ("tempo senza minuto", B + "calcolo.py",
     "        minuto=snap.minute, tempo=tempo_partita(grezzo, snap.minute),",
     "        minuto=snap.minute, tempo=tempo_partita(grezzo, None),", [CAL]),
    ("rossi scambiati", B + "calcolo.py",
     "        rossi=coppia(snap.red_home, snap.red_away),",
     "        rossi=coppia(snap.red_away, snap.red_home),", [CAL]),
    ("riga: minuto ricalcolato dallo score_raw", B + "calcolo.py",
     '    minuto = _intero_o_none(payload.get("minute"))',
     '    minuto = _intero_o_none((payload.get("score_raw") or {}).get("timeElapsed"))', [CAL]),
    ("ko: cache per mercato tolta (KO spostato seguito)", B + "calcolo.py",
     "        cached = self._ko_ms.get(mid)\n        if cached is not None:\n            return cached",
     "        cached = None", [CAL]),
    ("ko: cache unica diventata per mercato", B + "calcolo.py",
     "        if self._ko_ms is not None:\n            return self._ko_ms\n        self._ko_ms = ko_epoch_ms(market_book)",
     "        self._ko_ms = ko_epoch_ms(market_book)", [CAL]),
    ("ko: naive non piu' UTC", B + "calcolo.py",
     "            mt = mt.replace(tzinfo=_dt.timezone.utc)\n        return float(mt.timestamp()) * 1000.0",
     "            pass\n        return float(mt.timestamp()) * 1000.0", [CAL]),
    ("tennis: pressione sempre falsa", B + "calcolo.py",
     "        pressione=bool(ts.point_pressure),", "        pressione=False,", [CAL]),
    ("tennis: chiave senza servizio", B + "calcolo.py",
     "            set_game.punto[0], set_game.punto[1], set_game.servizio)",
     "            set_game.punto[0], set_game.punto[1], None)", [CAL]),
    ("servizio: gol anche quando scende", B + "servizio.py",
     "sum(dopo.gol) > sum(prima.gol)", "sum(dopo.gol) != sum(prima.gol)", [SER]),
    ("servizio: firma con le eta'", B + "servizio.py",
     "            prezzi)\n", "            prezzi, stato.eta)\n", [SER]),
    ("servizio: flusso senza istante (orologio del PC)", B + "servizio.py",
     "    adesso_ms = None if adesso_s is None else int(float(adesso_s) * 1000)",
     "    adesso_ms = None", [SER]),
    ("servizio: mercati della decisione ignorati", B + "servizio.py",
     '                          let.get("stato_scanner"), event_id, mercati, adesso_ms)',
     '                          let.get("stato_scanner"), event_id, None, adesso_ms)', [SER]),
    ("servizio: callback che solleva ferma gli altri", B + "servizio.py",
     "                    self.errori_callback += 1\n",
     "                    self.errori_callback += 1\n                    break\n", [SER]),
    ("servizio: in gioco dal book ignorato", B + "servizio.py",
     "    if dal_book is not None:\n        return bool(dal_book)\n", "", [SER, COR]),
    ("servizio: ferma non aspetta il thread", B + "servizio.py",
     "        g.thread.join(attesa_s)", "        pass", [SER, COR]),
    ("registrazione: bisect_left", B + "adattatori/registrazione.py",
     "        return bisect_right(self._ts, int(self._adesso_ms - self.ritardo_s * 1000.0))",
     "        from bisect import bisect_left\n        return bisect_left(self._ts, int(self._adesso_ms - self.ritardo_s * 1000.0))",
     [ADA]),
    ("registrazione: ritardo ignorato", B + "adattatori/registrazione.py",
     "int(self._adesso_ms - self.ritardo_s * 1000.0)", "int(self._adesso_ms)", [ADA]),
    ("canale: battito ignoto = 0", B + "adattatori/canale.py",
     "        return None if eta is None else float(eta)",
     "        return 0.0 if eta is None else float(eta)", [ADA]),
    ("circuito: tutto etichettato ips_scanner", B + "adattatori/api_football.py",
     '                out[eid] = lettura(fonte="api_football", trasporto="http", sport="calcio",',
     '                out[eid] = lettura(fonte="ips_scanner", trasporto="http", sport="calcio",', [ADA]),
    ("runner: diretto senza contatore", B + "adattatori/ips.py",
     "        self.diretti += 1\n        snap = self.diretto.get_score(eid)",
     "        snap = self.diretto.get_score(eid)", [ADA]),
    ("tennis: id numerico non convertito", B + "adattatori/ips_tennis.py",
     "            event_ids=[int(event_id)] if str(event_id).isdigit() else [event_id],",
     "            event_ids=[event_id],", [ADA]),
    ("import: betfair_inplay in testa a calcolo", B + "calcolo.py",
     "from Betfair.omega import omega_engine as _omega_engine\n",
     "from Betfair.omega import omega_engine as _omega_engine\n"
     "from Betfair.stream.scores import betfair_inplay as _bi  # noqa: F401\n", [IMP]),
    # --- correzioni dopo la revisione --------------------------------------
    ("R2 guardia del parser tennis tolta", B + "calcolo.py",
     "    except Exception as ex:  # noqa: BLE001 - come tennis_runner.py:1652: record rotto = nessun punteggio",
     "    except ZeroDivisionError as ex:  # mutazione", [COR]),
    ("R2 guardia per partita del servizio tolta", B + "servizio.py",
     "        except Exception as ex:  # noqa: BLE001 - una partita rotta non ferma le altre",
     "        except ZeroDivisionError as ex:  # mutazione", [COR]),
    ("R2 log a ogni giro (promemoria tolto)", B + "servizio.py",
     "            if self._promemoria.dovuto(eid, ora):", "            if True:", [COR]),
    ("R3 eta' congelate in stato()", B + "servizio.py",
     "        if st is None or let is None:\n            return st", "        return st", [COR]),
    ("R3 tennis muto tiene il punteggio", B + "servizio.py",
     '        if prima.sport == "tennis":\n            return dataclasses.replace(prima, set_game=None,',
     '        if False:\n            return dataclasses.replace(prima, set_game=None,', [COR]),
    ("R4/d fase del ripiego 'sconosciuta' (Omega oggi la deduce)", B + "calcolo.py",
     "        fase=fase_partita(None, snap.minute, ko=_da_ms(ko_ms),",
     '        fase="sconosciuta" if snap else fase_partita(None, snap.minute, ko=_da_ms(ko_ms),', [CAL]),
    ("R4 FaseCambiata contro la fase precedente, non l'ultima letta", B + "servizio.py",
     "    nota = fase_nota if fase_nota is not None else _fase_letta(prima)", "    nota = prima.fase", [COR]),
    ("R6 ripresa senza prova (non noto conta)", B + "servizio.py",
     '    if getattr(esito, "noto", False) is not True:\n        return None\n', "", [COR]),
    ("R6 avvia senza controllo della generazione", B + "servizio.py",
     "            if self._giro_vivo is not None:\n                return\n", "", [SER, COR]),
    ("R6 giro non serializzato", B + "servizio.py",
     "        with self._giro_lock:\n            ora = self.adesso_s()",
     "        if True:\n            ora = self.adesso_s()", [COR, SEC]),
    ("R7 cache del KO mai potata", B + "servizio.py",
     "        self._ko.dimentica(self._in_gioco_mercati.pop(eid, {}).keys())",
     "        self._in_gioco_mercati.pop(eid, {})", [COR]),
    ("R7 rigori non sono supplementari", B + "calcolo.py",
     '_STATI_SUPPLEMENTARI = ("extratime", "penalt")', '_STATI_SUPPLEMENTARI = ("extratime",)', [COR]),
    ("R7 firma senza set_game", B + "servizio.py",
     "stato.gialli, stato.set_game, stato.ko_ms", "stato.gialli, stato.ko_ms", [COR]),
    ("R7 firma senza rossi", B + "servizio.py",
     "            stato.rossi, stato.corner, stato.gialli,", "            stato.corner, stato.gialli,", [COR]),
    ("R7 firma senza corner", B + "servizio.py",
     "            stato.rossi, stato.corner, stato.gialli,", "            stato.rossi, stato.gialli,", [COR]),
    ("R7 firma senza gialli", B + "servizio.py",
     "            stato.rossi, stato.corner, stato.gialli,", "            stato.rossi, stato.corner,", [COR]),
    ("R7 ko_ms troncato", B + "calcolo.py",
     "    return None if ko is None else int(round(ko))", "    return None if ko is None else int(ko)", [COR]),
    # --- seconda revisione ---------------------------------------------------
    ("a consegna sotto _giro_lock (deadlock)", B + "servizio.py",
     "        self._svuota_coda()\n        return eventi",
     "            self._svuota_coda()\n        return eventi", [SEC]),
    ("a rientranza: il giro annidato consegna subito", B + "servizio.py",
     "            if self._consegnatore is not None:\n                return\n", "", [SEC]),
    ("b scanner_s non ricalcolato", B + "servizio.py",
     "            scanner = float(scanner) + max(0.0, float(adesso_s) - float(istante))",
     "            pass", [SEC]),
    ("c fonte muta: verdetto non ricalcolato nel giro", B + "servizio.py",
     "        let = self._letture.get(eid)\n        if let is None:\n            return None\n"
     "        return self._ricalcolato(prima, let, eid, ora, self._istanti.get(eid))",
     "        return None", [SEC]),
    ("d kickoff ignorato nella fase dedotta", B + "calcolo.py",
     "        fase=fase_partita(None, snap.minute, ko=_da_ms(ko_ms),",
     "        fase=fase_partita(None, snap.minute, ko=None,", [CAL]),
    ("d fase dedotta dichiarata letta", B + "calcolo.py",
     "        prezzi_vivi=prezzi_vivi, grezzo=entry or {}, fase_dedotta=True,",
     "        prezzi_vivi=prezzi_vivi, grezzo=entry or {}, fase_dedotta=False,", [CAL, SEC]),
    ("d FaseCambiata anche da fasi dedotte", B + "servizio.py",
     '    if stato.fase == "sconosciuta" or C.fase_dedotta(stato):',
     '    if stato.fase == "sconosciuta":', [COR, SEC]),
    ("e ferma dal thread del giro: join su se stesso", B + "servizio.py",
     "        if g.thread is threading.current_thread():", "        if False:", [SEC]),
    ("f runner: una partita rotta scarta il giro", B + "adattatori/ips.py",
     "            except Exception as ex:  # noqa: BLE001 - una partita rotta non ferma le altre",
     "            except ZeroDivisionError as ex:  # mutazione", [SEC]),
    ("f tennis: una partita rotta scarta il giro", B + "adattatori/ips_tennis.py",
     "        except Exception as ex:  # noqa: BLE001 - il feed non rompe mai chi lo legge",
     "        except ZeroDivisionError as ex:  # mutazione", [SEC]),
    ("f log a ogni errore (LogRaro tolto)", B + "adattatori/ips.py",
     "        if not self._promemoria.dovuto(str(event_id), float(self._orologio())):\n            return False\n",
     "", [SEC]),
    ("g T13 _dimentica non pulisce fase/flusso", B + "servizio.py",
     "        self._fase_nota.pop(eid, None)\n        self._vivo_noto.pop(eid, None)\n", "", [SEC]),
    ("g T15 osserva_book senza filtro dei seguiti", B + "servizio.py",
     "            if eid not in self._seguiti:\n                return\n            ko = C.ko_ms_intero",
     "            ko = C.ko_ms_intero", [SEC]),
    ("g T21 chi esce durante la lettura torna in memoria", B + "servizio.py",
     "                if eid not in self._seguiti:\n                    continue",
     "                if False:\n                    continue", [SEC]),
    ("g T24 tennis muto conserva la lettura vecchia", B + "servizio.py",
     '        elif nuovo.sport == "tennis":\n            self._letture.pop(eid, None)',
     "        elif False:\n            pass", [SEC]),
    # --- terza revisione (coda delle consegne) ------------------------------
    ("M1 consegnatore non rilasciato su BaseException", B + "servizio.py",
     "        except BaseException:\n            with self._coda_lock:\n                self._consegnatore = None\n"
     "                self._cb_in_corso = None\n            raise\n",
     "        except BaseException:\n            raise\n", [TER]),
    ("M3 coda LIFO", B + "servizio.py",
     "                    voce = self._coda.popleft()", "                    voce = self._coda.pop()", [TER]),
    ("3-1 disiscrivi senza effetto", B + "servizio.py",
     "                dove.pop(chiave, None)", "                pass", [TER]),
    ("3-1 nuovo iscritto riceve le voci calcolate prima", B + "servizio.py",
     "        for chiave in voce.ids:", "        for chiave in list(iscritti):", [TER]),
    ("3-2 stati non coalescenti (coda illimitata)", B + "servizio.py",
     "        if vecchia is not None:\n            self._coda.remove(vecchia)\n            self.stati_coalescati += 1\n",
     "", [TER]),
    ("3-2 eventi scartati", B + "servizio.py",
     '                        self._coda.append(_Voce("evento", ev.event_id, ev, ids_eventi))',
     "                        pass", [TER]),
    ("3-2 StatoCambiato coalescente perde il primo 'prima'", B + "servizio.py",
     "                            ev = StatoCambiato(ev.event_id, vecchia.cosa.prima, ev.dopo)",
     "                            pass", [TER]),
    ("3-2 nessun avviso oltre il tetto", B + "servizio.py",
     '        if oltre and self._avviso_coda.dovuto("coda", time.monotonic()):',
     "        if False:", [TER]),
    ("3-2 avviso a ogni giro (promemoria tolto)", B + "servizio.py",
     '        if oltre and self._avviso_coda.dovuto("coda", time.monotonic()):',
     "        if oltre:", [TER]),
    ("3-2 callback in corso non registrata", B + "servizio.py",
     "                self._cb_in_corso = cb\n", "                pass\n", [TER]),
    ("3-3 coda non svuotata al ritorno anticipato", B + "servizio.py",
     "        self._svuota_coda()\n        return eventi\n\n    def _calcola_e_accoda",
     "        if ids and letture is not None:\n            self._svuota_coda()\n        return eventi\n\n"
     "    def _calcola_e_accoda", [TER]),
]


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    rossi = 0
    for nome, rel, vecchio, nuovo, test in MUT:
        path = os.path.join(R, rel)
        prima = sha(path)
        with open(path, "rb") as fh:
            originale = fh.read()
        testo = originale.decode("utf-8")
        n = testo.count(vecchio)
        if n != 1:
            print(f"ERRORE  {nome}: occorrenze {n}")
            continue
        with open(path, "wb") as fh:
            fh.write(testo.replace(vecchio, nuovo).encode("utf-8"))
        try:
            res = subprocess.run([sys.executable, "-m", "pytest", *test, "-q", "-x",
                                  "-p", "no:cacheprovider", "-m", "not cert"],
                                 cwd=R, capture_output=True, text=True, timeout=900)
        finally:
            with open(path, "wb") as fh:
                fh.write(originale)
        dopo = sha(path)
        ultima = (res.stdout.strip().splitlines() or ["?"])[-1]
        rosso = res.returncode != 0
        rossi += rosso
        print(f"{'ROSSO' if rosso else 'VERDE!'}  {nome}  [{ultima}]  "
              f"sha256 {'uguale' if prima == dopo else 'DIVERSO'} {dopo[:12]}")
    print(f"TOTALE rosse {rossi}/{len(MUT)}")


main()
