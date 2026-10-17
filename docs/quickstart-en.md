# Universal Voice KR 0.9.3

Translate audio playing on your Windows PC, including Discord and YouTube. Your microphone is not captured. The default models run locally without a paid API. NLLB translation is licensed **CC-BY-NC-4.0 for noncommercial use**.

## Install and choose your language

1. Download [Windows setup](https://raw.githubusercontent.com/rys070425-design/sexy-giga-s-voice/main/dist/UniversalVoiceKR_Setup_v093.exe). Close the old app and installer first.
2. Setup starts in English. Use **Language** to choose from the language-pack catalog. Instructions change immediately. Brazilian Portuguese shares the Portuguese model and interface.
3. Use the same installation folder to reuse existing models. Initial setup needs internet and several GB of free space. This EXE is an online installer.
4. The selected language is applied to the interface and captions in all saved profiles. Other profile settings and your glossary are preserved.

## Start captions

Choose the output device playing your audio under **Playback audio**, then press **Start**. No Discord bot invitation is required for audio captions.

**Hide speech in my caption language** is enabled by default. With Korean captions, Korean speech is hidden; with English captions, English speech is hidden. The app skips native-language text decoding and translation, and adds no native-language text to the conversation view. Audio language detection still runs, and models remain prepared for fast foreign-language captions. Very short phrases, unusual accents, and mixed or overlapping speech may be misidentified.

For English videos with English transcripts, turn off **Hide speech in my caption language**. You can then fix **Speech language** to English. While hiding is enabled, automatic detection is required. Change **Language** in the upper right to switch the interface and current profile's caption language. **Caption language** can also be set separately for a profile. Changes during a running session restart the engine safely.

## Read comfortably

- Draft translations are paced to reduce flicker. A previous sentence stays briefly visible; long captions use a two-line reading window.
- Under **Profiles & captions**, adjust background opacity from 15–80% (default 42%). Turn on original text if useful.
- For everyday conversations, use general conversation context. Game context has shorter commit timing and a small game-call glossary.
- **Save captions** exports the text still retained in the conversation view. No automatic audio recording or conversation saving is performed.

## Speaker and site names

For Discord names, approve the official Streamkit connection once under **Discord connection**. Current-channel following depends on the official query being available; saved/manual links are the fallback. This is separate from audio captions. Confirmed Discord speakers appear as **Name: captions**. Brief indicator overlap is smoothed only with the same exclusive speaker on both sides. Sustained overlap shows **Alice / Bob: captions**, without the overlap status phrase. This names the active participants; it does not separate their mixed voices into independent transcripts. See [speaker changes and limits](validation-v092.md).

A playback application name is shown only when one source is consistently identified. Silent, muted, and own capture sessions are excluded. Mixed or unknown sources have no source header; technical process names are not listed. Exact Chrome/Edge website names require the optional extension opened through **Website names**. Load the provided unpacked extension, then copy the pairing code into its settings. It reports audible, unmuted, non-incognito tab hostnames to this PC, not page text or full URLs. You can also type a source label directly.

## Models and limits

In 0.9.3, general conversation retains up to 10 seconds of context for final recognition while preserving the first-draft cadence. Game context keeps its 8-second limit. Some unambiguous English contractions are expanded only for translation; original transcripts remain intact. The models were not retrained, and meaning errors remain.

**Use voices to help confirm Discord nicknames** under **Profiles & captions** enables the local CAM++ CPU model (about 28 MB, Apache-2.0). It learns session-only nicknames from clean solo-speaking indicator intervals. At least two people need independent enrollment intervals. It fills an unknown name only when the whole span and both halves agree with a clear margin. It never waits for speaker inference before displaying captions. Channel changes and stopping clear the session data. It cannot find a new person's real name or separate overlapping voices. See [tests and remaining limitations](validation-v093.md).

Speech recognition uses **Whisper large-v3-turbo / faster-whisper**. Translation uses **NLLB-200 distilled 600M, CPU int8**. These models were not retrained. Both can still be wrong.

Prefer NVIDIA GPU when available. Earlier CPU tests did not meet the 1.4-second target. Automatic detection adds work, and no universal latency is promised. See [0.9.0 measurements](validation-v090.md) and [model comparisons](model-choice.md).

Korean source text and English core screens were reviewed. Other interface translations and some supporting messages are machine-assisted with English fallback; native-speaker review is still needed. Captions, nicknames, websites, and editable user values are never passed through UI translation.

Optional ChatGPT correction has separate login and account terms and is not required for default captions. See [third-party notices](third-party.md).
