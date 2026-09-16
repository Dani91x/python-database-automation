# -*- coding: utf-8 -*-
"""IL BANCO VELOCE DEVE DARE IL REFERTO IDENTICO A QUELLO LENTO.

Ordine dell'utente (16/09): «e' da velocizzare senza perdere dati e qualita'».
La velocita' e' il risultato; il vincolo e' l'IDENTITA'.

Che cosa si confronta, sulla STESSA registrazione reale, fra la via lenta (il
`_read_loop` di flumine tale e quale, che ricostruisce un `MarketBook` per ogni
cache a ogni riga) e la via veloce (`banco_comune.GeneratoreLibri`, che riusa
l'oggetto dei mercati che la riga non ha toccato):

  * la SEQUENZA delle decisioni del bot, giro per giro;
  * gli ORDINI: riferimento, prezzo, size, stato, e il publish time del
    piazzamento (l'orologio di mercato al momento del place);
  * i FILL uno per uno (`order.simulated.matched`): publish time, prezzo, size
    — cioe' esattamente cio' che PROCESSO_STANDARD_BOT §6.8 chiede nel referto;
  * le VIOLAZIONI e tutti i numeri del referto di Mike (tick, decisioni,
    azioni, stati visti, motivi, note);
  * le RIGHE DI SCAN scritte dallo scanner vero.

E la FALSIFICAZIONE: si fa saltare un book alla via veloce e il confronto deve
diventare ROSSO. Un test che non sa diventare rosso non certifica niente.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from Betfair.stream.backtest import banco_comune as B

# la registrazione piu' corta del corpus in cui il bot opera davvero
# (la stessa del campione di `test_cert_banco_2026_09_16.py`)
EVENTO = "35823616"


def _cartella() -> str:
    from Betfair.stream.config_stream import DATA_DIR

    return DATA_DIR


def _serve_registrazione() -> None:
    percorso = os.path.join(_cartella(), EVENTO, f"{EVENTO}.raw.jsonl")
    if not os.path.isfile(percorso):
        pytest.skip(f"registrazione non su questa macchina: {percorso}")


def _impronta(oggetto) -> str:
    grezzo = json.dumps(oggetto, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha1(grezzo.encode("ascii")).hexdigest()  # noqa: S324


# ---------------------------------------------------------------------------
# un bot di prova con le MANI VERE
# ---------------------------------------------------------------------------
class BotDiProva:
    """Non e' una strategia: e' un provocatore di ordini.

    Piazza, a giri fissi, un TAKER (che abbina subito sul book del bet delay) e
    un ordine APPOGGIATO al miglior prezzo BACK (che resta in coda e puo'
    abbinare solo quando arrivano book DEL SUO mercato col volume scambiato).
    Serve proprio a questo il test: se la via veloce facesse perdere un
    aggiornamento del mercato dell'ordine appoggiato, il fill cambierebbe.
    """

    GIRO_TAKER = 6
    GIRO_APPOGGIATO = 12

    def __init__(self) -> None:
        self.decisioni = []
        self.piazzamenti = []
        self.mercato = None
        self.giro = 0

    # --- il miglior BACK disponibile su un mercato aperto -----------------
    @staticmethod
    def _miglior_back(strategia):
        for mid in sorted(strategia.mercati):
            mb = getattr(strategia.mercati[mid], "market_book", None)
            if mb is None or getattr(mb, "status", None) != "OPEN":
                continue
            for runner in (getattr(mb, "runners", None) or []):
                livelli = B._livelli_di_produzione(
                    getattr(getattr(runner, "ex", None), "available_to_back", None))
                if livelli and livelli[0].price and (livelli[0].size or 0) >= 2.0:
                    return (str(mid), int(runner.selection_id),
                            float(livelli[0].price), float(livelli[0].size))
        return None

    def __call__(self, *, db, market, now, row, banco, strategia):
        self.mercato = market
        self.giro += 1
        ms = int(now.timestamp() * 1000)
        scelta = self._miglior_back(strategia)
        if scelta is None:
            self.decisioni.append([ms, "senza-book", bool(row)])
            return
        mid, sel, prezzo, size = scelta
        self.decisioni.append([ms, "visto", mid, sel, prezzo, round(size, 2), bool(row)])
        if self.giro == self.GIRO_TAKER:
            # LAY a 1000: accetta qualunque quota -> abbina subito contro il
            # miglior BACK disponibile. E' il percorso taker.
            res = market.place_order_live(
                market_id=mid, selection_id=sel, price=1000.0, size=5.0,
                event_id=EVENTO, side="lay", customer_ref="prova-taker",
                fill_or_kill=True)
            self._registra("taker", ms, mid, sel, 1000.0, 5.0, res)
        elif self.giro == self.GIRO_APPOGGIATO:
            # BACK al miglior prezzo BACK gia' sul book: si mette IN CODA
            # dietro a chi c'e' gia' (`_piq`) e abbina solo col volume
            # scambiato dei book successivi DI QUEL MERCATO.
            res = market.place_order_live(
                market_id=mid, selection_id=sel, price=prezzo, size=4.0,
                event_id=EVENTO, side="back", customer_ref="prova-appoggiato",
                fill_or_kill=False)
            self._registra("appoggiato", ms, mid, sel, prezzo, 4.0, res)

    def _registra(self, ruolo, ms, mid, sel, prezzo, size, res) -> None:
        self.piazzamenti.append([
            ruolo, ms, mid, sel, prezzo, size,
            bool(res.ok), str(res.order_status),
            round(float(res.size_matched or 0.0), 2),
            (round(float(res.avg_price_matched), 4) if res.avg_price_matched else None),
        ])


def _corsa(veloce: bool):
    """Una corsa intera del banco, e tutto cio' che serve a confrontarla."""
    bot = BotDiProva()
    esito = B.replay_evento(event_id=EVENTO, cartella=_cartella(), servizio=bot,
                            sport="calcio", veloce=veloce)
    mercato = bot.mercato
    fill = mercato.fills() if mercato is not None else {}
    ordini = {}
    if mercato is not None:
        for ref, o in mercato.ordini.items():
            sim = getattr(o, "simulated", None)
            ordini[ref] = {
                "lato": str(getattr(o, "side", "")),
                "prezzo": getattr(getattr(o, "order_type", None), "price", None),
                "size": getattr(getattr(o, "order_type", None), "size", None),
                "stato": mercato._stato_betfair(o),
                "abbinato": round(float(getattr(sim, "size_matched", 0.0) or 0.0), 2),
                "medio": getattr(sim, "average_price_matched", None) or None,
                "annullato": round(float(getattr(o, "size_cancelled", 0.0) or 0.0), 2),
                "scaduto": round(float(getattr(o, "size_lapsed", 0.0) or 0.0), 2),
            }
    return {
        "decisioni": bot.decisioni,
        "piazzamenti": bot.piazzamenti,
        "ordini": ordini,
        "fill": {k: [[r[0], r[1], r[2]] for r in v] for k, v in fill.items()},
        "righe_scan": esito.righe_scan,
        "tick": esito.tick,
        "giri": esito.giri,
        "mercati": dict(esito.mercati),
        "book_attesi": esito.book_attesi,
        "book_in_ritardo": esito.book_in_ritardo,
        "lapse_al_fischio": esito.lapse_al_fischio,
        "senza_futuro": esito.senza_futuro,
        "errori": list(esito.errori),
        "ultima_riga": esito.ultima_riga,
    }


