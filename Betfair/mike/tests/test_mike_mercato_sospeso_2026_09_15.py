"""SOSPESO NON E' CHIUSO (15/09/2026).

Regola dell'utente, testuale:

> «SOSPESO, il mercato puo' riaprirsi; CHIUSO, il mercato e' chiuso e non si
> puo' piu' operare. Sono stati diversi e vanno gestiti guardando e chiedendo a
> Betfair.»

I difetti li ha trovati la CERTIFICAZIONE SULLE REGISTRAZIONI REALI
(`Betfair/mike/tools/replay_registrazioni.py`): otto ordini `ko_green` emessi
su un mercato `SUSPENDED`, su quattro partite diverse, sempre al fischio
d'inizio — che e' il momento in cui Betfair sospende. Nessuna review li aveva
visti; li ha visti il replay tick per tick coi prezzi veri.

Quattro correzioni, tutte autorizzate dall'utente:

  1. `_decide_ko_green` GUARDA il mercato. Prima non lo consultava affatto:
     `piano_uscita_ko` calcola il prezzo dal prezzo d'INGRESSO, quindi lo stato
     del mercato non lo vedeva nessuno.
  2. La finestra `ko_green_window_s` NON scorre a mercato non operabile. E' il
     danno economico: i 180 s correvano durante la sospensione e il bot
     rinunciava al green-up per un tempo in cui non poteva piazzare niente,
     ripiegando sulla copertura.
  3. L'ULTIMO INGRESSO non rinuncia per una sospensione. Prima qualunque stato
     diverso da OPEN mandava in `IDLE_LIVE` archiviando le gambe: il bot non
     riprovava piu'.
  4. `SUSPENDED`, `CLOSED` e l'IGNOTO si chiamano per nome, in un posto solo
     (`stato_mercato`/`operabile`/`riaprira`). Prima sei percorsi scrivevano
     `status != "OPEN"`, che li faceva tutti uguali.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import pytest

from Betfair.mike import engine as E
from test_mike_engine import KO, book, fill, params, snap


# ===========================================================================
# 1. I TRE STATI, CHIAMATI PER NOME
# ===========================================================================
@pytest.mark.parametrize("grezzo,atteso", [
    ("OPEN", E.STATO_APERTO),
    ("SUSPENDED", E.STATO_SOSPESO),
    ("CLOSED", E.STATO_CHIUSO),
    ("INACTIVE", E.STATO_CHIUSO),
    ("", E.STATO_IGNOTO),
    ("QUALCOSA_DI_NUOVO", E.STATO_IGNOTO),
])
def test_lo_stato_del_mercato_si_chiama_per_nome(grezzo, atteso):
    assert E.stato_mercato(book(1.50, status=grezzo)) == atteso


def test_senza_book_lo_stato_e_IGNOTO_non_chiuso():
    """Nessuna notizia non e' una cattiva notizia: e' nessuna notizia."""
    assert E.stato_mercato(None) == E.STATO_IGNOTO


def test_si_opera_SOLO_a_mercato_aperto():
    assert E.operabile(book(1.50, status="OPEN")) is True
    for st in ("SUSPENDED", "CLOSED", "INACTIVE", "", "BOH"):
        assert E.operabile(book(1.50, status=st)) is False, st
    assert E.operabile(None) is False


def test_si_ASPETTA_su_sospeso_e_su_ignoto_ma_non_su_chiuso():
    """Aspettare costa un ciclo; rinunciare per sbaglio costa un'uscita."""
    assert E.riaprira(book(1.50, status="SUSPENDED")) is True
    assert E.riaprira(book(1.50, status="BOH")) is True
    assert E.riaprira(None) is True
    assert E.riaprira(book(1.50, status="CLOSED")) is False
    assert E.riaprira(book(1.50, status="INACTIVE")) is False


# ===========================================================================
# 2. L'USCITA AL FISCHIO — il ramo che non guardava il mercato
# ===========================================================================
def _ctx_al_fischio(now=KO + 5.0):
    """Posizione Under aperta, appena entrati in gioco: e' lo stato in cui vive
    `ko_green`, ed e' quello in cui Betfair tiene il mercato sospeso."""
    ctx = E.MatchCtx(state="LIVE_KO_GREEN", live_since=now)
    gamba = E.Leg(ref="under_entry-0-1", role="under_entry", market=E.MARKET_OU35,
                  selection=E.SEL_UNDER, side="back", price=1.50, size=10.0)
    fill(gamba)
    ctx.legs.append(gamba)
    return ctx


def test_a_mercato_SOSPESO_non_parte_nessun_ordine_e_si_aspetta():
    """IL DIFETTO TROVATO SULLE REGISTRAZIONI: otto ordini veri emessi su un
    mercato sospeso, sempre al fischio d'inizio."""
    ctx = _ctx_al_fischio()
    d = E.decide(ctx, snap(KO + 10.0, u35=book(1.45, status="SUSPENDED"),
                           inplay=True, minute=1, goals=0), params())

    assert not [a for a in d.actions if a.kind == "place"], (
        "ha emesso un ordine su un mercato sospeso")
    assert d.state == "LIVE_KO_GREEN", "sospeso non e' chiuso: si aspetta la riapertura"
    assert "sospeso" in d.reason


