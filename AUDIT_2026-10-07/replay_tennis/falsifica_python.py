"""Falsificazioni del Replay Tennis (Python): ogni mutazione reintroduce un difetto,
il test indicato DEVE diventare rosso. Il file mutato e' ripristinato byte per byte
(controllo sha256) dopo OGNI mutazione, anche se il test esplode.

Uso:  python3 AUDIT_2026-10-07/replay_tennis/falsifica_python.py
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
T = "Betfair/stream/tennis_replay/tests/"
CONV = "Betfair/stream/tennis_replay/convertitore.py"
CAR = "Betfair/stream/tennis_replay/caricamento.py"
REC = "Betfair/stream/tennis_live/tennis_recorder.py"
DB = "Betfair/stream/db.py"
CUR = "Betfair/stream/curator.py"
C = "Betfair/stream/tests/"
L = "Betfair/stream/tennis_live/tests/"
MRG = "Betfair/stream/tennis_live/mercati_registrati.py"
RUN = "Betfair/stream/tennis_live/tennis_runner.py"
IMP = "Betfair/stream/tennis_replay/importa.py"

MUTAZIONI = [
    ("M1 libro serializzato a 3 livelli invece di LADDER_DEPTH", CONV,
     "out.record.append(serialize_book(mb, depth))", "out.record.append(serialize_book(mb, 3))",
     T + "test_convertitore_2026_10_07.py::test_vera_libri_identici_a_flumine"),
    ("M2 snapshot fotografato PRIMA di applicare la riga", CONV,
     "        listener.on_data(riga)\n        ids: List[str] = []",
     "        ids: List[str] = []",
     T + "test_convertitore_2026_10_07.py::test_costruita_libri_identici_all_oracolo"),
    ("M3 break se vince CHI SERVIVA (tenuta scambiata per break)", CONV,
     "servizio != vincitore and not prev.get(\"tiebreak\")", "servizio == vincitore and not prev.get(\"tiebreak\")",
     T + "test_convertitore_2026_10_07.py::test_eventi_tenuta_e_break"),
    ("M4 nessun SALTO: due game in una riga diventano un break", CONV,
     "if dg[0] < 0 or dg[1] < 0 or dg[0] + dg[1] > 1:", "if dg[0] < 0 or dg[1] < 0:",
     T + "test_convertitore_2026_10_07.py::test_eventi_salto_di_registrazione_nessun_break_inventato"),
    ("M5 break anche nel tie-break", CONV,
     "servizio != vincitore and not prev.get(\"tiebreak\")", "servizio != vincitore",
     T + "test_convertitore_2026_10_07.py::test_eventi_tie_break_vinto_non_e_break_e_fine_partita"),
    ("M6 curatore senza lo stato (la chiusura sparisce, tennis)", CUR,
     "stato_cambiato = seen and last_stato.get(market_id) != stato", "stato_cambiato = False",
     T + "test_convertitore_2026_10_07.py::test_vera_snapshot_curati_vengono_dai_libri"),
    ("M7 regolamento preso alla sospensione invece che alla chiusura", CONV,
     "if str(getattr(mb, \"status\", \"\") or \"\").upper() == \"CLOSED\" and stato.settled_ms is None:",
     "if str(getattr(mb, \"status\", \"\") or \"\").upper() in (\"CLOSED\", \"SUSPENDED\") and stato.settled_ms is None:",
     T + "test_convertitore_2026_10_07.py::test_costruita_tutti_i_mercati_da_due_file"),
    ("M8 doppioni fra file non tolti", CONV,
     "        if chiave in visti:\n            continue\n", "",
     T + "test_convertitore_2026_10_07.py::test_costruita_doppione_dello_stesso_file_entra_una_volta"),
    ("M9 niente nomi IPS per il Match Odds senza catalogo", CONV,
     "        if not nome and (stato.market_type or \"\").upper() == \"MATCH_ODDS\" and nomi_ips and sp in (1, 2):",
     "        if False:",
     T + "test_convertitore_2026_10_07.py::test_vera_catalogo_evento_e_buchi"),
    ("M10 raw senza libri accettato (evento vuoto nel DB)", CONV,
     "    if not dec.record:\n        raise ValueError", "    if False:\n        raise ValueError",
     T + "test_convertitore_2026_10_07.py::test_raw_senza_libri_rifiutato"),
    ("M11 caricamento cancella TUTTO l'evento per ogni mercato", CAR,
     "db.delete_event_rows(T_SNAPSHOT, ev, market_id=mid)", "db.delete_event_rows(T_SNAPSHOT, ev)",
     T + "test_caricamento_importa_2026_10_07.py::test_cartella_per_cartella_un_mercato_non_cancella_gli_altri"),
    ("M12 punteggio cancellato anche se l'import non lo porta", CAR,
     "    if rt.punteggio:\n        db.delete_event_rows(T_PUNTEGGIO, ev)",
     "    db.delete_event_rows(T_PUNTEGGIO, ev)\n    if rt.punteggio:",
     T + "test_caricamento_importa_2026_10_07.py::test_cartella_per_cartella_un_mercato_non_cancella_gli_altri"),
    ("M13 delete_event_rows ignora il filtro del mercato", DB,
     "        if market_id is not None:\n            sel = sel.eq(\"market_id\", market_id)\n", "",
     T + "test_caricamento_importa_2026_10_07.py::test_cartella_per_cartella_un_mercato_non_cancella_gli_altri"),
    ("M14 fine partita su QUALUNQUE mercato chiuso", REC,
     "and (c.get(\"marketDefinition\") or {}).get(\"marketType\") == \"MATCH_ODDS\")",
     ")",
     T + "test_fine_partita_runner_2026_10_07.py::test_chiusura_di_un_altro_mercato_o_evento_non_registrato"),
    ("M15 caricamento riprogrammato a ogni chiusura", REC,
     "if ev in self._fine_programmata or os.getenv", "if os.getenv",
     T + "test_fine_partita_runner_2026_10_07.py::test_chiusura_del_match_odds_carica_una_volta"),
    ("M16 interruttore TENNIS_REPLAY_CARICA=0 ignorato", REC,
     "os.getenv(\"TENNIS_REPLAY_CARICA\", \"1\").strip() == \"0\"", "False",
     T + "test_fine_partita_runner_2026_10_07.py::test_niente_caricamento_senza_chiusura_o_se_spento"),
    ("M17 il catalogo del runner non arriva al tee", REC,
     "tee.enable(ev, [mid] + mercati_extra(meta), meta=meta)", "tee.enable(ev, [mid] + mercati_extra(meta))",
     T + "test_fine_partita_runner_2026_10_07.py::test_sync_record_flags_passa_il_catalogo_del_runner"),
    # --- 07/10 sera: curatore del CALCIO (regola unica) ---
    ("M18 curatore calcio senza lo stato (la chiusura vera della 35760084 sparisce)", CUR,
     "stato_cambiato = seen and last_stato.get(market_id) != stato", "stato_cambiato = False",
     C + "test_curatore_stato_2026_10_07.py::test_calcio_vero_la_chiusura_entra_nel_replay"),
    ("M19 riga di solo stato che sposta l'orologio della cadenza", CUR,
     "        if not regola_di_sempre:\n            continue                    # riga di solo stato: cadenza e firma invariate\n",
     "",
     C + "test_curatore_stato_2026_10_07.py::test_solo_i_cambi_di_stato_in_piu_e_la_cadenza_non_si_sposta"),
    ("M20 inplay fuori dallo stato", CUR,
     "stato = (rec.get(\"status\") or \"OPEN\", bool(rec.get(\"inplay\", False)))",
     "stato = (rec.get(\"status\") or \"OPEN\", False)",
     C + "test_curatore_stato_2026_10_07.py::test_inplay_cambiato_coi_best_uguali_entra"),
    # --- 07/10 sera: REC su tutti i mercati (runner tennis) ---
    ("R1 elenco dello stream senza i mercati registrati", MRG,
     "        for mid in mercati_extra(metas[ev]):", "        for mid in []:",
     L + "test_rec_tutti_i_mercati_2026_10_07.py::test_rec_acceso_con_bot_in_posizione_i_mercati_entrano_e_il_bot_non_si_accorge"),
    ("R2 tetto ignorato (oltre il limite della connessione)", MRG,
     "            if len(scelti) >= tetto:\n", "            if False:\n",
     L + "test_rec_tutti_i_mercati_2026_10_07.py::test_tetto_i_match_odds_restano_i_registrati_in_eccesso_fuori"),
    ("R3 il catalogo rimette il Match Odds tra i registrati", MRG,
     "        if not mid or mid == str(escludi):", "        if not mid:",
     L + "test_rec_tutti_i_mercati_2026_10_07.py::test_catalogo_dell_evento_dalla_betting_api_senza_il_match_odds"),
    ("R4 REC spento: i mercati in piu' restano nello stream", RUN,
     "    spenti = [ev for ev, meta in session.market_meta.items() if ev not in voluti and _MR.CHIAVE in meta]",
     "    spenti = []",
     L + "test_rec_tutti_i_mercati_2026_10_07.py::test_rec_acceso_con_bot_in_posizione_i_mercati_entrano_e_il_bot_non_si_accorge"),
    ("R5 catalogo KO riletto a ogni giro (REST martellata)", RUN,
     "    if time.monotonic() - ko.get(event_id, -1e9) < _MR_RIPROVA_S:\n        return False\n", "",
     L + "test_rec_tutti_i_mercati_2026_10_07.py::test_catalogo_ko_niente_cambia_e_si_riprova_dopo"),
    ("R6 partita nuova registrata senza i suoi mercati", RUN,
     "            if voluti_righe[ev].get(\"record\"):\n                _leggi_mercati_registrati(session, ev, meta)\n", "",
     L + "test_rec_tutti_i_mercati_2026_10_07.py::test_partita_nuova_registrata_entra_coi_suoi_mercati_e_il_bot_resta"),
    ("R7 la build non legge i mercati registrati", RUN,
     "            _mercati_registrati_alla_build(session, follows)\n", "",
     L + "test_rec_tutti_i_mercati_2026_10_07.py::test_contratto_della_build_un_solo_elenco_per_capture_ordini_e_bot"),
    ("R8 iscrizione a caldo col solo Match Odds (toglie i registrati)", RUN,
     "        mids = _MR.mercati_da_sottoscrivere(\n            {**{ev: session.market_meta[ev] for ev in base}, **{ev: metas[ev] for ev in entrano}},\n            tetto)",
     "        mids = sorted([session.market_meta[ev][\"market_id\"] for ev in base] + [metas[ev][\"market_id\"] for ev in entrano])",
     L + "test_rec_tutti_i_mercati_2026_10_07.py::test_partita_nuova_registrata_entra_coi_suoi_mercati_e_il_bot_resta"),
    ("R9 tee senza i mercati in piu'", REC,
     "tee.enable(ev, [mid] + mercati_extra(meta), meta=meta)", "tee.enable(ev, [mid], meta=meta)",
     L + "test_rec_tutti_i_mercati_2026_10_07.py::test_rec_acceso_con_bot_in_posizione_i_mercati_entrano_e_il_bot_non_si_accorge"),
    ("R10 nomi dei mercati del catalogo ignorati nel replay", CONV,
     "(nomi_mercato or {}).get(mid) or nome_mercato(tipo)", "nome_mercato(tipo)",
     T + "test_fine_partita_runner_2026_10_07.py::test_tutti_i_mercati_della_partita_registrata_coi_nomi_del_catalogo"),
    ("R11 import: catalogo di tutti i mercati (full_odds) ignorato", IMP,
     "            for mk in riga.get(\"full_odds\") or []:          # TennisFullMarket[]",
     "            for mk in []:",
     T + "test_caricamento_importa_2026_10_07.py::test_anagrafica_dal_db_legge_solo_tabelle_tennis"),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    esiti = []
    for nome, rel, old, new, test in MUTAZIONI:
        p = RADICE / rel
        originale = p.read_bytes()
        prima = sha(p)
        testo = originale.decode("utf-8")
        assert testo.count(old) == 1, f"{nome}: testo da mutare non trovato una volta sola"
        try:
            p.write_bytes(testo.replace(old, new).encode("utf-8"))
            r = subprocess.run([sys.executable, "-m", "pytest", test, "-q", "-p", "no:cacheprovider", "-x"],
                               cwd=RADICE, capture_output=True, text=True, timeout=600)
            rosso = r.returncode != 0
        finally:
            p.write_bytes(originale)
        assert sha(p) == prima, f"{nome}: ripristino fallito"
        esiti.append(rosso)
        print(("ROSSO " if rosso else "VERDE!") + f" {nome}  [{test.split('::')[-1]}]")
    print(f"\n{sum(esiti)}/{len(esiti)} mutazioni rosse; file ripristinati (sha256 verificato)")
    return 0 if all(esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
