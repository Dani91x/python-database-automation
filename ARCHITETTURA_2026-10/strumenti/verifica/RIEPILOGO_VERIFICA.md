# Revisione indipendente delle citazioni (08/10, 4 verificatori Sonnet + coordinatore)

Campione riproducibile: `estrai_campione.py <documento> 25` (seme 20261008), 25 citazioni per scheda, 20 per 04 e 05.

| Gruppo | Referto | Citazioni | Confermate | Spostate (corrette) | False (corrette) |
|---|---|---:|---:|---:|---:|
| A, B, C, G | `verifica_ABCG.md` | 100 | 94 | 4 | 2 (G: funzione `revoke_live_order_request` scambiata per `enqueue_live_order`; `scalper_session.py:962` non e' una tabella `scalper_*`) |
| D, E1, E2, F | `verifica_DE1E2F.md` | 100 | 98 | 1 | 1 (E2-069: `CashOutButton` a 538-568, non 493) |
| E3, E4, E5, I | `verifica_E3E4E5I.md` | 100 | 95 | 5 | 0 |
| H, J, K, 04, 05 | `verifica_HJK0405.md` | 115 | 115 | 0 | 0 (1 citazione chiarita in K) |
| **Totale** | | **415** | **402 (96,9%)** | **10** | **3** |

Nessuna citazione falsa cambia un difetto, un numero o una decisione per l'utente. Il coordinatore ha ricontrollato
`mike/db.py:662` (`enqueue_live_order`) e `:683`, e corretto due residui (`F:127` -> `betfair_tennis_odds.py:311`,
`E5:152` -> `:305`). Prima di questa revisione: E1 respinta e corretta (D6 falso). Dopo le correzioni `01` rigenerato
(970 voci) e copertura del 05 ricontrollata: 971/971, 0 mancanti.
