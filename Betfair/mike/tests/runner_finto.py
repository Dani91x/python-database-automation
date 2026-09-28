"""Il RUNNER finto per i test di Mike paper (D1, 29/09).

Parla il protocollo VERO del canale di comando: il comando passa da
``motore_ordini.valida_comando`` (la validazione di produzione), l'ack e gli
eventi ``order`` entrano nella ``MemoriaComandi`` di produzione (la stessa della
``PortaCanale``), la fase la calcola ``motore_ordini.fase_da_riga`` sulla riga
dello specchio con le chiavi di ``motore_ordini.CHIAVI_SPECCHIO``.

Il MATCHING e' quello di un test, dichiarato: un taker (FOK) si abbina per
intero al prezzo chiesto, salvo ``rifiuta_fok``; un ordine senza FOK resta sul
book (``EXECUTABLE``) finche' il test lo abbina (``abbina``) o lo fa scadere
(``scadi``). Il matching vero (coda, bet delay, parziali) e' quello di flumine
nel runner e nel banco di replay.
"""
from __future__ import annotations

import itertools
from typing import Any, Dict, List, Optional

from Betfair.safe_strategy import porta_ordini as PO
from Betfair.stream import motore_ordini as MO


class RunnerFinto:
    via_canale = True
    nome = "runner_finto"

    def __init__(self, *, attore: str = "mike") -> None:
        self.attore = attore
        self.memoria = PO.MemoriaComandi()
        self.collegato = True
        self.comandi: List[Dict[str, Any]] = []
        self.ordini: Dict[str, Dict[str, Any]] = {}      # ref -> riga dello specchio
        self._seq = itertools.count(1_700_000_000_000)
        self._bet = itertools.count(900001)
        self.rifiuta_fok = False
        self.rifiuto_motore: Optional[str] = None
        #: prezzo a cui il runner abbina i taker (None = il prezzo chiesto)
        self.prezzo_taker: Optional[float] = None
        #: comandi che partono ma di cui il canale non conferma l'invio
        self.perdi_invio = False
        #: eventi ``order`` trattenuti (runner lento o muto): escono con ``rilascia``
        self.trattieni = False
        self._trattenuti: List[str] = []

    # -- interfaccia della PortaCanale -------------------------------------
    def disponibile(self) -> bool:
        return bool(self.collegato)

    def esiti(self, ref: str) -> Optional[Dict[str, Any]]:
        return self.memoria.esito(ref)

    def attendi_esito_bet(self, bet_id: str, timeout_s: float) -> Optional[Dict[str, Any]]:
        e = self.memoria.esito_per_bet(str(bet_id))
        if e is None:
            return None
        return e if (PO.terminale(e) or float(e.get("size_remaining") or 0.0) <= 0) else None

    def invia(self, comando: Dict[str, Any]) -> PO.Ack:
        ref = str(comando.get("ref") or "")
        if not self.collegato or self.perdi_invio:
            return PO.Ack.non_inviato(ref, "canale_giu")
        self.comandi.append(dict(comando))
        try:
            MO.valida_comando(self.attore, comando)
        except MO.Rifiuto as ex:
            return self._ack(ref, False, getattr(ex, "codice", str(ex)))
        if self.rifiuto_motore:
            return self._ack(ref, False, self.rifiuto_motore)
        ack = self._ack(ref, True, None)
        if comando.get("azione") == "place":
            self._piazza(comando)
        elif comando.get("azione") == "cancel":
            self._annulla(str(comando.get("bet_id") or ""))
        return ack

    # -- comandi del test ----------------------------------------------------
    def abbina(self, ref: str, size: Optional[float] = None,
               prezzo: Optional[float] = None) -> None:
        r = self.ordini[ref]
        resto = float(r["size_remaining"])
        quanto = resto if size is None else min(resto, float(size))
        gia = float(r["size_matched"])
        p = float(prezzo if prezzo is not None else r["price"])
        r["average_price_matched"] = round(
            (gia * float(r["average_price_matched"] or 0.0) + quanto * p) / (gia + quanto), 4)
        r["size_matched"] = round(gia + quanto, 2)
        r["size_remaining"] = round(resto - quanto, 2)
        r["status"] = "EXECUTION_COMPLETE" if r["size_remaining"] <= 0 else "EXECUTABLE"
        self._pubblica(ref)

    def scadi(self, ref: str) -> None:
        r = self.ordini[ref]
        r["size_lapsed"] = r["size_remaining"]
        r["size_remaining"] = 0.0
        r["status"] = "EXECUTION_COMPLETE"
        self._pubblica(ref)

    def ordine(self, ref: str) -> Dict[str, Any]:
        return self.ordini[ref]

    # -- interni ---------------------------------------------------------------
    def _ack(self, ref: str, ok: bool, motivo: Optional[str]) -> PO.Ack:
        d = {"ref": ref, "seq": next(self._seq), "accettato": ok, "motivo": motivo,
             "ricevuto_ms": 0}
        self.memoria.ricevi_ack(d)
        return PO.Ack.da_busta(d)

    def _piazza(self, c: Dict[str, Any]) -> None:
        riga = {k: None for k in MO.CHIAVI_SPECCHIO}
        riga.update({
            "bet_id": str(next(self._bet)), "client_order_ref": c["ref"], "mode": c["mode"],
            "market_id": c["market_id"], "selection_id": c["selection_id"],
            "side": c["side"], "order_type": "LIMIT", "price": c["price"], "size": c["size"],
            "size_matched": 0.0, "size_remaining": c["size"], "size_cancelled": 0.0,
            "size_lapsed": 0.0, "size_voided": 0.0, "average_price_matched": 0.0,
            "status": "EXECUTABLE", "persistence": c.get("persistence") or "LAPSE",
            "handicap": 0.0,
        })
        self.ordini[c["ref"]] = riga
        if c.get("time_in_force") == PO.FOK:
            if self.rifiuta_fok:
                riga["size_cancelled"] = riga["size_remaining"]
                riga["size_remaining"] = 0.0
                riga["status"] = "EXECUTION_COMPLETE"
                self._pubblica(c["ref"])
            else:
                self.abbina(c["ref"], prezzo=self.prezzo_taker)
            return
        self._pubblica(c["ref"])

    def _annulla(self, bet_id: str) -> None:
        for ref, r in self.ordini.items():
            if str(r["bet_id"]) == bet_id and float(r["size_remaining"]) > 0:
                r["size_cancelled"] = r["size_remaining"]
                r["size_remaining"] = 0.0
                r["status"] = "EXECUTION_COMPLETE"
                self._pubblica(ref)
                return

    def rilascia(self) -> None:
        refs, self._trattenuti = self._trattenuti, []
        for ref in refs:
            self._pubblica(ref, forza=True)

    def _pubblica(self, ref: str, forza: bool = False) -> None:
        if self.trattieni and not forza:
            if ref not in self._trattenuti:
                self._trattenuti.append(ref)
            return
        r = dict(self.ordini[ref])
        ev = {**r, "ref": ref, "seq": next(self._seq), "fase": MO.fase_da_riga(r),
              "esito_ms": 0}
        self.memoria.ricevi_evento(ev)
