"""D_scheletro_righe.py - misura usa-e-getta (scheda D, 08/10/2026).

Per ogni file dei servizi dei bot legge SOLO con `ast` le definizioni di primo livello
(def e class) e le divide in: S = scheletro del runtime (ciclo, controllo, canali,
heartbeat, arresto, avvio, persistenza dello stato, comandi dall'app), M = misto
(scheletro e configurazione di strategia insieme: run_session, setup_and_run,
_instantiate_bot), R = resto (strategia, ordini, regolamento: altre schede).
L'elenco S/M e' scritto qui sotto a mano dai nomi; R = tutto il resto.
Conta le righe (end_lineno - lineno + 1) di ogni def/class. Nessun import del codice
di produzione, nessuna scrittura. Uso: python -I D_scheletro_righe.py [misura|elenca|db]
"""
import ast
import difflib
import io
import os
import sys
import tokenize

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

S = {}
M = {}
FILE = {
    "mike": "Betfair/mike/service.py",
    "omega": "Betfair/omega/omega_service.py",
    "safe": "Betfair/safe_strategy/bot_service.py",
    "scalper_svc": "Betfair/stream/scalper/scalper_service.py",
    "scalper_sess": "Betfair/stream/scalper/scalper_session.py",
    "tennis_svc": "Betfair/stream/tennis_live/tennis_bot_service.py",
    "tennis_run": "Betfair/stream/tennis_live/tennis_runner.py",
}
S["mike"] = """mike_live_abilitato _LiveNonAbilitato _pretendi_live_abilitato _RealMarket _Cache _now _iso
svuota_le_cache azzera_cache_di_processo _scanner_stato _stato_scanner_dal_canale _scanner_age
_log_throttled _config_warn _result _richiesta_non_di_questa_partita process_requests _id_approvazione
_approvazione_eseguita _chiave_gamba _request_approva_uscita _request_cancel ferma_al_nuovo_avvio run_once
_operating_day_start_ts _operating_day_key _ctx_legs_of _open_liability posti_occupati_per_modo
_cadenza_battito partite_di_modalita_diversa _locked_open_pnl _aggregates_cached _aggregates _event_rows
_legs_from_json _ctx_from_row _row_from_ctx _corpo_sostanziale _signature _cadenza_pubblicazione _gambe_vive
_scrivi_evento _persist _svuota_lotto installa_conto_canale avvia_conto_dal_canale _avvia_canale _AlzaSveglia
_evento_seguito _pavimento_sveglia _su_sveglia_dal_canale _avvia_sveglia _client_scan_alza_sveglia
statistiche_sveglia _dormi_o_sveglia _canale_feed_acceso avvia_client_scan azzera_canale_scan
_canale_copre_tutte _feed_non_letto _avvisa_feed_non_letto _righe_del_feed statistiche_canale_scan
_pubblica_evento _pubblica_stato _ciclo_persistente arresto_con_ordini _al_segnale
_installa_segnali_di_arresto main""".split()
S["omega"] = """_now _Cache _mono _cadenza svuota_le_cache _fase_dovuta _insieme_cached _aggregati_cached _con_modalita
_feed_riga_cached _scanner_eta_cached giro_minimo_canale_s _SvegliaDalCanale _ricorda_posizioni_vive
_evento_con_posizione_viva _sveglia_dal_client_scan _canale_scan_attivo _riga_dal_canale _fondi_riga
_riga_del_giro _conta_fonte_scan fonte_scan_del_giro _con_fonte_scan avvia_client_scan
_applica_esiti_dal_canale avvia_esiti_ordini ferma_esiti_ordini esiti_ciclo ferma_client_scan _feed_row
run_once _fasi_di_gestione _giro_senza_controllo _leggi_controllo ferma_al_nuovo_avvio _degraded_heartbeat
_c_e_fretta _idle_stats _idle_stats_due _events_refresh_due _cadenza_battito now_iso _maybe_keepalive
_call_windowed _acquire_single_instance_lock _avvia_canale _evento_seguito _pavimento_sveglia
_su_sveglia_dal_canale _avvia_sveglia statistiche_sveglia _dormi_o_sveglia _control_per_canale
_pubblica_stato _ciclo_persistente _chiudi_all_arresto main _build_score_lookup process_manual
chiudi_eventi_in_attesa eventi_chiusi_dall_utente _marca_chiuso_dall_utente _richiesta_non_di_questa_riga
_uscita_del_bot_approvata refresh_events""".split()
S["safe"] = """_MercatoSafe _now resolve_params _f normalize_strategy_modes normalize_uscite_automatiche
uscite_automatiche_di modalita_di_strategia normalize_variants params_effective params_corrections
normalize_control_params _is_invalid_value prices_from_row _price_block rest_gate prices_for
_import_engine_module _import_opportunity_module _import_optional _extra_mods _omega_service
process_requests _request_state _request_result _request_cancel _request_riprendi_evento marcatore_utente
evento_chiuso_dall_utente indicizza_chiusure_utente _marca_righe segna_chiuso_dall_utente riprendi_evento
e_del_bot _righe_vive_del_bot _tutte_le_righe _richiesta_non_di_questa_riga _uscita_del_bot_approvata
_canale_scan_acceso avvia_client_scan installa_sveglia_canale azzera_canale_scan _avvisa_feed_non_letto
_leggi_righe_scan _giro_veloce_acceso azzera_giro_veloce stato_giro_veloce _sport_di _fotografa_giro_lento
interessa_al_giro_veloce segnala_prezzo_nuovo _righe_fresche_del_canale _novita_per_il_lento run_giro_veloce
giro_veloce_se_dovuto _attesa_prima_del_prossimo_veloce strategy_modes_a_paper _cadenza_battito
ferma_al_nuovo_avvio run_once _segnala_errore_di_ciclo _pulisci_errore_di_ciclo set_log_mode _log
params_signature _build_engine _build_model _avvia_canale _control_per_canale _pubblica_stato
_avvia_esiti_ordini _esiti_ciclo _minimo_fra_due_giri _attesa_interrompibile _sbircia_la_coda
_attesa_con_giro_veloce _control_per_il_giro _usa_timeout_bot _ciclo_persistente _chiudi_all_arresto main
svuota_le_cache remember_event_names event_name_for _agg_recente""".split()
S["scalper_svc"] = None   # tutto il file
S["scalper_sess"] = """motivo_freno sorveglia_freno dichiara_stato_finale non_partire_col_freno freno_soldi_veri
non_partire_senza_soldi_veri _strategy_flat _wait_flat _now_iso _esposizioni_nette _dichiarazione_non_flat
residuo_netto dichiarazione_stop_non_flat _ordini_vivi _session_bet_ids _bet_ids_da_lasciare
_mercato_chiuso_in_flumine partita_finita _sweep_cancel _ordini_vivi_lista annulla_ordini_vivi_all_arresto
chiudi_all_arresto _order_client_kwargs mantieni_sessione _handle_flumine_crash sorveglia_flusso_sessione
_make_session_mirror _order_mirror_loop applica_uscite_automatiche Db _uscita_su_eccezione main _al_segnale
installa_segnali_di_arresto""".split()
M["scalper_sess"] = ["run_session"]
S["tennis_svc"] = None    # tutto il file
S["tennis_run"] = """_desired_controls _stopping_controls _strategy_is_flat _hosted_not_flat _mark_waiting_controls
_clear_waiting_controls _reset_restart_episode _request_restart _rinvio_senza_forzare _disable_strategy
_scope_to_market _aggiorna_uscite session_posizioni_aperte _tennis_lifecycle_blockers
chiudi_alla_uscita_tennis _alert_stallo_tennis _tennis_blocker_uscita_stallo _sorveglia_flusso_tennis
_escala_stallo_tennis ContestoCaldo _caldo_attivo _mercato_con_posizioni _evento_con_posizioni _eventi_armati
_manuale _entro_il_tetto_al_build _allinea_follow_a_caldo _arma_a_caldo _cleanup_orphan_bot_controls
_pubblica_battito_attesa _stop_framework _announce_order_mode _partita_seguita _intervallo_bot_control
_avvia_sveglia_armamento _make_sink descrivi_esecuzione_bot _scrivi_attivita_modalita bot_control_worker
arresto_worker lifecycle_worker stall_worker follow_worker record_flag_worker _main""".split()
M["tennis_run"] = ["_instantiate_bot", "setup_and_run"]


