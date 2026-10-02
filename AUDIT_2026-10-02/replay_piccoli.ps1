# I tre replay di controllo del REPLAY VELOCE, uno dopo l'altro (mai in parallelo).
# Uso (dalla radice del worktree): powershell -File AUDIT_2026-10-02/replay_piccoli.ps1 PRIMA|DOPO
param([string]$etichetta)
$env:PYTHONPATH = (Get-Location).Path
$py = "C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/.venv/Scripts/python.exe"
$dati = "C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\_live_raw"
$out = "AUDIT_2026-10-02/replay"
$t = Get-Date
& $py -m Betfair.stream.backtest.certifica mike 35760084 --scenari base,riavvio,feed-stantio --worker 0 --data-dir $dati 2>$null > "$out/mike_base_riavvio_stantio_$etichetta.txt"
"mike  exit $LASTEXITCODE  $(((Get-Date)-$t).TotalSeconds) s"
$t = Get-Date
& $py -m Betfair.stream.backtest.certifica safe_base 35760084 --scenari rapidi --trasporto entrambi --worker 1 --data-dir $dati 2>$null > "$out/safe_base_rapidi_entrambi_$etichetta.txt"
"safe  exit $LASTEXITCODE  $(((Get-Date)-$t).TotalSeconds) s"
$t = Get-Date
& $py -m Betfair.stream.backtest.certifica omega 35760084 --scenari base --worker 0 --data-dir $dati 2>$null > "$out/omega_base_$etichetta.txt"
"omega exit $LASTEXITCODE  $(((Get-Date)-$t).TotalSeconds) s"
