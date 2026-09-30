// ============================================================================
// mikeCoverForm.test.ts - piano Mike 29/09, P6 blocco 6A: il parametro
// `cover_form` nel pannello, specchio di Betfair/mike/config.py PARAM_SPEC
// (P5 blocco 2: `("back_over45", str, None, None, ("lay_under45", "back_over45"))`).
// Il valore di serie passa a `lay_under45` solo nell'ultimo blocco di P5 (P6 blocco 6).
// ============================================================================
import { describe, it, expect } from 'vitest';
import { mergeMikeParams, MIKE_PARAM_DEFAULTS, MIKE_PARAM_FIELDS } from '@/lib/mike';

const SERIE = 'lay_under45';

describe('P6 blocco 6A - forma della copertura nel pannello', () => {
    it('due scelte, gruppo della copertura, stesso ordine di config.py', () => {
        const f = MIKE_PARAM_FIELDS.find((x) => x.key === 'cover_form');
        expect(f?.group).toBe('cover');
        expect(f?.kind === 'choice' ? f.choices : null).toEqual(['lay_under45', 'back_over45']);
    });

    it('la spiegazione e’ in parole semplici: stessa strategia, cambia solo l’ordine', () => {
        const h = MIKE_PARAM_FIELDS.find((x) => x.key === 'cover_form')!.hint;
        expect(h).toContain('la strategia e’ la stessa, cambia solo l’ordine');
        expect(h).toContain('banca Under 4,5 (importo sempre piazzabile, minimo 0,50 EUR)');
        expect(h).toContain('punta Over 4,5, la forma di prima (minimo 2,00 EUR a passi di 0,50)');
    });

    it('30/09 M17: gli hint non dicono piu’ «Over 4.5» come copertura, ne’ «chiude comunque», e i gol HT sono quelli di serie (3-4)', () => {
        const hint = (k: string) => MIKE_PARAM_FIELDS.find((x) => x.key === k)!.hint;
        expect(hint('ko_green_window_s')).toContain('copertura piena sulla linea 4,5');
        expect(hint('ko_green_window_s')).not.toContain('Over 4.5');
        expect(hint('early_goal_cover2_delay_s')).toContain('prezzo della copertura di quel momento');
        expect(hint('early_goal_cover2_delay_s')).not.toContain('quota Over');
        expect(hint('ht_loss_exit_enabled')).toBe('a fine 1T con 3-4 gol (vedi gol min/max)');
        expect(MIKE_PARAM_DEFAULTS.ht_loss_goals_min).toBe(3);
        expect(MIKE_PARAM_DEFAULTS.ht_loss_goals_max).toBe(4);
        expect(hint('ht_loss_pct')).toContain('propone (o esegue, se le uscite automatiche sono accese)');
        expect(hint('ht_loss_pct')).not.toContain('chiude comunque');
    });

    it('valore di serie come config.py; un valore salvato valido resta, uno ignoto torna al valore di serie', () => {
        expect(MIKE_PARAM_DEFAULTS.cover_form).toBe(SERIE);
        expect(mergeMikeParams({ cover_form: 'lay_under45' }).cover_form).toBe('lay_under45');
        expect(mergeMikeParams({ cover_form: 'back_over45' }).cover_form).toBe('back_over45');
        expect(mergeMikeParams({ cover_form: 'boh' }).cover_form).toBe(SERIE);
    });
});
