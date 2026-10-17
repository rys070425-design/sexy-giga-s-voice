# Android components

Universal Voice is an independent application and is not an official Google application.

- Android speech recognition is a platform service. The installed provider determines supported languages, device processing and any network processing. [Android API documentation](https://developer.android.com/reference/android/speech/SpeechRecognizer).
- Google ML Kit Translation 17.0.3 and its Google Play services dependencies are distributed under their applicable Google terms. Downloaded translation models remain subject to these terms; no model ownership or Google affiliation is claimed. [ML Kit terms](https://developers.google.com/ml-kit/terms), [translation guidelines](https://developers.google.com/ml-kit/language/translation/translation-terms). Official Google Translate attribution PNGs are included unchanged and shown beside translated text. The required translation disclaimer is in `app/src/main/assets/translation-notice.txt` and the app's Processing & privacy dialog.
- AndroidX AppCompat, Lifecycle, Core and related AndroidX runtime libraries: The Android Open Source Project, Apache License 2.0. [AndroidX project](https://android.googlesource.com/platform/frameworks/support/).
- Material Components for Android: Google / The Android Open Source Project, Apache License 2.0. [Project](https://github.com/material-components/material-components-android).
- Desugar JDK libraries: Google / The Android Open Source Project and upstream contributors, with the licenses provided by the package, including GPLv2 with Classpath Exception for OpenJDK-derived sources. [Project and licensing](https://github.com/google/desugar_jdk_libs).
- JUnit, Robolectric and AndroidX Test are used for development tests only and are not included in the release APK.

The Apache 2.0 license is packaged as `assets/Apache-2.0.txt`. Embedded notices from dependencies are preserved by the Android build. The Gradle wrapper is build tooling, Apache 2.0, and is not part of the installed app. Mobile does not bundle the Windows application's Whisper, NLLB or CAM++ models.
