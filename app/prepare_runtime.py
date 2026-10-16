"""Download base models and verify the actual new runtime without old app files."""
import json,sys,time
from pathlib import Path
from runtime_config import configure
root=configure()
from core import HOME, DEFAULT_SETTINGS, read_json, write_json
settings_file=HOME/'settings.json'
if settings_file.exists():
    config=read_json(settings_file,DEFAULT_SETTINGS)
    if config.get('quality_update_version')!='0.5':
        backup=HOME/('settings.before-051-'+time.strftime('%Y%m%d-%H%M%S')+'.json')
        backup.write_bytes(settings_file.read_bytes())
        for profile in config.get('profiles',[]):
            if isinstance(profile,dict):
                profile.update(model='large-v3-turbo',device='auto',beam_size=5,vad=1)
        config['quality_update_version']='0.5'
        write_json(settings_file,config)
import numpy as np
from cuda_runtime import prepare_cuda
prepare_cuda()
from faster_whisper import WhisperModel
from faster_whisper.utils import download_model
from argostranslate import package
from local_translation import LocalTranslator

print('STAGE:4:음성 인식 모델 다운로드',flush=True)
target=root/'models'/'large-v3-turbo'
download_model('large-v3-turbo',output_dir=str(target))
print('STAGE:5:영어 → 한국어 번역 모델 준비',flush=True)
installed={(p.from_code,p.to_code) for p in package.get_installed_packages()}
if ('en','ko') not in installed:
    package.update_package_index()
    candidates=[p for p in package.get_available_packages() if p.from_code=='en' and p.to_code=='ko' and getattr(p,'type','translate')=='translate']
    if not candidates:raise RuntimeError('공식 영어 → 한국어 번역 모델을 찾지 못했습니다.')
    package.install_from_path(candidates[-1].download())
print('STAGE:6:새 설치 환경 확인',flush=True)
translator=LocalTranslator()
translation=translator.translate('Hello, how are you?','en')
if not translation.strip():raise RuntimeError('번역 모델 확인 실패')
import ctranslate2
device='cuda' if ctranslate2.get_cuda_device_count() else 'cpu'
model=WhisperModel(str(target),device=device,compute_type='int8_float16' if device=='cuda' else 'int8',cpu_threads=4)
segments,_=model.transcribe(np.zeros(16000,np.float32),language='en',beam_size=1)
list(segments)
report=dict(version='0.7.0',python=sys.executable,device=device,model='large-v3-turbo',translation_ready=True,verified=True)
(root/'INSTALL_SUCCESS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('RUNTIME_VERIFIED',flush=True)
