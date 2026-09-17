"""PLACE-AND-TRIM su REST: qualsiasi importo, anche 0,05 EUR.

Nessuna rete: il client Betfair e' un finto che registra le chiamate. File
ASCII-only (console Windows cp1252).

Perche' esiste
--------------
Betfair rifiuta un place DIRETTO sotto il minimo di giurisdizione (.it BACK 2,00
/ LAY 0,50), ma NON rifiuta un ordine gia' esistente RIDOTTO sotto quella soglia.
E' la tecnica di Bet Angel, Fairbot e Betting Toolkit:

  1. si parcheggia il MINIMO a una quota NON abbinabile (BACK 1000 / LAY 1.01);
  2. si taglia col cancel parziale fino all'importo voluto;
  3. si riprezza alla quota reale.

Questi test coprono la sequenza e soprattutto le tre guardie money-critical:
il parcheggio che si abbina, il taglio non confermato, il riprezzo rifiutato.
In tutti e tre i casi il residuo va RITIRATO prima di propagare l'errore: mai un
ordine a riposo non tracciato sul conto.
"""
from __future__ import annotations

import pytest

from Betfair.omega import omega_market as M


# ---------------------------------------------------------------------------
# Finto client Betfair
# ---------------------------------------------------------------------------
class ClientFinto:
    def __init__(self, *, matched_al_parcheggio=0.0, tagliato=None, taglio_ok=True,
                 riprezzo_ok=True, matched_finale=0.0, place_ok=True,
                 residuo_letto=None, book=None):
        self.matched_al_parcheggio = matched_al_parcheggio
        self.tagliato = tagliato
        self.taglio_ok = taglio_ok
        self.riprezzo_ok = riprezzo_ok
        self.matched_finale = matched_finale
        self.place_ok = place_ok
        # 17/09 - verifica FAIL-CLOSED: dopo il taglio la funzione RILEGGE
        # l'ordine da Betfair (``listCurrentOrders`` per betId). ``residuo_letto``
        # e' quello che la lettura mostra; ``None`` = il residuo atteso (target).
        self.ritiro_ok = True
        self.residuo_letto = residuo_letto
        self.matched_letto = 0.0
        # book per (best_back, best_lay): vuoto = IGNOTO -> percorso conservativo
        # (parcheggio lontano + replace), che e' la sequenza storica.
        self.book = book
        self.chiamate: list = []      # solo place/cancel/replace (mutanti)
        self.letture_raw: list = []   # book + listCurrentOrders
        self._park_size = 0.0
        self._residuo_atteso = 0.0

    def list_market_book(self, market_ids, **kw):
        self.letture_raw.append(("listMarketBook", market_ids))
        return self.book or []

    def place_orders(self, market_id, instructions, customer_ref=None,
                     customer_strategy_ref=None, **kw):
        self.chiamate.append(("place", market_id, instructions[0]))
        self._park_size = float(instructions[0]["limitOrder"]["size"])
        self._residuo_atteso = self._park_size
        if not self.place_ok:
            return {"status": "FAILURE", "instructionReports": [
                {"status": "FAILURE", "errorCode": "INSUFFICIENT_FUNDS"}]}
        return {"status": "SUCCESS", "instructionReports": [
            {"status": "SUCCESS", "betId": "bet-1", "orderStatus": "EXECUTABLE",
             "sizeMatched": self.matched_al_parcheggio}]}

    def betting_rpc(self, method=None, params=None, **kw):
        instr = (params.get("instructions") or [None])[0]
        nome = method.split("/")[-1]
        if nome == "listCurrentOrders":
            self.letture_raw.append((nome, params))
        else:
            self.chiamate.append((nome, params.get("marketId"), instr))
        if method.endswith("cancelOrders"):
            instr = params["instructions"][0]
            if "sizeReduction" not in instr:
                # RITIRO TOTALE del residuo. ``ritiro_ok=False`` = Betfair
                # risponde FAILURE: l'ordine e' ancora VIVO, e dichiararlo
                # ritirato sarebbe un rifiuto CERTO su una gamba viva.
                if not self.ritiro_ok:
                    return {"status": "FAILURE", "instructionReports": [
                        {"status": "FAILURE", "errorCode": "BET_TAKEN_OR_LAPSED"}]}
                return {"status": "SUCCESS", "instructionReports": [{"status": "SUCCESS"}]}
            tagliato = self.tagliato if self.tagliato is not None else instr["sizeReduction"]
            if self.taglio_ok:
                self._residuo_atteso = round(self._park_size - float(tagliato), 2)
            return {"status": "SUCCESS" if self.taglio_ok else "FAILURE",
                    "instructionReports": [
                        {"status": "SUCCESS" if self.taglio_ok else "FAILURE",
                         "sizeCancelled": tagliato}]}
        if method.endswith("listCurrentOrders"):
            residuo = (self.residuo_letto if self.residuo_letto is not None
                       else self._residuo_atteso)
            return {"currentOrders": [{
                "betId": "bet-1", "sizeRemaining": residuo,
                "sizeMatched": self.matched_letto,
                "averagePriceMatched": None,
                "placedDate": "2026-09-17T16:03:52.000Z",
                "matchedDate": None}]}
        if method.endswith("replaceOrders"):
            if not self.riprezzo_ok:
                return {"status": "FAILURE", "instructionReports": [
                    {"status": "FAILURE", "errorCode": "BET_TAKEN_OR_LAPSED"}]}
            return {"status": "SUCCESS", "instructionReports": [{
                "status": "SUCCESS",
                "cancelInstructionReport": {"status": "SUCCESS"},
                "placeInstructionReport": {
                    "status": "SUCCESS", "betId": "bet-2",
                    "orderStatus": "EXECUTION_COMPLETE" if self.matched_finale else "EXECUTABLE",
                    "sizeMatched": self.matched_finale,
                    "averagePriceMatched": params["instructions"][0]["newPrice"]},
            }]}
        raise AssertionError("metodo non previsto: %s" % method)

    # --- comodita' di lettura ---------------------------------------------
    def passi(self):
        """Solo i passi MUTANTI (place/cancel/replace): sono quelli che contano
        per i limiti Betfair e per le guardie money-critical."""
        return [c[0] for c in self.chiamate]

    def letture(self):
        """Le sole LETTURE (book e ``listCurrentOrders`` della verifica)."""
        return [c[0] for c in self.letture_raw]