# ---------------------------------------------------------------------------
# 1) le due vie danno lo stesso identico referto
# ---------------------------------------------------------------------------
@pytest.mark.cert
def test_via_veloce_identica_alla_via_lenta():
    _serve_registrazione()
    lento = _corsa(veloce=False)
    veloce = _corsa(veloce=True)

    # il confronto campo per campo, cosi' un rosso dice SUBITO cosa e' cambiato
    for campo in ("decisioni", "piazzamenti", "ordini", "fill", "righe_scan",
                  "tick", "giri", "mercati", "book_attesi", "book_in_ritardo",
                  "lapse_al_fischio", "senza_futuro", "errori", "ultima_riga"):
        assert veloce[campo] == lento[campo], (
            f"la via veloce ha cambiato '{campo}': "
            f"lenta={_impronta(lento[campo])} veloce={_impronta(veloce[campo])}")
    assert _impronta(veloce) == _impronta(lento)

    # e il test deve avere avuto qualcosa da confrontare
    assert lento["tick"] > 0, "nessun book: il confronto non dimostrerebbe niente"
    assert lento["piazzamenti"], "nessun ordine piazzato: il matching non e' stato provato"
    assert lento["fill"], "nessun fill: la coda di flumine non e' stata provata"


# ---------------------------------------------------------------------------
# 2) i mercati toccati ricevono TUTTI i loro aggiornamenti
# ---------------------------------------------------------------------------
@pytest.mark.cert
def test_nessun_aggiornamento_perso_sui_mercati_toccati():
    """La via veloce non salta un aggiornamento: RIUSA l'oggetto dei mercati che
    la riga non ha toccato. Il numero di book emessi e' lo stesso; a cambiare e'
    solo quanti ne vengono COSTRUITI."""
    _serve_registrazione()
    emessi = {}
    costruiti = {}

    for veloce in (False, True):
        conteggio = {"n": 0}

        def contatore(*, db, market, now, row, banco, strategia, _c=conteggio):
            _c["n"] += 1

        motori = []
        vero = B.MotoreReplay._a_flumine

        def spia(self, market_book, _vero=vero, _c=conteggio):
            if self not in motori:
                motori.append(self)
            self._emessi = getattr(self, "_emessi", 0) + 1
            return _vero(self, market_book)

        B.MotoreReplay._a_flumine = spia
        try:
            B.replay_evento(event_id=EVENTO, cartella=_cartella(),
                            servizio=contatore, sport="calcio", veloce=veloce)
        finally:
            B.MotoreReplay._a_flumine = vero
        emessi[veloce] = sum(getattr(m, "_emessi", 0) for m in motori)
        costruiti[veloce] = sum(
            (m.generatore.costruiti if m.generatore else 0) for m in motori)

    assert emessi[True] == emessi[False] > 0, (
        f"book emessi diversi: lenta={emessi[False]} veloce={emessi[True]}")
    # la via LENTA costruisce un MarketBook per ogni book emesso (e' quello che
    # fa `_read_loop`); la veloce ne costruisce solo uno per aggiornamento vero.
    assert costruiti[True] < emessi[False], (
        f"nessun risparmio: la via lenta costruisce {emessi[False]} MarketBook, "
        f"la veloce {costruiti[True]}")
    # il risparmio dichiarato: ci si aspetta almeno 3 volte meno oggetti
    assert costruiti[True] * 3 <= emessi[False], (
        f"risparmio minore dell'atteso: {emessi[False]} -> {costruiti[True]}")


