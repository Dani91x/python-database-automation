"""07/10 (decisione D3 = A dell'utente) - tennis_pro: il fade scatta SOLO «dopo un
break PRECOCE» del favorito, come dice la spec (docstring del bot, setup 2:
«back del favorito dopo un break PRECOCE che ne ha gonfiato la quota»).

Caso vero, registrazione 35790089 (Barrios Vera - Simakin, 07/07/2026), primi
game del terzo set: 0-0 -> 0-1 -> 1-1 -> 1-2, TUTTI game tenuti al servizio.
Il codice di prima entrava in fade 4 volte (2 col prezzo del book di P1)
perche' guardava solo il salto di prezzo dall'inizio del set: nessun break.

Il punteggio entra come in produzione: record IPS con le chiavi vere
(`score.home/away.{name, score, games, sets, isServing, serviceBreaks,
gameSequence}`) passati a `parse_tennis_scores`; il book ha gli attributi del
`MarketBook` di flumine (`ex.available_to_back` = lista di {price, size}).
NB: nel sidecar vero `serviceBreaks` vale 0 per tutta la partita anche dopo i
break del terzo set: non e' una fonte, il break si legge da chi serviva il game
e da chi lo ha vinto.
"""
from types import SimpleNamespace as NS

from betfairlightweight import filters

from Betfair.stream.tennis_scalper.tennis_pro_bot import TennisProStrategy
from Betfair.stream.tennis_scalper.tennis_score import parse_tennis_scores

MID = "1.259745327"
BAR, SIM = 9633138, 35635727


class _Blotter:
    def strategy_orders(self, _s):
        return []


class _Mercato:
    market_id = MID
    blotter = _Blotter()

    def place_order(self, _o):
        return True

    def cancel_order(self, _o):
        return True


def _ips(sets, games, punti, serve_casa, seq=("6", "5"), seq_a=("4", "7")):
    """Un record IPS con le chiavi del sidecar vero (home = Barrios)."""
    def lato(i, nome, serve, sq):
        return {"name": nome, "score": punti[i], "games": str(games[i]),
                "sets": str(sets[i]), "isServing": serve, "highlight": serve,
                "serviceBreaks": 0, "gameSequence": list(sq)}
    return {"eventTypeId": 2, "eventId": 35790089,
            "score": {"home": lato(0, "Marcelo Tomas Barrios V", serve_casa, seq),
                      "away": lato(1, "Ilia Simakin", not serve_casa, seq_a)},
            "currentSet": sets[0] + sets[1] + 1}


def _runner(sel, bb, bl, ltp):
    return NS(selection_id=sel, status="ACTIVE", last_price_traded=ltp,
              ex=NS(available_to_back=[{"price": bb, "size": 100.0}],
                    available_to_lay=[{"price": bl, "size": 100.0}]))


def _book(pt, bar, sim):
    return NS(market_id=MID, status="OPEN", inplay=True, total_matched=7454.92,
              publish_time_epoch=pt, runners=[_runner(BAR, *bar), _runner(SIM, *sim)])


def _bot():
    # SOLO il fade acceso: gli altri setup hanno la precedenza e sporcherebbero
    # la misura; cancello di liquidita' aperto (Challenger poco liquido)
    return TennisProStrategy(
        market_filter=filters.streaming_market_filter(market_ids=[MID]),
        pro_params={"stake": 2.0, "dry_run": True, "min_matched": 0.0,
                    "enable_break_point": False, "enable_set_transition": False,
                    "enable_serving_set": False, "enable_double_break": False,
                    "enable_compressed_fav": False},
        name_to_sel={"Marcelo Tomas Barrios V": BAR, "Ilia Simakin": SIM})


def _gira(s, passi):
    """Ogni passo: (ora ms, record IPS, prezzi Barrios, prezzi Simakin). Ritorna i
    setup aperti; un trade aperto si dimentica subito (si misura ogni game da solo)."""
    entrate = []
    s.event_sink = lambda ev, p: entrate.append(p.get("kind")) if ev == "entry" else None
    for pt, rec, bar, sim in passi:
        s.score = parse_tennis_scores([rec], 35790089)
        s.process_market_book(_Mercato(), _book(pt, bar, sim))
        s._trade.pop(MID, None)
    return entrate


