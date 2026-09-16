// ============================================================================
// consapevolezzaOrdine.contratto.test.ts — C.12b: IL CONTRATTO kind <-> etichetta.
//
// Il 16/09 i due test Python che presidiavano questo contratto portavano una
// LISTA DEL DEBITO (`KIND_IN_ATTESA_DI_UI`) con dentro i kind che il backend
// scriveva e la UI non traduceva. Quella lista e' stata CANCELLATA insieme a
// questo lavoro, e i due test Python sono tornati a mordere su tutti i kind.
// Qui c'e' il loro equivalente dal lato TypeScript: se qualcuno toglie una di
// queste etichette, o la fa cadere nel traduttore parola-per-parola, questo
// file diventa ROSSO senza bisogno di lanciare pytest.
//
// I kind e le chiavi dei payload sono quelli che i servizi scrivono DAVVERO:
//   · place_rifiutato   omega_service.py:1189 · execution.py:558,579 · mike/service.py:702,1085
//   · place_parziale    omega_service.py:1662 · execution.py:604 · bot_service.py:944
//   · cancel_richiesto  omega_service.py:2347 · bot_service.py:985 · mike/service.py:3096
//   · cancel_esito      omega_service.py:2354 · bot_service.py:980,1001 · mike/service.py:3103
//   · fill_resting      mike/service.py:1424,2554,3126
// ============================================================================
import { describe, it, expect } from 'vitest';
import { ACTIVITY_BASE, activityMeta, activityLineGeneric } from './tradeStatus';
import {
    OMEGA_ACTIVITY_EXTRA, activityMeta as omegaMeta, activityLine as omegaLine,
} from './omega';
import { MIKE_ACTIVITY_KINDS, MIKE_ACTIVITY_EXTRA, mikeActivityLine } from './mike';
import {
    SAFE_ACTIVITY_EXTRA, safeActivityMeta, safeActivityLine,
} from '@/components/safestrategy/safeActivity';

/** i kind della consapevolezza dell'ordine, per bot che li scrive */
const OMEGA_KINDS = ['place_rifiutato', 'place_parziale', 'cancel_richiesto', 'cancel_esito'];
const SAFE_KINDS = ['place_rifiutato', 'place_parziale', 'cancel_richiesto', 'cancel_esito'];
const MIKE_KINDS = ['place_rifiutato', 'fill_resting', 'cancel_richiesto', 'cancel_esito'];

/** un'etichetta non deve essere la chiave inglese, ne il fallback a parole */
function etichettaVera(label: string, kind: string) {
    expect(label, kind).not.toMatch(/kind sconosciuto/);
    expect(label, kind).not.toBe(kind.toUpperCase());
    expect(label, kind).not.toBe(kind.replace(/_/g, ' ').toUpperCase());
    expect(label.trim().length, kind).toBeGreaterThan(3);
}

describe('OMEGA — ogni kind nuovo ha la sua etichetta italiana', () => {
    it('nessuno cade nel traduttore parola per parola', () => {
        for (const k of OMEGA_KINDS) {
            const esplicito = OMEGA_ACTIVITY_EXTRA[k] ?? ACTIVITY_BASE[k];
            expect(esplicito, `kind senza etichetta ESPLICITA: ${k}`).toBeTruthy();
            etichettaVera(omegaMeta(k).label, k);
        }
    });

    it('il PARZIALE porta i suoi numeri in riga, non un JSON nudo', () => {
        // omega_service.py:1662 — le chiavi sono queste, non altre
        const riga = omegaLine({
            id: 1, kind: 'place_parziale', at: '2026-09-16T10:00:00Z',
            payload: {
                event_id: '3600', trade_id: 12, critical: true,
                size_requested: 5, size_matched: 2, size_remaining: 3,
                avg_price_matched: 2.38,
                nota: 'parziale 2.00 su 5.00, residuo 3.00 vivo',
            },
        } as never, 'Roma v Lazio');
        expect(riga).toContain('chiesti 5,00 €');
        expect(riga).toContain('abbinati 2,00 € @ 2,38');
        expect(riga).toContain('residuo vivo 3,00 €');
    });

    it('il RIFIUTO mostra il codice di Betfair in chiaro', () => {
        const riga = omegaLine({
            id: 2, kind: 'place_rifiutato', at: '2026-09-16T10:00:00Z',
            payload: { event_id: '3600', trade_id: 12, leg: 'ft_cs', error_code: 'INSUFFICIENT_FUNDS' },
        } as never, null);
        expect(riga).toContain('codice Betfair INSUFFICIENT_FUNDS');
    });

    it('l ANNULLO dice se Betfair lo ha confermato (non confermato != annullato)', () => {
        const riga = omegaLine({
            id: 3, kind: 'cancel_esito', at: '2026-09-16T10:00:00Z',
            payload: { trade_id: 12, bet_id: '99', critical: true, confermato: false, riletto: false },
        } as never, null);
        expect(riga).toContain('annullo NON confermato');
    });
});

