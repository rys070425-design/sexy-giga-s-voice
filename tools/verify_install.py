import os,sys,json,time,subprocess
from unittest.mock import patch
from pathlib import Path
root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root))
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QTWEBENGINE_CHROMIUM_FLAGS']='--disable-gpu'
from runtime_config import configure
configure()
import PySide6,ctranslate2,argostranslate.package,numpy
for module in [PySide6,ctranslate2,argostranslate.package,numpy]:
    assert Path(module.__file__).resolve().is_relative_to(root/'.venv'),module.__file__
from cuda_runtime import prepare_cuda
prepare_cuda()
from faster_whisper import WhisperModel
model=WhisperModel(str(root/'models'/'large-v3-turbo'),device='cuda' if ctranslate2.get_cuda_device_count() else 'cpu',compute_type='int8_float16' if ctranslate2.get_cuda_device_count() else 'int8')
segments,info=model.transcribe(sys.argv[2],language='ko',beam_size=5)
text=' '.join(s.text.strip() for s in segments)
assert '기지' in text and '공격' in text,text
from local_translation import LocalTranslator
translation=LocalTranslator().translate('I need help.','en')
assert '도움' in translation,translation
assert 'NLLB' in LocalTranslator().model_label
assert '동의하지' in LocalTranslator().translate('I disagree with that idea.','en')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
import main,core
app=QApplication([])
from single_instance import SingleInstance
first_instance=SingleInstance(root/'test-instance')
second_instance=SingleInstance(root/'test-instance')
activations=[]
first_instance.activated.connect(lambda:activations.append(True))
assert first_instance.acquire()
assert not second_instance.acquire(),'A second launch must not load another model'
app.processEvents()
assert activations,'Second launch did not activate the existing window'
first_instance.close()
assert second_instance.acquire(),'Normal shutdown did not release the application lock'
second_instance.close()
crash_home=root/'test-crash-instance'
child_code="import sys,os; from pathlib import Path; from PySide6.QtCore import QCoreApplication; sys.path.insert(0,sys.argv[1]); from single_instance import SingleInstance; app=QCoreApplication([]); owner=SingleInstance(Path(sys.argv[2])); assert owner.acquire(); os._exit(0)"
subprocess.run([sys.executable,'-B','-c',child_code,str(root),str(crash_home)],check=True,timeout=15)
recovered=SingleInstance(crash_home)
assert recovered.acquire(),'An interrupted app left a permanent launch lock'
recovered.close()
QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf')
app.setStyleSheet(main.STYLESHEET)
testhome=root/'test-state'
main.HOME=testhome
main.init_files=lambda:core.init_files(testhome)
main.MainWindow.update_plan_state=lambda self:None
main.MainWindow._refresh_sources=lambda self:self.source.addItem('시험 출력 장치','')
window=main.MainWindow()
window.tab_discord.auto_follow.setChecked(False)
window.show();app.processEvents()
assert window.tabs.count()==7
for i in range(7):window.navigation.setCurrentRow(i);app.processEvents();assert window.tabs.currentIndex()==i
window.navigation.setCurrentRow(0)
from live_captions import CaptionUpdate
window.on_live_caption(CaptionUpdate(1,60,'test draft','','en','시험 화자'))
assert not window.live_text.isVisible(),'Untranslated foreign draft should not flash'
window.on_live_caption(CaptionUpdate(1,60,'test draft','초안','en','시험 화자',False,True))
assert window.overlay.label.text()=='초안'
assert window.overlay.label.font().pointSizeF()>=24,'Application styles shrank the subtitle font'
window.on_live_caption(CaptionUpdate(1,100,'final words','','en','시험 화자',True))
assert window.overlay.label.text()=='초안','Existing translation flickered back to original'
assert window.history.toPlainText()==''
window.on_live_caption(CaptionUpdate(1,100,'final words','확정 문장','en','시험 화자',True,True))
window.presentation.changed_at-=1;window.advance_captions()
assert window.history.toPlainText().count('확정 문장')==1
assert window.live_text.isVisible()
window.on_live_caption(CaptionUpdate(2,60,'new draft','','en','새 화자'))
assert window.overlay.label.text()=='확정 문장'
window.on_live_caption(CaptionUpdate(2,60,'new draft','새 문장','en','화자 미확인',False,True,'YouTube'))
window.presentation.changed_at-=1;window.advance_captions()
window.on_live_caption(CaptionUpdate(1,100,'old words','늦은 이전 번역','en','이전 화자',True,True))
assert window.overlay.label.text()=='새 문장'
assert '늦은 이전 번역' in window.overlay.previous_label.text()
assert window.overlay.speaker_label.text()=='YouTube'
assert '인식 중' not in window.live_text.text() and '화자 미확인' not in window.live_text.text()
assert '107' in window.overlay.surface.styleSheet()
window.background_opacity.setValue(20)
assert '51' in window.overlay.surface.styleSheet()
window.background_opacity.setValue(42)
window.source_label.setText('시험 출처')
window.source_label.editingFinished.emit()
until=time.monotonic()+.7
while time.monotonic()<until:app.processEvents();time.sleep(.01)
saved=json.loads((testhome/'settings.json').read_text(encoding='utf-8'))
assert saved['profiles'][window.profile_idx]['background_opacity']==42
assert saved['profiles'][window.profile_idx]['source_label']=='시험 출처'
window.source_label.clear();window.source_label.editingFinished.emit()
assert window.history.toPlainText().count('늦은 이전 번역')==1
export_path=testhome/'caption-export.txt'
with patch.object(main.QFileDialog,'getSaveFileName',return_value=(str(export_path),'Text files (*.txt)')):
    window.save_history()
