#!/usr/bin/env python3
"""
Vercel cron endpoint for refreshing BMKG forecast data.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from fetch.fetch_weather_data import run_refresh_job


class handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorize(self) -> bool:
        secret = os.getenv("CRON_SECRET")
        auth_header = self.headers.get("authorization")
        return bool(secret) and auth_header == f"Bearer {secret}"

    def _handle(self) -> None:
        if not self._authorize():
            self._send_json({"ok": False, "error": "Unauthorized"}, status=401)
            return

        query = parse_qs(urlparse(self.path).query)
        force = query.get("force", ["0"])[0] in {"1", "true", "yes"}

        try:
            result = run_refresh_job(force=force)
            self._send_json({"ok": True, **result})
        except Exception as exc:
            self._send_json(
                {"ok": False, "error": str(exc)},
                status=500,
            )

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()
