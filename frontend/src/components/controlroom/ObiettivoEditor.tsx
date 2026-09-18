// ============================================================================
// ObiettivoEditor.tsx — modifica IN LINEA dell'obiettivo di giornata (Task 2).
//
// Pattern bozza + conferma: matita → campo → conferma/annulla. MAI un
// salvataggio a ogni tasto (regola esplicita dell'utente): il valore parte
// solo al clic su "conferma", validato da `lib/obiettivoEditor.ts`.
//
// L'AVVISO SUL MOTORE non si nasconde: cambiare l'obiettivo mentre Omega gira
// cambia SUBITO il target per partita che il servizio calcola
// (`omega_service.py`: `goal = control.get('daily_goal')`, letto a ogni
// ciclo) — non è un dettaglio estetico, è un parametro vivo della strategia.
// ============================================================================
import { useState } from 'react';
import { Pencil, Check, X } from 'lucide-react';
import { validaObiettivo } from '@/lib/obiettivoEditor';
import { fmtMoney } from '@/lib/format';

export interface ObiettivoEditorProps {
    /** valore corrente (già in vigore sul servizio), null = ignoto */
    valoreAttuale: number | null;
    /** scrive l'obiettivo nuovo (RPC `omega_update_params`, via `lib/omega.ts`) */
    onSalva: (valore: number) => Promise<void>;
    /** avviso onesto quando cambiare l'obiettivo ha un effetto immediato sul
     *  motore (Omega in corsa): null/undefined = nessun avviso da mostrare */
    avvisoMotore?: string | null;
    testId?: string;
}

export function ObiettivoEditor({
    valoreAttuale, onSalva, avvisoMotore, testId = 'obiettivo-editor',
}: ObiettivoEditorProps) {
    const [editando, setEditando] = useState(false);
    const [bozza, setBozza] = useState('');
    const [errore, setErrore] = useState<string | null>(null);
    const [salvando, setSalvando] = useState(false);

    const apri = () => {
        setBozza(valoreAttuale != null ? String(valoreAttuale).replace('.', ',') : '');
        setErrore(null);
        setEditando(true);
    };
    const annulla = () => { setEditando(false); setErrore(null); setSalvando(false); };

    const conferma = async () => {
        const v = validaObiettivo(bozza);
        if (!v.ok || v.valore == null) { setErrore(v.errore); return; }
        setErrore(null);
        setSalvando(true);
        try {
            await onSalva(v.valore);
            setEditando(false);
        } catch (e) {
            setErrore(e instanceof Error ? e.message : String(e));
        } finally {
            setSalvando(false);
        }
    };

    if (!editando) {
        return (
            <button
                type="button"
                onClick={apri}
                title="modifica l'obiettivo di oggi"
                data-testid={`${testId}-matita`}
                className="text-white/35 hover:text-secondary transition-colors p-0.5 rounded"
            >
                <Pencil className="w-3.5 h-3.5" aria-hidden />
                <span className="sr-only">Modifica l&apos;obiettivo di oggi</span>
            </button>
        );
    }

    return (
        <div className="inline-flex items-center gap-1.5 flex-wrap" data-testid={testId}>
            <span className="text-[11px] text-white/50">obiettivo</span>
            <input
                type="text"
                inputMode="decimal"
                value={bozza}
                autoFocus
                onChange={(e) => setBozza(e.target.value)}
                onKeyDown={(e) => {
                    if (e.key === 'Enter') void conferma();
                    if (e.key === 'Escape') annulla();
                }}
                disabled={salvando}
                data-testid={`${testId}-input`}
                className="w-24 px-1.5 py-0.5 rounded border border-white/15 bg-white/5 font-mono text-right text-white/90 text-xs"
                aria-label="Nuovo obiettivo di oggi, in euro"
            />
            <button
                type="button"
                onClick={() => void conferma()}
                disabled={salvando}
                data-testid={`${testId}-conferma`}
                className="text-emerald-400 hover:text-emerald-300 disabled:opacity-40 p-0.5"
                title="conferma"
            >
                <Check className="w-3.5 h-3.5" aria-hidden />
            </button>
            <button
                type="button"
                onClick={annulla}
                disabled={salvando}
                data-testid={`${testId}-annulla`}
                className="text-white/40 hover:text-white/70 disabled:opacity-40 p-0.5"
                title="annulla"
            >
                <X className="w-3.5 h-3.5" aria-hidden />
            </button>
            {errore && (
                <span className="basis-full text-[10.5px] text-red-300" data-testid={`${testId}-errore`}>
                    {errore}
                </span>
            )}
            {!errore && avvisoMotore && (
                <span className="basis-full text-[10.5px] text-amber-300" data-testid={`${testId}-avviso`}>
                    {avvisoMotore}
                </span>
            )}
            {valoreAttuale != null && (
                <span className="basis-full text-[9.5px] text-white/30">
                    oggi in vigore: {fmtMoney(valoreAttuale)}
                </span>
            )}
        </div>
    );
}

export default ObiettivoEditor;
