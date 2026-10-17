"""Extract canonical UI text for the offline catalog builder (stdlib only)."""
import ast,re,json,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
output=Path(sys.argv[1]).resolve();output.mkdir(parents=True,exist_ok=True)
texts=set();templates=set()
for name in ('main','discord_widget','gpu_tab','engine','speaker_labels','language_packs','cuda_runtime','core','model_assets','chatgpt_plan'):
    tree=ast.parse((repo/'app'/f'{name}.py').read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node,ast.Constant) and isinstance(node.value,str):
            if re.search('[가-힣]',node.value) and len(node.value)<1800:texts.add(node.value)
        if isinstance(node,ast.JoinedStr):
            parts=[];index=0
            for part in node.values:
                if isinstance(part,ast.Constant):parts.append(part.value)
                else:parts.append('{'+str(index)+'}');index+=1
            value=''.join(parts)
            if re.search('[가-힣]',value) and not value.startswith('다음은 온라인 게임 음성채팅'):texts.add(value);templates.add(value)
for match in re.finditer(r'"([^"\\]*(?:\\.[^"\\]*)*)"',(repo/'installer/Setup.cs').read_text(encoding='utf-8')):
    try:value=json.loads('"'+match.group(1)+'"')
    except ValueError:continue
    if re.search('[가-힣]',value):texts.add(value)
(output/'ui_source_strings.json').write_text(json.dumps(sorted(texts),ensure_ascii=False,indent=2),encoding='utf-8')
(output/'ui_source_templates.json').write_text(json.dumps(sorted(templates,key=len,reverse=True),ensure_ascii=False,indent=2),encoding='utf-8')
print(len(texts),len(templates))
