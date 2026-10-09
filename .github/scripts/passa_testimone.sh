#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Staffetta della catena notturna (09/10/2026, cantiere orologio notturno).
#
# Uso:  bash .github/scripts/passa_testimone.sh <prossimo.yml> [chiave=valore ...]
#
# Lancia il PROSSIMO anello della catena con workflow_dispatch usando il
# GITHUB_TOKEN del job (env GH_TOKEN). Perche' workflow_dispatch e non
# workflow_run: GitHub non esegue piu' di tre livelli di workflow_run in fila
# (docs "Events that trigger workflows", sezione workflow_run), la catena ne ha
# nove; workflow_dispatch fatto con GITHUB_TOKEN crea sempre una run (docs
# "GITHUB_TOKEN": eccezione workflow_dispatch / repository_dispatch).
#
# Al prossimo anello passa sempre catena=true (cosi' a sua volta passera' il
# testimone) piu' le coppie chiave=valore date qui.
#
# MAI DUE LANCI: un solo tentativo. Se il comando fallisce, prima di ritentare
# si chiede a GitHub se una run del prossimo anello e' stata creata dopo
# l'inizio di questo passo (il comando puo' fallire DOPO che GitHub ha creato
# la run: rete). Se c'e', non si rilancia. Se non c'e', un solo nuovo tentativo;
# se fallisce anche quello il job esce 1 (run ROSSA, visibile) e la verifica
# delle 07:30 UTC lo segnala in live_alerts (CATENA_NOTTURNA_INCOMPLETA).
# ---------------------------------------------------------------------------
set -u

PROSSIMO="${1:?manca il workflow del prossimo anello}"
shift
RAMO="${GITHUB_REF_NAME:-master}"
DAL="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

ARGOMENTI=(-f catena=true)
for kv in "$@"; do
  ARGOMENTI+=(-f "$kv")
done

echo "[STAFFETTA] da ${GITHUB_WORKFLOW:-?} (run ${GITHUB_RUN_ID:-?}) a ${PROSSIMO} sul ramo ${RAMO}: ${ARGOMENTI[*]}"

if gh workflow run "$PROSSIMO" --ref "$RAMO" "${ARGOMENTI[@]}"; then
  echo "[STAFFETTA] OK: ${PROSSIMO} lanciato."
  exit 0
fi

# attesa prima del controllo (i test la accorciano con PASSA_TESTIMONE_ATTESA_S)
ATTESA_S="${PASSA_TESTIMONE_ATTESA_S:-90}"
echo "[STAFFETTA] lancio di ${PROSSIMO} non confermato: controllo fra ${ATTESA_S} s se la run e' stata creata comunque."
sleep "$ATTESA_S"
N="$(gh api -X GET "repos/${GITHUB_REPOSITORY}/actions/workflows/${PROSSIMO}/runs" \
       -f event=workflow_dispatch -f created=">=${DAL}" --jq '.total_count' 2>/dev/null || echo "")"
if [ -n "$N" ] && [ "$N" -gt 0 ]; then
  echo "[STAFFETTA] OK: ${PROSSIMO} risulta creato (${N} run dal ${DAL}): nessun secondo lancio."
  exit 0
fi
if [ -z "$N" ]; then
  echo "::error::[STAFFETTA] stato di ${PROSSIMO} non leggibile da GitHub: NON rilancio (mai due lanci). Catena ferma qui: lanciare a mano ${PROSSIMO} con catena=true."
  exit 1
fi

echo "[STAFFETTA] nessuna run di ${PROSSIMO} dal ${DAL}: secondo e ultimo tentativo."
if gh workflow run "$PROSSIMO" --ref "$RAMO" "${ARGOMENTI[@]}"; then
  echo "[STAFFETTA] OK al secondo tentativo: ${PROSSIMO} lanciato."
  exit 0
fi
echo "::error::[STAFFETTA] ${PROSSIMO} NON lanciato dopo due tentativi: catena ferma qui. Lanciare a mano ${PROSSIMO} con catena=true."
exit 1
