// ============================================================================
// AvvisoCoerenzaBarra - avviso DISCRETO di Match Replay: se il verificatore trova
// incoerenze fra barra, simboli e tabellone della partita aperta, la pagina lo dice e
// ne elenca i motivi; se e' tutto coerente non mostra NIENTE.
//
// Ordine dell'utente (07/10/2026): la coerenza barra / simboli / tabellone e' uno
// standard per tutte le partite, presenti e future. Per le partite GIA' caricate la
// certificazione la fa `scripts/verifica_barra_replay.ts`; questo avviso copre quelle
// FUTURE: appena un replay con una barra che non torna viene aperto, il trader lo vede
// (e sa quali simboli o quale punteggio non fidarsi di) invece di scoprirlo da solo.
//
// Le NOTE del verificatore (buchi della registrazione, correzioni VAR, sospensioni
// troppo brevi per essere disegnate) NON sono incoerenze e qui non compaiono.
// ============================================================================
import { useMemo } from 'react';
import { AlertTriangle } from 'lucide-react';
import type { ReplayData } from '@/lib/live';
import type { Snapshot } from '@/lib/opportunities/types';
import type { EsitoVerificaBarra, EstremiRegistrazione, Rilievo } from '@/lib/replayVerificaBarra';
import { oraUtc } from '@/lib/replayVerificaBarra';
import { verificaBarraReplayCalcio } from '@/lib/replayVerificaBarraCalcio';

export interface AvvisoCoerenzaBarraProps {
    /** la partita aperta (null = nessuna: l'avviso non compare) */
    replay: ReplayData | null;
    /** snapshot del motore opportunita' gia' calcolati dalla pagina (evita di rifarli) */
    snapshots?: ReadonlyArray<Snapshot> | null;
    /** estremi di `get_replay_meta`, se la pagina li ha */
    estremi?: EstremiRegistrazione | null;
    /** quante segnalazioni elencare prima del "e altre N" */
    massimo?: number;
    /** il verificatore dello sport (default: calcio); il tennis passa il suo */
    verifica?: (replay: ReplayData, opzioni: { snapshots: ReadonlyArray<Snapshot> | null; estremi: EstremiRegistrazione | null }) => EsitoVerificaBarra;
}

function dove(r: Rilievo): string {
    return [
        r.passo != null ? `passo ${r.passo}` : null,
        r.istante ? oraUtc(r.istante) : null,
        r.minuto != null ? `${r.minuto}'` : null,
    ].filter(Boolean).join(' - ');
}

export function AvvisoCoerenzaBarra({ replay, snapshots = null, estremi = null, massimo = 8, verifica = verificaBarraReplayCalcio }: AvvisoCoerenzaBarraProps) {
    const esito: EsitoVerificaBarra | null = useMemo(() => {
        if (!replay || !replay.frames || replay.frames.length === 0) return null;
        try {
            return verifica(replay, { snapshots, estremi });
        } catch (e) {
            // il controllo non deve mai rompere la pagina
            console.warn('[AvvisoCoerenzaBarra] verifica non eseguibile:', e);
            return null;
        }
    }, [replay, snapshots, estremi, verifica]);

    if (!esito || esito.ok) return null;
    const elenco = esito.incoerenze.slice(0, massimo);
    const altre = esito.incoerenze.length - elenco.length;

    return (
        <details
            data-testid="avviso-coerenza-barra"
            className="rounded-xl border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-[11px] text-white/80"
        >
            <summary className="cursor-pointer flex items-center gap-2 font-bold text-amber-200 select-none">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>
                    Controllo coerenza della barra: {esito.incoerenze.length} {esito.incoerenze.length === 1 ? 'segnalazione' : 'segnalazioni'}
                </span>
                <span className="font-normal text-white/60">(tocca per leggerle)</span>
            </summary>
            <p className="mt-2 text-white/70">
                Barra, simboli o tabellone di questa partita non tornano del tutto con i dati registrati. I prezzi mostrati
                restano quelli registrati; prima di fidarti dei punti elencati controlla la partita.
            </p>
            <ul className="mt-2 space-y-1.5">
                {elenco.map((r, i) => (
                    <li key={`${r.codice}-${i}`} data-testid="avviso-coerenza-voce" className="flex flex-col gap-0.5 rounded-lg bg-black/30 px-2 py-1.5">
                        <span className="flex items-center gap-2 flex-wrap">
                            <span
                                className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-black ${
                                    r.gravita === 'errore' ? 'bg-red-500/25 text-red-200' : 'bg-amber-500/25 text-amber-200'
                                }`}
                            >
                                {r.codice}
                            </span>
                            {dove(r) && <span className="tabular-nums text-white/50">{dove(r)}</span>}
                            {r.occorrenze > 1 && <span className="text-white/50">(x{r.occorrenze})</span>}
                        </span>
                        <span>{r.spiegazione}</span>
                        {/* 08/10 (cantiere 13): incoerenza dei DATI registrati (classe c), dichiarata con il motivo */}
                        {r.perDati && (
                            <span data-testid="avviso-coerenza-per-dati" className="text-white/60">
                                <span className="font-bold text-amber-200/80">Dato registrato, non errore della pagina:</span> {r.perDati}
                            </span>
                        )}
                    </li>
                ))}
            </ul>
            {altre > 0 && <p data-testid="avviso-coerenza-altre" className="mt-1 text-white/50">... e altre {altre} {altre === 1 ? 'segnalazione' : 'segnalazioni'}.</p>}
        </details>
    );
}
