// ============================================================================
// TesseraRunner.tsx - 01/10: i due runner in testata, una TESSERA ciascuno.
//
// Ordine dell'utente (01/10): "i segnali di vita dei runner: devo sapere se il
// runner e' connesso e di che runner parliamo, calcio o tennis". Ieri:
// "Runner vivo, in attesa - ordini veri consentiti canale 5 s" e "Runner
// tennis vivo, in attesa - solo simulati": illeggibile.
//
// Ogni tessera dice, una riga per cosa:
//   * QUALE runner: "Runner CALCIO (canale 47331)" / "Runner TENNIS (canale 47332)";
//   * CONNESSO o no al canale locale (pallino): `fonte === 'canale'` vuol dire
//     che il canale del processo e' collegato e ha parlato
//     (`lib/runnerCanale.ts::runnerDalCanale`); il calcio senza canale ripiega
//     sul battito del database, il tennis non ha un battito sul database;
//   * il PROCESSO: in streaming / vivo, in attesa / fermo / mai avviato
//     (`runnerPhase`, fail-closed: il dubbio vale attesa, mai streaming);
//   * gli ORDINI che il runner PUO' servire (tetto del suo .env,
//     `tettoRunner`): ORDINI VERI consentiti col colore LIVE, solo simulati col
//     colore PAPER. Non e' il modo di un bot (lo dicono i chip dei bot);
//   * FONTE ed ETA' dell'ultima notizia.
// Solo presentazione: nessuna lettura nuova, i dati sono quelli che il hook
// gia' calcola (`vm.runner`, `vm.fonteRunner`, `vm.runnerTennis`,
// `vm.fonteRunnerTennis`).
// ============================================================================
import { fmtAge } from '@/lib/format';
import { runnerPhase, type RunnerPhase, type RunnerState } from '@/lib/safeBot';
import type { FonteRunner } from '@/lib/runnerCanale';
import { tettoRunner, type Tono } from './paroleImpianto';

export type SportRunner = 'calcio' | 'tennis';

export const PORTA_RUNNER: Record<SportRunner, number> = { calcio: 47331, tennis: 47332 };

export interface TesseraRunnerVista {
    titolo: string;
    porta: number;
    connesso: boolean;
    connessione: string;
    processo: { testo: string; tono: Tono };
    ordini: { testo: string; tono: Tono; titolo: string };
    fonte: string;
}

const PROCESSO: Record<RunnerPhase, { testo: string; tono: Tono }> = {
    streaming: { testo: 'in streaming', tono: 'ok' },
    idle: { testo: 'vivo, in attesa', tono: 'neutro' },
    off: { testo: 'fermo', tono: 'allarme' },
};

/**
 * R-03 (review 01/10): il runner PUO' servire ordini veri? Stessa regola
 * fail-closed della modalita': false SOLO se il tetto e' letto e dice "solo
 * simulati" o "ordini spenti"; runner non letto o tetto ignoto = forse.
 * Nessuna lettura nuova: `r` e' `vm.runner` / `vm.runnerTennis`.
 */
export function runnerForseLive(r: RunnerState | null | undefined): boolean {
    if (r == null) return true;
    const t = tettoRunner(r.mode);
    return !(t?.testo === 'solo simulati' || t?.testo === 'ordini spenti');
}

