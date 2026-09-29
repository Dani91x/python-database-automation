# CANTIERE MIKE-APP - P6 blocco 6A: `cover_form` nel pannello (sblocco del motore P5 blocco 2), 29/09/2026

Patch: `AUDIT_2026-09-29/MIKE_P6_6A.patch`, su master `08b9c6a`. Solo `frontend/src/lib/mike.ts`
(+3 righe, -1) e un test nuovo `frontend/src/lib/mikeCoverForm.test.ts`.

## Cosa
- `MIKE_PARAM_FIELDS`, gruppo della copertura, subito dopo `cover_max_overshoot_pct` (stesso
  posto di config.py): `cover_form`, «Forma della copertura», scelte `lay_under45` / `back_over45`
  (stesso ordine di config.py). Spiegazione: «la strategia e' la stessa, cambia solo l'ordine
  con cui Mike si copre. lay_under45 = banca Under 4,5 (importo sempre piazzabile, minimo 0,50
  EUR); back_over45 = punta Over 4,5, la forma di prima (minimo 2,00 EUR a passi di 0,50)».
- `MIKE_PARAM_DEFAULTS.cover_form = 'back_over45'`.
- Nient'altro del blocco 6 (etichette, `investedOf`, `positionRows` restano nel 6).

## Prove (in un worktree temporaneo = master `08b9c6a` + 6A, poi rimosso senza forzare)
- Contratto Python `test_mike_certificazione_ui_2026_09_11.py` col `config.py` di P5 blocco 2
  (`MIKE_P5_2.patch` applicata SOLO a `Betfair/mike/config.py` nella copia): **40/40 verdi**.
- `tsc` 0 errori; `npx vitest run src/lib/mike src/components/mike/MikeParamsSheet`: 6 file, 115 verdi.
- Mutazione: valore di serie `lay_under45` al posto di `back_over45` -> contratto **ROSSO**
  (`test_contratto_parametri_stessi_clamp_scelte_e_default`) e test nuovo rosso (1 su 3);
  ripristino con hash identico.

## Blocco 6 rigenerato
`MIKE_P6_6.patch` ora sta SOPRA il 6A: applica pulita su master + 6A (e su master + 6A + P6_4).
Rispetto al 6A cambia solo il valore di serie (`lay_under45`) e la costante `SERIE` del test
`mikeCoverForm.test.ts`; il resto del blocco 6 e' invariato (verificato file per file contro la
patch precedente). Stato master + 6A + 6, verificato nel worktree temporaneo: contratto 40/40
verde col config di P5 blocco 2 portato a `lay_under45`; `tsc` 0 errori; `src/lib`,
`components/mike`, `controlroom`, `trading`, `pages/Mike`: 200 file, 3332 verdi, 1 saltato
(preesistente).
