// ============================================================================
// B2GlossarioAuditCR.test.tsx - 30/09 (blocco B2 dell'audit di veridicita'
// della UI, `AUDIT_2026-09-30/AUDIT_UI_VERIDICITA.md`): i testi della Control
// Room che dicevano una cosa diversa da quella che fa il codice.
//
//   A9  cash out con un prezzo mancante: il netto del servizio ESCLUDE la linea
//       senza prezzo (`engine.cashout_value`, `complete=False`): nessuna cifra.
//   M9  «ciclo 0 · 0 chiusi»: il ciclo si numera come nella pagina di Mike.
//   A3  linea 4,5: c'e' anche l'Under 4,5 (la banca della copertura di serie e
//       il re-ingresso), e l'Over 4,5 non si chiama piu' «la copertura».
//   M10 una parola sola: «Liability», mai «responsabilita'».
//   M11 ogni proposta d'uscita di Mike e' un'uscita che puo' chiudere IN
//       PERDITA (`engine.gate_uscite` / `uscita_in_perdita`): titolo e rosso.
//   M12 «chiudendo ora X»: X e' il cash out di TUTTA la partita.
//   A12 per Mike l'interruttore governa SOLO le uscite in perdita: il tooltip
//       non deve dire «in profitto e in perdita». Gli altri bot: identico.
//
// Finti con le chiavi VERE: `MikeEvent` (lib/mike.ts), `live.cashout` =
// `MikeCashout`, `live.books` con chiavi «MERCATO|SELEZIONE» come le scrive
// `service.py` (`f"{m}|{s}"`), la proposta come la scrive `engine.gate_uscite`,
// `StatoUscite` di lib/interruttori.ts.
// ============================================================================
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { MikeEvent } from '@/lib/mike';
import { statoUscite, interruttoreDi, NOTA_USCITE_MIKE, type StatoUscite } from '@/lib/interruttori';
import { SchedaMike } from './SchedaMike';
import { PropostaUscitaMike } from './PropostaUscitaMike';
import { InterruttoreUscite } from './InterruttoreUscite';

const ORA_S = Math.floor(Date.now() / 1000);

function ev(over: Partial<MikeEvent> = {}, live: Record<string, unknown> = {}): MikeEvent {
    return {
        event_id: 'E1', fixture_id: null, event_name: 'Roma v Lazio', competition: 'Serie A', league_id: null,
        ko_at: new Date().toISOString(), mode: 'live', markets: {}, state: 'LIVE_COVERED',
        cycle_no: 0, entry_price_initial: 1.5, dossier: null,
        live: {
            feed_age_s: 2,
            published_ts: ORA_S,
            liability: 5,
            books: {
                'OU35|UNDER': { best_back: 1.30, best_lay: 1.31, back_size: 100, lay_size: 80, status: 'OPEN' },
                'OU45|OVER': { best_back: 12.0, best_lay: 12.5, back_size: 10, lay_size: 8, status: 'OPEN' },
                'OU45|UNDER': { best_back: 1.08, best_lay: 1.09, back_size: 300, lay_size: 250, status: 'OPEN' },
            },
            ...live,
        } as unknown as MikeEvent['live'],
        positions: [], ctx: null, skipped: false, settled_pnl: null, updated_at: new Date().toISOString(),
        ...over,
    };
}

function cashout(over: Record<string, unknown> = {}) {
    return { net: -0.84, gross: -0.84, base: 9.8, complete: true, pct: -8.6, target_pct: 5, ...over };
}

function proposta(over: Record<string, unknown> = {}) {
    return {
        chiave: 'chiusura|c0', categoria: 'chiusura', ciclo: 0, stato: 'LIVE_COVERED',
        stato_voluto: 'LIVE_CLOSING', motivo: 'uscita a modello', close_reason: 'loss_model',
        ordini: [
            { ruolo: 'under_close', mercato: 'OU35', selezione: 'UNDER', lato: 'lay', prezzo: 1.31, size: 22.9 },
        ],
        bloccabile: -1.31, urgente: true, minuto: 60, gol: 2,
        decided_at: ORA_S - 3, proposed_at: ORA_S - 3,
        sostanza: ['chiusura|c0', [['under_close', 'lay']], 'loss_model'],
        ...over,
    };
}

/** tutti i testi che il trader LEGGE: contenuto e tooltip */
function testiVisibili(el: HTMLElement): string {
    const titoli = [...el.querySelectorAll('[title]')].map((n) => n.getAttribute('title') ?? '');
    return `${el.textContent ?? ''}\n${titoli.join('\n')}`;
}

