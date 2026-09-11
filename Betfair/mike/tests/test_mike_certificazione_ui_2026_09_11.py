"""Certificazione MIKE end-to-end UI <-> servizio (11/09/2026).

Questo file chiude i buchi della checklist di certificazione:

  1. CONTRATTO DATI — ogni chiave che la UI LEGGE esiste, con lo stesso nome e
     tipo, fra quelle che il servizio SCRIVE (e viceversa per quelle utili al
     trader). I test leggono direttamente ``frontend/src/lib/mike.ts``: se il
     backend aggiunge un parametro, un kind di attivita', uno stato, un ruolo o
     un codice di esito senza dichiararlo nella UI, QUESTI TEST FALLISCONO.
  2. PULSANTI — per ogni comando della UI (Cash out / Flatten / Annulla ordini /
     Salta / Riprendi) il codice di esito che il servizio restituisce e lo
     ``status`` con cui la richiesta viene chiusa.
  3. NUMERI — la somma delle righe di regolamento e' il P&L della partita; il
     "se chiudo ora" pubblicato e' NETTO; l'eta' del feed per partita nasce da
     ``safe_strategy_scan.updated_at``.

Nessuna rete, nessun Supabase. File ASCII-only (console Windows cp1252).
"""
from __future__ import annotations

import dataclasses
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import feed as F
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_feed import payload, row
from Betfair.mike.tests.test_mike_service import FakeDB, FakeMarket

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "migrations"
FRONTEND = ROOT / "frontend" / "src"
MIKE_TS = (FRONTEND / "lib" / "mike.ts").read_text(encoding="utf-8")
CARD_TS = (FRONTEND / "components" / "mike" / "MikeMatchCard.tsx").read_text(encoding="utf-8")
PAGE_TS = (FRONTEND / "pages" / "Mike.tsx").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Lettori del data-layer TypeScript (nessuna dipendenza: solo regex)
# ---------------------------------------------------------------------------
def _ts_block(src: str, start: str, end: str) -> str:
    assert start in src, f"blocco non trovato nel TS: {start}"
    return src.split(start, 1)[1].split(end, 1)[0]


def ts_string_list(name: str) -> list[str]:
    """``export const NAME = ['a', 'b'] ...`` -> ['a', 'b'] (con o senza as const)."""
    blk = MIKE_TS.split(f"{name}", 1)[1]
    blk = blk.split("= [", 1)[1].split("]", 1)[0]
    return re.findall(r"'([A-Za-z0-9_]+)'", blk)


def ts_record_keys(name: str) -> list[str]:
    """chiavi di primo livello di ``export const NAME: Record<...> = { ... };``

    Le mappe di Mike mettono piu' chiavi per riga: si prende ogni ``chiave:``
    che NON e' dentro un oggetto annidato (profondita' 1).
    """
    blk = _ts_block(MIKE_TS, f"{name}", "\n};")
    blk = blk.split("{", 1)[1]
    out: list[str] = []
    depth = 0
    token = ""
    for i, ch in enumerate(blk):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == ":" and depth == 0:
            key = token.strip().strip("'\"")
            if re.fullmatch(r"[A-Za-z0-9_]+", key):
                out.append(key)
            token = ""
            continue
        if ch in ",\n" and depth == 0:
            token = ""
        elif depth == 0:
            token += ch
        _ = i
    return out


def ts_interface_keys(name: str) -> list[str]:
    blk = _ts_block(MIKE_TS, f"export interface {name} {{", "\n}")
    return re.findall(r"^\s{4}([A-Za-z0-9_]+)\??:", blk, re.M)


def ts_param_fields() -> dict[str, dict]:
    blk = _ts_block(MIKE_TS, "MIKE_PARAM_FIELDS: readonly MikeParamField[] = [", "\n];")
    out: dict[str, dict] = {}
    for m in re.finditer(r"\{ key: '([a-z0-9_]+)'.*?\}", blk):
        line, key = m.group(0), m.group(1)
        d: dict = {"kind": re.search(r"kind: '(\w+)'", line).group(1)}
        for att in ("min", "max", "step"):
            got = re.search(rf"{att}: ([0-9_.]+)", line)
            if got:
                d[att] = float(got.group(1).replace("_", ""))
        choices = re.search(r"choices: \[([^\]]+)\]", line)
        if choices:
            d["choices"] = tuple(x.strip().strip("'") for x in choices.group(1).split(","))
        out[key] = d
    return out