# ---------------------------------------------------------------------------
# 3) FALSIFICAZIONE: un salto di book e il test diventa rosso
# ---------------------------------------------------------------------------
@pytest.mark.cert
def test_falsificazione_un_salto_di_book_rende_rosso(monkeypatch):
    """Si introduce nella via veloce esattamente il difetto che si teme: un book
    ogni N non viene emesso. Il confronto DEVE fallire, altrimenti il test 1 non
    sta misurando niente."""
    _serve_registrazione()
    lento = _corsa(veloce=False)

    veloce_vera = B.GeneratoreLibri.veloce

    def veloce_bucata(self):
        for i, libri in enumerate(veloce_vera(self)):
            if i % 25 == 24:
                continue          # IL DIFETTO: un book ogni 25 sparisce
            yield libri

    monkeypatch.setattr(B.GeneratoreLibri, "veloce", veloce_bucata)
    bucato = _corsa(veloce=True)

    assert _impronta(bucato) != _impronta(lento), (
        "un salto di book NON ha cambiato il referto: il confronto del test 1 "
        "non e' in grado di accorgersi di una perdita di dati")


# ---------------------------------------------------------------------------
# 4) il memo si invalida SEMPRE, anche sulle righe che flumine non emette
# ---------------------------------------------------------------------------
class _CacheFinta:
    """Una cache di mercato come quella di betfairlightweight, ridotta ai due
    fatti che contano qui: `active` e `create_resource`."""

    def __init__(self, market_id: str) -> None:
        self.market_id = market_id
        self.active = True
        self.versione = 0
        self.costruiti = 0

    def create_resource(self, unique_id, snap=False):
        self.costruiti += 1
        return ("book", self.market_id, self.versione)


