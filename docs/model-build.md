# 번역 자료 출처와 재현

설치 프로그램은 `app/model_assets.py`에 고정한 공개 자료 주소와 SHA-256을 사용합니다. 내려받은 압축 파일 전체와 추출한 모델·토크나이저·라이선스를 각각 검증합니다. 모델 자료는 저장소의 Git 이력에 넣지 않고 Releases에 배포합니다.

원본은 [Meta NLLB-200 distilled 600M](https://huggingface.co/facebook/nllb-200-distilled-600M)의 revision `f8d333a098d19b4fd9a8b18f94170487ad3f821d`입니다. 원본 `pytorch_model.bin`의 SHA-256은 `c266c2cfd19758b6d09c1fc31ecdf1e485509035f6b51dfe84f1ada83eefcc42`입니다. [CTranslate2 공식 변환 안내](https://opennmt.net/CTranslate2/guides/transformers.html)의 NLLB 경로로 int8 양자화했습니다. 새로운 학습 데이터나 사용자 음성을 사용하지 않았습니다.

변환은 앱과 분리한 Python 3.11 환경에서 수행했습니다. 사용 버전은 CTranslate2 4.7.2, Transformers 4.55.4, Torch 2.8.0, SentencePiece 0.2.1입니다. 실제 앱 추론은 CTranslate2 4.8.3과 SentencePiece 0.2.1이며 Torch나 Transformers를 로드하지 않습니다.

위 revision의 config.json, pytorch_model.bin, sentencepiece.bpe.model, tokenizer.json, tokenizer_config.json, special_tokens_map.json을 받은 디렉터리를 준비한 뒤 다음 방식으로 변환할 수 있습니다. 변환 결과는 원본 모델의 **CC-BY-NC-4.0** 조건을 그대로 따릅니다.

```python
from ctranslate2.converters import TransformersConverter

# 이 두 고정 버전의 dtype 인자 이름 차이를 연결하는 어댑터입니다.
class Converter(TransformersConverter):
    def load_model(self, model_class, model_name_or_path, **kwargs):
        kwargs['torch_dtype'] = kwargs.pop('dtype', None)
        return model_class.from_pretrained(model_name_or_path, **kwargs)

Converter('official-source-directory').convert('nllb600m-int8', quantization='int8')
```

변환 디렉터리에 원본 sentencepiece.bpe.model을 복사합니다. 배포 압축 파일은 model.bin, config.json, shared_vocabulary.json, sentencepiece.bpe.model, LICENSE.txt, MODEL_INFO.json만 포함합니다. LICENSE.txt는 [CC-BY-NC-4.0 원문](https://creativecommons.org/licenses/by-nc/4.0/legalcode.txt), MODEL_INFO.json에는 원본 모델·revision·작성자 표시·변경 내용·개별 파일 해시가 있습니다. 앱의 26개 비교 문장에서는 이 경량 토크나이저 경로와 Transformers 경로의 결과가 모두 같았습니다.

모델마다 사용자별 튜닝이나 문장별 정답 치환을 넣지 않았습니다. 기존 사용자가 직접 저장한 문장 보정과 게임 문맥의 짧은 호출 사전은 별도 기능이며, 일반 대화 모델 비교에는 적용하지 않았습니다.
