"""C.3 — i controlli di `safe_strategy/certificazione.py` sanno diventare ROSSI.

Un controllo che non sa diventare rosso non certifica: per ogni voce della SPEC
qui ci sono DUE casi, il sano (che deve tacere) e la violazione certa (che deve
scattare). Non e' una formalita': e' l'unica prova che il referto «zero
violazioni» del replay voglia dire qualcosa.

I FINTI PARLANO COME IL VERO. Il contesto NON e' costruito a mano: si passa
sempre da `engine.build_football_ctx_from_scan`, cioe' dalla stessa funzione con
cui il bot legge una riga di `safe_strategy_scan`, e il payload ha le chiavi e i
tipi che `service.Scanner.build_rows` scrive davvero (`odds` con
back/lay/back_size/lay_size/selection_id, `pre_ko`, `cs.any_other_home/away`,
`score_home`/`score_away` interi, `mo_status` testuale). Le valutazioni sono
quelle VERE (`evaluate_base`, `evaluate_esatto`, `evaluate_punta`), non copie.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import dataclasses
import inspect
from typing import Any, Dict, Optional

import pytest

from Betfair.safe_strategy import bot_db as BD
from Betfair.safe_strategy import certificazione as CERT
from Betfair.safe_strategy import db as SD
from Betfair.safe_strategy import engine as E
from Betfair.safe_strategy import exits as XE


# ---------------------------------------------------------------------------
# i finti: costruiti con le chiavi e i tipi del feed VERO
# ---------------------------------------------------------------------------
def coppia(back: Optional[float] = None, lay: Optional[float] = None,
           sid: int = 1) -> Dict[str, Any]:
    """Una coppia di quote come la scrive `Scanner._apply_market_book`."""
    return {"back": back, "lay": lay, "back_size": 50.0, "lay_size": 50.0,
            "selection_id": int(sid), "ltp": back or lay}


def payload(*, minute: int = 60, sh: int = 1, sa: int = 0,
            pre: Optional[Dict[str, float]] = None,
            home_back: float = 1.25, home_lay: float = 1.27,
            away_back: float = 24.0, away_lay: float = 25.0,
            any_home: Optional[float] = 40.0, any_away: Optional[float] = 45.0,
            inplay: bool = True, osservato: float = 60.0,
            stabile_da: Optional[int] = None) -> Dict[str, Any]:
    """Una riga di `safe_strategy_scan`, con le chiavi di `build_rows`."""
    return {
        "event_name": "Alfa v Beta", "home": "Alfa", "away": "Beta",
        "competition": None, "open_date": "2026-06-30T16:00:00+00:00",
        "inplay": inplay, "mo_market_id": "1.1", "mo_status": "OPEN",
        "odds": {"home": coppia(home_back, home_lay, 11),
                 "draw": coppia(6.0, 6.2, 13),
                 "away": coppia(away_back, away_lay, 12)},
        "minute": minute, "score_home": sh, "score_away": sa,
        "red_home": 0, "red_away": 0,
        "pre_ko": dict(pre or {"home": 1.60, "draw": 4.0, "away": 6.0}),
        "cs": {"market_id": "1.2", "status": "OPEN",
               "any_other_home": (coppia(any_home, any_home, 9063254)
                                  if any_home is not None else None),
               "any_other_away": (coppia(any_away, any_away, 9063255)
                                  if any_away is not None else None),
               "selections": []},
        "ht": None, "media": None, "score_raw": None, "timeline": None,
        "mo_total_matched": 1000.0, "odds_ts_ms": 0, "pressure_index": None,
        "_osservato": osservato,
        # da QUANDO il punteggio e' fermo: la PUNTA aspetta 3-4' dal gol
        "_stabile_da": (minute - 5) if stabile_da is None else stabile_da,
    }


def contesto(p: Dict[str, Any]):
    """Il contesto VERO del bot da una riga di scan."""
    return E.build_football_ctx_from_scan("1", p, p.get("_stabile_da"),
                                          float(p.get("_osservato") or 60.0))


def valutazione(strategia: str, p: Dict[str, Any],
                par: Optional[Dict[str, Any]] = None,
                sub: str = "home", pre_congelato=None) -> CERT.Valutazione:
    """Una `Valutazione` costruita con i valutatori VERI del motore."""
    params = E.merge_params(None)
    sezione = dict(params[strategia])
    sezione.update(par or {})
    params = {**params, strategia: sezione}
    ctx = contesto(p)
    if strategia == "base":
        ev = E.evaluate_base(ctx, sezione)
    elif strategia == "punta":
        ev = E.evaluate_punta(ctx, sezione)
    else:
        ev = E.evaluate_esatto(ctx, sezione, sub)
    return CERT.Valutazione(strategia=strategia, ctx=ctx, ev=ev, par=sezione,
                            params=params, pre_ko_congelato=pre_congelato)


def codici(oss) -> set:
    return {v.codice for v in CERT.verifica(oss)}


def solo(oss, codice: str) -> bool:
    """Il controllo `codice` ha davvero un caso e lo giudica senza errori."""
    sol: Dict[str, int] = {}
    CERT.verifica(oss, sol)
    return bool(sol.get(codice))


# ===========================================================================
# BASE — le voci della SPEC §1
# ===========================================================================
def test_base_sana_tace() -> None:
    """Segnale legittimo: favorita 1.60 pre-KO, 1.25 live, 1-0 al 60'."""
    v = valutazione("base", payload())
    assert v.segnale, [(c.id, c.value, c.ok) for c in v.ev.checks]
    assert codici(v) == set()


def test_b4_minuto_sotto_la_soglia_scatta() -> None:
    """Il controllo deve accorgersi di un segnale prima del 55'."""
    v = valutazione("base", payload(minute=50), par={"minuteMin": 40})
    assert v.segnale
    assert "B4" in codici(v)


def test_b4_soglia_aperta_un_minuto_alto_non_e_un_veto() -> None:
    """La fascia e' una SOGLIA (regola trasversale 14/09): all'85' si entra."""
    v = valutazione("base", payload(minute=85))
    assert "B4" not in codici(v)


def test_b5_punteggio_fuori_elenco_scatta() -> None:
    v = valutazione("base", payload(sh=3, sa=0), par={"scores": ["3-0"]})
    assert v.segnale
    # la banda della SPEC e' 1-0 / 2-1 / 2-0: 3-0 non c'e'
    assert "B5" in codici(v)


def test_b6_favorita_pre_match_fuori_banda_scatta() -> None:
    v = valutazione("base", payload(pre={"home": 1.10, "draw": 6.0, "away": 20.0}),
                    par={"favPreMin": 1.0, "favPreMax": 2.0,
                         "dogPreMin": 1.0, "dogPreMax": 30.0})
    assert v.segnale
    assert "B6" in codici(v)


