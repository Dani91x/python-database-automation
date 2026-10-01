// ============================================================================
// PosizioniChiuse.giornoPartita.test.tsx - 01/10, ordine dell'utente:
// «Posizioni chiuse (calcio e tennis) mostra oggi le chiusure di ieri: le
// chiusure devono essere assegnate alla giornata di riferimento».
//
// GIORNATA = giorno della PARTITA, deciso dal database (`giorno_partita`,
// `giorno_da`, `in_day`). Qui si prova a video:
//   - una partita di ieri sera regolata stanotte NON compare oggi, nemmeno se
//     in memoria (senza il dato del database) e' ancora sul regolamento;
//   - la controprova con la barra sullo STESSO perimetro della barra
//     (regolato oggi), con le posizioni a cavallo della mezzanotte ELENCATE;
//   - senza il contratto nuovo la scheda dichiara il ripiego, non finge.
// I finti hanno le chiavi delle tabelle vere piu' quelle del contratto 01/10.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PosizioniChiuse, MARGINE_LETTURA_MS, type LeggiGiornata } from './PosizioniChiuse';
import type { TradeChiudibile } from '@/lib/posizioniChiuse';
import type { ChiuseGiornata } from '@/lib/chiuseGiornata';
import type { ComposizioneObiettivo } from '@/lib/composizioneObiettivo';

const OGGI = '2026-10-01';
const IERI = '2026-09-30';

function t(over: Partial<TradeChiudibile> & { id: number }): TradeChiudibile {
    return {
        __bot: 'mike', event_id: 'E1', event_name: 'Atalanta - Como', sport: 'calcio',
        mode: 'live', status: 'won', pnl: 1, side: 'back', price: 2, size: 5,
        selection_name: 'Under 3.5', market_type: 'OVER_UNDER_35', placed_at: `${OGGI}T08:00:00.000Z`,
        settled_at: `${OGGI}T10:00:00.000Z`, closes_trade_id: null, strategy: 'under_entry',
        bet_id: `B${over.id}`, origin: 'auto',
        size_requested: 5, size_matched: 5, size_remaining: 0, avg_price_matched: 2, meta: null,
        ...over,
    };
}
const conGiorno = (r: TradeChiudibile, giorno: string, inDay: boolean): TradeChiudibile => ({
    ...r, giorno_partita: giorno, giorno_da: 'partita', in_day: inDay,
});

/** la partita di IERI 23:30, regolata OGGI 01:15 (Roma) */
const ieriNotte = t({ id: 7, pnl: 2, event_id: 'E7', event_name: 'Partita di ieri sera',
    placed_at: `${IERI}T21:30:00.000Z`, settled_at: `${IERI}T23:15:00.000Z` });
/** una partita di OGGI regolata oggi */
const diOggi = t({ id: 1, pnl: 1, settled_at: `${OGGI}T10:00:00.000Z` });

function lettura(giorno: string, righe: TradeChiudibile[], opz: Partial<ChiuseGiornata> = {}): ChiuseGiornata {
    return { giorno, modo: 'live', righe, fonte: 'rpc', avvisi: [], lettoAlle: 0, ...opz };
}

function monta(righe: TradeChiudibile[], leggi: LeggiGiornata, barra: ComposizioneObiettivo | null = null) {
    return render(
        <MemoryRouter>
            <PosizioniChiuse righe={righe} sport={null} giorno={OGGI} barra={barra} leggiGiornata={leggi} />
        </MemoryRouter>,
    );
}

