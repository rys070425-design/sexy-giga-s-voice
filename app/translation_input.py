"""Meaning-preserving English contraction expansion for local translation.

No guessed subjects, dictionary answers, or ambiguous 's / 'd expansion.
The original recognition text remains untouched for captions and history.
"""
import re

_FORMS={"i'm":"I am"}
for _pronoun in ('you','we','they'):_FORMS[_pronoun+"'re"]=_pronoun+' are'
for _pronoun in ('i','you','we','they'):_FORMS[_pronoun+"'ve"]=('I' if _pronoun=='i' else _pronoun)+' have'
for _pronoun in ('i','you','he','she','it','we','they','that','there'):
    _FORMS[_pronoun+"'ll"]=('I' if _pronoun=='i' else _pronoun)+' will'
# Keep modal perfect forms (could've, would've...) intact. In comparative
# checks, expansion sometimes changed a past counterfactual into permission.
_PATTERN=re.compile(r"(?<![\w@])(?:"+'|'.join(re.escape(key) for key in _FORMS)+r")(?![\w@])",re.I)
_PROTECTED=re.compile(r'https?://\S+|\S+@\S+')

def prepare_translation_text(text,source):
    if source!='en':return text
    def replace(match):
        token=match.group(0);value=_FORMS[token.casefold()]
        if token.isupper():return value.upper()
        if token[0].isupper():return value[0].upper()+value[1:]
        return value
    # Protect URLs and addresses; normalize typographic apostrophes in prose.
    out=[];start=0
    for match in _PROTECTED.finditer(text):
        out.extend((_PATTERN.sub(replace,text[start:match.start()].replace('’',"'")),match.group(0)));start=match.end()
    out.append(_PATTERN.sub(replace,text[start:].replace('’',"'")))
    return ''.join(out)
