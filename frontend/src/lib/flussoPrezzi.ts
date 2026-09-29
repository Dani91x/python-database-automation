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
