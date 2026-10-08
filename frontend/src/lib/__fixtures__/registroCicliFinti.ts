// ============================================================================
// 08/10 (cantiere 10) — l'esito «4 cicli del bot, due coppie che si toccano
// nello stesso istante» (la forma del difetto visto dall'utente sul Match Replay
// 35768297: ciclo 1 chiuso alle 23:04:21 e rientro automatico alle 23:04:21.752,
// fusi in un solo ciclo dalla regola «da piatto a piatto»).
// Costruito da una riga VERA e da un ciclo dichiarato VERO dell'esito della
// media under sulla 35797769 (stesse chiavi e tipi): cambiano solo i valori.
// ============================================================================
import type { CicloDichiarato, EsitoBot, RigaBot } from '@/lib/replayBot';
import mediaClicMulti69 from './replay_pro/esito_media_clic_multi_69.json';

export const MULTI_VERO = mediaClicMulti69 as unknown as EsitoBot;
const VERA = MULTI_VERO.righe[0];

export function rigaDaVera(o: Partial<RigaBot> & { _ms: number; _ordine: string }): RigaBot {
    return {
        ...VERA, bet_id: o._ordine, client_order_ref: `d30755a527963-${o._ordine}`, size_matched: 0, size_remaining: o.size ?? VERA.size ?? 0,
        size_cancelled: 0, size_lapsed: 0, size_voided: 0, average_price_matched: 0, status: 'EXECUTABLE',
        matched_at: null, _trade_id: `t-${o._ordine}`, _sostituisce: null, ...o,
    } as RigaBot;
}

/** una coppia punta/banca abbinate per intero: la punta nasce a `da`, la banca e' abbinata a `a` */
export function coppia(k: string, da: number, a: number): RigaBot[] {
    return [
        rigaDaVera({ _ms: da, _ordine: `${k}p`, side: 'back', price: 2.2, size: 10, status: 'PENDING' }),
        rigaDaVera({ _ms: da + 100, _ordine: `${k}p`, side: 'back', price: 2.2, size: 10, size_matched: 10, average_price_matched: 2.2, size_remaining: 0, status: 'EXECUTION_COMPLETE' }),
        rigaDaVera({ _ms: da + 100, _ordine: `${k}b`, side: 'lay', price: 2.16, size: 10.19, size_remaining: 10.19 }),
        rigaDaVera({ _ms: a, _ordine: `${k}b`, side: 'lay', price: 2.16, size: 10.19, size_matched: 10.19, average_price_matched: 2.16, size_remaining: 0, status: 'EXECUTION_COMPLETE' }),
    ];
}

const D0 = MULTI_VERO.cicli_bot![0];
/** il ciclo come lo dichiara il bot (`riepilogo_cicli_media`): punta 10 @2,20 e
 *  banca 10,19 @2,16 abbinate = min(+0,1796, +0,19) = lordo +0,18, netto 0,18 x 0,95 */
export function dichiarato(n: number, k: string, da: number, a: number, origine: string): CicloDichiarato {
    return {
        ...D0, ciclo: n, inizio_ms: da - 50, fine_ms: a, ordini_id: [`${k}p`, `${k}b`], origine, lordo: 0.18, netto: 0.17,
        clic: origine === 'clic' ? `clic-${n}-${da - 60}` : null, prima_punta_ordine: `${k}p`, prima_punta_ms: da,
    };
}

/** ciclo 1 chiuso a 2000 e rientro automatico NELLO STESSO ISTANTE (2000); ciclo 3
 *  chiuso a 6000 e rientro automatico a 6000 */
export const RIGHE_4 = [...coppia('a', 1000, 2000), ...coppia('b', 2000, 3000), ...coppia('c', 5000, 6000), ...coppia('d', 6000, 7000)];
export const ESITO_4: EsitoBot = {
    ...MULTI_VERO, righe: RIGHE_4, ordini: 8, clic_bot: null,
    // il conto del bot: 4 x 0,1796 = 0,7184 -> lordo 0,72, commissione 0,04, netto 0,68
    conto_dichiarato: { ...MULTI_VERO.conto_dichiarato!, lordo: 0.72, commissione: 0.04, netto: 0.68 },
    cicli_bot: [
        dichiarato(1, 'a', 1000, 2000, 'clic'), dichiarato(2, 'b', 2000, 3000, 'rientro_automatico'),
        dichiarato(3, 'c', 5000, 6000, 'clic'), dichiarato(4, 'd', 6000, 7000, 'rientro_automatico'),
    ],
};
