"""analisi_ordini.py - lettura di una giornata del registratore ordini (M-1, 11/10/2026).

Legge i file ``ordini_<servizio>_<pid>.jsonl.gz`` di UN giorno (scritti da
``registratore_ordini.py``) e ricostruisce:

  * la SEQUENZA ordine per ordine: place (REST) -> ocm EXECUTABLE -> parziali
    -> EXECUTION_COMPLETE (o cancel/lapse/void), con chi l'ha fatto;
  * le LATENZE della REST (per metodo, per attore) e REST -> primo ocm;
  * gli ordini del SITO (nessun nostro riferimento: ne' ``rfo`` ne' ``rfs``, e
    nessuna REST registrata che li abbia piazzati);
  * i messaggi ocm arrivati PRIMA della risposta REST dello stesso ordine;
  * i BUCHI: ripartenze dello stream (sottoscrizioni nuove, con o senza ripresa
    da ``clk``), immagini piene ripetute, ``status`` d'errore, messaggi di dati
    senza ``clk``, silenzi oltre il battito atteso, righe perse (sequenza o
    coda piena), file senza chiusura (processo morto), coda gzip tronca.

Solo lettura: nessuna scrittura, nessuna connessione. Uso::

    python -m Betfair.monitor.analisi_ordini --giorno 20261011
    python -m Betfair.monitor.analisi_ordini --cartella <dir> --giorno 20261011 --json out.json

Gli istanti sono quelli del PC (epoca in microsecondi). Il confronto fra file di
processi diversi usa l'epoca (stessa macchina, stesso orologio); le durate
dentro una chiamata usano l'orologio monotono.
ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import zlib
from typing import Any, Dict, Iterable, List, Optional, Tuple

#: battito di Betfair sullo stream ordini se la sottoscrizione non lo dice (ms)
BATTITO_DEFAULT_MS = 5000
#: un silenzio oltre ``FATTORE_SILENZIO`` battiti e' un buco
FATTORE_SILENZIO = 3.0

STATI_OCM = {"E": "EXECUTABLE", "EC": "EXECUTION_COMPLETE"}


# ---------------------------------------------------------------------------
# lettura dei file
# ---------------------------------------------------------------------------
MAGIA_GZIP = b"\x1f\x8b\x08"
_BLOCCO = 4096


def _un_membro(dati: bytes, da: int) -> Tuple[bytes, Optional[int], bool]:
    """Decomprime UN membro gzip a partire da ``da``, a blocchi, tenendo
    l'uscita gia' ottenuta anche se poi il membro si rompe.
    Ritorna (byte, posizione del membro dopo | None, membro completo)."""
    d = zlib.decompressobj(wbits=31)
    out: List[bytes] = []
    pos = da
    while pos < len(dati) and not d.eof:
        prima = d.copy()
        blocco = dati[pos:pos + _BLOCCO]
        try:
            out.append(d.decompress(blocco))
        except zlib.error:
            # il blocco si rifa' byte per byte: si tiene TUTTO cio' che precede
            # il primo byte che non si decomprime
            for j in range(len(blocco)):
                try:
                    out.append(prima.decompress(blocco[j:j + 1]))
                except zlib.error:
                    break
            return b"".join(out), None, False
        pos += _BLOCCO
    if not d.eof:
        try:
            out.append(d.flush())
        except zlib.error:
            pass
        return b"".join(out), None, False
    # membro completo: il successivo comincia dove finiscono i byte usati
    dopo = min(pos, len(dati)) - len(d.unused_data)
    return b"".join(out), dopo, True


def decomprimi_tollerante(dati: bytes) -> Tuple[bytes, bool]:
    """Decomprime un gzip a piu' membri anche quando un membro e' TRONCO
    (processo morto fra due svuotamenti) e altri membri lo seguono: tiene cio'
    che il membro rotto ha gia' dato (fino all'ultima riga intera) e riprende
    dal membro successivo (prossima firma ``1f 8b 08`` che si decomprime).
    Ritorna (byte, troncato)."""
    out: List[bytes] = []
    troncato = False
    pos = 0
    while pos < len(dati):
        if not dati[pos:].lstrip(b"\x00"):
            break
        pezzo, dopo, completo = _un_membro(dati, pos)
        if completo:
            out.append(pezzo)
            pos = dopo  # type: ignore[assignment]
            continue
        troncato = True
        # del membro rotto si tengono solo le righe intere
        taglio = pezzo.rfind(b"\n")
        if taglio >= 0:
            out.append(pezzo[:taglio + 1])
        # il prossimo membro che si lascia decomprimere
        cerca = pos + 1
        pos = len(dati)
        while True:
            i = dati.find(MAGIA_GZIP, cerca)
            if i < 0:
                break
            prova, _dopo, _c = _un_membro(dati, i)
            if prova or _c:
                pos = i
                break
            cerca = i + 1
    return b"".join(out), troncato


def leggi_file(percorso: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Le righe di un file e le sue informazioni (righe rotte, coda tronca)."""
    with open(percorso, "rb") as fh:
        grezzo = fh.read()
    dati, troncato = decomprimi_tollerante(grezzo)
    righe: List[Dict[str, Any]] = []
    rotte = 0
    for linea in dati.split(b"\n"):
        if not linea.strip():
            continue
        try:
            r = json.loads(linea.decode("utf-8", "replace"))
        except ValueError:
            rotte += 1
            continue
        if isinstance(r, dict):
            righe.append(r)
        else:
            rotte += 1
    avvii = [r for r in righe if r.get("k") == "avvio"]
    chiusure = [r for r in righe if r.get("k") == "chiusura"]
    info = {
        "file": os.path.basename(percorso),
        "percorso": percorso,
        "righe": len(righe),
        "rotte": rotte,
        "troncato": troncato,
        "servizio": avvii[0].get("servizio") if avvii else None,
        "pid": avvii[0].get("pid") if avvii else None,
        "avvii": len(avvii),
        "chiusura": chiusure[-1] if chiusure else None,
        "byte": len(grezzo),
    }
    return righe, info


