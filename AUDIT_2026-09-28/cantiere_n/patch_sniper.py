"""Applica UNA volta allo sniper (base D2) il cancello delle uscite del cantiere N:
presa di profitto, STOP e TIMEOUT ``max_pos_s`` diventano proposte a uscite
manuali; fine finestra, force-flat (freno/cap), ledger e flatten restano
protezioni. Ogni sostituzione deve trovare ESATTAMENTE un'occorrenza."""
import os
import sys

WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(WT, "Betfair", "stream", "scalper", "sniper_bot.py")


def main() -> int:
    with open(P, "r", encoding="utf-8", newline="") as fh:
        t = fh.read()
    nl = "\r\n" if "\r\n" in t else "\n"

    def R(vecchio: str, nuovo: str) -> None:
        nonlocal t
        v = vecchio.replace("\n", nl)
        n = t.count(v)
        if n != 1:
            raise SystemExit(f"occorrenze {n} per: {vecchio[:80]!r}")
        t = t.replace(v, nuovo.replace("\n", nl))

    R("from .scalper_bot import compute_green, ticks_between\n",
      "from .scalper_bot import compute_green, ticks_between\n"
      "from ..uscite_proposte import CHIAVE_STATS as CHIAVE_PROPOSTE\n"
      "from ..uscite_proposte import CancelloUscite, proposta_di\n")
    R("        self.uscite_automatiche: bool = _ua if isinstance(_ua, bool) else False\n"
      "        self.force_flat: bool = False\n",
      "        self.uscite_automatiche: bool = _ua if isinstance(_ua, bool) else False\n"
      "        # 29/09 (CANTIERE N, regola dell'utente del 28/09): in manuale anche\n"
      "        # STOP a N tick e TIMEOUT ``max_pos_s`` sono uscite di TRADING: tutte e\n"
      "        # tre (con la presa di profitto) diventano PROPOSTE coi numeri e\n"
      "        # partono solo con la firma, quando la condizione vale ancora. Restano\n"
      "        # protezioni automatiche: fine finestra, force-flat (freno/cap),\n"
      "        # divergenza del ledger, flatten e close parziale.\n"
      "        self.cancello_uscite = CancelloUscite(emetti=lambda ev, p: self._emit(ev, **p))\n"
      "        self.force_flat: bool = False\n")
    # --- TIMEOUT: dal cancello
    R("            if (pos.entries and not pos.flattening\n"
      "                    and pos.entry_fill_pt is not None\n"
      "                    and now - pos.entry_fill_pt > self.max_pos_s * 1000.0):\n"
      "                self.stats[\"timeouts\"] += 1\n",
      "            vive_n: List[str] = []\n"
      "            if (pos.entries and not pos.flattening\n"
      "                    and pos.entry_fill_pt is not None\n"
      "                    and now - pos.entry_fill_pt > self.max_pos_s * 1000.0\n"
      "                    and self._lascia_uscire(pos, runner.selection_id, \"timeout\",\n"
      "                                            bb, bl, now, vive_n)):\n"
      "                self.stats[\"timeouts\"] += 1\n")
    # --- STOP: dal cancello
    R("                    if up is not None and up >= self.stop_ticks:\n"
      "                        self.stats[\"stops\"] += 1\n",
      "                    if (up is not None and up >= self.stop_ticks\n"
      "                            and self._lascia_uscire(pos, runner.selection_id, \"stop\",\n"
      "                                                    bb, bl, now, vive_n)):\n"
      "                        self.stats[\"stops\"] += 1\n")
    # --- TARGET: dal cancello (sostituisce la sola proposta di D2)
    R("                            if g is not None and not self.uscite_automatiche:\n",
      "                            if g is not None and not self._lascia_uscire(\n"
      "                                    pos, runner.selection_id, \"target\", bb, bl, now,\n"
      "                                    vive_n, prezzo=price, g=g):\n")
    R("                                side, size, locked = g\n"
      "                                self._proponi_uscita(\n"
      "                                    pos, runner.selection_id, motivo=\"target\",\n"
      "                                    lato=side, prezzo=price, size=size,\n"
      "                                    bloccabile=locked)\n",
      "                                pass    # proposta scritta dal cancello\n")
    # --- a fine gestione della posizione aperta: condizioni cadute via
    R("                        if (self.profit_target > 0\n"
      "                                and self.stats[\"pnl_locked\"] >= self.profit_target):\n"
      "                            self._event_done = True\n"
      "                            self._emit(\"sniper_mission_done\",\n"
      "                                       pnl=round(self.stats[\"pnl_locked\"], 3))\n"
      "                continue\n",
      "                        if (self.profit_target > 0\n"
      "                                and self.stats[\"pnl_locked\"] >= self.profit_target):\n"
      "                            self._event_done = True\n"
      "                            self._emit(\"sniper_mission_done\",\n"
      "                                       pnl=round(self.stats[\"pnl_locked\"], 3))\n"
      "                if pos.entries:\n"
      "                    self.cancello_uscite.conferma_vive(self._prefisso_uscite(pos), vive_n)\n"
      "                self._pubblica_proposte()\n"
      "                continue\n")
    # --- metodi del cancello, prima di _proponi_uscita
    R("    def _proponi_uscita(self, pos: _Pos, selection_id: Any, *, motivo: str, lato: Any,\n",
      "    # ----------------------------------- 29/09 (CANTIERE N): il cancello uscite\n"
      "    def _prefisso_uscite(self, pos: _Pos) -> str:\n"
      "        \"\"\"La posizione (mercato, selezione, primo ingresso). Il primo pezzo\n"
      "        e' 'scalper': la firma passa dalla stessa RPC della sessione\n"
      "        (``scalper_approva_uscita``); ``sn-`` distingue lo sniper dal maker.\"\"\"\n"
      "        k = next((kk for kk, v in self._pos.items() if v is pos), (\"?\", 0))\n"
      "        e0 = pos.entries[0] if pos.entries else None\n"
      "        ingresso = getattr(e0, \"id\", None) or id(e0)\n"
      "        return f\"scalper|{k[0]}|{k[1]}|sn-{ingresso}|\"\n"
      "\n"
      "    def _lascia_uscire(self, pos: _Pos, selection_id: Any, motivo: str,\n"
      "                       bb: Any, bl: Any, now: float, vive: List[str], *,\n"
      "                       prezzo: Any = None, g: Any = None) -> bool:\n"
      "        \"\"\"True = l'uscita ``motivo`` decisa dalla strategia parte ADESSO\n"
      "        (automatiche, o firmata dall'utente entro il TTL); False = proposta\n"
      "        coi numeri e niente ordini. Lo stop e il timeout si chiudono a mercato\n"
      "        (flatten al touch): la proposta porta quel prezzo.\"\"\"\n"
      "        sb_m, ob, sl_m, ol = self._matched(pos.entries)\n"
      "        nw = sb_m * ((ob or 1.0) - 1.0) - sl_m * ((ol or 1.0) - 1.0)\n"
      "        nl = sl_m - sb_m\n"
      "        if prezzo is None:\n"
      "            prezzo = bl if nw > nl else bb\n"
      "        if g is None and prezzo:\n"
      "            g = compute_green(nw, nl, prezzo)\n"
      "        chiave = self._prefisso_uscite(pos) + motivo\n"
      "        ok = self.cancello_uscite.lascia_uscire(\n"
      "            automatiche=bool(self.uscite_automatiche), chiave=chiave,\n"
      "            now_s=float(now) / 1000.0,\n"
      "            proposta=proposta_di(\n"
      "                bot=\"sniper\", motivo=motivo, market_id=chiave.split(\"|\")[1],\n"
      "                selection_id=(int(selection_id) if selection_id is not None else None),\n"
      "                lato_ingresso=\"BACK\", prezzo=prezzo,\n"
      "                lato_chiusura=(g[0] if g else None),\n"
      "                size_chiusura=(g[1] if g else None),\n"
      "                se_chiudi=(g[2] if g else None), se_vince=nw, se_perde=nl))\n"
      "        if not ok:\n"
      "            vive.append(chiave)\n"
      "            if pos.proposta != motivo:\n"
      "                pos.proposta = motivo\n"
      "                self.stats[\"uscite_proposte_emesse\"] = int(\n"
      "                    self.stats.get(\"uscite_proposte_emesse\", 0) or 0) + 1\n"
      "        return ok\n"
      "\n"
      "    def _pubblica_proposte(self) -> None:\n"
      "        \"\"\"Le proposte vive nelle ``stats`` (la sessione le scrive come\n"
      "        ``sniper_uscite_proposte``): solo quelle delle posizioni aperte.\"\"\"\n"
      "        self.cancello_uscite.tieni_solo(\n"
      "            [self._prefisso_uscite(p) for p in self._pos.values()\n"
      "             if p.entries and not p.flattening])\n"
      "        self.stats[CHIAVE_PROPOSTE] = self.cancello_uscite.vive()  # type: ignore[assignment]\n"
      "\n"
      "    def _proponi_uscita(self, pos: _Pos, selection_id: Any, *, motivo: str, lato: Any,\n")
    with open(P, "w", encoding="utf-8", newline="") as fh:
        fh.write(t)
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
