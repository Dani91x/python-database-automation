"""Falsificazione dei test nuovi (25/09, strada unica sul banco).

Per ogni rottura minima: si salva il file, si applica la mutazione, si lanciano
SOLO i test che la devono vedere, si RIPRISTINA dal contenuto salvato (mai git
checkout: memoria del 23/09) e si verifica l'impronta sha1 del ripristino.

    python AUDIT_2026-09-25/strada_unica/falsifica.py
"""
import hashlib
import os
import subprocess
import sys

T = "Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py"
MUTAZIONI = [
    ("M1 base del primo seq tolta", "Betfair/safe_strategy/porta_ordini.py",
     "        if self.seq_visto == 0 and not self._sopra:\n"
     "            self.seq_visto = seq - 1          # primo contatto: la base\n", "",
     [T + "::test_primo_seq_e_la_base_nessun_da_seq_su_flusso_contiguo",
      T + "::test_client_vero_su_wsbanco_ack_eventi_e_nessun_da_seq",
      T + "::test_tempesta_assente_col_motore_vero"]),
    ("M2 una richiesta da_seq alla volta tolta", "Betfair/safe_strategy/porta_ordini.py",
     "        if ws is None or self._da_seq_in_corso:\n", "        if ws is None:\n",
     [T + "::test_un_buco_una_sola_richiesta_finche_il_motore_non_risponde"]),
    ("M3 risposta da_seq ignorata", "Betfair/safe_strategy/porta_ordini.py",
     "        if t == \"da_seq\":\n            self._da_seq_in_corso = False\n"
     "            return self.memoria.chiudi_da_seq(d)\n", "",
     [T + "::test_da_seq_incompleto_riparte_da_fino_a_e_lo_conta"]),
    ("M4 FOK anche sotto il minimo (Safe canale)", "Betfair/safe_strategy/execution.py",
     "            time_in_force=(None if sotto_minimo else PO.FOK),\n",
     "            time_in_force=PO.FOK,\n",
     [T + "::test_safe_sotto_minimo_dal_canale_va_nel_place_and_trim"]),
    ("M5 cliente live del banco etichettato SIMULATED", "Betfair/stream/backtest/porta_banco.py",
     "    VENUE = SimpleNamespace(name=\"BANCO_LIVE\", value=\"BANCO_LIVE\")\n",
     "    VENUE = SimpleNamespace(name=\"SIMULATED\", value=\"SIMULATED\")\n",
     [T + "::test_banco_live_serve_live_col_cliente_live_e_paper_col_simulato",
      T + "::test_cliente_live_banco_delega_ma_non_e_simulato"]),
    ("M6 token del WsBanco sempre valido", "Betfair/stream/backtest/porta_banco.py",
     "        ws = WsBanco(self, attore, token_ok=(tok == TOKEN_BANCO))\n",
     "        ws = WsBanco(self, attore, token_ok=True)\n",
     [T + "::test_token_sbagliato_rifiutato_nessun_ordine"]),
    ("M7 prezzo fuori dalla chiave di parita'", "Betfair/stream/backtest/trasporto.py",
     "            o.get(\"side\"), o.get(\"price\"), o.get(\"size\"), o.get(\"fok\"))\n",
     "            o.get(\"side\"), o.get(\"size\"), o.get(\"fok\"))\n",
     [T + "::test_parita_rotta_da_prezzo_esito_o_rest_sul_canale"]),
    ("M8 interruttore non ripristinato", "Betfair/stream/backtest/trasporto.py",
     "            if env_prima is None:\n                os.environ.pop(nome_env, None)\n",
     "            if env_prima is None:\n                pass\n",
     [T + "::test_contesto_accende_e_rimette_l_interruttore"]),
    ("M9 ordini del canale non adottati", "Betfair/stream/backtest/trasporto.py",
     "        ordini.setdefault(cor, o)\n", "        pass\n",
     [T + "::test_ordini_del_canale_adottati_nella_vista_di_conto"]),
    ("M10 specchio senza 'sporco' dopo il comando", "Betfair/stream/backtest/porta_banco.py",
     "        self._sporco = True                # dopo il comando possono esserci ordini nuovi\n",
     "",
     ["Betfair/stream/tests/test_porta_banco_f4_2026_09_24.py",
      T + "::test_ordini_del_canale_adottati_nella_vista_di_conto"]),
]


def sha(t: str) -> str:
    return hashlib.sha1(t.encode("utf-8")).hexdigest()[:12]


def main() -> int:
    env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x",
               SUPABASE_KEY="x")
    sopravvissute = 0
    for nome, f, vecchio, nuovo, test in MUTAZIONI:
        orig = open(f, encoding="utf-8").read()
        if vecchio not in orig:
            print("?? %s: testo da mutare NON trovato in %s" % (nome, f))
            sopravvissute += 1
            continue
        try:
            open(f, "w", encoding="utf-8").write(orig.replace(vecchio, nuovo, 1))
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p",
                                "no:cacheprovider", *test], env=env, capture_output=True,
                               text=True, timeout=600)
            ultima = (r.stdout.strip().splitlines() or ["?"])[-1]
        finally:
            open(f, "w", encoding="utf-8").write(orig)
        ripristino = sha(open(f, encoding="utf-8").read()) == sha(orig)
        rosso = r.returncode != 0
        if not rosso:
            sopravvissute += 1
        print("%s %-46s -> %s | ripristino %s (%s)" % (
            "ROSSO " if rosso else "VERDE!", nome, ultima,
            "OK" if ripristino else "KO", sha(orig)))
    print("mutazioni sopravvissute: %d su %d" % (sopravvissute, len(MUTAZIONI)))
    return 1 if sopravvissute else 0


if __name__ == "__main__":
    sys.exit(main())
