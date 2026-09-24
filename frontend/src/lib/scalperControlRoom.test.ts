// ============================================================================
// scalperControlRoom.test.ts - lo scalper calcio in Control Room: le funzioni
// pure che trasformano sessioni e ordini in stato, righe e soldi (24/09).
//
// I FINTI PARLANO COME IL VERO: una sessione ha le chiavi di
// `to_jsonb(scalper_control)` + le quattro aggiunte dalla RPC
// (`get_scalper_control_room`, migrations/scalper_control_room_2026-09-24.sql);
// un ordine ha le colonne della SELECT della stessa RPC su betfair_live_orders.
// Nessuna rete: le due chiamate si collaudano altrove.
// ============================================================================
import { describe, it, expect } from 'vitest';
import {
    statoBotScalper, ordiniDellaSessione, esposizioneScalper, chiusuraScalper,
    pnlRealeOrdini, pnlLordoBot, modalitaSessione, idSessione, notaSessioneScalper,
} from '@/lib/scalperControlRoom';
import type { CalcioScanPayload } from '@/lib/safeStrategyScan';
import { sessione, ordine } from '@/lib/__fixtures__/scalperFinti';

describe('statoBotScalper - la riga della plancia dalle sessioni', () => {
    it('nessuna sessione: fermo, modalita non dichiarata', () => {
        const s = statoBotScalper([]);
        expect(s).toMatchObject({ inCorsa: false, stato: 'stopped', modalita: null, vive: 0 });
    });

    it('una sessione running in prova: acceso, prova', () => {
        const s = statoBotScalper([sessione()]);
        expect(s).toMatchObject({ inCorsa: true, stato: 'running', modalita: 'paper', misto: false });
        expect(s.battitoAt).toBe('2026-09-24T12:10:00+00:00');
    });

    it('basta UNA sessione viva con soldi veri perche la riga dica soldi veri (e misto)', () => {
        const s = statoBotScalper([
            sessione({ event_id: '1' }),
            sessione({ event_id: '2', dry_run: false, status: 'armed' }),
        ]);
        expect(s.modalita).toBe('live');
        expect(s.misto).toBe(true);
        expect(s.attive).toBe(2);
    });

    it('solo una sessione che si sta fermando: non acceso, stato stopping', () => {
        const s = statoBotScalper([sessione({ status: 'stopping' })]);
        expect(s).toMatchObject({ inCorsa: false, stato: 'stopping', vive: 1, attive: 0 });
    });

    it('le sessioni ferme o finite non accendono niente e non danno modalita', () => {
        const s = statoBotScalper([
            sessione({ status: 'stopped', dry_run: false }), sessione({ status: 'done' }),
            sessione({ status: 'error' }),
        ]);
        expect(s).toMatchObject({ inCorsa: false, stato: 'stopped', modalita: null });
    });
});

describe('ordiniDellaSessione - paper e live mai mischiati, riarmo separato', () => {
    it('prende solo la partita, la modalita e gli ordini dopo requested_at', () => {
        const s = sessione();
        const tenuti = ordiniDellaSessione(s, [
            ordine({ id: 1 }),
            ordine({ id: 2, mode: 'live' }),                                  // altra modalita
            ordine({ id: 3, event_id: '999' }),                               // altra partita
            ordine({ id: 4, placed_at: '2026-09-24T11:59:59+00:00' }),        // sessione di prima
            ordine({ id: 5, placed_at: null, updated_at: null }),             // senza orario
        ]);
        expect(tenuti.map((o) => o.id)).toEqual([1]);
    });

    it('modalita ignota = nessun ordine (non si attribuisce alla cieca)', () => {
        expect(ordiniDellaSessione(sessione({ dry_run: null }), [ordine()])).toEqual([]);
        expect(modalitaSessione({ dry_run: null })).toBeNull();
    });
});

describe('esposizioneScalper - aritmetica dell exchange sull ABBINATO', () => {
    it('un back abbinato: rischio lo stake, vinco (p-1)*m', () => {
        const e = esposizioneScalper([ordine({ size_matched: 10, average_price_matched: 2.5 })]);
        expect(e.selezioni).toEqual([{ marketId: '1.200', selectionId: 47972, win: 15, lose: -10, netto: 10 }]);
        expect(e.responsabilita).toBe(10);
        expect(e.abbinato).toBe(10);
    });

    it('un lay abbinato: la responsabilita e (p-1)*m', () => {
        const e = esposizioneScalper([ordine({ side: 'lay', size_matched: 10, average_price_matched: 3 })]);
        expect(e.responsabilita).toBe(20);
    });

    it('back e lay sulla stessa selezione (lo scalp): responsabilita = caso peggiore residuo', () => {
        const e = esposizioneScalper([
            ordine({ id: 1, side: 'back', size_matched: 10, average_price_matched: 2.02 }),
            ordine({ id: 2, side: 'lay', size_matched: 10, average_price_matched: 2.0 }),
        ]);
        // vince: +10,20 - 10,00 = +0,20 ; perde: -10 + 10 = 0 -> nessun rischio
        expect(e.selezioni[0].win).toBe(0.2);
        expect(e.selezioni[0].lose).toBe(0);
        expect(e.responsabilita).toBe(0);
    });

    it('il residuo sul book NON e esposizione, ma si conta come in attesa', () => {
        const e = esposizioneScalper([ordine({
            size: 10, size_matched: 0, size_remaining: 10, status: 'EXECUTABLE',
        })]);
        expect(e.selezioni).toEqual([]);
        expect(e.responsabilita).toBe(0);
        expect(e.inAttesa).toBe(1);
        expect(e.residuo).toBe(10);
        expect(e.chiesto).toBe(10);
    });
});

