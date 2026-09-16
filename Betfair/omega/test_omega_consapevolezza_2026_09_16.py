# -*- coding: utf-8 -*-
"""FALSIFICAZIONE DELLA FAMIGLIA K — i cinque difetti del 15/09, uno per uno.

Reperto portato da Mike (addendum del coordinatore, 16/09; catalogo §7 punti 36-37
di `PROCESSO_STANDARD_BOT.md`): i controlli che guardano solo la DECISIONE non
vedono quei difetti, perche' non stanno nella decisione — stanno nel giro dopo,
quando il bot rilegge il suo ordine e non si riconosce.

Qui ogni difetto viene RIPRODOTTO nella forma esatta che avrebbe sulle righe e
sugli ordini, e si pretende che il controllo corrispondente diventi ROSSO. Un
controllo che non sa diventare rosso non certifica.

COME E' STATA FATTA LA FALSIFICAZIONE, e perche' non col metodo dell'md5.
Il metodo del catalogo e' rompere `omega_service.py` / `omega_market.py`, far
girare il replay, vedere i controlli rossi e ripristinare verificando l'md5. **Non
si poteva fare stasera**: `omega_service.py` e' in mano a un altro delegato in
questo stesso momento (riconciliazione, chiusure dell'utente, aggregati) e
riscriverlo, anche per un secondo, avrebbe potuto cancellargli il lavoro. La
falsificazione e' quindi fatta al livello sotto, che e' altrettanto stringente e
piu' sicuro: si costruisce l'ARTEFATTO che il difetto produrrebbe — la riga e
l'ordine, con le chiavi VERE del banco (`MercatoFlumine._riga`) e le chiavi VERE
delle righe (`omega_trades`) — e si verifica che il controllo lo prenda.
Dichiarato come divergenza dal metodo, non nascosto.

⊘ NON FALSIFICABILE QUI: il place-and-trim (il residuo tagliato dopo un fill
parziale) non passa dal banco perche' il banco non simula un secondo ordine di
trim sullo stesso ref; K6 si limita quindi a pretendere che il residuo sia
DICHIARATO, che e' la parte verificabile.
"""
from __future__ import annotations

import pytest

from Betfair.omega import certificazione as CERT
from Betfair.omega import omega_service as S


# ---------------------------------------------------------------------------
# I FINTI PARLANO COME IL VERO.
# `_riga` del banco (`Betfair/stream/backtest/banco_comune.py:760-784`) produce
# queste chiavi, tutte snake_case. Se un domani il banco ne cambiasse una, il
# test qui sotto (`test_le_chiavi_dei_finti_sono_quelle_del_banco`) diventa rosso
# prima che il controllo inizi a guardare la chiave sbagliata.
# ---------------------------------------------------------------------------
def _ordine(ref="omega-t1", *, matched=1.0, medio=65.0, stato="EXECUTION_COMPLETE",
            bet_id="B1", residuo=0.0, ref_riletto=None):
    return {
        "customer_order_ref": ref if ref_riletto is None else ref_riletto,
        "bet_id": bet_id,
        "market_id": "1.2",
        "selection_id": 101,
        "side": "LAY",
        "status": stato,
        "price": medio,
        "size": matched,
        "size_matched": matched,
        "size_remaining": residuo,
        "avg_price_matched": medio,
        "average_price_matched": medio,
        "size_requested": matched + residuo,
    }


def _riga(id_=1, *, size=1.0, price=65.0, status="open", bet_id="B1", side="lay",
          meta=None, closes=None):
    return {
        "id": id_, "event_id": "35760084", "market_id": "1.2", "selection_id": 101,
        "runner_name": "3 - 3", "side": side, "price": price, "size": size,
        "liability": round(size * (price - 1.0), 2), "status": status,
        "bet_id": bet_id, "phase": "ft_cs", "closes_trade_id": closes,
        "meta": dict(meta or {}),
    }


def _codici(viol):
    return {v.codice for v in viol}


