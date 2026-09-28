"""Falsificazione del cantiere C (28/09): ogni mutazione reintroduce UN difetto,
i test indicati devono diventare ROSSI. Il file originale si ripristina dal
contenuto in memoria (byte per byte) in un ``finally``; alla fine si verifica
l'hash e l'assenza della parola MUTAZIONE. Non interrompere a meta'.

    .venv\\Scripts\\python.exe AUDIT_2026-09-28\\cantiere_c\\falsifica_c.py
"""
import hashlib
import io
import os
import subprocess
import sys

WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = os.path.join(WT, ".venv", "Scripts", "python.exe")
SVC = os.path.join(WT, "Betfair", "omega", "omega_service.py")
PRO = os.path.join(WT, "Betfair", "omega", "omega_proposte.py")
DBF = os.path.join(WT, "Betfair", "omega", "omega_db.py")
ENG = os.path.join(WT, "Betfair", "omega", "omega_engine.py")
TRR = os.path.join(WT, "Betfair", "stream", "backtest", "trasporto_rapido.py")
NT = "Betfair/omega/tests/test_cantiere_c_parita_paper_live_2026_09_28.py"

MUT = [
    ("M1 canale: FOK solo live", SVC,
     "vista = _PO.VistaOmega(porta, time_in_force=_PO.FOK, riduce=False)",
     "vista = _PO.VistaOmega(porta, time_in_force=(_PO.FOK if str(mode) == 'live' else None), riduce=False)  # MUTAZIONE",
     [NT + "::test_canale_paper_e_live_mandano_lo_stesso_comando",
      "Betfair/omega/tests/test_porta_ordini_omega_f6_2026_09_24.py::test_apertura_paper_comando_giusto_e_conferma_da_evento",
      "Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py::test_profilo_rapido_verde_sulla_registrazione_vera"]),
    ("M2 coda: FOK solo live", SVC,
     '    payload["time_in_force"] = "FILL_OR_KILL"\n    try:\n        rid = db.enqueue_live_order(payload)',
     '    if mode == "live":  # MUTAZIONE\n        payload["time_in_force"] = "FILL_OR_KILL"\n    try:\n        rid = db.enqueue_live_order(payload)',
     [NT + "::test_coda_paper_e_live_stesso_payload",
      "Betfair/omega/test_omega_flumine_live.py::test_invariante_paper_mai_richieste_live",
      "Betfair/omega/tests/test_porta_ordini_omega_f6_2026_09_24.py::test_spento_parita_apertura_paper_coda"]),
    ("M5 reconcile paper: fill dalla riserva", SVC,
     "    if voce is None:\n        return []\n    o = voce[\"ordine\"]",
     "    if voce is None:  # MUTAZIONE\n        return [{\"customer_order_ref\": E.customer_ref_for(tr[\"id\"]), \"size_matched\": float(tr.get(\"size\") or 0), \"size_remaining\": 0.0, \"avg_price_matched\": tr.get(\"price\"), \"bet_id\": None}]\n    o = voce[\"ordine\"]",
     [NT + "::test_riserva_con_risposta_persa_mai_un_fill_inventato_paper_come_live",
      NT + "::test_riavvio_perde_la_fonte_paper_e_la_riga_non_diventa_un_fill",
      "Betfair/omega/test_omega_audit_2026_09_11.py::test_m11_riserva_senza_fill_non_confermata_dal_reconcile"]),
    ("M7 chiusura in volo registrata", SVC,
     "        if res.get(\"error\") or res.get(\"pending_fill\") or not res.get(\"closing_trade_id\"):",
     "        if res.get(\"error\") or not res.get(\"closing_trade_id\"):  # MUTAZIONE",
     [NT + "::test_chiusura_non_registrata_se_non_eseguita_dal_simulatore"]),
    ("M8 cash-out manuale non registra", SVC,
     "    ricorda_chiusura_paper(tr, res, now)   # fonte vera del paper legacy (cantiere C)\n    if res.get(\"error\"):",
     "    pass  # MUTAZIONE\n    if res.get(\"error\"):",
     [NT + "::test_le_tre_chiusure_registrano_la_fonte_paper"]),
    ("M9 read_control senza protezione", SVC,
     "        try:\n            return db.read_control(), None\n        except Exception as ex:  # noqa: BLE001 - si ritenta, poi giro degradato\n            errore = str(ex)[:160]",
     "        return db.read_control(), None  # MUTAZIONE",
     [NT + "::test_read_control_ko_giro_di_sola_gestione_con_l_ultimo_controllo",
      NT + "::test_read_control_ko_senza_controllo_valido_solo_riconciliazione",
      NT + "::test_read_control_ko_una_volta_si_ritenta_e_il_giro_e_normale"]),
    ("M10 controllo vecchio usato per aprire", SVC,
     "    if errore_controllo is not None:\n        return _giro_senza_controllo(market=market, db=db, now=now,\n                                     errore=errore_controllo, greenup_feed=greenup_feed)",
     "    if errore_controllo is not None:  # MUTAZIONE\n        control = _ULTIMO_CONTROLLO.get(\"control\")",
     [NT + "::test_read_control_ko_giro_di_sola_gestione_con_l_ultimo_controllo",
      NT + "::test_bot_fermato_durante_il_buco_non_riparte_con_il_controllo_vecchio"]),
    ("M11 nessun ritentativo", SVC,
     "    for pausa in _PAUSE_LETTURA_CONTROLLO_S:",
     "    for pausa in _PAUSE_LETTURA_CONTROLLO_S[:1]:  # MUTAZIONE",
     [NT + "::test_read_control_ko_una_volta_si_ritenta_e_il_giro_e_normale"]),
    ("M12 senza controllo valido gira tutto", SVC,
     "    ultimo = _ULTIMO_CONTROLLO.get(\"control\")\n    ora_ts = now.timestamp()",
     "    ultimo = _ULTIMO_CONTROLLO.get(\"control\") or {}  # MUTAZIONE\n    ora_ts = now.timestamp()",
     [NT + "::test_read_control_ko_senza_controllo_valido_solo_riconciliazione"]),
    ("M13 proposte: chiusura senza porta", PRO,
     "                                extra_row=extra,\n                                **S._porta_kw_chiusura(params, modo_riga))",
     "                                extra_row=extra)  # MUTAZIONE",
     [NT + "::test_uscita_automatica_passa_dalla_porta_come_le_altre_chiusure"]),
    ("M14 missione: pending paper non vivo", SVC,
     "    alive = any(t.get(\"status\") in (\"open\", \"pending\")\n                for t in trades if t.get(\"phase\"))",
     "    alive = any(t.get(\"status\") in (\"open\",) or (t.get(\"status\") == \"pending\" and (t.get(\"bet_id\") or str(t.get(\"mode\")) == \"live\"))  # MUTAZIONE\n                for t in trades if t.get(\"phase\"))",
     [NT + "::test_missione_non_si_chiude_con_un_pending_senza_bet_id"]),
    ("M15 paper: richiesta stantia non revocata", SVC,
     "        if str(req.get(\"status\")) == \"pending\" and mirror is None and matched <= 0:",
     "        if False:  # MUTAZIONE",
     [NT + "::test_richiesta_mai_presa_in_carico_revocata_alla_scadenza",
      NT + "::test_revoca_paper_persa_la_riga_resta_in_attesa"]),
    ("M16 (coordinatore) ordine di un'altra riga accettato", SVC,
     "    return [dict(o)] if stessa else []",
     "    return [dict(o)]  # MUTAZIONE",
     [NT + "::test_ordine_registrato_di_un_altra_riga_non_conferma"]),
    ("M17 controllo vecchio senza eta' massima", SVC,
     "    scaduto = ultimo is not None and eta > _ULTIMO_CONTROLLO_MAX_ETA_S",
     "    scaduto = False  # MUTAZIONE",
     [NT + "::test_controllo_troppo_vecchio_solo_riconciliazione"]),
    ("M18 D1: torna il fill di casa (automatico)", SVC,
     "        # runner non disponibile: apertura NON eseguita, esito certo, nessun\n",
     "        _confirm_open_trade(db, trade_id, event_id=ev.event_id, price=price, size=size, liability=E.liability_from_lay(size, price), bet_id=None, meta={}, mode='paper'); return 1  # MUTAZIONE\n",
     ["Betfair/omega/test_omega_flumine_paper.py::test_gate_ko_runner_giu_apertura_non_eseguita",
      "Betfair/omega/test_omega_flumine_paper.py::test_enqueue_ko_apertura_non_eseguita",
      "Betfair/omega/test_t3_consapevolezza_2026_09_17.py::test_r_j6_paper_senza_runner_nessun_fill_ne_parziale"]),
    ("M19 D1: 'rest' chiude il runner in paper", SVC,
     "                         params={**(params or {}), \"execution_mode\": \"auto\"}, now=now)",
     "                         params=params, now=now)  # MUTAZIONE",
     ["Betfair/omega/test_omega_flumine_paper.py::test_execution_mode_rest_in_paper_usa_comunque_il_runner",
      "Betfair/omega/test_omega_flumine_paper.py::test_gate_paper_ignora_execution_mode_rest"]),
    ("M20 D1: torna il fill di casa (manuale)", SVC,
     "                           blocco, trade_id)\n        db.update_trade(trade_id, status=\"error\", pnl=0.0,",
     "                           blocco, trade_id)\n        db.update_trade(trade_id, status=\"open\", pnl=0.0,  # MUTAZIONE",
     ["Betfair/omega/test_omega_flumine_paper.py::test_manuale_gate_ko_ordine_non_eseguito",
      NT + "::test_manuale_paper_senza_runner_non_eseguito"]),
    ("M21 D3: orfano paper non regolato col risultato", SVC,
     "            vince = E.vince_col_risultato(tr.get(\"runner_name\"), risultato,",
     "            vince = None and E.vince_col_risultato(tr.get(\"runner_name\"), risultato,  # MUTAZIONE",
     [NT + "::test_orfano_paper_regolato_col_risultato_vero"]),
    ("M22 D3: esito dedotto anche in live", SVC,
     "        if str(tr.get(\"mode\")) == \"paper\":\n            chiave = E.result_key_for_trade(tr)",
     "        if True:  # MUTAZIONE\n            chiave = E.result_key_for_trade(tr)",
     [NT + "::test_orfano_senza_risultato_o_live_resta_aperto_con_allarme"]),
    ("M23 D4: il servizio somma le modalita'", SVC,
     "        agg_pagina, agg = _aggregati_cached(db, day_start, ora_ts,\n                                            mode=str(control.get(\"mode\") or \"paper\"))",
     "        agg_pagina, agg = _aggregati_cached(db, day_start, ora_ts,\n                                            mode=None)  # MUTAZIONE",
     [NT + "::test_perdita_di_una_modalita_non_ferma_l_altra"]),
    ("M24 D4: DB in casa senza filtro", DBF,
     "    rows = E.righe_della_modalita(_righe_per_aggregati(), mode)",
     "    rows = _righe_per_aggregati()  # MUTAZIONE",
     [NT + "::test_db_aggregati_per_modalita_senza_migrazione_in_casa"]),
    ("M25 D3/engine: Any Other senza punteggi quotati", ENG,
     "    if (h, a) in quotati:\n        return False",
     "    if False:  # MUTAZIONE\n        return False",
     [NT + "::test_vince_col_risultato"]),
]