def file_del_giorno(cartella: str, giorno: str) -> List[str]:
    return sorted(glob.glob(os.path.join(cartella, giorno, "ordini_*.jsonl.gz")))


# ---------------------------------------------------------------------------
# utilita'
# ---------------------------------------------------------------------------
def _percentili(valori: List[float]) -> Dict[str, Any]:
    if not valori:
        return {"n": 0}
    v = sorted(valori)

    def p(q: float) -> float:
        i = min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))
        return round(v[i], 3)

    return {"n": len(v), "min": round(v[0], 3), "p50": p(0.5), "p90": p(0.9),
            "p99": p(0.99), "max": round(v[-1], 3)}


def _attore_da_rfs(rfs: Any) -> str:
    from .registratore_ordini import attore_da

    return attore_da({"customerStrategyRef": rfs}) if rfs else "?"


def _ms(us: Optional[float]) -> Optional[float]:
    return None if us is None else round(us / 1000.0, 3)


# ---------------------------------------------------------------------------
# analisi
# ---------------------------------------------------------------------------
class _Ordine:
    __slots__ = ("bet_id", "market_id", "selection_id", "attore", "rfo", "rfs", "origine",
                 "place", "eventi", "chiavi_viste", "nato_da", "decisione", "copie")

    def __init__(self, bet_id: str) -> None:
        self.bet_id = bet_id
        self.market_id: Optional[str] = None
        self.selection_id: Any = None
        self.attore = "?"
        self.rfo: Any = None
        self.rfs: Any = None
        self.origine = "?"
        self.place: Optional[Dict[str, Any]] = None
        self.eventi: List[Dict[str, Any]] = []
        self.chiavi_viste: set = set()
        self.nato_da: Optional[str] = None
        self.decisione: Optional[Dict[str, Any]] = None
        self.copie = 0


def _ordine(ordini: Dict[str, _Ordine], bet_id: Any) -> _Ordine:
    b = str(bet_id)
    o = ordini.get(b)
    if o is None:
        o = ordini[b] = _Ordine(b)
    return o


