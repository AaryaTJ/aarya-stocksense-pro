$src     = 'C:\Users\priya\Aarya_Stocks'
$desktop = [Environment]::GetFolderPath('Desktop')
$dest    = Join-Path $desktop 'AaryaStockSensePro.zip'
$tmp     = Join-Path $env:TEMP 'AaryaStockSensePro_zip_tmp\Aarya_Stocks'

# Clean up any previous temp
if (Test-Path (Split-Path $tmp)) { Remove-Item (Split-Path $tmp) -Recurse -Force }
New-Item -ItemType Directory -Path $tmp -Force | Out-Null

# Copy everything except excluded folders/files
$skipFolders = @('dist','build','__pycache__','.streamlit','.git','.claude')
$skipFiles   = @('monitor.log','test_run.log','build_log.txt','make_zip.ps1',
                 'aarya_debug.spec','check_live.py','test_monitor.py','AaryaStockSensePro.zip')

Write-Host "Copying files..."
Get-ChildItem $src -Recurse -File | Where-Object {
    $rel   = $_.FullName.Substring($src.Length + 1)
    $parts = $rel -split '\\'
    $skip  = $false
    foreach ($f in $skipFolders) { if ($parts -contains $f) { $skip = $true; break } }
    foreach ($f in $skipFiles)   { if ($_.Name -eq $f)      { $skip = $true; break } }
    -not $skip
} | ForEach-Object {
    $rel    = $_.FullName.Substring($src.Length + 1)
    $target = Join-Path $tmp $rel
    $dir    = Split-Path $target
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Copy-Item $_.FullName $target
    Write-Host "  + $rel"
}

# Zip the temp folder
if (Test-Path $dest) { Remove-Item $dest -Force }
Write-Host ""
Write-Host "Compressing..."
Compress-Archive -Path (Split-Path $tmp) -DestinationPath $dest -CompressionLevel Optimal

# Clean up temp
Remove-Item (Split-Path $tmp) -Recurse -Force

$sizeMB = [math]::Round((Get-Item $dest).Length / 1MB, 2)
Write-Host ""
Write-Host "DONE! Zip saved to:"
Write-Host "  $dest"
Write-Host "  Size: $sizeMB MB"