def test_b7_sfavorita_pre_match_fuori_banda_scatta() -> None:
    v = valutazione("base", payload(pre={"home": 1.60, "draw": 6.0, "away": 20.0}),
                    par={"dogPreMin": 1.0, "dogPreMax": 30.0})
    assert v.segnale
    assert "B7" in codici(v)


def test_b8_banda_della_quota_di_banca_spostata_scatta() -> None:
    """Q1 (25/09). Prima di oggi: `test_b8_quota_live_favorita_fuori_banda_scatta`
    (Lettura A). Ora B8 difende la banda 20-34 della QUOTA DI BANCA: allargata
    nei parametri, il segnale a 40 passa il motore ma B8 lo accusa."""
    v = valutazione("base", payload(away_back=39.0, away_lay=40.0),
                    par={"dogLayMin": 1.01, "dogLayMax": 1000.0})
    assert v.segnale
    assert "B8" in codici(v)


def test_b8_banda_in_uso_diversa_dal_corso_scatta_anche_senza_segnale() -> None:
    """Lo specchio non basta: una banda diversa da 20-34 e' rossa sempre."""
    v = valutazione("base", payload(), par={"dogLayMin": 20.0, "dogLayMax": 35.0})
    assert solo(v, "B8")
    assert "B8" in codici(v)


def test_b8_motore_che_ignora_la_banda_scatta() -> None:
    """Banda in uso GIUSTA (20-34) ma un motore alterato che desse segnale col
    lay della perdente a 40: B8 guarda il prezzo vero della riga e lo accusa.
    Il segnale si forza sul contesto vero, come per B3."""
    v = valutazione("base", payload(away_back=39.0, away_lay=40.0))
    assert not v.segnale                      # il motore vero lo respinge
    # `entry_odds` dentro la banda: cosi' a parlare e' SOLO il prezzo della riga
    ev = dataclasses.replace(v.ev, state="signal", entry_odds=25.0)
    oss = CERT.Valutazione(strategia="base", ctx=v.ctx, ev=ev, par=v.par,
                           params=v.params)
    viol = [x for x in CERT.verifica(oss) if x.codice == "B8"]
    assert len(viol) == 1 and "40" in viol[0].dettaglio, viol


def test_b8_ordine_a_un_prezzo_fuori_banda_scatta() -> None:
    """La riga dice 25 (dentro), ma l'ordine partirebbe a 36: B8 guarda anche
    `entry_odds`, il prezzo con cui il bot piazza davvero."""
    v = valutazione("base", payload())
    assert v.segnale
    ev = dataclasses.replace(v.ev, entry_odds=36.0)
    oss = CERT.Valutazione(strategia="base", ctx=v.ctx, ev=ev, par=v.par,
                           params=v.params)
    viol = [x for x in CERT.verifica(oss) if x.codice == "B8"]
    assert len(viol) == 1 and "36" in viol[0].dettaglio, viol


def test_b8_bordi_20_e_34_tacciono() -> None:
    for lay in (20.0, 34.0):
        v = valutazione("base", payload(away_back=lay - 1, away_lay=lay))
        assert v.segnale, lay
        assert solo(v, "B8") and "B8" not in codici(v), lay


def test_b9_il_filtro_sulla_favorita_live_ricompare_scatta() -> None:
    """Q1 (25/09): nessun filtro sulla quota live della favorita. Se il check
    `favLive` ricomparisse nella valutazione, B9 deve accusarlo."""
    v = valutazione("base", payload())
    assert solo(v, "B9") and "B9" not in codici(v)
    finto = E.ConditionCheck("favLive", "Quota live favorita 1.2-1.34", "1,25", True)
    ev = dataclasses.replace(v.ev, checks=tuple(v.ev.checks) + (finto,))
    oss = CERT.Valutazione(strategia="base", ctx=v.ctx, ev=ev, par=v.par,
                           params=v.params)
    assert "B9" in codici(oss)


def test_b9_i_parametri_della_lettura_a_risolti_scattano() -> None:
    v = valutazione("base", payload(), par={"favLiveMin": 1.2, "favLiveMax": 1.34})
    assert "B9" in codici(v)


def test_b9_la_favorita_live_fuori_dalla_vecchia_banda_non_e_un_veto() -> None:
    """La favorita a 1,60 live: prima era "no" (Lettura A), ora si entra."""
    v = valutazione("base", payload(home_back=1.60, home_lay=1.62))
    assert v.segnale
    assert codici(v) == set()


def test_b3_selezione_bancata_non_e_la_sfavorita_scatta() -> None:
    """La squadra in vantaggio non si banca: e' la regola centrale della BASE."""
    v = valutazione("base", payload(sh=0, sa=1),
                    par={"scores": ["0-1", "1-0", "2-1", "2-0"]})
    # con 0-1 la favorita (casa) e' sotto: il check `score` la respinge gia',
    # quindi si forza il caso costruendo la valutazione a mano sul contesto vero
    ev = v.ev.__class__(variant="base", state="signal", checks=v.ev.checks,
                        headline="BANCA Alfa", side="LAY", selection="Alfa",
                        entry_odds=1.27, entry_size=10.0,
                        market_type="MATCH_ODDS", market_id="1.1",
                        selection_id=11)
    oss = CERT.Valutazione(strategia="base", ctx=v.ctx, ev=ev, par=v.par,
                           params=v.params)
    assert "B3" in codici(oss)


def test_b11_pre_ko_che_cambia_in_gioco_scatta() -> None:
    """Difetto 19 del catalogo: il riferimento 1X2 non si ricalcola dal live."""
    v = valutazione("base", payload(), pre_congelato={"home": 1.50, "draw": 4.0,
                                                      "away": 6.0})
    assert solo(v, "B11")
    assert "B11" in codici(v)


def test_b11_pre_ko_fermo_tace() -> None:
    v = valutazione("base", payload(), pre_congelato={"home": 1.60, "draw": 4.0,
                                                      "away": 6.0})
    assert solo(v, "B11")
    assert "B11" not in codici(v)


# --- le uscite della BASE ---------------------------------------------------
def tracker(**kw: Any) -> Dict[str, Any]:
    """Il tracker `meta.exit_track` con le chiavi VERE di `exits.track`."""
    base = {"side": "home", "entry_home": 1, "entry_away": 0,
            "last_home": 1, "last_away": 0, "minute": 60,
            "red_home": 0, "red_away": 0, "entry_red_home": 0,
            "entry_red_away": 0, "last_goal_ts": 0.0, "last_red_ts": 0.0}
    base.update(kw)
    return base


