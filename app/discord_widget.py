"""Bot-free Discord Streamkit observer. Reads visible names/activity only."""
from __future__ import annotations
import json
from collections import Counter
from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout, QGroupBox, QCheckBox
from localized_widgets import QLabel,QLineEdit,QPushButton,QGroupBox,QCheckBox
from speaker_labels import validate_widget_url, widget_connection_status

CONNECTION_SCRIPT = r"""(() => {
  window.__uvkrDiscordConnected = false;
  const fresh = () => ({ ready: false, authorized: false, channel: false, error: '', code: null });
  window.__uvkrDiscordStatus = fresh();
  let owner = null;
  const Original = window.WebSocket;
  window.WebSocket = class extends Original {
    constructor(...args) {
      super(...args);
      let host = '';
      try { host = new URL(String(args[0])).hostname; } catch (_) {}
      if (host === '127.0.0.1' || host === 'localhost') {
        this.addEventListener('open', () => {
          owner = this; window.__uvkrDiscordConnected = true; window.__uvkrDiscordStatus = fresh();
        });
        const closed = () => {
          if (owner !== this) return;
          window.__uvkrDiscordConnected = false; window.__uvkrDiscordStatus = fresh();
        };
        this.addEventListener('close', closed);
        this.addEventListener('error', closed);
        this.addEventListener('message', event => {
          if (owner !== this) return;
          try {
            // Observe command/status only. Never retain tokens, auth codes,
            // complete payloads, user details, or message contents.
            const message = JSON.parse(event.data);
            const state = window.__uvkrDiscordStatus;
            const cmd = message.cmd;
            if (cmd === 'DISPATCH' && message.evt === 'READY') state.ready = true;
            if (!['AUTHORIZE', 'AUTHENTICATE', 'GET_CHANNEL'].includes(cmd)) return;
            if (message.evt === 'ERROR') {
              state.error = cmd;
              const code = message.data?.code;
              state.code = Number.isInteger(code) ? code : null;
              if (cmd === 'GET_CHANNEL') state.channel = false;
              else state.authorized = false;
            } else {
              state.error = ''; state.code = null;
              if (cmd === 'AUTHENTICATE') state.authorized = true;
              if (cmd === 'GET_CHANNEL') state.channel = true;
            }
          } catch (_) {}
        });
      }
    }
  };
})();
"""

AUTO_CHANNEL_SCRIPT = r"""(() => {
  const rpc=window.rpc;
  if (!rpc) return;
  const state=window.__uvkrSelectedChannel ||= {pending:false,last:0,guild:'',channel:'',empty:false,error:null};
  const now=Date.now();
  if (!rpc.connected) {
    state.guild='';state.channel='';state.empty=false;state.pending=false;
    state.serial=(state.serial||0)+1;
    if(state.lastConnect===undefined || now-state.lastConnect>=5000) {
      state.lastConnect=now;
      try { const attempt=rpc.connect(); if(attempt?.catch)attempt.catch(()=>{}); } catch (_) {}
    }
    return;
  }
  if (!rpc.authenticated) {
    state.guild='';state.channel='';state.empty=false;state.pending=false;
    state.serial=(state.serial||0)+1;return;
  }
  if (state.pending && now-state.last<5000) return;
  if (now-state.last<(state.error?10000:1000)) return;
  state.pending=true;state.last=now;state.serial=(state.serial||0)+1;
  const serial=state.serial;
  rpc.request('GET_SELECTED_VOICE_CHANNEL',{}).then(data=>{
    if(state.serial!==serial)return;
    state.pending=false;state.error=null;
    if(data===null){state.guild='';state.channel='';state.empty=true;return;}
    const valid=value=>typeof value==='string' && /^\d{15,22}$/.test(value);
    state.guild=valid(data?.guild_id)?data.guild_id:'';
    state.channel=valid(data?.id)?data.id:'';
    state.empty=false;
    if(!state.guild || !state.channel || data.type!==2)state.error='unsupported';
  }).catch(error=>{
    if(state.serial!==serial)return;
    state.pending=false;state.error=Number.isInteger(error?.code)?error.code:'unavailable';
  });
})();
"""

SNAPSHOT_SCRIPT = r"""(() => JSON.stringify({
  connected: window.__uvkrDiscordConnected === true,
  rpc: window.__uvkrDiscordStatus || null,
  selected: window.__uvkrSelectedChannel || null,
  users: Array.from(document.querySelectorAll('li.voice_state[data-userid]')).map(el => ({
    id: el.getAttribute('data-userid'),
    name: (el.querySelector('.voice_username')?.textContent || '').trim(),
    speaking: el.classList.contains('wrapper_speaking'),
    self: el.classList.contains('is_widget_owner')
  }))
}))();
"""


