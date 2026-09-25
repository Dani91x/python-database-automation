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
import { EsitoAbbinamentoStriscia } from './EsitoAbbinamentoStriscia';
import { SchedaPropostaOpportunita } from './SchedaPropostaOpportunita';
import type { SportKey } from './SplitSport';
import type { useControlRoom, PropostaOppVista } from './useControlRoom';
import { sorgenteLadderAlMs } from '@/lib/localTransport';
import type { SorgenteLadder } from './usePrezzoAlMs';

export interface OpportunitaColonnaProps {
    vm: ReturnType<typeof useControlRoom>;
    /** serve SOLO a dirlo a schermo: la colonna non si filtra mai. */
    filtroSport: SportKey | null;
    testId?: string;
    /** 24/09 — la sorgente del ladder al ms delle schede (test: una finta). */
    sorgenteLadder?: SorgenteLadder | null;
}

const SORGENTE_DI_SERIE: SorgenteLadder = (sport) => sorgenteLadderAlMs(sport);

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

export function OpportunitaColonna({
    vm, filtroSport, testId = 'cr-opportunita', sorgenteLadder = SORGENTE_DI_SERIE,
}: OpportunitaColonnaProps) {
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

            {/* 24/09 — l'ESITO delle ultime approvazioni: la scheda sparisce al
                clic, quello che il servizio ha fatto (coi due prezzi se ha
                rifiutato) resta qui, nello stesso riquadro degli avvisi. */}
            {/* B17 (25/09) — l'ORDINE di ogni clic seguito fino all'esito: prezzo
                medio abbinato, Δ in tick vs visto e vs segnale, parziale/totale,
                NON abbinato (FOK), rifiutato — con fonte ed eta'. Sostituisce la
                riga dell'esito della richiesta per le proposte che segue. */}
            {(vm.esitiOrdini ?? [])
                .filter((e) => e.clic.bot === 'safe' && e.clic.tipo === 'apertura')
                .map((e) => <EsitoAbbinamentoStriscia key={e.clic.chiave} seguito={e} />)}
            {(vm.esitiOpportunita ?? [])
                .filter((e) => !(vm.esitiOrdini ?? []).some((s) => s.clic.chiave === `safe:apertura:${e.id}`))
                .map((e) => (
                <div key={`esito-${e.id}`}
                    className={`px-3 py-1.5 border-b text-[10.5px] ${
                        e.stato === 'eseguita' ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300'
                            : e.stato === 'rifiutata' ? 'border-red-500/20 bg-red-500/10 text-red-300'
                                : 'border-white/10 bg-white/[0.03] text-white/60'
                    }`}
                    data-testid="cr-opportunita-esito" data-stato={e.stato}>
                    proposta #{e.id} · {e.stato}: {e.testo}
                </div>
            ))}

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
                                sorgenteLadder={sorgenteLadder}
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
