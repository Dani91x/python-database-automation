"""mappa_flussi.py - la MAPPA DEI FLUSSI REALI di una giornata (M-3, 11/10/2026).

Comando riproducibile (dalla radice del repo, il giorno dopo la giornata):

    python -m Betfair.stream.mappa_flussi --giorno 2026-10-12
    python -m Betfair.stream.mappa_flussi --giorno 2026-10-12 --canale _logs/canale \\
        --raw _live_raw --salute _logs/monitor --ordini <cartella di M-1> \\
        --uscita ARCHITETTURA_2026-10/mappa/MAPPA_2026-10-12.md --json mappa.json

Legge, SOLO se ci sono (cio' che manca si DICE nel referto, mai si inventa):

  * ``--canale``: le registrazioni del registratore del canale locale
    (``registratore_canale.py``): ``<canale>/<giorno>/canale_<porta>[_<pid>[_n]].jsonl.gz``
    (un file per processo; i processi si distinguono per porta, pid e avvio);
  * ``--raw``: le registrazioni raw dei prezzi (``raw_listener.py``):
    ``<raw>/<evento>/<evento>.raw.jsonl[.gz]`` (+ ``.recmeta.jsonl``); si tengono
    i messaggi con ``pt`` nel giorno (fuso Europe/Rome), si saltano i file non
    toccati quel giorno (mtime);
  * ``--salute``: le righe locali di "Salute" (``Betfair/monitor/scrittore.py``):
    ``<salute>/<giorno>/<servizio>.jsonl``;
  * ``--ordini``: la cartella dei file di M-1 (``Betfair/monitor/
    registratore_ordini.py``): ``<LIVE_STREAM_DATA_DIR>/_ordini/<AAAAMMGG UTC>/
    ordini_<servizio>_<pid>[_n].jsonl.gz``. Si leggono le cartelle UTC che
    coprono il giorno LOCALE (di solito due) con un glob ricorsivo
    ``ordini_*.jsonl*`` e si tengono le righe con l'istante nel giorno. Righe di
    M-1: ``k`` (``stream``, ``rest``, ``dec``, ``sub``, ``avvio``, ``chiusura``),
    ``ep_us``/``mono_us`` in microsecondi; le ``rest`` anche ``risposta_ep_us``/
    ``risposta_mono_us``, ``metodo``, ``attore``, ``errore``. Riassunto per file e
    genere, durate delle REST per metodo e attore, e la latenza comando della UI
    sul canale -> risposta della REST. Se nel processo c'e' il lettore di M-1
    (``Betfair.monitor.analisi_ordini``) se ne allega anche il referto.

Produce un referto Markdown (e a richiesta il JSON dei numeri) con: chi pubblica
e chi riceve cosa, cadenza (p50/p95/p99 dei tempi fra messaggi), byte al
secondo, client; i client saltati; i comandi della UI e il loro esito; i buchi.
Stessi file in ingresso = stessi byte in uscita (nessun "adesso" nel testo).

Sola lettura. Nessun import di flumine, betfairlightweight o del DB.
ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .gz_tollerante import problema as _gz_problema
from .gz_tollerante import righe_file as _gz_righe

RADICE = Path(__file__).resolve().parents[2]

try:
    from zoneinfo import ZoneInfo

    FUSO: Any = ZoneInfo("Europe/Rome")
    NOME_FUSO = "Europe/Rome"
except Exception:  # noqa: BLE001 - tzdata assente: si dichiara UTC
    FUSO = timezone.utc
    NOME_FUSO = "UTC"

#: silenzio oltre il quale un processo del canale "tace" (nessun record)
SOGLIA_SILENZIO_CANALE_S = 60.0
#: buco nel raw dei prezzi: nessun messaggio (nemmeno heartbeat) per piu' di
SOGLIA_BUCO_RAW_S = 15.0
#: buco nelle righe di Salute: oltre 2 finestre senza riga
FATTORE_BUCO_SALUTE = 2.0
#: buco generico nei file di M-1
SOGLIA_BUCO_ORDINI_S = 60.0
#: un comando della UI si accoppia alla prima REST del desktop entro questa finestra
FINESTRA_UI_REST_S = 5.0
MAX_ELENCO = 15
#: azione del comando della UI -> metodo REST di Betfair
_AZIONE_REST = {"place": "placeOrders", "cancel": "cancelOrders", "replace": "replaceOrders",
                "update": "updateOrders"}

_CHIAVI_TEMPO = ("epoca_ms", "ts_ms", "epoch_ms", "rx", "pt")
_CHIAVI_GENERE = ("k", "tipo", "kind", "op", "evento")
_RE_PT = re.compile(r'"pt"\s*:\s*(\d+)')
_RE_RX = re.compile(r'"rx"\s*:\s*(\d+)')
_RE_HEARTBEAT = re.compile(r'"ct"\s*:\s*"HEARTBEAT"')


# ---------------------------------------------------------------------------
# utilita' pure
# ---------------------------------------------------------------------------
def percentile(valori: List[float], p: float) -> Optional[float]:
    """Percentile a rango piu' vicino (deterministico). ``None`` se vuoto."""
    if not valori:
        return None
    v = sorted(valori)
    k = max(0, min(len(v) - 1, int(-(-p * len(v) // 100)) - 1))
    return float(v[k])


def _f(x: Optional[float], nd: int = 1) -> str:
    if x is None:
        return "-"
    return ("%." + str(nd) + "f") % x


def limiti_giorno(giorno: str) -> Tuple[int, int]:
    """[inizio, fine) del giorno nel fuso, in ms epoca."""
    d = datetime.strptime(giorno, "%Y-%m-%d").replace(tzinfo=FUSO)
    a = int(d.timestamp() * 1000)
    b = int((d + timedelta(days=1)).timestamp() * 1000)
    return a, b


def ora(ms: Optional[float]) -> str:
    if ms is None:
        return "-"
    return datetime.fromtimestamp(ms / 1000.0, tz=FUSO).strftime("%H:%M:%S")


def righe_testo(p: Path) -> Tuple[List[str], Optional[str]]:
    """Le righe di un file di testo o gzip. Il gzip si legge in modo TOLLERANTE
    (``gz_tollerante``): coda tronca, membri corrotti e membri accodati dopo un
    flusso tronco non fermano la lettura, e il problema si dice."""
    try:
        if p.name.endswith(".gz"):
            grezze, resoconto = _gz_righe(str(p))
            return [g.decode("utf-8", "replace") for g in grezze], (_gz_problema(resoconto)
                                                                     or None)
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            return [r for r in fh.read().splitlines() if r.strip()], None
    except OSError as e:
        return [], "file illeggibile: %s" % type(e).__name__


def leggi_jsonl(p: Path) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Righe JSON di un file (anche gzip rovinato: si legge tutto il leggibile e
    lo si dice)."""
    righe: List[Dict[str, Any]] = []
    testi, errore = righe_testo(p)
    cattive = 0
    for linea in testi:
        try:
            o = json.loads(linea)
        except ValueError:
            cattive += 1
            continue
        if isinstance(o, dict):
            righe.append(o)
    if cattive:
        errore = (errore + "; " if errore else "") + "%d righe illeggibili" % cattive
    return righe, errore


def cadenza_ms(istanti_ms: List[float]) -> Dict[str, Optional[float]]:
    d = [b - a for a, b in zip(istanti_ms, istanti_ms[1:])]
    return {"p50": percentile(d, 50), "p95": percentile(d, 95), "p99": percentile(d, 99),
            "max": max(d) if d else None}


def buchi(istanti_ms: List[float], soglia_ms: float) -> List[Tuple[float, float]]:
    return [(a, b) for a, b in zip(istanti_ms, istanti_ms[1:]) if b - a > soglia_ms]


def _rel(p: Optional[Path]) -> str:
    if p is None:
        return "-"
    try:
        return str(Path(p).resolve().relative_to(RADICE)).replace(os.sep, "/")
    except ValueError:
        return str(p).replace(os.sep, "/")


# ---------------------------------------------------------------------------
# 1. canale locale
# ---------------------------------------------------------------------------
def analizza_canale(cartella: Optional[Path], giorno: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"fonte": "canale", "cartella": _rel(cartella), "file": [],
                           "mancante": None}
    if cartella is None:
        out["mancante"] = "cartella non indicata"
        return out
    d = Path(cartella) / giorno
    if not d.is_dir():
        out["mancante"] = "nessuna cartella %s (registratore spento quel giorno?)" % _rel(d)
        return out
    files = sorted(d.glob("canale_*.jsonl.gz"))  # anche canale_<porta>_<pid>[_n]
    if not files:
        out["mancante"] = "nessun file canale_*.jsonl.gz in %s" % _rel(d)
        return out
    topics: Dict[Tuple[int, str], Dict[str, Any]] = {}
    salti: Dict[Tuple[int, str], List[float]] = {}
    comandi: List[Dict[str, Any]] = []
    risposte: List[Dict[str, Any]] = []
    processi: Dict[Tuple[Any, Any, Any], Dict[str, Any]] = {}
    collegati: Dict[Tuple[Any, str, str], Dict[str, Any]] = {}
    for f in files:
        righe, errore = leggi_jsonl(f)
        out["file"].append({"nome": f.name, "righe": len(righe), "errore": errore,
                            "byte_gz": f.stat().st_size})
        for r in righe:
            porta, pid, av = r.get("porta"), r.get("pid"), r.get("av")
            # la VITA di un processo: porta, pid e istante d'avvio (un pid
            # riusato, un riavvio nello stesso giorno = un processo nuovo)
            pr = processi.setdefault((porta, pid, av), {
                "porta": porta, "pid": pid, "av": av, "sport": r.get("sport"), "seq": [],
                "epoca": [], "stato": None, "tetto": [], "chiuso": False,
                "file": set()})
            pr["file"].add(f.name)
            if r.get("sport") and not pr["sport"]:
                pr["sport"] = r.get("sport")
            k = r.get("k")
            if k in ("stato", "tetto_raggiunto", "chiusura"):
                pr["stato"] = r.get("conti")
                if k == "tetto_raggiunto":
                    pr["tetto"].append(r.get("epoca_ms"))
                if k == "chiusura":
                    pr["chiuso"] = True
                continue
            if "seq" in r:
                pr["seq"].append(int(r["seq"]))
            if "epoca_ms" in r:
                pr["epoca"].append(float(r["epoca_ms"]))
            if k == "pub" and isinstance(r.get("clienti"), list):
                _conta_collegati(collegati, porta, r)
            if k == "pub":
                t = topics.setdefault((porta, r.get("topic")), {
                    "n": 0, "byte": 0, "con_payload": 0, "mono": {}, "dest": [],
                    "client": [], "lettori": [], "saltati": 0, "giri_con_saltati": 0,
                    "prima": None, "ultima": None, "sport": r.get("sport")})
                t["n"] += 1
                t["byte"] += int(r.get("byte") or 0)
                t["con_payload"] += 1 if "msg" in r else 0
                t["mono"].setdefault((pid, av), []).append(r["mono_ns"] / 1e6)
                t["dest"].append(int(r.get("dest") or 0))
                t["client"].append(int(r.get("client") or 0))
                t["lettori"].append(int(r.get("lettori") or 0))
                s = int(r.get("saltati") or 0)
                t["saltati"] += s
                t["giri_con_saltati"] += 1 if s else 0
                e = r.get("epoca_ms")
                t["prima"] = e if t["prima"] is None else min(t["prima"], e)
                t["ultima"] = e if t["ultima"] is None else max(t["ultima"], e)
            elif k == "giro_saltato":
                salti.setdefault((porta, r.get("topic")), []).append(r.get("epoca_ms"))
            elif k == "rx":
                comandi.append(r)
            elif k == "tx":
                risposte.append(r)
    out["topic"] = _riassumi_topic(topics)
    out["collegati"] = [dict(v, porta=p, genere=g, chi=c) for (p, g, c), v in
                        sorted(collegati.items(), key=lambda x: (str(x[0][0]), x[0][1], x[0][2]))]
    out["giri_saltati"] = [{"porta": p, "topic": t, "n": len(v), "prima": min(v),
                            "ultima": max(v)} for (p, t), v in sorted(salti.items(),
                                                                       key=lambda x: (x[0][0], str(x[0][1])))]
    out["processi"] = _riassumi_processi(processi)
    out["comandi"] = _accoppia_comandi(comandi, risposte)
    # i comandi d'ordine della UI (per la latenza UI -> REST con i file di M-1)
    out["_ordini_ui"] = sorted(
        ({"epoca_ms": c.get("epoca_ms"), "porta": c.get("porta"),
          "azione": _par(c).get("action"), "modo": _modo(c)}
         for c in comandi if c.get("genere") == "desktop" and _msg(c).get("m") == "order"),
        key=lambda x: (x["epoca_ms"] or 0))
    return out


def _conta_collegati(coll: Dict[Tuple[Any, str, str], Dict[str, Any]], porta: Any,
                     r: Dict[str, Any]) -> None:
    """Composizione dei client (record ``pub`` con ``clienti``): per porta e
    genere di client, quanti insieme al massimo e quando."""
    per: Dict[Tuple[str, str], int] = {}
    for c in r["clienti"]:
        if isinstance(c, list) and len(c) == 3:
            k2 = (str(c[1]), str(c[2] if c[2] is not None else "-"))
            per[k2] = per.get(k2, 0) + 1
    e = r.get("epoca_ms")
    for (g, chi), n in per.items():
        v = coll.setdefault((porta, g, chi), {"max_insieme": 0, "visto_dalle": e,
                                               "cambi": 0})
        v["max_insieme"] = max(v["max_insieme"], n)
        v["cambi"] += 1
        if e is not None and (v["visto_dalle"] is None or e < v["visto_dalle"]):
            v["visto_dalle"] = e


def _riassumi_topic(topics: Dict[Tuple[int, str], Dict[str, Any]]) -> List[Dict[str, Any]]:
    res = []
    for (porta, topic), t in sorted(topics.items(), key=lambda x: (x[0][0], str(x[0][1]))):
        gap: List[float] = []
        for istanti in t["mono"].values():
            gap.extend(b - a for a, b in zip(istanti, istanti[1:]))
        durata_s = ((t["ultima"] or 0) - (t["prima"] or 0)) / 1000.0
        res.append({
            "porta": porta, "sport": t["sport"], "topic": topic, "n": t["n"],
            "byte": t["byte"], "con_payload": t["con_payload"],
            "byte_s": (t["byte"] / durata_s) if durata_s > 0 else None,
            "msg_s": (t["n"] / durata_s) if durata_s > 0 else None,
            "cad_p50": percentile(gap, 50), "cad_p95": percentile(gap, 95),
            "cad_p99": percentile(gap, 99),
            "dest_p50": percentile([float(x) for x in t["dest"]], 50),
            "dest_max": max(t["dest"]) if t["dest"] else None,
            "client_max": max(t["client"]) if t["client"] else None,
            "lettori_max": max(t["lettori"]) if t["lettori"] else None,
            "saltati": t["saltati"], "giri_con_saltati": t["giri_con_saltati"],
            "prima": t["prima"], "ultima": t["ultima"]})
    return res


def _riassumi_processi(processi: Dict[Tuple[Any, Any, Any], Dict[str, Any]]
                       ) -> List[Dict[str, Any]]:
    res = []
    for (porta, pid, av), pr in sorted(processi.items(),
                                       key=lambda x: (str(x[0][0]), str(x[0][1]),
                                                      str(x[0][2]))):
        seq = sorted(set(pr["seq"]))
        # l'ultima riga ``stato`` dice quale numero avrebbe avuto il prossimo
        # record: i record scartati DOPO l'ultimo scritto si vedono cosi'
        ultimo = max(seq[-1] if seq else 0,
                     int((pr["stato"] or {}).get("seq_prossimo") or 1) - 1)
        mancanti = ultimo - len(seq)
        ep = sorted(pr["epoca"])
        sil = buchi(ep, SOGLIA_SILENZIO_CANALE_S * 1000.0)
        res.append({"porta": porta, "pid": pid, "av": av, "sport": pr["sport"],
                    "chiuso": pr["chiuso"], "file": sorted(pr["file"]), "record": len(seq),
                    "seq_mancanti": mancanti, "conti": pr["stato"],
                    "tetto_raggiunto": pr["tetto"], "prima": ep[0] if ep else None,
                    "ultima": ep[-1] if ep else None,
                    "silenzi": sorted(sil, key=lambda x: x[0] - x[1])[:MAX_ELENCO],
                    "n_silenzi": len(sil)})
    return res


def _msg(r: Dict[str, Any]) -> Dict[str, Any]:
    m = r.get("msg")
    return m if isinstance(m, dict) else {}


def _par(r: Dict[str, Any]) -> Dict[str, Any]:
    """I parametri del comando: ``p`` (desktop, ``/order``) o ``d`` (``/comando/``)."""
    m = _msg(r)
    p = m.get("d") if r.get("genere") == "comando" else m.get("p")
    return p if isinstance(p, dict) else {}


def _modo(r: Dict[str, Any]) -> str:
    """paper / live del comando (``-`` se non lo dice): paper e live MAI sommati."""
    v = _par(r).get("mode")
    return str(v).lower() if v not in (None, "") else "-"


def _metodo(r: Dict[str, Any]) -> str:
    m = r.get("msg")
    if not isinstance(m, dict):
        return "<illeggibile>"
    p = _par(r)
    if r.get("genere") == "comando":
        az = p.get("azione")
        return "comando:%s%s" % (m.get("t") or "?", (":%s" % az) if az else "")
    az = p.get("action")
    return "%s%s" % (m.get("m") or "?", (":%s" % az) if az else "")


def _accoppia_comandi(comandi: List[Dict[str, Any]],
                      risposte: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Ogni comando ricevuto con la PRIMA risposta che lo riguarda arrivata DOPO
    di lui e non gia' usata: per ``id`` sulla stessa CONNESSIONE (``/order``,
    sveglia, board_mercato, rifiuti) o per ``ref`` nell'ack del motore
    (``/comando/``). La connessione e' (porta, pid, avvio, numero del client):
    i numeri dei client non si riusano."""
    per_id: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    per_ref: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    for t in sorted(risposte, key=lambda x: x.get("mono_ns", 0)):
        m = _msg(t)
        vita = (t.get("porta"), t.get("pid"), t.get("av"))
        if "id" in m:
            per_id.setdefault(vita + (t.get("cliente"), m.get("id")), []).append(t)
        d = m.get("d") if isinstance(m.get("d"), dict) else {}
        if m.get("t") == "ack" and d.get("ref") is not None:
            per_ref.setdefault(vita + (d.get("ref"),), []).append(t)
    usate: set = set()
    righe: Dict[Tuple[Any, str, str, str], Dict[str, Any]] = {}
    senza: List[Dict[str, Any]] = []
    motivi: Dict[str, int] = {}
    for c in sorted(comandi, key=lambda x: x.get("mono_ns", 0)):
        m = _msg(c)
        vita = (c.get("porta"), c.get("pid"), c.get("av"))
        cand: List[Dict[str, Any]] = []
        if c.get("genere") == "comando":
            d = m.get("d") if isinstance(m.get("d"), dict) else {}
            cand = per_ref.get(vita + (d.get("ref"),), [])
        elif "id" in m:
            cand = per_id.get(vita + (c.get("cliente"), m.get("id")), [])
        esito = next((t for t in cand if id(t) not in usate
                      and t.get("mono_ns", 0) >= c.get("mono_ns", 0)), None)
        chiave = (c.get("porta"), str(c.get("genere")), _metodo(c), _modo(c))
        r = righe.setdefault(chiave, {"porta": chiave[0], "genere": chiave[1],
                                      "metodo": chiave[2], "modo": chiave[3], "n": 0, "ok": 0,
                                      "rifiutati": 0, "senza_esito": 0, "lat": []})
        r["n"] += 1
        if esito is None:
            r["senza_esito"] += 1
            if len(senza) < MAX_ELENCO:
                senza.append({"porta": c.get("porta"), "quando": c.get("epoca_ms"),
                              "metodo": chiave[2], "genere": chiave[1], "modo": chiave[3]})
            continue
        usate.add(id(esito))
        r["lat"].append((esito["mono_ns"] - c["mono_ns"]) / 1e6)
        em = _msg(esito)
        ed = em.get("d") if isinstance(em.get("d"), dict) else {}
        ok = bool(ed.get("accettato")) if em.get("t") == "ack" else bool(em.get("ok"))
        if ok:
            r["ok"] += 1
        else:
            r["rifiutati"] += 1
            motivo = str(ed.get("motivo") if em.get("t") == "ack" else em.get("e"))[:120]
            motivi[motivo] = motivi.get(motivo, 0) + 1
    tab = []
    for k in sorted(righe, key=lambda x: (str(x[0]), x[1], x[2], x[3])):
        r = righe[k]
        lat = r.pop("lat")
        r.update({"lat_p50": percentile(lat, 50), "lat_p95": percentile(lat, 95),
                  "lat_max": max(lat) if lat else None})
        tab.append(r)
    return {"tabella": tab, "senza_esito": senza,
            "motivi_rifiuto": sorted(motivi.items(), key=lambda x: (-x[1], x[0]))[:MAX_ELENCO]}


# ---------------------------------------------------------------------------
# 2. raw dei prezzi
# ---------------------------------------------------------------------------
def analizza_raw(cartella: Optional[Path], giorno: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"fonte": "raw", "cartella": _rel(cartella), "eventi": [],
                           "mancante": None}
    if cartella is None:
        out["mancante"] = "cartella non indicata"
        return out
    base = Path(cartella)
    if not base.is_dir():
        out["mancante"] = "cartella %s assente" % _rel(base)
        return out
    a, b = limiti_giorno(giorno)
    trovati = 0
    for ev in sorted(p for p in base.iterdir() if p.is_dir()):
        for f in sorted(ev.glob("*.raw.jsonl*")):
            if not (f.name.endswith(".raw.jsonl") or f.name.endswith(".raw.jsonl.gz")):
                continue
            try:
                if f.stat().st_mtime * 1000 < a:
                    continue          # non toccato quel giorno
            except OSError:
                continue
            trovati += 1
            r = _analizza_un_raw(f, a, b)
            if r["messaggi"]:
                r["evento"] = ev.name
                r["recmeta"] = _conta_recmeta(ev, ev.name, a, b)
                out["eventi"].append(r)
    if not trovati:
        out["mancante"] = "nessun file raw toccato il %s in %s" % (giorno, _rel(base))
    elif not out["eventi"]:
        out["mancante"] = "%d file raw toccati ma nessun messaggio con pt nel giorno" % trovati
    return out


def _analizza_un_raw(f: Path, a: int, b: int) -> Dict[str, Any]:
    pts: List[float] = []
    eta: List[float] = []
    byte = hb = 0
    errore = None
    testi, problema = righe_testo(f)
    if problema:
        errore = problema
    for linea in testi:
        m = _RE_PT.search(linea)
        if not m:
            continue
        pt = int(m.group(1))
        if not (a <= pt < b):
            continue
        pts.append(float(pt))
        byte += len(linea) + 1
        if _RE_HEARTBEAT.search(linea):
            hb += 1
        mr = _RE_RX.search(linea)
        if mr:
            eta.append(float(int(mr.group(1)) - pt))
    pts.sort()
    durata = (pts[-1] - pts[0]) / 1000.0 if len(pts) > 1 else 0.0
    bh = buchi(pts, SOGLIA_BUCO_RAW_S * 1000.0)
    return {"file": f.name, "messaggi": len(pts), "byte": byte, "heartbeat": hb,
            "prima": pts[0] if pts else None, "ultima": pts[-1] if pts else None,
            "byte_s": byte / durata if durata > 0 else None, **{
                "cad_" + k: v for k, v in cadenza_ms(pts).items()},
            "eta_p50": percentile(eta, 50), "eta_p95": percentile(eta, 95),
            "n_buchi": len(bh), "buco_max_s": max((y - x for x, y in bh), default=0) / 1000.0,
            "errore": errore}


def _conta_recmeta(ev: Path, nome: str, a: int, b: int) -> Dict[str, int]:
    p = ev / ("%s.recmeta.jsonl" % nome)
    conti: Dict[str, int] = {}
    if not p.exists():
        return conti
    righe, _ = leggi_jsonl(p)
    for r in righe:
        ts = r.get("ts_ms")
        if isinstance(ts, (int, float)) and a <= ts < b:
            k = str(r.get("kind"))
            conti[k] = conti.get(k, 0) + 1
    return dict(sorted(conti.items()))


# ---------------------------------------------------------------------------
# 3. righe di Salute
# ---------------------------------------------------------------------------
def _ms_da_iso(v: Any) -> Optional[float]:
    if not isinstance(v, str):
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp() * 1000.0
    except ValueError:
        return None


def analizza_salute(cartella: Optional[Path], giorno: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"fonte": "salute", "cartella": _rel(cartella), "servizi": [],
                           "mancante": None}
    if cartella is None:
        out["mancante"] = "cartella non indicata"
        return out
    d = Path(cartella) / giorno
    files = sorted(d.glob("*.jsonl")) if d.is_dir() else []
    if not files:
        out["mancante"] = ("nessuna riga di Salute in %s (MONITOR_SALUTE spento quel "
                           "giorno?)" % _rel(d))
        return out
    for f in files:
        righe, errore = leggi_jsonl(f)
        ts = sorted(t for t in (_ms_da_iso(r.get("ts")) for r in righe) if t is not None)
        fin = [float((r.get("metriche") or {}).get("finestra_s") or 30.0) for r in righe]
        finestra = percentile(fin, 50) or 30.0
        bh = buchi(ts, FATTORE_BUCO_SALUTE * finestra * 1000.0)
        cpu = [float(r["cpu_pct"]) for r in righe if isinstance(r.get("cpu_pct"), (int, float))]
        rss = [float(r["rss_mb"]) for r in righe if isinstance(r.get("rss_mb"), (int, float))]
        out["servizi"].append({
            "servizio": f.stem, "righe": len(righe), "errore": errore,
            "prima": ts[0] if ts else None, "ultima": ts[-1] if ts else None,
            "finestra_s": finestra, "n_buchi": len(bh),
            "buco_max_s": max((y - x for x, y in bh), default=0) / 1000.0,
            "cpu_p50": percentile(cpu, 50), "cpu_p95": percentile(cpu, 95),
            "rss_max": max(rss) if rss else None,
            "db": sum(int(r.get("db_richieste") or 0) for r in righe),
            "rest": sum(int(r.get("rest_richieste") or 0) for r in righe)})
    return out


# ---------------------------------------------------------------------------
# 4. file di M-1 (stream ordini e REST): interfaccia generica
# ---------------------------------------------------------------------------
def _tempo(r: Dict[str, Any]) -> Optional[float]:
    """Istante in ms di una riga di M-1 (``ep_us`` in microsecondi) o, per altri
    formati, la prima chiave in ms fra ``_CHIAVI_TEMPO`` o ``ts`` ISO."""
    v = r.get("ep_us")
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
        return float(v) / 1000.0
    for k in _CHIAVI_TEMPO:
        v = r.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 1e11:
            return float(v)
    return _ms_da_iso(r.get("ts"))


def _genere_riga(r: Dict[str, Any]) -> str:
    for k in _CHIAVI_GENERE:
        v = r.get(k)
        if isinstance(v, str) and v:
            return v[:60]
    return "?"


def cartelle_utc(giorno: str) -> List[str]:
    """Le cartelle ``AAAAMMGG`` (UTC) di M-1 che coprono il giorno LOCALE: di
    solito due (in Italia il giorno locale comincia alle 22 o alle 23 UTC del
    giorno prima)."""
    a, b = limiti_giorno(giorno)
    prima = datetime.fromtimestamp(a / 1000.0, tz=timezone.utc).date()
    ultima = datetime.fromtimestamp((b - 1) / 1000.0, tz=timezone.utc).date()
    out = []
    g = prima
    while g <= ultima:
        out.append(g.strftime("%Y%m%d"))
        g += timedelta(days=1)
    return out


def file_ordini(base: Path, giorno: str) -> List[Path]:
    """I file di M-1 del giorno locale: glob RICORSIVO ``ordini_*.jsonl*`` sotto
    ``base``, nelle cartelle UTC che coprono il giorno (o direttamente in
    ``base`` se gli si passa gia' la cartella di un giorno)."""
    utc = set(cartelle_utc(giorno))
    out = []
    for f in sorted(base.rglob("ordini_*.jsonl*")):
        if not (f.name.endswith(".jsonl") or f.name.endswith(".jsonl.gz")):
            continue
        cartelle = {p.name for p in f.relative_to(base).parents}
        if f.parent == base or cartelle & utc or base.name in utc:
            out.append(f)
    return out


def lettore_m1() -> Any:
    """Il lettore di M-1 (``Betfair.monitor.analisi_ordini``: ``leggi_file``
    tollerante, ``analizza_giorni``, ``formatta``) se c'e' nel processo, o
    ``None``. Import OPZIONALE: senza, la mappa usa il suo lettore e lo dice."""
    try:
        import importlib

        m = importlib.import_module("Betfair.monitor.analisi_ordini")
    except Exception:  # noqa: BLE001 - M-1 non (ancora) in questo ramo
        return None
    if not all(hasattr(m, n) for n in ("leggi_file", "analizza_giorni", "formatta")):
        return None
    return m


def _leggi_ordini(f: Path, m1: Any) -> Tuple[List[Dict[str, Any]], Optional[str], bool]:
    """(righe, problema, chiuso) di un file di M-1: col lettore di M-1 se c'e'
    (``leggi_file`` -> righe e info con ``troncato``/``rotte``/``chiusura``),
    altrimenti col lettore tollerante della mappa."""
    if m1 is not None:
        try:
            righe, info = m1.leggi_file(str(f))
            prob = []
            if info.get("troncato"):
                prob.append("coda tronca o membro corrotto")
            if info.get("rotte"):
                prob.append("%d righe illeggibili" % info["rotte"])
            return righe, ("; ".join(prob) or None), info.get("chiusura") is not None
        except Exception as e:  # noqa: BLE001 - lettore di M-1 cambiato: si ripiega
            righe, errore = leggi_jsonl(f)
            errore = "lettore di M-1 fallito (%s), letto dalla mappa%s" % (
                type(e).__name__, ("; " + errore) if errore else "")
            return righe, errore, any(r.get("k") == "chiusura" for r in righe)
    righe, errore = leggi_jsonl(f)
    return righe, errore, any(r.get("k") == "chiusura" for r in righe)


def analizza_ordini(cartella: Optional[Path], giorno: str) -> Dict[str, Any]:
    m1 = lettore_m1()
    out: Dict[str, Any] = {"fonte": "ordini (M-1)", "cartella": _rel(cartella), "file": [],
                           "rest": [], "mancante": None, "cartelle_utc": cartelle_utc(giorno),
                           "_rest": [], "lettore": "M-1" if m1 is not None else
                           "lettore M-1 assente: file letti dal lettore tollerante della mappa"}
    if cartella is None:
        out["mancante"] = "cartella non indicata (--ordini): i file di M-1 non sono letti"
        return out
    base = Path(cartella)
    if not base.is_dir():
        out["mancante"] = "cartella %s assente" % _rel(base)
        return out
    files = file_ordini(base, giorno)
    if not files:
        out["mancante"] = "nessun ordini_*.jsonl[.gz] nelle cartelle UTC %s di %s" % (
            ", ".join(cartelle_utc(giorno)), _rel(base))
        return out
    a, b = limiti_giorno(giorno)
    rest: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for f in files:
        righe, errore, chiuso = _leggi_ordini(f, m1)
        generi: Dict[str, List[float]] = {}
        senza_tempo = 0
        for r in righe:
            t = _tempo(r)
            if t is None:
                senza_tempo += 1
                continue
            if not (a <= t < b):
                continue
            genere = _genere_riga(r)
            if genere == "dec":
                # decisioni: paper e live MAI sommati
                genere = "dec:%s" % (str(r.get("mode") or "-").lower())
            generi.setdefault(genere, []).append(t)
            if r.get("k") == "rest":
                metodo, attore = str(r.get("metodo") or "?"), str(r.get("attore") or "?")
                v = rest.setdefault((metodo, attore), {"n": 0, "errori": 0, "durate": []})
                v["n"] += 1
                if r.get("errore") or r.get("eccezione"):
                    v["errori"] += 1
                rep_us = r.get("risposta_ep_us")
                if isinstance(rep_us, (int, float)) and isinstance(r.get("ep_us"), (int, float)):
                    v["durate"].append((rep_us - r["ep_us"]) / 1000.0)
                    out["_rest"].append({"invio_ms": r["ep_us"] / 1000.0,
                                         "risposta_ms": rep_us / 1000.0, "metodo": metodo,
                                         "attore": attore})
        tab = []
        for g, ts in sorted(generi.items()):
            ts.sort()
            bh = buchi(ts, SOGLIA_BUCO_ORDINI_S * 1000.0)
            tab.append({"genere": g, "n": len(ts), **{"cad_" + k: v for k, v in
                                                      cadenza_ms(ts).items()},
                        "prima": ts[0], "ultima": ts[-1], "n_buchi": len(bh)})
        out["file"].append({"nome": str(f.relative_to(base)).replace(os.sep, "/"),
                            "righe": len(righe), "errore": errore,
                            "senza_tempo": senza_tempo, "chiuso": chiuso, "generi": tab})
    for (metodo, attore), v in sorted(rest.items()):
        d = v["durate"]
        out["rest"].append({"metodo": metodo, "attore": attore, "n": v["n"],
                            "errori": v["errori"], "p50": percentile(d, 50),
                            "p95": percentile(d, 95), "p99": percentile(d, 99),
                            "max": max(d) if d else None})
    out["_rest"].sort(key=lambda x: x["invio_ms"])
    return out


def ui_verso_rest(ordini_ui: List[Dict[str, Any]], rest: List[Dict[str, Any]]
                  ) -> Dict[str, Any]:
    """Latenza comando della UI (ricezione sul canale) -> risposta della REST di
    Betfair (``risposta_ep_us`` di M-1). Accoppiamento per TEMPO: il comando
    LIVE del desktop con la prima REST del desktop dello stesso metodo partita
    dopo di lui entro ``FINESTRA_UI_REST_S``, mai usata due volte. I comandi
    paper non vanno a Betfair: non si accoppiano."""
    usate: set = set()
    per: Dict[str, Dict[str, Any]] = {}
    for c in ordini_ui:
        if c.get("modo") != "live" or c.get("epoca_ms") is None:
            continue
        metodo = _AZIONE_REST.get(str(c.get("azione") or ""))
        if metodo is None:
            continue
        v = per.setdefault(metodo, {"metodo": metodo, "comandi": 0, "accoppiati": 0,
                                    "invio": [], "risposta": []})
        v["comandi"] += 1
        t0 = float(c["epoca_ms"])
        for i, r in enumerate(rest):
            if i in usate or r["metodo"] != metodo or not str(r["attore"]).startswith("desktop"):
                continue
            if r["invio_ms"] < t0:
                continue
            if r["invio_ms"] - t0 > FINESTRA_UI_REST_S * 1000.0:
                break
            usate.add(i)
            v["accoppiati"] += 1
            v["invio"].append(r["invio_ms"] - t0)
            v["risposta"].append(r["risposta_ms"] - t0)
            break
    tab = []
    for metodo in sorted(per):
        v = per[metodo]
        tab.append({"metodo": metodo, "comandi": v["comandi"], "accoppiati": v["accoppiati"],
                    "invio_p50": percentile(v["invio"], 50),
                    "risposta_p50": percentile(v["risposta"], 50),
                    "risposta_p95": percentile(v["risposta"], 95),
                    "risposta_max": max(v["risposta"]) if v["risposta"] else None})
    return {"tabella": tab}


def referto_m1(cartella: Optional[Path], giorno: str) -> Optional[str]:
    """Il referto del lettore di M-1 (``analizza_giorni`` sulle cartelle UTC
    del giorno INSIEME: gli ordini a cavallo della mezzanotte UTC restano
    interi), se il modulo c'e'. ``None`` se non c'e'; il testo dell'errore se
    c'e' ma fallisce (mai solleva). Attenzione: copre le cartelle UTC intere,
    non solo il giorno locale."""
    if cartella is None or not Path(cartella).is_dir():
        return None
    m1 = lettore_m1()
    if m1 is None:
        return None
    giorni = [g for g in cartelle_utc(giorno) if (Path(cartella) / g).is_dir()]
    if not giorni:
        return None
    try:
        return "cartelle UTC %s (intere)\n%s" % (", ".join(giorni), m1.formatta(
            m1.analizza_giorni(str(cartella), giorni)))
    except Exception as e:  # noqa: BLE001
        return "lettore di M-1 fallito: %s: %s" % (type(e).__name__, str(e)[:200])


# ---------------------------------------------------------------------------
# referto
# ---------------------------------------------------------------------------
def genera(giorno: str, *, canale: Optional[Path] = None, raw: Optional[Path] = None,
           salute: Optional[Path] = None, ordini: Optional[Path] = None) -> Dict[str, Any]:
    datetime.strptime(giorno, "%Y-%m-%d")
    c = analizza_canale(canale, giorno)
    o = analizza_ordini(ordini, giorno)
    o["ui_rest"] = ui_verso_rest(c.pop("_ordini_ui", []), o.pop("_rest", []))
    o["referto_m1"] = referto_m1(ordini, giorno)
    return {"giorno": giorno, "fuso": NOME_FUSO, "canale": c,
            "raw": analizza_raw(raw, giorno),
            "salute": analizza_salute(salute, giorno), "ordini": o}


def markdown(dati: Dict[str, Any], comando: str = "") -> str:
    L: List[str] = []
    g = dati["giorno"]
    L.append("# Mappa dei flussi reali - %s" % g)
    L.append("")
    L.append("Generata da `Betfair/stream/mappa_flussi.py` (M-3). Orari in %s. "
             "Stessi file = stesso referto." % dati["fuso"])
    if comando:
        L.append("")
        L.append("Comando: `%s`" % comando)
    L.append("")
    L.append("## 0. Fonti lette e fonti mancanti")
    L.append("")
    L.append("| fonte | cartella | stato |")
    L.append("|---|---|---|")
    for k in ("canale", "raw", "salute", "ordini"):
        s = dati[k]
        if s["mancante"]:
            stato = "MANCA: " + s["mancante"]
        elif k == "canale":
            stato = "letta: %d file" % len(s["file"])
        elif k == "raw":
            stato = "letta: %d eventi" % len(s["eventi"])
        elif k == "salute":
            stato = "letta: %d servizi" % len(s["servizi"])
        else:
            stato = "letta: %d file" % len(s["file"])
        L.append("| %s | `%s` | %s |" % (s["fonte"], s["cartella"], stato))
    L.append("")
    _md_canale(L, dati["canale"])
    _md_raw(L, dati["raw"])
    _md_salute(L, dati["salute"])
    _md_ordini(L, dati["ordini"])
    _md_buchi(L, dati)
    return "\n".join(L) + "\n"


def _md_canale(L: List[str], c: Dict[str, Any]) -> None:
    L.append("## 1. Canale locale: chi pubblica, chi riceve, con quale cadenza")
    L.append("")
    if c["mancante"]:
        L.append("Non disponibile: %s." % c["mancante"])
        L.append("")
        return
    L.append("Cadenza = tempo fra due publish consecutivi dello stesso topic nello stesso "
             "processo (orologio monotono), in ms. `dest` = client che ricevono il giro; "
             "`saltati` = invii tolti a client oltre il tetto degli invii in volo.")
    L.append("")
    L.append("| porta | sport | topic | msg | msg/s | byte/s | cad p50 | p95 | p99 | dest p50 "
             "| dest max | client max | lettori max | con payload | saltati | dalle | alle |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for t in c["topic"]:
        L.append("| %s | %s | %s | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %d | %d "
                 "| %s | %s |" % (
                     t["porta"], t["sport"], t["topic"], t["n"], _f(t["msg_s"], 2),
                     _f(t["byte_s"], 0), _f(t["cad_p50"]), _f(t["cad_p95"]), _f(t["cad_p99"]),
                     _f(t["dest_p50"], 0), t["dest_max"], t["client_max"], t["lettori_max"],
                     t["con_payload"], t["saltati"], ora(t["prima"]), ora(t["ultima"])))
    L.append("")
    L.append("### 1.0 Chi e' collegato (chi riceve)")
    L.append("")
    if not c.get("collegati"):
        L.append("Nessuna composizione dei client registrata.")
    else:
        L.append("Dalle composizioni scritte a ogni cambio dei client collegati. `desktop` = "
                 "UI (o client senza percorso); `lettore` = topic dichiarati; `comando` = attore.")
        L.append("")
        L.append("| porta | genere | chi | max insieme | composizioni | visto dalle |")
        L.append("|---|---|---|---|---|---|")
        for v in c["collegati"]:
            L.append("| %s | %s | %s | %d | %d | %s |" % (
                v["porta"], v["genere"], v["chi"], v["max_insieme"], v["cambi"],
                ora(v["visto_dalle"])))
    L.append("")
    L.append("### 1.1 Client saltati e giri saltati")
    L.append("")
    con = [t for t in c["topic"] if t["saltati"]]
    if not con and not c["giri_saltati"]:
        L.append("Nessun client saltato e nessun giro saltato.")
    for t in con:
        L.append("- porta %s, `%s`: %d invii saltati in %d giri su %d." % (
            t["porta"], t["topic"], t["saltati"], t["giri_con_saltati"], t["n"]))
    for s in c["giri_saltati"]:
        L.append("- porta %s, `%s`: %d giri saltati PER INTERO (nessun client pronto), "
                 "dalle %s alle %s." % (s["porta"], s["topic"], s["n"], ora(s["prima"]),
                                       ora(s["ultima"])))
    L.append("")
    L.append("### 1.2 Comandi ricevuti e loro esito")
    L.append("")
    cm = c["comandi"]
    if not cm["tabella"]:
        L.append("Nessun comando ricevuto sul canale.")
    else:
        L.append("Latenza = dalla ricezione sul canale alla risposta (ms).")
        L.append("")
        L.append("Paper e live su righe SEPARATE (colonna modo), mai sommati.")
        L.append("")
        L.append("| porta | client | metodo | modo | n | ok | rifiutati | senza esito | "
                 "lat p50 | p95 | max |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in cm["tabella"]:
            L.append("| %s | %s | %s | %s | %d | %d | %d | %d | %s | %s | %s |" % (
                r["porta"], r["genere"], r["metodo"], r["modo"], r["n"], r["ok"],
                r["rifiutati"],
                r["senza_esito"], _f(r["lat_p50"], 2), _f(r["lat_p95"], 2),
                _f(r["lat_max"], 2)))
        if cm["motivi_rifiuto"]:
            L.append("")
            L.append("Motivi di rifiuto:")
            for m, n in cm["motivi_rifiuto"]:
                L.append("- %d x %s" % (n, m.replace("|", "/")))
        if cm["senza_esito"]:
            L.append("")
            L.append("Comandi senza esito registrato (primi %d):" % MAX_ELENCO)
            for s in cm["senza_esito"]:
                L.append("- %s porta %s %s %s (%s)" % (ora(s["quando"]), s["porta"],
                                                       s["metodo"], s["modo"], s["genere"]))
    L.append("")


def _md_raw(L: List[str], r: Dict[str, Any]) -> None:
    L.append("## 2. Stream dei prezzi (raw registrato)")
    L.append("")
    if r["mancante"]:
        L.append("Non disponibile: %s." % r["mancante"])
        L.append("")
        return
    L.append("Cadenza fra messaggi sul `pt` di Betfair (ms); eta' = `rx - pt` se il "
             "monitor l'ha scritto; buco = nessun messaggio per oltre %.0f s." % SOGLIA_BUCO_RAW_S)
    L.append("")
    L.append("| evento | msg | heartbeat | byte/s | cad p50 | p95 | p99 | max | eta p50 | "
             "eta p95 | buchi | buco max s | recmeta | dalle | alle |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for e in r["eventi"]:
        meta = ", ".join("%s=%d" % kv for kv in e["recmeta"].items()) or "-"
        L.append("| %s | %d | %d | %s | %s | %s | %s | %s | %s | %s | %d | %s | %s | %s | %s |"
                 % (e["evento"], e["messaggi"], e["heartbeat"], _f(e["byte_s"], 0),
                    _f(e["cad_p50"]), _f(e["cad_p95"]), _f(e["cad_p99"]), _f(e["cad_max"]),
                    _f(e["eta_p50"]), _f(e["eta_p95"]), e["n_buchi"], _f(e["buco_max_s"]),
                    meta, ora(e["prima"]), ora(e["ultima"])))
    L.append("")


def _md_salute(L: List[str], s: Dict[str, Any]) -> None:
    L.append("## 3. Processi (righe di Salute)")
    L.append("")
    if s["mancante"]:
        L.append("Non disponibile: %s." % s["mancante"])
        L.append("")
        return
    L.append("| servizio | righe | finestra s | cpu p50 | cpu p95 | rss max MB | richieste DB "
             "| REST Betfair | buchi | buco max s | dalle | alle |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for v in s["servizi"]:
        L.append("| %s | %d | %s | %s | %s | %s | %d | %d | %d | %s | %s | %s |" % (
            v["servizio"], v["righe"], _f(v["finestra_s"], 0), _f(v["cpu_p50"]),
            _f(v["cpu_p95"]), _f(v["rss_max"]), v["db"], v["rest"], v["n_buchi"],
            _f(v["buco_max_s"]), ora(v["prima"]), ora(v["ultima"])))
    L.append("")


def _md_ordini(L: List[str], o: Dict[str, Any]) -> None:
    L.append("## 4. Stream ordini e REST (file di M-1)")
    L.append("")
    if o["mancante"]:
        L.append("Non disponibile: %s." % o["mancante"])
        L.append("")
        return
    if o.get("lettore") != "M-1":
        L.append("ordini: lettore M-1 assente (``Betfair.monitor.analisi_ordini`` non c'e' in "
                 "questo ramo): niente referto di M-1, i file sono letti dalla mappa.")
        L.append("")
    L.append("Cartelle UTC lette per il giorno locale: %s (righe filtrate sul giorno "
             "locale). Lettore: %s." % (", ".join(o["cartelle_utc"]), o.get("lettore")))
    L.append("")
    L.append("| file | genere | n | cad p50 ms | p95 | p99 | max | buchi > %.0f s | dalle | alle |"
             % SOGLIA_BUCO_ORDINI_S)
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for f in o["file"]:
        for g in f["generi"]:
            L.append("| %s | %s | %d | %s | %s | %s | %s | %d | %s | %s |" % (
                f["nome"], g["genere"], g["n"], _f(g["cad_p50"]), _f(g["cad_p95"]),
                _f(g["cad_p99"]), _f(g["cad_max"]), g["n_buchi"], ora(g["prima"]),
                ora(g["ultima"])))
        if f["senza_tempo"]:
            L.append("| %s | (righe senza istante) | %d | | | | | | | |" % (
                f["nome"], f["senza_tempo"]))
    L.append("")
    L.append("### 4.1 REST con soldi: durata invio -> risposta (ms)")
    L.append("")
    if not o["rest"]:
        L.append("Nessuna REST registrata nel giorno.")
    else:
        L.append("| metodo | attore | n | errori | p50 | p95 | p99 | max |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in o["rest"]:
            L.append("| %s | %s | %d | %d | %s | %s | %s | %s |" % (
                r["metodo"], r["attore"], r["n"], r["errori"], _f(r["p50"]), _f(r["p95"]),
                _f(r["p99"]), _f(r["max"])))
    L.append("")
    L.append("### 4.2 Comando della UI sul canale -> REST di Betfair (ms)")
    L.append("")
    tab = (o.get("ui_rest") or {}).get("tabella") or []
    if not tab:
        L.append("Nessun comando LIVE della UI accoppiabile (servono canale e M-1 dello "
                 "stesso giorno).")
    else:
        L.append("Accoppiamento per tempo: il comando LIVE del desktop con la prima REST del "
                 "desktop dello stesso metodo entro %.0f s." % FINESTRA_UI_REST_S)
        L.append("")
        L.append("| metodo | comandi | accoppiati | invio p50 | risposta p50 | risposta p95 "
                 "| risposta max |")
        L.append("|---|---|---|---|---|---|---|")
        for r in tab:
            L.append("| %s | %d | %d | %s | %s | %s | %s |" % (
                r["metodo"], r["comandi"], r["accoppiati"], _f(r["invio_p50"]),
                _f(r["risposta_p50"]), _f(r["risposta_p95"]), _f(r["risposta_max"])))
    L.append("")
    if o.get("referto_m1"):
        L.append("### 4.3 Referto del lettore di M-1")
        L.append("")
        L.append("```")
        L.append(str(o["referto_m1"]))
        L.append("```")
        L.append("")


def _md_buchi(L: List[str], dati: Dict[str, Any]) -> None:
    L.append("## 5. Buchi")
    L.append("")
    righe: List[str] = []
    c = dati["canale"]
    if not c["mancante"]:
        for f in c["file"]:
            if f["errore"]:
                righe.append("- canale `%s`: %s." % (f["nome"], f["errore"]))
        porte: Dict[Any, int] = {}  # processi diversi per porta
        for p in c["processi"]:
            porte[p["porta"]] = porte.get(p["porta"], 0) + 1
            if p["seq_mancanti"]:
                righe.append("- canale porta %s (pid %s): %d record mancanti nella sequenza "
                             "(scartati a coda piena o file troncato)." % (
                                 p["porta"], p["pid"], p["seq_mancanti"]))
            conti = p["conti"] or {}
            for k in ("scartati_coda", "scartati_tetto", "errori_disco", "errori_aggancio"):
                if conti.get(k):
                    righe.append("- canale porta %s (pid %s): %s = %d." % (
                        p["porta"], p["pid"], k, conti[k]))
            if not p.get("chiuso"):
                righe.append("- canale porta %s (pid %s): nessuna riga di chiusura (processo "
                             "morto, ucciso o ancora vivo alla lettura)." % (p["porta"], p["pid"]))
            for t in p["tetto_raggiunto"]:
                righe.append("- canale porta %s: TETTO raggiunto alle %s, registrazione "
                             "sospesa per il resto del giorno." % (p["porta"], ora(t)))
            if p["n_silenzi"]:
                peggiore = p["silenzi"][0]
                righe.append("- canale porta %s (pid %s): %d silenzi > %.0f s (il piu' lungo "
                             "%.0f s, dalle %s alle %s)." % (
                                 p["porta"], p["pid"], p["n_silenzi"], SOGLIA_SILENZIO_CANALE_S,
                                 (peggiore[1] - peggiore[0]) / 1000.0, ora(peggiore[0]),
                                 ora(peggiore[1])))
        for porta, n in sorted(porte.items(), key=lambda x: str(x[0])):
            if n > 1:
                righe.append("- canale porta %s: %d processi diversi nel giorno (riavvii)." % (
                    porta, n))
    r = dati["raw"]
    if not r["mancante"]:
        for e in r["eventi"]:
            if e["n_buchi"]:
                righe.append("- raw evento %s: %d buchi > %.0f s (max %.0f s)." % (
                    e["evento"], e["n_buchi"], SOGLIA_BUCO_RAW_S, e["buco_max_s"]))
            if e["errore"]:
                righe.append("- raw evento %s: %s." % (e["evento"], e["errore"]))
    s = dati["salute"]
    if not s["mancante"]:
        for v in s["servizi"]:
            if v["n_buchi"]:
                righe.append("- salute %s: %d buchi (max %.0f s)." % (
                    v["servizio"], v["n_buchi"], v["buco_max_s"]))
    o = dati["ordini"]
    if not o["mancante"]:
        for f in o["file"]:
            for g in f["generi"]:
                if g["n_buchi"]:
                    righe.append("- M-1 %s/%s: %d buchi > %.0f s." % (
                        f["nome"], g["genere"], g["n_buchi"], SOGLIA_BUCO_ORDINI_S))
            if f["errore"]:
                righe.append("- M-1 %s: %s." % (f["nome"], f["errore"]))
            if not f["chiuso"]:
                righe.append("- M-1 %s: nessuna riga di chiusura (processo morto o vivo)."
                             % f["nome"])
    for k in ("canale", "raw", "salute", "ordini"):
        if dati[k]["mancante"]:
            righe.append("- fonte `%s` MANCANTE: %s." % (dati[k]["fonte"], dati[k]["mancante"]))
    L.extend(righe or ["Nessun buco rilevato nelle fonti lette."])
    L.append("")


def _json_stabile(dati: Dict[str, Any]) -> str:
    return json.dumps(dati, sort_keys=True, indent=1, ensure_ascii=True, default=str) + "\n"


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Mappa dei flussi reali di una giornata (M-3)")
    ap.add_argument("--giorno", required=True, help="AAAA-MM-GG")
    ap.add_argument("--canale", default=str(RADICE / "_logs" / "canale"))
    ap.add_argument("--raw", default=str(RADICE / "_live_raw"))
    ap.add_argument("--salute", default=str(RADICE / "_logs" / "monitor"))
    ap.add_argument("--ordini", default=None, help="cartella dei file di M-1 (facoltativa)")
    ap.add_argument("--uscita", default=None, help="file .md (altrimenti a video)")
    ap.add_argument("--json", default=None, help="file .json con i numeri")
    a = ap.parse_args(list(argv) if argv is not None else None)
    dati = genera(a.giorno, canale=Path(a.canale) if a.canale else None,
                  raw=Path(a.raw) if a.raw else None,
                  salute=Path(a.salute) if a.salute else None,
                  ordini=Path(a.ordini) if a.ordini else None)
    comando = "python -m Betfair.stream.mappa_flussi --giorno %s --canale %s --raw %s " \
              "--salute %s%s" % (a.giorno, _rel(Path(a.canale)), _rel(Path(a.raw)),
                                 _rel(Path(a.salute)),
                                 (" --ordini %s" % _rel(Path(a.ordini))) if a.ordini else "")
    testo = markdown(dati, comando)
    if a.uscita:
        Path(a.uscita).parent.mkdir(parents=True, exist_ok=True)
        Path(a.uscita).write_text(testo, encoding="ascii", errors="replace")
    else:
        sys.stdout.write(testo)
    if a.json:
        Path(a.json).write_text(_json_stabile(dati), encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
