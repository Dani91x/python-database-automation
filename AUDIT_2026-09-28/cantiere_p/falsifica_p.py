"""Falsificazione del cantiere P: ogni mutazione reintroduce un difetto, i test
indicati devono diventare ROSSI. Ripristino byte-identico verificato (SHA-256).
Uso (dal worktree): .venv\\Scripts\\python.exe AUDIT_2026-09-28\\cantiere_p\\falsifica_p.py [id ...]
ASCII-only."""
import hashlib
import subprocess
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[2]
PY = str(WT / ".venv" / "Scripts" / "python.exe")
EX = "Betfair/safe_strategy/execution.py"
BS = "Betfair/safe_strategy/bot_service.py"
T_P = "Betfair/safe_strategy/tests/test_p_nessun_fill_di_casa_2026_09_28.py"
T_X = "Betfair/safe_strategy/tests/test_execution.py"
T_B = "Betfair/safe_strategy/tests/test_bot_service.py"
T_A = "Betfair/safe_strategy/tests/test_paper_fill_al_best_2026_09_26.py"

VECCHIO_FILL = '''        return PlaceOutcome("error", None, 0.0, None, f"paper_senza_runner:{gate_reason}",
                            size_requested=size, size_remaining=0.0)'''
FILL_DI_CASA = '''        fill = E.paper_fill(size, best_price=price, lay_ladder=_ladder_tuple(ladder),  # MUTAZIONE
                            limit_price=price, side=side, best_size=best_size)
        if fill is None or fill.matched_size <= 0:
            return PlaceOutcome("error", None, 0.0, None, f"paper_no_fill:{gate_reason}")
        return PlaceOutcome("open", fill.avg_price, fill.matched_size, None,
                            f"paper_fill:{gate_reason}")'''

MUT = {
    "m1_fill_di_casa": (EX, VECCHIO_FILL, FILL_DI_CASA,
                        [T_P + "::test_apertura_paper_senza_runner_non_eseguita_e_NON_consuma_il_tentativo",
                         T_P + "::test_uscita_paper_senza_runner_resta_da_ritentare_e_poi_esce",
                         T_P + "::test_safe_tennis_paper_senza_runner_non_riempie_in_casa",
                         T_X + "::test_place_paper_senza_runner_non_esegue_nulla",
                         T_X + "::test_omega_chiusura_paper_senza_runner_non_si_riempie_in_casa",
                         T_A]),
    "m2_close_rest_non_ignorato": (EX, 'if mode == "paper" and str(params.get("execution_mode") or "auto") != "auto":',
                                   'if False:  # MUTAZIONE',
                                   [T_P + "::test_chiusura_paper_con_rest_va_comunque_al_runner"]),
    "m3_apertura_rest_non_ignorato": (BS, '    if str(riga.get("mode") or "") != "paper":\n        return params',
                                      '    if True:  # MUTAZIONE\n        return params',
                                      [T_P + "::test_apertura_paper_con_rest_va_comunque_al_runner",
                                       T_P + "::test_params_ordine_rest_diventa_auto_solo_in_paper"]),
    "m4_s7_rimando_paper": (EX, "    lock = locked_pnl(trade, plan)\n",
                            "    if mode == 'paper' and not (prices.get(f'{side}_ladder') or ()) and (best_size is None or float(best_size) <= 0):  # MUTAZIONE\n"
                            "        return {'error': 'liquidita_del_book_ignota'}\n"
                            "    lock = locked_pnl(trade, plan)\n",
                            [T_X + "::test_close_trade_paper_senza_size_del_book_va_al_runner_come_il_live",
                             T_X + "::test_close_trade_senza_size_paper_e_live_partono_uguali"]),
    "m5_reconcile_conferma_riserva": (BS, '                _terminal_error(db, tr, reason="reconcile_paper_senza_runner", now=now,',
                                      '                _reconcile_confirm(db, tr, price=float(tr.get("price") or 0.0), size=float(tr.get("size") or 0.0), bet_id=None, how="paper", now=now)  # MUTAZIONE\n'
                                      '                n += 1\n'
                                      '                continue\n'
                                      '                _terminal_error(db, tr, reason="reconcile_paper_senza_runner", now=now,',
                                      [T_B + "::test_reconcile_paper_riga_storica_senza_fase_non_si_conferma_piu"]),
    "m6_motivo_rinominato": (EX, 'f"paper_senza_runner:{gate_reason}"', 'f"paper_runner_assente:{gate_reason}"',
                             [T_P + "::test_apertura_paper_senza_runner_non_eseguita_e_NON_consuma_il_tentativo",
                              "Betfair/stream/tests/test_r3_freno_unico_2026_09_25.py::test_safe_paper_freno_rilasciato_parita"]),
    "m7_paper_ladder_ancora_cancello": (BS, "    # F1 (25/09): ref UNIFICATO",
                                        "    if mode == 'paper' and feed_prices is None:  # MUTAZIONE\n"
                                        "        _place_fail(db, trade_id, row, 'paper_prezzi_non_disponibili', now, params)\n"
                                        "        return X.PlaceOutcome('error', None, 0.0, None, 'paper_prezzi_non_disponibili')\n"
                                        "    # F1 (25/09): ref UNIFICATO",
                                        [T_P + "::test_apertura_paper_col_runner_va_in_coda_e_si_conferma_dal_poll",
                                         T_P + "::test_stesso_ordine_paper_al_runner_e_live_a_betfair"]),
}

