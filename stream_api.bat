@echo off
REM Avvia il RUNNER stream Betfair: iscrive GIOCATA + "Segui live", le segue fino
REM a fine partita, poi le carica nel Replay. NESSUN ordine reale (solo advisory).
REM NON ospita l'endpoint quote/ordini: per quelli avvia aggiorna_quote_betfair.bat
REM (puoi tenere ENTRAMBI i .bat aperti insieme).
REM Se non c'e' nessuna partita da seguire, il runner esce subito (normale).
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
echo Avvio runner stream Betfair (GIOCATA + Segui live) ...
"%PY%" -m Betfair.stream.runner
echo.
echo [runner terminato]
pause
