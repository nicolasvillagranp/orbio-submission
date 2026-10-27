"""Tiny Supabase client: PostgREST over httpx with the service-role key (bypasses RLS)."""

from __future__ import annotations

import os
import sys

import httpx


class Db:
    def __init__(self, url: str, key: str, transport: httpx.BaseTransport | None = None):
        self.http = httpx.Client(
            base_url=f"{url.rstrip('/')}/rest/v1",
            headers={"apikey": key, "Authorization": f"Bearer {key}", "Prefer": "return=representation"},
            timeout=15,
            transport=transport,
        )

    @classmethod
    def from_env(cls) -> "Db":
        url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            sys.exit("Falta SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en .env (mira .env.example)")
        return cls(url, key)

    def _send(self, method: str, table: str, params: dict | None = None, json=None) -> list[dict]:
        resp = self.http.request(method, f"/{table}", params=params, json=json)
        resp.raise_for_status()
        return resp.json() if resp.content else []

    def select(self, table: str, params: dict) -> list[dict]:
        return self._send("GET", table, params)

    def insert(self, table: str, rows: list[dict]) -> list[dict]:
        return self._send("POST", table, json=rows)

    def update(self, table: str, match: dict, patch: dict) -> list[dict]:
        return self._send("PATCH", table, {k: f"eq.{v}" for k, v in match.items()}, json=patch)

    def delete(self, table: str, params: dict) -> None:
        self._send("DELETE", table, params)
