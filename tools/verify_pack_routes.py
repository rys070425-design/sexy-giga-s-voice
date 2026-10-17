import sys,json,time
from pathlib import Path
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root))
from runtime_config import configure
configure()
from local_translation import LocalTranslator
from language_preferences import language_choices,normalize_language
translator=LocalTranslator();rows=[]
for name,choice in language_choices():
    target=normalize_language(choice);source='ko' if target=='en' else 'en'
    text='다음 역에서 내릴게요.' if target=='en' else 'I will get off at the next station.'
    assert translator.supports(source,target),(source,target)
    start=time.monotonic();result=translator.translate(text,source,target)
    assert result.strip(),choice
    rows.append({'choice':choice,'source':source,'target':target,'nonempty':True,'characters':len(result),'seconds':round(time.monotonic()-start,3)})
report=Path(sys.argv[2]);report.write_text(json.dumps({'result':'ALL_25_PACK_CHOICES_TRANSLATION_SMOKE_VERIFIED','cases':rows},indent=2),encoding='utf-8')
print('ALL_25_PACK_CHOICES_TRANSLATION_SMOKE_VERIFIED',flush=True)