describe('SAFE — ogni kind nuovo ha la sua etichetta italiana', () => {
    it('nessuno cade nel traduttore parola per parola', () => {
        for (const k of SAFE_KINDS) {
            expect(SAFE_ACTIVITY_EXTRA[k], `kind non mappato: ${k}`).toBeTruthy();
            etichettaVera(safeActivityMeta(k).label, k);
        }
    });

    it('rifiuto e annullo sono CRITICI: non si seppelliscono nella lista', () => {
        expect(safeActivityMeta('place_rifiutato').critical).toBe(true);
        expect(safeActivityMeta('place_parziale').critical).toBe(true);
        expect(safeActivityMeta('cancel_esito').critical).toBe(true);
    });

    it('il PARZIALE della riconciliazione porta i numeri veri', () => {
        // bot_service.py:944 — `fonte: 'riconciliazione'`
        const riga = safeActivityLine({
            trade_id: 7, event_id: '3600', mode: 'live', side: 'back', bet_id: '99',
            size_requested: 5, size_matched: 2, size_remaining: 3, avg_price_matched: 2.38,
            critical: true, fonte: 'riconciliazione',
            nota: 'parziale 2.00 su 5.00, residuo 3.00 vivo',
        });
        expect(riga).toContain('chiesti 5,00 €');
        expect(riga).toContain('abbinati 2,00 € @ 2,38');
        expect(riga).toContain('residuo vivo 3,00 €');
    });

    it('il rifiuto del place-and-trim mostra il codice', () => {
        // execution.py:558 — `percorso: 'submin'`
        const riga = safeActivityLine({
            trade_id: 7, mode: 'live', side: 'back', price: 3.1, size: 2,
            error_code: 'INVALID_PROFIT_RATIO', percorso: 'submin',
            nota: 'Betfair ha rifiutato: nessun ordine a mercato',
        });
        expect(riga).toContain('codice Betfair INVALID_PROFIT_RATIO');
    });
});

describe('MIKE — ogni kind nuovo e DICHIARATO e tradotto', () => {
    it('i kind sono nell elenco del contratto (lo stesso che legge pytest)', () => {
        for (const k of ['cancel_richiesto', 'cancel_esito']) {
            expect(MIKE_ACTIVITY_KINDS as readonly string[], `kind non dichiarato: ${k}`).toContain(k);
        }
    });

    it('nessuno cade nel traduttore parola per parola', () => {
        for (const k of MIKE_KINDS) {
            const esplicito = MIKE_ACTIVITY_EXTRA[k] ?? ACTIVITY_BASE[k];
            expect(esplicito, `kind senza etichetta ESPLICITA: ${k}`).toBeTruthy();
            etichettaVera(activityMeta(k, MIKE_ACTIVITY_EXTRA).label, k);
        }
    });

    it('l appoggiata abbinata dice il PARZIALE coi numeri del servizio', () => {
        // mike/service.py:1424 — chiavi: matched, price, size_requested, size_remaining
        const riga = mikeActivityLine('fill_resting', {
            leg: 'L1', role: 'under_entry', matched: 2, price: 2.38, live: true,
            size_requested: 5, size_remaining: 3,
            nota: 'parziale 2.00 su 5.00, residuo 3.00 vivo',
        });
        expect(riga).toContain('2,00 €');
        expect(riga).toContain('su 5,00 € chiesti');
        expect(riga).toContain('residuo vivo 3,00 €');
    });

    it('l annullo NON confermato non viene raccontato come annullato', () => {
        // mike/service.py:3103
        const riga = mikeActivityLine('cancel_esito', {
            leg: 'L1', role: 'under_entry', bet_id: '99', trade_id: 12,
            confermato: false, critical: true,
            nota: 'annullamento NON confermato: la riga resta in riconciliazione',
        });
        expect(riga).toContain('NON confermato');
        expect(riga).not.toContain('ANNULLATO su Betfair');
    });

    it('il rifiuto mostra il codice di Betfair', () => {
        const riga = mikeActivityLine('place_rifiutato', {
            leg: 'L1', role: 'over_cover', critical: true, reason: 'resting_rifiutata',
            order_status: 'EXPIRED', error_code: 'BET_TAKEN_OR_LAPSED', price: 1.62, size: 10,
        });
        expect(riga).toContain('codice Betfair BET_TAKEN_OR_LAPSED');
    });
});

describe('la riga generica del design system porta gli stessi tre numeri', () => {
    it('chiesto / abbinato / residuo / codice, coi formatter unici', () => {
        const riga = activityLineGeneric({
            size_requested: 5, size_matched: 2, size_remaining: 3,
            avg_price_matched: 2.38, error_code: 'INSUFFICIENT_FUNDS',
        });
        expect(riga).toBe('chiesti 5,00 € · abbinati 2,00 € @ 2,38 · residuo 3,00 € · codice Betfair INSUFFICIENT_FUNDS');
    });
});
