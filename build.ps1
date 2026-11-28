param([string]$Python = "python", [string]$Destination = "$PSScriptRoot/dist",
      [string]$BuildDirectory = "$PSScriptRoot/build")
$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    & $Python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
    & $Python -m PyInstaller --noconfirm --clean --onedir --windowed --add-data "$PSScriptRoot/neurofocus/sky_assets:neurofocus/sky_assets" --noupx --name NeuroFocus --icon "$PSScriptRoot/NeuroFocus.ico" --distpath $Destination --workpath $BuildDirectory --specpath $BuildDirectory NeuroFocus.py
    if ($LASTEXITCODE -ne 0) { throw "Packaging failed" }
} finally { Pop-Location }
