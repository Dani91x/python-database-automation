// ============================================================================
// 04/10 - LE VISTE A SCHERMO TORNANO COL CONTO (segnalazione dell'utente:
// «Calcio dice -10,75, Posizioni chiuse -5,68: uniforma»). Payload della
// giornata vera del 04/10 come lo scrive il runner nuovo, letto con la
// funzione VERA (`leggiPnlRealeOggi`) e passato alle viste VERE.
// ============================================================================
import { describe, expect, it } from 'vitest';
import { render, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SplitSport } from './SplitSport';
import { PosizioniChiuse } from './PosizioniChiuse';
import { leggiPnlRealeOggi } from '@/lib/composizioneObiettivo';
import { contoPerVista, perSportDalConto } from '@/lib/composizioneConto';

const OGGI = '2026-10-04';
const VUOTA = { netto: 0, lordo: 0, ordini: 0, senza_commissione: 0 };
const FONTI_VUOTE = {
    omega: VUOTA, scalper: VUOTA, altri_bot: VUOTA, bot_tennis: VUOTA, manuale_app: VUOTA,
    safe_calcio: VUOTA, safe_tennis: VUOTA,
};
const SPORT_VUOTO = {
    netto: 0, lordo: 0, commissione: 0, ordini: 0, senza_commissione: 0,
    bot: { netto: 0, lordo: 0, ordini: 0 }, a_mano: { netto: 0, lordo: 0, ordini: 0 },
    chiusure_a_mano: { netto: 0, lordo: 0, ordini: 0 },
};
const PAYLOAD = {
    day: OGGI, lordo: -5.13, netto: -5.15, ordini: 7, commissione: 0.02,
    bet_ids: ['445568321596', '445568325409', '445568328282', '445569572640', '445572059076',
        '445572454155', '445577040174'],
    letto_at: '2026-10-04T13:08:03.439008+00:00', sospetti_sito: 0, senza_commissione: 0,
    per_fonte: {
        ...FONTI_VUOTE,
        mike: { lordo: -10.75, netto: -10.75, ordini: 5, senza_commissione: 0 },
        manuale_sito: { lordo: 5.62, netto: 5.6, ordini: 2, senza_commissione: 0 },
    },
    per_posizione: {
        ...FONTI_VUOTE,
        mike: { netto: -5.68, lordo: -5.68, ordini: 6, senza_commissione: 0 },
        manuale_sito: { netto: 0.53, lordo: 0.55, ordini: 1, senza_commissione: 0 },
    },
    chiusure_a_mano: { mike: { netto: 5.07, lordo: 5.07, ordini: 1, bet_ids: ['445577040174'] } },
    per_sport: {
        calcio: {
            netto: -5.15, lordo: -5.13, commissione: 0.02, ordini: 7, senza_commissione: 0,
            bot: { netto: -5.68, lordo: -5.68, ordini: 6 },
            a_mano: { netto: 0.53, lordo: 0.55, ordini: 1 },
            chiusure_a_mano: { netto: 5.07, lordo: 5.07, ordini: 1 },
        },
        tennis: SPORT_VUOTO, altro: SPORT_VUOTO,
    },
};
const reale = leggiPnlRealeOggi(PAYLOAD, OGGI);

describe('04/10 - tessera Calcio', () => {
    it('mostra il conto dello sport -5,15 con «bot -5,68 (di cui tue chiusure a mano +5,07) · a mano +0,53»', () => {
        const s = render(<SplitSport selezionato={null} onSeleziona={() => undefined}
            perSport={{}} perSportPaper={{}} contoEtaS={12} perSportConto={perSportDalConto(reale)} />);
        const c = within(s.getByTestId('cr-sport-calcio'));
        expect(c.getByTestId('cr-sport-calcio-live-pnl').textContent).toBe('−5,15 €');
        expect(c.getByTestId('cr-sport-calcio-live-conto').textContent).toBe('7 ordini regolati oggi');
        expect(c.getByTestId('cr-sport-calcio-live-parte-bot').textContent).toBe('−5,68 €');
        expect(c.getByTestId('cr-sport-calcio-live-chiusure-a-mano').textContent)
            .toBe(' (di cui tue chiusure a mano +5,07 €)');
        expect(c.getByTestId('cr-sport-calcio-live-a-mano').textContent).toBe('+0,53 €');
        expect(c.getByTestId('cr-sport-calcio-live-commissione').textContent).toContain('commissione 0,02 €');
    });

    it('runner di prima: gli ordini a mano non separati per sport si dicono, mai taciuti', () => {
        // FALSIFICAZIONE: non mostrare la riga -> rosso
        const vecchio = { ...PAYLOAD, per_posizione: undefined, chiusure_a_mano: undefined, per_sport: undefined };
        const s = render(<SplitSport selezionato={null} onSeleziona={() => undefined}
            perSport={{}} perSportPaper={{}} perSportConto={perSportDalConto(leggiPnlRealeOggi(vecchio, OGGI))} />);
        expect(s.getByTestId('cr-sport-calcio-live-pnl').textContent).toBe('−10,75 €');
        expect(s.getByTestId('cr-sport-calcio-live-a-mano-fuori').textContent).toContain('+5,60 €');
        expect(s.queryByTestId('cr-sport-calcio-live-scomposizione')).toBeNull();
    });
});

describe('04/10 - Posizioni chiuse: riga del conto di oggi', () => {
    const nessunaLettura = async (giorno: string, modo: 'live' | 'paper') => ({
        giorno, modo, righe: [], fonte: 'rpc' as const, avvisi: [], lettoAlle: 0,
    });
    it('«Conto Betfair oggi -5,15 = posizioni dei bot -5,68 + a mano fuori dai bot +0,53 (1 ordine)»', () => {
        // FALSIFICAZIONE: non passare/mostrare `contoOggi` -> rosso
        const s = render(
            <MemoryRouter>
                <PosizioniChiuse righe={[]} sport="calcio" giorno={OGGI} leggiGiornata={nessunaLettura}
                    contoOggi={contoPerVista(reale, 'calcio')} />
            </MemoryRouter>,
        );
        const r = s.getByTestId('cr-chiuse-conto');
        expect(within(r).getByTestId('cr-chiuse-conto-netto').textContent).toBe('−5,15 €');
        expect(within(r).getByTestId('cr-chiuse-conto-bot').textContent).toBe('−5,68 €');
        expect(within(r).getByTestId('cr-chiuse-conto-a-mano').textContent).toBe('+0,53 €');
        expect(r.textContent).toContain('(1 ordine)');
        expect(r.textContent).toContain('netto di commissione (0,02 € tolta)');
    });
});