def test_le_chiavi_dei_finti_sono_quelle_del_banco():
    """Memoria del 15/09: i finti scritti in camelCase avevano CERTIFICATO il bug
    e sono usciti 32 ordini veri in loop. Qui si controlla che le chiavi dei finti
    siano davvero quelle che il banco produce."""
    from Betfair.stream.backtest import banco_comune as B
    import inspect
    sorgente = inspect.getsource(B.MercatoFlumine._riga)
    for chiave in ("customer_order_ref", "size_matched", "avg_price_matched",
                   "size_remaining", "bet_id", "status"):
        assert f'"{chiave}"' in sorgente, chiave


# ---------------------------------------------------------------------------
# I CINQUE DIFETTI DEL 15/09
# ---------------------------------------------------------------------------
def test_sano_nessuna_violazione():
    """Il caso in regola: riga e ordine dicono la stessa cosa."""
    viol = CERT.verifica_consapevolezza([_riga()], {"omega-t1": _ordine()}, set())
    assert not viol, [str(v) for v in viol]


def test_difetto_1_ref_camelcase_il_ref_non_si_rilegge():
    """`customerOrderRef` scritto, `customer_order_ref` riletto: l'ordine esiste
    ma il bot non lo ritrova piu'. E' il difetto che il 15/09 ha fatto uscire 32
    green-up veri in loop su Mike."""
    o = _ordine()
    o.pop("customer_order_ref")
    o["customerOrderRef"] = "omega-t1"     # la grafia sbagliata, quella vera
    viol = CERT.verifica_consapevolezza([_riga()], {"omega-t1": o}, set())
    assert "K3" in _codici(viol)


def test_difetto_1bis_il_ref_riletto_e_un_altro():
    o = _ordine(ref_riletto="qualcun-altro")
    viol = CERT.verifica_consapevolezza([_riga()], {"omega-t1": o}, set())
    assert "K3" in _codici(viol)


def test_difetto_2_res_ok_ignorato_la_riga_resta_viva():
    """Betfair ha RIFIUTATO: nessun ordine esiste. Se `res.ok` non viene letto, la
    riga resta `open` e il bot crede di avere una posizione che non ha."""
    viol = CERT.verifica_consapevolezza([_riga(status="open")], {}, {"omega-t1"})
    assert "K2" in _codici(viol)
    # e nel caso sano (riga chiusa dopo il rifiuto) K2 tace
    sane = CERT.verifica_consapevolezza([_riga(status="error")], {}, {"omega-t1"})
    assert "K2" not in _codici(sane)


def test_difetto_3_avg_price_invece_di_avg_price_matched():
    """Il bot scrive il prezzo CHIESTO (65) e il mercato ha abbinato a 62."""
    viol = CERT.verifica_consapevolezza([_riga(price=65.0)],
                                        {"omega-t1": _ordine(medio=62.0)}, set())
    assert "K1" in _codici(viol)


def test_difetto_3bis_abbinato_diverso_da_quello_creduto():
    viol = CERT.verifica_consapevolezza([_riga(size=1.0)],
                                        {"omega-t1": _ordine(matched=0.4)}, set())
    assert "K1" in _codici(viol)


def test_un_ordine_ancora_vivo_non_e_una_violazione():
    """EXECUTABLE = ancora sul book: il bot lo rilegge alla SUA cadenza e non
    puo' essere accusato di non sapere gia' com'e' finito."""
    viol = CERT.verifica_consapevolezza(
        [_riga(size=0.0)], {"omega-t1": _ordine(matched=1.0, stato="EXECUTABLE")}, set())
    assert "K1" not in _codici(viol)


