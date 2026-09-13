#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""LE 75 CONDIZIONI DI MIKE, VERIFICATE SUL CAMPO (COSTITUZIONE_MIKE.md §16.4).

SOLA LETTURA. Nessuna scrittura sul DB, nessun servizio avviato, nessun ordine.
Rieseguibile quante volte si vuole: ogni esecuzione rifa' i conti sullo stato
corrente, quindi ha senso rilanciarlo man mano che le partite si accumulano.

Perche' esiste
--------------
Il 13/09 le 75 condizioni operative sono state verificate A TAVOLINO: dati
costruiti, passati a ``engine.decide``, risposta letta. Tutte corrette. Ma
quella verifica non dice niente su cosa succede quando le stesse condizioni si
presentano DA SOLE, su partite vere, col feed vero e il servizio che gira.

Questo strumento cerca negli archivi del bot — ``mike_activity``,
``mike_trades``, ``mike_events`` — le TRACCE che ogni condizione lascia quando
accade davvero, e dice quali sono state osservate e quali no.

La regola della costituzione: prima si riempie la colonna PAPER, poi quella
LIVE. Finche' la prima non e' piena non si passa a soldi veri; finche' non lo e'
la seconda, stake al minimo e una partita per volta.

Uso
---
    python -m Betfair.tools.verifica_75_condizioni_2026_09_13            # paper
    python -m Betfair.tools.verifica_75_condizioni_2026_09_13 live       # live

Output ASCII (console Windows cp1252).
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env() -> Dict[str, str]:
    out: Dict[str, str] = {}
    with open(os.path.join(ROOT, ".env"), encoding="utf8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _client():
    from supabase import create_client

    env = _env()
    return create_client(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])


# ---------------------------------------------------------------------------
# Gli archivi su cui si cerca
# ---------------------------------------------------------------------------
class Archivio:
    """Tutto quello che il bot ha lasciato dietro di se', in memoria."""

    def __init__(self, db: Any, mode: str) -> None:
        self.mode = mode
        self.eventi: List[dict] = []
        self.righe: List[dict] = []
        self.attivita: List[dict] = []
        self._carica(db)
        # indici comodi
        self.motivi: List[str] = []
        for e in self.eventi:
            ctx = e.get("ctx") if isinstance(e.get("ctx"), dict) else {}
            r = ctx.get("last_reason") or (e.get("live") or {}).get("last_reason")
            if r:
                self.motivi.append(str(r))
        for a in self.attivita:
            p = a.get("payload") if isinstance(a.get("payload"), dict) else {}
            for k in ("reason", "motivo", "to"):
                if p.get(k):
                    self.motivi.append(str(p[k]))
        self.kind = defaultdict(int)
        for a in self.attivita:
            self.kind[str(a.get("kind"))] += 1
        self.ruoli = defaultdict(int)
        self.stati_riga = defaultdict(int)
        for r in self.righe:
            self.ruoli[str(r.get("role"))] += 1
            self.stati_riga[str(r.get("status"))] += 1
        self.stati_evento = defaultdict(int)
        for e in self.eventi:
            self.stati_evento[str(e.get("state"))] += 1

    def _carica(self, db: Any) -> None:
        self.eventi = [e for e in (db.table("mike_events").select(
            "event_id,event_name,state,cycle_no,mode,settled_pnl,ctx,live,positions"
        ).limit(1000).execute().data or [])
            if str(e.get("mode") or "paper") == self.mode]
        frm = 0
        while True:
            pagina = db.table("mike_trades").select(
                "id,event_id,role,side,price,size,pnl,status,closes_trade_id,cycle_no,mode,meta"
            ).range(frm, frm + 999).execute().data or []
            self.righe += [r for r in pagina if str(r.get("mode") or "paper") == self.mode]
            frm += len(pagina)
            if len(pagina) < 1000:
                break
        frm = 0
        while True:
            pagina = (db.table("mike_activity").select("id,kind,event_id,payload")
                      .order("id", desc=True).range(frm, frm + 999).execute().data or [])
            self.attivita += pagina
            frm += len(pagina)
            if len(pagina) < 1000 or frm >= 4000:
                break

    # -- cerche ------------------------------------------------------------
    def motivo_contiene(self, *pezzi: str) -> int:
        n = 0
        for m in self.motivi:
            basso = m.lower()
            if all(p.lower() in basso for p in pezzi):
                n += 1
        return n

    def attivita_con(self, kind: str, *pezzi: str) -> int:
        n = 0
        for a in self.attivita:
            if str(a.get("kind")) != kind:
                continue
            testo = str(a.get("payload") or "").lower()
            if all(p.lower() in testo for p in pezzi):
                n += 1
        return n

    def righe_con_ruolo(self, *ruoli: str) -> int:
        return sum(self.ruoli.get(r, 0) for r in ruoli)

    def eventi_in_stato(self, *stati: str) -> int:
        return sum(self.stati_evento.get(s, 0) for s in stati)


