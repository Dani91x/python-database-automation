@echo off
echo ============================================================
echo   AGGIORNA MODELLI ML — Retraining completo tutte le leghe
echo   Betfair Trading System
echo ============================================================
echo.
echo  ATTENZIONE: Questo script riaddestra tutti i modelli ML.
echo  Puo' richiedere molte ore a seconda del numero di leghe.
echo  Non chiudere questa finestra durante l'esecuzione.
echo.
echo  RIPRESA AUTOMATICA: le leghe gia' addestrate negli ultimi 7
echo  giorni vengono saltate automaticamente. Puoi stoppare e
echo  rilanciare questo script in qualsiasi momento senza perdere
echo  il lavoro gia' fatto.
echo.
echo  VELOCITA': 2 leghe in parallelo, 2 worker ciascuna.
echo  RAM stimata: ~1.6 GB. CPU: 8 core usati al massimo.
echo.

cd /d "%~dp0"

echo [INFO] Avvio retraining (modalita' parallela + ripresa automatica)...
echo.

set RETRAIN_N_WORKERS=2
set RETRAIN_PARALLEL_LEAGUES=2

python retrain_all_leagues.py --source cache --skip-existing --max-age-days 7 --parallel-leagues 2 %*

echo.
echo ============================================================
if %ERRORLEVEL% EQU 0 (
    echo   COMPLETATO CON SUCCESSO!
    echo   I nuovi modelli sono attivi al prossimo aggiorna_report.bat
) else (
    echo   COMPLETATO CON ERRORI - controlla retrain_log_*.txt
)
echo ============================================================
pause
