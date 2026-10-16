import json
import sys
import tempfile
import unittest
import io
from unittest.mock import patch
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import remember_phrase, read_phrase_memory, normalized_phrase
from chatgpt_plan import (AccountError, SCOPE, build_authorize_params,
                          verify_callback, build_review_prompt, collect_response_events,
                          PlanAccount)


class ChatGPTPlanTests(unittest.TestCase):
    def test_login_ignores_favicon_and_wrong_state_before_callback(self):
        import chatgpt_plan as module
        from urllib.parse import parse_qs, urlencode, urlsplit
        class FakeServer:
            server_port = 15011
            calls = 0
            def __init__(self, address, handler):
                self.handler=handler
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def handle_request(self):
                self.calls+=1
                h=self.handler.__new__(self.handler)
                h.path=paths.pop(0)
                h.send_error=lambda *args:None
                h.send_response=lambda *args:None
                h.send_header=lambda *args:None
                h.end_headers=lambda:None
                h.wfile=io.BytesIO()
                h.do_GET()
        paths=[]
        def open_browser(url):
            state=parse_qs(urlsplit(url).query)['state'][0]
            paths.extend(['/favicon.ico', '/auth/callback?state=wrong',
                          '/auth/callback?'+urlencode(dict(state=state,code='test-code',client_id='oaiapp_test'))])
            return True
        account=PlanAccount(Path('unused'))
        with patch.object(account,'load',return_value=None), patch.object(account,'host_id',return_value='urn:uuid:test'), \
             patch.object(account,'save') as save, patch.object(module,'HTTPServer',FakeServer), \
             patch.object(module.webbrowser,'open',side_effect=open_browser), \
             patch.object(module,'_token_exchange',return_value=dict(id_token='dummy',access_token='dummy',scope='chatgpt.tokens.use.direct')), \
             patch.object(module,'_decode_id_token',return_value=dict(sub='test',email='test@example.invalid')):
            self.assertEqual(account.login(timeout=1),'test@example.invalid')
            save.assert_called_once()
            self.assertEqual(paths,[])

    def test_pkce_and_redirect_safety(self):
        d = build_authorize_params("urn:uuid:valid", 15011, "stateX", "nonceX", "verifierX")
        self.assertEqual(d["client_id"], "dynamic_agent_client")
        self.assertEqual(d["redirect_uri"], "http://127.0.0.1:15011/auth/callback")
        self.assertIn("chatgpt.tokens.use.direct", d["scope"])
        self.assertEqual(d["code_challenge_method"], "S256")
        self.assertNotEqual(d["code_challenge"], "verifierX")

    def test_callback_security(self):
        self.assertEqual(verify_callback({"code":"abc","client_id":"oaiapp_123","state":"correct"}, "correct"),
                         ("abc","oaiapp_123"))
        self.assertEqual(verify_callback({"code":"abc","state":"correct"}, "correct", "oaiapp_older"),
                         ("abc","oaiapp_older"))
        for invalid in [
            {"code":"abc", "state":"bad", "client_id":"oaiapp_x"},
            {"code":"abc", "state":"correct"},
            {"code":"abc", "state":"correct", "client_id":"oaiapp_wrong"},
            {"state":"correct", "client_id":"oaiapp_x"},
            {"error":"access_denied", "state":"correct"},
        ]:
            with self.assertRaises(AccountError):
                verify_callback(invalid, "correct", "oaiapp_older" if invalid.get('client_id')=='oaiapp_wrong' else None)

    def test_prompt_only_contains_given_text(self):
        p = build_review_prompt("They're soaking rn", "지금 담그고 있어", "en", {"soaking":"터렛 탄약 소모"})
        self.assertIn("터렛 탄약 소모", p)
        self.assertIn("한국어", p)
        self.assertNotIn("Discord token", p)

    def test_sse_complete(self):
        events = [b'data: {"type":"response.output_text.delta","delta":"\xec\xa0\x81\xec\x9d\xb4"}\n',
                  b'data: {"type":"response.completed"}\n', b'data: [DONE]\n']
        self.assertEqual(collect_response_events(events), "적이")
        with self.assertRaises(AccountError):
            collect_response_events(events[:1])
        with self.assertRaises(AccountError):
            collect_response_events(['data: {"type":"response.failed","response":{"error":{"code":"subscription_sharing_usage_limit_exceeded"}}}'])

    def test_phrase_memory(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)/"phrase_memory.json"
            remember_phrase(f, "  They're   pushing  ", "그들이 밀고 들어와", "en")
            self.assertEqual(read_phrase_memory(f)["en:" + normalized_phrase("THEY'RE PUSHING")], "그들이 밀고 들어와")
            with self.assertRaises(ValueError):
                remember_phrase(f, "", "xxx")

    def test_host_id_is_stable(self):
        with tempfile.TemporaryDirectory() as d:
            first = PlanAccount(Path(d)).host_id()
            second = PlanAccount(Path(d)).host_id()
            self.assertEqual(first, second)
            self.assertTrue(first.startswith("urn:uuid:"))


if __name__ == '__main__':
    unittest.main()
