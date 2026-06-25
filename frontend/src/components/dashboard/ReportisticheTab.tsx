// ============================================================================
// ReportisticheTab — sezione "Reportistiche" di /analytics.
// Contenitore SELEZIONABILE di report storici. Si parte con "Direzioni"; nuovi
// report si aggiungono al catalogo REPORTS (lib/reportistiche) e a SWITCH qui,
// senza toccare il resto. Stesso design system della pagina.
// ============================================================================
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { REPORTS, type ReportId } from '@/lib/reportistiche';
import DirezioniReport from './DirezioniReport';

export default function ReportisticheTab() {
    const [active, setActive] = useState<ReportId>('direzioni');
    const current = REPORTS.find(r => r.id === active);

    return (
        <div className="space-y-5">
            {/* selettore report */}
            <div className="flex flex-wrap gap-2">
                {REPORTS.map(r => (
                    <Button key={r.id} variant={active === r.id ? 'default' : 'outline'} size="sm"
                        onClick={() => setActive(r.id)}
                        className={active === r.id ? 'bg-primary text-black' : 'border-white/10 text-muted-foreground hover:text-white'}
                        title={r.desc}>
                        {r.label}
                    </Button>
                ))}
            </div>
            {current && (
                <p className="text-xs text-muted-foreground -mt-2">{current.desc}</p>
            )}

            {active === 'direzioni' && <DirezioniReport />}
        </div>
    );
}
