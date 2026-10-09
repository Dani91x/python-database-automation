// ============================================================================
// ritorno.pagine.test.tsx - 08/10 (cantiere W1): il punto di ritorno con DUE
// pagine di partenza (Control Room e Cash Out).
//   * `AzioniPartita` di serie segna la Control Room (identico a prima); con
//     `ritorno` il Cash Out;
//   * i «Torna» delle pagine di arrivo leggono l'origine dal `from`;
//   * `useRitornoAlPunto` consuma SOLO un punto della sua rotta, e riporta
//     davvero in vista la partita (il timer non si cancella da solo).
// ============================================================================
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@/lib/omegaMissions', async (orig) => ({
    ...(await orig() as object),
    followMission: vi.fn(async () => undefined),
}));

import type { ReactElement } from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { AzioniPartita } from '@/components/controlroom/AzioniPartita';
import {
    ORIGINI_RITORNO, origineRitorno, leggiRitorno, salvaRitorno, useRitornoAlPunto,
} from '@/lib/ritorno';
import type { PartitaGiornata } from '@/lib/controlRoom';
import { followMission } from '@/lib/omegaMissions';

function partita(): PartitaGiornata {
    return {
        event_id: 'E1', sport: 'calcio', nome: 'Inter v Milan', campionato: 'Serie A',
        koMs: Date.parse('2026-10-08T13:00:00Z'), stato: 'live', minuto: 10, punteggio: '0-0',
        controlloDisponibile: true, etaFeedS: 1, freschezza: 'fresca', latenzaQuoteS: 1,
        freschezzaQuote: 'fresca', statoQuote: 'fresco', media: null, marketId: '1.MO', soldi: null,
        target: null, avanzamento: null,
        extra: { campionato: null, leagueId: null, homeTeamId: null, awayTeamId: null, fixtureId: 777 },
    };
}

function Dove() {
    const l = useLocation();
    return <div data-testid="dove">{l.pathname + l.search}</div>;
}

function monta(el: ReactElement) {
    return render(
        <MemoryRouter initialEntries={['/qui']}>
            <Routes>
                <Route path="/qui" element={el} />
                <Route path="/dashboard" element={<Dove />} />
                <Route path="/tennis/terminal" element={<Dove />} />
                <Route path="/segui-live" element={<Dove />} />
            </Routes>
        </MemoryRouter>,
    );
}

beforeEach(() => sessionStorage.clear());

describe('AzioniPartita: da dove si parte', () => {
    it('di serie: Control Room, come prima (rotta, nome, from=control-room)', () => {
        monta(<AzioniPartita p={partita()} scheda="live" />);
        fireEvent.click(screen.getByTestId('cr-statistiche'));
        expect(screen.getByTestId('dove').textContent).toBe('/dashboard?fixture=777&from=control-room');
        expect(leggiRitorno()).toMatchObject({ rotta: '/control-room', nome: 'Control Room', scheda: 'live', eventId: 'E1' });
    });

    it('dal Cash Out: rotta /cash-out, nome Cash Out, from=cash-out', () => {
        monta(<AzioniPartita p={partita()} scheda="cash-out" ritorno={ORIGINI_RITORNO['cash-out']} />);
        fireEvent.click(screen.getByTestId('cr-statistiche'));
        expect(screen.getByTestId('dove').textContent).toBe('/dashboard?fixture=777&from=cash-out');
        expect(leggiRitorno()).toMatchObject({ rotta: '/cash-out', nome: 'Cash Out', eventId: 'E1' });
    });
});

describe('AzioniPartita: soloMediaStatistiche (secondo giro)', () => {
    it('di serie TUTTI i pulsanti di oggi (video/stats, Statistiche, Trading, Segui live)', () => {
        monta(<AzioniPartita p={partita()} scheda="live" />);
        for (const id of ['cr-statistiche', 'cr-trading', 'cr-segui-live']) expect(screen.getByTestId(id)).toBeTruthy();
        expect(screen.getByTestId('cr-azioni').querySelectorAll('button').length).toBeGreaterThanOrEqual(5);
    });

    it('con la prop: solo Video | Stats Betfair e «Statistiche»', () => {
        monta(<AzioniPartita p={partita()} scheda="cash-out" soloMediaStatistiche />);
        expect(screen.getByTestId('cr-statistiche')).toBeTruthy();
        expect(screen.queryByTestId('cr-trading')).toBeNull();
        expect(screen.queryByTestId('cr-segui-live')).toBeNull();
        // restano i due pulsanti Betfair + Statistiche
        expect(screen.getByTestId('cr-azioni').querySelectorAll('button').length).toBe(3);
    });
});

