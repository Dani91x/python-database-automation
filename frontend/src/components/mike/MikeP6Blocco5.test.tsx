// ============================================================================
// MikeP6Blocco5.test.tsx - piano Mike 29/09, P6 blocco 5: i testi dell'app
// allineati ai pacchetti del motore gia' su master (P2 pre-partita `5414b0e`,
// P4 blocco 2 `6cc91a0`) e al P4 blocco 3 in integrazione. Payload delle
// attivita' con le chiavi di `db.log(...)` del servizio di master; righe
// `mike_trades` con `meta.regolamento` / `meta.settle_reason` come le scrive.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MikeEventPnlTable } from './MikeEventPnlTable';
import {
    groupMikeTrades, mikeActivityLine, notaRegolamentoMike, MIKE_PARAM_FIELDS, MIKE_PHASE_META,
    type MikeTrade,
} from '@/lib/mike';

function campo(key: string) {
    const f = MIKE_PARAM_FIELDS.find((x) => x.key === key);
    if (!f) throw new Error(key);
    return f;
}

let seq = 5000;
function riga(over: Partial<MikeTrade> = {}): MikeTrade {
    seq += 1;
    return {
        id: seq, event_id: 'E1', event_name: 'Roma v Lazio', strategy: 'under_entry',
        role: 'under_entry', cycle_no: 0, market_type: 'OVER_UNDER_35', market_id: '1.1',
        selection_id: 1222344, side: 'back', price: 1.5, size: 10, liability: 10,
        commission: 5, mode: 'paper', status: 'open', pnl: null, bet_id: null,
        placed_at: '2026-09-29T10:00:00Z', day_placed_at: '2026-09-29T10:00:00Z',
        settled_at: null, signal_key: `k${seq}`, meta: {}, closes_trade_id: null,
        origin: 'auto', ...over,
    } as MikeTrade;
}

describe('P2 - pre-partita: testi del pannello e delle fasi', () => {
    it('l’ultimo ingresso non e’ piu’ un PERSIST: interruttore con la spiegazione nuova', () => {
        const f = campo('last_entry_persist');
        expect(f.label).toBe('Ultimo ingresso a 10 min dal fischio');
        expect(f.hint).toContain('solo se Mike non ha posizione');
        expect(f.hint).toContain('non piu’ un ordine PERSIST');
    });

    it('last_entry_ticks_above resta in elenco ma NON ATTIVO', () => {
        const f = campo('last_entry_ticks_above');
        expect(f.label).toContain('NON ATTIVO');
        expect(f.hint).toMatch(/^NON ATTIVO dal 29\/09/);
        expect(f.kind === 'number' ? [f.min, f.max] : null).toEqual([0, 3]);
    });

    it('il veto blocca l’ultimo ingresso, non chiude', () => {
        const h = campo('veto_p_under35_cal').hint;
        expect(h).toContain('blocca l\'ultimo ingresso');
        expect(h).toContain('Non chiude mai niente');
        expect(h).not.toContain('PERSIST si piazza');
    });

    it('fase HOLD: dopo il segno dei 10 minuti, banca fino al fischio', () => {
        expect(MIKE_PHASE_META.HOLD.what).toBe('dopo il segno dei 10 minuti: nessun ingresso fino al fischio; la banca resta appoggiata');
        expect(MIKE_PHASE_META.PRE_LAST_ENTRY_PENDING.what).not.toContain('resta valido anche in gioco');
        expect(campo('pre_last_entry_min').hint).not.toContain('PERSIST');
    });
});

describe('P4 blocchi 2 e 3 - attivita’ nuove in parole semplici', () => {
    it('lettura dei dati fallita e ripresa', () => {
        expect(mikeActivityLine('error', { reason: 'lettura_feed_fallita', critical: true, nota: 'x' }))
            .toBe('lettura dei dati fallita: Mike ritenta, nessuna partita data per sparita');
        expect(mikeActivityLine('skip', { reason: 'lettura_feed_ripresa', secondi_senza_lettura: 42, nota: 'x' }))
            .toBe('lettura dei dati ripresa');
    });

    it('punteggio assente: non e’ una «linea assente nel feed»', () => {
        const t = mikeActivityLine('feed_line_missing', { reason: 'punteggio_assente', state: 'LIVE_COVERED' });
        expect(t).toMatch(/^in gioco il punteggio non arriva: Mike non decide niente che dipenda dai gol · fase /);
        expect(t).not.toContain('linee assenti');
    });

    it('punteggio e quote tornati, ordine senza risposta', () => {
        expect(mikeActivityLine('skip', { reason: 'punteggio_assente_tornato' })).toBe('il punteggio e’ tornato');
        expect(mikeActivityLine('skip', { reason: 'quote_assenti_tornato' })).toBe('le quote sono tornate');
        expect(mikeActivityLine('reconcile_pending', { leg: 'under_close-0-3', reason: 'runner_senza_esito' }))
            .toContain('ordine senza risposta: Mike lo sta verificando');
    });
});

describe('P4 blocco 2 - come e’ stata regolata una riga', () => {
    it('le due note del regolamento', () => {
        expect(notaRegolamentoMike({ regolamento: 'non_determinabile' })).toBe('da regolare a mano: risultato non leggibile');
        expect(notaRegolamentoMike({ settle_reason: 'risultato_indipendente_dal_punteggio' }))
            .toBe('regolata senza punteggio: il risultato non dipendeva dai gol');
        expect(notaRegolamentoMike({})).toBeNull();
        expect(notaRegolamentoMike(null)).toBeNull();
    });

    it('nella tabella delle operazioni la riga lo dice', () => {
        const r = riga({ meta: { regolamento: 'non_determinabile' } });
        render(<MikeEventPnlTable gruppi={groupMikeTrades([r])} titolo="Operazioni" vuoto="-" />);
        fireEvent.click(screen.getByTestId('apri-E1'));
        expect(screen.getByTestId(`regolamento-${r.id}`).textContent).toBe('da regolare a mano: risultato non leggibile');
    });
});
