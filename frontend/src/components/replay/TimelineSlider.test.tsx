// ============================================================================
// 07/10 — GEOMETRIA DELLA BARRA DI MATCH REPLAY (componente isolato).
// Tutto sta sulla stessa scala: il cursore al passo i sta a i/span, un simbolo
// con pctLeft = i/span sta nello stesso punto, il segmento di sospensione del
// passo i parte da li' ed e' largo un passo, la lineetta del calcio d'inizio sta
// a kickoffIndex/span. span = max - min (minimo 1: nessuna divisione per zero).
// La pagina intera e' provata in `lib/replayBarraSimboli.test.tsx`.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TimelineSlider, type TimelineEventMarker } from './TimelineSlider';

const nulla = () => undefined;
const num = (e: HTMLElement, k: string) => Number(e.getAttribute(k));
// % orizzontale DISEGNATA (stile): e' cio' che vede l'utente
const sinistra = (e: HTMLElement) => Number.parseFloat(e.style.left);
const larghezza = (e: HTMLElement) => Number.parseFloat(e.style.width);

function monta(props: Partial<React.ComponentProps<typeof TimelineSlider>> = {}) {
    return render(<TimelineSlider min={0} max={100} value={0} minute={null} onChange={nulla} {...props} />);
}

describe('TimelineSlider — cursore', () => {
    it('sta a (valore - min) / (max - min): 0% al primo passo, 100% all\'ultimo, e il DOM lo dice come lo stile', () => {
        for (const [valore, atteso] of [[0, 0], [25, 25], [50, 50], [100, 100]] as const) {
            const { unmount } = monta({ value: valore });
            const k = screen.getByTestId('barra-knob');
            expect(sinistra(k)).toBeCloseTo(atteso, 9);
            unmount();
        }
    });

    it('con min diverso da 0 la scala parte dal minimo', () => {
        monta({ min: 10, max: 30, value: 20 });
        expect(sinistra(screen.getByTestId('barra-knob'))).toBeCloseTo(50, 9);
    });

    it('una barra a un solo passo non produce NaN ne\' Infinity', () => {
        monta({ min: 0, max: 0, value: 0, events: [{ pctLeft: 0, kind: 'goal', team: 'home', minute: 1, label: 'Gol' }], suspended: [true] });
        expect(sinistra(screen.getByTestId('barra-knob'))).toBe(0);
        expect(Number.isFinite(sinistra(screen.getByTestId('barra-simbolo')))).toBe(true);
        // con un solo passo non c'e' nessun tratto da disegnare
        expect(screen.queryAllByTestId('barra-sospensione')).toHaveLength(0);
    });

    it('mostra PRE prima del fischio, altrimenti il minuto, altrimenti un trattino', () => {
        const { unmount } = monta({ pre: true, minute: 30 });
        expect(screen.getByTestId('barra-knob').textContent).toBe('PRE');
        unmount();
        const b = monta({ minute: 30 });
        expect(screen.getByTestId('barra-knob').textContent).toBe('30');
        b.unmount();
        monta({ minute: null });
        expect(screen.getByTestId('barra-knob').textContent).toBe('—');
    });
});

describe('TimelineSlider — simboli', () => {
    const sim = (pct: number, kind = 'goal'): TimelineEventMarker => ({ pctLeft: pct, kind, team: 'home', minute: 10, label: 'x' });

    it('un simbolo con pctLeft = i/span sta nello stesso punto del cursore al passo i', () => {
        const span = 200;
        for (const i of [0, 1, 57, 199, 200]) {
            const { unmount } = monta({ max: span, value: i, events: [sim(i / span)] });
            expect(sinistra(screen.getByTestId('barra-simbolo'))).toBeCloseTo(sinistra(screen.getByTestId('barra-knob')), 9);
            unmount();
        }
    });

    it('una posizione fuori scala viene tenuta dentro la barra (0..100)', () => {
        monta({ events: [sim(-0.3), sim(1.7)] });
        const v = screen.getAllByTestId('barra-simbolo').map(e => sinistra(e));
        expect(v).toEqual([0, 100]);
        for (const e of screen.getAllByTestId('barra-simbolo')) expect(sinistra(e)).toBeGreaterThanOrEqual(0);
    });

    it('il tipo del simbolo arriva al DOM e la legenda elenca solo i tipi presenti', () => {
        monta({ events: [sim(0.1, 'goal'), sim(0.2, 'yellow'), sim(0.3, 'corner')] });
        expect(screen.getAllByTestId('barra-simbolo').map(e => e.getAttribute('data-kind'))).toEqual(['goal', 'yellow', 'corner']);
        expect(screen.getByText(/Gol/)).toBeTruthy();
        expect(screen.getByText(/Giallo/)).toBeTruthy();
        expect(screen.getByText(/Angolo/)).toBeTruthy();
        expect(screen.queryByText(/Rosso/)).toBeNull();
    });
});

