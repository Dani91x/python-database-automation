// ============================================================================
// UsciteColonna.tsx — «Uscite — decidi tu», STACCATA dalle opportunità
// (Task 4, 18/09). Contenuto delle schede INVARIATO (`SchedaChiusura`,
// `SchedaChiusuraOmega`): qui cambia solo il contenitore.
//
// Il nastro non si filtra MAI per sport: un'uscita matura su soldi veri non
// deve sparire perché il trader sta guardando l'altro sport (regola già in
// vigore, qui solo trasferita nel contenitore nuovo).
// ============================================================================
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/trading/EmptyState';
import { BOT_LABEL, affidabilePerPiazzare } from '@/lib/controlRoom';
import { SchedaChiusura } from './SchedaChiusura';
import { SchedaChiusuraOmega } from './SchedaChiusuraOmega';
import { trovaEsitoUscita } from './trovaEsitoUscita';
import type { SportKey } from './SplitSport';
import type { useControlRoom } from './useControlRoom';

export interface UsciteColonnaProps {
    vm: ReturnType<typeof useControlRoom>;
    /** serve SOLO a dirlo a schermo: la colonna non si filtra mai. */
    filtroSport: SportKey | null;
    testId?: string;
}

export function UsciteColonna({ vm, filtroSport, testId = 'cr-nastro' }: UsciteColonnaProps) {
    const bloccati = vm.bots.filter((b) => b.canale !== 'connected' || !affidabilePerPiazzare(b.freschezzaPush));
    const urgenti = vm.proposte.filter((p) => p.proposta.payload?.urgente === true).length;
    const conta = vm.proposte.length + vm.proposteOmega.length;

    return (
        <Card className="glass-card border-white/10 p-0 overflow-hidden" data-testid={testId}>
            <div className="px-3 py-2 border-b border-white/10 flex items-center justify-between gap-2">
                <span className="text-[11px] uppercase tracking-wider text-white/60">Uscite — decidi tu</span>
                <span className="text-[11px] text-white/40" data-testid="cr-nastro-contatore">
                    {conta} in attesa
                    {urgenti > 0 && <span className="text-orange-300 font-semibold"> · {urgenti} urgenti</span>}
                </span>
            </div>

            {filtroSport != null && (
                <div className="px-3 py-1.5 border-b border-white/10 text-[10.5px] text-white/45"
                    data-testid="cr-nastro-non-filtrato">
                    Il filtro <span className="text-white/70">{filtroSport}</span> non tocca questo nastro:
                    le uscite compaiono da entrambi gli sport.
                </div>
            )}

            {bloccati.length > 0 && (
                <div className="px-3 py-2 border-b border-white/10 text-[11px] text-orange-300" data-testid="cr-bot-muti">
                    {bloccati.map((b) => BOT_LABEL[b.bot]).join(', ')}: nessuna spinta recente.
                    I numeri di {bloccati.length > 1 ? 'questi bot' : 'questo bot'} potrebbero essere vecchi —
                    non si piazza su dati di cui non conosciamo l&apos;età.
                </div>
            )}

            <div className="px-3 py-1.5 border-b border-white/10 flex items-center gap-2 text-[11px] text-white/50">
                <label htmlFor="cr-slippage">scostamento massimo dal prezzo della proposta</label>
                <input
                    id="cr-slippage" type="number" step="0.5" min="0.5" max="20"
                    value={vm.slippagePct}
                    onChange={(e) => vm.setSlippagePct(Math.max(0.5, Number(e.target.value) || 2))}
                    className="w-16 px-1.5 py-0.5 rounded border border-white/15 bg-white/5 font-mono text-right text-white/90"
                />
                <span>%</span>
            </div>

            <div className="max-h-[calc(100vh-240px)] overflow-y-auto p-3 space-y-2.5">
                {vm.erroreProposteOmega && (
                    <div className="rounded border border-orange-500/30 bg-orange-500/10 px-2.5 py-1.5 text-[11px] text-orange-200"
                        data-testid="cr-proposte-omega-errore">
                        <strong className="text-orange-300">Proposte di uscita di Omega non leggibili:</strong>{' '}
                        {vm.erroreProposteOmega}. Finché non si legge, qui non compare nessuna uscita di Omega —
                        e non vuol dire che non ce ne siano.
                    </div>
                )}
                {vm.proposteOmega.map((pr) => (
                    <SchedaChiusuraOmega
                        key={`omega-${pr.id}`}
                        proposta={pr}
                        onApprova={vm.approvaOmega}
                        onIgnora={vm.ignoraOmega}
                        esito={trovaEsitoUscita(
                            vm.operazioni.get(pr.payload.event_id), 'omega', pr.payload.trade_id,
                        )}
                    />
                ))}
                {conta === 0 && (
                    <EmptyState>
                        <span className="font-semibold block mb-1">Nessuna uscita da decidere</span>
                        Il bot apre da solo. Quando matura un&apos;uscita non la esegue: la propone qui, con il prezzo
                        che si aggiorna da solo, l&apos;importo davvero abbinabile e il confronto fra chiudere e tenere.
                        Le urgenti stanno in cima.
                    </EmptyState>
                )}
                {vm.proposte.map((pv) => (
                    <SchedaChiusura
                        key={pv.proposta.id}
                        proposta={pv.proposta}
                        vivo={pv.vivo}
                        etaQuoteS={pv.etaQuoteS}
                        etaScannerS={vm.feedEtaS}
                        bloccabileOra={pv.bloccabileOra}
                        slippagePct={vm.slippagePct}
                        onApprova={vm.approva}
                        onIgnora={vm.ignora}
                        esito={trovaEsitoUscita(
                            vm.operazioni.get(pv.proposta.payload.event_id), 'safe', pv.proposta.payload.trade_id,
                        )}
                    />
                ))}
            </div>
        </Card>
    );
}

export default UsciteColonna;
