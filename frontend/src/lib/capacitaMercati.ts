// ============================================================================
// capacitaMercati.ts - 28/09 (cantiere B): la CAPACITA' dei mercati del runner
// calcio e le partite idonee rimaste FUORI, dal canale 47331.
//
// Ordine dell'utente (28/09): «non possiamo lasciare eventi "fuori", noi
// lavoriamo sul volume». Il runner segue le partite su piu' connessioni di
// mercato (frammenti); se la capacita' vera e' comunque esaurita, chi resta
// fuori e perche' deve essere VISIBILE, mai silenzioso.
//
// Il messaggio VERO (busta `{"t": topic, "d": ...}` di local_channel.py):
//   auto_follow <- `runner._costruisci_auto_follow._pubblica` =
//                  `auto_follow.AutoFollow.stato()`, a ogni cambio
//   hello.auto_follow <- lo stesso oggetto, per chi si collega dopo
// Chiavi e tipi: lib/__fixtures__/autoFollowFinti.json, generata dallo stato
// vero e verificata da
// Betfair/stream/tests/test_frammenti_mercato_2026_09_28.py::test_fixture_ui_ha_le_chiavi_vere
//
// Modulo PURO: nessun import di rete, nessun React.
// ============================================================================

export interface PartitaFuori {
    eventId: string;
    /** "Casa v Ospite"; null = nome non noto */
    nome: string | null;
    motivo: string;
    /** ms epoch da quando e' fuori; null = non noto */
    dalMs: number | null;
}

export interface CapacitaMercati {
    mercatiSeguiti: number;
    /** tetto del piano = capacita' vera (connessioni concesse x mercati per connessione) */
    tetto: number;
    connessioni: number;
    connessioniMassime: number | null;
    /** partite seguite dall'auto-follow */
    partiteSeguite: number;
    /** partite del feed (ultima lettura); null = feed non letto */
    partiteFeed: number | null;
    fuoriN: number;
    fuori: PartitaFuori[];
    motivoLimite: string | null;
    criterio: string | null;
    ultimoRifiuto: string | null;
    /** connectionsAvailable dichiarato da Betfair all'ultima autenticazione */
    disponibiliBetfair: number | null;
}

function num(v: unknown): number | null {
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function testo(v: unknown): string | null {
    return typeof v === 'string' && v.trim() ? v : null;
}

/**
 * Legge lo stato dell'auto-follow (topic `auto_follow` o `hello.auto_follow`).
 * `null` = messaggio storto o runner di prima del 28/09 senza le chiavi della
 * capacita' (`partite_fuori_n`).
 */
export function leggiCapacitaMercati(d: unknown): CapacitaMercati | null {
    if (!d || typeof d !== 'object' || Array.isArray(d)) return null;
    const o = d as Record<string, unknown>;
    const fuoriN = num(o.partite_fuori_n);
    const tetto = num(o.tetto_mercati);
    const seguiti = num(o.mercati_seguiti);
    if (fuoriN == null || tetto == null || seguiti == null) return null;
    const fr = o.frammenti && typeof o.frammenti === 'object' && !Array.isArray(o.frammenti)
        ? o.frammenti as Record<string, unknown> : {};
    const feed = o.feed && typeof o.feed === 'object' && !Array.isArray(o.feed)
        ? o.feed as Record<string, unknown> : {};
    const fuori: PartitaFuori[] = [];
    for (const x of Array.isArray(o.partite_fuori) ? o.partite_fuori : []) {
        if (!x || typeof x !== 'object') continue;
        const r = x as Record<string, unknown>;
        const id = testo(r.event_id);
        if (id == null) continue;
        const dal = num(r.dal);
        fuori.push({
            eventId: id,
            nome: testo(r.nome),
            motivo: testo(r.motivo) ?? 'motivo non dichiarato',
            dalMs: dal == null ? null : Math.round(dal * 1000),
        });
    }
    return {
        mercatiSeguiti: seguiti,
        tetto,
        connessioni: num(o.connessioni_di_mercato) ?? 1,
        connessioniMassime: num(fr.connessioni_massime),
        partiteSeguite: num(o.eventi_auto) ?? 0,
        partiteFeed: feed.letto === true ? num(feed.partite) : null,
        fuoriN,
        fuori,
        motivoLimite: testo(fr.motivo_limite),
        criterio: testo(o.criterio_fuori),
        ultimoRifiuto: testo(fr.ultimo_rifiuto),
        disponibiliBetfair: num(fr.connessioni_disponibili_betfair),
    };
}