# --- blocco 3 (punti 5-7) -------------------------------------------------
OM = "Betfair/omega/omega_service.py"
SC = "Betfair/safe_strategy/service.py"
PO_ = "Betfair/safe_strategy/porta_ordini.py"
CK = "Betfair/safe_strategy/certificazione_k.py"
T_3 = "Betfair/safe_strategy/tests/test_p_blocco3_2026_09_28.py"
MUT.update({
    "m8_omega_senza_timeout": (OM, '__import__("db_client").usa_timeout_bot())',
                               '"MUTAZIONE")',
                               [T_3 + "::test_omega_main_accende_il_profilo_bot_prima_di_tutto"]),
    "m9_scanner_senza_timeout": (SC, "                    _dbc.usa_timeout_bot())",
                                 "                    'MUTAZIONE')",
                                 [T_3 + "::test_scanner_main_accende_il_profilo_bot_prima_del_client"]),
    "m10_cor_non_salvato": (BS, "    if cor and not meta.get(\"canale_cor\"):",
                            "    if False:  # MUTAZIONE",
                            [T_3 + "::test_cor_salvato_alla_prima_vista"]),
    "m11_reconcile_senza_cor": (EX, "    ref = refs_di_riconciliazione(trade, ref)\n",
                                "    pass  # MUTAZIONE\n",
                                [T_3 + "::test_reconcile_decision_ritrova_l_ordine_per_cor",
                                 T_3 + "::test_riga_live_senza_eventi_si_ritrova_su_betfair_per_cor"]),
    "m12_memoria_perde_il_cor": (PO_, '            if prima is not None and prima.get("cor") and not copia.get("cor"):',
                                 '            if False:  # MUTAZIONE',
                                 [T_3 + "::test_la_memoria_del_canale_conserva_il_cor_del_primo_evento"]),
    "m13_tennis_non_al_minimo": (EX, '    return str(client_ref or "").startswith("safe_tennis-")',
                                 '    return False  # MUTAZIONE',
                                 [T_3 + "::test_tennis_live_rest_back_122_diventa_200",
                                  T_3 + "::test_tennis_paper_coda_al_minimo"]),
    "m14_chiusura_gonfiata": (EX, "    if not is_closing and _e_tennis(client_ref):",
                              "    if _e_tennis(client_ref):  # MUTAZIONE",
                              [T_3 + "::test_tennis_chiusura_sotto_il_minimo_resta_esatta"]),
    "m15_banco_senza_cor": (CK, '"customer_order_ref", "canale_cor"):',
                            '"customer_order_ref"):  # MUTAZIONE',
                            [T_3 + "::test_ref_di_riga_del_banco_include_il_cor"]),
    "m16_cleared_senza_cor": (EX, "    return by_ref.get(cor) if cor else None",
                              "    return None  # MUTAZIONE",
                              [T_3 + "::test_cleared_match_per_cor"]),
})