def ts_param_defaults() -> dict:
    blk = _ts_block(MIKE_TS, "MIKE_PARAM_DEFAULTS: Record<string, number | boolean | string> = {", "\n};")
    out: dict = {}
    for m in re.finditer(r"([a-z0-9_]+):\s*('[^']*'|true|false|[0-9_.]+)", blk):
        key, raw = m.group(1), m.group(2)
        if raw.startswith("'"):
            out[key] = raw.strip("'")
        elif raw in ("true", "false"):
            out[key] = raw == "true"
        else:
            out[key] = float(raw.replace("_", ""))
    return out


def backend_activity_kinds() -> set[str]:
    """Kind che il servizio SCRIVE davvero in ``mike_activity``.

    Tre sorgenti: ``db.log("kind"`` , ``_log_throttled(..., "kind"`` e la
    tupla della telemetria (``pre_cycle``/``cover``/... loggati in ciclo).
    """
    found: set[str] = set()
    for name in ("service.py", "engine.py", "db.py", "feed.py", "dossier.py"):
        src = (Path(S.__file__).parent / name).read_text(encoding="utf-8")
        found |= set(re.findall(r"\blog\(\s*\"([a-z_]+)\"", src))
        found |= set(re.findall(
            r"_log_throttled\(\s*db,\s*extra,\s*params,\s*now_ts,\s*\"([a-z_]+)\"", src))
    src = Path(S.__file__).read_text(encoding="utf-8")
    tele = re.search(r"for k, v in d\.telemetry\.items\(\):.*?if k in \(([^)]*)\)", src, re.S)
    assert tele, "tupla della telemetria non trovata in service.py"
    logged_tele = set(re.findall(r"\"([a-z_]+)\"", tele.group(1)))
    # dentro il ramo, questi tre finiscono in ``extra`` (non sono attivita')
    return found | (logged_tele - {"cashout", "cover_wait", "loss_exit"})


# ===========================================================================
# 1. CONTRATTO DATI — parametri
# ===========================================================================
def test_contratto_parametri_stesse_chiavi_in_ui_e_backend():
    fields, defaults = ts_param_fields(), ts_param_defaults()
    assert set(fields) == set(C.PARAM_SPEC), {
        "solo_ui": sorted(set(fields) - set(C.PARAM_SPEC)),
        "solo_backend": sorted(set(C.PARAM_SPEC) - set(fields)),
    }
    assert set(defaults) == set(C.PARAM_SPEC), {
        "default_solo_ui": sorted(set(defaults) - set(C.PARAM_SPEC)),
        "default_mancanti": sorted(set(C.PARAM_SPEC) - set(defaults)),
    }


def test_contratto_parametri_stessi_clamp_scelte_e_default():
    fields, defaults = ts_param_fields(), ts_param_defaults()
    kind_of = {bool: "bool", int: "number", float: "number"}
    for key, (default, cast, lo, hi, choices) in C.PARAM_SPEC.items():
        f = fields[key]
        expected_kind = kind_of.get(cast, "choice" if choices else "text")
        assert f["kind"] == expected_kind, f"{key}: kind UI {f['kind']} != {expected_kind}"
        if choices is not None:
            assert tuple(f["choices"]) == tuple(choices), key
        elif cast in (int, float):
            if lo is not None:
                assert f["min"] == float(lo), f"{key}: min UI {f['min']} != {lo}"
            if hi is not None:
                assert f["max"] == float(hi), f"{key}: max UI {f['max']} != {hi}"
        ui_default = defaults[key]
        if isinstance(default, bool):
            assert bool(ui_default) is bool(default), key
        elif isinstance(default, str):
            assert ui_default == default, key
        else:
            assert float(ui_default) == pytest.approx(float(default)), key


def test_contratto_parametri_i_rimossi_non_tornano_in_ui():
    fields = ts_param_fields()
    for key in C.REMOVED_PARAMS:
        assert key not in fields, f"{key} e' stato rimosso dalla whitelist ma la UI lo mostra ancora"


# ===========================================================================
# 1. CONTRATTO DATI — attivita', stati, ruoli, esiti
# ===========================================================================
def test_contratto_ogni_kind_di_attivita_del_backend_e_dichiarato_in_ui():
    """Il test FALLISCE se il backend aggiunge un kind senza dichiararlo."""
    declared = set(ts_string_list("MIKE_ACTIVITY_KINDS"))
    found = backend_activity_kinds()
    assert found - declared == set(), f"kind scritti dal servizio e MUTI in UI: {sorted(found - declared)}"
    assert declared - found == set(), f"kind dichiarati in UI e mai scritti: {sorted(declared - found)}"


