@echo off
echo ============================================
echo   AGGIORNA REPORT - Betfair Trading System
echo   Poisson + ML Side-by-Side A/B Test
echo ============================================
echo.
echo  MODELLI SOLO-LETTURA: usa i modelli FRESCHI dal
echo  database (ai_model_registry). NON addestra, NON
echo  carica e NON cancella alcun modello. Il training
echo  e' competenza esclusiva della pipeline cloud.
echo.

cd /d "%~dp0"
echo Directory: %CD%
echo.

echo [1/4] Pulizia stato precedente (nuovo giorno = auto-reset)...
echo.

echo [2/4] Lancio report giornaliero (modelli read-only dal DB)...
python -m Betfair.betfair_report_manager --skip-training

echo.
echo [3/4] Aggiornamento fogli Money Management...
python aggiorna_mm_sheets.py

echo.
echo [4/4] Quote Betfair COMPLETE (tutti i mercati, back+lay) per la dashboard...
echo   (rispetta i limiti API: batch peso 100, delay 0.6s, stop sui limiti. NON tocca i fogli)
python betfair_full_odds.py

echo.
echo ============================================
echo   COMPLETATO!
echo ============================================
pause
