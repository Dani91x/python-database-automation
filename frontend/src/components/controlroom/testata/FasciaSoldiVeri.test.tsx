// ============================================================================
// FasciaSoldiVeri.test.tsx - P3 (30/09): cosa legge il trader nella testata.
// Il campo `soldiVeri` e' costruito con le funzioni VERE (soldiVeri.ts) sui
// finti dei produttori veri (vedi soldiVeri.test.ts): nessun oggetto a mano
// piu' comodo del vero.
// ============================================================================
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { FasciaSoldiVeri, CHIAVE_SALDO_NASCOSTO, SALDO_NASCOSTO } from './FasciaSoldiVeri';
import {
    contoAdesso, rischioBotLive, scartoContoBot, partiteConPosizione, type SoldiVeriTestata,
} from './soldiVeri';

const NOW = Date.parse('2026-09-30T14:05:00Z');
const RIGA = { available: 30.61, exposure: -9.95, updated_at: '2026-09-30T14:04:57+00:00' };
const APERTE = [
    { bot: 'mike' as const, modalita: 'live' as const, eventId: 'Follo' },
    { bot: 'mike' as const, modalita: 'live' as const, eventId: 'Vsetin' },
    { bot: 'mike' as const, modalita: 'live' as const, eventId: 'Farul' },
    { bot: 'safe' as const, modalita: 'paper' as const, eventId: 'Z' },
];
const STATI = {
    omega: { aggregates: { mode: 'paper', open_liability: 0 }, aggregates_by_mode: { paper: { open_liability: 0 }, live: { open_liability: 0 } } },
    safe: { aggregates: { mode: null, open_liability: 0 } },
    mike: { aggregates: { mode: 'live', open_liability: 16.22, liability_stale: false } },
};

function soldi(over: { riga?: typeof RIGA | null; letti?: boolean; stati?: typeof STATI } = {}): SoldiVeriTestata {
    const conto = contoAdesso({ riga: over.riga === undefined ? RIGA : over.riga, canale: null, etaRunnerS: 4, nowMs: NOW });
    const letti = over.letti ?? true;
    const rischioBot = rischioBotLive({ letti, stati: over.stati ?? STATI, aperte: APERTE });
    return {
        conto, rischioBot, etaBotS: 7,
        scarto: scartoContoBot(conto.esposizione, rischioBot),
        partite: letti ? partiteConPosizione(APERTE) : null,
        programmaScanner: 28,
    };
}

beforeEach(() => {
    cleanup();
    try { window.localStorage.removeItem(CHIAVE_SALDO_NASCOSTO); } catch { /* niente */ }
});

describe('FasciaSoldiVeri - i numeri di oggi', () => {
    it('esposizione del CONTO 9,95 col marchio CONTO BETFAIR e l\'eta\'; rischio dei bot 16,22 col marchio BOT', () => {
        render(<FasciaSoldiVeri s={soldi()} />);
        expect(screen.getByTestId('cr-esposizione-conto-valore').textContent).toMatch(/9,95/);
        const m = screen.getByTestId('cr-esposizione-conto-marchio');
        expect(m.getAttribute('data-fonte')).toBe('conto');
        expect(m.textContent).toMatch(/CONTO BETFAIR/);
        expect(m.textContent).toMatch(/3 s fa/);
        expect(screen.getByTestId('cr-rischio-bot-valore').textContent).toMatch(/16,22/);
        expect(screen.getByTestId('cr-rischio-bot-marchio').getAttribute('data-fonte')).toBe('bot');
        expect(screen.getByTestId('cr-disponibile-conto').textContent).toMatch(/30,61/);
    });

    it('conto e bot non tornano: lo dice in ambra con la differenza (6,27), marchio STIMA', () => {
        render(<FasciaSoldiVeri s={soldi()} />);
        const el = screen.getByTestId('cr-scarto-conto-bot');
        expect(el.textContent).toMatch(/NON TORNANO/);
        expect(el.textContent).toMatch(/6,27/);
        expect(el.textContent).toMatch(/il conto rischia meno dei bot/);
        expect(screen.getByTestId('cr-scarto-marchio').getAttribute('data-fonte')).toBe('pagina');
    });

    it('la somma LORDA per riga (39,15 / 37,04) non compare', () => {
        const { container } = render(<FasciaSoldiVeri s={soldi()} />);
        expect(container.textContent).not.toMatch(/39,15|37,04/);
    });

    it('partite con posizione LIVE (3), in prova a parte, programma dello scanner (28) etichettato', () => {
        render(<FasciaSoldiVeri s={soldi()} />);
        const el = screen.getByTestId('cr-partite-posizione');
        expect(el.textContent).toMatch(/3 partite/);
        expect(el.textContent).toMatch(/in prova 1/);
        expect(el.textContent).toMatch(/programma scanner 28/);
        expect(el.textContent).not.toMatch(/3 \/ 28/);
    });
});

