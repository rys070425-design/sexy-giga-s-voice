# 외부 구성요소

이 저장소는 모델 가중치나 Python 실행 환경을 포함하지 않습니다. 설치할 때 각 배포처에서 내려받습니다. 아래는 주요 구성요소이며 전체 의존성 목록은 `app/requirements-install.txt`와 설치 결과를 참고하세요.

| 구성요소 | 출처 | 라이선스 안내 |
|---|---|---|
| Whisper large-v3-turbo | https://huggingface.co/openai/whisper-large-v3-turbo | MIT |
| faster-whisper | https://github.com/SYSTRAN/faster-whisper | MIT |
| CTranslate2 | https://github.com/OpenNMT/CTranslate2 | MIT |
| NLLB-200 distilled 600M | https://huggingface.co/facebook/nllb-200-distilled-600M | 모델 CC-BY-NC-4.0 · 비상업용. NLLB Team / Meta AI, 2022. 재학습 없이 int8 양자화 |
| SentencePiece | https://github.com/google/sentencepiece | Apache-2.0 |
| Argos Translate 및 번역 패키지 | https://github.com/argosopentech/argos-translate | 코드 MIT/CC0, 모델은 각 배포 패키지 참조 |
| PySide6 / Qt | https://doc.qt.io/qtforpython-6/ | LGPLv3/GPLv3 또는 상용, 모듈별 조건 참조 |
| Python | https://www.python.org/ | PSF License |
| SoundCard | https://github.com/bastibe/SoundCard | BSD-3-Clause |
| WebRTC VAD wheels | https://github.com/daanzu/py-webrtcvad-wheels | MIT, 포함 WebRTC 코드 조건 참조 |
| NVIDIA CUDA/cuDNN 패키지 | https://pypi.org/project/nvidia-cudnn-cu12/ | NVIDIA 배포 라이선스 |

공식 Discord Streamkit은 사용자가 직접 연결하는 외부 서비스입니다. 이 앱은 Discord 봇 토큰을 요구하지 않습니다.

NLLB 자료에는 원문 라이선스와 모델 출처·버전·변경 정보가 포함됩니다. 변환 자료의 원본 revision은 `f8d333a098d19b4fd9a8b18f94170487ad3f821d`입니다. 기본 번역에 유료 API는 쓰지 않으며, 무료라는 설명이 상업적 이용 권한을 뜻하지는 않습니다. [공식 모델 안내](https://huggingface.co/facebook/nllb-200-distilled-600M)와 [모델 라이선스](https://creativecommons.org/licenses/by-nc/4.0/)를 참고하세요.
