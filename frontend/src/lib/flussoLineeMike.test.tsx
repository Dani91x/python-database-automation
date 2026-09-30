// 30/09 - «⚠ FLUSSO PREZZI INTERROTTO da 1628 s» sulla scheda PRE-PARTITA.
// Il blocco `flusso` della riga riguarda il MATCH ODDS, che prima del fischio
// lo scanner non segue (motivo `mai_ricevuto`, `dal_ms` = creazione della
// riga), mentre le linee Under/Over 3,5 e 4,5 di Mike arrivano al secondo.
// La scheda giudica le LINEE DI MIKE con la stessa regola di Mike
// (`Betfair/mike/feed.py::flusso_esito` + `mercati_di_mike`) e il Match Odds
// pre-partita non ricevuto e' una nota grigia. La riga finta ha le chiavi e i
// tipi della riga vera di `safe_strategy_scan` (scanner: `flusso_evento`,
// `build_market_block` + `seen_ms`), come la riga 36132117 del 30/09.
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { giudizioFlussoMike, giudizioFlusso, type FlussoRiga } from './flussoPrezzi';
import { costruisciGiornata, type PartitaFeedLike } from './controlRoom';
import { mikeActivityLine, MIKE_ACTIVITY_EXTRA } from './mike';
import { activityMeta } from './tradeStatus';
import FlussoBadge from '@/components/controlroom/FlussoBadge';
import { SchedaPreMatch } from '@/components/controlroom/SchedaPreMatch';
import { SchedaPartita } from '@/components/controlroom/SchedaPartita';

const ORA = Date.parse('2026-09-30T13:00:00Z');
const KO = '2026-09-30T14:00:00.000Z';

function blocco(line: number, marketId: string, seenFaS: number) {
    return {
        market_id: marketId, status: 'OPEN', inplay: false, total_matched: 812.4,
        market_type: `OVER_UNDER_${String(line).replace('.', '')}`, line, ts_ms: ORA - 60_000,
        bet_delay: 0, seen_ms: ORA - seenFaS * 1000,
        selections: [
            { selection_id: 1222344, name: `Under ${line} Goals`, runner_status: 'ACTIVE',
                back: 1.5, lay: 1.52, back_size: 30, lay_size: 25 },
            { selection_id: 1222345, name: `Over ${line} Goals`, runner_status: 'ACTIVE',
                back: 2.6, lay: 2.7, back_size: 20, lay_size: 15 },
        ],
    };
}

/** La riga pre-partita del 30/09: Match Odds mai ricevuto da 1628 s, linee vive. */
function riga(fermi: string[] = [], over: Partial<Record<string, unknown>> = {}) {
    const flusso: FlussoRiga = { vivo: false, motivo: 'mai_ricevuto', dal_ms: ORA - 1_628_000, mercati_fermi: fermi };
    return {
        event_name: 'Roma v Lazio', home: 'Roma', away: 'Lazio', competition: 'Serie A',
        open_date: KO, inplay: false, mo_market_id: '1.250', mo_status: 'OPEN',
        odds: { home: { back: 1.9, lay: 1.92 }, draw: { back: 3.4, lay: 3.5 }, away: { back: 4.2, lay: 4.3 } },
        odds_ts_ms: ORA - 5_000, minute: null, score_home: null, score_away: null,
        ou: [blocco(3.5, '1.35', 36), blocco(4.5, '1.45', 1)],
        flusso,
        ...over,
    };
}

function partita(payload: ReturnType<typeof riga>) {
    const g = costruisciGiornata({
        righe: [{ event_id: '36132117', sport: 'calcio', updated_at: new Date(ORA).toISOString(),
            payload: payload as PartitaFeedLike }],
        soldi: new Map(), nowMs: ORA,
    });
    return g[0].partite[0];
}

