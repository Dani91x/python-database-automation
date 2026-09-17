// ============================================================================
// soloTennis.ts — «NELLA SCHEDA TENNIS PARTE SOLO IL TENNIS, A 3 EURO».
//
// Richiesta dell'utente, 15/09: «nella scheda "tennis" voglio vedere solo il
// bot di tennis, e quando lo attivo dalla scheda tennis deve partire solo lui
// come ieri, sempre con 3 euro di stake».
//
// ⚠️ 16/09 — NON E' PIU' UN PERCORSO A PARTE. Da quando ogni strategia ha il
// suo interruttore (`lib/interruttori.ts`), «solo il tennis» e' un CASO
// PARTICOLARE dello stesso modello: tennis acceso nella modalita' scelta,
// base/esatto/punta spente, `model` e `manual` in prova. Le due mappe
// (`variants` = chi apre, `strategy_modes` = con che soldi) le scrive
// `paramsAccensioni`, una volta sola, per tutti. Qui restano soltanto le tre
// cose che questo gesto aggiunge e che l'utente ha chiesto per nome.
//
// «COME IERI» non e' un modo di dire: e' la configurazione scritta in
// `Betfair/safe_strategy/SESSIONE_LIVE_TENNIS_2026-09-14.md`, riga per riga —
//   · strategie in live: **solo `tennis`**; base, esatto, punta, model,
//     manual → `paper`;
//   · stake del tennis = 3,00 €;
//   · Mike e Omega non si toccano: da qui non partono e basta.
//
// ⚠️ REPERTO 17/09 sera — `auto_trade_tennis` NON E' L'INTERRUTTORE DELLE
// ENTRATE DELLA STRATEGIA S TENNIS. La Strategia S tennis (righe
// `strategy='tennis'`, le SUE entrate) si accende SOLO da `variants` — quello
// che questa scheda scrive gia' qui sopra. `auto_trade_tennis` governa il
// SECONDO motore, indipendente: le "opportunita' di modello tennis" (righe
// `strategy='model'`, `meta.kind='tennis'`, oggi sempre in paper perche'
// `strategy_modes.model` non e' mai 'live'). Fino al 17/09 questa scheda
// forzava quell'interruttore a `true` credendo servisse alla Strategia S: sul
// campo il trader ha visto 3 righe (2 paper del modello + 1 live della
// Strategia S) e ha creduto a 3 ingressi della stessa strategia. Da qui in poi
// la scheda «solo tennis» NON tocca piu' `auto_trade_tennis`: lo lascia
// esattamente come lo trova.
// ============================================================================
import { fmtMoney } from '@/lib/format';
import {
    paramsAccensioni, leggiChiave, scriviChiave, STRATEGIE_SAFE_TUTTE,
    type Accensioni, type Modalita,
} from '@/lib/interruttori';

/**
 * Lo stake del tennis, in euro. **Fisso**, per decisione dell'utente
 * (14/09: «stake fisso», ribadito il 15/09: «sempre con 3 euro di stake»).
 */
export const STAKE_TENNIS = 3;

/**
 * La chiave dello stake del tennis nei parametri del servizio.
 *
 * ⚠️ B.5, 16/09 — prima era `stake.backSize`, che pero' valeva **insieme** per
 * TENNIS e PUNTA: cambiare lo stake del tennis cambiava anche quello della
 * punta, in silenzio. Adesso ogni strategia ha la sua chiave e il motore la
 * legge per NOME (`engine.stake_di_strategia`); se manca ricade su quella per
 * lato, com'era prima, quindi nessun importo cambia da solo.
 */
export const CHIAVE_STAKE_TENNIS = 'stake.per_strategia.tennis';
/** il ripiego dichiarato: la chiave per LATO, valida finche' non c'e' la sua */
export const CHIAVE_STAKE_TENNIS_PER_LATO = 'stake.backSize';

/** Il nome della strategia del tennis dentro Safe. */
export const STRATEGIA_TENNIS = 'tennis';

/** Tutte le strategie che Safe conosce. Una sola lista, in `lib/interruttori`. */
export const STRATEGIE_SAFE = STRATEGIE_SAFE_TUTTE;

/** Le accensioni del gesto «solo tennis»: lui acceso, le altre tre spente. */
export function accensioniSoloTennis(modalita: Modalita): Accensioni {
    return { base: null, esatto: null, punta: null, tennis: modalita };
}

/** Lo stake con cui il tennis entra ADESSO: il suo, o quello per lato. */
export function stakeTennisEffettivo(correnti: Record<string, unknown> | null | undefined): number | null {
    return leggiChiave(correnti, CHIAVE_STAKE_TENNIS)
        ?? leggiChiave(correnti, CHIAVE_STAKE_TENNIS_PER_LATO);
}

