// MEDIA UNDER (05/10/2026): la scheda manda TUTTI i parametri (la sessione non
// inventa un valore mancante), controlla i valori prima di mandarli e legge le
// statistiche della sessione controllandone i tipi.
import { describe, expect, it } from 'vitest';
import {
    MEDIA_UNDER_DEFAULTS, MEDIA_UNDER_CAMPI, mediaUnderDefaults, erroriMediaUnder,
    paramsMediaUnder, leggiObiettiviLive, leggiMediaUnder, testoObiettivo,
} from './mediaUnder';

describe('mediaUnder — parametri', () => {
    it('spenta di serie e i valori di serie della spec par.5', () => {
        expect(MEDIA_UNDER_DEFAULTS.media_mode).toBe(false);
        const p = mediaUnderDefaults();
        expect(p.media_stake).toBe(10);
        expect(p.media_max_rientri).toBe(5);
        expect(p.media_rischio_max).toBe(0);
        expect(p.media_obiettivi_live).toEqual([0, 0.3, 1]);
        expect(erroriMediaUnder('OVER_UNDER_25', p)).toEqual([]);
    });

    it('il mercato si sceglie: senza mercato la scheda non manda', () => {
        expect(erroriMediaUnder('', mediaUnderDefaults()).join(' ')).toMatch(/Scegli il mercato/);
    });

    it('punta d\'ingresso solo da 1,00 a multipli di 0,50 (Betfair.it)', () => {
        const p = mediaUnderDefaults();
        expect(erroriMediaUnder('OVER_UNDER_35', { ...p, media_stake: 10.3 })).toHaveLength(1);
        expect(erroriMediaUnder('OVER_UNDER_35', { ...p, media_stake: 0.5 })).toHaveLength(1);
        expect(erroriMediaUnder('OVER_UNDER_35', { ...p, media_stake: 12.5 })).toEqual([]);
    });

    it('valori non validi: tick, rientri, quote, commissione', () => {
        const p = mediaUnderDefaults();
        expect(erroriMediaUnder('OVER_UNDER_25', { ...p, media_tick_chiusura: 0 })).toHaveLength(1);
        expect(erroriMediaUnder('OVER_UNDER_25', { ...p, media_tick_rientro: 1.5 })).toHaveLength(1);
        expect(erroriMediaUnder('OVER_UNDER_25', { ...p, media_max_rientri: -1 })).toHaveLength(1);
        expect(erroriMediaUnder('OVER_UNDER_25', { ...p, media_quota_min: 4.5 })).toHaveLength(1);
        expect(erroriMediaUnder('OVER_UNDER_25', { ...p, media_commissione_pct: 100 })).toHaveLength(1);
        expect(erroriMediaUnder('OVER_UNDER_25', { ...p, media_rischio_max: -1 })).toHaveLength(1);
    });

    it('il payload ha TUTTE le chiavi, la modalità accesa e sniper/theta/intervallo spenti', () => {
        const out = paramsMediaUnder('OVER_UNDER_35', mediaUnderDefaults());
        for (const c of MEDIA_UNDER_CAMPI) expect(out[c.key]).toBeTypeOf('number');
        expect(out.media_obiettivi_live).toEqual([0, 0.3, 1]);
        expect(out.media_mode).toBe(true);
        expect(out.media_mercato).toBe('OVER_UNDER_35');
        expect(out.sniper_mode).toBe(false);
        expect(out.theta_mode).toBe(false);
        expect(out.ht_mode).toBe(false);
    });

    it('obiettivi in gioco scritti con la virgola italiana', () => {
        expect(leggiObiettiviLive('0; 0,30; 1')).toEqual([0, 0.3, 1]);
        expect(leggiObiettiviLive('0 0.5 2')).toEqual([0, 0.5, 2]);
        expect(leggiObiettiviLive('0; dieci')).toBeNull();
    });
});

describe('mediaUnder — lettura delle statistiche della sessione', () => {
    const stats: Record<string, unknown> = {
        pnl_locked: 0,
        media_stato: 'LIVE', media_mercato: 'OVER_UNDER_25', media_rientri: 5, media_max_rientri: 5,
        media_totale_puntato: 321, media_quota_media: 1.5807, media_se_vince: 186.39, media_se_perde: -321,
        media_banca: { stato: 'viva', importo: 321.13, quota: 1.58, abbinato: 0, testo: 'appoggiata, non ancora abbinata' },
        media_cicli_chiusi: 0, media_pnl_chiuso_lordo: 0, media_rientri_bloccati: null, media_riavvio: null,
        media_fonte: 'solo ordini del bot',
        media_chiusura: {
            fonte: 'solo ordini del bot', tick: 2,
            posizione: { totale_puntato: 10, quota_media: 1.32, banche_abbinate: 0, se_vince: 3.2, se_perde: -10 },
            banca: { stato: 'nessuna' },
            chiudi_adesso: { banca: 7.9, quota: 1.67, pnl_lordo: -2.1, pnl_netto: -2.1 },
            obiettivi: [{
                obiettivo_netto: 0.3, quota_punta: 1.67, quota_chiusura: 1.65, punta: 189.5,
                punta_esatta: 189.75, rischio_totale: 199.5, rischio_totale_esatto: 199.75,
                quota_media_dopo: 1.6525, quota_media_dopo_esatta: 1.6525, banca_dopo: 199.8,
                profitto_netto: 0.3, piazzabile: true,
            }],
        },
    };

    it('nessuna modalità = null (la vista non compare)', () => {
        expect(leggiMediaUnder({ pnl_locked: 1 })).toBeNull();
        expect(leggiMediaUnder(null)).toBeNull();
    });

    it('legge stato, banca e riquadro con i loro tipi', () => {
        const m = leggiMediaUnder(stats);
        expect(m?.stato).toBe('LIVE');
        expect(m?.banca.importo).toBe(321.13);
        expect(m?.chiusura?.chiudi_adesso?.banca).toBe(7.9);
        expect(m?.chiusura?.obiettivi[0].punta).toBe(189.5);
    });

    it('un campo col tipo sbagliato non passa come numero', () => {
        const m = leggiMediaUnder({ ...stats, media_totale_puntato: '321', media_chiusura: { fonte: 'x' } });
        expect(m?.totale_puntato).toBe(0);
        expect(m?.chiusura).toBeNull();
    });

    it('la riga dell\'obiettivo dice punta a multiplo, importo esatto, rischio, media e banca dopo', () => {
        const m = leggiMediaUnder(stats);
        const t = testoObiettivo(m!.chiusura!.obiettivi[0]);
        expect(t).toContain('PUNTA 189,50 €');
        expect(t).toContain('importo esatto 189,75 €');
        expect(t).toContain('Rischio totale 199,50 €');
        expect(t).toContain('con l\'esatto 199,75 €');
        expect(t).toContain('BANCA di 199,80 €');
        expect(testoObiettivo({ ...m!.chiusura!.obiettivi[0], piazzabile: false })).toMatch(/non piazzabile/);
    });
});