def test_contratto_stati_evento_identici_e_con_gruppo():
    ui = ts_string_list("MIKE_STATES")
    assert ui == list(E.STATES)
    assert set(ts_string_list("MIKE_TERMINAL_STATES")) == set(E.TERMINAL_STATES)
    # ogni stato ha una etichetta ITALIANA e un gruppo dichiarato
    meta = _ts_block(MIKE_TS, "MIKE_PHASE_META: Record<MikeState, PhaseMeta> = {", "\n};")
    groups = dict(re.findall(r"^\s{4}([A-Z_]+): \{.*?group: '(\w+)'", meta, re.M))
    assert set(groups) == set(E.STATES), sorted(set(E.STATES) - set(groups))
    assert set(groups.values()) <= {"pre", "live", "flat", "done", "off"}
    expected = {
        "WATCH": "pre", "PRE_ENTRY_PENDING": "pre", "PRE_OPEN": "pre", "PRE_GREEN_PENDING": "pre",
        "HOLD": "pre", "PRE_LAST_ENTRY_PENDING": "pre",
        "IDLE_LIVE": "live", "LIVE_UNCOVERED": "live", "LIVE_COVER_PENDING": "live",
        "LIVE_COVERED": "live", "LIVE_CLOSING": "live", "REENTRY_PENDING": "live",
        "REENTRY_OPEN": "live", "REENTRY_GREEN_PENDING": "live",
        "FLAT": "flat", "SETTLING": "done", "SETTLED": "done", "ERROR": "off", "SKIPPED": "off",
    }
    assert groups == expected
    # nessuna etichetta in inglese fra quelle dichiarate
    labels = re.findall(r"label: '([^']+)'", meta)
    assert len(labels) == len(E.STATES)
    assert all(lbl == lbl.upper() or "…" in lbl for lbl in labels)


def test_contratto_ruoli_delle_gambe_identici():
    ui = ts_record_keys("MIKE_ROLE_LABEL")
    assert set(ui) == set(E.ROLES), {
        "solo_ui": sorted(set(ui) - set(E.ROLES)), "solo_backend": sorted(set(E.ROLES) - set(ui))}


def test_contratto_codici_di_esito_delle_richieste():
    """Ogni ``result.code`` che il servizio puo' scrivere ha un messaggio italiano."""
    src = Path(S.__file__).read_text(encoding="utf-8")
    codes = set(re.findall(r"_result\(\"([a-z_]+)\"", src))
    db_src = (Path(S.__file__).parent / "db.py").read_text(encoding="utf-8")
    codes |= set(re.findall(r"\"code\": \"([a-z_]+)\"", db_src))
    ui = set(ts_record_keys("MIKE_REQUEST_CODE_MESSAGE"))
    assert codes - ui == set(), f"codici senza messaggio italiano: {sorted(codes - ui)}"
    assert ui - codes == set(), f"messaggi per codici inesistenti: {sorted(ui - codes)}"


def test_contratto_kind_delle_richieste_identici():
    """I `kind` che la UI puo' inviare sono esattamente quelli che il servizio processa."""
    src = Path(S.__file__).read_text(encoding="utf-8")
    body = src.split("def process_requests", 1)[1].split("\ndef _request_cancel", 1)[0]
    handled: set[str] = set()
    for frag in re.findall(r"kind (?:==|!=|in) (\(?[^:\n]+)", body):
        handled |= set(re.findall(r"\"([a-z_]+)\"", frag))
    ui = set(ts_record_keys("MIKE_REQUEST_KIND_LABEL"))
    assert ui == {"cashout", "flatten", "skip_event", "resume_event", "cancel"}
    assert ui - handled == set(), f"kind inviati dalla UI e non gestiti: {sorted(ui - handled)}"


def test_contratto_stati_ammessi_per_una_richiesta():
    """`rejected` = rifiuto ATTESO; la UI lo distingue dall'errore (M1)."""
    assert set(S._REJECT_CODES) <= set(ts_record_keys("MIKE_REQUEST_CODE_MESSAGE"))
    sql = (MIGRATIONS / "mike_bot_v2.sql").read_text(encoding="utf-8")
    assert "'pending','processing','done','rejected','error'" in sql
    blk = _ts_block(MIKE_TS, "export interface MikeRequest {", "\n}")
    for st in ("pending", "processing", "done", "rejected", "error"):
        assert f"'{st}'" in blk, st


