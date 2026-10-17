"""Opt-in GPU / CUDA diagnostics and NVIDIA runtime wheel installer UI."""
from __future__ import annotations
import subprocess
import sys
import threading
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPushButton,
                               QPlainTextEdit, QMessageBox)
from cuda_runtime import gpu_report, cuda_packages
from localized_widgets import QLabel,QPushButton,QMessageBox
from ui_i18n import translate as ui


class GpuSetupTab(QWidget):
    line = Signal(str)
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.working = False
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('GPU/CUDA 점검 · RTX 4050 노트북 지원 (CUDA 12 + cuDNN 9)'))
        layout.addWidget(QLabel('검사는 무료이며 드라이버나 시스템 설정을 변경하지 않습니다.'))
        layout.addWidget(QLabel('CUDA 라이브러리 설치는 선택 사항이며 약 1GB 이상의 다운로드가 발생할 수 있습니다.'))
        self.scan = QPushButton('1. NVIDIA GPU 및 CUDA 상태 진단')
        self.scan.clicked.connect(self.check)
        layout.addWidget(self.scan)
        self.install = QPushButton('2. CUDA 12 + cuDNN 9 런타임 설치 (선택)')
        self.install.clicked.connect(self.ask_install)
        layout.addWidget(self.install)
        layout.addWidget(QLabel('설치 후 프로그램을 재시작하고 프로필·오버레이 → 연산 장치에서 NVIDIA GPU를 선택하세요.'))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)
        self.line.connect(lambda text:self.log.appendPlainText(ui(text)))
        self.finished.connect(self.on_finished)

    def _set_busy(self, value):
        self.working = value
        self.scan.setEnabled(not value)
        self.install.setEnabled(not value)

    def check(self):
        if self.working:
            return
        self._set_busy(True)
        self.line.emit('진단 시작 ...')
        threading.Thread(target=self._run_scan, daemon=True).start()

    def _run_scan(self):
        try:
            self.line.emit(gpu_report())
        except Exception as exc:
            self.line.emit('진단 실패: ' + str(exc)[:350])
        finally:
            self.finished.emit()

    def ask_install(self):
        if self.working:
            return
        answer = QMessageBox.question(
            self, 'CUDA 런타임 설치 확인',
            'NVIDIA 공식 패키지 저장소(PyPI)의 CUDA 12/cuDNN 9 구성요소를 '
            '번역기 Python 환경에 설치합니다. 대용량 다운로드가 발생할 수 있습니다.\n\n'
            '기존 게임/그래픽 드라이버는 변경하지 않습니다. 계속할까요?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self._set_busy(True)
        self.line.emit('CUDA 라이브러리 설치 시작 · 다운로드 중 ...')
        threading.Thread(target=self._run_install, daemon=True).start()

    def _run_install(self):
        try:
            cmd = [sys.executable, '-m', 'pip', 'install', '--only-binary=:all:', *cuda_packages()]
            self.line.emit('설치 대상: ' + ', '.join(cuda_packages()))
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding='utf-8', errors='replace', bufsize=1)
            assert proc.stdout is not None
            for line in proc.stdout:
                self.line.emit(line.rstrip()[:900])
            ret = proc.wait()
            if ret == 0:
                self.line.emit('설치 완료. 프로그램 재시작 후 GPU 진단을 다시 실행하세요.')
            else:
                self.line.emit('설치 실패 (종료 코드 %d). 인터넷/용량/드라이버 상태를 확인하세요.' % ret)
        except Exception as exc:
            self.line.emit('CUDA 설치 시작 실패: ' + str(exc)[:500])
        finally:
            self.finished.emit()

    def on_finished(self):
        self._set_busy(False)
