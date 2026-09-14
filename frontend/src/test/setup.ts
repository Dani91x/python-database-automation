// Setup globale dei test COMPONENTE (jsdom). Registra i matcher di jest-dom
// (toBeInTheDocument, toBeDisabled, ...) sull'`expect` di vitest e smonta l'albero
// React dopo ogni test (globals:false → cleanup non è automatico).
import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
    cleanup();
});

// ============================================================================
// IL COLLAUDO NON DEVE APRIRE SOCKET VERI (14/09/2026)
// ============================================================================
// Dal 14/09 le pagine dei bot si collegano al canale locale su 127.0.0.1
// (ws://…:47333 Mike, 47334 Omega, 47335 Safe). In un test quella connessione è
// un disastro silenzioso: se l'app desktop sta girando sulla stessa macchina il
// socket si APRE DAVVERO, jsdom e undici si scambiano oggetti `Event` di due
// realm diversi e il test cade con un `TypeError` che non c'entra niente con ciò
// che stava misurando — «The "event" argument must be an instance of Event.
// Received an instance of Event». Se invece l'app è spenta, il test aspetta un
// timeout di rete. In tutti e due i casi il verdetto dipende da cosa gira sul
// PC, non dal codice.
//
// È lo stesso difetto che il 14/09 abbiamo trovato in `Betfair/stream/tests`,
// dove alcuni test interrogavano DAVVERO Supabase e diventavano rossi quando il
// database era giù. La regola vale su entrambi i lati:
//
//     una misura che dipende da cosa gira sulla macchina non è una misura.
//
// Qui si sostituisce `WebSocket` con un guscio che non si connette a niente e
// non emette nulla: le pagine si comportano come con il canale SPENTO, cioè
// leggendo dal database — che è esattamente lo scenario da certificare per
// difetto (il canale è un'accelerazione, mai l'unica fonte). Chi vuole provare
// il canale ACCESO lo fa apposta, con il suo finto, come in
// `src/lib/localChannel.test.ts`.
class WebSocketSpento {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSING = 2;
    static readonly CLOSED = 3;
    readonly url: string;
    readonly readyState = WebSocketSpento.CLOSED;
    onopen: unknown = null;
    onclose: unknown = null;
    onerror: unknown = null;
    onmessage: unknown = null;
    constructor(url: string | URL) { this.url = String(url); }
    send(): void { /* nessuno ascolta */ }
    close(): void { /* già chiuso */ }
    addEventListener(): void { /* nessun evento arriva mai */ }
    removeEventListener(): void { /* idem */ }
    dispatchEvent(): boolean { return false; }
}
(globalThis as unknown as { WebSocket: unknown }).WebSocket = WebSocketSpento;
