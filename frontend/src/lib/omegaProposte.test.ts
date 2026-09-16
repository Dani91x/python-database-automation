// ============================================================================
// omegaProposte.test.ts — LE USCITE DI OMEGA DIVENTANO PROPOSTE.
//
// Il finto parla come il VERO: i `motivo_codice` sono i SEI esiti esatti di
// `Betfair/omega/omega_v3.proposta_uscita` e i campi del payload sono quelli
// elencati nella migrazione `omega_proposte_uscita_2026-09-16.sql` §1.
//
// FALSIFICAZIONE (verificata: i test diventano rossi):
//   · un motivo senza etichetta italiana (torna la chiave con gli underscore) → rosso;
//   · «Chiudi ora» approvabile su una proposta che il servizio NON propone → rosso;
//   · l'esito `{ok:false}` della RPC scartato invece che rilanciato → rosso;
//   · l'ordinamento che mette in fondo quella che conviene chiudere → rosso.
// ============================================================================
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/integrations/supabase/client', () => ({
    supabase: { rpc: vi.fn(), from: vi.fn(), channel: vi.fn(), removeChannel: vi.fn() },
}));

import { supabase } from '@/integrations/supabase/client';
import {
    motivoUscitaOmegaLabel, motivoNonApprovabileOmega, ordinaProposteOmega,
    fetchProposteOmega, approvaPropostaOmega, ignoraPropostaOmega,
    type PropostaUscitaOmega, type PropostaUscitaOmegaPayload,
} from './omegaProposte';

const rpc = vi.mocked(supabase.rpc);
beforeEach(() => { rpc.mockReset(); });

/** payload con le chiavi ESATTE della migrazione */
function payload(over: Partial<PropostaUscitaOmegaPayload> = {}): PropostaUscitaOmegaPayload {
    return {
        trade_id: 4821, event_id: '35760084', event_name: 'Trinec v Mlada Boleslav',
        market_id: '1.245', market_type: 'CORRECT_SCORE', selection_id: 77,
        selection_name: '0 - 2', side: 'back', entry_side: 'lay', entry_price: 65, size: 1,
        price_at_decision: 31, size_available_at_decision: 12.5,
        motivo_codice: 'blocca_il_profitto', profitto_bloccabile: 0.94,
        back_price: 31, back_size: 2.1, ev_tenere: 0.42, p_evento: 0.0123,
        meglio_aspettare: false, bloccabile_max_atteso: 0.88, minuto_del_massimo: 72,
        minute: 38, score: '0-1', mode: 'paper',
        decided_at: '2026-09-16T21:00:00Z', proposed_at: '2026-09-16T21:00:30Z',
        ...over,
    };
}

function proposta(id: number, over: Partial<PropostaUscitaOmegaPayload> = {},
    created = '2026-09-16T21:00:00Z'): PropostaUscitaOmega {
    return { id, kind: 'cashout', payload: payload(over), created_at: created, updated_at: null };
}

describe('i SEI motivi di omega_v3, in italiano', () => {
    const attesi = ['blocca_il_profitto', 'tenere_vale_di_piu', 'aspettare_vale_di_piu',
        'bloccabile_non_positivo', 'controparte_insufficiente', 'nessun_prezzo_di_back'];

    it('nessuno cade nel traduttore parola per parola', () => {
        for (const k of attesi) {
            const l = motivoUscitaOmegaLabel(k);
            expect(l, `motivo senza etichetta: ${k}`).toBeTruthy();
            expect(l, `etichetta = chiave: ${k}`).not.toBe(k.replace(/_/g, ' '));
        }
    });

    it('un motivo sconosciuto non arriva con gli underscore', () => {
        expect(motivoUscitaOmegaLabel('motivo_mai_visto')).toBe('motivo mai visto');
    });

    it('assente = niente da scrivere', () => {
        expect(motivoUscitaOmegaLabel(null)).toBeNull();
    });
});

describe('quando si puo approvare — fail-closed', () => {
    it('la proposta vera del servizio e approvabile', () => {
        expect(motivoNonApprovabileOmega(payload())).toBeNull();
    });

    it('il servizio NON propone: il bottone si spegne e lo dice', () => {
        const m = motivoNonApprovabileOmega(payload({ motivo_codice: 'tenere_vale_di_piu' }));
        expect(m).toMatch(/non propone di chiudere/);
        expect(m).toMatch(/tenere vale di più/i);
    });

    it('senza prezzo di back non si piazza al buio', () => {
        expect(motivoNonApprovabileOmega(payload({ back_price: null }))).toMatch(/non si piazza al buio/);
        expect(motivoNonApprovabileOmega(payload({ back_price: 1 }))).toMatch(/non si piazza al buio/);
    });

    it('senza importo di chiusura non si piazza al buio', () => {
        expect(motivoNonApprovabileOmega(payload({ back_size: 0 }))).toMatch(/importo di chiusura/);
    });

    it('senza profitto bloccabile dichiarato non si approva', () => {
        expect(motivoNonApprovabileOmega(payload({ profitto_bloccabile: null })))
            .toMatch(/profitto bloccabile/);
    });
});

describe('ordine: prima quelle in cui chiudere conviene', () => {
    it('blocca_il_profitto prima, poi le altre; a parita la piu vecchia', () => {
        const ordinate = ordinaProposteOmega([
            proposta(1, { motivo_codice: 'tenere_vale_di_piu' }, '2026-09-16T20:00:00Z'),
            proposta(2, { motivo_codice: 'blocca_il_profitto' }, '2026-09-16T21:00:00Z'),
            proposta(3, { motivo_codice: 'blocca_il_profitto' }, '2026-09-16T20:30:00Z'),
        ]);
        expect(ordinate.map((p) => p.id)).toEqual([3, 2, 1]);
    });
});

describe('le RPC — nomi e argomenti esatti', () => {
    it('get_omega_proposte legge l elenco vivo', async () => {
        rpc.mockResolvedValue({
            data: [{ id: 9, kind: 'cashout', payload: payload(), created_at: 'x', updated_at: null }],
            error: null,
        } as never);
        const r = await fetchProposteOmega();
        expect(rpc).toHaveBeenCalledWith('get_omega_proposte');
        expect(r).toHaveLength(1);
        expect(r[0].payload.trade_id).toBe(4821);
    });

    it('migrazione non applicata: l errore della RPC RISALE (non un elenco vuoto muto)', async () => {
        rpc.mockResolvedValue({
            data: null, error: { message: 'function public.get_omega_proposte() does not exist' },
        } as never);
        await expect(fetchProposteOmega()).rejects.toThrow(/does not exist/);
    });

    it('approva: omega_request_approve con p_id', async () => {
        rpc.mockResolvedValue({ data: { ok: true, id: 9, status: 'pending' }, error: null } as never);
        await approvaPropostaOmega(9);
        expect(rpc).toHaveBeenCalledWith('omega_request_approve', { p_id: 9 });
    });

    it('la RPC che RITORNA ok:false non e un successo (review 15/09)', async () => {
        rpc.mockResolvedValue({
            data: { ok: false, status: 'pending', note: 'la proposta non e piu in attesa di approvazione' },
            error: null,
        } as never);
        await expect(approvaPropostaOmega(9)).rejects.toThrow(/non e piu in attesa/);
    });

    it('ignora: omega_request_ignore con p_id e p_reason', async () => {
        rpc.mockResolvedValue({ data: { ok: true }, error: null } as never);
        await ignoraPropostaOmega(9, 'preferisco tenere');
        expect(rpc).toHaveBeenCalledWith('omega_request_ignore', { p_id: 9, p_reason: 'preferisco tenere' });
    });
});
