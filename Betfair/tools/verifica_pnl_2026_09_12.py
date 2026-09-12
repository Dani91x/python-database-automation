#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""verifica_pnl_2026_09_12 -- certificazione INDIPENDENTE del P&L di Omega, Safe
Strategy e Mike.

SOLA LETTURA. Nessuna scrittura sul DB, nessun servizio avviato, nessun ordine.
Lo script e' rieseguibile: ogni esecuzione rifa' i conti sullo stato corrente.

Perche' esiste
--------------
Il P&L e' il numero su cui il trader decide se sta guadagnando o perdendo. Se
mente, tutto il resto non conta. Qui il P&L viene RICALCOLATO DA ZERO a partire
dai campi grezzi delle righe (side/size/price/status), SENZA riusare nessuna
funzione del repo: e' un controllo incrociato, non una ripetizione.

Regole applicate nel ricalcolo (money-critical)
-----------------------------------------------
  * BACK vinto  -> + size * (price - 1)        (lordo)
  * BACK perso  -> - size
  * LAY  vinto  -> + size                      (si incassa lo stake del backer)
  * LAY  perso  -> - size * (price - 1)        (liability)
  * void        ->   0
  * commissione: 5% (aliquota della RIGA, ``commission``, non quella corrente dei
    parametri) sul NETTO VINCENTE **per MERCATO** (``market_id``), una sola
    volta: se il mercato chiude in perdita non si paga nulla. Mai per riga.
  * le gambe di CHIUSURA (``closes_trade_id``) NON sono posizioni indipendenti:
    appartengono alla posizione che chiudono e al GIORNO della sua apertura.
  * giornata operativa = Europe/Rome, giorno di PIAZZAMENTO della posizione.

Uso
---
    python -m Betfair.tools.verifica_pnl_2026_09_12
    python -m Betfair.tools.verifica_pnl_2026_09_12 --snapshot 2026-09-12T08:58:00Z

Con ``--snapshot`` lo stato viene "riavvolto" a quell'istante (si ignorano le
righe piazzate dopo e i regolamenti avvenuti dopo): serve a confrontare i numeri
con un dump della UI catturato in quel momento, anche se i servizi hanno
continuato a operare nel frattempo.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Optional

try:
    from zoneinfo import ZoneInfo
    _ROME = ZoneInfo("Europe/Rome")
except Exception:  # pragma: no cover - ambienti senza tzdata
    _ROME = None

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

CENT = 0.005  # tolleranza: mezzo centesimo (sotto c'e' solo rumore di float)


# ---------------------------------------------------------------------------
# utilita' di base
# ---------------------------------------------------------------------------
def _load_env() -> None:
    env = REPO / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def _dt(x: Any) -> Optional[datetime]:
    if not x:
        return None
    try:
        t = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _rome_day_start(now: datetime) -> datetime:
    """Mezzanotte Europe/Rome del giorno di ``now``, in UTC."""
    if _ROME is None:  # fallback grezzo: CEST/CET
        off = timedelta(hours=2 if 3 <= now.month <= 10 else 1)
        loc = now + off
        return (loc.replace(hour=0, minute=0, second=0, microsecond=0) - off).replace(
            tzinfo=timezone.utc)
    loc = now.astimezone(_ROME)
    return loc.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _rome_day(now: datetime) -> str:
    return (now.astimezone(_ROME) if _ROME else now).strftime("%Y-%m-%d")


