"""08/10/2026 - CANTIERE 6: banco tennis, nomi dei giocatori e scenario `gate-aperto`.

(a) `certifica` passa al banco tennis il `_names.json` della cartella della
    partita (la stessa di `applica_bot.risolvi_cartella_tennis`); se il file
    manca o non ha la partita la TESTA del referto lo dice e i controlli che
    dipendono dai nomi escono NE (non esercitabili) con la causa.
(b) `gate-aperto`: contratto sui parametri che cambia (lista bianca =
    `parametri_modificabili` del bot + le soglie fuori catalogo DICHIARATE), e
    nessun altro scenario ha un insieme suo.
(c) Famiglia SP (setup di tennis_pro coi nomi): il metro del banco
    (`LettoreSetupPro`) e i controlli SP1 fade / SP2 set transition / SP3 break
    point, provati con la CLASSE DI PRODUZIONE del bot, i record IPS con le
    chiavi vere (`parse_tennis_scores`) e il book con gli attributi del
    `MarketBook` di flumine.

`_names.json`: la forma vera (grid runner e registratore del cantiere 14):
chiave piatta `{event_id: {selection_id: nome}}` del Match Odds + la chiave
RISERVATA `"_mercati"` `{event_id: {market_id: {selection_id: nome}}}`.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest
from betfairlightweight import filters

from Betfair.stream.backtest import certifica as C
from Betfair.stream.backtest import registro_bot as REG
from Betfair.stream.tennis_live import certificazione_bot as CERT
from Betfair.stream.tennis_live.tools import replay_bot as RB
from Betfair.stream.tennis_scalper.tennis_pro_bot import TennisProStrategy
from Betfair.stream.tennis_scalper.tennis_score import parse_tennis_scores

MID = "1.259745327"
BAR, SIM = 9633138, 35635727
NOMI = {"Marcelo Tomas Barrios V": BAR, "Ilia Simakin": SIM}
BOT_TENNIS = ("tennis_scalper", "tennis_pro", "tennis_flb", "tennis_swing")


# ---------------------------------------------------------------------------
# finti con le chiavi vere
# ---------------------------------------------------------------------------
def _riga_md(market_id: str, market_type: str, pt: int) -> str:
    # forma di una riga del recorder (mcm del flusso Betfair)
    return json.dumps({
        "op": "mcm", "clk": "AAA", "pt": pt,
        "mc": [{"id": market_id, "marketDefinition": {
            "bspMarket": False, "turnInPlayEnabled": True, "persistenceEnabled": True,
            "marketBaseRate": 5.0, "eventId": "x", "eventTypeId": "2",
            "numberOfWinners": 1, "bettingType": "ODDS", "marketType": market_type,
            "betDelay": 0, "status": "OPEN", "inPlay": False, "version": 1,
            "runners": [{"status": "ACTIVE", "sortPriority": 1, "id": BAR},
                        {"status": "ACTIVE", "sortPriority": 2, "id": SIM}]},
            "rc": [{"atb": [[1.5, 10.0]], "id": BAR}]}]})


def _partita(cartella, ev: str, market_id: str = MID) -> None:
    d = cartella / ev
    d.mkdir(parents=True, exist_ok=True)
    (d / ("%s.raw.jsonl" % ev)).write_text(_riga_md(market_id, "MATCH_ODDS", 1751900000000)
                                           + "\n", encoding="utf-8")
    (d / ("%s.score.jsonl" % ev)).write_text("", encoding="utf-8")


def _nomi_json(cartella, contenuto) -> None:
    (cartella / "_names.json").write_text(json.dumps(contenuto), encoding="utf-8")


def _ips(sets, games, punti, serve_casa, casa="Marcelo Tomas Barrios V",
         fuori="Ilia Simakin"):
    """Un record IPS con le chiavi del sidecar vero (`tennis_score.py`)."""
    def lato(i, nome, serve):
        return {"name": nome, "score": punti[i], "games": str(games[i]),
                "sets": str(sets[i]), "isServing": serve, "highlight": serve,
                "serviceBreaks": 0, "gameSequence": []}
    return {"eventTypeId": 2, "eventId": 35790089,
            "score": {"home": lato(0, casa, serve_casa), "away": lato(1, fuori, not serve_casa)},
            "currentSet": sets[0] + sets[1] + 1}


def _runner(sel, bb, bl, ltp):
    return NS(selection_id=sel, status="ACTIVE", last_price_traded=ltp,
              ex=NS(available_to_back=[{"price": bb, "size": 100.0}],
                    available_to_lay=[{"price": bl, "size": 100.0}]))


def _book(pt, bar, sim, inplay=True):
    return NS(market_id=MID, status="OPEN", inplay=inplay, total_matched=70000.0,
              publish_time_epoch=pt, runners=[_runner(BAR, *bar), _runner(SIM, *sim)])


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


_TUTTI_SPENTI = {"enable_break_point": False, "enable_fade": False,
                 "enable_set_transition": False, "enable_serving_set": False,
                 "enable_double_break": False, "enable_compressed_fav": False}


def _bot(solo: str, nomi=NOMI, **extra):
    """Il bot di PRODUZIONE con UN solo setup acceso (per misurarlo da solo),
    direzione fissa (trend, senza regime adattivo) e cancello di liquidita'
    aperto. Sono parametri del TEST, non del banco."""
    acceso = {"serving_for_set": "enable_serving_set"}.get(solo, "enable_%s" % solo)
    p = {"stake": 2.0, "dry_run": True, "min_matched": 0.0, "adapt": False,
         "trend": True, **_TUTTI_SPENTI, acceso: True}
    p.update(extra)
    return TennisProStrategy(market_filter=filters.streaming_market_filter(market_ids=[MID]),
                             pro_params=p, name_to_sel=dict(nomi))


def _gira(s, passi, lettore=None, mutazione=None):
    """Ogni passo: (ora ms, record IPS, prezzi Barrios, prezzi Simakin). Il bot
    e' quello vero; il banco legge lo STESSO campione col suo metro e giudica le
    entrate coi controlli SP. Ritorna (kind delle entrate, violazioni SP)."""
    entrate, violazioni = [], []
    for pt, rec, bar, sim in passi:
        giro = []
        s.event_sink = lambda ev, p: giro.append((ev, dict(p)))
        ts = parse_tennis_scores([rec], 35790089)
        s.score = ts
        book = _book(pt, bar, sim)
        if lettore is not None:
            lettore.campione(ts, book, s)
        s.process_market_book(_Mercato(), book)
        att = [(k, p) for k, p in giro]
        if mutazione is not None:
            att = mutazione(att)
        entrate += [p.get("kind") for k, p in att if k == "entry"]
        if lettore is not None:
            oss = CERT.Osservazione(bot="tennis_pro", attivita=att,
                                    setup_pro=lettore.stato(s, book))
            sol = {}
            violazioni += [v for v in CERT.verifica(oss, sol) if v.codice.startswith("SP")]
        s._trade.pop(MID, None)
    return entrate, violazioni


# --- le sequenze (prezzi del book in banda, punteggi coi campi IPS veri) ---
_BP = [(1_000_000, _ips((0, 0), (2, 1), ("15", "40"), True), (1.50, 1.52, 1.5), (2.8, 2.9, 2.8))]
_FADE = [
    (1_000_000, _ips((1, 0), (0, 0), ("0", "0"), True), (1.30, 1.31, 1.30), (4.2, 4.3, 4.2)),
    (1_060_000, _ips((1, 0), (1, 0), ("0", "0"), False), (1.30, 1.31, 1.30), (4.2, 4.3, 4.2)),
    (1_120_000, _ips((1, 0), (1, 1), ("0", "0"), True), (1.40, 1.42, 1.40), (3.3, 3.4, 3.3)),
    # Barrios (favorito) serve il game 3 e lo perde: BREAK del favorito
    (1_180_000, _ips((1, 0), (1, 2), ("0", "0"), False), (1.44, 1.45, 1.44), (3.2, 3.3, 3.2)),
]
_SET = [
    (1_000_000, _ips((0, 0), (5, 4), ("40", "0"), True), (1.50, 1.52, 1.5), (2.8, 2.9, 2.8)),
    # Barrios vince il set
    (1_060_000, _ips((1, 0), (0, 0), ("0", "0"), False), (1.40, 1.42, 1.4), (3.0, 3.1, 3.0)),
]
_SFS = [(1_000_000, _ips((0, 0), (5, 3), ("0", "0"), True), (1.50, 1.52, 1.5), (2.8, 2.9, 2.8))]
_DB = [(1_000_000, _ips((0, 0), (4, 1), ("0", "0"), True), (1.50, 1.52, 1.5), (2.8, 2.9, 2.8))]
_CF = [(1_000_000, _ips((0, 0), (1, 1), ("0", "0"), True), (1.15, 1.16, 1.15), (7.0, 7.4, 7.0))]
_SEQUENZE = {"break_point": _BP, "fade": _FADE, "set_transition": _SET,
             "serving_for_set": _SFS, "double_break": _DB}


# ===========================================================================
# (a) i nomi del `_names.json`
# ===========================================================================
def test_nomi_forma_piatta_letta(tmp_path):
    _nomi_json(tmp_path, {"35794049": {str(BAR): "Jannik Sinner", str(SIM): "Jan-Lennard Struff"}})
    assert RB.catalogo_dichiarato(str(tmp_path), "35794049") == {
        "Jannik Sinner": BAR, "Jan-Lennard Struff": SIM}


def test_nomi_chiave_riservata_mercati_ignorata_e_niente_crash(tmp_path):
    # forma del cantiere 14: piatta + "_mercati" (non e' un event_id)
    _nomi_json(tmp_path, {
        "35794049": {str(BAR): "Jannik Sinner", str(SIM): "Jan-Lennard Struff"},
        "_mercati": {"35794049": {MID: {str(BAR): "Jannik Sinner", str(SIM): "Jan-Lennard Struff"},
                                  "1.999": {"7": "Set 1 Sinner"}}}})
    assert RB.catalogo_dichiarato(str(tmp_path), "35794049", market_id=MID) == {
        "Jannik Sinner": BAR, "Jan-Lennard Struff": SIM}
    # nessun event_id "_mercati": nessun nome, nessuna eccezione
    assert RB.catalogo_dichiarato(str(tmp_path), "_mercati") == {}


def test_nomi_dal_mercato_del_bot_se_manca_la_chiave_piatta(tmp_path):
    _nomi_json(tmp_path, {"_mercati": {"35790089": {
        MID: {str(BAR): "Marcelo Tomas Barrios Vera", str(SIM): "Ilia Simakin"},
        "1.999": {"7": "Altro mercato"}}}})
    assert RB.catalogo_dichiarato(str(tmp_path), "35790089", market_id=MID) == {
        "Marcelo Tomas Barrios Vera": BAR, "Ilia Simakin": SIM}
    # mai un altro mercato, mai senza sapere quale
    assert RB.catalogo_dichiarato(str(tmp_path), "35790089", market_id="1.888") == {}
    assert RB.catalogo_dichiarato(str(tmp_path), "35790089") == {}


def test_stato_nomi_dice_presenti_e_assenti_con_la_causa(tmp_path):
    _partita(tmp_path, "35794049")
    _partita(tmp_path, "35790089")
    _nomi_json(tmp_path, {"35794049": {str(BAR): "Sinner", str(SIM): "Struff"}})
    si = RB.stato_nomi(str(tmp_path), "35794049")
    no = RB.stato_nomi(str(tmp_path), "35790089")
    assert si["presenti"] and si["nomi"] == ["Sinner", "Struff"] and not si["causa"]
    assert not no["presenti"] and "non ha la partita 35790089" in no["causa"]
    assert "assente" in RB.stato_nomi(str(tmp_path / "vuota"), "1")["causa"]


def test_intestazione_tennis_pro_nomi_e_parametri(tmp_path):
    _partita(tmp_path, "35794049")
    _partita(tmp_path, "35790089")
    _nomi_json(tmp_path, {"35794049": {str(BAR): "Sinner", str(SIM): "Struff"}})
    righe = RB.intestazione_certifica(
        "tennis_pro", {"35794049": str(tmp_path), "35790089": str(tmp_path)},
        ["base", "gate-aperto", "live", "parziali", "pro-fade-dopo-break"])
    testo = "\n".join(righe)
    assert "nomi dei giocatori 35794049: PRESENTI (Sinner, Struff)" in testo
    assert "nomi dei giocatori 35790089: ASSENTI" in testo
    assert "NON ESERCITABILI" in testo and "fade" in testo and "SP1, SP2, SP3" in testo
    assert "  base: nessuno (parametri di produzione)" in righe
    assert "  pro-fade-dopo-break: nessuno (parametri di produzione)" in righe
    # 08/10 sera (D-4): min_book_size e price_min sono nella scheda; fuori
    # resta solo la chiave che il pro non legge
    assert any(r.startswith("  gate-aperto: min_book_size=0.0") and
               r.endswith("FUORI dal catalogo della UI (dichiarati): "
                          "min_total_matched") for r in righe)
    assert any(r.startswith("  live: gli stessi di gate-aperto") for r in righe)
    assert "  parziali: stake=400.0" in righe


def test_intestazione_bot_senza_nomi(tmp_path):
    righe = RB.intestazione_certifica("tennis_flb", {"1": str(tmp_path)}, ["base"])
    assert righe[0].startswith("nomi dei giocatori: non usati da tennis_flb")


# ===========================================================================
# (b) gate-aperto: il contratto dei parametri
# ===========================================================================
_MAI = ("stake", "dry_run", "size_step", "live_min_bet", "exact_exits",
        "uscite_automatiche", "max_selection_exposure")


@pytest.mark.parametrize("bot", BOT_TENNIS)
def test_gate_aperto_solo_lista_bianca_o_dichiarati(bot):
    catalogo = {v["chiave"] for v in RB.parametri_modificabili("gate-aperto", bot)}
    cambiati = set(RB.parametri_scenario("gate-aperto", bot))
    dichiarati = set(RB.SOGLIE_FUORI_CATALOGO[bot])
    fuori = cambiati - catalogo
    # nessuna chiave fuori dalla lista bianca che non sia dichiarata
    assert fuori <= dichiarati, "gate-aperto cambia %s: ne' catalogo ne' dichiarati" % (
        sorted(fuori - dichiarati))
    # nessuna dichiarazione vecchia (chiave tolta o entrata nel catalogo)
    assert dichiarati == fuori, "dichiarazioni da aggiornare: %s" % sorted(dichiarati ^ fuori)
    # mai importi, sicurezza o blindature, mai l'accensione di un setup
    assert not [k for k in cambiati if k in _MAI or k.startswith("enable_")]


@pytest.mark.parametrize("bot", BOT_TENNIS)
def test_gate_aperto_dichiarazioni_vere_sull_istanza(bot):
    """Le cause dichiarate dicono il vero sull'istanza costruita da
    `_instantiate_bot`: `_NON_LETTA` = nessun attributo; le altre = attributo che
    c'e' (e che lo scenario cambia, salvo il 'gia' 0' dichiarato)."""
    base = RB._bot_dello_scenario(bot, "base")
    aperto = RB._bot_dello_scenario(bot, "gate-aperto")
    for k, causa in RB.SOGLIE_FUORI_CATALOGO[bot].items():
        if causa == RB._NON_LETTA:
            assert not hasattr(base, k), (bot, k)
        else:
            assert hasattr(base, k), (bot, k)
            if "gia' 0" not in causa:
                assert getattr(base, k) != getattr(aperto, k), (bot, k)


@pytest.mark.parametrize("bot", BOT_TENNIS)
def test_gate_aperto_e_l_unico_insieme_di_parametri(bot):
    """Ogni scenario o non cambia niente, o cambia SOLO lo stake (parziali), o
    porta ESATTAMENTE i gate di `gate-aperto` (la testa del referto lo scrive:
    "gli stessi di gate-aperto")."""
    gate = RB.parametri_scenario("gate-aperto", bot)
    for sc, descr in RB.scenari_del_bot(bot).items():
        p = RB.parametri_scenario(sc, bot)
        if not p or sc == "gate-aperto":
            continue
        if set(p) == {"stake"}:
            continue
        assert p == gate, (bot, sc, p)
        assert RB.descrivi_parametri_scenario(sc, bot).startswith(
            "gli stessi di gate-aperto"), (bot, sc, descr[:40])


def test_scenari_dei_setup_solo_del_pro_e_senza_parametri():
    assert set(RB.SCENARI_SETUP_PRO) == set(RB.CONTROLLO_DEL_SETUP)
    assert set(RB.CONTROLLO_DEL_SETUP.values()) == set(CERT.SETUP_CERTIFICATI)
    assert set(REG.bot("tennis_pro").elenco_scenari()) == set(RB.SCENARI_DESCRITTI_PRO)
    for b in ("tennis_scalper", "tennis_flb", "tennis_swing"):
        assert not set(RB.SCENARI_SETUP_PRO) & set(REG.bot(b).elenco_scenari())
    for sc in RB.SCENARI_SETUP_PRO:
        assert RB.parametri_scenario(sc, "tennis_pro") == {}
        assert RB.stake_scenario(sc, 2.0) == 2.0 and RB.modalita_scenario(sc) == "PAPER"


# ===========================================================================
# (c) i setup coi nomi, sulla classe di produzione
# ===========================================================================
@pytest.mark.parametrize("setup", CERT.SETUP_CON_NOMI)
def test_setup_con_nomi_scatta_solo_coi_nomi(setup):
    con, _ = _gira(_bot(setup), _SEQUENZE[setup])
    senza, _ = _gira(_bot(setup, nomi={}), _SEQUENZE[setup])
    assert con == [setup] and senza == [], (setup, con, senza)


def test_compressed_fav_non_dipende_dai_nomi():
    assert "compressed_fav" not in CERT.SETUP_CON_NOMI
    senza, _ = _gira(_bot("compressed_fav", nomi={}), _CF)
    assert senza == ["compressed_fav"]


@pytest.mark.parametrize("setup,codice", [("fade", "SP1"), ("set_transition", "SP2"),
                                          ("break_point", "SP3")])
def test_bot_vero_conforme_controllo_sollecitato_e_verde(setup, codice):
    lettore = CERT.LettoreSetupPro(NOMI)
    entrate, viol = _gira(_bot(setup), _SEQUENZE[setup], lettore)
    assert entrate == [setup] and viol == []
    # il metro ha visto l'occasione
    assert lettore.occasioni[codice] >= 1


def test_break_point_superficie_hard_su_chi_riceve():
    lettore = CERT.LettoreSetupPro(NOMI)
    entrate, viol = _gira(_bot("break_point", surface="hard"), _BP, lettore)
    assert entrate == ["break_point"] and viol == []


def _cambia_sel(att):
    return [(k, dict(p, sel=SIM if p.get("sel") == BAR else BAR)) if k == "entry" else (k, p)
            for k, p in att]


@pytest.mark.parametrize("setup", ["fade", "set_transition", "break_point"])
def test_entrata_sul_giocatore_sbagliato_e_rossa(setup):
    lettore = CERT.LettoreSetupPro(NOMI)
    _e, viol = _gira(_bot(setup), _SEQUENZE[setup], lettore, mutazione=_cambia_sel)
    assert [v.codice for v in viol] == [{"fade": "SP1", "set_transition": "SP2",
                                         "break_point": "SP3"}[setup]]


def _oss(kind, sel, s, lettore, book, side="BACK"):
    st = lettore.stato(NS(score=s, surface="grass", fade_max_game=3, st_window_games=2), book)
    return CERT.Osservazione(bot="tennis_pro", setup_pro=st, stato_mercato="OPEN",
                             attivita=[("entry", {"kind": kind, "sel": sel, "side": side})])


def _sp(violazioni):
    return [v for v in violazioni if v.codice.startswith("SP")]


def test_sp1_fade_senza_break_rosso():
    lettore = CERT.LettoreSetupPro(NOMI)
    book = _book(1, (1.40, 1.42, 1.4), (3.3, 3.4, 3.3))
    strat = NS(fade_max_game=3)
    for rec in (_ips((1, 0), (0, 0), ("0", "0"), True), _ips((1, 0), (1, 0), ("0", "0"), False)):
        lettore.campione(parse_tennis_scores([rec], 1), book, strat)
    s = parse_tennis_scores([_ips((1, 0), (1, 0), ("0", "0"), False)], 1)
    v = _sp(CERT.verifica(_oss("fade", BAR, s, lettore, book), {}))
    assert [x.codice for x in v] == ["SP1"] and "nessun break" in v[0].dettaglio


def test_sp1_fade_fuori_dai_primi_game_rosso():
    lettore = CERT.LettoreSetupPro(NOMI)
    book = _book(1, (1.40, 1.42, 1.4), (3.3, 3.4, 3.3))
    s = parse_tennis_scores([_ips((1, 0), (3, 2), ("0", "0"), False)], 1)
    v = _sp(CERT.verifica(_oss("fade", BAR, s, lettore, book), {}))
    assert [x.codice for x in v] == ["SP1"] and "game giocati" in v[0].dettaglio


def test_sp2_fuori_finestra_rosso():
    lettore = CERT.LettoreSetupPro(NOMI)
    book = _book(1, (1.40, 1.42, 1.4), (3.3, 3.4, 3.3))
    strat = NS(fade_max_game=3)
    lettore.campione(parse_tennis_scores([_ips((0, 0), (5, 4), ("40", "0"), True)], 1), book, strat)
    lettore.campione(parse_tennis_scores([_ips((1, 0), (0, 0), ("0", "0"), False)], 1), book, strat)
    s = parse_tennis_scores([_ips((1, 0), (2, 1), ("0", "0"), False)], 1)
    v = _sp(CERT.verifica(_oss("set_transition", BAR, s, lettore, book), {}))
    assert [x.codice for x in v] == ["SP2"] and "fuori finestra" in v[0].dettaglio


@pytest.mark.parametrize("punti", [("30", "40"), ("1", "3"), ("0", "3")])
def test_sp3_non_break_point_rosso(punti):
    """30-40 e il tie-break (punti numerici) non sono il break point della spec
    del setup 1 (0-40 / 15-40)."""
    lettore = CERT.LettoreSetupPro(NOMI)
    book = _book(1, (1.40, 1.42, 1.4), (3.3, 3.4, 3.3))
    s = parse_tennis_scores([_ips((0, 0), (6, 6), punti, True)], 1)
    v = _sp(CERT.verifica(_oss("break_point", BAR, s, lettore, book), {}))
    assert [x.codice for x in v] == ["SP3"]


def test_sp_non_gira_senza_lettura_del_banco():
    """Gli altri bot e il giro di settlement (setup_pro None): famiglia SP spenta,
    nessun conteggio in piu' (i loro referti non cambiano)."""
    sol = {}
    oss = CERT.Osservazione(bot="tennis_pro", attivita=[("entry", {"kind": "fade", "sel": BAR})])
    assert not [v for v in CERT.verifica(oss, sol) if v.codice.startswith("SP")]
    assert not [c for c in sol if c.startswith("SP")]
    assert CERT.famiglie_del_bot("tennis_flb") == []
    assert [c for c, _ in CERT.famiglie_del_bot("tennis_pro")[0][1]] == ["SP1", "SP2", "SP3"]
    assert not [c for c, _ in CERT.elenco_controlli() if c.startswith("SP")]


def test_selezione_del_nome_regole():
    cat = {"Sinner": 1, "Struff": 2}
    assert CERT.selezione_del_nome("Jannik Sinner", cat) == 1
    assert CERT.selezione_del_nome("Jan-Lennard Struff", cat) == 2
    assert CERT.selezione_del_nome("Marcelo Tomas Barrios V",
                                   {"Marcelo Tomas Barrios Vera": 7, "Ilia Simakin": 8}) == 7
    # cognome condiviso = ambiguo = nessuno
    assert CERT.selezione_del_nome("Venus Williams", {"S Williams": 1, "V Williams": 2}) is None
    assert CERT.selezione_del_nome("Chiunque", {}) is None


# ===========================================================================
# fine replay: NON ESERCITABILE / NON ESERCITATO
# ===========================================================================
def test_chiudi_setup_pro_senza_nomi():
    ref = CERT.Referto(event_id="35790089")
    RB.chiudi_setup_pro(ref, "pro-fade-dopo-break", CERT.LettoreSetupPro({}))
    assert sorted(ref.non_esercitabili) == ["SP1", "SP2", "SP3"]
    assert "nomi dei giocatori ASSENTI" in ref.non_esercitabili["SP1"]
    assert len(ref.non_esercitato) == 1 and ref.non_esercitato[0].startswith("SP1")
    assert any(n.startswith("LETTURA DEL BANCO") for n in ref.note)


def test_chiudi_setup_pro_zero_occasioni_misurate_e_occasioni_senza_ingresso():
    lettore = CERT.LettoreSetupPro(NOMI)
    lettore.campioni = 50
    lettore.occasioni["SP3"] = 4
    ref = CERT.Referto(event_id="35794049", sollecitati={"SP2": 3})
    RB.chiudi_setup_pro(ref, "pro-break-point", lettore)
    # SP1 zero occasioni: non esercitabile, misurato; SP2 sollecitato; SP3 occasioni
    # senza ingresso: NON e' non esercitabile (resta "non lo so"), lo scenario e' NE
    assert sorted(ref.non_esercitabili) == ["SP1"]
    assert "misurato sulla registrazione" in ref.non_esercitabili["SP1"]
    assert ref.non_esercitato and "4 occasioni" in ref.non_esercitato[0]
    # uno scenario NON di setup non diventa mai NE (i referti di prima restano OK)
    altro = CERT.Referto(event_id="x")
    RB.chiudi_setup_pro(altro, "base", CERT.LettoreSetupPro({}))
    assert altro.non_esercitato == [] and len(altro.non_esercitabili) == 3
    assert altro.note == []


# ===========================================================================
# certifica: cartella della partita, testa del referto, copertura NE
# ===========================================================================
def _fake_esegui(referti_per, visti):
    def _fake(compiti, processi, picchi):  # noqa: ARG001 - stessa firma del vero
        for c in compiti:
            visti.append(c)
            yield referti_per(c)
    return _fake


def _referto(ev, nomi_assenti=True, sollecitati=None):
    r = CERT.Referto(event_id=ev, bot="tennis_pro", decisioni=5, tick=5,
                     sollecitati=dict(sollecitati or {}))
    if nomi_assenti:
        RB.chiudi_setup_pro(r, "base", CERT.LettoreSetupPro({}))
    return r


def test_certifica_testa_e_copertura_ne_senza_nomi(tmp_path, monkeypatch, capsys):
    giorno = tmp_path / "20260707"
    _partita(giorno, "35790089")
    _nomi_json(giorno, {"35794049": {str(BAR): "Sinner", str(SIM): "Struff"}})
    visti = []
    monkeypatch.setattr(C, "_esegui_compiti",
                        _fake_esegui(lambda c: _referto(c[1]), visti))
    C.main(["tennis_pro", "35790089", "--data-dir", str(giorno), "--scenari",
            "base,pro-fade-dopo-break"])
    out = capsys.readouterr().out
    assert [c[2] for c in visti] == [str(giorno), str(giorno)]
    assert "nomi dei giocatori 35790089: ASSENTI" in out
    assert "  pro-fade-dopo-break: nessuno (parametri di produzione)" in out
    assert "  -- controlli dei setup di tennis_pro" in out
    assert "  NE SP1 x0" in out and "NE NON ESERCITABILI" in out
    mai = out.split("MAI SOLLECITATI")[-1] if "MAI SOLLECITATI" in out else ""
    assert "SP1:" not in mai


def test_certifica_un_referto_che_non_dichiara_lascia_non_lo_so(tmp_path, monkeypatch, capsys):
    giorno = tmp_path / "20260707"
    _partita(giorno, "35790089")
    referti = iter([_referto("35790089"), _referto("35790089", nomi_assenti=False)])
    monkeypatch.setattr(C, "_esegui_compiti", _fake_esegui(lambda c: next(referti), []))
    C.main(["tennis_pro", "35790089", "--data-dir", str(giorno), "--scenari", "base,live"])
    out = capsys.readouterr().out
    assert "  ?? SP1 x0" in out and "     SP1: PRO fade" in out


def test_certifica_trova_la_cartella_della_partita(tmp_path, monkeypatch, capsys):
    """Senza --data-dir il registro da' il giorno piu' recente; la partita sta in
    un altro giorno col suo `_names.json`: il banco la trova e usa quei nomi."""
    _partita(tmp_path / "20260706", "35794049")
    _nomi_json(tmp_path / "20260706", {"35794049": {str(BAR): "Sinner", str(SIM): "Struff"}})
    _partita(tmp_path / "20260707", "35790089")
    monkeypatch.setenv("TENNIS_RECORD_DIR", str(tmp_path))
    visti = []
    monkeypatch.setattr(C, "_esegui_compiti", _fake_esegui(
        lambda c: _referto(c[1], nomi_assenti=False, sollecitati={"SP1": 1, "SP2": 1, "SP3": 1}),
        visti))
    C.main(["tennis_pro", "35794049", "--scenari", "base"])
    out = capsys.readouterr().out
    assert visti[0][2] == str(tmp_path / "20260706")
    assert "cartella della partita 35794049: %s" % (tmp_path / "20260706") in out
    assert "nomi dei giocatori 35794049: PRESENTI (Sinner, Struff)" in out
    assert "NE NON ESERCITABILI" not in out


def test_certifica_altri_bot_senza_righe_nuove(tmp_path, monkeypatch, capsys):
    giorno = tmp_path / "20260707"
    _partita(giorno, "35790089")
    monkeypatch.setattr(C, "_esegui_compiti", _fake_esegui(
        lambda c: CERT.Referto(event_id=c[1], decisioni=1, tick=1), []))
    C.main(["tennis_flb", "35790089", "--data-dir", str(giorno), "--scenari", "base"])
    out = capsys.readouterr().out
    assert "nomi dei giocatori: non usati da tennis_flb" in out
    assert "controlli dei setup" not in out and "  NE " not in out
    assert "NE NON ESERCITABILI" not in out


def test_chiave_mercati_nomi_uguale_al_convertitore():
    """08/10 (coordinatore): la chiave riservata di `_names.json` e' copiata in
    `replay_bot` (importare `convertitore` porterebbe dipendenze pesanti nel
    replay): le due copie devono restare identiche."""
    from Betfair.stream.tennis_live.tools import replay_bot as RB
    from Betfair.stream.tennis_replay import convertitore as CV

    assert RB.CHIAVE_MERCATI_NOMI == CV.CHIAVE_MERCATI_NOMI