/** Un payload di scansione del calcio col Match Odds in `odds` (chiavi del
 *  vero: `CalcioScanPayload.odds.<lato>` con `selection_id`/`back`/`lay`/
 *  `back_size`/`lay_size`), nessun blocco CS/OU. */
function feed(back: number | null, lay: number | null): CalcioScanPayload {
    return {
        cs: null, ht: null, ou: [],
        odds: {
            home: { selection_id: 47972, ltp: 2.0, back, lay, back_size: 50, lay_size: 40 },
            draw: null, away: null,
        },
    } as unknown as CalcioScanPayload;
}

describe('chiusuraScalper - se chiudo ora, con la matematica del cash out', () => {
    it('un back da coprire: si banca al LAY di adesso e il bloccato e uguale sui due esiti', () => {
        const esp = esposizioneScalper([ordine({ size_matched: 10, average_price_matched: 2.5 })]);
        const c = chiusuraScalper(esp, feed(2.0, 2.02));
        expect(c).not.toBeNull();
        expect(c!.lato).toBe('lay');
        expect(c!.prezzo).toBe(2.02);
        // hedge = (15 - (-10)) / 2,02 = 12,38 -> vince 15 - 12,38*1,02 = 2,37 ; perde -10 + 12,38 = 2,38
        expect(c!.bloccabile).toBeCloseTo(2.37, 2);
    });

    it('senza prezzo nel feed: niente numero (mai un parziale spacciato per il totale)', () => {
        const esp = esposizioneScalper([ordine({ size_matched: 10, average_price_matched: 2.5 })]);
        const c = chiusuraScalper(esp, feed(2.0, null));
        expect(c!.prezzo).toBeNull();
        expect(c!.bloccabile).toBeNull();
    });

    it('gia tutto coperto: il bloccato e certo anche senza prezzo', () => {
        const esp = esposizioneScalper([
            ordine({ id: 1, side: 'back', size_matched: 10, average_price_matched: 2.02 }),
            ordine({ id: 2, side: 'lay', size_matched: 10.1, average_price_matched: 2.0 }),
        ]);
        const c = chiusuraScalper(esp, null);
        expect(c!.prezzo).toBeNull();
        expect(c!.bloccabile).toBe(Math.min(esp.selezioni[0].win, esp.selezioni[0].lose));
    });

    it('niente di abbinato: nessuna chiusura', () => {
        expect(chiusuraScalper(esposizioneScalper([]), feed(2, 2.02))).toBeNull();
    });
});

describe('pnlRealeOrdini - il P&L REALE di Betfair per bet_id', () => {
    const giorno = (iso: string) => iso.slice(0, 10);
    it('completo solo quando OGNI ordine abbinato ha il suo pnl_betfair', () => {
        const a = pnlRealeOrdini([
            ordine({ id: 1, mode: 'live', pnl_betfair: 0.5, pnl_betfair_settled_at: '2026-09-24T20:00:00+00:00' }),
            ordine({ id: 2, mode: 'live', pnl_betfair: null }),
        ], giorno, '2026-09-24');
        expect(a).toMatchObject({ reale: 0.5, completo: false, regolatiOggi: 0.5 });
        const b = pnlRealeOrdini([
            ordine({ id: 1, mode: 'live', bet_id: '11', pnl_betfair: 0.5, pnl_betfair_settled_at: '2026-09-24T20:00:00+00:00' }),
            ordine({ id: 2, mode: 'live', bet_id: '12', pnl_betfair: -0.3, pnl_betfair_settled_at: '2026-09-23T20:00:00+00:00' }),
            ordine({ id: 3, mode: 'live', size_matched: 0, pnl_betfair: null }), // mai abbinato
        ], giorno, '2026-09-24');
        expect(b).toMatchObject({ reale: 0.2, completo: true, regolatiOggi: 0.5, betIds: ['11', '12'] });
    });

    it('il paper non ha un reale: nessun numero, mai completo', () => {
        const p = pnlRealeOrdini([ordine()], giorno, '2026-09-24');
        expect(p).toMatchObject({ reale: null, completo: false, regolatiOggi: null });
    });
});

describe('lordo del bot, id e nota', () => {
    it('il lordo somma maker, sniper e theta (e resta lordo)', () => {
        expect(pnlLordoBot(sessione({ stats: { pnl_locked: 0.4, sniper_pnl_locked: 0.1, theta_pnl_locked: -0.05 } })))
            .toBe(0.45);
        expect(pnlLordoBot(sessione({ stats: null }))).toBeNull();
    });

    it('id numerico = event_id; un event_id non numerico non si comanda', () => {
        expect(idSessione('35760084')).toBe(35760084);
        expect(idSessione('ev-1')).toBeNull();
        expect(idSessione('')).toBeNull();
    });

    it('la nota dichiara stato, ultima attivita, battito, lordo, slot non pubblicato, FONTE ed ETA', () => {
        const now = Date.parse('2026-09-24T12:10:05+00:00');
        const n = notaSessioneScalper(sessione(), now, 12);
        expect(n).toContain('sessione running');
        expect(n).toContain("ultima attivita' fill 15 s fa");
        expect(n).toContain('battito 5 s fa');
        expect(n).toContain('+0.40 EUR lordo');
        expect(n).toContain('stato dello slot non pubblicato dal bot');
        expect(n).toContain('fonte: database, letto 12 s fa');
        expect(notaSessioneScalper(sessione(), now, null)).toContain('letto mai');
    });
});
