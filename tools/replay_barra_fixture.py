"""Fixture per il verificatore della barra di Match Replay (07/10/2026).

Dato l'ID di una partita registrata in `registrazioni_banco/<event>/` (raw dello
stream, punteggi, timeline Betfair) ricostruisce, SENZA database e SENZA rete, i
dati come li riceve la pagina Match Replay dal database:

  1. libro per mercato dallo stream grezzo (betfairlightweight, come il recorder:
     `Betfair.stream.recorder.serialize_book`) -> righe `{market_id, pt, runners,
     inplay, status}`;
  2. CURATOR VERO (`Betfair.stream.curator.curate_event`, cadenza 10 s, minuto dalla
     mappa del punteggio come `uploader.py::_read_scores`) = le righe di
     `live_market_snapshots`;
  3. estremi (`ts_min`, `ts_max`, `inplay_from_ts`) come `get_replay_meta`;
  4. campionamento del server (`get_replay_frames`: 1 frame per mercato e per bucket
     di N secondi, primo del bucket) con bucket e finestre calcolati come
     `frontend/src/lib/live.ts::fetchReplayChunked` (stesso codice, riportato qui);
  5. `score_timeline` = righe del punteggio + righe-evento della timeline Betfair
     (come `uploader.py::_read_timeline_events`: score null, event_type = tipo).

Il file prodotto sta in `frontend/src/lib/__fixtures__/replay_barra_<event>.json`
ed e' l'INGRESSO del test su tutte le partite
(`frontend/src/lib/replayVerificaBarra.partite.test.ts`). Per stare sotto 150 KB si
conservano tutti i frame del MATCH_ODDS (best back/lay) e, degli altri mercati, i
soli frame che DEFINISCONO la griglia della barra (marcati "fantasma"): provato
equivalente al completo (referto 07/10, REPLAY_BARRA_SIMBOLI.md par. 3).

Uso (dalla radice del repository, Python 3.13 con betfairlightweight):

    python3 tools/replay_barra_fixture.py 35797769            # scrive la fixture
    python3 tools/replay_barra_fixture.py --tutte             # tutte le partite in registrazioni_banco/
    python3 tools/replay_barra_fixture.py --tutte --verifica  # NON scrive: esce 1 se manca o e' diversa

Solo lettura dei file di registrazione; nessuna rete, nessun database. NON importa
`config_stream` (carica il `.env` vero): la cadenza e' la costante qui sotto, la
stessa di `UPLOAD_CADENCE_SEC`.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import queue
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RADICE not in sys.path:
    sys.path.insert(0, RADICE)

from Betfair.stream.curator import curate_event  # noqa: E402  (puro: path -> righe)

CARTELLA_REGISTRAZIONI = os.path.join(RADICE, "registrazioni_banco")
CARTELLA_FIXTURE = os.path.join(RADICE, "frontend", "src", "lib", "__fixtures__")
# = Betfair.stream.config_stream.UPLOAD_CADENCE_SEC (default); non lo si importa
# perche' quel modulo carica il .env vero.
CADENZA_CURATOR_SEC = 10.0
PROFONDITA_LADDER = 3  # = recorder.serialize_book(depth=3)

# ---- costanti di fetchReplayChunked (frontend/src/lib/live.ts) -----------------
REPLAY_TARGET_FRAMES = 9000
REPLAY_TARGET_PRE = 2500
WINDOW_MS = 10 * 60_000
FRAMES_PER_CALL = 10000
PRE_MATCH_MAX_MS = 4 * 3600_000
BUCKET_BARRA_MS = 10_000  # bucket della griglia della barra (MatchReplay.tsx)


def nome_fixture(event_id: str) -> str:
    return os.path.join(CARTELLA_FIXTURE, f"replay_barra_{event_id}.json")


def eventi_registrati() -> List[str]:
    """Ogni sottocartella di registrazioni_banco/ con un raw dello stream."""
    out: List[str] = []
    if not os.path.isdir(CARTELLA_REGISTRAZIONI):
        return out
    for nome in sorted(os.listdir(CARTELLA_REGISTRAZIONI)):
        d = os.path.join(CARTELLA_REGISTRAZIONI, nome)
        if os.path.isdir(d) and (
            os.path.exists(os.path.join(d, f"{nome}.raw.jsonl.gz"))
            or os.path.exists(os.path.join(d, f"{nome}.raw.jsonl"))
        ):
            out.append(nome)
    return out


def _apri_testo(path_base: str):
    """Apre `path_base` o `path_base.gz` come testo; None se non esiste."""
    if os.path.exists(path_base):
        return open(path_base, "r", encoding="utf-8")
    if os.path.exists(path_base + ".gz"):
        return gzip.open(path_base + ".gz", "rt", encoding="utf-8")
    return None


def _sha256_file(path: str) -> Optional[str]:
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blocco in iter(lambda: fh.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


def impronte_sorgente(event_id: str) -> Dict[str, Optional[str]]:
    """sha256 dei file di registrazione cosi' come stanno nel repository."""
    d = os.path.join(CARTELLA_REGISTRAZIONI, event_id)
    out: Dict[str, Optional[str]] = {}
    for nome in (f"{event_id}.raw.jsonl", f"{event_id}.scores.jsonl", f"{event_id}.timeline.jsonl"):
        p = os.path.join(d, nome)
        out[nome] = _sha256_file(p) or _sha256_file(p + ".gz")
    return out


