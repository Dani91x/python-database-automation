"""Componente SCALPER (separato da live_engine_pro).

Bot di micro-scalping su Betfair Exchange progettato per **micro-profitti
costanti** cavalcando movimenti di pochi tick. Opera di default SOLO pre-match
(rischio settlement nullo); l'in-play e' attivabile via flag.

Espone:
  * :class:`~Betfair.stream.scalper.scalper_bot.ScalperStrategy`
  * :func:`~Betfair.stream.scalper.run_scalper.run_scalper`

17/09/2026 — L'IMPORT DI ``ScalperStrategy`` E' PIGRO, E DEVE RESTARLO.
``scalper_bot`` importa ``flumine``, e ``flumine/__init__.py:13`` sostituisce
``bettingresources.RunnerBookEX`` per TUTTO il processo con una classe che
lascia i livelli del ladder come dizionari. Con l'import eager, bastava un
``from Betfair.stream.scalper.<qualsiasi cosa> import ...`` - per esempio
l'Atlante Hazard caricato da ``safe_strategy/service.py`` - perche' il
processo del FEED si ritrovasse flumine dentro e leggesse ``None`` su ogni
prezzo. E' la causa del blackout delle quote del 17/09.
Chi vuole la strategia la chiede per nome (``from Betfair.stream.scalper import
ScalperStrategy``) e la paga in quel momento; chi vuole l'Atlante importa
``hazard_atlas``, che flumine non lo tira dentro.
"""
from typing import Any

__all__ = ["ScalperStrategy"]


def __getattr__(name: str) -> Any:
    """Import PIGRO degli attributi del package (PEP 562)."""
    if name == "ScalperStrategy":
        from .scalper_bot import ScalperStrategy

        return ScalperStrategy
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
