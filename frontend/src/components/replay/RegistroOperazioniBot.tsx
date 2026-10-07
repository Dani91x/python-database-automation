// ============================================================================
// RegistroOperazioniBot — il REGISTRO DELLE OPERAZIONI del bot applicato al
// replay (07/10 sera). Uguale per TUTTI i bot, calcio e tennis: legge solo
// l'analisi generica della cronologia degli ordini (`useOperativitaBot`).
//   * vista «per ciclo»: ciclo -> una riga per ORDINE (bet id, lato, quota,
//     importo, stato finale) -> sotto, gli eventi dell'ordine;
//   * vista «cronologica»: tutti gli eventi in ordine di tempo;
//   * in cima i clic «Attiva adesso» col loro esito (eseguito / RIFIUTATO e
//     perche'), quando il bot ne ha.
// Ogni evento e' cliccabile: la timeline del replay salta all'istante ESATTO
// (`_ms` del banco) e il ladder mostra il mercato dell'ordine.
// ============================================================================
import { useMemo, useState } from 'react';
import { testoIstante } from '@/lib/applicaBot';
import type { CicloDichiarato, EsitoBot } from '@/lib/replayBot';
import {
    eur, nomeLato, pnl, statoOrdineTesto, testoEvento,
    type CicloOperativo, type EventoOperazione, type OrdineBot,
} from '@/lib/replayOperazioni';
import type { OperativitaBot } from '@/lib/useOperativitaBot';

export interface PuntoSeek {
    ms: number;
    marketId: string | null;
    selectionId: number | null;
}

export interface RegistroOperazioniBotProps {
    esito: EsitoBot;
    analisi: OperativitaBot;
    nowMs: number;
    nomeMercato: (marketId: string) => string;
    nomeSelezione: (marketId: string, selectionId: number) => string;
    /** minuto di gioco / fase della partita all'istante (calcio: 23'; tennis: set) */
    etichettaIstante?: (ms: number) => string;
    onSeek: (p: PuntoSeek) => void;
}

const CLS_SELECT = 'px-2 py-1 rounded-md bg-black/40 border border-white/15 text-white text-[11px]';

function ora(ms: number): string {
    const ms3 = String(((ms % 1000) + 1000) % 1000).padStart(3, '0');
    return `${testoIstante(ms)}.${ms3}`;
}

const COLORE_TIPO: Record<string, string> = {
    piazzato: 'text-white/85',
    appoggiato: 'text-amber-200',
    abbinato_parziale: 'text-emerald-300',
    abbinato_totale: 'text-emerald-300 font-bold',
    annullo_richiesto: 'text-white/50',
    riprezzo_richiesto: 'text-white/50',
    annullato: 'text-orange-300',
    scaduto: 'text-orange-300',
    void: 'text-orange-300',
    rifiutato: 'text-red-300',
    ciclo_chiuso: 'text-violet-200 font-bold',
    mercato_chiuso: 'text-violet-200 font-bold',
};

/** Il ciclo dichiarato dal bot che contiene gli ordini di un ciclo. PURA. */
export function cicloDelBot(c: CicloOperativo, dichiarati: ReadonlyArray<CicloDichiarato> | null | undefined): CicloDichiarato | null {
    if (!dichiarati) return null;
    const ids = new Set(c.ordini.filter(k => k.startsWith('o:')).map(k => k.slice(2)));
    return dichiarati.find(d => (d.ordini_id ?? []).some(id => ids.has(String(id)))) ?? null;
}

function RigaEvento({ e, attuale, futuro, quando, onSeek, mostraOrdine, nomeMercato, nomeSelezione }: {
    e: EventoOperazione; attuale: boolean; futuro: boolean; quando: string;
    onSeek: (p: PuntoSeek) => void; mostraOrdine: boolean;
    nomeMercato: (m: string) => string; nomeSelezione: (m: string, s: number) => string;
}) {
    const testo = testoEvento(e);
    return (
        <button type="button"
            onClick={() => onSeek({ ms: e.ms, marketId: e.marketId, selectionId: e.selectionId })}
            data-testid="registro-evento" data-ms={e.ms} data-tipo={e.tipo}
            title="Porta la timeline a questo istante esatto e mostra il ladder di questo mercato"
            className={`w-full text-left grid grid-cols-[96px_72px_1fr] gap-1 px-1 py-0.5 rounded hover:bg-white/10 ${
                attuale ? 'bg-amber-400/15 ring-1 ring-amber-400/60' : ''} ${futuro ? 'opacity-50' : ''}`}>
            <span className="font-mono tabular-nums text-white/60">{ora(e.ms)}</span>
            <span className="text-white/45 truncate">{quando}</span>
            <span className={COLORE_TIPO[e.tipo] ?? 'text-white/80'}>
                {mostraOrdine && e.selectionId != null && (
                    <span className="text-white/50">{nomeMercato(e.marketId)} · {nomeSelezione(e.marketId, e.selectionId)} · </span>
                )}
                {mostraOrdine && e.lato && !testo.startsWith(nomeLato(e.lato)) && (
                    <span className={`font-bold ${e.lato === 'back' ? 'text-sky-300' : 'text-pink-300'}`}>{nomeLato(e.lato)} </span>
                )}
                {testo}
            </span>
        </button>
    );
}

