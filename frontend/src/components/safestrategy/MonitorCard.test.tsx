// ============================================================================
// CERT. 13/09 — MonitorCard: «5/9» non bastava.
//
// Il chip contava SOLO le condizioni VERE, quindi una partita con 4 condizioni
// FALSE (non va bene) e una con 4 condizioni N/D (non misurabili — quasi sempre
// il riferimento 1X2 pre-kickoff mancante) mostravano lo stesso identico
// «5/9». Sono due situazioni opposte: la prima è un no, la seconda è un «non
// lo so» e spiega perché BASE e PUNTA non scattano su quella partita.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MonitorCard } from './MonitorCard';
import type { ConditionCheck, VariantEvaluation } from '@/lib/safeStrategy';

function check(id: string, ok: boolean | null): ConditionCheck {
    return { id, label: `condizione ${id}`, value: ok === null ? 'n/d' : 'x', ok };
}

function evaluation(checks: ConditionCheck[]): VariantEvaluation {
    return {
        variant: 'base', state: 'nd', checks,
        headline: null, side: null, selection: null, entryOdds: null,
    } as VariantEvaluation;
}

function renderCard(checks: ConditionCheck[]) {
    render(
        <MonitorCard
            eventId="e1"
            title="Roma – Lazio"
            liveLine="58′ · 1-0"
            inplay
            evaluations={[{ evaluation: evaluation(checks) }]}
        />,
    );
}

describe('MonitorCard — sì / no / n/d, non un solo numero', () => {
    it('distingue le condizioni FALSE da quelle non valutabili', () => {
        renderCard([
            check('a', true), check('b', true), check('c', true), check('d', true), check('e', true),
            check('f', null), check('g', null), check('h', null), check('i', null),
        ]);
        const chip = screen.getByTestId('monitor-variant-chip');
        expect(chip).toHaveTextContent('5 sì · 0 no · 4 n/d');
        expect(chip.title).toMatch(/4 non valutabili/);
        expect(chip.title).toMatch(/riferimento pre-KO/);
    });

    it('stessa somma, significato opposto: 4 condizioni FALSE', () => {
        renderCard([
            check('a', true), check('b', true), check('c', true), check('d', true), check('e', true),
            check('f', false), check('g', false), check('h', false), check('i', false),
        ]);
        const chip = screen.getByTestId('monitor-variant-chip');
        // prima questo chip e quello del test sopra erano identici: «5/9»
        expect(chip).toHaveTextContent('5 sì · 4 no · 0 n/d');
        expect(chip.title).toMatch(/4 non soddisfatte/);
    });

    it('la nota diagnostica del pre-KO resta visibile sulla card', () => {
        render(
            <MonitorCard
                eventId="e1" title="Roma – Lazio" liveLine="58′ · 1-0" inplay
                evaluations={[{ evaluation: evaluation([check('a', null)]) }]}
                dataNote="riferimento pre-KO non catturato (scanner partito a match iniziato) — condizioni pre-match n/d"
            />,
        );
        expect(screen.getByText(/riferimento pre-KO non catturato/)).toBeInTheDocument();
    });
});
