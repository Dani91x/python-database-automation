"""UN PREZZO CONGELATO E' PEGGIO DI UN PREZZO ASSENTE (13/09/2026).

Quando un mercato esce dal feed — il tetto delle partite seguite morde, il pool
dello stream e' pieno, il poll REST salta un giro — il suo blocco ``ou`` NON
sparisce dal payload: resta in cache con l'ULTIMO prezzo ricevuto. E la riga
continua ad aggiornarsi lo stesso, perche' il minuto, il punteggio e l'1X2 si
muovono comunque.

Prima del 13/09 Mike non aveva nessun modo di accorgersene: giudicava la
freschezza sull'``updated_at`` della RIGA, che era giovane, e prezzava un book
morto. Comprava la copertura Over 4.5 credendo di essersi coperto, o usciva su un
prezzo che non esisteva piu'.

Dal 13/09 lo scanner marca ogni blocco con ``seen_ms`` — il momento dell'ultimo
BOOK RICEVUTO — distinto da ``ts_ms``, che e' l'ultimo CAMBIO DI PREZZO. Le due
domande hanno risposte opposte:

    ts_ms vecchio + seen_ms recente -> il prezzo non si muove ma lo guardiamo:
                                       E' il prezzo corrente, si opera.
    ts_ms vecchio + seen_ms vecchio -> non lo guarda piu' nessuno: e' un ricordo.

Qui si fissa il comportamento del secondo caso.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import feed as F

ORA = time.time()
KO = datetime.fromtimestamp(ORA + 3600, tz=timezone.utc)


def _blocco(line: float, *, seen_ms=None, back=1.50):
    blk = {
        "line": line,
        "market_id": "1.%d" % int(line * 10),
        "status": "OPEN",
        "selections": [
            {"selection_id": int(line * 10) + 1, "name": "Under %.1f Goals" % line,
             "back": back, "back_size": 500.0, "lay": back + 0.02, "lay_size": 500.0},
            {"selection_id": int(line * 10) + 2, "name": "Over %.1f Goals" % line,
             "back": 3.0, "back_size": 500.0, "lay": 3.05, "lay_size": 500.0},
        ],
    }
    if seen_ms is not None:
        blk["seen_ms"] = seen_ms
    return blk


def _riga(*, seen35=None, seen45=None, eta_riga_s=2.0):
    payload = {
        "event_name": "Tizio v Caio",
        "open_date": KO.isoformat(),
        "ou": [_blocco(3.5, seen_ms=seen35), _blocco(4.5, seen_ms=seen45, back=1.12)],
    }
    aggiornata = datetime.fromtimestamp(ORA - eta_riga_s, tz=timezone.utc)
    return {"event_id": "E1", "payload": payload, "updated_at": aggiornata.isoformat()}


def _snap(riga, params=None):
    p = params or C.merge_params(None)
    info = F.event_info("E1", riga["payload"])
    return F.snapshot_from_row(riga, info, now=ORA, params=p, scanner_age_s=3.0)


# ---------------------------------------------------------------------------
# la domanda di base
# ---------------------------------------------------------------------------
def test_blocco_visto_adesso_e_osservato():
    assert F.blocco_osservato({"seen_ms": ORA * 1000}, ORA, 90.0) is True


def test_blocco_visto_un_secolo_fa_non_e_osservato():
    assert F.blocco_osservato({"seen_ms": (ORA - 600) * 1000}, ORA, 90.0) is False


def test_scanner_vecchio_senza_seen_ms_non_fa_sparire_i_book():
    """Compatibilita': finche' il produttore non scrive ``seen_ms`` si tiene il
    comportamento di prima. Il rischio si chiude aggiornando lo scanner, non
    spegnendo il bot nel frattempo."""
    assert F.blocco_osservato({}, ORA, 90.0) is True
    assert F.blocco_osservato({"seen_ms": None}, ORA, 90.0) is True


def test_seen_ms_illeggibile_non_fa_sparire_i_book():
    assert F.blocco_osservato({"seen_ms": "boh"}, ORA, 90.0) is True


# ---------------------------------------------------------------------------
# l'effetto sullo snapshot: e' li' che si decide
# ---------------------------------------------------------------------------
def test_book_osservati_ci_sono_tutti():
    s = _snap(_riga(seen35=ORA * 1000, seen45=ORA * 1000))
    assert s is not None
    assert s.book(E.MARKET_OU35, E.SEL_UNDER) is not None
    assert s.book(E.MARKET_OU45, E.SEL_OVER) is not None


def test_la_linea_della_COPERTURA_non_piu_osservata_sparisce():
    """IL CASO CHE COSTA SOLDI: l'Under 3.5 e' vivo, ma l'Over 4.5 — la linea su
    cui si COMPRA LA COPERTURA — non la guarda piu' nessuno da dieci minuti. Il
    suo prezzo e' ancora nel payload e sembra ottimo. Deve sparire."""
    s = _snap(_riga(seen35=ORA * 1000, seen45=(ORA - 600) * 1000))
    assert s is not None
    assert s.book(E.MARKET_OU35, E.SEL_UNDER) is not None, "l'Under 3.5 e' vivo"
    assert s.book(E.MARKET_OU45, E.SEL_OVER) is None, "l'Over 4.5 e' morto: niente copertura su un fantasma"


