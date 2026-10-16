"""Regression checks for short-click rejection, short calls, PT-BR, and lifecycle."""
import sys, types, threading, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

try:
    import PySide6.QtCore
except ImportError:
    # Run offline in Linux review sandbox; Windows release installs PySide6.
    fake=types.ModuleType('PySide6'); q=types.ModuleType('PySide6.QtCore')
    class QObject: pass
    class Signal:
        def __init__(self,*a): self.callbacks=[]
        def connect(self, fn): self.callbacks.append(fn)
        def emit(self, *args):
            for fn in self.callbacks: fn(*args)
    q.QObject=QObject; q.Signal=Signal
    sys.modules['PySide6']=fake; sys.modules['PySide6.QtCore']=q

from engine import Segmenter, VoiceService
from language_packs import find_route

class RegressionTests(unittest.TestCase):
    def run_timeline(self,blocks):
        seg=Segmenter(level=2)
        # Artificial speech oracle, avoiding assumption that sine waves are speech.
        seg.vad.is_speech=lambda frame, rate: frame != bytes(len(frame))
        completed=[]
        for voiced,frames in blocks:
            for _ in range(frames):
                completed+=seg.push(np.full(320,.30 if voiced else 0,dtype=np.float32))
        return completed
    def test_tiny_20ms_noise_not_a_caption(self):
        self.assertEqual(self.run_timeline([(True,1),(False,35)]),[])
    def test_fast_200ms_game_call_preserved(self):
        self.assertEqual(len(self.run_timeline([(True,10),(False,35)])),1)
    def test_long_speech_split_at_eight_seconds(self):
        self.assertEqual(len(self.run_timeline([(True,450),(False,35)])),2)
    def test_brazilian_portuguese_translates_with_standard_pt_model(self):
        self.assertEqual(find_route('pb', set(),{('pt','en'),('en','ko')}),[('pt','en'),('en','ko')])
        self.assertEqual(find_route('pb',{('pt','en'),('en','ko')},set()),[])
    def test_workers_both_must_exit_before_saying_stopped(self):
        svc=VoiceService(); svc._workers_remaining=2; svc.running=True
        evt=threading.Event(); calls=[]
        svc.stopped.connect(lambda: calls.append('stopped'))
        svc._worker_finished(evt)
        self.assertTrue(svc.running)
        self.assertEqual(calls,[])
        svc._worker_finished(evt)
        self.assertFalse(svc.running)
        self.assertEqual(calls,['stopped'])

if __name__=='__main__': unittest.main()
