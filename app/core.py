"""Dependency-free settings, glossary, and subtitle utilities."""
from __future__ import annotations
import copy
import json
import os
import re
import time
from pathlib import Path

APP_NAME = "UniversalVoiceKR"
HOME = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / APP_NAME

DEFAULT_PROFILES = [
    {"name": "디스코드 · 게임", "model": "large-v3-turbo", "device": "auto", "language": "auto",
     "vad": 1, "beam_size": 5, "translation_context": "game", "font": 26, "position": "bottom", "show_original": False,
     "overlay": True, "audio_id": "", "glossary_group": "global", "game_exes": []},
    {"name": "디스코드 · 대화", "model": "large-v3-turbo", "device": "auto", "language": "auto",
     "vad": 1, "beam_size": 5, "translation_context": "game", "font": 27, "position": "bottom", "show_original": True,
     "overlay": True, "audio_id": "", "glossary_group": "global", "game_exes": []},
    {"name": "영상 · 일반", "model": "large-v3-turbo", "device": "auto", "language": "auto",
     "vad": 1, "beam_size": 5, "translation_context": "general", "font": 25, "position": "bottom", "show_original": True,
     "overlay": True, "audio_id": "", "glossary_group": "global", "game_exes": []},
]
DEFAULT_TERMS = {
    "global": {
        "rn": "right now", "idk": "I don't know", "ngl": "honestly", "fr": "for real",
        "afk": "away from keyboard", "brb": "be right back", "omw": "on my way",
        "gg": "good game", "wp": "well played", "lfg": "looking for group",
        "imo": "in my opinion", "tbh": "to be honest"
    },
    "games": {"ARK": {"stego": "stegosaurus", "soaking": "draining turret ammunition",
                       "dedi": "dedicated storage", "cryo": "cryopod", "tame": "tamed creature"},
              "FPS": {"ult": "ultimate ability", "flank": "attack from the side",
                      "heals": "healing"}}
}
DEFAULT_SETTINGS = {
    "profiles": DEFAULT_PROFILES,
    "active_profile": 0,
    "auto_switch": False,
    "glossary_group": "global",
    "update": {"schedule": "weekly", "url": "", "last_checked": 0},
}


def select_output_loopback(devices, requested_id: str = "", default_speaker=None):
    """Only capture audio *played by an output device*, never microphone input.

    This is enforced in the engine, not only the dropdown, to protect against
    persisted settings from older versions or deliberately modified config.
    """
    loopbacks = [dev for dev in devices if bool(getattr(dev, "isloopback", False))]
    if requested_id:
        for dev in loopbacks:
            if str(dev.id) == str(requested_id):
                return dev
        raise ValueError(
            "선택한 소리 장치가 출력 루프백이 아닙니다. "
            "마이크 입력은 번역에 사용할 수 없어요. 소리 입력을 다시 선택하세요."
        )
    if default_speaker is None:
        raise ValueError("기본 출력 장치를 찾지 못했습니다. 출력 루프백 장치를 선택하세요.")
    for dev in loopbacks:
        if str(dev.id) == str(default_speaker.id):
            return dev
    raise ValueError(
        "기본 스피커의 루프백을 찾지 못했습니다. "
        "장치 새로고침 후 출력 루프백을 선택하세요. 마이크로 대체하지 않습니다."
    )


def read_json(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, type(default)) else copy.deepcopy(default)
    except (FileNotFoundError, ValueError, OSError):
        return copy.deepcopy(default)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def init_files(base: Path = HOME):
    base.mkdir(parents=True, exist_ok=True)
    cfg_path, terms_path = base / "settings.json", base / "glossary.json"
    cfg = read_json(cfg_path, DEFAULT_SETTINGS)
    terms = read_json(terms_path, DEFAULT_TERMS)
    if not cfg_path.exists():
        write_json(cfg_path, cfg)
    if not terms_path.exists():
        write_json(terms_path, terms)
    return cfg, terms


def expand_terms(text: str, entries: dict[str, str]) -> str:
    """Replace standalone tokens, not word fragments; longer keys first."""
    safe = [(str(k), str(v)) for k, v in entries.items() if k.strip() and v.strip() and len(k) <= 80]
    safe.sort(key=lambda item: len(item[0]), reverse=True)
    if not safe:
        return text
    patt = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(k) for k, _ in safe) + r")(?![\w])", re.I)
    mapping = {k.casefold(): v for k, v in safe}
    return patt.sub(lambda m: mapping[m.group(0).casefold()], text)


def merge_glossary(terms: dict, group: str) -> dict:
    all_terms = dict(terms.get("global", {}))
    if group != "global":
        all_terms.update(terms.get("games", {}).get(group, {}))
    return all_terms


def update_due(update: dict, now: float | None = None) -> bool:
    if not update.get("url"):
        return False
    intervals = {"daily": 86400, "weekly": 7 * 86400, "monthly": 30 * 86400}
    period = intervals.get(update.get("schedule"))
    if not period:
        return False
    return (time.time() if now is None else now) - float(update.get("last_checked", 0)) >= period


def valid_remote_dictionary(value) -> bool:
    """User-reviewed remote file schema; keep updates limited to terms, not code."""
    if not isinstance(value, dict) or not isinstance(value.get("global"), dict) or not isinstance(value.get("games"), dict):
        return False
    groups = [value["global"]] + list(value["games"].values())
    if len(groups) > 60:
        return False
    return all(isinstance(x, dict) and len(x) <= 2000 and
               all(isinstance(k, str) and isinstance(v, str) and len(k) <= 80 and len(v) <= 240
                   for k, v in x.items()) for x in groups)


def normalized_phrase(original: str) -> str:
    """Normalize whitespace/case only; never fuzzy-match and introduce false meanings."""
    return " ".join(original.split()).casefold().strip()


def read_phrase_memory(path: Path) -> dict[str, str]:
    return read_json(path, {})


def remember_phrase(path: Path, original: str, translated: str, language: str = "auto") -> None:
    language = language.strip().lower() or "auto"
    if not language.isascii() or not language.replace("-", "").isalpha() or len(language) > 12:
        raise ValueError("언어 코드가 올바르지 않습니다.")
    original_key = normalized_phrase(original)
    key = language + ":" + original_key
    if not original_key or not translated.strip() or len(key) > 1500 or len(translated) > 1500:
        raise ValueError("문장 길이가 너무 길거나 내용이 비어 있습니다.")
    entries = read_phrase_memory(path)
    if len(entries) >= 5000 and key not in entries:
        raise ValueError("저장된 문장이 5,000개를 초과했습니다.")
    entries[key] = translated.strip()
    write_json(path, entries)