describe('TimelineSlider — sospensioni e calcio d\'inizio', () => {
    it('il segmento del passo i parte dalla posizione del cursore su quel passo ed e\' largo un passo', () => {
        const span = 50;
        const sosp = Array.from({ length: span + 1 }, (_, i) => i >= 10 && i <= 12);
        monta({ max: span, suspended: sosp });
        const seg = screen.getAllByTestId('barra-sospensione');
        expect(seg.map(e => num(e, 'data-indice'))).toEqual([10, 11, 12]);
        for (const e of seg) {
            expect(sinistra(e)).toBeCloseTo(num(e, 'data-indice') / span * 100, 9);
            expect(larghezza(e)).toBeCloseTo(100 / span, 9);
        }
    });

    it('l\'ultimo passo sospeso non esce dalla barra', () => {
        const span = 40;
        monta({ max: span, suspended: Array.from({ length: span + 1 }, (_, i) => i >= span - 1) });
        for (const e of screen.getAllByTestId('barra-sospensione')) {
            expect(sinistra(e) + larghezza(e)).toBeLessThanOrEqual(100 + 1e-9);
        }
    });

    it('la lineetta del calcio d\'inizio compare solo con pre-match (kickoffPct > 0) e sta dove dice kickoffPct', () => {
        const { unmount } = monta({ kickoffPct: 0 });
        expect(screen.queryByTestId('barra-kickoff')).toBeNull();
        unmount();
        monta({ kickoffPct: 453 / 1121 });
        const k = screen.getByTestId('barra-kickoff');
        expect(sinistra(k)).toBeCloseTo(453 / 1121 * 100, 9);
    });
});

// 07/10 — PARAMETRI PER LO SPORT (Replay Tennis): icone, legenda e titolo del marker
// d'inizio si possono passare; senza, tutto resta come per il calcio (Match Replay).
describe('TimelineSlider — parametri per lo sport', () => {
    const eventi: TimelineEventMarker[] = [
        { pctLeft: 0.2, kind: 'goal', team: 'home', minute: 12, label: 'Gol' },
        { pctLeft: 0.6, kind: 'break', team: null, minute: null, label: 'Break' },
    ];

    it('senza parametri: icone, legenda e titolo del calcio, identici a prima', () => {
        monta({ events: eventi, kickoffPct: 0.1 });
        const simboli = screen.getAllByTestId('barra-simbolo');
        expect(simboli[0].textContent).toBe('⚽');
        expect(simboli[1].querySelector('span.rounded-full')).not.toBeNull(); // punto generico
        expect(screen.getByTestId('barra-kickoff').getAttribute('title')).toBe("Calcio d'inizio");
        expect(screen.getByText('⚽ Gol')).toBeInTheDocument();
    });

    it('con i parametri: le icone dello sport, la sua legenda e il suo titolo d\'inizio', () => {
        monta({
            events: eventi, kickoffPct: 0.1,
            iconaEvento: k => <span data-testid={`icona-${k}`}>{k.toUpperCase()}</span>,
            legenda: <div data-testid="legenda-sport">B = Break</div>,
            titoloInizio: 'Passaggio in gioco',
        });
        expect(screen.getByTestId('icona-goal').textContent).toBe('GOAL');
        expect(screen.getByTestId('icona-break').textContent).toBe('BREAK');
        expect(screen.getByTestId('barra-kickoff').getAttribute('title')).toBe('Passaggio in gioco');
        expect(screen.getByTestId('legenda-sport')).toBeInTheDocument();
        expect(screen.queryByText('⚽ Gol')).toBeNull();
    });
});
