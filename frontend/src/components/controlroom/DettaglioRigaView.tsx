// ============================================================================
// DettaglioRigaView.tsx — COME SI MOSTRA il dettaglio di una riga.
//
// I numeri li calcola `dettaglioRiga.ts` (che a sua volta non calcola niente di
// nuovo: chiama le funzioni delle pagine originali). Qui c'è solo il montaggio,
// con le regole del design system: i soldi da `fmtMoney`, le quote da
// `fmtOdds`, le percentuali da `fmtPct`, e ciò che non c'è è `—`, mai 0,00 €.
//
// Gli stessi pezzi servono a DUE posti — la colonna delle posizioni aperte e la
// scheda della partita — perché è la stessa posizione: mostrarla con due
// vocabolari diversi nella stessa pagina è il modo più veloce per far sbagliare
// un trader.
// ============================================================================
import { ChevronRight } from 'lucide-react';
import { fmtMoney, fmtOdds, fmtPct, fmtTime, fmtAge, DASH } from '@/lib/format';
import { isSettled } from '@/lib/eventGroups';
import { StrisciaEsitoChiusura } from '@/components/controlroom/StrisciaEsitoChiusura';
import { pnlClass } from '@/lib/tradeStatus';
import { comeLabel, marcatoreRiga } from '@/lib/chiusuraUtente';
import { StatoOrdineCompatto } from '@/components/trading/StatoOrdine';
import { isBotTennis } from '@/lib/controlRoom';
import type { DettaglioRiga, QuotaViva } from '@/components/controlroom/dettaglioRiga';
import type { OperazionePartita } from '@/components/controlroom/useControlRoom';

