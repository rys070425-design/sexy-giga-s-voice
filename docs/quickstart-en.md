# Universal Voice KR: listening to English

The app captions sound played by your Windows output device. It can caption Discord calls, videos, or other playback. It does not capture your microphone. Most settings are still written in Korean; the labels below help you find them.

## Start captions

1. Install the latest setup and wait for its first model download to finish. Keep several GB of free disk space. You need internet for setup; the default speech and translation models then run on your PC without a paid API.
2. Open **실시간 자막** (Live captions). Under **Playback audio**, select the output device used by Discord or your browser. If you change headphones, stop captions, refresh the device list, and select the new output.
3. Set **Speech** to English when listening to English. Automatic detection is useful for mixed languages but costs time and can misidentify short phrases.
4. Choose **Captions**: Korean, English, Spanish, French, German, Japanese, Chinese, or Portuguese. English output gives you the recognized English text without translating it.
5. Press **Start**. Initial model preparation happens before listening begins. The first line is a draft and may be corrected as the speaker continues.

## Read and review

| Korean label | What it does |
|---|---|
| 프로필과 자막 | Profile and caption appearance |
| 번역 문맥 → 일반 대화 | General conversation, without the exact game-call phrase replacements |
| 배경 진하기 | Background opacity; default 42%, adjustable from 15% to 80% |
| 원문 | Show the original alongside translated captions |
| 기록 저장 / Save | Export the text still retained in the conversation view |
| 장치 진단 | NVIDIA GPU and runtime diagnostics |

Updates are paced so drafts do not flash on every recognition result. A previous sentence remains briefly visible while a new one arrives. Very long text uses a two-line reading window; the conversation view retains more text. Save is manual and exports retained text only, rather than guaranteeing a complete transcript of a long call. The app does not automatically record audio or save conversations.

For everyday conversation or videos, use the **영상 · 일반** profile or select **일반 대화 · 문장 문맥 유지** under translation context. Version 0.8.2 keeps a little more context across hesitation while still showing drafts before the sentence ends. Final confirmation may arrive later. Newly created **디스코드 · 대화** profiles use this mode; existing saved profiles keep your settings. The game profile includes a small exact-phrase glossary for game calls and retains its shorter commit timing. You can add actual names and specialist vocabulary under **인식할 이름·용어**; do not paste entire unrelated conversations there.

## Show who or what is playing

**Discord names:** open **Discord 연결** and approve the official Discord/Streamkit connection once. Enable **현재 통화방 자동 연결** to follow the current voice channel when the official query is available. A server bot invitation is not required. If the official connection does not permit the channel query, use the manual channel/widget address. You can start audio captions without connecting nicknames. Simultaneous voices are mixed audio; the app cannot reliably separate every speaker.

**Website names:** Windows playback application names are detected automatically. For exact website names in Chrome or Edge, click **웹사이트 이름 연결**, open the provided extension folder, and load it as an unpacked extension from the browser's extension manager with Developer mode enabled. Copy the app's pairing code into the extension popup and save. The code is hidden on screen; use **연결 코드 복사** to copy it. The extension reports audible tab hostnames to the app on this PC, excluding incognito and muted tabs. It does not send page text, full URLs, or browsing history. You can also enter a source label manually in the live-caption screen.

## Performance and limitations

Use automatic GPU selection or NVIDIA GPU when available. With large-v3-turbo, our i7-13700H CPU test took about 7.4–13.7 seconds to show the first draft across seven synthetic-input conditions after warmup. Small CPU took about 2.6–6.9 seconds and made slightly more word errors in the two accent samples. Neither met the 1.4-second goal. Those CPU comparisons used the earlier 0.8.1 segmentation. A fast GPU measurement is not a CPU promise. See [model comparisons](model-choice.md). Game load, noise, overlapping voices, and accents can affect both delay and recognition.

Speech recognition uses **Whisper large-v3-turbo / faster-whisper**. Translation uses **NLLB-200 distilled 600M, CPU int8**. No model was retrained for your voice. Translation can still change meanings, including negation or short ambiguous expressions; compare the original when meaning matters.

The default NLLB translation model is licensed **CC-BY-NC-4.0 for noncommercial use**. Free personal use does not grant unrestricted commercial rights. See [third-party notices](third-party.md) and [validation details](validation-v082.md). The optional ChatGPT correction page has its own login and account terms and is not required for default live captions.
