param(
    [Parameter(Mandatory=$true)][string]$PlatformJar,
    [Parameter(Mandatory=$true)][string]$BuildTools,
    [Parameter(Mandatory=$true)][string]$Jdk,
    [string]$BuildDir = "$PSScriptRoot/build",
    [string]$Apk = "$PSScriptRoot/NeuroFocus-Android.apk"
)
$ErrorActionPreference='Stop'
function Run-Tool([string]$File,[string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$File failed with exit code $LASTEXITCODE" }
}
$PlatformJar=(Resolve-Path -LiteralPath $PlatformJar).Path
$BuildTools=(Resolve-Path -LiteralPath $BuildTools).Path
$BuildDir=[IO.Path]::GetFullPath($BuildDir)
$bin=Join-Path $Jdk 'bin'
$javac=Join-Path $bin 'javac.exe'
$java=Join-Path $bin 'java.exe'
$env:JAVA_HOME=$Jdk
$env:PATH="$bin;$env:PATH"
foreach ($d in 'generated','classes','dex','test') { New-Item -ItemType Directory -Path (Join-Path $BuildDir $d) -Force | Out-Null }
Push-Location $BuildDir
try {
    Run-Tool $javac @('-encoding','UTF-8','--release','8','-d','test',"$PSScriptRoot/src/Engine.java","$PSScriptRoot/tests/EngineTest.java")
    Run-Tool $java @('-cp','test','app.neurofocus.timer.EngineTest')
    $aapt=Join-Path $BuildTools 'aapt2.exe'
    Run-Tool $aapt @('compile','--dir',"$PSScriptRoot/res",'-o','res.zip')
    Run-Tool $aapt @('link','-o','unsigned.apk','-I',$PlatformJar,'--manifest',"$PSScriptRoot/AndroidManifest.xml",'-A',"$PSScriptRoot/assets",'--java','generated','res.zip')
    $sources=@(Get-ChildItem -LiteralPath "$PSScriptRoot/src",'generated' -Filter '*.java' -Recurse -File | ForEach-Object FullName)
    Run-Tool $javac (@('-encoding','UTF-8','--release','8','-classpath',$PlatformJar,'-d','classes')+$sources)
    Run-Tool (Join-Path $bin 'jar.exe') @('cf','classes.jar','-C','classes','.')
    Run-Tool $java @('-cp',(Join-Path $BuildTools 'lib/d8.jar'),'com.android.tools.r8.D8','--min-api','26','--lib',$PlatformJar,'--output','dex','classes.jar')
    Run-Tool 'python' @('-c',"from zipfile import ZipFile; z=ZipFile('unsigned.apk','a'); z.write('dex/classes.dex','classes.dex'); z.close()")
    Run-Tool (Join-Path $BuildTools 'zipalign.exe') @('-f','4','unsigned.apk','aligned.apk')
    if (-not (Test-Path -LiteralPath 'local-test.p12')) {
        Run-Tool (Join-Path $bin 'keytool.exe') @('-genkeypair','-keystore','local-test.p12','-storetype','PKCS12','-alias','neurofocus','-storepass','android','-keypass','android','-keyalg','RSA','-keysize','3072','-validity','10000','-dname','CN=NeuroFocus Local Build')
    }
    $signer=Join-Path $BuildTools 'lib/apksigner.jar'
    Run-Tool $java @('-jar',$signer,'sign','--ks','local-test.p12','--ks-pass','pass:android','--ks-key-alias','neurofocus','--v4-signing-enabled','false','--out',$Apk,'aligned.apk')
    Run-Tool $java @('-jar',$signer,'verify','--verbose',$Apk)
    Run-Tool $aapt @('dump','badging',$Apk)
} finally { Pop-Location }
