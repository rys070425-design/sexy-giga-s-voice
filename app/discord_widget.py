"""Bot-free Discord Streamkit observer. Reads visible names/activity only."""
from __future__ import annotations
import json
from collections import Counter
from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout, QGroupBox
from speaker_labels import validate_widget_url

CONNECTION_SCRIPT = r"""(() => {
  window.__uvkrDiscordConnected = false;
  const Original = window.WebSocket;
  window.WebSocket = class extends Original {
    constructor(...args) {
      super(...args);
      let host = '';
      try { host = new URL(String(args[0])).hostname; } catch (_) {}
      if (host === '127.0.0.1' || host === 'localhost') {
        this.addEventListener('open', () => { window.__uvkrDiscordConnected = true; });
        this.addEventListener('close', () => { window.__uvkrDiscordConnected = false; });
        this.addEventListener('error', () => { window.__uvkrDiscordConnected = false; });
      }
    }
  };
})();
"""

SNAPSHOT_SCRIPT = r"""(() => JSON.stringify({
  connected: window.__uvkrDiscordConnected === true,
  users: Array.from(document.querySelectorAll('li.voice_state[data-userid]')).map(el => ({
    id: el.getAttribute('data-userid'),
    name: (el.querySelector('.voice_username')?.textContent || '').trim(),
    speaking: el.classList.contains('wrapper_speaking'),
    self: el.classList.contains('is_widget_owner')
  }))
}))();
"""


class DiscordSpeakerTab(QWidget):
    def __init__(self, timeline, config, save_config, parent=None):
        super().__init__(parent)
        self.timeline, self.config, self.save_config = timeline, config, save_config
        self.browser = None
        self._pending = False
        self._generation = 0
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._poll)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
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
        instructions = QLabel('공식 화면에서 Voice Widget → 서버 → 음성 채널을 선택하고, 제공된 주소를 아래에 붙여넣으세요.')
        instructions.setWordWrap(True)
        second.addWidget(instructions)
        self.url = QLineEdit(config.get('discord_voice_widget', ''))
        self.url.setPlaceholderText('Streamkit에서 복사한 Voice Widget 주소')
        second.addWidget(self.url)
        buttons = QHBoxLayout()
        for label, fn in [('닉네임 연결 시작', self.connect_widget),
                          ('연결 중지', self.disconnect_widget)]:
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
                        '서버·통화방을 바꾸면 위젯 주소도 바꿔 주세요. 이름 숨기기는 꺼 두세요.')
        limits.setObjectName('muted')
        limits.setWordWrap(True)
        layout.addWidget(limits)

    def _ensure_browser(self):
        if self.browser is not None:
            return True
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            from PySide6.QtWebEngineCore import QWebEngineScript, QWebEnginePage, QWebEngineProfile
            profile = QWebEngineProfile(self)  # off-the-record; no copied login cookies
            profile.setHttpUserAgent(profile.httpUserAgent().replace('QtWebEngine/', 'Chromium/'))

            class OfficialPage(QWebEnginePage):
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
        if self._ensure_browser():
            self.browser.load(QUrl('https://streamkit.discord.com/overlay'))
            self.state.setText('공식 Streamkit 연결 화면 · Discord의 권한 승인 창을 확인하세요.')

    def connect_widget(self):
        try:
            url = validate_widget_url(self.url.text())
        except ValueError as exc:
            self.state.setText(str(exc))
            return
        self.disconnect_widget()
        if not self._ensure_browser():
            return
        self.config['discord_voice_widget'] = url
        self.save_config()
        self.browser.load(QUrl(url))
        self.state.setText('공식 Voice Widget 연결 중 · Discord가 권한을 요청하면 직접 승인하세요.')
        self.timer.start()

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
        self.browser.page().runJavaScript(SNAPSHOT_SCRIPT,
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
        if not isinstance(value, dict) or not value.get('connected'):
            self.timeline.record([])
            self.state.setText('Discord 위젯 연결 대기 · PC 앱과 권한 승인을 확인하세요.')
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
