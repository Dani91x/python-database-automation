// ============================================================================
// RigaCapacitaMercati.tsx - 28/09 (cantiere B): quante partite calcio segue il
// runner, su quante connessioni di mercato, e chi resta FUORI e perche'.
//
// Ordine dell'utente (28/09): «non possiamo lasciare eventi "fuori", noi
// lavoriamo sul volume». Il runner calcio segue le partite del feed su piu'
// connessioni (frammenti, `Betfair/stream/frammenti_mercato.py`); se Betfair
// non concede altre connessioni le partite rimaste fuori sono elencate qui con
// il motivo, mai in silenzio. Solo lettura: dal canale 47331 (topic
// `auto_follow` e `hello.auto_follow`), nessuna scrittura.
// ============================================================================
import { useEffect, useState } from 'react';
import { getLocalChannel } from '@/lib/localChannel';
import { leggiCapacitaMercati, type CapacitaMercati } from '@/lib/capacitaMercati';
import { AlertTriangle } from 'lucide-react';

/** quante partite fuori si elencano per nome */
const ELENCO_MAX = 10;

function minutiDa(ms: number | null, nowMs: number): string {
    if (ms == null) return '';
    const m = Math.max(0, Math.round((nowMs - ms) / 60_000));
    return m < 1 ? 'da meno di 1 min' : `da ${m} min`;
}

export function RigaCapacitaMercati() {
    const [cap, setCap] = useState<CapacitaMercati | null>(null);
    const [nowMs, setNowMs] = useState(() => Date.now());

    useEffect(() => {
        const ch = getLocalChannel('calcio');
        const daHello = (h: unknown) => leggiCapacitaMercati(
            h && typeof h === 'object' ? (h as Record<string, unknown>).auto_follow : null);
        const helloDi = () => (typeof ch.getHello === 'function' ? ch.getHello() : null);
        if (ch.getStatus() === 'connected') setCap(daHello(helloDi()));
        const offStato = ch.onStatus((st) => {
            // canale giu': lo stato del runner non e' piu' noto
            if (st !== 'connected') setCap(null);
            else setCap((p) => daHello(helloDi()) ?? p);
        });
        const offHello = ch.subscribe('hello', (d) => setCap((p) => daHello(d) ?? p));
        const offAuto = ch.subscribe('auto_follow', (d) => {
            const c = leggiCapacitaMercati(d);
            if (c) setCap(c);
        });
        const t = window.setInterval(() => setNowMs(Date.now()), 30_000);
        return () => { offStato(); offHello(); offAuto(); window.clearInterval(t); };
    }, []);

    const fuori = cap != null && cap.fuoriN > 0;
    return (
        <div className={`px-3 py-2 border-b border-white/10 ${fuori ? 'bg-red-500/10' : ''}`}
            data-testid="cr-capacita">
            <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[12px] font-bold uppercase tracking-wider w-24 shrink-0">Mercati</span>
                {cap == null ? (
                    <span className="text-[10px] text-white/40" data-testid="cr-capacita-ignota">
                        non noto (runner calcio spento o auto-follow non attivo)
                    </span>
                ) : (
                    <>
                        <span className="text-[10px] text-white/70" data-testid="cr-capacita-numeri"
                            title="mercati seguiti / capacita' (connessioni concesse x mercati per connessione)">
                            {cap.partiteSeguite} partite{cap.partiteFeed != null ? ` su ${cap.partiteFeed} del feed` : ''}
                            {' '}- {cap.mercatiSeguiti}/{cap.tetto} mercati - {cap.connessioni}
                            {cap.connessioniMassime != null ? `/${cap.connessioniMassime}` : ''} connessioni
                        </span>
                        <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                            fuori ? 'bg-red-500/30 text-red-200' : 'bg-emerald-500/15 text-emerald-300'
                        }`} data-testid="cr-capacita-fuori">
                            {fuori ? `${cap.fuoriN} partite FUORI` : 'nessuna partita fuori'}
                        </span>
                    </>
                )}
            </div>
            {cap != null && fuori && (
                <div className="mt-1.5 text-[10px] text-red-200 space-y-0.5" data-testid="cr-capacita-elenco">
                    <div className="flex items-center gap-1.5 text-amber-300">
                        <AlertTriangle className="w-3 h-3 shrink-0" />
                        <span data-testid="cr-capacita-motivo">
                            {cap.motivoLimite ?? 'capacita\' esaurita'}
                            {cap.ultimoRifiuto ? ` - ultimo rifiuto Betfair: ${cap.ultimoRifiuto}` : ''}
                        </span>
                    </div>
                    {cap.fuori.slice(0, ELENCO_MAX).map((p) => (
                        <div key={p.eventId} data-testid="cr-capacita-partita">
                            {p.nome ?? p.eventId} - {p.motivo} {minutiDa(p.dalMs, nowMs)}
                        </div>
                    ))}
                    {cap.fuoriN > ELENCO_MAX && (
                        <div className="text-white/40">... e altre {cap.fuoriN - ELENCO_MAX}</div>
                    )}
                    {cap.criterio && <div className="text-white/40" data-testid="cr-capacita-criterio">{cap.criterio}</div>}
                </div>
            )}
        </div>
    );
}

export default RigaCapacitaMercati;