def _report_place(rep: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
    istr = rep.get("instruction") or {}
    lim = istr.get("limitOrder") or {}
    return (str(rep["betId"]) if rep.get("betId") else None), {
        "stato_istruzione": rep.get("status"), "errore": rep.get("errorCode"),
        "orderStatus": rep.get("orderStatus"), "sizeMatched": rep.get("sizeMatched"),
        "averagePriceMatched": rep.get("averagePriceMatched"),
        "placedDate": rep.get("placedDate"), "selectionId": istr.get("selectionId"),
        "side": istr.get("side"), "price": lim.get("price"), "size": lim.get("size"),
        "persistenceType": lim.get("persistenceType"), "cor": istr.get("customerOrderRef"),
    }


SOGLIA_RITENTATIVO_MS = 2000.0


def _codici_annidati(rec: Dict[str, Any]) -> List[str]:
    """Tutti i codici d'errore di una REST: quello del rapporto, quelli delle
    istruzioni E quelli annidati di ``replaceOrders`` (cancel e place)."""
    out: List[str] = []
    res = _result(rec)
    if res.get("errorCode"):
        out.append(str(res["errorCode"]))
    for rep in res.get("instructionReports") or []:
        if not isinstance(rep, dict):
            continue
        if rep.get("errorCode"):
            out.append(str(rep["errorCode"]))
        for sotto in ("cancelInstructionReport", "placeInstructionReport"):
            x = rep.get(sotto)
            if isinstance(x, dict) and x.get("errorCode"):
                out.append(str(x["errorCode"]))
    if not res:
        # risposta senza ``result`` (errore JSON-RPC): il codice gia' estratto
        out.extend(str(c) for c in (rec.get("codici") or []) if c)
        if rec.get("errore"):
            out.append(str(rec["errore"]))
    return out


def _result(rec: Dict[str, Any]) -> Dict[str, Any]:
    r = rec.get("risposta")
    if isinstance(r, dict) and "result" in r and isinstance(r.get("result"), dict):
        return r["result"]
    return r if isinstance(r, dict) else {}


def analizza(letti: Iterable[Tuple[List[Dict[str, Any]], Dict[str, Any]]],
             fattore_silenzio: float = FATTORE_SILENZIO) -> Dict[str, Any]:
    """L'analisi di una giornata (``letti`` = uscite di ``leggi_file``)."""
    letti = list(letti)
    ordini: Dict[str, _Ordine] = {}
    rest_tutte: List[Dict[str, Any]] = []
    rifiuti: List[Dict[str, Any]] = []
    # decisioni PER MODO: paper e live non si sommano mai; si legano alle REST
    # solo quelle live (il paper non fa REST)
    decisioni: Dict[str, Dict[str, Dict[str, Any]]] = {}
    # l'ultimo istante visto in QUALUNQUE file (riferimento per la fine di un
    # processo morto senza riga di chiusura)
    fine_giorno_us = max([int(r["ep_us"]) for righe, _i in letti for r in righe
                          if isinstance(r.get("ep_us"), (int, float))] or [0])
    buchi_file: List[Dict[str, Any]] = []
    eventi_ocm: List[Tuple[int, str, Dict[str, Any], Dict[str, Any]]] = []

    for righe, info in letti:
        nome = info["file"]
        seqs = sorted(r["seq"] for r in righe
                      if isinstance(r.get("seq"), int) and r["seq"] > 0)
        seq_mancanti = 0
        for a, b in zip(seqs, seqs[1:]):
            if b > a + 1:
                seq_mancanti += b - a - 1
        ch = info.get("chiusura") or {}
        b: Dict[str, Any] = {
            "file": nome, "servizio": info.get("servizio"), "pid": info.get("pid"),
            "righe": info["righe"], "rotte": info["rotte"], "coda_gzip_tronca": info["troncato"],
            "fine_pulita": bool(ch), "motivo_fine": ch.get("motivo"),
            "persi_coda": ch.get("persi_coda"), "scartati_tetto": ch.get("scartati_tetto"),
            "scartati_errore": ch.get("scartati_errore"),
            "seq_mancanti": seq_mancanti, "sottoscrizioni": [], "silenzi": [],
            "status_errori": [], "immagini_piene": 0, "dati_senza_clk": 0,
            "messaggi_stream": 0, "battiti": 0,
        }
        battito_sid: Dict[int, float] = {}
        ultimo_sid: Dict[int, int] = {}
        primo_sid: Dict[int, int] = {}
        sub_ord: List[Tuple[int, int]] = []
        for r in righe:
            k = r.get("k")
            if k == "sub":
                b["sottoscrizioni"].append({
                    "sid": r.get("sid"), "ep_us": r.get("ep_us"), "ripresa": r.get("ripresa"),
                    "initial_clk": r.get("initial_clk"), "clk": r.get("clk"),
                    "conflate_ms": r.get("conflate_ms"), "heartbeat_ms": r.get("heartbeat_ms")})
                hb = r.get("heartbeat_ms") or BATTITO_DEFAULT_MS
                cf = r.get("conflate_ms") or 0
                battito_sid[int(r.get("sid") or 0)] = float(max(hb, cf))
                sub_ord.append((int(r.get("sid") or 0), int(r.get("ep_us") or 0)))
            elif k == "dec":
                if r.get("cor"):
                    modo = str(r.get("mode") or "?").strip().lower() or "?"
                    decisioni.setdefault(modo, {})[str(r["cor"])] = r
            elif k == "rest":
                rest_tutte.append(dict(r, _file=nome))
            elif k == "stream":
                b["messaggi_stream"] += 1
                msg = r.get("msg")
                if not isinstance(msg, dict):
                    continue
                sid = int(r.get("sid") or 0)
                ep = int(r.get("ep_us") or 0)
                prec = ultimo_sid.get(sid)
                soglia_us = fattore_silenzio * battito_sid.get(sid, BATTITO_DEFAULT_MS) * 1000.0
                if prec is not None and ep - prec > soglia_us:
                    b["silenzi"].append({"sid": sid, "tipo": "intermedio", "da_ep_us": prec,
                                         "a_ep_us": ep, "secondi": round((ep - prec) / 1e6, 3)})
                ultimo_sid[sid] = ep
                primo_sid.setdefault(sid, ep)
                op = msg.get("op")
                if op == "status":
                    if msg.get("statusCode") not in (None, "SUCCESS") or msg.get("connectionClosed"):
                        b["status_errori"].append({"sid": sid, "ep_us": ep,
                                                   "statusCode": msg.get("statusCode"),
                                                   "errorCode": msg.get("errorCode"),
                                                   "errorMessage": msg.get("errorMessage")})
                    continue
                if op != "ocm":
                    continue
                ct = msg.get("ct")
                if ct == "HEARTBEAT":
                    b["battiti"] += 1
                    continue
                if ct == "SUB_IMAGE":
                    b["immagini_piene"] += 1
                if not msg.get("clk") and not msg.get("initialClk"):
                    b["dati_senza_clk"] += 1
                eventi_ocm.append((ep, nome, msg, {"sid": sid, "ct": ct or "UPDATE"}))
        # silenzi ai BORDI di ogni sottoscrizione: sottoscrizione -> primo
        # messaggio, ultimo messaggio -> sottoscrizione dopo / chiusura / ultimo
        # istante visto nel giorno (processo morto senza chiusura)
        fine_file = ch.get("ep_us") if isinstance(ch.get("ep_us"), (int, float)) \
            else fine_giorno_us
        for i, (sid, ep_sub) in enumerate(sub_ord):
            soglia_us = fattore_silenzio * battito_sid.get(sid, BATTITO_DEFAULT_MS) * 1000.0
            fine_rif = sub_ord[i + 1][1] if i + 1 < len(sub_ord) else int(fine_file or 0)
            primo = primo_sid.get(sid)
            ultimo = ultimo_sid.get(sid)
            if primo is None:
                if fine_rif - ep_sub > soglia_us:
                    b["silenzi"].append({"sid": sid, "tipo": "nessun_messaggio",
                                         "da_ep_us": ep_sub, "a_ep_us": fine_rif,
                                         "secondi": round((fine_rif - ep_sub) / 1e6, 3)})
                continue
            if primo - ep_sub > soglia_us:
                b["silenzi"].append({"sid": sid, "tipo": "iniziale", "da_ep_us": ep_sub,
                                     "a_ep_us": primo, "secondi": round((primo - ep_sub) / 1e6, 3)})
            if ultimo is not None and fine_rif - ultimo > soglia_us:
                b["silenzi"].append({"sid": sid, "tipo": "finale", "da_ep_us": ultimo,
                                     "a_ep_us": fine_rif,
                                     "secondi": round((fine_rif - ultimo) / 1e6, 3)})
        b["ripartenze"] = max(0, len(b["sottoscrizioni"]) - 1)
        b["immagini_ripetute"] = max(0, b["immagini_piene"] - len(b["sottoscrizioni"]))
        buchi_file.append(b)

    # -- REST: piazzamenti, rimpiazzi, annulli, modifiche --------------------
    rest_tutte.sort(key=lambda r: r.get("ep_us") or 0)
    for r in rest_tutte:
        met = r.get("metodo")
        res = _result(r)
        base = {"file": r["_file"], "metodo": met, "invio_ep_us": r.get("ep_us"),
                "risposta_ep_us": r.get("risposta_ep_us"), "durata_ms": r.get("durata_ms"),
                "attore": r.get("attore"), "stato": r.get("stato"), "errore": r.get("errore"),
                "eccezione": r.get("eccezione"), "market_id": r.get("market_id")}
        reps = res.get("instructionReports") or []
        if met == "placeOrders":
            for rep in reps:
                bet, d = _report_place(rep)
                if bet is None:
                    rifiuti.append(dict(base, **d))
                    continue
                o = _ordine(ordini, bet)
                o.market_id = r.get("market_id")
                o.selection_id = d["selectionId"]
                o.attore = r.get("attore") or "?"
                o.rfo = d["cor"]
                o.rfs = r.get("csr")
                o.origine = "nostro"
                o.place = dict(base, **d)
            if not reps:
                rifiuti.append(dict(base))
        elif met == "replaceOrders":
            for rep in reps:
                c = rep.get("cancelInstructionReport") or {}
                p = rep.get("placeInstructionReport") or {}
                vecchio = (c.get("instruction") or {}).get("betId")
                if vecchio:
                    ov = _ordine(ordini, vecchio)
                    ov.eventi.append(dict(base, tipo="rest_replace_cancel",
                                          stato_istruzione=c.get("status"),
                                          errore=c.get("errorCode"),
                                          sizeCancelled=c.get("sizeCancelled")))
                bet, d = _report_place(p) if p else (None, {})
                if bet is None:
                    rifiuti.append(dict(base, **d, sostituisce=vecchio))
                    continue
                o = _ordine(ordini, bet)
                o.market_id = r.get("market_id")
                o.selection_id = d.get("selectionId")
                o.nato_da = str(vecchio) if vecchio else None
                padre = ordini.get(str(vecchio)) if vecchio else None
                o.attore = padre.attore if padre is not None else (r.get("attore") or "?")
                o.rfo = d.get("cor")
                o.origine = "nostro"
                o.place = dict(base, **d)
            if not reps:
                rifiuti.append(dict(base))
        elif met in ("cancelOrders", "updateOrders"):
            istr_req = (r.get("richiesta") or {}).get("instructions") or []
            for rep in reps:
                bet = (rep.get("instruction") or {}).get("betId")
                if not bet:
                    continue
                o = _ordine(ordini, bet)
                o.eventi.append(dict(base, tipo="rest_" + met, stato_istruzione=rep.get("status"),
                                     errore_istruzione=rep.get("errorCode"),
                                     sizeCancelled=rep.get("sizeCancelled")))
            if not reps:
                # cancel di TUTTO il mercato (nessuna istruzione) o eccezione
                for i in istr_req or [{}]:
                    bet = i.get("betId") if isinstance(i, dict) else None
                    if bet:
                        _ordine(ordini, bet).eventi.append(dict(base, tipo="rest_" + met))
                    else:
                        rifiuti.append(dict(base, nota="senza esito per istruzione"))

    # -- ocm: gli eventi di ogni ordine, una volta sola anche se visti da piu'
    #    processi (il primo arrivo vince, le copie si contano) ----------------
    eventi_ocm.sort(key=lambda e: e[0])
    for ep, nome, msg, extra in eventi_ocm:
        for oc in msg.get("oc") or []:
            mid = oc.get("id")
            for orc in oc.get("orc") or []:
                for uo in orc.get("uo") or []:
                    bet = uo.get("id")
                    if not bet:
                        continue
                    o = _ordine(ordini, bet)
                    o.market_id = o.market_id or mid
                    o.selection_id = o.selection_id if o.selection_id is not None else orc.get("id")
                    if uo.get("rfo") and not o.rfo:
                        o.rfo = uo.get("rfo")
                    if uo.get("rfs") and not o.rfs:
                        o.rfs = uo.get("rfs")
                    chiave = (uo.get("status"), uo.get("sm"), uo.get("sr"), uo.get("sc"),
                              uo.get("sl"), uo.get("sv"), uo.get("p"), uo.get("s"))
                    if chiave in o.chiavi_viste:
                        o.copie += 1
                        continue
                    o.chiavi_viste.add(chiave)
                    o.eventi.append({
                        "tipo": "ocm", "file": nome, "ep_us": ep, "sid": extra["sid"],
                        "ct": extra["ct"], "pt": msg.get("pt"),
                        "stato": STATI_OCM.get(uo.get("status"), uo.get("status")),
                        "sm": uo.get("sm"), "sr": uo.get("sr"), "sc": uo.get("sc"),
                        "sl": uo.get("sl"), "sv": uo.get("sv"), "p": uo.get("p"),
                        "s": uo.get("s"), "avp": uo.get("avp"), "side": uo.get("side"),
                        "pd": uo.get("pd"), "md": uo.get("md"), "cd": uo.get("cd"),
                        "ld": uo.get("ld"), "lsrc": uo.get("lsrc")})

    # -- per ordine: origine, latenze, ocm prima della risposta ---------------
    lat_rest_ocm: List[float] = []
    lat_invio_ocm: List[float] = []
    lat_decisione_invio: List[float] = []
    prima_della_risposta: List[Dict[str, Any]] = []
    sito: List[Dict[str, Any]] = []
    sequenze: List[Dict[str, Any]] = []
    for bet, o in ordini.items():
        ocm = [e for e in o.eventi if e.get("tipo") == "ocm"]
        if o.place is None:
            if not o.rfo and not o.rfs:
                o.origine = "sito"
            else:
                o.origine = "altro_processo"
                o.attore = _attore_da_rfs(o.rfs)
        if o.origine == "sito":
            sito.append({"bet_id": bet, "market_id": o.market_id, "selection_id": o.selection_id,
                         "primo_ep_us": ocm[0]["ep_us"] if ocm else None,
                         "stato_finale": ocm[-1]["stato"] if ocm else None,
                         "sm": ocm[-1]["sm"] if ocm else None})
        primo = ocm[0] if ocm else None
        riga: Dict[str, Any] = {
            "bet_id": bet, "market_id": o.market_id, "selection_id": o.selection_id,
            "attore": o.attore, "origine": o.origine, "rfo": o.rfo, "rfs": o.rfs,
            "nato_da": o.nato_da, "copie_ocm": o.copie,
        }
        if o.place is not None:
            p = o.place
            riga["place"] = p
            dec_live = decisioni.get("live", {})
            if o.rfo and str(o.rfo) in dec_live:
                d = dec_live[str(o.rfo)]
                riga["decisione"] = {k: d.get(k) for k in ("chiave", "strada", "azione", "rif",
                                                           "decisione_ms", "ricezione_ms")}
                dm = d.get("decisione_ms")
                if isinstance(dm, (int, float)) and p.get("invio_ep_us"):
                    v = p["invio_ep_us"] / 1000.0 - float(dm)
                    riga["decisione_invio_ms"] = round(v, 3)
                    lat_decisione_invio.append(v)
            if primo is not None and p.get("risposta_ep_us"):
                dr = (primo["ep_us"] - p["risposta_ep_us"]) / 1000.0
                di = (primo["ep_us"] - p["invio_ep_us"]) / 1000.0
                riga["risposta_primo_ocm_ms"] = round(dr, 3)
                riga["invio_primo_ocm_ms"] = round(di, 3)
                lat_rest_ocm.append(dr)
                lat_invio_ocm.append(di)
                if dr < 0:
                    prima_della_risposta.append({
                        "bet_id": bet, "metodo": p.get("metodo"), "anticipo_ms": round(-dr, 3),
                        "file_rest": p.get("file"), "file_ocm": primo["file"],
                        "stato_ocm": primo["stato"]})
        riga["eventi"] = sorted(o.eventi, key=lambda e: e.get("ep_us") or e.get("invio_ep_us") or 0)
        fin = ocm[-1] if ocm else None
        riga["stato_finale"] = fin["stato"] if fin else None
        riga["parziali"] = sum(1 for e in ocm if e.get("stato") == "EXECUTABLE" and (e.get("sm") or 0) > 0)
        sequenze.append(riga)
    sequenze.sort(key=lambda r: ((r.get("place") or {}).get("invio_ep_us")
                                 or (r["eventi"][0].get("ep_us") if r["eventi"] else 0) or 0))

    # -- latenze REST ----------------------------------------------------------
    # I percentili si fanno SOLO sulle chiamate pulite: niente eccezione, niente
    # codice d'errore, e per il client nostro niente durata da ritentativo
    # (``_rpc`` dorme 2**tentativo s fra un tentativo e l'altro: >= 2 s e'
    # quasi certamente un ritentativo). Le altre hanno percentili a parte.
    per_metodo: Dict[str, List[float]] = {}
    per_via: Dict[str, List[float]] = {}
    per_attore: Dict[str, List[float]] = {}
    scartate: Dict[str, List[float]] = {}
    errori: Dict[str, int] = {}
    for r in rest_tutte:
        d = r.get("durata_ms")
        codici = _codici_annidati(r)
        if isinstance(d, (int, float)):
            if r.get("eccezione") or codici:
                scartate.setdefault("con_errore " + str(r.get("metodo")), []).append(float(d))
            elif r.get("via") == "rest_nostro" and float(d) >= SOGLIA_RITENTATIVO_MS:
                scartate.setdefault("probabile_ritentativo " + str(r.get("metodo")),
                                    []).append(float(d))
            else:
                per_metodo.setdefault(str(r.get("metodo")), []).append(float(d))
                per_via.setdefault("%s %s" % (r.get("via"), r.get("metodo")), []).append(float(d))
                per_attore.setdefault("%s %s" % (r.get("attore"), r.get("metodo")),
                                      []).append(float(d))
        if r.get("eccezione"):
            codici.append("eccezione:" + str(r["eccezione"]).split(":", 1)[0])
        for c in codici:
            chiave = "%s %s" % (r.get("metodo"), c)
            errori[chiave] = errori.get(chiave, 0) + 1

    return {
        "file": [b["file"] for b in buchi_file],
        "conteggi": {
            "rest": len(rest_tutte), "ordini": len(ordini),
            "ordini_nostri": sum(1 for o in ordini.values() if o.origine == "nostro"),
            "ordini_sito": len(sito),
            "ordini_altri_processi": sum(1 for o in ordini.values() if o.origine == "altro_processo"),
            "rifiuti_senza_bet": len(rifiuti),
            "ocm_prima_della_risposta": len(prima_della_risposta),
            "decisioni": {m: len(v) for m, v in sorted(decisioni.items())},
        },
        "latenze": {
            "rest_ms_per_metodo": {k: _percentili(v) for k, v in sorted(per_metodo.items())},
            "rest_ms_per_attore": {k: _percentili(v) for k, v in sorted(per_attore.items())},
            "rest_ms_per_via": {k: _percentili(v) for k, v in sorted(per_via.items())},
            "rest_ms_escluse": {k: _percentili(v) for k, v in sorted(scartate.items())},
            "risposta_rest_primo_ocm_ms": _percentili(lat_rest_ocm),
            "invio_rest_primo_ocm_ms": _percentili(lat_invio_ocm),
            "decisione_invio_rest_ms": _percentili(lat_decisione_invio),
        },
        "errori_rest": dict(sorted(errori.items())),
        "rifiuti": rifiuti,
        "ocm_prima_della_risposta": prima_della_risposta,
        "ordini_sito": sito,
        "sequenze": sequenze,
        "buchi": buchi_file,
        "ci_sono_buchi": any(
            b["ripartenze"] or b["silenzi"] or b["status_errori"] or b["seq_mancanti"]
            or b["dati_senza_clk"] or b["immagini_ripetute"] or not b["fine_pulita"]
            or b["coda_gzip_tronca"] or b["rotte"] or (b["persi_coda"] or 0)
            or (b["scartati_tetto"] or 0) or (b["scartati_errore"] or 0)
            for b in buchi_file),
    }


def analizza_giorno(cartella: str, giorno: str) -> Dict[str, Any]:
    return analizza(leggi_file(p) for p in file_del_giorno(cartella, giorno))


def giorni_fra(dal: str, al: str) -> List[str]:
    """I giorni AAAAMMGG da ``dal`` ad ``al`` compresi."""
    import datetime as _dt

    a = _dt.datetime.strptime(dal, "%Y%m%d").date()
    b = _dt.datetime.strptime(al, "%Y%m%d").date()
    out = []
    while a <= b:
        out.append(a.strftime("%Y%m%d"))
        a += _dt.timedelta(days=1)
    return out


def analizza_giorni(cartella: str, giorni: Iterable[str]) -> Dict[str, Any]:
    """Piu' giorni INSIEME (es. gli ordini a cavallo della mezzanotte UTC)."""
    return analizza(leggi_file(p) for g in giorni for p in file_del_giorno(cartella, g))


# ---------------------------------------------------------------------------
# referto in testo
# ---------------------------------------------------------------------------
def formatta(a: Dict[str, Any], dettaglio: int = 20) -> str:
    out: List[str] = []
    c = a["conteggi"]
    out.append("REGISTRO ORDINI - file: %d" % len(a["file"]))
    out.append("  REST con soldi: %d | ordini: %d (nostri %d, sito %d, altri processi %d) | "
               "rifiuti senza bet: %d | decisioni per modo: %s"
               % (c["rest"], c["ordini"], c["ordini_nostri"], c["ordini_sito"],
                  c["ordini_altri_processi"], c["rifiuti_senza_bet"],
                  ", ".join("%s %d" % kv for kv in c["decisioni"].items()) or "nessuna"))
    out.append("LATENZE (ms)")
    for k, v in a["latenze"]["rest_ms_per_metodo"].items():
        out.append("  REST %-14s %s" % (k, _riga_perc(v)))
    out.append("  risposta REST -> primo ocm   %s" % _riga_perc(a["latenze"]["risposta_rest_primo_ocm_ms"]))
    out.append("  invio REST -> primo ocm      %s" % _riga_perc(a["latenze"]["invio_rest_primo_ocm_ms"]))
    out.append("  decisione -> invio REST      %s" % _riga_perc(a["latenze"]["decisione_invio_rest_ms"]))
    for k, v in a["latenze"].get("rest_ms_escluse", {}).items():
        out.append("  ESCLUSE dai percentili: %-34s %s" % (k, _riga_perc(v)))
    if a["errori_rest"]:
        out.append("ERRORI REST")
        for k, n in a["errori_rest"].items():
            out.append("  %-50s %d" % (k, n))
    out.append("OCM PRIMA DELLA RISPOSTA REST: %d" % c["ocm_prima_della_risposta"])
    for x in a["ocm_prima_della_risposta"][:dettaglio]:
        out.append("  bet %s %s: ocm %s con %.1f ms di anticipo" % (
            x["bet_id"], x["metodo"], x["stato_ocm"], x["anticipo_ms"]))
    out.append("ORDINI DEL SITO: %d" % c["ordini_sito"])
    for x in a["ordini_sito"][:dettaglio]:
        out.append("  bet %s mercato %s sel %s -> %s abbinato %s" % (
            x["bet_id"], x["market_id"], x["selection_id"], x["stato_finale"], x["sm"]))
    out.append("BUCHI: %s" % ("SI" if a["ci_sono_buchi"] else "nessuno"))
    for b in a["buchi"]:
        out.append("  %s: righe %d, stream %d (battiti %d), ripartenze %d, immagini ripetute %d, "
                   "silenzi %d, status d'errore %d, senza clk %d, seq mancanti %d, persi %s, "
                   "oltre tetto %s, fine %s%s%s" % (
                       b["file"], b["righe"], b["messaggi_stream"], b["battiti"], b["ripartenze"],
                       b["immagini_ripetute"], len(b["silenzi"]), len(b["status_errori"]),
                       b["dati_senza_clk"], b["seq_mancanti"], b["persi_coda"],
                       b["scartati_tetto"], b["motivo_fine"] or "NON PULITA",
                       ", coda gzip tronca" if b["coda_gzip_tronca"] else "",
                       (", righe rotte %d" % b["rotte"]) if b["rotte"] else ""))
        for s in b["sottoscrizioni"]:
            out.append("    sottoscrizione sid %s %s" % (
                s["sid"], "ripresa da clk" if s["ripresa"] else "immagine piena"))
        for s in b["silenzi"][:dettaglio]:
            out.append("    silenzio %s sid %s di %.1f s" % (s.get("tipo"), s["sid"], s["secondi"]))
    out.append("SEQUENZE (prime %d)" % dettaglio)
    for r in a["sequenze"][:dettaglio]:
        passi = []
        for e in r["eventi"]:
            if e.get("tipo") == "ocm":
                passi.append("%s(sm=%s,sr=%s)" % ("EC" if e["stato"] == "EXECUTION_COMPLETE"
                                                  else "E", e.get("sm"), e.get("sr")))
            else:
                passi.append(str(e.get("tipo")))
        testa = "place %.0fms" % r["place"]["durata_ms"] if r.get("place") and \
            isinstance(r["place"].get("durata_ms"), (int, float)) else r["origine"]
        out.append("  bet %s [%s] %s -> %s" % (r["bet_id"], r["attore"], testa, " -> ".join(passi)))
    return "\n".join(out)


def _riga_perc(v: Dict[str, Any]) -> str:
    if not v.get("n"):
        return "n=0"
    return "n=%d p50=%s p90=%s p99=%s max=%s" % (v["n"], v["p50"], v["p90"], v["p99"], v["max"])


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Analisi di una giornata del registratore ordini (M-1)")
    ap.add_argument("--giorno", default=None, help="AAAAMMGG (UTC)")
    ap.add_argument("--dal", default=None, help="AAAAMMGG (UTC), con --al: piu' giorni insieme")
    ap.add_argument("--al", default=None, help="AAAAMMGG (UTC), compreso")
    ap.add_argument("--cartella", default=None, help="di serie <LIVE_STREAM_DATA_DIR>/_ordini")
    ap.add_argument("--json", default=None, help="scrive l'analisi intera in questo file")
    ap.add_argument("--dettaglio", type=int, default=20)
    args = ap.parse_args(argv)
    cartella = args.cartella
    if not cartella:
        from .registratore_ordini import cartella_base

        cartella = cartella_base()
    if args.dal or args.al:
        giorni = giorni_fra(args.dal or args.al, args.al or args.dal)
    elif args.giorno:
        giorni = [args.giorno]
    else:
        ap.error("serve --giorno oppure --dal/--al")
        return 2
    a = analizza_giorni(cartella, giorni)
    print(formatta(a, args.dettaglio))
    if args.json:
        with open(args.json, "w", encoding="ascii") as fh:
            json.dump(a, fh, ensure_ascii=True, indent=1, default=str)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
