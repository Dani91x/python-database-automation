"""Falsificazione dei test nuovi (unificazione + Safe tennis via canale, 25/09).

Ogni mutazione rimette nel codice un difetto preciso; i test indicati DEVONO
diventare rossi. Il file originale si ripristina dal contenuto salvato e si
verifica con sha1. Uso (dalla radice del worktree, sandbox DB):

    set SUPABASE_URL=http://127.0.0.1:9 & set SUPABASE_SERVICE_ROLE_KEY=x & set SUPABASE_KEY=x
    python AUDIT_2026-09-25/tennis_unificazione/falsifica.py [M1 M2 ...]
"""
from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys

T_UNI = "Betfair/stream/tests/test_sottoscrizione_a_caldo_unica_2026_09_25.py"
T_MOT = "Betfair/stream/tennis_live/tests/test_motore_ordini_tennis_2026_09_25.py"
T_SAFE = "Betfair/safe_strategy/tests/test_safe_tennis_canale_f8_2026_09_25.py"

MUTAZIONI = [
    ("M1", "sottoscrizione condivisa: il filtro nuovo non va sulla MarketStream",
     "Betfair/stream/sottoscrizione_a_caldo.py",
     "    stream.market_filter = filtro            # la riconnessione di flumine lo riusa\n",
     "", [T_UNI + "::test_parita_del_marketsubscription_calcio_e_tennis"]),
    ("M2", "calcio: applica NON passa dal modulo condiviso (copia sua)",
     "Betfair/stream/auto_follow.py",
     "        return _SC.sottoscrivi(framework, _SC.stream_di_mercato(framework), market_ids)\n",
     "        st = _SC.stream_di_mercato(framework)\n"
     "        return st._stream.subscribe_to_markets(market_filter={'marketIds': list(market_ids)},"
     " market_data_filter=st.market_data_filter, conflate_ms=st.conflate_ms)\n",
     [T_UNI + "::test_i_due_runner_usano_la_stessa_funzione"]),
    ("M3", "tennis: sottoscrivi di nuovo una copia (non la funzione condivisa)",
     "Betfair/stream/tennis_live/iscrizione_a_caldo.py",
     "    sottoscrivi,\n    stream_di_mercato,\n)\n",
     "    stream_di_mercato,\n)\nfrom .. import sottoscrizione_a_caldo as _SCM\n\n\n"
     "def sottoscrivi(framework, stream, market_ids):\n"
     "    return _SCM.sottoscrivi(framework, stream, market_ids)\n",
     [T_UNI + "::test_i_due_runner_usano_la_stessa_funzione"]),
    ("M4", "motore: ignora l'esecutore (sempre il worker del calcio)",
     "Betfair/stream/motore_ordini.py",
     "        self._low = esecutore if esecutore is not None else LOW\n",
     "        self._low = LOW\n",
     [T_MOT + "::test_il_motore_tennis_esegue_il_dispatch_del_worker_tennis"]),
    ("M5", "motore: prefisso del ref interno fisso 'awlq' (eventi tennis persi)",
     "Betfair/stream/motore_ordini.py",
     '        pref = self._low._cust_ref("")\n',
     '        pref = "awlq"\n',
     [T_MOT + "::test_specchio_tennis_diventa_evento_order"]),
    ("M6", "worker tennis: time_in_force non letto dal comando",
     "Betfair/stream/tennis_live/tennis_live_order_worker.py",
     '        "time_in_force": (str(merged["time_in_force"]).upper()\n'
     '                          if merged.get("time_in_force") else None),\n',
     '        "time_in_force": None,\n',
     [T_MOT + "::test_fok_e_riduzione_arrivano_al_limitorder"]),
    ("M7", "worker tennis: la chiusura dichiarata non vale per il minimo",
     "Betfair/stream/tennis_live/tennis_live_order_worker.py",
     "    riduce = bool(params.get(\"reduces_liability\"))\n",
     "    riduce = False\n",
     [T_MOT + "::test_fok_e_riduzione_arrivano_al_limitorder"]),
    ("M8", "worker tennis: nessun diario write-ahead prima del place",
     "Betfair/stream/tennis_live/tennis_live_order_worker.py",
     "    _pre_invio(order, market, \"place\")   # 25/09: diario del motore (no-op per la coda)\n",
     "",
     [T_MOT + "::test_il_motore_tennis_esegue_il_dispatch_del_worker_tennis"]),
    ("M9", "worker tennis: customerStrategyRef fisso 'tennis' anche dal motore",
     "Betfair/stream/tennis_live/tennis_live_order_worker.py",
     "    return str(ref)[:15] if ref else CUSTOMER_STRATEGY_REF\n",
     "    return CUSTOMER_STRATEGY_REF\n",
     [T_MOT + "::test_customer_strategy_ref_dell_attore_e_default_tennis"]),
    ("M10", "esecutore: place_submin non rifiutato col motivo dichiarato",
     "Betfair/stream/tennis_live/esecutore_tennis.py",
     '    if action == "place_submin":\n        raise ValueError(MOTIVO_SUBMIN)\n',
     "",
     [T_MOT + "::test_sotto_il_minimo_rifiuto_dichiarato_nessun_ordine"]),
    ("M11", "esecutore: il motore drena anche il /order del desktop",
     "Betfair/stream/tennis_live/esecutore_tennis.py",
     "    def pop_requests(self, max_n: int = 20) -> list:  # noqa: ARG002\n        return []\n",
     "    def pop_requests(self, max_n: int = 20) -> list:  # noqa: ARG002\n"
     "        return self._canale.pop_requests(max_n)\n",
     [T_MOT + "::test_order_del_desktop_resta_al_worker_tennis"]),
    ("M12", "aggancio: servibile anche col libro di prima",
     "Betfair/stream/tennis_live/esecutore_tennis.py",
     "                if libro is None or id(libro) == attesa[mid]:\n                    return False\n",
     "",
     [T_MOT + "::test_aggancio_servibile_solo_con_un_book_nuovo"]),
    ("M13", "aggancio: la partita a mano diventa espellibile",
     "Betfair/stream/tennis_live/esecutore_tennis.py",
     "                ev, manuale=ev in manuali and ev not in self.session.comandi,\n",
     "                ev, manuale=False,\n",
     [T_MOT + "::test_aggancio_tetto_pieno"]),
    ("M14", "piano: il comando sotto la partita armata",
     "Betfair/stream/tennis_live/iscrizione_a_caldo.py",
     "PRI_COMANDO = 3        # 25/09 (F8): un bot ha mandato un ORDINE su questa partita\n",
     "PRI_COMANDO = 2        # mutato\n",
     [T_MOT + "::test_piano_comando_sopra_armata_sotto_a_mano"]),
    ("M15", "runner: la partita di un comando trattata come seguita a mano",
     "Betfair/stream/tennis_live/tennis_runner.py",
     "    return (_AM.origine_follow(follow) != _AM.ORIGINE_AUTO\n            and not _ET.e_comando(follow))\n",
     "    return _AM.origine_follow(follow) != _AM.ORIGINE_AUTO\n",
     [T_MOT + "::test_follows_con_comandi_ttl_e_follow_del_db_vince",
      T_MOT + "::test_follow_nuovo_solo_comandi_non_forza_il_restart"]),
    ("M16", "runner: nessun libro registrato alla sottoscrizione",
     "Betfair/stream/tennis_live/tennis_runner.py",
     "            session.attesa_libro.update(attesa)\n",
     "",
     [T_MOT + "::test_partita_del_comando_entra_a_caldo_sulla_stessa_connessione"]),
    ("M17", "runner: il follow_worker dimentica le partite dei comandi",
     "Betfair/stream/tennis_live/tennis_runner.py",
     "    session.ultimi_follows = list(follows)\n    follows = _ET.follows_con_comandi(session, follows)\n",
     "    session.ultimi_follows = list(follows)\n",
     [T_MOT + "::test_partita_del_comando_entra_a_caldo_sulla_stessa_connessione"]),
    ("M18", "guardia d'avvio: disarmata senza il diario del motore",
     "Betfair/stream/tennis_live/guardie_tennis.py",
     "        if fn_motore is not None and not fn_motore():\n",
     "        if False:\n",
     [T_MOT + "::test_ripresa_d_avvio_non_si_disarma_senza_il_diario_del_motore"]),
    ("M19", "Safe: annullo col prefisso del calcio per ogni attore",
     "Betfair/safe_strategy/porta_ordini.py",
     '    ref = "%s-c%s" % (str(attore or ATTORE_CALCIO), str(bet_id).strip())\n',
     '    ref = "safe-c%s" % str(bet_id).strip()\n',
     [T_SAFE + "::test_ref_annullo_col_prefisso_dell_attore",
      T_SAFE + "::test_annullo_safe_tennis_sul_canale_arriva_col_prefisso_giusto"]),
    ("M20", "Safe: la riga risolta dal canale senza chiesto/abbinato/residuo",
     "Betfair/safe_strategy/bot_service.py",
     '            pulita["meta"].setdefault("esecuzione", {\n',
     '            pulita["meta"].setdefault("_esecuzione_mutata", {\n',
     [T_SAFE + "::test_riga_risolta_dal_canale_porta_chiesto_abbinato_residuo_medio"]),
    ("M21", "J4: ogni ref estraneo passa per ordine del motore",
     "Betfair/safe_strategy/certificazione_tennis.py",
     "    for tr in oss.trades:\n        meta = tr.get(\"meta\") or {}\n"
     "        if not isinstance(meta, dict) or not meta.get(\"canale_ref\"):\n            continue\n",
     "    return True\n    for tr in oss.trades:\n        meta = tr.get(\"meta\") or {}\n"
     "        if not isinstance(meta, dict) or not meta.get(\"canale_ref\"):\n            continue\n",
     [T_SAFE + "::test_j4_resta_rosso_per_un_ref_sbagliato_senza_canale"]),
    ("M22", "esecutore: annullo cross-mode non fermato",
     "Betfair/stream/tennis_live/esecutore_tennis.py",
     "            _low._assert_order_mode(ordine, mode, action)\n",
     "            pass\n",
     [T_MOT + "::test_annullo_mai_cross_mode"]),
    ("M23", "banco tennis: lo specchio non arriva al motore (profilo rapido)",
     "Betfair/stream/backtest/porta_banco.py",
     "        TW.aggiungi_osservatore_ordini(self.motore._su_riga_specchio)\n",
     "",
     [T_MOT + "::test_profilo_rapido_safe_tennis_sulla_registrazione_vera"]),
]


