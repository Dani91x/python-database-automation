// ============================================================================
// StrisciaEsitoChiusura.test.tsx — LA STRISCIA DI ESITO dopo l'approvazione.
//
// Ogni riga (`RigaOrdine`) porta le IDENTICHE chiavi delle colonne della
// migrazione `trades_consapevolezza_ordine_2026-09-16.sql` (`size_matched`,
// `size_remaining`, `avg_price_matched`, `betfair_updated_at`), esattamente
// come le scrive il servizio e come le legge `lib/statoOrdine.ts` — nessuna
// chiave inventata.
//
// FALSIFICAZIONE (verificata a mano): rimuovere il controllo `!apertura`
// (o `chiusure.length === 0 && !regolataDalMercato`) fa comparire una riga
// vuota nel primo test — rosso; rimuovere `esposta &&` fa comparire "ancora
// esposti 0,00 €" nel test CONFERMATA — rosso; rimuovere
// `role={... 'alert' : undefined}` fa fallire il test CHIUSURA_FALLITA — rosso.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StrisciaEsitoChiusura } from './StrisciaEsitoChiusura';
import type { RigaOrdine } from '@/lib/statoOrdine';

function apertura(over: Partial<RigaOrdine> = {}): RigaOrdine {
    return {
        status: 'open', side: 'back', price: 2.0, size: 10,
        size_requested: 10, size_matched: 10, size_remaining: 0,
        avg_price_matched: 2.0, betfair_updated_at: '2026-09-18T10:00:00.000Z',
        meta: null,
        ...over,
    };
}

function gamba(over: Partial<RigaOrdine> = {}): RigaOrdine {
    return {
        status: 'open', side: 'lay', price: 2.0, size: 0,
        size_requested: 0, size_matched: 0, size_remaining: 0,
        avg_price_matched: null, betfair_updated_at: '2026-09-18T10:05:00.000Z',
        meta: null,
        ...over,
    };
}

describe('montaggio additivo: niente dati, niente riga', () => {
    it('senza apertura non renderizza nulla', () => {
        const { container } = render(
            <StrisciaEsitoChiusura apertura={null} chiusure={[]} modo="live" />,
        );
        expect(container).toBeEmptyDOMElement();
    });

    it('con apertura ma nessuna chiusura e nessun invio dichiarato: nulla (nessuna azione ancora tentata)', () => {
        const { container } = render(
            <StrisciaEsitoChiusura apertura={apertura()} chiusure={[]} modo="live" />,
        );
        expect(container).toBeEmptyDOMElement();
    });
});

describe('"inviata": distinta da "non verificabile"', () => {
    it('inviata=true senza righe ancora arrivate mostra "inviata", non un allarme', () => {
        render(
            <StrisciaEsitoChiusura apertura={apertura()} chiusure={[]} modo="live" inviata />,
        );
        const riga = screen.getByTestId('striscia-esito-chiusura');
        expect(riga.textContent).toMatch(/inviata/i);
        expect(riga.dataset.stato).toBeUndefined();
    });
});

describe('CHIUSA_CONFERMATA: verde, nessuna esposizione mostrata', () => {
    it('copertura completa dalle colonne di Betfair, in LIVE', () => {
        render(
            <StrisciaEsitoChiusura
                apertura={apertura({ side: 'back', size_matched: 10, avg_price_matched: 2.0 })}
                chiusure={[gamba({ side: 'lay', size_matched: 10, size_remaining: 0, avg_price_matched: 2.0 })]}
                modo="live"
                testId="cr-esito"
            />,
        );
        const riga = screen.getByTestId('cr-esito');
        expect(riga.dataset.stato).toBe('CHIUSA_CONFERMATA');
        expect(riga.textContent).toMatch(/CHIUSA/);
        expect(riga.textContent).toMatch(/CONFERMATA/);
        expect(riga.textContent).not.toMatch(/ancora esposti/);
        expect(screen.queryByTestId('cr-esito-esposizione')).toBeNull();
        expect(riga).not.toHaveAttribute('role', 'alert');
    });
});

describe('CHIUSA_PARZIALE: arancione, importo esposto in evidenza', () => {
    it('due lay abbinate su tre, il residuo esatto e in vista', () => {
        render(
            <StrisciaEsitoChiusura
                apertura={apertura({ side: 'back', size_matched: 10, avg_price_matched: 2.0 })}
                chiusure={[
                    gamba({ side: 'lay', size_matched: 4, size_remaining: 0, avg_price_matched: 2.0 }),
                    gamba({ side: 'lay', size_matched: 4, size_remaining: 0, avg_price_matched: 2.0 }),
                    gamba({ side: 'lay', status: 'cancelled', size_matched: 0, size_remaining: 0, avg_price_matched: null }),
                ]}
                modo="live"
                testId="cr-esito"
            />,
        );
        const riga = screen.getByTestId('cr-esito');
        expect(riga.dataset.stato).toBe('CHIUSA_PARZIALE');
        expect(screen.getByTestId('cr-esito-esposizione').textContent).toMatch(/2,00/);
    });
});

describe('CHIUSURA_FALLITA: rosso, allarme, posizione ancora aperta', () => {
    it('unica chiusura rifiutata da Betfair: tutto lo stake resta esposto', () => {
        render(
            <StrisciaEsitoChiusura
                apertura={apertura({ side: 'back', size_matched: 10, avg_price_matched: 2.0 })}
                chiusure={[gamba({
                    side: 'lay', size_matched: 0, size_remaining: 0,
                    meta: { error_code: 'INSUFFICIENT_FUNDS' },
                })]}
                modo="live"
                testId="cr-esito"
            />,
        );
        const riga = screen.getByTestId('cr-esito');
        expect(riga.dataset.stato).toBe('CHIUSURA_FALLITA');
        expect(riga.dataset.allarme).toBe('1');
        expect(riga).toHaveAttribute('role', 'alert');
        expect(riga.textContent).toMatch(/FALLITA/);
        expect(riga.textContent).toMatch(/ANCORA APERTA/);
        expect(screen.getByTestId('cr-esito-esposizione').textContent).toMatch(/10,00/);
    });
});

describe('REGOLATA_DAL_MERCATO: verde, senza nemmeno una gamba di chiusura', () => {
    it('mercato regolato prevale su tutto', () => {
        render(
            <StrisciaEsitoChiusura
                apertura={apertura({ status: 'won' })}
                chiusure={[]}
                regolataDalMercato
                modo="live"
                testId="cr-esito"
            />,
        );
        expect(screen.getByTestId('cr-esito').dataset.stato).toBe('REGOLATA_DAL_MERCATO');
    });
});
