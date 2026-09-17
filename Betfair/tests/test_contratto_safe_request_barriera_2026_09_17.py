"""LA BARRIERA DI MODALITA' DI `safe_request` NON PUO' SPARIRE IN SILENZIO (17/09/2026).

IL DIFETTO CHE QUESTA RETE IMPEDISCE DI REINTRODURRE. La migrazione del 13/09
(`safe_strategy_paper_live_2026-09-13.sql`, §5) ha messo su `public.safe_request`
una barriera: la modalita' dichiarata nel payload ('place' -> default 'paper',
'cashout'/'cancel' -> opzionale) deve corrispondere a `safe_strategy_control.mode`,
altrimenti la RPC RIFIUTA la richiesta PRIMA di accodarla. E' la stessa regola
che il servizio Python applica un ciclo dopo (`bot_service._request_place`), ma
qui e' ANCHE nel DB-as-bus, perche' una richiesta LIVE puo' arrivare da
qualunque altra via, non solo dal servizio.

La migrazione del 16/09 (`safe_cash_out_globale_e_cap_automatico_2026-09-16.sql`,
§2), che doveva SOLO aggiungere i due kind `cashout_event`/`riprendi_evento`,
ha invece fatto un `CREATE OR REPLACE FUNCTION public.safe_request` ripartendo
dalla firma vecchia (quella di `safe_strategy_bot_v2.sql`, senza barriera):
`v_req_mode`/`v_ctrl_mode`, la lettura di `safe_strategy_control.mode` e il
RAISE "modalita' non corrispondente" sono SPARITI. Essendo l'ultima definizione
in ordine di applicazione, quella senza barriera e' quella che vince sul DB.
Una richiesta LIVE poteva tornare ad accodarsi mentre la sezione e' in PAPER
(o viceversa): soldi veri mossi mentre lo schermo dice un'altra cosa.

PERCHE' UN TEST SUL SORGENTE SQL E NON SUL DATABASE: il database non e'
raggiungibile dalla suite (vedi `test_contratto_activate_params_2026_09_16.py`),
e il punto e' impedire che una FUTURA riscrittura di `safe_request` faccia
sparire di nuovo la barriera senza che nessuno se ne accorga.

FALSIFICAZIONE (obbligatoria, vedi referto): con
`migrations/safe_cash_out_globale_e_cap_automatico_2026-09-16.sql` alla versione
del 16/09 (prima della correzione del 17/09) i test
`test_l_ultima_definizione_ha_la_barriera_di_modalita` e
`test_la_barriera_sta_prima_dell_insert` sono ROSSI. Dopo la correzione (questo
file com'e' oggi) sono VERDI.
"""
from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"

FILE_16_09 = MIGRATIONS / "safe_cash_out_globale_e_cap_automatico_2026-09-16.sql"
FILE_OMEGA_5 = MIGRATIONS / "omega_proposte_uscita_2026-09-16.sql"

#: le stringhe che la barriera DEVE contenere, testuali (vedi §5 del 13/09)
BARRIERA_MARCATORI = (
    "v_ctrl_mode",
    "v_req_mode",
    "FROM public.safe_strategy_control",
    "modalità non corrispondente",
)


