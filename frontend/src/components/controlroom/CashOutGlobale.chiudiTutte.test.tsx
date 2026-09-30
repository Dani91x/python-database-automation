// ============================================================================
// CashOutGlobale.chiudiTutte.test.tsx - 30/09 sera (W_C, P16): «Chiudi tutte le
// gambe dei bot». Si orchestrano IN SEQUENZA i comandi GIA' esistenti del
// pulsante di riga (`ChiusuraRigaContext.chiudi`): Mike una volta per partita,
// Safe/Omega/tennis per riga, scalper per sessione con firma.
//
// FALSIFICAZIONE (`falsifica_w_c.sh`): comandi in parallelo, Mike una volta
// per gamba, guardia dei 400 ms tolta, gamba senza comando taciuta -> rossi.
// ============================================================================
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { CashOutGlobale, pianoChiusuraPartita, testoPiano, SCADENZA_ARMATURA_MS, type OperazionePerChiusura } from './CashOutGlobale';
import { ChiusuraRigaContext } from './BottoneChiudiRiga';
import { ATTESA_CONFERMA_USCITE_MS } from './InterruttoreUscite';
import type { RigaDaChiudere, StatoChiusuraRiga } from './chiudiRiga';
import { cashOutPartita, type GambaViva } from '@/lib/cashOutPartita';
import { PREZZO_VUOTO } from '@/lib/schedaAlMs';
import type { Bot } from '@/lib/controlRoom';

const NOW = Date.now();

function op(p: Partial<OperazionePerChiusura> & Pick<OperazionePerChiusura, 'bot' | 'id'>): OperazionePerChiusura {
    return { eventId: '35001', marketId: '1.35', modalita: 'live', stato: 'open', chiudeId: null, pnl: null, ...p };
}

// Follo: due gambe di Mike + una di Safe (live), la sessione dello scalper senza firma
const OPS: OperazionePerChiusura[] = [
    op({ bot: 'mike', id: 5085 }),
    op({ bot: 'mike', id: 5094, marketId: '1.45' }),
    op({ bot: 'safe', id: 9 }),
    op({ bot: 'scalper', id: 7, marketId: null, stato: 'running', firma: null }),
];

const GAMBE: GambaViva[] = [
    { id: 5085, bot: 'mike', modalita: 'live', marketId: '1.35', selectionId: 11, selezione: 'Under 3.5 Goals',
        lato: 'back', abbinato: 5, prezzoMedio: 2.4, aliquota: 0.05 },
    { id: 5094, bot: 'mike', modalita: 'live', marketId: '1.45', selectionId: 21, selezione: 'Under 4.5 Goals',
        lato: 'lay', abbinato: 6.32, prezzoMedio: 1.76, aliquota: 0.05 },
];
function risultato(etaMs = 300) {
    const libro: Record<string, { back: number; lay: number }> = {
        '1.35|11': { back: 2.46, lay: 2.56 }, '1.45|21': { back: 1.63, lay: 1.68 },
    };
    return cashOutPartita(GAMBE, {
        prezzo: (m, s) => {
            const p = libro[`${m}|${s}`];
            return p ? { ...PREZZO_VUOTO, ...p, backSize: 90, laySize: 90, fonte: 'canale', istanteMs: NOW - etaMs, statoMercato: 'OPEN' } : null;
        },
        nowMs: NOW,
    });
}

function contesto(stati: Record<string, Partial<StatoChiusuraRiga>> = {}) {
    const chiamate: RigaDaChiudere[] = [];
    const attese: (() => void)[] = [];
    const chiudi = vi.fn((riga: RigaDaChiudere) => {
        chiamate.push(riga);
        return new Promise<void>((ok) => { attese.push(ok); });
    });
    const stato = (bot: Bot, id: number): StatoChiusuraRiga | null => {
        const s = stati[`${bot}:${id}`];
        return s ? {
            bot, id, requestId: 1, faseRichiesta: 'inviata', richiestaChiusa: false, motivo: null,
            rigaCambiata: false, inviataMs: NOW, ...s,
        } : null;
    };
    return { chiudi, stato, chiamate, attese };
}

function monta(c: ReturnType<typeof contesto>, ops = OPS, r = risultato()) {
    return render(
        <ChiusuraRigaContext.Provider value={{ chiudi: c.chiudi, stato: c.stato }}>
            <CashOutGlobale risultato={r} operazioni={ops} />
        </ChiusuraRigaContext.Provider>,
    );
}

afterEach(() => { vi.useRealTimers(); });

