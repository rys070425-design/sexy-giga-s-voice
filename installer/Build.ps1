$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    $sourcePath=Join-Path $PSScriptRoot '..\app'
    $archivePath=Join-Path $PSScriptRoot 'payload.zip'
    $outputPath=Join-Path $PSScriptRoot '..\dist'
    New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
    # Explicit file selection prevents local model caches or credentials from
    # entering a rebuilt installer.
    $files=@(Get-ChildItem -LiteralPath $sourcePath -File -Filter '*.py')
    $files+=Get-Item -LiteralPath (Join-Path $sourcePath 'voice.ico'),(Join-Path $sourcePath 'requirements-install.txt'),(Join-Path $sourcePath 'packs'),(Join-Path $sourcePath 'browser_source_extension')
    Compress-Archive -LiteralPath $files.FullName -DestinationPath $archivePath -Force
    $output=Join-Path $outputPath 'UniversalVoiceKR_Setup_v082.exe'
    & "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /target:winexe /platform:x64 /optimize+ /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll /win32icon:voice.ico /resource:payload.zip,payload.zip /resource:bootstrap.ps1,bootstrap.ps1 ("/out:"+$output) Setup.cs
    if($LASTEXITCODE -ne 0){throw 'Installer build failed'}
    $hash=(Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLower()
    Set-Content -LiteralPath (Join-Path $outputPath 'UniversalVoiceKR_Setup_v082.sha256') -Value ($hash+'  UniversalVoiceKR_Setup_v082.exe') -Encoding ascii
} finally {Pop-Location}
