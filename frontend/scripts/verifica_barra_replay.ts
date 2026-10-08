// verifica_barra_replay.ts -- certifica la COERENZA BARRA / SIMBOLI / TABELLONE di
// TUTTE le partite di Match Replay gia' caricate nel database, in SOLA LETTURA.
//
// Ordine dell'utente (07/10/2026): la coerenza della barra e' uno standard per tutte
// le partite, presenti e future. Per ogni partita di `list_replays` carica i dati come
// la pagina (`get_replay_meta` + `get_replay_frames` a finestre, le stesse funzioni di
// `src/lib/live.ts`), li passa al verificatore (`src/lib/replayVerificaBarra*.ts`) e
// stampa un referto per partita (OK / incoerenze con codice, istante e spiegazione) e
// un riepilogo.
//
// USO (dalla cartella frontend/; vite-node e' gia' nelle dipendenze, nessuna installazione):
//
//   npx vite-node scripts/verifica_barra_replay.ts
//   npx vite-node scripts/verifica_barra_replay.ts --env-file ../.env
//   npx vite-node scripts/verifica_barra_replay.ts --evento 35797769 --evento 35760084
//   npx vite-node scripts/verifica_barra_replay.ts --solo-incoerenti --senza-note
//
// CREDENZIALI: SOLO da variabili d'ambiente (mai scritte nel file), con questi nomi:
//   URL    VITE_SUPABASE_URL      (oppure SUPABASE_URL)
//   CHIAVE SUPABASE_SERVICE_ROLE_KEY   (le RPC sono concesse a service_role e authenticated)
//          oppure VITE_SUPABASE_ANON_KEY + VERIFICA_EMAIL + VERIFICA_PASSWORD (utente dell'app)
// `--env-file <percorso>` carica un file .env nelle variabili del processo (Node >= 20.12);
// le variabili gia' impostate nella shell hanno la precedenza.
//
// SOLA LETTURA: il client viene "blindato" (`blindaSolaLettura`): sono permesse solo le RPC
// list_replays, get_replay_meta, get_replay_frames, get_replay; ogni altra RPC o accesso a
// una tabella lancia un errore. Nessun INSERT/UPDATE/DELETE e' possibile da qui.
//
// CODICE DI USCITA: 0 = tutte coerenti; 1 = almeno una partita con incoerenze o non
// verificabile; 2 = uso errato o credenziali mancanti.

import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { comandoViteNode } from '@/lib/replayVerificaBarraLancio';

interface Argomenti {
    eventi: string[];
    limite: number;
    envFile: string | null;
    soloIncoerenti: boolean;
    senzaNote: boolean;
    json: boolean;
    aiuto: boolean;
}

function leggiArgomenti(argv: string[]): Argomenti | string {
    const a: Argomenti = { eventi: [], limite: 500, envFile: null, soloIncoerenti: false, senzaNote: false, json: false, aiuto: false };
    for (let i = 0; i < argv.length; i++) {
        const x = argv[i];
        const valore = (): string | null => (i + 1 < argv.length ? argv[++i] : null);
        if (x === '--evento') { const v = valore(); if (!v) return 'manca il valore di --evento'; a.eventi.push(v); }
        else if (x === '--limite') { const v = Number(valore()); if (!Number.isInteger(v) || v < 1 || v > 500) return '--limite deve essere un intero da 1 a 500'; a.limite = v; }
        else if (x === '--env-file') { const v = valore(); if (!v) return 'manca il percorso di --env-file'; a.envFile = v; }
        else if (x === '--solo-incoerenti') a.soloIncoerenti = true;
        else if (x === '--senza-note') a.senzaNote = true;
        else if (x === '--json') a.json = true;
        else if (x === '--aiuto' || x === '-h' || x === '--help') a.aiuto = true;
        else return `argomento sconosciuto: ${x}`;
    }
    return a;
}

const USO = [
    'uso: npx vite-node scripts/verifica_barra_replay.ts [--env-file ../.env] [--evento ID]... [--limite N]',
    '                                                    [--solo-incoerenti] [--senza-note] [--json]',
    'credenziali (solo da variabili d\'ambiente): VITE_SUPABASE_URL (o SUPABASE_URL) e',
    '  SUPABASE_SERVICE_ROLE_KEY, oppure VITE_SUPABASE_ANON_KEY + VERIFICA_EMAIL + VERIFICA_PASSWORD',
].join('\n');

