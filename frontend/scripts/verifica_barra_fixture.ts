// verifica_barra_fixture.ts -- verifica della barra di Match Replay su FIXTURE generate dal raw
// (08/10, cantiere 13). Nessun database, nessuna rete: legge solo i file JSON indicati.
//
// A cosa serve: riprodurre una partita del database dal suo raw (sul PC, `_live_raw/<event>/`)
// con la regola unica del curatore e verificarla come la verifica la pagina:
//
//   (dalla radice)  python tools/replay_barra_fixture.py --registrazioni _live_raw --uscita <cartella> 35787218
//   (da frontend/)  npx vite-node scripts/verifica_barra_fixture.ts <cartella>/replay_barra_35787218.json --dettaglio
//
// Confrontato con `scripts/verifica_barra_replay.ts --evento 35787218 --dettaglio` (dati caricati
// nel database) dice se un'incoerenza viene dai dati caricati (sparisce dal raw) o resta.
//
// USO: npx vite-node scripts/verifica_barra_fixture.ts <fixture.json>... [--dettaglio] [--senza-note]
// CODICE DI USCITA: 0 = tutte coerenti; 1 = almeno una incoerente (anche solo per dati) o illeggibile;
// 2 = uso errato.

import { readFileSync } from 'node:fs';
import { verificaFixture, type FixtureDaVerificare } from '@/lib/replayVerificaBarraFixture';
import { soloPerDati } from '@/lib/replayVerificaBarra';

function principale(argv: string[]): number {
    const file: string[] = [];
    let dettaglio = false, conNote = true;
    for (const x of argv) {
        if (x === '--dettaglio') dettaglio = true;
        else if (x === '--senza-note') conNote = false;
        else if (x === '--aiuto' || x === '-h' || x === '--help') { console.log('uso: npx vite-node scripts/verifica_barra_fixture.ts <fixture.json>... [--dettaglio] [--senza-note]'); return 0; }
        else if (x.startsWith('--')) { console.error(`argomento sconosciuto: ${x}`); return 2; }
        else file.push(x);
    }
    if (file.length === 0) { console.error('indica almeno una fixture (replay_barra_<event>.json)'); return 2; }
    let ok = 0, perDati = 0, incoerenti = 0, illeggibili = 0;
    for (const p of file) {
        let fx: FixtureDaVerificare;
        try {
            fx = JSON.parse(readFileSync(p, 'utf-8')) as FixtureDaVerificare;
        } catch (e) {
            illeggibili += 1;
            console.log(`ILLEGGIBILE ${p}: ${e instanceof Error ? e.message : String(e)}`);
            continue;
        }
        const r = verificaFixture(fx, { dettaglio, conNote });
        console.log(r.testo);
        if (r.esito.ok) ok += 1;
        else if (soloPerDati(r.esito)) perDati += 1;
        else incoerenti += 1;
    }
    console.log(`RIEPILOGO FIXTURE: ${file.length} verificate: ${ok} OK, ${perDati} solo per dati, ${incoerenti} da correggere, ${illeggibili} illeggibili. Nessun database: solo lettura dei file.`);
    return ok === file.length ? 0 : 1;
}

const codice = principale(process.argv.slice(2));
process.stdout.write('', () => process.exit(codice));
