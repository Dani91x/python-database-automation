"""Applica UNA volta al tennis scalper lo schema del cancello uscite (cantiere N).
Ogni sostituzione deve trovare ESATTAMENTE un'occorrenza, altrimenti si ferma
senza scrivere niente. Rilanciarlo su un file gia' patchato fallisce (voluto)."""
import os
import sys

WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(WT, "Betfair", "stream", "tennis_scalper", "tennis_scalper_bot.py")

SOST = [
    # 1) import
    ("from flumine.utils import ",
     None),  # solo controllo presenza
]


def main() -> int:
    with open(P, "r", encoding="utf-8", newline="") as fh:
        t = fh.read()
    nl = "\r\n" if "\r\n" in t else "\n"

    def R(vecchio: str, nuovo: str) -> None:
        nonlocal t
        v = vecchio.replace("\n", nl)
        n = t.count(v)
        if n != 1:
            raise SystemExit(f"occorrenze {n} per: {vecchio[:70]!r}")
        t = t.replace(v, nuovo.replace("\n", nl))

    # 1) import del modulo comune
    R("from flumine.utils import get_nearest_price",
      "from ..uscite_proposte import CHIAVE_STATS as CHIAVE_PROPOSTE\n"
      "from ..uscite_proposte import CancelloUscite, proposta_di\n"
      "from flumine.utils import get_nearest_price")
    # 2) il campo della proposta sullo slot
    R("    swing: bool = False                  # ciclo originato dal trend (target/stop swing)\n"
      "    inplay_cycle: bool = False           # ciclo aperto in-play (per circuit breaker)\n",
      "    swing: bool = False                  # ciclo originato dal trend (target/stop swing)\n"
      "    # 28/09 (CANTIERE N) - uscite manuali: il motivo dell'ultima proposta\n"
      "    proposta: Optional[str] = None\n"
      "    inplay_cycle: bool = False           # ciclo aperto in-play (per circuit breaker)\n")
    # 3) attributo di classe (lo imposta il runner dalla riga per partita)
    R("    def __init__(self, *args: Any, **kwargs: Any) -> None:\n"
      "        # estrai i parametri dedicati PRIMA di passare il resto a BaseStrategy\n",
      "    #: 28/09 (CANTIERE N, ordine dell'utente: \"nessuna eccezione per\n"
      "    #: strategia\"): prima lo scalper tennis era SEMPRE automatico\n"
      "    #: (``auto_mode.BOT_USCITE_SEMPRE_AUTOMATICHE``). Ora ha l'interruttore come\n"
      "    #: gli altri bot e nasce MANUALE: target, gamba opposta come chiusura,\n"
      "    #: scratch, stop e lock_ttl diventano PROPOSTE e partono con la firma.\n"
      "    uscite_automatiche: bool = False\n\n"
      "    def __init__(self, *args: Any, **kwargs: Any) -> None:\n"
      "        # estrai i parametri dedicati PRIMA di passare il resto a BaseStrategy\n")
    R("        self._slots: Dict[Tuple[str, int], _Slot] = {}\n",
      "        self._slots: Dict[Tuple[str, int], _Slot] = {}\n"
      "        # 28/09 (CANTIERE N): proposte d'uscita e firme dell'utente\n"
      "        self.cancello_uscite = CancelloUscite(emetti=lambda ev, p: self._emit(ev, **p))\n")
    # 4) gamba opposta del maker come chiusura: solo a uscite automatiche
    R("            if done and el is not None and abs(mb - float(\n",
      "            if done and el is not None and self.uscite_automatiche and abs(mb - float(\n")
    R("            if done and eb is not None and abs(ml - float(\n",
      "            if done and eb is not None and self.uscite_automatiche and abs(ml - float(\n")
    # 5) LOCKING: firma/riaccensione del target, poi condizioni vive
    R("        if slot.status == LOCKING:\n"
      "            # vecchie close sostituite (scratch): ritenta il cancel finche'\n"
      "            # non sono morte (il primo cancel puo' fallire su ordini PENDING)\n"
      "            for o in slot.flatten_orders:\n"
      "                if self._has_live(o):\n"
      "                    self._cancel_if_live(market, o)\n",
      "        if slot.status == LOCKING:\n"
      "            # vecchie close sostituite (scratch): ritenta il cancel finche'\n"
      "            # non sono morte (il primo cancel puo' fallire su ordini PENDING)\n"
      "            for o in slot.flatten_orders:\n"
      "                if self._has_live(o):\n"
      "                    self._cancel_if_live(market, o)\n"
      "            # 28/09 (CANTIERE N): posizione in attesa dell'utente e uscite\n"
      "            # riaccese, o chiusura a target FIRMATA: la chiusura parte adesso.\n"
      "            if (slot.close is None and slot.proposta is not None and slot.entry is not None\n"
      "                    and (self.uscite_automatiche or self._firmata(slot, \"target\"))):\n"
      "                self._open_lock(market, slot, now, slot.entry, best_back, best_lay)\n"
      "                return\n")
    R("            if (adverse is not None and adverse >= eff_stop) or (\n"
      "                slot.t_lock is not None and now - slot.t_lock > self.lock_ttl_ms\n"
      "            ):\n"
      "                self._cancel_if_live(market, close)\n",
      "            # 28/09 (CANTIERE N): quali uscite vuole la strategia ADESSO\n"
      "            cond_stop = adverse is not None and adverse >= eff_stop\n"
      "            cond_ttl = slot.t_lock is not None and now - slot.t_lock > self.lock_ttl_ms\n"
      "            cond_scratch = bool(self.scratch_enable and scratch_now\n"
      "                                and not slot.close_scratched and c_match <= _EPS\n"
      "                                and entry_p is not None)\n"
      "            pref = self._prefisso_uscite(slot)\n"
      "            vive = [pref + m for m, v in ((\"target\", slot.close is None),\n"
      "                                          (\"stop\", cond_stop),\n"
      "                                          (\"timeout\", cond_ttl and not cond_stop),\n"
      "                                          (\"scratch\", cond_scratch)) if v]\n"
      "            self.cancello_uscite.conferma_vive(pref, vive)\n"
      "            self._pubblica_proposte(pota=False)\n"
      "            if cond_stop or cond_ttl:\n"
      "                nw_x = sb * (ob - 1.0) - sl * (ol - 1.0)\n"
      "                nl_x = sl - sb\n"
      "                px_x = best_lay if slot.entry_side == \"BACK\" else best_back\n"
      "                g_x = compute_green(nw_x, nl_x, px_x) if px_x else None\n"
      "                if not self._lascia_uscire(\n"
      "                        slot, \"stop\" if cond_stop else \"timeout\",\n"
      "                        lato=(g_x[0] if g_x else None), prezzo=px_x,\n"
      "                        size=(g_x[1] if g_x else None),\n"
      "                        bloccabile=(g_x[2] if g_x else None),\n"
      "                        se_vince=nw_x, se_perde=nl_x, now_ms=now):\n"
      "                    return\n"
      "            if cond_stop or cond_ttl:\n"
      "                self._cancel_if_live(market, close)\n")
    R("            if (\n"
      "                self.scratch_enable\n"
      "                and scratch_now\n"
      "                and not slot.close_scratched\n"
      "                and c_match <= _EPS\n"
      "                and entry_p is not None\n"
      "            ):\n"
      "                self._cancel_if_live(market, close)\n",
      "            if cond_scratch:\n"
      "                nw_s = sb * (ob - 1.0) - sl * (ol - 1.0)\n"
      "                g_s = compute_green(nw_s, sl - sb, entry_p)\n"
      "                if not self._lascia_uscire(slot, \"scratch\", lato=(g_s[0] if g_s else None),\n"
      "                                           prezzo=entry_p, size=(g_s[1] if g_s else None),\n"
      "                                           bloccabile=(g_s[2] if g_s else None),\n"
      "                                           se_vince=nw_s, se_perde=sl - sb, now_ms=now):\n"
      "                    return\n"
      "            if cond_scratch:\n"
      "                self._cancel_if_live(market, close)\n")
    # 6) _open_lock: il target passa dal cancello
    R("        side, size, _locked = g\n"
      "        # floor_min=False: l'hedge deve coprire ESATTAMENTE la quota matchata.\n",
      "        side, size, _locked = g\n"
      "        if not self._lascia_uscire(slot, \"target\", lato=side, prezzo=target, size=size,\n"
      "                                   bloccabile=_locked, se_vince=net_win,\n"
      "                                   se_perde=net_lose, now_ms=now):\n"
      "            # 28/09 (CANTIERE N) - uscite MANUALI: nessuna chiusura del bot;\n"
      "            # la posizione resta in LOCKING e l'utente firma la proposta.\n"
      "            slot.close = None\n"
      "            if slot.t_lock is None:\n"
      "                slot.t_lock = now\n"
      "            slot.status = LOCKING\n"
      "            self._pubblica_proposte()\n"
      "            return\n"
      "        # floor_min=False: l'hedge deve coprire ESATTAMENTE la quota matchata.\n")
    # 7) i metodi del cancello (prima di _begin_flatten)
    R("    def _begin_flatten(self, slot: _Slot) -> None:\n",
      "    # ----------------------------------- 28/09 (CANTIERE N): il cancello uscite\n"
      "    def _chiave_slot(self, slot: _Slot) -> Optional[Tuple[str, int]]:\n"
      "        for k, v in self._slots.items():\n"
      "            if v is slot:\n"
      "                return k\n"
      "        return None\n\n"
      "    def _prefisso_uscite(self, slot: _Slot) -> str:\n"
      "        k = self._chiave_slot(slot) or (\"?\", 0)\n"
      "        ingresso = getattr(slot.entry, \"id\", None) or id(slot.entry)\n"
      "        return f\"tennis_scalper|{k[0]}|{k[1]}|{ingresso}|\"\n\n"
      "    def _firmata(self, slot: _Slot, motivo: str) -> bool:\n"
      "        return (self._prefisso_uscite(slot) + motivo) in self.cancello_uscite.approvate\n\n"
      "    def _lascia_uscire(self, slot: _Slot, motivo: str, *, lato: Any, prezzo: Any,\n"
      "                       size: Any, bloccabile: Any, se_vince: Any = None,\n"
      "                       se_perde: Any = None, now_ms: Optional[int] = None) -> bool:\n"
      "        \"\"\"True = l'uscita decisa dalla strategia parte ADESSO (automatiche o\n"
      "        firmata); False = proposta coi numeri, niente ordini.\"\"\"\n"
      "        k = self._chiave_slot(slot) or (\"?\", 0)\n"
      "        ok = self.cancello_uscite.lascia_uscire(\n"
      "            automatiche=bool(self.uscite_automatiche),\n"
      "            chiave=self._prefisso_uscite(slot) + motivo,\n"
      "            now_s=(float(now_ms) / 1000.0 if now_ms is not None else self._orologio_s()),\n"
      "            proposta=proposta_di(\n"
      "                bot=\"tennis_scalper\", motivo=motivo, market_id=k[0], selection_id=k[1],\n"
      "                lato_ingresso=slot.entry_side, prezzo=prezzo, lato_chiusura=lato,\n"
      "                size_chiusura=size, se_chiudi=bloccabile, se_vince=se_vince,\n"
      "                se_perde=se_perde))\n"
      "        if not ok:\n"
      "            slot.proposta = motivo\n"
      "        self._pubblica_proposte(pota=False)\n"
      "        return ok\n\n"
      "    def _pubblica_proposte(self, pota: bool = True) -> None:\n"
      "        if pota:\n"
      "            self.cancello_uscite.tieni_solo(\n"
      "                [self._prefisso_uscite(s) for s in self._slots.values()\n"
      "                 if s.status == LOCKING and s.entry is not None])\n"
      "        self.stats[CHIAVE_PROPOSTE] = self.cancello_uscite.vive()  # type: ignore[assignment]\n\n"
      "    def _begin_flatten(self, slot: _Slot) -> None:\n")
    # 8) reset dello slot
    R("        slot.t_lock = None\n",
      "        slot.t_lock = None\n"
      "        slot.proposta = None\n")
    with open(P, "w", encoding="utf-8", newline="") as fh:
        fh.write(t)
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
