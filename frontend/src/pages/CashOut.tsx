// ============================================================================
// CashOut.tsx - 08/10 (cantiere W1): la pagina «Cash Out», subito sotto la
// Control Room. Un RACCOGLITORE delle operazioni aperte adesso, una scatola
// per partita con tutte le sue gambe (Mike con 3 gambe = una scatola, 3 righe),
// il cash out di ogni gamba e quello della posizione intera.
//
// «ABBIAMO GIA TUTTI I COMPONENTI: LIMITA AL MINIMO IL CODICE» (utente, 08/10):
//   * i dati: UNA chiamata a `useControlRoom()` (le stesse letture e gli stessi
//     canali della Control Room; le due pagine non sono mai montate insieme).
//     Nessuna lettura nuova;
//   * i contesti delle righe: `ContestiRigheBanco` (gli stessi della Control
//     Room): senza, il «Chiudi» di riga e «Chiudi tutte le gambe» non si montano;
//   * le partite e le loro fasi: `aperte/cashOutPagina.ts` (regole pure);
//   * la scatola: `aperte/ScatolaCashOut.tsx` (pezzi gia' esistenti).
// Filtri in testata: sport (Calcio / Tennis), fase (Pre-match / Live) e soldi
// (Live e prova / Solo live / Solo prova), con la logica delle tessere sport
// della Control Room (`SplitSport`): un clic sceglie, un secondo clic sullo
// stesso toglie, niente di scelto = tutto.
// Secondo giro (08/10): in testa le due cifre «Se chiudo tutto adesso», LIVE e
// PROVA, MAI sommate: le riporta ogni scatola (la cifra che ha GIA' calcolato),
// la pagina somma solo se tutte sono calcolabili (fail-closed).
// LIVE e PROVA non si sommano mai; calcio e tennis non si mischiano.
// ============================================================================
import { useCallback, useMemo, useState } from 'react';
import { Card } from '@/components/ui/card';
import { PageShell } from '@/components/trading/PageShell';
import { EmptyState } from '@/components/trading/EmptyState';
import { MarchioSoldi } from '@/components/controlroom/MarchioSoldi';
import { useControlRoom } from '@/components/controlroom/useControlRoom';
import { ContestiRigheBanco, SORGENTE_LADDER_RIGHE } from '@/components/controlroom/aperte/PosizioniAperte';
import {
    contaPerModalita, filtraScatole, ordinaScatole, scatoleCashOut, sezioneScatola, totaleModalita,
    type ScatolaCashOut as Scatola, type SportScatola, type TotaleModalita,
} from '@/components/controlroom/aperte/cashOutPagina';
import { ScatolaCashOut, type SafeScatola } from '@/components/controlroom/aperte/ScatolaCashOut';
import type { SintesiCashOut } from '@/components/controlroom/useCashOutPartita';
import { useRitornoAlPunto } from '@/lib/ritorno';
import { fmtMoney } from '@/lib/format';
import { pnlClass } from '@/lib/tradeStatus';
import type { ControlRoomVM } from '@/components/controlroom/useControlRoom';

type FaseFiltro = 'pre' | 'live';
type SoldiFiltro = 'live' | 'prova';

/**
 * Un gruppo di pulsanti-filtro con la logica delle tessere sport della
 * Control Room: clic = scegli, clic sullo stesso = togli (`null` = tutti).
 * `tutti` (facoltativo) = un primo pulsante che dice lo stato «niente di
 * scelto» e ci riporta.
 */
function Filtro<K extends string>({ voci, scelto, onScegli, etichetta, testId, tutti }: {
    voci: readonly { k: K; testo: string }[];
    scelto: K | null;
    onScegli: (k: K | null) => void;
    etichetta: string;
    testId: string;
    tutti?: string;
}) {
    const cls = (attivo: boolean) => `h-7 px-3 text-[11px] uppercase tracking-wider ${attivo
        ? 'bg-white/15 text-white font-semibold' : 'text-white/55 hover:text-white'}`;
    return (
        <div className="inline-flex rounded border border-white/10 overflow-hidden" role="group" aria-label={etichetta}
            data-testid={testId}>
            {tutti && (
                <button type="button" aria-pressed={scelto == null} data-testid={`${testId}-tutti`}
                    onClick={() => onScegli(null)} className={cls(scelto == null)}>
                    {tutti}
                </button>
            )}
            {voci.map((v) => (
                <button key={v.k} type="button" aria-pressed={scelto === v.k}
                    data-testid={`${testId}-${v.k}`}
                    onClick={() => onScegli(scelto === v.k ? null : v.k)}
                    className={`${cls(scelto === v.k)} ${scelto != null && scelto !== v.k ? 'opacity-60' : ''}`}>
                    {v.testo}
                </button>
            ))}
        </div>
    );
}

