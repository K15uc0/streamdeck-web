# Teste de fumaca do StreamDeck.exe (Windows, pwsh). Usado pelos workflows
# testes.yml e release.yml: abre o .exe com dados numa pasta temporaria,
# espera /api/local/hello, confere /api/config, /api/actions e
# /api/local/windows e fecha pelo /api/local/quit. (No modo --onefile o PID do
# hello e o do processo filho, nao o do Start-Process.)
# Uso: pwsh tests/exe_smoke.ps1 [-Exe dist/StreamDeck.exe]
param([string]$Exe = "dist/StreamDeck.exe", [int]$Timeout = 60)
$ErrorActionPreference = "Stop"

$exePath = (Resolve-Path $Exe).Path
$data = Join-Path ([IO.Path]::GetTempPath()) ("sd-exe-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $data | Out-Null
# config pronto: assim nao e "primeira vez" e o .exe nao abre o navegador
Copy-Item config.padrao.json (Join-Path $data "config.json")
$env:STREAMDECK_DATA = $data
$env:STREAMDECK_UPDATE_URL = "http://127.0.0.1:9/sem-rede"

$base = "http://127.0.0.1:8765"
$h = @{ "X-StreamDeck" = "1" }
$out = Join-Path $data "saida.txt"
$err = Join-Path $data "erros.txt"
$p = Start-Process -FilePath $exePath -PassThru -NoNewWindow -RedirectStandardOutput $out -RedirectStandardError $err
$null = $p.Handle   # sem isto o ExitCode pode vir vazio no pwsh

function Show-Log {
  foreach ($f in @($out, $err, (Join-Path $data "streamdeck.log"))) {
    if (Test-Path $f) { Write-Host "--- $f"; Get-Content $f -ErrorAction SilentlyContinue | Write-Host }
  }
}
function Fail([string]$msg) {
  Write-Host "FALHA: $msg"
  Show-Log
  if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
  exit 1
}

# 1) espera subir
$hello = $null
$t0 = Get-Date
while (((Get-Date) - $t0).TotalSeconds -lt $Timeout) {
  if ($p.HasExited) { Fail "o .exe fechou sozinho (codigo $($p.ExitCode))" }
  try { $hello = Invoke-RestMethod -Uri "$base/api/local/hello" -Headers $h -TimeoutSec 2; break } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $hello) { Fail "sem resposta em /api/local/hello depois de $Timeout s" }
if ($hello.app -ne "streamdeck") { Fail "hello inesperado: $($hello | ConvertTo-Json -Compress)" }
Write-Host ("ok hello em {0:N1} s (PID {1})" -f ((Get-Date) - $t0).TotalSeconds, $hello.pid)

try {
  # 2) config, acoes e janelas
  $cfg = Invoke-RestMethod -Uri "$base/api/config" -Headers $h -TimeoutSec 10
  if ($cfg.version -ne 2 -or $cfg.pages.Count -lt 1) { Fail "config inesperado" }
  Write-Host "ok config: $($cfg.pages.Count) pagina(s)"
  $acts = Invoke-RestMethod -Uri "$base/api/actions" -Headers $h -TimeoutSec 10
  $types = @($acts.actions | ForEach-Object { $_.type })
  foreach ($t in @("none", "hotkey", "sound", "app", "site")) { if ($types -notcontains $t) { Fail "acao $t faltando" } }
  Write-Host "ok actions: $($types.Count) tipos"
  $wins = Invoke-RestMethod -Uri "$base/api/local/windows" -Headers $h -TimeoutSec 20
  if (-not $wins.ok) { Fail "/api/local/windows sem ok" }
  Write-Host "ok windows: $(@($wins.windows).Count) janela(s)"
  $page = Invoke-WebRequest -Uri "$base/" -TimeoutSec 10
  if ($page.StatusCode -ne 200 -or $page.Content -notmatch "core.js") { Fail "pagina inicial inesperada" }
  Write-Host "ok pagina inicial"
} catch {
  Fail "pedido falhou: $_"
}

# 3) fecha pelo /api/local/quit
try {
  $q = Invoke-RestMethod -Method Post -Uri "$base/api/local/quit" -Headers $h -ContentType "application/json" -Body "{}" -TimeoutSec 10
  if (-not $q.ok) { Fail "quit sem ok" }
} catch { Fail "quit falhou: $_" }
if (-not $p.WaitForExit(15000)) { Fail "o .exe nao fechou depois do quit" }
Start-Sleep -Milliseconds 500
try {
  Invoke-RestMethod -Uri "$base/api/local/hello" -Headers $h -TimeoutSec 2 | Out-Null
  Fail "porta 8765 ainda responde depois do quit"
} catch { }
Write-Host "ok fechou (codigo $($p.ExitCode))"
Remove-Item -Recurse -Force $data -ErrorAction SilentlyContinue
exit 0
