// Cantiere J (28/09/2026) — i PREZZI di una partita sono VIVI?
//
// Il segnale lo scrive lo scanner (`Betfair/safe_strategy/service.py`,
// `flusso_evento`) nella riga di `safe_strategy_scan`, chiave `payload.flusso`,
// e lo definisce `Betfair/stream/flusso_prezzi.py`. Qui SOLO la lettura per la
// pagina: nessuna soglia duplicata (le decide lo scanner), nessun calcolo.
//
// Regola di presentazione (contratto del referto, §5):
//  · vivo=false e motivo flusso_interrotto | stream_latente | mai_ricevuto →
//    «FLUSSO PREZZI INTERROTTO da …», rosso, accanto ai prezzi;
//  · senza_prezzi → «senza prezzi / sospeso», ambra;
//  · chiave assente → «non dichiarato» (scanner vecchio), nessun badge rosso.

export type MotivoFlusso =
    | 'flusso_interrotto'
    | 'mai_ricevuto'
    | 'senza_prezzi'
    | 'stream_latente';

/** Il blocco `payload.flusso` come lo scrive lo scanner (stesse chiavi e tipi). */
export interface FlussoRiga {
    vivo: boolean;
    motivo: MotivoFlusso | null;
    /** epoch ms del passaggio allo stato attuale */
    dal_ms: number;
    /** altri mercati APERTI della riga col flusso fermo (cs, ht, linee) */
    mercati_fermi: string[];
}

export type StatoFlusso = 'vivo' | 'interrotto' | 'senza_prezzi' | 'non_dichiarato';

export interface GiudizioFlusso {
    stato: StatoFlusso;
    /** secondi dal passaggio allo stato attuale; null = non noto */
    daS: number | null;
    /** mercati diversi dal Match Odds fermi (visibili anche a MO vivo) */
    mercatiFermi: number;
    testo: string;
    motivo: MotivoFlusso | null;
}

const MOTIVO_IT: Record<MotivoFlusso, string> = {
    flusso_interrotto: 'nessun dato ricevuto da Betfair',
    mai_ricevuto: 'prezzi mai ricevuti',
    senza_prezzi: 'mercato senza prezzi o sospeso',
    stream_latente: 'Betfair in latenza (503)',
};

function eFlussoRiga(v: unknown): v is FlussoRiga {
    if (!v || typeof v !== 'object') return false;
    const o = v as Record<string, unknown>;
    return typeof o.vivo === 'boolean';
}

function durata(s: number): string {
    if (s < 60) return `${Math.round(s)} s`;
    if (s < 3600) return `${Math.floor(s / 60)} min`;
    const h = Math.floor(s / 3600);
    return `${h} h ${Math.floor((s - h * 3600) / 60)} min`;
}

/** Il giudizio per la pagina. `flusso` e' il blocco della riga (o assente). */
export function giudizioFlusso(flusso: unknown, nowMs: number): GiudizioFlusso {
    if (!eFlussoRiga(flusso)) {
        return { stato: 'non_dichiarato', daS: null, mercatiFermi: 0, motivo: null,
            testo: 'flusso prezzi non dichiarato dallo scanner' };
    }
    const daS = typeof flusso.dal_ms === 'number' && Number.isFinite(flusso.dal_ms) && flusso.dal_ms > 0
        ? Math.max(0, (nowMs - flusso.dal_ms) / 1000) : null;
    const mercatiFermi = Array.isArray(flusso.mercati_fermi) ? flusso.mercati_fermi.length : 0;
    if (flusso.vivo) {
        return { stato: 'vivo', daS, mercatiFermi, motivo: null,
            testo: mercatiFermi > 0
                ? `prezzi vivi sul Match Odds; ${mercatiFermi} mercati col flusso fermo`
                : 'prezzi vivi' };
    }
    const motivo = flusso.motivo ?? 'flusso_interrotto';
    const quanto = daS == null ? '' : ` da ${durata(daS)}`;
    if (motivo === 'senza_prezzi') {
        return { stato: 'senza_prezzi', daS, mercatiFermi, motivo,
            testo: `SENZA PREZZI${quanto}: ${MOTIVO_IT.senza_prezzi}` };
    }
    return { stato: 'interrotto', daS, mercatiFermi, motivo,
        testo: `FLUSSO PREZZI INTERROTTO${quanto}: ${MOTIVO_IT[motivo] ?? motivo}. `
            + 'Nessun bot apre né chiude a mercato su questi prezzi.' };
}

// ---------------------------------------------------------------------------
// 30/09 — IL FLUSSO DELLE LINEE DI MIKE (Under/Over 3,5 e 4,5).
//
// `flusso.vivo`/`motivo`/`dal_ms` riguardano il MATCH ODDS: prima del fischio
// lo scanner non lo segue (motivo `mai_ricevuto`, contatore dalla creazione
// della riga) mentre le linee di Mike arrivano al secondo. Mike giudica il SUO
// flusso così (`Betfair/mike/feed.py::flusso_esito` + `mercati_di_mike`): le
// linee 3,5 e 4,5 della riga ANCORA IN GIOCO (gol <= linea) che lo scanner
// elenca in `flusso.mercati_fermi`. Qui la STESSA regola, in sola lettura,
// senza soglie nuove. Il "da quanto" è l'età dell'ultimo book RICEVUTO della
// linea (`seen_ms` del blocco `ou`), come nel diario di Mike
// (`feed.linee_ferme_mike`). Lo STATO dello scanner (giro bloccato) non è
// nella riga: la scheda non lo vede (lo dice il diario di Mike).
// ---------------------------------------------------------------------------