class _FlussoFinto:
    _lookup = "mc"

    def __init__(self, esiti) -> None:
        self._caches = {}
        self._esiti = list(esiti)      # cosa risponde `_process`, riga per riga
        self.i = 0

    def _process(self, mc, publish_time):
        for agg in mc:
            cache = self._caches.get(agg["id"])
            if cache is None:
                cache = self._caches[agg["id"]] = _CacheFinta(agg["id"])
            cache.versione += 1        # LA CACHE E' CAMBIATA
        esito = self._esiti[self.i] if self.i < len(self._esiti) else True
        self.i += 1
        return esito


class _AscoltatoreFinto:
    def __init__(self, flusso) -> None:
        self.stream = flusso
        self.update_clk = True

    def register_stream(self, unique_id, operation):
        return None


class _GeneratoreStoricoFinto:
    def __init__(self, percorso, listener) -> None:
        self.file_path = percorso
        self.listener = listener
        self.unique_id = 1
        self.operation = "marketSubscription"

    def _read_loop(self):  # pragma: no cover - la via lenta non serve qui
        return iter(())


class _StreamFinto:
    def __init__(self, gs) -> None:
        self._gs = gs

    def create_generator(self):
        return self._gs._read_loop


def test_il_memo_si_invalida_anche_se_la_riga_non_viene_emessa(tmp_path):
    """`_process` aggiorna le cache e POI dice se emettere (`active`): con i
    `listener_kwargs` (inplay, seconds_to_start) puo' rispondere False su una
    riga che ha comunque cambiato i prezzi. Se il memo non venisse invalidato
    li', il giro dopo il banco servirebbe un book VECCHIO — una perdita di dati
    silenziosa, cioe' esattamente cio' che questo lavoro non deve fare."""
    percorso = tmp_path / "finto.jsonl"
    percorso.write_text(
        '{"pt":1,"mc":[{"id":"1.1"}]}' + chr(10) +
        '{"pt":2,"mc":[{"id":"1.1"}]}' + chr(10) +   # riga NON emessa
        '{"pt":3,"mc":[{"id":"1.2"}]}' + chr(10),    # tocca un ALTRO mercato
        encoding="ascii")
    flusso = _FlussoFinto([True, False, True])
    gs = _GeneratoreStoricoFinto(str(percorso), _AscoltatoreFinto(flusso))
    gen = B.GeneratoreLibri(_StreamFinto(gs))

    uscita = [list(x) for x in gen.veloce()]
    # riga 1: emesso 1.1 versione 1. riga 2: NON emessa (ma 1.1 e' cambiato).
    # riga 3: emessi 1.1 e 1.2 -> 1.1 DEVE essere alla versione 2, non alla 1.
    assert uscita[0] == [("book", "1.1", 1)]
    assert uscita[1] == [("book", "1.1", 2), ("book", "1.2", 1)]
    assert len(uscita) == 2


def test_il_memo_riusa_solo_i_mercati_fermi(tmp_path):
    """Il contrario: un mercato che NON cambia non viene ricostruito."""
    percorso = tmp_path / "finto.jsonl"
    percorso.write_text(
        '{"pt":1,"mc":[{"id":"1.1"},{"id":"1.2"}]}' + chr(10) +
        '{"pt":2,"mc":[{"id":"1.1"}]}' + chr(10) +
        '{"pt":3,"mc":[{"id":"1.1"}]}' + chr(10),
        encoding="ascii")
    flusso = _FlussoFinto([True, True, True])
    gs = _GeneratoreStoricoFinto(str(percorso), _AscoltatoreFinto(flusso))
    gen = B.GeneratoreLibri(_StreamFinto(gs))
    uscita = [list(x) for x in gen.veloce()]

    # 6 book emessi (2 mercati x 3 righe), ma 1.2 costruito UNA volta sola
    assert sum(len(x) for x in uscita) == 6
    assert flusso._caches["1.2"].costruiti == 1
    assert flusso._caches["1.1"].costruiti == 3
    assert gen.costruiti == 4 and gen.riusati == 2


