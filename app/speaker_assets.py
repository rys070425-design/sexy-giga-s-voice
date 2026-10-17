"""Verified data-only CAM++ model download; no runtime network calls."""
from pathlib import Path
import urllib.request
from model_assets import file_hash
from voice_identity import MODEL_NAME,MODEL_SHA256,MODEL_BYTES,MODEL_URL

def install_speaker_model(root,log=print):
    folder=Path(root)/'models'/'speaker';folder.mkdir(parents=True,exist_ok=True)
    target=folder/MODEL_NAME
    if target.is_file() and target.stat().st_size==MODEL_BYTES and file_hash(target)==MODEL_SHA256:return target
    partial=folder/(MODEL_NAME+'.partial')
    log('CAM++ 목소리 보조 모델 다운로드 · 약 28 MB · Apache-2.0')
    request=urllib.request.Request(MODEL_URL,headers={'User-Agent':'UniversalVoiceKR-Setup'})
    with urllib.request.urlopen(request,timeout=60) as response,partial.open('wb') as output:
        received=0
        while chunk:=response.read(1024*1024):
            received+=len(chunk)
            if received>MODEL_BYTES:raise ValueError('Speaker model download is too large')
            output.write(chunk)
    if partial.stat().st_size!=MODEL_BYTES or file_hash(partial)!=MODEL_SHA256:
        raise ValueError('Speaker model SHA-256 verification failed')
    partial.replace(target);log('CAM++ 목소리 보조 모델 확인 완료')
    return target
