#!/bin/bash
# Falsificazione (30/09, UI Mike veritiera): ogni mutazione DEVE far diventare
# rosso il test indicato. Ripristino SEMPRE dalla copia in bak/ (mai git
# checkout). Uso: falsifica_ui_mike_veritiera.sh <cartella con bak/>
SP="$1"
W="$(cd "$(dirname "$0")/.." && pwd)"
PY="$W/.venv/Scripts/python.exe"
export SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x
cd "$W" || exit 2

muta() {  # nome file(relativo) sed-expr tipo(py|ts) test
  local nome="$1" f="$2" expr="$3" tipo="$4" test="$5"
  cp "$SP/bak/$(basename "$f")" "$W/$f"
  sed -i "$expr" "$W/$f"
  if cmp -s "$SP/bak/$(basename "$f")" "$W/$f"; then
    echo "[$nome] MUTAZIONE NON APPLICATA"; return
  fi
  if [ "$tipo" = py ]; then
    "$PY" -m pytest "$test" -q -p no:cacheprovider > "$SP/f_$nome.txt" 2>&1; rc=$?
  else
    (cd frontend && npx vitest run "$test" > "$SP/f_$nome.txt" 2>&1); rc=$?
  fi
  cp "$SP/bak/$(basename "$f")" "$W/$f"
  if [ $rc -ne 0 ]; then echo "[$nome] ROSSO (ok) rc=$rc"; else echo "[$nome] VERDE: il test NON morde"; fi
}

muta M1_prepartita frontend/src/components/controlroom/SchedaPreMatch.tsx \
  's/<FlussoBadge flusso={p.flusso} prePartita \/>/<FlussoBadge flusso={p.flusso} \/>/' ts src/lib/flussoLineeMike.test.tsx
muta M2_linea_decisa frontend/src/lib/flussoPrezzi.ts \
  's/if (gol != null \&\& gol > linea) continue;/void gol;/' ts src/lib/flussoLineeMike.test.tsx
muta M3_badge_ingioco frontend/src/components/controlroom/SchedaPartita.tsx \
  's/<FlussoLineeMikeBadge flusso={p.flussoMike} \/>//' ts src/lib/flussoLineeMike.test.tsx
muta M4_testo_linea Betfair/mike/feed.py \
  's/    return replace(esito, testo=testo) if testo else esito/    return esito/' py Betfair/mike/tests/test_mike_flusso_testo_linea_2026_09_30.py
muta M5_da_secondi Betfair/mike/service.py \
  's/"da_secondi": F.secondi_fermo_mike(/"da_secondi": F._flusso.secondi_fermo(/' py Betfair/mike/tests/test_mike_flusso_testo_linea_2026_09_30.py
muta M6_riallinea frontend/src/components/trading/ParamsSheetBase.tsx \
  "s/            setLastServerKey('');//" ts src/components/mike/MikeParamsSheet.riscontro.test.tsx
muta M7_rilancia frontend/src/components/mike/useMike.ts \
  's/        if (esito.errore != null) throw new Error(esito.errore);//' ts src/components/mike/useMike.saveParams.test.tsx
muta M8_opzione frontend/src/components/mike/MikeParamsSheet.tsx \
  's/^            riscontroSalvataggio\r\?$//' ts src/components/mike/MikeParamsSheet.riscontro.test.tsx
muta M9_null_zero frontend/src/lib/mike.ts \
  "s/typeof p.da_secondi === 'number' \&\& Number.isFinite(p.da_secondi)/Number.isFinite(n('da_secondi'))/" ts src/lib/flussoLineeMike.test.tsx
muta M10_catch_errore frontend/src/components/trading/ParamsSheetBase.tsx \
  "s/            setEsito({ ok: false, errore: String((e as Error)?.message ?? e) });/            setEsito({ ok: true, ms: Date.now() });/" ts src/components/mike/MikeParamsSheet.riscontro.test.tsx

# verifica finale: nessuna mutazione rimasta
for f in frontend/src/components/controlroom/SchedaPreMatch.tsx frontend/src/components/controlroom/SchedaPartita.tsx \
         frontend/src/lib/flussoPrezzi.ts Betfair/mike/feed.py Betfair/mike/service.py \
         frontend/src/components/trading/ParamsSheetBase.tsx frontend/src/components/mike/useMike.ts \
         frontend/src/components/mike/MikeParamsSheet.tsx frontend/src/lib/mike.ts; do
  cmp -s "$SP/bak/$(basename "$f")" "$W/$f" && echo "ripristinato $f" || echo "DIVERSO $f"
done
