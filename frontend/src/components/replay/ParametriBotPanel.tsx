// ============================================================================
// ParametriBotPanel — i PARAMETRI del bot applicato al replay (07/10).
// Ordine dell'utente: «devo poter modificare i parametri di ognuno cosi' da
// provare altre varianti SENZA CAMBIARE LA STRATEGIA».
// Le voci arrivano dal catalogo GENERATO dal backend (replayBotCatalogo.ts):
// chiave, etichetta, tipo, valore di SERIE, limiti, passo, unita', gruppo.
// Per ogni parametro: il campo, il valore di serie sempre accanto, il segno
// «cambiato» se diverso dalla serie, l'errore se fuori dominio. I bool sono
// interruttori, le scelte una fila di pulsanti. Riusabile (Match Replay e
// Replay Tennis): nessuno stato interno oltre all'apertura del pannello.
// ============================================================================
import { useState, type ReactElement } from 'react';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { gruppiParametri, sostituzioni, testoValore, validaCampo } from '@/lib/applicaBot';
import type { VoceParametro } from '@/lib/replayBot';

export const FRASE_VARIANTI = 'Varianti dei parametri: la strategia non cambia';

export interface ParametriBotPanelProps {
    /** il catalogo dello scenario scelto */
    voci: ReadonlyArray<VoceParametro>;
    /** i SOLI valori toccati dall'utente (chiave -> valore o testo del campo) */
    valori: Readonly<Record<string, unknown>>;
    /** un campo cambiato; `undefined` = torna al valore di serie */
    onCambia: (chiave: string, valore: unknown) => void;
    /** tutti i campi tornano ai valori di serie */
    onRipristina: () => void;
    disabilitato?: boolean;
    /** pannello aperto all'inizio (di serie chiuso: e' una tendina) */
    apertoDiSerie?: boolean;
}

function CampoParametro({ v, valore, toccato, onCambia, disabilitato }: {
    v: VoceParametro; valore: unknown; toccato: boolean;
    onCambia: (valore: unknown) => void; disabilitato: boolean;
}) {
    const attuale = toccato ? valore : v.default;
    const esito = toccato ? validaCampo(v, valore) : { ok: true, valore: v.default };
    const cambiato = toccato && esito.ok && esito.valore !== v.default;
    const id = `param-bot-${v.chiave}`;
    let campo: ReactElement;
    if (v.tipo === 'bool') {
        const acceso = attuale === true;
        campo = (
            <Button
                id={id}
                type="button"
                role="switch"
                aria-checked={acceso}
                size="sm"
                variant={acceso ? 'default' : 'outline'}
                disabled={disabilitato}
                onClick={() => onCambia(!acceso)}
                className="h-7 min-w-[5.5rem] text-[11px]"
                data-testid={`param-bot-switch-${v.chiave}`}
            >
                {acceso ? 'acceso' : 'spento'}
            </Button>
        );
    } else if (v.tipo === 'scelta') {
        campo = (
            <div id={id} role="radiogroup" aria-label={v.etichetta} className="flex flex-wrap gap-1">
                {(v.scelte ?? []).map(s => (
                    <Button
                        key={s}
                        type="button"
                        role="radio"
                        aria-checked={attuale === s}
                        size="sm"
                        variant={attuale === s ? 'default' : 'outline'}
                        disabled={disabilitato}
                        onClick={() => onCambia(s)}
                        className="h-7 text-[11px]"
                    >
                        {s}
                    </Button>
                ))}
            </div>
        );
    } else {
        campo = (
            <Input
                id={id}
                type="number"
                inputMode="decimal"
                min={v.min ?? undefined}
                max={v.max ?? undefined}
                step={v.passo ?? undefined}
                value={String(attuale ?? '')}
                disabled={disabilitato}
                aria-invalid={!esito.ok}
                onChange={e => onCambia(e.target.value)}
                className="h-7 w-28 text-[11px]"
                data-testid={`param-bot-campo-${v.chiave}`}
            />
        );
    }
    return (
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5 py-1"
            data-testid={`param-bot-${v.chiave}`} data-cambiato={cambiato ? 'si' : 'no'}>
            <Label htmlFor={id} className="text-[11px] font-normal">
                {v.etichetta}{v.unita && v.tipo !== 'bool' && v.tipo !== 'scelta' ? ` (${v.unita})` : ''}
                {cambiato && <Badge variant="default" className="ml-2 px-1.5 py-0 text-[10px]">cambiato</Badge>}
            </Label>
            <div className="flex items-center gap-2 justify-self-end">
                {campo}
                {toccato && (
                    <Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-[10px]"
                        disabled={disabilitato} onClick={() => onCambia(undefined)}
                        title="torna al valore di serie">
                        di serie
                    </Button>
                )}
            </div>
            <span className="text-[10px] text-muted-foreground">
                di serie: <span className="tabular-nums">{testoValore(v, v.default)}</span>
                {v.tipo !== 'bool' && v.tipo !== 'scelta' && v.min != null && v.max != null
                    ? ` · ${v.min}–${v.max}` : ''}
            </span>
            {!esito.ok && (
                <span role="alert" className="text-[10px] text-destructive justify-self-end">{esito.errore}</span>
            )}
        </div>
    );
}

