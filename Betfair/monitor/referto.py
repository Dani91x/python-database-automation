"""referto.py - il referto giornaliero "Salute" (T0A, 09/10/2026).

Comando riproducibile (dalla radice del repo, sul PC con l'app accesa da 24 h):

    python -m Betfair.monitor.referto --giorno 2026-10-10 --da-db --log-dir _logs --raw-dir _live_raw
    python -m Betfair.monitor.referto --giorno 2026-10-10                      (righe locali _logs/monitor)
    python -m Betfair.monitor.referto --giorno 2026-10-10 --righe righe.json   (stesse righe -> stesso referto)

Scrive ``AUDIT_MONITOR/REFERTO_SALUTE_<giorno>.md`` e ``.json``. Stesse righe in
ingresso = stessi byte in uscita (nessun "adesso" nel testo; l'impronta delle
righe lette e' nel referto). ``--salva-righe`` congela le righe lette dal DB in un
file JSON, cosi' chiunque rigenera lo stesso referto senza DB.

Grandezze (I par. 7, 04 par. 7 L15-L19) contro gli OBIETTIVI PROVVISORI (da confermare a
fine baseline): processi, riavvii (non pianificati se il DB dice ``RUNNER
CRASHATO``), CPU, RAM e crescita fra 2a e 24a ora di vita, richieste al cloud,
log al giorno, re-login, eta' del feed (per partita, dalle registrazioni con
``rx``; "con soldi" se il DB dice che la partita ha ordini, paper e live MAI
sommati), scarto dell'orologio (limite superiore stimato da ``rx - pt``),
transazioni/ora del conto, tratti del percorso dell'ordine (L6, L6b, L7),
versioni contro i pin di ``requirements*.txt`` e Windows Update.

Sola lettura (DB in SELECT/RPC, file locali). ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .registro import somma_riassunti

RADICE = Path(__file__).resolve().parents[2]

try:
    from zoneinfo import ZoneInfo

    FUSO = ZoneInfo("Europe/Rome")
except Exception:  # noqa: BLE001 - tzdata assente: si dichiara UTC
    FUSO = timezone.utc

#: obiettivi PROVVISORI (I par. 7, 04 par. 7 L15-L19; da confermare a fine baseline)
OBIETTIVI = {
    "cpu_servizio_p95_pct": 30.0,          # nessun servizio > 30% p95 (di un core) a riposo
    "cpu_app_media_pct": 100.0,            # app totale <= 100% di un core mediano
    "rss_crescita_pct": 5.0,               # crescita <= 5% fra 2a e 24a ora
    "rss_app_mb": 0.25 * 15.8 * 1024.0,    # totale <= 25% dei 15,8 GB
    "db_bot_al_minuto": 60.0,              # servizi bot <= 60 richieste/min
    "log_mb_giorno": 50.0,                 # <= 50 MB/giorno a riposo
    "relogin_12h": 1.0,                    # <= 1 re-login per servizio ogni 12 h
    "riavvii_non_pianificati": 0,          # 0
    "orologio_ms": 100.0,                  # scarto <= 100 ms
    "transazioni_ora": 5000,               # tetto Betfair (flumine MaxTransactionCount)
}
SERVIZI_BOT = ("mike-service", "omega-service", "safe-strategy-bot")
FINESTRE_GIORNO = 2880
#: modulo del watchdog -> servizio (per i "RUNNER CRASHATO [modulo]" di live_alerts)
MODULO_SERVIZIO = {
    "Betfair.stream.runner": "runner-calcio",
    "Betfair.stream.tennis_live.tennis_runner": "runner-tennis",
    "Betfair.stream.scalper.scalper_service": "scalper-service",
    "Betfair.stream.tennis_live.tennis_bot_service": "tennis-bot-service",
    "Betfair.safe_strategy.service": "safe-strategy-service",
    "Betfair.omega.omega_service": "omega-service",
    "Betfair.safe_strategy.bot_service": "safe-strategy-bot",
    "Betfair.mike.service": "mike-service",
}


# ---------------------------------------------------------------------------
# lettura delle righe
# ---------------------------------------------------------------------------
def finestra_del_giorno(giorno: str) -> Tuple[datetime, datetime]:
    d = datetime.strptime(giorno, "%Y-%m-%d").replace(tzinfo=FUSO)
    return d.astimezone(timezone.utc), (d + timedelta(days=1)).astimezone(timezone.utc)


def _ts(r: Dict[str, Any]) -> Optional[datetime]:
    v = r.get("ts")
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def righe_locali(cartella: Path, giorno: str) -> List[Dict[str, Any]]:
    """Le righe JSONL della copia locale (cartella del giorno e del successivo:
    la cartella e' per data locale del PC, la finestra e' Europe/Rome)."""
    out: List[Dict[str, Any]] = []
    d0 = datetime.strptime(giorno, "%Y-%m-%d")
    for g in (d0, d0 + timedelta(days=1)):
        dd = cartella / g.strftime("%Y-%m-%d")
        if not dd.is_dir():
            continue
        for f in sorted(dd.glob("*.jsonl")):
            with open(f, "r", encoding="ascii", errors="replace") as fh:
                for riga in fh:
                    riga = riga.strip()
                    if riga:
                        try:
                            out.append(json.loads(riga))
                        except ValueError:
                            continue
    return out


def righe_db(da: datetime, a: datetime, pagina: int = 1000) -> List[Dict[str, Any]]:
    from db_client import get_supabase_client  # noqa: PLC0415

    sb = get_supabase_client()
    out: List[Dict[str, Any]] = []
    inizio = 0
    while True:
        res = (sb.table("monitor_metrics").select("*")
               .gte("ts", da.isoformat()).lt("ts", a.isoformat())
               .order("ts").order("id").range(inizio, inizio + pagina - 1).execute())
        blocco = getattr(res, "data", None) or []
        out.extend(blocco)
        if len(blocco) < pagina:
            return out
        inizio += pagina


def filtra_giorno(righe: Iterable[Dict[str, Any]], da: datetime, a: datetime) -> List[Dict[str, Any]]:
    out = []
    for r in righe:
        t = _ts(r)
        if t is not None and da <= t < a:
            r = {k: v for k, v in r.items() if k not in ("id", "creato_at")}
            out.append(r)
    out.sort(key=lambda r: (str(r.get("servizio")), str(r.get("ts")), int(r.get("pid") or 0)))
    return out


def impronta(righe: List[Dict[str, Any]]) -> str:
    testo = json.dumps(righe, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(testo.encode("ascii")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# aggregazione
# ---------------------------------------------------------------------------
def _num(v: Any) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _p(valori: List[float], q: float) -> Optional[float]:
    if not valori:
        return None
    xs = sorted(valori)
    k = max(0, min(len(xs) - 1, int(round(q * (len(xs) - 1)))))
    return round(xs[k], 2)


def _somma_dict(dst: Dict[str, float], src: Any) -> None:
    if isinstance(src, dict):
        for k, v in src.items():
            n = _num(v)
            if n is not None:
                dst[k] = dst.get(k, 0) + n


def gruppo_servizio(nome: str) -> str:
    return "scalper-sessioni" if str(nome).startswith("scalper-sessione-") else str(nome)


def aggrega_servizio(righe: List[Dict[str, Any]]) -> Dict[str, Any]:
    cpu = [x for x in (_num(r.get("cpu_pct")) for r in righe) if x is not None]
    vite: Dict[Tuple[Any, Any], List[Dict[str, Any]]] = {}
    for r in righe:
        vite.setdefault((r.get("pid"), r.get("avvio_ts")), []).append(r)
    cont: Dict[str, Dict[str, float]] = {}
    tratti: Dict[str, List[Dict[str, Any]]] = {}
    valori: Dict[str, Any] = {}
    sistema: Optional[Dict[str, Any]] = None
    minuti = 0.0
    thread_max = handle_max = None
    psutil_ok = None
    for r in righe:
        m = r.get("metriche") or {}
        minuti += float(_num(m.get("finestra_s")) or 0.0) / 60.0
        for g, d in (m.get("contatori") or {}).items():
            _somma_dict(cont.setdefault(g, {}), d)
        for k, t in (m.get("tratti") or {}).items():
            tratti.setdefault(k, []).append(t)
        for g, d in (m.get("valori") or {}).items():
            if isinstance(d, dict):
                valori.setdefault(g, {}).update(d)
        if isinstance(m.get("sistema"), dict):
            sistema = m["sistema"]
        pr = m.get("processo") or {}
        if pr.get("psutil") is not None:
            psutil_ok = bool(pr.get("psutil"))
        for campo in ("thread",):
            v = _num(pr.get(campo))
            if v is not None:
                thread_max = v if thread_max is None else max(thread_max, v)
        for campo in ("handle", "fd"):
            v = _num(pr.get(campo))
            if v is not None:
                handle_max = v if handle_max is None else max(handle_max, v)
    crescite = []
    for (pid, _avvio), rr in sorted(vite.items(), key=lambda x: str(x[0])):
        crescite.append(crescita_rss(rr, pid))
    db_tot = sum((cont.get("db") or {}).values())
    rest = cont.get("betfair_rest") or {}
    login = int(rest.get("certlogin", 0) + rest.get("login", 0))
    return {
        "righe": len(righe),
        "copertura_pct": round(100.0 * len(righe) / FINESTRE_GIORNO, 1),
        "minuti_misurati": round(minuti, 1),
        "vite": len(vite),
        "riavvii_pid": max(0, len(vite) - 1),
        "psutil": psutil_ok,
        "cpu_media_pct": round(statistics.fmean(cpu), 2) if cpu else None,
        "cpu_p95_pct": _p(cpu, 0.95),
        "cpu_max_pct": round(max(cpu), 2) if cpu else None,
        "rss_max_mb": max((x for x in (_num(r.get("rss_mb")) for r in righe) if x is not None), default=None),
        "crescita_rss": crescite,
        "thread_max": thread_max,
        "handle_max": handle_max,
        "db_richieste": int(db_tot),
        "db_al_minuto": round(db_tot / minuti, 2) if minuti > 0 else None,
        "db_tabelle_top": sorted(((k, int(v)) for k, v in (cont.get("db") or {}).items()),
                                 key=lambda x: (-x[1], x[0]))[:12],
        "db_errori": {k: int(v) for k, v in sorted((cont.get("db_errori") or {}).items())},
        "rest": {k: int(v) for k, v in sorted(rest.items())},
        "login": login,
        "relogin": max(0, login - len(vite)),
        "transazioni": {k: int(v) for k, v in sorted((cont.get("transazioni") or {}).items())},
        "esecuzione_live": {k: int(v) for k, v in sorted((cont.get("esecuzione_live") or {}).items())},
        "esecuzione_paper": {k: int(v) for k, v in sorted((cont.get("esecuzione_paper") or {}).items())},
        "log_errori_top": sorted(((k, int(v)) for k, v in (cont.get("log_errori") or {}).items()),
                                 key=lambda x: (-x[1], x[0]))[:10],
        "stream": {g: {k: int(v) for k, v in sorted((cont.get(g) or {}).items())}
                   for g in ("stream_msg", "stream_status", "stream_status_log", "stream_avvii")
                   if cont.get(g)},
        "connessioni_disponibili": valori.get("connessioni_disponibili") or {},
        "connessioni_disponibili_log": valori.get("connessioni_disponibili_log") or {},
        "tratti": {k: somma_riassunti(v) for k, v in sorted(tratti.items())},
        "sistema": sistema,
    }


def crescita_rss(righe: List[Dict[str, Any]], pid: Any) -> Dict[str, Any]:
    """RSS mediana nella 2a ora di vita contro l'ultima ora di vita del processo."""
    def _rss_fra(a: float, b: float) -> List[float]:
        return [x for x in (_num(r.get("rss_mb")) for r in righe
                            if a <= float(_num(r.get("uptime_s")) or -1) < b) if x is not None]

    vita = max((float(_num(r.get("uptime_s")) or 0.0) for r in righe), default=0.0)
    h2 = _rss_fra(3600.0, 7200.0)
    fine = _rss_fra(max(7200.0, vita - 3600.0), vita + 1.0)
    out: Dict[str, Any] = {"pid": pid, "vita_ore": round(vita / 3600.0, 2)}
    if not h2 or not fine or vita < 3 * 3600.0:
        out["esito"] = "non misurabile (vita < 3 h o righe mancanti)"
        return out
    a, b = statistics.median(h2), statistics.median(fine)
    out.update({"rss_2a_ora_mb": round(a, 1), "rss_ultima_ora_mb": round(b, 1),
                "crescita_pct": round(100.0 * (b - a) / a, 2) if a > 0 else None})
    return out


