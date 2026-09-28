"""Falsificazione del CANTIERE B (28/09): ogni mutazione reintroduce un difetto
nel file VERO, il test nuovo DEVE diventare rosso; poi ripristino byte per byte
(sha256 verificato). NON interrompere: il ripristino e' nel finally.

Uso (dalla radice del worktree):  python AUDIT_2026-09-28/falsifica_cantiere_b.py
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST = "Betfair/stream/tests/test_frammenti_mercato_2026_09_28.py"
TEST_TCP = "Betfair/stream/tests/test_frammenti_tcp_2026_09_28.py"
FR = "Betfair/stream/frammenti_mercato.py"
AF = "Betfair/stream/auto_follow.py"
RU = "Betfair/stream/runner.py"

MUTAZIONI = [
    ("M1 strategia ordini senza lo stream condiviso (seconda connessione)", FR,
     '        "market_data_filter": recorder.market_data_filter,\n',
     '        # MUTAZIONE market_data_filter tolto\n'),
    ("M2 runner: LiveTradingStrategy col solo market_filter", RU,
     "                live_strategy = LiveTradingStrategy(\n"
     "                    **_FR.kwargs_stream_condiviso(recorder),",
     "                live_strategy = LiveTradingStrategy(  # MUTAZIONE\n"
     "                    market_filter=recorder.market_filter,"),
    ("M3 piano: i mercati esistenti non restano nel loro frammento", FR,
     "    tenuti: List[Set[str]] = [set(a) & vol for a in attuali]",
     "    tenuti: List[Set[str]] = [set() for a in attuali]  # MUTAZIONE"),
    ("M4 piano: frammento 0 lasciato vuoto", FR,
     "        tenuti[0] = set(attuali[0])             # mai vuoto: tiene quelli di prima",
     "        pass  # MUTAZIONE"),
    ("M5 frammento nuovo non agganciato alle strategie", FR,
     "                st.streams = list(st.streams) + [s]",
     "                pass  # MUTAZIONE"),
    ("M6 si risottoscrivono anche i frammenti che non cambiano", FR,
     "            if bersaglio == attuali[i]:\n                continue",
     "            if False:  # MUTAZIONE\n                continue"),
    ("M7 capacita' esaurita: si applica lo stesso", FR,
     "        if piano.fuori:\n            raise CapacitaInsufficiente(",
     "        if False:  # MUTAZIONE\n            raise CapacitaInsufficiente("),
    ("M8 rete giu': si chiudono i frammenti muti anche senza altri vivi", FR,
     "            if (not mai_autenticato and altri_vivi and len(fr) > 1",
     "            if (not mai_autenticato and len(fr) > 1  # MUTAZIONE"),
    ("M9 pausa dopo rifiuto ignorata", FR,
     "                and self._ora() - self._rifiuto_mono < PAUSA_RIFIUTO_S):\n"
     "            self.motivo_limite",
     "                and False):  # MUTAZIONE\n            self.motivo_limite"),
    ("M10 connectionsAvailable=0 perso (come bflw)", FR,
     "        if isinstance(disp, int) and not isinstance(disp, bool):",
     "        if disp:  # MUTAZIONE"),
    ("M11 riserva ignorata", FR,
     "        if disp is not None and disp <= self.riserva and aperti < self.max_conn:",
     "        if False:  # MUTAZIONE"),
    ("M12 frammento chiuso che si riconnette (retry infinito come @retry)", FR,
     "        while not self.chiuso:\n            try:\n                _RUN_MARKETSTREAM(self)",
     "        while True:  # MUTAZIONE\n            try:\n                _RUN_MARKETSTREAM(self)"),
    ("M13 rifiuto Betfair non riconosciuto", FR,
     "            if mai_autenticato and (errore in CODICI_RIFIUTO",
     "            if mai_autenticato and (False  # MUTAZIONE"),
    ("M14 auto-follow: persi non tolti dagli applicati", AF,
     "                        self._applicati -= persi",
     "                        pass  # MUTAZIONE"),
    ("M15 auto-follow: manutenzione frammenti non chiamata nel giro", AF,
     "        self._frammenti()\n        self._applica(ora)",
     "        pass  # MUTAZIONE\n        self._applica(ora)"),
    ("M16 auto-follow: partite fuori in silenzio", AF,
     "                self._segna_fuori(ev, info, \"capacita' esaurita: %s\" % esito.motivo)",
     "                pass  # MUTAZIONE"),
    ("M17 auto-follow: capacita' ridotta senza rientro", AF,
     "            if len(self.piano.mercati()) > self.piano.tetto:\n"
     "                self.rientra_nel_tetto()",
     "            if False:  # MUTAZIONE\n                self.rientra_nel_tetto()"),
    ("M18 runner: budget del catalogo sul tetto di UNA connessione", RU,
     "        cap = _capacita_mercati()",
     "        cap = int(HARD_MARKET_CAP)  # MUTAZIONE"),
    ("M19 runner: auto-follow col sottoscrittore di sempre (una connessione)", RU,
     "                          sottoscrittore=gestore, follow_db=_AF.FollowDb(), feed=_feed,",
     "                          follow_db=_AF.FollowDb(), feed=_feed,  # MUTAZIONE"),
    # --- punto 1 del coordinatore: soldi nel frammento 0 ---
    ("M20 frammento 0: i mercati con soldi non vanno davanti", FR,
     "    soldi = sorted(tutti & {str(m) for m in con_soldi})",
     "    soldi = []  # MUTAZIONE"),
    ("M21 runner: frammento 0 senza i mercati con soldi", RU,
     "    ids0 = _FR.primo_frammento(market_ids, manuali, gestore.per_conn, con_soldi)",
     "    ids0 = _FR.primo_frammento(market_ids, manuali, gestore.per_conn)  # MUTAZIONE"),
    ("M22 auto-follow: voci con soldi noti al runner non protette", AF,
     "            elif esterni and (v.mercati & esterni):",
     "            elif False:  # MUTAZIONE"),
    ("M23 auto-follow: sgancio senza ricordare le voci con ordini", AF,
     "            self._protetti_allo_sgancio = {m for k in self._protetti()",
     "            self._protetti_allo_sgancio = set() or {m for k in ()  # MUTAZIONE"),
    ("M24 runner: blotter precedente non letto alla fine del framework", RU,
     "                mercati_con_ordini_prec = _FR.mercati_con_ordini(framework)",
     "                pass  # MUTAZIONE"),
    # M25 (lettura dello specchio del runner) sostituita su master da X5: la
    # lettura ora e' ``db.mercati_con_soldi``, regola unica con il cantiere A
    ("M26 runner: soldi dichiarati DOPO il rientro nel tetto", RU,
     "                auto.imposta_con_soldi(con_soldi)\n                auto.rientra_nel_tetto()",
     "                auto.rientra_nel_tetto()\n                auto.imposta_con_soldi(con_soldi)  # MUTAZIONE"),
    ("M27 soldi oltre il frammento 0 in silenzio", RU,
     "    if c[\"oltre_frammento0\"]:\n        msg = (",
     "    if False:  # MUTAZIONE\n        msg = ("),
    # --- punto 3: concorrenza ---
    ("M28 chiusura: remove sul posto nella lista delle strategie", FR,
     "                st.streams = [x for x in lista if x is not s]",
     "                lista.remove(s)  # MUTAZIONE"),
    ("M29 chiusura: remove sul posto nella lista degli stream di flumine", FR,
     "            contenitore._streams = [x for x in interni if x is not s]",
     "            interni.remove(s)  # MUTAZIONE"),
    # --- punto 2: esecuzione vera su TCP ---
    ("M30 run del frammento = run di flumine con @retry infinito", FR,
     "                _RUN_MARKETSTREAM(self)\n                return",
     "                MarketStream.run(self)  # MUTAZIONE\n                return"),
    ("M31 listener che non misura la sua connessione", FR,
     "        try:\n            self._osserva(raw_data)",
     "        try:\n            pass  # MUTAZIONE self._osserva(raw_data)"),
]


DB = "Betfair/stream/db.py"
TEST_INCROCIO = "Betfair/stream/tests/test_frammenti_fine_evento_2026_09_28.py"
TEST_A = "Betfair/stream/tests/test_fine_evento_2026_09_28.py"

#: 28/09 sera, merge su master (cantiere A 7a83206): mutazioni dell'INCROCIO
MUTAZIONI_MERGE = [
    ("X1 frammento 0 coi manuali di tutte le partite (finite comprese)", RU,
     "            mercati_frammento0 = _frammento0(market_ids, mercati_manuali_da_sottoscrivere(session),",
     "            mercati_frammento0 = _frammento0(market_ids, session.all_market_ids(),  # MUTAZIONE"),
    ("X2 frammento in piu' rimasto vuoto NON chiuso", FR,
     "            if not bersaglio and i > 0:",
     "            if False and not bersaglio and i > 0:  # MUTAZIONE"),
    ("X3 gestore che apre connessioni su un framework fermo", FR,
     "        if not fr:\n            # nessun frammento vivo",
     "        if False:  # MUTAZIONE\n            # nessun frammento vivo"),
    ("X4 chiusura che lascia il frammento nella lista delle strategie", FR,
     "            if isinstance(lista, list) and s in lista:\n"
     "                st.streams = [x for x in lista if x is not s]",
     "            if False:  # MUTAZIONE\n"
     "                st.streams = [x for x in lista if x is not s]"),
    ("X5 una regola sola: regolati non esclusi (mercati_con_soldi)", DB,
     "        out |= {str(p.get(\"market_id\")) for p in\n"
     "                _posizioni_aperte_non_regolate(sb, getattr(pos, \"data\", None) or [])}",
     "        out |= {str(p.get(\"market_id\")) for p in (getattr(pos, \"data\", None) or [])  # MUTAZIONE\n"
     "                if esposizione_aperta(p)}"),
    ("X6 frammento 0: mercati manuali delle partite finite rimessi (A)", RU,
     "            market_ids = mercati_manuali_da_sottoscrivere(session)\n            con_soldi",
     "            market_ids = session.all_market_ids()  # MUTAZIONE\n            con_soldi"),
    ("X7 aggancia senza azzerare _inviato_ts (nota 3 di A)", AF,
     "            for mid in self._applicati:\n                self._inviato_ts[mid] = ora",
     "            for mid in ():  # MUTAZIONE\n                self._inviato_ts[mid] = ora"),
]


def _sha(p: str) -> str:
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main() -> int:
    env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_KEY="x",
               SUPABASE_SERVICE_ROLE_KEY="x")
    esiti = []
    solo_merge = "--solo-merge" in sys.argv
    elenco = MUTAZIONI_MERGE if solo_merge else MUTAZIONI + MUTAZIONI_MERGE
    # i test di A sempre: X7 (nota 3 di A) la coglie il suo test
    test = [TEST, TEST_TCP, TEST_INCROCIO, TEST_A]
    for nome, rel, vecchio, nuovo in elenco:
        path = os.path.join(RADICE, rel)
        with open(path, "rb") as fh:
            originale = fh.read()
        sha0 = _sha(path)
        testo = originale.decode("utf-8")
        if "\r\n" in testo:                 # file con fine riga CRLF
            vecchio = vecchio.replace("\n", "\r\n")
            nuovo = nuovo.replace("\n", "\r\n")
        n = testo.count(vecchio)
        if n != 1:
            esiti.append((nome, "NON APPLICABILE (%d occorrenze)" % n))
            continue
        try:
            with open(path, "wb") as fh:
                fh.write(testo.replace(vecchio, nuovo).encode("utf-8"))
            r = subprocess.run([sys.executable, "-m", "pytest", *test, "-q", "-p",
                                "no:cacheprovider", "-x", "--no-header"],
                               cwd=RADICE, env=env, capture_output=True, text=True,
                               timeout=600)
            coda = [x for x in r.stdout.splitlines() if x.strip()][-1:]
            primo = [x for x in r.stdout.splitlines() if x.startswith("FAILED")][:1]
            esiti.append((nome, ("ROSSA " if r.returncode != 0 else "VERDE (NON CATTURATA) ")
                          + " ".join(coda + primo)))
        finally:
            with open(path, "wb") as fh:
                fh.write(originale)
            assert _sha(path) == sha0, "RIPRISTINO FALLITO: " + rel
    for nome, e in esiti:
        print("%-72s %s" % (nome, e))
    rosse = sum(1 for _n, e in esiti if e.startswith("ROSSA"))
    print("\nROSSE %d/%d" % (rosse, len(esiti)))
    for rel in (FR, AF, RU, DB):
        with open(os.path.join(RADICE, rel), encoding="utf-8") as fh:
            assert "MUTAZIONE" not in fh.read(), rel
    print("ripristino verificato: nessuna MUTAZIONE nei file")
    return 0 if rosse == len(esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