describe('la chiusura di ieri sera NON e\' di oggi', () => {
    // la lettura di OGGI (contratto nuovo) e' partita alle 12:00: la riga di
    // ieri, regolata alle 01:15, c'era gia' e NON e' fra quelle del giorno
    const chiestoAlle = Date.parse(`${OGGI}T10:00:00.000Z`);

    it('in memoria senza il giorno del database, la lettura di oggi la esclude: fuori dal totale, contata', async () => {
        const leggi: LeggiGiornata = async (g, m) => ({
            ...lettura(g, [conGiorno(diOggi, OGGI, true)], { giornoPartita: true, chiestoAlle }), modo: m,
        });
        monta([diOggi, ieriNotte], leggi);
        await waitFor(() => expect(screen.queryByTestId('cr-chiusa-7')).toBeNull());
        expect(screen.getByTestId('cr-chiuse-totale')).toHaveTextContent('+1,00');
        expect(screen.getByTestId('cr-chiuse-fuori-giornata')).toHaveTextContent('Altre 1 posizioni');
    });

    it('FALSIFICAZIONE: senza la conferma del database (lettura vecchia) la stessa riga resta oggi, ma PROVVISORIA', async () => {
        const leggi: LeggiGiornata = async (g, m) => ({ ...lettura(g, [diOggi], { giornoPartita: false, chiestoAlle }), modo: m });
        monta([diOggi, ieriNotte], leggi);
        await waitFor(() => expect(screen.getByTestId('cr-chiuse-giornata-ripiego')).toBeInTheDocument());
        expect(screen.getByTestId('cr-chiusa-7')).toBeInTheDocument();
        expect(screen.getByTestId('cr-chiuse-totale')).toHaveTextContent('+3,00');
        expect(screen.getByTestId('cr-chiuse-giornata-ripiego')).toHaveTextContent(/non manda ancora il giorno della\s+partita/);
    });

    it('regolata DOPO l\'inizio della lettura (meno del margine): resta provvisoria, mai esclusa a torto', async () => {
        const recente = t({ id: 9, pnl: 0.5, event_id: 'E9', settled_at: new Date(chiestoAlle - MARGINE_LETTURA_MS / 2).toISOString() });
        const leggi: LeggiGiornata = async (g, m) => ({
            ...lettura(g, [conGiorno(diOggi, OGGI, true)], { giornoPartita: true, chiestoAlle }), modo: m,
        });
        monta([diOggi, recente], leggi);
        await waitFor(() => expect(screen.getByTestId('cr-chiuse-nota-provvisorie')).toBeInTheDocument());
        expect(screen.getByTestId('cr-chiusa-9')).toBeInTheDocument();
    });
});

describe('B-12: controprova con la barra sullo STESSO perimetro, e la mezzanotte elencata', () => {
    const barra = (mike: number | null, scalper: number | null = null): ComposizioneObiettivo => ({
        righe: [
            { chiave: 'mike', etichetta: 'Mike', valore: mike },
            { chiave: 'scalper', etichetta: 'Scalper calcio', valore: scalper },
            { chiave: 'manuale_sito', etichetta: 'Manuale sito', valore: 99 },
        ],
        totale: null, provaPaper: null,
    });
    // la lettura di oggi porta ANCHE la riga di ieri regolata oggi, con in_day=false
    const leggi: LeggiGiornata = async (g, m) => ({
        ...lettura(g, [conGiorno(diOggi, OGGI, true), conGiorno(ieriNotte, IERI, false)], { giornoPartita: true }),
        modo: m,
    });

    it('la barra (regolato oggi = 1 + 2) coincide; la scheda di oggi dice 1 e ELENCA la partita di ieri', async () => {
        monta([diOggi, ieriNotte], leggi, barra(3));
        await waitFor(() => expect(screen.getByTestId('cr-chiuse-a-cavallo')).toBeInTheDocument());
        expect(screen.getByTestId('cr-chiuse-totale')).toHaveTextContent('+1,00');
        expect(screen.getByTestId('cr-chiuse-controprova').dataset.coincide).toBe('1');
        const voce = screen.getByTestId('cr-chiuse-a-cavallo-7');
        expect(voce).toHaveTextContent('Partita di ieri sera');
        expect(voce).toHaveTextContent('+2,00');
        expect(voce).toHaveTextContent('(non in questa giornata)');
    });

    it('FALSIFICAZIONE: col vecchio confronto (totale della scheda contro la barra) mancherebbero 2,00 €', async () => {
        monta([diOggi, ieriNotte], leggi, barra(1));
        await waitFor(() => expect(screen.getByTestId('cr-chiuse-a-cavallo')).toBeInTheDocument());
        // la barra dice 1 ma sul conto oggi sono regolati 3: la differenza e' vera e si vede
        expect(screen.getByTestId('cr-chiuse-controprova').dataset.coincide).toBe('0');
        expect(screen.getByTestId('cr-chiuse-controprova-qui')).toHaveTextContent('+3,00');
        expect(screen.getByTestId('cr-chiuse-controprova-diff')).toHaveTextContent('+2,00');
    });

    it('C-06: lo Scalper calcio della barra e\' dichiarato con la sua cifra, fuori dal confronto', async () => {
        monta([diOggi, ieriNotte], leggi, barra(3, 0.7));
        await waitFor(() => expect(screen.getByTestId('cr-chiuse-controprova-scalper')).toHaveTextContent('+0,70'));
        expect(screen.getByTestId('cr-chiuse-controprova').dataset.coincide).toBe('1');
    });
});