export function RegistroOperazioniBot({
    esito, analisi, nowMs, nomeMercato, nomeSelezione, etichettaIstante, onSeek,
}: RegistroOperazioniBotProps) {
    const [vista, setVista] = useState<'cicli' | 'tempo'>('cicli');
    const [mercato, setMercato] = useState<string>('');
    const [nascondiVuoti, setNascondiVuoti] = useState(true);
    const quando = (ms: number) => (etichettaIstante ? etichettaIstante(ms) : '');
    const mercati = useMemo(() => [...new Set(analisi.ordini.map(o => o.marketId))], [analisi]);
    const eventi = useMemo(
        () => analisi.eventi.filter(e => !mercato || e.marketId === mercato),
        [analisi, mercato],
    );
    // l'evento «attuale»: l'ultimo con istante <= cursore
    const attuale = useMemo(() => {
        let id: string | null = null;
        for (const e of eventi) {
            if (e.ms > nowMs) break;
            id = e.id;
        }
        return id;
    }, [eventi, nowMs]);
    const perOrdine = useMemo(() => {
        const m = new Map<string, EventoOperazione[]>();
        for (const e of analisi.eventi) {
            if (!e.ordine) continue;
            const a = m.get(e.ordine) ?? [];
            a.push(e);
            m.set(e.ordine, a);
        }
        return m;
    }, [analisi]);
    const cicli = analisi.cicli.filter(c => (!mercato || c.marketId === mercato)
        && !(nascondiVuoti && c.abbinatoBack + c.abbinatoLay <= 0 && c.stato === 'chiuso'));
    const vuoti = analisi.cicli.filter(c => (!mercato || c.marketId === mercato)
        && c.abbinatoBack + c.abbinatoLay <= 0 && c.stato === 'chiuso').length;
    const rigaOrdine = (o: OrdineBot) => {
        const ultima = o.righe[o.righe.length - 1];
        const sost = o.sostituitoDa != null;
        return (
            <div key={o.chiave} className="border-l-2 border-white/10 pl-2 py-0.5" data-testid="registro-ordine" data-ordine={o.chiave}>
                <div className="flex flex-wrap items-center gap-x-2 text-[11px]">
                    <span className={`font-black ${o.lato === 'back' ? 'text-sky-300' : 'text-pink-300'}`}>{nomeLato(o.lato)}</span>
                    <span className="text-white/90">{nomeSelezione(o.marketId, o.selectionId)}</span>
                    <span className="font-mono tabular-nums text-white">{eur(o.importo)} @ {eur(o.quota)}</span>
                    <span className="text-white/40">{o.persistenza ?? ''}</span>
                    <span className="text-white/40">bet {o.betId ?? '—'}</span>
                    <span className="text-white/70" data-testid="registro-stato-ordine">→ {statoOrdineTesto(ultima, sost)}</span>
                </div>
                <div className="pl-1">
                    {(perOrdine.get(o.chiave) ?? []).map(e => (
                        <RigaEvento key={e.id} e={e} attuale={e.id === attuale} futuro={e.ms > nowMs}
                            quando={quando(e.ms)} onSeek={onSeek} mostraOrdine={false}
                            nomeMercato={nomeMercato} nomeSelezione={nomeSelezione} />
                    ))}
                </div>
            </div>
        );
    };
    return (
        <div className="rounded-xl border border-amber-400/30 bg-black/30 p-2 text-[11px] space-y-2" data-testid="registro-operazioni">
            <div className="flex flex-wrap items-center gap-2">
                <span className="font-black text-amber-200">📒 Registro operazioni del bot</span>
                <span className="text-white/50">{analisi.ordini.length} ordini · {analisi.eventi.filter(e => e.ordine).length} eventi · {analisi.cicli.length} cicli</span>
                <span className="flex-1" />
                <select value={mercato} onChange={e => setMercato(e.target.value)} aria-label="Filtra per mercato"
                    style={{ colorScheme: 'dark' }} className={CLS_SELECT} data-testid="registro-filtro-mercato">
                    <option value="" className="bg-neutral-900">tutti i mercati</option>
                    {mercati.map(m => <option key={m} value={m} className="bg-neutral-900">{nomeMercato(m)}</option>)}
                </select>
                <div role="radiogroup" aria-label="Vista del registro" className="flex gap-1">
                    {(['cicli', 'tempo'] as const).map(v => (
                        <button key={v} type="button" role="radio" aria-checked={vista === v} onClick={() => setVista(v)}
                            className={`px-2 py-0.5 rounded border text-[11px] ${vista === v ? 'bg-amber-400/25 border-amber-400/60 text-amber-100' : 'border-white/15 text-white/60'}`}>
                            {v === 'cicli' ? 'per ciclo e ordine' : 'cronologica'}
                        </button>
                    ))}
                </div>
            </div>
            {analisi.clic.length > 0 && (
                <div className="rounded-lg border border-white/10 p-1.5 space-y-0.5" data-testid="registro-clic">
                    <div className="font-bold text-white/80">Clic «Attiva adesso»</div>
                    {analisi.clic.map(c => (
                        <button key={c.id} type="button" data-testid="registro-clic-voce" data-esito={c.esito}
                            onClick={() => onSeek({ ms: c.seekMs, marketId: c.marketId, selectionId: null })}
                            className="w-full text-left grid grid-cols-[96px_72px_1fr] gap-1 px-1 py-0.5 rounded hover:bg-white/10">
                            <span className="font-mono tabular-nums text-white/60">{ora(c.ms)}</span>
                            <span className="text-white/45 truncate">{quando(c.ms)}</span>
                            <span className={c.eseguito ? 'text-emerald-300' : 'text-red-300 font-bold'}>{c.testo}</span>
                        </button>
                    ))}
                </div>
            )}
            {analisi.ordini.length === 0 ? (
                <div className="text-white/50">Il bot non ha piazzato nessun ordine in questa prova.</div>
            ) : vista === 'tempo' ? (
                <div className="max-h-[420px] overflow-y-auto space-y-0" data-testid="registro-cronologico">
                    {eventi.map(e => (
                        <RigaEvento key={e.id} e={e} attuale={e.id === attuale} futuro={e.ms > nowMs}
                            quando={quando(e.ms)} onSeek={onSeek} mostraOrdine
                            nomeMercato={nomeMercato} nomeSelezione={nomeSelezione} />
                    ))}
                </div>
            ) : (
                <div className="max-h-[520px] overflow-y-auto space-y-2" data-testid="registro-cicli">
                    {vuoti > 0 && (
                        <label className="flex items-center gap-1 text-white/50">
                            <input type="checkbox" checked={nascondiVuoti} onChange={e => setNascondiVuoti(e.target.checked)} />
                            nascondi i {vuoti} cicli senza abbinamenti (ordini messi e tolti)
                        </label>
                    )}
                    {cicli.map(c => {
                        const delBot = cicloDelBot(c, esito.cicli_bot);
                        return (
                            <div key={c.n} className="rounded-lg border border-violet-400/25 bg-violet-500/5 p-1.5" data-testid="registro-ciclo">
                                <button type="button" onClick={() => onSeek({ ms: c.daMs, marketId: c.marketId, selectionId: null })}
                                    className="w-full text-left flex flex-wrap items-center gap-x-2 hover:bg-white/5 rounded px-1">
                                    <span className="font-black text-violet-200">Ciclo {c.n}</span>
                                    <span className="text-white/70">{nomeMercato(c.marketId)}</span>
                                    <span className="font-mono text-white/60">{ora(c.daMs)}{quando(c.daMs) ? ` (${quando(c.daMs)})` : ''} → {c.aMs != null ? `${ora(c.aMs)}${quando(c.aMs) ? ` (${quando(c.aMs)})` : ''}` : 'aperto'}</span>
                                    <span className="text-white/70">{c.origine}</span>
                                    <span className={`font-mono font-bold ${((c.stato === 'regolato' ? c.regolato : c.garantito) ?? 0) >= 0 ? 'text-emerald-300' : 'text-red-300'}`}
                                        data-testid="registro-ciclo-pnl">
                                        P&L {pnl(c.stato === 'regolato' ? c.regolato : c.garantito)}
                                    </span>
                                    {delBot && (
                                        <span className="text-amber-200/90" data-testid="registro-ciclo-bot">
                                            per il bot: {delBot.origine === 'clic' ? 'partito da un clic'
                                                : delBot.origine === 'rientro_automatico' ? 'rientro automatico pre-match' : 'origine non dichiarata'}
                                            {' · '}{delBot.esito} · lordo {pnl(delBot.lordo)} · netto {pnl(delBot.netto)}
                                        </span>
                                    )}
                                </button>
                                <div className="space-y-1 mt-1">
                                    {analisi.ordini.filter(o => o.ciclo === c.n).map(rigaOrdine)}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