# --------------------------------------------------------------------------------
# 1. libro per mercato dallo stream -> righe del recorder
# --------------------------------------------------------------------------------
def _serializza(book: Any) -> Dict[str, Any]:
    """Come `Betfair.stream.recorder.serialize_book` (depth 3) senza importare il
    recorder (porta dentro flumine e il .env). NON porta `trd` ne' `tv` per volume
    e memoria: il curator decide su best back/lay e ltp, e la barra non legge altro."""
    def livelli(lista: Any, n: int) -> List[List[float]]:
        out = [[x["price"], x["size"]] if isinstance(x, dict) else [x.price, x.size] for x in (lista or [])]
        return out[:n]

    runners: Dict[str, Any] = {}
    for r in getattr(book, "runners", None) or []:
        ex = getattr(r, "ex", None)
        runners[str(r.selection_id)] = {
            "b": livelli(getattr(ex, "available_to_back", None), PROFONDITA_LADDER) if ex else [],
            "l": livelli(getattr(ex, "available_to_lay", None), PROFONDITA_LADDER) if ex else [],
            "ltp": getattr(r, "last_price_traded", None),
        }
    return {
        "market_id": book.market_id,
        "pt": getattr(book, "publish_time_epoch", None),
        "status": getattr(book, "status", None),
        "inplay": bool(getattr(book, "inplay", False)),
        "runners": runners,
    }


def libri_dallo_stream(event_id: str, percorso_uscita: str) -> Dict[str, Dict[str, Any]]:
    """Scrive in `percorso_uscita` le righe dei libri (una per aggiornamento, nell'ordine
    dello stream, come le scrive il recorder) e ritorna il catalogo dei mercati
    ({market_id: {market_type, runners:[(id, sortPriority)], open_date}})."""
    from betfairlightweight import StreamListener

    q: "queue.Queue[Any]" = queue.Queue()
    listener = StreamListener(output_queue=q, max_latency=None)
    listener.register_stream(0, "marketSubscription")
    catalogo: Dict[str, Dict[str, Any]] = {}
    fh = _apri_testo(os.path.join(CARTELLA_REGISTRAZIONI, event_id, f"{event_id}.raw.jsonl"))
    if fh is None:
        raise FileNotFoundError(f"raw dello stream mancante per {event_id}")
    with fh, open(percorso_uscita, "w", encoding="utf-8") as out:
        for linea in fh:
            if not linea.strip():
                continue
            # catalogo dalle marketDefinition (nomi dei partecipanti non presenti nello stream)
            if '"marketDefinition"' in linea:
                try:
                    msg = json.loads(linea)
                    for mc in msg.get("mc") or []:
                        md = mc.get("marketDefinition")
                        if md:
                            catalogo[mc["id"]] = {
                                "market_type": md.get("marketType"),
                                "runners": [(r["id"], r.get("sortPriority")) for r in md.get("runners") or []],
                                "open_date": md.get("openDate") or md.get("marketTime"),
                            }
                except (ValueError, KeyError):
                    pass
            listener.on_data(linea)
            while True:
                try:
                    libri = q.get_nowait()
                except queue.Empty:
                    break
                for b in libri:
                    out.write(json.dumps(_serializza(b), separators=(",", ":")) + "\n")
    return catalogo


