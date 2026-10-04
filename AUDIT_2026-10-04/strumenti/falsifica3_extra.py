FLB = "Betfair/stream/tennis_scalper/tennis_flb_bot.py"
SW = "Betfair/stream/tennis_scalper/tennis_swing_bot.py"
T = "Betfair/stream/tennis_live/tests/test_residui_flb_swing_2026_10_04.py"
MUT = [
    ("F1 FLB senza il ramo del residuo", FLB,
     "                    if abs(nw_ - nl_) > 0.01 and self._residuo_non_piazzabile(",
     "                    if False and self._residuo_non_piazzabile(  # MUTAZIONE", T, "flb"),
    ("F2 FLB residuo non regolato", FLB,
     "        self.residui_ricordati.regola_mercato(getattr(market, \"market_id\", \"\"))\n",
     "        pass  # MUTAZIONE\n", T, "flb"),
    ("F3 SWING senza il ramo del residuo", SW,
     "            if not self.dry_run and self._residuo_non_piazzabile(",
     "            if False and self._residuo_non_piazzabile(  # MUTAZIONE", T, "swing"),
    ("F4 SWING residuo non regolato", SW,
     "        self.residui_ricordati.regola_mercato(getattr(market, \"market_id\", \"\"))\n",
     "        pass  # MUTAZIONE\n", T, "swing"),
]
