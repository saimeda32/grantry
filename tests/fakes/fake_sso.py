from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class _State:
    def __init__(self):
        self.token_polls = 0


def _make_handler(state: _State):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body, error_type=None):
            payload = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            # Real sso-oidc reports the error class via this header; botocore
            # reads it to set Error.Code. Without it, a 400 reads as code "400".
            if error_type is not None:
                self.send_header("x-amzn-errortype", error_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(length)
            try:
                body = json.loads(body_bytes) if body_bytes else {}
            except json.JSONDecodeError:
                body = {}
            path = self.path
            if path.endswith("/client/register"):
                self._send(
                    200,
                    {
                        "clientId": "cid",
                        "clientSecret": "csecret",
                        "clientIdIssuedAt": 0,
                        "clientSecretExpiresAt": 9999999999,
                    },
                )
            elif path.endswith("/device_authorization"):
                self._send(
                    200,
                    {
                        "deviceCode": "dc",
                        "userCode": "WXYZ-1234",
                        "verificationUri": "https://device.example/verify",
                        "verificationUriComplete": "https://device.example/verify?code=WXYZ-1234",
                        "expiresIn": 600,
                        "interval": 1,
                    },
                )
            elif path.endswith("/token"):
                if body.get("grantType") == "refresh_token":
                    # Renewal: return a fresh access token and rotate the refresh token.
                    self._send(
                        200,
                        {
                            "accessToken": "refreshed-access-token",
                            "tokenType": "Bearer",
                            "expiresIn": 3600,
                            "refreshToken": "refresh-token-v2",
                        },
                    )
                    return
                state.token_polls += 1
                if state.token_polls < 2:
                    self._send(
                        400,
                        {"error": "authorization_pending", "error_description": "pending"},
                        error_type="AuthorizationPendingException",
                    )
                else:
                    self._send(
                        200,
                        {
                            "accessToken": "sso-access-token-value",
                            "tokenType": "Bearer",
                            "expiresIn": 3600,
                            "refreshToken": "refresh-token-v1",
                        },
                    )
            else:
                self._send(404, {"error": "not_found"})

        def do_GET(self):  # noqa: N802
            path = self.path
            if "/assignment/accounts" in path:
                self._send(
                    200,
                    {
                        "accountList": [
                            {"accountId": "111122223333", "accountName": "prod"},
                            {"accountId": "444455556666", "accountName": "dev-payments"},
                        ]
                    },
                )
            elif "/assignment/roles" in path:
                self._send(
                    200,
                    {
                        "roleList": [
                            {"roleName": "ReadOnlyAccess", "accountId": "111122223333"},
                            {"roleName": "AWSPowerUserAccess", "accountId": "111122223333"},
                        ]
                    },
                )
            elif "/federation/credentials" in path:
                self._send(
                    200,
                    {
                        "roleCredentials": {
                            "accessKeyId": "AKIAFAKE",
                            "secretAccessKey": "fakesecret",
                            "sessionToken": "faketoken",
                            "expiration": 1893456000000,
                        }
                    },
                )
            else:
                self._send(404, {"error": "not_found"})

    return Handler


class FakeSSO:
    def __init__(self):
        self._state = _State()
        self._server = HTTPServer(("127.0.0.1", 0), _make_handler(self._state))
        port = self._server.server_address[1]
        self.endpoint = f"http://127.0.0.1:{port}"

    def __enter__(self):
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()
