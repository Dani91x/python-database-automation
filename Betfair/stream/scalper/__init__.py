"""Componente SCALPER (separato da live_engine_pro).

Bot di micro-scalping su Betfair Exchange progettato per **micro-profitti
costanti** cavalcando movimenti di pochi tick. Opera di default SOLO pre-match
(rischio settlement nullo); l'in-play e' attivabile via flag.

Espone:
  * :class:`~Betfair.stream.scalper.scalper_bot.ScalperStrategy`
  * :func:`~Betfair.stream.scalper.run_scalper.run_scalper`
"""
from .scalper_bot import ScalperStrategy  # noqa: F401