const VOCI_SPORT = [{ k: 'calcio', testo: '⚽ Calcio' }, { k: 'tennis', testo: '🎾 Tennis' }] as const;
const VOCI_FASE = [{ k: 'pre', testo: 'Pre-match' }, { k: 'live', testo: 'Live' }] as const;
const VOCI_SOLDI = [{ k: 'live', testo: 'Solo live' }, { k: 'prova', testo: 'Solo prova' }] as const;

/** «Se chiudo tutto adesso» di UNA modalita': la somma, «non calcolabile» col motivo, o «—». */
function TesseraTotale({ modo, t, gambe, partite, testId }: {
    modo: 'LIVE' | 'PROVA'; t: TotaleModalita; gambe: number; partite: number; testId: string;
}) {
    return (
        <div className="rounded border border-white/10 bg-white/[0.02] px-3 py-2 min-w-[14rem]" data-testid={testId}
            data-stato={t.stato}>
            <div className="text-[10px] uppercase tracking-wider text-white/55 flex items-center gap-1.5">
                <span className={modo === 'LIVE' ? 'text-red-300 font-bold' : 'text-sky-300 font-bold'}>{modo}</span>
                Se chiudo tutto adesso
            </div>
            {t.stato === 'ok' && t.netto != null ? (
                <div className="flex items-baseline gap-1.5 flex-wrap">
                    <span className={`font-mono text-[17px] font-bold tabular-nums ${pnlClass(t.netto)}`} data-testid={`${testId}-netto`}>
                        {fmtMoney(t.netto, { signed: true })}
                    </span>
                    <MarchioSoldi fonte={modo === 'LIVE' ? 'pagina' : 'prova'} etaS={t.etaIgnota ? null : t.etaPrezziS ?? undefined}
                        dettaglio="somma delle cifre delle scatole mostrate, ciascuna netta di commissione; eta' = il prezzo piu' vecchio usato"
                        testId={`${testId}-marchio`} />
                </div>
            ) : t.stato === 'non-calcolabile' ? (
                <div className="text-[11px] font-semibold text-orange-400" data-testid={`${testId}-non-calcolabile`}
                    title={t.motivi.join('\n')}>
                    NON CALCOLABILE: {t.motivi.join(' · ')}
                </div>
            ) : (
                <div className="font-mono text-[15px] text-white/40" data-testid={`${testId}-vuoto`}>
                    {t.stato === 'calcolo' ? 'in calcolo…' : '—'}
                </div>
            )}
            <div className="text-[10px] text-white/45" data-testid={`${testId}-conta`}>
                {gambe} {gambe === 1 ? 'gamba aperta' : 'gambe aperte'} su {partite} {partite === 1 ? 'partita' : 'partite'}
                {' · '}{modo === 'LIVE' ? 'netto commissione' : 'mai sommato al live'}
            </div>
        </div>
    );
}

function Sezione({ titolo, testId, scatole, vuoto, vm, safe, riporta }: {
    titolo: string;
    testId: string;
    scatole: Scatola[];
    vuoto: string;
    vm: ControlRoomVM;
    safe: SafeScatola;
    riporta: (eventId: string, x: SintesiCashOut | null | undefined) => void;
}) {
    return (
        <section className="space-y-2" data-testid={testId}>
            <h2 className="text-[11px] uppercase tracking-wider text-white/60 flex items-center gap-2">
                {titolo}
                <span className="font-mono text-white/40" data-testid={`${testId}-conta`}>
                    {scatole.length} {scatole.length === 1 ? 'partita' : 'partite'}
                </span>
            </h2>
            {scatole.length === 0 ? (
                <div className="text-[11px] text-white/40" data-testid={`${testId}-vuota`}>{vuoto}</div>
            ) : scatole.map((s) => (
                <ScatolaCashOut key={s.eventId} s={s} mike={vm.mikeEventi.get(s.eventId) ?? null} safe={safe}
                    sorgente={SORGENTE_LADDER_RIGHE} nowMs={vm.nowMs}
                    onSintesi={(x) => riporta(s.eventId, x)} />
            ))}
        </section>
    );
}