def uscita(strategia: str, tr: Dict[str, Any],
           par: Optional[Dict[str, Any]] = None) -> CERT.Uscita:
    p = XE.merge_exit_params(par)
    trade = {"id": 1, "strategy": strategia, "side": "lay", "mode": "live"}
    d = XE.decide(trade, None, {XE.TRACK_KEY: tr}, 10_000.0, p)
    return CERT.Uscita(strategia=strategia, trade=trade, tr=tr, decisione=d,
                       par=p, now_ts=10_000.0)


def test_b12_pareggio_della_sfavorita_e_uscita_in_perdita() -> None:
    u = uscita("base", tracker(last_away=1))
    assert u.decisione is not None and u.decisione.kind == "loss"
    assert "B12" not in codici(u)


def test_b12_scatta_se_la_regola_sparisce() -> None:
    """Falsificazione: si finge una decisione 'profit' sul pareggio."""
    u = uscita("base", tracker(last_away=1))
    u.decisione = XE.ExitDecision("profit", "inventata", 0.0)
    assert "B12" in codici(u)


def test_b14_minuto_di_uscita_fuori_dalla_finestra_della_spec() -> None:
    u = uscita("base", tracker(minute=90), par={"base_exit_minute": 20})
    assert "B14" in codici(u)


def test_b14_minuto_di_uscita_conforme_tace() -> None:
    u = uscita("base", tracker(minute=90))
    assert "B14" not in codici(u)


def test_b15_rosso_alla_sfavorita_e_neutro() -> None:
    """La SPEC: alla sfavorita il rosso e' neutro/positivo."""
    tr = tracker(red_away=1, entry_red_away=0)
    u = uscita("base", tr)
    assert solo(u, "B15")
    assert "B15" not in codici(u)


def test_b15_scatta_se_il_rosso_alla_sfavorita_facesse_uscire() -> None:
    tr = tracker(red_away=1, entry_red_away=0)
    u = uscita("base", tr)
    u.decisione = XE.ExitDecision("red_card", "rosso_alla_sfavorita", 0.0)
    assert "B15" in codici(u)


def test_b16_ritardo_di_assestamento_fuori_dalla_finestra_20_60s() -> None:
    u = uscita("base", tracker(last_away=1), par={"loss_settle_delay_s": 1})
    assert u.decisione is not None
    assert "B16" in codici(u)


# ===========================================================================
# ESATTO — le voci della SPEC §2
# ===========================================================================
def test_esatto_sano_tace() -> None:
    v = valutazione("esatto", payload(minute=50, sh=1, sa=0), sub="away")
    assert v.segnale, [(c.id, c.value, c.ok) for c in v.ev.checks]
    assert codici(v) - {"E10"} == set()


def test_e3_punteggio_fuori_elenco_scatta() -> None:
    v = valutazione("esatto", payload(minute=50, sh=3, sa=0),
                    par={"scores": ["3-0"]}, sub="away")
    assert v.segnale
    assert "E3" in codici(v)


def test_e4_lato_bancato_con_troppi_gol_scatta() -> None:
    v = valutazione("esatto", payload(minute=50, sh=2, sa=1),
                    par={"maxGoalsLaySide": 2, "scores": ["2-1"]}, sub="home")
    assert v.segnale
    assert "E4" in codici(v)


def test_e5_quota_di_entrata_fuori_banda_scatta() -> None:
    v = valutazione("esatto", payload(minute=50, sh=1, sa=0, any_away=100.0),
                    par={"entryMin": 1.0, "entryMax": 200.0}, sub="away")
    assert v.segnale
    assert "E5" in codici(v)


def test_e10_selezione_aggiuntiva_spenta_non_ha_casi() -> None:
    """Spenta, E10 non e' «sano»: non ha nessun caso, come B10 ed E6 con
    `requireControl` spento. Q7 (25/09): il DEFAULT e' ora ACCESO, quindi il
    caso spento si costruisce spegnendo il parametro (prima era il default)."""
    v = valutazione("esatto", payload(minute=50, sh=1, sa=0), sub="away",
                    par={"requireSelection": False})
    assert "E10" not in codici(v)
    assert not solo(v, "E10")


def test_e10_accesa_di_default_ha_casi_e_tace_senza_dato() -> None:
    """Q7 (25/09): acceso di default; riga senza `selection_hint` -> il check
    esiste, dichiara «dato assente» e NON blocca: E10 lo giudica e tace."""
    v = valutazione("esatto", payload(minute=50, sh=1, sa=0), sub="away")
    assert v.segnale
    assert solo(v, "E10") and "E10" not in codici(v)


def test_e10_accesa_senza_il_check_scatta() -> None:
    """Il difetto che E10 nasce per prendere: il parametro e' acceso e nessun
    check guarda la voce della SPEC."""
    v = valutazione("esatto", payload(minute=50, sh=1, sa=0), sub="away",
                    par={"requireSelection": False})
    par = dict(v.par)
    par["requireSelection"] = True
    v2 = CERT.Valutazione(strategia="esatto", ctx=v.ctx, ev=v.ev, par=par,
                          params=v.params)
    assert "E10" in codici(v2)


def test_e7_due_lati_altro_risultato_vivi_scattano() -> None:
    class _Db:
        trades = [{"id": 1, "strategy": "esatto", "status": "open",
                   "event_id": "1", "closes_trade_id": None},
                  {"id": 2, "strategy": "esatto", "status": "open",
                   "event_id": "1", "closes_trade_id": None}]

    class _Mk:
        def list_current_orders(self):
            return []

    c = CERT.Ciclo(db=_Db(), market=_Mk(), params={}, mode="live", now_ts=0.0)
    assert "E7" in codici(c)


def test_e9_gol_del_lato_bancato_e_uscita_in_perdita() -> None:
    tr = tracker(side="home", entry_home=1, last_home=2, entry_away=0, last_away=0)
    u = uscita("esatto", tr)
    assert u.decisione is not None and u.decisione.kind == "loss"
    assert "E9" not in codici(u)


def test_e9_scatta_se_il_gol_e_attribuito_al_lato_sbagliato() -> None:
    tr = tracker(side="home", entry_home=1, last_home=1, entry_away=0, last_away=1)
    u = uscita("esatto", tr)
    u.decisione = XE.ExitDecision("loss", "lato_bancato_segna", 0.0)
    assert "E9" in codici(u)


