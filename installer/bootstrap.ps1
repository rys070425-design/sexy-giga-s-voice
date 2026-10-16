param([Parameter(Mandatory=$true)][string]$InstallRoot,[switch]$NoShortcuts)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
$env:PIP_DISABLE_PIP_VERSION_CHECK='1'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
function Run-Python([string]$Python,[string[]]$Arguments) {
    & $Python @Arguments
    if($LASTEXITCODE -ne 0){throw ('Python 작업 실패 (종료 코드 '+$LASTEXITCODE+')')}
}
function Python311 {
    $candidates=@((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
                  (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311_UVKR\python.exe'),
                  (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311_UVKR05\python.exe'))
    foreach($candidate in $candidates){
        if(Test-Path -LiteralPath $candidate){
            $version=& $candidate -c 'import sys,struct; print(sys.version_info.major,sys.version_info.minor,struct.calcsize(chr(80)))'
            if($LASTEXITCODE -eq 0 -and $version -eq '3 11 8'){return $candidate}
        }
    }
    return $null
}
try {
    Write-Output 'STAGE:1:Python 실행 환경 준비'
    $python=Python311
    if(-not $python){
        $download=Join-Path $InstallRoot '.installer\python-3.11.9-amd64.exe'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile $download
        $signature=Get-AuthenticodeSignature -LiteralPath $download
        if($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or $signature.SignerCertificate.Subject -notlike '*Python Software Foundation*'){throw 'Python 공식 서명 확인에 실패했습니다.'}
        $runtime=Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311_UVKR05'
        $args='/quiet InstallAllUsers=0 TargetDir="'+$runtime+'" Include_pip=1 Include_launcher=0 Include_test=0 PrependPath=0 Shortcuts=0 AssociateFiles=0'
        $process=Start-Process -FilePath $download -ArgumentList $args -WindowStyle Hidden -PassThru -Wait
        if($process.ExitCode -notin @(0,3010)){throw ('Python 설치 실패: '+$process.ExitCode)}
        $python=Python311
        if(-not $python){throw 'Python 실행 환경을 찾지 못했습니다.'}
    }
    Write-Output 'STAGE:2:앱 전용 실행 환경 생성'
    $venv=Join-Path $InstallRoot '.venv'
    $appPython=Join-Path $venv 'Scripts\python.exe'
    if(-not (Test-Path -LiteralPath $appPython)){Run-Python $python @('-m','venv',$venv)}
    Write-Output 'STAGE:3:필수 구성요소 설치'
    Run-Python $appPython @('-m','pip','install','--index-url','https://pypi.org/simple','--upgrade','pip')
    Run-Python $appPython @('-m','pip','install','--index-url','https://pypi.org/simple','--prefer-binary','--no-compile','-r',(Join-Path $InstallRoot 'requirements-install.txt'))
    $nvidia=Join-Path $env:SystemRoot 'System32\nvidia-smi.exe'
    if(Test-Path -LiteralPath $nvidia){
        $gpu=& $nvidia --query-gpu=name --format=csv,noheader 2>$null
        if($LASTEXITCODE -eq 0 -and $gpu){
            Run-Python $appPython @('-m','pip','install','--index-url','https://pypi.org/simple','--only-binary=:all:','nvidia-cublas-cu12==12.9.2.10','nvidia-cudnn-cu12==9.22.0.52','nvidia-cuda-nvrtc-cu12==12.9.86')
        }
    }
    Run-Python $appPython @('-B','-u',(Join-Path $InstallRoot 'prepare_runtime.py'))
    if(-not (Test-Path -LiteralPath (Join-Path $InstallRoot 'INSTALL_SUCCESS.json'))){throw '설치 검증 결과가 없습니다.'}
    if(-not $NoShortcuts){
        $shell=New-Object -ComObject WScript.Shell
        $destinations=@((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Universal Voice KR 0.5.lnk'),
                         (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Universal Voice KR 0.5.lnk'))
        foreach($path in $destinations){
            $shortcut=$shell.CreateShortcut($path)
            $shortcut.TargetPath=Join-Path $venv 'Scripts\pythonw.exe'
            $shortcut.Arguments='"'+(Join-Path $InstallRoot 'launch.py')+'"'
            $shortcut.WorkingDirectory=$InstallRoot
            $shortcut.IconLocation=Join-Path $InstallRoot 'voice.ico'
            $shortcut.Description='Universal Voice KR · 실시간 음성 자막'
            $shortcut.Save()
        }
    }
    Write-Output 'INSTALL_COMPLETE'
    exit 0
} catch {
    Write-Output ('INSTALL_ERROR: '+$_.Exception.Message)
    exit 1
}