# --- correzione del coordinatore: il runner giu' non consuma tentativi ---
BD = "Betfair/safe_strategy/bot_db.py"
MUT.update({
    "m17_senza_runner_consuma": (BS, "    if X.e_senza_runner(err):\n        _place_fail_senza_runner(db, trade_id, row, err, now)\n        return\n",
                                 "    pass  # MUTAZIONE\n",
                                 [T_P + "::test_apertura_paper_senza_runner_non_eseguita_e_NON_consuma_il_tentativo",
                                  T_P + "::test_runner_giu_per_cinque_giri_poi_su_l_apertura_parte_senza_tentativi_consumati"]),
    "m18_seme_riconta": (BD, "        if pl.get(\"senza_runner\") or str(pl.get(\"last_error\") or \"\").startswith(\n                \"paper_senza_runner\"):\n            continue\n",
                         "        pass  # MUTAZIONE\n",
                         [T_P + "::test_dopo_il_riavvio_le_righe_senza_runner_non_contano"]),
    "m19_log_senza_freno": (BS, "    if ultimo is None or now.timestamp() - ultimo >= _SENZA_RUNNER_LOG_S:",
                            "    if True:  # MUTAZIONE",
                            [T_P + "::test_apertura_paper_senza_runner_non_eseguita_e_NON_consuma_il_tentativo"]),
    "m20_nessuna_attesa": (BS, "    st[\"next_ts\"] = now.timestamp() + attesa\n",
                           "    st[\"next_ts\"] = now.timestamp()  # MUTAZIONE\n",
                           [T_P + "::test_apertura_paper_senza_runner_non_eseguita_e_NON_consuma_il_tentativo"]),
})

