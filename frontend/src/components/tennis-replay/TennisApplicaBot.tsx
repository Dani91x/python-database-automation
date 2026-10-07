// ============================================================================
// TennisApplicaBot — la sezione «Applica bot» del Replay Tennis (SOLO bot tennis).
//
// FASE 1 (07/10): struttura pronta, comandi SPENTI con la ragione a schermo. Il
// backend comune (punto d'ingresso unico del banco con `parametri` e `dal_ms`,
// catalogo dei bot per il frontend, pannello Parametri e «accendi all'istante
// del cursore») lo sta costruendo un altro cantiere: quando e' integrato questa
// sezione si collega ai suoi componenti filtrati allo sport tennis (FASE 2).
// Calcio e tennis non si mischiano: qui ci sono solo i bot del tennis.
// ============================================================================
import { useState } from 'react';
import { Bot, SlidersHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { TENNIS_BOT_REGISTRY } from '@/lib/tennis';

/** I bot tennis che il banco certifica (registro del banco): i quattro del
 *  runner tennis e la Safe Strategy sul tennis. */
export const BOT_TENNIS_REPLAY: ReadonlyArray<{ key: string; nome: string }> = [
    ...TENNIS_BOT_REGISTRY.map(b => ({ key: b.key as string, nome: b.name })),
    { key: 'safe_tennis', nome: 'Safe Strategy · Tennis' },
];

export const MOTIVO_FASE_1 =
    'In arrivo: il banco comune con parametri e accensione al cursore e\' in costruzione '
    + '(altro cantiere). La sezione si collega quando e\' integrato.';

export function TennisApplicaBot({ istante }: { istante: string }) {
    const [bot, setBot] = useState('');
    return (
        <div className="rounded-xl border border-amber-400/40 bg-amber-500/10 px-3 py-2 space-y-2 text-[11px]"
            data-testid="tennis-applica-bot">
            <div className="flex items-center gap-2 flex-wrap">
                <span className="font-black text-amber-200 inline-flex items-center gap-1">
                    <Bot className="w-3.5 h-3.5" /> Applica bot · tennis
                </span>
                <select
                    value={bot}
                    onChange={e => setBot(e.target.value)}
                    aria-label="Bot tennis da applicare al replay"
                    style={{ colorScheme: 'dark' }}
                    className="px-2 py-1 rounded-md bg-black/40 border border-white/15 text-white text-[11px]"
                >
                    <option value="" className="bg-neutral-900 text-white">— scegli un bot tennis —</option>
                    {BOT_TENNIS_REPLAY.map(b => (
                        <option key={b.key} value={b.key} className="bg-neutral-900 text-white">{b.nome}</option>
                    ))}
                </select>
                <select
                    disabled
                    aria-label="Scenario del banco"
                    style={{ colorScheme: 'dark' }}
                    className="px-2 py-1 rounded-md bg-black/40 border border-white/15 text-white/50 text-[11px]"
                >
                    <option className="bg-neutral-900 text-white">scenario del banco</option>
                </select>
                <Button size="sm" variant="outline" disabled
                    className="h-7 border-amber-300/40 text-amber-100 text-[11px] font-bold" title={MOTIVO_FASE_1}>
                    <SlidersHorizontal className="w-3.5 h-3.5 mr-1" /> Parametri
                </Button>
                <Button size="sm" variant="outline" disabled
                    className="h-7 border-amber-300/40 text-amber-100 text-[11px] font-bold" title={MOTIVO_FASE_1}>
                    Accendi all&apos;istante del cursore{istante ? ` (${istante})` : ''}
                </Button>
            </div>
            <p className="text-white/70" data-testid="tennis-applica-bot-motivo">{MOTIVO_FASE_1}</p>
        </div>
    );
}

export default TennisApplicaBot;
