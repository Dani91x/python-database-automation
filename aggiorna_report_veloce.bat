@echo off
echo ============================================
echo   AGGIORNA REPORT VELOCE - Modelli read-only
echo   Betfair Trading System
echo ============================================
echo.
echo  MODELLI SOLO-LETTURA dal database (ai_model_registry):
echo  i pronostici usano sempre l'ultima versione presente
echo  sul DB (riscaricata se piu' recente della cache).
echo  NON addestra, NON carica, NON cancella alcun modello.
echo  Le leghe senza modelli sul DB non avranno predizioni AI.
echo.

cd /d "%~dp0"

echo [1/2] Lancio report giornaliero (modelli read-only dal DB)...
python -m Betfair.betfair_report_manager --skip-training

echo.
echo [2/2] Aggiornamento fogli Money Management...
python aggiorna_mm_sheets.py

echo.
echo ============================================
echo   COMPLETATO!
echo ============================================
pause