# --- reperti del revisore: P-O1, uscite a runner giu', cor storico, riepilogo ---
T_G = "Betfair/omega/test_omega_greenup_2026_09_10.py"
MUT.update({
    "m21_po1_integrale_come_prima": (OM, "    integral = residual is None and (bool(res.get(\"pending_fill\")) or covered)",
                                     "    integral = covered  # MUTAZIONE",
                                     [T_G + "::test_p_o1_green_up_integrale_col_fill_in_volo_e_greenup",
                                      T_G + "::test_take_profit_blocca_il_profitto_quasi_pieno"]),
    "m22_po1_stato_mai_done": (OM, "                _greenup_fill_confermato(db, tr, now)\n",
                               "                pass  # MUTAZIONE\n",
                               [T_G + "::test_p_o1_stato_done_al_fill_e_mai_un_secondo_invio"]),
    "m23_uscita_senza_runner_consuma": (BS, "    if err and X.e_senza_runner(res.get(\"detail\")):",
                                        "    if False:  # MUTAZIONE",
                                        [T_P + "::test_uscita_paper_senza_runner_resta_da_ritentare_e_poi_esce"]),
    "m24_riserva_a_runner_giu": (EX, "    if mode == \"paper\":\n        motivo = _runner_paper_assente(",
                                 "    if False:  # MUTAZIONE\n        motivo = _runner_paper_assente(",
                                 [T_P + "::test_uscita_paper_senza_runner_resta_da_ritentare_e_poi_esce",
                                  T_X + "::test_omega_chiusura_paper_senza_runner_non_si_riempie_in_casa"]),
    "m25_omega_green_up_consuma": (OM, "    if err and X.e_senza_runner(res.get(\"detail\")):",
                                   "    if False:  # MUTAZIONE",
                                   [T_G + "::test_p_green_up_paper_senza_runner_non_consuma_e_avvisa"]),
    "m26_cor_storico_perso": (BS, "        if meta.get(\"canale_cor\") and meta[\"canale_cor\"] not in storico:",
                              "        if False:  # MUTAZIONE",
                              [T_3 + "::test_ordine_nuovo_della_stessa_riga_aggiorna_il_cor_e_tiene_lo_storico"]),
    "m27_cor_mai_aggiornato": (BS, "    if cor and cor != meta.get(\"canale_cor\"):",
                               "    if cor and not meta.get(\"canale_cor\"):  # MUTAZIONE",
                               [T_3 + "::test_ordine_nuovo_della_stessa_riga_aggiorna_il_cor_e_tiene_lo_storico"]),
    "m28_riepilogo_assente": (BS, "    if chiuse_senza_runner:\n",
                              "    if False:  # MUTAZIONE\n",
                              [T_B + "::test_reconcile_paper_riga_storica_senza_fase_non_si_conferma_piu"]),
})
MUT.update({
    "m29_canale_alzato_in_execution": (EX, "    if not is_closing and not via_canale and _e_tennis(client_ref):",
                                       "    if not is_closing and _e_tennis(client_ref):  # MUTAZIONE",
                                       [T_3 + "::test_tennis_sul_canale_la_size_non_si_tocca_la_porta_al_minimo_il_motore",
                                        "Betfair/stream/tennis_live/tests/test_motore_ordini_tennis_2026_09_25.py::test_profilo_rapido_safe_tennis_sulla_registrazione_vera"]),
    "m30_rest_non_dichiara": (BS, "            meta[\"portata_al_minimo\"] = dict(nota_place[\"portata_al_minimo\"])",
                              "            pass  # MUTAZIONE",
                              [T_3 + "::test_tennis_rest_live_riga_e_attivita_dicono_chiesto_e_piazzato"]),
})
MUT["m14_chiusura_gonfiata"] = (EX, "    if not is_closing and not via_canale and _e_tennis(client_ref):",
                                "    if not via_canale and _e_tennis(client_ref):  # MUTAZIONE",
                                [T_3 + "::test_tennis_chiusura_sotto_il_minimo_resta_esatta"])
MUT["m16_cleared_senza_cor"] = (EX, "        if cor in by_ref:\n            return by_ref[cor]\n",
                                "        pass  # MUTAZIONE\n",
                                [T_3 + "::test_cleared_match_per_cor"])
MUT["m10_cor_non_salvato"] = (BS, "    if cor and cor != meta.get(\"canale_cor\"):",
                              "    if False:  # MUTAZIONE",
                              [T_3 + "::test_cor_salvato_alla_prima_vista"])


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ids = sys.argv[1:] or list(MUT)
    esiti = []
    for mid in ids:
        f, old, new, tests = MUT[mid]
        path = WT / f
        orig = path.read_bytes()
        h0 = sha(path)
        txt = orig.decode("utf-8")
        if "\r\n" in txt:  # file con CRLF: i blocchi multi-riga si adeguano
            old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
        n = txt.count(old)
        if n != 1:
            esiti.append((mid, f"ANCORA NON TROVATA ({n})"))
            continue
        try:
            path.write_bytes(txt.replace(old, new).encode("utf-8"))
            r = subprocess.run([PY, "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider"],
                               cwd=WT, capture_output=True, text=True, timeout=900)
            ultima = (r.stdout.strip().splitlines() or ["?"])[-1]
            rossi = "failed" in ultima or "error" in ultima
            esiti.append((mid, ("ROSSA " if rossi else "VERDE!! ") + ultima))
        finally:
            path.write_bytes(orig)
        assert sha(path) == h0, f"ripristino NON identico per {mid}"
        assert b"MUTAZIONE" not in path.read_bytes() and b"paper_runner_assente" not in path.read_bytes()
    for mid, e in esiti:
        print(f"{mid}: {e}")


if __name__ == "__main__":
    main()
