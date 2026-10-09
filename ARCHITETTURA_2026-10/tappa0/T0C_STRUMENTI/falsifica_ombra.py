"""T0C - FALSIFICAZIONE DELL'OMBRA A LIVELLO DI REPLAY (H par. 4.3), rieseguibile.

Sul replay VERO di Mike (``certifica mike 35760084 --scenari base``, ~70 s a
giro) si muta il comportamento IN MEMORIA, uno alla volta (nessun file del
repository cambia: le mutazioni sono sostituzioni fatte in questo processo
prima di chiamare ``certifica.main``), e si lancia ``--ombra`` contro la
cassetta di riferimento (lo stesso comando senza mutazioni):

  identita            nessuna mutazione                              -> 0 divergenze
  soglia_un_tick      ``pre_green_ticks`` 2 -> 3 (uscita appoggiata un tick piu' su)
  importo_0_01        l'importo di ogni BANCA emessa da ``engine._place`` +0,01
  stake_0_01          il parametro ``stake`` 10.00 -> 10.01 (Mike lo porta a 10.00 da
                      solo: diverge il motivo "liquidita 8.02 < 10.01", non l'ordine)
  istante_1_ms        l'istante delle righe dello specchio +1 ms (``varianti_bot.ms_di``)
  decisione_tolta     la PRIMA decisione con un piazzamento torna senza azioni
  ok_invertito        la condizione ``engine.riaprira`` (il mercato riaprira') invertita
  colonna_db          ``insert_trade``: la colonna ``liability`` scritta come ``responsabilita``
  controllo_spento    i controlli K di consapevolezza (``verifica_consapevolezza``) spenti
  sigillo             un byte della cassetta di riferimento cambiato (senza replay)

Ognuna (tranne l'identita') DEVE uscire con exit code != 0 e divergenze al
livello atteso; l'identita' DEVE dare 0 divergenze.

Uso (dalla radice del repository; DURATA: ~70 s a giro, 8 giri, 2 in
parallelo = ~5-6 minuti):
    python ARCHITETTURA_2026-10/tappa0/T0C_STRUMENTI/falsifica_ombra.py tutte --riferimento CAS.jsonl --uscite DIR
    python ARCHITETTURA_2026-10/tappa0/T0C_STRUMENTI/falsifica_ombra.py una NOME --riferimento CAS.jsonl
ASCII-only.
"""
from __future__ import annotations

import dataclasses
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.getcwd())

COMANDO = ["mike", "35760084", "--scenari", "base"]

#: mutazione -> livelli che DEVONO divergere (almeno questi)
ATTESE = {
    "identita": [],
    "soglia_un_tick": ["ordine"],
    "importo_0_01": ["ordine", "riga_db"],
    "stake_0_01": ["decisione", "riga_db"],
    "istante_1_ms": ["ordine"],
    "decisione_tolta": ["decisione"],
    "ok_invertito": ["decisione"],
    "colonna_db": ["riga_db"],
    "controllo_spento": ["decisione", "referto"],
}


def _sostituisci_ovunque(vecchia, nuova):
    """Sostituisce una funzione in TUTTI i moduli caricati che la tengono."""
    for m in list(sys.modules.values()):
        d = getattr(m, "__dict__", None)
        if not isinstance(d, dict):
            continue
        for k, v in list(d.items()):
            if v is vecchia:
                setattr(m, k, nuova)


def applica(nome):
    from Betfair.mike import config as C
    from Betfair.mike import engine as E

    if nome == "identita":
        return
    if nome == "soglia_un_tick":
        assert C.DEFAULTS["pre_green_ticks"] == 2
        C.DEFAULTS["pre_green_ticks"] = 3
        C.PARAM_SPEC["pre_green_ticks"] = (3,) + tuple(C.PARAM_SPEC["pre_green_ticks"][1:])
        return
    if nome == "importo_0_01":
        # l'importo di OGNI banca che Mike emette +0,01 (``engine._place``: le
        # punte no, Mike le porta a multipli di 0,50 per difetto e 0,01 sparirebbe
        # dentro la strategia stessa: prova del 09/10 con ``stake`` 10.00 -> 10.01,
        # rossa solo su decisione/riga_db/referto, ordini identici)
        vera = E._place

        def _place(role, market, selection, side, price, size, *a, **k):
            if side == "lay":
                size = round(float(size) + 0.01, 2)
            return vera(role, market, selection, side, price, size, *a, **k)

        _sostituisci_ovunque(vera, _place)
        return
    if nome == "stake_0_01":
        assert C.DEFAULTS["stake"] == 10.0
        C.DEFAULTS["stake"] = 10.01
        C.PARAM_SPEC["stake"] = (10.01,) + tuple(C.PARAM_SPEC["stake"][1:])
        return
    if nome == "istante_1_ms":
        from Betfair.stream.backtest import varianti_bot as VB

        vero = VB.ms_di

        def ms_di(adesso):
            v = vero(adesso)
            return None if v is None else v + 1

        VB.ms_di = ms_di
        return
    if nome == "decisione_tolta":
        vera = E.decide
        stato = {"fatta": False}

        def decide(ctx, snap, params):
            d = vera(ctx, snap, params)
            if not stato["fatta"] and any(getattr(a, "kind", "") == "place" for a in d.actions):
                stato["fatta"] = True
                return dataclasses.replace(d, actions=[])
            return d

        _sostituisci_ovunque(vera, decide)
        return
    if nome == "ok_invertito":
        vera = E.riaprira

        def riaprira(bk):
            return not vera(bk)

        _sostituisci_ovunque(vera, riaprira)
        return
    if nome == "colonna_db":
        from Betfair.stream.backtest import banco_comune as BC

        init_vero = BC.DbMemoria.__init__

        def init(self, *a, **k):
            init_vero(self, *a, **k)
            classe = type(self)

            def insert_trade(trade):
                t = dict(trade)
                if "liability" in t:
                    t["responsabilita"] = t.pop("liability")
                return classe.insert_trade(self, t)

            self.__dict__["insert_trade"] = insert_trade

        BC.DbMemoria.__init__ = init
        return
    if nome == "controllo_spento":
        from Betfair.mike import certificazione as CERT

        CERT.verifica_consapevolezza = lambda *a, **k: []
        return
    raise SystemExit("mutazione sconosciuta: %s" % nome)


