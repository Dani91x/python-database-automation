@echo off
echo ============================================
echo   IMPORT BACKFILL - Ultimi 15 giorni
echo   Operazioni Betfair -^> Report Personale
echo ============================================
echo.
echo  UNA TANTUM: importa nel Report Personale tutte le
echo  operazioni Betfair regolate degli ULTIMI 15 GIORNI
echo  (fino a ieri incluso). Idempotente: se lo rilanci
echo  aggiorna, non duplica.
echo.
echo  Dal giorno dopo usa aggiorna_report_betfair.bat
echo  (solo il giorno precedente).
echo.

cd /d "%~dp0"

echo [1/1] Import ultimi 15 giorni...
python import_betfair_operations.py --days 15

echo.
echo ============================================
echo   COMPLETATO!
echo ============================================
pause
