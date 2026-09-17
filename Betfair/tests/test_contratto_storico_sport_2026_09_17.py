"""`get_omega_daily` NON PUO' TORNARE AL LOOP PLPGSQL RIGA PER RIGA (17/09/2026).

IL DIFETTO CHE QUESTA RETE IMPEDISCE DI REINTRODURRE. La prima stesura di
`migrations/storico_sport_2026-09-17.sql` (revisione statica,
`APPLY_ORDER_2026-09-16.md` §7) aveva riscritto il merge dell'obiettivo
storicizzato di `get_omega_daily` ripartendo dalla base SBAGLIATA:
`omega_daily_v2.sql:497-509`, il vecchio
    FOR v_row IN SELECT * FROM jsonb_array_elements(v_rows) LOOP ... END LOOP
invece dell'ULTIMA definizione viva sul DB prima del 17/09, che e'
`omega_models_v4.sql:109-151` (set-based: un solo
`jsonb_agg(...) LEFT JOIN omega_daily_goal`, introdotto apposta da v4 al
punto 4: «niente loop plpgsql riga per riga»). Il risultato era identico
(stesse chiavi in uscita, stesso ordine), ma una regressione di prestazioni
silenziosa: annullava il lavoro gia' fatto da v4 senza dirlo da nessuna parte
nel commento del file.

PERCHE' UN TEST SUL SORGENTE SQL E NON SUL DATABASE: il database non e'
raggiungibile dalla suite (vedi `test_contratto_activate_params_2026_09_16.py`),
e il punto e' impedire che una FUTURA riscrittura di `get_omega_daily`
reintroduca il loop senza che nessuno se ne accorga.

FALSIFICAZIONE (obbligatoria, vedi referto): con il blocco set-based di
`get_omega_daily` sostituito dal vecchio
`FOR v_row IN SELECT * FROM jsonb_array_elements(v_rows) LOOP ... END LOOP`
(la prima stesura del 17/09, prima della correzione), il test
`test_get_omega_daily_e_set_based_non_loop` e' ROSSO. Con il file com'e' oggi
(dopo la correzione) e' VERDE. Verificato a mano spostando il file su una
copia con il blocco difettoso e rieseguendo la suite (vedi referto della
sessione che ha applicato questa correzione).
"""
from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
FILE = MIGRATIONS / "storico_sport_2026-09-17.sql"

#: le firme SENZA `p_mode` che devono sparire: lasciandole, una chiamata senza
#: `p_mode` diventerebbe ambigua fra la vecchia firma e la nuova con DEFAULT
#: (42725 "function ... is not unique" — lo stesso incidente di mike_history_v2.sql).
DROP_ATTESI = (
    "DROP FUNCTION IF EXISTS public.get_omega_daily(date, date);",
    "DROP FUNCTION IF EXISTS public.get_omega_day_trades(date);",
)


def _sorgente() -> str:
    assert FILE.exists(), f"manca {FILE}"
    return FILE.read_text(encoding="utf-8")


def _corpo_get_omega_daily(sql: str) -> str:
    """Il corpo di `CREATE OR REPLACE FUNCTION public.get_omega_daily(...)`,
    dalla firma fino al `$$;` che la chiude (stesso pattern dei contract test
    gemelli su questa migrazione)."""
    m = re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\.get_omega_daily\s*\(",
        sql, re.IGNORECASE,
    )
    assert m, "public.get_omega_daily non e' (ri)definita nel file"
    fine = sql.find("$$;", m.end())
    assert fine > 0, "get_omega_daily: corpo non terminato da `$$;`"
    return sql[m.start(): fine]


# --------------------------------------------------------------------------
# 1. niente loop plpgsql riga per riga: la regressione di omega_models_v4.
# --------------------------------------------------------------------------
def test_get_omega_daily_e_set_based_non_loop() -> None:
    corpo = _corpo_get_omega_daily(_sorgente())
    assert "FOR v_row IN" not in corpo, (
        "get_omega_daily e' tornata al LOOP plpgsql riga per riga "
        "(omega_daily_v2.sql:497-509): annulla in silenzio l'ottimizzazione "
        "set-based introdotta da omega_models_v4.sql punto 4 "
        "('niente loop plpgsql riga per riga')."
    )
    assert "END LOOP" not in corpo, (
        "get_omega_daily contiene un END LOOP: stesso difetto di sopra."
    )


