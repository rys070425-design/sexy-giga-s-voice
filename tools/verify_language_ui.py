"""Native Qt UI checks using a separate settings folder, no real account/audio."""
import os,sys,json,time,copy,tempfile
from pathlib import Path
from unittest.mock import patch
root=Path(sys.argv[1]).resolve();report=Path(sys.argv[2]).resolve()
test_state=tempfile.TemporaryDirectory(prefix='language-ui-',dir=report.parent)
os.environ['UVKR_DATA_DIR']=test_state.name
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QTWEBENGINE_CHROMIUM_FLAGS']='--disable-gpu'
sys.path.insert(0,str(root))
from runtime_config import configure
configure()
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
import main,core
from language_preferences import language_choices
from live_captions import CaptionUpdate
app=QApplication([])
for filename in ('malgun.ttf','segoeui.ttf','Nirmala.ttf','LeelawUI.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+filename)
app.setStyleSheet(main.STYLESHEET)
main.MainWindow.update_plan_state=lambda self:None
main.MainWindow._refresh_sources=lambda self:self.source.addItem('Test playback','')
window=main.MainWindow()
window.tab_discord.auto_follow.setChecked(False)
window.show();app.processEvents()
assert window.cfg['ui_language']=='en'
assert window.navigation.item(0).text()=='Live captions'
assert window.target_language.count()==25
language_control=window.ui_language
assert language_control.count()==25
window.profile_name.setText('My 이름 · 미설치')
expected=[]
for name,code in language_choices():
    language_control.setCurrentIndex(language_control.findData(code));app.processEvents()
    assert window.cfg['ui_language']==code
    assert window.target_language.currentData()==code
    assert window.profile_name.text()=='My 이름 · 미설치'
    assert window.hide_native.isChecked()
    assert not window.language.isEnabled()
    assert window.navigation.item(0).text()
    if code=='ko':assert window.navigation.item(0).text()=='실시간 자막'
    expected.append(code)
    if code in ('en','ko','ja','ar'):
        window.grab().save(str(report.parent/('language-ui-'+code+'.png')))
language_control.setCurrentIndex(language_control.findData('ko'));app.processEvents()
native=CaptionUpdate(3,100,'한국어 내용','한국어 내용','ko','Name',True,True)
window.on_live_caption(native);app.processEvents()
assert not window.overlay.isVisible()
assert window.history.toPlainText()==''
window.on_live_caption(CaptionUpdate(3,100,'late foreign','늦은 결과','en','Name',True,True))
assert not window.overlay.isVisible() and window.history.toPlainText()==''
window.on_live_caption(CaptionUpdate(4,100,'I need help.','도움이 필요해요.','en','Name',True,True,'YouTube'))
app.processEvents()
assert window.overlay.isVisible()
assert window.overlay.label.text()=='도움이 필요해요.'
assert window.history.toPlainText().count('도움이 필요해요.')==1
history=window.history.toPlainText()
language_control.setCurrentIndex(language_control.findData('en'));app.processEvents()
assert window.history.toPlainText()==history,'Language switch modified actual caption data'
window.on_live_caption(CaptionUpdate(5,100,'English native','English native','en','Name',True,True))
assert not window.overlay.isVisible()
assert window.history.toPlainText()==history
window.on_live_caption(CaptionUpdate(6,100,'도움이 필요해요.','I need help.','ko','Name',True,True,'YouTube',target_language='en'))
app.processEvents()
assert window.overlay.label.text()=='I need help.'
window.on_live_caption(CaptionUpdate(7,100,'안녕하세요.','Hello.','ko','Test Discord nickname',True,True,'',target_language='en'))
window.presentation.changed_at-=1;window.advance_captions();app.processEvents()
assert not window.overlay.speaker_label.isVisible(),'Unknown source retained a guessed source header'
assert window.overlay.speaker_label.text()==''
assert 'Discord nickname' not in window.history.toPlainText()
window.overlay.grab().save(str(report.parent/'source-caption-unidentified.png'))
window.on_live_caption(CaptionUpdate(8,100,'다음 문장.','Next sentence.','ko','',True,True,'VLC',target_language='en'))
window.presentation.changed_at-=1;window.advance_captions();app.processEvents()
assert window.overlay.speaker_label.isVisible() and window.overlay.speaker_label.text()=='VLC'
window.overlay.grab().save(str(report.parent/'source-caption-confirmed.png'))
window.hide_native.setChecked(False);assert window.language.isEnabled()
window.hide_native.setChecked(True);assert not window.language.isEnabled()
window.add_profile()
assert window.cfg['profiles'][window.profile_idx]['target_language']=='en'
window.cfg['ui_language']='ko';core.write_json(core.HOME/'settings.json',window.cfg)
window.close();app.processEvents()
result={'result':'LANGUAGE_UI_VERIFIED','ui_languages':expected,'same_language_hidden':True,'history_filtered':True,'real_caption_text_preserved':True,'uncertain_source_header_hidden':True,'confirmed_source_header_restored':True}
report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result),flush=True)
