"""CUDA 12/cuDNN 9 runtime resolver for faster-whisper on Windows.

No downloads, PATH mutations or admin rights at import time. NVIDIA wheels are
optional, user-installed in the app's existing Python environment.
"""
from __future__ import annotations
import ctypes
import importlib.metadata as metadata
import os
from pathlib import Path
import site
import subprocess
import sys
import sysconfig

_DLL_HANDLES = []
_DLL_DIRS = []
_DLL_LIBS = []


def _roots():
    paths = [sysconfig.get_paths().get('purelib'), sysconfig.get_paths().get('platlib')]
    try:
        paths += site.getsitepackages()
    except Exception:
        pass
    try:
        paths.append(site.getusersitepackages())
    except Exception:
        pass
    return [Path(p) for p in dict.fromkeys(str(p) for p in paths if p)]


def bundled_dll_dirs():
    """Only register directories owned by a Python NVIDIA wheel; no arbitrary PATH scans."""
    candidates = []
    for root in _roots():
        for path in ('nvidia/cublas/bin', 'nvidia/cudnn/bin', 'nvidia/cuda_nvrtc/bin',
                     'nvidia/cuda_runtime/bin'):
            folder = root / path
            if folder.is_dir() and any(folder.glob('*.dll')):
                candidates.append(folder)
    return list(dict.fromkeys(candidates))


def prepare_cuda():
    """Add DLL directories for this process before importing CTranslate2/Whisper."""
    if os.name != 'nt':
        return []
    out = []
    directories = bundled_dll_dirs()
    # CTranslate2/cuDNN use native LoadLibrary for lazy inference dependencies.
    # Python's add_dll_directory alone does not cover those calls on Windows.
    # Restrict the process-local search path to our installed NVIDIA wheels.
    existing = os.environ.get('PATH', '').split(os.pathsep)
    additions = [str(p) for p in directories if str(p).casefold() not in
                 {s.casefold() for s in existing}]
    if additions:
        os.environ['PATH'] = os.pathsep.join(additions + existing)
    for directory in directories:
        key = str(directory.resolve()).casefold()
        if key in _DLL_DIRS:
            continue
        handle = os.add_dll_directory(str(directory))
        _DLL_HANDLES.append(handle)  # keep alive until process exit
        _DLL_DIRS.append(key)
        out.append(str(directory))
        for name in ('cublasLt64_12.dll', 'cublas64_12.dll', 'cudnn64_9.dll'):
            library = directory / name
            if library.is_file():
                _DLL_LIBS.append(ctypes.WinDLL(str(library)))
    return out


def wheel_version(package):
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return '미설치'


def gpu_report():
    lines = ['=== Universal Voice KR / CUDA 진단 ===',
             'Python: ' + sys.version.split()[0],
             '실행 환경: ' + sys.executable]
    try:
        p = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,driver_version',
                            '--format=csv,noheader'], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=12)
        lines.append('NVIDIA GPU: ' + (p.stdout.strip() if p.returncode == 0 else
                       '조회 실패 (드라이버/전원/GPU 상태 점검)'))
    except (OSError, subprocess.TimeoutExpired):
        lines.append('NVIDIA GPU: nvidia-smi 실행 불가 (드라이버 점검)')
    for name in ('faster-whisper', 'ctranslate2', 'nvidia-cublas-cu12',
                 'nvidia-cudnn-cu12', 'nvidia-cuda-nvrtc-cu12'):
        lines.append(name + ': ' + wheel_version(name))
    try:
        paths = prepare_cuda()
        lines.append('발견한 NVIDIA DLL 경로: ' + (', '.join(paths) if paths else
                      '없음 또는 이미 적용됨'))
        if os.name == 'nt':
            for name in ('cublas64_12.dll', 'cudnn64_9.dll'):
                try:
                    ctypes.WinDLL(name)
                    lines.append(name + ': 불러오기 성공')
                except OSError:
                    lines.append(name + ': 불러오기 실패 (필수 DLL/의존성 확인)')
        import ctranslate2
        count = ctranslate2.get_cuda_device_count()
        lines.append('CTranslate2 CUDA 장치 수: ' + str(count))
        if count:
            lines.append('지원 연산 타입: ' + ', '.join(sorted(ctranslate2.get_supported_compute_types('cuda'))))
            lines.append('참고: 실제 Whisper 모델 로딩·추론은 별도 확인 필요')
    except Exception as e:
        lines.append('CTranslate2 CUDA 점검 실패: ' + type(e).__name__ + ': ' + str(e)[:350])
    return '\n'.join(lines)


def cuda_packages():
    """Pinned to published Windows wheels, CUDA 12 + cuDNN 9 pairing."""
    return ['nvidia-cublas-cu12==12.9.2.10', 'nvidia-cudnn-cu12==9.22.0.52',
            'nvidia-cuda-nvrtc-cu12']
