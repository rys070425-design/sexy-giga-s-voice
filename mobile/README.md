# Universal Voice for Android 0.1.0

주변 사람의 말을 **휴대폰 마이크 → 음성 인식 → 번역 자막**으로 보여 주는 Android 앱입니다. Windows 프로그램과 별도로 설치합니다. Python, PC 연결, API 키는 필요하지 않습니다.

## 설치와 첫 사용

1. Android 휴대폰에서 [APK 받기](https://raw.githubusercontent.com/rys070425-design/sexy-giga-s-voice/main/dist/UniversalVoice_Android_v010.apk)를 엽니다. APK는 휴대폰 설치 파일입니다. 메신저에서 첨부를 막으면 저장소 링크를 공유하세요.
2. 다운로드한 APK를 열어 설치합니다. Android에서 다운로드한 앱 설치 허용을 요청할 수 있습니다. 갤럭시의 보안 설정이나 조직 정책이 설치를 제한하면 해당 기기의 안내를 따르세요. 이 앱은 Play 스토어에 게시되지 않았습니다.
3. **상대방의 언어 / They speak**와 **내가 읽을 언어 / I read**를 고릅니다. 한국어를 읽을 언어로 고르면 안내도 한국어가 됩니다. 나머지는 영어 안내입니다.
4. **언어팩 준비 / Prepare languages**에서 번역팩을 한 번 받습니다. 기본은 Wi-Fi에서만 다운로드합니다. Wi-Fi가 없으면 다운로드 대화상자의 해당 옵션을 해제할 수 있습니다.
5. **Google로 번역 / Translate with Google**을 누르고 마이크를 허용한 뒤 상대방 가까이에 놓습니다. **듣기 중지 / Stop listening**으로 끕니다.

기본 모드는 기기 내 음성 인식입니다. Android 12 이상이어도 기기·설치된 음성 서비스·언어에 따라 사용할 수 없습니다. ‘기기 내 음성 인식 불가’ 안내가 뜨면 **설정 → 기기 내 음성 인식** 버튼을 눌러 **휴대폰 기본 음성 인식** 사용을 선택할 수 있습니다. 이때 음성이 제공 업체로 전송될 수 있다는 설명에 동의해야 합니다. 앱이 자동으로 이 모드로 전환하지 않습니다.

음성 언어팩이 없다는 안내가 나오면 설정의 **음성 모델 준비**를 시도합니다. Android 13 이상에서 제공 업체가 지원해야 작동합니다. 지원하지 않으면 휴대폰 음성 서비스의 오프라인 언어 설정을 확인하거나 다른 언어/서비스를 선택합니다. 번역팩과 음성 인식팩은 서로 다릅니다.

## 화면과 동작

- 번역은 큰 글씨, 원문은 아래에 작게 표시합니다. 이전 문장 한 개도 남깁니다.
- 설정에서 원문 숨기기, 더 큰 자막, 듣는 동안 화면 유지, 자막 지우기를 선택할 수 있습니다. 휴대폰의 어두운 테마도 따릅니다.
- 빠른 임시 결과는 최신 것 위주로 처리합니다. 확정 문장 우선, 임시 번역 간격 700ms, 처리 대기 최대 4개 확정 문장과 1개 임시 문장으로 제한합니다. 과부하가 나면 오래된 문장을 건너뛸 수 있습니다.
- 중지, 언어 변경, 앱을 벗어남, 화면 잠금 시 마이크와 재시작 예약을 취소합니다. 앱으로 돌아와도 자동으로 듣지 않습니다.
- 한국어와 영어 UI를 제공합니다. 번역 언어 선택지는 25개이며 포르투갈어 두 지역은 같은 번역팩을 사용합니다. **선택지의 모든 언어를 해당 휴대폰에서 음성 인식할 수 있다는 뜻은 아닙니다.**
- 이번 버전은 말하는 언어를 직접 선택합니다. Windows판의 자동 언어 구분·동일 언어 숨김·Discord 닉네임·목소리 구분 기능은 모바일에 포함하지 않았습니다. 같은 입력/번역 언어 조합에서는 시작을 막습니다.

## 모델, 비용, 개인정보

음성 인식은 Android `SpeechRecognizer`의 기기 내 서비스(기본) 또는 사용자가 동의한 기본 음성 서비스를 사용합니다. 번역은 Google ML Kit `translate:17.0.3`의 기기 내 모델입니다. Windows판 Whisper/NLLB 모델을 휴대폰에 넣은 버전은 아닙니다.

이 앱에 유료 API 키나 구독 기능은 없습니다. 최초 번역팩은 언어당 보통 약 30MB이며 다운로드에는 인터넷이 필요합니다. 통신 요금과 선택한 휴대폰 음성 서비스의 조건은 별도입니다. 번역은 기기에서 처리하며 Google SDK 이용 약관과 개인정보 조건이 적용됩니다. SDK는 운영 진단 정보를 수집할 수 있습니다. 필수 Google Translate 출처 표시와 고지는 화면·개인정보 안내에 포함했습니다.

앱은 사용자의 마이크 녹음, 대화 텍스트, 목소리 프로필을 파일로 자동 저장하지 않습니다. 자막은 현재 실행 중 메모리에만 두며 설정과 다운로드한 번역팩만 유지합니다. 백업 및 기기 간 데이터 이전도 제외했습니다. 기본 음성 서비스의 음성 처리·보관 정책은 제공 업체의 정책을 확인해야 합니다.

휴대폰의 음성 서비스가 부분 결과를 주는 시점과 문장 사이 재시작 간격에 따라 지연과 누락이 생길 수 있습니다. 1.4초 이내 자막, 끊김 없는 연속 인식, 모든 억양의 정확도를 보장하지 않습니다. 소음·겹친 발화·혼합 언어에서는 오류가 늘어납니다. ML Kit 번역은 일상적이고 단순한 문장에 적합하며 비영어 언어끼리 번역하면 영어를 거칠 수 있습니다.

## English quick start

Install the APK on Android 8 or later. Choose **They speak** and **I read**, prepare translation languages on Wi-Fi, then tap **Translate with Google** and allow microphone access. The UI is Korean for Korean captions and English for other caption languages. Android 12+ with a compatible on-device recognizer is needed for the default speech mode. If unavailable, Settings offers an explicitly consented phone recognition service that may send audio to its provider. Translation remains on-device after packs are prepared. Leaving the app stops listening; returning does not restart it. This release does not automatically detect the spoken language.

## Build and tests

Use JDK 17, Android SDK 36, Build Tools 35.0.0 and the Gradle 8.13 wrapper. Configure `ANDROID_HOME` or `local.properties` locally.

```text
gradlew.bat testDebugUnitTest lintDebug assembleDebug
gradlew.bat connectedDebugAndroidTest
```

The device test downloads the actual ML Kit EN/KO pack and translates six developer-authored examples. It does not record microphone audio or measure speech recognition quality. Its test-only output contains only those authored phrases. Unit tests simulate speech service callbacks to check lifecycle and queue behavior.

For release builds set `UVKR_ANDROID_KEYSTORE` and `UVKR_ANDROID_STORE_PASSWORD` in the local environment; key alias is `universal-voice`. Keep the signing key private and preserve it for future upgrades. Do not commit it. Then run `gradlew.bat assembleRelease`. A release must be signed and verified before distribution. The APK includes ARM and x86 native libraries; language models download separately.

References: [Android speech recognition](https://developer.android.com/reference/android/speech/SpeechRecognizer), [ML Kit translation](https://developers.google.com/ml-kit/language/translation), [Android guide](https://developers.google.com/ml-kit/language/translation/android), [translation attribution](https://developers.google.com/ml-kit/language/translation/translation-terms), [ML Kit terms](https://developers.google.com/ml-kit/terms).
