@echo off
echo ============================================
echo   AGGIORNA REPORT - Betfair Trading System
echo   Poisson + ML Side-by-Side A/B Test
echo ============================================
echo.

cd /d "%~dp0"
echo Directory: %CD%
echo.

echo [1/2] Pulizia stato precedente (nuovo giorno = auto-reset)...
echo.

echo [2/2] Lancio report giornaliero...
python -m Betfair.betfair_report_manager

echo.
echo ============================================
echo   COMPLETATO!
echo ============================================
pause
