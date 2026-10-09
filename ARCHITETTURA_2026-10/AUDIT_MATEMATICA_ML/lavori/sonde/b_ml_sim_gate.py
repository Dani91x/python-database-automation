"""Simulazione: un 'modello' SENZA ALCUN SKILL (predice il tasso base della lega stimato sul train)
supera il gate BSS>=0.12 (baseline uniforme) quando il tasso base della lega e' lontano da 0.5?
Binario, Brier = somma sulle 2 classi come in seriea_model_export._brier_score."""
import numpy as np
rng = np.random.default_rng(0)
N_HOLD, N_TRAIN, LEGHE = 170, 1270, 20000
for nome, mu, sd in [("over_2_5", .51, .08), ("over_1_5", .74, .06), ("btts", .52, .06), ("over_3_5", .29, .07)]:
    q = np.clip(rng.normal(mu, sd, LEGHE), .05, .95)
    p_hat = np.clip(rng.binomial(N_TRAIN, q) / N_TRAIN, .01, .99)       # stima del tasso base sul train
    y = rng.binomial(N_HOLD, q) / N_HOLD                                # frequenza osservata nell'holdout
    # Brier per partita = 2*(p-y)^2 ; media su holdout = 2*(p^2 - 2 p ybar + ybar)  (y in {0,1})
    brier = 2 * (p_hat ** 2 - 2 * p_hat * y + y)
    bss = 1 - brier / 0.5
    clim = 1 - brier / (2 * q * (1 - q))
    print(f"{nome:9s} tasso base medio {mu:.2f}: modello SENZA skill  Brier medio {brier.mean():.3f}  BSS(uniforme) medio {bss.mean():+.3f}  passa gate>=0.12: {100*(bss>=.12).mean():5.1f}%   BSS vs tasso-base medio {clim.mean():+.3f}")
