"""riconciliazione.py - il riconciliatore IN OMBRA (comparto C, W1-C2, tappa T11, 09/10/2026).

Scopo (``05_PIANO_DI_MIGRAZIONE.md`` T11; scheda C par. 1.6 e par. 6 passo 2):
confrontare il CONTO (lo stream degli ordini del conto, cioe' il libro; o
``listCurrentOrders``), lo SPECCHIO (righe di ``betfair_live_orders`` passate
come DATI), il BLOTTER di flumine (oggetti veri) e il DIARIO del motore (righe
``inviato``/``ordine``/``esito``) e produrre le DIVERGENZE per ``bet_id``/ref,
ciascuna col suo motivo, piu' ``StatoOrdine`` e ``PosizioneConto`` dal conto.
Gira ACCANTO ai nove riconciliatori di oggi (R1..R9): NON SCRIVE NIENTE (ne' DB,
ne' specchio, ne' alert, ne' file), non annulla ne' piazza.

Regole riprese dal codice di oggi (stessi esiti, provati nei test di parita'):
  * R1 ``reconcile_worker._reconcile_orders``: ordine sul conto e non nello
    specchio -> R1 lo copia (``source='account'`` o ``bot:<csr>``), salvo i bot
    con tabella propria (``_REF_BOT_CON_TABELLA``); entrambi presenti con
    abbinato diverso oltre 0,01 o stato diverso -> R1 corregge lo specchio;
    riga dello specchio ``EXECUTABLE`` assente dal conto (escluse ``bot:*`` e
    ``account``) -> R1 avvisa dal SECONDO giro consecutivo;
  * R2 ``motore_ordini.riprendi_da_diario``: comandi ``inviato`` senza
    ``esito``/``ripresa`` -> ritrovato (customerOrderRef sul conto),
    non_trovato, perso_paper, mai_inviato_place.
In piu' (diagnostica additiva, mai un'azione): attribuzione dell'autore,
confronto col blotter, righe dello specchio senza ``bet_id`` (esito ignoto).

Entrate: ``OrdineDalConto`` del conto (UN modo), righe dello specchio, ordini
del blotter, righe del diario. Uscite: ``RefertoOmbra``. Interruttore previsto
(ondata 2): ``ARCH_RICONCILIA=ombra``.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import (Any, Dict, FrozenSet, Iterable, List, Literal, Mapping, Optional,
                    Sequence, Tuple)

from Betfair.nucleo.betfair.contratto import OrdineDalConto
from Betfair.nucleo.comuni import Modo
from Betfair.nucleo.ordini import attribuzione as attr
from Betfair.nucleo.ordini import libro_conto, pnl_mercato
from Betfair.nucleo.ordini.contratto import OrdineConto, PosizioneConto, StatoOrdine

logger = logging.getLogger(__name__)

TipoDivergenza = Literal[
    "esterno_dal_sito",          # sul conto, non nello specchio, autore sito (R1: copia + WARN)
    "conto_senza_specchio",      # sul conto, non nello specchio, autore nostro (R1: copia)
    "bot_con_tabella",           # sul conto, non nello specchio, bot REST con tabella (R1: salta)
    "numeri_diversi",            # abbinato diverso oltre la tolleranza (R1: corregge)
    "stato_diverso",             # stato diverso (R1: corregge)
    "specchio_senza_conto",      # EXECUTABLE nello specchio, assente dal conto (R1: WARN al 2o giro)
    "specchio_senza_bet_id",     # riga dello specchio senza bet_id: esito ignoto (diagnostica)
    "blotter_diverso",           # blotter flumine e conto non concordano (diagnostica)
    "blotter_senza_conto",       # ordine vivo nel blotter, assente dal conto (diagnostica)
    "in_volo_ritrovato",         # R2: comando in volo, ordine sul conto
    "in_volo_non_trovato",       # R2: esito IGNOTO, ordine non sul conto
    "in_volo_perso_paper",       # R2: ordine simulato perso col riavvio
    "in_volo_senza_place",       # R2: nessuna riga 'ordine' (cancel/replace: esito ignoto)
    "attribuzione_in_conflitto",  # due fonti dicono due bot diversi
    "seme_non_fatto",           # conto senza i completi di prima: niente specchio_senza_conto
    "in_volo_da_verificare",    # R2 non trovato ma il conto e' senza seme: non si sa
]
Gravita = Literal["info", "avviso", "grave"]

#: tolleranza di R1 sull'abbinato (``reconcile_worker._reconcile_orders``:
#: ``abs(mir_matched - acc_matched) <= 0.01``); il test di parita' la prova
TOLLERANZA_ABBINATO = 0.01
#: giri consecutivi dopo cui R1 avvisa per una riga dello specchio assente dal
#: conto (``reconcile_worker._MISSING_SEEN[...] >= 2``)
GIRI_AVVISO_MANCANTE = 2

#: fase del motore (``motore_ordini.fase_da_riga``) -> ``FaseOrdine`` del contratto
FASE_CONTRATTO: Mapping[str, str] = {
    "accettato_betfair": "accettato", "abbinato_parziale": "parziale",
    "abbinato": "abbinato", "annullato": "annullato", "scaduto": "scaduto",
    "rifiutato": "rifiutato", "inviato": "ignoto",
}


@dataclass(frozen=True)
class Divergenza:
    tipo: TipoDivergenza
    gravita: Gravita
    bet_id: Optional[str]
    ref: Optional[str]
    motivo: str
    dettagli: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InVolo:
    """Un comando del diario senza esito (R2), con il suo esito ricostruito."""

    ref: str
    modo: Optional[str]
    cors: Tuple[str, ...]
    esito: Literal["ritrovato", "non_trovato", "perso_paper", "mai_inviato_place"]
    bet_ids: Tuple[str, ...]


@dataclass(frozen=True)
class RefertoOmbra:
    giro: int
    modo: Modo
    istante_ms: int
    divergenze: Tuple[Divergenza, ...]
    stati: Mapping[str, StatoOrdine]
    posizioni: Tuple[PosizioneConto, ...]
    in_volo: Tuple[InVolo, ...]
    conti: Mapping[str, int]

    def per_tipo(self, tipo: str) -> Tuple[Divergenza, ...]:
        return tuple(d for d in self.divergenze if d.tipo == tipo)


def _ref_bot_con_tabella() -> FrozenSet[str]:
    from Betfair.stream.reconcile_worker import _REF_BOT_CON_TABELLA

    return frozenset(_REF_BOT_CON_TABELLA)


def _f0(v: Any) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _testo(v: Any) -> str:
    return str(v).strip() if v is not None else ""


# ---------------------------------------------------------------------------
# R2: i comandi in volo dal diario
# ---------------------------------------------------------------------------
def in_volo_dal_diario(righe: Iterable[Mapping[str, Any]],
                       conto_per_cor: Mapping[str, OrdineDalConto]) -> Tuple[InVolo, ...]:
    """Le stesse regole di ``motore_ordini.riprendi_da_diario`` (righe
    ``inviato`` senza ``esito``/``ripresa``; ``ordine`` porta il
    customerOrderRef VERO), ma come lettura: il conto e' il libro, non una
    chiamata a Betfair, e niente viene scritto."""
    inviati: Dict[str, Mapping[str, Any]] = {}
    chiusi = set()
    cor_per_ref: Dict[str, List[str]] = {}
    for rec in righe:
        ref = rec.get("ref")
        if not isinstance(ref, str):
            continue
        tipo = rec.get("tipo")
        if tipo == "inviato":
            inviati[ref] = rec
        elif tipo in ("esito", "ripresa"):
            chiusi.add(ref)
        elif tipo == "ordine" and rec.get("cor"):
            cor_per_ref.setdefault(ref, []).append(str(rec["cor"]))
    out: List[InVolo] = []
    for ref in [r for r in inviati if r not in chiusi]:
        modo = inviati[ref].get("mode")
        cors = tuple(cor_per_ref.get(ref, []))
        trovati = tuple(str(conto_per_cor[c].bet_id) for c in cors if c in conto_per_cor)
        if modo != "live":
            esito = "perso_paper"
        elif trovati:
            esito = "ritrovato"
        elif cors:
            esito = "non_trovato"
        else:
            esito = "mai_inviato_place"
        out.append(InVolo(ref, modo, cors, esito, trovati))  # type: ignore[arg-type]
    return tuple(out)


# ---------------------------------------------------------------------------
# il confronto
# ---------------------------------------------------------------------------
def stato_dal_conto(o: OrdineDalConto) -> StatoOrdine:
    """``StatoOrdine`` dell'ordine come lo dice il conto (``ref`` = il
    customerOrderRef, o il bet_id se manca)."""
    fase = FASE_CONTRATTO.get(libro_conto.fase_dell_ordine(o), "ignoto")
    return StatoOrdine(ref=_testo(o.customer_order_ref) or str(o.bet_id), bet_id=str(o.bet_id),
                       fase=fase, abbinato=float(o.abbinato),  # type: ignore[arg-type]
                       residuo=float(o.residuo), prezzo_medio=o.prezzo_medio, ultimo_seq=0)


def _stato_flumine(ordine: Any) -> str:
    st = getattr(ordine, "status", None)
    return str(getattr(st, "name", None) or getattr(st, "value", None) or st or "")


class RiconciliatoreOmbra:
    """Il riconciliatore in ombra di UN modo. Tiene in memoria SOLO i giri
    consecutivi delle righe dello specchio mancanti dal conto (come
    ``reconcile_worker._MISSING_SEEN``) e il numero del giro. Thread-safe."""

    def __init__(self, *, modo: Modo, regole: Optional[attr.RegoleAttribuzione] = None) -> None:
        if modo not in libro_conto.MODI:
            raise ValueError(f"modo non ammesso: {modo!r}")
        self.modo: Modo = modo
        self._regole = regole
        self._lock = threading.Lock()
        self._mancanti: Dict[str, int] = {}
        self._giro = 0

    def giro(self, conto: Iterable[OrdineDalConto], specchio: Iterable[Mapping[str, Any]], *,
             blotter: Optional[Iterable[Any]] = None,
             diario: Optional[Iterable[Mapping[str, Any]]] = None,
             indizi: Optional[Mapping[str, Sequence[attr.Indizio]]] = None,
             istante_ms: int = 0, conto_completo: bool = True) -> RefertoOmbra:
        """UN confronto. ``conto`` = TUTTI gli ordini del conto del modo (lo
        stream o ``listCurrentOrders``); ``specchio`` = righe con le colonne di
        ``betfair_live_orders`` (si tengono solo quelle con ``mode`` = modo).

        ``conto_completo=False`` (revisione 09/10, G3: libro senza seme, cioe'
        ``not LibroConto.seme_fatto()``): lo stream non ha gli ordini gia'
        completi di prima della sottoscrizione, quindi NIENTE
        ``specchio_senza_conto`` (e i giri consecutivi non avanzano) e un R2
        "non trovato" diventa ``in_volo_da_verificare``."""
        regole = self._regole or attr.regole_di_oggi()
        per_bet = {str(o.bet_id): o for o in conto}
        righe = [r for r in specchio if _testo(r.get("mode")) == self.modo]
        div: List[Divergenza] = []
        attribuzioni = {b: attr.attribuisci(o, (indizi or {}).get(b, ()), regole)
                        for b, o in per_bet.items()}
        div += self._conto_contro_specchio(per_bet, righe, attribuzioni)
        with self._lock:
            self._giro += 1
            giro = self._giro
            if conto_completo:
                div += self._specchio_contro_conto(per_bet, righe)
            else:
                div.append(Divergenza("seme_non_fatto", "info", None, None,
                                      "conto senza seme da listCurrentOrders: lo specchio "
                                      "non si confronta con le assenze dal conto",
                                      {"righe_specchio": len(righe)}))
        if blotter is not None:
            div += _blotter_contro_conto(per_bet, blotter)
        cor = {_testo(o.customer_order_ref): o for o in per_bet.values()
               if _testo(o.customer_order_ref)}
        volo = in_volo_dal_diario(diario or (), cor)
        div += [_divergenza_in_volo(v, conto_completo) for v in volo]
        for b, a in sorted(attribuzioni.items()):
            if a.conflitto:
                div.append(Divergenza("attribuzione_in_conflitto", "avviso", b,
                                      per_bet[b].customer_order_ref, a.conflitto,
                                      {"autore": a.autore, "motivo": a.motivo}))
        stati = {b: stato_dal_conto(o) for b, o in sorted(per_bet.items())}
        posizioni, saltate = _posizioni(self.modo, per_bet, attribuzioni)
        conti: Dict[str, int] = {"conto": len(per_bet), "specchio": len(righe),
                                 "posizioni_a_linee_saltate": saltate}
        for d in div:
            conti[d.tipo] = conti.get(d.tipo, 0) + 1
        return RefertoOmbra(giro, self.modo, int(istante_ms), tuple(div), stati,
                            posizioni, volo, conti)

    @staticmethod
    def _conto_contro_specchio(per_bet: Mapping[str, OrdineDalConto],
                               righe: Sequence[Mapping[str, Any]],
                               attribuzioni: Mapping[str, attr.Attribuzione]) -> List[Divergenza]:
        bot_tabella = _ref_bot_con_tabella()
        per_riga = {_testo(r.get("bet_id")): r for r in righe if _testo(r.get("bet_id"))}
        out: List[Divergenza] = []
        for b, o in sorted(per_bet.items()):
            a = attribuzioni[b]
            riga = per_riga.get(b)
            if riga is None:
                csr = _testo(o.customer_strategy_ref).lower()
                det = {"autore": a.autore, "motivo": a.motivo, "market_id": o.market_id,
                       "csr": o.customer_strategy_ref, "cor": o.customer_order_ref}
                if csr and csr in bot_tabella:
                    out.append(Divergenza("bot_con_tabella", "info", b, o.customer_order_ref,
                                          "bot REST con tabella propria: lo specchio non lo "
                                          "copia (R1)", det))
                elif a.autore == attr.SITO:
                    out.append(Divergenza("esterno_dal_sito", "avviso", b, None,
                                          "ordine ESTERNO dal sito: sul conto, non nello "
                                          "specchio", det))
                else:
                    out.append(Divergenza("conto_senza_specchio", "avviso", b,
                                          o.customer_order_ref,
                                          f"ordine di {a.autore} sul conto ma non nello specchio",
                                          det))
                continue
            sm_s = _f0(riga.get("size_matched"))
            st_s = riga.get("status")
            det = {"specchio": {"size_matched": sm_s, "status": st_s,
                                "source": riga.get("source")},
                   "conto": {"size_matched": o.abbinato, "status": o.stato,
                             "size_cancelled": o.annullato, "size_lapsed": o.scaduto,
                             "fase": libro_conto.fase_dell_ordine(o)},
                   "autore": a.autore}
            if abs(sm_s - float(o.abbinato)) > TOLLERANZA_ABBINATO:
                out.append(Divergenza("numeri_diversi", "avviso", b,
                                      _testo(riga.get("client_order_ref")) or None,
                                      f"abbinato specchio {sm_s} contro conto {o.abbinato}", det))
            elif st_s != o.stato:
                out.append(Divergenza("stato_diverso", "avviso", b,
                                      _testo(riga.get("client_order_ref")) or None,
                                      f"stato specchio {st_s} contro conto {o.stato}", det))
        return out

    def _specchio_contro_conto(self, per_bet: Mapping[str, OrdineDalConto],
                               righe: Sequence[Mapping[str, Any]]) -> List[Divergenza]:
        """Sotto il lucchetto: aggiorna i giri consecutivi dei mancanti."""
        out: List[Divergenza] = []
        ora: Dict[str, Mapping[str, Any]] = {}
        for r in righe:
            b = _testo(r.get("bet_id"))
            src = _testo(r.get("source"))
            if not b:
                if r.get("status") in (None, "", "PENDING"):
                    out.append(Divergenza("specchio_senza_bet_id", "info", None,
                                          _testo(r.get("client_order_ref")) or None,
                                          "riga dello specchio senza bet_id: esito ignoto",
                                          {"status": r.get("status"), "source": src}))
                continue
            if (r.get("status") == "EXECUTABLE" and b not in per_bet
                    and not src.startswith("bot:") and src != "account"):
                ora[b] = r
        for b in list(self._mancanti):
            if b not in ora:
                self._mancanti.pop(b, None)
        for b, r in sorted(ora.items()):
            self._mancanti[b] = self._mancanti.get(b, 0) + 1
            n = self._mancanti[b]
            out.append(Divergenza(
                "specchio_senza_conto", "avviso" if n >= GIRI_AVVISO_MANCANTE else "info", b,
                _testo(r.get("client_order_ref")) or None,
                f"EXECUTABLE nello specchio, assente dal conto da {n} giri",
                {"giri": n, "source": r.get("source")}))
        return out


def _blotter_contro_conto(per_bet: Mapping[str, OrdineDalConto],
                          blotter: Iterable[Any]) -> List[Divergenza]:
    out: List[Divergenza] = []
    for ordine in blotter:
        b = _testo(getattr(ordine, "bet_id", None))
        if not b:
            continue
        sm = _f0(getattr(ordine, "size_matched", None))
        st = _stato_flumine(ordine)
        o = per_bet.get(b)
        if o is None:
            if st in ("EXECUTABLE", "PENDING", "CANCELLING", "UPDATING", "REPLACING"):
                out.append(Divergenza("blotter_senza_conto", "avviso", b,
                                      _testo(getattr(ordine, "customer_order_ref", None)) or None,
                                      f"ordine {st} nel blotter, assente dal conto",
                                      {"size_matched": sm, "status": st}))
            continue
        if abs(sm - float(o.abbinato)) > TOLLERANZA_ABBINATO:
            out.append(Divergenza("blotter_diverso", "avviso", b, o.customer_order_ref,
                                  f"abbinato blotter {sm} contro conto {o.abbinato}",
                                  {"blotter": {"size_matched": sm, "status": st},
                                   "conto": {"size_matched": o.abbinato, "status": o.stato}}))
    return out


def _divergenza_in_volo(v: InVolo, conto_completo: bool = True) -> Divergenza:
    if v.esito == "ritrovato":
        return Divergenza("in_volo_ritrovato", "info", v.bet_ids[0] if v.bet_ids else None,
                          v.ref, "comando in volo: l'ordine e' sul conto",
                          {"cors": list(v.cors), "bet_ids": list(v.bet_ids)})
    if v.esito == "non_trovato" and not conto_completo:
        return Divergenza("in_volo_da_verificare", "avviso", None, v.ref,
                          "ordine inviato non visto: il conto e' senza seme, serve "
                          "listCurrentOrders", {"cors": list(v.cors)})
    if v.esito == "non_trovato":
        return Divergenza("in_volo_non_trovato", "grave", None, v.ref,
                          "esito IGNOTO: ordine inviato ma assente dal conto",
                          {"cors": list(v.cors)})
    if v.esito == "perso_paper":
        return Divergenza("in_volo_perso_paper", "avviso", None, v.ref,
                          "ordine simulato in volo: il blotter paper non sopravvive al riavvio",
                          {"modo": v.modo})
    return Divergenza("in_volo_senza_place", "avviso", None, v.ref,
                      "nessuna riga 'ordine': place mai chiamato (cancel/replace: esito ignoto)",
                      {"modo": v.modo})


def _posizioni(modo: str, per_bet: Mapping[str, OrdineDalConto],
               attribuzioni: Mapping[str, attr.Attribuzione]) -> Tuple[Tuple[PosizioneConto, ...], int]:
    """``PosizioneConto`` per (mercato, selezione) dagli abbinati del conto
    (``pnl_mercato.esposizioni_per_selezione``, cioe' flumine). Le selezioni
    con handicap diverso da zero si contano e si saltano (``PosizioneConto``
    non ha l'handicap)."""
    per_mercato: Dict[str, List[OrdineConto]] = {}
    for b, o in per_bet.items():
        per_mercato.setdefault(str(o.market_id), []).append(
            libro_conto.componi_ordine_conto(modo, o, attribuzioni[b]))
    out: List[PosizioneConto] = []
    saltate = 0
    for mid, ordini in sorted(per_mercato.items()):
        for (sid, hc), e in pnl_mercato.esposizioni_per_selezione(ordini).items():
            if abs(hc) > 1e-9:
                saltate += 1
                continue
            out.append(PosizioneConto(market_id=mid, selection_id=sid, modo=modo,  # type: ignore[arg-type]
                                      se_vince=e.se_vince, se_perde=e.se_perde))
    return tuple(out), saltate