describe('FasciaSoldiVeri - dati mancanti: mai una cifra inventata', () => {
    it('conto NON letto: nessuna cifra, "conto non letto", niente scarto, niente disponibile', () => {
        render(<FasciaSoldiVeri s={soldi({ riga: null })} />);
        const el = screen.getByTestId('cr-esposizione-conto');
        expect(screen.getByTestId('cr-esposizione-conto-valore').textContent).toBe('\u2014');
        expect(el.textContent).toMatch(/conto non letto/);
        expect(el.textContent).not.toMatch(/0,00/);
        expect(screen.queryByTestId('cr-scarto-conto-bot')).toBeNull();
        expect(screen.queryByTestId('cr-disponibile-conto')).toBeNull();
    });

    it('campo assente dal modello di vista (finto di prima): tutto "non letto", nessuna cifra', () => {
        const { container } = render(<FasciaSoldiVeri s={undefined} />);
        expect(container.textContent).toMatch(/conto non letto/);
        expect(container.textContent).not.toMatch(/\d,\d\d/);
    });

    it('posizioni non ancora lette: rischio dei bot "-" e partite "-"', () => {
        render(<FasciaSoldiVeri s={soldi({ letti: false })} />);
        expect(screen.getByTestId('cr-rischio-bot-valore').textContent).toBe('\u2014');
        expect(screen.getByTestId('cr-rischio-bot').textContent).toMatch(/posizioni non ancora lette/);
        expect(screen.getByTestId('cr-partite-posizione').textContent).toMatch(/posizioni non ancora lette/);
        expect(screen.getByTestId('cr-partite-posizione').textContent).not.toMatch(/\d+ partit/);
    });

    it('un bot con posizioni LIVE che non dichiara il rischio live: stima PARZIALE, nomina il bot, nessuno scarto', () => {
        render(<FasciaSoldiVeri s={soldi({ stati: { ...STATI, mike: { aggregates: { mode: 'paper', open_liability: 30, liability_stale: false } } } })} />);
        expect(screen.getByTestId('cr-rischio-bot-nota').textContent).toMatch(/parziale: manca Mike/);
        expect(screen.queryByTestId('cr-scarto-conto-bot')).toBeNull();
    });

    it('R_T: numero del bot stantio (liability_stale del servizio): detto A SCHERMO in ambra, non solo nel title', () => {
        render(<FasciaSoldiVeri s={soldi({ stati: { ...STATI, mike: { aggregates: { mode: 'live', open_liability: 16.22, liability_stale: true } } } })} />);
        const el = screen.getByTestId('cr-rischio-bot-stantio');
        expect(el.textContent).toMatch(/dato del bot non aggiornato \(Mike\)/);
        expect(el.className).toMatch(/amber/);
    });

    it('W_T/P14: partite con ordini fuori dai bot, coi nomi, in ambra; non letti = lo dice', () => {
        render(<FasciaSoldiVeri s={{ ...soldi(), ordiniFuori: { letto: true, n: 1, nomi: ['FC Vsetin v Bohemians'], senzaPartita: 0, motivo: null } }} />);
        const el = screen.getByTestId('cr-ordini-fuori-bot');
        expect(el.textContent).toMatch(/partite con ordini fuori dai bot: 1 \(FC Vsetin v Bohemians\)/);
        expect(el.innerHTML).toMatch(/amber/);
        cleanup();
        render(<FasciaSoldiVeri s={{ ...soldi(), ordiniFuori: { letto: false, n: 0, nomi: [], senzaPartita: 0, motivo: 'RPC non disponibile' } }} />);
        expect(screen.getByTestId('cr-ordini-fuori-bot').textContent).toMatch(/ordini del conto: non letti \(RPC non disponibile\)/);
        expect(screen.getByTestId('cr-ordini-fuori-bot').textContent).not.toMatch(/: 0/);
    });

    it('R_T: numero fresco: nessun avviso di stantio', () => {
        render(<FasciaSoldiVeri s={soldi()} />);
        expect(screen.queryByTestId('cr-rischio-bot-stantio')).toBeNull();
    });

    // 01/10 - CAMBIATO PERCHE' CAMBIA L'ORDINE: prima la preferenza della card
    // nascondeva anche l'esposizione; ora l'occhio nasconde SOLO il saldo
    it('preferenza "nascosto" gia\' salvata (anche dalla card di prima): saldo nascosto, ESPOSIZIONE visibile', () => {
        window.localStorage.setItem(CHIAVE_SALDO_NASCOSTO, '1');
        render(<FasciaSoldiVeri s={soldi()} />);
        expect(screen.getByTestId('cr-esposizione-conto-valore').textContent).toMatch(/9,95/);
        expect(screen.getByTestId('cr-disponibile-conto').textContent).not.toMatch(/30,61/);
        expect(screen.getByTestId('cr-disponibile-conto-valore').textContent).toBe(SALDO_NASCOSTO);
    });
});

