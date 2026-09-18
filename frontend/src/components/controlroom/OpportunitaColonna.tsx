// ============================================================================
// OpportunitaColonna.tsx — «Opportunità di modello», STACCATA dalle uscite
// (Task 4, 18/09). Contenuto della scheda INVARIATO
// (`SchedaPropostaOpportunita`): qui cambia il contenitore, l'ordinamento e
// il raggruppamento per partita.
//
// «Organizzare alla perfezione» (parola dell'utente), SENZA un tetto al
// numero di schede: `lib/opportunitaOrdine.ts` ordina in modo STABILE (mai
// per prezzo: l'ordine cambia solo quando una scheda entra o esce) e
// raggruppa per partita con un'intestazione compatta.
// ============================================================================
import { Fragment } from 'react';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/trading/EmptyState';
import { organizzaOpportunita, type VoceOrdinabile } from '@/lib/opportunitaOrdine';
import { SchedaPropostaOpportunita } from './SchedaPropostaOpportunita';
import type { SportKey } from './SplitSport';
import type { useControlRoom, PropostaOppVista } from './useControlRoom';

export interface OpportunitaColonnaProps {
    vm: ReturnType<typeof useControlRoom>;
    /** serve SOLO a dirlo a schermo: la colonna non si filtra mai. */
    filtroSport: SportKey | null;
    testId?: string;
}

/** una proposta di opportunità come voce ordinabile: NESSUN campo di prezzo
 *  qui dentro, di proposito (vedi `lib/opportunitaOrdine.ts`). */
function comeVoce(po: PropostaOppVista): VoceOrdinabile & { po: PropostaOppVista } {
    const p = po.proposta;
    const creataAlleMs = p.created_at ? Date.parse(p.created_at) : null;
    return {
        id: p.id,
        eventId: p.payload?.event_id ?? null,
        live: String(p.payload?.mode ?? '').toLowerCase() === 'live',
        creataAlleMs: Number.isFinite(creataAlleMs) ? creataAlleMs : null,
        po,
    };
}

export function OpportunitaColonna({ vm, filtroSport, testId = 'cr-opportunita' }: OpportunitaColonnaProps) {
    const gruppi = organizzaOpportunita(vm.proposteOpportunita.map(comeVoce));
    const conta = vm.proposteOpportunita.length;

    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid={testId}>
            <div className="px-3 py-2 border-b border-white/10 flex items-center justify-between gap-2">
                <span className="text-[11px] uppercase tracking-wider text-white/60">Opportunità di modello</span>
                <span className="text-[11px] text-white/40" data-testid="cr-opportunita-contatore">{conta}</span>
            </div>

            {/* 18/09 (raccordo, R2) — avviso onesto: PIAZZA ha dovuto ripiegare
                sul solo p_id perche' la migrazione del prezzo visto non e'
                applicata. Mai un'approvazione persa, mai una doppia. */}
            {vm.avvisoOpportunita && (
                <div className="px-3 py-1.5 border-b border-orange-500/20 bg-orange-500/10 text-[10.5px] text-orange-300"
                    data-testid="cr-opportunita-avviso">
                    {vm.avvisoOpportunita}
                </div>
            )}

            {filtroSport != null && (
                <div className="px-3 py-1.5 border-b border-white/10 text-[10.5px] text-white/45"
                    data-testid="cr-opportunita-non-filtrata">
                    Il filtro <span className="text-white/70">{filtroSport}</span> non tocca questa colonna:
                    le opportunità compaiono da entrambi gli sport.
                </div>
            )}

            <div className="max-h-[calc(100vh-240px)] overflow-y-auto p-3 space-y-2.5" data-testid="cr-opportunita-scroll">
                {conta === 0 && (
                    <EmptyState>
                        <span className="font-semibold block mb-1">Nessuna opportunità in coda</span>
                        Quando il modello vede un vantaggio non lo piazza da solo: propone qui, con il prezzo che
                        si aggiorna da solo, e decidi tu.
                    </EmptyState>
                )}
                {gruppi.map((g) => (
                    <Fragment key={g.eventId ?? `combo-${g.voci[0]?.id}`}>
                        {g.voci.length > 1 && g.eventId != null && (
                            <div
                                className="text-[10px] uppercase tracking-wider text-white/40 px-0.5 pt-1"
                                data-testid="cr-opportunita-gruppo"
                            >
                                {g.voci.length} proposte sulla stessa partita
                            </div>
                        )}
                        {g.voci.map((v) => (
                            <SchedaPropostaOpportunita
                                key={`opp-${v.po.proposta.id}`}
                                proposta={v.po.proposta}
                                abbinabileOra={v.po.abbinabileOra}
                                etaQuoteS={v.po.etaQuoteS}
                                prezzoVivo={v.po.prezzoVivoGamba}
                                prezziViviGambe={v.po.prezziViviGambe}
                                slippagePct={vm.slippagePct}
                                onPiazza={vm.piazzaOpportunita}
                                onRifiuta={vm.rifiutaOpportunita}
                            />
                        ))}
                    </Fragment>
                ))}
            </div>
        </Card>
    );
}

export default OpportunitaColonna;