def toplevel(chiave):
    with open(os.path.join(RADICE, FILE[chiave]), encoding="utf-8") as f:
        t = f.read()
    a = ast.parse(t)
    out = []
    for n in a.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append((n.name, n.lineno, n.end_lineno - n.lineno + 1))
    return len(t.splitlines()), out


def misura(elenca=False):
    tot = {"S": 0, "M": 0, "R": 0, "righe_file": 0}
    for k in FILE:
        nrighe, defs = toplevel(k)
        s_set = S.get(k)
        m_set = set(M.get(k, []))
        s = m = r = 0
        resto = []
        for nome, ln, n in defs:
            if s_set is None or nome in s_set:
                s += n
            elif nome in m_set:
                m += n
            else:
                r += n
                resto.append((n, nome, ln))
        nomi_def = {d[0] for d in defs}
        mancanti = [x for x in (s_set or []) if x not in nomi_def]
        mancanti += [x for x in m_set if x not in nomi_def]
        defs_tot = sum(n for _, _, n in defs)
        print("%-13s file=%5d righe  def/class=%5d  S=%5d  M=%5d  R=%5d  (fuori dalle def: %d)  mancanti=%s" % (
            k, nrighe, defs_tot, s, m, r, nrighe - defs_tot, mancanti))
        if elenca:
            for n, nome, ln in sorted(resto, reverse=True)[:10]:
                print("      R %-40s %4d righe @%d" % (nome, n, ln))
        tot["S"] += s
        tot["M"] += m
        tot["R"] += r
        tot["righe_file"] += nrighe
    print("TOTALE S=%d M=%d R=%d righe_file=%d" % (tot["S"], tot["M"], tot["R"], tot["righe_file"]))


