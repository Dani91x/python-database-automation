// ============================================================================
// SectionFilter — mostra/nascondi le sezioni di una lista di partite.
//
// Richiesta dell'utente (13/09): nella scheda «Partite» servono due interruttori
// per nascondere PRE-MATCH e LIVE. Con molte partite seguite la sezione che
// interessa finiva sotto la piega e bisognava scorrere ogni volta.
//
// Regole di comportamento:
//  · la scelta SOPRAVVIVE al ricaricamento (localStorage, per chiave/sezione):
//    chi lavora solo sul live non deve rifare il clic a ogni refresh;
//  · il CONTEGGIO resta visibile anche a sezione nascosta — nascondere non deve
//    far credere che non ci sia niente;
//  · non si possono spegnere TUTTE le sezioni: l'ultima accesa non si spegne,
//    altrimenti la pagina resta vuota senza spiegazione;
//  · `localStorage` puo' lanciare (finestra privata, storage pieno): ogni
//    accesso e' protetto e in caso di errore si parte da "tutte visibili".
// ============================================================================
import { useCallback, useEffect, useState } from 'react';

export interface SectionOption {
    /** id stabile: entra nella chiave di localStorage, non cambiarlo alla leggera */
    id: string;
    /** etichetta mostrata sul bottone (senza il conteggio) */
    label: string;
    /** quante partite ci sono in questa sezione: mostrato SEMPRE, anche se nascosta */
    count: number;
    /** classi del bottone quando la sezione e' VISIBILE (colore della sezione) */
    activeCls: string;
}

/** Legge le sezioni nascoste salvate. Mai lanciare: storage inaccessibile = nessuna. */
export function readHidden(storageKey: string): Set<string> {
    try {
        const raw = window.localStorage.getItem(storageKey);
        if (!raw) return new Set();
        const parsed: unknown = JSON.parse(raw);
        return Array.isArray(parsed) ? new Set(parsed.map(String)) : new Set();
    } catch {
        return new Set();
    }
}

function writeHidden(storageKey: string, hidden: Set<string>): void {
    try {
        window.localStorage.setItem(storageKey, JSON.stringify([...hidden]));
    } catch {
        /* storage non disponibile: la scelta vale per questa sessione e basta */
    }
}

/**
 * Stato dei filtri + funzione per invertire una sezione.
 * `isVisible(id)` e' quello che la pagina usa per decidere se disegnare la sezione.
 */
export function useSectionFilter(storageKey: string, ids: readonly string[]) {
    const [hidden, setHidden] = useState<Set<string>>(() => readHidden(storageKey));

    // una sezione rimossa dal codice non deve restare "nascosta" per sempre
    useEffect(() => {
        setHidden((prev) => {
            const valide = new Set([...prev].filter((id) => ids.includes(id)));
            return valide.size === prev.size ? prev : valide;
        });
    }, [ids]);

    const toggle = useCallback((id: string) => {
        setHidden((prev) => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            } else {
                // mai spegnere l'ultima sezione accesa: la pagina resterebbe vuota
                if (ids.filter((x) => !next.has(x)).length <= 1) return prev;
                next.add(id);
            }
            writeHidden(storageKey, next);
            return next;
        });
    }, [ids, storageKey]);

    const isVisible = useCallback((id: string) => !hidden.has(id), [hidden]);
    return { hidden, toggle, isVisible };
}

export interface SectionFilterProps {
    options: readonly SectionOption[];
    hidden: Set<string>;
    onToggle: (id: string) => void;
    testId?: string;
}

export function SectionFilter({ options, hidden, onToggle, testId = 'section-filter' }: SectionFilterProps) {
    const visibili = options.filter((o) => !hidden.has(o.id)).length;
    return (
        <div className="flex flex-wrap items-center gap-1.5" data-testid={testId}>
            <span className="text-[10px] uppercase tracking-wide text-slate-500 mr-0.5">mostra</span>
            {options.map((o) => {
                const visibile = !hidden.has(o.id);
                const ultima = visibile && visibili <= 1;
                return (
                    <button
                        key={o.id}
                        type="button"
                        onClick={() => onToggle(o.id)}
                        disabled={ultima}
                        aria-pressed={visibile}
                        data-testid={`${testId}-${o.id}`}
                        data-visible={visibile ? 'true' : 'false'}
                        title={ultima
                            ? 'È l’ultima sezione visibile: non si può nascondere anche questa'
                            : visibile ? `Nascondi ${o.label}` : `Mostra ${o.label}`}
                        className={`px-2 py-0.5 rounded-md border text-[11px] font-heading transition-colors ${
                            visibile ? o.activeCls : 'bg-white/5 text-slate-500 border-white/10 line-through'
                        } ${ultima ? 'cursor-not-allowed opacity-70' : 'hover:brightness-125'}`}
                    >
                        {o.label} ({Number.isFinite(Number(o.count)) ? Number(o.count) : '—'})
                    </button>
                );
            })}
        </div>
    );
}
