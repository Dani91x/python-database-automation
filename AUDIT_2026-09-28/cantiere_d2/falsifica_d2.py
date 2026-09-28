"""Falsificazione dei test nuovi del cantiere D2 (28/09).

Per ogni mutazione: reintroduce il difetto nel codice, lancia i test, conta i
rossi, RIPRISTINA il file dai byte salvati e ne verifica lo sha1 (anche se il
test esplode: ``finally``). Un test che resta verde sotto la sua mutazione non
certifica. Uso (dal worktree):

    .venv/Scripts/python.exe AUDIT_2026-09-28/cantiere_d2/falsifica_d2.py
"""
import hashlib
import pathlib
import subprocess
import sys

W = pathlib.Path(__file__).resolve().parents[2]
PY = str(W / ".venv" / "Scripts" / "python.exe")

TEST = [
    "Betfair/stream/tennis_live/tests/test_cantiere_d2_minimo_e_specchio_2026_09_28.py",
    "Betfair/stream/tests/test_sniper_is_flat_2026_09_28.py",
    "Betfair/stream/tests/test_sniper_uscite_automatiche_2026_09_28.py",
    "Betfair/stream/tests/test_sniper_bot_2026_07_10.py",
    "Betfair/stream/tennis_scalper/tests/test_condotta_ordini_2026_09_17.py",
    "Betfair/stream/tennis_live/tests/test_tennis_bot_params.py",
    "Betfair/stream/tennis_live/tests/test_tennis_audit_runner.py",
    "Betfair/stream/tennis_live/tests/test_tennis_auto_mode_2026_09_25.py",
    "Betfair/stream/tennis_live/tests/test_motore_ordini_tennis_2026_09_25.py",
    "Betfair/stream/tennis_live/tests/test_paper_execution_gap5.py",
    "Betfair/stream/tennis_live/tests/test_modalita_e_guardie_tennis_2026_09_24.py",
    "Betfair/stream/tennis_live/tests/test_cantiere_d2_chiusure_esatte_2026_09_28.py",
    "Betfair/stream/tests/test_banco_scalper_sniper_2026_09_28.py",
    "Betfair/stream/tennis_live/tests/test_cantiere_d2_chiusure_via_bot_2026_09_28.py",
]

