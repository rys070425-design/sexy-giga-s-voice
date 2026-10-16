import json
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from audio_sources import SourceTracker
from source_bridge import BrowserSourceBridge

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tracker=SourceTracker();self.bridge=BrowserSourceBridge(self.tracker,'test-pairing-code-long-enough',0)
        self.assertTrue(self.bridge.start())
        self.url='http://127.0.0.1:'+str(self.bridge.server.server_address[1])+'/source'
    def tearDown(self):self.bridge.close()
    def request(self,key='test-pairing-code-long-enough',origin='chrome-extension://test',hosts=None):
        data=json.dumps({'browser':'chrome','hosts':hosts if hosts is not None else ['www.youtube.com']}).encode()
        request=Request(self.url,data=data,headers={'Authorization':'Bearer '+key,'Origin':origin,'Content-Type':'application/json'})
        with urlopen(request,timeout=2) as response:return response.status
    def test_paired_browser_updates_site(self):
        self.assertEqual(self.request(),200)
        self.assertEqual(self.tracker.web['chrome'][1],('YouTube',))
    def test_wrong_code_is_rejected(self):
        with self.assertRaises(HTTPError) as error:self.request(key='wrong')
        self.assertEqual(error.exception.code,401)
    def test_regular_web_page_cannot_submit_source(self):
        with self.assertRaises(HTTPError) as error:self.request(origin='https://example.com')
        self.assertEqual(error.exception.code,403)
    def test_invalid_payload_is_rejected(self):
        with self.assertRaises(HTTPError) as error:self.request(hosts='not-a-list')
        self.assertEqual(error.exception.code,400)