# ---------------------------------------------------------------------------
# 5) LA REGOLA DEL TEMPO: l'attesa dura quanto Betfair trattiene, non di piu'
# ---------------------------------------------------------------------------
# I NUMERI DI SCENARI DIVERSI SONO CONFRONTABILI SOLO DOVE LA SEQUENZA DI
# CHIAMATE E' IDENTICA FINO AL PUNTO CONFRONTATO. Perche' ogni chiamata
# bloccante consuma TEMPO DI MERCATO (in produzione come nel banco), e il tempo
# consumato sposta il book su cui si abbina tutto quello che viene dopo. Due
# scenari che prima dell'ingresso fanno le STESSE chiamate devono pero' avere
# l'ingresso IDENTICO: se non ce l'hanno, e' il banco che sbaglia, non la
# strategia.
class BotDueScenari:
    """Entra sempre allo stesso giro; DOPO l'ingresso i due scenari divergono
    (uno chiude subito, l'altro tiene). L'INGRESSO deve restare identico."""

    GIRO_INGRESSO = 6

    def __init__(self, chiude: bool) -> None:
        self.chiude = chiude
        self.giro = 0
        self.ingresso = None
        self.dopo = []
        self.mercato = None

    def __call__(self, *, db, market, now, row, banco, strategia):
        self.mercato = market
        self.giro += 1
        scelta = BotDiProva._miglior_back(strategia)
        if scelta is None:
            return
        mid, sel, prezzo, _size = scelta
        if self.giro == self.GIRO_INGRESSO:
            res = market.place_order_live(
                market_id=mid, selection_id=sel, price=1000.0, size=5.0,
                event_id=EVENTO, side="lay", customer_ref="ingresso",
                fill_or_kill=True)
            self.ingresso = [bool(res.ok), str(res.order_status),
                             round(float(res.size_matched or 0.0), 2),
                             res.avg_price_matched]
        elif self.giro > self.GIRO_INGRESSO and self.chiude and self.giro % 4 == 0:
            # LA DIVERGENZA: solo questo scenario continua a chiamare Betfair
            res = market.place_order_live(
                market_id=mid, selection_id=sel, price=1.01, size=2.0,
                event_id=EVENTO, side="back", customer_ref=f"chiusura-{self.giro}",
                fill_or_kill=True)
            self.dopo.append(bool(res.ok))


@pytest.mark.cert
def test_lingresso_non_cambia_per_quello_che_succede_dopo():
    """Il fill dell'INGRESSO (esito, size, prezzo medio) e i suoi abbinamenti
    uno per uno devono essere identici nei due scenari: fino a quel punto la
    sequenza di chiamate e' la stessa, quindi il tempo consumato e' lo stesso."""
    _serve_registrazione()
    esiti = {}
    for chiude in (False, True):
        bot = BotDueScenari(chiude)
        B.replay_evento(event_id=EVENTO, cartella=_cartella(), servizio=bot,
                        sport="calcio")
        fill = bot.mercato.fills().get("ingresso")
        esiti[chiude] = (bot.ingresso, fill)
    assert esiti[False][0] is not None, "l'ingresso non e' mai stato piazzato"
    assert esiti[False][0] == esiti[True][0], (
        f"l'esito dell'ingresso cambia con cio' che succede DOPO: "
        f"{esiti[False][0]} vs {esiti[True][0]}")
    assert esiti[False][1] == esiti[True][1], (
        f"i fill dell'ingresso cambiano con cio' che succede DOPO: "
        f"{esiti[False][1]} vs {esiti[True][1]}")


