"""percorso.py - dove vive l'archivio locale, senza che l'utente lo sappia (W1-G1).

Scopo
    Decidere la cartella dell'archivio locale (SQLite + JSONL) di UN processo
    dell'app e tenerla per se' con un lucchetto. Ordine dell'utente (09/10):
    l'archivio e' INVISIBILE: niente configurazione, niente cartelle nel repo,
    niente domande. Si crea da solo alla prima apertura.

Entrate
    * ``ARCH_ARCHIVIO_DIR`` (facoltativa): la cartella base che l'app desktop
      passera' ai processi Python (aggancio proposto per l'ondata 2 in
      ``desktop/ambiente_runner.js``, vedi il doc G1). Serve SOLO ad allineare
      Electron e Python; l'utente non la scrive mai.
    * Windows: ``%LOCALAPPDATA%\\AlphaScore Trading\\archivio`` (disco locale:
      il WAL di SQLite non funziona su un filesystem di rete, 07 par. 6.1;
      ``LOCALAPPDATA`` non segue i profili roaming).
    * Altri sistemi (test, cloud): ``$XDG_DATA_HOME`` o ``~/.local/share``,
      sottocartella ``alphascore-trading/archivio``.

Uscite
    ``cartella_base()``, ``cartella_processo(nome)`` e ``Lucchetto``: un file
    ``.lucchetto`` per cartella di processo, preso in esclusiva (``msvcrt`` su
    Windows, ``fcntl`` altrove). Un secondo processo con lo stesso nome riceve
    ``ArchivioOccupato``: due scrittori sullo stesso file non esistono.

Cosa NON fa
    Non apre file all'import, non crea nulla finche' non si chiama
    ``prepara_cartella``/``Lucchetto.prendi``; non sceglie MAI una cartella
    dentro il repo (``PercorsoNonAmmesso``): i dati non finiscono in git.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import IO, Mapping, Optional

logger = logging.getLogger(__name__)

#: variabile d'ambiente dell'aggancio con Electron (unica entrata esterna)
VARIABILE_CARTELLA = "ARCH_ARCHIVIO_DIR"
#: nome del prodotto come in ``desktop/package.json`` (``productName``)
NOME_PRODOTTO = "AlphaScore Trading"
NOME_PRODOTTO_POSIX = "alphascore-trading"
SOTTOCARTELLA = "archivio"
FILE_LUCCHETTO = ".lucchetto"

#: radice del repo: l'archivio non ci deve MAI stare dentro
RADICE_REPO = Path(__file__).resolve().parents[3]

_NOME_VALIDO = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class PercorsoNonAmmesso(ValueError):
    """La cartella calcolata cade dentro il repo (o il nome del processo non e' valido)."""


class ArchivioOccupato(RuntimeError):
    """Un altro processo vivo tiene gia' il lucchetto di questa cartella."""


def cartella_base(ambiente: Optional[Mapping[str, str]] = None,
                  piattaforma: Optional[str] = None) -> Path:
    """La cartella base dell'archivio (non la crea). Pura su ``ambiente``."""
    env = os.environ if ambiente is None else ambiente
    plat = sys.platform if piattaforma is None else piattaforma
    esplicita = (env.get(VARIABILE_CARTELLA) or "").strip()
    if esplicita:
        base = Path(esplicita)
    elif plat.startswith("win"):
        locale = (env.get("LOCALAPPDATA") or "").strip()
        radice = Path(locale) if locale else Path.home() / "AppData" / "Local"
        base = radice / NOME_PRODOTTO / SOTTOCARTELLA
    else:
        xdg = (env.get("XDG_DATA_HOME") or "").strip()
        radice = Path(xdg) if xdg else Path.home() / ".local" / "share"
        base = radice / NOME_PRODOTTO_POSIX / SOTTOCARTELLA
    base = base.expanduser().resolve()
    if _dentro(base, RADICE_REPO):
        raise PercorsoNonAmmesso(f"l'archivio locale non puo' stare dentro il repo: {base}")
    return base


def cartella_processo(nome: str, base: Optional[Path] = None) -> Path:
    """La cartella dell'archivio di UN processo (``runner-calcio``, ``mike``...)."""
    if not _NOME_VALIDO.match(nome or ""):
        raise PercorsoNonAmmesso(f"nome di processo non valido per l'archivio: {nome!r}")
    radice = (base if base is not None else cartella_base()).expanduser().resolve()
    if _dentro(radice, RADICE_REPO):
        raise PercorsoNonAmmesso(f"l'archivio locale non puo' stare dentro il repo: {radice}")
    return radice / nome


def prepara_cartella(cartella: Path) -> Path:
    """Crea la cartella (e le sottocartelle ``log``) se mancano. Idempotente."""
    (cartella / "log").mkdir(parents=True, exist_ok=True)
    return cartella


def _dentro(percorso: Path, radice: Path) -> bool:
    try:
        percorso.resolve().relative_to(radice.resolve())
        return True
    except ValueError:
        return False


class Lucchetto:
    """Lucchetto di processo su ``<cartella>/.lucchetto`` (esclusivo, non bloccante).

    Il sistema operativo lo rilascia da solo se il processo muore (anche con
    ``os._exit``): nessun lucchetto «orfano» da pulire a mano.
    """

    def __init__(self, cartella: Path) -> None:
        self.percorso = cartella / FILE_LUCCHETTO
        self._file: Optional[IO[str]] = None

    @property
    def preso(self) -> bool:
        return self._file is not None

    def prendi(self) -> None:
        if self._file is not None:
            return
        self.percorso.parent.mkdir(parents=True, exist_ok=True)
        f = open(self.percorso, "a+", encoding="ascii")
        try:
            _blocca(f)
        except OSError as exc:
            f.close()
            raise ArchivioOccupato(f"archivio gia' aperto da un altro processo: {self.percorso.parent}") from exc
        f.seek(0)
        f.truncate()
        f.write(str(os.getpid()))
        f.flush()
        self._file = f

    def rilascia(self) -> None:
        f, self._file = self._file, None
        if f is None:
            return
        try:
            _sblocca(f)
        except OSError as exc:  # il file si chiude comunque: il SO rilascia
            logger.warning("[archivio] rilascio del lucchetto %s: %s", self.percorso, exc)
        f.close()


def _blocca(f: IO[str]) -> None:
    if sys.platform.startswith("win"):
        import msvcrt

        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _sblocca(f: IO[str]) -> None:
    if sys.platform.startswith("win"):
        import msvcrt

        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
