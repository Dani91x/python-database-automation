// ============================================================================
// 08/10 - CANTIERE 12. L'impronta (sha256) dei file di registrazione e' INDIPENDENTE DAI
// FINE RIGA. Sul PC dell'utente `core.autocrlf=true` scrive i .jsonl con CRLF
// (`git ls-files --eol`: i/lf w/crlf) mentre le fixture portano lo sha dei byte LF: i due
// test "la registrazione e' cambiata dopo la generazione della fixture" erano rossi solo
// su Windows. Qui la copia CRLF si costruisce in una cartella TEMPORANEA (i file del
// repository non si riscrivono mai) e si prova che LF e CRLF danno la stessa impronta,
// che e' quella delle fixture esistenti (NON rigenerate), e che i .gz non si normalizzano.
// ============================================================================
import { afterEach, describe, expect, it } from 'vitest';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
    CARTELLA_REGISTRAZIONI, caricaFixtureCompleta, eventiConFixture, impronteSorgente, improntaContenuto,
} from './__fixtures__/replayBarraTutte';

const aLf = (b: Buffer): Buffer => Buffer.from(b.toString('latin1').replace(/\r\n/g, '\n'), 'latin1');
const aCrlf = (b: Buffer): Buffer => Buffer.from(aLf(b).toString('latin1').replace(/\n/g, '\r\n'), 'latin1');

const temporanee: string[] = [];
afterEach(() => { while (temporanee.length) rmSync(temporanee.pop() as string, { recursive: true, force: true }); });
function radiceTemporanea(): string {
    const d = mkdtempSync(join(tmpdir(), 'impronta-barra-'));
    temporanee.push(d);
    return d;
}

/** Copia la registrazione `ev` del repository in `radice/ev`: i .jsonl in chiaro passano da `trasforma`, il resto identico. */
function copiaRegistrazione(ev: string, radice: string, trasforma: (b: Buffer) => Buffer): void {
    const da = join(CARTELLA_REGISTRAZIONI, ev);
    const a = join(radice, ev);
    mkdirSync(a, { recursive: true });
    for (const nome of readdirSync(da, { withFileTypes: true }).filter(d => d.isFile()).map(d => d.name)) {
        const dati = readFileSync(join(da, nome));
        writeFileSync(join(a, nome), nome.endsWith('.jsonl') ? trasforma(dati) : dati);
    }
}

describe('impronta indipendente dai fine riga (funzione)', () => {
    it('LF e CRLF danno lo stesso sha256 per un file di testo', () => {
        const lf = Buffer.from('{"a":1}\n{"b":2}\n');
        const crlf = Buffer.from('{"a":1}\r\n{"b":2}\r\n');
        expect(crlf.equals(lf)).toBe(false);
        expect(improntaContenuto(crlf, true)).toBe(improntaContenuto(lf, true));
    });

    it('un file binario (.gz) NON si normalizza: 0d 0a dentro un gzip non e\' un fine riga', () => {
        expect(improntaContenuto(Buffer.from('ab\r\ncd'), false)).not.toBe(improntaContenuto(Buffer.from('ab\ncd'), false));
    });

    it('un CR isolato non e\' un fine riga e conta nell\'impronta', () => {
        expect(improntaContenuto(Buffer.from('a\rb\n'), true)).not.toBe(improntaContenuto(Buffer.from('a\nb\n'), true));
        expect(improntaContenuto(Buffer.from('a\r'), true)).not.toBe(improntaContenuto(Buffer.from('a'), true));
    });
});

describe.each(eventiConFixture())('registrazione %s: stessa impronta con LF e con CRLF, uguale alla fixture esistente', (ev) => {
    it('copia CRLF e copia LF in cartelle temporanee: impronteSorgente identiche e uguali a fixture.sorgente', () => {
        const sorgente = caricaFixtureCompleta(ev).sorgente;
        const lf = radiceTemporanea();
        const crlf = radiceTemporanea();
        copiaRegistrazione(ev, lf, aLf);
        copiaRegistrazione(ev, crlf, aCrlf);
        // la copia CRLF e' davvero diversa sul disco (altrimenti il test non potrebbe diventare rosso)
        const nomeTimeline = `${ev}.timeline.jsonl`;
        const bLf = readFileSync(join(lf, ev, nomeTimeline));
        const bCrlf = readFileSync(join(crlf, ev, nomeTimeline));
        expect(bCrlf.length).toBeGreaterThan(bLf.length);
        expect(bCrlf.includes(Buffer.from('\r\n'))).toBe(true);
        expect(bLf.includes(Buffer.from('\r'))).toBe(false);

        expect(impronteSorgente(ev, lf)).toEqual(sorgente);
        expect(impronteSorgente(ev, crlf)).toEqual(sorgente);
    });

    it('le fixture esistenti NON sono rigenerate: l\'impronta della registrazione del repository coincide con quella scritta nella fixture', () => {
        const sorgente = caricaFixtureCompleta(ev).sorgente;
        expect(impronteSorgente(ev)).toEqual(sorgente);
        // se il file nel repository sta con LF (Linux), l'impronta dei byte grezzi e quella normalizzata coincidono
        const grezzo = readFileSync(join(CARTELLA_REGISTRAZIONI, ev, `${ev}.timeline.jsonl`));
        if (!grezzo.includes(13)) expect(improntaContenuto(grezzo, false)).toBe(sorgente[`${ev}.timeline.jsonl`]);
    });

    it('i .gz della registrazione restano byte per byte (impronta dei byte grezzi)', () => {
        const sorgente = caricaFixtureCompleta(ev).sorgente;
        for (const nome of [`${ev}.raw.jsonl`, `${ev}.scores.jsonl`]) {
            const gz = join(CARTELLA_REGISTRAZIONI, ev, `${nome}.gz`);
            if (!existsSync(gz)) continue;
            expect(sorgente[nome], nome).toBe(improntaContenuto(readFileSync(gz), false));
        }
    });
});

describe('copia sintetica: i .gz con 0d 0a dentro non si normalizzano ma il testo si', () => {
    it('stesso testo LF/CRLF -> stessa impronta; .gz con byte diversi -> impronta diversa', () => {
        const scrivi = (radice: string, timeline: string, gz: string): void => {
            const d = join(radice, '9');
            mkdirSync(d, { recursive: true });
            writeFileSync(join(d, '9.timeline.jsonl'), timeline);
            writeFileSync(join(d, '9.raw.jsonl.gz'), gz);
            writeFileSync(join(d, '9.scores.jsonl.gz'), gz);
        };
        const a = radiceTemporanea(), b = radiceTemporanea();
        scrivi(a, '{"x":1}\n', 'ab\r\ncd');
        scrivi(b, '{"x":1}\r\n', 'ab\ncd');
        const ia = impronteSorgente('9', a), ib = impronteSorgente('9', b);
        expect(ia['9.timeline.jsonl']).toBe(ib['9.timeline.jsonl']);
        expect(ia['9.raw.jsonl']).not.toBe(ib['9.raw.jsonl']);
        expect(ia['9.scores.jsonl']).not.toBe(ib['9.scores.jsonl']);
    });
});
