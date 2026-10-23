# Bring this PC up to date with GitHub and install the mod jar into the game.
# Run from the project folder: powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1
param([string]$Game = "E:\SteamLibrary\steamapps\common\SlayTheSpire")
$ErrorActionPreference = "Stop"
git pull --ff-only origin main
$jar = Join-Path $PSScriptRoot "..\deploy\CommunicationMod.jar"
$target = Join-Path $Game "mods\CommunicationMod.jar"
if ((Get-FileHash $jar).Hash -ne (Get-FileHash $target).Hash) {
    if (Get-Process java -ErrorAction SilentlyContinue) { Write-Warning "The game is running: close it first, then run this again."; exit 1 }
    $backup = "$target.$(Get-Date -Format yyyyMMdd_HHmmss).bak"
    Copy-Item $target $backup
    Copy-Item $jar $target -Force
    Write-Output "Installed the new CommunicationMod.jar (old one kept as $backup)."
} else {
    Write-Output "The mod jar is already up to date."
}
