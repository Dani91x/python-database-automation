"""schema_locale.py - lo schema GENERICO e versionato dell'archivio locale (W1-G1).

Scopo
    Uno schema solo, uguale per i due file SQLite di un processo (``denaro`` e
    ``vivo``), che non conosce NESSUNA tabella del cloud: aggiungere una
    tabella al postino = una riga di registro (``SpecTabella``), mai uno schema
    nuovo (requisito dell'utente «cambiare un componente in minuti»).

    Tabelle locali (versione 1):
      * ``righe``       (tabella, chiave) -> json, rev, aggiornato_ms: l'ultima
                        versione di ogni riga di stato, per chiave naturale;
      * ``outbox``      (seq, tabella, op, chiave, json, tentativi, prossimo_ms):
                        cio' che il postino deve ancora consegnare, scritta
                        NELLA STESSA transazione della riga;
      * ``dead_letter`` righe rifiutate dal cloud per sempre (es. un CHECK):
                        visibili, contate, MAI cancellate da sole;
      * ``consegna``    marcatori di consegna dei file JSONL (offset per file);
      * ``riconciliazioni`` esito del confronto notturno per (tabella, giorno);
      * ``segnalazioni`` fatti da mostrare (riga JSONL troncata da un crash...).

    Aggiornamento automatico all'apertura con ``PRAGMA user_version``: si
    applicano in ordine le migrazioni mancanti, ciascuna in una transazione.
    Un file creato da una versione PIU' NUOVA dell'app non si tocca
    (``SchemaPiuNuovo``): niente retrocessioni silenziose.

    Qui vivono anche il formato della riga JSONL dei log e le due funzioni
    canoniche condivise da archivio, postino e riconcilia: ``chiave_canonica``
    (uguale, carattere per carattere, a ``jsonb_build_array(...)::text`` del
    cloud) e ``rev_ordinabile`` (versione monotona confrontabile).

Cosa NON fa
    Non apre file e non crea connessioni: riceve una ``sqlite3.Connection``.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence, Tuple

from .contratto import SpecTabella

VERSIONE_SCHEMA = 1

#: migrazioni in ordine; l'indice + 1 e' la ``user_version`` raggiunta
MIGRAZIONI: Tuple[Tuple[str, ...], ...] = (
    (
        """CREATE TABLE righe (
               tabella        TEXT    NOT NULL,
               chiave         TEXT    NOT NULL,
               json           TEXT    NOT NULL,
               rev            INTEGER,
               aggiornato_ms  INTEGER NOT NULL,
               PRIMARY KEY (tabella, chiave)
           ) WITHOUT ROWID""",
        "CREATE INDEX righe_aggiornato ON righe (tabella, aggiornato_ms)",
        """CREATE TABLE outbox (
               seq            INTEGER PRIMARY KEY AUTOINCREMENT,
               tabella        TEXT    NOT NULL,
               op             TEXT    NOT NULL CHECK (op IN ('upsert', 'insert', 'patch', 'delete')),
               chiave         TEXT,
               json           TEXT    NOT NULL,
               creato_ms      INTEGER NOT NULL,
               tentativi      INTEGER NOT NULL DEFAULT 0,
               prossimo_ms    INTEGER NOT NULL DEFAULT 0,
               ultimo_errore  TEXT,
               coalesce       INTEGER NOT NULL DEFAULT 0
           )""",
        "CREATE INDEX outbox_prossimo ON outbox (prossimo_ms, seq)",
        "CREATE INDEX outbox_chiave ON outbox (tabella, chiave)",
        """CREATE TABLE dead_letter (
               id             INTEGER PRIMARY KEY AUTOINCREMENT,
               fonte          TEXT    NOT NULL,
               seq_origine    INTEGER,
               tabella        TEXT    NOT NULL,
               op             TEXT    NOT NULL,
               chiave         TEXT,
               json           TEXT    NOT NULL,
               codice         TEXT,
               errore         TEXT,
               tentativi      INTEGER NOT NULL DEFAULT 0,
               creato_ms      INTEGER NOT NULL,
               morto_ms       INTEGER NOT NULL
           )""",
        """CREATE TABLE consegna (
               fonte          TEXT    PRIMARY KEY,
               offset         INTEGER NOT NULL,
               aggiornato_ms  INTEGER NOT NULL
           )""",
        """CREATE TABLE riconciliazioni (
               tabella        TEXT    NOT NULL,
               giorno         TEXT    NOT NULL,
               esito          TEXT    NOT NULL,
               dettagli       TEXT,
               ts_ms          INTEGER NOT NULL,
               PRIMARY KEY (tabella, giorno)
           )""",
        """CREATE TABLE segnalazioni (
               id             INTEGER PRIMARY KEY AUTOINCREMENT,
               tipo           TEXT    NOT NULL,
               dettagli       TEXT    NOT NULL,
               ts_ms          INTEGER NOT NULL
           )""",
    ),
)

assert len(MIGRAZIONI) == VERSIONE_SCHEMA


class SchemaPiuNuovo(RuntimeError):
    """Il file e' stato creato da una versione piu' nuova dell'app."""