@pytest.mark.cert
def test_lattesa_dura_quanto_il_bet_delay_e_non_quanto_il_mercato_e_liquido():
    """FALSIFICAZIONE della regola del tempo: con `ATTESA_ESATTA = False` il
    banco torna ad aspettare «finche' flumine esegue», cioe' finche' arriva un
    book DI QUEL mercato — un'attesa che dipende dalla liquidita' e non dalla
    regola di Betfair. Il tempo di mercato consumato deve cambiare."""
    _serve_registrazione()

    def consumo(esatta):
        vecchio = B.ATTESA_ESATTA
        B.ATTESA_ESATTA = esatta
        try:
            bot = BotDiProva()
            esito = B.replay_evento(event_id=EVENTO, cartella=_cartella(),
                                    servizio=bot, sport="calcio")
            return esito.book_attesi
        finally:
            B.ATTESA_ESATTA = vecchio

    esatta = consumo(True)
    lasca = consumo(False)
    assert esatta > 0, "nessun piazzamento ha atteso: il test non misura niente"
    assert esatta != lasca, (
        "l'attesa esatta e quella vecchia consumano gli STESSI book: il "
        f"controllo non sa accorgersi della differenza ({esatta} vs {lasca})")
    assert esatta < lasca, (
        f"l'attesa esatta deve consumare MENO book di quella che aspetta il "
        f"prossimo book del mercato: {esatta} vs {lasca}")


# ---------------------------------------------------------------------------
# 6) LE LETTURE NON SONO GRATIS (latenza ASSUNTA, non misurata)
# ---------------------------------------------------------------------------
class BotCheLegge:
    """Legge gli ordini a ogni giro, come fa un bot vero prima di decidere."""

    def __init__(self, quante: int) -> None:
        self.quante = int(quante)
        self.mercato = None
        self.giri = 0

    def __call__(self, *, db, market, now, row, banco, strategia):
        self.mercato = market
        self.giri += 1
        for _ in range(self.quante):
            market.list_current_orders()


@pytest.mark.cert
def test_una_lettura_costa_tempo_di_mercato():
    """In produzione `listCurrentOrders` e' una REST sincrona: il bot e' fermo
    sulla rete mentre i book continuano ad arrivare. Nel banco costava ZERO, e
    zero non e' il tempo vero. Il valore (120 ms) e' ASSUNTO — non misurato —
    ed e' dichiarato nel referto insieme a quante letture il bot fa per giro."""
    _serve_registrazione()

    def corsa(quante, latenza):
        vecchia = B.LATENZA_LETTURA_S
        B.LATENZA_LETTURA_S = latenza
        try:
            bot = BotCheLegge(quante)
            esito = B.replay_evento(event_id=EVENTO, cartella=_cartella(),
                                    servizio=bot, sport="calcio")
            return bot.mercato.letture, esito.giri, esito.tick
        finally:
            B.LATENZA_LETTURA_S = vecchia

    letture, giri, tick_con = corsa(3, 0.120)
    assert letture == giri * 3 > 0, "le letture non sono state contate"
    _l0, _g0, tick_senza = corsa(3, 0.0)
    # con la latenza accesa il tempo di mercato scorre durante le letture: il
    # bot vede MENO giri utili, quindi il conteggio dei tick cambia
    assert tick_con != tick_senza, (
        f"la latenza di lettura non sposta niente ({tick_con} vs {tick_senza}): "
        f"il controllo non sa accorgersi dell'assunzione")


@pytest.mark.cert
def test_la_latenza_di_lettura_e_dichiarata_e_governabile():
    """Un'assunzione che non si puo' spegnere ne' cambiare non e' un'assunzione:
    e' un numero cablato. 0.0 deve riportare il banco a com'era."""
    assert B.LATENZA_LETTURA_S == 0.120
    import flumine.config as fconf
    assert B.LATENZA_LETTURA_S == fconf.place_latency, (
        "la latenza assunta deve essere la stessa gia' certificata di flumine, "
        "non un numero nuovo inventato qui")


