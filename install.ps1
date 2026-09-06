# Jarvis Workspace — one-command install for Windows.
#
#   irm https://raw.githubusercontent.com/celsiusm/jarvis-workspace/main/install.ps1 | iex
#
# The engine is Linux (Python + tmux). On Windows it runs inside WSL2 Ubuntu.
# This script: installs WSL if needed (one reboot), runs install.sh inside
# Linux, and drops Jarvis.bat on your Desktop. Double-click that next time.
#
# Full app — same as Linux. You bring your own agent CLIs (Claude, Codex, …).

$ErrorActionPreference = 'Stop'
$RawInstall = 'https://raw.githubusercontent.com/celsiusm/jarvis-workspace/main/install.ps1'

function Write-Step([string]$Message) {
    Write-Host $Message
}

function Test-IsAdmin {
    $p = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-WslEngine {
    return [bool](Get-Command wsl.exe -ErrorAction SilentlyContinue)
}

function Test-WslDistro {
    if (-not (Test-WslEngine)) { return $false }
    try {
        $null = & wsl.exe -- true 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Install-WslThenExit {
    Write-Step 'WSL2 is required. Installing Ubuntu (Windows will ask for a reboot).'
    if (-not (Test-IsAdmin)) {
        Write-Host ''
        Write-Host 'Re-open PowerShell as Administrator and run:'
        Write-Host "  irm $RawInstall | iex"
        exit 1
    }
    & wsl.exe --install
    Write-Host ''
    Write-Host 'Reboot, then run the same command again:'
    Write-Host "  irm $RawInstall | iex"
    Write-Host 'If Ubuntu asks for a Unix username on first open, finish that, then re-run.'
    exit 0
}

function Invoke-LinuxInstall {
    Write-Step 'Warming up WSL…'
    & wsl.exe -- true
    if ($LASTEXITCODE -ne 0) {
        throw 'WSL did not start. Open Ubuntu from the Start menu once, then re-run this installer.'
    }

    Write-Step 'Installing Jarvis inside WSL (~/jarvis-workspace, full Python deps)…'
    $inner = @'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
REPO="$HOME/jarvis-workspace"
if [ ! -f "$REPO/plotspace/main.py" ]; then
  if command -v sudo >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y git curl
  else
    apt-get update -y
    apt-get install -y git curl
  fi
  git clone --depth 1 https://github.com/celsiusm/jarvis-workspace.git "$REPO"
fi
bash "$REPO/install.sh" --no-start
'@
    $inner = $inner -replace "`r`n", "`n"
    & wsl.exe -- bash -lc $inner
    if ($LASTEXITCODE -ne 0) {
        throw 'install.sh inside WSL failed. Open Ubuntu and look at the output above.'
    }
}

function Install-DesktopLauncher {
    $desktop = [Environment]::GetFolderPath('Desktop')
    if (-not $desktop) { $desktop = Join-Path $env:USERPROFILE 'Desktop' }
    $dest = Join-Path $desktop 'Jarvis.bat'
    Write-Step "Desktop shortcut → $dest"
    $bat = & wsl.exe -- bash -lc 'cat "$HOME/jarvis-workspace/scripts/abrir-jarvis-app.bat"'
    if ($LASTEXITCODE -ne 0 -or -not $bat) {
        throw 'Could not read scripts/abrir-jarvis-app.bat from WSL.'
    }
    $text = if ($bat -is [Array]) { [string]::Join("`r`n", $bat) } else { [string]$bat }
    if ($text -notmatch 'localhost:3000') {
        throw 'The launcher copied from WSL does not look like Jarvis.bat.'
    }
    [System.IO.File]::WriteAllText($dest, $text.TrimEnd() + "`r`n")
    return $dest
}

$dry = $false
$noStart = $false
foreach ($a in $args) {
    if ($a -eq '--dry-run' -or $a -eq '-DryRun') { $dry = $true }
    if ($a -eq '--no-start' -or $a -eq '-NoStart') { $noStart = $true }
}
if ($env:JARVIS_INSTALL_DRY_RUN -eq '1') { $dry = $true }

Write-Step 'Jarvis Workspace for Windows (engine in WSL2).'

if ($dry) {
    Write-Step '[dry-run] wsl --install  (if WSL is missing)'
    Write-Step '[dry-run] wsl -- bash install.sh --no-start'
    Write-Step '[dry-run] copy abrir-jarvis-app.bat → Desktop\Jarvis.bat'
    Write-Step '[dry-run] start Jarvis.bat'
    exit 0
}

if (-not (Test-WslDistro)) {
    if (-not (Test-WslEngine)) {
        Install-WslThenExit
    }
    Write-Step 'WSL is installed but no distro answered. Installing Ubuntu…'
    if (-not (Test-IsAdmin)) {
        Write-Host "Open PowerShell as Administrator and run:  wsl --install -d Ubuntu"
        Write-Host "Then reboot, open Ubuntu once, and re-run:"
        Write-Host "  irm $RawInstall | iex"
        exit 1
    }
    & wsl.exe --install -d Ubuntu
    Write-Host 'If Windows asked for a reboot, do that, open Ubuntu once, then re-run this installer.'
    exit 0
}

Invoke-LinuxInstall
$launcher = Install-DesktopLauncher

Write-Host ''
Write-Host "Installed. Shortcut: $launcher"
Write-Host 'Next time: double-click Jarvis.bat on the Desktop.'
Write-Host 'Then ⚙ → Accounts to link Claude / Codex / Grok / … (you bring those CLIs).'

if (-not $noStart) {
    Write-Step 'Starting Jarvis…'
    Start-Process -FilePath $launcher
}

exit 0