@pytest.fixture
def client(monkeypatch):
    c = ClientFinto()

    def finto(fn):
        return fn(c)

    monkeypatch.setattr(M, "call_mutating", finto)
    # le LETTURE (book, listCurrentOrders) passano da ``call``: stesso finto,
    # nessuna rete.
    monkeypatch.setattr(M, "call", finto)
    return c


def piazza(**over):
    kw = dict(market_id="1.234", selection_id=1222344, price=8.0, size=1.35,
              event_id="1.999", side="back", customer_ref="mike-t7")
    kw.update(over)
    return M.place_submin_live(**kw)


# ---------------------------------------------------------------------------
# La sequenza, quando va bene
# ---------------------------------------------------------------------------
def test_un_importo_da_1_35_si_piazza_in_tre_passi(client, monkeypatch):
    client.matched_finale = 1.35
    res = piazza()
    assert client.passi() == ["place", "cancelOrders", "replaceOrders"]

    # 1. parcheggio: il MINIMO a una quota NON abbinabile, senza fill-or-kill
    _, _, park = client.chiamate[0]
    assert park["limitOrder"]["size"] == 2.00
    assert park["limitOrder"]["price"] == 1000.0
    assert park["limitOrder"]["persistenceType"] == "LAPSE"
    assert "timeInForce" not in park["limitOrder"], \
        "un fill-or-kill ucciderebbe il parcheggio prima di poterlo tagliare"

    # 2. taglio: resta esattamente l'importo voluto
    _, _, taglio = client.chiamate[1]
    assert taglio["betId"] == "bet-1"
    assert taglio["sizeReduction"] == pytest.approx(0.65)      # 2.00 - 1.35

    # 3. riprezzo alla quota reale
    _, _, ripr = client.chiamate[2]
    assert ripr["betId"] == "bet-1" and ripr["newPrice"] == 8.0

    assert res.ok and res.size_matched == 1.35 and res.bet_id == "bet-2"


