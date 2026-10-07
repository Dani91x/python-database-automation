// ============================================================================
// replayVerificaBarraTesto - il REFERTO in testo di una verifica della barra
// (comune a calcio e tennis): una riga di esito per partita, poi i rilievi con
// codice, passo, istante, minuto e spiegazione. Lo stampano lo script
// `frontend/scripts/verifica_barra_replay.ts` e i test (messaggio di errore).
// ============================================================================
import { oraUtc, type EsitoVerificaBarra, type Rilievo } from '@/lib/replayVerificaBarra';

const ETICHETTA: Record<Rilievo['gravita'], string> = { errore: 'ERRORE', avviso: 'AVVISO', nota: 'nota  ' };

export function rigaRilievo(r: Rilievo): string {
    const dove = [
        r.passo != null ? `passo ${r.passo}` : null,
        r.istante ? oraUtc(r.istante) : null,
        r.minuto != null ? `${r.minuto}'` : null,
    ].filter(Boolean).join(', ');
    const molte = r.occorrenze > 1 ? ` (x${r.occorrenze})` : '';
    return `  [${ETICHETTA[r.gravita]}] ${r.codice}${dove ? ` (${dove})` : ''}${molte}: ${r.spiegazione}`;
}

export function esitoInUnaRiga(titolo: string, e: EsitoVerificaBarra): string {
    const sim = Object.entries(e.conteggi.simboli).map(([k, v]) => `${k} ${v}`).join(', ') || 'nessuno';
    return `${e.ok ? 'OK    ' : 'INCOERENTE'} ${titolo}: ${e.incoerenze.length} incoerenze, ${e.note.length} note | `
        + `passi ${e.conteggi.passi}, frame ${e.conteggi.frames}, simboli [${sim}], righe punteggio ${e.conteggi.righePunteggio}, righe evento ${e.conteggi.righeEvento}, buchi ${e.conteggi.buchi}`;
}

/** Referto completo di una partita. `conNote` = elenca anche le note (buchi, VAR, ...). */
export function formattaReferto(titolo: string, e: EsitoVerificaBarra, conNote = true): string {
    const righe = [esitoInUnaRiga(titolo, e)];
    for (const r of e.rilievi) {
        if (r.gravita === 'nota' && !conNote) continue;
        righe.push(rigaRilievo(r));
    }
    return righe.join('\n');
}
