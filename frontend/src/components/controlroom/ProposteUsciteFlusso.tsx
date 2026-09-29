// ============================================================================
// ProposteUsciteFlusso.tsx - LE USCITE DA APPROVARE dei bot di flusso (28/09).
//
// "OGNI BOT, PER ORA, DEVE PASSARE DA ME, IO APPROVO LE USCITE" (utente).
// Una riga per proposta viva (4 bot tennis, scalper calcio): cosa chiude, a che
// prezzo, quanto incassa o perde se chiude ORA, cosa succede se TIENE, e il
// bottone "approva uscita". Dopo la firma l'uscita la esegue il bot la
// prossima volta che la strategia la decide ancora (entro 120 s): se la
// condizione nel frattempo e' caduta, la proposta sparisce e non parte niente.
// Per chiudere comunque resta il "Chiudi" di sempre.
// ============================================================================
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { fmtMoney, fmtOdds, DASH } from '@/lib/format';
import { BOT_LABEL, type Bot } from '@/lib/controlRoom';
import {
    MOTIVO_TESTO, approvaPropostaFlusso, type PropostaFlusso,
} from '@/lib/proposteUscite';

export interface ProposteUsciteFlussoProps {
    proposte: PropostaFlusso[];
    nowMs: number;
    /** iniettabile nei test: di serie la RPC vera */
    approva?: (p: PropostaFlusso) => Promise<void>;
    testId?: string;
}

const soldi = (v: number | null) => (v == null ? DASH : fmtMoney(v, { signed: true }));

export function ProposteUsciteFlusso({ proposte, nowMs, approva, testId = 'cr-proposte-flusso' }: ProposteUsciteFlussoProps) {
    const [esiti, setEsiti] = useState<Record<string, string>>({});
    const [inVolo, setInVolo] = useState<string | null>(null);
    if (proposte.length === 0) return null;
    const firma = async (p: PropostaFlusso) => {
        setInVolo(p.chiave);
        try {
            await (approva ?? approvaPropostaFlusso)(p);
            setEsiti((e) => ({ ...e, [p.chiave]: 'firma inviata: parte al prossimo giro del bot se la condizione vale ancora' }));
        } catch (e) {
            setEsiti((x) => ({ ...x, [p.chiave]: `firma non inviata: ${e instanceof Error ? e.message : String(e)}` }));
        } finally { setInVolo(null); }
    };
    return (
        <div className="rounded border border-amber-400/40 bg-amber-400/5 px-3 py-2 space-y-2" data-testid={testId}>
            <div className="text-[11px] font-semibold text-amber-200">
                Uscite da approvare ({proposte.length})
            </div>
            {proposte.map((p) => {
                const daS = p.decidedAt == null ? null : Math.max(0, Math.round(nowMs / 1000 - p.decidedAt));
                const nome = BOT_LABEL[p.bot as Bot] ?? p.bot;
                return (
                    <div key={p.chiave} data-testid={`${testId}-riga`}
                        className={`rounded border px-2 py-1.5 space-y-1 ${p.urgente
                            ? 'border-red-500/40 bg-red-500/10' : 'border-white/10'}`}>
                        <div className="text-[10.5px] text-white/85" data-testid={`${testId}-titolo`}>
                            {nome} vorrebbe uscire: <strong>{MOTIVO_TESTO[p.motivo] ?? p.motivo}</strong>
                            {' - partita '}{p.eventId}
                            {daS != null ? ` - deciso ${daS} s fa` : ''}
                        </div>
                        <div className="text-[10.5px] font-mono text-white/75" data-testid={`${testId}-ordine`}>
                            {`chiude ${p.latoChiusura ?? DASH} ${p.sizeChiusura == null ? DASH : fmtMoney(p.sizeChiusura)}`
                                + ` @ ${fmtOdds(p.prezzo)}`
                                + (p.frazione != null && p.frazione < 1 ? ` (${Math.round(p.frazione * 100)}% della posizione)` : '')}
                        </div>
                        <div className="text-[10.5px] text-white/65" data-testid={`${testId}-numeri`}>
                            se chiudi ora {soldi(p.seChiudi)}
                            {' - se tieni: '}vince {soldi(p.seVince)} / perde {soldi(p.sePerde)}
                        </div>
                        <div className="flex items-center gap-2 flex-wrap">
                            <Button type="button" size="sm" disabled={inVolo != null}
                                onClick={() => void firma(p)}
                                data-testid={`${testId}-approva`}
                                className="h-6 px-2 text-[10px] uppercase tracking-wider bg-amber-600/80 hover:bg-amber-600 text-white">
                                approva uscita
                            </Button>
                            <span className="text-[10px] text-white/40">oppure chiudi a mano con "Chiudi"</span>
                        </div>
                        {esiti[p.chiave] && (
                            <div className="text-[10px] text-white/60" data-testid={`${testId}-esito`}>{esiti[p.chiave]}</div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}

export default ProposteUsciteFlusso;
