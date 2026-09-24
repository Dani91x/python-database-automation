// ============================================================================
// ObiettivoHero.tsx — ZONA 1 «L'OBIETTIVO» (Task 1/2, 18/09).
//
// Un concetto, una rappresentazione (checklist A5 §3.3 regola 1): l'obiettivo
// vive qui, UNA volta sola nella pagina. Contiene:
//   · l'intestazione con l'obiettivo MODIFICABILE (`ObiettivoEditor`);
//   · la `DayBar` già certificata, INVARIATA (nessuna modifica a
//     `components/trading/DayBar.tsx`: qui si aggiunge, non si tocca);
//   · la scomposizione di ciò che erode l'obiettivo (Task 2), sotto, sempre
//     SOLO soldi veri; il paper resta su una riga separata, mai sommato.
// ============================================================================
import { Target } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { DayBar, type DayBarProps } from '@/components/trading/DayBar';
import { ObiettivoEditor } from './ObiettivoEditor';
import { fmtMoney, DASH } from '@/lib/format';
import { pnlClass } from '@/lib/tradeStatus';
import type { ComposizioneObiettivo } from '@/lib/composizioneObiettivo';
import type { ManualeSitoBetfair } from '@/lib/manualeSitoBetfair';

export interface ObiettivoHeroProps {
    dayBar: DayBarProps;
    composizione: ComposizioneObiettivo;
    manualeSito: ManualeSitoBetfair;
    onSalvaObiettivo: (valore: number) => Promise<void>;
    /** avviso onesto: Omega in corsa → il target del servizio cambia subito */
    avvisoMotore?: string | null;
    testId?: string;
}

export function ObiettivoHero({
    dayBar, composizione, manualeSito, onSalvaObiettivo, avvisoMotore, testId = 'cr-obiettivo',
}: ObiettivoHeroProps) {
    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid={testId}>
            <div className="px-4 pt-3 flex items-center gap-2">
                <Target className="w-4 h-4 text-secondary" aria-hidden />
                <span className="text-[13px] text-white/85">Obiettivo di oggi</span>
                <ObiettivoEditor
                    valoreAttuale={dayBar.goal ?? null}
                    onSalva={onSalvaObiettivo}
                    avvisoMotore={avvisoMotore}
                    testId="cr-obiettivo-editor"
                />
            </div>

            <div className="px-2 pt-1">
                <DayBar {...dayBar} testId="cr-giornata" />
            </div>

            <div className="px-4 pb-3 pt-1" data-testid="cr-composizione">
                <div className="text-[10px] uppercase tracking-wider text-white/40 mb-1.5">
                    composizione — solo soldi veri, entra nell&apos;obiettivo
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-5 gap-y-0.5">
                    {composizione.righe.map((r) => (
                        <div
                            key={r.chiave}
                            className="flex items-baseline justify-between text-[11.5px] py-0.5 border-b border-dashed border-white/5"
                            data-testid={`cr-composizione-${r.chiave}`}
                        >
                            <span className="text-white/55">{r.etichetta}</span>
                            <span className={`font-mono ${r.valore == null ? 'text-white/30' : pnlClass(r.valore)}`}>
                                {r.valore == null ? DASH : fmtMoney(r.valore, { signed: true })}
                                {/* 24/09 - la parte non ancora regolata da Betfair si DICHIARA */}
                                {r.valore != null && r.stimato != null && (
                                    <span className="text-amber-300/70 text-[10px] ml-1"
                                        data-testid={`cr-composizione-${r.chiave}-stimato`}
                                        title="calcolo del bot: Betfair non ha ancora regolato">
                                        {r.stimato === r.valore ? 'stimato' : `di cui stimato ${fmtMoney(r.stimato, { signed: true })}`}
                                    </span>
                                )}
                            </span>
                        </div>
                    ))}
                </div>

                {/* SITO BETFAIR — punto d'aggancio isolato (Task 2b): oggi
                    sempre assente, mai un contributo alla somma. */}
                {manualeSito.fonte === 'non-disponibile' && (
                    <div className="text-[10px] text-white/30 mt-1" data-testid="cr-manuale-sito-assente">
                        scommesse dal sito Betfair (fuori app): {DASH} — in arrivo, non ancora collegate
                    </div>
                )}

                {composizione.provaPaper != null && (
                    <div
                        className="mt-1.5 pt-1.5 border-t border-white/10 flex items-baseline gap-2 text-[11px] text-white/40"
                        data-testid="cr-composizione-prova"
                    >
                        <span className="uppercase tracking-wider text-[9.5px] px-1.5 py-0.5 rounded bg-white/10">in prova</span>
                        <span className={pnlClass(composizione.provaPaper)}>
                            {fmtMoney(composizione.provaPaper, { signed: true })}
                        </span>
                        <span className="text-white/25">— mai sommato all&apos;obiettivo</span>
                    </div>
                )}
            </div>
        </Card>
    );
}

export default ObiettivoHero;