describe('giudizioFlussoMike: la stessa regola di Mike', () => {
    it('pre-partita, Match Odds mai ricevuto, linee vive: le linee di Mike sono VIVE', () => {
        expect(giudizioFlussoMike(riga(), ORA).stato).toBe('vivo');
    });
    it('linea 3,5 in mercati_fermi: QUALE linea e l’eta’ del suo ultimo book', () => {
        const g = giudizioFlussoMike(riga(['1.35']), ORA);
        expect(g.stato).toBe('fermo');
        expect(g.linee).toEqual([{ marketId: '1.35', nome: 'Under/Over 3,5', daS: 36, esatto: false }]);
        // 30/09 sera: senza `fermi_da_ms` (scanner precedente) l'eta' e' quella
        // della RIGA (`seen_ms` e' fuori firma), e lo si dice
        expect(g.testo).toContain('Under/Over 3,5 (1.35) ferma, riga scritta 36 s fa');
        expect(g.linee[0].esatto).toBe(false);
    });
    it('una linea gia’ decisa dai gol non conta (mercato_deciso, 30/09)', () => {
        const g = giudizioFlussoMike(riga(['1.35'], { inplay: true, score_home: 3, score_away: 1 }), ORA);
        expect(g.stato).toBe('vivo');
    });
    it('mercati fermi che non sono linee di Mike non contano', () => {
        expect(giudizioFlussoMike(riga(['1.25', '1.CS']), ORA).stato).toBe('vivo');
    });
    it('riga senza linee di Mike o senza flusso: nessun giudizio', () => {
        expect(giudizioFlussoMike(riga([], { ou: [] }), ORA).stato).toBe('senza_linee');
        expect(giudizioFlussoMike(riga([], { flusso: undefined }), ORA).stato).toBe('non_dichiarato');
    });
});

describe('scheda PRE-PARTITA', () => {
    it('Match Odds non ancora seguito: nota grigia, niente rosso, niente 1628 s', () => {
        render(<MemoryRouter><SchedaPreMatch p={partita(riga())} scheda="pre" mancaS={3600} /></MemoryRouter>);
        const b = screen.getByTestId('cr-flusso');
        expect(b.getAttribute('data-stato')).toBe('mo_non_ricevuto');
        expect(b.textContent).toBe('Match Odds: prezzi non ancora ricevuti');
        expect(screen.getByTestId('cr-pre-quote').textContent).not.toContain('INTERROTTO');
        expect(screen.getByTestId('cr-pre-quote').textContent).not.toContain('1628');
        expect(screen.queryByTestId('cr-flusso-mike')).toBeNull();
    });
    it('linea di Mike ferma: badge rosso con la linea e i secondi del suo ultimo book', () => {
        render(<MemoryRouter><SchedaPreMatch p={partita(riga(['1.35']))} scheda="pre" mancaS={3600} /></MemoryRouter>);
        const b = screen.getByTestId('cr-flusso-mike');
        expect(b.textContent).toBe('⚠ Under/Over 3,5 ferma · riga scritta 36 s fa');
        expect(b.getAttribute('title')).toContain('Mike non apre su queste linee');
    });
    it('linea ferma anche senza quote 1X2: la riga si monta lo stesso', () => {
        render(<MemoryRouter><SchedaPreMatch p={partita(riga(['1.45'], { odds: null, odds_ts_ms: null }))}
            scheda="pre" mancaS={3600} /></MemoryRouter>);
        expect(screen.getByTestId('cr-flusso-mike').textContent).toContain('Under/Over 4,5 ferma');
    });
    it('Match Odds davvero interrotto prima del fischio (flusso_interrotto): resta rosso', () => {
        const p = riga([], { flusso: { vivo: false, motivo: 'flusso_interrotto', dal_ms: ORA - 40_000, mercati_fermi: [] } });
        render(<MemoryRouter><SchedaPreMatch p={partita(p)} scheda="pre" mancaS={600} /></MemoryRouter>);
        expect(screen.getByTestId('cr-flusso').getAttribute('data-stato')).toBe('interrotto');
    });
});

