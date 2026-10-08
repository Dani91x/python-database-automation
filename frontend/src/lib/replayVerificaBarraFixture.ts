// ============================================================================
// replayVerificaBarraFixture - verifica della barra su una FIXTURE generata dal raw
// (08/10, cantiere 13). La fixture la scrive `tools/replay_barra_fixture.py` (curator
// vero, punteggi, timeline, campionamento del server); con `--registrazioni` e
// `--uscita` la si genera per una partita del database dal suo raw sul PC, fuori dal
// repository. Questa funzione PURA la converte come i test (`replayDaFixture`) e la
// passa al verificatore: e' la "cura" provata senza toccare il database (dati
// rigenerati dal raw con la regola unica del curatore) e il confronto con l'esito dei
// dati caricati (`scripts/verifica_barra_replay.ts`) dice se un'incoerenza e' dei dati
// caricati (sparisce dal raw) o resta (verificatore, pagina, o dato gia' nel raw).
// La usa `scripts/verifica_barra_fixture.ts`.
// ============================================================================
import type { EsitoVerificaBarra, EstremiRegistrazione } from '@/lib/replayVerificaBarra';
import { verificaBarraReplayCalcio } from '@/lib/replayVerificaBarraCalcio';
import { dettaglioIncoerenze } from '@/lib/replayVerificaBarraDettaglio';
import { formattaReferto } from '@/lib/replayVerificaBarraTesto';
import { replayDaFixture, type FixtureBarra } from '@/lib/__fixtures__/replayBarraConversione';

export interface FixtureDaVerificare extends FixtureBarra {
    meta?: EstremiRegistrazione | null;
}

export interface EsitoFixture {
    titolo: string;
    esito: EsitoVerificaBarra;
    /** referto in testo (riga di esito, rilievi, e le prove se richieste) */
    testo: string;
}

export function verificaFixture(fx: FixtureDaVerificare, opz: { dettaglio?: boolean; conNote?: boolean } = {}): EsitoFixture {
    const replay = replayDaFixture(fx);
    const estremi: EstremiRegistrazione | null = fx.meta
        ? { ts_min: fx.meta.ts_min ?? null, ts_max: fx.meta.ts_max ?? null, inplay_from_ts: fx.meta.inplay_from_ts ?? null }
        : null;
    const esito = verificaBarraReplayCalcio(replay, { estremi });
    const ev = fx.event;
    const titolo = `${ev.event_id} ${ev.home_name} - ${ev.away_name} (${String(ev.open_date ?? '').slice(0, 10) || 'data ignota'}, fixture dal raw)`;
    const righe = [formattaReferto(titolo, esito, opz.conNote ?? true)];
    if (opz.dettaglio && !esito.ok) righe.push(...dettaglioIncoerenze(replay, esito));
    return { titolo, esito, testo: righe.join('\n') };
}