# ===========================================================================
# 1. CONTRATTO DATI — gambe, book, cash out, live
# ===========================================================================
def test_contratto_gamba_e_book_hanno_gli_stessi_campi():
    leg = {f.name for f in dataclasses.fields(E.Leg)}
    assert set(ts_interface_keys("MikeLeg")) == leg, {
        "solo_ui": sorted(set(ts_interface_keys("MikeLeg")) - leg),
        "solo_backend": sorted(leg - set(ts_interface_keys("MikeLeg")))}
    book = {f.name for f in dataclasses.fields(E.Book)}
    assert set(ts_interface_keys("MikeBook")) == book


def test_contratto_cashout_pubblicato_dal_servizio_combacia_con_il_tipo_ui():
    src = Path(S.__file__).read_text(encoding="utf-8")
    blk = _ts_block(src, "cashout_live = {", "\n    }")
    written = set(re.findall(r'"([a-z_]+)":', blk))
    written.add("smart")               # aggiunta subito dopo, se il bot l'ha calcolata
    ui = set(ts_interface_keys("MikeCashout"))
    assert written == ui, {"solo_backend": sorted(written - ui), "solo_ui": sorted(ui - written)}


def _live_keys_written() -> set[str]:
    src = Path(S.__file__).read_text(encoding="utf-8")
    blk = _ts_block(src, 'ev["live"] = {"minute"', "\n    ev.update(")
    return set(re.findall(r'"([a-z_0-9]+)":', blk)) | {"minute", "feed_incomplete"}


def test_contratto_live_ogni_chiave_scritta_e_dichiarata_in_ui():
    ui = set(ts_interface_keys("MikeLive"))
    written = _live_keys_written()
    assert written - ui == set(), f"chiavi di live scritte e non dichiarate: {sorted(written - ui)}"
    assert ui - written == set(), f"chiavi di live dichiarate e mai scritte: {sorted(ui - written)}"


def test_contratto_live_ogni_chiave_letta_dalla_card_e_scritta_dal_servizio():
    read = set(re.findall(r"\blive\.([a-z_0-9]+)", CARD_TS))
    read |= set(re.findall(r"\blive\??\.([a-z_0-9]+)", PAGE_TS)) - {"length", "map", "locked"}
    read.add("locked")
    written = _live_keys_written()
    assert read - written == set(), f"la card legge chiavi che nessuno scrive: {sorted(read - written)}"


def test_contratto_ctx_le_bandiere_lette_dalla_ui_sono_persistite():
    """`flatten_pending` e `no_reentry` sopravvivono al round-trip del ctx."""
    for key in ("flatten_pending", "no_reentry"):
        assert key in S._CTX_FIELDS, key
        assert f"ctx.{key}" in MIKE_TS, key
    ctx = E.MatchCtx(state="LIVE_COVERED", legs=[])
    ctx.flatten_pending = True
    ctx.no_reentry = True
    out = S._row_from_ctx({"event_id": "E1"}, ctx, {"selections": {"OU35|UNDER": 1222344}})
    assert out["ctx"]["flatten_pending"] is True and out["ctx"]["no_reentry"] is True
    # `ctx.selections` serve alla card per i tooltip market/selection: non si perde
    assert out["ctx"]["selections"] == {"OU35|UNDER": 1222344}
    assert S._ctx_from_row(out).flatten_pending is True


def test_contratto_meta_di_riga_lette_dalla_tabella_trade():
    """Le chiavi di `meta` che la tabella Trade mostra le scrive il servizio."""
    table = (FRONTEND / "components" / "mike" / "MikeTradesTable.tsx").read_text(encoding="utf-8")
    read = set(re.findall(r"meta\.([a-z_]+)", table)) | set(re.findall(r"meta \?\? \{\}\)\['([a-z_]+)'\]", table))
    src = Path(S.__file__).read_text(encoding="utf-8")
    written = set(re.findall(r'meta(?:_d)?\["([a-z_]+)"\]', src)) | set(re.findall(r'"([a-z_]+)":', src))
    assert read - written == set(), f"meta lette e mai scritte: {sorted(read - written)}"


# ===========================================================================
# 3. TEMPO REALE — tabelle sottoscritte == tabelle scritte dal servizio
# ===========================================================================
def test_realtime_le_tabelle_sottoscritte_sono_quelle_che_il_servizio_scrive():
    ui = ts_string_list("MIKE_REALTIME_TABLES")
    sql = (MIGRATIONS / "mike_bot.sql").read_text(encoding="utf-8")
    published = re.search(r"ARRAY\[('mike_[a-z_]+',?\s*)+\]", sql)
    assert published, "elenco delle tabelle in realtime non trovato in mike_bot.sql"
    tables = re.findall(r"'(mike_[a-z_]+)'", published.group(0))
    assert set(ui) == set(tables), {"solo_ui": sorted(set(ui) - set(tables)),
                                    "solo_sql": sorted(set(tables) - set(ui))}
    # e sono davvero quelle su cui il servizio scrive
    assert set(tables) == {"mike_control", "mike_events", "mike_trades", "mike_activity", "mike_requests"}
    for table in tables:
        assert f"table: '{table}'" in MIKE_TS or f"'{table}'" in MIKE_TS, table