def _definizioni(nome: str) -> list[tuple[Path, str]]:
    """Ogni `CREATE OR REPLACE FUNCTION public.<nome>(...)` trovata, col corpo,
    in ordine di nome file (stesso pattern di
    `test_contratto_activate_params_2026_09_16.py`)."""
    out: list[tuple[Path, str]] = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        sql = f.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(
            r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\." + nome + r"\s*\(",
            sql, re.IGNORECASE,
        ):
            fine = sql.find("$$;", m.end())
            out.append((f, sql[m.start(): fine if fine > 0 else len(sql)]))
    return out


def _ordine_di_applicazione(f: Path) -> tuple[int, str]:
    """Le migrazioni datate vengono DOPO quelle senza data, che sono gli schemi
    di partenza; fra due datate vince la data (e poi il nome, a parita' di data)."""
    data = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
    return (1, data.group(1) + f.name) if data else (0, f.name)


def _definizioni_dal_13_09_in_poi() -> list[tuple[Path, str]]:
    trovate = _definizioni("safe_request")
    assert trovate, "public.safe_request non e' definita in nessuna migrazione"
    return [
        (f, corpo) for f, corpo in trovate
        if (m := re.search(r"(\d{4}-\d{2}-\d{2})", f.name)) and m.group(1) >= "2026-09-13"
    ]


def _ultima_definizione() -> tuple[Path, str]:
    trovate = _definizioni("safe_request")
    return sorted(trovate, key=lambda x: _ordine_di_applicazione(x[0]))[-1]


# --------------------------------------------------------------------------
# 1. l'ultima definizione (quella che vince sul DB) ha la barriera intera
# --------------------------------------------------------------------------
def test_l_ultima_definizione_ha_la_barriera_di_modalita() -> None:
    ultima_f, corpo = _ultima_definizione()
    mancanti = [m for m in BARRIERA_MARCATORI if m not in corpo]
    assert not mancanti, (
        f"safe_request ({ultima_f.name}): mancano nella barriera: {mancanti}. "
        "La modalita' della richiesta puo' tornare a non essere confrontata con "
        "safe_strategy_control.mode: soldi veri mossi mentre lo schermo dice "
        "un'altra cosa."
    )


def test_tutte_le_definizioni_dal_13_09_hanno_la_barriera() -> None:
    """Non solo l'ultima: OGNI migrazione datata >= 2026-09-13 che ridefinisce
    `safe_request` deve portarsi dietro la barriera, altrimenti una macchina che
    applica le migrazioni fino a una di quelle (non l'ultima) resta scoperta."""
    per_file = _definizioni_dal_13_09_in_poi()
    assert per_file, "nessuna definizione di safe_request datata >= 2026-09-13"
    for f, corpo in per_file:
        mancanti = [m for m in BARRIERA_MARCATORI if m not in corpo]
        assert not mancanti, f"safe_request ({f.name}): mancano {mancanti}"


# --------------------------------------------------------------------------
# 2. la barriera sta PRIMA dell'INSERT, non dopo (altrimenti la richiesta e'
#    gia' accodata quando si scopre l'incoerenza)
# --------------------------------------------------------------------------
def test_la_barriera_sta_prima_dell_insert() -> None:
    ultima_f, corpo = _ultima_definizione()
    pos_barriera = corpo.find("modalità non corrispondente")
    pos_insert = corpo.find("INSERT INTO public.safe_strategy_requests")
    assert pos_barriera != -1, f"safe_request ({ultima_f.name}): barriera assente"
    assert pos_insert != -1, f"safe_request ({ultima_f.name}): INSERT assente"
    assert pos_barriera < pos_insert, (
        f"safe_request ({ultima_f.name}): la barriera sta DOPO l'INSERT "
        f"({pos_barriera} >= {pos_insert}) — la richiesta sarebbe gia' accodata "
        "prima di scoprire l'incoerenza di modalita'."
    )


# --------------------------------------------------------------------------
# 3. il file del 16/09 ammette i due kind nuovi SIA nel CHECK SIA nella funzione
# --------------------------------------------------------------------------
def test_kind_nuovi_nel_check_e_nella_funzione() -> None:
    assert FILE_16_09.exists(), f"manca {FILE_16_09}"
    sql = FILE_16_09.read_text(encoding="utf-8")

    m_check = re.search(
        r"ADD CONSTRAINT\s+safe_strategy_requests_kind_check\s*"
        r"CHECK\s*\(kind IN\s*\(([^)]*)\)\)",
        sql, re.IGNORECASE,
    )
    assert m_check, "CHECK safe_strategy_requests_kind_check non trovato nel file del 16/09"
    lista_check = m_check.group(1)
    for kind in ("'cashout_event'", "'riprendi_evento'"):
        assert kind in lista_check, f"il CHECK non ammette {kind}: {lista_check}"

    definizioni_nel_file = [corpo for f, corpo in _definizioni("safe_request") if f == FILE_16_09]
    assert definizioni_nel_file, "safe_request non e' (ri)definita nel file del 16/09"
    corpo = definizioni_nel_file[-1]
    for kind in ("cashout_event", "riprendi_evento"):
        assert kind in corpo, f"safe_request (16/09): il kind {kind} non compare nel corpo della funzione"
    # il controllo p_kind NOT IN deve citare entrambi, non solo il ramo ELSIF
    m_notin = re.search(r"p_kind\s+NOT\s+IN\s*\(([^)]*)\)", corpo, re.IGNORECASE)
    assert m_notin, "safe_request (16/09): controllo `p_kind NOT IN (...)` non trovato"
    for kind in ("'cashout_event'", "'riprendi_evento'"):
        assert kind in m_notin.group(1), (
            f"safe_request (16/09): {kind} non e' nel controllo p_kind NOT IN: {m_notin.group(1)}"
        )


# --------------------------------------------------------------------------
# 4. omega_requests ha RLS abilitata (file 5: omega_proposte_uscita_2026-09-16.sql)
# --------------------------------------------------------------------------
def test_omega_requests_ha_row_level_security() -> None:
    assert FILE_OMEGA_5.exists(), f"manca {FILE_OMEGA_5}"
    sql = FILE_OMEGA_5.read_text(encoding="utf-8")
    assert re.search(
        r"ALTER TABLE\s+public\.omega_requests\s+ENABLE ROW LEVEL SECURITY",
        sql, re.IGNORECASE,
    ), (
        "manca `ALTER TABLE public.omega_requests ENABLE ROW LEVEL SECURITY;` "
        "in omega_proposte_uscita_2026-09-16.sql — tutte le tabelle sorelle Safe "
        "(safe_strategy_control/trades/activity/requests/opportunities) la hanno."
    )
    # deve stare DOPO la CREATE TABLE (altrimenti la tabella non esiste ancora)
    pos_create = sql.find("CREATE TABLE IF NOT EXISTS public.omega_requests")
    pos_rls = sql.find("ENABLE ROW LEVEL SECURITY")
    assert pos_create != -1 and pos_rls != -1 and pos_create < pos_rls