# ===========================================================================
# PUNTA — le voci della SPEC §4
# ===========================================================================
def test_punta_sana_tace() -> None:
    v = valutazione("punta", payload(minute=70, sh=2, sa=0, home_back=1.05))
    assert v.segnale, [(c.id, c.value, c.ok) for c in v.ev.checks]
    assert codici(v) == set()


def test_p3_punteggio_fuori_elenco_scatta() -> None:
    v = valutazione("punta", payload(minute=70, sh=4, sa=0, home_back=1.05),
                    par={"scores": ["4-0"]})
    assert v.segnale
    assert "P3" in codici(v)


def test_p4_quota_di_entrata_fuori_banda_scatta() -> None:
    v = valutazione("punta", payload(minute=70, sh=2, sa=0, home_back=1.50),
                    par={"entryMin": 1.0, "entryMax": 2.0})
    assert v.segnale
    assert "P4" in codici(v)


def test_p5_attesa_dopo_il_gol_sotto_i_3_minuti_scatta() -> None:
    """La SPEC dice 3-4': una soglia a 1' e' una difformita', non una scelta."""
    v = valutazione("punta", payload(minute=70, sh=2, sa=0, home_back=1.05),
                    par={"minMinutesAfterGoal": 1})
    assert "P5" in codici(v)


def test_p5_ingresso_troppo_vicino_al_gol_scatta() -> None:
    v = valutazione("punta", payload(minute=70, sh=2, sa=0, home_back=1.05,
                                     stabile_da=69))
    assert not v.segnale        # e' il motore stesso a fermarlo
    v.ev = v.ev.__class__(variant="punta", state="signal", checks=v.ev.checks,
                          headline="PUNTA Alfa", side="BACK", selection="Alfa",
                          entry_odds=1.05, entry_size=10.0,
                          market_type="MATCH_ODDS", market_id="1.1",
                          selection_id=11)
    assert "P5" in codici(v)


def test_p7_gol_subito_e_uscita_in_perdita_immediata() -> None:
    tr = tracker(side="home", entry_home=2, last_home=3, entry_away=0, last_away=1)
    u = uscita("punta", tr)
    assert u.decisione is not None and u.decisione.kind == "loss"
    assert "P7" not in codici(u)


def test_p7_scatta_se_il_gol_subito_non_producesse_una_perdita() -> None:
    tr = tracker(side="home", entry_home=2, last_home=3, entry_away=0, last_away=1)
    u = uscita("punta", tr)
    u.decisione = XE.ExitDecision("profit", "favorita_segna_ancora", 0.0)
    assert "P7" in codici(u)


def test_p10_la_punta_non_esce_per_rosso() -> None:
    tr = tracker(side="home", entry_home=2, last_home=2, minute=90)
    u = uscita("punta", tr)
    assert u.decisione is not None
    assert "P10" not in codici(u)
    u.decisione = XE.ExitDecision("red_card", "rosso_alla_favorita", 0.0)
    assert "P10" in codici(u)


# ===========================================================================
# T / J — trasversali e i difetti del 15/09
# ===========================================================================
class _Esito:
    """`execution.PlaceOutcome` finto con le chiavi del vero."""

    def __init__(self, status="open", size=2.0, price=10.0, bet_id="b1",
                 size_requested=None, fill_note="live_rest:EXECUTION_COMPLETE"):
        self.status = status
        self.size = size
        self.price = price
        self.bet_id = bet_id
        self.size_requested = size_requested
        self.fill_note = fill_note


def riga_ordine(**kw: Any) -> Dict[str, Any]:
    """Un ordine nella forma di `omega_market.list_current_orders` (snake_case)."""
    base = {"bet_id": "b1", "market_id": "1.1", "selection_id": 12, "side": "lay",
            "status": "EXECUTION_COMPLETE", "size_matched": 2.0,
            "avg_price_matched": 10.0, "size_remaining": 0.0, "size_settled": 2.0,
            "customer_order_ref": "safe-t1", "size_cancelled": 0.0,
            "size_lapsed": 0.0, "size_voided": 0.0, "price_requested": 10.0,
            "size_requested": 2.0, "average_price_matched": 10.0}
    base.update(kw)
    return base


def ordine(**kw: Any) -> CERT.Ordine:
    riga = kw.pop("riga", {"id": 1, "strategy": "base", "side": "lay",
                           "mode": "live", "size": 2.0, "price": 10.0,
                           "bet_id": "b1", "origin": "auto"})
    return CERT.Ordine(strategia=str(riga.get("strategy") or ""), riga=riga,
                       esito=kw.pop("esito", _Esito()), mode="live",
                       params=kw.pop("params", E.merge_params(None)),
                       stato_betfair=kw.pop("stato_betfair", riga_ordine()),
                       apertura=kw.pop("apertura", True),
                       origine=str(riga.get("origin") or ""),
                       size_chiesta=kw.pop("size_chiesta", 2.0))


def test_j1_riga_con_numeri_diversi_da_betfair_scatta() -> None:
    o = ordine(riga={"id": 1, "strategy": "base", "side": "lay", "mode": "live",
                     "size": 2.0, "price": 10.0, "bet_id": "b1", "origin": "auto"},
               stato_betfair=riga_ordine(size_matched=1.5))
    assert solo(o, "J1")
    assert "J1" in codici(o)


def test_j1_riga_allineata_tace() -> None:
    assert "J1" not in codici(ordine())


def test_j2_riga_aperta_senza_abbinamento_scatta() -> None:
    o = ordine(esito=_Esito(status="open", size=0.0))
    assert "J2" in codici(o)


def test_j3_prezzo_medio_diverso_da_betfair_scatta() -> None:
    o = ordine(riga={"id": 1, "strategy": "base", "side": "lay", "mode": "live",
                     "size": 2.0, "price": 12.0, "bet_id": "b1", "origin": "auto"})
    assert solo(o, "J3")
    assert "J3" in codici(o)


def test_j6_bet_id_non_scritto_scatta() -> None:
    o = ordine(riga={"id": 1, "strategy": "base", "side": "lay", "mode": "live",
                     "size": 2.0, "price": 10.0, "bet_id": None, "origin": "auto"})
    assert "J6" in codici(o)


def test_t2_fill_parziale_e_un_errore() -> None:
    o = ordine(stato_betfair=riga_ordine(size_matched=1.0, size_requested=2.0))
    assert solo(o, "T2")
    assert "T2" in codici(o)


def test_t2_fill_intero_tace() -> None:
    assert "T2" not in codici(ordine())


def test_t1_stake_maggiore_di_quello_dichiarato_scatta() -> None:
    o = ordine(riga={"id": 1, "strategy": "base", "side": "lay", "mode": "live",
                     "size": 99.0, "price": 10.0, "bet_id": "b1", "origin": "auto"})
    assert "T1" in codici(o)