def test_realtime_eta_del_feed_per_partita_nasce_da_safe_strategy_scan():
    """`live.feed_age_s` = ora - `safe_strategy_scan.updated_at` della PARTITA."""
    db = FakeDB(params={"stake": 10})
    mk = FakeMarket()
    stale_at = NOW - timedelta(seconds=12)
    S.run_once(db=db, market=mk, now=NOW, rows=[row(payload(), updated=stale_at)], atlas=None)
    live = db.events["E1"]["live"]
    assert live["feed_age_s"] == pytest.approx(12.0, abs=0.2)
    assert live["scanner_age_s"] is not None
    src = Path(S.__file__).read_text(encoding="utf-8")
    assert 'F.parse_iso_epoch(row.get("updated_at"))' in src
    # la riga arriva da `safe_strategy_scan` (feed unico), mai da una chiamata Betfair
    db_src = (Path(S.__file__).parent / "db.py").read_text(encoding="utf-8")
    fetch = db_src.split("def fetch_scan_rows", 1)[1].split("\ndef ", 1)[0]
    assert 'table("safe_strategy_scan")' in fetch and "updated_at" in fetch


def test_realtime_la_soglia_feed_fermo_della_ui_e_20_secondi():
    blk = _ts_block(MIKE_TS, "export function feedFreshness", "\n}")
    assert "n <= 5" in blk and "n <= 20" in blk and "FEED FERMO" in blk


# ===========================================================================
# 2. PULSANTI — comando della UI -> handler -> codice di esito -> status
# ===========================================================================
def _armed_event(*, positions, state="LIVE_COVERED", ctx=None, ko_offset_h=-1.0):
    return {
        "event_id": "E1", "event_name": "Roma v Lazio", "state": state, "cycle_no": 1,
        "entry_price_initial": 1.5, "competition": "Serie A",
        "markets": {E.MARKET_OU35: {"market_id": "1.35"}, E.MARKET_OU45: {"market_id": "1.45"}},
        "positions": [dataclasses.asdict(l) for l in positions], "dossier": {}, "live": {},
        "mode": "paper", "settled_pnl": None,
        "ko_at": (NOW + timedelta(hours=ko_offset_h)).isoformat(),
        "ctx": ctx if ctx is not None else {"seen_inplay": True},
    }


def _matched(role, market, selection, side, price, size, *, status="open", ref=None):
    leg = E.Leg(role=role, market=market, selection=selection, side=side, price=price, size=size,
                ref=ref or f"{role}-1-1", cycle_no=1, placed_at=NOW.timestamp() - 600)
    leg.matched = size
    leg.avg_price = price
    leg.status = status
    return leg


def _request(db, kind, event_id="E1"):
    db.requests.append({"id": len(db.requests) + 1, "kind": kind,
                        "payload": {"event_id": event_id}, "status": "pending", "result": None})
    return db.requests[-1]


def _process(db, events, rows, *, params=None, now=None):
    params = C.merge_params(params or {"stake": 10})
    S.process_requests(db=db, market=FakeMarket(), events=events,
                       rows_by_event={r["event_id"]: r for r in rows}, params=params,
                       now=now or NOW, dry=False, scanner_age=1.0)


def _outcome(req):
    return req["status"], (req["result"] or {}).get("code")


LIVE_ROW_KW = dict(inplay=True, minute=30, sh=1, sa=0)


def test_pulsante_cash_out_arma_la_chiusura_e_torna_ok():
    db = FakeDB()
    under = _matched("under_last", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 10.0)
    green = E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                  price=1.48, size=10.0, ref="under_green-1-2", cycle_no=1)
    events = {"E1": _armed_event(positions=[under, green])}
    req = _request(db, "cashout")
    _process(db, events, [row(payload(**LIVE_ROW_KW))])
    assert _outcome(req) == ("done", "ok")
    res = req["result"]
    assert res["phase"] == "armed" and res["cancelled"] == 1
    assert "cashout_net" in res and res["complete"] is True
    assert events["E1"]["ctx"]["flatten_pending"] is True
    # l'ordine appoggiato e' stato ANNULLATO prima di chiudere (H1)
    assert ("cancel", {"leg": "under_green-1-2", "role": "under_green", "by": "utente"}, "E1") in db.activity


