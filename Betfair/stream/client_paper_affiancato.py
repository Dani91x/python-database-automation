"""client_paper_affiancato.py - il client PAPER che affianca quello REALE dentro
lo STESSO processo (F0 calcio 16/09, esteso al runner tennis il 24/09).

Codice SPOSTATO qui da ``Betfair/stream/runner.py`` senza cambiarne una riga di
comportamento: il runner calcio lo re-importa col suo nome di sempre
(``runner.PaperCompanionClient``) e il runner tennis lo usa per servire i bot
dichiarati PAPER quando il processo gira in LIVE (reperto T1 del 24/09).

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

from flumine import clients


class PaperCompanionClient(clients.BetfairClient):
    """Client PAPER che affianca quello REALE dentro lo STESSO runner LIVE (F0, 16/09).

    Perche' esiste: flumine ammette piu' client nello stesso framework
    (``baseflumine.add_client``) e instrada l'esecuzione dal client dell'ordine
    (``market.place_order(..., client=...)`` -> ``client.execution``), quindi un solo
    processo puo' servire le righe 'live' (client reale) e quelle 'paper' (questo).
    Due vincoli imposti da flumine e da Betfair, entrambi rispettati qui:

      * ``Clients.add_client`` RIFIUTA due client con lo stesso ``username`` sullo
        stesso venue: la sessione betfairlightweight e' CONDIVISA con il client reale
        (stesso account), quindi l'username viene distinto col suffisso ``#paper``.
        E' un'etichetta interna a flumine, non viaggia verso Betfair.
      * la sessione e' UNA e la possiede il client reale: ``login``/``logout``/
        ``keep_alive``/``update_account_details`` qui sono NO-OP, altrimenti i worker
        nativi di flumine (``keep_alive``, ``poll_account_balance``) farebbero il
        DOPPIO delle chiamate a Betfair sullo stesso account (regola del feed unico)
        e un logout del companion chiuderebbe la sessione sotto il client reale.

    I soldi veri restano separati PER COSTRUZIONE: ``paper_trade=True`` manda questo
    client sulla ``SimulatedExecution`` di flumine, che non contatta mai l'Exchange.
    """

    @property
    def username(self) -> str:  # type: ignore[override]
        return f"{clients.BetfairClient.username.fget(self)}#paper"

    def login(self):  # noqa: D401 - sessione gia' aperta dal client proprietario
        return None

    def logout(self):  # noqa: D401 - mai chiudere la sessione del client reale
        return None

    def keep_alive(self):  # noqa: D401 - keepAlive lo fa il client proprietario
        return True

    def update_account_details(self) -> None:  # noqa: D401 - saldo: una sola lettura
        return None
