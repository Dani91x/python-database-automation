"""E1: somma le righe delle def/class di primo livello di Betfair/mike/service.py per gruppo di ruolo.
Solo lettura statica; i gruppi sono scritti qui a mano (elenco per nome). ASCII-only."""
import re
SRC = "Betfair/mike/service.py"
lines = open(SRC, encoding="utf-8").read().split("\n")
defs = [(i + 1, re.match(r"(?:async )?(?:def|class) (\w+)", l).group(1)) for i, l in enumerate(lines)
        if re.match(r"(?:async )?(?:def|class) \w+", l)]
size = {}
for (a, n), (b, _) in zip(defs, defs[1:] + [(len(lines) + 1, "")]):
    size[n] = b - a
G = {
 "D_scheletro": """mike_live_abilitato _LiveNonAbilitato _pretendi_live_abilitato _now _iso _Cache svuota_le_cache azzera_cache_di_processo
  _corpo_sostanziale _signature _scrivi_evento _persist _svuota_lotto _cadenza_pubblicazione _aggregates_cached _aggregates
  _scanner_stato _stato_scanner_dal_canale _scanner_age _params_for _log_throttled _episodio_dato_assente _cadenza_battito
  _config_warn _operating_day_start_ts _operating_day_key ferma_al_nuovo_avvio main _ciclo_persistente arresto_con_ordini _al_segnale
  _installa_segnali_di_arresto _AlzaSveglia _evento_seguito _pavimento_sveglia _su_sveglia_dal_canale _avvia_sveglia
  _client_scan_alza_sveglia statistiche_sveglia _dormi_o_sveglia _canale_feed_acceso avvia_client_scan azzera_canale_scan
  _canale_copre_tutte _feed_non_letto _avvisa_feed_non_letto _righe_del_feed statistiche_canale_scan _pubblica_evento _pubblica_stato
  _avvia_canale process_requests _richiesta_non_di_questa_partita _id_approvazione _approvazione_eseguita _chiave_gamba
  posti_occupati_per_modo partite_di_modalita_diversa _open_liability _locked_open_pnl _first_placed_at _ctx_legs_of""",
 "C_porta_ordini_e_ciclo_ordine": """execute_place _esito_del_rifiuto _esito_rifiuto_mercato _rifiutata _is_resting_leg _gia_appoggiata _porta_paper
  _attendi_terminale _nota_senza_runner _senza_runner _num_evento _segui_ordini_paper_su_runner _piazza_resting_paper _freno_gia_appoggiata
  _resting_e_chiusura _resting_in_attesa _freno_aperture_rest _rifiuto_non_di_mercato _ferma_aperture motivo_aperture_ferme _unisci_motivi
  _causa_aperture_ferme _aggiorna_aperture_ferme _freno_resting_paper _piazza_resting_live _aggiorna_riga_resting campo_ordine _num_ordine
  ordine_normalizzato ref_ordine_di_riga _ordine_della_riga _ordine_di _segui_resting_live _gambe_appoggiate_vive _classifica_ordine
  _rileggi_ordine_appoggiato _rileggi_per_bet_id _chiudi_gamba_scaduta _applica_esito_riapertura _registra_resti _registra_avvisi_esecuzione
  _esegui_annulli _sorveglia_posizione_di_conto _sorveglia_sospensione _selezione_copertura _sorveglia_mercato_copertura _sorveglia_gambe
  _sorveglia_senza_dati _mark_trade_cancelled _aggancia_riserve_orfane _reconcile_trades _reconcile_unknown _trade_ids_by_ref
  _trade_row_for_leg _trade_unknown_outcome _open_refs_by_event _mirror_is_aligned _gamba_dalla_riga _refs_di_mike _posizione_attesa
  _event_rows _trade_row _insert_trade_row _is_missing_column_error _stato_rest_riga_assente _esposizione_mike _books_ripiego_rest _RealMarket""",
 "F_regolamento_e_conto": """market_winner final_total_from_books market_voided settle_plan _settle_params _leggi_regolato_conto _applica_conto
  _settle_trades _retry_settle_rows _marca_righe_non_regolate scrivi_riga_utente_in_corso _riepilogo_conto _netto_su_selezione
  _verdetto_di_conto _segnale_conto_dal_canale installa_conto_canale avvia_conto_dal_canale _ContoNonLetto""",
 "E1_colla_di_Mike": """_run_event run_once _ctx_from_row _legs_from_json _row_from_ctx _request_approva_uscita _request_cancel _request_flatten
  _p_under35_calibrata _live_exit_override _punteggio_ingresso dossier_da_ritentare _retry_dossier _gambe_vive _firma_loss_exit_deciso
  _avvisa_copertura_fuori_prezzo""",
}
tot = {}
seen = set()
for g, names in G.items():
    for n in names.split():
        if n in size:
            tot[g] = tot.get(g, 0) + size[n]; seen.add(n)
        else:
            print("nome non trovato:", n)
resto = {n: s for n, s in size.items() if n not in seen}
print("def/class di primo livello:", len(size), "righe in def:", sum(size.values()), "file:", len(lines))
for g, v in tot.items():
    print(g, v)
print("non assegnate:", sum(resto.values()), sorted(resto.items(), key=lambda x: -x[1])[:15])