# --------------------------------------------------------------------------
# 2. la modalita' viaggia su ogni riga, in ENTRAMBI i rami del CASE (non solo
#    nell'ELSE) — altrimenti le righe col goal storicizzato perdono `mode`.
# --------------------------------------------------------------------------
def test_get_omega_daily_dichiara_mode_in_entrambi_i_rami() -> None:
    corpo = _corpo_get_omega_daily(_sorgente())
    occorrenze = len(re.findall(r"'mode'\s*,\s*v_mode", corpo))
    assert occorrenze >= 2, (
        f"get_omega_daily: 'mode', v_mode compare {occorrenze} volte, attese "
        "almeno 2 (un ramo del CASE 'goal_snapshot=true', l'altro "
        "'goal_snapshot=false'). Se 'mode' manca in un ramo, quelle righe "
        "escono senza dichiarare la modalita'."
    )
    # deve restare set-based: l'aggregazione e' UNA SOLA jsonb_agg, non un
    # accumulo riga per riga dentro un loop (vedi test precedente).
    assert corpo.count("jsonb_agg(") == 1, (
        "get_omega_daily: attesa una sola jsonb_agg (set-based); trovarne "
        "altre e' spia di un ritorno al pattern per-riga."
    )


# --------------------------------------------------------------------------
# 3. i DROP FUNCTION con le firme vecchie esatte, senza `p_mode`.
# --------------------------------------------------------------------------
def test_drop_function_firme_vecchie_esatte() -> None:
    sql = _sorgente()
    for atteso in DROP_ATTESI:
        assert atteso in sql, (
            f"manca `{atteso}` — senza questo DROP, una chiamata senza "
            "`p_mode` diventa ambigua fra la firma vecchia e quella con "
            "DEFAULT (42725 'function ... is not unique')."
        )
    # i DROP devono comparire PRIMA di entrambe le CREATE OR REPLACE che
    # ridefiniscono le stesse funzioni con `p_mode`.
    pos_drop_daily = sql.find(DROP_ATTESI[0])
    pos_drop_trades = sql.find(DROP_ATTESI[1])
    pos_create_daily = sql.find("CREATE OR REPLACE FUNCTION public.get_omega_daily(")
    pos_create_trades = sql.find("CREATE OR REPLACE FUNCTION public.get_omega_day_trades(")
    assert 0 <= pos_drop_daily < pos_create_daily, (
        "il DROP di get_omega_daily(date,date) non precede la CREATE OR REPLACE "
        "con p_mode"
    )
    assert 0 <= pos_drop_trades < pos_create_trades, (
        "il DROP di get_omega_day_trades(date) non precede la CREATE OR REPLACE "
        "con p_mode"
    )


# --------------------------------------------------------------------------
# 4. get_storico_stake dichiara il clamp a 400 giorni (nota non bloccante
#    del referto, chiusa qui: stessa chiave di trading_daily_history).
# --------------------------------------------------------------------------
def test_get_storico_stake_dichiara_window_clamped() -> None:
    m = re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\.get_storico_stake\s*\(",
        _sorgente(), re.IGNORECASE,
    )
    assert m, "public.get_storico_stake non e' definita nel file"
    sql = _sorgente()
    fine = sql.find("$$;", m.end())
    corpo = sql[m.start(): fine if fine > 0 else len(sql)]
    assert "window_clamped" in corpo, (
        "get_storico_stake clampa la finestra a 400 giorni senza dichiararlo: "
        "trading_daily_history (mike_history_v2.sql) usa 'window_clamped' per "
        "lo stesso scopo, qui deve comparire la stessa chiave."
    )
