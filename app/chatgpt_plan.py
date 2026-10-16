"""Opt-in, user-click-only Sign in with ChatGPT integration.

Follows the OpenAI 2026 open-source plan-sharing OAuth/PKCE flow. The local
Windows Credential Manager stores tokens via keyring; do not copy credentials
into settings, error messages, telemetry, stdout, or application log files.

NOTICE: Do not call improve_translation as a reaction to other Discord users'
voices. The UI must invoke it only after a local user clicks '보정 요청'.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError

AUTH_URL = "https://auth.openai.com/api/accounts/authorize"
TOKEN_URL = "https://auth.openai.com/api/accounts/oauth/token"
OIDC_URL = "https://auth.openai.com/.well-known/openid-configuration"
RESOURCE = "https://api.openai.com/v1"
SCOPE = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
SERVICE = "UniversalVoiceKR.ChatGPT"
ACCOUNT = "user_local_plan"
AGENT_NAME = "Universal Voice KR"
CALLBACK_PATH = "/auth/callback"


class AccountError(RuntimeError):
    pass


def _json_request(url: str, data=None, headers=None, timeout=15, max_bytes=256_000):
    """Send a bounded HTTPS request; never persist or include request contents in errors."""
    if not url.startswith("https://"):
        raise AccountError("HTTPS가 아닌 연결을 차단했습니다.")
    body = None
    hdr = {"Accept": "application/json", "User-Agent": "UniversalVoiceKR/0.3"}
    if headers:
        hdr.update(headers)
    if data is not None:
        body = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
    req = Request(url, data=body, headers=hdr)
    try:
        with urlopen(req, timeout=timeout) as resp:
            if not resp.url.startswith("https://"):
                raise AccountError("안전하지 않은 리다이렉트")
            raw = resp.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise AccountError("응답 크기 제한 초과")
            return json.loads(raw)
    except HTTPError as exc:
        # Do not include untrusted payloads which could expose tokens or user text.
        raise AccountError(f"OpenAI 연결 실패 (HTTP {exc.code})") from None


def _token_exchange(form):
    return _json_request(TOKEN_URL, urlencode(form).encode("ascii"),
                         {"Content-Type": "application/x-www-form-urlencoded"})


def build_authorize_params(host_id, port, state, nonce, verifier, client_id="dynamic_agent_client"):
    """Pure helper, easy to test with no network."""
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    params = {"client_id": client_id, "ext_agent_host_id": host_id,
              "redirect_uri": f"http://127.0.0.1:{port}{CALLBACK_PATH}",
              "response_type": "code", "scope": SCOPE, "resource": RESOURCE,
              "state": state, "nonce": nonce, "code_challenge_method": "S256",
              "code_challenge": challenge}
    if client_id == "dynamic_agent_client":
        params["agent_name_hint"] = AGENT_NAME
    return params


def verify_callback(params, expected_state, existing_client_id=None):
    """Return (code, issued client ID). Never allow mismatch to reach token endpoint."""
    if params.get("state") != expected_state:
        raise AccountError("잘못된 로그인 응답(state 불일치)")
    if params.get("error"):
        raise AccountError("로그인이 취소되었거나 권한이 승인되지 않았습니다.")
    code = params.get("code")
    issued = params.get("client_id")
    if not code:
        raise AccountError("로그인 인증 코드가 없습니다.")
    if existing_client_id:
        if issued and issued != existing_client_id:
            raise AccountError("등록된 클라이언트 ID가 변경되어 차단했습니다.")
        issued = existing_client_id
    if not issued or issued == "dynamic_agent_client":
        raise AccountError("새 클라이언트 등록이 완료되지 않았습니다.")
    return code, issued


def _decode_id_token(id_token, client_id, nonce):
    """Validate signature, issuer, audience, nonce, expiration using OIDC JWKS."""
    import jwt
    from jwt import PyJWKClient
    meta = _json_request(OIDC_URL)
    if meta.get("issuer") != "https://auth.openai.com":
        raise AccountError("신뢰할 수 없는 로그인 제공자")
    jwks_uri = meta.get("jwks_uri", "")
    if not jwks_uri.startswith("https://auth.openai.com/"):
        raise AccountError("JWKS 주소가 올바르지 않습니다.")
    key = PyJWKClient(jwks_uri, cache_jwk_set=True).get_signing_key_from_jwt(id_token)
    claims = jwt.decode(id_token, key.key, algorithms=["RS256", "ES256"],
                        audience=client_id, issuer="https://auth.openai.com")
    if claims.get("nonce") != nonce or not claims.get("sub"):
        raise AccountError("로그인 인증 정보 검증에 실패했습니다.")
    return claims


class PlanAccount:
    """Single locally-controlled ChatGPT account. Thread-safe rotating refresh tokens."""
    def __init__(self, home: Path):
        self.home = Path(home)
        self._lock = threading.RLock()
        self._record = None
        self._host_id = None

    def _storage(self):
        try:
            import keyring
            return keyring
        except ImportError:
            raise AccountError("Windows 자격 증명 저장소(keyring)를 설치해야 합니다.")

    def host_id(self):
        with self._lock:
            if self._host_id:
                return self._host_id
            path = self.home / "chatgpt_host_id.txt"
            try:
                saved = path.read_text(encoding="utf-8").strip()
                if uuid.UUID(saved.replace("urn:uuid:", "")) and saved.startswith("urn:uuid:"):
                    self._host_id = saved
                    return saved
            except (FileNotFoundError, ValueError, OSError):
                pass
            self.home.mkdir(parents=True, exist_ok=True)
            self._host_id = "urn:uuid:" + str(uuid.uuid4())
            path.write_text(self._host_id, encoding="utf-8")
            return self._host_id

    def load(self):
        """Read DPAPI protected record; accept legacy keyring credentials if present."""
        with self._lock:
            if self._record:
                return dict(self._record)
            from secure_credentials import SecureCredentialStore, SecureStorageError
            try:
                record = SecureCredentialStore(self.home).load()
            except SecureStorageError as exc:
                raise AccountError(str(exc)) from None
            if record is None:
                # Compatibility with versions before the encrypted-file DLC.
                # Credential Manager can reject long OAuth tokens (>2560 bytes).
                try:
                    raw = self._storage().get_password(SERVICE, ACCOUNT)
                    record = json.loads(raw) if raw else None
                except Exception:
                    record = None
            if not isinstance(record, dict):
                return None
            self._record = dict(record)
            return dict(record)

    def save(self, record):
        """Store the complete OAuth record encrypted under this Windows account."""
        with self._lock:
            from secure_credentials import SecureCredentialStore, SecureStorageError
            try:
                SecureCredentialStore(self.home).save(record)
            except SecureStorageError as exc:
                raise AccountError(str(exc)) from None
            self._record = dict(record)
            # If a previous version successfully stored a legacy credential,
            # remove that redundant copy only AFTER the new save succeeds.
            try:
                self._storage().delete_password(SERVICE, ACCOUNT)
            except Exception:
                pass

    def disconnect(self):
        """Remove the encrypted local credential (remote revocation is separate)."""
        with self._lock:
            from secure_credentials import SecureCredentialStore, SecureStorageError
            try:
                SecureCredentialStore(self.home).delete()
            except SecureStorageError as exc:
                raise AccountError(str(exc)) from None
            try:
                self._storage().delete_password(SERVICE, ACCOUNT)
            except Exception:
                pass
            self._record = None


    def is_authorized(self):
        item = self.load()
        return bool(item and "chatgpt.tokens.use.direct" in item.get("scopes", []))

    def login(self, message=lambda *_: None, timeout=180):
        """Run only on worker thread, opens external browser for explicit consent."""
        initial = self.load()
        existing_client_id = initial.get("client_id") if initial else None
        previous_sub = initial.get("subject") if initial else None
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        incoming = {}
        callback_received = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return
            def do_GET(self):
                target = urlsplit(self.path)
                if target.path != CALLBACK_PATH:
                    self.send_error(404)
                    return
                query = parse_qs(target.query, keep_blank_values=True)
                params = {k: v[0] for k, v in query.items() if v}
                if params.get('state') != state:
                    self.send_error(400)
                    return
                incoming.update(params)
                callback_received.set()
                try:
                    verify_callback(incoming, state, existing_client_id)
                    msg = "승인 정보를 받았습니다. 번역기 프로그램으로 돌아가세요."
                except AccountError:
                    msg = "승인 확인 실패. 번역기 프로그램에서 오류를 확인하세요."
                content = ("<!doctype html><meta charset='utf-8'><title>Universal Voice KR</title>"
                           "<p>" + msg + "</p>").encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Security-Policy", "default-src 'none'")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            deadline = time.monotonic() + float(timeout)
            server.timeout = min(0.5, float(timeout))
            p = build_authorize_params(self.host_id(), server.server_port, state, nonce, verifier,
                                       existing_client_id or "dynamic_agent_client")
            url = AUTH_URL + "?" + urlencode(p)
            message("브라우저에서 ChatGPT 계정 로그인과 사용량 공유 권한을 확인하세요.")
            if not webbrowser.open(url):
                raise AccountError("브라우저를 자동 실행하지 못했습니다.")
            # Browser prefetches, favicon requests, and unrelated localhost
            # traffic must not consume the one chance to complete sign-in.
            while not callback_received.is_set() and time.monotonic() < deadline:
                server.handle_request()
        if not callback_received.is_set():
            raise AccountError('로그인 대기 시간이 지났습니다. 다시 시도하세요.')
        code, client_id = verify_callback(incoming, state, existing_client_id)
        tokens = _token_exchange({"grant_type": "authorization_code", "client_id": client_id,
                                  "code": code, "code_verifier": verifier,
                                  "redirect_uri": p["redirect_uri"], "resource": RESOURCE})
        if not tokens.get("id_token") or not tokens.get("access_token"):
            raise AccountError("인증 토큰이 누락됐습니다.")
        claims = _decode_id_token(tokens["id_token"], client_id, nonce)
        if previous_sub and claims["sub"] != previous_sub:
            raise AccountError("다른 계정으로 재인증하려 했습니다. 기존 계정을 연결 해제한 후 다시 시도하세요.")
        record = {"client_id": client_id, "subject": claims["sub"],
                  "email": claims.get("email", ""), "id_token": tokens["id_token"],
                  "access_token": tokens["access_token"],
                  "refresh_token": tokens.get("refresh_token", ""),
                  "scopes": tokens.get("scope", "").split(),
                  "expires_at": time.time() + float(tokens.get("expires_in", 3600))}
        self.save(record)
        if "chatgpt.tokens.use.direct" not in record["scopes"]:
            raise AccountError("로그인은 됐지만 ChatGPT 플랜 사용 권한이 승인되지 않았습니다.")
        return record.get("email", "로그인 완료")

    def get_access_token(self):
        with self._lock:
            rec = self.load()
            if not rec or "chatgpt.tokens.use.direct" not in rec.get("scopes", []):
                raise AccountError("먼저 ChatGPT에 로그인하고 플랜 사용을 승인하세요.")
            if time.time() < float(rec.get("expires_at", 0)) - 90:
                return rec["access_token"]
            if not rec.get("refresh_token"):
                raise AccountError("로그인 세션이 만료됐습니다. 다시 로그인하세요.")
            new = _token_exchange({"grant_type": "refresh_token", "client_id": rec["client_id"],
                                   "refresh_token": rec["refresh_token"], "resource": RESOURCE})
            if not new.get("access_token") or not new.get("refresh_token"):
                raise AccountError("로그인 갱신이 완료되지 않았습니다.")
            rec.update({"access_token": new["access_token"],
                        "refresh_token": new["refresh_token"],
                        "expires_at": time.time() + float(new.get("expires_in", 3600)),
                        "scopes": new.get("scope", " ".join(rec["scopes"])).split()})
            self.save(rec)
            return rec["access_token"]

    def list_models(self):
        raw = _json_request(RESOURCE + "/models", headers={"Authorization": "Bearer " + self.get_access_token()}, timeout=30, max_bytes=16 * 1024 * 1024)
        return [(x.get("display_name") or x.get("slug"), x["slug"])
                for x in raw.get("models", []) if x.get("slug") and x.get("visibility") == "list"]


def build_review_prompt(original, local_translation, language, glossary=None):
    terms = glossary or {}
    sample = list(terms.items())[:35]
    glossary_lines = "\n".join(f"{str(k)[:40]}: {str(v)[:100]}" for k, v in sample)
    return ("다음은 온라인 게임 음성채팅의 짧은 발언입니다. 반드시 한국어 번역문 한 개만 작성하세요. "
            "이전 로컬 번역을 참고하되 오역이면 수정하세요. 의미를 지어내지 마세요. "
            "게임의 고유명사, 인게임 호출명, 닉네임은 함부로 바꾸지 마세요.\n"
            f"언어 코드: {language[:12]}\n"
            f"원문: {original[:1500]}\n"
            f"기존 번역: {local_translation[:1500]}\n"
            f"게임 용어 참고:\n{glossary_lines}\n")


def collect_response_events(lines):
    """Consume SSE events fully; don't claim success on partial stream."""
    deltas = []
    completed = False
    for raw in lines:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        for part in raw.splitlines():
            if not part.startswith("data: "):
                continue
            val = part[6:].strip()
            if val == "[DONE]":
                continue
            try:
                obj = json.loads(val)
            except ValueError:
                continue
            if obj.get("type") == "response.output_text.delta":
                deltas.append(obj.get("delta", ""))
            elif obj.get("type") == "response.failed":
                error = obj.get("response", {}).get("error", {}) or {}
                raise AccountError("AI 요청 실패: " + str(error.get("code") or "unknown_error")[:120])
            elif obj.get("type") == "response.incomplete":
                raise AccountError("AI 응답이 중간에 종료됐습니다.")
            elif obj.get("type") == "response.completed":
                completed = True
    if not completed:
        raise AccountError("응답 스트림이 완전히 종료되지 않았습니다.")
    return "".join(deltas).strip()


def improve_translation(account: PlanAccount, model: str, original: str, translated: str,
                        language: str, glossary=None):
    if not model or len(model) > 120:
        raise AccountError("ChatGPT에서 사용 가능한 모델을 먼저 선택하세요.")
    if not original.strip():
        raise AccountError("보정할 문장이 없습니다.")
    access = account.get_access_token()
    body = {"model": model, "input": [{"role": "user", "content": build_review_prompt(
        original, translated, language, glossary)}], "store": False, "stream": True}
    req = Request(RESOURCE + "/responses", data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                  headers={"Authorization": "Bearer " + access, "Content-Type": "application/json",
                           "Accept": "text/event-stream", "User-Agent": "UniversalVoiceKR/0.3"})
    try:
        with urlopen(req, timeout=60) as response:
            return collect_response_events(response)
    except HTTPError as exc:
        raise AccountError(f"ChatGPT 요청 실패 (HTTP {exc.code}). 플랜 이용한도 또는 모델 접근 여부를 확인하세요.") from None