describe('note fisse e testi del criterio', () => {
    it('la giornata e\' per PARTITA (title e aria), e i cicli con gambe aperte sono dichiarati fuori', () => {
        monta([diOggi], async (g, m) => ({ ...lettura(g, []), modo: m }));
        expect(screen.getByTestId('cr-chiuse-giornata').getAttribute('title')).toMatch(/giorno della PARTITA/);
        expect(screen.getByTestId('cr-f-giorno').getAttribute('aria-label')).toBe('giornata della partita da mostrare');
        expect(screen.getByTestId('cr-chiuse-nota-cicli-aperti')).toHaveTextContent('Qui solo operazioni CHIUSE');
    });

    it('inizio partita non noto: «giorno di piazzamento», contato', () => {
        const r = { ...diOggi, giorno_partita: null, giorno_da: 'piazzamento', in_day: true };
        monta([r], async (g, m) => ({ ...lettura(g, []), modo: m }));
        expect(screen.getByTestId('cr-chiuse-nota-piazzamento')).toHaveTextContent('1 operazione senza inizio partita noto');
    });
});

// C-08 (01/10, rilievi bassi): il badge «parziale» non aveva un test. Compare
// SOLO per una giornata PASSATA letta in ripiego (bot tennis assenti) e quando
// la scheda comprende il tennis. FALSIFICAZIONE: con `parziale` sempre falso il
// primo caso diventa rosso; con la condizione su oggi o sullo sport tolta,
// diventano rossi i casi negativi.
describe('C-08: «parziale» sulla giornata passata letta in ripiego', () => {
    const ieriDb = t({ id: 30, pnl: 1.5, event_id: 'E30', placed_at: `${IERI}T08:00:00.000Z`,
        settled_at: `${IERI}T10:00:00.000Z` });
    const leggiCon = (fonte: ChiuseGiornata['fonte']): LeggiGiornata => async (g, m) => ({
        ...lettura(g, g === IERI ? [ieriDb] : [], { fonte, giornoPartita: false }), modo: m,
    });
    function montaSport(sport: 'calcio' | 'tennis' | null, leggi: LeggiGiornata) {
        return render(
            <MemoryRouter>
                <PosizioniChiuse righe={[]} sport={sport} giorno={OGGI} leggiGiornata={leggi} />
            </MemoryRouter>,
        );
    }
    async function vaiAIeri() {
        fireEvent.click(screen.getByTestId('cr-f-giorno-prima'));
        await waitFor(() => expect(screen.getByTestId('cr-chiuse-totale')).toHaveTextContent('+1,50'));
    }

    it('ieri, lettura di ripiego, tutti gli sport: «parziale» col motivo', async () => {
        montaSport(null, leggiCon('ripiego'));
        await vaiAIeri();
        const b = screen.getByTestId('cr-chiuse-parziale');
        expect(b).toHaveTextContent('parziale');
        expect(b.getAttribute('title')).toMatch(/bot tennis di questa giornata non sono letti/);
    });

    it('ieri, lettura di ripiego, scheda tennis: «parziale»', async () => {
        montaSport('tennis', leggiCon('ripiego'));
        fireEvent.click(screen.getByTestId('cr-f-giorno-prima'));
        await waitFor(() => expect(screen.getByTestId('cr-chiuse-parziale')).toBeInTheDocument());
    });

    it('ieri, lettura completa: nessun «parziale»', async () => {
        montaSport(null, leggiCon('rpc'));
        await vaiAIeri();
        expect(screen.queryByTestId('cr-chiuse-parziale')).toBeNull();
    });

    it('ieri, ripiego, scheda CALCIO: nessun «parziale» (il ripiego legge tutto il calcio)', async () => {
        montaSport('calcio', leggiCon('ripiego'));
        await vaiAIeri();
        expect(screen.queryByTestId('cr-chiuse-parziale')).toBeNull();
    });

    it('OGGI in ripiego: nessun «parziale» (oggi i bot tennis arrivano dalla memoria)', async () => {
        const leggi: LeggiGiornata = async (g, m) => ({ ...lettura(g, [diOggi], { fonte: 'ripiego' }), modo: m });
        montaSport(null, leggi);
        await waitFor(() => expect(screen.getByTestId('cr-chiuse-totale')).toHaveTextContent('+1,00'));
        expect(screen.queryByTestId('cr-chiuse-parziale')).toBeNull();
    });
});
