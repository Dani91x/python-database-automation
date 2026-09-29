// Cantiere J (28/09/2026): il FLUSSO PREZZI interrotto si DICE al trader, in
// italiano, con il motivo, in tutti e tre i bot che scrivono l'attività.
import { describe, expect, it } from 'vitest';
import { safeActivityExitStatus } from './safeExitStatus';
import { MIKE_ACTIVITY_EXTRA, MIKE_REQUEST_CODE_MESSAGE, mikeActivityLine } from './mike';
import { OMEGA_ACTIVITY_EXTRA } from './omega';

describe('flusso prezzi interrotto', () => {
    it('Safe: exit_wait con flusso_interrotto:<motivo> dice FLUSSO PREZZI INTERROTTO e il motivo', () => {
        const info = safeActivityExitStatus({
            kind: 'exit_wait',
            id: 1,
            payload: { wait: 'flusso_interrotto:flusso_interrotto' },
        });
        expect(info?.text).toContain('FLUSSO PREZZI INTERROTTO');
        expect(info?.text).toContain('nessun dato ricevuto da Betfair');
        const giro = safeActivityExitStatus({
            kind: 'exit_wait',
            id: 1,
            payload: { wait: 'flusso_interrotto:scanner_bloccato' },
        });
        expect(giro?.text).toContain('giro dello scanner fermo');
    });

    it('Mike: kind, etichetta critica, riga e codice di esito', () => {
        expect(MIKE_ACTIVITY_EXTRA.flusso_interrotto.label).toBe('FLUSSO PREZZI INTERROTTO');
        expect(MIKE_ACTIVITY_EXTRA.flusso_interrotto.critical).toBe(true);
        const riga = mikeActivityLine('flusso_interrotto', {
            testo: 'flusso prezzi INTERROTTO: nessun dato ricevuto da oltre la soglia; da 312 s',
            state: 'LIVE_COVERED',
        });
        expect(riga).toContain('da 312 s');
        expect(riga).toContain('nessuna apertura né chiusura a mercato');
        expect(MIKE_REQUEST_CODE_MESSAGE.flusso_interrotto).toContain('flusso prezzi interrotto');
    });

    it('Omega: etichetta critica', () => {
        expect(OMEGA_ACTIVITY_EXTRA.flusso_interrotto.label).toBe('FLUSSO PREZZI INTERROTTO');
        expect(OMEGA_ACTIVITY_EXTRA.flusso_interrotto.critical).toBe(true);
    });
});
