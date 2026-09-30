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

    it('30/09 (P8): con la prova per bot, oggi e arretrati in colonne separate; la vecchia riga unica sparisce', () => {
        const zero = { pnl: 0, operazioni: 0, vinte: 0, perse: 0, partite: 0 };
        const s = render(
            <ObiettivoHero
                dayBar={dayBar()}
                composizione={composizioneVuota}
                manualeSito={{ pnlOggi: null, fonte: 'non-disponibile' }}
                onSalvaObiettivo={vi.fn()}
                prova={{
                    voci: [
                        { chiave: 'safe_calcio', etichetta: 'Safe calcio', sport: 'calcio', oggi: zero,
                            arretrati: [{ giorno: '2026-09-26', origine: 'apertura', pnl: 7.6, operazioni: 4, vinte: 4, perse: 0, partite: 4 }] },
                        { chiave: 'mike', etichetta: 'Mike', sport: 'calcio', oggi: zero, arretrati: null,
                            nota: 'arretrati di Mike: non letti' },
                        { chiave: 'bot_tennis', etichetta: 'Bot tennis', sport: 'tennis', oggi: zero, arretrati: [], perRegolamento: true },
                    ],
                    oggiPerSport: { calcio: zero, tennis: zero },
                    arretratiPerSport: { calcio: [], tennis: [] },
                    arretratiNonLetti: { calcio: ['Mike'], tennis: [] },
                    perRegolamento: { calcio: [], tennis: ['Bot tennis'] },
                }}
            />,
        );
        expect(s.getByTestId('cr-prova-safe_calcio-oggi').textContent).toContain('+0,00 €');
        expect(s.getByTestId('cr-prova-safe_calcio-arretrati').textContent).toBe('+7,60 € (4 operazioni aperte il 26/09)');
        expect(s.getByTestId('cr-prova-mike-arretrati').textContent).toBe('arretrati di Mike: non letti');
        expect(s.getByTestId('cr-prova-bot_tennis-arretrati').textContent).toMatch(/per giorno di regolamento/);
        // la cifra unica di prima (provaPaper -1,20) non compare piu'
        expect(s.getByTestId('cr-composizione-prova').textContent).not.toMatch(/1,20/);
    });

    it('30/09 (P7): ogni voce dichiara la fonte (CONTO con l\'eta\' della lettura, o BOT); conto non letto detto', () => {
        const dalConto = {
            ...composizioneVuota, dalConto: true,
            righe: [
                { chiave: 'mike' as const, etichetta: 'Mike', valore: 2, reale: 2, stimato: null, fonte: 'conto' as const },
                { chiave: 'omega' as const, etichetta: 'Omega', valore: 0.4, reale: null, stimato: 0.4, fonte: 'bot' as const },
                { chiave: 'altro' as const, etichetta: 'Altro sul conto Betfair', valore: null, fonte: null },
            ],
        };
        const s = render(
            <ObiettivoHero dayBar={dayBar()} composizione={dalConto} contoEtaS={180}
                manualeSito={{ pnlOggi: null, fonte: 'non-disponibile' }} onSalvaObiettivo={vi.fn()} />,
        );
        const mike = s.getByTestId('cr-composizione-mike-fonte');
        expect(mike.getAttribute('data-fonte')).toBe('conto');
        expect(mike.textContent).toBe('CONTO BETFAIR· 3 min fa');
        expect(s.getByTestId('cr-composizione-omega-fonte').getAttribute('data-fonte')).toBe('bot');
        // voce vuota: nessun marchio, resta «—»
        expect(s.queryByTestId('cr-composizione-altro-fonte')).toBeNull();
        expect(s.getByTestId('cr-composizione-fonte').textContent).toMatch(/dal conto Betfair/);
        s.unmount();
        const s2 = render(
            <ObiettivoHero dayBar={dayBar()} composizione={{ ...dalConto, dalConto: false }}
                manualeSito={{ pnlOggi: null, fonte: 'non-disponibile' }} onSalvaObiettivo={vi.fn()} />,
        );
        expect(s2.getByTestId('cr-composizione-fonte').textContent).toMatch(/conto Betfair non letto/);
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