/** Badge di stato ricco: lo stesso di Omega e Safe, stessa etichetta italiana. */
export function BadgeStato({ d, testId = 'cr-stato-riga' }: { d: DettaglioRiga; testId?: string }) {
    return (
        <span
            className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded border ${d.stato.cls}`}
            data-testid={testId}
        >{d.stato.label}</span>
    );
}

/** Minuto e punteggio AL MOMENTO DELL'INGRESSO: dicono a che partita il bot è
 *  entrato, che non è quella di adesso. Nessuno dei due c'è → niente riga. */
export function Ingresso({ d, testId = 'cr-ingresso' }: { d: DettaglioRiga; testId?: string }) {
    if (d.ingresso.minuto == null && d.ingresso.punteggio == null) return null;
    return (
        <span className="text-[10px] text-white/40" data-testid={testId}
            title="minuto e punteggio al momento dell'ingresso">
            ingresso <span className="text-white/65">
                {d.ingresso.minuto != null ? `${d.ingresso.minuto}′` : ''}
                {d.ingresso.punteggio ? ` ${d.ingresso.punteggio}` : ''}
            </span>
        </span>
    );
}

/** Quota d'ingresso → quota di ADESSO → tick di movimento. */
export function QuotaOra({ v, testId = 'cr-quota-viva' }: { v: QuotaViva; testId?: string }) {
    return (
        <span className="text-[10px] text-white/40 tabular-nums" data-testid={testId}
            title="miglior BACK e miglior LAY di adesso sulla stessa selezione, dal feed di scansione">
            ora <span className="text-teal-300 font-mono">B {fmtOdds(v.back)}</span>
            <span className="text-white/25"> / </span>
            <span className="text-sky-300 font-mono">L {fmtOdds(v.lay)}</span>
            {v.tick != null && (
                <span className={`ml-1 font-mono ${v.tick > 0 ? 'text-emerald-400' : v.tick < 0 ? 'text-red-400' : 'text-white/40'}`}
                    data-testid={`${testId}-tick`}
                    title="tick di movimento dall'ingresso: positivo = a favore della posizione">
                    {v.tick > 0 ? '+' : ''}{v.tick} tick
                </span>
            )}
        </span>
    );
}

const PNL_LABEL: Record<DettaglioRiga['pnlVivo']['stato'], string> = {
    settled: 'regolato',
    locked: 'bloccato',
    partial: 'caso peggiore',
    open: 'aperto',
    none: 'nessun P&L',
};

/**
 * P&L VIVO. La Control Room mostrava un numero SOLO a regolamento avvenuto:
 * una posizione già coperta (P&L ormai certo) restava senza numero. Qui si
 * dice anche COSA è quel numero — regolato, bloccato, caso peggiore — perché
 * un «bloccato» e un «aperto» non si leggono allo stesso modo.
 */
export function PnlVivo({ d, testId = 'cr-pnl-vivo' }: { d: DettaglioRiga; testId?: string }) {
    if (d.pnlVivo.stato === 'none' || (d.pnlVivo.stato === 'open' && d.pnlVivo.valore == null)) {
        return (
            <span className="text-[10px] text-white/30" data-testid={testId} data-stato={d.pnlVivo.stato}>
                P&amp;L {DASH}
            </span>
        );
    }
    return (
        <span className="text-[10px] tabular-nums" data-testid={testId} data-stato={d.pnlVivo.stato}
            title={`P&L ${PNL_LABEL[d.pnlVivo.stato]}`}>
            <span className="text-white/40">{PNL_LABEL[d.pnlVivo.stato]} </span>
            <span className={`font-mono font-semibold ${pnlClass(d.pnlVivo.valore)}`}>
                {d.pnlVivo.valore == null ? DASH : fmtMoney(d.pnlVivo.valore, { signed: true })}
            </span>
        </span>
    );
}

/** Copertura: quanto della posizione è già chiuso e quanto rischia ancora. */
export function Copertura({ d, testId = 'cr-copertura-riga' }: { d: DettaglioRiga; testId?: string }) {
    if (!d.copertura) return null;
    const pct = d.copertura.frazione == null ? null : Math.round(d.copertura.frazione * 100);
    return (
        <span className="text-[10px] text-white/40" data-testid={testId}
            data-completa={d.copertura.completa ? '1' : undefined}
            title="quota di stake già coperta e responsabilità ancora a rischio">
            coperta <span className="text-white/65">{pct == null ? DASH : `${pct} %`}</span>
            {d.copertura.residua != null && (
                <span className="text-white/30"> · a rischio <span className="font-mono">{fmtMoney(d.copertura.residua)}</span></span>
            )}
        </span>
    );
}

/** Badge green-up del servizio: stato, motivo, tentativi — mai una deduzione. */
export function Greenup({ d, testId = 'cr-greenup' }: { d: DettaglioRiga; testId?: string }) {
    if (!d.greenup) return null;
    return (
        <span className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded border ${d.greenup.cls}`}
            data-testid={testId} data-stato={d.greenup.state} title={d.greenup.title}>
            {d.greenup.label}
        </span>
    );
}

/** P(perdita) del MODELLO contro quella implicita nel MERCATO (Omega). */
export function ModelloP({ d, testId = 'cr-modello-p' }: { d: DettaglioRiga; testId?: string }) {
    if (!d.modello) return null;
    return (
        <span className="text-[10px] text-white/40 tabular-nums" data-testid={testId}
            title="P(perdita) secondo il modello del bot contro quella implicita nella quota LAY di adesso (1/quota)">
            P(perdita) <span className="text-white/70">{fmtPct(d.modello.pModello)}</span>
            <span className="text-white/25"> · mercato </span>
            <span className="text-white/60">{fmtPct(d.modello.pMercato)}</span>
            {d.modello.margine != null && (
                <span className={`ml-1 ${d.modello.margine > 0 ? 'text-emerald-400' : 'text-red-400'}`}
                    data-testid={`${testId}-margine`}
                    title="mercato − modello: positivo = il mercato paga più del rischio che il modello vede">
                    {d.modello.margine > 0 ? '+' : ''}{fmtPct(d.modello.margine)}
                </span>
            )}
        </span>
    );
}

/** L'uscita dichiarata dal servizio (`meta.exit_kind`). */
export function Uscita({ d, testId = 'cr-uscita' }: { d: DettaglioRiga; testId?: string }) {
    if (!d.uscita) return null;
    return (
        <span className="text-[9px] uppercase tracking-wider px-1 rounded bg-teal-500/15 text-teal-300"
            data-testid={testId} title="tipo di uscita dichiarato dal servizio">
            {ETICHETTA_USCITA[d.uscita] ?? d.uscita.replace(/_/g, ' ')}
        </span>
    );
}

