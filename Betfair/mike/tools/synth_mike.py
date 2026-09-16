"""REGISTRAZIONI SINTETICHE PER MIKE — formato NATIVO Betfair, dichiarate finte.

A che cosa servono, e perche' esistono. Il replay certifica la condotta di Mike
sulle partite REGISTRATE: quelle raccontano pero' solo cio' che e' successo.
Due condizioni che le registrazioni vere non contengono —

  * il **re-ingresso** (§3 Fase 6, controlli H1 e H2): vuole una partita in cui
    l'uscita al fischio si abbina INTERA (chiusura in profitto) e poi arriva UN
    gol nel primo tempo. Caso `reingresso`;
  * un ordine che si abbina a un prezzo **MIGLIORE** di quello chiesto
    (controllo K1, difetto 3 del 15/09: `avg_price` al posto di
    `avg_price_matched`). Caso `prezzo_migliore`.

e «un controllo che non ha un caso non e' una garanzia» (§6.7 del processo).
Quindi la condizione si COSTRUISCE, in un file che parla la lingua di Betfair.

COME SONO FATTE — nessun formato «curato»:
  * i `marketDefinition` sono COPIATI da una registrazione VERA (35760084):
    stessi campi, stessi `selectionId`, stessi `sortPriority`. Cosi' lo scanner
    vero, `feed.py` e flumine leggono esattamente quello che leggono sempre;
  * i messaggi sono `mcm` con `rc` = `atb`/`atl`/`trd` e `ltp`/`tv`, `trd`
    CUMULATIVO come lo manda Betfair (e' cio' che flumine consuma per abbinare
    gli ordini appoggiati);
  * il sidecar dei punteggi e' un record IPS VERO della stessa registrazione,
    con SOLO minuto e gol riscritti: `Scanner.apply_score_state` e
    `parse_score_dict` sono le funzioni di produzione e devono trovare le
    chiavi che trovano sempre (difetto 27 del catalogo: un finto che parla una
    lingua diversa dal vero certifica il difetto).

DICHIARAZIONE OBBLIGATORIA: la cartella si chiama `_synth_mike_<caso>` e
`Betfair/stream/backtest/certifica.py` stampa in testa al referto che la
registrazione e' **SINTETICA**. Non conta come partita reale, mai, in nessun
conteggio: serve solo a far parlare un controllo che sui dati veri tace.

Uso:
    python -m Betfair.mike.tools.synth_mike --caso reingresso
    python -m Betfair.mike.tools.synth_mike --caso tutti
    python -m Betfair.stream.backtest.certifica mike _synth_mike_reingresso --scenari base
    python -m Betfair.stream.backtest.certifica mike _synth_mike_prezzo_migliore --scenari base

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from typing import Any, Dict, List, Optional, Tuple

# la registrazione VERA da cui si copiano definizioni di mercato e record IPS
SORGENTE = "35760084"
TIPI = ("MATCH_ODDS", "OVER_UNDER_35", "OVER_UNDER_45")

# un passo di 5 secondi: piu' fitto non aggiunge niente (Mike decide ogni
# secondo, le sue finestre sono di minuti) e moltiplica per cinque il file.
PASSO_MS = 5_000


def _data_dir() -> str:
    from ...stream.config_stream import DATA_DIR

    return DATA_DIR


# ---------------------------------------------------------------------------
# i pezzi VERI da cui si parte
# ---------------------------------------------------------------------------
def modelli_di_mercato(data_dir: str, event_id: str = SORGENTE) -> Dict[str, Dict[str, Any]]:
    """Il PRIMO `marketDefinition` di ogni tipo che serve a Mike, dal raw vero."""
    raw = os.path.join(data_dir, str(event_id), f"{event_id}.raw.jsonl")
    trovati: Dict[str, Dict[str, Any]] = {}
    with open(raw, "r", encoding="utf-8") as fh:
        for riga in fh:
            if len(trovati) == len(TIPI):
                break
            try:
                msg = json.loads(riga)
            except ValueError:
                continue
            for mc in msg.get("mc") or []:
                md = mc.get("marketDefinition")
                if not md:
                    continue
                tipo = str(md.get("marketType") or "")
                if tipo in TIPI and tipo not in trovati:
                    trovati[tipo] = {"market_id": str(mc.get("id")),
                                     "market_definition": copy.deepcopy(md)}
    mancanti = [t for t in TIPI if t not in trovati]
    if mancanti:
        raise RuntimeError(f"tipi di mercato non trovati in {raw}: {mancanti}")
    return trovati


def modello_punteggio(data_dir: str, event_id: str = SORGENTE) -> Dict[str, Any]:
    """Il primo record IPS **di fonte BETFAIR** con minuto, dal sidecar vero.

    Il sidecar contiene DUE fonti: `api_football` (poche righe, formato fixture)
    e `betfair` (l'in-play vero, la stragrande maggioranza). Il parser di
    produzione che il banco usa e' `stream.scores.betfair_inplay.
    parse_score_dict`, che legge ``timeElapsed`` e ``score.home.score``: su un
    payload api_football torna minuto e gol NULLI. Prendere il modello dalla
    fonte sbagliata darebbe una registrazione sintetica senza punteggio — cioe'
    esattamente il difetto 27 del catalogo (un finto che parla una lingua
    diversa dal vero), misurato al primo giro il 16/09 sera.
    """
    path = os.path.join(data_dir, str(event_id), f"{event_id}.scores.jsonl")
    with open(path, "r", encoding="utf-8") as fh:
        for riga in fh:
            try:
                rec = json.loads(riga)
            except ValueError:
                continue
            if (str(rec.get("source") or "") == "betfair"
                    and rec.get("minute") is not None
                    and isinstance(rec.get("payload"), dict)):
                return copy.deepcopy(rec)
    raise RuntimeError(f"nessun record IPS betfair con minuto in {path}")


def _sel_per_priorita(md: Dict[str, Any]) -> Dict[int, int]:
    """{sortPriority: selectionId} dalla definizione vera."""
    return {int(r.get("sortPriority") or 0): int(r["id"])
            for r in (md.get("runners") or []) if r.get("id") is not None}


# ---------------------------------------------------------------------------
# la scrittura dei messaggi
# ---------------------------------------------------------------------------
def _md(modello: Dict[str, Any], *, event_id: str, ko_ms: int, status: str,
        inplay: bool, bet_delay: int, versione: int,
        vincitori: Optional[Dict[int, str]] = None) -> Dict[str, Any]:
    """Una `marketDefinition` come quella vera, con lo stato del momento."""
    md = copy.deepcopy(modello)
    iso = _iso(ko_ms)
    md.update({"eventId": str(event_id), "marketTime": iso, "suspendTime": iso,
               "openDate": iso, "status": status, "inPlay": bool(inplay),
               "betDelay": int(bet_delay), "version": int(versione)})
    for r in md.get("runners") or []:
        r["status"] = (vincitori or {}).get(int(r.get("id") or 0), "ACTIVE")
    return md


def _iso(ms: int) -> str:
    from datetime import datetime, timezone

    return (datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%S.000Z"))


class Costruttore:
    """Costruisce lo stream `mcm` di UNA partita sintetica."""

    def __init__(self, event_id: str, modelli: Dict[str, Dict[str, Any]],
                 t0_ms: int, ko_ms: int) -> None:
        self.event_id = str(event_id)
        self.modelli = modelli
        self.t0 = int(t0_ms)
        self.ko = int(ko_ms)
        self.righe: List[str] = []
        self.versione = 1
        self._cum: Dict[Tuple[str, int, float], float] = {}
        self._primo = True

    def sel(self, tipo: str, priorita: int) -> int:
        return _sel_per_priorita(self.modelli[tipo]["market_definition"])[priorita]

    def tick(self, pt_ms: int, *, status: str = "OPEN", inplay: bool = False,
             bet_delay: int = 0, prezzi: Optional[Dict[str, Dict[int, Tuple[float, float, float, float]]]] = None,
             scambiato: Optional[Dict[str, Dict[int, Tuple[float, float]]]] = None,
             vincitori: Optional[Dict[str, Dict[int, str]]] = None,
             con_definizione: bool = False) -> None:
        """UN messaggio `mcm` con tutti e tre i mercati.

        `prezzi[tipo][priorita] = (back, back_size, lay, lay_size)`;
        `scambiato[tipo][priorita] = (prezzo, volume NUOVO)` -> `trd` cumulativo.
        """
        mc: List[Dict[str, Any]] = []
        for tipo, mod in self.modelli.items():
            self.versione += 1
            blocco: Dict[str, Any] = {"id": mod["market_id"]}
            if con_definizione or self._primo:
                blocco["marketDefinition"] = _md(
                    mod["market_definition"], event_id=self.event_id, ko_ms=self.ko,
                    status=status, inplay=inplay, bet_delay=bet_delay,
                    versione=self.versione, vincitori=(vincitori or {}).get(tipo))
            per_sel = _sel_per_priorita(mod["market_definition"])
            rc: List[Dict[str, Any]] = []
            for priorita, sid in sorted(per_sel.items()):
                p = (prezzi or {}).get(tipo, {}).get(priorita)
                if p is None:
                    continue
                back, back_size, lay, lay_size = p
                riga: Dict[str, Any] = {"id": int(sid),
                                        "atb": [[round(back, 2), round(back_size, 2)]],
                                        "atl": [[round(lay, 2), round(lay_size, 2)]]}
                tr = (scambiato or {}).get(tipo, {}).get(priorita)
                if tr is not None:
                    prezzo, volume = tr
                    chiave = (tipo, int(sid), round(float(prezzo), 2))
                    self._cum[chiave] = self._cum.get(chiave, 0.0) + float(volume)
                    riga["trd"] = [[round(float(prezzo), 2), round(self._cum[chiave], 2)]]
                    riga["ltp"] = round(float(prezzo), 2)
                    riga["tv"] = round(sum(v for (t, s, _p), v in self._cum.items()
                                           if t == tipo and s == int(sid)), 2)
                rc.append(riga)
            if rc or "marketDefinition" in blocco:
                blocco["rc"] = rc
                if self._primo:
                    blocco["img"] = True
                mc.append(blocco)
        if not mc:
            return
        self._primo = False
        self.righe.append(json.dumps({"op": "mcm", "clk": "AAAAAAAA",
                                      "pt": int(pt_ms), "mc": mc}))

    def scrivi(self, cartella: str) -> str:
        os.makedirs(cartella, exist_ok=True)
        path = os.path.join(cartella, f"{self.event_id}.raw.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(self.righe) + "\n")
        return path


def scrivi_punteggi(cartella: str, event_id: str, modello: Dict[str, Any],
                    punti: List[Tuple[int, Optional[int], int, int]]) -> str:
    """Il sidecar `<id>.scores.jsonl`: record IPS VERI con minuto e gol riscritti.

    `punti` = [(ts_ms, minuto, gol casa, gol fuori)]. Un `minuto` None significa
    partita non ancora iniziata (come il record vero prima del fischio).
    """
    from datetime import datetime, timezone

    path = os.path.join(cartella, f"{event_id}.scores.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for ts_ms, minuto, casa, fuori in punti:
            rec = copy.deepcopy(modello)
            iso = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()
            rec["ts"] = iso
            rec["ts_ms"] = int(ts_ms)
            rec["minute"] = minuto
            rec["score_home"] = int(casa)
            rec["score_away"] = int(fuori)
            # IL PAYLOAD E' QUELLO DI BETFAIR IN-PLAY: si riscrivono le stesse
            # chiavi che `stream.scores.betfair_inplay.parse_score_dict` legge
            # (``timeElapsed``/``elapsedRegularTime``/``timeElapsedSeconds``,
            # ``score.home.score``, ``matchStatus``), nemmeno una in piu'.
            payload = rec["payload"]
            payload["eventId"] = str(event_id)
            punteggio = payload.setdefault("score", {})
            punteggio.setdefault("home", {})["score"] = str(int(casa))
            punteggio.setdefault("away", {})["score"] = str(int(fuori))
            if minuto is None:
                payload["timeElapsed"] = None
                payload["elapsedRegularTime"] = None
                payload["timeElapsedSeconds"] = None
                payload["status"] = payload["matchStatus"] = "NotStarted"
            else:
                payload["timeElapsed"] = int(minuto)
                payload["elapsedRegularTime"] = int(minuto)
                payload["timeElapsedSeconds"] = int(minuto) * 60
                stato = "FirstHalf" if int(minuto) <= 45 else "SecondHalf"
                payload["status"] = payload["matchStatus"] = stato
            fh.write(json.dumps(rec) + "\n")
    return path


# ---------------------------------------------------------------------------
# I CASI
# ---------------------------------------------------------------------------
def _quattro(back: float, back_size: float, lay: float, lay_size: float):
    return (back, back_size, lay, lay_size)


def caso_reingresso(modelli: Dict[str, Dict[str, Any]], modello_score: Dict[str, Any],
                    cartella: str, event_id: str,
                    lay_alla_riapertura: float = 1.48) -> Dict[str, Any]:
    """RE-INGRESSO (§3 Fase 6, controlli H1 e H2) — e insieme lo STATO TERMINALE (A2).

    La storia, scritta apposta perche' sui dati veri non e' mai capitata:

      1. 40' prima del fischio l'Under 3.5 sta 1,50/1,52 con liquidita': Mike
         entra (BACK Under 3.5) e appoggia la sua uscita pre-match a 1,48, che
         NON si abbina (il mercato non scende mai fin li' prima del fischio);
      2. al fischio il mercato passa in gioco: l'uscita al fischio (`ko_green`,
         lay appoggiata a 2 tick sotto l'ingresso) trova il book a 1,48 e si
         abbina INTERA -> chiusura in PROFITTO, `reentry_allowed`;
      3. al 20' arriva UN gol: un gol solo, primo tempo, e l'Under 4.5 quota
         1,60 (sopra il prezzo d'ingresso, come la regola richiede) con
         liquidita'. Mike RIENTRA — una volta sola (H1) e alle condizioni
         esatte (H2);
      4. la partita finisce 1-0, il mercato CHIUDE con i vincitori dichiarati:
         Mike regola, va in SETTLED e da li' in poi il servizio continua a
         girare su una partita in stato TERMINALE (A2).
    """
    mo, ou35, ou45 = "MATCH_ODDS", "OVER_UNDER_35", "OVER_UNDER_45"
    t0 = 1_800_000_000_000
    ko = t0 + 40 * 60 * 1000
    c = Costruttore(event_id, modelli, t0, ko)

    # MATCH_ODDS: un book qualunque ma VIVO (serve allo scanner per il catalogo
    # e per il riferimento 1X2 pre-KO)
    mo_prezzi = {1: _quattro(1.80, 200, 1.82, 200),
                 2: _quattro(4.00, 200, 4.10, 200),
                 3: _quattro(3.60, 200, 3.70, 200)}

    def istante(pt: int, *, u35, u45, status="OPEN", inplay=False, bet_delay=0,
                scambiato=None, vincitori=None, definizione=False) -> None:
        c.tick(pt, status=status, inplay=inplay, bet_delay=bet_delay,
               prezzi={mo: mo_prezzi, ou35: u35, ou45: u45},
               scambiato=scambiato, vincitori=vincitori, con_definizione=definizione)

    # sortPriority 1 = Under, 2 = Over (convenzione Betfair per le linee O/U)
    u35_pre = {1: _quattro(1.50, 300, 1.52, 300), 2: _quattro(2.90, 300, 3.00, 300)}
    u45_pre = {1: _quattro(1.20, 300, 1.22, 300), 2: _quattro(5.40, 300, 5.60, 300)}

    # ---- 1) PRE-MATCH: 40 minuti, book fermo -------------------------------
    pt = t0
    while pt < ko:
        istante(pt, u35=u35_pre, u45=u45_pre, definizione=(pt == t0))
        pt += PASSO_MS

    # ---- 2) FISCHIO: in gioco, poi sospensione tecnica, poi aperto ---------
    istante(ko, u35=u35_pre, u45=u45_pre, inplay=True, bet_delay=5, definizione=True)
    istante(ko + PASSO_MS, u35=u35_pre, u45=u45_pre, status="SUSPENDED",
            inplay=True, bet_delay=5, definizione=True)
    # riapertura con l'Under 3.5 SCESO a 1,48: l'uscita al fischio si abbina
    # `lay_alla_riapertura` = il miglior prezzo a cui si puo' LAYARE l'Under 3.5
    # appena il gioco comincia. A 1,48 l'uscita appoggiata di Mike si abbina al
    # suo prezzo; a 1,44 si abbina a un prezzo MIGLIORE del richiesto — ed e'
    # l'unico modo di mettere alla prova il difetto 3 del 15/09 (`avg_price` al
    # posto di `avg_price_matched`: il prezzo CHIESTO contabilizzato al posto di
    # quello ABBINATO). Su una partita vera quel caso non capita quasi mai.
    u35_live = {1: _quattro(round(lay_alla_riapertura - 0.02, 2), 300,
                            lay_alla_riapertura, 300),
                2: _quattro(3.30, 300, 3.40, 300)}
    u45_live = {1: _quattro(1.18, 300, 1.20, 300), 2: _quattro(5.80, 300, 6.00, 300)}
    pt = ko + 2 * PASSO_MS
    fine_apertura = ko + 6 * 60 * 1000
    while pt < fine_apertura:
        istante(pt, u35=u35_live, u45=u45_live, inplay=True, bet_delay=5,
                definizione=(pt == ko + 2 * PASSO_MS),
                scambiato={ou35: {1: (lay_alla_riapertura, 200.0)}})
        pt += PASSO_MS

    # ---- 3) IL GOL al 20': sospensione, poi Under 4.5 a 1,60 --------------
    gol = ko + 20 * 60 * 1000
    while pt < gol:
        istante(pt, u35=u35_live, u45=u45_live, inplay=True, bet_delay=5)
        pt += PASSO_MS
    istante(gol, u35=u35_live, u45=u45_live, status="SUSPENDED", inplay=True,
            bet_delay=5, definizione=True)
    # dopo il gol: Under 3.5 scende, Under 4.5 sale SOPRA il prezzo d'ingresso
    u35_gol = {1: _quattro(1.90, 300, 1.95, 300), 2: _quattro(2.05, 300, 2.10, 300)}
    u45_gol = {1: _quattro(1.60, 300, 1.62, 300), 2: _quattro(2.50, 300, 2.60, 300)}
    pt = gol + PASSO_MS
    fine_primo = ko + 45 * 60 * 1000
    primo = True
    while pt < fine_primo:
        istante(pt, u35=u35_gol, u45=u45_gol, inplay=True, bet_delay=5,
                definizione=primo)
        primo = False
        pt += PASSO_MS

    # ---- 4) SECONDO TEMPO senza altri gol, poi CHIUSURA --------------------
    fine = ko + 95 * 60 * 1000
    while pt < fine:
        istante(pt, u35=u35_gol, u45=u45_gol, inplay=True, bet_delay=5)
        pt += PASSO_MS
    istante(fine, u35=u35_gol, u45=u45_gol, status="SUSPENDED", inplay=True,
            bet_delay=5, definizione=True)
    # 1-0: Under 3.5 VINCE, Under 4.5 VINCE (sortPriority 1 = Under)
    vinc = {}
    for tipo in (ou35, ou45):
        per = _sel_per_priorita(modelli[tipo]["market_definition"])
        vinc[tipo] = {per[1]: "WINNER", per[2]: "LOSER"}
    per_mo = _sel_per_priorita(modelli[mo]["market_definition"])
    vinc[mo] = {per_mo[1]: "WINNER", per_mo[2]: "LOSER", per_mo[3]: "LOSER"}
    istante(fine + PASSO_MS, u35=u35_gol, u45=u45_gol, status="CLOSED", inplay=True,
            bet_delay=5, vincitori=vinc, definizione=True)
    # ...e il servizio continua a girare su una partita REGOLATA: e' l'unico
    # modo di mettere alla prova «da uno stato terminale non esce nessuna
    # azione» (A2) passando dal servizio vero.
    pt = fine + 2 * PASSO_MS
    for _ in range(120):
        istante(pt, u35=u35_gol, u45=u45_gol, status="CLOSED", inplay=True,
                bet_delay=5, vincitori=vinc)
        pt += PASSO_MS

    raw = c.scrivi(cartella)
    # i punteggi: nulli prima del fischio, 0-0 fino al 20', 1-0 dopo
    punti: List[Tuple[int, Optional[int], int, int]] = [(t0 + 60_000, None, 0, 0)]
    minuto = 1
    tp = ko + 60_000
    while tp < gol:
        punti.append((tp, minuto, 0, 0))
        minuto += 1
        tp += 60_000
    # il ritardo vero dell'IPS: il gol arriva sul tabellone 3 s dopo che il
    # mercato si e' sospeso (§6.1 del processo: stesso ritardo della produzione)
    punti.append((gol + 3_000, 20, 1, 0))
    minuto = 21
    tp = gol + 63_000
    while tp < fine:
        punti.append((tp, minuto, 1, 0))
        minuto += 1
        tp += 60_000
    scores = scrivi_punteggi(cartella, event_id, modello_score, punti)
    return {"raw": raw, "scores": scores, "messaggi": len(c.righe),
            "punteggi": len(punti), "ko_ms": ko}


def caso_prezzo_migliore(modelli: Dict[str, Dict[str, Any]],
                         modello_score: Dict[str, Any], cartella: str,
                         event_id: str) -> Dict[str, Any]:
    """PREZZO MIGLIORE DEL RICHIESTO (difetto 3 del 15/09, controllo K1).

    Identica alla partita del re-ingresso, con UNA differenza: alla riapertura
    dopo il fischio l'Under 3.5 si puo' layare a **1,44** invece che a 1,48.
    L'uscita appoggiata di Mike chiede 1,48 e si abbina a 1,44 — un prezzo
    MIGLIORE, come succede su un exchange. Da quel momento il prezzo che il bot
    contabilizza deve essere quello ABBINATO (1,44) e non quello CHIESTO: se
    qualcuno rimettesse `avg_price` al posto di `avg_price_matched`, K1
    diventerebbe rosso. Su 35760084 quel caso non capita mai.
    """
    return caso_reingresso(modelli, modello_score, cartella, event_id,
                           lay_alla_riapertura=1.44)


CASI = {"reingresso": caso_reingresso, "prezzo_migliore": caso_prezzo_migliore}


def genera(caso: str, data_dir: Optional[str] = None) -> Dict[str, Any]:
    dd = data_dir or _data_dir()
    event_id = f"_synth_mike_{caso}"
    cartella = os.path.join(dd, event_id)
    modelli = modelli_di_mercato(dd)
    score = modello_punteggio(dd)
    out = CASI[caso](modelli, score, cartella, event_id)
    out["event_id"] = event_id
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--caso", default="tutti", choices=list(CASI) + ["tutti"])
    ap.add_argument("--data-dir", default=None)
    a = ap.parse_args(argv)
    casi = list(CASI) if a.caso == "tutti" else [a.caso]
    for caso in casi:
        info = genera(caso, a.data_dir)
        print(f"SINTETICA {info['event_id']}: {info['messaggi']} messaggi, "
              f"{info['punteggi']} punteggi -> {info['raw']}")
    print("DICHIARAZIONE: sono registrazioni SINTETICHE. Non contano come partite "
          "reali in nessun referto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
