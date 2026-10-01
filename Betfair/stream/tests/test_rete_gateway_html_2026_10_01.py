"""01/10/2026 09:22:59: il runner calcio e' MORTO (rc=1) perche' una SELECT
dei follow ha ricevuto da Supabase/Cloudflare una pagina HTML 525 ("SSL
handshake failed"): postgrest solleva ``APIError`` (code = codice HTTP del
gateway, details = l'HTML) e ``e_errore_di_rete`` non la riconosceva.

Finti con le chiavi del vero: ``APIError`` VERA di postgrest, costruita con il
dict ESATTO del log (stesse chiavi e tipi di ``generate_default_error_message``:
code intero) e, nel caso della catena, sollevata con lo stesso codice di
postgrest su una ``httpx.Response`` 525 con corpo HTML (stessa catena
ValidationError -> APIError vista nel log).
"""
from __future__ import annotations

import pytest
from postgrest.exceptions import APIError, APIErrorFromJSON, generate_default_error_message
from postgrest.utils import model_validate_json

import Betfair.stream.runner as R
from Betfair.stream.runner_lifecycle import e_errore_di_rete

# primi caratteri VERI del ``details`` nel log runner-calcio_2026-10-01T07-00-20-514Z
_HTML_525 = (
    "b'<!DOCTYPE html>\\n<!--[if lt IE 7]> <html class=\"no-js ie6 oldie\" "
    "lang=\"en-US\"> <![endif]-->\\n<!--[if IE 7]>    <html class=\"no-js ie7 oldie\" "
    "lang=\"en-US\"> <![endif]-->\\n<!--[if IE 8]>    <html class=\"no-js ie8 oldie\" "
    "lang=\"en-US\"> <![endif]-->\\n<!--[if gt IE 8]><!--> <html class=\"no-js\" "
    "lang=\"en-US\"> <!--<![endif]-->\\n<head>\\n\\n<title>supabase.co | 525: SSL "
    "handshake failed</title>\\n<meta charset="
)
_ERRORE_DEL_LOG = {
    "message": "JSON could not be generated",
    "code": 525,
    "hint": "Refer to full message for details",
    "details": _HTML_525,
}


def _api(code, message="x", details=None) -> APIError:
    return APIError({"message": message, "code": code, "hint": None, "details": details})


def test_a_errore_esatto_del_log_e_rete() -> None:
    assert e_errore_di_rete(APIError(dict(_ERRORE_DEL_LOG)))


def test_b_codice_520_e_rete() -> None:
    assert e_errore_di_rete(_api(520, "JSON could not be generated", "b''"))


def test_c_codice_503_stringa_e_rete() -> None:
    assert e_errore_di_rete(_api("503", "Service Unavailable"))


@pytest.mark.parametrize("code", ["PGRST202", "23514", "57014", "42501", 400, None])
def test_d_e_f_codici_postgrest_veri_non_sono_rete(code) -> None:
    assert not e_errore_di_rete(_api(code, "errore vero del DB", "dettaglio"))


def test_json_non_generato_senza_html_non_e_rete() -> None:
    assert not e_errore_di_rete(_api(400, "JSON could not be generated", "b'testo'"))


def test_json_non_generato_con_html_e_rete_anche_con_codice_ignoto() -> None:
    assert e_errore_di_rete(_api(418, "JSON could not be generated", _HTML_525))


def test_g_api_error_come_causa_di_altra_eccezione() -> None:
    try:
        try:
            raise APIError(dict(_ERRORE_DEL_LOG))
        except APIError as inner:
            raise ValueError("avvolto") from inner
    except ValueError as outer:
        assert e_errore_di_rete(outer)


def _solleva_come_postgrest() -> None:
    """Stesso codice di postgrest/_sync/request_builder.py:50-55 su una
    risposta 525 HTML vera (httpx.Response)."""
    import httpx

    r = httpx.Response(525, content=b"<!DOCTYPE html>\n<html><title>525: SSL handshake "
                                    b"failed</title></html>")
    try:
        model_validate_json(APIErrorFromJSON, r.content)
    except Exception:  # noqa: BLE001 - ValidationError di pydantic, come nel log
        raise APIError(generate_default_error_message(r))


def test_h_catena_vista_oggi_validationerror_come_context() -> None:
    from pydantic import ValidationError

    with pytest.raises(APIError) as ei:
        _solleva_come_postgrest()
    assert isinstance(ei.value.__context__, ValidationError)
    assert ei.value.code == 525
    assert e_errore_di_rete(ei.value)


def test_runner_calcio_non_rilancia_il_525(monkeypatch) -> None:
    attese = []
    monkeypatch.setattr(R.time, "sleep", lambda s: attese.append(s))
    R._attendi_se_rete("lettura dei follow", APIError(dict(_ERRORE_DEL_LOG)))
    assert attese == [R._ATTESA_RETE_SEC]
    with pytest.raises(APIError):
        R._attendi_se_rete("lettura dei follow", _api("PGRST202", "funzione assente"))