// ------------------------------------------------------------------ A9
describe('A9 - cash out con una linea senza prezzo: nessuna cifra', () => {
    it('complete=false: «non calcolabile (manca il prezzo di una linea)», nessun euro', () => {
        render(<SchedaMike ev={ev({}, { cashout: cashout({ complete: false, net: 1.23 }) })} />);
        const voce = screen.getByTestId('cr-mike-cashout');
        expect(voce.textContent).toContain('non calcolabile (manca il prezzo di una linea)');
        expect(voce.textContent).not.toContain('1,23');
        expect(voce.textContent).not.toContain('€');
        expect(voce.textContent).not.toContain('parziale');
        // il vecchio aggancio resta
        expect(screen.getByTestId('cr-mike-cashout-parziale')).toBeTruthy();
    });

    it('complete=true: la cifra del servizio, col suo segno', () => {
        render(<SchedaMike ev={ev({}, { cashout: cashout() })} />);
        const voce = screen.getByTestId('cr-mike-cashout');
        expect(voce.textContent).toContain('−0,84 €');
        expect(screen.queryByTestId('cr-mike-cashout-parziale')).toBeNull();
    });
});

// ------------------------------------------------------------------ M9
describe('M9 - il ciclo si numera come nella pagina di Mike', () => {
    it('cycle_no 0 in gioco = «ciclo 1» (mai «ciclo 0»)', () => {
        render(<SchedaMike ev={ev({ cycle_no: 0 }, { cicli_chiusi: 0 })} />);
        const voce = screen.getByTestId('cr-mike-cicli');
        expect(voce.textContent).toMatch(/^ciclo\s*1 · 0 chiusi$/);
    });

    it('cycle_no 2 in gioco = «ciclo 3 · 2 chiusi»', () => {
        render(<SchedaMike ev={ev({ cycle_no: 2 }, { cicli_chiusi: 2 })} />);
        expect(screen.getByTestId('cr-mike-cicli').textContent).toMatch(/^ciclo\s*3 · 2 chiusi$/);
    });

    it('partita chiusa: i cicli USATI, nessun ciclo «in corso»', () => {
        render(<SchedaMike ev={ev({ cycle_no: 3, state: 'SETTLED', settled_pnl: 1 }, { cicli_chiusi: 3 })} />);
        expect(screen.getByTestId('cr-mike-cicli').textContent).toMatch(/^ciclo\s*3 usati$/);
    });
});

// ------------------------------------------------------------------ A3
describe('A3 - linea 4,5: Under 4,5 presente, Over 4,5 senza «(la copertura)»', () => {
    it('mostra l’Under 4.5 dai book veri («OU45|UNDER»)', () => {
        render(<SchedaMike ev={ev()} />);
        const u45 = screen.getByTestId('cr-mike-u45');
        expect(u45.textContent).toContain('Under 4.5');
        expect(u45.textContent).toContain('1,08');
        expect(u45.textContent).toContain('1,09');
    });

    it('nessun title promette che l’Over 4.5 sia la copertura', () => {
        render(<SchedaMike ev={ev()} />);
        const o45 = screen.getByTestId('cr-mike-o45');
        expect(o45.getAttribute('title')).not.toContain('(la copertura)');
        const p4 = screen.getByTestId('cr-mike-p4-mercato').getAttribute('title') ?? '';
        expect(p4).toContain('perdono l’Under 3,5 e la copertura');
        expect(p4).not.toContain('sia Over 4.5');
        // la formula resta quella
        expect(p4).toContain('P(Over 3.5) − P(Over 4.5)');
    });

    it('se la partita ha una gamba di copertura, il title dice QUALE (banca Under 4.5)', () => {
        const cop = {
            role: 'over_cover', market: 'OU45', selection: 'UNDER', side: 'lay', price: 1.09, size: 6.32,
            matched: 6.32, avg_price: 1.09, ref: 'r1', status: 'open', placed_at: ORA_S, persistence: 'LAPSE',
            cycle_no: 0, final: false, archived: false,
        } as MikeEvent['positions'][number];
        render(<SchedaMike ev={ev({ positions: [cop] })} />);
        expect(screen.getByTestId('cr-mike-u45').getAttribute('title')).toContain('Copertura: banca Under 4.5');
    });
});

// ------------------------------------------------------------------ M10
describe('M10 - una parola sola: Liability', () => {
    it('SchedaMike: «Liability aperta», mai «responsabilità» in testo o tooltip', () => {
        const { container } = render(<SchedaMike ev={ev({}, { cashout: cashout() })} />);
        const voce = screen.getByTestId('cr-mike-liability');
        expect(voce.textContent).toContain('Liability aperta');
        expect(voce.textContent).toContain('5,00 €');
        expect(testiVisibili(container)).not.toMatch(/responsabilit/i);
    });
});

