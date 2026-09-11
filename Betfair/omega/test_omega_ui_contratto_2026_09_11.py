"""Certificazione OMEGA — CONTRATTO fra il servizio e la UI (11/09/2026).

Questi test NON provano la logica di trading: provano che quello che il
servizio SCRIVE e quello che la dashboard LEGGE siano la stessa cosa, con gli
stessi nomi, gli stessi limiti e le stesse parole. È la classe di errori che
l'audit dell'11/09 ha trovato più volte (H-07 default divergenti, M-01 kind
senza etichetta, M-09 clamp diversi, M-10 chiavi senza UI, H-01 `exit_kind`
inventato): nessuno di essi rompe un test unitario, ma tutti mentono al trader.

Leggono i SORGENTI (Python e TypeScript) e li confrontano: se domani qualcuno
aggiunge una chiave alla whitelist, un `kind` all'attività o uno stato al
green-up senza toccare la dashboard, uno di questi test diventa rosso.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from Betfair.omega import omega_config as C
from Betfair.safe_strategy import exits as XE

# ---------------------------------------------------------------- sorgenti
_ROOT = Path(__file__).resolve().parents[2]
_OMEGA_TS = _ROOT / "frontend" / "src" / "lib" / "omega.ts"
_STATUS_TS = _ROOT / "frontend" / "src" / "lib" / "tradeStatus.ts"
_TABLE_TSX = _ROOT / "frontend" / "src" / "components" / "omega" / "MatchTradesTable.tsx"
_SERVICE_PY = Path(__file__).resolve().parent / "omega_service.py"
_EXEC_PY = _ROOT / "Betfair" / "safe_strategy" / "execution.py"


def _read(p: Path) -> str:
    if not p.exists():                       # pragma: no cover - albero incompleto
        pytest.skip(f"sorgente assente: {p}")
    return p.read_text(encoding="utf-8")


def _block(src: str, start_marker: str) -> str:
    """Testo dal marcatore fino alla chiusura del letterale (heuristica sui
    livelli di parentesi): basta per estrarre un oggetto/array TS."""
    i = src.index(start_marker)
    # Primo `{`/`[` dopo il marcatore SALTANDO le quadre dell'annotazione di
    # tipo (`OMEGA_PARAM_GROUPS: ParamGroup[] = [`): partire da quelle
    # troncherebbe il blocco a "[]". Funziona anche per `interface X {`, che
    # non ha un `=`.
    j = i + len(start_marker)
    while j < len(src):
        if src[j] == "{":
            break
        if src[j] == "[" and src[j + 1:j + 2] != "]":
            break
        j += 1
    else:                                     # pragma: no cover
        raise AssertionError(f"letterale non trovato dopo {start_marker}")
    open_ch = src[j]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    for k in range(j, len(src)):
        if src[k] == open_ch:
            depth += 1
        elif src[k] == close_ch:
            depth -= 1
            if depth == 0:
                return src[j:k + 1]
    raise AssertionError(f"blocco non chiuso per {start_marker}")  # pragma: no cover


# ------------------------------------------------------- whitelist parametri
def _ui_param_keys() -> list[str]:
    """`key: '...'` di ogni campo dentro OMEGA_PARAM_GROUPS."""
    block = _block(_read(_OMEGA_TS), "export const OMEGA_PARAM_GROUPS")
    return re.findall(r"\{\s*key:\s*'([A-Za-z0-9_]+)'", block)


def _ui_defaults() -> dict[str, object]:
    block = _block(_read(_OMEGA_TS), "export const OMEGA_PARAM_DEFAULTS")
    out: dict[str, object] = {}
    for key, raw in re.findall(r"^\s{4}([a-z_0-9]+):\s*([^,\n]+),", block, re.M):
        v = raw.strip()
        if v in ("true", "false"):
            out[key] = v == "true"
        elif v.startswith("'"):
            out[key] = v.strip("'")
        else:
            try:
                out[key] = float(v)
            except ValueError:                # pragma: no cover
                out[key] = v
    return out


def _ui_field_bounds() -> dict[str, tuple[float | None, float | None]]:
    """min/max dichiarati nella UI per ogni campo `type: 'number'`."""
    block = _block(_read(_OMEGA_TS), "export const OMEGA_PARAM_GROUPS")
    out: dict[str, tuple[float | None, float | None]] = {}
    for m in re.finditer(r"\{\s*key:\s*'([A-Za-z0-9_]+)'[^}]*?\}", block, re.S):
        field = m.group(0)
        if "type: 'number'" not in field:
            continue
        lo = re.search(r"\bmin:\s*(-?[0-9.]+)", field)
        hi = re.search(r"\bmax:\s*(-?[0-9.]+)", field)
        out[m.group(1)] = (float(lo.group(1)) if lo else None,
                           float(hi.group(1)) if hi else None)
    return out


class TestWhitelistParametri:
    """§7 — la whitelist del servizio e il pannello della UI sono lo stesso
    insieme, con gli stessi limiti e gli stessi default (H-07, M-09, M-10)."""

    def test_ogni_chiave_della_whitelist_ha_una_ui_e_viceversa(self) -> None:
        spec = set(C._SPEC)
        ui = set(_ui_param_keys())
        assert not spec - ui, f"chiavi del servizio SENZA UI (M-10): {sorted(spec - ui)}"
        assert not ui - spec, f"campi della UI che il servizio IGNORA: {sorted(ui - spec)}"

    def test_nessun_campo_duplicato_nel_pannello(self) -> None:
        keys = _ui_param_keys()
        dupes = {k for k in keys if keys.count(k) > 1}
        assert not dupes, f"campo presente due volte nel pannello: {sorted(dupes)}"

    def test_default_della_ui_uguali_a_quelli_del_servizio(self) -> None:
        """H-07: un default della UI diverso da quello del servizio riaccende in
        silenzio un calibratore o abbassa un cap con un «Salva» involontario."""
        ui = _ui_defaults()
        diff: list[str] = []
        for key, want in C.DEFAULTS.items():
            assert key in ui, f"default mancante nella UI: {key}"
            got = ui[key]
            if isinstance(want, bool):
                ok = bool(got) is want
            elif isinstance(want, (int, float)):
                ok = isinstance(got, (int, float)) and abs(float(got) - float(want)) < 1e-9
            else:
                ok = str(got) == str(want)
            if not ok:
                diff.append(f"{key}: UI={got!r} servizio={want!r}")
        assert not diff, "default divergenti (H-07): " + "; ".join(diff)

    def test_clamp_e_unita_uguali(self) -> None:
        """M-09: un valore «valido» per la UI non deve essere clampato in
        silenzio dal servizio (e viceversa)."""
        bounds = _ui_field_bounds()
        diff: list[str] = []
        for key, (_default, cast, lo, hi) in C._SPEC.items():
            if cast is bool or cast is str:
                continue
            assert key in bounds, f"chiave numerica senza campo number nella UI: {key}"
            ui_lo, ui_hi = bounds[key]
            if lo is not None and (ui_lo is None or abs(ui_lo - float(lo)) > 1e-9):
                diff.append(f"{key}.min: UI={ui_lo} servizio={lo}")
            if hi is not None and (ui_hi is None or abs(ui_hi - float(hi)) > 1e-9):
                diff.append(f"{key}.max: UI={ui_hi} servizio={hi}")
        assert not diff, "clamp divergenti (M-09): " + "; ".join(diff)

    def test_le_select_offrono_esattamente_i_valori_ammessi(self) -> None:
        """Un `select` che propone un valore che `_coerce` rifiuta riporta il
        parametro al default senza dirlo."""
        block = _block(_read(_OMEGA_TS), "export const OMEGA_PARAM_GROUPS")
        ammessi = {
            "entry_window_source": {"score", "clock"},
            "execution_mode": {"auto", "rest"},
            "engine": {"legs", "single"},
            "greenup_mode": {"auto", "off"},
            "model_calibration": {"auto", "off"},
            "model_empirical": {"veto", "off"},
        }
        for key, want in ammessi.items():
            m = re.search(r"\{\s*key:\s*'" + key + r"'.*?options:\s*\[(.*?)\]\s*\}", block, re.S)
            assert m, f"select senza options nella UI: {key}"
            got = set(re.findall(r"value:\s*'([^']*)'", m.group(1)))
            assert got == want, f"{key}: UI offre {sorted(got)}, il servizio ammette {sorted(want)}"
            # e il valore proposto deve sopravvivere al coerce del servizio
            for v in got:
                assert C._coerce(key, v) == v, f"{key}={v!r} viene riscritto dal servizio"


# --------------------------------------------------------- attività (kind)
_LOG_LITERAL = re.compile(r"""(?:db|_real_db|self\.db)\.log\(\s*["']([a-z0-9_]+)["']""")
_LOG_SHARED = re.compile(r"""_log\(\s*db\s*,\s*["']([a-z0-9_]+)["']""")
_LOG_TERNARY = re.compile(
    r"""\.log\(\s*["']([a-z0-9_]+)["']\s+if\s+.*?\s+else\s+["']([a-z0-9_]+)["']""")
# kind passati per NOME a _log_dedup(db, key, "<kind>", ...). La CHIAVE di
# dedup è spesso una tupla che contiene virgole e stringhe: va saltata intera,
# altrimenti si cattura la chiave al posto del kind.
_LOG_DEDUP = re.compile(
    r"""_log_dedup\(\s*db\s*,\s*(?:\([^()]*\)|[^,()]+)\s*,\s*["']([a-z0-9_]+)["']""")


def _kind_loggati() -> set[str]:
    """Tutti i `kind` che finiscono in `omega_activity`: i letterali del
    servizio più quelli dello strato CONDIVISO (execution.py scrive sulla
    tabella del `db` che gli viene iniettato: con Omega è omega_activity)."""
    kinds: set[str] = set()
    for src in (_read(_SERVICE_PY), _read(_EXEC_PY)):
        kinds |= set(_LOG_LITERAL.findall(src))
        kinds |= set(_LOG_SHARED.findall(src))
        kinds |= set(_LOG_DEDUP.findall(src))
        for a, b in _LOG_TERNARY.findall(src):
            kinds |= {a, b}
    return kinds


def _ui_kind_mappati() -> set[str]:
    """Chiavi ESPLICITE delle due mappe: quelle tradotte parola per parola dal
    fallback NON contano (è proprio il fallback che mostrava "SETTLE WAIT")."""
    extra = _block(_read(_OMEGA_TS), "export const OMEGA_ACTIVITY_EXTRA")
    base = _block(_read(_STATUS_TS), "export const ACTIVITY_BASE")
    keys: set[str] = set()
    for block in (extra, base):
        keys |= set(re.findall(r"^\s{4}([a-z0-9_]+):\s*\{", block, re.M))
    return keys


class TestAttivitaDelServizio:
    """M-01/L-05 — ogni passo che il servizio scrive deve avere una etichetta
    ITALIANA sua, non la traduzione automatica del fallback."""

    def test_l_estrazione_trova_i_kind_noti(self) -> None:
        """Guardia sull'estrazione stessa: se i regex smettono di agganciare
        (refactoring del logger) il test sotto passerebbe a vuoto."""
        kinds = _kind_loggati()
        assert len(kinds) >= 45, f"estratti troppo pochi kind ({len(kinds)}): regex da aggiornare"
        for atteso in ("place", "skip", "greenup", "greenup_hold", "greenup_retry",
                       "cashout_manual", "settle_position", "settle_wait",
                       "flumine_no_fill", "place_reconciling", "stale_open_alert", "error"):
            assert atteso in kinds, f"kind noto non estratto: {atteso}"

    def test_ogni_kind_loggato_e_mappato_in_italiano(self) -> None:
        mancanti = sorted(_kind_loggati() - _ui_kind_mappati())
        assert not mancanti, (
            "kind scritti dal servizio e SENZA etichetta italiana esplicita "
            f"(cadono nel fallback): {mancanti}"
        )

    def test_nessuna_etichetta_e_la_chiave_inglese(self) -> None:
        extra = _block(_read(_OMEGA_TS), "export const OMEGA_ACTIVITY_EXTRA")
        pairs = re.findall(r"^\s{4}([a-z0-9_]+):\s*\{\s*label:\s*'([^']*)'", extra, re.M)
        assert pairs, "mappa delle attività non letta"
        for key, label in pairs:
            assert label.strip(), f"etichetta vuota per {key}"
            if key == "stop":
                continue                      # "STOP" è italiano com'è
            assert label != key.upper(), f"etichetta = chiave inglese per {key}"


# ------------------------------------------------- vocabolari chiusi condivisi
class TestVocabolariCondivisi:
    """I vocabolari che il frontend usa per decidere un BADGE devono essere gli
    stessi del servizio: un valore in più e il badge sparisce (H-01, H-04)."""

    def test_stati_del_green_up(self) -> None:
        from Betfair.omega import omega_service as S
        ts = _read(_OMEGA_TS)
        m = re.search(r"const GREENUP_STATES:\s*GreenupState\[\]\s*=\s*\[(.*?)\]", ts, re.S)
        assert m, "GREENUP_STATES non trovato in omega.ts"
        ui = set(re.findall(r"'([a-z_]+)'", m.group(1)))
        assert ui == set(S.GREENUP_STATES), (
            f"stati green-up divergenti: UI={sorted(ui)} servizio={sorted(S.GREENUP_STATES)}"
        )

    def test_ogni_exit_kind_ha_un_badge(self) -> None:
        """H-01: `exit_kind` viene dal vocabolario chiuso di exits.EXIT_KINDS.
        La tabella deve gestirli TUTTI: quelli con un badge proprio
        (greenup/manual/profit/loss) e gli altri come uscita a mercato."""
        tsx = _read(_TABLE_TSX)
        m = re.search(r"const MARKET_EXIT_KINDS = new Set\(\[(.*?)\]\)", tsx, re.S)
        assert m, "MARKET_EXIT_KINDS non trovato in MatchTradesTable.tsx"
        mercato = set(re.findall(r"'([a-z_]+)'", m.group(1)))
        propri = {k for k in ("greenup", "manual", "profit", "loss")
                  if f"a.exitKind === '{k}'" in tsx}
        coperti = mercato | propri
        assert set(XE.EXIT_KINDS) <= coperti, (
            "exit_kind del servizio senza badge nella tabella: "
            f"{sorted(set(XE.EXIT_KINDS) - coperti)}"
        )
        assert not coperti - set(XE.EXIT_KINDS), (
            f"la UI gestisce exit_kind che il servizio non scrive: {sorted(coperti - set(XE.EXIT_KINDS))}"
        )

    def test_una_sola_parola_per_la_riconciliazione(self) -> None:
        """§19: lo stesso rischio non può avere due nomi. Tutte e tre le
        sezioni dicono «IN VERIFICA SU BETFAIR»: anche la mappa condivisa."""
        status = _read(_STATUS_TS)
        m = re.search(r"RECONCILING_META:\s*Meta\s*=\s*\{\s*label:\s*'([^']*)'", status)
        assert m, "RECONCILING_META non trovato"
        assert m.group(1) == "IN VERIFICA SU BETFAIR", (
            f"parola divergente per la riconciliazione: {m.group(1)!r}"
        )
        # la vecchia parola non deve tornare come ETICHETTA (nei commenti che
        # spiegano il perché della scelta può restare)
        assert not re.search(r"label:\s*'DA RICONCILIARE'", status), (
            "vecchia parola ancora usata come etichetta"
        )


# ------------------------------------------------------------- realtime
class TestCanaliRealtime:
    """§18 — `subscribeOmega` deve ascoltare le tabelle che il servizio SCRIVE:
    un canale su una tabella che nessuno tocca è una dashboard che non si
    aggiorna mai (e un canale mancante è un aggiornamento che non arriva)."""

    def test_i_canali_sono_tabelle_scritte_dal_servizio(self) -> None:
        ts = _read(_OMEGA_TS)
        m = re.search(r"export function subscribeOmega.*?\n}", ts, re.S)
        assert m, "subscribeOmega non trovata"
        canali = set(re.findall(r"table:\s*'([a-z_]+)'", m.group(0)))
        assert canali, "subscribeOmega non ascolta nessuna tabella"
        db_src = _read(Path(__file__).resolve().parent / "omega_db.py")
        scritte = set(re.findall(r"""\.table\(\s*["']([a-z_]+)["']""", db_src))
        orfani = sorted(canali - scritte)
        assert not orfani, (
            f"la UI ascolta tabelle che il servizio non scrive: {orfani}"
        )
        # le due che il trader DEVE vedere cambiare in tempo reale
        assert {"omega_control", "omega_trades"} <= canali, (
            f"canale realtime mancante: {sorted({'omega_control', 'omega_trades'} - canali)}"
        )


# ------------------------------------------------------------------ stats
class TestStatsDichiarateNellaUI:
    """L-03/H-08 — la UI legge `stats` solo dove l'RPC non ha il dato; le
    chiavi che legge devono comunque essere quelle che il servizio scrive."""

    def test_le_chiavi_lette_dalla_ui_sono_scritte_dal_servizio(self) -> None:
        import inspect

        from Betfair.omega import omega_service as S

        src = inspect.getsource(S)
        # chiavi dichiarate nell'interfaccia OmegaStats della UI
        block = _block(_read(_OMEGA_TS), "export interface OmegaStats")
        ui_keys = set(re.findall(r"^\s{4}([a-z_0-9]+)\??:", block, re.M))
        assert ui_keys, "interfaccia OmegaStats non letta"
        # il servizio le scrive come chiavi di dizionario "nome": valore
        scritte = set(re.findall(r'"([a-z_0-9]+)":', src))
        mancanti = sorted(k for k in ui_keys if k not in scritte)
        assert not mancanti, (
            f"la UI dichiara chiavi di stats che il servizio non scrive: {mancanti}"
        )


# ------------------------------------------------------- snapshot obiettivo
class TestSnapshotObiettivo:
    """§14/H-09/H-10 — l'obiettivo storicizzato ha DUE writer (la RPC SQL delle
    attivazioni e il servizio Python): devono usare la stessa giornata."""

    def test_il_giorno_e_quello_operativo_in_entrambi_i_percorsi(self) -> None:
        from Betfair.omega import omega_engine as E

        sql = (_ROOT / "migrations" / "omega_daily_v2.sql")
        if not sql.exists():                  # pragma: no cover
            pytest.skip("migrazione assente")
        body = sql.read_text(encoding="utf-8")
        m = re.search(r"omega_snapshot_daily_goal.*?\$\$(.*?)\$\$", body, re.S)
        assert m, "omega_snapshot_daily_goal non trovata"
        assert "Europe/Rome" in m.group(1), (
            "la RPC di snapshot non usa la giornata operativa Europe/Rome"
        )
        assert E.OPERATIONAL_TZ == "Europe/Rome", (
            f"il servizio usa un altro fuso operativo: {E.OPERATIONAL_TZ}"
        )

    def test_upsert_daily_goal_non_esplode_e_scrive_le_tre_colonne(self) -> None:
        """R3 dell'audit: la funzione falliva SEMPRE con un NameError
        inghiottito (import di datetime mancante) e lo snapshot non arrivava
        mai. Qui si verifica che il percorso completi e scriva `updated_at`."""
        from Betfair.omega import omega_db

        visti: list[dict] = []

        class _Tbl:
            def upsert(self, payload, on_conflict=None):
                visti.append(dict(payload))
                return self

            def execute(self):
                return None

        class _Sb:
            def table(self, _name):
                return _Tbl()

        original = omega_db._sb
        omega_db._sb = lambda: _Sb()          # type: ignore[assignment]
        try:
            ok = omega_db.upsert_daily_goal("2026-09-11", 250.0)
        finally:
            omega_db._sb = original           # type: ignore[assignment]
        assert ok is True, "upsert_daily_goal ha inghiottito un errore"
        assert visti and set(visti[0]) == {"day", "goal", "updated_at"}, visti
        assert visti[0]["day"] == "2026-09-11"
        assert visti[0]["goal"] == 250.0
        assert json.dumps(visti[0]), "payload non serializzabile"
