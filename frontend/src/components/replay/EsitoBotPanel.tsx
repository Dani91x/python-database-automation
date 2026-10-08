// ============================================================================
// EsitoBotPanel — il RISULTATO di «Applica bot» (07/10; strumento professionale
// dal 07/10 sera), per TUTTI i bot, calcio e tennis (stesso componente).
//   1. intestazione: bot, scenario, parametri cambiati, accensione;
//   2. AVVISI di onesta': cio' che la pagina ha mandato e il banco/bot NON ha
//      ricevuto (accensione dal cursore, clic, parametri) — ben visibili;
//   3. P&L del bot (al cursore e a fine prova, confrontato col banco);
//   4. REGISTRO DELLE OPERAZIONI (clic sull'evento = salto della timeline);
//   5. gli ordini al cursore; 6. il referto completo del banco (note).
// Gli stessi ordini (appoggiati/abbinati) e il P&L si vedono sul LADDER.
// ============================================================================
import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { BotOrdersPanel } from '@/components/replay/BotOrdersPanel';
import { RegistroOperazioniBot, type PuntoSeek } from '@/components/replay/RegistroOperazioniBot';
import { RiepilogoPnlBot } from '@/components/replay/RiepilogoPnlBot';
import { testoIstante, testoValore } from '@/lib/applicaBot';
import { avvisiBanco, confermaBanco } from '@/lib/avvisiBanco';
import { CATALOGO_BOT } from '@/lib/replayBotCatalogo';
import type { CatalogoBot, EsitoBot, OpzioniApplica, VoceParametro } from '@/lib/replayBot';
import type { FaseReplay } from '@/lib/replayFasi';
import { statoOrdiniAl } from '@/lib/replayOperazioni';
import type { OperativitaBot } from '@/lib/useOperativitaBot';

export interface EsitoBotPanelProps {
    esito: EsitoBot;
    /** l'analisi dell'esito (useOperativitaBot) */
    analisi: OperativitaBot;
    /** cio' che la pagina aveva mandato al banco (per gli avvisi); null = ignoto */
    inviato?: OpzioniApplica | null;
    /** istante corrente della timeline (ms) */
    nowMs: number;
    nomeMercato: (marketId: string) => string;
    nomeSelezione: (marketId: string, selectionId: number) => string;
    etichettaIstante?: (ms: number) => string;
    /** 08/10 (cantiere 10): la fase della partita all'istante (sezioni del registro e riga «per fase») */
    faseIstante?: (ms: number) => FaseReplay;
    runnerDi?: (marketId: string) => ReadonlyArray<number> | undefined;
    onSeek: (p: PuntoSeek) => void;
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

export function EsitoBotPanel({
    esito, analisi, inviato = null, nowMs, nomeMercato, nomeSelezione, etichettaIstante, faseIstante, runnerDi, onSeek,
    catalogo = CATALOGO_BOT,
}: EsitoBotPanelProps) {
    const [referto, setReferto] = useState(false);
    const cambiati = righeCambiati(esito, catalogo);
    const avvisi = avvisiBanco(esito, inviato);
    const conferma = confermaBanco(esito);
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
                {conferma && <div className="text-emerald-300/80" data-testid="esito-bot-conferma">{conferma}</div>}
                {esito.accensione && <div className="text-white/60">{esito.accensione}</div>}
            </div>
            {avvisi.length > 0 && (
                <div className="rounded-xl border-2 border-red-500/70 bg-red-500/15 p-2 text-[12px] space-y-1" role="alert"
                    data-testid="avvisi-banco">
                    {avvisi.map((a, i) => (
                        <div key={i} className={a.grave ? 'text-red-100 font-bold' : 'text-amber-100'}>⚠ {a.testo}</div>
                    ))}
                </div>
            )}
            <RiepilogoPnlBot esito={esito} analisi={analisi} nowMs={nowMs} runnerDi={runnerDi} faseIstante={faseIstante} />
            <RegistroOperazioniBot esito={esito} analisi={analisi} nowMs={nowMs}
                nomeMercato={nomeMercato} nomeSelezione={nomeSelezione}
                etichettaIstante={etichettaIstante} faseIstante={faseIstante} onSeek={onSeek} />
            <BotOrdersPanel
                titolo={esito.etichetta}
                ordini={statoOrdiniAl(analisi.ordini, nowMs)}
                nomeMercato={nomeMercato}
                nomeSelezione={nomeSelezione}
                onSeek={(ms, marketId, selectionId) => onSeek({ ms, marketId, selectionId })}
            />
            {esito.note.length > 0 && (
                <div className="rounded-xl border border-white/10 bg-black/30 p-2 text-[11px] text-white/70">
                    <button type="button" className="font-bold text-white/70" onClick={() => setReferto(r => !r)}
                        data-testid="referto-banco-apri">
                        {referto ? '▾' : '▸'} referto completo del banco ({esito.note.length} righe)
                    </button>
                    {referto && <div className="mt-1 space-y-0.5 whitespace-pre-wrap">{esito.note.map((n, i) => <div key={i}>• {n}</div>)}</div>}
                </div>
            )}
        </div>
    );
}
