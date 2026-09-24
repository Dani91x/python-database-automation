"""24/09/2026 - OMEGA: CHI ESEGUE L'USCITA CALCOLATA (`uscite_protezione`).

Ordine dell'utente, testuale: "la scelta tra 'avvisa e proponi la copertura/
uscita con un clic' e 'automatico (se ne occupa il bot)' vale PER TUTTI I BOT"
("QUESTO PER TUTTI I BOT"). Per Safe e' `combo_gamba_manuale` (commit 752139a);
qui lo stesso schema per Omega.

  * 'avvisa_e_proponi' (DEFAULT, fail-closed): la proposta in scheda, come dal
    17/09. Nessun ordine.
  * 'automatico': la STESSA uscita (stessa gamba, intera, prezzi del percorso di
    un'approvazione) la esegue il bot, con l'audit della scelta.

Nessun criterio d'uscita cambia: la decisione e' sempre `omega_v3.
proposta_uscita`; cambia solo chi preme il bottone.

I FINTI PARLANO COME IL VERO: il database e' quello dei test del green-up
(`_DB`, righe di `omega_trades` con le colonne vere e `execution.close_trade`
VERO sopra), piu' la coda `omega_manual_requests` con le chiavi della
migrazione (`id`, `kind`, `payload`, `status`, `result`, `created_at`,
`updated_at`, `processed_at`) e le firme di `omega_db`
(`proposta_di_chiusura_viva`, `scrivi_proposta_di_chiusura`,
`chiudi_proposta`). Il mercato risponde a `read_book(market_id, runner_names)`
con le chiavi di `omega_service._cashout_prices`.

OGNI TEST NUOVO E' STATO FALSIFICATO (vedi il referto del delegato): rimesso il
difetto, diventa rosso.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

import pytest

from Betfair.omega import certificazione as CERT
from Betfair.omega import omega_config as C
from Betfair.omega import omega_proposte as PR
from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_greenup_2026_09_10 import (
    CS_MID, EID, _DB, _payload, _sel, _trade)
from Betfair.omega.test_omega_service import NOW, FakeMarket

SEL = 14
RUNNER = "1 - 3"
AUDIT = "esecuzione automatica per scelta dell'utente (uscite_protezione=automatico)"


# ---------------------------------------------------------------------------
# i finti
# ---------------------------------------------------------------------------
class DbConCoda(_DB):
    """`_DB` (close_trade vero) + LA CODA delle proposte con le colonne di
    `omega_manual_requests` e le firme di `omega_db`. Stesso comportamento del
    `DbFinto` di test_omega_proposte_2026_09_17 (la coda e' UNA)."""

    def __init__(self, control: dict) -> None:
        super().__init__(control)
        self.richieste: List[dict] = []
        self._rid = 0

    def pending_manual_requests(self) -> List[dict]:
        return [dict(r) for r in self.richieste if str(r.get("status")) == "pending"]

    def set_manual_status(self, req_id: int, status: str,
                          result: Optional[dict] = None) -> None:
        for r in self.richieste:
            if int(r["id"]) == int(req_id):
                r["status"] = status
                if result is not None:
                    r["result"] = result

    def proposta_di_chiusura_viva(self, trade_id: int) -> Optional[dict]:
        for r in self.richieste:
            if (str(r.get("status")) == "proposed"
                    and str((r.get("payload") or {}).get("trade_id")) == str(int(trade_id))):
                return dict(r)
        return None

    def scrivi_proposta_di_chiusura(self, trade_id: int,
                                    payload: Dict[str, Any]) -> Optional[int]:
        corpo = {**payload, "trade_id": int(trade_id)}
        viva = self.proposta_di_chiusura_viva(trade_id)
        if viva is not None:
            for r in self.richieste:
                if int(r["id"]) == int(viva["id"]):
                    r["payload"] = corpo
                    r["updated_at"] = NOW.isoformat()
            return int(viva["id"])
        self._rid += 1
        self.richieste.append({
            "id": self._rid, "kind": "cashout", "status": "proposed",
            "payload": corpo, "result": None, "created_at": NOW.isoformat(),
            "updated_at": NOW.isoformat(), "processed_at": None})
        return self._rid

    def chiudi_proposta(self, trade_id: int, motivo: str) -> None:
        viva = self.proposta_di_chiusura_viva(trade_id)
        if viva is None:
            return
        for r in self.richieste:
            if int(r["id"]) == int(viva["id"]):
                r["status"] = "rejected"
                r["result"] = {**(r.get("result") or {}), "decaduta": True,
                               "motivo": str(motivo)[:200]}

    def kinds(self) -> List[str]:
        return [k for k, _p in self.activity]

    def attivita_di(self, kind: str) -> List[dict]:
        return [p for k, p in self.activity if k == kind]


class Mercato(FakeMarket):
    """Il book REST della selezione del trade, con le chiavi che legge
    `omega_service._cashout_prices` (`market.read_book(market_id, {})`)."""

    def __init__(self) -> None:
        super().__init__([], None, None)
        self.letture = 0

    def read_book(self, market_id, _runner_names):
        self.letture += 1
        return {"market_id": CS_MID, "status": "OPEN",
                "runners": [{"selection_id": SEL, "back_price": 8.0, "back_size": 500.0,
                             "lay_price": 8.2, "lay_size": 500.0,
                             "lay_ladder": ((8.2, 500.0),)}]}


@pytest.fixture(autouse=True)
def _prezzi_freschi(monkeypatch: pytest.MonkeyPatch):
    # la freschezza del feed la decide il mercato reale: qui la si dichiara
    # (stesso finto di test_omega_proposte_2026_09_17)
    monkeypatch.setattr(S, "_feed_prices_fresh", lambda market, eid: True)
    S.svuota_le_cache()
    yield
    S.svuota_le_cache()


def _params(**kw: Any) -> dict:
    return C.resolve_params({"strategy_version": 3, **kw})


def _db() -> DbConCoda:
    return DbConCoda({"id": 1, "status": "running", "mode": "paper",
                      "daily_goal": 100.0, "params": {"strategy_version": 3}})


def _feed(back: float = 8.0) -> dict:
    # lay 1-3 @55 sull'1-0 al 70': la gamba supera il tetto di GAMBA di V3
    # (270 EUR di liability contro 95) -> il produttore propone col motivo `cap`
    return _payload(70, 1, 0, cs=[_sel(SEL, RUNNER, back + 0.2, back)])


def _gira(db: DbConCoda, params: dict, *, now=NOW, market: Any = None) -> int:
    return PR.process_proposte_uscita(params=params, market=market or Mercato(), db=db,
                                      now=now, feed=lambda eid: _feed() if eid == EID else None)


def _chiusure(db: DbConCoda, tid: int) -> List[dict]:
    return [t for t in db.trades if t.get("closes_trade_id") == tid]


# ===========================================================================
# 1. IL PARAMETRO: default, fail-closed, lettura
# ===========================================================================
@pytest.mark.parametrize("grezzo,atteso", [
    (None, "avvisa_e_proponi"), ("", "avvisa_e_proponi"), ("boh", "avvisa_e_proponi"),
    ("auto", "avvisa_e_proponi"), (True, "avvisa_e_proponi"),
    ("avvisa_e_proponi", "avvisa_e_proponi"),
    ("automatico", "automatico"), (" Automatico ", "automatico"),
])
def test_default_fail_closed_solo_automatico_scritto_accende(grezzo, atteso):
    assert C.resolve_params({})["uscite_protezione"] == "avvisa_e_proponi"
    p = C.resolve_params({"uscite_protezione": grezzo})
    assert p["uscite_protezione"] == atteso
    assert PR.modo_uscite(p) == atteso
    # anche letto dal dict GREZZO (chi passa i params senza whitelist)
    assert PR.modo_uscite({"uscite_protezione": grezzo}) == atteso


def test_parametro_assente_vale_avvisa_anche_nel_lettore_del_servizio():
    assert PR.modo_uscite(None) == "avvisa_e_proponi"
    assert PR.modo_uscite({}) == "avvisa_e_proponi"


# ===========================================================================
# 2. AVVISA E PROPONI: la proposta di sempre, nessun ordine
# ===========================================================================
def test_avvisa_scrive_la_proposta_idempotente_e_nessun_ordine():
    db = _db()
    tr = _trade(db)
    mercato = Mercato()
    assert _gira(db, _params(), market=mercato) == 1
    assert len(db.richieste) == 1
    riga = db.richieste[0]
    assert riga["status"] == "proposed" and riga["kind"] == "cashout"
    # LE CHIAVI DELLA PROPOSTA sono quelle di sempre (`_payload`): nessun campo
    # nuovo, nessun campo tolto
    attese = set(PR._payload(tr=tr, proposta=_proposta_finta(), prezzi={"back": 8.0},
                             minuto=70, punteggio="1-0", decided_at="x", now=NOW,
                             fonte_p="v3:x", cap="v3_max_liability_per_leg",
                             ingredienti={}).keys())
    assert set(riga["payload"].keys()) - {"trade_id"} == attese - {"trade_id"}
    assert riga["payload"]["motivo_codice"] == "cap"
    # nessun ordine, nessuna lettura REST (regola del feed unico)
    assert _chiusure(db, tr["id"]) == []
    assert mercato.letture == 0
    assert "uscita_automatica" not in db.kinds()
    # idempotente: altri giri, sempre UNA riga
    for i in range(1, 4):
        _gira(db, _params(), now=NOW + timedelta(seconds=30 * i), market=mercato)
    assert len(db.richieste) == 1
    assert _chiusure(db, tr["id"]) == []


def _proposta_finta():
    from Betfair.omega import omega_v3 as V3
    return V3.PropostaUscita(True, "cap", -1.0, 8.0, 34.0, -2.0, False, -1.5, 80.0,
                             0.01, "-")


# ===========================================================================
# 3. AUTOMATICO: la stessa uscita la esegue il bot, con l'audit
# ===========================================================================
def test_automatico_esegue_l_uscita_con_audit():
    db = _db()
    tr = _trade(db)
    assert _gira(db, _params(uscite_protezione="automatico")) == 1
    chiusure = _chiusure(db, tr["id"])
    assert len(chiusure) == 1
    ch = chiusure[0]
    assert ch["side"] == "back" and ch["origin"] == "auto"
    assert ch["mode"] == "paper", "paper e live non si mischiano"
    # nessuna proposta in coda: l'utente ha scelto che decida il bot
    assert db.richieste == []
    aperta = db.get_trade(tr["id"])
    meta = aperta["meta"]
    # l'audit e' SCRITTO per esteso (letterale, non la costante: una costante
    # svuotata passerebbe il test)
    assert AUDIT in meta["exit_reason"]
    assert meta["chiusura_automatica"]["scelta_utente"] == "uscite_protezione=automatico"
    assert meta["chiusura_automatica"]["motivo_codice"] == "cap"
    assert meta[PR.AUTOMATICA_KEY]["eseguita"] is True
    assert AUDIT in (ch.get("meta") or {}).get("exit_reason", "")
    att = db.attivita_di("uscita_automatica")
    assert len(att) == 1
    assert att[0]["esito"] == "eseguita"
    assert att[0]["scelta_utente"] == "uscite_protezione=automatico"
    assert att[0]["closing_trade_id"] == ch["id"]
    # la decisione e' del bot: la partita NON e' 'chiusa dall'utente'
    assert EID not in S._EVENTI_CHIUSI


def test_automatico_esegue_la_stessa_uscita_che_avvisa_proporrebbe():
    """Stessa gamba, stesso motivo, stesso numero bloccabile: cambia solo chi
    preme il bottone."""
    db_a, db_b = _db(), _db()
    tr_a, tr_b = _trade(db_a), _trade(db_b)
    _gira(db_a, _params())
    _gira(db_b, _params(uscite_protezione="automatico"))
    prop = db_a.richieste[0]["payload"]
    auto = db_b.attivita_di("uscita_automatica")[0]
    assert auto["motivo_codice"] == prop["motivo_codice"]
    assert auto["profitto_bloccabile"] == prop["profitto_bloccabile"]
    assert auto["trade_id"] == prop["trade_id"] == tr_a["id"] == tr_b["id"]
    ch = _chiusure(db_b, tr_b["id"])[0]
    assert ch["selection_id"] == prop["selection_id"] and ch["side"] == prop["side"]


def test_lettura_a_caldo_da_avvisa_ad_automatico_la_proposta_viva_decade():
    """Il parametro si legge a OGNI giro (`run_once` -> `resolve_params`):
    l'utente passa ad 'automatico' con una proposta in scheda -> il bot la
    esegue e la riga in coda DECADE (non resta un bottone su una posizione
    chiusa)."""
    db = _db()
    tr = _trade(db)
    _gira(db, _params())
    assert db.richieste[0]["status"] == "proposed"
    _gira(db, _params(uscite_protezione="automatico"), now=NOW + timedelta(seconds=5))
    assert len(_chiusure(db, tr["id"])) == 1
    assert db.richieste[0]["status"] == "rejected"
    assert db.richieste[0]["result"]["decaduta"] is True
    assert PR.PROPOSTA_KEY not in db.get_trade(tr["id"])["meta"]
    assert len(db.richieste) == 1, "nessuna proposta nuova dopo l'esecuzione"


def test_lettura_a_caldo_dal_run_once():
    """Il servizio intero: il parametro arriva da `omega_control.params` e si
    rilegge a ogni giro, senza riavvio."""
    db = _db()
    tr = _trade(db)
    feed = lambda eid: _feed() if eid == EID else None  # noqa: E731
    S.run_once(market=Mercato(), db=db, now=NOW, greenup_feed=feed)
    assert [r["status"] for r in db.richieste] == ["proposed"]
    assert _chiusure(db, tr["id"]) == []
    db.control["params"] = {**db.control["params"], "uscite_protezione": "automatico"}
    S.run_once(market=Mercato(), db=db, now=NOW + timedelta(seconds=5), greenup_feed=feed)
    assert len(_chiusure(db, tr["id"])) == 1
    assert "uscita_automatica" in db.kinds()


# ===========================================================================
# 4. IL FRENO: mai un ordine a ogni giro, e dopo N fallimenti decide l'utente
# ===========================================================================
def test_automatico_fallito_freno_e_ripiego_sulla_proposta(monkeypatch):
    from Betfair.safe_strategy import execution as X

    chiamate: List[dict] = []

    def rifiuta(**kw):
        chiamate.append(kw)
        # le chiavi VERE del ramo fallito di `close_trade`
        return {"error": "chiusura_non_eseguita", "detail": "REJECTED dal book",
                "closing_trade_id": 999}

    monkeypatch.setattr(X, "close_trade", rifiuta)
    db = _db()
    tr = _trade(db)
    p = _params(uscite_protezione="automatico")
    _gira(db, p)
    assert len(chiamate) == 1
    f = db.attivita_di("uscita_automatica_fallita")
    assert f and f[0]["closing_trade_id"] == 999 and f[0]["scelta_utente"]
    # stesso istante e poco dopo: NESSUN nuovo invio (freno)
    _gira(db, p)
    _gira(db, p, now=NOW + timedelta(seconds=PR._RICONTROLLO_PROPOSTA_S - 1))
    assert len(chiamate) == 1
    assert db.richieste == []
    # secondo e terzo tentativo, ciascuno dopo il freno
    t = NOW
    for _ in range(PR._TENTATIVI_AUTOMATICI_MAX - 1):
        t = t + timedelta(seconds=PR._RICONTROLLO_PROPOSTA_S + 1)
        _gira(db, p, now=t)
    assert len(chiamate) == PR._TENTATIVI_AUTOMATICI_MAX
    # esauriti: la PROPOSTA (fail-closed, decide l'utente) e l'avviso critico
    assert [r["status"] for r in db.richieste] == ["proposed"]
    assert db.attivita_di("uscita_automatica_esaurita")[0]["critical"] is True
    assert db.get_trade(tr["id"])["meta"][PR.AUTOMATICA_KEY]["esaurita"] is True
    # e da li' in poi il bot non ci riprova da solo
    _gira(db, p, now=t + timedelta(minutes=10))
    assert len(chiamate) == PR._TENTATIVI_AUTOMATICI_MAX
    assert len(db.richieste) == 1


def test_automatico_chiusura_in_volo_non_conta_come_tentativo(monkeypatch):
    from Betfair.safe_strategy import execution as X

    monkeypatch.setattr(X, "close_trade", lambda **kw: {"error": "chiusura_in_corso",
                                                         "pending_closing_ids": [7]})
    db = _db()
    tr = _trade(db)
    _gira(db, _params(uscite_protezione="automatico"))
    m = db.get_trade(tr["id"])["meta"][PR.AUTOMATICA_KEY]
    assert m["tentativi"] == 0 and m["attesa"] == "chiusura_in_corso"
    assert db.richieste == [] and "uscita_automatica_fallita" not in db.kinds()


# ===========================================================================
# 5. IL BANCO: G1 e G4 conoscono il parametro
# ===========================================================================
def _ordine(params: dict, attivita: list) -> CERT.Momento:
    return CERT.Momento(tipo="ordine", now=NOW, params=params, event_id=EID, motore="v3",
                        richiesta={"side": "back", "customer_ref": "omega-t2",
                                   "market_id": CS_MID, "selection_id": SEL},
                        attivita=attivita)


def _cod(m: CERT.Momento) -> List[str]:
    return [v.codice for v in CERT.verifica(m)]


def test_G1_uscita_automatica_conforme_solo_col_parametro_su_automatico():
    att = [("uscita_automatica", {"closing_trade_id": 2, "esito": "eseguita",
                                  "scelta_utente": "uscite_protezione=automatico",
                                  "motivo_codice": "cap"})]
    assert "G1" not in _cod(_ordine(_params(uscite_protezione="automatico"), att))
    # stesso ordine, parametro su 'avvisa': il bot ha chiuso da solo
    assert "G1" in _cod(_ordine(_params(), att))
    # su 'automatico' ma senza la scelta dichiarata: non e' una dichiarazione
    senza = [("uscita_automatica", {"closing_trade_id": 2, "esito": "eseguita",
                                    "motivo_codice": "cap"})]
    assert "G1" in _cod(_ordine(_params(uscite_protezione="automatico"), senza))
    # il ramo FALLITO con l'ordine gia' partito resta dichiarato
    fallita = [("uscita_automatica_fallita", {"closing_trade_id": 2, "esito": "fallito",
                                              "scelta_utente": "uscite_protezione=automatico",
                                              "motivo_codice": "cap"})]
    assert "G1" not in _cod(_ordine(_params(uscite_protezione="automatico"), fallita))


def test_G1_d_giro_con_uscita_automatica_in_avvisa_e_una_violazione():
    att = [("uscita_automatica", {"trade_id": 1, "closing_trade_id": 2, "esito": "eseguita",
                                  "scelta_utente": "uscite_protezione=automatico",
                                  "motivo_codice": "protezione"})]
    giro = dict(tipo="giro", now=NOW, event_id=EID, motore="v3", attivita=att)
    assert "G1" in _cod(CERT.Momento(params=_params(), **giro))
    assert "G1" not in _cod(CERT.Momento(params=_params(uscite_protezione="automatico"),
                                         **giro))
    strano = [("uscita_automatica", {"trade_id": 1, "esito": "eseguita",
                                     "scelta_utente": "uscite_protezione=automatico",
                                     "motivo_codice": "tenere_vale_di_piu"})]
    assert "G1" in _cod(CERT.Momento(params=_params(uscite_protezione="automatico"),
                                     **{**giro, "attivita": strano}))


class _DbRighe:
    def __init__(self, meta: dict) -> None:
        self._meta = meta

    def get_trade(self, trade_id: int) -> dict:
        return {"id": int(trade_id), "meta": dict(self._meta)}


def test_G4_in_automatico_la_proposta_in_perdita_e_ammessa_solo_come_ripiego():
    from Betfair.omega import omega_v3 as V3
    pr = V3.PropostaUscita(True, "protezione", -1.4, 24.0, 2.0, -29.0, False, -2.0, 80.0,
                           0.2, "-")
    base = dict(tipo="proposta", now=NOW, event_id=EID, motore="v3", trade_id=1,
                stato_richiesta="proposed", proposta=pr)
    # avvisa: la regola del 17/09, la proposta in attesa e' giusta
    assert "G4" not in _cod(CERT.Momento(params=_params(), db=_DbRighe({}), **base))
    # automatico SENZA tentativi esauriti: doveva eseguirla il bot
    assert "G4" in _cod(CERT.Momento(params=_params(uscite_protezione="automatico"),
                                     db=_DbRighe({}), **base))
    # automatico col ripiego dichiarato: ammessa
    esaurita = {PR.AUTOMATICA_KEY: {"esaurita": True}}
    assert "G4" not in _cod(CERT.Momento(params=_params(uscite_protezione="automatico"),
                                         db=_DbRighe(esaurita), **base))


def test_il_banco_ha_lo_scenario_uscite_automatiche():
    from Betfair.omega.tools import replay_registrazioni as R

    assert R.SCENARI["uscite-automatiche"]["uscite_protezione"] == "automatico"
    assert R.SCENARI["uscite-automatiche"]["strategy_version"] == 3
    assert "uscite-automatiche" in R.SCENARI_DESCRITTI
    # tutti gli altri scenari restano su 'avvisa' (il default)
    for nome, sc in R.SCENARI.items():
        if nome != "uscite-automatiche":
            assert "uscite_protezione" not in sc, nome
