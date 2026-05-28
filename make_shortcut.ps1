$root     = $PSScriptRoot
$bat      = Join-Path $root 'run.bat'
$ico      = Join-Path $root 'aarya_icon.ico'
$ws       = New-Object -ComObject WScript.Shell
$startMenu = $env:APPDATA + '\Microsoft\Windows\Start Menu\Programs\Aarya StockSense Pro.lnk'
$desktop   = [Environment]::GetFolderPath('Desktop') + '\Aarya StockSense Pro.lnk'

foreach ($lnkPath in @($startMenu, $desktop)) {
    if (Test-Path $lnkPath) { Remove-Item $lnkPath -Force }
    $s = $ws.CreateShortcut($lnkPath)
    $s.TargetPath       = 'cmd.exe'
    $s.Arguments        = '/c ""' + $bat + '""'
    $s.WorkingDirectory = $root
    $s.Description      = 'Aarya StockSense Pro - Stock Analysis Tool'
    if (Test-Path $ico) { $s.IconLocation = $ico + ',0' }
    $s.WindowStyle      = 7
    $s.Save()
    Write-Host "Created: $lnkPath"
}
Write-Host "Done. Press Win key and type Aarya to launch."
