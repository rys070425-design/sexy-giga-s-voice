"""One-time local model download for Universal Voice KR setup.

Models remain local after download. Translator uses only packages in official
Argos package index and reports unsupported routes instead of claiming success.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def warm_whisper(model_name: str = 'base') -> bool:
    print(f'[Whisper] Download/check: {model_name}', flush=True)
    try:
        from faster_whisper import WhisperModel
        WhisperModel(model_name, device='cpu', compute_type='int8')
        print('[Whisper] Ready for offline use.', flush=True)
        return True
    except Exception as e:
        print(f'[Whisper] Could not pre-download: {e}', flush=True)
        print('[Whisper] The program can try downloading this later.', flush=True)
        return False


def install_argos_languages(codes: list[str]) -> tuple[list[str], list[str]]:
    from argostranslate import package
    from language_packs import find_route, get_installed_pairs, LANGUAGES

    print('[Argos] Checking official translation catalog...', flush=True)
    try:
        package.update_package_index()
        available = {(p.from_code, p.to_code): p for p in package.get_available_packages()
                     if p.from_code and p.to_code and getattr(p, 'type', 'translate') == 'translate'}
    except Exception as e:
        print(f'[Argos] Catalog unavailable: {e}', flush=True)
        return [], list(codes)

    installed = get_installed_pairs()
    ok: list[str] = []
    failures: list[str] = []
    for code in codes:
        if code not in LANGUAGES:
            failures.append(code)
            continue
        path = find_route(code, installed, set(available))
        if path is None:
            print(f'[Argos] {code}: no official model route to Korean.', flush=True)
            failures.append(code)
            continue
        try:
            for edge in path:
                if edge in installed:
                    continue
                print(f'[Argos] Download: {edge[0]} -> {edge[1]}', flush=True)
                model = available[edge]
                package.install_from_path(model.download())
                installed.add(edge)
            if find_route(code, installed, set()) == []:
                ok.append(code)
                print(f'[Argos] {code}: installed.', flush=True)
            else:
                failures.append(code)
        except Exception as e:
            print(f'[Argos] {code}: install failed: {e}', flush=True)
            failures.append(code)
    return ok, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['light', 'standard', 'full'], default='standard')
    args = parser.parse_args()
    languages = {
        'light': ['en'],
        'standard': ['en', 'es', 'ru', 'ja', 'pt', 'fr'],
        'full': ['en', 'es', 'pt', 'pb', 'ru', 'pl', 'tr', 'de', 'fr', 'zh',
                 'ja', 'it', 'ar', 'uk', 'nl', 'id', 'hi', 'cs', 'sv', 'vi',
                 'th', 'tl', 'ro', 'fa']
    }[args.mode]
    whisper_ok = warm_whisper('base')
    ok, failed = install_argos_languages(languages)
    print('\n=== MODEL INSTALL REPORT ===', flush=True)
    print('Whisper:', 'ready' if whisper_ok else 'not pre-cached', flush=True)
    print('Argos available:', ', '.join(ok) or '(none)', flush=True)
    print('Argos unavailable:', ', '.join(failed) or '(none)', flush=True)
    # Fail only when there is no single functioning model, not when some languages
    # lack a model in the official index. User can install them later.
    return 0 if whisper_ok and 'en' in ok else 2


if __name__ == '__main__':
    sys.exit(main())