async function principale(): Promise<number> {
    const arg = leggiArgomenti(process.argv.slice(2));
    if (typeof arg === 'string') { console.error(`${arg}\n${USO}`); return 2; }
    if (arg.aiuto) { console.log(USO); return 0; }

    if (arg.envFile) {
        try {
            (process as unknown as { loadEnvFile: (p: string) => void }).loadEnvFile(arg.envFile);
        } catch (e) {
            console.error(`--env-file ${arg.envFile}: ${e instanceof Error ? e.message : String(e)} (serve Node >= 20.12; in alternativa imposta le variabili nella shell)`);
            return 2;
        }
    }
    const url = process.env.VITE_SUPABASE_URL || process.env.SUPABASE_URL || '';
    const chiaveServizio = process.env.SUPABASE_SERVICE_ROLE_KEY || '';
    const chiaveAnon = process.env.VITE_SUPABASE_ANON_KEY || '';
    const email = process.env.VERIFICA_EMAIL || '';
    const password = process.env.VERIFICA_PASSWORD || '';
    const chiave = chiaveServizio || chiaveAnon;
    if (!url || !chiave) {
        console.error('Credenziali mancanti: servono VITE_SUPABASE_URL (o SUPABASE_URL) e SUPABASE_SERVICE_ROLE_KEY (oppure VITE_SUPABASE_ANON_KEY + VERIFICA_EMAIL + VERIFICA_PASSWORD).');
        return 2;
    }
    if (!chiaveServizio && (!email || !password)) {
        console.error('Con la sola chiave anonima servono anche VERIFICA_EMAIL e VERIFICA_PASSWORD (le RPC non sono concesse ad anon).');
        return 2;
    }
    // Il client del frontend (`src/integrations/supabase/client.ts`) legge `import.meta.env.VITE_SUPABASE_URL`
    // e `VITE_SUPABASE_ANON_KEY`, che vite-node FISSA all'avvio del processo (non seguono i cambi
    // successivi di process.env). Se all'avvio non erano gia' queste, il processo si rilancia UNA volta
    // con l'ambiente giusto (le credenziali restano solo nell'ambiente, mai in un file).
    const envAvvio = (import.meta as unknown as { env: Record<string, string | undefined> }).env;
    if (envAvvio.VITE_SUPABASE_URL !== url || envAvvio.VITE_SUPABASE_ANON_KEY !== chiave) {
        if (process.env.VERIFICA_BARRA_RILANCIATO === '1') {
            console.error('Impossibile impostare le credenziali per il client (rilancio gia\' avvenuto).');
            return 2;
        }
        // (vite-node lascia in process.argv solo [node, vite-node, ...argomenti]: il rilancio passa da npx come l'avvio)
        // 08/10 (cantiere 12): il comando lo costruisce la funzione comune (su Windows `npx.cmd` con shell e il
        // percorso del file tra virgolette: "C:\PYTHON DATABASE\..." ha uno spazio), la stessa del test.
        const cmd = comandoViteNode([fileURLToPath(import.meta.url), ...process.argv.slice(2)], process.platform);
        const figlio = spawnSync(cmd.comando, cmd.argomenti, {
            stdio: 'inherit',
            shell: cmd.shell,
            env: { ...process.env, VITE_SUPABASE_URL: url, VITE_SUPABASE_ANON_KEY: chiave, VERIFICA_BARRA_RILANCIATO: '1' },
        });
        if (figlio.error) { console.error(`Il rilancio non e' partito: ${figlio.error.message}`); return 1; }
        return figlio.status ?? 1;
    }

    const db = await import('@/lib/replayVerificaBarraDb');
    db.blindaSolaLettura(db.clienteSupabase);
    if (!chiaveServizio) {
        try { await db.accediConUtente(email, password); } catch (e) { console.error(e instanceof Error ? e.message : String(e)); return 2; }
    }

    const t0 = Date.now();
    let risultati: Awaited<ReturnType<typeof db.verificaPartite>>;
    try {
        risultati = await db.verificaPartite(db.fonteSupabase, {
            limite: arg.limite,
            eventi: arg.eventi,
            alRisultato: (r, i, tot) => {
                if (arg.json) return;
                const t = db.refertoPartita(r, !arg.senzaNote, arg.soloIncoerenti);
                if (t) console.log(`[${i + 1}/${tot}] ${t}  (${(r.ms / 1000).toFixed(1)} s)`);
            },
        });
    } catch (e) {
        console.error(`Lettura dell'elenco delle partite fallita: ${e instanceof Error ? e.message : String(e)}`);
        return 1;
    }
    const rie = db.riepilogo(risultati);
    if (arg.json) {
        console.log(JSON.stringify({
            riepilogo: { partite: rie.partite, ok: rie.ok, incoerenti: rie.incoerenti, nonVerificate: rie.nonVerificate },
            partite: risultati.map(r => ({
                event_id: r.eventId, titolo: r.titolo, ok: r.esito?.ok ?? false, errore: r.errore,
                incoerenze: r.esito?.incoerenze ?? [], note: arg.senzaNote ? [] : (r.esito?.note ?? []), conteggi: r.esito?.conteggi ?? null,
            })),
        }, null, 2));
    } else {
        if (risultati.length === 0) console.log('Nessuna partita in list_replays (o nessuna corrisponde ai filtri).');
        if (risultati.length >= arg.limite && arg.eventi.length === 0) {
            console.log(`ATTENZIONE: list_replays ha restituito ${risultati.length} partite = il limite richiesto (${arg.limite}): ce ne potrebbero essere altre.`);
        }
        console.log(rie.righe.join('\n'));
        console.log(`Tempo totale: ${((Date.now() - t0) / 1000).toFixed(1)} s. Sola lettura: nessuna scrittura sul database.`);
    }
    return rie.tutteOk ? 0 : 1;
}

// esce DOPO aver svuotato stdout (con l'output su una pipe un process.exit immediato puo' troncarlo)
const esci = (codice: number): void => { process.stdout.write('', () => process.exit(codice)); };
principale().then(esci, e => { console.error(e instanceof Error ? e.stack ?? e.message : String(e)); esci(1); });
