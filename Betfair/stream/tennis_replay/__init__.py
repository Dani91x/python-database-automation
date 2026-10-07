"""Replay TENNIS (07/10/2026): registrazione raw tennis -> tabelle ``tennis_replay_*``.

Sezione SEPARATA dal Match Replay del calcio (ordine dell'utente del 07/10):
tabelle, RPC, pagina e caricamento propri. Calcio e tennis non si mischiano.

  * ``convertitore``: funzioni PURE, raw nativo Betfair (+ sidecar punteggio IPS)
    -> righe delle tabelle. La decodifica dello stream e' quella di
    betfairlightweight (``StreamListener`` + cache dei mercati), mai un parser nostro.
  * ``caricamento``: scrittura idempotente su Supabase (service_role).
  * ``importa``: strumento da lanciare A MANO per le registrazioni gia' su disco.
"""