/**
 * L'unica cosa che il gesto «solo tennis» AGGIUNGE alle accensioni: stake a
 * 3,00 € sulla chiave del tennis. Tutto il resto (tetti, uscite, approvazione
 * delle chiusure, `auto_trade_tennis`) passa intatto.
 *
 * ⚠️ 17/09 sera — QUI PRIMA SI FORZAVA `auto_trade_tennis = true`, credendo
 * fosse l'interruttore delle entrate della Strategia S tennis. Non lo e': e'
 * il secondo motore (opportunita' di modello, paper). La scheda non lo tocca
 * piu' (vedi la nota in testa al file).
 */
export function extraSoloTennis(p: Record<string, unknown>): Record<string, unknown> {
    // LO STAKE — 3,00 € sulla chiave del TENNIS. `stake.backSize` non si tocca:
    // e' il ripiego di chi non ha ancora una chiave sua (la punta).
    return scriviChiave(p, CHIAVE_STAKE_TENNIS, STAKE_TENNIS);
}

/**
 * I parametri con cui far partire **solo il tennis**, a partire da quelli
 * correnti del servizio.
 *
 * Si parte SEMPRE dall'oggetto corrente: `safe_activate` fa
 * `coalesce(p_params, params)`, quindi quello che mandiamo SOSTITUISCE
 * l'intera colonna. Mandare le sole chiavi del tennis cancellerebbe tetti di
 * rischio, uscite e approvazione delle chiusure.
 */
export function paramsSoloTennis(
    correnti: Record<string, unknown>, modalita: Modalita,
): Record<string, unknown> {
    return extraSoloTennis(paramsAccensioni(correnti, accensioniSoloTennis(modalita), 'prova'));
}

/**
 * Che cosa cambierebbe l'avvio dalla scheda tennis, in parole, rispetto a
 * quello che il servizio ha ADESSO. Serve al pannello per dirlo PRIMA del
 * clic: un comando che tocca i soldi veri non si spiega dopo.
 * Lista vuota = non cambia niente oltre alla modalità.
 */
export function differenzeSoloTennis(
    correnti: Record<string, unknown> | null | undefined, modalita: Modalita,
): string[] {
    if (correnti == null || Object.keys(correnti).length === 0) return [];
    const fuori: string[] = [];

    const modi = (correnti.strategy_modes && typeof correnti.strategy_modes === 'object')
        ? (correnti.strategy_modes as Record<string, unknown>) : {};
    const inLive = Object.entries(modi)
        .filter(([n, m]) => n !== STRATEGIA_TENNIS && String(m ?? '').toLowerCase() === 'live')
        .map(([n]) => n);
    if (inLive.length) fuori.push(`${inLive.join(', ')} → in prova`);

    const stakeOra = stakeTennisEffettivo(correnti);
    if (typeof stakeOra !== 'number' || Math.abs(stakeOra - STAKE_TENNIS) > 0.0001) {
        // il denaro si scrive SEMPRE con `fmtMoney`: un euro formattato a mano
        // in questa pagina finisce accanto a uno formattato dal design system,
        // e due grafie diverse per la stessa cifra si leggono come due cifre.
        fuori.push(`stake → ${fmtMoney(STAKE_TENNIS)}`);
    }

    // ⚠️ 16/09 — `variants` adesso dice CHI E' ACCESO, quindi «solo tennis»
    // SPEGNE base, esatto e punta. Va detto prima del clic, non scoperto dopo.
    const varianti = Array.isArray(correnti.variants) ? correnti.variants.map(String) : [];
    const spente = varianti.filter((v) => v !== STRATEGIA_TENNIS);
    if (spente.length) fuori.push(`${spente.join(', ')} → spente`);
    if (varianti.length && !varianti.includes(STRATEGIA_TENNIS)) fuori.push('tennis → abilitato ad aprire');

    if (modalita === 'live') fuori.push('tennis → soldi veri');
    return fuori;
}

/**
 * Le strategie di Safe che stanno operando con soldi veri ADESSO, tennis
 * escluso.
 *
 * ⚠️ REVIEW 15/09 — la nota della scheda tennis diceva al PRESENTE che «il
 * calcio resta in prova». È vero solo DOPO un avvio da lì: con Safe già acceso
 * in live sul calcio (dalla sua pagina), la scheda mostrava una riga sola
 * chiamata «Tennis» e nessun segno che lo stesso servizio stesse piazzando
 * ordini reali sul calcio. Una plancia ristretta non deve nascondere denaro
 * vero che si muove altrove.
 *
 * Il `mode` del servizio resta un TETTO: in prova la risposta è sempre vuota.
 */
export function altreInLiveAdesso(
    modalitaServizio: string | null | undefined,
    modi: Record<string, string> | null | undefined,
): string[] {
    if (String(modalitaServizio ?? '').toLowerCase() !== 'live') return [];
    return Object.entries(modi ?? {})
        .filter(([n, m]) => n !== STRATEGIA_TENNIS && String(m ?? '').toLowerCase() === 'live')
        .map(([n]) => n);
}