describe('P16: il piano (quali comandi, in che ordine)', () => {
    it('Mike UNA volta per partita (copre le 2 gambe), Safe per riga, scalper senza firma dichiarato', () => {
        const p = pianoChiusuraPartita(OPS, 'live');
        expect(p.comandi.map((c) => [c.bot, c.riga.id, c.gambe])).toEqual([['mike', 5085, 2], ['safe', 9, 1]]);
        expect(p.senzaComando.map((s) => [s.bot, s.id])).toEqual([['scalper', 7]]);
        expect(testoPiano(p)).toBe('2 gambe di Mike, 1 di Safe; Scalper calcio #7 non ha un comando adesso: resta aperta '
            + '(firma della sessione assente (requested_at): non si ferma alla cieca)');
    });
    it('le righe PROVA non entrano nel piano LIVE (e viceversa); il tennis regolato non e\' una posizione', () => {
        const ops = [op({ bot: 'safe', id: 1, modalita: 'paper' }),
            op({ bot: 'tennis_pro', id: 2, marketId: '1.9', pnl: 3.1 }), op({ bot: 'omega', id: 3 })];
        expect(pianoChiusuraPartita(ops, 'live').comandi.map((c) => c.riga.id)).toEqual([3]);
        expect(pianoChiusuraPartita(ops, 'paper').comandi.map((c) => c.riga.id)).toEqual([1]);
    });
});

