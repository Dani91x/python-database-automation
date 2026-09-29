"""D1-ter - falsificazione dei test nuovi. Ogni mutazione si applica, si lancia
il test, si ripristina il file BYTE-IDENTICO (controllo SHA-256). Uso:
    python AUDIT_2026-09-28/d1ter/falsifica.py [blocco1|blocco2|blocco3]
Mai interrompere a meta'."""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
PY = str(RADICE / ".venv" / "Scripts" / "python.exe")

T1 = "Betfair/mike/tests/test_mike_d1ter_submin_fok_parita_2026_09_28.py"
T2 = "Betfair/mike/tests/test_mike_d1ter_esito_ignoto_runner_2026_09_28.py"
T3 = "Betfair/stream/tests/test_motore_ritiro_pendente_d1ter_2026_09_28.py"

T4 = "Betfair/stream/tests/test_motore_submin_fok_caso_b_d1ter_2026_09_28.py"
T5 = "Betfair/stream/tests/test_trasporto_parita_mode_d1ter_2026_09_28.py"

TQ = "Betfair/mike/tests/test_mike_aperture_ferme_d1quater_2026_09_29.py"
TB = "Betfair/stream/tests/test_certifica_freni_ambiente_d1quater_2026_09_29.py"

MUTAZIONI = {
    "d1quater_produzione": [
        ("q1 il motore non toglie le aperture ferme", "Betfair/mike/engine.py",
         "    elif isinstance(ctx.aperture_ferme, dict):",
         "    elif False:  # MUTAZIONE", TQ),
        ("q2 il servizio non scrive il fermo", "Betfair/mike/service.py",
         "    if ctx is None or leg.role not in E.OPENING_ROLES:\n        return\n",
         "    return  # MUTAZIONE\n", TQ),
        ("q3 la causa sparita non libera le aperture", "Betfair/mike/service.py",
         "    ferme = ctx.aperture_ferme if isinstance(ctx.aperture_ferme, dict) else None\n"
         "    if ferme is None:\n",
         "    ferme = None  # MUTAZIONE\n    if ferme is None:\n", TQ),
        ("q4 ogni rifiuto e' non di mercato", "Betfair/mike/service.py",
         "    return n.startswith(_PREFISSI_NON_DI_MERCATO) or _nota_senza_runner(n)",
         "    return True  # MUTAZIONE", TQ),
    ],
    "d1quater_banco": [
        ("b1 tetto d'ambiente non dichiarato", "Betfair/stream/backtest/certifica.py",
         "        os.environ.update(FRENI_AMBIENTE_DEL_BANCO)",
         "        pass  # MUTAZIONE", TB),
        ("b2 ambiente non ripristinato all'uscita", "Betfair/stream/backtest/certifica.py",
         "        for k, v in prima_env.items():",
         "        for k, v in {}.items():  # MUTAZIONE", TB),
    ],
    "blocco4": [
        ("4a il motore rifiuta di nuovo il FOK sotto il minimo",
         "Betfair/stream/motore_ordini.py",
         "                    piano[\"submin_fok\"] = True",
         "                    raise Rifiuto(M_SUBMIN, \"FOK\")  # MUTAZIONE", T4),
        ("4b nessun ritiro del residuo a fine sequenza", "Betfair/stream/motore_ordini.py",
         "            if s.get(\"fok\"):",
         "            if False:  # MUTAZIONE", T4),
        ("4c ritiro che solleva = sequenza chiusa", "Betfair/stream/motore_ordini.py",
         "        except Exception:  # noqa: BLE001 - si ritenta al giro dopo, mai lasciato a riposo",
         "        except Exception:  # noqa: BLE001 - si ritenta al giro dopo, mai lasciato a riposo\n"
         "            morto = True  # MUTAZIONE", T4),
        ("4d passo fallito chiude subito con errore (come prima)",
         "Betfair/stream/motore_ordini.py",
         "                self._abbandona_submin(cust, lsb, str(fallito))",
         "                self._chiudi_submin(cust, False, str(fallito))  # MUTAZIONE", T4),
        ("4e il canale non manda il FOK per la porta di Mike",
         "Betfair/safe_strategy/execution.py",
         "or getattr(porta, \"submin_fill_or_kill\", False))",
         "or False)  # MUTAZIONE", T1),
    ],
    "blocco5": [
        ("5a mode fuori confronto per tutti i bot", "Betfair/stream/backtest/trasporto.py",
         "if bot in BOT_CODA_LIVE_CANALE_PAPER else ())",
         "if True else ())  # MUTAZIONE", T5),
        ("5b mode nel confronto anche per Mike", "Betfair/stream/backtest/trasporto.py",
         "if bot in BOT_CODA_LIVE_CANALE_PAPER else ())",
         "if False else ())  # MUTAZIONE", T5),
    ],
    "blocco1": [
        ("1a piano paper mai applicato", "Betfair/safe_strategy/execution.py",
         "            if rif is not None:",
         "            if False:  # MUTAZIONE", T1),
        ("1b porta di Mike non dichiara il FOK", "Betfair/mike/porta_ordini.py",
         "self.submin_fill_or_kill = not self.appoggiata",
         "self.submin_fill_or_kill = False  # MUTAZIONE", T1),
        ("1c piano applicato a ogni porta", "Betfair/safe_strategy/execution.py",
         "    if not getattr(porta, \"submin_fill_or_kill\", False):",
         "    if False:  # MUTAZIONE", T1),
        ("1d paper senza FOK nel piano", "Betfair/safe_strategy/execution.py",
         "max_stake=None, fill_or_kill=True)",
         "max_stake=None, fill_or_kill=False)  # MUTAZIONE", T1),
        ("1e Mike non passa il book", "Betfair/mike/service.py",
         "\"best_back\": book.best_back,",
         "\"best_back\": None,  # MUTAZIONE", "Betfair/mike/tests/test_mike_d1ter_submin_fok_parita_2026_09_28.py"),
    ],
    "blocco2": [
        ("2a fase errore trattata come prima (annullata)", "Betfair/mike/service.py",
         "        if fase == \"errore\":\n",
         "        if False:  # MUTAZIONE\n", T2),
        ("2b coordinatore: no_definitivo = not appoggiata", "Betfair/mike/service.py",
         "            no_definitivo = (not appoggiata and not ignoto_prima",
         "            no_definitivo = not appoggiata or (0  # MUTAZIONE", T2),
        ("2c coordinatore: fase in (...) senza not appoggiata", "Betfair/mike/service.py",
         "            no_definitivo = (not appoggiata and not ignoto_prima",
         "            no_definitivo = (not ignoto_prima  # MUTAZIONE", T2),
        ("2d esito ignoto chiuso cancelled", "Betfair/mike/service.py",
         "                leg.status = E.STATUS_RECONCILE\n                meta.update({\"canale_fase\": fase, \"canale_seq\": seq,\n",
         "                leg.status = \"cancelled\"  # MUTAZIONE\n                meta.update({\"canale_fase\": fase, \"canale_seq\": seq,\n", T2),
        ("2e sincrono non dice riconciliazione", "Betfair/mike/service.py",
         "            return \"pending_reconcile\"     # D1-ter",
         "            pass  # MUTAZIONE D1-ter", T2),
    ],
    "blocco3": [
        ("3a terminale emesso anche a ritiro non confermato (come prima)",
         "Betfair/stream/motore_ordini.py",
         "                                s[\"ref\"], ora - float(s[\"ritiro_t0\"]))\n            return\n",
         "                                s[\"ref\"], ora - float(s[\"ritiro_t0\"]))\n            pass  # MUTAZIONE\n",
         T3),
        ("3b ordine senza bet_id dato per morto", "Betfair/stream/motore_ordini.py",
         "            elif _ordine_terminale(ordine):",
         "            elif True:  # MUTAZIONE", T3),
        ("3c annullo che solleva = morto", "Betfair/stream/motore_ordini.py",
         "        except Exception:  # noqa: BLE001 - ritiro non riuscito: si RITENTA, mai abbandonare",
         "        except Exception:  # noqa: BLE001 - ritiro non riuscito: si RITENTA, mai abbandonare\n"
         "            morto = True  # MUTAZIONE", T3),
        ("3d annullo non chiesto nemmeno col bet_id", "Betfair/stream/motore_ordini.py",
         "            elif getattr(ordine, \"bet_id\", None) and _ordine_eseguibile(ordine):",
         "            elif False:  # MUTAZIONE", T3),
    ],
}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    blocco = sys.argv[1] if len(sys.argv) > 1 else "blocco1"
    esito = 0
    for nome, rel, prima, dopo, test in MUTAZIONI[blocco]:
        p = RADICE / rel
        orig = p.read_bytes()
        sha = _sha(p)
        testo = orig.decode("utf-8")
        if "\r\n" in testo:
            prima = prima.replace("\n", "\r\n")
            dopo = dopo.replace("\n", "\r\n")
        if testo.count(prima) != 1:
            print(f"[{nome}] ANCORA NON UNICA ({testo.count(prima)}): salto")
            esito = 1
            continue
        try:
            p.write_bytes(testo.replace(prima, dopo).encode("utf-8"))
            r = subprocess.run([PY, "-m", "pytest", test, "-q", "-p", "no:cacheprovider",
                                "-x", "--no-header"], cwd=RADICE, capture_output=True,
                               text=True, timeout=600)
            ultima = (r.stdout.strip().splitlines() or ["?"])[-1]
            stato = "ROSSO" if r.returncode != 0 else "VERDE (mutazione SOPRAVVISSUTA)"
            if r.returncode == 0:
                esito = 1
            print(f"[{nome}] {stato}: {ultima}")
        finally:
            p.write_bytes(orig)
            assert _sha(p) == sha, f"ripristino NON byte-identico: {rel}"
    return esito


if __name__ == "__main__":
    sys.exit(main())
