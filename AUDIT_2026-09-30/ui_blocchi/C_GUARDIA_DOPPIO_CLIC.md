# C_GUARDIA_DOPPIO_CLIC - conferma live del «Cash out Safe» inerte per 400 ms (correzione di un reperto della review)

Reperto (review incrociata del 30/09, M2, difetto PREESISTENTE in `CashOutPartita.tsx`): in live il primo clic arma e «Confermo: …» compare nello stesso punto del pulsante, senza attesa: un doppio clic mandava il cash out con soldi veri senza una conferma voluta.

Correzione (delegato C_CASHOUT, dentro la corsia del cash out): stesso schema e STESSA costante di `InterruttoreUscite` (`ATTESA_CONFERMA_USCITE_MS` = 400): dall'armamento il pulsante `cr-cashout-partita-conferma` e' `disabled` e il suo clic e' ignorato per 400 ms. In PAPER un clic basta, come prima. Testid e resto del comportamento invariati.

File: `frontend/src/components/controlroom/CashOutPartita.tsx`, `CashOutPartita.test.tsx`. La patch si applica DOPO `C_P12b.patch`.

Test: nuovi «in LIVE un DOPPIO clic non manda (conferma inerte per 400 ms), dopo l'attesa si'» e «in PAPER nulla cambia»; cambiato (voluto) «in LIVE il SECONDO clic manda»: ora fa passare il tempo prima del secondo clic.

## Verifica del coordinatore UI (admin-07), 30/09 19:21
- Diff riletto per intero (28 righe di produzione). Applicata sul mio albero integrato (con T_P5 impilato): `CashOutPartita.test.tsx` + `CashOutGlobale.montaggio.test.tsx` + `pages/ControlRoom.test.tsx` = 146 test verdi.
- Mutazioni MIE, ROSSE, ripristino da copia con `cmp`: guardia tolta (`troppoPresto = false`) -> 1 rosso (il test del doppio clic); attesa applicata anche in paper -> 3 rossi.
- tsc sull'albero con la guardia: NON rilanciato da solo (modifica di 28 righe con tipi gia' usati): entra nel tsc della review finale sul commit F.
- Non verificato: l'app a schermo.
