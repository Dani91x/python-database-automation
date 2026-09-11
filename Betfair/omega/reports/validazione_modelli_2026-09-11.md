# Validazione modelli Omega — 2026-09-11

Campione: 1566 partite FT con gol a minuto coerenti (training 939, test 627).
Coda = risultati con P ≤ 2 % (quelli che Omega banca): `ratio` = usciti / previsti dal modello
(1 = calibrato; > 1 = il modello SOTTOSTIMA la coda → i lay perdono più del previsto).
Modelli: poisson (λ di lega + residui live), poisson_cal (calibratore condiviso, famiglie cs_cell/hts_cell), poisson_tail (fattore di coda ×1.3), empirical (tabella per minuto dal training), blend, blend_tail.

## Minuto 25' (45)

| modello | n | log-loss | coda n | previsti | usciti | ratio |
|---|---:|---:|---:|---:|---:|---:|
| poisson | 627 | 1.252631 | 27516 | 20.5826 | 31 | 1.5061 |
| poisson_cal | 627 | 1.255184 | 27926 | 24.6472 | 39 | 1.5823 |
| poisson_tail | 627 | 1.222921 | 26969 | 14.6813 | 15 | 1.0217 |
| empirical | 603 | 1.347503 | 3224 | 24.7178 | 30 | 1.2137 |
| blend | 603 | 1.221336 | 26410 | 19.8817 | 28 | 1.4083 |
| blend_tail | 603 | 1.195665 | 25918 | 14.2414 | 16 | 1.1235 |

## Minuto 60' (finale)

| modello | n | log-loss | coda n | previsti | usciti | ratio |
|---|---:|---:|---:|---:|---:|---:|
| poisson | 627 | 1.840194 | 71124 | 29.3087 | 32 | 1.0918 |
| poisson_cal | 627 | 1.824087 | 70628 | 39.973 | 25 | 0.6254 |
| poisson_tail | 627 | 1.805463 | 70804 | 29.9613 | 29 | 0.9679 |
| empirical | 546 | 2.321105 | 2142 | 24.3932 | 34 | 1.3938 |
| blend | 546 | 1.74066 | 62203 | 25.9053 | 29 | 1.1195 |
| blend_tail | 546 | 1.705582 | 61899 | 26.9651 | 21 | 0.7788 |

## Minuto 70' (finale)

| modello | n | log-loss | coda n | previsti | usciti | ratio |
|---|---:|---:|---:|---:|---:|---:|
| poisson | 627 | 1.519942 | 72055 | 24.7667 | 29 | 1.1709 |
| poisson_cal | 627 | 1.535782 | 71118 | 24.7738 | 14 | 0.5651 |
| poisson_tail | 627 | 1.491069 | 72002 | 30.9918 | 29 | 0.9357 |
| empirical | 534 | 1.769284 | 1753 | 15.938 | 16 | 1.0039 |
| blend | 534 | 1.417683 | 61537 | 21.719 | 22 | 1.0129 |
| blend_tail | 534 | 1.39066 | 61101 | 17.967 | 19 | 1.0575 |
