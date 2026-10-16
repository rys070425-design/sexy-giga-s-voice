"""Optional local browser hostname bridge. No page content or history."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import threading

PORT=43861
class BrowserSourceBridge:
    def __init__(self,tracker,key,port=PORT):
        self.tracker=tracker;self.key=key;self.port=port;self.server=None;self.error=''
    def start(self):
        bridge=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def allowed_origin(self):
                origin=self.headers.get('Origin','')
                return not origin or origin.startswith('chrome-extension://')
            def reply(self,code,data):
                self.send_response(code)
                origin=self.headers.get('Origin','')
                if origin and self.allowed_origin():self.send_header('Access-Control-Allow-Origin',origin)
                self.send_header('Content-Type','application/json')
                self.end_headers();self.wfile.write(json.dumps(data).encode())
            def do_OPTIONS(self):
                if not self.allowed_origin():return self.reply(403,{})
                self.send_response(204)
                self.send_header('Access-Control-Allow-Origin',self.headers.get('Origin','chrome-extension://none'))
                self.send_header('Access-Control-Allow-Methods','POST')
                self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type')
                self.end_headers()
            def do_POST(self):
                if self.path!='/source' or not self.allowed_origin():return self.reply(403,{})
                if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+bridge.key):return self.reply(401,{})
                try:
                    count=int(self.headers.get('Content-Length','0'))
                    if count<=0 or count>4096:raise ValueError()
                    data=json.loads(self.rfile.read(count));hosts=data.get('hosts')
                    if not isinstance(hosts,list) or len(hosts)>8 or not all(isinstance(h,str) for h in hosts):raise ValueError()
                    bridge.tracker.set_sites(data.get('browser'),hosts)
                except (ValueError,TypeError,AttributeError):return self.reply(400,{})
                self.reply(200,{'ok':True})
        try:
            self.server=ThreadingHTTPServer(('127.0.0.1',self.port),Handler);self.server.daemon_threads=True
            threading.Thread(target=self.server.serve_forever,daemon=True,name='browser-source-bridge').start()
            return True
        except OSError:
            self.error='웹사이트 이름 연결 포트를 사용할 수 없습니다. 다른 Universal Voice KR 창을 닫아 주세요.'
            return False
    def close(self):
        if self.server:self.server.shutdown();self.server.server_close();self.server=None
