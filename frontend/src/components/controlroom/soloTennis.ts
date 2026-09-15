// ============================================================================
// soloTennis.ts — «NELLA SCHEDA TENNIS PARTE SOLO IL TENNIS, A 3 EURO».
//
// Richiesta dell'utente, 15/09: «nella scheda "tennis" voglio vedere solo il
// bot di tennis, e quando lo attivo dalla scheda tennis deve partire solo lui
// come ieri, sempre con 3 euro di stake».
//
// PERCHÉ SERVE UN FILE, e non un `if` dentro il pannello: il servizio Safe è
// UNO SOLO e porta dentro di sé sia il tennis sia le tre strategie del calcio.
// `safe_activate('live')` da solo accende il SERVIZIO: quali strategie escano
// con soldi veri lo decide `strategy_modes`. Senza questa mappa, «avvia il
// tennis in live» accendeva anche base, esatto e punta.
//
// «COME IERI» non è un modo di dire: è la configurazione scritta in
// `Betfair/safe_strategy/SESSIONE_LIVE_TENNIS_2026-09-14.md`, riga per riga —
//   · strategie in live: **solo `tennis`**; base, esatto, punta, model,
//     manual → `paper`;
//   · `stake.backSize = 3,00 €` (è QUESTO che muove il tennis: `backSize`
//     entra su chi punta, `laySize` su chi banca ed è del calcio);
//   · entrate automatiche (`auto_trade_tennis = true`, quel giorno era spento
//     e il bot non entrava);
//   · Mike e Omega non si toccano: da qui non partono e basta.
//
// COSA NON SI TOCCA, di proposito: `variants` (chi può APRIRE) si arricchisce
// mai si sfoltisce — togliere una variante al calcio sarebbe alterare una
// strategia che l'utente non ha chiesto di cambiare; `tennis_exit_approval`,
// i tetti di rischio e tutto il resto passano intatti.
// ============================================================================
import { fmtMoney } from '@/lib/format';
import type { Modalita } from '@/components/controlroom/PannelloBot';

/**
 * Lo stake del tennis, in euro. **Fisso**, per decisione dell'utente
 * (14/09: «stake fisso», ribadito il 15/09: «sempre con 3 euro di stake»).
 * È `stake.backSize`, la chiave che il servizio legge davvero per chi punta.
 */
export const STAKE_TENNIS = 3;

/** La chiave dello stake del tennis nei parametri del servizio. */
export const CHIAVE_STAKE_TENNIS = 'stake.backSize';

/** Il nome della strategia del tennis dentro Safe. */
export const STRATEGIA_TENNIS = 'tennis';

/**
 * Tutte le strategie che Safe conosce (`BotParamsSheet.MODE_STRATEGIES`).
 * Servono per NOME: una strategia che non compare nella mappa eredita il
 * `mode` del servizio, e in live quello significa soldi veri.
 */
export const STRATEGIE_SAFE = ['base', 'esatto', 'punta', 'tennis', 'model', 'manual'] as const;

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
    const out: Record<string, unknown> = { ...correnti };

    // 1. MODALITÀ PER STRATEGIA — il tennis nella modalità scelta, TUTTE le
    //    altre in prova. Si spengono anche le chiavi che non conosciamo: se il
    //    servizio ne aggiunge una domani, «solo il tennis» deve restare vero.
    const precedenti = (correnti.strategy_modes && typeof correnti.strategy_modes === 'object'
        && !Array.isArray(correnti.strategy_modes))
        ? (correnti.strategy_modes as Record<string, unknown>) : {};
    const modi: Record<string, string> = {};
    for (const nome of new Set([...Object.keys(precedenti), ...STRATEGIE_SAFE])) {
        modi[nome] = nome === STRATEGIA_TENNIS ? modalita : 'paper';
    }
    out.strategy_modes = modi;

    // 2. LO STAKE — 3,00 € fissi su `stake.backSize`. `laySize` è del calcio
    //    (base ed esatto bancano) e non si tocca.
    const stake = (correnti.stake && typeof correnti.stake === 'object' && !Array.isArray(correnti.stake))
        ? { ...(correnti.stake as Record<string, unknown>) } : {};
    stake.backSize = STAKE_TENNIS;
    out.stake = stake;

    // 3. LE ENTRATE AUTOMATICHE — il 14/09 questo interruttore era spento e il
    //    bot, acceso e regolare, non entrava su niente. Avviarlo senza sarebbe
    //    accendere un motore in folle.
    out.auto_trade_tennis = true;

    // 4. IL TENNIS DEVE POTER APRIRE — ma `variants` si TOCCA SOLO SE C'È.
    //
    //    ⚠️ REVIEW 15/09, GRAVE — qui prima si scriveva sempre, e quando la
    //    colonna NON conteneva `variants` il risultato era `['tennis']`:
    //    `safe_activate` sostituisce l'intera colonna e
    //    `normalize_variants(['tennis'])` è una lista valida e non vuota,
    //    quindi base, esatto e punta restavano spente PER SEMPRE, anche in
    //    prova. Il default delle quattro varianti il servizio lo mette in
    //    LETTURA (`bot_service.normalize_variants`), non sul database: una
    //    chiave assente non è una lista vuota, è «usa il default», e il
    //    default il tennis ce l'ha già dentro.
    if (Array.isArray(correnti.variants)) {
        const varianti = (correnti.variants as unknown[]).map((v) => String(v)).filter(Boolean);
        // si arricchisce, mai si sfoltisce; e una lista vuota si lascia
        // com'è, perché è il servizio a rimpiazzarla col default.
        if (varianti.length > 0 && !varianti.includes(STRATEGIA_TENNIS)) {
            out.variants = [...varianti, STRATEGIA_TENNIS];
        }
    }

    return out;
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

    const stakeOra = (correnti.stake as Record<string, unknown> | undefined)?.backSize;
    if (typeof stakeOra !== 'number' || Math.abs(stakeOra - STAKE_TENNIS) > 0.0001) {
        // il denaro si scrive SEMPRE con `fmtMoney`: un euro formattato a mano
        // in questa pagina finisce accanto a uno formattato dal design system,
        // e due grafie diverse per la stessa cifra si leggono come due cifre.
        fuori.push(`stake → ${fmtMoney(STAKE_TENNIS)}`);
    }

    if (correnti.auto_trade_tennis !== true) fuori.push('entrate automatiche → accese');

    const varianti = Array.isArray(correnti.variants) ? correnti.variants.map(String) : [];
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
