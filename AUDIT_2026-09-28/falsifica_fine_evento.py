# -*- coding: utf-8 -*-
"""Falsificazione dei test del CANTIERE A (fine evento, 28/09/2026).

Ogni mutazione reintroduce UN difetto nel codice corretto; i test indicati
DEVONO diventare rossi. Il file mutato si ripristina SEMPRE dai byte originali
(sha256 verificato) nel ``finally``, anche se pytest fallisce o va in timeout.
NON interrompere a meta'. Uso (dalla radice del worktree):

    SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x \
      .venv/Scripts/python.exe AUDIT_2026-09-28/falsifica_fine_evento.py
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PY = os.path.join(RADICE, ".venv", "Scripts", "python.exe")
TC = "Betfair/stream/tests/test_fine_evento_2026_09_28.py"
TT = "Betfair/stream/tennis_live/tests/test_fine_evento_tennis_2026_09_28.py"
RUN = "Betfair/stream/runner.py"
AFW = "Betfair/stream/auto_follow.py"
DBF = "Betfair/stream/db.py"
SCS = "Betfair/stream/scalper/scalper_session.py"
TBS = "Betfair/stream/tennis_live/tennis_bot_service.py"
TRN = "Betfair/stream/tennis_live/tennis_runner.py"
TDBF = "Betfair/stream/tennis_live/tennis_db.py"

# (codice, file, vecchio, nuovo, test che devono diventare rossi)
MUTAZIONI = [
    ("M1 catalogo vuoto: di nuovo 3 ore dal via", RUN,
     "            if _finito_senza_mercati(f):",
     "            if _is_finished_stale(f):  # MUTAZIONE",
     [TC + "::test_catalogo_vuoto_a_partita_iniziata_finita_alla_seconda_lettura"]),
    ("M2 finalize senza live_now CLOSED", RUN,
     "    _chiudi_live_now_sicuro(event_id)\n",
     "    pass  # MUTAZIONE\n",
     [TC + "::test_match_odds_chiuso_follow_e_live_now_closed_e_mercati_chiusi_fuori_dal_tetto",
      TC + "::test_catalogo_vuoto_a_partita_iniziata_finita_alla_seconda_lettura"]),
    ("M3 finalize_worker senza rilascio periodico", RUN,
     "    if session.finished_events:\n        _rilascia_mercati_finiti(session)",
     "    if False:  # MUTAZIONE\n        _rilascia_mercati_finiti(session)",
     [TC + "::test_match_odds_chiuso_follow_e_live_now_closed_e_mercati_chiusi_fuori_dal_tetto"]),
    ("M4 mercati chiusi delle finite restano nel tetto", RUN,
     "            tenuti -= chiusi\n",
     "            pass  # MUTAZIONE\n",
     [TC + "::test_match_odds_chiuso_follow_e_live_now_closed_e_mercati_chiusi_fuori_dal_tetto"]),
    ("M5 ricostruzione risottoscrive le finite", RUN,
     "                  if ev not in finite)",
     "                  if True)  # MUTAZIONE",
     [TC + "::test_ricostruzione_non_risottoscrive_le_partite_finite"]),
    ("M6 uscita ordinata: vive CLOSED come prima", RUN,
     '        _safe_set_status(event_id, "PENDING")\n        out["in_attesa"].append(event_id)',
     '        _finalize_event(event_id, session)  # MUTAZIONE\n        out["in_attesa"].append(event_id)',
     [TC + "::test_uscita_ordinata_chiude_le_finite_e_rimette_in_attesa_le_vive"]),
    ("M7 uscita ordinata: finite non drenate", RUN,
     "            finiti = [str(e) for e in rec.drain_finished()]",
     "            finiti = []  # MUTAZIONE",
     [TC + "::test_uscita_ordinata_chiude_le_finite_e_rimette_in_attesa_le_vive"]),
    ("M8 live_now chiusa con upsert (perde il punteggio)", DBF,
     '        sb.table("live_now")\n        .update({"inplay": False, "status": "CLOSED", "updated_at": _now_iso()})\n        .eq("event_id", str(event_id)))',
     '        sb.table("live_now")\n        .upsert({"event_id": str(event_id), "inplay": False, "status": "CLOSED"}))  # MUTAZIONE',
     [TC + "::test_chiudi_live_now_e_un_update_che_conserva_il_punteggio"]),
    ("M9 live_now orfane: chiuse anche quelle dei follow attivi", DBF,
     "    da_chiudere = [e for e in ids if e in terminali]\n    for i in range(0, len(da_chiudere), 100):\n        (sb.table(\"live_now\")",
     "    da_chiudere = list(ids)  # MUTAZIONE\n    for i in range(0, len(da_chiudere), 100):\n        (sb.table(\"live_now\")",
     [TC + "::test_live_now_orfane_chiuse_all_avvio_solo_se_il_follow_e_terminale"]),
    ("M10 auto-follow: orario d'invio non azzerato al rebuild", AFW,
     "            for mid in self._applicati:\n                self._inviato_ts[mid] = ora",
     "            for mid in []:  # MUTAZIONE\n                self._inviato_ts[mid] = ora",
     [TC + "::test_dopo_la_ricostruzione_i_mercati_automatici_non_sono_mai_arrivati"]),
    ("M11 auto-follow: righe non chiuse all'uscita", AFW,
     "        for ev in sorted(self._scritti):\n            if self.follow_db.chiudi(ev):",
     "        for ev in []:  # MUTAZIONE\n            if self.follow_db.chiudi(ev):",
     [TC + "::test_uscita_ordinata_chiude_solo_le_righe_dell_auto_follow"]),
    ("M12 finally senza chiusura righe auto", RUN,
     "                auto.chiudi_righe()\n",
     "                pass  # MUTAZIONE\n",
     [TC + "::test_finally_del_runner_chiude_le_righe_auto_e_non_finalizza_le_vive"]),
    ("M13 scalper: MATCH_ODDS chiuso non riconosciuto", SCS,
     "    if mo_market_id and _mercato_chiuso_in_flumine(markets, mo_market_id) is True:\n        return True",
     "    if False:  # MUTAZIONE\n        return True",
     [TC + "::test_scalper_partita_finita_regola_su_flumine_vero"]),
    ("M14 scalper: sospeso scambiato per chiuso", SCS,
     '    return stato.upper() == "CLOSED"',
     '    return stato.upper() in ("CLOSED", "SUSPENDED")  # MUTAZIONE',
     [TC + "::test_scalper_partita_finita_regola_su_flumine_vero"]),
    ("M15 scalper: fine partita non controllata nel battito", SCS,
     '            if partita_finita(framework, getattr(mo, "market_id", None), market_ids):',
     '            if False:  # MUTAZIONE',
     [TC + "::test_scalper_sessione_usa_la_regola_nel_battito"]),
    ("M16 score_worker: mercato chiuso ancora in gioco", RUN,
     '            and str((latest.get(m["market_id"], {}) or {}).get("status") or "") != "CLOSED"\n',
     "            and True  # MUTAZIONE\n",
     [TC + "::test_score_worker_mercati_chiusi_non_in_gioco_e_mai_sopra_la_finalizzata"]),
    ("M17 score_worker: riscrive sopra la finalizzata", RUN,
     "        if event_id in session.finished_events:\n            # 28/09 (cantiere A): finalizzata",
     "        if False:  # MUTAZIONE\n            # 28/09 (cantiere A): finalizzata",
     [TC + "::test_score_worker_mercati_chiusi_non_in_gioco_e_mai_sopra_la_finalizzata"]),
    # --- seconda tornata (verifica del coordinatore 28/09) ---
    ("G1 calcio: niente conferma (ritirata alla prima lettura vuota)", RUN,
     "    if ora - dal < FINE_CONFERMA_S:\n        logger.info(\"[runner]",
     "    if False:  # MUTAZIONE\n        logger.info(\"[runner]",
     [TC + "::test_catalogo_vuoto_a_partita_iniziata_finita_alla_seconda_lettura"]),
    ("G2 calcio: soldi dentro ignorati", RUN,
     "    if motivo:\n        prima_volta = ev not in st[\"trattenute\"]",
     "    if False:  # MUTAZIONE\n        prima_volta = ev not in st[\"trattenute\"]",
     [TC + "::test_soldi_dentro_la_partita_non_si_ritira"]),
    ("G3 calcio: denaro non verificabile = nessun denaro", RUN,
     "        return \"denaro non verificabile (%s)\" % str(e)[:120]",
     "        return None  # MUTAZIONE",
     [TC + "::test_soldi_non_verificabili_valgono_soldi_dentro"]),
    ("G4 calcio: comandi in volo nel motore ignorati", RUN,
     "        if sul_evento:\n            return",
     "        if False:  # MUTAZIONE\n            return",
     [TC + "::test_comando_in_volo_nel_motore_vale_soldi_dentro"]),
    ("G5 calcio: in conferma ricontata come nuova (ricostruzioni in loop)", RUN,
     "        if ev in in_fine:\n",
     "        if False:  # MUTAZIONE\n",
     [TC + "::test_in_conferma_niente_ricostruzioni_la_rilegge_il_sub_worker",
      TC + "::test_soldi_dentro_la_partita_non_si_ritira"]),
    ("G6 db: posizione regolata ignorata (mai regolata)", DBF,
     "                  if (str(p.get(\"mode\")), str(p.get(\"market_id\"))) not in regolati]",
     "                  if True]  # MUTAZIONE",
     [TC + "::test_soldi_sull_evento_fonti_vere"]),
    ("G7 db: comandi in coda ignorati", DBF,
     "        if in_coda:\n            return \"%d comandi in coda sull'evento\"",
     "        if False:  # MUTAZIONE\n            return \"%d comandi in coda sull'evento\"",
     [TC + "::test_soldi_sull_evento_fonti_vere"]),
    ("G8 db: esposizione non abbinata ignorata", DBF,
     "            or _f(\"unmatched_back_exposure\") > 0.0 or _f(\"unmatched_lay_exposure\") > 0.0)",
     "            or False)  # MUTAZIONE",
     [TC + "::test_soldi_sull_evento_fonti_vere"]),
    ("G9 tennis: niente conferma", TRN,
     "    if ora - dal < FINE_CONFERMA_S:\n        logger.info(\"[tennis-runner]",
     "    if False:  # MUTAZIONE\n        logger.info(\"[tennis-runner]",
     [TT + "::test_riavvio_partita_finita_ad_app_spenta_follow_closed_senza_relogin"]),
    ("G10 tennis: soldi dentro ignorati", TRN,
     "    if motivo:\n        prima_volta = ev not in st[\"trattenute\"]",
     "    if False:  # MUTAZIONE\n        prima_volta = ev not in st[\"trattenute\"]",
     [TT + "::test_riavvio_soldi_dentro_la_partita_resta_seguita"]),
    ("G11 tennis: denaro non verificabile = nessun denaro", TRN,
     "        motivo = \"denaro non verificabile (%s)\" % str(e)[:120]",
     "        motivo = None  # MUTAZIONE",
     [TT + "::test_riavvio_soldi_non_verificabili_valgono_soldi"]),
    ("G12 tennis: follow_worker freddo ricostruisce in conferma", TRN,
     "           and fine_da_rileggere(session, f[\"event_id\"], _ora_fine)]",
     "           and True]  # MUTAZIONE",
     [TT + "::test_follow_worker_freddo_non_ricostruisce_in_conferma"]),
    ("G13 tennis db: comandi in coda ignorati", TDBF,
     "        if in_coda:\n            return \"%d comandi in coda sulla partita\"",
     "        if False:  # MUTAZIONE\n            return \"%d comandi in coda sulla partita\"",
     [TT + "::test_soldi_sull_evento_tennis_fonti_vere"]),
    ("P2 recorder illeggibile: rilascia tutto", RUN,
     "                    chiusi = set()\n",
     "                    chiusi = set(tenuti)  # MUTAZIONE\n",
     [TC + "::test_recorder_illeggibile_non_rilascia_niente"]),
    ("P3 live_now orfane: chiuse anche senza follow terminale", DBF,
     "    da_chiudere = [e for e in ids if e in terminali]",
     "    da_chiudere = [e for e in ids if e in terminali or e == 'Z']  # MUTAZIONE",
     [TC + "::test_live_now_orfane_chiuse_all_avvio_solo_se_il_follow_e_terminale"]),
    ("P3b tennis_now orfane: chiuse anche senza follow terminale", TDBF,
     "    da_chiudere = [e for e in ids if e in terminali]",
     "    da_chiudere = [e for e in ids if e in terminali or e == 'Z']  # MUTAZIONE",
     [TT + "::test_tennis_now_orfane_chiuse_all_avvio"]),
    ("A1 calcio: arresto_worker non ferma", RUN,
     "    if session.shutdown_requested.is_set() or not _AO.richiesto():\n        return\n    logger.warning(\"[runner]",
     "    if True:  # MUTAZIONE\n        return\n    logger.warning(\"[runner]",
     [TC + "::test_arresto_ordinato_file_e_worker"]),
    ("A2 calcio: arresto non controllato in cima al ciclo", RUN,
     "            if _AO.richiesto():\n                logger.warning(\"[runner] ARRESTO",
     "            if False:  # MUTAZIONE\n                logger.warning(\"[runner] ARRESTO",
     [TC + "::test_setup_and_run_controlla_l_arresto_in_cima_al_ciclo"]),
    ("A3 arresto: file vecchio conta", os.path.join("Betfair", "stream", "arresto_ordinato.py"),
     "    return mt >= rif - 2.0",
     "    return True  # MUTAZIONE",
     [TC + "::test_arresto_ordinato_file_e_worker"]),
    ("A4 tennis: automatiche chiuse anche al ricambio del processo", TRN,
     "        if ev in finiti or (arresto and _AM.origine_follow(f) == _AM.ORIGINE_AUTO):",
     "        if ev in finiti or (_AM.origine_follow(f) == _AM.ORIGINE_AUTO):  # MUTAZIONE",
     [TT + "::test_uscita_ordinata_tennis"]),
    ("A5 tennis: finally senza chiusura dei follow", TRN,
     "            chiudi_alla_uscita_tennis(session)\n",
     "            pass  # MUTAZIONE\n",
     [TT + "::test_arresto_ordinato_worker_tennis"]),
    ("A6 calcio: uscita ordinata dimentica le partite in conferma", RUN,
     "    for event_id in sorted(set(getattr(session, \"cataloged_events\", None) or ()) | in_fine):",
     "    for event_id in sorted(set(getattr(session, \"cataloged_events\", None) or ())):  # MUTAZIONE",
     [TC + "::test_uscita_ordinata_rimette_in_attesa_le_partite_in_conferma"]),
    ("T1 ponte: righe su partita finita non fermate", TBS,
     "            if ev_s not in finite:\n                continue",
     "            if True:  # MUTAZIONE\n                continue",
     [TT + "::test_ponte_la_seguita_a_mano_FINITA_si_chiude",
      TT + "::test_ponte_finita_si_chiude_anche_a_scanner_fermo",
      TT + "::test_ponte_riga_armata_su_partita_finita_senza_follow_va_a_stopped"]),
    ("T2 ponte: arma una partita a mano finita", TBS,
     "                if ev in finite:\n                    continue        # 28/09: partita finita, niente da armare",
     "                if False:  # MUTAZIONE\n                    continue",
     [TT + "::test_ponte_non_arma_una_partita_a_mano_finita"]),
    ("T3 ponte: follow a mano finito mai chiuso", TBS,
     "                       | ((finite & seguite) - occupati))",
     "                       | set())  # MUTAZIONE",
     [TT + "::test_ponte_la_seguita_a_mano_FINITA_si_chiude",
      TT + "::test_ponte_non_arma_una_partita_a_mano_finita"]),
    ("T4 ponte: senza follow 'stopping' eterno", TBS,
     "            if ev_s in seguite:\n                db.set_tennis_bot_status(ev_s, bot, \"stopping\")",
     "            if True:  # MUTAZIONE\n                db.set_tennis_bot_status(ev_s, bot, \"stopping\")",
     [TT + "::test_ponte_riga_armata_su_partita_finita_senza_follow_va_a_stopped",
      TT + "::test_ponte_bot_spento_riga_su_partita_finita_senza_follow"]),
    ("T5 ponte auto-mode: arma una partita del feed gia' finita", TBS,
     "                    if ev in finite:\n                        return True     # 28/09: partita finita (CLOSED)",
     "                    if False:  # MUTAZIONE\n                        return True",
     [TT + "::test_ponte_auto_mode_non_arma_una_partita_del_feed_gia_finita"]),
    ("T6 ensure: riapre il follow di una partita finita", TBS,
     "        if str(event_id) in finite:\n            continue",
     "        if False:  # MUTAZIONE\n            continue",
     [TT + "::test_ensure_non_riapre_il_follow_di_una_partita_finita"]),
    ("T7 runner: catalogo vuoto a partita iniziata = relogin ed ERROR", TRN,
     "            if not _partita_iniziata(follow):\n                raise",
     "            if True:  # MUTAZIONE\n                raise",
     [TT + "::test_riavvio_partita_finita_ad_app_spenta_follow_closed_senza_relogin"]),
    ("T8 runner: finita anche a partita futura", TRN,
     "            if not _partita_iniziata(follow):\n                raise",
     "            if False:  # MUTAZIONE\n                raise",
     [TT + "::test_riavvio_partita_futura_senza_catalogo_strada_di_sempre"]),
    ("T9 tennis_now chiusa sempre con upsert", TDBF,
     "    if not righe:\n        riga = {\"event_id\": str(event_id), \"inplay\": False, \"status\": \"CLOSED\",",
     "    if True:  # MUTAZIONE\n        riga = {\"event_id\": str(event_id), \"inplay\": False, \"status\": \"CLOSED\",",
     [TT + "::test_chiudi_tennis_now_update_e_riga_minima_solo_se_assente"]),
    ("T10 tennis_now orfane: chiuse anche quelle dei follow attivi", TDBF,
     "    da_chiudere = [e for e in ids if e in terminali]\n    for i in range(0, len(da_chiudere), 100):\n        (sb.table(\"tennis_live_now\")",
     "    da_chiudere = list(ids)  # MUTAZIONE\n    for i in range(0, len(da_chiudere), 100):\n        (sb.table(\"tennis_live_now\")",
     [TT + "::test_tennis_now_orfane_chiuse_all_avvio"]),
]


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    env = dict(os.environ)
    env.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
    env.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
    env.setdefault("SUPABASE_KEY", "x")
    if "127.0.0.1" not in env["SUPABASE_URL"]:
        print("SUPABASE_URL non finto: mi fermo (i test non devono toccare il DB vero)")
        return 2
    esiti = []
    # argomenti opzionali: solo le mutazioni con quei codici (es. M17 T4)
    scelte = [a.upper() for a in sys.argv[1:]]
    for codice, rel, vecchio, nuovo, tests in MUTAZIONI:
        if scelte and codice.split()[0] not in scelte:
            continue
        path = os.path.join(RADICE, rel)
        with open(path, "rb") as fh:
            orig = fh.read()
        h0 = _sha(orig)
        testo = orig.decode("utf-8")
        crlf = "\r\n" in testo
        v = vecchio.replace("\n", "\r\n") if crlf else vecchio
        n = nuovo.replace("\n", "\r\n") if crlf else nuovo
        if testo.count(v) != 1:
            esiti.append((codice, "MUTAZIONE NON APPLICABILE (%d occorrenze)" % testo.count(v)))
            continue
        try:
            with open(path, "wb") as fh:
                fh.write(testo.replace(v, n).encode("utf-8"))
            r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x"]
                               + tests, cwd=RADICE, env=env, capture_output=True, text=True,
                               timeout=600)
            rosso = r.returncode != 0
            coda = (r.stdout.strip().splitlines() or ["?"])[-1]
            esiti.append((codice, ("ROSSO" if rosso else "VERDE (NON CATTURATA)") + " - " + coda))
        finally:
            with open(path, "wb") as fh:
                fh.write(orig)
            with open(path, "rb") as fh:
                assert _sha(fh.read()) == h0, "RIPRISTINO FALLITO: " + rel
    for c, e in esiti:
        print("%-62s %s" % (c, e))
    rossi = sum(1 for _c, e in esiti if e.startswith("ROSSO"))
    print("\n%d/%d mutazioni ROSSE" % (rossi, len(esiti)))
    return 0 if rossi == len(esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
