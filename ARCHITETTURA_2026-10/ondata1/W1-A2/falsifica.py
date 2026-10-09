"""Falsificazione dei test di W1-A2: ogni mutazione rompe il codice, i test indicati DEVONO diventare rossi.

Dalla radice del repository:

    python ARCHITETTURA_2026-10/ondata1/W1-A2/falsifica.py [M1 M2 ...]

Per ogni mutazione: sha256 del file, sostituzione ESATTA (deve trovare il testo una
volta sola), pytest sui test indicati (``-x``: basta il primo rosso), ripristino del
testo originale e verifica che lo sha256 sia tornato identico. Una riga JSON per
mutazione: rossi/verdi, esito, sha prima e dopo. Nessun file resta mutato: il
ripristino e' in un ``finally``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
N = "Betfair/nucleo/betfair/"
T = N + "tests/"

#: (id, file, testo, sostituto, test, cosa rompe)
MUTAZIONI = [
    ("M1", N + "ladder.py",
     "        for s in sorted(selezioni, key=lambda x: x[\"selection_id\"])\n",
     "        for s in selezioni\n",
     [T + "test_a2_ladder_parita.py::test_firma_indipendente_dall_ordine_dei_runner",
      T + "test_a2_ladder_parita.py::test_payload_e_firma_identici_su_ogni_book"],
     "firma senza ordinamento per selection_id (A par. 5 punto 6a)"),
    ("M1b", N + "ladder.py",
     "        for s in sorted(selezioni, key=lambda x: x[\"selection_id\"])\n",
     "        for s in selezioni\n",
     [T + "test_a2_ladder_parita.py::test_payload_e_firma_identici_su_ogni_book[35760084]"],
     "come M1, ma SOLO il confronto su ogni book della registrazione vera"),
    ("M2", N + "ladder.py",
     "    if profilo.chiusura == \"marca_ultimo\":\n",
     "    if False:\n",
     [T + "test_a2_ladder.py::test_chiusura_come_oggi_per_sport",
      T + "test_a2_ladder.py::test_calcio_senza_book_prima_della_chiusura_non_pubblica"],
     "chiusura del calcio come quella del tennis"),
    ("M3", N + "ladder.py",
     "            sig, payload = self._versioni.versione(mid, libro, _costruisci)\n",
     "            payload, sig = _costruisci()\n",
     [T + "test_a2_ladder.py::test_chiusura_come_oggi_per_sport"],
     "updated_ms non piu' strettamente crescente (versione di StatoLadder saltata)"),
    ("M4", N + "ladder.py",
     "            dovuto = ora if voce.ultima_pub is None else voce.ultima_pub + self._intervallo\n",
     "            dovuto = ora\n",
     [T + "test_a2_ladder.py::test_coalescenza_20ms_vince_l_ultimo_book"],
     "nessuna coalescenza a 20 ms"),
    ("M5", N + "ladder.py",
     "            voce.firma_db = sig\n",
     "            pass\n",
     [T + "test_a2_ladder.py::test_db_nel_suo_thread_write_on_change_e_ritento_su_errore"],
     "DB senza write-on-change"),
    ("M6", N + "ladder.py",
     "                for mid, voce in self._mercati.items():\n                    voce.firma_canale = None\n",
     "                for mid, voce in []:\n                    voce.firma_canale = None\n",
     [T + "test_a2_ladder.py::test_canale_senza_client_poi_client_nuovo_riceve_tutto"],
     "client nuovo del canale che non riceve lo stato"),
    ("M7", N + "ladder.py",
     "    back_pct = round(back_sz / totale * 100.0, 1)\n",
     "    back_pct = round(back_sz / totale * 100.0, 2)\n",
     [T + "test_a2_ladder_parita.py::test_casi_limite_identici_alle_due_copie_di_oggi",
      T + "test_a2_ladder_parita.py::test_payload_e_firma_identici_su_ogni_book"],
     "WOM arrotondato diversamente"),
    ("M7b", N + "ladder.py",
     "    back_pct = round(back_sz / totale * 100.0, 1)\n",
     "    back_pct = round(back_sz / totale * 100.0, 2)\n",
     [T + "test_a2_ladder_parita.py::test_payload_e_firma_identici_su_ogni_book[35760084]"],
     "come M7, ma SOLO il confronto su ogni book della registrazione vera"),
    ("M7c", N + "ladder.py",
     "        \"status\": libro.get(\"status\"),\n        \"ladder\": payload,\n",
     "        \"ladder\": payload,\n        \"status\": libro.get(\"status\"),\n",
     [T + "test_a2_ladder.py::test_meta_none_fuori_ladder_e_snapshot_stesso_schema",
      T + "test_a2_ladder_parita.py::test_sequenza_del_topic_identica_al_worker_di_oggi"],
     "riga con le chiavi in un altro ordine (json.dumps diverso)"),
    ("M8", N + "flusso_ordini_conto.py",
     "        ripresa = bool(ic and clk) and not self._forza_immagine\n",
     "        ripresa = False\n",
     [T + "test_a2_flusso_ordini_conto.py::test_connessione_vera_sottoscrive_senza_filtro_e_riprende_con_clk"],
     "ordini: ripresa senza initialClk/clk (A par. 5 punto 6b)"),
    ("M9", N + "flusso_ordini_conto.py",
     "            customer_strategy_refs=None,\n",
     "            customer_strategy_refs=[\"runner\"],\n",
     [T + "test_a2_flusso_ordini_conto.py::test_filtro_senza_strategia_con_posizione_complessiva",
      T + "test_a2_flusso_ordini_conto.py::test_connessione_vera_sottoscrive_senza_filtro_e_riprende_con_clk"],
     "stream ordini filtrato per strategia (il difetto da togliere)"),
    ("M10", N + "flusso_ordini_conto.py",
     "        prezzo_medio=float(uo.average_price_matched) if uo.average_price_matched is not None else None,\n",
     "        prezzo_medio=float(uo.average_price_matched or 0.0),\n",
     [T + "test_a2_flusso_ordini_conto.py::test_ordine_del_sito_senza_riferimenti_e_avp_assente"],
     "prezzo medio assente scritto 0 (PSB 7 n.21: zero al posto di assente)"),
    ("M11", N + "flusso_ordini_conto.py",
     "                    if o.market_id == mid and o.stato == \"EXECUTABLE\" and bet_id not in visti:\n",
     "                    if False:\n",
     [T + "test_a2_flusso_ordini_conto.py::test_immagine_piena_dopo_caduta_segnala_gli_eseguiti_mentre_era_giu"],
     "ordini conclusi a connessione giu' non segnalati"),
    ("M12", N + "flusso_ordini_conto.py",
     "        if codice == CODICE_CLK_NON_VALIDO or self._listener.errore_elaborazione:\n",
     "        if False:\n",
     [T + "test_a2_flusso_ordini_conto.py::test_invalid_clock_riparte_da_immagine_piena",
      T + "test_a2_flusso_ordini_conto.py::test_messaggio_malformato_si_riconnette_da_immagine_piena"],
     "ripresa con un clk non valido o gia' avanzato"),
    ("M13", N + "flusso_ordini_conto.py",
     "                self._sessione.rinnova_se_serve()\n",
     "                pass\n",
     [T + "test_a2_flusso_ordini_conto.py::test_sessione_scaduta_rinnova_e_riprova"],
     "sessione scaduta non rinnovata"),
    ("M14", N + "flusso_ordini_conto.py",
     "            \"stato\": (\"assente\" if not avviato else \"vivo\" if verdetto[\"vivo\"] else \"muto\"),\n",
     "            \"stato\": (\"assente\" if not avviato else \"vivo\"),\n",
     [T + "test_a2_flusso_ordini_conto.py::test_vivo_poi_muto_poi_latente_503"],
     "ordini: muto mai dichiarato (PSB 7 n.20)"),
    ("M15", N + "flusso.py",
     "            ripresa = bool(li.initial_clk and li.clk) and not self._forza_immagine\n",
     "            ripresa = False\n",
     [T + "test_a2_flusso.py::test_ripresa_con_initial_clk_e_clk_dopo_la_caduta"],
     "prezzi: ripresa senza initialClk/clk (A par. 5 punto 6b)"),
    ("M16", N + "flusso.py",
     "                self._forza_immagine = True\n                return False\n",
     "                return False\n",
     [T + "test_a2_flusso.py::test_cambio_di_mercati_a_connessione_giu_riparte_da_immagine"],
     "ripresa con criteri cambiati"),
    ("M17", N + "flusso.py",
     "            disp = d.get(\"connectionsAvailable\")\n            if isinstance(disp, int) and not isinstance(disp, bool):\n                self.connessioni_disponibili = disp\n                self.connessioni_lette_mono",
     "            disp = None\n            if isinstance(disp, int) and not isinstance(disp, bool):\n                self.connessioni_disponibili = disp\n                self.connessioni_lette_mono",
     [T + "test_a2_flusso_piano.py::test_budget_identico_a_gestore_frammenti",
      T + "test_a2_flusso.py::test_riserva_e_connections_available"],
     "connectionsAvailable spento (A par. 5 punto 6d)"),
    ("M18", N + "flusso.py",
     "        self.per_conn = max(1, min(int(profilo.mercati_per_connessione), int(limite_mercati)))\n",
     "        self.per_conn = max(1, int(profilo.mercati_per_connessione))\n",
     [T + "test_a2_flusso.py::test_mai_oltre_200_per_sottoscrizione_anche_se_il_profilo_lo_chiede"],
     "oltre 200 mercati per sottoscrizione"),
    ("M19", N + "flusso.py",
     "    tenuti: List[Set[str]] = [set(a) & vol for a in attuali]\n    presenti",
     "    tenuti: List[Set[str]] = [set() for a in attuali]\n    presenti",
     [T + "test_a2_flusso_piano.py::test_piano_identico_a_frammenti_mercato_su_griglie"],
     "un mercato cambia connessione (piano non stabile)"),
    ("M20", N + "flusso.py",
     "            self._sottoscrivi(s, ripresa=False)\n            return True\n",
     "            self.mercati = set(mercati) - set(self.listener.serviti)\n            self._sottoscrivi(s, ripresa=False)\n            return True\n",
     [T + "test_a2_flusso.py::test_suddivisione_180_e_risottoscrizione_solo_della_connessione_che_cambia"],
     "sottoscrizione con il solo pezzo nuovo (non sostitutiva)"),
    ("M21", N + "flusso.py",
     "                if not mai and altri_vivi and len(conn) > 1 and ora - ultimo > MUTO_S:\n",
     "                if False:\n",
     [T + "test_a2_flusso.py::test_manutenzione_chiude_la_connessione_muta_e_ripiazza"],
     "connessione muta mai chiusa"),
    ("M22", N + "flusso.py",
     "                return \"vivo\" if (self._verdetto(c)[\"vivo\"] and mid in c.listener.serviti) else \"muto\"\n",
     "                return \"vivo\" if self._verdetto(c)[\"vivo\"] else \"muto\"\n",
     [T + "test_a2_flusso.py::test_salute_vivo_muto_assente_e_503"],
     "mercato senza book dichiarato vivo (PSB 7 n.20)"),
    ("M23", N + "flusso.py",
     "        if codice in CODICI_RIFIUTO and not li.autenticato_una_volta:\n",
     "        if False:\n",
     [T + "test_a2_flusso.py::test_rifiuto_di_betfair_chiude_mette_in_pausa_e_non_ritenta"],
     "rifiuto di Betfair ritentato senza pausa"),
    ("M24", N + "profili.py",
     "        conflate_ms=1000,               # safe_strategy/stream.py:67 (_CONFLATE_MS)\n",
     "        conflate_ms=0,                  # safe_strategy/stream.py:67 (_CONFLATE_MS)\n",
     [T + "test_a2_profili.py::test_profili_uguali_ai_valori_di_oggi"],
     "scanner a conflate 0 (U-01: decisione dell'utente)"),
    ("M25", N + "profili.py",
     "            base = int(float(raw))\n",
     "            base = int(raw)\n",
     [T + "test_a2_profili.py::test_profili_uguali_ai_valori_di_oggi"],
     "tetto tennis letto in un altro modo"),
]


def _sha(percorso: str) -> str:
    with open(percorso, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def esegui(m) -> dict:
    mid, rel, testo, sost, test, cosa = m
    percorso = os.path.join(RADICE, rel)
    sha0 = _sha(percorso)
    with open(percorso, "r", encoding="utf-8") as fh:
        originale = fh.read()
    assert originale.count(testo) == 1, "%s: testo trovato %d volte" % (mid, originale.count(testo))
    inizio = time.perf_counter()
    try:
        with open(percorso, "w", encoding="utf-8") as fh:
            fh.write(originale.replace(testo, sost))
        esito = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider",
                                *test], capture_output=True, text=True, cwd=RADICE, timeout=900)
    finally:
        with open(percorso, "w", encoding="utf-8") as fh:
            fh.write(originale)
    sha1 = _sha(percorso)
    coda = esito.stdout.strip().splitlines()[-1] if esito.stdout.strip() else esito.stderr[-200:]
    rossi = int(re.search(r"(\d+) failed", coda).group(1)) if "failed" in coda else 0
    return {"id": mid, "file": rel, "cosa": cosa, "rossi": rossi, "esito": coda,
            "rosso": esito.returncode != 0 and rossi > 0, "sha256_prima": sha0,
            "sha256_dopo": sha1, "ripristinato": sha0 == sha1,
            "secondi": round(time.perf_counter() - inizio, 1)}


def main(scelte: list) -> int:
    tutte = [m for m in MUTAZIONI if not scelte or m[0] in scelte]
    rossi = 0
    for m in tutte:
        r = esegui(m)
        rossi += int(r["rosso"])
        print(json.dumps(r, sort_keys=True), flush=True)
    print(json.dumps({"mutazioni": len(tutte), "rosse": rossi}), flush=True)
    return 0 if rossi == len(tutte) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
