// ============================================================================
// AppShell — la cornice del redesign «guscio v2» (layout route di App.tsx).
//
// Griglia `sidebar | (testata 56 px + contenuto)`. Il contenuto scorre in un
// contenitore proprio (.ds-contenuto): gli `sticky top-0` delle pagine restano
// attaccati al suo bordo alto e non finiscono sotto la testata.
// Le pagine sono rese IDENTICHE dentro <Outlet/>: il guscio non tocca testi,
// testid, comandi, dati. Tutto cio' che aggiunge sta dentro `data-shell-chrome`
// (la fotografia lo registra a parte, src/fotografia).
// `data-shell="v2"` sulla radice nasconde via CSS i soli elementi di pura
// navigazione duplicata delle testate di oggi (`data-nav-legacy`), mai comandi.
// ============================================================================
import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TestataGlobale } from './TestataGlobale';

export function AppShell() {
    const [compressa, setCompressa] = useState(false);
    return (
        <div className="ds-shell" data-shell="v2" data-compressa={compressa ? 'true' : 'false'}>
            <div data-shell-chrome className="contents">
                <Sidebar compressa={compressa} onComprimi={() => setCompressa((c) => !c)} />
            </div>
            <div className="ds-main">
                <div data-shell-chrome className="contents">
                    <TestataGlobale />
                </div>
                {/* nessun attributo di test qui: tutto cio' che non e' cornice e' PAGINA */}
                <div className="ds-contenuto">
                    <Outlet />
                </div>
            </div>
        </div>
    );
}

export default AppShell;
