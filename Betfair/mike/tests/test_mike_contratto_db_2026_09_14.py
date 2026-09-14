"""IL MOTORE E IL DATABASE DEVONO DIRE LE STESSE PAROLE (14/09/2026).

Questa è la rete che mancava, e la sua assenza è costata il difetto più grave
della storia del bot.

Il 13/09 il motore ha imparato due stati (`LIVE_KO_GREEN`, `LIVE_SECOND_ENTRY`)
e due ruoli (`ko_green`, `under_second`) per il flusso dal fischio d'inizio. I
`CHECK` del database non li hanno mai conosciuti. Risultato, misurato sul
database vero il 14/09:

    mike_trades  con strategy='ko_green'       ->  0 righe.   MAI.
    mike_events  con state='LIVE_KO_GREEN'     ->  0 partite. MAI.
    su 2000 righe di errore lette, 2000 erano rifiuti di quel vincolo. Il 100%.

**L'uscita al fischio d'inizio non è mai partita nemmeno una volta**, e ogni
partita entrata in gioco con una posizione aperta è rimasta scoperta fino al
fischio finale.

PERCHÉ NESSUN TEST L'HA VISTO. I contratti esistenti confrontano il motore con
la **UI** (`test_mike_certificazione_ui_2026_09_11.py`: `MIKE_STATES == E.STATES`,
`MIKE_ROLES == E.ROLES`). La pagina era allineata, il database no, e **nessuno
confrontava quei due**. Un elenco scritto a mano in tre posti diversi diverge
sempre: qui il terzo posto non aveva nessuno che lo guardasse.

Da qui in avanti ce l'ha.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from Betfair.mike import engine as E

MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"
VINCOLI = MIGRATIONS / "mike_vincoli_flusso_fischio_2026-09-14.sql"


def _valori_del_check(sql: str, dopo: str) -> set[str]:
    """I valori ammessi dal primo ``CHECK (<dopo> IN (...))`` che si incontra."""
    m = re.search(r"CHECK\s*\(\s*" + re.escape(dopo) + r"\s+IN\s*\((.*?)\)\s*\)", sql, re.S)
    assert m, f"nessun CHECK per {dopo} in {VINCOLI.name}"
    return set(re.findall(r"'([^']+)'", m.group(1)))


@pytest.fixture(scope="module")
def sql() -> str:
    assert VINCOLI.exists(), (
        f"manca {VINCOLI.name}: senza, il database rifiuta gli stati e i ruoli "
        "del flusso dal fischio d'inizio e il bot non può uscire in gioco")
    return VINCOLI.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# il contratto
# ---------------------------------------------------------------------------
def test_ogni_RUOLO_del_motore_e_ammesso_dal_database(sql: str) -> None:
    """Se il motore emette un ruolo che il CHECK non ammette, la riga viene
    RIFIUTATA, la gamba annullata e **nessun ordine parte**. Silenziosamente."""
    ammessi = _valori_del_check(sql, "strategy")
    mancanti = sorted(set(E.ROLES) - ammessi)
    assert not mancanti, (
        f"ruoli che il motore usa e il database RIFIUTA: {mancanti}. "
        "Ogni gamba con questo ruolo verrà annullata e nessun ordine partirà.")


def test_ogni_STATO_del_motore_e_ammesso_dal_database(sql: str) -> None:
    """Se il motore entra in uno stato che il CHECK non ammette, la scheda della
    partita NON SI SCRIVE: il bot perde la memoria di dove si trova e al giro
    dopo ricomincia da capo — per sempre, perché i contatori che fanno scadere
    le finestre non vengono mai salvati."""
    ammessi = _valori_del_check(sql, "state")
    mancanti = sorted(set(E.STATES) - ammessi)
    assert not mancanti, (
        f"stati in cui il motore entra e il database RIFIUTA: {mancanti}. "
        "La scheda non si scrive e la partita resta congelata all'ultimo stato valido.")


def test_il_database_non_ammette_ruoli_che_il_motore_non_conosce(sql: str) -> None:
    """L'altro verso: un valore ammesso e mai emesso è un elenco che è rimasto
    indietro, ed è il sintomo che qualcuno ha smesso di tenerli allineati."""
    extra = sorted(_valori_del_check(sql, "strategy") - set(E.ROLES))
    assert not extra, f"ruoli ammessi dal database e sconosciuti al motore: {extra}"


def test_il_database_non_ammette_stati_che_il_motore_non_conosce(sql: str) -> None:
    extra = sorted(_valori_del_check(sql, "state") - set(E.STATES))
    assert not extra, f"stati ammessi dal database e sconosciuti al motore: {extra}"


# ---------------------------------------------------------------------------
# i due valori che sono costati il difetto: nominati, così restano nominati
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ruolo", ["ko_green", "under_second"])
def test_i_ruoli_del_flusso_dal_fischio_ci_sono(sql: str, ruolo: str) -> None:
    """`ko_green` è l'uscita al fischio d'inizio, `under_second` la seconda
    puntata dopo un gol precoce (COSTITUZIONE §15). Sono nati il 13/09 nel
    motore e sono rimasti fuori dal database fino al 14/09."""
    assert ruolo in _valori_del_check(sql, "strategy")


@pytest.mark.parametrize("stato", ["LIVE_KO_GREEN", "LIVE_SECOND_ENTRY"])
def test_gli_stati_del_flusso_dal_fischio_ci_sono(sql: str, stato: str) -> None:
    assert stato in _valori_del_check(sql, "state")


# ---------------------------------------------------------------------------
# la migrazione dev'essere riapplicabile senza rompere niente
# ---------------------------------------------------------------------------
def test_la_migrazione_e_idempotente(sql: str) -> None:
    """Si applica a mano, e prima o poi qualcuno la riapplicherà: deve poterlo
    fare. ``DROP CONSTRAINT IF EXISTS`` prima di ogni ``ADD``."""
    assert sql.count("DROP CONSTRAINT IF EXISTS") >= 2
    assert sql.count("ADD CONSTRAINT") >= 2
    for c in ("mike_trades_strategy_check", "mike_events_state_check"):
        assert sql.count(f"DROP CONSTRAINT IF EXISTS {c}") == 1, c