def test_a_mercato_CHIUSO_l_uscita_al_fischio_NON_si_aspetta():
    """Chiuso e' chiuso: qui aspettare sarebbe fermarsi per sempre."""
    ctx = _ctx_al_fischio()
    d = E.decide(ctx, snap(KO + 10.0, u35=book(1.45, status="CLOSED"),
                           inplay=True, minute=1, goals=0), params())

    assert not [a for a in d.actions if a.kind == "place"]
    assert d.state != "LIVE_KO_GREEN"


def test_a_mercato_APERTO_l_uscita_parte_come_sempre():
    """La correzione non deve spegnere il comportamento normale."""
    ctx = _ctx_al_fischio()
    d = E.decide(ctx, snap(KO + 10.0, u35=book(1.45, status="OPEN"),
                           inplay=True, minute=1, goals=0), params())

    piazzati = [a for a in d.actions if a.kind == "place"]
    assert piazzati and piazzati[0].role == "ko_green"
    assert piazzati[0].side == "lay"


# ===========================================================================
# 3. LA FINESTRA NON SCORRE SE NON SI PUO' OPERARE — il danno economico
# ===========================================================================
def test_la_finestra_NON_scade_a_mercato_sospeso():
    """Rinunciare mentre non si poteva operare non e' una decisione: e' un caso.
    Prima i 180 s correvano durante la sospensione del fischio d'inizio e il
    bot ripiegava sulla copertura invece di uscire in green."""
    p = params()
    oltre = KO + float(p["ko_green_window_s"]) + 60.0
    ctx = _ctx_al_fischio(now=KO)

    scaduta = E.finestra_uscita_scaduta(
        ctx, snap(oltre, u35=book(1.45, status="SUSPENDED"), inplay=True), p)

    assert scaduta is False


def test_la_finestra_scade_regolarmente_a_mercato_aperto():
    p = params()
    oltre = KO + float(p["ko_green_window_s"]) + 60.0
    ctx = _ctx_al_fischio(now=KO)

    assert E.finestra_uscita_scaduta(
        ctx, snap(oltre, u35=book(1.45, status="OPEN"), inplay=True), p) is True


def test_dentro_la_finestra_non_scade_comunque():
    p = params()
    dentro = KO + float(p["ko_green_window_s"]) / 2.0
    ctx = _ctx_al_fischio(now=KO)

    assert E.finestra_uscita_scaduta(
        ctx, snap(dentro, u35=book(1.45, status="OPEN"), inplay=True), p) is False


# ===========================================================================
# 4. L'ULTIMO INGRESSO — una sospensione non e' una rinuncia
# ===========================================================================
def _dopo_il_green_finale():
    """Il ciclo pre-match si e' chiuso: si decide se fare l'ultimo ingresso."""
    return E.MatchCtx(state="PRE_GREEN_PENDING", cycle_no=2)


def test_ultimo_ingresso_su_mercato_SOSPESO_aspetta():
    """Prima andava in IDLE_LIVE archiviando le gambe: il bot non riprovava
    PIU'. A KO-10' una sospensione dura secondi, e l'ultimo ingresso e' l'unica
    gamba che porta la posizione in-play."""
    ctx = _dopo_il_green_finale()
    d = E._after_final_green(ctx, snap(KO - 300.0, u35=book(1.50, status="SUSPENDED")),
                             params(), book(1.50, status="SUSPENDED"), 10.0)

    assert d.state == ctx.state, "una sospensione non cambia lo stato"
    assert not d.updates, "non si archivia e non si incrementa il ciclo per una sospensione"
    assert "sospeso" in d.reason


def test_ultimo_ingresso_su_mercato_CHIUSO_chiude_la_partita():
    """Il comportamento di sempre, che resta giusto quando il mercato e' chiuso
    davvero."""
    ctx = _dopo_il_green_finale()
    d = E._after_final_green(ctx, snap(KO - 300.0, u35=book(1.50, status="CLOSED")),
                             params(), book(1.50, status="CLOSED"), 10.0)

    assert d.state == "IDLE_LIVE"
    assert d.updates.get("cycle_no") == ctx.cycle_no + 1


def test_ultimo_ingresso_senza_book_chiude_come_prima():
    ctx = _dopo_il_green_finale()
    d = E._after_final_green(ctx, snap(KO - 300.0), params(), None, 10.0)

    assert d.state == "IDLE_LIVE"


def test_ultimo_ingresso_a_mercato_aperto_piazza():
    ctx = _dopo_il_green_finale()
    bk = book(1.50, bs=1000.0, status="OPEN")
    d = E._after_final_green(ctx, snap(KO - 300.0, u35=bk), params(), bk, 10.0)

    piazzati = [a for a in d.actions if a.kind == "place"]
    assert piazzati and piazzati[0].role == "under_last"
    assert piazzati[0].persistence == "PERSIST", "l'ultimo ingresso deve restare in-play"
