// ============================================================================
// mediaUnderAttiva.ts — il pulsante «ATTIVA ADESSO» della Media Under (07/10/2026).
// Spec: Betfair/stream/scalper/SPEC_MEDIA_UNDER_2026-10-05.md par.13.
//
// Sessione ACCESA: il clic arriva alla sessione con la RPC owner-only
// scalper_media_attiva_adesso (migrations/media_under_attiva_adesso_2026-10-07.sql),
// che scrive {id, ts} in scalper_control.params.media_attiva_adesso: la stessa
// riga da cui la sessione rilegge i parametri a ogni battito. Sessione FERMA: il
// clic la accende con scalper_activate (lib/scalper.ts) e i params del pulsante
// (mediaUnder.paramsAttivaAdesso). Prova e soldi veri: stessa strada.
// ============================================================================
import { supabase } from '@/integrations/supabase/client';

import type { ComandoAttivaAdesso } from './mediaUnder';

export async function mandaAttivaAdesso(eventId: string, comando: ComandoAttivaAdesso): Promise<void> {
    const { error } = await supabase.rpc('scalper_media_attiva_adesso', {
        p_event_id: eventId,
        p_id: comando.id,
    });
    if (error) throw new Error(error.message);
}
