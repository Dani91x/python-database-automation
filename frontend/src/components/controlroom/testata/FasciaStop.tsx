// ============================================================================
// StopPerdita.tsx - P4 (30/09): gli stop di perdita nella testata, dentro il
// contenitore storico `cr-freni`.
//
//   Stop conto: SPENTO  [si modifica: Segui Live]
//   Safe PAPER -50,00  Mike LIVE -50,00  Omega PAPER -300,00   [modifica]
//
// Ogni stop col NOME del proprietario, la sua MODALITA' e il posto dove si
// modifica. Nessun nuovo punto di salvataggio: il conto rimanda a
// `LiveControlsPanel` (pagina Segui Live, "Controlli runner - limiti - audit"),
// ogni bot porta alla SUA riga di "Comando dei bot", dove c'e' il foglio
// parametri gia' montato col suo cancello "parametri non letti". Il pulsante
// scorre fino alla riga e mette il fuoco sul foglio: non lo apre e non salva
// niente da solo.
// Assente si scrive "assente", mai 0,00; scattato si scrive "SCATTATO".
// ============================================================================
import { Link } from 'react-router-dom';
import { Pencil } from 'lucide-react';
import { fmtMoney, fmtAge } from '@/lib/format';
import { BOT_LABEL } from '@/lib/controlRoom';
import type { StopPerditaTestata, StopBot } from './stopPerdita';

/** Porta il trader alla riga del bot in "Comando dei bot" (il foglio
 *  parametri esistente), o al pannello se la riga non e' visibile. */
export function vaiAllaRigaDelBot(bot: string, doc: Document = document): boolean {
    const riga = doc.querySelector<HTMLElement>(`[data-testid="cr-parametri-${bot}"]`);
    const bersaglio = riga ?? doc.querySelector<HTMLElement>('[data-testid="cr-pannello-bot"]');
    if (!bersaglio) return false;
    if (typeof bersaglio.scrollIntoView === 'function') bersaglio.scrollIntoView({ block: 'center', behavior: 'smooth' });
    const pulsante = riga?.querySelector<HTMLElement>('button');
    if (pulsante) pulsante.focus();
    return riga != null;
}

function Modo({ m }: { m: StopBot['modalita'] }) {
    if (m === 'live') return <span className="text-[9px] font-bold px-1 rounded bg-red-500/20 text-red-300">LIVE</span>;
    if (m === 'paper') return <span className="text-[9px] px-1 rounded border border-white/15 text-slate-300">PAPER</span>;
    return <span className="text-[9px] px-1 rounded text-orange-300">modo ?</span>;
}

function ValoreBot({ s }: { s: StopBot }) {
    if (s.scattato) return <span className="text-red-400 font-semibold">SCATTATO</span>;
    // Safe: lo stop lo DICHIARA il servizio, se manca e' assente; Mike e
    // Omega: e' un parametro, se la riga non e' letta non si sa
    if (!s.letto || s.soglia == null) {
        return <span className="text-orange-400">{s.bot === 'safe' ? 'assente' : 'non letto'}</span>;
    }
    if (s.soglia === 0) return <span className="text-white/50">spento</span>;
    return <span className="text-white/90">{fmtMoney(-s.soglia)}</span>;
}

export function StopPerdita({ stop, vai = vaiAllaRigaDelBot }: {
    stop: StopPerditaTestata | undefined;
    /** iniettabile per i test */
    vai?: (bot: string) => boolean;
}) {
    const c = stop?.conto ?? null;
    let contoTesto: string;
    let contoCls = 'text-white/90';
    if (c == null || !c.letto) { contoTesto = 'non letto'; contoCls = 'text-orange-400'; }
    else if (c.scattato) { contoTesto = 'SCATTATO: freno generale tirato'; contoCls = 'text-red-400'; }
    else if (c.soglia == null) { contoTesto = 'SPENTO'; contoCls = 'text-white/60'; }
    else contoTesto = fmtMoney(-c.soglia);

    return (
        <div className="flex flex-col gap-0.5" data-testid="cr-stop-perdita">
            <span className="text-[10px] uppercase tracking-wider text-white/40">Stop perdita</span>
            <span className="flex items-center gap-1.5 text-[11px] font-mono tabular-nums" data-testid="cr-stop-conto"
                title={c?.letto
                    ? `stop del CONTO (betfair_live_settings.daily_loss_limit, applicato dal runner): raggiunto, tira il freno generale.${c.motivo ? ` Stato del runner: ${c.motivo}.` : ''} Riga aggiornata al cambio, ultimo cambio ${fmtAge(c.etaS)} fa.`
                    : 'stato dello stop del conto (betfair_live_risk_state) non ancora letto'}>
                <span className="text-white/45 font-sans">Conto:</span>
                <span className={`font-semibold ${contoCls}`} data-testid="cr-stop-conto-valore">{contoTesto}</span>
                {c?.letto && c.soglia != null && c.oggi != null && (
                    <span className={c.oggi < 0 ? 'text-red-300' : 'text-white/50'} data-testid="cr-stop-conto-oggi"
                        title="P&L di giornata secondo il runner (regolato dal conto + aperto stimato)">
                        oggi {fmtMoney(c.oggi, { signed: true })}{c.degradato ? ' (stima degradata)' : ''}
                    </span>
                )}
                <Link to="/segui-live" data-testid="cr-stop-conto-modifica"
                    className="text-white/40 hover:text-white/80"
                    title="si modifica in Segui Live, pannello 'Controlli runner - limiti - audit', campo 'Stop giornaliero' (lo stesso controllo di sempre)">
                    <Pencil className="w-3 h-3" aria-label="modifica lo stop del conto" />
                </Link>
            </span>
            <span className="flex items-center gap-x-2 gap-y-0.5 flex-wrap text-[11px] font-mono tabular-nums">
                {(stop?.bot ?? []).map((s) => (
                    <span key={s.bot} className="flex items-center gap-1" data-testid={`cr-stop-${s.bot}`}
                        title={`stop di ${BOT_LABEL[s.bot]}: ${s.fonte}. Si modifica in ${s.dove}. Vale solo per le aperture di ${BOT_LABEL[s.bot]}.`}>
                        <span className="text-white/55 font-sans">{BOT_LABEL[s.bot]}</span>
                        <Modo m={s.modalita} />
                        <ValoreBot s={s} />
                        <button type="button" onClick={() => vai(s.bot)} data-testid={`cr-stop-${s.bot}-modifica`}
                            className="text-white/40 hover:text-white/80"
                            aria-label={`modifica lo stop di ${BOT_LABEL[s.bot]}`}>
                            <Pencil className="w-3 h-3" />
                        </button>
                    </span>
                ))}
            </span>
        </div>
    );
}

export default StopPerdita;
