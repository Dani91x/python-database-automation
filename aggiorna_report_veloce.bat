@echo off
echo ============================================
echo   AGGIORNA REPORT VELOCE - Skip Training
echo   Betfair Trading System
echo ============================================
echo.
echo  Usa SOLO modelli gia' in cache locale.
echo  Le leghe senza modelli non avranno predizioni AI.
echo  Ideale per aggiornare i fogli rapidamente
echo  mentre il training gira in background.
echo.

cd /d "%~dp0"

echo [1/2] Lancio report giornaliero (skip training)...
python -m Betfair.betfair_report_manager --skip-training

echo.
echo [2/2] Aggiornamento fogli Money Management...
python aggiorna_mm_sheets.py

echo.
echo ============================================
echo   COMPLETATO!
echo ============================================
pause
