# Creates (or replaces) the "Voice Anywhere" shortcut in your Startup folder, so the tray
# app starts every time you sign in to Windows, and starts it now. The shortcut runs:
#     <project>\.venv\Scripts\pythonw.exe -m voice_anywhere     (working folder: <project>)
# No administrator rights needed. Safe to run again: the existing shortcut is overwritten,
# and a second copy of the app just exits quietly.
#
# Run it (one line, from anywhere):
#   powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Tool Dev\voice-anywhere\scripts\make_shortcut.ps1"
# or double-click create_shortcut.bat in the project folder, which runs exactly that.
# Add -Remove to take Voice Anywhere out of the Startup folder again
# (remove_shortcut.bat does that).

param([switch]$Remove)

$ErrorActionPreference = 'Stop'

# The Startup folder of the signed-in user (shell:startup).
$startup = [Environment]::GetFolderPath('Startup')
$path    = Join-Path $startup 'Voice Anywhere.lnk'

if ($Remove) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path
        Write-Output "Removed $path"
        Write-Output "Voice Anywhere will no longer start with Windows. To stop the copy that is"
        Write-Output "running now, right-click its tray icon and choose Quit."
    } else {
        Write-Output "Nothing to remove: $path does not exist."
    }
    return
}

# Every path comes from where this script lives, so the project can sit in any folder,
# including ones with spaces.
$root   = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root '.venv\Scripts\pythonw.exe'
$icon   = Join-Path $root 'voice_anywhere\voice-anywhere.ico'

foreach ($needed in @($target, $icon)) {
    if (-not (Test-Path -LiteralPath $needed)) {
        Write-Error "Not found: $needed`nCreate the .venv first (see README, Setup)."
    }
}

$link = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
$link.TargetPath       = $target
$link.Arguments        = '-m voice_anywhere'
$link.WorkingDirectory = $root
$link.IconLocation     = "$icon,0"
$link.Description      = 'Voice Anywhere: offline dictation for any program'
$link.WindowStyle      = 1
$link.Save()

Write-Output "Created $path"
Write-Output "Voice Anywhere will now start each time you sign in to Windows."

Start-Process -FilePath $path
Write-Output "Started it now: look for the round microphone icon by the clock"
Write-Output "(it may be hidden under the ^ arrow)."
