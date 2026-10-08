# Misura usa-e-getta scheda J: lunghezza (righe) delle funzioni/tipi gemelli in lib/{mike,safeBot,omega}.ts.
# Una dichiarazione a colonna 0 finisce alla successiva dichiarazione a colonna 0 (commenti inclusi: stima per eccesso di ~3 righe).
# Uso: python ARCHITETTURA_2026-10/strumenti/J_gemelli_lib.py
import re
GR = {
 "attiva/ferma/aggiorna": {"mike": ["activateMike","stopMike","updateMikeParams"], "safeBot": ["activateSafe","stopSafe","updateSafeParams"], "omega": ["activateOmega","stopOmega","updateOmegaParams"]},
 "stato+trade (fetch)": {"mike": ["fetchMikeState","fetchMikeTrades"], "safeBot": ["fetchSafeState","fetchSafeTrades","fetchSafeActivity"], "omega": ["fetchOmegaState","fetchOmegaTrades"]},
 "realtime subscribe": {"mike": ["subscribeMike","MIKE_REALTIME_TABLES"], "safeBot": ["subscribeSafeBot"], "omega": ["subscribeOmega"]},
 "esito richiesta": {"mike": ["MikeRequestOutcome","requestOutcome","lastRequestFor","MIKE_REQUEST_KIND_LABEL","MIKE_REQUEST_CODE_MESSAGE"], "safeBot": ["RequestOutcome","requestOutcome","lastRequestFor","RequestTone"], "omega": []},
 "freschezza feed": {"mike": ["FeedTone","FeedFreshness","etaQuoteS","feedFreshness"], "safeBot": ["FEED_ROW_STALE_MS","FEED_HARD_MAX_MS","SCANNER_STALE_MS","FeedFreshness","feedFreshness","staleReason"], "omega": []},
 "regolamento/notifica": {"mike": ["detectSettledEvents"], "safeBot": ["detectSettlements"], "omega": ["SettlementNotice","settlementNotifications"]},
 "equity": {"mike": ["MikeEquityPoint","mikeEquitySeries"], "safeBot": ["buildEquitySeries"], "omega": ["buildEquitySeries"]},
 "riconciliazione": {"mike": [], "safeBot": ["isReconciling","errorFinal"], "omega": ["isReconciling","reconcilingSince","terminalError"]},
 "aggregati per modalita": {"mike": ["MikeAggregates"], "safeBot": ["SafeAggregates","SafeAggregatesByMode","aggregatesHaveDay","aggregatiDellaModalita","modalitaConAttivita","fetchSafeAggregates"], "omega": ["OmegaAggregates","aggregatiOmegaDellaModalita","omegaModalitaConAttivita"]},
 "tipi Status/Mode/Stats/Control": {"mike": ["MikeStatus","MikeMode","MikeStats","MikeControl"], "safeBot": ["SafeBotStatus","SafeMode","SafeStats","SafeControl"], "omega": ["OmegaStatus","OmegaMode","OmegaStats","OmegaControl"]},
 "tipi Trade/Activity/State": {"mike": ["MikeTrade","MikeActivity","MikeStateView"], "safeBot": ["SafeTrade","SafeActivityRow","SafeState"], "omega": ["OmegaTrade","OmegaActivityRow","OmegaState"]},
 "parametri (spec+default+merge)": {"mike": ["MikeParamGroup","MikeParamField","MIKE_PARAM_GROUP_LABEL","MIKE_PARAM_FIELDS","MIKE_PARAM_DEFAULTS","MikeParams","mergeMikeParams","parametriMikeDaSalvare"], "safeBot": ["SafeBotParams","SafeRiskParams","SAFE_RISK_DEFAULTS","SAFE_BOT_DEFAULTS","mergeRiskParams","mergeBotParams","strategyParamsOf","sameStrategyParams"], "omega": ["OmegaParams","OMEGA_DAILY_GOAL_MAX","OMEGA_PARAM_DEFAULTS","OmegaNumericParamKey","OMEGA_PARAM_GROUPS","OMEGA_PARAM_KEYS","omegaParamsPatch","obiettivoVuoto"]},
}
FILES = {"mike": "frontend/src/lib/mike.ts", "safeBot": "frontend/src/lib/safeBot.ts", "omega": "frontend/src/lib/omega.ts"}
dec = re.compile(r"^(?:export\s+)?(?:declare\s+)?(?:async\s+)?(?:function|const|let|interface|type|enum|class)\s+([A-Za-z0-9_]+)")
res = {}
for k, f in FILES.items():
    L = open(f, encoding="utf-8").read().split("\n")
    starts = [(i + 1, dec.match(l).group(1)) for i, l in enumerate(L) if dec.match(l)]
    ln = {}
    for j, (s, n) in enumerate(starts):
        e = (starts[j + 1][0] - 1) if j + 1 < len(starts) else len(L)
        ln[n] = (s, e - s + 1)
    res[k] = ln
tot = {"mike": 0, "safeBot": 0, "omega": 0}
for g, d in GR.items():
    out = []
    for k in ("mike", "safeBot", "omega"):
        s = 0; parts = []
        for n in d[k]:
            if n in res[k]: s += res[k][n][1]; parts.append(f"{n}@{res[k][n][0]}")
            else: parts.append(f"{n}?")
        tot[k] += s; out.append(f"{k}={s}")
    print(g, "|", " ".join(out))
print("TOTALE gruppi gemelli (righe):", tot, "somma", sum(tot.values()))