/** Un blocco `ou` della riga come lo scrive lo scanner (solo le chiavi lette qui). */
export interface BloccoOuRiga {
    market_id?: string | null;
    line?: number | null;
    status?: string | null;
    /** epoch ms dell'ultimo book RICEVUTO per questa linea */
    seen_ms?: number | null;
}

/** Il minimo della riga che serve al giudizio delle linee di Mike. */
export interface RigaLineeMike {
    ou?: BloccoOuRiga[] | null;
    flusso?: FlussoRiga | null;
    score_home?: number | null;
    score_away?: number | null;
}

export interface LineaFermaMike {
    marketId: string;
    /** «Under/Over 3,5» */
    nome: string;
    /** secondi dall'ultimo prezzo ricevuto (se `esatto`) o dall'ultima scrittura della riga; null = la riga non lo dice */
    daS: number | null;
    /** true = da `flusso.fermi_da_ms` (istante vero); false = ripiego su `seen_ms` (eta' della riga) */
    esatto: boolean;
}

export interface GiudizioFlussoMike {
    /** `senza_linee`: la riga non porta linee 3,5/4,5 ancora in gioco */
    stato: 'vivo' | 'fermo' | 'non_dichiarato' | 'senza_linee';
    linee: LineaFermaMike[];
    testo: string;
}

const LINEE_MIKE: Record<string, string> = { '3.5': 'Under/Over 3,5', '4.5': 'Under/Over 4,5' };

/** Le linee di Mike ancora in gioco (stessa regola di `feed.mercati_di_mike`). */
function lineeInGioco(riga: RigaLineeMike): { marketId: string; nome: string; seenMs: number | null }[] {
    const h = riga.score_home, a = riga.score_away;
    const gol = h == null || a == null || !Number.isFinite(Number(h)) || !Number.isFinite(Number(a))
        ? null : Math.trunc(Number(h)) + Math.trunc(Number(a));
    const out: { marketId: string; nome: string; seenMs: number | null }[] = [];
    for (const b of Array.isArray(riga.ou) ? riga.ou : []) {
        if (!b || typeof b !== 'object' || !b.market_id) continue;
        const linea = Number(b.line);
        const nome = LINEE_MIKE[String(linea)];
        if (b.line == null || !nome) continue;
        if (gol != null && gol > linea) continue;          // linea gia' decisa dai gol
        const seen = typeof b.seen_ms === 'number' && Number.isFinite(b.seen_ms) && b.seen_ms > 0
            ? b.seen_ms : null;
        out.push({ marketId: String(b.market_id), nome, seenMs: seen });
    }
    return out;
}

/** Il giudizio del flusso delle LINEE DI MIKE di questa riga. */
export function giudizioFlussoMike(riga: RigaLineeMike | null | undefined, nowMs: number): GiudizioFlussoMike {
    const linee = riga ? lineeInGioco(riga) : [];
    if (!linee.length) return { stato: 'senza_linee', linee: [], testo: '' };
    const flusso: unknown = riga?.flusso;
    if (!eFlussoRiga(flusso)) {
        return { stato: 'non_dichiarato', linee: [], testo: 'flusso prezzi non dichiarato dallo scanner' };
    }
    const fermi = new Set((Array.isArray(flusso.mercati_fermi) ? flusso.mercati_fermi : []).map(String));
    // 30/09 sera: «da quanto» VERO = `flusso.fermi_da_ms[market_id]` (istante
    // dell'ultima conferma con prezzi, scritto dallo scanner quando la linea
    // diventa ferma). `seen_ms` e' fuori firma: la riga non si riscrive se cambia
    // solo lui, quindi da solo sovrastima l'eta'. Resta come ripiego (scanner
    // precedente) e in quel caso si dice «riga scritta», non «ultimo book».
    const daMs = (flusso as { fermi_da_ms?: unknown }).fermi_da_ms;
    const fermiDa: Record<string, number> = daMs && typeof daMs === 'object' ? daMs as Record<string, number> : {};
    const ferme: LineaFermaMike[] = linee
        .filter((l) => fermi.has(l.marketId))
        .map((l) => {
            const da = fermiDa[l.marketId];
            const esatto = typeof da === 'number' && Number.isFinite(da) && da > 0;
            const rif = esatto ? da : l.seenMs;
            return { marketId: l.marketId, nome: l.nome, esatto,
                daS: rif == null ? null : Math.max(0, (nowMs - rif) / 1000) };
        });
    if (!ferme.length) return { stato: 'vivo', linee: [], testo: 'prezzi vivi sulle linee di Mike' };
    const parti = ferme.map((l) => `${l.nome} (${l.marketId}) ferma`
        + (l.daS == null ? '' : (l.esatto ? `, ultimo prezzo ricevuto ${durata(l.daS)} fa`
            : `, riga scritta ${durata(l.daS)} fa`)));
    return { stato: 'fermo', linee: ferme,
        testo: `Flusso prezzi fermo per lo scanner: ${parti.join('; ')}. `
            + 'Mike non apre su queste linee; con una posizione aperta chiude o copre solo '
            + 'sui prezzi letti da Betfair (ripiego REST).' };
}

/** Il Match Odds PRIMA del fischio non ancora ricevuto: non è un flusso
 *  interrotto (lo scanner lo segue solo in gioco o negli ultimi 20 minuti). */
export function moNonAncoraRicevuto(g: GiudizioFlusso | null | undefined): boolean {
    return g?.stato === 'interrotto' && g.motivo === 'mai_ricevuto';
}