# --------------------------------------------------------------------------------
# 2. curator vero + punteggi + timeline
# --------------------------------------------------------------------------------
def _leggi_jsonl(path_base: str) -> List[Dict[str, Any]]:
    fh = _apri_testo(path_base)
    if fh is None:
        return []
    out: List[Dict[str, Any]] = []
    with fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                out.append(json.loads(linea))
            except ValueError:
                continue
    return out


def righe_punteggio(event_id: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(righe live_score_timeline, mappa minuti per il curator): come
    `uploader.py::_read_scores` + `_read_timeline_events`."""
    base = os.path.join(CARTELLA_REGISTRAZIONI, event_id, event_id)
    righe: List[Dict[str, Any]] = []
    minute_map: List[Dict[str, Any]] = []
    for rec in _leggi_jsonl(base + ".scores.jsonl"):
        righe.append({
            "ts": rec.get("ts"), "source": rec.get("source") or "betfair", "minute": rec.get("minute"),
            "score_home": rec.get("score_home"), "score_away": rec.get("score_away"),
            "event_type": rec.get("event_type"), "payload": rec.get("payload"),
        })
        if rec.get("ts_ms") is not None:
            minute_map.append({"ts_ms": rec["ts_ms"], "minute": rec.get("minute")})
    minute_map.sort(key=lambda x: x["ts_ms"])
    for ev in _leggi_jsonl(base + ".timeline.jsonl"):
        righe.append({
            "ts": ev.get("ts"), "source": "betfair", "minute": ev.get("minute"),
            "score_home": None, "score_away": None, "event_type": ev.get("type"), "payload": ev,
        })
    return righe, minute_map


def _payload_ridotto(r: Dict[str, Any]) -> Any:
    """Payload ridotto alle chiavi che la barra legge: conteggi cumulativi per
    squadra (angoli/cartellini) per le righe del punteggio; tipo, squadra e minuto
    per le righe-evento."""
    p = r.get("payload")
    if r.get("event_type"):
        p = p or {}
        return {"team": p.get("team"), "team_name": p.get("team_name"), "type": p.get("type"), "minute": p.get("minute")}
    out: Dict[str, Any] = {"home": {}, "away": {}}
    sc = (p or {}).get("score") or {}
    for lato in ("home", "away"):
        d = sc.get(lato) or {}
        for k in ("numberOfYellowCards", "numberOfRedCards", "numberOfCorners"):
            if d.get(k) is not None:
                out[lato][k] = d[k]
    return {"score": out}


def snapshot_dal_curator(event_id: str, percorso_libri: str, minute_map: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Righe di live_market_snapshots: il curator VERO sul file dei libri."""
    return curate_event(percorso_libri, event_id, cadence_sec=CADENZA_CURATOR_SEC, timeline=minute_map or None)


# --------------------------------------------------------------------------------
# 3. campionamento del server come fetchReplayChunked + get_replay_frames
# --------------------------------------------------------------------------------
def _ms(iso: str) -> int:
    from datetime import datetime

    return int(round(datetime.fromisoformat(iso).timestamp() * 1000))


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, v))


def _finestra_server(righe: List[Dict[str, Any]], da_ms: int, a_ms: int, bucket_sec: int) -> List[Dict[str, Any]]:
    """get_replay_frames: DISTINCT ON (market_id, floor(epoch/bucket)) ORDER BY
    market_id, bucket, ts; LIMIT p_max_rows."""
    scelti: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for r in righe:
        t = r["_ms"]
        if t < da_ms or t >= a_ms:
            continue
        chiave = (r["market_id"], math.floor((t / 1000.0) / bucket_sec))
        cur = scelti.get(chiave)
        if cur is None or t < cur["_ms"]:
            scelti[chiave] = r
    ordinati = [scelti[k] for k in sorted(scelti)]
    return ordinati[:FRAMES_PER_CALL]


def _finestra_ricorsiva(righe: List[Dict[str, Any]], da_ms: int, a_ms: int, bucket_sec: int) -> List[Dict[str, Any]]:
    frames = _finestra_server(righe, da_ms, a_ms, bucket_sec)
    if len(frames) >= FRAMES_PER_CALL and a_ms - da_ms > 30_000:
        mid = da_ms + (a_ms - da_ms) // 2
        return _finestra_ricorsiva(righe, da_ms, mid, bucket_sec) + _finestra_ricorsiva(righe, mid, a_ms, bucket_sec)
    return frames