M = [
    ("M1 sniper is_flat misura le stake",
     "Betfair/stream/scalper/sniper_bot.py",
     "            nw, nl = self._real_net(pos)\n"
     "            if abs(nw - nl) > max(0.02, pos.residual_accepted + 0.02):\n",
     "            sb, _ob, sl, _ol = self._matched(  # MUTAZIONE\n"
     "                pos.entries + ([pos.close] if pos.close else [])\n"
     "                + pos.flatten_orders)\n"
     "            if abs(sb - sl) > 0.02:\n"),
    ("M2 motore senza la regola del minimo",
     "Betfair/stream/motore_ordini.py",
     'al_minimo = getattr(LOW, "_apertura_al_minimo", None)',
     "al_minimo = None  # MUTAZIONE"),
    ("M3 esecutore tennis non porta al minimo",
     "Betfair/stream/tennis_live/esecutore_tennis.py",
     "return porta_al_minimo_apertura(_jurisdiction(), str(side).lower(), float(size))",
     "return float(size)  # MUTAZIONE"),
    ("M4 regola pura gonfia anche sopra il minimo",
     "Betfair/stream/trading/submin.py",
     "return minimo if s < minimo - _TOL else s",
     "return max(minimo, s) + (0.5 if s >= minimo else 0.0)  # MUTAZIONE"),
    ("M5 ingresso bot tennis rifiutato come prima",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "    s = _porta_al_minimo(giurisdizione, lato.lower(), s)\n",
     "    pass  # MUTAZIONE\n"),
    ("M6 paper senza blindature .it",
     "Betfair/stream/tennis_live/tennis_runner.py",
     'if mode_u in ("LIVE", "PAPER"):',
     'if mode_u == "LIVE":  # MUTAZIONE'),
    ("M7 restart forzato in paper",
     "Betfair/stream/tennis_live/tennis_runner.py",
     'senza_ordini = modo_ordini not in ("LIVE", "PAPER")',
     'senza_ordini = modo_ordini != "LIVE"  # MUTAZIONE'),
    ("M8 evento senza cor",
     "Betfair/stream/motore_ordini.py",
     'if isinstance(result, dict) and result.get("cor_betfair"):',
     "if False:  # MUTAZIONE"),
    ("M9 esito tennis senza cor",
     "Betfair/stream/tennis_live/tennis_live_order_worker.py",
     '"cor_betfair": _cor_betfair(order),',
     '"cor_betfair": None,  # MUTAZIONE'),
    ("M10 la chiusura si gonfia",
     "Betfair/stream/motore_ordini.py",
     "        if azione == \"place\" and not riduce:\n"
     "            # 28/09 (TENNIS",
     "        if azione == \"place\":  # MUTAZIONE\n"
     "            # 28/09 (TENNIS"),
    ("M11 evento muto sul minimo",
     "Betfair/stream/motore_ordini.py",
     'if piano.get("portata_al_minimo"):',
     "if False:  # MUTAZIONE"),
    ("M12 sniper ignora l'interruttore (chiude sempre da solo)",
     "Betfair/stream/scalper/sniper_bot.py",
     "if g is not None and not self.uscite_automatiche:",
     "if False and g is not None:  # MUTAZIONE"),
    ("M13 sniper nasce ad uscite automatiche",
     "Betfair/stream/scalper/sniper_bot.py",
     '_ua = c.get("uscite_automatiche", False)',
     '_ua = c.get("uscite_automatiche", True)  # MUTAZIONE'),
    ("M14 lo stop dello sniper diventa discrezionale",
     "Betfair/stream/scalper/sniper_bot.py",
     "if up is not None and up >= self.stop_ticks:",
     "if up is not None and up >= self.stop_ticks and self.uscite_automatiche:  # MUTAZIONE"),
    ("M15 proposta a ogni book",
     "Betfair/stream/scalper/sniper_bot.py",
     "        if pos.proposta == motivo:\n            return\n",
     "        if False:  # MUTAZIONE\n            return\n"),
    ("M16 commissione del paper ordine per ordine (come prima)",
     "Betfair/stream/tennis_live/tennis_live_order_worker.py",
     "comm = quote_comm.get(id(order), 0.0)",
     "comm = round(max(0.0, pnl) * commissione, 2)  # MUTAZIONE"),
    ("M17 tetto tennis somma paper e live (come prima)",
     "Betfair/stream/tennis_live/tennis_bot_service.py",
     'and _modalita_dichiarata(r) == d["mode"]]',
     "]  # MUTAZIONE"),
    # ---- seconda consegna (28/09 sera) ----
    ("M19 copertura gonfiata al gradino come prima (niente uscita esatta)",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "        if diretta_ok(s, lato):\n            return s, None\n",
     "        if True:  # MUTAZIONE\n"
     "            return round(max(MINIMO_LATO[lato], math.ceil(s / 0.5 - 1e-9) * 0.5)"
     " if lato == 'BACK' else max(MINIMO_LATO[lato], s), 2), None\n"),
    ("M20 i bot non instradano la copertura sull'uscita esatta",
     "Betfair/stream/tennis_scalper/tennis_flb_bot.py",
     "        if copertura and self.live and not diretta_ok(size, side):\n",
     "        if False:  # MUTAZIONE\n"),
    ("M21 spezza_esatta perde il resto",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "        return diretta, round(s - diretta, 2)\n",
     "        return diretta, 0.0  # MUTAZIONE\n"),
    ("M22 la sequenza non avanza ai book",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "            self._passo(market, comp)\n            if not comp.in_corso():\n",
     "            pass  # MUTAZIONE\n            if not comp.in_corso():\n"),
    ("M23 l'annullo non ferma la sequenza",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "        if ordine.sequenza is not None and ordine.in_corso():\n",
     "        if False:  # MUTAZIONE\n"),
    ("M24 anti-cascata spenta",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "        if manca <= 0:\n            return True\n",
     "        return True  # MUTAZIONE\n"),
    ("M25 scalper tennis senza uscite esatte (come prima)",
     "Betfair/stream/tennis_live/tennis_runner.py",
     '        params.setdefault("exact_exits", True)\n',
     "        pass  # MUTAZIONE\n"),
    ("M26 S5 veloce ma sbagliata (copertura non integrata)",
     "Betfair/stream/scalper/certificazione.py",
     "        return self.integrale(b) - self.integrale(a)\n",
     "        return self.integrale(b)  # MUTAZIONE\n"),
    ("M27 linea sniper sbagliata di una",
     "Betfair/stream/scalper/scalper_session.py",
     '            lines = [f"OVER_UNDER_{tot + 1}5"]\n',
     '            lines = [f"OVER_UNDER_{tot}5"]  # MUTAZIONE\n'),
    ("M28 banco: live_now sempre vuota",
     "Betfair/stream/scalper/tools/replay_registrazioni.py",
     "        return dict(riga) if riga is not None else None\n",
     "        return None  # MUTAZIONE\n"),
    # ---- terza consegna: l'avanzamento DENTRO il bot (mutazioni del coordinatore)
    ("M29 FLB non fa avanzare la chiusura esatta",
     "Betfair/stream/tennis_scalper/tennis_flb_bot.py",
     "        self._esatte.avanza(market)\n", "        pass  # MUTAZIONE\n"),
    ("M30 PRO non fa avanzare la chiusura esatta",
     "Betfair/stream/tennis_scalper/tennis_pro_bot.py",
     "        self._esatte.avanza(market)\n", "        pass  # MUTAZIONE\n"),
    ("M31 SWING non fa avanzare la chiusura esatta",
     "Betfair/stream/tennis_scalper/tennis_swing_bot.py",
     "        self._esatte.avanza(market)\n", "        pass  # MUTAZIONE\n"),
    ("M32 scalper tennis non guida i submin",
     "Betfair/stream/tennis_scalper/tennis_scalper_bot.py",
     "            self._drive_submins(market, slot, int(now))\n",
     "            pass  # MUTAZIONE\n"),
    # ---- revisione del 28/09 sera
    ("M33 anti-cascata: intervallo fisso (niente raddoppio)",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "        return min(self.INTERVALLO_MAX_S, self.INTERVALLO_S * (2 ** n))\n",
     "        return self.INTERVALLO_S  # MUTAZIONE\n"),
    ("M34 blocco d'intervallo muto (nessuna riga critica)",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "        if self._blocco_detto.get(chiave) != avvii[-1]:\n",
     "        if False:  # MUTAZIONE\n"),
    ("M35 contatore non azzerato al successo",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "        self._fallite.pop((comp.market_id, comp.selection_id), None)\n",
     "        pass  # MUTAZIONE\n"),
    ("M36 completa letta dallo stato",
     "Betfair/stream/tennis_scalper/condotta_ordini.py",
     "        return self.size_remaining <= 0.0\n",
     "        return not self.in_corso()  # MUTAZIONE\n"),
    ("M37 B8: sostituto = non primo del Trade (come prima)",
     "Betfair/stream/tennis_live/certificazione_bot.py",
     "    return (abs(prezzo - _QUOTA_PARCHEGGIO[lato]) < 1e-9\n",
     "    return True or (abs(prezzo - _QUOTA_PARCHEGGIO[lato]) < 1e-9  # MUTAZIONE\n"),
    ("M18 riga viva dell'altra modalita' riscritta",
     "Betfair/stream/tennis_live/tennis_bot_service.py",
     "                    if ev in attive:\n",
     "                    if False:  # MUTAZIONE\n"),
]


