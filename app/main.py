"""Universal Voice KR · local Windows speech subtitle prototype.

Discord voice is the first-class use case. Output loopback only; never microphone input.
Discord names use the officially approved Streamkit connection; no user token,
server bot or privileged injection is used.
"""
from __future__ import annotations
import copy
import html
from pathlib import Path
import json
import sys
import threading
import secrets
import webbrowser
import urllib.request
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal, QUrl, QStandardPaths
from PySide6.QtGui import QFont, QIcon, QFontMetrics, QDesktopServices, QColor
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QPlainTextEdit, QSpinBox, QTabWidget, QFileDialog,
    QVBoxLayout, QWidget, QInputDialog, QListWidget, QFrame, QScrollArea, QStyle, QTextEdit, QSlider, QDialog, QGraphicsDropShadowEffect)
from PySide6.QtGui import QTextCursor

from core import (HOME, DEFAULT_PROFILES, init_files, merge_glossary,
                  remember_phrase, read_phrase_memory,
                  read_json, update_due, valid_remote_dictionary, write_json)
from engine import VoiceService
from live_captions import DisplayOrder
from caption_presentation import ReadableCaptions, CaptionCard, clean_caption_label, wrap_measured
from source_bridge import BrowserSourceBridge
from gpu_tab import GpuSetupTab
from discord_widget import DiscordSpeakerTab
from chatgpt_plan import PlanAccount, AccountError, improve_translation, build_review_prompt
from language_packs import (LANGUAGES as PACK_LANGUAGES, read_pack, create_manifest,
                            save_terms_without_overwrite, install_translation_models,
                            installed_for_language)

LANGUAGES = {"자동 감지 · 여러 언어": "auto"} | {name: code for code, (name, _) in PACK_LANGUAGES.items()}


def row(*items):
    lay = QHBoxLayout()
    for item in items:
        lay.addWidget(item)
    return lay


def paragraph(text):
    label=QLabel(text)
    label.setWordWrap(True)
    return label


def combo(items, val=None):
    w = QComboBox()
    w.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    w.setMinimumContentsLength(12)
    for label, value in items:
        w.addItem(str(label), value)
    if val is not None:
        idx = w.findData(val)
        if idx >= 0:
            w.setCurrentIndex(idx)
    return w


class WorkspacePages(QTabWidget):
    def setCurrentWidget(self, widget):
        super().setCurrentWidget(getattr(widget, '_scroll_container', widget))


class TranscriptView(QTextEdit):
    def appendPlainText(self, text):
        self.append(html.escape(text).replace('\n', '<br>'))

    def append_caption(self, speaker, translated, original, stamp, language):
        self.moveCursor(QTextCursor.End)
        original_html=('<p style="color:#96a5ba;font-size:12px;margin-bottom:20px;">'+html.escape(original)+'</p>') if original.strip()!=translated.strip() else ''
        self.insertHtml(
            '<p style="margin-top:18px;margin-bottom:5px;">'
            '<span style="color:#8fe3c9;font-weight:600;">' + html.escape(speaker) + '</span>'
            '<span style="color:#8999af;font-size:11px;"> &nbsp; ' + html.escape(stamp) +
            ' · ' + html.escape(language.upper()) + '</span></p>'
            '<p style="color:#f0f3fa;font-size:16px;margin-top:5px;margin-bottom:7px;">' + html.escape(translated) + '</p>'
            + original_html + '<br>')
        self.ensureCursorVisible()


class SubtitleOverlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                         Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(12, 12, 12, 12)
        surface = self.surface = QFrame()
        surface.setObjectName('subtitleSurface')
        surface.setStyleSheet('QFrame#subtitleSurface {background: rgba(12,18,27,230); border: 1px solid rgba(120,160,175,100); border-radius: 14px;} QLabel {background: transparent; border: none;}')
        caption_layout = QVBoxLayout(surface)
        caption_layout.setContentsMargins(22, 14, 22, 16)
        caption_layout.setSpacing(7)
        self.speaker_label = QLabel('')
        self.speaker_label.setTextFormat(Qt.PlainText)
        self.speaker_label.setFont(QFont('Malgun Gothic', 12, QFont.DemiBold))
        self.speaker_label.setStyleSheet('color: #8ce8cb; font-size: 12pt;')
        self.speaker_label.setAlignment(Qt.AlignCenter)
        caption_layout.addWidget(self.speaker_label)
        self.previous_label = QLabel('')
        self.previous_label.setTextFormat(Qt.PlainText)
        self.previous_label.setAlignment(Qt.AlignCenter)
        self.previous_label.setStyleSheet('color: #c5d1df;')
        caption_layout.addWidget(self.previous_label)
        self.label = QLabel("")
        self.label.setTextFormat(Qt.PlainText)
        self.label.setWordWrap(False)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet('color: #f4f6fc;')
        caption_layout.addWidget(self.label)
        self.original_label = QLabel('')
        self.original_label.setTextFormat(Qt.PlainText)
        self.original_label.setWordWrap(True)
        self.original_label.setFont(QFont('Malgun Gothic', 12))
        self.original_label.setAlignment(Qt.AlignCenter)
        self.original_label.setStyleSheet('color: #aebdce; font-size: 12pt;')
        caption_layout.addWidget(self.original_label)
        for text_label in (self.previous_label,self.label,self.speaker_label):
            shadow=QGraphicsDropShadowEffect(text_label)
            shadow.setBlurRadius(8);shadow.setOffset(0,1);shadow.setColor(QColor(0,0,0,220))
            text_label.setGraphicsEffect(shadow)
        self.box.addWidget(surface)
        self.resize(960, 145)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def show_caption(self, original, translated, profile, speaker="화자 미확인"):
        label=speaker if speaker and speaker!='화자 미확인' else (profile.get('source_label') or '오디오')
        card=CaptionCard(-1,translated,original,label,True)
        self.show_readable(card,None,profile)

    def show_readable(self, card, previous, profile):
        if not profile.get("overlay", True):
            self.hide()
            return
        font = int(profile.get("font", 26))
        self.label.setFont(QFont("Malgun Gothic", font, QFont.DemiBold))
        self.previous_label.setFont(QFont("Malgun Gothic", font))
        # The application-wide QWidget font rule otherwise overrides setFont,
        # silently shrinking subtitles to the settings UI's 13-pixel text.
        self.label.setStyleSheet(f'color:#f4f6fc;font-size:{font}pt;font-weight:600;')
        self.previous_label.setStyleSheet(f'color:#c5d1df;font-size:{font}pt;')
        opacity=max(15,min(80,int(profile.get('background_opacity',42))))
        self.surface.setStyleSheet('QFrame#subtitleSurface {background: rgba(12,18,27,'+str(round(opacity*2.55))+'); border: 1px solid rgba(160,190,205,45); border-radius: 14px;} QLabel {background: transparent;border: none;}')
        screen = QApplication.primaryScreen()
        if screen:self.setFixedWidth(min(1000,int(screen.availableGeometry().width()*.80)))
        header_metrics=QFontMetrics(self.speaker_label.font())
        self.speaker_label.setText(header_metrics.elidedText(card.label,Qt.ElideRight,max(80,self.width()-80)))
        metrics=QFontMetrics(self.label.font())
        lines=wrap_measured(card.text,max(80,self.width()-80),metrics.horizontalAdvance)
        if len(lines)>=2:
            older,current=lines[-2:]
        else:
            current=lines[0] if lines else ''
            old_lines=wrap_measured(previous.text,max(80,self.width()-80),metrics.horizontalAdvance) if previous else []
            older=old_lines[-1] if old_lines else ''
            if previous and previous.label!=card.label:
                previous_name=previous.label
                if card.label.startswith('Discord · '):previous_name=previous_name.removeprefix('Discord · ')
                prefix=metrics.elidedText(previous_name,Qt.ElideRight,max(40,int((self.width()-80)*.3)))+' · '
                old_lines=wrap_measured(previous.text,max(40,self.width()-80-metrics.horizontalAdvance(prefix)),metrics.horizontalAdvance)
                older=prefix+(old_lines[-1] if old_lines else '')
        self.previous_label.setText(older)
        self.previous_label.setFixedHeight(metrics.height()+4)
        self.label.setText(current)
        self.label.setFixedHeight(metrics.height()+4)
        show_original=bool(profile.get('show_original') and card.original.strip()!=card.text.strip())
        if show_original:
            self.original_label.setText(card.original)
            self.original_label.show()
        else:
            self.original_label.hide()
        if screen:
            g = screen.availableGeometry()
            self.setFixedWidth(min(1000, int(g.width() * .80)))
            height = (metrics.height()+4)*2 + 82
            if show_original:
                height += self.original_label.heightForWidth(self.width() - 70) + 7
            self.setFixedHeight(min(int(g.height() * .45), max(130, height)))
            x = g.x() + (g.width() - self.width()) // 2
            ymode = profile.get("position", "bottom")
            y = (g.y()+80 if ymode == "top" else
                 g.y()+(g.height()-self.height())//2 if ymode == "middle" else
                 g.y()+g.height()-self.height()-65)
            self.move(x, y)
        self.show()
        self.raise_()
        self.timer.start(6000)


