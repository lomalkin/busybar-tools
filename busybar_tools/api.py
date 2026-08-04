from __future__ import annotations

import http.client
import json
import os
from typing import Callable, Optional
from urllib import error, parse, request

from busybar_tools.config import HTTP_USER_AGENT


class BusybarApiError(RuntimeError):
    def __init__(self, method: str, url: str, status: Optional[int], body: Optional[bytes] = None):
        self.method = method
        self.url = url
        self.status = status
        self.body = body or b""
        detail = f"{method} {url}"
        if status is not None:
            detail += f" failed with HTTP {status}"
        else:
            detail += " failed"
        if self.body:
            detail += f": {self.body[:200].decode(errors='replace')}"
        super().__init__(detail)


class BusybarApiClient:
    def __init__(self, host: str, port: int = 80, token: Optional[str] = None, timeout: int = 5):
        self.host = host
        self.port = port
        self.token = token
        self.timeout = timeout

    def _url(self, path: str, params: Optional[dict] = None) -> str:
        if not path.startswith("/"):
            path = "/" + path
        query = parse.urlencode(params or {})
        base = f"http://{self.host}:{self.port}{path}"
        return f"{base}?{query}" if query else base

    def _headers(self, extra: Optional[dict] = None) -> dict:
        headers = {
            "User-Agent": HTTP_USER_AGENT,
        }
        if self.token:
            headers["X-API-Token"] = self.token
        if extra:
            headers.update(extra)
        return headers

    def request_bytes(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        data: Optional[bytes] = None,
        headers: Optional[dict] = None,
    ) -> bytes:
        url = self._url(path, params)
        req = request.Request(url, data=data, headers=self._headers(headers), method=method)
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                return response.read()
        except error.HTTPError as exc:
            body = exc.read()
            raise BusybarApiError(method, url, exc.code, body) from exc
        except Exception as exc:
            raise BusybarApiError(method, url, None) from exc

    def get_bytes(self, path: str, params: Optional[dict] = None) -> bytes:
        return self.request_bytes("GET", path, params=params)

    def delete_bytes(self, path: str, params: Optional[dict] = None) -> bytes:
        return self.request_bytes("DELETE", path, params=params)

    def post_bytes(self, path: str, params: Optional[dict] = None, data: bytes = b"") -> bytes:
        return self.request_bytes("POST", path, params=params, data=data)

    def get_json(self, path: str, params: Optional[dict] = None):
        return json.loads(self.get_bytes(path, params=params).decode("utf-8"))

    def post_json(self, path: str, params: Optional[dict] = None, data: bytes = b""):
        return json.loads(self.post_bytes(path, params=params, data=data).decode("utf-8"))

    def upload_file(
        self,
        path: str,
        local_path: str,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> bytes:
        """Stream a file to a device endpoint without loading it into memory."""
        total_size = os.path.getsize(local_path)
        conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        url = self._url(path)
        try:
            conn.putrequest("POST", path)
            for key, value in self._headers({
                "Content-Type": "application/octet-stream",
                "Content-Length": str(total_size),
            }).items():
                conn.putheader(key, value)
            conn.endheaders()

            sent = 0
            with open(local_path, "rb") as source:
                while True:
                    chunk = source.read(65536)
                    if not chunk:
                        break
                    conn.send(chunk)
                    sent += len(chunk)
                    if progress:
                        progress(sent, total_size)

            response = conn.getresponse()
            body = response.read()
            if not 200 <= response.status < 300:
                raise BusybarApiError("POST", url, response.status, body)
            return body
        except BusybarApiError:
            raise
        except Exception as exc:
            raise BusybarApiError("POST", url, None) from exc
        finally:
            conn.close()
