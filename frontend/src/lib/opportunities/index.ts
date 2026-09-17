// ============================================================================
// index.ts — punto di ingresso unico del motore di opportunità Betfair.
// ============================================================================
export * from './types';
export * from './fill';
export * from './helpers';
export * from './snapshot';
export * from './engine';
export * from './tier0_arb';
export * from './tier1_quasi';
export * from './tier2_micro';
export * from './validate';
// tier0_arb e tier1_quasi definiscono entrambi phaseFromMinute (stessa logica,
// firme di tipo diverse): risolvo l'ambiguita' del barrel export esplicitando
// quale versione esporta l'indice. Nessun consumer importa phaseFromMinute da
// qui (ogni file la importa dal proprio modulo tier), quindi la scelta non
// cambia comportamento a runtime.
export { phaseFromMinute } from './tier1_quasi';
