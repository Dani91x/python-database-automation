// ============================================================================
// NomiPartita.test.tsx — B1 (30/09), «Seychelles v Sri Lanka, nomi partita
// diversi dalla scheda "pre-match", uniformare lo stile» (utente, sezione 5).
// Un solo componente per pre-partita, in gioco e aperte.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { NomiPartita } from './NomiPartita';

describe('NomiPartita — gli stessi nomi in ogni scheda', () => {
    it('due righe (casa, ospite), stesso corpo, troncate, nome completo accessibile', () => {
        render(<NomiPartita nome="Seychelles v Sri Lanka" />);
        const blocco = screen.getByTestId('cr-nomi-partita');
        expect(blocco.getAttribute('title')).toBe('Seychelles v Sri Lanka');
        const righe = screen.getAllByTestId('cr-nome-squadra');
        expect(righe.map((r) => r.textContent)).toEqual(['Seychelles', 'Sri Lanka']);
        for (const r of righe) {
            expect(r.className).toMatch(/truncate/);
            expect(r.className).toMatch(/text-\[13px\]/);
        }
        // il nome intero resta leggibile dagli strumenti di accessibilita', una volta sola
        expect(screen.getByText('Seychelles v Sri Lanka').className).toMatch(/sr-only/);
    });

    it('i nomi del trattino lungo e del tennis si dividono allo stesso modo', () => {
        render(<NomiPartita nome="Federer R. – Nadal R." />);
        expect(screen.getAllByTestId('cr-nome-squadra').map((r) => r.textContent)).toEqual(['Federer R.', 'Nadal R.']);
    });

    it('un nome che non si divide resta intero su una riga', () => {
        render(<NomiPartita nome="1.234567" />);
        expect(screen.getAllByTestId('cr-nome-squadra').map((r) => r.textContent)).toEqual(['1.234567']);
    });

    it('con i loghi (id squadra noti): un logo per squadra', () => {
        const { container } = render(<NomiPartita nome="Roma v Lazio" homeTeamId={497} awayTeamId={487} />);
        const img = container.querySelectorAll('img');
        expect(img).toHaveLength(2);
        expect(img[0].getAttribute('src')).toContain('497');
        expect(img[1].getAttribute('src')).toContain('487');
    });

    // B1bis (decisione del coordinatore, 30/09): lo spazio del logo e' SEMPRE
    // riservato, invisibile, anche senza nessun logo, perche' in una lista mista
    // i nomi restino allineati. Sostituisce l'asserzione B1 «nessuno spazio».
    it('senza loghi: solo i nomi, con lo spazio del logo riservato e INVISIBILE (niente logo rotto)', () => {
        const { container } = render(<NomiPartita nome="Seychelles v Sri Lanka" />);
        expect(container.querySelectorAll('img')).toHaveLength(0);
        const vuoti = screen.getAllByTestId('cr-logo-vuoto');
        expect(vuoti).toHaveLength(2);
        for (const v of vuoti) {
            expect(v.className).toMatch(/w-4/);
            expect(v.className).not.toMatch(/border|bg-/);
            expect(v.getAttribute('aria-hidden')).toBe('true');
            expect(v.textContent).toBe('');
        }
    });

    it('allineamento: con e senza loghi i nomi partono dallo stesso punto (stessa struttura di riga)', () => {
        const { container: a } = render(<NomiPartita nome="Roma v Lazio" homeTeamId={497} awayTeamId={487} />);
        const { container: b } = render(<NomiPartita nome="Seychelles v Sri Lanka" />);
        const primo = (c: HTMLElement) => Array.from(c.querySelectorAll('[data-testid="cr-nome-squadra"]'))
            .map((n) => n.previousElementSibling?.className ?? 'NESSUNO');
        expect(primo(a).every((cls) => /w-4/.test(cls))).toBe(true);
        expect(primo(b).every((cls) => /w-4/.test(cls))).toBe(true);
    });

    it('un logo solo (l’altro manca): l’altra riga ha lo spazio vuoto per restare allineata, senza bordo né fondo', () => {
        const { container } = render(<NomiPartita nome="Roma v Lazio" homeTeamId={497} awayTeamId={null} />);
        expect(container.querySelectorAll('img')).toHaveLength(1);
        const vuoto = screen.getByTestId('cr-logo-vuoto');
        expect(vuoto.className).not.toMatch(/border|bg-/);
        expect(vuoto.getAttribute('aria-hidden')).toBe('true');
    });

    // R_B1: la stessa riga riusata per un'altra squadra non eredita il «rotto»
    it('logo rotto, poi la riga passa a un’altra squadra: il nuovo logo si mostra', () => {
        const { container, rerender } = render(<NomiPartita nome="Roma v Lazio" homeTeamId={497} awayTeamId={487} />);
        fireEvent.error(container.querySelectorAll('img')[0]);
        expect(container.querySelectorAll('img')).toHaveLength(1);
        rerender(<NomiPartita nome="Milan v Lazio" homeTeamId={489} awayTeamId={487} />);
        const img = container.querySelectorAll('img');
        expect(img).toHaveLength(2);
        expect(img[0].getAttribute('src')).toContain('489');
    });

    it('un logo che non carica sparisce (niente quadrato rotto)', () => {
        const { container } = render(<NomiPartita nome="Roma v Lazio" homeTeamId={497} awayTeamId={487} />);
        fireEvent.error(container.querySelectorAll('img')[0]);
        expect(container.querySelectorAll('img')).toHaveLength(1);
    });
});