def test_t8_modalita_ereditata_invece_che_scritta_scatta() -> None:
    par = E.merge_params(None)
    par["strategy_modes"] = {"base": "paper"}
    o = ordine(params=par,
               riga={"id": 1, "strategy": "base", "side": "lay", "mode": "live",
                     "size": 2.0, "price": 10.0, "bet_id": "b1", "origin": "auto"})
    assert "T8" in codici(o)


def test_t8_non_accusa_il_percorso_manuale() -> None:
    """Falso positivo escluso: il manuale non passa da `strategy_modes`."""
    par = E.merge_params(None)
    par["strategy_modes"] = {"base": "paper"}
    o = ordine(params=par,
               riga={"id": 1, "strategy": "manual", "side": "lay", "mode": "live",
                     "size": 2.0, "price": 10.0, "bet_id": "b1", "origin": "manual"})
    sol: Dict[str, int] = {}
    CERT.verifica(o, sol)
    assert not sol.get("T8")


def test_j4_riga_terminale_con_ordine_vivo_scatta() -> None:
    class _Db:
        trades = [{"id": 1, "status": "error", "bet_id": "b9", "strategy": "base"}]

    class _Mk:
        def list_current_orders(self):
            return [riga_ordine(bet_id="b9", status="EXECUTABLE",
                                size_remaining=2.0, size_matched=0.0)]

    c = CERT.Ciclo(db=_Db(), market=_Mk(), params={}, mode="live", now_ts=0.0)
    assert "J4" in codici(c)


def test_j5_closes_trade_id_solo_nel_meta_scatta() -> None:
    class _Db:
        trades = [{"id": 2, "status": "open", "closes_trade_id": None,
                   "meta": {"closes_trade_id": 1}, "strategy": "base"}]

    class _Mk:
        def list_current_orders(self):
            return []

    c = CERT.Ciclo(db=_Db(), market=_Mk(), params={}, mode="live", now_ts=0.0)
    assert "J5" in codici(c)


def test_j7_doppio_ordine_sullo_stesso_segnale_scatta() -> None:
    class _Db:
        trades = [{"id": 1, "status": "open", "event_id": "1",
                   "signal_key": "k", "mode": "live", "strategy": "base"},
                  {"id": 2, "status": "open", "event_id": "1",
                   "signal_key": "k", "mode": "live", "strategy": "base"}]

    class _Mk:
        def list_current_orders(self):
            return []

    c = CERT.Ciclo(db=_Db(), market=_Mk(), params={}, mode="live", now_ts=0.0)
    assert "J7" in codici(c)


def test_t9_feed_stantio_con_aperture_scatta() -> None:
    class _Db:
        trades: list = []
        attivita: list = []

        def aggregates(self, mode=None):
            return {}

    class _Mk:
        def list_current_orders(self):
            return []

    c = CERT.Ciclo(db=_Db(), market=_Mk(), params={}, mode="live", now_ts=0.0,
                   aperture_nel_giro=1, feed_stantio=True)
    assert "T9" in codici(c)


# ===========================================================================
# IL BANCO — il doppio del database parla come il vero
# ===========================================================================
# Le funzioni di `bot_db` che il servizio chiama davvero (`db.<nome>(` in
# bot_service/execution/exits/risk/opportunity) piu' quelle lette con
# `getattr(db, ...)`: se una manca dal doppio il servizio riceve `None` e il
# replay certifica un comportamento che in produzione non esiste.
FUNZIONI_BOT_DB = (
    "read_control", "set_control", "log", "insert_trade", "update_trade",
    "delete_trade", "get_trade", "list_trades", "open_trades",
    "closing_trades_for", "trade_by_idempotency_key", "traded_signal_keys",
    "aggregates", "place_attempts", "recent_activity", "pending_requests",
    "proposta_di_chiusura_viva", "scrivi_proposta_di_chiusura", "chiudi_proposta",
    "set_request_status", "fail_stale_processing", "upsert_opportunities",
    "purge_opportunities", "delete_opportunities", "get_event",
    "fixtures_for_window", "fixture_analysis", "fetch_scan_rows",
    "scanner_status", "live_follow_status", "runner_heartbeat",
    "enqueue_live_order", "get_live_order_request_by_ref",
    "get_live_order_request", "revoke_live_order_request",
    "get_live_order_mirror",
)
FUNZIONI_SCAN_DB = ("list_scan_event_ids", "load_scan_pre_ko", "upsert_scan_rows",
                    "delete_scan_rows", "upsert_status",
                    "list_mike_followed_event_ids")


def _firma(fn) -> list:
    """I nomi dei parametri, senza `self` e senza le annotazioni."""
    return [p.name for p in inspect.signature(fn).parameters.values()
            if p.name != "self"]


@pytest.mark.parametrize("nome", FUNZIONI_BOT_DB)
def test_il_doppio_del_db_ha_la_firma_del_vero(nome: str) -> None:
    from Betfair.safe_strategy.tools.replay_registrazioni import DbSafeMemoria

    vero = getattr(BD, nome)
    finto = getattr(DbSafeMemoria, nome, None)
    assert finto is not None, f"il banco non ha `{nome}`: il servizio riceverebbe None"
    assert _firma(finto) == _firma(vero), f"firma diversa dal vero per `{nome}`"


@pytest.mark.parametrize("nome", FUNZIONI_SCAN_DB)
def test_il_doppio_dello_scanner_ha_la_firma_del_vero(nome: str) -> None:
    from Betfair.safe_strategy.tools.replay_registrazioni import DbSafeMemoria

    vero = getattr(SD, nome)
    finto = getattr(DbSafeMemoria, nome, None)
    assert finto is not None, f"il banco non ha `{nome}`"
    assert _firma(finto) == _firma(vero), f"firma diversa dal vero per `{nome}`"


def test_insert_trade_torna_id_e_rispetta_l_indice_unico() -> None:
    from Betfair.safe_strategy.tools.replay_registrazioni import DbSafeMemoria

    db = DbSafeMemoria({"status": "running", "mode": "live", "params": {}})
    riga = {"event_id": "1", "signal_key": "k", "origin": "auto", "status": "pending",
            "mode": "live", "strategy": "base"}
    tid = db.insert_trade(dict(riga))
    assert isinstance(tid, int) and tid > 0
    with pytest.raises(RuntimeError):
        db.insert_trade(dict(riga))