def test_k1_non_accusa_una_riga_gia_dichiarata_in_errore():
    """FALSO POSITIVO TROVATO DAL BANCO (16/09, scenario `cashout-globale`): una
    riga di chiusura finita in 'error' dopo un `place_rifiutato` porta in `size`
    la size CHIESTA, non un abbinamento. Accusarla vuol dire accusare il bot di
    aver detto il contrario di quello che ha detto: 119 violazioni false."""
    r = _riga(id_=2, side="back", size=7.01, price=75.0, status="error",
              bet_id=None, closes=1)
    assert "K1" not in _codici(CERT.verifica_consapevolezza(
        [r], {"omega-t2": _ordine(ref="omega-t2", matched=0.0, medio=75.0)}, set()))
    # ma una riga APERTA con lo stesso scarto viene presa
    aperta = _riga(id_=2, side="lay", size=7.01, price=75.0, status="open")
    assert "K1" in _codici(CERT.verifica_consapevolezza(
        [aperta], {"omega-t2": _ordine(ref="omega-t2", matched=0.0, medio=75.0)}, set()))


def test_k5_non_accusa_il_paper_che_non_ha_ordini():
    """FALSO POSITIVO TROVATO DAL BANCO (16/09): nello scenario `paper` il fill
    viene da `omega_engine.paper_fill` — uno snapshot, non un ordine — quindi la
    riga e' aperta SENZA `bet_id` e a mercato non c'e' niente. E' la divergenza
    P4 dichiarata, non un difetto: accusarla voleva dire 242 violazioni false in
    un giro solo. K5 accusa solo chi DICHIARA un bet_id."""
    r = _riga(bet_id=None, status="open")
    assert "K5" not in _codici(CERT.verifica_consapevolezza([r], {}, set()))
    # ma appena la riga dichiara un bet_id, la posizione fantasma si vede
    assert "K5" in _codici(CERT.verifica_consapevolezza(
        [_riga(bet_id="B1", status="open")], {}, set()))


def test_difetto_4_riconciliazione_con_un_ref_diverso():
    """La riga e' aperta con `bet_id` B1, ma a mercato non esiste nessun ordine
    con i suoi riferimenti: la riconciliazione non lo ritroverebbe mai."""
    viol = CERT.verifica_consapevolezza([_riga(bet_id="B1")],
                                        {"un-altro-ref": _ordine(ref="un-altro-ref",
                                                                 bet_id="B9")}, set())
    assert "K5" in _codici(viol)


def test_il_dubbio_dichiarato_non_e_una_violazione():
    """`meta.reconciling` = «non so com'e' andata», ed e' la cosa giusta da fare:
    K1 e K5 tacciono, perche' il bot non sta affermando niente di falso."""
    r = _riga(bet_id="B1", meta={"reconciling": True})
    viol = CERT.verifica_consapevolezza([r], {}, set())
    assert not ({"K1", "K5"} & _codici(viol))


def test_difetto_5_closes_trade_id_solo_nel_meta():
    """La riga di chiusura (un back) deve dire NELLA COLONNA quale apertura
    chiude: se resta nel meta, nessuna query lo trova."""
    r = _riga(id_=2, side="back", closes=None, meta={"closes_trade_id": 1})
    viol = CERT.verifica_consapevolezza([r], {"omega-t2": _ordine(ref="omega-t2")}, set())
    assert "K4" in _codici(viol)
    sana = _riga(id_=2, side="back", closes=1)
    assert "K4" not in _codici(CERT.verifica_consapevolezza(
        [sana], {"omega-t2": _ordine(ref="omega-t2")}, set()))


def test_k6_il_residuo_non_dichiarato():
    """Chiesti 5, abbinati 2, e del residuo non parla nessuno."""
    r = _riga(size=2.0, meta={"requested_size": 5.0})
    viol = CERT.verifica_consapevolezza(
        [r], {"omega-t1": _ordine(matched=2.0, residuo=3.0)}, set())
    assert "K6" in _codici(viol)
    r2 = _riga(size=2.0, meta={"requested_size": 5.0, "size_remaining": 3.0})
    assert "K6" not in _codici(CERT.verifica_consapevolezza(
        [r2], {"omega-t1": _ordine(matched=2.0, residuo=3.0)}, set()))


