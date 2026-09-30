// ============================================================================
// falsifica_mike_p6.mjs - falsificazione dei test nuovi del pacchetto P6 (app).
// Uso (dalla cartella frontend/):  node ../AUDIT_2026-09-29/mike_p6/falsifica_mike_p6.mjs <blocco>
// Per ogni mutazione: copia in memoria del file + sha256, UNA sostituzione
// (deve esistere una sola volta), vitest sui soli file indicati, RIPRISTINO
// dalla copia in un finally e controllo dell'hash. Atteso: ogni mutazione ROSSA.
// Non interrompere a meta': il ripristino avviene nel finally.
// ============================================================================
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';

const sha = (s) => createHash('sha256').update(s).digest('hex');

const BLOCCHI = {
    1: [
        { id: 'M1 frase dell esito sbagliata', file: 'src/lib/mike.ts',
          da: "ritirato_da_noi: 'ritirato da Mike',", a: "ritirato_da_noi: 'errore',",
          test: ['src/components/mike/MikeP6Blocco1.test.tsx'] },
        { id: 'M2 esito letto anche fuori dagli errori', file: 'src/lib/mike.ts',
          da: "if (t.status !== 'error') return null;",
          a: "if (t.status === '__mai__') return null;",
          test: ['src/components/mike/MikeP6Blocco1.test.tsx'] },
        { id: 'M3 la tabella ignora l esito (parola comune)', file: 'src/components/trading/EventPnlTable.tsx',
          da: '{lab.statoLabel?.(t) ?? st.label}', a: '{st.label}',
          test: ['src/components/mike/MikeP6Blocco1.test.tsx'] },
        { id: 'M4 cap perdita di nuovo presentato come attivo', file: 'src/lib/mike.ts',
          da: "label: 'Cap perdita per partita % (NON ATTIVO)'", a: "label: 'Cap perdita per partita %'",
          test: ['src/components/mike/MikeP6Blocco1.test.tsx'] },
        { id: 'M5 reentry_max_goals di nuovo massimo 1', file: 'src/lib/mike.ts',
          da: "kind: 'number', step: 1, min: 0, max: 2, hint: '2 = rientra", a: "kind: 'number', step: 1, min: 0, max: 1, hint: '2 = rientra",
          test: ['src/components/mike/MikeP6Blocco1.test.tsx'] },
        { id: 'M6 default reentry_max_goals 1', file: 'src/lib/mike.ts',
          da: 'reentry_max_goals: 2, reentry_until_min', a: 'reentry_max_goals: 1, reentry_until_min',
          test: ['src/components/mike/MikeP6Blocco1.test.tsx'] },
        { id: 'M7 nota dell interruttore tolta', file: 'src/lib/interruttori.ts',
          da: "return { automatiche: usciteMikeDi(params), nota: NOTA_USCITE_MIKE };",
          a: "return { automatiche: usciteMikeDi(params) };",
          test: ['src/components/mike/MikeP6Blocco1.test.tsx', 'src/lib/interruttoriUscite.test.ts'] },
        { id: 'M8 testo vecchio dell interruttore nel pannello', file: 'src/lib/mike.ts',
          da: "hint: 'governa solo le uscite in PERDITA:", a: "hint: 'acceso: green-up, cash out e uscite in perdita li esegue il bot; cap perdita. governa solo le uscite in PERDITA:",
          test: ['src/components/mike/MikeP6Blocco1.test.tsx'] },
    ],
    2: [
        { id: 'E1 si crede allo stato FLAT (niente prova sui conti)', file: 'src/lib/mikeEsitoChiusura.ts',
          da: 'if (peggiore) {', a: 'if (false) {',
          test: ['src/components/controlroom/EsitoChiusuraMike.test.tsx'] },
        { id: 'E2 conti per selezione invece che per mercato', file: 'src/lib/mikeEsitoChiusura.ts',
          da: 'const c = out.get(l.market) ?? { u: 0, o: 0 };', a: 'const c = out.get(l.market + l.selection) ?? { u: 0, o: 0 };',
          test: ['src/components/controlroom/EsitoChiusuraMike.test.tsx'] },
        { id: 'E3 ordini a esito ignoto ignorati', file: 'src/lib/mikeEsitoChiusura.ts',
          da: "const ignoti = legs.filter((l) => l.status === 'pending_reconcile');", a: 'const ignoti: MikeLeg[] = [];',
          test: ['src/components/controlroom/EsitoChiusuraMike.test.tsx'] },
        { id: 'E4 ordini vivi ignorati', file: 'src/lib/mikeEsitoChiusura.ts',
          da: "const vivi = legs.filter((l) => l.status === 'pending');", a: 'const vivi: MikeLeg[] = [];',
          test: ['src/components/controlroom/EsitoChiusuraMike.test.tsx'] },
        { id: 'E5 dati vecchi ignorati', file: 'src/lib/mikeEsitoChiusura.ts',
          da: 'else if (eta > ESITO_DATI_VECCHI_S)', a: 'else if (eta > 1e9)',
          test: ['src/components/controlroom/EsitoChiusuraMike.test.tsx'] },
        { id: 'E6 linea decisa dai gol contata come esposta', file: 'src/lib/mikeEsitoChiusura.ts',
          da: 'if (goals != null && LINEA[m] != null && goals > LINEA[m]) continue;', a: '',
          test: ['src/components/controlroom/EsitoChiusuraMike.test.tsx'] },
        { id: 'E7 tentativi esauriti letti come in corso', file: 'src/lib/mikeEsitoChiusura.ts',
          da: "if (stato === 'LIVE_CLOSING' && tent != null && tent >= max && peggiore)", a: 'if (false && peggiore)',
          test: ['src/components/controlroom/EsitoChiusuraMike.test.tsx'] },
        { id: 'E8 risultato bloccato mancante non segnalato', file: 'src/lib/mikeEsitoChiusura.ts',
          da: "if (bloccato == null) perche.push('il bot non ha ancora pubblicato il risultato bloccato');", a: '',
          test: ['src/components/controlroom/EsitoChiusuraMike.test.tsx'] },
        { id: 'E9 SchedaMike non monta l esito', file: 'src/components/controlroom/SchedaMike.tsx',
          da: '<EsitoChiusuraMike ev={ev} testId={`${testId}-esito-chiusura`} />', a: '',
          test: ['src/components/controlroom/EsitoChiusuraMike.test.tsx'] },
        { id: 'E10 tentativo contato da zero', file: 'src/lib/mikeEsitoChiusura.ts',
          da: 'Math.max(1, tent + 1)', a: 'Math.max(1, tent)',
          test: ['src/components/controlroom/EsitoChiusuraMike.test.tsx'] },
    ],
    3: [
        { id: 'F1 la proposta non ascolta il canale', file: 'src/components/controlroom/PropostaUscitaMike.tsx',
          da: 'useMikeEventoAlMs(evDb, propostaDi(evDb) != null, canaleMike)', a: 'useMikeEventoAlMs(evDb, false, canaleMike)',
          test: ['src/components/mike/useMikeEventoAlMs.test.tsx'] },
        { id: 'F2 push di un altra partita accettato', file: 'src/components/mike/useMikeEventoAlMs.ts',
          da: "|| String(row.event_id ?? '') !== eid) return;", a: ') return;',
          test: ['src/components/mike/useMikeEventoAlMs.test.tsx'] },
        { id: 'F3 push piu vecchio del database vince', file: 'src/components/mike/useMikeEventoAlMs.ts',
          da: '(td != null && td > tp)', a: '(false)',
          test: ['src/components/mike/useMikeEventoAlMs.test.tsx'] },
        { id: 'F4 caduta del canale ignorata', file: 'src/components/mike/useMikeEventoAlMs.ts',
          da: "if (s !== 'connected') setSpinto(null);", a: 'void s;',
          test: ['src/components/mike/useMikeEventoAlMs.test.tsx'] },
        { id: 'F5 cifra mai dichiarata vecchia', file: 'src/components/controlroom/PropostaUscitaMike.tsx',
          da: 'etaCifra > CIFRA_VECCHIA_S', a: 'etaCifra > 1e9',
          test: ['src/components/mike/useMikeEventoAlMs.test.tsx'] },
        { id: 'F6 esito della chiusura senza canale', file: 'src/components/controlroom/EsitoChiusuraMike.tsx',
          da: 'useMikeEventoAlMs(evDb, !terminaleDb, canaleMike)', a: 'useMikeEventoAlMs(evDb, false, canaleMike)',
          test: ['src/components/mike/useMikeEventoAlMs.test.tsx'] },
    ],
    4: [
        { id: 'G1 Mike di nuovo per piazzamento', file: 'src/lib/dailyHistory.ts',
          da: "if (variant === 'mike') return 'settled';", a: '',
          test: ['src/components/trading/StoricoMikeGiornoRegolamento.test.tsx'] },
        { id: 'G2 tutti per regolamento (Omega/Safe cambiati)', file: 'src/lib/dailyHistory.ts',
          da: "if (variant === 'mike') return 'settled';", a: "return 'settled';",
          test: ['src/components/trading/StoricoMikeGiornoRegolamento.test.tsx'] },
        { id: 'G3 testo vecchio del criterio', file: 'src/components/trading/TradingHistory.tsx',
          da: "' P&L realizzato = posizioni REGOLATE nel giorno", a: "' P&L realizzato = trade REGOLATI nel giorno",
          test: ['src/components/trading/StoricoMikeGiornoRegolamento.test.tsx'] },
    ],
    5: [
        { id: 'H1 etichetta vecchia dell ultimo ingresso', file: 'src/lib/mike.ts',
          da: "label: 'Ultimo ingresso a 10 min dal fischio'", a: "label: 'Ultimo ingresso in PERSIST'",
          test: ['src/components/mike/MikeP6Blocco5.test.tsx'] },
        { id: 'H2 tick sopra il best presentato come attivo', file: 'src/lib/mike.ts',
          da: "label: 'Ultimo ingresso: tick sopra il best (NON ATTIVO)'", a: "label: 'Ultimo ingresso: tick sopra il best'",
          test: ['src/components/mike/MikeP6Blocco5.test.tsx'] },
        { id: 'H3 veto che chiude', file: 'src/lib/mike.ts',
          da: "blocca l\\'ultimo ingresso se", a: "all\\'ultimo ingresso il PERSIST si piazza solo se",
          test: ['src/components/mike/MikeP6Blocco5.test.tsx'] },
        { id: 'H4 HOLD vecchio', file: 'src/lib/mike.ts',
          da: "what: 'dopo il segno dei 10 minuti: nessun ingresso fino al fischio; la banca resta appoggiata'",
          a: "what: 'chiudere adesso sarebbe in perdita: tiene l’Under 3.5 e lo porta in gioco'",
          test: ['src/components/mike/MikeP6Blocco5.test.tsx'] },
        { id: 'H5 lettura fallita senza parole', file: 'src/lib/mike.ts',
          da: "lettura_feed_fallita: 'lettura dei dati fallita", a: "lettura_feed_fallita_x: 'lettura dei dati fallita",
          test: ['src/components/mike/MikeP6Blocco5.test.tsx'] },
        { id: 'H6 punteggio assente come linea assente', file: 'src/lib/mike.ts',
          da: "if (p.reason === 'punteggio_assente') return", a: "if (false) return",
          test: ['src/components/mike/MikeP6Blocco5.test.tsx'] },
        { id: 'H7 runner senza esito senza parole', file: 'src/lib/mike.ts',
          da: "runner_senza_esito: 'ordine senza risposta", a: "runner_senza_esito_x: 'ordine senza risposta",
          test: ['src/components/mike/MikeP6Blocco5.test.tsx'] },
        { id: 'H8 nota non determinabile tolta', file: 'src/lib/mike.ts',
          da: "if (m['regolamento'] === 'non_determinabile') return", a: "if (false) return",
          test: ['src/components/mike/MikeP6Blocco5.test.tsx'] },
        { id: 'H9 la tabella non mostra la nota', file: 'src/components/mike/MikeEventPnlTable.tsx',
          da: 'const reg = notaRegolamentoMike(t.meta);', a: 'const reg = null as string | null;',
          test: ['src/components/mike/MikeP6Blocco5.test.tsx'] },
        { id: 'H10 «di 20» finto quando il massimo non e noto', file: 'src/lib/mikeEsitoChiusura.ts',
          da: "const diMax = maxNoto != null ? ` di ${maxNoto}` : '';", a: 'const diMax = ` di ${max}`;',
          test: ['src/components/controlroom/EsitoChiusuraMike.test.tsx', 'src/components/mike/useMikeEventoAlMs.test.tsx'] },
    ],
    6: [
        { id: 'K1 copertura letta dal ruolo (forma indovinata)', file: 'src/lib/mike.ts',
          da: "if (g.role === 'over_cover' && sel && lato) {", a: "if (g.role === 'over_cover') {",
          test: ['src/components/mike/MikeP6Blocco6Copertura.test.tsx'] },
        { id: 'K2 capitale: la banca conta l importo', file: 'src/lib/mike.ts',
          da: 'return Number.isFinite(p) && p > 1 ? s + m * (p - 1) : s;', a: 'return s + m;',
          test: ['src/components/mike/MikeP6Blocco6Copertura.test.tsx'] },
        { id: 'K3 posizioni per selezione (niente mercato)', file: 'src/lib/mike.ts',
          da: 'if (gambeAltra.length) {', a: 'if (false) {',
          test: ['src/components/mike/MikeP6Blocco6Copertura.test.tsx'] },
        { id: 'K4 piatto arrotondato (resto della chiusura)', file: 'src/lib/mike.ts',
          da: 'if (Math.abs(w - l) < 0.01) continue;', a: 'if (Math.abs(Math.round(w * 100) - Math.round(l * 100)) < 0.5) continue;',
          test: ['src/components/mike/MikeP6Blocco6Copertura.test.tsx'] },
        { id: 'K5 tabella col nome del ruolo', file: 'src/components/mike/MikeEventPnlTable.tsx',
          da: 'roleLabelGamba({ role: t.role, side: t.side, selection: t.selection_name })', a: 'roleLabelGamba({ role: t.role })',
          test: ['src/components/mike/MikeP6Blocco6Copertura.test.tsx'] },
        { id: 'K6 attivita cover senza forma', file: 'src/lib/mike.ts',
          da: 'if (g !== roleLabel(\'over_cover\')) return g;', a: 'return g;',
          test: ['src/components/mike/MikeP6Blocco6Copertura.test.tsx'] },
        { id: 'K7 cover_form di serie la forma vecchia', file: 'src/lib/mike.ts',
          da: "cover_form: 'lay_under45', cover_profit_factor", a: "cover_form: 'back_over45', cover_profit_factor",
          test: ['src/components/mike/MikeP6Blocco6Copertura.test.tsx'] },
        { id: 'K8 fase che dice ancora Over 4.5', file: 'src/lib/mike.ts',
          da: "valuta quando coprirsi sulla linea 4.5'", a: "valuta quando comprare l’Over 4.5'",
          test: ['src/components/mike/MikeP6Blocco6Copertura.test.tsx'] },
    ],
};