// ------------------------------------------------------------------ M11, M12
describe('M11/M12 - proposta d’uscita di Mike', () => {
    it('in perdita (loss_*): titolo «IN PERDITA», riquadro rosso', () => {
        render(<PropostaUscitaMike ev={ev({ ctx: { uscita_proposta: proposta() } })} />);
        const t = screen.getByTestId('cr-mike-proposta-titolo').textContent ?? '';
        expect(t).toContain('IN PERDITA');
        expect(screen.getByTestId('cr-mike-proposta').className).toMatch(/border-red-500\/40/);
    });

    it('non urgente (chiusura a tempo del re-ingresso): comunque «IN PERDITA» e rosso', () => {
        render(<PropostaUscitaMike ev={ev({ ctx: { uscita_proposta: proposta({
            urgente: false, close_reason: 'reentry_time', categoria: 'reentry_green',
            chiave: 'reentry_green|c0' }) } })} />);
        const t = screen.getByTestId('cr-mike-proposta-titolo').textContent ?? '';
        expect(t).toContain('IN PERDITA');
        expect(t).toContain('uscita del re-ingresso');
        const box = screen.getByTestId('cr-mike-proposta');
        expect(box.className).toMatch(/border-red-500\/40/);
        expect(box.className).not.toMatch(/amber/);
    });

    it('la cifra «chiudendo ora» dice che e’ TUTTA la partita', () => {
        render(<PropostaUscitaMike ev={ev({ ctx: { uscita_proposta: proposta() } }, { cashout: cashout() })} />);
        const numeri = screen.getByTestId('cr-mike-proposta-numeri').textContent ?? '';
        expect(numeri).toMatch(/^chiudendo tutta la partita ora −0,84 €/);
        expect(screen.getByTestId('cr-mike-proposta-cifra').textContent).toBe('−0,84 €');
    });
});

// ------------------------------------------------------------------ A12
const TITOLO_MANUALI_DI_SEMPRE = 'le uscite della strategia (in profitto e in perdita) diventano PROPOSTE nella scheda: le approvi tu. Le protezioni restano automatiche';
const TITOLO_CONFERMA_DI_SEMPRE = 'confermi? da qui il bot chiude da solo secondo la sua strategia, in profitto e in perdita';

describe('A12 - tooltip dell’interruttore delle uscite', () => {
    it('Mike (stato del servizio): il tooltip parla SOLO delle uscite in perdita', () => {
        const st = statoUscite(interruttoreDi('mike'), { uscite_automatiche: true }) as StatoUscite;
        expect(st.nota).toBe(NOTA_USCITE_MIKE);
        expect(st.soloUsciteInPerdita).toBe(true);
        const cambia = vi.fn();
        const { unmount } = render(<InterruttoreUscite id="mike" uscite={st} cambia={cambia} />);
        const manuali = screen.getByTestId('cr-uscite-cambia-mike').getAttribute('title') ?? '';
        expect(manuali).toContain('PERDITA');
        expect(manuali).not.toContain('in profitto e in perdita');
        expect(manuali).toMatch(/profitto .*le esegue sempre il bot/);
        unmount();

        const spente = statoUscite(interruttoreDi('mike'), { uscite_automatiche: false }) as StatoUscite;
        render(<InterruttoreUscite id="mike" uscite={spente} cambia={cambia} />);
        fireEvent.click(screen.getByTestId('cr-uscite-cambia-mike'));
        const conferma = screen.getByTestId('cr-uscite-conferma-mike').getAttribute('title') ?? '';
        expect(conferma).toContain('PERDITA');
        expect(conferma).not.toContain('in profitto e in perdita');
    });

    it('gli altri bot: testo IDENTICO a prima', () => {
        for (const id of ['omega', 'safe-base', 'scalper'] as const) {
            const params = id === 'omega' ? { uscite_protezione: 'automatico' }
                : id === 'scalper' ? { uscite_automatiche: true }
                    : { uscite_automatiche: { base: true } };
            const st = statoUscite(interruttoreDi(id), params) as StatoUscite;
            expect(st.soloUsciteInPerdita).toBeUndefined();
            const { unmount } = render(<InterruttoreUscite id={id} uscite={st} cambia={vi.fn()} />);
            expect(screen.getByTestId(`cr-uscite-cambia-${id}`).getAttribute('title')).toBe(TITOLO_MANUALI_DI_SEMPRE);
            unmount();
        }
        render(<InterruttoreUscite id="omega" uscite={{ automatiche: false }} cambia={vi.fn()} />);
        fireEvent.click(screen.getByTestId('cr-uscite-cambia-omega'));
        expect(screen.getByTestId('cr-uscite-conferma-omega').getAttribute('title')).toBe(TITOLO_CONFERMA_DI_SEMPRE);
    });
});
