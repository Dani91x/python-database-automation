# M5b - campionatore di risorse dei processi dell'app (SOLA LETTURA, in primo piano, finito).
# Da lanciare quando l'app e' accesa:  powershell -NoProfile -File m05b_campiona_processi.ps1 -Campioni 30 -Secondi 10
# Scrive una riga CSV per processo python/node/electron per campione: ora, pid, nome, riga di comando (corta),
# CPU% dal campione precedente (su 1 core), working set MB, private MB, thread, handle.
# Poi stampa mediana/p95/max per processo. NON avvia nulla, NON scrive fuori da stdout.
param([int]$Campioni = 30, [int]$Secondi = 10)
$ncpu = [Environment]::ProcessorCount
$prev = @{}
$righe = New-Object System.Collections.ArrayList
for ($i = 0; $i -lt $Campioni; $i++) {
  $t = Get-Date
  $ps = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|node|electron|Betfair)' }
  foreach ($p in $ps) {
    $g = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
    if (-not $g) { continue }
    $cpu = $g.CPU
    $pct = $null
    if ($prev.ContainsKey($p.ProcessId)) { $pct = [math]::Round(100 * ($cpu - $prev[$p.ProcessId].c) / (($t - $prev[$p.ProcessId].t).TotalSeconds), 1) }
    $prev[$p.ProcessId] = @{ c = $cpu; t = $t }
    $cl = ($p.CommandLine -replace '\s+', ' ')
    if ($cl.Length -gt 90) { $cl = $cl.Substring(0, 90) }
    [void]$righe.Add([pscustomobject]@{ ora = $t.ToString('HH:mm:ss'); pid = $p.ProcessId; nome = $p.Name; cmd = $cl; cpu1core = $pct;
      ws_mb = [math]::Round($g.WorkingSet64 / 1MB, 1); priv_mb = [math]::Round($g.PrivateMemorySize64 / 1MB, 1); thr = $g.Threads.Count; hnd = $g.HandleCount })
  }
  Start-Sleep -Seconds $Secondi
}
$righe | Group-Object pid | ForEach-Object {
  $w = $_.Group.ws_mb | Sort-Object; $c = ($_.Group | Where-Object { $_.cpu1core -ne $null }).cpu1core | Sort-Object
  [pscustomobject]@{ pid = $_.Name; cmd = $_.Group[0].cmd; campioni = $_.Count; ws_p50 = $w[[int]($w.Count * 0.5)]; ws_max = $w[-1];
    cpu_p50 = if ($c) { $c[[int]($c.Count * 0.5)] } else { $null }; cpu_p95 = if ($c) { $c[[int]([math]::Min($c.Count - 1, $c.Count * 0.95))] } else { $null } }
} | Format-Table -AutoSize
"(CPU in % di UN core: 100 = un core pieno; il PC ha $ncpu processori logici)"
