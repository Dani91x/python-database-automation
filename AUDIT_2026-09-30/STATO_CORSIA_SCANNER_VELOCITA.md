# STATO corsia «velocita' del feed dei punteggi» (sessione admin-bc, 30/09/2026)

Punto di ripresa in caso di interruzione (rete, sessione). Aggiornato a ogni passo.

## Dove sta il lavoro
- Worktree: `C:\Users\Admin\AppData\Local\Temp\claude\C--Users-Admin\377881a6-0a16-4807-8c8a-3338fa38dd79\scratchpad\wt-scanner`,
  ramo `scanner-velocita`, base master `670f8a5`.
- Patch di sicurezza (diff completo, rigenerata a ogni passo): `scratchpad/scanner_velocita_v1.patch`.
- File toccati (3 + 1 test): `Betfair/safe_strategy/service.py`, `Betfair/safe_strategy/scanner.py`,
  `Betfair/mike/service.py`, `Betfair/safe_strategy/tests/test_velocita_feed_2026_09_30.py`.

## Decisioni dell'utente (30/09, 18:10-18:30) che questa corsia esegue
- (b) timeline IPS nella finestra del fischio, CONSOLIDATA al posto del poll dei punteggi
  («zero chiamate in piu'»); (c) sveglia del giro punteggi dallo stream; (d-1) Mike legge lo
  stato dello scanner dal canale (DB come ripiego); (e) `MIKE_MAX_FOLLOWED` 80 + potatura;
  NO API-Football; NO regola «punteggio invariato senza sospensione».

## Passi
1. [x] codice scanner (b)(c)(e) e Mike (d-1) — 18:55
2. [x] 21 test nuovi verdi; falsificazione: 12 mutazioni, tutte rosse (2 test aggiunti per
   le 2 sopravvissute al primo giro) — 19:10. ATTENZIONE: pulire `__pycache__` prima di
   rilanciare dopo una mutazione (un .pyc stantio ha dato un falso rosso su «tetto 80»).
3. [x] suite `Betfair/safe_strategy Betfair/mike Betfair/stream/tests` nel worktree (in corsa)
4. [x] replay Mike `--scenari base` 35760084 dal worktree, confronto con
   `AUDIT_2026-09-30/replay/mike_tutti_FINALE.txt` (identico numero per numero)
5. [x] referto `AUDIT_2026-09-30/VELOCITA_FEED_E_GIRI.md` (conto chiamate prima/dopo)
6. [x] fusione (commit `04b8d20`, badge `c4fa7d9`) su master (`git diff HEAD` dal worktree → `git apply --3way`), commit a
   percorsi espliciti, revisore indipendente, cronostoria
7. [x] `.env`: NESSUNA riga necessaria (il tetto 80 e' nel codice; `MIKE_MAX_FOLLOWED` resta
   un override)

## Cosa NON e' verificato (da dire all'utente)
- Che il record `eventTimelines` porti il blocco `score` gia' valorizzato al KickOff: se non
  lo porta, il codice ricade sul poll dei punteggi nello stesso giro (nessuna regressione,
  nessun guadagno). Si vede dal vivo nel log «primo punteggio … fonte timeline/scores» e dal
  contatore `ips.punteggi_dalla_timeline` nello stato dello scanner.