/** Funzione PURA: cosa scrive la tessera. */
export function descriviRunner(
    sport: SportRunner,
    r: RunnerState | null,
    fonte: { fonte: FonteRunner; etaS: number | null },
): TesseraRunnerVista {
    const porta = PORTA_RUNNER[sport];
    const titolo = `Runner ${sport === 'calcio' ? 'CALCIO' : 'TENNIS'}`;
    const connesso = r != null && fonte.fonte === 'canale';
    const eta = fonte.etaS == null ? null : fmtAge(fonte.etaS);

    if (r == null) {
        return {
            titolo, porta, connesso: false,
            connessione: 'non connesso',
            processo: sport === 'tennis'
                ? { testo: 'stato non noto (il runner tennis non scrive un battito sul database)', tono: 'attenzione' }
                : { testo: 'stato non letto', tono: 'attenzione' },
            ordini: { testo: 'ordini: non noto', tono: 'attenzione', titolo: 'il runner non ha dichiarato cosa puo\' servire' },
            fonte: sport === 'tennis' ? `canale ${porta} spento` : 'canale e database non letti',
        };
    }
    const processo = r.ageS == null
        ? { testo: 'mai avviato', tono: 'allarme' as Tono }
        : PROCESSO[runnerPhase(r)];
    const tetto = tettoRunner(r.mode);
    const ordini = tetto == null
        ? { testo: 'ordini: non dichiarato', tono: 'attenzione' as Tono, titolo: 'il runner non ha dichiarato LIVE_ORDER_MODE' }
        : tetto.testo === 'ordini veri consentiti'
            ? { testo: 'ORDINI VERI consentiti', tono: 'live' as Tono, titolo: tetto.titolo }
            : tetto.testo === 'solo simulati'
                ? { testo: 'solo simulati', tono: 'paper' as Tono, titolo: tetto.titolo }
                : { testo: tetto.testo, tono: 'neutro' as Tono, titolo: tetto.titolo };
    return {
        titolo, porta, connesso,
        connessione: connesso ? 'connesso' : 'non connesso al canale',
        processo,
        ordini,
        fonte: connesso
            ? `canale ${porta} \u00b7 ultimo messaggio ${eta ?? '?'} fa`
            : `database (battito ogni 30 s) \u00b7 battito ${eta ?? '?'} fa`,
    };
}

const TONO_CLS: Record<Tono, string> = {
    live: 'text-red-300 font-semibold',
    paper: 'text-slate-300',
    neutro: 'text-white/70',
    ok: 'text-emerald-400',
    attenzione: 'text-amber-300',
    allarme: 'text-orange-400 font-semibold',
};

export function TesseraRunner({ sport, r, fonte }: {
    sport: SportRunner;
    r: RunnerState | null;
    fonte: { fonte: FonteRunner; etaS: number | null };
}) {
    const t = sport === 'tennis' ? 'cr-runner-tennis' : 'cr-runner';
    const v = descriviRunner(sport, r, fonte);
    return (
        <div className="flex flex-col gap-0.5 rounded-md border border-white/10 bg-white/[0.03] px-2 py-1 min-w-[11rem]"
            data-testid={t}
            title={r?.ageS != null ? `ultimo battito del processo ${fmtAge(Math.round(r.ageS))} fa` : undefined}>
            <span className="text-[10.5px] tracking-wide text-white/80 font-semibold" data-testid={`${t}-nome`}>
                {v.titolo} <span className="font-normal text-white/40">(canale {v.porta})</span>
            </span>
            <span className="flex items-center gap-1.5 text-[11px]" data-testid={`${t}-connessione`}
                title="canale locale del processo: collegato = notizie in tempo reale dal runner">
                <span aria-hidden className={`inline-block w-2 h-2 rounded-full ${v.connesso ? 'bg-emerald-400' : 'bg-orange-400'}`}
                    data-testid={`${t}-pallino`} data-connesso={v.connesso ? '1' : '0'} />
                <span className={v.connesso ? 'text-emerald-300' : 'text-orange-300'}>{v.connessione}</span>
            </span>
            <span className="text-[11px]" data-testid={`${t}-processo`}>
                <span className="text-white/45">processo: </span>
                <span className={TONO_CLS[v.processo.tono]}>{v.processo.testo}</span>
            </span>
            <span className={`text-[11px] ${TONO_CLS[v.ordini.tono]}`} data-testid={`${t}-tetto`} title={v.ordini.titolo}>
                {v.ordini.testo}
            </span>
            <span className="text-[9.5px] text-white/35" data-testid={`${t}-fonte`}
                title="canale locale (processo collegato, eta' dell'ultimo messaggio) o database (battito al giro dei 30 s)">
                {v.fonte}
            </span>
        </div>
    );
}

export default TesseraRunner;
