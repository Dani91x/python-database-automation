// «ATTIVA ADESSO» della Media Under (07/10/2026, ordine dell'utente): il clic è
// un comando con un id unico; la scheda lo manda per la strada dei params e
// mostra cosa ne dice la sessione (stats.media_comando). Stesso pulsante e
// stessa dicitura in prova e in soldi veri, tranne la conferma dei soldi veri.
import { describe, expect, it } from 'vitest';
import {
    nuovoComandoAttivaAdesso, paramsAttivaAdesso, paramsMediaUnder, mediaUnderDefaults,
    statoDelClic, testoStatoClic, pulsanteCliccabile, ATTESA_ESITO_CLIC_MS, leggiMediaUnder,
    testoStatoMedia, testoConfermaAttivaAdesso, importiDallaRiga, MEDIA_UNDER_DEFAULTS,
    MEDIA_STATI_TESTO, CHIAVE_COMANDO,
} from './mediaUnder';

describe('Attiva adesso — il comando', () => {
    it('ogni clic ha un id nuovo e l\'istante del clic', () => {
        const a = nuovoComandoAttivaAdesso(new Date('2026-10-07T10:00:00Z'));
        const b = nuovoComandoAttivaAdesso(new Date('2026-10-07T10:00:00Z'));
        expect(a.id).not.toBe(b.id);
        expect(a.ts).toBe('2026-10-07T10:00:00.000Z');
    });

    it('a sessione ferma: tutti i parametri, armata dal pulsante, interruttore e comando', () => {
        const c = { id: 'clic-1', ts: '2026-10-07T10:00:00.000Z' };
        const out = paramsAttivaAdesso('OVER_UNDER_25', mediaUnderDefaults(), false, c);
        expect(out.media_mode).toBe(true);
        expect(out.media_a_clic).toBe(true);
        expect(out.media_rientro_auto_filtri).toBe(false);
        expect(out[CHIAVE_COMANDO]).toEqual(c);
        expect(paramsAttivaAdesso('OVER_UNDER_25', mediaUnderDefaults(), true, c).media_rientro_auto_filtri).toBe(true);
        // l'accensione di sempre NON manda le chiavi del pulsante
        const sempre = paramsMediaUnder('OVER_UNDER_25', mediaUnderDefaults());
        expect('media_a_clic' in sempre).toBe(false);
        expect('media_rientro_auto_filtri' in sempre).toBe(false);
        expect(CHIAVE_COMANDO in sempre).toBe(false);
        expect(MEDIA_UNDER_DEFAULTS.media_rientro_auto_filtri).toBe(false);
    });
});

describe('Attiva adesso — lo stato del clic letto dalla sessione', () => {
    const base: Record<string, unknown> = { media_stato: 'ATTESA_CLIC', media_a_clic: true };

    it('inviato finché la sessione non ha scritto il SUO esito', () => {
        expect(statoDelClic('clic-2', null)).toEqual({ fase: 'inviato', id: 'clic-2' });
        const m = leggiMediaUnder({ ...base, media_comando: { id: 'clic-1', esito: 'eseguito', prezzo: 1.5, importo: 10 } });
        // l'esito di un clic VECCHIO non vale per il clic appena mandato
        expect(statoDelClic('clic-2', m!.comando).fase).toBe('inviato');
    });

    it('eseguito con prezzo e importo, rifiutato col motivo della sessione', () => {
        const ok = leggiMediaUnder({ ...base, media_comando: { id: 'c', esito: 'eseguito', prezzo: 1.62, importo: 10, in_gioco: true } });
        const s = statoDelClic('c', ok!.comando);
        expect(s.fase).toBe('eseguito');
        expect(testoStatoClic(s)).toBe('Attiva adesso ESEGUITO: punta di 10,00 € a 1,62 in gioco.');
        const no = leggiMediaUnder({ ...base, media_comando: { id: 'c', esito: 'rifiutato', motivo: 'mercato sospeso: nessun ordine' } });
        expect(testoStatoClic(statoDelClic('c', no!.comando))).toBe('Attiva adesso RIFIUTATO: mercato sospeso: nessun ordine.');
        // dopo un riavvio la scheda non sa il suo id: mostra l'ultimo esito scritto
        expect(statoDelClic(null, no!.comando).fase).toBe('rifiutato');
    });

    it('un comando con i tipi sbagliati non passa', () => {
        expect(leggiMediaUnder({ ...base, media_comando: { id: 3 } })!.comando).toBeNull();
        expect(leggiMediaUnder({ ...base, media_comando: { id: 'x', prezzo: '1.5' } })!.comando!.prezzo).toBeNull();
    });

    it('niente doppio clic mentre il clic è inviato; di nuovo cliccabile dopo l\'esito o l\'attesa', () => {
        const inviato = statoDelClic('c', null);
        expect(pulsanteCliccabile(inviato, 1000, 1000 + 500)).toBe(false);
        expect(pulsanteCliccabile(inviato, 1000, 1000 + ATTESA_ESITO_CLIC_MS + 1)).toBe(true);
        const chiuso = statoDelClic('c', { id: 'c', esito: 'eseguito', motivo: null, prezzo: 1.5, importo: 10, in_gioco: false });
        expect(pulsanteCliccabile(chiuso, 1000, 1001)).toBe(true);
    });
});

describe('Attiva adesso — testi della scheda', () => {
    it('attesa del clic, rientro automatico, gestione in gioco', () => {
        expect(MEDIA_STATI_TESTO.ATTESA_CLIC).toMatch(/ATTESA DEL CLIC/);
        const fermo = leggiMediaUnder({ media_stato: 'FERMO', media_a_clic: true })!;
        expect(testoStatoMedia(fermo)).toMatch(/riparte da solo/);
        const sempre = leggiMediaUnder({ media_stato: 'FERMO' })!;
        expect(testoStatoMedia(sempre)).toBe(MEDIA_STATI_TESTO.FERMO);
        const gioco = leggiMediaUnder({ media_stato: 'IN_POSIZIONE', media_a_clic: true, media_in_gioco: true })!;
        expect(testoStatoMedia(gioco)).toMatch(/in gioco gestisce la posizione/);
    });

    it('la conferma dei soldi veri dice cosa succede, coi numeri della riga', () => {
        const t = testoConfermaAttivaAdesso('A - B', 'Under 2,5', importiDallaRiga({ media_stake: 12.5, media_max_rientri: 3, media_rischio_max: 0 }));
        expect(t).toContain('ORDINI REALI');
        expect(t).toContain('PUNTA SUBITO 12,50 €');
        expect(t).toContain('fino a 3 rientri');
        expect(t).toContain('Rischio massimo SPENTO');
        expect(importiDallaRiga(null).media_stake).toBe(10);
    });
});