def test_la_linea_di_INGRESSO_non_piu_osservata_sparisce():
    s = _snap(_riga(seen35=(ORA - 600) * 1000, seen45=ORA * 1000))
    assert s is not None
    assert s.book(E.MARKET_OU35, E.SEL_UNDER) is None


def test_la_riga_giovane_non_salva_un_book_morto():
    """E' esattamente il difetto del 13/09: la riga si aggiorna per il minuto e
    il punteggio, quindi ``updated_at`` e' giovane e ``feed_fresh`` dice True —
    ma la linea O/U dentro non la guarda piu' nessuno."""
    riga = _riga(seen35=(ORA - 600) * 1000, seen45=(ORA - 600) * 1000, eta_riga_s=1.0)
    s = _snap(riga)
    assert s is not None
    assert s.feed_fresh is True, "la riga e' giovane: il feed nel suo insieme e' fresco"
    assert s.book(E.MARKET_OU35, E.SEL_UNDER) is None, "ma il book dentro e' morto"
    assert s.book(E.MARKET_OU45, E.SEL_OVER) is None


def test_la_soglia_e_un_parametro():
    """Con una soglia larghissima lo stesso book torna utilizzabile: il
    comportamento e' governato dal parametro, non cablato."""
    riga = _riga(seen35=(ORA - 300) * 1000, seen45=(ORA - 300) * 1000)
    assert _snap(riga).book(E.MARKET_OU35, E.SEL_UNDER) is None
    largo = C.merge_params({"book_seen_max_s": 600})
    assert _snap(riga, largo).book(E.MARKET_OU35, E.SEL_UNDER) is not None


def test_event_info_NON_filtra_i_mercati_morti():
    """Money-critical al contrario: market_id e selection_id devono restare
    disponibili anche per un mercato che abbiamo smesso di guardare, altrimenti
    non potremmo nemmeno ANNULLARE un ordine ancora vivo li' sopra."""
    riga = _riga(seen35=(ORA - 600) * 1000, seen45=(ORA - 600) * 1000)
    info = F.event_info("E1", riga["payload"])
    assert info.market_id(E.MARKET_OU35) is not None
    assert info.selection_id(E.MARKET_OU35, E.SEL_UNDER) is not None


# ---------------------------------------------------------------------------
# e il bot, di conseguenza, non opera
# ---------------------------------------------------------------------------
def test_senza_il_book_di_ingresso_il_bot_non_entra():
    riga = _riga(seen35=(ORA - 600) * 1000, seen45=ORA * 1000)
    s = _snap(riga)
    d = E.decide(E.MatchCtx(), s, C.merge_params(None))
    assert not [a for a in d.actions if a.kind == "place"], \
        "nessun ordine su una linea che nessuno sta guardando"