def test_anche_cinque_centesimi(client):
    client.matched_finale = 0.05
    piazza(size=0.05)
    _, _, taglio = client.chiamate[1]
    assert taglio["sizeReduction"] == pytest.approx(1.95)
    assert client.passi() == ["place", "cancelOrders", "replaceOrders"]


def test_sul_lay_il_minimo_e_il_parcheggio_sono_altri(client):
    client.matched_finale = 0.20
    piazza(side="lay", size=0.20, price=1.48)
    _, _, park = client.chiamate[0]
    assert park["side"] == "LAY"
    assert park["limitOrder"]["size"] == 0.50 and park["limitOrder"]["price"] == 1.01
    _, _, taglio = client.chiamate[1]
    assert taglio["sizeReduction"] == pytest.approx(0.30)


def test_sopra_il_minimo_non_si_usa_nessun_trucco(client):
    """3,00 EUR sono piazzabili direttamente: una sola chiamata, ordine normale."""
    res = piazza(size=3.0)
    assert client.passi() == ["place"]
    _, _, istr = client.chiamate[0]
    assert istr["limitOrder"]["size"] == 3.0 and istr["limitOrder"]["price"] == 8.0
    assert istr["limitOrder"]["timeInForce"] == "FILL_OR_KILL"
    assert res.ok


def test_se_il_mercato_non_copre_l_ordine_viene_RITIRATO(client):
    """CERT. 13/09, difetto C-1 — il piu' pericoloso di tutti.

    Il riprezzo lascerebbe un ordine LIMITE a riposo alla quota richiesta. Chi
    chiama legge "size_matched = 0", lo interpreta come un rifiuto e marca la
    gamba annullata: ma l'ordine e' VIVO su Betfair, piu' tardi si abbina,
    nessuno lo contabilizza, e nel frattempo il bot rientra — posizione doppia
    con soldi veri. Quindi la parte non abbinata si RITIRA: o si abbina, o non
    esiste, esattamente come il place normale."""
    client.matched_finale = 0.0
    res = piazza()
    assert res.ok is False and res.size_matched == 0.0
    assert res.order_status == "LAPSED"
    assert client.passi() == ["place", "cancelOrders", "replaceOrders", "cancelOrders"]
    _, _, ritiro = client.chiamate[3]
    assert "sizeReduction" not in ritiro, "il ritiro del residuo deve essere TOTALE"


def test_un_fill_PARZIALE_tiene_la_parte_abbinata_e_ritira_il_resto(client):
    """Quello che si e' abbinato sono soldi veri e va contabilizzato; il residuo
    non deve restare sul book a insaputa del bot."""
    client.matched_finale = 0.80        # su 1,35 richiesti
    res = piazza()
    assert res.ok is True and res.size_matched == 0.80
    assert client.passi() == ["place", "cancelOrders", "replaceOrders", "cancelOrders"]


def test_se_si_abbina_TUTTO_non_si_ritira_niente(client):
    client.matched_finale = 1.35
    res = piazza()
    assert res.ok is True and res.size_matched == 1.35
    assert client.passi() == ["place", "cancelOrders", "replaceOrders"]