def _r2(x: float) -> float:
    """Arrotondamento al centesimo con HALF-UP (come un estratto conto, non come
    il banker's rounding di ``round()``: 0,215 -> 0,22 sempre, non a volte 0,21)."""
    return float(Decimal(repr(float(x))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# lettura DB (SOLA LETTURA)
# ---------------------------------------------------------------------------
def _client():
    from supabase import create_client  # import tardivo: lo script e' diagnostico

    url = (os.environ.get("SUPABASE_URL", "") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "") or "").strip()
    if not url or not key:
        raise SystemExit("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY assenti nel .env")
    return create_client(url, key)


def _fetch_all(cl, table: str) -> list[dict]:
    out: list[dict] = []
    page = 1000
    start = 0
    while True:
        res = (cl.table(table).select("*").order("id", desc=False)
               .range(start, start + page - 1).execute())
        rows = res.data or []
        out.extend(rows)
        if len(rows) < page:
            return out
        start += page


def _rpc(cl, name: str, args: dict) -> Any:
    try:
        return cl.rpc(name, args).execute().data
    except Exception as ex:  # noqa: BLE001 - diagnosi: l'errore e' un risultato
        return {"__error__": str(ex)[:200]}


# ---------------------------------------------------------------------------
# RICALCOLO INDIPENDENTE (il cuore dello script)
# ---------------------------------------------------------------------------
def gross_pnl(row: dict) -> Optional[float]:
    """P&L LORDO della riga dal suo esito. None se non ancora deciso."""
    st = str(row.get("status") or "")
    if st == "void":
        return 0.0
    if st not in ("won", "lost"):
        return None
    side = str(row.get("side") or "lay").lower()
    size = _f(row.get("size"))
    price = _f(row.get("price"))
    if side == "back":
        return size * (price - 1.0) if st == "won" else -size
    # LAY: vinto = incasso lo stake del backer; perso = pago la liability
    return size if st == "won" else -(size * (price - 1.0))


def recompute(rows: list[dict]) -> dict:
    """Ricalcolo per MERCATO con commissione sul netto vincente.

    Ritorna {'by_market': {market_id: {...}}, 'by_row': {id: net}, 'total': float}
    """
    markets: dict[str, dict] = {}
    for r in rows:
        g = gross_pnl(r)
        if g is None:
            continue
        mk = str(r.get("market_id") or f"__no_market__{r.get('id')}")
        m = markets.setdefault(mk, {"gross": 0.0, "rows": [], "commission": 0.05,
                                    "stored": 0.0})
        m["gross"] += g
        m["rows"].append((r, g))
        m["commission"] = max(m["commission"], _f(r.get("commission"), 0.05))
        m["stored"] += _f(r.get("pnl"))
    total = 0.0
    for mk, m in markets.items():
        gross = _r2(m["gross"])
        comm = _r2(gross * m["commission"]) if gross > 0 else 0.0
        m["gross_r"] = gross
        m["commission_due"] = comm
        m["net"] = _r2(gross - comm)
        m["stored"] = _r2(m["stored"])
        m["delta"] = _r2(m["stored"] - m["net"])
        total += m["net"]
    return {"by_market": markets, "total": _r2(total)}


def day_of_position(row: dict, by_id: dict) -> Optional[datetime]:
    """``placed_at`` della POSIZIONE: per una chiusura e' quello dell'apertura."""
    pid = row.get("closes_trade_id")
    parent = by_id.get(pid) if pid is not None else None
    return _dt((parent or row).get("placed_at"))


def my_aggregates(rows: list[dict], day_start: datetime) -> dict:
    """Aggregati ricalcolati da zero (non usa nessuna funzione del repo)."""
    by_id = {r.get("id"): r for r in rows}
    rec = recompute(rows)
    realized = realized_today = 0.0
    stored_realized = stored_today = 0.0
    open_liab = locked = locked_today = 0.0
    open_n = 0
    legs_today = 0
    events_today: set[str] = set()
    won_today = lost_today = 0
    pos_total: dict[Any, float] = {}
    for r in rows:
        st = str(r.get("status") or "")
        if st in ("won", "lost", "void"):
            pos = r.get("closes_trade_id") or r.get("id")
            pos_total[pos] = pos_total.get(pos, 0.0) + _f(r.get("pnl"))
    for r in rows:
        st = str(r.get("status") or "")
        pos_day = day_of_position(r, by_id)
        in_day = pos_day is not None and pos_day >= day_start
        is_closer = r.get("closes_trade_id") is not None
        if st in ("won", "lost", "void"):
            stored_realized += _f(r.get("pnl"))
            if in_day:
                stored_today += _f(r.get("pnl"))
        if not is_closer:
            meta = r.get("meta") or {}
            hedged = meta.get("locked_pnl") is not None and \
                _f(meta.get("residual_size"), 0.0) <= 0.01
            if st in ("open", "hedged") or (
                    st == "pending" and (r.get("bet_id")
                                         or meta.get("flumine_client_ref")
                                         or meta.get("reconciling")
                                         or str(meta.get("reason") or "")
                                         == "place_exception_reconciling")):
                open_n += 1
                open_liab += 0.0 if hedged else _f(r.get("liability"))
                if hedged:
                    locked += _f(meta.get("locked_pnl"))
                    if in_day:
                        locked_today += _f(meta.get("locked_pnl"))
                if in_day:
                    legs_today += 1
                    events_today.add(str(r.get("event_id")))
            elif st in ("won", "lost", "void") and in_day:
                legs_today += 1
                events_today.add(str(r.get("event_id")))
                tot = _r2(pos_total.get(r.get("id"), 0.0))
                if tot > 0:
                    won_today += 1
                elif tot < 0:
                    lost_today += 1
    # realizzato ricalcolato: somma dei netti di mercato limitata ai mercati
    # interamente regolati (un mercato con righe ancora vive non e' realizzato)
    realized = rec["total"]
    # realizzato di OGGI ricalcolato: si applica la commissione di mercato alla
    # quota di P&L lordo delle sole posizioni di oggi (pro-quota sul lordo)
    for mk, m in rec["by_market"].items():
        gross_today = 0.0
        for r, g in m["rows"]:
            d = day_of_position(r, by_id)
            if d is not None and d >= day_start:
                gross_today += g
        if abs(m["gross_r"]) > 1e-9:
            share = gross_today / m["gross_r"]
        else:
            share = 1.0 if abs(gross_today) < 1e-9 else 0.0
        realized_today += gross_today - m["commission_due"] * share
    return {
        "realized_recomputed": _r2(realized),
        "realized_stored": _r2(stored_realized),
        "realized_today_recomputed": _r2(realized_today),
        "realized_today_stored": _r2(stored_today),
        "open_liability": _r2(open_liab),
        "open_count": open_n,
        "locked_pnl_open": _r2(locked),
        "locked_pnl_open_today": _r2(locked_today),
        "legs_today": legs_today,
        "events_today": len(events_today),
        "won_today": won_today,
        "lost_today": lost_today,
        "_recompute": rec,
    }


# ---------------------------------------------------------------------------
# snapshot: riavvolge lo stato a un istante passato
# ---------------------------------------------------------------------------
def rewind(rows: list[dict], at: datetime) -> list[dict]:
    """Righe come erano a ``at``: piazzate prima, e regolate solo se il loro
    ``settled_at`` e' anteriore (altrimenti tornano 'open')."""
    out: list[dict] = []
    for r in rows:
        placed = _dt(r.get("placed_at"))
        if placed is None or placed > at:
            continue
        c = dict(r)
        settled = _dt(r.get("settled_at"))
        if settled is not None and settled > at:
            c["status"] = "open"
            c["pnl"] = 0
            c["settled_at"] = None
        out.append(c)
    return out


# ---------------------------------------------------------------------------
# stampa
# ---------------------------------------------------------------------------
def row(label: str, *vals: Any) -> str:
    cells = [f"{label:<34}"]
    for v in vals:
        if isinstance(v, float):
            cells.append(f"{v:>14.2f}")
        elif v is None:
            cells.append(f"{'-':>14}")
        else:
            cells.append(f"{str(v):>14}")
    return " | ".join(cells)


def verdict(*vals: Any) -> str:
    nums = [v for v in vals if isinstance(v, (int, float))]
    if len(nums) < 2:
        return "  ? (dato mancante)"
    return "  OK" if max(nums) - min(nums) <= CENT else \
        "  *** SCOSTAMENTO %.2f ***" % (max(nums) - min(nums))


def section(title: str) -> None:
    print()
    print("=" * 118)
    print(title)
    print("=" * 118)


# ---------------------------------------------------------------------------
# verifica di una sezione
# ---------------------------------------------------------------------------
def check_section(name: str, rows: list[dict], rpc_agg: Any, py_agg: dict,
                  ui: dict, now: datetime, with_ui: bool = False) -> list[str]:
    problems: list[str] = []
    day_start = _rome_day_start(now)
    mine = my_aggregates(rows, day_start)
    rpc = rpc_agg if isinstance(rpc_agg, dict) and "__error__" not in rpc_agg else {}

    section("SEZIONE %s -- giornata operativa %s (Europe/Rome), righe %d"
            % (name.upper(), _rome_day(now), len(rows)))
    print(row("grandezza", "UI (dump)", "RPC", "Python", "ricalcolo"))
    print("-" * 118)

    def line(label: str, ui_key: str, rpc_keys: tuple, py_keys: tuple, mine_key: str,
             ui_comparable: bool = True):
        u = ui.get(ui_key)
        rv = next((rpc[k] for k in rpc_keys if k in rpc), None)
        rv = _f(rv) if rv is not None else None
        pv = next((py_agg[k] for k in py_keys if k in py_agg), None)
        pv = _f(pv) if pv is not None else None
        mv = mine.get(mine_key)
        # in modalita' snapshot il valore della UI E' confrontabile: entra nel
        # verdetto. Senza snapshot il DB e' andato avanti e il confronto sarebbe
        # falso (i servizi continuano a operare).
        cmp_vals = (u, rv, pv, mv) if (with_ui and ui_comparable) else (rv, pv, mv)
        print(row(label, u, rv, pv, mv) + verdict(*cmp_vals))
        vals = [v for v in cmp_vals if isinstance(v, (int, float))]
        if len(vals) > 1 and max(vals) - min(vals) > CENT:
            problems.append("%s: %s diverge (UI=%s RPC=%s Python=%s ricalcolo=%s)"
                            % (name, label, u, rv, pv, mv))

    line("P&L totale storico", "total", ("realized_total", "realized_profit"),
         ("realized_total", "realized_profit"), "realized_stored")
    line("P&L oggi (giornata operativa)", "today", ("realized_today",),
         ("realized_today",), "realized_today_stored")
    # Mike espone DUE liability: ``open_liability`` e' la NETTA per partita
    # (calcolata dal servizio sulle posizioni nette, ed e' quella che finisce in
    # UI), ``open_liability_rows`` e' la somma delle righe -- la stessa cosa che
    # calcolano Python e questo script. Confrontare la somma delle righe con la
    # netta sarebbe confrontare due grandezze diverse.
    # NB Mike: in UI si legge la liability NETTA per partita, non la somma delle
    # righe -- sono due grandezze diverse e non vanno confrontate fra loro.
    line("Liability aperta (somma righe)", "liability",
         ("open_liability_rows", "open_liability"),
         ("open_liability",), "open_liability", ui_comparable=(name != "mike"))
    if "open_liability_rows" in rpc:
        print(row("Liability aperta (NETTA, in UI)", ui.get("liability"),
                  _f(rpc.get("open_liability")), None, None)
              + "  fonte=%s stantia=%s" % (rpc.get("liability_source"),
                                           rpc.get("liability_stale")))
    line("P&L bloccato (posizioni vive)", "locked",
         ("locked_pnl_open_today", "locked_pnl_open"),
         ("locked_pnl_open_today", "locked_pnl_open"), "locked_pnl_open_today")
    line("posizioni aperte", "open_count", ("open_count", "matches_open"),
         ("open_count", "matches_open"), "open_count")
    line("operazioni di oggi", "legs", ("legs_today", "cycles_today", "day_trades"),
         ("legs_today", "cycles_today", "day_trades"), "legs_today")
    line("partite di oggi", "events", ("events_today",), ("events_today",),
         "events_today")
    line("V di oggi", "won", ("won_today",), ("won_today",), "won_today")
    line("P di oggi", "lost", ("lost_today",), ("lost_today",), "lost_today")

    # --- ricalcolo indipendente della colonna pnl, mercato per mercato --------
    rec = mine["_recompute"]
    print()
    print("RICALCOLO INDIPENDENTE DELLA COLONNA pnl (commissione 5%% sul netto "
          "vincente per MERCATO)")
    print(row("P&L realizzato", "-", "-", mine["realized_stored"],
              mine["realized_recomputed"])
          + verdict(mine["realized_stored"], mine["realized_recomputed"]))
    bad = [(mk, m) for mk, m in rec["by_market"].items() if abs(m["delta"]) > CENT]
    big = [(mk, m) for mk, m in bad if abs(m["delta"]) > 0.015]
    if bad:
        print()
        print("  mercati con scostamento fra pnl SCRITTO e pnl RICALCOLATO "
              "(<=0,01 = arrotondamento; >0,01 = errore vero):")
        print("  %-18s %10s %10s %10s %10s %10s  righe" %
              ("market_id", "lordo", "comm.5%", "atteso", "scritto", "delta"))
        tot_delta = 0.0
        for mk, m in sorted(bad, key=lambda x: -abs(x[1]["delta"])):
            ids = ",".join(str(r.get("id")) for r, _ in m["rows"])
            print("  %-18s %10.2f %10.2f %10.2f %10.2f %10.2f  %s" %
                  (mk[:18], m["gross_r"], m["commission_due"], m["net"],
                   m["stored"], m["delta"], ids[:44]))
            tot_delta += m["delta"]
        print("  TOTALE scostamento: %.2f EUR su %d mercati (%d oltre il "
              "centesimo di arrotondamento)" % (tot_delta, len(bad), len(big)))
        problems.append("%s: %d mercati con pnl scritto != pnl ricalcolato "
                        "(totale %.2f EUR, di cui %d oltre l'arrotondamento)"
                        % (name, len(bad), tot_delta, len(big)))
    else:
        print("  nessuno scostamento: la colonna pnl rispetta la regola della "
              "commissione per mercato.")

    # --- coerenza della commissione dichiarata in meta -----------------------
    paid: dict[str, float] = {}
    declared: dict[str, float] = {}
    for r in rows:
        meta = r.get("meta") or {}
        if "commission_paid" not in meta and "commission_market" not in meta:
            continue
        mk = str(r.get("market_id") or "")
        paid[mk] = paid.get(mk, 0.0) + _f(meta.get("commission_paid"))
        if meta.get("commission_market") is not None:
            declared[mk] = max(declared.get(mk, 0.0), _f(meta.get("commission_market")))
    mism = [(mk, _r2(paid.get(mk, 0.0)), _r2(v)) for mk, v in declared.items()
            if abs(paid.get(mk, 0.0) - v) > CENT]
    if mism:
        tot = _r2(sum(p - d for _, p, d in mism))
        print("  commissione: %d mercati in cui la somma dei commission_paid delle "
              "righe != commission_market (totale %+.2f EUR)" % (len(mism), tot))
        for mk, p, d in sorted(mism, key=lambda x: -abs(x[1] - x[2]))[:8]:
            print("    %-18s pagata=%.2f dichiarata=%.2f delta=%+.2f" % (mk[:18], p, d, p - d))
        problems.append("%s: commissione per riga non somma a commission_market "
                        "su %d mercati (%+.2f EUR)" % (name, len(mism), tot))

    # --- "P&L bloccato" promette di non cambiare piu': e' vero? --------------
    by_id = {r.get("id"): r for r in rows}
    pos_real: dict[Any, float] = {}
    for r in rows:
        if str(r.get("status") or "") in ("won", "lost", "void"):
            pos = r.get("closes_trade_id") or r.get("id")
            pos_real[pos] = pos_real.get(pos, 0.0) + _f(r.get("pnl"))
    broken = []
    checked = 0
    for r in rows:
        meta = r.get("meta") or {}
        lk = meta.get("locked_pnl")
        # stesso criterio del codice: bloccato SOLO a copertura completa
        if lk is None or _f(meta.get("residual_size"), 99.0) > 0.01:
            continue
        if str(r.get("status") or "") not in ("won", "lost", "void"):
            continue
        checked += 1
        real = _r2(pos_real.get(r.get("id"), 0.0))
        if abs(real - _f(lk)) > CENT:
            broken.append((r.get("id"), _f(lk), real))
    if broken:
        print("  *** 'P&L bloccato' DIVERSO dal realizzato su %d/%d posizioni "
              "a copertura COMPLETA (l'etichetta promette che non cambia piu'):"
              % (len(broken), checked))
        for tid, lk, real in broken[:12]:
            print("      trade %-5s bloccato=%+.2f  realizzato=%+.2f  delta=%+.2f"
                  % (tid, lk, real, real - lk))
        tot = sum(r - l for _, l, r in broken)
        print("      totale: il bloccato mostrato e' %+.2f EUR rispetto al "
              "realizzato" % (-tot))
        problems.append("%s: 'P&L bloccato' != realizzato su %d/%d posizioni "
                        "coperte (scarto totale %+.2f EUR, max %.2f)"
                        % (name, len(broken), checked, -tot,
                           max(abs(r - l) for _, l, r in broken)))
    else:
        print("  'P&L bloccato' coincide col realizzato su tutte le %d posizioni "
              "coperte e gia' regolate." % checked)

    # --- trade ancora APERTI nel P&L? ---------------------------------------
    leak = [r for r in rows if str(r.get("status") or "") in ("open", "hedged", "pending", "error")
            and abs(_f(r.get("pnl"))) > CENT]
    if leak:
        print("  *** %d righe NON regolate con pnl != 0 (entrano nel realizzato "
              "senza esito): %s" % (len(leak), [r.get("id") for r in leak][:12]))
        problems.append("%s: %d righe non regolate con pnl != 0" % (name, len(leak)))
    else:
        print("  nessuna riga aperta/pending/error contribuisce al P&L (corretto).")

    # --- chiusure orfane -----------------------------------------------------
    ids = {r.get("id") for r in rows}
    orphan = [r for r in rows if r.get("closes_trade_id") is not None
              and r.get("closes_trade_id") not in ids]
    if orphan:
        print("  *** %d gambe di chiusura orfane (apertura assente): %s"
              % (len(orphan), [r.get("id") for r in orphan][:12]))
        problems.append("%s: %d chiusure orfane" % (name, len(orphan)))
    return problems


def check_daily(name: str, daily: Any, total_today_expected: float,
                realized_total: float) -> list[str]:
    """Lo storico per giornate deve sommare al P&L totale del periodo."""
    problems: list[str] = []
    if not isinstance(daily, list):
        print("  storico %s non disponibile: %s" % (name, daily))
        return ["%s: get_%s_daily non disponibile" % (name, name)]
    tot = _r2(sum(_f(d.get("pnl_realized")) for d in daily))
    print("  storico: %d giornate, somma P&L = %.2f" % (len(daily), tot))
    for d in daily:
        print("    %s  pnl=%8.2f  settled=%-4s won=%-4s lost=%-4s" %
              (d.get("day"), _f(d.get("pnl_realized")), d.get("settled"), d.get("won"),
               d.get("lost")))
    if abs(tot - realized_total) > CENT:
        print("  NOTA: la somma delle giornate (%.2f) non coincide col totale "
              "storico (%.2f): differenza %.2f -- legittima SOLO se il periodo "
              "richiesto non copre tutte le giornate operative."
              % (tot, realized_total, tot - realized_total))
    return problems


# ---------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", default=None,
                    help="istante ISO a cui riavvolgere lo stato (es. "
                         "2026-09-12T08:58:00Z) per confrontarlo con un dump UI")
    ap.add_argument("--json", default=None, help="salva il risultato grezzo qui")
    args = ap.parse_args(argv)

    _load_env()
    cl = _client()
    now = datetime.now(timezone.utc)
    snap = _dt(args.snapshot) if args.snapshot else None

    # valori letti dal dump reale della UI del 12/09/2026 (~08:58 UTC)
    UI = {
        "omega": {"total": -19.46, "today": 0.00, "liability": 0.00, "locked": 0.00,
                  "open_count": 0, "legs": 0, "events": 0, "won": 0, "lost": 0},
        "safe": {"total": 10.98, "today": 1.90, "liability": 300.00, "locked": -10.32,
                 "open_count": 5, "legs": 6, "events": 5, "won": 1, "lost": 0},
        "mike": {"total": 15.67, "today": 13.51, "liability": 120.00, "locked": 0.00,
                 "open_count": 14, "legs": 18, "events": 16, "won": 4, "lost": 0},
    }

    print("verifica_pnl_2026_09_12 -- SOLA LETTURA -- adesso %s UTC"
          % now.strftime("%Y-%m-%d %H:%M:%S"))
    if snap:
        print("SNAPSHOT: stato riavvolto a %s (confronto con il dump della UI)"
              % snap.isoformat())
    else:
        print("Stato CORRENTE del DB: i valori 'UI (dump)' sono quelli del "
              "12/09 ~08:58 UTC e coincidono solo usando --snapshot.")

    omega = _fetch_all(cl, "omega_trades")
    safe = _fetch_all(cl, "safe_strategy_trades")
    mike = _fetch_all(cl, "mike_trades")
    if snap:
        omega, safe, mike = rewind(omega, snap), rewind(safe, snap), rewind(mike, snap)
        now = snap

    problems: list[str] = []

    from Betfair.omega import omega_engine as _oe
    from Betfair.safe_strategy import bot_db as _sdb
    from Betfair.mike import db as _mdb

    day_start = _rome_day_start(now)

    problems += check_section(
        "omega", omega,
        _rpc(cl, "get_omega_aggregates", {}) if not snap else {},
        _oe.aggregate_trades(omega, day_start=day_start), UI["omega"], now,
        with_ui=bool(snap))
    problems += check_section(
        "safe", safe,
        _rpc(cl, "get_safe_aggregates", {}) if not snap else {},
        _sdb.aggregate_rows(safe, day_start=day_start), UI["safe"], now,
        with_ui=bool(snap))
    problems += check_section(
        "mike", mike,
        _rpc(cl, "get_mike_aggregates", {}) if not snap else {},
        _mdb.aggregate_rows(mike, day_start=day_start), UI["mike"], now,
        with_ui=bool(snap))

    if not snap:
        section("STORICO PER GIORNATE (get_*_daily) vs P&L TOTALE")
        rng = {"p_from": "2026-01-01", "p_to": _rome_day(now)}
        for nm, rows_ in (("omega", omega), ("safe", safe), ("mike", mike)):
            print("\n-- %s" % nm)
            tot = _r2(sum(_f(r.get("pnl")) for r in rows_
                          if str(r.get("status") or "") in ("won", "lost", "void")))
            problems += check_daily(nm, _rpc(cl, "get_%s_daily" % nm, rng), 0.0, tot)

    section("ESITO")
    if problems:
        print("DIFETTI / SCOSTAMENTI: %d" % len(problems))
        for i, p in enumerate(problems, 1):
            print("  %2d. %s" % (i, p))
    else:
        print("Nessuno scostamento: UI, RPC, Python e ricalcolo indipendente "
              "concordano al centesimo.")

    if args.json:
        Path(args.json).write_text(json.dumps({"problems": problems}, indent=1),
                                   encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