const ETICHETTA_USCITA: Record<string, string> = {
    greenup: 'green-up',
    cashout: 'cash out',
    manual: 'manuale',
    market_close: 'chiusura a mercato',
    stop: 'stop',
};

/**
 * Le RIGHE DI CHIUSURA, ANNIDATE sotto la posizione che chiudono (Task 4,
 * 18/09). Prima erano riassunte in un solo numero (`Copertura`: "coperta X% ·
 * a rischio Y"); qui si vede CON QUALE ordine — lato, prezzo, size, quando —
 * la copertura è avvenuta, una riga per gamba di chiusura.
 */
export function Chiusure({ d, testId = 'cr-chiusure' }: { d: DettaglioRiga; testId?: string }) {
    if (!d.chiusure.length) return null;
    return (
        <div className="basis-full pl-4 mt-0.5 space-y-0.5 border-l border-white/8" data-testid={testId}>
            {d.chiusure.map((c, i) => (
                <div key={i} className="flex items-baseline gap-1.5 text-[10px] flex-wrap"
                    data-testid={`${testId}-riga`}>
                    <span className="text-white/25">↳</span>
                    <span className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded ${
                        c.lato === 'lay' ? 'bg-pink-500/15 text-pink-300' : 'bg-sky-500/15 text-sky-300'
                    }`}>{c.lato === 'lay' ? 'banca' : c.lato === 'back' ? 'punta' : DASH}</span>
                    <span className="font-mono text-white/60">{fmtOdds(c.prezzo)}</span>
                    <span className="font-mono text-white/45">{c.size == null ? DASH : fmtMoney(c.size)}</span>
                    <span className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded border ${c.stato.cls}`}>
                        {c.stato.label}
                    </span>
                    {c.uscita && (
                        <span className="text-[9px] uppercase tracking-wider px-1 rounded bg-teal-500/15 text-teal-300">
                            {ETICHETTA_USCITA[c.uscita] ?? c.uscita.replace(/_/g, ' ')}
                        </span>
                    )}
                    <span className={`ml-auto font-mono font-semibold ${pnlClass(c.pnl)}`}>
                        {c.pnl == null ? DASH : fmtMoney(c.pnl, { signed: true })}
                    </span>
                </div>
            ))}
        </div>
    );
}

// ============================================================================
// RigaOperazione — LA RIGA DI UNA POSIZIONE, condivisa (18/09, secondo giro).
//
// PERCHÉ ESISTE. L'utente ha chiesto "stesso ordine in tutte le tab" per i
// campi di ogni posizione: lato, selezione, quota, importo, chiesto/abbinato/
// residuo/medio, strategia, modalità, marcatore, P&L, orario, poi il
// dettaglio (stato ricco/green-up/uscita/ingresso/copertura/P&L vivo/modello/
// chiusure annidate). Prima questa riga era scritta UNA VOLTA SOLA dentro
// `SchedaPartita.tsx`: `SchedaPreMatch.tsx` non la montava affatto. Due
// scritture della stessa riga in due file avrebbero potuto divergere (un
// campo aggiunto in un posto e dimenticato nell'altro) — la stessa classe di
// errore che il design system vieta per i formati. Un solo componente,
// usato da entrambe le schede, la esclude per costruzione.
// ============================================================================

/** Le chiavi del database NON si mostrano al trader (stessa lista di prima,
 *  spostata qui perché la riga che le usa ora vive qui). */
const STRATEGIA_LABEL: Record<string, string> = {
    ht_cs: 'risultato esatto 1° tempo',
    ft_cs: 'risultato esatto finale',
    base: 'base',
    esatto: 'risultato esatto',
    punta: 'punta',
    tennis: 'tennis',
    under_entry: 'ingresso Under 3.5',
    over_cover: 'copertura Over 4.5',
    under_green: 'green-up Under',
    ko_green: 'green-up al fischio',
};