def sha(p: pathlib.Path) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest()


def main() -> int:
    out = []
    filtro = sys.argv[1:]
    for nome, rel, vecchio, nuovo in M:
        if filtro and not any(nome.startswith(f + ' ') for f in filtro):
            continue
        p = W / rel
        orig = p.read_bytes()
        h0 = sha(p)
        testo = orig.decode("utf-8")
        n = testo.count(vecchio)
        if n == 0 and "\r\n" in testo:
            # file con fine riga CRLF: stessa mutazione con \r\n
            vecchio = vecchio.replace("\n", "\r\n")
            nuovo = nuovo.replace("\n", "\r\n")
            n = testo.count(vecchio)
        if n != 1:
            out.append("%s: NON APPLICABILE (%d occorrenze) -> NON ESEGUITA" % (nome, n))
            continue
        try:
            p.write_bytes(testo.replace(vecchio, nuovo).encode("utf-8"))
            r = subprocess.run([PY, "-m", "pytest", *TEST, "-q", "-p", "no:cacheprovider",
                                "-k", "not profilo_rapido"],
                               cwd=str(W), capture_output=True, text=True)
            righe = r.stdout.splitlines()
            fine = [ln for ln in righe if " passed" in ln or " failed" in ln]
            rossi = [ln.split("::", 1)[-1].split(" ")[0] for ln in righe
                     if ln.startswith("FAILED")]
            esito = "ROSSA" if r.returncode != 0 else "SOPRAVVISSUTA"
            out.append("%s [%s]: %s | %s | rossi: %s" % (
                nome, rel, esito, (fine[-1].strip("= ") if fine else "?"),
                ", ".join(rossi[:6]) + (" ..." if len(rossi) > 6 else "")))
        finally:
            p.write_bytes(orig)
            assert sha(p) == h0, "RIPRISTINO FALLITO " + rel
    for riga in out:
        print(riga)
    return 0


if __name__ == "__main__":
    sys.exit(main())
