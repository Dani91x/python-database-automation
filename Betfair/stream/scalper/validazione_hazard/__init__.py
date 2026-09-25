"""Banco di validazione FUORI CAMPIONE dell'Atlante Hazard (25/09/2026).

Moduli:
  raccogli   letture del DB in SOLA LETTURA, una volta, salvate in cache locale
  dati       dalla cache alle partite (gol, rossi, recupero) - PURO
  stati      partite -> stati osservabili (partite-minuto) con la verita' a 2'/3' - PURO
  candidati  A0 (produzione vera) e le varianti A1..A7, B1 - PURO
  metriche   log-loss, Brier, AUC, calibrazione, bootstrap per partita - PURO
  banco      CLI riproducibile (``--da-cache``)
ASCII-only; commenti in italiano. Nessuna scrittura sul DB, mai.
"""