def test_pulsante_flatten_usa_lo_stesso_handler_con_etichetta_propria():
    db = FakeDB()
    events = {"E1": _armed_event(positions=[_matched("under_last", E.MARKET_OU35, E.SEL_UNDER,
                                                     "back", 1.50, 10.0)])}
    req = _request(db, "flatten")
    _process(db, events, [row(payload(**LIVE_ROW_KW))])
    assert _outcome(req) == ("done", "ok")
    assert req["result"]["message"].startswith("Flatten:")


def test_pulsante_cash_out_con_feed_stantio_viene_RIFIUTATO_dal_servizio():
    """Checklist 3: la UI spegne il bottone, il servizio rifiuta comunque."""
    db = FakeDB()
    events = {"E1": _armed_event(positions=[_matched("under_last", E.MARKET_OU35, E.SEL_UNDER,
                                                     "back", 1.50, 10.0)])}
    req = _request(db, "cashout")
    old = row(payload(**LIVE_ROW_KW), updated=NOW - timedelta(minutes=5))
    S.process_requests(db=db, market=FakeMarket(), events=events, rows_by_event={"E1": old},
                       params=C.merge_params({"stake": 10}), now=NOW, dry=False, scanner_age=120.0)
    assert _outcome(req) == ("rejected", "feed_stantio")
    assert "Feed non aggiornato" in req["result"]["message"]


def test_pulsante_cash_out_senza_linee_nel_feed_dice_feed_assente():
    db = FakeDB()
    events = {"E1": _armed_event(positions=[_matched("under_last", E.MARKET_OU35, E.SEL_UNDER,
                                                     "back", 1.50, 10.0)])}
    req = _request(db, "cashout")
    p = payload(**LIVE_ROW_KW)
    p["ou"] = p["ou"][:1]                      # la linea 4.5 non c'e' piu' (C1)
    _process(db, events, [row(p)])
    assert _outcome(req) == ("rejected", "feed_assente")


def test_pulsante_cash_out_senza_posizione_dice_niente_da_chiudere():
    db = FakeDB()
    events = {"E1": _armed_event(positions=[], state="WATCH", ko_offset_h=1.0)}
    req = _request(db, "cashout")
    _process(db, events, [row(payload())])
    assert _outcome(req) == ("rejected", "niente_da_chiudere")
    # pre-KO: l'utente ha detto "chiudi questa partita" -> nessun rientro
    assert events["E1"]["ctx"]["no_reentry"] is True


def test_pulsante_annulla_ordini_annulla_solo_il_book_e_non_la_posizione():
    db = FakeDB()
    under = _matched("under_last", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 10.0)
    green = E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay",
                  price=1.48, size=10.0, ref="under_green-1-2", cycle_no=1)
    events = {"E1": _armed_event(positions=[under, green])}
    req = _request(db, "cancel")
    _process(db, events, [row(payload(**LIVE_ROW_KW))])
    assert _outcome(req) == ("done", "ok") and req["result"]["cancelled"] == 1
    saved = {l["ref"]: l for l in events["E1"]["positions"]}
    assert saved["under_green-1-2"]["status"] == "cancelled"
    assert saved["under_last-1-1"]["status"] == "open"       # la posizione resta


def test_pulsante_annulla_ordini_senza_ordini_vivi():
    db = FakeDB()
    events = {"E1": _armed_event(positions=[_matched("under_last", E.MARKET_OU35, E.SEL_UNDER,
                                                     "back", 1.50, 10.0)])}
    req = _request(db, "cancel")
    _process(db, events, [row(payload(**LIVE_ROW_KW))])
    assert _outcome(req) == ("rejected", "niente_da_chiudere")


def test_pulsante_salta_rifiuta_con_una_posizione_aperta_e_passa_senza():
    db = FakeDB()
    events = {"E1": _armed_event(positions=[_matched("under_last", E.MARKET_OU35, E.SEL_UNDER,
                                                     "back", 1.50, 10.0)])}
    req = _request(db, "skip_event")
    _process(db, events, [row(payload(**LIVE_ROW_KW))])
    assert _outcome(req) == ("rejected", "posizione_aperta")

    db2 = FakeDB()
    events2 = {"E1": _armed_event(positions=[], state="WATCH", ko_offset_h=1.0)}
    req2 = _request(db2, "skip_event")
    _process(db2, events2, [row(payload())])
    assert _outcome(req2) == ("done", "ok")
    assert events2["E1"]["state"] == "SKIPPED" and events2["E1"]["skipped"] is True
    assert "skip_event" in db2.kinds()


