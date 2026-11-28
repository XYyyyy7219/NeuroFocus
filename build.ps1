param([string]$Python = "python", [string]$Destination = "$PSScriptRoot/dist",
      [string]$BuildDirectory = "$PSScriptRoot/build")
$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    & $Python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
    $assets = @('--add-data', "$PSScriptRoot/neurofocus/literary_catalog.json:neurofocus")
    foreach ($name in @('deep-field.jpg','spiral.png','photosphere.png')) {
        $assets += @('--add-data', "$PSScriptRoot/neurofocus/sky_assets/${name}:neurofocus/sky_assets")
    }
    & $Python -m PyInstaller --noconfirm --clean --onedir --windowed @assets --noupx --name NeuroFocus --icon "$PSScriptRoot/NeuroFocus.ico" --distpath $Destination --workpath $BuildDirectory --specpath $BuildDirectory NeuroFocus.py
    if ($LASTEXITCODE -ne 0) { throw "Packaging failed" }
} finally { Pop-Location }