describe('01/10 - l\'occhio del saldo in testata', () => {
    it('default (nessuna preferenza): saldo VISIBILE', () => {
        render(<FasciaSoldiVeri s={soldi()} />);
        expect(screen.getByTestId('cr-disponibile-conto-valore').textContent).toMatch(/30,61/);
        expect(screen.getByTestId('cr-saldo-occhio').getAttribute('aria-pressed')).toBe('false');
    });

    it('clic sull\'occhio: nasconde SOLO la cifra del saldo ("••••"), esposizione e rischio restano; la preferenza si salva', () => {
        render(<FasciaSoldiVeri s={soldi()} />);
        fireEvent.click(screen.getByTestId('cr-saldo-occhio'));
        const v = screen.getByTestId('cr-disponibile-conto-valore');
        expect(v.textContent).toBe('••••');
        expect(v.getAttribute('title')).toBe('saldo nascosto: clicca per mostrare');
        expect(screen.getByTestId('cr-esposizione-conto-valore').textContent).toMatch(/9,95/);
        expect(screen.getByTestId('cr-rischio-bot-valore').textContent).toMatch(/16,22/);
        expect(window.localStorage.getItem(CHIAVE_SALDO_NASCOSTO)).toBe('1');
    });

    it('persistenza: una nuova testata (ricarica della pagina) lo ritrova nascosto; clic sulla cifra nascosta lo mostra e salva', () => {
        const primo = render(<FasciaSoldiVeri s={soldi()} />);
        fireEvent.click(screen.getByTestId('cr-saldo-occhio'));
        primo.unmount();
        render(<FasciaSoldiVeri s={soldi()} />);
        expect(screen.getByTestId('cr-disponibile-conto-valore').textContent).toBe(SALDO_NASCOSTO);
        fireEvent.click(screen.getByTestId('cr-disponibile-conto-valore'));
        expect(screen.getByTestId('cr-disponibile-conto-valore').textContent).toMatch(/30,61/);
        expect(window.localStorage.getItem(CHIAVE_SALDO_NASCOSTO)).toBe('0');
    });

    it('localStorage che lancia (sito bloccato): nessun crash, saldo visibile, l\'occhio funziona per la sessione', () => {
        const get = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('bloccato'); });
        const set = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('bloccato'); });
        try {
            render(<FasciaSoldiVeri s={soldi()} />);
            expect(screen.getByTestId('cr-disponibile-conto-valore').textContent).toMatch(/30,61/);
            fireEvent.click(screen.getByTestId('cr-saldo-occhio'));
            expect(screen.getByTestId('cr-disponibile-conto-valore').textContent).toBe(SALDO_NASCOSTO);
        } finally {
            get.mockRestore();
            set.mockRestore();
        }
    });
});