def una(nome, riferimento, cassetta=None):
    applica(nome)
    from Betfair.stream.backtest import certifica

    argv = COMANDO + ["--ombra", riferimento]
    if cassetta:
        argv += ["--cassetta", cassetta]
    return certifica.main(argv)


def _livelli_divergenti(testo):
    m = re.search(r"OMBRA: (\d+) divergenze su \S+ voci \(riferimento/nuova\) \| per livello: (.*)",
                  testo)
    if not m:
        return None, []
    livelli = [p.split()[0] for p in m.group(2).split(", ") if int(p.split()[1]) > 0]
    return int(m.group(1)), livelli


def tutte(riferimento, uscite, parallelo=2):
    os.makedirs(uscite, exist_ok=True)
    nomi = list(ATTESE)
    attivi = []
    esiti = {}
    coda = list(nomi)
    while coda or attivi:
        while coda and len(attivi) < parallelo:
            n = coda.pop(0)
            out = open(os.path.join(uscite, "falsifica_%s.txt" % n), "w", encoding="utf-8")
            p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "una", n,
                                  "--riferimento", riferimento], stdout=out,
                                 stderr=subprocess.STDOUT)
            attivi.append((n, p, out))
        n, p, out = attivi.pop(0)
        rc = p.wait()
        out.close()
        testo = open(os.path.join(uscite, "falsifica_%s.txt" % n), encoding="utf-8").read()
        esiti[n] = (rc, _livelli_divergenti(testo))
    # il sigillo: un byte della cassetta di riferimento cambiato
    with tempfile.TemporaryDirectory() as tmp:
        copia = os.path.join(tmp, "rif.jsonl")
        shutil.copyfile(riferimento, copia)
        with open(copia, "r+b") as fh:
            fh.seek(200)
            b = fh.read(1)
            fh.seek(200)
            fh.write(bytes([b[0] ^ 1]))
        from Betfair.stream.backtest import ombra as OMB

        es = OMB.confronta_file(copia, riferimento)
        esiti["sigillo"] = (0 if es.pulito else 1, (len(es.divergenze), ["sigillo"]
                                                    if es.sigillo_riferimento else []))
    ko = 0
    print("| mutazione | exit code | divergenze | livelli divergenti | attesi | esito |")
    print("|---|---|---|---|---|---|")
    for n, (rc, (tot, livelli)) in esiti.items():
        attesi = ATTESE.get(n, ["sigillo"])
        if n == "identita":
            ok = rc == 0 and tot == 0
        else:
            ok = rc != 0 and all(x in livelli for x in attesi)
        ko += 0 if ok else 1
        print("| %s | %s | %s | %s | %s | %s |" % (n, rc, tot, ", ".join(livelli) or "-",
                                                 ", ".join(attesi) or "nessuno",
                                                 "ATTESO" if ok else "NON ATTESO"))
    print("ESITO: %d prove, %d non come atteso" % (len(esiti), ko))
    return 1 if ko else 0


def main(argv):
    if len(argv) >= 2 and argv[1] == "una":
        nome = argv[2]
        rif = argv[argv.index("--riferimento") + 1]
        cas = argv[argv.index("--cassetta") + 1] if "--cassetta" in argv else None
        return una(nome, rif, cas)
    if len(argv) >= 2 and argv[1] == "tutte":
        rif = argv[argv.index("--riferimento") + 1]
        uscite = argv[argv.index("--uscite") + 1]
        return tutte(rif, uscite)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