def test_open_trades_non_include_le_riserve_pending() -> None:
    from Betfair.safe_strategy.tools.replay_registrazioni import DbSafeMemoria

    db = DbSafeMemoria({"status": "running", "mode": "live", "params": {}})
    db.insert_trade({"event_id": "1", "status": "pending", "mode": "live",
                     "origin": "manual", "strategy": "base"})
    db.insert_trade({"event_id": "1", "status": "open", "mode": "live",
                     "origin": "manual", "strategy": "base"})
    aperte = db.open_trades()
    assert [r["status"] for r in aperte] == ["open"]
    assert db.open_trades(mode="paper") == []


def test_traded_signal_keys_torna_un_set_di_tuple() -> None:
    from Betfair.safe_strategy.tools.replay_registrazioni import DbSafeMemoria

    db = DbSafeMemoria({"status": "running", "mode": "live", "params": {}})
    db.insert_trade({"event_id": "1", "signal_key": "k", "origin": "auto",
                     "status": "open", "mode": "live", "strategy": "base"})
    assert db.traded_signal_keys("live") == {("1", "k")}
    assert db.traded_signal_keys("paper") == set()


# ===========================================================================
# la tabella del referto: nessuna voce della SPEC sparisce
# ===========================================================================
def test_ogni_controllo_ha_una_voce_della_spec_e_una_strategia() -> None:
    voci = CERT.voci_spec()
    assert len(voci) == len(CERT.elenco_controlli())
    for cod, fam, voce, regola in voci:
        assert voce.strip(), f"{cod} senza voce della SPEC"
        assert regola.strip(), f"{cod} senza regola"
        assert fam in ("base", "esatto", "punta", "trasversale")


def test_la_tabella_dichiara_non_lo_so_su_chi_non_e_stato_sollecitato() -> None:
    ref = CERT.Referto(event_id="1")
    righe = "\n".join(CERT.tabella_per_strategia(ref))
    assert "non lo so" in righe
    for cod, _reg in CERT.elenco_controlli():
        assert f" {cod:4} " in righe or f"  {cod} " in righe, f"{cod} assente dalla tabella"


def test_osserva_valutazione_scrive_il_motivo_dello_scarto() -> None:
    """«Scartata per X» e' una prova; il silenzio no."""
    ref = CERT.Referto(event_id="1")
    v = valutazione("base", payload(minute=10))
    CERT.osserva_valutazione(ref, v)
    assert ref.valutazioni["base"] == 1
    assert ref.stati_valutazione["base"]["no"] == 1
    assert any(k.startswith("minute:") for k in ref.scarti["base"])


# ===========================================================================
# T12 — MAI due lay a mercato sulla stessa selezione (regola dell'utente 16/09)
# ===========================================================================
class _Mercato:
    """`list_current_orders` con le chiavi VERE di `omega_market`."""

    def __init__(self, ordini=()):
        self._ordini = list(ordini)

    def list_current_orders(self, strategy_ref=None):
        return list(self._ordini)


class _Database:
    def __init__(self, trades=(), attivita=()):
        self.trades = list(trades)
        self.attivita = list(attivita)

    def aggregates(self, mode=None):
        return {}


def ciclo(db, market, **kw) -> CERT.Ciclo:
    return CERT.Ciclo(db=db, market=market, params={}, mode="live",
                      now_ts=0.0, **kw)


def lay(id_: int, stato: str, bet_id=None, sid: int = 12,
        mid: str = "1.1", origin: str = "auto") -> Dict[str, Any]:
    """Una lay del BOT (`origin='auto'`) se non si dice altrimenti."""
    return {"id": id_, "side": "lay", "status": stato, "market_id": mid,
            "selection_id": sid, "bet_id": bet_id, "strategy": "base",
            "event_id": "1", "mode": "live", "origin": origin}


def test_t12_una_sola_lay_in_volo_tace() -> None:
    c = ciclo(_Database([lay(1, "pending")]), _Mercato())
    assert solo(c, "T12")
    assert "T12" not in codici(c)


def test_t12_due_lay_in_volo_sulla_stessa_selezione_scatta() -> None:
    c = ciclo(_Database([lay(1, "pending"), lay(2, "pending")]), _Mercato())
    assert "T12" in codici(c)


def test_t12_due_lay_su_selezioni_diverse_tacciono() -> None:
    c = ciclo(_Database([lay(1, "pending", sid=12), lay(2, "pending", sid=11)]),
              _Mercato())
    assert "T12" not in codici(c)


def test_t12_riga_e_suo_ordine_sono_la_stessa_lay() -> None:
    """Falso positivo escluso: una riga col suo `bet_id` non conta due volte."""
    ordine_vivo = riga_ordine(bet_id="b7", status="EXECUTABLE",
                              size_remaining=2.0, size_matched=0.0,
                              side="lay", selection_id=12, market_id="1.1")
    c = ciclo(_Database([lay(1, "pending", bet_id="b7")]), _Mercato([ordine_vivo]))
    assert solo(c, "T12")
    assert "T12" not in codici(c)


def test_t12_residuo_vivo_piu_seconda_lay_scatta() -> None:
    """Una posizione aperta col residuo ancora a mercato PIU' una nuova lay."""
    ordine_vivo = riga_ordine(bet_id="b7", status="EXECUTABLE",
                              size_remaining=1.0, size_matched=1.0,
                              side="lay", selection_id=12, market_id="1.1")
    c = ciclo(_Database([lay(1, "open", bet_id="b7"), lay(2, "pending")]),
              _Mercato([ordine_vivo]))
    assert "T12" in codici(c)


def _back(id_: int, stato: str = "hedged", sid: int = 12, mid: str = "1.1",
          origin: str = "auto") -> Dict[str, Any]:
    return {"id": id_, "side": "back", "status": stato, "market_id": mid,
            "selection_id": sid, "bet_id": f"b{id_}", "strategy": "punta",
            "event_id": "1", "mode": "live", "origin": origin}


def test_t12_due_chiusure_abbinate_di_due_back_diversi_tacciono() -> None:
    """16/09, trovato dalle SINTETICHE della PUNTA: la PUNTA punta e chiude
    BANCANDO la stessa selezione. Due operazioni consecutive lasciano due
    righe lay `open`, ognuna appaiata al SUO back: posizione piatta, non
    scoperta. Accusarle era un falso positivo del controllo (T12 x159)."""
    db = _Database([
        _back(1), dict(lay(2, "open", bet_id="c2"), closes_trade_id=1,
                       strategy="punta"),
        _back(3), dict(lay(4, "open", bet_id="c4"), closes_trade_id=3,
                       strategy="punta"),
    ])
    c = ciclo(db, _Mercato())
    assert "T12" not in codici(c)
    # e il motivo e' esattamente quello: nessuna delle due conta come lay viva
    assert CERT._lay_in_volo(c) == {}


