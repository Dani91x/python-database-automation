"""CERTIFICAZIONE 12/09 — il realtime della UI non deve essere MUTO.

Difetto trovato in produzione: la UI sottoscriveva tabelle che nessuna
migrazione aveva mai aggiunto alla publication ``supabase_realtime``. Postgres
non replica gli eventi di una tabella non pubblicata, quindi quelle
sottoscrizioni non ricevevano NULLA e non c'era modo di accorgersene: nessun
errore, nessun log, solo aggiornamenti in ritardo di un poll (15 secondi).

Casi reali corretti il 12/09:
  * ``omega_activity``          sottoscritta? no  · pubblicata? no  -> aggiunte entrambe
  * ``safe_strategy_activity``  sottoscritta si  · pubblicata? NO   -> muta da sempre
  * ``safe_strategy_requests``  sottoscritta si  · pubblicata? NO   -> muta da sempre

Questo test lega le due cose: ogni tabella che il TypeScript sottoscrive deve
comparire in un ``ALTER PUBLICATION supabase_realtime ADD TABLE`` dentro
``migrations/``.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
FRONTEND = ROOT / "frontend" / "src" / "lib"

# file TS che aprono un canale realtime, con il prefisso delle tabelle dei bot
SORGENTI = (
    FRONTEND / "omega.ts",
    FRONTEND / "safeBot.ts",
    FRONTEND / "mike.ts",
    FRONTEND / "safeStrategyScan.ts",
)
PREFISSI = ("omega_", "safe_strategy_", "mike_")


def _testo(p: Path) -> str:
    return p.read_text(encoding="utf8", errors="replace") if p.exists() else ""


def tabelle_sottoscritte() -> set[str]:
    """Tabelle passate a ``.on('postgres_changes', { ... table: 'X' })``, piu'
    quelle elencate negli array *_REALTIME_TABLES che il canale cicla."""
    trovate: set[str] = set()
    for src in SORGENTI:
        s = _testo(src)
        for m in re.finditer(r"table:\s*'([a-z0-9_]+)'", s):
            trovate.add(m.group(1))
        # array di tabelle ciclate da un for (pattern di Mike)
        for blocco in re.finditer(r"REALTIME_TABLES\s*=\s*\[(.*?)\]", s, re.S):
            trovate |= set(re.findall(r"'([a-z0-9_]+)'", blocco.group(1)))
    return {t for t in trovate if t.startswith(PREFISSI)}


def tabelle_pubblicate() -> set[str]:
    """Tabelle aggiunte a ``supabase_realtime`` da una qualunque migrazione.

    Due forme in uso: ``ADD TABLE public.X`` esplicito e il ciclo
    ``FOREACH t IN ARRAY ARRAY[...]`` con ``EXECUTE format(...)``.
    """
    pubbl: set[str] = set()
    for sql in MIGRATIONS.glob("*.sql"):
        s = _testo(sql)
        if "supabase_realtime" not in s:
            continue
        pubbl |= set(re.findall(
            r"ALTER PUBLICATION supabase_realtime ADD TABLE public\.([a-z0-9_]+)", s))
        if "EXECUTE format" in s and "supabase_realtime" in s:
            for blocco in re.finditer(r"IN ARRAY ARRAY\[(.*?)\]", s, re.S):
                pubbl |= set(re.findall(r"'([a-z0-9_]+)'", blocco.group(1)))
    return {t for t in pubbl if t.startswith(PREFISSI)}


def test_l_estrazione_aggancia_qualcosa() -> None:
    """Guardia sull'estrazione: se i regex smettono di agganciare (refactoring
    del client Supabase) il test sotto passerebbe a vuoto."""
    sott = tabelle_sottoscritte()
    pubbl = tabelle_pubblicate()
    assert len(sott) >= 8, f"troppe poche sottoscrizioni trovate ({sorted(sott)}): regex da aggiornare"
    assert len(pubbl) >= 8, f"troppe poche pubblicazioni trovate ({sorted(pubbl)}): regex da aggiornare"
    for attesa in ("omega_trades", "mike_trades", "safe_strategy_trades"):
        assert attesa in sott and attesa in pubbl, attesa


def test_ogni_tabella_sottoscritta_e_pubblicata_per_il_realtime() -> None:
    """Il cuore: una sottoscrizione senza publication e' silenziosamente morta."""
    mute = sorted(tabelle_sottoscritte() - tabelle_pubblicate())
    assert not mute, (
        "la UI sottoscrive tabelle NON pubblicate su supabase_realtime: il canale "
        f"non ricevera' mai un evento e l'aggiornamento resta al poll dei 15 s -> {mute}. "
        "Aggiungerle con ALTER PUBLICATION in una migrazione."
    )


@pytest.mark.parametrize("tabella", [
    "omega_activity", "safe_strategy_activity", "safe_strategy_requests",
])
def test_le_tre_tabelle_corrette_il_12_09_restano_pubblicate(tabella: str) -> None:
    """Regressione puntuale sui tre casi trovati: il log del servizio e l'esito
    delle azioni manuali devono arrivare in tempo reale in TUTTE le sezioni."""
    assert tabella in tabelle_pubblicate(), (
        f"{tabella} non e' piu' pubblicata: il suo log tornerebbe in ritardo di un poll"
    )
