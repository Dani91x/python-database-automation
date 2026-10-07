// ============================================================================
// EsitoBotPanel — il RISULTATO di «Applica bot» (07/10), per tutti i bot.
// Intestazione: bot, scenario, parametri cambiati rispetto alla serie, istante
// di accensione; poi cosa vede il bot all'accensione, le violazioni dei
// controlli del banco, le note sui motivi di non ingresso e gli ordini del bot
// all'istante corrente della timeline (BotOrdersPanel, sola lettura: gli
// stessi ordini compaiono sul ladder). Riusabile (Match Replay, Replay Tennis).
// ============================================================================
import { Badge } from '@/components/ui/badge';
import { BotOrdersPanel } from '@/components/replay/BotOrdersPanel';
import { testoIstante, testoValore } from '@/lib/applicaBot';
import { CATALOGO_BOT } from '@/lib/replayBotCatalogo';
import { noteUtili, ordiniBotAlMs, type CatalogoBot, type EsitoBot, type VoceParametro } from '@/lib/replayBot';

export interface EsitoBotPanelProps {
    esito: EsitoBot;
    /** istante corrente della timeline (ms) */
    nowMs: number;
    nomeMercato: (marketId: string) => string;
    nomeSelezione: (marketId: string, selectionId: number) => string;
    catalogo?: ReadonlyArray<CatalogoBot>;
}

/** L'etichetta e il valore leggibile di ogni parametro cambiato. PURA. */
export function righeCambiati(esito: EsitoBot, catalogo: ReadonlyArray<CatalogoBot>): string[] {
    const voci: VoceParametro[] = catalogo.find(b => b.bot === esito.bot)
        ?.scenari.find(s => s.scenario === esito.scenario)?.parametri ?? [];
    return Object.entries(esito.parametri_cambiati ?? {}).map(([k, x]) => {
        const v = voci.find(y => y.chiave === k);
        return v ? `${v.etichetta}: ${testoValore(v, x)} (di serie ${testoValore(v, v.default)})` : `${k}: ${String(x)}`;
    });
}

export function EsitoBotPanel({ esito, nowMs, nomeMercato, nomeSelezione, catalogo = CATALOGO_BOT }: EsitoBotPanelProps) {
    const cambiati = righeCambiati(esito, catalogo);
    const note = noteUtili(esito.note);
    return (
        <div className="space-y-2" data-testid="esito-bot">
            <div className="rounded-xl border border-amber-400/30 bg-black/30 p-2 text-[11px] text-white/80 space-y-1"
                data-testid="esito-bot-intestazione">
                <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-amber-200">{esito.etichetta}</span>
                    <Badge variant="outline" className="text-[10px]">{esito.bot} · {esito.scenario}</Badge>
                    <Badge variant="secondary" className="text-[10px]" data-testid="esito-bot-accensione">
                        {esito.dal_ms != null ? `acceso dalle ${testoIstante(esito.dal_ms)}` : 'acceso dall’inizio della registrazione'}
                    </Badge>
                    <Badge variant={esito.violazioni.length > 0 ? 'destructive' : 'outline'} className="text-[10px]"
                        data-testid="esito-bot-violazioni">
                        {esito.violazioni.length > 0
                            ? `violazioni: ${Array.from(new Set(esito.violazioni)).join(', ')}`
                            : 'nessuna violazione dei controlli del banco'}
                    </Badge>
                </div>
                <div data-testid="esito-bot-parametri">
                    {cambiati.length === 0
                        ? 'parametri: tutti di serie'
                        : <>parametri cambiati (la strategia non cambia): {cambiati.join(' · ')}</>}
                </div>
                {esito.accensione && <div className="text-white/60">{esito.accensione}</div>}
            </div>
            {note.length > 0 && (
                <div className="rounded-xl border border-amber-400/20 bg-black/30 p-2 text-[11px] text-white/75 space-y-0.5"
                    data-testid="note-bot">
                    <div className="font-bold text-amber-200">Cosa ha fatto il bot e perché non entrava prima</div>
                    {note.map((n, i) => <div key={i}>• {n}</div>)}
                </div>
            )}
            <BotOrdersPanel
                titolo={esito.etichetta}
                ordini={ordiniBotAlMs(esito.righe, nowMs)}
                nomeMercato={nomeMercato}
                nomeSelezione={nomeSelezione}
            />
        </div>
    );
}