class DiscordSpeakerTab(QWidget):
    subtitles_requested = Signal()
    def __init__(self, timeline, config, save_config, parent=None):
        super().__init__(parent)
        self.timeline, self.config, self.save_config = timeline, config, save_config
        self.browser = None
        self._pending = False
        self._generation = 0
        self._setup_mode = False
        self._auto_fallback = False
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._poll)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        independent = QLabel('이 연결은 닉네임 표시용입니다. 음성 자막은 Discord 연결이나 서버 초대 권한 없이 시작할 수 있어요.')
        independent.setWordWrap(True)
        layout.addWidget(independent)
        without_names = QPushButton('닉네임 연결 없이 자막 시작')
        without_names.clicked.connect(self.start_without_names)
        layout.addWidget(without_names)
        self.auto_follow=QCheckBox('현재 통화방 자동 연결 · 다음 실행에도 자동으로 따라가기')
        self.auto_follow.setChecked(bool(config.get('discord_auto_follow',True)))
        self.auto_follow.toggled.connect(self._auto_changed)
        layout.addWidget(self.auto_follow)
        setup = QGroupBox('01  ·  Discord 연결 승인')
        first = QVBoxLayout(setup)
        note = QLabel('Discord PC 앱에서 통화방에 들어간 뒤, 공식 연결 화면에서 Install for OBS를 누르세요.\n'
                      'Discord가 요청하는 연결 권한을 승인하면 됩니다. OBS나 서버 봇은 필요하지 않습니다.')
        note.setWordWrap(True)
        first.addWidget(note)
        setup_button = QPushButton('공식 연결 화면 열기')
        setup_button.clicked.connect(self.open_setup)
        first.addWidget(setup_button)
        layout.addWidget(setup)
        channel = QGroupBox('02  ·  통화방 선택')
        second = QVBoxLayout(channel)
        instructions = QLabel('Discord에서 현재 통화방을 우클릭 → 채널 링크 복사 → 아래에 붙여넣으세요.\n'
                              '일반 discord.com/channels/… 주소를 자동으로 처리합니다. 공식 Voice Widget 주소도 사용할 수 있어요.')
        instructions.setWordWrap(True)
        second.addWidget(instructions)
        self.url = QLineEdit(config.get('discord_voice_widget', ''))
        self.url.setPlaceholderText('Discord 통화방의 채널 링크를 붙여넣으세요')
        second.addWidget(self.url)
        buttons = QHBoxLayout()
        for label, fn in [('닉네임 연결 시작', self.connect_widget),
                          ('연결 중지', self.stop_connection)]:
            button = QPushButton(label)
            if fn == self.connect_widget:
                button.setObjectName('primaryButton')
            button.clicked.connect(fn)
            buttons.addWidget(button)
        second.addLayout(buttons)
        layout.addWidget(channel)
        preview = QGroupBox('연결 상태')
        preview_layout = QVBoxLayout(preview)
        self.state = QLabel('닉네임 연결 대기 · 미연결 시 화자 미확인')
        self.state.setWordWrap(True)
        preview_layout.addWidget(self.state)
        self.browser_layout = QVBoxLayout()
        self.placeholder = QLabel('연결하면 이곳에서 참여자와 발언 상태를 확인할 수 있어요.')
        self.placeholder.setObjectName('muted')
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setMinimumHeight(120)
        self.placeholder.setWordWrap(True)
        self.browser_layout.addWidget(self.placeholder)
        preview_layout.addLayout(self.browser_layout, 1)
        layout.addWidget(preview, 1)
        limits = QLabel('닉네임은 발언 시각으로 추정합니다. 겹친 목소리는 동시 발화로 표시합니다.\n'
                        '자동 연결을 켜면 통화방 이동을 따라갑니다. 첫 연결 승인은 직접 완료해 주세요.')
        limits.setObjectName('muted')
        limits.setWordWrap(True)
        layout.addWidget(limits)
        QTimer.singleShot(700,self._resume_auto)

    def _resume_auto(self):
        if self.auto_follow.isChecked():self.open_setup()

    def _auto_changed(self,enabled):
        self.config['discord_auto_follow']=bool(enabled);self.save_config()
        self._auto_fallback=False
        if enabled:self.open_setup()

    def stop_connection(self):
        self.auto_follow.setChecked(False)
        self.disconnect_widget()

    def _ensure_browser(self):
        if self.browser is not None:
            return True
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            from PySide6.QtWebEngineCore import QWebEngineScript, QWebEnginePage, QWebEngineProfile
            profile = QWebEngineProfile(self)  # off-the-record; no copied login cookies
            profile.setHttpUserAgent(profile.httpUserAgent().replace('QtWebEngine/', 'Chromium/'))

            class OfficialPage(QWebEnginePage):
                def javaScriptConsoleMessage(page, level, message, line, source):
                    pass  # Official page logs can contain complete RPC payloads.
                def acceptNavigationRequest(page, url, kind, is_main):
                    if not is_main:
                        return True
                    return (url.scheme() == 'https' and url.host() == 'streamkit.discord.com') or url.toString() == 'about:blank'

            self.browser = QWebEngineView(self)
            page = OfficialPage(profile, self.browser)
            self.browser.setPage(page)
            script = QWebEngineScript()
            script.setName('UniversalVoiceKR connection status')
            script.setInjectionPoint(QWebEngineScript.DocumentCreation)
            script.setWorldId(QWebEngineScript.MainWorld)
            script.setSourceCode(CONNECTION_SCRIPT)
            page.scripts().insert(script)
            self.browser.setMinimumHeight(230)
            self.placeholder.hide()
            self.browser_layout.addWidget(self.browser)
            self.browser.loadFinished.connect(self._loaded)
            return True
        except ImportError:
            self.state.setText('공식 위젯 화면을 열 수 없습니다. PySide6 WebEngine 설치를 확인하세요.')
            return False

    def open_setup(self):
        self.disconnect_widget()
        self._setup_mode = True
        if self._ensure_browser():
            self.browser.load(QUrl('https://streamkit.discord.com/overlay'))
            self.state.setText('공식 Streamkit 연결 화면 · Discord의 권한 승인 창을 확인하세요.')
            self.timer.start()

    def connect_widget(self):
        try:
            url = validate_widget_url(self.url.text())
        except ValueError as exc:
            self.state.setText(str(exc))
            return
        self.disconnect_widget()
        self._setup_mode = False
        if not self._ensure_browser():
            return
        self.config['discord_voice_widget'] = url
        self.url.setText(url)
        self.save_config()
        self.browser.load(QUrl(url))
        self.state.setText('공식 Voice Widget 연결 중 · Discord가 권한을 요청하면 직접 승인하세요.')
        self.timer.start()

    def start_without_names(self):
        self.auto_follow.setChecked(False)
        self.disconnect_widget()
        self.subtitles_requested.emit()

    def disconnect_widget(self):
        self._generation += 1
        self._pending = False
        self.timer.stop()
        # Keep past snapshots for ASR already in flight, append an empty state.
        self.timeline.record([])
        if self.browser is not None:
            self.browser.stop()
            self.browser.load(QUrl('about:blank'))
        self.state.setText('닉네임 연결 중지됨 · 화자 미확인으로 표시')

    def _loaded(self, ok):
        if not ok and self.timer.isActive():
            self.timeline.record([])
            self.state.setText('위젯을 불러오지 못했습니다. 인터넷·Discord PC 앱 연결을 확인하세요.')

    def _poll(self):
        if self.browser is None or self._pending:
            return
        self._pending = True
        generation = self._generation
        script=(AUTO_CHANNEL_SCRIPT if self.auto_follow.isChecked() else '')+SNAPSHOT_SCRIPT
        self.browser.page().runJavaScript(script,
                        lambda value: self._received(value, generation))

    def _received(self, value, generation):
        if generation != self._generation:
            return
        self._pending = False
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                value = None
        if isinstance(value,dict) and self.auto_follow.isChecked():
            selected=value.get('selected')
            if isinstance(selected,dict):
                if selected.get('empty'):
                    self.timeline.record([])
                    if not self._setup_mode:self.open_setup()
                    self.state.setText('자동 연결 대기 · Discord PC 앱에서 음성 통화방에 들어가세요.')
                    return
                guild,channel=selected.get('guild'),selected.get('channel')
                if guild and channel and not selected.get('error'):
                    try:url=validate_widget_url('https://discord.com/channels/'+guild+'/'+channel)
                    except ValueError:url=''
                    if url and self.browser.url().toString()!=url:
                        self.url.setText(url);self.connect_widget();return
                if selected.get('error') and self._setup_mode:
                    saved=self.config.get('discord_voice_widget','')
                    if saved and not self._auto_fallback:
                        self._auto_fallback=True;self.url.setText(saved);self.connect_widget();return
                    self.timeline.record([])
                    self.state.setText('현재 통화방 자동 조회를 사용할 수 없습니다. 한 번 채널 링크를 넣어 수동 연결해 주세요.')
                    return
        ready, explanation = widget_connection_status(value, self._setup_mode)
        if not ready:
            self.timeline.record([])
            self.state.setText(explanation)
            return
        users = value.get('users', [])
        counts = Counter(u.get('name') for u in users)
        active = [(u['name'] + (' · ' + str(u.get('id', ''))[-6:] if counts[u['name']] > 1 else ''))
                  for u in users if u.get('speaking') and not u.get('self') and u.get('name')]
        self.timeline.record(active)
        if active:
            self.state.setText('발언 중: ' + ' / '.join(active) + ' · 자막에 시간 기준으로 연결')
        else:
            self.state.setText(f'위젯 연결됨 · 참여자 {len(users)}명 · 음성 대기')