exported=export_path.read_text(encoding='utf-8-sig')
assert '늦은 이전 번역' in exported and 'old words' in exported,'Saved captions lost the original or translation'
assert window.live_text.isVisible()
window.live_language.setCurrentIndex(window.live_language.findData('ko'))
assert window.language.currentData()=='ko'
window.language.setCurrentIndex(window.language.findData('en'))
assert window.live_language.currentData()=='en'
window.resize(960,620)
for i in range(7):
    window.navigation.setCurrentRow(i);app.processEvents();assert window.tabs.currentIndex()==i
    scroll=window.tabs.widget(i)
    assert scroll.widget().width()<=scroll.viewport().width(),('Page clips horizontally',i,scroll.widget().width(),scroll.viewport().width())
window.navigation.setCurrentRow(0)
window.on_caption('Test','설치 검증이 완료되었습니다.','en','테스트')
app.processEvents()
window.grab().save(str(root/'fresh-install-ui.png'))
tab=window.tab_discord
assert tab._ensure_browser(),'WebEngine unavailable'
from PySide6.QtWebEngineCore import QWebEnginePage
from discord_widget import SNAPSHOT_SCRIPT
tab.browser.setPage(QWebEnginePage(tab.browser.page().profile(),tab.browser))
fixture={}
def loaded(ok):
    if ok:tab.browser.page().runJavaScript(SNAPSHOT_SCRIPT,lambda value:fixture.update(json.loads(value)))
tab.browser.loadFinished.connect(loaded)
tab.browser.setHtml('<html><li class="voice_state wrapper_speaking" data-userid="123"><div class="voice_username">Test</div></li><script>window.__uvkrDiscordConnected=true;</script></html>')
deadline=time.monotonic()+15
while 'users' not in fixture and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
assert fixture.get('users',[{}])[0].get('name')=='Test',fixture
from discord_widget import CONNECTION_SCRIPT
def run_js(script):
    answer={}
    tab.browser.page().runJavaScript(script,lambda value:answer.update(value=value))
    until=time.monotonic()+10
    while 'value' not in answer and time.monotonic()<until:app.processEvents();time.sleep(.01)
    assert 'value' in answer,'JavaScript callback timed out'
    return json.loads(answer['value'])