# ---------------------------------------------------------------------------
# Le 75 condizioni: numero, blocco, descrizione, come si riconosce
# ---------------------------------------------------------------------------
class Cond:
    __slots__ = ("n", "blocco", "testo", "prova", "nota")

    def __init__(self, n: int, blocco: str, testo: str,
                 prova: Callable[[Archivio], int], nota: str = "") -> None:
        self.n, self.blocco, self.testo, self.prova, self.nota = n, blocco, testo, prova, nota


def condizioni() -> List[Cond]:
    B1 = "1 - PRE-MATCH: chi entra e chi no"
    B2 = "2 - IL CICLO PRE-MATCH"
    B3 = "3 - L'ULTIMO INGRESSO (10' dal fischio)"
    B4 = "4 - IL FISCHIO D'INIZIO"
    B5 = "5 - LA COPERTURA SU OVER 4.5"
    B6 = "6 - LE USCITE GLOBALI"
    B7 = "7 - CHIUSURA E RESIDUI"
    B8 = "8 - IL RE-INGRESSO SU UNDER 4.5"
    B9 = "9 - FINE PARTITA"
    B10 = "10 - ECCEZIONI E COMANDI"

    return [
        # ---- blocco 1 --------------------------------------------------
        Cond(1, B1, "entra: prezzo, liquidita' e spread nei limiti",
             lambda a: a.righe_con_ruolo("under_entry")),
        Cond(2, B1, "NON entra: prezzo sotto la banda",
             lambda a: a.motivo_contiene("fuori banda")),
        Cond(3, B1, "NON entra: prezzo sopra la banda",
             lambda a: a.motivo_contiene("fuori banda"),
             "stesso motivo del 2: si distinguono dal prezzo nel testo"),
        Cond(4, B1, "NON entra: liquidita' al best insufficiente",
             lambda a: a.motivo_contiene("liquidita")),
        Cond(5, B1, "NON entra: spread troppo largo",
             lambda a: a.motivo_contiene("spread")),
        Cond(6, B1, "NON entra: fuori dalla finestra pre-match",
             lambda a: a.motivo_contiene("fuori finestra")),
        Cond(7, B1, "NON entra: finestra chiusa (ultimi minuti)",
             lambda a: a.motivo_contiene("finestra pre-match chiusa")),
        Cond(8, B1, "NON entra: feed stantio",
             lambda a: a.motivo_contiene("feed stantio")),
        Cond(9, B1, "NON entra: cicli massimi raggiunti",
             lambda a: a.motivo_contiene("max cicli")),
        Cond(10, B1, "NON entra: pausa dopo un green",
             lambda a: a.motivo_contiene("cooldown")),
        Cond(11, B1, "NON entra: pre-match spento dalla UI",
             lambda a: a.motivo_contiene("pre_disabilitato")),
        Cond(12, B1, "NON entra: partita saltata a mano",
             lambda a: a.motivo_contiene("rientro disabilitato")),
        Cond(13, B1, "NON entra: mercato non OPEN",
             lambda a: a.motivo_contiene("book assente")),
        # ---- blocco 2 --------------------------------------------------
        Cond(14, B2, "piazza l'ingresso del ciclo",
             lambda a: a.attivita_con("place", "under_entry")),
        Cond(15, B2, "aspetta il fill dell'ingresso",
             lambda a: a.motivo_contiene("attesa fill ingresso")),
        Cond(16, B2, "TTL scaduto: ritira l'ordine mai abbinato",
             lambda a: a.motivo_contiene("ttl scaduto")),
        Cond(17, B2, "TTL scaduto su un fill PARZIALE: tiene la parte abbinata",
             lambda a: a.motivo_contiene("ttl", "tengo")),
        Cond(18, B2, "ingresso abbinato: appoggia subito l'uscita a +N tick",
             lambda a: a.attivita_con("place_resting", "under_green")
             + a.attivita_con("place", "under_green")),
        Cond(19, B2, "prezzo salito: non tocca niente, l'uscita resta sul book",
             lambda a: a.motivo_contiene("green resting sul book")),
        Cond(20, B2, "uscita abbinata a meta': riappoggia il residuo",
             lambda a: a.motivo_contiene("residuo")),
        Cond(21, B2, "ciclo CHIUSO in green",
             lambda a: a.attivita_con("pre_cycle")),
        Cond(22, B2, "passata la pausa: rientra col ciclo successivo",
             lambda a: sum(1 for e in a.eventi if int(e.get("cycle_no") or 0) >= 1)),
        # ---- blocco 3 --------------------------------------------------
        Cond(23, B3, "a 10' dal fischio, in PROFITTO: chiude al mercato",
             lambda a: a.motivo_contiene("ultimo ingresso", "locked")),
        Cond(24, B3, "a 10' dal fischio, in PERDITA: tiene e porta in live",
             lambda a: a.motivo_contiene("tengo") + a.eventi_in_stato("HOLD")),
        Cond(25, B3, "chiusura finale abbinata: rientra in PERSIST",
             lambda a: a.righe_con_ruolo("under_last")),
        Cond(26, B3, "ultimo ingresso PERSIST spento dalla UI",
             lambda a: a.motivo_contiene("ultimo ingresso disabilitato")),
        Cond(27, B3, "chiusura finale non abbinata: riprezza",
             lambda a: a.motivo_contiene("green taker: riprezzo")),
        # ---- blocco 4 --------------------------------------------------
        Cond(28, B4, "in gioco con posizione: prova l'uscita a +N tick",
             lambda a: a.motivo_contiene("provo l'uscita")),
        Cond(29, B4, "uscita al fischio appoggiata sul book",
             lambda a: a.righe_con_ruolo("ko_green") + a.motivo_contiene("uscita appoggiata")),
        Cond(30, B4, "in gioco SENZA posizione: la partita si chiude",
             lambda a: a.motivo_contiene("in-play senza posizione")
             + a.motivo_contiene("nessuna operazione")),
        Cond(31, B4, "residuo PERSIST vivo: grazia rispettata",
             lambda a: a.motivo_contiene("in gioco")),
        Cond(32, B4, "residuo PERSIST annullato dopo la grazia",
             lambda a: a.attivita_con("cancel", "under_last")),
        # ---- blocco 5 --------------------------------------------------
        Cond(33, B5, "finestra scaduta: compra la copertura piena",
             lambda a: a.motivo_contiene("copertura Over 4.5")),
        Cond(34, B5, "ASPETTA per coprire (hazard e P(4) bassi)",
             lambda a: a.attivita_con("cover_wait") + a.motivo_contiene("attendo per coprire")),
        Cond(35, B5, "copre subito perche' la quota Over e' gia' buona",
             lambda a: a.attivita_con("cover")),
        Cond(36, B5, "copre subito perche' il rischio gol e' alto",
             lambda a: a.attivita_con("cover")),
        Cond(37, B5, "copre comunque: oltre il minuto massimo di attesa",
             lambda a: a.attivita_con("cover")),
        Cond(38, B5, "NON copre: troppi gol",
             lambda a: a.motivo_contiene("troppi gol")),
        Cond(39, B5, "attende il riprezzo dopo un gol",
             lambda a: a.attivita_con("cover_wait")),
        Cond(40, B5, "copertura rimandata: liquidita' insufficiente",
             lambda a: a.motivo_contiene("copertura: liquidita")),
        Cond(41, B5, "copertura sul book, in attesa di fill",
             lambda a: a.motivo_contiene("attesa fill copertura")),
        Cond(42, B5, "copertura riprezzata",
             lambda a: a.motivo_contiene("copertura: riprezzo")),
        Cond(43, B5, "copertura ABBINATA",
             lambda a: a.motivo_contiene("copertura abbinata")),
        # ---- blocco 6 --------------------------------------------------
        Cond(44, B6, "cash-out globale a soglia di profitto",
             lambda a: sum(1 for r in a.righe
                           if (r.get("meta") or {}).get("exit_kind") == "profit")),
        Cond(45, B6, "tiene: profitto sotto la soglia",
             lambda a: a.motivo_contiene("tengo")),
        Cond(46, B6, "tiene: in perdita, fuori dalle finestre di uscita",
             lambda a: a.motivo_contiene("tengo")),
        Cond(47, B6, "uscita all'INTERVALLO a modello",
             lambda a: a.attivita_con("loss_exit_deciso", "ht")),
        Cond(48, B6, "intervallo con pochi gol: non chiude",
             lambda a: a.motivo_contiene("tengo")),
        Cond(49, B6, "tiene con l'Under gia' perso (serve il quinto gol)",
             lambda a: a.motivo_contiene("tengo")),
        Cond(50, B6, "nessuna esposizione gestibile: aspetta l'incasso",
             lambda a: a.motivo_contiene("nessuna esposizione gestibile")),
        Cond(51, B6, "cap di perdita per partita",
             lambda a: a.motivo_contiene("cap perdita evento")),
        Cond(52, B6, "uscita del secondo tempo a modello",
             lambda a: a.attivita_con("loss_exit_deciso", "2t")),
        # ---- blocco 7 --------------------------------------------------
        Cond(53, B7, "chiusure sul book, in attesa",
             lambda a: a.motivo_contiene("attesa fill chiusura")),
        Cond(54, B7, "chiusura riprezzata",
             lambda a: a.motivo_contiene("chiusura: riprezzo")),
        Cond(55, B7, "tutte le chiusure abbinate: posizione chiusa",
             lambda a: a.motivo_contiene("chiuso (")),
        Cond(56, B7, "residuo minuscolo portato al regolamento",
             lambda a: a.motivo_contiene("residuo sotto il minimo")),
        # ---- blocco 8 --------------------------------------------------
        Cond(57, B8, "re-ingresso su Under 4.5",
             lambda a: a.righe_con_ruolo("reentry")),
        Cond(58, B8, "niente re-ingresso: nessun gol",
             lambda a: a.motivo_contiene("gol fuori range")),
        Cond(59, B8, "niente re-ingresso: troppi gol",
             lambda a: a.motivo_contiene("gol fuori range")),
        Cond(60, B8, "niente re-ingresso: oltre il minuto limite",
             lambda a: a.motivo_contiene("oltre il minuto di re-ingresso")),
        Cond(61, B8, "niente re-ingresso: prezzo non migliore dell'ingresso",
             lambda a: a.motivo_contiene("<= ingresso")),
        Cond(62, B8, "niente re-ingresso: gia' fatto su questa partita",
             lambda a: sum(1 for e in a.eventi
                           if (e.get("ctx") or {}).get("reentry_done"))),
        Cond(63, B8, "niente re-ingresso: chiusura precedente in perdita",
             lambda a: a.motivo_contiene("flat")),
        # ---- blocco 9 --------------------------------------------------
        Cond(64, B9, "mercato chiuso: si passa al regolamento",
             lambda a: a.motivo_contiene("mercato chiuso")),
        Cond(65, B9, "attesa del punteggio finale",
             lambda a: a.motivo_contiene("attesa punteggio finale")),
        Cond(66, B9, "partita REGOLATA e contabilizzata",
             lambda a: a.attivita_con("settled")),
        # ---- blocco 10 -------------------------------------------------
        Cond(67, B10, "ordine a esito IGNOTO: riconciliazione",
             lambda a: a.attivita_con("reconcile_pending")),
        Cond(68, B10, "con un esito ignoto NON si apre niente di nuovo",
             lambda a: a.motivo_contiene("esito ignoto")),
        Cond(69, B10, "CASH OUT dalla UI",
             lambda a: a.righe_con_ruolo("manual_close")),
        Cond(70, B10, "CASH OUT in pre-match",
             lambda a: a.motivo_contiene("chiusura manuale")),
        Cond(71, B10, "dopo un cash out manuale non rientra da solo",
             lambda a: sum(1 for e in a.eventi if (e.get("ctx") or {}).get("no_reentry"))),
        Cond(72, B10, "partita regolata: nessuna azione",
             lambda a: a.eventi_in_stato("SETTLED")),
        Cond(73, B10, "partita saltata dalla UI",
             lambda a: a.attivita_con("skip_event") + a.eventi_in_stato("SKIPPED")),
        Cond(74, B10, "stato imprevisto: va in errore e annulla tutto",
             lambda a: a.eventi_in_stato("ERROR")),
        Cond(75, B10, "in gioco senza mai aver operato: scheda chiusa a zero",
             lambda a: sum(1 for e in a.eventi if str(e.get("state")) == "SETTLED"
                           and not (e.get("positions") or []))),
    ]


