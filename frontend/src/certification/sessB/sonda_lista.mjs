// Sonda (sola lettura): ripete 5 volte le stesse query a blocchi della lista partite (MatchesList.tsx:140-167)
// e controlla doppioni/mancanti rispetto alla SELECT unica. Uso: node sonda_lista.mjs <yyyy-mm-dd>
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { createClient } = require('@supabase/supabase-js');
const env = Object.fromEntries(readFileSync(process.argv[3], 'utf8').split(/\r?\n/).filter((l) => l.includes('=') && !l.trim().startsWith('#')).map((l) => { const i = l.indexOf('='); return [l.slice(0, i).trim(), l.slice(i + 1).trim().replace(/^["']|["']$/g, '')]; }));
const sb = createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY, { auth: { persistSession: false } });
const day = process.argv[2];
const out = [];
for (let rep = 0; rep < 5; rep++) {
    let all = []; let off = 0;
    for (let g = 0; g < 50; g++) {
        const { data, error } = await sb.from('fixture_predictions').select('fixture_id, fixture_date').eq('status', 'ok').gte('fixture_date', `${day}T00:00:00Z`).order('fixture_date', { ascending: true }).range(off, off + 999);
        if (error) throw error;
        if (!data.length) break;
        all = all.concat(data); off += data.length;
    }
    const ids = all.map((r) => r.fixture_id);
    const uniq = new Set(ids);
    out.push({ rep, rows: ids.length, distinct: uniq.size, dup: ids.length - uniq.size });
}
console.log(JSON.stringify(out));