export function ParametriBotPanel({
    voci, valori, onCambia, onRipristina, disabilitato = false, apertoDiSerie = false,
}: ParametriBotPanelProps) {
    const [aperto, setAperto] = useState(apertoDiSerie);
    const { cambiati, errori } = sostituzioni(voci, valori);
    const nCambiati = Object.keys(cambiati).length;
    const nErrori = Object.keys(errori).length;
    const gruppi = gruppiParametri(voci);
    return (
        <div className="rounded-xl border bg-card/40 px-3 py-2 text-[11px]" data-testid="parametri-bot">
            <div className="flex items-center gap-2 flex-wrap">
                <Button type="button" size="sm" variant="outline" className="h-7 text-[11px] font-bold"
                    aria-expanded={aperto} onClick={() => setAperto(a => !a)}
                    data-testid="parametri-bot-apri">
                    Parametri {aperto ? '▴' : '▾'}
                </Button>
                <span className="font-semibold" data-testid="parametri-bot-frase">{FRASE_VARIANTI}</span>
                <span className="text-muted-foreground">
                    {voci.length === 0 ? 'nessun parametro variabile per questo scenario'
                        : nCambiati === 0 ? 'tutti di serie' : `${nCambiati} cambiati`}
                    {nErrori > 0 ? ` · ${nErrori} da correggere` : ''}
                </span>
                {Object.keys(valori).length > 0 && (
                    <Button type="button" size="sm" variant="ghost" className="h-7 text-[11px]"
                        disabled={disabilitato} onClick={onRipristina} data-testid="parametri-bot-ripristina">
                        Ripristina di serie
                    </Button>
                )}
            </div>
            {aperto && voci.length > 0 && (
                <Accordion type="multiple" defaultValue={gruppi.map(g => g.gruppo)} className="mt-1">
                    {gruppi.map(g => (
                        <AccordionItem key={g.gruppo} value={g.gruppo}>
                            <AccordionTrigger className="py-1.5 text-[11px] font-bold">
                                {g.gruppo}
                                <span className="ml-auto mr-2 font-normal text-muted-foreground">
                                    {g.voci.filter(v => v.chiave in cambiati).length > 0
                                        ? `${g.voci.filter(v => v.chiave in cambiati).length} cambiati` : ''}
                                </span>
                            </AccordionTrigger>
                            <AccordionContent className="pb-2">
                                {g.voci.map(v => (
                                    <CampoParametro key={v.chiave} v={v}
                                        valore={valori[v.chiave]} toccato={v.chiave in valori}
                                        onCambia={x => onCambia(v.chiave, x)} disabilitato={disabilitato} />
                                ))}
                            </AccordionContent>
                        </AccordionItem>
                    ))}
                </Accordion>
            )}
        </div>
    );
}
