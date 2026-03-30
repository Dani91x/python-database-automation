@echo off
echo ============================================
echo   AGGIORNA SOLO FOGLI GOOGLE
echo   (retrofix + resolve + analytics)
echo ============================================
echo.

cd /d "%~dp0"

python aggiorna_solo_fogli.py

echo.
echo Aggiornamento fogli Money Management...
python aggiorna_mm_sheets.py

echo.
pause