# ---------------------------------------------------------------------------
# 7) SU QUALE BOOK SI ABBINA: l'ultimo NOTO entro t + place_latency + betDelay
# ---------------------------------------------------------------------------
# UN SOLO PUNTO DI VERITA': `MotoreReplay.attendi_esecuzione` fa scorrere il
# tempo di mercato fino alla scadenza, e l'esecuzione usa `market.market_book`,
# cioe' l'ULTIMO book di quel mercato arrivato ENTRO quella scadenza. Vale per
# ogni percorso del banco che piazzi, `replay_evento` compreso: il motore e'
# uno solo.
#
# PERCHE' NON QUELLO DOPO. Betfair abbina sul mercato com'e' a t+delay. Di quel
# mercato noi abbiamo istantanee: la migliore approssimazione dello stato a
# t+delay e' l'ultima istantanea arrivata ENTRO t+delay. Usare la prima
# istantanea SUCCESSIVA vorrebbe dire mostrare al replay prezzi che a t+delay
# non erano ancora accaduti — guardare nel futuro, e rendere il banco ottimista
# (difetto 13 del catalogo §7).
#
# Lo garantisce l'ORDINE dentro `_a_flumine`, ereditato da
# `FlumineSimulation._process_market_books`: `_check_pending_packages` viene
# PRIMA di `market(market_book)`. Quando arriva il book che fa scattare la
# scadenza, l'ordine si abbina su quello di prima. Invertire le due righe
# farebbe abbinare su un book del futuro.
def _definizione_vera(bet_delay):
    """Il `marketDefinition` di una registrazione VERA del repo, col solo
    `betDelay` cambiato. Scriverlo a mano vorrebbe dire scrivere un finto che
    parla una lingua diversa dal vero — il difetto 27 del catalogo §7."""
    import copy
    import json
    import os

    from Betfair.stream.config_stream import DATA_DIR

    sorgente = os.path.join(DATA_DIR, "_synth_safe_tennis_prezzo_migliore",
                            "_synth_safe_tennis_prezzo_migliore.raw.jsonl")
    if not os.path.isfile(sorgente):
        pytest.skip(f"registrazione di riferimento assente: {sorgente}")
    with open(sorgente, encoding="utf-8") as fh:
        prima = json.loads(fh.readline())
    md = copy.deepcopy(prima["mc"][0]["marketDefinition"])
    md["betDelay"] = int(bet_delay)
    md["eventId"] = "1"
    md["runners"] = [{"status": "ACTIVE", "sortPriority": 1, "id": 111},
                     {"status": "ACTIVE", "sortPriority": 2, "id": 222}]
    return md


def _registrazione_a_passo(cartella, bet_delay, passo_s, quanti):
    """Una registrazione minima: un mercato, un runner, il miglior BACK che sale
    di un tick a ogni book. Serve a far cadere la scadenza DENTRO l'intervallo
    fra due book: sulle registrazioni vere del corpus non capita mai (betDelay
    3 s, book ogni 5 s), quindi li' la regola non si puo' mettere alla prova."""
    import json
    import os

    dove = os.path.join(str(cartella), "1")
    os.makedirs(dove, exist_ok=True)
    t0 = 1789495200000
    righe = []
    for i in range(quanti):
        prezzo = round(1.50 + i * 0.10, 2)
        mc = {"id": "1.999", "rc": [{"id": 111,
                                     "atb": [[prezzo, 500.0]],
                                     "atl": [[round(prezzo + 0.02, 2), 500.0]],
                                     "trd": [[prezzo, 900.0]]}]}
        if i == 0:
            # IL FINTO PARLA COME IL VERO: il `marketDefinition` non si inventa
            # (a flumine ne mancherebbero 15 campi obbligatori), si prende da
            # una registrazione del repo e si cambia il solo `betDelay`.
            mc["marketDefinition"] = _definizione_vera(bet_delay)
            mc["rc"].append({"id": 222, "atb": [[3.0, 500.0]], "atl": [[3.1, 500.0]]})
        righe.append(json.dumps({"op": "mcm", "pt": t0 + i * passo_s * 1000,
                                 "mc": [mc]}))
    with open(os.path.join(dove, "1.raw.jsonl"), "w", encoding="ascii") as fh:
        fh.write(chr(10).join(righe) + chr(10))
    return str(cartella)


class BotUnTaker:
    """Piazza UN taker a un giro noto e registra che cosa aveva letto."""

    def __init__(self, giro):
        self.giro_piazza = int(giro)
        self.g = 0
        self.mercato = None
        self.esito = None
        self.letto = None

    def __call__(self, *, db, market, now, row, banco, strategia):
        self.mercato = market
        self.g += 1
        m = strategia.mercati.get("1.999")
        if m is None or getattr(m, "market_book", None) is None:
            return
        if self.g != self.giro_piazza:
            return
        runner = m.market_book.runners[0]
        self.letto = B._livelli_di_produzione(runner.ex.available_to_back)[0].price
        res = market.place_order_live(
            market_id="1.999", selection_id=111, price=1.01, size=5.0,
            event_id="1", side="back", customer_ref="taker", fill_or_kill=True)
        self.esito = (res.size_matched, res.avg_price_matched)


