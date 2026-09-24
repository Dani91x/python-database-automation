// rilettureMirate.test.ts - 24/09: l'anti-tempesta delle riletture mirate.
// Orologio e timer FINTI: il tempo lo decide il test, niente attese vere.
//
// FALSIFICAZIONE (esito nel referto): togliendo il controllo `programmata !=
// null` (coalescenza) il test "una raffica costa al piu' due letture" diventa
// rosso; togliendo il minimo (sempre 'subito') diventa rosso "mai piu' di una
// ogni 2 s".
import { describe, it, expect } from 'vitest';
import { RilettureMirate, MINIMO_RILETTURA_MS, type OrologioRiletture } from './rilettureMirate';

function orologioFinto() {
    let t = 1_000_000;
    let prossimo = 1;
    const timer = new Map<number, { quando: number; cb: () => void }>();
    const o: OrologioRiletture = {
        ora: () => t,
        programma: (cb, ms) => { const id = prossimo++; timer.set(id, { quando: t + ms, cb }); return id; },
        annulla: (h) => { timer.delete(h as number); },
    };
    const avanza = (ms: number) => {
        const fine = t + ms;
        for (;;) {
            let primo: [number, { quando: number; cb: () => void }] | null = null;
            for (const e of timer) if (e[1].quando <= fine && (!primo || e[1].quando < primo[1].quando)) primo = e;
            if (!primo) break;
            timer.delete(primo[0]);
            t = primo[1].quando;
            primo[1].cb();
        }
        t = fine;
    };
    return { o, avanza, timer };
}

describe('RilettureMirate', () => {
    it('il minimo e\' 2 s', () => {
        expect(MINIMO_RILETTURA_MS).toBe(2_000);
    });

    it('la prima rilettura parte SUBITO', () => {
        const { o } = orologioFinto();
        const r = new RilettureMirate(2_000, o);
        let n = 0;
        r.registra('omega', () => { n += 1; });
        expect(r.chiedi('omega')).toBe('subito');
        expect(n).toBe(1);
    });

    it('una raffica costa al piu\' due letture (una subito, una a 2 s)', () => {
        const { o, avanza } = orologioFinto();
        const r = new RilettureMirate(2_000, o);
        let n = 0;
        r.registra('omega', () => { n += 1; });
        const esiti = Array.from({ length: 50 }, () => r.chiedi('omega'));
        expect(esiti[0]).toBe('subito');
        expect(esiti[1]).toBe('programmata');
        expect(esiti.slice(2).every((e) => e === 'coalescita')).toBe(true);
        expect(n).toBe(1);
        avanza(1_999);
        expect(n).toBe(1);
        avanza(1);
        expect(n).toBe(2);
        avanza(10_000);
        expect(n).toBe(2);
    });

    it('mai piu\' di una ogni 2 s per gruppo, anche su una tempesta lunga', () => {
        const { o, avanza } = orologioFinto();
        const r = new RilettureMirate(2_000, o);
        const istanti: number[] = [];
        r.registra('safe', () => { istanti.push(o.ora()); });
        for (let i = 0; i < 600; i += 1) { r.chiedi('safe'); avanza(100); }   // 60 s
        expect(istanti.length).toBeLessThanOrEqual(31);
        for (let i = 1; i < istanti.length; i += 1) {
            expect(istanti[i] - istanti[i - 1]).toBeGreaterThanOrEqual(2_000);
        }
    });

    it('i gruppi sono indipendenti', () => {
        const { o } = orologioFinto();
        const r = new RilettureMirate(2_000, o);
        const n: Record<string, number> = { omega: 0, mike: 0 };
        r.registra('omega', () => { n.omega += 1; });
        r.registra('mike', () => { n.mike += 1; });
        expect(r.chiedi('omega')).toBe('subito');
        expect(r.chiedi('mike')).toBe('subito');
        expect(n).toEqual({ omega: 1, mike: 1 });
    });

    it('dopo 2 s di quiete si riparte subito', () => {
        const { o, avanza } = orologioFinto();
        const r = new RilettureMirate(2_000, o);
        let n = 0;
        r.registra('tennis', () => { n += 1; });
        r.chiedi('tennis');
        avanza(2_500);
        expect(r.chiedi('tennis')).toBe('subito');
        expect(n).toBe(2);
    });

    it('gruppo sconosciuto: nessuna lettura', () => {
        const { o } = orologioFinto();
        const r = new RilettureMirate(2_000, o);
        expect(r.chiedi('nessuno')).toBe('ignota');
    });

    it('chiudi: la rilettura programmata non parte piu\'', () => {
        const { o, avanza, timer } = orologioFinto();
        const r = new RilettureMirate(2_000, o);
        let n = 0;
        r.registra('omega', () => { n += 1; });
        r.chiedi('omega');
        r.chiedi('omega');
        r.chiudi();
        expect(timer.size).toBe(0);
        avanza(5_000);
        expect(n).toBe(1);
        expect(r.chiedi('omega')).toBe('ignota');
    });

    it('una lettura che solleva non rompe lo scheduler', () => {
        const { o, avanza } = orologioFinto();
        const r = new RilettureMirate(2_000, o);
        let n = 0;
        r.registra('omega', () => { n += 1; throw new Error('rete giu\''); });
        expect(r.chiedi('omega')).toBe('subito');
        r.chiedi('omega');
        avanza(2_000);
        expect(n).toBe(2);
    });
});