export default function CashOut() {
    const vm = useControlRoom();
    const [sport, setSport] = useState<SportScatola | null>(null);
    const [fase, setFase] = useState<FaseFiltro | null>(null);
    const [soldi, setSoldi] = useState<SoldiFiltro | null>(null);
    // tornando da Statistiche: si riporta in vista la partita di partenza
    useRitornoAlPunto('/cash-out', !vm.caricamento);

    const scatole = useMemo(() => scatoleCashOut({
        giornata: vm.giornata, posizioni: vm.posizioni, operazioni: vm.operazioni,
        mikeEventi: vm.mikeEventi, ordiniConto: vm.ordiniConto, nowMs: vm.nowMs,
    }), [vm.giornata, vm.posizioni, vm.operazioni, vm.mikeEventi, vm.ordiniConto, vm.nowMs]);
    const visibili = useMemo(() => filtraScatole(scatole, { sport, fase, soldi }), [scatole, sport, fase, soldi]);
    // 08/10 sera (D-6): ogni scatola in UNA sezione (`sezioneScatola`): le
    // concluse (Match Odds CHIUSO, posizioni da regolare) hanno la loro
    const inGioco = useMemo(() => ordinaScatole(visibili.filter((s) => sezioneScatola(s) === 'gioco')), [visibili]);
    const pre = useMemo(() => ordinaScatole(visibili.filter((s) => sezioneScatola(s) === 'pre')), [visibili]);
    const concluse = useMemo(() => ordinaScatole(visibili.filter((s) => sezioneScatola(s) === 'concluse')), [visibili]);
    // le cifre che le scatole MOSTRATE hanno gia' calcolato (una scatola smontata esce)
    const [sintesi, setSintesi] = useState<ReadonlyMap<string, SintesiCashOut | null>>(new Map());
    const riporta = useCallback((eventId: string, x: SintesiCashOut | null | undefined) => {
        setSintesi((prima) => {
            if (x === undefined) {
                if (!prima.has(eventId)) return prima;
                const n = new Map(prima); n.delete(eventId); return n;
            }
            if (prima.has(eventId) && JSON.stringify(prima.get(eventId)) === JSON.stringify(x)) return prima;
            const n = new Map(prima); n.set(eventId, x); return n;
        });
    }, []);
    const totLive = useMemo(() => totaleModalita(visibili, sintesi, 'live'), [visibili, sintesi]);
    const totProva = useMemo(() => totaleModalita(visibili, sintesi, 'paper'), [visibili, sintesi]);
    const conta = useMemo(() => contaPerModalita(visibili), [visibili]);
    const safe: SafeScatola = {
        // la modalita' la DICHIARA il servizio: non dichiarata NON vale «paper»
        modalita: vm.bots.find((b) => b.bot === 'safe')?.modalita ?? null,
        statoChiusura: vm.statoChiusura,
        onCashOut: vm.cashOutEvento,
        onRiprendi: vm.riprendiEvento,
    };

    return (
        <PageShell
            title="Cash Out"
            footer="Fonti: posizioni e righe dai servizi dei bot, ordini fuori dai bot dal conto Betfair (specchio degli ordini); le cifre «se chiudo ora» le calcola la pagina ai prezzi di adesso (STIMA), LIVE e PROVA mai sommati."
        >
            <div className="flex items-center gap-3 flex-wrap" data-testid="co-testata-pagina">
                <h1 className="font-semibold tracking-wide text-white/90">Cash Out</h1>
                <span className="text-[11px] text-white/45">operazioni aperte adesso, una scatola per partita</span>
                <div className="ml-auto flex items-center gap-2 flex-wrap" data-testid="co-filtri">
                    <Filtro voci={VOCI_SPORT} scelto={sport} onScegli={setSport} etichetta="Sport" testId="co-filtro-sport" />
                    <Filtro voci={VOCI_FASE} scelto={fase} onScegli={setFase} etichetta="Fase" testId="co-filtro-fase" />
                    <Filtro voci={VOCI_SOLDI} scelto={soldi} onScegli={setSoldi} etichetta="Soldi" testId="co-filtro-soldi"
                        tutti="Live e prova" />
                </div>
            </div>

            <div className="flex items-stretch gap-3 flex-wrap" data-testid="co-riepilogo">
                <TesseraTotale modo="LIVE" t={totLive} gambe={conta.live.gambe} partite={conta.live.partite} testId="co-totale-live" />
                <TesseraTotale modo="PROVA" t={totProva} gambe={conta.paper.gambe} partite={conta.paper.partite} testId="co-totale-prova" />
                <div className="rounded border border-white/10 bg-white/[0.02] px-3 py-2 text-[11px] text-white/50"
                    data-testid="co-riepilogo-fasi">
                    <div className="text-[10px] uppercase tracking-wider text-white/55">Partite mostrate</div>
                    <div className="font-mono text-[15px] text-white/80" data-testid="co-riepilogo-fasi-conta">
                        {inGioco.length} in gioco · {pre.length} pre-match · {concluse.length} {concluse.length === 1 ? 'conclusa' : 'concluse'}
                    </div>
                    <div className="text-[10px] text-white/40">la fase la dà il flag «inplay» di Betfair; conclusa = Match Odds chiuso da Betfair</div>
                </div>
            </div>

            {vm.ordiniConto?.stato !== 'letti' && (
                <div className="text-[11px] text-white/45" data-testid="co-ordini-conto-non-letti">
                    ordini del conto fuori dai bot: non letti ({vm.ordiniConto?.motivo ?? 'motivo ignoto'}): le scatole mostrano solo le gambe dei bot
                </div>
            )}
            {vm.errore && (
                <Card className="glass-card border-orange-500/30 p-3 text-sm text-orange-300" data-testid="co-errore">
                    {vm.errore}. Le scatole mostrano l&apos;ultimo dato letto, non uno più recente.
                </Card>
            )}

            <ContestiRigheBanco vm={vm}>
                {vm.caricamento && scatole.length === 0 ? (
                    <div className="text-sm text-white/40" data-testid="co-caricamento">lettura delle posizioni aperte…</div>
                ) : scatole.length === 0 ? (
                    <EmptyState testId="co-vuoto">Nessuna operazione aperta. Quando un bot, l&apos;app o il sito vanno a mercato, la partita compare qui.</EmptyState>
                ) : (
                    <div className="space-y-5">
                        {fase !== 'pre' && (
                            <Sezione titolo="In gioco" testId="co-sezione-gioco" scatole={inGioco} vm={vm} safe={safe}
                                riporta={riporta}
                                vuoto="Nessuna partita in gioco con operazioni aperte." />
                        )}
                        {fase !== 'live' && (
                            <Sezione titolo="Pre-match" testId="co-sezione-pre" scatole={pre} vm={vm} safe={safe}
                                riporta={riporta}
                                vuoto="Nessuna operazione aperta su partite che devono ancora entrare in gioco." />
                        )}
                        {/* 08/10 sera (D-6): in fondo, perche' non c'e' piu' niente da
                            chiudere (il cash out e' spento), solo da attendere il
                            regolamento; compare solo se ce n'e' almeno una e segue il
                            filtro Live (sono partite gia' entrate in gioco) */}
                        {fase !== 'pre' && concluse.length > 0 && (
                            <Sezione titolo="Concluse · posizioni da regolare" testId="co-sezione-concluse" scatole={concluse}
                                vm={vm} safe={safe} riporta={riporta}
                                vuoto="Nessuna partita conclusa con posizioni da regolare." />
                        )}
                    </div>
                )}
            </ContestiRigheBanco>
        </PageShell>
    );
}