describe('P16: il pulsante nel riquadro', () => {
    it('il piano si legge PRIMA del clic, con la gamba senza comando', () => {
        monta(contesto());
        expect(screen.getByTestId('cr-cashout-globale-live-chiudi-tutte-piano').textContent)
            .toMatch(/^2 gambe di Mike, 1 di Safe; Scalper calcio #7 non ha un comando adesso: resta aperta/);
    });

    it('LIVE: il primo clic arma («Sono soldi veri: 2 comandi a 2 bot»), la conferma e\' inerte 400 ms', async () => {
        vi.useFakeTimers();
        const c = contesto();
        monta(c);
        fireEvent.click(screen.getByTestId('cr-cashout-globale-live-chiudi-tutte-avvia'));
        expect(c.chiudi).not.toHaveBeenCalled();
        expect(screen.getByTestId('cr-cashout-globale-live-chiudi-tutte-armato').textContent)
            .toBe('Sono soldi veri: 2 comandi a 2 bot (effetti: vedi il title). annulla');
        const conf = screen.getByTestId('cr-cashout-globale-live-chiudi-tutte-conferma') as HTMLButtonElement;
        expect(conf.disabled).toBe(true);
        fireEvent.click(conf);
        expect(c.chiudi).not.toHaveBeenCalled();
        await act(async () => { vi.advanceTimersByTime(ATTESA_CONFERMA_USCITE_MS + 50); });
        await act(async () => { fireEvent.click(screen.getByTestId('cr-cashout-globale-live-chiudi-tutte-conferma')); });
        expect(c.chiudi).toHaveBeenCalledTimes(1);
    });

    it('IN SEQUENZA: il secondo comando parte solo dopo l\'esito del primo; Mike una volta sola', async () => {
        vi.useFakeTimers();
        const c = contesto();
        monta(c);
        fireEvent.click(screen.getByTestId('cr-cashout-globale-live-chiudi-tutte-avvia'));
        await act(async () => { vi.advanceTimersByTime(ATTESA_CONFERMA_USCITE_MS + 50); });
        await act(async () => { fireEvent.click(screen.getByTestId('cr-cashout-globale-live-chiudi-tutte-conferma')); });
        expect(c.chiamate.map((r) => [r.bot, r.id])).toEqual([['mike', 5085]]);
        await act(async () => { c.attese[0](); });
        expect(c.chiamate.map((r) => [r.bot, r.id])).toEqual([['mike', 5085], ['safe', 9]]);
        await act(async () => { c.attese[1](); });
        expect(c.chiudi).toHaveBeenCalledTimes(2);
        // la riga passata e' quella del pulsante di riga: stessa identita', stessa modalita'
        expect(c.chiamate[0]).toMatchObject({ bot: 'mike', id: 5085, eventId: '35001', modalita: 'live', stato: 'open' });
    });

    it('riscontro per bot A SCHERMO: «Mike (partita, 2 gambe): presa in carico», «Safe #9: rifiutata: <motivo>»', async () => {
        const c = contesto({
            'mike:5085': { faseRichiesta: 'presa_in_carico' },
            'safe:9': { faseRichiesta: 'rifiutata', motivo: 'kind non valido', richiestaChiusa: true },
        });
        monta(c, OPS.map((o) => ({ ...o, modalita: 'paper' as const })),
            cashOutPartita(GAMBE.map((g) => ({ ...g, modalita: 'paper' as const })), {
                prezzo: () => ({ ...PREZZO_VUOTO, back: 2.46, lay: 2.56, backSize: 90, laySize: 90, fonte: 'canale', istanteMs: NOW, statoMercato: 'OPEN' }),
                nowMs: NOW,
            }));
        // PAPER: un clic, nessuna conferma
        fireEvent.click(screen.getByTestId('cr-cashout-globale-prova-chiudi-tutte-avvia'));
        expect(screen.queryByTestId('cr-cashout-globale-prova-chiudi-tutte-conferma')).toBeNull();
        await act(async () => { c.attese[0](); });
        await act(async () => { c.attese[1](); });
        expect(screen.getAllByTestId('cr-cashout-globale-prova-chiudi-tutte-esito').map((e) => e.textContent))
            .toEqual(['Mike (partita, 2 gambe): presa in carico', 'Safe #9: rifiutata: kind non valido']);
    });

    it('prezzi FERMI (oltre 20 s): il pulsante e\' spento e dice perche\'', () => {
        monta(contesto(), OPS, risultato(30_000));
        const b = screen.getByTestId('cr-cashout-globale-live-chiudi-tutte-avvia') as HTMLButtonElement;
        expect(b.disabled).toBe(true);
        expect(screen.getByTestId('cr-cashout-globale-live-chiudi-tutte-bloccato').textContent)
            .toBe('prezzi fermi da 30 s: non si chiude su prezzi vecchi');
    });

    it('R2-1: armato con prezzi freschi, se i prezzi diventano FERMI la conferma si spegne e dice perche', async () => {
        vi.useFakeTimers();
        const c = contesto();
        const r = monta(c);
        fireEvent.click(screen.getByTestId('cr-cashout-globale-live-chiudi-tutte-avvia'));
        await act(async () => { vi.advanceTimersByTime(ATTESA_CONFERMA_USCITE_MS + 50); });
        expect((screen.getByTestId('cr-cashout-globale-live-chiudi-tutte-conferma') as HTMLButtonElement).disabled).toBe(false);
        // il feed si ferma: stesso componente, prezzi di 30 s
        r.rerender(
            <ChiusuraRigaContext.Provider value={{ chiudi: c.chiudi, stato: c.stato }}>
                <CashOutGlobale risultato={risultato(30_000)} operazioni={OPS} />
            </ChiusuraRigaContext.Provider>,
        );
        // review incrociata (M1): l'armatura CADE: niente «Confermo», «avvia» spento col motivo
        expect(screen.queryByTestId('cr-cashout-globale-live-chiudi-tutte-conferma')).toBeNull();
        expect((screen.getByTestId('cr-cashout-globale-live-chiudi-tutte-avvia') as HTMLButtonElement).disabled).toBe(true);
        expect(c.chiudi).not.toHaveBeenCalled();
        expect(screen.getByTestId('cr-cashout-globale-live-chiudi-tutte-bloccato').textContent)
            .toBe('prezzi fermi da 30 s: non si chiude su prezzi vecchi');
    });

    it('M1: l’armatura scade da sola dopo SCADENZA_ARMATURA_MS; e cade se il piano cambia', async () => {
        vi.useFakeTimers();
        const c = contesto();
        const r = monta(c);
        fireEvent.click(screen.getByTestId('cr-cashout-globale-live-chiudi-tutte-avvia'));
        await act(async () => { vi.advanceTimersByTime(SCADENZA_ARMATURA_MS + 50); });
        expect(screen.queryByTestId('cr-cashout-globale-live-chiudi-tutte-conferma')).toBeNull();
        // riarmo, poi una gamba sparisce dal piano (si e' chiusa da sola): disarmo
        fireEvent.click(screen.getByTestId('cr-cashout-globale-live-chiudi-tutte-avvia'));
        await act(async () => { vi.advanceTimersByTime(ATTESA_CONFERMA_USCITE_MS + 50); });
        expect(screen.queryByTestId('cr-cashout-globale-live-chiudi-tutte-conferma')).not.toBeNull();
        r.rerender(
            <ChiusuraRigaContext.Provider value={{ chiudi: c.chiudi, stato: c.stato }}>
                <CashOutGlobale risultato={risultato()} operazioni={OPS.slice(0, OPS.length - 1)} />
            </ChiusuraRigaContext.Provider>,
        );
        expect(screen.queryByTestId('cr-cashout-globale-live-chiudi-tutte-conferma')).toBeNull();
        expect(c.chiudi).not.toHaveBeenCalled();
    });

    it('M2: due posizioni dello stesso bot TENNIS sulla stessa partita/mercato = UN comando (chiude la partita)', () => {
        const due: OperazionePerChiusura[] = [
            op({ bot: 'tennis_pro', id: 501, eventId: 'T1', marketId: '1.MO' }),
            op({ bot: 'tennis_pro', id: 502, eventId: 'T1', marketId: '1.MO' }),
        ];
        const p = pianoChiusuraPartita(due, 'live');
        const tennis = p.comandi.filter((x) => x.bot === 'tennis_pro');
        expect(tennis).toHaveLength(1);
        expect(tennis[0].gambe).toBe(2);
    });

    it('senza il contesto della Control Room (altre pagine) il pulsante non c\'e\'', () => {
        render(<CashOutGlobale risultato={risultato()} operazioni={OPS} />);
        expect(screen.queryByTestId('cr-cashout-globale-live-chiudi-tutte')).toBeNull();
    });
});
