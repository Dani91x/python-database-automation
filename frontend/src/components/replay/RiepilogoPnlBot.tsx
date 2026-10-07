// ============================================================================
// RiepilogoPnlBot — il P&L del bot applicato (07/10 sera), uguale per tutti i
// bot. Al cursore: abbinato, non abbinato sul book, esposizione (perdita
// peggiore delle posizioni aperte), cicli chiusi e loro P&L. A fine prova: il
// P&L a REGOLAMENTO (risultato del mercato registrato) ricavato dalle righe e
// CONFRONTATO col banco (stesse regole in Python e, quando c'e', il regolamento
// di flumine), e il P&L dei cicli col metodo che il bot dichiara.
// ============================================================================
import type { EsitoBot } from '@/lib/replayBot';
import { pnl, eur, riepilogoAl } from '@/lib/replayOperazioni';
import type { OperativitaBot } from '@/lib/useOperativitaBot';

export interface RiepilogoPnlBotProps {
    esito: EsitoBot;
    analisi: OperativitaBot;
    nowMs: number;
    runnerDi?: (marketId: string) => ReadonlyArray<number> | undefined;
}

const cls = (x: number | null | undefined) => ((x ?? 0) > 0 ? 'text-emerald-300' : (x ?? 0) < 0 ? 'text-red-300' : 'text-white/80');

function Confronto({ nostro, banco, etichetta }: { nostro: number; banco: number | null | undefined; etichetta: string }) {
    if (banco == null) return null;
    const ok = Math.abs(nostro - banco) < 0.005;
    return (
        <span className={ok ? 'text-emerald-300/80' : 'text-red-300 font-bold'} data-testid="confronto-banco" data-ok={ok ? '1' : '0'}>
            {ok ? `✓ uguale ${etichetta} (${pnl(banco)})` : `≠ ${etichetta}: ${pnl(banco)}`}
        </span>
    );
}

export function RiepilogoPnlBot({ esito, analisi, nowMs, runnerDi }: RiepilogoPnlBotProps) {
    const t = riepilogoAl(analisi.ordini, analisi.cicli, nowMs, esito.esiti_mercati ?? null, runnerDi);
    const reg = analisi.regolato;
    const dich = esito.conto_dichiarato;
    return (
        <div className="rounded-xl border border-emerald-400/30 bg-black/30 p-2 text-[11px] space-y-1" data-testid="riepilogo-pnl-bot">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <span className="font-black text-emerald-200">💶 P&L del bot</span>
                <span>al cursore: abbinato <b className="font-mono">{eur(t.abbinato)}</b></span>
                <span>sul book (non abbinato) <b className="font-mono">{eur(t.appoggiato)}</b> in {t.ordiniVivi} ordini</span>
                <span>esposizione <b className="font-mono text-red-200" data-testid="pnl-esposizione">{eur(t.esposizione)}</b></span>
                <span>cicli chiusi {t.cicliChiusi}: <b className={`font-mono ${cls(t.pnlCicliChiusi)}`} data-testid="pnl-cicli-al-cursore">{pnl(t.pnlCicliChiusi)}</b></span>
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="text-white/70">a regolamento (risultato del mercato registrato):</span>
                <span>lordo <b className={`font-mono ${cls(reg.lordo)}`} data-testid="pnl-regolato-lordo">{pnl(reg.lordo)}</b></span>
                <span>commissione <b className="font-mono">{eur(reg.commissione)}</b></span>
                <span>NETTO <b className={`font-mono ${cls(reg.netto)}`} data-testid="pnl-regolato-netto">{pnl(reg.netto)}</b></span>
                <Confronto nostro={reg.netto} banco={esito.conto_banco?.netto} etichetta="al banco" />
                <Confronto nostro={reg.lordo} banco={esito.conto_flumine?.lordo} etichetta="al regolamento di flumine (lordo)" />
                {reg.mercatiNonRegolati.length > 0 && (
                    <span className="text-amber-200">mercati senza risultato nella registrazione: {reg.mercatiNonRegolati.length} (fuori dal conto)</span>
                )}
            </div>
            {dich && (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="text-white/70">{dich.metodo === 'cicli' ? 'dei cicli (metodo del bot: ciclo chiuso = profitto bloccato):' : 'dichiarato dal referto del bot:'}</span>
                    {dich.metodo === 'cicli' ? (
                        <>
                            <span>lordo <b className={`font-mono ${cls(analisi.cicliConto.lordo)}`} data-testid="pnl-cicli-lordo">{pnl(analisi.cicliConto.lordo)}</b></span>
                            <span>commissione <b className="font-mono">{eur(analisi.cicliConto.commissione)}</b></span>
                            <span>NETTO <b className={`font-mono ${cls(analisi.cicliConto.netto)}`} data-testid="pnl-cicli-netto">{pnl(analisi.cicliConto.netto)}</b></span>
                            <Confronto nostro={analisi.cicliConto.netto} banco={dich.netto} etichetta="al referto del bot" />
                        </>
                    ) : (
                        <>
                            <span>lordo <b className="font-mono">{pnl(dich.lordo)}</b> · netto <b className="font-mono">{pnl(dich.netto)}</b></span>
                            <Confronto nostro={reg.lordo} banco={dich.lordo} etichetta="al referto del bot (lordo)" />
                        </>
                    )}
                </div>
            )}
        </div>
    );
}