def _sha(testo: str) -> str:
    return hashlib.sha1(testo.encode("utf-8")).hexdigest()


def main(argv: list) -> int:
    scelte = set(argv[1:])
    righe = []
    sopravvissute = 0
    for mid, desc, file, old, new, tests in MUTAZIONI:
        if scelte and mid not in scelte:
            continue
        orig = io.open(file, encoding="utf-8", newline="").read()
        sha0 = _sha(orig)
        if orig.count(old) != 1:
            righe.append("%s ERRORE: frammento non trovato una volta sola in %s" % (mid, file))
            sopravvissute += 1
            continue
        try:
            io.open(file, "w", encoding="utf-8", newline="").write(orig.replace(old, new))
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p",
                                "no:cacheprovider", *tests], capture_output=True, text=True,
                               timeout=900)
        finally:
            io.open(file, "w", encoding="utf-8", newline="").write(orig)
        ok_rip = _sha(io.open(file, encoding="utf-8", newline="").read()) == sha0
        esito = "ROSSO" if r.returncode != 0 else "SOPRAVVISSUTA"
        if r.returncode == 0:
            sopravvissute += 1
        ultima = [x for x in r.stdout.strip().splitlines() if x.strip()][-1:] or ["?"]
        righe.append("%s %s - %s | %s | ripristino sha1 %s" % (
            mid, esito, desc, ultima[0][:120], "OK" if ok_rip else "DIVERSO"))
        print(righe[-1], flush=True)
    righe.append("TOTALE: %d mutazioni, %d sopravvissute" % (
        len(righe), sopravvissute))
    print(righe[-1])
    with io.open(os.path.join(os.path.dirname(__file__), "falsificazione.txt"), "w",
                 encoding="utf-8") as f:
        f.write("\n".join(righe) + "\n")
    return 1 if sopravvissute else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