INTERRUTTORI = (
    "SAFE_SCAN_CANALE", "MIKE_CANALE_POSIZIONI", "OMEGA_CANALE_POSIZIONI",
    "SAFE_CANALE_POSIZIONI", "TENNIS_BOT_CANALE", "SAFE_BOT_LEGGE_CANALE",
    "SAFE_BOT_SVEGLIA_CANALE", "OMEGA_SVEGLIA_CANALE", "MIKE_SVEGLIA_CANALE",
    "TENNIS_BOT_SVEGLIA_CANALE", "MIKE_LEGGE_CANALE", "OMEGA_LEGGE_CANALE",
    "PUNTEGGI_CANALE", "ESITI_ORDINI_CANALE", "MOTORE_ORDINI_CANALE", "SCALPER_CANALE",
    "SAFE_ORDINI_VIA_CANALE", "OMEGA_ORDINI_VIA_CANALE", "MOTORE_ORDINI_CANALE_TENNIS",
    "SAFE_TENNIS_ORDINI_VIA_CANALE")


def _md5(p):
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def main():
    env = dict(os.environ)
    for v in INTERRUTTORI:       # il .env vero accende i canali: nei test si spengono
        env[v] = "0"
    hash_prima = {p: _md5(p) for p in (SVC, PRO, DBF, ENG, TRR)}
    esiti = []
    for nome, path, vecchio, nuovo, tests in MUT:
        with io.open(path, "rb") as f:
            originale = f.read()
        testo = originale.decode("utf-8")
        crlf = "\r\n" in testo
        v = vecchio.replace("\n", "\r\n") if crlf else vecchio
        n = nuovo.replace("\n", "\r\n") if crlf else nuovo
        if testo.count(v) != 1:
            esiti.append((nome, "NON APPLICATA", "occorrenze=%d" % testo.count(v)))
            continue
        try:
            with io.open(path, "wb") as f:
                f.write(testo.replace(v, n).encode("utf-8"))
            r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests],
                               cwd=WT, env=env, capture_output=True, text=True, timeout=600)
            righe = [l for l in r.stdout.splitlines() if " passed" in l or " failed" in l]
            esiti.append((nome, "ROSSO" if r.returncode != 0 else "VERDE (!!)",
                          righe[-1] if righe else r.stdout[-300:]))
        finally:
            with io.open(path, "wb") as f:
                f.write(originale)
    for e in esiti:
        print("%-42s %-14s %s" % e)
    for p, h in hash_prima.items():
        with io.open(p, encoding="utf-8") as f:
            pulito = "MUTAZIONE" not in f.read()
        print(("hash invariato" if _md5(p) == h else "HASH CAMBIATO!!"),
              ("MUTAZIONE=0" if pulito else "MUTAZIONE PRESENTE!!"), os.path.basename(p))
    return 0 if all(e[1] == "ROSSO" for e in esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
