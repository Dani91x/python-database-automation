// Cantiere J2 (28/09/2026): ladder e Segui Live dicono in rosso che lo stream
// del RUNNER e' muto. Il messaggio ha le chiavi VERE di
// `stream_muto.messaggio_canale` (topic `flusso_stream`).
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { giudizioFlussoStream, leggiFlussoStream } from './flussoStreamRunner';
import { FlussoStreamAvviso } from '@/components/live/FlussoStreamBanner';

const ORA = Date.parse('2026-09-28T20:00:00Z');
const MUTO = { ts: ORA - 4000, vivo: false, interrotto: true, motivo: 'flusso_interrotto',
    eta_s: 31.2, muto_da_s: 16.0, mercati_fermi: ['1.200', '1.201'], episodi: 1 };
const VIVO = { ...MUTO, vivo: true, interrotto: false, motivo: null, muto_da_s: null, mercati_fermi: [] };

describe('flusso_stream del runner', () => {
    it('muto sul mercato: FLUSSO INTERROTTO col tempo che scorre e il motivo', () => {
        const g = giudizioFlussoStream(leggiFlussoStream(MUTO), '1.200', ORA);
        expect(g?.testo).toContain('FLUSSO INTERROTTO da 20 s');
        expect(g?.testo).toContain('neanche heartbeat');
    });
    it('altro mercato vivo, stream vivo, messaggio vecchio o storto: nessun avviso', () => {
        expect(giudizioFlussoStream(leggiFlussoStream(MUTO), '1.999', ORA)).toBeNull();
        expect(giudizioFlussoStream(leggiFlussoStream(VIVO), '1.200', ORA)).toBeNull();
        expect(giudizioFlussoStream(leggiFlussoStream(MUTO), '1.200', ORA + 60_000)).toBeNull();
        expect(leggiFlussoStream({ interrotto: true })).toBeNull();
    });
    it('canale locale giu: stato NON NOTO, mai silenzio (anche dopo 30 s)', () => {
        render(<FlussoStreamAvviso flusso={leggiFlussoStream(VIVO)} marketId="1.200"
            nowMs={ORA + 120_000} canaleConnesso={false} />);
        const b = screen.getByTestId('flusso-stream-runner');
        expect(b.getAttribute('data-stato')).toBe('non_noto');
        expect(b.textContent).toContain('NON NOTO');
    });
    it('il banner si vede rosso sul mercato fermo e sparisce al rientro', () => {
        const { rerender } = render(
            <FlussoStreamAvviso flusso={leggiFlussoStream(MUTO)} marketId="1.200" nowMs={ORA} />);
        expect(screen.getByTestId('flusso-stream-runner').textContent).toContain('FLUSSO INTERROTTO');
        rerender(<FlussoStreamAvviso flusso={leggiFlussoStream(VIVO)} marketId="1.200" nowMs={ORA} />);
        expect(screen.queryByTestId('flusso-stream-runner')).toBeNull();
    });
});
