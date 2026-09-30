// ============================================================================
// FasciaSoldiVeri.test.tsx - P3 (30/09): cosa legge il trader nella testata.
// Il campo `soldiVeri` e' costruito con le funzioni VERE (soldiVeri.ts) sui
// finti dei produttori veri (vedi soldiVeri.test.ts): nessun oggetto a mano
// piu' comodo del vero.
// ============================================================================
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { FasciaSoldiVeri, CHIAVE_SALDO_NASCOSTO } from './FasciaSoldiVeri';
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

    it('R_T: numero fresco: nessun avviso di stantio', () => {
        render(<FasciaSoldiVeri s={soldi()} />);
        expect(screen.queryByTestId('cr-rischio-bot-stantio')).toBeNull();
    });

    it('saldo nascosto con l\'occhio della card: nascosto anche qui', () => {
        window.localStorage.setItem(CHIAVE_SALDO_NASCOSTO, '1');
        render(<FasciaSoldiVeri s={soldi()} />);
        expect(screen.getByTestId('cr-esposizione-conto-valore').textContent).not.toMatch(/9,95/);
        expect(screen.getByTestId('cr-disponibile-conto').textContent).not.toMatch(/30,61/);
    });
});