def _pulito(righe, a, b):
    src = "\n".join(righe[a - 1:b])
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src + "\n").readline))
        src = tokenize.untokenize([t for t in toks if t.type != tokenize.COMMENT])
    except (tokenize.TokenError, IndentationError):
        pass
    return [" ".join(l.split()) for l in src.splitlines() if l.strip()]


def db_gemelle():
    """Somiglianza (difflib sulle righe, senza commenti) delle funzioni di accesso
    omonime nei moduli DB per-bot."""
    dbs = {"mike_db": "Betfair/mike/db.py", "omega_db": "Betfair/omega/omega_db.py",
           "safe_db": "Betfair/safe_strategy/bot_db.py",
           "tennis_db": "Betfair/stream/tennis_live/tennis_db.py"}
    dati = {}
    for k, p in dbs.items():
        with open(os.path.join(RADICE, p), encoding="utf-8") as f:
            t = f.read()
        a = ast.parse(t)
        righe = t.splitlines()
        dati[k] = {n.name: (n.lineno, n.end_lineno, _pulito(righe, n.lineno, n.end_lineno))
                   for n in a.body if isinstance(n, ast.FunctionDef)}
        print("%s: %d righe, %d funzioni" % (k, len(righe), len(dati[k])))
    nomi = {}
    for k, d in dati.items():
        for n in d:
            nomi.setdefault(n, []).append(k)
    for n, ks in sorted(nomi.items()):
        if len(ks) < 2:
            continue
        parti = ["%s:%d(%d)" % (k, dati[k][n][0], dati[k][n][1] - dati[k][n][0] + 1) for k in ks]
        rat = []
        for i in range(len(ks)):
            for j in range(i + 1, len(ks)):
                r = difflib.SequenceMatcher(None, dati[ks[i]][n][2], dati[ks[j]][n][2], autojunk=False).ratio()
                rat.append("%s~%s=%.2f" % (ks[i], ks[j], r))
        print("%-32s %s  %s" % (n, ",".join(parti), " ".join(rat)))


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "misura"
    if modo == "db":
        db_gemelle()
    else:
        misura(elenca=(modo == "elenca"))
