@echo off
echo ============================================
echo   AGGIORNA REPORT - Betfair Trading System
echo   Poisson + ML Side-by-Side A/B Test
echo ============================================
echo.

cd /d "%~dp0"
echo Directory: %CD%
echo.

echo [1/3] Pulizia stato precedente (nuovo giorno = auto-reset)...
echo.

echo [2/3] Lancio report giornaliero...
python -m Betfair.betfair_report_manager

echo.
echo [3/3] Aggiornamento fogli Money Management...
python aggiorna_mm_sheets.py

echo.
echo ============================================
echo   COMPLETATO!
echo ============================================
pause
