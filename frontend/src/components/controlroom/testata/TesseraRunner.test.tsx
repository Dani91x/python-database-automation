// ============================================================================
// TesseraRunner.test.tsx - 01/10: le due tessere dei runner in testata.
// Finti con le chiavi del vero: `RunnerState` (lib/safeBot: ts, mode, ageS,
// up, streaming) come lo costruisce `runnerDalCanale` (lib/runnerCanale.ts),
// e `{ fonte: 'canale' | 'database', etaS }` come `vm.fonteRunner`.
// `mode` = le modalita' SERVITE dichiarate dal runner (heartbeat_mode():
// 'LIVE+PAPER' | 'PAPER' | 'OFF').
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TesseraRunner, descriviRunner, runnerForseLive } from './TesseraRunner';
import type { RunnerState } from '@/lib/safeBot';

const CALCIO_CANALE: RunnerState = { ts: '2026-10-01T08:00:00.000Z', mode: 'LIVE+PAPER', ageS: 5, up: true, streaming: 0 };
const TENNIS_CANALE: RunnerState = { ts: '2026-10-01T08:00:00.000Z', mode: 'PAPER', ageS: 2, up: true, streaming: null };

describe('descriviRunner - di che runner parliamo e se e\' connesso', () => {
    it('CALCIO dal canale: nome, porta 47331, connesso, vivo in attesa, ORDINI VERI col tono LIVE, fonte ed eta\'', () => {
        const v = descriviRunner('calcio', CALCIO_CANALE, { fonte: 'canale', etaS: 5 });
        expect(v.titolo).toBe('Runner CALCIO');
        expect(v.porta).toBe(47331);
        expect(v.connesso).toBe(true);
        expect(v.connessione).toBe('connesso');
        expect(v.processo).toEqual({ testo: 'vivo, in attesa', tono: 'neutro' });
        expect(v.ordini.testo).toBe('ORDINI VERI consentiti');
        expect(v.ordini.tono).toBe('live');
        expect(v.fonte).toBe('canale 47331 · ultimo messaggio 5 s fa');
    });
    it('TENNIS dal canale: porta 47332, solo simulati col tono PAPER', () => {
        const v = descriviRunner('tennis', TENNIS_CANALE, { fonte: 'canale', etaS: 2 });
        expect(v.titolo).toBe('Runner TENNIS');
        expect(v.porta).toBe(47332);
        expect(v.connesso).toBe(true);
        expect(v.ordini).toMatchObject({ testo: 'solo simulati', tono: 'paper' });
    });
    it('CALCIO senza canale (ripiego sul battito del database): NON connesso, fonte database', () => {
        const v = descriviRunner('calcio', { ...CALCIO_CANALE, ageS: 30, streaming: 2 }, { fonte: 'database', etaS: 30 });
        expect(v.connesso).toBe(false);
        expect(v.connessione).toBe('non connesso al canale');
        expect(v.processo.testo).toBe('in streaming');
        expect(v.fonte).toMatch(/^database \(battito ogni 30 s\)/);
    });
    it('TENNIS canale spento (null): non connesso, stato NON NOTO (mai "fermo")', () => {
        const v = descriviRunner('tennis', null, { fonte: 'database', etaS: null });
        expect(v.connesso).toBe(false);
        expect(v.processo.testo).toMatch(/non noto/);
        expect(v.processo.testo).not.toMatch(/fermo/);
        expect(v.fonte).toBe('canale 47332 spento');
    });
    it('battito vecchio = fermo; mai battuto = mai avviato; streaming non letto = attesa (mai streaming)', () => {
        expect(descriviRunner('calcio', { ts: '2026-09-02T17:55:00Z', mode: 'PAPER', ageS: 1_000_000, up: false }, { fonte: 'database', etaS: 1_000_000 }).processo.testo).toBe('fermo');
        expect(descriviRunner('calcio', { ts: null, mode: null, ageS: null, up: false }, { fonte: 'database', etaS: null }).processo.testo).toBe('mai avviato');
        expect(descriviRunner('calcio', { ...CALCIO_CANALE, streaming: null }, { fonte: 'canale', etaS: 5 }).processo.testo).toBe('vivo, in attesa');
    });
});

// R-03 (review 01/10): il runner tennis per la conferma dello stop del conto
describe('runnerForseLive - fail-closed: false SOLO col tetto letto PAPER o OFF', () => {
    it('PAPER e OFF letti: no; LIVE+PAPER: si\'; non letto o tetto ignoto: si\'', () => {
        expect(runnerForseLive(TENNIS_CANALE)).toBe(false);
        expect(runnerForseLive({ ...TENNIS_CANALE, mode: 'OFF' })).toBe(false);
        expect(runnerForseLive({ ...TENNIS_CANALE, mode: 'LIVE+PAPER' })).toBe(true);
        expect(runnerForseLive(null)).toBe(true);
        expect(runnerForseLive({ ...TENNIS_CANALE, mode: null })).toBe(true);
        expect(runnerForseLive({ ...TENNIS_CANALE, mode: 'BOH' })).toBe(true);
    });
});

describe('TesseraRunner - a schermo', () => {
    it('due tessere distinte e nominate, con pallino connesso/non connesso', () => {
        render(<>
            <TesseraRunner sport="calcio" r={CALCIO_CANALE} fonte={{ fonte: 'canale', etaS: 5 }} />
            <TesseraRunner sport="tennis" r={null} fonte={{ fonte: 'database', etaS: null }} />
        </>);
        expect(screen.getByTestId('cr-runner-nome').textContent).toBe('Runner CALCIO (canale 47331)');
        expect(screen.getByTestId('cr-runner-tennis-nome').textContent).toBe('Runner TENNIS (canale 47332)');
        expect(screen.getByTestId('cr-runner-pallino').getAttribute('data-connesso')).toBe('1');
        expect(screen.getByTestId('cr-runner-pallino').className).toMatch(/emerald/);
        expect(screen.getByTestId('cr-runner-tennis-pallino').getAttribute('data-connesso')).toBe('0');
        expect(screen.getByTestId('cr-runner-tennis-connessione').textContent).toMatch(/non connesso/);
        expect(screen.getByTestId('cr-runner-tetto').textContent).toBe('ORDINI VERI consentiti');
        expect(screen.getByTestId('cr-runner-tetto').className).toMatch(/red/);
        expect(screen.getByTestId('cr-runner-processo').textContent).toBe('processo: vivo, in attesa');
    });
});