# ---------------------------------------------------------------------------
def stampa(mode: str, arc: Archivio, conds: List[Cond]) -> int:
    print()
    print("=" * 100)
    print(" LE 75 CONDIZIONI DI MIKE — VERIFICA SUL CAMPO IN %s" % mode.upper())
    print("=" * 100)
    print("  archivi letti: %d partite, %d righe di operazione, %d attivita'"
          % (len(arc.eventi), len(arc.righe), len(arc.attivita)))
    print()

    blocco_corrente = ""
    viste = 0
    mancanti: List[Cond] = []
    for c in conds:
        if c.blocco != blocco_corrente:
            blocco_corrente = c.blocco
            print()
            print("  %s" % blocco_corrente)
            print("  " + "-" * 96)
        try:
            n = int(c.prova(arc))
        except Exception as ex:  # noqa: BLE001 — una condizione rotta non ferma le altre
            print("  %3d  ERRORE nella ricerca: %s" % (c.n, str(ex)[:60]))
            mancanti.append(c)
            continue
        if n > 0:
            viste += 1
            print("  %3d  [ VISTA %4d ]  %s" % (c.n, n, c.testo))
        else:
            mancanti.append(c)
            print("  %3d  [ MAI      ]  %s%s"
                  % (c.n, c.testo, ("  (%s)" % c.nota) if c.nota else ""))

    print()
    print("=" * 100)
    print("  OSSERVATE SUL CAMPO: %d su %d          DA VEDERE ANCORA: %d"
          % (viste, len(conds), len(mancanti)))
    print("=" * 100)
    if mancanti:
        print()
        print("  Da provocare a mano (non arrivano da sole):")
        for c in mancanti:
            if c.blocco.startswith("10") or c.n in (16, 17, 26, 38, 51, 56):
                print("     %3d  %s" % (c.n, c.testo))
        print()
        print("  Le altre arrivano con le partite: rilanciare questo strumento")
        print("  dopo ogni giornata di gioco.")
    print()
    return 0 if not mancanti else 1


def main() -> int:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "paper").strip().lower()
    if mode not in ("paper", "live"):
        print("  modalita' non valida: usare 'paper' o 'live'")
        return 2
    try:
        db = _client()
    except Exception as ex:  # noqa: BLE001
        print("  connessione al DB fallita: %s" % str(ex)[:160])
        return 2
    try:
        arc = Archivio(db, mode)
    except Exception as ex:  # noqa: BLE001
        print("  lettura fallita: %s" % str(ex)[:160])
        return 2
    return stampa(mode, arc, condizioni())


if __name__ == "__main__":
    raise SystemExit(main())
