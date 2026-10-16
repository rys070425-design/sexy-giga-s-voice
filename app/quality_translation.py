"""NLLB inference without importing Torch or Transformers into the UI."""
import json
from pathlib import Path
import re
from functools import lru_cache

MODEL_DIR=Path(__file__).resolve().parent/'models'/'nllb600m-int8'
LANGUAGE_CODES={'en':'eng_Latn','ko':'kor_Hang','es':'spa_Latn','pt':'por_Latn',
    'ru':'rus_Cyrl','pl':'pol_Latn','tr':'tur_Latn','de':'deu_Latn','fr':'fra_Latn',
    'zh':'zho_Hans','ja':'jpn_Jpan','it':'ita_Latn','ar':'arb_Arab','uk':'ukr_Cyrl',
    'nl':'nld_Latn','id':'ind_Latn','hi':'hin_Deva','cs':'ces_Latn','sv':'swe_Latn',
    'vi':'vie_Latn','th':'tha_Thai','tl':'tgl_Latn','ro':'ron_Latn','fa':'pes_Arab'}


def supported_languages(directory=MODEL_DIR):
    directory=Path(directory)
    if not all((directory/name).is_file() for name in
               ('model.bin','config.json','shared_vocabulary.json','sentencepiece.bpe.model')):
        return set()
    try:
        path=directory/'shared_vocabulary.json'
        stat=path.stat()
        return _read_languages(str(path),stat.st_mtime_ns,stat.st_size)
    except (OSError,ValueError,TypeError):return set()


@lru_cache(maxsize=4)
def _read_languages(path,modified,size):
    vocabulary=json.loads(Path(path).read_text(encoding='utf-8'))
    return frozenset(code for code,token in LANGUAGE_CODES.items() if token in vocabulary)


class QualityTranslator:
    def __init__(self,directory=MODEL_DIR):
        self.directory=Path(directory)
        self.languages=supported_languages(directory)
        self.model=self.tokenizer=None

    def supports(self,source,target):
        return source in self.languages and target in self.languages

    def translate(self,text,source,target):
        if not self.supports(source,target):
            raise ValueError(f'NLLB does not support {source} → {target}')
        if self.model is None:
            import ctranslate2
            import sentencepiece
            self.model=ctranslate2.Translator(str(self.directory),device='cpu',compute_type='int8',
                                            inter_threads=1,intra_threads=4)
            self.tokenizer=sentencepiece.SentencePieceProcessor(model_file=str(self.directory/'sentencepiece.bpe.model'))
        if not text.strip():return ''
        tokens=[LANGUAGE_CODES[source],*self.tokenizer.encode(text,out_type=str),'</s>']
        result=self.model.translate_batch([tokens],target_prefix=[[LANGUAGE_CODES[target]]],
                                          beam_size=4,max_decoding_length=192)[0]
        pieces=[token for token in result.hypotheses[0]
                if token not in ('<s>','</s>','<pad>') and not re.fullmatch(r'[a-z]{3}_[A-Z][a-z]{3}',token)]
        return self.tokenizer.decode(pieces).strip()
