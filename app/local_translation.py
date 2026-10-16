"""Short-utterance inference using installed Argos models and tokenizers.

The speech segmenter already provides bounded utterances. Loading Stanza/
PyTorch sentence-splitting pipelines for each language is unnecessary here and
can crash inside the PySide import hook on Windows. No network or downloads.
"""
from collections import deque, OrderedDict
import re

# Exact short game calls only. Never substitute fragments or fuzzy-match a
# different sentence. User-saved phrase corrections take precedence in engine.
GAME_PHRASES = {
    'they are pushing our base': '그들이 우리 기지로 밀고 들어오고 있어.',
    "they're pushing our base": '그들이 우리 기지로 밀고 들어오고 있어.',
    'watch the right side': '오른쪽을 잘 봐.',
    'watch the left side': '왼쪽을 잘 봐.',
    'wait a second, i am healing': '잠깐만, 회복 중이야.',
    "wait a second, i'm healing": '잠깐만, 회복 중이야.',
    'i am healing': '회복 중이야.',
    "i'm healing": '회복 중이야.',
    'i need healing': '회복이 필요해.',
    'i need heals': '힐이 필요해.',
    'i am reloading': '재장전 중이야.',
    "i'm reloading": '재장전 중이야.',
    'cover me': '엄호해 줘.',
    'behind you': '네 뒤에 있어.',
    'on your left': '네 왼쪽이야.',
    'on your right': '네 오른쪽이야.',
    'fall back': '뒤로 물러나.',
    'hold this position': '이 위치를 지켜.',
    'we need to defend the entrance together': '같이 입구를 지켜야 해.',
    'wait a second': '잠깐만.',
    'one second': '잠깐만.',
    'good game': '좋은 경기였어.',
    'well played': '잘했어.',
    'nice shot': '잘 맞혔어.',
}


def game_phrase_translation(text, language):
    if language != 'en':
        return None
    key = re.sub(r'[.!?。！？]+$', '', ' '.join(text.casefold().split())).strip()
    return GAME_PHRASES.get(key)


def translation_route(source, target, pairs):
    queue = deque([(source, [])])
    seen = {source}
    while queue:
        language, path = queue.popleft()
        if language == target:
            return path
        for edge in sorted(pairs, key=lambda p: (p[1] != target, p)):
            if edge[0] == language and edge[1] not in seen:
                seen.add(edge[1])
                queue.append((edge[1], path + [edge]))
    raise ValueError(f'{source} → {target} 번역 모델을 [번역 언어]에서 설치하세요.')


class LocalTranslator:
    def __init__(self):
        from argostranslate.package import get_installed_packages
        self.packages = {(p.from_code, p.to_code): p for p in get_installed_packages()
                         if p.from_code and p.to_code and getattr(p, 'type', 'translate') == 'translate'}
        self.models = OrderedDict()
        from quality_translation import QualityTranslator
        self.quality=QualityTranslator()

    def supports(self,source,target):
        if self.quality.supports(source,target):return True
        try:translation_route(source,target,set(self.packages));return True
        except ValueError:return False

    @property
    def model_label(self):
        return 'NLLB-200 600M · CPU int8 · 비상업용 모델' if self.quality.languages else 'Argos · 로컬'

    def translate(self, text, source, target='ko'):
        if source==target:return text
        if self.quality.supports(source,target):
            return self.quality.translate(text,source,target)
        import ctranslate2
        for edge in translation_route(source, target, set(self.packages)):
            package = self.packages[edge]
            if edge not in self.models:
                # Leave GPU memory to Whisper and the user's game.
                self.models[edge] = ctranslate2.Translator(str(package.package_path / 'model'),
                                      device='cpu', compute_type='int8',
                                      inter_threads=1, intra_threads=2)
                while len(self.models) > 3:
                    self.models.popitem(last=False)
            self.models.move_to_end(edge)
            tokens = package.tokenizer.encode(text)
            if not tokens:
                return ''
            prefix = [[package.target_prefix]] if package.target_prefix else None
            result = self.models[edge].translate_batch([tokens], target_prefix=prefix,
                           replace_unknowns=True, beam_size=4, num_hypotheses=1,
                           length_penalty=1.0 if edge==('en','ko') else 0.2,
                           max_decoding_length=256)[0]
            text = package.tokenizer.decode(result.hypotheses[0])
            if package.target_prefix and text.startswith(package.target_prefix):
                text = text[len(package.target_prefix):]
            text = text.strip()
        return text
