"""Bot OMEGA — LAY su Correct Score, set-and-forget, obiettivo giornaliero.

Fonte di verità: ``Betfair/omega/COSTITUZIONE_OMEGA.md``.

Moduli:
- ``omega_engine``  : logica PURA (selezione/sizing/target/settlement,
  fill PAPER ``paper_fill``, aggregati, riconciliazione) — testata.
- ``omega_config``  : default e whitelist parametri.
- ``omega_market``  : wrapper Betfair REST (events/catalogue/book/place).
- ``omega_db``      : I/O Supabase (control/trades/activity).
- ``omega_service`` : supervisore/loop locale.
"""