def versione(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def applica_schema(conn: sqlite3.Connection) -> int:
    """Porta il file all'ultima versione; ritorna la versione di partenza.

    ``conn`` deve essere in autocommit (``isolation_level=None``)."""
    partenza = versione(conn)
    if partenza > VERSIONE_SCHEMA:
        raise SchemaPiuNuovo(f"schema locale v{partenza} piu' nuovo di questo codice (v{VERSIONE_SCHEMA})")
    if partenza == 0:
        # deve precedere la prima tabella: poi la pulizia libera spazio a pezzi
        conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
    for n in range(partenza, VERSIONE_SCHEMA):
        conn.execute("BEGIN IMMEDIATE")
        try:
            for istruzione in MIGRAZIONI[n]:
                conn.execute(istruzione)
            conn.execute(f"PRAGMA user_version = {n + 1}")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    return partenza


# ---------------------------------------------------------------------------
# funzioni canoniche condivise
# ---------------------------------------------------------------------------
def chiave_canonica(spec: SpecTabella, riga: Mapping[str, Any]) -> str:
    """La chiave naturale come testo: ``["paper", "1.23"]``.

    Identica a ``jsonb_build_array(c1, c2, ...)::text`` di PostgreSQL per testo,
    interi e booleani (separatore ``", "``, UTF-8 non scappato): e' cio' che
    confronta ``riconcilia``. Una colonna della chiave assente e' un errore del
    chiamante (``KeyError``), mai una chiave inventata."""
    if not spec.chiave_naturale:
        raise ValueError(f"tabella {spec.nome}: chiave naturale vuota")
    mancanti = [c for c in spec.chiave_naturale if c not in riga]
    if mancanti:
        raise KeyError(f"tabella {spec.nome}: manca la chiave {mancanti}")
    return json.dumps([riga[c] for c in spec.chiave_naturale], ensure_ascii=False, separators=(", ", ": "))


def rev_ordinabile(valore: Any) -> int:
    """Versione confrontabile: intero cosi' com'e', istante ISO -> microsecondi UTC.

    Un istante senza fuso si legge come UTC (il cloud lavora in UTC)."""
    if isinstance(valore, bool) or valore is None:
        raise ValueError(f"versione di riga non valida: {valore!r}")
    if isinstance(valore, int):
        return valore
    if isinstance(valore, str):
        dt = datetime.fromisoformat(valore.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = dt - datetime(1970, 1, 1, tzinfo=timezone.utc)
        return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    raise ValueError(f"versione di riga non valida (serve intero o istante ISO): {valore!r}")


def iso_utc(ms: int) -> str:
    """Istante ISO UTC con millisecondi (``2026-10-09T10:00:00.123+00:00``)."""
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat(timespec="milliseconds")


def giorno_utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# la riga JSONL dei log (il file E' la coda del postino)
# ---------------------------------------------------------------------------
VERSIONE_RIGA_LOG = 1


def riga_log(tabella: str, op: str, ms: int, riga: Mapping[str, Any]) -> str:
    """Una riga del file del giorno, terminata da ``\\n``. ``t`` per primo: il
    conteggio per tabella di ``stato()`` non deve decodificare tutto."""
    return json.dumps({"t": tabella, "op": op, "ms": ms, "v": VERSIONE_RIGA_LOG, "r": riga},
                      ensure_ascii=True, separators=(",", ":")) + "\n"


def leggi_riga_log(testo: str) -> Tuple[str, str, int, Mapping[str, Any]]:
    """(tabella, op, ms, riga) da una riga completa; ``ValueError`` se guasta."""
    d = json.loads(testo)
    if not isinstance(d, dict) or not isinstance(d.get("r"), dict):
        raise ValueError("riga di log senza oggetto 'r'")
    return str(d["t"]), str(d.get("op") or "insert"), int(d["ms"]), d["r"]


def tabella_della_riga_log(testo: str) -> Optional[str]:
    """Solo il nome della tabella (prefisso fisso ``{"t":"...``), senza decodificare."""
    if not testo.startswith('{"t":"'):
        return None
    fine = testo.find('"', 6)
    return testo[6:fine] if fine > 6 else None


def colonne(conn: sqlite3.Connection, tabella: str) -> Sequence[str]:
    """Le colonne di una tabella locale (diagnostica e test dello schema)."""
    return [r[1] for r in conn.execute(f"PRAGMA table_info({tabella})")]
