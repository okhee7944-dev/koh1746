<#
.SYNOPSIS
    유튜브 반자동화 도구 (yt.py) PowerShell 실행기

.DESCRIPTION
    Windows PowerShell에서 yt.py를 바로 실행할 수 있게 해주는 래퍼 스크립트.
    - 콘솔 출력 인코딩을 UTF-8로 맞춰 한글 깨짐을 막는다.
    - python과 yt-dlp 설치 여부를 확인하고, 없으면 안내한다.
    - 모든 인자를 그대로 yt.py에 전달한다.

.EXAMPLE
    .\yt.ps1 channel https://www.youtube.com/@채널명/videos --scan 50 --top 25

.EXAMPLE
    .\yt.ps1 transcript https://youtu.be/영상ID --lang ko

.EXAMPLE
    .\yt.ps1 thumbs https://www.youtube.com/@채널명/videos --top 3
#>

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$YtPy = Join-Path $ScriptDir "yt.py"

function Get-PythonCommand {
    foreach ($cmd in @("python", "python3", "py")) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            return $cmd
        }
    }
    return $null
}

$python = Get-PythonCommand
if (-not $python) {
    Write-Error "python을 찾을 수 없습니다. https://www.python.org/downloads/ 에서 설치한 뒤 다시 시도하세요."
    exit 1
}

& $python -m yt_dlp --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "yt-dlp가 설치되어 있지 않습니다. 먼저 설치하세요: $python -m pip install -U yt-dlp"
    exit 1
}

if (-not (Test-Path $YtPy)) {
    Write-Error "yt.py를 찾을 수 없습니다: $YtPy"
    exit 1
}

& $python $YtPy @args
exit $LASTEXITCODE