def test_nessun_controllo_k_esplode_su_dati_vuoti():
    for righe, ordini in (([], {}), ([_riga()], {}), ([], {"x": _ordine()}),
                          ([{}], {"x": {}})):
        viol = CERT.verifica_consapevolezza(righe, ordini, set())
        assert not [v for v in viol if v.codice.endswith("-ERRORE")], (righe, ordini)


def test_i_controlli_k_entrano_nel_referto():
    """Se K restasse fuori da `elenco_controlli`, un K mai sollecitato passerebbe
    per inesistente invece che per «non lo so»: e' il buco che il referto esiste
    per chiudere."""
    codici = {c for c, _r in CERT.elenco_controlli()}
    for k in ("K1", "K2", "K3", "K4", "K5", "K6"):
        assert k in codici, k
    assert dict(CERT.mai_sollecitati({}))  # con zero solleciti, tutti «non lo so»
    assert "K1" in {c for c, _r in CERT.mai_sollecitati({})}


# ---------------------------------------------------------------------------
# LE CACHE DI PROCESSO — azzeramento ESPLICITO, e nessuna che sfugga
# ---------------------------------------------------------------------------
# In produzione l'azzeramento e' un ELENCO scritto a mano
# (`omega_service.svuota_le_cache`), non un `dir()`: una cancellazione fatta per
# riflessione butterebbe via anche cose che non sono cache. Qui, nel TEST, si usa
# invece la riflessione — ed e' il posto giusto: serve ad accorgersi che qualcuno
# ha aggiunto una cache NUOVA e si e' scordato di metterla nell'elenco. Se non ci
# fosse questo test, una cache dimenticata farebbe passare lo stato di uno
# scenario dentro lo scenario successivo (il reperto dell'addendum: la pool non
# azzerava le cache fra scenari, e i controlli di uno scenario venivano
# sollecitati meno del dovuto).
_PREFISSI_CACHE = ("_CACHE_", "_ULTIMI_", "_ULTIME_", "_FASE_ESEGUITA",
                   "_EVENTI_CHIUSI", "_CHIUSURA_IN_ATTESA", "_DA_ANNULLARE")


def _stato_cache():
    fuori = {}
    for nome in dir(S):
        if not nome.startswith(_PREFISSI_CACHE):
            continue
        val = getattr(S, nome)
        if isinstance(val, dict):
            fuori[nome] = len(val)
        elif isinstance(val, (set, list)):
            fuori[nome] = len(val)
        elif hasattr(val, "svuota"):
            fuori[nome] = "oggetto_con_svuota"
        else:
            fuori[nome] = val
    return fuori


def test_ogni_cache_di_processo_e_nell_elenco_di_svuota_le_cache():
    """Ogni nome che SEMBRA una cache dev'essere citato in `svuota_le_cache`."""
    import inspect
    sorgente = inspect.getsource(S.svuota_le_cache)
    mancanti = [n for n in _stato_cache() if n not in sorgente]
    assert not mancanti, (
        "cache di processo non azzerate da `svuota_le_cache` (passerebbero da uno "
        f"scenario all'altro): {sorted(mancanti)}")


def test_svuota_le_cache_svuota_davvero():
    """FALSIFICAZIONE: si sporca ogni cache e si pretende che torni vuota."""
    sporcate = []
    for nome in _stato_cache():
        val = getattr(S, nome)
        if isinstance(val, dict):
            val["__prova__"] = 1
            sporcate.append(nome)
        elif isinstance(val, set):
            val.add("__prova__")
            sporcate.append(nome)
        elif isinstance(val, list):
            val.append("__prova__")
            sporcate.append(nome)
    assert sporcate, "nessuna cache trovata: il test non proverebbe niente"
    S.svuota_le_cache()
    rimaste = []
    for nome in sporcate:
        val = getattr(S, nome)
        if len(val) != 0:
            rimaste.append(nome)
    assert not rimaste, f"cache NON svuotate: {rimaste}"
