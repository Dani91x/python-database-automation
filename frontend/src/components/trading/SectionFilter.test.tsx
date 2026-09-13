import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SectionFilter, useSectionFilter, readHidden } from './SectionFilter';

const SEZIONI = ['pre', 'live'] as const;
const CHIAVE = 'test.sezioni.nascoste';

function Prova({ chiave = CHIAVE }: { chiave?: string }) {
    const f = useSectionFilter(chiave, SEZIONI);
    return (
        <div>
            <SectionFilter
                options={[
                    { id: 'pre', label: '⏱ Pre-match', count: 5, activeCls: 'attivo-pre' },
                    { id: 'live', label: '🔴 Live', count: 3, activeCls: 'attivo-live' },
                ]}
                hidden={f.hidden}
                onToggle={f.toggle}
            />
            {f.isVisible('pre') && <div data-testid="sez-pre">sezione pre</div>}
            {f.isVisible('live') && <div data-testid="sez-live">sezione live</div>}
        </div>
    );
}

describe('SectionFilter — nascondere pre-match e live', () => {
    beforeEach(() => {
        window.localStorage.clear();
        vi.restoreAllMocks();
    });

    it('parte con tutte le sezioni visibili', () => {
        render(<Prova />);
        expect(screen.getByTestId('sez-pre')).toBeInTheDocument();
        expect(screen.getByTestId('sez-live')).toBeInTheDocument();
    });

    it('un clic nasconde la sezione, un altro la riporta', () => {
        render(<Prova />);
        fireEvent.click(screen.getByTestId('section-filter-pre'));
        expect(screen.queryByTestId('sez-pre')).not.toBeInTheDocument();
        expect(screen.getByTestId('sez-live')).toBeInTheDocument();
        fireEvent.click(screen.getByTestId('section-filter-pre'));
        expect(screen.getByTestId('sez-pre')).toBeInTheDocument();
    });

    it('il conteggio resta visibile anche a sezione nascosta', () => {
        render(<Prova />);
        const bottone = screen.getByTestId('section-filter-pre');
        expect(bottone).toHaveTextContent('(5)');
        fireEvent.click(bottone);
        expect(screen.queryByTestId('sez-pre')).not.toBeInTheDocument();
        expect(screen.getByTestId('section-filter-pre')).toHaveTextContent('(5)');
    });

    it("l'ultima sezione accesa NON si puo' spegnere: la pagina non resta vuota", () => {
        render(<Prova />);
        fireEvent.click(screen.getByTestId('section-filter-pre'));
        const live = screen.getByTestId('section-filter-live');
        expect(live).toBeDisabled();
        fireEvent.click(live);
        expect(screen.getByTestId('sez-live')).toBeInTheDocument();
    });

    it('la scelta sopravvive al ricaricamento della pagina', () => {
        const { unmount } = render(<Prova />);
        fireEvent.click(screen.getByTestId('section-filter-live'));
        expect(readHidden(CHIAVE).has('live')).toBe(true);
        unmount();
        render(<Prova />);
        expect(screen.queryByTestId('sez-live')).not.toBeInTheDocument();
        expect(screen.getByTestId('sez-pre')).toBeInTheDocument();
    });

    it('chiavi diverse non si disturbano fra loro', () => {
        const { unmount } = render(<Prova chiave="mike.x" />);
        fireEvent.click(screen.getByTestId('section-filter-pre'));
        unmount();
        render(<Prova chiave="omega.x" />);
        expect(screen.getByTestId('sez-pre')).toBeInTheDocument();
    });

    it('uno storage rotto non rompe la pagina: tutte visibili', () => {
        vi.spyOn(window.localStorage.__proto__, 'getItem').mockImplementation(() => {
            throw new Error('storage non disponibile');
        });
        vi.spyOn(window.localStorage.__proto__, 'setItem').mockImplementation(() => {
            throw new Error('storage pieno');
        });
        render(<Prova />);
        expect(screen.getByTestId('sez-pre')).toBeInTheDocument();
        expect(screen.getByTestId('sez-live')).toBeInTheDocument();
        // il clic non deve lanciare, anche se non riesce a salvare
        fireEvent.click(screen.getByTestId('section-filter-pre'));
        expect(screen.queryByTestId('sez-pre')).not.toBeInTheDocument();
    });

    it('un valore salvato malformato viene ignorato', () => {
        window.localStorage.setItem(CHIAVE, '{"non":"un array"}');
        render(<Prova />);
        expect(screen.getByTestId('sez-pre')).toBeInTheDocument();
        expect(screen.getByTestId('sez-live')).toBeInTheDocument();
    });

    it('una sezione tolta dal codice non resta nascosta per sempre', () => {
        window.localStorage.setItem(CHIAVE, '["pre","sezione_non_piu_esistente"]');
        render(<Prova />);
        expect(screen.queryByTestId('sez-pre')).not.toBeInTheDocument();
        expect(readHidden(CHIAVE).has('sezione_non_piu_esistente')).toBe(true);
        // ...e appena si tocca un filtro la chiave morta sparisce dal salvato
        fireEvent.click(screen.getByTestId('section-filter-pre'));
        expect(readHidden(CHIAVE).has('sezione_non_piu_esistente')).toBe(false);
    });

    it('lo stato è leggibile da chi usa la tastiera', () => {
        render(<Prova />);
        expect(screen.getByTestId('section-filter-pre')).toHaveAttribute('aria-pressed', 'true');
        fireEvent.click(screen.getByTestId('section-filter-pre'));
        expect(screen.getByTestId('section-filter-pre')).toHaveAttribute('aria-pressed', 'false');
    });
});