mock_socket='''window.WebSocket = class {
  constructor(url) { this.handlers = {}; }
  addEventListener(name, callback) { (this.handlers[name] ||= []).push(callback); }
  fire(name, message) { for (const callback of (this.handlers[name] || [])) callback({data:JSON.stringify(message)}); }
};'''
snapshot=run_js(mock_socket+CONNECTION_SCRIPT+'''
window.testSocket = new WebSocket('ws://127.0.0.1:6463/?v=1');
window.testSocket.fire('open');
'''+SNAPSHOT_SCRIPT)
assert snapshot['connected'] and not snapshot['rpc']['authorized']
tab._received(json.dumps(snapshot),tab._generation)
assert '아직' in tab.state.text()
snapshot=run_js('''
window.testSocket.fire('message',{cmd:'AUTHENTICATE',data:{access_token:'MUST_NOT_RETAIN'}});
window.testSocket.fire('message',{cmd:'GET_CHANNEL',evt:'ERROR',data:{code:4006}});
'''+SNAPSHOT_SCRIPT)
assert 'MUST_NOT_RETAIN' not in json.dumps(snapshot)
tab._received(json.dumps(snapshot),tab._generation)
assert '4006' in tab.state.text() and '읽지 못했습니다' in tab.state.text()
snapshot=run_js('''
window.testSocket.fire('message',{cmd:'GET_CHANNEL',data:{}});
window.testSocket.fire('message',{cmd:'CREATE_CHANNEL_INVITE',evt:'ERROR',data:{code:4006}});
'''+SNAPSHOT_SCRIPT)
assert snapshot['rpc']['channel'] and not snapshot['rpc']['error']
tab._received(json.dumps(snapshot),tab._generation)
assert '발언 중: Test' in tab.state.text()
snapshot=run_js('''
window.newSocket = new WebSocket('ws://127.0.0.1:6464/?v=1');
window.newSocket.fire('open');window.testSocket.fire('close');
'''+SNAPSHOT_SCRIPT)
assert snapshot['connected'],'Old socket invalidated a newer connection'
from discord_widget import AUTO_CHANNEL_SCRIPT
run_js('''window.savedNow=Date.now;window.testNow=100000;Date.now=()=>window.testNow;
window.connectAttempts=0;window.rpc={connected:false,connect:()=>{window.connectAttempts++;return Promise.reject('fixture');}};
'''+AUTO_CHANNEL_SCRIPT*12+SNAPSHOT_SCRIPT)
attempts=run_js('JSON.stringify({attempts:window.connectAttempts})')
assert attempts['attempts']==1,'Disconnected RPC was being retried on every UI poll'
run_js('window.testNow+=5000;'+AUTO_CHANNEL_SCRIPT+SNAPSHOT_SCRIPT)
attempts=run_js('JSON.stringify({attempts:window.connectAttempts})')
assert attempts['attempts']==2,'Discord reconnect did not recover after its backoff'
run_js('Date.now=window.savedNow;delete window.__uvkrSelectedChannel;'+SNAPSHOT_SCRIPT)
run_js('''window.commands=[];window.rpc={connected:true,authenticated:true,
request:(cmd,args)=>{window.commands.push(cmd);return Promise.resolve({id:'234567890123456789',guild_id:'123456789012345678',type:2});}};
'''+AUTO_CHANNEL_SCRIPT+SNAPSHOT_SCRIPT)
snapshot=run_js(SNAPSHOT_SCRIPT)
assert snapshot['selected']['channel']=='234567890123456789'
assert snapshot['selected']['guild']=='123456789012345678'
loaded_channels=[]
original_connect=tab.connect_widget
tab.connect_widget=lambda:loaded_channels.append(tab.url.text())
tab.auto_follow.blockSignals(True);tab.auto_follow.setChecked(True);tab.auto_follow.blockSignals(False)
tab._received(json.dumps(snapshot),tab._generation)
assert loaded_channels==['https://streamkit.discord.com/overlay/voice/123456789012345678/234567890123456789']
tab.connect_widget=original_connect
tab.auto_follow.blockSignals(True);tab.auto_follow.setChecked(False);tab.auto_follow.blockSignals(False)
extension=(root/'browser_source_extension'/'background.js').read_text(encoding='utf-8')
run_js('''
const event={addListener:()=>{}};
window.chrome={storage:{local:{get:async()=>({key:'TEST_PAIRING_KEY_NOT_REAL',enabled:true})}},
tabs:{query:async()=>[{url:'https://www.youtube.com/watch?v=PRIVATE_QUERY',audible:true},{url:'https://example.com/path',audible:true},{url:'https://muted.example/',mutedInfo:{muted:true}},{url:'https://private.example/',incognito:true}],onUpdated:event,onRemoved:event,onReplaced:event},
alarms:{onAlarm:event,create:()=>{}},runtime:{onInstalled:event,onStartup:event,onMessage:event}};
window.fetch=async(url,args)=>{window.bridgePayload=JSON.parse(args.body);return {ok:true};};
'''+extension+'''report().then(result=>{window.reportDone=result.ok;});JSON.stringify({started:true});''')
until=time.monotonic()+3
while time.monotonic()<until:
    payload=run_js('JSON.stringify({done:window.reportDone,payload:window.bridgePayload});')
    if payload.get('done'):break
assert payload['payload']['hosts']==['www.youtube.com','example.com']
assert 'PRIVATE_QUERY' not in json.dumps(payload)
started=[]
original_start=window.start_service
window.start_service=lambda:started.append(True)
tab.start_without_names()
assert started==[True] and window.navigation.currentRow()==0
window.start_service=original_start
assert 'torch' not in sys.modules
window.close();app.processEvents()
result=dict(result='FRESH_INSTALL_VERIFIED',python=sys.executable,source=str(root),transcription=text,translation=translation,ui_pages=7,webengine=True)
(root/'FRESH_TEST_RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False),flush=True)
