"""Install the reproducible, data-only NLLB package with pinned hashes."""
import hashlib
from pathlib import Path
import tempfile
import urllib.request
import zipfile

ARCHIVE_NAME='UniversalVoiceKR_NLLB600M_int8_v1.zip'
ARCHIVE_SHA256='9cdf8346ca17a56d5162c267e224a04a2508804358e9cda083dd46ca77e7d804'
ARCHIVE_BYTES=582306922
MODEL_URL='https://github.com/rys070425-design/sexy-giga-s-voice/releases/download/translation-models-v1/'+ARCHIVE_NAME
MODEL_FILES={
    'model.bin':'398726640cc2a02cc6a35277fa3cf2159ce8a1a66b48aa1b6c8837a47e3dd00c',
    'config.json':'72901fbd8abd89fb5cf4a388f26fc681f5c4c58a1e1a88b30b879f107270e7ee',
    'shared_vocabulary.json':'768aa4170693765cb4c62fc485ea4fd954cd3e5a44bc645d11d83f41f2393776',
    'sentencepiece.bpe.model':'14bb8dfb35c0ffdea7bc01e56cea38b9e3d5efcdcb9c251d6b40538e1aab555a',
    'LICENSE.txt':'41003d4a74749c0220e33dd415042164b5a1093ed401f36277234f772d22d3d0',
}


def file_hash(path):
    with Path(path).open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def model_verified(directory):
    try:return all(file_hash(Path(directory)/name)==digest for name,digest in MODEL_FILES.items())
    except OSError:return False


def install_quality_model(root,log=print,archive=None):
    root=Path(root).resolve()
    destination=root/'models'/'nllb600m-int8'
    if model_verified(destination):
        log('NLLB 공용 번역 모델 확인 완료');return destination
    staging=root/'.installer';staging.mkdir(parents=True,exist_ok=True)
    if archive is None:
        archive=staging/ARCHIVE_NAME
        if not archive.is_file() or archive.stat().st_size!=ARCHIVE_BYTES or file_hash(archive)!=ARCHIVE_SHA256:
            partial=archive.with_suffix('.partial')
            log('NLLB 번역 모델 다운로드 · 약 582 MB · CC-BY-NC-4.0')
            request=urllib.request.Request(MODEL_URL,headers={'User-Agent':'UniversalVoiceKR-Setup'})
            with urllib.request.urlopen(request,timeout=60) as response,partial.open('wb') as output:
                received=reported=0
                while chunk:=response.read(1024*1024):
                    received+=len(chunk)
                    if received>ARCHIVE_BYTES:raise ValueError('번역 모델 다운로드 크기가 일치하지 않습니다.')
                    output.write(chunk)
                    if received-reported>=40*1024*1024:
                        log(f'번역 모델 다운로드 {received//1000000} / 582 MB');reported=received
            partial.replace(archive)
    archive=Path(archive)
    if archive.stat().st_size!=ARCHIVE_BYTES or file_hash(archive)!=ARCHIVE_SHA256:
        raise ValueError('번역 모델 파일의 SHA-256 검증에 실패했습니다. 공식 파일을 다시 받아 주세요.')
    with tempfile.TemporaryDirectory(prefix='translation-',dir=staging) as temporary:
        unpacked=Path(temporary)
        with zipfile.ZipFile(archive) as package:
            if set(package.namelist())!=set(MODEL_FILES)|{'MODEL_INFO.json'}:
                raise ValueError('번역 모델 패키지의 파일 목록이 일치하지 않습니다.')
            for name in package.namelist():
                # The exact allowlist above excludes paths and executables.
                with package.open(name) as source,(unpacked/name).open('wb') as output:
                    while chunk:=source.read(1024*1024):output.write(chunk)
        if not model_verified(unpacked):raise ValueError('번역 모델 데이터 검증에 실패했습니다.')
        destination.mkdir(parents=True,exist_ok=True)
        for name in (*MODEL_FILES,'MODEL_INFO.json'):(unpacked/name).replace(destination/name)
    log('NLLB 공용 번역 모델 설치·무결성 확인 완료')
    return destination