def test_chi_sa_seguire_l_ordine_puo_lasciarlo_a_riposo(client):
    """``fill_or_kill=False`` e' per un chiamante che ha il bet_id e lo
    riconcilia: l'ordine resta sul book e non viene ritirato."""
    client.matched_finale = 0.0
    res = piazza(fill_or_kill=False)
    assert res.ok is True and res.size_matched == 0.0
    assert client.passi() == ["place", "cancelOrders", "replaceOrders"]


# ---------------------------------------------------------------------------
# Le tre guardie money-critical
# ---------------------------------------------------------------------------
def test_guardia_il_parcheggio_non_deve_mai_abbinarsi(client):
    """A quota 1000 non c'e' controparte. Se si abbina siamo entrati a mercato in
    modo NON previsto: si ritira tutto, si solleva, nessun ritento."""
    client.matched_al_parcheggio = 2.0
    with pytest.raises(RuntimeError, match="ABORT"):
        piazza()
    assert client.passi() == ["place", "cancelOrders"]
    _, _, ritiro = client.chiamate[1]
    assert "sizeReduction" not in ritiro, "il ritiro deve essere TOTALE"


def test_guardia_senza_taglio_confermato_non_si_riprezza(client):
    """LA guardia piu' importante: se Betfair non conferma il taglio, un replace
    porterebbe la size PIENA del parcheggio (2,00) alla quota reale. Si ritira."""
    client.tagliato = 0.0          # il taglio non e' avvenuto
    with pytest.raises(RuntimeError, match="taglio non confermato"):
        piazza()
    assert "replaceOrders" not in client.passi()
    assert client.passi() == ["place", "cancelOrders", "cancelOrders"]


def test_guardia_taglio_parziale_non_basta(client):
    client.tagliato = 0.30         # chiesti 0,65
    with pytest.raises(RuntimeError, match="taglio non confermato"):
        piazza()
    assert "replaceOrders" not in client.passi()


def test_guardia_riprezzo_rifiutato_ritira_il_residuo(client):
    client.riprezzo_ok = False
    with pytest.raises(RuntimeError, match="riprezzo rifiutato"):
        piazza()
    assert client.passi() == ["place", "cancelOrders", "replaceOrders", "cancelOrders"]
    _, _, ritiro = client.chiamate[3]
    assert "sizeReduction" not in ritiro


def test_parcheggio_rifiutato_non_lascia_niente(client):
    client.place_ok = False
    with pytest.raises(RuntimeError, match="parcheggio rifiutato"):
        piazza()
    assert client.passi() == ["place"], "niente da ritirare: l'ordine non esiste"


# ---------------------------------------------------------------------------
# Validazioni prima di toccare la rete
# ---------------------------------------------------------------------------
def test_sotto_il_centesimo_non_esiste_nemmeno_col_trucco(client):
    with pytest.raises(ValueError, match="minimo assoluto"):
        piazza(size=0.004)
    assert client.chiamate == []


def test_size_non_numerica_o_prezzo_assurdo(client):
    """Validazioni PRIMA di qualunque chiamata di rete: nessun ordine reale nasce
    da un numero rotto. (Un prezzo fuori scala viene CLAMPATO dal ladder, come
    nel place normale: 99999 diventa 1000, il massimo di Betfair.)"""
    with pytest.raises(ValueError, match="non numerica"):
        piazza(size="tanto")
    with pytest.raises(ValueError):
        piazza(price=float("nan"))
    with pytest.raises(ValueError, match="side non valido"):
        piazza(side="sopra")
    with pytest.raises(ValueError, match="non piazzabile"):
        piazza(size=float("nan"))
    assert client.chiamate == []