describe('scheda IN GIOCO (Safe/Omega: il Match Odds come prima)', () => {
    it('senza prePartita il Match Odds mai ricevuto resta il rosso di prima', () => {
        const g = giudizioFlusso({ vivo: false, motivo: 'mai_ricevuto', dal_ms: ORA - 1_628_000, mercati_fermi: [] }, ORA);
        render(<FlussoBadge flusso={g} />);
        expect(screen.getByTestId('cr-flusso').getAttribute('data-stato')).toBe('interrotto');
        expect(screen.getByTestId('cr-flusso').textContent).toContain('FLUSSO PREZZI INTERROTTO');
    });
    it('la scheda in gioco mostra anche le linee di Mike ferme', () => {
        const p = partita(riga(['1.45'], { inplay: true, minute: 27, score_home: 1, score_away: 0,
            flusso: { vivo: true, motivo: null, dal_ms: ORA - 1_628_000, mercati_fermi: ['1.45'] } }));
        render(<MemoryRouter><SchedaPartita p={p} operazioni={[]} /></MemoryRouter>);
        expect(screen.getByTestId('cr-flusso-mike').textContent).toBe('⚠ Under/Over 4,5 ferma · riga scritta 1 s fa');
    });
    it('30/09 sera: con `flusso.fermi_da_ms` dello scanner l’eta’ e’ quella VERA dell’ultimo prezzo, non della riga', () => {
        const p = partita(riga(['1.45'], { inplay: true, minute: 27, score_home: 1, score_away: 0,
            flusso: { vivo: true, motivo: null, dal_ms: ORA - 1_628_000, mercati_fermi: ['1.45'],
                fermi_da_ms: { '1.45': ORA - 41_000 } } as FlussoRiga }));
        render(<MemoryRouter><SchedaPartita p={p} operazioni={[]} /></MemoryRouter>);
        expect(screen.getByTestId('cr-flusso-mike').textContent).toBe('⚠ Under/Over 4,5 ferma · ultimo prezzo 41 s fa');
        const g = giudizioFlussoMike(riga(['1.45'], { inplay: true, minute: 27, score_home: 1, score_away: 0,
            flusso: { vivo: true, motivo: null, dal_ms: ORA - 1_628_000, mercati_fermi: ['1.45'],
                fermi_da_ms: { '1.45': ORA - 41_000 } } as FlussoRiga }), ORA);
        expect(g.linee).toEqual([{ marketId: '1.45', nome: 'Under/Over 4,5', daS: 41, esatto: true }]);
        expect(g.testo).toContain('ultimo prezzo ricevuto 41 s fa');
    });
});

describe('diario di Mike', () => {
    it('flusso_interrotto_senza_rest dice la linea (testo del servizio) e i secondi', () => {
        const riga = mikeActivityLine('flusso_interrotto_senza_rest', {
            critical: true, reason: 'mercato_fermo', state: 'LIVE_COVERED', mercati: ['1.35'],
            esposizione_eur: 12.5, da_secondi: 36.0,
            testo: 'flusso prezzi fermo sulle linee di Mike: Under/Over 3,5 (1.35) ferma, ultimo book ricevuto 36 s fa',
            selezioni: ['OU35|UNDER'], message: 'flusso prezzi FERMO e book REST non leggibile',
        });
        expect(riga).toContain('Under/Over 3,5 (1.35) ferma');
        expect(riga).toContain('ultimo dato 36 s fa');
        expect(riga).toContain('esposizione 12,50 €');
    });
    it('da_secondi assente: nessun "0 s" inventato', () => {
        const riga = mikeActivityLine('flusso_interrotto_senza_rest', {
            critical: true, reason: 'mercato_fermo', state: 'LIVE_COVERED', da_secondi: null,
        });
        expect(riga).not.toContain('0 s');
    });
    it('canale_inviato ha la sua etichetta italiana', () => {
        expect(MIKE_ACTIVITY_EXTRA.canale_inviato?.label).toBe('ORDINE INVIATO SUL CANALE · attesa esito');
        expect(activityMeta('canale_inviato', MIKE_ACTIVITY_EXTRA).label).not.toMatch(/[a-z]+_[a-z]+/);
    });
});
