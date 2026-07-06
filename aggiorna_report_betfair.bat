@echo off
echo ============================================
echo   AGGIORNA REPORT BETFAIR - Operazioni
echo   Import operazioni Betfair -^> Report Personale
echo ============================================
echo.
echo  Importa le operazioni Betfair REGOLATE del giorno
echo  precedente (default) nel Report Personale (dashboard):
echo  P^&L reale + commissione reale, raggruppate per mercato,
echo  con pronostici API-Football e direzioni motori congelati.
echo  Idempotente: rilanciarlo AGGIORNA (non duplica).
echo.
echo  Per una data specifica:  aggiorna_report_betfair.bat --date 2026-07-05
echo  Backfill ultimi 15 giorni: aggiorna_report_betfair.bat --days 15
echo.

cd /d "%~dp0"

if "%~1"=="" (
    echo [1/1] Import operazioni del giorno PRECEDENTE...
    python import_betfair_operations.py
) else (
    echo [1/1] Import operazioni ^(%*^)...
    python import_betfair_operations.py %*
)

echo.
echo ============================================
echo   COMPLETATO!
echo ============================================
pause
