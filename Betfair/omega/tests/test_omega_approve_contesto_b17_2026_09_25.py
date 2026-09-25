# -*- coding: utf-8 -*-
"""B17 (25/09/2026) - OMEGA: il prezzo VISTO al clic sull'uscita proposta.

La migrazione ``migrations/omega_request_approve_contesto_2026-09-25.sql``
aggiunge a ``omega_request_approve`` due parametri OPZIONALI (``p_price``,
``p_contesto``) scritti nel payload. Qui si certifica:
  1. il contratto della funzione (una sola versione, parametri DEFAULT NULL,
     firma conservata ``approved_at``, permessi del BLOCCO 3: niente anon);
  2. il servizio Omega non cambia comportamento con le chiavi nuove nel
     payload: la proposta firmata si riconosce identica, e ``_manual_cashout``
     non legge ``price_visto``/``prezzo_visto_ctx`` (B17: l'uscita resta a
     mercato, la tolleranza sul prezzo visto e' una decisione dell'utente).
ASCII-only nel codice, commenti in italiano.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

from Betfair.omega import omega_service as S

_RADICE = Path(__file__).resolve().parents[3]
_SQL = _RADICE / "migrations" / "omega_request_approve_contesto_2026-09-25.sql"


def _codice_sql() -> str:
    """Il testo SQL senza i commenti ``--`` (i controlli guardano il codice)."""
    righe = [r.split("--", 1)[0] for r in _SQL.read_text(encoding="utf-8").splitlines()]
    return "\n".join(righe)


def test_la_migrazione_esiste_ed_e_ascii():
    testo = _SQL.read_text(encoding="utf-8")
    assert testo.isascii()


def test_una_sola_versione_della_funzione_coi_parametri_opzionali():
    c = _codice_sql()
    assert "DROP FUNCTION IF EXISTS public.omega_request_approve(bigint);" in c
    assert "DROP FUNCTION IF EXISTS public.omega_request_approve(bigint, numeric, jsonb);" in c
    firma = re.search(r"CREATE FUNCTION public\.omega_request_approve\((.*?)\)\s*RETURNS", c, re.S)
    assert firma, "manca la CREATE della funzione"
    parametri = [p.strip() for p in firma.group(1).split(",")]
    assert parametri[0] == "p_id bigint"
    assert parametri[1] == "p_price numeric DEFAULT NULL"
    assert parametri[2] == "p_contesto jsonb DEFAULT NULL"


def test_il_payload_si_conserva_e_si_aggiunge_la_firma_e_il_visto():
    c = _codice_sql()
    assert "payload = v_row.payload || v_extra" in c            # difetto 27: mai rifarlo da zero
    assert "'approved_at'" in c                                  # la firma che il servizio riconosce
    assert "'price_visto', p_price" in c
    assert "jsonb_build_object('prezzo_visto_ctx', p_contesto)" in c
    assert "IF v_row.status <> 'proposed'" in c                   # una sola approvazione
    assert "FOR UPDATE" in c


def test_i_permessi_sono_quelli_del_blocco_3():
    c = _codice_sql()
    assert "REVOKE ALL ON FUNCTION public.omega_request_approve(bigint, numeric, jsonb) FROM anon;" in c
    assert "GRANT EXECUTE ON FUNCTION public.omega_request_approve(bigint, numeric, jsonb) TO authenticated;" in c
    assert "betfair_live_is_owner()" in c


def test_le_chiavi_nuove_non_cambiano_il_riconoscimento_della_firma():
    corpo = {"trade_id": 1, "fraction": 1.0, "motivo_codice": "blocca_il_profitto",
             "approved_at": "2026-09-25T10:00:00Z"}
    col_visto = {**corpo, "price_visto": 31.0, "price_visto_at": "2026-09-25T10:00:00.120Z",
                 "prezzo_visto_ctx": {"eta_ms": 80, "fonte": "canale", "prezzo_vivo_assente": False,
                                      "clic_ms": 1790000000000, "prezzo_segnale": 30.0}}
    assert S._uscita_del_bot_approvata(corpo) is S._uscita_del_bot_approvata(col_visto) is True
    assert S._exit_kind_della_proposta(corpo, 0.9) == S._exit_kind_della_proposta(col_visto, 0.9)


def test_l_uscita_resta_a_mercato_il_servizio_non_legge_il_prezzo_visto():
    """B17 aperto: finche' l'utente non decide, ``_manual_cashout`` non usa il
    prezzo visto. Se un giorno lo leggesse, questo test lo segnala (decisione
    dell'utente, non un'iniziativa)."""
    sorgente = inspect.getsource(S._manual_cashout)
    assert "price_visto" not in sorgente
    assert "prezzo_visto_ctx" not in sorgente