class MainWindow(QMainWindow):
    update_result = Signal(object, str)
    pack_result = Signal(str, bool)
    pack_progress = Signal(str)
    plan_result = Signal(str, str, object)  # operation, error, result

    def __init__(self):
        super().__init__()
        self.cfg, self.terms = init_files()
        if not self.cfg.get("profiles"):
            self.cfg["profiles"] = copy.deepcopy(DEFAULT_PROFILES)
        self.profile_idx = min(max(int(self.cfg.get("active_profile", 0)), 0), len(self.cfg["profiles"])-1)
        self.service = VoiceService()
        self.service.live_caption.connect(self.on_live_caption)
        self.display_order = DisplayOrder()
        self.last_live_translation = None
        self.presentation=ReadableCaptions()
        self.caption_timer=QTimer(self)
        self.caption_timer.setInterval(80)
        self.caption_timer.timeout.connect(self.advance_captions)
        self.appearance_save_timer=QTimer(self)
        self.appearance_save_timer.setSingleShot(True)
        self.appearance_save_timer.setInterval(500)
        self.appearance_save_timer.timeout.connect(lambda:write_json(HOME/'settings.json',self.cfg))
        if not isinstance(self.cfg.get('browser_pairing_key'),str) or len(self.cfg['browser_pairing_key'])<20:
            self.cfg['browser_pairing_key']=secrets.token_urlsafe(32)
            write_json(HOME/'settings.json',self.cfg)
        self.browser_bridge=BrowserSourceBridge(self.service.sources,self.cfg['browser_pairing_key'])
        self.browser_bridge.start()
        self.service.status.connect(self.on_status)
        self.service.error.connect(self.on_error)
        self.service.stopped.connect(self.on_stopped)
        self.overlay = SubtitleOverlay()
        self.pending_restart = False
        self.manual_stop = False
        self.last_error = ""
        self.closing = False
        self.update_result.connect(self.on_update_received)
        self.pack_result.connect(self.on_pack_result)
        self.pack_progress.connect(self.on_status)
        self.pack_busy = False
        self.plan = PlanAccount(HOME)
        self.plan_busy = False
        self.last_caption = None
        self.reviewed_translation = ""
        self.review_pin = False  # do not overwrite the phrase under review
        self.plan_result.connect(self.on_plan_result)
        self.setWindowTitle("Universal Voice KR v0.8 · 읽기 편한 실시간 자막")
        self.setMinimumSize(960,620)
        screen=QApplication.primaryScreen()
        available=screen.availableGeometry() if screen else None
        self.resize(min(1180,max(960,available.width()-64)) if available else 1180,
                    min(820,max(620,available.height()-48)) if available else 820)
        self._build_ui()
        self._refresh_profiles()
        self._load_profile()
        self._refresh_terms()
        self._refresh_sources()
        self.update_plan_state()
        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.auto_switch)
        self.scan_timer.start(3000)
        QTimer.singleShot(3000, self.check_scheduled_update)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.check_scheduled_update)
        self.update_timer.start(3600_000)

    def _build_ui(self):
        root = QWidget()
        root.setObjectName('workspace')
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(205)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 28, 16, 18)
        brand = QLabel('voice')
        brand.setObjectName('brand')
        side.addWidget(brand)
        brand_sub = QLabel('UNIVERSAL KR')
        brand_sub.setObjectName('brandSub')
        side.addWidget(brand_sub)
        side.addSpacing(34)
        menu_label = QLabel('워크스페이스')
        menu_label.setObjectName('muted')
        side.addWidget(menu_label)
        self.navigation = QListWidget()
        self.navigation.setObjectName('navigation')
        self.navigation.setSpacing(5)
        labels = ['실시간 자막', '프로필과 자막', 'Discord 연결', '용어 사전',
                  '번역 언어', 'ChatGPT 보정', '장치 진단']
        self.navigation.addItems(labels)
        side.addWidget(self.navigation, 1)
        local_note = QLabel('내 PC에서 음성 처리\n대화는 자동 저장되지 않아요')
        local_note.setObjectName('sideNote')
        side.addWidget(local_note)
        version = QLabel('VERSION 0.8')
        version.setObjectName('version')
        side.addWidget(version)
        outer.addWidget(sidebar)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 26, 30, 16)
        layout.setSpacing(18)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(6)
        self.page_title = QLabel(labels[0])
        self.page_title.setObjectName('pageTitle')
        self.page_description = QLabel('통화에 집중하세요. 대화는 자막으로 확인하세요.')
        self.page_description.setObjectName('muted')
        title_box.addWidget(self.page_title)
        title_box.addWidget(self.page_description)
        header.addLayout(title_box, 1)
        self.connection_badge = QLabel('●  준비됨')
        self.connection_badge.setObjectName('badge')
        header.addWidget(self.connection_badge)
        layout.addLayout(header)
        self.tabs = WorkspacePages()
        self.tabs.setObjectName('pages')
        self.tabs.tabBar().hide()
        layout.addWidget(self.tabs)
        outer.addWidget(content, 1)
        self.tab_live = QWidget()
        self.tab_profile = QWidget()
        self.tab_terms = QWidget()
        self.tabs.addTab(self.tab_live, "실시간 번역")
        self.tabs.addTab(self.tab_profile, "프로필·오버레이")
        self.tab_discord = DiscordSpeakerTab(self.service.timeline, self.cfg,
                                            lambda: write_json(HOME / "settings.json", self.cfg))
        self.tab_discord.subtitles_requested.connect(self.start_without_discord)
        self.tabs.addTab(self.tab_discord, "Discord 닉네임")
        self.tabs.addTab(self.tab_terms, "용어 사전·업데이트")
        self.tab_packs = QWidget()
        self.tabs.addTab(self.tab_packs, "국가별 언어팩")
        self.tab_chatgpt = QWidget()
        self.tabs.addTab(self.tab_chatgpt, "ChatGPT 선택 보정")
        self.tab_cuda = GpuSetupTab()
        self.tabs.addTab(self.tab_cuda, "GPU·CUDA 진단")
        self._build_live()
        self._build_profile()
        self._build_terms()
        self._build_packs()
        self._build_chatgpt()
        # Keep every settings page accessible on smaller laptop displays.
        for index in range(self.tabs.count()):
            page = self.tabs.widget(index)
            page.setProperty('pageContent', True)
            for label in page.findChildren(QLabel):
                label.setWordWrap(True)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            self.tabs.removeTab(index)
            scroll.setWidget(page)
            self.tabs.insertTab(index, scroll, labels[index])
            # Existing actions select a page by its content widget.
            page._scroll_container = scroll
        descriptions = ['통화에 집중하세요. 대화는 자막으로 확인하세요.',
                        '통화 환경에 맞는 음성 모델과 자막 모양을 설정하세요.',
                        '봇 없이, 말하는 사람의 닉네임을 자막에 연결하세요.',
                        '게임 용어와 자주 쓰는 표현을 나만의 사전에 담으세요.',
                        '필요한 언어를 한 번 설치하고 오프라인으로 번역하세요.',
                        '원하는 문장만 선택해서 더 자연스럽게 다듬으세요.',
                        '그래픽 장치와 음성 처리 환경을 확인하세요.']
        def change_page(index):
            if index >= 0:
                self.tabs.setCurrentIndex(index)
                self.page_title.setText(labels[index])
                self.page_description.setText(descriptions[index])
        self.navigation.currentRowChanged.connect(change_page)
        self.tabs.currentChanged.connect(self.navigation.setCurrentRow)
        self.navigation.setCurrentRow(0)
        self.statusBar().showMessage('준비됨 · 출력 장치를 선택하고 자막을 시작하세요')

    def _build_live(self):
        l = QVBoxLayout(self.tab_live)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(14)
        source_box = QGroupBox("대화 소리 / Playback audio")
        sb = QVBoxLayout(source_box)
        self.source = QComboBox()
        self.source.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.source.setMinimumContentsLength(16)
        sources = QHBoxLayout()
        sources.addWidget(self.source, 1)
        refresh = self._button('새로고침', self._refresh_sources)
        refresh.setFixedWidth(112)
        sources.addWidget(refresh)
        sb.addLayout(sources)
        sb.addWidget(paragraph('Discord·YouTube 등의 소리가 재생되는 출력 장치를 선택하세요. 내 마이크는 수집하지 않습니다.'))
        self.source_label=QLineEdit()
        self.source_label.setPlaceholderText('출처 이름 · 비워 두면 자동 / 직접 입력 예: YouTube')
        self.source_label.setMaxLength(60)
        self.source_label.editingFinished.connect(self.update_caption_source)
        sb.addLayout(row(self.source_label,self._button('웹사이트 이름 연결',self.browser_source_setup)))
        self.cb_exclude_own_mic = QCheckBox("내 마이크 제외")
        self.cb_exclude_own_mic.setChecked(True)
        self.cb_exclude_own_mic.setEnabled(False)
        self.cb_exclude_own_mic.hide()
        l.addWidget(source_box)
        self.picker = QComboBox()
        self.picker.currentIndexChanged.connect(self.choose_profile)
        profiles = QHBoxLayout()
        profile_label = QLabel('프로필')
        profile_label.setFixedWidth(65)
        profiles.addWidget(profile_label)
        profiles.addWidget(self.picker, 1)
        profiles.addWidget(paragraph('음성 언어 / Speech'))
        self.live_language = combo(list(LANGUAGES.items()))
        self.live_language.setToolTip('짧은 말의 정확도와 속도를 높이려면 주로 말하는 언어를 선택하세요. 변경은 다음 자막 시작부터 적용됩니다.')
        profiles.addWidget(self.live_language, 1)
        l.addLayout(profiles)
        self.target_language=combo([('한국어','ko'),('English','en'),('Español','es'),
                                   ('Français','fr'),('Deutsch','de'),('日本語','ja'),
                                   ('中文','zh'),('Português','pt')])
        self.target_language.setToolTip('Output language / 표시 언어. 다른 언어로 번역하려면 [번역 언어]에서 해당 방향의 모델을 한 번 설치하세요. 변경은 다음 시작부터 적용됩니다.')
        self.target_language.currentIndexChanged.connect(self.show_pack_state)
        l.addLayout(row(QLabel('표시 언어 / Captions'),self.target_language))
        self.btn_start = self._button("자막 시작 / Start", self.start_service)
        self.btn_start.setObjectName('primaryButton')
        self.btn_start.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn_stop = self._button("중지 / Stop", self.stop_service)
        self.btn_stop.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))
        self.btn_stop.setEnabled(False)
        self.btn_preview = self._button("미리보기 / Preview", self.preview)
        l.addLayout(row(self.btn_start, self.btn_stop, self.btn_preview))
        self.state = QLabel("상태: 대기 중")
        self.state.setObjectName('statusText')
        self.state.setWordWrap(True)
        l.addWidget(self.state)
        caption_header = QHBoxLayout()
        caption_title = QLabel('대화 기록')
        caption_title.setObjectName('sectionTitle')
        caption_header.addWidget(caption_title)
        caption_header.addStretch()
        link = self._button('닉네임 연결 설정', lambda:self.navigation.setCurrentRow(2))
        link.setObjectName('textButton')
        caption_header.addWidget(link)
        l.addLayout(caption_header)
        self.live_text = QLabel('')
        self.live_text.setTextFormat(Qt.PlainText)
        self.live_text.setWordWrap(True)
        self.live_text.setStyleSheet('color:#c3ded7;background:#1b2a2a;border-radius:8px;padding:12px;')
        self.live_text.hide()
        l.addWidget(self.live_text)
        self.history = TranscriptView()
        self.history.setReadOnly(True)
        self.history.setObjectName('transcript')
        self.history.setPlaceholderText('아직 들어온 대화가 없어요.\n\n자막을 시작하면 이곳에 닉네임과 대화 내용이 표시됩니다.')
        self.history.setMinimumHeight(220)
        self.history.document().setMaximumBlockCount(500)
        l.addWidget(self.history, 1)
        footer = QHBoxLayout()
        note = QLabel('PC에서 처리 · 대화 자동 저장 안 함 · 비상업용 번역 모델')
        note.setObjectName('muted')
        footer.addWidget(note, 1)
        save_history=self._button('기록 저장 / Save',self.save_history)
        save_history.setObjectName('textButton')
        save_history.setToolTip('지금 남아 있는 대화 기록의 원문과 번역을 텍스트로 저장합니다. 음성은 저장하지 않습니다.')
        footer.addWidget(save_history)
        review = self._button('최근 문장 다듬기', self.ask_review)
        review.setObjectName('textButton')
        footer.addWidget(review)
        l.addLayout(footer)

    def _build_profile(self):
        l = QVBoxLayout(self.tab_profile)
        l.addLayout(row(self._button("새 프로필", self.add_profile),
                        self._button("현재 프로필 복제", self.clone_profile),
                        self._button("현재 프로필 삭제", self.remove_profile),
                        self._button("설정 저장", self.save_profile)))
        form = QFormLayout()
        self.profile_name = QLineEdit()
        self.model = combo([("large-v3-turbo · 추천", "large-v3-turbo"),
                            ("large-v3 · 정확도 우선 / 부하 큼", "large-v3"),
                            ("중간 · medium", "medium"), ("CPU용 · small", "small"),
                            ("경량 · base", "base"), ("최소 부하 · tiny (오인식 많음)", "tiny")])
        self.device = combo([("자동 · GPU 우선", "auto"), ("NVIDIA GPU", "cuda"), ("CPU", "cpu")])
        self.language = combo(list(LANGUAGES.items()))
        self.live_language.currentIndexChanged.connect(self.language.setCurrentIndex)
        self.language.currentIndexChanged.connect(self.live_language.setCurrentIndex)
        self.translation_context = combo([('게임 대화 · 기본 호출 표현 보정', 'game'), ('일반 대화', 'general')])
        self.asr_hotwords = QLineEdit()
        self.asr_hotwords.setMaxLength(200)
        self.asr_hotwords.setPlaceholderText('선택 사항 · 자주 틀리는 닉네임, 지명, 게임 용어')
        self.asr_hotwords.setToolTip('발음이 비슷한 단어 중 입력한 용어를 알아듣도록 돕습니다. 실제 대화에 나오는 단어만 넣으세요.')
        self.vad = combo([("민감 (작은 소리 감지)", 0), ("조금 민감", 1),
                          ("표준", 2), ("소음 억제 우선", 3)])
        self.beam = combo([("빠르게", 1), ("균형", 3), ("정확하게 · 추천", 5)])
        self.language.setToolTip('한 언어로 대화할 때는 해당 언어를 직접 선택하면 짧은 발화의 언어 오인식을 줄일 수 있습니다.')
        self.font_size = QSpinBox()
        self.font_size.setRange(14, 44)
        self.background_opacity=QSlider(Qt.Horizontal)
        self.background_opacity.setRange(15,80)
        self.opacity_value=QLabel()
        self.background_opacity.valueChanged.connect(lambda value:self.opacity_value.setText(str(value)+'%'))
        self.background_opacity.setValue(42)
        self.background_opacity.valueChanged.connect(self.update_caption_opacity)
        self.position = combo([("아래", "bottom"), ("가운데", "middle"), ("위", "top")])
        self.cb_overlay = QCheckBox("게임 화면 위 자막 표시 (전체 화면 창 모드 권장)")
        self.cb_original = QCheckBox("원문도 함께 표시")
        self.cb_live = QCheckBox("말하는 중에도 자막 표시 · 문장이 끝나면 자동 수정")
        self.cb_auto = QCheckBox("등록한 게임 실행 파일을 감지하면 자동 프로필 전환")
        self.cb_auto.setChecked(bool(self.cfg.get("auto_switch", False)))
        self.exe_names = QLineEdit()
        self.exe_names.setPlaceholderText("예: ArkAscended.exe, Overwatch.exe, League of Legends.exe")
        self.profile_terms = QComboBox()
        self._reload_profile_terms()
        form.addRow("프로필 이름", self.profile_name)
        form.addRow("음성 인식 모델", self.model)
        form.addRow("연산 장치", self.device)
        form.addRow("음성 언어", self.language)
        form.addRow("인식할 이름·용어", self.asr_hotwords)
        form.addRow("번역 문맥", self.translation_context)
        form.addRow("목소리 민감도", self.vad)
        form.addRow("인식 정밀도", self.beam)
        form.addRow("자막 글씨 크기", self.font_size)
        opacity_row=QWidget();opacity_layout=QHBoxLayout(opacity_row);opacity_layout.setContentsMargins(0,0,0,0)
        opacity_layout.addWidget(self.background_opacity,1);opacity_layout.addWidget(self.opacity_value)
        form.addRow('자막 배경 진하기',opacity_row)
        form.addRow("자막 위치", self.position)
        form.addRow(self.cb_overlay)
        form.addRow(self.cb_original)
        form.addRow(self.cb_live)
        form.addRow(self.cb_auto)
        form.addRow("프로필 전용 용어 사전", self.profile_terms)
        form.addRow("프로필 적용 게임(.exe)", self.exe_names)
        l.addLayout(form)
        l.addWidget(paragraph('실시간은 Turbo를, 어려운 발음은 Large와 직접 지정한 음성 언어를 권장합니다.\n변경한 설정은 다음 자막 시작부터 적용됩니다.'))
        l.addStretch()

    def _build_terms(self):
        l = QVBoxLayout(self.tab_terms)
        l.addWidget(paragraph("영어 줄임말을 풀어 음성 인식 문장을 한국어 번역 전에 교정합니다. 오역이 있으면 직접 수정할 수 있어요."))
        self.group = QComboBox()
        self.group.currentIndexChanged.connect(self._refresh_terms_text)
        l.addLayout(row(QLabel("적용 사전:"), self.group,
                        self._button("게임 사전 추가", self.add_group)))
        self.terms_edit = QPlainTextEdit()
        self.terms_edit.setPlaceholderText("줄임말 = 풀어쓴 영어\nrn = right now")
        l.addWidget(self.terms_edit, 1)
        l.addWidget(self._button("현재 사전 저장", self.save_terms))
        g = QGroupBox("업데이트 · 신뢰할 수 있는 공개 JSON 사전 주소만 사용")
        form = QFormLayout(g)
        self.update_url = QLineEdit(self.cfg.get("update", {}).get("url", ""))
        self.update_url.setPlaceholderText("https://example.org/game-terms.json (선택 사항)")
        self.update_schedule = combo([("수동", "manual"), ("매일", "daily"),
                                      ("매주", "weekly"), ("매월(30일)", "monthly")],
                                     self.cfg.get("update", {}).get("schedule", "weekly"))
        form.addRow("업데이트 사전 URL", self.update_url)
        form.addRow("실행 중 확인 주기", self.update_schedule)
        l.addWidget(g)
        l.addLayout(row(self._button("업데이트 설정 저장", self.save_update),
                        self._button("지금 업데이트 확인", self.check_update)))
        l.addWidget(paragraph("업데이트는 앱 실행 시 확인하고 적용 전에 미리보기를 보여줍니다. URL이 없으면 수동 사전만 사용합니다."))
        l.addWidget(paragraph("번역 모델 설치는 왼쪽의 [번역 언어] 메뉴를 이용하세요."))

    def _build_packs(self):
        lay = QVBoxLayout(self.tab_packs)
        lay.addWidget(paragraph("NLLB 공용 번역 모델은 설치 프로그램에서 함께 준비됩니다. / Shared multilingual translation is included in setup."))
        lay.addWidget(paragraph("무료 개인·비상업용 모델(CC-BY-NC-4.0)입니다. 상업용 배포·서비스에는 별도 검토가 필요합니다."))
        lay.addWidget(paragraph("지원하는 언어는 추가 다운로드 없이 번역합니다. 아래에서 음성 언어 → 표시 언어 준비 상태를 확인하세요."))
        g = QGroupBox("언어 선택 · 여러 나라가 같은 언어를 사용하면 모델은 한 번만 설치")
        form = QFormLayout(g)
        self.pack_lang = combo([(f"{name} ({code}) — {countries}", code) for code, (name, countries) in PACK_LANGUAGES.items()])
        form.addRow("언어 / 해당 지역 예시", self.pack_lang)
        self.pack_state = QLabel("선택 언어팩의 설치 여부를 확인할 수 있어요.")
        form.addRow("현재 설치 상태", self.pack_state)
        lay.addWidget(g)
        self.pack_lang.currentIndexChanged.connect(self.show_pack_state)
        self.btn_install_pack = self._button("선택 언어팩 설치 / 번역 모델 받기", self.install_pack)
        self.btn_import_pack = self._button("받아둔 .uvkrpack 파일 가져오기", self.import_pack)
        lay.addWidget(self.btn_install_pack)
        lay.addWidget(self.btn_import_pack)
        lay.addWidget(self._button("설치 상태 확인", self.show_pack_state))
        lay.addWidget(paragraph("설치 설명팩(.uvkrpack)에는 대용량 모델이 들어 있지 않습니다. 파일을 가져오면 공식 Argos 목록에서 모델을 받습니다."))
        lay.addWidget(paragraph("자동 감지 시에도 해당 방향의 번역 모델이 필요합니다. 음성과 표시 언어가 같으면 추가 번역 모델은 필요하지 않습니다."))
        lay.addWidget(paragraph("미지원 언어팩은 실패를 알리며 설치 완료로 표시하지 않습니다."))
        lay.addStretch()

    def _build_chatgpt(self):
        l = QVBoxLayout(self.tab_chatgpt)
        l.addWidget(paragraph("로컬 음성 번역은 기존대로 무료입니다. ChatGPT 연결은 선택 사항입니다."))
        l.addWidget(paragraph("디스코드에 다른 사람이 말할 때 자동 호출하지 않습니다. 반드시 내가 [보정 요청]을 클릭해야 합니다."))
        g = QGroupBox("ChatGPT Plus · 개인용 오픈소스 연동 (별도 API 키 불필요)")
        f = QFormLayout(g)
        self.plan_state = QLabel("연결 확인 중")
        self.model_picker = QComboBox()
        self.model_picker.addItem("로그인 후 모델 가져오기", "")
        f.addRow("계정 연결 상태", self.plan_state)
        f.addRow("보정 AI 모델", self.model_picker)
        l.addWidget(g)
        l.addLayout(row(self._button("Continue with ChatGPT · 로그인", self.login_plan),
                        self._button("모델 목록 새로고침", self.fetch_models),
                        self._button("연결 해제", self.disconnect_plan)))
        l.addLayout(row(self._button("ChatGPT 사용량 설정 열기", self.open_usage),
                        self._button("ChatGPT에서 직접 번역하기", self.manual_chatgpt)))
        l.addWidget(paragraph("최근 음성 원문과 로컬 번역을 아래에서 확인 후 필요한 문장만 직접 보정하세요."))
        self.review_input = QPlainTextEdit()
        self.review_input.setPlaceholderText("아직 음성이 들어오지 않았습니다. 직접 원문을 붙여넣어도 됩니다.")
        self.review_input.setMaximumHeight(85)
        l.addWidget(paragraph("보정 요청할 원문 (필요하면 직접 편집)") )
        l.addWidget(self.review_input)
        l.addWidget(self._button("가장 최근 음성 가져오기", self.pull_latest_caption))
        self.review_local = QPlainTextEdit()
        self.review_local.setMaximumHeight(75)
        l.addWidget(paragraph("현재 로컬 번역 (필요하면 직접 편집)"))
        l.addWidget(self.review_local)
        self.review_lang = QLineEdit("auto")
        self.review_lang.setPlaceholderText("언어 코드, 예: en / ru / es")
        l.addLayout(row(QLabel("원문 언어"), self.review_lang))
        l.addWidget(self._button("선택한 문장 ChatGPT 보정 요청", self.ask_review))
        l.addWidget(paragraph("ChatGPT 보정 결과 · 원문 텍스트만 전송하며 음성 파일이나 마이크 소리는 보내지 않습니다."))
        self.review_result = QPlainTextEdit()
        self.review_result.setPlaceholderText("보정 결과가 여기에 표시됩니다.")
        self.review_result.setMaximumHeight(110)
        l.addWidget(self.review_result)
        l.addLayout(row(self._button("이 문장 번역을 내 PC 사전에 저장", self.save_reviewed_phrase),
                        self._button("보정 자막 미리보기", self.preview_review)))
        l.addWidget(paragraph("사전에 저장된 전체 문장은 동일한 문장이 다시 나올 때 로컬에서 바로 재사용합니다. AI 재학습은 아닙니다."))
        l.addStretch()

    def _plan_worker(self, operation, fn):
        if self.plan_busy:
            self.on_status("이미 ChatGPT 작업이 진행 중입니다.")
            return
        self.plan_busy = True
        self.on_status("ChatGPT: " + operation + " 진행 중")
        def work():
            try:
                obj = fn()
                self.plan_result.emit(operation, "", obj)
            except Exception as e:
                # token/callback never included in error messages by helper.
                self.plan_result.emit(operation, str(e), None)
        threading.Thread(target=work, daemon=True, name="ChatGPT-"+operation).start()

    def update_plan_state(self):
        try:
            rec = self.plan.load()
            if rec and self.plan.is_authorized():
                self.plan_state.setText("연결됨 · " + (rec.get("email") or "ChatGPT 계정"))
            elif rec:
                self.plan_state.setText("로그인됨 · 사용량 공유 승인 필요")
            else:
                self.plan_state.setText("미연결 · 로컬 번역만 사용")
        except AccountError as e:
            self.plan_state.setText("연결 저장소 오류: " + str(e))

    def login_plan(self):
        self._plan_worker("login", lambda: self.plan.login())

    def fetch_models(self):
        self._plan_worker("models", self.plan.list_models)

    def disconnect_plan(self):
        reply = QMessageBox.question(self, "연결 해제", "로컬에 저장된 ChatGPT 로그인 정보를 삭제할까요?\n실제 앱 권한은 ChatGPT 설정에서 별도로 해제할 수 있습니다.",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.plan.disconnect()
            self.model_picker.clear()
            self.model_picker.addItem("로그인 후 모델 가져오기", "")
            self.update_plan_state()

    def open_usage(self):
        webbrowser.open("https://chatgpt.com/#settings/usage")

    def manual_chatgpt(self):
        text = self.review_input.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "안내", "먼저 번역할 문장을 입력해 주세요.")
            return
        p = build_review_prompt(text, self.review_local.toPlainText(), self.review_lang.text())
        QApplication.clipboard().setText(p)
        webbrowser.open("https://chatgpt.com/")
        self.on_status("보정 요청문을 클립보드에 복사했습니다. ChatGPT 대화창에 붙여넣으세요.")

    def pull_latest_caption(self):
        if not self.last_caption:
            self.on_status("아직 받은 음성이 없습니다.")
            return
        original, translated, language = self.last_caption
        self.review_pin = False
        self.review_input.setPlainText(original)
        self.review_local.setPlainText(translated)
        self.review_lang.setText(language)
        self.review_result.clear()

    def ask_review(self):
        original = self.review_input.toPlainText().strip()
        translated = self.review_local.toPlainText().strip()
        language = self.review_lang.text().strip()
        model = self.model_picker.currentData()
        if not original:
            QMessageBox.information(self, "안내", "음성 원문이 없습니다. 원문을 입력하거나 번역을 먼저 실행하세요.")
            return
        try:
            authorized = self.plan.is_authorized()
        except AccountError:
            authorized = False
        if not authorized or not model:
            QMessageBox.information(self, "ChatGPT 연결 필요", "ChatGPT에 로그인해 사용량 공유를 승인하고 모델 목록에서 모델을 선택하세요.\n또는 [ChatGPT에서 직접 번역하기]를 사용하세요.")
            return
        group = self.cfg["profiles"][self.profile_idx].get("glossary_group", "global")
        glossary = merge_glossary(self.terms, group)
        # Only directly user-initiated button clicks invoke this network call.
        self.review_pin = True
        self.review_result.clear()
        self._plan_worker("review", lambda: improve_translation(self.plan, model, original,
                                   translated, language, glossary))

    def on_plan_result(self, operation, error, data):
        self.plan_busy = False
        if error:
            self.on_error("ChatGPT " + operation + ": " + error)
            self.update_plan_state()
            return
        if operation == "login":
            self.update_plan_state()
            self.on_status("ChatGPT 연결 성공 · 사용량 공유 승인됨. 모델 목록을 불러옵니다.")
            self.fetch_models()
        elif operation == "models":
            self.model_picker.clear()
            for display, slug in data:
                self.model_picker.addItem(display, slug)
            if not data:
                self.model_picker.addItem("사용 가능한 모델 없음", "")
            self.on_status(f"ChatGPT에서 사용 가능한 모델 {len(data)}개 확인됨")
        elif operation == "review":
            self.review_result.setPlainText(data)
            self.reviewed_translation = data
            self.on_status("ChatGPT 보정 완료 · 필요하다면 내 PC 사전에 저장하세요")

    def save_reviewed_phrase(self):
        original = self.review_input.toPlainText().strip()
        corrected = self.review_result.toPlainText().strip()
        if not original or not corrected:
            QMessageBox.information(self, "안내", "원문과 보정 번역 결과가 있어야 저장할 수 있습니다.")
            return
        reply = QMessageBox.question(self, "내 PC 사전에 저장", "이 원문과 보정문을 로컬 문장 사전에 저장할까요?\n동일한 문장이 다시 나올 때 사용됩니다.",
                                      QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                remember_phrase(HOME / "phrase_memory.json", original, corrected, self.review_lang.text())
            except ValueError as e:
                QMessageBox.warning(self, "저장 실패", str(e))
                return
            self.on_status("문장 번역을 로컬 사전에 저장했습니다. 번역 엔진 재시작 후 반영됩니다.")

    def preview_review(self):
        result = self.review_result.toPlainText().strip()
        if result:
            self.overlay.show_caption(self.review_input.toPlainText(), result,
                                      self.cfg["profiles"][self.profile_idx])

    @staticmethod
    def _button(text, fn):
        button = QPushButton(text)
        button.clicked.connect(lambda _checked=False: fn())
        return button

    def _refresh_profiles(self):
        self.picker.blockSignals(True)
        self.picker.clear()
        for p in self.cfg["profiles"]:
            self.picker.addItem(p["name"])
        self.picker.setCurrentIndex(self.profile_idx)
        self.picker.blockSignals(False)

    def _load_profile(self):
        p = self.cfg["profiles"][self.profile_idx]
        self.profile_name.setText(p.get("name", "프로필"))
        self.source_label.setText(p.get('source_label',''))
        self.target_language.setCurrentIndex(max(0,self.target_language.findData(p.get('target_language','ko'))))
        self.background_opacity.blockSignals(True)
        self.background_opacity.setValue(int(p.get('background_opacity',42)))
        self.opacity_value.setText(str(self.background_opacity.value())+'%')
        self.background_opacity.blockSignals(False)
        self.asr_hotwords.setText(p.get('asr_hotwords', ''))
        for widget, value in [(self.model, p.get("model", "large-v3-turbo")),
                              (self.device, p.get("device", "auto")),
                              (self.language, p.get("language", "en")),
                              (self.translation_context, p.get('translation_context', 'game' if '디스코드' in p.get('name','') else 'general')),
                              (self.vad, p.get("vad", 2)),
                              (self.beam, p.get("beam_size", 5)),
                              (self.position, p.get("position", "bottom"))]:
            idx = widget.findData(value)
            if idx >= 0:
                widget.setCurrentIndex(idx)
        self.font_size.setValue(int(p.get("font", 26)))
        self.cb_overlay.setChecked(bool(p.get("overlay", True)))
        self.cb_original.setChecked(bool(p.get("show_original", False)))
        self.cb_live.setChecked(bool(p.get('live_preview', True)))
        self.exe_names.setText(", ".join(p.get("game_exes", [])))
        idx = self.profile_terms.findData(p.get("glossary_group", "global"))
        self.profile_terms.setCurrentIndex(max(0, idx))
        dev_idx = self.source.findData(p.get("audio_id", ""))
        if dev_idx < 0 and p.get("audio_id"):
            self.source.addItem("저장된 출력 장치 연결 끊김 · 다시 선택", p["audio_id"])
            dev_idx = self.source.count() - 1
        self.source.setCurrentIndex(max(0, dev_idx))

    def save_profile(self, quiet=False):
        p = self.cfg["profiles"][self.profile_idx]
        p.update({"name": self.profile_name.text().strip() or "새 프로필",
                  "model": self.model.currentData(), "device": self.device.currentData(),
                  "language": self.language.currentData(), "vad": self.vad.currentData(),
                  "translation_context": self.translation_context.currentData(),
                  "beam_size": self.beam.currentData(),
                  "font": self.font_size.value(), "position": self.position.currentData(),
                  "overlay": self.cb_overlay.isChecked(), "show_original": self.cb_original.isChecked(),
                  "live_preview": self.cb_live.isChecked(),
                  "asr_hotwords": self.asr_hotwords.text().strip(),
                  "source_label":self.source_label.text().strip(),
                  "background_opacity":self.background_opacity.value(),
                  "target_language":self.target_language.currentData(),
                  "game_exes": [x.strip() for x in self.exe_names.text().split(",") if x.strip()],
                  "audio_id": self.source.currentData() or "",
                  "glossary_group": self.profile_terms.currentData() or "global"})
        self.cfg["auto_switch"] = self.cb_auto.isChecked()
        self.cfg["active_profile"] = self.profile_idx
        write_json(HOME / "settings.json", self.cfg)
        self._refresh_profiles()
        if not quiet:
            self.on_status("프로필 저장 완료 (번역 중 변경하면 다음 실행부터 적용)")

    def choose_profile(self, index):
        if index < 0 or index == self.profile_idx:
            return
        self.save_profile(quiet=True)
        self.profile_idx = index
        self.cfg["active_profile"] = index
        self._load_profile()
        self._refresh_profiles()
        write_json(HOME / "settings.json", self.cfg)
        if self.service.running:
            self.pending_restart = True
            self.stop_service(manual=False)

    def add_profile(self):
        self.save_profile(quiet=True)
        obj = copy.deepcopy(DEFAULT_PROFILES[0])
        obj["name"] = "새 게임 프로필"
        self.cfg["profiles"].append(obj)
        self.profile_idx = len(self.cfg["profiles"])-1
        self._refresh_profiles(); self._load_profile(); self.save_profile(quiet=True)

    def clone_profile(self):
        self.save_profile(quiet=True)
        obj = copy.deepcopy(self.cfg["profiles"][self.profile_idx])
        obj["name"] += " 복사본"
        self.cfg["profiles"].append(obj)
        self.profile_idx = len(self.cfg["profiles"])-1
        self._refresh_profiles(); self._load_profile(); self.save_profile(quiet=True)

    def remove_profile(self):
        if len(self.cfg["profiles"]) <= 1:
            QMessageBox.information(self, "안내", "프로필 하나는 유지해야 해요.")
            return
        self.cfg["profiles"].pop(self.profile_idx)
        self.profile_idx = 0
        self._refresh_profiles(); self._load_profile(); self.save_profile(quiet=True)

    def _refresh_sources(self):
        previous = self.source.currentData() if self.source.count() else ""
        self.source.clear()
        self.source.addItem("기본 출력 장치 / Default output", "")
        try:
            import soundcard as sc
            for dev in sc.all_microphones(include_loopback=True):
                if not getattr(dev, 'isloopback', False):
                    continue  # Never offer microphones in the live caption UI.
                self.source.addItem(f"스피커 재생 소리: {dev.name}", str(dev.id))
        except Exception as e:
            self.on_status("장치 확인 실패: " + str(e))
        p = self.cfg["profiles"][self.profile_idx]
        keep = previous or p.get("audio_id", "")
        idx = self.source.findData(keep)
        if idx >= 0:
            self.source.setCurrentIndex(idx)

    def start_service(self):
        self.save_profile(quiet=True)
        self.last_error = ""
        self.manual_stop = False
        self.pending_restart = False
        p = self.cfg["profiles"][self.profile_idx]
        self.display_order = DisplayOrder()
        self.last_live_translation = None
        self.presentation=ReadableCaptions()
        self.caption_timer.start()
        self.live_text.hide()
        dic = merge_glossary(self.terms, p.get("glossary_group", "global"))
        self.service.start(p, dic)
        self.overlay.show_caption('', '음성 모델을 준비하고 있어요…', p, '실시간 자막')
        self.overlay.timer.stop()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.state.setText("상태: 엔진 시작 중")

    def start_without_discord(self):
        self.navigation.setCurrentRow(0)
        if not self.service.running:
            self.start_service()

    def stop_service(self, manual=True):
        self.manual_stop = manual
        if manual:
            self.pending_restart = False
        self.service.stop()
        self.btn_stop.setEnabled(False)

    def on_stopped(self):
        self.caption_timer.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.overlay.hide()
        self.live_text.hide()
        self.state.setText("오류: " + self.last_error if self.last_error else "상태: 중지됨")
        self.connection_badge.setText('●  확인 필요' if self.last_error else '●  중지됨')
        if self.closing:
            QTimer.singleShot(0, self.close)
            return
        if self.pending_restart and not self.manual_stop:
            self.pending_restart = False
            QTimer.singleShot(400, self.start_service)

    def on_status(self, message):
        self.state.setText("상태: " + message)
        self.statusBar().showMessage(message)
        if self.service.running:
            self.connection_badge.setText('●  처리 중')
            if message.startswith('출력 소리 수집 중:'):
                self.overlay.show_caption('', '듣는 중…', self.cfg['profiles'][self.profile_idx], '실시간 자막')
                self.overlay.timer.stop()

    def on_error(self, message):
        self.last_error = message
        self.state.setText("오류: " + message)
        self.history.appendPlainText("[오류] " + message)
        self.statusBar().showMessage(message)
        self.connection_badge.setText('●  확인 필요')

    def on_live_caption(self, update):
        profile=self.cfg['profiles'][self.profile_idx]
        label=clean_caption_label(update.speaker,update.source,profile.get('source_label',''))
        if self.presentation.offer(update,label):self.render_captions()
        if not self.closing:self.caption_timer.start()
        if update.final and update.complete:
            self.on_caption(update.original, update.translated, update.language,
                            label, show_overlay=False)

    def advance_captions(self):
        if self.presentation.advance():self.render_captions()

    def update_caption_opacity(self,value):
        self.cfg['profiles'][self.profile_idx]['background_opacity']=value
        self.appearance_save_timer.start()
        if self.presentation.current:self.render_captions()

    def update_caption_source(self):
        self.cfg['profiles'][self.profile_idx]['source_label']=self.source_label.text().strip()
        self.appearance_save_timer.start()

    def render_captions(self):
        current,previous=self.presentation.current,self.presentation.previous
        if current is None:return
        lines=[current.label]
        if previous:lines.append(previous.text)
        lines.append(current.text)
        self.live_text.setText('\n'.join(lines));self.live_text.show()
        self.overlay.show_readable(current,previous,self.cfg['profiles'][self.profile_idx])
        if self.service.running:self.overlay.timer.stop()

    def browser_source_setup(self):
        dialog=QDialog(self);dialog.setWindowTitle('웹사이트 이름 자동 표시');dialog.resize(550,340)
        layout=QVBoxLayout(dialog)
        text=QLabel('Chrome·Edge에서 소리가 나는 탭의 사이트 이름을 연결합니다.\n\n'
                    '1. 아래 버튼으로 확장 폴더를 엽니다.\n'
                    '2. 브라우저의 확장 관리에서 개발자 모드를 켜고\n   압축 해제된 확장 로드로 이 폴더를 선택합니다.\n'
                    '3. 확장 아이콘을 눌러 아래 연결 코드를 입력합니다.\n\n'
                    '재생 중인 탭의 도메인만 PC에 전달합니다. 대화나 페이지 내용은 보내지 않습니다.')
        text.setWordWrap(True);layout.addWidget(text)
        code=QLineEdit(self.cfg['browser_pairing_key']);code.setReadOnly(True);layout.addWidget(code)
        folder=Path(__file__).with_name('browser_source_extension')
        layout.addLayout(row(self._button('확장 폴더 열기',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))),
                             self._button('연결 코드 복사',lambda:QApplication.clipboard().setText(code.text()))))
        if self.browser_bridge.error:layout.addWidget(paragraph(self.browser_bridge.error))
        dialog.exec()

    def on_caption(self, original, translated, language, speaker="화자 미확인", show_overlay=True):
        self.last_caption = (original, translated, language)
        if not self.plan_busy and not self.review_pin and not self.review_input.hasFocus():
            self.review_input.setPlainText(original)
            self.review_local.setPlainText(translated)
            self.review_lang.setText(language)
            self.review_result.clear()
        current = datetime.now().strftime("%H:%M:%S")
        self.history.append_caption(speaker, translated, original, current, language)
        if show_overlay:
            self.overlay.show_caption(original, translated, self.cfg["profiles"][self.profile_idx], speaker)

    def save_history(self):
        if not self.history.toPlainText().strip():
            self.on_status('저장할 대화 기록이 없습니다. / No captions to save.');return
        folder=Path(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation))
        suggested=folder/('VoiceKR_'+datetime.now().strftime('%Y%m%d_%H%M')+'.txt')
        filename,_=QFileDialog.getSaveFileName(self,'대화 기록 저장 / Save captions',str(suggested),'Text files (*.txt)')
        if not filename:return
        try:
            Path(filename).write_text(self.history.toPlainText()+'\n',encoding='utf-8-sig')
            self.on_status('화면의 대화 기록을 저장했습니다. 음성 파일은 저장하지 않습니다.')
        except OSError as error:
            QMessageBox.warning(self,'기록 저장 실패',str(error))

    def preview(self):
        self.save_profile(quiet=True)
        self.overlay.show_caption("They're pushing our base!",
                                  "적들이 우리 기지로 밀고 들어오고 있어!",
                                  self.cfg["profiles"][self.profile_idx])

    def auto_switch(self):
        if not self.cfg.get("auto_switch"):
            return
        try:
            import psutil
            names = {str(p.info.get("name") or "").casefold() for p in psutil.process_iter(["name"])}
            matched = next(((idx, p) for idx, p in enumerate(self.cfg["profiles"])
                            if any(exe.casefold() in names for exe in p.get("game_exes", []))), None)
            if matched and matched[0] != self.profile_idx:
                idx, profile = matched
                self.picker.setCurrentIndex(idx)
                self.on_status(f"게임 감지 · {profile['name']} 프로필 전환")
        except Exception:
            pass

    def _refresh_terms(self):
        selected = self.cfg.get("glossary_group", "global")
        self.group.blockSignals(True)
        self.group.clear()
        self.group.addItem("공통 신조어", "global")
        for name in self.terms.get("games", {}):
            self.group.addItem(name, name)
        idx = self.group.findData(selected)
        self.group.setCurrentIndex(max(0, idx))
        self.group.blockSignals(False)
        self._refresh_terms_text()

    def _refresh_terms_text(self):
        group = self.group.currentData()
        if group is None:
            return
        data = (self.terms.get("global", {}) if group == "global" else
                self.terms.get("games", {}).get(group, {}))
        self.terms_edit.setPlainText("\n".join(f"{k} = {v}" for k, v in data.items()))
        self.cfg["glossary_group"] = group

    def _reload_profile_terms(self):
        if not hasattr(self, "profile_terms"):
            return
        previous = self.profile_terms.currentData()
        self.profile_terms.clear()
        self.profile_terms.addItem("공통 사전만", "global")
        for name in self.terms.get("games", {}):
            self.profile_terms.addItem(name + " + 공통", name)
        idx = self.profile_terms.findData(previous)
        self.profile_terms.setCurrentIndex(max(0, idx))

    def save_terms(self):
        group = self.group.currentData()
        data = {}
        for lineno, line in enumerate(self.terms_edit.toPlainText().splitlines(), 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if "=" not in line:
                QMessageBox.warning(self, "형식 오류", f"{lineno}번째 줄: 단어 = 풀어쓴 영어 형식으로 입력하세요.")
                return
            key, value = [s.strip() for s in line.split("=", 1)]
            if not key or not value or len(key) > 80 or len(value) > 240:
                QMessageBox.warning(self, "형식 오류", f"{lineno}번째 줄을 확인해 주세요.")
                return
            data[key] = value
        if group == "global":
            self.terms["global"] = data
        else:
            self.terms.setdefault("games", {})[group] = data
        write_json(HOME / "glossary.json", self.terms)
        write_json(HOME / "settings.json", self.cfg)
        self.on_status("사전 저장됨 · 재시작 시 번역 엔진에 반영")

    def add_group(self):
        name, ok = QInputDialog.getText(self, "새 게임 용어 사전", "게임 / 장르 이름을 입력하세요")
        if ok and name.strip():
            name = name.strip()[:48]
            self.terms.setdefault("games", {}).setdefault(name, {})
            self.cfg["glossary_group"] = name
            self._reload_profile_terms()
            write_json(HOME / "glossary.json", self.terms)
            self._refresh_terms()

    def save_update(self):
        self.cfg.setdefault("update", {}).update({"url": self.update_url.text().strip(),
                                                    "schedule": self.update_schedule.currentData()})
        write_json(HOME / "settings.json", self.cfg)
        self.on_status("사전 업데이트 설정 저장됨")

    def check_scheduled_update(self):
        if update_due(self.cfg.get("update", {})):
            self.check_update()

    def check_update(self):
        self.save_update()
        url = self.cfg["update"].get("url", "")
        if not url:
            QMessageBox.information(self, "사전 URL 필요", "업데이트 주소를 등록하지 않았어요. 기본 사전은 로컬에서 계속 사용됩니다.")
            return
        if not url.startswith("https://"):
            QMessageBox.warning(self, "주소 오류", "HTTPS 주소만 허용합니다.")
            return
        self.on_status("온라인 사전 변경 사항 확인 중")
        def work():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "UniversalVoiceKR/0.1"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if not resp.url.startswith("https://"):
                        raise ValueError("HTTPS가 아닌 위치로 이동하여 차단함")
                    raw = resp.read(256001)
                if len(raw) > 256000:
                    raise ValueError("사전 파일 256KB 제한 초과")
                obj = json.loads(raw.decode("utf-8"))
                if not valid_remote_dictionary(obj):
                    raise ValueError("사전 JSON 구조가 올바르지 않음")
                self.update_result.emit(obj, "")
            except Exception as e:
                self.update_result.emit(None, str(e))
        threading.Thread(target=work, daemon=True).start()

    def on_update_received(self, incoming, error):
        if error:
            self.on_error("사전 업데이트: " + error)
            return
        self.cfg["update"]["last_checked"] = datetime.now().timestamp()
        write_json(HOME / "settings.json", self.cfg)
        new_entries = []
        for group_name, pack in [("global", incoming.get("global", {}))] + list(incoming.get("games", {}).items()):
            original = self.terms.get("global", {}) if group_name == "global" else self.terms.get("games", {}).get(group_name, {})
            for k,v in pack.items():
                if k not in original:
                    new_entries.append((group_name, k, v))
        if not new_entries:
            self.on_status("새 사전 항목 없음 · 사용자 수정 내용 유지")
            return
        sample = "\n".join(f"{g}: {k} = {v}" for g,k,v in new_entries[:8])
        reply = QMessageBox.question(self, "사전 업데이트 미리보기",
            f"새로운 단어 {len(new_entries)}개 발견. 기존 번역은 덮어쓰지 않습니다.\n\n{sample}\n\n추가할까요?",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            for g,k,v in new_entries:
                target = self.terms.setdefault("global", {}) if g == "global" else self.terms.setdefault("games", {}).setdefault(g, {})
                target[k] = v
            write_json(HOME / "glossary.json", self.terms)
            self._refresh_terms()
            self._reload_profile_terms()
            self.on_status(f"새 사전 단어 {len(new_entries)}개 추가됨")

    def show_pack_state(self, *_):
        if not hasattr(self, "pack_state"):
            return
        lang = self.pack_lang.currentData()
        target=self.target_language.currentData()
        if not lang or self.pack_busy:
            return
        try:
            ok = installed_for_language(lang,target)
            if lang == target or (lang=='pb' and target=='pt'):
                self.pack_state.setText("원문 자막 / Original captions · 추가 번역 모델 불필요")
            else:
                self.pack_state.setText(f"{lang} → {target} : " +
                                        ("번역 모델 설치됨 · 오프라인 사용 가능" if ok else "번역 모델 미설치 · 최초 다운로드 필요"))
        except Exception as e:
            self.pack_state.setText("상태 확인 불가: " + str(e))

    def install_pack(self, manifest=None):
        if self.pack_busy:
            self.on_status("다른 언어팩이 설치 중입니다")
            return
        if not isinstance(manifest, dict):
            manifest = create_manifest(self.pack_lang.currentData(),self.target_language.currentData())
        code = manifest["code"]
        target=manifest['translation_target']
        if code == target or (code=='pb' and target=='pt'):
            try:
                save_terms_without_overwrite(manifest, HOME)
                self.on_pack_result("원문 자막 준비 완료 · Whisper 모델을 그대로 사용합니다", True)
            except Exception as e:
                self.on_pack_result("언어팩 적용 오류: " + str(e), False)
            return
        reply = QMessageBox.question(
            self, "언어팩 다운로드 확인",
            f"{manifest['language']} ({code}) → {target} 번역 모델을 설치할까요?\n\n"
            "실제 AI 모델은 이 작은 설명팩에 포함되지 않습니다.\n"
            "최초 설치에는 인터넷 연결과 디스크 공간이 필요합니다.\n"
            "설치 완료 후에는 로컬 PC에서 번역합니다.",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.pack_busy = True
        self.btn_install_pack.setEnabled(False)
        self.btn_import_pack.setEnabled(False)
        self.pack_state.setText(f"{manifest['language']} 모델 설치 중…")
        self.on_status(f"{code} → {target} 번역 모델 다운로드 시작")

        def work():
            try:
                installed_edges = install_translation_models(code, self.pack_progress.emit,target)
                save_terms_without_overwrite(manifest, HOME)
                desc = ", ".join(f"{a}→{b}" for a,b in installed_edges) or "이미 설치됨"
                self.pack_result.emit(f"{manifest['language']} 설치 확인 완료 ({desc})", True)
            except Exception as e:
                self.pack_result.emit(f"{manifest['language']}: {e}", False)
        threading.Thread(target=work, daemon=True, name=f"pack-{code}").start()

    def import_pack(self):
        if self.pack_busy:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "받아둔 언어팩 선택", "", "Universal Voice 언어팩 (*.uvkrpack)")
        if not filename:
            return
        try:
            manifest = read_pack(__import__("pathlib").Path(filename))
        except Exception as e:
            QMessageBox.warning(self, "언어팩 형식 오류", str(e))
            return
        idx = self.pack_lang.findData(manifest["code"])
        if idx >= 0:
            self.pack_lang.setCurrentIndex(idx)
        self.install_pack(manifest)

    def on_pack_result(self, message, ok):
        self.pack_busy = False
        self.btn_install_pack.setEnabled(True)
        self.btn_import_pack.setEnabled(True)
        self.on_status(message if ok else "언어팩 설치 실패: " + message)
        if not ok:
            QMessageBox.warning(self, "언어팩 설치 실패", message)
        self.show_pack_state()

    def closeEvent(self, event):
        if self.appearance_save_timer.isActive():
            self.appearance_save_timer.stop()
            write_json(HOME/'settings.json',self.cfg)
        if self.service.running:
            self.closing = True
            self.scan_timer.stop()
            self.update_timer.stop()
            self.stop_service()
            self.overlay.hide()
            self.setEnabled(False)
            event.ignore()
            return
        self.tab_discord.disconnect_widget()
        self.caption_timer.stop()
        self.browser_bridge.close()
        self.stop_service()
        self.overlay.hide()
        super().closeEvent(event)


STYLESHEET = """
QWidget {color: #e9edf5; font-family: 'Malgun Gothic'; font-size: 13px;}
QMainWindow, QWidget#workspace {background: #11151c;}
QFrame#sidebar {background: #0c1016; border-right: 1px solid #242c38;}
QLabel {background: transparent;}
QLabel#brand {color: #78e4c1; font-size: 36px; font-weight: 800;}
QLabel#brandSub {color: #9ca9ba; font-size: 10px; letter-spacing: 3px;}
QLabel#sideNote {color: #8c99ab; font-size: 11px; line-height: 150%; padding: 12px 0;}
QLabel#version {color: #66758a; font-size: 10px; padding-top: 6px;}
QLabel#pageTitle {font-size: 26px; font-weight: 700; color: #f4f6fb;}
QLabel#muted {color: #95a3b7; font-size: 12px;}
QLabel#badge {background: #18332d; color: #8ae4c7; border: 1px solid #285043; border-radius: 15px; padding: 7px 14px; font-size: 11px;}
QLabel#sectionTitle {font-size: 15px; font-weight: 600;}
QLabel#statusText {color: #98abc2; font-size: 12px; padding: 3px 1px;}
QListWidget#navigation {background: transparent; border: none; outline: none;}
QListWidget#navigation::item {color: #9aa8bc; padding: 13px 14px; border-radius: 8px;}
QListWidget#navigation::item:selected {background: #1a302e; color: #92ecd1; font-weight: 600;}
QListWidget#navigation::item:hover:!selected {background: #18202c; color: #e8edf5;}
QTabWidget#pages::pane {border: none; background: transparent;}
QScrollArea {border: none; background: transparent;}
QScrollArea > QWidget > QWidget {background: #11151c;}
QGroupBox {background: #171d27; border: 1px solid #2b3443; border-radius: 11px; margin-top: 14px; padding: 18px 14px 12px; font-weight: 600;}
QGroupBox::title {subcontrol-origin: margin; subcontrol-position: top left; left: 16px; top: 2px; color: #cdd7e6; padding: 0 6px;}
QPushButton {background: #202938; color: #dae2ee; border: 1px solid #354154; border-radius: 8px; padding: 9px 14px; min-height: 20px; font-weight: 600;}
QPushButton:hover {background: #2b374a; border-color: #54657c;}
QPushButton:pressed {background: #151e2c;}
QPushButton:disabled {background: #171e29; color: #59687b; border-color: #273142;}
QPushButton#primaryButton {background: #79e3c0; color: #09251e; border-color: #79e3c0;}
QPushButton#primaryButton:hover {background: #9cefd5;}
QPushButton#primaryButton:disabled {background: #253f3a; color: #6b968a; border-color: #253f3a;}
QPushButton#textButton {background: transparent; color: #9db3ce; border: none; padding: 5px 8px; font-size: 12px;}
QPushButton#textButton:hover {background: #202b39; color: #c4f7e6;}
QComboBox, QLineEdit, QSpinBox, QPlainTextEdit {background: #141b26; color: #e4eaf5; border: 1px solid #303d50; padding: 9px 11px; border-radius: 8px; selection-background-color: #365f61;}
QComboBox {min-height: 20px; padding-right: 24px;}
QComboBox::drop-down {border: none; width: 22px;}
QComboBox QAbstractItemView {background: #1a2331; selection-background-color: #29473f; padding: 5px;}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {border-color: #6bc9ac;}
QTextEdit#transcript {background: #151c27; font-size: 14px; border: 1px solid #2e3b4d; border-radius: 10px; padding: 16px;}
QCheckBox {padding: 7px 0; spacing: 9px;}
QStatusBar {background: #0e131b; color: #8798ae; font-size: 11px; padding: 3px 12px; border-top: 1px solid #26303d;}
QScrollBar:vertical {background: #10151e; width: 8px; margin: 0;}
QScrollBar::handle:vertical {background: #364358; border-radius: 4px; min-height: 28px;}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height: 0;}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {background: transparent;}
QMessageBox, QInputDialog, QFileDialog {background: #171e29;}
QToolTip {background: #273247; color: #f4f6fb; border: 1px solid #52647c; padding: 6px;}
"""


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Universal Voice KR")
    from single_instance import SingleInstance
    instance=SingleInstance(HOME,app)
    if not instance.acquire():
        return
    app.aboutToQuit.connect(instance.close)
    icon_path = Path(__file__).with_name('voice.ico')
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setStyleSheet(STYLESHEET)
    win = MainWindow()
    def activate_window():
        win.showNormal();win.raise_();win.activateWindow()
    instance.activated.connect(activate_window)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