def test_caso_vero_35790089_nessun_fade_senza_break():
    # prezzi del book registrato (bb, bl, ltp) agli istanti degli ingressi di prima
    passi = [
        (1783427743000, _ips((1, 0), (5, 6), ("15", "40"), True), (1.43, 1.48, 1.4), (3.1, 3.3, 3.3)),
        (1783427752000, _ips((1, 1), (0, 0), ("0", "0"), False), (1.51, 1.57, 1.4), (2.74, 2.96, 3.3)),
        (1783428524000, _ips((1, 1), (0, 1), ("0", "0"), True), (1.76, 1.85, 1.51), (2.16, 2.32, 2.28)),
        (1783428781000, _ips((1, 1), (1, 1), ("0", "0"), False), (1.55, 1.61, 1.69), (2.66, 2.84, 2.66)),
        (1783429067000, _ips((1, 1), (1, 2), ("0", "0"), True), (1.74, 1.82, 1.4), (2.22, 2.38, 2.38)),
    ]
    assert _gira(_bot(), passi) == []


def _set_con_break(chi_serve_il_secondo_game_e_lo_perde_casa: bool):
    # inizio del set 2 sul 1-0 di Barrios (favorito): 0-0, poi 1-0 tenuto da
    # Barrios, poi il game di chi serve dopo; la quota di Barrios sale di 10+ tick
    s0 = (1, 0)
    return [
        (1_000_000, _ips(s0, (0, 0), ("0", "0"), True), (1.30, 1.31, 1.30), (4.2, 4.3, 4.2)),
        (1_060_000, _ips(s0, (1, 0), ("0", "0"), False), (1.30, 1.31, 1.30), (4.2, 4.3, 4.2)),
        # game 2: serve Simakin. Se Barrios lo PERDE e' tenuto da Simakin (1-1)
        (1_120_000, _ips(s0, (1, 1), ("0", "0"), True), (1.40, 1.42, 1.40), (3.3, 3.4, 3.3)),
        # game 3: serve Barrios; lo perde (1-2) = BREAK del favorito
        (1_180_000, _ips(s0, (1, 2), ("0", "0"), False), (1.44, 1.45, 1.44), (3.2, 3.3, 3.2)),
    ][: 4 if chi_serve_il_secondo_game_e_lo_perde_casa else 3]


def test_break_precoce_del_favorito_fa_scattare_il_fade():
    assert _gira(_bot(), _set_con_break(True)) == ["fade"]


def test_salto_senza_break_non_fa_scattare_il_fade():
    # stesso salto di prezzo, ma 1-1 e' un game TENUTO da Simakin
    assert _gira(_bot(), _set_con_break(False)) == []


def test_break_del_non_favorito_non_conta():
    # Simakin serve il game 2 e lo perde (2-0 Barrios): break, ma NON del favorito
    s0 = (1, 0)
    passi = [
        (1_000_000, _ips(s0, (0, 0), ("0", "0"), True), (1.30, 1.31, 1.30), (4.2, 4.3, 4.2)),
        (1_060_000, _ips(s0, (1, 0), ("0", "0"), False), (1.30, 1.31, 1.30), (4.2, 4.3, 4.2)),
        (1_120_000, _ips(s0, (2, 0), ("0", "0"), True), (1.44, 1.45, 1.44), (3.2, 3.3, 3.2)),
    ]
    assert _gira(_bot(), passi) == []


def test_due_game_fra_due_campioni_non_si_attribuiscono():
    # da 1-0 a 1-2 senza vedere l'1-1: chi ha servito il game perso non si sa
    s0 = (1, 0)
    passi = [
        (1_000_000, _ips(s0, (0, 0), ("0", "0"), True), (1.30, 1.31, 1.30), (4.2, 4.3, 4.2)),
        (1_060_000, _ips(s0, (1, 0), ("0", "0"), False), (1.30, 1.31, 1.30), (4.2, 4.3, 4.2)),
        (1_180_000, _ips(s0, (1, 2), ("0", "0"), False), (1.44, 1.45, 1.44), (3.2, 3.3, 3.2)),
    ]
    assert _gira(_bot(), passi) == []


def test_senza_nomi_il_break_non_si_attribuisce():
    s = TennisProStrategy(
        market_filter=filters.streaming_market_filter(market_ids=[MID]),
        pro_params={"stake": 2.0, "dry_run": True, "min_matched": 0.0,
                    "enable_break_point": False, "enable_set_transition": False,
                    "enable_serving_set": False, "enable_double_break": False,
                    "enable_compressed_fav": False},
        name_to_sel={})
    assert _gira(s, _set_con_break(True)) == []
