// ============================================================================
// 08/10 - CANTIERE 12. LANCIO PORTABILE DEL PROCESSO FIGLIO `npx vite-node ...`.
//
// Una funzione sola, usata dallo script `scripts/verifica_barra_replay.ts` (quando si
// rilancia con l'ambiente giusto) e dal test che lancia lo script davvero
// (`replayVerificaBarraScript.test.ts`). Prima ognuno costruiva il comando a modo suo:
//   - il test faceva `spawn('npx', ...)` senza shell: su Windows `npx` e' `npx.cmd`
//     e senza shell il processo non parte (`spawn npx ENOENT`);
//   - lo script usava `npx.cmd` con `shell: true` ma con il percorso del file NON tra
//     virgolette: con shell, Node incolla i pezzi con uno spazio e un percorso come
//     "C:\PYTHON DATABASE\..." si spezzava in due argomenti.
//
// Funzione PURA: la piattaforma e' un parametro (i test costruiscono il comando per
// `win32` anche su Linux). Chi la chiama passa `process.platform`.
//   - non-win32: `npx` senza shell, argomenti cosi' come sono (niente quoting);
//   - win32: `npx.cmd` con `shell: true` e ogni argomento che ne ha bisogno tra
//     virgolette doppie (spazi, `&|<>^()%!`, virgolette interne con il backslash,
//     backslash finali raddoppiati).
// ============================================================================

export interface ComandoFiglio {
    /** eseguibile da passare a spawn / spawnSync */
    comando: string;
    /** argomenti da passare a spawn / spawnSync (gia' quotati se serve la shell) */
    argomenti: string[];
    /** valore di `shell` da passare a spawn / spawnSync */
    shell: boolean;
}

/** Quota UN argomento per `cmd.exe`: tra virgolette doppie se vuoto o con spazi / caratteri speciali. */
export function quotaArgomentoWin32(argomento: string): string {
    if (argomento !== '' && !/[\s"&|<>^()%!]/.test(argomento)) return argomento;
    // regole del parser degli argomenti di Windows: i backslash prima di una virgoletta (o in coda, prima
    // della virgoletta di chiusura) si raddoppiano; la virgoletta interna prende il suo backslash
    const protetto = argomento.replace(/(\\*)"/g, '$1$1\\"').replace(/(\\+)$/, '$1$1');
    return `"${protetto}"`;
}

/**
 * Comando per lanciare `npx vite-node <argomenti...>` sulla piattaforma indicata.
 * `argomenti` e' tutto quello che segue `vite-node` (percorso del file e opzioni).
 */
export function comandoViteNode(argomenti: string[], piattaforma: string): ComandoFiglio {
    if (piattaforma === 'win32') {
        return { comando: 'npx.cmd', argomenti: ['vite-node', ...argomenti].map(quotaArgomentoWin32), shell: true };
    }
    return { comando: 'npx', argomenti: ['vite-node', ...argomenti], shell: false };
}
