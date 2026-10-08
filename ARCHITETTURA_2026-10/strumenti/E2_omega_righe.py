# -*- coding: utf-8 -*-
"""E2 - righe di Omega per ruolo (strategia / guscio / condiviso). Solo lettura dei sorgenti.
Uso: python ARCHITETTURA_2026-10/strumenti/E2_omega_righe.py
Le fasce sono un GIUDIZIO dell'autore (E2_OMEGA.md sez. 1.3), rieseguibile: cambia le liste e rilancia."""
import ast, io, os, sys
RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
def righe(p):
    with io.open(os.path.join(RADICE, p), encoding="utf-8", errors="replace") as f:
        return f.read().count("\n")
# 1) omega_service: fasce di righe (inclusive) -> (ruolo, descrizione)
FASCE = [
 (1, 40, "G", "docstring e import"), (41, 250, "G", "orologi, tetti di freschezza, _Cache, stato di processo"),
 (251, 848, "G", "cache, canale di scansione, sveglia, esiti dal canale"),
 (849, 1137, "G", "lettura dati live: riga del feed -> stato (cancelli di freschezza)"),
 (1138, 1396, "S", "catena dei lambda e tabelle empiriche/per minuto"),
 (1397, 1770, "S", "_model_select (v2), _v3_tarature/_v3_select (v3)"),
 (1771, 1879, "G", "_leg_market, mercato in attesa, log dedup"),
 (1880, 2094, "S", "scan_and_place_legs, _scan_event_legs (gambe, finestre, ordine dei cancelli)"),
 (2095, 2354, "G", "gambe fallite, ritenti, freni REST, catena"),
 (2355, 2427, "S", "_size_and_place (stake, cap di gamba/aperto)"),
 (2428, 2634, "S", "motore v1: estimate_minute, matches_remaining, scan_and_place"),
 (2635, 4970, "G", "conferma, _place_one, gate flumine, porta, poll, riconciliazione, chiuso dall'utente"),
 (4971, 5424, "G", "settle_open, risultati, refresh eventi"),
 (5425, 6315, "G", "operazioni manuali: process_manual, _manual_place, _manual_cashout"),
 (6316, 6411, "G", "chiudi_eventi_in_attesa e costanti green-up"),
 (6412, 6923, "S", "green-up v2: candidati, P(perdita), _greenup_decide, floor"),
 (6924, 7171, "G", "_greenup_send e flusso"),
 (7172, 7368, "S", "_greenup_one, process_auto_greenup (trigger)"),
 (7369, 7751, "M", "missioni: suggerimenti CS/scalp, process_missions"),
 (7752, 8936, "G", "cadenza, stats, avvio, fasi di gestione, run_once, main, canale"),
]
tot = {"S": 0, "G": 0, "M": 0}
print("omega_service.py", righe("Betfair/omega/omega_service.py"), "righe")
for a, b, r, d in FASCE:
    tot[r] += b - a + 1
    print("  %5d-%5d %4d %s %s" % (a, b, b - a + 1, r, d))
print("  TOTALE per ruolo:", tot, "somma", sum(tot.values()))
# 2) altri file: per nome di def/classe (ast), il resto = "fuori def"
SPEC = {
 "Betfair/omega/omega_proposte.py": ("S", {"_una_gamba","_punteggio_ingresso","_p_del_bancato","_nomi_del_mercato","_sostanza","_cambiamento_sostanziale","margine_attesa","_ingredienti_del_payload","esito_uscita_al_prezzo","cap_di_gamba_scattato","cap_globale_scattato","parametri_modello","modo_uscite","proposte_attive","firma_ancora_valida","_cap_param","_f","_fin"}),
 "Betfair/omega/omega_engine.py": ("S", {"select_lay_runner","dynamic_target","lay_size_from_target","liability_from_lay","apply_liability_cap","net_profit_if_win","mission_phase","scalp_market_types","pick_under_runner","minute_from_clock","is_in_entry_window","is_eligible","legs_remaining","greenup_automatico_attivo","cap_di_gamba_v3","moltiplicatori_rossi_v3","seleziona_v3","selezione_da_v3","ScoreRunner","Selection"}),
}
for p, (ruolo, nomi) in SPEC.items():
    t = ast.parse(io.open(os.path.join(RADICE, p), encoding="utf-8").read())
    s = 0; n = 0
    for nodo in t.body:
        if isinstance(nodo, (ast.FunctionDef, ast.ClassDef)):
            n += nodo.end_lineno - nodo.lineno + 1
            if nodo.name in nomi:
                s += nodo.end_lineno - nodo.lineno + 1
    tot_f = righe(p)
    print("%s: %d righe; def/classe di strategia %d; altre def/classe %d; fuori def (costanti, docstring, import) %d" % (p, tot_f, s, n - s, tot_f - n))
for p in ["omega_v3","omega_model","omega_empirical","omega_config","omega_db","omega_market","omega_advisor","omega_validate","porta_ordini","certificazione","liquidity_probe"]:
    print("Betfair/omega/%s.py %d" % (p, righe("Betfair/omega/%s.py" % p)))
