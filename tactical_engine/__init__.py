"""tactical_engine - Terzo motore di previsione calcio (standalone).

Motore INDIPENDENTE ispirato al metodo di TacticAI (DeepMind):
- forze attacco/difesa INFERITE per massima verosimiglianza (non medie mobili),
- correzione Dixon-Coles sui punteggi bassi,
- decadimento temporale,
- simmetria casa/trasferta strutturale (Z2): una sola coppia (att,def) per
  squadra + un unico vantaggio-campo condiviso.

NON importa nulla dal motore Poisson esistente (Prediction/) e non lo modifica.
Condivide solo l'accesso DB in sola lettura.
"""
__all__ = ["dixon_coles", "model", "data_loader", "report"]
