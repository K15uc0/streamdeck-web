# Teste de fumaca do instalador (Windows, pwsh). Usado pelos workflows testes.yml
# e release.yml. Passos:
#  1) instala em silencio numa pasta temporaria (/DIR=), sem tarefas extras
#  2) confere arquivos, atalho do Menu Iniciar e que o valor Run "StreamDeck" NAO foi criado
#  3) abre o StreamDeck.exe instalado, espera /api/local/hello
#  4) roda o instalador de novo com /RESTARTAPP=1 com o app aberto (como a
#     atualizacao automatica): o instalador tem de fechar o app pela API,
#     trocar os arquivos e abrir de novo (PID novo no hello)
#  5) fecha pelo /api/local/quit, desinstala em silencio e confere que a pasta
#     do programa sumiu e a pasta de dados ficou intacta
# Uso: pwsh tests/installer_smoke.ps1 [-Installer dist-installer/StreamDeck-Instalador.exe]
param([string]$Installer = "dist-installer/StreamDeck-Instalador.exe", [int]$Timeout = 60)
$ErrorActionPreference = "Stop"

$setup = (Resolve-Path $Installer).Path
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("sd-inst-" + [guid]::NewGuid().ToString("N"))
$app = Join-Path $tmp "Programa Stream Deck"     # com espaco de proposito
$data = Join-Path $tmp "dados"
New-Item -ItemType Directory -Path $data | Out-Null
Copy-Item config.padrao.json (Join-Path $data "config.json")
Set-Content -Path (Join-Path $data "marcador.txt") -Value "nao apagar"
# o app aberto pelo instalador herda estas variaveis
$env:STREAMDECK_DATA = $data
$env:STREAMDECK_UPDATE_URL = "http://127.0.0.1:9/sem-rede"

$base = "http://127.0.0.1:8765"
$h = @{ "X-StreamDeck" = "1" }
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$exe = Join-Path $app "StreamDeck.exe"
$silent = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER")

function Show-Log {
  foreach ($f in @((Join-Path $tmp "instalar.log"), (Join-Path $tmp "atualizar.log"), (Join-Path $data "streamdeck.log"))) {
    if (Test-Path $f) { Write-Host "--- $f"; Get-Content $f -ErrorAction SilentlyContinue | Write-Host }
  }
}
function Stop-App {
  Get-Process StreamDeck -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe } | Stop-Process -Force -ErrorAction SilentlyContinue
}
function Fail([string]$msg) {
  Write-Host "FALHA: $msg"
  Show-Log
  Stop-App
  exit 1
}
function Wait-Hello([int]$NotPid = 0) {
  $t0 = Get-Date
  while (((Get-Date) - $t0).TotalSeconds -lt $Timeout) {
    try {
      $r = Invoke-RestMethod -Uri "$base/api/local/hello" -Headers $h -TimeoutSec 2
      if ($r.app -eq "streamdeck" -and $r.pid -ne $NotPid) { return $r }
    } catch { }
    Start-Sleep -Milliseconds 500
  }
  return $null
}
function Run-Setup([string[]]$ArgList) {
  # sem -Wait: no pwsh 7 o -Wait espera tambem os filhos, e com /RESTARTAPP=1
  # o filho e o proprio Stream Deck reaberto (ficaria esperando para sempre)
  $p = Start-Process -FilePath $setup -ArgumentList $ArgList -PassThru
  if (-not $p.WaitForExit(180000)) { Fail "instalador nao terminou em 3 minutos" }
  if ($p.ExitCode -ne 0) { Fail "instalador terminou com codigo $($p.ExitCode)" }
}

if (Get-ItemProperty -Path $runKey -Name StreamDeck -ErrorAction SilentlyContinue) {
  Fail "valor Run StreamDeck ja existe antes do teste (maquina suja)"
}

# 1) instala
Run-Setup ($silent + @("/DIR=`"$app`"", "/LOG=`"$(Join-Path $tmp 'instalar.log')`""))
foreach ($f in @($exe, (Join-Path $app "_internal"), (Join-Path $app "unins000.exe"), (Join-Path $app "instalado.txt"))) {
  if (-not (Test-Path $f)) { Fail "faltando depois de instalar: $f" }
}
Write-Host "ok instalado em $app"

# 2) atalho e registro
$lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "Stream Deck.lnk"
if (-not (Test-Path $lnk)) { Fail "atalho do Menu Iniciar nao criado: $lnk" }
if (Get-ItemProperty -Path $runKey -Name StreamDeck -ErrorAction SilentlyContinue) {
  Fail "valor Run StreamDeck criado sem a tarefa 'Iniciar com o Windows'"
}
Write-Host "ok atalho e sem iniciar com o Windows"

# 3) abre o instalado
$p = Start-Process -FilePath $exe -WorkingDirectory $app -ArgumentList "--sem-bandeja" -PassThru
$hello = Wait-Hello
if (-not $hello) { Fail "sem resposta em /api/local/hello do programa instalado" }
Write-Host "ok hello do instalado (PID $($hello.pid))"

# 4) atualizacao silenciosa com o app aberto
Run-Setup ($silent + @("/RESTARTAPP=1", "/DIR=`"$app`"", "/LOG=`"$(Join-Path $tmp 'atualizar.log')`""))
if (-not $p.WaitForExit(20000)) { Fail "o instalador nao fechou o app aberto" }
$hello2 = Wait-Hello -NotPid $hello.pid
if (-not $hello2) { Fail "o app nao reabriu depois da atualizacao (/RESTARTAPP=1)" }
Write-Host "ok atualizacao silenciosa: fechou e reabriu (PID $($hello2.pid))"

# 5) fecha, desinstala
try {
  $q = Invoke-RestMethod -Method Post -Uri "$base/api/local/quit" -Headers $h -ContentType "application/json" -Body "{}" -TimeoutSec 10
  if (-not $q.ok) { Fail "quit sem ok" }
} catch { Fail "quit falhou: $_" }
$t0 = Get-Date
while ((Get-Process StreamDeck -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe }) -and ((Get-Date) - $t0).TotalSeconds -lt 15) { Start-Sleep -Milliseconds 300 }
if (Get-Process StreamDeck -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe }) { Fail "o app nao fechou depois do quit" }
Write-Host "ok fechou"

$unins = Join-Path $app "unins000.exe"
Start-Process -FilePath $unins -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Wait | Out-Null
# o desinstalador se copia para a pasta temporaria e termina sozinho depois
$t0 = Get-Date
while ((Test-Path $exe) -or (Test-Path $unins)) {
  if (((Get-Date) - $t0).TotalSeconds -gt 60) { Fail "arquivos do programa ainda existem depois de desinstalar" }
  Start-Sleep -Milliseconds 500
}
if (Test-Path (Join-Path $app "_internal")) { Fail "_internal ficou depois de desinstalar" }
if (Test-Path $lnk) { Fail "atalho do Menu Iniciar ficou depois de desinstalar" }
if (Get-ItemProperty -Path $runKey -Name StreamDeck -ErrorAction SilentlyContinue) { Fail "valor Run ficou depois de desinstalar" }
if (-not (Test-Path (Join-Path $data "marcador.txt")) -or -not (Test-Path (Join-Path $data "config.json"))) {
  Fail "a desinstalacao mexeu na pasta de dados"
}
Write-Host "ok desinstalado; pasta de dados intacta"
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
exit 0
