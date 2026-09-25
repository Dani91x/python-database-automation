"""Priorita' COMANDO nel piano tennis (F8 punto b). Lanciato una volta."""
import io

p = "Betfair/stream/tennis_live/iscrizione_a_caldo.py"
s = io.open(p, encoding="utf-8").read()


def sost(old, new, n=1):
    global s
    assert s.count(old) == n, (s.count(old), old[:80])
    s = s.replace(old, new)


sost('''  Priorita': POSIZIONI VIVE (mai espulse, mai tolte) > seguita A MANO (mai
  espulsa) > partita ARMATA (almeno un bot) > candidata. Una partita nuova entra''',
     '''  Priorita': POSIZIONI VIVE (mai espulse, mai tolte) > seguita A MANO (mai
  espulsa) > COMANDO di un bot (25/09, F8: l'ordine di Safe tennis su una
  partita non seguita, ``esecutore_tennis.AgganciaTennis``) > partita ARMATA
  (almeno un bot) > candidata. Una partita nuova entra''')
sost('''PRI_ARMATA = 2         # almeno un bot armato (riga in requested/arming/armed/running)
PRI_MANUALE = 3        # seguita a mano dall'utente: mai espulsa
''', '''PRI_ARMATA = 2         # almeno un bot armato (riga in requested/arming/armed/running)
PRI_COMANDO = 3        # 25/09 (F8): un bot ha mandato un ORDINE su questa partita
PRI_MANUALE = 4        # seguita a mano dall'utente: mai espulsa
''')
sost('''    posizioni: bool = False
    in_uscita: bool = False

    @property
    def priorita(self) -> int:
        if self.in_uscita:
            return PRI_IN_USCITA
        if self.manuale:
            return PRI_MANUALE
        if self.armata:
''', '''    posizioni: bool = False
    in_uscita: bool = False
    #: 25/09 (F8): chiesta da un COMANDO d'ordine di un bot (aggancio a comando)
    comando: bool = False

    @property
    def priorita(self) -> int:
        if self.in_uscita:
            return PRI_IN_USCITA
        if self.manuale:
            return PRI_MANUALE
        if self.comando:
            return PRI_COMANDO
        if self.armata:
''')
sost('''        uscente = Evento(s.event_id, s.manuale, s.armata, s.posizioni, in_uscita=True)
''', '''        uscente = Evento(s.event_id, s.manuale, s.armata, s.posizioni, in_uscita=True,
                         comando=s.comando)
''')
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