describe('AzioniPartita dal Programma del giorno (09/10)', () => {
    const tennis = (marketId: string | null): PartitaGiornata => ({
        ...partita(), event_id: 'T1', sport: 'tennis', nome: 'Sinner v Draper', marketId, extra: null,
    });

    it('origine board: Statistiche calcio con from=board e punto su /board', () => {
        monta(<AzioniPartita p={partita()} scheda="calcio" ritorno={ORIGINI_RITORNO.board} />);
        fireEvent.click(screen.getByTestId('cr-statistiche'));
        expect(screen.getByTestId('dove').textContent).toBe('/dashboard?fixture=777&from=board');
        expect(leggiRitorno()).toMatchObject({ rotta: '/board', nome: 'Programma', scheda: 'calcio', eventId: 'E1' });
    });

    it('tennis: «Statistiche» solo se chiesto, e apre il Tennis Terminal sulla partita', () => {
        const { unmount } = monta(<AzioniPartita p={tennis('1.T')} scheda="tennis" />);
        expect(screen.queryByTestId('cr-statistiche')).toBeNull();   // Control Room: come prima
        unmount();
        monta(<AzioniPartita p={tennis('1.T')} scheda="tennis" ritorno={ORIGINI_RITORNO.board} statisticheTennis />);
        fireEvent.click(screen.getByTestId('cr-statistiche'));
        expect(screen.getByTestId('dove').textContent)
            .toBe('/tennis/terminal?event=T1&market=1.T&name=Match+Odds&from=board&p1=Sinner&p2=Draper');
    });

    it('tennis SENZA mercato: Trading non scrive un seguito calcio, lo dice', async () => {
        vi.mocked(followMission).mockClear();
        monta(<AzioniPartita p={tennis(null)} scheda="tennis" ritorno={ORIGINI_RITORNO.board} statisticheTennis />);
        expect(screen.getByTestId('cr-statistiche')).toBeDisabled();
        await act(async () => { fireEvent.click(screen.getByTestId('cr-trading')); });
        expect(followMission).not.toHaveBeenCalled();
        expect(screen.getByTestId('cr-azioni-errore').textContent).toContain('manca il mercato Match Odds');
        expect(screen.queryByTestId('dove')).toBeNull();
    });
});

describe('«Torna»: l\'origine dal parametro from', () => {
    it('board: «Torna al Programma» verso /board', () => {
        expect(origineRitorno('board')).toEqual({
            rotta: '/board', nome: 'Programma', from: 'board',
            torna: 'Torna al Programma', testId: 'torna-board',
            titolo: 'torna al Programma del giorno, alla scheda sport e alla partita da cui sei partito',
        });
    });

    it('control-room invariato, cash-out nuovo, altro = nessun pulsante', () => {
        expect(origineRitorno('control-room')).toEqual({
            rotta: '/control-room', nome: 'Control Room', from: 'control-room',
            torna: 'Torna alla Control Room', testId: 'torna-control-room',
            titolo: 'torna alla Control Room, alla scheda e alla partita da cui sei partito',
        });
        expect(origineRitorno('cash-out')).toMatchObject({ rotta: '/cash-out', torna: 'Torna al Cash Out', testId: 'torna-cash-out' });
        expect(origineRitorno('omega')).toBeNull();
        expect(origineRitorno(null)).toBeNull();
    });
});

describe('useRitornoAlPunto', () => {
    function Pagina({ rotta }: { rotta: string }) {
        useRitornoAlPunto(rotta, true);
        return <div data-event-id="E7" data-testid="riga">partita</div>;
    }
    const scroll = vi.fn();
    beforeEach(() => {
        vi.useFakeTimers();
        scroll.mockReset();
        Element.prototype.scrollIntoView = scroll;
    });
    afterEach(() => vi.useRealTimers());

    it('il punto della SUA rotta si consuma e la partita torna in vista', () => {
        salvaRitorno({ rotta: '/cash-out', nome: 'Cash Out', scheda: null, eventId: 'E7', scorrimento: 0 });
        render(<Pagina rotta="/cash-out" />);
        act(() => { vi.advanceTimersByTime(100); });
        expect(scroll).toHaveBeenCalledTimes(1);
        expect(screen.getByTestId('riga').className).toContain('ring-2');
        expect(leggiRitorno()).toBeNull();
    });

    it('il punto di UN\'ALTRA pagina non si tocca: resta a chi l\'ha salvato', () => {
        salvaRitorno({ rotta: '/control-room', nome: 'Control Room', scheda: 'aperte', eventId: 'E7', scorrimento: 0 });
        render(<Pagina rotta="/cash-out" />);
        act(() => { vi.advanceTimersByTime(100); });
        expect(scroll).not.toHaveBeenCalled();
        expect(leggiRitorno()).toMatchObject({ rotta: '/control-room', scheda: 'aperte' });
    });
});
