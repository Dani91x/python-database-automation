"""NESSUNA `*_activate` PUO' AZZERARE I PARAMETRI (16/09/2026).

IL DIFETTO CHE QUESTA RETE IMPEDISCE DI REINTRODURRE. Le tre RPC di attivazione
dei bot fanno la stessa cosa, ma una la faceva al contrario:

    safe_activate  ->  params = coalesce(p_params, params)       CONSERVA
    mike_activate  ->  params = coalesce(p_params, params)       CONSERVA
    omega_activate ->  params = coalesce(p_params, '{}'::jsonb)  AZZERA

`{}` non e' NULL: attivare Omega senza passare i parametri SOSTITUIVA l'intera
colonna con un oggetto vuoto. E i tetti di rischio di Omega, a zero, nel suo
codice significano TETTO SPENTO (`apply_liability_cap`: `if not cap or cap <= 0:
return size`; `omega_service.py:963` e `:1201`). Cioe': una riattivazione
distratta toglieva tutti e tre i freni, in live, in silenzio.

Reggeva solo perche' il frontend passa sempre i parametri correnti e si rifiuta
di avviare quando non li ha letti (`ParametriOmegaIgnoti`). Una protezione che
vive solo nel browser non e' una protezione.

PERCHE' UN TEST SUL SORGENTE SQL E NON SUL DATABASE: il database non e'
raggiungibile dalla suite, e comunque il punto e' un altro — impedire che una
FUTURA riscrittura di una di queste funzioni riporti dentro `'{}'::jsonb` senza
che nessuno se ne accorga. Il file SQL e' il posto dove la riscrittura avviene.

REGOLA: fra tutte le migrazioni, l'ULTIMA definizione di ogni `*_activate` deve
usare la colonna come ripiego, mai un oggetto vuoto.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"

#: le RPC di attivazione dei bot: quelle che possono riscrivere `params`
ATTIVAZIONI = ("safe_activate", "mike_activate", "omega_activate")


def _definizioni(nome: str) -> list[tuple[Path, str]]:
    """Ogni `CREATE OR REPLACE FUNCTION public.<nome>(...)` trovata, col corpo,
    in ordine di nome file (che porta la data: le migrazioni si applicano in
    quell'ordine)."""
    out: list[tuple[Path, str]] = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        sql = f.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(
            r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\." + nome + r"\s*\(",
            sql, re.IGNORECASE,
        ):
            # il corpo arriva fino al `$$;` che chiude la funzione
            fine = sql.find("$$;", m.end())
            out.append((f, sql[m.start(): fine if fine > 0 else len(sql)]))
    return out


def _ordine_di_applicazione(f: Path) -> tuple[int, str]:
    """Le migrazioni datate (``*_2026-09-16.sql``) vengono DOPO quelle senza
    data, che sono gli schemi di partenza."""
    data = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
    return (1, data.group(1) + f.name) if data else (0, f.name)


@pytest.mark.parametrize("nome", ATTIVAZIONI)
def test_ogni_activate_esiste_almeno_una_volta(nome: str) -> None:
    assert _definizioni(nome), f"{nome} non e' definita in nessuna migrazione"


@pytest.mark.parametrize("nome", ATTIVAZIONI)
def test_l_ultima_definizione_conserva_i_parametri(nome: str) -> None:
    """L'ultima versione di ogni attivazione deve fare `coalesce(p_params, params)`.

    `'{}'::jsonb` come ripiego e' il difetto: azzera i tetti di rischio senza
    dirlo. Se questo test diventa rosso, qualcuno lo ha appena reintrodotto.
    """
    trovate = _definizioni(nome)
    ultima_f, corpo = sorted(trovate, key=lambda x: _ordine_di_applicazione(x[0]))[-1]

    # il ripiego che conta e' quello nell'assegnazione di `params`
    assegnazioni = re.findall(r"params\s*=\s*coalesce\(\s*p_params\s*,\s*([^)]*)\)",
                              corpo, re.IGNORECASE)
    assert assegnazioni, (
        f"{nome} ({ultima_f.name}): non assegna `params = coalesce(p_params, ...)`; "
        "una scrittura diversa va riletta a mano prima di fidarsi"
    )
    for ripiego in assegnazioni:
        pulito = ripiego.strip().lower()
        assert "'{}'" not in pulito and pulito == "params", (
            f"{nome} ({ultima_f.name}): il ripiego di `params` e' `{ripiego.strip()}`. "
            "Deve essere la colonna `params`: `'{}'::jsonb` AZZERA i tetti di rischio "
            "a ogni attivazione senza parametri, in live, in silenzio."
        )


def test_omega_ha_la_migrazione_correttiva_del_16_09() -> None:
    """La correzione e' un file a parte, e va applicata: finche' non lo e', sul
    database resta la versione che azzera (`omega_daily_v2.sql`)."""
    f = MIGRATIONS / "omega_activate_conserva_params_2026-09-16.sql"
    assert f.exists(), "manca migrations/omega_activate_conserva_params_2026-09-16.sql"
    sql = f.read_text(encoding="utf-8")
    assert "coalesce(p_params, params)" in sql
    # firma identica a quella in vigore: `CREATE OR REPLACE` senza `DROP`, cosi'
    # la migrazione e' idempotente e non rompe nessun chiamante
    assert "omega_activate(text,numeric,jsonb)" in sql
    assert "DROP FUNCTION" not in sql.upper()
