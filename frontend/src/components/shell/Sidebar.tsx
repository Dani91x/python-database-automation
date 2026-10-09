// ============================================================================
// Sidebar del guscio v2: gruppi e voci del prototipo, comprimibile, filtro
// Tutti / Calcio / Tennis che nasconde SOLO voci di menu.
//
// Nessuna lettura: le etichette di stato dei bot (LIVE/PROVA/FERMO) del
// prototipo NON ci sono, perche' il dato oggi lo legge solo la Control Room
// (useControlRoom) e le pagine dei bot: portarlo qui vorrebbe dire letture
// nuove. «Esci» fa esattamente cio' che fa oggi in Scelta sport, Cruscotto e
// TennisNav: supabase.auth.signOut() e poi la landing.
// ============================================================================
import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
    Activity, AlignJustify, ArrowLeftRight, BookOpen, Bot, CircleDot, ExternalLink, Eye, FileText,
    Gauge, History, Home, LayoutGrid, LineChart, LogOut, Omega, PanelLeft, Radar, RotateCcw, Shield,
    Star, Target, Wallet,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';
import { gruppiVisibili, type FiltroSport, type IconaVoce, type VoceNav } from './navigazione';
import { monitorSaluteAcceso } from '@/lib/monitorSalute';

const ICONE: Record<IconaVoce, LucideIcon> = {
    home: Home, radar: Radar, cruscotto: Gauge, omega: Omega, scudo: Shield, bersaglio: Target,
    impulso: Activity, storico: History, tennis: CircleDot, ladder: AlignJustify, bot: Bot,
    griglia: LayoutGrid, popout: ExternalLink, occhio: Eye, portafoglio: Wallet, stella: Star,
    replay: RotateCcw, grafico: LineChart, report: FileText, libro: BookOpen, scambio: ArrowLeftRight,
    esci: LogOut,
};

const FILTRI: { v: FiltroSport; etichetta: string }[] = [
    { v: 'tutti', etichetta: 'Tutti' },
    { v: 'calcio', etichetta: '⚽ Calcio' },
    { v: 'tennis', etichetta: '🎾 Tennis' },
];

interface SidebarProps {
    compressa: boolean;
    onComprimi: () => void;
}

function Voce({ v, compressa }: { v: VoceNav; compressa: boolean }) {
    const navigate = useNavigate();
    const Icona = ICONE[v.icona];
    const testo = compressa ? null : <span className="truncate">{v.etichetta}</span>;
    const titolo = v.nota ?? v.etichetta;
    if (v.rotta === null) {
        // «Esci»: lo stesso comando di oggi
        return (
            <button
                type="button"
                className="ds-sb-voce w-full text-left hover:text-red-300"
                data-testid={`shell-voce-${v.id}`}
                title={titolo}
                aria-label={compressa ? v.etichetta : undefined}
                onClick={async () => {
                    await supabase.auth.signOut();
                    navigate('/');
                }}
            >
                <Icona aria-hidden="true" />
                {testo}
            </button>
        );
    }
    if (v.finestra) {
        // come il bottone «stacca» di LadderView: finestra a parte 560×860
        return (
            <a
                href={v.rotta}
                className="ds-sb-voce"
                data-testid={`shell-voce-${v.id}`}
                title={titolo}
                aria-label={compressa ? v.etichetta : undefined}
                onClick={(e) => {
                    e.preventDefault();
                    window.open(v.rotta as string, 'ladder_popout', 'popup=yes,width=560,height=860,resizable=yes,scrollbars=yes');
                }}
            >
                <Icona aria-hidden="true" />
                {testo}
            </a>
        );
    }
    return (
        <NavLink
            to={v.rotta}
            end
            className="ds-sb-voce"
            data-testid={`shell-voce-${v.id}`}
            title={titolo}
            aria-label={compressa ? v.etichetta : undefined}
        >
            <Icona aria-hidden="true" />
            {testo}
        </NavLink>
    );
}

export function Sidebar({ compressa, onComprimi }: SidebarProps) {
    const [filtro, setFiltro] = useState<FiltroSport>('tutti');
    // 09/10 (R-5): «Salute» solo con il monitor acceso (MONITOR_SALUTE=1 alla build)
    const monitorAttivo = monitorSaluteAcceso();
    return (
        <aside className="ds-sidebar" aria-label="Navigazione principale" data-testid="shell-sidebar">
            <div className="ds-sb-brand">
                <div className="ds-sb-logo" aria-hidden="true">AI</div>
                {!compressa && (
                    <div className="font-display text-[15px] font-extrabold tracking-tight whitespace-nowrap">
                        AI <span className="text-primary">TERMINAL</span>
                    </div>
                )}
            </div>
            {!compressa && (
                <div className="ds-sb-sport" role="group" aria-label="Sport nella barra" data-testid="shell-filtro-sport">
                    {FILTRI.map((f) => (
                        <button
                            key={f.v}
                            type="button"
                            aria-pressed={filtro === f.v}
                            data-testid={`shell-filtro-${f.v}`}
                            onClick={() => setFiltro(f.v)}
                        >
                            {f.etichetta}
                        </button>
                    ))}
                </div>
            )}
            <nav className="flex-1 px-2 pb-4 pt-1.5" aria-label="Sezioni">
                {gruppiVisibili(filtro, monitorAttivo).map((g) => (
                    <div key={g.id} data-testid={`shell-gruppo-${g.id}`}>
                        {g.titolo && (
                            <div className={`ds-sb-gruppo ${compressa ? 'justify-center' : ''}`}>
                                {g.sport === 'calcio' && <span className="ds-led bg-primary" aria-hidden="true" />}
                                {g.sport === 'tennis' && <span className="ds-led bg-secondary" aria-hidden="true" />}
                                {!compressa && <span>{g.titolo}</span>}
                            </div>
                        )}
                        <div className={g.titolo ? '' : 'mt-1'}>
                            {g.voci.map((v) => (
                                <Voce key={v.id} v={v} compressa={compressa} />
                            ))}
                        </div>
                    </div>
                ))}
            </nav>
            <div className="ds-sb-piede">
                <button
                    type="button"
                    className="grid h-8 w-8 flex-none place-items-center rounded-lg border border-border bg-card text-muted-foreground hover:text-foreground"
                    onClick={onComprimi}
                    aria-pressed={compressa}
                    aria-label={compressa ? 'Espandi la barra' : 'Comprimi la barra'}
                    title={compressa ? 'Espandi la barra' : 'Comprimi la barra'}
                    data-testid="shell-comprimi"
                >
                    <PanelLeft className="h-4 w-4" aria-hidden="true" />
                </button>
            </div>
        </aside>
    );
}
