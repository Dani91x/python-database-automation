import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { ObiettivoHero } from './ObiettivoHero';
import type { ComposizioneObiettivo } from '@/lib/composizioneObiettivo';

const composizioneVuota: ComposizioneObiettivo = {
    righe: [
        { chiave: 'omega', etichetta: 'Omega', valore: 14.2 },
        { chiave: 'safe_calcio', etichetta: 'Safe calcio', valore: 9.6 },
        { chiave: 'safe_tennis', etichetta: 'Safe tennis', valore: null },
        { chiave: 'mike', etichetta: 'Mike', valore: 0.8 },
        { chiave: 'bot_tennis', etichetta: 'Bot tennis', valore: null },
        { chiave: 'manuale', etichetta: 'Manuale', valore: null },
    ],
    totale: 24.6,
    provaPaper: -1.2,
};

function dayBar(over: Partial<Parameters<typeof ObiettivoHero>[0]['dayBar']> = {}) {
    return { dayLabel: 'giovedì 18 settembre', realized: 24.6, goal: 50, ...over };
}

describe('ObiettivoHero', () => {
    it('mostra la composizione con — per un bot senza righe (mai zero)', () => {
        const s = render(
            <ObiettivoHero
                dayBar={dayBar()}
                composizione={composizioneVuota}
                manualeSito={{ pnlOggi: null, fonte: 'non-disponibile' }}
                onSalvaObiettivo={vi.fn()}
            />,
        );
        expect(s.getByTestId('cr-composizione-omega').textContent).toMatch(/14,20/);
        expect(s.getByTestId('cr-composizione-safe_tennis').textContent).toContain('—');
        expect(s.getByTestId('cr-composizione-bot_tennis').textContent).toContain('—');
    });

    it('la riga PROVA è separata e dice "mai sommato"', () => {
        const s = render(
            <ObiettivoHero
                dayBar={dayBar()}
                composizione={composizioneVuota}
                manualeSito={{ pnlOggi: null, fonte: 'non-disponibile' }}
                onSalvaObiettivo={vi.fn()}
            />,
        );
        const prova = s.getByTestId('cr-composizione-prova');
        expect(prova.textContent).toMatch(/1,20/);
        expect(prova.textContent).toMatch(/mai sommato/i);
    });

    it('il sito Betfair dichiara "non ancora collegate" quando assente', () => {
        const s = render(
            <ObiettivoHero
                dayBar={dayBar()}
                composizione={composizioneVuota}
                manualeSito={{ pnlOggi: null, fonte: 'non-disponibile' }}
                onSalvaObiettivo={vi.fn()}
            />,
        );
        expect(s.getByTestId('cr-manuale-sito-assente')).toBeTruthy();
    });

    it('SALVATAGGIO DELL’OBIETTIVO NON TOCCA ALTRI PARAMETRI: chiama onSalvaObiettivo solo col numero nuovo', async () => {
        const onSalva = vi.fn(async () => {});
        const s = render(
            <ObiettivoHero
                dayBar={dayBar()}
                composizione={composizioneVuota}
                manualeSito={{ pnlOggi: null, fonte: 'non-disponibile' }}
                onSalvaObiettivo={onSalva}
            />,
        );
        fireEvent.click(s.getByTestId('cr-obiettivo-editor-matita'));
        fireEvent.change(s.getByTestId('cr-obiettivo-editor-input'), { target: { value: '80' } });
        fireEvent.click(s.getByTestId('cr-obiettivo-editor-conferma'));
        await waitFor(() => expect(onSalva).toHaveBeenCalledWith(80));
        // un solo argomento: nessun oggetto-parametri completo passato in giro
        expect(onSalva.mock.calls[0]).toHaveLength(1);
    });

    it('contiene la DayBar con lo stesso testid storico cr-giornata', () => {
        const s = render(
            <ObiettivoHero
                dayBar={dayBar()}
                composizione={composizioneVuota}
                manualeSito={{ pnlOggi: null, fonte: 'non-disponibile' }}
                onSalvaObiettivo={vi.fn()}
            />,
        );
        expect(s.getByTestId('cr-giornata')).toBeTruthy();
    });
});
