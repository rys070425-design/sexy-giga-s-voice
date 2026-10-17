"""Shared installer/app language choices, derived from the language-pack catalog."""
from language_packs import LANGUAGES

NATIVE_NAMES={
    'ko':'한국어','en':'English','es':'Español','pt':'Português','pb':'Português (Brasil)',
    'ru':'Русский','pl':'Polski','tr':'Türkçe','de':'Deutsch','fr':'Français',
    'zh':'中文（简体）','ja':'日本語','it':'Italiano','ar':'العربية','uk':'Українська',
    'nl':'Nederlands','id':'Bahasa Indonesia','hi':'हिन्दी','cs':'Čeština','sv':'Svenska',
    'vi':'Tiếng Việt','th':'ไทย','tl':'Filipino','ro':'Română','fa':'فارسی',
}

def language_choices():
    return [(NATIVE_NAMES[code],code) for code in LANGUAGES]

def normalize_language(code):
    return 'pt' if code=='pb' else code

def valid_language(code,default='en'):
    return code if isinstance(code,str) and code in LANGUAGES else default

def same_language(source,target):
    return normalize_language(source)==normalize_language(target)

def apply_install_language(settings,code):
    code=valid_language(code)
    settings['ui_language']=code
    settings['default_caption_language']=code
    for profile in settings.get('profiles',[]):
        if isinstance(profile,dict):
            profile.update(target_language=code,language='auto',hide_native=True)
    return settings