# ---------------------------------------------------------------------------
# Il ritiro finale NON puo' fallire in silenzio (code review 13/09)
# ---------------------------------------------------------------------------
def test_se_il_ritiro_finale_fallisce_si_solleva(client, monkeypatch):
    """CRITICO della code review. Qui il riprezzo e' RIUSCITO: senza ritiro
    resta un ordine vivo a un prezzo REALE, non piu' al parcheggio. Dichiararlo
    annullato vorrebbe dire non contabilizzarlo mai — e nel frattempo il bot
    rientra: posizione doppia con soldi veri.

    Se il ritiro fallisce si SOLLEVA, cosi' la gamba finisce in riconciliazione
    e l'ordine viene cercato su Betfair invece di essere dato per morto.
    """
    client.matched_finale = 0.0
    vero_cancel = M._submin_cancel

    def cancel_che_fallisce(market_id, bet_id, size_reduction):
        if size_reduction is None:        # e' il RITIRO totale
            raise RuntimeError("rete caduta")
        return vero_cancel(market_id, bet_id, size_reduction)

    monkeypatch.setattr(M, "_submin_cancel", cancel_che_fallisce)
    with pytest.raises(RuntimeError, match="ritiro del residuo FALLITO"):
        piazza()


def test_un_ritiro_best_effort_non_copre_un_errore_gia_in_corso(client, monkeypatch):
    """Quando si sta gia' propagando un errore il ritiro resta best-effort: il
    chiamante fallira' comunque e la gamba andra' in riconciliazione, quindi un
    ritiro fallito in piu' non cambia l'esito — e non deve nascondere il motivo
    vero del fallimento."""
    client.tagliato = 0.0                  # il taglio non viene confermato
    vero_cancel = M._submin_cancel

    def cancel_che_fallisce(market_id, bet_id, size_reduction):
        if size_reduction is None:
            raise RuntimeError("rete caduta")
        return vero_cancel(market_id, bet_id, size_reduction)

    monkeypatch.setattr(M, "_submin_cancel", cancel_che_fallisce)
    with pytest.raises(RuntimeError, match="taglio non confermato"):
        piazza()


# ---------------------------------------------------------------------------
# 17/09 — IL RITIRO NON CONFERMATO VALE IGNOTO (money-critical)
# ---------------------------------------------------------------------------
def test_ritiro_che_risponde_FAILURE_non_e_un_rifiuto_certo(client):
    """Betfair risponde FAILURE al ritiro: l'ordine puo' essere ancora VIVO.

    Dichiararlo annullato sarebbe il difetto del 15/09 con un'altra faccia: la
    gamba si abbina piu' tardi e nessuno la contabilizza. L'esito deve restare
    IGNOTO (``RuntimeError``), non un rifiuto CERTO (``PlaceRifiutato``).
    """
    client.riprezzo_ok = False       # il replace viene rifiutato
    client.ritiro_ok = False         # e il ritiro NON e' confermato
    with pytest.raises(RuntimeError) as ex:
        piazza()
    assert not isinstance(ex.value, M.PlaceRifiutato),         "ritiro non confermato: esito IGNOTO, mai rifiuto certo"
    assert "ordine forse vivo" in str(ex.value)


def test_verifica_del_taglio_non_confermata_col_ritiro_che_SOLLEVA(client, monkeypatch):
    """La rilettura non conferma il taglio E il ritiro cade in rete: IGNOTO."""
    client.residuo_letto = 2.00      # il taglio non risulta avvenuto
    vero = M._submin_cancel

    def cancel(market_id, bet_id, size_reduction):
        if size_reduction is None:
            raise RuntimeError("rete caduta sul ritiro")
        return vero(market_id, bet_id, size_reduction)

    monkeypatch.setattr(M, "_submin_cancel", cancel)
    with pytest.raises(RuntimeError) as ex:
        piazza()
    assert not isinstance(ex.value, M.PlaceRifiutato)
    assert "RITIRO FALLITO" in str(ex.value)


def test_ritiro_confermato_resta_un_rifiuto_CERTO(client):
    """Il controcaso: ritiro confermato -> la riga si chiude in 'error'."""
    client.riprezzo_ok = False
    client.ritiro_ok = True
    with pytest.raises(M.PlaceRifiutato) as ex:
        piazza()
    assert ex.value.error_code == "BET_TAKEN_OR_LAPSED"
