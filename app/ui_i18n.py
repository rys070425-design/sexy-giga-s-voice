"""Data-only UI catalogs; caption text and user data never pass through this API."""
import json,re,weakref
from pathlib import Path
from language_preferences import valid_language,normalize_language

_language='en'
_catalog=None
_widgets=weakref.WeakSet()
_qt_translator=None

def catalog():
    global _catalog
    if _catalog is None:
        _catalog=json.loads(Path(__file__).with_name('ui_locales.json').read_text(encoding='utf-8'))
    return _catalog

def language():return _language

def register(widget):_widgets.add(widget)

def translate(source,code=None):
    source=str(source)
    active=_language if code is None else valid_language(code)
    if active=='ko' or not source:return source
    entries=catalog()['messages']
    selected=entries.get(normalize_language(active),entries['en'])
    if source in selected:return selected[source]
    if source in entries['en']:return entries['en'][source]
    for template in catalog().get('templates',[]):
        chunks=re.split(r'(\{\d+\})',template)
        fields=[chunk[1:-1] for chunk in chunks if re.fullmatch(r'\{\d+\}',chunk)]
        pattern=''.join('(.+?)' if re.fullmatch(r'\{\d+\}',chunk) else re.escape(chunk) for chunk in chunks)
        match=re.fullmatch(pattern,source,flags=re.S)
        if match:
            translated=selected.get(template,entries['en'].get(template,template))
            values={field:value for field,value in zip(fields,match.groups())}
            arguments=[values.get(str(index),'') for index in range(max(map(int,fields))+1)]
            try:return translated.format(*arguments)
            except (KeyError,ValueError,IndexError):return entries['en'].get(template,template).format(*arguments)
    # Canonical diagnostic prefixes retain paths, names, and native error data.
    for prefix in sorted((key for key in entries['en'] if key.endswith((': ',' · '))),key=len,reverse=True):
        if source.startswith(prefix):
            return selected.get(prefix,entries['en'][prefix])+translate(source[len(prefix):],active)
    return source

def set_language(code):
    global _language,_qt_translator
    _language=valid_language(code)
    from PySide6.QtCore import Qt,QLibraryInfo,QTranslator
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance()
    if app:
        if _qt_translator is not None:app.removeTranslator(_qt_translator)
        _qt_translator=QTranslator(app)
        qt_code={'zh':'zh_CN','pb':'pt_BR'}.get(_language,_language)
        if _qt_translator.load('qtbase_'+qt_code,QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
            app.installTranslator(_qt_translator)
        app.setLayoutDirection(Qt.RightToLeft if _language in ('ar','fa') else Qt.LeftToRight)
    for widget in list(_widgets):
        try:widget.retranslate_ui()
        except RuntimeError:pass  # Qt has already destroyed this dialog/control.
