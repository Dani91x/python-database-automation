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
//
// 08/10 (cantiere 10): i cicli sono quelli DEL BOT quando l'esito li porta
// (`cicli_bot`: numero, istanti, origine, lordo/netto), la regola «da piatto a
// piatto» resta solo come ripiego e lo dice; con la fase all'istante
// (`faseIstante`, dalla pagina) il registro si divide in sezioni fisse
// (calcio PRE-PARTITA / 1° TEMPO / INTERVALLO / 2° TEMPO; tennis PRE-PARTITA /
// SET n) con cicli, ordini e P&L della sezione, e in fondo i totali di sempre.
// ============================================================================
import { useMemo, useState } from 'react';
import { testoIstante } from '@/lib/applicaBot';
import type { CicloDichiarato, EsitoBot } from '@/lib/replayBot';
import { fasiFisse, type FaseReplay } from '@/lib/replayFasi';
import {
    eur, eventiDelRegistro, metodoConto, nomeLato, pnl, sezioniPerFase, statoOrdineTesto, testoEvento,
    type CicloOperativo, type CicloRegistro, type EventoOperazione, type OrdineBot,
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
    /** 08/10: la FASE della partita all'istante (sezioni del registro); assente = nessuna sezione */
    faseIstante?: (ms: number) => FaseReplay;
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

const clsPnl = (x: number | null | undefined) => ((x ?? 0) > 0 ? 'text-emerald-300' : (x ?? 0) < 0 ? 'text-red-300' : 'text-white/80');

/** Il ciclo dichiarato dal bot che contiene gli ordini di un ciclo. PURA. */
export function cicloDelBot(c: CicloOperativo, dichiarati: ReadonlyArray<CicloDichiarato> | null | undefined): CicloDichiarato | null {
    if (!dichiarati) return null;
    const ids = new Set(c.ordini.filter(k => k.startsWith('o:')).map(k => k.slice(2)));
    return dichiarati.find(d => (d.ordini_id ?? []).some(id => ids.has(String(id)))) ?? null;
}

/** L'origine di un ciclo del bot per il trader. PURA. */
export function origineDelBot(d: CicloDichiarato): string {
    return d.origine === 'clic' ? 'partito da un clic'
        : d.origine === 'rientro_automatico' ? 'rientro automatico pre-match' : 'origine non dichiarata';
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
    esito, analisi, nowMs, nomeMercato, nomeSelezione, etichettaIstante, faseIstante, onSeek,
}: RegistroOperazioniBotProps) {
    const [vista, setVista] = useState<'cicli' | 'tempo'>('cicli');
    const [mercato, setMercato] = useState<string>('');
    const [nascondiVuoti, setNascondiVuoti] = useState(true);
    const quando = (ms: number) => (etichettaIstante ? etichettaIstante(ms) : '');
    const reg = analisi.registro;
    const mercati = useMemo(() => [...new Set(analisi.ordini.map(o => o.marketId))], [analisi]);
    // con i cicli del bot le chiusure di ciclo sono le sue (08/10)
    const tuttiEventi = useMemo(() => eventiDelRegistro(analisi.eventi, reg), [analisi, reg]);
    const eventi = useMemo(
        () => tuttiEventi.filter(e => !mercato || e.marketId === mercato),
        [tuttiEventi, mercato],
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
    const delMercato = (marketId: string) => !mercato || marketId === mercato;
    const vuoto = (c: CicloRegistro) => c.abbinato <= 0 && c.stato === 'chiuso';
    const visibile = (c: CicloRegistro) => delMercato(c.marketId) && !(nascondiVuoti && vuoto(c));
    const vuoti = reg.cicli.filter(c => delMercato(c.marketId) && vuoto(c)).length;
    const fuoriCiclo = reg.fuoriCiclo.filter(k => delMercato(analisi.perChiave.get(k)?.marketId ?? ''));
    const metodo = metodoConto(esito);
    const sezioni = useMemo(() => {
        if (!faseIstante) return null;
        // il filtro del mercato vale anche per le sezioni (cicli, ordini e P&L della sezione)
        const filtrato = {
            ...reg,
            cicli: reg.cicli.filter(c => !mercato || c.marketId === mercato),
            fuoriCiclo: reg.fuoriCiclo.filter(k => !mercato || analisi.perChiave.get(k)?.marketId === mercato),
        };
        return sezioniPerFase(filtrato, analisi.ordini, faseIstante, fasiFisse(esito.sport === 'tennis' ? 'tennis' : 'calcio'),
            metodo, esito.esiti_mercati ?? null, analisi.aliquota);
    }, [faseIstante, reg, mercato, analisi, esito, metodo]);
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
    const ordiniDi = (chiavi: ReadonlyArray<string>) => chiavi
        .map(k => analisi.perChiave.get(k)).filter((o): o is OrdineBot => o != null);
    const bloccoCiclo = (c: CicloRegistro) => {
        const d = c.dichiarato;
        // 08/10: un ciclo che attraversa due fasi sta in quella in cui e' nato, con la fase della chiusura
        const faseFine = faseIstante && c.aMs != null ? faseIstante(c.aMs) : null;
        const attraversa = faseFine != null && faseIstante != null && faseFine.id !== faseIstante(c.daMs).id;
        return (
            <div key={`${c.fonte}:${c.n}`} className="rounded-lg border border-violet-400/25 bg-violet-500/5 p-1.5" data-testid="registro-ciclo"
                data-ciclo={c.n}>
                <button type="button" onClick={() => onSeek({ ms: c.daMs, marketId: c.marketId || null, selectionId: null })}
                    className="w-full text-left flex flex-wrap items-center gap-x-2 hover:bg-white/5 rounded px-1">
                    <span className="font-black text-violet-200">Ciclo {c.n}</span>
                    <span className="text-white/70">{c.marketId ? nomeMercato(c.marketId) : ''}</span>
                    <span className="font-mono text-white/60">{ora(c.daMs)}{quando(c.daMs) ? ` (${quando(c.daMs)})` : ''} → {c.aMs != null ? `${ora(c.aMs)}${quando(c.aMs) ? ` (${quando(c.aMs)})` : ''}` : 'aperto'}</span>
                    {attraversa && c.aMs != null && (
                        <span className="text-amber-200" data-testid="registro-ciclo-chiuso-al">
                            {c.stato === 'regolato' ? 'regolato' : 'chiuso'} al {quando(c.aMs) || ora(c.aMs)} · {faseFine!.nome}
                        </span>
                    )}
                    {c.operativo && <span className="text-white/70">{c.operativo.origine}</span>}
                    <span className={`font-mono font-bold ${(c.pnl ?? 0) >= 0 ? 'text-emerald-300' : 'text-red-300'}`}
                        data-testid="registro-ciclo-pnl">
                        P&L {pnl(c.pnl)}
                    </span>
                    {d && (
                        <span className="text-amber-200/90" data-testid="registro-ciclo-bot">
                            per il bot: {origineDelBot(d)}
                            {' · '}{d.esito} · lordo {pnl(d.lordo)} · netto {pnl(d.netto)}
                        </span>
                    )}
                </button>
                <div className="space-y-1 mt-1">
                    {ordiniDi(c.ordini).map(rigaOrdine)}
                </div>
            </div>
        );
    };
    const bloccoFuori = (chiavi: ReadonlyArray<string>) => chiavi.length > 0 && (
        <div className="rounded-lg border border-white/15 p-1.5" data-testid="registro-fuori-ciclo">
            <div className="font-bold text-white/70">Ordini fuori dai cicli dichiarati dal bot ({chiavi.length})</div>
            <div className="space-y-1 mt-1">{ordiniDi(chiavi).map(rigaOrdine)}</div>
        </div>
    );
    const totale = metodo === 'cicli' ? analisi.cicliConto : analisi.regolato;
    const riferimento = metodo === 'cicli' ? esito.conto_dichiarato?.netto : esito.conto_banco?.netto;
    const sommaLordo = sezioni ? Math.round(sezioni.reduce((s, x) => s + x.lordo, 0) * 100) / 100 : 0;
    const sommaNetto = sezioni ? Math.round(sezioni.reduce((s, x) => s + x.netto, 0) * 100) / 100 : 0;
    // la vista cronologica divisa per fase (la fase dell'istante dell'evento)
    const testate = useMemo(() => {
        if (!faseIstante) return null;
        const fasi = eventi.map(e => faseIstante(e.ms));
        return fasi.map((f, i) => (i === 0 || fasi[i - 1].id !== f.id ? f : null));
    }, [eventi, faseIstante]);
    const testataFase = (i: number): FaseReplay | null => testate?.[i] ?? null;
    return (
        <div className="rounded-xl border border-amber-400/30 bg-black/30 p-2 text-[11px] space-y-2" data-testid="registro-operazioni">
            <div className="flex flex-wrap items-center gap-2">
                <span className="font-black text-amber-200">📒 Registro operazioni del bot</span>
                <span className="text-white/50">{analisi.ordini.length} ordini · {analisi.eventi.filter(e => e.ordine).length} eventi · {reg.cicli.length} cicli</span>
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
            <div className="text-white/55" data-testid="registro-fonte-cicli" data-fonte={reg.fonte}>
                {reg.fonte === 'bot'
                    ? `cicli: quelli dichiarati dal bot (${reg.cicli.length}), con i suoi numeri, istanti, origine e P&L`
                    : 'cicli: il bot non li dichiara, ricavati dagli ordini (da posizione piatta a posizione piatta)'}
                {reg.mancanti.length > 0 && (
                    <span className="text-red-300 font-bold"> · {reg.mancanti.length} ordini dichiarati dal bot NON trovati nella cronologia</span>
                )}
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
                    {eventi.map((e, i) => {
                        const f = testataFase(i);
                        return (
                            <div key={e.id}>
                                {f && (
                                    <div className="mt-1 px-1 font-black text-amber-200/90 border-b border-amber-400/20"
                                        data-testid="registro-fase-cronologica" data-fase={f.id}>{f.nome}</div>
                                )}
                                <RigaEvento e={e} attuale={e.id === attuale} futuro={e.ms > nowMs}
                                    quando={quando(e.ms)} onSeek={onSeek} mostraOrdine
                                    nomeMercato={nomeMercato} nomeSelezione={nomeSelezione} />
                            </div>
                        );
                    })}
                </div>
            ) : (
                <div className="max-h-[520px] overflow-y-auto space-y-2" data-testid="registro-cicli">
                    {vuoti > 0 && (
                        <label className="flex items-center gap-1 text-white/50">
                            <input type="checkbox" checked={nascondiVuoti} onChange={e => setNascondiVuoti(e.target.checked)} />
                            nascondi i {vuoti} cicli senza abbinamenti (ordini messi e tolti)
                        </label>
                    )}
                    {sezioni ? (
                        <>
                            {sezioni.map(s => (
                                <div key={s.fase.id} className="space-y-1" data-testid="registro-fase" data-fase={s.fase.id}>
                                    <div className="flex flex-wrap items-center gap-x-2 border-b border-amber-400/30 px-1">
                                        <span className="font-black text-amber-200">{s.fase.nome}</span>
                                        <span className="text-white/60">{s.cicli.length} cicli · {s.ordini} ordini</span>
                                        <span data-testid="registro-fase-pnl">
                                            {metodo === 'cicli' ? 'dei cicli' : 'a regolamento'}: lordo <b className={`font-mono ${clsPnl(s.lordo)}`}>{pnl(s.lordo)}</b>
                                            {' · '}netto <b className={`font-mono ${clsPnl(s.netto)}`}>{pnl(s.netto)}</b>
                                            {s.cicliEsitoIgnoto > 0 ? ` · ${s.cicliEsitoIgnoto} cicli con esito ignoto (fuori dal conto)` : ''}
                                        </span>
                                    </div>
                                    {s.cicli.length === 0 && s.fuoriCiclo.length === 0 && (
                                        <div className="text-white/40 px-1">nessuna operazione in questa fase</div>
                                    )}
                                    {s.cicli.filter(visibile).map(bloccoCiclo)}
                                    {bloccoFuori(s.fuoriCiclo)}
                                </div>
                            ))}
                            <div className="flex flex-wrap items-center gap-x-3 border-t border-amber-400/30 pt-1 px-1" data-testid="registro-totale">
                                <span className="font-black text-amber-200">TOTALE{mercato ? ' della prova (tutti i mercati)' : ''}</span>
                                <span className="text-white/60">{metodo === 'cicli' ? 'dei cicli (metodo del bot)' : 'a regolamento'}:</span>
                                <span>lordo <b className={`font-mono ${clsPnl(totale.lordo)}`}>{pnl(totale.lordo)}</b></span>
                                <span>commissione <b className="font-mono">{eur(totale.commissione)}</b></span>
                                <span>NETTO <b className={`font-mono ${clsPnl(totale.netto)}`} data-testid="registro-totale-netto">{pnl(totale.netto)}</b></span>
                                {riferimento != null && (
                                    <span className={Math.abs(totale.netto - riferimento) < 0.005 ? 'text-emerald-300/80' : 'text-red-300 font-bold'}
                                        data-testid="confronto-banco" data-ok={Math.abs(totale.netto - riferimento) < 0.005 ? '1' : '0'}>
                                        {Math.abs(totale.netto - riferimento) < 0.005
                                            ? `✓ uguale ${metodo === 'cicli' ? 'al referto del bot' : 'al banco'} (${pnl(riferimento)})`
                                            : `≠ ${metodo === 'cicli' ? 'al referto del bot' : 'al banco'}: ${pnl(riferimento)}`}
                                    </span>
                                )}
                                {!mercato && (sommaLordo !== totale.lordo || sommaNetto !== totale.netto) && (
                                    <span className="text-white/50" data-testid="registro-totale-nota">
                                        somma delle fasi: lordo {pnl(sommaLordo)} · netto {pnl(sommaNetto)} (la commissione si
                                        calcola sul totale, gli arrotondamenti al centesimo per fase)
                                    </span>
                                )}
                            </div>
                        </>
                    ) : (
                        <>
                            {reg.cicli.filter(visibile).map(bloccoCiclo)}
                            {bloccoFuori(fuoriCiclo)}
                        </>
                    )}
                </div>
            )}
        </div>
    );
}