const blocco = process.argv[2];
const filtro = process.argv[3] ?? '';   // facoltativo: solo le mutazioni il cui id inizia cosi'
const lista = (BLOCCHI[blocco] ?? []).filter((m) => m.id.startsWith(filtro));
if (!lista.length) { console.error('blocco o filtro sconosciuto'); process.exit(2); }
const esiti = [];
for (const m of lista) {
    const orig = readFileSync(m.file, 'utf8');
    const h0 = sha(orig);
    const n = orig.split(m.da).length - 1;
    if (n !== 1) { esiti.push(`${m.id}: NON APPLICABILE (occorrenze ${n})`); continue; }
    let codice = null;
    try {
        writeFileSync(m.file, orig.replace(m.da, m.a), 'utf8');
        const r = spawnSync('npx', ['vitest', 'run', ...m.test], { encoding: 'utf8', shell: true });
        codice = r.status;
        const riga = (r.stdout.match(/Tests\s+[^\n]*/) ?? ['?'])[0];
        esiti.push(`${m.id}: ${codice === 0 ? 'VERDE (mutazione NON presa!)' : 'ROSSO'} - ${riga.trim()}`);
    } finally {
        writeFileSync(m.file, orig, 'utf8');
        const h1 = sha(readFileSync(m.file, 'utf8'));
        if (h1 !== h0) { esiti.push(`${m.id}: RIPRISTINO FALLITO`); }
    }
}
console.log(esiti.join('\n'));