function etichettaStrategia(k: string): string {
    return STRATEGIA_LABEL[k.toLowerCase()] ?? k.toLowerCase().replace(/_/g, ' ');
}

/** Il badge «chiusa da te» di UNA riga: lo accende il marcatore che il
 *  servizio ha scritto nel `meta`, mai una deduzione della pagina. */
function MarcatoreRigaOp({ meta }: { meta: Record<string, unknown> | null }) {
    const m = marcatoreRiga({ meta });
    if (!m) return null;
    return (
        <span className="text-[9px] px-1 rounded bg-amber-500/20 text-amber-300"
            data-testid="cr-riga-chiusa-da-te"
            title={[comeLabel(m.come) ?? 'chiusa da te',
                m.quando ? `alle ${fmtTime(m.quando)}` : 'istante non dichiarato'].join(' · ')}>
            chiusa da te
        </span>
    );
}

/**
 * UNA riga di posizione, con tutti i campi SEMPRE visibili senza espandere
 * nulla (richiesta utente 18/09): lato, selezione, quota chiesta, importo,
 * chiesto/abbinato/residuo/medio (`StatoOrdineCompatto`), strategia,
 * modalità, marcatore, P&L, orario — poi, se il bot pubblica il dettaglio
 * ricco (Omega/Safe), stato/green-up/uscita/ingresso/copertura/P&L vivo/
 * modello/chiusure annidate.
 */
