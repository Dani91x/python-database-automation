// ============================================================================
// MikeP6Blocco1.test.tsx - piano Mike 29/09, pacchetto P6 (app), blocco 1:
//   punto 3  - i testi delle uscite manuali dopo P1 (governa solo le perdite);
//   punto 4  - `event_loss_cap_pct` dichiarato NON ATTIVO, `reentry_max_goals`
//              di serie 2 e massimo 2 (specchio del config.py dell'altro
//              delegato, integrazione del coordinatore);
//   punto 5  - M8.13: come e' finito un ordine non abbinato (`meta.esito_ordine`).
// I finti hanno le chiavi VERE: righe di `mike_trades` come in
// MikeEventPnlTable.test.tsx, parametri come `mike_control.params`.
// ============================================================================
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MikeEventPnlTable } from './MikeEventPnlTable';
import {
    esitoOrdineMike, groupMikeTrades, mergeMikeParams, MIKE_ESITO_ORDINE_LABEL,
    MIKE_PARAM_DEFAULTS, MIKE_PARAM_FIELDS, type MikeTrade,
} from '@/lib/mike';
import { interruttoreDi, statoUscite, NOTA_USCITE_MIKE } from '@/lib/interruttori';
import { testoStatoUscite } from '@/components/controlroom/InterruttoreUscite';

let seq = 1000;
function riga(over: Partial<MikeTrade> = {}): MikeTrade {
    seq += 1;
    return {
        id: seq, event_id: 'E1', event_name: 'Roma v Lazio', strategy: 'under_entry',
        role: 'under_entry', cycle_no: 0, market_type: 'OVER_UNDER_35', market_id: '1.1',
        selection_id: 1222344, side: 'back', price: 1.5, size: 10, liability: 10,
        commission: 5, mode: 'paper', status: 'won', pnl: 0, bet_id: null,
        placed_at: '2026-09-29T10:00:00Z', day_placed_at: '2026-09-29T10:00:00Z',
        settled_at: null, signal_key: `k${seq}`, meta: {}, closes_trade_id: null,
        origin: 'auto', ...over,
    } as MikeTrade;
}

function campo(key: string) {
    const f = MIKE_PARAM_FIELDS.find((x) => x.key === key);
    if (!f) throw new Error(`campo ${key} assente`);
    return f;
}

describe('punto 5 (M8.13) - esito di un ordine non abbinato', () => {
    it('i cinque esiti del bot hanno la loro frase', () => {
        const attese: Record<string, string> = {
            ritirato_da_noi: 'ritirato da Mike',
            rifiutato: 'rifiutato da Betfair',
            non_abbinato_fok: 'non abbinato: tutto o niente',
            cancellato_da_betfair: 'cancellato da Betfair',
            fermato_da_noi: 'fermato da un nostro blocco',
        };
        expect(MIKE_ESITO_ORDINE_LABEL).toEqual(attese);
        for (const [k, v] of Object.entries(attese)) {
            expect(esitoOrdineMike({ status: 'error', meta: { esito_ordine: k } })).toBe(v);
        }
    });

    it('chiave assente, valore ignoto o riga non in errore: nessuna frase (resta il testo di oggi)', () => {
        expect(esitoOrdineMike({ status: 'error', meta: {} })).toBeNull();
        expect(esitoOrdineMike({ status: 'error', meta: null })).toBeNull();
        expect(esitoOrdineMike({ status: 'error', meta: { esito_ordine: 'boh' } })).toBeNull();
        expect(esitoOrdineMike({ status: 'error', meta: { esito_ordine: 3 } })).toBeNull();
        // lo stato resta `error` per contratto: su un'altra riga la chiave non conta
        expect(esitoOrdineMike({ status: 'won', meta: { esito_ordine: 'rifiutato' } })).toBeNull();
    });

    it('nella tabella delle operazioni l’ordine in errore dice come e’ finito', () => {
        const apre = riga({ status: 'lost', pnl: -10 });
        const rit = riga({
            role: 'under_green', side: 'lay', status: 'error', pnl: null, closes_trade_id: apre.id,
            placed_at: '2026-09-29T10:05:00Z', meta: { esito_ordine: 'ritirato_da_noi' },
        });
        const vecchia = riga({
            role: 'under_close', side: 'lay', status: 'error', pnl: null, closes_trade_id: apre.id,
            placed_at: '2026-09-29T10:06:00Z', meta: {},
        });
        render(<MikeEventPnlTable gruppi={groupMikeTrades([apre, rit, vecchia])} titolo="Operazioni" vuoto="-" />);
        fireEvent.click(screen.getByTestId('apri-E1'));
        expect(screen.getByTestId(`gamba-${rit.id}`)).toHaveTextContent('ritirato da Mike');
        expect(screen.getByTestId(`gamba-${rit.id}`)).not.toHaveTextContent('ERRORE');
        // riga vecchia senza la chiave: il testo di sempre
        expect(screen.getByTestId(`gamba-${vecchia.id}`)).toHaveTextContent('ERRORE');
    });
});

describe('punto 4 - parametri dopo le decisioni del 29/09', () => {
    it('event_loss_cap_pct resta in elenco ma si dichiara NON ATTIVO, con la spiegazione', () => {
        const f = campo('event_loss_cap_pct');
        expect(f.label).toContain('NON ATTIVO');
        expect(f.hint).toContain('NON ATTIVO');
        expect(f.hint).toContain('tetto tolto');
        // limiti e valore di serie invariati (contratto con config.py)
        expect(f.kind === 'number' ? [f.min, f.max] : null).toEqual([0, 500]);
        expect(MIKE_PARAM_DEFAULTS.event_loss_cap_pct).toBe(100);
    });

    it('reentry_max_goals: di serie 2, massimo 2 (1 o 2 gol)', () => {
        const f = campo('reentry_max_goals');
        expect(f.kind === 'number' ? [f.min, f.max] : null).toEqual([0, 2]);
        expect(MIKE_PARAM_DEFAULTS.reentry_max_goals).toBe(2);
        // un 2 salvato non viene piu' riportato a 1 dal pannello
        expect(mergeMikeParams({ reentry_max_goals: 2 }).reentry_max_goals).toBe(2);
        expect(mergeMikeParams({ reentry_max_goals: 5 }).reentry_max_goals).toBe(2);
        expect(campo('reentry_enabled').hint).toContain('1 o 2 gol');
    });
});

describe('punto 3 - le uscite manuali di Mike dopo P1', () => {
    it('il pannello dice che l’interruttore governa solo le uscite in perdita', () => {
        const h = campo('uscite_automatiche').hint;
        expect(h).toMatch(/^governa solo le uscite in PERDITA/);
        expect(h).toContain('le esegue Mike da solo in ogni caso');
        expect(h).not.toContain('cap perdita');
    });

    it('la riga di Mike in Control Room porta la stessa frase accanto allo stato', () => {
        const st = statoUscite(interruttoreDi('mike'), { uscite_automatiche: false });
        expect(st?.nota).toBe(NOTA_USCITE_MIKE);
        expect(testoStatoUscite(st!)).toBe(
            'MANUALI, approvi tu (governa solo le uscite in perdita; le uscite in profitto le esegue Mike)');
        // gli altri bot restano senza nota
        expect(statoUscite(interruttoreDi('omega'), { uscite_protezione: 'avvisa_e_proponi' })?.nota).toBeUndefined();
    });
});
