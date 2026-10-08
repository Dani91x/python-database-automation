# Suite complete su b4d91ed (cloud, 08/10/2026)

- sha: `b4d91ed063178596889104705e04b1d89d10ae61` (ramo claude/blissful-sagan-hri7o6-w3a-suite)
- nproc: 4 · Python 3.13.16 · le quattro suite lanciate in parallelo, poi la build
- Nota: per un errore nel comando di lancio i file di pytest_tools, tsc, vitest e build sono
  stati scritti in `/` e spostati qui dopo la corsa; contenuto ed esiti invariati.

| Suite | Esito | Numeri | Tempo (real) |
|---|---|---|---|
| `pytest Betfair/` | **ROSSO** (exit 1) | 1 failed, 11247 passed, 87 skipped, 6 xfailed, 14 warnings | 4m26s (pytest 261.70s) |
| `pytest tools/` | verde (exit 0) | 17 passed | 1m11s |
| `tsc -p tsconfig.app.json --noEmit` | verde (exit 0) | 0 errori | 1m03s |
| `vitest run` | verde (exit 0) | 367 file passati, 10 saltati (377); 5447 test passati, 51 saltati (5498) | 4m46s |
| `npm run build` | verde (exit 0) | build completata in 13.60s (solo l'avviso sulla dimensione dei chunk) | 14s |

## Il rosso

`Betfair/stream/tests/test_frammenti_mercato_2026_09_28.py::test_auto_follow_rifiuto_betfair_rientra_e_dichiara`
(riga 526: `assert s["eventi_auto"] == 67` -> `45 == 67`; dopo la pausa di rifiuto il secondo
frammento non viene concesso, e la capacita' resta 180 = 45 partite x 4).

Rilanciato DA SOLO: 3 volte -> 2 rossi, 1 verde; poi 20 volte -> 0 verdi, 20 rossi; il suo
file da solo: 1 failed, 37 passed. Quindi e' **rosso anche da solo** ma **non deterministico**:
NON e' un problema di parallelismo della suite.

Causa probabile, NON verificata (non ho modificato codice): in
`Betfair/stream/frammenti_mercato.py` `_visto_dal` e' indicizzato per `id(s)`
(`self._visto_dal.setdefault(id(s), ora)`). Quando il frammento rifiutato viene chiuso e
raccolto, il nuovo stream puo' riavere lo stesso `id()`: eredita cosi' il vecchio `dal`, con
l'orologio finto avanzato di `PAUSA_RIFIUTO_S + 1` (301 s) risulta `ora - dal >
ATTESA_APERTURA_S` (60 s) e viene richiuso come "nessuna autenticazione": quindi non rientra.
Il riuso di `id()` dipende dall'allocatore, da cui l'esito variabile. Concorre forse anche il
misto di `time.monotonic()` reale (`_osserva`, `aperto_mono`) con l'orologio finto.
Da confermare da chi possiede il dominio di quel file.
