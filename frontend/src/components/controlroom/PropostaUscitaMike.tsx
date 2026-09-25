// ============================================================================
// PropostaUscitaMike.tsx — 25/09: L'USCITA CHE MIKE VORREBBE FARE, DA APPROVARE.
//
// «se disattivo il pulsante (TUTTO IN UI PER SINGOLO BOT), le uscite le
// gestisco io manualmente tramite l'apposita scheda» (utente, 25/09).
//
// Con «Uscite automatiche» SPENTO il motore di Mike non esegue le uscite
// discrezionali (green-up, uscita al fischio, cash out, uscita in perdita a
// modello): scrive la PROPOSTA nel contesto della partita
// (`mike_events.ctx.uscita_proposta`, `engine.gate_uscite`). Qui la si mostra
// con tutto quello che serve per decidere, e il bottone APPROVA manda la
// richiesta `approva_uscita` con la chiave della proposta e il contesto del
// clic (prezzo visto, età, fonte). L'uscita poi la esegue il bot ESATTAMENTE
// come la strategia la vuole in quel momento. Per chiudere a mano resta il
// «Chiudi» di sempre della riga di Mike.
//
// REGOLE: nessuna fetch nuova (l'evento arriva già con `ctx` e `live`),
// stessa freschezza della scheda (`feedFreshness`): con il feed fermo o
// ignoto il bottone si spegne, come `MikeMatchCard` (regola della scheda).
// ============================================================================
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { fmtMoney, fmtOdds, DASH } from '@/lib/format';
import { etaQuoteS, feedFreshness, requestMike, roleLabel, type MikeEvent } from '@/lib/mike';
import { useSecondTick } from '@/components/mike/useMikeClock';

/** La proposta come la scrive `engine.gate_uscite` (chiavi VERE). */
export interface PropostaUscitaMikeDati {
    chiave: string;
    categoria: string;
    ciclo: number;
    stato: string;
    stato_voluto: string;
    motivo: string;
    close_reason: string | null;
    ordini: { ruolo: string; mercato: string; selezione: string; lato: string; prezzo: number | null; size: number | null }[];
    bloccabile: number | null;
    urgente: boolean;
    minuto: number | null;
    gol: number | null;
    decided_at: number;
    proposed_at: number;
}

const CATEGORIA: Record<string, string> = {
    green_pre: 'green-up pre-partita',
    ko_green: 'uscita al fischio',
    chiusura: 'cash out della posizione',
    reentry_green: 'uscita del re-ingresso',
};

export function propostaDi(ev: MikeEvent): PropostaUscitaMikeDati | null {
    const p = (ev.ctx ?? {})['uscita_proposta'];
    if (p == null || typeof p !== 'object' || Array.isArray(p)) return null;
    const d = p as Partial<PropostaUscitaMikeDati>;
    if (typeof d.chiave !== 'string' || !d.chiave) return null;
    return d as PropostaUscitaMikeDati;
}

export function PropostaUscitaMike({ ev, testId = 'cr-mike-proposta' }: { ev: MikeEvent; testId?: string }) {
    const prop = propostaDi(ev);
    const adesso = useSecondTick(prop != null);
    const [esito, setEsito] = useState<string | null>(null);
    const [inVolo, setInVolo] = useState(false);
    if (prop == null) return null;

    const live = ev.live ?? {};
    const eta = etaQuoteS(live, adesso);
    const fresh = feedFreshness(eta);
    const spento = fresh.tone === 'stale' || fresh.tone === 'unknown' || inVolo;
    const books = live.books ?? {};
    const daDecisioneS = Math.max(0, Math.round(adesso / 1000 - Number(prop.decided_at)));
    const bloccabileOra = typeof live.cashout?.net === 'number' ? live.cashout.net : null;

    const approva = async () => {
        setInVolo(true); setEsito(null);
        const o = prop.ordini[0];
        const bk = o ? books[`${o.mercato}|${o.selezione}`] : undefined;
        try {
            await requestMike('approva_uscita', {
                event_id: ev.event_id, bot: 'mike', mode: ev.mode, chiave: prop.chiave,
                contesto: {
                    prezzo_visto: bk ? (o.lato === 'lay' ? bk.best_lay : bk.best_back) : null,
                    eta_ms: eta == null ? null : Math.round(eta * 1000),
                    fonte: 'mike_events.live (get_mike_state)',
                },
            });
            setEsito('approvazione inviata: parte al prossimo giro del bot');
        } catch (e) {
            setEsito(`approvazione non inviata: ${e instanceof Error ? e.message : String(e)}`);
        } finally { setInVolo(false); }
    };

    return (
        <div className={`rounded border px-2.5 py-2 space-y-1 ${prop.urgente
            ? 'border-red-500/40 bg-red-500/10' : 'border-amber-400/40 bg-amber-400/10'}`}
            data-testid={testId}>
            <div className="flex items-center justify-between gap-2">
                <span className="text-[10.5px] font-semibold text-amber-200" data-testid={`${testId}-titolo`}>
                    Mike vorrebbe uscire: {CATEGORIA[prop.categoria] ?? prop.categoria}
                    {prop.urgente ? ' (in perdita)' : ''}
                </span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded border ${fresh.cls}`}>{fresh.label}</span>
            </div>
            <div className="text-[10.5px] text-white/70" data-testid={`${testId}-motivo`}>{prop.motivo}</div>
            <div className="text-[10.5px] font-mono text-white/80" data-testid={`${testId}-ordini`}>
                {prop.ordini.map((o) => {
                    const bk = books[`${o.mercato}|${o.selezione}`];
                    return `${roleLabel(o.ruolo)} ${o.lato} ${o.size == null ? DASH : fmtMoney(o.size)} @ ${fmtOdds(o.prezzo)}`
                        + ` (ora ${bk ? `${fmtOdds(bk.best_back)} / ${fmtOdds(bk.best_lay)}` : DASH})`;
                }).join(' + ')}
            </div>
            <div className="text-[10.5px] text-white/60" data-testid={`${testId}-numeri`}>
                chiudendo ora {bloccabileOra == null ? DASH : fmtMoney(bloccabileOra, { signed: true })}
                {' · '}alla decisione {prop.bloccabile == null ? DASH : fmtMoney(prop.bloccabile, { signed: true })}
                {' · '}deciso {daDecisioneS} s fa
                {prop.minuto != null ? ` · ${prop.minuto}′` : ''}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
                <Button type="button" size="sm" disabled={spento}
                    onClick={() => void approva()}
                    data-testid={`${testId}-approva`}
                    title={spento ? 'feed fermo o ignoto: non si approva su prezzi vecchi' : 'il bot esegue questa uscita al prossimo giro'}
                    className="h-6 px-2 text-[10px] uppercase tracking-wider bg-amber-600/80 hover:bg-amber-600 text-white">
                    approva uscita
                </Button>
                <span className="text-[10px] text-white/40">oppure chiudi a mano con «Chiudi» di Mike</span>
            </div>
            {esito && <div className="text-[10px] text-white/60" data-testid={`${testId}-esito`}>{esito}</div>}
        </div>
    );
}

export default PropostaUscitaMike;
