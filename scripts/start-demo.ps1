param(
  [string]$HostName = "127.0.0.1",
  [int]$DemoPort = 3000,
  [int]$RuntimePort = 8765
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$RuntimeDir = Join-Path $RepoRoot "python\nanorole_runtime"
$RuntimeUrl = "http://${HostName}:${RuntimePort}"
$RuntimeHealthUrl = "$RuntimeUrl/health"
$CurrentProcessId = $PID

function Write-Step {
  param([string]$Message)
  Write-Host "==> $Message"
}

function Invoke-External {
  param(
    [string]$Label,
    [scriptblock]$Command
  )

  Write-Step $Label
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with exit code $LASTEXITCODE"
  }
}

function Stop-ProcessById {
  param([int]$ProcessId)

  if ($ProcessId -eq 0 -or $ProcessId -eq $CurrentProcessId) {
    return
  }

  $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if (-not $process) {
    return
  }

  Write-Host "Stopping $($process.ProcessName) pid=$ProcessId"
  Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-PortOwners {
  param([int]$Port)

  $portOwners = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.OwningProcess -ne 0 } |
    Select-Object -ExpandProperty OwningProcess -Unique

  foreach ($processId in $portOwners) {
    Stop-ProcessById -ProcessId $processId
  }
}

function Stop-OldRuntimeProcesses {
  try {
    $runtimeProcesses = Get-CimInstance Win32_Process -ErrorAction Stop |
      Where-Object {
        $name = [string]$_.Name
        $commandLine = [string]$_.CommandLine
        $_.ProcessId -ne $CurrentProcessId -and
          ($name -eq "uv.exe" -or $name -eq "uvicorn.exe" -or $name -eq "python.exe") -and
          $commandLine.Contains("nanorole_runtime.server:app")
      }
  } catch {
    Write-Host "Unable to inspect old Nanorole runtime processes; skipping process scan: $($_.Exception.Message)"
    return
  }

  foreach ($process in $runtimeProcesses) {
    Stop-ProcessById -ProcessId $process.ProcessId
  }
}

function Wait-ForRuntime {
  Write-Step "Waiting for Python core health"
  $deadline = (Get-Date).AddSeconds(15)
  do {
    Start-Sleep -Milliseconds 300
    try {
      $response = Invoke-WebRequest -UseBasicParsing $RuntimeHealthUrl -TimeoutSec 2
      if ($response.Content.Contains("nanorole-runtime")) {
        return
      }
    } catch {
      # Keep polling until the deadline.
    }
  } while ((Get-Date) -lt $deadline)

  throw "Python core did not become healthy at $RuntimeHealthUrl"
}

Write-Step "Cleaning old Nanorole demo/core processes"
Stop-PortOwners -Port $DemoPort
Stop-PortOwners -Port $RuntimePort
Stop-OldRuntimeProcesses

Invoke-External "corepack yarn build" { corepack yarn build }

Write-Step "Starting Python core runtime"
$env:NANOROLE_PROJECT_ROOT = $RepoRoot.Path
Start-Process `
  -FilePath "uv" `
  -ArgumentList @("run", "uvicorn", "nanorole_runtime.server:app", "--host", $HostName, "--port", [string]$RuntimePort) `
  -WorkingDirectory $RuntimeDir `
  -WindowStyle Hidden

Wait-ForRuntime

Write-Host "Nanorole demo: http://${HostName}:${DemoPort}"
Write-Host "Nanorole chat: http://${HostName}:${DemoPort}/chat"
Write-Host "Nanorole logs: http://${HostName}:${DemoPort}/logs"
Write-Host "Nanorole core: $RuntimeUrl"

$env:NANOROLE_PROJECT_ROOT = $RepoRoot.Path
$env:NANOROLE_RUNTIME_URL = $RuntimeUrl
$env:NANOROLE_DEMO_HOST = $HostName
$env:NANOROLE_DEMO_PORT = [string]$DemoPort
Invoke-External "corepack yarn workspace @nanorole/demo node dist/index.js" {
  corepack yarn workspace @nanorole/demo node dist/index.js
}