def test_pulsante_riprendi_riporta_in_watch_e_riabilita_il_rientro():
    db = FakeDB()
    events = {"E1": _armed_event(positions=[], state="SKIPPED", ko_offset_h=1.0)}
    req = _request(db, "resume_event")
    _process(db, events, [row(payload())])
    assert _outcome(req) == ("done", "ok")
    assert events["E1"]["state"] == "WATCH" and events["E1"]["skipped"] is False

    # rientro bloccato da un cash out manuale: "Riprendi" lo riabilita
    db2 = FakeDB()
    events2 = {"E1": _armed_event(positions=[], state="WATCH", ko_offset_h=1.0,
                                  ctx={"no_reentry": True})}
    req2 = _request(db2, "resume_event")
    _process(db2, events2, [row(payload())])
    assert _outcome(req2) == ("done", "ok")
    assert events2["E1"]["ctx"]["no_reentry"] is False


def test_pulsante_riprendi_su_stato_normale_viene_rifiutato():
    db = FakeDB()
    events = {"E1": _armed_event(positions=[], state="WATCH", ko_offset_h=1.0)}
    req = _request(db, "resume_event")
    _process(db, events, [row(payload())])
    assert _outcome(req) == ("rejected", "stato_non_riprendibile")


def test_pulsante_su_partita_non_seguita_o_terminale():
    db = FakeDB()
    req = _request(db, "cashout", event_id="MAI_VISTA")
    _process(db, {}, [])
    assert _outcome(req) == ("rejected", "evento_non_seguito")

    db2 = FakeDB()
    events2 = {"E1": _armed_event(positions=[], state="SETTLED")}
    req2 = _request(db2, "cashout")
    _process(db2, events2, [row(payload())])
    assert _outcome(req2) == ("rejected", "stato_terminale")
    # ...ma "Riprendi" su ERROR passa: e' l'unico modo di rimettere in gioco la card
    db3 = FakeDB()
    events3 = {"E1": _armed_event(positions=[], state="ERROR", ko_offset_h=1.0,
                                  ctx={"no_reentry": True})}
    req3 = _request(db3, "resume_event")
    _process(db3, events3, [row(payload())])
    assert _outcome(req3) == ("done", "ok")


def test_pulsante_comando_non_valido_e_un_errore_non_un_rifiuto():
    db = FakeDB()
    events = {"E1": _armed_event(positions=[], state="WATCH", ko_offset_h=1.0)}
    req = _request(db, "danza_della_pioggia")
    _process(db, events, [row(payload())])
    assert _outcome(req) == ("error", "kind_non_valido")


