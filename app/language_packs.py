"""Data-only language install packs and Argos offline translation routes.

No third-party import until installing/querying actual translation models.
A .uvkrpack is intentionally a tiny *installer manifest*, NOT the model itself.
A model must be downloaded once on an Internet-connected Windows PC.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

PACK_FORMAT = "universal-voice-kr-language-pack"
PACK_FORMAT_VERSION = 1
# Example ARK community languages, not exhaustive player country statistics.
# Country names are examples: one language pack works across countries.
LANGUAGES = {
    "ko": ("한국어", "대한민국 · 한국어 사용권"),
    "en": ("영어", "미국 · 영국 · 캐나다 · 호주 등"),
    "es": ("스페인어", "스페인 · 멕시코 · 남미 여러 나라"),
    "pt": ("포르투갈어", "포르투갈 · 포르투갈어 사용권"),
    "pb": ("브라질 포르투갈어", "브라질"),
    "ru": ("러시아어", "러시아 · 러시아어 사용 커뮤니티"),
    "pl": ("폴란드어", "폴란드"),
    "tr": ("터키어", "튀르키예"),
    "de": ("독일어", "독일 · 오스트리아 · 스위스 일부"),
    "fr": ("프랑스어", "프랑스 · 캐나다 일부 · 벨기에 일부"),
    "zh": ("중국어(표준 중국어)", "중국 · 대만 등 (방언·문자 차이 있음)"),
    "ja": ("일본어", "일본"),
    "it": ("이탈리아어", "이탈리아"),
    "ar": ("아랍어", "중동 · 북아프리카 여러 나라"),
    "uk": ("우크라이나어", "우크라이나"),
    "nl": ("네덜란드어", "네덜란드 · 벨기에 일부"),
    "id": ("인도네시아어", "인도네시아"),
    "hi": ("힌디어", "인도 일부"),
    "cs": ("체코어", "체코"),
    "sv": ("스웨덴어", "스웨덴"),
    "vi": ("베트남어", "베트남"),
    "th": ("태국어", "태국"),
    "tl": ("필리핀어(타갈로그)", "필리핀"),
    "ro": ("루마니아어", "루마니아"),
    "fa": ("페르시아어", "이란 등"),
}
# Minimal examples for post-STT text normalization, not claims of fluency.
# Each file can be freely edited after installation.
TERMS = {
    "en": {"rn": "right now", "omw": "on my way", "brb": "be right back",
           "idk": "I don't know", "ngl": "honestly", "lfg": "looking for group", "gg": "good game"},
    "es": {"q": "que", "xq": "porque", "tmb": "también", "jajaja": "risa"},
    "pt": {"vc": "você", "pq": "porque", "blz": "beleza", "tbm": "também"},
    "pb": {"vc": "você", "pq": "porque", "blz": "beleza", "tbm": "também"},
    "ru": {"спс": "спасибо", "пж": "пожалуйста"},
    "pl": {"nwm": "nie wiem", "pzdr": "pozdrawiam"},
    "tr": {"slm": "selam", "tmm": "tamam"},
    "de": {"kA": "keine Ahnung", "vllt": "vielleicht"},
    "fr": {"jsp": "je ne sais pas", "stp": "s'il te plaît"},
    "zh": {"666": "很厉害"},
    "ja": {"草": "笑い"},
    "it": {"cmq": "comunque"},
    "ar": {}, "uk": {}, "nl": {"ff": "even"}, "id": {"gk": "tidak", "yg": "yang"},
    "hi": {}, "cs": {}, "sv": {}, "vi": {}, "th": {}, "tl": {}, "ro": {}, "fa": {},
}


def create_manifest(code: str, target: str = 'ko') -> dict:
    if code not in LANGUAGES or target not in LANGUAGES or target=='pb':
        raise ValueError(f"미지원 코드: {code}")
    name, countries = LANGUAGES[code]
    return {"format": PACK_FORMAT, "schema": PACK_FORMAT_VERSION, "code": code,
            "language": name, "countries": countries, "version": "1.0.0",
            "translation_target": target, "terms": TERMS.get(code, {}),
            "note": "다운로드용 설치 설명팩. 번역 AI 모델 데이터는 포함되지 않으며, 첫 설치 시 인터넷 연결이 필요합니다."}


def validate_manifest(obj) -> dict:
    if not isinstance(obj, dict) or obj.get("format") != PACK_FORMAT or obj.get("schema") != PACK_FORMAT_VERSION:
        raise ValueError("지원하지 않는 언어팩 형식입니다")
    code = obj.get("code")
    if code not in LANGUAGES or obj.get("translation_target") not in LANGUAGES or obj.get('translation_target')=='pb':
        raise ValueError("지원하지 않는 언어/번역 방향입니다")
    terms = obj.get("terms")
    if not isinstance(terms, dict) or len(terms) > 300:
        raise ValueError("단어 사전 형식이 잘못되었습니다")
    if not all(isinstance(k, str) and isinstance(v, str) and 0 < len(k) <= 80 and 0 < len(v) <= 240
               for k, v in terms.items()):
        raise ValueError("단어 사전 항목이 잘못되었습니다")
    if not isinstance(obj.get("language"), str) or len(obj["language"]) > 80:
        raise ValueError("언어 이름이 잘못되었습니다")
    return obj


def read_pack(path: Path) -> dict:
    if path.stat().st_size > 128_000:
        raise ValueError("언어팩 설명 파일은 128KB 이하여야 합니다")
    if not zipfile.is_zipfile(path):
        raise ValueError("올바른 .uvkrpack 파일이 아닙니다")
    with zipfile.ZipFile(path) as z:
        if z.namelist() != ["manifest.json"]:
            raise ValueError("manifest.json 하나만 들어 있는 언어팩을 선택해 주세요")
        if z.getinfo("manifest.json").file_size > 64_000:
            raise ValueError("언어팩 내용이 너무 큽니다")
        data = z.read("manifest.json")
        if len(data) > 64_000:
            raise ValueError("언어팩 내용이 너무 큽니다")
    return validate_manifest(json.loads(data.decode("utf-8")))


def write_pack(path: Path, code: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(create_manifest(code), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", data)


def combine_terms(base_terms: dict[str, str], language: str, app_home: Path) -> dict[str, str]:
    """Language-specific abbreviations, never overwritten user edits in base_terms."""
    out = dict(base_terms)
    path = app_home / "installed_pack_terms" / f"{language}.json"
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(items, dict):
            for k, v in items.items():
                if isinstance(k, str) and isinstance(v, str) and k not in out:
                    out[k] = v
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return out


def save_terms_without_overwrite(manifest: dict, app_home: Path):
    """Persistent editable language terms; updating a pack never clobbers user edits."""
    code = validate_manifest(manifest)["code"]
    target = app_home / "installed_pack_terms" / f"{code}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            existing = {}
    except (OSError, json.JSONDecodeError):
        existing = {}
    combined = dict(manifest["terms"])
    combined.update(existing)
    target.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def find_route(src: str, installed_pairs: set[tuple[str, str]], available_pairs: set[tuple[str, str]], target='ko'):
    """Shortest viable route <= 2 edges, prefers installed models over new installs.

    Same-language captions use no model. Only English pivot is considered.
    Returns list of missing pairs, or None when the upstream index cannot serve it.
    """
    if src == target or (src=='pb' and target=='pt'):
        return []
    # Brazilian Portuguese shares the standard Portuguese translation model.
    # Retain pb only for the Brazilian glossary and UI selection.
    if src == "pb":
        src = "pt"
    # Prefer already-installed route even if the catalog offers a direct model.
    routes = [[(src, target)]]
    if src != "en" and target!='en':
        routes.append([(src, "en"), ("en", target)])
    routes = [r for r in routes if all(edge in (installed_pairs | available_pairs) for edge in r)]
    if not routes:
        return None
    best = min(routes, key=lambda r: (sum(edge not in installed_pairs for edge in r), len(r)))
    return [edge for edge in best if edge not in installed_pairs]


def get_installed_pairs() -> set[tuple[str, str]]:
    from argostranslate import package
    return {(p.from_code, p.to_code) for p in package.get_installed_packages()
            if p.from_code and p.to_code and getattr(p, "type", "translate") == "translate"}


def installed_for_language(code: str, target='ko') -> bool:
    if code == target or (code=='pb' and target=='pt'):
        return True
    from quality_translation import supported_languages
    supported=supported_languages()
    if ('pt' if code=='pb' else code) in supported and target in supported:return True
    route = find_route(code, get_installed_pairs(), set(),target)
    return route == []


def install_translation_models(code: str, log=lambda msg: None, target='ko') -> list[tuple[str, str]]:
    """Downloads official Argos models (once) and installs exact needed pair(s).

    Raises clear error when package index or route is unavailable; does not simulate success.
    """
    if code not in LANGUAGES or target not in LANGUAGES or target=='pb':
        raise ValueError("선택한 언어를 지원하지 않습니다")
    if code == target or (code=='pb' and target=='pt'):
        log("원문 자막에는 추가 번역 모델이 필요하지 않습니다.")
        return []
    from quality_translation import supported_languages
    supported=supported_languages()
    if ('pt' if code=='pb' else code) in supported and target in supported:
        log(f'{code} → {target}: 공용 NLLB 번역 모델이 이미 준비되어 있습니다.')
        return []
    from argostranslate import package
    log("공식 번역 모델 목록 확인 중 · 인터넷 연결 필요")
    package.update_package_index()
    available = {(p.from_code, p.to_code): p for p in package.get_available_packages()
                 if p.from_code and p.to_code and getattr(p, "type", "translate") == "translate"}
    installed = get_installed_pairs()
    missing = find_route(code, installed, set(available),target)
    if missing is None:
        raise RuntimeError(f"현재 공식 Argos 목록에 {code} → {target} 번역 경로가 없습니다. 모델이 추가될 때 다시 확인해 주세요.")
    for edge in missing:
        model = available[edge]
        log(f"모델 다운로드·설치: {edge[0]} → {edge[1]} (파일 크기와 시간은 모델에 따라 다릅니다)")
        package.install_from_path(model.download())
    if not installed_for_language(code,target):
        raise RuntimeError("모델 설치 후 번역 경로를 확인할 수 없습니다. 설치 기록을 확인해 주세요.")
    return missing