def _corsa_taker(cartella, bet_delay, passo_s, giro):
    dove = _registrazione_a_passo(cartella, bet_delay, passo_s, 40)
    bot = BotUnTaker(giro)
    B.replay_evento(event_id="1", cartella=dove, servizio=bot, sport="calcio",
                    ogni_ms=1)
    return bot


@pytest.mark.cert
def test_il_fill_usa_lultimo_book_entro_la_scadenza(tmp_path):
    """betDelay 12 s, book ogni 5 s: la scadenza (t + 0,12 + 12) cade dopo DUE
    book e prima del terzo. Il fill deve usare il secondo, non il terzo."""
    bot = _corsa_taker(tmp_path / "a", bet_delay=12, passo_s=5, giro=3)
    assert bot.esito is not None and bot.esito[0] == 5.0
    atteso = round(bot.letto + 0.20, 2)     # due tick da 0,10 = i due book
    futuro = round(bot.letto + 0.30, 2)     # il terzo book, oltre la scadenza
    assert bot.esito[1] == atteso, (
        f"abbinato a {bot.esito[1]}: atteso {atteso}, l'ultimo book ENTRO la "
        f"scadenza. {futuro} sarebbe il book DOPO, cioe' futuro")


@pytest.mark.cert
def test_il_bet_delay_sposta_davvero_il_book_dellabbinamento(tmp_path):
    """Con lo stesso dato, un bet delay piu' lungo deve far abbinare piu' avanti.
    Se il fill non si spostasse, il bet delay sarebbe decorativo: e' l'accusa da
    verificare, e questo test la mette alla prova."""
    corto = _corsa_taker(tmp_path / "corto", bet_delay=1, passo_s=5, giro=3)
    lungo = _corsa_taker(tmp_path / "lungo", bet_delay=12, passo_s=5, giro=3)
    assert corto.letto == lungo.letto, "i due giri non partono dallo stesso book"
    assert corto.esito[1] == corto.letto, (
        f"con betDelay 1 s la scadenza cade prima del book successivo: il fill "
        f"resta sul book letto ({corto.letto}), invece e' {corto.esito[1]}")
    assert lungo.esito[1] > corto.esito[1], (
        f"il bet delay NON sposta il book dell'abbinamento: {corto.esito[1]} "
        f"con 1 s e {lungo.esito[1]} con 12 s")


@pytest.mark.cert
def test_falsificazione_il_book_del_futuro_cambia_il_fill(tmp_path):
    """IL DIFETTO CHE LA REGOLA IMPEDISCE: applicare al mercato il book che fa
    scattare la scadenza PRIMA di eseguire i pacchetti in attesa. L'ordine si
    abbinerebbe su un prezzo che a t+delay non era ancora accaduto. Se
    invertire quelle due righe non cambiasse il fill, i due test sopra non
    starebbero certificando niente."""
    vera = B.MotoreReplay._a_flumine

    def invertito(self, market_book):
        mercato = self.quadro.markets.markets.get(market_book.market_id)
        if mercato is not None:
            mercato(market_book)        # il futuro entra PRIMA dell'esecuzione
        return vera(self, market_book)

    sano = _corsa_taker(tmp_path / "sano", bet_delay=12, passo_s=5, giro=3)
    B.MotoreReplay._a_flumine = invertito
    try:
        bucato = _corsa_taker(tmp_path / "bucato", bet_delay=12, passo_s=5, giro=3)
    finally:
        B.MotoreReplay._a_flumine = vera
    assert sano.letto == bucato.letto, "i due giri non partono dallo stesso book"
    assert bucato.esito[1] != sano.esito[1], (
        f"col book del futuro gia' applicato il fill non cambia "
        f"({sano.esito[1]}): il controllo non sa vedere uno sguardo in avanti")
    assert bucato.esito[1] > sano.esito[1], (
        f"lo sguardo in avanti deve dare un prezzo MIGLIORE: "
        f"{sano.esito[1]} -> {bucato.esito[1]}")