def campiona_come_la_pagina(righe: List[Dict[str, Any]], n_mercati: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Ritorna (frame nell'ordine di arrivo alla pagina, meta con gli estremi)."""
    for r in righe:
        r["_ms"] = _ms(r["ts"])
    ts_min = min(r["_ms"] for r in righe)
    ts_max = max(r["_ms"] for r in righe)
    inplay = [r["_ms"] for r in righe if r["inplay"]]
    inplay_from = min(inplay) if inplay else None
    meta = {
        "ts_min": min(righe, key=lambda r: r["_ms"])["ts"],
        "ts_max": max(righe, key=lambda r: r["_ms"])["ts"],
        "inplay_from_ts": min((r for r in righe if r["inplay"]), key=lambda r: r["_ms"])["ts"] if inplay else None,
    }
    inplay_ms = inplay_from if inplay_from is not None else ts_min
    n = max(1, n_mercati)
    t_min = ts_min
    if inplay_ms - t_min > PRE_MATCH_MAX_MS:
        t_min = inplay_ms - PRE_MATCH_MAX_MS
    pre_sec = max(0.0, (min(inplay_ms, ts_max) - t_min) / 1000.0)
    in_sec = max(0.0, (ts_max - max(inplay_ms, t_min)) / 1000.0)
    bucket_pre = int(_clamp(math.ceil((pre_sec * n) / REPLAY_TARGET_PRE), 30, 300))
    bucket_in = int(_clamp(math.ceil((in_sec * n) / REPLAY_TARGET_FRAMES), 2, 60))
    finestre: List[Tuple[int, int, int]] = []

    def push(da: int, a: int, bucket: int) -> None:
        t = da
        while t < a:
            finestre.append((t, min(t + WINDOW_MS, a), bucket))
            t += WINDOW_MS

    fine_esclusa = ts_max + 1000
    if inplay_ms > t_min:
        push(t_min, min(inplay_ms, fine_esclusa), bucket_pre)
        push(inplay_ms, fine_esclusa, bucket_in)
    else:
        push(t_min, fine_esclusa, bucket_in)
    frames: List[Dict[str, Any]] = []
    for da, a, bucket in finestre:
        frames.extend(_finestra_ricorsiva(righe, da, a, bucket))
    meta["bucket_pre_sec"] = bucket_pre
    meta["bucket_in_sec"] = bucket_in
    return frames, meta


# --------------------------------------------------------------------------------
# 4. riduzione della fixture e scrittura
# --------------------------------------------------------------------------------
def costruisci_fixture(event_id: str) -> Dict[str, Any]:
    righe_pt, minute_map = righe_punteggio(event_id)
    with tempfile.TemporaryDirectory() as tmp:
        percorso = os.path.join(tmp, f"{event_id}.jsonl")
        catalogo = libri_dallo_stream(event_id, percorso)
        snapshots = snapshot_dal_curator(event_id, percorso, minute_map)
    if not snapshots:
        raise ValueError(f"{event_id}: il curator non ha prodotto nessuno snapshot")
    mo_id = next((m for m, c in catalogo.items() if c["market_type"] == "MATCH_ODDS"), None)
    if mo_id is None:
        raise ValueError(f"{event_id}: nessun mercato MATCH_ODDS nello stream (fixture solo calcio)")
    frames, meta = campiona_come_la_pagina(snapshots, len(catalogo) or len({s["market_id"] for s in snapshots}))
    sel = sorted(catalogo[mo_id]["runners"], key=lambda x: (x[1] is None, x[1], x[0]))
    selezioni = [[int(i), str(i)] for i, _ in sel]

    # riduzione: tutti i frame del Match Odds + i frame degli altri mercati che
    # definiscono la griglia della barra (primo di ogni bucket da 10 s nell'ordine
    # di arrivo; quello che porta il primo minuto del bucket) + il primo in-gioco.
    primo_bucket: Dict[int, int] = {}
    minuto_bucket: Dict[int, int] = {}
    for i, f in enumerate(frames):
        b = math.floor(f["_ms"] / BUCKET_BARRA_MS)
        primo_bucket.setdefault(b, i)
        if f["minute"] is not None:
            minuto_bucket.setdefault(b, i)
    idx_inplay = None
    for i, f in sorted(enumerate(frames), key=lambda x: (x[1]["_ms"], x[0])):
        if f["inplay"]:
            idx_inplay = i
            break
    definisce = set(primo_bucket.values()) | set(minuto_bucket.values())
    if idx_inplay is not None:
        definisce.add(idx_inplay)
    out_frames: List[List[Any]] = []
    for i, f in enumerate(frames):
        if f["market_id"] == mo_id:
            ladder = {}
            for sid, e in f["ladder"].items():
                ladder[sid] = [(e.get("back") or [None])[0], (e.get("lay") or [None])[0]]
            out_frames.append([1, f["ts"], f["minute"], 1 if f["inplay"] else 0, f["status"], ladder])
        elif i in definisce:
            out_frames.append([0, f["ts"], f["minute"], 1 if f["inplay"] else 0])

    righe_pt_ord = sorted(righe_pt, key=lambda r: (r["ts"] or ""))
    # nomi e data dalle righe del punteggio e dalle marketDefinition
    # nomi: prima le anagrafiche di API-Football (payload.teams), poi quelli dei punteggi Betfair
    casa = away = None
    for r in righe_pt:
        tm = ((r.get("payload") or {}).get("teams") or {})
        if (tm.get("home") or {}).get("name") and (tm.get("away") or {}).get("name"):
            casa, away = tm["home"]["name"], tm["away"]["name"]
            break
    if casa is None:
        for r in righe_pt:
            t = (((r.get("payload") or {}).get("score") or {}))
            if (t.get("home") or {}).get("name") and (t.get("away") or {}).get("name"):
                casa, away = t["home"]["name"], t["away"]["name"]
                break
    return {
        "event": {
            "event_id": event_id, "fixture_id": None, "league_name": "Lega",
            "home_name": casa or "Casa", "away_name": away or "Ospiti",
            "open_date": catalogo[mo_id].get("open_date"), "status": "UPLOADED",
        },
        # estremi di get_replay_meta + quanti mercati ha il catalogo (determina i bucket del
        # campionamento) e i bucket usati: servono al finto delle RPC dei test sul database
        "meta": {
            **{k: meta[k] for k in ("ts_min", "ts_max", "inplay_from_ts")},
            "n_mercati": len(catalogo) or len({s["market_id"] for s in snapshots}),
            "bucket_pre_sec": meta["bucket_pre_sec"],
            "bucket_in_sec": meta["bucket_in_sec"],
        },
        "mo": {"market_id": mo_id, "selections": selezioni},
        "frames": out_frames,
        "score_timeline": [
            [r["ts"], r["source"], r["minute"], r["score_home"], r["score_away"], r["event_type"], _payload_ridotto(r)]
            for r in righe_pt_ord
        ],
        "sorgente": impronte_sorgente(event_id),
    }


def serializza(fx: Dict[str, Any]) -> str:
    """Testo canonico e DETERMINISTICO (stesso ingresso -> stessi byte)."""
    return json.dumps(fx, separators=(",", ":"), ensure_ascii=True) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("eventi", nargs="*", help="ID delle partite in registrazioni_banco/")
    ap.add_argument("--tutte", action="store_true", help="tutte le partite di registrazioni_banco/")
    ap.add_argument("--verifica", action="store_true", help="non scrive: esce 1 se la fixture manca o differisce")
    a = ap.parse_args(argv)
    eventi = eventi_registrati() if a.tutte else a.eventi
    if not eventi:
        print("nessuna partita (indica un ID o --tutte)", file=sys.stderr)
        return 2
    esito = 0
    for ev in eventi:
        testo = serializza(costruisci_fixture(ev))
        dest = nome_fixture(ev)
        if a.verifica:
            att = open(dest, "r", encoding="utf-8").read() if os.path.exists(dest) else None
            stato = "OK" if att == testo else ("MANCA" if att is None else "DIVERSA")
            print(f"{ev}: {stato} ({os.path.relpath(dest, RADICE)})")
            if stato != "OK":
                esito = 1
        else:
            with open(dest, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(testo)
            print(f"{ev}: scritta {os.path.relpath(dest, RADICE)} ({len(testo) // 1024} KB)")
    return esito


if __name__ == "__main__":
    raise SystemExit(main())
