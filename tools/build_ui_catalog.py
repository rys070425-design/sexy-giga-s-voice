"""Precompute UI translations locally. No runtime UI translation or network.

English overrides are reviewed source; other locales are machine-assisted and
need native-speaker review. Runtime never loads NLLB to translate its interface.
"""
import argparse,json,sys,re,unicodedata,time
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--model-dir',type=Path,required=True)
parser.add_argument('--sources',type=Path,required=True)
parser.add_argument('--templates',type=Path,required=True)
parser.add_argument('--device',choices=('cpu','cuda'),default='cpu')
args=parser.parse_args()
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo/'app'))
from cuda_runtime import prepare_cuda
prepare_cuda()
import ctranslate2,sentencepiece
from quality_translation import LANGUAGE_CODES
from language_preferences import language_choices,normalize_language
model=ctranslate2.Translator(str(args.model_dir),device=args.device,
    compute_type='int8_float16' if args.device=='cuda' else 'int8',intra_threads=4)
sp=sentencepiece.SentencePieceProcessor(model_file=str(args.model_dir/'sentencepiece.bpe.model'))
overrides=json.loads(Path(__file__).with_name('ui_english_overrides.json').read_text(encoding='utf-8'))
sources=set(json.loads(args.sources.read_text(encoding='utf-8')))|set(overrides)
sources={text for text in sources if text!='한국어' and not text.startswith(('Opt-in, user-click-only','다음은 온라인 게임 음성채팅'))}
output=repo/'app'/'ui_locales.json'
catalog={'schema':1,'languages':[{'code':code,'name':name} for name,code in language_choices()],
         'messages':{},'templates':json.loads(args.templates.read_text(encoding='utf-8')),
         'translation_notes':'Korean source and English core controls reviewed; remaining interface translations are machine-assisted with English fallback. Brazilian Portuguese shares Portuguese translations.'}

def translate_many(texts,source,target):
    tasks=[];positions=[];out=[[] for _ in texts]
    for index,text in enumerate(texts):
        for line in text.split('\n'):
            if not line.strip():out[index].append('');continue
            slot=len(out[index]);out[index].append(None)
            protected=re.sub(r'\{(\d+)\}',lambda match:str(90010000+int(match.group(1))),line.strip())
            tasks.append([LANGUAGE_CODES[source],*sp.encode(protected,out_type=str),'</s>'])
            positions.append((index,slot,line))
    for offset in range(0,len(tasks),24):
        batch=tasks[offset:offset+24]
        results=model.translate_batch(batch,target_prefix=[[LANGUAGE_CODES[target]] for _ in batch],
            beam_size=2,max_decoding_length=384)
        for result,(index,slot,line) in zip(results,positions[offset:offset+24]):
            pieces=[piece for piece in result.hypotheses[0] if piece not in ('<s>','</s>','<pad>') and not re.fullmatch(r'[a-z]{3}_[A-Z][a-z]{3}',piece)]
            translated=sp.decode(pieces).strip()
            translated=''.join(str(unicodedata.digit(char)) if char.isdecimal() else char for char in translated)
            for field in re.findall(r'\{(\d+)\}',line):
                digits=str(90010000+int(field))
                pattern=r'[\s,._،]*'.join(digits)
                translated=re.sub(pattern,'{'+field+'}',translated)
            if set(re.findall(r'\{\d+\}',translated))!=set(re.findall(r'\{\d+\}',line)):
                translated=line.strip()
            leading=line[:len(line)-len(line.lstrip())];trailing=line[len(line.rstrip()):]
            out[index][slot]=leading+translated+trailing
    return ['\n'.join(lines) for lines in out]

keys=sorted(sources)
english=translate_many(keys,'ko','en')
catalog['messages']['en']=dict(zip(keys,english));catalog['messages']['en'].update(overrides)
catalog['messages']['ko']={}
output.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
print('ENGLISH_CATALOG_READY',len(keys),flush=True)
values=[catalog['messages']['en'][key] for key in keys]
started=time.monotonic()
for code in LANGUAGE_CODES:
    if code in ('ko','en'):continue
    translated=translate_many(values,'en',code)
    catalog['messages'][code]=dict(zip(keys,translated))
    output.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'locale':code,'messages':len(keys),'seconds':round(time.monotonic()-started,1)}),flush=True)
print('UI_CATALOGS_READY',flush=True)
locale_overrides=json.loads(Path(__file__).with_name('ui_locale_overrides.json').read_text(encoding='utf-8'))
for code,messages in locale_overrides.items():catalog['messages'][code].update(messages)
output.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
