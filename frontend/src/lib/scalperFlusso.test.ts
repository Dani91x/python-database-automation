// Cantiere J2 (28/09/2026): la sessione scalper col proprio stream MUTO lo
// dichiara in Control Room finche' dura. `stats.flusso` ha le chiavi di
// `stream_muto.SorvegliaStream.dichiarazione` (scritte dal battito della
// sessione, `scalper_session.sorveglia_flusso_sessione`).
import { describe, expect, it } from 'vitest';
import { flussoSessioneScalper, notaSessioneScalper, type SessioneScalper } from './scalperControlRoom';

const ORA = Date.parse('2026-09-28T20:00:00Z');

function sessione(flusso: Record<string, unknown> | null): SessioneScalper {
    return {
        event_id: '35760084', status: 'running', mode: 'paper', dry_run: false, stake: 10,
        params: null, bias: null, bias_meta: null,
        stats: flusso ? { pnl_locked: 0, flusso } : { pnl_locked: 0 },
        error: null, requested_at: new Date(ORA - 600_000).toISOString(),
        started_at: new Date(ORA - 590_000).toISOString(), stopped_at: null,
        heartbeat_at: new Date(ORA - 3_000).toISOString(), updated_at: null,
        event_name: 'Roma v Lazio', league_name: 'Serie A', kickoff: null,
        ultima_attivita_at: null, ultima_attivita_kind: null,
    };
}

describe('flusso dello stream della sessione scalper', () => {
    it('episodio in corso: la frase lo dice per prima, col tempo e il motivo', () => {
        const s = sessione({ vivo: false, motivo: 'flusso_interrotto', eta_s: 42, interrotto: true,
            mercati_fermi: ['1.200'], muto_da_s: 27.4, episodi: 1 });
        expect(flussoSessioneScalper(s)).toContain('FLUSSO PREZZI INTERROTTO da 27 s');
        const nota = notaSessioneScalper(s, ORA, 1);
        expect(nota.startsWith('FLUSSO PREZZI INTERROTTO')).toBe(true);
        expect(nota).toContain('posizione NON gestita');
    });
    it('stream vivo o dato assente: nessuna frase', () => {
        expect(flussoSessioneScalper(sessione({ vivo: true, motivo: null, eta_s: 2, interrotto: false,
            mercati_fermi: [], muto_da_s: null, episodi: 1 }))).toBeNull();
        expect(flussoSessioneScalper(sessione(null))).toBeNull();
        expect(notaSessioneScalper(sessione(null), ORA, 1)).not.toContain('FLUSSO');
    });
});