def test_t12_due_lay_di_APERTURA_abbinate_scattano_lo_stesso() -> None:
    """La regola dell'utente resta intera: due lay di APERTURA abbinate sulla
    stessa selezione sono responsabilita' doppia, e il controllo le prende."""
    c = ciclo(_Database([lay(1, "open", bet_id="a1"), lay(2, "open", bet_id="a2")]),
              _Mercato())
    assert "T12" in codici(c)


def test_t12_chiusura_su_UNALTRA_selezione_conta_lo_stesso() -> None:
    """L'eccezione vale solo se il back chiuso e' sulla STESSA selezione: una
    lay che «chiude» un back di un altro runner e' responsabilita' vera."""
    db = _Database([
        dict(_back(1), selection_id=99),
        dict(lay(2, "open", bet_id="c2"), closes_trade_id=1),
        lay(3, "open", bet_id="a3"),
    ])
    assert "T12" in codici(ciclo(db, _Mercato()))


def test_t12_chiusura_con_RESIDUO_ancora_a_mercato_conta() -> None:
    """Una chiusura non ancora abbinata del tutto e' ancora a mercato: puo'
    abbinarsi insieme all'altra lay, e il controllo la deve vedere."""
    ordine_vivo = riga_ordine(bet_id="c2", status="EXECUTABLE",
                              size_remaining=1.0, size_matched=1.0,
                              side="lay", selection_id=12, market_id="1.1")
    db = _Database([
        _back(1), dict(lay(2, "open", bet_id="c2"), closes_trade_id=1),
        lay(3, "pending"),
    ])
    assert "T12" in codici(ciclo(db, _Mercato([ordine_vivo])))


def test_t12_sostituzione_cancel_piu_place_nello_stesso_giro_e_un_reperto() -> None:
    db = _Database([lay(1, "pending", bet_id="b7")])
    c = ciclo(db, _Mercato(),
              attivita_del_giro=[("cancel_richiesto", {"trade_id": 1}, "1"),
                                 ("place", {"trade_id": 1}, "1")])
    assert "T12" in codici(c)


def test_t12_solo_un_cancel_non_e_una_sostituzione() -> None:
    db = _Database([lay(1, "pending", bet_id="b7")])
    c = ciclo(db, _Mercato(),
              attivita_del_giro=[("cancel_richiesto", {"trade_id": 1}, "1")])
    assert "T12" not in codici(c)


def test_t12_non_ha_un_caso_senza_lay_vive() -> None:
    """Senza nessuna lay viva il controllo NON deve essere contato fra i
    sollecitati: «zero violazioni» non vorrebbe dire niente."""
    c = ciclo(_Database([lay(1, "won", bet_id="b7")]), _Mercato())
    assert not solo(c, "T12")


def test_t12_due_lay_gia_abbinate_sulla_stessa_selezione_scattano() -> None:
    """«Se si abbinano siamo scoperti»: due lay ABBINATE sono il danno, non il
    rischio. Col FOK e' anche l'unico caso che capita davvero."""
    c = ciclo(_Database([lay(1, "open", bet_id="b1"), lay(2, "open", bet_id="b2")]),
              _Mercato())
    assert "T12" in codici(c)


def test_t12_una_lay_abbinata_e_la_sua_chiusura_back_tacciono() -> None:
    """Falso positivo escluso: la chiusura di una lay e' un BACK, non una lay."""
    chiusura = {"id": 2, "side": "back", "status": "open", "market_id": "1.1",
                "selection_id": 12, "bet_id": "b2", "strategy": "base",
                "event_id": "1", "mode": "live", "closes_trade_id": 1}
    c = ciclo(_Database([lay(1, "open", bet_id="b1"), chiusura]), _Mercato())
    assert solo(c, "T12")
    assert "T12" not in codici(c)


# ===========================================================================
# IL BANCO GIRA NELLA SUITE (`pytest -m cert`)
# ===========================================================================
# Ordine dell'utente del 16/09: il banco e' «da oggi standard e usato di
# default». Un campione CORTO, per far arrivare il rosso subito se qualcuno
# rompe la catena scanner -> feed -> `run_once` -> ordini. Il replay completo
# resta il comando sulla partita di riferimento:
#   python -m Betfair.stream.backtest.certifica safe_calcio 35760084 --scenari tutti
import os

_RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_CAMPIONE = "35823616"      # la piu' corta del corpus calcio (~2,2k tick)


@pytest.mark.cert
def test_il_campione_corto_passa_senza_violazioni() -> None:
    """La CATENA, su una registrazione corta: zero violazioni.

    ⚠️ Non certifica la CONDOTTA delle tre strategie: su questa registrazione
    non entrano (e il referto lo dice). Certifica che il collegamento esista e
    non esploda — che e' esattamente cio' che una modifica al bot puo' rompere
    senza che nessun test unitario se ne accorga.
    """
    from Betfair.stream import config_stream as CFG

    cartella = CFG.DATA_DIR
    raw = os.path.join(cartella, _CAMPIONE, f"{_CAMPIONE}.raw.jsonl")
    if not os.path.isfile(raw):
        pytest.skip(f"registrazione {_CAMPIONE} assente")
    from Betfair.safe_strategy.tools import replay_registrazioni as R

    ref = R.certifica_scenario(_CAMPIONE, data_dir=cartella, scenario="base")
    assert [str(v) for v in ref.violazioni] == []
    assert ref.decisioni > 0, "il servizio non ha mai girato: catena interrotta"


# ===========================================================================
# T12 ristretto alle operazioni DEL BOT (chiarimento dell'utente, 16/09)
# ===========================================================================
def test_t12_due_lay_MANUALI_non_sono_una_violazione_del_bot() -> None:
    """«Se io in manuale faccio altre operazioni, il bot deve ignorarle»."""
    c = ciclo(_Database([lay(1, "open", bet_id="b1", origin="manual"),
                         lay(2, "open", bet_id="b2", origin="manual")]),
              _Mercato())
    assert not solo(c, "T12")      # non ha nemmeno un caso da giudicare
    assert "T12" not in codici(c)


def test_t12_una_automatica_piu_una_manuale_tace() -> None:
    c = ciclo(_Database([lay(1, "open", bet_id="b1", origin="auto"),
                         lay(2, "open", bet_id="b2", origin="manual")]),
              _Mercato())
    assert solo(c, "T12")
    assert "T12" not in codici(c)


