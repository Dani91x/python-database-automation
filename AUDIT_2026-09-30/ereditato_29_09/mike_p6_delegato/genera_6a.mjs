// genera_6a.mjs - costruisce, da master, le versioni «6A» di lib/mike.ts e del
// test di cover_form (valore di serie back_over45), in una cartella a scelta.
// Uso: node genera_6a.mjs <cartella_con_mike_master.ts> <radice_worktree>
import { readFileSync, writeFileSync } from 'node:fs';
const sp = process.argv[2], wt = process.argv[3];
let m = readFileSync(`${sp}/mike_master.ts`, 'utf8');
const w = readFileSync(`${wt}/frontend/src/lib/mike.ts`, 'utf8');
const nl = m.includes('\r\n') ? '\r\n' : '\n';
const wl = w.split(/\r?\n/);
const i = wl.findIndex((l) => l.includes("key: 'cover_form'"));
const campo = [wl[i - 1], wl[i]].join(nl);
const anc = "hint: 'oltre: si logga cover_overshoot', group: 'cover' },";
if (m.split(anc).length !== 2) throw new Error('ancora campo');
m = m.replace(anc, anc + nl + campo);
const a2 = 'cover_max_overshoot_pct: 30, exact_sizes: true,';
if (m.split(a2).length !== 2) throw new Error('ancora default');
m = m.replace(a2, "cover_max_overshoot_pct: 30, cover_form: 'back_over45', exact_sizes: true,");
writeFileSync(`${sp}/mike_6a.ts`, m, 'utf8');
const t = readFileSync(`${wt}/frontend/src/lib/mikeCoverForm.test.ts`, 'utf8')
    .replace("const SERIE = 'lay_under45';", "const SERIE = 'back_over45';");
writeFileSync(`${sp}/mikeCoverForm_6a.test.ts`, t, 'utf8');
console.log('ok', nl === '\r\n' ? 'crlf' : 'lf');
