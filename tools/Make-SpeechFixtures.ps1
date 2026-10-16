param([string]$OutputDirectory=(Join-Path $PSScriptRoot 'fixtures'))
$ErrorActionPreference='Stop'
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$OutputDirectory=(Resolve-Path -LiteralPath $OutputDirectory).Path
$samples=@(
    @{Language='ko';Voice='Heami';Text='적들이 우리 기지로 밀고 들어오고 있어요. 오른쪽으로 돌아서 공격하세요. 잠깐 기다려 주세요. 지금 회복하고 있어요.'},
    @{Language='en';Voice='Zira';Text='They are pushing our base. Watch the right side. Wait a second, I am healing. We need to defend the entrance together.'}
)
foreach($sample in $samples){
    $speaker=New-Object -ComObject SAPI.SpVoice
    $voice=@($speaker.GetVoices() | Where-Object {$_.GetDescription() -match $sample.Voice})
    if($voice.Count -eq 0){throw ('Windows SAPI voice missing: '+$sample.Voice)}
    $speaker.Voice=$voice[0]
    $speaker.Rate=0
    $stream=New-Object -ComObject SAPI.SpFileStream
    try {
        $stream.Open((Join-Path $OutputDirectory ('speech-'+$sample.Language+'.wav')),3,$false)
        $speaker.AudioOutputStream=$stream
        [void]$speaker.Speak($sample.Text)
    } finally {$stream.Close()}
}