export function RigaOperazione({ o, testId = 'cr-op', nomeSelezioneRisolto = null }: {
    o: OperazionePartita; testId?: string;
    /**
     * TASK A2 (18/09, raccordo) — per i 4 bot tennis `o.selezione` è sempre
     * `null` (il servizio non lo pubblica): il chiamante risolve il nome dal
     * feed tennis vivo (`nomeSelezioneTennis(row, o.selectionId)`, STESSA
     * sottoscrizione condivisa di `TennisVivoBar`) e lo passa qui GIÀ pronto.
     * `null` = non risolvibile: resta `—`, col motivo nel title.
     */
    nomeSelezioneRisolto?: string | null;
}) {
    const nome = o.selezione ?? nomeSelezioneRisolto;
    return (
        <div className="flex items-baseline gap-1.5 text-[11px] flex-wrap" data-testid={`${testId}-riga`}>
            <ChevronRight className="w-2.5 h-2.5 text-white/25 shrink-0" />
            <span className={`text-[9px] font-bold uppercase tracking-wider px-1 rounded ${
                o.lato === 'lay' ? 'bg-pink-500/15 text-pink-300' : 'bg-sky-500/15 text-sky-300'
            }`}>{o.lato === 'lay' ? 'banca' : 'punta'}</span>
            <span className="text-white/75 truncate max-w-[9rem]"
                title={nome != null ? undefined
                    : isBotTennis(o.bot)
                        ? 'il servizio non pubblica il nome per questo bot e il feed tennis vivo non conosce ancora questa selezione'
                        : 'il servizio non pubblica il nome della selezione per questo bot'}>
                {nome ?? DASH}
            </span>
            <span className="font-mono text-white/60"
                title={o.prezzo == null ? 'prezzo chiesto non dichiarato dal servizio' : 'prezzo chiesto'}>
                {fmtOdds(o.prezzo)}
            </span>
            <span className="font-mono text-white/45"
                title={o.size == null ? 'importo non dichiarato dal servizio' : undefined}>
                {fmtMoney(o.size)}
            </span>
            {/* chiesto / abbinato / residuo / prezzo medio, con la fonte nel title.
                testid FISSO `cr-stato-ordine` (non derivato da `testId`): e' il
                contratto gia' verificato da `StatoOrdine.montaggio.test.tsx`
                (fuori dal mio perimetro) — mai rimuovere un testid esistente. */}
            <StatoOrdineCompatto riga={o.ordine} testId="cr-stato-ordine" />
            {/* 18/09 (raccordo, R1) — responsabilita' di QUESTA riga, quota
                di ADESSO (tick+eta') e "se chiudo ora": STESSE funzioni gia'
                usate per `PosizioneAperta` (`quotaViva`/`chiusuraViva`),
                nessuna seconda formula. */}
            {o.liability != null && (
                <span className="font-mono text-orange-400 text-[10px]"
                    title="responsabilita' impegnata da questa posizione">
                    resp. {fmtMoney(o.liability)}
                </span>
            )}
            {o.vivo && <QuotaOra v={o.vivo} testId={`${testId}-quota-viva`} />}
            {o.vivo && o.etaQuoteS != null && (
                <span className="text-[9px] text-white/30 font-mono" title="eta' del prezzo di adesso">
                    {fmtAge(o.etaQuoteS)}
                </span>
            )}
            {o.chiusura && (
                <span className="text-[10px] text-white/40 flex items-baseline gap-1" data-testid={`${testId}-chiudo-ora`}
                    title="quanto varrebbe chiudere ADESSO, per intero, al prezzo corrente">
                    chiudi ora
                    {o.chiusura.prezzo == null ? (
                        <span className="text-orange-400">{DASH}</span>
                    ) : (
                        <span className={`font-mono font-semibold ${pnlClass(o.chiusura.bloccabile)}`}>
                            {fmtMoney(o.chiusura.bloccabile, { signed: true })}
                        </span>
                    )}
                </span>
            )}
            {o.quale && (
                <span className="text-[9px] text-white/30 uppercase"
                    title="la regola che ha prodotto questa operazione">
                    {etichettaStrategia(o.quale)}
                </span>
            )}
            {o.modalita === 'live'
                ? <span className="text-[9px] px-1 rounded bg-orange-500/20 text-orange-300"
                    title="soldi VERI">live</span>
                : <span className="text-[9px] px-1 rounded bg-white/8 text-white/35"
                    title="simulazione: non sono soldi veri">paper</span>}
            <MarcatoreRigaOp meta={o.ordine.meta ?? null} />
            <span className={`ml-auto font-mono font-semibold ${pnlClass(o.pnl)}`}
                title={o.pnl == null ? 'non ancora regolata: nessun risultato certo, non è uno zero' : 'P&L netto di commissione'}>
                {o.pnl == null ? DASH : fmtMoney(o.pnl, { signed: true })}
            </span>
            <span className="text-[9px] text-white/25 font-mono">{fmtTime(o.at)}</span>
            {o.dettaglio && (
                <div className="basis-full pl-4 flex items-baseline gap-x-2 gap-y-0.5 flex-wrap"
                    data-testid={`${testId}-dettaglio`}>
                    <BadgeStato d={o.dettaglio} testId={`${testId}-stato`} />
                    <Greenup d={o.dettaglio} testId={`${testId}-greenup`} />
                    <Uscita d={o.dettaglio} testId={`${testId}-uscita`} />
                    <Ingresso d={o.dettaglio} testId={`${testId}-ingresso`} />
                    <Copertura d={o.dettaglio} testId={`${testId}-copertura`} />
                    <PnlVivo d={o.dettaglio} testId={`${testId}-pnl-vivo`} />
                    <ModelloP d={o.dettaglio} testId={`${testId}-modello`} />
                    <Chiusure d={o.dettaglio} testId={`${testId}-chiusure`} />
                    {/* 18/09 (raccordo, R3) — la CERTEZZA di chiusura di F4
                        (`StrisciaEsitoChiusura`, riusata cosi' com'e', nessuna
                        seconda formula), accanto a ogni posizione con
                        chiusure: "inviata -> a mercato -> CONFERMATA/
                        PARZIALE/FALLITA". */}
                    {o.chiusureOrdini.length > 0 && (
                        <StrisciaEsitoChiusura
                            apertura={o.ordine}
                            chiusure={o.chiusureOrdini}
                            regolataDalMercato={isSettled(o.stato) && o.chiusureOrdini.every((c) => isSettled(c.status))}
                            modo={o.modalita ?? 'paper'}
                            testId={`${testId}-esito`}
                        />
                    )}
                </div>
            )}
        </div>
    );
}