def test_t12_due_lay_del_bot_restano_rosse() -> None:
    c = ciclo(_Database([lay(1, "open", bet_id="b1"), lay(2, "open", bet_id="b2")]),
              _Mercato())
    assert "T12" in codici(c)


def test_t12_ordine_vivo_di_una_riga_manuale_non_conta() -> None:
    vivo = riga_ordine(bet_id="b9", status="EXECUTABLE", size_remaining=2.0,
                       size_matched=0.0, side="lay", selection_id=12,
                       market_id="1.1", customer_order_ref="safe-t9")
    db = _Database([lay(1, "open", bet_id="b1", origin="auto"),
                    {"id": 9, "side": "lay", "status": "pending", "market_id": "1.1",
                     "selection_id": 12, "bet_id": "b9", "strategy": "manual",
                     "event_id": "1", "mode": "live", "origin": "manual"}])
    c = ciclo(db, _Mercato([vivo]))
    assert "T12" not in codici(c)


# ===========================================================================
# T13 — il bot non tocca le operazioni del trader
# ===========================================================================
def test_t13_tace_se_il_bot_lavora_solo_sulle_sue() -> None:
    db = _Database([lay(1, "open", bet_id="b1", origin="manual"),
                    lay(2, "open", bet_id="b2", origin="auto")])
    c = ciclo(db, _Mercato())
    assert solo(c, "T13")
    assert "T13" not in codici(c)


def test_t13_il_bot_che_chiude_una_riga_manuale_scatta() -> None:
    chiusura = {"id": 3, "side": "back", "status": "pending", "market_id": "1.1",
                "selection_id": 12, "strategy": "base", "event_id": "1",
                "mode": "live", "origin": "auto", "closes_trade_id": 1}
    db = _Database([lay(1, "open", bet_id="b1", origin="manual"), chiusura])
    c = ciclo(db, _Mercato())
    assert "T13" in codici(c)


def test_t13_attivita_automatica_su_una_riga_manuale_scatta() -> None:
    db = _Database([lay(1, "open", bet_id="b1", origin="manual")])
    c = ciclo(db, _Mercato(),
              attivita_del_giro=[("exit", {"trade_id": 1}, "1")])
    assert "T13" in codici(c)


def test_t13_una_richiesta_del_trader_sulla_sua_riga_e_legittima() -> None:
    """`cashout` e `place` li scrive anche `execution.close_trade`, cioe' il
    bottone del trader: accusarli sarebbe un falso positivo del controllo."""
    db = _Database([lay(1, "open", bet_id="b1", origin="manual")])
    c = ciclo(db, _Mercato(),
              attivita_del_giro=[("cashout", {"trade_id": 1}, "1"),
                                 ("place", {"trade_id": 1}, "1")])
    assert solo(c, "T13")
    assert "T13" not in codici(c)


# ===========================================================================
# T14 — dopo il cash-out globale dell'utente il bot non fa altro
# ===========================================================================
def _riga_auto(id_: int, quando: str) -> Dict[str, Any]:
    return {"id": id_, "side": "lay", "status": "open", "market_id": "1.1",
            "selection_id": 12, "strategy": "esatto", "event_id": "1",
            "mode": "live", "origin": "auto", "placed_at": quando}


def test_t14_non_ha_un_caso_senza_cash_out_globale() -> None:
    c = ciclo(_Database([_riga_auto(1, "2026-06-30T17:00:00+00:00")]), _Mercato())
    assert not solo(c, "T14")


def test_t14_apertura_dopo_il_cash_out_globale_scatta() -> None:
    from datetime import datetime, timezone

    quando = datetime(2026, 6, 30, 17, 0, tzinfo=timezone.utc).timestamp()
    c = ciclo(_Database([_riga_auto(1, "2026-06-30T17:10:00+00:00")]), _Mercato(),
              chiuso_dall_utente={"1": quando})
    assert "T14" in codici(c)


def test_t14_le_righe_nate_prima_non_sono_una_violazione() -> None:
    from datetime import datetime, timezone

    quando = datetime(2026, 6, 30, 17, 0, tzinfo=timezone.utc).timestamp()
    c = ciclo(_Database([_riga_auto(1, "2026-06-30T16:30:00+00:00")]), _Mercato(),
              chiuso_dall_utente={"1": quando})
    assert solo(c, "T14")
    assert "T14" not in codici(c)


def test_t14_attivita_operativa_dopo_il_cash_out_globale_scatta() -> None:
    from datetime import datetime, timezone

    quando = datetime(2026, 6, 30, 17, 0, tzinfo=timezone.utc).timestamp()
    c = ciclo(_Database([_riga_auto(1, "2026-06-30T16:30:00+00:00")]), _Mercato(),
              chiuso_dall_utente={"1": quando},
              attivita_del_giro=[("exit", {"trade_id": 1, "event_id": "1"}, "1")])
    assert "T14" in codici(c)


def test_t14_il_cashout_del_trader_non_e_unattivita_del_bot() -> None:
    """Dopo il cash-out globale sono proprio le richieste del trader a girare:
    il `cashout` che ne esce non e' il bot che «fa altro»."""
    from datetime import datetime, timezone

    quando = datetime(2026, 6, 30, 17, 0, tzinfo=timezone.utc).timestamp()
    c = ciclo(_Database([_riga_auto(1, "2026-06-30T16:30:00+00:00")]), _Mercato(),
              chiuso_dall_utente={"1": quando},
              attivita_del_giro=[("cashout", {"trade_id": 1, "event_id": "1"}, "1")])
    assert solo(c, "T14")
    assert "T14" not in codici(c)


def test_t14_gamba_automatica_su_una_posizione_gia_chiusa_dal_trader_scatta() -> None:
    from datetime import datetime, timezone

    quando = datetime(2026, 6, 30, 17, 0, tzinfo=timezone.utc).timestamp()
    padre = _riga_auto(1, "2026-06-30T16:30:00+00:00")
    del_trader = {"id": 2, "side": "back", "status": "open", "market_id": "1.1",
                  "selection_id": 12, "strategy": "esatto", "event_id": "1",
                  "mode": "live", "origin": "manual", "closes_trade_id": 1,
                  "placed_at": "2026-06-30T17:00:00+00:00"}
    del_bot = {"id": 3, "side": "back", "status": "open", "market_id": "1.1",
               "selection_id": 12, "strategy": "esatto", "event_id": "1",
               "mode": "live", "origin": "auto", "closes_trade_id": 1,
               "size": 0.04, "placed_at": "2026-06-30T17:00:00+00:00"}
    c = ciclo(_Database([padre, del_trader, del_bot]), _Mercato(),
              chiuso_dall_utente={"1": quando})
    assert "T14" in codici(c)
