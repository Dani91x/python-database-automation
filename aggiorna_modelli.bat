@echo off
echo ============================================================
echo   AGGIORNA MODELLI ML — Retraining completo tutte le leghe
echo   Betfair Trading System
echo ============================================================
echo.
echo  ATTENZIONE: Questo script riaddestra tutti i modelli ML.
echo  Puo' richiedere 30-90 minuti a seconda del numero di leghe.
echo  Non chiudere questa finestra durante l'esecuzione.
echo.
echo  Opzioni disponibili:
echo    - Solo leghe specifiche: aggiungi --leagues 39,40,41
echo    - Salta gia' addestrate oggi: aggiungi --skip-existing
echo    - Test senza addestrare: aggiungi --dry-run
echo.

cd /d "%~dp0"

echo [INFO] Avvio retraining...
echo.

python retrain_all_leagues.py --source db %*

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