# ===========================================================================
# 5. NUMERI — netto di riga, somma = settled_pnl, "se chiudo ora"
# ===========================================================================
def test_numeri_la_somma_delle_righe_nette_e_il_pnl_della_partita():
    """H4: `sum(per_leg)` == `net` == `settled_pnl` (4 gol: l'esito che perde)."""
    legs = [
        _matched("under_last", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 10.0),
        _matched("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 6.00, 2.53, ref="over_cover-1-2"),
    ]
    for total, expect_sign in ((2, +1), (4, -1), (5, +1)):
        res = E.settle_legs(legs, total, 0.05)
        assert round(sum(p for _r, _s, p in res.per_leg), 2) == res.net, total
        assert (res.net > 0) is (expect_sign > 0), (total, res.net)


def test_numeri_il_se_chiudo_ora_pubblicato_e_netto_e_per_selezione():
    """M5: `cashout.per` (netto) e `cashout.per_gross` (lordo) dal SERVIZIO."""
    db = FakeDB(params={"stake": 10, "commission_pct": 5})
    mk = FakeMarket()
    S.run_once(db=db, market=mk, now=NOW, rows=[row(payload())], atlas=None)
    S.run_once(db=db, market=mk, now=NOW + timedelta(seconds=2), rows=[row(payload())], atlas=None)
    co = db.events["E1"]["live"]["cashout"]
    assert set(co) >= {"net", "gross", "base", "complete", "per", "per_gross", "decided",
                       "commission", "pct", "target_pct"}
    assert co["commission"] == 0.05
    assert co["target_pct"] == 5.0
    key = f"{E.MARKET_OU35}|{E.SEL_UNDER}"
    if co["per"].get(key) is not None and co["per_gross"].get(key) is not None:
        assert abs(co["per"][key]) <= abs(co["per_gross"][key]) + 0.01


def test_numeri_la_liability_della_card_e_quella_netta_del_servizio():
    """M4: `live.liability` = perdita PEGGIORE sulle posizioni NETTE, mai back+lay."""
    back = _matched("under_last", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 10.0)
    lay = _matched("under_green", E.MARKET_OU35, E.SEL_UNDER, "lay", 1.48, 10.0,
                   ref="under_green-1-2")
    somma_gambe = 10.0 + 10.0 * (1.48 - 1.0)
    netta = E.event_liability([back, lay], 0.05)
    assert netta < 1.0 < somma_gambe                  # ciclo greenato: rischio ~0
    # 4 gol: l'unico esito che perde davvero -> la liability e' quella perdita
    nudo = E.event_liability([back], 0.05)
    assert nudo == pytest.approx(10.0, abs=0.01)
    assert '"liability": E.event_liability' in Path(S.__file__).read_text(encoding="utf-8")


def test_numeri_pnl_per_gol_totali_ha_il_quattro_in_perdita():
    legs = [
        _matched("under_last", E.MARKET_OU35, E.SEL_UNDER, "back", 1.50, 10.0),
        _matched("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 6.00, 2.53, ref="over_cover-1-2"),
    ]
    by_total = E.net_pnl_by_total(legs, 0.05)
    assert set(by_total) == set(range(0, 9))
    assert by_total[4] < 0
    assert all(by_total[t] > 0 for t in (0, 1, 2, 3, 5, 6, 7, 8))


# ===========================================================================
# 8. STORICO — le RPC di Mike passano tutti gli argomenti (R2)
# ===========================================================================
def test_storico_le_rpc_di_mike_sono_nella_migrazione_v2_con_tutti_gli_argomenti():
    sql = (MIGRATIONS / "mike_history_v2.sql").read_text(encoding="utf-8")
    assert "DROP FUNCTION IF EXISTS public.trading_daily_history(text,text,text,text,date,date,numeric);" in sql
    assert "DROP FUNCTION IF EXISTS public.trading_day_trades(text,text,date);" in sql
    assert "'mike_trades'" in sql
    daily = sql.split("FUNCTION public.get_mike_daily", 1)[1].split("$$;", 1)[0]
    assert daily.count("public.trading_daily_history(") == 1
    assert "'placed')" in daily and "'mike_trades'" in daily
    day = sql.split("FUNCTION public.get_mike_day_trades", 1)[1].split("$$;", 1)[0]
    assert "public.trading_day_trades('mike_trades', NULL, p_day, 'placed')" in day


def test_storico_la_ui_chiama_le_rpc_con_i_parametri_della_migrazione():
    hist = (FRONTEND / "lib" / "dailyHistory.ts").read_text(encoding="utf-8")
    assert "rpc('get_mike_daily', { p_from: from, p_to: to })" in hist
    assert "rpc('get_mike_day_trades', { p_day: day })" in hist
    # e l'errore che arriva senza migrazione e' LEGGIBILE (checklist 8)
    assert "mike_history_v2.sql" in MIKE_TS
    assert "withMikeHistoryError(fetchMikeDaily)" in PAGE_TS
    assert "withMikeHistoryError(fetchMikeDayTrades)" in PAGE_TS


# ===========================================================================
# 9. SENZA MIGRAZIONI — il servizio e la pagina restano in piedi
# ===========================================================================
def test_senza_migrazione_v2_il_servizio_ripiega_senza_perdere_nulla():
    """`rejected` non ammesso -> 'error' con lo STESSO result (M1)."""
    src = (Path(S.__file__).parent / "db.py").read_text(encoding="utf-8")
    blk = src.split("def set_request_status", 1)[1].split("\ndef ", 1)[0]
    assert 'fields["status"] = "error"' in blk and 'if status != "rejected":' in blk
    # e la RPC v1 (senza requests) ha un ripiego dichiarato nel data-layer
    assert "fetchMikeRequests" in (FRONTEND / "components" / "mike" / "useMike.ts").read_text(encoding="utf-8")


def test_senza_migrazione_v2_la_colonna_closes_trade_id_non_blocca_l_ordine():
    src = Path(S.__file__).read_text(encoding="utf-8")
    assert "closes_trade_id_pending" in src and "schema_warn" in src


# ===========================================================================
# 4. SCHEDE FISSE — l'ordine lo decide solo il calcio d'inizio
# ===========================================================================
def test_schede_l_ordine_non_dipende_dallo_stato():
    """Specchio del test vitest: l'ordinamento usa SOLO `ko_at` e `event_id`."""
    blk = _ts_block(MIKE_TS, "function compareByKickoff", "\n}")
    assert "ko_at" in blk and "event_id" in blk
    assert "state" not in blk and "live" not in blk