def transazioni_per_ora(righe: List[Dict[str, Any]]) -> Dict[str, int]:
    """Transazioni Betfair (place+replace+fallite, solo esecuzione VERA) per ora
    locale, sommate su TUTTI i processi (il limite e' del conto)."""
    ore: Dict[str, int] = {}
    for r in righe:
        t = _ts(r)
        tx = ((r.get("metriche") or {}).get("contatori") or {}).get("transazioni") or {}
        if t is None or not tx:
            continue
        h = t.astimezone(FUSO).strftime("%H:00")
        ore[h] = ore.get(h, 0) + int(sum(float(v) for v in tx.values()))
    return dict(sorted(ore.items()))


def stima_orologio(righe: List[Dict[str, Any]]) -> Optional[float]:
    """Minimo di ``rx - pt`` di tutte le finestre: limite SUPERIORE dello scarto
    del PC (scarto + latenza minima di rete)."""
    mn: Optional[float] = None
    for r in righe:
        for k, t in ((r.get("metriche") or {}).get("tratti") or {}).items():
            if k.startswith("feed_rx_pt_ms.") and isinstance(t, dict) and t.get("min") is not None:
                v = float(t["min"])
                mn = v if mn is None else min(mn, v)
    return None if mn is None else round(mn, 1)


# ---------------------------------------------------------------------------
# fonti accessorie (facoltative)
# ---------------------------------------------------------------------------
def pin_requisiti(radice: Path = RADICE) -> Dict[str, str]:
    pin: Dict[str, str] = {}
    for nome in ("requirements.txt", "requirements-train.txt"):
        p = radice / nome
        if not p.exists():
            continue
        for riga in p.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^\s*([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*==\s*([^\s#;]+)", riga)
            if m:
                pin[m.group(1).lower()] = m.group(3)
    return pin


def log_del_giorno(cartella: Path, da: datetime, a: datetime) -> Dict[str, Any]:
    """Dimensione dei log toccati nel giorno (per servizio = prefisso del nome)."""
    per: Dict[str, float] = {}
    file_grandi = []
    tot = 0.0
    if not cartella.is_dir():
        return {"cartella": str(cartella), "assente": True}
    for f in sorted(cartella.glob("*.log")):
        try:
            st = f.stat()
        except OSError:
            continue
        t = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
        if not (da <= t < a + timedelta(hours=1)):
            continue
        mb = st.st_size / (1024.0 * 1024.0)
        tot += mb
        nome = f.name.split("_", 1)[0]
        per[nome] = per.get(nome, 0.0) + mb
        if mb > 100.0:
            file_grandi.append((f.name, round(mb, 1)))
    return {"cartella": str(cartella), "mb_totali": round(tot, 1),
            "mb_per_servizio": {k: round(v, 1) for k, v in sorted(per.items())},
            "file_oltre_100_mb": file_grandi}


def tempi_ordine(cartella: Path, da: datetime, a: datetime) -> List[Dict[str, Any]]:
    """Le righe ``tempi_ordine`` dei log del giorno, con il lettore esistente."""
    from Betfair.stream.tools import leggi_tempi_ordine as L  # noqa: PLC0415

    righe: List[str] = []
    if not cartella.is_dir():
        return []
    for f in sorted(cartella.glob("*.log")):
        try:
            t = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if not (da <= t < a + timedelta(hours=1)):
            continue
        with open(f, "r", encoding="utf-8", errors="replace") as fh:
            righe.extend(r for r in fh if "tempi_ordine" in r)
    return L.tabella(L.raccogli(righe))


def feed_per_partita(cartella: Path, da: datetime, a: datetime,
                     soldi: Optional[Dict[str, List[str]]] = None) -> List[Dict[str, Any]]:
    """Per ogni registrazione toccata nel giorno: messaggi, buchi > 5 s fra ``pt``
    consecutivi, ``rx - pt`` (solo righe con ``rx``: monitor acceso)."""
    out: List[Dict[str, Any]] = []
    if not cartella.is_dir():
        return out
    for f in sorted(cartella.glob("*/*.raw.jsonl")):
        try:
            t = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if not (da <= t < a + timedelta(hours=1)):
            continue
        n = buchi = 0
        prec: Optional[int] = None
        buco_max = 0
        eta: List[float] = []
        da_ms, a_ms = da.timestamp() * 1000, a.timestamp() * 1000
        with open(f, "r", encoding="utf-8", errors="replace") as fh:
            for riga in fh:
                try:
                    d = json.loads(riga)
                except ValueError:
                    continue
                pt = d.get("pt")
                if not isinstance(pt, (int, float)) or not (da_ms <= pt < a_ms):
                    continue
                n += 1
                if prec is not None:
                    g = int(pt) - prec
                    buco_max = max(buco_max, g)
                    if g > 5000:
                        buchi += 1
                prec = int(pt)
                rx = d.get("rx")
                if isinstance(rx, (int, float)):
                    eta.append(float(rx) - float(pt))
        if n == 0:
            continue
        ev = f.parent.name
        out.append({"evento": ev, "messaggi": n, "buchi_oltre_5s": buchi,
                    "buco_max_s": round(buco_max / 1000.0, 1),
                    "rx_pt_n": len(eta), "rx_pt_p50_ms": _p(eta, 0.5), "rx_pt_p99_ms": _p(eta, 0.99),
                    "soldi": ",".join(sorted(m for m, evs in (soldi or {}).items() if ev in evs)) or "-"})
    return out


def eventi_con_soldi(da: datetime, a: datetime) -> Dict[str, List[str]]:
    """Eventi CALCIO con ordini nel giorno (betfair_live_orders), per modalita'."""
    from db_client import get_supabase_client  # noqa: PLC0415

    res = (get_supabase_client().table("betfair_live_orders").select("event_id,mode")
           .gte("placed_at", da.isoformat()).lt("placed_at", a.isoformat()).limit(10000).execute())
    out: Dict[str, List[str]] = {}
    for r in getattr(res, "data", None) or []:
        if r.get("event_id"):
            out.setdefault(str(r.get("mode")), []).append(str(r["event_id"]))
    return {k: sorted(set(v)) for k, v in sorted(out.items())}


def crash_dal_db(da: datetime, a: datetime) -> Dict[str, int]:
    from db_client import get_supabase_client  # noqa: PLC0415

    res = (get_supabase_client().table("live_alerts").select("level,message,created_at")
           .eq("code", "RUNNER_WATCHDOG").gte("created_at", da.isoformat())
           .lt("created_at", a.isoformat()).limit(5000).execute())
    out: Dict[str, int] = {}
    for r in getattr(res, "data", None) or []:
        msg = str(r.get("message") or "")
        m = re.search(r"RUNNER CRASHATO \[([^\]]+)\]", msg)
        if m:
            s = MODULO_SERVIZIO.get(m.group(1).strip(), m.group(1).strip())
            out[s] = out.get(s, 0) + 1
        elif "ricambio pianificato" in msg:
            out["_pianificati"] = out.get("_pianificati", 0) + 1
    return dict(sorted(out.items()))


def vitalita_raccoglitori() -> Any:
    from db_client import get_supabase_client  # noqa: PLC0415

    return getattr(get_supabase_client().rpc("monitor_vitalita_raccoglitori", {}).execute(),
                   "data", None)


# ---------------------------------------------------------------------------
# referto
# ---------------------------------------------------------------------------
def _v(ok: Optional[bool]) -> str:
    return "NON MISURATO" if ok is None else ("OK" if ok else "FUORI")


def costruisci(giorno: str, righe: List[Dict[str, Any]], *, fonte: str,
               extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    extra = extra or {}
    per: Dict[str, List[Dict[str, Any]]] = {}
    for r in righe:
        per.setdefault(gruppo_servizio(r.get("servizio")), []).append(r)
    servizi = {s: aggrega_servizio(rr) for s, rr in sorted(per.items())}
    tutti_tratti: Dict[str, List[Dict[str, Any]]] = {}
    for r in righe:
        for k, t in ((r.get("metriche") or {}).get("tratti") or {}).items():
            tutti_tratti.setdefault(k, []).append(t)
    tx_ore = transazioni_per_ora(righe)
    orologio = stima_orologio(righe)
    cpu_app = sum(s["cpu_media_pct"] or 0.0 for s in servizi.values()) if servizi else None
    rss_app = sum(s["rss_max_mb"] or 0.0 for s in servizi.values()) if servizi else None
    db_giorno = sum(s["db_richieste"] for s in servizi.values())
    crash = extra.get("crash")
    log = extra.get("log") or {}
    verdetti = []

    def ver(cosa: str, valore: Any, obiettivo: Any, ok: Optional[bool], nota: str = "") -> None:
        verdetti.append({"grandezza": cosa, "valore": valore, "obiettivo": obiettivo,
                         "esito": _v(ok), "nota": nota})

    if servizi:
        peggiore = max(servizi.items(), key=lambda kv: kv[1]["cpu_p95_pct"] or -1)
        ver("L15 CPU p95 per servizio (% di un core)", f"{peggiore[0]} {peggiore[1]['cpu_p95_pct']}",
            f"<= {OBIETTIVI['cpu_servizio_p95_pct']}",
            None if peggiore[1]["cpu_p95_pct"] is None
            else peggiore[1]["cpu_p95_pct"] <= OBIETTIVI["cpu_servizio_p95_pct"],
            "p95 sull'intera giornata, non solo a riposo")
        ver("L15 CPU app (somma delle medie)", round(cpu_app or 0.0, 2),
            f"<= {OBIETTIVI['cpu_app_media_pct']}", (cpu_app or 0.0) <= OBIETTIVI["cpu_app_media_pct"])
        cres = [(s, c) for s, a in servizi.items() for c in a["crescita_rss"] if "crescita_pct" in c]
        if cres:
            s, c = max(cres, key=lambda x: x[1]["crescita_pct"] or -1e9)
            ver("L16 crescita RSS 2a -> ultima ora (peggiore)", f"{s} {c['crescita_pct']}%",
                f"<= {OBIETTIVI['rss_crescita_pct']}%",
                c["crescita_pct"] is not None and c["crescita_pct"] <= OBIETTIVI["rss_crescita_pct"])
        else:
            ver("L16 crescita RSS 2a -> ultima ora", "-", f"<= {OBIETTIVI['rss_crescita_pct']}%", None,
                "nessun processo con vita >= 3 h")
        ver("L16 RAM app (somma dei massimi)", round(rss_app or 0.0, 1),
            f"<= {round(OBIETTIVI['rss_app_mb'])} MB", (rss_app or 0.0) <= OBIETTIVI["rss_app_mb"])
        ver("L17 richieste al cloud nel giorno", db_giorno, "dal piano dei dati", None,
            "riferimento 08/10: 707,5/min = 1.018.800/giorno")
        for s in SERVIZI_BOT:
            a = servizi.get(s)
            if a is not None:
                ver(f"L17 {s} richieste/min", a["db_al_minuto"], f"<= {OBIETTIVI['db_bot_al_minuto']}",
                    None if a["db_al_minuto"] is None else a["db_al_minuto"] <= OBIETTIVI["db_bot_al_minuto"])
        rl = max(servizi.items(), key=lambda kv: kv[1]["relogin"])
        ver("L18 re-login (peggiore, nel giorno)", f"{rl[0]} {rl[1]['relogin']}",
            f"<= {OBIETTIVI['relogin_12h']} ogni 12 h", rl[1]["relogin"] <= 2 * OBIETTIVI["relogin_12h"],
            "login oltre il primo di ogni vita del processo")
    if crash is not None:
        n = sum(v for k, v in crash.items() if not k.startswith("_"))
        ver("L18 riavvii NON pianificati (live_alerts)", n, "0", n == 0)
    else:
        n_pid = sum(a["riavvii_pid"] for a in servizi.values())
        ver("L18 riavvii (pid cambiati, non classificati)", n_pid, "0 non pianificati", None,
            "senza DB non si distingue il crash dal ricambio pianificato")
    if "mb_totali" in log:
        ver("L18 log del giorno (MB)", log["mb_totali"], f"<= {OBIETTIVI['log_mb_giorno']}",
            log["mb_totali"] <= OBIETTIVI["log_mb_giorno"])
    else:
        ver("L18 log del giorno (MB)", "-", f"<= {OBIETTIVI['log_mb_giorno']}", None, "--log-dir assente")
    ver("L19 scarto orologio (limite superiore da rx - pt)", orologio, f"<= {OBIETTIVI['orologio_ms']} ms",
        None if orologio is None else (True if orologio <= OBIETTIVI["orologio_ms"] else None),
        "sopra 100 ms non e' conclusivo (contiene la latenza): misurare con m00b_ntp_offset.py")
    if tx_ore:
        ver("transazioni Betfair per ora (massimo)", max(tx_ore.values()),
            f"<= {OBIETTIVI['transazioni_ora']}", max(tx_ore.values()) <= OBIETTIVI["transazioni_ora"])
    else:
        ver("transazioni Betfair per ora", 0, f"<= {OBIETTIVI['transazioni_ora']}", True,
            "nessuna esecuzione VERA nel giorno (il paper non e' una transazione)")
    pin = pin_requisiti()
    versioni_fuori = []
    for s, a in servizi.items():
        pk = ((a.get("sistema") or {}).get("pacchetti") or {})
        for nome, ver_ in sorted(pk.items()):
            atteso = pin.get(nome.lower())
            if atteso and ver_ and ver_ != atteso:
                versioni_fuori.append(f"{s}: {nome} {ver_} (pin {atteso})")
    return {
        "giorno": giorno,
        "fuso": str(FUSO),
        "fonte": fonte,
        "righe": len(righe),
        "impronta_righe": impronta(righe),
        "obiettivi": OBIETTIVI,
        "verdetti": verdetti,
        "servizi": servizi,
        "tratti_app": {k: somma_riassunti(v) for k, v in sorted(tutti_tratti.items())},
        "transazioni_per_ora": tx_ore,
        "orologio_limite_superiore_ms": orologio,
        "versioni_fuori_pin": sorted(set(versioni_fuori)),
        **{k: v for k, v in sorted(extra.items())},
    }


_TRATTI_SPIEGATI = (
    ("feed_rx_pt_ms.", "L1 Betfair pt -> ricezione (orologi diversi: include lo scarto del PC)"),
    ("ladder_pub_pt_ms", "L3 pt -> pubblicazione del ladder sul canale"),
    ("canale_coda_ms", "L6 attesa in coda del canale (arrivo -> drenaggio del worker)"),
    ("diario_fsync_ms", "L6b diario write-ahead, flush+fsync prima del place"),
    ("betfair_place_ms", "L7 placeOrders -> risposta (flumine, Betfair vero)"),
    ("betfair_replace_ms", "L7 replaceOrders -> risposta"),
    ("betfair_cancel_ms", "cancelOrders -> risposta"),
    ("pacchetto_attesa_ms", "flumine: pacchetto in attesa del pool (> 100 ms)"),
    ("flumine_latenza_alta_ms", "flumine: book con latenza > 2 s (avviso oggi perso dal formato del log)"),
    ("db_ms", "PostgREST richiesta -> intestazioni di risposta"),
    ("rest_ms.", "REST Betfair per metodo (sessione dell'APIClient)"),
    ("monitor_giro_ms", "costo del giro dello scrittore (fuori dal ciclo caldo)"),
)


def _spiega(nome: str) -> str:
    for pref, testo in _TRATTI_SPIEGATI:
        if nome.startswith(pref):
            return testo
    return ""


def _f(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.2f}".rstrip("0").rstrip(".")
    return str(v)


def markdown(r: Dict[str, Any]) -> str:
    L: List[str] = []
    a = L.append
    a(f"# Referto 'Salute' del {r['giorno']} ({r['fuso']})")
    a("")
    a(f"Fonte: {r['fonte']}. Righe lette: {r['righe']} (impronta `{r['impronta_righe']}`).")
    a("Generato da `python -m Betfair.monitor.referto` (T0A). Stesse righe = stesso referto.")
    a("Obiettivi PROVVISORI (I par. 7, 04 par. 7 L15-L19), da confermare a fine baseline.")
    a("")
    a("## Verdetti")
    a("")
    a("| Grandezza | Valore | Obiettivo | Esito | Nota |")
    a("|---|---|---|---|---|")
    for v in r["verdetti"]:
        a(f"| {v['grandezza']} | {_f(v['valore'])} | {v['obiettivo']} | {v['esito']} | {v['nota']} |")
    a("")
    a("## Servizi")
    a("")
    a("| Servizio | Righe | Copertura | Vite | CPU media | CPU p95 | RSS max MB | Thread max | DB/giorno | DB/min | REST | Login | Re-login |")
    a("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s, x in r["servizi"].items():
        a(f"| {s} | {x['righe']} | {_f(x['copertura_pct'])}% | {x['vite']} | {_f(x['cpu_media_pct'])} | "
          f"{_f(x['cpu_p95_pct'])} | {_f(x['rss_max_mb'])} | {_f(x['thread_max'])} | {x['db_richieste']} | "
          f"{_f(x['db_al_minuto'])} | {sum(x['rest'].values())} | {x['login']} | {x['relogin']} |")
    a("")
    for s, x in r["servizi"].items():
        a(f"### {s}")
        a("")
        if x["psutil"] is False:
            a("- psutil NON disponibile: CPU da os.times, RSS solo su Linux.")
        a("- Crescita RSS: " + "; ".join(
            f"pid {c['pid']} vita {c['vita_ore']} h: " + (f"{c['rss_2a_ora_mb']} -> {c['rss_ultima_ora_mb']} MB "
                                                          f"({c['crescita_pct']}%)" if "crescita_pct" in c
                                                          else c["esito"]) for c in x["crescita_rss"]))
        if x["db_tabelle_top"]:
            a("- DB per tabella: " + ", ".join(f"{k} {v}" for k, v in x["db_tabelle_top"]))
        if x["db_errori"]:
            a("- DB errori: " + ", ".join(f"{k} {v}" for k, v in x["db_errori"].items()))
        if x["rest"]:
            a("- REST Betfair: " + ", ".join(f"{k} {v}" for k, v in x["rest"].items()))
        if x["esecuzione_live"] or x["esecuzione_paper"]:
            a(f"- Esecuzione LIVE (Betfair vero): {x['esecuzione_live'] or '-'}; PAPER (simulata, mai "
              f"sommata): {x['esecuzione_paper'] or '-'}; transazioni: {x['transazioni'] or '-'}")
        if x["stream"]:
            a("- Stream: " + "; ".join(f"{g} {d}" for g, d in x["stream"].items()))
        if x["connessioni_disponibili"] or x["connessioni_disponibili_log"]:
            a(f"- connectionsAvailable (ultimo): {x['connessioni_disponibili'] or '-'}"
              f" | dal log di betfairlightweight (lo 0 non e' salvato): {x['connessioni_disponibili_log'] or '-'}")
        if x["log_errori_top"]:
            a("- Errori di log: " + ", ".join(f"{k} {v}" for k, v in x["log_errori_top"]))
        a("")
    a("## Tratti (somma secchio per secchio di tutte le finestre; p50/p95/p99 = bordo del secchio)")
    a("")
    a("| Tratto | n | min | p50 | p95 | p99 | max | Cosa misura |")
    a("|---|---:|---:|---:|---:|---:|---:|---|")
    for k, t in r["tratti_app"].items():
        a(f"| {k} | {t['n']} | {_f(t['min'])} | {_f(t['p50'])} | {_f(t['p95'])} | {_f(t['p99'])} | "
          f"{_f(t['max'])} | {_spiega(k)} |")
    a("")
    a("## Transazioni Betfair per ora (tutti i processi: il limite e' del conto)")
    a("")
    a(", ".join(f"{h} {n}" for h, n in r["transazioni_per_ora"].items()) or "nessuna esecuzione vera")
    a("")
    a("## Versioni")
    a("")
    a("\n".join(f"- {x}" for x in r["versioni_fuori_pin"]) or "- tutte le versioni lette coincidono con i pin")
    for s, x in r["servizi"].items():
        w = (x.get("sistema") or {}).get("windows")
        if w:
            a(f"- Windows (letto da {s}): {json.dumps(w, sort_keys=True)}")
            break
    for chiave, titolo in (("log", "Log del giorno"), ("crash", "Riavvii dal watchdog (live_alerts)"),
                           ("raccoglitori", "Vitalita' dei raccoglitori"),
                           ("eventi_con_soldi", "Partite calcio con ordini (paper e live separati)")):
        if chiave in r:
            a("")
            a(f"## {titolo}")
            a("")
            a("```")
            a(json.dumps(r[chiave], sort_keys=True, indent=1, ensure_ascii=True, default=str))
            a("```")
    if r.get("feed"):
        a("")
        a("## Feed per partita (registrazioni del giorno)")
        a("")
        a("| Evento | Soldi | Messaggi | Buchi > 5 s | Buco max s | rx-pt n | p50 ms | p99 ms |")
        a("|---|---|---:|---:|---:|---:|---:|---:|")
        for e in r["feed"]:
            a(f"| {e['evento']} | {e['soldi']} | {e['messaggi']} | {e['buchi_oltre_5s']} | {e['buco_max_s']} | "
              f"{e['rx_pt_n']} | {_f(e['rx_pt_p50_ms'])} | {_f(e['rx_pt_p99_ms'])} |")
    if r.get("tempi_ordine") is not None:
        a("")
        a("## Tempi d'ordine (righe `tempi_ordine` dei log, lettore `leggi_tempi_ordine`)")
        a("")
        a("```")
        a(json.dumps(r["tempi_ordine"], sort_keys=True, indent=1, ensure_ascii=True, default=str))
        a("```")
    a("")
    return "\n".join(L)


def scrivi(r: Dict[str, Any], uscita: Path) -> Tuple[Path, Path]:
    uscita.mkdir(parents=True, exist_ok=True)
    pj = uscita / f"REFERTO_SALUTE_{r['giorno']}.json"
    pm = uscita / f"REFERTO_SALUTE_{r['giorno']}.md"
    with open(pj, "w", encoding="ascii", newline="\n") as fh:
        fh.write(json.dumps(r, sort_keys=True, indent=1, ensure_ascii=True, default=str) + "\n")
    with open(pm, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(markdown(r))
    return pm, pj


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Referto giornaliero Salute (T0A)")
    ap.add_argument("--giorno", required=True, help="AAAA-MM-GG (giornata Europe/Rome)")
    ap.add_argument("--da-db", action="store_true", help="righe da monitor_metrics (+ live_alerts, raccoglitori)")
    ap.add_argument("--locale", default=str(RADICE / "_logs" / "monitor"), help="cartella delle righe locali")
    ap.add_argument("--righe", default=None, help="file JSON con le righe (riproducibilita')")
    ap.add_argument("--salva-righe", default=None, help="salva le righe lette in questo file JSON")
    ap.add_argument("--log-dir", default=None, help="cartella _logs (dimensioni e tempi_ordine)")
    ap.add_argument("--raw-dir", default=None, help="cartella _live_raw (feed per partita)")
    ap.add_argument("--uscita", default=str(RADICE / "AUDIT_MONITOR"))
    args = ap.parse_args(argv)
    da, a = finestra_del_giorno(args.giorno)
    extra: Dict[str, Any] = {}
    if args.righe:
        with open(args.righe, "r", encoding="utf-8") as fh:
            dati = json.load(fh)
        grezze = dati["righe"] if isinstance(dati, dict) else dati
        fonte = f"file {Path(args.righe).name}"
        if isinstance(dati, dict):
            extra.update(dati.get("extra") or {})
    elif args.da_db:
        grezze = righe_db(da, a)
        fonte = "DB monitor_metrics"
        for nome, fn in (("crash", lambda: crash_dal_db(da, a)),
                         ("raccoglitori", vitalita_raccoglitori),
                         ("eventi_con_soldi", lambda: eventi_con_soldi(da, a))):
            try:
                extra[nome] = fn()
            except Exception as e:  # noqa: BLE001 - fonte accessoria: si dichiara
                extra[nome + "_errore"] = f"{type(e).__name__}: {str(e)[:160]}"
    else:
        grezze = righe_locali(Path(args.locale), args.giorno)
        fonte = f"righe locali {args.locale}"
    righe = filtra_giorno(grezze, da, a)
    if args.salva_righe:
        with open(args.salva_righe, "w", encoding="ascii", newline="\n") as fh:
            json.dump({"righe": righe, "extra": extra}, fh, sort_keys=True, ensure_ascii=True, default=str)
    if args.log_dir:
        extra["log"] = log_del_giorno(Path(args.log_dir), da, a)
        try:
            extra["tempi_ordine"] = tempi_ordine(Path(args.log_dir), da, a)
        except Exception as e:  # noqa: BLE001
            extra["tempi_ordine_errore"] = str(e)[:160]
    if args.raw_dir:
        extra["feed"] = feed_per_partita(Path(args.raw_dir), da, a, extra.get("eventi_con_soldi"))
    r = costruisci(args.giorno, righe, fonte=fonte, extra=extra)
    pm, pj = scrivi(r, Path(args.uscita))
    print(f"referto: {pm} ({len(righe)} righe, impronta {r['impronta_righe']})")
    for v in r["verdetti"]:
        print(f"  {v['esito']:<13} {v['grandezza']}: {_f(v['valore'])} (obiettivo {v['obiettivo']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
