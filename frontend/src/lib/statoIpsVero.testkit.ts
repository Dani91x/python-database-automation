// Stati IPS VERI per i test (chiavi e tipi identici alla registrazione).
//
// Fonte: `_live_raw/35797769/35797769.scores.jsonl` (Spagna-Belgio), campo
// `payload` delle righe 62 (19:49:22), 64 (19:50:45) e 68 (20:10:25). E' la
// forma del `score_raw` che lo scanner pubblica (`strip_volatile_state`: toglie
// solo `timeElapsedSeconds`). Gol e conteggi sono STRINGHE/numeri come nel vero.

function lato(nome: string, gol: string, ht: string, cornerSecondoTempo: boolean) {
    return {
        name: nome,
        score: gol,
        halfTimeScore: ht,
        fullTimeScore: '',
        penaltiesScore: '',
        penaltiesSequence: [] as string[],
        games: '',
        sets: '',
        numberOfYellowCards: nome === 'Spain' ? 1 : 0,
        numberOfRedCards: 0,
        numberOfCards: nome === 'Spain' ? 1 : 0,
        numberOfCorners: nome === 'Spain' ? 3 : 0,
        numberOfCornersFirstHalf: nome === 'Spain' ? 3 : 0,
        ...(cornerSecondoTempo ? { numberOfCornersSecondHalf: 0 } : {}),
        bookingPoints: nome === 'Spain' ? 10 : 0,
    };
}

function punteggio(ht: string, cornerSecondoTempo: boolean) {
    return {
        home: lato('Spain', '1', ht, cornerSecondoTempo),
        away: lato('Belgium', '1', ht, cornerSecondoTempo),
        numberOfYellowCards: 1,
        numberOfRedCards: 0,
        numberOfCards: 1,
        numberOfCorners: 3,
        numberOfCornersFirstHalf: 3,
        ...(cornerSecondoTempo ? { numberOfCornersSecondHalf: 0 } : {}),
        bookingPoints: 10,
    };
}

const ORA_ZERO = { hour: 0, min: 0, sec: 0 };

/** 19:49:22 - RECUPERO del 1T: KickOff, minuto cumulato 48 (reg 45, +3). */
export function statoIpsRecupero1T(): Record<string, unknown> {
    return {
        eventTypeId: 1, eventId: 35797769, score: punteggio('', false),
        timeElapsed: 48, elapsedRegularTime: 45, elapsedAddedTime: 3,
        fullTimeElapsed: ORA_ZERO, status: 'KickOff', matchStatus: 'KickOff',
    };
}

/** 19:50:45 - INTERVALLO: FirstHalfEnd, minuto 50 (reg 45, +5). */
export function statoIpsIntervallo(): Record<string, unknown> {
    return {
        eventTypeId: 1, eventId: 35797769, score: punteggio('1', false),
        timeElapsed: 50, elapsedRegularTime: 45, elapsedAddedTime: 5,
        fullTimeElapsed: ORA_ZERO, status: 'FirstHalfEnd', matchStatus: 'FirstHalfEnd',
    };
}

/** 20:10:25 - SECONDO TEMPO al 48': SecondHalfKickOff, reg 48, niente added. */
export function statoIps2T(): Record<string, unknown> {
    return {
        eventTypeId: 1, eventId: 35797769, score: punteggio('1', true),
        timeElapsed: 48, elapsedRegularTime: 48,
        fullTimeElapsed: ORA_ZERO, status: 'SecondHalfKickOff', matchStatus: 'SecondHalfKickOff',
    };
}
